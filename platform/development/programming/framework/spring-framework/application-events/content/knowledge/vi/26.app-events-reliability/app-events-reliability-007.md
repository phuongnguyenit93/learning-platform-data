# Retry có giới hạn khi xử lý Spring Application Events

Một event có thể được publish thành công nhưng listener vẫn thất bại vì một **lỗi tạm thời**: kết nối mạng bị reset, dịch vụ downstream trả HTTP 503, database có deadlock, hoặc một tài nguyên ngắn hạn chưa sẵn sàng. Nếu ứng dụng **không retry**, công việc phụ có thể bị bỏ lỡ. Nếu ứng dụng **retry vô hạn**, một lỗi nhỏ có thể giữ request thread, làm đầy thread pool, tăng tải downstream và gây sự cố dây chuyền.

**Retry có giới hạn (bounded retry)** là chính sách cho phép **tối đa một số lần thử đã xác định**, chỉ retry những lỗi phù hợp, có backoff/timeout và một đường xử lý rõ ràng khi hết lượt. Với Spring Framework Application Events, điều quan trọng không chỉ là “thử lại bao nhiêu lần” mà còn là **thử lại ở đâu, trong transaction nào và làm gì với event khi mọi lần thử đều thất bại**.

Bài này tập trung vào `ApplicationEventPublisher`, `@EventListener`, `@TransactionalEventListener`, executor/async, và lựa chọn giữa **retry đồng bộ trong JVM**, **Spring Retry qua AOP**, **hàng đợi bền vững/Transactional Outbox**. Các chiến lược có phạm vi đảm bảo khác nhau, không thể hoán đổi tùy tiện.

## 1. Retry là một quyết định về nghiệp vụ và độ tin cậy

Ví dụ khi tạo đơn hàng, ứng dụng publish event `OrderPlaced`; listener gửi thông báo tới dịch vụ khác:

```text
OrderService
    |
    +-- save(order)
    |
    +-- publishEvent(OrderPlaced)
              |
              +-- NotificationListener
                      |
                      +-- attempt 1 -> 503 Service Unavailable
                      |
                      +-- backoff 100 ms
                      |
                      +-- attempt 2 -> timeout
                      |
                      +-- backoff 200 ms
                      |
                      +-- attempt 3 -> 200 OK
```

Ba lần gọi không phải ba event nghiệp vụ độc lập; chúng là **ba attempts xử lý cùng một logical event**. Vì vậy event nên có định danh ổn định (`eventId`) để nối log, metrics và hỗ trợ idempotency ở downstream.

Phân biệt các khái niệm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Logical event** | Một sự thật nghiệp vụ, ví dụ `OrderPlaced(eventId=evt-42)` |
| **Attempt** | Một lần gọi thao tác xử lý event; một event có thể có nhiều attempts |
| **Retry policy** | Quy tắc xác định có thử lại hay không, tối đa bao nhiêu lần và chờ bao lâu |
| **Backoff** | Thời gian chờ giữa các lần thử nhằm giảm áp lực lên tài nguyên đang lỗi |
| **Retry exhaustion** | Đã dùng hết attempts/budget nhưng thao tác vẫn thất bại |
| **Dead-letter / failure state** | Nơi lưu công việc không thể xử lý tiếp một cách tự động |
| **Idempotency** | Xử lý trùng event không tạo ra side effect sai hoặc lặp |
| **Delivery guarantee** | Điều hệ thống thực sự bảo đảm về lưu, giao, retry và mất event |

**Không được đồng nhất retry trong bộ nhớ với durability.** Một vòng lặp retry được thực thi trên thread của listener **không lưu event bền vững**. Process chết trước lần thử cuối có thể làm toàn bộ công việc biến mất, dù chính sách đã đặt `maxAttempts=3`.

## 2. Spring event listener có tự retry không?

**Không.** `ApplicationEventPublisher.publishEvent(...)` và `@EventListener` của Spring Framework **không tự retry mỗi listener bị lỗi theo một policy giới hạn**.

Với `SimpleApplicationEventMulticaster` mặc định:

1. Listener thông thường được gọi **đồng bộ** trên thread đang publish event.
2. Nếu listener ném exception, mặc định không có `ErrorHandler` nên lỗi có thể **truyền về publisher** và làm dừng lượt multicast hiện tại.
3. Nếu publisher đang nằm trong một phương thức transactional, unchecked exception được propagate có thể khiến transaction **rollback theo chính sách Spring transaction**.
4. Nếu ứng dụng cấu hình executor, `@Async` hoặc custom error handler, hành vi propagate có thể khác. Bắt và log lỗi không đồng nghĩa lỗi được retry.

```java
@EventListener
public void handle(OrderPlaced event) {
    notificationGateway.send(event);
}
```

Đây chỉ là **mã minh họa** với các kiểu do ứng dụng cung cấp. Nếu `send(...)` ném lỗi tạm thời, Spring event bus mặc định không tự gọi lại `handle(...)` ba lần.

### Ba nơi có thể đặt retry

| Vị trí | Điều gì được retry? | Hệ quả chính |
| --- | --- | --- |
| **Trong listener đồng bộ** | Lặp lời gọi đến dependency hoặc handler con | Có thể giữ request/transaction mở lâu; lỗi cuối truyền về publisher |
| **Ở service/proxy Spring Retry** | Retry một method invocation qua AOP | Cần proxy hợp lệ, policy và transaction boundary chính xác |
| **Worker outbox/consumer broker** | Retry job/message đã được lưu bền vững | Tách khỏi request, có thể sống qua restart; cần dedup, queue, backoff, vận hành |

Không nên coi cả ba cùng cho một mức bảo đảm. Đặt retry bên trong một listener đồng bộ có thể đủ cho thông tin thứ yếu, nhưng **không bảo đảm phát event sau khi transaction đã commit khi process chết**.

## 3. Quy tắc thiết kế một bounded retry

### 3.1. Chỉ retry lỗi tạm thời, không phải mọi Throwable

