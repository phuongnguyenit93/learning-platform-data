# AutoML và custom training trên Vertex AI

Một dịch vụ Java trên Cloud Run thu thập đơn hàng, còn BigQuery lưu các đặc trưng như số lần mua, giá trị giỏ hàng và lịch sử giao dịch. Nhóm muốn huấn luyện mô hình dự đoán khả năng khách hàng quay lại mua, nhưng phải quyết định: **dùng AutoML để Google Cloud tự chọn quy trình huấn luyện hay tự viết mã custom training để kiểm soát thuật toán?**

**Vertex AI** cung cấp hạ tầng quản lý vòng đời học máy trên Google Cloud. Trong các tài liệu và giao diện mới, một số chức năng có thể mang tên **Gemini Enterprise Agent Platform / Agent Platform**; API huấn luyện vẫn sử dụng `aiplatform.googleapis.com`. Bài này tập trung vào **AutoML và custom training**, không đồng nhất chúng với việc gọi mô hình Gemini qua API hay fine-tuning mô hình ngôn ngữ.

Bài thuộc chương **Vertex AI và học máy**, mô-đun `CLOUD_PROVIDERS_GCP`. Bài kết nối lựa chọn ML với tổ chức project/IAM/VPC, Cloud Storage, BigQuery, Compute Engine, GKE, Cloud Run, bảo vệ dữ liệu, phát hành và theo dõi chất lượng cùng chi phí. Mọi ví dụ có thể phát sinh phí chỉ dành cho **project lab** với dữ liệu công khai hoặc tổng hợp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **AutoML**, **custom training**, **training pipeline**, **CustomJob**, **Model Registry** và **Endpoint**.
2. Chọn phương án huấn luyện theo loại dữ liệu, thuật toán, mức kiểm soát, năng lực kỹ thuật và chi phí.
3. Thiết kế dữ liệu **train/validation/test**, tránh label leakage và chọn metric phù hợp.
4. Tạo một luồng **AutoML tabular classification** trên dữ liệu công khai.
5. Đóng gói một chương trình scikit-learn thành container và chạy **custom training trên Vertex AI**.
6. Ghi model artifacts và metrics xuống Cloud Storage, đánh giá kết quả trước khi đăng ký/triển khai model.
7. Cấu hình service account/IAM, giới hạn tài nguyên và quan sát training jobs.
8. Lập kế hoạch giám sát dữ liệu/mô hình, retraining và dọn tài nguyên có tính phí.

## 1. Tư duy chung: dữ liệu, huấn luyện, đánh giá và triển khai

~~~mermaid
flowchart LR
    RAW["Cloud Storage / BigQuery<br/>dữ liệu và nhãn"] --> PREP["Validation / split<br/>train-val-test"]
    PREP --> CHOICE{"Cách huấn luyện?"}
    CHOICE --> A["AutoML<br/>quản lý search & training"]
    CHOICE --> B["Custom training<br/>mã nguồn + container"]
    A --> EVAL["Evaluation<br/>metrics + slices"]
    B --> EVAL
    EVAL --> APPROVE{"Đạt tiêu chí?"}
    APPROVE -->|Có| REG["Model Registry"]
    REG --> PRED["Online Endpoint<br/>hoặc Batch Prediction"]
    APPROVE -->|Không| ITER["Dữ liệu/feature/model iteration"]
    ITER --> PREP
~~~

Các tài nguyên cần phân biệt:

| Tài nguyên | Vai trò |
| --- | --- |
| **Dataset** | Tham chiếu hoặc quản lý tập dữ liệu huấn luyện theo loại dữ liệu/khả năng hỗ trợ |
| **AutoML training pipeline** | Quản lý quá trình huấn luyện AutoML và thường tạo model được quản lý |
| **CustomJob** | Chạy mã huấn luyện trong một hay nhiều worker pools; **không mặc nhiên đăng ký model** |
| **Custom training pipeline** | Bao bọc CustomJob và có thể **upload model** sau huấn luyện khi đã khai báo artifacts/serving container |
| **Model Registry** | Quản lý model resource, phiên bản, metadata và nguồn artifacts |
| **Endpoint** | Tài nguyên phục vụ **online prediction**; deploy có thể giữ máy và tính phí |
| **Batch Prediction Job** | Chạy dự đoán trên dữ liệu theo đợt, không cần endpoint chạy 24/7 |
| **Vertex AI Pipelines** | Điều phối nhiều bước ML; khác một job huấn luyện đơn |

**Huấn luyện thành công không có nghĩa mô hình đã sẵn sàng production.** Cần kiểm chứng dữ liệu, metric, các nhóm người dùng, bảo mật, chi phí và hành vi khi triển khai.

## 2. AutoML khác custom training ở đâu?

