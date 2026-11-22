# Retry listener và điều kiện retry trong Spring Application Events

## 1. Retry là gì và vì sao listener cần chính sách retry?

Một ứng dụng Spring có thể publish `OrderConfirmed`, sau đó một `@EventListener` gửi thông báo đến dịch vụ bên ngoài. Dịch vụ có thể trả `503 Service Unavailable`, bị timeout hoặc tạm thời mất kết nối. Thất bại **không nhất thiết** đồng nghĩa công việc không bao giờ hoàn thành; thử lại có kiểm soát (*retry*) có thể phục hồi khi lỗi chỉ tồn tại trong thời gian ngắn.

Tuy nhiên, không phải lỗi nào cũng nên retry. Gửi lại một request thanh toán mà không có idempotency key có thể thu tiền hai lần. Retry một email với địa chỉ không hợp lệ chỉ tạo thêm tải. Retry vô hạn khi database đang sập có thể làm toàn bộ ứng dụng cạn thread và giữ queue ngày càng lớn.

**Cần phân biệt ba hành động:**

- **Publish:** Spring nhận một đối tượng event để chuyển đến listener phù hợp.
- **Retry:** Có chính sách gọi lại một thao tác **sau khi thao tác đó thất bại**, theo loại lỗi và giới hạn đã chọn.
- **Recovery:** Xử lý sau khi đã hết lượt thử (hoặc gặp lỗi không được retry), chẳng hạn ghi trạng thái thất bại, chuyển dead-letter hoặc báo cho hệ thống vận hành.

`ApplicationEventPublisher.publishEvent(...)` **không mặc định retry listener**. Spring Application Events cũng không tự cung cấp persistent queue, bảo đảm giao sự kiện sau crash, hay exactly-once processing. Chính ứng dụng phải xác định điều kiện retry, điều kiện dừng, vị trí giữ trạng thái công việc và cách tránh tác dụng phụ trùng lặp.

Mục tiêu của bài: hiểu khi nào được retry listener, cách kết hợp Spring Retry với `@EventListener`, ảnh hưởng đến transaction/rollback và khi nào cần chuyển sang outbox hoặc message broker.

## 2. Retry theo lỗi hay theo kết quả nghiệp vụ?

Một *retry condition* tốt thường dựa trên: **loại lỗi**, **tính an toàn của thao tác khi lặp**, **số lần đã thử**, **thời gian còn lại** và **khả năng khôi phục**.

| Tình huống | Có nên retry ngay? | Lý do / hành động phù hợp |
| --- | --- | --- |
| HTTP 503/502/504 từ hệ thống downstream | Thường có, nếu thao tác lặp an toàn | Dùng backoff, timeout, giới hạn attempts và quan sát |
| HTTP 429 rate limit | Có điều kiện | Tôn trọng `Retry-After`/quota, hạn chế đồng thời, không gửi dồn dập |
| Mất kết nối tạm thời hoặc connect timeout | Có điều kiện | Kết quả ở server có thể **chưa rõ**; cần idempotency |
| Read timeout sau khi gửi request | Rủi ro cao | Server có thể đã thực thi; chỉ retry khi có khóa chống trùng hoặc kiểm tra trạng thái |
| Deadlock hoặc lỗi khóa DB tạm thời | Có thể | Retry **toàn bộ unit of work** trong transaction mới, với giới hạn |
| HTTP 400/422 do payload không hợp lệ | Thường không | Cần sửa dữ liệu/hợp đồng, retry cùng payload không hữu ích |
| HTTP 401/403 | Thường không | Xử lý authentication/authorization; không lặp liên tục |
| Vi phạm invariant nghiệp vụ | Không | Trả lỗi hoặc xử lý bù trừ theo quy trình |
| Đơn hàng đã xử lý thành công | Không phát lại tác dụng phụ | Ghi nhận idempotency; trả kết quả đã xử lý |
| Bug code, NullPointerException | Không retry theo mặc định | Điều tra/sửa lỗi; retry không chữa bug một cách đáng tin |

**Nguyên tắc:** Không quyết định retry chỉ dựa trên việc exception là `RuntimeException`. Hãy phân loại exception đủ rõ (ví dụ `TransientProviderException` và `PermanentValidationException`). Nếu một HTTP client bọc tất cả lỗi trong cùng một class, đọc status/code/cause có kiểm soát tại adapter, rồi chuyển thành loại exception phù hợp trước khi gọi cơ chế retry.

Đối với lỗi timeout, **không có phản hồi không đồng nghĩa chưa có side effect**. Đây là lý do idempotency phải đi cùng chính sách retry.

## 3. Spring dispatch event và lỗi được nhìn thấy ở đâu?

### Listener đồng bộ (mặc định)

`SimpleApplicationEventMulticaster` mặc định dispatch listener trên luồng publish. Với một listener `@EventListener` gọi service đồng bộ:

```text
publishEvent(OrderConfirmed)
        |
        v
@EventListener nhận event
        |
        v
service xử lý
        |
        +--> thành công --> listener trả về
        |
        +--> exception không được bắt --> có thể lan ngược tới publisher
```

