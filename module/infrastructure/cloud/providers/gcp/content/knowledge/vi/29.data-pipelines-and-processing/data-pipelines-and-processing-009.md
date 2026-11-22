# Lựa chọn Dataflow, Dataproc hoặc BigQuery cho biến đổi dữ liệu

Một công ty thương mại điện tử nhận **file đơn hàng mỗi đêm**, **sự kiện thanh toán liên tục qua Pub/Sub** và hàng TB dữ liệu Parquet từ hệ thống Spark cũ. Có thể dùng **BigQuery SQL**, **Dataflow/Apache Beam** hoặc **Managed Service for Apache Spark (trước đây là Dataproc)** để biến đổi dữ liệu; tuy nhiên mỗi công cụ tối ưu cho mô hình xử lý, mã nguồn và mức vận hành khác nhau.

Bài thuộc chương **Pipeline và xử lý dữ liệu** của học phần **CLOUD_PROVIDERS_GCP**, liên hệ với Cloud Storage, Pub/Sub, IAM, VPC, BigQuery, ứng dụng Java/Cloud Run, tự động hóa phát hành và giám sát chi phí. Mục tiêu là **chọn giải pháp dựa trên yêu cầu có thể đo được**, không mặc định dịch vụ nào luôn nhanh hoặc rẻ hơn.

Sau bài học, bạn có thể:

- Lựa chọn giữa **BigQuery ELT**, **Dataflow batch/stream** và **Spark batch/cluster** theo nguồn, độ trễ, engine, state và kỹ năng đội.
- Phân biệt *bounded/unbounded*, event time, window, watermark, late data, batch replay và idempotency.
- Tạo một bảng doanh thu thử nghiệm bằng **BigQuery GoogleSQL**, cùng phiên bản biến đổi bằng **PySpark** và **Java Apache Beam**.
- Hiểu sự khác biệt giữa Dataflow exactly-once trong pipeline và các side effects ngoài hệ thống; giữa Spark serverless với managed cluster.
- Xây kiến trúc kết hợp, tách dữ liệu raw/curated, backfill, schema evolution và kiểm tra chất lượng.
- Đo correctness, latency, throughput, bytes/slot-ms, backlog, shuffle, CPU, phí và SLO để quyết định.

> **Phạm vi lab:** đường dẫn project/bucket, service account và dữ liệu chỉ là ví dụ. Tạo BigQuery jobs, Dataflow workers hoặc Spark batches phát sinh chi phí; **không chạy trên production** hay tạo cluster chỉ để đọc bài. Các đoạn mã dùng cùng **hợp đồng dữ liệu** nhưng output khác định dạng; chỉ so sánh hiệu năng khi dataset và điều kiện đo giống nhau.

## 1. Ba engine, ba lợi thế

| Tiêu chí | **BigQuery** | **Dataflow** | **Managed Service for Apache Spark (Dataproc)** |
|---|---|---|---|
| Ngôn ngữ lõi | GoogleSQL, Dataform SQLX | Apache Beam Java/Python/Go; templates | Spark SQL, PySpark, Scala, Java |
| Mạnh nhất khi | Dữ liệu đã ở BigQuery, biến đổi quan hệ/aggregate bằng SQL | ETL/streaming từ nhiều nguồn, event time và window/state phức tạp | Spark/lakehouse jobs, data lake, thư viện OSS/legacy Spark |
| Batch | Query/DDL/DML/scheduled runs | Beam bounded pipeline | Spark batch (serverless hoặc cluster) |
| Streaming | **Continuous queries** cho các SQL patterns được hỗ trợ, còn giới hạn | **Thiết kế streaming chủ đạo**, Beam unbounded/windowing | Structured Streaming trong mô hình Spark/runtime hỗ trợ; cần quản lý checkpoint/capacity |
| Tính trạng thái và sự kiện muộn | SQL và continuous-query operations được hỗ trợ; không phải Beam đầy đủ | Watermark, windows, triggers, allowed lateness, state/timers | Spark windows/watermark/checkpoints theo chế độ |
| Hạ tầng | Không quản cluster SQL | Dataflow tự cấp workers, autoscaling/Streaming Engine | Serverless Spark theo job; cluster để tự quản sâu hơn |
| Đọc dữ liệu | Native BigQuery; external tables có điều kiện | Pub/Sub, GCS, BigQuery, JDBC, Kafka và nhiều IO connectors | GCS, Parquet/ORC, Iceberg/Hive, BigQuery connector, JDBC |
| Cách tính phí chính | Query compute theo on-demand bytes hoặc editions/slots; storage | Worker CPU/RAM, Streaming Engine/shuffle, network và storage | Serverless theo tài nguyên/job; cluster theo VM/disks + management |
| Rủi ro thường gặp | Scan bytes lớn, thiếu partition pruning, MERGE DML đắt | Late data, unbounded backlog, duplicate side effects, worker scaling | Shuffle/skew, driver memory, cluster idle cost, dependency/version |

**Tên sản phẩm hiện hành (2026):** Google Cloud đã hợp nhất **Dataproc** và **Serverless for Apache Spark** dưới thương hiệu **Managed Service for Apache Spark**. Các lệnh tương thích như `gcloud dataproc batches submit pyspark` và `gcloud dataproc clusters create` **vẫn được dùng**. Trong bài, “Dataproc/Spark” chỉ họ dịch vụ này, không đồng nghĩa một Spark batch bắt buộc chạy trên cluster VM.

Không có quan hệ thay thế 1:1: **BigQuery là SQL warehouse**, **Dataflow là runner cho Beam**, **Spark là compute engine phân tán**. Một kiến trúc có thể dùng cả ba khi thực sự có các workload khác nhau.

## 2. Cây quyết định trước khi viết pipeline

~~~mermaid
flowchart TD
  A["Cần biến đổi dữ liệu"] --> B{"Dữ liệu đã nằm trong BigQuery?"}
  B -- "Có" --> C{"SQL + lịch batch đủ đáp ứng?"}
  C -- "Có" --> Q["BigQuery SQL / scheduled query / Dataform"]
  C -- "Không" --> D{"SQL continuous query có hỗ trợ phép biến đổi?"}
  D -- "Có" --> CQ["Cân nhắc BigQuery continuous query"]
  D -- "Không" --> E{"Cần event-time windows, late data, state/IO đa nguồn?"}
  B -- "Không" --> E
  E -- "Có" --> F["Dataflow / Apache Beam"]
  E -- "Không" --> G{"Đang có Spark code hoặc cần lakehouse/OSS Spark?"}
  G -- "Có" --> H["Managed Spark serverless hoặc cluster"]
  G -- "Không" --> I["So sánh BigQuery load+SQL, Dataflow template và Spark batch"]
~~~

**Năm câu hỏi phải có câu trả lời trước khi chọn:**

1. **Tần suất/độ trễ:** 1 lần/đêm, mỗi 15 phút, hay cần cập nhật liên tục trong vài giây/phút?
2. **Nguồn và đích:** raw ở Cloud Storage, bảng BigQuery, Pub/Sub, Kafka, database CDC, lakehouse Iceberg hay hệ thống bên ngoài?
3. **Biến đổi:** SQL relational và aggregate, map/filter theo record, join nhiều dữ liệu lớn, ML library, window/state/event time?
4. **Ngữ nghĩa:** mất/đúp event có chấp nhận không; dữ liệu đến muộn được sửa thế nào; có cần replay và chống ghi trùng?
5. **Vận hành:** kỹ năng Java/Beam, Spark hay SQL; quota, thời gian chạy, logging, SLO, compliance và tổng chi phí?

### Quy tắc chọn nhanh