**Nhóm có thể retry** khi thao tác là an toàn/idempotent và còn budget:

- HTTP 503/502/504 hoặc lỗi kết nối tạm thời tới một downstream.
- HTTP 429 khi response và hợp đồng cho phép retry; tôn trọng `Retry-After` nếu có.
- Deadlock/serialization conflict của database khi có khả năng chạy lại **toàn bộ transactional unit** an toàn.
- Lỗi timeout có cơ chế xác định trạng thái hoặc idempotency key để tránh thực hiện trùng.

**Nhóm thường không retry tự động:**

- Lỗi dữ liệu cố định như thiếu trường bắt buộc, ID sai định dạng, vi phạm business invariant.
- HTTP 400/401/403 khi không có sự kiện làm thay đổi dữ liệu xác thực/quyền.
- Bug code (`NullPointerException`, sai cấu hình hoặc mapping cố định).
- Lỗi làm side effect đã xảy ra nhưng client không biết kết quả, **nếu không có idempotency/deduplication**.
- Tình huống vượt deadline hoặc được caller yêu cầu hủy.

Không dùng `catch (Exception)` để retry mọi lỗi một cách mù quáng. Phải định nghĩa **retryable exception taxonomy** hoặc predicate dựa trên lỗi/response thật. Những exception do người vận hành không thể tự hồi phục cần được surfaced sớm, không làm nghẽn queue.

### 3.2. Số attempts: tính cả lần đầu

Đặt `maxAttempts = 3` có nghĩa là:

```text
attempt 1: gọi lần đầu
attempt 2: retry lần thứ nhất
attempt 3: retry lần thứ hai
STOP: không có attempt 4
```

Đây cũng là cách hiểu của **Spring Retry 2.x `@Retryable(maxAttempts = 3)`**: tối đa ba lần gọi **bao gồm lần đầu**.

**Đừng nhầm với Spring Framework 7 core `@Retryable(maxRetries = 3)`**, vốn mô tả **tối đa ba lần thử lại sau lần gọi ban đầu**. Tên annotation, package và semantics khác nhau; với dự án **Spring Framework 6.2** của bài này, `@Retryable` dùng ở phần 6 là **Spring Retry add-on**, không phải core annotation của Spring Framework 7.

Nên ghi trong tài liệu project một tham số rõ nghĩa như `maxAttempts` thay vì “retry 3 lần”, vì câu đó có thể được hiểu là tổng 3 hay tổng 4 lần.

### 3.3. Backoff, jitter và deadline

Một policy thường dùng:

```text
delay(attempt) = min(maxDelay, initialDelay × multiplier^(attempt - 1))
```

Trong đó `attempt` ở công thức là **thứ tự lần thất bại cần lên lịch retry**, bắt đầu từ 1. Với `initialDelay=100 ms`, `multiplier=2`, `maxDelay=500 ms` và `maxAttempts=4`:

| Lần gọi | Nếu thất bại thì chờ trước lần kế | Ghi chú |
| --- | --- | --- |
| 1 | 100 ms | Retry attempt 2 |
| 2 | 200 ms | Retry attempt 3 |
| 3 | 400 ms | Retry attempt 4 |
| 4 | **Không chờ** | Exhausted, dừng |

Tổng backoff trước khi hết 4 attempts là **700 ms**, chưa gồm thời gian chạy từng attempt. Nếu mỗi attempt có network timeout 2 giây, tổng thời gian xấu nhất có thể gần **8,7 giây** hoặc hơn do overhead.

**Jitter** thêm một phần ngẫu nhiên vào delay để tránh hàng nghìn client đang lỗi cùng retry vào đúng thời điểm. Với hệ thống tải lớn, một công thức exponential backoff không jitter có thể khiến các retry cùng “đập” xuống downstream sau mỗi chu kỳ.

Một retry policy tốt thường có **hai trần**:

- **Attempt budget:** ví dụ 3 attempts, không có vòng lặp vô hạn.
- **Elapsed-time budget/deadline:** ví dụ không còn hơn 2 giây thì không bắt đầu attempt tiếp theo.

Với request có deadline, đừng chỉ nhân số attempts với timeout rồi hy vọng vẫn đáp ứng SLA. Để thử lại có ý nghĩa, cần đặt timeout từng attempt, timeout tổng và giới hạn queue waiting khi xử lý async.

### 3.4. Khi hết lượt: điều gì xảy ra?

Hết retries là **một outcome nghiệp vụ/vận hành cần được định nghĩa rõ**, không phải chỉ in stack trace:

- Nếu listener là bước **bắt buộc trước commit**, truyền lỗi cuối ra ngoài hoặc đánh dấu rollback-only theo đúng transaction policy.
- Nếu đó là một side effect **sau commit**, không thể rollback transaction nguồn. Lưu trạng thái thất bại và có cơ chế xử lý lại/đối soát.
- Nếu chỉ là **best-effort telemetry**, có thể ghi metric và dừng có chủ đích, không làm fail request.
- Nếu event đã vào **durable queue/outbox**, đánh dấu retry exhaustion, chuyển dead-letter/quarantine hoặc cảnh báo để điều tra; không xóa message mà chưa có quyết định.

Phải biết **số lần thử thực tế**, exception cuối, event ID và trạng thái cuối cùng. Một hệ thống báo “success” vì đã nuốt lỗi sau 3 lần thử là không đúng nếu công việc bắt buộc chưa hoàn thành.

## 4. Ví dụ Java 17+ chạy được: tối đa ba attempts trong @EventListener

Ví dụ dùng **Spring Framework 6.2.9**, không cần Spring Boot, database hay Spring Retry dependency. Để làm rõ thuật toán, một lớp `BoundedRetry` tự thực hiện tối đa **3 attempts** và chờ `10 ms`, `20 ms` khi lỗi tạm thời. Mục đích là dạy về **bounded retry + backoff + exception propagation**; trong production, không nên dùng vòng `Thread.sleep(...)` bên trong request/transaction khi công việc có thể chạy qua worker bền vững.

