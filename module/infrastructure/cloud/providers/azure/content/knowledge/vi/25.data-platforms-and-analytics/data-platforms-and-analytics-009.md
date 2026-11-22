# Azure Data Explorer và phân tích log hoặc telemetry bằng KQL

Một hệ thống thương mại điện tử chạy trên **Azure App Service**, **Azure Container Apps**, **AKS**, **Azure SQL Database** và **Azure Service Bus** có thể phát sinh hàng triệu sự kiện mỗi ngày: HTTP requests, exceptions, job processing, thông điệp lỗi, dấu vết truy vấn SQL, sự kiện bảo mật và số liệu thiết bị. Khi người dùng báo “trang đặt hàng chậm lúc 09:15”, nhóm vận hành cần trả lời được **dịch vụ nào chậm, bắt đầu từ lúc nào, deployment nào gây ra lỗi, tenant/region nào bị ảnh hưởng, và bằng chứng nào xác nhận đã phục hồi**.

Đọc log thủ công từng máy không giải quyết được khối dữ liệu như vậy. **Azure Data Explorer (ADX)** là nền tảng phân tích dữ liệu lớn, hướng tới log, telemetry, events, clickstream và dữ liệu thời gian, cho phép truy vấn bằng **Kusto Query Language (KQL)** với tốc độ tương tác trên nhiều loại dữ liệu có cấu trúc hoặc bán cấu trúc.

Bài học thuộc chương **Nền tảng dữ liệu và phân tích**, trong module **CLOUD_PROVIDERS_AZURE**. Trong hệ sinh thái Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, compute, storage và database, ADX bổ sung khả năng **thu thập, tổ chức, truy vấn và vận hành dữ liệu quan sát** ở quy mô lớn. Trọng tâm là **thực hành KQL để phân tích log/telemetry**, đồng thời biết cách xây pipeline nạp dữ liệu, cấp quyền, tối ưu hiệu năng và quản trị chi phí. Bài không giả định người học đã có cluster hoặc log production.

Sau bài học, bạn có thể:

- Phân biệt **ADX/Kusto**, **Azure Monitor Logs/Log Analytics**, **Application Insights**, **Event Hubs**, **Azure SQL** và các nền tảng phân tích khác.
- Mô tả kiến trúc **cluster → database → table → extents**, luồng ingestion và query endpoints.
- Thiết kế schema telemetry có **event time, operation, status, duration, trace ID, dimensions** và trường `dynamic`.
- Viết KQL với `where`, `project`, `extend`, `summarize`, `bin()`, `percentile()`, `dcount()`, `join`, `parse_json()`, `mv-expand`, `make-series`.
- Phân tích **HTTP 5xx/4xx, lỗi theo deployment, p95/p99 latency, traffic spike, retry, dependency failures**, truy dấu theo correlation ID.
- Tối ưu truy vấn bằng lọc thời gian sớm, giảm cột, giảm cardinality, chọn join, materialized view và caching phù hợp.
- Bảo vệ dữ liệu bằng **Microsoft Entra ID, RBAC/data-plane roles, row-level security**, private networking và quản trị PII/retention.
- Xây quy trình lab KQL có dữ liệu **tổng hợp ngay trong query**, không cần truy cập tenant production.
- Đánh giá ingestion delay, reliability, monitoring, chi phí và chọn đúng giải pháp cho bài toán.

## 1. Azure Data Explorer giải quyết bài toán nào?

**ADX** (còn gọi là **Kusto**) là dịch vụ phân tích gần thời gian thực cho lượng lớn dữ liệu dạng sự kiện. Nó đặc biệt phù hợp với các dữ liệu **append-heavy**: mỗi request, log line, sensor reading hoặc business event tạo một bản ghi mới. Query engine tối ưu để lọc theo thời gian, nhóm sự kiện, tìm mẫu bất thường và tổng hợp theo nhiều chiều.

### 1.1. Ví dụ từ một sự cố thực tế

Nhóm SRE nhận cảnh báo:

~~~text
2026-11-20 09:15 UTC
Orders API p95 latency > 900 ms
HTTP 503 rate tăng từ 0.2% lên 8%
Deployment v42 được phát hành vài phút trước
~~~

Một quy trình điều tra có thể:

1. Lọc telemetry theo **time window** bao quanh 09:15.
2. Vẽ requests/giây và error rate theo `Service`, `Region`.
3. So sánh p95/p99 theo `Deployment` trước và sau release.
4. Lọc `StatusCode >= 500`, tìm `Operation` có tỷ lệ lỗi cao.
5. Dùng `TraceId` liên kết HTTP request với database/dependency logs.
6. Kiểm tra bản ghi gần nhất để xác minh rollback phục hồi.

ADX thực hiện các phép phân tích tập hợp trên nhiều records bằng KQL, không yêu cầu đọc từng log thủ công.

### 1.2. Khi nào ADX phù hợp?

| Nhu cầu | Giá trị ADX mang lại |
|---|---|
| Truy vấn rất nhiều logs/events theo thời gian | Column-oriented analytics, indexing/partitioning và query engine Kusto |
| Telemetry có trường linh hoạt | `dynamic` cho JSON, kết hợp schema cố định để lọc/tổng hợp |
| Gần thời gian thực | Ingestion pipeline từ Event Hubs/Blob/SDK và truy vấn sau khi dữ liệu sẵn sàng |
| Điều tra incident | `where`, `summarize`, `join`, time series, correlation ID |
| Dashboard/alert phân tích | Truy vấn KQL qua giao diện, API, workbook/Grafana/BI theo tích hợp |
| Hàng tỷ sự kiện lâu dài | Retention/caching policy và dữ liệu append được quản trị theo dung lượng/compute |
| IoT/clickstream/cyber telemetry | Aggregation và khám phá patterns theo nhiều chiều |

**ADX không phải OLTP database** để đặt hàng với transactional updates trên từng row. Nó cũng không mặc nhiên thay **SIEM, alerting platform hoặc message broker**; mỗi dịch vụ có trách nhiệm riêng.

### 1.3. Luồng dữ liệu tham chiếu

~~~mermaid
flowchart LR
    APPS[App Service / AKS / Container Apps] -->|Structured logs/events| HUB[Azure Event Hubs]
    IOT[IoT sensors] -->|Telemetry| HUB
    STORAGE[Blob Storage / Data Lake] -->|Files / Event Grid| ING[Ingestion service]
    HUB --> ING
    ING --> ADX[(Azure Data Explorer cluster)]
    ADX --> DB[(Database / Tables / Extents)]
    DB --> KQL[KQL queries]
    KQL --> SRE[SRE investigations]
    KQL --> DASH[Dashboards / reporting]
    KQL --> ALERT[Alerts / automation when configured]
    MON[Azure Monitor] -. Platform and pipeline metrics .-> ADX
~~~

Không phải mọi ứng dụng phải gửi logs **qua Event Hubs**. Có nhiều đường ingestion; chọn đường nào phụ thuộc throughput, định dạng dữ liệu, độ trễ, replay, network và chi phí. **Pipeline mới chỉ là mô hình** cho bài học, không phải tài nguyên Azure đang tồn tại.

## 2. ADX so với Azure Monitor Logs, Application Insights và Azure SQL

Điểm dễ nhầm nhất: **Azure Monitor Logs cũng dùng KQL**, nhưng **không đồng nghĩa Log Analytics workspace là một Azure Data Explorer database của bạn**. Chúng có chung nền tảng ngôn ngữ/truy vấn Kusto, nhưng scope, schema, ingestion, quyền và billing khác nhau.

| Công nghệ | Vai trò chính | Khi ưu tiên |
|---|---|---|
| **Azure Data Explorer** | Kho phân tích events/logs quy mô lớn, schema và ingestion do nhóm dữ liệu quản trị | Cần kiểm soát ingestion/query, phân tích telemetry chuyên biệt, data exploration |
| **Azure Monitor Logs / Log Analytics** | Log platform tích hợp monitoring tài nguyên Azure, KQL queries và alert rules | Hạ tầng/ứng dụng Azure monitoring, resource logs, alert vận hành |
| **Application Insights** | Application Performance Monitoring (requests, dependencies, traces, exceptions) | Điều tra performance và distributed tracing app |
| **Azure Event Hubs** | Ingest/buffer event stream thông lượng lớn | Tách producer khỏi consumer, lưu events tạm để xử lý; không là kho KQL analytics |
| **Azure SQL Database** | OLTP transactions, relational constraints, cập nhật theo record | Source of truth cho orders/payments/users |
| **Azure Data Lake / Blob** | File/object lưu dữ liệu chi phí phù hợp | Raw events, archive, export/replay và downstream processing |
| **Microsoft Fabric Real-Time Intelligence** | Nền tảng phân tích thời gian thực và Eventhouse/KQL theo mô hình Fabric | Tổ chức dùng Fabric, cần kết hợp trải nghiệm dữ liệu/BI; xem feature/giá riêng |

### 2.1. Cùng ngôn ngữ, không cùng mọi tính năng

Một số KQL operators dùng được ở cả ADX và Azure Monitor Logs, ví dụ:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| summarize Requests=count() by bin(Timestamp, 5m)
~~~

Nhưng query này chỉ chạy khi **bảng `ApiTelemetry` có tồn tại** ở môi trường đang query. Trong Log Analytics, có thể phải dùng bảng khác như `AppRequests`, `AppTraces` hoặc `AzureDiagnostics` với **tên cột khác**. Lệnh quản trị như `.create table`, ingestion mapping và data retention trong ADX không tự áp dụng lên Log Analytics workspace.

**Không copy một truy vấn dùng `TimeGenerated` trên Log Analytics rồi chạy trong ADX custom table chỉ có `Timestamp` mà kỳ vọng tự đổi tên.** Trước hết kiểm tra schema.

### 2.2. Quy tắc chọn nhanh

- Muốn xem **Application Insights requests/dependencies/exception** đã có sẵn, hãy bắt đầu từ Azure Monitor/Application Insights trước khi xây thêm ADX.
- Muốn quản trị **pipeline events nhiều nguồn**, schema, retention và các truy vấn analytics tùy biến trên dữ liệu rất lớn, ADX có thể phù hợp.
- Muốn SQL transaction, foreign keys, isolation và point updates, dùng database OLTP.
- Muốn buffer dòng message và replay có giới hạn, dùng Event Hubs/Service Bus theo semantics; ADX là nơi **phân tích**, không phải queue worker truyền thống.

Chỉ thêm ADX khi **lợi ích phân tích/retention/performance** lớn hơn chi phí ingest + compute + lưu trữ + vận hành.

## 3. Kiến trúc Kusto: cluster, database, table và extents

Một ADX deployment có các khái niệm:

~~~text
Azure subscription
└── Resource group
    └── Azure Data Explorer cluster: adx-observability-prod
        ├── Database: Telemetry
        │   ├── Table: ApiTelemetry
        │   ├── Table: DependencyTelemetry
        │   ├── Table: DeploymentEvents
        │   ├── Functions / Materialized views
        │   └── Ingestion mappings / retention / caching policies
        └── Database: SecurityEvents
            ├── Table: AuditEvents
            └── Table: AuthFailures
~~~

### 3.1. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Điều cần chú ý |
|---|---|---|
| **Cluster** | Compute/engine của Kusto, endpoint để query/nạp dữ liệu | SKU, scale, network, Azure RBAC/control plane |
| **Database** | Đơn vị logic chứa tables/functions/policies | Data-plane roles, quyền đọc/nạp/quản trị |
| **Table** | Records dạng cột với schema rõ | Data types, mapping, retention và truy vấn |
| **Extent** | Đơn vị lưu trữ dữ liệu dạng cột, thường immutable trong kiến trúc ingest | Ingest batches, merge/optimization, caching |
| **Ingestion mapping** | Ánh xạ JSON/CSV/Parquet fields vào columns | Schema evolution và lỗi ingest |
| **Function** | Query logic có tên, tái sử dụng | Governance, quyền, kiểm thử version |
| **Materialized view** | Tổng hợp/tính toán được cập nhật từ source theo chính sách | Giảm query cost; tăng ingest/compute overhead |
| **Retention policy** | Dữ liệu tồn tại bao lâu trước khi được loại theo quy định | Compliance, storage cost, thời gian điều tra |
| **Caching policy** | Phần dữ liệu được giữ ở cache nhanh của engine | Tốc độ truy vấn gần đây và chi phí/compute |

### 3.2. Vì sao ADX giỏi dữ liệu thời gian?

ADX tổ chức dữ liệu theo dạng cột và các đơn vị lưu trữ có metadata. Khi truy vấn:

~~~kusto
ApiTelemetry
| where Timestamp between (ago(1h) .. now())
| where Service == "orders-api" and StatusCode >= 500
| project Timestamp, Operation, StatusCode, DurationMs, TraceId
~~~

Engine có thể bỏ qua nhiều dữ liệu không thuộc khoảng thời gian/lọc cột thay vì đọc toàn bộ JSON thô. **Schema, thời điểm ingest, data distribution và query shape** ảnh hưởng khả năng pruning/scan; không nên khẳng định mọi truy vấn đều chạy theo thời gian cố định bất kể dataset.

### 3.3. Query endpoint và ingestion endpoint

Với ADX cluster truyền thống, query endpoint thường dạng:

~~~text
https://<cluster>.<region>.kusto.windows.net
~~~

Ingestion endpoint có thể có tiền tố:

~~~text
https://ingest-<cluster>.<region>.kusto.windows.net
~~~

**Đây là pattern minh họa**, tùy Azure Data Explorer resource/endpoint. Đọc URI thực trong Portal/resource properties, đặc biệt với môi trường free/những dịch vụ tích hợp khác. Không dùng URL ingestion để giả định nó hỗ trợ mọi query SDK operation và ngược lại.

## 4. Thiết kế schema cho log và telemetry

Chất lượng query bắt đầu từ **log contract**. Nếu app ghi chuỗi `Something failed` mà không có timestamp/operation/status/trace ID, KQL có thể tìm văn bản nhưng không dễ tổng hợp, so sánh hoặc trace.

### 4.1. Một bản ghi telemetry nên có gì?

~~~json
{
  "timestamp": "2026-11-20T09:15:14.221Z",
  "service": "orders-api",
  "environment": "prod",
  "operation": "GET /orders/{id}",
  "statusCode": 503,
  "durationMs": 946.4,
  "region": "southeastasia",
  "traceId": "trace-cc42",
  "spanId": "span-001",
  "severity": "Error",
  "properties": {
    "deployment": "v42",
    "dependency": "sql-orders",
    "errorCategory": "SqlTimeout"
  }
}
~~~

**Dữ liệu trên là tổng hợp**, không có user hay hệ thống thực. Không lưu raw access tokens, mật khẩu, cookie session, thông tin thanh toán hoặc PII trong log chỉ để query tiện.

### 4.2. Schema ADX giả định cho các ví dụ

| Cột | Type KQL | Ý nghĩa |
|---|---|---|
| `Timestamp` | `datetime` | **Event time** (UTC) do nguồn phát ghi |
| `Service` | `string` | Tên workload như `orders-api` |
| `Environment` | `string` | `prod`/`staging`/`dev` |
| `Operation` | `string` | HTTP route template hoặc loại tác vụ |
| `StatusCode` | `int` | HTTP status hoặc status map đã chuẩn hóa |
| `DurationMs` | `real` | Thời lượng theo milliseconds |
| `Region` | `string` | Azure region/địa điểm logic, không chứa vị trí người dùng |
| `TraceId` | `string` | ID tương quan request/distributed trace |
| `SpanId` | `string` | ID span khi có tracing |
| `Severity` | `string` | `Info`, `Warning`, `Error` |
| `Properties` | `dynamic` | Additional JSON fields: deployment, dependency, error category |

Đặt `Timestamp` ở kiểu **datetime thật**, không để mọi thứ ở string rồi chạy `todatetime` trên hàng tỷ records. Chuẩn hóa tên columns và values (ví dụ `prod` vs `production`) ngay khi ingest. Lưu những fields lọc/aggregate thường xuyên ở **cột tĩnh** thay vì nhét tất cả vào JSON dynamic.

### 4.3. Event time khác ingestion time

~~~text
Source event time:  09:15:14.221 UTC
Event Hubs enqueue: 09:15:14.310 UTC
ADX ingestion time: 09:15:20.800 UTC
Query time:         09:15:22.000 UTC
~~~

Sự kiện có thể đến muộn do batch, network, retries hoặc offline devices. **Phân tích latency API phải dùng event time/duration đúng**, trong khi **độ trễ pipeline** cần so event time và thời điểm ingest. KQL `ingestion_time()` chỉ hữu dụng khi ingestion-time policy/metadata được bật và có dữ liệu; có trường hợp trả null. Nếu yêu cầu chặt về observability, cân nhắc ghi `ReceivedAtUtc` hoặc metadata ingest theo chính sách pipeline.

