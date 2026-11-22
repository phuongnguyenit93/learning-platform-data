# At-least-once và event nội bộ trong Spring Framework Application Events

## 1. Câu hỏi quan trọng: publishEvent có bảo đảm at-least-once không?

**Không.** `ApplicationEventPublisher.publishEvent(...)` là cơ chế phát sự kiện **trong một Spring ApplicationContext**, không phải hàng đợi bền vững. Bản thân Spring Application Events **không tự bảo đảm at-least-once delivery**, không lưu event qua restart và không tự retry cho tới khi mọi listener xử lý thành công.

Trong nhóm **Độ tin cậy**, bài **At-least-once và event nội bộ** tập trung vào việc phân biệt ba việc dễ bị nhầm:

1. **Phát thông báo trong bộ nhớ:** Spring chọn listener và dispatch event trong process.
2. **Chạy lại một lời gọi sau lỗi:** retry có thể khiến **cùng một logical event** được xử lý nhiều lần.
3. **Có bảo đảm giao ít nhất một lần:** phải có cơ chế lưu bền vững, theo dõi trạng thái, retry và xác nhận kết quả; không chỉ thêm annotation hay gọi `publishEvent`.

Ví dụ `OrderPlaced(eventId=EVT-42)` được tạo sau khi đặt đơn. Nếu listener ghi audit rồi tiến trình chết trước khi ghi nhận là “đã xử lý”, một worker có retry có thể chạy lại event đó. **At-least-once cho phép duplicate**: cùng một event ID có thể đến consumer hai lần trở lên, và consumer phải xử lý được điều đó.

Một mô hình mong muốn:

```text
Đặt hàng trong transaction
      |
      +--> COMMIT Orders + Outbox record (durable)
                              |
                              v
                       Dispatcher/Worker
                              |
                       gửi / retry event
                              |
                      Consumer/Handler
                              |
                  xử lý idempotent theo eventId
                              |
                    ghi kết quả / xác nhận
```

Điều quan trọng là xác định rõ **đối tượng được bảo đảm**: event đến broker, event đến một consumer cụ thể, hay side effect nghiệp vụ đã thành công? Các mốc này không đồng nghĩa.

### Bạn sẽ học được

- Ý nghĩa at-most-once, at-least-once và exactly-once theo từng ranh giới.
- Spring listener đồng bộ, multicaster bất đồng bộ và `@TransactionalEventListener` có điểm mất event ở đâu.
- Tại sao retry tạo duplicate, đặc biệt ở khoảng giữa **side effect** và **acknowledgment**.
- Thiết kế event ID, idempotency, inbox, outbox và trạng thái xử lý.
- Minh họa Java 17+ với Spring Context: phát lại một event nhưng chỉ áp dụng side effect một lần.
- Phân biệt mô phỏng in-memory với triển khai có bảo đảm bền vững.
- Kiểm thử crash windows, retry, transaction và giám sát event bị kẹt.

## 2. Ba kiểu delivery semantics

| Semantics | Điều hệ thống cố gắng bảo đảm | Rủi ro chính | Khi nào phù hợp? |
| --- | --- | --- | --- |
| **At-most-once** | Một thông điệp không được giao quá một lần qua ranh giới đã chọn | Có thể bị mất | Telemetry/best-effort nếu chấp nhận mất |
| **At-least-once** | Thông điệp được thử giao lại cho tới khi được xác nhận theo chính sách | Có thể bị giao **nhiều lần** | Workflow cần retry và có thể idempotent |
| **Exactly-once** | Một kết quả được áp dụng đúng một lần trong phạm vi được xác định | Khó bảo đảm end-to-end qua nhiều tài nguyên | Cơ chế có transaction/dedupe chặt chẽ, phạm vi hẹp |

**At-least-once không có nghĩa “listener chạy một lần là đủ”.** Nó mô tả **chính sách có retry/ack** của một cơ chế giao nhận, không mô tả số callback duy nhất trong toàn bộ vòng đời event.

Một hệ thống có thể bảo đảm broker nhận ít nhất một lần nhưng **không bảo đảm consumer bên ngoài đã thực hiện side effect**. Hoặc consumer đọc lại event nhiều lần nhưng dùng unique constraint để business effect chỉ được áp dụng một lần. Cần nói rõ tên ranh giới và điều kiện hoạt động.

### Điều kiện để tuyên bố at-least-once

Một kiến trúc thường cần:
- **Nguồn thông điệp bền vững:** outbox DB, durable queue/topic hoặc cơ chế tương đương.
- **Định danh event ổn định:** cùng một event logic giữ nguyên `eventId` qua retry.
- **Quy tắc xác nhận (ack):** chỉ coi attempt thành công tại mốc đã định.
- **Retry theo policy:** lỗi tạm thời được thử lại, có backoff và xử lý lỗi dài hạn.
- **Consumer chịu duplicate:** idempotent hoặc dedupe transactional.
- **Vận hành thực tế:** backlog, alert, retention, DLQ/quarantine, khôi phục sau outage.

Nếu giới hạn số lần retry rồi đưa event vào dead-letter queue, ta phải xác định cam kết: event **không bị âm thầm mất**, nhưng **không phải mọi event đều được xử lý thành công tự động**. Sự cố hạ tầng lâu dài, hết retention hoặc xử lý thủ công chưa hoàn tất vẫn ảnh hưởng kết quả.

## 3. Spring Application Events mặc định làm gì?

### 3.1. Synchronous multicast

Với `SimpleApplicationEventMulticaster` mặc định, listener thường chạy trên **thread của publisher**:

```text
OrderService.placeOrder()
   |
   +--> publishEvent(OrderPlaced)
              |
              +--> Listener A
              +--> Listener B
              +--> Listener C
   |
   +--> publishEvent return (nếu không có lỗi propagate)
```

