# Thiết kế data lake, data warehouse và lakehouse trên GCP

> **Chương:** Quản trị và khai thác dữ liệu  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một công ty bán hàng lưu đơn đặt hàng trong Cloud SQL, sự kiện duyệt sản phẩm trong Pub/Sub và tệp CSV/Parquet từ đối tác trong Cloud Storage. Bộ phận vận hành muốn **giữ dữ liệu thô để tái xử lý**, tài chính cần **chỉ tiêu doanh thu đã kiểm định**, còn data scientists muốn đọc dữ liệu bằng cả **BigQuery** lẫn **Apache Spark**. Nên xây **data lake**, **data warehouse**, hay **lakehouse**?

Câu trả lời không chỉ nằm ở tên dịch vụ. Kiến trúc phải đáp ứng **cách dữ liệu được nạp, quyền truy cập, cách cập nhật/xóa, chất lượng, độ tươi, truy vấn và chi phí**. Bài thuộc mô-đun **CLOUD_PROVIDERS_GCP**, nối kiến thức IAM/VPC, Cloud Run/GKE, Cloud Storage, cơ sở dữ liệu và vận hành độ tin cậy/chi phí. Mô hình xuyên suốt là **orders analytics** cho công ty bán lẻ; tài nguyên và số liệu đều giả định.

**Sau bài học, bạn có thể:**

1. Phân biệt lake, warehouse và lakehouse qua nơi lưu, format, quyền và mô hình cập nhật.
2. Thiết kế luồng *raw/bronze → validated/silver → curated/gold* theo use case thực tế.
3. Chọn **Cloud Storage**, **BigQuery native**, **BigLake external** hoặc **Apache Iceberg managed tables** đúng yêu cầu.
4. Phối hợp Pub/Sub, Dataflow, Dataform, Spark và BigQuery trong batch/streaming.
5. Thiết kế location, partition, schema evolution, dedup, data contracts, retention và recovery.
6. Thiết lập IAM, BigLake connection delegation, policy tags, row/column policies và catalog/lineage/data quality.
7. Viết SQL ví dụ, kiểm thử data quality và ước tính chi phí lưu trữ/truy vấn/compute.
8. Hoàn thành lab và checklist sẵn sàng production.

## 1. Ba mô hình không đồng nghĩa

| Khía cạnh | **Data lake** | **Data warehouse** | **Lakehouse** |
| --- | --- | --- | --- |
| Mục tiêu | Lưu raw/lịch sử đa định dạng | SQL analytics, BI nhất quán | Open tables trên object storage cho nhiều engines |
| Nơi lưu trên GCP | **Cloud Storage** | **BigQuery native storage** | **Cloud Storage** + open table format/catalog |
| Dạng dữ liệu | CSV, JSON, Avro, Parquet, objects | BigQuery managed tables | Parquet + **Apache Iceberg** metadata |
| Cập nhật | Tùy file/pipeline, thường append | DML, MERGE, transactions theo BigQuery | Theo engine/table format; managed Iceberg có BigQuery DML |
| Quản trị | Metadata, owner, retention phải xây | BigQuery IAM/schema/policies | Catalog, table snapshot, multi-engine access |
| Rủi ro | “Data swamp”: khó tìm/không tin cậy | Bản sao dữ liệu và compute có phí | Quản lý metadata, concurrent writes, compaction |

**Không bắt buộc chọn đúng một mô hình cho toàn công ty.** Kiến trúc phổ biến giữ raw trong Cloud Storage, bảng có KPI ổn định trong BigQuery và chỉ dùng Iceberg cho datasets cần open formats. Lakehouse **không tự động rẻ hơn** warehouse: còn phí compaction, metadata, GCS operations, compute và egress.

### 1.1. Khi nào chọn mô hình nào?

- **Lake:** dữ liệu thô, nhiều định dạng, cần khả năng replay/khôi phục khi schema hoặc thuật toán xử lý thay đổi.
- **Warehouse:** báo cáo doanh thu, dashboard tự phục vụ, SQL joins/aggregates, bảo mật và tối ưu BigQuery.
- **Lakehouse:** BigQuery và Spark/engines mở cần cùng đọc table có metadata và snapshots, không chỉ chia sẻ một thư mục Parquet.
- **Kết hợp:** raw GCS → silver BigQuery hoặc Iceberg → gold BigQuery marts, tùy domain.

**Lake không thay OLTP.** Đặt hàng, kiểm tra tồn kho và thanh toán cần Cloud SQL/AlloyDB/Firestore theo access pattern; hệ thống phân tích không thay transaction database.

## 2. Kiến trúc tham chiếu trên Google Cloud

~~~mermaid
flowchart LR
  SQL["Cloud SQL/Firestore\nOperational records"] --> CDC["CDC / batch extract"]
  EVT["Pub/Sub\nEvents"] --> DF["Dataflow\nValidation, windowing"]
  FILES["Đối tác: CSV/JSON/Parquet"] --> GCS["Cloud Storage\nRaw / Bronze"]
  CDC --> GCS
  DF --> GCS
  GCS --> CLEAN["Silver\nBigQuery / Spark\nNormalize + dedup"]
  CLEAN --> GOLD["Gold\nBigQuery marts / Iceberg"]
  GOLD --> BI["Looker Studio / Looker\nSQL dashboard"]
  GOLD --> ML["Spark / ML / notebooks"]
  GCS --> BGL["BigLake external tables\nSQL không copy file"]
  BGL --> CLEAN
  GOV["Knowledge Catalog\nmetadata, quality, lineage"] -.-> GCS
  GOV -.-> CLEAN
  GOV -.-> GOLD
~~~

Sơ đồ thể hiện các **lựa chọn thay thế**, không bắt buộc mỗi bản ghi phải đi qua mọi mũi tên. Dataflow cũng có thể ghi **trực tiếp BigQuery Storage Write API** để dữ liệu xuất hiện nhanh, đồng thời lưu raw copy nếu cần replay. Đừng nhân đôi dữ liệu chỉ vì mô hình “medallion” có ba tên vùng.

### 2.1. Vai trò từng dịch vụ

| Dịch vụ | Vai trò | Không nên giả định |
| --- | --- | --- |
| **Cloud Storage** | Lưu raw, Parquet, logs, objects | Không tự cung cấp SQL transactions trên tập file |
| **BigQuery** | SQL, native warehouse, ETL/ELT, BI | Không phải OLTP server với foreign keys enforced |
| **BigLake external tables** | GCS structured data qua **connection delegation** | **External BigLake là read-only**, không phải managed Iceberg |
| **Apache Iceberg managed tables trong BigQuery** | BigQuery quản lý Iceberg table, Parquet files lưu trong GCS do bạn sở hữu | Không tùy ý sửa/xóa underlying files ngoài table manager |
| **Pub/Sub** | Buffer events, redelivery | Không tự tạo business exactly-once |
| **Dataflow** | Batch/stream pipelines, enrichment, windowing | Không tự thay hợp đồng dữ liệu |
| **Managed Service for Apache Spark** | Spark trên files/open tables | Không tự đồng bộ multi-writer commits với mọi engine |
| **Dataform** | SQL transformations, assertions, dependencies trong BigQuery | Không thay data ingestion cho mọi hệ nguồn |
| **Knowledge Catalog** | Metadata, data quality, lineage | Không tự cấp quyền query data |
| **Cloud KMS/IAM/Audit Logs** | Encryption, authorization, audit | Không thay data classification và review |

