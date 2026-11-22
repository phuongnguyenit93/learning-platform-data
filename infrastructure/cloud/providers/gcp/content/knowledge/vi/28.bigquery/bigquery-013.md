# BigQuery ML và suy luận gần dữ liệu trên Google Cloud

> **Chương:** BigQuery  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

**BigQuery ML (BQML)** cho phép tạo, đánh giá, dự đoán và giải thích nhiều loại mô hình máy học bằng **GoogleSQL ngay trong BigQuery**. Kỹ sư dữ liệu không cần xuất hàng triệu rows sang máy tính cục bộ chỉ để chạy một workflow phân loại hoặc dự báo. Mô hình được lưu dưới dạng resource trong BigQuery dataset; inference có thể tham gia trực tiếp vào câu truy vấn, pipeline SQL hoặc scheduled job.

Bài học thực hành xây dựng mô hình **dự đoán khách hàng có nguy cơ ngừng sử dụng (churn)** từ dữ liệu tổng hợp, dùng **LOGISTIC_REG, ML.EVALUATE, ML.PREDICT và ML.EXPLAIN_PREDICT**. Sau đó ta khảo sát **remote models** kết nối dịch vụ AI như Vertex AI/Gemini để phân biệt “suy luận gần dữ liệu” với việc xử lý thật sự bên ngoài BigQuery. **Không có dữ liệu khách hàng thật** được sử dụng trong ví dụ.

**Cảnh báo chi phí:** BigQuery query, model training, remote inference, storage và nền tảng AI liên quan có thể phát sinh phí. Chỉ chạy trong project lab được phép, kiểm tra dự toán và giới hạn chi phí trước khi thực thi. Các lệnh thay đổi tài nguyên được đánh dấu rõ; không chạy trên dữ liệu production.

## Mục tiêu học tập

1. Phân biệt BigQuery ML local model, remote model, feature engineering, training, evaluation và inference.
2. Chọn loại mô hình theo bài toán: regression, classification, clustering, forecasting hoặc generative AI.
3. Viết GoogleSQL tạo tập dữ liệu tổng hợp và tách train/evaluation/holdout không rò rỉ nhãn.
4. Tạo mô hình LOGISTIC_REG bằng CREATE MODEL, đánh giá ML.EVALUATE và quan sát confusion matrix.
5. Dùng ML.PREDICT để ghi điểm theo lô, hiểu predicted label và xác suất.
6. Sử dụng ML.EXPLAIN_PREDICT / ML.WEIGHTS một cách đúng phạm vi.
7. Hiểu BigQuery connection và remote inference tới Vertex AI, kể cả các chi phí/đường truyền dữ liệu.
8. Thiết kế lịch chạy, model version, drift monitoring, IAM và kế hoạch rollback theo yêu cầu thực tế.

## 1. “Suy luận gần dữ liệu” nghĩa là gì?

Hệ thống dữ liệu thường có nhiều bước: sự kiện ứng dụng được đưa vào BigQuery, SQL làm sạch thành features, mô hình tạo predictions, rồi hệ thống nghiệp vụ tiêu thụ kết quả.

~~~mermaid
flowchart LR
    SRC["Cloud Run / GKE / ứng dụng"] --> INGEST["Batch / streaming ingestion"]
    INGEST --> TABLE["BigQuery feature tables"]
    TABLE --> TRAIN["CREATE MODEL\nBigQuery ML"]
    TRAIN --> MODEL["BigQuery model resource"]
    TABLE --> SCORE["ML.PREDICT / ML.EVALUATE"]
    MODEL --> SCORE
    SCORE --> OUT["Prediction table"]
    OUT --> JOB["Scheduled query / dashboard / API service"]
    TABLE --> REMOTE["Remote model qua BigQuery connection"]
    REMOTE --> VAI["Vertex AI / Gemini endpoint"]
    VAI --> REMOTE
~~~

Với **mô hình BQML được hỗ trợ chạy trong BigQuery**, dữ liệu features và SQL workflow nằm trong cùng nền tảng phân tích, giảm nhu cầu xuất tệp sang một training script bên ngoài. Tuy nhiên, **“gần dữ liệu” không mặc định có nghĩa mọi tính toán đều ở cùng máy, cùng khu vực mạng hoặc không phát sinh egress**. Với **remote model**, BigQuery **gửi yêu cầu cùng dữ liệu đầu vào được chọn tới dịch vụ AI** và nhận kết quả, nên phải xem IAM, residency, data governance và chi phí riêng.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| BigQuery dataset | Không gian chứa bảng/mô hình cùng vị trí dữ liệu | bqml_lab |
| Training table/query | Features và label dùng học | churn_features |
| Local BQML model | Resource với thuật toán/weights được quản lý | churn_logreg_v1 |
| ML.EVALUATE | Đo chất lượng bằng metrics | precision, recall, ROC AUC |
| ML.PREDICT | Chạy scoring trên dữ liệu mới | churn score của từng customer |
| ML.EXPLAIN_PREDICT | Feature attributions cho dự đoán | Vì sao một sample có score cao |
| Remote model | Đại diện một endpoint AI qua connection | gemini_remote |
| Prediction table | Kết quả để batch jobs sử dụng | churn_scores_yyyymmdd |

### 1.1. Chọn loại mô hình

| Bài toán | Loại BQML ví dụ | Đầu ra |
|---|---|---|
| Dự đoán doanh thu theo features | LINEAR_REG, BOOSTED_TREE_REGRESSOR | Một giá trị số |
| Khách hàng có churn hay không? | LOGISTIC_REG, BOOSTED_TREE_CLASSIFIER | Nhãn + xác suất |
| Phân cụm nhóm người dùng | KMEANS | cluster/centroid |
| Dự báo chuỗi thời gian | ARIMA_PLUS, ARIMA_PLUS_XREG | forecast và khoảng tin cậy |
| Phát hiện bất thường | Một số mô hình qua ML.DETECT_ANOMALIES | Mức độ bất thường |
| Sinh tóm tắt văn bản | Remote model + AI.GENERATE_TEXT | Nội dung do LLM sinh |
| Embedding / vector search | Supported embedding model/function | Vector cho tìm kiếm tương đồng |

Loại mô hình quyết định cú pháp và các hàm có thể dùng. **ML.FEATURE_IMPORTANCE** áp dụng cho tree-based models, **ML.WEIGHTS** hữu ích với tuyến tính/logistic; không tráo chúng cho mọi loại mô hình. Sự hỗ trợ tùy dịch vụ, location, edition và feature availability. Tham khảo: https://docs.cloud.google.com/bigquery/docs/bqml-introduction

### 1.2. BigQuery ML khác một dịch vụ serving real-time

Một truy vấn **ML.PREDICT** rất phù hợp để scoring theo lô, liên kết với SQL và lưu kết quả trong bảng. Nó không tự là một **low-latency API endpoint** cho mỗi HTTP request của ứng dụng. Khi cần latency ở mức mili giây, autoscale và SLO online rõ ràng, nên đánh giá **Vertex AI endpoint**, mô hình xuất/đăng ký được hỗ trợ, feature serving hoặc một kiến trúc online chuyên biệt.

## 2. Chuẩn bị project, dataset, quyền và chi phí

### 2.1. Kiểm tra môi trường (chỉ đọc)

Người học dùng **Google Cloud Console → BigQuery Studio**, hoặc **Cloud Shell** với bq/gcloud CLI. Các SQL dưới đây chạy trong editor với dialect **GoogleSQL**. Chọn project lab đã bật billing/quota và location phù hợp chính sách dữ liệu.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
BQ_LOCATION="US"
DATASET="bqml_lab"

# CHỈ ĐỌC.
gcloud auth list
gcloud config list project
gcloud projects describe "$PROJECT_ID"
gcloud services list --enabled --project="$PROJECT_ID"
bq --project_id="$PROJECT_ID" ls
~~~

**Địa điểm dữ liệu:** chọn location có hỗ trợ BigQuery ML, đồng nhất dataset/model/query jobs. Các ví dụ dùng **US multi-region** cho tiện; không sao chép lựa chọn này vào workload bị ràng buộc lưu trữ tại Việt Nam hoặc một khu vực cụ thể. Dataset tại **EU** không được query kết hợp tùy ý với dataset ở **US**.

