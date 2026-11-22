# Luồng thu nhận theo lô, CDC và luồng thời gian thực

> **Chương:** Nền tảng dữ liệu  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây, từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào thu nhận dữ liệu bằng batch, Change Data Capture (CDC) và streaming, cùng đánh đổi về độ trễ, tính đúng đắn, độ tin cậy, bảo mật, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt batch ingestion, CDC và streaming theo nguồn, độ trễ, khối lượng, thứ tự và mục tiêu nghiệp vụ.
2. Thiết kế luồng từ hệ thống nguồn đến landing/raw, xử lý, lưu trữ chuẩn hóa và hệ thống tiêu thụ.
3. Chọn giữa polling, log-based CDC, event broker và scheduled batch theo năng lực nguồn.
4. Hiểu at-most-once, at-least-once và exactly-once; thiết kế idempotency, deduplication, checkpoint và replay.
5. Quản lý schema evolution, dữ liệu sai, thứ tự sự kiện, late-arriving data và backfill.
6. Đánh giá bảo mật, quyền truy cập, chất lượng dữ liệu, khả năng khôi phục và tổng chi phí ingestion.

## 1. Vì sao phải thiết kế luồng thu nhận dữ liệu?

Một nền tảng dữ liệu cloud nhận dữ liệu từ nhiều nguồn: cơ sở dữ liệu giao dịch, ứng dụng, SaaS, thiết bị IoT, file đối tác, log và hệ thống kế thừa. Các nguồn này khác nhau về giao thức, tốc độ phát sinh, khả năng xuất dữ liệu, chất lượng và yêu cầu bảo mật.

Ví dụ nền tảng đặt chỗ cần lấy danh mục dịch vụ và dữ liệu đối soát từ ERP mỗi đêm; đồng bộ booking và payment sang warehouse trong vài phút; phân tích hành vi người dùng để cảnh báo gian lận gần thời gian thực; nhận file đối tác hàng ngày; và giữ lịch sử thay đổi để kiểm toán hoặc tái tạo báo cáo.

Thiết kế ingestion không phù hợp có thể làm dữ liệu đến quá muộn, tăng tải database nguồn, mất hoặc nhân đôi sự kiện, sai thứ tự cập nhật, rò rỉ dữ liệu nhạy cảm hoặc khiến chi phí cloud vượt dự báo.

**Batch, CDC và streaming không phải ba sản phẩm thay thế nhau hoàn toàn.** Một kiến trúc thực tế có thể kết hợp cả ba tùy loại dữ liệu và mục đích sử dụng.

## 2. Ba cách tiếp cận chính

### 2.1. Batch ingestion — thu nhận theo lô

Batch gom dữ liệu trong một khoảng thời gian hoặc một tập file rồi xử lý như một đơn vị công việc. Ví dụ chạy ETL lúc 01:00 mỗi ngày, nhập file CSV đối tác theo giờ hoặc đồng bộ dữ liệu giao dịch theo watermark.

Đặc điểm:

- Độ trễ thường là phút, giờ hoặc ngày; micro-batch có thể chạy thường xuyên hơn.
- Dễ xử lý tập dữ liệu lớn bằng scan, sort, join và aggregate.
- Có thể tối ưu tài nguyên theo lịch, tận dụng cửa sổ tải thấp của nguồn.
- Thường dễ backfill và chạy lại theo partition hoặc khoảng thời gian.
- Cần xử lý file trùng, file thiếu, bản ghi sửa/xóa và watermark.

Batch phù hợp với báo cáo định kỳ, đối soát, dữ liệu lịch sử, file đối tác và trường hợp nghiệp vụ chấp nhận dữ liệu trễ có giới hạn.

### 2.2. CDC — Change Data Capture

CDC ghi nhận thay đổi xảy ra ở nguồn dữ liệu, thường từ transaction log của database, rồi chuyển chúng tới hệ thống downstream. Một change record có thể biểu diễn insert, update, delete, vị trí log, thời gian, khóa chính và metadata nguồn.

Hai hướng phổ biến:

- **Log-based CDC:** đọc transaction log hoặc replication log. Thường tránh phải quét toàn bộ bảng và có thể ghi nhận delete nếu connector hỗ trợ.
- **Query/polling-based CDC:** định kỳ truy vấn bản ghi thay đổi bằng updated_at, version hoặc watermark. Dễ triển khai hơn với một số nguồn nhưng có thể bỏ sót delete, phụ thuộc timestamp và tạo tải query.

CDC phù hợp với đồng bộ database sang data lake/warehouse, cập nhật read model, cache, search index hoặc tích hợp hệ thống gần thời gian thực.

**CDC không đồng nghĩa với event nghiệp vụ hoàn chỉnh.** Một row update có thể không giải thích được ý nghĩa nghiệp vụ: booking chuyển từ PENDING sang CONFIRMED vì khách thanh toán hay vì nhân viên hỗ trợ sửa dữ liệu? Consumer cần hiểu semantics của change record.

### 2.3. Streaming — xử lý luồng sự kiện

Streaming xử lý sự kiện liên tục, thường đi qua message broker hoặc event streaming platform. Consumer đọc sự kiện khi chúng đến, theo dõi offset/checkpoint và cập nhật hệ thống đích.

Ví dụ: BookingCreated, PaymentAuthorized, InventoryReserved; clickstream web/mobile; telemetry; IoT; log bảo mật và tín hiệu cảnh báo.

Streaming phù hợp khi nghiệp vụ cần phản ứng nhanh, xử lý liên tục, phân tích event-time, cảnh báo hoặc fan-out tới nhiều consumer. Đổi lại hệ thống phải xử lý duplicate, ordering, late events, backpressure, schema evolution, partitioning và replay.

### 2.4. So sánh tổng quan

| Tiêu chí | Batch | CDC | Streaming |
| --- | --- | --- | --- |
| Đơn vị xử lý | File, partition, tập bản ghi | Change record từ database | Event/message liên tục |
| Độ trễ thường gặp | Phút đến ngày | Giây đến phút tùy connector | Millisecond đến phút tùy hệ thống |
| Nguồn điển hình | File, export, snapshot, API | Transaction log hoặc query watermark | Broker, event producer, telemetry |
| Tải lên nguồn | Có thể tăng theo lịch chạy | Log-based thường tránh full scan | Producer phát sinh liên tục |
| Thứ tự | Theo partition/file hoặc logic xử lý | Thường theo log/partition; không global order | Thường chỉ bảo đảm trong một partition/key |
| Chạy lại | Theo file, partition, time range | Theo log offset/snapshot và connector state | Replay theo offset/retention hoặc archive |
| Xử lý xóa | Cần tombstone, soft delete hoặc reconciliation | Có thể bắt delete nếu connector hỗ trợ | Producer phải phát event xóa |
| Phù hợp | BI, đối soát, lịch sử, file đối tác | Đồng bộ trạng thái database | Phản ứng sự kiện, near-real-time analytics |
| Độ phức tạp | Thấp đến trung bình | Trung bình đến cao | Trung bình đến cao |

