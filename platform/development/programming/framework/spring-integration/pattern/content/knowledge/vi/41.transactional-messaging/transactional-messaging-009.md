# Outbox như cách tách business transaction khỏi transport

## 1. Bài toán: cập nhật nghiệp vụ xong nhưng sự kiện không tới broker

Một ứng dụng bán hàng có quy trình:

1. Ghi đơn hàng `order-501` vào database.
2. Phát sự kiện `OrderCreated` sang message broker.
3. Hệ thống tồn kho, gửi email và kế toán tiêu thụ sự kiện.

Nếu ứng dụng chỉ thực hiện hai thao tác liên tiếp, có hai cửa sổ lỗi:

~~~java
// Ví dụ cố ý thiếu bảo đảm, KHÔNG nên dùng trong production.
orderRepository.save(order);
brokerClient.send(orderCreatedEvent);
~~~

- **Database commit thành công, broker send thất bại:** đơn hàng đã tồn tại nhưng các hệ thống khác không nhận được sự kiện.
- **Broker send thành công, database rollback:** các hệ thống khác thấy sự kiện cho một đơn hàng chưa từng được commit.

Đảo thứ tự hai lời gọi không giải quyết được cả hai trường hợp. Đưa network call vào `@Transactional` cũng không khiến broker mặc nhiên tham gia transaction của database. Giải pháp **Transactional Outbox** tách **business transaction** khỏi **transport** bằng cách lưu sự kiện vào một bảng outbox **trong cùng local transaction** với dữ liệu nghiệp vụ, rồi phát sự kiện ra bên ngoài ở bước bất đồng bộ.

Trong module **SPRING_INTEGRATION_PATTERN**, kỹ thuật này hỗ trợ thiết kế Enterprise Integration Patterns với Spring Integration: Router, Filter, Transformer, Splitter, Aggregator, Gateway, error channel, retry và correlation. Outbox không phải một `MessageChannel` đặc biệt; nó là **mẫu kiến trúc tại ranh giới giao dịch** mà các IntegrationFlow có thể sử dụng.

### Mục tiêu sau bài học

- Giải thích vì sao lưu đơn hàng và bản ghi outbox cùng một transaction tránh tình trạng **business commit mà không có ý định phát sự kiện**.
- Thiết kế relay đọc outbox và gửi sang transport khi database đã commit.
- Nhận diện đúng các rủi ro **at-least-once**, duplicate, crash, retry và ordering.
- Biết vị trí của Spring Integration, Spring Transaction, scheduler, error channel và idempotent consumer.
- Viết được kịch bản kiểm thử rollback, publish thành công/thất bại, restart và nhiều worker.

## 2. Luồng kiến trúc của Transactional Outbox

~~~mermaid
flowchart LR
    A[API / Gateway] --> B[Order Application Service]
    B --> T["Local DB transaction"]
    T --> O[(orders)]
    T --> X[(integration_outbox)]
    X --> R["Outbox Relay / Dispatcher"]
    R --> I["Spring Integration Flow"]
    I --> K[Broker / Transport]
    K --> C[Consumer]
    C --> N[(Consumer Inbox + Business DB)]
    R -. "Retry / error handling" .-> X
~~~

**Transaction A — Business write:**

~~~text
BEGIN
  INSERT / UPDATE orders ...
  INSERT integration_outbox(eventId, aggregateId, payload, PENDING) ...
COMMIT
~~~

Hai bản ghi được commit cùng nhau hoặc cùng rollback, với điều kiện thực sự dùng **cùng database và cùng transaction manager/resource**.

**Process B — Outbox relay:** một worker đọc bản ghi pending đã commit, gửi nó sang transport, rồi ghi lại kết quả gửi. Phần gửi tới broker **không nằm trong transaction A**; không cần giữ transaction đơn hàng mở để đợi mạng.

**Process C — Consumer:** đọc sự kiện từ transport, xử lý nghiệp vụ của mình và có cơ chế nhận diện sự kiện trùng.

### Outbox đảm bảo và không đảm bảo điều gì?

| Thuộc tính | Transactional Outbox |
| --- | --- |
| Business row và outbox row commit/rollback cùng nhau | **Có**, khi cùng local transaction |
| API phải chờ broker hoạt động mới commit đơn hàng | **Không** |
| Sự kiện tồn tại bền vững trước khi gửi | **Có**, sau khi outbox commit vào DB bền vững |
| Broker luôn nhận ngay lập tức | **Không**; có độ trễ relay và backlog |
| Chỉ phát đúng một lần trong mọi tình huống | **Không**; crash có thể làm relay phát lại |
| Consumer tự động chống xử lý trùng | **Không**; phải thiết kế idempotency/inbox |
| Thứ tự sự kiện giữa mọi aggregate luôn được bảo toàn | **Không**; cần chính sách ordering/partition |

Điểm cốt lõi: Outbox giải quyết **tính nguyên tử giữa thay đổi nghiệp vụ và bản ghi “cần phát”**, chứ không dùng một transaction duy nhất bao trùm database, broker và mọi consumer.

## 3. So sánh Outbox với các cách dễ làm sai

