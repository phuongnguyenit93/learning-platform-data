# Quan sát yêu cầu đi qua server và HTTP client bằng trace, metrics và log an toàn

Khi một API Spring Boot trả lỗi hoặc chậm, cần biết request nào đang chạy, công đoạn nào tốn thời gian và HTTP client đã gọi downstream nào. **Metrics** chỉ ra tỷ lệ lỗi và độ trễ tổng hợp; **distributed traces** thể hiện cây các công đoạn của một request; **logs** bổ sung những sự kiện có ý nghĩa. Ghi toàn bộ request/response body hoặc Authorization để debug có thể làm lộ secrets, cookie, dữ liệu cá nhân. Vì vậy bài này hướng dẫn tạo cả ba tín hiệu nhưng chỉ log thông tin đã được allowlist.

Bài thuộc **Spring Boot - web-runtime → Thực hành tổng hợp**, chủ đề **Quan sát yêu cầu đi qua server và HTTP client bằng trace, metrics và log an toàn**. Công nghệ: **Java 17, Spring Boot 3.3.13, Spring MVC/Tomcat, RestClient, Micrometer Observation, Micrometer Tracing Brave, Spring Boot Actuator, Prometheus registry và Maven**. Dự án demo chạy không cần DB hoặc HTTP server bên ngoài: inbound **GET /api/quote** gọi RestClient outbound tới **GET /partner/price** ở cùng JVM, qua port đang chạy thật. Việc tự HTTP loopback chỉ phục vụ lab, không phải kiến trúc khuyến nghị cho các hàm nội bộ production.

## 1. Kết quả học tập

1. Phân biệt **metric, log, trace, span, traceId, spanId, parent span và correlation ID**.
2. Dùng **ObservationRegistry** để đo custom operation bên trong Spring MVC request.
3. Nhận biết **http.server.requests**, **http.client.requests** và metric riêng cho nghiệp vụ.
4. Dùng **Boot-managed RestClient.Builder, RestTemplateBuilder, WebClient.Builder** để tạo HTTP client có tracing/metrics.
5. Theo dõi **W3C traceparent** từ inbound server tới outbound client/downstream server.
6. Đọc **/actuator/metrics** và **/actuator/prometheus**, hiểu naming/labels khác nhau.
7. Tìm các logs theo traceId; phân biệt trace ID với token hoặc idempotency key.
8. Kiểm soát **sampling, high-cardinality metrics, PII, secrets, log injection và exporter privacy**.
9. Chạy Maven project và test **@SpringBootTest(RANDOM_PORT)** bằng HTTP thật.
10. Biết vì sao context mất qua **ExecutorService, @Async, CompletableFuture và Reactor**.
11. Export traces tới Zipkin/OTLP khi cần và không nhầm propagation với export.
12. Dùng một runbook nhất quán để gỡ lỗi latency hoặc 5xx.

## 2. Ba trụ cột quan sát

| Tín hiệu | Trả lời | Không trả lời |
| --- | --- | --- |
| **Metrics** | Request rate, số 5xx, latency/p95/p99, saturation | Request cụ thể đi qua những spans nào. |
| **Traces** | Cây công đoạn, quan hệ cha-con, khoảng thời gian từng span | Toàn bộ request nếu đang sampling. |
| **Logs** | Sự kiện và error category chi tiết, liên kết traceId | Phân phối độ trễ của toàn traffic như histogram. |

**Trace** là một luồng xử lý có thể qua nhiều services. Mỗi **span** có spanId riêng, cùng **traceId** trong một trace. Với server call sang downstream:

~~~text
HTTP CLIENT bên ngoài
  |
  v
SERVER span: GET /api/quote         traceId=T
  |
  +-- custom observation: quote.price.lookup  traceId=T
       |
       +-- CLIENT span: GET /partner/price     traceId=T
            |
            +-- SERVER span: GET /partner/price traceId=T
~~~

Span tree là **minh họa**; instrumentation có thể tạo thêm spans, sampling có thể làm UI không hiển thị tất cả. Ở demo này cả hai HTTP server endpoints thuộc cùng service name vì chạy cùng JVM. Khi tách downstream thành service khác, trace propagation sẽ giữ traceId nhưng service name khác.

**Correlation ID** trong Boot 3.3 thường được hình thành từ traceId-spanId trong Logback MDC khi Micrometer Tracing hoạt động. Một **X-Request-ID** do gateway cung cấp khác traceId; **Idempotency-Key** nhằm chống lặp business POST, không được thay bằng traceId. Không sử dụng trace ID để xác thực hoặc cấp quyền.

## 3. Micrometer Observation và HTTP instrumentation

### 3.1. ObservationRegistry