Không có ngưỡng độ trễ phổ quát để phân loại. Hãy xác định **freshness objective** của nghiệp vụ trước khi chọn công nghệ.

## 3. Kiến trúc ingestion tham khảo trên cloud

Một nền tảng tổng quát có thể chia thành các lớp:

1. **Sources:** transactional database, SaaS, files, applications, IoT, partner systems.
2. **Capture/connectors:** batch extractors, CDC connectors, event producers/consumers.
3. **Transport:** object storage landing, message broker, event streaming platform hoặc managed transfer.
4. **Raw/landing zone:** giữ dữ liệu nhận được và metadata đủ để audit/replay.
5. **Processing:** validate, normalize, deduplicate, enrich, transform, route và quarantine.
6. **Curated storage:** lakehouse, warehouse, search/read model hoặc operational store.
7. **Consumers:** dashboard, BI, machine learning, API, alerting và downstream applications.
8. **Control/observability:** schema registry, orchestration, catalog, lineage, IAM, metrics, logs và audit.

~~~mermaid
flowchart LR
    subgraph SRC["Nguồn"]
      DB[("OLTP database")]
      FILE["Files / partner export"]
      APP["Application events"]
      EXT["SaaS / external APIs"]
    end
    subgraph CAP["Thu nhận"]
      CDC["CDC connectors"]
      BATCH["Batch extractor"]
      PRODUCER["Event producers"]
    end
    DB --> CDC
    FILE --> BATCH
    EXT --> BATCH
    APP --> PRODUCER
    subgraph TRANS["Vận chuyển"]
      BROKER["Event broker / stream"]
      LAND[("Object storage landing")]
    end
    CDC --> BROKER
    PRODUCER --> BROKER
    BATCH --> LAND
    BROKER --> LAND
    subgraph PROC["Xử lý"]
      VALID["Validate / schema / deduplicate"]
      TRANSFORM["Normalize / enrich / aggregate"]
      QUAR["Quarantine / DLQ"]
    end
    LAND --> VALID
    BROKER --> VALID
    VALID -->|"Valid"| TRANSFORM
    VALID -->|"Invalid"| QUAR
    TRANSFORM --> CUR[("Curated lake / warehouse")]
    TRANSFORM --> READ["Operational read model"]
    CUR --> BI["BI / ML / analytics"]
    READ --> API["Application APIs"]
~~~

Đây là kiến trúc khái niệm. Không phải mọi luồng đều cần object storage và broker cùng lúc. Có thể batch trực tiếp tới warehouse, CDC vào broker hoặc streaming thẳng vào engine rồi lưu raw archive tùy yêu cầu replay và audit.

### 3.1. Control plane và data plane

- **Data plane** vận chuyển và xử lý dữ liệu thực tế: connector, broker, object storage, compute và sink.
- **Control plane** quản lý cấu hình pipeline, schema, quyền, lịch chạy, checkpoint, catalog, lineage và chính sách.

Khi control plane lỗi, data plane có thể tiếp tục chạy một khoảng thời gian nếu đã có cấu hình và checkpoint; tuy nhiên việc triển khai pipeline mới, thay đổi schema hoặc khôi phục có thể bị ảnh hưởng. Cần thiết kế backup và HA cho metadata/control state phù hợp.

## 4. Thiết kế batch ingestion

### 4.1. Snapshot, incremental load và watermark

Ba dạng phổ biến:

- **Full snapshot:** tải toàn bộ dữ liệu mỗi lần. Dễ hiểu và kiểm tra nhưng tốn thời gian, băng thông và tải nguồn khi bảng lớn.
- **Incremental load:** chỉ lấy dữ liệu mới/thay đổi kể từ một mốc đã lưu.
- **Partitioned batch:** chia dữ liệu theo ngày, tháng, tenant hoặc khóa partition để xử lý song song và chạy lại.

Ví dụ incremental load dùng updated_at:

~~~sql
SELECT id, customer_id, status, updated_at
FROM booking
WHERE updated_at > :last_successful_watermark
  AND updated_at <= :upper_bound
ORDER BY updated_at, id;
~~~

Cách này cần lưu ý:

- Timestamp có thể trùng; dùng khóa phụ như id để tạo thứ tự ổn định.
- Bản ghi cập nhật muộn hoặc đồng hồ lệch có thể rơi ngoài cửa sổ.
- Delete vật lý không xuất hiện trong query này.
- Transaction có thể commit sau khi watermark được chốt.
- Nên dùng overlap window hợp lý và idempotent upsert để bù dữ liệu đến trễ.

Không cập nhật watermark sang thời điểm mới chỉ vì job đã bắt đầu. Chỉ tiến watermark sau khi batch tương ứng được xử lý, kiểm tra và commit thành công.

### 4.2. Manifest và file completion

Với file ingestion, tránh xử lý file khi producer vẫn đang ghi dở. Một quy ước hữu ích:

1. Producer ghi file tạm hoặc upload multipart.
2. Sau khi upload hoàn tất, producer phát manifest hoặc completion marker.
3. Manifest chứa file name, size, checksum, schema version, record count, source và thời điểm tạo.
4. Consumer chỉ xử lý file hoàn tất; xác minh checksum và kích thước.
5. Ghi kết quả bằng batch_id ổn định để chống ingest trùng.

Ví dụ manifest:

~~~json
{
  "batch_id": "partner-2026-11-18-001",
  "source": "partner_booking",
  "schema_version": 3,
  "object_uri": "s3://example-landing/partner/2026/11/18/data-001.parquet",
  "record_count": 125000,
  "checksum": "sha256:example",
  "created_at": "2026-11-18T01:00:00Z"
}
~~~

Dữ liệu minh họa. Không đưa bí mật hoặc PII thô vào manifest nếu metadata đó được chia sẻ rộng hơn data object.

### 4.3. Orchestration và lịch chạy

