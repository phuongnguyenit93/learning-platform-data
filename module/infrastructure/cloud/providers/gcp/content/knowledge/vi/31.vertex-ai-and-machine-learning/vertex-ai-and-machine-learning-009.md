# Vertex AI Feature Store và phục vụ đặc trưng trên Google Cloud

> **Chương:** Vertex AI và học máy  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Một mô hình dự đoán khách hàng có nguy cơ rời bỏ cần cùng một định nghĩa **features** khi train và khi dự đoán: chi tiêu 30 ngày gần nhất, số lần đăng nhập 7 ngày qua, gói đang dùng. Nếu nhóm dữ liệu tính chúng bằng SQL trong BigQuery nhưng Cloud Run API tự viết một đoạn Java khác để tính theo thời gian thực, hệ thống dễ gặp **training-serving skew**, sai khác về thời điểm, NULL, timezone và cách chuẩn hóa dữ liệu.

**Vertex AI Feature Store** — hiện được trình bày trong tài liệu Google Cloud dưới tên **Feature Store trên Gemini Enterprise Agent Platform** — cho phép dùng **BigQuery làm offline feature source**, đăng ký quản lý các đặc trưng và đồng bộ những giá trị cần phục vụ sang **FeatureOnlineStore**. Ứng dụng trên **Cloud Run/GKE/Compute Engine** gọi online serving API để lấy feature theo **entity ID** trước khi thực hiện model inference.

Bài học lấy **Bigtable online serving** làm phương án triển khai chính. **Optimized online serving đã deprecated từ ngày 17/05/2026, dự kiến sunset ngày 17/02/2027**, nên không xây hệ thống mới dựa vào nó. Ví dụ sử dụng khách hàng giả lập và BigQuery table nhỏ; không dùng dữ liệu cá nhân thật.

**An toàn và chi phí:** tạo FeatureOnlineStore kiểu Bigtable có thể phát sinh chi phí compute/storage ngay cả khi ít request. Không chạy lệnh tạo/xóa online store hoặc đổi IAM trên production. Phần thực hành triển khai chỉ dành cho project lab có billing/quota và được owner phê duyệt.

## Mục tiêu học tập

1. Phân biệt **feature**, **entity**, **offline store**, **Feature Registry**, **FeatureOnlineStore**, **FeatureView**, **sync** và **online fetch**.
2. Thiết kế feature table trong BigQuery với một **entity ID duy nhất** khi tạo feature view trực tiếp từ source.
3. Tránh rò rỉ dữ liệu tương lai bằng **point-in-time joins** khi tạo tập training.
4. Tạo online store **Bigtable**, feature view và đọc feature theo entity ID bằng REST/Python.
5. Giải thích scheduled sync, continuous sync, refresh lag, NULL và các giới hạn UPDATE/DELETE.
6. Thiết kế quyền IAM tách biệt giữa BigQuery source, Vertex AI Feature Store, runtime và service agent.
7. Kiểm tra dữ liệu đúng, độ trễ p95/p99, drift, quota, storage và chi phí.
8. Đánh giá khi nào Feature Store phù hợp hơn query BigQuery trực tiếp, cache tự quản hoặc Vector Search.

## 1. Kiến trúc offline → online → inference

~~~mermaid
flowchart LR
    SRC["Cloud SQL / Pub/Sub / ứng dụng"] --> PIPE["ELT / Dataflow / scheduled SQL"]
    PIPE --> BQ["BigQuery offline features\nlatest + history"]
    BQ --> REG["Feature Registry\noptional"]
    BQ --> FV["FeatureView"]
    REG -. "Feature definitions" .-> FV
    FV --> SYNC["Scheduled / Continuous sync\nnếu được hỗ trợ"]
    SYNC --> STORE["FeatureOnlineStore\nBigtable serving"]
    API["Cloud Run Java API"] --> FETCH["fetchFeatureValues(entity ID)"]
    STORE --> FETCH
    FETCH --> MODEL["Vertex AI / custom model"]
    MODEL --> APP["Prediction/decision\ncó nghiệp vụ kiểm soát"]
    BQ --> TRAIN["Point-in-time training data"]
    TRAIN --> EXP["Training / evaluation / model registry"]
~~~

**Phân biệt ba mặt phẳng:**

| Thành phần | Chức năng | Điều không nên nhầm |
|---|---|---|
| **BigQuery feature tables** | Offline data, lịch sử, features phục vụ batch/train | Không tự là endpoint đọc theo entity có latency online thấp |
| **Feature Registry** | Metadata/khai báo nhóm đặc trưng và các cột feature | Không tự lưu một bản sao data online |
| **FeatureOnlineStore + FeatureView** | Vật liệu hóa dữ liệu từ BigQuery, phục vụ giá trị gần nhất | Không thay engine train model hoặc model endpoint |

**Feature Store không tự dự đoán nhãn.** Online fetch trả feature values, sau đó model-serving code mới gọi mô hình để suy luận. Nếu mô hình yêu cầu thêm đặc trưng real-time chưa sync, phải có kiến trúc hợp nhất hợp lệ, không mặc định Feature Store đã có giá trị mới nhất sau từng transaction.

### 1.1. Entity, feature và feature view

| Khái niệm | Ví dụ | Trách nhiệm |
|---|---|---|
| **Entity** | Khách hàng **cust-101** | Khóa tìm dữ liệu của một đối tượng |
| **Feature** | **spend_30d**, **sessions_7d**, **plan** | Giá trị có định nghĩa SQL, kiểu, owner, thời hạn dữ liệu |
| **Feature group** | **customer_behavior** | Đăng ký BigQuery source và metadata, có thể lưu lịch sử |
| **Feature Registry** | Danh mục các feature groups/features | Tái sử dụng và quan sát đặc trưng |
| **FeatureOnlineStore** | **customer-features-lab** | Compute/storage cho online read |
| **FeatureView** | **churn-inputs-lab** | Tập feature được đồng bộ/phục vụ cùng cấu hình |
| **Feature timestamp** | 2026-11-18T10:00:00Z | Thời điểm giá trị feature có hiệu lực theo event time |
| **Sync schedule** | Mỗi giờ | Độ mới của online view, không phải source update rate |

Đối với **FeatureView trực tiếp từ BigQuery**, mỗi hàng source cần có entity ID duy nhất và **chỉ các giá trị hiện hành**; không được thiết kế bảng source trực tiếp có nhiều bản ghi lịch sử cùng entity hoặc cột tên **feature_timestamp**. Nếu cần lịch sử, time series hay đặc trưng từ nhiều nguồn, dùng **Feature Registry/feature groups** theo điều kiện hỗ trợ.

### 1.2. Vì sao online store không thay thế BigQuery history?

BigQuery giữ giá trị lịch sử để tái dựng feature tại **thời điểm ra quyết định**. Online store thông thường phục vụ **giá trị mới nhất** theo entity để inference nhanh. Khi online API được gọi lúc 12:00, không thể tự lấy dữ liệu của 09:00 để train một mô hình lịch sử chỉ bằng việc đọc online store lúc 12:00.

Offline history và online latest có thể xuất phát từ cùng pipeline, nhưng cần **time semantics, version/schema contract và quality gates** giống nhau.

## 2. Chọn online serving đúng theo vòng đời sản phẩm

| Lựa chọn | Trạng thái/đặc điểm | Nên dùng khi |
|---|---|---|
| **Bigtable online serving** | Hướng hiện hành; hỗ trợ scheduled và continuous sync với điều kiện | Phục vụ feature theo entity với độ bền cao và volume lớn |
| **Optimized online serving** | **Deprecated 17/05/2026**, sunset **17/02/2027** | Chỉ duy trì/chuyển đổi workload cũ, **không mở rộng hệ mới** |
| **BigQuery SQL trực tiếp** | Không cần materialize online store | Batch predictions/SQL joins; latency cao hơn online key fetch |
| **Cache Redis/Memorystore tự quản** | Linh hoạt, phải tự duy trì đồng bộ/expiry/schema | Use case caching đơn giản, không cần Feature Registry |
| **Vector Search** | Chuyên cho nearest-neighbor trên embeddings | Retrieval/semantic search; Bigtable online serving không quản lý embeddings |
| **Vertex AI endpoint** | Nhận features để chạy model inference | Model serving, không thay feature storage |

