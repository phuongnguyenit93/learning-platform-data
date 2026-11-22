# Copy activity, incremental load và điều phối pipeline

## 1. Bài toán thực tế: chuyển dữ liệu không được làm mất hoặc nhân đôi

Một công ty thương mại điện tử có cơ sở dữ liệu giao dịch SQL Server chứa bảng **Orders** với hàng triệu dòng. Đội phân tích cần đưa dữ liệu đến **Azure Data Lake Storage Gen2 (ADLS Gen2)** để lưu bản sao dữ liệu thô và đến **Azure SQL Database** để tạo bảng báo cáo.

Cách đơn giản nhất là sao chép toàn bộ bảng mỗi giờ. Cách này sớm gặp vấn đề:

- Một bảng 500 GB phải được đọc và truyền lại dù chỉ 1.000 đơn hàng thay đổi.
- Tải SELECT/scan gây ảnh hưởng ứng dụng giao dịch.
- Thời gian copy vượt chu kỳ chạy, các pipeline chồng lên nhau.
- Nếu một lần chạy lỗi giữa chừng rồi chạy lại, dữ liệu đích có thể bị ghi trùng.
- Nếu cập nhật mốc đã đọc quá sớm, một số thay đổi bị bỏ sót vĩnh viễn.

**Copy activity** giải quyết việc truyền dữ liệu giữa nguồn và đích. **Incremental load** xác định *dữ liệu mới hoặc thay đổi nào cần sao chép*. **Pipeline orchestration** điều phối thứ tự, trigger, dependency, retry, kiểm tra và cập nhật tiến độ.

Đây là bài học thuộc chương **Nền tảng dữ liệu và phân tích** của module tìm hiểu hệ sinh thái Microsoft Azure. Nội dung liên kết quản trị resource group, network, identity Microsoft Entra ID, ADLS, Azure SQL, giám sát và chi phí vào một quy trình ingest dữ liệu có khả năng vận hành thực tế.

### Mục tiêu của kịch bản xuyên suốt

Một pipeline tên **pl_orders_incremental** cần:

1. Đọc checkpoint hoặc watermark lần chạy thành công cuối.
2. Chốt ranh giới trên của lần chạy hiện tại.
3. Copy đúng phần dữ liệu thay đổi vào vùng staging.
4. Validate số lượng/chất lượng dữ liệu.
5. Upsert hoặc merge vào bảng báo cáo một cách idempotent.
6. Chỉ khi kết quả đích đã bền vững, cập nhật watermark.
7. Ghi run ID, số dòng, thời gian, RU/compute nếu liên quan, trạng thái và lỗi.
8. Chạy được lại khi thất bại mà không làm sai dữ liệu.

## 2. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích Azure Data Factory (ADF), pipeline, activity, linked service, dataset, trigger và Integration Runtime.
2. Thiết kế Copy activity cho SQL, Azure Storage và những connector được hỗ trợ.
3. Phân biệt full load, append-only incremental, update-aware incremental và CDC.
4. Chọn watermark theo timestamp, ID tăng dần, change version hoặc log sequence thích hợp.
5. Thiết kế bảng control và quy tắc cập nhật watermark chỉ sau khi dữ liệu đích an toàn.
6. Tạo cửa sổ (last, upper] để đọc đúng một phạm vi.
7. Giải quyết timestamp trùng nhau, late-arriving data, commit race, delete và schema drift.
8. Dùng staging, upsert/MERGE, deduplication và idempotent rerun.
9. Điều phối Lookup, Copy, Stored Procedure, If Condition, ForEach và Execute Pipeline.
10. Sử dụng schedule, tumbling-window và storage-event triggers đúng mục đích.
11. Hiểu retry, timeout, concurrency, dependency và recovery/backfill.
12. Chọn Azure Integration Runtime, self-hosted Integration Runtime, VNet/private connectivity và xác thực an toàn.
13. Giám sát rowsRead, rowsCopied, duration, throughput, failure, data consistency và chi phí.
14. Thực hiện bài lab mô phỏng incremental load với SQL Server/Azure SQL và ADLS.

## 3. Azure Data Factory và các khái niệm chính

**Azure Data Factory** là dịch vụ điều phối và tích hợp dữ liệu. Nó quản lý pipeline definitions, activity execution, connection metadata, monitoring và triggers. Các phiên bản pipeline trong **Azure Synapse Analytics** có khái niệm gần giống nhưng không nên giả định mọi connector, màn hình hay setting hoàn toàn giống nhau; ví dụ ở đây tập trung vào **ADF**.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Factory** | Tài nguyên quản lý pipelines | adf-commerce-prod |
| **Pipeline** | Quy trình gồm nhiều activities | pl_orders_incremental |
| **Activity** | Một bước cụ thể | Lookup, Copy, Stored Procedure |
| **Linked service** | Cấu hình kết nối tới data store/compute | ls_sql_source, ls_adls |
| **Dataset** | Định nghĩa tham chiếu cấu trúc/dữ liệu nguồn hoặc đích | ds_orders_sql, ds_stage_parquet |
| **Integration Runtime (IR)** | Hạ tầng thực hiện transfer/compute/connectivity tùy activity | Azure IR hoặc self-hosted IR |
| **Trigger** | Khởi chạy pipeline theo lịch/sự kiện/cửa sổ | Schedule, tumbling window |
| **Parameter** | Giá trị đầu vào của pipeline/dataset | windowStart, windowEnd |
| **Variable** | Trạng thái đơn giản trong pipeline | status, currentFile |
| **Monitor** | Quan sát pipeline/activity runs | Rows copied, failure details |

### 3.1. Bản đồ luồng thực thi

~~~mermaid
flowchart LR
    T[Trigger / Manual run] --> P[Pipeline]
    P --> L[Lookup watermark]
    L --> U[Determine upper bound]
    U --> C[Copy activity]
    C --> V[Validate]
    V --> M[Apply staging / merge]
    M --> W[Commit watermark]
    W --> O[Monitoring / alert]
~~~

Trên sơ đồ, các mũi tên là **dependency điều phối**; chúng không ngụ ý mọi activity thuộc cùng một distributed database transaction.

### 3.2. Control plane và data movement

ADF điều phối. Dữ liệu được copy thông qua connector và Integration Runtime, không nhất thiết đi qua máy đang mở browser hoặc máy chạy ADF Studio.

Điều này quan trọng với quyền mạng: **ADF Studio mở được không có nghĩa Integration Runtime đọc được nguồn SQL** hoặc ghi được Storage sink.

## 4. Copy activity thực sự làm gì?

**Copy activity** đọc dữ liệu từ source, truyền qua Integration Runtime theo cơ chế connector và ghi sang sink. Nó có thể hỗ trợ dữ liệu dạng bảng, file, binary và nhiều dạng khác tùy source/sink.

Ví dụ:

~~~text
SQL Server Orders
      |
      | Source query
      v
Copy Activity
      |
      +----> ADLS Gen2 /raw/orders/...
      |
      +----> Azure SQL staging table
~~~

Một Copy activity có **một source và một sink logic** theo cấu hình hoạt động; sơ đồ nhánh trên thể hiện hai hướng kiến trúc lựa chọn hoặc hai activities tách biệt, **không phải một Copy duy nhất ghi đồng thời hai sinks**.

### 4.1. Những thiết lập phổ biến

- **Source**: bảng, query, file path, wildcard, partitioned read nếu hỗ trợ.
- **Sink**: table/file path, write behavior, mapping, output format.
- **Dataset/linked service**: thông tin cấu trúc và kết nối.
- **Mapping**: ánh xạ các cột/kiểu dữ liệu.
- **Performance**: parallel copies, data integration units, staging và copy partitioning theo connector/tier.
- **Fault tolerance**: hành vi với bản ghi lỗi, skip/error logging theo khả năng connector.
- **Retry/timeout**: mức activity trong orchestration.

### 4.2. Copy không tự hiểu semantics nghiệp vụ

Nếu nguồn có bản ghi orderId=1001 đã thay đổi trạng thái, Copy activity không tự quyết định:

- Đích cần INSERT hay UPDATE.
- Một deletion ở nguồn phải xóa ở đích hay đánh dấu deleted.
- Có được phép ghi trùng không.
- Đã đủ điều kiện commit watermark chưa.
- Có cần merge nhiều updates trong một cửa sổ không.

Đây là những quyết định của **incremental strategy, staging và business logic**.

## 5. Chọn Integration Runtime (IR)

Integration Runtime đảm nhiệm data movement/dispatching tùy activity và kết nối.

| IR | Trường hợp phù hợp | Lưu ý |
|---|---|---|
| **Azure IR** | Copy giữa các cloud stores khi kết nối được theo network policy | Region, data movement, networking, DIUs |
| **Azure IR với Managed VNet** | Cần managed private endpoints theo tính năng và connector hỗ trợ | Phê duyệt private endpoints, DNS, cold-start/queueing |
| **Self-hosted IR (SHIR)** | Kết nối on-prem SQL hoặc nguồn trong mạng không công khai | Tự vận hành node Windows, version, credentials, HA và outbound |
| **Azure-SSIS IR** | Chạy các SSIS packages tương thích | Không phải lựa chọn mặc định chỉ để chạy Copy activity |

### 5.1. Nguồn SQL Server on-prem

SHIR chạy trong mạng có thể kết nối SQL Server và đi ra Azure service endpoints theo chính sách. **Không nên mở SQL Server trực tiếp ra Internet chỉ để ADF copy.**

### 5.2. Sink private trong Azure

Kiểm tra VNet, private endpoint, DNS, firewall, IAM và IR được chọn. Cần xác định đường truyền thực cho connector, không suy luận từ việc ADF resource đã có managed identity.

### 5.3. Scale/HA cho SHIR

Với workload quan trọng, xem xét nhiều nodes trong một self-hosted IR theo mô hình được hỗ trợ, theo dõi CPU, memory, queue, connectivity và phần mềm trên nodes. Các node phải được vận hành/patch theo chính sách tổ chức.

## 6. Linked service, dataset và managed identity

**Linked service** khai báo *đến đâu và bằng cách nào kết nối*. **Dataset** chỉ ra *dữ liệu gì và ở đâu* trong data store đó.

Ví dụ:

~~~text
Linked service: ls_azure_sql
  endpoint / database / authentication

Dataset: ds_orders_staging
  linkedService = ls_azure_sql
  schema = dbo
  table = OrdersStage
~~~

### 6.1. Authentication

Có thể sử dụng managed identity/service principal khi connector hỗ trợ. Với SQL source và ADLS sink, thường phải cấp quyền data-plane thích hợp:

- Azure SQL: Entra principal/database user và SQL grants cần thiết.
- ADLS Gen2: Azure RBAC data role kết hợp ACL khi áp dụng.
- Azure Key Vault: quyền đọc secrets cho factory identity hoặc identity kết nối phù hợp.
- On-prem SQL: credentials được lưu và bảo vệ qua cơ chế được duyệt.

