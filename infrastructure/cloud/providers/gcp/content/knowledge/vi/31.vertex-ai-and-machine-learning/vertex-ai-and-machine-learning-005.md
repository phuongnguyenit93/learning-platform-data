# Hyperparameter tuning và quản lý thí nghiệm

Một nền tảng học trực tuyến dự đoán học viên có nguy cơ bỏ dở khóa học để gợi ý hỗ trợ kịp thời. Nhóm ML đã huấn luyện mô hình đầu tiên, nhưng chưa rõ chọn `learning_rate`, `regularization` hay số cây bao nhiêu để có kết quả tốt; mỗi người thử một cấu hình trong notebook rồi ghi kết quả vào bảng tính. Cách làm này khó tái lập, dễ **dùng nhầm tập test để tối ưu**, không biết mô hình nào đã được huấn luyện trên phiên bản dữ liệu nào và có thể tiêu tốn nhiều GPU mà không có cải thiện đáng kể.

**Vertex AI hyperparameter tuning** tự chạy những phép thử (*trials*) với các tham số được chọn và tối ưu theo **metric validation** đã khai báo. **Vertex AI Experiments** giúp ghi lại tham số, metrics và artifacts để so sánh, truy vết và đưa ra quyết định có căn cứ. Bài thuộc chương **Vertex AI và học máy** của module **CLOUD_PROVIDERS_GCP**, liên kết Cloud Storage/BigQuery, IAM, VPC, Cloud Logging, Pipelines và chi phí; các ví dụ dùng **mô hình scikit-learn trên dữ liệu giả**, không sử dụng thông tin học viên thật.

**Sau bài học, bạn có thể:**

1. Phân biệt **model parameters**, **hyperparameters**, **trial**, **study/tuning job** và **experiment run**.
2. Thiết kế không gian tìm kiếm, metric mục tiêu, budget, số trial đồng thời và tiêu chí dừng.
3. Chuẩn bị script custom training nhận tham số dòng lệnh và báo metric cho dịch vụ tuning.
4. Ghi/so sánh experiment runs bằng Vertex AI SDK; phân biệt summary metrics với TensorBoard time series.
5. Chọn cấu hình dựa trên tập validation, retrain và đánh giá **một lần trên test holdout**, quản lý lineage và quyền.
6. Điều tra trial thất bại, tránh data leakage, và ước tính chi phí của chiến dịch thử nghiệm.

## 1. Hai vòng lặp: tối ưu tham số và quản lý bằng chứng

~~~mermaid
flowchart LR
    DATA["Dataset đã phân phiên bản"] --> SPLIT["Train / Validation / Test"]
    SPLIT --> HPT["HyperparameterTuningJob<br/>study + search space"]
    HPT --> T1["Trial 1"]
    HPT --> T2["Trial 2"]
    HPT --> TN["Trial N"]
    T1 --> METRIC["Validation metric<br/>trả về optimizer"]
    T2 --> METRIC
    TN --> METRIC
    METRIC --> BEST["Chọn cấu hình ứng viên"]
    BEST --> FINAL["Retrain + đánh giá<br/>test holdout một lần"]
    HPT -. "Trial IDs / parameters<br/>và metrics" .-> EXP["Vertex AI Experiments<br/>run tracking khi tích hợp"]
    FINAL --> REG["Model Registry / deployment<br/>sau phê duyệt"]
~~~

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **Model parameters** | Trọng số được **học** từ dữ liệu trong `fit()` | Hệ số của Logistic Regression |
| **Hyperparameters** | Cấu hình chọn **trước** khi train hoặc qua tuning | `C`, `max_iter`, learning rate, batch size |
| **Trial** | Một lần chạy training với một tổ hợp hyperparameters | `C=0.1`, `max_iter=200` |
| **Tuning job / study** | Điều phối nhiều trials và sử dụng metric để đề xuất cấu hình | 12 trials, tối đa 3 trial đồng thời |
| **Validation metric** | Chỉ số dịch vụ tối ưu trong quá trình tìm tham số | `val_auc` cần **maximize** |
| **Experiment** | Nhóm có ý nghĩa chung để so sánh nhiều lần chạy | `dropout-risk-v1` |
| **Experiment run** | Một record có tên, tham số, metrics và có thể có artifacts/lineage | `baseline-001`, `candidate-002` |
| **Model Registry** | Quản lý artifacts/model versions và vòng đời triển khai | Phiên bản mô hình đã qua validation/test |

**Quan trọng:** một `HyperparameterTuningJob` lưu thông tin trial và metric tối ưu; điều đó **không đồng nghĩa** dịch vụ tự tạo một ExperimentRun riêng cho mọi trial. Muốn so sánh cùng các baseline/trials khác hoặc truy vết code/dataset trong **Vertex AI Experiments**, hãy tích hợp logging hoặc đồng bộ metadata theo thiết kế.

### 1.1. Hyperparameter tuning không phải fine-tuning mô hình nền tảng

Từ “tuning” có nhiều nghĩa. Ở đây ta tối ưu **hyperparameters của custom training model** qua các trial. Nó khác **supervised fine-tuning một foundation model/Gemini** hoặc prompt tuning, vốn có API, quyền, dữ liệu và cách tính phí khác. Không dùng cấu hình `HyperparameterTuningJob` dưới đây để suy ra quy trình fine-tune Gemini.

### 1.2. Tránh tối ưu theo tập test

~~~text
Dữ liệu đã được loại trùng và chia tách
  ├─ Train: fit mô hình và mọi bước preprocessing có học thống kê
  ├─ Validation: tính metric cho mỗi trial; chọn hyperparameters
  └─ Test (holdout): chỉ dùng sau khi chốt cấu hình/phương pháp
~~~

Với dữ liệu **theo thời gian** (học viên học trước/sau), chia train/validation/test theo **mốc thời gian** nếu bài toán dự báo tương lai; với nhiều hàng của cùng học viên, cân nhắc **group split theo student_id** để tránh một người xuất hiện ở cả train và validation. Bước chuẩn hóa/phân loại/cân bằng phải fit trong training fold, không nhìn thống kê của validation/test.

Một val AUC tăng không chắc tạo lợi ích sản phẩm: còn phải kiểm tra calibration, fairness, sự thay đổi phân phối dữ liệu, độ trễ inference và chi phí.

## 2. Thiết kế search space và objective

### 2.1. Chọn metric gắn với mục tiêu sản phẩm

| Bài toán | Metric có thể chọn | Lưu ý |
| --- | --- | --- |
| Phân loại rủi ro bỏ học | AUC ROC hoặc PR AUC, **MAXIMIZE** | Nếu lớp dương rất hiếm, PR AUC/recall@precision có thể sát nhu cầu hơn accuracy |
| Hồi quy thời gian hoàn thành | MAE/RMSE, **MINIMIZE** | Xem đơn vị và tác động outliers |
| Xếp hạng nội dung | NDCG@K, **MAXIMIZE** | Validation phải đại diện truy vấn/nhóm người dùng |
| Dự báo nhu cầu | WAPE/sMAPE/MAE theo SLA | Tránh metric mất ổn định khi giá trị thực bằng 0 |