**Quan trọng tính đến tháng 11/2026:** không trình bày Optimized online serving như lựa chọn khuyến nghị mới, dù tài liệu/API cũ vẫn còn ví dụ. Google Cloud khuyến nghị **migrating sang Bigtable online serving** và dùng **Vector Search** nếu cần retrieval embedding. Tham khảo [Online serving types](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/online-serving-types).

## 3. Hai cách khai báo FeatureView

### 3.1. Trực tiếp từ BigQuery — bài lab chính

~~~text
BigQuery table:
bq://PROJECT_ID.feature_lab.customer_features_latest

customer_id STRING | spend_30d FLOAT64 | sessions_7d INT64 | plan STRING
------------------ | ---------------- | ----------------- | -----------
cust-101           | 520000.0         | 9                 | plus
cust-102           | 120000.0         | 2                 | basic
cust-103           | 930000.0         | 15                | team
~~~

Khi tạo **FeatureView**: khai báo **big_query_source.uri** và **entity_id_columns=["customer_id"]**. Bảng chỉ có một row/customer, không cần Feature Registry. Đây là cách dễ thực hành nhất nhưng **không hỗ trợ lưu lịch sử feature cho cùng ID trong chính bảng source của FeatureView**.

### 3.2. Qua Feature Registry — khi cần quản trị và time-series

~~~text
BigQuery feature history
       ↓
FeatureGroup customer_behavior
  source URI / entity IDs / time-series column
       ↓
Feature definitions (spend_30d, sessions_7d, plan)
       ↓
FeatureView linked to feature group
       ↓
Bigtable online serving
~~~

Đăng ký nhóm/feature có lợi khi cần **một BigQuery entity có nhiều mốc thời gian**, kết hợp đặc trưng từ nhiều feature groups, feature monitoring và tái sử dụng metadata. Trong mô hình time-series, **feature_timestamp** phải là TIMESTAMP và được khai báo đúng; Feature Store thường phục vụ **giá trị non-null mới nhất** theo timestamp, trừ khi sử dụng cấu hình **dense + Bigtable + scheduled sync** được hỗ trợ để giữ cả NULL gần nhất. Không coi NULL là đồng nghĩa DELETE.

**Cẩn thận với liên tục đồng bộ:** chỉ hỗ trợ khi FeatureView lấy từ **Feature Registry**, online store là **Bigtable** và BigQuery source ở location được hỗ trợ (ví dụ **us, eu, us-central1**). Nó chỉ đồng bộ **records mới**, không phản ánh UPDATE hoặc DELETE trên records đã có, và không cho sửa cấu hình feature view đó sau khi tạo. Chi tiết: [Create a feature view](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-featureview).

## 4. Chuẩn bị môi trường và tài nguyên lab

### 4.1. Preflight chỉ đọc

Giả định sử dụng **Cloud Shell (Bash)**, BigQuery/Vertex AI APIs đã được tổ chức phê duyệt, project có billing, quota và quyền tương ứng.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="us-central1"
DATASET="feature_lab"
ONLINE_STORE="customer-features-lab"
FEATURE_VIEW="churn-inputs-lab"

gcloud auth list
gcloud config list project
gcloud projects describe "$PROJECT_ID"

# CHỈ ĐỌC: kiểm tra API đã bật và dataset/tài nguyên hiện hữu.
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="NAME:(aiplatform.googleapis.com OR bigquery.googleapis.com)"

bq --project_id="$PROJECT_ID" ls
~~~

**Location:** BigQuery dataset và Feature Store resources phải dùng **locations tương thích**, không trộn tùy tiện US multi-region với region us-central1. Lab sử dụng **us-central1** cho cả hai. Nếu dự án có data residency ở nơi khác, kiểm tra [supported locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/locations) trước khi triển khai.

### 4.2. Bật APIs nếu đã được phê duyệt

~~~bash
# THAY ĐỔI CẤU HÌNH PROJECT — yêu cầu đủ IAM và owner approval.
gcloud services enable aiplatform.googleapis.com bigquery.googleapis.com \
  --project="$PROJECT_ID"
~~~

**Không tạo service account key JSON** để gọi Feature Store; ở máy local dùng gcloud/ADC được cấp quyền, trên Cloud Run hoặc GKE dùng workload identity. IAM quản trị BigQuery source và FeatureView có thể thuộc nhiều projects khác nhau; quyền không tự truyền qua.

### 4.3. Tạo BigQuery dataset của riêng lab

~~~bash
# THAY ĐỔI: chỉ tạo khi chưa tồn tại và có approval.
bq --project_id="$PROJECT_ID" --location="$LOCATION" mk \
  --dataset "$PROJECT_ID:$DATASET"

# CHỈ ĐỌC: kiểm tra vị trí dataset.
bq --project_id="$PROJECT_ID" show "$PROJECT_ID:$DATASET"
~~~

Nếu dataset **feature_lab** đã thuộc nhóm khác, không ghi đè tables hoặc đổi IAM; hãy xin một dataset riêng. Các SQL sau dùng placeholder **PROJECT_ID**: phải thay đúng project ID của lab trước khi chạy.

## 5. Lab A — Chuẩn bị bảng đặc trưng hiện hành trong BigQuery

### 5.1. Tạo dữ liệu thử không chứa thông tin cá nhân

Trong **BigQuery Studio**, chọn GoogleSQL, project/location lab và chạy:

~~~sql
-- THAY ĐỔI/REPLACE: chỉ bảng lab.
CREATE OR REPLACE TABLE `PROJECT_ID.feature_lab.customer_features_latest`
OPTIONS (
  expiration_timestamp =
    TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
) AS
SELECT *
FROM UNNEST([
  STRUCT('cust-101' AS customer_id,
         520000.0 AS spend_30d,
         9 AS sessions_7d,
         'plus' AS plan),
  STRUCT('cust-102', 120000.0, 2, 'basic'),
  STRUCT('cust-103', 930000.0, 15, 'team')
]);
~~~

**Ý nghĩa feature:**

- **spend_30d (FLOAT64):** tổng chi tiêu trong 30 ngày qua theo timezone và quy tắc làm tròn được thống nhất.
- **sessions_7d (INT64):** số phiên hoạt động hợp lệ trong 7 ngày qua.
- **plan (STRING):** loại gói hiện hành; phải xử lý unknown categories giữa train/predict.
- **customer_id (STRING):** khóa phục vụ, **không tự là feature đầu vào model** nếu không có lý do.

Đây là bảng **latest**, chỉ có một row/customer và **không chứa cột feature_timestamp**, nên phù hợp để tạo FeatureView trực tiếp từ BigQuery. Không dùng bảng này làm lịch sử huấn luyện nhiều thời điểm.

### 5.2. Kiểm tra key uniqueness, schema và NULL

~~~sql
-- CHỈ ĐỌC.
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT customer_id) AS unique_ids,
  COUNTIF(customer_id IS NULL OR customer_id = '') AS missing_ids,
  COUNTIF(spend_30d IS NULL OR sessions_7d IS NULL) AS missing_features
FROM `PROJECT_ID.feature_lab.customer_features_latest`;

-- Đảm bảo không có duplicate entity ID.
SELECT customer_id, COUNT(*) AS occurrences
FROM `PROJECT_ID.feature_lab.customer_features_latest`
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