**Role Contributor trên resource group không tự đảm bảo quyền SELECT trên SQL hoặc ghi file ADLS.**

### 6.2. Parameter hóa dataset

Dataset có thể nhận parameters như **schemaName**, **tableName**, **folderPath** để tái sử dụng. Nhưng tham số table/schema là identifier trong SQL: phải dùng danh sách allowlist đáng tin, không tự nối trực tiếp từ HTTP input không kiểm soát.

### 6.3. Secret rotation

Không ghi SQL password, storage key hoặc SAS token vào expression/logs. Dùng managed identity và Key Vault reference khi connector hỗ trợ. Quy trình rotation phải bao gồm test kết nối và rollback.

## 7. Full load, incremental load và CDC khác nhau thế nào?

| Chiến lược | Dữ liệu được lấy | Hợp khi | Rủi ro |
|---|---|---|---|
| **Full refresh** | Toàn bộ dataset hoặc partition cần làm mới | Dataset nhỏ, bảng tham chiếu | Tốn scan/transfer, downtime hoặc overwrite |
| **Append-only by ID** | Bản ghi có ID lớn hơn ID đã ghi | Dữ liệu chỉ INSERT, ID tăng đúng | Bỏ lỡ UPDATE, DELETE và ID tạo trước nhưng commit sau |
| **Timestamp watermark** | Hàng có modifiedAt trong cửa sổ | Nguồn có cột cập nhật đáng tin cậy | Ties, late commits, clock skew, DELETE |
| **Change Tracking (CT)** | Những PK đã thay đổi kể từ version | SQL Server/Azure SQL khi CT được bật và retention đủ | Không luôn có before/after details; cần đọc current rows và deletes |
| **Change Data Capture (CDC)** | Các insert/update/delete từ change log | Cần xử lý changes đầy đủ theo thứ tự/LSN | Retention, schema evolution, source support, vận hành |
| **File modification/listing** | File mới/sửa theo metadata | File landing zone | Timestamp và eventual delivery có thể thiếu semantics row-level |

**Incremental không có nghĩa chỉ lấy INSERT.** Phải trả lời rõ cần phản ánh UPDATE, DELETE và record đến muộn hay không.

### 7.1. Hai nhánh minh họa

~~~text
Append-only events  -> LastEventId / sequence
Mutable Orders       -> UpdatedAt + safety overlap hoặc CT/CDC
~~~

Nếu bảng có UPDATE/DELETE quan trọng, incremental dựa trên **created_at** là không đủ.

## 8. Watermark là gì?

**Watermark** là mốc tiến độ của dữ liệu đã được xử lý an toàn. Nó có thể là:

- Timestamp **lastModifiedAtUtc**.
- ID tăng dần **lastId**.
- SQL change tracking version.
- CDC log sequence number (LSN).
- Offset/checkpoint khác theo nguồn.

Ví dụ:

~~~text
Watermark đã commit: 2026-11-19T10:00:00.000Z
Upper bound của lần chạy: 2026-11-19T10:30:00.000Z

Đọc:
    updated_at > 10:00:00
AND updated_at <= 10:30:00
~~~

Ký hiệu toán học cho cửa sổ là **(lastWatermark, upperWatermark]**: mở bên trái, đóng bên phải.

### 8.1. Watermark không phải thời gian chạy pipeline

Nếu pipeline bắt đầu lúc 10:32 nhưng source database chưa commit mọi transaction có modified_at <= 10:30, việc lấy upper=10:30 mà không có cơ chế đảm bảo commit visibility có thể gây bỏ sót. Phải hiểu semantics của timestamp và isolation ở nguồn.

### 8.2. Không nâng watermark lên upper trước khi copy

Nếu copy fail sau khi nâng watermark, lần chạy tiếp theo sẽ bỏ qua khoảng dữ liệu chưa được copy. **Chỉ commit watermark sau khi dữ liệu đã được apply/validate an toàn.**

## 9. Bảng điều khiển watermark và run log

Ví dụ T-SQL trên **Azure SQL Database** dùng làm control store:

~~~sql
CREATE TABLE dbo.EtlWatermark (
    PipelineName      nvarchar(200) NOT NULL PRIMARY KEY,
    LastWatermarkUtc  datetime2(7) NOT NULL,
    UpdatedAtUtc      datetime2(7) NOT NULL
        CONSTRAINT DF_EtlWatermark_Updated
        DEFAULT SYSUTCDATETIME()
);

CREATE TABLE dbo.EtlRunLog (
    RunId             nvarchar(100) NOT NULL PRIMARY KEY,
    PipelineName      nvarchar(200) NOT NULL,
    StartWatermarkUtc datetime2(7) NOT NULL,
    UpperWatermarkUtc datetime2(7) NOT NULL,
    StartedAtUtc      datetime2(7) NOT NULL,
    CompletedAtUtc    datetime2(7) NULL,
    Status            nvarchar(30) NOT NULL,
    RowsCopied        bigint NULL,
    ErrorMessage      nvarchar(2000) NULL
);
~~~

Khởi tạo một pipeline:

~~~sql
INSERT INTO dbo.EtlWatermark (PipelineName, LastWatermarkUtc)
VALUES ('pl_orders_incremental', '2000-01-01T00:00:00.0000000');
~~~

Chỉ chạy một lần hoặc dùng upsert có điều kiện trong setup IaC. Giá trị đầu năm 2000 chỉ là sentinel minh họa; với production, mốc khởi tạo phải dựa trên chính sách full seeding/historical backfill.

### 9.1. Vì sao tách watermark và run log?

- Watermark biểu diễn **tiến độ đã cam kết**.
- Run log biểu diễn **mọi lần chạy**, kể cả lỗi, retry, cancellation và rerun.
- Một lần chạy lỗi phải được giữ dấu vết nhưng **không nâng** watermark.
- Một cùng cửa sổ chạy lại cần biết đã apply bao nhiêu dữ liệu.

### 9.2. Concurrency control

Nếu hai pipeline runs cùng đọc watermark cũ và cùng ghi, có thể chồng cửa sổ. Đặt pipeline concurrency phù hợp, dùng lock/lease/serializing controller hoặc stored procedure transaction để claim cửa sổ. **Không coi một bảng watermark đơn thuần đã ngăn được concurrent runs.**

## 10. Chụp ranh giới trên và chọn dữ liệu nguồn

Ví dụ nguồn **SQL Server**, bảng **dbo.Orders**:

~~~sql
CREATE TABLE dbo.Orders (
    OrderId        bigint PRIMARY KEY,
    CustomerId     bigint NOT NULL,
    Status         nvarchar(30) NOT NULL,
    Amount         decimal(18,2) NOT NULL,
    ModifiedAtUtc  datetime2(7) NOT NULL
);
~~~

Cách minh họa lấy upper:

~~~sql
SELECT SYSUTCDATETIME() AS UpperWatermarkUtc;
~~~

Với timestamp tracking đáng tin, một query source có thể:

~~~sql
SELECT OrderId, CustomerId, Status, Amount, ModifiedAtUtc
FROM dbo.Orders
WHERE ModifiedAtUtc > @lastWatermark
  AND ModifiedAtUtc <= @upperWatermark;
~~~

Hai giá trị **@lastWatermark** và **@upperWatermark** cần được cấp an toàn bởi connector/query parameters hoặc stored procedure theo khả năng hỗ trợ. Nếu chỉ có dynamic SQL text, phải kiểm soát chặt định dạng UTC và tất cả identifiers/values.

### 10.1. Rủi ro commit race

Transaction bắt đầu lúc 10:29, ghi ModifiedAtUtc=10:29, nhưng chỉ commit lúc 10:31. Pipeline chốt upper=10:30 và quét lúc 10:30:30 nên không thấy row chưa commit. Lần sau lọc >10:30 và row 10:29 bị bỏ sót.

**Kết luận:** chỉ dùng wall-clock upper với cột modified_at chưa chắc đúng trong hệ thống có long transactions, nguồn tự ghi timestamp hoặc late commits.

### 10.2. Cách giảm rủi ro

- Dùng CT/CDC/log sequence khi cần correctness cao và nguồn hỗ trợ.
- Có **safety delay**: chốt upper lùi một khoảng so với thời điểm hiện tại, phù hợp phân phối commit latency.
- Dùng **overlap window** và idempotent dedup/upsert; không dùng để biện minh cho thời gian commit bất kỳ dài vô hạn.
- Đảm bảo cột ModifiedAtUtc do DB/application cập nhật nhất quán khi mỗi lần thay đổi.
- Có reconciliation định kỳ so sánh nguồn và đích để phát hiện miss.

### 10.3. Clock skew

Nếu timestamp được ghi từ nhiều app servers lệch đồng hồ, một record mới có thể mang timestamp quá cũ. Ưu tiên timestamps/versions theo nguồn nhất quán hoặc commit-based mechanism, thay vì tin tuyệt đối vào client clocks.

## 11. Timestamp trùng nhau và watermark ghép

Giả sử nhiều rows có cùng timestamp **10:30:00.000**:

~~~text
OrderId 101 | ModifiedAt=10:30:00.000
OrderId 102 | ModifiedAt=10:30:00.000
OrderId 103 | ModifiedAt=10:30:00.000
~~~

Nếu pipeline ghi watermark tại 10:30 và sau đó lọc **>10:30**, mọi row có cùng timestamp nhưng chưa được đọc sẽ bị bỏ qua.

### 11.1. Khi nào cách timestamp-only vẫn dùng được?

Khi pipeline copy **toàn bộ cửa sổ tới upper** thành công và timestamp/commit semantics đáng tin; các timestamps bằng upper đã được xử lý đầy đủ, không bị phân lô cắt dở. Dẫu vậy vẫn cần xử lý late commits.

### 11.2. Watermark ghép (timestamp, primary key)

Một mô hình seek pagination:

~~~sql
SELECT TOP (1000)
    OrderId, CustomerId, Status, Amount, ModifiedAtUtc
FROM dbo.Orders
WHERE ModifiedAtUtc > @lastTimestamp
   OR (
       ModifiedAtUtc = @lastTimestamp
       AND OrderId > @lastOrderId
   )
ORDER BY ModifiedAtUtc, OrderId;
~~~

Trong mô hình này checkpoint sau mỗi trang là **(lastTimestamp, lastOrderId)** của row cuối đã xử lý bền vững. Nếu chỉ checkpoint timestamp mà không OrderId, có nguy cơ bỏ rows cùng timestamp khi chuyển trang.

**Vẫn còn commit race** nếu late transaction xuất hiện với timestamp cũ nhưng key nhỏ hơn checkpoint; watermark ghép không thay thế CDC/commit tracking.

## 12. Pipeline Copy theo watermark: sơ đồ từng bước

