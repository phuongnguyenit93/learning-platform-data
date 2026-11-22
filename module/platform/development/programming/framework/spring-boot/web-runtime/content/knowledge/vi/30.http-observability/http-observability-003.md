# Mã tương quan, trace ID và liên kết yêu cầu với lời gọi dịch vụ phía sau

**Ngữ cảnh:** Spring Boot → web-runtime → Quan sát HTTP. Khi một HTTP request đi qua gateway, service A, service B, database và hàng đợi thông điệp, cần biết log ở mỗi nơi có cùng một yêu cầu không, đoạn nào tốn thời gian và lỗi bắt nguồn ở đâu. Bài này phân biệt **request/correlation ID**, **trace ID**, **span ID**, **W3C traceparent**, MDC log context và distributed tracing; hướng dẫn tự động truyền trace qua các HTTP clients được Spring Boot instrument và truyền request ID có chủ đích.

**Môi trường lab:** Java 17+, Maven, Spring Boot **3.5.16**, Servlet/Spring MVC, Micrometer Tracing + OpenTelemetry bridge. Một ứng dụng được khởi chạy thành **hai JVM processes** trên cổng 8080/8081 để chứng minh outbound HTTP propagation thực sự. Có mã Java build được, các lệnh curl, expected JSON, JUnit HTTP tests, hướng dẫn collector/async/WebFlux, security và runbook.

**Lưu ý version:** 3.5.16 là bản cuối của Spring Boot 3.5 thuộc hỗ trợ OSS (6/2026), chỉ cố định để học API ổn định trong dòng 3.5; production phải dùng nhánh hoặc kênh bảo trì còn vá bảo mật. Không mặc định một dependency/config Boot 3.5 tương đương Boot 4.x.

## 1. Vì sao log thường không thể tự nối một request end-to-end?

Giả sử browser gọi `GET /orders/42`; API Gateway chuyển request cho Order Service; service gọi Inventory Service, rồi database. Cùng lúc hàng nghìn request khác đang dùng chung thread pools và các service có nhiều replicas.

~~~text
Browser                    Gateway                 Order Service A             Inventory B            DB
   │                          │                           │                      │                   │
   ├── GET /orders/42 ───────►│                           │                      │                   │
   │                          ├── GET /orders/42 ─────────►│                      │                   │
   │                          │                           ├── GET /stock/42 ──────►│                   │
   │                          │                           │                      ├── SQL query ──────►│
   │                          │                           │                      │◄──────────────────┤
   │                          │                           │◄─────────────────────┤                   │
   │                          │◄──────────────────────────┤                      │                   │
   │◄─────────────────────────┤                           │                      │                   │
   │                          │                           │                      │                   │
   │  requestId: r-123  ───────────────────────────────────────────────────────────►│ (custom header)
   │  traceId:   T      ───────────────────────────────────────────────────────────►│ (trace context)
   │                          │   span A-server=S1 ─┐                            │
   │                          │                      ├─ span A-client=S2 ─┐       │
   │                          │                      │                    ├─ B-server=S3
~~~

Một dòng `INFO Calling inventory` và một dòng `WARN Inventory timeout` chưa chứng minh cùng một request. Timestamp, URL hay thread name **không đủ** khi có concurrency, retries và async tasks.

Có hai công cụ bổ trợ:
- **Log correlation:** gắn ID vào mỗi log record, để tìm các dòng liên quan trong một hoặc nhiều log streams.
- **Distributed tracing:** tạo nhiều spans, mang thông tin parent/trace qua network, hiển thị latency waterfall, parent-child relationships và lỗi theo hop.

Có ID trong logs chưa có nghĩa đã có trace UI; có trace UI chưa bảo đảm log pipeline đã index fields để tìm theo ID. Cần thiết kế cả log, metrics và traces.

## 2. Từ vựng: request ID, correlation ID, traceId và spanId

| Tên | Hình dạng thường gặp | Định danh điều gì? | Có đổi qua HTTP hop? |
| --- | --- | --- | --- |
| **Request ID** (ví dụ `X-Request-ID`) | UUID hoặc opaque string giới hạn độ dài | Một inbound request ở edge hoặc transaction theo convention riêng | **Chỉ giữ nguyên nếu custom propagation có chủ đích** |
| **Correlation ID** (`X-Correlation-ID` hoặc logging key) | ID tùy tổ chức | Tên chung để tương quan, cần hợp đồng nội bộ | Tùy contract |
| **Trace ID** (`traceId`) | W3C: 32 chữ số hex, 128 bit | Một distributed trace | **Thường giữ nguyên** giữa các spans trong một trace |
| **Span ID** (`spanId`) | W3C: 16 chữ số hex, 64 bit | Một đơn vị công việc: HTTP server/client/DB... | **Thường khác nhau** với mỗi span |
| **Parent span ID** | 16 hex | Liên kết span hiện tại với caller/parent span | Thay đổi theo cấu trúc span tree |
| **Logging correlation field** | `[traceId-spanId]` hoặc `requestId` | Cách formatter lấy MDC fields đưa vào log | Phụ thuộc log config và context |

**Một trace có nhiều spans.** Cùng `traceId` mà `spanId` khác nhau là bình thường và đúng. `Request ID` không thay thế `traceId`, vì tracing framework **không tự biến** header `X-Request-ID` thành context W3C.

**Business ID** như `orderId`, `paymentAttemptId` có vòng đời khác: một đơn hàng có thể liên quan nhiều HTTP requests, jobs và traces trong nhiều ngày. Giữ business IDs làm khóa nghiệp vụ, traceId/requestId làm khóa quan sát vận hành. Không dùng traceId làm khóa database chính hoặc idempotency key mặc định.

### 2.1. Hợp đồng correlation cần ghi rõ

Với `X-Request-ID`, hãy trả lời:
1. Ai sinh: edge gateway, ingress hay ứng dụng đầu tiên?
2. Khi client gửi ID sẵn, chấp nhận, validate, hay **strip/overwrite**?
3. Format nào (UUID/ULID/opaque string), kích thước tối đa, charset, canonical case?
4. Có truyền sang các downstream HTTP services, message queues và scheduled jobs không?
5. Có echo trong HTTP response để support tra cứu không?
6. MDC/log field name và retention/truy cập logs là gì?
7. Nếu retries, redirects hoặc fan-out, ID có giữ nguyên không, và có cần thêm attempt ID?
8. Khi request vượt qua trust boundary giữa tenants/organizations, có tạo ID mới hay không?