Nếu listener B ném exception và không có `ErrorHandler` tùy chỉnh để suppress, exception có thể propagate đến publisher, việc dispatch còn lại có thể dừng. Spring **không tự tạo một durable retry record** để đảm bảo B/C sẽ được thử lại sau restart.

Nếu application service bắt exception rồi gọi lại `publishEvent(event)`, listener A **có thể đã thực hiện thành công lần đầu** và sẽ được gọi lần nữa. Đây là một nguồn duplicate phát sinh do retry cả multicast, không nhất thiết vì Spring tự retry.

**Bẫy quan trọng:** `publishEvent` chạy không lỗi chỉ chứng minh các callback được dispatch theo semantics hiện tại, **không** chứng minh một email đã tới người nhận hoặc giao dịch của listener đã commit. Một listener có thể chỉ enqueue một tác vụ khác rồi trả về.

### 3.2. Async multicaster

Khi `SimpleApplicationEventMulticaster.setTaskExecutor(...)` được cấu hình, những listener hỗ trợ async có thể được submit sang executor:

```text
Publisher thread: publishEvent -> submit task -> return
                                        |
                                        v
                                Worker xử lý sau
                                        |
                              success / exception / crash
```

`publishEvent` có thể return **trước khi worker bắt đầu**. Nếu process chết lúc event mới nằm trong hàng đợi **RAM**, công việc chưa chạy có thể mất. Không có broker/outbox bền vững thì đây chỉ là **best-effort dispatch**.

Nếu handler ném exception trên worker, lỗi thường không trở lại thread publish. Cần error handling riêng cho executor, metrics, retry và một nguồn lưu bền vững nếu không được phép mất event.

### 3.3. `@Async @EventListener`

`@Async` chạy qua Spring async proxy và executor được cấu hình qua `@EnableAsync` hoặc `@Async("executorName")`. Nó thay đổi **thread execution**, không tạo một delivery guarantee mới. Với async method trả `void`, exception cần được quan sát qua `AsyncUncaughtExceptionHandler` hoặc cơ chế tương đương. Một `assertThrows` quanh `publishEvent` không kiểm thử đúng thất bại trong worker.

**Tóm lại:** đồng bộ/async là lựa chọn **cách thực thi**; at-least-once là lựa chọn **lưu thông điệp, retry và ack**. Không đánh đồng hai quyết định.

## 4. Bốn thời điểm khác nhau phải theo dõi

Một event thường đi qua nhiều bước:

```text
Domain fact được chấp nhận
   |
   v
Database COMMIT
   |
   v
Event được dispatch / đưa vào queue
   |
   v
Listener/consumer nhận event
   |
   v
Side effect được commit / external API xác nhận
   |
   v
Delivery record được ACK / đánh dấu SENT
```

Các mốc khác nhau sẽ tạo ra các điểm rủi ro:

1. **Trước DB commit:** nếu event được phát và consumer thực hiện side effect ngoài DB, sau đó transaction gốc rollback thì side effect có thể không thể rollback.
2. **Sau DB commit, trước dispatch:** process crash khiến business fact đã lưu nhưng event in-memory chưa đến consumer.
3. **Sau dispatch, trước side effect:** worker crash hoặc downstream timeout; cần biết có retry không.
4. **Sau side effect, trước ACK:** side effect đã thành công nhưng người gửi chưa biết; retry khiến event được xử lý lại. Đây là **điểm kinh điển tạo duplicate**.
5. **Sau ACK, trước việc được coi là hoàn tất ở hệ thống khác:** ACK cục bộ có thể chỉ xác nhận enqueue, chưa nói lên external consumer xử lý xong.

Vì vậy, không thể giải quyết độ tin cậy chỉ bằng “đưa listener vào `AFTER_COMMIT`”. Giải pháp cần bám vào **failure window** và loại side effect được yêu cầu.

## 5. Transaction-bound events: AFTER_COMMIT giúp gì và không giúp gì?

Ví dụ listener:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    notificationService.send(event.orderId());
}
```

Đây là **mẫu tích hợp**, cần bean Spring, transaction manager, event type và imports tương ứng.

`@TransactionalEventListener` mặc định dùng `AFTER_COMMIT`. Khi publisher phát event trong một transaction phù hợp, listener được gắn vào transaction synchronization và chạy ở phase đã cấu hình. Nếu không có transaction phù hợp, mặc định listener **không được gọi** (`fallbackExecution=false`), trừ khi ứng dụng cho phép fallback một cách tường minh.

Ưu điểm: giảm nguy cơ chạy side effect cho một transaction bị rollback trước commit.

Nhưng giới hạn phải nhớ:

- Nếu JVM/process bị dừng **ngay sau commit** trước khi callback chạy, event có thể **mất**; Spring không có durable callback registry mặc định.
- Nếu callback `AFTER_COMMIT` ném exception, transaction gốc đã commit; không thể “rollback ngược” business fact.
- Nếu callback làm việc với DB, tài nguyên transaction cũ có thể vẫn đang bound trong một giai đoạn cleanup; thao tác ghi mới cần transaction riêng thích hợp, ví dụ bean method với `Propagation.REQUIRES_NEW`.
- `AFTER_COMMIT` không có nghĩa bất đồng bộ; body có thể chạy trong thread hoàn tất transaction.
- Với Spring 6.1 và reactive transactions, transaction context nằm trong Reactor Context; event cần mang `TransactionContext` làm source (thường qua `TransactionalEventPublisher`) để transactional event listener nhận đúng context. Điều này **không** tạo bảo đảm giao bền vững.

**Kết luận:** `AFTER_COMMIT` giúp chọn **thời điểm chạy**, không phải cơ chế at-least-once.

## 6. Thiết kế event nội bộ có identity rõ ràng

Một event phù hợp nên mang ID ổn định:

```java
public record OrderPlaced(
    String eventId,
    String orderId,
    String correlationId,
    long totalCents
) {}
```

Trong ví dụ này:
- `eventId` xác định **một lần xảy ra** event logic, không thay khi retry chính event đó.
- `orderId` xác định aggregate; một order có thể phát nhiều event khác nhau.
- `correlationId` liên kết nhiều bước cùng workflow để truy vết log; **không** thay thế event ID dùng dedupe.
- `totalCents` là snapshot giá trị nghiệp vụ tại thời điểm event xảy ra.

Không đưa JPA managed entity hoặc mutable collection trực tiếp vào payload cần retry/replay. Sau khi transaction đóng hoặc process restart, entity cũ không còn là một snapshot đáng tin. Record với primitive/value object immutable phù hợp hơn.

**Đừng tạo `UUID.randomUUID()` mỗi lần worker retry.** ID nên được cấp tại thời điểm event logic được tạo và lưu trong outbox, sau đó được chuyển nguyên vẹn qua mọi attempt. Với nhiều consumer độc lập, key dedupe thường là cặp **`consumerName + eventId`**, không phải chỉ event ID toàn hệ thống; mỗi consumer có quyền xử lý cùng event một lần theo trách nhiệm của mình.

## 7. Vì sao retry sinh duplicate?

Giả sử worker có outbox event `EVT-42` và gửi tới consumer:

```text
Attempt #1:
   Worker gửi EVT-42
   Consumer xử lý, ghi projection thành công
   Worker bị ngắt trước khi ghi ACK/SENT
   => outbox vẫn cho rằng chưa gửi xong