| Cách làm | Vấn đề |
| --- | --- |
| `save()` rồi `broker.send()` ngoài transaction | DB thành công, send lỗi làm mất sự kiện |
| `broker.send()` rồi `save()` | Có thể phát sự kiện khi DB chưa commit |
| `@Transactional` bao quanh cả `save()` và `send()` | JDBC transaction không tự rollback được một broker send đã thành công |
| `@TransactionalEventListener(AFTER_COMMIT)` gọi broker trực tiếp | Callback có thể không chạy nếu process chết ngay sau commit; không tự là outbox bền vững |
| Outbox row cùng transaction, relay riêng | Sau commit có bản ghi sự kiện chờ; relay có thể thử lại khi transport gặp lỗi |

**Lưu ý:** `@TransactionalEventListener` vẫn hữu ích để kích hoạt worker sau commit nhằm giảm độ trễ, **nhưng bản ghi outbox mới là nguồn sự thật bền vững**. Không nên chỉ dựa vào một callback trong RAM để bảo đảm việc phát sự kiện khi ứng dụng có thể crash.

## 4. Thiết kế schema dữ liệu

Ví dụ sau sử dụng **PostgreSQL** để minh họa khả năng claim nhiều worker bằng `FOR UPDATE SKIP LOCKED`. Với MySQL, SQL Server hoặc database khác, cú pháp claim/lock có thể khác; cần điều chỉnh theo hệ quản trị thực tế.

~~~sql
CREATE TABLE orders (
    order_id      text PRIMARY KEY,
    status        text NOT NULL,
    total_cents   bigint NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE integration_outbox (
    id               bigserial PRIMARY KEY,
    event_id         uuid NOT NULL UNIQUE,
    aggregate_id     text NOT NULL,
    event_type       text NOT NULL,
    payload_json     jsonb NOT NULL,
    status           text NOT NULL DEFAULT 'PENDING',
    attempts         integer NOT NULL DEFAULT 0,
    next_attempt_at  timestamptz NOT NULL DEFAULT now(),
    claim_token      uuid,
    lease_until      timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    published_at     timestamptz,
    last_error       text,
    CONSTRAINT outbox_status_check
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'PUBLISHED', 'FAILED'))
);

CREATE INDEX outbox_pending_idx
    ON integration_outbox (status, next_attempt_at, id);

CREATE INDEX outbox_aggregate_idx
    ON integration_outbox (aggregate_id, id);
~~~

**Ý nghĩa các cột chính:**

| Cột | Ý nghĩa |
| --- | --- |
| `event_id` | ID sự kiện nghiệp vụ ổn định; consumer dùng để dedupe |
| `aggregate_id` | Khóa đối tượng nghiệp vụ, ví dụ `order-501`; thường dùng làm routing key/partition key |
| `event_type` | Loại sự kiện, giúp Router chọn nhánh xử lý |
| `payload_json` | Dữ liệu sự kiện độc lập với object Java đang tồn tại trong RAM |
| `status` | Trạng thái relay: `PENDING`, `IN_FLIGHT`, `PUBLISHED` hoặc `FAILED` |
| `attempts` | Số lần relay đã **claim để thử phát** |
| `next_attempt_at` | Không lấy message trước thời điểm retry tiếp theo |
| `claim_token`, `lease_until` | Chống hai worker cùng chủ động sở hữu một bản ghi trong thời gian lease |
| `published_at` | Thời điểm relay xác nhận transport đã chấp nhận theo hợp đồng |
| `last_error` | Thông tin lỗi rút gọn; không lưu credential hay dữ liệu nhạy cảm |

Unique constraint trên `event_id` ngăn hai bản ghi outbox của **cùng một ID sự kiện** trong một database, nhưng không tự chống việc **một bản ghi được gửi nhiều lần** khi relay retry.

### Vòng đời trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Business transaction commit
    PENDING --> IN_FLIGHT: Relay claim
    IN_FLIGHT --> PUBLISHED: Broker ACK và ghi trạng thái
    IN_FLIGHT --> PENDING: Lỗi tạm + backoff
    IN_FLIGHT --> FAILED: Lỗi vĩnh viễn / hết retry budget
    IN_FLIGHT --> IN_FLIGHT: Lease hết hạn, worker khác claim lại
    FAILED --> PENDING: Replay thủ công có kiểm soát
~~~

Khi một worker bị kill trong `IN_FLIGHT`, bản ghi phải có cơ chế **lease hết hạn** để worker khác lấy lại. Nếu chỉ set `PROCESSING` vĩnh viễn mà không có lease/reconciliation, outbox có thể bị kẹt sau crash.

## 5. Producer: lưu nghiệp vụ và outbox trong **cùng một** transaction

Một ví dụ Spring JDBC dễ nhìn thấy ranh giới transaction. `@Transactional` phải được áp dụng trên một phương thức được Spring gọi qua proxy, dùng cùng `DataSource`/transaction manager với các thao tác JDBC.

~~~java
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    public OrderApplicationService(JdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Transactional
    public UUID createOrder(String orderId, long totalCents) {
        UUID eventId = UUID.randomUUID();

        String payload;
        try {
            payload = json.writeValueAsString(Map.of(
                    "eventId", eventId.toString(),
                    "orderId", orderId,
                    "totalCents", totalCents));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize OrderCreated", ex);
        }

        jdbc.update(
                "INSERT INTO orders(order_id, status, total_cents) " +
                "VALUES (?, 'CREATED', ?)",
                orderId, totalCents);

        jdbc.update(
                "INSERT INTO integration_outbox " +
                "(event_id, aggregate_id, event_type, payload_json) " +
                "VALUES (?, ?, 'OrderCreated', CAST(? AS jsonb))",
                eventId, orderId, payload);

        return eventId;
    }
}
~~~

