# Dead-letter cho event nội bộ trong Spring Framework

## 1. Mục tiêu và phạm vi

Trong hệ thống dùng Spring Application Events, một listener có thể xử lý lỗi khi kết nối dịch vụ ngoài, định dạng dữ liệu sai, thiếu quyền, timeout hoặc tài nguyên đã bị xóa. Nếu chỉ log rồi bỏ qua, bạn có nguy cơ **mất việc cần làm**. Nếu retry mãi ngay trong thread publisher, có thể làm nghẽn request, giữ transaction lâu, tạo tác dụng phụ trùng lặp và lan truyền sự cố. Một cách thiết kế là đưa các tác vụ **không xử lý được** vào một vùng **dead-letter (DLQ/DL store)** để điều tra, sửa và phát lại có kiểm soát.

**Quan trọng:** Spring Framework `ApplicationEventPublisher`, `@EventListener` và `SimpleApplicationEventMulticaster` **không cung cấp dead-letter queue bền vững tự động**. Với event chỉ tồn tại trong JVM, một “DLQ nội bộ” là **cơ chế do ứng dụng tự thiết kế**, chẳng hạn bảng database, queue bền vững, hoặc store tạm trong bộ nhớ để phát triển. Nó **không giống** một DLQ của Kafka/RabbitMQ hay một message broker.

Bài học giúp bạn:

- Hiểu dead-letter cho event nội bộ là gì và vì sao không phải lỗi listener nào cũng nên dead-letter.
- Phân biệt exception truyền về publisher, `ErrorHandler` của multicaster, async executor, retry, dead-letter, transactional event và outbox.
- Thiết kế vòng đời xử lý có **retry giới hạn**, phân loại transient/permanent, lưu metadata đủ để chẩn đoán, replay có idempotency.
- Triển khai một ví dụ Java 17+ với Spring Framework thuần, có hai lỗi cố ý, dead-letter store tạm trong bộ nhớ và thao tác replay.
- Chọn lưu trữ bền vững, đảm bảo transaction và xây dựng quy trình vận hành/giám sát cho production.
- Kiểm thử những tình huống quan trọng: lỗi tạm thời, lỗi vĩnh viễn, duplicate, restart, rollback và phát lại.

Phạm vi là **Spring Framework Application Events trong cùng ứng dụng**. Những phần nói đến broker/outbox là so sánh và hướng nâng cấp khi có yêu cầu độ bền.

## 2. Những điều Spring làm sẵn và không làm sẵn

### 2.1. Đường đi mặc định của event

~~~text
ApplicationEventPublisher.publishEvent(event)
               |
               v
ApplicationEventMulticaster
               |
               +--> @EventListener handler A
               |
               +--> @EventListener handler B
               |
               +--> @EventListener handler C
~~~

Với `SimpleApplicationEventMulticaster` mặc định, các listener thông thường chạy **đồng bộ trên thread gọi publish**. Khi listener ném exception không được xử lý và multicaster không được cấu hình `ErrorHandler`, exception có thể dừng lượt phân phối hiện tại và **truyền về publisher**.

Khi cấu hình một `TaskExecutor`, các listener có hỗ trợ async ở cấp multicaster được giao cho executor; exception có thể xảy ra trên worker thread, **không tự xuất hiện trong stack của publisher**. `@Async` trên listener cũng có những đường xử lý exception riêng. Transaction-synchronized listener có thể yêu cầu giữ đăng ký trên thread gốc; đừng giả định mọi listener đều chạy async chỉ vì multicaster có executor.

Spring cung cấp các điểm mở rộng:

- `SimpleApplicationEventMulticaster#setErrorHandler(ErrorHandler)`: xử lý `Throwable` do listener phát sinh; nếu handler **nuốt lỗi**, publisher có thể tiếp tục, nhưng dữ liệu sự kiện và identity của listener không tự được truyền đầy đủ cho error handler.
- `SimpleApplicationEventMulticaster#setTaskExecutor(...)`: chọn cách thực thi cho listener đủ điều kiện.
- `@EventListener` / `ApplicationListener<T>`: viết logic nhận event, có thể tự gọi một service có retry/dead-letter.
- `@TransactionalEventListener`: gắn callback với phase của một transaction, ví dụ `AFTER_COMMIT`.

Các API trên **không đồng nghĩa với**: “Spring tự lưu event thất bại vào hàng đợi có thể replay sau restart”. Muốn như vậy phải thiết kế storage, transaction boundary, delivery worker, chính sách retry và quan sát trạng thái.

### 2.2. Dead-letter khác error logging

Một log như “notification failed” giúp chẩn đoán nhưng có thể thiếu dữ liệu để xử lý lại. Một dead-letter record có cấu trúc thường lưu **event identity, handler identity, payload hoặc reference tối thiểu, nguyên nhân lỗi đã làm sạch, số lần thử, trạng thái, thời điểm và version**.

| Khái niệm | Ý nghĩa | Đảm bảo mặc định |
| --- | --- | --- |
| Log lỗi | Dòng ghi chẩn đoán | Không phải bản ghi có thể replay |
| `ErrorHandler` của multicaster | Nhận lỗi từ listener | Không tự lưu event hoặc retry |
| Retry | Thử lại tác vụ sau lỗi | Có thể lặp side effect nếu thiếu idempotency |
| Dead-letter store | Nơi giữ công việc thất bại cuối cùng để xử lý sau | Độ bền tùy implementation |
| Message broker DLQ | Queue/topic cho message không xử lý được | Tùy broker và cấu hình; không phải Spring in-process mặc định |
| Transactional outbox | Ghi công việc cần phát cùng transaction nghiệp vụ | Cần worker giao nhận và idempotency consumer |

**Định nghĩa thực dụng:** Một sự kiện được “dead-letter” khi hệ thống **cố ý ngừng tự động xử lý event/handler đó theo chính sách hiện hành**, lưu đủ thông tin để điều tra và tùy chọn replay. Nó không phải một trạng thái `TransactionPhase` có sẵn của Spring.

## 3. Vì sao listener thất bại?

Một event thường có nhiều listener với mục tiêu khác nhau. Ví dụ `PaymentCaptured` có listener gửi email, ghi metrics và đồng bộ CRM. Nếu CRM tạm ngừng, có thể không cần rollback giao dịch thanh toán, nhưng cần lưu công việc đồng bộ CRM để xử lý sau. Ngược lại, nếu một kiểm tra **bắt buộc** phải thành công trước khi nghiệp vụ được chấp nhận, việc nuốt exception rồi đưa vào DLQ có thể làm commit dữ liệu sai.

Phân loại lỗi giúp chọn chính sách:

| Loại lỗi | Ví dụ | Chính sách phù hợp |
| --- | --- | --- |
| **Transient** | Timeout, HTTP 503, network reset, tài nguyên tạm khóa | Retry có giới hạn, backoff/jitter; nếu hết hạn mức thì dead-letter |
| **Rate limit** | HTTP 429, quota ngắn hạn | Tôn trọng `Retry-After`, rate limit và backoff; không retry đồng loạt |
| **Permanent / non-retryable** | Schema không hợp lệ, email sai định dạng, thiếu trường bắt buộc | Dead-letter sớm hoặc từ chối tại validation, cần sửa dữ liệu/code |
| **Lỗi quyền/cấu hình** | Sai credential, ACL, endpoint | Có thể gây lỗi diện rộng; điều tra cấu hình, tạm dừng consumer, không vòng lặp vô hạn |
| **Duplicate** | Event được xử lý lại sau crash hoặc replay | Idempotency, dedup key, unique constraint |
| **Mất dependency** | Database hoặc service nền tảng tê liệt | Circuit breaker/bulkhead, ngừng nhận thêm khi quá tải, cảnh báo vận hành |
| **Lỗi lập trình** | `NullPointerException` bất thường, invariant bị phá | Điều tra và sửa; tránh tự retry vô nghĩa |
| **Lỗi hạ tầng ở storage DLQ** | Không ghi được dead-letter | Phải có chính sách fallback rõ, không được báo đã lưu thành công |

**Không catch `Throwable` một cách tràn lan** để đưa mọi lỗi vào DLQ. Những lỗi nghiêm trọng như `OutOfMemoryError` không nên bị che giấu như một lần retry nghiệp vụ bình thường. Nên catch các exception phù hợp và phân loại dựa trên contract của dependency.

## 4. Chọn đơn vị thất bại: event hay event–listener?

Một event có thể được phân phối cho nhiều handler. Nếu chỉ lưu `eventId` rồi replay bằng cách `publishEvent(event)` lại, **tất cả listener** có thể nhận thêm một lần:

~~~text
OrderPaid(eventId = e-42)
          |
          +--> metrics listener: SUCCESS
          +--> email listener: FAILED
          +--> loyalty listener: SUCCESS
~~~

Khi email thất bại, replay toàn bộ event có thể chạy metrics và loyalty lần hai. Vì vậy, ở nhiều ứng dụng, đơn vị công việc cần dead-letter là:

**`(eventId, handlerId)`**, không chỉ `eventId`.

Ví dụ:

~~~text
dead-letter key = ("evt-42", "send-receipt-email")
status          = DEAD
attempts        = 5
lastError       = "SMTP_UNAVAILABLE"
~~~

Các listener khác vẫn có trạng thái thành công và không cần chạy lại. Nếu muốn replay qua publisher toàn cục, **mọi listener nhận event phải idempotent** và có cơ chế bỏ qua event đã xử lý. Đối với hệ thống có nhiều subscriber độc lập, thiết kế bảng delivery/handler state giúp tránh replay trùng.

Cần thêm `eventType` và `schemaVersion` để xử lý đúng sau khi code triển khai phiên bản mới. Khi payload thay đổi, chương trình replay phải có cách đọc event cũ hoặc migration an toàn.

## 5. Vòng đời trạng thái dead-letter được đề xuất

Một workflow production có thể mô hình hóa:

~~~text
NEW / READY
     |
     v
PROCESSING --- success ---> SUCCEEDED / ACKED
     |
     +--- transient failure ---> RETRY_WAIT
     |                            |
     |                     delay / backoff
     |                            |
     |                            +----> PROCESSING
     |
     +--- permanent failure ---------------------\
     |                                            |
     +--- retry budget exhausted ----------------> DEAD
                                                  |
                                             investigate
                                                  |
                                     operator approves replay
                                                  |
                                               REPLAYING
                                                  |
                              success ------------+----> RESOLVED
                              failure -----------------> DEAD
~~~

Đây là **thiết kế mẫu**, không phải state machine Spring tự tạo. Tên trạng thái cần được dự án thống nhất.

Một số nguyên tắc:

1. **Retry budget rõ ràng:** số lần thử tối đa hoặc giới hạn thời gian; không lặp vô hạn.
2. **Backoff:** tránh bắn request liên tục khi dependency đang lỗi; có thể dùng exponential backoff và jitter để tránh thundering herd.
3. **Phân loại:** lỗi dữ liệu vĩnh viễn không nên lặp 20 lần như timeout.
4. **Dead-letter phải được xác nhận lưu:** chỉ thông báo “đã dead-letter” khi store trả success; nếu store mất, không giả định công việc an toàn.
5. **Replay có kiểm soát:** thao tác phải có quyền, trace và idempotency; sửa nguyên nhân gốc trước khi phát lại.
6. **Retention:** quy định TTL/lưu trữ và quyền xóa, tránh giữ PII quá lâu.
7. **Phục hồi crash:** nếu tiến trình chết giữa xử lý và cập nhật trạng thái, cần lease/claim timeout và cơ chế tìm công việc bị bỏ dở.

Chọn tiêu chí thành công ở **từng handler**. “Publisher hoàn thành” không tương đương “mọi tác vụ phụ đã thực sự được lưu và xử lý”, nhất là khi có async.

## 6. Mẫu thiết kế dữ liệu cho dead-letter store

Một schema tham khảo với PostgreSQL (không phải schema bắt buộc của Spring):

~~~sql
CREATE TABLE internal_event_dead_letter (
    id                  UUID PRIMARY KEY,
    event_id            VARCHAR(120) NOT NULL,
    handler_id          VARCHAR(120) NOT NULL,
    event_type          VARCHAR(180) NOT NULL,
    schema_version      INTEGER NOT NULL,
    payload_json        JSONB NOT NULL,
    failure_kind        VARCHAR(32) NOT NULL,
    last_error_code     VARCHAR(120),
    last_error_summary  TEXT,
    attempts            INTEGER NOT NULL,
    first_failed_at     TIMESTAMPTZ NOT NULL,
    last_failed_at      TIMESTAMPTZ NOT NULL,
    next_attempt_at     TIMESTAMPTZ,
    status              VARCHAR(32) NOT NULL,
    CONSTRAINT uq_internal_dlq_delivery
        UNIQUE (event_id, handler_id)
);
~~~

**Giải thích lựa chọn trường:**

