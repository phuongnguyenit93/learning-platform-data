# Backoff và chống bão retry khi xử lý Spring Application Events

## 1. Bài toán: retry có thể làm một lỗi nhỏ thành sự cố lớn

Trong hệ thống hướng sự kiện, một `@EventListener` có thể gửi email, gọi REST API, ghi database, publish thông điệp sang broker hoặc thực hiện một tác vụ khác. Khi dependency chậm, trả HTTP 429/503 hoặc mất kết nối, retry thường giúp vượt qua lỗi tạm thời. Tuy nhiên **retry ngay lập tức và đồng loạt** có thể làm quá tải chính dependency đang gặp sự cố.

Ví dụ 1.000 instance nhận lỗi `503 Service Unavailable` ở cùng một thời điểm:

```text
t = 0 ms:   1.000 lời gọi tới downstream -> 503
t = 1 ms:   1.000 retry ngay lập tức   -> 503
t = 2 ms:   1.000 retry tiếp           -> 503
...
Downstream chưa kịp hồi phục, connection pool/CPU lại quá tải.
```

Hiện tượng này gọi là **retry storm**; khi nhiều client cùng retry đúng một mốc thời gian cũng được gọi là *thundering herd*. Thậm chí một dependency vốn chỉ bị chậm trong vài giây có thể không phục hồi nổi vì lưu lượng retry nhân thêm vào lưu lượng mới. Nếu retry ở nhiều tầng (HTTP client, handler, queue consumer, gateway), số lần gọi xuống dưới còn bị khuếch đại.

**Backoff** là chính sách chờ tăng dần giữa các lần thử. **Jitter** là sự ngẫu nhiên hóa thời gian chờ nhằm phân tán các client thay vì để chúng đồng loạt gọi lại. Muốn chống bão retry hiệu quả còn cần giới hạn lần thử, tổng thời gian, số request đồng thời, idempotency, nhận diện lỗi retryable, quan sát retry và một nơi chịu trách nhiệm retry.

Mục tiêu của bài là thiết kế retry có kiểm soát quanh **công việc của listener hoặc integration client**, không coi lời gọi `ApplicationEventPublisher.publishEvent(...)` là một broker bền vững có sẵn retry.

## 2. Vì sao Spring application event đặc biệt dễ mắc lỗi khi retry?

Spring Framework hỗ trợ `ApplicationEventPublisher.publishEvent(Object)` và các method `@EventListener`. Với `SimpleApplicationEventMulticaster` mặc định, listener thông thường được gọi **đồng bộ trên thread phát event**. Điều này có nghĩa:

- Một listener gọi downstream rồi `Thread.sleep(...)` nhiều giây có thể **giữ request thread** hoặc thread xử lý command của publisher.
- Nếu publish nằm trong transaction, listener đồng bộ có thể đang giữ transaction và các tài nguyên database lâu hơn cần thiết.
- Nếu listener ném exception không được xử lý, nó có thể truyền ngược về `publishEvent(...)`. Transaction đang hoạt động có thể rollback tùy cấu hình.
- Một lần publish có thể có **nhiều listener**. Retry nguyên `publishEvent(event)` sau khi listener thứ hai lỗi có thể khiến listener thứ nhất — đã thành công — chạy lại lần nữa.
- Với `@Async` hoặc custom multicaster executor, lỗi listener không tự quay lại publisher; việc publisher trả về không có nghĩa xử lý đã thành công.
- Spring application events trong một JVM **không tự lưu bền vững** qua process crash. In-memory retry với thread sleep không thay thế durable queue/outbox.

Vì vậy thường cần retry tại **ranh giới thao tác lỗi cụ thể** — ví dụ `notificationClient.send(...)` — thay vì bao toàn bộ publish/fan-out một cách mù quáng.

```text
Application service
      |
      +-- publishEvent(NotificationRequested)
                     |
                     +-- AuditListener (đã thành công)
                     |
                     +-- EmailListener
                             |
                             +-- EmailClient.send(...) -> 503
                                      |
                                      +-- bounded retry/backoff
                                      +-- idempotency key
                                      +-- failure handling
```

Nếu gọi lại toàn bộ `publishEvent` sau lỗi `EmailClient`, `AuditListener` có thể chạy lại dù không liên quan. Nếu retry chỉ thao tác `EmailClient.send`, ít nhất scope của việc lặp đã được thu hẹp. Nhưng thao tác gửi email vẫn cần idempotency/deduplication khi kết quả gửi có thể không xác định.

## 3. Không phải lỗi nào cũng retry được

Phân loại lỗi dựa trên hợp đồng nghiệp vụ, API và tính chất operation:

| Tình huống | Có nên retry? | Lưu ý |
| --- | --- | --- |
| HTTP 429 Too Many Requests | Thường có | Ưu tiên giới hạn rate, tôn trọng `Retry-After` nếu có |
| HTTP 503 Service Unavailable | Thường có | Capped backoff, jitter và retry budget |
| HTTP 502/504 từ gateway | Có điều kiện | Hệ thống đích có thể đã thực hiện thao tác |
| Connection reset / timeout tạm thời | Có điều kiện | Timeout có thể để lại trạng thái **không xác định** |
| Deadlock/optimistic lock của DB | Có điều kiện | Retry lại unit of work phù hợp; không lặp side effect ngoài transaction |
| HTTP 400 / 422 do input sai | Thường không | Phải sửa payload hoặc quy tắc domain |
| HTTP 401 / 403 do quyền | Thường không | Sửa credentials/permissions; retry vô hạn vô ích |
| Resource đã tồn tại / 409 | Tùy hợp đồng | Có thể là kết quả idempotent hoặc conflict thực sự |
| Schema/payload không tương thích | Không cho tới khi sửa | Đưa vào xử lý lỗi cố định hoặc DLQ |
| Lỗi business như `ORDER_ALREADY_PAID` | Không retry máy móc | Không giả định retry sau vài mili giây sẽ giúp |

Đặc biệt **timeout không chứng minh operation chưa xảy ra**. Ví dụ một lệnh `charge(paymentId)` đã được ngân hàng xử lý nhưng response bị mất. Retry với ID mới có thể trừ tiền hai lần. Trước khi retry phải có **idempotency key ổn định** và/hoặc cơ chế truy vấn trạng thái để reconciliation.

Không nên viết:

```java
// Anti-pattern: bắt mọi lỗi và retry bất kể nguyên nhân.
catch (Exception ex) {
    Thread.sleep(100);
    publisher.publishEvent(event);
}
```

Đây là trích đoạn **không nên dùng**: nó retry toàn bộ publish, không giới hạn attempt, không kiểm tra loại lỗi và bỏ qua trạng thái các listener trước đó.

## 4. Chiến lược backoff: fixed, exponential, capped và jitter

### 4.1. Fixed delay

```text
Sau mỗi lỗi: 200ms, 200ms, 200ms, ...
```

Dễ hiểu nhưng khi hàng nghìn client cùng thất bại ở một thời điểm, chúng có thể cùng retry theo nhịp 200ms, tạo burst lặp lại.

### 4.2. Exponential backoff

Một công thức thường dùng cho **lần retry thứ k** (k bắt đầu từ 1):

\[
D_k = \min(D_{\max}, D_{\mathrm{base}} \times 2^{k-1})
\]

Trong đó `D_base` là thời gian chờ cơ sở và `D_max` là **cap**. Ví dụ `D_base = 200 ms`, `D_max = 2.000 ms`:

| Retry # | Cửa sổ chờ tối đa |
| ---: | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 2.000 ms (đã chạm cap) |
| 6 | 2.000 ms |

Không có cap hoặc deadline, thời gian chờ sẽ tăng rất lớn; cũng không nên tính `base * 2^k` bằng phép nhân không kiểm soát vì có thể overflow số nguyên ở số k lớn.

### 4.3. Full jitter

Với **full jitter**, chọn thời gian chờ ngẫu nhiên trong toàn bộ cửa sổ:

\[
W_k \sim \operatorname{Uniform}(0,D_k)
\]

hoặc khi lập trình:

```text
cap   = min(maxDelayMs, baseDelayMs * 2^(retryNumber - 1))
delay = random(0, cap)   // full jitter
```

Ví dụ khi cap là 800ms, các client có thể chọn 25ms, 330ms, 705ms... thay vì tất cả dồn vào 800ms. Điều này **không làm tổng lượng retry trở thành miễn phí**; nó chỉ phân tán những lần retry, giảm khả năng gây burst đồng bộ.

Có các biến thể khác, như *equal jitter* (chờ ít nhất một nửa cửa sổ) hoặc *decorrelated jitter* (dựa vào delay trước). Chúng có đặc tính latency/load khác nhau; khi dùng thư viện, phải hiểu đúng thuật toán chứ không chỉ thấy tham số tên `random`.

### 4.4. Min/max attempts, total elapsed time và deadline

**Max attempts** nên được định nghĩa rõ là **tính cả lần gọi đầu tiên** hay chỉ các retry. Ví dụ `maxAttempts = 4` thường nghĩa là 1 lần gọi gốc + tối đa 3 retries. Còn một số API đặt tên `maxRetries = 3` nghĩa là 3 retries sau lần đầu.

Ngoài số lần thử, cần có:

- **Per-attempt timeout**: một request không được treo vô hạn.
- **Overall deadline**: tổng thời gian retry và xử lý phải nhỏ hơn deadline nghiệp vụ.
- **Maximum delay cap**: tránh ngủ quá lâu.
- **Retry budget**: giới hạn retry so với request mới hoặc tổng retry trong một cửa sổ, trên mỗi dependency.
- **Cancellation/interrupt**: khi request bị hủy hoặc service shutdown, phải dừng retry và giải phóng tài nguyên.
- **Retry-After**: khi server gửi khuyến nghị thời gian chờ, áp dụng theo hợp đồng và giới hạn deadline; không retry trước thời gian server yêu cầu.

Tổng thời gian không chỉ là các delay. Nó còn gồm thời gian từng attempt và thời gian chờ tài nguyên. Nếu mỗi attempt timeout 5 giây, 4 attempts có thể giữ thread lâu dù backoff tổng cộng không lớn.

## 5. Ví dụ Maven + Java 17 chạy được: retry có cap, jitter và fail-fast