- **SQL trong BigQuery đủ làm việc** → ưu tiên biến đổi *in-place* bằng BigQuery/Dataform hoặc scheduled query; tránh xuất dữ liệu ra GCS rồi đọc lại bằng Spark không cần thiết.
- **Có Pub/Sub/Kafka/CDC với event time và late data**, windows phức tạp → bắt đầu với Dataflow/Beam; kiểm tra nguồn/sink IO và streaming semantics.
- **Có nhiều Spark SQL/PySpark/Scala hiện hữu**, Parquet/Iceberg/Hive, dependency tùy biến → cân nhắc Managed Spark, chọn **serverless** cho job theo đợt và **cluster** khi cần cấu hình/hệ sinh thái OSS sâu hoặc workload dài.
- **Chỉ chuyển thông điệp JSON từ Pub/Sub vào BigQuery** → đánh giá **Pub/Sub BigQuery subscription** hoặc Dataflow template trước khi viết custom Beam.
- **Cần điều phối nhiều jobs theo thứ tự** → dùng Workflows/Managed Airflow/Cloud Scheduler tùy phức tạp; **orchestrator không thay engine xử lý dữ liệu**.

## 3. Dataflow: Beam cho batch lẫn streaming

**Apache Beam** định nghĩa pipeline gồm `PCollection` và các phép biến đổi `PTransform`; **DataflowRunner** thực thi pipeline đó trên Dataflow. Một `PCollection` có thể **bounded** (file hữu hạn, batch) hoặc **unbounded** (Pub/Sub stream). Không phải mọi pipeline Beam chạy giống nhau: streaming cần chiến lược windowing, state, watermark và lối ra cho dữ liệu lỗi.

~~~text
Input Pub/Sub (unbounded)
  → parse + validate schema
  → dedup eventId / route invalid to DLQ
  → event-time window + watermark + allowed lateness
  → aggregate / enrich
  → BigQuery (Storage Write API) / GCS / Pub/Sub
                    ↑
       backlog, watermark lag, worker metrics
~~~

### Exactly-once không đồng nghĩa “side effect chỉ diễn ra một lần”

Dataflow streaming mặc định là **exactly-once processing mode** bên trong pipeline; có thể chọn **at-least-once mode** để giảm chi phí/độ trễ khi downstream xử lý được bản trùng. Tuy nhiên:

- Do retry, một `DoFn` **có thể chạy nhiều lần**, kể cả song song trong một số tình huống. Kết quả được dedup trong phạm vi bảo đảm của Dataflow, **không** đồng nghĩa một lần gọi REST API thanh toán bên trong `DoFn` chỉ diễn ra một lần.
- Với **sink** ra hệ thống ngoài như Pub/Sub, HTTP hoặc JDBC, semantics còn phụ thuộc connector/sink. BigQuery Storage Write API có chế độ exactly-once/at-least-once **tùy phương thức cấu hình**.
- Pub/Sub có thể giao lại cùng message; không dựa vào `messageId` để chống **business event** lặp nếu nhà sản xuất publish cùng sự kiện bằng hai messages khác nhau. Dùng `eventId` bền vững tại producer và idempotent sink.
- Exactly-once ở pipeline **không thay** unique business keys, upsert/dedup, outbox hay reconciliation ở data warehouse.

### Event time, processing time và watermark

Một đơn hàng được tạo lúc 10:02 nhưng tới Pub/Sub/Dataflow lúc 10:17:

| Khái niệm | Giá trị trong ví dụ | Vì sao quan trọng |
|---|---|---|
| **Event time** | 10:02 | Đơn hàng thuộc window nghiệp vụ 10:00–10:05 |
| **Processing time** | 10:17 | Thời điểm worker xử lý event |
| **Watermark** | Dự đoán tiến độ event time | Khi nào có thể coi phần lớn event của window đã tới |
| **Allowed lateness** | Ví dụ 30 phút | Chấp nhận late events trong khoảng sau window/watermark theo cấu hình |
| **Trigger/accumulation** | Early/on-time/late pane | Khi nào phát bản tổng hợp và có phát lại kết quả đã tích lũy không |

Một window 5 phút có thể phát kết quả **on-time** rồi **update** khi late event tới. Nếu sink chỉ `INSERT` vào BigQuery mà không có key/merge semantics, một dashboard có thể đếm trùng kết quả giữa các panes. Cần định nghĩa cách ghi: **upsert theo (storeId, windowStart, version)**, bảng append các revisions rồi lấy bản mới nhất, hoặc sink hỗ trợ mutation tương ứng.

**Khi nào không cần Dataflow?** Nếu job chỉ là `SELECT ... GROUP BY` trên BigQuery mỗi đêm, Beam thêm code/worker vận hành mà không tự mang lợi ích. Nếu luồng chỉ đẩy JSON tương thích schema từ Pub/Sub vào BigQuery, subscription trực tiếp có thể đủ, không cần Dataflow custom.

## 4. Managed Spark: serverless hay cluster?

Managed Service for Apache Spark cho phép giữ **Spark DataFrames, Spark SQL, PySpark/Scala/Java** và các thư viện JVM/Hive/Iceberg phù hợp. Đây là lựa chọn tự nhiên khi đội đang vận hành **Spark trên Hadoop/on-prem hoặc data lake** và cần chuyển job lên Google Cloud.

| Mô hình | Chọn khi | Đánh đổi |
|---|---|---|
| **Serverless Spark batches** (`gcloud dataproc batches submit ...`) | Job định kỳ/đột xuất; không muốn quản lý VM; ưu tiên pay-per-job | Hạn chế cấu hình hạ tầng so với cluster, cần chuẩn hóa artifacts/role/network |
| **Managed clusters** (`gcloud dataproc clusters ...`) | Cần cấu hình Spark/Hadoop, persistent services, HBase/Hive hoặc runtime đặc thù | Phải quản lý lifecycle, autoscaling, idle timeout, Compute Engine costs |
| **Spark Structured Streaming** | Có Spark streaming code/checkpoints và runtime phù hợp | Không mặc định mọi chế độ/serverless batch đều hợp cho job chạy mãi; phải xác minh hỗ trợ, checkpoint và restart |

Spark xử lý song song dựa trên **partitions và shuffle**. Hai dấu hiệu thường gặp:

- `groupBy`/`join` trên key rất lệch (một store có 90% events) → **data skew**, một vài tasks chạy chậm; cần partitioning/repartition/salt key khi hợp lý.
- Dataset nhỏ nhưng tạo cluster lớn → startup và idle cost cao hơn chính việc biến đổi. Với job theo đợt, thử serverless, giới hạn workers/executors và đo tổng thời gian.

**Không đánh đồng Spark và Dataflow:** Spark có Structured Streaming, nhưng Apache Beam trên Dataflow cung cấp mô hình windowing/trigger/late data riêng. Muốn chuyển giữa hai engine phải đối chiếu semantics, watermark, output mode, checkpoint và sink; không chỉ thay tên dịch vụ.

## 5. BigQuery: ELT/SQL trước khi tạo một engine khác

Khi dữ liệu đã được **load vào BigQuery**, GoogleSQL thường là đường ngắn nhất để lọc, join, chuẩn hóa, dedup, aggregate và ghi bảng curated.

| Tác vụ | BigQuery khả dụng | Cần cân nhắc |
|---|---|---|
| Chuẩn hóa staging thành curated | `CREATE TABLE AS SELECT`, `INSERT`, `MERGE`, `UPDATE` | Partition filters, quét bytes và idempotency |
| Transformation theo lịch | **Scheduled queries**, **Dataform**, BigQuery pipelines | Service account, dependencies, retry, backfill |
| Tổng hợp dùng nhiều lần | Materialized views/scheduled aggregate tables | Query rewrite, refresh, freshness, storage |
| Near-real-time SQL | **BigQuery continuous queries** | Những stateful JOIN/aggregate/window được hỗ trợ còn giới hạn, có Preview features |
| Data lake Parquet ngoài BigQuery | External/BigLake tables hoặc load sang native table | SQL support, quyền storage và hiệu năng từng connector |
| Tính toán phức tạp dùng thư viện Spark | Không phải thay thế trực tiếp runtime Spark | Đánh giá Managed Spark hoặc Dataflow |

