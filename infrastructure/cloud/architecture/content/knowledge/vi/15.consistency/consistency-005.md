# Transactional outbox, inbox và đồng bộ bằng CDC

Trong ứng dụng cloud, một dịch vụ thường vừa cập nhật dữ liệu của mình vừa cần thông báo cho các dịch vụ khác. Ví dụ, Booking Service xác nhận một đặt phòng trong database, sau đó phát sự kiện BookingConfirmed để Notification gửi email, Search cập nhật chỉ mục và Analytics ghi nhận giao dịch. Hai thao tác này nằm ở hai hệ thống khác nhau: database và message broker. Nếu database commit thành công nhưng ứng dụng dừng trước khi publish, dữ liệu đã đổi nhưng sự kiện không đến consumer. Nếu publish trước rồi database rollback, consumer lại nhận một thông báo về thay đổi chưa từng xảy ra.

Đây là bài toán **dual-write**. Ba kỹ thuật thường được kết hợp để giải quyết:

- **Transactional outbox:** ghi thay đổi nghiệp vụ và bản ghi sự kiện cần phát trong cùng transaction của database.
- **Transactional inbox / deduplication:** ghi nhận sự kiện đã xử lý cùng transaction với thay đổi dữ liệu của consumer, giúp chịu được message giao lại.
- **Change Data Capture (CDC):** phát hiện thay đổi dữ liệu từ database, thường bằng cách đọc transaction log hoặc cơ chế ghi nhận thay đổi mà nền tảng cung cấp, rồi chuyển thay đổi đó tới broker hoặc hệ thống đích.

Các kỹ thuật này bổ sung cho nhau. Outbox giúp bảo đảm ý định phát event được lưu cùng dữ liệu nguồn; CDC có thể vận chuyển bản ghi outbox mà không cần polling liên tục; inbox giúp consumer xử lý trùng an toàn. Chúng không tự tạo ra một transaction ACID xuyên nhiều database, cũng không mặc nhiên bảo đảm exactly-once end-to-end.

Bài học thuộc chương **Tính nhất quán** của module **CLOUD_ARCHITECTURE**. Khi thiết kế kiến trúc ứng dụng trên đám mây, mục tiêu là giữ dữ liệu nghiệp vụ đúng trong khi các dịch vụ trao đổi sự kiện bất đồng bộ, đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao dual-write giữa database và broker có thể làm mất hoặc phát sai sự kiện.
2. Thiết kế transactional outbox để ghi trạng thái nghiệp vụ và event record trong cùng transaction.
3. Thiết kế inbox/deduplication để consumer an toàn khi nhận message trùng hoặc được giao lại.
4. Phân biệt CDC dựa trên transaction log với polling, trigger và timestamp-based extraction.
5. Chọn cách vận chuyển outbox phù hợp: polling publisher, CDC connector hoặc cơ chế tích hợp do nền tảng cung cấp.
6. Xử lý ordering, replay, schema evolution, delete/tombstone, snapshot và checkpoint.
7. Thiết kế retry, đối soát, observability, bảo mật và khôi phục cho pipeline sự kiện.
8. Đánh giá consistency lag, tính đúng đắn và chi phí của mô hình trong kiến trúc cloud.

## 2. Bài toán dual-write: vì sao hai thao tác riêng lẻ không an toàn?

### 2.1. Cập nhật database rồi publish event

Một cách triển khai trực quan:

~~~text
1. UPDATE bookings SET status = 'CONFIRMED'
2. COMMIT database transaction
3. PUBLISH BookingConfirmed to broker
~~~

Nếu service crash giữa bước 2 và 3, booking đã xác nhận nhưng consumer không nhận event. Search index, notification hoặc hệ thống downstream có thể không bao giờ biết thay đổi đã xảy ra.

### 2.2. Publish event rồi cập nhật database

Đảo thứ tự cũng không giải quyết vấn đề:

~~~text
1. PUBLISH BookingConfirmed to broker
2. UPDATE bookings SET status = 'CONFIRMED'
3. COMMIT database transaction
~~~

Nếu bước 2 hoặc 3 thất bại sau khi event đã được phát, consumer có thể hành động dựa trên một trạng thái không tồn tại trong nguồn dữ liệu chuẩn.

### 2.3. Ma trận lỗi của dual-write

| Database commit | Publish event | Kết quả |
|---|---|---|
| Thành công | Thành công | Trạng thái và event khớp |
| Thành công | Thất bại | Mất thông báo; consumer không cập nhật |
| Thất bại | Thành công | Event mô tả dữ liệu chưa commit |
| Không rõ kết quả do timeout | Không rõ kết quả | Có thể phát trùng hoặc bỏ sót khi retry |

Một transaction database thông thường chỉ bảo vệ các thay đổi trong database đó. Broker là hệ thống độc lập, nên không thể giả định một lệnh COMMIT bao trùm cả database và broker nếu không có giao thức distributed transaction được hỗ trợ và chủ động cấu hình. Ngay cả khi nền tảng có transaction broker, side effect ở API bên ngoài vẫn là một ranh giới khác.

## 3. Transactional outbox

### 3.1. Ý tưởng

Outbox là một bảng hoặc vùng dữ liệu lưu các event đang chờ phát. Trong **cùng transaction** với cập nhật nghiệp vụ, service ghi thêm một bản ghi outbox:

1. Kiểm tra và cập nhật dữ liệu có thẩm quyền.
2. Tạo event record trong outbox.
3. Commit transaction.
4. Một publisher riêng đọc outbox và chuyển event tới broker.

~~~mermaid
flowchart LR
    APP[Booking Service] --> TX[Database transaction]
    TX --> B[(Bookings table)]
    TX --> O[(Outbox table)]
    O --> PUB[Outbox publisher / CDC]
    PUB --> BUS[(Message broker)]
    BUS --> C[Consumers]
~~~

Nếu database transaction rollback, cả cập nhật booking và event record đều không tồn tại. Nếu transaction commit, event record sẽ còn trong outbox để publisher phát sau đó. Khoảng trống giữa commit database và publish broker được chuyển thành công việc có thể retry và đối soát.

### 3.2. Schema outbox tham khảo

~~~sql
CREATE TABLE outbox_events (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id   VARCHAR(120) NOT NULL,
    aggregate_seq  BIGINT,
    event_type     VARCHAR(120) NOT NULL,
    event_version  INTEGER NOT NULL,
    occurred_at    TIMESTAMP NOT NULL,
    payload        JSON NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);