| Tiêu chí | AutoML | Custom training |
| --- | --- | --- |
| Người chọn thuật toán / tuning | Dịch vụ tự động nhiều bước | Nhóm ML tự kiểm soát |
| Mã huấn luyện | Ít hoặc không phải viết | Phải có script/package/container |
| Định dạng dữ liệu | Theo loại dataset và schema AutoML hỗ trợ | Linh hoạt theo framework/mã của bạn |
| Tiền xử lý và feature engineering | Hỗ trợ tự động theo loại dữ liệu | Tự làm hoặc dùng pipeline/framework |
| Framework/kiến trúc đặc thù | Ít kiểm soát | TensorFlow, PyTorch, scikit-learn, XGBoost, mã tùy chỉnh... |
| GPU/distributed training | Dịch vụ quản theo khả năng AutoML | Tự chọn worker pools, GPUs, phân tán |
| Debug chi tiết thuật toán | Có giới hạn | Logs, checkpoints, profiler, code tùy ý |
| Khởi đầu với đội ít MLOps | Thường nhanh hơn | Tốn công xây pipeline nhưng có tính linh hoạt |
| Billing | Training budget theo đơn vị AutoML và tác vụ liên quan | VM/GPU/worker thời gian chạy, storage/network/artifacts |

**Quy tắc chọn:** nếu cần baseline nhanh cho bài toán AutoML hỗ trợ, thử **AutoML**; nếu phải dùng thuật toán/feature đặc biệt, kiểm soát dependency/hyperparameter, phân tán nhiều workers hoặc sở hữu toàn bộ mã, chọn **custom training**. Cả hai đều cần dữ liệu tốt và đánh giá thực nghiệm.

### 2.1. Những gì không nên gọi là AutoML

- Gọi Gemini API để tóm tắt văn bản **không phải** một AutoML training job.
- Tăng `n_estimators` trong scikit-learn **không tự biến** script thành AutoML.
- Train một lần rồi dùng model mãi **không phải MLOps**; cần monitoring/drift/retraining khi nghiệp vụ thay đổi.

## 3. Những bài toán AutoML hỗ trợ và điều kiện chọn

Các nhóm AutoML có thể bao gồm **tabular classification/regression**, bài toán ảnh và một số loại dữ liệu khác tùy dịch vụ, region, phiên bản. **Không mặc định AutoML hỗ trợ mọi loại text/video/forecasting với cùng API, dataset và giao diện.** Tra ma trận tính năng trước khi thiết kế.

Bài tập chính chọn **tabular classification**:

~~~text
Mục tiêu: dự đoán biến Deposit (đồng ý gửi tiền kỳ hạn hay không)
Nguồn mẫu công khai: gs://cloud-ml-tables-data/bank-marketing.csv
Target column: Deposit
Bài toán: supervised classification
~~~

Đây là bộ dữ liệu hướng dẫn công khai của Google. Với doanh nghiệp thực, nên loại hoặc kiểm soát chặt những trường nhạy cảm và thuộc tính chỉ được biết **sau khi kết quả xảy ra**.

### 3.1. Điều kiện dữ liệu cơ bản

Với AutoML tabular classification/regression, tài liệu hướng dẫn hiện hành quy định dữ liệu thường cần **ít nhất 1.000 hàng**, **ít nhất hai cột** (target + feature), không quá **1.000 cột** và có giới hạn kích thước/row count. Target phải phù hợp bài toán và không được rỗng.

**Bộ CSV 10–20 dòng chỉ có thể dùng để giải thích schema**, không đủ để train AutoML tabular. Dùng dữ liệu công khai hợp lệ hoặc dataset lớn đã được kiểm duyệt; đừng tự sinh hàng nhân bản rồi coi accuracy là bằng chứng chất lượng.

## 4. Chia tập dữ liệu và chống data leakage

Chia dữ liệu:

| Tập | Mục tiêu | Khi được sử dụng |
| --- | --- | --- |
| **Training** | Học tham số mô hình | Trong huấn luyện |
| **Validation** | Chọn mô hình, tuning và threshold | Trong lựa chọn mô hình |
| **Test (holdout)** | Đánh giá cuối cùng bằng dữ liệu chưa dùng để tuning | Sau khi chốt lựa chọn |
| **Production shadow/canary** | Xác thực hành vi thực tế và drift | Sau khi model đạt offline gate |

AutoML tabular có tùy chọn random split mặc định khoảng **80% train / 10% validation / 10% test**, đồng thời hỗ trợ **manual** và **chronological** split tùy loại bài toán. Chọn split phù hợp mục đích, không mặc định random là đúng.

Ví dụ chống leakage:

- **Dự báo khách sẽ hủy đơn ngày mai:** chỉ dùng các đặc trưng biết **trước** thời điểm dự báo; không đưa trạng thái hủy cuối cùng làm feature.
- **Dữ liệu theo thời gian:** dùng chronological split theo cutoff; không huấn luyện trên dữ liệu tương lai.
- **Nhiều records cùng customer:** nên group split nếu cần đánh giá khả năng tổng quát hóa cho khách hàng mới.
- **Class imbalance:** stratified split cho custom classification và đo cả precision/recall, không chỉ accuracy.
- **Target leakage từ ID:** loại order_id, nhãn phát sinh sau sự kiện, trường gần như mã hóa trực tiếp target.

**Không tái sử dụng test set để điều chỉnh mô hình nhiều lần.** Nếu tuning trên test, test không còn là phép đo độc lập.

## 5. Đánh giá mô hình bằng metric phù hợp