Nếu listener chạy trong transaction do application service đang mở, exception không được xử lý có thể làm transaction rollback tùy loại exception và cấu hình transaction. Một retry thành công hoặc recovery nuốt exception sẽ thay đổi đường lan truyền lỗi: **transaction có thể tiếp tục**, dù một thao tác phụ đã hết attempts và chưa hoàn thành.

### Listener bất đồng bộ

Nếu dùng `@Async` và có executor phù hợp, lời gọi listener chạy trên thread khác. Exception khi listener thực thi **không tự động** quay về publisher; retry cần được cấu hình trong nhánh xử lý bất đồng bộ. Số lượng retry lớn có thể chiếm worker/queue và làm nghẽn các event sau.

### Listener gắn với transaction

`@TransactionalEventListener` có thể gắn việc xử lý vào `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION`. Mặc định là `AFTER_COMMIT`; event publish ngoài transaction đang hoạt động mặc định **không kích hoạt** listener dạng này trừ khi bật `fallbackExecution = true`.

Vì thế, vị trí retry quan trọng không kém cấu hình max attempts. Retry trước commit có thể ảnh hưởng khả năng commit của nghiệp vụ gốc; retry sau commit không thể tự đảo ngược dữ liệu đã commit.

## 4. Spring Retry: @Retryable, @Recover và AOP proxy

Trong một ứng dụng **Spring Boot 3.x / Spring Framework 6.x**, có thể dùng thư viện **Spring Retry 2.x** để retry lời gọi method của bean:

- `@EnableRetry`: bật xử lý annotation retry trên các bean phù hợp.
- `@Retryable`: khai báo exception cần retry, số attempts và chính sách backoff.
- `@Backoff`: khai báo độ trễ giữa những lần thử.
- `@Recover`: xử lý khi không thể hoàn thành method `@Retryable` theo chính sách recovery.

Các annotation ở đây thuộc package **`org.springframework.retry.annotation`**. **Không trộn lẫn** chúng với API resilience annotation tích hợp của **Spring Framework 7**, vốn có cấu hình/tham số khác (ví dụ `maxRetries` thay vì `maxAttempts`). Ví dụ ở dưới cố định Spring Boot 3.x và Spring Retry để tránh nhầm ý nghĩa.

### Lưu ý quan trọng về attempts

Trong Spring Retry:

```java
@Retryable(
    retryFor = TransientProviderException.class,
    maxAttempts = 3,
    backoff = @Backoff(delay = 200))
public void deliver(DeliveryRequested event) {
    // Một lượt gọi đầu tiên + tối đa hai lượt thử lại.
}
```

Đây là **mảnh cấu hình minh họa**; `maxAttempts=3` nghĩa là **tổng cộng tối đa ba lần gọi method**, bao gồm lần đầu. Khi mỗi lần đều lỗi, không có lượt thứ tư. Số delay giữa ba lần thử tối đa là hai lần.

### Vì sao nên retry ở một service riêng?

Retry dựa trên Spring AOP proxy. Một lời gọi từ bean A sang **public method của bean B được proxy quản lý** sẽ đi qua interceptor retry. Ngược lại, một method gọi `this.deliver(...)` trong **chính instance chứa method retry** thường không đi qua proxy: annotation có thể không có hiệu lực.

Kiến trúc khuyến nghị:

```text
@EventListener bean
    |
    v
retryingService.send(event)  <-- gọi qua bean/proxy Spring
    |
    +--> retry interceptor
            |
            +--> external adapter
            +--> @Recover nếu hết attempts
```

Cách chia trách nhiệm này giữ listener mỏng, dễ kiểm thử method retry độc lập và ít phụ thuộc vào thứ tự proxy khi kết hợp `@EventListener`, `@Async`, `@Transactional`.

## 5. Ví dụ hoàn chỉnh Java 17+: retry thành công và hết attempts

Ví dụ sử dụng **Spring Boot 3.3.13**, Java 17+, Spring Retry 2.x và Spring AOP. Không cần database hoặc API thật; gateway được mô phỏng bằng exception có thể lặp lại, giúp kiểm tra chính xác số lần gọi.

Hai event được gửi:

1. `ORD-OK`: lỗi tạm thời ở lần 1 và 2, thành công ở lần 3.
2. `ORD-FAIL`: lỗi tạm thời ở cả 3 lần; `@Recover` được gọi, ghi nhận đã hết attempts.

### Cấu trúc project

```text
listener-retry-demo/
├── pom.xml
└── src/main/java/example/events/ListenerRetryDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>listener-retry-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.retry</groupId>
            <artifactId>spring-retry</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### ListenerRetryDemo.java

```java
package example.events;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.EnableRetry;
import org.springframework.retry.annotation.Recover;
import org.springframework.retry.annotation.Retryable;

@SpringBootApplication
@EnableRetry
public class ListenerRetryDemo {

    public record DeliveryRequested(String orderId) {
    }

    public static class TransientProviderException
            extends RuntimeException {
        public TransientProviderException() {
            super("Temporary delivery-provider failure");
        }
    }

    // Bean riêng để lời gọi từ listener đi qua Retry AOP proxy.
    public static class RetryingDeliveryService {
        private final Map<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();

