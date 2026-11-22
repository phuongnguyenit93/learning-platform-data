# Timeout và Retryer trong Spring Cloud OpenFeign: kiểm tra hành vi mặc định thực tế

## Mục tiêu

Khi gọi một dịch vụ qua OpenFeign, câu hỏi quan trọng không chỉ là “đặt timeout bao nhiêu?”, mà còn là **lần gọi thất bại có được gửi lại không, ai gửi lại và gửi lại tới instance nào?** Hai ứng dụng dùng cùng interface `@FeignClient` vẫn có thể có hành vi khác nhau vì phiên bản Feign, cấu hình Spring Cloud OpenFeign, HTTP client được chọn và Spring Cloud LoadBalancer.

Sau bài này, bạn có thể:

- Phân biệt `connectTimeout`, `readTimeout` với giới hạn tổng thời gian của một yêu cầu.
- Giải thích sự khác nhau giữa `Retryer.Default` trong **Feign gốc** và `Retryer.NEVER_RETRY` do **Spring Cloud OpenFeign** cung cấp mặc định.
- Tự kiểm tra số request thực sự tới server bằng một phép thử có timeout, thay vì đoán từ tên dependency hoặc log phía client.
- Cấu hình retry có chủ đích và nhận ra retry của Feign khác retry của Spring Cloud LoadBalancer.
- Chọn chính sách cho các lệnh đọc và ghi để tránh nhân đôi tác dụng phụ khi kết nối có lỗi.

**Bối cảnh:** Module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` tập trung vào giao tiếp giữa các service bằng `service ID`, discovery, chọn `ServiceInstance`, health check và định tuyến phía client. OpenFeign là một trong các HTTP client có thể tham gia luồng này. Bài học đi sâu vào timeout và retry, vì chúng ảnh hưởng trực tiếp tới khả năng phục hồi, độ trễ và việc chọn lại instance khi lỗi xảy ra.

## 1. Timeout và retry nằm ở đâu trong đường đi của request?

```mermaid
sequenceDiagram
    participant App as Service gọi
    participant Feign as OpenFeign
    participant LB as Spring Cloud LoadBalancer
    participant Target as ServiceInstance
    App->>Feign: Gọi phương thức interface
    Note over Feign: Request.Options: connect/read timeout<br/>Retryer: xử lý RetryableException
    Feign->>LB: HTTP request theo service ID (khi dùng discovery)
    Note over LB: Chọn instance; có thể có<br/>chính sách retry riêng
    LB->>Target: Gửi HTTP request
    Target-->>LB: Phản hồi hoặc lỗi
    LB-->>Feign: Kết quả cuối cùng của tầng LB
    Feign-->>App: Giá trị hoặc exception