Không có một HTTP standard bắt buộc mọi hệ thống dùng tên `X-Request-ID` hay `X-Correlation-ID`. Tên header do hạ tầng và team thống nhất.

## 3. W3C Trace Context: traceparent và tracestate

Trace context chuẩn W3C thường đi qua HTTP headers:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=opaque-example
~~~

Format `traceparent` version 00:

~~~text
00 - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
│                   │                               │              │
│                   └── trace-id: 32 hex            │              └── trace-flags: 2 hex
└── version: 2 hex                                  └── parent-id: 16 hex
~~~

- **Trace ID** đại diện whole trace; toàn số 0 là không hợp lệ.
- **Parent ID** là span ID mà phía **gửi** đặt vào header (thường span HTTP client của A). B nhận context đó và tạo **span HTTP server mới**, nên B's span ID **không bằng** parent-id vừa nhận.
- **Flags** chứa bit sampled, ví dụ `01`. Đây là suggestion, không bắt downstream phải export mọi spans; chính sách sampling có thể giảm tải.
- **Tracestate** chứa metadata tracing vendor; tránh chứa sensitive info, áp limits và validate.
- **Baggage** là context dữ liệu có thể truyền liên dịch vụ, khác tracestate và khác log MDC. Không nhét raw JWT, session cookies, email vào baggage.

Ví dụ quan hệ đúng:

~~~text
traceId = T  (giữ nguyên)
└── A HTTP server span: S1
    └── A HTTP client span: S2  → traceparent outbound có parent-id = S2
        └── B HTTP server span: S3  → parent = S2, spanId = S3
            └── B DB span: S4
~~~

Nếu chỉ so hai JSON fields `A.spanId` và `B.spanId`, bạn **không thể chứng minh parent-child**; muốn xem parentId thực, mở spans đã export trong trace backend (Jaeger, Tempo, Zipkin). So trace IDs chỉ xác nhận cùng trace, chưa xác nhận topology.

### 3.1. HTTP headers không tương đương nhau

| Header | Phạm vi | Có tự được Spring Boot tracing thêm không? |
| --- | --- | --- |
| `traceparent` | W3C trace context | **Có**, với instrumented HTTP client/propagator |
| `tracestate` | W3C vendor state | Khi có dữ liệu propagatable |
| `baggage` | Propagated application context theo baggage spec | Nếu tracer/baggage config hỗ trợ |
| `b3`/`X-B3-TraceId` | B3 tracing legacy/Zipkin | Khi cấu hình consume/produce B3 |
| `X-Request-ID` | Custom application request ID | **Không**, cần injector/interceptor/gateway riêng |
| `X-Correlation-ID` | Custom app correlation ID | **Không**, trừ khi có contract riêng |

Spring Boot 3.5 có các property `management.tracing.propagation.consume`, `produce`, `type`. Trong bảng property Boot 3.5.16, mặc định **produce W3C**, consume **W3C/B3/B3_MULTI**; cấu hình `type` override lựa chọn chi tiết. Nên xác nhận hai service dùng compatible formats; không thể “A gửi B3, B chỉ nhận W3C” rồi mong cùng một trace.

### 3.2. Trace Context là input không tin cậy

Public client có thể gửi `traceparent` hợp lệ, đưa trace ID tùy ý và sampled flag. Tracer phải parse/validate chuẩn, và gateway có thể chọn **restart trace** ở ranh giới bảo mật. Không tự nối chuỗi thành header rồi giả định đã có tracing đúng; đừng lấy `traceparent` làm credential hoặc authorization decision. Dùng tracer SDK/propagator thay vì parser tự viết xử lý hex/all-zero/flags/tracestate.

## 4. Spring Boot Actuator, Observation và Micrometer Tracing

Spring Boot cung cấp:
- **Micrometer Observation**: abstraction để ghi các quan sát HTTP/server/client và các hoạt động được instrument. Observation có thể được xuất thành metrics/traces.
- **Micrometer Tracing**: facade cho OpenTelemetry hoặc Brave, tạo/đọc spans, tự gắn MDC correlation và truyền context qua client instrumentation.
- **Actuator**: auto-configuration, metrics/tracing integration; actuator **không đồng nghĩa mọi endpoint hoặc collector đã được expose**.
- **OTLP/Zipkin exporter**: gửi spans tới collector/backends khi có dependencies/config.
- **Logback/SLF4J MDC**: giữ map fields trong current logging scope để formatter đưa `traceId`, `spanId` và custom `requestId` vào log.

Hai nhóm dependency phổ biến cho Boot 3.5:
- OpenTelemetry: `spring-boot-starter-actuator` + `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` (hoặc Zipkin exporter).
- Brave: `spring-boot-starter-actuator` + `micrometer-tracing-bridge-brave` + reporter tương thích.

**Chỉ chọn một tracing stack chính** trong application. Trộn OTel agent, OTel starter và Micrometer custom instrumentation không kiểm soát có thể tạo duplicate spans. Với các HTTP handlers đã được instrument, không gắn thêm `@Observed` vào từng controller chỉ để “có trace”, tránh double observations.

### 4.1. Thứ tự xử lý khi request đi qua Spring MVC

~~~text
HTTP inbound ──► Servlet container
                   ├── observation/tracing instrumentation
                   │      tạo/khôi phục server span context
                   ├── application Request-ID filter (custom MDC)
                   │
                   └── DispatcherServlet → Controller → Service
                                            │
                                            └─ RestClient (Boot Builder)
                                                 tạo client observation/span
                                                 inject traceparent outbound
                                                 inject X-Request-ID custom
                                    ▼
                                 HTTP service B
                                    └─ extract traceparent → server span mới
~~~

Thứ tự thực tế của filters phụ thuộc Boot/context/filter order. Mục tiêu là **controller và outbound client được gọi trong active trace scope** và requestId MDC đã được set trước logs/business logic; không tự suy ra order từ sơ đồ. Đừng đăng ký cùng filter ở container và Spring Security chain, hoặc tự thêm một server observation filter lặp nếu Boot đã cung cấp.

### 4.2. Builders quyết định automatic HTTP trace propagation

Tài liệu Boot 3.5 khuyến nghị client do auto-configured builders tạo ra:
- `RestClient.Builder`
- `RestTemplateBuilder`
- `WebClient.Builder`