Boot Actuator tạo Micrometer ObservationRegistry và handlers thích hợp. Một custom observation:

~~~java
Observation.createNotStarted("quote.price.lookup", registry)
        .lowCardinalityKeyValue("flow", "price-lookup")
        .observe(() -> {
            // Công đoạn nghiệp vụ.
        });
~~~

Đây là snippet; cần imports io.micrometer.observation.Observation và ObservationRegistry. Khi có metrics handler, observation có thể tạo Timer; khi có tracing bridge, nó còn tạo span. Không cần tự tạo UUID rồi giả lập tracing.

### 3.2. HTTP server metrics

Spring Boot 3.3 auto-instrument Spring MVC handlers; metric mặc định **http.server.requests**. Tags có thể là **method, uri template, status, outcome, exception** tùy request. Request path nên biểu diễn như **/orders/{id}**, không phải raw order ID/query string.

Không mặc định mọi exception đã được ExceptionHandler xử lý đều xuất hiện ở exception tag; phải xem status/outcome và runtime test.

### 3.3. HTTP client metrics và propagation

Spring Boot auto-configure **RestClient.Builder, RestTemplateBuilder, WebClient.Builder** có observation customizers. Dùng injected builder giúp outbound HTTP được đo bằng **http.client.requests**, đồng thời Micrometer Tracing có thể inject trace context.

Nếu tự tạo client:

~~~java
RestClient client = RestClient.create();
~~~

thì Boot builder instrumentation có thể không được áp dụng. Không chữa bằng việc tự copy incoming traceparent sang mọi outbound call: có thể tạo sai quan hệ span, sai trust boundary, hoặc làm mất bối cảnh hiện tại.

### 3.4. W3C traceparent

Header minh họa:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Nó mang version, traceId, parent spanId và flags. Spring Boot 3.3 hỗ trợ cấu hình **management.tracing.propagation.consume/produce**; mặc định outgoing W3C. Khi hai services dùng B3/W3C khác nhau phải đối chiếu gateway/library settings, không hardcode trace IDs.

Incoming **traceparent/tracestate/baggage là input không đáng tin**. Không chuyển Authorization/JWT/cookie/email vào baggage, không lấy traceId làm metric label hay file name, không dùng header trace để quyết định authentication. Tracer library cần validate format.

### 3.5. Sampling và export

Boot 3.3 mặc định sampling traces khoảng **10%**. Trong lab bật **management.tracing.sampling.probability: 1.0** để các traces dễ quan sát. **Sampling không tắt HTTP metrics của các request không được chọn**. Có thể thấy traceId trong logs nhưng không thấy spans trong Zipkin vì chưa cấu hình reporter, collector không chạy hoặc trace không được export.

## 4. Metric cardinality và logging safety

**Low cardinality**: method=GET, status=200, flow=price-lookup, partner=demo, outcome=success.

**High cardinality không phù hợp cho metric labels**: userId, email, UUID, traceId, session ID, raw URL có số đơn hàng. Mỗi tổ hợp labels có thể tạo time series mới, tăng memory/storage và làm lộ dữ liệu. Micrometer **lowCardinalityKeyValue** thêm tags vào metrics và traces; **highCardinalityKeyValue** thường chỉ thêm vào traces. Nhưng trace attributes cũng được export, nên high-cardinality không đồng nghĩa được phép chứa PII.

**Không log thẳng:** Authorization, Basic/Bearer token, Cookie, Set-Cookie, CSRF token, password, OTP, JWT claims, response/request body, email, phone, payment card, raw URL/query có token, multipart file, stack trace chứa nội dung nhạy cảm.

**Nên log:** event name cố định, HTTP method/route template, status/outcome, controlled error category, bounded retry count, service/environment không nhạy cảm và MDC trace IDs. Chỉ log user-controlled field khi đã validate/sanitize/allowlist; attacker có thể dùng newline để tạo **log injection**.

Mẫu an toàn:

~~~java
log.info("quote_started operation=price_lookup");
log.info("partner_price_lookup tier={}", "book");
log.warn("partner_call_failed category=http_client");
~~~

Mẫu rủi ro:

~~~java
log.info("headers={}, body={}", headers, requestBody);
log.error("auth=" + bearerToken);
~~~

Đừng rely hoàn toàn vào regex redaction sau khi log đã bị đẩy ra collector; nên **không emit nhạy cảm từ nguồn**. Cần retention, access control, encryption/network security và audit đối với hệ thống lưu logs/traces. Không expose Actuator management endpoints ra Internet thiếu bảo vệ.

## 5. Project hoàn chỉnh: inbound server → RestClient → downstream server

### 5.1. Cây project

