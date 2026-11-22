# Huấn luyện, đăng ký và triển khai mô hình trong Azure Machine Learning

Một doanh nghiệp muốn dự đoán khách hàng có nguy cơ ngừng sử dụng dịch vụ. Mô hình thử nghiệm trên laptop có kết quả tốt, nhưng nhóm kỹ thuật chưa biết **tập dữ liệu, phiên bản code và dependency nào** tạo ra mô hình; nếu một API production đưa ra dự đoán sai, không thể xác định model version đang chạy hay rollback. Khi mô hình cần huấn luyện lại, quy trình thủ công có thể dùng nhầm data, mất dấu các thử nghiệm và triển khai artifact khác với artifact đã được đánh giá.

**Azure Machine Learning (Azure ML)** là nền tảng giúp quản lý vòng đời ML trên Azure, từ **data assets, environments, compute, training jobs, experiment tracking, model assets** đến **online/batch deployments, monitoring và MLOps**. Quy trình sản xuất không chỉ có lệnh `model.fit()`. Nó cần **tái lập, kiểm tra, phê duyệt, triển khai, giám sát và khả năng thu hồi** một mô hình có version rõ ràng.

Bài thuộc chương **AI và học máy trên Azure**, module **CLOUD_PROVIDERS_AZURE**, gắn với kiến trúc Microsoft Azure từ subscription, resource group, Entra ID, mạng ảo, compute, storage đến bảo mật, giám sát và kiểm soát chi phí. Ví dụ sử dụng **Azure ML CLI/SDK v2** và mô hình scikit-learn phân loại Iris để người học hiểu toàn đường đi trước khi áp dụng cho dữ liệu doanh nghiệp.

> **Giới hạn:** tên schema Azure ML v2, phiên bản Python SDK/CLI, các môi trường container, compute SKU, vùng, quyền hỗ trợ và giá có thể thay đổi. Mã minh họa cần kiểm tra trong workspace lab đã được cấp quyền, không coi là lệnh production sẵn dùng. Đối với mô hình tạo sinh, còn có các yêu cầu đánh giá safety, prompt/grounding và triển khai chuyên biệt nằm ngoài ví dụ scikit-learn này.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vòng đời **dữ liệu → huấn luyện → đánh giá → đăng ký → triển khai → giám sát**.
2. Phân biệt Azure ML workspace, compute, data asset, datastore, environment, job, experiment, registry, endpoint và deployment.
3. Thiết kế train/validation/test để tránh leakage và chọn metrics gắn với nghiệp vụ.
4. Gửi command training job bằng YAML CLI v2 hoặc Python SDK v2, lưu model/metrics outputs.
5. Đọc logs/metrics và thực hiện **quality gate** trước khi đăng ký model.
6. Đăng ký artifact theo **model name/version** và lưu lineage.
7. Triển khai custom model vào managed online endpoint, tạo scoring script và kiểm tra inference contract.
8. Phân biệt online và batch endpoints; thiết kế blue/green rollout và rollback.
9. Bảo vệ training data, secrets và endpoint bằng Entra ID, RBAC, managed identity và private networking.
10. Lập kế hoạch MLOps, theo dõi drift/performance, xử lý sự cố và chi phí Azure ML.

## 2. Vòng đời end-to-end

~~~mermaid
flowchart LR
  DATA["SQL / ADLS / Cosmos DB"] --> ASSET["Versioned data asset"]
  ASSET --> TRAIN["Azure ML training job"]
  CODE["Code + environment + compute"] --> TRAIN
  TRAIN --> EVAL["Evaluation metrics / artifacts"]
  EVAL --> GATE{"Quality + security gate"}
  GATE -->|Pass| MODEL["Model asset name/version"]
  GATE -->|Fail| FIX["Sửa dữ liệu / mô hình"]
  MODEL --> DEPLOY["Online / Batch deployment"]
  DEPLOY --> OBS["Telemetry, drift, ground truth"]
  OBS --> RETRAIN["Retrain / review / rollback"]
  RETRAIN --> TRAIN
~~~

Mỗi mũi tên phải có đầu vào/đầu ra và người chịu trách nhiệm rõ. Việc training job có trạng thái **Completed** không tự chứng minh mô hình vượt qua đánh giá, còn một model asset đã đăng ký **không tự có quyền** triển khai production.

### Các ranh giới quan trọng

- **Management/control plane:** tạo workspace, compute, jobs, assets, endpoints, phân quyền.
- **Data plane:** training compute đọc dữ liệu, ghi artifacts, serving endpoint tiếp nhận requests.
- **Lineage:** xác định data snapshot, code commit, environment, hyperparameters, training job và model version.
- **Governance:** chính sách phê duyệt, rollback, retention, privacy, data residency, audit.

## 3. Những đối tượng trong Azure ML

| Thành phần | Chức năng | Ví dụ |
|---|---|---|
| **Workspace** | Ranh giới quản trị ML, metadata, assets, quyền | `mlw-commerce-lab` |
| **Experiment** | Nhóm các lần chạy theo một bài toán | `iris-classification` |
| **Job** | Một lần chạy huấn luyện/đánh giá có logs, status, outputs | `train-iris-001` |
| **Compute instance** | Máy phát triển tương tác/notebook | `ds-workstation` |
| **Compute cluster** | Compute phục vụ jobs, có autoscaling | `cpu-cluster` |
| **Environment** | Container image + dependencies/version | `iris-train-env:1` |
| **Datastore** | Kết nối tham chiếu storage nguồn/đích | ADLS Gen2 |
| **Data asset** | Dữ liệu được đặt tên/version/format | `customer-churn-data:4` |
| **Model asset** | Artifact đăng ký dưới name/version | `iris-logreg:1` |
| **Registry** | Không gian chia sẻ assets theo policy/tính năng | Model dùng chung nhóm |
| **Endpoint** | Địa chỉ logic phục vụ online/batch scoring | `iris-demo-endpoint` |
| **Deployment** | Model + code + env + compute dưới endpoint | `blue` và `green` |

Một **Azure ML model asset** khác file `.joblib` trên disk: asset là tài nguyên có identity/name/version/metadata và URI tới artifacts. **Environment asset** không phải mô hình; nó định nghĩa điều kiện để mã train/score chạy.

## 4. Bắt đầu từ yêu cầu nghiệp vụ

Bài toán churn prediction cần định nghĩa:

- **Prediction target:** khách hàng rời bỏ trong vòng 30 ngày tính từ thời điểm dự đoán.
- **Input availability:** chỉ dùng dữ liệu có trước thời điểm dự đoán.
- **Decision:** ưu tiên chăm sóc, không tự động đưa ra quyết định bất lợi không có kiểm soát.
- **Output:** probability/class, schema, model version và thời gian.
- **Service objective:** batch hoàn tất trước 06:00 hoặc online p95 latency cụ thể.
- **Business risk:** false positive gây liên hệ lãng phí; false negative bỏ sót khách hàng quan trọng.
- **Privacy/fairness:** dữ liệu nhạy cảm có được dùng không, cần human review không.

Chọn model có accuracy cao nhưng không đáp ứng inference latency, không thể kiểm toán hoặc gây sai lệch nhóm khách hàng **chưa phải mô hình production tốt**.

### Metrics theo loại bài toán

| Bài toán | Metrics thường dùng | Điểm cần lưu ý |
|---|---|---|
| Classification | Precision, recall, F1, ROC-AUC, PR-AUC, calibration | Class imbalance, threshold, cost of errors |
| Regression | MAE, RMSE, R², quantile errors | Outliers, drift theo segment |
| Ranking | NDCG, MAP, recall@k | Labels và feedback bias |
| Forecasting | WAPE, MAE, backtest error | Time leakage, horizon |
| Anomaly detection | Detection recall, false alert rate | Labels thường thiếu, human review |

Đánh giá **theo segment và business impact**; không dùng một con số accuracy làm điều kiện phát hành duy nhất.

## 5. Chia tập và tránh data leakage

**Leakage** xuất hiện khi model vô tình sử dụng thông tin “tương lai” hoặc thông tin từ tập đánh giá trong quá trình train.

Ví dụ:

- Dùng trường “đã chấm dứt hợp đồng” để dự đoán churn.
- Chuẩn hóa cả train và test rồi mới chia tập.
- Dữ liệu cùng một khách hàng vừa ở train vừa ở test khi muốn đánh giá tổng quát theo khách hàng.
- Split ngẫu nhiên dữ liệu theo thời gian, dẫn tới dùng thông tin sau ngày dự đoán để huấn luyện.
- Tune hyperparameters liên tục trên holdout test rồi coi đó là test độc lập.

### Quy tắc

- **Train set:** fit preprocessing và mô hình.
- **Validation set:** chọn hyperparameters, model family và threshold.
- **Test set:** đánh giá độc lập một lần cho ứng viên đã chọn; tránh tune lại theo kết quả test.
- **Time-series:** chia theo thời gian có horizon/embargo phù hợp.
- **Grouped records:** group split khi nhiều records cùng subject.
- **Feature transformations:** fit chỉ trên train, áp dụng sang validation/test/serving.

Ví dụ scikit-learn Iris sau dùng random stratified split vì đây là lab nhỏ độc lập; **không áp dụng máy móc cho churn thực tế**.

## 6. Data assets, datastores và immutable snapshots

Trong production, data asset giúp lưu tham chiếu theo name/version và type/format (ví dụ `uri_file`, `uri_folder`, `mltable` theo SDK v2).

~~~text
Data asset: churn-training-data:4
Source: ADLS curated/churn/snapshot_2026-11-20/
Schema: features-v7
Labels: churn within next 30d
Owner: Data Platform
Permissions: least privilege
Checksum/table commit: recorded
~~~

**Version của data asset không tự biến file bên dưới thành bất biến** nếu ai đó overwrite cùng storage path. Muốn tái lập, cần immutable snapshots/path, lake table version hoặc file manifest/hash và permission policy.

### Quyền data-plane

Người có Azure RBAC cho workspace vẫn có thể bị Storage 403 nếu identity của compute/job không có quyền **Storage Blob Data Reader** hoặc ADLS Gen2 ACL thích hợp. Private Endpoint chỉ là mạng, **không cấp authorization**.

## 7. Workspace và tài nguyên liên quan

~~~mermaid
flowchart TD
  ENTRA["Microsoft Entra ID + Azure RBAC"] --> WS["Azure ML Workspace"]
  WS --> STORE["Storage / Data Assets"]
  WS --> KV["Key Vault"]
  WS --> REG["Container Registry / Images"]
  WS --> COMP["Compute clusters/jobs"]
  WS --> EP["Online / Batch endpoints"]
  COMP --> MON["Azure Monitor / App Insights"]
  EP --> MON
~~~

Một workspace có thể liên kết Storage, Key Vault, Container Registry và Application Insights theo topology được hỗ trợ. Cần kiểm tra identities, subscriptions, policies, region và managed networking.

### Phân tách dev/staging/prod

- **Dev:** thử nghiệm linh hoạt, dữ liệu nhỏ/ẩn danh, giới hạn compute.
- **Staging:** test deployment, security, load, feature contract, migration.
- **Prod:** model đã approved, access hạn chế, autoscale/alerts/rollback runbook.

Dùng **managed identity hoặc federated identity** cho automation và giữ secrets trong Key Vault/secret manager theo policy; không commit subscription credentials vào notebook.

## 8. Compute instance và compute cluster

**Compute instance** dành cho notebook/interactive development; chạy lâu có thể phát sinh phí. **AmlCompute cluster** dành cho jobs và có thể scale nodes theo cấu hình.

Ví dụ `compute.yml`:

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/amlCompute.schema.json
name: cpu-cluster
type: amlcompute
size: Standard_DS3_v2
min_instances: 0
max_instances: 2
idle_time_before_scale_down: 120
~~~

Tạo bằng CLI v2:

~~~bash
az ml compute create --file compute.yml
az ml compute show --name cpu-cluster
~~~

**Cẩn trọng:** SKU phải tồn tại và được quota/policy của subscription/region cho phép; tên property và khả năng autoscale theo schema hiện hành. `min_instances: 0` giúp giảm chi phí compute khi không chạy job nhưng không xóa storage, images hoặc monitoring charges.

Không mặc định GPU luôn tốt hơn CPU; với logistic regression/Iris, CPU thường đủ, GPU chỉ thêm chi phí và quota.

## 9. Environments: version hóa thư viện

Một môi trường huấn luyện cần có Python, scikit-learn và mã preprocessing tương thích. Bài lab dùng Python 3.10 và bộ dependency cố định để dễ tái lập.

### `conda-train.yml`

~~~yaml
name: iris-train
channels:
  - conda-forge
dependencies:
  - python=3.10
  - pip
  - pip:
      - scikit-learn==1.5.2
      - numpy==1.26.4
      - joblib==1.4.2
~~~

### `train-env.yml`

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: iris-train-env
version: "1"
image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
conda_file: ./conda-train.yml
description: "Training environment for Iris lab"
~~~

~~~bash
az ml environment create --file train-env.yml
az ml environment show --name iris-train-env --version 1
~~~

