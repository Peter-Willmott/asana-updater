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

resource "aws_ecr_repository" "ecr_repository" {
  name                 = "jobs/asana-integrations/production"
  image_tag_mutability = "MUTABLE"
}


resource "aws_lambda_function" "survey_issues" {
  image_uri        = var.image_uri
  function_name    = "jobs-asana-integrations-survey-issues"
  package_type     = "Image"
  publish          = true
  role             = data.terraform_remote_state.jobs.outputs.jobs_iam_role_arn
  handler          = "main.lambda_handler"
  runtime          = "python3.8"
  layers           = [data.terraform_remote_state.lambda.outputs.lambda_layer_aero_lib_arn]
  timeout          = 900

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

  image_config {
    command = ["main.sync_survey_issues_to_asana_handler"]
  }
}

resource "aws_cloudwatch_event_rule" "every_sixty_minutes" {
  name = "trigger-every-60-minutes"
  description = "Event which triggers every 60 minutes"
  schedule_expression = "rate(60 minutes)"
}

resource "aws_cloudwatch_event_target" "trigger_survey_issues_every_sixty_minutes" {
  rule = aws_cloudwatch_event_rule.every_sixty_minutes.name
  target_id = aws_lambda_function.survey_issues.function_name
  arn = aws_lambda_function.survey_issues.arn
}

resource "aws_lambda_permission" "allow_cloudwatch_to_call_survey_issues" {
  statement_id = "AllowExecutionFromCloudWatch"
  action = "lambda:InvokeFunction"
  function_name = aws_lambda_function.survey_issues.function_name
  principal = "events.amazonaws.com"
  source_arn = aws_cloudwatch_event_rule.every_sixty_minutes.arn
}