~~~text
observability-flow-demo/
  pom.xml
  src/main/java/com/example/obs/
    ObservabilityFlowApplication.java
    PartnerPriceResponse.java
    QuoteResponse.java
    PartnerClient.java
    PartnerController.java
    QuoteController.java
    ClientErrorAdvice.java
  src/main/resources/application.yml
  src/test/java/com/example/obs/FlowHttpIntegrationTest.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>observability-flow-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
~~~

starter-web cung cấp Tomcat và Spring MVC/RestClient, starter-actuator ObservationRegistry/metrics, Brave bridge tracing context/MDC, Prometheus registry xuất metrics, starter-test có JUnit/TestRestTemplate. Spring Boot BOM quản lý library versions. Chưa có Zipkin reporter trong POM này nên không phụ thuộc collector ngoài.

### 5.3. ObservabilityFlowApplication.java

~~~java
package com.example.obs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ObservabilityFlowApplication.class, args);
    }
}
~~~

### 5.4. PartnerPriceResponse.java

~~~java
package com.example.obs;

public record PartnerPriceResponse(
        String sku,
        long priceCents,
        boolean traceparentPresent) {
}
~~~

### 5.5. QuoteResponse.java

~~~java
package com.example.obs;

public record QuoteResponse(
        String status,
        long unitPriceCents,
        boolean downstreamTraceContextPresent) {
}
~~~

Hai Java records chỉ có dữ liệu giả lập. Boolean traceparentPresent báo downstream **nhận header hay không**, không expose raw header và không chứng minh exporter đã gửi spans lên backend.

### 5.6. PartnerController.java — server endpoint được RestClient gọi tới

~~~java
package com.example.obs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class PartnerController {

    private static final Logger log =
            LoggerFactory.getLogger(PartnerController.class);

    @GetMapping("/partner/price")
    public PartnerPriceResponse price(
            @RequestParam String sku,
            @RequestHeader(
                name = "traceparent",
                required = false) String traceparent) {

        if (!sku.matches("[A-Z]{2,12}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid sku format");
        }

        String tier = sku.equals("BOOK")
                ? "book"
                : "standard";

        // tier thuộc tập giá trị hữu hạn, không log raw SKU/header.
        log.info("partner_price_lookup tier={}", tier);

        long cents = sku.equals("BOOK") ? 1599L : 999L;

        return new PartnerPriceResponse(
                sku, cents,
                traceparent != null && !traceparent.isBlank());
    }
}
~~~

**Điểm an toàn:** log chỉ tier đã allowlist; không ghi traceparent string, SKU raw, token hoặc response body. Trong thực tế, SKU hoặc product metadata cũng có thể được xem là dữ liệu nhạy cảm tùy lĩnh vực. Không dùng boolean propagation như một điều kiện xác thực.

### 5.7. PartnerClient.java — outbound RestClient instrumented

~~~java
package com.example.obs;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerClient {

    private final RestClient http;
    private final AtomicInteger port = new AtomicInteger(-1);

    public PartnerClient(RestClient.Builder builder) {
        // Builder được Boot/Actuator customize cho HTTP observation.
        this.http = builder.build();
    }

    @EventListener
    public void serverStarted(
            ServletWebServerInitializedEvent event) {
        port.set(event.getWebServer().getPort());
    }

    public PartnerPriceResponse fetchPrice(String sku) {
        int actualPort = port.get();

        if (actualPort < 1) {
            throw new IllegalStateException(
                    "HTTP server not ready");
        }

        return http.get()
                .uri(
                    "http://127.0.0.1:{port}/partner/price?sku={sku}",
                    actualPort, sku)
                .retrieve()
                .body(PartnerPriceResponse.class);
    }
}
~~~

**Giải thích:**
1. Inject **RestClient.Builder** do Boot cấu hình; không dùng RestClient.create.
2. Sử dụng URI template với {port}, {sku}; không nối raw input thành URL string.
3. **ServletWebServerInitializedEvent** lấy port thật, kể cả khi test RANDOM_PORT.
4. Demo không có management.server.port tách riêng, nên event port là main web server.
5. HTTP client tự tạo outbound client observation và truyền W3C traceparent khi tracing active.
6. Production cần service URL được kiểm soát, HTTP timeouts, connection pooling, retry policy và không self-call vào cùng JVM khi không có nhu cầu.

### 5.8. QuoteController.java — server + business observation