Ví dụ dùng Spring Framework **6.2.8** và Java 17, không dùng Spring Boot, broker hay database. Một `@EventListener` gọi fake gateway, phân biệt lỗi tạm thời với lỗi cố định. Chính sách:

- Tối đa **4 attempts** (bao gồm lần đầu).
- Exponential cap bắt đầu 200ms, nhân đôi, tối đa 2.000ms.
- Full jitter được diễn tả qua interface `DoubleSupplier` cho giá trị trong khoảng từ 0 (bao gồm) tới 1 (không bao gồm).
- Trong demo, dùng `() -> 0.5` để tạo **đầu ra xác định**, không phải random thật; production dùng `ThreadLocalRandom.current().nextDouble()`.
- `Thread.sleep(...)` chỉ để **trực quan hóa** trong console. Không dùng sleep/blocking retry ngay trong request listener đồng bộ ở production.
- Event ID giữ nguyên qua các lần thử, chuẩn bị cho cơ chế idempotency.

### 5.1. Cấu trúc dự án

```text
event-retry-backoff/
├── pom.xml
└── src/main/java/demo/RetryBackoffDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-retry-backoff</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.RetryBackoffDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/RetryBackoffDemo.java`:

```java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.DoubleSupplier;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class RetryBackoffDemo {

    public record NotificationRequested(String eventId) {}

    public static final class TemporaryDeliveryFailure
            extends RuntimeException {
        public TemporaryDeliveryFailure() {
            super("downstream temporarily unavailable");
        }
    }

    public static final class PermanentDeliveryFailure
            extends RuntimeException {
        public PermanentDeliveryFailure() {
            super("recipient permanently invalid");
        }
    }

    public static final class FakeGateway {
        private final Map<String, Integer> attempts = new HashMap<>();

        public void deliver(NotificationRequested event) {
            int number = attempts.merge(event.eventId(), 1, Integer::sum);
            String id = event.eventId();

            if ("E-STOP".equals(id)) {
                System.out.println(
                        "gateway: " + id + " permanent attempt=" + number);
                throw new PermanentDeliveryFailure();
            }

            if ("E-OUT".equals(id)
                    || ("E-OK".equals(id) && number < 3)) {
                System.out.println(
                        "gateway: " + id + " transient attempt=" + number);
                throw new TemporaryDeliveryFailure();
            }

            System.out.println(
                    "gateway: " + id + " delivered attempt=" + number);
        }
    }

    @FunctionalInterface
    public interface Sleeper {
        void sleep(long millis) throws InterruptedException;
    }

    public static final class RetryingListener {
        private static final int MAX_ATTEMPTS = 4;
        private static final long BASE_DELAY_MS = 200;
        private static final long MAX_DELAY_MS = 2_000;

        private final FakeGateway gateway;
        private final DoubleSupplier randomFraction;
        private final Sleeper sleeper;

        public RetryingListener(
                FakeGateway gateway,
                DoubleSupplier randomFraction,
                Sleeper sleeper) {
            this.gateway = gateway;
            this.randomFraction = randomFraction;
            this.sleeper = sleeper;
        }

        // failureAttempt = 1 sau khi attempt 1 thất bại.
        private long cappedWindow(int failureAttempt) {
            long cap = BASE_DELAY_MS;
            for (int i = 1; i < failureAttempt; i++) {
                cap = Math.min(MAX_DELAY_MS, cap * 2);
            }
            return cap;
        }

        @EventListener
        public void onNotification(NotificationRequested event) {
            String id = event.eventId();

            for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
                try {
                    gateway.deliver(event);
                    System.out.println("listener: " + id + " completed");
                    return;
                } catch (PermanentDeliveryFailure ex) {
                    System.out.println(
                            "listener: " + id + " non-retryable");
                    throw ex;
                } catch (TemporaryDeliveryFailure ex) {
                    if (attempt == MAX_ATTEMPTS) {
                        System.out.println(
                                "listener: " + id + " exhausted="
                                        + MAX_ATTEMPTS);
                        throw ex;
                    }

                    long cap = cappedWindow(attempt);
                    // Chính sách full jitter; demo dùng fraction = 0.5.
                    long delay = (long) (cap * randomFraction.getAsDouble());
                    System.out.println("retry: " + id
                            + " next-attempt=" + (attempt + 1)
                            + " delay=" + delay + "ms");

                    try {
                        sleeper.sleep(delay);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "Retry interrupted", interrupted);
                    }
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        FakeGateway fakeGateway() {
            return new FakeGateway();
        }

        @Bean
        RetryingListener retryingListener(FakeGateway gateway) {
            // Deterministic demo: nửa cửa sổ ở mỗi lần retry.
            // Production có thể dùng:
            // () -> ThreadLocalRandom.current().nextDouble()
            return new RetryingListener(gateway, () -> 0.5, Thread::sleep);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("=== RECOVERY ===");
            context.publishEvent(new NotificationRequested("E-OK"));

            System.out.println("=== PERMANENT ===");
            try {
                context.publishEvent(new NotificationRequested("E-STOP"));
            } catch (PermanentDeliveryFailure ex) {
                System.out.println("main: E-STOP rejected");
            }

            System.out.println("=== EXHAUSTION ===");
            try {
                context.publishEvent(new NotificationRequested("E-OUT"));
            } catch (TemporaryDeliveryFailure ex) {
                System.out.println("main: E-OUT exhausted");
            }
        }
    }
}
```

