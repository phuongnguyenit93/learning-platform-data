# BigQuery Storage Write API và dữ liệu streaming

> **Chương:** BigQuery  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một nền tảng IoT gửi liên tục sự kiện nhiệt độ, trạng thái thiết bị và thời gian đo. Nhóm phân tích muốn truy vấn dữ liệu mới trong **BigQuery** sau khi ghi, nhưng hệ thống gửi sự kiện có thể retry do mất mạng. Nếu retry thiếu kiểm soát, báo cáo sẽ đếm trùng; nếu ghi từng hàng không batching, đường truyền và quota bị sử dụng kém hiệu quả. **BigQuery Storage Write API** giải quyết bài toán nạp dữ liệu trực tuyến bằng các *write streams*, cơ chế ghi bất đồng bộ và những lựa chọn khác nhau về **thời điểm hiển thị** và **bảo đảm không ghi trùng**.

Bài thuộc mô-đun **CLOUD_PROVIDERS_GCP**, nối kiến thức về project/IAM, VPC, Cloud Run, Pub/Sub, Dataflow và BigQuery với thiết kế pipeline đáng tin cậy, vận hành, bảo mật và chi phí. Nội dung ưu tiên **Storage Write API qua gRPC** và Java client; REST và các phương án nạp khác được so sánh để biết khi nào nên dùng.

**Mục tiêu học tập:** Sau bài học, người học có thể:

1. Phân biệt Storage Write API với batch load jobs và legacy streaming inserts.
2. Chọn **default**, **application-created committed** hoặc **pending** streams theo yêu cầu nghiệp vụ; biết buffered type chủ yếu cho trường hợp nâng cao.
3. Hiểu chính xác phạm vi của **at-least-once**, **exactly-once qua offsets** và **atomic batch commit**.
4. Cấu hình BigQuery table schema, partitioning và quyền IAM tối thiểu cho producer.
5. Dùng Java `JsonStreamWriter` gửi một batch JSON vào default stream, chờ acknowledgment và xử lý lỗi.
6. Thiết kế checkpoint/retry/idempotency, schema evolution và dead-letter queue (DLQ).
7. Quan sát throughput, quota, latency, duplicated events và chi phí với BigQuery/Cloud Monitoring.
8. Hoàn thành lab kiểm thử đường nạp sự kiện và so sánh các loại stream.

## 1. Kiến trúc tham chiếu cho streaming analytics

~~~mermaid
flowchart LR
  DEVICE["Thiết bị IoT / ứng dụng"] --> PUB["Pub/Sub topic\nevents-raw"]
  PUB --> WORKER["Dataflow hoặc Cloud Run worker\nvalidate, transform, batch"]
  WORKER -->|"Storage Write API gRPC\nAppendRows"| BQ["BigQuery\nstream_lab.events"]
  WORKER -->|"Lỗi không retry được"| DLQ["DLQ / Cloud Storage\nquarantine"]
  BQ --> SQL["BigQuery SQL\npartition + cluster"]
  WORKER --> OBS["Cloud Logging / Monitoring"]
  BQ --> OBS
~~~

**Tại sao có Pub/Sub?** Pub/Sub là một lớp đệm và cơ chế phân phối sự kiện, giúp producer không phải chờ BigQuery. Khi BigQuery chậm hoặc bị quota, consumer có thể tạm giảm tốc và xử lý lại. Tuy nhiên **Pub/Sub không tự đảm bảo bảng BigQuery không có duplicate**: cần chọn ngữ nghĩa stream hoặc có khoá sự kiện để khử trùng.

BigQuery phù hợp phân tích và SQL trên khối lượng lớn; **không phải database OLTP** cho mỗi yêu cầu cập nhật đơn hàng. Nếu cần giao dịch ứng dụng, thường ghi Cloud SQL/Firestore trước, rồi đẩy sự kiện phân tích sang BigQuery.

### 1.1. Các thành phần và trách nhiệm

| Thành phần | Vai trò | Rủi ro phải xử lý |
| --- | --- | --- |
| Producer | Tạo `event_id`, gửi dữ liệu có schema | Gửi trùng, thời gian thiết bị sai |
| Pub/Sub | Buffer và chuyển sự kiện tới consumer | Redelivery, backlog, retention |
| Worker | Validate, enrich, batch, retry/ack | Crash trước/sau acknowledgment |
| Storage Write API | Nạp dữ liệu tới BigQuery | Quota, stream state, offset/schema errors |
| BigQuery table | Lưu dữ liệu cho SQL/reporting | Partition/cluster, schema, dữ liệu trùng |
| Monitoring/DLQ | Quan sát và giữ bản ghi lỗi | Lộ dữ liệu nhạy cảm, dữ liệu lỗi bị bỏ qua |

**Quy tắc quan trọng:** Một acknowledgment từ `AppendRows` xác nhận lời gọi nạp của BigQuery theo semantics của stream; **không** khẳng định toàn bộ workflow kinh doanh downstream đã hoàn tất. Còn Pub/Sub acknowledgment là sự kiện riêng.

## 2. Chọn đúng phương thức nạp BigQuery

| Phương pháp | Dùng khi | Độ trễ/semantics | Ghi chú |
| --- | --- | --- | --- |
| **Storage Write API gRPC** | Streaming liên tục, throughput cao, điều khiển offset/batch | Gần thời gian thực; tùy stream có at-least-once hoặc exactly-once trong stream | **Ưu tiên thiết kế streaming mới** |
| **Storage Write API REST** | Client stateless/khó giữ gRPC connection | Tùy REST method và semantics | Không có toàn bộ khả năng gRPC; kiểm tra giá riêng |
| **BigQuery load job** | File trên Cloud Storage; xử lý theo lô | Dữ liệu có sau khi load job hoàn tất | Phù hợp batch lớn, có mô hình quota/cost riêng |
| **Legacy `tabledata.insertAll`** | Hệ thống cũ đang dùng streaming inserts | Cơ chế streaming cũ, có `insertId` best-effort dedup | Không tương đương write streams với offsets |
| **Dataflow BigQueryIO** | Muốn framework streaming có checkpoints/scale/retries | Tùy `STORAGE_WRITE_API` / `STORAGE_API_AT_LEAST_ONCE` | Đọc đúng cấu hình Beam connector |

**Không nhầm lẫn:** Lệnh `bq insert` và một số SDK streaming legacy thường sử dụng **`tabledata.insertAll`**, không phải bài thực hành Storage Write API gRPC ở đây. API **Storage Read** cũng hoàn toàn khác API **Storage Write**.

