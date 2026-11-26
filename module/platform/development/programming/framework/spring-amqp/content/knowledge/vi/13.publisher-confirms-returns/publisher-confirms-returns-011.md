# Giới hạn số publish chưa được xác nhận và lưu trạng thái chờ

## 1. Bài toán: producer gửi nhanh hơn broker xác nhận

Trong một hệ thống **Spring AMQP** tích hợp RabbitMQ, producer sử dụng `RabbitTemplate` gửi message tới exchange, broker định tuyến qua binding vào queue, rồi `@RabbitListener` xử lý. Để theo dõi kết quả gửi, producer bật **publisher confirms** và **publisher returns**.

Giả sử ứng dụng phát 2.000 sự kiện mỗi giây. Producer gọi `convertAndSend(...)` rất nhanh, nhưng broker cần thời gian ghi message, đồng bộ quorum queue hoặc xử lý áp lực đĩa. Nếu mỗi lệnh publish đều tạo một `CorrelationData` và một callback mà không kiểm soát số lượng đang đợi, ứng dụng có thể tích lũy rất nhiều:

- `CorrelationData` và các future chưa hoàn thành;
- metadata như `eventId`, exchange, routing key, thời điểm gửi;
- bản sao payload để retry nếu ứng dụng giữ chúng trong RAM;
- các thao tác chờ, hàng đợi công việc và trách nhiệm đối soát khi mất kết nối.

**Giới hạn số publish chưa được xác nhận (bounded in-flight confirms)** là kỹ thuật đặt trần cho số lần gửi đang ở trạng thái **đã phát nhưng chưa có kết quả cuối cùng đủ tin cậy**. Song song với đó, **lưu trạng thái chờ** giúp ứng dụng biết phải làm gì với từng sự kiện khi nhận ACK, NACK, return, timeout hoặc sau khi tiến trình khởi động lại.

Đây là **hai trách nhiệm khác nhau**:

1. **Điều tiết tốc độ và tài nguyên:** không cấp vô hạn lượt gửi khi những lượt trước chưa được xác nhận.
2. **Bảo toàn công việc chưa hoàn tất:** trạng thái của sự kiện vẫn được truy xuất sau lỗi mạng hoặc crash; không chỉ nằm trong một `ConcurrentHashMap`.

Bài thuộc chương **Confirm và return** này hướng dẫn thiết kế đầy đủ từ cửa sổ in-flight, cấu hình Spring AMQP, bảng trạng thái, ví dụ Java, transactional outbox cho đến cách kiểm thử lỗi và quan sát production.

## 2. Publisher confirm và return xác nhận điều gì?

### 2.1. Ba kết quả dễ bị hiểu nhầm

| Tín hiệu | Ngữ nghĩa | Kết luận **không được** suy ra |
| --- | --- | --- |
| Publisher confirm **ACK** | Broker đã xử lý publish theo mức bảo đảm tương ứng của exchange và các queue đích. | `@RabbitListener` đã xử lý xong; message chắc chắn đến đúng queue nghiệp vụ chỉ từ ACK. |
| Publisher confirm **NACK** | Broker không thể xử lý publish thành công. | Consumer đã gọi `basicNack`; đây là hai giai đoạn độc lập. |
| `basic.return` (với `mandatory=true`) | Message không được định tuyến đến queue phù hợp trong điều kiện return. | Broker NACK; một message **returned** vẫn có thể có confirm **ACK**. |

Với message **mandatory** không có queue đích, RabbitMQ gửi `basic.return` **trước** publisher confirm. Spring AMQP tương quan returned message với `CorrelationData`, cho phép kiểm tra `getReturned()` khi future confirm hoàn thành trong điều kiện callback được xử lý đúng thời hạn theo tài liệu.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer / RabbitTemplate
    participant B as RabbitMQ
    participant Q as Queue
    P->>B: publish(eventId, attemptId)
    alt Định tuyến thành công
        B->>Q: Enqueue message
        B-->>P: Publisher confirm ACK
    else Không có route, mandatory=true
        B-->>P: basic.return / NO_ROUTE
        B-->>P: Publisher confirm ACK
    else Broker không hoàn thành publish
        B-->>P: Publisher confirm NACK
    else Mạng mất trước khi confirm tới producer
        Note over P,B: Outcome không xác định
    end
~~~

Publisher confirm ACK **không thay thế consumer acknowledgment**. Khi listener commit database nhưng mất ACK, RabbitMQ có thể giao lại message. Cơ chế **idempotency** ở consumer vẫn cần thiết ngay cả khi producer đã nhận confirm.

### 2.2. CorrelationData và hai loại ID

Spring AMQP cung cấp `org.springframework.amqp.rabbit.connection.CorrelationData` để liên kết **một lần thử publish** với confirm và return:

~~~java
String eventId = "evt-1001";                      // Logical event, giữ nguyên khi retry
String attemptId = java.util.UUID.randomUUID().toString(); // Mỗi lần publish một ID mới

CorrelationData correlation = new CorrelationData(attemptId);
rabbitTemplate.convertAndSend(
        "orders.events", "order.created", "ORD-1001",
        message -> {
            message.getMessageProperties().setMessageId(eventId);
            return message;
        },
        correlation
);
~~~

Phân biệt:

- **`eventId/messageId`:** nhận diện *sự kiện nghiệp vụ*. Giữ nguyên khi gửi lại cùng event.
- **`attemptId` trong `CorrelationData`:** nhận diện *một lần cố gắng gửi*. Thay đổi sau mỗi lần retry để không gán nhầm confirm muộn cho attempt mới.
- **`correlationId` trên message properties:** có thể nhận diện workflow/request; không tự động là `CorrelationData` của publisher.

Nếu một message được retry ba lần vì producer mất confirm, có thể có **ba attempt ID** nhưng chỉ **một event ID**. Đây là cơ sở để phân biệt *attempt-level monitoring* và *event-level deduplication*.

## 3. Thế nào là một publish đang “in-flight”?

Với người gửi, một publish **in-flight** là lượt gửi đã được chấp nhận vào quy trình phát nhưng **chưa hoàn tất quyết định xử lý** theo chính sách của ứng dụng.

