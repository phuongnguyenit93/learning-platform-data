# Model Registry và quản lý phiên bản mô hình

> **Chương:** Vertex AI và học máy  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một đội xây mô hình phát hiện gian lận cho đơn hàng. Tuần này, phiên bản mới đạt F1 cao hơn bản đang chạy, nhưng chỉ cần đổi dữ liệu huấn luyện hoặc thứ tự các features là kết quả production có thể thay đổi đáng kể. Nếu chỉ lưu tệp `model.pkl` rồi ghi đè mỗi lần huấn luyện, đội vận hành sẽ không trả lời được: **đang chạy mô hình nào, được huấn luyện từ dữ liệu/commit nào, ai phê duyệt, và nếu phát sinh lỗi thì rollback về đâu?**

**Vertex AI Model Registry** giúp tổ chức các phiên bản của một model và kết nối chúng với quy trình đánh giá, triển khai, theo dõi. Ở những phần tài liệu Google Cloud mới, cùng tính năng có thể xuất hiện dưới tên **Gemini Enterprise Agent Platform Model Registry**; API nền tảng vẫn dùng các tài nguyên `aiplatform.googleapis.com` và lệnh `gcloud ai`. Bài tập trung vào **custom-trained/AutoML models được đăng ký trong Model Registry**, không đánh đồng với vòng đời phiên bản API của Gemini foundation models.

Bài thuộc mô-đun **CLOUD_PROVIDERS_GCP**, nối các kiến thức project/IAM, Cloud Storage, Artifact Registry, Cloud Run/GKE, triển khai và monitoring với vòng đời MLOps.

**Kết quả học tập:**

1. Phân biệt **Model resource**, **model version**, **version ID**, **alias**, **labels**, **Endpoint** và **DeployedModel**.
2. Đăng ký phiên bản đầu tiên và thêm phiên bản mới vào cùng model qua Console, `gcloud` hoặc Python SDK.
3. Thiết kế metadata chứng minh **nguồn gốc artifact, training data, code, evaluation, container**.
4. Sử dụng aliases như `candidate`/`production-approved` và hiểu vai trò đặc biệt của `default`.
5. Lựa chọn phiên bản cụ thể khi triển khai online/batch inference; rollout canary và rollback theo **DeployedModel IDs**, không theo version IDs.
6. Tách quyền train/upload/approve/deploy/predict và tránh lộ dữ liệu/credentials.
7. Xác định cách theo dõi drift, chất lượng, chi phí và cleanup phiên bản không còn sử dụng.
8. Hoàn thành một lab mô phỏng và các bước kiểm chứng an toàn trên project thử nghiệm.

## 1. Vì sao cần Model Registry?

Model Registry là **kho quản trị metadata và phiên bản model**, không chỉ nơi chứa weights. Nó giúp team nhìn được chuỗi **Train → Evaluate → Register → Approve → Deploy → Monitor → Retire**.

~~~mermaid
flowchart LR
  DATA["Dữ liệu train + feature schema"] --> TRAIN["Vertex AI Training\nhoặc pipeline"]
  CODE["Git commit + container digest"] --> TRAIN
  TRAIN --> ART["Model artifacts\nCloud Storage"]
  ART --> REG["Model Registry\nModel + versions"]
  REG --> QA["Evaluation / approval\ncandidate → approved"]
  QA --> EP["Endpoint\nDeployedModel IDs"]
  EP --> OBS["Monitoring + business KPIs"]
  OBS --> DEC{"Giữ, retrain\nhay rollback?"}
  DEC --> TRAIN
  DEC --> EP
~~~

**Bẫy:** Đăng ký xong **không** đồng nghĩa endpoint đã triển khai model. Gán alias `production-approved` cũng **không** đồng nghĩa requests đã chuyển sang phiên bản đó. Chỉ nên coi model “đang chạy” khi đã kiểm tra cấu hình **Endpoint/DeployedModel và traffic split**.

### 1.1. Có nên dùng Model Registry cho mọi model?

| Tình huống | Hướng quản lý |
| --- | --- |
| Mô hình sklearn/PyTorch/TensorFlow do nhóm huấn luyện | Registry + artifact + serving container |
| AutoML model trên Vertex AI | Đọc/đăng ký/triển khai qua Registry theo loại hỗ trợ |
| BigQuery ML models | Có thể liên kết/đăng ký với Registry bằng cơ chế BigQuery ML tương ứng |
| Model Garden models mở | Tùy sản phẩm, upload/deploy hoặc dùng managed API; không tự suy chúng chung một vòng đời |
| Gemini API model như Gemini Flash | Managed foundation-model API có **model identifiers/release lifecycle riêng**, không coi như custom model upload từng version |
| Chỉ chạy thử notebook một lần | Có thể chưa cần deployment, nhưng vẫn lưu training configuration và evaluation nếu cần tái lập |

**Không thay Model Registry bằng Artifact Registry.** Artifact Registry lưu **container images/dependencies**; Model Registry quản lý **model version, provenance và deployment relationship**. Cả hai nên dùng cùng nhau.

## 2. Đúng tên các tài nguyên

~~~mermaid
flowchart TD
  PROJ["Google Cloud project + location"] --> M["Model: fraud-detector\nprojects/.../models/MODEL_ID"]
  M --> V1["Version ID: 1\nalias: stable, default"]
  M --> V2["Version ID: 2\nalias: candidate"]
  M --> V3["Version ID: 3\nalias: experimental"]
  EP["Endpoint: fraud-api"] --> D1["DeployedModel ID: 111\nmodelVersionId: 1"]
  EP --> D2["DeployedModel ID: 222\nmodelVersionId: 2"]
  V1 -. "model@1" .-> D1
  V2 -. "model@2" .-> D2
  D1 --> TS["Traffic split:\n90% → 111; 10% → 222"]
  D2 --> TS
~~~

### 2.1. Resource path và version selector

Ví dụ project `LAB_PROJECT_ID`, location `us-central1`, parent model ID `1234567890123456789`:

~~~text
projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789

projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789@1
projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789@2
projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789@candidate
projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789@default
~~~

- **Parent model ID** định danh một family/model resource.
- **Version ID** do Vertex AI cấp (ví dụ `1`, `2`), trỏ phiên bản cụ thể.
- **Alias** là tên trỏ phiên bản **có thể được chuyển**. Một model version có thể có nhiều aliases.
- Nếu không ghi `@version` hoặc `@alias` khi gọi một số Model APIs, chúng chọn **`default`**.
- **Endpoint ID** khác model ID; **DeployedModel ID** khác cả hai, được dùng trong `traffic_split`.

**Mọi ID phía trên là minh họa.** Sau upload, luôn lấy model ID/version ID thực tế từ response hoặc `gcloud ai models list-version`.

