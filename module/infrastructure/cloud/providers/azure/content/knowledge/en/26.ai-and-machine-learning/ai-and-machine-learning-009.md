# Azure Machine Learning with Workspaces, Compute, and Data Assets

A retail application development team stores orders in Azure SQL Database, product images in Azure Blob Storage, and user events in Azure Event Hubs. The team wants to build a model predicting customer churn, retrain it periodically, and track results on Azure. If individual engineers run notebooks on laptops against different datasets, reproducing results, governing permissions, and controlling costs become very difficult.

**Azure Machine Learning (Azure ML)** provides a platform for managing the machine learning lifecycle. The first three foundational concepts to master are the **workspace** (the scope organizing resources and experiments), **compute** (execution resources running code), and **data assets** (named, typed, versioned data references for ML jobs). Combined properly, these three pieces let teams run verifiable training jobs, decouple data from code, reuse assets, enforce security, and track costs.

This lesson belongs to the **AI and Machine Learning on Azure** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module spans Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data—followed by deploying, monitoring, securing, and controlling costs for an application architecture. Azure ML is where those infrastructure, data, and identity foundations come together to power model training and deployment.

> **Scope:** This lesson prioritizes **Azure Machine Learning v2**, Azure ML Studio, the Azure CLI **`ml`** extension, and the **`azure-ai-ml` Python SDK**. Older guides may use the v1 SDK, Datasets v1, or legacy terminology: never mix v1 and v2 syntax. Features, quotas, VM SKUs, GPUs, workspace networking, Azure regions, and pricing evolve over time; verify real settings before applying.

## Learning Objectives

After this lesson, you will be able to:

1. Describe the relationship between an Azure subscription, resource group, Azure ML workspace, and dependent services.
2. Distinguish between **compute instances**, **AML compute clusters**, and other compute targets.
3. Choose CPU/GPU SKUs, min/max nodes, dedicated vs. low-priority capacity, networking, and autoscaling for a workload.
4. Explain how a **datastore** differs from a **data asset**, and distinguish **`URI_FILE`**, **`URI_FOLDER`**, and **`MLTABLE`**.
5. Version data assets and reference a specific version in a job.
6. Describe a job consisting of **code, command, environment, compute, inputs, and outputs**.
7. Use Azure CLI and Python SDK v2 examples to inspect workspaces/compute/data and create controlled lab resources.
8. Understand identity management, RBAC, data-plane permissions, managed identities, Key Vault, and private networking.
9. Distinguish an ML workspace from Azure AI services, Azure OpenAI/Azure AI Foundry, and inference applications.
10. Build a checklist for testing, monitoring, cost optimization, and post-lab cleanup.

## 1. What Is Azure Machine Learning?

Azure ML is a platform service for building, training, registering, deploying, and managing machine learning models. It integrates across Azure services to:

- Organize workspaces, jobs, experiments, data assets, model assets, and environments.
- Run Python/R code or container-based workflows on supported compute targets.
- Manage datasets and storage path bindings.
- Track run statuses, logs, metrics, and model artifacts.
- Support pipelines, AutoML, model registries, and endpoints per service capabilities.
- Enforce identity, permissions, networking, and infrastructure cost controls.

~~~text
Data sources                    Azure Machine Learning
Azure SQL / Blob / ADLS         +---------------------------+
Cosmos DB / Event Hubs -------> | Workspace                 |
                                |   Data assets             |
                                |   Environments            |
                                |   Jobs / Experiments      |
                                |      |                    |
                                |      v                    |
                                |   Compute instance/cluster|
                                |      |                    |
                                |      v                    |
                                |   Models / outputs        |
                                +---------------------------+
                                             |
                                             v
                                  Evaluation / deployment
                                             |
                                             v
                                    API / application
~~~

**Azure ML does not automatically turn raw sources into trustworthy data.** Your team remains responsible for data quality, partitioning, labels, consent, model validation, and security.

## 2. Workspace: The Collaboration and Governance Hub

An **Azure Machine Learning workspace** is an Azure resource acting as the organizational boundary for ML work. It lets teams define:

- Which jobs and experiments belong to a project.
- Which workspace hosts data, model, and environment assets.
- Who can create, view, run, or administer resources.
- Which compute targets are registered and available.
- Connections to datastores and external services.
- Logs, metrics, lineage, and associated metadata.

~~~text
Azure subscription
    |
    v
Resource group: rg-ml-lab
    |
    +-- Azure ML workspace: aml-churn-lab
    |      |
    |      +-- Data assets: churn_data:1, churn_data:2
    |      +-- Environments: sklearn-env:1
    |      +-- Jobs / experiments
    |      +-- Compute: cpu-cluster-lab
    |      +-- Models / endpoints
    |
    +-- Storage account (or linked source)
    +-- Key Vault
    +-- Application Insights / monitoring resources
    +-- Container Registry (when needed, per service mechanics)
~~~

A workspace is not a VM. Creating a workspace **does not mean GPUs are already running**. Compute is provisioned or attached separately with its own lifecycle and billing.

### Workspace vs. Resource Group

| Concept | Primary Responsibility |
|---|---|
| **Subscription** | Billing, policy/quotas, and top-level Azure governance scope |
| **Resource group** | Logical container of Azure resources for lifecycle and IaC |
| **Azure ML workspace** | Manages assets, jobs, metadata, and ML workflows |
| **Compute target** | Executes code/jobs, consuming CPU/GPU/memory |
| **Datastore** | Connection metadata to a supported data storage location |
| **Data asset** | Named, versioned, typed reference to data for reuse |

A workspace can link to multiple storage accounts and compute targets; **the workspace boundary does not automatically authorize every Azure storage container for use**.

## 3. Dependent Services of a Workspace

A workspace typically pairs with other Azure resources:

| Service | Common Role | Operational Notes |
|---|---|---|
| **Azure Storage** | Holds data, job snapshots, artifacts, or default datastore per config | RBAC, firewalls, networking, retention, storage costs |
| **Azure Key Vault** | Manages secrets and sensitive configuration | Least privilege, auditing, rotation |
| **Application Insights / Azure Monitor** | Telemetry and diagnostics per capability | Log retention, sensitive data, costs |
| **Azure Container Registry** | Container images for environments/jobs/endpoints as required | Registry access, image security, data transfer |
| **Microsoft Entra ID** | User, service, and workload identities | RBAC, managed identity, token lifetimes |
| **VNet / Private Endpoint** | Private connectivity and restricted access paths when configured | DNS, outbound dependencies, firewalls |

**Do not assume ACR is always provisioned immediately when a workspace is created.** In Azure ML workflows, a container registry may be created or required only when building images, depending on workspace configuration and lifecycle.

### Does Creating a Workspace Cost Money?

Billing rules depend on Azure ML and its associated services. **Jobs, compute, storage, registries, networking, and logs** are the common cost drivers; never assume an "empty workspace is strictly free," as linked resources can still incur charges.

## 4. Workspace and Azure ML Studio

**Azure ML Studio** is the web interface to:

1. Inspect the workspace and its configuration.
2. Manage compute instances and clusters.
3. Create, register, and inspect data assets.
4. Author and run jobs, pipelines, or AutoML.
5. View experiments, logs, metrics, and outputs.
6. Manage models, endpoints, and other components per permissions.

~~~text
Azure Portal
  -> Azure ML workspace resource
     -> Launch Studio
        -> Data
        -> Compute
        -> Jobs / Experiments
        -> Models / Endpoints
~~~

Menu names and layout can change. **Studio is an operational UI**, not a compute instance that runs notebooks on its own. Running notebooks still requires a compute session, compute instance, or supported execution compute.

### Separating Read vs. Run Permissions

Someone may be allowed to view job logs without permission to create compute, or submit jobs without permission to read source storage. Check both **Azure ML workspace permissions** and **data-source permissions**.

## 5. What Does Compute Mean in Azure ML?

**Compute** provides processing power to run notebooks, training jobs, batch inference, or ML workloads. Clarify whether users need:

- An interactive development environment.
- Autoscaling infrastructure for queued jobs.
- GPU training.
- Short periodic jobs.
- Attached compute resources outside the workspace.
- Online inference serving via dedicated endpoint mechanisms.