~~~text
READY -> ACQUIRE_SLOT -> REGISTER_PENDING -> SEND
                                           |
                  +------------------------+-------------------+
                  |                        |                   |
               CONFIRM ACK              CONFIRM NACK       TIMEOUT/LOST
                  |                        |                   |
          CHECK RETURNED MESSAGE          RETRYABLE?        UNKNOWN
                  |                        |                   |
          CONFIRMED / UNROUTABLE          RETRY             RECONCILE
                  |
             RELEASE_SLOT
~~~

Một cách đếm cửa sổ gửi:

\[
\text{inFlight} = \text{attempt đã nhận slot} - \text{attempt đã kết thúc quản lý slot}
\]

Nếu giới hạn là `maxInFlight=200`, tại một thời điểm phải có **tối đa 200 attempt được nhận slot**, không phải tối đa 200 message tổng cộng trong RabbitMQ. Cơ chế giới hạn này **nằm ở producer**, khác hoàn toàn với:

| Cấu hình | Chức năng |
| --- | --- |
| `maxInFlight` của ứng dụng | Giới hạn số publish attempt producer theo dõi cùng lúc. **Tự triển khai** bằng semaphore/queue/worker pool. |
| `spring.rabbitmq.cache.channel.size` | Số channel idle được cache; có thể thành channel limit khi bật checkout timeout. **Không tự là giới hạn số event chưa confirm của ứng dụng.** |
| RabbitMQ `channel_max` | Số AMQP channel tối đa có thể mở trên một connection theo thương lượng. |
| `spring.rabbitmq.listener.simple.prefetch` | Số delivery chưa ACK bên **consumer** theo cơ chế QoS; không giới hạn publisher confirms. |
| `RabbitTemplate.replyTimeout` | Timeout request/reply RPC; **không phải** deadline của publisher confirm cho từng event. |
| `CorrelationData.getFuture()` | Future cho kết quả một attempt; **không tự tạo một bounded window**. |

**Lưu ý phạm vi:** trong Spring AMQP, các thao tác `RabbitTemplate` thường dùng channel từ `CachingConnectionFactory`; việc channel được giữ hoặc cache trong lúc đợi confirm là chi tiết khác với **trần số công việc producer cho phép song song**. Không sử dụng con số channel để thay thế đồng hồ đo `inFlight`.

## 4. Vì sao phải giới hạn số attempt chưa được xác nhận?

### 4.1. Nếu không có giới hạn

~~~text
Publisher                  RabbitMQ
  send 1  -------------------->
  send 2  -------------------->
  send 3  -------------------->   Broker xử lý chậm
  ...                                 |
  send 100_000  ---------------->      |

Producer giữ rất nhiều future/pending entries
-> heap pressure -> GC -> timeout -> reconnect -> retry hàng loạt
~~~

Việc bất đồng bộ hóa callback **không tự tạo backpressure**. Một producer có thể tiếp tục phát message và giữ thêm state trong RAM nhanh hơn tốc độ xác nhận; lỗi có thể xuất hiện rất lâu sau khi từng lời gọi `convertAndSend` đã trả về.

### 4.2. Cửa sổ in-flight có giới hạn

~~~mermaid
flowchart LR
    SRC["Outbox / event stream"]
    SLOT{"Còn slot trong<br/>cửa sổ in-flight?"}
    SEND["RabbitTemplate<br/>publish"]
    WAIT["Pending map<br/>attemptId → metadata"]
    RESULT["Confirm / Return<br/>hoặc deadline"]
    NEXT["Release / reconcile"]
    PAUSE["Đợi/backpressure<br/>không tạo thêm attempt"]
    SRC --> SLOT
    SLOT -- Có --> SEND --> WAIT --> RESULT --> NEXT --> SLOT
    SLOT -- Không --> PAUSE --> SLOT
~~~

Khi đạt trần, producer phải **giảm hoặc dừng nhận công việc mới**, thay vì tạo thêm future rồi cho chúng chờ trong một queue RAM vô hạn. Một số chiến lược:

- **Backpressure từ nguồn:** worker chỉ đọc thêm outbox records khi còn slot.
- **Fail fast:** API hoặc tác vụ nền nhận trạng thái `BUSY` để thử lại sau, không chứa payload trong RAM.
- **Bounded queue:** đặt cả trần số item chờ lấy slot, policy khi đầy và metrics.
- **Circuit breaker:** tạm ngừng publish mới khi confirm bị treo hàng loạt, broker bị chặn hoặc connection không ổn định.

**Không dùng callback confirm để chờ semaphore** hoặc thực hiện I/O database lâu. Callback phải nhẹ và nhanh; việc cập nhật DB, retry và điều tra nên giao cho worker/executor có giới hạn.

### 4.3. Chọn mức trần ban đầu

Một ước lượng theo *Little's Law*:

\[
\text{inFlight trung bình} \approx
\text{tốc độ publish/giây} \times
\text{thời gian chờ confirm trung bình (giây)}
\]

Ví dụ producer muốn phát khoảng **400 message/giây**, độ trễ confirm bình quân **0,2 giây** thì đã cần khoảng **80 attempt** cùng chờ ở trạng thái ổn định. Có thể thử một mức trần có headroom, chẳng hạn **160–320**, rồi đo thực tế; đây **không phải con số được RabbitMQ bảo đảm** cho mọi workload.

Không chọn giới hạn chỉ từ throughput trung bình. Cần đo thêm:

- `p95/p99` confirm latency, đặc biệt khi queue ghi đĩa hoặc quorum replication chậm;
- kích thước payload và lượng state giữ trên mỗi attempt;
- số application instances, số connection và tổng tải của broker;
- thời gian hồi phục khi broker tạm dừng xác nhận;
- chính sách chờ, retry và sức chứa outbox khi broker không sẵn sàng.

Nếu một attempt giữ payload lớn trong RAM, 1.000 pending entries có thể rất tốn bộ nhớ. Nếu chỉ giữ `eventId/attemptId` và tham chiếu tới bản ghi outbox, mức tiêu thụ sẽ khác nhiều. **Dùng queue bền vững làm nguồn**, không sao chép toàn bộ payload vào nhiều future chỉ để tiện retry.

