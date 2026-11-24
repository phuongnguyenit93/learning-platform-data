# Consumer lặp an toàn với inbox và ràng buộc duy nhất

Một consumer Spring Cloud Stream có thể nhận cùng một event nhiều lần. Producer có thể gửi lại khi không nhận được publish confirmation; broker có thể giao lại message chưa được acknowledge; Kafka có thể đọc lại record sau khi consumer xử lý xong nhưng chưa commit offset; Pulsar có thể redeliver khi acknowledgment timeout. Retry và replay cũng có thể đưa một event cũ quay lại sau nhiều giờ hoặc nhiều ngày.

Nếu mỗi lần nhận message đều trừ tiền, tăng số lượng tồn kho hoặc tạo một đơn hàng mới, duplicate sẽ làm sai dữ liệu nghiệp vụ. Consumer cần xử lý lặp an toàn: cùng một event được giao nhiều lần nhưng hiệu ứng nghiệp vụ chỉ được áp dụng một lần trong phạm vi consumer đó.

Inbox pattern kết hợp một bảng lưu event đã tiếp nhận với ràng buộc duy nhất của cơ sở dữ liệu. Consumer ghi dấu event và cập nhật dữ liệu nghiệp vụ trong cùng một transaction. Ràng buộc duy nhất là điểm phân xử cuối cùng khi hai lần giao cùng event đến đồng thời.

## 1. Vì sao broker có thể giao lại message?

Hệ thống message thường ưu tiên khả năng giao lại khi không chắc consumer đã hoàn tất. Điều này tạo semantics at-least-once: một message có thể được giao một hoặc nhiều lần, miễn là nó chưa được xác nhận hoàn tất theo cơ chế của broker.

Các tình huống thường gặp:

- Producer publish thành công nhưng mất kết nối trước khi nhận confirmation, nên producer gửi lại.
- RabbitMQ consumer xử lý xong một phần nhưng channel đóng trước khi ACK được broker ghi nhận.
- Kafka consumer cập nhật database xong nhưng process chết trước khi commit offset.
- Pulsar consumer chưa ACK trước acknowledgment timeout hoặc bị ngắt kết nối.
- Operator chủ động replay message để khôi phục dữ liệu hoặc chạy lại một khoảng thời gian.
- Retry topic, dead-letter recovery hoặc redrive đưa event cũ trở lại luồng xử lý.

Ví dụ cửa sổ lỗi:

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Database
    B->>C: Event E-101
    C->>D: Update order and commit
    Note over C,B: Process dies before ACK / offset commit
    B->>C: Redeliver E-101
    C->>D: Update order again?
~~~

Database đã commit nhưng broker chưa biết điều đó. Từ góc nhìn broker, event vẫn chưa được xác nhận; giao lại là hành vi đúng. Consumer phải nhận diện event đã được áp dụng và kết thúc lần giao lại mà không lặp side effect.

## 2. Inbox pattern giải quyết vấn đề gì?

Inbox là bảng trong database của consumer, lưu định danh các event đã được logical consumer xử lý thành công. Một hàng inbox thường đại diện cho một cặp consumer và event:

    (consumer_name, producer_id, event_id)

Khi message đến, consumer cố gắng chèn khóa này vào inbox. Unique constraint đảm bảo chỉ một transaction có thể chèn thành công cùng khóa. Nếu insert thành công, transaction tiếp tục cập nhật business data. Nếu khóa đã tồn tại, event đã được xử lý trước đó và lần giao hiện tại có thể kết thúc như duplicate.

~~~mermaid
flowchart TD
    A["Nhận event"] --> B["Bắt đầu DB transaction"]
    B --> C["INSERT inbox với unique key"]
    C --> D{"Insert được một hàng?"}
    D -- Không --> E["Đã xử lý: bỏ qua duplicate"]
    D -- Có --> F["Cập nhật business state"]
    F --> G["Commit transaction"]
    E --> H["Handler trả về thành công"]
    G --> H
    H --> I["Binder/broker xác nhận theo cấu hình"]
~~~

Điểm quan trọng là inbox insert và business update phải commit hoặc rollback cùng nhau. Nếu insert inbox commit riêng rồi process chết trước khi cập nhật business data, lần giao sau sẽ bị đánh dấu duplicate dù nghiệp vụ chưa xảy ra. Nếu business update commit riêng rồi inbox insert thất bại, lần giao lại có thể lặp side effect.

## 3. Thiết kế định danh event ổn định

Consumer cần một event identity ổn định qua mọi lần retry, redelivery và replay. Nên dùng event ID do producer tạo và giữ nguyên khi gửi lại.

Một envelope có thể gồm:

~~~json
{
  "id": "7c83c4f2-3e0f-4d7c-9b8e-4d6c6c2c0101",
  "source": "order-service",
  "type": "com.example.order.created.v1",
  "subject": "orders/ORD-1001",
  "time": "2026-11-24T08:30:00Z",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-42",
    "amount": 125.50
  }
}
~~~

