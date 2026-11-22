# Quản lý datasets và chuẩn bị dữ liệu huấn luyện trên Vertex AI

Một doanh nghiệp bán lẻ vận hành API đơn hàng trên **Cloud Run**, xử lý dữ liệu bằng **Dataflow**, lưu lịch sử ở **Cloud Storage/BigQuery**, và muốn huấn luyện mô hình dự đoán **đơn hàng có khả năng yêu cầu trả hàng trong 30 ngày sau giao thành công**. Dữ liệu đã có không có nghĩa là **tập huấn luyện** đã sẵn sàng: có thể thiếu nhãn, dữ liệu trùng, customer IDs lộ thông tin cá nhân, hoặc các features chứa thông tin chỉ xuất hiện *sau thời điểm dự đoán*. Khi đó mô hình có thể đạt điểm test cao nhưng thất bại trên production.

Bài học thuộc chương **Vertex AI và học máy**, mô-đun **CLOUD_PROVIDERS_GCP**. Trọng tâm là chọn nơi lưu dữ liệu, quản lý managed datasets, kiểm tra chất lượng, tạo nhãn, chia tập, chống data leakage và tái lập các phiên bản huấn luyện. Ví dụ gắn với IAM, Cloud Storage, BigQuery, CI/CD, độ tin cậy và chi phí; chưa triển khai thuật toán huấn luyện chuyên sâu.