**Cập nhật 2026:** BigQuery **continuous queries** không còn chỉ là cách lọc record đơn giản; có hỗ trợ một số stateful JOIN, aggregation và window operations **ở Preview**, nhưng vẫn **không** thay toàn bộ Beam/Spark streaming. Continuous queries có những hạn chế về SQL, RLS/column-level security, nguồn, destination và job lifecycle. Đừng kết luận tuyệt đối “BigQuery không xử lý stream”, cũng không mặc định mọi `MERGE`/`SELECT DISTINCT` đều chạy trong continuous query.

**SLO và chi phí:** BigQuery query jobs tiêu thụ capacity tính theo **on-demand bytes** hoặc **editions/slots**, có storage cost, query-result cache, scan và DML overhead. Sử dụng partition pruning, clustering, chỉ đọc cột cần thiết, giới hạn bytes billed và kiểm tra `INFORMATION_SCHEMA.JOBS` trước khi mua thêm slots.

## 6. Lab chung: cùng một hợp đồng đơn hàng cho ba engine

Ta biến đổi một file CSV có **8 rows**, gồm một event bị gửi trùng, một đơn bị hủy, một đơn đã hoàn tiền và một dòng `amount_minor < 0` không hợp lệ. Kết quả mong muốn là **doanh thu các đơn PAID hợp lệ theo ngày và cửa hàng**.

**Hợp đồng đầu vào:**

| Trường | Kiểu | Quy tắc |
|---|---|---|
| `event_id` | STRING | ID ổn định từ producer; lần gửi lại phải giữ nguyên ID/payload |
| `order_id` | STRING | ID đơn hàng nghiệp vụ, khác với message ID |
| `event_ts` | TIMESTAMP UTC | Thời điểm phát sinh sự kiện, không phải lúc file được tải lên |
| `store_id` | STRING | Cửa hàng được phép ghi nhận doanh thu |
| `amount_minor` | INT64 | Số nguyên theo đơn vị tiền nhỏ nhất, phải dương cho PAID |
| `status` | STRING | `PAID` / `CANCELLED` / `REFUNDED` |

Đây là **event stream rút gọn**. Trong hệ thống thực, một order có thể thay trạng thái, có hoàn tiền một phần, nhiều currency hoặc late adjustments. Đơn vị tiền tệ và business rules phải được quy định riêng; không dùng phép cộng tất cả `PAID` làm sổ cái tài chính chính thức.

### Bước 1 — tạo file dữ liệu mẫu

Lưu file `orders.csv` vào thư mục lab của người học:

~~~csv
event_id,order_id,event_ts,store_id,amount_minor,status
e-001,O-1001,2026-11-18T09:00:00Z,store-a,12500,PAID
e-002,O-1002,2026-11-18T09:01:00Z,store-a,5900,PAID
e-003,O-1003,2026-11-18T09:02:00Z,store-b,3000,CANCELLED
e-004,O-1004,2026-11-18T09:03:00Z,store-b,8900,PAID
e-004,O-1004,2026-11-18T09:03:00Z,store-b,8900,PAID
e-005,O-1005,2026-11-18T09:04:00Z,store-b,2500,PAID
e-006,O-1006,2026-11-18T09:05:00Z,store-a,1000,REFUNDED
e-007,O-1007,2026-11-18T09:06:00Z,store-a,-100,PAID
~~~

**Expected output** sau khi loại bản trùng `e-004`, bỏ `CANCELLED/REFUNDED` và số tiền không hợp lệ:

| sale_date | store_id | paid_orders | revenue_minor |
|---|---|---:|---:|
| 2026-11-18 | store-a | 2 | 18.400 |
| 2026-11-18 | store-b | 2 | 11.400 |

**Bất biến kiểm tra:** tổng số đơn PAID hợp lệ sau dedup là **4**, tổng doanh thu `29.800` minor units. Có **7 event_id khác nhau** trong 8 rows, trong đó 1 event sai amount; việc một duplicate có **payload khác** là vi phạm producer contract, phải chuyển sang quarantine/cảnh báo chứ không chọn tùy tiện một bản.

### Bước 2 — chuẩn bị GCS và BigQuery cho nhánh lab được chọn

~~~bash
PROJECT_ID="my-data-pipelines-lab"
REGION="asia-southeast1"
BUCKET="my-data-pipelines-lab-unique-bucket"
DATASET="pipeline_lab"

gcloud config set project "$PROJECT_ID"
gcloud services enable storage.googleapis.com bigquery.googleapis.com

# Chỉ tạo bucket/dataset mới nếu chưa tồn tại và đã được phép.
gcloud storage buckets create "gs://$BUCKET" --location="$REGION"
bq --location="$REGION" mk --dataset "$PROJECT_ID:$DATASET"
gcloud storage cp orders.csv "gs://$BUCKET/raw/orders.csv"
~~~

Tên bucket **globally unique**, tên ở trên chỉ là placeholder. Giữ **Cloud Storage, BigQuery dataset và processing region** tương thích với chính sách residency/egress của tổ chức; một dataset không tự đổi location. Từng phần lab dưới đây là **phương án thay thế**, không bắt buộc chạy cả ba và trả phí ba lần.

## 7. Phương án A — BigQuery SQL: ngắn nhất khi dữ liệu đích là BigQuery

Khi file đã ở Cloud Storage, dùng **load job** vào bảng raw rồi chạy một GoogleSQL transformation. Cách này phù hợp **hàng giờ/hàng ngày** hoặc pipeline dữ liệu đã ở BigQuery; không cần một cluster Spark chỉ để tính `GROUP BY`.

### Bước A1 — load CSV với schema tường minh

~~~bash
bq --location="$REGION" load \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --replace \
  "$PROJECT_ID:$DATASET.raw_order_events" \
  "gs://$BUCKET/raw/orders.csv" \
  "event_id:STRING,order_id:STRING,event_ts:TIMESTAMP,store_id:STRING,amount_minor:INT64,status:STRING"
~~~

`--replace` chỉ dành cho **lab có thể tái tạo**, sẽ ghi đè bảng nếu đã tồn tại. Trong production, giữ raw bất biến, nạp dữ liệu theo batch ID/date và ghi metadata nguồn, ingestion time. Load job hoàn tất **không đồng nghĩa business data hợp lệ**; phải chạy validation.

### Bước A2 — xác minh duplicate và dữ liệu không hợp lệ

Chạy trong BigQuery Studio tại location `asia-southeast1`, thay `MY_PROJECT` bằng project lab:

~~~sql
SELECT COUNT(*) AS raw_rows,
       COUNT(DISTINCT event_id) AS distinct_event_ids,
       COUNTIF(amount_minor <= 0) AS invalid_amount_rows
FROM `MY_PROJECT.pipeline_lab.raw_order_events`;

-- Event ID có payload MÂU THUẪN là dữ liệu cần quarantine.
SELECT event_id,
       COUNT(DISTINCT TO_JSON_STRING(STRUCT(
         order_id, event_ts, store_id, amount_minor, status
       ))) AS payload_variants
FROM `MY_PROJECT.pipeline_lab.raw_order_events`
GROUP BY event_id
HAVING payload_variants > 1;
~~~

Kỳ vọng truy vấn đầu trả `8, 7, 1`; truy vấn mâu thuẫn payload trả **0 hàng**. Với nguồn thực tế, triển khai **quarantine table** có lý do lỗi, nguồn, file/offset và thời gian nhận; không chỉ loại dòng không hợp lệ mà không lưu dấu vết.