~~~text
Data scientist
    |
    +--> Compute instance: exploration, authoring notebooks, debugging
    |
    +--> AML compute cluster: queued training jobs
    |          |
    |          +--> CPU nodes
    |          +--> GPU nodes (if needed)
    |
    +--> Other supported compute targets / inference
               |
               +--> Depends on workload type and service capabilities
~~~

**Do not treat all compute as identical VMs with the same lifecycle.** Compute instances, AML compute clusters, and managed online endpoints differ in provisioning, autoscaling, and billing.

## 6. Compute Instance: Interactive Development Environment

A **compute instance** is managed compute for interactive work: notebooks, terminals, code prep, small tests, or debugging inside a workspace.

### Appropriate Scenario

A data scientist wants to test pandas/scikit-learn, inspect a few thousand rows, prototype feature transformations, and verify scripts before submitting a job to a cluster.

~~~text
User -> Azure ML Studio -> Compute instance
                              |
                              +-- Jupyter/terminal
                              +-- Edit code
                              +-- Debug on sample
                              +-- Submit remote job
~~~

### Key Points to Remember

- A compute instance is typically assigned to an individual or specific access config.
- While **Running**, compute accrues charges even when no notebook is actively executing.
- **Stop** instances when idle; configure auto-shutdown/idle schedules where supported.
- Store important code and data in proper repositories (Git, Storage, data assets)—**never rely on an instance's local disk as the sole backup**.
- Choose an appropriate SKU; exploratory notebooks rarely need expensive GPUs.
- A compute instance's user/identity permissions do not automatically grant access to every datastore.

### Does "Stop Instance" Delete Data?

Stopping and deleting have different semantics. Even so, **never treat a compute instance disk as a source of truth**, as lifecycle, backups, and retention require explicit design. Back up local changes and data before deleting any instance.

## 7. AML Compute Cluster: On-Demand Job Execution

An **AML compute cluster (AmlCompute)** runs training and batch jobs, configured with minimum and maximum node counts to process queued workloads.

~~~text
Job A ---------\
Job B ----------> Azure ML scheduler -> AML Compute Cluster
Job C ---------/                            |
                                             +-- Node 1
                                             +-- Node 2
                                             +-- ... up to max nodes
                                             |
                                    Idle -> scale down to min nodes
~~~

### When to Use It?

- Training models repeatedly across datasets or versions.
- Periodic batch scoring.
- Hyperparameter sweeps or pipeline steps.
- GPU training decoupled from personal notebooks.
- Workloads that can wait in a job queue to optimize resource costs.

### Core Configuration Settings

- **VM size:** CPU/GPU, memory, networking, regional availability.
- **Min instances:** baseline node count kept warm.
- **Max instances:** upper cap on scale and spend.
- **Idle scale-down delay:** wait window before scaling down idle nodes.
- **Priority/tier:** dedicated vs. low-priority/spot depending on cluster type and support.
- **Identity/network settings:** managed identity, VNet/isolation, and data access.

Setting **`min_instances = 0`** lets the cluster scale down to zero when idle, though it **does not zero out storage/network/log costs**, and new jobs wait for node provisioning.

## 8. Comparing Compute Instances and Compute Clusters

| Criterion | Compute Instance | AML Compute Cluster |
|---|---|---|
| Primary purpose | Interactive development | Running training and batch jobs |
| Usage pattern | Usually personal workflow | Shared via job scheduler and workspace policy |
| Autoscaling | Stop/start manually or by idle schedule | Scales between min/max nodes by queue demand |
| Idle cost | Charges continue while running | Can scale to 0 when `min=0` |
| GPU | Select GPU SKU if supported/quota allows | GPU compute nodes subject to quota |
| Code storage | Interactive/local filesystem | Job code snapshot/mount/download and outputs |
| Job reproducibility | Easy to ad-hoc tweak; less standardized unless versioned | Built for jobs tracking code/env/data versions |
| Risks | Forgetting to stop; unsaved local files | Queue/provisioning delays, VM quotas, node preemptions |

**A compute instance is not the default choice for 24/7 recurring production workloads**; use job schedulers/compute clusters or appropriate inference endpoints instead.

## 9. CPU vs. GPU: Choosing by Workload

| Workload | Starting Resource to Evaluate | Notes |
|---|---|---|
| Small data cleaning / pandas | CPU + sufficient RAM | Optimize memory usage first |
| Basic scikit-learn | CPU | GPUs add no automatic speedup |
| NLP/CV deep learning | GPU matching framework | Check CUDA/drivers, VRAM, quotas, and price |
| Small batch scoring | CPU | Measure provisioning time vs. throughput |
| Distributed training | Multi-node / multi-GPU as supported | Check networking and distributed config |
| Large-scale feature engineering | High-RAM CPU or Spark per scale | Do not confuse large tabular files with needing GPUs |

### Common Constraints

- Azure VM family unavailable in your selected region or subscription.
- GPU quota not yet allocated even though the UI lists the SKU.
- Insufficient **regional vCPU quota** or **AML compute quota**.
- Temporary regional capacity shortages.
- Container environment lacks matching CUDA/framework compatibility.

**Do not buy a massive GPU to fix a CSV schema parsing bug.** Diagnose code and data before scaling hardware.

## 10. Dedicated vs. Low-Priority / Spot Compute

Some AML compute cluster configurations support low-priority/spot VMs to cut costs at the risk of capacity preemption.

### Dedicated

- Suited for jobs requiring higher stability.
- Typically priced higher than equivalent spot capacity.
- Still subject to hardware faults, quotas, and retries—jobs are never immortal.

### Low-Priority / Spot

- Cost-effective for interruptible batch workloads.
- Nodes can be preempted or evicted.
- Jobs require checkpoints, retries, and idempotency.
- Unsuitable for strict completion SLAs without fallback capacity.

### Long Training Example

~~~text
8-hour training run; Spot node evicted at hour 6.

Without checkpoints:
  May have to restart training from scratch.

With periodic checkpoints:
  Resume from saved state
  if the framework and job logic support it.
~~~

Never assume every job or framework restores checkpoints automatically just because Spot is selected. **Checkpoints must be written to durable storage and your code must explicitly support resuming.**

## 11. Data Assets: Named, Typed, Versioned Data

A **data asset** in Azure ML v2 is a metadata resource referencing data, carrying:

- **`name`**: reusable name across jobs.
- **`version`**: explicit version identifier.
- **`type`**: e.g., **`uri_file`**, **`uri_folder`**, **`mltable`**.
- **`path`**: data location (local upload, datastore URI, or supported source).
- **`description`/`tags`**: description, owner, business labels.

~~~text
Azure Blob / ADLS data:
  training/churn/2026-11/part-*.parquet
                |
                v
Azure ML Data asset:
  name: churn_train
  version: 3
  type: uri_folder
  path: azureml://datastores/.../paths/...
                |
                v
Training Job:
  input: azureml:churn_train:3
~~~

A data asset manages a **named, versioned reference**; it does not mean the data is automatically copied into a separate database inside the workspace.

### Data Asset vs. Generic "Dataset"

"Dataset" can mean any collection of records. A "data asset" in Azure ML v2 is a **managed reference object pointing to a data source**. When older documentation mentions **Dataset v1**, never copy v1 creation commands into SDK v2.

## 12. How Do Datastores and Data Assets Differ?

| Criterion | Datastore | Data Asset |
|---|---|---|
| Role | Declares a connection to supported storage | Declares specific named/versioned data |
| Examples | Azure Blob container, ADLS Gen2 path, supported stores | Training CSV, image folder, MLTable |
| Information | Storage location and auth/connection settings | Name, version, type, path, metadata |
| Reuse scope | Many datasets share one storage location | One specific dataset reused across many jobs |
| Security | Identity/credentials/networking to storage | Asset metadata permissions plus underlying data access |
| Relationship | Supplies the place where data lives | Typically points to a path inside a datastore |

### Distinguishing via Example

~~~text
Datastore:
  team-adls
  -> Curated Azure Data Lake Storage Gen2 container