Ba trường hợp được mô phỏng:

1. `evt-A`: hai attempts đầu lỗi tạm thời, attempt thứ ba thành công.
2. `evt-B`: cả ba attempts đều lỗi tạm thời, policy ném `DeliveryExhaustedException` giữ **cause**.
3. `evt-C`: lỗi dữ liệu vĩnh viễn, dừng **ngay attempt đầu tiên**, không retry.

### 4.1. Cấu trúc

```text
bounded-event-retry-demo/
├── pom.xml
└── src/main/java/example/BoundedEventRetryDemo.java
```

### 4.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>bounded-event-retry-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.BoundedEventRetryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. src/main/java/example/BoundedEventRetryDemo.java

```java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class BoundedEventRetryDemo {

    public record NotificationRequested(String eventId) {}

    public static class TransientDeliveryException extends RuntimeException {
        public TransientDeliveryException(String message) {
            super(message);
        }
    }

    public static class DeliveryExhaustedException extends RuntimeException {
        public DeliveryExhaustedException(String eventId, Throwable cause) {
            super("exhausted retries for " + eventId, cause);
        }
    }

    public static class BoundedRetry {
        private static final int MAX_ATTEMPTS = 3;

        public void execute(String eventId, Runnable operation) {
            for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
                try {
                    operation.run();
                    return;
                } catch (TransientDeliveryException original) {
                    if (attempt == MAX_ATTEMPTS) {
                        System.out.println("retry: exhausted " + eventId
                                + " after " + attempt + " attempts");
                        throw new DeliveryExhaustedException(eventId, original);
                    }

                    long delayMillis = 10L << (attempt - 1);
                    System.out.println("retry: " + eventId
                            + " attempt=" + attempt
                            + " delayMs=" + delayMillis);
                    try {
                        Thread.sleep(delayMillis);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "retry interrupted for " + eventId,
                                interrupted);
                    }
                }
            }
        }
    }

    public static class NotificationListener {
        private final BoundedRetry retry;
        private final Map<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();

        public NotificationListener(BoundedRetry retry) {
            this.retry = retry;
        }

        @EventListener
        public void onNotificationRequested(NotificationRequested event) {
            retry.execute(event.eventId(), () -> {
                int current = attempts.computeIfAbsent(
                        event.eventId(), key -> new AtomicInteger())
                        .incrementAndGet();

                System.out.println("listener: " + event.eventId()
                        + " attempt=" + current);

                if ("evt-A".equals(event.eventId()) && current < 3) {
                    throw new TransientDeliveryException("gateway temporary");
                }

                if ("evt-B".equals(event.eventId())) {
                    throw new TransientDeliveryException("gateway temporary");
                }

                if ("evt-C".equals(event.eventId())) {
                    throw new IllegalArgumentException("invalid payload");
                }

                System.out.println("listener: delivered " + event.eventId());
            });
        }
    }

    public static class NotificationService {
        private final ApplicationEventPublisher publisher;

        public NotificationService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void request(String eventId) {
            System.out.println("publisher: " + eventId);
            publisher.publishEvent(new NotificationRequested(eventId));
            System.out.println("publisher: returned " + eventId);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        BoundedRetry boundedRetry() {
            return new BoundedRetry();
        }

        @Bean
        NotificationListener notificationListener(BoundedRetry retry) {
            return new NotificationListener(retry);
        }

        @Bean
        NotificationService notificationService(
                ApplicationEventPublisher publisher) {
            return new NotificationService(publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {
            NotificationService service =
                    context.getBean(NotificationService.class);

            service.request("evt-A");

            try {
                service.request("evt-B");
            } catch (DeliveryExhaustedException exhausted) {
                System.out.println("caller: " + exhausted.getMessage()
                        + " cause="
                        + exhausted.getCause().getClass().getSimpleName());
            }

            try {
                service.request("evt-C");
            } catch (IllegalArgumentException permanent) {
                System.out.println("caller: permanent " + permanent.getMessage());
            }
        }
    }
}
```

Chạy bằng JDK 17+ và Maven trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in, theo đúng thứ tự khi chạy bình thường (không tính log Spring/Maven):

```text
publisher: evt-A
listener: evt-A attempt=1
retry: evt-A attempt=1 delayMs=10
listener: evt-A attempt=2
retry: evt-A attempt=2 delayMs=20
listener: evt-A attempt=3
listener: delivered evt-A
publisher: returned evt-A
publisher: evt-B
listener: evt-B attempt=1
retry: evt-B attempt=1 delayMs=10
listener: evt-B attempt=2
retry: evt-B attempt=2 delayMs=20
listener: evt-B attempt=3
retry: exhausted evt-B after 3 attempts
caller: exhausted retries for evt-B cause=TransientDeliveryException
publisher: evt-C
listener: evt-C attempt=1
caller: permanent invalid payload
```

### Phân tích

- `NotificationListener` là Spring bean được khai báo qua `@Bean`; `@EventListener` được Spring phát hiện khi context refresh.
- `ApplicationEventPublisher` dùng multicaster mặc định đồng bộ, nên các attempts `evt-A` chạy **trước khi** `service.request("evt-A")` trả về. Delay `10+20 ms` cộng vào thời gian caller chờ, chưa tính thời gian xử lý.
- `BoundedRetry` chỉ catch `TransientDeliveryException`. Do đó `IllegalArgumentException` của `evt-C` **không bị retry**; nó thoát ra ngay từ attempt đầu.
- Khi `evt-B` dùng hết ba attempts, `DeliveryExhaustedException` giữ exception cuối trong `getCause()`. Caller không nhận một lỗi chung mất dấu nguyên nhân.
- Demo dùng `Map` để **mô phỏng số attempts trong một process**. Đây không phải một bảng idempotency, không bảo vệ duplicate event giữa nhiều instances và không survive restart.
- `Thread.sleep(...)` chỉ nhằm làm minh họa backoff nhìn được trong code. Một executor/scheduler hoặc worker nền mới là nơi phù hợp cho retry chờ dài; cần tránh chiếm request thread hoặc database transaction.
- Demo **không mở transaction**, nên không được dùng stdout này để khẳng định commit hay rollback. Trong ứng dụng có `@Transactional`, phải kiểm tra cả policy propagation và dữ liệu database.