### Bước A3 — CTAS có dedup, filter, aggregate

~~~sql
CREATE OR REPLACE TABLE `MY_PROJECT.pipeline_lab.daily_store_sales`
PARTITION BY sale_date
CLUSTER BY store_id
AS
WITH ranked AS (
  SELECT
    event_id, order_id, event_ts, store_id, amount_minor, status,
    ROW_NUMBER() OVER (
      PARTITION BY event_id
      ORDER BY event_ts DESC, order_id DESC
    ) AS rn
  FROM `MY_PROJECT.pipeline_lab.raw_order_events`
  WHERE event_id IS NOT NULL
)
SELECT
  DATE(event_ts) AS sale_date,
  store_id,
  COUNT(*) AS paid_orders,
  SUM(amount_minor) AS revenue_minor
FROM ranked
WHERE rn = 1 AND status = 'PAID' AND amount_minor > 0
GROUP BY sale_date, store_id;

SELECT sale_date, store_id, paid_orders, revenue_minor
FROM `MY_PROJECT.pipeline_lab.daily_store_sales`
ORDER BY sale_date, store_id;
~~~

Với dữ liệu mẫu, output khớp bảng ở mục 6. `ROW_NUMBER()` là đủ cho **bản trùng giống hệt** trong lab; trong production khi một `event_id` có **hai payload khác nhau**, phải quarantine trước khi chạy query — thứ tự tùy ý sẽ che mất lỗi tính tiền. Nếu nguồn có CDC updates, thiết kế version/sequence và `MERGE` theo business key, không coi một event ID như record state mới nhất.

**Idempotency:** `CREATE OR REPLACE TABLE ... AS SELECT` tái tạo kết quả từ toàn bộ raw, nên chạy lại với nguồn **không đổi** cho cùng output. Với bảng TB và incremental load, thay bằng **partitioned staging + MERGE theo batch/event keys**, pruning các partitions bị ảnh hưởng và kiểm tra trùng keys trước MERGE; scan toàn bộ mỗi giờ có thể tốn kém.

### Bước A4 — đưa vào lịch/Dataform

- **Scheduled query:** dùng BigQuery Data Transfer Service để chạy SQL theo giờ/ngày, identity có quyền query/write, đặt lịch và kiểm soát chạy trùng/backfill.
- **Dataform:** khai báo DAG bảng raw → validated → daily sales bằng SQLX, có assertions về unique keys, non-null, giá trị hợp lệ; phù hợp khi có nhiều SQL transformations phụ thuộc nhau.
- **BigQuery continuous query:** cân nhắc nếu dữ liệu đã streaming vào BigQuery và phép biến đổi nằm trong tập được hỗ trợ; không giả định CTAS, `ROW_NUMBER` hay `MERGE` trong ví dụ trên được dùng nguyên vẹn làm continuous query.

**Giới hạn:** BigQuery là analytics engine; dữ liệu mới từ OLTP có thể cần CDC/ingestion và thời gian cập nhật. Không dùng dashboard `daily_store_sales` để xác nhận thanh toán ngay sau commit khi business đòi strongly consistent OLTP read.

## 8. Phương án B — Managed Spark: PySpark cho data lake và job batch

Spark phù hợp nếu CSV chỉ là một phần trong **lakehouse Parquet/ORC**, cần ghép nhiều tập dữ liệu ngoài BigQuery, có thư viện PySpark/JVM đang dùng hoặc muốn giữ engine đồng nhất giữa các hệ thống.

Lưu file **`orders_etl.py`** trong project lab, đầu vào và đầu ra là GCS URIs:

~~~python
import sys
from pyspark.sql import SparkSession, functions as F, types as T

if len(sys.argv) != 3:
    raise SystemExit("Usage: orders_etl.py INPUT_CSV OUTPUT_PARQUET")

input_uri, output_uri = sys.argv[1], sys.argv[2]
spark = SparkSession.builder.appName("orders-daily-sales").getOrCreate()

schema = T.StructType([
    T.StructField("event_id", T.StringType(), False),
    T.StructField("order_id", T.StringType(), False),
    T.StructField("event_ts", T.TimestampType(), False),
    T.StructField("store_id", T.StringType(), False),
    T.StructField("amount_minor", T.LongType(), False),
    T.StructField("status", T.StringType(), False),
])

raw = (
    spark.read.option("header", "true")
    .option("mode", "FAILFAST")
    .schema(schema)
    .csv(input_uri)
)

# Chỉ đúng cho lab: những rows trùng event_id có payload giống hệt.
# Trong production, kiểm tra sự kiện mâu thuẫn và quarantine trước dedup.
deduped = raw.dropDuplicates(["event_id"])

daily = (
    deduped.filter(
        (F.col("status") == "PAID") & (F.col("amount_minor") > 0)
    )
    .withColumn("sale_date", F.to_date("event_ts"))
    .groupBy("sale_date", "store_id")
    .agg(
        F.count(F.lit(1)).alias("paid_orders"),
        F.sum("amount_minor").alias("revenue_minor"),
    )
)

daily.orderBy("sale_date", "store_id").show(truncate=False)
# Chỉ overwrite đường output DÀNH RIÊNG cho lab.
daily.write.mode("overwrite").parquet(output_uri)
spark.stop()
~~~

**Đặc điểm đáng nhớ:** `dropDuplicates(["event_id"])` sẽ cần shuffle/state phù hợp; nếu cùng ID có payload khác nhau, Spark **không bảo đảm chọn hàng nào** khi không có business sequence rõ ràng. Với dữ liệu nhiều TB, quan sát **shuffle read/write, skew, number of partitions, executor memory**. `FAILFAST` chỉ xử lý lỗi parse; business validation như amount âm vẫn phải tách quarantine thay vì silently drop.

### Gửi Spark batch serverless

Sau khi platform team tạo **runtime service account** có quyền thích hợp (ví dụ `roles/dataproc.worker` và quyền đọc/ghi đúng bucket), copy code lên GCS:

~~~bash
gcloud services enable dataproc.googleapis.com \
  --project="$PROJECT_ID"

SPARK_SA="spark-batch@$PROJECT_ID.iam.gserviceaccount.com"
gcloud storage cp orders_etl.py "gs://$BUCKET/code/orders_etl.py"

gcloud dataproc batches submit pyspark \
  "gs://$BUCKET/code/orders_etl.py" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service-account="$SPARK_SA" \
  --batch="orders-etl-lab-001" \
  -- \
  "gs://$BUCKET/raw/orders.csv" \
  "gs://$BUCKET/out/spark-daily-sales/"

# Xem batch sau khi nộp/chạy, không nhầm ID với cluster name.
gcloud dataproc batches describe orders-etl-lab-001 \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Tên batch phải **duy nhất trong phạm vi yêu cầu**; nếu ID đã tồn tại, dùng ID khác sau khi kiểm tra kết quả cũ. Đây là **Managed Spark serverless batch**, không tạo VM cluster thường trực. Đối với chạy cluster, tham số, startup/shutdown, autoscaling và chi phí khác; không dùng lệnh `batches submit` như thể quản lý cluster VM.

**Kết quả PySpark**: hai hàng với `store-a = (2, 18400)` và `store-b = (2, 11400)`. Đường output là **Parquet directory** có nhiều part-files, không phải một file CSV. Nếu cần đưa vào BigQuery, sử dụng **BigQuery connector** hoặc load job; ghi Parquet ra GCS **không tự tạo** bảng BigQuery.

## 9. Phương án C — Dataflow/Java Apache Beam cho batch

Beam thích hợp nếu cùng hệ thống còn phải xử lý **Pub/Sub stream** bằng event-time windows, hoặc team có các transform Java/Beam cần tái sử dụng. Trước tiên chạy **bounded pipeline** từ cùng CSV trong GCS, tạo số tiền tổng theo cửa hàng/ngày để so với BigQuery/Spark.