### 4.4. Cardinality và bảo mật thông tin

**Cardinality cao** là số lượng giá trị khác nhau rất lớn: orderId, requestId, userId. Nó hữu ích để trace một request nhưng là lựa chọn tồi cho bảng dashboard nhóm theo mọi ID (kết quả khổng lồ). Nên:

- Aggregate theo `Service`, `Region`, `Operation`, `StatusCode`, `Deployment` trước.
- Chỉ dùng `TraceId` để drill down khi điều tra.
- Redact/hashing identifiers khi được phép và cần; không xem hash là cách chắc chắn loại bỏ khả năng nhận diện.
- Không ghi URL path chứa ID/PII raw nếu có thể dùng **route template**.
- Định nghĩa retention theo lớp dữ liệu; audit logs khác debug traces.

**Mục tiêu schema:** phân tích chính xác mà không vô tình biến data lake/log platform thành kho dữ liệu cá nhân không kiểm soát.

## 5. Ingestion: đưa logs/events vào Azure Data Explorer

KQL chỉ trả lời được dựa trên **dữ liệu đã nạp đúng schema**. Một pipeline ingestion cần định nghĩa **nguồn, định dạng, đường truyền, mapping, retry, checkpoint, duplicate handling, validation, retention** và cách theo dõi độ trễ.

### 5.1. Các nguồn dữ liệu phổ biến

| Nguồn | Hướng tích hợp thường gặp | Khi dùng |
|---|---|---|
| **Azure Event Hubs** | ADX data connection đọc stream từ consumer group | Request/event stream liên tục, cần buffer và độ trễ nhỏ |
| **Azure Blob Storage / ADLS** | Queued ingest, Event Grid data connection hoặc ingestion SDK | NDJSON/CSV/Parquet files, backfill lịch sử |
| **Application/ETL SDK** | Ingestion SDK/API, batching | Dữ liệu đã chuẩn hóa hoặc tích hợp riêng |
| **Kafka / connectors** | Kafka Connect hoặc bridge tương ứng | Tổ chức đã có streaming pipeline |
| **Azure IoT Hub** | Data connection theo dịch vụ/tính năng | IoT telemetry được truyền vào Azure |
| **Các hệ thống monitoring** | Export/stream qua giải pháp được hỗ trợ | Phân tích tập trung trên dữ liệu được cho phép xuất |

**Đừng mặc định mọi Azure Monitor/App Insights log tự chảy sang ADX.** Cần thiết lập export, streaming hoặc ingestion riêng nếu muốn sao chép dữ liệu. Điều này tạo **chi phí và bản sao dữ liệu** mới, phải xét quyền truy cập và retention.

### 5.2. Streaming ingestion và queued ingestion

| Đặc tính | Queued ingestion | Streaming ingestion |
|---|---|---|
| Mục tiêu | Throughput lớn, tối ưu batch/cost | Độ trễ xuất hiện dữ liệu thấp |
| Cách xử lý | Gom thành batches/extents theo pipeline | Truy cập dữ liệu mới sớm hơn theo cơ chế dịch vụ |
| Cost/compute | Thường phù hợp phần lớn workloads ingest lớn | Có overhead và feature restrictions |
| Phù hợp | 100 GB logs/ngày không cần phản hồi từng giây | Telemetry operational gần real-time |
| Rủi ro | Ingestion delay tăng khi backlog | Không nên bật bừa với event size/volume không phù hợp |

**“Near real time” không có nghĩa zero lag hoặc exactly-once delivery.** End-to-end latency gồm producer, Event Hubs, connector, ingestion batching và KQL query. Đo **ingestion lag** thực tế theo nguồn.

### 5.3. Pipeline Event Hubs → ADX

~~~mermaid
sequenceDiagram
    participant API as Orders API
    participant EH as Azure Event Hubs
    participant CONN as ADX Data Connection
    participant T as ADX ApiTelemetry
    participant SRE as KQL Analyst
    API->>EH: Publish JSON event with event time and trace ID
    EH-->>CONN: Read batch from consumer group / partition
    CONN->>T: Apply ingestion mapping and ingest
    T-->>CONN: Ingestion status / checkpoint workflow
    SRE->>T: Query recent window
    T-->>SRE: Aggregated results
~~~

Điểm cần triển khai:

1. **Event Hub namespace/topic và partition capacity** đủ throughput.
2. Consumer group **riêng cho ADX connector** khi cần độc lập với consumer khác.
3. Quyền đọc Event Hubs và ghi vào ADX phù hợp, ưu tiên managed identity được hỗ trợ.
4. Chọn **target database/table, data format và ingestion mapping** đúng.
5. Có khả năng quan sát bad records, mapping failures và ingestion delay.
6. Event Hubs retention đủ để xử lý outage/backfill theo kế hoạch, không phải lưu trữ vĩnh viễn.
7. Xử lý **at-least-once/duplicate events** theo key nếu nghiệp vụ yêu cầu kết quả chính xác.

Nếu producer gửi mỗi event 10 lần do retry, ADX không tự biết đâu là bản trùng nếu không có `EventId`/logic dedup. Query `count()` sẽ đếm cả bản trùng; cần quyết định cách khử trùng trước ingest hoặc trong query.

### 5.4. Bảng và JSON ingestion mapping (tham khảo)

Trong **ADX database được phép quản trị**, có thể tạo table với Kusto management command:

~~~kusto
// Administrative command: chỉ chạy trong database lab được cấp phép.
.create table ApiTelemetry (
    Timestamp: datetime,
    Service: string,
    Environment: string,
    Operation: string,
    StatusCode: int,
    DurationMs: real,
    Region: string,
    TraceId: string,
    SpanId: string,
    Severity: string,
    Properties: dynamic
)
~~~

Một **JSON ingestion mapping** minh họa:

~~~kusto
// Ánh xạ path từ JSON source sang các cột của bảng.
.create table ApiTelemetry ingestion json mapping 'ApiTelemetryJson'
'[
  {"column":"Timestamp","path":"$.timestamp","datatype":"datetime"},
  {"column":"Service","path":"$.service","datatype":"string"},
  {"column":"Environment","path":"$.environment","datatype":"string"},
  {"column":"Operation","path":"$.operation","datatype":"string"},
  {"column":"StatusCode","path":"$.statusCode","datatype":"int"},
  {"column":"DurationMs","path":"$.durationMs","datatype":"real"},
  {"column":"Region","path":"$.region","datatype":"string"},
  {"column":"TraceId","path":"$.traceId","datatype":"string"},
  {"column":"SpanId","path":"$.spanId","datatype":"string"},
  {"column":"Severity","path":"$.severity","datatype":"string"},
  {"column":"Properties","path":"$.properties","datatype":"dynamic"}
]'
~~~

**Quan trọng:**

- Những lệnh bắt đầu bằng dấu chấm (`.create`, `.show`, `.alter`) là **management commands**, không phải query KQL thông thường. Chúng cần database/table permissions.
- Không chạy `.create` trên database production khi chưa có change approval; bài có **lab datatable không cần tạo table** ở phần sau.
- Mapping phải tương thích JSON thực tế. Một JSON field thiếu/không đúng type có thể tạo null hoặc ingest failure theo pipeline; test schema changes.
- Dữ liệu event nên ghi dưới dạng NDJSON/stream records theo format ingestion hỗ trợ, không dùng một JSON array khổng lồ rồi giả định connector tự tách.
- Có thể cần mapping reference và data connection authorization theo phương án triển khai; tạo table đơn lẻ chưa nạp được dữ liệu.

### 5.5. Ingestion-time validation và dead-letter strategy

Nếu producer gửi:

~~~json
{
  "timestamp": "not-a-date",
  "service": "orders-api",
  "durationMs": "very slow"
}
~~~

thì mapping sang `datetime` và `real` sẽ có vấn đề. Hệ thống nên:

- Validate payload/schema ở producer hoặc ingestion layer.
- Có `schemaVersion` để rollout tương thích.
- Ghi nhận **ingestion failures** qua monitoring/connector status.
- Lưu raw events an toàn trong Event Hubs/Blob theo retention phù hợp nếu cần replay.
- Có runbook sửa mapping, backfill và phân loại poison records.
- Không để một lô records lỗi kéo theo mất cả ngày telemetry mà không có alert.

ADX không mặc nhiên tạo một “dead-letter queue” riêng cho mọi ingestion source; khả năng báo lỗi/quarantine phụ thuộc ingestion mechanism, cần thiết kế rõ.

### 5.6. Ingestion time, idempotency và ordering

ADX phù hợp với dữ liệu events **append-only**. Vì network/retry/replay, event có thể:

- Đến muộn so với `Timestamp`.
- Đến không đúng thứ tự.
- Bị gửi lặp.
- Có nhiều versions cho cùng logical event.

Nếu cần dedup:

~~~kusto
// Chỉ minh họa khi schema có EventId và ReceivedAtUtc.
ApiTelemetry
| where Timestamp > ago(1d)
| summarize arg_max(ReceivedAtUtc, *) by EventId
~~~

**Không copy query này vào bảng không có `EventId`/`ReceivedAtUtc`.** Nó cũng chỉ chọn bản ghi cuối **theo dữ liệu đang hiện diện ở thời điểm query**, không khẳng định ingestion exactly once. Để bảo vệ doanh thu/giao dịch, uniqueness phải nằm trong hệ thống authoritative.

## 6. KQL cơ bản: truy vấn theo pipeline

**Kusto Query Language** dùng biểu thức dạng **bảng | operator | operator | ...**. Mỗi operator nhận dữ liệu trước đó, lọc/biến đổi/nhóm và chuyển kết quả cho bước tiếp theo. KQL khác SQL ở cú pháp và tư duy xử lý, dù đều dùng khái niệm bảng và aggregates.

### 6.1. Một query đơn giản

~~~kusto
ApiTelemetry
| where Timestamp > ago(30m)
| where Environment == "prod"
| project Timestamp, Service, Operation, StatusCode, DurationMs
| order by Timestamp desc
| take 100
~~~

Đọc từ trái sang phải:

1. Lấy records từ `ApiTelemetry`.
2. Giữ các events trong **30 phút gần đây**.
3. Chỉ chọn môi trường production.
4. Chỉ giữ năm cột cần xem.
5. Sắp xếp mới nhất lên trước.
6. Chỉ trả 100 rows.

KQL **case-sensitive** cho tên bảng/cột; tên `Timestamp` khác `timestamp` nếu schema định nghĩa khác. String operator `==` thường so sánh có phân biệt hoa/thường; `=~` so sánh không phân biệt hoa/thường theo semantics của Kusto.

### 6.2. Các operator nền tảng

| Operator | Tác dụng | Ví dụ |
|---|---|---|
| `where` | Lọc rows | `where StatusCode >= 500` |
| `project` | Chọn/đổi tên cột | `project Timestamp, DurationMs` |
| `extend` | Tạo cột tính toán | `extend IsError = StatusCode >= 500` |
| `summarize` | Group và aggregate | `summarize Events=count() by Service` |
| `order by` / `sort by` | Sắp xếp | `order by DurationMs desc` |
| `top` | Lấy N rows đứng đầu theo tiêu chí | `top 10 by DurationMs desc` |
| `take` / `limit` | Lấy một số rows (không bảo đảm thứ tự nếu không sort) | `take 20` |
| `distinct` | Các giá trị/kết hợp khác nhau | `distinct Service, Region` |
| `join` | Liên kết bảng theo khóa | `join kind=leftouter ... on TraceId` |
| `union` | Gộp rows từ nhiều nguồn tương thích | `union ApiTelemetry, DependencyTelemetry` |
| `mv-expand` | Mở rộng phần tử mảng/bag dynamic thành rows | `mv-expand ErrorTags` |
| `render` | Hiển thị kết quả thành chart trong UI hỗ trợ | `render timechart` |

### 6.3. Cú pháp scalar và data types

~~~kusto
print
    QueryTime = now(),
    WindowStart = ago(1h),
    Threshold = 500,
    Success = true,
    Ratio = 1.5,
    Region = "southeastasia",
    Tags = dynamic({"env":"prod","service":"orders-api"})
~~~

Các kiểu thường gặp gồm `bool`, `int`, `long`, `real`, `decimal`, `string`, `datetime`, `timespan`, `dynamic`, `guid`. Dữ liệu thời gian nên thống nhất **UTC**, tránh trộn local time trong logs rồi báo sai thời điểm incident.

### 6.4. KQL `let` và dấu chấm phẩy

`let` đặt tên cho biểu thức/query fragment để tái sử dụng trong **phạm vi câu query**:

~~~kusto
let Window = 1h;
let TargetEnvironment = "prod";
ApiTelemetry
| where Timestamp > ago(Window)
| where Environment == TargetEnvironment
| summarize Events=count() by Service
~~~

Các `let` statements kết thúc bằng dấu chấm phẩy (`;`). Một `let` ở query editor này **không tự tồn tại** trong query tab khác hoặc các lần SDK call khác; nếu cần dùng chung lâu dài, xem **stored functions** hoặc query templates.

### 6.5. `has` khác `contains`

~~~kusto
// Khi lọc message text (nếu bảng có Message:string):
ApiTelemetry
| where Timestamp > ago(1h)
| where tostring(Properties.errorMessage) has "timeout"
~~~

`has` dựa trên **term/token** phù hợp cơ chế Kusto, thường hiệu quả hơn `contains` cho việc tìm **từ** có index hỗ trợ. `contains` tìm **substring** (kể cả trong từ dài), hữu ích nhưng có thể scan rộng hơn. Biến thể `has_cs`/`contains_cs` có phân biệt hoa/thường.

**Ví dụ:** `has "error"` không mặc định khớp mọi chuỗi `errorsomething`; `contains "error"` có thể khớp substring này. Chọn operator theo semantics trước khi tối ưu.

## 7. Lab KQL đầu tiên: dữ liệu tự tạo, không cần cluster production

Người học có thể sử dụng Kusto query editor trong **Azure Data Explorer Web UI** hoặc môi trường KQL được phép, nhập một `datatable` chứa events giả. Ví dụ này là **self-contained**, không gọi đến bảng production và không tạo dữ liệu persistent.

### 7.1. Dataset thử nghiệm

~~~kusto
let Demo = datatable(
    Timestamp:datetime, Service:string, Environment:string,
    Operation:string, StatusCode:int, DurationMs:real,
    Region:string, TraceId:string, Properties:dynamic)
[
    datetime(2026-11-20T09:00:00Z), "orders-api", "prod", "GET /orders/{id}", 200,  82.0, "southeastasia", "tr-001", dynamic({"deployment":"v41","dependency":"sql"}),
    datetime(2026-11-20T09:01:00Z), "orders-api", "prod", "GET /orders/{id}", 200,  75.0, "southeastasia", "tr-002", dynamic({"deployment":"v41","dependency":"sql"}),
    datetime(2026-11-20T09:02:00Z), "orders-api", "prod", "POST /orders",      201, 180.0, "southeastasia", "tr-003", dynamic({"deployment":"v41","dependency":"sql"}),
    datetime(2026-11-20T09:10:00Z), "orders-api", "prod", "GET /orders/{id}", 200,  95.0, "southeastasia", "tr-004", dynamic({"deployment":"v42","dependency":"sql"}),
    datetime(2026-11-20T09:11:00Z), "orders-api", "prod", "GET /orders/{id}", 503, 950.0, "southeastasia", "tr-005", dynamic({"deployment":"v42","errorCategory":"SqlTimeout"}),
    datetime(2026-11-20T09:12:00Z), "orders-api", "prod", "POST /orders",      500, 820.0, "southeastasia", "tr-006", dynamic({"deployment":"v42","errorCategory":"SqlTimeout"}),
    datetime(2026-11-20T09:13:00Z), "orders-api", "prod", "GET /orders/{id}", 503, 991.0, "southeastasia", "tr-007", dynamic({"deployment":"v42","errorCategory":"SqlTimeout"}),
    datetime(2026-11-20T09:14:00Z), "orders-api", "prod", "GET /orders/{id}", 429,  18.0, "southeastasia", "tr-008", dynamic({"deployment":"v42","errorCategory":"RateLimit"}),
    datetime(2026-11-20T09:15:00Z), "orders-api", "prod", "GET /orders/{id}", 200,  91.0, "eastasia",      "tr-009", dynamic({"deployment":"v42","dependency":"sql"}),
    datetime(2026-11-20T09:16:00Z), "orders-api", "prod", "GET /orders/{id}", 503, 978.0, "southeastasia", "tr-010", dynamic({"deployment":"v42","errorCategory":"SqlTimeout"}),
    datetime(2026-11-20T09:17:00Z), "catalog-api","prod", "GET /products",    200,  37.0, "southeastasia", "tr-011", dynamic({"deployment":"v13","dependency":"redis"}),
    datetime(2026-11-20T09:18:00Z), "catalog-api","prod", "GET /products",    200,  41.0, "southeastasia", "tr-012", dynamic({"deployment":"v13","dependency":"redis"}),
    datetime(2026-11-20T09:19:00Z), "orders-api", "staging", "POST /orders",    500, 500.0, "southeastasia", "tr-013", dynamic({"deployment":"v42-test","errorCategory":"TestFault"})
];
Demo
| where Environment == "prod"
| project Timestamp, Service, Operation, StatusCode, DurationMs, Region
| order by Timestamp asc
~~~

