# Phát lại dữ liệu mà không lặp tác dụng phụ

Trong hệ thống xử lý sự kiện, phát lại (replay) là việc đưa message đã được lưu trước đó qua consumer một lần nữa. Replay hữu ích khi cần khôi phục sau sự cố, chạy lại một phiên bản xử lý mới, sửa dữ liệu đã tính sai hoặc tái dựng trạng thái. Tuy nhiên, một message có thể đã tạo tác dụng phụ trước khi consumer gặp lỗi hoặc trước khi broker ghi nhận acknowledgement. Nếu phát lại message đó mà không có cơ chế chống lặp, ứng dụng có thể trừ tiền hai lần, gửi email nhiều lần, tăng tồn kho sai hoặc tạo bản ghi trùng.

Độ tin cậy giao nhận của Spring Cloud Stream cần được thiết kế cùng với tính idempotent của nghiệp vụ. Broker có thể giao lại message; consumer cần nhận diện cùng một sự kiện qua nhiều lần giao, lưu dấu vết xử lý một cách nguyên tử và bảo vệ các lời gọi ra hệ thống bên ngoài. Bài học này trình bày cách phát lại an toàn với Kafka, RabbitMQ và Pulsar, đồng thời phân biệt acknowledgement, offset, deduplication, inbox và outbox.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao at-least-once delivery có thể làm consumer nhận lại cùng message.
- Phân biệt event ID ổn định với broker offset, delivery tag hoặc message ID.
- Thiết kế idempotent consumer và idempotency key để ngăn lặp tác dụng phụ.
- Dùng inbox/deduplication record cùng transaction cơ sở dữ liệu.
- Dùng transactional outbox để phát sự kiện sau khi cập nhật trạng thái nghiệp vụ.
- Hiểu quan hệ giữa xử lý nghiệp vụ và acknowledgement/offset trên Kafka, RabbitMQ và Pulsar.
- Lập kế hoạch replay theo thời gian, phạm vi, tốc độ và thứ tự.
- Kiểm thử các cửa sổ lỗi giữa commit, acknowledgement và tác dụng phụ bên ngoài.

## 1. Vì sao message có thể được xử lý nhiều lần?

Trong hệ thống phân tán, consumer và broker không thể luôn biết chắc một tác vụ đã hoàn tất hay chưa khi kết nối bị ngắt đúng thời điểm. Một tình huống điển hình:

1. Consumer nhận message `OrderPaid`.
2. Consumer gọi dịch vụ thanh toán hoặc cập nhật database thành công.
3. Consumer bị dừng trước khi acknowledgement hoặc offset commit được broker ghi nhận.
4. Broker không thấy xác nhận hoàn tất và giao lại message.
5. Consumer xử lý lại message, tạo thêm tác động phụ.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Database / API
    B->>C: Giao OrderPaid (eventId=evt-100)
    C->>D: Ghi nhận thanh toán
    D-->>C: Thành công
    Note over C: Process dừng trước acknowledgement
    B->>C: Giao lại evt-100
    C->>D: Ghi nhận thanh toán lần nữa
    D-->>C: Có nguy cơ lặp tác dụng phụ
~~~

Đây là lý do at-least-once delivery thường cho phép message được giao lại. Mục tiêu của nó là tránh mất message trong các tình huống lỗi, nhưng đổi lại consumer phải chịu được việc nhận trùng.

### Các cửa sổ gây trùng

| Thời điểm xảy ra sự cố | Hệ quả có thể có |
|---|---|
| Trước khi xử lý | Broker giao lại; chưa có tác dụng phụ |
| Trong khi xử lý, trước commit | Transaction có thể rollback; message được giao lại |
| Sau commit database, trước acknowledgement | Database đã thay đổi nhưng broker có thể giao lại |
| Sau khi gọi API ngoài thành công, trước khi lưu kết quả/ack | API có thể thực hiện tác động lần nữa khi retry |
| Sau acknowledgement | Broker xem message đã hoàn tất; nếu ứng dụng mất dữ liệu trước đó thì không thể dựa vào broker để tự khôi phục |