Data assets:
  churn_features:1
  -> team-adls/churn/2026-10

  churn_features:2
  -> team-adls/churn/2026-11
~~~

**Creating a datastore or data asset does not automatically grant every compute identity read access to storage.** Always check RBAC, ACLs, firewalls, Private Endpoints, and job authentication.

## 13. `URI_FILE`, `URI_FOLDER`, and `MLTABLE`

| Data Asset Type | Description | When to Use |
|---|---|---|
| **`uri_file`** | References a single file | Normalized CSV model input or single config file |
| **`uri_folder`** | References a folder or file set | Training images, partitioned Parquet files, batch inputs |
| **`mltable`** | Defines tabular data via an `MLTable` file and read/transform specs | Tabular datasets needing explicit path rules, filters, or loaders |

### URI File

~~~text
churn_train_csv:1
type: uri_file
path: azureml://datastores/teamblob/paths/churn/train.csv
~~~

### URI Folder

~~~text
product_images:2
type: uri_folder
path: azureml://datastores/teamblob/paths/images/train/
~~~

### MLTable

**MLTable** defines how to load tabular data from file paths and can specify supported transformations. An **`MLTable` definition file** and source data must exist at a valid location; merely naming a folder "mltable" does not make Azure ML guess the schema.

## 14. Data Versioning and Reproducibility

Suppose October training uses a 100,000-customer snapshot, and November grows to 110,000 customers.

~~~text
Data asset: churn_train:1 -> snapshot/2026-10
Data asset: churn_train:2 -> snapshot/2026-11

Job run-001:
  data = churn_train:1
  environment = churn-sklearn:1
  code = commit abc123

Job run-002:
  data = churn_train:2
  environment = churn-sklearn:1
  code = commit def456
~~~

### Does a Data Asset Version Make Underlying Data Immutable?

**Metadata versioning and storage bytes are two separate things.** An asset pointing to a mutable path where files can be overwritten may yield different data for the same version at two points in time unless backed by immutable snapshots or versioned storage.

For reproducibility:

1. Freeze or copy input datasets into **immutable/versioned paths** per policy.
2. Pin explicit data asset versions rather than relying solely on `latest`.
3. Record **code commit hashes**, environment images/dependencies, and parameters.
4. Record metrics, job IDs, output/model versions, and label provenance.
5. Verify permissions and retention so data remains accessible for audits.

**A `latest` alias** is handy during development yet can shift versions; never rely on it as an immutable audit reference for production runs.

## 15. Data Assets vs. Direct Paths

A job can accept a direct storage path or a data asset reference depending on SDK/API. Both have trade-offs:

| Characteristic | Direct Path | Versioned Data Asset |
|---|---|---|
| Quick start | Convenient for quick experiments | Requires registering the asset |
| Reusability | Tied to raw path strings | Explicit name/version |
| Metadata/description | Minimal standardization | Managed cleanly with the asset |
| Reproducibility | Must enforce path immutability manually | Better reference tracking; bytes still need protection |
| Governance | Requires external tracking for ownership | Assets help teams discover and govern data |

You do not need a registered data asset for every temporary intermediate file, yet **important training and evaluation datasets** should have explicit versioning, lineage, and permissions.

## 16. Input Access Modes: Download, Mount, Direct

Azure ML jobs support different ways of delivering data to compute, depending on asset type, compute target, and SDK:

- **Download:** copies data to local compute disk before/during the job.
- **Read-only mount:** exposes a virtual/mounted filesystem path read on demand.
- **Direct:** passes the reference URI so job code reads directly via supported clients.

~~~text
Azure storage ----download----> Local disk on compute
              \
               \---read-only mount---> Filesystem path at runtime
                \
                 \---direct URI------> Application-specific reader
~~~

### Choosing Mode by Workload

| Scenario | Approach to Evaluate |
|---|---|
| Small dataset read repeatedly | Download is often efficient |
| Large dataset read partially | Mount avoids copying everything upfront |
| Spark/SDK reading storage URIs directly | Direct mode when supported and configured |
| Private data source | Verify identity, firewalls, routing, and credentials |
| Offline job needing local files | Download or verified caching mechanism |

**Do not assume every data asset type supports all three modes.** `MLTable` has its own capabilities, modes, and reader APIs; storage connectivity and compute networking must be compatible.

## 17. Jobs in Azure ML v2

A **command job** is a declarative execution unit specifying everything Azure ML needs to schedule, run, and track it.

~~~text
Job:
  code: train.py with source directory
  command: python train.py --data <input-path>
  environment: image + Python dependencies
  compute: cpu-cluster-lab
  inputs:
    training_data -> churn_train:3
  outputs:
    model_output -> artifacts directory
  experiment_name: churn-training
~~~

### Five Questions Before Submitting a Job

1. Which **code** directory is snapshotted or referenced?
2. Which **environment** supplies the exact Python, packages, and CUDA versions?
3. Does the **input** point to the right data asset version with storage access?
4. Does the **compute** have quota, network reachability, and capacity?
5. Where are **outputs** persisted, and is model registration/auditing needed?

Never confuse **successful job submission** with a **successfully trained model**. A job progresses through states such as queued, preparing, running, failed, canceled, or completed.

## 18. Environments: Packaging Job Software

A job needs more than a Python script: Python version, libraries, container image, and frameworks must align. An **Azure ML environment** declares the image and dependencies so teams do not rely on whatever packages happened to be installed on a laptop.

~~~text
Code commit abc123
    + Data asset churn_train:1
    + Environment sklearn-lab:1
    + Compute cpu-churn-lab
                 |
                 v
             Training job
                 |
                 v
        Metrics + model artifacts
~~~

| Environment Choice | Pros | Trade-Offs |
|---|---|---|
| **Curated environment** | Fast start with Azure-provided reference configs | Must verify tags/versions and compatibility |
| **Custom environment** | Full control over image and dependencies | Requires build effort and security patching |

Never embed secrets in images. Pin dependencies for reproducibility while maintaining a CVE patching cadence. **The `latest` tag is not immutable**, so production should pin image digests/versions and schedule controlled upgrades.

## 19. Separating Management, Job Submission, and Data Access Permissions

| Activity | Permission Layer Involved |
|---|---|
| Create workspace, edit networking | Azure management plane / RBAC |
| Submit jobs, edit data/model assets | Azure ML workspace permissions |
| Read CSVs in ADLS/Blob | Storage data-plane RBAC/ACLs or appropriate credentials |
| Pull containers from ACR | Registry pull permissions/identity |
| Read Key Vault secrets | Key Vault data-plane permissions |
| Call model endpoints | Endpoint authentication/authorization |

**Having Azure ML Contributor does not automatically grant Storage Blob Data Reader on every storage account.** Identify the exact principal reading data inside the job: user identity, compute managed identity, or configured datastore credentials.

## 20. Python SDK v2: Connecting Safely to a Workspace

In a dedicated Python lab project, install the SDK:

~~~bash
python -m pip install azure-ai-ml azure-identity
~~~

Once provisioned with a workspace and identity:

~~~python
import os
from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential

ml_client = MLClient(
    credential=DefaultAzureCredential(),
    subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
    resource_group_name=os.environ["AZURE_RESOURCE_GROUP"],
    workspace_name=os.environ["AZURE_ML_WORKSPACE"],
)

workspace = ml_client.workspaces.get(
    os.environ["AZURE_ML_WORKSPACE"]
)
print({"name": workspace.name, "location": workspace.location})
~~~

This performs a **read-only configuration check**. `DefaultAzureCredential` does not grant permissions on its own; local developer identities and production managed identities may be **two different principals**. Never embed client secrets or tokens in source code, logs, or shared notebooks.

## 21. Azure CLI v2: Inspecting Workspaces, Compute, and Data

Azure ML v2 uses the Azure CLI **`ml`** extension. The commands below only read Azure resources; install the extension per official documentation if missing locally.

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --query "{id:id,name:name,tenantId:tenantId}" -o json

az ml workspace show \
  --name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o json

az ml compute list \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o table

az ml data list \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o table

az ml data show \
  --name "churn_train" --version "1" \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o json

az ml datastore list \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o table