### 2.2. Alias và label khác gì?

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Version ID | `2` | Định danh phiên bản đã đăng ký |
| `default` alias | Chỉ về v1 hoặc v2 | Phiên bản mặc định khi không chỉ định version |
| Custom alias | `candidate`, `reviewed` | Con trỏ dễ dùng trong quy trình |
| Labels | `team=fraud`, `env=lab` | Metadata để lọc/quản trị/cost allocation |
| Version description | `features-v4, training dataset 2026-11` | Ngữ cảnh con người đọc |
| Endpoint deployed model | `id=222; modelVersionId=2` | Thực thể đang chạy prediction trong endpoint |

**Quy tắc alias:**

- Trong mỗi **Model**, một alias phải trỏ tới **tối đa một version** tại một thời điểm; chuyển alias sẽ tháo nó khỏi version cũ.
- **`default`** được gán cho version đầu tiên và **luôn có đúng một** default cho model.
- Custom alias là chuỗi phi số, chữ thường/số/dấu gạch ngang; đừng dùng numeric alias như `123` vì dễ nhầm version ID.
- Một quy tắc format từ API: `[a-z][a-z0-9-]{0,126}[a-z0-9]`. Dùng `candidate` hoặc `production-ready`, không dùng `v_2`.
- Alias **là con trỏ mutable**, không phải phê duyệt bất biến. Audit thay đổi alias và yêu cầu approval riêng.

**Ví dụ:** `candidate` hôm nay có thể trỏ v2, tuần sau trỏ v3. Muốn deployment có thể tái lập, ghi rõ `model@2` và artifact/container digests trong release manifest thay vì chỉ ghi `model@candidate`.

## 3. Model version gồm những gì?

Một version biểu diễn **một tập artifact và cấu hình serving** với metadata giúp tái hiện cách tạo ra model. Thường cần:

| Thành phần | Ví dụ/nguồn | Vì sao lưu |
| --- | --- | --- |
| Parent model & version | `fraud-detector@2` | Định danh chính xác release |
| Artifact URI | `gs://YOUR_BUCKET/models/fraud/v2/` | Weights, vocabulary, preprocess assets |
| Artifact checksum/manifest | SHA-256 từng tệp + object version | Tránh GCS path bị ghi đè khác bytes |
| Serving container image | `REGION-docker.pkg.dev/.../predictor@sha256:DIGEST` | Reproducible runtime code/libraries |
| Training code | Git commit SHA | Biết thuật toán và tiền xử lý |
| Training dataset | Snapshot/version ID, BigQuery snapshot, hash | Phân biệt huấn luyện lại |
| Feature schema | `schema-v4` với names/types/order | Tránh prediction/serving skew |
| Hyperparameters & seed | Learning rate, class weights, seed | Tái lập kết quả gần đúng |
| Evaluation | PR-AUC, precision/recall, p95 latency, slice fairness | So sánh/duyệt |
| Security & ownership | Owner, classification, approval, expiration | Quản trị |
| Deployment manifest | Endpoint/DeployedModel IDs, traffic, timestamp | Rollback kiểm chứng được |

**Cần phân biệt:**

- **Model artifact**: tệp mô hình thực tế nằm ở storage; Registry không tự bảo đảm nguyên vẹn mọi object URI nếu bucket cho phép overwrite.
- **Serving container**: image đáp ứng hợp đồng prediction (health/predict routes, port, runtime). Upload container **không** chứng minh container chạy thành công.
- **Experiment**: một run huấn luyện với metrics/params; không nhất thiết mọi run đều là một version production.
- **Model evaluation**: so sánh với baseline và datasets chuẩn; metrics thuộc đúng dataset/split và version.
- **Model card**: tài liệu giới hạn sử dụng, rủi ro, owner, dữ liệu huấn luyện, fairness và bảo mật. Registry không tự viết model card hoàn chỉnh.

### 3.1. Khi nào tạo version mới?

Nên tạo **version mới** nếu thay đổi có thể ảnh hưởng predictions hoặc runtime, ví dụ: weights, thuật toán, preprocessing, feature order, training dataset/version, serving image hoặc output contract. Thay description/alias để phân loại trạng thái **không** thay thế việc tạo model version khi artifact đổi.

**Không dùng cùng một `gs://.../model.pkl` và ghi đè** để giả làm version mới. Dùng immutable/object-versioned artifact paths, lưu checksums, và pin serving container bằng digest thay cho tag như `latest`.

## 4. Mô hình governance cho các giai đoạn

Ví dụ quy trình promotion:

| Trạng thái nghiệp vụ | Quyền / cửa kiểm tra | Alias (gợi ý) |
| --- | --- | --- |
| Training complete | Pipeline upload artifact, schema/test pass | `candidate` |
| Evaluated | Offline metrics và quality checks được duyệt | `reviewed` |
| Staging | Smoke tests, integration, latency | `staging-ready` |
| Production approved | Human/CI approval, model card hoàn chỉnh | `production-ready` |
| Serving canary | Một DeployedModel nhận 5–10% traffic | Không suy từ alias |
| Serving stable | Endpoint chuyển 100% sang version được chấp thuận | `default` có thể trỏ version này nếu policy yêu cầu |
| Retired | Undeploy, giữ metadata theo retention, xóa có kiểm soát | Xóa alias cũ/đổi trạng thái theo policy |

**Không có nghĩa Model Registry tự enforce các stage này**: aliases chỉ là metadata mutable, không phải workflow approval system. Cần CI/CD, IAM, audit logs, runbook và nguyên tắc tách người phát hành model khỏi người phê duyệt production.

### 4.1. Pipeline phát hành đề xuất

~~~mermaid
flowchart TD
  TRAIN["Train + evaluate\nVertex AI Pipeline"] --> GATE{"Metrics / fairness /\nschema / security đạt?"}
  GATE -- "Không" --> HOLD["Lưu experiment artifact\nKhông promote"]
  GATE -- "Có" --> REG["Upload new version\nRegistry + provenance"]
  REG --> APPROVE["Approval + reviewed alias"]
  APPROVE --> STAGING["Deploy explicit version to staging\nSmoke + load tests"]
  STAGING --> CANARY["Production Endpoint\n5% candidate / 95% stable"]
  CANARY --> HEALTH{"Latency, errors,\nquality, drift đạt?"}
  HEALTH -- "Không" --> RB["Traffic rollback\nstable 100%"]
  HEALTH -- "Có" --> PROMOTE["Gradually increase 20% → 100%\nrecord exact version"]
~~~

**Promotion không được làm mất khả năng truy lại:** ghi đủ version ID, metrics snapshot, Git SHA, dataset version và một biên bản phê duyệt. Không dùng auto-approve chỉ dựa vào một metric có thể thay đổi giữa các dataset.

## 5. Chuẩn bị lab an toàn