Dataset có **13 records tổng hợp**, trong đó có một event **staging** dùng để kiểm tra lọc môi trường. Nó cố tình mô phỏng deployment `v42` gây lỗi SQL ở region `southeastasia`. Không so sánh các số liệu trong bảng nhỏ này với SLO production; percentiles trên sample nhỏ chỉ minh họa cú pháp.

### 7.2. Query aggregation tự chạy

~~~kusto
let Demo = datatable(Service:string, StatusCode:int, DurationMs:real)
[
  "orders-api", 200, 82.0,
  "orders-api", 503, 950.0,
  "orders-api", 500, 820.0,
  "orders-api", 429, 18.0,
  "catalog-api", 200, 37.0,
  "catalog-api", 200, 41.0
];
Demo
| summarize
    Requests = count(),
    ServerErrors = countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms = percentile(DurationMs, 95)
  by Service
| extend ServerErrorRatePct = round(100.0 * ServerErrors / Requests, 2)
| order by ServerErrorRatePct desc
~~~

**Kết quả mong đợi:** `orders-api` có 4 requests, 2 HTTP 5xx → **50% server error rate**; `catalog-api` có 2 requests, 0 HTTP 5xx → **0%**. `429` là client throttling và **không** thuộc HTTP 5xx. Percentile được Kusto ước lượng theo thuật toán của engine; không dùng 6 dòng mẫu để suy ra latency percentile của production.

### 7.3. Một khác biệt quan trọng: KQL cố định vs `ago()`

Dataset ở trên dùng **ngày 2026-11-20**. Nếu ngày thực hành cách xa thời điểm này, thêm:

~~~kusto
| where Timestamp > ago(1h)
~~~

sẽ trả **0 rows**, không phải do KQL hoặc ADX hỏng. Trong bài lab dữ liệu lịch sử cố định, dùng `between (datetime(...) .. datetime(...))`; với telemetry live, dùng `ago(1h)`.

### 7.4. Lab an toàn

`datatable` chỉ tạo dữ liệu trong một query. Không cấp quyền tạo table, ingest hay xóa dữ liệu chỉ để chạy bài này. Nếu dùng Free cluster hoặc môi trường lab của tổ chức, kiểm tra quota/điều khoản và không đưa dữ liệu người dùng thật vào ví dụ.

## 8. KQL lọc dữ liệu theo thời gian, dịch vụ và văn bản

Ở bảng log lớn, **đặt điều kiện thời gian sớm** là một trong những cải tiến hiệu năng quan trọng nhất. Không nên đọc toàn bộ vài năm telemetry rồi mới lọc một phút cuối trong phần aggregate.

**Quy ước cho những query tiếp theo:** giả sử đã nạp bảng `ApiTelemetry` có schema tại phần 4.2. Những truy vấn này là **mẫu cho bảng ADX đã chuẩn bị**, không tự chạy trên môi trường chưa có bảng. Khi tự học không có ADX, thay `ApiTelemetry` bằng `Demo` sau khi khai báo `let Demo=datatable(...)` trong **cùng một query**.

### 8.1. Khoảng thời gian relative

~~~kusto
ApiTelemetry
| where Timestamp >= ago(1h) and Timestamp < now()
| where Environment == "prod"
| project Timestamp, Service, StatusCode, DurationMs
| order by Timestamp desc
~~~

`ago(1h)` tính từ thời điểm query, không phải “giờ bắt đầu incident” bất biến. Khi điều tra một sự cố trong quá khứ, ghi **absolute start/end UTC**:

~~~kusto
let StartUtc = datetime(2026-11-20T09:00:00Z);
let EndUtc = datetime(2026-11-20T10:00:00Z);
ApiTelemetry
| where Timestamp between (StartUtc .. EndUtc)
| where Service == "orders-api"
| order by Timestamp asc
~~~

**Nuance:** `between` bao gồm cả các biên theo semantics KQL; với time windows liên tiếp để không đếm trùng một event ở biên, dùng điều kiện **`Timestamp >= StartUtc and Timestamp < EndUtc`**.

### 8.2. Lọc nhiều services/status

~~~kusto
ApiTelemetry
| where Timestamp >= ago(6h)
| where Environment == "prod"
| where Service in ("orders-api", "payments-api", "catalog-api")
| where StatusCode >= 500 and StatusCode < 600
| project Timestamp, Service, Operation, StatusCode, TraceId
~~~

`in` thường so sánh chuỗi phân biệt hoa/thường; `in~` cho so sánh không phân biệt hoa/thường theo Kusto. Với telemetry được chuẩn hóa, **nên dùng một chuẩn tên duy nhất** để tránh query phải bù cho dữ liệu bẩn.

### 8.3. Lọc theo text trong `dynamic`

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| where Service == "orders-api"
| extend ErrorCategory = tostring(Properties.errorCategory)
| where ErrorCategory has "Timeout"
| project Timestamp, Operation, StatusCode, ErrorCategory, TraceId
~~~

Nếu giá trị `errorCategory` được định nghĩa thành `SqlTimeout`, `has "Timeout"` **có thể không khớp như mong muốn** vì `has` tìm term theo tokenization; với mã lỗi dạng CamelCase, tốt nhất so khớp **đúng giá trị**:

~~~kusto
| where ErrorCategory == "SqlTimeout"
~~~

hoặc dùng substring nếu mục đích là khám phá text:

~~~kusto
| where ErrorCategory contains "Timeout"
~~~

**Chọn operator dựa trên semantics.** Điều kiện `has` thường khai thác term index tốt, `contains` có thể phải scan nhiều hơn nhưng khớp substring.

### 8.4. Lọc error thay vì mọi 4xx

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| extend IsServerError = StatusCode between (500 .. 599),
         IsClientError = StatusCode between (400 .. 499)
| summarize
    Requests=count(),
    ServerErrors=countif(IsServerError),
    ClientErrors=countif(IsClientError)
  by Service
~~~

**HTTP 401/403/404/429** có thể là hành vi bảo vệ đúng hoặc lỗi client, không tự tính vào availability outage như 5xx. Một 429 tăng đột biến vẫn có thể gây gián đoạn trải nghiệm; đo thêm **throttled rate** riêng. Với workloads không dùng HTTP, cần chuẩn hóa `StatusCode`/`Success` riêng thay vì ép mọi message thành status 500.

## 9. Aggregation: requests, error rate, p95/p99 latency

`summarize` là công cụ trung tâm của phân tích telemetry. Nó gom records theo dimensions, áp aggregates rồi trả bảng nhỏ hơn để quan sát trends.

### 9.1. Requests theo 5 phút

~~~kusto
ApiTelemetry
| where Timestamp > ago(24h)
| where Environment == "prod"
| summarize Requests=count() by Service, bin(Timestamp, 5m)
| order by Timestamp asc, Service asc
| render timechart
~~~

**`bin(Timestamp, 5m)` làm tròn về bucket 5 phút**, không phải thay mọi timestamps thành một thời điểm tùy ý. Với UI Kusto có hỗ trợ `render timechart`, bạn sẽ thấy một đường series theo service; SDK/automation có thể lấy kết quả bảng mà không tự tạo chart.

### 9.2. Error rate theo service và region

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Environment == "prod"
| summarize
    Requests = count(),
    Http5xx = countif(StatusCode >= 500 and StatusCode < 600),
    Http429 = countif(StatusCode == 429)
  by Service, Region, bin(Timestamp, 5m)
| extend
    ErrorRatePct = round(100.0 * todouble(Http5xx) / Requests, 2),
    ThrottledRatePct = round(100.0 * todouble(Http429) / Requests, 2)
| order by Timestamp asc, ErrorRatePct desc
~~~

Do `summarize` chỉ tạo bucket nếu có records, mẫu trên không hiện các khoảng hoàn toàn không có traffic; nếu cần chart với **missing intervals = 0**, xem `make-series` ở phần time series. Hãy lưu ý `Requests` đếm những events đã được ingest; nếu ingestion lag hoặc sampling, không nhất thiết là toàn bộ traffic thật.

### 9.3. Latency percentiles

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| where Environment == "prod"
| where DurationMs >= 0
| summarize
    Requests = count(),
    AverageMs = round(avg(DurationMs), 1),
    P50Ms = round(percentile(DurationMs, 50), 1),
    P95Ms = round(percentile(DurationMs, 95), 1),
    P99Ms = round(percentile(DurationMs, 99), 1),
    MaxMs = max(DurationMs)
  by Service, Operation
| top 20 by P95Ms desc
~~~

**Tại sao cần p95/p99?** Nếu 95% requests nhanh nhưng 5% rất chậm, **average** có thể che trải nghiệm xấu ở tail. Percentiles trong các engine phân tán có thể là **approximate**, nhất là khi lượng mẫu nhỏ/hoạt động theo buckets. Đừng cộng hay lấy trung bình các p95 đã aggregate để có p95 toàn cục; cần tính percentile trên dữ liệu gốc hoặc phương pháp phân phối phù hợp.

### 9.4. SLO và minimum sample size

Giả sử SLO nội bộ:

~~~text
Successful authorized GET /orders/{id}:
  p95 latency < 500 ms per 5-minute window
  availability target >= 99.9%
~~~

Truy vấn:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| where Environment == "prod"
| where Service == "orders-api"
| where Operation == "GET /orders/{id}"
| summarize
    Samples = count(),
    P95Ms = percentile(DurationMs, 95),
    Http5xx = countif(StatusCode >= 500 and StatusCode < 600)
  by bin(Timestamp, 5m)
| extend
    ErrorRatePct = round(100.0 * Http5xx / Samples, 3),
    LatencySloMiss = P95Ms >= 500,
    AvailabilitySloMiss = ErrorRatePct > 0.1
| where Samples >= 100
| order by Timestamp asc
~~~

**Đây chỉ là ví dụ SLO**, không phải SLA của Azure Data Explorer hay Orders API. Cần xác định **request nào eligible**, status errors nào do client, maintenance period và mức sampling. Filter `Samples >= 100` để tránh kết luận từ bucket quá nhỏ nhưng có thể bỏ qua một outage không còn requests; kết hợp thêm health/availability probes.

### 9.5. Distinct users/clients và cardinality

Giả sử ứng dụng có `ClientId` đã được chuẩn hóa và phê duyệt lưu:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| summarize
    Requests=count(),
    UniqueClients=dcount(ClientId)
  by Service
~~~

**Chỉ chạy nếu bảng có `ClientId`.** `dcount()` là **approximate distinct count**, phù hợp thống kê quy mô lớn; không dùng nó để xác nhận số giao dịch duy nhất cần bảo đảm tuyệt đối. Với tập dữ liệu nhỏ muốn exact distinct, có thể dùng `count_distinct()` theo giới hạn/chi phí; với dữ liệu cá nhân, ưu tiên ID giả danh/hash do chính sách cho phép.

## 10. Điều tra incident: dịch vụ nào gây tăng HTTP 5xx?

Ta muốn trả lời “lỗi bắt đầu từ dịch vụ/phiên bản nào?” thay vì chỉ báo “backend 500”.

### 10.1. Top failing operations

~~~kusto
let WindowStart = datetime(2026-11-20T09:00:00Z);
let WindowEnd = datetime(2026-11-20T09:30:00Z);
ApiTelemetry
| where Timestamp >= WindowStart and Timestamp < WindowEnd
| where Environment == "prod"
| summarize
    TotalRequests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs, 95)
  by Service, Operation, Region
| extend ErrorRatePct=round(100.0 * todouble(Http5xx) / TotalRequests, 2)
| where TotalRequests >= 50
| top 15 by Http5xx desc
~~~

**Không chỉ sắp theo error rate**: một operation có 1 lỗi/1 request sẽ có 100%, nhưng ảnh hưởng người dùng thấp hơn operation có 5.000 lỗi/100.000 requests. Cần xem **volume, rate, business criticality và baseline**.

### 10.2. So sánh trước và sau deployment

Trường `Deployment` nằm trong `Properties`:

~~~kusto
ApiTelemetry
| where Timestamp > ago(6h)
| where Environment == "prod"
| extend Deployment=tostring(Properties.deployment)
| where isnotempty(Deployment)
| summarize
    Requests=count(),
    Error5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs, 95)
  by Service, Deployment, Region
| extend ErrorPct=round(100.0 * Error5xx / Requests, 2)
| order by Service asc, Deployment asc
~~~

**Rủi ro khi diễn giải:** có thể v41 và v42 được triển khai vào các regions/tenants khác nhau; error rate khác nhau không tự chứng minh **causality**. So sánh thêm timeframe, traffic mix, service region, dependencies và deployment event. Dùng canary/control cohort nếu có thể.

### 10.3. Tìm error categories

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Service == "orders-api"
| where StatusCode >= 500 and StatusCode < 600
| extend ErrorCategory=tostring(Properties.errorCategory)
| summarize
    Errors=count(),
    LastSeen=max(Timestamp)
  by ErrorCategory, Region
| top 20 by Errors desc
~~~

Để tránh một số lỗi không khai báo category biến mất vào giá trị trống, có thể:

~~~kusto
| extend ErrorCategory = iff(
    isempty(tostring(Properties.errorCategory)),
    "Unclassified",
    tostring(Properties.errorCategory))
~~~

Khối `extend` riêng này là **đoạn chèn vào pipeline**, không phải query hoàn chỉnh nếu chạy độc lập.

### 10.4. Phân tích retry sau sự cố

Nếu log schema có `RequestId`, `Attempt` và `Success`:

~~~kusto
// Sơ đồ: chỉ dùng sau khi đã ingest đúng 3 cột sau.
ApiTelemetry
| where Timestamp > ago(1h)
| summarize
    Attempts=count(),
    AnySuccess=countif(Success == true),
    LastSeen=max(Timestamp)
  by RequestId
| where Attempts > 1
| top 20 by Attempts desc
~~~

Thấy cùng ID nhiều lần chưa hẳn lỗi: có thể đó là **traces của nhiều spans** hoặc retries hợp lệ. Phải hiểu event contract: một row là request, một span hay một log line? Đừng dedup chỉ theo `TraceId` nếu mỗi trace cần nhiều events để điều tra.

### 10.5. Vẽ tần suất HTTP 5xx và 429 cùng lúc

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Service == "orders-api" and Environment == "prod"
| summarize
    Http5xx=countif(StatusCode between (500 .. 599)),
    Http429=countif(StatusCode == 429)
  by bin(Timestamp, 1m)
| order by Timestamp asc
| render timechart
~~~

Nếu 429 tăng trước 5xx, có thể ứng dụng đã đạt rate limit rồi downstream bị retry storm; nhưng kết luận cần đối chiếu rate-limit policy, load và logs. **Correlation không tự chứng minh nguyên nhân.**

## 11. KQL `dynamic`: JSON, arrays và fields không cố định

Log thường có attributes thay đổi tùy service, chẳng hạn:

~~~json
{
  "deployment": "v42",
  "dependency": "sql-orders",
  "tags": ["checkout", "priority"],
  "error": {
    "category": "SqlTimeout",
    "code": "DB_CONN_TIMEOUT"
  }
}
~~~

ADX có kiểu `dynamic` để lưu JSON-like values. Hãy **lấy values ra kiểu rõ ràng** trước khi so sánh/aggregate.

### 11.1. Truy cập field động

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| extend
    Deployment = tostring(Properties.deployment),
    Dependency = tostring(Properties.dependency),
    ErrorCategory = tostring(Properties.error.category)
| project Timestamp, Service, Deployment, Dependency, ErrorCategory, TraceId
~~~

Một bản ghi không có `Properties.error.category` sẽ tạo giá trị trống/null khi convert; không giả định mọi event đều có tất cả nested attributes. **Đừng đặt mọi field quan trọng vào `dynamic` chỉ để khỏi quản lý schema**.

### 11.2. Khi JSON đang là string

Nếu nguồn ingest raw JSON vào cột `RawPayload:string`:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| extend Payload = parse_json(RawPayload)
| extend Deployment = tostring(Payload.deployment)
| summarize Events=count() by Deployment
~~~

**Chỉ chạy với schema có `RawPayload`.** Nếu `Properties` đã là `dynamic`, có thể truy cập `Properties.deployment` trực tiếp; gọi `parse_json(Properties)` thường không cần. Với JSON lồng bên trong string field phải parse thêm đúng tầng.

