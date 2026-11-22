# Replay, backfill và phân biệt dữ liệu phục hồi với dữ liệu mới

Trong **SPRING_BOOT_INTEGRATION**, một ứng dụng Spring Boot có thể nhận dữ liệu qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration. Luồng tích hợp thường vận hành liên tục, nhưng thực tế có lúc consumer ngừng hoạt động, message hết thời gian lưu, một phiên bản ứng dụng xử lý sai hoặc một bảng tổng hợp phải xây dựng lại. Khi đó cần **replay** hay **backfill** để phục hồi dữ liệu.

Thách thức không chỉ là đưa dữ liệu cũ vào hệ thống lần nữa. Cần biết **dữ liệu mô tả điều gì, được phát sinh khi nào, đã được áp dụng chưa, còn hợp lệ không, và liệu việc xử lý lại có tạo ra tác dụng phụ hay không**. Nếu coi một sự kiện lịch sử vừa được nạp lại là “đơn hàng mới”, hệ thống có thể gửi lại email, tính doanh thu của hôm nay sai, ghi đè trạng thái mới hơn hoặc thu tiền hai lần.

Mục tiêu của bài học:

- Phân biệt **retry**, **replay**, **backfill**, **reprocess**, **reconciliation** và luồng **live**.
- Mô hình hóa **định danh sự kiện**, **thời gian nghiệp vụ**, **nguồn gốc dữ liệu** và **lượt phục hồi** thành các khái niệm riêng.
- Thiết kế xử lý **idempotent**, kiểm soát **version/thứ tự** khi lịch sử và dữ liệu mới đến xen kẽ.
- Thực hiện replay/backfill an toàn với Spring Boot, PostgreSQL, HTTP, broker và Spring Integration.
- Kiểm chứng **tính đầy đủ, nhất quán và không lặp side effect** thay vì chỉ đếm số message đã đọc.

## 1. Tình huống: mất một đoạn dữ liệu nhưng luồng mới vẫn chạy

Giả sử dịch vụ **Order Projection** nhận sự kiện trạng thái đơn hàng từ hệ thống đối tác, rồi lưu bảng đọc nhanh để API tra cứu. Đối tác phát:

~~~text
10:00  order-42 / version=10 / CREATED
10:05  order-42 / version=11 / PAID
10:10  order-42 / version=12 / SHIPPED
10:15  order-42 / version=13 / DELIVERED
~~~

Consumer bị lỗi từ 10:04 đến 10:12. Sau khi khôi phục, nó có thể nhận được sự kiện **version=13** qua luồng live, trong khi một tiến trình backfill đang lấy lại **version=11** và **version=12** từ API lịch sử. Nếu updater áp dụng message theo **thứ tự đến**, kết quả có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant Source as Hệ thống nguồn
    participant Live as Live consumer
    participant Backfill as Backfill worker
    participant DB as Order projection DB
    Source->>Live: DELIVERED (v13)
    Live->>DB: Lưu DELIVERED, version=13
    Source->>Backfill: Lịch sử PAID (v11), SHIPPED (v12)
    Backfill->>DB: Cố ghi PAID (v11)
    Note over DB: Nếu ghi đè vô điều kiện -> sai!
    Backfill->>DB: Cố ghi SHIPPED (v12)
    Note over DB: Chỉ cho cập nhật khi version mới hơn
~~~

Yêu cầu đúng là **khôi phục phần thiếu mà không làm lùi trạng thái mới nhất**. Đồng thời, báo cáo “đơn hàng mới trong hôm nay” không được tính lại các đơn chỉ vì chúng được nạp vào cơ sở dữ liệu hôm nay.

Ví dụ này giả định mỗi thay đổi trạng thái được nguồn cấp một **version tăng đơn điệu trên từng orderId**. Nếu hệ thống nguồn không cung cấp version hoặc sequence đáng tin cậy, phải lựa chọn chiến lược khác, chẳng hạn snapshot có watermark, CDC với vị trí log, hoặc reconciliation; **timestamp nhận tại consumer không đủ để khẳng định bản nào mới hơn**.

## 2. Các thuật ngữ gần nhau nhưng không giống nhau

| Khái niệm | Ý nghĩa | Ví dụ | Rủi ro nếu nhầm |
| --- | --- | --- | --- |
| **Live ingestion** | Tiếp nhận sự kiện phát sinh theo luồng hoạt động bình thường | Consumer nhận OrderPaid ngay sau khi phát | Coi message đến muộn là sự kiện mới |
| **Retry** | Thử lại một thao tác chưa hoàn tất hoặc có kết quả chưa chắc chắn | HTTP timeout rồi gửi lại cùng idempotency key | Lặp giao dịch hoặc side effect |
| **Redelivery** | Broker giao lại một delivery chưa được ack hoặc cần xử lý lại | RabbitMQ requeue sau consumer crash | Trừ tiền hai lần nếu consumer không idempotent |
| **Replay** | Chạy lại các sự kiện/bản ghi **đã tồn tại** từ lịch sử bền vững | Đọc lại Kafka offset hoặc event archive để rebuild projection | Phát lại thông báo và tác động ngoài ý muốn |
| **Backfill** | Bù dữ liệu bị thiếu hoặc xây dữ liệu lịch sử cho một phạm vi | Lấy đơn hàng từ API đối tác cho khoảng 10:04–10:12 | Ghi đè cập nhật live, bỏ sót biên thời gian |
| **Reprocess** | Tính lại dữ liệu đã xử lý bằng logic/hợp đồng đã thay đổi | Tính lại VAT từ bản ghi nguồn sau sửa bug | Thay đổi business result mà không có audit/version |
| **Reconciliation** | So sánh hai phía để phát hiện và giải quyết chênh lệch | Đối chiếu số đơn theo source với projection | Tin nhầm “job thành công” là “dữ liệu đã đủ” |

**Replay** thường dựa vào **log sự kiện bền vững**, còn **backfill** có thể lấy từ snapshot, API phân trang, bảng staging hoặc kho dữ liệu lịch sử; cách đặt tên trong từng tổ chức có thể khác. Điều quan trọng là xác định **nguồn chân lý (source of truth)** và **ngữ nghĩa dữ liệu được đọc**.