az ml job list \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o table
~~~

If `show` reports not found, first verify **subscription, resource group, workspace/asset name, version, and permissions**. Do not blindly create duplicate resources to work around naming errors.

## 22. Python SDK v2: Listing Current State Before Creating

~~~python
for compute in ml_client.compute.list():
    print({"name": compute.name, "type": compute.type})

for asset in ml_client.data.list():
    print({
        "name": asset.name,
        "version": asset.version,
        "type": asset.type,
    })
~~~

Listing existing assets prevents colliding with clusters or data assets used by other teams. **Matching names do not imply shared ownership**; `create_or_update` calls can overwrite existing resources if you don't inspect first.

## 23. Defining an AML Compute Cluster with SDK v2

Example describing a CPU cluster for a lab workspace:

~~~python
from azure.ai.ml.entities import AmlCompute

cluster = AmlCompute(
    name="cpu-churn-lab",
    size="STANDARD_DS3_V2",
    min_instances=0,
    max_instances=2,
    idle_time_before_scale_down=120,
)

# Run only on a LAB workspace after authorization:
# op = ml_client.compute.begin_create_or_update(cluster)
# op.result()
~~~

- **`size`** is an illustrative VM SKU; verify regional availability, quotas, and pricing.
- **`min_instances=0`** allows scaling to zero when idle under supported conditions, though storage/log/network charges still apply.
- **`max_instances=2`** caps scaling, without guaranteeing 2 nodes are always available immediately.
- **`idle_time_before_scale_down`** is an operational setting, not a promise of instant provisioning.
- **`begin_create_or_update`** mutates real Azure resources; it is commented out to prevent accidental runs.

Example YAML in a hands-on project:

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/amlCompute.schema.json
name: cpu-churn-lab
type: amlcompute
size: STANDARD_DS3_V2
min_instances: 0
max_instances: 2
idle_time_before_scale_down: 120
~~~

Once the operator prepares `cpu-cluster.yml` in the lab project with permissions:

~~~bash
# CREATE/UPDATE COMPUTE - run only in LAB.
az ml compute create --file cpu-cluster.yml \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab"
~~~

Never run create/update commands against production or an existing cluster name without confirming ownership and change windows.

## 24. Registering a Versioned `URI_FOLDER` Data Asset

Assume Azure ML already has a datastore **`teamblob`** containing **`churn/train/v1/`**.

~~~python
from azure.ai.ml.entities import Data
from azure.ai.ml.constants import AssetTypes

training_asset = Data(
    name="churn_train",
    version="1",
    type=AssetTypes.URI_FOLDER,
    path="azureml://datastores/teamblob/paths/churn/train/v1/",
    description="Churn synthetic dataset for lab",
    tags={"purpose": "lab", "sensitivity": "synthetic"},
)

# Write to Azure ML LAB only when authorized:
# registered = ml_client.data.create_or_update(training_asset)
~~~

**Prerequisites:** the datastore and source folder exist, the creator has asset management permissions, and the compute identity has data read permissions. Registering an asset **does not copy** datastore contents and does not lock files against overwrites.

### CLI Data Asset YAML

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/data.schema.json
name: churn_train
version: 1
type: uri_folder
description: Synthetic churn training data for lab
path: azureml://datastores/teamblob/paths/churn/train/v1/
tags:
  purpose: lab
~~~

~~~bash
# CREATE DATA ASSET - run only in LAB with prepared churn-data.yml.
az ml data create --file churn-data.yml \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab"
~~~

### When to Use `URI_FILE`?

If the dataset is a single **`train.csv`**, `uri_file` pointing directly to the file fits cleanly. If the script expects a directory and appends `train.csv` itself, use **`uri_folder`**. Input types must match what your script expects.

## 25. `MLTable` for Defining How to Read Tabular Data

`MLTable` is a data asset type describing tabular data via a definition file specifying paths and read/transformation steps.

~~~text
churn-mltable/
  MLTable
  data/
    part-0001.parquet
    part-0002.parquet
~~~

**Structural illustration**:

~~~yaml
paths:
  - pattern: ./data/*.parquet
transformations:
  - read_parquet:
      include_path_column: false
~~~

**Verify transformation syntax and variants against your actual MLTable schema and package version.** Never just rename an extension or tag an arbitrary CSV as `type=mltable`. The `MLTable` file, source data, access permissions, and versioned path must all exist.

### Choosing the Asset Type

| Need | Reference Type |
|---|---|
| Single CSV file | `uri_file` |
| Image folder or multiple files | `uri_folder` |
| Tabular data with declarative paths/reader | `mltable` |
| Querying a database directly | Code + connector/identity with a dedicated snapshot strategy |

## 26. Preparing Synthetic Data for the Lab

Create **`train.csv`** in your lab data folder—never use real customer records:

~~~csv
age,monthly_spend,support_tickets,churned
23,150,0,0
47,35,4,1
32,200,1,0
58,40,5,1
29,125,1,0
43,65,3,1
36,180,0,0
55,50,4,1
26,220,0,0
51,45,5,1
31,175,1,0
48,60,3,1
~~~

Columns **`age`, `monthly_spend`, `support_tickets`** are features; **`churned`** is the label. **12 rows are insufficient** to validate production ML quality: use them solely to prove the input → train → output pipeline.

### Protecting Real Datasets

Customer datasets from SQL or Cosmos DB must undergo PII classification, legal/consent verification, access restriction, retention policies, and label quality checks. A data scientist permitted to read anonymized extracts does not automatically have permission to query raw production tables.

## 27. Simple `train.py` Script

File **`src/train.py`** in the lab project:

~~~python
import argparse
import json
import os

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

parser = argparse.ArgumentParser()
parser.add_argument("--data-folder", required=True)
parser.add_argument("--output-dir", required=True)
args = parser.parse_args()

df = pd.read_csv(os.path.join(args.data_folder, "train.csv"))
features = ["age", "monthly_spend", "support_tickets"]
target = "churned"

if any(column not in df.columns for column in features + [target]):
    raise ValueError("Missing training columns")

df = df.dropna(subset=features + [target])
if len(df) < 10 or df[target].nunique() < 2:
    raise ValueError("Dataset too small or one-class only")

x_train, x_test, y_train, y_test = train_test_split(
    df[features], df[target],
    test_size=0.25, stratify=df[target], random_state=42,
)

model = LogisticRegression(max_iter=500, random_state=42)
model.fit(x_train, y_train)
accuracy = float(accuracy_score(y_test, model.predict(x_test)))

os.makedirs(args.output_dir, exist_ok=True)
joblib.dump(model, os.path.join(args.output_dir, "model.joblib"))
with open(
    os.path.join(args.output_dir, "metrics.json"),
    "w", encoding="utf-8",
) as file:
    json.dump({"test_accuracy": accuracy}, file, indent=2)

print({"rows": len(df), "test_accuracy": accuracy})
~~~

**Warning:** accuracy on 12 rows is meaningless for evaluating a real model; production requires validation/cross-validation, fairness, drift checks, and an independent test set. **Never deserialize `joblib`/`pickle` files from untrusted sources.** Examples create artifacts solely inside the lab job.

## 28. Declaring an Environment for a Command Job

File **`conda.yml`** in the lab project:

~~~yaml
name: churn-sklearn-lab
dependencies:
  - python=3.10
  - pip
  - pip:
      - pandas==2.2.3
      - scikit-learn==1.5.2
      - joblib==1.4.2
~~~

These versions are illustrative, not guaranteed to be the latest or vulnerability-free. Check CVEs, base images, and compatibility before production use.

~~~python
from azure.ai.ml.entities import Environment

environment = Environment(
    name="sklearn-churn-lab",
    version="1",
    image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest",
    conda_file="./conda.yml",
)

# CREATE/UPDATE ENVIRONMENT IN LAB WORKSPACE if authorized:
# ml_client.environments.create_or_update(environment)
~~~

**The `latest` image tag is mutable**; pick an organization-approved, security-scanned digest/tag for reproducibility. Building images requires appropriate network and registry permissions.

## 29. Defining a Command Job with SDK v2

The example below wires **`src/train.py`**, **`churn_train:1`**, the registered environment, and the lab cluster:

~~~python
from azure.ai.ml import Input, Output, command
from azure.ai.ml.constants import AssetTypes

training_input = Input(
    type=AssetTypes.URI_FOLDER,
    path="azureml:churn_train:1",
    mode="ro_mount",
)
model_output = Output(
    type=AssetTypes.URI_FOLDER,
    mode="rw_mount",
)

job = command(
    code="./src",
    command=(
        "python train.py "
        "--data-folder ${{inputs.training_data}} "
        "--output-dir ${{outputs.model_output}}"
    ),
    inputs={"training_data": training_input},
    outputs={"model_output": model_output},
    compute="cpu-churn-lab",
    environment="azureml:sklearn-churn-lab:1",
    experiment_name="churn-synthetic-lab",
    display_name="train-churn-v1",
)

# RUNS JOB ON AZURE AND MAY INCUR CHARGES:
# submitted = ml_client.jobs.create_or_update(job)
# print(submitted.name)
~~~

**Prerequisites before uncommenting submit:**

1. `./src` contains `train.py`.
2. Your Azure account has job submission permissions.
3. The compute cluster, environment, and data asset exist with matching names/versions.
4. The data asset folder contains `train.csv`.
5. The job identity can read Blob/ADLS inputs and write outputs.
6. The container image can be pulled and the environment builds cleanly.
7. GPUs are unnecessary for a tiny scikit-learn job; pick a CPU cluster to control cost.

**Do not replace command placeholder paths with local machine paths**: `${{...}}` expressions are resolved by the job engine at runtime.

## 30. Tracking Job Status, Logs, and Outputs

After submitting an authorized job in the lab:

~~~bash
az ml job show \
  --name "<JOB_NAME>" \
  --workspace-name "aml-churn-lab" \
  --resource-group "rg-ml-lab" -o json
~~~

~~~python
details = ml_client.jobs.get("<JOB_NAME>")
print({"name": details.name, "status": details.status})
~~~

In Studio, inspect:

- Job states: queued, preparing, running, completed, failed.
- Compute allocation and provisioning logs.
- Environment image build and dependency errors.
- Input mount/download diagnostics.
- Script stdout/stderr and `metrics.json`.
- Output artifact path and `model.joblib`.

**Job `Completed` does not mean the model is production-ready.** It only proves the technical run finished per the job runner; accuracy, fairness, security, and reliability must be evaluated separately.

## 31. Distinguishing Jobs, Experiments, Pipelines, and Models

| Concept | Purpose |
|---|---|
| **Job** | Single execution with code, environment, compute, inputs/outputs |
| **Experiment** | Logical grouping of runs/jobs for tracking trials |
| **Pipeline job** | Orchestrates multiple dependent steps/jobs |
| **Model asset** | Named, versioned model artifacts for governance |
| **Online endpoint** | Serves real-time inference requests/responses per endpoint type |
| **Batch endpoint** | Runs asynchronous batch inference per service capabilities |

A **data asset** is an input; a **model asset** is a managed output after training. Registering a model does not deploy an endpoint automatically, and having an endpoint does not mean drift or fairness is monitored automatically.

## 32. Model Lineage and Reproducibility

Every critical job should record:

~~~text
Data version + immutable storage snapshot
               |
               v
Code commit + job parameters
               |
               v
Environment version / image digest
               |
               v
Compute configuration / region
               |
               v
Job ID + logs + metrics + artifacts
               |
               v
Evaluation decision / model registration
~~~

**A data asset version does not automatically make storage bytes immutable.** If someone overwrites files at the same path, two runs using `churn_train:1` could read different bytes. Combine immutable paths/snapshots, retention, hashes, and Azure Storage access policies for auditability.

Even with `random_state` fixed, GPU kernels, library versions, multithreading, and algorithms can remain non-deterministic. Test reproducibility rather than assuming a seed guarantees it.

## 33. Compute Scheduling and Resource Sharing

A team might structure compute as:

~~~text
Development EDA       -> CPU compute instance
Daily CPU training    -> AML compute cluster (min=0)
Deep learning         -> GPU cluster with allocated quota
Batch model scoring   -> Appropriate cluster / batch endpoint
Online inference      -> Managed online endpoint or equivalent target
~~~

If Spark-style preprocessing jobs and GPU training contend unpredictably for capacity, queue times, costs, and access permissions become hard to govern. Separate compute when workloads differ in GPU/CPU needs, SLOs, or data permissions—never dump every job onto one shared cluster by default.

### Metrics for Tuning Clusters

- Queue wait time and node provisioning time.
- Node CPU/GPU utilization.
- Job success, failure, and retry rates.
- Total VM hours plus storage and network costs.
- Spot eviction and checkpoint recovery rates.
- Idle running hours on compute instances.

## 34. Quotas and Compute Allocation Failures

A job can fail to start even when the script is completely valid:

- VM family unavailable in the region.
- Insufficient GPU or vCPU quota.
- Compute cluster reached `max_instances`.
- Spot or dedicated capacity temporarily unavailable.
- Network cannot reach Storage or ACR.
- Identity lacks create/pull/read permissions.

### Troubleshooting Workflow

1. Confirm workspace region and VM SKU.
2. Read compute status and job scheduling errors.
3. Check Azure ML/VM family quotas and per-region limits.
4. Check autoscale min/max settings and node allocation.
5. Check Storage/ACR permissions if the job fails during preparation.
6. Request a quota increase via approved channels if genuinely short.
7. Evaluate alternate SKUs, regions, or off-peak scheduling where appropriate.

**Never respond to an authentication error by raising GPU quota**, or hack the job script to mask compute provisioning failures.

## 35. Managing Microsoft Entra ID and Managed Identity

In Azure ML, three identities can differ:

1. **Developer identity:** the user signing into Studio/CLI to create jobs and assets.
2. **Compute/workload identity:** the identity used by the job to access Storage, Key Vault, and registries per configuration.
3. **Source identity:** the datastore's service principal or credentials if connections do not use the job's identity.

~~~text
Developer (Microsoft Entra ID)
       |
       | Workspace RBAC: submit job
       v
Azure ML Workspace
       |
       | Scheduler starts job
       v
AML Compute identity
       |
       +-- Storage Blob Data Reader -> input data
       +-- Storage Blob Data Contributor -> outputs if needed
       +-- ACR pull rights -> environment image if needed
       +-- Key Vault secrets read -> only when strictly required
~~~

### Practical Least Privilege

- Developers do not need subscription-wide `Owner` to run jobs.
- Read-only training jobs do not need `Storage Blob Data Owner` across the entire storage account.
- Pipelines should read only approved containers/datasets.
- Separate dev/test/prod identities so lab workspaces can never reach production storage.
- Document resource IDs and principal IDs in runbooks—never tokens or passwords.
- When using user-identity passthrough or credentialed datastores, verify which principal actually performs data access.

**Azure management-plane RBAC alone does not govern all data access.** Azure Storage uses data-plane roles/ACLs, Key Vault enforces its own access model, and SQL sources require database permissions.

## 36. Datastore Credentials and Secrets Governance

Azure ML datastores support **identity-based access** or credential-based access depending on datastore type and SDK/feature. Prefer approaches that minimize static secrets.

| Access Method | Pros | Risks / What to Verify |
|---|---|---|
| **Managed identity / identity-based** | No account keys embedded in scripts | Roles/ACLs, auth flow, runtime identity, network |
| **Service principal** | Useful for automation | Certificate/secret expiry, least privilege, rotation |
| **Account key / SAS** | Compatible with many workflows | Secret exposure, overly broad scope, expiry, rotation |
| **External source credential** | Connects to supported external stores | Ownership, change control, log redaction |

### What Not to Do

- Never put Storage account keys in job YAML or notebook cell outputs.
- Never commit connection strings or SAS tokens to Git.
- Never grant a Compute Instance read access to every container out of convenience.
- Never wire a short-lived SAS token into a long-running production pipeline without renewal.
- Never print URIs containing SAS query parameters into logs or artifacts.

### What Role Does Key Vault Play?

Key Vault manages infrastructure and application secrets, yet **creating a workspace does not automatically grant every workspace user access to Key Vault secrets**. Use managed identities with tightly scoped roles/permissions, rotation, and auditing.

## 37. Network Isolation and Private Endpoints

An Azure ML workspace interacts with Storage, Key Vault, ACR, Compute, and endpoints across Azure networking. For enterprises requiring private connectivity:

~~~text
Developer / CI
      |
      v
Azure ML workspace control/API
      |
      v
Managed network / approved VNet path
      |
      +--> Compute instance / cluster
      |          |
      |          +--> Storage Private Endpoint
      |          +--> ACR access
      |          +--> Key Vault access
      |
      +--> Other approved destinations
~~~

**Managed virtual network / isolation mode**, private endpoints, outbound rules, and workspace public access are explicit architectural choices—not every workspace is private by default.

### Checklist

1. Which network isolation mode is configured on the workspace?
2. Does compute have outbound internet access, and is it genuinely needed?
3. Do Storage, ACR, and Key Vault have dedicated firewalls/private endpoints?
4. Do private DNS/FQDNs resolve accurately from compute nodes?
5. Where do container images and conda packages come from?
6. Do scripts need access to PyPI, Git, or external model registries?
7. Can users and CI reach Azure ML Studio/APIs from approved networks?
8. Do workspace and storage regions comply with data residency policies?

### Two Common Mistakes

**Mistake 1: private workspace, public storage.** Never claim data is fully isolated merely because the Azure ML workspace uses Private Link.

**Mistake 2: private compute fails to pull images.** Never disable all firewalls immediately; determine whether you need a private registry route, approved outbound rules, or prebuilt images.

### Debugging Network Issues

Separate layers: **DNS → TCP/routing → TLS → Identity/RBAC → Service API**. A Storage `403` can stem from either a firewall rule or a missing role; inspect diagnostics and the active principal rather than assuming an access key typo.

## 38. Workspaces and Compute Across Environments

Clearly separate workspaces by environment:

~~~text
Resource group ml-dev
  Workspace aml-dev
  Compute dev-cluster (CPU, low max nodes)
  Data: synthetic / approved samples

Resource group ml-test
  Workspace aml-test
  Compute test-cluster
  Data: sanitized staging snapshots

Resource group ml-prod
  Workspace aml-prod
  Compute prod-cluster
  Data: production with tight access controls
~~~

### Why Separate?

- Prevents running exploratory notebooks against sensitive production data.
- Isolates RBAC, networking, and compliance boundaries.
- Prevents experimental jobs from consuming production GPU quotas.
- Tracks costs cleanly by team and environment.
- Strengthens auditing and change control.

**Separating workspaces is not enough** if all workspaces share the same storage account/container with broad write permissions. Enforce data boundaries at both storage and identity layers.

### Sharing Assets Across Workspaces

Azure ML can manage assets across workspaces/registries depending on resource type and features. However, **registering a data asset in workspace A does not automatically grant workspace B read access to storage bytes**. Verify feature support, identities, sharing policies, and data residency upfront.

## 39. Selecting Data Sources for Training

An organization may store data across Azure SQL, Cosmos DB, Blob/ADLS, Event Hubs, and Microsoft Fabric.

| Source | Ingestion Path to Evaluate for Azure ML | Watch-Outs |
|---|---|---|
| **Azure SQL Database** | Export/snapshot to Blob/ADLS, or job code connector | Transactional load, snapshot consistency, SQL permissions |
| **Azure Cosmos DB** | Export/snapshot or supported connector/code | RU/s impact, partition keys, freshness, consent |
| **Azure Blob / ADLS** | Datastore + `URI_FILE`/`URI_FOLDER`/`MLTable` | RBAC/ACLs, private endpoints, versioned paths |
| **Azure Event Hubs** | Streaming pipeline to curated storage prior to training | Event ordering, consumer lag, deduplication, retention |
| **Microsoft Fabric / OneLake** | Export/approved integration or supported read path | Data permissions, copy vs. shortcut, formats, residency |
| **On-premises data** | Secure pipeline/gateway to staging storage | Compliance, PII, network/firewalls, lineage |

### Do Not Train Directly on Hot OLTP by Default

A training job scanning millions of rows can degrade live payment transactions. Usually it is safer to snapshot/curate data into ADLS/Blob or an analytical store, version it, and point Azure ML there. Snapshots must preserve **point-in-time feature/label alignment** to prevent data leakage.

## 40. Data Quality, Leakage, and Reproducibility

A job can succeed technically yet train on flawed data:

- Churn labels computed after the prediction timestamp.
- Features containing columns that directly leak future outcomes.
- Duplicate customer records spanning train and test splits.
- Sudden spikes in missing or invalid rows.
- One tenant's data accidentally mixed into another tenant's slice.
- Underlying source files mutated without changing the data asset version.

### Mandatory Pre-Training Checks

1. Validate schemas, dtypes, null rates, and value ranges.
2. Check duplicates and sample identifiers.
3. Enforce point-in-time validity between features and labels.
4. Split train/validation/test along proper entities such as customer ID or time.
5. Check class imbalance and cohort fairness where appropriate.
6. Record row counts, dataset hashes/versions, and data quality metrics.
7. Quarantine malformed rows instead of silently dropping them.

**Never throw more compute at label leakage.** If a model peeks at future information, sky-high offline accuracy will fail in production inference.

## 41. Tracking Metrics, Logs, and Observability

| Component | Metrics / Logs | Used For |
|---|---|---|
| **Workspace** | Job counts/statuses, asset changes, access events | Tracking activity and configuration drift |
| **Compute instance** | Running hours, CPU/RAM/GPU, idle time | Optimizing dev spend |
| **Cluster** | Node allocation, queue wait time, failures, utilization | Sizing and quota planning |
| **Environment** | Image build/pull errors, dependency faults | Diagnosing job setup failures |
| **Data** | Read errors, mount time, dataset size, schema quality | Spotting storage/format issues |
| **Training** | Loss, accuracy, AUC, elapsed time, checkpoints | Evaluating model quality |
| **Cost** | VM hours, storage/egress, networking/logs | TCO tracking |
| **Security** | Identity failures, anomalous access, secret exposure | Incident response |

Not all of these are **built-in Azure Monitor metrics**. Several—such as data quality, label drift, and checkpoint rates—require custom logging in job code or an MLOps framework.

### Safe Logging

~~~json
{
  "experiment": "churn-synthetic-lab",
  "dataAsset": "churn_train:1",
  "environment": "sklearn-churn-lab:1",
  "compute": "cpu-churn-lab",
  "rows": 12000,
  "trainDurationSeconds": 42,
  "testAccuracy": 0.81
}
~~~

This is an **illustrative mock log**, not output from the 12-row dataset. Never print raw customer rows, access tokens, SAS URLs, or full Key Vault responses into logs.

### Should You Look Only at Accuracy?

No. Churn prediction typically requires precision/recall, calibration, AUC, per-cohort error rates, and business impact. On a severely imbalanced dataset, a model hitting 90% accuracy might still miss most actual churners.

## 42. Cost: Where Do the Main Charges Come From?

An Azure ML solution incurs charges from:

- **Compute instance/cluster VM hours** (CPU/GPU, node count, idle time).
- **Storage** for datasets, model outputs, and workspace artifacts.
- **Container Registry / image builds**, per resource/config.
- **Networking / Private Endpoints / egress** during data movement.
- **Monitoring / Log Analytics / Application Insights** by ingestion and retention.
- **Managed online endpoints** or batch inference infrastructure.
- **External Azure sources** such as SQL, Cosmos DB, ADLS, and ETL compute.

### Rough Compute Cost Example

Suppose a training job uses:

~~~text
2-node CPU cluster
Each node runs 3 hours for the job

Total VM-node-hours:
  2 x 3 = 6 node-hours

Estimated compute cost:
  6 x hourly node rate in the target region
~~~

This excludes environment builds, node provisioning, data transfer, storage/logs, and supporting services. Never hard-code dollar amounts since Azure rates vary by region, SKU, and offer.

### Compute Instance Left Running

~~~text
Compute instance running 24 hours/day
Developer actively uses it 2 hours/day

Idle compute hours:
  22 hours/day (illustrative)
~~~

While an instance stays `Running`, compute charges keep ticking. Configure auto-shutdown/idle policies where supported and monitor actual usage; **never delete an instance before backing up needed code and assets**.

### Optimization Levers

1. Set cluster `min_instances = 0` when cold start is acceptable.
2. Enforce `max_instances`, quotas, and budgets.
3. Stop compute instances when idle; restrict GPU notebooks.
4. Use Spot for workloads with checkpointing and retries.
5. Trim input dataset size and avoid cross-region bulk copies.
6. Cache environment images sensibly and pin dependencies.
7. Tag resources by cost-center, team, and project.
8. Use Azure Cost Management budgets and alerts.

**Never cut costs by deleting outputs/metadata required for auditing.** Data/model lifecycle and retention are business governance decisions.

## 43. Lab A: Verifying Workspace, Compute, and Datastores

**Goal:** inspect existing resources using **read-only** tools. Do not create VMs, alter policies, or launch training.

### Preparation

- Subscription/resource group containing a lab Azure ML workspace.
- Developer identity with workspace read permissions.
- Azure CLI v2 `ml` extension or matching Python SDK.
- Plan ensuring no production data is exported.

### Steps

1. Confirm subscription via **`az account show`**.
2. Inspect workspace name and location via **`az ml workspace show`**.
3. List compute via **`az ml compute list`**, distinguishing instances from clusters.
4. List registered datastores via **`az ml datastore list`**.
5. List assets, names, and versions via **`az ml data list`**.
6. Pick a synthetic asset and inspect its URI/type via **`az ml data show`**.
7. Cross-reference the data asset path with the datastore and storage owner.
8. Inspect past jobs without downloading raw customer data.
9. Document any gaps: quotas, identity, networking, or missing datasets.

### PASS Criteria

| Item | Expectation |
|---|---|
| Workspace | Correct subscription, resource group, and location |
| Compute | Distinguishes instances vs. clusters and running vs. idle |
| Data asset | Identifies name, version, type, and source path |
| Datastore | Identifies storage target and credential/auth mode |
| Permissions | Does not expand RBAC unnecessarily |
| Networking | Does not attempt to bypass firewalls or Private Endpoints |
| Cost | Creates zero unintended VMs or jobs |

## 44. Lab B: Training Synthetic Data on a CPU Cluster

**Goal:** combine a workspace, compute cluster, data asset, and environment into a command job. Steps that **create resources or run jobs can incur charges**—execute only inside an approved lab workspace.

### Preparation

1. Hold asset/job/compute creation permissions (or have an admin pre-provision).
2. Lab Azure ML and storage accounts properly configured.
3. Cost estimate, `max_instances` cap, and idle scale-down verified.
4. Synthetic dataset **`train.csv`** from Section 26 ready.
5. Scripts **`src/train.py`** (Section 27) and **`conda.yml`** (Section 28) ready.
6. Permissions to read input data and write job artifacts.

### Procedure

1. Create or confirm **`cpu-churn-lab`** (CPU cluster min 0, max 2) after checking quotas.
2. Upload `train.csv` to an authorized lab datastore folder or create a data asset via an official local upload flow.
3. Register **`churn_train:1`** as `URI_FOLDER` pointing to the folder containing `train.csv`.
4. Register the **`sklearn-churn-lab:1`** environment with tested dependencies.
5. Define the command job from Section 29 and submit via SDK/Studio.
6. Watch the job transition through Queued / Preparing / Running.
7. Verify **`model.joblib`** and **`metrics.json`** appear in job outputs.
8. Record the job ID and versions, then re-run with identical data/env to verify repeatability.
9. Never label the model "production-ready" just because the script printed an accuracy number.
10. Stop personal compute instances, confirm the cluster scales back to 0 when idle, and check spend.

### Deliberate Failure Tests

- Intentionally point to a nonexistent asset version **in lab config only** to observe the lookup error.
- Test an input folder missing `train.csv` to distinguish job setup errors from script errors.
- Test missing storage permissions using a restricted lab identity **if approved**; never alter production permissions.
- Do not load-test GPUs, request quota increases, or touch customer data to complete this lab.

### Acceptance Criteria

| Criterion | PASS When |
|---|---|
| Scope | Lab resources only |
| Compute | Suitable CPU SKU with capped max nodes |
| Input | Explicitly versioned data asset with the right file |
| Environment | Image and dependencies pinned |
| Job | Completes with logs, metrics, and model artifact |
| Reproducibility | Job ID, data version, code, and env recorded |
| Security | Zero leaked secrets; proper permissions |
| Billing | VM hours, storage, and related costs accounted for |

## 45. Lab C: Read-Only Check on Data Asset Access

**Goal:** understand that viewing metadata does not equal permission to read underlying bytes.

~~~text
Developer: views data asset churn_train:1 metadata successfully
            |
            v
Compute job: attempts to read train.csv
            |
          /   \
   Permitted   Denied
       |           |
       v           v
   Train OK     403 / AccessDenied
~~~

Steps:

1. Inspect data asset metadata and note datastore/URI and type.
2. Identify which identity actually reads storage along the job path.
3. Check **`Storage Blob Data Reader`/ACLs** at the required scope.
4. Check storage firewalls, Private Endpoints, and DNS.
5. Run a quick test with an approved test job.
6. On failure, inspect Storage diagnostics and Azure ML job logs to isolate auth vs. network issues.

**Never respond by pasting a storage account key into Python code or granting subscription Owner.** Fix the exact principal and exact permission scope.

## 46. Case Study: Churn Prediction for a SaaS Platform

A SaaS platform on Azure runs:

- Azure SQL Database for transactions and subscriptions.
- Azure Cosmos DB for user interactions.
- ADLS Gen2 for curated historical data.
- 8 data scientists needing development notebooks.
- Nightly training runs, plus occasional GPUs for NLP.
- Data privacy rules banning PII in logs and forbidding ad-hoc production data experiments.
- Churn prediction API requiring low p95 latency (though this lesson focuses on the training setup).
- Finance team needing cost allocation by team and project.

### Tasks

1. Design workspaces/resource groups for dev/test/prod and justify separation.
2. Determine compute instances for 8 developers and how to curb idle VM spend.
3. Size the CPU training cluster min/max nodes.
4. Decide when a separate GPU cluster is justified.
5. Design the ADLS datastore and **`churn_train:1`**, **`churn_eval:1`** data assets.
6. Choose `URI_FOLDER`, `URI_FILE`, or `MLTABLE` for each source.
7. Explain how to version/snapshot sources immutably for reproducible jobs.
8. Select environments/dependencies and govern image security.
9. Design least-privilege identities for reading storage and writing outputs.
10. Explain why a successfully submitted Azure ML job can still fail with Storage `403`.
11. Diagram private networking to ADLS, ACR, and Key Vault.
12. Structure a training + independent evaluation job/pipeline.
13. Identify metrics beyond accuracy for a churn model.
14. Design budgets, tags, quotas, timeouts, and Spot checkpointing.
15. Distinguish model asset registration from online endpoint deployment.

### Solution Approach

~~~text
Azure SQL / Cosmos DB
       |
       v
Curated + privacy-approved data in ADLS
       |
       v
Datastore: team-adls
       |
       v
Data assets:
  churn_train:1
  churn_eval:1
       |
       +-- sklearn environment:1
       +-- CPU training cluster (min 0)
       |
       v
Azure ML command/pipeline job
       |
       +--> metrics + model artifact
       +--> evaluation/quality/security checks
       |
       v
Model registration / approval
       |
       v
Separate inference deployment process
~~~

This is a **reference architecture**. If data must stay in a specific region or the workspace requires private networking, datastore, compute, and identity designs must satisfy those constraints before training begins.

## 47. Common Error Diagnosis

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Cannot open Azure ML workspace | Wrong tenant/subscription or missing RBAC | Azure portal/resource ID, `az account` |
| Compute cluster won't allocate nodes | VM quota, SKU unavailable, policy/network | Region, quotas, compute status |
| Notebook slow after long idle | Compute instance stopped or env unready | Instance state and startup logs |
| Job stays `Queued` too long | Cluster `max_instances`, quota, or capacity shortage | Queue, node allocation, cluster config |
| Environment build fails | Base image, conda dependency, or ACR access | Build logs, registry, networking |
| Data asset visible, job fails with `403` | Job identity lacks storage permissions | Principal, RBAC/ACLs, firewall |
| Input mount timeout | Private DNS/network or storage access issue | Compute path, endpoints, URI |
| Script `FileNotFoundError` | `URI_FILE` vs. `URI_FOLDER`, missing `train.csv` | Input mode/path vs. script code |
| Job `Completed` yet no model saved | Script wrote to wrong output path | Job outputs, local vs. mounted dirs |
| Suspiciously high metrics | Label leakage or train/test overlap | Data validation and splits |
| Same data asset version yields different data | Underlying storage files overwritten | Snapshot immutability and hashes |
| GPU spend spiking | Compute instance left running or cluster `min > 0` | VM hours, auto-shutdown schedules |
| Job fails reaching PyPI | Network isolation / outbound rules | Build logs and network policies |
| CLI command not found | Missing or outdated `ml` extension | `az extension list` and CLI docs |
| Cannot read Key Vault secret | Missing Key Vault data-plane RBAC | Managed identity and vault access |
| Inference API not responding | Model not deployed or endpoint auth/network error | Endpoint settings (separate from job lifecycle) |

### Six-Step Investigation Process

1. **Scope:** right tenant, subscription, resource group, and workspace?
2. **Identity:** which user, job, compute, and data principals are active?
3. **Compute:** type, VM size, quota, scheduler, and node status?
4. **Data:** asset version/path, access mode, and underlying bytes present?
5. **Environment:** image, dependencies, ACR/network, and code snapshot?
6. **Outcome:** job logs, metrics, artifacts, business data quality, and cost?

Never delete a workspace, compute, or data asset just because the first job failed. Diagnose the exact layer and preserve logs for investigation.

## 48. Pre-Production Checklist

| Area | Question to Satisfy |
|---|---|
| Workspace | Are environments and resource ownership clearly defined? |
| Subscription | Are regions, policies, quotas, tags, and budgets approved? |
| Identity | Are Entra RBAC and data-plane permissions least-privilege? |
| Network | Are managed VNet/VNet, DNS, and Storage/ACR/Key Vault paths valid? |
| Compute instance | Does it have an owner, auto-stop schedule, and no sole local data? |
| Cluster | Are min/max nodes, SKU/quotas, scale-down, and concurrency sized? |
| GPU / Spot | Are framework compatibility, checkpoints, and preemption handled? |
| Datastore | Are storage location, credential mode, and lifecycle clear? |
| Data assets | Are name, version, type, path, and ownership documented? |
| Data integrity | Are source snapshots immutable with automated quality checks? |
| MLTable / URI | Does the input type match how the training script reads it? |
| Environment | Are images/dependencies pinned and security-scanned? |
| Job | Are code commits, parameters, inputs, and outputs logged? |
| Training evaluation | Is leakage prevented with independent validation/test sets? |
| Model | Are registry/approval separated from endpoint deployment? |
| Monitoring | Do alerts track logs, metrics, queue wait times, failures, and data quality? |
| Cost | Are VM hours, storage, ACR, networking, and logs measured? |
| DR / retention | Do data snapshots, artifacts, code, and restore plans exist? |
| MLOps | Are CI/CD, tests, approvals, rollbacks, and model owners clear? |
| Security | Are job logs, artifacts, and model outputs free of PII and secrets? |

## 49. Self-Check Questions

1. How does an Azure ML workspace differ from a resource group and a VM?
2. Which Azure services are commonly linked with a workspace?
3. Why does creating a workspace not mean a GPU is already running?
4. Is a compute instance better suited for interactive development or queued batch jobs?
5. What are the benefits and trade-offs of `min_instances=0` on an AML compute cluster?
6. When is Spot/low-priority compute appropriate?
7. Why might a GPU not help a small scikit-learn workload?
8. How do a datastore and a data asset differ in role and permissions?
9. Does a data asset version automatically make underlying storage bytes immutable?
10. How do `URI_FILE` and `URI_FOLDER` differ in the path a script receives?
11. What does an `MLTable` define, and which files does it require?
12. When are download, mount, and direct access modes appropriate?
13. Why can a data asset appear in Studio while a job still fails with Storage `403`?
14. What components make up a v2 command job?
15. What role does an environment play in reproducibility?
16. Why pin container images/dependencies while still patching CVEs?
17. Should Azure ML v1 Dataset and v2 data asset syntax ever be mixed?
18. Does running `az ml compute list` spin up a new compute VM?
19. What resources can `az ml compute create` modify?
20. Why must job name, code commit, and data version all be recorded?
21. Why does a `Completed` job not prove a model is production-ready?
22. How can data leakage and train/test overlap distort metrics?
23. Why export a snapshot from OLTP before running heavy training scans?
24. Does workspace admin RBAC automatically grant read access to ADLS data?
25. How does managed identity differ from a storage account key for secret management?
26. Which resource dependencies must be checked for Azure ML private networking?
27. Can an ACR pull failure stem from networking or identity?
28. Can a compute instance in the `Running` state incur charges with no active notebook?
29. Running a 2-node CPU cluster for 3 hours equals how many node-hours?
30. Why does inspecting only Azure ML workspace billing miss total TCO?
31. How do model registration and endpoint deployment differ?
32. Which signals should you check when a job stays `Queued` too long?
33. What principles guide separating dev, test, and prod workspaces?
34. Which metadata and artifacts are needed to reproduce a training job?
35. What are the three most critical steps to protect customer datasets?

## References

- Microsoft Learn — *What is Azure Machine Learning?*: https://learn.microsoft.com/azure/machine-learning/overview-what-is-azure-machine-learning?view=azureml-api-2
- Microsoft Learn — *Azure Machine Learning workspaces*: https://learn.microsoft.com/azure/machine-learning/concept-workspace?view=azureml-api-2
- Microsoft Learn — *Compute targets*: https://learn.microsoft.com/azure/machine-learning/concept-compute-target?view=azureml-api-2
- Microsoft Learn — *Create a compute instance*: https://learn.microsoft.com/azure/machine-learning/how-to-create-compute-instance?view=azureml-api-2
- Microsoft Learn — *Create an AML compute cluster*: https://learn.microsoft.com/azure/machine-learning/how-to-create-attach-compute-cluster?view=azureml-api-2
- Microsoft Learn — *Data in Azure Machine Learning*: https://learn.microsoft.com/azure/machine-learning/concept-data?view=azureml-api-2
- Microsoft Learn — *Create and manage data assets*: https://learn.microsoft.com/azure/machine-learning/how-to-create-data-assets?view=azureml-api-2
- Microsoft Learn — *Manage datastores*: https://learn.microsoft.com/azure/machine-learning/how-to-manage-datastores?view=azureml-api-2
- Microsoft Learn — *Train models with jobs*: https://learn.microsoft.com/azure/machine-learning/how-to-train-model?view=azureml-api-2
- Microsoft Learn — *Authentication for Azure Machine Learning*: https://learn.microsoft.com/azure/machine-learning/how-to-authenticate?view=azureml-api-2
- Microsoft Learn — *Secure workspace and networking*: https://learn.microsoft.com/azure/machine-learning/how-to-secure-workspace-vnet?view=azureml-api-2
- Microsoft Learn — *Private endpoint for workspaces*: https://learn.microsoft.com/azure/machine-learning/how-to-configure-private-link?view=azureml-api-2
- Microsoft Learn — *Azure ML CLI v2*: https://learn.microsoft.com/azure/machine-learning/how-to-configure-cli?view=azureml-api-2
- Microsoft Learn — *Manage quotas for Azure Machine Learning*: https://learn.microsoft.com/azure/machine-learning/how-to-manage-quotas?view=azureml-api-2
- Microsoft Learn — *Manage models in Azure Machine Learning*: https://learn.microsoft.com/azure/machine-learning/how-to-manage-models?view=azureml-api-2
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