### 11.3. `mv-expand` làm tăng số rows

Để minh họa bằng dữ liệu tự tạo:

~~~kusto
let Demo = datatable(
    TraceId:string, Tags:dynamic)
[
    "tr-001", dynamic(["checkout","priority"]),
    "tr-002", dynamic(["catalog"]),
    "tr-003", dynamic(["checkout","retry","sql"])
];
Demo
| mv-expand Tag=Tags to typeof(string)
| summarize Traces=dcount(TraceId) by Tag
| order by Traces desc
~~~

`mv-expand` biến mỗi phần tử mảng thành một row; nếu một event có 1.000 tags và 1 triệu events, kết quả trung gian có thể rất lớn. **Filter theo thời gian/service trước khi expand**, giới hạn cardinality hoặc tính toán khác khi phù hợp.

### 11.4. `bag_unpack` và schema linh hoạt

ADX có plugin `bag_unpack` giúp mở các thuộc tính object từ `dynamic` thành columns:

~~~kusto
// Chỉ minh họa; Properties phải chứa object keys phù hợp.
ApiTelemetry
| where Timestamp > ago(10m)
| evaluate bag_unpack(Properties)
| take 20
~~~

Mở tất cả attributes trên dữ liệu nhiều schema có thể tạo rất nhiều columns/chi phí. Với truy vấn production, ưu tiên **chỉ extract những fields cần dùng** hoặc khai báo schema output/kiểm soát names khi dùng plugin.

### 11.5. JSON không thay quyền dữ liệu

Nếu `Properties` vô tình chứa `email`, `token` hoặc nội dung request body, KQL có thể đọc được chúng trong phạm vi quyền của user. **Không nhập dữ liệu nhạy cảm không cần thiết** chỉ vì `dynamic` cho phép schema linh hoạt. Áp dụng field-level redaction ở producer/ingestion và role/retention phù hợp.

## 12. `join`, `lookup` và truy dấu một request qua nhiều dịch vụ

Một HTTP request có thể gây nhiều dependency calls: Azure SQL query, Redis cache lookup, Service Bus publish và downstream HTTP request. Nếu chỉ xem bảng request tổng, bạn có thể thấy API chậm nhưng không biết **dependency nào** gây chậm.

### 12.1. Chuẩn hóa distributed trace

Khi ứng dụng dùng OpenTelemetry/W3C Trace Context, records có thể mang:

~~~text
TraceId:       trace-cc42
Request span:  span-api-001
Child span 1:  span-sql-001
Child span 2:  span-redis-001
Deployment:    v42
~~~

`TraceId` liên kết **cùng trace**, `SpanId` và `ParentSpanId` (nếu có) mô tả quan hệ cha–con. Một trace có **nhiều rows** là bình thường; **không** dedup toàn bộ logs theo `TraceId` rồi coi còn một event là đủ.

### 12.2. Giả định bảng dependency

Để minh họa, giả sử có bảng `DependencyTelemetry`:

| Cột | Type | Nội dung |
|---|---|---|
| `Timestamp` | datetime | Event time |
| `TraceId` | string | Trace ID từ request |
| `Target` | string | `sql-orders`, `redis-catalog`, `payments-api` |
| `DurationMs` | real | Latency dependency |
| `Success` | bool | Dependency call có đạt điều kiện success |
| `Region` | string | Region |

**Đây là schema giả định**, không phải bảng tự có trong mọi ADX cluster. Hãy tạo ingest mapping tương ứng hoặc chuyển query theo bảng có thật.

### 12.3. Join request với dependency

~~~kusto
let WindowStart = ago(1h);
let Requests =
    ApiTelemetry
    | where Timestamp > WindowStart
    | where Service == "orders-api"
    | project
        TraceId,
        RequestTime = Timestamp,
        RequestStatus = StatusCode,
        RequestMs = DurationMs,
        Operation;
let DepPerTrace =
    DependencyTelemetry
    | where Timestamp > WindowStart
    | summarize
        DependencyCalls = count(),
        FailedDependencies = countif(Success == false),
        SlowestDependencyMs = max(DurationMs),
        DependencyTargets = make_set(Target, 20)
      by TraceId;
Requests
| join kind=leftouter (DepPerTrace) on TraceId
| project RequestTime, TraceId, Operation, RequestStatus,
          RequestMs, DependencyCalls, FailedDependencies,
          SlowestDependencyMs, DependencyTargets
| top 20 by RequestMs desc
~~~

**Tại sao aggregate dependency trước `join`?** Một request có thể gọi 20 dependencies; join trực tiếp tạo **20 rows cho một request**. Nếu sau đó tính `count()`, bạn có thể đếm request 20 lần. Tổng hợp theo `TraceId` trước giúp giữ một row per trace **nếu bảng request thực sự có một request root event/trace**.

Trong distributed tracing phức tạp, có thể có **nhiều root/request spans trong cùng trace**. Khi đó cần xác định khóa phù hợp hơn, ví dụ `TraceId + SpanId`, hoặc chọn request root events trước khi join. Không giả định `TraceId` luôn unique cho từng HTTP request.

### 12.4. `lookup` cho bảng dimension nhỏ

Giả sử cần gắn tên team từ bảng dimension nhỏ:

~~~kusto
let Teams = datatable(Service:string, OwnerTeam:string)
[
  "orders-api", "Commerce",
  "catalog-api", "Catalog",
  "payments-api", "Payments"
];
ApiTelemetry
| where Timestamp > ago(1h)
| summarize Errors=countif(StatusCode >= 500) by Service
| lookup kind=leftouter Teams on Service
| project Service, OwnerTeam, Errors
~~~

`lookup` thường phù hợp khi một phía là **dimension table nhỏ**, không phải hàng tỷ records. Nếu table team metadata có trùng `Service`, lookup có thể nhân rows. Kiểm soát uniqueness và test. Với rất nhiều data ở cả hai phía, xem `join` strategy/query plan phù hợp.

### 12.5. Phân tích call graph từ logs

Nếu schema có `ParentSpanId` và `SpanId`, bạn có thể tìm quan hệ giữa spans cùng trace:

~~~kusto
// Chỉ dùng khi bảng có đầy đủ ParentSpanId / SpanId.
let TraceEvents =
    ApiTelemetry
    | where Timestamp > ago(1d)
    | where TraceId == "trace-cc42"
    | project TraceId, SpanId, ParentSpanId, Service, Timestamp, DurationMs;
TraceEvents
| order by Timestamp asc
~~~

Muốn hiển thị một **trace tree**, cần xử lý parent-child graph hoặc sử dụng công cụ distributed tracing chuyên dụng. `order by Timestamp` cho biết thứ tự thời điểm nhưng **không tự vẽ topology nhân quả**.

### 12.6. `union` qua nhiều nguồn

~~~kusto
union withsource=SourceTable ApiTelemetry, DependencyTelemetry
| where Timestamp > ago(30m)
| project SourceTable, Timestamp, TraceId, Service, Target
| take 100
~~~

`union` giữa hai bảng khác schema thường tạo columns bị null ở những rows không có cột. Nếu `Service` hoặc `Target` không có ở một bảng, nhận null là bình thường. Chỉ nên union khi muốn **hợp nhất timeline**, không dùng nó để thay `join` liên kết theo khóa.

## 13. Time series, spikes và phát hiện bất thường với KQL

Khi monitor requests/giây, bạn cần một chuỗi thời gian có các buckets đều nhau. `make-series` có thể tạo **mảng số liệu theo time bins**, cho phép áp dụng các hàm xử lý series của Kusto.

### 13.1. Tạo time series đều đặn

~~~kusto
let StartUtc = ago(24h);
let EndUtc = now();
ApiTelemetry
| where Timestamp >= StartUtc and Timestamp < EndUtc
| where Environment == "prod"
| make-series Requests=count() default=0
    on Timestamp from StartUtc to EndUtc step 5m
    by Service
| render timechart
~~~

**Điều kiện dùng `default=0`:** “không có event trong bucket” không nhất thiết có nghĩa **không có HTTP traffic**. Nó có thể là outage của ingestion, mất kết nối Event Hubs, sampling hoặc pipeline delay. Kết hợp với ingestion health và synthetic probes trước khi diễn giải zero là service down.

### 13.2. Phát hiện anomalies

KQL cung cấp các hàm cho series, trong đó có `series_decompose_anomalies()`:

~~~kusto
let StartUtc = ago(7d);
let EndUtc = now();
ApiTelemetry
| where Timestamp >= StartUtc and Timestamp < EndUtc
| where Environment == "prod"
| where Service == "orders-api"
| make-series Requests=count() default=0
    on Timestamp from StartUtc to EndUtc step 10m
| extend (AnomalyFlags, Scores, Baseline) =
    series_decompose_anomalies(Requests, 1.5)
| mv-expand
    Timestamp to typeof(datetime),
    Requests to typeof(long),
    AnomalyFlags to typeof(long),
    Scores to typeof(real),
    Baseline to typeof(real)
| where AnomalyFlags != 0
| project Timestamp, Requests, Baseline, Scores, AnomalyFlags
| order by Timestamp asc
~~~

Hàm phát hiện outliers trên series so với **baseline thống kê**, không phải lời khẳng định bảo mật hay business incident. Với data có chu kỳ ngày/tuần, cần đủ lịch sử và hiểu seasonal behavior. Một ngày Black Friday có thể là spike hợp lệ; query không tự biết lịch marketing.

### 13.3. Phân biệt spike traffic và spike lỗi

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Environment == "prod"
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs,95)
  by bin(Timestamp, 5m), Service
| extend ErrorPct=round(100.0 * Http5xx / Requests,2)
| order by Timestamp asc
~~~

Nếu traffic tăng 5× nhưng error rate vẫn 0.1% và p95 ổn định, có thể hệ thống chịu tải tốt. Nếu requests không đổi mà 5xx tăng mạnh, có khả năng dependency hoặc release lỗi. Nếu requests giảm về 0, hãy xác nhận **ingestion health và user-facing availability** trước khi nói sản phẩm không có người dùng.

### 13.4. Baseline và so sánh ngày trước

Để so sánh cùng giờ hôm qua, có thể dùng `ago(1d)` và cùng bucket:

~~~kusto
let NowUtc = now();
let Today =
    ApiTelemetry
    | where Timestamp >= NowUtc - 1h and Timestamp < NowUtc
    | summarize RequestsToday=count() by Service;
let Yesterday =
    ApiTelemetry
    | where Timestamp >= NowUtc - 25h and Timestamp < NowUtc - 24h
    | summarize RequestsYesterday=count() by Service
    | project PreviousService=Service, RequestsYesterday;
Today
| join kind=fullouter (Yesterday)
    on $left.Service == $right.PreviousService
| extend
    ServiceName=coalesce(Service, PreviousService),
    TodayCount=coalesce(RequestsToday, 0),
    YesterdayCount=coalesce(RequestsYesterday, 0)
| project ServiceName, TodayCount, YesterdayCount
~~~

**Chú ý:** ví dụ đặt tên khóa hai phía là `Service` và `PreviousService` để tránh phụ thuộc vào cách query engine tự đổi tên cột trùng; đây là phép so hai khoảng 1 giờ. Nếu muốn so **theo từng phút cùng ngày**, cần tính offset/time-bin alignment rõ hơn. Ngày lễ, deployment và time zones có thể làm baseline không tương đồng.

## 14. KQL `let`, `materialize()`, stored functions và materialized views

Khi query được dùng lặp lại trong dashboard, viết cùng 20 dòng filter ở mọi nơi dễ gây sai lệch. ADX hỗ trợ các cơ chế tái sử dụng logic và tính trước kết quả, nhưng chúng phục vụ **mục đích khác nhau**.

### 14.1. `let` — đặt tên trong một query

~~~kusto
let ProductionErrors =
    ApiTelemetry
    | where Timestamp > ago(1h)
    | where Environment == "prod"
    | where StatusCode >= 500 and StatusCode < 600;
ProductionErrors
| summarize Errors=count() by Service
| order by Errors desc
~~~

`let` có phạm vi query hiện tại; query khác sẽ cần khai báo lại. Nên dùng để làm code rõ ràng, không phải để tự tạo materialized data.

### 14.2. `materialize()` — cache subquery trong cùng query

Nếu một subquery được dùng hai lần trong **cùng request**, có thể cân nhắc:

~~~kusto
let Recent = materialize(
    ApiTelemetry
    | where Timestamp > ago(1h) and Environment == "prod"
    | project Service, StatusCode, DurationMs
);
let Totals =
    Recent
    | summarize Requests=count(), P95Ms=percentile(DurationMs,95)
      by Service;
let Failures =
    Recent
    | where StatusCode >= 500 and StatusCode < 600
    | summarize Http5xx=count() by Service;
Totals
| join kind=leftouter (Failures) on Service
| extend Http5xx=coalesce(Http5xx, 0)
| project Service, Requests, Http5xx, P95Ms
~~~

`materialize()` có **bộ nhớ cache hữu hạn** và có thể tăng memory use khi trung gian quá lớn. Đặt `where`, `project` sớm **bên trong** subquery; thử benchmark trước/sau. Đừng bọc tất cả tables bằng `materialize()` như một “tối ưu hóa mặc định”.

### 14.3. Stored functions — logic có tên ở database

Một Kusto function có thể đưa query dùng chung vào database:

~~~kusto
// Management command, chỉ dành cho DBA/Kusto admin ở database lab.
.create-or-alter function with (folder = "Observability",
    docstring = "HTTP 5xx by service in a lookback window")
ErrorsByService(Lookback:timespan) {
    ApiTelemetry
    | where Timestamp > ago(Lookback)
    | where Environment == "prod"
    | summarize Http5xx=countif(StatusCode >= 500 and StatusCode < 600)
      by Service
}
~~~

Sau khi được triển khai với quyền phù hợp:

~~~kusto
ErrorsByService(1h)
| order by Http5xx desc
~~~

**Phải quản lý version của function** trong source control/IaC, document contract và test regression. Function không tự chạy ingest hoặc tự tạo dashboard. Một người có quyền `Viewer` database không nhất thiết có quyền tạo/sửa function.

### 14.4. Materialized view — tính sẵn aggregate

Với dashboard luôn truy vấn:

~~~kusto
ApiTelemetry
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600)
  by Service, bin(Timestamp, 5m)
~~~

một **materialized view** (khi thỏa yêu cầu engine/aggregate) có thể lưu kết quả tổng hợp được cập nhật từ source table, giảm chi phí mỗi lần đọc. Nhưng:

- Không phải mọi KQL query/operator đều được hỗ trợ trong materialized view definition.
- Có **chi phí ingestion/maintenance**, backfill và tài nguyên lưu trữ riêng.
- Độ mới của kết quả phụ thuộc pipeline/materialization và cách query.
- Bản ghi đến trễ và updates/dedup có thể ảnh hưởng semantics.
- Cần monitor materialization health, source retention và schema changes.

**Không tạo materialized view cho mọi dashboard**: nếu query chỉ chạy một lần/ngày, chi phí duy trì view liên tục có thể vượt lợi ích. Nếu muốn query recent data lẫn phần chưa materialize, phải kiểm tra semantics của việc query view theo Kusto.

### 14.5. Update policies không phải ETL transaction engine

ADX có **update policies** để sinh dữ liệu/bảng dẫn xuất khi ingest vào source. Hữu ích khi muốn chuẩn hóa/biến đổi sớm, nhưng cần xét:

- Ingestion failures khi mapping/transformation lỗi.
- Duplicates/idempotency.
- CPU/latency và tính nhất quán giữa source/target theo chính sách.
- Schema evolution và quyền tạo/sửa policy.
- Monitoring khi pipeline nạp hàng triệu events.

Không dùng update policy như thay thế database transaction cross-table đảm bảo đúng/sai của đơn hàng.

## 15. Tối ưu KQL trên dữ liệu lớn

Trên một bảng vài tỷ rows, sự khác biệt giữa query tốt và query kém có thể là **vài giây so với nhiều phút**, hoặc từ tiêu thụ tài nguyên nhỏ đến ảnh hưởng dashboard của những nhóm khác. ADX là hệ phân tích mạnh, nhưng không có nghĩa mọi query là miễn phí.

### 15.1. Quy tắc 1: lọc thời gian càng sớm càng tốt

**Tránh:**

~~~kusto
ApiTelemetry
| summarize Total=count() by Service
~~~

Query này có thể cần đọc dữ liệu từ **toàn bộ thời hạn retention**.

**Ưu tiên:**

~~~kusto
ApiTelemetry
| where Timestamp >= ago(1h)
| where Environment == "prod"
| summarize Total=count() by Service
~~~

Nếu cần all-time totals, hãy thiết kế materialized view/aggregate theo yêu cầu, không tự động scan dữ liệu nhiều năm mỗi 10 giây.