**Kỳ vọng:** row_count=3, unique_ids=3, missing_ids=0, missing_features=0; truy vấn duplicate trả 0 rows. Với dữ liệu thật, đặt **quality gate** trước khi sync; đừng kỳ vọng hệ online store tự suy nên lấy hàng nào khi key trùng.

### 5.3. Dữ liệu mới nhất chưa chắc mới đủ với nghiệp vụ

Bảng có một row/customer nhưng có thể đã được cập nhật cách đây 12 giờ. Mỗi feature nên có **contract** về thời điểm nguồn, freshness và lịch refresh. Nếu thêm trường **computed_at** để quan sát dữ liệu, đây sẽ là một feature/metadata column; hãy kiểm tra policy về columns được phép expose và **không đặt tên feature_timestamp** khi dùng BigQuery source trực tiếp.

**Data deletion:** khi xóa một customer khỏi BigQuery source, **Bigtable online serving không tự xóa entity tương ứng khỏi FeatureView sau sync**. Không dùng thao tác xóa row BigQuery như cam kết xóa dữ liệu ở online store; cần runbook xóa/recreate feature view hoặc thiết kế quyền phục vụ/retention thích hợp.

## 6. Point-in-time correctness — tránh training-serving skew

### 6.1. Hai thời điểm phải biết

Đối với một đặc trưng sử dụng dữ liệu giao dịch, cần phân biệt:

- **feature_timestamp / event time:** thời điểm sự kiện xảy ra hoặc trạng thái có hiệu lực.
- **available_at / ingestion time:** thời điểm feature thật sự đã sẵn sàng trong pipeline.
- **prediction_time:** thời điểm mô hình được phép biết các đặc trưng khi dự đoán.
- **label_window:** khoảng tương lai dùng xác định ground truth, không được xuất hiện trong features.

**Điều kiện tối thiểu:** feature_timestamp **không sau** prediction_time **và** available_at **không sau** prediction_time. Chỉ dùng event time có thể gây leakage nếu sự kiện đến muộn nhưng được pipeline backfill như thể lúc đó đã sẵn sàng.

### 6.2. Ví dụ GoogleSQL point-in-time join hoàn chỉnh

Truy vấn dưới đây **chỉ đọc dữ liệu tạo tại chỗ** (không tạo resources), cố ý dùng hai mốc dự đoán cho một khách hàng.

~~~sql
WITH feature_history AS (
  SELECT *
  FROM UNNEST([
    STRUCT(
      'cust-101' AS customer_id,
      TIMESTAMP('2026-10-01T09:00:00Z') AS feature_timestamp,
      TIMESTAMP('2026-10-01T09:03:00Z') AS available_at,
      100000.0 AS spend_30d,
      2 AS sessions_7d
    ),
    STRUCT(
      'cust-101',
      TIMESTAMP('2026-10-02T09:00:00Z'),
      TIMESTAMP('2026-10-02T09:10:00Z'),
      200000.0,
      5
    ),
    -- Sự kiện quá khứ nhưng xử lý đến muộn: không được dùng ở 01/10.
    STRUCT(
      'cust-101',
      TIMESTAMP('2026-10-01T10:00:00Z'),
      TIMESTAMP('2026-10-03T00:00:00Z'),
      999999.0,
      99
    )
  ])
),
prediction_samples AS (
  SELECT *
  FROM UNNEST([
    STRUCT(
      'sample-1' AS sample_id,
      'cust-101' AS customer_id,
      TIMESTAMP('2026-10-01T12:00:00Z') AS prediction_time
    ),
    STRUCT(
      'sample-2',
      'cust-101',
      TIMESTAMP('2026-10-02T12:00:00Z')
    )
  ])
)
SELECT
  p.sample_id,
  p.customer_id,
  p.prediction_time,
  f.feature_timestamp,
  f.spend_30d,
  f.sessions_7d
FROM prediction_samples p
LEFT JOIN feature_history f
  ON p.customer_id = f.customer_id
 AND f.feature_timestamp <= p.prediction_time
 AND f.available_at <= p.prediction_time
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY p.sample_id
  ORDER BY f.feature_timestamp DESC, f.available_at DESC
) = 1
ORDER BY p.sample_id;
~~~

**Kết quả kỳ vọng:** sample-1 lấy spend_30d=100000, sessions_7d=2; sample-2 lấy 200000 và 5. Bản ghi 999999 đến sau thời điểm dự đoán nên **không được đưa vào bất kỳ sample nào ở đây**, dù event time nằm trong quá khứ.