Trong ví dụ, id là định danh event, source là producer identity, còn type mô tả contract. Nếu dùng CloudEvents, có thể lấy cặp source và id làm identity theo contract của producer. Ví dụ database bên dưới chọn UUID cho event ID; nếu contract dùng ID chuỗi bất kỳ, đổi cột event_id sang VARCHAR và truyền nguyên chuỗi.

Không tạo UUID mới ở consumer mỗi lần nhận message; như vậy mỗi lần redelivery sẽ có khóa khác và inbox không nhận ra duplicate. Cũng không dùng timestamp hoặc business payload làm ID nếu chúng không được bảo đảm duy nhất.

### 3.1. Chọn phạm vi unique key

Không phải event ID luôn duy nhất trên toàn hệ thống. Hãy chọn khóa theo contract:

| Trường hợp | Khóa gợi ý |
|---|---|
| Event ID duy nhất toàn nền tảng | (consumer_name, event_id) |
| Event ID chỉ duy nhất trong producer | (consumer_name, producer_id, event_id) |
| Event ID chỉ duy nhất trong tenant | (consumer_name, tenant_id, producer_id, event_id) |
| Nhiều logical consumer cần xử lý cùng event | Mỗi consumer có consumer_name riêng |

consumer_name là tên ổn định của logical handler, ví dụ orders-projection hoặc billing-ledger. Không gắn version triển khai như orders-projection-v2 nếu v2 chỉ thay thế v1 và vẫn phải kế thừa lịch sử chống duplicate. Đổi consumer name sẽ tạo một không gian inbox mới; cùng event có thể được áp dụng lại.

Nếu hai consumer độc lập đều cần xử lý cùng event, mỗi consumer có khóa riêng. Không dùng một bảng inbox chung với khóa event ID đơn lẻ rồi vô tình khiến consumer thứ hai bị bỏ qua.

## 4. Tạo bảng inbox với unique constraint

Ví dụ dưới đây dùng PostgreSQL:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name  VARCHAR(120) NOT NULL,
    producer_id    VARCHAR(160) NOT NULL,
    event_id       UUID NOT NULL,
    event_type     VARCHAR(240) NOT NULL,
    payload_hash   BYTEA,
    received_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at   TIMESTAMPTZ,
    CONSTRAINT pk_consumer_inbox
        PRIMARY KEY (consumer_name, producer_id, event_id)
);
~~~

Primary key ở đây đồng thời tạo unique constraint trên ba cột. Database bảo vệ tính duy nhất ngay cả khi nhiều thread, nhiều Pod hoặc nhiều consumer cùng xử lý event.

Nếu ID chỉ duy nhất trong tenant, thêm tenant_id vào bảng và primary key, đồng thời truyền tenant_id trong lệnh insert. Không chỉ thêm tenant vào code kiểm tra mà bỏ nó khỏi unique constraint của database.

Các cột có ý nghĩa:

- consumer_name: logical consumer sở hữu lần xử lý.
- producer_id: namespace định danh producer.
- event_id: ID ổn định do producer tạo.
- event_type: hỗ trợ điều tra và thống kê theo contract.
- payload_hash: tùy chọn, dùng phát hiện producer tái sử dụng cùng ID cho payload khác.
- received_at: thời điểm transaction ghi inbox.
- processed_at: thời điểm business update hoàn tất, được cập nhật trước khi transaction commit.

Với xử lý đồng bộ trong một transaction, hàng inbox chỉ nhìn thấy sau khi transaction commit. processed_at được cập nhật sau business update nhưng trước commit; transaction rollback sẽ xóa cả hàng inbox và thay đổi nghiệp vụ. Nếu cần lưu riêng thời điểm bắt đầu và kết thúc, dùng state machine riêng ở phần xử lý bất đồng bộ.

Không lưu toàn bộ payload trong inbox nếu không có nhu cầu audit/replay rõ ràng. Lưu ID và metadata thường đủ để deduplicate; payload có thể chứa dữ liệu cá nhân hoặc làm bảng tăng rất nhanh.

## 5. Unique constraint là hàng rào chống race condition

Một cách triển khai sai thường gặp:

~~~java
if (!inboxRepository.existsById(eventId)) {
    orderService.apply(event);
    inboxRepository.save(new InboxEntry(eventId));
}
~~~

Hai consumer có thể cùng chạy existsById trước khi bên nào insert. Cả hai đều nhận kết quả chưa tồn tại, rồi cùng cập nhật business state. Đây là race condition kiểu check-then-act.

Một distributed lock ở tầng ứng dụng cũng dễ sai nếu lock hết hạn, process chết hoặc nhiều instance không dùng chung một lock service. Unique constraint của database cung cấp điểm phân xử nguyên tử ngay tại nơi dữ liệu nghiệp vụ được ghi.

Quy tắc:

1. Để database thử insert khóa inbox.
2. Chỉ transaction insert thành công mới được thực hiện business update.
3. Transaction duplicate không được thực hiện side effect.
4. Nếu business update lỗi, rollback cả inbox insert.