~~~mermaid
flowchart TD
    A["Nhận file / snapshot"] --> B["Kiểm tra manifest và checksum"]
    B --> C["Validate schema và dữ liệu"]
    C --> D["Load staging"]
    D --> E["Merge/upsert curated tables"]
    E --> F["Reconcile counts / quality checks"]
    F --> G["Commit watermark và đánh dấu hoàn tất"]
    C -->|"Invalid"| Q["Quarantine + alert"]
    D -->|"Failure"| R["Retry / resume theo batch_id"]
~~~

Orchestrator cần hỗ trợ retry, timeout, dependency, concurrency limit, backfill, parameterization và audit. Tránh để hai lần chạy cùng partition ghi đồng thời mà không có cơ chế khóa hoặc upsert an toàn.

### 4.4. Ưu và nhược điểm của batch

Batch dễ triển khai và kiểm chứng theo tập dữ liệu, nhưng độ mới phụ thuộc lịch chạy. Job lớn có thể tạo tải đỉnh lên nguồn hoặc kho dữ liệu; nếu thất bại gần cuối, chạy lại toàn bộ sẽ tốn kém. Chia partition và checkpoint giúp kiểm soát phạm vi xử lý.

## 5. Thiết kế CDC

### 5.1. Log-based CDC hoạt động ra sao?

Database ghi thay đổi giao dịch vào transaction log để hỗ trợ recovery/replication. CDC connector đọc log, diễn giải thay đổi và xuất record tới broker hoặc sink.

~~~mermaid
flowchart LR
    APP["Ứng dụng ghi giao dịch"] --> DB[("Database primary")]
    DB --> LOG["Transaction log / WAL / binlog"]
    LOG --> CDC["CDC connector"]
    CDC --> BR["Broker / stream"]
    BR --> SINK["Warehouse / search / read model"]
    CDC --> STATE[("Connector offset / schema state")]
~~~

Metadata có thể chứa operation, key, before/after image, source database/table, transaction ID, log sequence/offset, timestamp và schema version. Tên trường và semantics khác nhau giữa connector; không giả định mọi nguồn đều cung cấp before image.

### 5.2. Snapshot ban đầu và streaming changes

Khi bắt đầu CDC, hệ thống thường cần **initial snapshot** để có trạng thái hiện tại, rồi tiếp tục nhận thay đổi từ vị trí log phù hợp. Snapshot và streaming phải phối hợp để không có khoảng trống hoặc nhân bản ngoài ý muốn.

Cần làm rõ:

- Snapshot được chụp tại thời điểm/LSN nào?
- Connector ghi nhận vị trí log trước, trong hay sau snapshot?
- Update xảy ra trong lúc snapshot được đọc sẽ được xử lý ra sao?
- Khi restart, checkpoint/state còn nguyên và có thể tiếp tục không?
- Khi log retention bị vượt qua, cần re-snapshot hay phục hồi từ archive?

Connector khỏe không đồng nghĩa pipeline không mất dữ liệu. Phải kiểm tra offset, lag, transaction log retention, snapshot state, schema history và sink acknowledgement.

### 5.3. CDC từ timestamp polling

Nếu nguồn không hỗ trợ log-based CDC, có thể polling các bản ghi có updated_at hoặc version. Cách này đơn giản hơn nhưng:

- Không bắt được hard delete nếu không có tombstone hoặc audit table.
- Nhiều cập nhật cùng timestamp có thể bị bỏ sót nếu watermark chỉ dùng timestamp.
- Query lặp lại có thể làm tải database nguồn tăng.
- Audit column có thể thiếu hoặc không được cập nhật bởi mọi đường ghi.

Có thể dùng soft delete, change table, sequence/version hoặc overlap window; phải xác minh mọi kênh ghi đều tuân thủ.

### 5.4. CDC không tự động tạo domain event

Row-level update thể hiện trạng thái dữ liệu, không nhất thiết là sự kiện nghiệp vụ. Ví dụ CDC cho biết booking.status đổi từ HELD sang CONFIRMED; domain event BookingConfirmed có thể được phát ra sau khi quy tắc thanh toán, giữ chỗ và quyền sở hữu đơn đã được xác nhận.

Nếu consumer cần nghiệp vụ rõ ràng, ưu tiên event contract do ứng dụng/domain phát hành. Nếu cần đồng bộ dữ liệu hoặc xây lakehouse, CDC phù hợp hơn. Có thể dùng cả hai với mục tiêu riêng.

### 5.5. Log retention và connector lag

Nếu connector ngừng đủ lâu khiến transaction log cần đọc bị xóa hoặc tái sử dụng, CDC có thể không tiếp tục được từ offset cũ. Cần:

- Theo dõi connector lag và vị trí log so với retention.
- Cảnh báo trước khi lag vượt thời gian an toàn.
- Xác định cách tăng retention, phục hồi connector hoặc re-snapshot.
- Capacity planning cho broker, sink và mạng.
- Diễn tập connector restart, network partition và sink outage.

Không tăng retention vô hạn: transaction log lớn có thể tăng storage và ảnh hưởng vận hành database nguồn.

## 6. Thiết kế streaming/event ingestion

### 6.1. Producer, broker và consumer

Producer xuất sự kiện, broker giữ/định tuyến và consumer xử lý. Broker có thể cung cấp partition, replication, retention, consumer groups, acknowledgement và bảo mật.

~~~mermaid
flowchart LR
    P1["Booking producer"] --> TOP["Topic: booking-events"]
    P2["Payment producer"] --> TOP
    TOP --> CG1["Consumer group: analytics"]
    TOP --> CG2["Consumer group: notification"]
    TOP --> CG3["Consumer group: fraud"]
    CG1 --> DWH[("Warehouse")]
    CG2 --> MSG["Notification service"]
    CG3 --> ALERT["Fraud alerts"]
~~~

Consumer group thường có offset riêng, nên có thể đọc cùng stream độc lập. Khả năng scale consumer bị giới hạn bởi số partition và semantics ordering.

### 6.2. Event contract

Một event tốt cần:

- Event ID duy nhất và ổn định khi retry cùng sự kiện.
- Event type, schema version, occurred_at và source.
- Aggregate/entity key để phân vùng và giữ thứ tự trong phạm vi cần thiết.
- Payload tối thiểu cần cho consumer; tránh secret và PII không cần thiết.
- Correlation ID/causation ID để truy vết.
- Quy tắc tương thích schema và thời hạn hỗ trợ phiên bản.

Ví dụ:

~~~json
{
  "event_id": "evt-8f14",
  "event_type": "BookingConfirmed",
  "event_version": 2,
  "occurred_at": "2026-11-18T03:20:00Z",
  "producer": "booking-service",
  "aggregate_type": "booking",
  "aggregate_id": "bkg-204",
  "correlation_id": "req-91ac",
  "tenant_id": "tenant-08",
  "data": {
    "booking_id": "bkg-204",
    "status": "CONFIRMED",
    "currency": "VND"
  }
}
~~~

Dữ liệu minh họa. Tenant ID và business data chỉ được phát khi cần thiết, đã được phân loại và cho phép theo hợp đồng dữ liệu.

### 6.3. Partition key và ordering

Trong partitioned stream, broker thường chỉ bảo đảm thứ tự trong một partition, không phải toàn bộ topic. Nếu cần thứ tự thay đổi theo booking, dùng booking_id làm partition key để sự kiện cùng booking được định tuyến ổn định.

Đánh đổi:

- Key phân bố không đều tạo hot partition.
- Tăng partition count có thể thay đổi mapping key-to-partition tùy thuật toán, ảnh hưởng thứ tự khi di chuyển dữ liệu.
- Một consumer group thường không xử lý song song nhiều hơn số partition hữu dụng.
- Global ordering giảm khả năng song song và thường không cần cho mọi nghiệp vụ.

Chỉ giữ thứ tự ở phạm vi nghiệp vụ thực sự yêu cầu.

### 6.4. Event time, processing time và watermark

- **Event time:** thời điểm sự kiện thực sự xảy ra tại nguồn.
- **Processing time:** thời điểm hệ thống xử lý sự kiện.
- **Ingestion time:** thời điểm nền tảng nhận sự kiện.

Ba thời điểm khác nhau do mạng chậm, producer offline, clock skew hoặc backlog. Analytics theo cửa sổ cần xác định dùng event-time hay processing-time.

Streaming engine có thể dùng watermark để ước lượng mức hoàn tất dữ liệu event-time trong một cửa sổ. Event đến sau watermark có thể bị bỏ qua, đưa vào side output hoặc cập nhật kết quả theo chính sách engine.

Ví dụ doanh thu theo giờ nhận sự kiện thanh toán trễ 10 phút. Watermark 15 phút có thể cân bằng độ trễ kết quả và dữ liệu muộn; giá trị thực tế phải dựa trên phân phối độ trễ và yêu cầu nghiệp vụ.

Cần làm rõ late event có được phép cập nhật aggregate đã phát hành, báo cáo có revision/correction record không, sự kiện quá muộn được quarantine/replay hay batch reconciliation và watermark có bị giữ do partition ngừng phát hay không.

## 7. Semantics giao hàng và tính đúng đắn

### 7.1. At-most-once, at-least-once và exactly-once

| Semantics | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| At-most-once | Có thể không xử lý message nhưng không retry theo semantics đó | Có thể mất dữ liệu; phù hợp một số metric ít quan trọng |
| At-least-once | Retry theo điều kiện cho đến khi acknowledgement/checkpoint | Có thể nhận trùng; consumer phải idempotent |
| Exactly-once | Bảo đảm trong một phạm vi xử lý/commit cụ thể | Không tự động bao phủ mọi database, API và side effect |

Luôn hỏi **exactly-once ở ranh giới nào?** Stream processor có thể bảo đảm transaction giữa input offset và output topic trong một hệ sinh thái; điều đó không tự động bảo đảm email chỉ gửi một lần hoặc cổng thanh toán chỉ thu tiền một lần.

Thiết kế thực tế thường dùng at-least-once + idempotent processing + reconciliation thay vì dựa vào lời hứa exactly-once xuyên hệ thống.

### 7.2. Idempotency và deduplication

Một thao tác idempotent cho cùng input logic sẽ tạo cùng tác dụng cuối dù được thực hiện nhiều lần.

Consumer có thể lưu processed_event_id với unique constraint trong cùng transaction với cập nhật dữ liệu đích. Nếu nhận lại event đã xử lý, bỏ qua tác dụng phụ và acknowledgement theo đúng quy trình.

Cần xác định event ID duy nhất ở phạm vi nào, lưu deduplication state bao lâu, database update và đánh dấu processed có nằm trong cùng transaction không, hệ thống ngoài hỗ trợ idempotency key ra sao và replay có được phép tạo lại email/hóa đơn/lệnh thanh toán không.

### 7.3. Checkpoint và offset

Consumer đọc stream thường duy trì offset/checkpoint. Ghi checkpoint trước khi hoàn tất side effect có thể làm mất xử lý sau crash; ghi sau nhưng không idempotent có thể gây xử lý trùng.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Target DB
    B->>C: Event at offset 101
    C->>D: Begin transaction
    C->>D: Check event_id / apply update
    C->>D: Commit data + processed_event_id
    C->>B: Commit offset 101
    Note over B,D: Nếu crash trước offset commit, event có thể được giao lại; consumer deduplicate
~~~

Không phải broker và database nào cũng commit offset cùng transaction với database. Khi không có distributed transaction, cần idempotency, outbox/inbox pattern hoặc reconciliation.

## 8. Schema evolution và hợp đồng dữ liệu

Producer và consumer thường phát hành ở thời điểm khác nhau. Schema thay đổi phá vỡ consumer có thể làm pipeline dừng hoặc đọc sai dữ liệu.

Nguyên tắc:

- Có schema version và quy trình review.
- Ưu tiên bổ sung field optional có default hợp lý, giữ semantics ổn định.
- Tránh xóa hoặc đổi kiểu field consumer đang sử dụng trước khi migration.
- Consumer nên chịu được field chưa biết khi contract cho phép.
- Kiểm tra compatibility trong CI, registry hoặc pipeline.
- Hỗ trợ nhiều phiên bản trong thời gian chuyển đổi.
- Lưu raw payload khi cần audit/replay, đồng thời kiểm soát retention và bảo mật.

Version 1:

~~~json
{
  "booking_id": "bkg-204",
  "status": "CONFIRMED"
}
~~~

Version 2 bổ sung currency optional:

~~~json
{
  "booking_id": "bkg-204",
  "status": "CONFIRMED",
  "currency": "VND"
}
~~~

Bổ sung optional field thường tương thích tốt hơn đổi booking_id từ string sang object hoặc đổi ý nghĩa status. Tính tương thích còn tùy serialization format, default, consumer và schema registry policy.