Chạy trong thư mục dự án, yêu cầu JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Các dòng do ứng dụng in (không tính thông tin phụ của Maven):

```text
=== RECOVERY ===
gateway: E-OK transient attempt=1
retry: E-OK next-attempt=2 delay=100ms
gateway: E-OK transient attempt=2
retry: E-OK next-attempt=3 delay=200ms
gateway: E-OK delivered attempt=3
listener: E-OK completed
=== PERMANENT ===
gateway: E-STOP permanent attempt=1
listener: E-STOP non-retryable
main: E-STOP rejected
=== EXHAUSTION ===
gateway: E-OUT transient attempt=1
retry: E-OUT next-attempt=2 delay=100ms
gateway: E-OUT transient attempt=2
retry: E-OUT next-attempt=3 delay=200ms
gateway: E-OUT transient attempt=3
retry: E-OUT next-attempt=4 delay=400ms
gateway: E-OUT transient attempt=4
listener: E-OUT exhausted=4
main: E-OUT exhausted
```

### 5.2. Đọc kết quả

- **E-OK**: gateway lỗi tạm thời 2 lần rồi thành công lần 3. Backoff có hai khoảng 100ms, 200ms vì fraction demo là 0.5 và cap lần lượt 200ms, 400ms.
- **E-STOP**: lỗi cố định, **không retry**; dù max attempts là 4, chỉ gọi gateway một lần.
- **E-OUT**: lỗi tạm thời kéo dài, gọi đúng 4 attempts; có ba khoảng chờ 100ms + 200ms + 400ms rồi **exhausted**. Không sleep sau lần thử cuối.
- `context.publishEvent(...)` trong ví dụ chạy đồng bộ. Khi lỗi thoát khỏi `@EventListener`, main nhận exception và in thông tin tương ứng.
- `Thread.sleep` giữ thread trong lúc backoff; toàn demo có thời gian chờ có chủ đích khoảng 1.000ms. Đây **không phải cách tổ chức production listener** nếu cần nhiều event/second.

### 5.3. Vì sao demo không sử dụng ngẫu nhiên thật?

Mục tiêu của ví dụ là có thể dự đoán chính xác stdout. Interface `DoubleSupplier` cho phép thay giá trị 0.5 bằng số ngẫu nhiên trong [0, 1) trong production, chẳng hạn:

```java
// Trích đoạn: dùng trong @Bean thay cho () -> 0.5.
() -> ThreadLocalRandom.current().nextDouble()
```

Khi dùng random thật, delay thay đổi và không thể định trước số ms trong output; trong unit test, inject một source giả để kiểm thử các biên 0, gần 1 và cap. Không seed một số cố định trong production chỉ để tạo kết quả logging "đẹp": nếu mọi instance cùng sequence jitter, chúng có thể đồng bộ lại.

### 5.4. Giới hạn quan trọng của demo

Đây là mô hình giới hạn attempts và xử lý lỗi rõ ràng, **không** phải giao hàng bền vững, rate limiting hay backpressure. `FakeGateway` chưa có idempotency thực sự và dữ liệu `attempts` chỉ nằm trong bộ nhớ. Khi hệ thống restart, trạng thái này biến mất. Nó cũng không bao gồm transaction DB, broker, deadline tổng, hay retry budget chia sẻ giữa các replica. Các yếu tố đó cần được thiết kế thêm trước khi dùng trong production.

## 6. Tại sao chỉ exponential backoff vẫn có retry storm?

Giả sử 10.000 listener bắt đầu cùng lúc, cùng chọn exponential backoff **không jitter**:

```text
t = 0ms       10.000 attempts thất bại
t = 200ms     10.000 retries #1
t = 600ms     10.000 retries #2 (200 + 400)
t = 1.400ms   10.000 retries #3 (200 + 400 + 800)
```

Backoff đã làm thưa các đợt gọi, nhưng chúng vẫn **cùng thời điểm**. Nếu downstream chỉ xử lý nổi 500 calls mỗi 100ms, các đợt retry đó tiếp tục bóp nghẹt.

Full jitter khiến mỗi client chọn thời điểm khác nhau trong cửa sổ; tuy nhiên trong hệ thống hàng nghìn replica, không nên dựa **duy nhất** vào jitter. Cần tổng ngân sách lưu lượng và khả năng bảo vệ phía downstream.

Cũng lưu ý "fixed 500ms ± 10%" thường không phân tán tốt bằng full jitter trong dải rộng khi tải quá lớn. Đổi lại full jitter đôi khi tạo delay rất gần 0; do đó rate limiter/circuit breaker là lớp bảo vệ bổ sung, đặc biệt khi có nhiều client.

## 7. Các lớp bảo vệ để chống bão retry

### 7.1. Retry budget

Giới hạn tỉ lệ retries so với số request gốc hoặc tổng attempts trong một cửa sổ. Ví dụ một policy có thể đặt "không quá 10% lưu lượng gửi đi là retry" cho mỗi dependency, hoặc dùng token bucket riêng cho retries.