## 5. Lưu trạng thái chờ: map RAM và outbox bền vững khác nhau

### 5.1. Hai lớp trạng thái

| Lớp | Ví dụ | Mất khi process crash? | Mục đích |
| --- | --- | --- | --- |
| **In-memory pending** | `ConcurrentHashMap<attemptId, Pending>`, `Semaphore`, future | **Có** | Tương quan callback, giữ cửa sổ gửi, đo latency trong vòng đời hiện tại. |
| **Durable pending/outbox** | Bảng `outbox_events` và `publish_attempts` | **Không**, nếu database và transaction bền vững | Khôi phục event chưa có kết luận khi ứng dụng khởi động lại. |

Chỉ dùng `ConcurrentHashMap` để “lưu message chờ” **không đảm bảo không mất sự kiện** khi JVM bị kill hoặc container bị thay thế. Với message nghiệp vụ quan trọng, phải lưu event vào một hệ thống bền vững **trước** khi coi việc phát là trách nhiệm đã được nhận.

### 5.2. Đề xuất trạng thái của logical event

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| `PENDING` | Event đã nằm trong outbox, chưa được worker lấy phát. | Chờ slot và lấy việc. |
| `CLAIMED` | Worker đã nhận quyền xử lý record, có lease/owner. | Ghi nhận attempt và publish. |
| `WAITING_CONFIRM` | Đã bắt đầu gửi, đang chờ ACK/NACK/return. | Theo dõi callback và deadline. |
| `CONFIRMED` | Broker confirm ACK, không quan sát thấy return theo contract. | Đánh dấu giai đoạn publish hoàn thành. |
| `UNROUTABLE` | Broker return message vì không định tuyến được. | Kiểm tra exchange, routing key, queue, binding, vhost. |
| `NACKED` | Broker NACK hoặc client có kết quả tiêu cực được phân loại. | Điều tra nguyên nhân, retry khi hợp lý. |
| `UNKNOWN` | Mất confirm, mất connection, quá deadline hoặc worker crash khi đang gửi. | Đối soát và retry cùng event ID, chấp nhận khả năng trùng. |
| `FAILED_PERMANENT` | Lỗi không thể tự khắc phục hoặc vượt số lần thử theo policy. | Alert/quarantine/manual repair; **không xóa event im lặng**. |

`UNROUTABLE` không mặc nhiên là `NACKED`: một return thường đi kèm publisher **ACK**. `UNKNOWN` cũng không được tự đổi thành `NACKED`; nó có nghĩa **không biết chắc**.

### 5.3. Mô hình dữ liệu gợi ý

~~~sql
-- Ví dụ logic cho PostgreSQL; có thể điều chỉnh theo hệ CSDL thực tế.
CREATE TABLE outbox_events (
    event_id          VARCHAR(100) PRIMARY KEY,
    aggregate_id      VARCHAR(100) NOT NULL,
    event_type        VARCHAR(100) NOT NULL,
    exchange_name     VARCHAR(200) NOT NULL,
    routing_key       VARCHAR(200) NOT NULL,
    payload_json      TEXT NOT NULL,
    state             VARCHAR(40) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    current_attempt   VARCHAR(100),
    lease_until       TIMESTAMPTZ,
    next_retry_at     TIMESTAMPTZ,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL,
    confirmed_at      TIMESTAMPTZ
);

CREATE INDEX idx_outbox_ready
    ON outbox_events (state, next_retry_at, created_at);

CREATE TABLE publish_attempts (
    attempt_id        VARCHAR(100) PRIMARY KEY,
    event_id          VARCHAR(100) NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    completed_at      TIMESTAMPTZ,
    outcome           VARCHAR(40),
    return_code       INTEGER,
    return_text       TEXT,
    confirm_reason    TEXT
);
~~~

Đây là **schema tham khảo**, chưa phải hệ thống migration hoàn chỉnh. Trong môi trường có nhiều publisher worker, cần transaction/row locking, lease, index và cách chuyển state **atomic**. Có thể dùng PostgreSQL `FOR UPDATE SKIP LOCKED` hoặc cơ chế tương đương để nhiều worker không cùng claim một event.

**Bất biến quan trọng:** `event_id` ổn định qua các retry, còn `attempt_id` duy nhất cho **mỗi lượt gửi**. Khi callback muộn đến, nó chỉ được cập nhật attempt tương ứng, không tự ghi đè trạng thái của một attempt mới đang xử lý event đó.

### 5.4. Tại sao cần ghi cả attempt?

Ví dụ:

~~~text
Event evt-1001

Attempt A1: gửi lúc 10:00:00; timeout -> UNKNOWN
Attempt A2: retry lúc 10:00:10; broker ACK -> CONFIRMED
Attempt A1: confirm muộn đến lúc 10:00:12
~~~

Nếu chỉ lưu `Map<eventId, Future>` và thay future khi retry, kết quả muộn của **A1** có thể bị gán nhầm cho **A2**. Với `attemptId` riêng và cập nhật có điều kiện theo version/lease, hệ thống lưu được lịch sử đúng mà không làm rối state hiện tại.

## 6. Cấu hình Spring AMQP: confirm và return có tương quan

### 6.1. Dependency và application.yml

Ví dụ dùng **Spring Boot 3.x / Spring AMQP 3.x**, RabbitMQ AMQP 0-9-1:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    cache:
      channel:
        size: 30
~~~

Ba thuộc tính đầu tiên cho cơ chế theo dõi:

1. `publisher-confirm-type: correlated`: cho phép liên kết ACK/NACK với `CorrelationData`.
2. `publisher-returns: true`: cho phép xử lý returned messages.
3. `template.mandatory: true`: yêu cầu broker return message không định tuyến được trong điều kiện tương ứng.

`cache.channel.size=30` là cỡ cache channel dùng để tái sử dụng; **không phải `maxInFlight`**. Giá trị 30 chỉ minh họa. Trong ứng dụng thật, kiểm tra channel churn, publisher connection, listener concurrency và số connection trước khi điều chỉnh.