Ví dụ dưới dùng **Java 17** và Beam Java SDK tương thích Dataflow. Trong một Maven project Beam chuẩn, cần dependencies `beam-sdks-java-core`, `beam-sdks-java-io-google-cloud-platform`, `beam-runners-google-cloud-dataflow-java`, và plugin chạy main class (ví dụ Maven Exec Plugin), **cùng phiên bản Beam SDK được Dataflow hỗ trợ**. Không tự phối các phiên bản runner/SDK khác nhau.

**`src/main/java/example/SalesBeam.java`**

~~~java
package example;

import org.apache.beam.runners.dataflow.options.DataflowPipelineOptions;
import org.apache.beam.sdk.Pipeline;
import org.apache.beam.sdk.io.TextIO;
import org.apache.beam.sdk.options.Description;
import org.apache.beam.sdk.options.PipelineOptionsFactory;
import org.apache.beam.sdk.options.Validation;
import org.apache.beam.sdk.transforms.Distinct;
import org.apache.beam.sdk.transforms.DoFn;
import org.apache.beam.sdk.transforms.Filter;
import org.apache.beam.sdk.transforms.MapElements;
import org.apache.beam.sdk.transforms.ParDo;
import org.apache.beam.sdk.transforms.Sum;
import org.apache.beam.sdk.values.KV;
import org.apache.beam.sdk.values.TypeDescriptors;

public final class SalesBeam {
    public interface Options extends DataflowPipelineOptions {
        @Description("CSV file input, including header")
        @Validation.Required
        String getInput();
        void setInput(String value);

        @Description("Cloud Storage output prefix")
        @Validation.Required
        String getOutputPrefix();
        void setOutputPrefix(String value);
    }

    public static void main(String[] args) {
        Options opts = PipelineOptionsFactory.fromArgs(args)
            .withValidation().as(Options.class);
        Pipeline p = Pipeline.create(opts);

        p.apply("ReadCSV", TextIO.read().from(opts.getInput()))
         .apply("SkipHeader", Filter.by(
             (String line) -> !line.startsWith("event_id,")))
         // Chỉ loại bản trùng GIỐNG HỆT trong lab.
         // Production cần dedup theo event_id và báo lỗi payload conflict.
         .apply("DeduplicateExactRows", Distinct.create())
         .apply("ValidateAndMap", ParDo.of(
             new DoFn<String, KV<String, Long>>() {
                 @ProcessElement
                 public void process(
                         @Element String line,
                         OutputReceiver<KV<String, Long>> out) {
                     // CSV đơn giản: không chứa dấu phẩy trong quoted fields.
                     // Production: dùng parser/schema, DLQ cho malformed rows.
                     String[] c = line.split(",", -1);
                     if (c.length != 6) {
                         throw new IllegalArgumentException("Malformed CSV");
                     }
                     long amount = Long.parseLong(c[4]);
                     if (!"PAID".equals(c[5]) || amount <= 0) {
                         return;
                     }
                     String saleDate = c[2].substring(0, 10);
                     String key = saleDate + "," + c[3];
                     out.output(KV.of(key, amount));
                 }
             }))
         .apply("SumByDateStore", Sum.longsPerKey())
         .apply("AsCSV", MapElements
             .into(TypeDescriptors.strings())
             .via((KV<String, Long> kv) ->
                 kv.getKey() + "," + kv.getValue()))
         // Một output file CHỈ cho lab nhỏ; production nên sharding.
         .apply("WriteCSV", TextIO.write()
             .to(opts.getOutputPrefix())
             .withSuffix(".csv")
             .withoutSharding());

        p.run().waitUntilFinish();
    }
}
~~~

Khác hai lab trước, output Beam trên đây chỉ có **`sale_date,store_id,revenue_minor`** (không có `paid_orders`). Mục đích là cho thấy `PTransform`/`KV`/`Sum.longsPerKey` và kiểm tra **cùng tổng doanh thu**; muốn có count, dùng một aggregate kết hợp `Count.perKey`/custom `CombineFn` hoặc biểu diễn value dạng `(count, amount)`. **Không so một cột output thiếu với số liệu count rồi kết luận engine sai**.

**Giới hạn của ví dụ tối giản:** `Distinct.create()` chỉ loại các dòng **trùng text chính xác** và cần shuffle; không đủ để phát hiện cùng `event_id` nhưng amount khác. `ParDo` throws với CSV hỏng, khiến job fail/retry; pipeline production phải đưa bad records ra **dead-letter output** và ghi lý do lỗi. `withoutSharding()` hạn chế tính song song của output; bỏ tùy chọn đó khi xử lý file lớn.

### Chạy Beam local trước, rồi gửi Dataflow

Trong Maven project đã có SDK, I/O, Dataflow runner và plugin exec:

~~~bash
# Local bounded run: không tạo Dataflow workers.
mvn -q compile exec:java \
  -Dexec.mainClass=example.SalesBeam \
  -Dexec.args="--runner=DirectRunner --input=orders.csv --outputPrefix=out/sales"

# Dataflow remote: cần worker SA, temp/staging bucket và IAM trước.
DF_SA="dataflow-worker@$PROJECT_ID.iam.gserviceaccount.com"
mvn -q -Pdataflow-runner compile exec:java \
  -Dexec.mainClass=example.SalesBeam \
  -Dexec.args="--runner=DataflowRunner --project=$PROJECT_ID --region=$REGION --gcpTempLocation=gs://$BUCKET/tmp --serviceAccount=$DF_SA --input=gs://$BUCKET/raw/orders.csv --outputPrefix=gs://$BUCKET/out/beam/sales"
~~~

**Điều kiện cần:** `DirectRunner` phải có dependency `beam-runners-direct-java` trong profile local; Dataflow runner profile phải tồn tại trong `pom.xml`. Lệnh trên **không tự tạo các Maven profiles**. Trên Dataflow, worker SA cần quyền worker/đọc input/ghi staging/output, launcher cần quyền tạo job và `iam.serviceAccounts.actAs` nếu gắn worker SA. Dataflow Workers thường chạy trong VPC của project; network, subnet, firewall và private access tới Google APIs cũng phải phù hợp.

Kỳ vọng output (có thể khác thứ tự hàng):

~~~csv
2026-11-18,store-a,18400
2026-11-18,store-b,11400
~~~

### Nếu cần streaming thật: chọn Beam hoặc template

Biến bounded pipeline thành streaming **không đơn giản đổi `--streaming=true`** rồi tiếp tục dùng `Distinct.create()` không giới hạn: lưu state của tập ID trên stream vô hạn sẽ tăng không kiểm soát nếu không có cửa sổ/TTL. Phải quyết định:

1. Source `PubsubIO.read...` và event timestamp attribute/parse event time.
2. `Window.into(FixedWindows...)`, watermark, allowed lateness, early/late firings.
3. Dedup theo `event_id` với state expiry/window và late-arrival contract; không dựa vào thứ tự messages.
4. Sink có semantics cụ thể (ví dụ BigQuery Storage Write API), business key và cách upsert kết quả window revisions.
5. DLQ/quarantine, backlog monitoring và phương án replay từ nguồn bền vững.

Đối với luồng **chỉ đưa JSON từ Pub/Sub vào BigQuery**, trước khi code hãy đánh giá template có sẵn:

~~~bash
# Chỉ là ví dụ: yêu cầu subscription/tables/schema đã được tạo đúng,
# và pipeline sẽ chạy STREAMING cho tới khi drain/cancel.
gcloud dataflow jobs run "orders-pubsub-to-bq-lab" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --gcs-location="gs://dataflow-templates/latest/PubSub_Subscription_to_BigQuery" \
  --staging-location="gs://$BUCKET/staging" \
  --parameters="inputSubscription=projects/$PROJECT_ID/subscriptions/orders-events-sub,outputTableSpec=$PROJECT_ID:$DATASET.raw_order_events"
