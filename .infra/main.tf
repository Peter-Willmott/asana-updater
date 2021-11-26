provider "aws" {
  region  = ""
}

terraform {
  backend "remote" {
    hostname = "app.terraform.io"
    organization = ""

    workspaces {
      name = "jobs-asana-integrations"
    }
  }
  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "~> 3.37.0"
    }
  }
}

data "terraform_remote_state" "lambda" {
  backend = "remote"
  config = {
    hostname = "app.terraform.io"
    organization = ""
    workspaces = {
      name = "terraform-aws-lambda"
    }
  }
}

data "terraform_remote_state" "jobs" {
  backend = "remote"
  config = {
    hostname = "app.terraform.io"
    organization = ""
    workspaces = {
      name = "terraform-aws-jobs"
    }
  }
}

resource "aws_ecr_repository" "ecr_repository" {
  name                 = "jobs/asana-integrations/production"
  image_tag_mutability = "MUTABLE"
}


resource "aws_lambda_function" "mapping_uploads" {
  image_uri        = var.image_uri
  function_name    = "jobs-asana-integrations-mapping-uploads"
  package_type     = "Image"
  publish          = true
  role             = data.terraform_remote_state.jobs.outputs.jobs_iam_role_arn
  timeout          = 300

  environment {
    variables = {
      SHERLOCK_GATEWAY_ACCESS_TOKEN = ""
      JOBS_SECRET_ARN = data.terraform_remote_state.jobs.outputs.jobs_general_secret_arn
      UPDATE_TASK_ONLY_ON_COMPLETE_STATUS = "True"
    }
  }


  image_config {
    command = ["main.sync_mapping_uploads_handler"]
  }
}


resource "aws_cloudwatch_event_rule" "every_thirty_minutes" {
  name = "trigger-every-30-minutes"
  description = "Event which triggers every 30 minutes"
  schedule_expression = "rate(30 minutes)"
}

resource "aws_cloudwatch_event_target" "trigger_mapping_uploads_every_thirty_minutes" {
  rule = aws_cloudwatch_event_rule.every_thirty_minutes.name
  target_id = aws_lambda_function.mapping_uploads.function_name
  arn = aws_lambda_function.mapping_uploads.arn
}

resource "aws_lambda_permission" "allow_cloudwatch_to_call_mapping_uploads" {
  statement_id = "AllowExecutionFromCloudWatch"
  action = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mapping_uploads.function_name
  principal = "events.amazonaws.com"
  source_arn = aws_cloudwatch_event_rule.every_thirty_minutes.arn
}