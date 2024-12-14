import argparse
import base64
import dotenv
import glob
import httpx
import json
import os
import pandas as pd
import random
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from collections import namedtuple, Counter
from platformdirs import user_data_dir
from rich.console import Console
from subprocess import run, PIPE
import logging

# Set environment variable for AIPROXY_TOKEN
AIPROXY_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjIzZjMwMDMxMTdAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.LX_wTuS0-CWg6IBPJtnClBNYmwR5yUbDhaWYd2DmaI8"

# Use the AIProxy endpoint
AI_PROXY_URL = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def detect_encoding(file_path):
    try:
        with open(file_path, 'rb') as f:
            return f.read(512).decode(errors="ignore")
    except Exception as e:
        logging.error(f"Error detecting encoding for {file_path}: {str(e)}")
        raise

def analyze_csv(file_path):
    try:
        # Detect file encoding
        encoding = detect_encoding(file_path)
        
        # Load the CSV file with detected encoding
        data = pd.read_csv(file_path, encoding=encoding)
        logging.info(f"Successfully loaded {file_path} with encoding {encoding}")

        # Basic information about the dataset
        column_summary = summarize_columns(data)
        stats = data.describe(include="all").transpose()

        # Select only numeric columns for correlation matrix
        numeric_data = data.select_dtypes(include=["number"])
        correlation = numeric_data.corr().to_dict() if not numeric_data.empty else "No numeric columns available for correlation analysis."

        # Detect outliers (IQR Method)
        outliers = detect_outliers(numeric_data, data)

        # Create a summary to send to the LLM
        llm_prompt = generate_llm_prompt(column_summary, stats, correlation)

        # Send the prompt to AIProxy
        insights = get_llm_insights(llm_prompt)

        # Write results to README.md
        write_to_readme(data, column_summary, stats, correlation, outliers, insights)

    except Exception as e:
        logging.error(f"Error processing file {file_path}: {str(e)}")
        sys.exit(1)

def summarize_columns(data):
    column_summary = {}
    for col in data.columns:
        try:
            column_summary[col] = {
                "type": str(data[col].dtype),
                "num_missing": int(data[col].isnull().sum()),
                "unique_values": int(data[col].nunique()) if isinstance(data[col].nunique(), (int,)) else data[col].nunique(),
                "sample_values": data[col].dropna().sample(min(3, data[col].dropna().shape[0])).tolist() if data[col].nunique() > 3 else data[col].dropna().unique().tolist()
            }
        except Exception as e:
            column_summary[col] = {"error": f"Could not analyze column due to: {str(e)}"}
    return column_summary

def detect_outliers(numeric_data, data):
    outliers = {}
    for col in numeric_data.columns:
        try:
            Q1 = data[col].quantile(0.25)
            Q3 = data[col].quantile(0.75)
            IQR = Q3 - Q1
            outliers[col] = data[(data[col] < (Q1 - 1.5 * IQR)) | (data[col] > (Q3 + 1.5 * IQR))].shape[0]
        except Exception as e:
            outliers[col] = f"Error detecting outliers: {str(e)}"
    return outliers

def generate_llm_prompt(column_summary, stats, correlation):
    return f"""
    You are analyzing a dataset. Here are the details:
    Column Summary: {json.dumps(column_summary, indent=2)}
    Summary Statistics: {stats.to_json()}
    Correlation Matrix: {json.dumps(correlation)}
    Suggest further analyses or insights based on this information.
    """

def get_llm_insights(llm_prompt):
    try:
        response = httpx.post(
            AI_PROXY_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AIPROXY_TOKEN}"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a data analysis assistant."},
                    {"role": "user", "content": llm_prompt}
                ]
            }
        )
        response.raise_for_status()
        insights = response.json().get("choices", [{}])[0].get("message", {}).get("content", "No insights available.")
        return insights
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error occurred: {str(e)}")
        return "Error retrieving insights"
    except Exception as e:
        logging.error(f"Error occurred while fetching insights: {str(e)}")
        return "Error retrieving insights"

def write_to_readme(data, column_summary, stats, correlation, outliers, insights):
    try:
        with open("README.md", "w") as f:
            f.write("# Automated Analysis Report\n\n")
            f.write("## Dataset Overview\n")
            f.write(f"- **Number of rows**: {data.shape[0]}\n")
            f.write(f"- **Number of columns**: {data.shape[1]}\n\n")

            f.write("## Column Summary\n")
            f.write("| Column Name | Data Type | Missing Values | Unique Values | Sample Values |\n")
            f.write("|-------------|-----------|----------------|---------------|---------------|\n")
            for col, details in column_summary.items():
                f.write(f"| {col} | {details.get('type', 'N/A')} | {details.get('num_missing', 'N/A')} | {details.get('unique_values', 'N/A')} | {details.get('sample_values', 'N/A')} |\n")
            f.write("\n")

            f.write("## Summary Statistics\n")
            f.write(stats.to_string())
            f.write("\n\n")

            f.write("## Correlation Matrix\n")
            f.write(json.dumps(correlation, indent=2))
            f.write("\n\n")

            f.write("## Outlier Detection\n")
            f.write("| Column Name | Outlier Count |\n")
            f.write("|-------------|---------------|\n")
            for col, count in outliers.items():
                f.write(f"| {col} | {count} |\n")
            f.write("\n")

            f.write("## Insights from LLM\n")
            f.write(insights)
            f.write("\n\n")
        logging.info("README.md successfully written.")

    except Exception as e:
        logging.error(f"Error writing to README.md: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run autolysis.py <csv_filename>")
        sys.exit(1)

    csv_filename = sys.argv[1]
    analyze_csv(csv_filename)