CREATE INDEX ix_outbox_pending
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
~~~

Đây là schema minh họa; kiểu JSON, partial index, timestamp và cú pháp phụ thuộc database. Có thể cần thêm tenant_id, correlation_id, trạng thái lease, số lần thử và metadata tracing. Không lưu secret hoặc payload nhạy cảm không cần thiết chỉ vì outbox nằm trong database nội bộ.

### 3.3. Ghi nghiệp vụ và outbox trong cùng transaction

~~~sql
BEGIN;

UPDATE bookings
SET status = 'CONFIRMED',
    version = version + 1
WHERE booking_id = 'booking_913'
  AND status = 'PENDING';

INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id, aggregate_seq,
    event_type, event_version, occurred_at, payload, created_at
)
VALUES (
    'evt_01JXY99', 'Booking', 'booking_913', 7,
    'BookingConfirmed', 1, CURRENT_TIMESTAMP,
    '{"bookingId":"booking_913","status":"CONFIRMED"}',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Trong code thực tế, phải kiểm tra số dòng update hoặc trạng thái trước đó để bảo đảm đúng một transition hợp lệ được ghi. Nếu update không thành công vì booking không còn PENDING, không được tạo event xác nhận. Có thể dùng transaction với điều kiện, constraint hoặc cơ chế khóa phù hợp để bảo vệ invariant.

### 3.4. Outbox ghi ý định phát event, không phải nơi lưu nghiệp vụ

Outbox thường có vòng đời ngắn hơn dữ liệu nghiệp vụ: được tạo cùng transaction, vận chuyển sau đó, giữ lại đủ cho retry/đối soát và xóa/archive theo chính sách. Nguồn dữ liệu chuẩn vẫn là bảng hoặc aggregate mà service sở hữu.

Không nên dùng trạng thái published_at IS NOT NULL để suy ra mọi consumer đều xử lý xong. Nó chỉ thể hiện publisher đã ghi nhận việc phát theo semantics đã chọn; trạng thái consumer, delivery và side effect thuộc các luồng khác.

## 4. Vận chuyển outbox: polling hay CDC?

Có hai cách phổ biến để đưa bản ghi outbox tới broker.

### 4.1. Polling publisher

Một tiến trình định kỳ truy vấn các hàng chưa được publish, chiếm quyền xử lý và gửi message:

~~~mermaid
flowchart TD
    TIMER[Timer / Worker] --> Q[Query pending outbox]
    Q --> CLAIM[Claim batch / lease]
    CLAIM --> SEND[Publish to broker]
    SEND -->|Acknowledged| MARK[Mark published]
    SEND -->|Error / timeout| RETRY[Keep pending / retry]
    RETRY --> Q
~~~

**Ưu điểm:**

- Dễ hiểu, dễ triển khai nếu volume vừa phải.
- Không cần đọc transaction log hoặc quản lý connector CDC.
- Có thể kiểm soát batch, nhịp polling và trạng thái publish trong database.

**Đánh đổi:**

- Có polling latency giữa commit và lần truy vấn tiếp theo.
- Truy vấn liên tục tạo database load, index maintenance và contention.
- Nhiều publisher có thể tranh cùng một hàng nếu không claim/lease an toàn.
- Cần xử lý crash sau publish nhưng trước khi mark published.

Một chiến lược có thể dùng SELECT ... FOR UPDATE SKIP LOCKED hoặc cơ chế lease tương đương, tùy database, để nhiều worker claim batch mà ít tranh chấp. Nhưng không nên giả định cú pháp hoặc lock semantics giống nhau ở mọi hệ quản trị.

### 4.2. CDC dựa trên transaction log

Change Data Capture ghi nhận thay đổi từ database và chuyển chúng tới hệ thống downstream. Với log-based CDC, connector đọc transaction log (ví dụ binlog, WAL hoặc cơ chế tương đương), lấy các thay đổi đã commit và phát chúng theo checkpoint/offset.

~~~mermaid
flowchart LR
    APP[Application transaction] --> DB[(Database)]
    DB --> LOG[(Transaction log)]
    LOG --> CDC[CDC connector]
    CDC --> ROUTE[Filter / Transform]
    ROUTE --> BUS[(Broker / Stream)]
    BUS --> CONSUMERS[Consumers]
~~~

**Ưu điểm:**

- Có thể phát hiện thay đổi gần thời gian thực mà không polling từng hàng.
- Ít truy vấn đọc bảng outbox lặp lại khi volume lớn.
- Có thể ghi nhận insert/update/delete đã commit theo semantics log và connector.
- Hỗ trợ chuyển đổi dữ liệu thay đổi sang stream cho nhiều consumer.

**Đánh đổi:**

- Cần cấu hình quyền đọc log và giữ log đủ lâu.
- Connector có checkpoint, offset, schema history và trạng thái vận hành riêng.
- Thay đổi cấu trúc database, failover và phục hồi connector cần quy trình.
- CDC có thể phát nhiều loại thay đổi; phải filter đúng bảng/operation để tránh biến mọi cập nhật nội bộ thành integration event.

### 4.3. CDC không đồng nghĩa với outbox

CDC là kỹ thuật quan sát thay đổi dữ liệu. Nó có thể đọc bảng nghiệp vụ trực tiếp, bảng audit, hoặc bảng outbox. Transactional outbox là **mẫu dữ liệu và transaction** bảo đảm ý định phát event cùng commit với dữ liệu nghiệp vụ. Log-based CDC là **cơ chế vận chuyển/quan sát thay đổi**.

Kết hợp outbox + CDC có thể mang lại:

- Event contract được thiết kế rõ trong bảng outbox thay vì suy luận từ từng cột nghiệp vụ.
- Tính nguyên tử giữa cập nhật nghiệp vụ và ý định phát event.
- Vận chuyển thay đổi sau commit qua transaction log.

CDC trực tiếp từ bảng nghiệp vụ có thể phù hợp cho data replication hoặc analytics, nhưng nếu dùng để tạo domain event cho integration, cần cẩn trọng về ngữ nghĩa, thứ tự, trạng thái trung gian và việc một thay đổi nội bộ có thực sự là event nghiệp vụ hay không.

### 4.4. So sánh polling, CDC và trigger

| Cơ chế | Cách phát hiện thay đổi | Lợi thế | Hạn chế |
|---|---|---|---|
| Polling | Truy vấn hàng chưa xử lý theo lịch | Đơn giản, dễ kiểm soát bằng SQL | Độ trễ polling, DB load, claim/locking |
| Log-based CDC | Đọc transaction log đã commit | Gần thời gian thực, giảm polling bảng | Connector/log retention/schema/offset phức tạp |
| Database trigger | Trigger ghi thêm record hoặc gọi cơ chế nội bộ khi DML xảy ra | Cùng transaction và gần nơi ghi dữ liệu | Có thể tăng coupling và ảnh hưởng write latency; logic trigger khó version/review |
| Timestamp polling | Lọc bản ghi có updated_at mới | Dễ bắt đầu cho batch đồng bộ | Dễ bỏ sót khi timestamp trùng/lệch, delete khó phát hiện, không có transaction sequence chuẩn |

Timestamp polling không thay thế được CDC log-based cho yêu cầu cần ghi nhận đầy đủ update/delete và thứ tự transaction. Trigger cũng không nên gọi network API trực tiếp trong transaction database; điều này kéo dài khóa và làm giao dịch phụ thuộc dịch vụ ngoài.

## 5. Publisher: phát event an toàn

### 5.1. Trình tự gửi và đánh dấu

Với polling publisher, cách phổ biến là:

1. Claim các hàng pending bằng lease hoặc lock.
2. Publish event tới broker.
3. Chờ xác nhận theo semantics của broker.
4. Đánh dấu hàng đã publish, ghi timestamp/attempt.

Có một cửa sổ lỗi: broker đã nhận event nhưng publisher crash trước khi cập nhật published_at. Khi chạy lại, publisher có thể phát event lần nữa. Đây là lý do consumer vẫn phải chịu duplicate.

Nếu publisher đánh dấu trước khi broker xác nhận rồi mới gửi, crash sau khi mark có thể làm mất event. Vì vậy, thứ tự và trạng thái phải ưu tiên không mất ý định phát, chấp nhận khả năng giao lặp và thiết kế idempotency.

### 5.2. Claim an toàn với nhiều publisher

Nếu nhiều worker cùng xử lý outbox:

- Mỗi record cần được claim độc quyền tạm thời hoặc chia partition công việc ổn định.
- Lease phải có thời hạn để worker chết không giữ record mãi.
- Worker phải kiểm tra lease/owner khi cập nhật trạng thái.
- Batch size và concurrency cần giới hạn theo throughput broker và database.
- Thời gian xử lý phải tính đến network timeout và lease expiry.

Không nên giữ transaction database mở trong suốt thời gian gọi broker nếu điều đó tạo lock dài và giảm throughput. Một mô hình claim-lease có thể commit nhanh rồi publish ngoài transaction, sau đó cập nhật kết quả bằng owner token/version. Cần chấp nhận khả năng lease hết hạn khi request vẫn đang chạy và consumer nhận duplicate.

### 5.3. Thứ tự event theo aggregate

Nếu booking chuyển PENDING → CONFIRMED → CANCELLED, consumer có thể cần nhận theo đúng thứ tự cho cùng booking. Có thể ghi aggregate_seq hoặc version tăng đơn điệu trong transaction nghiệp vụ và dùng aggregate ID làm partition/message-group key.

Những điều phải quyết định:

- Publisher có giữ thứ tự theo aggregate khi gửi song song không?
- Broker giữ thứ tự trong queue group hoặc partition nào?
- Retry một event cũ có chặn event mới cùng aggregate không?
- Consumer có từ chối event có sequence cũ hơn trạng thái hiện tại không?

Không nên giả định toàn bộ event trên hệ thống có thứ tự toàn cục. Thường chỉ cần thứ tự trong phạm vi một aggregate/entity.

## 6. Transactional inbox và deduplication phía consumer

### 6.1. Vì sao consumer vẫn có thể nhận lặp?

Consumer có thể xử lý message thành công, commit dữ liệu, rồi crash trước khi acknowledge. Broker không biết side effect đã hoàn thành nên giao message lần nữa. Stream consumer có thể ghi dữ liệu thành công nhưng crash trước khi commit offset, rồi đọc record lại sau khi khởi động.

Delivery at-least-once vì vậy đòi hỏi consumer xử lý lặp an toàn.

### 6.2. Inbox là gì?

Inbox là bảng hoặc kho lưu dấu event đã được consumer nhận/xử lý. Consumer ghi event ID vào inbox và cập nhật dữ liệu của mình trong cùng transaction:

~~~mermaid
flowchart TD
    BROKER[(Broker)] --> C[Consumer]
    C --> TX[Consumer DB transaction]
    TX --> CHECK{eventId đã có?}
    CHECK -->|Có| SKIP[Bỏ qua side effect lặp]
    CHECK -->|Chưa| INBOX[Insert inbox record]
    INBOX --> UPDATE[Update consumer data]
    UPDATE --> COMMIT[Commit]
    COMMIT --> ACK[Acknowledge / commit progress]
~~~

Nếu event đã được xử lý trước đó, consumer không lặp side effect và có thể acknowledge bản giao trùng. Nếu transaction rollback, cả inbox record và cập nhật dữ liệu đều rollback; broker sẽ giao lại theo semantics.

### 6.3. Schema inbox tham khảo

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa chính gồm consumer name và event ID vì cùng event có thể được nhiều consumer độc lập xử lý. Nếu mọi subscriber dùng chung một dedup table không phân biệt consumer, subscriber đầu tiên có thể khiến subscriber khác bị bỏ qua nhầm.

### 6.4. Pseudocode consumer

~~~text
receive(message)

BEGIN DATABASE TRANSACTION
    inserted = INSERT processed_events(consumer_name, event_id)
               ON CONFLICT DO NOTHING

    IF inserted:
        apply_business_update(message.data)
    ELSE:
        do_not_repeat_business_update()
COMMIT

ACK message only after commit succeeds
~~~

Pseudo-code thể hiện nguyên tắc. Cần dùng transaction isolation và câu lệnh kiểm tra insert phù hợp database. Nếu apply_business_update gọi API bên ngoài, side effect đó không nằm trong transaction inbox; cần thêm outbox, idempotency API hoặc trạng thái trung gian.

### 6.5. Chính sách lưu inbox

Inbox không nhất thiết phải lưu mọi event mãi mãi. Thời hạn retention cần dài hơn cửa sổ có thể replay/redelivery và yêu cầu đối soát. Nếu xóa dedup record quá sớm rồi broker replay event cũ, consumer có thể thực hiện side effect lại. Cần quy định:

- Broker retention hoặc khoảng thời gian DLQ có thể redrive.
- Thời hạn retry và replay trong quy trình vận hành.
- Nghiệp vụ nào cần dedup lâu dài qua khóa unique nghiệp vụ.
- Cách archive/xóa inbox theo chính sách dữ liệu.

Đối với giao dịch tài chính hoặc thao tác không thể lặp, event inbox có thể kết hợp với constraint unique theo payment reference/order ID để bảo vệ ở cấp nghiệp vụ.

## 7. CDC: snapshot, transaction log, offset và checkpoint

### 7.1. Snapshot ban đầu và thay đổi tiếp theo

Khi bắt đầu CDC, connector có thể cần chụp snapshot dữ liệu hiện có để downstream có trạng thái ban đầu, sau đó mới áp dụng các thay đổi phát sinh. Quá trình phải phối hợp ranh giới snapshot với vị trí transaction log để tránh bỏ sót hoặc áp dụng sai thứ tự.

Một số connector hỗ trợ initial snapshot, incremental snapshot hoặc chế độ khởi động từ vị trí log đã lưu. Cách cụ thể khác nhau giữa database và connector. Cần kiểm thử:

- Snapshot có khóa/đọc nhất quán như thế nào?
- Ghi mới trong lúc snapshot được xử lý ra sao?
- Khi snapshot lỗi giữa chừng, có thể resume từ đâu?
- Làm sao xác định downstream đã nhận đủ trạng thái ban đầu?

### 7.2. Offset và checkpoint

CDC connector lưu vị trí đã đọc trong transaction log, chẳng hạn binlog position, WAL LSN hoặc một cursor tương ứng. Khi connector restart, nó tiếp tục từ checkpoint hoặc vị trí đã commit.

Nếu checkpoint được lưu trước khi event thực sự được gửi bền vững tới broker, thay đổi có thể bị bỏ qua. Nếu gửi thành công nhưng checkpoint chưa kịp lưu, event có thể phát lại. Vì vậy, semantics của offset/checkpoint và khả năng duplicate cần được hiểu rõ.

### 7.3. Transaction boundary và commit order

Database log có transaction và commit order. Connector có thể phát record thay đổi theo từng row hoặc một envelope đại diện transaction, tùy nền tảng. Khi một transaction cập nhật nhiều bảng, consumer cần biết các record liên quan có được nhóm và phát theo thứ tự ra sao.

Nếu downstream chỉ cần event outbox sau commit, filter connector nên tập trung vào outbox table và dùng transaction metadata có thể cần thiết cho thứ tự. Nếu CDC trực tiếp nhiều bảng nghiệp vụ, không tự suy ra một domain event từ mỗi row change mà chưa xác định invariant và ý nghĩa nghiệp vụ.

### 7.4. Insert, update, delete và tombstone

CDC có thể ghi nhận:

- **INSERT:** hàng mới được tạo.
- **UPDATE:** một số cột thay đổi; connector có thể xuất before/after hoặc chỉ after tùy cấu hình.
- **DELETE:** hàng bị xóa; có thể biểu diễn bằng record delete hoặc tombstone.
- **TRUNCATE/DDL:** thay đổi cấu trúc hoặc xóa hàng loạt; phạm vi hỗ trợ tùy connector.

Consumer phải biết cách diễn giải tombstone và delete. Nếu chỉ đồng bộ insert/update, dữ liệu downstream có thể giữ record đã bị xóa ở nguồn. Với dữ liệu có nghĩa vụ xóa, phải xem cả bản sao, archive, search index và cache.

### 7.5. Transaction log retention

Nếu connector ngừng hoạt động lâu hơn thời gian database giữ transaction log, vị trí đã checkpoint có thể không còn tồn tại. Connector không thể tiếp tục từ log đã bị loại bỏ; có thể cần snapshot lại hoặc quy trình phục hồi riêng.

Do đó, capacity và vận hành CDC cần tính:

- Tốc độ phát sinh log và thời gian retention.
- Thời lượng gián đoạn connector có thể chịu.
- Băng thông và tốc độ tiêu thụ khi connector khởi động lại.
- Snapshot time và ảnh hưởng tới tải database.
- Lưu trữ schema history, offset và connector config.

## 8. CDC và outbox cùng nhau trong kiến trúc cloud

### 8.1. Luồng kiến trúc tham khảo

~~~mermaid
flowchart TB
    API[Booking API] --> TX[DB transaction]
    TX --> BOOK[(Bookings)]
    TX --> OUT[(Outbox events)]
    DBLOG[(Transaction log)] --> CDC[CDC connector]
    OUT --> DBLOG
    CDC --> FILTER[Filter outbox + serialize]
    FILTER --> TOPIC[(Booking events topic)]
    TOPIC --> CONSUMER[Consumer group]
    CONSUMER --> INBOX[(Inbox / processed events)]
    INBOX --> PROJ[(Search projection)]
    TOPIC --> NOTIFY[Notification consumer]
~~~

Outbox được ghi cùng transaction với trạng thái booking. CDC đọc log để phát những record outbox đã commit; connector map event record thành contract trên topic. Các consumer có thể giữ inbox/dedup riêng.

### 8.2. Những lớp đảm bảo khác nhau

| Lớp | Cơ chế | Bảo đảm hướng tới | Không tự bảo đảm |
|---|---|---|---|
| Nghiệp vụ nguồn | Database transaction + outbox row | Event intent commit cùng dữ liệu nguồn | Broker đã nhận event |
| Vận chuyển | Poller hoặc CDC connector + broker ack/checkpoint | Phát event bền vững theo semantics của pipeline | Không có duplicate |
| Consumer | Inbox + business update cùng transaction | Không lặp cập nhật nội bộ cho cùng event ID | Side effect ngoài database |
| Tích hợp ngoài | Idempotency reference + reconciliation | Giảm nguy cơ lặp side effect và xử lý kết quả không rõ | Exactly-once tuyệt đối giữa mọi hệ thống |
| Vận hành | Retry, DLQ, replay, alert và runbook | Phát hiện và khôi phục lỗi có kiểm soát | Không bao giờ có lỗi hoặc mất dữ liệu |

### 8.3. Đừng nhầm CDC với event sourcing

**CDC** ghi nhận các thay đổi đã xảy ra trong database để đồng bộ hoặc xử lý tiếp. **Event sourcing** dùng event như mô hình lưu trữ nguồn của trạng thái nghiệp vụ; trạng thái hiện tại được tái tạo từ chuỗi event theo quy tắc domain.

Một pipeline CDC từ bảng bookings không tự biến ứng dụng thành event-sourced system. Tương tự, bảng outbox là danh sách event cần phát, không nhất thiết là nguồn chuẩn để dựng lại toàn bộ trạng thái nghiệp vụ.

## 9. Ordering, duplicate và tính nhất quán

### 9.1. Event version và aggregate sequence

Event nên có:

- eventId ổn định để deduplicate.
- aggregateId hoặc entity ID để nhóm sự kiện cùng thực thể.
- aggregateVersion/sequence để phát hiện event cũ hoặc thiếu.
- occurredAt để tham khảo thời gian nghiệp vụ, không dùng như bằng chứng duy nhất của ordering.
- correlationId để truy vết một luồng xử lý.

Nếu consumer nhận sequence 9 sau sequence 7, nó cần biết sequence 8 đã thiếu hay event 9 là bản cập nhật mới đủ thông tin. Tùy mô hình, consumer có thể buffer, query owner service, retry hoặc đưa event vào vùng cần đối soát.

### 9.2. At-least-once là giả định an toàn

Ngay cả khi broker hoặc connector có cơ chế giao nhận mạnh, publisher/consumer vẫn có thể crash ở ranh giới giữa side effect và acknowledgement/checkpoint. Thiết kế nên giả định một event có thể xuất hiện nhiều lần và bảo vệ bằng idempotency/deduplication.

### 9.3. Eventual consistency và lag

Outbox + CDC tạo luồng cập nhật bất đồng bộ. Thời gian từ khi database commit tới khi consumer xử lý xong phụ thuộc:

- Log flush và connector polling/streaming.
- Connector lag và batch size.
- Broker throughput, partition và throttling.
- Consumer capacity, retry và dependency downstream.
- Backlog, rebalance và xử lý lỗi.

Do đó, hệ thống cần một SLO hoặc ngưỡng freshness cho từng luồng: ví dụ search projection cập nhật trong vài giây ở tải bình thường; báo cáo phân tích có thể trễ lâu hơn. Không nên áp một con số chung cho mọi event.

### 9.4. Read-after-write

Nếu người dùng vừa xác nhận booking rồi lập tức xem lịch sử, read model do CDC cập nhật có thể chưa bắt kịp. Một số cách:

- Trả trạng thái từ nguồn Booking có thẩm quyền ngay sau commit.
- Truy vấn nguồn chuẩn cho một khoảng thời gian sau ghi.
- Truyền aggregate version và chờ projection đạt version cần thiết.
- Trả trạng thái “đang đồng bộ” khi nghiệp vụ cho phép.

Không nên báo thất bại chỉ vì projection chưa thấy event mới; điều đó có thể làm client gửi lại một thao tác đã thành công.

## 10. Xử lý lỗi và phục hồi

### 10.1. Publisher lỗi

| Tình huống | Hành vi cần có |
|---|---|
| Database transaction rollback | Không có outbox record; không phát event |
| Commit thành công, broker tạm lỗi | Outbox còn pending; retry theo policy |
| Broker nhận event, publisher crash trước mark | Có thể publish trùng; consumer dedup |
| Record bị claim bởi worker chết | Lease hết hạn và worker khác claim lại |
| Payload không hợp lệ | Đưa vào trạng thái lỗi/DLQ theo quy trình, không retry vô hạn |
| Publisher bị quá tải | Giới hạn batch/concurrency, theo dõi backlog và oldest age |

### 10.2. CDC connector lỗi

Khi connector không đọc được log, thiếu quyền, lỗi schema hoặc mất checkpoint:

1. Xác định vị trí log cuối cùng đã checkpoint và log hiện có còn bao phủ không.
2. Kiểm tra trạng thái broker: record cuối đã được phát chưa, có khả năng duplicate không?
3. Kiểm tra connector config, schema history, credential, network và quota.
4. Không reset offset hoặc chạy lại snapshot tùy tiện khi chưa đánh giá ảnh hưởng downstream.
5. Nếu phải snapshot lại, xác định cách xử lý dữ liệu trùng/đè và delete/tombstone.
6. Sau khi phục hồi, kiểm tra lag về bình thường và đối soát số lượng/version ở nguồn và đích.

### 10.3. Consumer lỗi

Consumer cần retry transient error, đưa poison message vào DLQ, giữ inbox và trạng thái xử lý nhất quán, không commit offset trước khi ghi dữ liệu bền vững theo thiết kế. Khi redrive, phải kiểm tra side effect đã xảy ra hay chưa và dùng cùng idempotency key.

### 10.4. Reconciliation là lớp bảo vệ bổ sung

Với dữ liệu quan trọng, có thể chạy tác vụ đối soát định kỳ:

- So sánh số lượng/sequence booking đã commit với event đã phát.
- Tìm outbox record quá tuổi mà chưa được publish.
- Tìm consumer lag hoặc event thiếu trong projection.
- So khớp trạng thái payment với provider theo reference.
- Rebuild projection từ nguồn hoặc stream lưu giữ khi cần.

Đối soát không thay thế transaction và idempotency, nhưng giúp phát hiện sai lệch còn sót lại do lỗi hiếm hoặc giới hạn quan sát.

## 11. Quản lý schema và thay đổi cấu trúc

### 11.1. Outbox payload nên là contract tích hợp

Không nhất thiết serialize toàn bộ row của database vào payload. Nếu consumer phụ thuộc trực tiếp mọi cột nội bộ, một migration database có thể trở thành breaking change cho toàn hệ thống. Thiết kế integration event chỉ chứa field có ý nghĩa nghiệp vụ và được công bố có version.

### 11.2. Schema evolution

Thông thường, thêm field optional với semantics và default rõ ràng dễ tương thích hơn xóa/đổi tên field hoặc đổi kiểu. Nhưng compatibility phụ thuộc serializer/deserializer và hành vi consumer; cần test thực tế.

Khi CDC trực tiếp table, thay đổi DDL có thể ảnh hưởng connector, schema history và consumer. Cần quy trình expand–migrate–contract, kiểm thử cả schema cũ/mới và kế hoạch rollback.

### 11.3. Không phát mọi thay đổi nội bộ thành event công khai

Một record có thể thay đổi vì sửa typo, cập nhật timestamp hoặc điều chỉnh cột kỹ thuật. Nếu mỗi thay đổi đều phát event integration, consumer nhận nhiều dữ liệu thừa và bị gắn với schema nội bộ. Hãy dùng outbox để owner quyết định rõ event nghiệp vụ nào được công bố; dùng CDC trực tiếp cho replication/analytics khi phù hợp.

## 12. Bảo mật và quản trị dữ liệu

### 12.1. Quyền truy cập database và log

CDC connector thường cần quyền đọc transaction log và metadata schema. Quyền này có thể nhạy cảm hơn quyền SELECT thông thường. Nên:

- Cấp tài khoản riêng cho connector với quyền tối thiểu mà nền tảng yêu cầu.
- Giới hạn database/schema/table được theo dõi.
- Bảo vệ credential bằng secret manager và rotation.
- Mã hóa đường truyền tới database, broker và schema registry.
- Theo dõi thay đổi connector, offset reset, snapshot, publication và replication slot.
- Không chia sẻ credential quản trị database cho nhiều consumer.

### 12.2. Event payload và history

Outbox, broker, inbox, DLQ, connector log và backup có thể chứa dữ liệu cá nhân hoặc thông tin giao dịch. Cần phân loại payload, tối thiểu hóa trường, mã hóa, phân quyền đọc/replay và đặt retention phù hợp.

### 12.3. Region và chủ quyền dữ liệu

Nếu database nguồn ở một region nhưng broker, CDC connector, archive hoặc analytics pipeline ở region khác, dữ liệu vẫn có thể được chuyển qua biên giới. Cần đánh giá toàn bộ luồng:

Database → transaction log → connector → broker → consumer → projection / archive / logs

Không chỉ kiểm tra vị trí database. Region lưu log, backup, checkpoint, DLQ và telemetry cũng có thể thuộc phạm vi chính sách. Quy định pháp lý cụ thể cần được xác minh theo loại dữ liệu, hợp đồng và địa điểm xử lý thực tế.

## 13. Hiệu năng, capacity và chi phí

### 13.1. Outbox table growth

Nếu publisher không dọn bản ghi đã phát, outbox sẽ tăng liên tục. Cần retention, partition/archive hoặc cleanup job theo policy. Không xóa record quá sớm khi cần điều tra, replay hoặc đối soát.

### 13.2. Polling cost

Polling quá thường xuyên tạo truy vấn kể cả khi không có event. Polling quá thưa làm tăng event latency. Batch size lớn cải thiện throughput nhưng giữ lock/lease lâu và tăng memory; batch quá nhỏ tăng round-trip.

### 13.3. CDC throughput và log retention

CDC cần đủ băng thông để theo kịp tốc độ phát sinh log. Nếu connector chậm, log có thể tăng và retention không đủ. Snapshot lớn có thể tạo tải đọc lên database; connector restart có thể cần đọc bù backlog dài.

### 13.4. Broker và consumer capacity

Partition, replication factor, retention, message size, compression, subscription và consumer concurrency ảnh hưởng storage, CPU, network và chi phí. Consumer chậm làm lag tăng; tăng worker chỉ có ích nếu partition và dependency cho phép song song.

### 13.5. Bảng so sánh vận hành

| Tiêu chí | Polling outbox | Outbox + CDC |
|---|---|---|
| Độ trễ | Theo interval/batch | Có thể thấp hơn, phụ thuộc connector/log |
| Tải database | Truy vấn pending rows lặp lại | Đọc transaction log, vẫn có tải connector |
| Phức tạp hạ tầng | Thường thấp hơn | Cao hơn do connector, offset và schema history |
| Scale publisher | Worker/lease/batch | Partition/connector task và throughput log |
| Recovery | Reclaim pending records | Resume offset hoặc snapshot lại |
| Quan sát | Pending count, oldest pending age, publish error | Connector lag, log position, offset, broker lag |
| Phù hợp | Volume vừa phải, cần đơn giản | Volume/latency yêu cầu cao, có năng lực vận hành CDC |

Không có một ngưỡng volume cố định để chuyển từ polling sang CDC. Quyết định nên dựa vào latency mục tiêu, throughput, DB load, khả năng quản lý connector, chi phí và rủi ro chấp nhận được.

## 14. Ví dụ đầu cuối: đồng bộ booking sang Search

Giả sử Booking Service sở hữu trạng thái booking. Search Service duy trì projection để tìm kiếm/lọc lịch sử. Khi booking được xác nhận, hệ thống cần cập nhật projection trong vài giây ở điều kiện bình thường.

### 14.1. Luồng dữ liệu

~~~mermaid
sequenceDiagram
    participant API as Booking API
    participant DB as Booking DB
    participant LOG as Transaction log
    participant CDC as CDC connector
    participant BUS as Event broker
    participant S as Search consumer
    participant IDX as Search index
    API->>DB: BEGIN
    API->>DB: Update booking = CONFIRMED
    API->>DB: Insert BookingConfirmed into outbox
    API->>DB: COMMIT
    DB-->>LOG: Committed changes
    LOG-->>CDC: Outbox row change
    CDC->>BUS: Publish BookingConfirmed
    BUS->>S: Deliver event
    S->>S: Inbox dedup by eventId
    S->>IDX: Update projection
    S-->>BUS: Acknowledge / commit progress
~~~

### 14.2. Trách nhiệm từng thành phần

| Thành phần | Trách nhiệm | Bằng chứng/metric |
|---|---|---|
| Booking API | Kiểm tra transition, ghi booking + outbox | Transaction commit, version |
| Booking DB | Nguồn chuẩn và log thay đổi | Backup, log retention, transaction health |
| CDC connector | Đọc outbox change và phát đúng contract | Connector status, offset, lag |
| Event broker | Lưu/định tuyến event tới consumer | Publish/consume rate, retention, delivery error |
| Search consumer | Dedup và cập nhật projection | Inbox, processing lag, error/DLQ |
| Search index | Phục vụ truy vấn eventual consistent | Projection version, freshness, rebuild |

### 14.3. Các tình huống lỗi

**Tình huống A – Booking commit, connector dừng:** outbox row đã nằm trong transaction log. Khi connector phục hồi, nó tiếp tục từ checkpoint nếu log còn đủ. Theo dõi connector lag và log retention.

**Tình huống B – Connector publish nhưng crash trước checkpoint:** event có thể được phát lại. Search consumer dùng eventId/inbox để tránh cập nhật trùng và không tăng side effect ngoài ý muốn.

**Tình huống C – Consumer cập nhật index nhưng crash trước ack:** broker giao event lại. Consumer kiểm tra inbox; nếu dữ liệu và inbox được commit nguyên tử cùng transaction của datastore hỗ trợ, bản giao trùng không lặp update. Nếu index không hỗ trợ transaction cùng inbox, cần idempotent document update theo version hoặc kho trạng thái trung gian.

**Tình huống D – Event version mới:** consumer cũ không parse được. Contract test và compatibility policy phải ngăn phát hành không tương thích; message lỗi được xử lý vào DLQ thay vì retry vô hạn.

**Tình huống E – Search bị lag lâu:** UI có thể hiển thị dữ liệu cũ. Với thao tác yêu cầu trạng thái ngay sau ghi, đọc Booking API làm nguồn chuẩn hoặc cung cấp read-your-writes bằng version; không suy ra booking chưa tồn tại chỉ vì Search chưa cập nhật.

## 15. Kiểm thử và diễn tập

### 15.1. Kiểm thử transaction nguồn

- Commit booking và outbox thành công: phải có cả hai.
- Rollback transaction: không có booking transition mới và không có event.
- Transition không hợp lệ hoặc update 0 row: không tạo event.
- Hai request đồng thời: không phát hai event xác nhận cho cùng transition.

### 15.2. Kiểm thử publisher/CDC

- Broker ngừng hoạt động rồi phục hồi.
- Publisher crash sau publish nhưng trước mark.
- Hai publisher claim cùng batch.
- Lease hết hạn khi publish còn chạy.
- Connector restart từ checkpoint.
- Connector mất log retention.
- Snapshot trong khi có write mới.
- DDL/schema change và event version mới.

### 15.3. Kiểm thử consumer

- Giao cùng event nhiều lần.
- Consumer commit dữ liệu nhưng mất ack.
- Event tới sai thứ tự hoặc thiếu sequence.
- Inbox commit thất bại.
- Downstream tạm lỗi, quá tải hoặc timeout sau side effect.
- DLQ redrive và replay.

### 15.4. Kiểm chứng consistency

Đo thời gian:

source commit → outbox publish → broker delivery → consumer commit → projection visible

Theo dõi p50/p95/p99 event lag, oldest pending outbox age, connector lag, broker lag và consumer processing duration. Đặt mục tiêu freshness theo từng use case; không chỉ kiểm tra số event đã publish.

## 16. Quan sát và runbook

### 16.1. Metric quan trọng

| Lớp | Metric | Cảnh báo khi |
|---|---|---|
| Outbox | Pending rows, oldest pending age, publish attempts | Pending tăng hoặc record cũ vượt deadline |
| Publisher | Publish success/error, batch duration, lease expiry | Error liên tục hoặc worker tranh lease |
| CDC | Connector health, log position, source lag, offset age | Connector dừng hoặc lag tăng nhanh |
| Database log | Log growth, retained bytes, replication slot lag | Sắp hết dung lượng hoặc log bị giữ quá lâu |
| Broker | Produce/consume rate, throttling, storage, partition health | Broker không theo kịp producer |
| Consumer | Processing rate, retry, error, inbox duplicate count | Consumer chậm hoặc lỗi tăng |
| DLQ | Message count, oldest age, schema/error type | Có message cần owner xử lý |
| Projection | Version lag, freshness, reconciliation mismatch | Read model không bắt kịp nguồn |

### 16.2. Runbook publisher stuck

1. Kiểm tra pending count và tuổi record cũ nhất.
2. Xác định broker/network/credential đang lỗi hay worker không claim được batch.
3. Kiểm tra lease, lock, query plan và index outbox.
4. Kiểm tra eventId đã được broker nhận hay chưa trước khi thao tác gửi lại.
5. Khôi phục publisher với batch/concurrency có giới hạn.
6. Đối chiếu record đã publish và consumer lag.

### 16.3. Runbook CDC lag hoặc mất checkpoint

1. Kiểm tra connector state, last committed offset và transaction log còn bao phủ vị trí đó không.
2. Kiểm tra quyền đọc log, schema history, network và broker.
3. Ước lượng backlog và tốc độ bắt kịp; bảo đảm log không hết retention giữa lúc xử lý.
4. Không reset offset hoặc snapshot lại khi chưa đánh giá duplicate và nguy cơ bỏ sót.
5. Sau khi resume, xác minh thứ tự/version và đối soát số liệu.

### 16.4. Runbook consumer/DLQ

1. Phân loại lỗi theo schema, permission, dependency, data và code.
2. Xác minh consumer có thể nhận duplicate; kiểm tra inbox và side effect thực tế.
3. Sửa lỗi và chạy test với payload lỗi trong môi trường kiểm soát.
4. Redrive theo batch/rate giới hạn, theo dõi lag và downstream.
5. Đóng sự cố sau khi projection hoặc hệ thống đích được đối soát.

## 17. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Update DB rồi publish event riêng | Có thể mất event sau commit | Transactional outbox |
| Publish trước khi commit DB | Consumer nhận event không đúng trạng thái | Chỉ phát ý định đã commit |
| Coi outbox = exactly-once | Publish có thể lặp sau crash | Consumer idempotent và dedup |
| Dùng CDC trực tiếp mọi bảng để tạo domain event | Lộ cấu trúc nội bộ, event sai ngữ nghĩa | Thiết kế event contract qua outbox |
| Acknowledge trước khi consumer commit | Mất xử lý khi crash | Commit dữ liệu/inbox trước ack |
| Xóa inbox quá sớm | Replay cũ gây lặp side effect | Retention theo replay window và yêu cầu nghiệp vụ |
| Reset CDC offset tùy tiện | Bỏ sót hoặc phát trùng lượng lớn | Kiểm tra log/offset và kế hoạch snapshot |
| Không quản lý transaction log retention | Connector không resume được sau downtime dài | Capacity log và alert connector lag |
| Dùng timestamp làm checkpoint duy nhất | Bỏ sót record hoặc khó xử lý delete | CDC log/sequence hoặc cursor có semantics rõ |
| Không version event | Consumer cũ lỗi khi schema đổi | Contract, compatibility test và rollout |
| Không xử lý delete/tombstone | Dữ liệu đích còn record cũ | Định nghĩa semantics xóa và propagation |
| Không có reconciliation | Sai lệch hiếm tồn tại lâu | Đối soát định kỳ và bằng chứng sửa lỗi |

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp/đánh đổi |
|---|---|---|
| **Operational Excellence** | Ai sở hữu outbox, connector, topic, consumer và runbook? | Service catalog, dashboard, replay procedure; CDC thêm thành phần phải vận hành |
| **Security** | Ai được đọc transaction log, payload, inbox và DLQ? | Least privilege, secret rotation, encryption, data minimization và audit |
| **Reliability** | Commit, publish, ack/checkpoint và side effect có cửa sổ lỗi nào? | Outbox/inbox, idempotency, retry giới hạn, DLQ và reconciliation |
| **Performance Efficiency** | Polling load, log throughput, partition và consumer capacity có đủ? | Batch, index, partition, connector scaling; tối ưu latency theo workload |
| **Cost Optimization** | Storage outbox, log retention, broker, connector, egress và history tốn bao nhiêu? | Retention hợp lý, cleanup, chọn polling/CDC theo lợi ích |
| **Sustainability** | Có polling quá thường xuyên, event thừa hoặc replay không cần thiết? | CDC/polling cadence phù hợp, payload nhỏ, cleanup và xử lý batch hiệu quả |

Outbox/inbox/CDC là các cơ chế cải thiện consistency và khả năng phục hồi, nhưng thêm bảng, connector, broker, offset, storage và quy trình vận hành. Chỉ nên áp dụng mức phức tạp tương xứng với giá trị nghiệp vụ và rủi ro dual-write.

## 19. Bài tập áp dụng

### Bài tập A – Khoảng trống dual-write

Booking Service commit CONFIRMED thành công rồi crash trước khi publish BookingConfirmed.

**Câu hỏi:** Tại sao retry request của client không phải cách sửa đầy đủ? Cần thiết kế gì?

**Gợi ý:** Client có thể không biết commit đã thành công; gửi lại có thể gây lặp thao tác. Cần idempotency cho command và outbox trong transaction nguồn để event intent vẫn tồn tại sau crash.

### Bài tập B – Publisher crash

Publisher gửi event tới broker thành công, nhưng crash trước khi đánh dấu outbox row published.

**Câu hỏi:** Khi khởi động lại điều gì có thể xảy ra? Làm sao bảo vệ consumer?

**Gợi ý:** Event có thể được publish lại. Dùng eventId ổn định và inbox/dedup ở consumer; không đánh dấu trước khi broker xác nhận theo semantics.

### Bài tập C – CDC mất log

Connector dừng 18 giờ. Database chỉ giữ transaction log đủ 12 giờ. Offset cuối đã nằm ngoài phần log còn tồn.

**Câu hỏi:** Có thể chỉ restart connector không?

**Gợi ý:** Có thể không resume được từ offset cũ. Cần quy trình snapshot/rebootstrap hoặc phục hồi khác, đánh giá duplicate, delete/tombstone và đối soát downstream; tăng retention và cảnh báo lag để tránh lặp lại.

### Bài tập D – Consumer side effect ngoài

Consumer gửi email thành công, sau đó database commit inbox thất bại. Broker giao lại event.

**Câu hỏi:** Inbox đơn thuần có ngăn email gửi hai lần không?

**Gợi ý:** Không, vì gửi email và ghi inbox không nằm trong cùng transaction. Dùng idempotency API của provider nếu hỗ trợ, một delivery record/outbox trung gian và trạng thái đối soát; chấp nhận rằng kết quả bên ngoài có thể chưa xác định sau timeout.

### Bài tập E – CDC trực tiếp bảng nghiệp vụ

Một connector phát event mỗi khi cột updated_at hoặc cột nội bộ thay đổi. Consumer coi mọi record update là BookingUpdated.

**Câu hỏi:** Rủi ro là gì?

**Gợi ý:** Event có thể không mang ý nghĩa nghiệp vụ, phát thừa và ràng buộc consumer với schema nội bộ. Dùng outbox để service owner quyết định integration event; hoặc định nghĩa rõ mapping/filter và contract khi dùng CDC cho replication.

### Bài tập F – Thứ tự aggregate

Booking có sequence 11 CONFIRMED và 12 CANCELLED. Consumer nhận 12 trước 11.

**Câu hỏi:** Consumer cần xử lý như thế nào?

**Gợi ý:** Dùng aggregate sequence/version để phát hiện thứ tự; partition theo bookingId nếu nền tảng đảm bảo ordering trong partition; bỏ qua hoặc đối soát event cũ theo state transition, không dựa duy nhất vào timestamp nhận.

## 20. Checklist trước khi đưa outbox/inbox/CDC vào production

- [ ] Event được định nghĩa theo ngữ nghĩa nghiệp vụ, có owner, eventId, version và aggregate key.
- [ ] Cập nhật dữ liệu nguồn và insert outbox nằm trong cùng transaction.
- [ ] Chỉ tạo event khi transition nghiệp vụ hợp lệ đã được thực hiện.
- [ ] Publisher có lease/claim an toàn, batch/concurrency giới hạn và xử lý crash sau publish.
- [ ] CDC connector có quyền tối thiểu, offset/checkpoint, schema history và log retention được quản lý.
- [ ] Đã chọn polling hoặc CDC dựa trên latency, volume, DB load và năng lực vận hành.
- [ ] Consumer ghi inbox/dedup cùng transaction với thay đổi dữ liệu cục bộ.
- [ ] Side effect ngoài database có idempotency key hoặc reconciliation.
- [ ] Duplicate, ordering, retry, poison message, DLQ và replay đã được kiểm thử.
- [ ] Snapshot, delete/tombstone, schema evolution và offset reset có runbook.
- [ ] Có metric pending outbox age, connector lag, broker lag, consumer lag và reconciliation mismatch.
- [ ] Retention/cleanup của outbox, inbox, log, broker và DLQ được xác định.
- [ ] Payload, checkpoint, connector credential và dữ liệu lưu trữ được bảo vệ.
- [ ] Region của source, connector, broker, backup, log và consumer phù hợp chính sách dữ liệu.
- [ ] Capacity database, transaction log, broker, partition, network và consumer đã được benchmark.
- [ ] Có owner, ngân sách, cảnh báo, diễn tập phục hồi và quy trình đối soát định kỳ.

**Điểm cốt lõi:** transactional outbox giữ **ý định phát event** cùng transaction với dữ liệu nguồn; inbox giúp consumer **không lặp xử lý nội bộ** khi message được giao lại; CDC vận chuyển **những thay đổi đã commit** từ database tới các hệ thống khác theo log/checkpoint. Kết hợp đúng ba kỹ thuật giúp pipeline sự kiện đáng tin cậy hơn, nhưng vẫn phải thiết kế idempotency cho side effect, quản lý ordering và lag, xử lý replay, bảo mật dữ liệu và diễn tập phục hồi.