Schema registry quản lý schema và compatibility policy trong một số nền tảng streaming. Data contract rộng hơn schema: có thể gồm owner, ý nghĩa business field, classification, freshness SLA, quality rules, retention và quyền truy cập.

Không chỉ kiểm tra JSON parse được. Dữ liệu amount âm có thể hợp lệ về cấu trúc nhưng sai nghiệp vụ nếu giao dịch không cho phép số âm.

## 9. Chất lượng dữ liệu, quarantine và xử lý lỗi

Pipeline ingestion phải xác định rõ dữ liệu nào hợp lệ, dữ liệu nào được sửa có kiểm soát và dữ liệu nào cần cách ly.

Các lớp kiểm tra:

- **Schema validation:** field bắt buộc, kiểu dữ liệu, enum, version.
- **Completeness:** không thiếu khóa chính, timestamp, source hoặc partition.
- **Uniqueness:** khóa nghiệp vụ hoặc event ID không trùng ngoài quy tắc.
- **Validity:** giá trị nằm trong miền cho phép; timestamp và currency hợp lệ.
- **Referential integrity:** tham chiếu entity tồn tại hoặc có chính sách khi đến trễ.
- **Freshness:** dữ liệu đến trong SLA.
- **Volume/anomaly:** record count, null rate, phân phối giá trị bất thường.
- **Reconciliation:** so sánh số bản ghi/tổng tiền với hệ thống nguồn.

### 9.1. DLQ và quarantine

Với event không thể xử lý sau số lần retry hợp lý, có thể chuyển vào dead-letter queue (DLQ) hoặc quarantine store cùng metadata: lỗi, event ID, source, offset, schema version, thời điểm và số lần retry.

Nguyên tắc:
- Retry lỗi tạm thời với backoff và jitter; không retry vô hạn lỗi dữ liệu không hợp lệ.
- Giữ payload trong vùng có quyền hạn chặt; tránh biến DLQ thành nơi lưu PII không kiểm soát.
- Có dashboard cho số lượng, tuổi bản ghi và nhóm lỗi DLQ.
- Có quy trình sửa dữ liệu/schema và replay có kiểm soát.
- Đánh dấu bản ghi đã replay, giữ audit và chống side effect lặp.

Một poison message có thể khiến consumer lặp lại cùng offset và không tiến lên. Cần bounded retries, DLQ, pause partition có cảnh báo hoặc cách ly record theo khả năng broker/engine. Bỏ qua lỗi phải có chính sách rõ để không âm thầm mất dữ liệu.

## 10. Backpressure, throughput và capacity

Backpressure là cơ chế điều tiết producer/consumer khi tốc độ xử lý không cân bằng. Nếu producer nhanh hơn consumer, backlog tăng, tuổi dữ liệu tăng và storage/retention bị tiêu thụ.

Theo dõi producer rate, consumer throughput, consumer lag theo record và thời gian, oldest message age, partition skew, hot key, retry, DLQ growth, broker disk, network, sink saturation.

Ví dụ giả định: producer tạo trung bình 5.000 event/giây, mỗi event 2 KB:

\[
R_{\text{raw}} = 5{,}000 \times 2\text{ KB} = 10\text{ MB/s}
\]

Trong một giờ, payload thô xấp xỉ:

\[
10\text{ MB/s} \times 3{,}600\text{ s} = 36{,}000\text{ MB} \approx 36\text{ GB}
\]

Chưa tính overhead, replication, compression, index và metadata. Với replication factor 3, dung lượng broker vật lý có thể cao hơn đáng kể.

Nếu consumer xử lý 3.000 event/giây, backlog tăng 2.000 event/giây. Trong 10 phút tăng khoảng 1,2 triệu event. Cần capacity hoặc chính sách giảm tải, scale consumer, buffer và cảnh báo trước khi hết retention.

Cách xử lý:
- Tăng consumer song song trong giới hạn partition và sink capacity.
- Tối ưu xử lý từng record, batch commit và I/O.
- Tăng partition khi key distribution và ordering cho phép.
- Chọn broker capacity và retention đủ thời gian khôi phục.
- Giới hạn producer, quota hoặc ưu tiên luồng quan trọng.
- Scale sink/database theo năng lực chịu tải.
- Tách telemetry ít quan trọng khỏi luồng giao dịch.
- Dùng circuit breaker/backpressure thay vì buffer vô hạn.

Autoscaling consumer chỉ hiệu quả nếu partition cho phép scale, sink không nghẽn và worker khởi tạo đủ nhanh.

## 11. Bảo mật và quản trị dữ liệu trong ingestion

Dữ liệu đi qua nhiều trust boundary: nguồn, connector, broker, object storage, processing engine, catalog và consumer.

Các kiểm soát quan trọng:

1. **Identity và least privilege:** connector chỉ đọc bảng/log cần thiết; consumer chỉ đọc topic/bucket cần thiết; sink chỉ ghi đích được cấp.
2. **Mã hóa:** TLS khi truyền và encryption at rest cho broker, object storage, checkpoint, schema registry và backup.
3. **Secret management:** database credential, API key và certificate lấy từ secret manager; có rotation và audit.
4. **Data classification:** gắn nhãn PII, payment, confidential; giảm payload hoặc masking/tokenization khi phù hợp.
5. **Data residency:** xác minh region của source, broker, landing, processing, backup, logs và DR.
6. **Network isolation:** private endpoints, egress allowlist, VPC/VNet segmentation, security group và firewall.
7. **Audit:** ghi lại ai đọc, ghi, sửa schema, replay, export hoặc thay đổi pipeline.
8. **Retention/deletion:** raw archive, DLQ, log và replay store có thời hạn, quy trình xóa và legal hold phù hợp.
9. **Tenant isolation:** tenant context đã xác thực, partition/bucket/policy phù hợp; không tin tenant_id do client tự khai.

CDC có thể đọc dữ liệu trước/sau thay đổi, trong đó chứa thông tin nhạy cảm. Event stream tồn tại lâu trong retention, nên cần thiết kế quyền và lưu trữ cẩn thận.

~~~mermaid
flowchart LR
    S["Database source\nPII / payment"] --> C["Connector identity\nleast privilege"]
    C --> B["Private broker\nTLS + encryption"]
    B --> P["Processing\nvalidate / mask"]
    P --> R[("Raw restricted zone")]
    P --> K[("Curated zone")]
    R --> AUD["Catalog / lineage / audit"]
    K --> CONS["Authorized consumers"]