| Thông tin | Giá trị minh họa |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Region | `us-central1` (chỉ dùng nếu hỗ trợ model/serving cho lab) |
| Display name | `fraud-detector-lab` |
| Parent model ID | `MODEL_ID_FROM_UPLOAD` |
| Model artifact | `gs://YOUR_BUCKET/models/fraud/v1/` |
| Serving image | `us-central1-docker.pkg.dev/LAB_PROJECT_ID/ml-images/predictor@sha256:REAL_DIGEST` |
| Alias | `candidate` / `production-ready` / `default` |
| Endpoint ID | `ENDPOINT_ID_FROM_CREATE` |
| DeployedModel IDs | `DEPLOYED_V1_ID`, `DEPLOYED_V2_ID` |

Các chuỗi chữ hoa là placeholders, **không phải tài nguyên tồn tại**. GCP IAM, billing, Artifact Registry access, Cloud Storage, region và quotas phải được xác nhận trước khi tạo model/endpoint. **Triển khai online prediction dùng compute có phí** dù request thấp; lab không có ngân sách nên chỉ làm phần mô phỏng.

### 5.1. Preflight read-only bằng gcloud

~~~bash
# Không tạo/sửa tài nguyên; chạy với identity test được cấp phép
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

gcloud ai models list \
  --project=LAB_PROJECT_ID --region=us-central1

gcloud ai endpoints list \
  --project=LAB_PROJECT_ID --region=us-central1

# Nếu đã có model, thay MODEL_ID thực:
gcloud ai models list-version MODEL_ID \
  --project=LAB_PROJECT_ID --region=us-central1

gcloud ai models describe MODEL_ID@2 \
  --project=LAB_PROJECT_ID --region=us-central1

# Nếu đã có endpoint:
gcloud ai endpoints describe ENDPOINT_ID \
  --project=LAB_PROJECT_ID --region=us-central1
~~~

Lệnh `describe MODEL_ID@2` có thể trả `NOT_FOUND` khi model chưa có version 2; đó là dữ liệu lab chưa sẵn sàng, không phải lỗi hệ thống cần cấp Owner. Kiểm tra quyền `aiplatform.models.list/get` và `aiplatform.endpoints.get/list` trên phạm vi phù hợp.

### 5.2. Quyền IAM và nhận dạng

| Principal | Permissions tiêu biểu | Gợi ý |
| --- | --- | --- |
| Training/pipeline SA | `aiplatform.customJobs.create`, model upload/get, GCS artifact write | Cho phép train/upload, **không** tự deploy prod |
| Model reviewer | model get/list, evaluation/metadata read | Không cần model delete |
| Release operator | `aiplatform.endpoints.deploy` và quản lý traffic, model get | Chỉ scope endpoints dự án được cấp |
| Prediction caller | `aiplatform.endpoints.predict` | Không cần model upload/admin |
| Serving runtime SA | Đọc artifacts/secrets khi container cần | Service account riêng, không nhúng keys |
| Cleanup operator | model delete/undeploy được phê duyệt | Không xóa model đang phục vụ |
| Auditor | IAM/metadata, logging/approval read-only | Không cần mutable permissions |

Role predefined `roles/aiplatform.user` chứa nhiều quyền hơn việc đọc/predict ở vài workflows; sản xuất có thể dùng **custom roles** và Resource Manager IAM Conditions nếu được hỗ trợ. Cloud Storage bucket, Artifact Registry image và Vertex AI Model resource là **ba bề mặt quyền riêng**.

**Không cấp service-agent role cho người dùng hoặc runtime SA tùy ý.** Dùng ADC trên Cloud Run/GKE, Workload Identity Federation và service identities do sản phẩm quản lý. Không tải service account JSON key lên notebooks.

## 6. Đăng ký phiên bản đầu tiên vào Model Registry

Để upload **custom model**, cần chuẩn bị **model artifacts** và **serving container** được Vertex AI hỗ trợ. Một tệp `model.pkl` đơn lẻ không đủ để dự đoán nếu container không có preprocessing, thư viện và endpoint handler phù hợp.

### 6.1. Chuẩn bị artifacts có thể kiểm chứng

~~~text
gs://YOUR_BUCKET/models/fraud/v1/
  model.joblib
  feature_schema.json
  preprocessing.json
  model_manifest.json

Serving image:
  us-central1-docker.pkg.dev/LAB_PROJECT_ID/ml-images/predictor@sha256:REAL_DIGEST
~~~

Ví dụ `model_manifest.json` do CI sinh:

~~~json
{
  "model_family": "fraud-detector",
  "release": "candidate-20261119",
  "training_git_sha": "EXAMPLE_GIT_SHA",
  "dataset_snapshot": "bq-snapshot-20261117",
  "feature_schema_version": "4",
  "artifact_sha256": "EXAMPLE_SHA256",
  "serving_image_digest": "sha256:EXAMPLE_DIGEST",
  "evaluation_id": "eval-20261119-01",
  "owner": "ml-platform-team"
}
~~~

Giá trị `EXAMPLE_*` chỉ là placeholders. Lưu manifest và checksums cùng release; riêng chứa manifest **không làm toàn bộ GCS bucket trở thành immutable**. Bảo vệ artifacts bằng IAM, retention/versioning phù hợp và tránh ghi đè path đã phát hành.

### 6.2. Upload model bằng gcloud

~~~bash
# THAY ĐỔI Vertex AI Model Registry: chỉ project LAB, cần artifact/image thật.
# Region của Model resource và quyền truy cập artifacts phải hợp lệ.
gcloud ai models upload \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --display-name=fraud-detector-lab \
  --artifact-uri=gs://YOUR_BUCKET/models/fraud/v1/ \
  --container-image-uri=us-central1-docker.pkg.dev/LAB_PROJECT_ID/ml-images/predictor@sha256:REAL_DIGEST \
  --version-description="baseline features-v4, evaluation approved for lab" \
  --version-aliases=baseline
~~~

Lệnh trên **tạo Model resource mới** khi không có `--parent-model`, với version đầu tiên có `default` alias. Kết quả có thể là operation kéo dài; lấy **MODEL_ID thực tế** từ response/Model Registry. `--version-aliases=baseline` là alias tùy chọn ngoài `default`.

Nếu image chỉ có tag hoặc artifact path không tồn tại, bước upload có thể thất bại. Hợp đồng server container (health/predict route, port, load artifacts) phải phù hợp với framework/Vertex AI prediction requirements. **Upload thành công chưa chứng minh model có thể phục vụ prediction**.

### 6.3. Đọc lại Model ID và version ID

~~~bash
# Chỉ đọc, không tạo/deploy
gcloud ai models list \
  --project=LAB_PROJECT_ID --region=us-central1

# Thay MODEL_ID lấy từ registry
gcloud ai models list-version MODEL_ID \
  --project=LAB_PROJECT_ID --region=us-central1

gcloud ai models describe MODEL_ID@1 \
  --project=LAB_PROJECT_ID --region=us-central1
~~~