```

`connectTimeout` là thời gian chờ thiết lập kết nối tới đích. `readTimeout` thường là giới hạn thời gian chờ đọc dữ liệu từ kết nối đã thiết lập. Cách đo cụ thể phụ thuộc HTTP client nền (JDK, Apache HttpClient 5, OkHttp nếu được cấu hình) và loại thao tác mạng.

Một số giới hạn dễ bị hiểu nhầm:

| Cơ chế | Kiểm soát điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| `connectTimeout` | Chờ mở kết nối TCP tới endpoint | Không phải timeout cho toàn bộ lần gọi; DNS, lấy kết nối từ pool và TLS có thể có quy tắc riêng |
| `readTimeout` | Chờ đọc dữ liệu trên kết nối sau khi gửi yêu cầu | Không nhất thiết là tổng thời gian tải response, đặc biệt với response truyền theo nhiều đợt |
| Feign `Retryer` | Quyết định có thử lại khi Feign nhận `RetryableException` | Không tự động thử lại mọi mã HTTP 4xx/5xx |
| Spring Cloud LoadBalancer retry | Có thể thử lại thao tác HTTP và/hoặc đổi `ServiceInstance` tùy client, classpath và cấu hình | Không được suy ra chỉ từ bean `Retryer` của Feign |
| Circuit breaker / time limiter | Có thể hạn chế hoặc ngắt lời gọi ở một lớp khác, khi được tích hợp | Không thay thế việc xác định timeout và số lần gửi thực tế |

Ví dụ, một phương thức mất 2 giây có thể vượt `readTimeout=500ms`; nếu có 3 lần thử, tổng độ trễ có thể dài hơn 500 ms rất nhiều. **Timeout của một lần thử không phải deadline cho toàn bộ thao tác nghiệp vụ.**

## 2. Hành vi mặc định: phân biệt Feign gốc và Spring Cloud OpenFeign

Đây là điểm dễ gây kết luận sai nhất:

1. **Feign core** có một `Retryer.Default` mặc định: nó có thể thử lại khi nhận lỗi được biểu diễn thành `RetryableException`, chẳng hạn một số lỗi I/O tạm thời hoặc lỗi do `ErrorDecoder` chuyển thành retryable.
2. **Spring Cloud OpenFeign** mặc định cung cấp `Retryer.NEVER_RETRY` cho Feign client của mình. Chính sách này **không tiếp tục thử lại tại tầng Feign** khi gặp `RetryableException`. Đây là khác biệt có chủ đích so với Feign core.
3. Cấu hình riêng từng client, bean `Retryer` tùy biến, cấu hình HTTP transport hoặc một cơ chế retry ở tầng khác có thể thay đổi kết quả cuối cùng.

Không nên ghi nhớ máy móc rằng “gặp HTTP 500 thì Feign sẽ gọi 3 lần”. Với `ErrorDecoder` mặc định, **một mã 500/503 thông thường không nhất thiết là `RetryableException`**. Header `Retry-After` hoặc `ErrorDecoder` tự viết có thể làm thay đổi cách phân loại lỗi. Ngay cả khi lỗi được phân loại là retryable, `Retryer.NEVER_RETRY` vẫn ngăn retry ở **tầng Feign**.

Ngoài ra, tài liệu hoặc ví dụ dành cho thư viện `feign-core` thuần túy không thể dùng làm bằng chứng về mặc định trong một ứng dụng Spring Cloud. Cũng không nên lấy các con số timeout của một phiên bản thư viện làm cam kết cho mọi phiên bản: **đọc cấu hình đang có và kiểm chứng trên chính dependency/HTTP client của dự án**. Các bản Feign phổ biến sử dụng mặc định `Request.Options` khoảng 10 giây cho kết nối, 60 giây cho đọc, nhưng ứng dụng có thể đã ghi đè hoặc chọn transport khác.

## 3. Cấu hình timeout cho một Feign client

Giả sử `order-service` gọi `stock-service` để đọc tồn kho. Interface cơ bản:

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "stock-service")
public interface StockClient {
    @GetMapping("/stocks/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}

public record StockResponse(String sku, int available) {}
```

Khi có Spring Cloud LoadBalancer và cơ chế service discovery tương ứng, tên `stock-service` được dùng để tìm/chọn instance. Một cấu hình minh họa trong `application.yml`:

```yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          stock-service:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: BASIC
```

`connectTimeout` và `readTimeout` ở đây tính bằng **mili giây**. Đây là giá trị **chủ động cấu hình**, không phải các giá trị mặc định được suy đoán. Trong thực tế, chọn chúng theo độ trễ quan sát được, SLO, tình trạng mạng, số lần thử được phép và giới hạn thời gian của request phía trên.

Có thể đặt cấu hình chung ở `spring.cloud.openfeign.client.config.default`, rồi ghi đè theo tên client. Cấu hình bằng properties có thể được ưu tiên hơn Java configuration theo cơ chế và phiên bản Spring Cloud OpenFeign; trong các phiên bản hỗ trợ, tùy chọn `spring.cloud.openfeign.client.default-to-properties` ảnh hưởng thứ tự ưu tiên. Kiểm tra giá trị thực tế thay vì chỉ nhìn một `@Bean`.

Muốn thử riêng hành vi của Feign, có thể cung cấp URL trực tiếp:

```java
@FeignClient(name = "stock-service", url = "${stock.service.url}")
public interface StockClient {
    @GetMapping("/stocks/{sku}")
    String getStock(@PathVariable("sku") String sku);
}
```

Với `url` cố định, lần gọi đi trực tiếp tới URL đó: phép thử này hữu ích để cô lập retry của Feign khỏi việc chọn instance qua LoadBalancer. Trong môi trường dùng discovery, bỏ `url` để sử dụng `service ID` và kiểm tra thêm tầng LoadBalancer.

## 4. Tự kiểm chứng mặc định thay vì đoán: thử nghiệm một request chậm

### Giả thuyết cần kiểm tra

Với Spring Cloud OpenFeign chưa cấu hình `Retryer` riêng, endpoint giữ kết nối nhưng trả lời chậm hơn `readTimeout` thì:

- Caller nhận exception liên quan đến read timeout.
- Server **chỉ nhận một HTTP request** do Feign gửi; không có Feign retry mặc định.
- Khi đổi chính sách retry, số request có thể tăng. Nếu bật retry ở LoadBalancer hoặc gateway, phải tính riêng các tầng đó.