~~~mermaid
flowchart TD
    START([Trigger]) --> L[Lookup last committed watermark]
    L --> U[Determine stable upper boundary]
    U --> CLAIM[Claim unique run/window]
    CLAIM --> COPY[Copy source delta to staging]
    COPY --> CHECK{Copy/validation successful?}
    CHECK -->|No| FAIL[Log failure, retain old watermark]
    CHECK -->|Yes| APPLY[Idempotent merge/upsert into destination]
    APPLY -->|Failure| FAIL
    APPLY -->|Success| COMMIT[Commit watermark after durable apply]
    COMMIT --> LOG[Record rows, duration and run status]
    LOG --> DONE([Success])
~~~

### 12.1. Vì sao cần staging?

Copy source delta trực tiếp vào bảng báo cáo có thể gặp:

- Duplicate rows khi rerun.
- Data changes không được apply theo business key.
- Một Copy partial write để lại trạng thái nửa chừng.
- Khó kiểm tra số dòng và schema.
- Khó phân biệt dữ liệu từ run nào.

**Staging** cho phép tải delta, validate, dedup rồi apply idempotent. Có thể dùng **Azure SQL staging table** hoặc **ADLS landing files** theo sink và workload.

### 12.2. Tính đúng quan trọng hơn pipeline activity thành công

Copy status **Succeeded** chứng minh activity thực hiện thành công theo connector, không tự chứng minh downstream tables chính xác. Cần validation/constraints và business reconciliation.

## 13. Tổ chức dữ liệu trong ADLS Gen2

Một cách chia layer:

~~~text
adls-account/
  landing/orders/
    ingest_date=2026-11-20/
      run_id=<pipeline-run-id>/
        part-0001.parquet
  bronze/orders/
  silver/orders_current/
  gold/daily_order_revenue/
~~~

Đây là cấu trúc minh họa; đường dẫn thực phải phù hợp quy định naming/retention/partitioning.

### 13.1. Raw/landing

Giữ dữ liệu đầu vào của lần chạy, metadata như source system, runId, extraction window và ingestion timestamp. Tránh viết đè file cũ nếu cần audit/replay.

### 13.2. Silver/current state

Chuyển đổi, dedup, xử lý UPDATE/DELETE và tạo một state đúng theo business key.

### 13.3. Gold/marts

Bảng phục vụ BI/analytics, có quy tắc aggregate và kiểm tra chất lượng.

### 13.4. Không mặc định Copy activity tự tạo Delta Lake transaction

Copy vào Parquet/CSV là chuyển dữ liệu file; việc duy trì một bảng **Delta Lake** có transaction log, MERGE và schema enforcement cần engine/công cụ phù hợp, không phải cứ đặt tên file .parquet là có tính năng ACID của Delta.

## 14. Copy activity: source và sink configuration

Ví dụ thiết kế:

| Thuộc tính | Giá trị minh họa |
|---|---|
| Source linked service | SQL Server/Azure SQL connection |
| Source dataset | dbo.Orders |
| Source query | Lấy (last, upper] |
| Sink linked service | Azure SQL Database |
| Sink dataset | dbo.OrdersStage |
| Mapping | OrderId, CustomerId, Status, Amount, ModifiedAtUtc |
| Run marker | RunId và pipeline metadata |
| IR | Azure IR hoặc self-hosted IR theo network |
| Error handling | Fail activity nếu copy không đảm bảo dữ liệu chính xác |
| Monitoring | rowsRead, rowsCopied, duration, throughput, errors |

### 14.1. Chọn sink write behavior

- **Insert/append** phù hợp staging có runId hoặc lịch sử append-only.
- **Upsert** có thể được connector hỗ trợ với key column và các ràng buộc tùy sink.
- **Stored procedure/merge sau copy** phù hợp khi cần logic nghiệp vụ phức tạp, dedup, version checks và atomic watermark update.

Đừng giả định mỗi sink connector có cùng tính năng upsert, transaction hoặc schema handling. Kiểm tra cụ thể connector và IR.

### 14.2. Copy parallelism

Copy activity có thể hỗ trợ chia nguồn/đích và parallelCopies/DIUs theo connector. Tăng song song không tự nâng throughput của source DB hoặc tăng capacity đích; có thể gây lock pressure, DTU/vCore exhaustion hoặc network bottleneck.

### 14.3. Staging + validation

Cần metadata mỗi run: runId, window boundaries, expected source rows (nếu có), rowsCopied, schemaVersion và trạng thái validation. Có thể dùng schema mapping tường minh thay vì auto-mapping nếu hợp đồng dữ liệu quan trọng.

## 15. ADF expressions và dynamic content

ADF cho phép tham chiếu parameters, variables và outputs từ activities.

Ví dụ:

~~~text
@pipeline().RunId
@pipeline().parameters.windowStart
@pipeline().parameters.windowEnd
@activity('LookupWatermark').output.firstRow.LastWatermarkUtc
@activity('LookupUpper').output.firstRow.UpperWatermarkUtc
~~~

Các expressions trên giả định:

- Pipeline có parameters tên **windowStart/windowEnd** khi dùng.
- Lookup có tên đúng chính tả và **firstRowOnly=true**.
- Query SQL của Lookup trả về aliases chính xác.
- Output shape của activity phù hợp; nếu **firstRowOnly=false**, dữ liệu có thể nằm ở **output.value** thay vì firstRow.

### 15.1. Lookup watermark

Ví dụ SQL cho Lookup:

~~~sql
SELECT LastWatermarkUtc
FROM dbo.EtlWatermark
WHERE PipelineName = 'pl_orders_incremental';
~~~

### 15.2. Lookup upper bound

Nếu chỉ minh họa timestamp từ nguồn:

~~~sql
SELECT SYSUTCDATETIME() AS UpperWatermarkUtc;
~~~

Với data correctness nghiêm ngặt, upper nên dựa trên **CT/CDC version, snapshot/commit sequence** hoặc có safety policy như đã nêu, không mặc định wall-clock upper là không thể bỏ sót.

### 15.3. Dynamic SQL an toàn

ADF có các biểu thức **@concat(...)** để tạo SQL text. Nhưng nối input vào SQL dễ tạo lỗi quote/injection, đặc biệt với dynamic schema/table names. Ưu tiên nguồn parameterized query hoặc stored procedure có typed parameters nếu connector hỗ trợ. Với table names động từ metadata, chỉ dùng allowlist nội bộ đáng tin.
## 16. Một ví dụ pipeline có parameters và activity dependencies

Trong ADF Studio, tạo pipeline **pl_orders_incremental** với các activities theo thứ tự:

~~~text
LookupWatermark
       |
LookupUpper
       |
CopyOrdersToStage
       |
ValidateStage
       |
ApplyOrdersAndCommitWatermark
       |
NotifySuccess
~~~

Một fragment JSON minh họa **pipeline parameter** (không phải toàn bộ ARM template có thể deploy):

~~~json
{
  "name": "pl_orders_incremental",
  "properties": {
    "parameters": {
      "sourceTable": {
        "type": "String",
        "defaultValue": "dbo.Orders"
      },
      "runMode": {
        "type": "String",
        "defaultValue": "incremental"
      }
    }
  }
}
~~~

Với những resources thực, **activity JSON còn phải có linked services, datasets, source/sink types, policies và dependencies**. Cấu trúc trên chỉ cho thấy cách truyền parameters.

### 16.1. Lookup output

Lookup SQL:

~~~sql
SELECT LastWatermarkUtc
FROM dbo.EtlWatermark
WHERE PipelineName = 'pl_orders_incremental';
~~~

Sau chạy thành công, tham chiếu:

~~~text
@activity('LookupWatermark').output.firstRow.LastWatermarkUtc
~~~

Nếu Lookup trả về zero rows, expression sẽ không có thuộc tính firstRow mong đợi. Cần khởi tạo control record hoặc có nhánh xử lý **no watermark** thay vì để pipeline lỗi khó hiểu.

### 16.2. Chốt upper một lần

Upper boundary phải được tính **một lần cho một run** và lưu trong run metadata. Không tính lại upper sau khi Copy fail rồi chạy lại một phần vì có thể tạo cửa sổ khác.

### 16.3. Truyền runId xuống các bước

Dùng:

~~~text
@pipeline().RunId
~~~

Đưa runId vào staging, audit log, file path hoặc stored procedure parameters. Khi ADF retry một **activity trong cùng pipeline run**, runId thường giữ nguyên; một pipeline run mới/backfill có runId mới, cần vẫn idempotent theo business key và window.

### 16.4. Dependencies

Mỗi activity cần cấu hình **Succeeded, Failed, Skipped, Completed** theo quy tắc control flow ADF. Ví dụ **ApplyOrdersAndCommitWatermark chỉ chạy khi ValidateStage Succeeded**, không chỉ vì Copy activity đã Completed.

## 17. SQL staging table cho incremental load

Ví dụ staging trên Azure SQL Database:

~~~sql
CREATE TABLE dbo.OrdersStage (
    RunId          nvarchar(100) NOT NULL,
    OrderId        bigint NOT NULL,
    CustomerId     bigint NOT NULL,
    Status         nvarchar(30) NOT NULL,
    Amount         decimal(18,2) NOT NULL,
    ModifiedAtUtc  datetime2(7) NOT NULL,
    CONSTRAINT PK_OrdersStage
        PRIMARY KEY (RunId, OrderId)
);

CREATE TABLE dbo.OrdersCurrent (
    OrderId        bigint NOT NULL PRIMARY KEY,
    CustomerId     bigint NOT NULL,
    Status         nvarchar(30) NOT NULL,
    Amount         decimal(18,2) NOT NULL,
    ModifiedAtUtc  datetime2(7) NOT NULL
);
~~~

**Giả định của ví dụ:** mỗi OrderId có một bản hiện hành trong cửa sổ. Nếu source là log nhiều versions của cùng OrderId, phải chọn bản cuối theo commit version/business rule trước khi load vào staging có primary key (RunId, OrderId).

### 17.1. Vì sao có RunId?

- Xác định rõ dữ liệu thuộc lần chạy nào.
- Kiểm tra đích trước khi apply.
- Tránh một run lỗi trộn dữ liệu với run khác.
- Hỗ trợ retry, diagnostics và cleanup sau retention.

### 17.2. Cơ chế rerun staging

Trước khi Copy vào staging, có thể **DELETE FROM dbo.OrdersStage WHERE RunId = @RunId** trong một activity có kiểm soát, hoặc dùng một staging area riêng cho attempt. Không bao giờ TRUNCATE bảng staging dùng chung giữa nhiều runs mà không có serialization.

### 17.3. RunId và attempt

Một số nền tảng có **activity retry** không thay đổi pipeline RunId nhưng có thể copy lại các rows đã ghi một phần. Cần dọn dữ liệu stage của **attempt đó** trước retry hoặc dùng idempotent staging sink. Không cho Copy ghi duplicate vào bảng có primary key rồi giả định retry tự sửa.

## 18. Áp dụng delta bằng upsert có điều kiện

Định nghĩa **upsert idempotent**: chạy cùng một delta nhiều lần phải cho kết quả cuối giống như một lần, theo business ordering được xác định.

Với SQL Server/Azure SQL, có thể dùng UPDATE sau đó INSERT trong transaction. Ví dụ đơn giản:

~~~sql
DECLARE @RunId nvarchar(100) = N'RUN-DEMO-001';

BEGIN TRANSACTION;

UPDATE target
SET target.CustomerId = stage.CustomerId,
    target.Status = stage.Status,
    target.Amount = stage.Amount,
    target.ModifiedAtUtc = stage.ModifiedAtUtc
FROM dbo.OrdersCurrent AS target
JOIN dbo.OrdersStage AS stage
  ON stage.OrderId = target.OrderId
WHERE stage.RunId = @RunId
  AND stage.ModifiedAtUtc >= target.ModifiedAtUtc;

INSERT INTO dbo.OrdersCurrent (
    OrderId, CustomerId, Status, Amount, ModifiedAtUtc
)
SELECT stage.OrderId,
       stage.CustomerId,
       stage.Status,
       stage.Amount,
       stage.ModifiedAtUtc
FROM dbo.OrdersStage AS stage
WHERE stage.RunId = @RunId
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.OrdersCurrent AS target WITH (UPDLOCK, HOLDLOCK)
      WHERE target.OrderId = stage.OrderId
  );

COMMIT TRANSACTION;
~~~

**Chỉ chạy trên bảng lab.** Trong production, đóng gói trong stored procedure với **TRY/CATCH, XACT_ABORT, transaction isolation/locking policy, validation, versioning và error logging** đã được kiểm thử.

### 18.1. Vì sao có ModifiedAtUtc comparison?

Nếu một run cũ được replay sau một run mới, nó không nên ghi đè row hiện hành bằng version cũ. Nhưng timestamp không luôn là một version hoàn hảo; nếu có **source change sequence/rowversion/aggregateVersion** đáng tin, ưu tiên nó để xác định thứ tự trạng thái.

### 18.2. MERGE là lựa chọn, không phải phép màu

T-SQL có lệnh **MERGE** nhưng cần xem kỹ concurrency, duplicate sources và behavior của version SQL. Không giả định một câu MERGE không có khóa/transaction đã idempotent và an toàn ở mọi tải.

### 18.3. INSERT thuần có thể đủ khi dữ liệu append-only

Nếu mỗi source event luôn mới và không cần UPDATE/DELETE, sink có thể append với unique key chống duplicate. Đừng làm pipeline phức tạp nếu contract thực sự append-only.

## 19. Cập nhật watermark trong cùng transaction khi có thể

Khi bảng đích và bảng watermark **cùng Azure SQL Database**, một stored procedure có thể áp dụng delta rồi nâng watermark trong **cùng database transaction**.

Pseudo-code T-SQL minh họa cơ chế:

~~~sql
CREATE OR ALTER PROCEDURE dbo.usp_CommitOrderWindow
    @RunId nvarchar(100),
    @PipelineName nvarchar(200),
    @ExpectedOldUtc datetime2(7),
    @UpperUtc datetime2(7)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        DECLARE @ActualOldUtc datetime2(7);

        SELECT @ActualOldUtc = LastWatermarkUtc
        FROM dbo.EtlWatermark WITH (UPDLOCK, HOLDLOCK)
        WHERE PipelineName = @PipelineName;

        IF @ActualOldUtc IS NULL
           OR @ActualOldUtc <> @ExpectedOldUtc
        BEGIN
            THROW 51000,
                  'Watermark changed or not initialized',
                  1;
        END;

        -- Thực hiện idempotent upsert từ OrdersStage
        -- theo @RunId vào OrdersCurrent tại đây.
        -- Validate row count/business constraints trước khi commit.

        UPDATE dbo.EtlWatermark
        SET LastWatermarkUtc = @UpperUtc,
            UpdatedAtUtc = SYSUTCDATETIME()
        WHERE PipelineName = @PipelineName;

        UPDATE dbo.EtlRunLog
        SET Status = N'SUCCEEDED',
            CompletedAtUtc = SYSUTCDATETIME()
        WHERE RunId = @RunId;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
~~~

**Rất quan trọng:** procedure ở trên là **khung minh họa**, chưa có đoạn SQL thực hiện upsert và validation. Không dùng nguyên mẫu để nâng watermark trong production: cần chèn và kiểm thử thao tác apply thực trong transaction trước khi cho phép câu UPDATE watermark.

### 19.1. Khi control database và sink khác nhau

Không có atomic transaction tự động giữa:

- Copy file vào ADLS.
- Upsert vào một Azure SQL database.
- Update watermark ở một database khác.
- Publish message qua Service Bus.

Trong topology này, thiết kế theo **at-least-once + idempotent sink**:

1. Copy/apply durable.
2. Validate.
3. Chỉ sau thành công mới nâng watermark.
4. Nếu watermark update fail, rerun cùng window sẽ copy lại; upsert/dedup bảo đảm không nhân đôi.
5. Dùng manifest/commit marker cho các sink file nếu cần.

### 19.2. Watermark không phải cách duy nhất để đảm bảo không bỏ sót

Một watermark chính xác vẫn phụ thuộc nguồn có cung cấp change signal đáng tin. Nếu source timestamp sai/late, transaction apply hoàn hảo vẫn có thể không thấy row cần lấy.

## 20. Validation: không chỉ đếm rowsCopied

Copy activity có metrics như **rowsRead**, **rowsCopied**, bytes và duration theo connector/output. Chúng giúp quan sát nhưng chưa chứng minh dữ liệu đúng nghiệp vụ.

Các kiểm tra có thể gồm:

- Source row count của cửa sổ so với staging count.
- Unique OrderId trong run.
- Không có null trong các cột bắt buộc.
- Không có Amount âm nếu business rule cấm.
- Schema/version nằm trong danh sách hỗ trợ.
- Dữ liệu đích không có OrderId trùng.
- Phân phối theo status/tenant phù hợp.
- Tổng tiền hoặc checksum theo partition/cửa sổ nếu có cách đo đáng tin.
- Dữ liệu UPDATE/DELETE đã được phản ánh theo contract.
- Một số key mẫu được đối chiếu trực tiếp.

### 20.1. Count source không luôn ổn định

Nếu source thay đổi trong lúc Copy, một câu COUNT trước Copy và query Copy có thể nhìn hai snapshots khác nhau. Với yêu cầu đối chiếu chặt, cần thống nhất snapshot/isolation hoặc dùng CDC/change window và version.

### 20.2. Count 0 không mặc định là lỗi

Một giờ không có thay đổi có thể tạo **zero-row delta** hợp lệ. Pipeline cần phân biệt không có dữ liệu với lỗi đọc nguồn hoặc phạm vi bị tính sai.

### 20.3. Data quality failures không được nâng watermark

Nếu copy 1.000 rows nhưng 100 rows invalid và chưa được xử lý theo chính sách quarantine, không nên nâng watermark qua toàn bộ cửa sổ nếu làm mất khả năng xử lý lại.

## 21. SQL Change Tracking: incremental theo version

**SQL Server/Azure SQL Change Tracking** (nơi hỗ trợ và đã bật) ghi dấu **những primary keys nào thay đổi** kể từ một change version. Nó hữu ích khi bảng mutable có INSERT, UPDATE và DELETE mà timestamp không đủ tin cậy.

Ý tưởng:

~~~sql
SELECT CHANGE_TRACKING_CURRENT_VERSION()
    AS UpperVersion;
~~~

Lấy những key thay đổi kể từ last version:

~~~sql
SELECT
    CT.OrderId,
    CT.SYS_CHANGE_VERSION,
    CT.SYS_CHANGE_OPERATION,
    S.CustomerId,
    S.Status,
    S.Amount,
    S.ModifiedAtUtc
FROM CHANGETABLE(
    CHANGES dbo.Orders, @LastVersion
) AS CT
LEFT JOIN dbo.Orders AS S
    ON S.OrderId = CT.OrderId
WHERE CT.SYS_CHANGE_VERSION <= @UpperVersion;
~~~

**Đây là pattern minh họa**, phải bảo đảm CT đã bật và có permission; câu query chỉ phản ánh trạng thái row hiện tại khi join, không cung cấp mọi phiên bản trung gian. Với source còn thay đổi trong lúc đọc, cần dùng snapshot isolation hoặc cơ chế consistency phù hợp.

### 21.1. Xử lý DELETE

Với **SYS_CHANGE_OPERATION = 'D'**, row hiện hành trong bảng nguồn có thể không còn; dùng tombstone hoặc delete operation theo contract ở sink.

### 21.2. Retention và min valid version

CT có retention và cleanup. Trước khi đọc, kiểm tra:

~~~sql
SELECT CHANGE_TRACKING_MIN_VALID_VERSION(
    OBJECT_ID('dbo.Orders')
) AS MinValidVersion;
~~~

Nếu checkpoint version đã **cũ hơn min valid version**, một số changes có thể đã bị cleanup. Phải reinitialize/full resync theo kế hoạch, **không tự nâng version rồi bỏ qua lịch sử**.

### 21.3. CT không phải full event history

CT thường cho biết row nào đã thay đổi, không chứa mọi before/after state của từng transaction như CDC log. Chọn CT khi cần current-state replication và biết rõ giới hạn.

## 22. Change Data Capture (CDC): nắm bắt INSERT, UPDATE, DELETE

**CDC** ghi nhận các thay đổi từ transaction log theo cơ chế hỗ trợ của nguồn. Nó phù hợp khi cần:

- Theo dõi DELETE.
- Giữ nhiều changes giữa hai lần chạy.
- Dùng log sequence/checkpoint thay vì timestamp của ứng dụng.
- Xây dựng downstream changes stream hoặc history.
- Đảm bảo thứ tự trong phạm vi log semantics được hỗ trợ.

### 22.1. Khái niệm LSN

**Log Sequence Number (LSN)** là mốc vị trí log được dùng trong một số giải pháp CDC SQL Server. Cửa sổ đọc incremental cần thiết kế ranh giới LSN đúng, tránh overlap hoặc gaps do inclusive/exclusive semantics riêng của hàm CDC.

### 22.2. Đừng nhầm CDC với tên một activity

Một số dịch vụ/connector cung cấp native CDC/managed pipelines trong những điều kiện cụ thể; trường hợp khác phải dùng change tables/log connector/engine. **Không phải cứ chọn Copy activity là tự có CDC**. Cần xác nhận connector, source version, permissions và retention.

### 22.3. Các điều kiện vận hành

- Log/change retention lớn hơn outage/backlog cần phục hồi.
- Có quyền đọc change tables/log.
- Có cơ chế schema evolution.
- Có checkpoint commit-based.
- Consumer áp dụng changes idempotent và theo thứ tự phù hợp.
- Có quy trình reinitialization khi mất retention window.

### 22.4. Chọn watermark, CT hay CDC?