### 15.2. Quy tắc 2: giữ số cột cần thiết

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| where Service == "orders-api"
| project Timestamp, StatusCode, DurationMs, TraceId
| top 100 by DurationMs desc
~~~

`project` loại các cột lớn như `Properties:dynamic` khi không cần; query/response nhỏ hơn và giảm data movement. Với bảng column-oriented, engine có thể tối ưu column access, nhưng bạn vẫn nên giới hạn output.

### 15.3. Quy tắc 3: hạn chế `parse_json`, regex và substring scan vô ích

**Kém hiệu quả với field được query thường xuyên:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| extend Parsed = parse_json(RawPayload)
| where tostring(Parsed.service) == "orders-api"
~~~

Nếu `service` luôn có, ingest nó vào cột `Service:string` và query:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| where Service == "orders-api"
~~~

**Chỉ áp query đầu nếu bảng có RawPayload.** Việc chuyển field sang typed column đòi hỏi ingestion mapping/schema management, nhưng có thể tiết kiệm rất nhiều CPU trên query lặp lại.

### 15.4. Quy tắc 4: aggregate trước khi join

Nếu bảng dependency có 500 triệu rows, bảng request có 100 triệu rows:

~~~text
Naive join raw request × raw dependencies
    → Có thể phình số rows rất lớn.

Filter both sides to exact time window
    → Aggregate dependencies by TraceId
    → Join compact results
    → Project only needed fields
~~~

`join` strategy (`broadcast`, `shuffle`, lookup) phụ thuộc kích thước và phân bố dữ liệu. **Không thêm hint tùy tiện** khi chưa đo query plan; có thể làm query chậm hơn.

### 15.5. Quy tắc 5: hạn chế cardinality của `summarize`

~~~kusto
// Cẩn trọng: một result row cho mỗi TraceId có thể rất lớn.
ApiTelemetry
| where Timestamp > ago(1d)
| summarize Requests=count() by TraceId
~~~

Nếu cần dashboard, group theo `Service`, `Region`, `Operation` và time bucket. Chỉ drill down `TraceId` cho một tập sự kiện nhỏ khi điều tra. Nếu muốn tổng số trace IDs, dùng `dcount(TraceId)` (approximate).

### 15.6. Query output, sampling và giới hạn tài nguyên

Một query trả toàn bộ raw logs trong 30 ngày có thể vượt giới hạn kết quả và gây memory pressure ở client. Thực hành tốt:

- Trả **aggregate** trước rồi drill down chi tiết.
- Dùng `top N by ...` khi muốn ranking xác định.
- Tránh `take N` nếu đang cần sự bảo đảm “N bản ghi gần nhất” mà không có sort.
- Dùng sampling thích hợp để khám phá, nhưng **không** lấy sample ngẫu nhiên làm bằng chứng chính xác về billing/security.
- Theo dõi query diagnostics/resource consumption, CPU/memory/concurrency và throttling.
- Kiểm soát concurrency/deadlines ở dashboard/SDK, không cho hàng nghìn queries nặng chạy liên tục.

### 15.7. Retention và hot caching là hai chính sách

**Retention** quyết định dữ liệu được giữ bao lâu; **caching policy** quyết định bao nhiêu phần dữ liệu được lưu trong cache nhanh để truy vấn hiệu quả. Ví dụ:

~~~text
Soft-delete retention: 90 ngày
Hot cache period:      14 ngày

Query last 2h  → thường có lợi từ hot cache
Query last 60d → phần cũ có thể phải truy cập tầng lưu trữ chậm hơn
~~~

Đây là **mô hình minh họa**; query performance phụ thuộc cluster/size/ingest/partition. Đừng đồng nhất “không còn trong hot cache” với “dữ liệu đã bị xóa”. Retention phục vụ nghĩa vụ xóa dữ liệu, còn caching policy là tradeoff performance/capacity.

Các lệnh **chỉ đọc** trên table khi có quyền:

~~~kusto
.show table ApiTelemetry policy retention

.show table ApiTelemetry policy caching
~~~

Những lệnh trên là **Kusto management commands**, không phải KQL SELECT. Policy có thể kế thừa ở database level; xem effective policy tại scope sử dụng. Không tự `.alter` retention của production chỉ để query nhanh hơn.

### 15.8. KQL performance checklist

| Câu hỏi | Nếu câu trả lời “chưa” |
|---|---|
| Có lọc thời gian đầu query? | Thêm `where Timestamp ...` |
| Có lọc service/env/operation sớm? | Giảm dữ liệu trước aggregate |
| Có `project` ra đúng cột? | Bỏ dynamic payload không dùng |
| Có group theo high-cardinality ID không? | Tính dcount hoặc drill-down có giới hạn |
| Join hai bên có filter và cardinality đúng? | Aggregate trước, kiểm tra duplicate keys |
| `mv-expand` có làm nở dữ liệu? | Filter và giới hạn expansion |
| Query chạy lặp 1.000×/giờ? | Cân nhắc function/materialized view/caching |
| Query có cần exactness tuyệt đối? | Không dùng approximate dcount/percentile thay ledger |

## 16. Bảo mật Azure Data Explorer và quyền KQL

ADX có thể giữ nhật ký chứa đường dẫn nội bộ, application IDs, identifiers và security events. Chỉ cần KQL đủ mạnh để tìm mọi sự kiện cũng đồng nghĩa phải **hạn chế ai được query cái gì**.

### 16.1. Các lớp quyền

| Lớp | Ví dụ quyền | Không đồng nghĩa |
|---|---|---|
| **Azure control plane RBAC** | Contributor/Reader trên cluster ARM resource | Tự động đọc mọi bảng dữ liệu Kusto |
| **ADX database data-plane roles** | Viewer, User, Ingestor, Admin theo mô hình Kusto | Tự sửa VNet/Private Endpoint của cluster |
| **Table/function security** | Chính sách truy cập hẹp, RLS/restricted view khi hỗ trợ | Tự bảo vệ tất cả dữ liệu đã xuất ra CSV |
| **Producer/ingestion identity** | Managed identity có quyền đọc Event Hubs và ingest table | Tự được đọc mọi dữ liệu analytics |
| **Consumer query identity** | Entra principal được cấp quyền query | Tự có quyền export/copy PII ngoài tổ chức |

Nguyên tắc **least privilege**: dashboard reader cần đọc bảng/aggregate được phép, ingestion connector chỉ cần quyền ingest, platform admin mới được thay retention, policies và quyền truy cập.

### 16.2. Authentication bằng Microsoft Entra ID

Client Kusto thường xác thực bằng **Microsoft Entra** qua SDK, Azure CLI login (lab) hoặc managed identity/service principal (runtime). Sau khi nhận token hợp lệ, principal còn cần **quyền database/table phù hợp**.

~~~text
Developer / app
    ↓ Acquire Entra token for ADX cluster
ADX query endpoint
    ↓ Authorize database/table/function access
KQL query execution
    ↓ Return only permitted results
~~~

**Azure Contributor trên resource group không tự là Kusto database Viewer.** Nếu Kusto trả access denied, xác minh tenant, query endpoint, database, data-plane role assignments và managed identity; đừng tăng quyền lên Owner subscription để thử.

### 16.3. Row-level security (RLS) và dữ liệu đa tenant

Giả sử bảng telemetry chứa `TenantId`. Một dashboard phục vụ đối tác A không nên được phép thấy events của tenant B. Có thể:

- Ingest dữ liệu vào **database/table tách biệt** theo data classification khi phù hợp.
- Sử dụng **row-level security policy**/restricted views hoặc tính năng bảo vệ dữ liệu tương ứng theo hỗ trợ ADX.
- Chỉ expose **stored functions/views** đã được kiểm soát với đúng permissions.
- Tách application credentials và kiểm soát export/query access.

**Cực kỳ quan trọng:** query có `where TenantId == "A"` trong một dashboard **không phải security boundary** nếu user được quyền chạy KQL tùy ý trên bảng gốc. Phải thực thi quyền ở **data plane/database/row security**, không chỉ dựa vào UI filter.

### 16.4. Không ingest bí mật

Đối với logs/telemetry:

- Không lưu `Authorization: Bearer ...`, API keys, connection strings, passwords, cookies hoặc session tokens.
- Redact PII như email/điện thoại/address khi không có nhu cầu hợp lệ.
- Không lưu nội dung thẻ thanh toán hoặc raw request bodies không cần thiết.
- Dùng correlation/route templates thay giá trị chứa user ID khi có thể.
- Phân loại audit/security logs riêng khỏi debug logs, áp retention theo chính sách.
- Đánh giá ingest/export cross-region, customer-managed key/encryption theo yêu cầu dữ liệu.

**Retention 30 ngày không xóa dữ liệu đã được xuất ra laptop, Power BI hoặc lưu bản sao ở Blob.** Chính sách xóa và incident response phải tính cả exports/downstream copies.

### 16.5. Private networking

ADX hỗ trợ các mô hình network exposure/private endpoints theo loại deployment và tính năng. Một kiến trúc private có thể:

~~~mermaid
flowchart LR
    PROD[Producers / Event Hubs] --> ING[ADX ingestion path]
    CLIENT[SRE / Dashboard in approved network] --> DNS[Private DNS / resolver]
    DNS --> PE[ADX Private Endpoint]
    PE --> QUERY[ADX query endpoint]
    ING --> DATA[(Kusto tables)]
    QUERY --> DATA
    ID[Microsoft Entra ID] -. Authentication .-> QUERY
~~~

Đường **ingestion** và **query** có thể cần endpoint/DNS/identity riêng theo cấu hình. Tạo Private Endpoint inbound cho ADX **không tự cấp đường ADX outbound tới Event Hubs/Storage/Key Vault** trong mọi topo. Kiểm tra managed private endpoints/egress requirements, VNet, Private DNS và routing theo service.

Hãy luôn:

1. Xác định inbound data sources, query clients và outbound dependencies.
2. Dùng FQDN chính thức từ resource, xác minh DNS trả private IP từ runtime.
3. Kiểm tra cổng HTTPS/TLS và certificate hostname.
4. Cấp identity/data permissions riêng cho ingest và query.
5. Nếu policy yêu cầu private-only, **tắt public exposure sau khi tất cả clients đã test**.
6. Giám sát failed ingestions/query logins sau network changes.

**Đừng copy Private DNS zone của Azure SQL hoặc Storage sang ADX.** Private DNS names/zone group khác nhau theo dịch vụ và region; đọc resource-provided configuration khi triển khai.

### 16.6. Governance cho queries tốn kém

Người dùng có quyền query một database lớn có thể vô tình tạo **query cost/performance impact** cho người khác. Thiết kế workload groups, query limits, concurrency và budgets phù hợp theo tính năng ADX. Không mở unrestricted access cho đối tác hoặc dashboard không kiểm soát; theo dõi resource consumption và audit.

## 17. Monitoring ADX: tách ingestion health khỏi query health

Một hệ thống có thể trả kết quả KQL rất nhanh **nhưng dữ liệu đã ngừng được nạp 2 giờ**. Ngược lại ingestion khỏe nhưng queries chậm do cluster CPU hoặc query design. Đây là hai mặt reliability khác nhau.

### 17.1. Ingestion observability

| KPI | Câu hỏi trả lời |
|---|---|
| **Ingestion volume/events per second** | Có nạp đủ theo expected producer traffic? |
| **Ingestion latency** | Event xuất hiện trong ADX sau bao lâu? |
| **Ingestion failures** | JSON mapping, schema, permissions hoặc throttling lỗi? |
| **Event Hubs lag/backlog** | Connector có theo kịp partitions/consumer group không? |
| **Last event time per source** | Source có ngừng phát hay pipeline bị kẹt? |
| **Duplicates/late arrivals** | Replay/retry có nhân rows hoặc đến trễ? |
| **Storage/retention growth** | Khối dữ liệu tăng vượt kế hoạch? |

Ví dụ KQL để phát hiện source im lặng (chỉ quan sát trong bảng đã nạp):

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| summarize LastEventUtc=max(Timestamp), Events=count() by Service
| extend MinutesSinceLastEvent=datetime_diff("minute", now(), LastEventUtc)
| order by MinutesSinceLastEvent desc
~~~

**Nếu bảng không có dữ liệu nào của service trong cả ngày, service sẽ không hiện trong kết quả.** Để alert missing service, cần **inventory expected services** và `join kind=leftouter` với results, hoặc synthetic probes độc lập. Ngoài ra, event time có thể do clock source sai; cần đo cả ingestion/pipeline metrics.

### 17.2. Query observability

| KPI | Tác động |
|---|---|
| Query duration p50/p95 | Trải nghiệm analyst/dashboard |
| Query CPU/memory/resource usage | Cluster sizing hoặc query anti-pattern |
| Query failures/timeouts | Syntax, permissions, capacity, result limits |
| Concurrent queries | Workload contention |
| Data scanned/cache hit | Retention/hot cache và filter effectiveness |
| Throttling/admission control | Cần tối ưu workload hoặc compute scaling |

Kusto cung cấp thông tin query diagnostics và Azure Monitor metrics theo deployment. Không tự kết luận “cluster khỏe” chỉ từ CPU trung bình dưới 50%; một số concurrent heavy queries có thể bị throttle hoặc tràn memory mặc dù CPU trung bình thấp.

### 17.3. Kiểm tra ingestion failures

Trong môi trường có quyền quản trị phù hợp, Kusto có các management commands để xem ingestion operations/failures, ví dụ:

~~~kusto
// Read-only administrative diagnostics where permission allows.
.show ingestion failures
~~~

Đồng thời kiểm tra Azure Monitor metrics, Event Hubs diagnostic logs, connector health và producer logs. **Một failed ingestion record không tự cho biết bản ghi nào cần replay nếu bạn không giữ event ID/raw source.**

### 17.4. Bốn cảnh báo cần có ngay

1. **Ingestion lag vượt SLO**, ví dụ dữ liệu đến trễ hơn 5 phút liên tục.
2. **Ingestion failure rate tăng** theo database/table/source.
3. **Query p95 hoặc query failures tăng** trên dashboard trọng yếu.
4. **Cluster utilization/storage growth vượt budget**, kèm owner và runbook.

Tùy workload có thể thêm cảnh báo missing source, security permission changes, retention policy changes, unhealthy materialized views, Event Hubs backlog và telemetry error rate. **Alert không có người nhận và hành động tiếp theo** thường chỉ tạo nhiễu.

## 18. Reliability, dữ liệu đến muộn, recovery và vòng đời dữ liệu

Một nền tảng log đáng tin không chỉ “ghi thành công ngày thường”. Khi Event Hubs gián đoạn, cluster quá tải hoặc mapping lỗi, đội vận hành vẫn phải biết **dữ liệu nào đã mất, dữ liệu nào bị trùng và từ đâu có thể replay**.

### 18.1. Phân biệt availability và freshness

Hai SLO khác nhau:

~~~text
Query availability:
  Analyst can execute a query and receive a result.

Telemetry freshness:
  Newly produced events become queryable within a target delay.
~~~

Một dashboard KQL có thể truy vấn bình thường nhưng chỉ chứa events đến **09:00** trong khi hiện tại là **09:30**. Vì vậy, đừng chỉ giám sát query success; đo **last observed event time** và ingestion lag.

### 18.2. Buffered ingestion và replay

Event Hubs hoặc raw files ở Blob/Data Lake có thể cung cấp **cửa sổ replay** theo retention đã cấu hình. Khi ADX connector dừng 20 phút:

1. Xác nhận Event Hubs/source data còn events cần nạp.
2. Xác định consumer group/checkpoint hiện tại và khoảng thời gian thiếu.
3. Sửa nguyên nhân như quyền, mapping, cluster saturation.
4. Cho connector catch up hoặc backfill theo cơ chế được hỗ trợ.
5. Kiểm tra duplicates/late arrivals, so sánh count/correlation với source.
6. Đo lại ingestion lag và cảnh báo trong giai đoạn khôi phục.

**Nếu Event Hubs đã hết retention và không còn raw archive, bạn có thể không khôi phục được mọi events.** “ADX tự có replicas” không tạo bản sao của dữ liệu **chưa ingest**.

### 18.3. Dedup và ordering trong analytics

Một số telemetry là **at-least-once**, nên:

- Có `EventId` hoặc source sequence ID khi cần khử trùng.
- Có `Timestamp` là event time và `ReceivedAtUtc` nếu cần đo lag chính xác.
- Không dùng `arg_max(Timestamp, *)` theo business key mà không hiểu semantics.
- Nếu event chỉnh sửa nhiều lần, chọn logic lấy version mới nhất rõ ràng.
- Không loại tất cả spans thuộc cùng `TraceId` vì sẽ mất call graph.

Đối với billing/financial reconciliation, nên dựa trên authoritative ledger và **exact IDs**. `dcount()` và telemetry sampling không phải bằng chứng kế toán.