**Tên metric phải trùng tuyệt đối** giữa khai báo tuning job và mã `report_hyperparameter_tuning_metric`. Tuning sẽ không có tín hiệu đúng nếu code báo `auc` nhưng `metric_spec` khai báo `val_auc`, hoặc nếu train chỉ `print()` số liệu mà không báo theo giao thức được hỗ trợ.

### 2.2. Kiểu hyperparameter và cách lấy mẫu

| Kiểu | Ví dụ | Đặt khi |
| --- | --- | --- |
| **Double / continuous** | `learning_rate ∈ [1e-5, 1e-1]` | Tham số liên tục; dùng **log scale** nếu phân bố theo cấp số nhân |
| **Integer** | `max_depth ∈ [3, 15]` | Giá trị nguyên theo phạm vi |
| **Discrete** | `batch_size ∈ {16, 32, 64, 128}` | Chỉ chấp nhận tập số hữu hạn |
| **Categorical** | `optimizer ∈ {"adam", "sgd"}` | Chọn một danh mục không có thứ tự tuyến tính |

Nên bắt đầu với **2–5 hyperparameters có ảnh hưởng lớn** theo hiểu biết về model. Nếu trải rộng cả `learning_rate`, `batch_size`, `depth`, `dropout`, `activation`, `optimizer`, `weight_decay` với chỉ 6 trials, không thể khám phá hiệu quả một không gian tổ hợp lớn.

### 2.3. Các thuật toán tìm kiếm

- **Default/Bayesian optimization:** dùng kết quả các trial đã hoàn tất để gợi ý cấu hình tiếp theo, thường hiệu quả khi budget đắt.
- **Random search:** kiểm tra baseline không gian rộng, đơn giản và dễ so sánh.
- **Grid search:** thử lưới hữu hạn có chủ đích; trong Vertex AI chỉ dùng với các parameter specs hỗ trợ grid. Không đặt grid khổng lồ vì số tổ hợp tăng rất nhanh.

Không có thuật toán nào bảo đảm tìm **global optimum** với một budget hữu hạn và metric nhiễu. Dùng validation lặp/cross-validation hoặc nhiều seeds khi độ biến thiên ảnh hưởng quyết định.

## 3. Quản lý trial budget, concurrency và dừng sớm

Một Vertex AI HyperparameterTuningJob gồm **trial count**, **parallel count**, search algorithm, không gian tham số, objective và một **trial job spec** (máy/worker/container) được dùng cho mỗi lần train.

| Thiết lập | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| `max_trial_count` | Số lần thử tối đa mong muốn | Tăng cơ hội khám phá nhưng tăng giờ máy và chi phí |
| `parallel_trial_count` | Số trial có thể chạy đồng thời | Giảm thời gian thực nhưng tăng peak resources/quota và ít tận dụng kết quả thử trước |
| `max_failed_trial_count` | Ngưỡng failed trials liên quan việc dừng tuning job | Không nên đặt cao để bỏ qua lỗi cấu hình lan rộng |
| `measurement_selection` | Chọn metric tốt nhất hay cuối cùng khi trial báo nhiều measurements | `best` có thể thiên lệch khi metric nhiễu, `last` phù hợp tiến trình ổn định |
| Machine type/accelerator | Tài nguyên của **mỗi trial** | Nhiều trial đồng thời nhân nhu cầu CPU/GPU |
| Search algorithm | Quy tắc đề xuất hyperparameters | Bayesian tận dụng feedback hơn khi ít parallel trials |

**Ước lượng capacity:** 12 trials, mỗi trial chạy 20 phút trên 1 VM, có `parallel_trial_count=3`. Tổng **VM-minutes ≈ 12 × 20 = 240**, còn thời gian wall-clock lý tưởng khoảng **80 phút** nếu các trial đồng đều, provisioning không trễ và có đủ quota. Ba trial đồng thời không làm tổng compute còn một phần ba; chỉ có thể rút ngắn thời gian chờ.

Nếu mỗi trial dùng 1 GPU, peak có thể cần **3 GPU tương ứng** cùng quota/trong region, chưa kể storage, tải dữ liệu và overhead. Chọn giới hạn dựa trên ngân sách, quota, deadline, số trial và lợi ích học được từ những thử nghiệm trước.

### 3.1. Early stopping và measurement

Khi huấn luyện nhiều epochs, một trial kém rõ ràng có thể được **dừng sớm theo chính sách/thuật toán được hỗ trợ** hoặc tự dừng bằng early stopping trong script để tiết kiệm compute. Khi báo nhiều measurements, Vertex AI có thể dùng chiến lược `measurement_selection="best"` hoặc `"last"` để chọn measurement đại diện.

**Không nhầm hai cơ chế:** dừng training khi validation không cải thiện là logic học máy trong script hoặc chính sách HPT; `measurement_selection` chỉ quy định chọn phép đo nào để xếp hạng. Nếu kết quả epoch đầu tốt rồi giảm do overfit, `best` có thể cho điểm cao hơn; nếu chọn `best` trên metric nhiều nhiễu, dễ gặp **winner's curse**. Kiểm tra tài liệu thuật toán và số steps được report trước khi bật tự động dừng.

### 3.2. Quy tắc chốt ngân sách

1. Chạy **baseline** không tuning, đo metric + thời gian/chi phí.
2. Thử 4–8 trials nhỏ để xác nhận metric, parameter ranges và tính lặp lại.
3. Dựa trên kết quả mới mở rộng số trial/parallelism theo quota.
4. Đặt **timeout, alert và ngưỡng chi phí**, không để job thất bại/lặp mãi.
5. Dừng nếu cải thiện metric không tương xứng chi phí/độ phức tạp hoặc kém ổn định ngoài validation.

**Budget alerts không phải hard spending cap.** Khi chạy nhiều jobs cùng lúc phải tính **tổng CPU/GPU-hours** của tất cả trials, logs, Cloud Storage artifacts, network và các dịch vụ bổ trợ.

## 4. Ví dụ scikit-learn: train một trial và báo metric

Để tách rõ orchestration khỏi độ phức tạp mô hình, lab dùng **LogisticRegression trên dữ liệu tổng hợp** được tạo bởi `sklearn.datasets.make_classification`. Script chấp nhận hai tham số do HPT truyền và **report `val_auc`** cho Vertex AI bằng `cloudml-hypertune`. Không cần Cloud Storage/BigQuery data thật.

### 4.1. File `train.py`