Trường metadata cần xác nhận: model resource name, version ID, version aliases, `artifactUri`, container image, description, timestamps và nếu có metadata liên quan training/evaluation. **Display name không bảo đảm unique**: hai model resources khác nhau có thể cùng tên hiển thị. Luôn lưu resource ID đầy đủ.

## 7. Tạo version mới thay vì tạo model family mới

Khi train lại fraud detector với dataset mới hoặc feature schema mới, thường đăng ký **version 2 dưới cùng parent model** để các phiên bản có thể được so sánh và quản lý như một family.

### 7.1. Upload phiên bản 2 bằng gcloud

~~~bash
# THAY ĐỔI: thêm version dưới một Model resource đã có.
# MODEL_ID và artifact URI phải được xác minh trước.
gcloud ai models upload \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --parent-model=projects/LAB_PROJECT_ID/locations/us-central1/models/MODEL_ID \
  --display-name=fraud-detector-lab \
  --artifact-uri=gs://YOUR_BUCKET/models/fraud/v2/ \
  --container-image-uri=us-central1-docker.pkg.dev/LAB_PROJECT_ID/ml-images/predictor@sha256:REAL_DIGEST_V2 \
  --version-aliases=candidate \
  --version-description="candidate: new training data, threshold calibration v2"
~~~

**Khác biệt chủ chốt là `--parent-model`**. Không có nó, lệnh tạo một Model resource mới, không phải version 2 cùng family. Version ID thực tế được API sinh ra, **không được giả định luôn là 2** (ví dụ đã có phiên bản bị xóa).

Nếu training job muốn tự đăng ký version vào Model Registry, tham số parent model cũng phải được truyền ở workflow huấn luyện. Không cần upload thủ công hai lần.

### 7.2. Python SDK làm cùng công việc

Ví dụ dùng SDK `google-cloud-aiplatform`, ứng dụng được xác thực qua ADC và đã có artifacts:

~~~python
from google.cloud import aiplatform

PROJECT = "LAB_PROJECT_ID"
LOCATION = "us-central1"
MODEL_ID = "MODEL_ID"   # Thay bằng ID thực sau khi đăng ký v1

aiplatform.init(project=PROJECT, location=LOCATION)

model = aiplatform.Model.upload(
    display_name="fraud-detector-lab",
    artifact_uri="gs://YOUR_BUCKET/models/fraud/v2/",
    serving_container_image_uri=(
        "us-central1-docker.pkg.dev/LAB_PROJECT_ID/"
        "ml-images/predictor@sha256:REAL_DIGEST_V2"
    ),
    parent_name=(
        f"projects/{PROJECT}/locations/{LOCATION}/models/{MODEL_ID}"
    ),
    version_aliases=["candidate"],
    version_description="features-v4; calibrated threshold; lab test",
    is_default_version=False,
)

print("Registered model resource:", model.resource_name)
~~~

`parent_name` đưa version mới dưới model cũ; `is_default_version=False` **không tự chuyển default** khỏi phiên bản đang được chọn. Đây là lệnh **có tác dụng tạo version**, không thực thi trên project sản xuất khi chưa có phê duyệt.

### 7.3. Xem versions qua Python SDK

~~~python
from google.cloud import aiplatform

aiplatform.init(project="LAB_PROJECT_ID", location="us-central1")
registry = aiplatform.models.ModelRegistry(model="MODEL_ID")

versions = registry.list_versions()
for item in versions:
    print(item)

# Thay VERSION_ID theo kết quả list:
version_info = registry.get_version_info(version="VERSION_ID")
print(version_info)
~~~

Đoạn này chỉ **đọc Model Registry** nhưng cần package/ADC/permissions. Không in toàn bộ model artifacts hoặc dữ liệu training nhạy cảm ra logs.

## 8. Aliases, chuyển default và quy trình phê duyệt

### 8.1. Alias không phải khóa bảo vệ production

Giả sử ban đầu:

| Model version | Aliases | Trạng thái nghiệp vụ |
| --- | --- | --- |
| v1 | `default`, `production-ready` | Đang được phê duyệt |
| v2 | `candidate` | Đang kiểm thử |
| v3 | `experimental` | Chưa đạt metrics |

Sau offline evaluation, người có quyền có thể **di chuyển `production-ready` sang v2**. Điều này chỉ đổi **registry metadata**. Nếu endpoint đang chạy `DeployedModel ID 111` là v1, traffic **không tự chuyển** sang v2 chỉ vì alias đổi.

**Quy trình an toàn:** approve v2 → deploy v2 rõ version → canary → đo → 100% v2 → chuyển `default/production-ready` theo chính sách → cập nhật release manifest. Có thể đặt `production-ready` sau khi phê duyệt và trước deployment nếu data contract gọi đó là “ready”, nhưng **đừng gọi nó “serving”**.

### 8.2. Thao tác qua Console

1. Mở **Model Registry** trong Google Cloud Console (giao diện có thể nằm dưới Agent Platform).
2. Chọn đúng **project/region** và **Model resource**, mở danh sách các phiên bản.
3. Chọn version đã đánh giá, dùng **Edit alias / Add alias** để thêm `reviewed` hoặc di chuyển `candidate`.
4. Nếu được phép, chọn **Set as default** để chuyển `default` sang version đã được duyệt.
5. Đọc lại danh sách versions và audit event; đừng chỉ dựa vào toast “Saved”.
6. Kiểm tra endpoint riêng để biết version nào đang nhận prediction traffic.

**Cảnh báo:** `default` luôn phải tồn tại và chỉ có một trong cùng Model resource. Chuyển `default` có thể khiến các **lệnh deploy sau này không pin version** chọn phiên bản khác; vì vậy CI/CD nên luôn pin `@VERSION_ID`.

### 8.3. Phân biệt thay alias với rollback thật

~~~text
Registry:
  default  ──> v2
  candidate ──> v3

Endpoint:
  DeployedModel 111 ──> v1, 90% traffic
  DeployedModel 222 ──> v2, 10% traffic
~~~

Nếu bạn chuyển alias `default` về v1 nhưng **traffic split vẫn 90/10**, endpoint vẫn đang phục vụ v1/v2 theo split đó. **Rollback thật là thay traffic của Endpoint** sang DeployedModel đã được xác minh, rồi mới chỉnh aliases/metadata nếu quy trình yêu cầu. Điều này được phản ánh trong thuộc tính `Endpoint.deployedModels[*].modelVersionId` và `Endpoint.trafficSplit`.

## 9. Đánh giá versions trước khi cấp traffic

Một model có F1 cao hơn không chắc đáng triển khai: có thể gây latency, thiếu khả năng giải thích, tỷ lệ false positives ở nhóm quan trọng tăng hoặc dùng features không có trên production.

### 9.1. Quality gate tham khảo