Điểm khó nhất là khoảng giữa tác dụng phụ đã xảy ra và dấu hiệu hoàn tất được lưu bền vững. Thiết kế idempotency phải bao phủ khoảng này.

## 2. Phân biệt delivery, processing và side effect

Ba khái niệm cần được tách riêng:

- **Delivery:** broker giao message cho consumer.
- **Processing:** ứng dụng kiểm tra và thực hiện logic cho message.
- **Side effect:** thay đổi trạng thái bên ngoài như ghi database, trừ tiền, gửi email hoặc gọi dịch vụ khác.

Một message có thể được giao nhiều lần nhưng chỉ tạo một tác dụng phụ nếu consumer idempotent. Ngược lại, broker có thể giao message đúng một lần trong điều kiện bình thường nhưng ứng dụng vẫn tạo tác dụng phụ lặp do retry ở tầng HTTP hoặc do client gửi lại lệnh.

| Cơ chế | Bảo vệ điều gì? | Không tự bảo vệ điều gì? |
|---|---|---|
| Broker acknowledgement/offset | Tiến độ giao nhận và tiêu thụ | Tính duy nhất của tác dụng phụ trong database/API |
| Producer idempotence | Hạn chế duplicate record do retry gửi ở một số broker/client | Xử lý trùng ở consumer hoặc side effect ngoài broker |
| Consumer deduplication | Nhận diện event đã được xử lý | Tác dụng phụ ngoài transaction nếu không có idempotency |
| Idempotency key ở API | Ngăn cùng thao tác nghiệp vụ bị thực hiện lặp tại API hỗ trợ key | Các API khác không chia sẻ key hoặc trạng thái |
| Database transaction | Nhóm các thay đổi trong cùng database thành một đơn vị | Giao dịch nguyên tử xuyên database, broker và API ngoài |

Không nên gọi toàn hệ thống là exactly-once chỉ vì một thành phần có tính năng idempotence hoặc transaction. Cần xác định chính xác ranh giới được bảo vệ.

## 3. Dùng event ID ổn định để nhận diện sự kiện

Consumer cần một định danh không đổi qua các lần giao lại và replay. Thông thường producer tạo `eventId` khi sự kiện nghiệp vụ được phát hành.

Ví dụ:

~~~java
public record OrderPaid(
    String eventId,
    String orderId,
    String paymentId,
    BigDecimal amount,
    Instant occurredAt
) {}
~~~

`eventId` đại diện cho một sự kiện cụ thể. Nếu broker giao lại message, eventId phải giữ nguyên. Nếu producer tạo lại event mới cho cùng đơn hàng ở một thời điểm khác, event mới cần eventId khác.

Không nên dùng các giá trị sau làm idempotency key nghiệp vụ:

- Kafka offset: thay đổi khi message được ghi lại hoặc phát lại vào topic khác.
- RabbitMQ delivery tag: chỉ có ý nghĩa trong channel và lần giao cụ thể.
- Pulsar message ID: xác định vị trí message ở broker, không nhất thiết giữ nguyên khi republish.
- Thời điểm nhận message: mỗi lần giao có thể có thời điểm khác.
- UUID được tạo trong consumer mỗi lần xử lý: lần giao lại sẽ tạo khóa mới và không phát hiện trùng.

Nếu producer chưa có eventId, hãy xác định một khóa nghiệp vụ ổn định, chẳng hạn `paymentId` hoặc `orderId + eventType + aggregateVersion`. Không dùng một tổ hợp có thể va chạm giữa các sự kiện hợp lệ.

## 4. Idempotent consumer

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng đầu vào mà trạng thái cuối cùng vẫn tương đương với việc thực hiện một lần. Ví dụ:

- Đặt trạng thái đơn hàng thành `PAID` có thể idempotent nếu cập nhật có điều kiện và không kích hoạt side effect lặp.
- Tăng số dư thêm 100 mỗi lần không idempotent.
- Ghi nhận `paymentId` với unique constraint có thể ngăn một khoản thanh toán bị ghi hai lần.
- Gửi email mỗi lần handler chạy không idempotent nếu nhà cung cấp email không hỗ trợ idempotency.

Ví dụ thao tác đặt trạng thái:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = :orderId
  AND status <> 'PAID';
~~~

Câu lệnh này tránh cập nhật trạng thái đã là PAID thêm lần nữa, nhưng nếu logic khác vẫn phát email hoặc trừ tiền ở mỗi lần chạy thì tác dụng phụ đó vẫn có thể lặp. Idempotency phải được áp dụng cho toàn bộ các hiệu ứng cần bảo vệ, không chỉ một câu lệnh SQL.

### Idempotency key theo nghiệp vụ

Với thao tác thanh toán, dùng `paymentId` hoặc `eventId` làm key:

~~~java
paymentClient.capture(
    paymentId,
    amount,
    eventId
);
~~~

Nếu API thanh toán hỗ trợ idempotency key, cùng key phải được gửi lại cho các lần retry của cùng thao tác. Không tạo key mới mỗi lần retry. API có thể trả lại kết quả đã lưu thay vì thực hiện capture lần nữa.

Nếu API ngoài không hỗ trợ idempotency, consumer không thể tự đảm bảo tuyệt đối rằng thao tác không bị lặp trong cửa sổ response bị mất. Khi đó cần hợp đồng tích hợp khác, truy vấn trạng thái trước khi retry, reconciliation hoặc quy trình xử lý thủ công.

## 5. Inbox pattern: ghi nhận message đã xử lý

Inbox là bảng lưu dấu vết message mà một consumer đã tiếp nhận và xử lý. Một khóa duy nhất như `(consumer_name, event_id)` cho phép phát hiện cùng event được giao lại.

Ví dụ schema PostgreSQL:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer mở transaction, thử thêm eventId vào inbox và chỉ thực hiện thay đổi nghiệp vụ nếu bản ghi mới được tạo. Câu lệnh PostgreSQL:

~~~sql
INSERT INTO processed_messages (consumer_name, event_id)
VALUES (:consumerName, :eventId)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Nếu số hàng được thêm bằng 1, đây là lần xử lý đầu tiên của event trong consumer đó. Nếu số hàng được thêm bằng 0, event đã được ghi nhận; consumer có thể kết thúc thành công mà không lặp tác dụng phụ trong transaction này.

### Xử lý inbox và nghiệp vụ trong cùng transaction

Ví dụ với Spring JDBC và PostgreSQL:

~~~java
@Service
public class OrderPaidHandler {

    private final JdbcTemplate jdbc;

    public OrderPaidHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void handle(OrderPaid event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_messages (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "accounting",
            event.eventId()
        );

        if (inserted == 0) {
            return; // Event đã được xử lý
        }

        jdbc.update("""
            UPDATE orders
            SET status = 'PAID'
            WHERE order_id = ?
            """,
            event.orderId()
        );

        jdbc.update("""
            INSERT INTO payment_ledger (payment_id, order_id, amount)
            VALUES (?, ?, ?)
            """,
            event.paymentId(),
            event.orderId(),
            event.amount()
        );
    }
}
~~~

Điều kiện quan trọng là inbox record và các thay đổi nghiệp vụ phải commit trong cùng một transaction database. Nếu cập nhật nghiệp vụ thất bại, transaction rollback cả inbox record; khi broker giao lại, consumer có thể thử lại. Nếu transaction commit nhưng acknowledgement bị mất, lần giao lại sẽ gặp inbox record và không lặp các thay đổi trong database.

Ví dụ dùng cú pháp `ON CONFLICT` của PostgreSQL. Với database khác, dùng cú pháp insert-if-absent tương ứng và bảo đảm unique constraint được thực thi ở database, không chỉ kiểm tra bằng câu SELECT trước khi INSERT. Hai consumer có thể đồng thời kiểm tra cùng event; chỉ unique constraint mới giải quyết tranh chấp một cách tin cậy.