~~~python
import argparse
import json
import numpy as np
from sklearn.datasets import make_classification
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--c", type=float, default=1.0)
    parser.add_argument("--max_iter", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report_hpt", action="store_true")
    args = parser.parse_args()

    if args.c <= 0 or args.max_iter < 1:
        raise ValueError("c must be > 0; max_iter must be >= 1")

    x, y = make_classification(
        n_samples=3000, n_features=20,
        n_informative=10, n_redundant=3,
        weights=[0.8, 0.2], flip_y=0.02,
        random_state=args.seed,
    )
    # Chia test TRƯỚC; trong HPT chỉ dùng train/validation.
    x_dev, _, y_dev, _ = train_test_split(
        x, y, test_size=0.2, stratify=y, random_state=args.seed
    )
    x_train, x_val, y_train, y_val = train_test_split(
        x_dev, y_dev, test_size=0.25,
        stratify=y_dev, random_state=args.seed
    )
    model = make_pipeline(
        StandardScaler(),  # fit CHỈ trên x_train, tránh leakage
        LogisticRegression(
            C=args.c, max_iter=args.max_iter, random_state=args.seed
        ),
    )
    model.fit(x_train, y_train)
    auc = roc_auc_score(y_val, model.predict_proba(x_val)[:, 1])
    if not np.isfinite(auc):
        raise ValueError("Validation AUC must be finite")

    print(json.dumps({
        "validation_auc": float(auc),
        "c": args.c, "max_iter": args.max_iter, "seed": args.seed
    }))

    # Trial báo metric qua giao thức HPT, không chỉ in ra stdout.
    if args.report_hpt:
        import hypertune  # pip package: cloudml-hypertune
        hypertune.HyperTune().report_hyperparameter_tuning_metric(
            hyperparameter_metric_tag="val_auc",
            metric_value=float(auc),
            global_step=1,
        )


if __name__ == "__main__":
    main()
~~~

**Chú ý:** đây là minh họa cho bài toán **custom training/hyperparameter optimization**, không phải một mô hình dự báo rủi ro học tập đủ chất lượng triển khai. Dataset được sinh bằng seed cố định nên các trial có thể so sánh tương đối công bằng. Tập test được tách nhưng **không dùng** để báo objective cho HPT; cần phương pháp đánh giá cuối độc lập sau khi chốt cấu hình.

Chạy **local** để kiểm tra logic không có chi phí cloud:

~~~bash
python -m pip install scikit-learn numpy
python train.py --c 0.1 --max_iter 200 --seed 42
~~~

Local run **không** có `--report_hpt`, nên không cần gói hypertune cho bước này. Nếu script không chạy, hãy sửa vấn đề parse/schema/model trước khi tiêu tốn tài nguyên Vertex AI.

### 4.2. Tên flag và báo metric phải khớp

Tuning service thêm các tham số do search space chọn vào command-line của trial, ví dụ:

~~~text
python train.py --report_hpt --c 0.03 --max_iter 100
~~~

Vì vậy `parameter_spec` phải có keys `c`, `max_iter` và script phải nhận `--c`, `--max_iter`. Objective job khai báo `val_auc` thì script phải gọi `report_hyperparameter_tuning_metric(hyperparameter_metric_tag="val_auc", ...)`. Nếu không khớp, trial có thể chạy hết nhưng optimizer không có metric hợp lệ.

## 5. Tạo HyperparameterTuningJob bằng Vertex AI SDK

### 5.1. Điều kiện trước khi gửi job thật

Chỉ dùng **project lab được phê duyệt** với billing, Vertex AI API đã bật và region hỗ trợ custom training. Cần:

- Quyền tạo/đọc Vertex AI **CustomJobs/HyperparameterTuningJobs**, truy cập Cloud Logging để xem lỗi.
- **Service account dành cho training** với quyền tối thiểu trên bucket artifacts/nguồn dữ liệu nếu có; submitter có `iam.serviceAccounts.actAs` trên SA đó.
- **Cloud Storage staging bucket** trong location phù hợp, IAM cho người upload source và runtime; image được kiểm chứng có Python/scikit-learn phù hợp.
- Quota máy (CPU/GPU nếu dùng), giới hạn trial/parallelism và budget alert.
- Không đưa dữ liệu thật, credential hoặc danh tính học viên vào source, console logs hay experiment parameters.

Trong môi trường doanh nghiệp có VPC Service Controls, private egress, Artifact Registry, CMEK hoặc custom network, cần cấu hình network/service agents theo chính sách riêng. Các lệnh trong bài chỉ là **tài liệu**, không tự tạo/chạy job trên GCP.

### 5.2. File `submit_tuning.py`

Ví dụ SDK sử dụng `CustomJob.from_local_script` để đóng gói script ở mục 4 thành training job và đặt nó làm template cho từng trial:

~~~python
import os
from google.cloud import aiplatform
from google.cloud.aiplatform import hyperparameter_tuning as hpt

PROJECT_ID = os.environ["PROJECT_ID"]
LOCATION = os.environ["LOCATION"]
STAGING_BUCKET = os.environ["STAGING_BUCKET"]  # gs://...
TRAINING_SA = os.environ["TRAINING_SA"]        # email của SA đã cấp quyền
TRAINING_IMAGE = os.environ["TRAINING_IMAGE"]  # image Python đã được duyệt

aiplatform.init(
    project=PROJECT_ID,
    location=LOCATION,
    staging_bucket=STAGING_BUCKET,
)

custom_job = aiplatform.CustomJob.from_local_script(
    display_name="student-risk-trial-lab",
    script_path="train.py",
    container_uri=TRAINING_IMAGE,
    requirements=["numpy", "scikit-learn", "cloudml-hypertune"],
    args=["--report_hpt", "--seed", "42"],
    machine_type="n1-standard-4",
    replica_count=1,
)

hp_job = aiplatform.HyperparameterTuningJob(
    display_name="student-risk-hpt-lab",
    custom_job=custom_job,
    metric_spec={"val_auc": "maximize"},
    parameter_spec={
        "c": hpt.DoubleParameterSpec(
            min=0.001, max=100.0, scale="log"
        ),
        "max_iter": hpt.DiscreteParameterSpec(
            values=[100, 200, 300], scale="linear"
        ),
    },
    max_trial_count=6,
    parallel_trial_count=2,
    search_algorithm=None,        # Default optimization
    measurement_selection="last",
    labels={"purpose": "learning-lab"},
)

# THAO TÁC TÍNH PHÍ: chỉ chạy trên project/budget được duyệt.
hp_job.run(service_account=TRAINING_SA, sync=True)

print("Job:", hp_job.resource_name)
for trial in hp_job.trials:
    print("Trial:", trial.id, "State:", trial.state,
          "Parameters:", trial.parameters,
          "Final:", trial.final_measurement)
~~~

**Điều kiện để chạy được:** `TRAINING_IMAGE` phải là **URI image có thật và tương thích với SDK/runtime**, không phải placeholder. Chọn image theo [danh sách prebuilt containers](https://cloud.google.com/vertex-ai/docs/training/pre-built-containers) còn được hỗ trợ hoặc image riêng tại Artifact Registry. Với production, **pin version thư viện và image digest** thay vì dùng `latest`/`requirements` không pin; tham số được giữ đơn giản để tập trung vào HPT.

SDK tạo **6 trials tối đa**, **2 trials chạy song song tối đa**, dùng một mẫu worker 1 `n1-standard-4` mỗi trial. Vì script dùng dữ liệu tổng hợp, không có yêu cầu GPU hay kết nối database. Với workload thật, đặt chính xác `base_output_dir`, quyền Cloud Storage, network/region, encryption và workload identity theo quy định.

**Các ranh giới quan trọng:**

- `max_trial_count=6` là budget thử nghiệm, không phải 6 bản model tốt nhất được tự đăng ký Model Registry.
- `hp_job.trials` chứa trial parameters và final measurements **sau khi job có dữ liệu/đã hoàn tất**; cần kiểm tra trạng thái terminal/failed trước khi chọn.
- `metric_spec={"val_auc":"maximize"}` tối ưu **validation**; không tự đánh giá test hoặc fairness.
- `parallel_trial_count=2` có thể tăng tổng tài nguyên đang dùng nhưng không bảo đảm tốc độ hoàn tất tăng gấp đôi.
- `hp_job.run(sync=True)` chờ job, có thể lỗi nếu trial, quota, network hoặc IAM không đáp ứng; script ứng dụng cần ghi lỗi và không coi “đã submit” là “đã chọn model”.

### 5.3. Tùy chọn gcloud và REST

Nếu dự án dùng infrastructure automation thay vì Python SDK, có thể gửi job bằng **Batches/Training Job API tương ứng Vertex AI**, qua lệnh:

~~~bash
# Chỉ tra cứu lệnh trước khi tạo tài nguyên tính phí:
gcloud ai hp-tuning-jobs create --help

# THAO TÁC TÍNH PHÍ; dùng file config được owner review:
# gcloud ai hp-tuning-jobs create \
#   --region="$LOCATION" \
#   --display-name="student-risk-hpt-lab" \
#   --max-trial-count=6 --parallel-trial-count=2 \
#   --config="hpt-config.yaml"
~~~

Config cần định nghĩa **study metrics, search parameters và trial job spec** (image/worker machine/args). Không sao chép lệnh `gcloud ai custom-jobs create` rồi cho rằng đã có optimizer; đó là job training đơn lẻ. Với SDK `google-cloud-aiplatform`, HPT job dùng lớp `HyperparameterTuningJob`, không phải `CustomJob.run` gọi 6 lần theo vòng lặp.

### 5.4. Lấy kết quả trial đúng cách

Khi job hoàn tất, so sánh trial có **state thành công** và **metric hợp lệ**, rồi chọn một hoặc vài cấu hình ứng viên. Không lấy `trial 1` vì đó là trial chạy trước; cũng không mặc định tối ưuizer đảm bảo thắng một baseline đã được tune kỹ.

| Trial (giả định) | `C` | `max_iter` | `val_auc` | Nhận xét |
| --- | ---: | ---: | ---: | --- |
| T01 | 0.001 | 100 | 0.841 | Regularization mạnh, có thể underfit |
| T02 | 0.03 | 200 | 0.886 | Ứng viên |
| T03 | 0.3 | 200 | **0.893** | Đứng đầu validation |
| T04 | 10 | 100 | 0.871 | Cần xem convergence |
| T05 | 0.1 | 300 | 0.889 | Gần bằng T03 |
| T06 | 50 | 300 | 0.865 | Không cải thiện |

**Đây là số giả định để luyện ra quyết định**, không phải kết quả thực thi script. Nếu chênh lệch nhỏ và validation nhiễu, nên so thêm seeds/folds và độ lệch chuẩn; một trial `val_auc=0.893` **không** bảo đảm test AUC hoặc business impact bằng vậy.

## 6. Quản lý thí nghiệm với Vertex AI Experiments

Hyperparameter tuning giúp **tìm tham số**; experiment tracking giúp trả lời: *ai chạy, với code/dữ liệu nào, dùng tham số gì, hiệu quả ra sao, model/artifact ở đâu, có tái lập được không?*

### 6.1. Experiment, run và metrics

| Nội dung log | Nơi ghi | Ví dụ |
| --- | --- | --- |
| **Run parameters** | Vertex AI Experiments | `c=0.3`, `max_iter=200`, `dataset_version=v20261118` |
| **Summary metrics** | Experiment Run | `val_auc=0.893`, `test_auc=0.880` (chỉ final run) |
| **Time series metrics** | Experiment Run + **Vertex AI TensorBoard backing resource** | `train_loss`/`val_loss` theo epoch |
| **Artifacts/metadata** | Vertex ML Metadata/Experiments và nơi lưu artifact | GCS model URI, dataset digest, model version |
| **Pipeline run/lineage** | Vertex AI Pipelines/Metadata nếu tích hợp | Data validation → train → evaluate → register |

**Summary metrics** là giá trị đơn đại diện một run; **time series** ghi nhiều điểm theo step và cần **TensorBoard instance** phù hợp. `log_metrics` được gọi nhiều lần với cùng key thường **ghi đè** giá trị trước; không dùng nó để tạo biểu đồ loss theo epoch. `cloudml-hypertune` báo metric cho optimizer, **không thay thế** `aiplatform.log_params/log_metrics` để lưu run theo convention của nhóm.

### 6.2. Code ghi experiment run (không phải HPT submission)

Đoạn code dưới đây ghi record cho một baseline/candidate đã có metric, **không tự train mô hình**:

~~~python
import os
from google.cloud import aiplatform

aiplatform.init(
    project=os.environ["PROJECT_ID"],
    location=os.environ["LOCATION"],
    experiment="student-risk-lab",
)

# Mỗi lần thử có run ID riêng, không ghi đè run của người khác.
with aiplatform.start_run(run="baseline-001") as run:
    run.log_params({
        "algorithm": "logistic_regression",
        "c": 1.0, "max_iter": 200, "seed": 42,
        "dataset_version": "synthetic-v1",
        "code_revision": "REPLACE_WITH_GIT_COMMIT",
    })
    run.log_metrics({
        "val_auc": 0.87,
        "fit_seconds": 2.1,
    })

# Đọc bảng so sánh (yêu cầu quyền xem Experiment).
df = aiplatform.get_experiment_df(
    experiment="student-risk-lab",
    include_time_series=False,
)
print(df[["run_name", "param.c", "metric.val_auc"]].head())
~~~

**Chú ý:** `0.87` và `2.1` chỉ là ví dụ, phải thay bằng **metric đo được** nếu dùng làm bằng chứng. `REPLACE_WITH_GIT_COMMIT` bắt buộc thay bằng revision thật của code. Không ghi mật khẩu, token, đường dẫn chứa PII hoặc nguyên danh sách học viên vào params/tags/logs. Với thử nghiệm thật, có thể dùng `aiplatform.start_run(run=..., resume=True)` chỉ khi **cố ý tiếp tục đúng run**; tránh ghi chồng và làm mất lịch sử.

### 6.3. Time series, TensorBoard và autologging

~~~python
# Mẫu ý tưởng khi experiment đã liên kết Vertex AI TensorBoard:
# aiplatform.init(project=..., location=...,
#                 experiment="student-risk-lab",
#                 experiment_tensorboard="projects/.../tensorboards/...")
# with aiplatform.start_run(run="train-epochs-001"):
#     for epoch, loss in enumerate(epoch_losses):
#         aiplatform.log_time_series_metrics(
#             {"train_loss": float(loss)}, step=epoch
#         )
~~~

Nếu chưa có **backing TensorBoard instance**, không gọi `log_time_series_metrics` rồi giả định số liệu đã được lưu. SDK cũng có `aiplatform.autolog()` cho một số frameworks; đó là **tính năng hỗ trợ theo framework**, không tự log đúng mọi custom metric, dataset version hoặc artifact. Với HPT, thử tích hợp **trong từng trial** hoặc đồng bộ một bảng trials → experiment runs có naming cố định sau khi job hoàn tất; **không** tự động gộp nhiều trial thành cùng một run.

## 7. Chọn mô hình cuối và khả năng tái lập

### 7.1. Quy trình promotion an toàn

1. **Chốt HPT campaign** sau khi đủ trials theo budget, xác nhận trial state/measurement và so với baseline.
2. Chọn **một vài ứng viên** theo validation metric, độ ổn định giữa folds/seeds, thời gian train và inference cost; không chỉ lấy số lớn nhất.
3. **Đóng băng hyperparameters, code revision, dữ liệu/feature definitions và preprocessing**.
4. **Retrain** cấu hình được chọn trên train + validation (theo chính sách đánh giá) rồi đánh giá **test holdout chưa được dùng để chọn**.
5. Kiểm tra chất lượng theo nhóm, calibration, robustness, privacy/bias, latency và yêu cầu vận hành.
6. Chỉ sau khi đạt gates mới lưu **model artifact**, đăng ký **Vertex AI Model Registry**/version và xem xét triển khai có kiểm soát qua endpoint/batch prediction.
7. Ghi metadata lineage `experiment_run_id`, `hpt_job_id`, `trial_id`, dữ liệu/model checksum, code version và người phê duyệt.

**Không tự động deploy “best trial”**. HPT best theo `val_auc` không chắc là best theo business KPI, fairness hoặc giá inference. Khi dữ liệu bị drift hay feature pipeline thay đổi, phải đánh giá lại ngay cả khi hyperparameters không đổi.

### 7.2. Checklist tái lập thí nghiệm

| Thông tin | Vì sao cần giữ |
| --- | --- |
| `dataset_uri`, version/snapshot, schema và checksum | Đầu vào phải không đổi giữa các trials, hoặc thay đổi có ghi rõ |
| Train/validation/test split policy + seed | Tránh lệch so sánh và data leakage |
| Docker image **digest**, dependency lock, Python/framework version | Mô hình có thể khác khi runtime/thư viện đổi |
| Code commit, feature engineering, preprocessing | Đảm bảo script và transform được tái sử dụng |
| Hyperparameters, trial state, optimizer version/algorithm | Giải thích kết quả và chi phí |
| Summary metrics, đường cong validation nếu có | So sánh chất lượng và overfit |
| Training resource, region, GPU/CPU-hours, chi phí | Quyết định trade-off và ngân sách |
| Model artifact URI/hash + evaluation report | Truy được model nào đã triển khai |

Giữ seed giúp tái lập **phần nào**, nhưng GPU, distributed training, non-deterministic kernels và thứ tự xử lý dữ liệu có thể khiến kết quả không hoàn toàn bit-for-bit. Với khác biệt nhỏ 0,001 AUC, đừng coi thắng lợi chắc chắn khi chưa đánh giá phương sai.

### 7.3. Multi-metric và ràng buộc nghiệp vụ

Vertex AI HPT có thể cấu hình mục tiêu metrics theo các tính năng được hỗ trợ, nhưng **một con số tối ưu** không thể thay thế toàn bộ yêu cầu. Ví dụ chọn AUC cao nhưng inference latency quá 200 ms hoặc precision quá thấp có thể không phù hợp.

Một quy tắc ra quyết định minh họa:

~~~text
Điều kiện tối thiểu:
  validation PR-AUC >= 0.55
  p95 inference latency <= 150 ms ở batch size thực tế
  không vi phạm chính sách dữ liệu và fairness gates
Sau đó:
  ưu tiên chi phí / 1.000 dự đoán thấp nhất
  trong nhóm đáp ứng yêu cầu trên
~~~

Ngưỡng trên **chỉ là giả định**; phải dựa vào sản phẩm, nhóm người dùng và đánh giá khoa học của dự án. Không dùng tuning metric như một hợp đồng duy nhất cho việc triển khai.

## 8. Bảo mật, IAM, mạng và quản lý chi phí

### 8.1. Tách quyền submit và quyền chạy model

| Vai trò | Phạm vi IAM nên có | Rủi ro nếu cấp quá rộng |
| --- | --- | --- |
| ML engineer/CI submit job | Quyền tạo/đọc HPT và CustomJob trong project/region đã duyệt | `Vertex AI Admin` toàn project nếu chỉ cần submit |
| Người dùng custom service account | `iam.serviceAccounts.actAs` trên **SA training được duyệt** | Có thể mạo danh các SA mạnh hơn nếu cấp toàn project |
| **Training service account** | Quyền đọc dữ liệu train/validation, ghi artifacts, logs; BigQuery jobs/data nếu dùng | Truy cập mọi buckets/datasets chứa PII |
| Experiment/metadata consumer | Quyền ghi/xem Vertex AI Experiments/metadata theo vai trò | Xóa/chỉnh metadata của người khác |
| Deployer/model owner | Quyền đăng ký/deploy model **sau phê duyệt** | Quyền deploy bị trao cho mọi người chạy HPT |

**Mã trong training container không tự có quyền** chỉ vì người submit đang đăng nhập gcloud. Nếu dùng custom SA với `hp_job.run(service_account=...)`, các truy cập Cloud Storage/BigQuery/Artifact Registry phải được cấp cho **runtime identity thực** và service agents liên quan. Không lưu service account JSON key trong notebook, source code, Docker image hoặc environment logs.

### 8.2. Bảo vệ dữ liệu học viên

- Dữ liệu học tập/thanh toán có thể chứa PII và thông tin nhạy cảm. Chỉ dùng **features được phê duyệt**, mã hóa, ẩn danh/pseudonymization và tuân thủ data residency/retention.
- Với BigQuery, áp dụng IAM, row/column policies nếu phù hợp. Với Cloud Storage, giới hạn bucket/prefix và logs.
- Đừng ghi raw feature rows/labels, access tokens, URI có signed URL, output dự đoán cá nhân vào Vertex AI Experiments, TensorBoard hoặc stdout.
- Chọn region đặt training/model/artifacts theo yêu cầu lưu trú dữ liệu; mạng riêng, CMEK và VPC Service Controls cần thiết kế theo khả năng hỗ trợ và chính sách.
- Khi chia sẻ experiment dashboard, nhớ rằng **metric/parameter names/values** cũng có thể tiết lộ chi tiết nhạy cảm hoặc đường dẫn dữ liệu.

### 8.3. Tối ưu hóa ngân sách tuning

Ví dụ campaign có **20 trials**, mỗi trial chạy trung bình 25 phút trên một máy được tính phí:

\[
20 \times \frac{25}{60} \approx 8{,}33\ \text{machine-hours}
\]

Đây là **giờ máy tương đương**, không phải tiền; nếu trial dùng nhiều worker/GPU thì phải nhân từng resource theo giá tương ứng và thời gian thực. `parallel_trial_count=4` có thể giúp hoàn thành nhanh hơn nhưng cần peak capacity lớn hơn; tổng giờ máy **không tự giảm** vì chạy đồng thời.

| Thành phần | Cần dự toán |
| --- | --- |
| Custom training compute | CPU/GPU machine-hours cho mỗi trial, retries và failed trials |
| Cloud Storage / BigQuery | Input reads, artifacts, logs/checkpoints, data egress |
| Vertex AI Experiments/TensorBoard/metadata | Tài nguyên được bật, retention, lưu trữ metric và billing theo hiện hành |
| Network & security | Egress, private networking, CMEK/KMS nếu dùng |
| Retrain/đánh giá/deployment | Thêm lần train cuối, batch prediction hoặc online endpoint chạy liên tục |

**Tối ưu chi phí thực tế:** bắt đầu bằng baseline, chạy trial nhỏ để xác nhận plumbing, giới hạn search space, dùng CPU cho mô hình nhẹ, chỉ mở GPU khi cần, dùng early stopping có kiểm chứng, lưu artifact có retention và dừng/không tạo endpoint test luôn bật ngoài ý muốn. Giá và quota khác nhau theo region/machine/accelerator; dùng [bảng giá Vertex AI](https://cloud.google.com/vertex-ai/pricing) và Cloud Billing để chốt budget.

## 9. Quan sát HPT và chẩn đoán lỗi

### 9.1. Những nguồn quan sát hữu ích

| Nguồn | Xem gì? |
| --- | --- |
| **HyperparameterTuningJob / Trials** | Trạng thái job, trial IDs, tham số gợi ý, final/intermediate measurements, lỗi |
| **Cloud Logging** | Lỗi Python/import, báo metric, training container startup, IAM/permission |
| **Cloud Monitoring** | CPU/GPU/network utilization, training job metrics, quota và latency |
| **Vertex AI Experiments** | Baseline vs candidate metrics, params, artifacts, thông tin run |
| **Vertex AI TensorBoard** | Learning curves theo epoch/step khi có backing resource |
| **BigQuery/Cloud Storage metrics** | Throughput/latency nguồn dữ liệu, lỗi permission, chi phí |

**Không dựa duy nhất vào “job succeeded”**: tuning có thể tạo trial có metric không tương đương, chọn sai validation, hoặc mã train đã fit preprocessing trên cả test. Phải kiểm tra script và số liệu, cũng như trạng thái từng trial.

### 9.2. Runbook theo tầng lỗi

| Hiện tượng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| HPT job tạo không được | Thiếu `aiplatform.hyperparameterTuningJobs.create`, API/quota hoặc tham số sai | Kiểm tra principal submit, IAM và config, không cấp Owner ngay |
| `Permission denied` khi gắn custom SA | Thiếu `iam.serviceAccounts.actAs` | Kiểm tra quyền trên đúng SA |
| Container khởi động rồi lỗi import | Image/dependencies/Python version không phù hợp | Pin image digest và package versions, chạy local smoke test |
| Trial chạy hết nhưng không có objective | Sai `metric_tag`, chưa gọi hypertune report, exception trước bước report | So `metric_spec` với script, xem driver logs và measurements |
| Tham số job không vào mô hình | Sai `--flag`/`argparse`, script bỏ qua args | In param values **không nhạy cảm**, assert ranges và kiểm thử local |
| Trials chạy rất chậm | Provisioning, quota/GPU, data-loading, CPU/I/O bottleneck | Tách scheduling vs training, xem machine utilization |
| Nhiều trials FAILED | Bug chung, dataset path, IAM, không đủ memory | Dừng campaign, sửa script trước khi tiêu budget thêm |
| AUC validation cao nhưng test thấp | Data leakage, overfit vào validation, split sai, metric nhiễu | Audit pipeline/splits, giảm search space, đánh giá unbiased test |
| Experiments không có trial metrics | HPT không tự đồng bộ sang từng ExperimentRun | Tích hợp log params/metrics hoặc đồng bộ trials → runs |
| Không log được learning curve | Chưa có TensorBoard backing resource hoặc quyền | Kiểm tra `experiment_tensorboard`, IAM và SDK version |
| Cost vượt dự toán | Quá nhiều trials × machine/GPU, retried jobs, artifacts/logs | Giảm budget/parallelism, kiểm tra quotas và billing |

**Quy trình 6 bước:** chốt project/region/job ID → đọc trial state và error → xem training logs → đối chiếu script/metric flags → kiểm tra data/VM/quota/IAM → thử lại **một cấu hình nhỏ** với run ID khác. Không đồng thời thay IAM, image, seed, dữ liệu và search space vì không xác định được nguyên nhân.

## 10. Lab theo từng mức độ: local trước, cloud sau

**Mục tiêu:** hiểu một lần train, tác động của hyperparameters, quá trình chọn trial và cách ghi ExperimentRun. Lab không cần dữ liệu thật và **không yêu cầu tạo online endpoint**.

### 10.1. Mức A — không tạo tài nguyên GCP

Trong môi trường Python local **được phép cài package**, tạo một thư mục lab có `train.py` từ mục 4 rồi chạy:

~~~bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install numpy scikit-learn

python train.py --c 0.001 --max_iter 100 --seed 42
python train.py --c 0.1 --max_iter 200 --seed 42
python train.py --c 10 --max_iter 300 --seed 42
~~~

**Ghi vào bảng** tham số, validation AUC và thời gian thực thi cho ba lần chạy. Không thay seed trong lần so sánh đầu. Nếu có `ConvergenceWarning`, không tự bỏ qua: nó có thể phản ánh `max_iter` thấp; hãy thử tăng iterations hoặc thay regularization với lý do rõ ràng.

| Run | `C` | `max_iter` | Val AUC (đo) | Nhận xét |
| --- | ---: | ---: | --- | --- |
| Local-01 | 0.001 | 100 | ... | Regularization mạnh |
| Local-02 | 0.1 | 200 | ... | So với baseline |
| Local-03 | 10 | 300 | ... | Kiểm tra overfit/convergence |

Đây là bài thử **script/metric contract**; không cho phép dùng ba điểm nhỏ để kết luận tuning sản phẩm đủ tốt. Dữ liệu tổng hợp vẫn có nhiễu có chủ đích.

### 10.2. Mức B — tùy chọn trên project lab được duyệt

Chỉ sau khi có **billing, Vertex AI API, staging bucket, training SA và budget** được phê duyệt:

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export LOCATION="us-central1"
export STAGING_BUCKET="gs://YOUR_APPROVED_LAB_STAGING_BUCKET"
export TRAINING_SA="YOUR_APPROVED_TRAINING_SA@YOUR_PROJECT.iam.gserviceaccount.com"
export TRAINING_IMAGE="YOUR_VERIFIED_PYTHON_TRAINING_IMAGE_URI"

# CHỈ ĐỌC: xác minh project, API và quota trước khi trả chi phí.
gcloud config set project "$PROJECT_ID"
gcloud services list --enabled --filter="aiplatform.googleapis.com"
gcloud storage buckets describe "$STAGING_BUCKET"
gcloud ai hp-tuning-jobs list --region="$LOCATION"
~~~

Khi mọi điều kiện đã được owner xác minh, môi trường local đã cài `google-cloud-aiplatform`, `train.py` đã được smoke test, mới chạy:

~~~bash
# CÓ TÍNH PHÍ: tạo HPT job tối đa 6 trials.
python -m pip install google-cloud-aiplatform
python submit_tuning.py
~~~

Nếu image, bucket, SA hoặc quota chưa đúng, **không chạy** và làm lab giấy ở mục 10.3. Đừng dùng email service account giả để thử “có chạy không”; không cấp `Vertex AI Admin` cho cả team chỉ để chữa lỗi 403.

Sau khi job có ID, đọc trạng thái theo Console hoặc:

~~~bash
# CHỈ ĐỌC: thay bằng HPT job ID thật.
gcloud ai hp-tuning-jobs describe "YOUR_HPT_JOB_ID" \
  --region="$LOCATION" --project="$PROJECT_ID"
~~~

Trên Console, tìm mục **Vertex AI → Training → Hyperparameter tuning jobs** (nhãn giao diện có thể thay đổi theo lần cập nhật sản phẩm) để xem trial parameters/metrics và logs. Không coi “6 trial được submit” nghĩa là mọi trial đều thành công; đối chiếu state/measurement từng trial.

### 10.3. Mức C — lab giấy không cần GCP

Giả định có bảng trial ở mục 5.4, baseline val AUC bằng **0,870**. Hãy:

1. Chọn cấu hình ứng viên theo validation, ghi rõ trial nào và chênh lệch so baseline.
2. Ước tính tác động nếu T03/T05 chỉ khác **0,004 AUC** trong khi sai số bootstrap validation khoảng ±0,01.
3. Đề xuất một bước kiểm chứng **không chạm test holdout**.
4. Viết experiment run record tối thiểu cần log, kể cả `trial_id`, dataset version và cost.
5. Nêu khi nào có thể xem **test holdout**.

**Định hướng:** T03 đứng đầu validation (0,893), chênh baseline 0,023; T03–T05 rất nhỏ so sai số 0,01 nên cần nhiều seeds/folds hoặc thêm validation đúng thiết kế. Test holdout chỉ dùng **sau khi chốt phương pháp/cấu hình**, không chạy đi chạy lại và chỉnh search space dựa vào test.

### 10.4. Dọn dữ liệu và dừng chi phí

Không tạo Endpoint trong lab; nếu đã tạo HPT job thì kiểm tra mọi trial **terminal** và quyền/hồ sơ logs trước khi xóa metadata theo retention policy. Nếu cần hủy job đang chạy, thực hiện từ Console/API có xác nhận owner; thao tác hủy có thể **không có hiệu lực tức thì** và chi phí đến thời điểm dừng vẫn phát sinh. Chỉ xóa **file/artifact trong staging prefix riêng do bạn tạo**, không dùng lệnh xóa recursive trên bucket dùng chung.

## 11. Bài tập tình huống

### Tình huống A — Overfit vào validation

Nhóm thử 2.000 tổ hợp trên cùng 1.000 bản ghi validation, chọn một trial AUC 0,99. Trên test holdout, AUC chỉ 0,77.

**Yêu cầu:** phân biệt overfitting của **mô hình** với overfitting do **quá nhiều lần chọn thử trên cùng validation**.

**Hướng giải:** việc chọn 2.000 trials trên một validation nhỏ khiến optimizer khai thác nhiễu và **selection bias**; chưa chắc model train quá nhiều epochs. Cần validation đại diện hơn, nested CV nếu hợp lý, giảm search budget, dùng holdout test chỉ một lần và kiểm tra leakage theo học viên/thời gian.

### Tình huống B — Parallelism và quota GPU

Một trial cần 2 GPU và mất 45 phút. Kế hoạch là 16 trials với `parallel_trial_count=8`; quota region chỉ có 8 GPU rảnh.

**Yêu cầu:** có chạy được 8 trials đồng thời không? Đề xuất cận trên hợp lý.

**Hướng giải:** 8 trials × 2 GPU = **16 GPU peak**, lớn hơn quota 8; về mặt GPU chỉ có tối đa **4 trials đồng thời**, chưa kể quota/máy khác. Chọn ≤4 và đo hiệu quả Bayesian search/chi phí. Nếu giảm parallelism, tổng GPU-hours lý tưởng vẫn `16 × 2 × 0,75 = 24 GPU-hours`, không giảm chỉ nhờ đổi lịch.

### Tình huống C — Metric khai báo khác script

`metric_spec={"val_auc": "maximize"}` nhưng code gửi `hyperparameter_metric_tag="auc"`. Job tạo được và các trial có log in ra AUC, nhưng không có final measurements hợp lệ.

**Yêu cầu:** sửa ở đâu?

**Hướng giải:** đổi **cùng một tên** ở configuration và `report_hyperparameter_tuning_metric`, chạy một trial smoke test trước khi mở rộng campaign; `print()` trong stdout không thay thế metric report.

### Tình huống D — Kết quả không tái lập

T03 tốt nhất nhưng không ai biết dữ liệu train, version thư viện và seed; một người đã cập nhật bảng BigQuery nguồn trước khi rerun.

**Yêu cầu:** bổ sung điều gì vào ExperimentRun và pipeline?

**Hướng giải:** lưu dataset snapshot/version hoặc checksum, cách split/seed, image digest, dependency lock, code commit, trial ID, hyperparameters, artifacts, metric và job ID. Không dùng tên table `latest` thay cho version; khi dữ liệu thay đổi, đó là thí nghiệm khác, không phải rerun y nguyên.

### Tình huống E — Chi phí vượt ngân sách

Một nhóm chạy 40 trials, mỗi trial 1 GPU, 30 phút; vì quota nên chỉ 2 trials chạy đồng thời. Owner hiểu nhầm “2 chạy cùng lúc” nghĩa là chỉ phải trả 1 GPU-hour.

**Yêu cầu:** tính tổng GPU-hours lý tưởng và giải thích.

**Hướng giải:** `40 × 0,5 × 1 = 20 GPU-hours`, chưa tính retries/provisioning/các tài nguyên khác. Parallelism 2 làm **thời gian wall-clock** lý tưởng khoảng `40 / 2 × 30 = 600 phút`, nhưng không làm mất 38 trial còn lại. Kiểm tra giá thực, quotas và stop criteria.

### Tình huống F — Thử nghiệm và mô hình sản phẩm

Một trial đứng đầu `val_auc` nhưng giảm recall của nhóm học viên mới, p95 inference latency gấp ba và yêu cầu dữ liệu phải ở region khác.

**Yêu cầu:** có tự động deploy không?

**Hướng giải:** **không**; cần kiểm thử fairness/recall theo phân khúc, latency/cost, compliance và data residency. HPT objective là một **tiêu chí kỹ thuật**, không thay các deployment gates. Chọn ứng viên cân bằng hoặc thiết kế objective/constraints khác rồi đánh giá lại theo quy trình.

### Bài tập định lượng — ngân sách so với thời gian

Ba phương án cho **24 trials**, mỗi trial 15 phút trên **1 VM giống nhau**:

| Phương án | Parallel trials | VM-hours lý tưởng | Wall-clock lý tưởng |
| --- | ---: | ---: | ---: |
| A | 1 | 6 | 360 phút |
| B | 4 | 6 | 90 phút |
| C | 8 | 6 | 45 phút |

**Câu hỏi:**

1. Vì sao VM-hours gần như bằng nhau? — Cả ba chạy **24 × 15 phút = 360 VM-minutes**, trước overhead/retries.
2. Vì sao C không nhất thiết cho **model tốt nhất**? — Bayesian optimization nhận feedback ít hơn từ các trials đang chạy đồng thời.
3. Nếu quota chỉ cho 4 VM, chọn phương án nào không vượt quota? — A hoặc B, với giả định một trial dùng đúng một VM.
4. Nếu báo cáo phải hoàn tất trong 1 giờ thì A/B/C có đảm bảo không? — Không; B lý tưởng 90 phút, C lý tưởng 45 phút nhưng vượt quota trong ví dụ và còn provisioning. Phải đổi tài nguyên, tối ưu script hoặc xin quota được phê duyệt.

### Tự kiểm tra

1. **Hyperparameter khác parameter thế nào?** — Hyperparameter do cấu hình/search chọn; model parameter học trong train.
2. **Một trial có phải một ExperimentRun tự động không?** — Không, trừ khi có tích hợp tracking.
3. **Tại sao không dùng tập test cho HPT?** — Gây overfit vào test và đánh giá cuối lạc quan.
4. **Tên `metric_spec` có cần trùng với tên report từ script?** — Có.
5. **`parallel_trial_count` lớn có làm tổng compute tự giảm không?** — Không.
6. **`measurement_selection="best"` có chắc tốt khi metric nhiễu?** — Không; có thể chọn cực trị do nhiễu.
7. **Summary metrics khác time series ở đâu?** — Summary lưu một giá trị; time series lưu chuỗi theo step, cần TensorBoard.
8. **Seed cố định có bảo đảm GPU train tái lập bit-for-bit không?** — Không chắc.
9. **Tại sao cần training SA riêng?** — Thực thi least privilege, tách submitter khỏi quyền dữ liệu.
10. **Best validation trial có thể deploy thẳng không?** — Không; cần retrain/test và các production gates.

## 12. Checklist review trước chiến dịch tuning production

| Hạng mục | Điều kiện đạt |
| --- | --- |
| **Bài toán** | Có baseline, business KPI, metric mục tiêu và chiều `maximize`/`minimize` rõ ràng |
| **Dữ liệu** | Dataset/split đúng thời gian/nhóm, không leakage, có version và kiểm tra quyền |
| **Tính đúng script** | Local smoke test, parse đủ hyperparameter flags, report metric đúng tên và hợp lệ |
| **Search space** | Tham số có ý nghĩa, range/scale đúng, không quá rộng so với trial budget |
| **Cost/quota** | Max/parallel trials, machine/GPU quota, timeout, budget và cảnh báo được duyệt |
| **IAM/network** | Submitter, runtime SA, Artifact Registry, Cloud Storage/BigQuery và VPC đúng least privilege |
| **Reproducibility** | Code commit, image digest, dependency lock, seed, dataset version và input artifacts |
| **Tracking** | Trial ID ↔ HPT job ID ↔ ExperimentRun ID, metrics, timing, cost và artifacts có khả năng đối soát |
| **Evaluation** | Validation để chọn, test holdout dùng một lần, kiểm tra confidence intervals và phân khúc |
| **Promotion** | Retrain, kiểm tra inference latency/fairness/compliance, model version và người phê duyệt |
| **Vận hành** | Runbook thất bại/quota/permission, tài nguyên có cleanup/retention, không deploy tự động ngoài quy trình |

### Mẫu báo cáo thí nghiệm cho kỹ sư ML

~~~text
Experiment:        student-risk-lab
Objective:         maximize val_auc
Dataset/version:   synthetic-v1 / checksum: ...
Split policy:      train/validation/test; group/time policy: ...
Training image:    digest: ...
Code revision:     commit: ...
HPT job ID:        projects/.../hyperparameterTuningJobs/...
Trials:            6 max; 2 concurrent; 0-6 completed
Best candidates:   trial ID + hyperparameters + val metric
Uncertainty:       folds/seeds + confidence interval
Cost:              actual machine-hours + storage/network
Test result:       only after selecting candidate, with method fixed
Decision:          approve / reject / investigate
Owner and date:    ...
~~~

Nếu một trường quan trọng chưa biết, đánh dấu **chưa xác minh** thay vì bịa giá trị. Những thay đổi dữ liệu, code hoặc split phải được ghi thành experiment run/campaign khác để giữ lịch sử đáng tin.

## 13. Tài liệu Google Cloud chính thức

- [Overview of hyperparameter tuning](https://cloud.google.com/vertex-ai/docs/training/hyperparameter-tuning-overview) — trials, metrics, search optimization và giới hạn.
- [Create a hyperparameter tuning job](https://cloud.google.com/vertex-ai/docs/training/using-hyperparameter-tuning) — cách report objective, cấu hình job, thông số trial.
- [Vertex AI Python SDK: HyperparameterTuningJob](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.HyperparameterTuningJob) — `metric_spec`, `parameter_spec`, trial count, parallelism và `run()`.
- [Vertex AI Python SDK: CustomJob](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.CustomJob) — `from_local_script`, image, requirements và runtime identity.
- [Vertex AI training containers](https://cloud.google.com/vertex-ai/docs/training/pre-built-containers) — image/runtime được hỗ trợ.
- [Vertex AI Experiments overview](https://cloud.google.com/vertex-ai/docs/experiments/intro-vertex-ai-experiments) — experiments, runs, metrics, artifacts và ML Metadata.
- [Log data to experiment runs](https://cloud.google.com/vertex-ai/docs/experiments/log-data) — `log_params`, `log_metrics` và TensorBoard time series.
- [Autolog data](https://cloud.google.com/vertex-ai/docs/experiments/autolog-data) — điều kiện và frameworks hỗ trợ autologging.
- [Compare and analyze runs](https://cloud.google.com/vertex-ai/docs/experiments/compare-analyze-runs) — lấy bảng so sánh và đọc kết quả.
- [Training metrics](https://cloud.google.com/vertex-ai/docs/general/monitoring-metrics) — theo dõi custom training/compute.
- [Vertex AI access control](https://cloud.google.com/vertex-ai/docs/general/access-control) — IAM và quyền training jobs.
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) — đơn giá training/experiments/tài nguyên liên quan theo thời điểm.

**Kết luận:** hyperparameter tuning tự động hóa việc thử nhiều cấu hình nhưng **không thay thế phương pháp đánh giá ML**. Cần khai báo đúng search space, validation metric, trial budget và báo metric cho optimizer; đồng thời dùng **Vertex AI Experiments** để lưu tham số, metric, dataset/code version và artifacts. Chỉ đưa mô hình vào vận hành sau khi **test holdout, kiểm tra chất lượng theo nhóm, độ trễ, quyền dữ liệu và chi phí** đều đáp ứng yêu cầu.