### 2.2. IAM theo vai trò tác nghiệp

| Principal | Nhiệm vụ | Quyền cần xem |
|---|---|---|
| Người tạo dataset | Quản lý dataset lab | BigQuery dataset create/admin theo phạm vi |
| Model author | Tạo model/train và tables | BigQuery Data Editor phù hợp dataset; jobs.create trên project |
| Analyst | Đọc dữ liệu, đánh giá/predict | Dataset/table/model read/getData và quyền tạo job |
| Scheduled job identity | Ghi scoring table mỗi ngày | Quyền jobs.create, read features/model, write output |
| Remote connection SA | Gọi Vertex AI endpoint | Vertex AI User / quyền endpoint theo API |
| Auditor/FinOps | Xem metadata và Billing | Quyền read-only phù hợp, không cần dữ liệu thô |

**Tránh cấp BigQuery Admin/Owner toàn project** cho người chỉ cần query. Với remote model, ngoài quyền của người chạy query, **service account do BigQuery connection quản lý** cần quyền trên nền tảng AI mục tiêu. Một mô hình đã được tạo không tự cấp quyền xem dữ liệu gốc cho mọi người dùng.

### 2.3. Tạo dataset riêng (thay đổi, có thể tính phí)

~~~bash
# THAY ĐỔI: chỉ trong project lab đã được phê duyệt.
bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" mk \
  --dataset "$PROJECT_ID:$DATASET"

# CHỈ ĐỌC xác minh dataset location.
bq --project_id="$PROJECT_ID" show "$PROJECT_ID:$DATASET"
~~~

Nếu dataset đã tồn tại, **không tạo lại** và không đổi quyền/retention của dataset chung. Các câu SQL tiếp theo giả định bạn đã **thay mọi PROJECT_ID** bằng giá trị project thật. Dấu backtick quanh tên fully-qualified table/model là cú pháp BigQuery cần giữ.

### 2.4. Chi phí trước khi train

- **CREATE MODEL** có chi phí training riêng tùy model type, edition và mô hình thanh toán.
- **SQL scans, ML.PREDICT, ML.EVALUATE**, tạo bảng và lưu output dùng tài nguyên BigQuery; một số tính năng được tính giá khác nhau.
- **Remote model** thường còn có phí request/token/endpoint của dịch vụ AI và có thể retry/batch.
- Bắt đầu bằng **3.000 records giả lập**, không chạy trên bảng customer production.
- Dùng **Query dry run** cho những câu query hỗ trợ dry run, **maximum bytes billed**, query plan và Cloud Billing budget alerts; **dry run không bảo đảm dự toán chính xác tiền training/remote AI**.
- Theo tài liệu hiện hành, **BigQuery ML không khả dụng trong BigQuery Standard edition**. Kiểm tra edition/reservation/entitlements và pricing trước khi chọn phương án.

## 3. Chọn dữ liệu và tránh rò rỉ tương lai

**Bài toán giả định:** tại ngày chụp dữ liệu (snapshot), dự đoán khách hàng có ngừng sử dụng trong **30 ngày kế tiếp**. Trong thực tế, **label chỉ biết sau 30 ngày**; tất cả features phải được tổng hợp từ dữ liệu có trước snapshot.

| Feature | Kiểu | Ví dụ | Rủi ro cần tránh |
|---|---|---|---|
| monthly_spend | INT64 | 79 | Phải lấy trước snapshot |
| tenure_months | INT64 | 18 | Không dùng tuổi thuê bao cập nhật sau khi churn |
| tickets_90d | INT64 | 4 | Chỉ tính tickets trước snapshot |
| days_since_login | INT64 | 12 | Không lén lấy thời điểm đăng nhập sau snapshot |
| plan | STRING | basic | Phân loại categorical |
| churned_next_30d | STRING: yes/no | yes | **Label**, không phải feature |
| customer_id | INT64 | 1001 | Định danh để join, **không dùng làm feature** |

Dataset demo sẽ tạo label bằng công thức có tương quan với features, nên kết quả chỉ minh họa quy trình. Nó **không đại diện** độ khó, phân bố, công bằng hay performance của dữ liệu churn thực tế.

### 3.1. Data leakage và các cách tách tập

- **Leakage:** đưa sự kiện chỉ biết sau snapshot vào features, hoặc tính aggregate trên cả giai đoạn test.
- **Random split:** phù hợp một số bài toán độc lập, nhưng có thể sai với dữ liệu có thời gian/khách hàng lặp lại.
- **Entity split:** cùng một customer không được nằm cả train và test nếu điều đó mô phỏng đúng điều kiện sử dụng.
- **Time split:** với forecasting/churn production, thường ưu tiên train ở các snapshot cũ, validation/test ở các snapshot mới hơn, có **label maturity gap**.
- **Holdout:** một tập chưa dùng để chọn features/hyperparameters/threshold; chỉ dùng đánh giá cuối.

**Lab:** chỉ có một record/customer, chia **80% development** (60% train, 20% validation) và **20% holdout** theo customer_id. Cách chia theo modulo là deterministic cho ví dụ, **không** phải khuyến nghị dùng cho time-series thật.

## 4. Lab A — Tạo dữ liệu churn giả lập bằng SQL

Tại **BigQuery Studio**, chọn đúng **PROJECT_ID**, location **US** theo ví dụ và chạy **GoogleSQL** sau. Mỗi người học chỉ tạo bảng trong dataset lab của mình.

### 4.1. Sinh bảng 3.000 khách hàng

~~~sql
-- THAY ĐỔI: ghi/ghi đè BẢNG LAB, không dùng tên bảng production.
CREATE OR REPLACE TABLE `PROJECT_ID.bqml_lab.churn_features`
OPTIONS (
  expiration_timestamp = TIMESTAMP_ADD(
      CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
) AS
WITH base AS (
  SELECT
    customer_id,
    30 + MOD(customer_id * 37, 160) AS monthly_spend,
    1 + MOD(customer_id * 17, 48) AS tenure_months,
    MOD(customer_id * 13, 6) AS tickets_90d,
    MOD(customer_id * 7, 45) AS days_since_login,
    ['basic', 'plus', 'team'][OFFSET(MOD(customer_id, 3))] AS plan,
    MOD(customer_id * 19, 29) / 29.0 AS noise
  FROM UNNEST(GENERATE_ARRAY(1, 3000)) AS customer_id
)
SELECT
  customer_id,
  monthly_spend,
  tenure_months,
  tickets_90d,
  days_since_login,
  plan,
  IF(
    0.70 * tickets_90d
    + 0.05 * days_since_login
    - 0.024 * tenure_months
    - 0.014 * monthly_spend
    + 0.90 * noise > 1.80,
    'yes',
    'no'
  ) AS churned_next_30d
FROM base;
~~~

**Vì sao dùng bảng thay vì chạy trực tiếp GENERATE_ARRAY mỗi lần?** Có một nguồn dữ liệu cố định để so sánh các lần train/evaluate và thuận tiện kiểm tra leakage. Bảng có **expiration 7 ngày**, giúp giảm khả năng quên dọn; model là một resource khác và phải xóa riêng nếu không còn dùng.

### 4.2. Kiểm tra kích thước, nhãn và phân bố

~~~sql
-- CHỈ ĐỌC.
SELECT
  COUNT(*) AS customers,
  COUNT(DISTINCT customer_id) AS unique_customers,
  COUNTIF(churned_next_30d = 'yes') AS positive_labels,
  COUNTIF(churned_next_30d = 'no') AS negative_labels,
  MIN(monthly_spend) AS min_spend,
  MAX(monthly_spend) AS max_spend
FROM `PROJECT_ID.bqml_lab.churn_features`;

-- Phân bố nhóm được giữ lại cho test/holdout.
SELECT
  CASE
    WHEN MOD(customer_id, 10) < 6 THEN 'TRAIN'
    WHEN MOD(customer_id, 10) < 8 THEN 'VALIDATION'
    ELSE 'HOLDOUT'
  END AS dataset_partition,
  COUNT(*) AS row_count,
  ROUND(AVG(IF(churned_next_30d = 'yes', 1, 0)), 3)
    AS churn_rate
FROM `PROJECT_ID.bqml_lab.churn_features`
GROUP BY 1
ORDER BY 1;
~~~

Kỳ vọng bảng có **3.000 customers**, không có customer_id trùng; mỗi partition có cả hai nhãn để mô hình học và được đánh giá. **Không gán trước một giá trị ROC AUC/accuracy cụ thể**: muốn biết kết quả cần chạy truy vấn thật.

### 4.3. Khóa dữ liệu theo snapshot trong production

Với dữ liệu thật, thay công thức giả lập bằng pipeline có thể tái lập:

~~~text
feature_snapshot_time = 2026-10-01 00:00:00 UTC
features                = chỉ dữ liệu đã có trước snapshot
label_window            = 2026-10-01 đến 2026-10-31
label_matured_at        = sau khi cửa sổ 30 ngày kết thúc
entity_key              = customer_id
dataset_partition       = train/validation/holdout theo thời gian
~~~

**Không dùng các cột** như cancellation_date tương lai, refund sau churn hoặc customer support outcome sau snapshot làm features. Label có thể chứa tương lai để làm **ground truth**, nhưng không được đi vào đầu vào inference.

## 5. Lab B — Train mô hình Logistic Regression

### 5.1. CREATE MODEL với custom split

BQML có thể chia dữ liệu **CUSTOM**. Với mô hình không chạy hyperparameter tuning, cột chia tập phải là **BOOL**: giá trị **FALSE = train**, **TRUE/NULL = evaluation**. Đây là điểm khác với một số model có hyperparameter tuning dùng nhãn **TRAIN/EVAL/TEST** dạng STRING. Ta dành 20% cuối làm **holdout ngoài CREATE MODEL**.

~~~sql
-- THAY ĐỔI: tạo hoặc ghi đè model trong dataset lab.
CREATE OR REPLACE MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['churned_next_30d'],
  data_split_method = 'CUSTOM',
  data_split_col = 'is_eval',
  max_iterations = 30
) AS
SELECT
  monthly_spend,
  tenure_months,
  tickets_90d,
  days_since_login,
  plan,
  churned_next_30d,
  MOD(customer_id, 10) IN (6, 7) AS is_eval