Tài khoản `guest` chỉ dành cho RabbitMQ demo cục bộ, thường bị giới hạn kết nối loopback. Production cần user/vhost/permissions riêng và bảo vệ secrets.

### 6.2. Khai báo exchange, queue, binding đúng trước khi gửi

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "order.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding ordersBinding(Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with(ROUTING_KEY);
    }
}
~~~

Spring `RabbitAdmin` có thể khai báo topology từ bean nếu được cấu hình phù hợp. Nếu producer gửi vào exchange chưa tồn tại, broker có thể đóng channel vì `NOT_FOUND` thay vì trả message kiểu `NO_ROUTE`. Việc có confirm ACK và không có return cũng **không thay thế** kiểm tra topology đã được khai báo đúng.

## 7. Ví dụ publisher có cửa sổ in-flight giới hạn

Để minh họa giới hạn, ví dụ sau dùng:

- `Semaphore` để cấp tối đa **100 slot** trên **một instance publisher**.
- `ConcurrentHashMap` để theo dõi **attempt còn chờ** và đối chiếu callback.
- `CorrelationData.getFuture()` để nhận publisher confirm ACK/NACK.
- `CorrelationData.getReturned()` để phát hiện return đi kèm ACK.
- Deadline và **fail-closed**: nếu confirm bị mất/quá hạn, tạm ngừng gửi mới để tránh tiếp tục bơm vô hạn khi trạng thái broker không chắc chắn.

**Đây là mẫu điều tiết trong một JVM, không phải durable outbox.** Khi ứng dụng crash, những entry RAM biến mất; production phải lưu event/state ở database theo mục 5 và 8.

### 7.1. Service Java

~~~java
import jakarta.annotation.PreDestroy;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class BoundedConfirmPublisher {

    public enum State {
        CONFIRMED, UNROUTABLE, NACKED, UNKNOWN, REJECTED
    }

    public record Outcome(
            String eventId, String attemptId, State state, String detail) {}

    private static final int MAX_IN_FLIGHT = 100;
    private static final Duration CONFIRM_DEADLINE = Duration.ofSeconds(15);

    private final RabbitTemplate template;
    private final Semaphore slots = new Semaphore(MAX_IN_FLIGHT);
    private final Map<String, Pending> pending = new ConcurrentHashMap<>();
    private final AtomicBoolean accepting = new AtomicBoolean(true);
    private final ScheduledExecutorService deadlines =
            Executors.newSingleThreadScheduledExecutor();

    static final class Pending {
        final String eventId;
        final CompletableFuture<Outcome> outcome = new CompletableFuture<>();
        final AtomicBoolean completed = new AtomicBoolean();
        volatile ScheduledFuture<?> timer;

        Pending(String eventId) {
            this.eventId = eventId;
        }
    }

    public BoundedConfirmPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public CompletableFuture<Outcome> publish(String eventId, String body) {
        // Fail fast: không tạo một queue RAM không giới hạn khi hết slot.
        if (!accepting.get() || !slots.tryAcquire()) {
            return CompletableFuture.completedFuture(
                    new Outcome(eventId, null, State.REJECTED, "Publisher busy/paused"));
        }
        if (!accepting.get()) {
            slots.release();
            return CompletableFuture.completedFuture(
                    new Outcome(eventId, null, State.REJECTED, "Publisher paused"));
        }

        String attemptId = UUID.randomUUID().toString();
        Pending entry = new Pending(eventId);
        CorrelationData correlation = new CorrelationData(attemptId);
        pending.put(attemptId, entry);

        entry.timer = deadlines.schedule(() -> {
            // Timeout KHÔNG có nghĩa broker đã NACK hay chưa nhận message.
            accepting.set(false); // dừng cấp attempt mới đến khi đối soát/reset
            finish(attemptId, entry, State.UNKNOWN, "Confirm deadline exceeded");
        }, CONFIRM_DEADLINE.toMillis(), TimeUnit.MILLISECONDS);

        correlation.getFuture().whenComplete((confirm, error) -> {
            if (error != null || confirm == null) {
                accepting.set(false);
                finish(attemptId, entry, State.UNKNOWN, "Confirm unavailable");
            } else if (!confirm.isAck()) {
                finish(attemptId, entry, State.NACKED, confirm.getReason());
            } else if (correlation.getReturned() != null) {
                finish(
                        attemptId, entry, State.UNROUTABLE,
                        correlation.getReturned().getReplyText()
                );
            } else {
                finish(attemptId, entry, State.CONFIRMED, "ACK, no return");
            }
        });

        try {
            template.convertAndSend(
                    OrderTopology.EXCHANGE,
                    OrderTopology.ROUTING_KEY,
                    body,
                    message -> {
                        message.getMessageProperties().setMessageId(eventId);
                        return message;
                    },
                    correlation
            );
        } catch (AmqpException sendError) {
            // Có thể broker đã nhận bytes trước khi lỗi được phát hiện.
            accepting.set(false);
            finish(attemptId, entry, State.UNKNOWN, sendError.toString());
        }

        return entry.outcome;
    }

    private void finish(
            String attemptId, Pending entry, State state, String detail) {
        if (!entry.completed.compareAndSet(false, true)) {
            // Có thể có confirm muộn sau timeout: cần gửi vào audit/reconciler.
            return;
        }
        if (entry.timer != null) {
            entry.timer.cancel(false);
        }
        pending.remove(attemptId, entry);
        slots.release();
        entry.outcome.complete(new Outcome(entry.eventId, attemptId, state, detail));
    }

    public int inFlight() {
        return pending.size();
    }

    public boolean isAccepting() {
        return accepting.get();
    }

    @PreDestroy
    void shutdown() {
        accepting.set(false);
        deadlines.shutdownNow();
    }
}
~~~

**Đọc kỹ phạm vi của ví dụ:**