~~~

Template này yêu cầu **Pub/Sub payload JSON có schema khớp bảng BigQuery đã tồn tại**, không tự tạo `daily_store_sales` hay tự dedup/aggregate theo business rules của lab. Nó có thể tạo dead-letter table tùy cấu hình. Nếu cần lọc/transform JSON đơn giản, kiểm tra template UDF hoặc Pub/Sub **BigQuery subscription** trước khi chọn custom Dataflow streaming.

**Điều kiện dừng:** streaming job chạy liên tục **phát sinh phí khi không có message**. Để shutdown có kiểm soát, xem trạng thái và lựa chọn **drain** (cố hoàn tất inflight work khi được hỗ trợ) hoặc **cancel** (dừng nhanh, cần đối soát/replay):

~~~bash
gcloud dataflow jobs list --project="$PROJECT_ID" --region="$REGION"
# Không chạy drain/cancel khi chưa xác nhận đúng JOB_ID và owner.
~~~

## 10. So sánh kết quả và đặc tính ba bản lab

| Kết quả hoặc đặc tính | BigQuery SQL | Spark PySpark | Dataflow Beam Java |
|---|---|---|---|
| Đầu vào | BigQuery raw table từ CSV | CSV trên GCS | CSV trên GCS |
| Dedup trong lab | `ROW_NUMBER` theo event_id | `dropDuplicates(event_id)` | `Distinct` theo **toàn dòng** |
| Filter | `status=PAID`, amount dương | Tương đương | Tương đương |
| Output | BigQuery partitioned table | GCS Parquet directory | GCS CSV file |
| `store-a` revenue | **18.400** | **18.400** | **18.400** |
| `store-b` revenue | **11.400** | **11.400** | **11.400** |
| Count paid | 2 + 2 | 2 + 2 | Chưa tính trong ví dụ |
| Tái chạy | CTAS thay bảng output | Overwrite output prefix | TextIO sẽ cần output path mới/cleanup |
| Chức năng streaming | SQL continuous query riêng | Structured Streaming theo runtime | Beam unbounded pipeline với window/state |

**Không suy ra engine nào nhanh nhất từ file 8 rows.** Chi phí startup/worker có thể lớn hơn CPU xử lý; benchmark hợp lệ phải dùng đủ dữ liệu, tính lại đúng business semantics, kiểm soát input location, concurrency và cache.

## 11. Thiết kế kiến trúc kết hợp theo loại dữ liệu

Một doanh nghiệp không nhất thiết chọn một engine cho mọi nguồn:

~~~mermaid
flowchart LR
  F["GCS: file bán hàng mỗi đêm"] --> L["BigQuery load job"]
  L --> S["BigQuery SQL / Dataform"]
  P["Pub/Sub: sự kiện real-time"] --> D["Dataflow Beam streaming"]
  D --> R["BigQuery raw events"]
  R --> S
  K["Lake Parquet / legacy Spark jobs"] --> SP["Managed Spark batch"]
  SP --> O["GCS curated Parquet / BigQuery"]
  O --> S
  S --> V["BigQuery marts / BI dashboards"]
  M["Workflows / Scheduler / Airflow"] --> L
  M --> SP
  M --> S
~~~

**Nguyên tắc raw → validated → curated:**

1. **Raw/landing:** giữ nguồn gốc, `event_id`, source offset/file URI, thời gian nhận và schema version. Quy trình phải có cách đọc lại dữ liệu khi pipeline lỗi.
2. **Validated/quarantine:** tách bản ghi sai schema, currency, thiếu ID, negative amount và event ID mâu thuẫn; không âm thầm “drop tất cả lỗi” rồi báo thành công.
3. **Curated:** chuyển đổi đã dedup và business rules rõ, ghi theo batch ID/partition để dễ kiểm tra và replay.
4. **Marts:** bảng tổng hợp `daily_store_sales` có độ mới được công bố rõ cho BI; không dùng như nguồn xác nhận thanh toán OLTP.

**Điều phối vs xử lý:** Cloud Scheduler kích hoạt chạy định kỳ; Workflows/Managed Airflow biểu diễn dependency `load → validate → aggregate → check → publish`. Dataflow/Spark/BigQuery mới là nơi thực hiện phần xử lý dữ liệu phân tán. Kết nối từ Eventarc/Pub/Sub cũng có thể bị giao trùng: orchestrator phải dùng **run ID/batch ID** để không khởi tạo hai jobs ghi đè nhau.

### Xử lý late data và backfill

- **BigQuery:** lưu sự kiện gốc, chạy lại các **partitions bị ảnh hưởng**, dùng `MERGE`/CTAS có phạm vi và business sequence. Đừng backfill dữ liệu 3 năm bằng query quét toàn bảng mỗi giờ.
- **Dataflow:** ấn định watermark, allowed lateness, triggers, retention của state; dữ liệu tới sau allowed lateness cần DLQ/backfill path, không mặc định tự sửa dashboard.
- **Spark:** ghi batch outputs **versioned hoặc partitioned**, lưu checkpoint/job inputs để chạy lại từ GCS. Với Structured Streaming phải có **checkpoint location bền vững** và sink upsert/dedup semantics.
- **Tất cả:** tránh hai writers cùng `overwrite` một output khi retry; dùng staging + validation + atomic publish/swap view khi hệ thống cho phép.

## 12. IAM, mạng và dữ liệu nhạy cảm

**Deployer/orchestrator identity khác runtime identity**. Một tài khoản có quyền tạo job không có nghĩa workers cũng có quyền đọc GCS/ghi BigQuery; và việc cấp quyền đọc bucket cho workers không cho chúng quyền sửa pipeline code.

| Thành phần | Runtime identity và quyền thường cần | Không nên cấp |
|---|---|---|
| **BigQuery scheduled query / Dataform execution** | SA có `bigquery.jobs.create` ở billing project, quyền đọc bảng nguồn, ghi bảng đích | Project Owner cho SQL analyst |
| **Dataflow workers** | Worker SA với role phù hợp, Storage Object Viewer/Creator trên đúng paths/buckets, Pub/Sub Subscriber, BigQuery write nếu cần | Editor toàn project chỉ để đọc GCS |
| **Managed Spark serverless** | Batch workload SA có Dataproc Worker theo yêu cầu sản phẩm, GCS permissions, BigQuery roles nếu dùng connector | Compute Admin mặc định cho từng Spark job |
| **CI/CD launcher** | Quyền deploy/job create và `iam.serviceAccounts.actAs` trên workload SA được phê duyệt | Service Account Token Creator trên mọi SA |
| **Operations/SRE** | Job/metrics/log reader; chỉ có quyền stop/drain/delete khi được giao | Quyền xem PII nếu chỉ cần metrics |

Kiểm soát mạng:

- Workers/managed Spark thường cần truy cập Cloud Storage, BigQuery, Pub/Sub và các service APIs; trong **private subnet** kiểm tra **Private Google Access/Private Service Connect for Google APIs**, route, firewall, DNS, VPC Service Controls và NAT khi cần Internet.
- Với **GCS/BigQuery cross-project**, cấp IAM cho **đúng workload SA** trên resource project, không nhầm account của developer hoặc Compute Engine default SA.
- Dữ liệu ngân hàng/PII cần mã hóa, chính sách retention, CMEK khi bắt buộc, phân vùng tenant/authorized views, audit logs và **không ghi raw payload, secret hoặc access token** vào worker logs.
- Các connector đọc JDBC/SQL phải dùng Secret Manager/credentials ngắn hạn, TLS và network path phù hợp; không nhúng DB password trong command args hoặc source.