### Vì sao không lưu inbox trước rồi xử lý sau?

Nếu ghi inbox và commit trước, sau đó mới cập nhật nghiệp vụ, một sự cố giữa hai bước có thể khiến event được đánh dấu đã xử lý dù tác dụng phụ chưa xảy ra. Lần giao lại sẽ bị bỏ qua và dữ liệu nghiệp vụ bị thiếu.

Nếu cập nhật nghiệp vụ trước, commit rồi mới ghi inbox, một sự cố giữa hai bước có thể khiến tác dụng phụ xảy ra lần nữa khi message được giao lại.

Vì vậy, inbox và các thay đổi trong cùng database phải nằm trong cùng transaction. Với tác dụng phụ ngoài database, cần thêm idempotency hoặc outbox.

## 6. Phạm vi và thời hạn lưu deduplication record

Inbox key cần được thiết kế theo phạm vi consumer. Cùng một event có thể được nhiều consumer hợp lệ xử lý cho các mục đích khác nhau, vì vậy khóa thường gồm consumer name và eventId.

Ví dụ:

| consumer_name | event_id | Ý nghĩa |
|---|---|---|
| accounting | evt-100 | Consumer kế toán đã xử lý |
| notification | evt-100 | Consumer thông báo đã xử lý |
| inventory | evt-100 | Consumer kho đã xử lý |

Không dùng một bảng eventId toàn cục để một consumer vô tình chặn các consumer khác.

Thời hạn lưu inbox phải dài ít nhất bằng khoảng thời gian có thể replay hoặc redeliver message. Nếu broker giữ dữ liệu 30 ngày nhưng inbox record bị xóa sau 7 ngày, replay message cũ vào ngày thứ 20 có thể tạo lại side effect.

Cần cân nhắc:

- Retention của topic/queue và khả năng replay lịch sử.
- Khoảng thời gian DLQ có thể được giữ và replay.
- Backup/restore database có thể làm mất một phần inbox record.
- Yêu cầu kiểm toán và thời hạn lưu dấu vết nghiệp vụ.
- Kích thước bảng và chiến lược partition/archiving.

Với tác dụng phụ tài chính hoặc pháp lý, có thể cần giữ idempotency ledger lâu dài theo quy định nghiệp vụ thay vì xóa theo TTL ngắn.

## 7. Tác dụng phụ ngoài database

Transaction database không thể tự bao phủ một API HTTP, email provider hoặc hệ thống thanh toán khác nếu không có giao thức giao dịch phân tán được hỗ trợ. Tránh giả định `@Transactional` làm cho database và API ngoài commit nguyên tử.

Ví dụ một handler:
1. Ghi inbox vào database.
2. Gọi API gửi email.
3. Cập nhật trạng thái notification.
4. Commit database.

Nếu API gửi email thành công nhưng database rollback, message được giao lại và email có thể gửi lần nữa. Nếu database commit trước rồi API thất bại, trạng thái có thể ghi nhận hoàn tất dù email chưa được gửi.

Các cách bảo vệ:

- Dùng idempotency key mà API ngoài hỗ trợ.
- Lưu yêu cầu side effect vào outbox trong transaction database.
- Dùng worker riêng gửi outbox và đánh dấu trạng thái sau khi nhận kết quả.
- Dùng trạng thái trung gian như PENDING, SENT, FAILED để có thể retry có kiểm soát.
- Reconcile với hệ thống ngoài khi kết quả không rõ ràng.

Với email provider không hỗ trợ idempotency, có thể lưu notification key và kiểm tra trạng thái nội bộ, nhưng vẫn tồn tại cửa sổ không chắc chắn nếu provider nhận email mà response bị mất. Cần chấp nhận và quản lý rủi ro đó bằng reconciliation hoặc nhà cung cấp có khả năng chống trùng.

## 8. Outbox pattern khi cần phát sự kiện tiếp theo