Khi broker chỉ giữ message trong một thời gian, việc muốn replay không đồng nghĩa message cũ vẫn còn đó. Nếu không có lưu trữ sự kiện hay API lịch sử, có thể **không thể phục hồi chính xác** toàn bộ quá khứ chỉ bằng cơ chế retry của consumer.

## 3. Phân biệt ba loại thời gian

Một sự kiện lịch sử có thể được xử lý lại rất lâu sau khi xảy ra. Không dùng một cột **created_at = now()** để đại diện mọi loại thời gian.

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **occurredAt / eventTime** | Khi sự kiện **xảy ra trong nghiệp vụ** theo nguồn | Đối tác xác nhận thanh toán lúc 10:05 |
| **sourceRecordedAt / sourcePosition** | Khi nguồn ghi nhận hoặc vị trí có thứ tự trong log/CDC | CDC LSN, event sequence 11 |
| **ingestedAt / observedAt** | Khi hệ thống tích hợp **tiếp nhận lần này** | Backfill nhập sự kiện lúc 14:00 |
| **processedAt** | Khi handler commit tác động vào projection | 14:00:01 |
| **recoveryRunId** | Lượt replay/backfill đã đưa bản ghi vào | run-20261121-01 |

Một event PAID phát sinh lúc 10:05 nhưng được backfill lúc 14:00 vẫn là **sự kiện PAID lúc 10:05**, không phải một đơn thanh toán mới lúc 14:00. Vì vậy:

- **Báo cáo theo thời gian nghiệp vụ** dùng eventTime hay effective date theo contract.
- **Báo cáo độ trễ tích hợp** dùng hiệu giữa ingestedAt và occurredAt (có lưu ý đồng hồ nguồn có thể lệch).
- **Audit phục hồi** dùng recoveryRunId, thời điểm chạy và nguồn dữ liệu phục hồi.
- **Định thứ tự cập nhật** dùng sourceVersion, sequence hoặc nguồn version có bảo đảm thứ tự; **không dựa riêng vào ingestedAt hay occurredAt** nếu upstream có độ trễ/lệch clock.

Cần xác định timezone, định dạng UTC, độ chính xác timestamp và ý nghĩa “ngày kế toán” trong hợp đồng dữ liệu. Đôi khi sự kiện **được ghi lúc 10:05 nhưng có hiệu lực hồi tố từ 09:00**; khi đó cần cả effectiveAt riêng, tránh đánh đồng eventTime với thời gian hiệu lực.

## 4. Định danh sự kiện và định danh lượt nạp là hai việc khác nhau

**Một sự kiện nguồn** phải có **identity ổn định** dù được nhận qua live, replay hay backfill nhiều lần. Trong khi đó, **mỗi lần nạp/attempt** có định danh riêng để theo dõi vận hành.

~~~mermaid
flowchart LR
    E["Source event E-007, order-42, v11"] --> LIVE["Lần nhận LIVE"]
    E --> REP1["Lần nhận REPLAY #1"]
    E --> BACK["Lần nhận BACKFILL #2"]
    LIVE --> ID["Cùng business event identity"]
    REP1 --> ID
    BACK --> ID
    ID --> APPLY["Một tác động nghiệp vụ đúng quy tắc"]
~~~

Hợp đồng sự kiện ví dụ:

~~~json
{
  "eventId": "91fe41a3-4164-4b8f-84e5-c08b9d5abbd0",
  "sourceSystem": "partner-a",
  "aggregateType": "Order",
  "aggregateId": "order-42",
  "sourceVersion": 11,
  "eventType": "OrderStateChanged",
  "state": "PAID",
  "occurredAt": "2026-11-21T03:05:00Z",
  "schemaVersion": 1
}
~~~

Thông tin của **lượt tiếp nhận** được giữ ở envelope/metadata khác:

~~~json
{
  "ingestionMode": "BACKFILL",
  "recoveryRunId": "4c88bcf3-11a8-40b3-b0e1-e85e286cc009",
  "ingestedAt": "2026-11-21T07:00:00Z",
  "sourceSnapshotId": "partner-a-snapshot-20261121",
  "attempt": 2
}
~~~

**Không được thay eventId hay occurredAt thành giá trị mới chỉ vì chạy lại.** Nếu nguồn không có eventId:

1. Ưu tiên khóa bất biến do nguồn cam kết, như **(sourceSystem, aggregateId, sourceVersion, eventType)** nếu contract xác nhận một sự kiện duy nhất cho mỗi tổ hợp.
2. Với snapshot, định danh bản ghi theo **sourceSystem + businessKey + revision/snapshot watermark**, không theo số lần tải.
3. Hash nội dung chuẩn hóa chỉ là phương án suy diễn có giới hạn: hai sự kiện hợp lệ có nội dung giống nhau vẫn có thể khác nhau; đổi schema/format sẽ làm hash thay đổi. Phải hiểu hợp đồng trước khi chọn.

**Idempotency key cho thao tác bên ngoài** (như một yêu cầu thanh toán) là một loại định danh khác. Nó cần ràng buộc với **ý định nghiệp vụ**, không với attempt hoặc recoveryRunId.

## 5. Dữ liệu phục hồi không có nghĩa là dữ liệu mới

Có ít nhất ba trạng thái nên phân biệt rõ ở downstream:

| Trạng thái xử lý | Nghĩa chính xác | Ví dụ |
| --- | --- | --- |
| **FIRST_SEEN_LIVE** | Lần đầu handler nhận sự kiện qua luồng live | Đơn mới phát sinh, consumer xử lý tức thời |
| **FIRST_SEEN_RECOVERY** | Handler **mới nhìn thấy lần đầu**, nhưng event đã xảy ra trong quá khứ | PAID lúc 10:05, backfill lúc 14:00 |
| **ALREADY_SEEN** | Sự kiện đã được áp dụng/ghi nhận trước đó | Replay lại chính event PAID |
| **STALE_OR_SUPERSEDED** | Sự kiện chưa từng gặp nhưng version cũ hơn trạng thái hiện tại | Replay v11 khi projection đã v13 |
| **CONFLICT** | Hai dữ liệu nguồn tự nhận cùng identity/version nhưng nội dung mâu thuẫn | Event khác payload cùng order-42/v11 |