| Bài toán | Metric | Khi hữu ích |
| --- | --- | --- |
| Binary classification | ROC-AUC | Xếp hạng tổng thể theo dải thresholds |
| Binary, lớp dương hiếm | **PR-AUC, precision, recall** | Chú ý false positives/false negatives |
| Binary, quyết định vận hành | F1, confusion matrix, calibration | Chọn ngưỡng theo chi phí sai lầm |
| Multi-class classification | Macro/micro F1, per-class recall | Tránh lớp phổ biến che khuất lớp hiếm |
| Regression | MAE | Sai số tuyệt đối dễ diễn giải |
| Regression | RMSE | Phạt sai số lớn nhiều hơn |
| Business KPI | Revenue uplift, conversion, manual-review rate | Đánh giá giá trị thực thay vì chỉ chỉ số ML |

Ví dụ một hệ thống gian lận chỉ có 1% giao dịch gian lận: mô hình luôn dự đoán “không gian lận” có **99% accuracy** nhưng **recall fraud = 0**. Vì thế đặt tiêu chí gắn business cost, đo metric trên từng vùng/segment và so với **baseline**.

**Model evaluation không phải fairness/privacy review đầy đủ.** Các loại dữ liệu nhạy cảm cần threat model, kiểm tra bias, policy và phê duyệt riêng.

## 6. Preflight: project, API, vùng và IAM

Các lệnh bên dưới dành cho **Cloud Shell/Bash**. Chọn `us-central1` cho lab vì là vùng phổ biến trong các tài liệu AutoML; dữ liệu giả lập/công khai không có yêu cầu cư trú. Khi dùng dữ liệu thực, **region phải phù hợp luật, VPC và data residency**.

Chỉ đọc thông tin hiện tại:

~~~bash
gcloud auth list
gcloud config get-value project

gcloud ai custom-jobs list \
  --project=PROJECT_ID --region=us-central1

gcloud ai models list \
  --project=PROJECT_ID --region=us-central1
~~~

Khi đã có project lab và phê duyệt sử dụng phí:

~~~bash
gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  --project=PROJECT_ID
~~~

Dịch vụ có thể cần **Compute Engine API** và service agents tùy luồng huấn luyện. Quyền gợi ý:

| Principal | Quyền cần cân nhắc |
| --- | --- |
| Người tạo jobs | `aiplatform.customJobs.create`, quyền đọc/list phù hợp, `iam.serviceAccounts.actAs` khi chỉ định runtime SA |
| Người tạo dataset/AutoML | Quyền Vertex AI dataset/training pipeline phù hợp |
| Training runtime service account | Chỉ quyền đọc training data và **ghi artifact bucket** cần thiết |
| Container image pull | Artifact Registry Reader cho identity thực sự lấy image |
| Cloud Build | Quyền build và push image tới repository |
| Model deployer | Quyền upload/deploy model và cấu hình endpoint phù hợp |
| Ứng dụng inference | Chỉ quyền predict trên endpoint/model theo kiến trúc |

**Không cấp Owner/Editor cho mọi danh tính.** Google-managed **service agents** có quyền đặc biệt; không cấp role service-agent cho runtime app hay user. Dùng **Application Default Credentials** trên local, service account của Cloud Run/GKE/VM khi chạy trong hệ thống.

## 7. Lab A: train AutoML tabular qua Console

Bài lab dùng dữ liệu công khai `gs://cloud-ml-tables-data/bank-marketing.csv`, không cần tự tạo model code. Giao diện sản phẩm có thể hiển thị **Vertex AI** hoặc **Agent Platform**; thứ tự trường có thể khác theo phiên bản.

1. Mở **Vertex AI / Agent Platform → Datasets → Create**.
2. Chọn **Tabular → Classification/Regression**, region `us-central1`, tên `bank-automl-lab`.
3. Chọn dữ liệu **Cloud Storage CSV** `gs://cloud-ml-tables-data/bank-marketing.csv` theo giao diện hỗ trợ.
4. Kiểm tra schema/target, số dòng, missing values. Chọn **Train new model → AutoML**.
5. Chọn **Classification**, target column `Deposit`; bỏ các feature gây leakage hoặc không được phép sử dụng.
6. Chọn split **80/10/10 random** cho lab; với dữ liệu thời gian thực/churn, thay bằng split phù hợp.
7. Chọn optimization objective theo chi phí nghiệp vụ, ví dụ ROC-AUC hoặc mục tiêu được hỗ trợ; đặt **training budget thấp hợp lệ**, không nhầm budget là tổng hóa đơn cố định.
8. Chạy training; theo dõi job state, training metrics và resource model khi hoàn tất.
9. Đọc **confusion matrix, precision/recall/AUC**, so baseline và xác định ngưỡng quyết định.
10. Chỉ deploy endpoint online khi thật cần; nếu dùng batch, cân nhắc **batch prediction** không phải giữ máy inference liên tục.

**Cảnh báo chi phí:** AutoML có thể mất hàng giờ và phát sinh tiền **ngay cả khi người học đóng trình duyệt**. Budget huấn luyện là trần ngân sách *huấn luyện theo đơn vị áp dụng*, **không bao gồm mọi phí** như data, batch/online prediction hoặc artifacts. Kiểm tra billing trước khi bấm **Start Training**.

### 7.1. Điều cần ghi vào báo cáo lab

~~~text
Dataset: bank-automl-lab
Target: Deposit
Region: us-central1
Split: random 80/10/10 (lab)
Training budget: [giá trị đã chọn]
Training state: [succeeded/failed]
Metric trên test: [ROC-AUC, precision/recall hoặc metrics được hiển thị]
Baseline: [so sánh]
Deployment: [chưa deploy nếu chỉ đánh giá offline]
~~~