**Giới hạn của ví dụ:** container image `:latest` là tag dễ thay đổi; production phải pin image digest/tag được phê duyệt, scan vulnerabilities và kiểm tra compatibility. Các phiên bản thư viện dùng để minh họa **không phải khuyến nghị cập nhật mới nhất**. Với production, có thể dùng curated environments được Azure hỗ trợ hoặc custom image với dependency lock.

## 10. Project layout cho lab

~~~text
azureml-iris/
  compute.yml
  conda-train.yml
  train-env.yml
  src/
    train.py
  job.yml
  conda-infer.yml
  infer-env.yml
  score/
    score.py
  endpoint.yml
  deployment-blue.yml
  sample-request.json
~~~

Các file là phần của **bài thực hành người học có thể tạo trong workspace lab**; không phải file ngoài phạm vi bài học mà worker sẽ sinh trong repository.

## 11. Training code: scikit-learn classification

Iris có 150 mẫu, 4 features và 3 classes. Dataset được đóng gói trong scikit-learn, không chứa dữ liệu doanh nghiệp. Đoạn mã:

~~~python
# src/train.py
import argparse
import json
from pathlib import Path

import joblib
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--metrics_dir", required=True)
    args = parser.parse_args()

    iris = load_iris()
    X_train, X_test, y_train, y_test = train_test_split(
        iris.data,
        iris.target,
        test_size=0.2,
        stratify=iris.target,
        random_state=42,
    )

    # Scaler chỉ fit từ train để tránh leakage.
    model = Pipeline([
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(
            max_iter=500,
            random_state=42
        )),
    ])
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "f1_macro": float(f1_score(y_test, predictions, average="macro")),
        "confusion_matrix": confusion_matrix(
            y_test, predictions
        ).tolist(),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "classes": list(iris.target_names),
        "seed": 42
    }

    model_dir = Path(args.model_dir)
    metrics_dir = Path(args.metrics_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, model_dir / "model.joblib")
    (metrics_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "accuracy": metrics["accuracy"],
        "f1_macro": metrics["f1_macro"],
        "model_file": str(model_dir / "model.joblib")
    }))


if __name__ == "__main__":
    main()
~~~

Lưu ý:

- Sử dụng `Pipeline` để scaler và classifier đi cùng artifact, tránh serving skew.
- `random_state` cố định hỗ trợ tái lập; không bảo đảm tuyệt đối giữa mọi phần cứng/thư viện.
- Dataset bé nên metric dao động khi đổi split; production phải có validation/test design tốt hơn.
- `joblib` được dùng cho trusted artifacts, không load file từ người lạ.
- Hai outputs có thư mục riêng để dễ thu và audit.

## 12. Gửi command job bằng Azure ML CLI v2

Ví dụ `job.yml`:

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
code: ./src
command: >-
  python train.py
  --model_dir ${{outputs.model}}
  --metrics_dir ${{outputs.metrics}}
environment: azureml:iris-train-env:1
compute: azureml:cpu-cluster
experiment_name: iris-lab
display_name: train-iris-logreg
outputs:
  model:
    type: uri_folder
  metrics:
    type: uri_folder
~~~

Hai biểu thức `${{outputs.model}}` và `${{outputs.metrics}}` là **named output bindings của Azure ML CLI v2**, được dịch vụ ánh xạ thành các thư mục output của job lúc chạy; chúng không phải đường dẫn local hard-coded. Các lệnh CLI bên dưới giả định đã cấu hình workspace/resource-group defaults hoặc cung cấp các tham số workspace tương ứng. Trước khi thực thi, kiểm tra commandJob schema và CLI version hiện hành.

~~~bash
az ml job create --file job.yml
~~~

**Gửi job không có nghĩa job đã Completed.** Chờ job hoàn tất và xem logs/output:

~~~bash
JOB_NAME="<JOB_NAME_RETURNED_BY_CREATE>"

az ml job show --name "$JOB_NAME" --output json
az ml job stream --name "$JOB_NAME"
~~~

Nếu job thất bại vì container build, quota, Storage 403 hoặc code exception, không đăng ký model chỉ vì CLI trả về job ID.

### Cách đọc outputs

Job có named outputs `model` và `metrics`; trong output storage cần có `model.joblib` và `metrics.json`. Nếu code ghi ra `./model` nhưng job khai báo output ở path khác, registry sẽ không tìm thấy artifact cần thiết. Dùng **Azure ML output binding** để tránh lệch đường dẫn.

## 13. Python SDK v2: phương án tương đương

~~~python
from azure.ai.ml import MLClient, command, Output
from azure.ai.ml.constants import AssetTypes
from azure.identity import DefaultAzureCredential

ml_client = MLClient(
    DefaultAzureCredential(),
    subscription_id="<SUBSCRIPTION_ID>",
    resource_group_name="<RESOURCE_GROUP>",
    workspace_name="<WORKSPACE_NAME>",
)

job = command(
    code="./src",
    command=(
        "python train.py "
        "--model_dir ${{outputs.model}} "
        "--metrics_dir ${{outputs.metrics}}"
    ),
    environment="azureml:iris-train-env:1",
    compute="cpu-cluster",
    experiment_name="iris-lab",
    outputs={
        "model": Output(type=AssetTypes.URI_FOLDER),
        "metrics": Output(type=AssetTypes.URI_FOLDER),
    },
)

submitted = ml_client.jobs.create_or_update(job)
print("Training job:", submitted.name)
~~~

Tương tự YAML CLI, chuỗi `command` đã sử dụng **named output bindings** `${{outputs.model}}` và `${{outputs.metrics}}`. Trong lab, cần cài `azure-ai-ml`, `azure-identity` theo versions tương thích. `DefaultAzureCredential` lấy identity từ môi trường (developer identity hoặc workload/managed identity tùy cấu hình), không tự cấp quyền workspace/Storage.

### Khi nào CLI, SDK hay Studio?

- **YAML/CLI v2:** dễ review/cấp quyền qua CI/CD, khai báo tài nguyên.
- **SDK v2:** dễ lập trình tạo jobs, parameters, pipeline components.
- **Azure ML Studio:** trực quan để debug, xem job/metrics/compare models.
- **IaC:** quản trị subscription/workspace/network/policy một cách có kiểm soát.

Không trộn mã SDK v1 (ví dụ `ScriptRunConfig` theo workflow cũ) với SDK v2 mà không chuyển đối tượng/schema.

## 14. Training metrics, experiment tracking và MLflow

Một job nên ghi lại:

~~~text
Experiment = iris-lab
Training job = train-iris-001
Data asset or source snapshot = iris built-in
Code commit SHA = ...
Environment = iris-train-env:1
Compute = cpu-cluster / SKU
Hyperparameters = LogisticRegression(max_iter=500, seed=42)
Metrics = accuracy, f1_macro, confusion matrix
Artifacts = model/model.joblib, metrics/metrics.json
Start/end/status = ...
~~~