Theo [tài liệu tổng quan](https://docs.cloud.google.com/bigquery/docs/write-api-intro), gRPC có lợi thế về kết nối lâu dài, binary serialization (Protocol Buffers/Arrow), async writes, stream-level transactions và chi phí ingestion thường thấp hơn REST. Luôn xem bảng giá/quotas tại thời điểm triển khai.

## 3. Bốn loại write stream và khi dữ liệu có thể truy vấn

**Stream** là nguồn ghi hướng tới **một BigQuery table**. Có thể ghi song song nhiều streams vào cùng bảng; mỗi loại có hành vi hiển thị/commit khác nhau.

| Stream | Có cần `CreateWriteStream`? | Khi nào rows hiển thị? | Bảo đảm đặc trưng | Mục đích |
| --- | --- | --- | --- | --- |
| **Default stream** (tên kết thúc bằng `_default`) | **Không** | Sau khi ghi được server xác nhận | **At-least-once**, có thể trùng khi retry | Streaming thông thường |
| **COMMITTED do ứng dụng tạo** | Có | Sau acknowledgment của `AppendRows` | **Exactly-once trong cùng stream nếu dùng offsets** | Streaming cần điều khiển duplicate |
| **PENDING** | Có | **Chỉ sau `BatchCommitWriteStreams`** | Atomic commit nhiều streams | Batch/parallel import |
| **BUFFERED** | Có | Sau `FlushRows` tới offset xác định | Điều khiển thời điểm hiển thị từng phần | Trường hợp chuyên sâu, thường qua Beam |

**Lưu ý:** Default stream dùng hành vi committed nhưng **không có exactly-once offset tracking của application-created committed stream**. Vì vậy mô tả chính xác là “default at-least-once”, không phải “mọi committed streams đều exactly-once”.

### 3.1. Default: ingest ít phức tạp nhất

~~~mermaid
sequenceDiagram
  participant P as Worker
  participant D as Default stream
  participant Q as BigQuery SQL
  P->>D: AppendRows(batch A)
  D-->>P: ACK
  Q->>D: SELECT...
  D-->>Q: Batch A có thể truy vấn
  Note over P,D: Mất ACK → retry có thể sinh duplicate
~~~

Với default stream, producer **không phải tạo/đóng stream riêng**, có thể chia sẻ nhiều kết nối, hỗ trợ throughput cao. Đây là lựa chọn mặc định nếu dữ liệu đã có `event_id` để downstream deduplicate hoặc việc một số records lặp lại là chấp nhận được.

### 3.2. Committed: offsets để kiểm soát ghi trùng

Application-created COMMITTED stream có **vị trí ghi hiện tại (next offset)**, đếm theo **số rows đã append**, bắt đầu ở 0. `AppendRows(rows, offset)` chỉ thành công nếu offset đúng vị trí hợp lệ.

~~~text
Stream mới, next_offset = 0
AppendRows([A,B], offset=0)  → OK; next_offset = 2
AppendRows([C], offset=2)    → OK; next_offset = 3
Retry [C] với offset=2       → ALREADY_EXISTS (đã ghi)
AppendRows([D], offset=5)    → OUT_OF_RANGE (có khoảng trống)
~~~

Nếu chưa rõ request trước **đã được server thực thi hay chưa**, retry **cùng batch ở cùng offset** sau khi kết nối được khôi phục. `ALREADY_EXISTS` có thể là tín hiệu batch đã được ghi, nhưng chỉ an toàn khi bạn chắc chắn offset ánh xạ tới **cùng nội dung**; nếu quản lý offset sai, có thể bỏ sót dữ liệu. `OUT_OF_RANGE` thường cần truy lại checkpoint/last-acknowledged offset.

**Giới hạn cam kết:** Exactly-once chỉ **trong phạm vi một stream với offsets đúng**. Nếu cùng sự kiện được gửi qua **hai streams khác nhau**, hoặc upstream phát hai `event_id` khác nhau cho cùng nghiệp vụ, BigQuery **không tự hiểu chúng là cùng một sự kiện**. Muốn ngữ nghĩa kinh doanh exactly-once phải thiết kế cả upstream, mapping sự kiện→stream, checkpoint và dedup/reconciliation.

### 3.3. Pending: commit nguyên tử cho nhiều workers

~~~mermaid
sequenceDiagram
  participant C as Coordinator
  participant W1 as Worker A
  participant W2 as Worker B
  participant B as BigQuery
  C->>B: CreateWriteStream(PENDING) x2
  C->>W1: Stream 1
  C->>W2: Stream 2
  W1->>B: AppendRows + Finalize
  W2->>B: AppendRows + Finalize
  C->>B: BatchCommitWriteStreams(1,2)
  B-->>C: Commit ACK
  Note over B: Rows của cả hai streams hiển thị cùng commit
~~~

Trong PENDING stream, dữ liệu **chưa được query nhìn thấy** trước commit. Sau `FinalizeWriteStream` không còn được append; nếu mọi worker thành công, coordinator gọi `BatchCommitWriteStreams` để commit **nguyên tử** nhiều streams. Nếu commit gặp lỗi, cần kiểm tra response `stream_errors`, trạng thái/timeout và retry theo hướng dẫn.

**Không gọi pending stream là “realtime streaming”** khi chưa commit. Đây là cách phù hợp cho **batch atomic load** khi muốn điều phối nhiều workers.

### 3.4. Buffered: chỉ khi có nhu cầu cụ thể

BUFFERED stream cho phép append rồi `FlushRows` để quyết định rows nào hiển thị. Google khuyến nghị **không dùng trực tiếp cho use case phổ biến**, trừ các giải pháp đã hỗ trợ như Apache Beam. Đối với streaming gần thời gian thực, chọn default/committed; đối với batch nhiều workers commit cùng lúc, chọn pending. <https://docs.cloud.google.com/bigquery/docs/write-api-grpc>

## 4. Schema, định dạng và table layout trước khi ghi

Bài lab nhận sự kiện:

~~~json
{
  "event_id": "evt-20261119-0001",
  "device_id": "device-0042",
  "event_ts": "2026-11-19T02:00:00Z",
  "temperature_c": 27.5,
  "source": "iot"
}
~~~

Schema bảng:

| Field | BigQuery type | Nullability | Ý nghĩa |
| --- | --- | --- | --- |
| `event_id` | STRING | REQUIRED | Khoá duy nhất phía producer để đối chiếu/dedup |
| `device_id` | STRING | REQUIRED | Phân tích theo thiết bị |
| `event_ts` | TIMESTAMP | REQUIRED | Thời điểm sự kiện xảy ra |
| `temperature_c` | FLOAT64 | NULLABLE | Giá trị đo |
| `source` | STRING | NULLABLE | Nguồn sự kiện |

**BigQuery table không tự áp UNIQUE constraint theo `event_id`**. Các trường khai báo PRIMARY KEY nếu được dùng trong tính năng liên quan cũng có thể **không được BigQuery enforce** như OLTP database; không xem schema là biện pháp ngăn ghi trùng. Validate `event_id` ngay tại producer và dùng truy vấn/ETL dedup khi cần.

### 4.1. Partition + cluster phù hợp ingestion

- Partition theo **ngày của `event_ts`** giúp truy vấn theo khoảng thời gian quét ít partition hơn.
- Cluster theo `device_id` giúp truy vấn chọn nhóm thiết bị hiệu quả hơn.
- Dữ liệu đến muộn cần nằm trong khoảng partition hợp lệ; nếu bị lọc bởi expiration hoặc phân vùng không cho ghi, pipeline phải có DLQ/rehydration.
- Cân nhắc thêm `ingest_ts` (thời điểm hệ thống nhận) để đo **ingestion lag**, khác thời điểm thiết bị đo `event_ts`.
- Với late/out-of-order events, **không** dùng arrival order làm event ordering business mặc định.

### 4.2. Java hỗ trợ JSON, wire format gRPC là binary

BigQuery Storage Write API gRPC dùng **serialized Protocol Buffers** hoặc **Apache Arrow**. Java `JsonStreamWriter` nhận JSON objects và **chuyển sang protobuf trước khi gửi**; Java `StreamWriter` nhận protobuf schema/rows trực tiếp. Không nghĩ rằng gửi `JSONArray` qua `JsonStreamWriter` tức là API gửi REST JSON.

Nếu payload có fields lạ, type sai hoặc giá trị không hợp schema, có thể bị `SCHEMA_MISMATCH_EXTRA_FIELD`/serialization error. **Không bật ignore unknown fields để che lỗi pipeline**, vì fields mới có thể bị loại âm thầm.

## 5. Quyền và giới hạn phạm vi lab

Trong ví dụ này chỉ thao tác với:

| Tài nguyên | Giá trị minh họa |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| BigQuery dataset | `stream_lab` |
| Region | `asia-southeast1` |
| Table | `events` |
| Producer runtime SA | `bq-stream-writer@LAB_PROJECT_ID.iam.gserviceaccount.com` |
| gRPC API | `bigquerystorage.googleapis.com` |
| Java library | `com.google.cloud:google-cloud-bigquerystorage` |
| Event identity | `event_id` |
| Java ingest method | `JsonStreamWriter` + default stream |

### 5.1. IAM từng vai trò

| Principal | Quyền | Mục đích |
| --- | --- | --- |
| Người tạo dataset/table | BigQuery Data Owner trên dataset hoặc quyền quản trị thích hợp | Provision/tạo schema |
| Producer runtime SA | **`bigquery.tables.updateData`** trên table/dataset và quyền xem metadata phù hợp | Storage Write API append |
| Người/CI chạy query | `bigquery.jobs.create` ở project chạy job + quyền đọc dataset/table | Xác nhận dữ liệu, SQL và monitoring |
| Cloud Run/GKE caller | Dùng runtime SA qua ADC | Không lưu key JSON trong source |
| Monitoring/SRE | Metrics, logs và quyền `INFORMATION_SCHEMA` tương ứng | Quan sát/điều tra |

Predefined role `roles/bigquery.dataEditor` chứa `bigquery.tables.updateData` nhưng cũng có quyền rộng hơn việc ghi. Ở production, cân nhắc **custom role** hoặc cấp trên dataset hẹp nhất theo hướng dẫn IAM. Không cấp Project Owner cho writer chỉ vì lỗi permission.

Với Storage Write API gRPC, permissions và OAuth scopes là **hai điều kiện khác nhau** khi môi trường có scopes hạn chế. Dùng **Application Default Credentials** trên workload; BigQuery Storage Write API không cần hard-coded service account private key.

### 5.2. Preflight chỉ đọc

~~~bash
# Trên máy có gcloud và bq, kiểm tra project trước mọi thay đổi
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

bq show --format=prettyjson LAB_PROJECT_ID:stream_lab
bq show --format=prettyjson LAB_PROJECT_ID:stream_lab.events

# Kiểm tra identity ứng dụng (nếu đã tạo)
gcloud iam service-accounts describe \
  bq-stream-writer@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --project=LAB_PROJECT_ID
~~~

Nếu dataset/table chưa tồn tại, `bq show` trả lỗi không tìm thấy là bình thường; **không tự chạy lệnh tạo tài nguyên production** để xử lý lỗi. Xác minh billing/quota, data location, retention và chi phí trước khi tạo.

## 6. Tạo dataset và table có partition/cluster trong project lab

**Các lệnh tiếp theo thay đổi tài nguyên và có thể phát sinh chi phí.** Chỉ chạy sau khi project, dataset name, data residency, IAM và budget đã được phê duyệt. Bỏ qua nếu sandbox đã cung cấp sẵn bảng tương đương.

~~~bash
# Tạo dataset tại cùng region với pipeline được chọn
bq --location=asia-southeast1 mk \
  --dataset LAB_PROJECT_ID:stream_lab
~~~

Tạo **chính bảng đích `events`** bằng BigQuery SQL (trong Console hoặc `bq query --use_legacy_sql=false`), để các fields quan trọng được khai báo `NOT NULL` đúng như hợp đồng ở mục 4:

~~~sql
-- Dùng BigQuery SQL trong project lab; tạo tài nguyên và có thể phát sinh phí
CREATE TABLE IF NOT EXISTS `LAB_PROJECT_ID.stream_lab.events` (
  event_id STRING NOT NULL,
  device_id STRING NOT NULL,
  event_ts TIMESTAMP NOT NULL,
  temperature_c FLOAT64,
  source STRING
)
PARTITION BY DATE(event_ts)
CLUSTER BY device_id
OPTIONS(description="Lab Storage Write API");
~~~

Nếu bảng `events` đã tồn tại, `IF NOT EXISTS` **không chỉnh schema cũ**. Hãy dùng một bảng lab sạch hoặc xác minh schema thực tế trước khi ingest. Producer vẫn phải validate `event_id/device_id/event_ts`, vì ràng buộc cột không bảo đảm tính duy nhất của `event_id`.

### 6.1. Quyền producer trên table (mẫu)

~~~bash
# Chỉ người quản trị IAM được phép chạy, trong project lab
bq add-iam-policy-binding \
  --member=serviceAccount:bq-stream-writer@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/bigquery.dataEditor \
  --table LAB_PROJECT_ID:stream_lab.events
~~~

Lệnh `bq add-iam-policy-binding` hỗ trợ **table/view, không hỗ trợ dataset**. Nếu cần grant trên cả dataset (nhiều bảng), cấu hình tại **Console → BigQuery → Dataset → Sharing → Permissions** hoặc thông qua IAM API/IaC thích hợp. Bắt đầu với phạm vi table nhỏ nhất; xác minh quyền bằng workload identity thật.

## 7. Java: ghi batch nhỏ vào default stream

Đây là ví dụ Java dùng **BigQuery Storage Write API gRPC** trực tiếp, không dùng legacy `insertAll`. Cần thư viện `google-cloud-bigquerystorage`, `org.json`, BigQuery Storage API enabled, ADC và bảng đã tồn tại. Chọn version theo BOM được kiểm thử với JDK/framework; không ghim một version tuỳ ý vào nội dung học.

### 7.1. Chương trình Java hoàn chỉnh, đơn giản

~~~java
import com.google.cloud.bigquery.storage.v1.AppendRowsResponse;
import com.google.cloud.bigquery.storage.v1.BigQueryWriteClient;
import com.google.cloud.bigquery.storage.v1.JsonStreamWriter;
import com.google.cloud.bigquery.storage.v1.TableName;
import com.google.api.core.ApiFuture;
import org.json.JSONArray;
import org.json.JSONObject;

public final class WriteEvents {
    public static void main(String[] args) throws Exception {
        String project = "LAB_PROJECT_ID";
        String dataset = "stream_lab";
        String table = "events";
        String parent = TableName.of(project, dataset, table).toString();

        try (BigQueryWriteClient client = BigQueryWriteClient.create()) {
            JsonStreamWriter writer = JsonStreamWriter
                .newBuilder(parent, client)
                .build();
            try {
                JSONArray rows = new JSONArray();
                rows.put(new JSONObject()
                    .put("event_id", "evt-20261119-0001")
                    .put("device_id", "device-0042")
                    .put("event_ts", "2026-11-19T02:00:00Z")
                    .put("temperature_c", 27.5)
                    .put("source", "iot"));

                rows.put(new JSONObject()
                    .put("event_id", "evt-20261119-0002")
                    .put("device_id", "device-0101")
                    .put("event_ts", "2026-11-19T02:00:01Z")
                    .put("temperature_c", 29.1)
                    .put("source", "iot"));

                ApiFuture<AppendRowsResponse> pending = writer.append(rows);
                AppendRowsResponse ack = pending.get(); // Đợi server ACK
                System.out.println("Batch appended: " + ack.hasAppendResult());
            } finally {
                writer.close();
            }
        }
    }
}
~~~

**Vì sao dùng `JsonStreamWriter.newBuilder(parent, client)`?** Khi truyền table name thay vì stream name, Java client ghi tới **default stream**; nó quản lý gRPC transport, protobuf mapping, regional headers và tái kết nối. Thêm offset vào default stream **không biến** nó thành exactly-once stream.

- `ApiFuture` là kết quả của append bất đồng bộ; demo dùng `get()` để đợi **một** batch hoàn tất.
- Mẫu production nên gửi **nhiều batches async**, quản lý giới hạn inflight bytes/requests và đợi tất cả acknowledgments trước khi ack Pub/Sub hoặc shutdown.
- Nếu `get()` throw, không log payload/credentials, phân loại lỗi, retry có backoff và xử lý duplicate như phần sau.
- Bản ghi dùng timestamps giả để có thể thử độc lập với đồng hồ thật; **không dùng lại `event_id` trong pipeline thật** trừ khi cố tình test duplicate.
- Đừng tạo/đóng writer cho **mỗi HTTP request** hoặc mỗi message; tái sử dụng writer/channel trên worker sống lâu.

### 7.2. Kiểm tra dữ liệu bằng SQL

~~~sql
-- Chỉ đọc; có phí query nếu vượt mức miễn phí theo gói
SELECT
  event_id,
  device_id,
  event_ts,
  temperature_c,
  source
FROM `LAB_PROJECT_ID.stream_lab.events`
WHERE event_ts >= TIMESTAMP("2026-11-19T00:00:00Z")
  AND event_ts < TIMESTAMP("2026-11-20T00:00:00Z")
ORDER BY event_ts
LIMIT 20;
~~~

Dữ liệu từ **default/COMMITTED stream** có thể truy vấn sau acknowledgment. Với PENDING stream, truy vấn sẽ **không thấy** rows trước khi commit. Không dùng `SELECT COUNT(*)` lặp mỗi giây để thay monitoring: SQL queries có thể phát sinh phí; dùng metrics và kiểm tra mẫu có giới hạn.

### 7.3. Phân biệt stream ACK và uniqueness

Thực thi lại chương trình cùng `event_id` có thể thêm hai rows lần nữa vì default stream **at-least-once**. BigQuery không tự enforce unique key. Để bảo đảm báo cáo không đếm trùng, ví dụ:

~~~sql
-- Ví dụ truy vấn làm sạch dựa trên event_id, chọn bản ghi mới nhất.
-- Nếu không có ingest_ts, tie-breaker có thể chưa đủ xác định.
SELECT * EXCEPT(row_num)
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY event_id
      ORDER BY event_ts DESC
    ) AS row_num
  FROM `LAB_PROJECT_ID.stream_lab.events`
)
WHERE row_num = 1;
~~~