~~~

Việc mask ở processing không xóa nghĩa vụ bảo vệ raw landing zone nếu raw payload còn PII.

## 12. Độ tin cậy, khôi phục và replay

Các trạng thái lỗi cần nghĩ tới:

- Database source failover, transaction log bị rotate hoặc connector mất vị trí đọc.
- Broker mất node/partition hoặc storage đầy.
- Consumer crash sau khi ghi sink nhưng trước khi commit offset.
- Sink throttling hoặc không ghi được.
- Schema mới không tương thích consumer cũ.
- Network partition khiến message được giao lại.
- Pipeline chạy lại cùng batch/partition hai lần.
- Producer phát event trùng hoặc sai thứ tự.

Thiết kế recovery:

- Lưu checkpoint/offset và backup metadata connector có thể khôi phục.
- Giữ raw archive đủ lâu để replay theo chính sách.
- Đặt retention broker dựa trên thời gian outage và backfill dự kiến.
- Tạo sink idempotent và upsert theo business key/version/event ID.
- Tách replay khỏi live traffic khi cần để tránh cạn capacity.
- Reconcile với source để phát hiện gap và dữ liệu sai.
- Diễn tập mất connector, broker, sink và vùng triển khai.
- Đo RTO/RPO cho pipeline và freshness riêng; không dùng một chỉ số cho cả platform.

Replay không phải lúc nào cũng an toàn. Nó có thể kích hoạt lại side effect như gửi email, thu tiền, tạo order, gọi đối tác hoặc billing. Cần xác định consumer nào chỉ cập nhật projection có thể chạy lại, consumer nào có side effect và cần idempotency/replay mode riêng.

Khi backfill, dùng namespace/topic/output hoặc versioned table riêng nếu thích hợp; kiểm tra kết quả trước khi thay thế dữ liệu production đang phục vụ.

## 13. Chọn batch, CDC hay streaming theo mục tiêu nghiệp vụ

| Nhu cầu | Hướng phù hợp ban đầu | Lý do / điểm cần kiểm tra |
| --- | --- | --- |
| Báo cáo tài chính cuối ngày | Batch | Đối soát đầy đủ theo ngày; chạy lại được |
| Đồng bộ booking sang data lake trong vài phút | Log-based CDC | Giảm polling; cần schema, log retention, snapshot |
| Cảnh báo gian lận khi giao dịch xảy ra | Streaming event | Phản ứng nhanh; cần event contract và late event policy |
| Nhận file đối tác mỗi giờ | Batch/micro-batch | Manifest, checksum, duplicate detection |
| Đồng bộ search index sau thay đổi hồ sơ | CDC hoặc domain event | Chọn theo semantics và nhu cầu lịch sử |
| Dashboard cập nhật mỗi 15 phút | Micro-batch hoặc CDC | So sánh chi phí stream liên tục với freshness |
| Phân tích clickstream gần real-time | Streaming | Throughput cao, event-time và backpressure |
| Backfill dữ liệu lịch sử nhiều năm | Batch | Partition, rate limit nguồn và checkpoint |
| Phát tín hiệu khi booking confirmed | Domain event | Ý nghĩa nghiệp vụ rõ hơn row-level CDC |

Không chọn streaming chỉ vì dữ liệu cần mới. Nếu dashboard cập nhật 15 phút là đủ, batch hoặc micro-batch có thể rẻ và dễ vận hành hơn. Nếu fraud decision phải đưa ra trước khi cho phép thanh toán, batch theo giờ không đáp ứng.

## 14. Tình huống thực tế: nền tảng đặt chỗ và phân tích dữ liệu

### 14.1. Nguồn và yêu cầu

Một nền tảng đặt chỗ có database Booking, database Payment, file CSV đối tác vận chuyển mỗi ngày, clickstream web/mobile với hàng nghìn event/giây trong chiến dịch và ERP cung cấp danh mục/đối soát theo lịch.

Yêu cầu:
- Dashboard vận hành booking cập nhật trong vài phút.
- Cảnh báo gian lận phản ứng trong vài giây.
- Báo cáo tài chính hoàn tất sau đối soát cuối ngày.
- Không làm quá tải database giao dịch.
- Giữ dữ liệu nguồn đủ để kiểm toán và chạy lại khi pipeline lỗi.

### 14.2. Thiết kế kết hợp

~~~mermaid
flowchart TB
    DB1[("Booking DB")] --> CDC1["Log-based CDC"]
    DB2[("Payment DB")] --> CDC2["Log-based CDC"]
    CDC1 --> BROKER["Managed stream / broker"]
    CDC2 --> BROKER
    CLICK["Web/mobile clickstream"] --> BROKER
    ERP["ERP API"] --> BATCH["Scheduled extractor"]
    PARTNER["Partner CSV"] --> LAND[("Object storage landing")]
    BATCH --> LAND
    BROKER --> RAW[("Raw event archive")]
    BROKER --> RT["Stream processing"]
    RT --> FRAUD["Fraud alerts"]
    RT --> OPS[("Operational analytics store")]
    LAND --> BATCHPROC["Batch validation / transform"]
    RAW --> BATCHPROC
    BATCHPROC --> WH[("Warehouse / lakehouse")]
    OPS --> DASH["Operations dashboard"]
    WH --> BI["Financial / BI reports"]
~~~

### 14.3. Giải thích lựa chọn

- **Booking/Payment:** CDC cập nhật trạng thái dữ liệu trong vài phút và xây raw history. Cần lọc PII, xử lý delete và xác định bảng được phép capture.
- **Clickstream:** streaming phù hợp lưu lượng liên tục và fraud alerts. Cần partition theo entity/session tùy ordering, event ID, sampling và retention.
- **ERP/CSV:** batch theo lịch dễ kiểm soát đối soát và file; manifest giúp phát hiện file thiếu/trùng.
- **Operational dashboard:** consume CDC/event và cập nhật read model; nêu rõ freshness và khả năng dữ liệu đến muộn.
- **Financial reports:** batch reconciliation từ nguồn đáng tin cậy; không chỉ cộng event stream nếu cần chứng từ và đối soát chính xác.

### 14.4. Chỉ tiêu và phép thử minh họa