- `event_id` định danh logic event, tạo từ lúc publish; không tạo lại mỗi lần retry.
- `handler_id` phân biệt các subscriber/handler có nhu cầu replay khác nhau.
- `event_type` và `schema_version` hỗ trợ deserialize và chuyển đổi event cũ.
- `payload_json` là **payload tối thiểu, có kiểm soát schema**, không nhét cả JPA entity, request, stream, secret hoặc stacktrace.
- `failure_kind` phân loại transient/permanent; `last_error_code` và `last_error_summary` là thông tin đã được vệ sinh, tránh leak PII.
- `attempts` là tổng số lần thử; `first_failed_at`, `last_failed_at` hỗ trợ vận hành và SLA.
- `next_attempt_at` phục vụ scheduler; `status` phân biệt đang retry, dead hay đã resolve.
- Unique key theo `(event_id, handler_id)` ngăn tạo nhiều dead-letter record cho cùng một delivery. Tùy semantics, cần thêm `tenant_id`, partition key hoặc consumer version trong unique key.

Nếu xử lý đa instance, cần kiểm soát **đồng thời**: worker claim record theo lease/lock, dùng optimistic locking/version hoặc `SELECT ... FOR UPDATE SKIP LOCKED` trên PostgreSQL trong transaction claim ngắn. Không dựa vào một `ConcurrentHashMap` dùng chung trong một JVM làm durable queue.

Nếu payload quá nhạy cảm hoặc quá lớn, lưu **ID + metadata đã được chấp thuận** và dùng một snapshot/reference có quyền truy cập riêng; phải xét rằng dữ liệu được tham chiếu có thể thay đổi hoặc bị xóa trước lúc replay.

## 7. Ví dụ Java 17+ chạy được: dead-letter tạm trong bộ nhớ

Ví dụ này chỉ dùng **Spring Framework thuần**, không cần Spring Boot, HTTP server hay database. Mục đích là minh họa **retry có giới hạn, phân loại lỗi, lưu event/handler thất bại và replay riêng handler**.

Một Spring event `OrderPaid` được listener xử lý:

- Đơn hàng **101**: gửi thông báo thành công ngay.
- Đơn hàng **202**: downstream bị ngắt tạm thời; thử hai lần, sau đó đưa vào dead-letter; khi downstream được sửa, replay thành công.
- Đơn hàng **303**: địa chỉ không hợp lệ; coi là lỗi vĩnh viễn, dead-letter ngay và **không replay mù**.

Code có output ổn định vì xử lý đồng bộ, không phụ thuộc scheduler và không dùng `Thread.sleep`. **In-memory store mất dữ liệu khi JVM tắt**; không được dùng như production DLQ.

### 7.1. Cấu trúc dự án

~~~text
internal-dead-letter-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── InternalDeadLetterDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'internal-dead-letter-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
}

application {
    mainClass = 'demo.InternalDeadLetterDemo'
}
~~~

JDK 17+ và Gradle phù hợp là đủ để chạy demo. Spring Framework 6.2.x có baseline Java 17. Khi dùng Spring Boot thực tế, nên để Boot dependency management quản lý phiên bản Spring.

### 7.2. Mã nguồn hoàn chỉnh

