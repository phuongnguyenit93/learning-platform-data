# Data Preparation and Training Environment Management

In the **AI and Machine Learning on OCI** chapter of the **Oracle Cloud Infrastructure** module, training preparation consists of two tightly coupled parts: building data fit for the problem and providing a manageable, reproducible execution environment.

A notebook that runs today is not yet proof that the workflow will run again on an OCI Data Science Job, under a different principal, or after libraries are updated. You must know which data was used, which source code processed it, which environment executed it, and which OCI resources were permitted to be accessed.

This lesson focuses on the following outputs:

- A dataset version with clear provenance, contract, and splitting strategy.
- A preprocessing workflow that avoids using information that did not exist at prediction time.
- A training environment that is selected, verified, and versioned.
- Configuration for transitioning from a notebook to a job, complete with authorization, networking, monitoring, and cost control.

## 1. The unit of reproducibility is the entire training run

A training run can be described by the following set of information:

~~~text
Training run =
    dataset version
  + source code version
  + preprocessing and split configuration
  + software environment
  + compute resources and execution configuration
  + run tracking metadata
~~~

Two runs of the same source file can still differ if they read a "latest" data path, install libraries without pinned versions, or use different data splits.

| Component | Information to record |
| --- | --- |
| Data | Dataset ID, manifest, source, cutoff timestamp, individual object versions or checksums |
| Source code | Git commit or code package identifier, entrypoint |
| Preprocessing | Schema, feature list, cleaning rules, pipeline version |
| Data split | Time window, group rule, seed if applicable |
| Environment | Python, libraries, approved Conda environment or container image |
| Execution | Shape, CPU/GPU, region, worker/thread configuration, and runtime limit |
| Traceability | Run ID or job run OCID, logs, check results, and output storage location |

Never write passwords, tokens, or private keys into reproducibility records. For sensitive data, store only necessary identifiers and metadata in locations with appropriate access controls.

## 2. Data and environment preparation flow on OCI

One organizational pattern separates business sources, versioned datasets, software environments, and per-run outputs.

~~~mermaid
flowchart TD
    A["Oracle Database, files, and business sources"] --> B["Point-in-time extraction"]
    B --> C["Object Storage: versioned raw data"]
    C --> D["Validate, normalize, and define split strategy"]
    D --> E["Dataset release and manifest"]
    E --> F["Data Science Notebook: exploration and experimentation"]
    G["Selected Conda environment"] --> F
    F --> H["Environment published to Object Storage"]
    E --> I["Data Science Job: parameterized execution"]
    H --> I
    J["Versioned source code and config"] --> I
    I --> K["Artifacts, reports, and logs by run ID"]
~~~

This is an illustrative architecture, not a built-in pipeline that automatically connects the services.

Notebooks support exploration; Object Storage holds datasets and packaged environments; Jobs execute the workflow decoupled from interactive state. If data volume exceeds single-machine capacity, distributed processing may be needed, while still preserving the data contract and traceability.

## 3. Define the problem before fetching data

### 3.1. Running example: predicting late order delivery

Suppose an application needs to predict late-delivery risk **at the exact moment an order is confirmed**.

You must clearly decide:

- Does one record correspond to an order or an individual shipment package?
- Against which promised milestone is "late delivery" defined?
- How are canceled orders or orders without enough observation time handled?
- Which fields are already known when the application must make a prediction?
- Does the model output drive operational adjustments or only prioritize review order?

If one order has multiple packages while data is labeled at the order level, duplicating the label across every package must be justified and evaluated. Using the wrong unit of observation can inflate dataset size without increasing independent information.

### 3.2. Separate prediction time, event time, and label availability time

Three timestamps must be distinguished:

| Timestamp | Meaning in the example |
| --- | --- |
| **Prediction time** | Order confirmation time, when the score must be computed |
| **Event time** | Time the actual event occurs, such as delivery completion |
| **Label availability time** | Time the system has enough information to determine the label |

An event might occur yesterday but be synced to the data warehouse today. When simulating a prediction as of yesterday, do not use records that were not yet present in the system at that time.