Azure ML có tích hợp **MLflow tracking** theo môi trường/SDK được hỗ trợ. Nếu đã cấu hình tracking URI và packages phù hợp, có thể log params/metrics:

~~~python
import mlflow

mlflow.log_param("model_family", "logistic_regression")
mlflow.log_param("random_state", 42)
mlflow.log_metric("accuracy", metrics["accuracy"])
mlflow.log_metric("f1_macro", metrics["f1_macro"])
~~~

Đoạn trên là fragment đặt trong quá trình train sau khi tính `metrics`, **không có tác dụng nếu không cấu hình MLflow/Azure ML integration đúng**. Một số môi trường cần package `azureml-mlflow`. Logging run artifacts và **đăng ký model asset để deploy** là những bước có thể kết nối nhưng không được đánh đồng.

## 15. Quality gate: Completed ≠ Approved

Ví dụ điều kiện lab:

~~~text
Training job status == Completed
model.joblib exists and can load
metrics.json exists and parseable
accuracy >= 0.85
f1_macro >= 0.80
model.predict smoke test passes
security + provenance checks pass
~~~

Những ngưỡng `0.85` và `0.80` chỉ minh họa. Đối với churn production, cần:

- Chọn model bằng validation set.
- So với **champion model**, không chỉ ngưỡng cố định.
- Kiểm tra class-specific precision/recall và business cost.
- Data leakage checks, segment fairness và calibration.
- Security/privacy review và approval theo rủi ro.
- Đảm bảo đúng **artifact được đánh giá** sẽ được đăng ký.
- Thử serialization/deserialization ở environment inference.

Nếu evaluation thất bại, chặn promotion. Một model có thể đạt accuracy nhưng vẫn không được phát hành vì PII, fairness hoặc endpoint latency.

## 16. Đăng ký model asset

Artifact train có thể nằm trong Azure ML job outputs. **Model registration** đặt tên và version để quản lý, deploy, rollback và audit:

~~~text
Name: iris-logreg
Version: 1
Type: custom_model
Path: exact approved training job output
Tags: owner, code commit, data version, experiment
Description: lab classification model
~~~

### Lấy URI từ job

~~~bash
az ml job show --name "$JOB_NAME" --query outputs --output json
~~~

Khi dùng named output `model`, URI thường có dạng tham chiếu job output:

~~~text
azureml://jobs/<JOB_NAME>/outputs/model
~~~

**Phải dùng output URI thực tế được dịch vụ chấp nhận**, không đoán tên trong mọi loại job hoặc model path. Nếu URI/SDK version khác, lấy kết quả job metadata hoặc sử dụng model asset path theo schema hiện hành.

### Tạo model asset bằng CLI

~~~bash
MODEL_OUTPUT_URI="azureml://jobs/<JOB_NAME>/outputs/model"

az ml model create \
  --name iris-logreg \
  --version 1 \
  --type custom_model \
  --path "$MODEL_OUTPUT_URI" \
  --description "Iris candidate from approved Azure ML training job"
~~~

Chỉ chạy sau khi job Completed và gate PASS. `<JOB_NAME>` là placeholder. Trong dự án thật, version không được âm thầm thay artifact bytes; tăng version và ghi provenance theo policy.

### Custom model và MLflow model

| Loại | Artifact | Triển khai |
|---|---|---|
| **custom_model** | Joblib/ONNX/PyTorch files hoặc thư mục artifacts | Thường cần scoring code và inference environment |
| **mlflow_model** | Cấu trúc MLflow flavor với metadata/signature | Có thể tận dụng khả năng MLflow deployment khi được hỗ trợ |

Không khai báo một file joblib đơn lẻ là `mlflow_model` nếu thư mục thiếu cấu trúc MLflow model hợp lệ.

## 17. Model lineage và governance

Một model version cần biết:

- Job và experiment tạo ra nó.
- Data version/snapshot, feature schema và label definition.
- Source commit, dependencies, image digest, hyperparameters.
- Evaluation metrics, class-wise results và test sample count.
- Model artifact hash/provenance và SBOM/container security khi phù hợp.
- Owner, approver, thời điểm đăng ký, chính sách retention.
- Các deployments đang dùng version đó và lịch sử traffic.
- Kịch bản rollback và người chịu trách nhiệm.

**Tags không phải cơ chế phê duyệt tự động.** Nếu bất cứ ai có quyền edit đều gắn `approved=true`, tag không bảo vệ production. Cần RBAC, approval gate ngoài code, immutable artifacts và audit.

### Lưu ý bảo mật của joblib

`joblib.load()`/pickle có thể chạy mã khi nạp dữ liệu không tin cậy. Chỉ load model artifacts từ pipeline và registry đáng tin; không cho user upload file tùy ý rồi gọi deserialization trong endpoint.

## 18. Online inference và batch inference khác nhau

| Thuộc tính | Managed online endpoint | Batch endpoint |
|---|---|---|
| Hình thức | HTTP request/response | Kích hoạt batch scoring job |
| Latency | Hướng tới thấp, yêu cầu SLO p95 | Minutes/hours tùy data volume |
| Tình huống | API phân loại ngay khi giao dịch | Chấm điểm hàng triệu khách hàng ban đêm |
| Compute | Serving deployment instances, có baseline cost | Job compute theo workload |
| Outputs | JSON prediction response | Files/tables ở destination |
| Thử version | Blue/green traffic, canary | Jobs/batch IDs/versioned outputs |
| Error handling | Timeout/429/5xx/schema errors | Retry, partial batch, idempotency |
| Giá | Compute có thể tính phí khi idle | Compute/job theo thời gian, storage |

Không nên tạo online endpoint chạy 24/7 cho một công việc batch chạy một lần mỗi tuần nếu không cần low-latency requests.

## 19. Scoring script cho managed online endpoint

Với `custom_model`, viết một script nhận JSON, kiểm tra features, dùng đúng preprocessing pipeline đã train và trả dự đoán.

### `score/score.py`

~~~python
import json
import os
from pathlib import Path

import joblib
import numpy as np

model = None


def init():
    global model
    model_root = Path(os.environ["AZUREML_MODEL_DIR"])
    model = joblib.load(model_root / "model.joblib")


def run(raw_data):
    if model is None:
        raise RuntimeError("Model is not initialized")

    request = json.loads(raw_data)
    rows = np.asarray(request["data"], dtype=float)

    if rows.ndim != 2 or rows.shape[1] != 4:
        raise ValueError("Expected 4 features per row")
    if rows.shape[0] < 1 or rows.shape[0] > 128:
        raise ValueError("Invalid batch size")
    if not np.isfinite(rows).all():
        raise ValueError("All features must be finite")

    labels = model.predict(rows)
    return {"predictions": labels.astype(int).tolist()}