**Lưu ý:** Nếu hai bản ghi cùng `event_id` có cùng `event_ts` nhưng payload khác, kết quả có thể không xác định vì thiếu tie-breaker. Production nên có **`ingest_ts`/source sequence** và quy ước xử lý conflict rõ ràng; dùng view/projection/MERGE theo batch khi cần.

## 8. Java committed stream: dùng offset để chống retry ghi trùng

Default stream đáp ứng phần lớn pipelines. Chỉ chuyển sang **application-created COMMITTED stream** khi cần exactly-once ingestion ở **phạm vi stream** và sẵn sàng vận hành checkpoint/stream ownership.

### 8.1. Tạo stream và gửi một batch có offset

Ví dụ đoạn Java sau dùng lại class `BigQueryWriteClient`, `JsonStreamWriter` và `TableName` ở mục 7, cùng các import `CreateWriteStreamRequest`, `WriteStream`, `JSONArray`. Đây là **trích đoạn logic** để gắn vào worker đã có retry/checkpoint, không phải source Java độc lập:

~~~java
String parent = TableName
    .of("LAB_PROJECT_ID", "stream_lab", "events").toString();

WriteStream spec = WriteStream.newBuilder()
    .setType(WriteStream.Type.COMMITTED)
    .build();

try (BigQueryWriteClient client = BigQueryWriteClient.create()) {
    WriteStream stream = client.createWriteStream(
        CreateWriteStreamRequest.newBuilder()
            .setParent(parent)
            .setWriteStream(spec)
            .build());

    JsonStreamWriter writer = JsonStreamWriter
        .newBuilder(stream.getName(), stream.getTableSchema(), client)
        .build();
    try {
        // JSONArray rows đã được tạo/validate.
        long nextOffset = 0L;
        AppendRowsResponse ack = writer.append(rows, nextOffset).get();

        // Chỉ sau ACK mới checkpoint vị trí kế tiếp theo số row.
        if (!ack.hasAppendResult()) {
            throw new IllegalStateException("No append result");
        }
        nextOffset += rows.length();
        // Persist (stream.getName(), nextOffset) vào checkpoint store.
    } finally {
        writer.close();
    }

    // Finalize optional cho COMMITTED, sau khi producer ngừng ghi.
    client.finalizeWriteStream(stream.getName());
}
~~~

