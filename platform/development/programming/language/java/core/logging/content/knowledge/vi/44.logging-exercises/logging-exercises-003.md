# Thêm correlation ID vào Java Logging — dự án thực hành

## 1. Mục tiêu và tiêu chí hoàn thành

Khi nhiều HTTP requests chạy đồng thời trên cùng Java service, log của chúng có thể xen kẽ:

```text
INFO  OrderController - request received
INFO  OrderService    - checking order
WARN  InventoryClient - remote timeout
INFO  OrderController - request completed
```

Không rõ timeout thuộc request nào. **Correlation ID** là một định danh dùng để liên kết các event trong cùng một luồng xử lý:

```text
INFO  [cid=req-A11] OrderController - request received
INFO  [cid=req-A11] OrderService    - checking order
WARN  [cid=req-A11] InventoryClient - remote timeout
INFO  [cid=req-A11] OrderController - request completed
```

Đây là bài **Dự án thực hành: Thêm correlation ID**, không chỉ giải thích `MDC.put`. Sau khi hoàn thành, người học cần:

1. Xác định phạm vi một correlation ID: một HTTP request, một distributed workflow hay một batch.
2. Tạo ID mới an toàn khi không có input đáng tin; không lấy user ID, token hay session cookie làm ID.
3. Xác thực nguồn header inbound và validate cú pháp/độ dài để tránh spoofing và log injection.
4. Lưu một ID nhất quán trong Servlet request; gắn vào logging context tại từng thread/dispatch.
5. Thêm ID vào SLF4J/Logback output, response header `X-Correlation-ID` và outbound HTTP call được cho phép.
6. Dọn/khôi phục MDC trong `finally` để request B không mang nhầm ID của A.
7. Xử lý async/executor và hiểu vì sao Servlet async dispatch không tự bao mọi background thread.
8. Phân biệt `correlation_id` với OpenTelemetry `trace_id`/`span_id` và W3C `traceparent`.
9. Viết unit/integration tests xác nhận request, error, security boundary, outgoing header, concurrency, context cleanup và khả năng query log.
10. Áp dụng giới hạn dữ liệu, quyền truy cập, retention và quan sát được khi pipeline bị drop.

**Kết quả:** một chương trình Java 17 độc lập với stdout xác định để hiểu logic, tiếp theo là các file tích hợp Spring Boot 3.x, controller thử nghiệm, propagation, TaskDecorator và checklist QA. Snippets Spring cần classpath/framework; chúng không phải file `javac` độc lập.

## 2. Correlation ID là gì, khác ID nào?

| Định danh | Ý nghĩa | Người tạo / người sử dụng |
| --- | --- | --- |
| `correlation_id` | Liên kết log của cùng logical workflow | Entry service/gateway và các service liên quan |
| `request_id` | Nhận diện một HTTP request cụ thể | Edge/API gateway/application |
| `trace_id` | Nhận diện distributed trace | OpenTelemetry/Micrometer Tracing/tracer |
| `span_id` | Nhận diện một span trong trace | Tracer/SDK |
| `business_id` | Đơn hàng, giao dịch, công việc | Domain model, có rủi ro privacy |
| `idempotency_key` | Kiểm soát retry/side effects trùng | API/business persistence contract |

Một số hệ thống đặt `correlation_id=request_id` ở entry point và forward cùng ID qua service chain. Số khác dùng một correlation ID cho workflow kéo dài qua message queue. Không có một chuẩn Java bắt buộc format/lifetime cho custom header này: **phải định nghĩa rõ contract và thời điểm kết thúc**.

**Không sử dụng correlation ID làm xác thực hoặc phân quyền.** Việc client biết/đoán được ID không có nghĩa client có quyền đọc dữ liệu tương ứng. ID cũng **không thay thế** idempotency key trong thanh toán hoặc event deduplication.

### 2.1. Correlation ID và `traceparent` của W3C

Ví dụ W3C Trace Context:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

`traceparent` chứa version, trace ID (32 chữ số hex), parent ID (16 chữ số hex) và trace flags. Nó khác một custom header:

```http
X-Correlation-ID: 00b4374c-95b9-4575-821e-86184ac6470d
```

Nếu ứng dụng đã có OpenTelemetry hoặc Micrometer Tracing, hãy để **instrumentation tự inject/extract W3C context**. Không viết mã chuyển một chuỗi tùy ý từ `X-Correlation-ID` thành active trace ID. Có thể giữ cả hai trường trong logs khi có use case rõ; không bắt buộc luôn tạo ID riêng nếu trace ID đã đáp ứng nhu cầu.

## 3. Luồng xử lý mong muốn