FROM `PROJECT_ID.bqml_lab.churn_features`
WHERE MOD(customer_id, 10) < 8;
~~~

**Ý nghĩa từng phần:**

- **model_type='LOGISTIC_REG'**: phân loại nhãn **yes/no**.
- **input_label_cols**: chỉ rõ nhãn mục tiêu, tránh dùng default **label** sai cột.
- **data_split_method='CUSTOM' / is_eval**: 6/10 rows làm train, 2/10 làm validation.
- **WHERE MOD(customer_id,10)<8**: giữ 2/10 rows ngoài huấn luyện; đây là **holdout** thật.
- **customer_id không xuất hiện trong SELECT đầu vào mô hình** nên không bị dùng làm feature.
- **plan** là feature dạng STRING; BQML có thể mã hóa categorical features tự động theo model type.
- **max_iterations** chặn số lượt tối đa, không phải cam kết training phải dùng đủ 30 iterations.

**CREATE OR REPLACE MODEL** là thao tác thay model thật và có thể ảnh hưởng các jobs đang tham chiếu nó. Trong production, **không ghi đè model v1 đang phục vụ**; tạo v2 với tên mới, so sánh, đổi consumer và giữ rollback point.

### 5.2. Kiểm tra model và training history

~~~bash
# CHỈ ĐỌC metadata model, không phải BigQuery INFORMATION_SCHEMA.MODELS.
bq --project_id="$PROJECT_ID" show --model \
  "$PROJECT_ID:bqml_lab.churn_logreg_v1"
~~~

~~~sql
-- CHỈ ĐỌC iterations/loss/training status.
SELECT *
FROM ML.TRAINING_INFO(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`
)
ORDER BY iteration;
~~~

BigQuery hiện không hỗ trợ lấy model metadata từ một view **INFORMATION_SCHEMA.MODELS**; dùng **bq show --model**, BigQuery Studio → Model Details hoặc BigQuery models.get API. **ML.TRAINING_INFO** là hàm riêng để xem các vòng huấn luyện.

**Không dùng training loss để thay đo chất lượng dự đoán ngoài mẫu.** Loss giảm có thể đi cùng overfitting; phải kiểm tra evaluation/holdout, điều chỉnh features và threshold theo chi phí false positives/false negatives.

## 6. Lab C — Đánh giá chất lượng bằng dữ liệu chưa dùng huấn luyện

### 6.1. Metrics từ dữ liệu evaluation trong training

~~~sql
SELECT *
FROM ML.EVALUATE(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`
);
~~~

Với binary classification, kết quả có thể gồm **precision, recall, accuracy, f1_score, log_loss, roc_auc**. Ý nghĩa:

| Metric | Câu hỏi trả lời | Giới hạn |
|---|---|---|
| Accuracy | Tỷ lệ dự đoán đúng | Dễ gây hiểu nhầm nếu nhãn lệch |
| Precision | Trong số dự đoán churn, bao nhiêu thực sự churn? | Có thể tăng bằng threshold cao |
| Recall | Bao nhiêu churn thực sự được phát hiện? | Tăng recall có thể tăng false alarms |
| F1 score | Cân bằng precision và recall | Không phản ánh trực tiếp chi phí nghiệp vụ |
| ROC AUC | Phân biệt positives và negatives qua thresholds | Không kiểm tra probability calibration |
| Log loss | Chất lượng xác suất dự đoán | Nhạy với các dự đoán sai quá tự tin |

### 6.2. Đánh giá riêng trên holdout

**Quan trọng:** với ML.EVALUATE và ML.CONFUSION_MATRIX khi cung cấp query thủ công, input phải gồm **features và label thật**. Đây là tập **20% chưa vào CREATE MODEL**, nên là phép đánh giá ngoài mẫu có ý nghĩa hơn việc chỉ xem train metrics.

~~~sql
SELECT *
FROM ML.EVALUATE(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      monthly_spend,
      tenure_months,
      tickets_90d,
      days_since_login,
      plan,
      churned_next_30d
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
  )
);
~~~

Kết quả trên dữ liệu giả lập **không được trình bày là performance sản phẩm thật**. Một mô hình có ROC AUC cao trên synthetic labels có thể thất bại vì feature drift, seasonality, label noise và class imbalance khi ra đời thực.

### 6.3. Confusion matrix và threshold

~~~sql
-- Dự đoán nhãn theo threshold 0.35 để nghiên cứu trade-off.
SELECT *
FROM ML.CONFUSION_MATRIX(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      monthly_spend,
      tenure_months,
      tickets_90d,
      days_since_login,
      plan,
      churned_next_30d
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
  ),
  STRUCT(0.35 AS threshold)
);
~~~

Threshold thấp hơn **0.5** thường dự đoán positive nhiều hơn (tăng khả năng phát hiện churn nhưng cũng có thể tăng false positives). **Không chọn threshold bằng trực giác**: dùng validation set và dữ liệu chi phí nghiệp vụ để chọn, sau đó **chỉ dùng holdout để báo cáo cuối**. Nếu liên tục sửa threshold sau khi xem holdout, holdout đã trở thành tập tuning và không còn độc lập.

### 6.4. Các chỉ số theo nhiều thresholds

~~~sql
SELECT
  threshold,
  recall,
  true_positives,
  false_positives,
  true_negatives,
  false_negatives
FROM ML.ROC_CURVE(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      monthly_spend, tenure_months, tickets_90d,
      days_since_login, plan, churned_next_30d
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
  ),
  GENERATE_ARRAY(0.20, 0.80, 0.10)
)
ORDER BY threshold;
~~~

Đây là truy vấn **học về threshold**, không phải cách tuning production trên holdout. Trong production hãy tạo một **validation/threshold-selection dataset** tách riêng rồi đóng băng threshold trước khi chấm holdout.

## 7. Lab D — Dự đoán theo lô gần dữ liệu

### 7.1. ML.PREDICT trên tập holdout