Con số 10% chỉ là ví dụ, không phải mặc định Spring. Khi budget hết, **defer/fail fast** theo hợp đồng, không cứ retry cho tới khi mọi event đều hoàn thành bằng bất cứ giá nào.

### 7.2. Rate limiting và tôn trọng Retry-After

Downstream trả 429 thường có nghĩa muốn client giảm tốc. Nếu có `Retry-After`, nên phân tích/áp dụng theo HTTP contract: giá trị có thể là số giây hoặc HTTP-date. Khi giới hạn đó vượt quá deadline của command, không giữ request thread vô hạn; lưu trạng thái retryable/deferred hoặc báo trạng thái chờ.

Rate limiter kiểm soát **tốc độ**, khác với concurrency limiter kiểm soát **số in-flight operations**. Tùy tải, có thể cần cả hai.

### 7.3. Circuit breaker

Khi lỗi kỹ thuật có xu hướng kéo dài, circuit breaker có thể mở để **tạm dừng** những lời gọi chắc chắn thất bại. Sau thời gian chờ, trạng thái half-open cho phép một số request kiểm tra sự phục hồi. Không để hàng nghìn client cùng mở lại circuit và gây burst; giới hạn probe và kết hợp rate limit/jitter.

Circuit breaker không phải retry: nó ngăn lời gọi khi dependency không khỏe. Khi circuit open, operation có thể bị từ chối nhanh, được xếp lịch lại hoặc đưa vào queue tùy chính sách nghiệp vụ.

### 7.4. Concurrency limit và bulkhead

Giới hạn số handler/integration calls đang chạy để một dependency lỗi không chiếm tất cả thread, DB connections và memory. Có thể dùng semaphore, thread pool riêng, bounded queue, bulkhead hay request concurrency limiter.

Một thread pool 100 workers mà mỗi worker `sleep` 3 giây để retry sẽ nhanh chóng cạn capacity. Với workload lớn, dùng scheduler/queue với thời điểm next-attempt để **giải phóng worker** giữa các lần thử.

### 7.5. Dead-letter queue / parking lot

Sau khi hết attempts hoặc gặp lỗi cố định cần can thiệp, lưu thông tin vào DLQ hoặc trạng thái `FAILED` có thể điều tra. Đừng liên tục phát lại DLQ ngay lập tức và tạo *DLQ replay storm*. Replay nên có phê duyệt/quy tắc, rate limit, batch size và khả năng dừng.

Payload có thể chứa PII, nên cả DLQ/logs/retry headers cần áp dụng phân loại dữ liệu, thời hạn lưu và quyền truy cập.

### 7.6. Timeout và deadline

Retry chỉ hữu ích khi từng attempt có timeout phù hợp và thời gian còn đủ trong deadline. Nếu một HTTP client mặc định chờ 30 giây và maxAttempts 4, trước cả backoff đã có thể tiêu tốn tới 120 giây. Điều chỉnh connect/read/request timeout theo SLO của luồng event, không để retry làm tăng tail latency vượt yêu cầu nghiệp vụ.

## 8. Tránh retry amplification nhiều tầng

Giả sử một event consumer gọi application service; service gọi HTTP client; HTTP client SDK tự retry:

```text
Queue consumer: 3 attempts
  -> Service retry: 3 attempts
       -> SDK retry: 3 attempts
            -> Downstream có thể nhận tới 27 calls
```

Công thức gần đúng với chuỗi các tầng retry độc lập: \(\prod_i A_i\), trong đó `A_i` là số attempts tối đa của tầng i. Với 3 tầng mỗi tầng 3 attempts: \(3 \times 3 \times 3 = 27\).

Không phải mọi lần sẽ chạm mức đó, nhưng ví dụ cho thấy vì sao **không nên bật default retry ở tất cả tầng mà không điều phối**. Thực tế cần chỉ định rõ:

- Tầng **nào sở hữu retry** cho lỗi network hoặc broker?
- Thư viện SDK đã retry trước khi trả lỗi chưa?
- Sau khi listener exhausted, queue sẽ retry lại toàn bộ event với attempt counter riêng không?
- Một attempts của consumer có tạo bao nhiêu attempts tới downstream?
- Retry budget có áp cho tổng calls trên dependency không?
- Correlation ID và event ID có giữ nguyên khi truyền qua các tầng không?

Ưu tiên retry ở tầng **biết rõ idempotency và outcome**, nơi có thể quyết định tiếp tục/chuyển sang delayed queue hoặc báo lỗi. Với broker consumer, nhiều framework có cấu hình retry/delay/backoff/DLQ riêng: không bọc thêm vòng retry trong listener nếu nó lặp lại chính cơ chế mà broker đã cung cấp.

## 9. Idempotency và kết quả không xác định

Một retry có thể trùng tác dụng phụ ngay cả khi code chỉ retry **khi có exception**:

```text
Worker gửi request idempotencyKey=E-100
     |
     +-- downstream ghi thành công
     +-- response mất / timeout
     |
     +-- worker nhận exception, không biết đã thành công
     +-- retry idempotencyKey=E-100
     |
     +-- downstream trả lại kết quả cũ, không áp dụng tác dụng phụ lần 2
```