Outbox giải quyết vấn đề cập nhật database thành công nhưng phát message tiếp theo thất bại. Thay vì ghi database rồi gửi message trực tiếp trong cùng request, ứng dụng ghi cả thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction.

~~~mermaid
flowchart TD
    A["Consumer nhận event"] --> B["Database transaction"]
    B --> C["Ghi inbox / dedup"]
    C --> D["Cập nhật trạng thái nghiệp vụ"]
    D --> E["Ghi outbox event"]
    E --> F["Commit transaction"]
    F --> G["Outbox relay đọc event"]
    G --> H["Publish tới broker"]
    H --> I["Đánh dấu đã publish"]
~~~

Ví dụ bảng outbox:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(200) PRIMARY KEY,
    aggregate_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
~~~

Trong transaction xử lý message, ứng dụng cập nhật trạng thái và thêm outbox record. Một relay hoặc CDC connector đọc outbox và publish event. Nếu relay publish thành công nhưng chết trước khi đánh dấu `published_at`, nó có thể publish lại; consumer nhận sự kiện tiếp theo vẫn cần idempotent.

Inbox và outbox giải quyết hai hướng khác nhau:

- Inbox chống xử lý lặp khi message đầu vào được giao lại.
- Outbox bảo đảm yêu cầu phát sự kiện đầu ra được lưu cùng thay đổi nghiệp vụ.
- Consumer phía sau vẫn cần idempotency vì relay có thể publish lại.

## 9. Acknowledgement và replay trên Kafka

Kafka lưu record trong topic theo partition và offset. Consumer group theo dõi tiến độ bằng offset. Nếu xử lý database xong nhưng offset chưa được commit, record có thể được đọc lại sau restart hoặc rebalance.

Với mô hình xử lý at-least-once, thứ tự thường được thiết kế là:
1. Đọc record.
2. Xử lý và commit transaction database.
3. Sau khi xử lý thành công, commit offset theo cơ chế binder/container.

Nếu process chết giữa bước 2 và 3, Kafka giao lại record. Inbox deduplication giúp consumer bỏ qua tác dụng phụ đã commit.

### Kafka transactions và exactly-once

Kafka transactions có thể phối hợp việc đọc từ Kafka, ghi sang Kafka và commit offset trong cùng transaction Kafka khi ứng dụng/binder được cấu hình đúng. Đây là nền tảng cho exactly-once semantics trong phạm vi Kafka read-process-write. Nó không tự làm cho một lần gọi database, email hoặc API ngoài trở thành một phần của Kafka transaction.

Nếu pipeline ghi database, vẫn cần inbox/idempotency hoặc một chiến lược phối hợp giao dịch phù hợp. Không suy luận rằng bật Kafka transaction sẽ ngăn duplicate side effect ở hệ thống ngoài.

### Replay Kafka

Có thể replay bằng cách:
- Tạo consumer group mới để đọc lại dữ liệu theo offset reset policy.
- Reset offset của group hiện có về vị trí đã chọn.
- Dùng công cụ đọc topic và publish lại vào destination replay riêng.

Reset offset của group production có thể làm các consumer đang chạy đọc lại lượng lớn dữ liệu. Cần dừng hoặc điều phối consumer, ghi lại offset ban đầu, chọn phạm vi partition/offset và có kế hoạch rollback.

Khi replay, giữ nguyên eventId gốc để inbox nhận diện message đã xử lý. Nếu phát lại vào topic mới, broker offset mới không thay thế eventId gốc.

## 10. Acknowledgement và replay trên RabbitMQ

RabbitMQ consumer nhận message qua channel. Với manual acknowledgement, consumer chỉ ack sau khi xử lý thành công. Nếu connection/channel bị đóng trước ack, broker có thể requeue và giao message lại.

Một quy trình an toàn:
1. Nhận message.
2. Xử lý trong transaction database có inbox.
3. Commit database.
4. Ack message sau khi xử lý thành công.
5. Nếu process chết sau commit trước ack, message được giao lại nhưng inbox chặn side effect lặp.