**Cách dễ mất instrumentation:**

~~~java
RestClient raw = RestClient.create();
// Không tự nhận toàn bộ Boot customizers / ObservationRegistry.
~~~

**Cách đúng khi cần traceparent outbound:**

~~~java
@Bean
RestClient myClient(RestClient.Builder builder) {
    return builder.baseUrl("http://127.0.0.1:8081").build();
}
~~~

Đây là **mảnh cấu hình minh họa**; project đầy đủ ở phần 6 có interceptor truyền request ID. `RestClient.Builder` phải được Spring Boot inject, không phải gọi thủ công `RestClient.builder()` rồi không gắn observation registry. Với `WebClient` reactive, cũng dùng `WebClient.Builder` do Boot quản lý.

### 4.3. Log correlation và sampling

Khi Micrometer Tracing hoạt động, Spring Boot mặc định có thể in correlation ID từ MDC `traceId` và `spanId`. Có thể custom:

~~~properties
logging.pattern.correlation=[${spring.application.name:},trace=%X{traceId:-},span=%X{spanId:-},req=%X{requestId:-}] 
logging.include-application-name=false
~~~

`logging.pattern.correlation` ở trên **có dấu cách cuối** sau `]`, tránh dính với logger name. `logging.include-application-name=false` tránh in application name trùng lặp. Đây là format text logs, không phải JSON structured logging mặc định.

Spring Boot 3.5 `management.tracing.sampling.probability` mặc định khoảng **0.1**; trong lab dùng **1.0** để dễ xem. **TraceId trong log không đảm bảo span đã được export**: có thể sampling loại, exporter off, collector unreachable, backend drop hoặc dữ liệu đến muộn.

## 5. Kiến trúc lab: một JAR, hai JVM, một trace

Để dễ chạy mà vẫn kiểm tra propagation qua socket thật, dùng một Maven project khởi chạy thành hai tiến trình:
- `frontend` cổng `8080`, `GET /entry` là điểm gọi chính.
- `backend` cổng `8081`, `GET /internal` là API downstream.
- Cả hai có cùng code, nhưng khác `spring.application.name` và port.
- `RestClient.Builder` của frontend tự propagate W3C `traceparent`.
- Một interceptor riêng chuyển `X-Request-ID` từ MDC sang outbound header.
- Filter ở mỗi JVM lấy/kiểm tra `X-Request-ID` hoặc tạo UUID mới, echo response header và set MDC có cleanup.
- Endpoint trả JSON chứa service, traceId, spanId, requestId **chỉ để lab xác minh**.

~~~text
curl ──► frontend:8080/entry ── RestClient GET ──► backend:8081/internal
           │ traceId=T, spanId=A                     │ traceId=T, spanId=B
           │ requestId=R                             │ requestId=R
           └────── HTTP JSON caller + downstream ◄──┘
~~~

**Không cần collector để kiểm tra hai ID trong JSON** vì lab dùng tracing bridge nhưng tắt export. Để xem complete span tree/latency waterfall sẽ bật exporter và collector ở mục 8. Hai endpoints không có authorization chỉ để thực hành: mặc định bind `127.0.0.1`, **không expose ra Internet**.

## 6. Dự án Java 17 / Maven hoàn chỉnh

Cây thư mục:

~~~text
http-correlation-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/correlation/
    │   │   ├── CorrelationApplication.java
    │   │   ├── RequestIdFilter.java
    │   │   ├── HttpClientConfiguration.java
    │   │   └── CorrelationController.java
    │   └── resources/application.properties
    └── test/java/com/example/correlation/
        └── RequestIdHttpTest.java
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>http-correlation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>micrometer-tracing-bridge-otel</artifactId>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-exporter-otlp</artifactId>
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

Spring Boot BOM quản lý versions transitive phù hợp. Không cần thêm `spring-boot-starter-webflux` để dùng `RestClient` vì đây là Servlet MVC. Nếu muốn WebClient/reactive thì cấu hình khác có ở phần 10.

### 6.2. CorrelationApplication.java

~~~java
package com.example.correlation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorrelationApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorrelationApplication.class, args);
    }
}
~~~

### 6.3. RequestIdFilter.java

~~~java
package com.example.correlation;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public final class RequestIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Request-ID";
    private static final String MDC_KEY = "requestId";
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        String candidate = request.getHeader(HEADER);
        String id = candidate != null && SAFE.matcher(candidate).matches()
                ? candidate
                : UUID.randomUUID().toString();

        // Restore giá trị cũ để không rò ID giữa các requests/threads.
        String previous = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, id);
        try {
            response.setHeader(HEADER, id);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }
}
~~~

**Điểm cần hiểu:**
- `@Component` khiến Boot đăng ký filter với Servlet container; **không** đồng thời dùng `HttpSecurity.addFilterBefore` với cùng instance trong một Spring Security chain.
- Regex giới hạn ký tự/độ dài, **không chứng minh nguồn header đáng tin**. Một public client có thể gửi một ID giả trông hợp lệ. Trong production, secure edge cần **strip/overwrite** incoming ID hoặc service chỉ tin trusted proxy theo policy.
- `OncePerRequestFilter` không bảo đảm một request bất đồng bộ/ERROR dispatch được xử lý duy nhất trong mọi hoàn cảnh; lab dùng synchronous MVC.
- `MDC.put` trong scope và cleanup bằng `finally` tránh ID request trước xuất hiện ở log của request sau. Không dùng request ID để cấp quyền.
- Dùng UUID cho request không có ID hợp lệ, không ghi token/PII vào mã tương quan.

### 6.4. HttpClientConfiguration.java

~~~java
package com.example.correlation;