**Điều đoạn code này chưa giải quyết:** checkpoint phải **bền vững**, quản lý ownership của stream trên nhiều workers, lưu batch chưa ACK để retry lại **cùng nội dung/cùng offset**, và xử lý crash giữa ACK và checkpoint. `long nextOffset` trong RAM chỉ minh họa, **không đủ cho exactly-once end-to-end**. Không finalize một stream đang được worker khác dùng.

### 8.2. Quy tắc checkpoint cụ thể

| Tình huống | Việc worker cần làm |
| --- | --- |
| Append ở offset 0 thành công 2 rows | Lưu checkpoint next offset = 2 |
| Gửi 3 rows ở offset 2, kết nối đứt trước ACK | Giữ nguyên batch, retry **offset 2** |
| Retry báo `OFFSET_ALREADY_EXISTS` | Xác minh batch/offset đã ACK trước đó, tiếp tục từ offset 5 |
| Gửi offset lớn hơn vị trí tiếp theo, `OFFSET_OUT_OF_RANGE` | Đối chiếu last ACK, gửi lại phần thiếu; không nhảy offset |
| Worker restart | Lấy lại stream ID, offset checkpoint và nội dung chưa xác nhận |
| Một event đi vào **stream khác** | Offset không giúp chống trùng cross-stream; cần `event_id`/dedup |
| Có nhiều writers | Một active connection cho mỗi application-created stream; phân quyền ownership rõ |