**FIRST_SEEN_RECOVERY không phải là “new order” trong báo cáo nghiệp vụ.** Trạng thái mới của một đơn thường được quyết định theo **thời gian sự kiện, identity và các quy tắc trạng thái**, không theo thời điểm bản ghi lần đầu xuất hiện trong database đích.

Nếu hệ thống phát thêm sự kiện từ projection, hãy phân biệt rõ:

- **Business event**: sự kiện thật từ nguồn, giữ nguyên identity và eventTime.
- **Processing/audit event**: thông báo rằng dữ liệu đã được phục hồi, ví dụ **BackfillCompleted**; đây là sự kiện vận hành mới, có eventId riêng, không đồng nghĩa phát sinh một OrderCreated mới.
- **Derived event**: sự kiện mới thực sự phản ánh một thay đổi tính toán được nghiệp vụ cho phép. Cần quy tắc rõ trước khi phát ra ngoài.

Không tự động gửi lại email chào mừng, thông báo đẩy, giao dịch thanh toán hoặc lệnh đặt hàng chỉ vì một event lịch sử được đọc lại. Đối với downstream cần làm lại dữ liệu, hãy cung cấp **hợp đồng replay có chủ ý**, vì một số consumer như projection có thể replay an toàn trong khi consumer tạo side effect lại không.

## 6. Hai lớp bảo vệ: inbox chống trùng và version chống ghi lùi

**Deduplication** và **ordering** giải quyết hai loại lỗi khác nhau:

- **Inbox/dedup:** cùng một **eventId** được giao nhiều lần nhưng không áp dụng nhiều lần.
- **Version guard:** hai event **khác ID** của cùng aggregate tới sai thứ tự; event cũ không thể ghi đè trạng thái mới hơn.

Nếu chỉ có inbox, version=11 lần đầu đến sau version=13 vẫn sẽ được xem là “mới” và có thể ghi lùi. Nếu chỉ kiểm tra version, hai event cùng version nhưng payload mâu thuẫn có thể bị bỏ qua mà không có dấu vết điều tra.

### 6.1. Schema PostgreSQL minh họa

~~~sql
-- Bảng dùng chung cho consumer projection, chống xử lý lại cùng event ID.
CREATE TABLE processed_source_event (
    consumer_name    varchar(80)  NOT NULL,
    source_system    varchar(80)  NOT NULL,
    event_id         uuid         NOT NULL,
    aggregate_id     varchar(120) NOT NULL,
    source_version   bigint       NOT NULL,
    first_seen_mode  varchar(16)  NOT NULL,
    first_seen_at    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, source_system, event_id),
    CONSTRAINT processed_event_mode_check
        CHECK (first_seen_mode IN ('LIVE', 'REPLAY', 'BACKFILL'))
);

-- Projection thể hiện trạng thái MỚI NHẤT của mỗi đơn.
CREATE TABLE order_state_projection (
    source_system        varchar(80)  NOT NULL,
    order_id             varchar(120) NOT NULL,
    source_version       bigint       NOT NULL,
    state                varchar(40)  NOT NULL,
    state_occurred_at    timestamptz  NOT NULL,
    last_applied_event_id uuid        NOT NULL,
    updated_at           timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (source_system, order_id)
);

-- Theo dõi một lượt chạy phục hồi, KHÔNG giả làm đơn hàng mới.
CREATE TABLE recovery_run (
    id                  uuid PRIMARY KEY,
    mode                varchar(16) NOT NULL,
    source_system       varchar(80) NOT NULL,
    scope_description   text NOT NULL,
    source_watermark    text,
    state               varchar(20) NOT NULL,
    started_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    CHECK (mode IN ('REPLAY', 'BACKFILL')),
    CHECK (state IN ('PLANNED','RUNNING','PAUSED','FAILED','COMPLETED'))
);
~~~

Trong production, cần thêm index, retention, lỗi từng bản ghi và **source identity contract**. **processed_source_event** có thể tăng rất nhanh; không xóa lịch sử chống trùng trước khi kết thúc cửa sổ replay/redelivery hoặc khi chưa có cách nhận diện idempotency thay thế.

### 6.2. Transaction apply với kiểm tra version

Giả định nguồn bảo đảm **sourceVersion tăng trên từng orderId**; một version mới thay thế trạng thái cũ, không yêu cầu phải xử lý đủ các version trung gian để dựng ra trạng thái hiện tại. Handler dưới đây minh họa cập nhật projection:

~~~java
public record OrderStateChanged(
        UUID eventId, String sourceSystem, String orderId,
        long sourceVersion, String state, Instant occurredAt,
        int schemaVersion) {}

public enum IngestionMode { LIVE, REPLAY, BACKFILL }

public enum ApplyResult { APPLIED, ALREADY_SEEN, STALE }
~~~

~~~java
@Service
public class OrderProjectionUpdater {
    private final JdbcTemplate jdbc;