```text
Public Client
     |
     v
Trusted Ingress/Gateway
  - strip/overwrite inbound X-Correlation-ID theo policy
  - xác thực service-to-service trust boundary
     |
     v
Java Servlet Service A
  [CorrelationIdFilter]
     |
     +-- choose ID: validated trusted incoming OR new UUID
     +-- save request attribute = ID
     +-- put MDC["correlation_id"] = ID for current dispatch
     +-- response.setHeader("X-Correlation-ID", ID)
     |
     v
Controller -> Service -> Repository (logs có cùng cid)
     |
     +-- HTTP client tới allowlisted Service B
           Header: X-Correlation-ID = ID
                 |
                 v
          Service B (validate + trust + reuse ID)
     |
     +-- async task: capture/restore context nếu task dùng worker thread
     |
  finally: restore previous MDC key; không để context rò rỉ
```

Ba ranh giới cần test:

- **Security boundary:** header do Internet client tự gửi là untrusted input. Đúng regex chưa có nghĩa đáng tin.
- **Thread boundary:** MDC có tính thread-local trong logging implementation phổ biến. Thread pool và callback không tự kế thừa context theo cách an toàn.
- **Transport boundary:** một ID xuất ở app logs không chứng minh outbound service/Collector/backend có record; phải test đường đi và log query thật.

### 3.1. Hợp đồng định dạng ID của lab

Quy ước minh họa:
- Header `X-Correlation-ID`.
- MDC key/structured field `correlation_id`.
- Inbound chỉ chấp nhận khi **đúng một giá trị** và đến từ gateway đã xác thực, loại bỏ header bên ngoài.
- Regex `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`: 1–64 ký tự ASCII, không whitespace/control characters.
- Nếu thiếu, không hợp lệ hoặc không đáng tin, tạo `UUID.randomUUID().toString()`.
- Không log raw header bị từ chối; không nối giá trị chưa validate vào message.
- Với async Servlet redispatch, **không sinh ID lần thứ hai** nếu request attribute đã có ID hợp lệ.

Regex là policy của ví dụ, không phải chuẩn bắt buộc cho mọi môi trường. Nếu hệ thống gateway dùng format khác, thay đổi cả phía ingress, các service và tests theo một contract versioned.

## 4. Chạy demo Java 17 độc lập trước khi tích hợp Spring

Bắt đầu từ một ví dụ **JDK-only** dùng `java.util.logging` (JUL) và `ThreadLocal` để mô phỏng scoped logging context. **Nó không phải SLF4J MDC**. Chương trình nhận ba request giả:

- Upstream trusted gửi `edge-101` hợp lệ → chấp nhận.
- Client không được trust gửi `spoof-999` → bỏ qua và tạo `gen-202`.
- Trusted upstream gửi chuỗi có newline → reject rồi tạo `gen-303`.

Để stdout chính xác, demo dùng generator giả với giá trị cố định. Production phải dùng giá trị ngẫu nhiên phù hợp.