Nếu upstream Pub/Sub có redelivery, ánh xạ một **logical partition** ổn định vào stream + checkpoint thay vì tạo stream mới theo từng request. Khi worker mất stream hoặc pending records, có runbook reconciliation thay vì ghi lại mọi events vào stream mới một cách mù quáng.

### 8.3. Không đồng nhất exactly-once row delivery với nghiệp vụ

Exactly-once trong stream bảo đảm cùng offset **không được ghi hai lần vào stream đó**, nhưng **không** đảm bảo nguồn chỉ tạo một sự kiện cho một giao dịch, hoặc quy trình downstream không xử lý lại một event. Quy tắc tổng quát:

- Sự kiện có **`event_id`**/source sequence ổn định.
- Các nguồn ghi có quy tắc partitioning và checkpoint nhất quán.
- Nếu dữ liệu vào nhiều streams, báo cáo/transformations có dedup hoặc MERGE theo business key.
- Kết quả `AppendRows` và Pub/Sub ack được lưu/đối chiếu để phục hồi sau crash.

Khi exactly-once qua nhiều hệ thống làm tăng độ phức tạp không cần thiết, **default stream + idempotent downstream** thường thực dụng hơn.

## 9. Pending streams: atomic commit một batch nhiều workers

Đối với batch cuối ngày/nhập lại lịch sử, dữ liệu thường chỉ được công bố khi **tất cả** các phần đã nạp và kiểm tra xong. Pending streams cho phép coordinator tạo nhiều streams cho các workers và **commit chúng cùng lúc**.

### 9.1. Quy trình bắt buộc

~~~text
Coordinator:
  CreateWriteStream(type=PENDING) -> stream-A, stream-B
  Giao mỗi stream cho một worker.

Worker A:
  AppendRows(stream-A, rows, offsets nếu quản lý)
  Đợi tất cả ACK
  FinalizeWriteStream(stream-A) -> row_count_A

Worker B:
  AppendRows(stream-B, rows)
  Đợi tất cả ACK
  FinalizeWriteStream(stream-B) -> row_count_B

Coordinator:
  Kiểm tra row counts, checksum/manifest nếu có
  BatchCommitWriteStreams(parent table, [stream-A, stream-B])
  Xác nhận không có stream_errors
  Mới công bố batch thành công
~~~

Đây là **pseudocode luồng API** (không phải Bash). Các phương thức tương ứng trong Java `BigQueryWriteClient` là `createWriteStream`, `finalizeWriteStream`, `batchCommitWriteStreams`. `FinalizeWriteStream` **bắt buộc** với pending; `BatchCommitWriteStreams` là bước khiến dữ liệu hiển thị.

### 9.2. Trạng thái dữ liệu và lỗi

| Trạng thái | Có thể query? | Hành động |
| --- | --- | --- |
| Đã append, chưa finalize | Không | Tiếp tục gửi/kiểm tra ACK |
| Finalized, chưa commit | Không | Coordinator quyết định commit hoặc điều tra |
| Commit thành công | Có | Đánh dấu manifest batch hoàn tất |
| Một worker failed | Chưa có commit toàn batch | Retry worker/stream theo runbook |
| Timeout/unknown commit status | Chưa nên coi là thất bại hoàn toàn | Đối chiếu trạng thái/response và retry commit idempotent |

Pending streams có **giới hạn thời gian lưu** trước commit; không dùng làm hàng đợi lưu dữ liệu vô hạn. Tài liệu nêu sau finalize dữ liệu có thể giữ trong buffer tối đa khoảng 4 giờ và pending stream cần commit trong 24 giờ. <https://docs.cloud.google.com/bigquery/docs/write-api-batch-load>

**Đối chiếu với load job:** Nếu dữ liệu đã có ở Cloud Storage và chỉ cần batch load, BigQuery load jobs thường đơn giản hơn. Dùng pending streams khi cần điều phối nạp trực tiếp/đa workers và atomic commit rõ ràng.

## 10. Retry, backpressure và dead-letter queue

### 10.1. Phân loại trước khi retry

| Lỗi/nhóm | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `UNAVAILABLE`, `INTERNAL`, `DEADLINE_EXCEEDED` | Sự cố tạm thời/network | Exponential backoff + jitter, reconnect, replay phù hợp stream |
| `RESOURCE_EXHAUSTED`/429 | Throughput, connection hoặc request quota | Giảm inflight/rate, batch, kiểm tra quota trước khi xin nâng |
| `OFFSET_ALREADY_EXISTS` | Batch đã ghi hoặc offset quản lý sai | Xác minh checkpoint/payload, **không append offset mới mù quáng** |
| `OFFSET_OUT_OF_RANGE` | Khoảng trống offset hoặc write trước thất bại | Khôi phục từ last ACK, bù batch còn thiếu |
| `SCHEMA_MISMATCH_EXTRA_FIELD` | Payload có field chưa thuộc schema | Thay schema trước, đồng bộ writer, hoặc DLQ |
| `INVALID_ARGUMENT`/type mismatch | Dữ liệu sai schema/format | Không retry vô hạn; quarantine record |
| `PERMISSION_DENIED` | Runtime SA thiếu IAM/không đúng resource | Sửa identity/quyền đúng phạm vi, không cấp Editor rộng |
| `NOT_FOUND` | Sai table/dataset/stream hoặc hết TTL | Kiểm tra names, region, stream lifecycle |
| `STREAM_FINALIZED` | Append sau finalize | Không dùng lại stream, kiểm tra workflow state |

**Không phải mọi timeout đều có nghĩa server chưa ghi.** Với default stream, retry có thể tạo duplicate; với committed stream, retry batch **cùng offset** giúp idempotency trong stream.

### 10.2. Quy tắc backpressure cho consumer Pub/Sub

