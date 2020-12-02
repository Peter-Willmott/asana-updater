provider "aws" {
  region  = "us-east-1"
  version = "~> 2.56.0"
}

terraform {
  backend "remote" {
    hostname = "app.terraform.io"
    organization = "aerobotics"

    workspaces {
      name = "jobs-asana-integrations"
    }
  }
}

data "terraform_remote_state" "lambda" {
  backend = "remote"
  config = {
    hostname = "app.terraform.io"
    organization = "aerobotics"
    workspaces = {
      name = "terraform-aws-lambda"
    }
  }
}

data "terraform_remote_state" "jobs" {
  backend = "remote"
  config = {
    hostname = "app.terraform.io"
    organization = "aerobotics"
    workspaces = {
      name = "terraform-aws-jobs"
    }
  }
}

data "archive_file" "survey_issues" {
  type        = "zip"
  source_dir  = "${path.root}/survey-issues/"
  output_path = "${path.root}/survey-issues/lambda.zip"
}

resource "aws_lambda_function" "survey_issues" {
  filename         = data.archive_file.survey_issues.output_path
  function_name    = "jobs-asana-integrations-survey-issues"
  role             = data.terraform_remote_state.jobs.outputs.jobs_iam_role_arn
  handler          = "main.handler"
  runtime          = "python3.8"
  source_code_hash = data.archive_file.survey_issues.output_base64sha256
  layers           = [data.terraform_remote_state.lambda.outputs.lambda_layer_aero_lib_arn]
  timeout          = 300

  environment {
    variables = {
      SHERLOCK_GATEWAY_ACCESS_TOKEN = "AERO-INTERNAL-PASS"
      JOBS_SECRET_ARN = data.terraform_remote_state.jobs.outputs.jobs_general_secret_arn
    }
  }

  vpc_config {
    security_group_ids = [
      data.terraform_remote_state.jobs.outputs.sherlock_vpc_security_group_id
    ]
    // Need private subnets because of the NAT Gateway so that the lambda can connect to internet
    subnet_ids = [
      "subnet-0fd06654c739301f7",
      "subnet-0b8fa19b7389a8a7d"
    ]
  }
}