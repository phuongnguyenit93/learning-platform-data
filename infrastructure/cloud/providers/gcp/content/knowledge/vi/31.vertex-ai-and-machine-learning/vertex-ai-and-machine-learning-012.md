# MLOps với Artifact Registry và CI/CD trên GCP

Một nhóm xây dịch vụ Java `fraud-api` trên Cloud Run để phát hiện đơn hàng bất thường. Data scientist huấn luyện mô hình Python trên Vertex AI, nhưng sau mỗi lần sửa mã, nhóm phải thủ công cài thư viện, build image, chạy train, chép file model rồi thay phiên bản đang phục vụ. Kết quả: khó biết model production đã dùng **commit, dữ liệu, thư viện và cấu hình nào**, khó quay về bản cũ và có nguy cơ phát hành mô hình không đạt chất lượng.

**MLOps** kết hợp quản lý dữ liệu, mã huấn luyện, model artifacts, kiểm thử, phát hành và giám sát. Trên Google Cloud, một kiến trúc phổ biến là **Git → Cloud Build → Artifact Registry → Vertex AI training/pipelines → Model Registry → prediction endpoint hoặc batch prediction**. Trong đó **Artifact Registry giữ container và mẫu pipeline**, còn **Vertex AI Model Registry quản lý tài nguyên và phiên bản mô hình**. Chúng không thay thế nhau.

Bài thuộc chương **Vertex AI và học máy** của mô-đun `CLOUD_PROVIDERS_GCP`, kết nối tổ chức project/IAM/VPC với Cloud Storage, BigQuery, Cloud Run, GKE, Compute Engine và tự động hóa phát hành, độ tin cậy, chi phí. Ví dụ dùng **Python 3.11, scikit-learn, Cloud Build và Vertex AI CustomJob**; ứng dụng Java chỉ là một consumer dự đoán. Những ví dụ tạo tài nguyên cloud chỉ dành cho **project lab có ngân sách** và chưa được thực thi trong bài viết này.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **CI mã/model container**, **CD của model**, **CT (continuous training)** và **monitoring**.
2. Hiểu vị trí của **Artifact Registry, Cloud Build, Vertex AI Pipelines, Model Registry và Endpoint**.
3. Viết kiểm thử, Dockerfile và `cloudbuild.yaml` để tạo image huấn luyện có thể truy vết.
4. Dùng **tag để nhận diện bản build** và **image digest để chạy đúng bytes đã kiểm duyệt**.
5. Cấp quyền riêng cho build service account, training runtime service account và deployer.
6. Khởi chạy một **CustomJob từ image đã build**, lưu model và metrics vào Cloud Storage.
7. Thiết kế **quality gate, manual approval, canary rollout và rollback**.
8. Theo dõi lineage, drift, logs, model SLO và **toàn bộ chi phí** của vòng đời ML.

## 1. Kiến trúc MLOps end-to-end

~~~mermaid
flowchart LR
    GIT["Git commit / PR"] --> CI["Cloud Build CI<br/>test, scan, build"]
    CI --> AR["Artifact Registry<br/>training image @sha256"]
    AR --> TRAIN["Vertex AI CustomJob<br/>hoặc Pipelines"]
    DATA[("GCS / BigQuery<br/>versioned dataset")] --> TRAIN
    TRAIN --> ART[("GCS model artifacts<br/>metrics + model")]
    ART --> GATE{"Evaluation / quality gate"}
    GATE -->|Pass + approval| REG["Vertex AI Model Registry"]
    REG --> DEPLOY["Staging → canary → production<br/>Endpoint / batch"]
    GATE -->|Fail| STOP["Không phát hành<br/>review/retrain"]
    DEPLOY --> MON["Monitoring: latency / drift / KPI"]
    MON -->|cần retrain| TRAIN
~~~

**Bốn loại đầu ra phải quản lý riêng:**

| Tài sản | Nơi lưu điển hình | Định danh phiên bản |
| --- | --- | --- |
| Mã huấn luyện | Git | **Commit SHA** và review |
| Training/serving container | **Artifact Registry Docker repo** | Image **digest `sha256:...`** |
| Model files và metrics | **Cloud Storage** | URI cố định, checksum, run ID, dataset version |
| Model được đăng ký | **Vertex AI Model Registry** | Model resource + **version ID/alias** |
| Pipeline template (nếu dùng KFP) | Git và **Artifact Registry KFP repository** | Template version/digest |

**Không dùng `trainer:latest` làm định danh production.** Tag có thể được chuyển sang image khác nếu repository cho phép mutable tags. Digest xác định đúng nội dung image; đồng thời **model artifact và dataset vẫn phải được version hóa riêng**.

## 2. CI, CD và CT: khi nào kích hoạt từng việc?

| Giai đoạn | Trigger | Việc nên làm | Điều không nên mặc định |
| --- | --- | --- | --- |
| **CI** | Pull request, merge, commit | Lint, unit tests, schema tests, build, dependency/vulnerability scan | Train model tốn GPU cho mọi PR |
| **CD – training** | Merge được duyệt, tag release, lịch hoặc data drift có kiểm soát | Chạy Vertex AI CustomJob/Pipeline, lưu metrics/model | Tự deploy khi job `SUCCEEDED` |
| **CD – serving** | Quality gate + người/luồng phê duyệt | Register, deploy staging, smoke test, canary, promote | Chuyển 100% traffic ngay |
| **CT** | Dữ liệu/nhãn mới, lịch hoặc performance giảm | Train trên snapshot mới, đánh giá so baseline | Retrain liên tục mà không có tiêu chí |
| **Monitoring** | Liên tục | p95/p99, 5xx, skew/drift, business KPI, costs | Coi prediction drift = model chắc chắn sai |

**Cloud Build** điều phối kiểm thử/build/automation theo sự kiện Git. **Vertex AI Pipelines** điều phối các bước ML (chuẩn bị dữ liệu → train → evaluate → register). **Cloud Deploy** mạnh cho phát hành ứng dụng tới những đích được hỗ trợ như Cloud Run/GKE, **không mặc nhiên triển khai mô hình Vertex Endpoint**; với endpoint hãy dùng Vertex AI API/CLI hoặc pipeline được kiểm soát.