~~~java
package com.example.obs;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class QuoteController {

    private static final Logger log =
            LoggerFactory.getLogger(QuoteController.class);

    private final PartnerClient partner;
    private final ObservationRegistry registry;

    public QuoteController(
            PartnerClient partner,
            ObservationRegistry registry) {
        this.partner = partner;
        this.registry = registry;
    }

    @GetMapping("/api/quote")
    public QuoteResponse quote(
            @RequestParam(defaultValue = "BOOK") String sku) {

        if (!sku.matches("[A-Z]{2,12}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid sku format");
        }

        log.info("quote_started operation=price_lookup");

        return Observation
                .createNotStarted("quote.price.lookup", registry)
                .lowCardinalityKeyValue("flow", "price-lookup")
                .observe(() -> {
                    PartnerPriceResponse price =
                            partner.fetchPrice(sku);

                    log.info(
                        "quote_completed outcome=success "
                        + "partner=demo");

                    return new QuoteResponse(
                            "OK",
                            price.priceCents(),
                            price.traceparentPresent());
                });
    }
}
~~~

**Why this instrumentation works:** Spring MVC đã tạo HTTP server observation; custom quote.price.lookup là **sub-operation**, không phải một server span thứ hai trùng. Client call nằm trong observation scope nên tracing có thể tạo client span bên dưới. **flow=price-lookup** là metric tag thấp cardinality; không dùng sku/userId/traceId. Log events không in headers, user input hoặc tokens. Khi downstream lỗi, observation kết thúc với exception path và advice quyết định response.

### 5.9. ClientErrorAdvice.java — chỉ log error taxonomy

~~~java
package com.example.obs;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClientException;

@RestControllerAdvice
public class ClientErrorAdvice {

    private static final Logger log =
            LoggerFactory.getLogger(ClientErrorAdvice.class);

    @ExceptionHandler(RestClientException.class)
    public ResponseEntity<Map<String, String>> clientFailed(
            RestClientException exception) {

        // Không log exception.getMessage(), upstream body/URL.
        log.warn("partner_call_failed type={}",
                exception.getClass().getSimpleName());

        return ResponseEntity.status(
                HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "PARTNER_UNAVAILABLE"));
    }
}
~~~

502 chỉ mang nghĩa upstream HTTP error trong lab; production có thể dùng 503/504 tùy lỗi và contract. Không bắt mọi RuntimeException thành 502 vì sẽ che bug nội bộ. Cần timeouts/metrics để phân biệt upstream timeout với response 5xx.

### 5.10. application.yml

~~~yaml
spring:
  application:
    name: observability-flow-demo

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0
  observations:
    key-values:
      environment: "lab"

logging:
  level:
    com.example.obs: INFO
~~~

- sampling=1.0 **chỉ cho lab**, không là khuyến nghị mọi production.
- environment=lab là common observation tag giá trị hữu hạn.
- /metrics và /prometheus có thể lộ thông tin vận hành; production cần management network, auth/TLS/RBAC.
- Boot 3.3 + Micrometer Tracing có thể tự thêm correlation ID vào logs. Không phải tự đọc traceId từ request header để in trong từng message.
- Tránh bật DEBUG/TRACE network wire logs nếu chưa kiểm duyệt có chứa body/headers hay không.

## 6. Chạy project và xem output

### 6.1. Build/start

Linux/macOS:

~~~bash
mvn clean package
java -jar target/observability-flow-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvn.cmd clean package
java -jar target/observability-flow-demo-0.0.1-SNAPSHOT.jar
~~~

Gọi HTTP:

~~~bash
curl -i "http://localhost:8080/api/quote?sku=BOOK"
curl -i "http://localhost:8080/api/quote?sku=PEN"
curl -i "http://localhost:8080/api/quote?sku=bad123"
~~~

Kỳ vọng BOOK trả HTTP 200 với JSON dạng:

~~~json
{
  "status": "OK",
  "unitPriceCents": 1599,
  "downstreamTraceContextPresent": true
}
~~~

PEN có unitPriceCents=999; bad123 không match regex chữ hoa và trả 400. Boolean downstreamTraceContextPresent **dự kiến true** với tracing bridge và RestClient.Builder của Boot; không phải cam kết nếu bạn đổi tracing configuration.

### 6.2. Log correlation

Tìm trong console:

~~~text
quote_started operation=price_lookup
partner_price_lookup tier=book
quote_completed outcome=success partner=demo
~~~

Khi active tracing, các dòng này có traceId cùng nhau trong MDC correlation; spanId có thể khác giữa business/server/downstream spans. **Không cố định traceId hoặc thứ tự log timestamps**. Nếu không có MDC traceId, kiểm tra bridge và context trước khi thêm thủ công trace header logging.

### 6.3. Actuator metrics

Sau khi có requests:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/http.server.requests
curl -i http://localhost:8080/actuator/metrics/http.client.requests
curl -i http://localhost:8080/actuator/metrics/quote.price.lookup
~~~