### 18.4. Retention và chính sách xóa

Ví dụ một tổ chức có:

| Loại dữ liệu | Retention minh họa | Lý do |
|---|---:|---|
| Debug traces | 7–14 ngày | Thông tin chi tiết, volume/PII risk cao |
| API request metrics | 30–90 ngày | Phân tích SLO và release trends |
| Security audit | Theo policy/compliance | Cần điều tra, lưu giữ và bảo vệ cao hơn |
| Raw telemetry archive | Theo hợp đồng và lưu trữ | Backfill/reprocessing khi cần |

Những mốc này **không phải quy định pháp lý mặc định**; mỗi tổ chức phải quyết định theo hợp đồng, nơi xử lý dữ liệu và chính sách bảo mật. Retention policy ADX và retention Blob/Event Hubs/Log Analytics là **các chính sách độc lập**, cần quản trị cùng nhau.

### 18.5. Export, backup và disaster recovery

ADX cung cấp các cơ chế phục hồi/durability do dịch vụ quản lý và những khả năng export dữ liệu, nhưng **không xem query cache hoặc extent replicas là một bản backup ứng dụng có thể tùy ý restore tại mọi thời điểm**. Một chiến lược cần:

- Lưu raw source (Blob/Event Hubs retention) đủ lâu khi dữ liệu quan trọng.
- Có **export/backup** theo khả năng dịch vụ và mục tiêu khôi phục đã định.
- Document data mappings/functions/materialized views/roles trong IaC/source control.
- Đánh giá region failure và recovery topology theo SKU/service capabilities.
- Diễn tập **backfill trên một table/database lab**, so counts/checksums và query compatibility.
- Xác định RPO/RTO thực đo; không nói “không mất dữ liệu” khi chưa kiểm chứng.

**Xóa nhầm một bảng hoặc thay retention quá ngắn** có thể gây mất dữ liệu theo policy, không tự chữa chỉ bằng việc restart cluster. Những thao tác quản trị phá hủy cần approvals, backup/retention plan và audit.

### 18.6. Pipeline evolution

Khi producer thêm field `schemaVersion=2` hoặc đổi `DurationMs` từ number sang string, cần:

1. Test mapping ở staging.
2. Cập nhật table schema/ingestion transformation theo kế hoạch.
3. Giữ compatibility với versions cũ đủ lâu.
4. Kiểm tra lại stored functions/dashboards.
5. Giám sát mapping failures sau deploy.
6. Có kế hoạch backfill nếu records bị bỏ lỡ.

Với JSON `dynamic`, field mới có thể nạp được nhưng **tên/type không chuẩn** vẫn làm query sai. Schema evolution không chỉ là việc “nạp được JSON”.

## 19. FinOps: ADX query và ingestion tốn chi phí ở đâu?

Khi tính chi phí ADX, hãy nhìn **toàn pipeline**, không chỉ giá một cluster node. Một dashboard chạy query không giới hạn mỗi 5 giây có thể đòi nhiều compute hơn cả khối lượng ingest.

### 19.1. Các nhóm chi phí

| Thành phần | Nguồn phát sinh |
|---|---|
| **ADX compute** | Cluster SKU/cores/nodes, scale và availability |
| **Data storage** | Lượng dữ liệu ingest/retained, compression và policies |
| **Hot caching** | Dung lượng compute/SSD cache và hiệu năng query cần thiết |
| **Streaming/ingestion** | Dòng events, batching, connectors và phụ trợ |
| **Event Hubs** | Partitions/throughput/retention theo tier |
| **Blob/Data Lake archive** | Raw logs, export, replay, network transfer |
| **Networking** | Private Endpoints, DNS Resolver, VNet/Firewall/egress |
| **Monitoring** | Azure Monitor, Log Analytics, dashboards/alerts, retention |
| **Human/operations** | Incident, backfill, schema governance, DR testing |

Giá phụ thuộc **region, SKU, provisioning model và thời điểm**. Azure có thể có mô hình reserved/commitment cho một số loại capacity nhưng không nên mua trước khi benchmark nhu cầu ổn định.

### 19.2. Tính volume sơ bộ

Giả sử:

~~~text
Producers:              10 services
Events/service/second:   1,000
Average event size:      800 bytes (raw)
Seconds/day:             86,400
~~~

Raw input mỗi ngày:

\[
10 \times 1{,}000 \times 800 \times 86{,}400
=691{,}200{,}000{,}000\ \text{bytes}
\approx 691.2\ \text{GB/day}.
\]

Giữ 30 ngày có raw source volume lý thuyết khoảng:

\[
691.2 \times 30 = 20{,}736\ \text{GB}
\approx 20.7\ \text{TB}.
\]

**Đây không phải số GB billed storage của ADX**: nén cột, metadata, replicas, retention, ingestion errors và data shape làm lượng lưu trữ thực khác đáng kể. Nhưng bài toán cho thấy vì sao chỉ đổi retention từ 30 lên 365 ngày có thể thay đổi lớn chi phí và compliance risk.

### 19.3. Cách giảm chi phí mà không mất tín hiệu cần thiết

- **Structured logs thay verbose string logging** vô kiểm soát.
- **Sampling** debug traces khi business/security không yêu cầu 100% events; ghi rõ sampling fraction.
- Không ingest raw request/response bodies nhiều KB nếu đã có dimensions cần thiết.
- Chọn retention theo data class, hot cache window theo query nhu cầu.
- Giảm dashboard query frequency hoặc dùng materialized aggregates nếu hợp lý.
- Dùng `project`/`where` sớm để giảm scanned data/query resources.
- Phân tách ingest throughput spikes và query compute demand.
- Tag owner/team/environment/costCenter; so data volume và chi phí từng service.
- Kiểm tra budget alerts và capacity scaling theo SLO.

**Sampling không phù hợp nếu cần đếm chính xác mọi security action/financial event.** Có thể sample performance traces nhưng giữ audit events theo quy định. Không biến một dashboard đẹp thành “lời chứng” nếu 90% requests đã bị sampling.

### 19.4. Query value vs query cost

Ví dụ một dashboard có 20 charts, mỗi chart query 30 ngày raw logs mỗi 10 giây: 120 queries/phút trên một số tổ hợp dataset rất lớn. Có thể:

1. Chuyển charts operational sang **last 15m / 1h**.
2. Tạo aggregates 1m/5m qua supported materialized view nếu cần.
3. Refresh mỗi 30–60 giây với dữ liệu phù hợp.
4. Cho analyst drill-down raw logs chỉ khi phát hiện bất thường.
5. Dùng query diagnostics để benchmark trước/sau.

Đừng tạo materialized view cho mọi query chỉ để “tiết kiệm”: write-side maintenance và storage cũng có phí.

## 20. IaC, source control và quản trị thay đổi KQL

ADX có **hạ tầng** (cluster/database/network) và **logic dữ liệu** (tables/mappings/functions/policies/permissions). Cả hai cần versioned deployment, nhưng không nên để mọi developer tùy ý sửa production schema khi đang có ingestion traffic.

### 20.1. Phân định owner

| Nhóm | Sở hữu | Guardrail |
|---|---|---|
| **Cloud Platform** | Cluster SKU, VNet/private endpoint, availability, resource RBAC | Change approvals, IaC, cost governance |
| **Data Engineering** | Ingestion connectors, mappings, schema evolution, retention | Replay strategy, schema tests, source ownership |
| **SRE/Observability** | Dashboards, alerts, query SLO, incident runbooks | Query review, metric definition, on-call |
| **Security/Privacy** | Data classification, RLS, permissions, retention, export | Least privilege, audit, compliance |
| **Application team** | Structured events/trace IDs, schema contract, sampling | No secrets/PII, correlation consistency |

### 20.2. Repository tham khảo

~~~text
adx-observability/
├── infrastructure/
│   ├── main.bicep
│   └── environments/
│       ├── dev.params.json
│       └── prod.params.json
├── schemas/
│   ├── api-telemetry-table.kql
│   └── api-telemetry-mapping.kql
├── functions/
│   └── errors-by-service.kql
├── dashboards/
│   ├── requests-by-region.kql
│   └── p95-latency.kql
├── tests/
│   ├── schema-contract/
│   ├── query-golden-data/
│   └── security-negative-tests/
└── runbooks/
    ├── ingestion-backlog.md
    └── trace-query-slow.md
~~~

Đây là **cấu trúc minh họa**, không phải yêu cầu tạo files khác trong bài học này. Với hệ thống thật, có thể dùng Bicep/ARM/Terraform và pipeline deploy Kusto commands theo quyền/approval. **Không commit connection strings có secret, Entra tokens hoặc production export chứa PII**.

### 20.3. Pipeline CI/CD gợi ý

~~~mermaid
flowchart LR
    PR[Pull request] --> LINT[Review KQL + mapping/schema]
    LINT --> TEST[Run on synthetic golden dataset]
    TEST --> SEC[Security/PII + RBAC review]
    SEC --> PLAN[Check IaC/management command diff]
    PLAN --> DEPLOY[Deploy to staging ADX]
    DEPLOY --> INGEST[Ingest sample + verify counts/latency]
    INGEST --> APPROVE[Production approval]
    APPROVE --> PROD[Apply compatible changes]
    PROD --> WATCH[Monitor ingestion/query health + rollback]
~~~

### 20.4. Những thay đổi rủi ro cao

- Đổi ingestion mapping làm đổi type/timestamp.
- Tăng hoặc giảm retention ngoài chính sách.
- Xóa/recreate table hoặc database.
- Sửa update policy gây ingest failure.
- Tạo materialized view backfill khối lượng lớn.
- Thay database roles/RLS làm lộ data hoặc chặn dashboard.
- Đổi Event Hubs consumer group/checkpoint làm events trùng/thiếu.
- Chuyển public/private network khi CI/consumers chưa có đường mới.

**Không sửa trực tiếp production Portal rồi quên source control.** Nếu cần break-glass, ghi audit và reconcile vào IaC/KQL repository ngay sau recovery.

## 21. Lab end-to-end: từ Azure Portal tới KQL và query SDK

Lab có hai cấp độ: **A. chỉ truy vấn `datatable`** không tạo persistent data và **B. có bảng `ApiTelemetry` trong ADX lab**. Tất cả ví dụ chỉ mang tính hướng dẫn, **không được thực thi tự động khi soạn bài**. Tạo cluster/ingestion resources có thể tính phí và cần quyền quản trị; phải có ngân sách, chủ sở hữu và môi trường dùng thử được phê duyệt.

### 21.1. Chuẩn bị

- Tài khoản Azure/Entra ID có quyền truy cập **môi trường thử nghiệm**.
- Azure Data Explorer Web UI: `https://dataexplorer.azure.com` hoặc giao diện query phù hợp.
- Nếu có ADX cluster lab: query endpoint, **database name**, data-plane role Viewer/User cần thiết.
- Nếu muốn ingest: cluster/database/table riêng, quyền tạo table/mappings, Event Hubs/Blob source giả, kiểm soát chi phí.
- Không sử dụng token, connection string có key hoặc log khách hàng thật.
- Người học hiểu `datatable` chỉ sống trong phạm vi query hiện tại.

### 21.2. Lab A — không cần tạo bảng

1. Mở Kusto query editor trong môi trường KQL được cấp phép.
2. Sao chép query `let Demo=datatable(...)` tại **phần 7.1**.
3. Chạy và xác nhận có **12 rows prod + 1 row staging trước lọc**, sau lọc `Environment=="prod"` chỉ còn **12 rows**.
4. Thay phần cuối:

~~~kusto
Demo
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs,95)
  by Service, Region
| extend ErrorRatePct=round(100.0 * Http5xx / Requests,2)
| order by ErrorRatePct desc
~~~

**Lưu ý thực thi:** Phần mã trên là **phần đuôi thay thế** sau định nghĩa `let Demo=datatable(...)` trong **cùng query tab**; nếu chỉ chạy những dòng này ở tab trống sẽ báo unknown table `Demo`.

5. Thay filter thời gian bằng absolute dates `2026-11-20T09:00:00Z .. 2026-11-20T09:30:00Z`.
6. Lấy deployment từ `tostring(Properties.deployment)` và so sánh v41/v42.
7. Phân biệt `503/500` với `429` và `200/201`.
8. Giải thích tại sao p95 từ 13 records không là SLO production.

### 21.3. Lab B — dùng ADX database/table được cấp phép

Khi platform team có ADX lab:

1. Kiểm tra cluster/database endpoint đúng tenant, role và budget.
2. Tạo table/mapping tham khảo **phần 5.4** nếu có quyền và chưa tồn tại.
3. Dùng ingestion mechanism phù hợp để nạp **synthetic JSON records** có schema từ phần 4.2.
4. Kiểm tra ingestion mapping và số records bằng:

~~~kusto
ApiTelemetry
| summarize Events=count(), FirstEvent=min(Timestamp), LastEvent=max(Timestamp)
~~~

5. Chạy query 5xx rate, p95 theo service/operation và deployment.
6. Đo ingestion lag và so sánh event time/ingestion time.
7. Thêm trace/dependency table **chỉ khi đã có schema test**, rồi join theo `TraceId`.
8. Tạo một dashboard KQL phân biệt requests, 5xx, 429, p95 và ingestion lag.
9. Kiểm tra dữ liệu nhận được từ nguồn **không có PII/secret**.
10. Giữ quyền tạo/sửa policies cho DB/platform admins, không cấp rộng cho mọi analyst.

### 21.4. Đo ingestion lag bằng KQL

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| extend IngestedAtUtc=ingestion_time()
| where isnotnull(IngestedAtUtc)
| extend LagSeconds=datetime_diff("second", IngestedAtUtc, Timestamp)
| summarize
    Events=count(),
    MedianLagSeconds=percentile(LagSeconds,50),
    P95LagSeconds=percentile(LagSeconds,95),
    MaxLagSeconds=max(LagSeconds)
  by Service
~~~

**Điều kiện:** `ingestion_time()` cần metadata/policy phù hợp để trả giá trị; nếu null, query sẽ lọc hết dữ liệu. Timestamps client lệch đồng hồ hoặc event phát từ quá khứ sẽ làm lag khác pipeline latency thực. Để SLO chính xác, dùng producer/connector timestamps được kiểm soát và đo Event Hubs backlog riêng.

### 21.5. SDK query: Python và Azure CLI credential (lab)

Một analyst có thể dùng **Python Azure Data Explorer SDK** để truy vấn ADX. Trên máy dev đã được phép:

~~~bash
az login
python -m pip install azure-kusto-data

export KUSTO_CLUSTER="https://<cluster>.<region>.kusto.windows.net"
export KUSTO_DATABASE="Telemetry"
~~~

Ứng dụng Python tham khảo:

~~~python
import os

from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

cluster = os.environ["KUSTO_CLUSTER"]
database = os.environ["KUSTO_DATABASE"]

# Development-only login from az login; not a production credential plan.
kcsb = KustoConnectionStringBuilder.with_az_cli_authentication(cluster)
client = KustoClient(kcsb)

query = """
ApiTelemetry
| where Timestamp > ago(1h) and Environment == "prod"
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600)
  by Service
| order by Http5xx desc
"""

try:
    result = client.execute(database, query)
    for row in result.primary_results[0]:
        print(row["Service"], row["Requests"], row["Http5xx"])
finally:
    client.close()
~~~

**Điều kiện:** `ApiTelemetry` phải tồn tại, user đã `az login` vào đúng tenant, có **data-plane query role**, và network/DNS tới cluster phải hoạt động. Với production, dùng **managed identity/workload identity/service principal được phê duyệt**, không đặt một developer Azure CLI login vào container chạy 24/7. API và version của SDK có thể thay đổi; kiểm tra hướng dẫn package tại thời điểm triển khai.

### 21.6. Khi lab không có cluster

Đừng tự tạo một ADX production SKU có phí lớn chỉ để kiểm tra `summarize`. Có thể dùng môi trường demo/free/lab do tổ chức cung cấp **nếu có tính năng phù hợp**, nhưng điều khoản/quota thay đổi. Phần KQL `datatable` và các bài suy luận vẫn đủ để học cách viết queries mà không cần quyền ingestion.

### 21.7. Acceptance checklist cho lab

| Kiểm tra | Kết quả đạt |
|---|---|
| Schema/query editor | Query `datatable` chạy không lỗi |
| Filter môi trường | Prod 12, staging 1 trong data gốc |
| Error definitions | 500–599 là 5xx; 429 tách riêng |
| Percentiles | Có p95 theo service/operation, hiểu sample size |
| Structured JSON | Đọc được `Properties.deployment` |
| Traceability | Drill-down theo trace ID, không gộp nhầm spans |
| Security | Không dùng production PII/token, đúng role |
| Ingestion (nếu có) | Synthetic JSON đúng mapping, latency đo được |
| Performance | Có filter time/columns và result size phù hợp |
| Cost | Có owner/budget và cleanup plan |

