import logging; logging.getLogger().setLevel(logging.INFO)
import argparse
import json
import subprocess
from google.cloud import bigquery
from google.oauth2 import service_account


def get_bq_client(credentials_json, project_id):
  credentials = service_account.Credentials.from_service_account_info(json.loads(credentials_json))
  return bigquery.Client(credentials=credentials, project=project_id)

def create_bq_dataset(client, dataset_id):
  dataset = bigquery.Dataset(dataset_id)
  dataset.location = "us-central1"
  dataset = client.create_dataset(dataset, exists_ok=True)
  logging.info(f"Created dataset {dataset.dataset_id}")

def delete_bq_dataset(client, dataset_id):
  client.delete_dataset(dataset_id, delete_contents=True, not_found_ok=True)
  logging.info(f"Deleted dataset {dataset_id}")

def execute_dbt_command(command, working_dir):
  result = subprocess.run(command, shell=True, cwd=working_dir, capture_output=True, text=True)
  if result.returncode != 0:
    logging.error(f"Command failed: {command}")
    logging.error(f"{result.stderr}")
    logging.error(f"STDOUT: {result.stdout}")
    raise Exception(f"DBT command failed: {command}")
  logging.info(result.stdout)

def main(project_id, dataset_id, credentials_json, dbt_path, dbt_target, cleanup=False):
  client = get_bq_client(credentials_json=credentials_json, project_id=project_id)
  
  full_dataset_id = f"{project_id}.{dataset_id}"
  if cleanup: # Drop PD dataset
    delete_bq_dataset(client, full_dataset_id)
    return
  
  if "PD_" in dataset_id:
    logging.info(f"DATASET ID: {full_dataset_id}")
    create_bq_dataset(client, full_dataset_id)

  try:
    commands = [
        f"dbt deps",
        f"dbt debug --profiles-dir . --target {dbt_target}",
        f"dbt test --profiles-dir . --target {dbt_target}",
        f"dbt run --profiles-dir . --target {dbt_target}"
    ]

    for command in commands:
      execute_dbt_command(command, dbt_path)

  except Exception as e:
    logging.error(e)
    if "PD_" in dataset_id:
      logging.error("Cleaning up PR dataset due to failure.")
      delete_bq_dataset(client, full_dataset_id)
    raise

if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Manage PR-specific BigQuery dataset")
  parser.add_argument("--project_id", required=True, help="GCP Project ID")
  parser.add_argument("--dataset_id", required=True, help="BigQuery Dataset ID")
  parser.add_argument("--credentials_json", required=True, help="GCP Service Account JSON")
  parser.add_argument("--dbt_path", required=True, help="Path to DBT project")
  parser.add_argument("--dbt_target", required=True, help="DBT target")
  parser.add_argument("--cleanup", action='store_true', help="Cleanup the dataset")

  args = parser.parse_args()
  main(args.project_id, args.dataset_id, args.credentials_json, args.dbt_path, args.dbt_target, args.cleanup)