~~~

**Tính minh họa:**

- `init()` load model khi scoring worker khởi tạo theo runtime.
- `run(raw_data)` nhận JSON body, dùng đúng 4 features.
- `AZUREML_MODEL_DIR` là thư mục artifacts được Azure ML runtime cung cấp theo deployment scheme; phải kiểm tra packaging thực tế khi endpoint khởi động.
- Không cho user chèn đường dẫn file model vào payload.
- Nên kiểm soát input shape, size, finite values và error mapping để không leak stack trace.
- Với tác vụ sensitive, log metadata/anonymized metrics, không log PII/raw payload.
- Scoring code không có authorization logic; endpoint auth/network vẫn phải cấu hình riêng.

### `sample-request.json`

~~~json
{
  "data": [
    [5.1, 3.5, 1.4, 0.2],
    [6.0, 2.2, 4.0, 1.0]
  ]
}
~~~

## 20. Environment cho inference

Inference cần tương thích scikit-learn/joblib với artifact, đồng thời có HTTP inference server package được hỗ trợ.

### `conda-infer.yml`

~~~yaml
name: iris-infer
channels:
  - conda-forge
dependencies:
  - python=3.10
  - pip
  - pip:
      - scikit-learn==1.5.2
      - numpy==1.26.4
      - joblib==1.4.2
      - azureml-inference-server-http
~~~

### `infer-env.yml`

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: iris-infer-env
version: "1"
image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
conda_file: ./conda-infer.yml
~~~

~~~bash
az ml environment create --file infer-env.yml
~~~

Production cần pin version của `azureml-inference-server-http` phù hợp Azure ML managed online endpoint, image/OS/security và kiểm tra build. Nếu dùng MLflow deployment/curated environment, packaging có thể khác. Không assume training env có thể phục vụ online không cần scoring server.

## 21. Tạo managed online endpoint

**Endpoint** là tài nguyên logical; **deployment** là sự kết hợp model + code + environment + compute thực hiện inference.

### `endpoint.yml`

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/managedOnlineEndpoint.schema.json
name: iris-lab-endpoint-unique
auth_mode: key
description: "Online endpoint cho Iris lab"
~~~

~~~bash
az ml online-endpoint create --file endpoint.yml
az ml online-endpoint show --name iris-lab-endpoint-unique
~~~

Chọn tên endpoint hợp lệ, không trùng trong phạm vi mà dịch vụ yêu cầu. `auth_mode: key` chỉ minh họa môi trường lab; với production đánh giá Entra token-based authentication theo khả năng endpoint hiện hành. Không in credentials/key trong logs hoặc code.

### `deployment-blue.yml`

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/managedOnlineDeployment.schema.json
name: blue
endpoint_name: iris-lab-endpoint-unique
model: azureml:iris-logreg:1
code_configuration:
  code: ./score
  scoring_script: score.py
environment: azureml:iris-infer-env:1
instance_type: Standard_DS3_v2
instance_count: 1
~~~

~~~bash
az ml online-deployment create \
  --file deployment-blue.yml \
  --all-traffic

az ml online-deployment show \
  --endpoint-name iris-lab-endpoint-unique \
  --name blue
~~~

**Cảnh báo:** `--all-traffic` đưa traffic hiện tại vào blue theo chế độ hỗ trợ; trên production có thể gây cutover ngoài ý muốn. Trong lab, không có user thật. VM SKU/quota, container build, network và model artifact path phải được kiểm tra trước. Một deployment có instance_count=1 có thể **tiếp tục tính phí khi không có requests**.

## 22. Invoke và kiểm tra contract

~~~bash
az ml online-endpoint invoke \
  --name iris-lab-endpoint-unique \
  --request-file sample-request.json
~~~

CLI invoke có thể dùng identity/credentials được quản trị trong client; **không tự suy rằng một ứng dụng production có thể gọi endpoint khi chưa thiết kế auth**.

### Kiểm thử tối thiểu

| Test | Mong muốn |
|---|---|
| Payload 4 numeric features | Predictions hợp schema |
| Thiếu `data` | Lỗi đầu vào rõ ràng, không lộ nội bộ |
| Sai số chiều hoặc Nan/Infinity | Không chấp nhận |
| Artifact không load được | Deployment unhealthy, logs đủ chẩn đoán |
| Request quá lớn | Bị giới hạn |
| Sai token/key | Access denied |
| Latency p95 qua tải lab | Đạt SLO đã đặt |
| Model version mới | Traceability tới version đang phục vụ |
| Endpoint chưa có deployment | Không nhận prediction như thể đã sẵn sàng |

Không đánh đồng HTTP 200 với **mô hình có chất lượng**. Dự đoán chính xác cần ground truth và metric phù hợp.

## 23. Blue/green, canary và rollback

~~~mermaid
flowchart LR
  C["Clients"] --> E["Managed online endpoint"]
  E -->|90%| B["Blue model v1"]
  E -->|10%| G["Green model v2"]
  B --> MON["Metrics, logs, quality"]
  G --> MON
  MON --> D{"Gates pass?"}
  D -->|Yes| RAMP["Increase green traffic"]
  D -->|No| ROLLBACK["Route back to blue"]
~~~

### Quy trình

1. Deploy green song song, chưa nhận production traffic.
2. Test green trực tiếp bằng mechanism được hỗ trợ, đủ schema/latency/auth.
3. Canary tỷ lệ thấp theo phê duyệt và risk level.
4. Theo dõi 5xx/429, p95/p99, resource usage, prediction distribution và business signals.
5. Nếu đạt, tăng traffic từ từ.
6. Nếu regression, chuyển traffic về blue trước khi điều tra dài hơn.
7. Giữ bản blue và artifact tương ứng đủ thời gian cho rollback.
8. Ghi deployment/version/approver/time và quyết định.

Ví dụ cấu hình tỷ lệ traffic ở mức khái niệm:

~~~yaml
traffic:
  blue: 90
  green: 10
~~~

Đây không phải toàn bộ endpoint YAML; áp dụng theo schema của endpoint. **Rollback traffic không hoàn tác những hành động nghiệp vụ** đã dựa trên prediction cũ. Với quyết định rủi ro cao cần decision logging, human review và remediation.

## 24. Batch endpoints và tác vụ offline scoring

Khi có 2 triệu khách hàng cần chấm điểm mỗi đêm, một **batch endpoint** phù hợp hơn online HTTP endpoint. Nó khởi động jobs, đọc inputs theo dữ liệu có version, ghi outputs và cho phép kiểm tra tình trạng xử lý.