## 22. Case study: điều tra sự cố Orders API sau deployment

**Giả định:** Orders API phát log chuẩn vào Event Hubs, ADX nhận records `ApiTelemetry`. Một bản cập nhật `v42` triển khai ở `southeastasia` lúc **09:10 UTC ngày 20/11/2026**, trước đó là `v41`. API bắt đầu trả nhiều `503` do timeout với Azure SQL. Các records trong `Demo` ở phần 7 mô phỏng tình huống này.

### 22.1. Chuỗi bằng chứng kỳ vọng

~~~mermaid
flowchart LR
    ALERT[Alert: p95 + 5xx spike] --> TIME[Locate time window]
    TIME --> SVC[Break down by service and region]
    SVC --> DEPLOY[Compare v41 / v42]
    DEPLOY --> TRACE[Drill down TraceId]
    TRACE --> DEP[Dependency evidence SQL timeout]
    DEP --> FIX[Rollback or fix backend]
    FIX --> VERIFY[Verify 5xx/p95 and ingestion health]
~~~

Không bắt đầu bằng việc khẳng định release `v42` là nguyên nhân duy nhất: Azure SQL, network/private DNS hoặc một dependency khác cũng có thể đồng thời lỗi. **Tìm bằng chứng trước, kết luận sau**.

### 22.2. Bước 1: khoanh khoảng thời gian

~~~kusto
let StartUtc = datetime(2026-11-20T09:00:00Z);
let EndUtc = datetime(2026-11-20T09:30:00Z);
ApiTelemetry
| where Timestamp >= StartUtc and Timestamp < EndUtc
| where Environment == "prod"
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs,95)
  by Service, Region, bin(Timestamp, 5m)
| extend ErrorPct=round(100.0 * Http5xx / Requests,2)
| order by Timestamp asc, ErrorPct desc
~~~

Kết quả nên cho thấy `orders-api`/`southeastasia` bất thường so với `catalog-api` và `orders-api` ở vùng khác (nếu dataset đủ lớn). **Một số records mẫu không đủ xác nhận causal impact**; truy vấn production cần nhiều mẫu và kiểm tra traffic mix.

### 22.3. Bước 2: deployment split

~~~kusto
ApiTelemetry
| where Timestamp >= datetime(2026-11-20T09:00:00Z)
  and Timestamp < datetime(2026-11-20T09:30:00Z)
| where Service == "orders-api" and Environment == "prod"
| extend Deployment=tostring(Properties.deployment)
| summarize
    Requests=count(),
    Error5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs,95)
  by Deployment, Region
| extend ErrorRatePct=round(100.0 * Error5xx / Requests,2)
| order by ErrorRatePct desc
~~~

Nếu v42 lỗi hơn v41, vẫn cần xét **region, request volume, traffic distribution** và thời gian release. Một release thường ảnh hưởng cả code lẫn feature flags/config/DB migrations; KQL giúp khoanh vùng, không tự xác định fix.

### 22.4. Bước 3: lỗi cụ thể

~~~kusto
ApiTelemetry
| where Timestamp >= datetime(2026-11-20T09:10:00Z)
  and Timestamp < datetime(2026-11-20T09:30:00Z)
| where Service == "orders-api" and StatusCode >= 500
| extend ErrorCategory=tostring(Properties.errorCategory)
| summarize
    Failures=count(),
    P95Ms=percentile(DurationMs,95),
    ExampleTrace=take_any(TraceId)
  by ErrorCategory, Region
| order by Failures desc
~~~

`take_any(TraceId)` lấy một ID mẫu **không được đảm bảo là trace tệ nhất**. Dùng nó như gợi ý drill-down, không coi là representative sample khoa học. Nếu cần trace **chậm nhất**, lọc theo DurationMs hoặc dùng `arg_max(DurationMs, ...)` với grouping phù hợp.

### 22.5. Bước 4: drill-down theo trace

~~~kusto
let TargetTrace="tr-005";
ApiTelemetry
| where Timestamp >= datetime(2026-11-20T09:00:00Z)
  and Timestamp < datetime(2026-11-20T10:00:00Z)
| where TraceId == TargetTrace
| project Timestamp, Service, Operation, StatusCode,
          DurationMs, SpanId, Properties
| order by Timestamp asc
~~~

Với full OpenTelemetry, cần tương quan `TraceId` trong **dependency logs** và application trace backend. Nếu chỉ có HTTP request event, bạn mới biết 503 xảy ra; thuộc tính `errorCategory=SqlTimeout` là **nhãn của app**, cần xác minh SQL performance/connectivity/timeout logs thực.

### 22.6. Bước 5: xác minh đã phục hồi

Sau khi rollback hoặc sửa connection pool, hãy so sánh 15 phút trước và 15 phút sau:

~~~kusto
let FixTime=datetime(2026-11-20T09:30:00Z);
let Before =
    ApiTelemetry
    | where Timestamp >= FixTime-15m and Timestamp < FixTime
    | where Service == "orders-api" and Environment == "prod"
    | summarize
        Requests=count(),
        Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
        P95Ms=percentile(DurationMs,95)
    | extend Phase="Before";
let After =
    ApiTelemetry
    | where Timestamp >= FixTime and Timestamp < FixTime+15m
    | where Service == "orders-api" and Environment == "prod"
    | summarize
        Requests=count(),
        Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
        P95Ms=percentile(DurationMs,95)
    | extend Phase="After";
union (Before), (After)
| extend ErrorPct=round(100.0 * Http5xx / Requests,2)
| project Phase, Requests, Http5xx, ErrorPct, P95Ms
~~~

Điều kiện: `FixTime` chỉ là mốc giả định; khi điều tra production dùng **deployment/change timestamp thực**. Dữ liệu của `After` có thể đến muộn, nên cần xác minh ingestion lag và chờ đủ số mẫu. **Có p95 tốt trở lại chưa đủ** nếu SQL data integrity/business transactions đã bị ảnh hưởng.

### 22.7. Viết postmortem từ bằng chứng

Một postmortem gọn cần:

- Timeline theo UTC: alert, first bad request, release, mitigation, recovery.
- Tác động: những services, operations, regions, client groups nào bị ảnh hưởng.
- Metrics: requests, 5xx rate, p95/p99, ingestion freshness.
- Evidence: trace IDs, dependency error categories, Azure SQL/Application Insights logs.
- Root cause có bằng chứng, không chỉ “v42 triển khai cùng lúc”.
- Corrective actions: test, rollout gate, tracing, circuit breaker, SQL pool, monitoring.
- RPO/RTO hoặc business recovery nếu dữ liệu bị ảnh hưởng.

**KQL hỗ trợ tìm bằng chứng**, còn quyết định xử lý hệ thống phải dựa trên SRE/application/database ownership và quy trình change management.

## 23. Ngoài HTTP logs: phân tích IoT telemetry và chuỗi thời gian

ADX không giới hạn ở HTTP status code. Một hệ thống logistics có thể gửi **temperature, humidity, vibration, device health** qua IoT Hub/Event Hubs. Những bản ghi này có `DeviceId` và timestamp, nhưng không có `StatusCode`/`DurationMs`.

### 23.1. Dữ liệu sensor mẫu tự chứa

~~~kusto
let Sensors = datatable(
    Timestamp:datetime, DeviceId:string, Region:string, TemperatureC:real)
[
    datetime(2026-11-20T08:00:00Z), "sensor-01", "warehouse-a", 24.0,
    datetime(2026-11-20T08:05:00Z), "sensor-01", "warehouse-a", 24.5,
    datetime(2026-11-20T08:10:00Z), "sensor-01", "warehouse-a", 31.2,
    datetime(2026-11-20T08:15:00Z), "sensor-01", "warehouse-a", 35.4,
    datetime(2026-11-20T08:00:00Z), "sensor-02", "warehouse-b", 22.1,
    datetime(2026-11-20T08:05:00Z), "sensor-02", "warehouse-b", 22.0,
    datetime(2026-11-20T08:10:00Z), "sensor-02", "warehouse-b", 22.2,
    datetime(2026-11-20T08:15:00Z), "sensor-02", "warehouse-b", 22.0
];
Sensors
| summarize
    Samples=count(),
    AvgC=round(avg(TemperatureC),1),
    PeakC=max(TemperatureC)
  by Region, DeviceId
| order by PeakC desc
~~~

**Kết quả kỳ vọng:** `sensor-01` đạt đỉnh **35.4°C**, cao hơn `sensor-02` **22.2°C**. Đây là dữ liệu tổng hợp để tập cú pháp, không phải tín hiệu thiết bị thật. Nếu nhiệt độ là safety-critical, phải có rules và validation/alert thiết bị/edge phù hợp, không chỉ dựa vào dashboard analytics.

### 23.2. So sánh lần đọc liên tiếp

~~~kusto
let Sensors = datatable(
    Timestamp:datetime, DeviceId:string, TemperatureC:real)
[
    datetime(2026-11-20T08:00:00Z), "sensor-01", 24.0,
    datetime(2026-11-20T08:05:00Z), "sensor-01", 24.5,
    datetime(2026-11-20T08:10:00Z), "sensor-01", 31.2,
    datetime(2026-11-20T08:15:00Z), "sensor-01", 35.4
];
Sensors
| sort by DeviceId asc, Timestamp asc
| serialize
| extend
    PreviousDevice=prev(DeviceId),
    PreviousC=prev(TemperatureC)
| where DeviceId == PreviousDevice
| extend DeltaC=TemperatureC-PreviousC
| project Timestamp, DeviceId, TemperatureC, PreviousC, DeltaC
| order by DeltaC desc
~~~

`prev()` phụ thuộc **thứ tự rows được serialize**. Không dùng nó trên bảng lớn không được sort hoặc dữ liệu có nhiều DeviceIds lẫn nhau mà quên kiểm tra ranh giới. Với dữ liệu sensor có thể đến muộn, `Timestamp` cần được dùng đúng theo event time chứ không dựa vào thứ tự ingestion.

### 23.3. Missing telemetry và mất kết nối thiết bị

Một sensor không gửi bản ghi trong 30 phút có thể:

- Mất điện hoặc network.
- Thiết bị ngưng gửi.
- Event Hubs connector bị lag.
- Bản ghi bị lỗi mapping.
- DeviceId đã được decommission hợp lệ.

**Một query chỉ đọc bảng telemetry không hiện thiết bị hoàn toàn mất records** nếu bạn không có **danh sách thiết bị được kỳ vọng**. Dùng dimension inventory được phép và `leftouter join` last-seen values, đặt ngưỡng phù hợp cadence từng thiết bị. Không coi “không có bản ghi” là nhiệt độ bằng 0.

### 23.4. Những lưu ý về time-series IoT

- Lọc dữ liệu theo thời gian trước khi aggregate.
- Đánh giá sensor sampling interval và source clock skew.
- Tách device malfunction khỏi event ingestion failures.
- Với billions of device IDs, tránh group all-time theo ID không giới hạn.
- Nếu cần phát hiện bất thường, dùng `make-series` và hàm series sau khi có đủ lịch sử.
- Không dùng KQL dashboard một mình để điều khiển actuator an toàn theo thời gian thực; use-case control cần bounded-latency edge/control system.

## 24. Troubleshooting: KQL sai, thiếu dữ liệu hoặc query rất chậm

### 24.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân phổ biến | Cách kiểm tra |
|---|---|---|
| `Failed to resolve table or column` | Sai table/database/schema/name case | `.show tables`, kiểm tra schema/permissions |
| Query dùng `TimeGenerated` nhưng bảng có `Timestamp` | Copy từ Azure Monitor Logs sang ADX custom table | Dùng đúng cột trong table thực |
| `0 rows` sau `ago(1h)` | Dữ liệu lab lịch sử hoặc source ngừng gửi | Kiểm tra min/max Timestamp, absolute window |
| `0 rows` dù producer gửi | Ingestion lag, connector lỗi, mapping sai | Event Hubs backlog, ingestion failures, table count |
| Field từ `Properties` luôn trống | JSON path sai, field không tồn tại, type không đúng | `take 5` với data được phép, xem schema mẫu |
| Query p95 rất cao dù average thấp | Tail latency thực, outliers, sample mix | Bucket/service/operation, raw top slow events |
| `dcount` không bằng số exact IDs | Approximate algorithm hoặc duplicates | Dùng count distinct exact khi phù hợp |
| Join trả gấp nhiều lần requests | Many-to-many keys, duplicate trace/span IDs | Aggregate/dedup đúng grain trước join |
| `mv-expand` làm query timeout | Mảng dynamic quá lớn, không filter sớm | Chặn expansion, filter time/source |
| Query quá chậm | Scan lâu năm, string parsing, high cardinality, join lớn | Explain/resource stats, lọc/projection sớm |
| Query bị throttle/timeout | Concurrency/cluster load, query limits | Workload metrics, giảm nặng, scale có căn cứ |
| 403/access denied | Entra principal không có database/table role | Kiểm tra tenant, cluster, data-plane role |
| Có cluster Reader nhưng không query được bảng | Azure control-plane vs Kusto data-plane khác nhau | Cấp role database phù hợp |
| `ingestion_time()` luôn null | Metadata/policy không được bật hoặc source không hỗ trợ | Kiểm tra ingest policy và nguồn timestamp |
| Dashboard chỉ hiện dữ liệu cũ | Ingestion stopped, time window sai, query cache/freshness | Last EventUtc, ingestion lag, connector health |
| Missing time buckets bị hiểu là 0 traffic | Không có events/ingestion gap | Make-series + source health probes |
| Không thấy 429 trong error dashboard | Chỉ countif 5xx | Tách throttled rate 429 và security events |
| TLS/private endpoint query lỗi | DNS/route/identity không đúng | Test từ runtime thật, HTTPS/TLS, data permissions |

### 24.2. Runbook chẩn đoán tám bước

**Bước 1 — Xác minh scope:** đúng cluster URI, database, table, thời gian, environment và resource group/subscription chưa?

**Bước 2 — Kiểm tra schema:** bảng có `Timestamp`, `Service`, `StatusCode` không? `Properties` là `dynamic` hay string?

**Bước 3 — Thử query tối giản:**

~~~kusto
ApiTelemetry
| take 5
~~~

Lệnh này chỉ kiểm tra xem bảng có rows hay không; `take` **không đảm bảo 5 rows mới nhất**. Nếu cần kiểm tra recent:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| top 5 by Timestamp desc
~~~

**Bước 4 — Kiểm tra time bounds và freshness:**

~~~kusto
ApiTelemetry
| summarize
    Rows=count(),
    MinTimestamp=min(Timestamp),
    MaxTimestamp=max(Timestamp)
~~~

Đọc `MaxTimestamp` trong bối cảnh source clock; một event có timestamp tương lai có thể làm query last-seen trông “mới” giả.

**Bước 5 — Kiểm tra ingestion**: connector/consumer group, Event Hubs backlog, failures, mapping, permissions, resource metrics.

**Bước 6 — Kiểm tra query plan**: có lọc time sớm, chỉ giữ cột cần thiết, join đúng cardinality, dynamic parsing và cardinality phù hợp?

**Bước 7 — Kiểm tra security/network**: Entra/data-plane role, private DNS, TLS, resource policies. Không tăng Owner subscription để sửa `SELECT`-equivalent.

**Bước 8 — Xác minh sửa lỗi**: so source counts, ingestion lag, query time, output values và synthetic business flow; cập nhật runbook.

### 24.3. Sự cố “triển khai xong nhưng error rate = 0%”

Một dashboard query:

~~~kusto
ApiTelemetry
| where Timestamp > ago(15m)
| summarize ErrorPct=100.0 * countif(StatusCode>=500) / count()
~~~

Trả `0%`. Nhưng Event Hubs connector đã dừng ingest từ 30 phút trước. **Không có events không phải zero errors.** Khi input rỗng, `count()=0` nên tỷ lệ có thể null/NaN theo ngữ cảnh; nếu hệ thống ép null thành 0 khi hiển thị, dashboard càng dễ đánh lừa.

Giải pháp: một dashboard SLO phải kiểm tra **data freshness/ingestion health và minimum sample threshold** trước khi khẳng định trạng thái khỏe.

### 24.4. Sự cố truy vấn “nhanh” nhưng trả kết quả sai

Giả sử `DependencyTelemetry` có 5 SQL calls trên mỗi request; join raw với `ApiTelemetry` rồi `count()` có thể tăng request count lên 5 lần. Query vẫn chạy nhanh và hiển thị biểu đồ đẹp, nhưng dữ liệu sai.

Giải pháp: định nghĩa **grain** (một row là request hay dependency call), pre-aggregate đúng khóa và có golden-data tests. **Tính đúng của KQL quan trọng ngang hiệu năng.**

## 25. Bài thực hành tổng hợp: từ log thô đến kết luận có bằng chứng