        @Retryable(
                retryFor = TransientProviderException.class,
                maxAttempts = 3,
                backoff = @Backoff(delay = 10))
        public void deliver(DeliveryRequested event) {
            int n = attempts.computeIfAbsent(
                    event.orderId(), id -> new AtomicInteger())
                    .incrementAndGet();

            System.out.printf(
                    "ATTEMPT order=%s n=%d%n", event.orderId(), n);

            if ("ORD-FAIL".equals(event.orderId()) || n < 3) {
                throw new TransientProviderException();
            }

            System.out.println("DELIVERED order=" + event.orderId());
        }

        @Recover
        public void recover(TransientProviderException error,
                            DeliveryRequested event) {
            // Demo chỉ in log. Production phải có đường ghi lỗi
            // bền vững/đưa ra DLQ hoặc báo vận hành theo chính sách.
            System.out.println("EXHAUSTED order=" + event.orderId());
        }
    }

    public static class DeliveryListener {
        private final RetryingDeliveryService deliveryService;

        public DeliveryListener(RetryingDeliveryService deliveryService) {
            this.deliveryService = deliveryService;
        }

        @EventListener
        public void on(DeliveryRequested event) {
            deliveryService.deliver(event);
        }
    }

    @Bean
    RetryingDeliveryService retryingDeliveryService() {
        return new RetryingDeliveryService();
    }

    @Bean
    DeliveryListener deliveryListener(
            RetryingDeliveryService deliveryService) {
        return new DeliveryListener(deliveryService);
    }

    @Bean
    CommandLineRunner scenario(ApplicationEventPublisher publisher) {
        return args -> {
            publisher.publishEvent(new DeliveryRequested("ORD-OK"));
            publisher.publishEvent(new DeliveryRequested("ORD-FAIL"));
        };
    }

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ListenerRetryDemo.class);
        app.setBannerMode(Banner.Mode.OFF);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner đã được thực thi trong quá trình startup.
        }
    }
}
```

### Biên dịch, chạy và output

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q package
java -jar target/listener-retry-demo-1.0.0.jar
```

Các dòng do **mã ứng dụng** in ra theo thứ tự sau (Spring Boot có thể in log khởi động/shutdown khác):

```text
ATTEMPT order=ORD-OK n=1
ATTEMPT order=ORD-OK n=2
ATTEMPT order=ORD-OK n=3
DELIVERED order=ORD-OK
ATTEMPT order=ORD-FAIL n=1
ATTEMPT order=ORD-FAIL n=2
ATTEMPT order=ORD-FAIL n=3
EXHAUSTED order=ORD-FAIL
```

**Vì sao kết quả ổn định?**

- `@EnableRetry` kích hoạt AOP; `DeliveryListener` gọi method `deliver(...)` của **bean service riêng** để interceptor nhìn thấy lời gọi.
- Với `ORD-OK`, service ném `TransientProviderException` hai lần; interceptor chờ ngắn rồi thử lại. Lần thứ ba không ném lỗi, nên in `DELIVERED`.
- Với `ORD-FAIL`, cả ba lần đều ném exception. `@Recover` có cùng kiểu trả về `void` và nhận `TransientProviderException` cùng các tham số method gốc; Spring Retry chọn nó khi hết attempts.
- `@Recover` ở đây **trả về bình thường**, nên listener và lời gọi `publishEvent(...)` không nhìn thấy exception ở nhánh `ORD-FAIL`. Điều này **không có nghĩa công việc đã được giao thành công**. Mẫu demo cố ý cho thấy rủi ro recovery chỉ in log.
- Event dispatch trong ví dụ là **đồng bộ**, nên việc publish `ORD-OK` kết thúc rồi mới publish `ORD-FAIL`. Chương trình không dùng `@Async` và không có transaction.

**Giới hạn quan trọng:** Các biến `attempts` chỉ nằm trong bộ nhớ; restart ứng dụng sẽ mất thông tin. Một event thật cần `eventId`/idempotency key, tracking trạng thái và cơ chế phục hồi bền vững nếu không được bỏ sót việc gửi. `@Recover` không tự tạo dead-letter, không lưu job và không đảm bảo operator nhận được cảnh báo.

Phiên bản Boot 3.3.13 được dùng để bài có dependency cụ thể, không phải khuyến nghị dùng một nhánh đã hết vòng hỗ trợ cho production. Khi triển khai thật, chọn Spring Boot còn được hỗ trợ và xác minh API tương ứng.

## 6. Định nghĩa điều kiện retry và non-retryable thật rõ

Ví dụ production thường có ít nhất hai loại lỗi:

```java
public class TransientDeliveryException extends RuntimeException {
    public TransientDeliveryException(String message) {
        super(message);
    }
}

public class InvalidDestinationException extends RuntimeException {
    public InvalidDestinationException(String message) {
        super(message);
    }
}
```

Đây là **hai class minh họa** cần đặt vào hai file Java tương ứng hoặc sửa cho phù hợp class bao ngoài. Chỉ lỗi tạm thời mới cho retry:

```java
@Retryable(
    retryFor = TransientDeliveryException.class,
    noRetryFor = InvalidDestinationException.class,
    notRecoverable = InvalidDestinationException.class,
    maxAttempts = 4,
    backoff = @Backoff(delay = 100, multiplier = 2, maxDelay = 1000))
public void send(NotificationCommand command) {
    // Gọi provider; adapter chuyển HTTP/status/cause thành loại lỗi.
}
```

Đây là **đoạn method minh họa, không phải chương trình độc lập**: giả định đã có `NotificationCommand`, class exception, annotation import và bean gọi qua proxy.

- `retryFor`: cho phép thử lại khi exception thuộc nhóm được nêu.
- `noRetryFor`: loại những exception ra khỏi retry.
- `notRecoverable`: không gọi `@Recover` đối với những loại exception này; lỗi được truyền về caller. Nó hữu ích khi lỗi dữ liệu phải được nhận diện rõ, tránh ghi nhận là "đã xử lý qua recovery".
- `maxAttempts=4`: một lần đầu + tối đa ba lần thử lại.
- `delay=100, multiplier=2, maxDelay=1000`: backoff tăng dần, có giới hạn. Các số này dùng **mili-giây**; không nên chọn theo ví dụ mà phải đo tải thực.

Nếu lỗi có thể phục hồi nhưng đã hết attempts, chọn một trong hai chính sách có giải thích: để exception đi lên để caller quyết định, hoặc `@Recover` ghi trạng thái thất bại bền vững và đưa job đến hệ thống retry dài hạn. Không chỉ `catch (Exception ignored)`, vì như vậy ứng dụng không còn biết event nào xử lý thất bại.

### Có thể chọn retry qua predicate hoặc exception mapping

Với HTTP client, có thể chuyển:

```java
if (status == 429 || status == 503) {
    throw new TransientDeliveryException("Provider unavailable");
}
if (status == 400 || status == 422) {
    throw new InvalidDestinationException("Invalid request");
}
```

Đây là **mảnh mapping minh họa**, không chứa toàn bộ HTTP client. Status 429 nên dùng thông tin `Retry-After` và quota nếu có; status 503 cũng có thể biểu thị bảo trì kéo dài, khi đó retries trong cùng request không hiệu quả. Trạng thái 409, 500, timeout và connection reset cần phân loại theo API cụ thể, không có quy tắc duy nhất đúng cho mọi hệ thống.

## 7. Backoff, jitter, giới hạn thời gian và tránh retry storm

Nếu một service downstream đang quá tải, 1.000 listener cùng retry đúng mỗi giây có thể tạo **retry storm**, khiến service không có thời gian phục hồi.

Các yếu tố chính:

- **Số attempts:** giới hạn công việc lặp, tránh giữ worker vô hạn.
- **Backoff:** chờ giữa các lần retry, thường tăng dần.
- **Jitter:** thêm độ ngẫu nhiên để các worker không đồng loạt retry cùng thời điểm.
- **Max delay và deadline:** không chờ vượt ngân sách thời gian xử lý hoặc SLA.
- **Rate limit / concurrency limit:** giảm số request đồng thời, không chỉ hoãn từng request.
- **Circuit breaker:** tạm ngừng gọi khi downstream có nhiều lỗi, thay vì thêm retry không hữu ích.
- **Retry-After:** với HTTP 429/503 khi provider cung cấp gợi ý, chính sách cần cân nhắc thời gian do provider quy định.

Ví dụ backoff lý thuyết:

```text
initial delay = 200 ms
multiplier    = 2
max delay     = 2,000 ms

Giữa attempts: 200 ms, 400 ms, 800 ms, 1,600 ms, 2,000 ms...
```

Đây là chuỗi delay *nếu có đủ lần retry*, không phải cấu hình mặc định của Spring Retry. Ví dụ `maxAttempts=3` chỉ có **hai khoảng chờ**, không phải năm.

Với API có nhiều worker, thêm jitter giúp phân tán thời điểm retry; không dùng một timer đồng bộ cố định cho toàn bộ fleet. Nếu một request đã vượt deadline, tiếp tục retry chỉ làm tăng độ trễ và tải mà không giúp trải nghiệm người dùng.

**Cẩn trọng:** Backoff bằng việc ngủ trong luồng listener đồng bộ sẽ giữ luồng publisher; backoff trong worker async giữ tài nguyên worker. Khi cần retry sau nhiều phút hoặc giờ, nên chuyển sang queue/job scheduler bền vững chứ không giữ thread của Spring chờ lâu.

## 8. Retry có thể tạo side effect trùng: idempotency là bắt buộc khi cần

Giả sử listener gửi yêu cầu thu tiền:

```text
Client -> Payment API: charge ORD-101
Payment API: thu tiền thành công
Network: mất phản hồi
Client: timeout, tưởng thất bại
Client retry -> Payment API: charge ORD-101 lần nữa
```

Nếu API không có cơ chế chống trùng, một sự kiện nghiệp vụ đã được xử lý thành công có thể tạo hai side effect. **Không được suy luận timeout = chưa thực thi**.

Biện pháp:

1. Tạo **idempotency key** ổn định cho *một nghiệp vụ*, ví dụ `paymentAttemptId` hoặc `eventId`; retry phải dùng **cùng key**, không tạo key mới mỗi lượt.
2. Gửi key đó cho downstream nếu API hỗ trợ idempotency. Nếu downstream không hỗ trợ, cần check trạng thái hoặc cơ chế khóa/unique constraint tại lớp ứng dụng.
3. Consumer giữ sổ xử lý (*inbox/dedup table*) với unique key, trạng thái, kết quả xử lý và transaction phù hợp.
4. Phân biệt **đã nhìn thấy event** và **đã hoàn thành side effect**. Không ghi "processed" trước khi side effect có thể được xác nhận hoặc phục hồi đúng.
5. Nếu retry có thể chạy song song trên nhiều instance, cần chống race bằng DB unique constraint/atomic operation, không chỉ `ConcurrentHashMap` trong một JVM.

Ví dụ một idempotency key ở tầng messaging:

```json
{
  "eventId": "f6d7bc9b-5c7a-4c2d-81ec-2f0df60b30ef",
  "eventType": "order.confirmed",
  "orderId": "ORD-101",
  "createdAt": "2026-09-15T11:20:00Z"
}
```

Khi message broker giao lại bản ghi do consumer crash trước khi ACK, key `eventId` cho phép xác định đây là **cùng sự kiện được giao lại**, không phải sự kiện mới. Việc bảo đảm *exactly-once business effect* cần thiết kế nhất quán xuyên qua storage và side effect; annotation `@Retryable` tự nó không tạo bảo đảm đó.

## 9. Retry listener trong transaction: trước commit và sau commit

### 9.1. @EventListener đồng bộ khi publisher đang @Transactional

Một application service có thể thay đổi trạng thái đơn hàng rồi gọi `publisher.publishEvent(new OrderConfirmed(...))` **trong transaction chưa commit**:

```text
begin transaction
  update order
  publish event
      -> @EventListener
          -> retry send notification
commit / rollback transaction
```

Nguy cơ: listener gọi dịch vụ bên ngoài thành công, rồi transaction DB sau đó rollback. Việc gửi email/thanh toán **không tự rollback** theo DB. Hoặc retry kéo dài khiến transaction giữ khóa lâu, tăng deadlock và timeout.

Nếu listener ném unchecked exception sau khi hết retry và exception đi qua transaction boundary, transaction thường rollback theo quy tắc của Spring; nhưng nếu `@Recover` bắt lỗi và trả về bình thường, publisher có thể tiếp tục commit dù hành động phụ chưa hoàn thành. **Recovery là quyết định nghiệp vụ, không chỉ là log.**

### 9.2. @TransactionalEventListener(AFTER_COMMIT)

Khi cần chỉ xử lý sau khi cập nhật DB đã commit, có thể dùng:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderAfterCommitListener {
    private final DeliveryService deliveryService;

    public OrderAfterCommitListener(DeliveryService deliveryService) {
        this.deliveryService = deliveryService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        deliveryService.process(event);
    }
}
```

Đây là **lớp minh họa, không thuộc demo mục 5**. Nó giả định `DeliveryService`/`OrderConfirmed` được định nghĩa và event được publish **trong transaction đang hoạt động**. Không có transaction thì listener mặc định **không chạy**, vì `fallbackExecution=false`.

AFTER_COMMIT tránh gửi thông báo cho transaction đã rollback, nhưng cần hiểu:

- Khi listener chạy, transaction gốc **đã commit**; thất bại hoặc retry hết lượt **không làm transaction gốc rollback**.
- Listener có thể vẫn chạy đồng bộ trên luồng hoàn tất transaction; retry lâu có thể làm kéo dài latency trả lời, dù DB đã commit.
- Sau commit, một số tài nguyên transaction vẫn còn gắn với luồng. Nếu listener cần ghi DB **trong một transaction độc lập**, dùng service riêng với `@Transactional(propagation = Propagation.REQUIRES_NEW)` qua Spring proxy hoặc `TransactionTemplate` tạo transaction mới.
- Process crash sau DB commit nhưng trước khi listener hoàn thành vẫn có thể khiến công việc phụ **mất**.

Không chỉ gắn `@Async` lên `@TransactionalEventListener` rồi cho rằng đã giải quyết độ bền: task async cũng có thể bị từ chối hoặc mất khi process chết.

### 9.3. BEFORE_COMMIT và AFTER_ROLLBACK

- `BEFORE_COMMIT` chạy trước commit; nếu việc phụ thất bại và exception không được xử lý, commit có thể bị chặn. Nhưng việc gọi API bên ngoài trước commit vẫn có rủi ro side effect không rollback được.
- `AFTER_ROLLBACK` phù hợp để ghi nhận hoặc bù trừ sau khi transaction thất bại theo thiết kế. Nó **không tự retry toàn bộ transaction nghiệp vụ**.
- `AFTER_COMPLETION` xử lý sau khi transaction hoàn tất bất kể commit/rollback; phải kiểm tra mục tiêu nghiệp vụ trước khi thực hiện side effect.

Nếu retry một thao tác DB vì deadlock hoặc lỗi transaction, nên tổ chức retry ở **ranh giới của toàn bộ unit of work**, cho phép một attempt dùng **transaction mới**, thay vì tiếp tục gọi thêm statement trong một transaction đã bị đánh dấu rollback-only.

## 10. Khi nào @Retryable là chưa đủ? Outbox, job queue và DLQ

Một listener Spring chạy trong memory không phải broker bền vững. Với event quan trọng (thanh toán, tạo vận đơn, hoàn tiền, phân phối dữ liệu), việc "thử lại ba lần rồi thôi" thường không đáp ứng yêu cầu.

Ví dụ sự cố:

```text
DB commit order CONFIRMED
            |
            v