Delivery tag của RabbitMQ chỉ có ý nghĩa trong channel và không phải event ID nghiệp vụ. Cờ redelivered có thể giúp quan sát message được giao lại, nhưng không thay thế deduplication vì message có thể được republish thành một message mới.

Khi replay từ DLQ, có thể republish vào exchange/queue gốc hoặc một destination replay riêng. Giữ eventId gốc, thêm metadata về replay run nếu cần kiểm toán và tránh tạo vòng lặp DLQ vô hạn. Xác minh routing key, TTL, queue policy và acknowledgement của consumer đích.

## 11. Acknowledgement và replay trên Pulsar

Pulsar theo dõi tiến độ tiêu thụ bằng subscription cursor. Consumer acknowledge message sau khi xử lý; message chưa ack có thể được redeliver theo chính sách ack timeout, negative acknowledgement hoặc subscription.

Nếu database commit thành công nhưng acknowledgement không tới broker, message có thể được giao lại. Inbox record với eventId ổn định giúp tránh lặp tác dụng phụ.

Pulsar có thể hỗ trợ retry letter topic và dead-letter topic theo cấu hình client/binder. Khi replay, cần hiểu subscription đang đọc từ vị trí nào, dùng seek/reset cursor hay republish message. Republish tạo một message broker mới, vì vậy message ID native có thể khác; giữ eventId trong payload hoặc metadata nghiệp vụ.

Với Key_Shared hoặc subscription type khác, thứ tự và phân phối message có ngữ nghĩa riêng. Nếu replay message theo thứ tự khác với luồng ban đầu, consumer cần kiểm tra aggregate version hoặc sequence để tránh áp dụng trạng thái cũ sau trạng thái mới.

## 12. Phát lại có kiểm soát

Replay không chỉ là gửi lại message. Một quy trình replay an toàn cần xác định rõ nguồn, phạm vi, mục tiêu và tốc độ.

### Trước khi replay

- Xác định nguyên nhân ban đầu đã được khắc phục.
- Chọn tập event theo eventId, thời gian, partition/offset hoặc DLQ.
- Xác nhận consumer đích có inbox/idempotency phù hợp.
- Kiểm tra schema và phiên bản payload.
- Xác định replay có chạy lại mọi side effect hay chỉ tái dựng trạng thái.
- Xác định thứ tự theo aggregate và cách xử lý event cũ.
- Ghi lại số lượng dự kiến, phạm vi và người/tiến trình khởi chạy.

### Trong khi replay

- Dùng replay topic hoặc consumer group riêng khi phù hợp.
- Giới hạn tốc độ để tránh gây quá tải hệ thống phụ thuộc.
- Thêm replayRunId và source metadata để truy vết.
- Giữ nguyên eventId gốc.
- Theo dõi số event thành công, duplicate-suppressed, lỗi và DLQ.
- Dừng replay nếu tỷ lệ lỗi hoặc backlog vượt ngưỡng.

### Sau khi replay

- Đối chiếu số event đầu vào với số event xử lý mới, duplicate và thất bại.
- Kiểm tra trạng thái nghiệp vụ và các side effect ngoài.
- Ghi lại offset/cursor hoặc phạm vi đã replay.
- Giữ audit record để có thể giải thích tác động của lần chạy.
- Xác minh không còn message mắc trong retry/DLQ ngoài dự kiến.

Một replay run nên có định danh riêng, nhưng không thay eventId gốc. replayRunId dùng để truy vết một lần chạy lại; eventId dùng để nhận diện sự kiện nghiệp vụ.

## 13. Thứ tự và sự kiện cũ

Idempotency không tự giải quyết thứ tự. Nếu một aggregate có các sự kiện:
- OrderCreated, version 1
- OrderPaid, version 2
- OrderShipped, version 3

Replay chỉ OrderCreated sau khi trạng thái đã đến version 3 có thể làm dữ liệu quay về trạng thái cũ nếu handler không kiểm tra version.