**Đề bài:** Hệ thống có `orders-api`, `catalog-api` và `payments-api`, phát sự kiện JSON vào Event Hubs và được ingest vào ADX. Bạn là SRE được giao điều tra một đợt tăng lỗi sau deployment. Với môi trường chưa có ADX lab, dùng `datatable` ở phần 7 và giải thích bằng ngôn ngữ tự nhiên; **không yêu cầu truy cập production**.

### 25.1. Bộ câu hỏi kỹ thuật

1. **Kiến trúc:** Vẽ data flow Application/IoT → Event Hubs/Blob → ADX → KQL dashboard. Giải thích Event Hubs không tự cung cấp KQL query.
2. **Chọn sản phẩm:** Khi nào ưu tiên Application Insights/Log Analytics thay vì tạo ADX cluster?
3. **Schema:** Thiết kế `Timestamp`, `Service`, `Environment`, `Operation`, `StatusCode`, `DurationMs`, `TraceId` và `Properties`.
4. **Ingestion:** Giải thích JSON ingestion mapping và hậu quả khi `durationMs` không phải number.
5. **Event vs ingest time:** Source event lúc 09:15, ADX nhận lúc 09:22; ingestion lag bao lâu và dùng timestamp nào để báo cáo API latency?
6. **KQL basic:** Viết query lấy 100 HTTP 5xx gần nhất của `orders-api` trong 6 giờ.
7. **Environment:** Vì sao phải lọc `Environment=="prod"` trước khi tính production SLO?
8. **Time bins:** Viết query requests theo 5 phút và region; giải thích missing buckets.
9. **Error rate:** Viết query tính 5xx rate và 429 rate riêng cho một service.
10. **Latency:** Viết query p50/p95/p99 theo operation; tại sao average chưa đủ?
11. **Deployment:** So sánh v41/v42 trên cùng time window và region.
12. **Dynamic:** Lấy `errorCategory` từ `Properties` và group theo category.
13. **Text search:** Khi nào dùng `has` thay `contains`? Cho ví dụ chuỗi CamelCase.
14. **Trace joins:** Join request và dependencies theo TraceId mà không đếm trùng requests.
15. **Distinct:** `dcount` khác `count_distinct` thế nào và khi nào approximation không được chấp nhận?
16. **Time series:** Dùng `make-series`/`series_decompose_anomalies` để phát hiện traffic spike; nêu rủi ro false positives.
17. **Query performance:** Tối ưu query scan một năm log có `mv-expand`/`join` và `project *`.
18. **Security:** Vì sao query có `where TenantId=="partner-a"` trong dashboard chưa đủ để cô lập tenant?
19. **Reliability:** Event Hubs gián đoạn 45 phút và chỉ lưu events 30 phút; dữ liệu nào có thể mất và cần kế hoạch gì?
20. **FinOps:** Ước lượng raw data/day cho 10 services × 1.000 events/s × 800 bytes/event.
21. **Monitoring:** Thiết kế alert ingestion lag, last event time, query p95 và cluster resource use.
22. **Incident:** API 503 giảm sau rollback nhưng ingestion đã dừng từ trước; vì sao không kết luận phục hồi chỉ từ KQL error rate?
23. **IoT:** Viết query temperature peak theo DeviceId trong 24 giờ và đánh giá timestamp lệch.
24. **Governance:** Liệt kê thay đổi schema/retention/roles cần được review bằng IaC/CI.

### 25.2. Đáp án và đoạn KQL tham khảo

**Câu 5 — độ trễ ingest:** 09:22 − 09:15 = **7 phút**. Để tính API execution duration, dùng `DurationMs` của request đã instrument đúng. Để đo pipeline latency, so nguồn/ingestion timestamps đã kiểm chứng. Không trừ ingestion time khỏi event time rồi gọi đó là “HTTP latency”.

**Câu 6 — 100 lỗi mới nhất:**

~~~kusto
ApiTelemetry
| where Timestamp >= ago(6h)
| where Environment == "prod"
| where Service == "orders-api"
| where StatusCode >= 500 and StatusCode < 600
| top 100 by Timestamp desc
| project Timestamp, Service, Operation, StatusCode,
          DurationMs, TraceId, Properties
~~~

**Câu 8 — requests theo bucket và region:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| where Environment == "prod"
| summarize Requests=count() by Region, bin(Timestamp, 5m)
| order by Timestamp asc, Region asc
~~~

**Câu 9 — 5xx và 429:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| where Environment == "prod"
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    Http429=countif(StatusCode == 429)
  by Service
| extend
    ServerErrorPct=round(100.0*Http5xx/Requests,2),
    ThrottlePct=round(100.0*Http429/Requests,2)
~~~

**Câu 10 — latency percentiles:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Environment == "prod"
| summarize
    Samples=count(),
    P50=percentile(DurationMs,50),
    P95=percentile(DurationMs,95),
    P99=percentile(DurationMs,99)
  by Operation
| order by P95 desc
~~~

**Câu 12 — error categories:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where StatusCode >= 500 and StatusCode < 600
| extend Category=tostring(Properties.errorCategory)
| summarize Errors=count() by Category
| order by Errors desc
~~~

**Câu 14 — join đúng grain:** xác định một row request, gom dependencies `summarize ... by TraceId` trước, rồi `join kind=leftouter`. Nếu một trace có nhiều request spans, dùng thêm span/root operation ID để phân biệt. Không lấy `count()` sau raw many-to-many join làm total request.

**Câu 15 — distinct:** `dcount` là approximate, phù hợp dashboard; `count_distinct` tính exact distinct theo giới hạn hệ thống, có thể tốn resource hơn. Financial ledger dùng event IDs/transactions ở authoritative store, không chỉ telemetry.

**Câu 18 — security:** filter UI có thể bị sửa/bỏ khi user có quyền query raw table. Cần database permissions/RLS hoặc cơ chế cách ly data-plane phù hợp, cộng audit và export policies.

**Câu 19 — mất events:** nếu outage 45 phút nhưng source retention chỉ 30 phút và không có archive, phần dữ liệu ngoài cửa sổ retention có thể không replay được. Cần raw Blob archive/retention đủ dài, monitoring lag và tested backfill.

**Câu 20 — volume:** raw **691.2 GB/day** trước nén/replication/overhead, như tính ở phần 19.2. Không suy trực tiếp billable stored GB.

**Câu 22 — chưa chứng minh recovery:** nếu pipeline dừng, KQL chỉ đang nhìn dữ liệu cũ. Xác minh ingestion lag, source activity, synthetic requests và App Insights/backend health trước khi tuyên bố hết 503.

### 25.3. Rubric đánh giá

| Hạng mục | Điều kiện đạt |
|---|---|
| **Đúng dữ liệu** | Phân biệt event time/ingestion time, request vs span grain |
| **Đúng KQL** | `where` thời gian, `summarize`, `bin`, p95, dynamic, join |
| **Đúng thống kê** | Error rate có denominator, 429 tách 5xx, hiểu sampling |
| **Đúng vận hành** | Biết kiểm tra pipeline freshness, thất bại ingest và query health |
| **Đúng bảo mật** | Không log PII/token, data-plane roles/RLS, retention |
| **Đúng hiệu năng** | Time filter/projection sớm, tránh high cardinality/expand/join phình |
| **Đúng kết luận** | Sử dụng nhiều nguồn bằng chứng, không gán causal chỉ từ correlation |
| **Đúng tài chính** | Tính raw data volume, đánh giá compute/storage/ingestion cost |

## 26. Checklist triển khai và vận hành Azure Data Explorer

### 26.1. Trước khi chọn ADX

- [ ] Bài toán thật sự cần analytics trên log/telemetry quy mô lớn; không có giải pháp sẵn như Log Analytics/App Insights đáp ứng tốt hơn?
- [ ] Xác định data sources, volume/peak ingest, schema, retention và query SLO.
- [ ] Quyết định event time UTC, ingestion time, `EventId`/`TraceId`, route template và phiên bản schema.
- [ ] Phân loại dữ liệu, PII/secrets, chính sách export và retention.
- [ ] Chọn cluster SKU/capacity/region/network theo nhu cầu và budget.
- [ ] Phân biệt ADX database query endpoint và ingestion endpoint.
- [ ] Có owner cho pipelines, KQL dashboards, Azure resource và data quality.
- [ ] Xác định raw source retention/backfill để xử lý dữ liệu mất.

### 26.2. Khi thiết kế pipeline

- [ ] Event Hubs/Blob/SDK ingestion connector có identity/permissions tối thiểu.
- [ ] Ingestion mapping tương thích JSON/CSV/Parquet source.
- [ ] Có validation cho timestamp, duration, status, trace IDs và unknown schema fields.
- [ ] Theo dõi connector failures, ingestion lag, backpressure và raw source backlog.
- [ ] Có tested replay/backfill, event dedup assumptions và dead-letter/quarantine strategy nếu cần.
- [ ] Table retention/caching policies được review theo compliance/SLO/cost.
- [ ] Cấu hình Private Endpoint/network/DNS/TLS nếu architecture yêu cầu.
- [ ] Không nạp raw PII/tokens/credential vào telemetry.

### 26.3. Khi viết KQL production

- [ ] Lọc time window sớm và dùng đúng cột `Timestamp`/`TimeGenerated` theo schema.
- [ ] Lọc environment, service, operation trước khi summarize/join.
- [ ] Chỉ project các cột cần thiết, tránh trả full dynamic payload không cần.
- [ ] Xác định grain: một row là HTTP request, span, dependency hay log line?
- [ ] Error rate có mẫu số và phân biệt HTTP 5xx/4xx/429 đúng.
- [ ] Percentile p95/p99 được tính trên dữ liệu đúng, không average percentiles.
- [ ] `join` không nhân số events ngoài ý muốn; dimension keys không trùng.
- [ ] `mv-expand`/`parse_json` có kiểm soát cardinality/memory.
- [ ] `dcount` và anomaly scores được hiểu là approximate/statistical.
- [ ] Nếu dùng `render`, query vẫn có bảng kết quả hữu ích cho SDK/automation.
- [ ] Có synthetic/golden-data tests và resource usage benchmark.

### 26.4. Khi phát hành dashboard/alert

- [ ] Có biểu đồ **ingestion freshness/lag** cạnh biểu đồ request/error.
- [ ] Có requests, 5xx, 429, p95/p99 theo service/region/operation.
- [ ] Cảnh báo có owner, severity, window, minimum traffic threshold và runbook.
- [ ] Query không quét retention dài vô ích mỗi lần refresh.
- [ ] Phân quyền reader/admin, RLS nếu cần, không dựa chỉ filter UI để cô lập tenant.
- [ ] Data export được kiểm soát, diagnostics không lưu secrets.
- [ ] Có dashboard/query versioning, review và rollback.
- [ ] Budget alerts và query/compute capacity được theo dõi.

### 26.5. Khi có sự cố

- [ ] Xác nhận đúng cluster/database/table và time window UTC.
- [ ] Kiểm tra ingestion pipeline/last event time trước khi diễn giải “zero errors”.
- [ ] Xác nhận schema và data types thực.
- [ ] Phân tích error volume/rate/p95 theo region/operation/deployment.
- [ ] Drill-down `TraceId` nhưng không dedup mất spans.
- [ ] Xem dependency, network, database và application logs độc lập.
- [ ] Nếu query chậm, lọc/projection sớm, kiểm tra join/expand/cardinality.
- [ ] Nếu thiếu dữ liệu, xem ingestion failures, Event Hubs retention và backfill plan.
- [ ] Khi rollback/khôi phục, xác minh freshness, SLO và business correctness.
- [ ] Ghi bằng chứng, nguyên nhân và hành động phòng ngừa.

## 27. Dọn dẹp lab và quản trị chi phí tài nguyên

`datatable` không tạo bảng persistent, nên chỉ thực hành KQL với dữ liệu tổng hợp **không cần cleanup Azure resources**. Nếu đã tạo ADX cluster lab, Event Hubs namespace, Blob storage, database/table hay Private Endpoint, chi phí có thể tiếp tục phát sinh sau buổi học.

### 27.1. Trước khi xóa

1. Xác nhận đúng subscription, resource group và chủ sở hữu.
2. Kiểm kê resources trong lab (ADX cluster, database, ingestion connectors, Event Hubs, Blob, network/DNS, monitoring).
3. Xem dữ liệu cần retention/backup theo chính sách; không xóa audit/security events thật.
4. Kiểm tra có downstream dashboards/alerts/other teams đang dùng cluster/database không.
5. Nếu là ADX dùng chung, **không xóa cả cluster/resource group** chỉ vì bạn tạo một table thử nghiệm.
6. Tắt producers và connectors lab đúng cách, bảo đảm không có scheduled jobs còn chạy.
7. Dọn đúng tài nguyên thuộc lab sau approval; xem chi phí còn lại qua Azure Cost Management.

Lệnh Azure CLI **chỉ đọc** để xác minh scope:

~~~bash
az account show --query "{id:id,name:name,tenantId:tenantId}" -o table

az resource list \
  --resource-group "<approved-lab-resource-group>" \
  --output table
~~~

**Không chạy** một lệnh `az group delete` với resource group chưa được kiểm kê/approved. Xóa ADX database/table/cluster có thể phá dashboards, data retention và compliance evidence của người khác. Đây là lab phân tích, không cần thực hành lệnh phá hủy để hiểu KQL.

## 28. Tài liệu tham khảo và ghi nhớ

Các tài liệu kỹ thuật nên tra cứu khi triển khai thực tế, đặc biệt vì Azure Data Explorer, SDK, RBAC và networking có thể thay đổi theo phiên bản/tier:

- [Azure Data Explorer documentation](https://learn.microsoft.com/azure/data-explorer/) — tổng quan cluster, ingestion, quản trị và vận hành.
- [Azure Data Explorer overview](https://learn.microsoft.com/azure/data-explorer/data-explorer-overview) — mục tiêu và kiến trúc.
- [Kusto Query Language documentation](https://learn.microsoft.com/kusto/query/) — operators, data types, functions, query semantics.
- [`summarize` operator](https://learn.microsoft.com/kusto/query/summarize-operator) — aggregation theo dimensions.
- [`join` operator](https://learn.microsoft.com/kusto/query/join-operator) — join kinds và lựa chọn strategy.
- [`make-series` operator](https://learn.microsoft.com/kusto/query/make-series-operator) — time series.
- [`series_decompose_anomalies()`](https://learn.microsoft.com/kusto/query/series-decompose-anomalies-function) — anomaly detection.
- [KQL Python client SDK](https://learn.microsoft.com/azure/data-explorer/python-query-data) — authentication và query execution.

**Những điểm then chốt cần ghi nhớ:**

1. **ADX là nền tảng analytics cho events/logs/telemetry**, không thay transactional database hay message broker.
2. **ADX và Azure Monitor Logs cùng dùng KQL**, nhưng schema, quyền, ingestion, query endpoints và billing không giống nhau.
3. **Schema tốt quyết định query tốt:** event time UTC, typed dimensions, status, duration, trace/span IDs và chỉ dùng `dynamic` cho fields linh hoạt.
4. **Ingestion là pipeline cần quản trị:** Event Hubs/Blob/SDK, mapping, validation, late events, replay và ingestion lag.
5. **KQL mạnh nhờ pipeline:** `where` → `project/extend` → `summarize` → `join/make-series` → chart hoặc drill-down.
6. **Error rate và p95/p99 cần thống kê đúng:** phân biệt 5xx, 429, 4xx, sample size, sampling và duplicate events.
7. **Correlation không là causality:** trace ID giúp tìm quan hệ; kết luận root cause cần thêm deployment/dependency/network/business evidence.
8. **Tối ưu có nguyên tắc:** lọc thời gian sớm, giảm cột, kiểm soát cardinality, join/expand, materialization và caching.
9. **Bảo mật ở data plane:** Entra ID, Kusto roles, RLS và private networking, không dùng filter UI hoặc Azure Contributor như thay thế authorization dữ liệu.
10. **Dashboard khỏe phải có dữ liệu mới:** query trả 200 không có nghĩa ingestion đang hoạt động.
11. **Vận hành phải chuẩn bị lỗi:** monitoring, retention, backfill, backups/exports, IaC và chi phí rõ ràng.
12. **Ra quyết định dựa trên nguồn và yêu cầu:** nếu App Insights/Log Analytics đã đáp ứng SLO và nhu cầu log, đừng dựng thêm ADX không có business value.

Một hệ thống phân tích log/telemetry bằng KQL chỉ thực sự có giá trị khi có thể trả lời **điều gì đã xảy ra, xảy ra khi nào, trên dịch vụ và người dùng/region nào, dữ liệu có đầy đủ và mới không, kết luận có bằng chứng độc lập không, và chi phí/quyền truy cập được kiểm soát ra sao**.