Chính sách trong demo có tối đa ba attempts; **không có retry thứ tư**. Mỗi lần thất bại tạm thời chỉ tiếp tục nếu vẫn còn attempts, còn lỗi vĩnh viễn và lỗi interrupt kết thúc ngay. Trong chương trình thật cần thêm **deadline**, jitter, metric, sự an toàn của operation khi retry, và cơ chế recovery bền vững khi cần.

## 5. Spring Retry 2.x: @Retryable và @Recover với listener

Đối với Spring Framework 6.2, có thể bổ sung **Spring Retry** (artifact `org.springframework.retry:spring-retry`) và AOP support để dùng `org.springframework.retry.annotation.Retryable`, `@EnableRetry`, `@Backoff` và `@Recover`.

Đây là **thư viện bổ sung**, không phải retry có sẵn cho mọi `@EventListener`. Phải cấu hình `@EnableRetry` và bảo đảm method được gọi qua **Spring proxy**. Vì một event listener thường có trách nhiệm điều phối công việc, cách dễ hiểu là để listener gọi **một service riêng được retry**, thay vì trộn logic retry vào chính method annotated listener.

### Ví dụ tích hợp có sử dụng Spring Retry

```java
@Configuration
@EnableRetry
class RetryConfiguration {
    // Spring Retry tạo retry advice cho bean phù hợp.
}
```

```java
@Service
public class NotificationDeliveryService {

    @Retryable(
        retryFor = TransientGatewayException.class,
        maxAttempts = 3,
        backoff = @Backoff(delay = 100, multiplier = 2)
    )
    public void deliver(NotificationRequested event) {
        gateway.send(event);
    }

    @Recover
    public void exhausted(
            TransientGatewayException lastFailure,
            NotificationRequested event) {
        throw new DeliveryExhaustedException(
                event.eventId(), lastFailure);
    }
}
```

```java
@Component
public class NotificationEventListener {
    private final NotificationDeliveryService delivery;

    public NotificationEventListener(NotificationDeliveryService delivery) {
        this.delivery = delivery;
    }

    @EventListener
    public void onNotificationRequested(NotificationRequested event) {
        delivery.deliver(event); // Gọi qua proxy của bean khác.
    }
}
```

Ba đoạn trên là **mã tích hợp minh họa, chưa phải project độc lập**: phải có imports, `gateway`, event DTO, exception types, Spring Retry version phù hợp, AOP dependencies (trong Spring Boot thường dùng `spring-boot-starter-aop`) và cấu hình Spring context. `@Recover` cần chữ ký tương thích với method retryable (return type phù hợp, exception và arguments còn lại). Với method `void`, recovery trên cũng là `void` nhưng ném lại exception bọc để không nói dối rằng đã giao thành công.

Giải thích:

- `retryFor = TransientGatewayException.class` giới hạn loại lỗi được retry; permanent validation errors không được retry.
- `maxAttempts = 3` là **tổng số lần gọi bao gồm lần đầu**, theo Spring Retry 2.x.
- `delay=100`, `multiplier=2` tạo backoff theo policy; không giả định đây là cơ chế bền vững qua process crash.
- `@Recover` xử lý khi retry đã hết attempts; trong ví dụ nó **propagate failure** kèm cause. Có thể đổi thành việc ghi failure state bền vững nếu kiến trúc phù hợp, nhưng không được nuốt lỗi của một bước bắt buộc mà không có quyết định nghiệp vụ.
- Nếu `NotificationDeliveryService` gọi `this.deliver(...)` từ chính bean của nó, **self-invocation có thể bypass proxy**, làm retry không chạy. Gọi từ listener bean khác qua injected Spring-managed service giúp tránh lỗi này.
- `@EnableRetry` tạo advice/proxy; hãy xác minh annotation thực sự có hiệu lực bằng integration test cố tình fail hai attempts rồi success ở lần 3, không chỉ nhìn annotation trong source.
- Cần kiểm soát thứ tự retry advice và transaction advice. Một lần retry bên trong transaction đã bị đánh dấu rollback-only **không tương đương** chạy lại transactional operation sau rollback; nếu cần retry deadlock/serialization failure, thường phải retry **toàn bộ một transaction mới** theo boundary đã xác định.

**Khác biệt đáng chú ý giữa Spring Retry 2.x và Spring Framework 7:** Core Spring Framework 7 bổ sung resilience `@Retryable` trong package riêng và thuộc tính như `maxRetries`, không có semantics giống hệt `maxAttempts` ở trên. Không nhập nhằng hai annotation chỉ vì chúng có cùng tên.

## 6. Retry trong transaction: phải rõ transaction nào được thử lại

### 6.1. Retry đồng bộ bên trong transaction nguồn

```java
@Transactional
public void placeOrder(Command command) {
    repository.save(...);
    publisher.publishEvent(new OrderPlaced(...));
}
```

Đây là **mã minh họa**, không chạy độc lập.

Giả sử một listener thực hiện ba lần gọi HTTP trong transaction nguồn:

- Các lần chờ backoff có thể giữ **transaction/connection/lock** lâu hơn.
- Nếu một thao tác DB trong listener đánh dấu transaction **rollback-only** từ lần thử đầu, một retry thành công ở lần tiếp theo trong **cùng transaction đó** có thể vẫn không cứu được commit.
- Khi listener fail cuối cùng bằng unchecked exception và lỗi truyền ra ngoài, transaction interceptor có thể rollback. **Nếu listener catch lỗi rồi trả về bình thường**, transaction có thể commit dù side effect không thành công.
- Một external operation có thể đã hoàn tất dù client nhìn thấy timeout; retry không có idempotency key có thể tạo side effect **hai lần** trước khi local transaction biết kết quả.