| Mục tiêu giả định | Phép kiểm chứng |
| --- | --- |
| CDC lag p95 dưới 2 phút | Đo source commit time so với sink availability ở tải thường/đỉnh |
| Fraud alert dưới 5 giây từ event time | End-to-end timestamp và tải cao điểm |
| Không bỏ sót file có completion marker | Manifest/checksum/count reconciliation |
| Không tạo booking/payment projection trùng khi replay | Duplicate/restart/replay test |
| Không lộ PII cho consumer ngoài quyền | IAM negative tests và access audit |
| Phục hồi trong RTO/RPO đã duyệt | Broker/sink outage và restore/replay exercise |

Các ngưỡng trên là giả định bài tập, cần Product/Security/SRE xác nhận trước khi trở thành SLO hoặc tiêu chí nghiệm thu.

## 15. Chi phí và đánh đổi của nền tảng ingestion

Chi phí gồm connector compute/license; broker throughput, partition, storage, replication và retention; object storage; batch/stream processing; network egress/cross-region; schema registry, catalog, monitoring, logs, audit; backfill, replay, DLQ và công vận hành.

\[
TCO = C_{\text{capture}} + C_{\text{transport}} + C_{\text{storage}}
+ C_{\text{processing}} + C_{\text{network}} + C_{\text{governance}}
+ C_{\text{operations}}
\]

| Cách | Khoản chi đáng chú ý | Hướng tối ưu |
| --- | --- | --- |
| Batch | Compute theo job, scan, storage, lịch chạy | Partition pruning, incremental load, compression |
| CDC | Connector, broker, source log retention, sink | Capture đúng bảng, tune snapshot, theo dõi lag |
| Streaming | Broker, retention, partition, continuous compute | Right-size partition, batch processing, retention theo use case |
| Kết hợp | Nhiều semantics/tooling, duplicate storage | Chuẩn hóa contract, catalog, IAM và observability |

Streaming liên tục có thể cần capacity và vận hành thường trực; nếu freshness objective rộng, batch có thể hiệu quả hơn. Không có kết luận chi phí chung nếu chưa biết lưu lượng, retention, replication, managed-service pricing và mô hình compute.

FinOps cần trả lời: byte capture/broker/replicate mỗi ngày; số lần scan raw trong backfill; egress liên vùng; thời gian consumer lag; dữ liệu nào cần raw dài hạn; cost/GB và cost/million events; telemetry nào có thể giảm sampling/retention.

## 16. Observability và vận hành pipeline

Pipeline cần SLO về freshness, tính toàn vẹn và khả năng phục hồi.

| Nhóm | Metric / tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Source | Log position, source latency, query load, log retention | Nguồn có bị ảnh hưởng hoặc connector sắp mất khả năng tiếp tục? |
| Capture | Connector status, snapshot progress, lag, error count | Thay đổi có được đọc đầy đủ? |
| Broker | Throughput, partition skew, storage, replication, oldest age | Vận chuyển có ổn định và đủ capacity? |
| Consumer | Consumer lag, processing latency, retry, checkpoint age | Downstream có bắt kịp? |
| Quality | Schema failure, null/duplicate rate, rejected records | Dữ liệu có đúng và đủ? |
| Sink | Commit duration, write failures, throttling, reconciliation | Dữ liệu có ghi đúng đích? |
| Freshness | Event time so với availability time | Dữ liệu mới đến đúng SLA? |
| Cost | Cost/GB, cost/million events, storage growth | Chi phí có tăng bất thường? |
| Security | Unauthorized access, secret rotation, policy violation | Dữ liệu có được bảo vệ? |

Không chỉ cảnh báo số event lag. Queue lag 100.000 event có thể bình thường nếu throughput cao; 100 event đã chậm 30 phút có thể là sự cố nghiêm trọng. Dùng cả lag theo record và **age of oldest unprocessed event**.

Runbook tối thiểu:
- Connector stopped: kiểm tra credential, source log retention, schema change, network và checkpoint.
- Broker backlog: xem producer rate, consumer throughput, partition skew, storage và sink throttling.
- Schema incompatibility: xác định phiên bản producer/consumer, dừng rollout nếu cần, route record lỗi và sửa contract.
- Sink outage: giới hạn retry/backpressure, giữ message trong retention, bảo đảm không commit offset sai.
- DLQ tăng: phân loại lỗi, xác định poison message, sửa dữ liệu/schema và replay có phê duyệt.
- Data mismatch: dừng phát hành báo cáo sai, đối soát source, xác định khoảng thời gian và chạy backfill.
- Region failure: phục hồi metadata, connector state, broker/landing theo RTO/RPO và kiểm tra gap.

Mỗi pipeline cần owner kỹ thuật, owner nghiệp vụ, source of truth, consumers, classification, schema, freshness SLA, retention và runbook. Lineage giúp biết bảng/dashboard nào phụ thuộc vào field hoặc nguồn nào khi thay đổi.

## 17. Architecture Decision Record mẫu

~~~markdown
# ADR-052: Kết hợp CDC và batch cho nền tảng dữ liệu đặt chỗ

Trạng thái: Đề xuất / chấp thuận có điều kiện
Decision owner: Data Architect + Product + SRE
Ngày: YYYY-MM-DD

Bối cảnh:
- Booking/Payment cần đồng bộ sang analytics trong vài phút.
- Fraud alerts cần phản ứng nhanh theo click/payment event.
- ERP và đối tác gửi dữ liệu đối soát theo lịch.
- Không được tạo tải scan lớn trên OLTP database.

Phương án:
A. Batch toàn bộ nguồn.
B. CDC cho database, streaming cho event, batch cho file/ERP.
C. Streaming toàn bộ dữ liệu.

Quyết định:
- Đề xuất B; giữ raw archive đủ để replay và audit.
- CDC chỉ capture bảng cần thiết; business event có contract riêng.
- Batch reconciliation là nguồn đối chiếu cho báo cáo tài chính.

Đánh đổi:
- Vận hành nhiều pipeline và semantics.
- Cần schema management, deduplication, replay và data lineage.

Bằng chứng nghiệm thu:
- CDC lag và freshness theo SLO đã duyệt.
- Không mất/trùng dữ liệu khi restart và replay.
- Không làm OLTP source quá tải.
- Data quality/reconciliation đạt tiêu chí.
- TCO ở steady state, peak và backfill nằm trong ngân sách.

Điều kiện xem xét lại:
- Freshness objective thay đổi; source đổi database;
  log retention không đủ; chi phí hoặc số consumer tăng mạnh.
~~~

ADR cần ghi rõ phạm vi exactly-once/at-least-once, dữ liệu được capture, ai phê duyệt quyền truy cập và phương án khi phải re-snapshot.