~~~mermaid
flowchart LR
  DATA["ADLS input snapshot"] --> B["Azure ML batch endpoint"]
  B --> JOB["Batch scoring job"]
  JOB --> OUT["ADLS predictions staging"]
  OUT --> V["Validate/dedup/publish"]
  V --> BI["BI / campaign / app"]
~~~

Batch design cần:

- Batch ID cố định, input data version và model version.
- Mini-batch size/concurrency theo compute và model.
- Retry/checkpoint tránh nhân đôi predictions.
- Output schema, sample counts và failed records/quarantine.
- Data permissions và network routes trên compute.
- Deadline hoàn tất trước downstream consumption.
- Có thể scale compute xuống 0 sau job nếu cấu hình hỗ trợ.

Một batch endpoint invocation không đồng nghĩa toàn bộ batch đã hoàn tất; cần chờ job success và validate output. Không dùng online `run(raw_data)` nguyên xi cho mini-batch workload nếu batch scoring contract khác.

## 25. Pipeline jobs và tự động hóa workflow

Các bước thường được chia:

~~~text
Validate input snapshot
  -> Prepare / feature transform
  -> Train candidate
  -> Evaluate against champion
  -> Quality/security approval
  -> Register model
  -> Deploy staging
  -> Integration/load tests
  -> Promote/canary production
  -> Monitor/drift/retrain review
~~~

**Azure ML pipeline jobs** có thể dùng components và output bindings cho prepare/train/evaluate. Việc register/promotion cần gate: pipeline job Completed không tự mang nghĩa mọi chính sách bảo mật/đạo đức đã được phê duyệt.

### Tại sao component hóa?

- Tái sử dụng code/env cho nhiều runs.
- Khôi phục nhanh bước lỗi và so sánh outputs.
- Tái lập từ data snapshot và component versions.
- CI/CD dễ kiểm tra quality gates.
- Lineage giữa đầu vào và model artifact rõ.
- Phân quyền và kiểm toán từng stage.

Với retraining tự động, **drift alert chỉ nên mở quy trình đánh giá**, không mặc định tự triển khai mô hình mới thiếu xét duyệt.

## 26. Training-serving skew và feature contracts

Mô hình train với dữ liệu tiền xử lý một cách nhưng inference dùng quy tắc khác:

- Train dùng `total_spend_30d`, serving dùng `total_spend_7d`.
- Train quy đổi tiền về VND, API gửi USD.
- Train đọc giờ UTC, API dùng local timezone.
- Train bỏ đi giá trị null, API trả chuỗi `"null"`.
- Train dùng scaler fit từ train set, serving fit scaler mới.
- Thứ tự 4 features bị đổi.

Đây là **training-serving skew**, có thể khiến mô hình đưa ra kết quả sai dù không gặp exception.

Biện pháp:

1. Định nghĩa schema feature: tên, thứ tự, đơn vị, nullable, ranges.
2. Đóng gói preprocessing cùng model hoặc component phiên bản hóa đồng nhất.
3. Test cùng input trên offline evaluation và online serving.
4. Quản lý feature snapshots và drift ở data pipeline.
5. Chặn deployment có contract mismatch.
6. Dùng canary và theo dõi feature distributions.
7. Không lấy feature tương lai trong training.

## 27. Giám sát production: metrics, logs và chất lượng

Các tín hiệu cần theo dõi:

| Nhóm | Chỉ số |
|---|---|
| Endpoint health | Ready instances, request count, 5xx, timeout |
| SLO latency | p50/p95/p99, model load/startup |
| Inference errors | Input schema failures, auth failures, 429 |
| Data quality | Missing values, outlier ratio, ranges |
| Prediction distributions | Class/probability distribution theo thời gian |
| Actual model quality | F1, precision, recall, calibration với ground truth |
| Drift | Data drift, concept drift, model output drift |
| Fairness | Chất lượng/chênh lệch theo nhóm khi policy cho phép |
| Batch | Job status, input/output counts, freshness, failure rate |
| Cost | Training compute, online compute idle, storage/egress/logs |

**Data drift không đồng nghĩa model đã hỏng**; có thể do seasonality, thay đổi sản phẩm hoặc pipeline lỗi. **Prediction drift không phải ground truth**. Chỉ tính performance thực khi nhãn đáng tin đã xuất hiện, chú ý label delay và sampling bias.

### Alert nên có hành động

- Endpoint 5xx/p95 vượt baseline đủ lâu và đủ traffic.
- Model load errors khi khởi động deployment.
- Input schema mismatch tăng sau release.
- Model class-specific recall giảm trên ground truth.
- Batch deadline trễ, dữ liệu quá cũ, tỷ lệ records bị loại cao.
- Compute costs tăng bất thường hoặc endpoint idle kéo dài.
- Model drift vượt ngưỡng dẫn tới review có owner.

### Azure Monitor và Application Insights

Azure ML có thể tích hợp metrics, logs và diagnostic settings với **Azure Monitor, Application Insights và Log Analytics** theo tài nguyên/feature được hỗ trợ. Schema log table khác nhau theo export mode và resource; cần xác nhận table names thật trước khi viết KQL production, tránh tự tạo truy vấn với các cột không tồn tại.

Ví dụ log an toàn:

~~~json
{
  "timestampUtc": "2026-11-20T10:00:00Z",
  "endpoint": "iris-lab-endpoint-unique",
  "deployment": "blue",
  "modelVersion": "iris-logreg:1",
  "requestId": "example-001",
  "durationMs": 34,
  "featureSchema": "iris-v1",
  "status": "success"
}
~~~

Không log dữ liệu cá nhân/raw payload, tokens, keys hay feature values nhạy cảm trừ khi có chính sách pháp lý/consent và bảo vệ thích hợp.

## 28. Bảo mật: identity, network, registry

### Identity/RBAC

- **Microsoft Entra ID + Azure RBAC** cho workspace, jobs, assets và endpoints.
- **Managed identity** cho compute/deployment đọc Storage, Key Vault theo hỗ trợ.
- **Storage data-plane RBAC/ACL** riêng với workspace management.
- **Least privilege**: Data Scientist, ML Engineer, Approver, Security/Operator.
- **CI/CD federated identity/OIDC** nếu khả năng và policy hỗ trợ, tránh client secrets lâu dài.
- Online endpoint authentication theo mode; key/token không để trong source code.

### Network