Nếu nghiệp vụ cần atomicity, hãy thiết kế retry **cả use case/transaction** ở ranh giới phù hợp. Một transaction đã rollback không thể được “khôi phục” bằng cách gọi lại một method nhỏ trong cùng transaction bị đánh dấu rollback-only.

### 6.2. @TransactionalEventListener(AFTER_COMMIT)

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    notificationDeliveryService.deliver(event);
}
```

Đây là **mã tích hợp minh họa**, cần bean/import tương ứng. Listener chỉ được gọi khi có **commit thành công** của transaction nguồn; mặc định `fallbackExecution = false` nên publish ngoài transaction phù hợp có thể bị bỏ qua.

Retry tại callback này:

- **Không rollback được transaction nguồn đã commit.**
- Có thể vẫn chặn thread đang hoàn tất commit nếu listener và retry chạy đồng bộ.
- Nếu process chết ngay sau commit, một callback trong JVM có thể chưa kịp chạy; annotation **không tự cung cấp durable delivery**.
- Nếu callback cần cập nhật DB để ghi trạng thái giao notification, có thể cần **transaction mới**, ví dụ service `@Transactional(propagation = Propagation.REQUIRES_NEW)` được gọi qua Spring proxy trong imperative flow.

Đừng coi “event được publish”, “transaction committed”, “listener retry exhausted” và “notification delivered” là một trạng thái duy nhất. Chúng thuộc các lớp trách nhiệm khác nhau.

### 6.3. Async listener không giữ transaction caller

Với `@Async @EventListener`, công việc chạy trên executor thread và **không tự kế thừa thread-bound transaction** của request. Lỗi từ worker không tự propagate về publisher; retry trong worker cũng không rollback transaction nguồn.

Có thể cấu hình `AsyncUncaughtExceptionHandler` cho async `void`, hoặc quản lý completion với các API `Future`/`CompletableFuture` ở tầng phù hợp. Nhưng chỉ “ghi log lỗi async” **không phải một retry queue có durability**.

Một listener transaction-synchronized có thể cần chạy trong thread publish để đăng ký synchronization; đừng cấu hình custom multicaster executor rồi cho rằng tất cả transactional listeners được dời sang worker một cách an toàn.

## 7. Retry có giới hạn nhưng phải đảm bảo không giao trùng

Giả sử gọi:

```text
sendPaymentConfirmation(evt-42)
   |
   +-- request tới gateway: gateway xử lý THÀNH CÔNG
   |
   +-- response bị mất, client thấy timeout
   |
   +-- retry: gateway xử lý LẦN NỮA
```

Từ góc nhìn client, attempt đầu “thất bại”, nhưng side effect có thể đã xảy ra. **Retry không tự làm operation an toàn**.

### 7.1. Stable idempotency key

Dùng `eventId`/business operation ID ổn định **qua mọi attempts**. Ví dụ, một API hỗ trợ idempotency nhận header:

```text
Idempotency-Key: evt-42
```

Nếu gateway có hợp đồng idempotency, hai request với cùng khóa có thể được xử lý như cùng một thao tác logic. Không được tự giả định tất cả downstream hỗ trợ hoặc tôn trọng header đó.

Ở consumer, có thể thiết kế một bảng `processed_events`:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Đây là **schema minh họa**. Để bảo đảm idempotency đối với side effect trong DB, việc kiểm tra/ghi marker và thay đổi nghiệp vụ cần được phối hợp **trong cùng transaction hoặc dùng cơ chế unique constraint/atomic insert**. Một câu hỏi “đã xử lý chưa?” trước thao tác mà không có unique constraint có thể race giữa hai workers.

Không nên dùng ID tạo **mới ở mỗi lần retry** làm idempotency key vì như vậy các attempts trông như các operation khác nhau.

### 7.2. Tránh retry storm

Khi hàng nghìn consumer cùng gặp HTTP 503, backoff với jitter, global concurrency limit, circuit breaker và rate limit có thể cần thiết. Không chỉ dựa vào maxAttempts=3: 1.000 requests lỗi với 3 attempts có thể tạo **3.000 calls** lên dịch vụ đã quá tải.

Sử dụng deadline và thông tin `Retry-After` khi backend cung cấp. Với HTTP 429, việc retry ngay không có backoff thường làm tình hình xấu thêm. Với circuit breaker đang open, một retry vô nghĩa có thể nhanh chóng thất bại; cần định nghĩa fallback hoặc chuyển job về queue tùy hợp đồng.

## 8. Khi retry in-process chưa đủ: Transactional Outbox và worker

Nếu một event phản ánh đơn hàng **đã commit** và cần gửi email/webhook **không được mất**, bounded retry ngay trong `@TransactionalEventListener(AFTER_COMMIT)` **chưa đủ**. Process có thể crash giữa commit và gửi, hoặc giữa attempts, làm event biến mất khỏi RAM.

Một thiết kế bền vững hơn:

```text
Transaction T1:
   INSERT orders(...)
   INSERT outbox_events(
       event_id, aggregate_id, event_type, payload,
       status='PENDING', attempts=0, next_attempt_at=NOW()
   )
   COMMIT

Worker:
   chọn các outbox_events đủ điều kiện và claim an toàn
      |
      +-- attempt 1 -> failure -> status=RETRYING,
      |                        attempts=1,
      |                        next_attempt_at=NOW()+backoff
      |
      +-- attempt 2 -> success -> status=SENT
      |
      +-- attempts hết giới hạn -> status=DEAD_LETTER,
                                 last_error=...