1. `MAX_IN_FLIGHT=100` là giới hạn **per application instance**, không phải giới hạn toàn cluster publisher. Nếu có 10 instances, tổng window có thể lớn hơn 100.
2. `tryAcquire()` từ chối ngay khi hết slot. Worker đọc outbox nên đợi/giảm tốc ở **nguồn**, không loop liên tục gọi lại method khi nhận `REJECTED`.
3. Future callback trả kết quả vào `entry.outcome`; **không thực hiện DB transaction blocking bên trong callback**. Consumer của outcome nên giao cập nhật state bền vững cho một worker/executor thích hợp.
4. Khi deadline trôi qua, code chuyển sang **`UNKNOWN` và dừng nhận publish mới**. Nó giải phóng slot RAM nhưng **không giả định broker đã hủy attempt trên wire**. Muốn tiếp tục gửi sau UNKNOWN phải có quy trình đối soát/fence hoặc khởi tạo connection/publisher an toàn; không đơn giản bật lại `accepting=true`.
5. Khi callback confirm đến **muộn** sau timeout, ví dụ bỏ qua kết quả ở RAM. Production phải **audit kết quả muộn theo attempt ID**, và cập nhật outbox bằng compare-and-set/versioning để không ghi đè state của lần retry khác.
6. Nếu ứng dụng dừng đột ngột, các `Pending` mất hết. Đó là lý do cần durable outbox; code trên là **minh họa bounded pending**, không phải đầy đủ giải pháp phát sự kiện không mất.
7. Ví dụ sử dụng một scheduled thread chỉ để mô tả deadline. Production nên dùng scheduler/executor do ứng dụng quản lý, có giám sát và shutdown chuẩn; callback không nên giữ hoặc chặn thread quan trọng của RabbitMQ.

### 7.2. Vì sao không chỉ dùng `Semaphore` rồi chờ từng ACK?

Code kiểu sau đơn giản nhưng **tuần tự hóa toàn bộ việc gửi**:

~~~java
// Dễ hiểu nhưng kém throughput nếu dùng trong một loop tuần tự:
CorrelationData data = new CorrelationData(attemptId);
rabbitTemplate.convertAndSend("orders.events", "order.created", body, data);
var confirm = data.getFuture().get(15, TimeUnit.SECONDS);
~~~

Với một thread chỉ gửi event kế tiếp sau khi đợi ACK của event trước, tại thời điểm bất kỳ chỉ có một publish chờ xác nhận. Có thể dùng cho tác vụ rất ít message, nhưng thường không phù hợp khi throughput cao hoặc confirm latency lớn.

**Cửa sổ in-flight** cho phép phát nhiều message **đồng thời** rồi nhận xác nhận bất đồng bộ. Ngược lại, **không giới hạn cửa sổ** có thể tăng throughput ngắn hạn nhưng dẫn đến pending state quá lớn khi broker chậm.

RabbitMQ cũng hỗ trợ chiến lược **batch publish và chờ batch confirms**. Cách đó đơn giản hơn nhưng có thể phải gửi lại cả batch khi một phần kết quả chưa rõ; với event nghiệp vụ quan trọng, giữ attempt-level ID và trạng thái từng event giúp đối soát chính xác hơn.

## 8. Luồng production: transactional outbox + bounded worker

### 8.1. Quy trình bền vững đề xuất

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Business service
    participant DB as DB: orders + outbox
    participant W as Bounded publisher worker
    participant MQ as RabbitMQ
    participant C as Idempotent @RabbitListener
    A->>DB: Transaction: order + eventId PENDING
    W->>DB: Claim tối đa số slot còn trống
    DB-->>W: Event + attemptId + lease
    W->>MQ: publish messageId=eventId
    alt ACK không return
        MQ-->>W: confirm ACK
        W->>DB: attempt ACK, event CONFIRMED
    else basic.return
        MQ-->>W: return + confirm
        W->>DB: UNROUTABLE, cần sửa topology
    else NACK
        MQ-->>W: confirm NACK
        W->>DB: NACKED, chọn retry
    else Mất confirm hoặc worker crash
        Note over W,DB: Lease quá hạn, trạng thái UNKNOWN
        W->>DB: Recovery/đối soát, lên lịch retry
    end
    MQ->>C: Delivery
    C->>C: processed_event(eventId) chống trùng
    C-->>MQ: Consumer ACK sau commit
~~~

Đây là quy trình **at-least-once có kiểm soát**, không phải exactly-once delivery. Event được persist trước khi phát; retry có thể tạo thêm bản sao; consumer dùng `eventId` và transaction DB để không lặp side effect nghiệp vụ.

### 8.2. Claim theo cửa sổ còn trống

Ví dụ giả mã cho worker:

~~~text
LOOP:
  if publisher is PAUSED:
      alert / reconcile / wait for recovery
      continue

  available = maxInFlight - inFlight
  if available <= 0:
      wait for confirm or bounded timer
      continue

  claim at most available outbox events
      WHERE status IN (PENDING, RETRYABLE)
      AND next_retry_at <= now
      USING database row locking/lease

  FOR each claimed event:
      create unique attemptId
      persist attempt + lease / WAITING_CONFIRM
      register confirm callback
      publish with eventId in messageId

  ON ACK + no RETURN:
      atomically mark matching attempt CONFIRMED
  ON RETURN:
      mark matching attempt UNROUTABLE; stop hot retry
  ON NACK:
      record NACK and schedule policy-driven retry
  ON CONFIRM TIMEOUT:
      mark UNKNOWN; pause/fence session; reconcile before resuming
~~~

Với nhiều worker chạy đồng thời, một event phải được claim bằng lease/transaction và cập nhật có điều kiện, ví dụ `WHERE event_id=? AND current_attempt=?`. Nếu callback của attempt cũ đến muộn, không được ghi đè kết quả attempt mới.

### 8.3. Khi nào xóa record khỏi outbox?

Không nên xóa event **ngay sau lời gọi `convertAndSend`**. Cần có chính sách retention:

- Event `CONFIRMED` có thể được archive/xóa sau thời gian đối soát theo yêu cầu nghiệp vụ.
- Event `UNKNOWN` vẫn cần được giữ, dù worker đã timeout hoặc container restart.
- Event `UNROUTABLE/NACKED` cần thông tin nguyên nhân và route để sửa lỗi.
- Event quá số lần retry không nên bị silently dropped; chuyển `FAILED_PERMANENT` và alert.