- **http.server.requests** cho cả /api/quote và /partner/price, vì demo có hai inbound HTTP requests.
- **http.client.requests** cho outbound RestClient request.
- **quote.price.lookup** đo custom business observation.
- COUNT/TOTAL_TIME/MAX/tags theo meter/registry.
- Không kỳ vọng COUNT bằng một con số cố định nếu đã chạy nhiều requests hoặc Actuator endpoints.

Có thể filter tags khi tồn tại:

~~~bash
curl -G \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=status:200" \
  http://localhost:8080/actuator/metrics/http.server.requests
~~~

### 6.4. Prometheus

~~~bash
curl -i http://localhost:8080/actuator/prometheus
~~~

Các tên series theo convention có thể gồm:

~~~text
http_server_requests_seconds_count
http_client_requests_seconds_count
quote_price_lookup_seconds_count
~~~

Tên chính xác/suffix tùy Micrometer Prometheus registry; xem output thực. Actuator metrics sử dụng tên dotted trong code, Prometheus chuẩn hóa tên metric và seconds suffix. **Không public scrape endpoint nếu không có security/network isolation.**

## 7. HTTP integration test thực

Test sử dụng **@SpringBootTest(RANDOM_PORT)**, không chỉ MockMvc, và PartnerClient biết port thực từ ServletWebServerInitializedEvent. Test kiểm tra HTTP server, outbound client, custom observation và việc downstream nhận traceparent.

### 7.1. FlowHttpIntegrationTest.java

~~~java
package com.example.obs;