~~~mermaid
flowchart TD
  MSG["Pull Pub/Sub message"] --> VAL{"Validate schema + event_id?"}
  VAL -- "Không" --> DLQ["Quarantine/DLQ\nreason + safe payload reference"]
  VAL -- "Có" --> BATCH["Ghép batch có giới hạn bytes/rows/time"]
  BATCH --> APP["AppendRows async"]
  APP --> ACK{"Server ACK?"}
  ACK -- "Có" --> SAVE["Persist checkpoint/ack Pub/Sub\ntheo delivery policy"]
  ACK -- "Retryable" --> WAIT["Bounded backoff + jitter\nflow control"] --> APP
  ACK -- "Nonretryable" --> DLQ
  SAVE --> NEXT["Nhận batch mới"]
~~~

Cần có giới hạn cho **số batches đang chờ, bytes trong RAM, request deadlines và concurrency**. Khi downstream bị quota, giảm tốc nhận messages; nếu Pub/Sub backlog kéo dài, capacity/retention phải đủ để không mất dữ liệu. Nếu mất kết nối quá lâu, cần lưu batch vào storage bền vững để phục hồi, không chỉ buffer trong RAM.

### 10.3. Poison records không được “nuốt” mất

Record sai schema, timestamp hoặc nested field nên vào DLQ **cùng mã lỗi, event_id, source và object reference**. Không ghi toàn bộ PII hoặc secret vào Cloud Logging. Có quy trình sửa/replay có kiểm tra và audit, tránh replay DLQ sinh thêm duplicate.

## 11. Schema evolution trong luồng dữ liệu chạy liên tục

Một schema BigQuery có thể thay đổi khi worker vẫn đang gửi data. Ví dụ thêm `firmware_version STRING`:

1. **Expand schema trước**: thêm field nullable/default phù hợp vào BigQuery table.
2. **Chờ schema được phát hiện**: Storage Write API không nhìn thấy đổi schema tức thời; tài liệu mô tả có thể mất vài phút.
3. **Điều chỉnh producer**: chỉ sau khi writer hỗ trợ schema mới mới gửi field.
4. **Theo dõi errors**: `SCHEMA_MISMATCH_EXTRA_FIELD`, bad type, serialization.
5. **Rollback an toàn**: có thể bỏ gửi field mới nếu schema consumer chưa sẵn sàng; không xóa cột đang được các jobs dùng.

Với Java, `JsonStreamWriter` có hỗ trợ **tự kết nối lại với schema mới**, nhưng vẫn cần quản lý retries/ACK và rollout producers. Với gRPC low-level, có thể phải đóng/mở kết nối khi schema đã đổi.

**Không bật `setIgnoreUnknownFields(true)` theo mặc định.** Nó có thể bỏ âm thầm fields mới của payload, làm dữ liệu thiếu mà execution vẫn thành công. Kiểm tra toàn bộ pipeline qua schema tests và DLQ.

### 11.1. Kiểu dữ liệu quan trọng

| Trường | Dữ liệu gửi | Lỗi phổ biến |
| --- | --- | --- |
| TIMESTAMP | Chuỗi thời gian hợp lệ/định dạng được hỗ trợ | Múi giờ sai, timestamp không parse được |
| FLOAT64 | Số thực JSON hợp lệ | `NaN`/Infinity hoặc chuỗi ký tự |
| STRING | Chuỗi UTF-8 | PII không được phép, vượt row/request limits |
| RECORD/REPEATED | Nested/repeated fields đúng schema | Map/list thiếu/mismatch |
| NUMERIC/DECIMAL | Biểu diễn chính xác theo thư viện | Mất độ chính xác khi dùng float |
| REQUIRED | Có giá trị không null | Missing/null gây lỗi |

Không gửi dữ liệu nhạy cảm nếu chưa kiểm tra data classification, policy tags, quyền bảng và retention.

## 12. Throughput, multiplexing, quota và chi phí

### 12.1. Batch và async thay vì append từng row

Mỗi lần `AppendRows` có overhead. Gom **nhiều rows trong một batch** giúp tăng hiệu suất; nhưng phải giữ dưới **giới hạn kích thước request** và giới hạn bộ nhớ/latency của pipeline. Google khuyến nghị requests lớn, có thể trên 1 MB khi phù hợp, thay vì đóng/mở connection cho từng row. <https://docs.cloud.google.com/bigquery/docs/write-api-best-practices>

**Cân bằng:** Batch quá lớn làm tăng thời gian chờ trước khi có dữ liệu và khó retry khi lỗi; batch quá nhỏ tốn overhead. Chọn ngưỡng theo **byte, số rows và max wait time**, đo p95 ingestion lag và throughput trong load test.

### 12.2. Multiplexing ở default stream

- Default stream có thể dùng **nhiều gRPC connections**.
- Java/Go/Rust client hỗ trợ **multiplexing/connection pooling** cho default stream, giúp chia sẻ connections giữa tables/streams khi tương thích.
- Java có tuỳ chọn `JsonStreamWriter.newBuilder(...).setEnableConnectionPool(true)`.
- Với application-created streams, chỉ nên có **một active connection mỗi stream**.
- Không tạo một stream cho **mỗi message**: `CreateWriteStream` có quota/rate limit và tác động latency.

### 12.3. Những quota cần theo dõi

| Hạn mức | Rủi ro |
| --- | --- |
| Ingest throughput theo project/location | `RESOURCE_EXHAUSTED`, backlog tăng |
| Số concurrent connections | AppendRows bị từ chối khi vượt |
| Tốc độ tạo application-created streams | Provision quá nhiều streams, trễ hoặc quota |
| Số active streams | Resource exhaustion nếu quên finalize/TTL |
| Request size, inflight bytes/requests | Serialization error, timeout hoặc flow control |
| Pending buffer và thời hạn commit | Batch hết khả năng commit đúng hạn |

Hạn mức thực tế phụ thuộc location, project và loại API (gRPC/REST), có thể thay đổi. Kiểm tra [BigQuery quotas](https://docs.cloud.google.com/bigquery/quotas#write-api-limits) trong project trước khi gắn số cứng vào capacity plan.

### 12.4. Chi phí nhìn theo toàn pipeline

Chi phí không chỉ là bytes qua Storage Write API:

- **Ingestion**: gRPC/REST có cơ chế giá khác nhau và mức miễn phí theo điều kiện hiện hành.
- **BigQuery storage**: raw events, partitions, copies, retention, time travel/backup phù hợp.
- **Query compute**: bytes scanned hoặc slots; dùng partition filters, clustering và LIMIT có ý nghĩa.
- **Pub/Sub/Dataflow/Cloud Run**: buffering, xử lý, scaling, retries.
- **Logging/Monitoring/DLQ**: volume logs, storage và vận hành.
- **Network egress**: data location/cross-region transfer trong kiến trúc.

Giới hạn dữ liệu ingest theo **kích thước đã xử lý** và chi phí theo SKU hiện hành; không áp dụng giá cố định từ ví dụ cũ. Đặt **Billing Budget** và cảnh báo cho giai đoạn thử.

## 13. Quan sát Storage Write API bằng BigQuery và Monitoring

### 13.1. View `WRITE_API_TIMELINE`

BigQuery cung cấp `INFORMATION_SCHEMA.WRITE_API_TIMELINE[_BY_PROJECT]` với số requests/rows/bytes, stream type và error codes theo **khoảng một phút**. Truy vấn cần **region qualifier** khớp vùng dataset/query.

~~~sql
-- Chỉ đọc; chạy job ở asia-southeast1 (có thể phát sinh phí)
SELECT
  start_timestamp,
  table_id,
  stream_type,
  error_code,
  SUM(total_requests) AS request_count,
  SUM(total_rows) AS rows_count,
  SUM(total_input_bytes) AS input_bytes
FROM `region-asia-southeast1`.INFORMATION_SCHEMA.WRITE_API_TIMELINE_BY_PROJECT
WHERE start_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 MINUTE)
  AND dataset_id = 'stream_lab'
  AND table_id = 'events'