| Nhu cầu | Gợi ý |
|---|---|
| Append-only đơn giản | ID/timestamp có semantics rõ |
| Bảng mutable nhỏ, dễ reconciliation | ModifiedAtUtc + overlap/idempotent upsert có kiểm tra |
| Current-state replication SQL | Change Tracking |
| Audit/history có INSERT/UPDATE/DELETE | CDC/log-based mechanism |
| Source không có change signal | Periodic full/snapshot-diff theo capacity |

Không chọn CDC chỉ vì nghe “chuyên nghiệp”; mỗi phương án có chi phí và độ phức tạp vận hành riêng.

## 23. Xử lý DELETE và tombstone

Một pipeline chỉ copy rows đang tồn tại không thể tự biết row nào đã bị xóa khỏi nguồn.

Ví dụ:

~~~text
Source 09:00: OrderId=1001 tồn tại
Source 09:30: OrderId=1001 bị DELETE

Copy incremental theo ModifiedAt:
    Không có row 1001 để sao chép
    -> Sink giữ 1001 mãi
~~~

Cách xử lý:

- Dùng **soft delete**: cột IsDeleted/DeletedAt được cập nhật và đưa vào incremental.
- Dùng **CT/CDC** có delete markers.
- Dùng periodic full reconciliation/diff cho dataset đủ nhỏ.
- Dùng tombstone events từ domain service.

### 23.1. Soft delete ví dụ

~~~sql
UPDATE dbo.Orders
SET IsDeleted = 1,
    ModifiedAtUtc = SYSUTCDATETIME()
WHERE OrderId = 1001;
~~~

Chỉ thực hiện nếu source schema có cột IsDeleted và nghiệp vụ đã chấp nhận soft delete. Nếu chưa, câu SQL chỉ là minh họa, không chạy trực tiếp.

### 23.2. Chọn chính sách sink

- Hard delete trên mirror table.
- Soft delete ở sink.
- Lưu lịch sử event/tombstone và tính current state sau.
- Giữ retained data theo compliance khi cần.

Cần thống nhất quy tắc xóa dữ liệu với chủ sở hữu dữ liệu và quy định lưu trữ.

## 24. Pipeline orchestration là gì?

**Orchestration** là điều phối các activities theo dependencies và điều kiện, xử lý timeout/retry, truyền parameters, ghi run trạng thái, thực hiện các nhánh success/failure, kiểm soát concurrency và trigger lịch chạy.

Ví dụ:

~~~mermaid
flowchart TD
    START[Schedule/tumbling trigger] --> P[Prepare run]
    P --> L[Lookup watermark]
    L --> C[Copy delta]
    C --> V{Validation passed?}
    V -->|Yes| A[Apply delta]
    V -->|No| F[Record failure and alert]
    A --> W[Commit watermark]
    W --> S[Audit success]
    C -. Failure .-> F
    A -. Failure .-> F
    W -. Failure .-> F
~~~

### 24.1. Pipeline là DAG có nhánh

ADF pipeline có control-flow graph với dependencies, ForEach/Until và branching; không phải mọi bước là một script SQL tuần tự.

### 24.2. Thành công của activity và thành công của pipeline

Nếu cấu hình Failure branch rồi activity cuối trong failure branch trả Succeeded, pipeline status tổng thể có thể khác kỳ vọng tùy dependency graph. Đảm bảo error-handling branch **fail pipeline** hoặc báo trạng thái thất bại rõ ràng khi business load chưa hoàn tất, không che lỗi.

### 24.3. Không dùng pipeline variable như distributed lock

Variables là trạng thái trong pipeline run, không phải một database lock có tính toàn cục để ngăn hai runs cùng ghi. Cần điều phối concurrency hoặc control store atomic claim.

## 25. Lookup, Get Metadata và Stored Procedure activities

| Activity | Dùng để | Ví dụ |
|---|---|---|
| **Lookup** | Đọc kết quả query/config nhỏ | LastWatermarkUtc |
| **Get Metadata** | Lấy file/field metadata từ datasets | File exists, list of child items |
| **Copy** | Truyền dữ liệu | SQL delta đến staging |
| **Stored Procedure** | Chạy stored proc SQL trên connector phù hợp | Apply delta/commit progress |
| **Script** | Thực thi SQL scripts trên connector được hỗ trợ | Control table/update/validation |
| **If Condition** | Rẽ nhánh | rowsCopied > 0 |
| **Set Variable** | Ghi trạng thái tạm | currentBatchIndex |
| **Execute Pipeline** | Gọi pipeline con | pl_load_one_table |
| **Web** | Gọi HTTP endpoint | Alert đến approved webhook |

### 25.1. Lookup không dùng để tải hàng triệu rows

Lookup hướng tới metadata/small result sets; có giới hạn output và timeout tùy dịch vụ. Đọc dữ liệu lớn bằng Copy activity hoặc compute engine phù hợp.

### 25.2. Get Metadata liệt kê file có giới hạn

Nếu folder có lượng file rất lớn, Get Metadata có thể bị giới hạn output/chi phí. Cân nhắc partitioned folder layout, file manifest hoặc event-driven ingest thay vì scan toàn bộ filesystem mỗi lần.

### 25.3. Stored Procedure phải có quyền

Data Factory connected identity cần EXECUTE và những quyền mà procedure yêu cầu theo mô hình security. Không cấp db_owner khi chỉ cần một procedure cụ thể nếu có phương án phù hợp.

## 26. If Condition và xử lý zero-row delta

Giả sử Copy trả output **rowsCopied** (field có thể khác theo connector/kiểu copy). Có thể dùng dynamic expression:

~~~text
@greater(activity('CopyOrdersToStage').output.rowsCopied, 0)
~~~

Trong ADF, dùng If Condition:

- **True**: chạy validate/apply nếu có dữ liệu.
- **False**: có thể skip apply rows, nhưng vẫn cần logic cập nhật watermark an toàn nếu đã xác nhận source không có delta và cửa sổ hợp lệ.

**Zero rows là dữ liệu hợp lệ** nếu nguồn thực sự không thay đổi. Tuy nhiên, zero rows do query sai, permission bị lọc, dynamic path sai hoặc source read lỗi không được coi là thành công nghiệp vụ.

### 26.1. Không dùng rowsCopied làm watermark

rowsCopied là số lượng rows đã copy, không biểu diễn **vị trí dữ liệu đã xử lý**. Watermark cần mốc timestamp/sequence/LSN/ID phù hợp.

### 26.2. Output field phải được kiểm tra

Trước khi viết expression cố định, chạy test và xem **Activity Output JSON**. Các connector có output shape khác nhau; expression dùng field không tồn tại sẽ gây lỗi runtime.

## 27. ForEach và metadata-driven pipelines

Một data platform thường có nhiều bảng:

~~~text
dbo.Orders
dbo.Customers
dbo.Products
dbo.Payments
~~~

Thay vì copy-paste bốn pipelines gần giống, có thể tạo **metadata/control table**:

~~~sql
CREATE TABLE dbo.EtlTableConfig (
    SourceSchema    sysname NOT NULL,
    SourceTable     sysname NOT NULL,
    SinkTable       sysname NOT NULL,
    WatermarkColumn sysname NULL,
    IsEnabled       bit NOT NULL,
    PRIMARY KEY (SourceSchema, SourceTable)
);
~~~

Pipeline cha dùng Lookup lấy danh sách bảng, **ForEach** lặp và gọi pipeline con **pl_load_one_table** với parameters.

### 27.1. Parameter hóa an toàn

Tên schema/table/column phải lấy từ allowlist nội bộ được kiểm duyệt. Nếu dựng SQL động, quote identifiers bằng công cụ SQL phù hợp và không nhận giá trị tự do từ HTTP user input.

### 27.2. Parallel ForEach và variables

Khi ForEach chạy song song, không dùng một pipeline variable chia sẻ để giữ watermark hoặc run result riêng từng bảng mà không kiểm soát. Variables có thể bị cập nhật cạnh tranh. **Truyền parameters và lưu trạng thái theo từng table trong control DB** thường an toàn hơn.

### 27.3. Concurrency và batchCount

ForEach có cơ chế parallel/sequential và giới hạn đồng thời theo dịch vụ. Chọn mức song song dựa trên tài nguyên nguồn/đích, không đặt thật cao theo cảm tính. Tăng concurrency có thể làm SQL Server on-prem quá tải hoặc sink database thiếu capacity.

### 27.4. Failure isolation

Nếu một bảng lỗi, cần quyết định:

- Fail toàn pipeline cha.
- Ghi lỗi từng bảng rồi tiếp tục các bảng độc lập.
- Retry bảng lỗi sau.
- Ngăn downstream gold transform chỉ khi dependency table cần thiết đã thành công.

Trạng thái run phải phân biệt partial success với full success.

## 28. Execute Pipeline và phân tầng orchestration

Một cấu trúc dễ vận hành:

~~~text
pl_daily_analytics
  |
  +-- pl_ingest_orders
  +-- pl_ingest_customers
  +-- pl_ingest_products
  |
  +-- pl_validate_curated
  |
  +-- pl_build_marts
  |
  +-- pl_publish_reporting
~~~

Có thể dùng **Execute Pipeline** để gọi pipelines con với parameters. Tùy nhu cầu, chờ child completion trước khi chạy bước downstream.

### 28.1. Không đánh đồng run cha thành công với tất cả con thành công

Nếu Execute Pipeline không chờ child completion hoặc failure branch không propagate error đúng, pipeline cha có thể hoàn tất trước khi dữ liệu báo cáo đã sẵn sàng. Thiết lập wait và dependency semantics đúng.

### 28.2. Idempotency theo từng lớp

- Ingest idempotent theo source keys và windows.
- Curated merge idempotent theo versions.
- Mart publish có version/batch marker.
- Downstream consumers không đọc dữ liệu chưa được publish/validated.

### 28.3. Tách concerns

Pipeline ingest nên chịu trách nhiệm capture và lưu raw/stage. Pipeline transform chịu quality/business mapping. Pipeline publish kiểm soát dữ liệu sẵn sàng cho người dùng. Không nhồi tất cả business logic vào một Copy expression khó kiểm thử.

## 29. Schedule triggers: chạy theo lịch

**Schedule trigger** chạy pipeline theo lịch/cadence định nghĩa, ví dụ mỗi giờ.

~~~text
00:00  Pipeline run A
01:00  Pipeline run B
02:00  Pipeline run C
~~~

### 29.1. Rủi ro khi run kéo dài hơn chu kỳ

Nếu run A mất 90 phút, run B có thể bắt đầu trước khi A hoàn tất nếu concurrency không được giới hạn. Hai runs cùng watermark có thể tranh/ghi đè dữ liệu.

Biện pháp:

- Đặt pipeline **concurrency** theo yêu cầu (ví dụ 1 khi chỉ một stream tuần tự).
- Dùng control-table claim/lock nếu cần đảm bảo ngay cả khi có manual reruns hoặc pipelines khác.
- Có cơ chế queue/backlog nếu throughput không đủ.
- Không bỏ qua một chu kỳ mà không biết cách catch up.

### 29.2. Timezone và DST