```

Lợi ích:

- Event được lưu **trong cùng transaction** với thay đổi nghiệp vụ.
- Worker có thể phục hồi sau restart, dựa vào `status`/`next_attempt_at` và lịch retry.
- Retry không cần giữ HTTP request thread chờ backoff.
- Có thể đo backlog, retry lag, tuổi event và dead-letter.
- Có thể giới hạn attempts, deadline, concurrency và rate limit rõ ràng.

Những gì outbox **không tự đảm bảo**:

- Không đảm bảo downstream chỉ nhận event **đúng một lần**. Gửi thành công rồi crash trước khi đánh dấu `SENT` có thể làm gửi lại. Consumer vẫn cần idempotency.
- Không tự xử lý ordering trên nhiều aggregate hoặc nhiều partition. Nếu cần thứ tự theo aggregate, phải đưa ra chiến lược partition/ordering rõ ràng.
- Không tự giải quyết mọi lỗi nghiệp vụ vĩnh viễn; cần dead-letter, quy trình điều tra và khả năng replay có kiểm soát.
- Không miễn phí chi phí ghi DB; đổi lại là khả năng phục hồi và tách thời gian I/O khỏi request.

### Quy tắc worker tối thiểu

1. **Claim atomically** job để hai worker không cùng xử lý một event nếu architecture yêu cầu; có thể dùng locking/lease phù hợp DB.
2. Ghi `attempts` một cách nhất quán khi bắt đầu hoặc kết thúc mỗi attempt; định nghĩa rõ để không bị lệch số đếm khi crash.
3. `next_attempt_at` tăng theo backoff và jitter, chịu max delay; không tạo tight loop khi DB/downstream lỗi.
4. Sau lần thử cuối, chuyển sang `DEAD_LETTER` hoặc `FAILED_PERMANENT`; không xóa row âm thầm.
5. Lưu `last_error_type`, message đã lọc secrets, correlation ID, timestamp để có thể điều tra.
6. Sử dụng stable `eventId` và idempotent consumer khi giao lại.
7. Nếu operator muốn replay, xác định liệu replay có reset attempts, tạo event mới hay chỉ tạo **một delivery attempt mới** cho cùng logical event.

## 9. Chọn backoff và tổng budget theo SLA

Hãy tính **tổng thời gian** chứ không chỉ số attempts.

Giả sử trong một request:

- `maxAttempts = 3`.
- Mỗi lần gọi downstream có timeout tối đa **500 ms**.
- Delay sau thất bại thứ nhất **100 ms**.
- Delay sau thất bại thứ hai **200 ms**.

Worst-case chỉ riêng các thao tác retry có thể xấp xỉ:

```text
3 × 500 ms + 100 ms + 200 ms = 1,800 ms
```

Chưa tính database, controller, framework overhead và scheduler jitter. Nếu SLO của HTTP endpoint là **p95 dưới 300 ms**, chính sách retry đồng bộ này **không phù hợp** cho request. Hãy giảm attempt budget, giới hạn deadline hoặc chuyển tác vụ không bắt buộc sang worker bền vững.

Nếu xử lý trong queue sau commit, budget có thể được tính theo **SLA thời gian hoàn tất event** (ví dụ tối đa 10 phút). Nhưng dù total deadline dài, mỗi attempt vẫn cần timeout; một call không timeout có thể chiếm worker vô hạn và khiến tất cả retry budget trở nên vô nghĩa.

Chọn delay không có một giá trị “chuẩn” dùng cho mọi downstream. Cần dựa vào latency lịch sử, rate limits, transient error distribution, số workers và mức ưu tiên event. Đừng dùng một backoff quá ngắn với dependency đang rate limit.

## 10. Observability: đếm retries đúng cách

Trong logs/metrics/traces, cần tách:

| Signal | Ví dụ | Điều cần xem |
| --- | --- | --- |
| `eventId` | `evt-42` | Stable qua attempts/replay |
| `eventType` | `OrderPlaced` | Bounded set cho metrics |
| `consumer` | `NotificationListener` | Ai xử lý |
| `attempt` | 1, 2, 3 | Lần gọi hiện tại |
| `outcome` | SUCCESS, RETRYING, EXHAUSTED | Kết quả attempt và logical event |
| `error.category` | TRANSIENT, PERMANENT, TIMEOUT | Nên retry nữa không |
| `nextAttemptAt` | Timestamp | Khi nào thử lại |
| `elapsed` | Duration | Có vượt deadline/SLA không |
| `transactionPhase` | AFTER_COMMIT | Không nhầm publication với commit |

Một event thành công ở attempt 3 có **hai attempt failures** nhưng chỉ **một logical event thành công**. Dashboard nên tách:

- `retry.attempts.total`: số attempts.
- `retry.failures.total`: số attempts lỗi.
- `event.completed.total`: số logical events thành công.
- `event.exhausted.total`: số logical events hết budget.
- `retry.delay` và `event.end_to_end_latency`: độ trễ chờ và thời gian hoàn tất thực.

Đây là **tên metric gợi ý do ứng dụng đặt**, không phải metrics Spring Framework tự xuất khi dùng `@EventListener`. Spring Framework không tự tạo Micrometer Observation riêng cho mỗi `@EventListener`.

**Tránh cardinality explosion:** không đưa `eventId`, `orderId`, URL chứa ID hoặc exception message tùy ý làm low-cardinality metric labels; dùng chúng trong log/trace hoặc high-cardinality attributes theo policy bảo mật. Không log bearer tokens, thông tin thanh toán, mật khẩu hoặc cả payload cá nhân trong một failure record.

### Bảo toàn exception cuối và lỗi gốc

Khi exhaustion, đừng làm:

```java
throw new RuntimeException("Retry failed");
```

Cách đó bỏ mất loại lỗi/stack trace cuối. Thay bằng:

```java
throw new DeliveryExhaustedException(event.eventId(), lastFailure);
```

Đây là **đoạn minh họa**, cần class exception/biến theo ứng dụng. Constructor nhận `cause` giữ lại nguyên nhân để người vận hành biết vì sao tất cả attempts thất bại.

Nếu quá trình ghi failure status cũng thất bại, cần ghi nhận lỗi thứ cấp mà **không vô tình che mất nguyên nhân delivery**. Tùy use case có thể dùng suppressed exception hoặc failure record riêng. Nhưng không được nuốt lỗi ghi trạng thái bền vững nếu việc đó làm mất job mà hệ thống cần phục hồi.

## 11. Test bounded retry, không chỉ test “đã gọi lại”

Để một policy thực sự đáng tin, nên test:

| Tình huống | Kỳ vọng |
| --- | --- |
| Lần đầu thành công | Một attempt, không sleep, không retry |
| Lỗi transient hai lần, lần ba thành công | Đúng **3 attempts**, 2 backoffs, không exhaustion |
| Lỗi transient liên tục | Sau **3 attempts** dừng; exception cuối có cause |
| Lỗi permanent | Chỉ **1 attempt**, không retry |
| Thread bị interrupt trong backoff | Restore interrupt flag và kết thúc, không âm thầm retry tiếp |
| Deadline hết trước attempt tiếp theo | Dừng, ghi outcome deadline exceeded |
| HTTP 429 có Retry-After | Tuân thủ server hint trong giới hạn policy |
| Concurrent retry cùng logical event | Idempotency/dedup ngăn side effect lặp |
| Worker crash giữa attempts | Job outbox được phục hồi nếu policy yêu cầu durability |
| Listener đang trong transaction | Biết chính xác trường hợp commit/rollback, không nhầm logger với outcome |
| Retry exhausted after commit | Không nói transaction nguồn rollback; ghi failure state riêng |
| Circuit breaker đang open | Không tạo storm cố gọi lại không hiệu quả |

### 11.1. Unit test dùng clock/sleeper giả

Đối với retry utility, không nên dùng `Thread.sleep` thật để test delays nếu có thể tách **Sleeper/Clock** ra thành dependency. Dùng một fake sleeper ghi lại các delays và một fake clock có thể điều khiển để test deadline nhanh, deterministic.

Pseudo-test:

```java
// Mã minh họa: FakeSleeper, Policy và fakeGateway là test fixtures.
fakeGateway.failTransiently(2);
policy.execute("evt-42", fakeGateway::send);