| Chỉ số | v1 baseline (giả định) | v2 candidate (giả định) | Điều kiện |
| --- | ---: | ---: | --- |
| PR-AUC trên holdout | 0,81 | 0,84 | Không giảm |
| Recall ở precision ≥ 0,95 | 0,64 | 0,68 | Tăng hoặc đạt ngưỡng |
| False positive rate cho nhóm rủi ro | 1,4% | 1,2% | Không vượt ngưỡng công bằng |
| Predict latency p95 | 110 ms | 138 ms | ≤ 160 ms |
| Memory/container | 1,2 GiB | 1,8 GiB | Hợp machine/replicas |
| Feature schema | v3 | v4 | Backend đã triển khai v4 |
| PII compliance | PASS | PASS | Không bỏ qua |
| Training reproducibility | PASS | PASS | Manifest + dataset snapshot |

**Đây không phải chuẩn bắt buộc của Vertex AI.** Ngưỡng phải được đội nghiệp vụ và ML owner quyết định dựa trên tỷ lệ gian lận, chi phí false positives, drift và SLO. Ví dụ accuracy cao trên dataset mất cân bằng là không đủ.

### 9.2. Test trước deploy

- **Unit/schema tests:** input/output shape, missing values, unknown categories, timezone, numeric ranges.
- **Offline tests:** holdout tách theo thời gian, tránh training leakage; PR-AUC, calibration, class-weighted metrics.
- **Slice/fairness tests:** theo loại khách, khu vực hoặc nhóm nghiệp vụ có ý nghĩa, theo chính sách quyền riêng tư.
- **Security tests:** kiểm tra serving image vulnerabilities, dependencies, secret handling, IAM.
- **Integration tests:** phiên bản API/feature store/serving container tương thích.
- **Load tests:** throughput, p95/p99, cold start, autoscaling, memory/GPU quota.
- **Approval record:** người duyệt, thời gian, version, metrics report URI, ticket ID.

Có thể lưu đánh giá bằng Vertex AI Model Evaluation và Vertex AI Experiments/ML Metadata khi loại model/hạ tầng hỗ trợ. Đừng tự đưa metrics test vào description mà không lưu **dataset và phương pháp đánh giá**, vì hai con số không cùng mẫu không có ý nghĩa so sánh.

## 10. Deploy phiên bản rõ ràng vào endpoint

**Endpoint** là tài nguyên nhận prediction requests. Mỗi lần deploy một model version vào endpoint sẽ tạo một **DeployedModel** với ID riêng; endpoint có thể có nhiều DeployedModels cùng lúc khi được hỗ trợ và có đủ compute quota.

### 10.1. Tạo endpoint (lab, có thể phát sinh phí khi deploy)

~~~bash
# THAY ĐỔI tài nguyên, chỉ project lab
gcloud ai endpoints create \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --display-name=fraud-detector-lab-endpoint
~~~

Lấy `ENDPOINT_ID` thực tế từ kết quả; không giả định display name là ID.

### 10.2. Deploy v1 theo version ID

~~~bash
# TẠO DeployedModel và cấp serving machines (CÓ PHÍ).
# MODEL_ID@1 là minh họa; dùng VERSION_ID thật đã được phê duyệt.
gcloud ai endpoints deploy-model ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --model=MODEL_ID@1 \
  --display-name=fraud-v1 \
  --machine-type=n1-standard-4 \
  --min-replica-count=1 \
  --max-replica-count=2
~~~

Phải kiểm tra loại custom model/container tương thích `n1-standard-4`, quota máy và region. Một số model có yêu cầu GPU/memory/image khác. **Endpoint có deployment đang chạy thường phát sinh compute cost ngay cả khi ít requests.**

### 10.3. Deploy v2 nhưng chưa cấp production traffic

~~~bash
# THAY ĐỔI endpoint: thêm DeployedModel candidate (CÓ PHÍ).
# Xác minh các flags deploy/traffic trước trên gcloud bản đang cài.
gcloud ai endpoints deploy-model ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --model=MODEL_ID@2 \
  --display-name=fraud-v2-candidate \
  --machine-type=n1-standard-4 \
  --min-replica-count=1 \
  --max-replica-count=2 \
  --traffic-split=DEPLOYED_V1_ID=100
~~~

**Chú ý:** `DEPLOYED_V1_ID` phải là **DeployedModel ID hiện tại** (không phải model version ID) và endpoint phải đang có v1. Phần traffic split của deploy call có thể **ghi đè map hiện tại**; phải đọc endpoint và kiểm tra CLI/API response trước khi dùng ở production. Nếu muốn giữ v2 ở 0% trước khi canary, cần xác nhận endpoint cho phép deployment **không tự nhận traffic** và test bằng cách định tuyến cụ thể theo DeployedModel ID khi supported.

### 10.4. Xác minh deployed version IDs

~~~bash
# Chỉ đọc
gcloud ai endpoints describe ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1
~~~

Trong output cần tìm:

~~~yaml
# VÍ DỤ minh họa, không phải response từ project thật
deployedModels:
  - id: "111"
    displayName: fraud-v1
    model: projects/LAB_PROJECT_ID/locations/us-central1/models/MODEL_ID
    modelVersionId: "1"
  - id: "222"
    displayName: fraud-v2-candidate
    model: projects/LAB_PROJECT_ID/locations/us-central1/models/MODEL_ID
    modelVersionId: "2"
trafficSplit:
  "111": 100
  "222": 0
~~~

**Nguồn sự thật khi release online là `modelVersionId` trong DeployedModel và `trafficSplit`**, không phải `default` alias hiện tại. Đây là ví dụ cấu trúc; API response thực tế có thêm machine/resources, state và annotations.

## 11. Canary và rollback bằng traffic split

Một chiến lược phổ biến:

| Giai đoạn | v1 deployed ID 111 | v2 deployed ID 222 | Điều kiện chuyển |
| --- | ---: | ---: | --- |
| Stable | 100% | 0% | v2 sẵn sàng |
| Canary 1 | 95% | 5% | Latency, error, skew kiểm chứng |
| Canary 2 | 80% | 20% | Không suy giảm SLO |
| Promote | 0% | 100% | Approval và metrics đạt |
| Rollback | 100% | 0% | Điều kiện dừng/cảnh báo |

### 11.1. Lệnh chuyển traffic ở mức endpoint

~~~bash
# THAY ĐỔI PRODUCTION TRAFFIC nếu endpoint là production.
# Thay đúng các DeployedModel IDs vừa lấy từ endpoint describe.
gcloud ai endpoints update ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --traffic-split=111=95,222=5
~~~

Cú pháp dùng **DeployedModel IDs**, ví dụ ở đây `111/222`. Không truyền `@1`, `@candidate` hoặc Model Registry version IDs thay thế. Tổng các tỷ lệ phải là **100**. Ghi lại split trước khi thay để có rollback nhanh.

### 11.2. Rollback phải thực hiện được khi cần