**Không đưa nhãn churned_next_30d vào input dự đoán**; label chỉ phục vụ đánh giá sau khi sự kiện thật xảy ra. Khi chấm điểm, đầu vào cần các feature mà mô hình đã được huấn luyện. **customer_id** là cột pass-through để nối kết quả về ứng dụng, không phải feature đã dùng trong CREATE MODEL.

~~~sql
SELECT
  customer_id,
  predicted_churned_next_30d,
  predicted_churned_next_30d_probs
FROM ML.PREDICT(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      customer_id,
      monthly_spend,
      tenure_months,
      tickets_90d,
      days_since_login,
      plan
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
  )
)
LIMIT 10;
~~~

**ML.PREDICT** thêm hai cột cho phân loại nhị phân:

- **predicted_churned_next_30d:** nhãn mô hình chọn, ví dụ **yes** hoặc **no**.
- **predicted_churned_next_30d_probs:** mảng chứa từng **label** và **probability**. Không được giả định phần tử mảng đầu tiên luôn là lớp positive.

### 7.2. Tách xác suất lớp “yes” một cách rõ ràng

~~~sql
WITH scored AS (
  SELECT
    customer_id,
    predicted_churned_next_30d,
    predicted_churned_next_30d_probs
  FROM ML.PREDICT(
    MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
    (
      SELECT
        customer_id,
        monthly_spend,
        tenure_months,
        tickets_90d,
        days_since_login,
        plan
      FROM `PROJECT_ID.bqml_lab.churn_features`
      WHERE MOD(customer_id, 10) >= 8
    )
  )
)
SELECT
  customer_id,
  predicted_churned_next_30d,
  (SELECT probability
   FROM UNNEST(predicted_churned_next_30d_probs)
   WHERE label = 'yes') AS churn_probability
FROM scored
ORDER BY churn_probability DESC
LIMIT 20;
~~~

Giá trị **churn_probability** thuộc khoảng [0,1] theo phân loại của mô hình, **không mặc nhiên là xác suất đã được hiệu chỉnh (calibrated)**. Với quyết định có chi phí lớn như khóa tài khoản hoặc ưu đãi tiền, cần đánh giá calibration, bias và người phê duyệt chính sách.

### 7.3. Ghi kết quả scoring ra bảng BigQuery

Một job theo lô có thể ghi kết quả để ứng dụng/backend hoặc dashboard truy cập **không phải chạy ML.PREDICT mỗi request**:

~~~sql
-- THAY ĐỔI: chỉ ghi đè BẢNG LAB, expiration sau 7 ngày.
CREATE OR REPLACE TABLE `PROJECT_ID.bqml_lab.churn_scores_lab`
OPTIONS (
  expiration_timestamp = TIMESTAMP_ADD(
      CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
) AS
WITH scored AS (
  SELECT
    customer_id,
    predicted_churned_next_30d,
    predicted_churned_next_30d_probs
  FROM ML.PREDICT(
    MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
    (
      SELECT
        customer_id, monthly_spend, tenure_months,
        tickets_90d, days_since_login, plan
      FROM `PROJECT_ID.bqml_lab.churn_features`
      WHERE MOD(customer_id, 10) >= 8
    )
  )
)
SELECT
  customer_id,
  predicted_churned_next_30d,
  (SELECT probability
   FROM UNNEST(predicted_churned_next_30d_probs)
   WHERE label = 'yes') AS churn_probability,
  'churn_logreg_v1' AS model_version,
  CURRENT_TIMESTAMP() AS scored_at
FROM scored;
~~~

**Khi dùng production:** không ghi đè bảng lịch sử một cách mù quáng. Tổ chức thường dùng **partition by scoring date**, stable job ID và **MERGE**/insert có khóa (model_version, snapshot_date, customer_id) để hỗ trợ rerun, đối soát và rollback. Đặt **retention/expiration** theo hợp đồng dữ liệu thật.

## 8. Giải thích mô hình và feature engineering

### 8.1. Giải thích một vài prediction

~~~sql
SELECT
  customer_id,
  predicted_churned_next_30d,
  top_feature_attributions
FROM ML.EXPLAIN_PREDICT(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      customer_id,
      monthly_spend,
      tenure_months,
      tickets_90d,
      days_since_login,
      plan
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
    LIMIT 10
  ),
  STRUCT(3 AS top_k_features)
);
~~~

**top_feature_attributions** cho biết mức đóng góp của từng feature vào dự đoán theo phương pháp giải thích được hỗ trợ; **không chứng minh quan hệ nhân quả**. Feature có attribution lớn không có nghĩa can thiệp trực tiếp vào feature đó sẽ làm khách hàng ở lại.

### 8.2. Quan sát hệ số mô hình logistic