Ở một lời gọi thành công, DB có cả đơn hàng và bản ghi outbox `PENDING`. Nếu câu lệnh insert outbox ném exception làm transaction rollback, bản ghi đơn hàng cũng phải rollback. Nếu ghi đơn hàng thất bại, outbox không được commit.

**Điều kiện bắt buộc:**

- Đã cấu hình `DataSource` và transaction manager; Spring JDBC tham gia cùng transaction.
- Không dùng `REQUIRES_NEW` cho riêng phần insert outbox nếu muốn hai thay đổi luôn cùng commit/rollback.
- Không gọi `createOrder(...)` bằng self-invocation trong cùng bean rồi mặc định `@Transactional` chắc chắn được áp dụng.
- Không nuốt exception khiến transaction vẫn commit; nếu cố ý bắt lỗi, phải có chính sách rollback rõ ràng.
- Với nghiệp vụ cần tránh tạo hai đơn từ một API request gửi lặp, bổ sung **request idempotency key** hoặc unique constraint ở tầng đơn hàng. Đây là bài toán khác với việc outbox relay gửi lặp.

### Đừng phát message trực tiếp trong transaction trên

~~~java
@Transactional
public void unsafeCreateAndPublish(...) {
    // Ghi vào database...
    // brokerClient.send(...); // Không làm nó trở nên atomic với JDBC.
}
~~~

Một broker send thành công rồi database rollback vẫn có thể tạo sự kiện sai. Trong Outbox, `createOrder` chỉ ghi vào DB, còn việc gửi broker thuộc trách nhiệm của relay **sau commit**.

## 6. Relay: claim → publish → đánh dấu

Relay có thể chạy bằng polling, CDC hoặc worker event-driven. Với polling, vòng đời chuẩn là:

1. **Claim** một số bản ghi `PENDING` đã đến thời điểm gửi (và bản ghi `IN_FLIGHT` có lease hết hạn).
2. Commit transaction claim **trước khi gọi network**.
3. Gửi sang broker/transport với `eventId` ổn định.
4. Đợi **ACK phù hợp từ transport**, không chỉ đợi một lời gọi async trả về.
5. Ghi `PUBLISHED`; nếu lỗi thì đặt lại trạng thái và `next_attempt_at`.

~~~mermaid
sequenceDiagram
    participant R as Relay
    participant DB as Outbox DB
    participant B as Broker
    R->>DB: Claim 1 row và commit lease
    DB-->>R: Event + claimToken
    R->>B: Publish(eventId, aggregateId, payload)
    alt Broker xác nhận
      B-->>R: ACK
      R->>DB: Mark PUBLISHED nếu claimToken còn hợp lệ
    else Broker lỗi / timeout
      B--xR: Lỗi hoặc trạng thái không chắc chắn
      R->>DB: Reschedule retry với backoff
    end
~~~

### 6.1. SQL claim cho nhiều relay worker

SQL PostgreSQL minh họa dưới đây chạy trong **một transaction ngắn**, với `:claimToken` là UUID mới cho lần claim và một bản ghi mỗi lần:

~~~sql
WITH picked AS (
    SELECT id
    FROM integration_outbox
    WHERE (status = 'PENDING' AND next_attempt_at <= now())
       OR (status = 'IN_FLIGHT' AND lease_until <= now())
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE integration_outbox AS o
SET status = 'IN_FLIGHT',
    claim_token = :claimToken,
    lease_until = now() + interval '60 seconds',
    attempts = attempts + 1
FROM picked
WHERE o.id = picked.id
RETURNING o.id, o.event_id, o.aggregate_id,
          o.event_type, o.payload_json, o.attempts, o.claim_token;
~~~

`FOR UPDATE SKIP LOCKED` giúp hai transaction claim đang chạy đồng thời ít tranh cùng một row. `claim_token` là **fencing condition** cho thao tác cập nhật tiếp theo; nó không ngăn được một worker cũ thực sự gửi trùng nếu mạng/scheduler bị chậm và lease đã hết hạn.

**Quan trọng:** một lease 60 giây chỉ là con số ví dụ. Phải chọn lease dài hơn thời gian timeout/ACK hợp lý hoặc có cơ chế gia hạn lease; nếu worker gửi chậm hơn lease, worker khác có thể claim lại và gửi trùng. Với relay nhiều instance, cần kiểm chứng concurrency bằng database thực.

### 6.2. Đánh dấu sau ACK bằng token sở hữu

~~~sql
UPDATE integration_outbox
SET status = 'PUBLISHED',
    published_at = now(),
    claim_token = NULL,
    lease_until = NULL,
    last_error = NULL
WHERE id = :id
  AND status = 'IN_FLIGHT'
  AND claim_token = :claimToken;
~~~

Nếu cập nhật ảnh hưởng **0 row**, có thể lease đã hết hạn và worker khác đã claim. Không được tự kết luận sự kiện chắc chắn chưa tới broker; cần kiểm tra ownership/metric và dựa vào idempotency ở consumer.

### 6.3. Lỗi tạm thời: đặt lịch retry

~~~sql
UPDATE integration_outbox
SET status = 'PENDING',
    next_attempt_at = now() + interval '15 seconds',
    claim_token = NULL,
    lease_until = NULL,
    last_error = :safeErrorSummary
WHERE id = :id
  AND status = 'IN_FLIGHT'
  AND claim_token = :claimToken;
~~~

Đây là backoff cố định 15 giây để minh họa. Trong production, có thể dùng exponential backoff kèm jitter, giới hạn số lần thử và deadline nghiệp vụ; khi vượt giới hạn hoặc dữ liệu lỗi vĩnh viễn, chuyển `FAILED` và phát cảnh báo/quarantine thay vì lặp vô tận.

**Không giữ database transaction mở trong khi chờ broker ACK.** Một worker có thể mất vài giây để gửi sự kiện. Nếu giữ row lock xuyên network call sẽ tăng cạnh tranh, kéo dài giao dịch và có thể gây nghẽn database.

## 7. Relay worker và ranh giới Spring Integration

Spring có thể chạy relay bằng `@Scheduled`, một poller, hoặc một worker được gọi từ hệ thống vận hành. Ví dụ sau thể hiện **điều phối**, với repository và transport đóng gói SQL/network:

~~~java
import java.util.Optional;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

record OutboxEvent(
        long id,
        java.util.UUID eventId,
        String aggregateId,
        String eventType,
        String payloadJson,
        int attempts,
        java.util.UUID claimToken) {
}

interface OutboxRepository {
    // claimNext(): transaction DB ngắn, commit lease trước khi trả về.
    Optional<OutboxEvent> claimNext();
    void markPublished(OutboxEvent event);
    void scheduleRetryOrFail(OutboxEvent event, Exception failure);
}

interface OutboxTransport {
    // Chỉ return sau khi transport xác nhận theo contract đã chọn.
    // Không chỉ enqueue async trong RAM rồi coi là publish thành công.
    void publishAndAwaitAck(OutboxEvent event) throws Exception;
}

@Component
class OutboxRelay {
    private final OutboxRepository repository;
    private final OutboxTransport transport;

    OutboxRelay(OutboxRepository repository, OutboxTransport transport) {
        this.repository = repository;
        this.transport = transport;
    }

    @Scheduled(fixedDelay = 1_000)
    public void poll() {
        for (int i = 0; i < 20; i++) {
            Optional<OutboxEvent> candidate = repository.claimNext();
            if (candidate.isEmpty()) {
                return;
            }
            publishOne(candidate.get());
        }
    }

    private void publishOne(OutboxEvent event) {
        try {
            transport.publishAndAwaitAck(event);
        } catch (Exception failure) {
            repository.scheduleRetryOrFail(event, failure);
            return;
        }
        // Nếu update này lỗi sau broker ACK, relay có thể gửi trùng
        // khi lease hết hạn. Consumer phải idempotent.
        repository.markPublished(event);
    }
}
~~~

Đây là **ví dụ kiến trúc**, không phải một ứng dụng chạy độc lập: cần triển khai `OutboxRepository` với SQL ở mục 6, `OutboxTransport` với broker, bật scheduling khi dùng `@Scheduled`, cấu hình transaction, logging và testing. Không chạy network call bên trong method `claimNext()` có transaction mở.

### Spring Integration nằm ở đâu?

Relay có thể gọi một `DirectChannel`, và IntegrationFlow chuyển message đến adapter. Chỉ đánh dấu `PUBLISHED` nếu hợp đồng của endpoint thực sự đảm bảo ACK mong muốn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class OutboxTransportIntegrationConfig {

    @Bean("outbox.transport")
    MessageChannel outboxTransportChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow outboxTransportFlow(BrokerClient broker) {
        return IntegrationFlow.from("outbox.transport")
                .handle(OutboxEvent.class, (event, headers) -> {
                    broker.sendAndAwaitAck(
                            event.aggregateId(),
                            event.eventId().toString(),
                            event.eventType(),
                            event.payloadJson());
                    return null;
                })
                .get();
    }
}

// Hợp đồng minh họa; triển khai thực tế bằng Kafka/Rabbit/JMS/etc.
interface BrokerClient {
    void sendAndAwaitAck(String key, String eventId,
                         String type, String jsonPayload);
}
~~~

Ở ví dụ này, `DirectChannel` chạy handler đồng bộ; `sendAndAwaitAck` **phải thực sự đợi xác nhận transport** và ném exception khi không có xác nhận hợp lệ. Nếu thay bằng `ExecutorChannel`/`QueueChannel` hoặc adapter chỉ enqueue vào buffer nội bộ, `send() == true` **không chứng minh broker đã nhận**. Khi đó không được đánh dấu outbox `PUBLISHED` dựa riêng vào việc gửi vào channel.

Nếu transport trả về ACK không rõ kết quả (ví dụ timeout sau khi broker đã nhận), hãy để relay retry bằng **cùng event ID**, không tạo event ID mới. Spring Integration error channel có thể ghi nhận lỗi; chính **outbox status + retry scheduling** mới quyết định khi nào phát lại. Đừng để cả error flow và dispatcher cùng requeue mà không có một owner retry rõ ràng.

### Phân công EIP trong relay

| Pattern | Ứng dụng trong Outbox |
| --- | --- |
| **Filter** | Bỏ qua sự kiện không còn hợp lệ nếu chính sách nghiệp vụ cho phép; ghi nhận rõ trạng thái |
| **Transformer** | Từ bản ghi outbox thành message transport và headers có schema version |
| **Router** | Chọn topic/queue theo `event_type` hoặc tenant |
| **Service Activator** | Gửi broker, xử lý ACK, ném exception nếu lỗi |
| **Retry/error channel** | Xử lý lỗi publish và định hướng retry/quarantine |
| **Correlation** | Dùng `eventId`, `aggregateId` và trace ID để liên kết log |
| **Aggregator** | Gom kết quả downstream nếu nghiệp vụ cần, không phải thành phần bắt buộc của outbox |

## 8. Cửa sổ crash: vì sao Outbox thường là at-least-once?

Giả sử relay đang gửi `evt-501`:

~~~mermaid
sequenceDiagram
    participant D as Database
    participant R as Relay
    participant B as Broker
    participant C as Consumer
    R->>D: Claim evt-501
    R->>B: Publish evt-501
    B-->>R: ACK
    Note over R: CRASH trước khi mark PUBLISHED
    Note over D: Row vẫn IN_FLIGHT, lease sẽ hết hạn
    R->>D: Worker mới claim evt-501
    R->>B: Publish lại cùng eventId
    B->>C: Có thể giao trùng evt-501
~~~

Đây là **khoảng hở giữa broker ACK và việc ghi trạng thái outbox**. Không có một transaction nguyên tử bao trùm hai thao tác này, nên relay có thể gửi lại sau crash hoặc khi ACK không chắc chắn.

| Thời điểm lỗi | Trạng thái có thể xảy ra | Hậu quả cần xử lý |
| --- | --- | --- |
| Trước commit business transaction | Cả business row và outbox row rollback | Không phát sự kiện của giao dịch thất bại |
| Commit xong, relay chưa lấy | Outbox `PENDING` | Worker khác hoặc lần poll sau vẫn lấy được |
| Đã claim, chưa publish | `IN_FLIGHT` | Đợi lease hết hạn rồi claim lại |
| Broker nhận, relay không thấy ACK | Không biết broker đã nhận hay chưa | Retry có thể tạo duplicate |
| Broker ACK, DB mark `PUBLISHED` thất bại | Outbox vẫn pending/in-flight | Có thể publish lại cùng `eventId` |
| Đã mark `PUBLISHED` | Outbox ghi nhận transport ACK | Consumer vẫn có thể chưa xử lý xong |
| Consumer commit, broker ACK bị mất | Broker redeliver | Consumer inbox/idempotency phải chặn xử lý trùng |

**Kết luận vận hành:** thiết kế với giả định một sự kiện có thể được chuyển đi **nhiều lần**, nhưng tác động nghiệp vụ cần đạt kết quả đúng nhờ consumer idempotent. Không quảng bá Outbox tự cung cấp exactly-once end-to-end.

## 9. Idempotent consumer và Inbox

Consumer nhận `eventId` ổn định từ producer. Nếu consumer xử lý trong cùng database với một bảng `consumer_inbox`, có thể dùng unique constraint để chống xử lý trùng.

~~~sql
CREATE TABLE consumer_inbox (
    event_id     uuid PRIMARY KEY,
    processed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE order_projections (
    order_id      text PRIMARY KEY,
    status        text NOT NULL
);
~~~

Ví dụ consumer dùng **cùng transaction của database nhận** để ghi inbox và cập nhật read model:

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionConsumer {
    private final JdbcTemplate jdbc;

    public OrderProjectionConsumer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void onOrderCreated(UUID eventId, String orderId) {
        int inserted = jdbc.update(
                "INSERT INTO consumer_inbox(event_id) VALUES (?) " +
                "ON CONFLICT (event_id) DO NOTHING",
                eventId);
        if (inserted == 0) {
            return; // Cùng eventId đã được commit trước đó.
        }

        jdbc.update(
                "INSERT INTO order_projections(order_id, status) " +
                "VALUES (?, 'CREATED') " +
                "ON CONFLICT (order_id) DO UPDATE SET status = EXCLUDED.status",
                orderId);
    }
}
~~~

Khi handler lỗi trước commit, cả insert inbox và thay đổi projection rollback. Sau đó broker có thể redeliver để thử lại. Khi transaction commit rồi broker ACK thất bại, lần redelivery thấy event ID đã có trong inbox nên không tạo thêm tác động trong database.

**Giới hạn:** kiểu inbox này bảo vệ các thay đổi **cùng database transaction**. Nếu consumer còn gọi email hoặc REST API bên ngoài, DB rollback không thu hồi side effect đã xảy ra. Cần idempotency key phía dịch vụ nhận, outbox thứ hai hoặc workflow có đối soát tùy yêu cầu.

### Tránh lỗi ACK sớm

Với một consumer nhận từ broker, không xác nhận hoàn tất message trước khi transaction nghiệp vụ/inbox thật sự commit (trừ khi kiến trúc có bảo đảm khác). ACK trước commit rồi tiến trình chết có thể làm mất sự kiện dù broker tin rằng đã xử lý xong. Chính sách ACK/NACK/transaction là đặc thù của Kafka, RabbitMQ, JMS hoặc adapter đang dùng.

## 10. Ordering và nhiều sự kiện trên cùng aggregate

Một đơn hàng có thể phát:

~~~text
OrderCreated  -> PaymentConfirmed -> OrderShipped
~~~

Outbox ID tăng dần giúp quan sát thứ tự **insert cục bộ**, nhưng không tự bảo đảm toàn bộ thứ tự business:

- Hai transaction song song có thể tạo ID trước nhưng commit sau.
- Hai relay worker có thể claim/gửi các sự kiện ở tốc độ khác nhau.
- Broker có thể partition message theo key, nhưng ordering chỉ có thể được bảo đảm theo contract của transport và partition.
- Consumer xử lý/retry bất đồng bộ có thể hoàn thành không theo thứ tự nhận.

Nếu cần thứ tự theo đơn hàng:

1. Đặt `aggregate_id=orderId` làm routing/partition key khi broker hỗ trợ.
2. Lưu một **aggregate version** hoặc sequence nghiệp vụ trong transaction sinh sự kiện (ví dụ `orderVersion=3`).
3. Định nghĩa cách relay/consumer xử lý gap, duplicate và out-of-order.
4. Đánh giá yêu cầu triển khai tuần tự theo aggregate hoặc partition; đừng dựa chỉ vào `ORDER BY id` với nhiều worker.

Mỗi sự kiện vẫn phải có `eventId` riêng. `aggregateId` dùng để gom nhóm sự kiện của cùng đơn, **không thay thế** idempotency key của từng sự kiện.

## 11. Polling relay hay Change Data Capture (CDC)?

Hai chiến lược phổ biến:

| Tiêu chí | Polling Outbox Relay | CDC từ database log |
| --- | --- | --- |
| Cách phát hiện event mới | Worker query `PENDING` và claim | CDC connector đọc thay đổi đã commit |
| Độ trễ | Phụ thuộc chu kỳ polling và backlog | Thường thấp, phụ thuộc connector |
| Tải lên DB | Query/index/lock định kỳ | Dùng log replication, có chi phí vận hành riêng |
| Cơ chế retry | Relay quản lý attempts/next attempt | Connector/broker và offset quản lý theo thiết kế |
| Vận hành | Code và DB job đơn giản hơn khi nhỏ | Cần quản trị connector, offset, snapshot, lag |
| Tương tác Spring Integration | Dễ tích hợp flow/poller và error channel | Spring Integration có thể xử lý ở phía consumer |

Với CDC (ví dụ một công cụ đọc WAL/binlog và định tuyến sự kiện outbox), cần đảm bảo chỉ phát sự kiện của transaction **đã commit** và mapping đúng metadata như `eventId`, `aggregateId`, `eventType`. CDC cũng có thể phát lại khi connector restart hoặc offset bị replay; consumer vẫn cần idempotency.

Một số kiến trúc dùng **insert-only outbox với CDC** thay vì bảng có nhiều trạng thái relay. Đừng áp dụng máy móc SQL claim của polling cho CDC nếu connector đã có cơ chế riêng. Lựa chọn phụ thuộc lưu lượng, độ trễ, kỹ năng vận hành và hạ tầng.

## 12. Timeout, retry, error channel và dead letter

Retry cần phân loại lỗi:

| Tình huống | Chính sách gợi ý |
| --- | --- |
| Broker tạm không kết nối | Retry với backoff, giới hạn và cảnh báo |
| Gửi bị timeout, ACK không chắc chắn | Retry bằng **cùng eventId**; consumer dedupe |
| Dữ liệu sự kiện không serialize được | Quarantine/FAILED, sửa dữ liệu hoặc code |
| Topic/queue bị thiếu | Có thể là lỗi cấu hình; cảnh báo và ngừng retry ồ ạt |
| Hết số lần thử | `FAILED` + audit, dead-letter và replay có kiểm soát |
| DB đánh dấu `PUBLISHED` lỗi | Không nói broker chưa nhận; reconciliation rồi retry |

### Ranh giới lỗi trong Spring Integration

Với một `DirectChannel` và một handler gửi broker đồng bộ, exception có thể truyền về relay; relay đặt `PENDING` với `next_attempt_at` mới.

Nếu một IntegrationFlow tách sang `ExecutorChannel` hoặc queue, lỗi có thể xảy ra trên thread khác. Khi đó **error channel chỉ thông báo lỗi**, còn quyết định thay đổi row outbox phải có một **owner retry duy nhất**. Không đánh dấu `PUBLISHED` khi mới enqueue vào RAM.

Một luồng xử lý error có thể là:

~~~mermaid
flowchart LR
    R[Outbox Relay] --> I[IntegrationFlow send]
    I -->|ACK| D[Mark PUBLISHED]
    I -->|Error| E[Classify exception]
    E -->|Retryable| P[Mark PENDING + backoff]
    E -->|Permanent| F[Mark FAILED + alert]
    F --> Q[Quarantine / operator replay]
~~~

`RequestHandlerRetryAdvice` có thể hữu ích cho retry ngắn ở handler, nhưng hãy tính **tổng số lần gọi transport** nếu relay cũng có retry. Hai tầng retry 3 lần có thể gây tối đa 9 lần thử trong một số đường lỗi. Với retry lâu, để scheduler/DB quyết định lần thử tiếp theo thường dễ kiểm soát hơn so với giữ thread ngủ trong handler.

### Đừng đồng nhất DLQ với trạng thái PUBLISHED

Một sự kiện `FAILED` không nên bị coi là đã publish chỉ vì lỗi được ghi log. Đặt chính sách bảo quản row và nguồn replay; chỉ cleanup `PUBLISHED` sau khi thời gian retention đáp ứng nhu cầu audit/đối soát. Khi replay **cùng nghiệp vụ**, giữ `eventId` cũ; nếu phát sinh một sự kiện nghiệp vụ mới thật sự thì mới dùng ID mới.

## 13. Giám sát và đối soát

Một hệ thống outbox cần quan sát ít nhất:

| Metric | Ý nghĩa |
| --- | --- |
| `outboxPendingCount` | Số row sẵn sàng hoặc đang chờ retry |
| `outboxOldestPendingAge` | Độ tuổi backlog lớn nhất |
| `outboxInFlightCount` | Số row đang có owner/lease |
| `outboxExpiredLeaseCount` | Số row cần reclaim do worker có thể đã chết |
| `outboxPublishLagMs` | Thời gian từ `createdAt` đến broker ACK |
| `outboxRetries` | Số lần relay thử lại |
| `outboxFailedCount` | Số row quá hạn retry/không phát được |
| `consumerDuplicateSuppressedCount` | Số event trùng được inbox/idempotency chặn |

Ví dụ log có cấu trúc:

~~~text
flow=OrderCreatedOutboxRelay
eventId=7b39bf78-992c-4b04-8782-cfdc6178d852
aggregateId=order-501
eventType=OrderCreated
outboxId=10421
claimToken=9f09cbfa-14e5-450c-bd2a-4192b418f879
attempt=2
createdAt=2026-11-21T09:00:00Z
brokerAckAt=2026-11-21T09:00:04Z
outcome=PUBLISHED
~~~

Đây là **log do ứng dụng tự thiết kế**. Không ghi các trường nhạy cảm như token, số thẻ hoặc toàn bộ thông tin cá nhân. `claimToken` ở ví dụ là UUID quản trị relay; production cân nhắc che/giới hạn log tùy chính sách bảo mật.

### Runbook khi backlog tăng

1. Xem database/transaction còn hoạt động không; kiểm tra `PENDING` quá hạn và `IN_FLIGHT` hết lease.
2. Kiểm tra broker availability, quota, quyền topic và loại lỗi gửi.
3. So sánh tốc độ producer tạo outbox với tốc độ relay publish ACK.
4. Kiểm tra retry storm, claim contention, thời gian lease và scheduler.
5. Đối soát số event `PUBLISHED` với broker/consumer khi có yêu cầu nghiệp vụ.
6. Với row `FAILED`, xác minh side effect tại consumer trước khi replay bằng cùng `eventId`.

Không xóa outbox rows đang hoạt động chỉ để giảm backlog. Việc xóa/migration cần chính sách retention, audit và xác minh trạng thái giao dịch.

## 14. Kiểm thử Outbox qua các cửa sổ lỗi

Để chứng minh cơ chế, cần các bài test **khác nhau** cho transaction nghiệp vụ và relay.

### 14.1. Kiểm thử transaction business

**Case A — Commit thành công:** gọi `createOrder("order-501", ...)`; truy vấn thấy **một row orders** và **một row outbox** chứa event cùng nghiệp vụ.

**Case B — Outbox insert lỗi:** giả lập ràng buộc unique/serialization/DB error ở câu lệnh insert outbox; phương thức ném exception; truy vấn thấy **không có đơn hàng mới** sau rollback.

**Case C — Business insert lỗi:** dùng `orderId` trùng; xác minh không xuất hiện thêm outbox event cho transaction thất bại.

Một ví dụ test dùng `JdbcTemplate` và JUnit, giả định cấu hình tích hợp DB/test context đã sẵn sàng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

class OutboxTransactionIT {
    @Autowired OrderApplicationService orders;
    @Autowired JdbcTemplate jdbc;

    @Test
    void writesBusinessRowAndOutboxAtomically() {
        java.util.UUID eventId = orders.createOrder("order-it-501", 150_000L);

        Integer orderCount = jdbc.queryForObject(
                "SELECT count(*) FROM orders WHERE order_id = ?",
                Integer.class, "order-it-501");
        Integer outboxCount = jdbc.queryForObject(
                "SELECT count(*) FROM integration_outbox WHERE event_id = ?",
                Integer.class, eventId);

        assertEquals(1, orderCount);
        assertEquals(1, outboxCount);
    }
}
~~~

Đây là **đoạn minh họa phần test**: cần `@SpringBootTest` hoặc cấu hình test context phù hợp, schema PostgreSQL thực, làm sạch dữ liệu giữa các test. Nếu bài test bao ngoài bằng một transaction riêng, việc nhìn thấy dữ liệu trước commit chưa chứng minh durability; cần kiểm chứng từ một transaction/connection khác sau khi transaction ứng dụng đã commit.

### 14.2. Kiểm thử relay và consumer

| Kịch bản | Kỳ vọng |
| --- | --- |
| Broker ACK bình thường | Row được mark `PUBLISHED` sau ACK |
| Broker tạm lỗi | Row trở lại `PENDING` với `next_attempt_at`, tăng `attempts` |
| Broker ACK rồi relay chết trước mark | Row được reclaim sau lease, có thể phát lại cùng `eventId` |
| Hai relay claim đồng thời | Không cùng sở hữu row trong lease còn hiệu lực; xác minh bằng DB thật |
| Lease hết hạn khi worker còn chậm | Nhận diện nguy cơ duplicate; không phụ thuộc lease để có exactly-once |
| Consumer nhận cùng `eventId` hai lần | Inbox nhận diện và side effect trong DB chỉ xảy ra một lần |
| Consumer xử lý xong nhưng broker ACK consumer thất bại | Redelivery được inbox chặn |
| Có hai event cùng aggregate | Cần xác minh policy version/partition và xử lý out-of-order |
| Đưa event vào `FAILED` | Alert/quarantine và replay có kiểm soát |
| Relay restart | Row `PENDING` hoặc `IN_FLIGHT` hết lease tiếp tục được xử lý |

Testcontainers với PostgreSQL là một cách thử concurrency và `SKIP LOCKED` sát thực tế. Một unit test chỉ mock repository không chứng minh row lock/lease hoạt động dưới nhiều transaction.

## 15. Khi nào chọn Outbox và khi nào cần thiết kế khác?

Outbox phù hợp khi:

- Một business transaction trong database cần phát sự kiện sang broker/service khác.
- Không muốn phụ thuộc broker đang hoạt động để commit giao dịch cục bộ.
- Chấp nhận eventual consistency và cần khả năng retry/replay có kiểm soát.
- Consumer có thể được thiết kế idempotent và có công cụ vận hành backlog.

Outbox **không thay**:

- Transaction phân tán/XA nếu mục tiêu thực sự yêu cầu atomic commit giữa nhiều resource và chấp nhận chi phí kiến trúc tương ứng.
- Saga/workflow khi một quy trình gồm nhiều bước nghiệp vụ có **compensating actions**.
- Idempotency ở consumer và API khi request/event có thể được gửi lại.
- Scheduler nghiệp vụ hoặc Delayer khi yêu cầu là chờ đúng một thời điểm trong tương lai; outbox phục vụ **phát đáng tin cậy**, không tự quyết định thời điểm gửi.

### Kết hợp Outbox với các EIP khác

Một kiến trúc có thể là:

~~~mermaid
flowchart LR
    A[API Gateway] --> B[Business service + Outbox]
    B --> R[Outbox Relay]
    R --> K[Broker]
    K --> T[Transformer]
    T --> F{Filter / Router}
    F -->|Immediate| C[Consumer + Inbox]
    F -->|Wait| D[Delayer + Persistent Store]
    D --> C
    C --> E[Audit / Error handling]
~~~

Nếu có Delayer sau broker, cần thiết kế bền vững **cả** pending message trong Delayer, chứ không suy rằng Outbox của producer tự đảm bảo mọi message còn chờ ở một downstream JVM. Tương tự, khi consumer tạo sự kiện mới sau xử lý, có thể dùng một outbox **của consumer** trong transaction riêng.

## 16. Bài tập thực hành và câu hỏi tự kiểm tra

1. Tạo bảng `orders` và `integration_outbox` trên PostgreSQL. Cấu hình service dùng `@Transactional` ghi cả hai. Giả lập lỗi ghi outbox và kiểm tra rollback của `orders`.
2. Viết relay polling `PENDING` theo `next_attempt_at`, claim bằng `FOR UPDATE SKIP LOCKED`, gửi một bản ghi mỗi lần rồi mark `PUBLISHED` sau ACK.
3. Cho relay crash sau khi broker ACK nhưng trước update DB. Mô tả vì sao sự kiện có thể được phát lại.
4. Tạo hai relay instance cùng đọc một database; xác minh một transaction claim không lấy row đang bị transaction khác khóa.
5. Cho một relay bị treo quá thời gian lease trong lúc gửi. Phân tích điều gì xảy ra nếu worker khác reclaim row đó.
6. Tạo bảng `consumer_inbox` có unique `eventId`. Gửi cùng sự kiện hai lần và chứng minh projection chỉ được cập nhật một lần.
7. Thiết kế backoff sau broker timeout; phân biệt lỗi network không rõ đã ACK với lỗi schema chắc chắn không retryable.
8. Phát hai sự kiện cùng `aggregateId` trên hai worker. Đề xuất `aggregateVersion` và partition key để giữ thứ tự cần thiết.
9. So sánh polling relay với CDC cho lưu lượng một triệu sự kiện/ngày: độ trễ, tải database, vận hành, connector restart và replay.
10. Ghép Outbox → Broker → Router → Delayer → Consumer. Liệt kê các điểm cần persistence, retry, error channel và idempotency ở từng ranh giới.

**Câu hỏi tự kiểm tra:** Vì sao `@Transactional` bao quanh một REST call không đảm bảo atomic với database? Vì sao callback `AFTER_COMMIT` không thay thế outbox? Khi nào được đánh dấu `PUBLISHED`? Crash giữa ACK và mark gây ra điều gì? `FOR UPDATE SKIP LOCKED` giải quyết và không giải quyết rủi ro nào? Tại sao consumer inbox phải ghi cùng transaction với cập nhật nghiệp vụ? Nếu event được gửi tới broker nhiều lần, cách nào giữ side effect không bị nhân đôi?

## Tài liệu tham khảo

- [Spring Integration Reference — Transactions Support](https://docs.spring.io/spring-integration/reference/transactions.html): giao dịch trong message flow, poller và ranh giới transaction.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, error channel, lỗi đồng bộ/bất đồng bộ.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `IntegrationFlow`, endpoint và channel.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional` và phạm vi giao dịch.
- [Microservices Patterns — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): động cơ, relay, duplicate và idempotent consumer.
- [Debezium Documentation — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): lựa chọn CDC để chuyển outbox events.