    public OrderProjectionUpdater(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ApplyResult apply(OrderStateChanged event, IngestionMode mode) {
        if (event.schemaVersion() != 1 || event.sourceVersion() < 0) {
            throw new IllegalArgumentException("Unsupported event contract");
        }

        int inserted = jdbc.update("""
                INSERT INTO processed_source_event
                    (consumer_name, source_system, event_id,
                     aggregate_id, source_version, first_seen_mode)
                VALUES ('order-projection', ?, ?, ?, ?, ?)
                ON CONFLICT (consumer_name, source_system, event_id)
                DO NOTHING
                """,
                event.sourceSystem(), event.eventId(),
                event.orderId(), event.sourceVersion(), mode.name());

        if (inserted == 0) {
            return ApplyResult.ALREADY_SEEN;
        }

        int changed = jdbc.update("""
                INSERT INTO order_state_projection
                    (source_system, order_id, source_version, state,
                     state_occurred_at, last_applied_event_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (source_system, order_id)
                DO UPDATE SET
                    source_version = EXCLUDED.source_version,
                    state = EXCLUDED.state,
                    state_occurred_at = EXCLUDED.state_occurred_at,
                    last_applied_event_id = EXCLUDED.last_applied_event_id,
                    updated_at = now()
                WHERE order_state_projection.source_version
                    < EXCLUDED.source_version
                """,
                event.sourceSystem(), event.orderId(),
                event.sourceVersion(), event.state(),
                Timestamp.from(event.occurredAt()), event.eventId());

        if (changed == 0) {
            // Trạng thái hiện tại đã mới hơn hoặc bằng sourceVersion.
            // Cần kiểm tra riêng conflict "cùng version, khác payload"
            // theo source contract; xem mục 6.3.
            return ApplyResult.STALE;
        }
        return ApplyResult.APPLIED;
    }
}
~~~

**Điều kiện để ví dụ đúng:** thao tác insert inbox và upsert projection dùng **cùng PostgreSQL DataSource và transaction manager**. Gọi phương thức qua Spring proxy để **@Transactional** có hiệu lực, không dựa vào self-invocation. Nếu transaction rollback, cả marker dedup và projection phải rollback; không được đánh dấu đã xử lý khi phần nghiệp vụ chưa commit.

**ON CONFLICT ... DO UPDATE ... WHERE source_version < EXCLUDED.source_version** là cập nhật có điều kiện thực hiện ngay trong DB, giúp ngăn ghi lùi dưới cạnh tranh từ hai thread/instance. Đây là ví dụ **last version wins**, không phải **last arrival wins**. Version là nguồn bảo đảm thứ tự, khác với thời điểm consumer nhận.

Khi **changed=0**, không phải lúc nào cũng là lỗi: sự kiện v11 đến sau v13 là trường hợp mong đợi. Nhưng v11 với payload mâu thuẫn cùng một version đã áp dụng lại là lỗi hợp đồng cần điều tra, không được âm thầm gọi là stale.

### 6.3. Cùng version nhưng dữ liệu khác nhau

Nếu mỗi aggregate/version chỉ được phép có một trạng thái nguồn, nên lưu thêm **hash payload đã chuẩn hóa** hoặc một bản ghi sự kiện nguồn bất biến theo **(sourceSystem, aggregateId, sourceVersion)**. Với message khác eventId nhưng cùng sourceVersion:

1. Nếu nội dung trùng khớp theo contract, xem là **duplicate alias**; audit và bỏ qua.
2. Nếu payload mâu thuẫn, đưa vào **quarantine/conflict queue**, cảnh báo và đối soát với nguồn.
3. Nếu nguồn cho phép sửa lịch sử, **không** tự ghi đè theo thời điểm nhận; sử dụng **sourceRevision/correctionId** hoặc chính sách bitemporal được định nghĩa rõ.

Để thực hiện chặt chẽ, thêm bảng **source_event_version** với unique key và content hash, ghi trong transaction cùng inbox/projection. Handler minh họa ở mục 6.2 chỉ cho thấy version guard căn bản; nó **chưa triển khai đầy đủ conflict detection** và không thích hợp để mặc định bỏ qua mọi message bằng sourceVersion.

## 7. Chọn cách ghi theo loại dữ liệu: snapshot, event hay ledger

Không có một kiểu **upsert** phù hợp mọi bài toán.

| Dạng dữ liệu nguồn | Cách xử lý replay/backfill | Điều tránh |
| --- | --- | --- |
| **Snapshot trạng thái hiện tại** | Upsert theo business key và sourceRevision/version, kiểm tra tombstone | Snapshot cũ ghi đè trạng thái live |
| **Sự kiện trạng thái thay thế nhau** | Lưu history nếu cần; cập nhật latest projection khi version tăng | Dùng thời điểm nhận để chọn trạng thái |
| **Sự kiện cộng dồn** (thanh toán, điểm thưởng, điều chỉnh tồn) | Lưu từng fact theo eventId rồi tạo aggregate; một fact áp dụng tối đa một lần | Cộng lại số tiền khi replay |
| **Sự kiện có ràng buộc thứ tự** (saga, workflow) | Xử lý tuần tự theo key, giữ pending khi thiếu predecessor; phát hiện gap | Bỏ qua version trung gian dù business cần từng bước |
| **Dữ liệu bị xóa** | Tôn trọng delete event/tombstone và revision | Backfill snapshot cũ làm “hồi sinh” bản ghi đã xóa |
| **Sửa dữ liệu hồi tố** | Correction/revision riêng, có audit và phép tính lại rõ ràng | Coi bản sửa hồi tố là order mới |

Ví dụ **current status projection** có thể bỏ qua v11 và v12 nếu đã áp dụng v13 **và trạng thái v13 chứa toàn bộ thông tin cần thiết**. Nhưng với **ledger** tính tổng giao dịch, bỏ qua hai sự kiện cũ có thể làm thiếu tiền: phải lưu từng fact bất biến với khóa duy nhất, rồi tính lại tổng hoặc áp dụng các fact chưa từng xử lý. **Version guard cho latest state không được sao chép sang ledger dạng cộng dồn**.

Khi nguồn không có version đáng tin cậy, có thể tải một **snapshot có chốt watermark** rồi nối phần thay đổi bằng CDC, hoặc tạm giữ event live trước khi đánh dấu snapshot đã hoàn thành. Cần xem xét tính ổn định của snapshot và khả năng phát hiện **gap**; đơn thuần “sort theo occurredAt” không cung cấp trật tự đáng tin khi clock lệch và event được phát trễ.

## 8. Replay và backfill khi luồng live vẫn tiếp tục

Hai luồng có thể cùng ghi vào một projection. Nếu tạm dừng toàn bộ hệ thống không khả thi, cần một chiến lược **phối hợp live + recovery**.

~~~mermaid
flowchart TD
    SOURCE["Nguồn sự kiện"] --> LIVE["Live consumer"]
    ARCHIVE["Archive / API lịch sử / CDC"] --> REC["Replay/Backfill worker"]
    LIVE --> VALIDATE["Validate schema và source identity"]
    REC --> VALIDATE
    VALIDATE --> TX["Một handler idempotent có version guard"]
    TX --> PROJ[("Projection DB")]
    TX --> AUDIT[("Recovery audit / metrics")]
    PROJ --> CHECK["Reconciliation trước khi đóng run"]
~~~

### 8.1. Chiến lược A: chạy song song với cập nhật có điều kiện

Với projection dạng **latest state** và upstream cung cấp version monotonic, có thể cho live và backfill cùng gọi **một handler**, với:

- Unique key trên eventId/source identity để chống xử lý trùng.
- Câu SQL cập nhật projection **chỉ nếu incoming version lớn hơn**.
- Ghi nhận riêng event đã thấy, event áp dụng, event stale và event conflict.
- Không thực thi side effect không idempotent khi phục hồi.

Ưu điểm là không cần dừng live. Giới hạn là **không bảo đảm thực thi mọi transition trung gian theo thứ tự**, nên chỉ phù hợp khi business cho phép latest-state semantics.

### 8.2. Chiến lược B: snapshot + change stream với watermark

Khi cần rebuild bảng lớn hoặc hệ thống nguồn cung cấp CDC:

1. Chọn một **mốc W** của nguồn (LSN, offset, sequence hoặc snapshot token có ý nghĩa xác định), và tạo snapshot nhất quán tại W.
2. Trong lúc nạp snapshot, giữ hoặc tiếp tục ghi nhận các thay đổi có **sourcePosition lớn hơn W** ở một luồng bền vững.
3. Nạp snapshot vào bảng mới/staging hoặc projection có version guard.
4. Áp các thay đổi sau W theo thứ tự/khóa cần thiết, kiểm tra đã đuổi kịp high watermark hiện tại.
5. Kiểm tra dữ liệu rồi **cutover** con trỏ đọc, bảng phục vụ API hoặc version projection theo phương án đã thiết kế.

Không mặc định các tham số **updatedSince=...** hoặc phân trang HTTP tạo snapshot nhất quán. Đối tác có thể cập nhật/xóa dữ liệu trong lúc bạn quét, gây **bỏ sót** hoặc **đếm trùng**. Nếu API không hỗ trợ snapshot/CDC, cần overlap window, dedup, reconciliation và chấp nhận giới hạn nhất quán.

### 8.3. Chiến lược C: tạm giữ và phát lại sau

Với workflow cần xử lý **mọi sự kiện theo thứ tự** (không chỉ trạng thái cuối), có thể dừng/đệm luồng live theo aggregate, nạp phần thiếu theo sourceVersion, rồi lần lượt mở đệm khi không còn gap. Cần theo dõi:

- **lastContiguousVersion** đã áp dụng, khác với **highestSeenVersion**.
- Các version đang thiếu và thời gian tối đa chờ.
- Giới hạn bộ nhớ/queue của pending event.
- Cách vận hành khi nguồn không thể cung cấp một version bị mất.

Nếu không thể phục hồi gap, không nên tự tăng lastContiguousVersion rồi tuyên bố dữ liệu đã đủ; cần chuyển incident sang xử lý ngoại lệ hoặc đối soát business.

## 9. Phát hiện và giới hạn phạm vi cần backfill

Backfill an toàn bắt đầu từ việc xác định **đúng phạm vi thiếu** và **nguồn phục hồi đáng tin**.

Ví dụ nguồn trả sự kiện theo thời gian; consumer bị lỗi trong khoảng 10:04–10:12:

~~~text
Khoảng nghi ngờ: [10:04, 10:12)
Khoảng truy xuất: [10:02, 10:14)  -- có overlap để tránh thiếu biên
Định danh ổn định: eventId / sourceVersion
Cutoff/snapshot: watermark tại thời điểm bắt đầu recovery
~~~

Khoảng overlap chỉ có ích nếu handler dedupe được. Với API phân trang, phải xét cách **cursor** vận hành dưới các bản ghi cập nhật và cách xử lý xóa; offset paging trên tập dữ liệu thay đổi thường không đảm bảo quét đầy đủ. Khi data source cho phép, dùng **cursor/snapshot token** hoặc **keyset pagination** theo khóa và version ổn định.

Một kế hoạch phục hồi nên ghi:

| Trường của recovery run | Vai trò |
| --- | --- |
| runId và operator/ticket | Audit: ai/chương trình nào đã chạy |
| sourceSystem + entity/tenant/filter | Khoanh vùng, tránh tác động dữ liệu không liên quan |
| mode và source version/schema | Phân biệt replay, backfill và reprocess có chủ ý |
| from/to hoặc source offset/LSN | Giới hạn phạm vi và hỗ trợ resume |
| high watermark/snapshot token | Điểm đối soát dữ liệu mục tiêu |
| dryRun, batchSize, rateLimit | Kiểm soát tải và kiểm tra trước khi ghi |
| counts theo trạng thái | Thấy applied, duplicate, stale, conflict, rejected |
| checkpoint và retry policy | Tiếp tục cùng run mà không tạo dữ liệu trùng |

Hạn chế cho phép operator chọn “từ đầu lịch sử đến hiện tại” không có giới hạn. Cần kiểm soát quyền, giới hạn khoảng thời gian, xác định dry-run, quota và cảnh báo khi recovery tạo tải cao.

## 10. Quy trình phục hồi an toàn qua các bước

### Bước 1. Xác minh source of truth và hợp đồng

Xác định hệ thống nào có quyền quyết định giá trị cuối cùng. Có thể có nhiều nguồn, nhưng phải có **thứ tự ưu tiên và quy tắc xung đột**; không chọn bản ghi “mới nhất theo giờ nhập” một cách vô thức. Kiểm tra schemaVersion, quyền truy cập, timezone, sourceVersion, delete/correction và dữ liệu lịch sử còn giữ được đến đâu.

### Bước 2. Ghi nhận scope và source watermark

Tạo bản ghi **recovery_run = PLANNED**, lưu source/range/cutoff, phiên bản code hoặc rule đã chọn và trace/operator. Nếu source có thể snapshot, lưu token để có thể chạy lại cùng phạm vi sau crash. Nếu không, ghi rõ giả định và thiết kế overlap/reconciliation.

### Bước 3. Dry-run và đánh giá ảnh hưởng

Đọc thử hoặc quét metadata để đếm **ứng viên**, phân phối độ tuổi, event type, schema, số key bị tác động và số thay đổi dự kiến. So sánh với số liệu nguồn, ước lượng tải DB/HTTP/broker và rủi ro side effect. **Dry-run** không được tạo bản ghi đã xử lý hay thực hiện lệnh có side effect; nếu muốn ghi audit dự kiến, dùng khu vực tách biệt.

### Bước 4. Chạy có giới hạn, cùng logic kiểm tra với live

Chuyển run sang **RUNNING**; đọc lịch sử từng trang/lô, validate và chuyển qua **cùng domain handler** với live. Handler ghi marker idempotency và projection trong một DB transaction. Giới hạn concurrency và tốc độ, có timeout HTTP, retry backoff, DLQ/quarantine và kiểm soát tải nguồn.

Khi cần chạy lại sau crash, tiếp tục bằng **cursor/checkpoint của recovery run** nhưng **không xem checkpoint là cách chống trùng duy nhất**. Luôn giữ unique key/version guard tại DB.

### Bước 5. Đối soát ở mức dữ liệu

Không kết luận “đã phục hồi” chỉ vì job không có exception. Cần so:

- Số event/bản ghi **source kỳ vọng** trong phạm vi với số identity đã tiếp nhận và số bản ghi bị loại có lý do.
- Tập business key/version/tombstone, tổng tiền hoặc trạng thái theo hợp đồng.
- Những **gap còn thiếu**, xung đột, bản ghi lỗi schema và số record chưa có nguồn phục hồi.
- High watermark của nguồn và của consumer để xác nhận recovery đã đuổi kịp mức yêu cầu.

### Bước 6. Đóng run và công bố kết quả

Chỉ đánh dấu **COMPLETED** khi tiêu chí đối soát được đáp ứng; có thể dùng **PARTIAL/FAILED** nếu còn chênh lệch cần can thiệp (schema ví dụ ở mục 6 cần mở rộng trạng thái nếu dùng PARTIAL). Giữ báo cáo về applied, duplicate, stale, conflict, rejected và khoảng thời gian dữ liệu đã khôi phục. Khi cần, phát **RecoveryRunCompleted** như một **sự kiện vận hành mới**, không tạo lại business event cũ.

## 11. Spring Boot và Spring Integration: tích hợp replay/backfill như thế nào?

Một thiết kế thực tế có thể gồm:

~~~text
Live:       RabbitMQ/Kafka adapter --> validate --> handler --> PostgreSQL
Backfill:   HTTP polling / Batch  --> validate --> handler --> PostgreSQL
Replay:     Event archive reader  --> validate --> handler --> PostgreSQL
                                                   |
                                                   +--> metrics/audit
                                                   +--> optional outbox
~~~

**Nguyên tắc:** các nguồn nạp có adapter khác nhau nhưng **chung business event contract và logic idempotent**. Chỉ đường truy vết/thông tin vận hành như ingestionMode và recoveryRunId là khác.

### 11.1. HTTP client và lịch sử phân trang

Một adapter HTTP phục hồi cần:

- API có filter theo **watermark** hoặc một cursor ổn định, có snapshot token nếu được hỗ trợ.
- Timeout theo request, retry có backoff và rate limit, xử lý HTTP 429/503 và lỗi hợp đồng dữ liệu.
- Validate trước khi ghi DB, quản lý schema evolution và các bản ghi **deleted/corrected**.
- Lưu cursor **sau khi lô dữ liệu đã được xử lý bền vững**; nếu cursor tiến trước commit business data thì crash có thể bỏ sót.

Có thể dùng Spring Batch **ItemReader/ItemProcessor/ItemWriter** để quét theo lô, với **JobParameters** đại diện recoveryRunId, source watermark và phạm vi; **ExecutionContext** chỉ lưu checkpoint kỹ thuật. Kết quả nghiệp vụ và audit phục hồi quan trọng vẫn nên được lưu ở bảng domain/audit, vì metadata Spring Batch không thay thế reconciliation.

### 11.2. Broker thông điệp: giới hạn khả năng phát lại

| Broker/cơ chế | Replay theo lịch sử | Lưu ý |
| --- | --- | --- |
| **Kafka topic có retention phù hợp** | Consumer group có thể đọc lại từ offset/timestamp còn được broker lưu | Offset không phải business event ID; giữ kiểm soát commit và side effect |
| **RabbitMQ classic/quorum queue thông thường** | Có redelivery message chưa ack; message đã ack/xóa không tự có để replay | Cần archive/outbox/event store riêng nếu muốn phát lại lịch sử đã tiêu thụ |
| **RabbitMQ Streams** | Hỗ trợ log có retention và đọc lại theo offset | Phụ thuộc loại stream, retention, client/protocol được dùng |
| **Database outbox / CDC / event archive** | Có thể làm nguồn replay khi còn dữ liệu | Dùng event ID/sequence gốc, schema và retention phù hợp |

**Redelivery không đồng nghĩa replay lịch sử.** Một RabbitMQ queue không phải event store vĩnh viễn, và Spring Integration **AMQP inbound adapter** không tạo khả năng đọc lại message đã ack ngoài những gì broker và cơ chế lưu lịch sử hỗ trợ.

Khi replay qua một broker mới, cần lưu **event identity** trong payload/header đã version hóa và tránh dùng deliveryTag, delivery timestamp hoặc offset mới làm khóa chống trùng nghiệp vụ.

### 11.3. Spring Integration adapter và transaction

Các flow có thể phân biệt nguồn bằng header nội bộ như **ingestionMode**, nhưng để an toàn cần biến **sourceSystem/eventId/sourceVersion** thành phần bắt buộc của contract. Các transformer không được vô tình sửa hoặc bỏ các trường này. Khi chuyển qua network, chỉ truyền các header phù hợp transport hoặc nhúng chúng trong envelope đã định nghĩa rõ.

**@Transactional** trên handler JDBC chỉ bảo vệ các thao tác trong DB thuộc transaction manager tương ứng. Nó **không tự rollback** một HTTP request, Kafka publish hoặc RabbitMQ acknowledgment. Nếu projection commit rồi consumer chết trước ack, broker có thể giao lại; **inbox** xử lý idempotency. Nếu cần từ cập nhật DB phát sự kiện mới, dùng **Transactional Outbox** trong cùng DB transaction rồi publish có confirm/retry, tránh dual-write trực tiếp.

**Cache** như Redis chỉ nên là phần tối ưu/đọc nhanh, có invalidation hoặc rebuild sau DB commit. Không dùng cache key dạng **eventId xử lý rồi** làm bằng chứng duy nhất để chống trùng nếu mất cache có thể tạo tác dụng nghiệp vụ lặp.

## 12. Tránh side effect khi khôi phục

Một consumer không chỉ cập nhật projection; nó có thể gửi email, gọi payment gateway, trừ điểm, kích hoạt shipping hoặc phát message cho service khác. Đây là nơi replay nguy hiểm nhất.

| Handler | Với event live | Với event replay/backfill |
| --- | --- | --- |
| **Xây dựng projection** | Cập nhật theo identity/version | Có thể áp dụng lại an toàn nếu idempotent |
| **Tính ledger giao dịch** | Ghi fact một lần theo transactionId | Chỉ chèn fact còn thiếu; đối soát tổng |
| **Gửi email/SMS** | Theo chính sách nghiệp vụ | Không tự gửi lại; chỉ replay nếu có yêu cầu sản phẩm rõ ràng |
| **Thu tiền/hoàn tiền** | API với idempotency key nghiệp vụ | Không gọi lại tùy ý; tra trạng thái và dùng khóa gốc |
| **Phát sự kiện tích hợp tiếp theo** | Qua outbox hoặc cơ chế đảm bảo | Xác định cần rebuild downstream hay không, chống gửi trùng |
| **Cập nhật cache** | Invalidate/refresh từ DB | Rebuild theo trạng thái mới nhất, không ghi lùi |

**Không nên viết điều kiện đơn giản “nếu mode=BACKFILL thì bỏ qua mọi side effect”** rồi cho rằng hệ thống đã nhất quán. Một event từng bị mất có thể **thật sự cần** tạo một tác động nghiệp vụ còn thiếu. Quyết định phải dựa trên **idempotency và trạng thái thực tế của tác động đích**:

1. Có side effect trước đó hay chưa? Kiểm tra bằng business key, outbox/inbox, ledger, API tra cứu trạng thái.
2. Nếu chưa có, có được thực hiện muộn không? Ví dụ thông báo giao hàng sau ba tuần có thể không còn ý nghĩa.
3. Nếu phải thực hiện, dùng **idempotency key gốc** và ghi dấu trong store bền vững.
4. Nếu không được phép tự động, đưa vào **manual review/quarantine** hoặc báo cáo chênh lệch.

Mô hình **“recovery mode”** vì thế là một phần bối cảnh điều phối và audit, không phải công tắc duy nhất quyết định sự thật nghiệp vụ.

## 13. Ma trận lỗi và cách phục hồi

| Tình huống lỗi | Điều có thể xảy ra | Cách thiết kế |
| --- | --- | --- |
| Crash sau commit projection, trước broker ack | Broker giao lại event | Inbox chống trùng; ack sau commit |
| Crash sau xử lý một page, trước lưu cursor | Page được đọc lại | Dedup/business key; checkpoint chỉ là tối ưu tiến độ |
| Cursor lưu trước DB commit | Có thể bỏ sót các bản ghi chưa bền vững | Commit dữ liệu trước cursor hoặc một transaction chung; reconciliation |
| Backfill v11 đến sau live v13 | Projection bị ghi lùi nếu update mù | Conditional update theo sourceVersion |
| Hai event khác payload cùng version | Dữ liệu nguồn mâu thuẫn | Conflict detection, quarantine, hỏi source of truth |
| Dữ liệu bị xóa được snapshot cũ đưa lại | Bản ghi bị “hồi sinh” | Tombstone + revision; xử lý delete |
| Replay event tích lũy vào số dư | Cộng tiền hai lần | Ledger theo event/transaction ID, không cộng nếu đã áp dụng |
| Thay đổi schema giữa lịch sử và hiện tại | Deserialize hoặc tính toán sai | Versioned schema, transform rõ, quarantine bản không hỗ trợ |
| Source API thay đổi giữa các trang | Bỏ sót/trùng records | Snapshot token/cursor ổn định, overlap, reconciliation |
| Broker/event archive hết retention | Không còn nguồn replay | Chấp nhận giới hạn; phục hồi từ snapshot/DB nguồn nếu có, báo gap |
| Consumer mới đọc replay và live cùng lúc | Lỗi race và tải tăng | Shared handler idempotent, bounded concurrency, backpressure |
| Sự kiện cũ kích hoạt thanh toán/email | Side effect lặp không thể đảo ngược | Business idempotency, trạng thái tác động, workflow phục hồi |

**Dấu hiệu phục hồi thành công** là các **bất biến dữ liệu** đúng, không phải chỉ thấy HTTP 200, Job COMPLETED, queue rỗng hoặc không còn exception.

## 14. Quan sát, đo lường và đối soát

Nên có metric theo **run, source và ingestionMode**:

| Nhóm chỉ số | Ví dụ |
| --- | --- |
| Khối lượng | candidates, fetched, validated, applied, duplicate, stale, conflict, rejected |
| Tiến độ | currentCursor, sourceHighWatermark, processedHighWatermark, gapCount |
| Độ trễ | processingLag = ingestedAt − occurredAt; runDuration, pageFetchLatency |
| Chất lượng | missingKeys, mismatchedVersions, staleSnapshotCount, audit discrepancies |
| Tài nguyên | DB lock wait, transaction rollback, HTTP 429/5xx, queue depth, thread pool saturation |
| Tác động ngoài | outbox backlog, sideEffectAlreadyDone, manuallyReviewed, compensations |

Trong log/trace, gắn **recoveryRunId, eventId, aggregateId, sourceVersion, attempt** để tra cứu một bản ghi. Trong metric Prometheus, tránh dùng eventId/runId bất kỳ làm nhãn có cardinality lớn; dùng source, mode, result và nhóm lỗi, còn ID cụ thể giữ trong log/trace/audit database.

Đối soát nên có **kiểm tra độc lập**:

- So đếm **distinct source event identities**, không chỉ tổng số lượt nhận (gồm cả retry).
- So trạng thái/tổng số theo business key với source ở watermark đã xác định.
- Kiểm tra độ đầy đủ của version/gap theo yêu cầu domain.
- Đối chiếu các effect quan trọng như bút toán, lệnh thu tiền, email cần gửi.
- Có hồ sơ kết quả, dữ liệu còn thiếu và người chịu trách nhiệm xử lý cuối.

Nếu còn gap không thể phục hồi vì nguồn hết retention, báo cáo **không đầy đủ** và chuyển sang phương án đối soát/snapshot/manual correction; không gán COMPLETED chỉ vì worker đã đọc hết dữ liệu còn lại.

## 15. Kiểm thử các tình huống thường bị bỏ sót

Trong Spring Boot, có thể dùng PostgreSQL thật qua **Testcontainers**, mock HTTP bằng **MockWebServer/WireMock**, và broker thật trong integration test khi cần kiểm chứng acknowledgment, offset và retry. Các ca quan trọng:

1. **Lặp cùng event ID:** đưa event v11 ba lần dưới các mode LIVE, REPLAY và BACKFILL; chỉ một effect idempotent được ghi nhận.
2. **Đến sai thứ tự:** apply v13 rồi v11/v12; projection vẫn v13 và trạng thái DELIVERED.
3. **Race hai instance:** đồng thời apply v12 và v13; unique key và conditional SQL phải giữ version cao nhất.
4. **Rollback:** gây lỗi trong transaction sau insert inbox; cả inbox và projection rollback để lần sau retry được.
5. **Event cùng version, payload khác:** phải được phát hiện conflict, không âm thầm bỏ qua.
6. **Ledger cộng dồn:** replay event có cùng transactionId; tổng tiền không tăng lần hai.
7. **Tombstone:** source xóa đơn ở v14; backfill snapshot cũ v12 không khôi phục đơn đã xóa.
8. **Crash giữa page:** xử lý thành công 50 record rồi chết trước cập nhật cursor; restart vẫn cho kết quả đúng và không tạo trùng.
9. **Backfill trong khi live chạy:** phát sự kiện live mới xen kẽ lịch sử, kiểm tra tính đúng theo sourceVersion và không vượt tải.
10. **Retention/thiếu nguồn:** không có event v12 trong archive; recovery_run phải báo gap, không tuyên bố đã đầy đủ.
11. **Schema migration:** replay sự kiện schemaVersion cũ khi code mới chạy; transform hoặc quarantine theo chính sách.
12. **Side effects:** replay của OrderCreated không tự gửi lại email hoặc lệnh payment đã hoàn tất; nếu còn thiếu, thực hiện qua quy trình idempotent được phê duyệt.

### Tiêu chí chấp nhận minh họa

Với order-42 có bốn sự kiện v10–v13, khi live đã cập nhật projection lên **v13/DELIVERED** trước lúc recovery đưa v11/v12 tới:

- Projection cuối giữ **v13/DELIVERED**.
- Các sự kiện lịch sử có identity gốc và occurredAt gốc; **không xuất hiện thêm một OrderCreated nghiệp vụ vào lúc chạy backfill**.
- Inbox/audit ghi nhận rõ đã nhìn thấy gì, áp dụng gì và vì sao các event cũ là stale.
- Retry hoặc crash rồi chạy lại cùng phạm vi **không nhân đôi giao dịch, thông báo hoặc dòng ledger**.
- Recovery chỉ đóng khi đã đối soát nguồn và các gap/exception đạt tiêu chí được đặt trước.

## 16. Checklist triển khai replay/backfill an toàn

- [ ] Có **nguồn dữ liệu lịch sử đáng tin**, retention đủ và scope/watermark rõ ràng.
- [ ] Phân biệt **eventTime, ingestedAt, processedAt**; không biến dữ liệu cũ thành sự kiện nghiệp vụ mới.
- [ ] Có **event/business identity ổn định** và **recoveryRunId** riêng cho hoạt động phục hồi.
- [ ] Có **inbox/dedup** và cơ chế **version/ordering** đúng với dạng dữ liệu (state, ledger, workflow).
- [ ] Xử lý tombstone, correction, schemaVersion và event conflict theo contract.
- [ ] Có chính sách cho **live + recovery đồng thời**, rate limit, backpressure, retry và checkpoint.
- [ ] Side effect HTTP, email, payment, cache và broker có quy tắc idempotency hoặc phục hồi riêng.
- [ ] Có dry-run, audit, trạng thái từng run, quarantine và **reconciliation** sau khi nạp.
- [ ] Có kiểm thử crash, duplicate, out-of-order, race, gap, deleted record và replay schema cũ.

**Nguyên tắc cần nhớ:** **Replay và backfill phục hồi các sự thật đã tồn tại trong lịch sử; thời điểm nạp lại không làm chúng trở thành sự kiện nghiệp vụ mới.** Muốn phục hồi an toàn, phải giữ **identity và thời gian nguồn**, chỉ áp dụng sự thay đổi hợp lệ theo **version/quy tắc domain**, kiểm soát side effect và chứng minh kết quả bằng **đối soát dữ liệu**.