**Tên sản phẩm năm 2026:** Google Cloud đã đổi tên **Vertex AI Platform** thành **Gemini Enterprise Agent Platform** (Agent Platform). Trong tài liệu/API hiện hành, chức năng datasets/training có thể xuất hiện dưới Agent Platform, trong khi SDK Python `google-cloud-aiplatform`, `aiplatform.googleapis.com` và nhiều resource names vẫn giữ tiền tố cũ. Bài dùng “Vertex AI/Agent Platform” để tương thích đề bài và hướng dẫn hiện hành. Tham khảo [bảng đổi tên chính thức](https://docs.cloud.google.com/gemini-enterprise-agent-platform/vertex-ai-name-changes).

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **raw data**, **curated training table**, **managed Dataset resource**, **data snapshot** và **model artifact**.
2. Chọn nguồn dữ liệu **BigQuery**, **Cloud Storage**, hoặc managed dataset theo **AutoML** so với **custom training**.
3. Thiết kế label/feature contract tại **thời điểm dự đoán**, phát hiện target leakage, temporal leakage, entity leakage và training-serving skew.
4. Chuẩn hóa dữ liệu số, phân loại, văn bản, ảnh; kiểm tra missing values, duplicates, label noise, imbalance và quyền sử dụng dữ liệu.
5. Chia **train/validation/test** theo random, thời gian hoặc nhóm thực thể và giữ test set không tham gia tuning.
6. Dùng BigQuery SQL chuẩn bị bảng, Python SDK liên kết managed tabular dataset với nguồn BigQuery, và xác minh nguồn bằng CLI.
7. Ghi nhận phiên bản, lineage, quyền truy cập, vùng dữ liệu, SLO và chi phí để tái lập thí nghiệm.

## 2. Dataset nằm ở đâu trong vòng đời ML?

~~~mermaid
flowchart LR
    SRC["Cloud SQL / Spanner / Pub/Sub / GCS"] --> RAW["Raw events + source snapshots"]
    RAW --> CLEAN["BigQuery/Dataflow: validate, join, dedupe"]
    CLEAN --> CUR["Curated feature-label dataset"]
    CUR --> SPLIT["Train / validation / test"]
    SPLIT --> MAN["Managed Dataset (khi cần)"]
    SPLIT --> CUSTOM["Custom training đọc BQ/GCS trực tiếp"]
    MAN --> TRAIN["AutoML hoặc training phù hợp"]
    CUSTOM --> TRAIN
    TRAIN --> REG["Model Registry + evaluation"]
    META["Metadata/version/lineage + IAM"] -.-> CUR
    META -.-> MAN
    META -.-> TRAIN
~~~

| Thành phần | Chứa gì? | Có phải “dataset resource” trên Agent Platform? |
| --- | --- | --- |
| **Nguồn giao dịch** | Đơn hàng, payment, thời gian giao, returns. | Không; dữ liệu sống ở hệ thống nguồn. |
| **Raw layer** | Event gốc và dấu thời gian ingest, ID, schema version. | Không; thường nằm ở GCS/BigQuery. |
| **Curated table** | Mỗi dòng một mẫu, features và label đã kiểm chứng. | Không; đây là **bảng thực tế** để huấn luyện. |
| **Managed Dataset** | Resource mô tả tập dữ liệu, nhiệm vụ và nguồn nhập/liên kết. | **Có**, dùng trong AutoML và khi thích hợp. |
| **Training snapshot** | Tập đầu vào được chốt cho một run. | Có thể là snapshot lúc bắt đầu training hoặc artifact được pin riêng. |
| **Model artifact** | Weights, metrics và metadata từ một run. | Không phải dataset; quản lý bằng Model Registry/artifact store. |

**Đừng đồng nhất “tạo dataset” với “sao chép và đóng băng dữ liệu”.** Với **tabular managed dataset**, Agent Platform **liên kết** bảng/view BigQuery hoặc CSV GCS; khi nguồn thay đổi, training run *về sau* có thể sử dụng dữ liệu mới. Dịch vụ tạo snapshot phục vụ training **khi run bắt đầu**, không phải mặc định bất biến từ thời điểm resource dataset được tạo. Với **image datasets**, dữ liệu/annotations được nhập và có cách quản lý khác. Muốn tái lập run trong nhiều tháng, hãy quản lý **nguồn đã pin** (BigQuery table snapshot/version, GCS object generation hoặc đường dẫn immutable), code, thời điểm cutoff và cấu hình split. [Nguồn: tạo tabular dataset](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/classification-regression/create-dataset).

## 3. Chọn nguồn và loại dataset

### 3.1. Tabular, image, text, video có workflow khác nhau

| Bài toán | Dạng dữ liệu | Nguồn và cách quản lý phù hợp |
| --- | --- | --- |
| Dự đoán đơn trả hàng | Tabular: một dòng/đơn, label 0/1 | BigQuery table/view hoặc CSV GCS, managed tabular dataset cho AutoML. |
| Dự báo nhu cầu SKU | Time series: SKU×ngày, target và covariates | BigQuery/CSV; kiểm tra frequency, historical windows và forecasting constraints. |
| Phân loại ảnh sản phẩm | Ảnh + nhãn loại sản phẩm | Objects GCS và CSV/JSONL manifest theo **import schema** của objective. |
| Phát hiện lỗi ảnh | Ảnh + bounding boxes | GCS, labels và annotation manifest đúng schema detection. |
| Phân loại phản hồi khách hàng | Text + label/class | Text dataset/manifest hoặc custom training pipeline. |
| Huấn luyện mô hình tùy chỉnh | Tensor/chunks/features tùy framework | Custom training đọc BigQuery, GCS, TFRecord/Parquet/...; managed Dataset **không bắt buộc**. |

**AutoML** thường cần managed dataset cho objective được hỗ trợ; **custom training** có thể dùng managed dataset hoặc đọc nguồn trực tiếp theo code. Không bắt buộc import mọi thứ vào một managed dataset nếu training container đã có data pipeline versioned. Tính khả dụng của một objective, import format, region và SDK có thể thay đổi; kiểm tra [managed datasets overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/datasets/overview).

### 3.2. BigQuery hay Cloud Storage?

| Tiêu chí | BigQuery | Cloud Storage |
| --- | --- | --- |
| Truy vấn, join, làm sạch tabular | Rất phù hợp với GoogleSQL, partition, quality SQL. | Phù hợp file CSV, Parquet, TFRecord; cần engine đọc/biến đổi. |
| Versioning | Snapshot tables, bản materialized theo run, kiểm soát query. | Object generations hoặc immutable prefix + manifest/checksums. |
| Schema | Table schema, constraints kiểm chứng qua queries. | Phụ thuộc file format/schema riêng. |
| Dữ liệu không cấu trúc | Có thể chứa tham chiếu/metadata. | Thường lưu ảnh/video/text files và annotations. |
| Chi phí chính | Storage + query/slot processing. | Storage + operations/egress + compute khi xử lý. |
| Quản trị | BigQuery IAM, row/column policies, authorized views. | Bucket/object IAM, VPC SC, encryption/retention. |

Với dữ liệu cá nhân/nhạy cảm, cân nhắc **giảm trường đầu vào**, hạn chế xuất raw PII và phân quyền riêng cho data prep, training, analyst và service agent; giữ vùng dữ liệu phù hợp với chính sách.

## 4. Định nghĩa label và feature theo thời điểm dự đoán

### 4.1. Mô hình ví dụ: yêu cầu trả hàng trong 30 ngày

Giả sử dự đoán được thực hiện **ngay khi đơn giao thành công**. Vì vậy:

- **Đơn vị mẫu (grain):** một dòng cho mỗi `order_id` đã giao thành công.
- **Prediction time:** `delivered_at`.
- **Target:** `return_within_30d = 1` nếu có yêu cầu trả hàng hợp lệ trong khoảng `[delivered_at, delivered_at + 30 ngày]`; còn lại 0 **chỉ khi đã đủ 30 ngày quan sát**.
- **Features hợp lệ ở prediction time:** tổng đơn, số mặt hàng, phương thức vận chuyển, vùng giao, số ngày giao, thông tin lịch sử trước `delivered_at`.
- **Features không hợp lệ:** `return_requested_at`, `refund_issued`, trạng thái CSKH sau giao, hoặc bất kỳ thống kê nào nhìn về tương lai.

| Trường | Vai trò | Có dùng làm feature? |
| --- | --- | --- |
| `order_id` | ID để đối soát/dedup | Không làm tín hiệu dự đoán mặc định. |
| `delivered_at` | Mốc dự đoán và phân chia thời gian | Có thể trích ngày/giờ phù hợp, không cho leakage. |
| `customer_id` | Grouping/audit nếu cần | Không thả trực tiếp PII/high-cardinality ID vào AutoML vô kiểm soát. |
| `item_count`, `subtotal_vnd` | Features biết trước/khi giao | Có, với schema và đơn vị nhất quán. |
| `shipping_method`, `region` | Categorical features | Có, kiểm tra danh mục lạ/missing. |
| `delivery_duration_days` | Feature biết tại giao | Có nếu inference thực hiện lúc giao. |
| `return_requested_at` | Xây target cho dữ liệu lịch sử | **Không** được đưa vào feature. |
| `return_within_30d` | Nhãn (target) | Chỉ là target, không vừa target vừa predictor. |
| `split` | TRAIN/VALIDATE/TEST | Metadata chia tập, không phải feature. |

**Quy tắc kiểm tra:** với mỗi feature, hỏi *“nếu hệ thống phải dự đoán đúng thời điểm `delivered_at`, giá trị này đã tồn tại và truy cập được chưa?”* Nếu câu trả lời không chắc, loại ra hoặc tái xây dựng bằng **point-in-time join**.

### 4.2. Tránh nhãn chưa đủ thời gian quan sát

Nếu ngày chạy pipeline là `2026-11-01`, một đơn giao ngày `2026-10-25` vẫn có thể bị trả trong tháng 11. **Không được gán 0 chỉ vì đến hôm nay chưa thấy yêu cầu trả hàng**. Chọn `as_of` cố định, chỉ lấy đơn đã giao **ít nhất 30 ngày trước cutoff**, và cân nhắc thêm buffer cho hệ thống gửi sự kiện muộn. Với đơn huỷ/chưa giao, cần định nghĩa rõ **ngoài phạm vi** hay một label khác.

### 4.3. Các dạng leakage phổ biến

| Leakage | Ví dụ | Cách ngăn |
| --- | --- | --- |
| **Target leakage** | Cột `refund_status` làm predictor cho việc trả hàng. | Phân định features và target tại prediction time. |
| **Temporal leakage** | Dùng tổng số complaints *tới hiện tại* để dự đoán một đơn giao tháng trước. | Point-in-time features, join với `event_time <= delivered_at`. |
| **Entity leakage** | Một người/thiết bị gần như trùng lặp nằm ở train và test khi mục tiêu là người dùng mới. | Group split theo customer/device nếu đúng evaluation goal. |
| **Duplicate leakage** | Cùng order xuất hiện hai lần với IDs khác nhau. | Dedup business key trước khi chia. |
| **Preprocessing leakage** | Mean/std, vocabulary, imputers được fit trên tất cả train+test. | Fit preprocessing **chỉ trên TRAIN**, apply trên VAL/TEST và inference. |
| **Label leakage từ pipeline** | Data prep join dữ liệu hoàn tiền và vô tình giữ cột hoàn tiền vào features. | Whitelist feature columns và kiểm tra schema tự động. |

**Training-serving skew** là khác biệt giữa cách tính feature khi training và cách tính tại inference. Ví dụ dùng trung bình spend 90 ngày trong training nhưng 7 ngày khi serving; mô hình có thể giảm chất lượng dù không có leakage trực tiếp. Dùng chung feature definitions, cutoff logic và phép biến đổi hoặc kiểm thử tương đương.

## 5. Làm sạch và kiểm tra dữ liệu trước khi nhập

### 5.1. Hợp đồng dữ liệu tối thiểu

| Kiểm tra | Ví dụ | Phản ứng |
| --- | --- | --- |
| **Schema/type** | `subtotal_vnd` là `NUMERIC`, `delivered_at` là `TIMESTAMP`, label là 0/1. | Chặn schema drift hoặc chuyển qua bước normalize được phê duyệt. |
| **Completeness** | `order_id`, thời điểm giao, nhãn không null; `shipping_method` có thể null. | Loại, impute hoặc gắn missing flag tùy trường. |
| **Uniqueness** | Một `order_id` không được tạo nhiều training rows. | Dedupe bằng quy tắc business, không `DISTINCT` mù. |
| **Validity** | `item_count > 0`, `subtotal_vnd >= 0`, `created_at <= delivered_at`. | Quarantine giá trị không hợp lệ và đối chiếu nguồn. |
| **Consistency** | Đồng tiền VND, timezone UTC, category codes thống nhất. | Chuyển đổi theo quy tắc có version; không “ước lượng” tiền tệ. |
| **Distribution** | Tỷ lệ nhãn 1, vùng giao, mùa cao điểm. | Theo dõi imbalance và sample-selection bias. |
| **Freshness** | Dữ liệu đã đủ 30 ngày để gán nhãn. | Không coi label chưa quan sát là 0. |
| **Privacy/consent** | Không dùng địa chỉ đầy đủ, email, mã định danh nếu không có cơ sở. | Giảm/minimize data, masked views, policy reviews. |

Nên thực hiện **profiling trên dữ liệu thô trước**, sau đó lưu **test results trên curated data**, thay vì âm thầm bỏ tất cả rows không hợp lệ mà không thống kê tỷ lệ bị loại. Việc bỏ dữ liệu có thể thiên lệch: ví dụ loại mọi đơn chưa giao có thể làm tập training chỉ còn đơn có trải nghiệm tốt.

### 5.2. Missing values, outliers và categorical features

- **Numeric:** đo null %, khoảng giá trị, percentiles, outliers; không tự clamp mọi đơn lớn về trung bình. Với model cần imputation, fit median/mean trên TRAIN hoặc sử dụng transformations của AutoML.
- **Categorical:** chuẩn hóa spelling/codes, tách `UNKNOWN` với giá trị thật, xử lý category mới ở inference; không one-hot thủ công nếu AutoML đã quản lý transformation phù hợp.
- **Time:** phân biệt timezone, daylight saving; `DATE` có thể làm mất giờ/phút quan trọng, giữ timestamp gốc khi cần.
- **Text:** loại secrets, thông tin cá nhân và boilerplate nhạy cảm; kiểm tra ngôn ngữ, encoding và nhãn.
- **Class imbalance:** luôn đo **tỷ lệ dương/âm theo từng split**; accuracy có thể gây hiểu nhầm nếu chỉ 2% đơn yêu cầu trả hàng. Dùng precision/recall, PR-AUC, confusion matrix theo business costs thay vì chỉ accuracy.

Trong **tabular AutoML**, nhiều bước biến đổi categorical/numeric/text được hệ thống thực hiện; không tiền xử lý quá mức khi làm mất tín hiệu. Nhưng **loại PII, sửa nhãn, chống leakage và giữ prediction-time contract** vẫn thuộc trách nhiệm đội dữ liệu. [Thực hành tabular data](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/bp-tabular).

### 5.3. Chất lượng nhãn với ảnh và văn bản

Ví dụ phân loại ảnh sản phẩm thành `shoe`, `shirt`, `bag`:

- Xác định nhãn có **mutually exclusive** (single-label) hay một ảnh được gắn nhiều nhãn (multi-label).
- Viết **annotation guidelines** với ví dụ ranh giới, ảnh mờ, nhiều vật thể, hàng bị che.
- Lấy mẫu review gán nhãn giữa hai người; đo disagreement và sửa hướng dẫn trước khi gắn hàng chục nghìn ảnh.
- Phát hiện ảnh giống hệt/near-duplicate giữa train và test để tránh đánh giá ảo.
- Kiểm tra tính đại diện theo thiết bị, ánh sáng, khu vực; test phải gần với dữ liệu triển khai.
- Với object detection, cần **bounding boxes** đúng định dạng objective; classification label không đủ.

Managed image dataset dùng **GCS URIs và manifest CSV/JSONL** theo import schema. Ví dụ CSV ba cột cho **single-label image classification**:

~~~csv
training,gs://REPLACE_BUCKET/images/shoe-001.jpg,shoe
validation,gs://REPLACE_BUCKET/images/shirt-101.jpg,shirt
test,gs://REPLACE_BUCKET/images/bag-090.jpg,bag
~~~

Đây là **format minh họa**, các objects chưa tồn tại; không dùng ảnh công ty/khách hàng khi thiếu quyền. Cột đầu là split theo format objective, không phải `customer_id`; kiểm tra schema ảnh/classification và dữ liệu URL trước khi import. Nếu import JSONL, cấu trúc field và `annotation_set_name` khác CSV. [Chuẩn bị image classification data](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/image-data/classification/prepare-data).

## 6. Train, validation và test: chia thế nào cho đúng?

### 6.1. Mục đích của mỗi split

| Tập | Dùng để làm gì? | Tránh điều gì? |
| --- | --- | --- |
| **TRAIN** | Fit model parameters và preprocessing statistics. | Chứa dữ liệu tương lai hoặc test labels. |
| **VALIDATION** | Chọn feature, model/hyperparameters và threshold. | Điều chỉnh quá nhiều lần làm overfit vào validation. |
| **TEST** | Đánh giá cuối trên dữ liệu chưa tham gia lựa chọn. | Dùng để quyết định model rồi tuyên bố test độc lập. |

Với tabular AutoML classification/regression, mặc định công cụ thường chia **80%/10%/10% ngẫu nhiên**, và cho phép **manual/timestamp split**. Đó là **mặc định dịch vụ**, không phải tỷ lệ tối ưu cho mọi bài toán. [Data splits](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/data-splits).

### 6.2. Ba chiến lược

| Chiến lược | Phù hợp | Cẩn thận |
| --- | --- | --- |
| **Random split** | Các mẫu gần độc lập và dữ liệu ổn định theo thời gian. | Leakage giữa người dùng hoặc thời gian; trùng ảnh/document. |
| **Chronological split** | Dự đoán trên **tương lai**: trả hàng, nhu cầu, giao hàng. | Giữ label maturity và gap; test chỉ chứa thời điểm sau train. |
| **Group/entity split** | Đánh giá với khách hàng, thiết bị, bệnh nhân hoặc seller **chưa từng thấy**. | Group ID không được xuất hiện ở cả train và test; phân phối class có thể lệch. |

**Mục tiêu evaluation quyết định cách split.** Nếu production dự đoán những **đơn mới của cùng khách hàng cũ**, chronological split là bước cơ bản. Nếu triển khai cho **khách hàng hoàn toàn mới**, cần test group split theo customer, thậm chí kết hợp thời gian. Với time series và forecasting, cần train trên quá khứ, validation/test trên những khoảng tương lai không chồng chéo; tránh tính rolling features qua ranh giới không hợp lệ.

### 6.3. Một ví dụ SQL hoàn toàn tự chứa

Chạy trong **BigQuery SQL editor**; `WITH` chỉ tạo dữ liệu **trong truy vấn**, không ghi bảng hay dùng dữ liệu thật. Các nhãn được giả định là đã quan sát đủ thời gian:

~~~sql
WITH samples AS (
  SELECT 'O-01' AS order_id, DATE '2026-05-01' AS delivered_date,
         120000 AS subtotal_vnd, 0 AS return_within_30d UNION ALL
  SELECT 'O-02', DATE '2026-05-18', 240000, 1 UNION ALL
  SELECT 'O-03', DATE '2026-06-07', 90000, 0 UNION ALL
  SELECT 'O-04', DATE '2026-06-25', 330000, 0 UNION ALL
  SELECT 'O-05', DATE '2026-07-12', 510000, 1 UNION ALL
  SELECT 'O-06', DATE '2026-07-29', 78000, 0 UNION ALL
  SELECT 'O-07', DATE '2026-08-09', 425000, 1 UNION ALL
  SELECT 'O-08', DATE '2026-08-26', 150000, 0
),
split_data AS (
  SELECT *,
    CASE
      WHEN delivered_date < DATE '2026-07-01' THEN 'TRAIN'
      WHEN delivered_date < DATE '2026-08-01' THEN 'VALIDATE'
      ELSE 'TEST'
    END AS data_split
  FROM samples
)
SELECT data_split, COUNT(*) AS rows,
       COUNTIF(return_within_30d = 1) AS positive_labels,
       ROUND(AVG(return_within_30d), 3) AS positive_rate
FROM split_data
GROUP BY data_split
ORDER BY data_split;
~~~

Kết quả mong đợi: **TRAIN 4 dòng/1 positive; VALIDATE 2 dòng/1 positive; TEST 2 dòng/1 positive**. Đây là **toy dataset 8 dòng để hiểu logic**, hoàn toàn không đủ huấn luyện model thực tế; chia theo thời gian làm tỷ lệ classes khác nhau, cần đánh giá đại diện trên dữ liệu lớn hơn. `data_split` không được đưa vào features.

### 6.4. Tránh thay đổi test set theo mỗi lần chạy

- Ghi **chính xác thời gian cutoff**, danh sách test entity IDs hoặc một bảng immutable cho split.
- Seed chỉ giúp random split tái lập **khi nguồn và thứ tự/thuật toán cố định**; không thay thế version dữ liệu.
- Giữ các event trùng/mối quan hệ cùng thực thể trong cùng split nếu cần chống leakage.
- Không tham gia tuning trên test set; sau khi test thất bại và quyết định sửa model, cần cân nhắc **một evaluation set mới** nếu đã “nhìn” nhiều lần.
- Các thống kê normalization, target encoding và feature selection phải fit từ TRAIN (hoặc dùng đúng pipeline transformations của hệ thống).

## 7. Chuẩn bị bảng BigQuery cho managed tabular dataset

### 7.1. SQL pipeline có cutoff và danh sách features

Giả sử **dataset lab đã có** hai bảng nguồn:

- `retail-lab.raw.orders`: `order_id`, `customer_id`, `created_at`, `delivered_at`, `item_count`, `subtotal_vnd`, `shipping_method`, `destination_zone`, `order_state`.
- `retail-lab.raw.return_requests`: `order_id`, `requested_at`, `request_status`.

Mục tiêu là một mẫu/đơn *đã giao*, prediction time tại `delivered_at`. SQL dưới đây là **template ghi bảng thật**, chỉ chạy khi đã kiểm tra schema/permissions, yêu cầu chấp thuận và **dữ liệu nguồn là lab**, không copy nguyên lên production:

~~~sql
-- WRITE: tạo/thay bảng training chuẩn hóa, có thể phát sinh phí BigQuery.
DECLARE as_of TIMESTAMP DEFAULT TIMESTAMP '2026-11-01 00:00:00+00';

CREATE OR REPLACE TABLE `retail-lab.ml_data.return_training_v1`
PARTITION BY DATE(delivered_at)
CLUSTER BY data_split
AS
WITH first_return AS (
  SELECT order_id,
         MIN(requested_at) AS first_request_at
  FROM `retail-lab.raw.return_requests`
  WHERE request_status = 'VALID'
    AND requested_at <= as_of
  GROUP BY order_id
),
eligible_orders AS (
  SELECT order_id, customer_id, created_at, delivered_at,
         item_count, subtotal_vnd, shipping_method, destination_zone
  FROM `retail-lab.raw.orders`
  WHERE order_state = 'DELIVERED'
    AND delivered_at IS NOT NULL
    AND delivered_at <= TIMESTAMP_SUB(as_of, INTERVAL 35 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id ORDER BY delivered_at DESC
  ) = 1
)
SELECT
  o.order_id,                  -- audit ID; không làm feature
  o.customer_id,               -- split/group ID; không làm feature mặc định
  o.delivered_at,              -- prediction timestamp
  o.item_count,
  o.subtotal_vnd,
  o.shipping_method,
  o.destination_zone,
  TIMESTAMP_DIFF(o.delivered_at, o.created_at, HOUR)
    AS delivery_duration_hours,
  IF(r.first_request_at BETWEEN o.delivered_at
       AND TIMESTAMP_ADD(o.delivered_at, INTERVAL 30 DAY), 1, 0)
    AS return_within_30d,
  CASE
    WHEN DATE(o.delivered_at) < DATE '2026-07-01' THEN 'TRAIN'
    WHEN DATE(o.delivered_at) < DATE '2026-08-01' THEN 'VALIDATE'
    ELSE 'TEST'
  END AS data_split
FROM eligible_orders AS o
LEFT JOIN first_return AS r USING (order_id)
WHERE o.item_count > 0
  AND o.subtotal_vnd >= 0;
~~~

**Giới hạn của ví dụ:** giả sử `order_state`, `delivered_at`, trả hàng hợp lệ và event delivery đã được đồng bộ trước `as_of`; buffer **35 ngày** là quy ước lab (30 ngày label + 5 ngày ingest lag). Nếu `order_state` có thể đổi sau giao, điều kiện `order_state='DELIVERED'` ở thời điểm hiện tại có thể **loại oan đơn đã được giao rồi hoàn tất trả hàng**. Trong production, phải lấy **event lịch sử/giao thành công bất biến**, không lọc từ trạng thái hiện tại làm sai sample selection. Tương tự, `MIN(requested_at)` chỉ đúng nếu business định nghĩa một return hợp lệ đầu tiên là căn cứ; với nhiều events/hủy, cần mô hình hóa riêng.

`CREATE OR REPLACE TABLE` có thể xóa dữ liệu, permission/resource metadata hoặc downstream dependencies; ưu tiên **bảng version mới** (`return_training_20261101_v1`) hoặc snapshot có approval, không ghi đè một bảng được training job khác sử dụng.

### 7.2. Kiểm thử dữ liệu sau khi tạo bảng

~~~sql
-- READ-ONLY: toàn bộ truy vấn sử dụng bảng lab đã tạo.
SELECT data_split, COUNT(*) AS n,
       COUNTIF(return_within_30d=1) AS positives,
       COUNTIF(item_count IS NULL) AS missing_item_count
FROM `retail-lab.ml_data.return_training_v1`
GROUP BY data_split ORDER BY data_split;

-- READ-ONLY: một dòng cho mỗi order.
SELECT COUNT(*) - COUNT(DISTINCT order_id) AS duplicate_order_rows
FROM `retail-lab.ml_data.return_training_v1`;

-- READ-ONLY: xác định dữ liệu lỗi và kiểm tra cột có nguy cơ leakage.
SELECT COUNTIF(delivery_duration_hours < 0) AS bad_delivery_duration,
       COUNTIF(subtotal_vnd < 0) AS bad_amount,
       COUNTIF(return_within_30d NOT IN (0, 1)) AS bad_label
FROM `retail-lab.ml_data.return_training_v1`;
~~~

Đối với dữ liệu thật, test thêm **NULL label, ID rỗng, class ratio theo tháng/vùng, outliers, kiểm tra thời gian feature**, và test rằng feature set không chứa `return_requested_at` hoặc `refund_status`. Dù test SQL đạt, pipeline vẫn cần kiểm chứng schema của source, nguồn PII và point-in-time correctness.

## 8. Tạo managed tabular dataset trên Vertex AI/Agent Platform

### 8.1. Console workflow

1. Trong Google Cloud console, mở **Agent Platform → Datasets → Create**.
2. Chọn **Tabular → Regression/Classification**, nhập tên dataset có version và chọn **region hỗ trợ**.
3. Liên kết bảng/view BigQuery `retail-lab.ml_data.return_training_v1` hoặc CSV từ Cloud Storage.
4. Xác minh dataset/nguồn hiện đúng số rows, schema và tỷ lệ NULL; kiểm tra service agent có quyền **đọc dữ liệu nguồn**.
5. Khi bắt đầu AutoML training, chọn `return_within_30d` làm **target**, chọn `data_split` làm **predefined/manual split column** (hoặc thiết lập timestamp split theo mục tiêu), và **loại ID, split column cùng mọi label-derived fields khỏi feature list**.
6. Ghi model/training job ID, dataset resource ID, BigQuery snapshot identifier, nhãn/version, thời điểm lấy dữ liệu và metric evaluation.

**Managed dataset không tự xác định feature nào là rò rỉ**. Tên `return_within_30d` là label, còn `order_id`, `customer_id`, `data_split` cần được xử lý như metadata hoặc cột loại trừ khi chọn features. Tạo Dataset resource và **huấn luyện model** là hai thao tác khác nhau, cả hai có thể tạo resource/chi phí.

### 8.2. Python SDK với BigQuery

Ví dụ **mã mẫu, không chạy trong repository bài học**. Cài phiên bản `google-cloud-aiplatform` đã được tổ chức kiểm thử và thiết lập **Application Default Credentials (ADC)**. Bảng BigQuery lab cần tồn tại; region của nguồn phải đáp ứng yêu cầu vị trí datasets của dịch vụ.

~~~python
from google.cloud import aiplatform

PROJECT = "retail-lab"
REGION = "us-central1"  # Chọn region thực sự hỗ trợ, kiểm tra data location.
SOURCE = "bq://retail-lab.ml_data.return_training_v1"

aiplatform.init(project=PROJECT, location=REGION)

# WRITE: tạo managed Dataset resource liên kết bảng BigQuery.
# Chưa train model, nhưng có thể phát sinh phí dịch vụ/nguồn.
dataset = aiplatform.TabularDataset.create(
    display_name="returns-30d-20261101-v1",
    bq_source=SOURCE,
    labels={"env": "lab", "source": "bq", "version": "v1"},
)

print("Dataset resource:", dataset.resource_name)
print("Display name:", dataset.display_name)
~~~

**Đây là lệnh ghi tài nguyên**; thay project, region và source bằng môi trường được duyệt. `bq_source` dùng URI **`bq://project.dataset.table`**, không dùng dấu backtick kiểu SQL hoặc `gs://`. Tạo dataset này **chưa cố định một bản copy nguồn**: nếu upstream thay bảng, run sau có thể thấy dữ liệu khác. Với workflow cần tái lập, dùng **bảng nguồn versioned/immutable hoặc snapshot** rồi lưu ID đó trong metadata training run. Kiểm tra [Python `TabularDataset.create`](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.TabularDataset).

### 8.3. Chỉ đọc nguồn trước khi tạo resource

~~~bash
PROJECT_ID="retail-lab"

# READ-ONLY: xác nhận danh tính gcloud.
gcloud auth list
gcloud config get-value project

# READ-ONLY: đọc schema và metadata của bảng nguồn.
bq show --format=prettyjson \
  "${PROJECT_ID}:ml_data.return_training_v1"

# READ-ONLY: dự toán truy vấn, không thực thi scan đầy đủ.
bq query --use_legacy_sql=false --dry_run \
  'SELECT item_count, subtotal_vnd, return_within_30d
   FROM `retail-lab.ml_data.return_training_v1`'
~~~

Quyền chạy BigQuery query và quyền tạo Agent Platform Dataset là **hai nhóm quyền khác nhau**. `bq show` thành công không chứng minh service agent của Agent Platform có quyền đọc bảng, đặc biệt khi nguồn ở **project khác**. Hãy xác minh project/region và IAM trước khi tăng quyền.

## 9. Phiên bản dữ liệu, lineage và tái lập thí nghiệm

### 9.1. “Dataset v1” chỉ là tên nếu không pin nội dung

Để trả lời “model này huấn luyện trên dữ liệu nào?”, ghi:

| Metadata | Ví dụ |
| --- | --- |
| `dataset_version` | `returns-20261101-v1` |
| `source_uri` | `bq://retail-lab.ml_data.return_training_20261101_v1` |
| `as_of` và label horizon | `2026-11-01T00:00:00Z`, 30 ngày + buffer 5 ngày |
| `feature_contract_version` | `returns-feature-schema-v3` |
| `split_policy` | Delivered-time chronological cutoffs, train/validate/test |
| `preprocessing_version` | Git commit/container image digest, config của SQL/Dataflow |
| `quality_report` | Duplicate count, null %, class balance và lỗi |
| `source_snapshot` | BigQuery snapshot/immutable table hoặc GCS generations/checksums |
| `training_run` | Training job ID, run ID, model artifact ID, hyperparameters |
| `owner` và `access_policy` | Data owner/steward, quyền và retention |

**BigQuery table snapshot** là một cách giữ dữ liệu nguồn theo thời điểm; `CREATE SNAPSHOT TABLE` có điều kiện/quota/retention và chi phí riêng. Với GCS, **object versioning** hoặc prefix được khóa ghi + manifest/checksum giúp tái lập file; không giả định một đường `gs://bucket/latest.csv` là immutable.

### 9.2. Vì sao Data Lineage/ML Metadata quan trọng?

~~~mermaid
flowchart LR
    RAW["raw.orders + raw.returns"] --> SQL["BigQuery SQL commit abc123"]
    SQL --> SNAP["training data snapshot v1"]
    SNAP --> DATA["Managed Dataset ref"]
    DATA --> RUN["Training pipeline run #41"]
    RUN --> MODEL["Model Registry: returns-model v5"]
    QA["Data quality report"] -.-> SNAP
    GIT["Code + config + split policy"] -.-> RUN
~~~

**Agent Platform Pipelines** có thể lưu metadata của pipeline executions và artifacts thông qua **Vertex ML Metadata**; **Knowledge Catalog** có thể hỗ trợ khám phá/lineage ở cấp tài sản được map với FQN. Nhưng lineage **không tự biết** quy tắc business label nếu pipeline không ghi metadata. Ví dụ phải lưu SQL version/cutoff, không chỉ ghi “đọc bảng orders”. [Lineage của pipeline artifacts](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/pipelines/lineage).

### 9.3. Dataset drift khác model drift

- **Data drift:** phân phối features ở production đổi so với training (ví dụ vùng giao, đơn giá cao hơn).
- **Label drift:** tỷ lệ trả hàng thực tế thay đổi theo mùa/chính sách.
- **Schema drift:** tên/kiểu/missing rate của feature thay đổi làm pipeline lỗi.
- **Training-serving skew:** cùng một feature được tính khác nhau giữa training và inference.
- **Model quality drift:** precision/recall giảm trên nhãn *sau khi có đủ thời gian quan sát*, không suy chỉ từ số requests.

Lưu baseline statistics theo **từng split và thời điểm**, rồi giám sát trên dữ liệu serving. Với nhãn cần 30 ngày trưởng thành, **quality monitoring có độ trễ tự nhiên**; dùng chỉ số không nhãn (feature drift, null %, inference failures) để cảnh báo sớm nhưng không khẳng định độ chính xác cuối.

## 10. IAM, bảo mật, vùng dữ liệu và kiểm soát sử dụng

### 10.1. Tách principal theo chức năng

| Danh tính | Công việc | Quyền cần cân nhắc |
| --- | --- | --- |
| Data engineer SA | Chạy SQL chuẩn hóa và tạo bảng training. | BigQuery Job User ở project chạy job, Data Viewer ở nguồn, Data Editor tại dataset đích. |
| Agent Platform user/deployer | Tạo/list managed datasets, chạy training đã duyệt. | `roles/aiplatform.user` hoặc custom role phù hợp scope, `iam.serviceAccounts.actAs` khi chạy với custom SA. |
| **Agent Platform Service Agent** | Truy cập dữ liệu do dịch vụ quản lý khi tạo/train datasets. | Quyền mặc định dịch vụ và **quyền đọc bổ sung ở GCS/BQ khác project** khi cần. |
| Custom training SA | Đọc curated data để chạy container huấn luyện. | `Storage Object Viewer`/`BigQuery Data Viewer` đúng nơi, logging/artifact write theo nhiệm vụ. |
| Data steward/auditor | Xem schema, quality và quyền sử dụng dữ liệu. | Metadata/Viewer/Logging tối thiểu, không mặc định quyền PII. |

Agent Platform Service Agent thường có dạng `service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com` với vai trò nội bộ `roles/aiplatform.serviceAgent`. **Không cấp role Service Agent này cho người dùng hay mọi custom SA**. Nếu bảng BigQuery nằm ở project khác, phải cấp quyền nguồn phù hợp cho **đúng principal do tài liệu yêu cầu**, thay vì chuyển toàn bộ dataset về public. [IAM Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/general/access-control).

### 10.2. Dữ liệu khách hàng và governance

- Thực hiện **data minimization**: chỉ lấy features phục vụ bài toán; hạn chế email, số điện thoại, địa chỉ cụ thể và free-text chứa PII.
- Dùng **authorized views**, policy tags, row/column access policies, masking và service account riêng phù hợp từng bước.
- Kiểm tra **VPC Service Controls, Private Google Access/PSC, DNS và egress** theo network topology nếu Dataflow/training jobs truy cập Google APIs từ private environments.
- **CMEK, region/location, bucket location và retention** phải phù hợp chính sách tổ chức; không suy rằng Dataset resource region tự di chuyển dữ liệu BigQuery/GCS về cùng region.
- Tài liệu ML, annotation reviewers, labels hoặc metadata **cũng có thể chứa dữ liệu nhạy cảm**; log sample IDs thay vì raw payload.
- Khi dùng dữ liệu bên thứ ba, xác minh quyền huấn luyện, thời hạn lưu trữ, mục đích dùng và khả năng xóa dữ liệu theo hợp đồng.

**Một model được huấn luyện thành công không chứng minh dữ liệu dùng để train được phép sử dụng.** Quyền kỹ thuật và trách nhiệm pháp lý/đạo đức là hai lớp cần xem xét độc lập.

## 11. CI/CD dữ liệu, kiểm thử và giám sát

### 11.1. Data preparation là một bước deploy có kiểm soát

~~~text
Source update (BigQuery / GCS / Dataflow)
  → schema contract & freshness checks
  → point-in-time joins + dedup + label generation
  → data quality and privacy gates
  → immutable/versioned training data
  → split assignment + feature selection
  → managed Dataset reference (nếu AutoML)
  → training job + evaluation
  → review / approval / promotion
~~~

Không tạo bảng training theo cách “nhà nghiên cứu chỉnh tay trên notebook rồi chạy lại”. Nên có SQL/code trong Git, query parameters (`as_of`, label horizon), pipeline job identity, version schema, logs và artifacts. Với **Agent Platform Pipelines**, có thể quản lý dependency giữa các components và ghi lineage; với workflow nhỏ hơn, CI/CD có thể gọi BigQuery/Dataflow và SDK trực tiếp, nhưng vẫn cần idempotency và rollback.

### 11.2. Các chất lượng cần chặn release

| Data quality gate | Ví dụ ngưỡng minh họa | Vì sao |
| --- | --- | --- |
| Uniqueness | 0 rows trùng `order_id`. | Tránh duplicate leakage và tăng trọng số ngầm. |
| Feature availability | 100% features được phép tính tại `delivered_at`. | Ngăn temporal leakage. |
| Label maturity | 100% mẫu có đủ 30 ngày + buffer. | Không gán sai negative. |
| Required field null | `order_id`, target null = 0. | Dữ liệu không thể dùng làm supervised example nếu thiếu. |
| Data loss | Tỷ lệ rows bị loại được thống kê, không vượt ngưỡng được duyệt. | Tránh selection bias. |
| Class distribution | Có positive labels trong từng split, đo PR metrics. | Tránh test rỗng một class hoặc report metric không ổn định. |
| Split contamination | 0 duplicate business IDs xuyên splits; group leakage kiểm tra theo mục tiêu. | Test phải độc lập theo thiết kế. |
| Privacy | Không có raw email/phone/token trong feature table. | Giảm rủi ro truy cập sai mục đích. |
| Reproducibility | Có snapshot ID + code version + config. | Rebuild, audit và rollback được. |

Các ngưỡng trong bảng là **ví dụ chính sách nội bộ**, không phải SLA mặc định Google Cloud. Gate phải định nghĩa riêng theo nghiệp vụ; ví dụ một vùng khách hàng rất nhỏ có thể không đủ positive labels ở test nếu chia thời gian quá hẹp.

### 11.3. Tín hiệu cần theo dõi

- **Data prep:** số records đầu vào/đầu ra, duplicates, invalid values, age của dữ liệu, độ trễ BigQuery/Dataflow jobs.
- **Training input:** class balance, missing rate theo feature, file count, data volume, thời gian tạo snapshot, source URI/version.
- **Inference/serving:** tỷ lệ unknown categories, null feature rates, data/feature drift, train-serving skew.
- **Evaluation:** precision, recall, PR-AUC và hiệu quả theo từng segment; theo dõi label delay trước khi đo model quality.
- **Ops/cost:** BigQuery bytes billed/slots, GCS storage/operations, training compute, autoscaling, egress, logs và dataset/artifact retention.

Tạo alerts khi có **schema drift hoặc chất lượng dữ liệu xấu**, không chỉ khi training job thất bại. Model có thể train thành công trên dữ liệu sai.

## 12. Chi phí và những đánh đổi thường bị bỏ sót

| Quyết định | Chi phí/tác động |
| --- | --- |
| Scan nhiều lần bảng BigQuery raw lớn | Tăng query bytes/slot usage; dùng partition pruning/materialized curated data. |
| Tạo snapshot/table version cho mỗi run | Tăng storage và chi phí quản lý retention nhưng giúp tái lập/audit. |
| Giữ nhiều bản ảnh/video thô | Storage, annotation processing, nhân bản GCS và data transfer. |
| Reimport một managed dataset khi thay labels | Tốn thời gian import/index và có thể phát sinh xử lý/labeling. |
| Training thử nghiệm nhiều cấu hình | Tăng compute, thời gian training và artifact storage. |
| Tạo Feature Store cho mọi cột | Có thêm vận hành/sync/online serving costs; chỉ dùng khi cần reuse/serving consistency. |
| Cấp cross-region dữ liệu cho training | Có thể gặp location constraints, network transfer và data residency issues. |

**Feature Store** (nay trong Agent Platform) quản lý các đặc trưng để dùng lại, đồng bộ offline/online khi cần; **không phải** cùng resource với managed training Dataset. Với mô hình đơn giản chạy batch trên bảng BigQuery đã version, chưa chắc cần Feature Store. Quyết định theo **training-serving skew, nhu cầu online latency và số đội dùng chung feature**.

Đánh giá theo **chi phí cho một thử nghiệm tái lập được và một mô hình đạt SLO**, không chỉ phí tạo dataset. Dọn dẹp trial tables, GCS staging, training endpoints/jobs và objects sau khi đã hết retention/approval; **không xóa nguồn còn được managed Dataset hoặc pipeline khác tham chiếu**.

## 13. Tình huống thực tế: mô hình trả hàng 30 ngày

### 13.1. Một kế hoạch có thể kiểm chứng

| Giai đoạn | Việc cần làm | Điều kiện chuyển tiếp |
| --- | --- | --- |
| **Problem framing** | Dự đoán yêu cầu trả hàng trong 30 ngày **từ thời điểm giao**. | Có định nghĩa label và inference timestamp. |
| **Source inventory** | Xác minh `orders`, return events và các data owners. | Có IAM, tính hợp lệ pháp lý và ingestion timestamps. |
| **Label construction** | Dùng as-of cố định, trưởng thành 30 ngày + ingest buffer. | Không gán 0 cho đơn chưa đủ quan sát. |
| **Feature contract** | Chỉ dùng facts sẵn có tại delivery. | Không có refund/return columns trong feature list. |
| **Quality checks** | Dedupe, null/negative duration, class ratio, missing categories. | Có quality report, các lỗi được xử lý. |
| **Split** | Theo thời gian giao; thiết kế group tests nếu cần generalize tới khách mới. | Không leakage và test period là tương lai. |
| **Version** | BigQuery immutable table hoặc snapshot, code digest và run config. | Tái lập được các rows/splits. |
| **Dataset & training** | Agent Platform managed dataset nếu AutoML; hoặc custom training từ BQ/GCS. | Ghi dataset/job/model IDs và metrics. |
| **Evaluation** | PR-AUC, precision/recall tại threshold, metrics theo vùng/seller. | Đạt yêu cầu kinh doanh/fairness và latency. |
| **Monitoring** | Dữ liệu feature ở production, label xuất hiện sau 30 ngày. | Có cảnh báo và lịch retraining phù hợp. |

### 13.2. Hai cách làm sai thường gặp

**Lỗi A — AUC cực cao nhưng không triển khai được:** tập huấn luyện có `return_requested_at` đã được đưa vào model như numerical/timestamp feature. Khi chạy inference ngay thời điểm giao, trường này chưa có. Sửa bằng **whitelist features có sẵn tại delivery**, retrain và đánh giá trên test đã khóa.

**Lỗi B — mô hình luôn dự đoán “không trả hàng”:** data engineering xem đơn giao tuần trước chưa có return event là label 0; nhiều đơn có thể trả sau đó, khiến dataset bị sai nhãn. Sửa bằng cutoff trưởng thành, giữ raw history và dùng pipeline late-event reconciliation.

## 14. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Dataset tạo được nhưng training đọc dữ liệu khác ngày trước | Tabular Dataset **liên kết nguồn**, upstream table/CSV thay đổi. | Dataset source URI, training snapshot/version, cutoff và code. |
| Tạo Dataset báo `PERMISSION_DENIED` | Người gọi hoặc Agent Platform Service Agent thiếu quyền nguồn. | ADC principal, project/location, BigQuery/GCS cross-project IAM. |
| Bảng ở BigQuery nhưng Dataset không tạo được | Vị trí nguồn không hỗ trợ hoặc sai URI/schema. | `bq://project.dataset.table`, region, data types và source shape. |
| Import image thất bại | GCS URI/manifest/split label không đúng import schema. | Objective, schema URI, file permissions, format CSV/JSONL. |
| Accuracy 99% nhưng precision kém | Class imbalance, evaluation metric không phù hợp. | Confusion matrix, prevalence, PR-AUC, threshold. |
| Train score tốt hơn test quá nhiều | Overfit, drift hoặc train/test leakage. | Splits, duplicates, feature timing, data distribution. |
| Test cao bất thường rồi production thất bại | Target/temporal leakage hoặc training-serving skew. | Feature availability, point-in-time joins, serving transformations. |
| Label có nhiều null | Đơn chưa đủ 30 ngày, event returns thiếu hoặc join sai. | As-of, maturity buffer, late data và label rules. |
| Kết quả không tái lập dù cùng Dataset ID | Dữ liệu nguồn mutable, split/random seed hoặc code thay đổi. | Snapshot/generation, run parameters, preprocessing version. |
| Một phân khúc hoạt động kém | Dataset không đại diện, nhãn nhiễu, thiếu số lượng mẫu. | Metrics theo region/device/season, consent và cân bằng mẫu. |
| Chi phí data prep cao | Quét toàn bộ BigQuery mỗi lần, nhiều trial/staging files. | Partition filters, dry run, Billing, retention. |
| Model không nhận feature mới | Schema drift hoặc inference preprocessing không tương thích. | Feature contract version, training-serving tests. |

**Runbook:** xác nhận mục tiêu và prediction time → kiểm tra nguồn/label maturity → đọc quality gates → so feature list và split → đối chiếu snapshot/code version → kiểm tra IAM/region → chạy thử trên sample đã được phê duyệt → mới cân nhắc training lại. Không sửa `PERMISSION_DENIED` bằng cách cấp project Owner hoặc làm public bucket.

## 15. Bài tập

### Bài 1 — Chọn nơi lưu dataset

Phân loại bốn trường hợp: (a) một triệu đơn hàng có features dạng bảng; (b) 40.000 ảnh sản phẩm có labels; (c) custom PyTorch pipeline đọc TFRecord từ GCS; (d) dữ liệu tại BigQuery dùng AutoML. Với mỗi trường hợp, chọn **nguồn lưu** và cho biết **managed Dataset resource có bắt buộc không**.

### Bài 2 — Feature availability

Mô hình dự đoán yêu cầu trả hàng **ngay lúc giao thành công**. Trong các trường sau, trường nào không được dùng làm feature: `subtotal_vnd`, `shipping_method`, `delivery_duration`, `return_requested_at`, `refund_status`, `item_count`? Giải thích bằng timeline.

### Bài 3 — Nhãn chưa trưởng thành

Pipeline chạy ngày 2026-11-01, mục tiêu trả hàng trong 30 ngày từ lúc giao. Có nên gán label 0 cho đơn giao 2026-10-25 không? Nếu upstream thường trễ thêm 5 ngày, chọn cutoff mẫu thế nào?

### Bài 4 — Kiểm tra dữ liệu

Một bảng có 10.000 rows, 300 `order_id` trùng, 100 `subtotal_vnd` âm và 600 rows thiếu `shipping_method`. Hãy viết SQL/profiling để đo tỷ lệ từng lỗi, rồi chọn **block, quarantine, impute** hay **giữ missing category** theo từng trường; nêu rủi ro nếu loại hết 600 rows.

### Bài 5 — Split theo thời gian và theo customer

Viết query BigQuery gán TRAIN trước tháng 7, VALIDATE tháng 7, TEST từ tháng 8. Nếu mục tiêu mới là dự đoán khách hàng chưa từng mua, hãy thiết kế thêm group split và chứng minh cùng `customer_id` không xuất hiện ở hai splits.

### Bài 6 — SQL bài toán returns

Dựa vào template ở mục 7, nêu hai nguồn tạo lỗi leakage/selection bias, bổ sung một query kiểm tra `order_id` trùng và một test phát hiện feature sinh sau `delivered_at`. Vì sao cần nguồn **delivery events lịch sử** thay cho trạng thái hiện tại?

### Bài 7 — BigQuery source vs managed Dataset

Bạn tạo managed tabular dataset `returns-v1` liên kết `bq://retail-lab.ml_data.return_training_v1`. Sau đó upstream ghi đè bảng nhưng resource Dataset ID không đổi. Training run tiếp theo có thể khác run cũ không? Đề xuất ba metadata/artifacts để tái lập.

### Bài 8 — Ảnh và annotation quality

Tập ảnh phân loại áo/giày/túi có 5% ảnh giống hệt giữa train/test, nhãn của người gán khác nhau ở nhiều ảnh. Hãy sửa annotation guidelines, duplicates và split trước khi train; giải thích vì sao single-label khác multi-label.

### Bài 9 — IAM theo project

Agent Platform Dataset được tạo ở project A nhưng bảng training nằm ở project B. Local `bq show` thành công còn import/train báo 403. Bạn cần kiểm tra những **principal** nào, role nào ở B và region/location ra sao?

### Bài 10 — Tối ưu chi phí và đánh giá

Đội thử 20 lần training, mỗi lần quét toàn bộ bảng raw 3 TB và tạo một bản copy GCS; chất lượng model tăng không đáng kể. Đề xuất curated table/snapshot, partition pruning, preprocessing caching, artifact retention và metrics cần theo dõi. Vì sao không được bỏ test/quality checks chỉ để giảm chi phí?

## 16. Checklist production và tài liệu chính thức

| Hạng mục | Câu hỏi kiểm chứng |
| --- | --- |
| **Task/label** | Prediction time và target horizon định nghĩa rõ? |
| **Sources** | BigQuery/GCS nguồn hợp lệ, đủ IAM, region và provenance? |
| **Managed dataset** | Có cần AutoML Dataset hay custom training đọc trực tiếp? Resource có liên kết nguồn mutable không? |
| **Features** | Features chỉ dùng thông tin có sẵn tại inference; thống nhất serving code? |
| **Quality** | Dedupe, missingness, validation, class balance và sample-selection bias được kiểm tra? |
| **Split** | Random/chronological/group theo evaluation goal; test không bị dùng cho tuning? |
| **Versioning** | Có nguồn immutable, snapshot/object generation, `as_of`, code digest và split policy? |
| **Labels** | Chưa đủ 30 ngày không gán nhầm negative; có xử lý late returns? |
| **Security** | Tách data engineer, training SA, Agent Platform Service Agent và auditor; PII/consent đúng? |
| **Lineage** | Dataset, SQL version, training job/model ID được ghi lại? |
| **Cost** | Query/slots, storage, training, transfer, annotation và retention được dự toán? |
| **Operations** | Có quality gates, drift alerts, approval, rollback và cleanup an toàn? |

Nguồn chính thức để đối chiếu sản phẩm, API và hạn mức theo phiên bản:

- [Vertex AI → Gemini Enterprise Agent Platform: tên sản phẩm mới](https://docs.cloud.google.com/gemini-enterprise-agent-platform/vertex-ai-name-changes)
- [Managed datasets overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/datasets/overview)
- [Prepare tabular classification/regression data](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/classification-regression/prepare-data)
- [Create tabular datasets; BigQuery/GCS association và training snapshot](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/classification-regression/create-dataset)
- [Best practices for tabular data: leakage/skew/bias](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/bp-tabular)
- [Data splits for tabular models](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/data-splits)
- [Image classification: prepare data and annotations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/image-data/classification/prepare-data)
- [Agent Platform SDK Python: TabularDataset](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.TabularDataset)
- [Agent Platform IAM and service agents](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/general/access-control)
- [Track lineage of pipeline artifacts](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/pipelines/lineage)
- [BigQuery table snapshots](https://docs.cloud.google.com/bigquery/docs/table-snapshots-intro)
- [BigQuery cost best practices](https://docs.cloud.google.com/bigquery/docs/best-practices-costs)

**Ghi nhớ:** quản lý dataset không chỉ là tạo một resource trong Vertex AI/Agent Platform. Chất lượng mô hình phụ thuộc **nhãn đúng thời điểm, features không nhìn tương lai, split phản ánh production và nguồn dữ liệu được pin để tái lập**. BigQuery/GCS lưu dữ liệu thật; managed Dataset kết nối dữ liệu với workflow huấn luyện khi cần. IAM, versioning, chất lượng và chi phí phải được kiểm chứng **trước khi bấm Train**, không chỉ sau khi mô hình có metrics đẹp.