### Ví dụ kiểm thử tích hợp bằng HTTP server của JDK

Ví dụ dưới đây dùng JUnit 5 và `@SpringBootTest`; cần `spring-cloud-starter-openfeign` cùng dependency kiểm thử của Spring Boot. HTTP stub sử dụng `com.sun.net.httpserver.HttpServer` của JDK nên không phải cài WireMock. Đặt lớp vào `src/test/java` của ứng dụng Spring Boot và bảo đảm các version Spring Boot/Spring Cloud tương thích.

```java
import com.sun.net.httpserver.HttpServer;
import feign.RetryableException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
    classes = TimeoutRetryBehaviorTest.TestApp.class,
    properties = {
        "spring.cloud.openfeign.client.config.stock-service.connectTimeout=300",
        "spring.cloud.openfeign.client.config.stock-service.readTimeout=200",
        "spring.cloud.loadbalancer.retry.enabled=false"
    }
)
class TimeoutRetryBehaviorTest {
    private static final AtomicInteger REQUESTS = new AtomicInteger();
    private static final HttpServer STUB = startStub();

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableFeignClients(clients = StockClient.class)
    static class TestApp {}

    @FeignClient(name = "stock-service", url = "${stock.service.url}")
    public interface StockClient {
        @GetMapping("/stocks/{sku}")
        String getStock(@PathVariable("sku") String sku);
    }

    @Autowired
    StockClient client;

    @DynamicPropertySource
    static void setProperties(DynamicPropertyRegistry properties) {
        properties.add("stock.service.url",
            () -> "http://127.0.0.1:" + STUB.getAddress().getPort());
    }

    @Test
    void timeoutDoesNotCauseFeignRetryByDefault() {
        assertThrows(RetryableException.class,
            () -> client.getStock("SKU-1"));
        assertEquals(1, REQUESTS.get(),
            "Default OpenFeign Retryer must not resend the request");
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/stocks", exchange -> {
                REQUESTS.incrementAndGet();
                try {
                    Thread.sleep(800); // Chậm hơn readTimeout=200ms
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
                byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, body.length);
                    try (var stream = exchange.getResponseBody()) {
                        stream.write(body);
                    }
                } catch (IOException clientDisconnected) {
                    // Client có thể đóng kết nối sau khi timeout.
                } finally {
                    exchange.close();
                }
            });
            server.start();
            return server;
        } catch (IOException error) {
            throw new IllegalStateException("Cannot start local HTTP stub", error);
        }
    }
}
```

**Đọc kết quả:** `readTimeout=200ms`, nhưng HTTP stub chỉ bắt đầu gửi response sau 800ms. Trong cấu hình cô lập, Feign ném `RetryableException` liên quan đến I/O và bộ đếm `REQUESTS` phải là `1`. Nếu dự án dùng HTTP client tùy biến, kiểm tra loại exception thực tế trước khi cố định phép khẳng định về class; điều cần kiểm chứng ở đây là **số request đã tới server**.

Khi đổi sang `readTimeout=1200`, server sẽ phản hồi kịp và caller nhận `"ok"`; đó là phép thử đối chứng để tránh nhầm cấu hình URL, annotation hoặc stub bị lỗi với timeout.

Không nên dùng địa chỉ IP “không truy cập được” để chứng minh `connectTimeout` một cách tuyệt đối: hệ điều hành có thể trả `connection refused` ngay lập tức, DNS có thể thất bại trước lúc kết nối, hoặc firewall phản hồi khác nhau. Muốn đo connect timeout chính xác, dùng công cụ chặn gói/điều khiển network được thiết kế cho mục đích đó và đo thời gian thực tế.

## 5. Bật Retryer tường minh và kiểm tra lại

Khi nghiệp vụ chấp nhận thử lại, cấu hình một `Retryer` cho **riêng** Feign client:

```java
import feign.Retryer;
import org.springframework.context.annotation.Bean;

public class StockFeignRetryConfig {
    @Bean
    public Retryer stockRetryer() {
        // period=100ms, maxPeriod=300ms, maxAttempts=3 (tính cả lần đầu)
        return new Retryer.Default(100, 300, 3);
    }
}
```

```java
@FeignClient(
    name = "stock-service",
    url = "${stock.service.url}",
    configuration = StockFeignRetryConfig.class
)
public interface StockClient {
    @GetMapping("/stocks/{sku}")
    String getStock(@PathVariable("sku") String sku);
}
```

`Retryer.Default(100, 300, 3)` cho phép tối đa **3 attempts tổng cộng**, không phải “1 lần đầu + 3 lần retry”. Nó chỉ được kích hoạt khi Feign thực sự nhận `RetryableException`; không có nghĩa mọi response `500` đều được gửi lại.