~~~bash
# THAY ĐỔI traffic; chỉ khi v1 vẫn được deploy, khỏe và có capacity
gcloud ai endpoints update ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --traffic-split=111=100,222=0
~~~

Sau rollback:

1. Đọc lại `Endpoint.trafficSplit` và `deployedModels[*].modelVersionId`.
2. Gửi **synthetic inference** qua endpoint và kiểm tra response/error/latency.
3. Kiểm tra dashboards và metrics theo **DeployedModel**.
4. Đối soát requests đang bay dở; không giả định mọi lời gọi trước thời điểm đổi đều dùng v1.
5. Ghi incident/canary result; giữ v2 để điều tra, không xóa vội.
6. Nếu muốn, di chuyển alias `default`/`production-ready` về v1 theo policy **sau** khi traffic ổn.

**Đừng undeploy v1 ngay khi canary bắt đầu.** Nó là rollback target. Nhưng cũng đừng giữ hai models phục vụ 24/7 vô hạn nếu không có lợi ích, vì cả hai tiêu thụ serving resources.

### 11.3. Version alias có thể là đầu vào của deploy, không phải traffic router

Google Cloud Model API hỗ trợ `model@2` hoặc `model@golden` khi truy cập/triển khai một version. Khi đã triển khai, API cung cấp **`DeployedModel.modelVersionId`** là output-only version ID thực tế. Do đó:

- Định danh một release bằng **version ID** trong manifest.
- Có thể dùng alias để tìm candidate, nhưng **resolve alias trước khi deploy** và kiểm tra lại output.
- Không suy từ alias đã chuyển mà deployed runtime tự hot-swap weights hoặc chuyển request sang version khác.
- Nếu rollback version đã bị undeploy, phải **deploy lại** và tính thời gian provisioning/quota; đổi alias không tạo lại resources.

## 12. Quan sát mô hình sau khi triển khai

Một model có metrics offline tốt vẫn có thể gây lỗi trên production vì **feature skew**, dữ liệu thay đổi theo mùa, schema khác, timeout hoặc serving image thiếu dependency. Monitoring phải nhìn vào **cả hạ tầng và chất lượng mô hình**.

### 12.1. Ba nhóm tín hiệu

| Nhóm | Metrics / bằng chứng | Hành động |
| --- | --- | --- |
| **Serving SLO** | Requests/s, 4xx/5xx, p50/p95/p99 latency, CPU/memory, accelerator utilization, autoscaling | Theo dõi canary/rollback |
| **Data quality/skew/drift** | Null/unknown feature rate, schema mismatch, phân phối feature so với training/reference | Kiểm tra input pipeline/retrain |
| **Business/model quality** | Precision/recall/F1, calibration, false positive cost, fairness slices sau khi có nhãn thực | Đánh giá chất lượng/version promotion |

**Skew khác drift:** skew so sánh dữ liệu/feature **training và serving**; drift là sự thay đổi phân phối input **theo thời gian**. Hai khái niệm có quan hệ nhưng không đồng nhất; thiếu ground-truth labels thì drift score **không tự khẳng định** model chính xác hay sai.

### 12.2. Canary có ý nghĩa thống kê

Ví dụ v2 nhận 5% traffic nhưng chỉ có 10 requests, việc chưa thấy lỗi không đủ để promote. Thiết kế cần:

- Thời gian/sample size tối thiểu theo volume và failure rate.
- So sánh theo **DeployedModel ID**; không chỉ aggregate endpoint.
- Kiểm tra user segments quan trọng và thời điểm cao điểm/thấp điểm.
- Xác định p95/p99 và error budget trước khi rollout.
- **Delayed labels:** phát hiện gian lận có thể cần nhiều ngày mới có nhãn; không dùng vài phút canary để khẳng định PR-AUC production tốt hơn.
- Nếu thay đổi routing khiến traffic không chia ngẫu nhiên (ví dụ canary chỉ khách nội bộ), ghi rõ bias khi kết luận.

Nếu triển khai version mới bằng same endpoint, đảm bảo dashboards/observability phân biệt version ID và traffic allocation. Prediction logging có thể chứa dữ liệu khách hàng; bật theo **chính sách retention/PII**, dùng sampling khi phù hợp.

### 12.3. Runbook khi chất lượng giảm

~~~text
Alert: production model degradation
  1. Xác định Endpoint ID và DeployedModel ID nào bị ảnh hưởng.
  2. Kiểm tra rollout/feature schema/source data thay đổi gần đây.
  3. Phân loại: serving error/latency, drift, hay business metric.
  4. Nếu vượt rollback gate: chuyển traffic về deployed stable.
  5. Xác minh trafficSplit, inference response, p95, 5xx.
  6. Lưu metrics và version manifest; không xóa candidate vội.
  7. Root cause → sửa dữ liệu/code → tạo version mới để đánh giá lại.
~~~

Đừng âm thầm **ghi đè artifacts tại cùng URI** để “vá model đang chạy”. Điều đó phá khả năng xác minh release và có thể gây hiệu ứng khác nhau giữa replicas/cache.

## 13. Chi phí và bảo mật trong vòng đời Model Registry

### 13.1. Tổng chi phí không chỉ là Registry

| Tầng | Khoản chi | Cách kiểm soát |
| --- | --- | --- |
| Training/tuning | Custom training CPU/GPU/TPU, pipelines | Chạy theo lịch/on-demand, kiểm tra quota |
| Artifacts | GCS bytes, object versions, network egress | Retention có phê duyệt, không nhân bản vô hạn |
| Container images | Artifact Registry storage/scanning | Pin digest, retention và image cleanup |
| Online inference | Dedicated endpoint replicas/machines/accelerators | Autoscaling theo SLO, gỡ unused deployments |
| Batch prediction | Job compute/output storage | Theo batch có deadline, tránh chạy lại không cần |
| Evaluation/monitoring | Model Monitoring, BigQuery logs, metadata, alerts | Sampling, retention, budgets |
| Networking | Cross-region traffic, private networking, egress | Đặt gần data/clients, kiểm tra residency |

Không giả định “chỉ đổi alias nên model mới miễn phí” nếu trước đó đã deploy thêm một DeployedModel có máy phục vụ. Ngược lại, một version **chỉ đăng ký nhưng không deploy** thường không tốn online serving compute; vẫn có storage và chi phí liên quan các thành phần khác.

### 13.2. Bề mặt dữ liệu nhạy cảm

- **Training data:** PII/secrets, consent, data residency và retention.
- **Feature logs:** request/response có thể chứa thông tin khách hàng; cần masking/sampling.
- **Model artifacts:** có thể tiết lộ mẫu huấn luyện; hạn chế GCS access và tải về.
- **Container:** kiểm soát dependencies, image provenance, malware/vulnerability scans.
- **Registry metadata:** version descriptions, experiment links và labels không nên chứa credentials.
- **Serving endpoint:** xác thực IAM, network restrictions và rate limits phù hợp, không để API công khai ngoài policy.