Lưu file `CorrelationIdLab.java`:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class CorrelationIdLab {
    private static final String HEADER = "X-Correlation-ID";
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private static boolean valid(String value) {
        return value != null
                && value.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    }

    private static String resolve(String inbound,
                                  boolean trustedGateway,
                                  Supplier<String> generator) {
        return trustedGateway && valid(inbound)
                ? inbound : generator.get();
    }

    private static final class Scope implements AutoCloseable {
        private final String previous;

        Scope(String id) {
            previous = CURRENT.get();
            CURRENT.set(id);
        }

        @Override
        public void close() {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    private static final class Capture extends Handler {
        private final List<String> lines = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                String id = CURRENT.get();
                lines.add(record.getLevel().getName()
                        + " cid=" + (id == null ? "none" : id)
                        + " " + record.getMessage());
            }
        }

        @Override public void flush() { }
        @Override public void close() { }

        List<String> lines() {
            return List.copyOf(lines);
        }
    }

    private static void handle(String name,
                               String headerValue,
                               boolean trustedGateway,
                               String generatedId,
                               Logger logger,
                               List<String> forwarded) {
        String id = resolve(headerValue, trustedGateway,
                () -> generatedId);

        try (Scope ignored = new Scope(id)) {
            logger.info("event=request.accepted name=" + name);

            HttpRequest outgoing = HttpRequest.newBuilder(
                    URI.create("https://inventory.internal.example/stock"))
                    .header(HEADER, CURRENT.get())
                    .GET()
                    .build();

            String sent = outgoing.headers()
                    .firstValue(HEADER)
                    .orElse("none");
            forwarded.add("request=" + name + " cid=" + sent);
            logger.info("event=downstream.prepared name=" + name);
        }

        if (CURRENT.get() != null) {
            throw new IllegalStateException("CONTEXT_LEAK");
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lab.correlation");
        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);
        logger.addHandler(capture);

        try {
            List<String> forwarded = new ArrayList<>();
            handle("first", "edge-101", true,
                    "gen-101", logger, forwarded);
            handle("second", "spoof-999", false,
                    "gen-202", logger, forwarded);
            handle("third", "bad\nvalue", true,
                    "gen-303", logger, forwarded);

            for (String line : capture.lines()) {
                System.out.println(line);
            }
            for (String item : forwarded) {
                System.out.println("outbound " + item);
            }
            System.out.println("after_requests cid="
                    + (CURRENT.get() == null ? "none" : CURRENT.get()));
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 CorrelationIdLab.java
java CorrelationIdLab
```

Stdout chính xác:

```text
INFO cid=edge-101 event=request.accepted name=first
INFO cid=edge-101 event=downstream.prepared name=first
INFO cid=gen-202 event=request.accepted name=second
INFO cid=gen-202 event=downstream.prepared name=second
INFO cid=gen-303 event=request.accepted name=third
INFO cid=gen-303 event=downstream.prepared name=third
outbound request=first cid=edge-101
outbound request=second cid=gen-202
outbound request=third cid=gen-303
after_requests cid=none
```

**Giải thích:**
- `resolve` chỉ giữ incoming header khi có cả trust và cú pháp hợp lệ.
- `HttpRequest.newBuilder` chỉ chuẩn bị outbound request và header; không gọi `HttpClient.send` nên **không gửi network request**.
- Custom JUL Handler in CID từ `ThreadLocal` khi nhận log record và không dùng parent handlers, nên không có timestamp/duplicate output từ JUL console mặc định.
- `Scope.close()` restore giá trị trước đó hoặc remove, vì vậy request kế tiếp trên cùng thread không mang ID cũ.
- Header chứa newline bị regex loại trước khi được đưa vào HttpRequest/headers.
- Generator cố định chỉ để test, không phải code sinh ID production. Trong thực tế dùng `UUID.randomUUID()` và tránh dùng token hoặc thông tin người dùng.
- Không có trace SDK, collector hay bảo đảm backend delivery trong demo.

## 5. Bắt đầu project Spring Boot 3.x

Một Spring Boot 3.x **Servlet Spring MVC** project dùng Java 17, `spring-boot-starter-web`, SLF4J/Logback. Spring Boot 3 dùng `jakarta.servlet`; Spring Boot 2 dùng `javax.servlet`, không trộn hai API.

Cấu trúc gợi ý:

```text
src/main/java/com/example/correlation/
  DemoApplication.java
  CorrelationIdFilter.java
  CorrelationIdConfig.java
  ProbeController.java
  CorrelatedExecutorConfig.java
src/main/resources/
  application.properties
```

Đối với Maven project đã có Spring Boot parent/BOM, dependency web:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Đây là **đoạn trong `pom.xml`**, không phải POM hoàn chỉnh: parent/BOM, version, build config vẫn cần được tạo bởi dự án. Spring Boot starter mặc định thường có SLF4J và Logback; kiểm tra provider thực tế, không thêm nhiều SLF4J implementations mâu thuẫn.

Ứng dụng bootstrap `DemoApplication.java`:

```java
package com.example.correlation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Nếu dùng Spring WebFlux/Reactor, **không dùng Servlet filter này**; WebFlux cần `WebFilter` và reactive context propagation, không thể sao chép nguyên cơ chế ThreadLocal.

## 6. Viết CorrelationIdFilter với một ID cho logical request

Filter cần lưu ID trong Servlet request attribute qua dispatch, gắn một MDC key có scope và trả ID trong response. File `CorrelationIdFilter.java`:

```java
package com.example.correlation;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class CorrelationIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Correlation-ID";
    public static final String MDC_KEY = "correlation_id";
    private static final String ATTRIBUTE =
            CorrelationIdFilter.class.getName() + ".requestId";
    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    private final boolean trustInbound;

    public CorrelationIdFilter(boolean trustInbound) {
        this.trustInbound = trustInbound;
    }

    private static boolean valid(String raw) {
        return raw != null && VALID.matcher(raw).matches();
    }

    private static String incoming(HttpServletRequest request) {
        List<String> values = Collections.list(request.getHeaders(HEADER));
        return values.size() == 1 ? values.get(0) : null;
    }

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Object saved = request.getAttribute(ATTRIBUTE);
        String id = saved instanceof String value && valid(value)
                ? value : null;

        if (id == null) {
            String candidate = incoming(request);
            id = trustInbound && valid(candidate)
                    ? candidate : UUID.randomUUID().toString();
            request.setAttribute(ATTRIBUTE, id);
        }

        response.setHeader(HEADER, id);
        String previous = MDC.get(MDC_KEY);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable(MDC_KEY, id)) {
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
```

Điểm cốt lõi:

- Một `request attribute` giữ ID ổn định qua dispatch trong cùng Servlet request, khi container giữ thuộc tính. Không sinh ID mỗi lần filter vào lại.
- `Collections.list(request.getHeaders(...))` kiểm tra số giá trị header. Hai header trùng tên không được chọn ngẫu nhiên; một proxy có thể gộp thành chuỗi chứa dấu phẩy mà regex cũng loại.
- `trustInbound=false` là mặc định an toàn cho ứng dụng public-facing. Chỉ bật true khi ingress strip/overwrite header từ client, backend nhận traffic từ upstream đã xác thực và đường direct-bypass bị chặn.
- `MDC.putCloseable` đặt key trong scope hiện hành, `finally` restore previous value. Không `MDC.clear()` bừa trong filter vì có thể xóa trace/span metadata hoặc context của một middleware khác.
- `OncePerRequestFilter` bảo đảm theo **request dispatch**, không bảo đảm chỉ một invocation cho toàn bộ vòng đời nếu có ASYNC/ERROR dispatch.
- Error dispatch lồng trong REQUEST có cơ chế `doFilterNestedErrorDispatch` riêng; class mẫu chưa custom hook đó. Phải test container thực nếu cần correlation trong mọi error-handler log.
- Trả response header sớm giúp client nhận ID; nhưng response wrapper/error handler có thể reset headers. Test chính xác behavior tại điểm trả response, nhất là HTTP 500.
- Class trên là code tích hợp Spring Boot, không phải file JDK độc lập.

### 6.1. Validation không tạo trust

Một attacker có thể gửi `X-Correlation-ID: trusted-admin-123` — cú pháp hợp lệ nhưng danh tính không được xác minh. **Không bao giờ coi giá trị này là authentication hoặc authorization**. Gateway cần bỏ hoặc thay header untrusted, sau đó xác thực/upstream identity theo network/mTLS/service mesh policy. Header có thể dùng để tra cứu event nếu đã qua boundary an toàn, nhưng không dùng để quyết định quyền.

## 7. Đăng ký filter cho REQUEST, ASYNC và ERROR

Không gắn `@Component` lên filter ở trên nếu đồng thời dùng `FilterRegistrationBean`; nên đăng ký một instance rõ ràng.

File `CorrelationIdConfig.java`:

```java
package com.example.correlation;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;

@Configuration
public class CorrelationIdConfig {
    @Bean
    public FilterRegistrationBean<CorrelationIdFilter>
    correlationIdFilterRegistration(Environment environment) {

        boolean trusted = Boolean.TRUE.equals(environment.getProperty(
                "app.logging.trust-inbound-correlation-id",
                Boolean.class,
                false));

        FilterRegistrationBean<CorrelationIdFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new CorrelationIdFilter(trusted));
        registration.setName("correlationIdFilter");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        registration.setAsyncSupported(true);
        registration.setDispatcherTypes(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR);
        return registration;
    }
}
```

Spring Servlet filter mappings phải bao gồm dispatcher types phù hợp; chỉ override `shouldNotFilterAsyncDispatch()` không đủ để filter chạy ở ASYNC. `setAsyncSupported(true)` giúp container cho phép async processing ở filter. `Ordered.HIGHEST_PRECEDENCE+10` là lựa chọn minh họa; cần kiểm tra thứ tự thực tế so với Spring Security, tracing filters, request wrappers và các custom middleware khác.

Việc filter chạy lại ở ASYNC dispatch **không** thay thế propagation tới mọi arbitrary executor task. Đó là phần riêng ở mục 11.

## 8. Cấu hình Logback để in correlation ID

File `application.properties`:

```properties
server.port=8080

# Chỉ bật true khi ingress thật sự strip/overwrite header công khai.
app.logging.trust-inbound-correlation-id=false

# Pattern dành cho Spring Boot + Logback.
logging.pattern.console=%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [cid=%X{correlation_id:-none}] %logger{36} - %msg%n
logging.level.com.example.correlation=INFO
```

`%X{correlation_id:-none}` đọc MDC key; **pattern không tự sinh ID**. Log ngoài HTTP (startup, scheduler, task độc lập) có thể không có correlation ID: hiển thị `none` là hợp lý khi chưa tạo scope.

Nếu ứng dụng đã dùng Micrometer Tracing hoặc OpenTelemetry, logging config có thể sẵn `traceId`, `spanId` hay `trace_id`/`span_id`. Không ghi đè mất các field đó khi tùy chỉnh console pattern. Với JSON encoder, phải kiểm tra `correlation_id` thành structured field có thể query, thay vì chỉ một đoạn trong message.

Log4j 2 cũng có ThreadContext/Map pattern, nhưng file config và cú pháp riêng; đừng đưa nguyên XML Logback vào Log4j 2.

## 9. Controller kiểm thử: response header và log có cùng ID

File `ProbeController.java`:

```java
package com.example.correlation;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class ProbeController {
    private static final Logger LOG =
            LoggerFactory.getLogger(ProbeController.class);

    @GetMapping("/ping")
    public ResponseEntity<String> ping() {
        LOG.info("event=demo.ping outcome=SUCCESS");
        return ResponseEntity.ok("pong");
    }

    @GetMapping("/error")
    public ResponseEntity<String> error() {
        LOG.warn("event=demo.error.triggered");
        throw new IllegalStateException("synthetic_failure");
    }
}
```

`/error` chỉ để kiểm tra lab, không deploy route cố tình ném lỗi công khai vào production. Chạy project qua Maven Wrapper có sẵn:

```bash
./mvnw spring-boot:run
```

Phải có Maven/Wrapper và POM đúng; đây không phải `javac` một file. Gọi:

```bash
curl --include http://127.0.0.1:8080/demo/ping
```

Response ví dụ:

```text
HTTP/1.1 200
X-Correlation-ID: 6a218a3e-4f6f-499d-a7f8-456c1a899655

pong
```

UUID sẽ **khác mỗi lần chạy**; các HTTP headers khác phụ thuộc servlet container. Tìm log `event=demo.ping`; giá trị `cid` trong log phải trùng response header của **cùng request**.

Gọi tiếp:

```bash
curl --include \
  -H "X-Correlation-ID: client-picked-id" \
  http://127.0.0.1:8080/demo/ping
```

Với trust flag false, response **không được** giữ `client-picked-id`. Nếu chuyển trust true trên một môi trường backend có ingress thật, cần kiểm chứng gateway đã strip header công khai và chỉ gắn giá trị hợp lệ. Đừng chỉ đổi property thành true để thử trên public service.

Với route `/demo/error`, cần kiểm tra response header, ID trong WARN log, handler lỗi và số bản ghi. Error response có thể bị reset, nên không hứa bảo toàn header khi chưa test Servlet error lifecycle.

## 10. Gửi ID sang downstream service

Giả sử service A gọi Inventory Service B qua HTTP. Khi gọi host nội bộ được cho phép, thêm `X-Correlation-ID` từ scoped context vào outbound request.

Với Spring Framework 6.1+/Spring Boot 3.2+, có thể dùng `RestClient` interceptor:

```java
// Snippet trong @Configuration có import RestClient, MDC và @Bean.
@Bean
RestClient inventoryClient(RestClient.Builder builder) {
    return builder
        .baseUrl("https://inventory.internal.example")
        .requestInterceptor((request, body, execution) -> {
            String id = MDC.get("correlation_id");
            String host = request.getURI().getHost();

            if (id != null
                    && "inventory.internal.example"
                            .equalsIgnoreCase(host)) {
                request.getHeaders().set("X-Correlation-ID", id);
            }

            return execution.execute(request, body);
        })
        .build();
}
```

Host `inventory.internal.example` là địa chỉ minh họa, không phải backend có sẵn. Code snippet cần Spring Web, SLF4J và imports trong configuration class. Không gửi ID và credential nội bộ cho host không tin cậy; xác minh cả redirect/proxy behavior và service discovery.

Một HTTP client chạy trên worker thread không có MDC có thể gửi request **không có header** dù upstream servlet thread từng có ID. Với WebClient/Reactor dùng reactive context/instrumentation; không sao chép `MDC.get` tùy tiện và tin rằng nó luôn đúng thread.

Header custom giúp liên hệ logs khi service B nhận và giữ ID hợp lệ. **Nó không tự tạo distributed trace**; W3C propagation/tracer phải được cấu hình độc lập.

## 11. Async và thread pools: truyền context rồi dọn sạch

Trong nhiều logging backends, MDC là context theo thread. Nếu request A gọi `@Async` trên thread khác, `MDC.get("correlation_id")` có thể rỗng. Nếu worker trước đó không cleanup, nó thậm chí có thể mang ID của request B.

### 11.1. TaskDecorator cho executor cụ thể

File `CorrelatedExecutorConfig.java`:

```java
package com.example.correlation;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class CorrelatedExecutorConfig {
    @Bean("correlatedExecutor")
    public ThreadPoolTaskExecutor correlatedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("correlated-");

        executor.setTaskDecorator(task -> {
            Map<String, String> captured = MDC.getCopyOfContextMap();
            return () -> {
                Map<String, String> previous = MDC.getCopyOfContextMap();
                try {
                    if (captured == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(captured);
                    }
                    task.run();
                } finally {
                    if (previous == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(previous);
                    }
                }
            };
        });

        return executor;
    }
}
```

Trong Spring-managed bean lifecycle, executor được initialize khi bean được tạo. Nếu tự new executor không qua Spring, phải initialize và shutdown đúng cách. `TaskDecorator` snapshot MDC từ submitter rồi restore map trước đó ở worker trong `finally`.

**Giới hạn quan trọng:**
- Chỉ các tasks **được submit qua executor này** nhận context. `CompletableFuture.runAsync(task)` không chỉ định executor thường dùng common pool, không được tự bọc.
- Với `@Async("correlatedExecutor")`, còn phải có cấu hình enable async thích hợp; verify executor thật.
- `TaskDecorator` sao chép MDC **map**, không khôi phục OpenTelemetry active span hoặc Reactor Context. Nếu cần trace continuity, dùng Micrometer Context Propagation/OpenTelemetry instrumentation và tránh copy ID text như thể đó là active tracing state.
- Snapshot có thể chứa keys nhạy cảm nếu trước đó người khác đã đặt chúng vào MDC; chỉ đưa metadata đã phê duyệt vào MDC.
- `MDC.getCopyOfContextMap()` có thể trả null, nên code phải xử lý null.

### 11.2. Ví dụ CompletableFuture

```java
// Snippet trong service có executor correlatedExecutor và Logger log.
CompletableFuture<Void> work = CompletableFuture.runAsync(
        () -> log.info("event=inventory.refresh.started"),
        correlatedExecutor);
```

Đây là snippet tích hợp; task chỉ nhận correlation ID khi `correlatedExecutor` đúng bean có TaskDecorator và task được submit trong scope MDC phù hợp.

### 11.3. Servlet ASYNC dispatch không phải mọi async task

`OncePerRequestFilter` có thể chạy trên `DispatcherType.ASYNC` khi được đăng ký. Nhưng controller `Callable`/`DeferredResult` hay application background job có thể chạy **giữa** các dispatch trên thread khác, không đi qua filter. Đừng giữ MDC trên request thread mãi cho tới khi async hoàn tất; thread đó có thể phục vụ request khác. Mỗi thread/task cần scope riêng và cleanup.

Với Scheduled Jobs, Message Consumers, Kafka/Rabbit workers, định nghĩa entry boundary để tạo/chọn correlation ID mới hoặc dùng message header đã được validate. `correlation_id` không thay `message_id`, `idempotency_key` hoặc `retry_attempt`.

## 12. OpenTelemetry và Micrometer Tracing

Nếu có auto instrumentation, một log có thể chứa:

```text
correlation_id=6a218a3e-4f6f-499d-a7f8-456c1a899655
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
span_id=00f067aa0ba902b7
```

Tùy stack, Micrometer Tracing thường sử dụng MDC keys `traceId` và `spanId`, trong khi OpenTelemetry Java agent MDC instrumentation có thể dùng `trace_id` và `span_id`. Kiểm tra thực tế encoder: chỉ thêm pattern không tạo tracer hay làm span xuất hiện.

Một trace ID hiện trong log **không bảo đảm backend chứa trace**: head/tail sampling, exporter/Collector failure, retention hoặc sai environment đều có thể khiến không truy vấn được trace. Log và trace correlation là khả năng tra cứu khi cả hai pipeline hoạt động, không phải đảm bảo log storage.

Không gắn `correlation_id`, `request_id` hoặc `trace_id` vào **metric labels** cho từng request. Các nhãn này có cardinality cao; với request latency/error metrics, nên dùng route template/status/method/service để tính p95/p99 và error rate.

## 13. Viết unit tests cho ID policy

| Inbound | Trusted? | Kỳ vọng |
| --- | --- | --- |
| Không có header | No | Tạo ID mới |
| `edge-101` hợp lệ | Yes | Giữ `edge-101` |
| `client-picked` hợp lệ | No | Bỏ qua, tạo ID |
| Header rỗng | Yes | Tạo ID |
| Header có newline/tab | Yes | Reject, không log raw |
| Header 100 ký tự | Yes | Reject theo giới hạn 64 |
| Header chứa comma/control character | Yes | Reject |
| Nhiều header cùng tên | Yes | Reject hoặc policy gateway explicit |
| ID hợp lệ qua ASYNC dispatch | N/A | Giữ ID từ request attribute |
| Reused thread | N/A | Không mang CID request trước |
| Exception | N/A | MDC cleanup trong finally |
| Outbound tới host khác allowlist | N/A | Không forward header |

Tại test boundary, phân biệt request header từ Internet và header do trusted service đã xác thực gửi. Không “mock trusted = true” rồi coi đó là security test đầy đủ; còn phải có integration test tại ingress thực.

### 13.1. Ví dụ MockMvc (snippet cần test dependencies)

```java
@WebMvcTest(ProbeController.class)
@Import(CorrelationIdConfig.class)
class CorrelationIdWebTest {
    @Autowired MockMvc mvc;

    @Test
    void publicHeaderCannotSelectId() throws Exception {
        MvcResult result = mvc.perform(
                get("/demo/ping")
                    .header("X-Correlation-ID", "attacker-123"))
                .andExpect(status().isOk())
                .andReturn();

        String id = result.getResponse()
                .getHeader("X-Correlation-ID");

        assertNotNull(id);
        assertNotEquals("attacker-123", id);
        assertTrue(id.matches(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,63}"));
    }
}
```

Đây là **test class minh họa với imports bị lược bớt**, không file JDK độc lập. Cần `spring-boot-starter-test`, MockMvc, JUnit Jupiter và test property giữ trustInbound=false. Nếu Spring Security có trong project, cần cấu hình authentication phù hợp.

MockMvc không mô phỏng hoàn toàn proxy trust, network, Servlet container error/async lifecycle hoặc multithread. Phải có integration test thật khi triển khai production.

## 14. E2E tests: cùng ID trên console, response và downstream

Một bộ kiểm tra thiết thực:

1. Gọi `/demo/ping` không header. Assert response có một ID mới hợp lệ.
2. Bắt log event `demo.ping`; assert `correlation_id` trùng response header của request đó.
3. Gọi hai requests liên tiếp trên cùng worker thread; assert IDs khác nhau và không bị leakage.
4. Gửi inbound header giả từ public client; assert service không chọn nó khi trust flag false.
5. Đi qua ingress đã strip/overwrite, bật trust đúng môi trường: assert service A và B cùng ID.
6. Gây error HTTP 500: assert ID của error log/response cùng logical request, không sinh mới trên ERROR dispatch; lưu ý container có thể reset header.
7. Dùng `Callable`/`DeferredResult` và executor riêng, assert worker log có CID nếu executor được instrument.
8. Submit task khác vào worker vừa dùng, assert nó không có CID cũ.
9. Tạo HTTP client tới host không allowlist, assert không gửi CID.
10. Test JSON encoder và Collector/backend query bằng ID, không chỉ test console.
11. Tạo synthetic header chứa newline/secret, assert không xuất ở message/MDC/response.
12. Test fan-out/dual ingest: cùng event không bị ghi hai lần do root/child additivity hoặc stdout + OTLP cùng backend.

**Một log có CID chưa chứng minh request được trace end-to-end.** Phải kiểm tra từng boundary và data pipeline.

## 15. Security và privacy: những điều không được bỏ qua

- **Spoofing:** client có thể gửi ID hợp lệ về cú pháp; cần trust boundary ở gateway và backend network.
- **Log injection:** reject control characters/newline và raw headers dài; dùng structured encoding, không nối trực tiếp untrusted data.
- **PII:** không dùng email, user ID, số điện thoại, IP, session token, JWT hoặc order ID làm CID mặc định.
- **Exfiltration:** không truyền CID và baggage nội bộ sang host bên ngoài không được phép; kiểm tra redirect.
- **Authentication:** không dùng CID làm authorization, CSRF token, session hoặc idempotency key.
- **Retention:** CID dù ngẫu nhiên vẫn liên kết sự kiện; kiểm soát ACL, thời gian lưu và export.
- **Observability security:** logging pipeline có thể drop/delay; không suy “không thấy log nên hành động không xảy ra”.
- **Cleanup:** thiếu `finally` có thể làm user A liên kết sai với log của B, gây rủi ro privacy và điều tra sai.

Nếu browser JavaScript cần đọc response header, CORS có thể cần `Access-Control-Expose-Headers: X-Correlation-ID` ở **origin được phép**. Đây chỉ là khả năng nhìn thấy header đối với script, không phải cơ chế xác thực; không mở wildcard/credential policy không cần thiết.

## 16. Các anti-pattern thường gặp

**Lỗi 1 — tạo UUID trong từng service mà không forward:** request đi qua ba services nhưng có ba ID khác nhau; logs khó ghép.

**Lỗi 2 — tin mọi inbound header:** attacker có thể ép ID của người khác, gây spoofing/correlation giả.

**Lỗi 3 — log rejected header raw:** newline/secret có thể tạo log injection hoặc lộ dữ liệu.

**Lỗi 4 — sử dụng global static String:** các requests và threads ghi đè ID lẫn nhau.

**Lỗi 5 — quên cleanup MDC:** một thread pool worker giữ ID của request trước.

**Lỗi 6 — gọi `MDC.clear()` không kiểm soát:** xóa traceId/spanId hoặc context do framework khác sở hữu.

**Lỗi 7 — filter ASYNC flag nhưng thiếu dispatcher mapping:** không chạy ở async redispatch như kỳ vọng.

**Lỗi 8 — áp TaskDecorator cho executor không được sử dụng:** `CompletableFuture` vẫn chạy common pool và mất CID.

**Lỗi 9 — chỉ copy trace ID text qua MDC:** không tạo parent/child span relationship; dùng OTel Context Propagation.

**Lỗi 10 — thêm CID vào metric labels:** mỗi request tạo time series, làm tăng cardinality và chi phí.

**Lỗi 11 — gắn lại handler/appender ở root và child:** một event có thể xuất hai lần do additivity.

**Lỗi 12 — dùng CID làm identity/idempotency:** không có proof of authorization và không ngăn side effects lặp.

**Lỗi 13 — tin response header còn sau mọi 500:** error handler/container có thể reset response; cần test.

**Lỗi 14 — chỉ kiểm tra console:** log có thể không đi qua shipper/OTLP/Collector hoặc backend query.

**Lỗi 15 — forward header tùy tiện:** internal identifier bị gửi tới domain ngoài tổ chức.

**Lỗi 16 — coi một ID là audit bằng chứng:** audit đòi transaction, durability và identity contract riêng.

## 17. Runbook vận hành khi support nhận correlation ID

Khi người dùng báo lỗi kèm `X-Correlation-ID`:
1. Xác định service, environment, endpoint và khoảng thời gian.
2. Query exact `correlation_id` trong centralized logs, ưu tiên structured field.
3. Sắp theo source event timestamp và đối chiếu time zone/ingest delay.
4. Nhìn request outcome, status, error_type, retry attempts và service version.
5. Theo ID tìm log downstream ở các service trusted.
6. Nếu log có `trace_id`, mở trace nếu được sampling/lưu lại, xem critical path và dependency spans.
7. Dùng HTTP metrics/histograms xem lỗi là cá biệt hay nhiều request.
8. Không suy danh tính người gọi từ ID; mở dữ liệu nhạy cảm chỉ khi có quyền/need-to-know.
9. Nếu không thấy record, kiểm tra level/filter, MDC encoder, async propagation, sampling, queue/drop và Collector/backend.
10. Sau khi khắc phục, xác minh event mới có CID đúng ở source và backend.

Không chia sẻ toàn bộ logs/token trong ticket chỉ vì có CID. Khi trích xuất bản ghi, áp dụng redaction và hạn chế quyền theo chính sách.

## 18. Checklist nghiệm thu cuối dự án

- [ ] Định nghĩa ID lifetime, header format, max length và owner.
- [ ] Public ingress strip/overwrite untrusted header; backend không có đường bypass.
- [ ] Missing/invalid/untrusted inbound sẽ sinh ID mới; không dùng PII.
- [ ] Request attribute lưu một ID qua các dispatch được hỗ trợ.
- [ ] Filter gắn MDC tại entry và restore/remove trong `finally`.
- [ ] Logback/structured encoder thực sự xuất `correlation_id`.
- [ ] HTTP response header chứa cùng ID ở success và error theo contract đã test.
- [ ] Outbound client chỉ forward tới allowlisted service.
- [ ] Async worker được cấu hình context propagation đúng executor.
- [ ] Thread reuse không tạo leakage; tests đồng thời không lẫn ID.
- [ ] OTel/Micrometer Tracing vẫn xử lý traceparent và span hierarchy; không tự sửa trace ID.
- [ ] Không đưa CID vào metric labels; không dùng CID làm auth/idempotency.
- [ ] Không lộ synthetic token/cookie/Authorization trong logs.
- [ ] Centralized pipeline không duplicate, parser/schema đúng và query theo CID được.
- [ ] Có runbook tìm kiếm ID và phương án chẩn đoán khi trace/log bị drop.
- [ ] Monitoring có metrics cho logging failures và queue/backpressure nếu dùng remote pipeline.

**Kết luận:** Thêm correlation ID đúng cách là thiết kế **trust boundary + ID lifecycle + scoped context + propagation + verification**, không chỉ gọi `UUID.randomUUID()` rồi chèn ID vào một log message. Khi các bước trên được kiểm thử, ứng dụng Java có thể liên kết log theo request/workflow, giảm nhầm lẫn giữa threads/services và cải thiện điều tra production mà vẫn bảo vệ dữ liệu người dùng.

## Tài liệu tham khảo chính thức

- [SLF4J MDC API: putCloseable, getCopyOfContextMap, setContextMap](https://www.slf4j.org/apidocs/org/slf4j/MDC.html).
- [SLF4J User Manual](https://www.slf4j.org/manual.html).
- [Logback MDC Manual](https://logback.qos.ch/manual/mdc.html).
- [Spring OncePerRequestFilter JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html).
- [Spring MVC Async Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html).
- [Spring ThreadPoolTaskExecutor/TaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).
- [Spring Boot Tracing và Logging Correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot Logging](https://docs.spring.io/spring-boot/reference/features/logging.html).
- [OpenTelemetry Logs correlation](https://opentelemetry.io/docs/specs/otel/logs/).
- [OpenTelemetry Java MDC instrumentation](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md).
- [W3C Trace Context](https://www.w3.org/TR/trace-context/).
- [Oracle JDK 17 UUID](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html).
- [Oracle JDK 17 HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).