Application process crash
            |
            X  listener chưa chạy hoặc chưa gửi thành công
```

Ngay cả `AFTER_COMMIT` cũng không làm công việc phụ thành một record được lưu bền. **Transactional Outbox** giảm khoảng hở này:

```text
Một transaction:
  update order
  insert outbox(eventId, payload, status=NEW)
  commit
        |
        v
Outbox worker / CDC
        |
        +--> gửi thành công --> ghi nhận/ACK
        |
        +--> lỗi tạm thời --> retry theo lịch và backoff
        |
        +--> hết giới hạn / poison message --> DLQ hoặc FAILED
```

Các thành phần vận hành cần có:

- **Retry state bền vững:** số attempts, `nextRetryAt`, lỗi cuối, trạng thái, thời điểm hết hạn.
- **Idempotency:** tránh tác dụng phụ trùng khi worker crash sau khi gửi nhưng trước khi cập nhật trạng thái.
- **Visibility/lease:** tránh hai worker lấy cùng job mà không có cơ chế bảo vệ.
- **Poison-message handling:** đưa thông điệp không thể xử lý sang DLQ/quarantine, có quy trình điều tra và replay có kiểm soát.
- **Dead-letter / exhausted alert:** không âm thầm bỏ task, nhất là event nghiệp vụ quan trọng.
- **Retention và audit:** xác định giữ lại lịch sử phục vụ truy vết trong thời hạn phù hợp.

Spring Retry phù hợp với **retry ngắn trong một lần thực thi**. Outbox/broker/job scheduler phù hợp hơn với **retry dài hạn, chịu được restart/crash và nhiều instance**. Có thể kết hợp cả hai: một số lần retry nhanh trong worker, sau đó lưu thất bại và chờ lượt xử lý tiếp theo.

## 11. Thiết kế recovery thay vì chỉ nuốt exception

Một lỗi xử lý thường có ba kết quả cần biểu diễn riêng:

1. **SUCCEEDED:** side effect đã được xác nhận thành công.
2. **RETRY_SCHEDULED:** chưa thành công nhưng đã lưu trạng thái để xử lý lại.
3. **FAILED_PERMANENTLY / NEEDS_INTERVENTION:** không thể tự hoàn thành, đã có dấu vết và quy trình xử lý.

Nếu method `@Recover` chỉ ghi một dòng log rồi trả về, Spring Retry xem lời gọi method đã được recovery xử lý, còn publisher nhìn thấy lời gọi kết thúc bình thường. Điều này có thể hợp lệ nếu phương thức recovery đã **lưu một job thất bại vào queue bền vững** hoặc áp dụng chính sách nghiệp vụ rõ ràng; nó không hợp lệ nếu cần bảo đảm giao thông báo nhưng lại không lưu gì.

Một mẫu recovery rõ hơn (chỉ minh họa, yêu cầu các bean phụ thuộc được cung cấp):

```java
@Recover
public void recover(TransientDeliveryException ex,
                    DeliveryRequested event) {
    // failedDeliveryRepository phải lưu trạng thái bền vững;
    // không chỉ là log hoặc Map in-memory.
    failedDeliveryRepository.recordForLaterRetry(
            event.orderId(), ex.getMessage());
}
```

Đây là **đoạn cấu hình minh họa**, giả sử có `failedDeliveryRepository` và các kiểu đã định nghĩa. Nếu việc lưu trạng thái thất bại cũng lỗi, cần quyết định để exception lan ra hoặc chuyển sang cơ chế an toàn khác; đừng nuốt tiếp.

Nếu chính sách là lỗi phải làm publisher thất bại, **không khai báo recovery nuốt lỗi** cho loại exception đó. Dùng `notRecoverable` với nhóm exception không thể recover hoặc để exception cuối lan truyền theo hợp đồng. Quan trọng là caller biết chính xác một trong ba kết quả, thay vì coi mọi lời gọi method trả về bình thường là "gửi thành công".

## 12. Retry và thread pool: hiệu suất và backpressure

Với `@Async @EventListener` hoặc multicaster có executor:

- Mỗi listener đang đợi backoff có thể chiếm một worker và giữ tài nguyên.
- Khi tốc độ event đến lớn hơn tốc độ hoàn thành, queue sẽ tăng.
- Khi queue và pool đều đầy, executor có thể **từ chối task ngay từ lúc submit**. Đây là lỗi **chưa được listener chạy**, không phải exception phát sinh trong method retry.
- `@Retryable` bên trong listener **không tự giải quyết** lỗi nộp task từ executor.
- Nếu retry thất bại kéo dài, độ trễ end-to-end của event tăng; không được đánh đồng `publishEvent(...)` đã trả về với công việc hoàn thành.

Một hàng đợi memory có thể mất task khi process chết. Đối với event quan trọng cần bảo đảm tiếp tục sau restart, dùng job/outbox bền vững.

Bảng điều khiển tối thiểu: queue depth, active threads, số task rejected, event processing latency, số attempts, tỷ lệ retry-success, số task exhausted và lỗi downstream theo nhóm. Không chỉ đo số lần gọi `@Retryable` rồi kết luận "xử lý thành công".

## 13. Quan sát retry: metrics, logs và cảnh báo

Một số metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `listener.events.received` | Số event listener thật sự nhận |
| `listener.attempts.total` | Số lần thực thi thao tác (bao gồm cả lần đầu) |
| `listener.retries.total` | Số lần thử lại, không tính lần đầu |
| `listener.succeeded.total` | Số tác vụ hoàn thành side effect |
| `listener.exhausted.total` | Số tác vụ hết attempts nhưng chưa xong |
| `listener.permanent_failure.total` | Lỗi không retry hoặc cần sửa dữ liệu |
| `listener.retry_delay` | Độ trễ/backoff quan sát được |
| `listener.end_to_end_latency` | Từ lúc publish đến lúc kết thúc trạng thái nghiệp vụ |
| `listener.duplicate_skipped.total` | Số lần event giao lại bị chặn bởi idempotency |

Đây là **tên gợi ý cho metric ứng dụng**, không phải tên metric tự động được Spring Boot xuất ra. Với Micrometer, gắn tag loại event, loại lỗi, tên provider và kết quả; **không gắn `eventId`/`orderId` làm tag** vì sẽ tạo cardinality rất lớn. Đưa các ID vào log/tracing được kiểm soát quyền truy cập.

Các trường log hữu ích: event type, eventId, attempt/maxAttempts, retry decision, next retry time, error category, correlation/trace ID và kết quả cuối. Tránh ghi token, secret và toàn bộ payload chứa PII vào log lỗi.

Cảnh báo nên kích hoạt khi `exhausted` hoặc `permanent_failure` tăng ở loại event quan trọng, khi queue tồn đọng kéo dài hoặc tỷ lệ retry tăng đồng thời latency xấu đi. Số retry tăng chưa hẳn là lỗi nếu hệ thống vẫn hoàn thành nhanh và trong ngưỡng; điều cần quan tâm là khả năng hoàn thành nghiệp vụ và tác động đến upstream.

## 14. Ma trận kiểm thử: retry đúng và dừng đúng

| Tình huống | Cần khẳng định |
| --- | --- |
| Thành công ngay lần đầu | `deliver()` gọi đúng 1 lần, không backoff |
| Lỗi tạm thời 2 lần rồi thành công | Tổng đúng 3 attempts; không gọi `@Recover` |
| Lỗi tạm thời liên tục đến giới hạn | Tổng đúng `maxAttempts`; recovery hoặc exception cuối theo chính sách |
| Lỗi không retryable | Không lặp; exception/recovery theo `noRetryFor` và `notRecoverable` |
| Listener gọi method retry qua bean khác | AOP interceptor thực sự được áp dụng |
| Method gọi qua `this.method()` | Test phát hiện self-invocation không được proxy retry |
| Publish event đồng bộ khi listener ném lỗi | Publisher thấy exception theo cấu hình multicaster/handler |
| `@Async` listener ném lỗi | Publisher không bị coi là đã nhận exception xử lý async |
| Event phát trong transaction và AFTER_COMMIT listener | Chỉ xử lý sau commit thành công |
| Transaction rollback | AFTER_COMMIT không thực hiện side effect |
| Publish ngoài transaction | `@TransactionalEventListener` mặc định không chạy |
| Timeout sau khi downstream đã xử lý | Retry không tạo tác dụng phụ trùng nhờ idempotency |
| Worker/process restart giữa các attempts | Với mô hình bền vững, job có thể tiếp tục theo trạng thái lưu |
| Task bị executor reject trước khi chạy | Được ghi nhận riêng, không nhầm với retry exception bên trong |
| Downstream trả 429 | Tuân thủ rate-limit/backoff; không tạo retry storm |
| Poison event luôn lỗi dữ liệu | Chuyển DLQ/quarantine, không lặp vô hạn |

### Gợi ý kiểm thử trong Spring Boot

- Dùng mock/stub gateway có bộ đếm attempt và lỗi theo kịch bản; assert số lần gọi và kết quả cuối.
- Kiểm thử qua bean thật trong Spring context để chắc chắn AOP proxy hoạt động; gọi `new RetryingDeliveryService()` trong unit test sẽ **không** tự kích hoạt `@Retryable`.
- Với test transaction AFTER_COMMIT, cẩn trọng: nhiều test Spring mặc định rollback sau test nếu đặt `@Transactional`. Muốn quan sát AFTER_COMMIT, phải có **commit thật** hoặc dùng API test transaction phù hợp.
- Với async, dùng latch hoặc cơ chế chờ điều kiện có timeout thay vì `Thread.sleep(...)` tùy tiện; không assert thứ tự hoàn thành nếu thiết kế không bảo đảm.
- Với outbox, mô phỏng crash giữa "downstream đã nhận" và "đánh dấu outbox sent" để xác nhận idempotency.

Trong demo mục 5, hai tình huống `ORD-OK` và `ORD-FAIL` đã chứng minh số attempts/đường recovery. Để kiểm thử fail-fast với exception vĩnh viễn, cần bổ sung adapter ném `InvalidDestinationException` và policy `noRetryFor/notRecoverable` như mục 6.

## 15. Lỗi phổ biến khi thêm retry cho event listener

**Lỗi 1 — Cho rằng Spring tự retry mọi listener.** `publishEvent(...)` không phải durable broker; lỗi có thể lan ngược, bị xử lý bởi error handler hoặc xảy ra trên thread async. Phải cấu hình retry minh bạch.

**Lỗi 2 — @Retryable đặt trên method gọi bằng this.** Spring Retry dùng proxy; self-invocation thường bypass interceptor. Gọi bean service riêng qua DI.

**Lỗi 3 — Retry mọi RuntimeException.** Lỗi validation và lỗi nghiệp vụ không tự hết; phân loại exception để tránh storm.

**Lỗi 4 — Không kiểm soát số attempts/độ trễ.** Retry vô hạn hoặc backoff quá lớn có thể giữ thread và làm nghẽn queue.

**Lỗi 5 — Retry sau timeout mà không có idempotency.** API có thể đã xử lý thành công. Dùng key ổn định và cơ chế dedup.

**Lỗi 6 — @Recover chỉ log rồi trả về.** Listener coi việc đã giải quyết xong trong khi công việc thật sự thất bại. Lưu trạng thái, gửi cảnh báo hoặc làm exception lan ra theo hợp đồng.

**Lỗi 7 — Nhầm rollback của DB với rollback side effect bên ngoài.** Email và HTTP call đã gửi không thể được Spring transaction tự động đảo ngược.

**Lỗi 8 — Coi AFTER_COMMIT là delivery guarantee.** Process có thể chết sau commit trước khi hoàn thành listener. Dùng outbox khi không được mất event.

**Lỗi 9 — Đưa retry DB vào transaction đã rollback-only.** Khi attempt đầu làm transaction không còn dùng được, retry từng câu lệnh trong cùng transaction là không đủ; cần lặp toàn bộ unit of work với transaction mới.

**Lỗi 10 — Quên rằng async có lỗi submit riêng.** Executor rejection xảy ra trước listener; cần theo dõi/bảo vệ cả đường nộp tác vụ.

**Lỗi 11 — Trộn API retry giữa các thế hệ Spring.** Spring Retry 2.x dùng `org.springframework.retry.annotation.Retryable` với `maxAttempts`; Spring Framework 7 có resilience API khác. Xác minh import/dependency và semantics trước khi sao chép ví dụ.

## 16. Checklist triển khai

Trước khi đưa retry listener lên production:

1. Đã phân loại **transient** và **permanent** theo exception/status nghiệp vụ chưa?
2. Tác vụ có **an toàn khi lặp** không? Nếu không, đã có idempotency key/unique constraint chưa?
3. Đã xác định `maxAttempts`, backoff, jitter, deadline, rate limit và timeout chưa?
4. Method có thực sự được gọi **qua Spring retry proxy** không?
5. Với `@Recover`, đã lưu/định tuyến kết quả thất bại thay vì chỉ log chưa?
6. Listener chạy đồng bộ hay bất đồng bộ, có ảnh hưởng request/thread pool/queue không?
7. Event liên quan DB phải chạy `BEFORE_COMMIT` hay `AFTER_COMMIT`, và tại sao?
8. Nếu cần retry một transaction DB thất bại, đã thiết kế **transaction mới cho mỗi attempt** chưa?
9. Nếu process chết hoặc restart, event quan trọng có cơ chế khôi phục qua outbox/broker/job store không?
10. Có metric/log cho attempts, succeeded, exhausted, rejected, lag và duplicate không?
11. Có test cho thành công, hết attempts, lỗi vĩnh viễn, rollback, async và idempotency không?

**Kết luận:** Retry listener không chỉ là "gọi lại sau khi lỗi". Một cơ chế retry đúng phải có **điều kiện thử lại rõ ràng, số lần và thời gian hữu hạn, idempotency, kết quả recovery minh bạch và ranh giới transaction phù hợp**. Dùng Spring Retry cho các lỗi ngắn hạn trong một lần xử lý; dùng lưu trữ bền vững và luồng retry dài hạn khi sự kiện không được phép mất.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): dispatch mặc định, listener đồng bộ và bất đồng bộ.
- [Spring Retry — Project documentation](https://github.com/spring-projects/spring-retry): `@EnableRetry`, `@Retryable`, `@Recover` và API Spring Retry 2.x.
- [Spring Retry — Retryable annotation](https://github.com/spring-projects/spring-retry/blob/main/src/main/java/org/springframework/retry/annotation/Retryable.java): `retryFor`, `noRetryFor`, `notRecoverable`, `maxAttempts`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và các transaction phases.
- [Spring Framework 7 — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html): API resilience mới; lưu ý phân biệt với Spring Retry khi xem ví dụ.