GROUP BY start_timestamp, table_id, stream_type, error_code
ORDER BY start_timestamp DESC;
~~~

**Chú ý:** View có dữ liệu cho **gRPC Storage Write API**, không thay Cloud Logging hoặc legacy REST metrics. IAM xem metadata và query job permissions vẫn cần đúng; query cần chạy đúng region. Nếu không có dữ liệu trong 30 phút gần nhất, nới thời gian quan sát thay vì khẳng định API không hoạt động.

### 13.2. Các chỉ số quan trọng

| Tầng | Metric/quan sát | Câu hỏi |
| --- | --- | --- |
| Producer | Events created/s và event size | Lượng đầu vào thực sự |
| Pub/Sub | Oldest unacked message age, backlog, redelivery | Buffer có tăng không? |
| Worker | Batch bytes, inflight, retries, ACK latency | Có backpressure/đứt mạng không? |
| Storage Write API | Requests/errors theo code, rows/s, bytes/s | Quota/schema/offset errors? |
| BigQuery table | Rows/min theo event_ts/ingest_ts, duplicate event_id | Ingest có đủ/đúng/không trùng? |
| Business | Số thiết bị hoạt động, p95 ingestion lag | Báo cáo có đáp ứng SLO? |
| Cost | Ingest bytes, query bytes, worker hours | Có vượt ngân sách không? |

**Không đo request latency bằng thời lượng một kết nối gRPC sống lâu**. Với bidirectional streams, Console có thể thể hiện connection duration; cần dựa vào **ACK từng append, client metrics và WRITE_API_TIMELINE** để đo latency ở mức request.

### 13.3. Chẩn đoán ngắn

| Triệu chứng | Xác minh |
| --- | --- |
| Java `PERMISSION_DENIED` | ADC/runtime SA, BigQuery table quyền `bigquery.tables.updateData`, API activation |
| `INVALID_ARGUMENT`/serialization | JSON fields/types, schema, required values |
| `SCHEMA_MISMATCH_EXTRA_FIELD` | Schema đã expand chưa? Writer đã refresh chưa? |
| `RESOURCE_EXHAUSTED` | Byte/s, connections, stream creation rate, flow control |
| `ALREADY_EXISTS`/`OUT_OF_RANGE` | Stream ID, offset checkpoint, batch equality |
| Mất data trong report | Pending chưa commit, query partition filter, late events |
| Duplicates | Default retry, upstream redelivery, two streams, source duplicate |
| Pending commit lỗi | Streams finalized? `stream_errors`? TTL/buffer? |
| Backlog lâu | Producer > ingest capacity, retries, DLQ, insufficient workers |
| Giá query cao | Partition scan quá rộng, thiếu cluster filter, polling SQL quá thường xuyên |

**Thứ tự điều tra:** đúng table/region → IAM → writer/stream type → schema → ACK/error code → checkpoint/retry → Pub/Sub backlog → query/filter → business reconciliation.

## 14. Case study: hệ thống IoT có sự kiện đến trễ

**Yêu cầu:** 100.000 thiết bị gửi một mẫu mỗi phút, dữ liệu cần xuất hiện trong báo cáo sau vài phút; sensor có thể mất mạng và gửi lại nhiều mẫu cũ.

- **Thiết kế A:** Pub/Sub → Dataflow → BigQuery default stream, mỗi event có `event_id` ổn định và phép dedup downstream.
- **Thiết kế B:** Custom Java workers với committed streams/offsets cho từng logical partition, checkpoint ở durable store.
- **Thiết kế C:** Import dữ liệu lịch sử từ file bằng load jobs hoặc pending streams nếu cần atomic batch.

**Đánh đổi:** A dễ scale/vận hành hơn với at-least-once; B tăng độ phức tạp để kiểm soát exactly-once trong stream; C dùng batch vì yêu cầu hiển thị cùng lúc và có thời gian đóng batch. Với báo cáo không chấp nhận đếm trùng, cả A/B vẫn cần kiểm tra **business event identity** và nguồn có gửi trùng không.

**Rủi ro riêng của IoT:** Thiết bị mất kết nối 12 giờ rồi replay khiến `event_ts` cũ hơn thời gian ingest. Nếu table partition theo event time, báo cáo chỉ lấy “hôm nay” có thể bỏ qua late events; cần quy ước watermark/late-data window, không xử lý bằng tăng retry.

## 15. Bài lab: chứng minh các loại stream

**Điều kiện:** Dùng project lab đã có billing/quota và quyền phù hợp. Nếu không có sandbox, làm **mô phỏng offset/batch**; không cần tạo tài nguyên có phí.

### 15.1. Phần A — Default stream có thể tạo duplicate

1. Xác nhận table schema, partition, SA và các API cần thiết.
2. Ghi hai events bằng Java ở mục 7.
3. Chạy truy vấn kiểm tra hai `event_id`.
4. Chạy chương trình một lần nữa **với cùng event IDs** để mô phỏng replay.
5. Dùng SQL phân nhóm để xem trùng:

~~~sql
SELECT event_id, COUNT(*) AS copies
FROM `LAB_PROJECT_ID.stream_lab.events`
WHERE event_ts >= TIMESTAMP("2026-11-19T00:00:00Z")
  AND event_ts < TIMESTAMP("2026-11-20T00:00:00Z")
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY copies DESC;
~~~

Giải thích vì sao **cả hai append đều nhận ACK** nhưng dữ liệu vẫn trùng theo `event_id`.

### 15.2. Phần B — Committed offset (mô phỏng an toàn)

Đặt một stream có next offset 0:

| Lần | Rows | Offset gửi | Dự kiến |
| --- | --- | ---: | --- |
| 1 | A, B | 0 | ACK, next = 2 |
| 2 | C | 2 | ACK, next = 3 |
| 3 | C (retry) | 2 | OFFSET_ALREADY_EXISTS |
| 4 | D | 5 | OFFSET_OUT_OF_RANGE |
| 5 | D | 3 | ACK, next = 4 |

Viết logic checkpoint/ACK và mô tả trường hợp worker crash **sau khi server ghi nhưng trước khi lưu checkpoint**. Giải thích vì sao retry cùng offset hữu ích và vì sao vẫn cần `event_id` nếu có nhiều streams.

### 15.3. Phần C — Pending commit

