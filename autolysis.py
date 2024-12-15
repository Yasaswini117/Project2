# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pandas",
#     "matplotlib",
#     "seaborn",
#     "numpy",
#     "chardet",
#     "tabulate",
#     "requests",
# ]
# ///

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import json
import os
import requests
import numpy as np
from chardet import detect

# Fetch AIPROXY_TOKEN from environment variable
AIPROXY_TOKEN = os.getenv("AIPROXY_TOKEN")
if not AIPROXY_TOKEN:
    raise ValueError("AIPROXY_TOKEN environment variable is not set.")

# Use the AIProxy endpoint
AI_PROXY_URL = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"

def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        result = detect(f.read())
        return result['encoding']

def analyze_csv(file_path):
    try:
        # Detect file encoding
        encoding = detect_encoding(file_path)
        
        # Load the CSV file with detected encoding
        data = pd.read_csv(file_path, encoding=encoding)

        # Basic information about the dataset
        column_summary = {}
        for col in data.columns:
            try:
                column_summary[col] = {
                    "type": str(data[col].dtype),
                    "num_missing": int(data[col].isnull().sum()),
                    "unique_values": int(data[col].nunique()) if isinstance(data[col].nunique(), (int, np.integer)) else data[col].nunique(),
                    "sample_values": data[col].dropna().sample(min(3, data[col].dropna().shape[0])).tolist() if data[col].nunique() > 3 else data[col].dropna().unique().tolist()
                }
            except Exception as e:
                column_summary[col] = {"error": f"Could not analyze column due to: {str(e)}"}

        # Generate summary statistics
        stats = data.describe(include="all").transpose()

        # Select only numeric columns for correlation matrix
        numeric_data = data.select_dtypes(include=["number"])
        if not numeric_data.empty:
            correlation = numeric_data.corr()
        else:
            correlation = "No numeric columns available for correlation analysis."

        # Detect outliers (IQR Method)
        outliers = {}
        for col in numeric_data.columns:
            try:
                Q1 = data[col].quantile(0.25)
                Q3 = data[col].quantile(0.75)
                IQR = Q3 - Q1
                outliers[col] = data[(data[col] < (Q1 - 1.5 * IQR)) | (data[col] > (Q3 + 1.5 * IQR))].shape[0]
            except Exception as e:
                outliers[col] = f"Error detecting outliers: {str(e)}"

        # Generate visualizations for numeric columns
        if not numeric_data.empty:
            # Correlation matrix heatmap
            plt.figure(figsize=(10, 6))
            sns.heatmap(correlation, annot=True, cmap="coolwarm", fmt=".2f")
            plt.title("Correlation Matrix")
            plt.savefig("correlation_matrix.png")
            plt.close()

            # Histograms for numeric data
            numeric_data.hist(figsize=(12, 10), bins=20, edgecolor='black')
            plt.tight_layout()
            plt.savefig("histograms.png")
            plt.close()

        # Create a summary to send to the LLM
        llm_prompt = f"""
        You are analyzing a dataset. Here are the details:
        Column Summary: {json.dumps(column_summary, indent=2)}
        Summary Statistics: {stats.to_json()}
        Correlation Matrix: {correlation if isinstance(correlation, str) else correlation.to_json()}
        Suggest further analyses or insights based on this information.
        """

        # Send the prompt to AIProxy
        response = requests.post(
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

        # Extract insights from the response
        insights = response.json().get("choices", [{}])[0].get("message", {}).get("content", "No insights available.")

        # Write results to README.md
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
            f.write(stats.to_markdown())
            f.write("\n\n")

            f.write("## Correlation Matrix\n")
            if not isinstance(correlation, str):
                f.write(correlation.to_markdown())
            else:
                f.write(correlation)
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

            f.write("## Visualizations\n")
            if not numeric_data.empty:
                f.write("![Correlation Matrix](correlation_matrix.png)\n")
                f.write("![Histograms](histograms.png)\n")

    except Exception as e:
        print(f"Error processing file {file_path}: {str(e)}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: uv run autolysis.py <csv_filename>")
        sys.exit(1)

    csv_filename = sys.argv[1]
    analyze_csv(csv_filename)