Mẫu thiết kế:

1. Gán `eventId` ổn định khi tạo business fact.
2. Dùng eventId hoặc operation-specific idempotency key theo hợp đồng downstream.
3. Consumer hoặc downstream lưu trạng thái đã xử lý cùng key trong storage có unique constraint/atomic compare-and-set.
4. Nếu nhận lại cùng key, trả kết quả đã ghi hoặc skip tác dụng phụ theo chính sách.
5. Không sinh ID mới cho mỗi retry của cùng một event nếu muốn dedup.
6. Có chính sách TTL/retention cho dedup keys đủ bao phủ retry window và các lần replay.

Hạn chế: idempotency phải **thực sự được phía nhận thực thi**; chỉ truyền một HTTP header tên "Idempotency-Key" không có tác dụng nếu downstream không hỗ trợ. Unique event ID cũng không tự ngăn gọi email/SMS hai lần nếu dedup được thực hiện sau side effect.

Với thanh toán, gửi tiền và các hành vi không thể đảo ngược đơn giản, ưu tiên kiểm tra trạng thái/reconciliation thay vì mặc định retry sau timeout.

## 10. Transaction, @TransactionalEventListener và durable retry

### 10.1. Listener đồng bộ trong transaction

Nếu service đang `@Transactional` phát event rồi listener gọi REST API với retry/sleep:

- Thread và transaction có thể bị giữ trong các khoảng backoff.
- Transaction DB có thể giữ lock/connection lâu hơn.
- Sau khi các lần retry thất bại, exception của listener có thể làm transaction rollback.
- Nếu remote API đã thành công ở lần thử trước nhưng caller nhận timeout, rollback DB **không undo** tác dụng phụ ngoài DB.

Vì vậy không nên làm external I/O lâu dài trong listener đồng bộ ở giữa transaction chỉ để "đảm bảo retry".

### 10.2. AFTER_COMMIT giảm coupling nhưng chưa durable

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chỉ thực thi callback sau khi transaction liên quan commit thành công. Nó phù hợp khi muốn không gửi thông báo cho một transaction bị rollback. Tuy nhiên sau commit, lỗi của callback **không thể rollback commit đã hoàn thành**.

Nếu process chết sau commit nhưng trước khi thực hiện callback, event in-memory có thể mất. Annotation after-commit không tự biến event thành job retry bền vững. Với listener sau commit cần ghi DB mới, phải xét việc mở transaction độc lập phù hợp, vì resource transaction cũ có thể vẫn tồn tại nhưng không có commit tiếp theo.

### 10.3. Transactional outbox + delayed relay

Khi yêu cầu "không mất event dù process crash", lưu một outbox record cùng transaction cập nhật state:

```text
BEGIN TRANSACTION
  UPDATE orders SET status = 'PAID' WHERE id = ?
  INSERT INTO outbox(
      event_id, type, payload, attempts, next_attempt_at, state)
COMMIT

Relay worker:
  claim một số row READY đến hạn, có concurrency limit
  -> gọi downstream với stable idempotency key
  -> thành công: mark DELIVERED
  -> transient failure: attempts++, đặt next_attempt_at với backoff+jitter
  -> permanent failure hoặc exhausted: mark FAILED/DLQ
  -> tiếp tục batch nhỏ, có rate limit và metrics
```

Một relay đa replica cần cơ chế **claim/lease hoặc row locking** để tránh xử lý cùng row quá mức; lease hết hạn và crash vẫn có thể gây duplicate nên idempotency vẫn cần. Bảng outbox là hàng đợi bền vững: việc relay gửi thành công rồi chết trước khi mark DELIVERED có thể khiến event được gửi thêm lần nữa.

`next_attempt_at` giúp backoff mà **không phải giữ worker thread ngủ**. Worker chỉ lấy những row đến hạn, đặt lịch attempt sau và giải phóng tài nguyên. Với throughput cao hoặc tích hợp liên dịch vụ, delayed broker messages và queue redelivery policy có thể thay thế/đi cùng outbox, nhưng phải điều phối số lần retry giữa các tầng.

### 10.4. Không retry toàn bộ publish/fan-out một cách mù quáng

`publishEvent(event)` là handoff tới multicaster, không cam kết mọi listener đã hoàn tất. Trong đồng bộ, listener thứ nhất có thể thành công nhưng listener thứ hai throw; nếu service retry `publishEvent`, listener thứ nhất chạy lại.

Một hướng tốt hơn là retry **operation idempotent trong từng handler**, hoặc tách handler thành công việc bền vững riêng với event ID và chính sách retry của từng consumer. Tránh biến số lần publish từ 1 thành n chỉ vì một listener bên ngoài tạm không khả dụng.

## 11. Spring Retry, Framework 7 và các thư viện resilience

Với **Spring Retry 2.x** (thư viện riêng), có `@Retryable`, `@Backoff`, `RetryTemplate` và annotation cấu hình `@EnableRetry`. Ví dụ trích đoạn cho một **service bean được Spring proxy gọi qua boundary phù hợp**:

```java
// Spring Retry 2.x: trích đoạn, chưa phải chương trình độc lập.
// Cần spring-retry, Spring AOP/config và @EnableRetry phù hợp.
@Retryable(
    retryFor = TemporaryDeliveryFailure.class,
    maxAttempts = 4,
    backoff = @Backoff(
        delay = 200,
        multiplier = 2,
        maxDelay = 2000))
public void callDownstream(NotificationRequested event) {
    gateway.deliver(event);
}
```

Trong Spring Retry 2.x, `maxAttempts=4` **bao gồm lần gọi đầu tiên**. Phương thức phải được invoke qua cơ chế Spring proxy/aspect phù hợp; tự gọi `this.callDownstream(...)` trong cùng bean có thể bypass advice. Cấu hình `@Backoff` ở trên không mặc nhiên là **full jitter**. Muốn jitter đúng yêu cầu, kiểm tra backoff policy/implementation và cấu hình được hỗ trợ bởi phiên bản thực tế.

Một điểm dễ nhầm: **Spring Framework 7.0** đưa các resilience features như `org.springframework.resilience.annotation.Retryable` vào core framework. Thuộc tính và semantics khác Spring Retry 2.x, ví dụ `maxRetries` là số retry bổ sung sau lần đầu. **Không copy nguyên tham số `maxRetries` sang Spring Retry `maxAttempts`**, và không dùng package/framework version khác trong cùng snippet.

Resilience4j cũng có Retry, RateLimiter, CircuitBreaker, Bulkhead và TimeLimiter. Chọn công cụ theo yêu cầu; quan trọng hơn tên thư viện là:

- Phân loại lỗi retryable chính xác.
- Config attempts/deadline/delay và jitter.
- Đồng bộ hóa với HTTP client SDK/broker retry có sẵn.
- Giới hạn concurrency/rate và có circuit breaker khi cần.
- Idempotency, metrics, logging và xử lý exhausted.
- Đánh giá runtime blocking hay non-blocking với workload thực.

## 12. Kiểm thử chính sách backoff và chống retry storm

Không nên dùng `Thread.sleep` thật trong mọi unit test; dễ chậm và flaky. Thiết kế retry policy cho phép inject `Sleeper`/scheduler, source random và clock để deterministic test.

Với ví dụ mục 5, có thể tạo `Sleeper` giả chỉ ghi lại delay vào list, và `DoubleSupplier` trả về 0.5. Sau đó kiểm tra:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Gateway thành công lần đầu | 1 attempt, 0 delay |
| Lỗi tạm 2 lần rồi thành công | 3 attempts, delay ghi nhận [100, 200]ms |
| Lỗi cố định | 1 attempt, không sleep, exception đúng loại |
| Lỗi tạm kéo dài | 4 attempts, đúng 3 khoảng chờ [100, 200, 400]ms, exhausted |
| Random fraction = 0 | Delay có thể 0, không âm |
| Fraction gần 1 | Delay không vượt cap |
| Exception do interrupt | Giữ interrupted flag, dừng retry |
| Nhiều listener | Không tự retry toàn bộ publish khi một listener lỗi |
| Duplicate event ID | Consumer/downstream không lặp side effect |
| Burst 429/503 | Retry budget, rate limit và queue depth ngăn overload |
| Process crash sau commit | Outbox/delayed queue có thể tiếp tục |
| Retry-After lớn hơn deadline | Defer/fail theo policy, không block vô hạn |

### Kiểm thử hành vi retry tại đúng tầng

1. **Unit test retry executor/handler**: assert số attempts, loại lỗi, sequence delay và dừng đúng điều kiện.
2. **Spring integration test**: đảm bảo `@EventListener` thực sự nhận event, exception handling đúng, không vô tình multiply số lần publish.
3. **Transaction test**: listener sync thất bại trước commit gây outcome theo rollback policy; after-commit failure không giả mạo rollback.
4. **Outbox integration test**: event và state cùng transaction; retry sau restart, multiple relays, lease expiry, idempotent consumer.
5. **Load/chaos test**: cho downstream trả 429/503 đồng loạt, xem traffic retry có phân tán theo jitter, có đạt rate cap, không bùng thread/queue, recovery trở lại bình thường.
6. **Monitoring test**: metric retry attempts, exhausted, rejected, queue lag và dependency availability đều phản ánh trạng thái thật.

Bản thân việc unit test đếm đúng attempts **không chứng minh** đã chống retry storm trong deployment nhiều instance. Cần kiểm tra tải tổng hợp và các cơ chế điều tiết tài nguyên thực tế.

## 13. Observability và vận hành

Nên đo những chỉ số khác nhau:

| Metric / log dimension | Giúp trả lời |
| --- | --- |
| `event.publish.attempts` | Có bao nhiêu event được yêu cầu phân phối? |
| `handler.attempts` | Có bao nhiêu lần handler thực thi, kể cả retry? |
| `handler.success` / `handler.failure` | Tỷ lệ thành công thật là bao nhiêu? |
| `retry.attempts` | Retry chiếm bao nhiêu tỷ lệ tải? |
| `retry.exhausted` | Bao nhiêu công việc đã hết budget? |
| `retry.delay` | Phân phối thời gian chờ thực tế thế nào? |
| `downstream.429` / `downstream.503` | Dependency đang bị giới hạn hay không khả dụng? |
| `queue.depth` / `queue.oldest.age` | Work tồn đọng có đang tăng không? |
| `rate_limiter.rejected` | Có chạm trần lưu lượng không? |
| `circuit.state` | Circuit đang closed, open hay half-open? |