Vẽ luồng coordinator tạo hai pending streams, workers append/finalize và coordinator commit. Trả lời: *SELECT có thấy dữ liệu trước commit không? Nếu một worker lỗi thì coordinator nên làm gì? Có thể retry commit sau timeout không?* Không thử xoá bảng hoặc cố ý làm hỏng production job để chứng minh lỗi.

### 15.4. Phần D — Quan sát, nộp bài

| Bằng chứng | Tiêu chí |
| --- | --- |
| Kiến trúc pipeline | Có buffer, worker, DLQ, BigQuery |
| Stream choice | Giải thích at-least-once/exactly-once/pending |
| JSON/schema | Types và required fields hợp lệ |
| IAM | Writer SA có quyền ở table, không là Owner |
| ACK/retry | Phân biệt timeout và lỗi vĩnh viễn |
| Batch | Có số bytes/rows/inflight limits |
| Metrics | Dùng WRITE_API_TIMELINE đúng region |
| Duplicates | Giải thích `event_id` và dedup query |
| Chi phí | Ingestion, storage, query, workers/logs |
| Cleanup | Không đụng dữ liệu lab dùng chung |

## 16. Câu hỏi ôn tập

1. **Storage Write API khác Storage Read API?** Một API nạp rows, một API đọc dữ liệu hiệu quả.
2. **Default stream cần CreateWriteStream?** Không.
3. **Default stream bảo đảm exactly-once?** Không; at-least-once, retry có thể trùng.
4. **Committed stream khi nào query thấy rows?** Khi append được xác nhận.
5. **Vì sao committed offsets giúp exactly-once?** Server chỉ chấp nhận append ở next offset hợp lệ của stream.
6. **Exactly-once trong stream có ngăn hai streams ghi cùng event?** Không.
7. **Offset sau batch 7 rows ở offset 12 là bao nhiêu?** 19.
8. **ALREADY_EXISTS nên làm gì?** Xác minh batch đã ghi/checkpoint trước khi tiếp tục.
9. **OUT_OF_RANGE nên làm gì?** Đối chiếu last ACK, bù offsets còn thiếu.
10. **Pending stream khi nào có thể query?** Sau BatchCommitWriteStreams thành công.
11. **Finalize pending có thể tiếp tục append?** Không.
12. **Buffered stream nên dùng phổ biến cho API realtime?** Không; là cơ chế nâng cao.
13. **JsonStreamWriter dùng JSON trên wire gRPC trực tiếp?** Không; chuyển thành protobuf.
14. **Một stream nên tạo cho mỗi HTTP message?** Không; overhead và stream creation quota.
15. **Vì sao cần DLQ?** Lưu records sai schema/hết retries để xử lý có kiểm soát.
16. **BigQuery có tự enforce UNIQUE trên event_id?** Không.
17. **Dùng query liên tục mỗi giây để đo throughput?** Không tối ưu; dùng API metrics/monitoring.
18. **Mất ACK của default stream có thể retry cùng data an toàn tuyệt đối?** Không, có thể sinh duplicate.
19. **Schema thêm field có thể lập tức dùng từ mọi producer?** Không; cần đợi schema propagation/writer refresh.
20. **Phân vùng event_ts có ảnh hưởng gì tới dữ liệu đến muộn?** Late event có thể được ghi vào partition quá khứ, cần query đúng cửa sổ.

## 17. Checklist production và tài liệu tham khảo

- [ ] Phân biệt batch load và near-real-time ingest; chọn gRPC/REST theo khả năng client.
- [ ] Có event schema/version, event_id và quy tắc thời gian UTC/late arrivals.
- [ ] Chọn **default** cho at-least-once hoặc **COMMITTED + offsets** khi cần exactly-once trong stream.
- [ ] Với pending, coordinator finalizes rồi commit nguyên tử; kiểm tra hạn lưu stream.
- [ ] Java writer/client dùng lại, append bất đồng bộ có flow control và chờ ACK trước khi shutdown.
- [ ] Checkpoint stream ID, offset và batch content bền vững nếu dùng committed.
- [ ] Có bounded retry, exponential backoff/jitter, DLQ và replay chống trùng.
- [ ] Quản lý schema evolution; không mặc định ignore unknown fields.
- [ ] Quyền IAM tối thiểu theo table/dataset, ADC, không lưu JSON keys.
- [ ] Dataset/table location, partitioning/clustering và retention được duyệt.
- [ ] Theo dõi throughput/quota, ack p95, Pub/Sub backlog và write errors.
- [ ] Có query/ETL dedup khi các sự kiện duplicate về mặt nghiệp vụ.
- [ ] Có Billing Budget, tối ưu batching, query scans và logging.
- [ ] Có rollout/canary, audit changes và runbook khi BigQuery hoặc Pub/Sub gặp sự cố.

**Tài liệu Google Cloud chính thức:**

- [Storage Write API overview](https://docs.cloud.google.com/bigquery/docs/write-api-intro) — gRPC/REST và lý do chọn.
- [Introduction to Storage Write API gRPC](https://docs.cloud.google.com/bigquery/docs/write-api-grpc) — stream types, permissions, protocol.
- [Streaming with Storage Write API](https://docs.cloud.google.com/bigquery/docs/write-api-streaming) — default và committed Java examples.
- [Batch load with pending streams](https://docs.cloud.google.com/bigquery/docs/write-api-batch-load) — finalize, atomic commit, buffer time.
- [Storage Write API best practices](https://docs.cloud.google.com/bigquery/docs/write-api-best-practices) — throughput, offsets, connection pooling, schema evolution.
- [Storage Write API quotas](https://docs.cloud.google.com/bigquery/quotas#write-api-limits) — request/throughput/connection/stream limits.
- [WRITE_API_TIMELINE information schema](https://docs.cloud.google.com/bigquery/docs/information-schema-write-api) — per-minute stream metrics và error codes.
- [Troubleshooting Storage API](https://docs.cloud.google.com/bigquery/docs/troubleshoot-storage-api) — lỗi/quota/vùng.
- [BigQuery Java client libraries](https://cloud.google.com/java/docs/reference/google-cloud-bigquerystorage/latest/overview) — Java BigQueryWriteClient/JsonStreamWriter.
- [Control access to BigQuery](https://docs.cloud.google.com/bigquery/docs/control-access-to-resources-iam) — BigQuery IAM roles.
- [Partitioned tables](https://docs.cloud.google.com/bigquery/docs/partitioned-tables) và [Clustered tables](https://docs.cloud.google.com/bigquery/docs/clustered-tables) — query pruning.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — ingestion, storage và queries.

**Kết luận:** Storage Write API là **đường nạp dữ liệu**, không phải bộ máy nghiệp vụ exactly-once tự động. **Default stream** phù hợp streaming phổ biến khi chấp nhận at-least-once; **committed streams kèm offsets** chống duplicate **trong một stream**; **pending streams** hỗ trợ atomic batch commit. Một pipeline production còn cần schema rõ ràng, IAM tối thiểu, checkpoint/retry/DLQ, quan sát ingestion lag và kiểm soát chi phí.