Có thể lưu aggregate version và chỉ áp dụng event mới hơn:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :eventVersion
WHERE order_id = :orderId
  AND version < :eventVersion;
~~~

Câu lệnh minh họa kiểm soát version tăng dần. Hãy xác định cách xử lý event bị bỏ qua do version cũ, event thiếu version hoặc hai event cùng version. Với một số nghiệp vụ, cần xử lý tuần tự hoặc tái dựng trạng thái từ event log thay vì chỉ bỏ qua event cũ.

Partitioning theo aggregate key giúp các sự kiện liên quan có cơ hội giữ thứ tự trong cùng partition, nhưng replay có thể đưa message vào đường đi khác hoặc thay đổi partition. Kiểm tra version vẫn hữu ích để bảo vệ trạng thái.

## 14. Kiểm thử các cửa sổ lỗi

Kiểm thử bình thường không đủ để chứng minh replay an toàn. Cần mô phỏng process dừng ở các thời điểm quan trọng:

| Điểm dừng giả lập | Kết quả cần xác minh |
|---|---|
| Trước khi ghi inbox | Broker giao lại và consumer xử lý bình thường |
| Sau insert inbox nhưng trước cập nhật nghiệp vụ | Transaction rollback; lần giao lại được xử lý |
| Sau cập nhật nghiệp vụ nhưng trước commit | Transaction rollback toàn bộ thay đổi trong DB |
| Sau commit DB nhưng trước ack/offset commit | Broker giao lại; inbox ngăn side effect DB lặp |
| Sau API ngoài thành công nhưng trước lưu kết quả | API idempotency key ngăn tác động lặp hoặc reconciliation phát hiện trạng thái |
| Sau publish outbox nhưng trước đánh dấu published | Relay có thể publish lại; consumer downstream deduplicate |
| Khi replay event cũ hơn trạng thái hiện tại | Version guard ngăn ghi đè trạng thái mới |

### Kiểm thử inbox

- Gửi cùng eventId hai lần.
- Chạy hai consumer instance đồng thời với cùng eventId.
- Xác minh unique constraint chỉ cho một transaction xử lý lần đầu.
- Xác minh duplicate không tạo thêm ledger entry hoặc thay đổi nghiệp vụ.
- Rollback transaction và xác minh lần giao tiếp theo vẫn có thể xử lý.

### Kiểm thử API ngoài

Dùng mock server có hỗ trợ idempotency key:
- Gọi cùng key hai lần.
- Xác minh server chỉ tạo một tác động.
- Làm response timeout sau khi server đã ghi nhận.
- Retry với cùng key và xác minh nhận lại kết quả đã lưu.

### Kiểm thử broker

Với Kafka, kiểm tra offset commit và redelivery sau restart. Với RabbitMQ, kiểm tra manual ack và redelivery khi channel đóng. Với Pulsar, kiểm tra ack/nack, redelivery và subscription cursor. Broker integration test cần chạy với cấu hình gần production vì test binder không mô phỏng đầy đủ semantics của từng broker.

## 15. Những sai lầm thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trừ tiền hai lần sau restart | Commit DB/API trước ack, consumer không idempotent | Inbox và payment idempotency key |
| Message bị bỏ qua dù nghiệp vụ chưa chạy | Ghi inbox rồi commit trước side effect | Gộp inbox và DB update trong cùng transaction |
| Email gửi hai lần | Email provider thành công nhưng response mất | Provider idempotency nếu có; outbox và reconciliation |
| Replay tạo tác động mới | Replay dùng eventId mới hoặc dedup record đã hết hạn | Giữ eventId gốc và retention đủ dài |
| Consumer này chặn consumer khác | Inbox key chỉ dùng eventId toàn cục | Dùng composite key consumer_name + event_id |
| Kafka reset offset gây xử lý lại diện rộng | Không xác định phạm vi replay | Lưu offset gốc, chọn partition/range và dùng group riêng khi phù hợp |
| RabbitMQ redelivered flag bị dùng làm dedup key | Cờ redelivered không định danh sự kiện | Dùng eventId ổn định |
| Pulsar republish không được nhận diện trùng | Dựa vào native message ID mới | Giữ eventId trong payload/metadata |
| Event cũ ghi đè trạng thái mới | Không kiểm tra aggregate version | Version guard hoặc xử lý theo thứ tự |
| Outbox phát message trùng | Relay chết sau publish trước khi đánh dấu | Consumer downstream idempotent |
| Deduplication không hoạt động sau nhiều ngày | Inbox record bị xóa quá sớm | Đồng bộ retention với replay horizon |