Attempt #2:
   Worker đọc lại EVT-42
   Consumer nhận lại cùng EVT-42
   => duplicate delivery
```

Từ góc nhìn sender, attempt #1 chưa được xác nhận. Từ góc nhìn consumer, business effect có thể đã được commit. Không có một transaction chung bao trùm database ở cả hai đầu và broker, sender **không thể suy ra** event có được xử lý hay chưa chỉ từ timeout hoặc mất ACK.

Nên phân biệt:
- **Duplicate delivery:** cùng event được gửi/nhận lại nhiều lần.
- **Duplicate attempt:** cùng handler có thể được gọi nhiều lần.
- **Duplicate business effect:** cùng nghiệp vụ được áp dụng nhiều lần ngoài ý muốn.

At-least-once **cho phép hai loại đầu**, nhưng phải thiết kế để **tránh loại thứ ba**.

### Lặp event không phải luôn là lỗi

Nếu event `OrderPlaced(EVT-42)` được giao lại, listener idempotent có thể skip lần hai. Nhưng nếu sau đó đơn hàng phát `OrderAddressChanged(EVT-43)`, đó là event khác và phải được xử lý dù `orderId` giống nhau. Dedupe bằng `orderId` đơn thuần sẽ loại sai event hợp lệ.

## 8. Ví dụ Java 17+ chạy được: mô phỏng duplicate và idempotent listener

Ví dụ này dùng **Spring Context 6.1.21**, không cần Spring Boot, message broker hay database. Nó mô phỏng:

1. Lưu một event vào **outbox in-memory** (không bền vững).
2. Worker publish event cho `@EventListener` đồng bộ.
3. Giả lập worker gặp lỗi **sau khi listener đã xử lý nhưng trước khi đánh dấu SENT**.
4. Worker retry **chính cùng event ID**.
5. Listener kiểm tra `eventId` trong một tập `processedIds` và chỉ tăng business effect một lần.

**Giới hạn bắt buộc hiểu:** chương trình không cố tình crash JVM, mà ném exception để mô phỏng một failure window. Cả outbox và processed IDs đều nằm trong RAM, nên **demo không thực sự cung cấp at-least-once sau restart**. Muốn có guarantee trong production phải thay bằng DB/broker và dedupe transaction như mục 9–11.

### 8.1. Cấu trúc

```text
internal-event-retry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/InternalEventRetryDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'internal-event-retry-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.InternalEventRetryDemo'
}
```

### 8.2. File Java hoàn chỉnh

`src/main/java/demo/InternalEventRetryDemo.java`:

```java
package demo;