Lịch theo local timezone có thể gặp DST ở những vùng áp dụng. Với pipeline window dễ kiểm soát, chuẩn hóa timestamps và watermark bằng **UTC**, sau đó chuyển sang timezone nghiệp vụ ở lớp báo cáo.

### 29.3. Schedule không phải commit checkpoint

Sự kiện trigger xảy ra đúng giờ không chứng minh data source có dữ liệu đến đúng giờ hoặc lần chạy trước đã thành công. Watermark cần độc lập với trigger cadence.

## 30. Tumbling window triggers: xử lý cửa sổ có trạng thái

**Tumbling window trigger** biểu diễn các khoảng thời gian liên tục, có ranh giới và hỗ trợ mô hình stateful windows/backfill/dependencies theo khả năng dịch vụ.

Ví dụ cửa sổ nửa giờ:

~~~text
[00:00, 00:30)
[00:30, 01:00)
[01:00, 01:30)
[01:30, 02:00)
~~~

Khi thiết kế query, có thể chọn predicate **>= start AND < end** để khớp trực tiếp với half-open windows. Đây là quy ước khác với watermark pattern **(last, upper]** nhưng cả hai đều hợp lệ nếu **nhất quán** và không bỏ/nhân đôi ở ranh giới.

### 30.1. Cần định nghĩa rõ boundary convention

- Tumbling window thông thường: **[start, end)**.
- Last watermark high-water pattern: **(last, upper]**.
- Không trộn lẫn hai conventions mà không kiểm tra timestamps ở ranh giới.

### 30.2. Backfill

Tumbling window cho phép vận hành và reprocess các cửa sổ lịch sử trong phạm vi hỗ trợ. Tuy nhiên, **backfill chỉ an toàn nếu sink idempotent**, có tracking theo window và tôn trọng data retention của nguồn.

### 30.3. Dependency theo window

Có thể thiết kế cửa sổ downstream đợi dependency window upstream hoàn thành theo tính năng trigger. Không nhầm việc schedule start với việc pipeline downstream đã có dữ liệu sạch.

### 30.4. Trigger window chưa giải quyết late commits

Nếu source ghi dữ liệu chậm vào một event-time window đã đóng, vẫn cần data arrival policy, overlap, CT/CDC hoặc reconciliation.
## 31. Storage event trigger: chạy khi file xuất hiện

Với nguồn file trên Azure Storage được hỗ trợ, có thể dùng **storage event trigger** dựa trên Event Grid để khởi chạy pipeline khi file được tạo/sự kiện phù hợp.

Ví dụ:

~~~text
Producer upload file -> ADLS container
     |
     v
BlobCreated event
     |
     v
ADF storage event trigger
     |
     v
Pipeline validate/copy/process file
~~~

### 31.1. Không đồng nghĩa đúng một lần

Event-driven systems có thể nhận duplicate notifications hoặc file được xử lý lại do retry. Dùng **file ID/path + ETag/version/run manifest** làm idempotency key theo connector và tính năng, không dựa vào “mỗi file chỉ phát một event”.

### 31.2. File đã sẵn sàng chưa?

Với multipart upload hoặc quy trình copy từ hệ thống ngoài, cần định nghĩa cách xác nhận file hoàn tất:

- Tải vào đường dẫn tạm rồi publish/rename/commit marker.
- Có file manifest chứa danh sách/tổng số files.
- Chỉ trigger khi producer gửi sự kiện hoàn tất hoặc dấu hiệu mà dịch vụ bảo đảm.
- Kiểm tra file size/schema/row count trước khi apply.

Không mặc định event trigger có thể giải thích mọi lifecycle state của producer tùy ý.

### 31.3. Khi nào không dùng event trigger?

Nếu cần ingest theo cửa sổ cố định có dữ liệu tổng hợp từ nhiều files đến không đồng thời, tumbling window/schedule + manifest có thể phù hợp hơn.

## 32. Timeout, retry và error handling

ADF activities có **policy retry, retryInterval, timeout** theo loại activity và cấu hình. Retry giúp vượt một số lỗi tạm thời, nhưng có thể tạo duplicate writes nếu sink không idempotent.

### 32.1. Phân loại lỗi

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Transient | HTTP 429/503, network timeout, throttling Azure SQL | Bounded retry + backoff, kiểm tra năng lực |
| Authentication | Credential expired, wrong managed identity | Sửa quyền/secret, không retry vô hạn |
| Authorization | SQL permission denied, ADLS ACL 403 | Kiểm tra data-plane permissions |
| Data/schema | Type conversion, missing column, invalid JSON | Validate/quarantine, sửa mapping |
| Data correctness | Duplicate key, incorrect watermark, row count mismatch | Dừng commit, điều tra/idempotent rerun |
| Capacity | SHIR CPU cao, SQL DTU/vCore saturation | Giảm concurrency, scale hoặc đổi schedule |
| Source retention | CDC/CT checkpoint quá cũ | Reinitialize/resync có kiểm soát |

### 32.2. Retry và duplicate

Một Copy đã ghi một phần dữ liệu rồi gặp network timeout. Nếu activity được retry và sink write mode là **append**, có thể có bản ghi/file trùng. Cần:

- Stage theo run/attempt.
- Clean stage của attempt trước khi retry hoặc dùng deterministic output names/overwrite có kiểm soát.
- Upsert/dedup bằng business key ở bước apply.
- Bảo vệ watermark đến sau durable commit.

### 32.3. Timeout không bảo đảm rollback sink

Activity timeout/cancel không phải database transaction rollback xuyên source, IR và sink. Sau timeout phải kiểm tra đích đã ghi gì trước khi rerun.

### 32.4. Failure branch

Ghi log lỗi, gửi alert và giữ watermark. Đảm bảo pipeline trả trạng thái thất bại rõ; nếu xử lý lỗi xong nhưng pipeline đánh dấu Succeeded, monitoring có thể không gọi on-call.

## 33. Idempotency khi chạy lại pipeline

**Idempotency** nghĩa là cùng một window/run được xử lý nhiều lần mà bảng đích và các side effects cuối cùng vẫn đúng.

Ví dụ:

~~~text
Run A:
  Copy 1.000 rows thành công
  Apply 1.000 rows thành công
  Update watermark lỗi
  -> Pipeline Failed

Run B:
  Đọc watermark cũ
  Copy lại 1.000 rows
  Apply idempotent
  Watermark commit
  -> Pipeline Succeeded
~~~

Nếu sink chỉ append không có dedup, Run B sẽ tạo 2.000 rows. Nếu sink upsert theo OrderId + version, kết quả cuối vẫn đúng.

### 33.1. Kỹ thuật

- Business key/unique constraint.
- Upsert/replace theo version đáng tin.
- Manifest hoặc commit marker cho batch files.
- Định danh window, run và source change sequence.
- Atomic transaction cho apply + watermark khi trong cùng database.
- Test fail ở mọi ranh giới hoạt động.

### 33.2. Không đồng nghĩa exactly-once end-to-end

ADF Copy activity + pipeline control flow không tự tạo ACID transaction xuyên hai services. Có thể đạt **effectively-once business result** bằng idempotent sink, nhưng phải chứng minh qua kiểm thử.

### 33.3. Delete, events và side effects

Nếu pipeline sau khi copy còn gửi một email hoặc phát Service Bus message, rerun có thể phát lại. Dùng outbox, dedup message key hoặc downstream idempotency.

## 34. Concurrency: giữa các runs và giữa các bảng

Có ít nhất ba mức concurrency:

1. **Pipeline-run concurrency**: bao nhiêu lần chạy đồng thời của cùng pipeline.
2. **ForEach parallelism**: bao nhiêu bảng/nhánh chạy cùng lúc.
3. **Copy internal parallelism**: bao nhiêu phân vùng luồng copy/DIUs theo connector.

Nếu cả ba đều lớn, nguồn SQL và sink có thể bị áp lực vượt dự kiến.

### 34.1. Ví dụ rủi ro

~~~text
Pipeline concurrency: 2 runs
ForEach: 10 tables concurrently
Mỗi Copy: nhiều reader/writer parallel tasks

Tổng tải đến SQL có thể lớn hơn rất nhiều
so với khi chỉ nhìn "10 tables".
~~~

### 34.2. Kế hoạch giới hạn

- Một pipeline incremental serial theo bảng nếu dùng chung watermark.
- Bảng độc lập có thể song song nhưng có batchCount phù hợp.
- Tách workload batch nặng khỏi giờ cao điểm của OLTP.
- Giới hạn max connections/queries trên source.
- Giám sát queue time của SHIR, source CPU, SQL waits và ADLS throughput.
- Điều phối load theo priority/SLO khi có nhiều nhóm cùng ingest.

### 34.3. Không chỉ tối ưu copy throughput

Nếu ingestion nhanh làm ứng dụng giao dịch bị nghẽn, giải pháp không đạt yêu cầu tổng thể. Đặt SLO cho cả source OLTP và analytics availability.

## 35. Performance tuning của Copy activity

Đo trước khi tối ưu:

- Data read throughput và write throughput.
- Rows/bytes read/copied.
- Source query execution time.
- IR provisioning/queueing time.
- Network transfer duration.
- Sink staging/commit duration.
- Số parallel readers/writers.
- Throughput capacity của Azure SQL/ADLS.
- SQL locks, DTU/vCore, I/O và SHIR health.

### 35.1. Source partitioned reads

Một số SQL connectors hỗ trợ partitioned copy/read theo range hoặc physical partition. Cách này có thể tăng throughput trên bảng lớn nhưng tạo nhiều concurrent queries.

Cần kiểm tra:

- Index trên partition key/read range.
- Các ranges không trùng/không hở.
- Snapshot/read consistency.
- Source chịu được parallel scans.
- Network/IR có đủ capacity.

### 35.2. Sink bulk ingestion

Một số relational sinks hỗ trợ batch size, write behavior hoặc native bulk mechanisms. Giá trị lớn quá có thể tăng lock, transaction log pressure hoặc timeout.

### 35.3. Compression và file size

Với ADLS Parquet, phân vùng theo ngày/hệ thống hoặc key phù hợp. Tránh tạo hàng triệu files rất nhỏ vì file listing, metadata operations và downstream scans sẽ tốn kém.

### 35.4. Chạy thử tải có kiểm soát

Benchmark với dữ liệu tương tự production, đo end-to-end throughput và ảnh hưởng nguồn. Không chỉ tăng DIUs/parallelCopies đến tối đa mà bỏ qua cost và source latency.

## 36. Schema drift, mapping và data contracts

Nguồn có thể thêm, đổi tên hoặc thay kiểu một cột. Pipeline không có data contract sẽ dễ:

- Copy lỗi conversion.
- Bỏ qua cột mới không mong muốn.
- Đẩy dữ liệu vào sai cột.
- Ghi null âm thầm.
- Làm hỏng downstream marts.

### 36.1. Tách ba loại thay đổi