Không tự điền metric “0.95” khi chưa chạy thật. Chỉ dùng kết quả **đã quan sát**, ghi rõ thời điểm, phiên bản dữ liệu và model.

## 8. AutoML training pipeline trong API

Ở cấp API, AutoML tabular dùng **`TrainingPipeline`** với task definition và inputs thích hợp:

~~~json
{
  "displayName": "bank-classifier-lab",
  "trainingTaskDefinition": "gs://google-cloud-aiplatform/schema/trainingjob/definition/automl_tabular_1.0.0.yaml",
  "trainingTaskInputs": {
    "targetColumn": "Deposit",
    "predictionType": "classification",
    "trainBudgetMilliNodeHours": 1000,
    "transformations": [
      { "categorical": { "column_name": "job" } },
      { "numeric": { "column_name": "age" } }
    ]
  },
  "modelToUpload": { "displayName": "bank-classifier-lab-model" },
  "inputDataConfig": { "datasetId": "DATASET_ID" }
}
~~~

Đây là **mẫu cấu trúc**, **không phải payload đủ để chạy ngay** với mọi phiên bản của dataset. Cần khai báo transformations cho các cột được dùng, target config, giá trị labels/feature types theo schema đã import và xác minh ngân sách hợp lệ. `trainBudgetMilliNodeHours=1000` nghĩa là **1.000 milli-node-hours = 1 node-hour** theo API, không phải 1.000 giờ.

**Không dùng `CustomJob` để thay cho AutoML task definition.** Một `TrainingPipeline` AutoML được quản lý khác với chương trình Python tùy chỉnh tự huấn luyện.

## 9. Custom training: từ mã nguồn tới CustomJob

Khi dùng custom training, **bạn sở hữu mã và môi trường**; Vertex AI quản lý tài nguyên worker, lịch chạy, logging và kết quả job. Một CustomJob có **workerPoolSpecs**, mỗi pool có `machineSpec`, `replicaCount` và `containerSpec` hoặc `pythonPackageSpec`.

~~~mermaid
flowchart LR
    CODE["train.py + requirements/Dockerfile"] --> BUILD["Artifact Registry image"]
    BUILD --> JOB["Vertex AI CustomJob<br/>1 worker CPU"]
    JOB --> TRAIN["scikit-learn training"]
    TRAIN --> GCS["Cloud Storage artifacts<br/>model.joblib + metrics.json"]
    GCS -. "khi được phê duyệt" .-> REG["Model Registry"]
~~~

Lựa chọn đóng gói:

- **Prebuilt training container:** dùng image sẵn có và mã dạng Python package hoặc script.
- **Custom container:** tự chọn OS, dependencies, entrypoint. Phù hợp khi cần thư viện riêng, cấu hình phức tạp.
- **Autopackaging:** công cụ hỗ trợ đóng gói mã local vào image khi thông số phù hợp.
- **Distributed training:** nhiều worker pools/replicas, chiến lược framework để đồng bộ; **chỉ tăng replicaCount không khiến mọi script tự học phân tán**.

Bài chọn custom container **CPU một worker**; không cần GPU để học cách tạo job.

## 10. Lab B: mã scikit-learn huấn luyện và xuất artifacts

Dùng bộ dữ liệu `digits` đi kèm scikit-learn để **không tải dữ liệu cá nhân**, đồng thời giữ bài lab nhỏ. Đây là **bài toán phân loại ảnh chữ số** với features numeric, khác bộ dữ liệu ngân hàng của AutoML; mục đích là học hạ tầng custom training, **không so AUC giữa hai dataset để quyết định phương pháp nào tốt hơn**.

Cấu trúc thư mục lab **trên máy người học**:

~~~text
vertex-custom-lab/
├── train.py
├── requirements.txt
├── Dockerfile
└── customjob.yaml
~~~

`requirements.txt`:

~~~text
scikit-learn==1.5.2
joblib==1.4.2
google-cloud-storage==2.18.2
~~~

Phiên bản được pin để lab tái lập. Production cần cập nhật/kiểm duyệt lỗ hổng và thống nhất phiên bản **training–serving**; không cho phép untrusted model artifacts đi vào `joblib.load()`.

### 10.1. File train.py

~~~python
import json
import os

import joblib
from google.cloud import storage
from sklearn.datasets import load_digits
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