For aggregate features like "customer's late-order rate over the past 30 days", use only orders and labels that were already available prior to prediction time. Computing aggregates across the entire table and joining them back onto historical timestamps can leak future information into the model.

### 3.3. Write a data contract

A data contract describes what inputs must satisfy.

| Illustrative field | Type or constraint | Role |
| --- | --- | --- |
| **order_id** | String, non-empty, unique per observation unit | Identifier, not a feature by default |
| **prediction_time** | Timestamp with standardized timezone | Splitting and time alignment |
| **amount** | Numeric, consistent currency unit | Feature if known at confirmation |
| **distance_km** | Non-negative number, computed from info available at prediction time | Feature |
| **warehouse_code** | Valid warehouse code or defined missing value | Categorical feature |
| **destination_zone** | Normalized region group | Categorical feature |
| **late_delivery** | 0/1 label per agreed rule | Target variable |
| **label_available_at** | Timestamp when the label can be used | Label governance and backtesting |

Do not include customer names, phone numbers, or full street addresses directly in training data if the problem only requires delivery zones. If customer-level linkage is needed, consider controlled surrogate identifiers; replacing an identifier alone does not automatically make all data anonymous.

## 4. Ingesting and versioning data

### 4.1. Extracting from Oracle Database or changing sources

Before exporting data, determine:

1. Which table or view is the authoritative source.
2. Which columns to select and time-based filter conditions.
3. What consistent-read mechanism fits the source.
4. How late-arriving data or modified records are handled.
5. How record counts and checksums are reconciled after export.

If you export the orders table at one time and export delivery status several hours later, the two parts may reflect different business states. Design a snapshot or source-consistent reconciliation mechanism; naming a folder with the export date does not create consistency.

Use a database account with only the required read privileges. OCI IAM permissions to access cloud resources do not replace query privileges inside Oracle Database; connectivity, TLS, authentication methods, and database grants must be configured separately.

### 4.2. Distinguish raw data, validated data, and training data

Example of a project-designed object layout:

~~~text
datasets/delivery-delay/
  raw/extract-2026-09-30/...
  releases/ds-2026-09-r1/
    manifest.json
    train/...
    validation/...
    test/...
    quality-report.json

environments/delivery-training/env-r3/...

runs/delivery-delay/run-0042/
  run-manifest.json
  metrics.json
  preprocessing-artifact/...
  model-artifact/...
~~~

These prefixes organize object names. They do not automatically create directories with separate permissions or security boundaries. Bucket scope, policies, and access conditions still must be designed.

Raw data should be retained per policy for lineage back to source; invalid data is routed to quarantine with reasons; dataset releases are published after validation and split assignment.

### 4.3. Use a manifest to specify the dataset explicitly

A manifest is an **application-defined** description, not a mandatory OCI Data Science schema.

~~~json
{
  "datasetId": "delivery-delay-ds-2026-09-r1",
  "schemaVersion": "delivery-schema-v2",
  "labelRuleVersion": "late-delivery-rule-v1",
  "extractionCutoff": "2026-09-30T00:00:00Z",
  "splitRuleVersion": "time-split-v1",
  "objects": [
    {
      "split": "train",
      "objectName": "releases/ds-2026-09-r1/train/part-0001.parquet",
      "versionId": "REPLACE_WITH_ACTUAL_VERSION_ID",
      "sha256": "REPLACE_WITH_ACTUAL_SHA256",
      "rowCount": 120000
    }
  ]
}
~~~

The row count in the example is synthetic. An actual manifest must list all parts across train, validation, and test, along with namespace, bucket, or equivalent locator details.

The release workflow can upload all objects, validate them, and then publish the final manifest. Training workers should treat a release as ready only once the manifest is finalized. Do not assume uploading multiple objects forms an atomic transaction.

### 4.4. Object versioning aids traceability but does not replace release governance