Unique constraint cần nằm trong database dùng chung bởi tất cả consumer instance. Một HashSet hoặc cache cục bộ chỉ chống duplicate trong một JVM; nó không chống được restart, scale out hoặc nhiều Pod.

## 6. Insert-if-absent với PostgreSQL

PostgreSQL hỗ trợ ON CONFLICT DO NOTHING. Lệnh trả về số hàng được insert:

~~~sql
INSERT INTO consumer_inbox (
    consumer_name,
    producer_id,
    event_id,
    event_type,
    payload_hash
)
VALUES (
    :consumerName,
    :producerId,
    :eventId,
    :eventType,
    :payloadHash
)
ON CONFLICT (consumer_name, producer_id, event_id)
DO NOTHING;
~~~

- Kết quả 1: transaction này giành được khóa event; có thể tiếp tục business update.
- Kết quả 0: khóa đã tồn tại; event đã được inbox của logical consumer ghi nhận.

Khi hai transaction đồng thời insert cùng khóa, PostgreSQL kiểm tra unique index và điều phối xung đột. Transaction thua chờ kết quả của transaction thắng; sau khi transaction thắng commit, lệnh của transaction còn lại không insert hàng mới.

Không dùng ON CONFLICT DO UPDATE để ghi đè payload hoặc thời điểm xử lý một cách mù quáng. Một duplicate có payload khác có thể là lỗi producer nghiêm trọng; ghi đè sẽ che mất dấu hiệu đó.

## 7. Tích hợp với Spring Cloud Stream và JdbcTemplate

Ví dụ sau minh họa một consumer imperative nhận OrderCreated, dùng JdbcTemplate để claim event trong inbox rồi cập nhật bảng đơn hàng. Giả sử inbox và business table nằm cùng database, cùng transaction manager.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderCreated(
    String producerId,
    UUID eventId,
    String orderId,
    String customerId,
    BigDecimal amount,
    Instant occurredAt
) {}
~~~