| Thay đổi | Ví dụ | Cách ứng xử |
|---|---|---|
| Backward-compatible | Thêm cột nullable | Cập nhật mapping theo quy trình |
| Breaking | Đổi CustomerId bigint sang string semantics khác | Migration plan/schema version |
| Dữ liệu sai | Amount chứa text không chuyển được | Quarantine hoặc fail validation |

### 36.2. Explicit mapping và validation

Với hệ thống quan trọng, dùng mapping rõ ràng, test conversion theo từng cột và kiểm tra schema version. Mapping tự động tiện cho lab nhưng có thể che lỗi khi nguồn thay cấu trúc.

### 36.3. Parquet/JSON không tự sửa logical schema drift

Định dạng file linh hoạt hơn một số trường hợp, nhưng downstream SQL/analytics vẫn cần hiểu kiểu dữ liệu, các trường mandatory và quy tắc versioning.

### 36.4. Data contract ownership

Mỗi source table/stream nên có owner, mô tả PK, watermark semantics, delete policy, timezone, SLAs và quy trình thông báo breaking changes.

## 37. Monitoring pipeline và Copy activity

ADF Monitor và Azure Monitor có thể cung cấp trạng thái pipeline/activity, duration, errors và số liệu Copy theo connector. Ứng dụng cần bổ sung **business/data-quality metrics** riêng.

| Nhóm | Metric/điểm kiểm tra | Ý nghĩa |
|---|---|---|
| Scheduling | Trigger fires, start delay | Pipeline chạy đúng cadence? |
| Pipeline state | Succeeded/Failed/Cancelled | Có lỗi điều phối? |
| Copy | Rows read/copied, throughput, duration | Truyền dữ liệu hiệu quả? |
| Data completeness | Source/destination counts, hash, missing keys | Có bỏ sót dữ liệu? |
| Incremental lag | Source latest commit - committed watermark | Pipeline bị tụt hậu? |
| Retry | Attempts/timeout/throttling | Có overload? |
| IR | SHIR CPU/queue/offline, Azure IR wait | Hạ tầng truyền có nghẽn? |
| SQL/Storage | CPU/IO, transactions, requests | Source/sink còn headroom? |
| Cost | Activity runs, DIU hours, storage/compute | Ngân sách có hợp lý? |

### 37.1. Phân biệt monitoring với watermark

Một pipeline **Succeeded** không tự chứng minh watermark đúng hoặc dữ liệu đích đủ. Ngược lại, một pipeline Failed sau apply có thể đã commit dữ liệu đích nhưng watermark chưa cập nhật.

### 37.2. Correlation

Ghi các trường vào run log:

~~~text
PipelineName
PipelineRunId
TriggerName / WindowId
SourceTable
SinkObject
StartWatermark
UpperWatermark
RowsRead
RowsCopied
RowsApplied
StartedAtUtc / CompletedAtUtc
Status / ErrorCode
~~~

### 37.3. Alert theo độ trễ dữ liệu

Nếu dữ liệu có SLO xuất hiện trong mart sau 15 phút, monitor **watermark age/data freshness**, không chỉ “pipeline run đã được khởi chạy”.

## 38. Security và private networking cho dữ liệu

Một pipeline dữ liệu thường đi qua nhiều boundary:

~~~text
Source SQL Server (on-prem / Azure VM)
       |
Self-hosted IR / Azure IR + private connectivity
       |
ADLS Gen2 landing / Azure SQL staging
       |
Curated analytics / reporting
~~~

Các nguyên tắc:

- Không mở SQL Server public để làm bài lab nhanh.
- Ưu tiên managed identity và least privilege khi connector hỗ trợ.
- Secrets đặt ở Key Vault; không đưa vào ARM JSON/logs.
- Phân quyền source SELECT, sink INSERT/UPDATE/EXECUTE và Storage ACL đúng phạm vi.
- Sử dụng TLS/encryption in transit và encryption at rest theo chính sách.
- Dùng private endpoint/VNet integration/SHIR phù hợp topology.
- Cần DNS resolution từ **IR thực thi**, không chỉ từ admin workstation.
- Tách dev/test/prod identities, databases và storage containers.
- Quản lý PII: masking, column-level access, audit, retention và purge.
- Kiểm tra data residency và outbound transfer giữa regions.

### 38.1. Key Vault reference

ADF Linked Service có thể dùng secret reference theo tính năng. Managed identity của factory cần quyền đọc secret theo mô hình access policy/RBAC của Key Vault và kết nối mạng phù hợp.

### 38.2. ADLS Gen2 RBAC và ACL

Với hierarchical namespace, Azure RBAC data roles và POSIX-like ACLs có vai trò khác nhau tùy permission path. Một role management Reader không mặc định cho phép tạo file vào thư mục.

### 38.3. On-prem SHIR và credentials

SHIR nodes cần được quản trị như hạ tầng quan trọng: OS patching, local service account, secret protection, outbound rules, HA và monitoring. Không đặt passwords cleartext trong pipeline expressions.

## 39. Git, CI/CD và nhiều môi trường

ADF hỗ trợ quy trình authoring/publishing và tích hợp Git theo phương thức hỗ trợ của dịch vụ. Một pipeline production cần:

- Code review cho pipeline definitions.
- Parameterized linked services/datasets.
- Tham số endpoint, resource group, storage path theo environment.
- Secrets qua Key Vault/identity.
- Infrastructure as Code và release approval.
- Automated validation/smoke tests sau deployment.
- Rollback strategy cho pipeline hoặc schema changes.
- Kiểm soát triggers để không chạy nhầm khi đang cutover.

### 39.1. Định nghĩa ở Git không tự là phiên bản đang chạy

Trong quy trình ADF Git integration, authoring branch/repository và **published/live factory artifacts** có bước đồng bộ/publish/deployment riêng. Cần kiểm tra trạng thái thực đang chạy, không mặc định commit Git xong là trigger production dùng định nghĩa mới.

### 39.2. Đừng lưu secrets trong linked service JSON

Git repository có thể được nhiều người đọc; chỉ lưu references/parameters, không lưu password hoặc connection string có credentials.

### 39.3. Deploy pipeline khác deploy dữ liệu

Sửa pipeline JSON không tự migration schema của Azure SQL hoặc tạo indexes. Cần phối hợp database migrations, permissions và release order.

## 40. Chi phí Data Factory và những dịch vụ liên quan

Chi phí không chỉ nằm trong resource ADF:

| Hạng mục | Ví dụ yếu tố tính phí |
|---|---|
| ADF orchestration | Số activity executions/runs theo pricing model |
| Data movement | DIUs/data movement compute và duration |
| Data flow | Compute sử dụng khi có Mapping Data Flows |
| Self-hosted IR | VM/on-prem node, vận hành và network |
| Azure SQL | vCore/DTU/storage/transaction log khi source/sink ghi |
| ADLS Gen2 | Dung lượng, transactions, tier và egress |
| Monitoring | Azure Monitor/Log Analytics ingestion/retention |
| Networking | Egress, Private Link, NAT/Firewall và transfer liên vùng |
| Backfill/retry | Số lần đọc/ghi lại dữ liệu và chạy pipeline |
| Downstream compute | Synapse, Databricks, Spark hoặc BI engine |

Giá thay đổi theo region, loại execution, thời điểm và hợp đồng, nên không đưa đơn giá cố định khi chưa kiểm tra Azure pricing hiện hành.

### 40.1. Incremental thường tiết kiệm hơn full copy

Nếu mỗi ngày chỉ 1% bảng thay đổi, incremental có thể giảm volume rất lớn. Nhưng nếu incremental query gây full scan vì thiếu index, source SQL vẫn tốn tài nguyên dù số rows copied nhỏ.

### 40.2. Không tạo pipeline activity vô ích

Với metadata-driven workload, hàng chục nghìn activities nhỏ có thể tạo orchestration overhead và chi phí. Cân nhắc gom/chia công việc hợp lý theo SLO, monitoring và cost.

### 40.3. Đừng dùng retries làm chiến lược mở rộng

Retry liên tục khi SQL bị throttled hoặc IR queue quá tải làm tăng executions/latency. Tìm bottleneck, điều chỉnh concurrency/scheduling hoặc capacity có căn cứ.

## 41. Runbook: incremental pipeline bị lỗi giữa chừng

Một lần chạy:

~~~text
10:00  Watermark = 09:30
10:01  Upper = 10:00
10:02  Copy vào staging bắt đầu
10:05  Copy đã ghi một phần, rồi timeout
10:06  Pipeline Failed
~~~

Quy trình:

1. Xác nhận RunId, window start/upper và activity output.
2. Kiểm tra control table watermark vẫn là 09:30.
3. Kiểm tra staging/landing đã có dữ liệu partial.
4. Xác định lỗi nguồn, network, IR, sink hay mapping.
5. Dọn đúng **partial staging của run/attempt** theo chính sách; không TRUNCATE staging chung.
6. Rerun với window đã claim hoặc chạy lại từ committed watermark theo design.
7. Apply idempotent; kiểm tra duplicates, updates và deletes.
8. Chỉ nâng watermark sau validation.
9. Ghi run log trạng thái mới và đối chiếu dữ liệu.
10. Alert nếu thời gian trễ vượt SLA.

### 41.1. Nếu fail sau khi target đã commit

Đích đã đúng nhưng watermark update fail. Chạy lại có thể tạo duplicate copy; sink/upsert phải chịu được. Đừng tăng watermark thủ công nếu chưa xác minh mọi dữ liệu trong window đã được apply.

### 41.2. Nếu watermark đã commit nhưng downstream mart fail

Phải biết watermark thuộc bước **ingest** hay **full business pipeline**. Có thể cần checkpoints riêng cho từng stage (bronze/silver/gold) để retry mart mà không ingest lại.

### 41.3. Khi CT/CDC retention đã quá hạn

Không thể luôn chạy lại các changes đã cleanup. Phải dùng full resync/reseed hoặc nguồn archive rồi đối soát. Không tự điều chỉnh checkpoint tới current version để che khoảng thiếu.

## 42. Lab 1: full load, incremental bằng watermark

**Điều kiện:** dùng Azure subscription/resource group lab được cấp phép, Azure SQL/SQL Server sample và ADLS Gen2 hoặc Azure SQL sink. Không chạy SQL destructive lên dữ liệu production.

### A. Chuẩn bị nguồn

Tạo bảng Orders mẫu với OrderId, CustomerId, Status, Amount, ModifiedAtUtc. Chèn một số dòng có ModifiedAtUtc khác nhau. Ghi rõ timezone là UTC.

~~~sql
INSERT INTO dbo.Orders (
    OrderId, CustomerId, Status, Amount, ModifiedAtUtc
)
VALUES
(101, 1, N'CREATED', 120.00, '2026-11-20T09:01:00'),
(102, 2, N'PAID',    90.00, '2026-11-20T09:02:00'),
(103, 1, N'CREATED', 300.00, '2026-11-20T09:03:00');
~~~

Chỉ chạy nếu bảng lab đã tồn tại và các OrderId chưa trùng.

### B. Tạo linked services/datasets