Object Storage provides bucket-level versioning and a version ID for each object version. Prior versions can also incur storage costs. [Object Storage Versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

If you only record an object name, a later run may read a newer version that differs from the one trained on. When an exact version is required, record the version ID and use read operations that support it, or use non-overwriting release naming conventions combined with checksum verification.

Versioning does not prevent an authorized user from permanently deleting a version. Nor does it turn a set of multiple objects into a consistent business snapshot. Data protection policies and dataset release policies are complementary decisions.

## 5. Validate data before allocating large training compute

Run cheap checks first to catch bad inputs early.

| Check category | Example | Suggested handling |
| --- | --- | --- |
| Schema/structure | Missing required column, wrong data type | Halt release publication |
| Keys | Same `order_id` appears multiple times | Check observation unit or deduplication rules |
| Missing values | Missing label or prediction timestamp | Quarantine; never impute labels automatically |
| Value ranges | Negative distance, invalid zone code | Raise error or handle via versioned rule |
| Time alignment | Feature only appears after prediction time | Remove from features or fix construction logic |
| Referential integrity | Order references missing origin warehouse | Reconcile with source and effective dates |
| Distribution | Label rate or missingness shifts sharply | Alert and review before proceeding |
| Sensitive data | Phone number appears outside contract | Block release and handle per policy |

Distinguish **hard errors** from **warnings**. Missing the entire label column is a structural error; an increase in one region's share may be a valid business shift. Do not automatically drop all rare values or outliers, as they may be the exact cases the model needs to recognize.

A quality report should record input row counts, counts rejected per reason, label distribution, and checks executed. Never write raw sensitive failing rows into shared logs.

When choosing alert thresholds, base them on historical data and business requirements. A percentage in a learning example is not a universal default for every project.

## 6. Split train, validation, and test according to deployment scenario

### 6.1. Roles of the three splits

- **Train:** fit parameters of preprocessing steps and the model.
- **Validation:** select configurations, decision thresholds, and candidate approaches.
- **Test:** final evaluation under the locked workflow; avoid repeated use for model selection.

If you repeatedly select features or configurations based on test scores, the test set gradually becomes selection data.

### 6.2. Do not default to random splitting

| Scenario | Splitting strategy to consider |
| --- | --- |
| Nearly independent records without meaningful time ordering | Random split, consider stratification for classification |
| Multiple images or records from the same entity | Group split to reflect the generalization you need to measure |
| Predicting future time periods | Time-based split |
| Delayed labels or overlapping observation windows | Time-based split with an appropriate gap or exclusion condition |
| Evaluating on unseen customers or devices | Hold out those entity groups separately |

Tools like `TimeSeriesSplit` help split data chronologically, though windows, label delays, and features still must be designed for the specific problem. [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

In the order example, an initial description might train on an older period, validate on a later period, and test on a more recent period. However, if simulating "train on day X and predict from day X onward", training may only include labels already available on day X. A gap between windows or exclusion of orders whose labels were unknown at that cutoff may be required.

Having the same customer appear in both older and newer periods may be valid if the system will keep predicting for existing customers. If the goal is predicting for brand-new customers, the split must reflect that different requirement.

### 6.3. Handle duplicates and class imbalance in the right place

Copies of the same image, document, or event should be assigned to the same split group when appropriate. Keeping one copy in train and a near-identical copy in test can produce overly optimistic results.

Oversampling or synthetic sample generation must only be performed inside the training portion of each evaluation fold. Validation and test should preserve distributions reflecting production usage. Class weights or balancing techniques are also configuration settings that must be recorded.

A random seed makes a stochastic operation repeatable, but it does not replace saving the split rule and the list or identifiers of records belonging to each split.

## 7. Build preprocessing to prevent data leakage

### 7.1. Distinguish fixed rules from transformations learned from data

Predefined normalization rules, such as converting meters to kilometers, differ from computing a median from data to impute missing values.

Steps that learn statistics from data must be fit on train, then apply that same fitted state to transform validation, test, and inference data. Pipelines keep preprocessing and the model together. [Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html).

Operations requiring extra care include imputation, scaling, feature selection, PCA, and target encoding. During cross-validation, data-dependent steps must run inside each training fold.

Never treat "only used X columns, didn't touch y" as proof of no leakage. The evaluation set's distribution can also leak into preprocessing steps.

### 7.2. Tabular pipeline example

The Python snippet below targets an environment with compatible pandas and scikit-learn. Variables **train** and **validation** are DataFrames loaded from a release, validated, and split properly. The example illustrates keeping preprocessing coupled with the model; it is not a complete training project.

~~~python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

numeric_columns = ["amount", "distance_km"]
category_columns = ["warehouse_code", "destination_zone"]
feature_columns = numeric_columns + category_columns
target_column = "late_delivery"

numeric_pipeline = Pipeline([
    ("impute", SimpleImputer(strategy="median")),
    ("scale", StandardScaler()),
])

category_pipeline = Pipeline([
    ("impute", SimpleImputer(strategy="most_frequent")),
    ("encode", OneHotEncoder(handle_unknown="ignore")),
])

preprocess = ColumnTransformer([
    ("numeric", numeric_pipeline, numeric_columns),
    ("category", category_pipeline, category_columns),
])

training_pipeline = Pipeline([
    ("preprocess", preprocess),
    ("classifier", LogisticRegression(max_iter=1000)),
])

training_pipeline.fit(
    train[feature_columns],
    train[target_column],
)

validation_probability = training_pipeline.predict_proba(
    validation[feature_columns]
)[:, 1]
~~~

Key takeaways to notice:

- Only the `fit` call on train learns medians, most frequent values, scaling statistics, and encoding categories.
- When calling `predict_proba`, the pipeline uses the already-fitted state to process validation.
- The feature list excludes identifiers, labels, and label-availability timestamps from model inputs.
- Labels must be verified as 0/1 and train must contain both classes for this example.
- Missing-value and categorical policies must fit actual data; do not assume most-frequent imputation is always right.

When saving artifacts, keep the fitted pipeline or equivalent preprocessing components together with the input schema. If you only save the classifier and rewrite preprocessing logic in the application, the two flows can diverge.

### 7.3. For other data modalities, the contract must still be explicit

| Modality | Decisions to lock before training |
| --- | --- |
| Text | Encoding, cleaning rules, language, labels, and versioned tokenizer |
| Images | Format, dimensions, label rules, duplicate images, and train-only augmentation |
| Time series | Frequency, timezone, late-arriving data, lookback window, and horizon |
| LLM fine-tuning data | Sample structure, usage rights, sensitive data, length, and cross-split overlap |

Do not apply the exact same "cleaning" across every source. Stripping diacritics or punctuation can destroy essential information for a text task.

## 8. A training environment has multiple layers

Distinguish Python packages from the full execution environment.

| Layer | Example | Risk if only recording library names |
| --- | --- | --- |
| Runtime | Python and native libraries | Version or ABI incompatibility |
| Dependencies | pandas, scikit-learn, frameworks, OCI SDK | API changes, differing outputs |
| System | OS, CPU architecture, system libraries | Packages installed on Windows do not run on Linux |
| Acceleration | GPU, drivers, CUDA, and related libraries | Framework cannot utilize the GPU |
| Resources | OCPUs, RAM, GPU memory, disk | Out-of-memory or out of disk space |
| OCI integration | Principal, policies, subnet, routes | Can import libraries but cannot read data |
| Configuration | Seed, thread count, job parameters | Hard to explain differences across runs |

Conda packages dependencies; it does not grant IAM policies or create network routes. An environment package also cannot replace underlying infrastructure GPU drivers on its own.

The reproducibility goal must be defined. Reproducing a workflow and quality within acceptable tolerance does not always mean bit-for-bit identical numerical outputs across every CPU/GPU.

## 9. Selecting and using Conda in OCI Data Science Notebook

### 9.1. Three commonly confused concepts

OCI Data Science has service-provided Conda environments, environments installed inside a notebook, and environments published to Object Storage. Environment Explorer lets you inspect these groups. [Viewing the Conda Environments](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_viewing.htm).

| Concept | Practical meaning |
| --- | --- |
| **Data Science Conda environment** | Service-provided environment available for selection |
| **Installed environment** | Copy currently installed inside the notebook session |
| **Published environment** | Packaged copy stored in a bucket for reuse |

Installing an environment does not mean the current notebook is already using its kernel. Updating an installed copy also does not automatically update a published copy or a job's configuration.

### 9.2. Starting from the right environment

Prefer CPU environments for small tabular experiments. Choose GPU only when both the framework and workload can effectively utilize that resource.

Oracle provides the **odsc conda** tool in notebooks to manage environments. Each environment can map to a separate JupyterLab kernel. [Conda Environments](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_understand_environments.htm).

The following illustrative commands run in the **OCI Data Science Notebook terminal**, using a slug taken from Environment Explorer or the live listing:

~~~bash
odsc conda -h
odsc conda list

OCI_DS_ENV_SLUG='REPLACE_WITH_VERIFIED_SLUG'
odsc conda install --slug "$OCI_DS_ENV_SLUG"
~~~

Do not guess a slug from a library name or an old example. After installation, select the right kernel and restart the kernel if dependency changes require it.

Environments installed via the supported workflow live on the block volume under **/home/datascience/conda** and can persist across deactivate/reactivate. Oracle recommends avoiding installing extra packages into the base Python environment because changes there may not persist after reactivation. [Installing Conda Environments](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_installing.htm).

### 9.3. Confirming the active interpreter

Inside the selected kernel, you can inspect non-sensitive metadata:

~~~python
import platform
import sys
from importlib.metadata import version

print({
    "python": platform.python_version(),
    "interpreter": sys.executable,
    "machine": platform.machine(),
    "scikit_learn": version("scikit-learn"),
    "oci_sdk": version("oci"),
})
~~~

The example assumes the listed packages are installed. If a package is missing, a metadata error is also a signal to resolve before training.

When an installation succeeds in the terminal but the notebook still reports missing libraries, compare the terminal's interpreter with the kernel's first. Repeatedly reinstalling with different tools can make the environment harder to manage.

### 9.4. Creating a custom environment when needed

If built-in environments do not fit, you can create one from a Conda specification file using `odsc conda create`. By default, the tool adds required integration components; the option to create an empty environment should be weighed carefully as it may lack a JupyterLab kernel. [Creating a Custom Conda Environment](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_create_conda_env.htm).

Test changes in a separate environment copy, record dependencies, and verify before using them for formal runs. Never bulk-upgrade all libraries just to resolve one missing package.

## 10. Versioning and publishing the training environment

### 10.1. Keep both the specification and resolved dependencies

Two complementary types of evidence exist:

- **Desired specification:** direct libraries, versions or constraints, and package sources.
- **Actual resolved state:** resolved dependencies, builds, architecture, and the packaged environment or image used.

A file listing package names without version constraints may resolve to a different environment next month. Conversely, a specification overly tied to one platform may not transfer to another.

Conda supports multiple export formats; the explicit format is typically platform-bound, whereas environment specs intended for sharing have different characteristics. Choose the format matching your goal and installed tool version. [Conda export](https://docs.conda.io/projects/conda/en/stable/commands/export.html).

A plain `pip` freeze list does not capture Conda packages, system libraries, or drivers. If using both pip and Conda, document both parts and how the environment is constructed.

### 10.2. Publishing to Object Storage

Publishing packages an installed environment and uploads it to a configured bucket. Resource principal can be used with appropriate permissions. [Publishing a Conda Environment](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_publishs_object.htm).

Example commands in the notebook terminal, after replacing illustrative values with actual bucket, namespace, and slug:

~~~bash
OCI_DS_ENV_BUCKET='ml-environments'
OCI_DS_NAMESPACE='REPLACE_WITH_NAMESPACE'
OCI_DS_ENV_SLUG='REPLACE_WITH_VERIFIED_SLUG'

odsc conda init -b "$OCI_DS_ENV_BUCKET" -n "$OCI_DS_NAMESPACE" -a resource_principal
odsc conda publish -s "$OCI_DS_ENV_SLUG"
~~~

After publishing, record the **exact resulting object name or URI**, release version, package metadata, and checksum if your workflow uses one. Do not infer the packaged filename from the slug alone.

An environment release workflow should include these steps:

1. Create or install the candidate environment.
2. Add required dependencies from approved sources.
3. Verify imports, sample data reads, and a small end-to-end flow.
4. Publish the candidate.
5. Install or run the published copy in a clean context.
6. Record the approved version and keep it immutable for reference runs.

If you continue modifying the environment inside a notebook, publish a new version. A published copy is a snapshot of packaged state, not a live sync with the running kernel.

### 10.3. When to consider containers?

Containers fit when you need stricter control over system libraries, native tools, or specialized runtimes. With OCI Data Science Jobs, Bring Your Own Container has its own configuration; reference images by supported digest rather than relying solely on mutable tags. [Creating a Job](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-create.htm).

Containers do not automatically grant dataset read permissions or guarantee GPU compatibility. Verify platform, drivers, registry, image pull permissions, and region per service configuration.

## 11. Granting permissions and networking for data, environments, and outputs

### 11.1. Notebooks and Jobs have different resource identities

The Linux user inside a notebook does not automatically possess OCI IAM permissions. Resource principal allows a notebook to authenticate as a resource identity without storing personal API keys in code. Policies are still required for that resource to access other services. [Using Notebook Sessions to Build and Train Models](https://docs.oracle.com/en-us/iaas/Content/data-science/using/use-notebook-sessions.htm).

A notebook being able to read a bucket does not prove a job run can also read it. The dynamic group must match the right resource type and permitted compartment; membership scope should be bounded per environment.

Illustrative policy showing read-only access for an already configured dynamic group:

~~~text
Allow dynamic-group MlTrainingRuns to read objects in compartment ml-data where target.bucket.name='training-datasets'

Allow dynamic-group MlTrainingRuns to read objects in compartment ml-platform where target.bucket.name='ml-environments'
~~~

These two statements do not grant output write permissions, do not grant access to read every bucket, and do not grant query privileges inside databases. Permissions for a job run to download a published Conda environment from Object Storage are described in [Data Science Policies](https://docs.oracle.com/en-us/iaas/Content/data-science/using/policies.htm).

Separate permissions for reading datasets, reading environments, writing outputs, and managing resources. If a job needs to write artifacts, grant targeted write permissions at the output destination rather than opening tenancy-wide management permissions to fix a write error.

### 11.2. Verify connectivity per destination

| Destination | What to verify |
| --- | --- |
| Object Storage | IAM, endpoint, DNS, and appropriate routes |
| Private database | Connectivity from subnet, NSG/security list, TLS, and database grants |
| External package repository | Permitted egress, proxy, or internal package mirror |
| Container Registry | Repo read permissions, connectivity, and matching registry region |
| Vault or secret store | Principal permitted to retrieve only the required secrets |

With custom networking, you must provide appropriate network paths for accessing Conda environments and data. NAT and Service Gateway serve different roles: Service Gateway serves supported OCI services; NAT serves configured outbound internet traffic. [Conda Environments — Networking](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_understand_environments.htm).

A private subnet does not automatically have the ability to download packages from the internet. Conversely, open network connectivity does not replace Object Storage IAM policies.

### 11.3. Never package secrets into artifacts

Keep passwords, wallets, or sensitive credentials out of training packages whenever possible; retrieve them via environment-supported mechanisms with least privilege. When a wallet is required for a database, protect its storage location, read permissions, and temporary copies.

Never print all environment variables or authentication config files when troubleshooting errors. Log only approved metadata such as library versions, run ID, record counts, and validation status.

## 12. Moving the workflow from a notebook to an OCI Data Science Job

### 12.1. Remove dependencies on interactive state

Before packaging:

- Refactor data reading, validation, preprocessing, and training into functions or modules.
- Move paths, seeds, and parameters into configuration.
- Do not rely on variables that only exist because an old cell ran earlier.
- Do not hard-code notebook-specific local paths for datasets or artifacts.
- Let input errors fail the run explicitly rather than silently training on empty data.

An entrypoint should read configuration, validate inputs, execute the workflow, and write outputs under the run ID. When re-running with identical inputs, never silently overwrite outputs already used as evidence.

### 12.2. Explicitly choose the environment for the Job

A Job can use a service Data Science Conda environment or a published custom Conda environment. Do not assume a Job automatically inherits the notebook's environment. Conda-based runs must declare the corresponding environment; Oracle documentation notes there is no default Conda environment unless configured. [Other Ways to Run Jobs](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-other.htm).

Example environment variable pairs for **published Conda**, shown in YAML for readability:

~~~yaml
CONDA_ENV_TYPE: published
CONDA_ENV_BUCKET: ml-environments
CONDA_ENV_NAMESPACE: REPLACE_WITH_NAMESPACE
CONDA_ENV_OBJECT_NAME: REPLACE_WITH_EXACT_OBJECT_NAME
CONDA_ENV_REGION: REPLACE_WITH_ENVIRONMENT_REGION
JOB_RUN_ENTRYPOINT: src/train.py

TRAINING_DATA_MANIFEST_URI: REPLACE_WITH_MANIFEST_URI
TRAINING_OUTPUT_PREFIX: runs/delivery-delay/run-0042/
TRAINING_SEED: "42"
~~~

This is a configuration example, not a resource creation command. Names starting with **CONDA_ENV_...** and **JOB_RUN_ENTRYPOINT** belong to the service mechanism; the final three **TRAINING_...** variables are application-defined and must be read by training code.

For zip or tar artifacts, the entrypoint must match the actual directory layout inside the archive. Environment properties are documented in [Job Environment Variables](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-env-vars.htm).

If choosing a service Conda environment, use type **service** along with the documented verified slug instead of the published properties. Never mix the two configuration styles arbitrarily.

### 12.3. Record the effective configuration of each job run

A job run can override certain Job settings. Therefore, the Job name alone is insufficient to identify the environment and parameters used.

Record the environment, data manifest, arguments, runtime limit, shape, output location, and job run OCID. OCI exposes default and override values in job run details. [Managing Job Runs](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-manage-runs.htm).

Execution logic pattern:

~~~text
read run configuration
verify identifiers for data, source code, and environment
read manifest and validate input objects
validate schema, labels, and split assignment
fit pipeline on train
evaluate according to locked protocol
save artifacts, metadata, and reports to run-specific location
declare run completion only after required outputs are persisted
~~~

Temporary directories on the runner machine must never be the sole copy holding models or evidence. Persist durable outputs before considering a run complete.

## 13. Selecting compute resources and controlling costs

### 13.1. Measure bottlenecks before scaling up shapes

| Symptom | What to check first |
| --- | --- |
| Out of RAM while reading data | Read only required columns, batch processing, dtypes, and uncompressed size |
| CPU idle while waiting long | Source read speed, many small objects, database, or network |
| Low GPU utilization | Data loading pipeline, framework, batch size, and algorithm GPU acceleration |
| Out of disk | Data copies, caches, environment extraction, and checkpoints |
| One-hot encoding explodes | Cardinality of categorical values, sparse representations, and feature strategy |
| Slow Job startup | Downloading and extracting environment, artifact size, package sources |

Compressed file size does not equal required RAM. Beyond raw data, memory holds intermediate copies, feature matrices, and model state.

Use a representative sample to estimate, but do not conclude from a few rows that the entire dataset will fit in RAM. If scaling out to distributed processing, preserve time rules, schema, and release identifiers.

### 13.2. Runtime limits and resource lifecycle

Configure maximum runtime for job runs to prevent runaway execution; the service provides cancellation when the configured timeout is exceeded. [Creating a Job — Maximum runtime](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-create.htm).

After experimentation:

- Deactivate notebooks when compute is not needed and review retained storage.
- Check for still-running jobs, repeated retries, or duplicate runs on the same inputs.
- Manage lifecycle policies for temporary data, logs, Conda copies, and object versions.
- Retain artifacts needed for auditability per policy rather than deleting everything just to cut storage fees.
- Monitor costs by project compartment or tags.

Deactivating a notebook stops compute billing per service mechanics, while retained block storage can continue incurring charges. [Overview of Data Science — Provisioning and Pricing](https://docs.oracle.com/en-us/iaas/data-science/using/overview.htm).

Cost optimization is not just picking a smaller machine: an oversized environment, repeated redundant data downloads, or unbounded retries also inflate costs without improving the model.

## 14. Troubleshooting training preparation errors

| Symptom | Causes to check | Verification step |
| --- | --- | --- |
| Notebook has package but Job reports missing | Job uses a different or unconfigured environment | Inspect the effective environment of the job run |
| Package installed, cell still fails import | Kernel uses a different interpreter than installed into | Inspect `sys.executable` and reselect kernel |
| Notebook reads bucket, Job cannot | Different principal or dynamic group | Compare resource identities and policies |
| Cannot download environment | Wrong object name, permissions, or network path | Check published metadata, IAM, and connectivity |
| Same code yields noticeably different scores | Data, split, dependencies, or config changed | Compare run manifest, checksums, and environment |
| Evaluation score suspiciously high | Duplicate records, leakage, or bad split | Audit timestamps, groups, and feature construction |
| Libraries missing after deactivate/reactivate | Installed into base or wrong kernel selected | Check installed Conda environments and interpreter |
| Out of RAM after encoding | High-cardinality categoricals, large intermediates | Check cardinality and data representation |
| Job finishes but no artifacts exist | Wrote only locally or save error ignored | Check durable path and completion criteria |
| GPU goes unused | Incompatible runtime, drivers, packages, or algorithm | Verify compatibility for framework and shape |

Never solve every permission error by opening wide permissions. Nor solve every import error by bulk-upgrading all dependencies. Layered troubleshooting keeps the environment explainable.

## 15. Hands-on: preparing a repeatable training run

Practice in a learning compartment using synthetic or authorized data. The goal is to produce evidence for data and environment management, without needing a complex model.

### 15.1. Preparing a dataset release

1. Define the observation unit, prediction time, and label rule.
2. Write the schema and list of permitted fields.
3. Take a data snapshot and strip unnecessary columns.
4. Validate structure, keys, labels, and timestamps.
5. Split according to the deployment target, including label availability rules.
6. Store data, manifest, and quality report in a managed location.

**Required evidence:** release identifier, object list, split strategy, and justification for accepting the dataset.

### 15.2. Preparing an environment release

1. Select a suitable Conda environment in the notebook.
2. Confirm kernel, Python, dependencies, and resources.
3. Run a small flow from reading data to producing outputs.
4. Publish the candidate environment.
5. Record the exact package location and metadata.
6. Reuse the published copy in a clean context to confirm zero reliance on local state.

**Required evidence:** environment identifier, software metadata, and small-flow test results.

### 15.3. Running a Job from identified inputs

1. Package code with a clear entrypoint.
2. Configure dataset manifest, environment, output prefix, and seed.
3. Grant permissions to the job run and verify connectivity per destination.
4. Set a runtime limit, enable appropriate logging, and execute the workflow.
5. Save effective configuration, artifacts, and reports.
6. Re-run with the exact same locked inputs and compare within defined tolerances.

If discrepancies exceed acceptable bounds, inspect data, dependencies, thread counts, hardware, and randomness sources. Do not treat using the same seed as proof that every layer is identical.

### 15.4. Completion criteria for preparation

| Question | Expected evidence |
| --- | --- |
| Do you know exactly which data was used? | Dataset manifest and object identifiers |
| Can you justify labels and features at prediction time? | Schema, label rules, and temporal constraints |
| Does the split match the deployment scenario? | Split rule and split assignment records |
| Does preprocessing stay bundled with the model? | Pipeline or equivalent artifact |
| Can the environment be rebuilt without the current notebook? | Published Conda or image with metadata |
| Does the Job have proper permissions and network paths? | Principal config, policies, and connectivity checks |
| Can you trace results and config for each run? | Run manifest, logs, and durable outputs |
| Are compute limits and data lifecycles bounded? | Maximum runtime and retention policies |

Once this evidence is complete, the team has a solid foundation to proceed to model training and selection on OCI while being able to explain exactly which data, source code, and environment produced any result.