Chạy phép thử ở mục 4 với cấu hình mới: lỗi timeout tạm thời có thể tạo tối đa 3 lượt tới server (và thời gian chờ cộng dồn). Vì phép thử ban đầu khẳng định đúng `1` request, cần đổi assertion cho tình huống thử retry, khởi tạo lại bộ đếm/server cho mỗi trường hợp và kiểm tra cả response cuối. Tránh cho class `StockFeignRetryConfig` bị quét như cấu hình toàn cục nếu bạn chỉ muốn áp dụng với `stock-service`: đặt ngoài phạm vi component scan thông thường và khai báo qua `@FeignClient(configuration = ...)`.

Bạn cũng có thể tự viết `Retryer` để kiểm soát khoảng nghỉ, số lần thử và loại lỗi. Khi làm vậy, hãy bảo đảm các bản sao `clone()` của retryer không chia sẻ bộ đếm attempts giữa những request độc lập.

## 6. Phân biệt retry của Feign với retry của LoadBalancer

Trong luồng `@FeignClient(name = "stock-service")` **không có `url` cố định**, Spring Cloud LoadBalancer có thể chọn một `ServiceInstance` từ discovery. Khi các dependency và tính năng retry tương ứng được kích hoạt, tầng LoadBalancer có thể thử lại với cùng hoặc với instance khác. Việc có retry ở tầng này hay không phụ thuộc **phiên bản, classpath, loại client (blocking/reactive) và cấu hình**, vì vậy không thể suy ra từ `Retryer.NEVER_RETRY`.