Spring Framework không tự tạo Observation cho mọi `@EventListener` chỉ vì có Micrometer. Muốn metric cho số lần retry, delay và outcome cần instrument đúng vị trí hoặc dùng metrics/hook của thư viện đã cấu hình.

Không dùng eventId, email, userId hoặc raw exception message làm **low-cardinality tag**. Có thể đưa correlation/event ID đã được phân loại vào log/trace phù hợp, nhưng tránh lộ PII và secret. Metric nên gắn các nhãn giới hạn số lượng như event type, dependency, outcome, retryable và failure category.

Một dashboard tốt cần phân biệt offered rate, original attempts, retry rate, completion throughput và backlog. Nếu chỉ nhìn số lần gọi downstream tăng, hệ thống có thể tưởng throughput cải thiện, trong khi thực tế retries đang làm giảm tỉ lệ thành công.

## 14. Checklist triển khai

- [ ] Chỉ retry lỗi tạm thời được xác định; fail fast với lỗi nghiệp vụ/cấu hình cố định.
- [ ] Chọn chính xác tầng sở hữu retry, kiểm tra retry đã tích hợp ở SDK/broker.
- [ ] Có cap cho attempts, delay và elapsed time; đặt per-attempt timeout và overall deadline.
- [ ] Dùng exponential backoff với jitter để giảm thundering herd.
- [ ] Tôn trọng `Retry-After`, rate limit và retry budget khi dependency quá tải.
- [ ] Giới hạn concurrency và queue capacity; có backpressure/fail/defer policy.
- [ ] Không `sleep` lâu trong listener đồng bộ/transaction của request.
- [ ] Khi cần durability, dùng outbox hoặc delayed queue thay vì bộ đệm chỉ ở RAM.
- [ ] Giữ event ID/idempotency key ổn định; consumer deduplicate và reconcile kết quả không xác định.
- [ ] Không retry mù toàn bộ `publishEvent` khiến listener đã thành công chạy lại.
- [ ] Cấu hình DLQ/parking lot và replay có kiểm soát để không tạo retry storm lần hai.
- [ ] Có metrics retry, exhaustion, error, queue backlog, saturation và latency.
- [ ] Test số lần thử, delay, deadline, interrupt, permanent failure và load/burst toàn hệ thống.
- [ ] Đánh giá impact tới transaction, side effects, rollback và việc giữ thread/resource.

## 15. Câu hỏi tự kiểm tra

1. **Backoff khác retry thông thường thế nào?** — Nó kiểm soát khoảng chờ giữa các lần thử, tránh lặp ngay lập tức.
2. **Vì sao exponential backoff không jitter vẫn gây burst?** — Các client cùng thất bại có thể cùng retry ở các mốc thời gian giống nhau.
3. **Full jitter chọn delay trong dải nào?** — Từ 0 đến giới hạn exponential cap của lần retry tương ứng.
4. **Max attempts có luôn bằng max retries không?** — Không; cần xem lần gọi ban đầu được tính hay không.
5. **Vì sao phải phân loại lỗi?** — Retry lỗi cố định gây tốn tải; timeout có thể là kết quả chưa xác định.
6. **Tại sao không retry cả publishEvent khi listener thứ hai lỗi?** — Listener thứ nhất có thể đã thành công và sẽ bị gọi lại.
7. **Tại sao sleep trong @EventListener đồng bộ là nguy hiểm?** — Nó giữ publisher thread và có thể giữ transaction/lock.
8. **Một SDK retry 3 lần trong handler retry 3 lần có thể gây điều gì?** — Retry amplification; cùng operation có thể gọi xuống dưới tới 9 lần.
9. **Jitter có tự bảo đảm không overload không?** — Không; cần rate/concurrency limits, budget và circuit breaker.
10. **Vì sao cần idempotency key qua mọi retry?** — Timeout không chứng minh downstream chưa thực hiện; retry có thể tạo side effect trùng.
11. **Dùng AFTER_COMMIT là đủ để không mất event không?** — Không; crash sau commit có thể làm mất callback in-memory, cần outbox khi đòi durability.
12. **Cách giải phóng worker trong thời gian backoff ở queue là gì?** — Lưu `next_attempt_at` hoặc sử dụng delayed message/scheduler, không sleep giữ worker.
13. **Khi 429 có Retry-After, ứng dụng nên làm gì?** — Tôn trọng thời gian chờ theo contract trong giới hạn deadline/budget.
14. **Lỗi cố định nên đi đâu?** — Fail fast và/hoặc trạng thái FAILED/DLQ để sửa, không retry vô hạn.

## Tài liệu tham khảo

- [Spring Framework — Application Events và @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Retry 2.x — @Retryable API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html)
- [Spring Framework 7.0 — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html)
- [AWS Well-Architected — Control and limit retry calls](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_mitigate_interaction_failure_limit_retries.html)
- [AWS — Retry with backoff pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html)
- [AWS SDK — Retry with full jitter](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