Nếu producer gửi vào nhiều queue hoặc alternate exchange, việc đánh dấu `CONFIRMED` phải được định nghĩa theo contract: ACK + không return không tự nói rằng *mỗi* consumer đích đã xử lý.

## 9. Timeout và sự khác biệt giữa “quá hạn” với “thất bại”

### 9.1. Confirm không có SLA cố định do broker cam kết

RabbitMQ gửi confirms bất đồng bộ; thời gian ACK phụ thuộc queue type, ghi đĩa, quorum replication, tải hệ thống, network và broker resource alarms. Với persistent message trên durable queue, việc ghi đĩa có thể tạo độ trễ; với quorum queue, broker cần đa số replica xác nhận theo ngữ nghĩa quorum.

`confirmDeadline=15s` trong ví dụ là **deadline của ứng dụng**, không phải lời hứa từ RabbitMQ rằng sau 15 giây broker đã bỏ publish. Khi quá hạn:

1. Ghi `UNKNOWN`, không mặc định `NACKED` hay `NOT_SENT`.
2. Giới hạn hoặc dừng việc phát thêm để tránh chất đống attempt.
3. Kiểm tra connection/channel shutdown, broker logs, publisher latency và outstanding events.
4. Khi khôi phục, retry với **cùng event ID** sau khi thiết lập chính sách chống trùng.

### 9.2. Vì sao giải phóng slot trên timeout cần thận trọng?

Giải phóng semaphore slot chỉ làm giảm số **attempt được theo dõi trong tiến trình**. Nó **không hủy publish đã được gửi** hoặc rút message khỏi RabbitMQ.

Nếu cứ “timeout → giải phóng slot → gửi ngay message khác” khi broker không có confirm, số publish thực tế chưa được xử lý có thể tăng không giới hạn **dù `pending.size() <= maxInFlight`**. Do đó muốn có **giới hạn thực sự về hoạt động đang diễn ra**, cần:

- dừng cấp thêm attempt khi hàng loạt confirm timeout;
- thiết lập lại/fence producer session hoặc connection theo quy trình;
- lưu durable pending và đối soát các attempt UNKNOWN;
- chỉ resume khi đã xác nhận cơ chế recovery và giới hạn tổng tải.

Ví dụ Java ở mục 7 dùng `accepting=false` khi xảy ra UNKNOWN nhằm minh họa **fail-closed**. Một hệ thống production có thể chọn circuit breaker theo tỷ lệ lỗi và thời gian, nhưng không nên tiếp tục phát vô hạn trong lúc mất khả năng xác nhận.

### 9.3. Confirm đến muộn sau retry

Nếu attempt A1 timeout, A2 được gửi lại cùng event và được ACK, rồi A1 cũng ACK:

- Không được tự xem hai lần ACK là hai sự kiện khác nhau.
- Cập nhật bảng attempt theo **A1, A2**, còn bảng event chỉ phản ánh logical event `evt-1001`.
- Consumer vẫn cần kiểm tra `eventId` để tránh side effect trùng.
- Các late confirms nên được ghi audit để điều chỉnh chính sách timeout và phân tích broker latency.

## 10. ReturnsCallback, CorrelationData và vấn đề đồng thời

`RabbitTemplate` có thể dùng:

~~~java
template.setReturnsCallback(returned -> {
    System.err.printf(
            "RETURN exchange=%s key=%s code=%d text=%s%n",
            returned.getExchange(),
            returned.getRoutingKey(),
            returned.getReplyCode(),
            returned.getReplyText());
});

template.setConfirmCallback((correlation, ack, cause) -> {
    System.out.printf(
            "CONFIRM attempt=%s ack=%s cause=%s%n",
            correlation == null ? null : correlation.getId(),
            ack,
            cause);
});
~~~

Các dòng trên minh họa **trong một method có biến `RabbitTemplate template`**, không phải một class độc lập. Chỉ có **một callback loại này trên mỗi `RabbitTemplate`**; đừng để các service khác nhau tùy tiện ghi đè nhau.

Khi cần quản lý từng attempt, dùng `CorrelationData.getFuture()` là cách đơn giản để ghép result. Nếu cả confirms và returns được bật đúng, Spring AMQP đảm bảo returned message được gắn vào `CorrelationData` trước khi future hoàn thành ACK trong điều kiện return callback không chặn quá thời gian đảm bảo của framework.

**Không để callback chặn lâu.** Khi cần gọi database, gửi lại message hoặc chạy logic nặng, đặt một sự kiện trạng thái vào **bounded executor/queue** được giám sát, hoặc để outbox worker thực hiện. Ngay cả khi Spring AMQP hiện đại chạy callback trên executor thay vì raw connection I/O thread, công việc quá lâu vẫn có thể gây backlog, chậm xác nhận và khó hồi phục.

### 10.1. Nếu future hoàn thành nhưng không có return

Điều kiện `confirm ACK && returned == null` nói rằng producer **không quan sát thấy basic.return** theo cơ chế cấu hình. Nó không có nghĩa consumer đã xử lý xong.

Nếu ứng dụng không bật `mandatory` hoặc không xử lý publisher returns, việc không thấy return không có nhiều giá trị để khẳng định message được định tuyến. Vì vậy cần bảo đảm **cả ba**: correlated confirms, publisher returns, mandatory flag và topology đúng.

### 10.2. Nếu broker đóng channel vì exchange không tồn tại

Publish đến exchange không tồn tại có thể khiến broker đóng channel với `404 NOT_FOUND`. Đây **không phải** một basic.return `NO_ROUTE` thông thường. Spring có thể hoàn thành confirm với NACK có reason khi framework phát hiện shutdown, hoặc callback/log thể hiện channel failure. Nếu kết quả đến không đầy đủ, phân loại `UNKNOWN` thay vì đoán.

## 11. Quan sát production và chọn chỉ số