**Chú ý BigQuery row-level/column-level policies:** chúng áp vào truy vấn theo quyền caller. Đừng tắt chính sách bảo mật chỉ để Spark hoặc Dataflow chạy nhanh; chọn service account được cấp quyền tối thiểu hoặc thiết kế data products/authorized views phù hợp.

## 13. Độ tin cậy, hiệu năng và tổng chi phí

### Đo theo cùng một bộ dữ liệu

Giữ cố định input size, schema, partitioning, region, output format, yêu cầu dedup, số bản ghi lỗi và độ mới đầu ra. Đo **từ lúc khởi chạy đến khi output kiểm tra thành công**, không chỉ thời gian transform lõi:

| Thước đo | BigQuery | Dataflow | Managed Spark |
|---|---|---|---|
| Latency | Job creation/elapsed time, query stages | Job startup, system lag/watermark lag (stream), end-to-end latency | Batch startup, driver/executor runtime |
| Throughput | Bytes processed, rows/s, slot-ms | Elements/s, input bytes, worker CPU, backlog | Records/s, shuffle bytes, stages/tasks |
| Correctness | Duplicates/quarantine, reconciliation SQL | Late/invalid count, watermark, DLQ, sink errors | Invalid records, dedup conflicts, stage retry |
| Scale bottleneck | Partition pruning, JOIN shuffle, slot contention | Hot keys, state size, slow transforms, Pub/Sub backlog | Skew, partition count, shuffle spill/OOM |
| Costs | On-demand bytes/slots, storage, DML | CPU/RAM, Streaming Engine/shuffle, VM/network, I/O | Serverless compute/DCUs/shuffle hoặc cluster VM uptime |

**Công thức tính chi phí end-to-end (mang tính định tính):**

~~~text
Tổng chi phí = ingest + nguồn/lưu trữ + compute
             + shuffle/streaming state + network/egress
             + sink writes + logging/monitoring + vận hành
~~~

- Dataflow streaming có **workers chạy liên tục**; không suy giá từ số event/ngày mà bỏ qua giờ idle, Streaming Engine, shuffle và state.
- Managed Spark **serverless** tối ưu cho job ngắt quãng, tính theo tài nguyên/run; **cluster** còn phí VM/disks và thời gian idle nếu không dừng. Không kết luận serverless luôn rẻ hơn ở tải 24/7.
- BigQuery SQL có thể rẻ và đơn giản khi mọi dữ liệu đã ở warehouse, nhưng query scan TB nhiều lần hoặc `MERGE` thiếu partition pruning sẽ tốn kém; một query scheduled sai có thể lặp phí hàng ngày.
- Dữ liệu qua nhiều region/project có thể phát sinh phí **network egress** và ảnh hưởng residency; để pipeline/sink cùng region khi khả thi.

### SLO mẫu cho ba workload

| Workload | SLO cần xác minh | Công cụ phù hợp để thử đầu tiên |
|---|---|---|
| File CSV nạp lúc 02:00, báo cáo phải hoàn tất trước 03:00 | Job finish P95 dưới 1 giờ, reconciliation pass | BigQuery load + SQL/Dataform |
| Đơn hàng Pub/Sub cần cảnh báo trong 30 giây | End-to-end event lag P95 dưới 30 giây, late-data contract | Dataflow streaming |
| Hàng TB Parquet và Spark libraries cũ chạy vào cuối tuần | Batch trong 3 giờ, không để cluster idle sau job | Managed Spark serverless hoặc cluster có autoscaling |

Mỗi SLO cần **ngưỡng cảnh báo, owner và phương án xử lý**. Không đo riêng `job SUCCEEDED` khi business output sai hoặc thiếu 0,1% events.

## 14. Runbook lỗi và phương án xử lý

| Triệu chứng | Nguyên nhân thường gặp | Bước điều tra ưu tiên |
|---|---|---|
| BigQuery `PERMISSION_DENIED` khi load/query | Job SA thiếu quyền jobUser/dataViewer/dataEditor trên đúng project/dataset | Kiểm tra principal của job và dataset IAM |
| BigQuery `Not found: Dataset ... location` | Dataset và query job region khác nhau | Dataset location, job location |
| BigQuery báo cáo bị trùng | Re-run append, event IDs trùng, `MERGE` sai key | Raw duplicates, input batch ID, curated uniqueness |
| BigQuery bill/query time tăng | Full table scan, thiếu partition filter, JOIN shuffle lớn | `INFORMATION_SCHEMA.JOBS`, query plan, bytes/slot-ms |
| Dataflow `RUNNING` nhưng output không đổi | Không có events, watermark lag, sink errors, backlog | Worker logs, input subscriptions, system lag, dead letters |
| Dataflow có bản ghi trùng sau retry | External side effect/sink không idempotent, producer republish | Event ID, sink semantics, dedup state |
| Dataflow window ra muộn/sai count | Timestamp assignment, watermark, allowed lateness/triggers | Window configuration và pane/retraction strategy |
| Dataflow workers không truy cập storage | Worker SA thiếu IAM hoặc VPC/DNS/Private Google Access | Service account, network path, API errors |
| Spark batch `FAILED`/Python dependency lỗi | Runtime version, package/JAR, Python mismatch | Driver logs, batch runtime config, artifacts |
| Spark job chậm/OOM | Skew, shuffle spill, số partitions/driver memory | Spark UI stages, executors, shuffle/skew metrics |
| Spark output trống | Sai GCS URI, filter loại hết dữ liệu, schema cast lỗi | Input row count/schema và transformation stages |
| Cả ba output không khớp | Khác semantics dedup, timezone, currency hoặc late data | So theo event IDs + hợp đồng dữ liệu, không chỉ totals |

### Lệnh quan sát chỉ đọc

~~~bash
# Dataflow:
gcloud dataflow jobs list --project="$PROJECT_ID" --region="$REGION"

# Managed Spark batches:
gcloud dataproc batches list --project="$PROJECT_ID" --region="$REGION"
gcloud dataproc batches describe orders-etl-lab-001 \
  --project="$PROJECT_ID" --region="$REGION"

# BigQuery:
bq --location="$REGION" ls "$PROJECT_ID:$DATASET"
bq --location="$REGION" show "$PROJECT_ID:$DATASET.daily_store_sales"
~~~

Đối với BigQuery query jobs, xem `INFORMATION_SCHEMA.JOBS_BY_PROJECT` tại region tương ứng để phân tích `total_bytes_processed`, `total_slot_ms` và `error_result`. Với Dataflow sử dụng Monitoring theo job/worker, **backlog và system lag** quan trọng hơn trạng thái RUNNING. Với Spark, xem **driver logs và Spark UI**, không chỉ job state.

## 15. Migration và triển khai không gây gián đoạn

1. **Inventory:** nguồn, sinks, schemas, dependencies, partitions, watermark/checkpoint, IAM/locations và chi phí hiện tại.
2. **Golden dataset:** tạo input có trùng event ID, late events, null fields, negative amount, invalid schema, timezone edges và các trường hợp nghiệp vụ đặc biệt.
3. **Chạy song song (shadow):** engine mới ghi vào **dataset/output prefix riêng**, không ghi đè curated production. Đối soát event IDs, record counts và revenue theo partition.
4. **Canary:** một phần dữ liệu hoặc một store/partition; đo correctness, P95 latency, backlog/shuffle, cost và downstream load.
5. **Cutover:** đổi scheduler/orchestrator hoặc view/table alias sau khi kết quả kiểm tra đạt; xác nhận không còn hai writers cùng publish.
6. **Rollback:** quay lại output/engine cũ còn khả dụng, replay từ raw bằng event IDs/batch IDs; không xóa checkpoint hoặc Pub/Sub subscription khi chưa có kế hoạch dữ liệu tồn đọng.
7. **Cleanup:** tắt job/cluster/running streaming pipeline **đúng owner**, xóa lab resources khi được phép và rà soát IAM đã cấp.