Ví dụ cấu hình minh họa khi muốn chủ động **tắt retry của LoadBalancer trong phép thử**:

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
```

Khi đo trong hệ thống thực:

1. Xác định client có `url` tĩnh hay gọi bằng `service ID`; URL tĩnh cho phép cô lập Feign.
2. Kiểm tra HTTP transport, Spring Cloud LoadBalancer, Spring Retry và các cấu hình liên quan trên classpath.
3. Gắn request ID/correlation ID, ghi log số attempts và tên instance ở phía server, hoặc dùng metrics/tracing có nhãn phù hợp.
4. Test riêng **Feign retry** và **LoadBalancer retry**, sau đó test cả hệ thống khi hai chính sách được bật.

Nếu Feign thử 3 lần và một tầng bên dưới lại thử nhiều lần cho mỗi attempt, số request tiềm năng có thể **nhân lên**, khiến timeout và tải lên downstream tăng mạnh. Các tầng như API gateway, service mesh, reverse proxy cũng cần được tính đến.

## 7. Ma trận tình huống cần quan sát

Trong bảng, “mặc định OpenFeign” giả định **không có Retryer tùy biến, không có retry từ LoadBalancer/proxy và đang gọi qua URL tĩnh**.

| Kịch bản ở server/network | Kết quả dự kiến với OpenFeign mặc định | Điều cần đo hoặc kiểm chứng |
| --- | --- | --- |
| HTTP 200 trước `readTimeout` | Thành công, 1 request | Response và bộ đếm phía server |
| Server giữ kết nối, phản hồi sau `readTimeout` | Exception do timeout, 1 request | Bộ đếm và thời gian client chờ |
| Không kết nối được tới endpoint | Exception kết nối, không retry ở tầng Feign | Log lỗi; số request server có thể bằng 0 |
| HTTP 500/503 thông thường | Trả exception HTTP, không tự mặc định retry mọi 5xx | Mã HTTP, `ErrorDecoder` và bộ đếm |
| `RetryableException` do I/O hoặc `ErrorDecoder` sinh ra | `NEVER_RETRY` phát lỗi ngay | Loại exception và số attempts |
| Cấu hình `Retryer.Default(..., 3)`; mỗi lần đều lỗi retryable | Có thể thử tối đa 3 lần | Đếm attempts và khoảng backoff |
| Retry của LoadBalancer được kích hoạt khi dùng discovery | Có thể có các lượt gửi khác tầng Feign | Đếm theo service ID và instance |

Chú ý: phép thử `readTimeout` không chứng minh cơ chế xử lý **mọi** lỗi HTTP. Với lỗi 503 có `Retry-After`, `ErrorDecoder` hoặc transport có thể tạo kết quả khác lỗi 503 thông thường; hãy kiểm tra điều kiện cụ thể của ứng dụng.

## 8. Đặt retry theo ngữ nghĩa nghiệp vụ

Retry giúp vượt qua lỗi tạm thời nhưng có thể gửi lại **một thao tác đã được server xử lý**. Client timeout chỉ cho biết **client chưa nhận được kết quả đúng hạn**; không khẳng định rằng server chưa lưu dữ liệu.

- **GET tra cứu dữ liệu** thường phù hợp hơn với retry có giới hạn, nếu tải của downstream và deadline cho phép.
- **POST tạo đơn, thanh toán, ghi số dư** cần cơ chế chống lặp như `Idempotency-Key`, khóa nghiệp vụ hoặc kiểm tra trạng thái giao dịch trước khi retry.
- **429/503** chỉ nên retry theo chính sách được thỏa thuận, có backoff/jitter và tôn trọng `Retry-After` khi phù hợp.
- **400/401/403/404** thường không được giải quyết bằng thử lại y nguyên; cần xử lý đúng nguyên nhân, quyền truy cập hoặc dữ liệu đầu vào.
- **Lỗi có thể phục hồi nhưng liên tục** vẫn cần giới hạn attempts, deadline tổng thể, quan sát tải và khả năng mở circuit breaker.

Một cách lập ngân sách thời gian sơ bộ là cộng thời gian mỗi attempt với backoff rồi so với deadline của request phía trên. Ví dụ: 3 attempts, mỗi lần có thể chờ đọc đến 1.5 giây, cộng backoff 0.1 giây và 0.3 giây, thì chỉ riêng chờ đọc và backoff đã có thể đạt khoảng **4.9 giây**; còn thiếu kết nối, discovery và các lớp khác. Đây là phép tính minh họa, **không phải** giới hạn thời gian thực thi được bảo đảm.

## 9. Checklist chẩn đoán khi kết quả khác kỳ vọng

| Dấu hiệu | Kiểm tra đầu tiên |
| --- | --- |
| Tưởng đã đặt timeout nhưng request vẫn rất lâu | Đúng tên `spring.cloud.openfeign.client.config.<client-name>` chưa? HTTP client nào đang chạy? Có retry/backoff ở tầng khác? |
| Thấy nhiều request dù dùng `Retryer.NEVER_RETRY` | Spring Cloud LoadBalancer, gateway/mesh, caller phía trên hoặc thao tác người dùng có gửi lại không? |
| Không retry khi server trả 500 | 500 đã được biến thành `RetryableException` chưa? `Retryer` hiện hành là gì? |
| Thử retry nhưng không đổi instance | URL tĩnh hay discovery? Chính sách same/next instance của LoadBalancer ra sao? |
| Kết quả khác giữa máy local và staging | So sánh dependency versions, `Request.Options`, cấu hình client, proxy, DNS và network latency |
| Một POST được ghi hai lần | Timeout có thể xảy ra sau khi server xử lý; kiểm tra idempotency và trạng thái giao dịch |

Đừng chỉ xem log `FULL` của Feign rồi suy ra số request server nhận. Log ở mỗi tầng có thể hiển thị attempts khác nhau; đếm ở **endpoint thực tế** hoặc trace xuyên tầng mới trả lời được câu hỏi “đã gửi bao nhiêu lần?”.

## 10. Tự luyện

1. Chạy lại phép thử ở mục 4 với `readTimeout` lần lượt là 100ms, 200ms và 1200ms; ghi nhận exception, thời gian đo và `REQUESTS`.
2. Thay `Retryer.NEVER_RETRY` bằng `Retryer.Default(100, 300, 3)`; điều chỉnh assertion, đếm requests và xác nhận attempts tổng cộng. Sau đó thử HTTP 500 thông thường để thấy retry không tự động áp dụng cho mọi 5xx.
3. Bỏ URL tĩnh, đăng ký hai instance của `stock-service` qua cơ chế discovery của ứng dụng và quan sát instance được chọn khi gặp lỗi. Kiểm soát `spring.cloud.loadbalancer.retry.enabled` để phân biệt tầng retry.
4. Đề xuất chính sách `timeout/retry` cho thao tác `GET /stocks/{sku}` và `POST /orders`, giải thích cách hạn chế trùng lặp và bảo vệ deadline tổng thể.

**Điểm cần giữ lại:** Khi kiểm tra một hệ thống Spring Cloud LoadBalancer + OpenFeign, câu trả lời đúng về hành vi mặc định đến từ **đúng tầng và phép đo thực tế**: Spring Cloud OpenFeign mặc định sử dụng `Retryer.NEVER_RETRY` ở tầng Feign; timeout không phải deadline tổng thể; và các lần gửi lại từ LoadBalancer hoặc hạ tầng bên ngoài phải được quan sát độc lập.