import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    RestClient downstreamRestClient(
            RestClient.Builder builder,
            @Value("${demo.downstream.base-url:http://127.0.0.1:8081}")
            String baseUrl) {

        // builder do Spring Boot quản lý giữ HTTP tracing instrumentation.
        return builder
                .baseUrl(baseUrl)
                .requestInterceptor((request, body, execution) -> {
                    // X-Request-ID là custom propagation, tách khỏi traceparent.
                    String id = MDC.get("requestId");
                    if (id != null) {
                        request.getHeaders()
                                .set(RequestIdFilter.HEADER, id);
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Interceptor chỉ truyền **request ID**, không tự build hay override `traceparent`. Span/client context được Spring/Micrometer instrumentation thêm khi dùng Boot-provided `RestClient.Builder`. Nếu dùng `RestClient.create()` trong ứng dụng chính, có thể mất auto propagation và B bắt đầu trace mới.

### 6.5. CorrelationController.java

~~~java
package com.example.correlation;

import java.util.Objects;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class CorrelationController {
    private static final Logger log =
            LoggerFactory.getLogger(CorrelationController.class);

    private final Tracer tracer;
    private final RestClient client;
    private final String serviceName;

    public CorrelationController(
            Tracer tracer,
            RestClient downstreamRestClient,
            @Value("${spring.application.name:trace-demo}")
            String serviceName) {
        this.tracer = tracer;
        this.client = downstreamRestClient;
        this.serviceName = serviceName;
    }

    // Chỉ phục vụ localhost lab; production phải bảo vệ endpoint.
    @GetMapping("/entry")
    public EntryResult entry() {
        TraceInfo caller = currentInfo();
        log.info("entry received, requestId={}", caller.requestId());

        TraceInfo downstream = Objects.requireNonNull(
                client.get()
                      .uri("/internal")
                      .retrieve()
                      .body(TraceInfo.class),
                "Downstream returned no response body");

        log.info("backend answered, service={}", downstream.service());
        return new EntryResult(caller, downstream);
    }

    @GetMapping("/internal")
    public TraceInfo internal() {
        TraceInfo info = currentInfo();
        log.info("internal received, requestId={}", info.requestId());
        return info;
    }

    private TraceInfo currentInfo() {
        Span span = tracer.currentSpan();
        String traceId = span == null ? "missing"
                : span.context().traceId();
        String spanId = span == null ? "missing"
                : span.context().spanId();

        return new TraceInfo(serviceName, traceId, spanId,
                             MDC.get("requestId"));
    }

    public record TraceInfo(String service, String traceId,
                            String spanId, String requestId) {
    }

    public record EntryResult(TraceInfo caller,
                              TraceInfo downstream) {
    }
}
~~~

Mỗi process có hai endpoints vì chung JAR, nhưng trong lab **chỉ gọi `/entry` ở frontend** và **`/internal` ở backend**. Class nested records là public và được Jackson serialize/deserialize thành JSON. `"missing"` là marker nếu không có current span, giúp chẩn đoán chứ không phải trace ID hợp lệ.

**Không expose toàn bộ traceId/spanId trong response body public ở production.** Chúng được trả ở đây chỉ để thử equal/different. Đối với người dùng và support, response `X-Request-ID` có thể hữu ích hơn; logs và trace store được phân quyền tách biệt.

### 6.6. application.properties

~~~properties
# Giới hạn demo trên loopback; không expose các endpoints chưa auth.
server.address=127.0.0.1
server.port=8080
spring.application.name=trace-demo
demo.downstream.base-url=http://127.0.0.1:8081

management.tracing.enabled=true
management.tracing.sampling.probability=1.0

# Hai JVM cùng W3C; mặc định Boot 3.5 vốn đã produce W3C.
management.tracing.propagation.produce=W3C
management.tracing.propagation.consume=W3C

# Demo không yêu cầu collector; tắt export, KHÔNG tắt tracing.
management.otlp.tracing.export.enabled=false

# Logback MDC fields: traceId, spanId của Micrometer, requestId custom.
logging.pattern.correlation=[${spring.application.name:},trace=%X{traceId:-},span=%X{spanId:-},req=%X{requestId:-}] 
logging.include-application-name=false

# Chỉ health được expose, tránh mở toàn bộ Actuator endpoints.
management.endpoints.web.exposure.include=health
~~~

**Phân biệt:**
- `sampling.probability=1.0` phù hợp lab, không phải best practice scale production.
- `management.otlp.tracing.export.enabled=false` chỉ ngăn việc gửi spans sang collector; vẫn có thể sinh/propagate trace context.
- `management.tracing.propagation.produce/consume=W3C` là định dạng chuẩn. Khi có legacy B3, configure compatibility có kiểm soát.
- `logging.pattern.correlation` là pattern log, không tạo distributed spans nếu thiếu tracing dependencies.
- `X-Request-ID` không nằm trong W3C property; interceptor tự forward.

### 6.7. Chạy hai JVM thật

Đặt các files đúng vị trí, ở root project:

~~~bash
java -version
mvn clean package
~~~

**Terminal B** (backend, chạy trước):

~~~bash
java -jar target/http-correlation-demo-0.0.1-SNAPSHOT.jar \
  --server.port=8081 \
  --spring.application.name=backend
~~~

**Terminal A** (frontend):

~~~bash
java -jar target/http-correlation-demo-0.0.1-SNAPSHOT.jar \
  --server.port=8080 \
  --spring.application.name=frontend \
  --demo.downstream.base-url=http://127.0.0.1:8081
~~~

Trên PowerShell, dùng lệnh một dòng hoặc backtick continuation PowerShell; dấu `\` ở cuối các dòng Bash không phải continuation trong PowerShell. Hai service bind trên loopback; `127.0.0.1` của mỗi **container** không tự tham chiếu tới container khác nếu sau này chuyển Docker/Kubernetes.

**Terminal C**:

~~~bash
curl -i -H 'X-Request-ID: lab-request-12345' \
  http://127.0.0.1:8080/entry
~~~

### 6.8. Expected JSON và cách đọc

JSON **minh họa hình dạng**, IDs thay đổi theo từng lần gọi; Jackson có thể trả một dòng thay vì pretty print:

~~~json
{
  "caller": {
    "service": "frontend",
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
    "spanId": "00f067aa0ba902b7",
    "requestId": "lab-request-12345"
  },
  "downstream": {
    "service": "backend",
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
    "spanId": "12ab34cd56ef7890",
    "requestId": "lab-request-12345"
  }
}
~~~

Header frontend có:

~~~http
X-Request-ID: lab-request-12345
Content-Type: application/json
~~~

**Assertions đúng nếu tracing/propagation hoạt động:**
- `caller.service == frontend`, `downstream.service == backend`.
- `caller.traceId == downstream.traceId`, cả hai 32 hex, không phải `missing`.
- `caller.spanId != downstream.spanId`, mỗi spanId là 16 hex, không phải `missing`.
- `caller.requestId == downstream.requestId == lab-request-12345`.
- Response header `X-Request-ID` khớp requestId.
- Log ở cả JVM có thể tìm theo `req=lab-request-12345` và cùng traceId.

**Chú ý:** B server span parent thường là **A client span**, không phải A server span; chỉ xem hai JSON từ controller không thấy client span parent. Muốn xác minh parent-child và waterfall, bật exporter/collector mục 8.

### 6.9. Khi không gửi request ID

~~~bash
curl -i http://127.0.0.1:8080/entry
~~~

Frontend tạo UUID, forward sang B; response header và hai JSON objects cùng ID mới. Khi ID quá ngắn:

~~~bash
curl -i -H 'X-Request-ID: bad' \
  http://127.0.0.1:8080/entry
~~~

Filter thay bằng UUID do `bad` không đạt regex tối thiểu 8 ký tự. **Đây là input sanitation, không phải anti-spoof đầy đủ**: một ID do attacker tự chọn nhưng đúng regex vẫn được chấp nhận trong lab. Production phải có trusted edge overwrite hoặc validation theo nguồn đáng tin.

### 6.10. Khi client có sẵn W3C traceparent

~~~bash
curl -i \
  -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' \
  -H 'X-Request-ID: lab-tracing-0001' \
  http://127.0.0.1:8080/entry
~~~

Khi không có gateway reset trace context, tracer W3C có thể tiếp nối incoming traceId cho A rồi B. **Đây là test propagation local**, không phải policy production: bên ngoài có thể cố tình chọn flags/IDs, cần đánh giá restart/sampling ở trust boundary.

### 6.11. Test biểu thức equality bằng jq (không bắt buộc)

~~~bash
curl -sS \
  -H 'X-Request-ID: lab-request-12345' \
  http://127.0.0.1:8080/entry |
jq '{
  sameTrace: (.caller.traceId == .downstream.traceId),
  differentSpan: (.caller.spanId != .downstream.spanId),
  sameRequestId: (.caller.requestId == .downstream.requestId),
  caller: .caller.service,
  downstream: .downstream.service
}'
~~~

Expected logical output:

~~~json
{
  "sameTrace": true,
  "differentSpan": true,
  "sameRequestId": true,
  "caller": "frontend",
  "downstream": "backend"
}
~~~

Các giá trị `true` là **mong đợi** của project khi hoạt động đúng; không phải xác nhận đã chạy trên máy người đọc. Nếu ra false, xem bảng troubleshooting mục 13.

## 7. Integration test HTTP với embedded container

Test trong `@SpringBootTest` có tracing-reporting auto-configuration khác runtime. Vì vậy JUnit dưới đây **chỉ kiểm tra custom X-Request-ID HTTP contract**, không giả định collector có sẵn, không đòi exact span ID random. Để test trace thật, dùng `@AutoConfigureObservability` và setup tracer/exporter test, hoặc chạy hai JVM như trên.

File `src/test/java/com/example/correlation/RequestIdHttpTest.java`:

~~~java
package com.example.correlation;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RequestIdHttpTest {
    @LocalServerPort
    int port;

    String endpoint() {
        return "http://127.0.0.1:" + port + "/internal";
    }

    @Test
    void safeRequestIdIsEchoed() {
        ResponseEntity<CorrelationController.TraceInfo> r =
            RestClient.create().get()
                .uri(endpoint())
                .header("X-Request-ID", "lab-test-00001")
                .retrieve()
                .toEntity(CorrelationController.TraceInfo.class);

        assertEquals("lab-test-00001",
                     r.getHeaders().getFirst("X-Request-ID"));
        assertNotNull(r.getBody());
        assertEquals("lab-test-00001", r.getBody().requestId());
    }

    @Test
    void unsafeShortIdIsReplacedByUuid() {
        ResponseEntity<CorrelationController.TraceInfo> r =
            RestClient.create().get()
                .uri(endpoint())
                .header("X-Request-ID", "bad")
                .retrieve()
                .toEntity(CorrelationController.TraceInfo.class);

        String id = r.getHeaders().getFirst("X-Request-ID");
        assertNotNull(id);
        assertTrue(id.matches(
            "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"));
        assertNotNull(r.getBody());
        assertEquals(id, r.getBody().requestId());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Hai tests dự kiến PASS** khi source đúng. Test gọi `/internal` trực tiếp trên RANDOM_PORT, nên không cần process B. Trong **test client**, `RestClient.create()` là có chủ đích vì chỉ test raw HTTP request-ID; **ứng dụng chính** dùng injected Boot `RestClient.Builder` để nhận tracing. Test không tự chứng minh cross-process parentage; đó là chức năng của smoke test hai JVM + collector/test exporter.

## 8. Xuất spans và kiểm tra cây trace

Nếu muốn **xem latency waterfall**, cần một OpenTelemetry Collector/Tempo/Jaeger có OTLP HTTP receiver thực sự chạy. Bật exporter trong cả A và B:

~~~properties
management.otlp.tracing.export.enabled=true
management.otlp.tracing.endpoint=http://127.0.0.1:4318/v1/traces
~~~

`4318/v1/traces` là convention OTLP/HTTP, **4317** thường dành cho OTLP/gRPC. Khi chạy container, `127.0.0.1` trỏ chính container chứ không phải collector khác; dùng network DNS/Service URL được quản lý. Secure TLS/auth, rate limits và tenant authorization trong production.

Sau khi bật exporter và gọi `/entry`, trace backend lý tưởng hiển thị:

~~~text
Trace T
└── frontend HTTP server /entry          S1
    └── frontend HTTP client GET         S2
        └── backend HTTP server /internal S3
~~~

Một số instrumentation còn sinh business/DB spans. **Parent của S3 là S2** trong mô hình HTTP client/server thông thường. Không đồng nhất `trace ID được sinh` với `trace đã export thành công`:
- exporter off → logs/JSON vẫn có thể thấy ID nhưng UI trống;
- sampling thấp → một trace có thể không được lưu;
- collector unreachable → exporter báo lỗi và span mất;
- backend ingestion/index delay hoặc tenant query sai → chưa truy vấn ra span;
- log ingestion parse sai MDC → có trace UI nhưng log link chưa hoạt động.

Log correlation, trace export và metrics là **ba đường dữ liệu khác nhau**. Đừng bật mọi Actuator endpoint công khai, đừng gửi raw tokens/PII trong span attributes hoặc baggage.

## 9. Request ID, baggage và downstream headers

Trong code, requestId là một **custom HTTP header**. Interceptor đọc từ MDC rồi `set("X-Request-ID", id)` trước HTTP exchange. Điều đó **không được W3C traceparent tự làm hộ**.

Một mô hình thay thế dùng Micrometer baggage:

~~~java
// Minh họa trong một Spring-managed class có injected Tracer.
try (BaggageInScope scope =
         tracer.createBaggageInScope("support-key", "demo-123")) {
    // Gọi instrumented downstream client tại đây.
}
~~~

Imports là `io.micrometer.tracing.BaggageInScope` và `Tracer`. Khi cấu hình W3C baggage propagation phù hợp, dữ liệu baggage có thể đi qua header `baggage`. Spring Boot có `management.tracing.baggage.remote-fields` để allowlist remote fields và `management.tracing.baggage.correlation.fields` để đưa fields được chọn vào MDC. **Baggage không phải place để lưu secrets/PII.**

**Không tự forward mọi header inbound** sang service B: Authorization, Cookie, baggage hoặc correlation metadata có thể vượt trust boundary và lộ dữ liệu. Thiết kế whitelist và áp security policy riêng cho mỗi service.

## 10. Khi có @Async, Reactor và message queue

### 10.1. MDC là ThreadLocal context có scope

Trong synchronous MVC, request thường có active trace scope khi vào controller. Nhưng:

~~~java
// Phản ví dụ: tự tạo thread mới, không restore context.
new Thread(() -> log.info("background processing")).start();
~~~

Thread mới có thể mất MDC và current span. **Không dùng static/global map** để copy current request context cho mọi threads: concurrent requests sẽ đè nhau. Nếu cần truyền context, dùng Micrometer Context Propagation hoặc explicit parameters.

### 10.2. ContextPropagatingTaskDecorator

Spring Boot 3.5 Observability docs đề xuất `ContextPropagatingTaskDecorator` cho `@Async` và `AsyncTaskExecutor`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration(proxyBeanMethods = false)
class ContextPropagationConfig {
    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

Nếu tự cấu hình `ThreadPoolTaskExecutor`:

~~~java
@Bean
ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

Đây là **mảnh code**, cần imports/config cụ thể và không thuộc project lab chính. TaskDecorator capture/restore **những contexts có accessor hỗ trợ**; không mặc nhiên bảo đảm mọi custom MDC key bất kỳ sẽ được propagate. Nếu request ID phải sống lâu trong background job, lưu/truyền nó rõ ràng trong job metadata/parameters, không dựa vào HTTP thread-local vô thời hạn.

### 10.3. WebFlux và Reactor Context

Reactive WebFlux/Netty không bảo đảm một request luôn chạy cùng Java thread. Spring Boot 3.5 hỗ trợ:

~~~properties
spring.reactor.context-propagation=auto
~~~

để hỗ trợ automatic context propagation theo Micrometer. Dùng `WebClient.Builder` Boot injected, không chỉ `WebClient.create()`. Khi viết custom WebFilter hoặc operator `publishOn`/`subscribeOn`, test MDC/traceId dưới concurrency; có thể cần Reactor Context và tracing scopes thay vì `MDC.put` trực tiếp trong callback.

**Servlet `OncePerRequestFilter` không tự trở thành WebFlux `WebFilter`**. Khi app có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường chọn MVC/Servlet application type trừ khi override; xem runtime thật.

### 10.4. Kafka/RabbitMQ/SQS

HTTP `traceparent` không tự đi qua một message broker nếu message producer không instrument và không inject headers. Khi có async messaging:
- producer inject trace context vào **message headers** theo instrumentation của client/binder;
- consumer extract context, tạo consumer span hoặc **span link** tùy causal semantics;
- message có thể retry, redelivery hoặc chạy sau vài giờ; không giữ một HTTP request scope mãi;
- business ID (order ID) giúp nối các workflow dài hơn vòng đời một trace;
- kiểm tra Spring Kafka/AMQP/cloud SDK instrumentation riêng, không suy ra `RestClient.Builder` xử lý cả MQ.

## 11. Sampling, cardinality và chi phí quan sát

**Sampling** quyết định phần nào traces được ghi/export. `management.tracing.sampling.probability=1.0` giúp lab dễ quan sát nhưng production có thể quá tải collector/storage. Thiết kế sampling theo traffic, error signals, critical flows và compliance; không tin `sampled=1` từ client public là yêu cầu bắt buộc phải tốn tài nguyên.

**Metric cardinality** là mối nguy khác:
- Phù hợp low-cardinality: `service=frontend`, `method=GET`, `route=/orders/{id}`, `status=200`.
- Không phù hợp metric label trên mọi request: `traceId`, `requestId`, email, session token, raw orderId hoặc URL chứa IDs ngẫu nhiên.
- Với distributed traces, high-cardinality attributes có thể hữu ích nhưng vẫn phải kiểm soát privacy và retention.
- Không gắn `@Observed` cho mọi MVC controller đã được instrument tự động, gây duplicate observations; tạo custom observation quanh một **business operation mới** khi có giá trị.

Mảnh minh họa cho bước nghiệp vụ:

~~~java
Observation.createNotStarted("inventory.reserve", observationRegistry)
    .lowCardinalityKeyValue("result", "accepted")
    .observe(() -> {
        // Business logic chưa được framework tự instrument.
    });
~~~

Mảnh này cần `io.micrometer.observation.Observation` và `ObservationRegistry`, nằm trong Spring-managed service đã inject registry. Không đưa `requestId` vào `lowCardinalityKeyValue`; kết quả sẽ có số nhãn gần bằng số requests.

## 12. Retries, timeout và span tree không đơn giản 1-1

Nếu A gọi B hai lần do retry:
- A có thể tạo hai **HTTP client spans** theo attempts (tùy nơi retry layer đặt instrumentation).
- B có thể tạo hai **server spans**, dù ứng dụng user chỉ click một lần.
- TraceId có thể giữ nguyên nếu retry xảy ra trong cùng active context.
- Request ID thường giữ nguyên theo contract; nếu cần phân biệt attempts, có thêm attempt counter/ID.
- Nếu circuit breaker từ chối trước network, có thể **không có span từ B**.
- Nếu B đã xử lý POST nhưng A timeout rồi retry, cần **Idempotency-Key** cho nghiệp vụ, không lấy `traceId` hay `X-Request-ID` làm bảo đảm exactly-once.

~~~text
Trace T
└── A-server span S1
    ├── A-client attempt 1 S2 (timeout)
    │   └── B-server S3
    └── A-client attempt 2 S4 (success)
        └── B-server S5
~~~

Đây là sơ đồ khả dĩ, không phải lời hứa mọi library sinh đúng từng span. Đếm B log hai lần không tự chứng minh filter đăng ký trùng; hãy kiểm tra retries, proxy và request IDs.

## 13. Security và privacy

Các IDs/context có thể bị giả bởi public client. Phải có **trust boundary**:
1. Edge sinh request ID mới hoặc strip/overwrite giá trị từ client không tin cậy.
2. Backend chỉ tin metadata từ trusted proxies qua network/identity bảo vệ.
3. Tracing runtime parse W3C chuẩn và có policy restart trace khi vượt boundary/tenant; limit header size/tracestate/baggage.
4. Không cấp quyền chỉ vì caller biết một traceId/requestId.
5. Không cho người dùng tra cứu log/trace tùy ý theo ID mà không kiểm tra authorization/tenant.
6. Không log raw `Authorization`, `Cookie`, JWT, password, thẻ thanh toán hoặc query strings nhạy cảm.
7. Validate/escape header fields tránh CRLF/log injection, giới hạn kích thước/truncation.
8. Redact/retention đối với span attributes, baggage và structured logs theo data policy.
9. Dùng TLS/mTLS, ingress policies và service identities phù hợp giữa các hops.
10. Đừng expose endpoints `/entry`, `/internal` của lab ngoài localhost khi chưa có authentication.

**MDC cleanup** là phần bảo mật dữ liệu: request A không được để requestId tồn tại trên pooled thread của request B. Filter demo dùng `finally` để restore/remove. Với tracing, để tracer quản lý traceId/spanId MDC; không tự `MDC.put("traceId", request.getHeader("traceparent"))` vì nó sai semantics và có thể là header giả.

### 13.1. Response header và browser CORS

Với browser, response:

~~~http
X-Request-ID: lab-request-12345
~~~

có thể hiển thị trong Network tab nhưng JavaScript cross-origin **không tự đọc được** nếu server chưa expose custom response header. Trong CORS policy được phép, có thể thêm:

~~~http
Access-Control-Expose-Headers: X-Request-ID
~~~

Không bật CORS rộng chỉ để debug; cân nhắc allowed origins và credentials. CORS không phải authorization và cũng không chứng minh trace context đáng tin.

### 13.2. Structured log gắn traceId/spanId/requestId

Một JSON log schema **minh họa**, không phải format mặc định của Spring Boot:

~~~json
{
  "timestamp": "2026-11-08T04:30:00Z",
  "level": "INFO",
  "service": "frontend",
  "message": "downstream answered",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "requestId": "lab-request-12345",
  "http.route": "/entry"
}
~~~

Để sinh JSON thật cần logging encoder/structured logging setup tương ứng với Boot version. Một trace backend lưu **spans**, không mặc định lưu toàn bộ ứng dụng log lines. Cấu hình ingestion/index fields đúng để từ trace UI nhảy sang logs qua traceId, và từ support ticket requestId truy ra trace.

## 14. Bảng lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| A và B traceId khác nhau | Client không instrument, B không consume W3C, proxy strip traceparent | Dùng Boot RestClient.Builder, xác minh W3C outbound/inbound |
| A/B cùng requestId nhưng traceId khác | Custom header được forward, tracing context bị mất | Kiểm tra traceparent, bridge, sampler và client auto-config |
| A/B traceId giống, spanId khác | **Bình thường** | Xem span tree để xác nhận parent-child |
| B không có requestId nhưng traceId đúng | X-Request-ID không tự nằm trong W3C propagation | Dùng interceptor/baggage theo contract |
| TraceId là `missing` trong controller | Tracer không có current span hoặc tracing bị tắt | Dependency/config/active observation/HTTP stack |
| Log không có traceId nhưng controller JSON có | Log pattern/MDC scope hoặc log formatter không dùng MDC | Kiểm tra logging.pattern.correlation và scope |
| Logs có traceId nhưng trace UI trống | Exporter off, sampling, collector unreachable, ingest/index issues | Xem exporter/sampling/backend riêng |
| `@Async` mất trace fields | Thread context không propagated | ContextPropagatingTaskDecorator + tests |
| WebFlux mất trace sau scheduler hop | Reactor context config chưa phù hợp | `spring.reactor.context-propagation=auto`, instrumented WebClient |
| RequestId của client trước xuất hiện trong log client sau | Không cleanup MDC | try/finally restore/remove |
| B có nhiều spans cho một user action | Retries, async, redirect, actual multiple HTTP requests | Xem client attempts, traces, proxy |
| Span count double sau thêm `@Observed` | HTTP framework đã instrument sẵn | Gỡ duplicate annotations hoặc kiểm soát ObservationPredicate |
| Trace ID truyền nhưng parent relationship sai | Multiple trace propagators/tracestate hoặc custom manual header | Để SDK inject, inspect HTTP client spans |
| Performance giảm khi sample 100% | Trace data volume tăng | Sampling và collector sizing |
| Prometheus/Loki metric labels bùng nổ | Dùng unique traceId/requestId làm metric tag | Dùng route/method/status low-cardinality |
| Browser không đọc X-Request-ID | Header không được expose qua CORS | CORS policy có Access-Control-Expose-Headers |
| ID bị thay ở proxy | Edge overwrite/trust policy khác contract | Kiểm tra từng hop và quy tắc ingress |
| RestClient.create trong controller | Không dùng Boot customizer | Inject auto-configured RestClient.Builder |
| Trace bị chia thành hai khi có MQ | Broker producer/consumer không propagate context | Instrument message headers, span links |
| B 401/403 dù traceId đúng | IDs không phải authentication | Xem authN/authZ, không cấp quyền vì biết ID |
| ID trông hợp lệ nhưng bị giả | Chỉ validate format | Strip ở edge, giới hạn upstream tin cậy |
| Test SpringBootTest không có exporter như runtime | Test tracing auto config khác production | @AutoConfigureObservability/test exporters |
| OpenTelemetry exporter báo lỗi kết nối | Collector URL sai hoặc chưa chạy | Kiểm tra endpoint HTTP/gRPC và network/auth |

### 14.1. Runbook điều tra mất tương quan

1. Lấy **requestId** từ response header hoặc support ticket. Xác định route, timestamp và frontend instance.
2. Tìm frontend log theo requestId, kiểm tra traceId/spanId có mặt ở controller.
3. Xác nhận A gọi B bằng injected `RestClient.Builder` hoặc `WebClient.Builder` đã instrument.
4. Xem outbound `traceparent` và `X-Request-ID` trên hop **staging/được phép**; không dump secrets.
5. Xem B nhận headers gì, selected endpoint, source port/proxy rewrite, tracer bridge và propagation consume settings.
6. Nếu A/B traceId khác, debug W3C/B3 compatibility, active tracing scope và gateway header stripping.
7. Nếu trace IDs đúng nhưng collector thiếu spans, kiểm tra sampling/exporter/collector và trace backend ingestion riêng.
8. Nếu async hop gây mất, kiểm tra TaskDecorator, Reactor context, scheduled jobs/queues.
9. Kiểm tra retries, circuit breaker, timeout, 401/403 và business IDs nếu request phát sinh nhiều attempts.
10. Chốt automated tests, chuẩn hóa structured log schema, tắt debug nhạy cảm, bảo vệ observability systems.

## 15. Checklist cho production

- **Contract:** chọn `X-Request-ID`/`X-Correlation-ID`, format, owner, echo response, hop forwarding.
- **Boundary:** strip/override spoofed IDs tại ingress, chính sách traceparent/tracestate/baggage rõ.
- **Instrumentation:** Actuator + tracer bridge, không duplicate tracer stacks hoặc double observations.
- **HTTP client:** Boot auto RestClient.Builder/WebClient.Builder, không tạo raw client thiếu tracing.
- **Correlation:** traceId/spanId trong log, requestId custom MDC, cleanup request scope.
- **Async/reactive:** context propagation qua executor/Reactor; test request/child tasks.
- **Sampling/Export:** collector có auth/TLS, sampling cost/PII retention, error-rate monitoring.
- **Metrics:** không dùng unique IDs làm metric tags.
- **Downstream:** traceparent và requestId được propagate có chọn lọc; retries/timeouts và idempotency riêng.
- **Browser:** response `X-Request-ID` có thể đọc nếu CORS expose phù hợp.
- **Ops:** từ support request ID tìm logs, từ log traceId vào span tree, từ spans đến downstream lỗi.
- **Security:** không có authN/authZ bằng requestId/traceId; bảo vệ logs, traces, Actuator và collector.

## 16. Bài tập và đáp án

1. Request ID khác traceId ở contract nào?
2. W3C traceId có bao nhiêu hex? spanId và parent-id có bao nhiêu hex?
3. Hai services cùng traceId nhưng spanId khác có phải propagation lỗi không?
4. B-server span nên nhận parent-id từ A-server hay A-client span?
5. Vì sao `X-Request-ID` không tự lan truyền theo W3C traceparent?
6. Vì sao `RestClient.create()` thiếu tự động tracing so với Boot RestClient.Builder?
7. Tại sao log có traceId nhưng tracing UI chưa tìm thấy?
8. 100% sampling có luôn phù hợp production không?
9. Vì sao traceId/requestId không được dùng làm Prometheus labels?
10. Vì sao Java MDC cần restore/remove trong finally?
11. Một `@Async` có tự nhận trace context từ Servlet thread không?
12. Property nào có thể hỗ trợ Reactor Context propagation?
13. Baggage có giống `MDC` hoặc span attributes không?
14. Có thể coi requestId do client gửi là trusted chỉ vì regex hợp lệ không?
15. Nếu HTTP client retry hai lần, có nhất thiết chỉ một B-server span không?
16. Trong browser cross-origin, vì sao JavaScript có thể không đọc `X-Request-ID` response header?
17. Có thể dùng traceId thay JWT để kiểm tra quyền không?
18. Khi có message queue, trace context có tự động đi qua plain JSON body không?
19. Trace UI parent-child khác gì so chỉ so hai JSON traceId fields?
20. Có nên thêm `@Observed` lên mọi MVC controller đã tự instrument không?
21. Business order ID giúp nối nhiều traces như thế nào?
22. Khi thấy traceId là `missing`, nên kiểm tra những gì?
23. Có thể dùng X-Request-ID mặc định làm payment idempotency key không?
24. Vì sao nên tắt OTLP exporter trong demo khi chưa có collector, nhưng không tắt tracing?
25. Nếu A/B logs cùng requestId nhưng trace IDs khác, điều tra đầu tiên ở đâu?

**Đáp án tóm tắt:** (1) ID custom cho yêu cầu vs ID distributed trace. (2) Trace 32, span/parent 16 hex. (3) Không, đúng theo span model. (4) Thường A-client. (5) Header custom cần interceptor/baggage. (6) Không có Boot auto-config builder customizers. (7) Sampling/exporter/backend khác logs. (8) Không, có cost. (9) Cardinality quá cao. (10) Tránh leak request ID giữa pooled threads. (11) Không mặc định, cần context propagation. (12) `spring.reactor.context-propagation=auto`. (13) Không. (14) Không, cần trusted edge. (15) Không, mỗi attempt có thể tạo span. (16) Thiếu Access-Control-Expose-Headers. (17) Không. (18) Không, cần instrument broker headers. (19) UI kiểm tra parentage/timing; JSON equality chỉ xem same trace. (20) Tránh double observations. (21) Business ID bền qua nhiều events. (22) Tracing bridge, observation scope, config. (23) Không, contract idempotency riêng. (24) Không phát lỗi collector nhưng IDs vẫn có. (25) Outbound RestClient builder + W3C propagation/extraction.

## 17. Tài liệu chính thức

- Spring Boot 3.5, **Tracing, Logging Correlation IDs, Propagating Traces, Baggage**: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- Spring Boot 3.5, **Observability, Micrometer, Context Propagation, AsyncTaskExecutor**: https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html
- Spring Boot 3.5, **Common Application Properties**: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Boot 3.5, **Using Tracing in Tests**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- W3C, **Trace Context Recommendation**: https://www.w3.org/TR/trace-context/
- W3C, **Baggage Specification**: https://www.w3.org/TR/baggage/
- Micrometer, **Tracing Reference**: https://docs.micrometer.io/tracing/reference/
- Micrometer, **Context Propagation Reference**: https://docs.micrometer.io/context-propagation/reference/
- OpenTelemetry, **Context Propagation**: https://opentelemetry.io/docs/concepts/context-propagation/
- Spring Framework, **RestClient and REST Clients**: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Boot 3.5.16 release/OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