Với dữ liệu lớn, cần partition/filter thời gian, xử lý multiple versions/late-arriving events, khóa phân vùng entity đúng và tối ưu joins. BigQuery cũng có các hàm hỗ trợ **ML.FEATURES_AT_TIME** và **ML.ENTITY_FEATURES_AT_TIME** để tra cứu feature tại thời điểm, xem [BigQuery feature serving](https://docs.cloud.google.com/bigquery/docs/feature-serving).

### 6.3. Những nguồn skew phổ biến

| Sai khác | Hậu quả | Cách tránh |
|---|---|---|
| SQL tính **7 ngày** nhưng Java tính **calendar week** | Feature không cùng định nghĩa | Một feature contract và tests |
| Training dùng timestamp UTC, serving dùng giờ local | Sai cửa sổ | UTC/as-of rules rõ ràng |
| Backfill dùng dữ liệu đến sau snapshot | Data leakage | Kiểm tra available_at |
| Offline NULL nhưng online lấy non-null trước đó | Mô hình nhận giá trị cũ | Chọn cấu hình NULL semantics đúng |
| Categorical values khác chữ hoa/thường | Mapping sai | Shared preprocessing/versioned schema |
| Offline latest cập nhật nhưng FeatureView sync chưa chạy | Online stale | Freshness SLO và sync monitor |
| Model v2 chờ feature mới, FeatureView vẫn schema v1 | Missing feature | Contract tests trước rollout |

**Không gọi Feature Store là giải pháp “tự động loại mọi skew”.** Dịch vụ giúp tái sử dụng features và serving theo entity; tính đúng của feature computation, timestamps, readiness, type/schema và model version là trách nhiệm của pipeline.

## 7. Lab B — Tạo FeatureOnlineStore bằng Bigtable online serving

### 7.1. Kiểm tra chi phí và quyền trước thao tác tạo

**FeatureOnlineStore là tài nguyên online riêng**: bảng BigQuery nhỏ không có nghĩa online serving miễn phí. Chỉ tạo trong project lab với owner approval. Nếu có store do nhóm sở hữu sẵn, dùng lại khi được phép; **không tạo mới chỉ để thử API**.

Người tạo cần quyền quản lý Vertex AI Feature Store, đồng thời service agent cần thiết lập đúng để đọc BigQuery source. Các lệnh sau dùng **REST v1** qua Cloud Shell/Bash:

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="us-central1"
ONLINE_STORE="customer-features-lab"
FEATURE_VIEW="churn-inputs-lab"

API_ROOT="https://$LOCATION-aiplatform.googleapis.com/v1/projects/$PROJECT_ID/locations/$LOCATION"

# CHỈ ĐỌC: store hiện hữu hoặc 404 nếu chưa tồn tại.
curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE"
~~~

### 7.2. Tạo Bigtable online store (thay đổi, có phí)

Trong một thư mục lab riêng, không đặt cấu hình IAM/secrets vào source repository bài học:

~~~bash
# Tạo file JSON ví dụ trên máy học tập; chưa gọi Cloud API.
cat > online-store.json <<'JSON'
{
  "bigtable": {
    "auto_scaling": {
      "min_node_count": 1,
      "max_node_count": 3,
      "cpu_utilization_target": 50
    }
  }
}
JSON

# THAY ĐỔI CÓ PHÍ: POST chỉ khi store chưa tồn tại và owner đã duyệt.
curl -f -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @online-store.json \
  "$API_ROOT/featureOnlineStores?feature_online_store_id=$ONLINE_STORE"
~~~

**Phản hồi thường là long-running operation**: request tạo thành công chưa chắc resource đã sẵn sàng để tạo feature view. Xem operation status và chi tiết online store trong Console hoặc REST. Các thông số min/max node và CPU target chỉ minh họa, **không dùng làm sizing mặc định** production. [Create an online store](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-onlinestore).

### 7.3. Chọn Bigtable, không chọn Optimized

Bigtable online serving hỗ trợ **CMEK** khi có yêu cầu; nó **không hỗ trợ embeddings management**. Với bài toán approximate nearest neighbors, đánh giá **Vector Search**. Không dùng cấu hình Optimized trong JSON tạo store mới chỉ vì một blog cũ sử dụng. Loại online serving **không thể đổi sau khi online store được tạo**; muốn chuyển loại phải lập kế hoạch migration sang resource mới.

## 8. Lab C — Tạo FeatureView từ bảng BigQuery

### 8.1. Khai báo nguồn trực tiếp và lịch đồng bộ

Chỉ tiếp tục khi **FeatureOnlineStore đã ready** và bảng **customer_features_latest** kiểm tra uniqueness PASS.

~~~bash
# Dùng environment variables từ mục 7.
# File lab không chứa credentials, chỉ tên resource.
cat > feature-view.json <<EOF
{
  "big_query_source": {
    "uri": "bq://$PROJECT_ID.feature_lab.customer_features_latest",
    "entity_id_columns": ["customer_id"]
  },
  "sync_config": {
    "cron": "0 * * * *"
  }
}
EOF

# THAY ĐỔI: tạo FeatureView có lịch đồng bộ hằng giờ.
curl -f -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @feature-view.json \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews?feature_view_id=$FEATURE_VIEW"
~~~

**Ngữ nghĩa:** FeatureView lấy **customer_id** làm khóa và phục vụ các cột feature còn lại. Cron **0 * * * *** yêu cầu đồng bộ **mỗi giờ**, không có nghĩa BigQuery cập nhật lúc nào thì online store cũng đổi tức thì. Kiểm tra các giới hạn cron/sync và phí BigQuery trước khi chọn lịch production. [Create a feature view](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-featureview).

### 8.2. Trigger sync thủ công và xem trạng thái

Với feature view dùng **scheduled sync**, có thể yêu cầu sync ngay để không chờ lịch:

~~~bash
# THAY ĐỔI: phát sinh sync, có thể tạo chi phí BigQuery/Feature Store.
curl -f -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data '' \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW:sync"

# CHỈ ĐỌC: chi tiết và lịch sử sync.
curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW"

curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW/featureViewSyncs"
~~~

Phản hồi của **sync** có thể chỉ là **tên FeatureViewSync**, chưa phải dấu hiệu dữ liệu materialize xong. Kiểm tra operation **finalStatus**, lỗi, thời gian bắt đầu/kết thúc và record counts. **Không gọi sync nhiều lần liên tiếp** khi một sync đang chạy; yêu cầu sau có thể được xếp hàng.

**Continuous sync** không thể trigger thủ công; cũng **không áp dụng** cho FeatureView trực tiếp từ BigQuery như lab này. [Start a data sync](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/sync-data).

### 8.3. Kiểm tra IAM khi đồng bộ

Khi source BigQuery không cùng project hoặc dùng **dedicated feature view service account**, principal mà Feature Store dùng truy vấn bảng phải có quyền BigQuery tương ứng. Xem email service account qua FeatureView details API nếu đã cấu hình dedicated; cấp quyền trên **dataset/bảng nguồn** và quyền tạo BigQuery job theo tài liệu.

Khi lỗi Access Denied, xác định **principal trong sync logs**, **dataset IAM** và **BigQuery jobs permissions**, không cấp Owner toàn project. Đồng bộ có thể bị chặn vì location mismatch hoặc BigQuery job quota dù bảng nguồn chỉ có ba rows.

## 9. Lab D — Online fetch theo entity ID

FeatureView phải **đã sync ít nhất một lần thành công** trước khi đọc online.

~~~bash
# CHỈ ĐỌC feature values (nhưng có thể tính phí online requests).
curl -f -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data '{"data_key":{"key":"cust-101"},"data_format":"KEY_VALUE"}' \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW:fetchFeatureValues"
~~~

**Kỳ vọng:** kết quả chứa **spend_30d=520000**, **sessions_7d=9**, **plan=plus** theo schema KEY_VALUE/protobuf JSON thực tế. Không hardcode response thành business DTO nếu chưa kiểm tra tên trường và kiểu; parse có validation.

### 9.1. Entity không tồn tại

~~~bash
# CHỈ ĐỌC; xem not-found/empty theo behavior của API đang dùng.
curl -i -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data '{"data_key":{"key":"cust-does-not-exist"},"data_format":"KEY_VALUE"}' \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW:fetchFeatureValues"
~~~

**Không** ánh xạ mọi lỗi 404/permission/timeout thành **0** hoặc **plan=basic** rồi âm thầm chạy model. Ứng dụng cần phân biệt entity không tồn tại, online view chưa sync, quyền bị từ chối và lỗi tạm thời. Fallback phải có contract và giám sát.

### 9.2. Composite entity key

Nếu có hai cột khóa (**tenant_id**, **customer_id**), FeatureView có thể khai báo cả hai; khi fetch cần gửi **data_key.composite_key.parts** đúng thứ tự.

~~~json
{
  "data_key": {
    "composite_key": {
      "parts": ["tenant-a", "cust-101"]
    }
  },
  "data_format": "KEY_VALUE"
}
~~~

Không tự nối khóa bằng một delimiter chưa escape như **tenant#customer** nếu ID có thể chứa dấu phân cách, hoặc dùng user input chưa xác thực làm khóa multi-tenant.

### 9.3. Kiểm tra online freshness sau khi BigQuery thay đổi

~~~sql
-- THAY ĐỔI BẢNG LAB, không dùng bảng production.
UPDATE `PROJECT_ID.feature_lab.customer_features_latest`
SET sessions_7d = 11
WHERE customer_id = 'cust-101';
~~~

Fetch ngay sau UPDATE có thể vẫn thấy **9** vì lịch sync chưa chạy. Trigger **sync** thủ công trên FeatureView scheduled, kiểm tra sync hoàn tất và fetch lại, kỳ vọng **11**. Nếu vẫn thấy 9, kiểm tra sync status/source URI/permissions và read cache, không kết luận sai dịch vụ khi sync chưa hoàn tất.

### 9.4. Xóa entity không đồng nghĩa xóa feature online

Nếu xóa **cust-102** khỏi BigQuery, **Bigtable FeatureView không tự xóa cust-102 khi sync**. Hướng dẫn Google Cloud yêu cầu **xóa FeatureView** để xóa những record còn giữ tương ứng. Hệ thống có yêu cầu xóa dữ liệu phải có **deletion runbook** và xác minh toàn chuỗi, không chỉ BigQuery DELETE.

Trong ứng dụng production, cần bổ sung chính sách **consent/active-entity** hoặc chặn phục vụ sau khi được yêu cầu xóa, kể cả lúc online store chưa được dọn. Xóa/recreate view có thể làm gián đoạn và phải được owner chấp thuận.

## 10. Dùng Feature Store từ ứng dụng Java/Cloud Run

Tương tự Cloud Tasks/BigQuery, Cloud Run API Java có thể gọi **featureViews.fetchFeatureValues** bằng HTTPS. Token của **Cloud Run runtime service account** được lấy qua **Application Default Credentials (ADC)**, không nhúng API key/service account JSON vào code.

### 10.1. Maven dependency

Trong ứng dụng Java 21 có Maven:

~~~xml
<!-- Ví dụ: chọn bản auth library đã kiểm tra tương thích trong BOM của dự án. -->
<dependency>
  <groupId>com.google.auth</groupId>
  <artifactId>google-auth-library-oauth2-http</artifactId>
  <version>1.40.0</version>
</dependency>
~~~

Version ví dụ là mốc cố định để trình bày, không phải latest mãi mãi; ở hệ thống thật phải rà soát phiên bản/JDK/CVE và dependency tree.

### 10.2. Java 21 HTTP client gọi Feature Store

~~~java
package lab;

import com.google.auth.oauth2.GoogleCredentials;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;

public final class FeatureReadExample {
    public static void main(String[] args) throws Exception {
        String project = required("PROJECT_ID");
        String location = required("LOCATION");
        String store = required("ONLINE_STORE");
        String view = required("FEATURE_VIEW");
        String customerId = args.length > 0 ? args[0] : "cust-101";

        // Lab: allowlist ID pattern; production: validate tenant/ownership.
        if (!customerId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid entity ID");
        }

        String endpoint = "https://" + location
                + "-aiplatform.googleapis.com/v1/projects/"
                + project + "/locations/" + location
                + "/featureOnlineStores/" + store
                + "/featureViews/" + view + ":fetchFeatureValues";

        GoogleCredentials credentials = GoogleCredentials
                .getApplicationDefault()
                .createScoped(List.of(
                    "https://www.googleapis.com/auth/cloud-platform"));
        credentials.refreshIfExpired();

        // Validation ở trên khiến việc chèn customerId vào JSON an toàn
        // trong bài lab. Production: dùng JSON library để encode payload.
        String json = "{\"data_key\":{\"key\":\"" + customerId
                + "\"},\"data_format\":\"KEY_VALUE\"}";

        HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
                .timeout(Duration.ofSeconds(5))
                .header("Authorization", "Bearer "
                        + credentials.getAccessToken().getTokenValue())
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpResponse<String> response = client.send(request,
                    HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                throw new IllegalStateException(
                    "Feature fetch HTTP " + response.statusCode());
            }

            // Chỉ demo với dữ liệu giả lập; không log raw PII production.
            System.out.println(response.body());
        }
    }

    private static String required(String name) {
        String v = System.getenv(name);
        if (v == null || v.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return v;
    }
}
~~~

**Điểm cần bổ sung khi production hóa:** tái sử dụng **HttpClient** và credential provider trong vòng đời ứng dụng (không tạo cho mỗi request), cache/access-token refresh đúng SDK, parse typed response, đo latency, deadline và retry budget; không retry 401/403 hoặc 404 vô điều kiện. Endpoint/ID được lấy từ trusted config; tránh SSRF qua URL người dùng tự cung cấp.

### 10.3. Integration với model serving

~~~mermaid
sequenceDiagram
    participant U as Caller
    participant API as Cloud Run Java service
    participant F as FeatureView Bigtable
    participant M as Vertex AI model endpoint
    U->>API: POST /predict customerId
    API->>API: Authenticate + authorize tenant/customer
    API->>F: fetchFeatureValues(customerId)
    F-->>API: spend_30d / sessions_7d / plan
    API->>API: Validate schema, freshness, missing values
    API->>M: Predict with feature vector
    M-->>API: probability/label
    API-->>U: Business-approved result
~~~

**Không gửi trực tiếp toàn bộ Feature Store response vào model** nếu schema model yêu cầu preprocessing/version khác. Cần map features theo **model signature**, kiểm tra kiểu và đơn vị, ghi metadata model/feature version, không log token hoặc PII.

### 10.4. Offline và online phải có contract

Ví dụ model v2 cần thêm **refunds_90d**, nhưng FeatureView v1 chưa đồng bộ feature này. Trước khi chuyển production traffic sang model v2, triển khai feature pipeline/schema, sync, xác minh **refunds_90d** trên các entity test, chạy canary inference rồi mới cutover. Khi rollback, giữ FeatureView/model versions cần thiết cho khách hàng còn chạy phiên bản cũ.

## 11. Đồng bộ features: scheduled, continuous và direct write

### 11.1. Những semantics không thể bỏ qua

| Tính năng | Scheduled sync | Continuous sync | Direct write |
|---|---|---|---|
| Online store | Bigtable (và Optimized cũ) | **Bigtable** | **Bigtable** |
| Nguồn FeatureView | Direct BigQuery hoặc Feature Registry | **Feature Registry + feature groups** | Ghi trực tiếp vào FeatureView |
| Lập lịch | Cron hoặc trigger thủ công | Theo cập nhật nguồn được hỗ trợ | Theo request của writer |
| Nguồn BigQuery | Bảng/view hợp lệ | Table tại region hỗ trợ | Không cần cập nhật BigQuery trước |
| UPDATE/DELETE từ BigQuery | UPDATE được phản ánh sau sync theo quy tắc; DELETE entity **không được dọn tự động** | **Chỉ records mới**; UPDATE/DELETE không đồng bộ | Không hỗ trợ xóa entity/feature |
| Độ mới | Phụ thuộc lịch + thời gian job | Phụ thuộc pipeline và điều kiện nguồn | Có thể thấp, nhưng Preview |
| Mức hỗ trợ | Chính thức theo cấu hình | Các giới hạn cụ thể | **Preview**, cần đánh giá rủi ro |

**Direct write** vào Bigtable online FeatureView hiện thuộc **Preview**, không tự ghi ngược về bảng BigQuery và không có API xóa entity hiện có. Nếu ứng dụng cần offline–online consistency, phải thiết kế cả việc cập nhật nguồn dữ liệu chính và reconciliation. [Update features in a feature view](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/featureview-direct-write).

### 11.2. Giá trị NULL và logic latest

Với feature groups có **feature_timestamp**, Feature Store thường phục vụ **non-null value mới nhất**: nếu snapshot mới có NULL, giá trị lịch sử cũ không NULL có thể vẫn được trả. Đó là semantics có chủ đích nhưng có thể trái với business contract **“NULL nghĩa là không có thông tin hiện tại”**.

Khi muốn latest-value bao gồm NULL, tài liệu yêu cầu cấu hình phù hợp, chẳng hạn **Feature Registry dense=true + Bigtable online serving + scheduled sync**. Không nên lấp NULL bằng 0 cho mọi model vì **0** là giá trị thật và **NULL** là thiếu dữ liệu.

### 11.3. Xác định freshness budget

Giả định feature pipeline từ Cloud SQL/BigQuery tạo xong sau **4 phút**, lịch sync mỗi **15 phút**, sync job mất tối đa **3 phút** trong bài toán giả định:

\[
\text{Độ trễ trong tình huống xấu gần đúng}
\leq 4+15+3 = 22\ \text{phút}
\]

Đây là **ước tính không phải SLA của Google Cloud**. Nếu business yêu cầu feature dưới 30 giây, cách đồng bộ trên không đạt dù online **lookup latency** chỉ vài chục milliseconds. Phải xác định **end-to-end freshness** từ source event đến online store, không chỉ đo thời gian fetch.

### 11.4. Theo dõi đồng bộ theo từng view

- **Sync success/failure:** có operation hoàn tất và không có finalStatus lỗi hay không.
- **Last successful sync time:** đã quá freshness SLO hay chưa.
- **Source data timestamp/availability:** record mới nhất ở BigQuery có được xử lý chưa.
- **Online sampled values:** đọc cùng entity trước/sau sync, so hash/type/NULL.
- **Schema drift:** cột bị đổi tên/xóa/type khác giữa source và FeatureView.
- **Deleted entities:** record đã bị xóa ở source nhưng còn tại online; cần deletion runbook riêng.

Không coi HTTP 200 khi fetch là bằng chứng feature hiện hành; request có thể trả **dữ liệu cũ được materialize từ lần sync trước**.

## 12. IAM, bảo mật và quyền dữ liệu

### 12.1. Những danh tính phải phân biệt

| Principal | Trách nhiệm | Kiểu quyền cần xác nhận |
|---|---|---|
| Dataset owner | Tạo bảng/features trong BigQuery | BigQuery dataset/table write/schema management |
| Feature Store admin | Tạo online store/feature view/sync | Vertex AI Feature Store Admin hoặc custom permissions |
| FeatureView service agent | Đọc bảng BigQuery để sync | BigQuery Data Viewer/jobs.create theo thiết lập |
| Cloud Run Java runtime SA | Fetch feature values | FeatureView online fetch permission trong Vertex AI |
| Model-serving SA | Gọi model endpoint | Vertex AI endpoint predict permission |
| Auditor | Xem metadata/log/cost | Quyền read-only, không cần dữ liệu thô |

**Quyền đồng bộ khác quyền fetch.** Cấp BigQuery read cho runtime SA không tự làm FeatureView sync được; cấp Vertex AI read cho service agent không tự cho nó truy vấn BigQuery table. Nếu resources ở nhiều projects, cấu hình IAM trên **đúng resource/project**, kiểm tra caller identity thực tế từ logs.

### 12.2. Kiểm soát tenant và dữ liệu nhạy cảm

- **customer_id không phải chứng cứ quyền sở hữu.** Service nhận ID từ HTTP client phải kiểm tra tenant/user authorization trước khi fetch.
- Không log toàn bộ payload features nếu có thông tin khách hàng hoặc suy luận nhạy cảm.
- Features về sức khỏe, tín dụng, hành vi nhạy cảm cần policy/consent, retention, fairness và human review phù hợp.
- Áp schema/data minimization: chỉ cho model đọc các features thật sự cần.
- Kết nối tới APIs dùng TLS và OAuth2 access token qua ADC, không hardcode token hoặc service account key.
- Nếu cần CMEK, kiểm tra hỗ trợ trên **Bigtable online store**, quyền KMS service agent và chi phí bổ sung.
- Không giả định xóa bảng BigQuery đồng nghĩa toàn bộ online copies, logs và backups bị xóa.

### 12.3. Phân chia môi trường

Dùng online stores/feature views riêng cho **dev, staging, prod**, xác định dataset/region/owner và data classification. Nếu test thay schema/feature IDs, không dùng view production đang được model serving gọi. Feature Store là dịch vụ phục vụ dữ liệu production; thay một cột có thể phá cả inference path dù model endpoint vẫn healthy.

## 13. Vận hành: latency, monitoring, quota và chi phí

### 13.1. Metric/SLO nên có

| Chỉ số | Mục đích | Cảnh báo mẫu |
|---|---|---|
| **Online fetch p50/p95/p99** | Đảm bảo request model không bị chậm | p95 vượt ngưỡng SLO |
| **QPS và HTTP error rate** | Phát hiện traffic spikes, quota | 429/5xx/timeout tăng |
| **Sync status và duration** | Đảm bảo view được refresh | 2 lần sync thất bại liên tiếp |
| **Feature age / data freshness** | Không dự đoán từ dữ liệu stale | Thời gian từ nguồn đến online > budget |
| **Missing-feature ratio** | Kiểm tra entity/schema | Missing cao bất thường |
| **Feature distribution/drift** | Đánh giá input thay đổi so với training | Phân bố chi tiêu/plan lệch baseline |
| **Online store CPU/node/storage** | Sizing backend Bigtable | Capacity/billing tăng nhanh |
| **Model inference p95/errors** | Đo cả đường phục vụ | Model endpoint có lỗi dù feature fetch OK |
| **Billing by SKU** | Phát hiện chi phí của serving và BigQuery sync | Vượt ngân sách lab/team |

**Độ trễ online read thấp không đồng nghĩa feature fresh hoặc model chính xác.** Dashboard nên hiển thị ít nhất ba mốc: source feature age, last successful sync và online request latency.

### 13.2. Quy hoạch quy mô và công suất

Giả sử Cloud Run nhận **120 requests/giây**, mỗi request cần fetch một entity và model inference. Nếu Feature Store fetch trung bình mất **20 ms** thì số fetch đang bay trung bình theo Little's Law:

\[
L = \lambda W = 120 \times 0{,}02 = 2{,}4
\]

Đó là **concurrency trung bình**, không phải headroom cho spikes/p99. Ngoài Feature Store còn có **auth, model inference, network, serialization và retries**. Load test cần đo cả end-to-end p99; không suy Bigtable node count chỉ từ công thức.

### 13.3. Bề mặt tính phí

| Dịch vụ | Nguồn phát sinh phí | Tối ưu |
|---|---|---|
| BigQuery offline data | Storage, SQL query/scan, historical snapshots | Partition/cluster, retention phù hợp |
| Feature sync | BigQuery jobs và khối lượng dữ liệu đồng bộ | Chọn lịch theo freshness, chỉ include cột cần |
| FeatureOnlineStore Bigtable | Compute nodes/autoscaling, storage/reads theo pricing | Rightsize min/max nodes, kiểm tra idle cost |
| Vertex AI/API | Feature serving operations và hạ tầng Vertex AI theo SKU | Batch/budget/quota, không retry storm |
| Cloud Run/API service | Request/CPU/memory/concurrency | Connection reuse, scale limits, timeout |
| Model endpoint | Predict compute/endpoint usage | Cache khi hợp lý, autoscaling |
| Cloud Monitoring/KMS/network | Metrics, logs, encryption, traffic | Sampling, region, data minimization |

**Không có một bảng giá “mỗi feature” cố định cho mọi kiến trúc.** Bigtable online store có thể tạo chi phí khi rảnh; scheduled sync có thể query BigQuery theo lịch. Xem [Feature Store pricing](https://cloud.google.com/vertex-ai/pricing#featurestore), [BigQuery pricing](https://cloud.google.com/bigquery/pricing) và Cloud Billing thực tế.

### 13.4. Runbook thay đổi lịch sync

1. Baseline end-to-end freshness, sync duration, online p95 và BigQuery cost.
2. Xác nhận source data update cadence; không sync mỗi phút nếu features chỉ cập nhật theo ngày.
3. Kiểm thử cron mới trên staging, đồng thời theo dõi BigQuery job quota.
4. Điều chỉnh lịch một bước, không đổi lịch + schema + model cùng lúc.
5. Theo dõi source-to-online delay và sampled entity values qua 2–3 kỳ đồng bộ.
6. Nếu tốn phí hoặc freshness không đạt, rollback cấu hình theo change record.
7. Ghi SLO, owner, retention, missing-value policy và deletion procedure.

## 14. Troubleshooting và khôi phục dịch vụ đặc trưng

### 14.1. Xác định lỗi nằm ở đâu

~~~mermaid
flowchart TD
    A["API prediction trả lỗi hoặc feature stale"] --> B{"Lỗi fetch HTTP?"}
    B -->|"401 / 403"| C["Kiểm tra ADC, runtime SA, Vertex AI IAM"]
    B -->|"404 / empty"| D["Kiểm tra entity ID, view, sync và data source"]
    B -->|"429 / 5xx"| E["Xem quota, store capacity, API logs; backoff"]
    B -->|"HTTP 200"| F{"Feature age/schema đạt?"}
    F -->|"Không"| G["Kiểm tra BigQuery source, sync status, feature definitions"]
    F -->|"Có"| H["Kiểm tra model signature, preprocessing và inference"]
    G --> I["Sửa root cause, sync/rollback, canary lại"]
    H --> I
    C --> I
    D --> I
    E --> I
~~~

| Triệu chứng | Nguyên nhân thường gặp | Xác minh/khắc phục |
|---|---|---|
| BigQuery source không thể sync | View service agent thiếu BigQuery data/jobs rights | Dataset IAM, job permissions, identity |
| FeatureOnlineStore create 403 | Operator thiếu Vertex AI permissions | IAM admin/custom role đúng project |
| Online fetch 403 | Cloud Run runtime SA không có quyền fetch | Runtime identity/permission, API auth scope |
| Resource 404 | Sai location/store/view hoặc chưa Ready | Kiểm tra resource path, creation operation |
| Fetch entity chưa từng có | Thiếu key trong BigQuery latest source | Entity ID, source rows, last sync |
| Fetch trả giá trị cũ sau UPDATE | Scheduled sync chưa chạy/đang lỗi | FeatureViewSync status và source |
| Xóa BigQuery row nhưng online vẫn trả | **Bigtable FeatureView không auto-delete entities** | Deletion runbook/recreate view đã duyệt |
| Direct source table có duplicate keys | Mỗi entity không duy nhất | Quality gate trước sync |
| Có cột feature_timestamp và lịch sử trên direct source | Vi phạm quy tắc nguồn trực tiếp | Dùng Feature Registry, không direct |
| Continuous sync không áp UPDATE | Nó chỉ đồng bộ **new records** | Chọn scheduled sync/recreate phù hợp |
| NULL online khác NULL offline | Lấy latest non-null historical value | Định nghĩa dense/NULL policy đúng |
| Online request latency cao | Store capacity, auth/network, load/QPS | p95/p99, node counts, quota, retries |
| Chi phí tăng dù QPS thấp | Online nodes/sync jobs vẫn chạy | Billing, min-node và cron review |
| Model score thay đổi sau sync | Feature version/types/units khác | Feature contract, model version, canary |
| Optimized store vẫn đang dùng | Lựa chọn cũ deprecated | Lập migration sang Bigtable trước sunset |

### 14.2. Chỉ đọc tài nguyên để chẩn đoán

~~~bash
# Chạy sau khi đã đặt API_ROOT, ONLINE_STORE, FEATURE_VIEW.
curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE"

curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW"

curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW/featureViewSyncs"
~~~

Đồng thời trong **BigQuery Studio**, kiểm tra source table có **customer_id** và giá trị đúng. Với dữ liệu thật, không đưa toàn bộ raw features, token hoặc IDs định danh vào support ticket. Ghi **correlation ID, timestamp, resource path, HTTP status, missing-field count và model version**.

### 14.3. Runbook khi model trả sai do feature stale

1. **Chặn các quyết định có rủi ro cao** hoặc dùng fallback đã được phê duyệt; không mặc định prediction hợp lệ.
2. Ghi **last successful sync**, source update timestamp và online value của các entity kiểm tra.
3. Xác định là pipeline BigQuery nguồn, FeatureView sync hay model preprocessing.
4. Nếu scheduled sync bị lỗi, sửa IAM/quota/source schema rồi trigger sync và đợi trạng thái thành công.
5. Nếu business cần xóa một entity, chặn phục vụ trước; xử lý online deletion theo runbook riêng.
6. Canary trên các entity test, so features offline–online, kiểm tra inference outputs.
7. Khôi phục traffic và ghi incident/root cause cùng guardrail tránh tái diễn.

**Không “sửa” bằng cách tạo thêm một online store mới ở production** khi chưa biết hệ thống sẽ chuyển client traffic, chịu chi phí và xử lý online data stale như thế nào.

## 15. Case study: gợi ý hỗ trợ khách hàng trên Cloud Run

### 15.1. Bối cảnh

Một doanh nghiệp SaaS có backend Java trên **Cloud Run**, dữ liệu đăng nhập/chi tiêu trong **Cloud SQL**, event streaming qua **Pub/Sub**, feature aggregations tính trong **BigQuery**. Hệ thống muốn dự đoán nhu cầu hỗ trợ của từng tài khoản khi người dùng đăng nhập. SLO: online feature fetch **p95 dưới 100 ms** (mục tiêu giả định), features phản ánh nguồn trong **30 phút** và model trả response trong ngưỡng API cho phép.

**Thiết kế:**

- BigQuery giữ **customer_features_history** để train đúng theo prediction timestamp và **customer_features_latest** để phục vụ.
- Feature Store **Bigtable** có FeatureView với **scheduled sync**; đồng bộ mỗi 15 phút nếu BigQuery pipeline/freshness budget cho phép.
- Cloud Run runtime SA chỉ có quyền fetch, model-serving principal riêng có quyền Vertex AI predict.
- Feature schema **spend_30d, sessions_7d, plan** được version hóa, có tests so khớp offline–online.
- API từ chối dự đoán hoặc dùng fallback đã chuẩn hóa nếu feature age/missing vượt ngưỡng.
- Dashboard theo dõi sync, request latency, drift, model quality và Cloud Billing.

### 15.2. Sự cố

Ngày triển khai v2, mô hình yêu cầu **tickets_90d**, nhưng FeatureView vẫn chỉ trả ba features cũ. HTTP fetch trả **200**, vậy mà model prediction **400** vì thiếu cột.

**Phân tích:** online store vẫn khỏe; lỗi nằm ở **model-feature schema contract**. Giải pháp là phát triển source pipeline/tables, cập nhật hoặc tạo FeatureView v2 tương ứng, sync và canary kiểm tra schema trước khi chuyển model traffic. Không cần tăng Bigtable nodes hoặc cấp Owner để sửa lỗi này.

### 15.3. Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng |
|---|---|
| Dữ liệu point-in-time đúng | Golden SQL tests theo event/availability time |
| Entity keys hợp lệ | Unique ID, no unexpected NULL, tenant authorization |
| Sync ổn định | Không có sync failure, last sync trong freshness budget |
| Online read đạt SLO | P95/p99 + error rate/QPS dưới tải đại diện |
| Schema cùng model signature | Type/units/feature names/version tests |
| Offline–online values khớp | So khớp sampling sau khi sync catch-up |
| Data deletion có quy trình | Chặn serving và xác minh dọn đúng |
| Quyền tối thiểu | Read-only runtime, feature sync agent đúng |
| Có rollback | Giữ version feature view/model đang phục vụ |
| Chi phí trong budget | BigQuery/Bigtable/Vertex AI/Cloud Run theo Billing |

## 16. Bài tập thực hành và đáp án

### 16.1. Bài A — So sánh các loại feature storage

**Câu hỏi:** Chọn cách thực hiện cho ba tình huống: (a) train model từ 12 tháng lịch sử, (b) trả feature theo customer ID trước khi gọi model online, (c) tìm 20 tài liệu gần nhất theo embedding.

**Đáp án:** (a) BigQuery history với point-in-time joins; (b) FeatureOnlineStore/FeatureView Bigtable; (c) Vertex AI Vector Search. Một FeatureView online không thay chức năng training history hoặc ANN retrieval.

### 16.2. Bài B — SQL tạo latest source

Tạo ba customers như mục 5 rồi kiểm tra count/unique ID. Nếu thêm **customer_id=cust-101** lần thứ hai nhưng spend khác, điều kiện nào bị phá?

**Đáp án:** FeatureView direct BigQuery source cần **mỗi entity ID duy nhất**; phải có upstream **MERGE/QUALIFY theo business timestamp** để tạo latest table, không đưa nhiều rows cùng customer vào nguồn direct.

### 16.3. Bài C — Point-in-time và late-arriving feature

Khách hàng **cust-101** có giao dịch lúc **09:00**, pipeline tính xong lúc **13:00**; mô hình cần dự đoán tại **10:00**.

**Đáp án:** dù event time 09:00, feature **không được dùng lúc 10:00** vì available_at=13:00. Truy vấn PIT cần cả feature_timestamp và available_at không sau prediction_time.

### 16.4. Bài D — Scheduled sync và độ trễ

Pipeline BigQuery mất **5 phút**, scheduled sync chạy mỗi **20 phút** và hoàn tất trong **3 phút**. Độ mới trong tình huống xấu gần đúng là bao nhiêu (bỏ qua failures)?

\[
5 + 20 + 3 = 28\ \mathrm{phút}
\]

**Đáp án:** khoảng **28 phút**, chưa tính retries, queueing và spikes. Với yêu cầu dưới 10 phút, kiến trúc này chưa đủ; không giảm chỉ online fetch timeout để giả vờ độ mới tốt hơn.

### 16.5. Bài E — DELETE không được lan truyền

Xóa **cust-102** từ BigQuery latest table và chạy manual sync. Online FeatureView vẫn có thể trả gì?

**Đáp án:** **giá trị cũ** của cust-102 vì Bigtable online serving không xóa entity record khi đồng bộ từ BigQuery. Phải áp deletion runbook và bảo vệ quyền phục vụ; chỉ BigQuery DELETE không đủ.

### 16.6. Bài F — Continuous sync

Một FeatureView dùng continuous sync qua Feature Registry. Người vận hành thay giá trị một record đã có trong BigQuery rồi kỳ vọng online update.

**Đáp án:** sai kỳ vọng: continuous sync chỉ đồng bộ **new records**, không update/delete records đã có. Nếu cần cập nhật values/NULL, phải chọn kiểu đồng bộ và cấu hình data nguồn phù hợp hoặc thiết kế ghi trực tiếp với các giới hạn Preview.

### 16.7. Bài G — Quyền truy cập

Cloud Run SA có quyền online fetch, nhưng FeatureView sync báo BigQuery Access Denied. Có nên cấp Vertex AI Admin cho Cloud Run SA?

**Đáp án:** không. Lỗi xảy ra ở **sync identity → BigQuery source**. Phải xác định dedicated/default FeatureView service account và quyền BigQuery data/job; Cloud Run SA không sửa được lỗi đó.

### 16.8. Bài H — Tổng chi phí

Online store vẫn có Bigtable nodes dù chỉ 10 request/ngày; sync mỗi phút làm nhiều BigQuery queries nhưng dữ liệu nguồn chỉ được cập nhật mỗi 6 giờ.

**Đáp án:** rà soát min nodes/online store necessity, giảm tần suất sync theo actual freshness SLO, dùng BigQuery batch khi online SLA không cần thiết, và đối chiếu Billing by SKU. Không xóa production store khi còn ứng dụng sử dụng.

### 16.9. Biên bản lab mẫu

~~~text
PROJECT_ID / LOCATION / DATASET / OWNER:
FEATURE_SOURCE_TABLE / ENTITY_ID_COLUMNS:
UNIQUE_ID_CHECK / NULL_CHECK:
POINT_IN_TIME_SQL_RESULT:
ONLINE_STORE_ID / TYPE / NODE_BUDGET:
FEATURE_VIEW_ID / SOURCE_URI / SYNC_CRON:
FEATURE_VIEW_SA / BIGQUERY_IAM / FETCH_IAM:
FIRST_SYNC_ID / FINAL_STATUS / LAST_SUCCESS:
FETCH_CUST_101 / FETCH_UNKNOWN_ENTITY:
BIGQUERY_UPDATE_VALUE / ONLINE_AFTER_SYNC:
FRESHNESS_SLO / ONLINE_P95 / MISSING_RATIO:
MODEL_SCHEMA_VERSION / CANARY_RESULT:
DELETION_RUNBOOK / RETENTION_POLICY:
COST_BREAKDOWN / CLEANUP / OPEN_ISSUES:
~~~

Chỉ báo cáo PASS khi có dữ liệu chạy thực tế. Nếu chưa có project được cấp quyền, ghi **NOT_EXECUTED** cho phần Cloud APIs, không tự nhận online serving đã được triển khai.

## 17. Dọn lab, kiểm tra trước khi xóa và nguồn tham khảo

### 17.1. Xác minh quyền sở hữu

Bảng BigQuery ví dụ có expiration **7 ngày**, nhưng **FeatureView và FeatureOnlineStore không tự biến mất khi bảng nguồn hết hạn**. Nếu lab tạo Bigtable online store, online compute/storage có thể tiếp tục bị tính phí. Không để lại store vì nghĩ dữ liệu BigQuery sẽ tự hết hạn.

Trước khi dọn, kiểm tra:

~~~bash
# CHỈ ĐỌC: dùng đúng project/location/online store/view trong lab.
curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE"

curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW"

bq --project_id="$PROJECT_ID" show \
  "$PROJECT_ID:feature_lab.customer_features_latest"
~~~

**Dừng các model-serving clients/scheduled sync consumers** trước khi xóa view, xác nhận không có nhóm khác dùng chung online store và review chính sách retention/deletion.

### 17.2. Xóa đúng tài nguyên mình tạo (destructive)

Các lệnh sau minh họa cleanup **trên project lab đã được owner duyệt**, không dùng trong production. Ghi tên resource thực và đọc xác nhận trước mỗi bước:

~~~bash
# XÓA THẬT FeatureView lab, xóa dữ liệu online của view đó.
curl -f -sS -X DELETE \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW"

# CHỈ sau khi view đã bị xóa hoàn toàn, và store không có views khác:
curl -f -sS -X DELETE \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE"
~~~

Delete APIs có thể trả **long-running operations**; cần theo dõi cho tới khi hoàn tất, không coi request được chấp nhận là data online đã biến mất ngay. Sau đó DBA/data owner có thể xóa bảng BigQuery **customer_features_latest** và dataset lab nếu không còn phụ thuộc. Không xóa dataset shared, resource registry/feature groups của người khác, service agents hay KMS key chung.

**Ghi chú về deletion:** nếu mục tiêu là thực hiện quyền xóa dữ liệu khách hàng, cần xác minh cả BigQuery history, backups, FeatureViews khác, model logs, serving caches và chính sách pháp lý — **không** chỉ chạy DELETE ở một resource.

### 17.3. Tài liệu chính thức

- [Feature Store overview — Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/overview)
- [Prepare BigQuery feature data source](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/prepare-data-source)
- [Online serving types và Optimized deprecation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/online-serving-types)
- [Create a FeatureOnlineStore](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-onlinestore)
- [Create a FeatureView và các chế độ đồng bộ](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-featureview)
- [Start a manual sync](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/sync-data)
- [List FeatureView sync operations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/list-data-syncs)
- [Serve feature values using Bigtable](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/serve-feature-values)
- [Direct write feature values — Preview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/featureview-direct-write)
- [BigQuery feature serving và point-in-time correctness](https://docs.cloud.google.com/bigquery/docs/feature-serving)
- [Vertex AI IAM access control](https://docs.cloud.google.com/vertex-ai/docs/general/access-control)
- [BigQuery security overview](https://docs.cloud.google.com/bigquery/docs/security-overview)
- [Google Cloud Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)

**Checklist kết thúc:** xác định feature contract → offline history + latest table → kiểm tra entity uniqueness → point-in-time training joins → chọn **Bigtable online serving** → FeatureView + sync IAM → sync thành công → fetch/validate schema → đo freshness và p95/p99 → xây deletion/rollback policy → theo dõi Billing → cleanup đúng ownership.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** bài học sử dụng **BigQuery làm offline source**, **Vertex AI Feature Store** để materialize/serve features, **Bigtable** cho online reads, và **Cloud Run Java API/Vertex AI model endpoint** để dự đoán. IAM, VPC/secure access, Cloud Monitoring và Cloud Billing là các lớp vận hành xuyên suốt. **Feature Store giúp chuẩn hóa đường cấp feature, nhưng không tự sửa skew, source data lỗi, quyền sai hoặc yêu cầu xóa dữ liệu chưa có runbook.**