Service xử lý transaction:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCreatedHandler {

    private static final String CONSUMER = "orders-projection";

    private final JdbcTemplate jdbc;

    public OrderCreatedHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean handle(OrderCreated event) {
        int inserted = jdbc.update("""
            INSERT INTO consumer_inbox (
                consumer_name,
                producer_id,
                event_id,
                event_type
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT (consumer_name, producer_id, event_id)
            DO NOTHING
            """,
            CONSUMER,
            event.producerId(),
            event.eventId(),
            "OrderCreated"
        );

        if (inserted == 0) {
            return false; // Duplicate: business update không chạy lại.
        }

        jdbc.update("""
            INSERT INTO order_projection (
                order_id, customer_id, amount, created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            event.orderId(),
            event.customerId(),
            event.amount(),
            event.occurredAt()
        );

        jdbc.update("""
            UPDATE consumer_inbox
            SET processed_at = clock_timestamp()
            WHERE consumer_name = ?
              AND producer_id = ?
              AND event_id = ?
            """,
            CONSUMER,
            event.producerId(),
            event.eventId()
        );

        return true;
    }
}
~~~

Spring Cloud Stream function gọi service:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderCreated> orderCreated(OrderCreatedHandler handler) {
        return event -> handler.handle(event);
    }
}
~~~

Ví dụ cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderCreated
    stream:
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: orders-projection
~~~

Service transaction hoàn tất trước khi lời gọi handler.handle trả về. Nếu exception thoát ra khỏi handler, transaction rollback và framework/binder áp dụng error handling, retry hoặc dead-letter policy đã cấu hình. Khi handler trả về bình thường cho duplicate, binder có thể xác nhận lần giao đó theo acknowledgment semantics của binder.

### 7.1. Vì sao service transaction nằm ở bean riêng?

Spring thường áp dụng @Transactional qua proxy. Gọi một method transactional từ method khác trong cùng object (self-invocation) có thể bỏ qua proxy và không mở transaction như mong đợi.

Đặt transaction trên service bean riêng, được inject vào function bean, giúp lời gọi đi qua proxy. Cần xác minh transaction manager được chọn đúng và JDBC/JPA dùng cùng DataSource.

### 7.2. Điều kiện để ví dụ thực sự atomic

Inbox insert và business update chỉ atomic khi:

- Cùng database transaction.
- Cùng transaction manager/connection resource.
- Không commit thủ công giữa hai bước.
- Không dùng REQUIRES_NEW cho inbox hoặc business update theo cách tách transaction.
- Không gọi API ngoài database rồi giả định nó rollback cùng JDBC transaction.

Nếu inbox dùng database A còn business state ở database B, transaction local trên A không bảo vệ B. Khi đó cần distributed transaction có chủ đích hoặc thiết kế saga/outbox/inbox theo từng ranh giới dịch vụ.

## 8. Khi business update lỗi thì điều gì xảy ra?

Giả sử insert inbox thành công nhưng INSERT order_projection vi phạm constraint:

1. Exception thoát khỏi service.
2. Transaction rollback.
3. Hàng inbox vừa insert cũng rollback.
4. Lần retry sau có thể insert inbox thành công và thử lại business update.

Đây là tính chất quan trọng nhất của inbox cùng transaction. Nếu code bắt exception rồi trả về bình thường, Spring có thể commit inbox dù business update thất bại. Không nuốt exception nghiệp vụ hoặc database nếu message cần được retry.

Ví dụ không nên làm:

~~~java
@Transactional
public void handle(OrderCreated event) {
    claimInbox(event);
    try {
        updateProjection(event);
    } catch (RuntimeException ex) {
        log.error("Projection failed", ex);
        // Trả về bình thường có thể commit inbox và làm mất cơ hội retry.
    }
}
~~~

Hãy để exception được ném ra hoặc đánh dấu transaction rollback-only theo chính sách rõ ràng. Chỉ chuyển message vào DLQ khi lỗi thuộc nhóm không thể xử lý theo retry policy; việc chuyển DLQ phải là quyết định của error handler/binder và được quan sát.

Spring mặc định rollback transaction khi có unchecked exception hoặc Error. Nếu business method ném checked exception mà lỗi đó cũng phải rollback inbox và business update, khai báo rollbackFor phù hợp trên @Transactional hoặc chuyển đổi exception theo quy ước của ứng dụng.

## 9. Phân biệt duplicate hợp lệ với event ID bị tái sử dụng sai

Nếu cùng (consumer_name, producer_id, event_id) xuất hiện lần nữa với cùng nội dung, đó thường là duplicate có thể bỏ qua.

Nếu cùng khóa xuất hiện nhưng payload khác, có thể producer đã:

- Tái sử dụng event ID cho event mới.
- Gửi lại event bị sửa nội dung thay vì giữ nguyên.
- Có lỗi serialize hoặc route nhầm dữ liệu.
- Có hai producer dùng chung namespace ID không đúng contract.

Không âm thầm coi mọi conflict là duplicate hợp lệ. Có thể lưu SHA-256 của payload canonical hoặc các trường quan trọng, sau đó so sánh khi gặp conflict. Nếu hash khác, ghi metric/error riêng và chuyển sang quy trình điều tra hoặc quarantine.

Hash chỉ có ý nghĩa nếu cách canonicalize dữ liệu ổn định. JSON có thể khác thứ tự field nhưng mang cùng dữ liệu; hash raw bytes sẽ khác. Nếu cần so sánh nội dung logic, hãy canonicalize theo schema/contract trước khi hash.

## 10. Unique constraint cho business invariant

Inbox bảo đảm cùng event không được áp dụng hai lần bởi một logical consumer. Một business invariant có thể cần unique constraint riêng.

Ví dụ mỗi payment provider transaction chỉ được ghi nhận một lần:

~~~sql
CREATE TABLE payment_ledger (
    id BIGSERIAL PRIMARY KEY,
    provider_name VARCHAR(80) NOT NULL,
    provider_transaction_id VARCHAR(180) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    amount NUMERIC(19, 4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_payment_provider_transaction
        UNIQUE (provider_name, provider_transaction_id)
);
~~~

Inbox bảo vệ event delivery identity; unique constraint trên ledger bảo vệ quy tắc nghiệp vụ. Hai lớp bổ sung cho nhau:

- Hai event ID khác nhau có thể cùng tham chiếu một provider transaction; ledger constraint ngăn ghi hai lần.
- Cùng event ID được gửi lại; inbox constraint ngăn handler chạy lại.
- Hai Pod xử lý hai event khác nhau nhưng cùng order/payment key; business constraint vẫn bảo vệ dữ liệu.

Không thay thế một business constraint bằng inbox. Cũng không dùng unique constraint quá rộng làm mất các nghiệp vụ hợp lệ, ví dụ một order có nhiều payment attempt khác nhau.

## 11. Xử lý lỗi unique constraint theo database

SQL ON CONFLICT DO NOTHING trong ví dụ là cú pháp PostgreSQL. Các hệ quản trị khác có cú pháp và semantics riêng:

| Database | Cách triển khai thường gặp | Điều cần kiểm tra |
|---|---|---|
| PostgreSQL | INSERT ... ON CONFLICT DO NOTHING | Conflict target phải khớp unique constraint mong muốn |
| MySQL | INSERT IGNORE hoặc INSERT ... ON DUPLICATE KEY | IGNORE có thể che một số lỗi khác; row count phụ thuộc cấu hình |
| SQL Server | Insert có xử lý unique violation hoặc chiến lược locking phù hợp | Tránh giả định MERGE luôn an toàn trong mọi concurrency pattern |
| Oracle | Insert và bắt unique violation theo constraint cụ thể | Transaction/error handling phải giữ đúng atomicity |

Khi dùng JPA save() rồi bắt DataIntegrityViolationException, transaction có thể đã bị đánh dấu rollback-only. Không bắt exception rồi tiếp tục business update trong cùng transaction và giả định nó vẫn commit được.

Hãy ưu tiên primitive insert-if-absent/upsert phù hợp database. Nếu dùng unique violation để phân xử, thiết kế savepoint/transaction boundary và kiểm thử với đúng database production. Không chỉ kiểm thử bằng H2 rồi suy luận PostgreSQL/MySQL có cùng semantics.

## 12. Không dùng SELECT trước INSERT làm cơ chế duy nhất

Đoạn sau không an toàn khi có nhiều instance:

~~~sql
SELECT 1
FROM consumer_inbox
WHERE consumer_name = 'orders-projection'
  AND producer_id = 'order-service'
  AND event_id = '7c83c4f2-3e0f-4d7c-9b8e-4d6c6c2c0101';
~~~

Kết quả "không có hàng" chỉ đúng tại thời điểm truy vấn. Transaction khác có thể insert ngay sau đó. Một SELECT rồi INSERT không tự tạo tính duy nhất.

SELECT vẫn hữu ích để đọc metadata của event đã xử lý, ví dụ kiểm tra payload hash. Nhưng quyết định claim event phải dựa trên thao tác ghi được bảo vệ bởi unique constraint, hoặc một cơ chế locking/isolation đã được chứng minh trên database đang dùng.

## 13. Inbox cho xử lý đồng bộ và xử lý bất đồng bộ

### 13.1. Đồng bộ trong một transaction

Đây là dạng đơn giản nhất:

1. Nhận event.
2. Insert inbox.
3. Cập nhật business tables.
4. Commit một transaction.
5. Handler trả về để binder xác nhận message theo cấu hình.

Phù hợp khi xử lý nghiệp vụ đủ ngắn để transaction database có thời gian sống hợp lý. Không giữ transaction mở trong lúc chờ API ngoài kéo dài.

### 13.2. Bất đồng bộ với trạng thái inbox

Nếu cần xử lý dài, có thể tách tiếp nhận và thực thi:

~~~sql
CREATE TABLE inbox_work (
    consumer_name VARCHAR(120) NOT NULL,
    producer_id VARCHAR(160) NOT NULL,
    event_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_until TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (consumer_name, producer_id, event_id),
    CHECK (status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED'))
);
~~~

Consumer transaction insert PENDING rồi commit; message broker có thể được xác nhận sau khi hàng work đã được lưu bền vững. Một worker riêng claim công việc bằng locking/lease, xử lý và cập nhật PROCESSED.

Thiết kế này cần thêm:

- Cách claim work nguyên tử để hai worker không xử lý cùng hàng.
- Lease/lock expiry để phục hồi khi worker chết.
- Attempt count, retry schedule và giới hạn retry.
- Quy tắc chuyển FAILED hoặc phát lệnh DLQ.
- Metrics cho tuổi hàng PENDING và PROCESSING quá hạn.
- Idempotency cho side effect bên ngoài.

Không để trạng thái PROCESSING khóa vĩnh viễn nếu worker crash. Lease cần hết hạn và có quy trình reclaim. Cũng không đánh dấu PROCESSED trước khi side effect đạt ranh giới hoàn tất.

## 14. Kết hợp inbox và outbox

Inbox chống event đầu vào được áp dụng lặp. Nếu consumer còn cần publish một event đầu ra, có thể dùng outbox để bảo vệ bước đó:

~~~mermaid
flowchart TD
    A["Nhận event đầu vào"] --> B["DB transaction"]
    B --> C["Insert inbox unique key"]
    C --> D["Update business state"]
    D --> E["Insert outbox event"]
    E --> F["Commit"]
    F --> G["Outbox relay"]
    G --> H["Publish tới broker"]
    H --> I["Đánh dấu outbox đã gửi"]
~~~

Inbox, business update và outbox insert nằm trong cùng transaction database. Nếu transaction rollback, cả ba đều rollback. Relay đọc outbox và publish sau commit; nếu relay chết sau publish nhưng trước khi đánh dấu sent, nó có thể publish lại. Vì vậy downstream consumer vẫn cần inbox/idempotency.

Ví dụ bảng outbox:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(240) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);
~~~

Không gọi outbox relay là exactly-once. Outbox bảo đảm event được lưu cùng business transaction và có thể publish lại; duplicate ở ranh giới broker vẫn cần được xử lý.

## 15. External API và side effect không nằm trong database transaction

Một transaction JDBC không thể rollback email đã gửi, HTTP request đã thành công hoặc lệnh thanh toán đã được nhà cung cấp chấp nhận.

Ví dụ không nên:

~~~java
@Transactional
public void handle(PaymentRequested event) {
    claimInbox(event);
    paymentGateway.charge(event.paymentId(), event.amount());
    paymentRepository.markPaid(event.paymentId());
}
~~~

Nếu gateway charge thành công nhưng database transaction rollback, lần retry có thể charge lần nữa. Inbox rollback không thể hoàn tác charge bên ngoài.

Các lựa chọn an toàn hơn:

- Gửi idempotency key ổn định tới API bên ngoài nếu provider hỗ trợ.
- Ghi command/outbox trong transaction, sau đó worker gọi API với idempotency key.
- Lưu trạng thái workflow và reconcile với provider khi timeout không rõ kết quả.
- Dùng saga/compensation khi quy trình trải qua nhiều dịch vụ.

Không tạo idempotency key mới cho mỗi retry. Key phải giữ nguyên cho cùng một business operation.

## 16. Inbox retention và replay

Inbox chỉ ngăn duplicate khi hàng tương ứng còn tồn tại. Nếu xóa hàng quá sớm, event cũ được replay sau đó sẽ được xem như mới.

Retention cần tính tới:

- Broker retention và thời gian message có thể còn trong queue/topic.
- Retry topic, delayed retry và DLQ retention.
- Thời gian operator có thể redrive message.
- Backfill, disaster recovery và replay từ archive.
- Thời gian producer có thể gửi lại event cũ.
- Quy định lưu trữ dữ liệu và quyền riêng tư.

Ví dụ nếu event có thể được replay trong 30 ngày, không xóa inbox sau 7 ngày nếu không có một dedupe archive khác. Có thể partition bảng theo thời gian, archive khóa cũ hoặc lưu compacted dedupe key; nhưng cleanup phải giữ đúng khoảng chống duplicate.

Không xóa inbox chỉ để giảm dung lượng mà không xem xét replay window. Khi cần replay có chủ đích như tái tạo projection, hãy dùng một logical consumer identity/version mới và database/output cách ly theo kế hoạch. Đổi consumer name là hành động thay đổi semantics dedupe, không phải thao tác vô hại.

## 17. Inbox và thứ tự xử lý

Inbox giải quyết duplicate, không tự bảo đảm thứ tự event. Hai event khác nhau cho cùng aggregate có thể được xử lý đồng thời hoặc đảo thứ tự nếu broker partition/queue và concurrency cho phép.

Nếu business invariant yêu cầu thứ tự:

- Dùng aggregate key nhất quán làm Kafka key hoặc routing key phù hợp.
- Kiểm tra partition/queue ordering semantics và consumer concurrency.
- Lưu aggregate version hoặc sequence number.
- Chỉ áp dụng event nếu version kế tiếp hợp lệ; phát hiện gap và retry/reconcile.
- Đặt unique constraint cho (aggregate_id, aggregate_version) nếu mỗi version chỉ được ghi một lần.

Ví dụ:

~~~sql
ALTER TABLE order_projection
ADD COLUMN last_event_version BIGINT NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX uq_order_event_version
ON applied_order_event (order_id, event_version);
~~~

Khi nhận version thấp hơn hoặc bằng version đã áp dụng, consumer có thể nhận diện duplicate/stale event. Khi nhận version nhảy cóc, không nên đánh dấu event đã xử lý rồi bỏ qua; cần chờ event thiếu hoặc chuyển sang quy trình repair.

## 18. Inbox trong nhiều consumer và nhiều binding

Một ứng dụng Spring Cloud Stream có thể có nhiều function/binding. Mỗi logical consumer cần namespace riêng:

~~~text
orders-projection + order-service + event-101
billing-ledger    + order-service + event-101
shipping-planner  + order-service + event-101
~~~

Ba hàng trên đều hợp lệ vì ba consumer có trách nhiệm riêng. Nếu chỉ dùng (producer_id, event_id) làm primary key toàn bảng, consumer đầu tiên xử lý sẽ ngăn hai consumer còn lại. Vì vậy consumer_name thường là một phần của unique key.

Nếu một function có nhiều binding đầu vào nhưng cùng cập nhật một projection, quyết định consumer identity theo logical business handler, không chỉ theo tên bean hoặc binding ngẫu nhiên. Identity phải ổn định qua refactor tên function và deployment.

## 19. Kiểm thử duplicate và concurrency

Kiểm thử chỉ gửi cùng message hai lần tuần tự là chưa đủ. Race condition thường chỉ xuất hiện khi hai instance cùng claim một event gần như đồng thời.

### 19.1. Các kịch bản bắt buộc

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Duplicate tuần tự | Gửi cùng event ID hai lần | Business update chỉ một lần |
| Duplicate đồng thời | Hai thread/Pod xử lý cùng ID | Một transaction insert inbox; chỉ một business update |
| Rollback sau inbox insert | Gây lỗi business update | Inbox và business state đều rollback |
| Crash sau DB commit trước ACK | Ngắt consumer tại điểm test | Redelivery bị inbox nhận diện; không lặp update |
| Hai consumer độc lập | Cùng event tới hai logical consumer | Mỗi consumer xử lý một lần |
| Cùng ID, payload khác | Gửi cùng key với nội dung khác | Phát hiện conflict, không âm thầm ghi đè |
| ID trùng giữa producer | Hai producer cùng event ID | Producer namespace tách biệt |
| Replay sau retention | Redrive event cũ | Hành vi phù hợp chính sách retention |
| External API timeout | Provider có thể đã thực hiện request | Retry giữ nguyên idempotency key và reconcile |
| Event sai thứ tự | Gửi version 12 trước version 11 | Không đánh dấu bỏ qua gap như event đã hoàn tất |

### 19.2. Kiểm thử cạnh tranh trên database thật

Với PostgreSQL, có thể dùng Testcontainers để chạy đúng engine và phiên bản gần production. Tạo hai transaction cùng insert một inbox key, đồng thời điều khiển latch để chúng chạy gần nhau. Xác minh:

- Tổng số hàng inbox cho key bằng một.
- Tổng số business mutation bằng một.
- Transaction thua nhận kết quả duplicate sau khi transaction thắng hoàn tất.
- Nếu transaction thắng rollback, transaction còn lại có thể claim và xử lý.

Không chỉ dùng mock repository vì mock không mô phỏng unique index, lock wait, isolation hoặc transaction rollback.

## 20. Ví dụ kiểm thử service với hai lần giao

Ví dụ test tích hợp khái niệm dùng database đã được cấu hình trong Spring test context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class OrderCreatedHandlerIT {

    @Autowired
    OrderCreatedHandler handler;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void duplicateEventChangesProjectionOnlyOnce() {
        UUID eventId = UUID.randomUUID();
        OrderCreated event = new OrderCreated(
            "order-service",
            eventId,
            "ORD-9001",
            "CUS-9001",
            new BigDecimal("125.50"),
            Instant.parse("2026-11-24T08:30:00Z")
        );

        boolean first = handler.handle(event);
        boolean second = handler.handle(event);

        assertThat(first).isTrue();
        assertThat(second).isFalse();

        Integer inboxRows = jdbc.queryForObject("""
            SELECT COUNT(*)
            FROM consumer_inbox
            WHERE consumer_name = 'orders-projection'
              AND producer_id = 'order-service'
              AND event_id = ?
            """, Integer.class, eventId);

        Integer projectionRows = jdbc.queryForObject("""
            SELECT COUNT(*)
            FROM order_projection
            WHERE order_id = 'ORD-9001'
            """, Integer.class);

        assertThat(inboxRows).isEqualTo(1);
        assertThat(projectionRows).isEqualTo(1);
    }
}
~~~

Test trên minh họa duplicate tuần tự. Test concurrency cần chạy hai transaction trên hai thread với cùng event và dùng latch/barrier để tăng xác suất tranh chấp; sau đó xác minh row count và business effect. Cũng cần test transaction rollback để chứng minh inbox không bị commit riêng.

Nếu test method được đánh dấu @Transactional, cần lưu ý transaction test bao ngoài có thể làm thay đổi cách commit/visibility. Để kiểm thử transaction boundary thật, gọi service qua Spring proxy trong các transaction độc lập và xác minh dữ liệu sau khi mỗi lời gọi hoàn tất.

## 21. Quan sát inbox trong production

Inbox giúp chống duplicate nhưng cũng cần metrics để phát hiện producer/broker có vấn đề:

- Tổng số event mới được claim.
- Số duplicate bị bỏ qua.
- Tỷ lệ duplicate theo producer, event type và binding.
- Unique conflict rate và thời gian chờ lock.
- Transaction rollback và business update failure.
- Tuổi hàng PENDING/PROCESSING nếu dùng worker bất đồng bộ.
- Số event cùng ID nhưng payload hash khác.
- Dung lượng bảng, tốc độ tăng và thời gian cleanup.
- Thời gian xử lý từ received tới committed.

Không gắn event ID hoặc order ID làm metric label vì cardinality tăng không giới hạn. Có thể ghi event ID trong structured log/tracing với chính sách bảo vệ dữ liệu; metric dùng label có cardinality thấp như consumer, producer và event type.

Tỷ lệ duplicate tăng đột biến có thể cho biết:

- Producer retry quá nhiều do confirmation timeout.
- Consumer restart/rebalance liên tục.
- Ack/commit thường xuyên thất bại.
- Operator replay hoặc redrive.
- Một producer gửi cùng event nhiều lần do bug.

Duplicate bị bỏ qua không nhất thiết là lỗi, nhưng xu hướng bất thường cần điều tra.

## 22. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ dùng existsById trước insert | Hai consumer cùng vượt qua check | Claim bằng insert được unique constraint bảo vệ |
| Inbox và business update ở hai transaction | Có thể đánh dấu đã xử lý nhưng business chưa commit | Dùng cùng database transaction |
| Tạo event ID mới khi retry | Mỗi lần giao được xem như event mới | Producer giữ ID ổn định |
| Dùng inbox identity thay đổi theo release | Rollback/deploy mới có thể xử lý lại toàn bộ event | Dùng logical consumer name ổn định |
| Bỏ consumer_name khỏi khóa khi có nhiều handler | Consumer này chặn consumer khác | Namespace theo logical consumer |
| Bắt mọi exception rồi trả về bình thường | Binder có thể ACK event lỗi | Propagate lỗi hoặc rollback transaction |
| Bắt unique violation rồi tiếp tục trong transaction rollback-only | Business update không commit hoặc lỗi cuối transaction | Dùng insert-if-absent/upsert đúng database |
| Chỉ dedupe trong cache JVM | Duplicate sau restart hoặc ở Pod khác | Unique constraint trong database dùng chung |
| Xóa inbox quá sớm | Replay cũ có thể lặp side effect | Retention lớn hơn replay/retry window |
| Gọi API ngoài trong DB transaction | External side effect không rollback | Outbox, provider idempotency key và reconciliation |
| Coi inbox là exactly-once toàn hệ thống | Vẫn có duplicate ở broker hoặc dịch vụ tiếp theo | Inbox ở mỗi consumer và outbox ở producer boundary |
| Hash raw JSON để so nội dung | Field order/format có thể tạo hash khác | Canonicalize theo schema hoặc hash semantic fields |

## 23. Quy trình triển khai inbox cho một consumer

1. Xác định event identity ổn định từ producer contract.
2. Chọn logical consumer name và phạm vi uniqueness.
3. Tạo inbox table cùng unique/primary key.
4. Xác định business update nào phải nằm trong cùng database transaction.
5. Implement insert-if-absent bằng primitive phù hợp database.
6. Chỉ chạy business update khi insert claim thành công.
7. Để exception nghiệp vụ thoát ra để transaction rollback và binder áp dụng retry.
8. Nếu cần output, ghi outbox trong cùng transaction.
9. Làm side effect ngoài database idempotent hoặc có workflow/reconciliation.
10. Định nghĩa retention theo broker retention, retry, DLQ và replay window.
11. Test duplicate tuần tự, đồng thời, rollback và crash trước ACK.
12. Theo dõi duplicate rate, transaction failure, lock wait và inbox growth.

## 24. Checklist thiết kế và vận hành

- [ ] Producer tạo event ID ổn định và giữ nguyên khi retry.
- [ ] Identity có đủ namespace producer/tenant nếu event ID không duy nhất toàn hệ thống.
- [ ] Logical consumer name ổn định qua deployment và refactor.
- [ ] Inbox có primary key/unique constraint ở database dùng chung.
- [ ] Inbox insert và business update cùng transaction.
- [ ] Insert-if-absent là thao tác nguyên tử; không chỉ SELECT rồi INSERT.
- [ ] Duplicate không chạy lại business side effect.
- [ ] Business invariants quan trọng có unique constraint riêng.
- [ ] Exception nghiệp vụ không bị nuốt và không commit inbox sai.
- [ ] External API có idempotency key hoặc outbox/workflow phù hợp.
- [ ] Payload ID conflict được phát hiện nếu cùng key nhưng nội dung khác.
- [ ] Retention đủ dài cho retry, DLQ redrive, replay và recovery.
- [ ] Có test đồng thời bằng database engine tương đương production.
- [ ] Có test crash sau DB commit nhưng trước broker ACK/offset commit.
- [ ] Có dashboard duplicate rate, transaction failure và inbox storage.
- [ ] Cleanup inbox có kế hoạch và không phá replay guarantee.

## 25. Nguyên tắc cần nhớ

Inbox không ngăn broker giao lại message. Inbox bảo đảm consumer có thể nhận ra event đã được áp dụng và bỏ qua lần giao trùng. Unique constraint là cơ chế phân xử an toàn giữa nhiều transaction; transaction chung làm cho dấu inbox và business state cùng thành công hoặc cùng thất bại.

Với Spring Cloud Stream, handler nên trả về bình thường sau khi transaction nghiệp vụ hoàn tất hoặc sau khi xác định đó là duplicate hợp lệ. Khi transaction thất bại, để lỗi đi tới error handling của binder để message có thể retry hoặc đi DLQ theo chính sách. Nếu consumer phát output hoặc gọi hệ thống ngoài, dùng outbox, idempotency key và reconciliation để bảo vệ ranh giới đó.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/): functional model, bindings, consumer error handling và binder configuration.
- [Spring Framework Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): declarative transaction, propagation và transaction manager.
- [Spring JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): JdbcTemplate và quản lý tài nguyên JDBC.
- [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html): ON CONFLICT và insert-if-absent.
- [PostgreSQL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary key, unique constraint và kiểm tra tính duy nhất.
- [Apache Kafka Consumer Design](https://kafka.apache.org/documentation/#intro_consumers): consumer group, offset và xử lý record.
- [RabbitMQ Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): ACK/NACK và delivery chưa được xác nhận.
- [Apache Pulsar Messaging](https://pulsar.apache.org/docs/next/concepts-messaging/): acknowledgment, redelivery và subscription.
- [CloudEvents Specification](https://cloudevents.io/): event envelope, id, source và event identity.