**Nếu chuyển Spark → BigQuery**, kiểm tra khác biệt SQL dialect, xử lý null, timezone, duplicate ordering, UDF, decimal precision và transaction semantics. **Nếu chuyển Spark Structured Streaming → Beam**, review windows/watermarks/output modes và state retention trước khi thay công cụ; kết quả giống nhau trên batch test không chứng minh giống nhau ở late events.

## 16. Checklist trước production

- [ ] Đã ghi rõ nguồn/đích, schema, business keys, event time và timezone.
- [ ] Đã phân loại batch, micro-batch, streaming và mục tiêu end-to-end SLO.
- [ ] Đã đánh giá SQL BigQuery trước khi tự tạo Dataflow/Spark cho một phép aggregate đơn giản.
- [ ] Với streaming, có watermark/late events/dedup và sink idempotency strategy.
- [ ] Có raw retention, replay/backfill, DLQ/quarantine và schema evolution plan.
- [ ] Không dùng `Distinct.create()` không giới hạn cho unbounded stream.
- [ ] Spark batch có versioned artifacts, network/SA, kiểm soát shuffle/skew và job output.
- [ ] BigQuery tables partition/cluster theo query, transformations có kiểm thử và limit scan.
- [ ] Runtime SA khác deployer, quyền hẹp trên GCS/PubSub/BigQuery và không có key JSON.
- [ ] Có data-quality assertions (counts, uniqueness, monetary totals), không chỉ health status.
- [ ] Có dashboard latency, throughput, backlog, error rate, cost và freshness.
- [ ] Đã benchmark bằng dữ liệu đủ lớn và cùng semantics; startup và output validation được tính vào phép đo.
- [ ] Có canary, rollback, IAM audit và trách nhiệm dọn cloud resources.

## 17. Bài tập vận dụng

**Bài 1 — Chọn engine.** Phân loại ba trường hợp: (a) SQL aggregate bảng BigQuery mỗi đêm, (b) Pub/Sub streaming cần event-time windows và late data, (c) 4 TB Parquet với PySpark/UDF/JAR cũ. Giải thích không chỉ lựa chọn dịch vụ mà cả mode chạy và chi phí.

**Bài 2 — BigQuery dedup.** Với tám rows ở mục 6, thực thi SQL `ROW_NUMBER` và tính doanh thu/store. Nếu event `e-004` được publish lần thứ ba với amount khác, vì sao không thể chọn một payload tùy ý mà vẫn gọi là đúng nghiệp vụ?

**Bài 3 — PySpark.** Mở rộng `orders_etl.py` để tạo thêm `paid_orders`, ghi output partitioned theo `sale_date`. Chỉ ra chi phí shuffle của `dropDuplicates` và `groupBy` khi dữ liệu rất lớn.

**Bài 4 — Beam Java.** Thêm count vào `SalesBeam` và trả về bốn cột như BigQuery. Giải thích tại sao `Distinct.create()` theo dòng chỉ phù hợp với dữ liệu trùng hoàn toàn trong lab và cần state/window hợp lý khi streaming.

**Bài 5 — Streaming semantics.** Một `DoFn` gọi thanh toán HTTP rồi job retry do worker failure. Dataflow exactly-once mode có bảo đảm API thanh toán chỉ bị gọi một lần? Đề xuất event ID, idempotency key và transaction/lookup trạng thái.

**Bài 6 — Late data.** Order xuất hiện lúc 10:02 nhưng worker nhận lúc 10:17. Với window 5 phút, allowed lateness 30 phút, hãy giải thích nơi phân loại event, cửa sổ nào được cập nhật và sink nên tránh đếm trùng giữa các panes như thế nào.

**Bài 7 — Spark serverless/cluster.** Một job Spark chạy 15 phút mỗi ngày, một job khác cần Hive/JAR tùy chỉnh trên cluster 24/7. Chọn hai mô hình Managed Spark, so sánh startup, idle cost, quyền/network và vận hành.

**Bài 8 — BigQuery continuous queries.** Vì sao có thể xem xét continuous query cho một số biến đổi dòng mới, nhưng không mang nguyên CTAS với `ROW_NUMBER`/`MERGE` vào một query streaming? Hãy liệt kê hai hạn chế quan trọng cần xác minh.

**Bài 9 — IAM.** App Java trên Cloud Run kích hoạt Dataflow job ghi BigQuery ở project dữ liệu khác. Vẽ ba danh tính: launcher SA, Dataflow worker SA và BigQuery resource owner; cấp quyền tối thiểu ở đâu?

**Bài 10 — Chi phí và đo lường.** Lập bảng benchmark cùng 100 triệu rows cho SQL, Beam, Spark: latency P95, job startup, bytes/shuffle, workers/slots, số records lỗi, phí và giá trị của việc giảm backlog. Vì sao kết quả trên 8 rows không có giá trị dự báo tuyệt đối?

**Bài 11 — Migration.** Một đội muốn chuyển Spark Structured Streaming sang Dataflow nhưng có 24 giờ replay backlog và nhiều late events. Viết runbook shadow test, watermark/state/checkpoint migration, canary, đối soát và rollback để không mất/ghi trùng dữ liệu.

## Tài liệu tham khảo chính thức

- [Dataflow overview](https://cloud.google.com/dataflow/docs/overview) — xử lý batch/stream với Apache Beam.
- [Dataflow streaming modes](https://cloud.google.com/dataflow/docs/guides/streaming-modes) — exactly-once/at-least-once modes.
- [Exactly-once in Dataflow](https://cloud.google.com/dataflow/docs/concepts/exactly-once) — phạm vi bảo đảm và side effects.
- [Pub/Sub streaming with Dataflow](https://cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub) — duplicate deliveries và ordering.
- [Create Java Dataflow pipelines](https://cloud.google.com/dataflow/docs/guides/create-pipeline-java) — Beam Java SDK, Maven runners và GCS.
- [Deploy Dataflow pipelines](https://cloud.google.com/dataflow/docs/guides/deploying-a-pipeline) — options, region, tempLocation và IAM.
- [Dataflow Pub/Sub Subscription to BigQuery template](https://cloud.google.com/dataflow/docs/guides/templates/provided/pubsub-subscription-to-bigquery) — input JSON, target schema và template.
- [Write from Dataflow to BigQuery](https://cloud.google.com/dataflow/docs/guides/write-to-bigquery) — BigQueryIO/Storage Write API semantics.
- [Managed Service for Apache Spark (formerly Dataproc)](https://cloud.google.com/products/managed-service-for-apache-spark) — serverless vs cluster.
- [Submit a Spark batch workload](https://cloud.google.com/managed-spark/docs/quickstarts/spark-batch) — `gcloud dataproc batches submit`.
- [Managed Spark pricing](https://cloud.google.com/products/managed-service-for-apache-spark/pricing) — serverless/cluster costs.
- [BigQuery data transformation options](https://cloud.google.com/bigquery/docs/transform-intro) — SQL, Dataform, scheduled/continuous queries.
- [BigQuery scheduled queries](https://cloud.google.com/bigquery/docs/scheduling-queries) — lịch, quyền và batch jobs.
- [BigQuery continuous queries introduction](https://cloud.google.com/bigquery/docs/continuous-queries-introduction) — SQL streaming support và giới hạn.
- [BigQuery query optimization](https://cloud.google.com/bigquery/docs/best-practices-performance-compute) — partition pruning/JOIN/aggregate.
- [BigQuery job information schema](https://cloud.google.com/bigquery/docs/information-schema-jobs) — query cost/slot-ms/metadata.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) và [Dataflow pricing](https://cloud.google.com/dataflow/pricing) — ước tính tổng chi phí.