## 3. Định nghĩa chất lượng và an toàn trước khi viết YAML

Một release chỉ được chấp nhận khi có các điều kiện rõ:

| Gate | Ví dụ điều kiện | Khi không đạt |
| --- | --- | --- |
| Source/code | PR review, static checks, unit tests pass | Dừng build |
| Dữ liệu | Schema đúng, dữ liệu không rỗng, label hợp lệ, không leakage | Không train |
| Build | Container build thành công, dependency scan không có lỗi vượt ngưỡng | Chặn promotion |
| Model | Macro-F1 ≥ ngưỡng đã duyệt, so baseline, kiểm thử trên holdout | Giữ bản cũ |
| Security | Service account ít quyền, không PII/secrets trong artifact/logs | Chặn deploy |
| Serving | Health, latency, error rate và input/output schema đúng | Dừng rollout |
| Business | Fraud detection uplift/false-positive impact đủ tốt | Giữ canary hoặc rollback |

**Không chọn ngưỡng dựa trên kết quả test rồi báo rằng test độc lập.** Chọn threshold từ validation/baseline và yêu cầu nghiệp vụ; đánh giá trên tập test được giữ lại và không lặp việc tuning trên tập đó.

Với mô hình dùng trong quyết định nhạy cảm, cần đánh giá fairness/privacy/bias, human review và chính sách tuân thủ ngoài các kiểm thử ở đây.

## 4. Repo lab tối thiểu

Bài thực hành dùng **digits dataset** đi kèm scikit-learn, không cần dữ liệu khách thật. Mục đích là học CI/CD và tạo artifacts, **không chứng minh mô hình đủ tốt cho bài toán gian lận thực tế**.

~~~text
mlops-digits-lab/
├── src/
│   ├── __init__.py
│   └── train.py
├── tests/
│   └── test_train.py
├── requirements.txt
├── Dockerfile
├── cloudbuild.yaml
└── customjob.yaml
~~~

Mỗi file có một nhiệm vụ:

- `src/train.py`: huấn luyện, đánh giá và xuất model/metrics.
- `tests/test_train.py`: kiểm tra pipeline train và đặc tính đầu ra.
- `Dockerfile`: môi trường huấn luyện tái lập.
- `cloudbuild.yaml`: **CI** test → build → push, không tự chạy training tính phí.
- `customjob.yaml`: **CD-training** được phê duyệt, tham chiếu digest cụ thể.

Bài dùng một training image. Production thường có **serving image riêng** để load artifacts và cung cấp giao diện dự đoán.

## 5. Viết mã huấn luyện có thể kiểm thử

`requirements.txt`:

~~~text
scikit-learn==1.5.2
joblib==1.4.2
google-cloud-storage==2.18.2
~~~

Các version trên là ví dụ **pin dependency** cho bài lab; khi dùng thực tế phải kiểm tra tương thích Python, security advisories và cập nhật phiên bản đã phê duyệt. Cố định thêm base-image digest và lockfile khi cần khả năng tái lập chặt chẽ.

`src/train.py`:

~~~python
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import joblib
from google.cloud import storage
from sklearn.datasets import load_digits
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split


def train_once():
    features, labels = load_digits(return_X_y=True)
    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2,
        stratify=labels, random_state=42
    )
    model = RandomForestClassifier(
        n_estimators=80, random_state=42, n_jobs=2
    )
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, predicted)),
        "macro_f1": float(f1_score(
            y_test, predicted, average="macro"
        )),
        "train_rows": int(len(y_train)),
        "test_rows": int(len(y_test)),
        "seed": 42
    }
    return model, metrics


def upload_artifacts(directory: Path, gcs_uri: str):
    parsed = urlparse(gcs_uri)
    if parsed.scheme != "gs" or not parsed.netloc:
        raise ValueError("AIP_MODEL_DIR must be a gs:// URI")

    bucket = storage.Client().bucket(parsed.netloc)
    prefix = parsed.path.strip("/")
    for name in ("model.joblib", "metrics.json"):
        object_name = f"{prefix}/{name}" if prefix else name
        bucket.blob(object_name).upload_from_filename(
            str(directory / name)
        )