- Kiểm tra private endpoint, VNet, DNS, NSG/Firewall, egress cho workspace, compute, model registry/Storage, container image và telemetry.
- Private Link không tự cấp role hoặc quyền đọc dữ liệu.
- Training compute không truy cập được package registry/image registry có thể gây build failure.
- Endpoint private có thể cần client network path (VPN/ExpressRoute) riêng.
- Hạn chế data egress cross-region theo policy và residency.

### Supply-chain risk

- Chỉ load `joblib`/pickle artifact từ pipeline đáng tin.
- Pin dependencies, scan base images/packages, verify provenance.
- Không dùng arbitrary user input làm đường dẫn model file hoặc lệnh shell.
- Có model rollback và quy trình revoke khi phát hiện data/model poisoning.
- Kiểm soát dataset licenses, PII, bias/fairness và retention.

## 29. CI/CD và MLOps promotion

~~~mermaid
flowchart TD
  PR["PR: code/env/data schema"] --> CHECK["Unit/data/security tests"]
  CHECK --> TRAIN["Azure ML train job"]
  TRAIN --> EVAL["Offline evaluation"]
  EVAL --> Q{"Gates pass?"}
  Q -->|No| BLOCK["Block promotion"]
  Q -->|Yes| REG["Register versioned asset"]
  REG --> STAGE["Staging deployment + load tests"]
  STAGE --> APP{"Approval?"}
  APP -->|No| BLOCK
  APP -->|Yes| CANARY["Canary green"]
  CANARY --> MON["Monitor SLO + quality"]
  MON -->|Regress| RB["Rollback blue"]
  MON -->|Pass| PROD["Scale traffic green"]
~~~

Để pipeline có thể kiểm toán:

1. Pipeline spec/code lưu trong Git, commit SHA ghi vào job.
2. Data snapshots có version và immutable/manifest.
3. Environment/container image có version và dependency lock.
4. Tests: unit, data schema, leakage, performance, security, serving contract.
5. Evaluation so champion và business risk thresholds.
6. Approval controls tránh developer tự promote model rủi ro cao.
7. Staging test auth/network/latency.
8. Canary/rollback chỉ ra model version cụ thể.
9. Audit decision records và downstream impact.
10. Retention/archival hỗ trợ reproducibility nhưng tuân thủ data deletion requests.

**Không mặc định có một tag `approved=true` là đủ**. Cần enforce bằng quyền và workflow, đặc biệt với mô hình ảnh hưởng con người.

## 30. Troubleshooting Azure ML training và deployment

| Triệu chứng | Nguyên nhân | Kiểm tra |
|---|---|---|
| Job queued lâu | Compute quota/region capacity/autoscale startup | Cluster size, quota, job state |
| Environment build failed | Image/network/dependency conflict | Build logs, pins, registry reachability |
| Input Storage 403 | Identity thiếu data-plane role/ACL | Managed identity, Storage ACL, DNS |
| Training đạt accuracy quá cao | Leakage, split sai, duplicated samples | Feature timing, holdout |
| Job Completed nhưng thiếu model | Sai output binding/path | Job outputs và file structure |
| Register model lỗi URI | Sai job name/output name hoặc output chưa có | Job metadata/actual URI |
| Deployment unhealthy | score.py import, model file missing, server env | Container/startup logs |
| Invoke 401/403 | Auth/key/token/network permission | Endpoint auth mode/RBAC |
| Invoke 400 | Input JSON schema/shape sai | Payload validation |
| Invoke 5xx | Scoring exception/OOM/downstream failure | Runtime logs và trace |
| Endpoint trả 200 nhưng dự đoán lệch | Feature skew, drift, artifact mismatch | Data contract, ground truth |
| Model mới chậm | VM quota/resources, batch size, code | Latency/CPU/memory profiling |
| Idle endpoint vẫn tốn tiền | Compute instances còn running | Deployment list/Cost Management |
| Batch predictions bị trùng | Retry không idempotent | Batch ID, staging/dedup |
| Không thấy Azure Monitor logs | Sai diagnostics/table | Destination/category/schema |

### Runbook sự cố inference

1. Lấy endpoint, deployment, model version, request time UTC và mức ảnh hưởng.
2. Kiểm tra auth, payload/schema, 4xx/5xx, p95 latency.
3. So sánh deployment mới với bản ổn định trước.
4. Xem logs khởi động, model path, environment/registry permissions.
5. Nếu canary regression, chuyển traffic về blue theo runbook.
6. Kiểm tra predictions đã được dùng trong quyết định nghiệp vụ, có cần remediation không.
7. Sửa lỗi, chạy integration tests và kiểm tra lại policy trước promote.
8. Ghi incident timeline, owner, preventive actions và chi phí.

## 31. Cost management

~~~text
ML platform cost =
  Compute instances + Training clusters/jobs
  + Image/environment builds
  + Model/data storage
  + Online deployment instances + network
  + Batch inference jobs
  + Logging/monitoring
  + Retraining/reprocessing/operational overhead
~~~

### Điểm dễ quên

- Notebook compute instance bật suốt đêm.
- Cluster `min_instances > 0` khi không có training jobs.
- Managed online endpoint có 1–2 serving instances luôn bật.
- Cả blue và green cùng giữ compute khi rollout dài ngày.
- GPU đắt nhưng model nhỏ chạy CPU đủ.
- Raw datasets/checkpoints/artifacts và logs không có retention.
- Cross-region data transfer và private networking resources.
- Drift alert kích hoạt retrain liên tục mà không có budget.

### Giải pháp

- Rightsize VM, scale-to-zero nơi phù hợp.
- Cài budget/quota và tags owner/cost center/environment.
- So sánh batch và online theo business latency.
- Chỉ chạy training theo lịch/hướng dẫn, không retrain vô hạn.
- Đo cost per **valid and useful prediction**, không chỉ compute giờ.
- Xóa **lab endpoint/deployment** khi kết thúc theo quyền được giao, không xóa workspace hoặc dữ liệu shared.
- Giữ artifact/version cần thiết cho rollback/audit theo retention.

Không dùng một đơn giá cố định vì giá phụ thuộc VM SKU, region, thời gian và billing model.

## 32. Case study: churn scoring hằng đêm

Một công ty SaaS có dữ liệu giao dịch trên Azure SQL và sự kiện trên ADLS Gen2. Mỗi ngày trước 06:00, bộ phận chăm sóc cần danh sách nguy cơ churn.

**Thiết kế:**

- ADF chuẩn bị dữ liệu và versioned snapshot.
- Azure ML training pipeline hằng tuần với time-based split, feature contract và metrics.
- Evaluation so với champion model, fairness/privacy review khi cần.
- Model asset v12 đã approved và deployment batch endpoint.
- Batch scoring ghi output theo batch ID vào ADLS staging.
- Data validation trước publish; retries idempotent.
- Job, dữ liệu và artifact lineage đầy đủ.
- SLO data freshness, cost và quality monitoring.