X, y = load_digits(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

model = RandomForestClassifier(
    n_estimators=100, n_jobs=2, random_state=42
)
model.fit(X_train, y_train)
pred = model.predict(X_test)

metrics = {
    "accuracy": float(accuracy_score(y_test, pred)),
    "macro_f1": float(f1_score(y_test, pred, average="macro")),
    "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
    "train_rows": int(len(y_train)),
    "test_rows": int(len(y_test)),
    "seed": 42
}
print(json.dumps(metrics, ensure_ascii=False))

joblib.dump(model, "model.joblib")
with open("metrics.json", "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=2)

model_dir = os.environ.get("AIP_MODEL_DIR", "").rstrip("/")
if not model_dir.startswith("gs://"):
    raise RuntimeError("AIP_MODEL_DIR must be set to a gs:// directory")

client = storage.Client()
for name in ("model.joblib", "metrics.json"):
    uri = f"{model_dir}/{name}"
    storage.Blob.from_string(uri, client=client).upload_from_filename(name)
    print(f"Uploaded: {uri}")
~~~

**Kỹ thuật:** dùng seed và `stratify=y` để phép split có thể tái lập; metrics đo trên holdout chưa dùng để fit. Bài demo không có validation/tuning riêng vì cố tình chỉ huấn luyện **một cấu hình cố định**; nếu tuning nhiều cấu hình, phải tách validation và giữ test cho đánh giá cuối.

### 10.2. Dockerfile

~~~dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY train.py .
ENTRYPOINT ["python", "train.py"]
~~~

**Không đưa Cloud credentials JSON hoặc dataset PII vào Docker image.** Vertex AI gắn workload identity cho container theo `serviceAccount` của job. Container cần truy cập Cloud Storage bằng Application Default Credentials.

## 11. Xây image và chuẩn bị output bucket

Chỉ chạy sau khi project lab có Billing, quota, quyền Cloud Build/Artifact Registry và ngân sách. Chọn `us-central1`, thay `PROJECT_ID` và `UNIQUE` bằng giá trị được cấp. **Bucket name phải duy nhất toàn cầu.**

~~~bash
gcloud artifacts repositories create vertex-training-lab \
  --repository-format=docker \
  --location=us-central1 \
  --description="Lab Vertex training images" \
  --project=PROJECT_ID

gcloud storage buckets create \
  gs://PROJECT_ID-vertex-models-UNIQUE \
  --location=us-central1 \
  --project=PROJECT_ID

# Từ thư mục vertex-custom-lab/ có Dockerfile và train.py.
gcloud builds submit \
  --region=us-central1 \
  --tag=us-central1-docker.pkg.dev/PROJECT_ID/vertex-training-lab/digits-trainer:v1 \
  --project=PROJECT_ID .
~~~

**Cloud Build có phí/quota và quyền riêng.** Nếu build fail `PERMISSION_DENIED` ở Artifact Registry, kiểm tra đúng **Cloud Build execution service account**, quyền tạo image và ràng buộc tổ chức; **không cấp Owner toàn project**. Không ghi đè tag đang phục vụ production; production pin **image digest** để tái lập.

Tạo runtime service account dùng cho job:

~~~bash
gcloud iam service-accounts create vertex-trainer-lab \
  --display-name="Vertex custom training lab" \
  --project=PROJECT_ID

gcloud storage buckets add-iam-policy-binding \
  gs://PROJECT_ID-vertex-models-UNIQUE \
  --member=serviceAccount:vertex-trainer-lab@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.objectCreator
~~~

Execution SA cần quyền **ghi artifacts** vào bucket; nếu code đọc training data từ GCS/BigQuery, cấp thêm quyền **read đúng nguồn**. Người nộp job cần quyền `iam.serviceAccounts.actAs` trên SA này. Nếu image pull lỗi, kiểm tra quyền Artifact Registry của **identity lấy image** và service agent tương ứng.

## 12. Tạo CustomJob từ file cấu hình

File `customjob.yaml`, nội dung thay `PROJECT_ID` và `UNIQUE`:

~~~yaml
workerPoolSpecs:
  - machineSpec:
      machineType: n1-standard-4
    replicaCount: 1
    containerSpec:
      imageUri: us-central1-docker.pkg.dev/PROJECT_ID/vertex-training-lab/digits-trainer:v1
baseOutputDirectory:
  outputUriPrefix: gs://PROJECT_ID-vertex-models-UNIQUE/digits-run
serviceAccount: vertex-trainer-lab@PROJECT_ID.iam.gserviceaccount.com
~~~

Đây là **CustomJobSpec**, không có các field như `displayName` ở root file; CLI cấp display name riêng. `baseOutputDirectory.outputUriPrefix` khiến Vertex AI đặt các biến môi trường như `AIP_MODEL_DIR` trỏ tới subdirectory trong GCS (thường dưới thư mục run tương ứng). Script ở mục 10 upload artifacts vào đó.

Chạy **chỉ khi đã phê duyệt chi phí**:

~~~bash
gcloud ai custom-jobs create \
  --project=PROJECT_ID \
  --region=us-central1 \
  --display-name=digits-custom-lab \
  --config=customjob.yaml

gcloud ai custom-jobs list \
  --project=PROJECT_ID --region=us-central1

# Thay JOB_ID bằng ID từ kết quả list/create.
gcloud ai custom-jobs describe JOB_ID \
  --project=PROJECT_ID --region=us-central1
~~~

**Kỳ vọng:** job đi qua các trạng thái tạo tài nguyên/chạy và cuối cùng `JOB_STATE_SUCCEEDED` khi hoàn tất. Log có JSON metrics và đường dẫn upload; GCS chứa `model.joblib`, `metrics.json` trong model directory của run.

**Không dự đoán số accuracy cụ thể:** đó là số đo phải lấy từ lần chạy thật. Model mẫu này **chưa được tự động tạo trong Model Registry**, vì ta chạy `CustomJob` đơn thuần, không phải `TrainingPipeline` có khai báo `modelToUpload`.

### 12.1. Khi cần GPU hoặc phân tán

Cấu hình worker pool cần `machineSpec.acceleratorType`, `acceleratorCount` và image/framework hỗ trợ GPU, quota và runtime/cuDNN phù hợp. Một số machine types yêu cầu GPU; availability khác theo region.

Đào tạo phân tán cần **code phù hợp** (PyTorch DDP, TensorFlow distributed strategy...) và coordination giữa workers. **Không chỉ đặt `replicaCount=4` với script dùng `load_digits` rồi coi đó là distributed training**: bốn workers có thể train và ghi artifacts đè nhau.

## 13. Chọn CustomJob hay training pipeline có đăng ký model?

| Cách chạy | Kết quả tự nhiên | Cần thêm |
| --- | --- | --- |
| **CustomJob** | Worker thực thi mã; artifacts tùy code | Đăng ký model thủ công hoặc trong pipeline sau |
| **Custom TrainingPipeline + modelToUpload** | Huấn luyện và có thể tạo Model resource khi job thành công | Artifacts đúng định dạng + **serving container** hợp lệ |
| **AutoML TrainingPipeline** | AutoML training + managed model theo luồng hỗ trợ | Evaluation, review và chọn online/batch |
| **Vertex AI Pipelines** | Điều phối các bước prep/train/evaluate/register/deploy | Components, pipeline metadata, governance |

Đối với scikit-learn `model.joblib`, để phục vụ inference cần **container dự đoán tương thích** với phiên bản training hoặc **custom prediction container**. Không phải Dockerfile huấn luyện ở mục 10 có thể dùng làm serving container ngay: container đó chạy `train.py` rồi thoát, **không mở HTTP inference endpoint**.

**Production gate:** chỉ đăng ký/deploy model sau khi đã kiểm tra metric, schema input/output, vulnerability scan, IAM và khả năng tái lập model.

## 14. Đánh giá AutoML và custom training một cách công bằng

Không so AutoML trên ngân hàng với RandomForest trên chữ số; hai bài toán và datasets khác nhau. Khi benchmark thật, phải cố định:

1. **Cùng dataset snapshot** tại thời điểm training, quyền truy cập hợp lệ.
2. **Cùng train/validation/test split** hoặc nguyên tắc split có thể đối chiếu.
3. **Cùng định nghĩa label và feature availability** (tránh leakage).
4. **Cùng metric và threshold chọn từ validation**, so trên test chưa đụng tới.
5. **Chi phí training end-to-end**: data prep, tuning, compute, artifacts và vận hành.
6. **Latency/cost inference** trên CPU/GPU/endpoint hoặc batch.
7. **Fairness/slice evaluation** cho nhóm địa lý, thiết bị hoặc phân khúc được phép.
8. Khả năng debug, retrain, tích hợp CI/CD, theo dõi drift và kiểm toán.

| Kết quả thử nghiệm | Quyết định gợi ý |
| --- | --- |
| AutoML baseline tốt, vận hành đơn giản | Dùng AutoML và xây monitoring/gates |
| Custom tốt hơn rõ theo business KPI | Dùng custom khi lợi ích bù complexity |
| Hai cách tương đương, SLA/latency khác | Chọn theo chi phí phục vụ và bảo trì |
| Dữ liệu không đủ/label sai | **Sửa dữ liệu** trước khi tốn tiền train |
| Có rủi ro fairness/PII/leakage | **Không deploy**, đánh giá lại data/policy |

## 15. MLOps tối thiểu sau khi train

Huấn luyện một lần là bước đầu. Một luồng production nên có:

~~~mermaid
flowchart TD
    DATA["Data version + contracts"] --> TRAIN["AutoML / CustomJob"]
    TRAIN --> EVAL["Holdout + slice metrics"]
    EVAL --> GATE{"Metric / policy gates đạt?"}
    GATE -->|Có| REG["Register model + version"]
    REG --> DEPLOY["Batch / canary endpoint"]
    DEPLOY --> MON["Drift, latency, cost, quality"]
    MON --> RETRAIN["Trigger retrain khi cần"]
    RETRAIN --> DATA
    GATE -->|Không| FIX["Review feature, label, bias"]
    FIX --> DATA
~~~

Một số tín hiệu sau deploy:

- **Data/feature drift**: phân bố feature khác training set.
- **Prediction drift**: phân bố đầu ra thay đổi.
- **Quality drift**: khi có nhãn thật đến muộn, precision/recall/MAE thay đổi.
- **Operational SLO**: p95/p99 inference, throughput, availability, errors.
- **Business SLO**: quyết định có cải thiện conversion/losses không.
- **Cost**: GPU/CPU/endpoint uptime, batch jobs, model registry artifacts.

**Drift không đồng nghĩa cần retrain ngay.** Cần xem nguồn thay đổi, nhãn và hiệu quả mô hình. Với ứng dụng Java trên Cloud Run, gọi model qua Vertex AI endpoint/batch output bằng **runtime service account** ít quyền; đừng đưa credential key vào image hoặc frontend.

## 16. Bảo mật, dữ liệu nhạy cảm và network

- **IAM:** tách người tạo training job, training runtime SA, model approver và inference caller.
- **Data locality:** chọn region của dataset, bucket, training job, artifact registry và endpoints theo quy định cư trú dữ liệu.
- **GCS/BQ:** cấp quyền đọc training snapshot và ghi artifact theo bucket/dataset nhỏ nhất, bật log/audit theo yêu cầu.
- **Secrets:** dùng Secret Manager hoặc workload identity, không hard-code keys/token trong `train.py`, Dockerfile hay container args.
- **Private connectivity:** nếu huấn luyện cần Cloud SQL private IP/on-prem, cấu hình networking/PSC/VPC/private service access theo loại Vertex training job; **IAM không thay route network**.
- **PII:** giảm trường nhạy cảm, kiểm soát labels/features, quyền người xem logs/artifacts; không log raw records chứa PII.
- **Supply chain:** pin base image/dependency versions và digest, quét vulnerabilities, ký/phê duyệt container theo policy.
- **Model artifacts:** `joblib`/`pickle` có thể thực thi mã khi deserialization; **không load artifact từ nguồn chưa tin cậy**.
- **Fairness/safety:** đo slices, privacy exposure và khả năng giải thích theo loại quyết định. Với tài chính/tín dụng phải đáp ứng quy định riêng.

**Chỉ dùng public sample/dữ liệu tổng hợp trong lab**; việc đưa dữ liệu thật vào dịch vụ AI phải theo phân quyền, hợp đồng và chính sách tổ chức.

## 17. Chi phí training: ngân sách phải tính đủ

| Thành phần | Khi phát sinh phí |
| --- | --- |
| AutoML | Đơn vị compute/node hours hoặc model training budget theo loại tác vụ |
| Custom training | Machine type × worker replicas × duration, GPU/accelerator khi dùng |
| Hyperparameter tuning | **Nhiều trials** huấn luyện, tổng phí cao hơn một job |
| Cloud Storage | Dataset snapshots, checkpoints, model artifacts, logs |
| BigQuery/Dataflow | Data prep, feature queries, materialization |
| Cloud Build/Artifact Registry | Xây và lưu image |
| Online prediction | Endpoint deployed machines/accelerators theo thời gian, kể cả traffic thấp |
| Batch prediction | Tài nguyên thực thi dự đoán theo đợt |
| Network/Logging/Monitoring | Egress, logs, metrics và các dịch vụ phụ trợ |

Ví dụ ước lượng **tương đối** cho custom training:

~~~text
Chi phí huấn luyện gần đúng =
  số worker replicas × số giờ chạy × giá machine/hour
  + GPU (nếu có)
  + storage/artifacts + build/log/network

1 replica CPU × 0,5 giờ chỉ là 0,5 machine-hour;
KHÔNG có nghĩa tổng chi phí hệ thống chỉ bằng giá VM đó.
~~~

**Không chép giá cứng từ tài liệu cũ:** tra [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) và Billing SKU tại region. Budget alerts **không tự dừng training job hoặc endpoint**. Tắt/xóa endpoint khi không dùng; xóa model artifacts có kiểm soát và xác nhận không còn pipeline khác cần chúng.

## 18. Quan sát và troubleshooting training job

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `PERMISSION_DENIED` đọc GCS | Runtime SA thiếu Object Viewer/Reader phù hợp | Kiểm tra principal, bucket IAM |
| Không pull được image | Repo sai region/tag, thiếu Artifact Registry Reader | Kiểm tra URI và image pull identity |
| `AIP_MODEL_DIR` trống | Không thiết lập `baseOutputDirectory` cho job | Kiểm tra customjob.yaml và env |
| Job RUNNING lâu nhưng không train | Startup image/cluster/data loading hoặc quota | Xem job details và Cloud Logging |
| GPU OOM | Batch size/model quá lớn | Giảm batch, mixed precision khi phù hợp, tăng capacity |
| Nhiều replicas nhưng không nhanh | Code không hỗ trợ distributed training | Dùng framework/strategy phân tán |
| Model không hiện trong Registry | `CustomJob` đơn thuần không tự register | Upload model hoặc dùng TrainingPipeline |
| AutoML không cho train | Dữ liệu thiếu rows/target, unsupported location/objective | Xem schema, min rows, region |
| Accuracy cao bất thường | Leakage hoặc split sai | Kiểm tra feature chronology/group split |
| Accuracy cao nhưng lớp dương kém | Imbalanced classes | PR-AUC/recall/slice metrics |
| Kết quả train khác lần trước | Seed, snapshot, image/dependency thay đổi | Pin data/image/code/seed |
| Hóa đơn tăng sau train | Endpoint vẫn deploy hoặc artifacts còn lưu | Kiểm tra Billing, endpoints, storage |

**Đọc logs bằng job ID/training pipeline ID**, không log dữ liệu người dùng/secret để debug. Lưu Git commit, image digest, data snapshot, training parameters, metrics và chi phí để truy vết.

## 19. Bài tập thực hành và tự kiểm tra

**Bài 1 — Quyết định phương án.** Cần baseline dự đoán nhãn trên dữ liệu bảng 50.000 rows, ít người viết ML code.

*Đáp án gợi ý:* Thử AutoML tabular trước, sau đó so với baseline đơn giản và đánh giá chi phí.

**Bài 2 — Kiểm tra leakage.** Trường `refund_completed_at` chỉ xuất hiện sau khi hoàn tiền; nhóm muốn dự đoán khả năng hoàn tiền khi khách thanh toán.

*Đáp án:* Loại khỏi features tại thời điểm dự đoán, dùng cutoff thời gian.

**Bài 3 — CustomJob.** Tạo container theo mục 10–12, chỉ chạy trên project lab được duyệt.

*Đạt:* Job `SUCCEEDED`, GCS có `model.joblib`/`metrics.json`, logs có metrics và image/dataset version.

**Bài 4 — Đánh giá công bằng.** Muốn so AutoML với XGBoost custom.

*Đạt:* Cùng dataset snapshot, split, labels, metrics, tính cả training và inference costs.

**Câu 5.** AutoML có loại bỏ nhu cầu kiểm tra chất lượng dữ liệu không?

*Đáp án:* Không. Dữ liệu/label lỗi sẽ tạo model kém hoặc lệch.

**Câu 6.** `CustomJob` có tự tạo model trong Model Registry sau khi train xong?

*Đáp án:* Không mặc định; cần upload model hoặc TrainingPipeline với modelToUpload.

**Câu 7.** Callback training hay container viết model vào đâu để lưu bền?

*Đáp án:* Cloud Storage, thường dùng `AIP_MODEL_DIR` khi `baseOutputDirectory` được khai báo.

**Câu 8.** Training budget AutoML có là trần của mọi hóa đơn không?

*Đáp án:* Không. Data prep, prediction, storage, networking có phí riêng.

**Câu 9.** 99% accuracy trên dataset có 1% nhãn dương có đủ tốt không?

*Đáp án:* Chưa. Mô hình đoán toàn âm cũng có thể đạt 99%; cần recall/PR-AUC/business impact.

**Câu 10.** Có thể dùng Dockerfile huấn luyện chạy script rồi thoát làm container phục vụ endpoint không?

*Đáp án:* Không. Serving container cần inference server/protocol và artifacts phù hợp.

**Câu 11.** Tăng replicaCount từ 1 lên 4 có tự biến RandomForest script thành distributed training không?

*Đáp án:* Không. Cần mã và framework hỗ trợ phân tán.

**Câu 12.** Có nên đặt service-account JSON key trong training image không?

*Đáp án:* Không. Dùng runtime service account/ADC và IAM ít quyền.

**Câu 13.** Mỗi lần tuning có thể nhìn test accuracy rồi chọn tham số cho lần sau không?

*Đáp án:* Không nên; làm rò rỉ thông tin test vào quá trình chọn model.

**Câu 14.** Model đã train tốt một năm trước có mặc nhiên còn chính xác khi hành vi khách thay đổi?

*Đáp án:* Không. Cần theo dõi drift, metrics với labels mới và retraining có kiểm chứng.

## 20. Checklist production và kết luận

- [ ] Bài toán/label/metric gắn với chi phí sai lầm và business SLO.
- [ ] Đã so sánh AutoML/custom với baseline đơn giản.
- [ ] Dataset đủ rows, schema/target đúng và data leakage đã được loại.
- [ ] Train/validation/test split phù hợp theo thời gian/nhóm và có test holdout.
- [ ] Evaluation gồm metrics tổng + slices, fairness/privacy và calibration khi cần.
- [ ] Training code, container digest, datasets, seeds, parameters và outputs được version hóa.
- [ ] IAM runtime SA ít quyền, artifacts bucket private, không log PII/secrets.
- [ ] CustomJob/TrainingPipeline có output GCS và error/timeout handling.
- [ ] Model Registry/deploy chỉ sau approval, serving container tương thích artifacts.
- [ ] Online/batch prediction được chọn theo latency và chi phí.
- [ ] Có pipeline retraining, validation gates, model rollback và drift monitoring.
- [ ] Data residency/VPC/CMEK/organization policies được kiểm tra theo yêu cầu.
- [ ] Billing tính đủ training, tuning, inference, storage, network và logs.
- [ ] Cleanup lab được thực hiện có kiểm soát, không xóa artifacts dùng chung.

**Kết luận:** **AutoML** giúp có baseline nhanh khi loại dữ liệu và mục tiêu được hỗ trợ; **custom training** giúp sở hữu thuật toán, môi trường, cấu hình tài nguyên và logic đặc thù. Cả hai chỉ tạo giá trị khi **dữ liệu đúng, đánh giá không leakage, đăng ký/triển khai an toàn và theo dõi liên tục chi phí cùng chất lượng**.

## Tài liệu tham khảo chính thức

- [Train tabular classification/regression with AutoML](https://cloud.google.com/vertex-ai/docs/tabular-data/classification-regression/train-model)
- [Prepare tabular classification/regression data](https://cloud.google.com/vertex-ai/docs/tabular-data/classification-regression/prepare-data)
- [Data splits for tabular models](https://cloud.google.com/vertex-ai/docs/tabular-data/data-splits)
- [Vertex AI custom training overview](https://cloud.google.com/vertex-ai/docs/training/overview)
- [Create a custom training job](https://cloud.google.com/vertex-ai/docs/training/create-custom-job)
- [Custom training code requirements](https://cloud.google.com/vertex-ai/docs/training/code-requirements)
- [Export scikit-learn model artifacts](https://cloud.google.com/vertex-ai/docs/training/exporting-model-artifacts)
- [Create a training pipeline](https://cloud.google.com/vertex-ai/docs/training/create-training-pipeline)
- [Configure compute for custom training](https://cloud.google.com/vertex-ai/docs/training/configure-compute)
- [gcloud ai custom-jobs create](https://cloud.google.com/sdk/gcloud/reference/ai/custom-jobs/create)
- [Vertex AI IAM and service agents](https://cloud.google.com/vertex-ai/docs/general/access-control)
- [Vertex AI training and inference pricing](https://cloud.google.com/vertex-ai/pricing)