import io.micrometer.core.instrument.MeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FlowHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    MeterRegistry metrics;

    @Test
    void serverAndHttpClientAreObserved() {
        var response = http.getForEntity(
                "/api/quote?sku=BOOK",
                QuoteResponse.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(200);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().status())
                .isEqualTo("OK");
        assertThat(response.getBody().unitPriceCents())
                .isEqualTo(1599L);
        assertThat(response.getBody()
                .downstreamTraceContextPresent()).isTrue();

        assertThat(metrics.find("http.server.requests")
                .timers()).isNotEmpty();
        assertThat(metrics.find("http.client.requests")
                .timers()).isNotEmpty();
        assertThat(metrics.find("quote.price.lookup")
                .timers()).isNotEmpty();
    }

    @Test
    void invalidSkuReturns400() {
        var response = http.getForEntity(
                "/api/quote?sku=bad123",
                String.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Test giải thích:** TestRestTemplate trả HTTP response cho 4xx để assert; RANDOM_PORT tạo Tomcat network connector thật. Boolean true kiểm chứng **header traceparent hiện diện** trên downstream request, chưa kiểm chứng exporter/backend nhận spans. MeterRegistry.find(...).timers() kiểm tra server/client/business timers đã xuất hiện khi operation hoàn tất. Không assert IDs ngẫu nhiên hay exact counts. Không cần Zipkin Docker để chạy test.

## 8. Xuất distributed traces ra Zipkin hoặc OTLP

### 8.1. Propagation khác export

| Quan sát | Đã chứng minh | Chưa chứng minh |
| --- | --- | --- |
| http.client.requests xuất hiện | Outbound HTTP metrics được instrumented | Có traceparent hoặc exporter. |
| downstreamTraceContextPresent=true | HTTP request mang traceparent tới downstream | Zipkin nhận sampled spans. |
| Zipkin hiển thị span tree | Reporter/collector nhận spans | Mọi request đều được lấy mẫu. |

### 8.2. Brave + Zipkin reporter

POM chính cố ý chỉ có bridge để lab không cần backend ngoài. Muốn xem spans UI, thêm dependency:

~~~xml
<dependency>
    <groupId>io.zipkin.reporter2</groupId>
    <artifactId>zipkin-reporter-brave</artifactId>
</dependency>
~~~

Bổ sung vào **management section đang có**:

~~~yaml
management:
  zipkin:
    tracing:
      endpoint: "http://localhost:9411/api/v2/spans"
~~~

Đây là YAML snippet, **không để hai top-level management keys trùng nhau** trong file thật. Nếu có Docker được phép dùng:

~~~bash
docker run --rm -d --name zipkin-lab \
  -p 9411:9411 openzipkin/zipkin:latest
~~~

Docker tag latest chỉ dành cho lab, production cần pin version. Nếu app chạy trong container khác, localhost của app không trỏ đến host Zipkin; sử dụng DNS/network phù hợp. Mở **http://localhost:9411** trên host có Zipkin UI, gửi vài requests rồi tìm service **observability-flow-demo**.

**Một trace có thể không xuất hiện** vì sampling, exporter network, collector auth/TLS, queue drops hoặc flush khi shutdown. Không log raw headers/body để điều tra exporter.

### 8.3. OpenTelemetry và OTLP

Spring Boot 3.3 cũng hỗ trợ **micrometer-tracing-bridge-otel** kèm **opentelemetry-exporter-otlp**, cấu hình **management.otlp.tracing.***. Có thể export tới OTel collector/Jaeger/tempo theo infrastructure. **Không dùng Brave và OTel bridge cùng lúc** chỉ để “đủ tính năng”; chọn một tracing stack nhất quán, tránh double instrumentation.

## 9. Context propagation qua async và reactive

### 9.1. ExecutorService và @Async

MDC/trace context của Servlet request không mặc nhiên theo **new Thread, CompletableFuture.commonPool, custom ExecutorService**. Log trong worker có thể mất traceId, HTTP client span có thể thành root mới. Spring Framework 6.1 có **ContextPropagatingTaskDecorator**:

~~~java
@Bean
ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("observed-");
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

Snippet nằm trong Spring @Configuration, cần imports:
- org.springframework.context.annotation.Bean;
- org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
- org.springframework.core.task.support.ContextPropagatingTaskDecorator.

Decorator có overhead, đặc biệt với jobs nhỏ; áp dụng đúng boundary. Không tự copy ThreadLocal MDC toàn cục giữa threads mà không cleanup vì có thể rò request cũ.

### 9.2. Reactor/WebFlux

Spring Boot 3.3 có thể bật automatic Reactor context propagation:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Với reactive client, inject **WebClient.Builder** của Boot, test context qua publishOn/subscribeOn/flatMap. Không gọi block() trên Netty event loop. Property propagation không biến JDBC/blocking RestClient thành non-blocking.

### 9.3. RestClient, RestTemplate, WebClient so sánh

| Client | Loại | Cách Boot instrumentation |
| --- | --- | --- |
| RestClient | Fluent synchronous | Inject RestClient.Builder. |
| RestTemplate | Legacy synchronous | Inject RestTemplateBuilder. |
| WebClient | Reactive | Inject WebClient.Builder. |
| JDK HttpClient raw | JDK HTTP | Cần instrumentation riêng nếu muốn tracing giống Boot builders. |
| Apache HttpClient raw | Low-level | Dùng integration/agent phù hợp, không mặc định mọi raw call đều traced. |

Một Spring MVC app có thể dùng WebClient để gọi outbound HTTP mà **không đổi web server sang WebFlux**. Boot 3.3 có cả starters thì chọn Servlet/MVC mặc định; cần kiểm tra stack thật khi refactor.

## 10. Dashboard và runbook điều tra

### 10.1. Dashboard tối thiểu

~~~text
Service: observability-flow-demo
  - HTTP RPS by uri template + method
  - HTTP 5xx ratio and outcome
  - p50/p95/p99 latency (khi đã cấu hình histogram)
  - Outbound http.client.requests by target/status
  - quote.price.lookup COUNT/duration
  - JVM heap, GC, CPU, threads và connection pool
  - Trace UI lọc service/time/status
  - Logs tìm traceId và fixed event names
~~~

p99 không tính chính xác từ average; cần Micrometer distribution histogram hoặc SLO buckets phù hợp và Prometheus queries. Đừng bật histogram cho mọi metric không cần thiết vì cardinality và storage.

### 10.2. Quy trình điều tra lỗi

1. Xác định service, deployment version, route template, HTTP method và time window.
2. Xem **http.server.requests**: lỗi và latency xuất hiện từ khi nào, trên route nào?
3. Xem **http.client.requests**: có downstream status/latency tăng cùng thời gian?
4. Chọn slow/error trace để tìm server span, business span và client span kéo dài.
5. Dùng traceId lọc safe log events: quote_started, partner_price_lookup, quote_completed, partner_call_failed.
6. Nếu không có client span, kiểm tra RestClient.Builder, tracer bridge, propagation, sampling, exporter.
7. Nếu span mất qua executor, kiểm tra context decorator và Reactor propagation.
8. So CPU/GC/DB/pools với latency; không kết luận một client span chậm luôn do downstream code.
9. Xác minh không có secrets/PII trong logs/traces/metric labels.
10. Sửa nguyên nhân, viết integration test/regression và cập nhật dashboard/runbook.

### 10.3. Sampling bias

Traces được sampling không đại diện toàn traffic. Với tỷ lệ 0.1, một rare 5xx có thể không có trace sampled trong khoảng ngắn. **Metrics** mới phù hợp để đo error rate tổng; **trace** dùng điều tra công đoạn. Nếu có tail-based/error sampling ở collector, cần xác minh cost/privacy và thống nhất cách kết hợp với application sampling.

## 11. Troubleshooting

| Triệu chứng | Nguyên nhân | Cách kiểm tra/sửa |
| --- | --- | --- |
| Không có http.client.requests | Dùng RestClient.create hoặc client chưa gọi | Inject Boot RestClient.Builder, gửi quote rồi kiểm tra. |
| server metrics có, traceparentPresent=false | Thiếu bridge/propagation/builder | Check POM, W3C config, client creation. |
| Logs không có traceId | Không có active span hoặc MDC context | Check Micrometer bridge, log correlation pattern. |
| downstream traceId đổi | Gateway lọc header hoặc context mất | Check traceparent, B3/W3C compatibility và async. |
| Zipkin UI rỗng | Không có reporter, collector lỗi, sampling | Check exporter endpoint, network và queue drops. |
| /actuator/prometheus 404 | Thiếu registry hoặc exposure | micrometer-registry-prometheus, management properties. |
| Metric có quá nhiều series | Raw URI/ID/PII tag | Dùng URI template và finite tags. |
| HTTP 502 ở /api/quote | RestClient exception | Xem safe category, network/downstream status. |
| 400 không tạo client metric | Invalid SKU bị chặn trước outbound | Đây là behavior đúng. |
| Server COUNT cao hơn số quote | Demo có thêm /partner/price inbound | Filter uri template. |
| @Async mất traceId | Thread context không propagate | ContextPropagatingTaskDecorator. |
| WebFlux span không liền | Reactive context chưa đúng | Boot property và WebClient builder. |
| p99 không thấy | Chưa có histogram/SLO buckets | Configure distribution cho metrics cần thiết. |
| Actuator trả 401/403 | Endpoint có security | Dùng management access hợp lệ, không public hóa. |
| User token nằm trong logs | Wire logging/request body dump | Tắt nguy hiểm, allowlist/redact tại nguồn. |
| Duplicate spans | @Observed trùng HTTP auto-instrumentation hoặc agent | Bỏ double instrumentation. |
| Tracing backend không thấy request | Unsampled hoặc exporter dropped | Không khẳng định request chưa xảy ra. |

## 12. Anti-pattern

1. **Log Authorization, Cookie hoặc request body** để tìm lỗi — dễ lộ dữ liệu.
2. **Dùng userId, traceId, UUID, raw URI làm metric label** — cardinality quá cao.
3. **Tự tạo RestClient.create()** rồi kỳ vọng Boot tự instrument.
4. **Ghi raw traceparent/baggage** để debug propagation — không cần thiết.
5. **Dùng traceId làm authentication hoặc idempotency key** — sai nghĩa.
6. **Dùng @Observed trên HTTP controller vốn đã auto-instrumented** mà không hiểu duplicate observations.
7. **Bật tracing 100% toàn production không giới hạn** — quá tải collector/storage.
8. **Lấy average để suy p99** — sai thống kê.
9. **Log exception.getMessage() chứa raw URL/query/body** — privacy risk.
10. **Exposing all Actuator endpoints ra Internet** — lộ thông tin vận hành.
11. **Kết luận “không có trace nên không có request”** — trace có sampling.
12. **Truyền MDC ThreadLocal trực tiếp giữa threads không cleanup** — leakage giữa requests.

## 13. Bài tập

### Bài 1 — Trace tree
Vẽ 4 spans mẫu, phân biệt traceId và spanId, giải thích vì sao client và downstream đều có server/client observations.

### Bài 2 — Server/client metrics
Gọi 10 quotes hợp lệ, 3 SKU không hợp lệ, so COUNT inbound/outbound/custom observation. Giải thích vì sao client COUNT không tính requests bị reject trước outbound.

### Bài 3 — Log an toàn
Gửi Authorization header giả trong lab, xem logs không có token. Viết allowlist log fields và mô tả cách chống newline log injection.

### Bài 4 — Mất propagation
Tạm thay Boot-managed RestClient.Builder thành RestClient.create trong bản sao lab, quan sát metric/traceparent. Hoàn nguyên builder và test lại.

### Bài 5 — Sampling
Bật Zipkin rồi giảm sampling từ 1.0 xuống 0.1. So số trace export với tổng metrics; không ép mẫu nhỏ phải đúng tỷ lệ 10/100.

### Bài 6 — @Async
Submit task sang executor thiếu context decorator rồi kiểm tra log traceId. Sau đó dùng ContextPropagatingTaskDecorator và so.

### Bài 7 — WebClient
Trong Spring MVC app dùng WebClient.Builder Boot-managed; xác minh HTTP client metrics. Không block trên WebFlux event loop nếu chuyển server sang reactive.

### Bài 8 — Observability incident
Giả lập downstream 503 có kiểm soát; kiểm tra advice trả 502 và logs chỉ error class. Dùng metric → trace → log để chỉ ra failure hop.

### Bài 9 — Histogram budget
Chọn 2 endpoints quan trọng, thiết kế p95/p99 histogram/SLO buckets với labels hữu hạn. Tính số series tăng khi thêm label mới.

### Bài 10 — Privacy
Xác định dữ liệu tuyệt đối không vào baggage/logs/traces/metrics; quy định ai được đọc và retention. Không dùng dữ liệu khách hàng thật.

## 14. Checklist trước production

- [ ] http.server.requests đã xuất hiện cho inbound requests.
- [ ] http.client.requests có trên outbound calls dùng Boot-managed builders.
- [ ] Có test traceparent propagation qua HTTP thật.
- [ ] Custom observations có tên và low-cardinality tags ổn định.
- [ ] Không có userId/traceId/email/session/raw URL trong metrics labels.
- [ ] Logs không chứa Authorization, Cookie, Set-Cookie, API keys, tokens, body hay PII.
- [ ] Log error taxonomy và event names cố định, không raw exception messages.
- [ ] Trace/span IDs chỉ dùng correlation, không auth.
- [ ] Zipkin/OTLP exporter có TLS/auth, queue/dropped spans được giám sát.
- [ ] Sampling policy theo traffic/cost/privacy, không mặc định 100% mọi nơi.
- [ ] /actuator/metrics và /actuator/prometheus chỉ dành cho management network có bảo vệ.
- [ ] Histograms/SLO buckets cho endpoints quan trọng, không bật vô hạn.
- [ ] Async/Reactor context propagation được test, không duplicate spans.
- [ ] Có @SpringBootTest(RANDOM_PORT) kiểm tra metrics và HTTP propagation.
- [ ] Logs/traces có retention và access control.
- [ ] Có dashboard, alerts và runbook metric → trace → safe log.
- [ ] Test regression khi nâng Spring Boot, Micrometer hoặc HTTP client libraries.

## 15. Tự kiểm tra

**Metrics có chứa từng traceId?** Không, metrics aggregate và không nên dùng high-cardinality IDs làm labels.

**Hai spans cùng trace chia sẻ gì?** traceId, còn spanId riêng.

**Tại sao RestClient.create có thể không tự có tracing?** Không qua Boot-managed builder/customizers.

**Sampling 0.1 có xóa 90% HTTP metrics?** Không; sampling traces khác metrics.

**Propagation thành công có nghĩa Zipkin đã nhận trace?** Không; còn exporter/backend/sampling.

**WebClient dùng được trong MVC app?** Có, nếu dùng Boot WebClient.Builder; không có nghĩa web server đã chuyển sang WebFlux.

**Async thread có tự thừa hưởng MDC?** Không phải luôn; cần context propagation ở async boundary.

**Tại sao không log Authorization/cookie?** Có thể lộ credentials/session hoặc dữ liệu cá nhân.

**Tại sao không dùng user ID làm tag?** High-cardinality time series và privacy risk.

**Khi p99 tăng nên làm gì?** Dùng metrics để khoanh phạm vi, trace tìm hop chậm, logs theo traceId để giải thích.

## 16. Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html): ObservationRegistry, cardinality, Reactor context.
2. [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): http.server.requests, http.client.requests, managed HTTP client builders.
3. [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html): Brave/OTel bridges, sampling, MDC, propagation, exporter.
4. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): metrics/prometheus và security.
5. [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): RANDOM_PORT/TestRestTemplate.
6. [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): custom observation APIs.
7. [Micrometer Metrics](https://docs.micrometer.io/micrometer/reference/concepts.html): labels, meters, Timer.
8. [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): spans/tracers.
9. [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent, tracestate.
10. [OpenTelemetry Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): distributed context.
11. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): safe logging, injection, sensitive data.
12. [Prometheus Metric Naming](https://prometheus.io/docs/practices/naming/): labels và cardinality.

**Kết luận:** Để quan sát luồng request Spring Boot đi qua server và HTTP client, dùng **http.server.requests** cho inbound, **http.client.requests** cho outbound, **ObservationRegistry** cho bước nghiệp vụ, **traceId** nối các spans/log events và **safe logging theo allowlist** để giải thích lỗi. Đừng dump headers/body hoặc đưa user/trace IDs vào metric tags. Khi incident, đi từ **metric → trace → correlated safe log → root cause**, sau đó bổ sung regression tests và giới hạn telemetry theo chính sách bảo mật.