import java.util.HashSet;
import java.util.Set;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class InternalEventRetryDemo {

    public record OrderPlaced(String eventId, String orderId) {}

    // Mô phỏng durable outbox, nhưng thực tế chỉ lưu trong RAM.
    public static final class InMemoryOutbox {
        private OrderPlaced pending;
        private boolean sent;
        private int attempts;

        public void add(OrderPlaced event) {
            if (pending != null) {
                throw new IllegalStateException("One event only in demo");
            }
            pending = event;
        }

        public OrderPlaced nextPending() {
            return sent ? null : pending;
        }

        public void incrementAttempts() {
            attempts++;
        }

        public void markSent() {
            sent = true;
        }

        public int attempts() {
            return attempts;
        }

        public boolean sent() {
            return sent;
        }
    }

    // In-memory idempotency: chỉ dùng minh họa, không an toàn qua restart.
    public static final class OrderProjectionListener {
        private final Set<String> processedIds = new HashSet<>();
        private int effects;

        @EventListener
        public void on(OrderPlaced event) {
            if (!processedIds.add(event.eventId())) {
                System.out.println(
                    "DUPLICATE eventId=" + event.eventId()
                );
                return;
            }

            effects++;
            System.out.println(
                "HANDLED eventId=" + event.eventId()
                    + " orderId=" + event.orderId()
            );
        }

        public int effects() {
            return effects;
        }
    }

    public static final class OutboxWorker {
        private final InMemoryOutbox outbox;
        private final ApplicationEventPublisher publisher;

        public OutboxWorker(
                InMemoryOutbox outbox,
                ApplicationEventPublisher publisher) {
            this.outbox = outbox;
            this.publisher = publisher;
        }

        public void deliverOnce(boolean failBeforeAck) {
            OrderPlaced event = outbox.nextPending();
            if (event == null) {
                return;
            }

            outbox.incrementAttempts();
            publisher.publishEvent(event);

            // Giả lập lỗi ở sender sau khi listener đã chạy.
            if (failBeforeAck) {
                throw new IllegalStateException(
                    "simulated failure after publish"
                );
            }

            outbox.markSent();
            System.out.println(
                "ACKED eventId=" + event.eventId()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public InMemoryOutbox outbox() {
            return new InMemoryOutbox();
        }

        @Bean
        public OrderProjectionListener projectionListener() {
            return new OrderProjectionListener();
        }

        @Bean
        public OutboxWorker worker(
                InMemoryOutbox outbox,
                ApplicationEventPublisher publisher) {
            return new OutboxWorker(outbox, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            InMemoryOutbox outbox =
                context.getBean(InMemoryOutbox.class);
            OutboxWorker worker =
                context.getBean(OutboxWorker.class);
            OrderProjectionListener projection =
                context.getBean(OrderProjectionListener.class);

            outbox.add(new OrderPlaced("EVT-42", "ORD-42"));

            try {
                worker.deliverOnce(true);
            } catch (IllegalStateException expected) {
                System.out.println(
                    "WORKER_ERROR " + expected.getMessage()
                );
            }

            // Retry cùng event, không sinh eventId mới.
            worker.deliverOnce(false);

            System.out.println(
                "attempts=" + outbox.attempts()
            );
            System.out.println(
                "business_effects=" + projection.effects()
            );
            System.out.println(
                "outbox_sent=" + outbox.sent()
            );
        }
    }
}
```

Chạy với JDK 17+ và Gradle đã cài:

```bash
gradle run --quiet
```

**Stdout nghiệp vụ kỳ vọng:**

```text
HANDLED eventId=EVT-42 orderId=ORD-42
WORKER_ERROR simulated failure after publish
DUPLICATE eventId=EVT-42
ACKED eventId=EVT-42
attempts=2
business_effects=1
outbox_sent=true
```

Giải thích từng bước:

1. `Config` tạo `OrderProjectionListener` là Spring bean có method `@EventListener`. Không cấu hình async multicaster nên Spring dispatch đồng bộ khi `publisher.publishEvent(event)` được gọi.
2. Worker lần thứ nhất lấy `EVT-42`, tăng `attempts`, publish event. Handler chưa từng thấy ID nên tăng `effects=1` và in `HANDLED`.
3. Worker ném exception **sau** khi `publishEvent` đã hoàn tất nhưng **trước** khi gọi `outbox.markSent()`; main bắt lỗi và in `WORKER_ERROR`.
4. Vì `sent=false`, worker lần thứ hai đọc lại **chính object event** với `eventId=EVT-42`. Handler đã lưu ID đó trong `processedIds` nên in `DUPLICATE` và không tăng `effects`.
5. Worker đánh dấu `sent=true`, in `ACKED`. Kết quả hai attempts, một business effect, trạng thái sent.
6. `HashSet` và `int` trong demo **không thread-safe** khi listener chạy song song; việc kiểm tra `contains/add` cũng không đủ đảm bảo exactly-once giữa các process. Ở production cần unique constraint/transaction và phân phối công việc được kiểm soát.
7. `outbox.sent()` chỉ minh họa ACK **cục bộ**. Trong mô hình thực, ACK broker hoặc dấu mốc SENT có ngữ nghĩa riêng; không nên coi “publish returned” trong async multicaster là listener hoàn tất.

**Điểm mấu chốt:** ví dụ cho thấy *vì sao* duplicate xuất hiện và *tại sao* cần idempotency, chứ không chứng minh Spring Application Events tự mang guarantee at-least-once. Đây là bài học về thiết kế failure handling, không phải lời hứa durable delivery.

## 9. Mẫu production: transactional outbox để không mất intent phát event

Một cách tiếp cận đáng tin hơn cho ứng dụng dùng relational DB:

```text
Trong transaction đặt hàng:
    UPDATE orders SET status = 'PLACED', ...
    INSERT INTO outbox(
        event_id, aggregate_id, type, payload, status
    ) VALUES (..., 'PENDING')
    COMMIT  -- cùng một transaction

Outbox dispatcher sau commit:
    đọc record PENDING
    gửi tới broker / handler được quản lý
    đợi ack của đích đã định
    đánh dấu SENT hoặc lên lịch retry

Consumer:
    nhận event có eventId ổn định
    dedupe/idempotent
    commit business effect
    xác nhận tiêu thụ khi thích hợp
```

Nếu business transaction rollback, cả thay đổi `orders` và record outbox rollback. Nếu commit, intent gửi event đã được lưu bền vững. Worker có thể restart và đọc lại record chưa gửi.

### 9.1. Hai bước phải atomic ở bên phát

Ví dụ pseudo-SQL:

```sql
BEGIN;

UPDATE orders
SET status = 'PLACED'
WHERE order_id = :order_id
  AND status = 'DRAFT';

-- Sau khi xác nhận đúng một đơn hợp lệ đã được đổi trạng thái:
INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload_json, status
) VALUES (
    :event_id, :order_id, 'OrderPlaced', :payload_json, 'PENDING'
);

COMMIT;
```

Đây là **mẫu ý tưởng**, cần schema, business invariant, locking/optimistic locking và logic kiểm tra row count theo DB thực tế. Không phát broker trước khi transaction commit chỉ để rồi mong rollback sẽ thu hồi được thông điệp.

**Không biến outbox thành event payload chứa JPA entity mutable.** Lưu ID và snapshot bất biến được version hóa, hoặc một integration DTO/JSON có hợp đồng rõ ràng.

### 9.2. Sender có thể gửi lại cùng record

Outbox dispatcher thông thường thực hiện:

```text
select pending event
claim/lease
publish message
receive broker acknowledgment
mark record sent
```

Nếu worker crash **sau publish thành công nhưng trước mark sent**, lần sau có thể gửi duplicate. Đây là lý do transactional outbox thường tạo **at-least-once publishing**, không mặc định exactly-once end-to-end.

Để có nhiều dispatcher:
- Claim một nhóm record bằng locking/lease phù hợp (ví dụ `FOR UPDATE SKIP LOCKED` nếu DB hỗ trợ).
- Thiết kế lease expiry để worker khác lấy lại nếu instance chết.
- Tránh giữ transaction DB mở xuyên qua remote API call kéo dài nếu không có lý do đặc biệt; có thể dùng claim state/lease để quản lý.
- Phân biệt thời gian outbox pending, inflight, sent, failed, quarantined.
- Có policy retry/backoff, giám sát và khôi phục khi broker lỗi.

`SENT` cần được định nghĩa: ví dụ broker đã ack nhận message, **không nhất thiết** tất cả consumer đã xử lý.

### 9.3. Event nội bộ có cần broker không?

**Không bắt buộc.** Nếu yêu cầu chỉ là “chạy một công việc sau commit, không được mất”, có thể triển khai **durable local job/outbox table** trong cùng ứng dụng:
- Business transaction ghi job/outbox vào DB.
- Worker trong cùng application đọc các job pending sau commit.
- Worker gọi service handler và ghi kết quả/ack.
- Nếu worker lỗi/restart, job chưa ack có thể được thử lại.
- Handler dùng idempotency theo job/event ID.

Cơ chế này có tính bền vững của dữ liệu nguồn mà không cần Kafka/RabbitMQ. Nhưng cần thiết kế multi-instance concurrency, lease, retry, failure policy và khả năng vận hành. Đừng dùng `ApplicationEventPublisher` thuần để giả lập durable job queue.

## 10. Inbox/idempotency: tránh duplicate business effect

Outbox chỉ xử lý phía **phát/gửi**. Consumer muốn tránh làm trùng effect nên lưu dấu event đã xử lý dưới một transaction thích hợp.

### 10.1. Mẫu inbox trong relational DB

Ví dụ pseudo-SQL cho consumer cập nhật projection:

```sql
BEGIN;

INSERT INTO processed_events (consumer_name, event_id)
VALUES (:consumer_name, :event_id)
ON CONFLICT DO NOTHING;

-- Nếu INSERT tạo 1 row: xử lý effect trong CÙNG transaction.
-- Nếu INSERT tạo 0 row: duplicate; không áp dụng effect lần nữa.

UPDATE order_projection
SET placed_orders = placed_orders + 1
WHERE projection_id = :projection_id;

COMMIT;
```

**Cảnh báo:** đoạn trên là **sơ đồ thao tác**, không phải script chạy nguyên xi. Nó giả định PostgreSQL-style `ON CONFLICT` và code ứng dụng **kiểm tra row count**; câu `UPDATE` chỉ được chạy khi INSERT thành công. Nếu INSERT là duplicate, bỏ qua UPDATE rồi commit/ack. Cần unique constraint:

```sql
ALTER TABLE processed_events
ADD CONSTRAINT uq_processed_consumer_event
UNIQUE (consumer_name, event_id);
```

Điều kiện đủ an toàn ở đây:
1. Insert dấu “đã xử lý” và thay đổi projection **nằm trong cùng DB transaction**.
2. Unique constraint ở DB bảo đảm hai worker đua nhau xử lý cùng `(consumerName,eventId)` không cùng tạo effect, dù cả hai đọc “chưa thấy event” trước khi insert.
3. Nếu transaction lỗi trước commit, **cả inbox marker và projection update rollback**; retry vẫn có thể xử lý.
4. ACK message **sau khi** DB transaction commit thành công, theo semantics của broker/consumer cụ thể.

Không đặt marker “processed” trước rồi thực hiện business update ở transaction khác: crash giữa hai bước sẽ tạo marker nhưng effect chưa xảy ra, khiến retry bị bỏ qua và event bị mất hiệu quả.

### 10.2. Xử lý external side effects

Nếu consumer cần gửi email, gọi payment gateway hoặc API ngoài DB, không thể giả định unique constraint local bảo đảm side effect ngoài đã thực hiện đúng một lần.

Các hướng:
- Gọi API hỗ trợ **idempotency key** và truyền `eventId` hoặc một key nghiệp vụ thích hợp.
- Chuyển tác vụ ngoài thành **job/outbox thứ cấp** được ghi cùng transaction dedupe, rồi worker riêng xử lý có retry.
- Với bên thứ ba không hỗ trợ idempotency, thiết kế reconciliation/compensation, điều tra trạng thái qua external reference và giới hạn tác hại của duplicate.
- Không ghi “đã xử lý” chỉ vì request HTTP được gửi; cần xác định trạng thái thành công/tạm lỗi/không rõ kết quả.

Một email được gửi hai lần có thể là duplicate khó tránh nếu nhà cung cấp không có chính sách idempotency mạnh. Hãy mô tả guarantee thực tế, thay vì quảng cáo exactly-once khi các ranh giới không cùng transaction.

### 10.3. Dedupe key theo consumer

Giả sử `EVT-42` được tiêu thụ bởi `BillingProjection`, `AuditProjection` và `NotificationHandler`. Nếu dùng bảng chung với unique `eventId` đơn lẻ và consumer đầu tiên ghi marker, các consumer còn lại có thể bị chặn sai.

Nên có unique key `(consumer_name, event_id)` hoặc bảng inbox riêng mỗi consumer. Mỗi consumer được phép xử lý cùng event theo mục tiêu của nó **một lần**, đồng thời chặn retry trùng cho chính nó.

## 11. At-least-once với nhiều listener trong cùng process

Một Spring event có thể kích hoạt nhiều listener độc lập:

```text
OrderPlaced EVT-42
   |
   +--> AuditListener           success
   +--> NotificationListener    failed
   +--> LoyaltyListener         success
```

Nếu retry **cả** `publishEvent(EVT-42)`, `AuditListener` và `LoyaltyListener` có thể chạy lại dù đã thành công. Không có per-listener acknowledgment mặc định của Spring multicaster.

Có ba lựa chọn phụ thuộc yêu cầu:

1. **Best-effort internal event:** chấp nhận mất task/phải làm thủ công; đơn giản, dùng cho metrics/cache invalidation có thể xây lại, nếu nghiệp vụ cho phép.
2. **Local per-handler retry/idempotency:** retry logic của handler với key ổn định, timeout, error reporting; nếu chỉ giữ state trong RAM thì vẫn có crash gap.
3. **Durable handler jobs:** lưu một nhiệm vụ cho từng consumer quan trọng, ví dụ unique `(eventId,handlerName)`, retry và ack độc lập. Có thể triển khai bằng DB queue/outbox hoặc broker có consumer groups/subscriptions thích hợp.

Dùng một status `SENT` chung cho cả sự kiện **không chứng minh** tất cả listener đã hoàn tất. Nếu cần fan-out reliable, theo dõi outcome theo consumer/subscription/handler. Một handler chậm không nên làm mất khả năng xử lý của handler khác, trừ khi transaction nghiệp vụ yêu cầu tất cả cùng một ranh giới atomic được thiết kế rõ.

### Thứ tự và version

At-least-once **không bảo đảm ordering**. Event `OrderPlaced(v5)` có thể bị retry và đến sau `OrderCancelled(v6)`. Consumer cần chính sách:
- xử lý theo `aggregateVersion`/sequence nếu contract yêu cầu;
- phát hiện duplicate bằng `eventId`;
- bỏ qua version cũ, buffer hoặc reconcile tùy ngữ nghĩa;
- dùng partition/key phù hợp nếu broker bảo đảm thứ tự trong phạm vi đó.

Dedupe và ordering là **hai bài toán khác nhau**.

## 12. Backoff, poison messages và giới hạn retry

Retry mọi lỗi ngay lập tức có thể tạo retry storm:
- DB đang down → hàng nghìn task lập tức retry, tăng tải thêm.
- Broker chậm → publisher giữ thread và connection tới hạn.
- Event payload không hợp lệ → retry mãi một lỗi vĩnh viễn, không có hy vọng thành công.
- Một listener lỗi chặn cả pipeline nếu không có cơ chế cách ly.

Một chính sách thực tế có thể phân lỗi:

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Tạm thời | network timeout, 503, deadlock có thể retry | Backoff có jitter, giới hạn đồng thời |
| Không hợp lệ | schema sai, ID thiếu, domain invariant bị vi phạm | Không retry vô hạn; quarantine/DLQ, sửa hoặc can thiệp |
| Không rõ kết quả | HTTP timeout sau khi downstream có thể đã commit | Retry **cùng idempotency key**, reconcile khi cần |
| Conflict do duplicate | Inbox unique conflict/đã xử lý | Ack theo contract; không tạo side effect mới |
| Hạ tầng quá tải | queue full, broker unavailable | Giữ durable record và giảm tốc retry/backpressure |

**Exponential backoff với jitter** giảm tình huống nhiều worker cùng retry tại một thời điểm. Có thể dùng max attempts rồi đưa record vào DLQ, nhưng lúc ấy guarantee phải được diễn đạt chính xác: event đã được giữ để xử lý thất bại, **không phải đã hoàn tất nghiệp vụ**. Cần dashboard và quy trình replay/resubmit an toàn.

Không thay event ID khi chuyển vào DLQ hoặc phát lại cùng logical event; lưu attempt count và last error thành metadata riêng, tránh nhét vào identity của event.

## 13. Transaction, error handling và khả năng mất event

### 13.1. @EventListener nằm trong transaction gốc

Một `@EventListener` đồng bộ được gọi khi service đang `@Transactional` có thể thực thi trước commit. Nếu listener ghi cùng DB transaction, thay đổi của nó có thể rollback cùng service khi transaction thất bại. Nhưng nếu listener gọi API ngoài, API không tham gia rollback DB theo mặc định.

Thêm `@TransactionalEventListener(AFTER_COMMIT)` để trì hoãn side effect có thể đúng về timing, nhưng vẫn có crash window sau commit. Với công việc phải hoàn tất, outbox được lưu atomic với nghiệp vụ giúp thu hẹp lỗ hổng về **mất intent gửi**.

### 13.2. ErrorHandler của multicaster

`SimpleApplicationEventMulticaster.setErrorHandler(...)` có thể thay đổi cách lỗi listener được xử lý. Nếu handler suppress exception và chỉ log, caller có thể thấy publish thành công dù listener lỗi. Nếu handler propagate, caller có thể nhận lỗi (trong sync path) và nghĩ nên retry toàn bộ event; hãy cân nhắc các listener đã thực hiện effect trước đó.

Không dựa vào kết quả `publishEvent()` như một ACK bền vững khi có async listener. Nếu dùng custom ErrorHandler, metrics và retry cần biết chính xác exception được xem là failure ở đâu, tránh vừa nuốt lỗi vừa đánh dấu task “DONE”.

### 13.3. Retry không được làm lặp domain command

Giả sử command `PlaceOrder` đã commit và phát event `OrderPlaced`. Khi cần gửi lại notification, **không** chạy lại toàn bộ `PlaceOrder` command để tạo event mới; cách đó có thể làm lặp hóa đơn/thanh toán hoặc tạo thêm audit facts.

Hãy lưu và retry **event đã xảy ra** với ID ổn định, không replay nghiệp vụ nguồn trừ khi command được thiết kế idempotent và đó thực sự là thao tác mong muốn.

### 13.4. Reactive flows

Trong Spring WebFlux, một `Mono` chưa subscribe thì logic có thể chưa chạy. Tạo event rồi gọi `publishEvent` bên ngoài chuỗi reactive không tự khiến transaction hoặc eventual completion đúng. Với reactive transaction, dùng context propagation và `TransactionalEventPublisher` phù hợp; `@TransactionalEventListener` không biến message thành durable queue.

Không tự gọi `subscribe()` trong listener để “fire-and-forget” khi tác vụ yêu cầu bảo đảm: exception, cancellation, lifecycle và việc chờ completion sẽ khó kiểm soát. Cần nối composition hoặc lưu durable work theo contract.

## 14. Kiểm thử at-least-once và idempotency

Test reliability **không thể chỉ assert một callback được gọi**. Phải kiểm thử các failure windows và duplicate attempts.

### 14.1. Unit test của idempotent handler

Với một handler nhận `EVT-42`:
1. Gọi lần đầu; assert business effect được áp dụng.
2. Gọi lần hai với **cùng `eventId`**; assert effect không tăng.
3. Gọi `EVT-43` với cùng `orderId` nhưng là event khác; assert event mới được xử lý đúng.
4. Nếu có nhiều consumer, xác nhận mỗi consumer dedupe độc lập.
5. Kiểm tra record chứa snapshot immutable, không mang managed entity.

Trong demo Java ở mục 8, hai lần publish cùng event cho ra `business_effects=1`, nhưng chưa đủ chứng minh persistence idempotency.

### 14.2. Integration test transaction rollback

Dùng DB thật hoặc test container:
- Trong một transaction, cập nhật aggregate và insert outbox.
- Ép rollback; assert **cả hai** không được commit.
- Commit bình thường; assert **cả hai** tồn tại.
- Đừng chỉ mock repository rồi kết luận đã kiểm thử atomicity.

Nếu dùng test method `@Transactional` và framework tự rollback cuối test, chủ động kiểm soát commit bằng `TransactionTemplate` hoặc test transaction utilities khi cần chứng minh nhánh commit.

### 14.3. Crash trước và sau ACK

Các kịch bản cần thử:

| Điểm lỗi giả lập | Dữ liệu còn lại | Kỳ vọng sau restart/retry |
| --- | --- | --- |
| Trước khi DB transaction commit | Không có aggregate change/outbox | Không phát event giả |
| Sau DB commit, trước dispatcher | Outbox PENDING tồn tại | Worker gửi tiếp |
| Sau broker nhận, trước sender đánh dấu SENT | Outbox vẫn PENDING | Có thể gửi duplicate; consumer dedupe |
| Sau consumer DB effect commit, trước broker ACK | Effect + inbox marker đã commit | Broker redeliver; consumer skip duplicate và ACK |
| Trước consumer DB commit | Effect + marker rollback | Retry áp dụng effect một lần |
| External API timeout không rõ kết quả | Trạng thái downstream có thể thành công | Retry cùng idempotency key/reconcile |
| Event gây lỗi vĩnh viễn | Record bị retry/đưa DLQ | Có alert và thao tác recovery, không biến mất lặng lẽ |

Test sender crash có thể dùng fault injection ở đúng bước (sau publish và trước mark sent). Test consumer crash có thể kill process/test container hoặc chèn lỗi kiểm soát; cần đọc lại state từ storage bền vững thay vì giữ tất cả trong RAM.

### 14.4. Concurrency test

Hai worker cùng nhận `EVT-42` đồng thời không được tạo hai business effects:
- Dùng unique constraint trong DB làm cơ chế tranh chấp cuối cùng.
- Test hai transaction chạy song song và kiểm tra một transaction trở thành duplicate.
- Không chỉ dùng `ConcurrentHashMap.putIfAbsent(...)` trong một process rồi tuyên bố an toàn khi chạy nhiều instance.
- Nếu record outbox được claim bởi nhiều dispatcher, kiểm thử lease, lock và expiry.

### 14.5. Test async bằng tín hiệu, không sleep

Nếu listener thực thi async, dùng `CountDownLatch`, `CompletableFuture` hoặc Awaitility với timeout hữu hạn để chờ **đúng mốc xử lý**; `Thread.sleep(500)` không chứng minh at-least-once. Một test đợi `publishEvent()` trả về chưa chứng minh listener đã chạy.

### 14.6. Integration test sau commit

Với `@TransactionalEventListener(AFTER_COMMIT)`, commit thật rồi assert listener chạy; rollback thì listener after-commit không chạy. Tuy nhiên, kết quả ấy chỉ kiểm thử **phase behavior**, không chứng minh callback vẫn chạy sau process crash. Muốn kiểm tra reliability, phải test outbox/queue và restart recovery.

## 15. Quan sát và vận hành đường at-least-once

Các metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `outbox.pending.count` | Số event chưa gửi |
| `outbox.oldest.pending.age` | Tuổi event pending lâu nhất |
| `outbox.dispatch.attempts` | Số attempt gửi |
| `outbox.dispatch.failures` | Số lần gửi lỗi |
| `outbox.sent.count` | Số lần đánh dấu sender giao thành công |
| `consumer.duplicate.count` | Số duplicate được dedupe |
| `consumer.processing.duration` | Thời gian xử lý một attempt |
| `consumer.final.failures` | Số event rơi vào quarantine/DLQ |

Tên trên chỉ là **quy ước minh họa**; Micrometer/Prometheus không tự xuất toàn bộ các metric này nếu không có instrumentation. Đặt tag hữu hạn như `eventType`, `consumer`, `outcome`, `exceptionCategory`.

**Không gắn `eventId` hoặc `orderId` vào metric tags** vì high cardinality. Đưa ID vào structured logs/tracing; giữ `correlationId` để lần theo workflow. Khi phát hiện một record PENDING quá lâu hoặc DLQ tăng, cần alert và runbook khôi phục, không chỉ dashboard.

Phân biệt metric:
- `dispatch attempts`: số lần thử.
- `logical events`: số event ID khác nhau.
- `consumer effects committed`: số effect nghiệp vụ đã commit.
- `duplicates skipped`: số attempt bị khử trùng lặp.

Nếu ba attempts của cùng `EVT-42` chỉ có một lần effect, việc hiển thị “3 events processed” là sai ngữ nghĩa. Nên đặt tên và mô tả số liệu đúng ranh giới để SLO không bị méo.

## 16. Khi nào chỉ cần event nội bộ best-effort?

Không phải mọi event đều cần outbox và broker.

| Sự kiện / tác vụ | Độ tin cậy điển hình cần cân nhắc |
| --- | --- |
| Ghi một metric phụ có thể thiếu mẫu | Best-effort thường chấp nhận được |
| Xóa cache có TTL và có thể rebuild | Có thể chấp nhận eventual repair |
| Gửi thông báo không thiết yếu | Tùy cam kết sản phẩm; retry hoặc queue có thể đủ |
| Cập nhật projection quan trọng cho người dùng | Nên có durable retry hoặc cơ chế rebuild/reconciliation |
| Gửi hóa đơn, ghi sổ, tính phí | Cần atomic intent, idempotency, audit và recovery nghiêm ngặt |
| Tích hợp giữa dịch vụ, yêu cầu không mất thay đổi | Outbox + broker/worker + consumer dedupe và giám sát |

Các ví dụ chỉ gợi ý thảo luận; yêu cầu nghiệp vụ thực tế quyết định mức bảo đảm. Một số hệ thống có thể dựng lại projection từ dữ liệu gốc thay vì lưu mỗi event; khi ấy phải kiểm tra thời gian phục hồi và yêu cầu nhất quán.

**Đừng nâng tất cả Spring events thành Kafka messages chỉ vì sợ duplicate.** Ngược lại, đừng dùng một `@Async @EventListener` in-memory cho công việc mất một lần là không thể chấp nhận được. Chọn mức độ tin cậy đúng mục tiêu.

## 17. Những nhầm lẫn thường gặp

1. **“Spring publishEvent bảo đảm at-least-once.”** Sai: nó dispatch in-process; không có durable store/retry mặc định.
2. **“@TransactionalEventListener(AFTER_COMMIT) không bao giờ mất event.”** Sai: crash ngay sau commit vẫn có khoảng trống.
3. **“Bật @Async là đã có queue an toàn.”** Sai: executor queue trong RAM không tự sống qua process restart.
4. **“At-least-once nghĩa listener chỉ chạy một lần.”** Sai: duplicate là hành vi được chấp nhận.
5. **“Event ID là order ID.”** Sai: một aggregate có thể tạo nhiều event.
6. **“Retry toàn bộ PlaceOrder command cũng giống retry OrderPlaced event.”** Sai: có thể lặp nghiệp vụ nguồn.
7. **“Một HashSet trong JVM đủ để khử trùng lặp.”** Không bền vững qua restart và không an toàn giữa nhiều instance.
8. **“INSERT inbox marker rồi gửi API ở transaction khác là atomic.”** Không: crash giữa hai bước có thể làm mất effect.
9. **“Sender đánh dấu SENT nghĩa mọi consumer đã xong.”** Không nhất thiết; phụ thuộc ACK contract.
10. **“Outbox cho exactly-once end-to-end.”** Thông thường không: có thể duplicate khi crash giữa publish và mark sent.
11. **“Dedupe bằng correlationId là đủ.”** Sai: một correlation ID có thể gắn nhiều event.
12. **“At-least-once đảm bảo ordering.”** Sai: ordering/version phải được xử lý riêng.
13. **“Retry lỗi vĩnh viễn càng nhanh càng tốt.”** Không: gây retry storm; cần backoff/quarantine.
14. **“ErrorHandler suppress lỗi nhưng publish trả về nghĩa là thành công.”** Không: có thể listener đã fail.
15. **“Chỉ cần chạy test một lần là đã chứng minh crash recovery.”** Không: cần test durable state và fail/restart windows.

## 18. Checklist review thiết kế

- [ ] Đã nói rõ **ranh giới** được bảo đảm: sender→broker, broker→consumer hay business effect?
- [ ] Công việc quan trọng đã có durable intent/outbox hoặc queue tương đương?
- [ ] Event ID được tạo **một lần** cho logical event và giữ qua retry?
- [ ] Không dùng correlation ID hoặc aggregate ID thay cho event ID?
- [ ] Payload bất biến/serializable, không chứa JPA managed entity hoặc transient context?
- [ ] Aggregate + outbox ghi trong cùng transaction nếu cần tránh mất event sau commit?
- [ ] Có ACK contract rõ: SENT nghĩa gì, DONE nghĩa gì?
- [ ] Consumer có dedupe/unique constraint theo `(consumerName,eventId)` và effect atomic khi có thể?
- [ ] External side effect có idempotency key hoặc reconciliation/compensation?
- [ ] Có retry/backoff/jitter, timeout, dead-letter/quarantine và runbook?
- [ ] Có xử lý cạnh tranh giữa nhiều workers, lease/claim và reset sau crash?
- [ ] Có chính sách ordering/version và xử lý event đến trễ?
- [ ] Metrics phân biệt attempts, duplicate, effect committed và backlog?
- [ ] Test bao phủ rollback, crash trước/sau ACK, duplicate, concurrency và restart?
- [ ] Nếu chỉ best-effort, nghiệp vụ đã chấp nhận rủi ro mất event chưa?

**Ghi nhớ:** Spring Application Events giải quyết việc **thông báo trong process**, chứ không mặc định giải quyết **giao nhận bền vững**. Nếu yêu cầu at-least-once, phải có nguồn event/job durable, retry và ACK rõ ràng. Khi ấy duplicate là điều bình thường: thiết kế consumer idempotent và transaction/inbox đúng cách để cùng một logical event có thể được **giao nhiều lần nhưng chỉ tạo side effect nghiệp vụ hợp lệ một lần** trong phạm vi đã cam kết.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1 API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.1 API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring 6.1 API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Martin Fowler — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Idempotent Consumer Pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
- [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