## 18. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng batch cho nghiệp vụ cần phản ứng vài giây | Cảnh báo/decisions đến muộn | Xác định freshness objective, dùng event/stream khi cần |
| Dùng streaming cho báo cáo chỉ cần mỗi ngày | Tăng chi phí và vận hành không cần thiết | Batch/micro-batch và reconciliation |
| Tưởng CDC là domain event | Consumer hiểu sai ý nghĩa business | Phân biệt row change và business event |
| Chỉ dùng timestamp làm watermark | Bỏ sót record trùng timestamp hoặc commit muộn | Compound cursor, overlap, version và reconciliation |
| Không xử lý delete | Downstream giữ bản ghi đã xóa | Tombstone, soft delete hoặc reconciliation |
| Commit offset trước khi sink commit | Crash có thể làm mất dữ liệu | Transaction boundary, idempotency và đúng thứ tự commit |
| Không deduplicate | Số liệu hoặc tác dụng phụ trùng | Stable event ID, inbox/unique constraint |
| Tin exactly-once toàn hệ thống | Email/payment/API side effect trùng | Xác định boundary, idempotency, reconciliation |
| Không giám sát source log retention | CDC mất vị trí đọc | Alert lag và diễn tập re-snapshot |
| Không có schema governance | Consumer lỗi sau thay đổi | Data contract, compatibility test, versioning |
| Retry vô hạn poison message | Partition bị chặn, backlog tăng | Bounded retries, DLQ và quarantine |
| Không tính late-arriving event | Báo cáo cửa sổ thời gian sai | Event-time, watermark và correction policy |
| Chỉ đo record lag | Không thấy event đã cũ hàng giờ | Theo dõi oldest event age và freshness |
| Raw zone không giới hạn quyền | PII lan rộng | Classification, IAM, encryption, retention |
| Replay thẳng production có side effect | Gửi lại thông báo hoặc giao dịch | Replay mode, idempotency và tách projection |
| Không đối soát với nguồn | Pipeline xanh nhưng số liệu sai | Count/total reconciliation và quality checks |

## 19. Bài tập thực hành

Một nền tảng thương mại điện tử có ba nguồn: PostgreSQL chứa đơn hàng, ứng dụng web phát clickstream và đối tác logistics gửi CSV mỗi 30 phút. Product muốn dashboard vận hành cập nhật trong 2 phút; Fraud cần cảnh báo trong 5 giây; báo cáo doanh thu cần đối soát đúng cuối ngày. Database đơn hàng không được chịu full table scan liên tục.

Hãy thực hiện:

1. Phân loại dữ liệu theo batch, CDC hay streaming; giải thích lý do.
2. Vẽ kiến trúc source → capture → broker/landing → process → curated → consumers; phân biệt data plane và control plane.
3. Đề xuất event contract gồm event_id, event_type, version, occurred_at, entity key và correlation ID.
4. Thiết kế incremental batch với watermark, xử lý file trùng và delete.
5. Mô tả snapshot + log-based CDC; xác định điều kiện connector có thể mất log position và cách phục hồi.
6. Định nghĩa at-least-once, idempotency, checkpoint và replay cho consumer có side effect.
7. Thiết kế schema evolution và DLQ/quarantine; nêu quy trình replay bản ghi lỗi.
8. Tính throughput, backlog và retention với giả định dữ liệu nêu rõ.
9. Lập danh sách IAM, encryption, tenant isolation, data residency và retention controls.
10. Đặt SLI/SLO cho freshness, data quality, CDC lag, consumer lag và reconciliation.
11. So sánh TCO cho batch-only, CDC + streaming và kiến trúc kết hợp.
12. Viết ADR có giả định, rủi ro còn lại, phương án thay thế, owner và điều kiện xem xét lại.

**Tiêu chí tự đánh giá:** giải pháp tốt không chỉ đưa dữ liệu đến nhanh. Nó phải chứng minh dữ liệu đúng, đủ, có thể truy vết và chạy lại an toàn; không làm quá tải nguồn; bảo vệ dữ liệu nhạy cảm; đạt freshness cần thiết với chi phí và năng lực vận hành chấp nhận được.

## 20. Checklist trước khi đưa pipeline vào production

- [ ] Mỗi nguồn có owner, source of truth và quyền truy cập được xác nhận.
- [ ] Freshness objective, SLO, volume và retention được Product/Data/SRE thống nhất.
- [ ] Batch có manifest/checksum, watermark, partition, retry, idempotent load và backfill.
- [ ] CDC có snapshot strategy, log position, connector state, lag alert và re-snapshot plan.
- [ ] Streaming có event contract, partition key, ordering scope, offset/checkpoint và backpressure.
- [ ] Delivery semantics xác định ở từng boundary; consumer có idempotency/deduplication.
- [ ] Schema evolution có compatibility test, owner và policy.
- [ ] Dữ liệu sai đi vào quarantine/DLQ có audit, retention và replay có kiểm soát.
- [ ] Event-time, processing-time, watermark và late-arrival policy rõ.
- [ ] Raw/curated storage có classification, IAM, encryption, retention và lineage.
- [ ] Connector/consumer có dashboard, logs, metrics, trace/correlation và runbook.
- [ ] Có fault test: source outage, broker outage, sink outage, duplicate, late data và schema break.
- [ ] Reconciliation chứng minh tính đầy đủ và chính xác so với source.
- [ ] RTO/RPO, checkpoint backup và replay đã diễn tập khi phù hợp.
- [ ] TCO gồm capture, transport, storage, processing, network, governance và vận hành.
- [ ] ADR lưu lựa chọn, giả định, rủi ro, đánh đổi và trigger xem xét lại.

## Ghi nhớ

**Batch** phù hợp với dữ liệu xử lý theo tập và lịch; **CDC** ghi nhận thay đổi từ database để đồng bộ trạng thái gần thời gian thực; **streaming** xử lý sự kiện liên tục và cho phép phản ứng nhanh. Các phương pháp có thể kết hợp: CDC cho thay đổi OLTP, streaming cho event nghiệp vụ/clickstream, batch cho file, backfill và đối soát.

Thiết kế ingestion tốt phải bảo đảm **đúng dữ liệu, đúng thời điểm, đúng quyền và có thể phục hồi**. Hãy bắt đầu từ freshness, volume, semantics và source constraints; sau đó thiết kế contract, checkpoint, idempotency, quality, security, observability và TCO. Tốc độ chỉ là một phần của chất lượng nền tảng dữ liệu.