Google dùng tên **Knowledge Catalog** (trước đây **Dataplex Universal Catalog**) cho các khả năng catalog/quality/lineage; một số API còn dùng tiền tố `dataplex`. Xem [Data governance in BigQuery](https://docs.cloud.google.com/bigquery/docs/data-governance).

## 3. Thiết kế từ data products và consumer

Bắt đầu bằng bảng **data contracts** thay vì tạo bucket trước:

| Dữ liệu | Nguồn | Consumer | Độ tươi mục tiêu | Chất lượng/nhạy cảm |
| --- | --- | --- | --- | --- |
| `order_created` | Cloud SQL CDC/Pub/Sub | KPI gần realtime | Vài phút (giả định) | `event_id` ổn định, timestamp đúng |
| Orders đã xác nhận | Operational DB | Finance | Theo giờ | `order_id` duy nhất, amount hợp lệ |
| Danh mục sản phẩm | Cloud SQL/files | Analysts | Hằng ngày | Snapshot/version |
| File nhà cung cấp | Cloud Storage inbound | Data engineers | Hằng ngày | Schema, checksum, origin |
| App logs | Cloud Logging/GCS | SRE | Phút/giờ | Mask PII, TTL ngắn |
| `daily_revenue` | Silver orders | BI | Hằng ngày | SQL definition, owner, reconciliation |

**Data owner** chịu trách nhiệm định nghĩa nghiệp vụ và SLO của một data product; **platform team** quản lý storage, IAM, pipeline và monitoring. Một bảng “gold” không có owner có thể chạy SQL đúng nhưng vẫn sai nghĩa nghiệp vụ.

### 3.1. Data contract tối thiểu

~~~json
{
  "event_id": "evt-20261119-001",
  "order_id": "ord-001",
  "customer_id": "cust-042",
  "order_ts": "2026-11-19T02:10:00Z",
  "amount_minor": 259900,
  "currency": "VND",
  "status": "PAID",
  "source_version": 1
}
~~~

`event_id` phải giữ nguyên khi retry, `order_ts` chuẩn UTC, `amount_minor` là số nguyên theo đơn vị nhỏ nhất và `status/currency` thuộc tập cho phép. Không ghi tokens, mật khẩu, địa chỉ cá nhân hoặc PII không cần thiết vào logs/bronze.

## 4. Các vùng dữ liệu raw/bronze → silver → gold

~~~mermaid
flowchart TD
  INPUT["Incoming events + files"] --> BR["RAW/BRONZE\nGCS nguyên bản + source metadata"]
  BR --> Q{"Schema + quality đạt?"}
  Q -- "Không" --> QUAR["Quarantine\nerror code + safe reference"]
  Q -- "Có" --> SIL["SILVER\nnormalize, dedup, privacy"]
  SIL --> GOLD["GOLD\nbusiness KPIs/aggregates"]
  GOLD --> USE["Dashboards, analytics, ML"]
  BR -. "Replay/backfill" .-> SIL
~~~

| Vùng | Mục tiêu | Định dạng phổ biến | Điều kiện xuất bản |
| --- | --- | --- | --- |
| **Raw/landing** | Bản gốc, truy vết nguồn | CSV/JSON/log/file gốc | Restricted access, hash, source/version |
| **Bronze** | Parse tối thiểu, thêm ingestion metadata | Parquet/Avro/BigQuery raw | Source timestamp, event_id, schema version |
| **Silver** | Đúng kiểu, clean/dedup, PII policy | Parquet/Iceberg/BigQuery | DQ checks PASS |
| **Gold** | Định nghĩa nghiệp vụ chuẩn cho BI/ML | BigQuery marts/Iceberg curated | Owner sign-off, access policy |

Trong hệ thống nhỏ, Raw và Bronze có thể là **một vùng**; cũng không xóa raw quá sớm khi còn nhu cầu replay hoặc điều tra pipeline.

### 4.1. Đường dẫn và datasets có ý nghĩa

~~~text
gs://company-lake-lab/
  landing/partner_orders/2026/11/19/file-001.csv
  bronze/orders/dt=2026-11-19/part-0001.parquet
  quarantine/orders/dt=2026-11-19/invalid-001.json
  iceberg/orders_curated/ ...  # Chỉ table manager được sửa metadata

BigQuery (dataset location: asia-southeast1)
  lake_ext.orders_parquet         # BigLake external table
  silver.orders                  # BigQuery native table
  gold.daily_revenue             # Business mart
~~~

Các prefixes `dt=...` chỉ là key strings trong GCS; **không tự tạo Hive partitioning trong BigQuery**. Muốn external table partition pruning phải cấu hình Hive partitioning options và lọc đúng partition column. Wildcard `*.parquet` không tự sinh partition metadata.

### 4.2. Chọn format và tránh small-file problem

- **Parquet:** columnar, nén, phù hợp scans chọn cột với BigQuery/Spark. Dùng cho analytical lake.
- **Avro:** có schema, tốt cho interchange và dữ liệu tuần tự với evolving schema.
- **NDJSON/CSV:** dễ nhận từ đối tác nhưng cần parse/validate types, timezone và schema drift.
- **Apache Iceberg:** **table format** có snapshots/metadata/schema evolution, thường dùng Parquet data files. Không nhầm một thư mục Parquet bất kỳ với Iceberg table.
- **Delta Lake/Hudi:** open formats khác, hỗ trợ phụ thuộc engine; không suy chúng dùng được mọi tính năng SQL.

Hàng triệu objects vài KB làm tăng listing và metadata/query overhead. Batch/compaction thành file sizes thích hợp workload; không tạo mỗi event một Parquet file. Partition theo thời gian/ngữ nghĩa truy vấn, tránh high-cardinality partitions sinh vô số thư mục nhỏ. BigQuery native table thường partition theo ngày và cluster theo `customer_id`/`store_id`.

## 5. Bốn cách đưa GCS vào BigQuery

| Cách | Dữ liệu lưu ở đâu? | Quyền đọc | Mutations | Trường hợp |
| --- | --- | --- | --- | --- |
| **Non-BigLake external table** | GCS objects | User cần BigQuery **và GCS permissions** | Không DML trên external table | Lab, file ít thay đổi |
| **Cloud Storage BigLake external table** | GCS objects | BigQuery table permission; **connection SA** đọc GCS | **Read-only** table | Access delegation, row/column policies, metadata cache |
| **BigQuery native table** | BigQuery-managed storage | BigQuery IAM/policies | DML/MERGE, BigQuery features | BI/warehouse, SQL marts |
| **Apache Iceberg managed table** | GCS bucket do bạn sở hữu | BigQuery/Iceberg permissions; managed connection | **BigQuery DML** và engine-specific access | Open lakehouse, BigQuery + Spark |

**External vs managed** là khác biệt quyết định. Một BigLake external Parquet table không trở thành transactional table chỉ vì connection service account có quyền ghi GCS. Apache Iceberg managed table được BigQuery quản lý file/metadata và có DML, cần tính phí **GCS storage + storage optimization + query compute**.

### 5.1. BigLake access delegation

Ở non-BigLake external table, caller cần cả quyền BigQuery và quyền trực tiếp tới GCS files. Với **BigLake external**, bạn tạo một **BigQuery connection** có service account được cấp quyền bucket, người dùng chỉ cần quyền query/table ở BigQuery. Nhờ đó có thể áp row/column policies trên BigLake table và giảm chia sẻ trực tiếp bucket credentials.

**Giới hạn:** nếu người dùng vẫn có quyền đọc bucket qua IAM đường khác, BigLake policy **không tước quyền đọc GCS đó**. Muốn table là cổng truy cập duy nhất, cần ngăn direct GCS access.

## 6. Preflight: location, resources và quyền

Lab giả định (tất cả là placeholder):

| Giá trị | Ví dụ |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Region | `asia-southeast1` (chỉ ví dụ; đối chiếu hỗ trợ và residency) |
| Bucket raw/bronze | `gs://YOUR_BUCKET` |
| Dataset external | `lake_ext` |
| Dataset curated | `silver` |
| Dataset gold | `gold` |
| BigQuery connection | `LAB_PROJECT_ID.asia-southeast1.lake_conn` |
| Parquet | `gs://YOUR_BUCKET/bronze/orders/part-0001.parquet` |

Đây không phải project/bucket thật. Bucket name là định danh toàn cục và phải duy nhất. Không chạy lệnh tạo tài nguyên trên production nếu chưa có phê duyệt billing, quotas, location và IAM.

### 6.1. Lệnh kiểm tra chỉ đọc

~~~bash
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

gcloud storage buckets describe gs://YOUR_BUCKET
gcloud storage ls gs://YOUR_BUCKET/bronze/orders/

bq ls --project_id=LAB_PROJECT_ID
bq show --format=prettyjson LAB_PROJECT_ID:lake_ext
bq show --format=prettyjson LAB_PROJECT_ID:silver

bq ls --connection --project_id=LAB_PROJECT_ID --location=asia-southeast1
~~~

Nếu resource chưa có, ghi **NOT PRESENT**. Không tự tạo database/bucket có phí để hoàn thành checklist. Đảm bảo BigQuery API và BigQuery Connection API khi dùng connection; Dataflow API chỉ khi chạy Dataflow.

### 6.2. IAM tách theo nhiệm vụ

| Identity | Quyền phù hợp |
| --- | --- |
| Ingest Cloud Run/Dataflow SA | Ghi prefix raw/bronze được duyệt; không đọc toàn gold |
| BigLake **connection SA** | `roles/storage.objectViewer` trên bucket/managed folder cần query |
| BigLake table analyst | `bigquery.tables.getData` trên table và `bigquery.jobs.create` trên query project |
| ELT service account | Đọc bronze/silver, ghi silver/gold theo dataset/table scope |
| Dashboard viewer | Chỉ đọc gold view/aggregate theo credential model |
| Data steward | Catalog, metadata, DQ scans, ownership, lineage |
| Security operator | IAM, policy tags, audit, KMS/retention |

Ưu tiên runtime service account và **Workload Identity Federation/ADC**; không commit JSON service account keys. Trong BigQuery, role `roles/bigquery.dataViewer` ở table/dataset và `roles/bigquery.jobUser` trên project có thể đáp ứng query, nhưng luôn xác minh permissions theo hành động. Không cấp Project Editor để chữa lỗi 403.

## 7. Lab BigLake external: truy vấn Parquet từ Cloud Storage

Giả định bucket chứa các tệp Parquet **đúng schema**:

~~~text
gs://YOUR_BUCKET/bronze/orders/part-0001.parquet
gs://YOUR_BUCKET/bronze/orders/part-0002.parquet
~~~

Mỗi file có fields `order_id STRING`, `customer_id STRING`, `order_ts TIMESTAMP`, `amount_minor INT64`, `currency STRING`, `status STRING`. **Không tự chạy** SQL nếu bucket chưa có file hợp lệ, connection chưa được cấp quyền hoặc GCP project chưa duyệt chi phí.

### 7.1. Tạo dataset và BigQuery connection

~~~bash
# THAY ĐỔI PROJECT: chạy trong lab được phê duyệt, có chi phí liên quan
bq --location=asia-southeast1 mk \
  --dataset LAB_PROJECT_ID:lake_ext

bq --location=asia-southeast1 mk \
  --dataset LAB_PROJECT_ID:silver

bq --location=asia-southeast1 mk \
  --dataset LAB_PROJECT_ID:gold

# Tạo BigQuery Cloud resource connection
bq mk --connection \
  --location=asia-southeast1 \
  --connection_type=CLOUD_RESOURCE \
  lake_conn
~~~

**Trước bước tiếp theo:** Lấy **service account của connection** bằng BigQuery Console → Connections hoặc:

~~~bash
# CHỈ ĐỌC: xác nhận serviceAccountId trong connection metadata
bq show --connection \
  LAB_PROJECT_ID.asia-southeast1.lake_conn
~~~

Sau khi biết `serviceAccountId` thật, chủ sở hữu bucket chỉ cấp **Storage Object Viewer** trên bucket/prefix cần đọc. Không gán quyền Viewer cho `principal` giả trong ví dụ. Nếu dùng bucket có Uniform bucket-level access, dùng bucket-level IAM hoặc managed folder IAM theo tính năng hỗ trợ.

### 7.2. Khai báo BigLake Cloud Storage external table

~~~sql
-- THAY ĐỔI DATASET: tạo external table trong project lab
CREATE OR REPLACE EXTERNAL TABLE
  `LAB_PROJECT_ID.lake_ext.orders_parquet`
WITH CONNECTION `LAB_PROJECT_ID.asia-southeast1.lake_conn`
OPTIONS (
  format = "PARQUET",
  uris = ["gs://YOUR_BUCKET/bronze/orders/*.parquet"]
);
~~~

Câu lệnh dùng **BigLake external table** vì có `WITH CONNECTION`. BigQuery đọc Parquet và metadata lưu trong Cloud Storage, **không copy** toàn bộ dữ liệu sang BigQuery managed storage. Trên một external table như vậy, **không dùng BigQuery DML trực tiếp để sửa các hàng trong file**.

Nếu bảng có hàng triệu files hoặc Hive-style partitions, có thể thêm cấu hình **metadata caching** theo tài liệu:

~~~sql
-- Tạo bảng khác để so sánh tác dụng cache
CREATE OR REPLACE EXTERNAL TABLE
  `LAB_PROJECT_ID.lake_ext.orders_cached`
WITH CONNECTION `LAB_PROJECT_ID.asia-southeast1.lake_conn`
OPTIONS (
  format = "PARQUET",
  uris = ["gs://YOUR_BUCKET/bronze/orders/*.parquet"],
  max_staleness = INTERVAL 2 HOUR,
  metadata_cache_mode = "AUTOMATIC"
);
~~~

Cache làm tăng hiệu quả đọc metadata/listing và có **chi phí làm mới cache**; dữ liệu file mới có thể chưa phản ánh ngay trong cache cho tới lúc refresh. Với `AUTOMATIC`, lịch làm mới thường khoảng **30–60 phút**, không phải cam kết độ tươi 2 giờ của dữ liệu nghiệp vụ. `max_staleness` cho biết lúc nào truy vấn có thể dùng cache, không phải retention period.

### 7.3. Truy vấn sample

~~~sql
-- CHỈ ĐỌC; sẽ chạy query và có thể phát sinh phí
SELECT
  DATE(order_ts) AS order_date,
  currency,
  COUNT(*) AS orders,
  SUM(amount_minor) AS total_minor
FROM `LAB_PROJECT_ID.lake_ext.orders_parquet`
WHERE order_ts >= TIMESTAMP "2026-11-18 00:00:00+00"
  AND order_ts < TIMESTAMP "2026-11-20 00:00:00+00"
  AND status = "PAID"
GROUP BY order_date, currency
ORDER BY order_date;
~~~

**Nhắc lại:** Truy vấn SQL được phép không đồng nghĩa external BigLake table hỗ trợ `UPDATE`/`DELETE`. Nếu cần upsert hoặc phân tích lặp nhiều lần, cân nhắc nạp sang BigQuery native hoặc chọn Iceberg managed.

## 8. Data warehouse với BigQuery native tables

Warehouse phù hợp khi nhóm BI cần bảng ổn định, partition pruning, joins, materialized views, scheduled transformations và SQL DML.

### 8.1. Tạo silver table có partition/cluster

Khi Parquet external table đã sẵn sàng, ví dụ ELT nạp sang BigQuery native:

~~~sql
-- THAY ĐỔI DATASET: tạo/ghi lại silver table trong lab
CREATE OR REPLACE TABLE `LAB_PROJECT_ID.silver.orders`
PARTITION BY DATE(order_ts)
CLUSTER BY customer_id
OPTIONS (description="Orders đã chuẩn hóa từ BigLake external source")
AS
SELECT
  CAST(order_id AS STRING) AS order_id,
  CAST(customer_id AS STRING) AS customer_id,
  SAFE_CAST(order_ts AS TIMESTAMP) AS order_ts,
  SAFE_CAST(amount_minor AS INT64) AS amount_minor,
  UPPER(TRIM(CAST(currency AS STRING))) AS currency,
  UPPER(TRIM(CAST(status AS STRING))) AS status
FROM `LAB_PROJECT_ID.lake_ext.orders_parquet`
WHERE order_id IS NOT NULL;
~~~

**Điểm chưa hoàn thiện để đưa production:** `CREATE OR REPLACE` full refresh làm tốn scan/copy và không tự xử lý duplicate `order_id`; các `SAFE_CAST` lỗi có thể trả `NULL`. Cần kiểm thử chất lượng trước/đồng thời, ghi invalid records sang quarantine và có quy tắc chọn bản ghi cập nhật mới nhất. Partition theo thời gian nên giữ data type TIMESTAMP hợp lệ và xử lý late events.

### 8.2. Gold mart có định nghĩa KPI

~~~sql
CREATE OR REPLACE TABLE `LAB_PROJECT_ID.gold.daily_revenue`
PARTITION BY order_date
AS
SELECT
  DATE(order_ts) AS order_date,
  currency,
  COUNT(*) AS paid_orders,
  SUM(amount_minor) AS revenue_minor
FROM `LAB_PROJECT_ID.silver.orders`
WHERE status = "PAID"
  AND order_ts IS NOT NULL
  AND amount_minor >= 0
GROUP BY 1, 2;
~~~

Đây chỉ là **bản đơn giản để học**; với refund, cancellation, partial payments và thuế/chiết khấu, `revenue` phải tuân theo **hợp đồng kế toán** và dữ liệu trạng thái đúng thời điểm. Không coi SUM đơn hàng có status PAID là doanh thu kế toán chính thức nếu chưa có owner phê duyệt.

### 8.3. Incremental thay cho full refresh

- **CDC** cung cấp thay đổi inserts/updates/deletes từ operational systems. Cần phân biệt snapshot ban đầu và change events.
- **MERGE** vào silver table theo `order_id` với latest source version hoặc event-time/sequence được định nghĩa.
- **Dataform** quản lý dependencies, SQL models, assertions và lịch chạy; không tự tạo exactly-once từ một stream có duplicate.
- **Materialized view** chỉ phù hợp với SQL/nguồn/query patterns được hỗ trợ, không phải mọi external table đều hỗ trợ.
- **Gold** nên có một contract truy vấn/định nghĩa metrics, được thử với dữ liệu giả trước khi công bố.

Một MERGE an toàn phải bảo đảm **tối đa một dòng source cho một target key** ở lượt thực thi; nếu input có nhiều bản cập nhật cho cùng `order_id`, dùng `ROW_NUMBER()/QUALIFY` và tie-breaker ổn định trước khi MERGE. Tránh chạy MERGE cho mọi event riêng lẻ nếu có thể gom micro-batches.

## 9. Lakehouse: Apache Iceberg managed tables trong BigQuery

BigQuery hỗ trợ **Apache Iceberg managed tables** lưu **Parquet trên Cloud Storage bucket do tổ chức sở hữu**. Table metadata format Iceberg cho phép Spark/third-party engines đọc theo cách được hỗ trợ; BigQuery cung cấp trải nghiệm managed như schema evolution, DML và background storage optimization. <https://docs.cloud.google.com/bigquery/docs/biglake-iceberg-tables-in-bigquery>

### 9.1. DDL mẫu (phần nâng cao, có phí)

~~~sql
-- THAY ĐỔI DATASET VÀ BUCKET: chỉ thực hiện trên lab đủ điều kiện
CREATE TABLE `LAB_PROJECT_ID.silver.orders_iceberg` (
  order_id STRING,
  customer_id STRING,
  order_ts TIMESTAMP,
  amount_minor INT64,
  currency STRING,
  status STRING
)
CLUSTER BY customer_id
WITH CONNECTION `LAB_PROJECT_ID.asia-southeast1.lake_conn`
OPTIONS (
  file_format = "PARQUET",
  table_format = "ICEBERG",
  storage_uri = "gs://YOUR_BUCKET/iceberg/orders_curated"
);
~~~

Khác BigLake external read-only, đây là **managed table**, không có từ khóa `EXTERNAL`. Connection service account cần các quyền thích hợp **đọc, tạo, xóa và liệt kê GCS objects** theo hướng dẫn Iceberg managed, thay vì chỉ Object Viewer. Dataset, bucket, connection và storage location phải tương thích; cần hỗ trợ feature ở region và chính sách tổ chức.

### 9.2. Ranh giới trách nhiệm với table format mở

| Chủ đề | Cần nhớ |
| --- | --- |
| Dữ liệu thật | Parquet files và Iceberg metadata ở bucket do bạn sở hữu |
| DML | BigQuery quản lý mutations, compaction, metadata/snapshots |
| Spark reads | Dùng Iceberg snapshot/catalog được hỗ trợ, không đọc file path tùy ý |
| Concurrent writers | Kiểm tra **write ownership/commit protocol** theo integration cụ thể |
| Xóa bảng | Không mặc định mọi data files GCS sẽ được xóa tự động cùng BigQuery table |
| Metadata freshness | Snapshot/export có lịch/cơ chế refresh; external engine có thể đọc bản trước |
| Chi phí | GCS bytes/operations, BigQuery queries, **DCU storage optimization**, egress |

**Không** chạy `gcloud storage rm -r gs://.../iceberg/orders_curated` hoặc để Spark ghi trực tiếp vào thư mục managed table **khi chưa có hướng dẫn integration chính thức**. Ghi song song bằng nhiều engines không phối hợp có thể làm hỏng metadata và snapshots. Việc chia sẻ open format **không đồng nghĩa multi-writer ACID tự động trên tất cả engines**.

### 9.3. Tiêu chí quyết định dùng Iceberg

Chọn Iceberg managed nếu **đã có use case đa engine**, cần open format trên GCS và chấp nhận trách nhiệm KMS/retention/table metadata lifecycle. Nếu toàn bộ dashboard và SQL transformations chỉ dùng BigQuery, **native BigQuery tables thường đơn giản hơn**, với nhiều tối ưu BI/warehouse được quản lý đầy đủ. Nếu chỉ muốn query một tập Parquet ít thay đổi, **BigLake external table** có thể đủ.

## 10. Ingestion và xử lý batch/streaming

~~~mermaid
flowchart TD
  INPUT["Operational DB / Events / Files"] --> CLASS{"Tính chất nguồn?"}
  CLASS -- "CDC/batch" --> LAND["GCS raw + manifest/hash"]
  CLASS -- "Streaming" --> PUB["Pub/Sub"]
  PUB --> FLOW["Dataflow validate + dedup"]
  LAND --> LOAD["BigQuery load job / Spark transform"]
  LOAD --> SILVER["Silver table"]
  FLOW --> SILVER
  SILVER --> TEST["Data quality gate"]
  TEST --> GOLD["Gold mart"]
  TEST --> QUAR["Quarantine / retry if failed"]
~~~

### 10.1. Batch file ingestion

1. Ghi tệp vào `landing`, kèm source ID, arrival timestamp, checksum và schema version.
2. Kiểm tra kích thước, format, encoding và schema trước khi publish.
3. Lưu raw dưới đường dẫn chỉ ingest job có quyền ghi; tránh ghi đè file có cùng tên.
4. Dùng BigQuery load job hoặc Spark xử lý, xuất bronze/silver.
5. Đặt idempotency key theo `source_file_checksum + version` để rerun không nhân đôi.
6. Xuất quality metrics, rejected-record counts và manifest/job ID.

### 10.2. Streaming với Pub/Sub và Dataflow

1. Producer gắn `event_id` duy nhất theo nghiệp vụ.
2. Pub/Sub có thể redeliver; Dataflow phải quản lý watermark, late data và DLQ.
3. Chọn write mode BigQuery Storage Write API theo yêu cầu: default at-least-once, app-created committed/offsets khi cần exactly-once **trong một stream**.
4. Deduplicate theo `event_id/source_version` trước Silver hoặc trong batch reconciliation.
5. Tạo metric `event_to_query_lag` và cảnh báo backlog.
6. Không ack/upstream commit chỉ dựa vào một bước chưa có xác nhận ghi bền vững.

**Không tuyên bố exactly-once nghiệp vụ chỉ vì dùng một API có tên “exactly once”.** Cần xử lý source duplication, retries, checkpoint, dedup và downstream idempotency.

### 10.3. Một số phương án chuyển đổi

| Workload | Công cụ phù hợp | Lưu ý |
| --- | --- | --- |
| Batch CSV nhỏ, SQL transformations | BigQuery load + SQL/Dataform | Schema types và lịch refresh |
| Parquet lớn, Spark ecosystem | Managed Service for Apache Spark | File sizing, partitioning, temporary storage |
| Near-real-time events | Pub/Sub + Dataflow + BigQuery Write API | Backpressure, duplicates, watermark |
| Periodic SQL ELT | BigQuery scheduled queries/Dataform | Dependency order, incremental MERGE |
| Data source từ Cloud SQL | CDC/data integration được hỗ trợ | Snapshot + change log + tombstones |
| Machine learning features | BigQuery/Vertex AI, validated data products | Training/serving skew, privacy |

## 11. Catalog, ownership, lineage và data quality

Một kiến trúc lakehouse không thành công nếu 100 TB dữ liệu không ai biết nguồn, chất lượng và người được phép dùng. **Knowledge Catalog** (tên cũ Dataplex Universal Catalog) hỗ trợ tìm assets, ghi metadata, quản lý quality scans và lineage trong phạm vi dịch vụ hỗ trợ. <https://docs.cloud.google.com/dataplex/docs/use-auto-data-quality>

### 11.1. Gắn metadata có thể hành động

| Thành phần | Metadata cần có | Ví dụ |
| --- | --- | --- |
| Data product | Owner, SLA, classification, contract | `orders-paid-v1`, owner Finance |
| Bảng/field | Mô tả, schema, format, tags, sensitivity | `customer_id`: Internal; `email`: Restricted |
| Ingestion | Source, run ID, checkpoint, hash, arrival time | `cdc-run-20261119` |
| Quality | Completeness, validity, uniqueness, freshness | `order_id` nonnull, `event_id` unique |
| Retention | Business/legal rule, expiration, deletion flow | Raw 90 ngày (giả định) |
| Lineage | Upstream → transform → downstream | GCS orders → Silver orders → Gold daily revenue |
| Access | Data owner approvals, policy, IAM | Gold viewers, raw restricted |

### 11.2. Data quality gates

Ví dụ Silver orders cần:

- **Completeness:** `order_id`, `order_ts`, `currency` không null.
- **Validity:** `amount_minor >= 0`; status trong danh sách.
- **Uniqueness:** không trùng `order_id` tại snapshot hiện hành hoặc `event_id` tại change log.
- **Freshness:** thời gian ingest không vượt SLA đã thỏa thuận.
- **Reconciliation:** tổng/số lượng giữa raw và Silver khớp sau khi loại records lỗi có ghi nhận.
- **Contract drift:** không thêm/bỏ cột bắt buộc mà chưa cập nhật schema/version.

Quality scan có thể tự động chạy theo lịch và xuất kết quả; **không có nghĩa scan tự ngăn SQL dashboard đọc dữ liệu sai**. Cần một **publication gate**: nếu kiểm tra fail, không thay thế gold snapshot đã được phê duyệt, phát cảnh báo và lưu bằng chứng.

### 11.3. Lineage và tác động thay đổi

~~~mermaid
flowchart LR
  SRC["Cloud SQL orders"] --> BR["GCS bronze orders"]
  BR --> SIL["BigQuery silver.orders"]
  SIL --> GOLD["BigQuery gold.daily_revenue"]
  GOLD --> DASH["Dashboard finance"]
  SIL --> MODEL["ML features"]
~~~

Khi đổi kiểu `amount_minor` hoặc xóa `customer_id`, lineage cho thấy báo cáo/model nào phụ thuộc vào trường đó. Bật Data Lineage API/capture theo hướng dẫn; lineage tự thu từ một số dịch vụ nhưng **không tự nhận biết mọi script, laptop hoặc third-party transformation**. Thêm custom lineage nếu cần và kiểm tra quyền xem metadata giữa projects.

## 12. Bảo mật, quyền riêng tư và vòng đời dữ liệu

### 12.1. Các lớp bảo vệ phải phối hợp

| Lớp | Ví dụ công cụ | Phạm vi |
| --- | --- | --- |
| Ingestion/network | Service identity, private connectivity, VPC Service Controls khi phù hợp | Giảm rủi ro truy cập/di chuyển dữ liệu không được phép |
| Object storage | Cloud Storage **Uniform bucket-level access**, IAM, Public Access Prevention | Ai được đọc/ghi files |
| BigLake | Connection access delegation | Không lộ GCS bucket cho tất cả analysts |
| BigQuery | Dataset/table IAM, **row access policies**, **column policy tags**, masking | Quyền đọc hàng/cột, masking |
| Encryption | Google-managed encryption/CMEK với Cloud KMS | Khóa và vận hành key lifecycle |
| Governance | Catalog classification, retention, audit, DQ | Owner, lineage, kiểm toán, tính tin cậy |
| Presentation | Authorized views, curated aggregates, dashboard permissions | Chỉ chia sẻ dữ liệu đúng audience |

**Quan trọng:** CMEK áp trên BigQuery table **không tự áp** tới Parquet objects trong Cloud Storage được BigLake external table đọc. Nếu cần CMEK end-to-end, phải cấu hình encryption/key access cho **cả GCS và BigQuery** theo các phần dịch vụ tương ứng.

### 12.2. Row/column policies và authorized views

Ví dụ Silver orders có `customer_id` và `amount_minor`, nhưng một số nhóm chỉ cần revenue theo ngày. Phương án hạn chế rủi ro hơn là:

1. Gold mart **không chứa customer IDs**.
2. Chỉ cấp analysts `roles/bigquery.dataViewer` trên Gold dataset/view.
3. Nếu cần quyền theo chi nhánh/tenant, dùng row-level policy hoặc authorized view có filter được kiểm duyệt.
4. Nếu cần masking PII, dùng policy tags và **dynamic data masking** theo các tính năng tương thích.
5. Test cả **direct GCS access**: ai được đọc file bronze vẫn có thể bỏ qua các controls BigQuery nếu bucket IAM quá rộng.

**Không lấy việc dashboard ẩn cột nhạy cảm bằng UI làm bảo mật thực sự.** Kiểm soát phải nằm tại nguồn/table/view và identity.

### 12.3. Retention/TTL và yêu cầu xóa dữ liệu

- Phân biệt **raw legal retention**, **Silver TTL**, **Gold aggregate retention** và **backups/snapshots**.
- Cloud Storage có lifecycle policies, object versioning/soft delete và retention policies; mỗi tính năng có hành vi riêng.
- **Bucket Lock** làm retention policy không thể giảm hoặc gỡ sau khi khóa; việc này là **không thể đảo ngược**, không làm trong lab.
- BigQuery có table/partition expiration, time travel và recovery windows theo configuration. Xóa logical row không nhất thiết xóa mọi bản snapshot/backup ngay.
- Dữ liệu cần xóa theo yêu cầu người dùng phải đi qua **mọi bản sao và derived data** theo luật/chính sách của tổ chức.
- Nếu dữ liệu được replicate sang các regions hoặc external engines, retention/deletion phải xét **mọi nơi tồn tại bản sao**.

**Không hứa “xóa khỏi warehouse tức là xóa khỏi data lake”.** Cần lineage, data inventory và quy trình deletion/rewrite hợp đồng.

## 13. Độ tin cậy, hiệu năng, chi phí và SLO

### 13.1. Đặt các mục tiêu có thể đo

| Chỉ số | Định nghĩa | Ví dụ yêu cầu, không phải SLA Google |
| --- | --- | --- |
| Freshness | Bản ghi mới được query trong Silver/Gold sau bao lâu? | 95% events xuất hiện trong 5 phút |
| Completeness | Tỷ lệ records hợp lệ nhận đủ so với nguồn | ≥ 99,9% theo manifest |
| Uniqueness | Không có duplicate business events | 0 duplicate `order_id` trong snapshot |
| Accuracy | Tổng doanh thu reconciled với nguồn kế toán | Chênh ≤ ngưỡng owner duyệt |
| Availability | Khả năng query/nhận dữ liệu | Theo dashboard/pipeline SLO |
| Recoverability | RPO/RTO cho replay/backfill | RPO trong phạm vi retention raw |
| Cost efficiency | Phí ingest/store/query trên 1 triệu events | Mốc ngân sách theo workload |

**Đặt owner chịu trách nhiệm mỗi SLO.** Không dùng “job thành công” thay cho “dữ liệu đạt chất lượng”: có pipeline xanh nhưng đếm trùng doanh thu.

### 13.2. Phân tích TCO

Tổng chi phí kiến trúc cần tính cả:

\[
C_{\text{total}} =
C_{\text{storage}} + C_{\text{ingest}} + C_{\text{processing}} +
C_{\text{query}} + C_{\text{network}} + C_{\text{governance/operations}}
\]

| Thiết kế | Khoản chi chính | Cách tối ưu |
| --- | --- | --- |
| GCS raw lake | GCS bytes, operations, retrieval, egress | Lifecycle đúng retention, Parquet compaction, ít copies |
| BigLake external | GCS + BigQuery query compute + metadata cache refresh | Partition/file pruning, không scan millions small files |
| BigQuery native | Native storage + load/transforms + SQL query slots/bytes | Partition/cluster, incrementals, materialized aggregations |
| Iceberg managed | GCS bytes + BigQuery queries + storage optimization DCUs | File sizing, data lifecycle, chỉ dùng khi đa engine có giá trị |
| Streaming | Pub/Sub, Dataflow, Write API, worker CPU | Batching, backpressure, checkpoint và DLQ |
| Governance | Catalog scans, logging, KMS, personnel | Scan có lịch, lọc logs/PII, ownership |

**Không suy query external sẽ rẻ hơn native vì “không copy dữ liệu”.** External đọc file metadata/lists và query compute vẫn tính phí, có thể chậm/đắt khi truy vấn lặp; native có phí lưu trữ nhưng tối ưu hóa mạnh hơn trong nhiều BI workloads.

### 13.3. Giảm bytes quét trên BigQuery

~~~bash
# Chỉ dry run, không thực thi query kết quả
bq query \
  --project_id=LAB_PROJECT_ID \
  --use_legacy_sql=false \
  --dry_run \
  'SELECT COUNT(*) FROM `LAB_PROJECT_ID.silver.orders`'

# Query có giới hạn bytes billed; chỉ chạy với bảng lab đã tạo
bq query \
  --project_id=LAB_PROJECT_ID \
  --use_legacy_sql=false \
  --maximum_bytes_billed=1073741824 \
  'SELECT currency, SUM(amount_minor) AS total
   FROM `LAB_PROJECT_ID.silver.orders`
   WHERE order_ts >= TIMESTAMP("2026-11-18")
     AND order_ts < TIMESTAMP("2026-11-20")
   GROUP BY currency'
~~~

Phép lọc trực tiếp theo **partitioning field/expression** giúp BigQuery prune partitions của native table, khác với việc thêm `LIMIT 10` vào một query quét bảng. Dry run giúp ước lượng chi phí, nhưng external tables có trường hợp **ước lượng chỉ là lower bound**, nên cần đo query job statistics thực tế.

## 14. Lab thực hành không cần tạo cloud resources

Nếu chưa có IAM/budget, dùng query **inline** trong BigQuery SQL editor trên project lab có quyền chạy query. Không cần Cloud SQL/GCS/BigLake connection hoặc dataset; câu lệnh dưới **không ghi** dữ liệu.

### 14.1. Đầu vào giả định

| event_id | order_id | status | amount_minor | Ghi chú |
| --- | --- | --- | ---: | --- |
| evt-01 | ord-101 | PAID | 100000 | Hợp lệ |
| evt-01 | ord-101 | PAID | 100000 | Replay bị trùng |
| evt-02 | ord-102 | PAID | 250000 | Hợp lệ |
| evt-03 | ord-103 | CANCELLED | 200000 | Không tính paid |
| evt-04 | ord-104 | PAID | -2000 | Sai hợp đồng |

**Bẫy:** Tổng tiền paid của raw nếu không dedup/validate có thể bị tính sai. Định nghĩa đúng cho bài: **350.000 VND** (mỗi event chỉ một lần, loại cancelled và số tiền âm).

### 14.2. SQL hoàn chỉnh chạy trên dữ liệu giả

~~~sql
-- Query GoogleSQL read-only; không tạo bảng hoặc thay đổi tài nguyên.
WITH bronze AS (
  SELECT 'evt-01' event_id, 'ord-101' order_id,
         TIMESTAMP '2026-11-19 02:00:00+00' order_ts,
         'PAID' status, 100000 amount_minor, 'VND' currency
  UNION ALL SELECT 'evt-01', 'ord-101',
         TIMESTAMP '2026-11-19 02:00:00+00', 'PAID', 100000, 'VND'
  UNION ALL SELECT 'evt-02', 'ord-102',
         TIMESTAMP '2026-11-19 02:01:00+00', 'PAID', 250000, 'VND'
  UNION ALL SELECT 'evt-03', 'ord-103',
         TIMESTAMP '2026-11-19 02:02:00+00', 'CANCELLED', 200000, 'VND'
  UNION ALL SELECT 'evt-04', 'ord-104',
         TIMESTAMP '2026-11-19 02:03:00+00', 'PAID', -2000, 'VND'
),
validated AS (
  SELECT *
  FROM bronze
  WHERE order_id IS NOT NULL
    AND amount_minor >= 0
    AND status IN ('PAID', 'CANCELLED')
    AND currency = 'VND'
),
silver AS (
  SELECT * EXCEPT(row_number)
  FROM (
    SELECT *,
      ROW_NUMBER() OVER (
        PARTITION BY event_id
        ORDER BY order_ts DESC, order_id DESC
      ) AS row_number
    FROM validated
  )
  WHERE row_number = 1
),
gold AS (
  SELECT DATE(order_ts) order_date, currency,
         COUNT(*) paid_orders, SUM(amount_minor) revenue_minor
  FROM silver
  WHERE status = 'PAID'
  GROUP BY 1, 2
)
SELECT * FROM gold ORDER BY order_date;
~~~

**Kết quả mong đợi:** `2026-11-19 | VND | 2 | 350000`. Đây là ví dụ data quality/dedup rõ ràng, **không phải logic nghiệp vụ đầy đủ**: nếu hai events cùng `event_id` nhưng payload khác, cần stable source sequence/ingest time và rule xử lý conflict. Trong production, `ROW_NUMBER` không nên dựa vào tie-breaker ngẫu nhiên; nguồn phải có sequence/snapshot version nhất quán.

### 14.3. Bài tập mở rộng từ query

1. Thêm bản ghi `evt-05, ord-105, PAID, 300000, USD`. Sửa SQL để **group theo currency**, không cộng VND và USD.
2. Thêm một record có `order_ts` null; đưa nó vào thống kê quality-failure thay vì gold.
3. Đếm số records raw, số rejected, số duplicate bị loại và số vào gold. Ghi rõ bước loại từng dòng.
4. Bổ sung filter `status='REFUNDED'` và quyết định có trừ revenue hay đưa vào một mart khác theo hợp đồng Finance.
5. Giả lập replay `evt-01` sau một ngày và giải thích sự khác nhau giữa event time, ingest time và partition date.

Không copy dữ liệu giả này vào `silver.orders` hoặc Gold production.

## 15. Case study: từ một lake nhỏ đến hệ thống đa nhóm

### 15.1. Giai đoạn A — Data lake + BigQuery warehouse

Công ty chỉ có vài nguồn (orders CSV mỗi đêm và event logs), 5 analysts và một dashboard doanh thu:

- GCS giữ raw files với retention rõ.
- BigQuery native Silver/Gold cho SQL, partition theo ngày.
- Dataform/Scheduled Queries cho ELT có tests; IAM theo datasets.
- Chưa cần Iceberg chỉ vì “lakehouse hiện đại”.

**Lợi ích:** Đơn giản, dễ vận hành, ít table metadata coordination.

### 15.2. Giai đoạn B — Thêm BigLake để chia sẻ raw có kiểm soát

Dữ liệu Parquet lớn, nhiều analysts muốn query ngay mà chưa cần nạp mọi file:

- Tạo BigLake external table với connection SA đọc GCS.
- Chỉ analysts có BigQuery permissions dùng SQL; khóa direct GCS khi phù hợp.
- Bật metadata cache với freshness phù hợp nếu file listing lớn.
- Những datasets được truy vấn nhiều lần vẫn nên nạp vào native BigQuery.

**Tránh sai lầm:** Cho analysts đọc thẳng bucket rồi tưởng column masking trên BigLake table bảo vệ được objects.

### 15.3. Giai đoạn C — Iceberg managed table khi có nhu cầu đa engine

Data science thực sự muốn chạy Spark trên một bản curated data và BI muốn BigQuery SQL:

- Chọn một dataset managed Iceberg, xác định **write ownership**, version/catalog integration và snapshot refresh.
- Dùng BigQuery để quản lý Iceberg table theo tài liệu; Spark đọc qua catalog/snapshot được hỗ trợ.
- Test concurrent writes, rollback metadata, performance/compaction, lineage và GCS object lifecycle.
- Theo dõi query + GCS + DCU storage optimization + data egress.

**Điều kiện lựa chọn:** Giá trị đa engine phải lớn hơn chi phí/sự phức tạp mới. Không di chuyển toàn bộ warehouse sang Iceberg theo phong trào.

## 16. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách kiểm tra/hành động |
| --- | --- | --- |
| BigLake query 403 | Connection SA chưa có GCS Object Viewer | IAM của **connection SA**, bucket/managed folder |
| Analyst vẫn tải raw file dù bị chặn BigQuery | User có direct GCS IAM | Rà direct bucket permissions, perimeter |
| External table không thấy file mới | Metadata caching chưa refresh hoặc sai URI | Cache freshness, wildcard, file naming |
| SQL đọc Parquet lỗi schema | Các files khác type hoặc writer drift | Check schema contract, quarantine |
| BigQuery CTAS/MERGE lỗi type | `SAFE_CAST` trả null, nguồn nhiều versions | DQ gates, dedup theo source version |
| Gold revenue tăng gấp đôi | Pub/Sub retry/CDS replay, dedup thiếu | `event_id`, checkpoint, MERGE uniqueness |
| Query đắt dù LIMIT nhỏ | Scan nhiều external files/native partitions | Dry run, partition filters, file compaction |
| Iceberg metadata không khớp Spark view | Snapshot/catalog stale, writer không phối hợp | Refresh/export metadata, commit protocol |
| Iceberg storage phình | Snapshots/files chưa được GC theo policy | Retention/optimization metrics, không rm files thủ công |
| IAM BigQuery đúng nhưng GCS không đọc được | Non-BigLake external cần quyền ở cả hai nơi | Phân biệt external table type |
| Data quality scan xanh nhưng dashboard sai | Business definition/reconciliation không được test | Owner kiểm tra KPI/late data |
| Bucket có data không thể xóa | Retention policy/Bucket Lock/lifecycle hold | Kiểm tra policy, không tìm cách bypass |
| Chênh lệch vùng/lưu dữ liệu | Bucket/dataset/connection location không tương thích | Kiểm tra data residency trước tạo |
| BI refresh quá chậm | Nhiều external files, cache/index/SQL chưa tối ưu | Mart native, cache phù hợp, alert cost |

**Thứ tự chẩn đoán:** data source → IAM/network/location → file schema → table type & metadata → DQ/lineage → SQL access path → query cost → BI definitions.

## 17. Bài tập ôn tập

1. **Data lake khác warehouse thế nào?** Lake giữ dữ liệu thô, nhiều định dạng; warehouse tổ chức bảng SQL đã chuẩn hóa cho analytics.
2. **Lakehouse có nghĩa “Parquet trong GCS” không?** Không; cần table format/catalog/snapshot và quản trị writes.
3. **BigLake external table lưu dữ liệu ở BigQuery managed storage?** Không, file ở GCS.
4. **Non-BigLake external table cần những quyền nào?** BigQuery và quyền đọc dữ liệu GCS ở caller.
5. **BigLake connection SA thay quyền GCS của analyst thế nào?** Access delegation; analyst có thể query table mà không cần direct bucket read.
6. **BigLake external table có update bằng BigQuery DML không?** Không; external BigLake là read-only.
7. **Managed Iceberg table có DML trong BigQuery không?** Có, theo khả năng/tài liệu được hỗ trợ.
8. **Iceberg metadata và Parquet có đồng nghĩa không?** Không; Iceberg là format quản lý table/snapshots.
9. **Tại sao cần Bronze?** Replay, source fidelity, traceability và điều tra.
10. **Tại sao không đưa file lỗi thẳng vào Silver?** Chất lượng/kiểu không đảm bảo, cần quarantine.
11. **Pub/Sub có tự loại mọi business duplicates không?** Không; cần event identity/checkpoint/dedup.
12. **Dataform có thay Pub/Sub/Dataflow không?** Không, chủ yếu quản lý SQL workflows/assertions.
13. **Catalog có cấp quyền đọc table không?** Không; IAM/policies kiểm soát quyền.
14. **Data lineage giúp gì?** Theo dõi upstream/downstream, impact analysis và audit.
15. **CMEK trên BigQuery table có bảo vệ file GCS external tự động?** Không.
16. **Cloud Storage Bucket Lock có nên bật thử trong lab?** Không; khóa retention là không thể đảo ngược.
17. **Khi query Gold chậm, tăng retention Raw có giúp không?** Không; cần xem SQL/partition/cache/capacity.
18. **Khi nào nên chọn native BigQuery hơn Iceberg?** Khi chỉ cần BigQuery analytics và muốn vận hành đơn giản.
19. **Tại sao data lake có thể thành data swamp?** Thiếu owner, metadata, quality, retention và quyền.
20. **Tại sao phải tính cả phí DCUs/GCS khi dùng Iceberg managed?** Vì chi phí không chỉ là BigQuery query compute.

## 18. Checklist production và tài liệu Google Cloud

- [ ] Use case và consumer/SLO rõ, đã so sánh lake/warehouse/lakehouse.
- [ ] Data contracts có owner, source ID, schema version, event time và retention.
- [ ] Đã quyết định raw/bronze/silver/gold có cần tất cả hay có thể gộp.
- [ ] Format Parquet/Avro/JSON và file size/partition design phù hợp workload.
- [ ] IAM phân lớp GCS, BigQuery và BigLake connection; không có direct access trái policy.
- [ ] Project, region, bucket/dataset/connection location phù hợp residency.
- [ ] BigLake external read-only không bị nhầm với Iceberg managed hỗ trợ DML.
- [ ] Iceberg multi-engine access có write ownership, snapshot/metadata và cleanup plan.
- [ ] Có schema validation, dedup/replay, DLQ và incremental update được kiểm thử.
- [ ] Silver/Gold có DQ gates, quality scores và business reconciliation.
- [ ] Knowledge Catalog ghi metadata/ownership/lineage có thể tra cứu.
- [ ] BigQuery row/column masking/policy tags có test theo principal thực.
- [ ] Data retention/backups/PII deletion áp dụng trên mọi bản sao/derived data.
- [ ] Theo dõi end-to-end freshness, failures, backlog, query p95 và cost per data unit.
- [ ] BigQuery dry run, maximum bytes billed, partition pruning đã được kiểm chứng.
- [ ] Có change approval, rollback/backfill, on-call runbook và ngân sách.

**Tài liệu chính thức (kiểm tra edition/region/feature tại thời điểm triển khai):**

- [BigQuery introduction to external sources](https://docs.cloud.google.com/bigquery/docs/external-data-sources) — phân biệt external/BigLake/object.
- [Create Cloud Storage BigLake tables](https://docs.cloud.google.com/bigquery/docs/create-cloud-storage-table-biglake) — BigLake connection, DDL, IAM.
- [BigLake tables overview](https://docs.cloud.google.com/bigquery/docs/biglake-intro) — access delegation, read-only, storage.
- [BigLake external metadata caching](https://docs.cloud.google.com/bigquery/docs/metadata-caching-external-tables) — cache freshness và hiệu năng.
- [Apache Iceberg managed tables in BigQuery](https://docs.cloud.google.com/bigquery/docs/biglake-iceberg-tables-in-bigquery) — open table format, GCS, DML/metadata.
- [BigQuery native tables](https://docs.cloud.google.com/bigquery/docs/tables-intro) — storage, views và DML.
- [Introduction to data governance in BigQuery](https://docs.cloud.google.com/bigquery/docs/data-governance) — catalog/quality/lineage.
- [Knowledge Catalog automatic data quality](https://docs.cloud.google.com/dataplex/docs/use-auto-data-quality) — DQ rules/scans.
- [Knowledge Catalog data lineage](https://docs.cloud.google.com/knowledge-catalog/docs/about-data-lineage) — tracing và impact.
- [Column-level access control](https://docs.cloud.google.com/bigquery/docs/column-level-security) — policy tags.
- [Cloud Storage uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access) — IAM thay ACLs.
- [Cloud Storage Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock) — retention không thể đảo ngược.
- [BigQuery best practices for costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs) — dry run, max bytes billed.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) và [Cloud Storage pricing](https://cloud.google.com/storage/pricing) — tổng chi phí.

**Ghi nhớ:** **Data lake** tối ưu giữ dữ liệu gốc và khả năng replay; **data warehouse** tối ưu SQL/BI có định nghĩa nghiệp vụ; **lakehouse** dùng open table format để kết hợp nhiều engines trên object storage. Trên GCP, điều cốt lõi không phải đặt tên kiến trúc mà là **đúng kiểu bảng, access controls, data quality/lineage, retention và khả năng kiểm chứng chi phí/SLO**.