~~~sql
SELECT *
FROM ML.WEIGHTS(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`
);
~~~

**ML.WEIGHTS** hiển thị hệ số cho mô hình tuyến tính/logistic và thông tin categorical weight tùy schema; hệ số chưa chuẩn hóa không thể so độ quan trọng giữa các feature có thang đo rất khác nhau chỉ bằng trị tuyệt đối. Dùng chuẩn hóa khi so sánh phù hợp hoặc ML.EXPLAIN_PREDICT trên các mẫu cụ thể.

**Không dùng ML.FEATURE_IMPORTANCE cho LOGISTIC_REG:** hàm đó phục vụ boosted trees/random forests. Nếu thay model_type, phải kiểm tra lại hàm giải thích, huấn luyện, chi phí và phép đánh giá tương ứng.

### 8.3. Preprocessing khi train và predict

BigQuery ML hỗ trợ một số **automatic preprocessing** theo model type như biến đổi categorical và xử lý missing values; đồng thời có thể khai báo **TRANSFORM clause** để đóng gói feature transformations trong model, giúp tránh training-serving skew. Tài liệu: https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create

**Quy tắc:**

1. Định nghĩa feature logic một lần, version hóa SQL/migration/metadata.
2. Không chuẩn hóa dựa trên cả holdout/test trước khi train (leakage).
3. Không để query inference đổi nghĩa các cột như **monthly_spend** hay **days_since_login**.
4. Xử lý NULL, unknown categories, outliers và timestamp boundaries có chủ đích.
5. Nếu dùng TRANSFORM, kiểm tra input names được yêu cầu lúc **ML.PREDICT**; không tự đưa đã-transform features lần thứ hai.
6. Đánh giá model fairness/drift trên các nhóm khách hàng được phép sử dụng, không suy ra phân nhóm nhạy cảm nếu không có yêu cầu và cơ sở pháp lý.

### 8.4. Khi bài toán không phải classification

- **LINEAR_REG:** dự đoán một biến số liên tục, đánh giá MAE/RMSE/R² thay vì precision/recall.
- **KMEANS:** không có label, quan sát centroid và khoảng cách; không dùng confusion matrix churn.
- **ARIMA_PLUS:** dữ liệu thời gian được xây theo series/đơn vị đo, dùng ML.FORECAST; tránh split ngẫu nhiên xuyên tương lai.
- **BOOSTED_TREE_CLASSIFIER:** có thể mô hình hóa phi tuyến tốt hơn nhưng chi phí/giải thích/khả năng khái quát phải được so sánh.
- **AUTO_CLASS_WEIGHTS:** giúp xử lý mất cân bằng nhãn với logistic regression; không thay việc định nghĩa chi phí false positive/false negative.

Không chọn thuật toán theo quảng cáo độ chính xác. Bắt đầu bằng **baseline đơn giản**, xác minh SLO và cost rồi mới thử mô hình phức tạp.

## 9. Remote inference: BigQuery kết nối Vertex AI/Gemini

Mô hình BQML dạng **remote** là một resource trong BigQuery đại diện cho dịch vụ/mô hình nằm **ngoài BigQuery**. Nó không có nghĩa BigQuery đã tải toàn bộ model weights vào warehouse. BQML có thể gửi selected input rows tới endpoint được cấp quyền, rồi nhận dự đoán hoặc nội dung được sinh.

~~~mermaid
sequenceDiagram
    participant Q as BigQuery SQL job
    participant R as BigQuery remote model
    participant C as BigQuery connection SA
    participant V as Vertex AI / Gemini service
    Q->>R: AI.GENERATE_TEXT(model, prompts)
    R->>C: Yêu cầu xác thực/ủy quyền
    C->>V: Requests chứa prompt data
    V-->>R: Responses / errors / usage
    R-->>Q: Table-valued results
    Note over Q,V: Có quota, pricing và data governance riêng
~~~

### 9.1. Các điều kiện cần có

- Dataset và BigQuery **Cloud resource connection** phải cùng location hợp lệ theo tài liệu.
- **Connection service account** cần quyền thích hợp trên Vertex AI/endpoint (ví dụ Agent Platform/Vertex AI User theo loại model).
- API/service, endpoints và model version phải được hỗ trợ ở location được chọn.
- Dữ liệu được truyền tới endpoint AI; **không gửi PII, secrets, raw customer messages** nếu chưa có chính sách và cơ sở pháp lý.
- Có thể phát sinh **BigQuery query charges + remote model token/endpoint charges + retry/capacity costs**.
- Đối với model thế hệ mới, Google khuyến nghị **AI.GENERATE_TEXT** thay cho ML.GENERATE_TEXT trong truy vấn mới vì tên các cột kết quả đơn giản hơn.

### 9.2. Tạo remote model — tùy chọn, chỉ trong project lab được duyệt

Đây là **ví dụ mẫu**, không chạy nguyên văn. Trước tiên, quản trị viên phải tạo connection đúng loại, cấp IAM cho connection service account và xác minh model endpoint khả dụng. Thay **PROJECT_ID, us, bqml_ai_connection, MODEL_ID_DUOC_HO_TRO** bằng các giá trị được phép dùng.

~~~sql
-- THAY ĐỔI: tạo remote model và gắn endpoint dịch vụ AI có phí.
CREATE OR REPLACE MODEL `PROJECT_ID.bqml_lab.text_remote_lab`
REMOTE WITH CONNECTION `PROJECT_ID.us.bqml_ai_connection`
OPTIONS (
  ENDPOINT = 'MODEL_ID_DUOC_HO_TRO'
);
~~~

Tham khảo danh sách endpoint/model được hỗ trợ tại [remote models over LLMs](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-remote-model). **Không chọn một model ID chỉ vì nó đã xuất hiện trong bài cũ**; version và location support có thể thay đổi.

### 9.3. AI.GENERATE_TEXT trên dữ liệu thử nghiệm

~~~sql
-- Có thể tạo requests tính phí tới AI service.
-- Đổi MODEL ở trên thành remote model đã tạo thành công.
SELECT *
FROM AI.GENERATE_TEXT(
  MODEL `PROJECT_ID.bqml_lab.text_remote_lab`,
  (
    SELECT 101 AS review_id,
      'Tóm tắt trong một câu: Sản phẩm giao đúng hẹn và đóng gói tốt.'
        AS prompt
    UNION ALL
    SELECT 102 AS review_id,
      'Tóm tắt trong một câu: Hệ thống hỗ trợ phản hồi chậm.'
        AS prompt
  ),
  STRUCT(128 AS max_output_tokens, 0.2 AS temperature)
);
~~~

**Không coi output từ LLM là sự thật đã được kiểm chứng.** Kiểm tra các cột kết quả và trạng thái/thông báo lỗi của từng row theo schema phiên bản function, xử lý responses rỗng, safety blocks, rate limits và retries. Với hàng triệu rows, nên **lọc, LIMIT và ghi prompt subset ra bảng nhỏ trước khi gọi** để tránh vô tình gửi hàng triệu requests có phí.

### 9.4. Remote model khác native BQML ở đâu?

| Chiều so sánh | Local BigQuery ML | Remote model qua connection |
|---|---|---|
| Model weights/compute | Do BigQuery ML quản lý theo loại model | Endpoint AI bên ngoài BigQuery |
| Input | BigQuery table/query | BigQuery query → remote service |
| Auth | BigQuery roles cho model/data/job | Thêm connection SA + AI endpoint IAM |
| Location | BigQuery model/dataset | Thêm endpoint/residency/location support |
| Billing | BigQuery ML/model/query/storage | BigQuery + dịch vụ endpoint/token/compute |
| Kết quả | Predict label/numbers/metrics | Output schema của remote model/AI function |
| SLO | Theo query/warehouse | Còn phụ thuộc remote endpoint quota/latency |
| Privacy | Tuân quyền truy cập BigQuery | Cần đánh giá rõ dữ liệu gửi đến AI service |

## 10. Đưa BQML vào pipeline định kỳ có thể kiểm soát

Một mô hình vừa train xong không tự trở thành tính năng production. Cần tách **training pipeline** khỏi **scoring pipeline** và quản lý chúng như các phiên bản phần mềm.

~~~mermaid
flowchart TD
    A["Nguồn sự kiện đã kiểm định"] --> F["Feature snapshots\npartition theo ngày"]
    F --> T["Training job định kỳ\nmodel vN"]
    T --> E["Evaluation + approval gate"]
    E -->|"PASS"| M["Model registry / approved version"]
    M --> S["Scheduled scoring job"]
    F --> S
    S --> O["Partitioned predictions table"]
    O --> D["Dashboard / downstream activation"]
    O --> MON["Monitoring: data drift + label metrics"]
    MON -. "Cần retrain" .-> T
    E -->|"FAIL"| HOLD["Giữ model đang phục vụ"]
~~~

### 10.1. Tách ba loại dữ liệu

| Tập dữ liệu | Chức năng | Quy tắc |
|---|---|---|
| **Feature snapshot** | Trạng thái khách hàng tại thời điểm được phép | Không cập nhật lại snapshot đã chốt nếu muốn tái lập |
| **Training/evaluation** | Tạo và chọn model/threshold | Không chạm holdout cho từng vòng tuning |
| **Scoring snapshot** | Features của khách hàng hiện tại | Không bao gồm label tương lai; schema giống training |
| **Ground truth sau 30 ngày** | Đánh giá real-world accuracy | Join bằng customer_id + snapshot_date, xử lý late-arriving data |
| **Prediction table** | Đầu ra cho BI/ứng dụng | Gắn model version, scoring time, feature snapshot ID |

### 10.2. Quy trình phát hành model

1. **Data quality gate:** số rows, null rate, label maturity, phát hiện dữ liệu ngoài phạm vi, kiểm tra PII.
2. **Train:** tạo **churn_logreg_v2**, không ghi đè **v1** đang được job downstream dùng.
3. **Evaluate:** so sánh ROC AUC/precision/recall trên validation, calibration và chi phí hành động.
4. **Holdout:** chỉ chạy sau khi khóa features và threshold, ghi biên bản.
5. **Approve:** có model owner, data owner, revision SQL, schema version và người phê duyệt.
6. **Canary:** chỉ dùng v2 cho một nhóm batch nhỏ, đối chiếu model scores và outcome.
7. **Promote:** scheduled query trỏ sang model version v2; giữ v1 và output lịch sử để rollback.
8. **Observe:** giám sát input drift, prediction distribution, lỗi, query time và cost.
9. **Rollback:** đổi model reference của scoring job về v1, không xóa dữ liệu đã công bố khi chưa có cách đối soát.

Có thể dùng **BigQuery scheduled queries**, **Dataform**, **Cloud Composer/Workflows** hoặc một CI/CD pipeline để tự động hóa tùy mức phức tạp. Ghi lại code SQL trong Git; không quản lý production chỉ bằng cách sửa thủ công một câu query trong console mà không có change history.

### 10.3. Dùng scheduled query an toàn

Khi tạo một scheduled query ghi điểm hàng ngày:

- Chọn **service account riêng** có quyền đọc features/model và ghi bảng điểm trong dataset đích.
- Đặt **location** trùng dataset/model, lịch chạy sau khi snapshot features hoàn thành.
- Dùng **partition/snapshot date** ổn định thay vì gọi CURRENT_DATE tràn lan trong nhiều bước.
- Ghi **model_version, run_id, feature_snapshot_date, scored_at** để truy vết.
- Chống task lặp bằng **MERGE** theo khóa hoặc write disposition đã được duyệt.
- Đặt cảnh báo **job failed, số hàng lệch bất thường, NULL tăng, latency và chi phí**.
- **Không chạy một scheduled query dùng CREATE OR REPLACE MODEL v1** nếu v1 đang phục vụ nhiều consumers.

### 10.4. Thao tác batch hay online?

| Yêu cầu | Hướng triển khai |
|---|---|
| Phân loại 1 triệu khách hàng mỗi đêm | Scheduled BigQuery ML.PREDICT vào bảng partitioned |
| Dashboard churn hàng ngày | BigQuery table → Looker/BI |
| API chỉ đọc score đã tính | Cloud Run service đọc bảng/serving store theo SLO |
| Suy luận khi người dùng bấm nút, cần trả rất nhanh | Serving endpoint chuyên biệt/Vertex AI, cache và performance test |
| Dự báo 30 ngày với dữ liệu streaming vừa đến | Cân nhắc feature freshness, microbatch, online features và SLA |

**Không query BigQuery để thực hiện mỗi quyết định đồng bộ trong HTTP request** trừ khi đã đo rõ latency, quota và cost, và chấp nhận giới hạn đó.

## 11. Giám sát chất lượng mô hình sau triển khai

### 11.1. Một dashboard cần có gì?

| Nhóm | Chỉ số | Tại sao quan trọng |
|---|---|---|
| **Data quality** | row count, missing/null ratio, schema changes | Dữ liệu hỏng tạo scores vô nghĩa |
| **Feature drift** | phân bố spend, tickets, plan, days_since_login | Mô hình có thể không còn đúng với nhóm khách hàng mới |
| **Prediction drift** | % predicted yes, score histogram | Phát hiện thay đổi output bất thường |
| **Ground-truth quality** | label availability, late-arriving labels | Không đánh giá được nếu nhãn chưa trưởng thành |
| **Model accuracy** | precision, recall, ROC AUC theo cohort/time | Đảm bảo không suy giảm ngoài mẫu |
| **Fairness/impact** | metric theo nhóm phù hợp đã được phép đo | Tránh bất lợi không được kiểm soát |
| **Query reliability** | jobs failed, duration, bytes scanned, slot usage | Bảo đảm batch hoàn thành đúng hạn |
| **Remote inference** | output status, rate limit, token usage, latency | Tránh chi phí và thất bại âm thầm |
| **Cost** | BigQuery ML training/inference, storage, Vertex AI | Dự toán và tối ưu |

### 11.2. Drift không phải chỉ là accuracy

**Feature drift** là input distribution thay đổi (ví dụ khách hàng mới chủ yếu chọn plan team), còn **concept drift** là quan hệ giữa features và churn thay đổi (ví dụ một đợt khuyến mại làm hành vi nghỉ dùng khác trước). Một mô hình có thể chạy thành công 100% nhưng quyết định kém vì drift.

Vì nhãn **churned_next_30d** chỉ trưởng thành sau 30 ngày, không thể dùng accuracy “thời gian thực” ngay sau khi scoring. Trong thời gian chờ nhãn, theo dõi drift, invalid rows, prediction distribution và phản hồi người dùng; khi label xuất hiện mới chấm model quality.

### 11.3. Kiểm tra jobs và tài nguyên đã chạy

~~~sql
-- CHỈ ĐỌC BigQuery job metadata; cần quyền INFORMATION_SCHEMA phù hợp.
-- Dataset/model đang ở US multi-region; region qualifier phải khớp.
SELECT
  creation_time,
  job_id,
  user_email,
  statement_type,
  total_bytes_processed,
  total_slot_ms
FROM `PROJECT_ID.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 100;
~~~

**Đọc đúng giới hạn:** số **bytes processed** và **slot-ms** giúp phân tích công việc, nhưng **không trực tiếp là số tiền bị tính** cho mọi model type/billing model. Đối chiếu với **Cloud Billing**/Pricing SKUs và thông tin reservation; remote model charges có thể xuất hiện ở dịch vụ AI riêng.

### 11.4. Kiểm tra an toàn trước mỗi đợt retrain

- Bảng snapshot có schema đúng và được phân quyền.
- Label được tạo từ cửa sổ thời gian đầy đủ và không bị future leakage.
- Train/validation/test không bị đan cùng customer/time theo cách sai.
- Không bỏ sót cohort hiếm hoặc nhóm quan trọng về nghiệp vụ.
- Thử baseline: nếu phiên bản mới không cải thiện, giữ phiên bản cũ.
- Giữ version SQL/data/model và tiêu chí rollback có thể truy vết.
- Có kế hoạch kiểm soát false positives gây chi phí ưu đãi và false negatives bỏ lỡ người dùng cần hỗ trợ.

## 12. Bảo mật và quản trị dữ liệu/AI

### 12.1. Bốn bề mặt phân quyền khác nhau

~~~mermaid
flowchart LR
    USER["Analyst / job SA"] -->|"BigQuery jobs.create"| JOB["BigQuery query job"]
    JOB -->|"Tables/model read"| BQ["BigQuery features + model"]
    JOB -->|"Connection use"| CONN["BigQuery connection service account"]
    CONN -->|"AI endpoint IAM"| AI["Vertex AI / Gemini"]
    BQ -->|"Output table IAM"| DOWN["Scores for approved consumers"]
~~~

- **BigQuery job permission:** cho phép tạo job, không tự cấp quyền đọc mọi bảng.
- **Dataset/model data permissions:** truy vấn cần đọc bảng/mô hình; training cần tạo model đúng phạm vi.
- **Connection permission:** dùng remote model phải có quyền trên connection theo chính sách; connection service account mới là principal gọi AI.
- **Endpoint IAM:** connection SA cần được ủy quyền phù hợp trên Vertex AI/remote endpoint; không sử dụng end-user personal credentials để che cấu hình thiếu.
- **Output privacy:** predictions có thể trở thành dữ liệu cá nhân/suy luận nhạy cảm dù features gốc không chứa PII trực tiếp. Chỉ publish cho consumer có cơ sở nghiệp vụ hợp lệ.

### 12.2. Đường đi của dữ liệu và residency

Một SQL job trên BigQuery dataset **US** không đảm bảo mọi remote inference diễn ra nội bộ cùng dataset hoặc quốc gia. Với remote model, phải xác nhận:

1. Location của dataset, BigQuery connection và model endpoint.
2. Chính sách xử lý prompt/input của nhà cung cấp model.
3. Loại dữ liệu gửi (chỉ fields cần thiết, data minimization).
4. Retention/logging của cả BigQuery và AI service.
5. CMEK, VPC Service Controls, organization policies và khả năng tương thích nếu có yêu cầu.
6. Hợp đồng và quy định bảo vệ dữ liệu áp dụng.

**Không đưa access token, database password, full customer transcript hoặc thẻ thanh toán vào prompt** chỉ vì AI.GENERATE_TEXT trả về kết quả thuận tiện.

### 12.3. ML governance và trách nhiệm con người

Không tự động khóa tài khoản, từ chối dịch vụ, tính giá khác hoặc đưa ra quyết định nhạy cảm chỉ từ **churn_probability** của mô hình ví dụ. Mô hình phục vụ **hỗ trợ ra quyết định**, cần đánh giá chất lượng, fairness, risk controls và đường khiếu nại nếu triển khai trong nghiệp vụ tác động tới khách hàng.

## 13. Chi phí, quota và chiến lược tối ưu

| Nguồn chi phí | Điều kiện phát sinh | Cách kiểm soát |
|---|---|---|
| BigQuery training | CREATE MODEL, hyperparameter tuning | Giới hạn input, chọn model đơn giản, lịch retrain |
| BigQuery analysis/inference | SELECT, ML.EVALUATE/PREDICT, CTAS | Partition pruning, filter rows, chỉ chọn columns |
| Storage | Feature/scores tables, model storage, snapshots | Expiration và retention theo nhu cầu |
| Remote AI | Model requests, input/output tokens, serving compute | Lọc dữ liệu, pre-aggregate, quota/token budgets |
| Query orchestration | Scheduled queries, retry attempts | Error notifications, run ID, tránh rerun trùng |
| Monitoring | Log/metrics retention | Sampling, không log PII/prompt lớn |
| Data movement | Cross-region query/transfer/egress tùy cấu hình | Chọn location và topology hợp lý |

### 13.1. Ước lượng số request AI — không phải bảng giá

Giả sử có 100.000 rows feedback và remote model tạo một request cho mỗi row. Nếu không lọc, có thể phát sinh **100.000 inference requests**; retry một phần cũng có chi phí thêm. Nếu chỉ cần 1.000 feedback đại diện, hãy tạo **bảng sample 1.000 rows trước**, kiểm tra độ bao phủ, rồi mới gọi remote model.

Đối với churn scoring, một bảng partitioned theo ngày tránh scan lại nhiều năm features khi chỉ cần snapshot hiện tại. **BigQuery dry run không đủ để biết toàn bộ phí training hoặc remote inference**; luôn tham khảo [BigQuery pricing](https://cloud.google.com/bigquery/pricing), [BigQuery ML pricing](https://cloud.google.com/bigquery/pricing#bqml) và [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing).

### 13.2. On-demand và capacity pricing

BigQuery có mô hình tính phí on-demand/capacity tùy tổ chức. **Slots/edition/reservation** ảnh hưởng khả năng chạy ML jobs, không phải một “free inference endpoint”. Với dataset lớn hoặc nhiều scheduled queries, cần đo **time-to-result, slot consumption, wall time và cost per successfully scored row** trên môi trường thật.

**Cảnh báo vận hành:** một model phức tạp có metrics tốt hơn đôi chút nhưng tốn nhiều lần training hoặc scoring có thể không đáng dùng. Đặt mục tiêu tổng chi phí kinh doanh, không chỉ ROC AUC.

## 14. Troubleshooting: xác định đúng tầng lỗi

| Triệu chứng | Nguyên nhân thường gặp | Bước xử lý |
|---|---|---|
| **Access Denied** khi chạy SELECT | Thiếu quyền đọc dataset/table | Xác định job principal, dataset IAM |
| **Permission denied / models.create** | Thiếu quyền tạo model trong dataset | Cấp model/data editor đúng phạm vi |
| **Location mismatch** | Dataset, model, connection hoặc job khác location | Kiểm tra US/EU/region và query settings |
| **CREATE MODEL lỗi label** | INPUT_LABEL_COLS sai tên/type, chỉ có một lớp | Kiểm tra schema và phân bố nhãn |
| **CUSTOM split không hợp lệ** | Không tuning nhưng split column không phải BOOL | Đổi is_eval BOOL, không dùng TRAIN/EVAL STRING |
| **Model không tìm thấy** | Sai project/dataset/model hoặc model chưa tạo xong | INFORMATION_SCHEMA, model name |
| **ML.PREDICT thiếu feature** | Query inference thiếu cột hoặc sai kiểu dữ liệu | So sánh training input schema |
| **Dự đoán lệch dù query chạy** | Leakage, drift, khác nghĩa features, bias | Data contract, holdout, distribution monitor |
| **Accuracy cao bất thường** | Synthetic label/quá ít lớp hoặc leakage | Audit SQL trước/sau snapshot |
| **Cost tăng sau retrain** | Scan quá rộng, hyperparameter trials, reruns | Bytes, Billing SKU, schedule |
| **Remote model 403** | Connection SA thiếu quyền endpoint hoặc connection IAM | Connection resource + Vertex AI IAM |
| **Remote 429/RESOURCE_EXHAUSTED** | Quota/token/endpoint capacity | Rate limits, giảm batch size, backoff |
| **Remote output trống/lỗi từng row** | Safety block, invalid prompt, service/transient error | Đọc status fields, retry policy |
| **Remote model region unsupported** | Endpoint không hỗ trợ BigQuery dataset location | Chọn location/model theo docs |
| **Scheduled query không có dữ liệu mới** | Job chạy trước feature snapshot, hoặc SA thiếu quyền | Dependency scheduling, run_id và logs |

### 14.1. Trình tự điều tra

1. Kiểm tra project, dataset, **job location**, model name và SQL dialect GoogleSQL.
2. Phân biệt lỗi đọc bảng, quyền model, BigQuery job permission và **connection SA → AI endpoint IAM**.
3. Với schema lỗi: so sánh tên/kiểu feature tại training và inference; label chỉ cần có ở evaluation.
4. Với quality thấp: kiểm tra train/eval/holdout, time leakage, label maturity và distribution theo cohort.
5. Với chi phí cao: xem BigQuery Job Information, Billing SKUs, partition pruning, remote token counts và số lần retry.
6. Với model mới kém hơn model cũ: **rollback model reference** của scheduled query theo change record thay vì xóa dữ liệu đầu ra tức thì.
7. Không đưa raw PII, prompts chứa bí mật, access tokens hoặc SQL credentials vào support ticket.

### 14.2. Đọc thông tin model bằng CLI

~~~bash
# CHỈ ĐỌC; thay project/dataset/model thật, không in dữ liệu nhạy cảm.
bq --project_id="$PROJECT_ID" show \
  --model "$PROJECT_ID:bqml_lab.churn_logreg_v1"

bq --project_id="$PROJECT_ID" ls --models \
  "$PROJECT_ID:bqml_lab"
~~~

Nếu thao tác CLI thay đổi theo bản SDK, dùng **BigQuery Studio → dataset → Models → Model Details/Training** để đối chiếu resource và quyền. Model được tạo không đồng nghĩa đã sẵn sàng cho mọi consumer trước khi training job kết thúc.

## 15. Case study: chiến dịch giữ chân khách hàng

**Bối cảnh giả định:** ứng dụng Java trên Cloud Run lưu đơn hàng trong Cloud SQL, gửi events qua Pub/Sub, tổng hợp vào BigQuery. Đội sản phẩm muốn phân loại khách hàng có nguy cơ churn và gửi ưu đãi qua hệ thống marketing sau khi đã đồng ý nhận thông tin.

### 15.1. Thiết kế

~~~mermaid
flowchart LR
    APP["Cloud Run / Java"] --> EVT["Pub/Sub / ingest"]
    EVT --> WH["BigQuery feature snapshots"]
    WH --> BQML["BQML churn v1/v2"]
    BQML --> SCORES["Daily scores table"]
    SCORES --> RULES["Business eligibility + consent rules"]
    RULES --> ACT["Approved campaign system"]
    SCORES --> QA["Quality/drift dashboard"]
    QA -. "Retrain review" .-> BQML
~~~

**Chọn chính sách:**

- Features chỉ đến từ data trước snapshot; label phải đủ **30 ngày** để trưởng thành.
- Training và threshold tuning dùng train/validation, giữ holdout không nhìn trước.
- Model v2 phải vượt baseline về business metrics, không chỉ accuracy.
- Scores được ghi **theo ngày + model version**, có TTL/retention và consumer IAM.
- Chiến dịch chỉ dùng score sau khi kiểm tra **consent, hạn mức liên hệ và chính sách marketing**.
- Không chuyển scores trực tiếp thành quyết định gây bất lợi hoặc suy luận nhạy cảm ngoài phạm vi đã được phê duyệt.

### 15.2. Sự cố và cách phân tích

Một hôm ROC AUC vẫn khá cao trên dữ liệu tập huấn luyện, nhưng tỷ lệ phản hồi campaign giảm mạnh. Nhóm muốn lập tức retrain hàng giờ.

**Chẩn đoán đúng:** xem có marketing campaign mới khiến tỷ lệ churn cơ bản đổi không; feature snapshot có đầy đủ không; label đủ 30 ngày chưa; model output drift ra sao; liệu hệ thống liên hệ có đổi routing không. **Retrain thường xuyên** không tự khắc phục rò rỉ nhãn hoặc sai business definition.

### 15.3. Điều kiện nghiệm thu

| Yêu cầu | Bằng chứng |
|---|---|
| Train reproducible | SQL/model/data snapshot version |
| Holdout độc lập | Split và label window được audit |
| Mô hình dùng hợp lý | Precision/recall, calibration, impact review |
| Quyền tối thiểu | Query job SA, dataset/model/connection IAM |
| Vận hành có thể theo dõi | Job success, drift, model score distributions |
| Không phát sinh remote requests ngoài ý muốn | Model type và service billing rõ |
| Rollback được | v1 model còn tồn tại, scheduled job có change record |
| Chi phí có kiểm soát | Cloud Billing/report per SKU |

## 16. Bài tập thực hành và đáp án

### 16.1. Bài A — Train, evaluate và predict

Trong project lab được cấp quyền:

1. Tạo dataset riêng, chạy SQL sinh 3.000 rows.
2. Kiểm tra đủ 2 nhãn và đúng chia train/validation/holdout.
3. Tạo model **churn_logreg_v1** với **CUSTOM BOOL split**.
4. Chạy **ML.EVALUATE** trên holdout, ghi 6 metrics.
5. Chạy **ML.PREDICT**, lấy **20 khách hàng có xác suất yes cao nhất**.
6. Lưu scores vào bảng và ghi model_version/scored_at.
7. Không thay label hoặc công thức dữ liệu sau khi báo cáo kết quả mà không version hóa bảng.

**Đạt khi:** model train thành công; holdout chưa được dùng trong CREATE MODEL; output prediction có nhãn và xác suất, không bị lẫn customer ID vào features.

### 16.2. Bài B — Rò rỉ dữ liệu

Một nhóm thêm **cancellation_date** và **last_login_at_after_snapshot** vào training query. ROC AUC tăng rất nhiều.

**Câu hỏi:** có nên phát hành ngay?

**Đáp án:** không. Đây có thể là **future leakage**: ở ngày thực hiện dự đoán không thể biết các giá trị đó. Phải loại cột chỉ có ở tương lai, xây feature snapshot as-of, tách tập theo thực tế triển khai và đánh giá lại.

### 16.3. Bài C — Precision và recall

Giả sử trên holdout có 100 khách thực sự churn. Mô hình cảnh báo 80 khách, trong số đó 60 khách thực sự churn.

\[
\text{Precision} = 60/80 = 0.75;\qquad
\text{Recall} = 60/100 = 0.60.
\]

**Nếu chi phí gửi ưu đãi cao**, nên thử threshold nào? **Đáp án định hướng:** xem threshold cao hơn trên **validation set** để cải thiện precision nếu business cho phép giảm recall; không có threshold tối ưu phổ quát và không tuning trên holdout cuối.

### 16.4. Bài D — Phân biệt local và remote inference

Một analyst tạo BQML logistic regression và dùng **ML.PREDICT**; người khác tạo remote Gemini model và gọi **AI.GENERATE_TEXT**.

**Trả lời:** (1) code/models xử lý ở đâu, (2) danh tính IAM nào cần thêm, (3) dịch vụ nào tính phí, (4) dữ liệu nào rời khỏi BigQuery?

**Đáp án:** logistic regression do BigQuery ML quản lý; remote LLM gọi endpoint AI với BigQuery connection SA; có thêm AI endpoint/quota/token charges và dữ liệu prompt được gửi tới dịch vụ AI. Không coi cả hai là một loại compute vì đều được gọi bằng SQL.

### 16.5. Bài E — Thiết kế pipeline sản xuất

Đề xuất job chấm điểm **mỗi đêm** cho 5 triệu khách hàng. Cần gì để bảo đảm không tính lại sai khi scheduled job chạy hai lần?

**Đáp án định hướng:** feature snapshot có ngày rõ, scheduled job service account, output partition theo ngày, **model_version/run_id**, idempotent MERGE hoặc write policy, job monitoring, quota/budget và rollback plan. Không overwrite một bảng scores duy nhất mà không lưu version.

### 16.6. Bài F — Chi phí remote AI

100.000 đánh giá sản phẩm cần tạo tóm tắt; mỗi row phát một remote request. Analyst thử truy vấn trên toàn bảng trong khi chỉ cần kiểm tra **100 mẫu**.

**Đáp án:** lọc và materialize một bảng 100 rows đại diện **trước khi AI.GENERATE_TEXT**, tính token/request budget và xác minh model output/status; không dựa vào LIMIT đặt bên ngoài function để giả định chỉ gọi 100 requests.

### 16.7. Biên bản lab mẫu

~~~text
PROJECT_ID / LOCATION / DATASET:
DATA_SOURCE / SNAPSHOT_TIME:
ROW_COUNT / CLASS_DISTRIBUTION:
TRAIN_SPLIT / EVAL_SPLIT / HOLDOUT_SPLIT:
FEATURE_SCHEMA / LABEL_DEFINITION:
MODEL_NAME / MODEL_TYPE / TRAINING_JOB_ID:
EVAL_ACCURACY / PRECISION / RECALL / F1 / ROC_AUC / LOG_LOSS:
THRESHOLD_SELECTION_POLICY:
PREDICT_OUTPUT / SCORE_TABLE / MODEL_VERSION:
EXPLAIN_PREDICT_NOTES:
REMOTE_MODEL_USED? / CONNECTION_SA / AI_ENDPOINT:
IAM_REVIEW / DATA_RESIDENCY_REVIEW:
QUERY_BYTES / REMOTE_TOKEN_COST / BILLING_CHECK:
CLEANUP / OPEN_ISSUES:
~~~

Chỉ ghi **PASS** nếu đã thực sự kiểm chứng. Nếu không có project BigQuery được phép sử dụng, ghi **NOT_EXECUTED** thay vì tự báo training hoặc inference thành công.

## 17. Dọn tài nguyên lab và tham khảo

### 17.1. Cleanup có kiểm soát

**Chỉ dọn dataset và resources do chính người học tạo, sau khi xác minh không có consumers hoặc scheduled jobs tham chiếu.** Lệnh SQL bên dưới **xóa thật**:

~~~sql
-- THAY ĐỔI/XÓA: chỉ project lab và sau owner approval.
DROP TABLE IF EXISTS `PROJECT_ID.bqml_lab.churn_scores_lab`;
DROP MODEL IF EXISTS `PROJECT_ID.bqml_lab.churn_logreg_v1`;
DROP TABLE IF EXISTS `PROJECT_ID.bqml_lab.churn_features`;

-- Chỉ khi đã tạo remote model và không còn sử dụng:
-- DROP MODEL IF EXISTS `PROJECT_ID.bqml_lab.text_remote_lab`;
~~~

Không xóa toàn dataset nếu nó được chia sẻ. Nếu tạo **Cloud resource connection** riêng cho remote lab, cần kiểm kê các remote models/tác vụ khác tham chiếu trước khi xóa; quyền IAM của connection SA và endpoint có lifecycle riêng. Xóa BQML model **không tự xóa dữ liệu đã gửi đến endpoint hay mọi logs/billing records**.

### 17.2. Nguồn chính thức

- [BigQuery ML introduction](https://docs.cloud.google.com/bigquery/docs/bqml-introduction)
- [Model creation with BigQuery ML](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create)
- [CREATE MODEL for logistic/linear regression](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-glm)
- [ML.EVALUATE](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-evaluate)
- [ML.PREDICT](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-predict)
- [ML.CONFUSION_MATRIX](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-confusion)
- [ML.ROC_CURVE](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-roc)
- [ML.EXPLAIN_PREDICT](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-explain-predict)
- [ML.WEIGHTS](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-weights)
- [Remote models over LLMs](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-remote-model)
- [AI.GENERATE_TEXT](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-ai-generate-text)
- [BigQuery scheduled queries](https://docs.cloud.google.com/bigquery/docs/scheduling-queries)
- [BigQuery INFORMATION_SCHEMA jobs metadata](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs)
- [BigQuery security overview](https://docs.cloud.google.com/bigquery/docs/security-overview)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing)

**Checklist cuối:** định nghĩa label và snapshot → kiểm tra leakage → chia train/eval/holdout → CREATE MODEL → ML.EVALUATE → chọn threshold trên validation → ML.PREDICT → explain/model governance → scoring table theo version → giám sát drift/chi phí → đánh giá remote AI IAM/residency nếu dùng → cleanup đúng ownership.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** BigQuery ML giúp triển khai machine learning **trong luồng phân tích dữ liệu bằng SQL**, tích hợp dữ liệu từ Cloud Run/GKE/Compute Engine và dịch vụ lưu trữ. Kết quả chỉ có giá trị khi **features đúng thời điểm, đánh giá ngoài mẫu, IAM phù hợp, endpoint/chi phí được kiểm soát và quyết định nghiệp vụ có giám sát**.