**Phân biệt IAM:** người có quyền list/read model metadata không mặc nhiên có quyền xem training dataset hay tải mọi GCS objects. Mỗi lớp có IAM riêng; ngược lại granting `roles/storage.objectViewer` rộng trên artifact bucket có thể vượt ý định kiểm soát Registry.

## 14. Retention, archive và xóa version an toàn

Không xóa version đang là rollback target trước khi kết thúc canary và thời hạn hỗ trợ. Cũng không giữ mọi endpoint deployment mãi vì sẽ phát sinh phí.

### 14.1. Quy trình retirement

1. Xác định version ID, aliases và **các endpoints đang deploy version đó**.
2. Đảm bảo traffic hiện tại của version sẽ xóa đã về **0%** và có stable replacement.
3. **Undeploy** DeployedModel khỏi các endpoints theo change window; kiểm tra không còn requests phụ thuộc.
4. Lưu model card, training/eval provenance và release manifests theo retention.
5. Kiểm tra model version đã **không** cần cho batch prediction, scheduled jobs hoặc rollback.
6. Chỉ khi được phê duyệt mới xóa version; kiểm tra side effects tới evaluation records/aliases.
7. Kiểm tra riêng GCS artifacts, container images, logs/monitoring và IAM; **xóa registry version không mặc định chứng minh mọi bản sao artifacts đã bị xóa**.

### 14.2. Lệnh có tính phá hủy — chỉ là ví dụ

~~~bash
# CẢNH BÁO: LỆNH XÓA VERSION, KHÔNG CHẠY TRÊN PRODUCTION
# Chỉ sau khi undeploy, xác nhận VERSION_ID và có approval.
gcloud ai models delete-version MODEL_ID@VERSION_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1
~~~

Nếu xóa **toàn bộ Model resource**, tất cả versions/evaluation liên quan có thể bị xóa, và một model đang deploy không thể xóa trước khi undeploy. Khi xóa version chứa alias `default`, dịch vụ có thể gán nó sang version còn lại; không dựa vào hành vi này để tự động promotion. **Không** dùng xóa version làm rollback traffic.

## 15. Bài lab mô phỏng — không cần cloud resources

Bài mô phỏng giúp hiểu sự độc lập giữa **aliases** và **Endpoint traffic** trước khi thao tác thật. Chạy trên Python tiêu chuẩn trong môi trường lab nếu được phép; **không gọi API Google Cloud, không tạo máy có phí**.

### 15.1. Tình huống

- Registry có model `fraud-detector` với v1/v2.
- `default` trỏ v1, `candidate` trỏ v2.
- Endpoint có DeployedModel ID 111 = v1; ID 222 = v2.
- Traffic ban đầu 90% v1 và 10% v2.
- Người duyệt chuyển `default` từ v1 sang v2 nhưng chưa thay endpoint.

**Câu hỏi:** Bao nhiêu phần trăm requests tiếp tục dùng v1? **Đáp án 90%**.

### 15.2. Mã Python mô phỏng có thể chạy độc lập

~~~python
# Không sử dụng Vertex AI SDK, chỉ mô phỏng các con trỏ.
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelVersion:
    version_id: int
    pr_auc: float

versions = {
    1: ModelVersion(version_id=1, pr_auc=0.81),
    2: ModelVersion(version_id=2, pr_auc=0.84),
}
aliases = {"default": 1, "candidate": 2}
deployed_models = {111: 1, 222: 2}  # DeployedModelID -> versionID
traffic_split = {111: 90, 222: 10}

def serving_distribution(split):
    assert sum(split.values()) == 100, "Traffic phải cộng 100%"
    return {
        deployed_models[deployment_id]: percent
        for deployment_id, percent in split.items()
    }

print("Before:", serving_distribution(traffic_split))
aliases["default"] = 2
print("After moving default:", serving_distribution(traffic_split))

# Canary được approved -> đổi traffic ở Endpoint (không phải Registry)
traffic_split = {111: 80, 222: 20}
print("Canary:", serving_distribution(traffic_split))

# Lỗi serving -> rollback Endpoint
traffic_split = {111: 100, 222: 0}
print("Rollback:", serving_distribution(traffic_split))
~~~

Kết quả mong đợi:

~~~text
Before: {1: 90, 2: 10}
After moving default: {1: 90, 2: 10}
Canary: {1: 80, 2: 20}
Rollback: {1: 100, 2: 0}
~~~

**Giới hạn mô phỏng:** Không mô tả provisioning, request routing thực tế, traffic weights trong rolling windows hoặc consistency của endpoint API. Mục tiêu là kiểm tra **đúng loại định danh và logic thay đổi**.

### 15.3. Lab có Vertex AI sandbox (tùy chọn)

| Bước | Thao tác | Bằng chứng |
| --- | --- | --- |
| 1 | Chọn project, region, Vertex AI API, billing/quota | Screenshot hoặc command output chỉ đọc |
| 2 | Liệt kê Models/versions với `gcloud ai models list/list-version` | Model ID, version IDs thật |
| 3 | So sánh metadata v1/v2 | Artifact URIs, serving image, descriptions |
| 4 | Đánh giá/đọc model card và approval | Metrics + dataset/slice rõ |
| 5 | Gán `candidate` rồi chuyển `default` trong **lab** | Alias table trước/sau |
| 6 | Nếu được duyệt tạo Endpoint + hai deployments | DeployedModel IDs và `modelVersionId` |
| 7 | Canary 95/5, rồi 80/20 khi metrics đạt | TrafficSplit thật và dashboards |
| 8 | Mô phỏng lỗi bằng giả định, rollback 100/0 | Readback cấu hình sau rollback |
| 9 | Tính chi phí endpoint/GCS/Artifact Registry | Dự toán và Billing |
| 10 | Cleanup sau approval, không xóa model dùng chung | Không còn idle deployments có phí |

**Không chủ động làm hỏng endpoint hoặc chạy fuzz/traffic quá mức để tạo lỗi.** Khi không có sandbox, hoàn thành mô phỏng ở mục 15.2 và bảng đánh giá là đủ.