1. Source SQL linked service.
2. Staging sink linked service và dataset.
3. Integration Runtime phù hợp network.
4. Quyền SELECT nguồn, INSERT staging, EXECUTE procedure nếu dùng.
5. Tùy chọn ADLS landing nếu cần lưu bản copy raw.

### C. Chạy full seed

1. Chọn mốc watermark trước dataset đầu tiên.
2. Copy dữ liệu cần seed vào staging/đích.
3. Validate row count và một vài business keys.
4. Đặt watermark ban đầu theo trạng thái dữ liệu **đã apply đầy đủ**.
5. Ghi RunId và seed metadata.

### D. Chạy incremental

1. Lookup watermark cũ.
2. Chốt upper bound hợp lệ.
3. Copy rows thuộc cửa sổ.
4. Kiểm tra staging.
5. Apply upsert idempotent vào OrdersCurrent.
6. Commit watermark.
7. So sánh source và target.

### E. Tạo UPDATE mới

~~~sql
UPDATE dbo.Orders
SET Status = N'SHIPPED',
    ModifiedAtUtc = '2026-11-20T09:15:00'
WHERE OrderId = 102;
~~~

Trong lab giả định cửa sổ mới bao gồm 09:15 và watermark cũ trước đó. Rerun và xác minh row 102 ở đích thay đổi trạng thái thay vì có hai rows.

### F. Test retry

1. Dừng Copy có kiểm soát hoặc mô phỏng lỗi đích.
2. Xác minh watermark không tăng.
3. Rerun cùng window.
4. Chứng minh target không có duplicate OrderId.
5. Ghi logs và thời gian phục hồi.

## 43. Lab 2: metadata-driven orchestration với nhiều bảng

Tạo bảng cấu hình một số nguồn lab:

~~~text
dbo.Orders    -> dbo.OrdersStage
dbo.Customers -> dbo.CustomersStage
dbo.Products  -> dbo.ProductsStage
~~~

Thực hành:

1. Lookup danh sách bảng IsEnabled=1.
2. ForEach chạy **sequential** trước cho dễ kiểm tra.
3. Gọi pipeline con với sourceSchema/sourceTable/sinkTable.
4. Mỗi bảng dùng watermark riêng trong control DB.
5. Ghi RunId, rows copied, status và errors riêng từng bảng.
6. Tăng mức song song nhỏ và quan sát SQL/IR capacity.
7. Mô phỏng một bảng lỗi để kiểm tra partial failure/alert.
8. Không ghi một watermark chung cho nhiều bảng nếu chúng thay đổi độc lập.

### 43.1. Tiêu chí thành công

- Bảng thành công có checkpoint đúng.
- Bảng lỗi giữ checkpoint cũ.
- Pipeline cha báo kết quả partial/failure rõ ràng.
- Rerun bảng lỗi không nhân đôi bảng đã thành công.
- Tăng parallelism không làm source OLTP quá tải.

## 44. Lab 3: trigger, backfill và runbook

### A. Schedule trigger

1. Tạo schedule lab theo cadence có đủ thời gian hoàn thành.
2. Đặt pipeline-run concurrency thấp, ví dụ 1 cho cùng watermark stream.
3. Xem Monitor → Trigger runs và Pipeline runs.
4. Kiểm tra trễ schedule vs completion.

### B. Tumbling window

1. Tạo các cửa sổ giả 15 hoặc 30 phút.
2. Chuyển windowStart/windowEnd vào pipeline parameters.
3. Dùng quy ước **[start, end)** nhất quán cho SQL/file partitioning.
4. Giả lập backfill một window.
5. Xác minh rerun không ghi trùng.
6. Không bật hai triggers cùng xử lý một phạm vi nếu chưa có concurrency control.

### C. Failure/recovery

1. Mô phỏng lỗi network/permission trong lab.
2. Kiểm tra pipeline Failed và alert.
3. Xác nhận watermark không tiến.
4. Sửa nguyên nhân.
5. Rerun cửa sổ đã lỗi.
6. Đối chiếu dữ liệu cuối.
7. Viết runbook 1 trang ghi rõ ai xử lý, khi nào full resync cần thiết.

### D. Cleanup

1. Dừng/disable triggers lab.
2. Xác nhận không có pipeline runs đang ghi.
3. Kiểm tra không dùng linked services đến production.
4. Xóa đúng resource lab theo quyền/phê duyệt.
5. Xem Azure Cost Management để tránh compute/storage còn tính phí.

## 45. Checklist production

- [ ] Source/target owner và data contract được xác định.
- [ ] Chọn full, watermark, CT hay CDC đúng semantics UPDATE/DELETE.
- [ ] Watermark source thực sự đáng tin, có timezone/precision rõ.
- [ ] Commit race, late arrivals và timestamp ties đã được đánh giá.
- [ ] Có CT/CDC retention và runbook nếu mất checkpoint.
- [ ] Có composite cursor hoặc pagination strategy nếu cần.
- [ ] Control watermark tách với run log, có concurrency coordination.
- [ ] Upper boundary được chốt một lần cho run và audit.
- [ ] Copy chỉ xử lý cửa sổ nhất quán, không trộn conventions.
- [ ] Có staging/landing theo run hoặc attempt.
- [ ] Partial writes không phá khả năng retry.
- [ ] Sink apply idempotent theo business keys/versions.
- [ ] Watermark chỉ commit sau durable apply/validation.
- [ ] Đã kiểm thử fail trước/giữa/sau Copy, apply và watermark.
- [ ] Có dữ liệu reconciliation để phát hiện miss.
- [ ] DELETE/tombstone được xử lý theo policy.
- [ ] Schema drift/mapping có version và approval.
- [ ] Lookup output và expressions được kiểm tra trên actual output.
- [ ] ForEach parallelism không làm race pipeline variables.
- [ ] Pipeline-run concurrency/locks ngăn runs tranh watermark.
- [ ] Trigger chọn theo nhu cầu schedule/window/event.
- [ ] Backfill/rerun không tạo dữ liệu trùng.
- [ ] Error branch propagates failure và alert.
- [ ] Retry/timeout có budget, không vòng lặp vô hạn.
- [ ] Azure IR/SHIR có network, DNS và quota phù hợp.
- [ ] Linked services dùng secrets/identity theo least privilege.
- [ ] Azure SQL/ADLS RBAC và ACL được xác minh.
- [ ] Không truyền credentials/PII qua logs.
- [ ] Có giám sát freshness, rows, bytes, throughput và errors.
- [ ] Có monitoring SHIR queue/health và SQL source performance.
- [ ] Có SLO dữ liệu cuối và đối soát dữ liệu đích.
- [ ] CI/CD parameterized, tách dev/test/prod.
- [ ] Triggers được quản lý an toàn khi deploy.
- [ ] Có cost budget và tối ưu DIUs/activity executions.
- [ ] Có quy trình xóa tài nguyên lab và rotate secrets.

## 46. Câu hỏi tự kiểm tra

1. Copy activity làm nhiệm vụ gì và không tự giải quyết điều gì?
2. Linked service và dataset khác nhau thế nào?
3. Azure IR và self-hosted IR phù hợp nguồn dữ liệu nào?
4. Full load khác incremental load ở đặc điểm nào?
5. Vì sao incremental theo created_at không phát hiện UPDATE?
6. Watermark có nhất thiết là timestamp không?
7. Cửa sổ (last, upper] nghĩa là gì?
8. Vì sao không được nâng watermark trước Copy/apply?
9. Commit race là gì và vì sao safety delay có thể chưa đủ?
10. Timestamp ties gây rủi ro gì khi phân trang?
11. Khi nào dùng (timestamp, primaryKey) cursor?
12. CT và CDC có khác nhau ở dữ liệu changes mà chúng lưu không?
13. Khi CT checkpoint cũ hơn min valid version phải làm gì?
14. Nếu source xóa row, incremental chỉ đọc current rows sẽ xảy ra gì?
15. Staging theo RunId giúp phục hồi ra sao?
16. Vì sao rowsCopied không chứng minh dữ liệu báo cáo chính xác?
17. Upsert/idempotency giúp khi watermark commit thất bại thế nào?
18. ADF Copy vào ADLS và cập nhật SQL watermark có tự atomic không?
19. Lookup với firstRowOnly=false trả output dạng nào?
20. Vì sao không nên dùng Lookup để tải hàng triệu rows?
21. ForEach parallel có thể gây race trên pipeline variables ra sao?
22. Execute Pipeline cần chờ child completion trong trường hợp nào?
23. Schedule trigger có ngăn hai runs chồng nhau không?
24. Tumbling window thường dùng quy ước boundary nào?
25. Storage event trigger có bảo đảm exactly-once không?
26. Retry một Copy append partial có nguy cơ gì?
27. Nếu Copy timeout, có chắc không có row nào được ghi vào sink không?
28. Vì sao tăng parallelCopies quá cao có thể làm source OLTP chậm?
29. Khi nào cần explicit column mapping?
30. Data freshness SLO khác pipeline status như thế nào?
31. Managed identity có tự cho phép SELECT trên Azure SQL không?
32. Vì sao Git commit chưa chắc là pipeline live production?
33. CI/CD pipeline và schema migration nên phối hợp ra sao?
34. Những nguồn chi phí ngoài ADF orchestration là gì?
35. Runbook khi thất bại sau apply nhưng trước watermark phải xử lý thế nào?

## 47. Tổng kết

Trong **Azure Data Factory**, **Copy activity** đảm nhiệm sao chép dữ liệu từ source sang sink thông qua linked services, datasets và Integration Runtime. Tuy nhiên, tính đúng của hệ thống dữ liệu không chỉ phụ thuộc vào số rows đã copy.

**Incremental load** phải lựa chọn được thay đổi cần lấy và có **watermark/checkpoint đáng tin**: timestamp/ID cho trường hợp đơn giản, **Change Tracking hoặc CDC** khi cần hỗ trợ UPDATE/DELETE và commit-based change capture. Một cửa sổ dữ liệu phải có ranh giới rõ, xử lý timestamp ties và late commits; watermark chỉ được cập nhật **sau khi dữ liệu đã được apply và kiểm tra an toàn**.

**Pipeline orchestration** nối Lookup, Copy, validation, stored procedures, ForEach, Execute Pipeline và triggers thành một workflow có dependency, retry, timeout, concurrency và quan sát. Với các hệ thống khác nhau không chia sẻ transaction, thiết kế **at-least-once và idempotent sink** để một lần chạy lại không tạo dữ liệu trùng hoặc mất bản ghi.

Khi triển khai thực tế, kết hợp **managed identity/Key Vault, Azure IR hoặc self-hosted IR, VNet/private networking, Azure SQL/ADLS, Azure Monitor, CI/CD, runbook phục hồi và Cost Management**. Tiêu chí thành công cuối cùng không phải Copy activity màu xanh mà là **dữ liệu đích đầy đủ, đúng, cập nhật đúng hạn, có thể chạy lại an toàn và có chi phí dự báo được**.