## 16. Bài thực hành: replay OrderPaid an toàn

Xây dựng consumer `accounting` nhận `OrderPaid`:

1. Bảo đảm producer tạo eventId ổn định và giữ nguyên qua retry/replay.
2. Tạo bảng `processed_messages` với unique key `(consumer_name, event_id)`.
3. Tạo bảng `payment_ledger` có unique constraint trên paymentId.
4. Viết handler dùng một transaction database để insert inbox và ghi ledger.
5. Nếu inbox insert không tạo hàng mới, kết thúc xử lý mà không ghi ledger lần nữa.
6. Nếu transaction lỗi, xác minh inbox và ledger cùng rollback.
7. Ack/commit offset sau khi transaction thành công theo cơ chế binder.
8. Mô phỏng process dừng sau DB commit nhưng trước ack; xác minh broker giao lại và dedup chặn lặp.
9. Nếu gọi payment API ngoài, truyền cùng eventId/paymentId làm idempotency key cho mọi lần retry.
10. Thêm outbox nếu handler cần phát `AccountingEntryCreated` sau commit.
11. Replay cùng eventId từ DLQ hoặc replay topic và xác minh không có ledger entry thứ hai.
12. Replay một event version cũ và xác minh version guard không ghi đè trạng thái mới.
13. Chạy bài test trên Kafka, RabbitMQ hoặc Pulsar theo binder thực tế.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Event identity | eventId ổn định qua delivery và replay |
| Inbox | Có unique key theo consumer và event |
| Atomicity | Inbox và thay đổi DB cùng transaction |
| External API | Cùng idempotency key qua các lần retry |
| Outbox | Event đầu ra được lưu cùng thay đổi nghiệp vụ |
| Acknowledgement | Chỉ xác nhận sau khi xử lý bền vững |
| Replay scope | Có phạm vi, tốc độ và audit rõ ràng |
| Ordering | Có aggregate version hoặc quy tắc thứ tự |
| Retention | Dedup record tồn tại đủ lâu cho replay |
| Failure injection | Các cửa sổ lỗi chính được kiểm thử |

## Kết luận

Phát lại dữ liệu an toàn đòi hỏi nhận diện cùng một sự kiện qua nhiều lần giao và bảo vệ từng tác dụng phụ. Broker acknowledgement, Kafka offset hoặc Pulsar subscription cursor quản lý tiến độ giao nhận; chúng không tự bảo đảm một lần cập nhật database hay một lần gọi API ngoài.

Hãy dùng eventId ổn định, inbox/deduplication trong cùng transaction với thay đổi nghiệp vụ, idempotency key cho API ngoài và outbox khi cần phát sự kiện tiếp theo. Giữ dedup record đủ lâu, kiểm soát thứ tự bằng aggregate version và replay theo phạm vi có audit. Thiết kế này giúp consumer chịu được redelivery, retry và replay trên Kafka, RabbitMQ hoặc Pulsar mà không lặp tác dụng phụ ngoài dự kiến.

## Tài liệu tham khảo

- [Spring Cloud Stream – Consumer Properties and Acknowledgement](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream – Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder.html)
- [Spring Cloud Stream – Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Apache Kafka – Design and Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
- [Apache Pulsar – Messaging and Acknowledgement](https://pulsar.apache.org/docs/next/concepts-messaging/)