## 16. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `PERMISSION_DENIED` khi upload | Thiếu `aiplatform.models.upload` hoặc GCS/image access | Runtime SA, bucket IAM, Artifact Registry |
| Upload tạo model mới thay vì version | Quên `--parent-model`/`parent_name` | Model ID thực tế, upload request |
| List Model có nhiều tên giống nhau | Display name không unique | Dùng resource ID, project/region |
| Dùng alias số như `2` | Nhầm version ID và alias format | Chọn custom alias chữ, dùng `@2` khi cần |
| Chuyển alias nhưng predictions không đổi | Endpoint DeployedModel chưa đổi | `Endpoint.trafficSplit`, `modelVersionId` |
| Deploy ra version không mong muốn | Bỏ `@version` nên dùng `default` | Pin `model@VERSION_ID` và readback |
| DeployedModel 403 | Caller thiếu `endpoints.predict` | IAM caller; không cấp quyền upload |
| Container unhealthy | Sai health/predict route, missing dependency/artifact | Container logs, serving contract |
| Error p95 tăng ở canary | v2 nặng hơn, CPU/GPU thiếu, feature fetch chậm | P95 theo version/replica và quotas |
| Offline metrics tốt nhưng prod lỗi | Feature schema/skew, leakage hoặc drift | Dataset snapshots, serving input validation |
| Cannot delete model/version | Vẫn đang deploy ở endpoint | Đọc endpoint, undeploy theo approval |
| Sai version khi rollback | Dùng Model version ID thay DeployedModel ID | Endpoint describe và mapping IDs |
| Chi phí tăng sau promotion | Hai deployments chạy song song nhiều ngày | Billing, min replicas, cleanup |
| GCS artifact URI thay đổi | Overwrite object/tag và thiếu checksum | Manifest, object generation, image digest |

**Thứ tự điều tra:** project/region → Model resource/version ID → alias/default → artifact/container → Endpoint/DeployedModel ID → traffic split → IAM/network → metrics/data quality → cost.

## 17. Câu hỏi ôn tập

1. **Model Registry dùng để làm gì?** Quản lý tập model versions, metadata, evaluation và khả năng triển khai.
2. **Model resource và model version khác nhau?** Resource là parent/family, version là một bộ artifacts/config riêng bên trong.
3. **Tại sao không ghi đè `model.pkl`?** Mất reproducibility, khó rollback và đối soát.
4. **Version ID và alias khác nhau?** Version ID định danh phiên bản; alias có thể chuyển sang version khác.
5. **`default` có luôn trỏ version mới nhất?** Không; có thể di chuyển, phải kiểm tra.
6. **Một model có bao nhiêu `default`?** Chính xác một.
7. **Hai versions trong cùng Model có thể giữ cùng alias?** Không tại cùng thời điểm.
8. **Model version ID `2` có phải DeployedModel ID `222`?** Không.
9. **Chuyển alias có tự chuyển online traffic?** Không.
10. **Trường nào cho biết version được Endpoint deploy?** `deployedModels[*].modelVersionId`.
11. **Trường nào cho biết tỷ lệ request?** `Endpoint.trafficSplit`.
12. **Cách đăng ký version mới dưới parent hiện có?** `--parent-model` hoặc SDK `parent_name`.
13. **Vì sao cần Git SHA và dataset snapshot?** Tái hiện huấn luyện và giải thích khác biệt metrics.
14. **Vì sao pin container digest?** Tránh image tag đổi nội dung khi deploy lại.
15. **Model F1 cao hơn có đủ để promote?** Không; cần đánh giá dữ liệu, fairness, calibration, latency, chi phí.
16. **Tại sao chỉ nhìn drift chưa đủ để kết luận chất lượng?** Drift không trực tiếp đo ground-truth correctness.
17. **Rollback khi v1 đã undeploy có cần gì?** Deploy lại, quota/capacity và thời gian provisioning.
18. **Có thể xóa version còn đang deploy?** Phải undeploy trước.
19. **Ai nên được phép cập nhật production endpoint?** Release operator được phê duyệt, không phải mọi training SA.
20. **Model Garden model update có tự cập nhật uploaded version?** Không mặc định; phải kiểm tra/đăng ký/triển khai phiên bản mới theo sản phẩm.

## 18. Checklist production và tài liệu chính thức

- [ ] Model family, project, region, version IDs được quản lý rõ.
- [ ] Artifacts lưu dưới đường dẫn versioned, checksum/object generation; container pin digest.
- [ ] Gắn training code commit, data snapshot, feature schema, hyperparameters và evaluation ID.
- [ ] Có Model Registry versions và description/aliases có ý nghĩa; không dùng `default` như release ID bất biến.
- [ ] Review data leakage, drift, fairness, input/output schema và compliance trước approval.
- [ ] CI/CD tách quyền train/register/approve/deploy/predict.
- [ ] Release manifest pin `model@VERSION_ID` và ghi `DeployedModel ID` thực tế.
- [ ] Deploy staging + smoke/load tests trước production.
- [ ] Canary có traffic percentages, sample size/observation window, p95/error/quality gates.
- [ ] Rollback target vẫn deploy và đủ capacity cho đến hết change window.
- [ ] Monitor phục vụ theo version, xác nhận feature skew/drift và delayed labels.
- [ ] Endpoint IAM/network, serving image credentials và logging privacy đã review.
- [ ] Costs: training, GCS artifacts, image storage, serving replicas, monitoring và logs.
- [ ] Không xóa Model/version/aliases/deployments khi chưa đối soát dependencies và retention.
- [ ] Có backup/provenance/rollback evidence, release owner và incident runbook.

**Nguồn Google Cloud chính thức:**

- [Introduction to Model Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/introduction) — quản lý custom/AutoML/BigQuery ML models.
- [Model versioning with Model Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/versioning) — upload/train/list versions.
- [How to use model version aliases](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/model-alias) — default/custom aliases và thay đổi.
- [Delete a model or version](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/delete-model) — undeploy, retention và rủi ro xóa.
- [REST: models.get](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/projects.locations.models/get) — cú pháp `model@version`, `model@alias`.
- [REST: Endpoint DeployedModel](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/projects.locations.endpoints) — `modelVersionId`/`trafficSplit`.
- [gcloud ai models upload](https://docs.cloud.google.com/sdk/gcloud/reference/ai/models/upload) — `--parent-model`, `--version-aliases`.
- [gcloud ai models list-version](https://docs.cloud.google.com/sdk/gcloud/reference/ai/models/list-version) — liệt kê versions.
- [gcloud ai endpoints deploy-model](https://docs.cloud.google.com/sdk/gcloud/reference/ai/endpoints/deploy-model) — deploy model version.
- [gcloud ai endpoints update](https://docs.cloud.google.com/sdk/gcloud/reference/ai/endpoints/update) — thay traffic split.
- [Vertex AI IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/aiplatform) — model/endpoint permissions.
- [Vertex AI Model Monitoring](https://docs.cloud.google.com/vertex-ai/docs/model-monitoring/overview) — skew/drift và quan sát.
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) — training/inference/monitoring.

**Ghi nhớ:** **Model Registry quản lý phiên bản và aliases; Endpoint quản lý DeployedModels và traffic.** Hãy đăng ký artifacts theo version không bị ghi đè, lưu đủ training/evaluation provenance, pin phiên bản khi deploy, chỉ promote qua quality gates và rollback bằng **traffic split của endpoint**. Việc gán `default` hay `production-ready` không thay thế bước triển khai hay kiểm chứng phiên bản thực sự đang phục vụ.
