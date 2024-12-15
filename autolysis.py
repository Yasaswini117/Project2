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
from tabulate import tabulate

# Fetch AIPROXY_TOKEN from environment variable
AIPROXY_TOKEN = os.getenv("AIPROXY_TOKEN")
if not AIPROXY_TOKEN:
    raise ValueError("AIPROXY_TOKEN environment variable is not set.")

# AIProxy configuration
AI_PROXY_URL = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"

# Function: Detect encoding of the file
def detect_encoding(file_path):
    """Detect the file encoding to handle diverse datasets."""
    with open(file_path, 'rb') as f:
        result = detect(f.read())
        return result['encoding']

# Function: Load and preprocess dataset
def load_dataset(file_path):
    """Load the dataset and preprocess it."""
    try:
        encoding = detect_encoding(file_path)
        data = pd.read_csv(file_path, encoding=encoding)
        print(f"Dataset loaded successfully with encoding: {encoding}")
        return data
    except Exception as e:
        raise ValueError(f"Failed to load dataset: {e}")

# Function: Generate column summary
def generate_column_summary(data):
    """Generate a summary of dataset columns."""
    column_summary = {}
    for col in data.columns:
        try:
            column_summary[col] = {
                "type": str(data[col].dtype),
                "num_missing": int(data[col].isnull().sum()),
                "unique_values": int(data[col].nunique()),
                "sample_values": data[col].dropna().sample(min(3, data[col].dropna().shape[0])).tolist()
            }
        except Exception as e:
            column_summary[col] = {"error": f"Could not analyze column: {str(e)}"}
    return column_summary

# Function: Detect outliers using IQR method
def detect_outliers(data):
    """Detect outliers in numeric columns using the IQR method."""
    outliers = {}
    numeric_data = data.select_dtypes(include=['number'])
    for col in numeric_data.columns:
        try:
            Q1 = data[col].quantile(0.25)
            Q3 = data[col].quantile(0.75)
            IQR = Q3 - Q1
            outliers[col] = int(data[(data[col] < (Q1 - 1.5 * IQR)) | (data[col] > (Q3 + 1.5 * IQR))].shape[0])
        except Exception as e:
            outliers[col] = f"Error detecting outliers: {str(e)}"
    return outliers

# Function: Generate visualizations
def generate_visualizations(data):
    """Create and save visualizations for the dataset."""
    numeric_data = data.select_dtypes(include=['number'])
    if not numeric_data.empty:
        # Correlation heatmap
        correlation = numeric_data.corr()
        plt.figure(figsize=(10, 8))
        sns.heatmap(correlation, annot=True, cmap="coolwarm", fmt=".2f")
        plt.title("Correlation Heatmap")
        plt.savefig("correlation_matrix.png")
        plt.close()

        # Histograms
        numeric_data.hist(figsize=(12, 10), bins=20, edgecolor='black')
        plt.tight_layout()
        plt.savefig("histograms.png")
        plt.close()

# Function: Generate insights using AIProxy
def generate_insights(column_summary, stats, correlation):
    """Generate insights using AIProxy by sending a structured prompt."""
    prompt = {
        "summary_statistics": column_summary,
        "descriptive_stats": stats.to_dict(),
        "correlation": correlation.to_dict() if isinstance(correlation, pd.DataFrame) else correlation,
        "questions": [
            "What trends or patterns can you identify?",
            "Are there any significant correlations or outliers?",
            "What additional analyses should be performed?"
        ]
    }

    prompt_json = json.dumps(prompt, indent=2)
    token_usage = len(prompt_json.split()) // 4  # Estimate tokens
    print(f"Estimated Token Usage: {token_usage}")

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
                {"role": "user", "content": prompt_json}
            ]
        }
    )

    if response.status_code == 200:
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "No insights available."), token_usage
    else:
        raise ValueError(f"AIProxy API call failed with status {response.status_code}: {response.text}")

# Function: Write report to README.md
def write_report(data, column_summary, stats, outliers, insights):
    """Generate a detailed analysis report in README.md."""
    with open("README.md", "w") as f:
        f.write("# Automated Analysis Report\n\n")
        f.write(f"## Dataset Overview\n\n- **Rows**: {data.shape[0]}\n- **Columns**: {data.shape[1]}\n\n")

        f.write("## Column Summary\n")
        f.write(tabulate(
            [[col, details.get('type', 'N/A'), details.get('num_missing', 'N/A'), details.get('unique_values', 'N/A'), details.get('sample_values', 'N/A')] for col, details in column_summary.items()],
            headers=["Column", "Type", "Missing Values", "Unique Values", "Sample Values"],
            tablefmt="github"
        ))
        f.write("\n\n")

        f.write("## Summary Statistics\n")
        f.write(stats.to_markdown())
        f.write("\n\n")

        f.write("## Outlier Detection\n")
        f.write(tabulate(
            [[col, count] for col, count in outliers.items()],
            headers=["Column", "Outlier Count"],
            tablefmt="github"
        ))
        f.write("\n\n")

        f.write("## Insights from LLM\n")
        f.write(insights)
        f.write("\n\n")

        f.write("## Visualizations\n")
        f.write("![Correlation Heatmap](correlation_matrix.png)\n")
        f.write("![Histograms](histograms.png)\n")

# Main Function
def main(file_path):
    """Main function to orchestrate the analysis."""
    try:
        data = load_dataset(file_path)
        column_summary = generate_column_summary(data)
        stats = data.describe(include='all').transpose()
        correlation = data.select_dtypes(include=['number']).corr()
        outliers = detect_outliers(data)
        generate_visualizations(data)
        insights, token_usage = generate_insights(column_summary, stats, correlation)

        print(f"Insights generated with {token_usage} tokens.")
        write_report(data, column_summary, stats, outliers, insights)
        print("Analysis complete. Report saved to README.md.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python script.py <csv_filename>")
        sys.exit(1)

    csv_filename = sys.argv[1]
    main(csv_filename)