def main():
    model, metrics = train_once()
    print(json.dumps(metrics, sort_keys=True))
    out = Path("/tmp/digits-artifacts")
    out.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, out / "model.joblib")
    (out / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    target = os.getenv("AIP_MODEL_DIR")
    if target:
        upload_artifacts(out, target)
    else:
        print("Local mode: artifacts in", out)


if __name__ == "__main__":
    main()
~~~

**Tại sao viết theo cách này?** `train_once()` không có side effect cloud, có thể unit-test. `main()` chỉ xuất model và metrics khi cần. Vertex AI CustomJob với `baseOutputDirectory` đặt biến `AIP_MODEL_DIR`; ở local không có biến này nên không ghi lên Cloud Storage.

Với dữ liệu thực, **không tải dữ liệu ngẫu nhiên mỗi lần train**: lưu dataset snapshot/generation và khóa feature schema, label, cutoff thời gian, preprocessing version. Tập digits ở đây chỉ là dữ liệu demo đi kèm phiên bản scikit-learn.

**An toàn artifacts:** `joblib`/`pickle` có thể thực thi mã khi deserialization. Chỉ load model từ nguồn tin cậy, giới hạn IAM đọc artifacts, quét dependency và pin version training–serving.

## 6. Unit tests và quality gate phải tách biệt

`tests/test_train.py`:

~~~python
from src.train import train_once


def test_train_produces_valid_model_and_metrics():
    model, metrics = train_once()

    assert len(model.classes_) == 10
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["macro_f1"] <= 1.0
    assert metrics["train_rows"] > metrics["test_rows"] > 0
    assert metrics["seed"] == 42
~~~

CI kiểm tra **code contract**, không đưa ra kết luận hiệu năng ML chỉ từ một unit test. **Quality gate sau huấn luyện** đánh giá metrics của đúng model artifact:

~~~json
{
  "metric": "macro_f1",
  "minimum": 0.85,
  "baseline_model": "approved-baseline-v1",
  "must_pass_data_contract": true,
  "approval_required_for_production": true
}
~~~

Đây là **ví dụ policy JSON để giải thích**, không phải file mà Vertex AI tự đọc và thực thi. Một bước evaluator trong Vertex AI Pipelines/Workflows/Cloud Build release pipeline phải **thực sự parse metrics**, so threshold, so baseline và trả lỗi khi vi phạm. Không coi `CustomJob: SUCCEEDED` là `MODEL_APPROVED`.

### 6.1. Vì sao dữ liệu test cần độc lập?

Dataset dùng để tuning, chọn tham số hoặc ngưỡng không được dùng tiếp như bằng chứng cuối cùng không thiên lệch. Trong bài lab chỉ huấn luyện **một** cấu hình RandomForest và lấy một holdout. Trong production phải có validation (tuning) và test (final), kiểm tra theo thời gian/nhóm người dùng, cùng dữ liệu ngoài phân phối khi phù hợp.

## 7. Dockerfile: đóng gói môi trường huấn luyện

`Dockerfile`:

~~~dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY src ./src
ENTRYPOINT ["python", "-m", "src.train"]
~~~

CI sẽ dùng Dockerfile để tạo image. Training container:

- Chạy entrypoint rồi kết thúc; **không phải serving container**.
- Nhận workload identity do Vertex AI cấp, không cần đưa service account key vào image.
- Ghi artifacts qua `AIP_MODEL_DIR` khi Vertex AI truyền biến này.
- Không được phép dựa vào file local `/tmp` sau khi job kết thúc: phải upload sang GCS.

**Production:** pin base image theo **digest**, quản lý SBOM/dependencies, quét lỗ hổng, giới hạn build provenance và kiểm tra license. Không dùng image `latest` hoặc `pip install` không có pin trên đường production.

## 8. Preflight: xem project và tài nguyên hiện có

Chỉ chạy trên **project lab có Billing** và các quyền được cấp. Chọn `us-central1` cho ví dụ, dùng dữ liệu public/builtin; với data thật cần kiểm tra **residency** và region ở GCS/BigQuery/training.

~~~bash
gcloud auth list
gcloud config get-value project

gcloud artifacts repositories list \
  --location=us-central1 --project=PROJECT_ID

gcloud builds list \
  --region=us-central1 --project=PROJECT_ID --limit=10

gcloud ai custom-jobs list \
  --region=us-central1 --project=PROJECT_ID

gcloud ai models list \
  --region=us-central1 --project=PROJECT_ID
~~~

Đây là lệnh **chỉ đọc**. Không dùng project production để tạo lần đầu một repo/container/Vertex job khi chưa có approval và budget.

### 8.1. Chuẩn bị các dịch vụ có tính phí

~~~bash
gcloud services enable \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  --project=PROJECT_ID

gcloud artifacts repositories create mlops-train \
  --repository-format=docker \
  --location=us-central1 \
  --description="ML training containers for lab" \
  --project=PROJECT_ID

gcloud storage buckets create \
  gs://PROJECT_ID-mlops-artifacts-UNIQUE \
  --location=us-central1 \
  --project=PROJECT_ID
~~~

`UNIQUE` phải thay bằng hậu tố để **bucket name duy nhất toàn cầu**. Nếu repo/bucket đã tồn tại, kiểm tra owner/IAM/location trước; không xóa hay ghi đè. Artifact Registry, Cloud Build, Vertex AI và GCS có thể phát sinh phí/quotas.

## 9. Thiết kế IAM tách ba danh tính

| Danh tính | Mục đích | Quyền tối thiểu cần xem xét |
| --- | --- | --- |
| **Build SA** | Chạy CI, push image | Artifact Registry **Writer** trên repo, ghi Cloud Logging/logs, quyền build source |
| **Training SA** | Vertex AI worker đọc dữ liệu/ghi artifacts | GCS read đúng dataset, **Storage Object Creator/Writer** ở bucket artifacts |
| **Release SA** | Tạo CustomJob, đăng ký/deploy model | Quyền Vertex AI phù hợp, `iam.serviceAccounts.actAs` trên Training SA |
| **Prediction runtime SA** | Serving container đọc resource cần thiết | Chỉ quyền inference-time, không có quyền build/train |
| **Cloud Build/Vertex service agents** | Nhiệm vụ Google-managed | Giữ role service-agent đúng phạm vi, không cấp cho user/app |

Tạo ví dụ Training SA cho lab:

~~~bash
gcloud iam service-accounts create mlops-training-sa \
  --display-name="MLOps training runtime" \
  --project=PROJECT_ID

gcloud storage buckets add-iam-policy-binding \
  gs://PROJECT_ID-mlops-artifacts-UNIQUE \
  --member=serviceAccount:mlops-training-sa@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.objectCreator
~~~

Quyền `roles/storage.objectCreator` phù hợp tạo object mới; nếu code cần **đọc, overwrite hay xóa** artifacts thì phải thiết kế permission bổ sung tại bucket/prefix phù hợp. Người kích hoạt CustomJob cần `iam.serviceAccounts.actAs` trên Training SA. Quyền **Artifact Registry Reader** cần cấp cho đúng identity thực sự **pull container** (có thể là Vertex AI service agent, nhất là repo cross-project), không mặc nhiên cho mọi runtime.

Với Cloud Build trigger, chọn **Build SA riêng** theo màn hình/CLI; trigger có thể **bỏ qua serviceAccount khai trong build config** và dùng service account chọn ở trigger. **Không giả định Cloud Build default SA luôn có quyền Writer** vì chính sách tổ chức có thể tắt auto-grant.

## 10. cloudbuild.yaml: unit test → build → push image

`cloudbuild.yaml` đặt ở root repo:

~~~yaml
steps:
  - id: unit-tests
    name: python:3.11-slim
    entrypoint: bash
    args:
      - -ceu
      - |
        python -m pip install --no-cache-dir -r requirements.txt
        python -m pip install --no-cache-dir pytest==8.3.4
        python -m pytest -q tests/

  - id: docker-build
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - us-central1-docker.pkg.dev/$PROJECT_ID/mlops-train/digits-trainer:${_IMAGE_TAG}
      - .

images:
  - us-central1-docker.pkg.dev/$PROJECT_ID/mlops-train/digits-trainer:${_IMAGE_TAG}

substitutions:
  _IMAGE_TAG: lab-v1

options:
  logging: CLOUD_LOGGING_ONLY
~~~

**Giải thích các điểm dễ sai:**

- Build steps chạy **theo thứ tự** mặc định. Nếu unit test fail, build/push không diễn ra.
- `images` yêu cầu Cloud Build **push image và ghi nhận trong build result** khi build thành công; không cần thêm một bước `docker push` trùng.
- `$PROJECT_ID` là built-in substitution; `${_IMAGE_TAG}` là **user-defined substitution**. Chuỗi thực trong YAML phải có ký tự `$` ngay trước `{`, như `$` + `{_IMAGE_TAG}`, không có ký tự `¤`. Khi lưu bài vào file Markdown, các ký hiệu này được hiển thị nguyên đúng cú pháp.
- `CLOUD_LOGGING_ONLY` yêu cầu Build SA có quyền ghi Cloud Logging; với custom SA phải cấp đúng `roles/logging.logWriter` và các quyền build cần thiết.
- `python:3.11-slim` trong CI cài dependency để test; Dockerfile cài dependency độc lập bên trong training image.
- Không dùng biến substitutions để chuyển **bí mật**; dùng Secret Manager integration nếu build cần token.

**CI chưa chạy training trên Vertex AI.** Tách việc này để PR hoặc commit nháp không khởi tạo VM/GPU bất ngờ.

## 11. Chạy CI thủ công và kiểm tra image digest

Trong thư mục lab có Dockerfile/`cloudbuild.yaml`:

~~~bash
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --region=us-central1 \
  --project=PROJECT_ID \
  --substitutions=_IMAGE_TAG=lab-v1

gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/PROJECT_ID/mlops-train/digits-trainer \
  --include-tags \
  --project=PROJECT_ID
~~~

**Kỳ vọng:** test qua, build/push thành công, Artifact Registry có một image version với digest `sha256:<64-hex>`. **Không tự điền digest mẫu** vào production: sao chép digest **thực** từ Console hoặc output CLI.

Ba định danh khác nhau:

~~~text
Build commit:  6cba... (Git SHA)
Image tag:     digits-trainer:lab-v1  (dễ đọc, có thể mutable)
Image digest:  digits-trainer@sha256:... (đúng nội dung image)
~~~

Để promote, đưa **image digest** cùng **source commit, test run, scan result, training config, data version** vào release manifest/metadata. Nếu image đã được quét sau push, CI/CD cần **đọc kết quả quét và enforce policy**; việc chỉ bật scanning không tự chặn triển khai.

## 12. Tự động hóa bằng Cloud Build triggers

Trong **Cloud Build → Triggers**, kết nối GitHub/Git repository theo chính sách tổ chức. Tạo hai đường:

1. **Pull request CI:** chạy lint/unit tests/schema checks và build test nếu cần. Với fork PR, không cấp quyền build truy cập production secrets hay project rộng.
2. **Protected main/release trigger:** chỉ chạy sau review/merge; build image có tag commit/release duy nhất, ghi digest và provenance. **Không auto-deploy production** chỉ vì có commit.

Các trường quan trọng:

| Trường | Giá trị gợi ý |
| --- | --- |
| Event | Pull request hoặc push/tag vào branch được bảo vệ |
| Config | `cloudbuild.yaml` |
| Service account | Build SA riêng, repo Writer và quyền logs |
| Substitutions | `_IMAGE_TAG` = release ID duy nhất hoặc `SHORT_SHA` từ trigger được xét |
| Included files | `src/**`, `tests/**`, `Dockerfile`, `requirements.txt` |
| Approval | Bật cho đường **release/promote** khi cần |
| Logs | Cloud Logging hoặc bucket riêng đã phê duyệt |

Cloud Build có built-in variables như `$COMMIT_SHA` và `$SHORT_SHA` trên **Git triggers**. Khi chạy thủ công không gắn Git commit, các biến này có thể rỗng; bài lab chủ động dùng `_IMAGE_TAG` để tránh image tag trống.

**Kịch bản an toàn:** CI trên pull request không được dùng Release SA hoặc deployer credentials. Trigger phát hành có **approval** và chỉ cấp đúng quyền để khởi tạo workflow, không có toàn quyền thay chính sách IAM.

## 13. Bảo vệ Artifact Registry và chuỗi cung ứng

Artifact Registry có thể lưu OCI/Docker images và, với loại repo phù hợp, **Kubeflow Pipelines templates**. Đây là **registry artifacts**, không phải kho model versions.

| Bảo vệ | Ý nghĩa |
| --- | --- |
| **Artifact Registry IAM** | Build SA Writer; người/agent chạy job Reader |
| **Immutable tags** | Tag không bị trỏ sang digest khác sau khi push |
| **Digest pinning** | CustomJob/serving dùng chính image đã duyệt |
| **Artifact Analysis** | Scan lỗ hổng OS/Python packages, theo repo/configuration |
| **SBOM/build provenance** | Truy vết thành phần và nguồn build |
| **Binary Authorization nếu target hỗ trợ** | Enforce policy triển khai ở các đích hỗ trợ; **không mặc định áp cho mọi Vertex AI training/endpoint** |
| **Cleanup/retention policy** | Quản image cũ theo thời hạn, giữ các digest còn dùng trong rollback |

**Lưu ý:** Artifact Analysis có **automatic** và **on-demand scanning**; khả năng quét không mặc định bật cho mọi repo theo cùng cấu hình. CI nên đọc kết quả scan theo **digest** và chặn lỗi severity đã phê duyệt. Một scan pass hôm nay không bảo đảm tháng sau không phát hiện CVE mới; cần continuous vulnerability review.

Không xóa image đang được CustomJob/serving model tham chiếu. Nếu đã pin digest mà Artifact Registry dọn digest đó, **reproduce/redeploy/rollback có thể thất bại**.

## 14. CD-training: chạy CustomJob bằng image digest đã kiểm duyệt

Mẫu `customjob.yaml` (**CustomJobSpec**) dưới đây phải được điền bằng digest thật lấy từ mục 11:

~~~yaml
workerPoolSpecs:
  - machineSpec:
      machineType: n1-standard-4
    replicaCount: 1
    containerSpec:
      imageUri: us-central1-docker.pkg.dev/PROJECT_ID/mlops-train/digits-trainer@sha256:REPLACE_WITH_REAL_DIGEST
baseOutputDirectory:
  outputUriPrefix: gs://PROJECT_ID-mlops-artifacts-UNIQUE/runs/RUN_ID
serviceAccount: mlops-training-sa@PROJECT_ID.iam.gserviceaccount.com
~~~

Chọn một **RUN_ID duy nhất**, ví dụ kết hợp release ID và ngày, **không dùng lại output prefix** của run trước để tránh artifact overwrite. `baseOutputDirectory` thiết lập vị trí output; Vertex AI truyền `AIP_MODEL_DIR` cho custom training theo cấu hình. Code mục 5 sẽ upload hai files `model.joblib` và `metrics.json` vào đúng thư mục.

Sau khi **có approval về phí và quyền**:

~~~bash
gcloud ai custom-jobs create \
  --region=us-central1 \
  --project=PROJECT_ID \
  --display-name=digits-train-release-lab \
  --config=customjob.yaml

gcloud ai custom-jobs list \
  --region=us-central1 \
  --project=PROJECT_ID

# Thay JOB_ID bằng ID có thật.
gcloud ai custom-jobs describe JOB_ID \
  --region=us-central1 \
  --project=PROJECT_ID
~~~

**Kỳ vọng:** job `JOB_STATE_SUCCEEDED`, GCS có `model.joblib` và `metrics.json`; ghi nhận **job ID + image digest + output GCS URI**. Job `SUCCEEDED` chỉ chứng minh container hoàn tất theo exit code, **chưa chứng minh model đạt quality gate**.

**Không tăng `replicaCount` chỉ để đẩy nhanh mọi Python script:** nếu code không phân tán, workers có thể train trùng và ghi đè artifacts. Bài lab dùng một CPU worker.

## 15. Quality gate sau training: kiểm tra đúng model artifact

Workflow release phải **đọc metrics.json từ output của đúng CustomJob**, so với baseline và chính sách release, rồi quyết định.

Ví dụ logic định hướng:

~~~text
input: run_id, image_digest, artifact_uri, dataset_version

1. Xác nhận CustomJob SUCCEEDED và artifacts tồn tại.
2. Đọc metrics.json; kiểm tra schema và giá trị hữu hạn.
3. So macro_f1 với ngưỡng đã phê duyệt.
4. So benchmark/baseline trên CÙNG dataset snapshot/metric.
5. Kiểm tra security scan + provenance + quyền truy cập model.
6. Nếu không đạt: đánh dấu REJECTED, không đăng ký/deploy.
7. Nếu đạt: lưu evidence + chờ approval rồi mới register.
~~~

Một bước evaluator chạy trên Cloud Run, Vertex AI Pipelines component hoặc Cloud Build release stage có thể triển khai logic trên. Nếu dùng Cloud Build, cấu hình **release trigger** riêng, không dùng PR trigger có quyền upload/deploy model.

**Ghi metadata đầy đủ:**

~~~yaml
release:
  source_commit: GIT_COMMIT_SHA
  training_image: us-central1-docker.pkg.dev/PROJECT_ID/mlops-train/digits-trainer@sha256:REAL_DIGEST
  vertex_custom_job: JOB_ID
  dataset_version: sklearn-digits-versioned-by-dependencies
  model_artifact_uri: gs://PROJECT_ID-mlops-artifacts-UNIQUE/runs/RUN_ID/model/
  metrics_uri: gs://PROJECT_ID-mlops-artifacts-UNIQUE/runs/RUN_ID/model/metrics.json
  evaluation_status: PENDING_APPROVAL
~~~

Manifest trên là **ví dụ quản trị**, không phải schema mà Vertex AI tự nhận để deploy. Đường `model/` chỉ minh họa thư mục `AIP_MODEL_DIR`: lấy URI thật từ logs/metadata sau run, không tự suy path nếu cấu hình hệ thống khác.

### 15.1. Tránh data leakage giữa bản CI và model

Nếu mỗi build fetch “dữ liệu mới nhất” không có snapshot, hai mô hình dùng **cùng image digest** vẫn có thể khác nhau vì data đổi. Phiên bản release cần quản lý **source object generation/BigQuery snapshot**, preprocessing, label definition, feature schema, seed và training config. Tính tái lập là thuộc tính **của toàn bộ hệ ML**, không chỉ Docker image.

## 16. Vertex AI Pipelines và Artifact Registry pipeline templates

Một CustomJob chỉ xử lý một phần. Khi pipeline nhiều bước, sử dụng **Vertex AI Pipelines** (trong tài liệu mới có thể xuất hiện tên **Gemini Enterprise Agent Platform Pipelines**) để điều phối:

~~~mermaid
flowchart TD
    SNAP["Data snapshot / validation"] --> TRAIN["CustomTrainingJobOp"]
    TRAIN --> EVAL["Evaluation component"]
    EVAL --> GATE{"Policy pass?"}
    GATE -->|Có| UPLOAD["ModelUploadOp / Registry"]
    GATE -->|Không| REJECT["Reject + notify"]
    UPLOAD --> STAGE["Staging evaluation"]
    STAGE --> APPROVE["Manual/automated approval"]
    APPROVE --> DEPLOY["Controlled rollout"]
~~~

Một pipeline từ **Kubeflow Pipelines SDK v2** được **compile thành YAML**. Có thể version hóa template trong Git và **Artifact Registry KFP repository**; mỗi run tham chiếu **template version**, parameter values và **pipeline root** trên GCS. Các thành phần dùng **Google Cloud Pipeline Components (GCPC)** như `CustomTrainingJobOp`, `ModelUploadOp` theo phiên bản SDK được hỗ trợ.

Phần này không cần viết thêm một pipeline Python dài trùng lab: hãy xác định hợp đồng giữa các bước:

| Component | Input chính | Output chính |
| --- | --- | --- |
| Data validation | Dataset URI/version | Contract pass/fail, snapshot |
| Training | Image digest, snapshot, params | CustomJob ID, artifacts URI |
| Evaluation | Model artifacts, test snapshot | Metrics, threshold verdict |
| Register | Approved artifact, serving image | Model resource + version ID |
| Staging/deploy | Model version, serving contract | Endpoint/deployedModelId |
| Monitor | Logs, labels, inference data | Alerts và retrain proposal |

**Lưu ý về API mới:** các tài liệu Agent Platform Pipelines hiện mô tả tạo run qua **SDK, REST hoặc Console**, không phải bắt buộc một lệnh `gcloud ai pipeline-jobs submit`. Hãy dùng giao diện được tài liệu của **project/API version hiện hành** hỗ trợ. Pipeline có thể dùng execution caching; nếu thành phần phụ thuộc dữ liệu bên ngoài luôn thay đổi, phải khóa dataset version hoặc tắt cache cho bước liên quan.

## 17. Model Registry không phải nơi chứa Dockerfile huấn luyện

Sau khi gate pass, đăng ký model:

- Artifact `model.joblib` và metadata nằm trong GCS được phép truy cập.
- **Vertex AI Model Registry** quản lý model resource, version, alias, label và lịch sử triển khai.
- **Serving container** phải **load đúng artifact** và cung cấp API dự đoán theo Vertex AI prediction contract, bao gồm health/predict routes nếu dùng custom container.

Đoạn lab `Dockerfile` ở mục 7 **chỉ chạy `src.train` rồi thoát**, **không thể deploy trực tiếp như inference server**.

Ví dụ lệnh **chỉ khi đã có serving container được kiểm thử**:

~~~bash
gcloud ai models upload \
  --project=PROJECT_ID \
  --region=us-central1 \
  --display-name=digits-classifier-candidate \
  --artifact-uri=gs://PROJECT_ID-mlops-artifacts-UNIQUE/runs/RUN_ID/model \
  --container-image-uri=us-central1-docker.pkg.dev/PROJECT_ID/mlops-serving/digits-predictor@sha256:APPROVED_SERVING_DIGEST
~~~

**Không chạy lệnh này chỉ với image trainer**: chưa có `mlops-serving/digits-predictor` trong bài lab. Cần triển khai/test prediction container riêng hoặc dùng prebuilt serving container **tương thích định dạng model** được tài liệu hỗ trợ.

Model aliases như `candidate`, `staging`, `approved` là **tên tham chiếu có thể thay đổi**; khi rollback cần biết chính xác **model version ID và serving image digest**, không chỉ alias.

## 18. CD-serving: staging, canary và rollback

Đường phát hành an toàn:

1. Đăng ký phiên bản model có **evaluation evidence**.
2. Deploy staging bằng **prediction container**, chạy schema checks, smoke tests và performance test.
3. Sau approval, deploy phiên bản mới trên endpoint production với **traffic nhỏ**, ví dụ 5%.
4. Theo dõi latency, 5xx, input errors, model skew và KPI; tăng 5 → 25 → 50 → 100% nếu đạt.
5. Nếu không đạt, chuyển traffic về `deployedModelId` cũ, rồi mới cân nhắc undeploy bản lỗi.

Ví dụ **chỉ có tác động trong môi trường được phê duyệt**, sau khi endpoint đã chứa hai deployed models:

~~~bash
# Xác nhận trước khi thay routing:
gcloud ai endpoints describe ENDPOINT_ID \
  --project=PROJECT_ID --region=us-central1

# Tỷ lệ trên tổng traffic endpoint: 95% cũ, 5% mới.
gcloud ai endpoints update ENDPOINT_ID \
  --project=PROJECT_ID --region=us-central1 \
  --traffic-split=OLD_DEPLOYED_ID=95,NEW_DEPLOYED_ID=5

# Rollback routing nếu canary vi phạm SLO:
gcloud ai endpoints update ENDPOINT_ID \
  --project=PROJECT_ID --region=us-central1 \
  --traffic-split=OLD_DEPLOYED_ID=100

# CHỈ SAU khi traffic đã về bản khỏe và được phê duyệt:
gcloud ai endpoints undeploy-model ENDPOINT_ID \
  --project=PROJECT_ID --region=us-central1 \
  --deployed-model-id=NEW_DEPLOYED_ID
~~~

**`deployedModelId` không phải `Model Registry modelId`.** Lấy `deployedModels[].id` thật từ endpoint describe. Endpoint traffic split chỉ định các IDs đã triển khai, tổng tỷ lệ phải đúng yêu cầu. Nếu chưa có bản cũ khỏe, **không dùng lệnh rollback mẫu** mà cần incident/restore plan riêng.

**Rollback model không rollback dữ liệu hoặc business side effects.** Nếu model mới đã tự động từ chối/gắn cờ giao dịch, phải có quy trình kiểm toán, đối soát và sửa những quyết định đã phát sinh. Không chuyển traffic chỉ vì một metrics chart mà bỏ qua impact nghiệp vụ.

## 19. Bảo mật, network, secrets và compliance

- **Source control:** protected branches, PR approval, dependency lockfiles, không commit service account JSON.
- **Cloud Build:** service account riêng, hạn chế quyền trigger PR, Secret Manager, logs không chứa token.
- **Artifact Registry:** private repository, Writer chỉ cho CI, Reader cho runtime cần thiết, provenance/scan và retention.
- **Vertex AI:** phân quyền train, register và deploy, service accounts riêng; tránh cấp `roles/aiplatform.admin` cho mọi consumer.
- **Cloud Storage/BigQuery:** bucket/dataset đúng region, điều kiện data residency, IAM tối thiểu, CMEK nếu chính sách yêu cầu.
- **Networking:** CustomJob cần đường mạng tới nguồn private Cloud SQL/BigQuery endpoints; kiểm tra VPC/PSC/Private Service Access, không coi IAM là mạng.
- **VPC Service Controls:** đánh giá perimeter cho Cloud Build, Artifact Registry, Vertex AI, Cloud Storage và các service agents theo cấu hình hỗ trợ.
- **Supply chain:** image digest, SBOM, vulnerability scanning; model artifacts chỉ nhận từ pipeline tin cậy.
- **Privacy:** chỉ log metrics/ID; không log raw PII, model features nhạy cảm hoặc prediction payload đầy đủ nếu chưa được chấp thuận.

**Không dùng service agent role** (dành cho Google-managed identities) làm giải pháp nhanh cho một người hay service account bình thường. Khi lỗi permission, xác định chính xác **principal và resource** (source repo, image, bucket, model, endpoint).

## 20. Quan sát, điều tra và kiểm soát chi phí

| Thành phần | Chỉ số cần theo dõi | Câu hỏi |
| --- | --- | --- |
| Git/Cloud Build | Trigger, Build ID, test result, duration, image digest | Bản build nào tạo image? |
| Artifact Registry | Scan findings, image age/size, retention | Image có CVE mới hoặc đang bị dọn? |
| Training jobs | Job state, duration, worker type, failures | Mô hình đã train được không? |
| Evaluation | Metrics vs baseline, data slices, drift, policy verdict | Có đủ điều kiện promote? |
| Registry | Model/version/alias, approval | Đang dùng version nào? |
| Endpoint | p50/p95/p99 latency, 4xx/5xx, replica count, traffic split | Canary có ảnh hưởng người dùng? |
| Business | Fraud false positives, conversion, support tickets | Model thật sự giúp kinh doanh? |
| Billing | Cloud Build, Artifact Registry, Vertex workers, GCS, endpoint machines | Chi phí đi từ đâu? |

**Chi phí CI/CD không chỉ là Cloud Build:** Artifact Registry storage/scan, Cloud Build CPU/time/logs, Vertex AI training VM/GPU, GCS model artifacts, BigQuery feature queries, Vertex AI Pipelines orchestration, endpoint CPU/GPU/replica-minimum và log retention đều có thể tính phí.

**Endpoint online có thể bị tính phí khi nhàn rỗi** nếu giữ replicas được triển khai. Training job đã xong không đảm bảo endpoint tự tắt. Dùng Cloud Billing budgets, labels và exports; **budget alert không tự khóa hóa đơn**. Dọn project lab sau khi xác minh không còn phụ thuộc.

## 21. Troubleshooting theo giai đoạn

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| CI unit tests fail | Imports/versions/schema/test regression | Build log, môi trường CI so local |
| Build push bị `PERMISSION_DENIED` | Build SA không có repo Writer | IAM tại Artifact Registry repo |
| Build logs không hiện | Custom SA thiếu Logging Writer hoặc log bucket config | Cloud Build options/logs policy |
| Image tag đổi nhưng CustomJob vẫn bản cũ | Job pin digest cũ | So digest URI trong job |
| CustomJob không pull được image | Artifact Registry Reader/service agent/cross-project | Kiểm tra identity lấy image |
| `AIP_MODEL_DIR` rỗng | Chưa đặt `baseOutputDirectory` | CustomJobSpec/runtime env |
| Job `SUCCEEDED` nhưng thiếu model | Code không upload hoặc output path sai | GCS objects/logs, check artifacts |
| Metric gate fail | Dữ liệu/label thay đổi, overfit/underfit | Dataset version, split, baseline |
| Model Registry không có version | CustomJob không tự upload model | Model upload step/training pipeline |
| Endpoint deploy fail | Serving image không chạy prediction server | Container logs, model format, health |
| Canary 5xx tăng | Schema mismatch/timeout/resource | Endpoint metrics, rollback traffic |
| Đã rollback nhưng KPI còn sai | Side effects của predictions đã xảy ra | Audit/reconciliation runbook |
| Bill tăng dù không train | Endpoint deployed, stored images, logs | Billing SKU, cleanup plan |

Khi incident, giữ **Build ID, Git SHA, image digest, CustomJob ID, dataset snapshot, model version, endpoint deployedModelId**. Những identifiers này giúp đối chiếu nhanh hơn việc chỉ ghi “release v2 bị lỗi”.

## 22. Tình huống tổng hợp: fraud model cho Commerce API

**Bối cảnh:** mô hình phát hiện gian lận được cập nhật hằng tuần; Java API trên Cloud Run gọi Vertex AI endpoint trước khi xác nhận đơn. Nhóm có ba môi trường `dev/staging/prod`.

**Thiết kế đề xuất:**

~~~mermaid
flowchart TD
    PR["PR / merge code"] --> CI["Cloud Build CI"]
    CI --> IMAGE["Artifact Registry image digest"]
    IMAGE --> T["Release trigger / approval"]
    T --> TRAIN["Vertex training on snapshot"]
    TRAIN --> METRIC["Evaluation & security gate"]
    METRIC -->|Pass| REG["Model Registry version"]
    METRIC -->|Fail| REJECT["Reject / investigate"]
    REG --> STAGE["Staging smoke + load tests"]
    STAGE --> CANARY["Prod 5% canary"]
    CANARY -->|"Metrics healthy"| FULL["25% → 50% → 100%"]
    CANARY -->|"Error / KPI regression"| ROLLBACK["Traffic 100% old model"]
~~~

**Phân chia trách nhiệm:**

| Vai trò | Quyết định |
| --- | --- |
| Data engineer | Dữ liệu có schema, nhãn và snapshot đúng? |
| ML engineer | Model metrics/feature drift, training code phù hợp? |
| Platform engineer | Build/image/IAM/network/endpoint an toàn? |
| Product/compliance | False positive, fairness, privacy, business KPI? |
| SRE | Canary SLO, rollback, observability và runbook? |

Chỉ phát hành khi **tất cả gates cần thiết** đạt. Nếu mô hình mới tăng recall nhưng làm false-positive rate tăng mạnh khiến nhiều khách hợp lệ bị từ chối, cần **giữ bản cũ** dù job training và API đều hoạt động.

## 23. Bài tập thực hành và tự kiểm tra

**Bài 1 — CI lab.** Từ repo ở mục 4–10, chạy unit tests và Cloud Build trong project lab có approval.

*Đạt:* build có Build ID, tests pass, Artifact Registry có digest được ghi lại; không tự chạy CustomJob.

**Bài 2 — CD-training.** Tạo `customjob.yaml` với **digest thật**, chạy một CPU worker, xem artifacts.

*Đạt:* Job `SUCCEEDED`, GCS có model/metrics, có link giữa source commit – image digest – run ID.

**Bài 3 — Chặn model lỗi.** Giả lập `macro_f1` dưới ngưỡng phát hành.

*Đạt:* release pipeline giữ model ở trạng thái **REJECTED**, không deploy endpoint; logs ghi nguyên nhân.

**Bài 4 — Canary.** Với endpoint staging có hai deployed models, tính tỷ lệ 95/5 và rollback.

*Đạt:* phân biệt model ID với deployedModelId; rollback chỉ thay traffic, không xóa dữ liệu/side effects.

**Câu 5.** Artifact Registry có phải Model Registry không?

*Đáp án:* Không. Artifact Registry lưu container/KFP templates; Vertex AI Model Registry quản model resources/versions.

**Câu 6.** Image tag `latest` có đảm bảo nội dung bất biến không?

*Đáp án:* Không nếu mutable tags; dùng image digest hoặc enforce immutable tags.

**Câu 7.** Cloud Build PR trigger có nên được phép deploy production không?

*Đáp án:* Không. PR CI cần quyền hạn chế, release approval tách riêng.

**Câu 8.** Unit test pass có chứng minh model business performance tốt không?

*Đáp án:* Không. Cần validation/test metrics và đánh giá nghiệp vụ.

**Câu 9.** `CustomJob` hoàn tất có tự đăng ký model trong Model Registry không?

*Đáp án:* Không mặc định; cần bước upload hoặc TrainingPipeline hỗ trợ.

**Câu 10.** Nếu giữ image digest nhưng dữ liệu huấn luyện thay đổi, model có đảm bảo giống nhau?

*Đáp án:* Không. Cần version dataset, seed, parameters và preprocessing.

**Câu 11.** Có thể deploy Dockerfile chỉ chạy `train.py` làm endpoint inference không?

*Đáp án:* Không. Cần serving container hỗ trợ protocol predict/health.

**Câu 12.** `OLD_DEPLOYED_ID` trong traffic split lấy từ đâu?

*Đáp án:* Từ `deployedModels[].id` trên Vertex AI Endpoint; khác Registry modelId.

**Câu 13.** Chuyển traffic về 100% bản cũ có hoàn tác mọi quyết định đã dùng model mới không?

*Đáp án:* Không. Cần audit/reconciliation các side effects.

**Câu 14.** Tại sao ngân sách ML không chỉ tính VM huấn luyện?

*Đáp án:* Còn build, Artifact Registry, scanning, storage, orchestration, inference, network và monitoring.

## 24. Checklist production và kết luận

- [ ] Có Git PR review, CI tests và release approval riêng.
- [ ] Training image sử dụng digest; source SHA và dependency versions được lưu.
- [ ] Build SA, Training SA, Release SA và serving identity **tách quyền**.
- [ ] Artifact Registry private, scan vulnerabilities và retention có kiểm soát.
- [ ] Dataset snapshot/labels/splits được version hóa; có kiểm tra leakage.
- [ ] Model evaluation gate trên holdout, so baseline và theo business KPI.
- [ ] Không đăng ký hoặc deploy khi quality/security gate fail.
- [ ] Model artifact GCS URI, checksum, metrics, run ID và model version có lineage.
- [ ] Serving container riêng tương thích model và schema input/output.
- [ ] Staging smoke/load tests đạt trước production.
- [ ] Canary/rollback sử dụng **deployedModelId** đúng.
- [ ] IAM, VPC/PSC, organization policies, secrets và data residency được kiểm tra.
- [ ] Monitoring p95/5xx, drift, fraud false positives, costs và alerts hoạt động.
- [ ] Có runbook rebuild/retrain/rollback và giữ artifacts cần thiết.
- [ ] Có ngân sách, quota, cleanup plan cho jobs, endpoint và registry.

**Kết luận:** MLOps tốt không đồng nghĩa “mỗi lần push Git là tự train rồi tự deploy”. Một quy trình đáng tin cậy là **CI kiểm thử và phát hành training image bất biến → CD chạy training trên dữ liệu có phiên bản → quality/security gate → đăng ký model → staging/canary/rollback → monitoring**. Artifact Registry giúp xác định **mã nào được chạy**, Vertex AI quản lý **việc huấn luyện/phiên bản model**, còn các chính sách chất lượng và quyền truy cập mới quyết định **có nên đưa model vào production**.

## Tài liệu tham khảo chính thức

- [Artifact Registry: Repository and image names](https://cloud.google.com/artifact-registry/docs/docker/names)
- [Artifact Registry: Push and pull images](https://cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Artifact Registry: Connect Cloud Build](https://cloud.google.com/artifact-registry/docs/configure-cloud-build)
- [Cloud Build: Build and push container](https://cloud.google.com/build/docs/build-push-docker-image)
- [Cloud Build: Automated build triggers](https://cloud.google.com/build/docs/automate-builds)
- [Cloud Build: Build substitutions](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
- [Cloud Build: User-managed service account](https://cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Artifact Analysis: Container vulnerability scanning](https://cloud.google.com/artifact-analysis/docs/container-scanning-overview)
- [Vertex AI: Create custom training job](https://cloud.google.com/vertex-ai/docs/training/create-custom-job)
- [gcloud ai custom-jobs create reference](https://cloud.google.com/sdk/gcloud/reference/ai/custom-jobs/create)
- [Vertex AI Pipelines: Build a pipeline](https://cloud.google.com/vertex-ai/docs/pipelines/build-pipeline)
- [Vertex AI Pipelines: Run a pipeline](https://cloud.google.com/vertex-ai/docs/pipelines/run-pipeline)
- [Vertex AI: Pipeline templates in Artifact Registry](https://cloud.google.com/vertex-ai/docs/pipelines/create-pipeline-template)
- [Vertex AI Model Registry: Model aliases](https://cloud.google.com/vertex-ai/docs/model-registry/model-alias)
- [Vertex AI: Deploy model to endpoint](https://cloud.google.com/vertex-ai/docs/general/deployment)
- [gcloud ai models upload reference](https://cloud.google.com/sdk/gcloud/reference/ai/models/upload)
- [gcloud ai endpoints update traffic split](https://cloud.google.com/sdk/gcloud/reference/ai/endpoints/update)
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing)