| Metric | Cách hiểu | Tín hiệu cần báo động |
| --- | --- | --- |
| `publisher_inflight_attempts` | Số attempt hiện đang giữ slot trong instance. | Duy trì gần max lâu, không giảm sau khi broker phục hồi. |
| `publisher_window_utilization` | `inFlight/maxInFlight`. | Luôn cao kèm confirm latency tăng. |
| `publisher_confirm_latency_seconds` (p50/p95/p99) | Thời gian từ publish attempt tới confirm. | p99 tăng đột biến so với baseline. |
| `publisher_confirm_ack_total` | Số ACK từ broker. | Giảm mạnh so với publish attempts. |
| `publisher_confirm_nack_total` | Số NACK. | Bất kỳ sự gia tăng bất thường nào. |
| `publisher_return_total` | Số basic.return / unroutable. | Tăng theo route/key/vhost mới triển khai. |
| `publisher_unknown_total` | Số attempt không có kết quả chắc chắn trước deadline. | Tăng đột biến hoặc kéo dài. |
| `publisher_backpressure_rejected_total` | Số lượt bị từ chối vì hết slot. | Nguồn cần giảm tốc / outbox backlog tăng. |
| `outbox_oldest_pending_age_seconds` | Tuổi bản ghi chờ lâu nhất. | Vượt SLA xử lý event. |
| `outbox_pending_count` | Số event chưa phát xong bền vững. | Tăng liên tục, báo hiệu producer chậm hơn nguồn sinh event. |
| `publisher_connection_errors_total` | Lỗi connection/channel. | Correlate với broker restart, network, disk/memory alarms. |

Nên bổ sung tracing/log với `eventId`, `attemptId`, exchange, routing key, vhost, queue, confirm result và trạng thái outbox. **Không log toàn bộ payload nhạy cảm** chỉ để tiện tìm lỗi.

### 11.1. Bộ câu hỏi chẩn đoán

1. `inFlight` tăng vì tốc độ publish lớn, hay vì confirm latency kéo dài?
2. `publisher_confirm_ack_total` vẫn tăng nhưng `publisher_return_total` cũng tăng? Nếu vậy, có thể là **unroutable**, không phải thiếu confirm.
3. `inFlight` giảm sau timeout nhưng `outbox_pending_count` vẫn tăng? Đây có thể là producer bị tạm dừng để đối soát, đúng với chính sách fail-closed.
4. Broker có channel bị mở/đóng liên tục, blocked connection hoặc disk alarm không?
5. Producer chạy nhiều instance: tổng in-flight và tổng backlog có vượt ngân sách của RabbitMQ không?
6. Message đã CONFIRMED nhưng consumer không xử lý: queue ready/unacknowledged, listener concurrency, ack mode, retry và DLQ có vấn đề gì?

**Không dùng tỷ lệ ACK của publisher để đo trực tiếp tỷ lệ thành công nghiệp vụ.** Một event có thể được broker chấp nhận nhưng listener thất bại, retry rồi vào DLQ. Hai giai đoạn cần dashboard riêng nhưng có chung event ID để đối chiếu.

## 12. Bài thực hành

Thử trên RabbitMQ cục bộ có Management UI và Spring Boot với topology ở mục 6. Không thử phá kết nối hoặc làm tràn pending trên môi trường production.

| Bước | Hành động | Kết quả quan sát |
| --- | --- | --- |
| 1 | Bật correlated publisher confirms, returns và mandatory. | Có thể nhận ACK/NACK/return theo từng `CorrelationData`. |
| 2 | Dùng `BoundedConfirmPublisher` với `MAX_IN_FLIGHT=100`, gửi một số event có ID riêng. | `inFlight` tăng khi nhận slot, giảm khi attempt kết thúc. |
| 3 | Thay limit thành `2` trong môi trường thử nghiệm, phát ít nhất ba request gần nhau khi hai attempt đầu còn chờ. | Request không có slot được trả `REJECTED`, không tự chen thêm future vào bộ nhớ. |
| 4 | Gửi routing key không có binding tới exchange hợp lệ, với `mandatory=true`. | Returned message có reply code/reason; confirm có thể vẫn ACK, kết quả cuối là `UNROUTABLE`. |
| 5 | Gửi vào exchange không tồn tại (chỉ trong test). | Channel có thể đóng `NOT_FOUND`; xử lý theo NACK hoặc UNKNOWN tùy tín hiệu thực nhận. |
| 6 | Dừng RabbitMQ giữa đợt publish. | Có thể có attempt `UNKNOWN`/timeout; producer fail-closed và không tiếp tục phát vô hạn. |
| 7 | Khởi động lại broker và ứng dụng. | Pending map RAM đã mất; những record `PENDING/UNKNOWN` trong outbox còn để recovery. |
| 8 | Retry một logical event bằng **cùng eventId** nhưng attemptId mới. | Lịch sử attempt phân biệt được; consumer idempotent không làm side effect trùng. |
| 9 | Tạm dừng consumer, giữ queue tồn tại, rồi publish. | Publisher vẫn có thể nhận confirm ACK; queue có thể chứa message ready, chưa có consumer ACK. |
| 10 | Thử payload/schema lỗi phía consumer và cấu hình DLQ. | Đây là lỗi tiêu thụ **sau publish**, không biến publisher ACK thành NACK. |

### Phiếu ghi kết quả

~~~text
RabbitMQ / Spring AMQP version:
maxInFlight per instance:
number of publisher instances:
payload size:
publish attempt rate:
confirm latency p50/p95/p99:
inFlight peak:
pending outbox count / oldest age:
ACK / NACK / return / UNKNOWN count:
connection/channel errors:
publisher paused / resumed:
same eventId across retries?:
late confirm detected?:
consumer redelivery / idempotency result:
~~~

Một bài test đúng nên tạo **tải đủ dài** để thấy cửa sổ in-flight, chứ không chỉ gửi từng message rồi đợi confirm đồng bộ. Đồng thời phải đo **tuổi backlog trong outbox**: việc producer luôn giữ đúng trần 100 không có nghĩa event được giao đúng hạn nếu tốc độ sinh sự kiện cao hơn tốc độ broker xác nhận.

## 13. Những sai lầm thường gặp