Lưu toàn bộ mã vào `src/main/java/demo/InternalDeadLetterDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class InternalDeadLetterDemo {

    // Payload nhỏ và ổn định; eventId được giữ nguyên khi replay.
    public record OrderPaid(String eventId, long orderId) {}

    public record DeadLetter(
            OrderPaid event,
            String handlerId,
            int attempts,
            String failureKind,
            String reason) {}

    public static final class TemporaryFailure extends RuntimeException {
        public TemporaryFailure(String message) {
            super(message);
        }
    }

    public static final class PermanentFailure extends RuntimeException {
        public PermanentFailure(String message) {
            super(message);
        }
    }

    // Mô phỏng downstream. Không phải một SMTP/API client thực.
    public static final class DeliveryGateway {
        private boolean recovered = false;

        public void send(OrderPaid event) {
            if (event.orderId() == 202L && !recovered) {
                throw new TemporaryFailure("service unavailable");
            }
            if (event.orderId() == 303L) {
                throw new PermanentFailure("invalid destination");
            }
        }

        public void recover() {
            recovered = true;
        }
    }

    // Chỉ phục vụ demo đồng bộ một thread: không durable, không concurrent.
    public static final class InMemoryDeadLetterStore {
        private final Map<String, DeadLetter> records =
                new LinkedHashMap<>();

        private String key(String eventId, String handlerId) {
            return eventId + "|" + handlerId;
        }

        public void save(DeadLetter letter) {
            records.put(key(
                    letter.event().eventId(),
                    letter.handlerId()), letter);
        }

        public DeadLetter find(String eventId, String handlerId) {
            return records.get(key(eventId, handlerId));
        }

        public void delete(String eventId, String handlerId) {
            records.remove(key(eventId, handlerId));
        }

        public int size() {
            return records.size();
        }

        public List<String> remainingEventIds() {
            List<String> ids = new ArrayList<>();
            for (DeadLetter letter : records.values()) {
                ids.add(letter.event().eventId());
            }
            return ids;
        }
    }

    public static final class NotificationListener {
        private static final int MAX_ATTEMPTS_PER_RUN = 2;
        private static final String HANDLER_ID = "send-receipt";

        private final DeliveryGateway gateway;
        private final InMemoryDeadLetterStore store;

        public NotificationListener(
                DeliveryGateway gateway,
                InMemoryDeadLetterStore store) {
            this.gateway = gateway;
            this.store = store;
        }

        @EventListener
        public void onOrderPaid(OrderPaid event) {
            deliver(event, 0);
        }

        // Trong demo, replay trực tiếp handler thất bại,
        // không republish cho tất cả listeners.
        public void replay(String eventId) {
            DeadLetter letter = store.find(eventId, HANDLER_ID);
            if (letter == null) {
                throw new IllegalArgumentException(
                        "No dead letter for " + eventId);
            }
            deliver(letter.event(), letter.attempts());
        }

        private void deliver(OrderPaid event, int previousAttempts) {
            for (int localAttempt = 1;
                    localAttempt <= MAX_ATTEMPTS_PER_RUN;
                    localAttempt++) {

                int totalAttempt = previousAttempts + localAttempt;

                try {
                    gateway.send(event);
                    store.delete(event.eventId(), HANDLER_ID);
                    System.out.println(
                            "delivered order=" + event.orderId()
                            + " attempt=" + totalAttempt);
                    return;

                } catch (PermanentFailure ex) {
                    store.save(new DeadLetter(
                            event,
                            HANDLER_ID,
                            totalAttempt,
                            "PERMANENT",
                            ex.getMessage()));

                    System.out.println(
                            "dead-letter order=" + event.orderId()
                            + " attempts=" + totalAttempt
                            + " kind=PERMANENT");
                    return;

                } catch (TemporaryFailure ex) {
                    if (localAttempt == MAX_ATTEMPTS_PER_RUN) {
                        store.save(new DeadLetter(
                                event,
                                HANDLER_ID,
                                totalAttempt,
                                "TRANSIENT",
                                ex.getMessage()));

                        System.out.println(
                                "dead-letter order=" + event.orderId()
                                + " attempts=" + totalAttempt
                                + " kind=TRANSIENT");
                        return;
                    }
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public DeliveryGateway deliveryGateway() {
            return new DeliveryGateway();
        }

        @Bean
        public InMemoryDeadLetterStore deadLetterStore() {
            return new InMemoryDeadLetterStore();
        }

        @Bean
        public NotificationListener notificationListener(
                DeliveryGateway gateway,
                InMemoryDeadLetterStore store) {
            return new NotificationListener(gateway, store);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            NotificationListener listener =
                    context.getBean(NotificationListener.class);
            InMemoryDeadLetterStore deadLetters =
                    context.getBean(InMemoryDeadLetterStore.class);
            DeliveryGateway downstream =
                    context.getBean(DeliveryGateway.class);

            context.publishEvent(new OrderPaid("evt-101", 101L));
            context.publishEvent(new OrderPaid("evt-202", 202L));
            context.publishEvent(new OrderPaid("evt-303", 303L));

            System.out.println("dead-letter count=" + deadLetters.size());

            // Giả lập đã sửa lỗi downstream và chủ động replay evt-202.
            downstream.recover();
            listener.replay("evt-202");

            System.out.println(
                    "after replay count=" + deadLetters.size());
            System.out.println(
                    "remaining=" + deadLetters.remainingEventIds());
        }
    }
}
~~~

### 7.3. Chạy và kết quả chính xác của chương trình

Trong thư mục `internal-dead-letter-demo`, với JDK 17+ và Gradle đã cài:

~~~bash
gradle -q run
~~~

Hoặc dùng wrapper đã được tạo sẵn: `./gradlew -q run` trên Linux/macOS, `gradlew.bat -q run` trên Windows.

Các dòng do ứng dụng tự in ra:

~~~text
delivered order=101 attempt=1
dead-letter order=202 attempts=2 kind=TRANSIENT
dead-letter order=303 attempts=1 kind=PERMANENT
dead-letter count=2
delivered order=202 attempt=3
after replay count=1
remaining=[evt-303]
~~~

**Diễn giải:**

1. `evt-101` được gửi thành công ở lần đầu. Nó không vào dead-letter.
2. `evt-202` ném `TemporaryFailure` hai lần; sau lần thứ hai, listener lưu record có `eventId=evt-202`, `handlerId=send-receipt`, `attempts=2` và `failureKind=TRANSIENT`.
3. `evt-303` ném `PermanentFailure` ngay lần đầu và được dead-letter với `attempts=1`. Không thử lại vì cùng input chắc chắn còn sai theo mô phỏng.
4. Trước replay store có hai record. Sau `downstream.recover()`, lệnh `listener.replay("evt-202")` lấy lại event cũ và thử lần thứ ba (tổng attempt=3), thành công rồi xóa record.
5. Còn đúng một dead-letter `evt-303`. Trường hợp này cần sửa dữ liệu/đích nhận trước khi replay.

**Ranh giới demo:** code cố tình **không có backoff, database transaction, thread pool, distributed lock, storage bền vững, consumer checkpoint, idempotency marker hoặc API vận hành**. Vì mọi xử lý đồng bộ trong `main` và chỉ chạy một JVM, `LinkedHashMap` là đủ để minh họa trạng thái. Trong production cần thay các phần đó, không sao chép nguyên demo để nhận trách nhiệm đảm bảo giao hàng.

## 8. Điều chỉnh mẫu cho ứng dụng thật: tách delivery khỏi publisher

Một thiết kế dễ kiểm thử thường gồm các thành phần:

~~~text
Domain service
   |
   +--> publish event nhỏ (eventId, aggregateId, type, version)
            |
            +--> Spring listener / adapter
                        |
                        +--> Delivery service
                                |
                                +--> attempt handler
                                +--> classify exception
                                +--> persist retry/dead-letter state
                                +--> metrics / logs
                                |
                                +--> replay worker / operator
~~~

Tách `NotificationListener` khỏi `DeliveryService` giúp handler không ôm trách nhiệm retry, persistence, metrics và authorization. Listener chỉ chuyển event đúng loại tới delivery workflow, còn delivery workflow có thể được chạy lại từ scheduler **mà không republish event cho tất cả subscriber**.

Trong sản phẩm thực, transaction và persistence nên được thiết kế trước khi chọn API retry:

- Nếu event không quan trọng và best-effort là đủ, có thể dùng Spring event đồng bộ/async kèm log/metric, chấp nhận khả năng mất công việc.
- Nếu event quan trọng nhưng còn nằm trong process, có thể ghi **delivery job bền vững** tại nguồn phát, rồi dùng worker đọc và xử lý.
- Nếu event phải qua dịch vụ khác, cân nhắc **transactional outbox + message broker** (hoặc một queue bền vững khác), thay vì dựa vào callback in-memory.
- Dead-letter bền vững không chỉ là “một list các event lỗi”: nó phải hỗ trợ claim, attempt count, schedule, replay, audit, retention và giao dịch với dữ liệu nguồn.

Một bảng dead-letter có thể là một phần của cùng delivery-job table với state `DEAD`; không bắt buộc luôn phải có queue vật lý riêng nếu hợp đồng đã rõ.

## 9. Retry đúng cách trước khi dead-letter

### 9.1. Retry ngay trong listener: chỉ phù hợp trường hợp nhỏ

Ví dụ ở mục 7 thử liên tục hai lần để giữ output xác định. Đây **không phải policy khuyến nghị** cho network failure production, vì hai lần thử sát nhau thường thất bại giống nhau và chặn publisher.

Nếu listener đồng bộ:

- Retry inline làm `publishEvent(...)` trả về chậm hơn.
- Nếu publisher đang trong transaction, retry kéo dài thời gian giữ lock/connection.
- Nếu callback tiếp tục ném exception, publisher có thể nhận lỗi, có thể ảnh hưởng transaction tùy call stack.
- Khi một dependency đang ngừng hoạt động, nhiều request đồng thời retry có thể làm quá tải nghiêm trọng hơn.

Vì vậy, khi cần backoff nhiều giây/phút, nên **lưu work item và để scheduler/worker riêng** xử lý; không `Thread.sleep` bên trong listener.

### 9.2. Backoff, jitter và phân loại

Một policy minh họa:

~~~text
Transient error:
    attempt 1 -> wait 5 seconds + jitter
    attempt 2 -> wait 15 seconds + jitter
    attempt 3 -> wait 45 seconds + jitter
    attempt 4 -> wait 2 minutes + jitter
    attempt 5 -> DEAD

Permanent validation error:
    attempt 1 -> DEAD

Rate limit:
    follow Retry-After when valid,
    otherwise use bounded backoff with rate limiter
~~~

Các con số là **ví dụ chính sách**, không phải default của Spring. Thực tế phải dựa trên SLA, tính chất dependency, timeout, throughput và thời gian event còn giá trị.

Tránh dùng một retry loop cho mọi exception. Chẳng hạn, lỗi invalid email không hết bằng chờ 30 giây, còn HTTP 503 không có nghĩa message cần bị bỏ ngay.

### 9.3. Không quên attempt budget khi replay

Phân biệt:

- `deliveryAttempts`: số lần thực tế đã gọi dependency.
- `retryCycles`: số lượt worker thức dậy.
- `replayAttempts`: số lần vận hành chủ động cho retry từ trạng thái DEAD.

Demo giữ `attempts` cộng dồn. Production có thể bổ sung lịch sử attempts thay vì chỉ một bộ đếm, nhưng phải đặt trần để tránh log phình vô hạn. Không để replay vô điều kiện làm vòng lặp vĩnh viễn.

## 10. Đồng bộ, async và giới hạn của ErrorHandler

### 10.1. Đồng bộ mặc định: exception có thể tác động publisher

~~~java
@EventListener
public void onOrderPaid(OrderPaid event) {
    downstream.send(event);
}
~~~

Đây là phương thức minh họa; `OrderPaid` và `downstream` cần được định nghĩa. Nếu `downstream.send` ném runtime exception chưa được xử lý và multicaster dùng chế độ đồng bộ mặc định, exception có thể truyền ngược về `publishEvent`. Điều này **không phải dead-letter**: chỉ là exception propagation.

### 10.2. Cấu hình ErrorHandler trên multicaster

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

@Configuration
class EventConfig {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error -> {
            System.err.println(
                    "listener failed: "
                    + error.getClass().getSimpleName());
        });

        return multicaster;
    }
}
~~~

Đây là đoạn cấu hình minh họa, không thuộc chương trình mục 7. Tên bean phải là `applicationEventMulticaster` để context sử dụng làm multicaster.

**Không nên coi `setErrorHandler(...)` là DLQ hoàn chỉnh** vì callback `handleError(Throwable)` nhận lỗi, **không tự nhận một envelope chuẩn chứa event ID, handler ID, payload và delivery state**. Nếu chỉ log hoặc suppress, bạn có thể khiến publisher nghĩ xử lý đã xong trong khi side effect chưa được thực hiện. Nếu cần dead-letter, hãy lưu trong handler/workflow có đủ ngữ cảnh hoặc xây một adapter chuyên dụng.

### 10.3. Async executor

Nếu dùng `setTaskExecutor(...)`, listener đủ điều kiện có thể chạy trên thread khác. Các hệ quả:

- Publisher có thể trả về **trước khi listener hoàn tất**.
- Exception không tự trở về thread publisher; phải có cơ chế theo dõi handler/async failure riêng.
- Queue executor có thể giữ event/payload lâu, gây áp lực bộ nhớ.
- Transaction/security/logging ThreadLocal của publisher không tự động di chuyển.
- Transaction-synchronized listener có thể không hỗ trợ async ở cấp multicaster; Spring 6.1+ có `ApplicationListener.supportsAsyncExecution()` để thể hiện điều này.

Nếu yêu cầu delivery bền vững, executor trong JVM **không thay cho durable queue**. Tiến trình bị kill sau khi submit nhưng trước khi xử lý sẽ làm mất task trong memory queue.

## 11. Transaction, rollback và dead-letter: điểm dễ thiết kế sai nhất

### 11.1. Lỗi trong listener có thể rollback transaction nghiệp vụ

Giả sử:

~~~java
@Transactional
public void capturePayment(Payment payment) {
    paymentRepository.save(payment);
    publisher.publishEvent(
            new PaymentCaptured(payment.getId()));
}
~~~

Đây là đoạn minh họa cần `Payment`, repository, Spring proxy transaction và event type được định nghĩa.

Nếu listener `@EventListener` chạy đồng bộ ngay tại `publishEvent` và ném unchecked exception, ngoại lệ có thể khiến lời gọi service thoát ra, khiến interceptor `@Transactional` **đánh dấu rollback theo quy tắc áp dụng**.

Ngược lại, nếu listener catch tất cả lỗi, ghi log rồi nuốt exception, transaction có thể **tiếp tục commit**. Điều đó có thể đúng với notification không bắt buộc, nhưng rất nguy hiểm nếu listener đảm nhiệm một invariant bắt buộc.

**Câu hỏi thiết kế bắt buộc:** thất bại của handler này có cần hủy giao dịch nghiệp vụ không?

- Nếu **có**, giữ lỗi có nghĩa rõ để transaction rollback; dead-letter không được âm thầm thay đổi contract thành “commit dù kiểm tra thất bại”.
- Nếu **không**, tách side effect thứ cấp khỏi transaction nghiệp vụ, ghi công việc cần thực hiện bền vững và xử lý sau commit.

### 11.2. Ghi dead-letter cùng transaction đang rollback

Nếu listener ném lỗi làm transaction A rollback, và trước đó bạn ghi record DLQ bằng **chính transaction A**, record DLQ cũng có thể bị rollback. Vì thế dòng log “saved to DLQ” không phải bằng chứng dead-letter đã bền vững.

Các lựa chọn phải xét:

1. Ghi DLQ trong **transaction độc lập** (ví dụ với `REQUIRES_NEW` qua proxy Spring) khi thực sự cần lưu thất bại mà transaction nguồn rollback. Nhưng không được vô tình ghi “event cần gửi” cho nghiệp vụ chưa từng commit.
2. Dùng một worker/outbox độc lập: transaction nghiệp vụ commit công việc cần làm, sau đó retry/dead-letter diễn ra ở transaction xử lý khác.
3. Nếu nghiệp vụ rollback và không còn đối tượng hợp lệ, có thể chỉ cần audit/log lỗi thay vì dead-letter tác vụ không nên tiếp tục.

Trong nhiều trường hợp, **transactional outbox** là cấu trúc sáng sủa nhất: cùng transaction lưu business entity và một outbox work item, worker chỉ nhìn thấy outbox record đã commit. Sau đó worker tự quản lý retries/dead-letter. Khi business rollback, **không có outbox record hợp lệ để phát**.

### 11.3. AFTER_COMMIT không phải phép màu

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(PaymentCaptured event) {
    downstream.call(event);
}
~~~

Đoạn này chỉ chạy khi có transaction phù hợp đã commit thành công; với `fallbackExecution=false` mặc định, event ngoài transaction bị bỏ qua. Vì callback ở phase sau commit, lỗi sau đó **không thể tự rollback commit đã xảy ra**. Nhưng application event vẫn **không phải durable queue**: nếu process chết sau commit, trước hoặc trong callback, công việc có thể mất mà không có record để replay.

Với thao tác cần ghi DB ở listener AFTER_COMMIT, không giả định tài nguyên transaction cũ sẽ commit các thay đổi mới. Cần một transaction mới phù hợp hoặc một worker chuyên dụng.

### 11.4. Không nhầm “lưu lỗi” với “bảo đảm không mất sự kiện”

Một lỗi có thể xuất hiện ở nhiều cửa sổ thời gian:

~~~text
T1: business commit
T2: listener được gọi
T3: downstream xử lý thành công
T4: ghi ACK / xóa delivery record
~~~

Ứng dụng có thể crash **giữa bất kỳ hai mốc nào**. Nếu không có durable work item **trước T1 hoặc đồng thời T1**, chỉ thêm logic catch exception ở T2 không giải quyết khoảng trống crash trước T2. Nếu crash sau T3 nhưng trước T4, retry có thể **gây xử lý trùng**. Bởi vậy, production thường cần **at-least-once delivery + idempotent consumer**, không hứa exactly-once end-to-end từ Spring event nội bộ.

## 12. Thiết kế replay an toàn

Replay là một hành động **có tác dụng nghiệp vụ**, không chỉ nút “thử lại”. Một quy trình có thể gồm:

1. Lọc dead-letter theo `handlerId`, thời gian, loại lỗi và trạng thái. Không replay hàng loạt không giới hạn.
2. Điều tra nguyên nhân, khắc phục cấu hình/nguồn dữ liệu và đánh giá xem event cũ còn hợp lệ.
3. Kiểm tra `eventType`/`schemaVersion` có tương thích với code hiện tại; upcast/migrate nếu cần.
4. Claim record bằng optimistic lock/lease để hai operator không replay đồng thời.
5. Chuyển sang `REPLAYING` hoặc `RETRY_WAIT` với idempotency key gốc.
6. Xử lý **đúng handler thất bại**; nếu republish toàn bộ event thì các handler khác phải idempotent.
7. Ghi kết quả success/failure và audit ai thực hiện, khi nào, vì sao; phân biệt “retry đã gửi” với “side effect thành công”.
8. Nếu vẫn lỗi, cập nhật attempts và quay lại `DEAD` theo chính sách; không xóa dữ liệu lỗi chỉ vì đã bấm replay.

### 12.1. Idempotency

Event có thể bị xử lý hơn một lần do retry hoặc crash. Một consumer gửi email, tạo hóa đơn hoặc cộng điểm phải có cách phát hiện sự kiện đã hoàn tất:

~~~text
idempotency key = eventId + ":" + handlerId

if delivery already SUCCEEDED:
    skip work
else:
    claim and process
    record success durably
~~~

Đây là pseudo-workflow; việc check rồi insert riêng rẽ **chưa đủ an toàn khi có nhiều worker**. Dùng unique constraint hoặc thao tác atomically claim/insert, và cân nhắc transaction của side effect.

Với REST bên ngoài, gửi idempotency key nếu API hỗ trợ. Nếu API không hỗ trợ và thành công rồi bị crash trước khi lưu ACK, replay có thể tạo side effect trùng; phải thiết kế biện pháp đối soát, không thể đơn giản tuyên bố exactly-once.

### 12.2. Không replay poison event liên tục

Permanent failure như schema invalid, customer bị xóa vĩnh viễn hoặc thiếu quyền kéo dài cần **sửa nguyên nhân**. Nếu không, replay chỉ nhân thêm số lỗi, tiêu tốn quota và che mất vấn đề thực sự.

### 12.3. Quan hệ với quyền truy cập và dữ liệu nhạy cảm

Một DLQ thường chứa dữ liệu lỗi có độ nhạy cao hơn log bình thường. Cần RBAC cho người xem/replay/delete, redaction của error message, mã hóa lưu trữ khi cần, audit trail, policy retention và quy trình xử lý dữ liệu cá nhân. **Không lưu stacktrace đầy đủ với token/request body** trong `last_error_summary`.

## 13. Production implementation: worker, claim và xử lý kết quả

Một worker dùng database có thể xử lý theo chu kỳ:

~~~text
repeat while running:
    claim a bounded batch of due READY/RETRY_WAIT records
    for each claimed job:
        reconstruct versioned event payload
        locate handler by handlerId
        if already processed:
            mark ACKED
        else:
            try side effect with timeout and idempotency key
            on success: durable ACK
            on transient failure: schedule backoff or mark DEAD
            on permanent failure: mark DEAD
    renew/release stale leases and emit metrics
~~~

Những lưu ý thực thi:

- **Claim transaction nên ngắn**: không giữ DB lock trong lúc gọi HTTP mất 20 giây.
- **Lease có timeout**: worker chết không làm job mắc kẹt `PROCESSING` mãi.
- **Bộ nhớ bị chặn trần**: giới hạn batch, queue, concurrency và payload size.
- **Deadline và backoff**: không retry vô hạn khi dependency chết.
- **Dedupe**: dùng unique key trên event-handler; xử lý duplicate và replay an toàn.
- **State transition atomic**: update status và attempt count cùng một transaction DB.
- **Xử lý DLQ storage failure**: nếu không thể lưu thất bại, phải báo trạng thái không xác nhận và cảnh báo; không xóa work item trước khi persistence thành công.
- **Kill/restart test**: khởi động lại worker và kiểm tra job chờ được tiếp tục.

Để đơn giản hóa, có thể dùng thư viện hỗ trợ retry, scheduler, Spring Batch, Spring Integration hoặc message broker **khi phù hợp**. Nhưng đừng nhầm feature của một thư viện với khả năng tự động có trong `ApplicationEventPublisher`.

## 14. Cần dùng Spring Integration hoặc broker khi nào?

**Spring Integration** có các khái niệm message channel, error channel và luồng xử lý message; nếu application đã tổ chức event thành integration flow, có thể dùng error-handling flow để chuyển failed message tới một kênh xử lý riêng. Đây là một **kiến trúc khác với** Spring ApplicationEventMulticaster thuần.

**Kafka/RabbitMQ** có retry topic/queue, DLT/DLQ hoặc dead-letter exchange theo tính năng và cấu hình tương ứng. Khi ứng dụng publish event ra broker qua outbox hoặc adapter, broker-side dead lettering là trách nhiệm của **consumer và hạ tầng broker**, không phải một tác dụng phụ tự nhiên của `@EventListener`.

Gợi ý lựa chọn:

| Quy mô/yêu cầu | Cách phù hợp |
| --- | --- |
| Event chỉ dùng cho logging/metrics best-effort | Spring event thông thường, log/metrics có giám sát; chấp nhận mất một số event |
| Side effect phụ nhưng cần retry trong cùng ứng dụng, số lượng vừa | Persisted job table + scheduler/worker + dead-letter state |
| Cần bảo đảm công việc được ghi cùng business transaction | Transactional outbox + worker |
| Nhiều service cần subscribe, replay và retention | Broker với delivery/retry/DLQ được cấu hình, cùng idempotent consumer |
| Luồng integration channels phức tạp trong một ứng dụng | Spring Integration/error channel, storage theo yêu cầu độ bền |

Không bắt buộc triển khai Kafka chỉ để có thuật ngữ “dead letter”. Ngược lại, nếu mất event là rủi ro kinh doanh nghiêm trọng, **một `ArrayList` hay executor queue trong process không đủ**.

## 15. Kiểm thử dead-letter trong event nội bộ

Một bộ test đáng tin nên đi qua đường phát event thật của Spring và xác nhận store:

| Test case | Dữ liệu vào | Điều cần assert |
| --- | --- | --- |
| Thành công | Event hợp lệ, downstream hoạt động | Handler chạy một lần, không có dead-letter |
| Lỗi transient | Downstream thất bại có thể phục hồi | Retry theo policy; sau budget, có đúng một dead-letter với attempt count |
| Lỗi permanent | Payload sai vĩnh viễn | Không retry vô ích, dead-letter ngay |
| Replay sau khi sửa lỗi | Event đang DEAD, dependency đã phục hồi | Handler thành công, record chuyển RESOLVED/xóa theo policy |
| Replay trước khi sửa lỗi | Event vẫn không hợp lệ | Vẫn DEAD, ghi nhận lần thử, không mất record |
| Nhiều handler | Chỉ một handler thất bại | DLQ theo eventId+handlerId; không replay handler đã success |
| Duplicate event | Nhận lại cùng eventId+handlerId | Không phát side effect trùng; unique/idempotency có tác dụng |
| Worker crash | Chết giữa claim và ACK | Lease hết hạn và job được xử lý lại, không mất |
| DLQ database lỗi | Persist thất bại | Không báo lưu thành công, không ACK/xóa job sai |
| Transaction rollback | Business transaction không commit | Không có delivery job cho nghiệp vụ chưa commit, theo kiến trúc outbox |
| AFTER_COMMIT listener lỗi | Business đã commit | Không giả định rollback được business |
| Startup/restart | JVM tắt rồi bật | Dead-letter bền vững vẫn tồn tại nếu dùng persistent store |
| Security | Người không đủ quyền replay | Từ chối truy cập và ghi audit phù hợp |

### 15.1. Kiểm tra nhanh bằng output demo

Đối với ví dụ ở mục 7, các assertion tương ứng là:

~~~text
initial published evt-101 -> 0 DEAD for evt-101
evt-202 -> attempts=2, kind=TRANSIENT
evt-303 -> attempts=1, kind=PERMANENT
dead-letter count before replay = 2
replay evt-202 after recover -> delivered at attempt=3
dead-letter count after replay = 1
remaining eventId = evt-303
~~~

Đây là **bảng kỳ vọng**, không phải stdout đã đo bằng bộ test. Mã ví dụ in bảy dòng ở mục 7.3; ở dự án thực, nên dùng JUnit và assertion trên `InMemoryDeadLetterStore` hoặc persistent repository.

### 15.2. Test sai dễ cho kết quả PASS giả

- Gọi trực tiếp `NotificationListener.onOrderPaid(...)` rồi kết luận Spring event wiring đúng: cách này **không kiểm tra** bean discovery hoặc event multicaster.
- Kiểm tra chỉ có log `dead-letter` nhưng không đọc record đã lưu thành công.
- Gọi `Thread.sleep` để chờ async thay vì một tín hiệu hoàn tất có timeout.
- Chạy test trên `ConcurrentHashMap` rồi kết luận record tồn tại sau restart.
- Test retry mà không test duplicate và crash window.
- Test business rollback chỉ bằng việc mock exception, không kiểm tra trạng thái database.
- Dùng một worker/thread duy nhất rồi suy luận không có race condition khi chạy nhiều instance.

Với integration test, dùng datasource thực (có thể H2/Testcontainers tùy mức độ), publish trong transaction có kiểm soát, chờ worker hoàn tất, rồi kiểm tra state sau transaction và sau restart. Test nguồn ngoài như SMTP/HTTP qua stub có timeout và script lỗi dự đoán được.

## 16. Metrics, cảnh báo và runbook vận hành

Nếu đã xây DLQ nhưng không ai quan sát, hệ thống chỉ chuyển “mất việc” thành “tồn đọng im lặng”. Tối thiểu nên có:

**Metrics:**

- `dead_letter_total{handler,failure_kind}`: số dead-letter mới theo handler và loại lỗi.
- `dead_letter_backlog{handler,status}`: số record đang DEAD/RETRY_WAIT.
- `dead_letter_oldest_age_seconds`: thời gian chờ của record cũ nhất.
- `delivery_attempt_total{handler,outcome}` và tỷ lệ thành công sau retry.
- `delivery_latency_seconds`, queue lag, số worker active, số worker timeout.
- `replay_total{actor,outcome}` ở mức số lượng tổng hợp; không đưa email/ID cá nhân vào metric label.
- Số bản ghi `PROCESSING` quá hạn lease và số lần DB dead-letter persistence lỗi.

**Runbook:**

1. Nhận cảnh báo backlog/age vượt ngưỡng SLA; phân biệt sự cố diện rộng với một vài poison events.
2. Lọc theo handler, failure kind, deployment version và thời điểm bắt đầu.
3. Kiểm tra dependency, rate limit, schema/migration, secret/credential và các thay đổi vừa phát hành.
4. Cô lập handler hoặc giảm concurrency nếu retry đang làm dependency quá tải.
5. Sửa lỗi gốc, đánh giá liệu cần đổi event data/version hay khôi phục resource.
6. Replay **nhóm nhỏ** có kiểm soát, so số lượng success/duplicate/failed, rồi mới mở rộng.
7. Ghi lại nguyên nhân, tác động nghiệp vụ và quyết định xóa/giữ dead-letter theo retention policy.

Đối với lỗi liên quan thanh toán, giao vận hoặc gửi thông báo khách hàng, cần quy trình đối soát và có thể yêu cầu phê duyệt trước khi replay hàng loạt. Không xóa dead-letter chỉ để biểu đồ backlog về 0.

## 17. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| Spring Application Events có DLQ mặc định | Không; phải tự tạo workflow lưu/retry/replay hoặc dùng hạ tầng khác |
| `setErrorHandler(...)` tự lưu payload lỗi | Chỉ nhận `Throwable`; không có event+handler envelope chuẩn |
| Listener exception luôn được publisher nhận | Đồng bộ có thể truyền lỗi; async thì không có bảo đảm như vậy |
| Listener exception luôn làm rollback | Phụ thuộc transaction boundary và exception handling; AFTER_COMMIT không undo commit |
| Catch mọi exception rồi lưu DLQ luôn an toàn | Có thể che giấu invariant bắt buộc hoặc nuốt cả lỗi nghiêm trọng |
| `@TransactionalEventListener(AFTER_COMMIT)` bảo đảm delivery bền vững | Không; callback vẫn trong JVM và có cửa sổ crash |
| In-memory `Map` là DLQ production | Mất khi restart, thiếu claim/lease/RBAC và retention |
| Retry nhiều lần sẽ bảo đảm xử lý đúng một lần | Retry có thể tạo duplicate side effect; cần idempotency |
| Replay là `publishEvent` lại cho mọi listener | Có thể chạy lại các handler đã thành công |
| Ghi DLQ trong cùng transaction bị rollback sẽ vẫn còn | Record có thể rollback theo |
| Đủ log lỗi là có thể replay | Log có thể thiếu event identity, schema version và metadata cần thiết |
| DLQ broker và DLQ application là cùng một feature | Tính năng, persistence và trách nhiệm vận hành khác nhau |
| Chỉ số attempts tự giải quyết retry storm | Còn cần backoff, jitter, rate limit, concurrency control, circuit breaker |
| Có bảng dead-letter thì không bao giờ mất event | Cần atomically tạo work item trước crash window, xác nhận persist và thiết kế ACK |
| Ngắt job đang chạy và replay ngay là an toàn | Cần claim/lease/idempotency để tránh xử lý song song |

## 18. Bài tập thực hành

**Bài tập 1: Retry transient.** Trong demo, đổi giới hạn `MAX_ATTEMPTS_PER_RUN` từ 2 thành 3. Dự đoán output cho đơn hàng 202 và tổng số attempts khi replay thành công. Giải thích vì sao thêm một retry sát nhau chưa chắc nâng xác suất phục hồi của downstream.

**Bài tập 2: Poison event.** Sau lần publish `evt-303`, gọi `listener.replay("evt-303")` khi chưa sửa nguyên nhân. Kiểm tra record vẫn tồn tại và attempts tăng theo chính sách. Sau đó sửa gateway để hỗ trợ một thao tác “repair address” và replay lại có kiểm soát.

**Bài tập 3: Nhiều subscriber.** Thêm một listener ghi metrics luôn thành công. Tại sao dùng `context.publishEvent(event)` để replay event lỗi có thể ghi metrics thêm lần nữa? Viết logic dedupe hoặc replay riêng `handlerId`.

**Bài tập 4: Lưu bền vững.** Thay `InMemoryDeadLetterStore` bằng JDBC repository có unique constraint `(event_id, handler_id)`. Viết test đóng rồi mở lại Spring context, xác minh record vẫn còn và replay được.

**Bài tập 5: Transaction rollback.** Dùng `TransactionTemplate` tạo business transaction và một công việc cần xử lý. Cho business transaction ném lỗi trước commit; kiểm tra liệu DLQ/delivery record được tạo ra trong transaction đó có bị rollback hay không. Đề xuất outbox khi mục tiêu chỉ gửi event của giao dịch đã commit.

**Bài tập 6: Concurrent replay.** Mô phỏng hai worker cùng claim `evt-202`. Tạo cơ chế unique/delivery lock có TTL, đảm bảo chỉ một worker đang xử lý; kiểm tra điều gì xảy ra nếu worker chết sau side effect nhưng trước ACK.

**Bài tập 7: Runbook.** Giả lập 500 dead-letter của handler email với lỗi rate limit. Đặt chính sách cảnh báo, replay từng batch nhỏ, giới hạn concurrency, theo dõi thành công và phân loại trường hợp cần can thiệp thủ công.

## 19. Checklist trước khi đưa vào production

- [ ] Đã xác định listener nào là **critical** (lỗi cần rollback) và listener nào là **side effect thứ cấp**.
- [ ] Có định danh `eventId`, `handlerId` và version của payload; không dead-letter chỉ theo log message.
- [ ] Sự kiện được lưu bền vững **trước cửa sổ crash có thể làm mất việc** nếu delivery là yêu cầu nghiệp vụ.
- [ ] Có retry budget, phân loại lỗi, backoff/jitter, timeout và giới hạn concurrency.
- [ ] Có persistent store, unique constraint, state transition và claim/lease nếu xử lý nhiều instance.
- [ ] Đã làm rõ transaction boundary; DLQ không bị rollback ngoài ý muốn.
- [ ] Replay chỉ chạy handler thất bại, hoặc toàn bộ handler đã idempotent và có dedupe.
- [ ] Có xử lý duplicate, worker crash, DB lưu DLQ lỗi và dữ liệu quá hạn.
- [ ] Payload/stacktrace không chứa secret/PII không cần thiết; có RBAC, audit và retention.
- [ ] Có metrics cho backlog, age, attempts, outcome, error kind và cảnh báo có người chịu trách nhiệm.
- [ ] Có test commit/rollback/restart/replay với storage thật, không chỉ chạy in-memory demo.
- [ ] Không dùng Spring events trong JVM như một bảo đảm delivery xuyên restart khi chưa có hạ tầng bền vững.

## 20. Tài liệu tham khảo

- Spring Framework 6.2 Javadoc — `ApplicationEventPublisher`, hợp đồng phát event: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 Javadoc — `SimpleApplicationEventMulticaster`, `setErrorHandler` và `setTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Reference 6.2 — Application Events (`@EventListener`): https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Reference 6.2 — Transaction-bound Events và `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Reference — Transaction propagation và `REQUIRES_NEW`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html
- Spring Integration Reference — Error Handling, error channels: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring for Apache Kafka Reference — error handlers, dead-letter topics (là cơ chế riêng của Kafka listener): https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring AMQP Reference — RabbitMQ dead-letter exchange/error handling (là cơ chế riêng của Rabbit): https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/error-handling.html