### Sự cố giả định

Team đổi feature `usage_30d` thành `usage_7d` ở pipeline nhưng code training không thay. Batch endpoint vẫn hoàn tất, output không lỗi kỹ thuật, nhưng prediction distribution dịch mạnh.

Quy trình:

1. Chặn publish khi feature contract không khớp.
2. Giữ dữ liệu approved trước hoặc thông báo dataset không sẵn sàng.
3. Sửa feature pipeline và test offline/online parity.
4. Chạy lại batch với cùng batch ID, không nhân đôi records.
5. Đánh giá ground-truth quality khi nhãn tới.
6. Thêm schema regression test trước CI/CD promotion.

## 33. Bài lab: từ Iris training đến endpoint invoke

> **An toàn:** chỉ sử dụng Azure ML workspace/resource group lab được phép, giới hạn ngân sách và quyền. Training/managed endpoint tạo compute tính phí. Bài mô tả các file người học có thể tạo, không yêu cầu thao tác với dữ liệu khách hàng thật.

### Phần A — Chuẩn bị

1. Xác nhận subscription/tenant với `az account show`.
2. Kiểm tra workspace và CLI extension `ml`.
3. Kiểm tra quota, VM SKU, network, Storage RBAC.
4. Tạo cấu trúc thư mục phần 10.
5. Tạo `compute.yml`, `conda-train.yml` và `train-env.yml`.
6. Tạo compute cluster và environment asset.

### Phần B — Training

1. Viết `src/train.py` với scaler trong Pipeline.
2. Viết `job.yml` và dùng output bindings đúng schema.
3. Gửi job, lấy job ID.
4. Xem job logs và kiểm tra trạng thái Completed.
5. Kiểm tra output model, metrics, confusion matrix.
6. Kiểm tra quality gate; nếu không đạt, không register.
7. Lưu data/code/environment/compute provenance.

### Phần C — Registry

1. Lấy URI thực của named output.
2. Tạo model asset `iris-logreg:1` loại `custom_model`.
3. Kiểm tra model path và tags/version.
4. Không overwrite artifact của version đã dùng.

### Phần D — Deployment

1. Tạo `score.py` và inference environment.
2. Tạo managed online endpoint lab.
3. Deploy blue với model v1.
4. Đợi endpoint/deployment Healthy.
5. Invoke `sample-request.json`.
6. Kiểm tra payload sai, auth sai, latency và model metadata.
7. Ghi p95/5xx và serving cost.
8. Đóng/xóa lab endpoint theo phê duyệt.

### Phần E — MLOps nâng cao

1. Train model candidate v2 bằng một thay đổi có lý do.
2. So offline quality và giữ holdout test độc lập.
3. Đăng ký v2 sau gate.
4. Deploy green với no-traffic và integration tests.
5. Canary tỷ lệ thấp, theo dõi monitoring.
6. Thử rollback traffic blue khi cố tình tạo lỗi lab.
7. Thiết kế batch scoring cho dữ liệu lớn.
8. Viết feature drift/quality alert với owner.
9. Đánh giá RBAC, Private Endpoint, secrets, data retention.
10. Tổng kết chi phí và runbook.

## 34. Câu hỏi tự kiểm tra

**Câu 1.** Workspace, compute, data asset, environment, model asset và endpoint khác nhau thế nào?

**Câu 2.** Tại sao training job Completed không đủ kết luận model được phép phát hành?

**Câu 3.** Data asset version có làm storage path tự động immutable không?

**Câu 4.** Vì sao StandardScaler phải fit trên train, không fit trên cả train+test?

**Câu 5.** Khi nào nên chia theo thời gian hoặc theo nhóm thay vì random?

**Câu 6.** Vì sao accuracy dễ gây hiểu lầm ở bài toán nhãn hiếm?

**Câu 7.** Command job v2 cần code, environment, compute và output bindings như thế nào?

**Câu 8.** Model custom_model khác mlflow_model ở đâu?

**Câu 9.** Vì sao phải đăng ký đúng artifact đã được evaluation PASS?

**Câu 10.** Vì sao joblib/pickle model chỉ nên load từ nguồn đáng tin?

**Câu 11.** Online endpoint và deployment khác nhau ra sao?

**Câu 12.** Khi nào chọn batch thay online inference?

**Câu 13.** `score.py` cần kiểm tra những điều kiện gì trước `model.predict`?

**Câu 14.** Tại sao training-serving skew có thể gây lỗi chất lượng mà HTTP vẫn trả 200?

**Câu 15.** Blue/green và rollback bảo vệ production như thế nào?

**Câu 16.** Rollback traffic có tự đảo ngược quyết định nghiệp vụ đã được đưa ra không?

**Câu 17.** Data drift, concept drift và prediction drift khác nhau thế nào?

**Câu 18.** Khi chưa có ground truth, ta nên quan sát gì và không được khẳng định gì?

**Câu 19.** Managed identity của compute có tự có quyền đọc Blob/ADLS không?

**Câu 20.** Private endpoint có tự cấp authentication/authorization cho endpoint không?

**Câu 21.** Vì sao online deployment có thể tiếp tục tính tiền khi idle?

**Câu 22.** Những gì cần lưu để model version tái lập/kiểm toán được?

**Câu 23.** Vì sao không nên tự retrain+promote production chỉ vì một drift alert?

**Câu 24.** Khi batch retry, làm thế nào tránh duplicated predictions?

**Tiêu chí hoàn thành:** người học trình bày được chu trình Azure ML end-to-end, viết command training job và output model/metrics, đánh giá bằng quality gates, đăng ký model version, triển khai/invoke managed online endpoint, phân biệt batch, thiết kế security/monitoring/rollback và kiểm soát chi phí.

## Kết luận

**Huấn luyện, đăng ký và triển khai mô hình trong Azure Machine Learning** là một quy trình có kiểm soát từ dữ liệu đến kết quả kinh doanh. Training job nối **code, dữ liệu, environment và compute**; evaluation chứng minh chất lượng trong giới hạn thiết kế; model registry giữ **artifact có name/version/lineage**; deployment online hoặc batch đưa model vào ứng dụng theo SLO.

Muốn xây MLOps đáng tin cậy trên Azure, cần bổ sung **data versioning và leakage prevention, quality/security gates, environment provenance, Entra/RBAC và private network, blue/green rollout, drift/ground-truth monitoring, batch idempotency, audit và chi phí**. Mô hình hoạt động trên laptop chỉ là điểm khởi đầu; giá trị dài hạn đến từ khả năng tái lập, triển khai đúng model đã được phê duyệt, vận hành an toàn và rollback khi cần.