**“`CorrelationData` tự giới hạn số message chưa confirm.”** Không. Nó liên kết kết quả với attempt; giới hạn window cần được ứng dụng thiết kế, chẳng hạn semaphore cộng backpressure.

**“`channelCacheSize=100` nghĩa là producer chỉ giữ được 100 publish in-flight.”** Không. Kích thước cache channel và số logical event chờ confirm là hai khái niệm khác nhau.

**“Khi future timeout, message chắc chắn thất bại và có thể tạo event ID mới.”** Không. Outcome là `UNKNOWN`; message có thể đã được broker chấp nhận. Retry cùng logical event ID.

**“Xóa record pending ngay sau `convertAndSend` để tránh tốn DB.”** Sai với event quan trọng. Phải đợi đủ tín hiệu để kết luận giai đoạn publish hoặc lưu trạng thái cần đối soát.

**“ACK nghĩa là được định tuyến và consumer đã xử lý.”** Sai. ACK publisher có thể đi cùng basic.return, và consumer ACK là tín hiệu riêng.

**“Gắn `messageId` vào payload thì broker tự deduplicate.”** Sai. RabbitMQ AMQP 0-9-1 không mặc nhiên bỏ thông điệp trùng ID; consumer cần idempotency.

**“Dùng `ConcurrentHashMap` là lưu được trạng thái chờ sau crash.”** Sai. Map chỉ nằm trong heap; cần outbox/database bền vững nếu nghiệp vụ không được mất event.

**“Khi deadline hết, giải phóng slot và gửi tiếp vô hạn vẫn giữ được giới hạn.”** Sai. Chỉ giới hạn số **entry RAM** còn thấy; broker có thể còn xử lý những attempt đã timeout. Cần fail-closed/fence và reconcile.

**“Retry ngay trong callback NACK sẽ tốt hơn.”** Không hẳn. Callback có thể chạy trên executor của connection factory; blocking I/O hoặc retry không giới hạn sẽ gây nghẽn xử lý confirms. Đưa retry vào worker có backoff và giới hạn.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao producer cần giới hạn số attempt chưa confirm, dù `convertAndSend` thường trả về nhanh?

**Trả lời:** Vì confirms bất đồng bộ. Nếu broker chậm, mỗi attempt chưa kết thúc giữ future/state; không giới hạn sẽ tạo áp lực heap, callback và backlog.

**Câu 2.** `maxInFlight=50` của publisher và `prefetch=50` của listener có cùng ý nghĩa không?

**Trả lời:** Không. `maxInFlight` giới hạn lượt publish đang theo dõi ở **producer**; `prefetch` giới hạn delivery chưa ACK ở **consumer**.

**Câu 3.** Có confirm ACK nhưng `CorrelationData.getReturned()` chứa `NO_ROUTE`. Event nên có trạng thái gì?

**Trả lời:** `UNROUTABLE`; ACK không tự chứng minh message đã tới queue nghiệp vụ. Cần sửa topology/routing.

**Câu 4.** Event `evt-1001` bị timeout rồi retry. Giữ ID nào và đổi ID nào?

**Trả lời:** Giữ `eventId/messageId=evt-1001`, tạo **attemptId mới** cho lượt publish mới. Consumer dùng event ID để chống trùng.

**Câu 5.** Khi hết slot, có nên tiếp tục xếp mọi event vào một `LinkedBlockingQueue` không giới hạn trong RAM?

**Trả lời:** Không. Cần backpressure hoặc queue có giới hạn, ưu tiên giữ backlog trong outbox bền vững và chỉ claim thêm khi còn slot.

**Câu 6.** Vì sao timeout không được coi là broker NACK?

**Trả lời:** Timeout chỉ nói producer **không nhận được kết quả trong thời hạn**; broker có thể đã chấp nhận message. NACK là phản hồi tiêu cực thực sự.

**Câu 7.** Tại sao outbox cần lưu `attemptId` riêng với `eventId`?

**Trả lời:** Để audit từng lượt gửi, gắn đúng confirm muộn và bảo vệ state hiện tại khỏi callback của attempt đã hết hạn.

**Câu 8.** Khi đã có durable outbox và publisher confirms, còn cần idempotent `@RabbitListener` không?

**Trả lời:** Vẫn cần. Retry sau UNKNOWN hoặc consumer redelivery do mất ACK có thể gây giao trùng; outbox không tạo exactly-once side effect.

## 15. Tài liệu tham khảo

- [Spring AMQP — AmqpTemplate: Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `RabbitTemplate`, `CorrelationData.getFuture()`, returned message, callback và giới hạn của xác nhận.
- [Spring AMQP — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory`, confirms/returns và channel cache.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ngữ nghĩa ACK/NACK, confirm latency, queue persistence và quorum confirmations.
- [RabbitMQ — Reliable Publishing with Publisher Confirms, Java](https://www.rabbitmq.com/tutorials/tutorial-seven-java): so sánh xác nhận từng message, theo batch và xử lý bất đồng bộ.
- [RabbitMQ — Publishers](https://www.rabbitmq.com/docs/publishers): xác nhận, xử lý unroutable, connection blocking và các cơ chế độ tin cậy phía publisher.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): `RabbitTemplate`, listener acknowledgment và xử lý lỗi trong hệ sinh thái Spring.

**Ghi nhớ:** **Publisher confirms bất đồng bộ cần một cửa sổ in-flight có giới hạn** để tránh tích lũy future và trạng thái chờ vô hạn. `Semaphore` hoặc bounded worker pool chỉ giải quyết **điều tiết trong RAM**; với sự kiện nghiệp vụ quan trọng, phải có **outbox bền vững** lưu event ID, attempt ID và trạng thái `PENDING/WAITING_CONFIRM/CONFIRMED/UNROUTABLE/NACKED/UNKNOWN`. Khi confirm mất hoặc quá hạn, **không đoán message chưa gửi**: tạm dừng, đối soát và retry cùng event ID, kết hợp publisher returns, định tuyến đúng, `@RabbitListener` idempotent, consumer ACK, retry/dead-letter và quan sát hệ thống để xử lý bất đồng bộ đáng tin cậy.