assertEquals(3, fakeGateway.attemptCount());
assertEquals(List.of(100L, 200L), fakeSleeper.delays());
```

Đoạn trên **không phải test độc lập**; nó mô tả ý định kiểm tra policy. Không dùng `Thread.sleep(1000)` để “đợi retry hoàn thành” rồi assert một trạng thái ngẫu nhiên.

### 11.2. Integration test Spring event

Với `AnnotationConfigApplicationContext` hoặc `@SpringBootTest`:

1. Đăng ký listener thật và service được retry qua Spring proxy.
2. Publish event một lần và xác nhận **số attempts** bằng fake gateway có counter.
3. Đảm bảo `@Recover` được gọi đúng lúc exhaustion, và error được phân loại đúng.
4. Nếu có `@TransactionalEventListener`, tạo transaction manager thật, test commit/rollback riêng.
5. Với `@Async`, dùng `CountDownLatch`, `CompletableFuture` hoặc test executor để chờ completion thật.
6. Nếu có `@RecordApplicationEvents`, nhớ rằng recorder **chứng minh event đã publish**, không chứng minh listener retries xong.

Một fake gateway trong test có thể cố tình ném transient error hai lần rồi trả thành công, nhưng phải xác nhận listener side effect thực sự được thực thi **đúng một lần về mặt nghiệp vụ**, không chỉ đếm retry calls.

### 11.3. Load/chaos test trước production

Trong thử nghiệm tải, đo request p95/p99, throughput, queue depth, error rates và năng lực phục hồi sau outage. Một hệ thống có `maxAttempts=3` nhưng queue lớn vẫn có thể tích lũy lượng công việc khổng lồ.

Mô phỏng các tình huống:

- Gateway trả 503 liên tục 5 phút, rồi phục hồi.
- DB deadlock/serialization conflict trong nhiều transaction cạnh tranh.
- Process bị kill giữa gửi thành công và cập nhật trạng thái outbox.
- Worker restart, lease hết hạn, job được giao lại.
- 429 response kèm `Retry-After` thay đổi theo tải.
- Consumer cố tình xử lý trùng cùng `eventId` để xác nhận idempotency.

Quan sát cả **tính đúng đắn và tốc độ phục hồi**, không chỉ việc hệ thống còn trả HTTP 200.

## 12. Anti-patterns thường gặp

**1. Vòng `while(true)` trong `@EventListener`.**  
Một downstream lỗi lâu có thể giữ request/worker vô hạn. Luôn có maxAttempts, deadline và failure policy.

**2. Retry mọi exception.**  
Lỗi validation vĩnh viễn được gọi lại nhiều lần không giúp phục hồi mà chỉ tăng tải, làm nhiễu logs và che bug.

**3. Retry 3 lần nhưng không rõ đó là tổng hay số lần sau attempt đầu.**  
Trong Spring Retry 2.x `maxAttempts=3` là tổng 3; core Spring Framework 7 `maxRetries=3` là tối đa 3 lần thử lại sau lần đầu. Đọc đúng API/version.

**4. Chỉ catch, log rồi trả về.**  
Khi business operation bắt buộc, caller có thể tưởng hoàn thành và transaction commit; phải propagate hoặc lưu failure state được định nghĩa rõ.

**5. Gọi method `@Retryable` qua `this` trong cùng class.**  
Self-invocation có thể bypass AOP proxy, nên policy không chạy. Dùng injected Spring-managed service hoặc cấu trúc interceptor phù hợp.

**6. Retry một SQL trong transaction đã bị đánh dấu rollback-only.**  
Một lần retry thành công trong transaction lỗi không bảo đảm commit. Retry nguyên một transaction mới sau rollback khi cần.

**7. `@Async` được xem là durable queue.**  
Task queue trong RAM có thể mất khi process chết. Nếu yêu cầu giao event chắc chắn, dùng outbox/broker bền vững.

**8. Backoff không có jitter khi nhiều consumers cùng lỗi.**  
Các attempts có thể đồng bộ hóa, gây retry storm lên downstream. Dùng jitter, concurrency limits và circuit breaker phù hợp.

**9. Không giới hạn timeout từng attempt.**  
Một call treo vô hạn phá hỏng mọi maxAttempts. Đặt timeout ở I/O client và global deadline.

**10. Dùng eventId mới cho mỗi attempt.**  
Phá idempotency, khiến consumer không nhận ra cùng logical operation. Giữ một ID xuyên suốt.

**11. Trông chờ rollback khi listener `AFTER_COMMIT` thất bại.**  
Transaction nguồn đã commit. Phải quản lý trạng thái xử lý event sau commit độc lập.

**12. Cho rằng việc có một exception trong log nghĩa là delivery đã được retry.**  
Logging không phải scheduler/retry policy. Cần đo attempts, next retry time, exhaustion và final outcome.

**13. Không định nghĩa dead-letter/recovery procedure.**  
Policy hết budget nhưng không ai xử lý sẽ biến sự cố tạm thời thành mất sự kiện kéo dài. Đặt dashboard, alerts, runbook và replay kiểm soát.

**14. Retry có side effect không idempotent.**  
Timeout có thể xảy ra sau khi downstream đã xử lý; retry có thể tạo đơn/gửi tiền/email hai lần. Cần kiểm tra giao thức và idempotency key trước.

## 13. Checklist thiết kế retry có giới hạn

Trước khi đưa policy vào production, trả lời được các câu hỏi sau:

1. **Mục tiêu:** Thao tác nào sẽ retry? Toàn listener, một HTTP call, hay cả use case/transaction?
2. **Phân loại lỗi:** Những exception/status code nào là transient? Loại nào dừng ngay?
3. **Attempts:** Giới hạn tổng số lần gọi, tính cả lần đầu, được định nghĩa ở đâu?
4. **Backoff:** Initial delay, multiplier, max delay, jitter, `Retry-After`?
5. **Deadline:** Timeout mỗi attempt và budget toàn operation?
6. **Transaction:** Retry có nằm trong transaction đã rollback-only không? Callback chạy trước hay sau commit?
7. **Threading:** Có chặn HTTP request hoặc executor worker trong lúc sleep không?
8. **Idempotency:** Nếu attempt cũ đã thành công nhưng response bị mất, retry có an toàn không?
9. **Durability:** Process chết giữa các attempts thì event có còn ở nơi có thể phục hồi không?
10. **Exhaustion:** Error được ném, lưu failure state, chuyển dead-letter, hay bỏ qua có chủ đích?
11. **Observability:** Có eventId, attempt count, outcome, backoff delay, retry lag và cảnh báo?
12. **Capacity:** Khi toàn downstream lỗi, tải nhân lên bao nhiêu; queue, circuit breaker, bulkhead hoạt động ra sao?
13. **Testing:** Có test permanent error, retry exhaustion, interrupt, rollback, async, crash/replay và duplicate không?

Nếu câu trả lời cho **durability** là “không”, hãy ghi rõ rằng bounded retry hiện tại chỉ bảo vệ những lỗi tạm thời **trong lúc tiến trình còn chạy**. Nếu event quan trọng không được mất, cần một lớp lưu trữ và worker đáng tin cậy hơn.

## 14. Câu hỏi tự đánh giá

**1. `@EventListener` mặc định có tự retry khi handler ném exception không?**  
Không. Với multicaster đồng bộ mặc định, exception có thể propagate về publisher và ngăn phần multicast còn lại.

**2. `maxAttempts=3` trong Spring Retry 2.x tương ứng bao nhiêu lần gọi?**  
Tối đa **ba lần tổng cộng**, bao gồm lần gọi đầu và hai lần thử lại.

**3. Tại sao phải phân biệt transient với permanent errors?**  
Vì retry lỗi permanent không thể tự phục hồi, chỉ tăng tải và trì hoãn việc báo lỗi thật.

**4. Vì sao retry trong `@Transactional` có thể gây rollback dù lần cuối thành công?**  
Vì một lỗi trong attempt trước có thể khiến transaction hiện tại bị đánh dấu rollback-only; cần thiết kế ranh giới retry/transaction phù hợp.

**5. Vì sao `@TransactionalEventListener(AFTER_COMMIT)` với retry không thể rollback đơn hàng gốc?**  
Vì transaction nguồn đã commit trước khi listener chạy ở pha đó. Phản ứng thất bại phải có trạng thái hoặc transaction xử lý riêng.

**6. `@Async` có biến retry thành bền vững qua restart không?**  
Không. Executor queue trong bộ nhớ không bảo đảm lưu việc qua process crash.

**7. Nếu một request gửi thành công tới gateway nhưng mất response, retry có thể gây gì?**  
Có thể tạo side effect trùng. Cần stable idempotency key và hợp đồng xử lý trùng từ gateway/consumer.

**8. Khi hết ba attempts, có nên in lỗi rồi trả success không?**  
Chỉ khi đó là best-effort side effect và hợp đồng cho phép. Với công việc bắt buộc, phải propagate hoặc ghi failure state bền vững.

**9. Khi một downstream lỗi trên diện rộng, tại sao maxAttempts chưa đủ?**  
Vì nhiều callers vẫn nhân số attempts, gây retry storm; cần backoff/jitter, timeout, rate limit, concurrency limit và circuit breaker.

## 15. Tài liệu tham khảo chính thức

- [Spring Framework 6.2.9 — SimpleApplicationEventMulticaster (đồng bộ, error propagation)](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Application Events và @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Transaction Rollback Rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Retry 2.x — @Retryable API (maxAttempts)](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html)
- [Spring Retry — @Recover API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Recover.html)
- [Spring Framework 7 — Core Resilience Features (maxRetries khác maxAttempts)](https://docs.spring.io/spring-framework/reference/core/resilience.html)
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)

