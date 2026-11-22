# Quan sát yêu cầu/phản hồi bằng log, tracing và Micrometer Observation trong Spring Web

Một endpoint Spring MVC có thể trả `200 OK` nhưng người dùng vẫn thấy chậm; một request khác có thể kết thúc bằng `500` nhưng log chỉ ghi “Something went wrong”. Muốn tìm nguyên nhân, cần biết **request nào đã vào hệ thống, đi qua thành phần nào, mất bao lâu, trả về status gì, có lỗi nào, và các bản ghi liên quan có thể nối với nhau hay không**.

Quan sát (observability) không chỉ là in ra nhiều log. Trong Spring Framework 6.1/Spring Boot 3.3, ba nguồn tín hiệu thường phối hợp là **logs**, **metrics** và **distributed traces**. Micrometer Observation tạo một lớp ghi nhận sự kiện chung: qua các `ObservationHandler` tương ứng, cùng một observation có thể sinh meter/metric và span, trong khi logging mô tả diễn biến cụ thể của ứng dụng. Bài học tập trung vào request/response của **Spring MVC trên Servlet stack**, có đối chiếu ranh giới HTTP client và truy vết liên dịch vụ khi cần.

## 1. Từ một request đến ba loại bằng chứng

Giả sử ứng dụng có endpoint `GET /api/items/42`. Nhìn vào ba tín hiệu:

| Tín hiệu | Trả lời câu hỏi gì? | Ví dụ nội dung | Phạm vi và điểm yếu |
| --- | --- | --- | --- |
| **Log** | “Điều gì đã xảy ra trong lần xử lý này?” | “start lookup”, “lookup failed”, exception stack trace, `traceId` | Chi tiết, có thứ tự gần đúng; thiếu correlation thì khó nối nhiều dòng/dịch vụ |
| **Metric** | “Tần suất, thời gian, tỷ lệ lỗi của nhiều request là bao nhiêu?” | Số lần, tổng/thống kê độ trễ của `http.server.requests` theo method/status/URI template | Rẻ để tổng hợp/xem xu hướng; không mô tả từng lần xử lý |
| **Trace** | “Một lần xử lý cụ thể đã đi qua các service/span nào, mất thời gian ở đâu?” | Trace A có server span → client span → downstream server span | Cần tracer, truyền context và backend; sampling có thể bỏ qua một số request |

Ví dụ điều tra: cảnh báo p95 latency tăng ở `GET /api/items/{id}` từ metric; lọc trace chậm để thấy span gọi dịch vụ danh mục chiếm đa số thời gian; dùng `traceId` của trace đó để xem log và nguyên nhân cụ thể. **Không dùng một metric để khôi phục nội dung request đơn lẻ, cũng không dùng log rời rạc thay cho tỷ lệ lỗi tổng hợp.**

```text
Client
  └─ HTTP GET /api/items/42
      ├─ Servlet filter / Spring MVC
      │   ├─ HTTP server Observation: http.server.requests
      │   │   ├─ ObservationHandler → metric timer
      │   │   └─ tracing handler → server span (khi có tracer)
      │   ├─ Controller/Service → application logs
      │   └─ HTTP response 200
      └─ HTTP client / network response

Người vận hành
  ├─ metrics → lượng request, duration, status, nhóm URI
  ├─ traces  → quan hệ span và thời gian trên một trace
  └─ logs    → sự kiện, lỗi, dữ kiện phục vụ điều tra
```

Tên `http.server.requests` là tên observation/meter trong cấu hình mặc định Spring Framework 6.1. Backend như Prometheus có thể đổi quy tắc đặt tên meter khi xuất dữ liệu. Không mặc định coi một tên metric trong Prometheus là nguyên văn tên observation.

## 2. Bắt đầu từ log request/response có ý nghĩa

### 2.1. Log ở đúng cấp độ

Log có thể đặt ở controller/service để mô tả sự kiện thực sự có giá trị: bắt đầu xử lý, lựa chọn nhánh quan trọng, kết quả nghiệp vụ, lỗi cần triage. Khi cần tổng quan từng HTTP request, dùng filter hoặc access log của server/proxy thay vì rải câu `log.info` vào mọi controller. Mỗi nguồn quan sát có phạm vi khác nhau:

- **Application log:** controller/service biết nghiệp vụ và nguyên nhân; filter biết HTTP method/status nhưng không tự biết tất cả chi tiết nghiệp vụ.
- **Servlet filter log:** có thể ghi method, route, status và duration; thứ tự filter/dispatch ảnh hưởng điều gì được ghi, nhất là async request.
- **Container access log:** ghi giao dịch HTTP từ góc nhìn server; format và cấu hình phụ thuộc Tomcat/Jetty/Undertow.
- **Proxy/ingress log:** phản ánh những request bị chặn hoặc lỗi ngay ở proxy, có thể không hề vào ứng dụng Java.

Đừng mở log debug toàn bộ body, token, cookie hoặc header `Authorization` ở production. URL có thể chứa email, ID hoặc query nhạy cảm; ưu tiên **route template** `/api/items/{id}` thay cho raw URL khi log phục vụ tổng hợp. Nếu cần log chi tiết để xử lý sự cố, phải xác định rõ các trường cho phép, mức giữ dữ liệu và nơi truy cập.

### 2.2. Controller ví dụ có log nghiệp vụ

Giả sử ứng dụng Spring Boot 3.3/Java 17+ có `spring-boot-starter-web` và `spring-boot-starter-actuator`. Tệp `src/main/java/com/example/observe/ObserveApplication.java`:

```java
package com.example.observe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObserveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ObserveApplication.class, args);
    }
}
```

Tệp `src/main/java/com/example/observe/ItemController.java`:

```java
package com.example.observe;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private static final Logger log =
            LoggerFactory.getLogger(ItemController.class);

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public ResponseEntity<ItemDto> find(@PathVariable long id) {
        log.debug("Looking up item");
        String label = service.findLabel(id);
        log.info("Item lookup completed");
        return ResponseEntity.ok(new ItemDto(id, label));
    }

    public record ItemDto(long id, String label) {}
}
```

Ví dụ intentionally không in `id` vào log. Khi hệ thống được phân quyền và phân loại dữ liệu, có thể log khóa định danh đã được duyệt, nhưng không nên coi mọi `@PathVariable` đều an toàn để xuất log.

Tệp `src/main/java/com/example/observe/ItemService.java`:

```java
package com.example.observe;

import org.springframework.stereotype.Service;

@Service
public class ItemService {
    public String findLabel(long id) {
        return "Item-" + id;
    }
}
```

Request `GET /api/items/42` dự kiến trả JSON tương đương `{"id":42,"label":"Item-42"}` và status 200. Đó là kết quả logic của mã mẫu; thứ tự trường JSON không phải là hợp đồng bắt buộc khi không cấu hình thêm.

Có thể cấu hình mức log:

```properties
logging.level.root=INFO
logging.level.com.example.observe=DEBUG
```

`DEBUG` cho package riêng làm rõ sự kiện mà không mở log DEBUG toàn bộ Spring. Trong môi trường thật, log ở mức `INFO` trên mỗi request có thể tạo lưu lượng lớn; cân nhắc dựa vào metrics/access logs cho thống kê thường xuyên và giữ log nghiệp vụ ở đúng mức.

### 2.3. Nếu viết filter, phải tôn trọng vòng đời Servlet

Khi cần request summary độc lập với controller, một `OncePerRequestFilter` tối giản có thể ghi method, status và thời gian cho những dispatch thông thường. Ví dụ sau là **đoạn minh họa cách chọn thông tin an toàn**, không thay thế instrumentation chuẩn của Micrometer:

```java
// Bên trong doFilterInternal(...) của OncePerRequestFilter:
long started = System.nanoTime();
try {
    filterChain.doFilter(request, response);
} finally {
    long elapsedMs = java.util.concurrent.TimeUnit.NANOSECONDS
            .toMillis(System.nanoTime() - started);

    Object matchedPattern = request.getAttribute(
            org.springframework.web.servlet.HandlerMapping
                    .BEST_MATCHING_PATTERN_ATTRIBUTE);

    String route = matchedPattern instanceof String pattern
            ? pattern
            : "UNMATCHED";

    logger.info("method={} route={} status={} durationMs={}",
            request.getMethod(), route, response.getStatus(), elapsedMs);
}
```

Đoạn trên không phải class Java độc lập: nó cần nằm trong một subclass filter đã định nghĩa `logger` và nhận tham số `request`, `response`, `filterChain`. Với Servlet async, thời gian ở `finally` có thể chỉ phản ánh thời điểm dispatch hoàn thành, chưa phải lúc response cuối cùng gửi xong. Nếu cần đo đúng lifecycle HTTP, ưu tiên instrumentation Servlet server tích hợp sẵn và cấu hình dispatch phù hợp.

Không tự tạo thêm `Observation` tên `http.server.requests` quanh mỗi request **khi đã có** `ServerHttpObservationFilter`; có thể nhân đôi metric/span và làm sai số liệu.

## 3. Micrometer Observation: đơn vị ghi nhận chung

Micrometer phân biệt các thành phần:

- `ObservationRegistry`: registry tiếp nhận/điều phối observation; không có handler hữu hiệu, observation có thể không sinh metric hay span.
- `Observation`: khoảng hoạt động được đặt tên, có thời điểm bắt đầu/kết thúc và context.
- `Observation.Context`: lưu ngữ cảnh cho quá trình xử lý observation (bao gồm trạng thái lỗi và key-values).
- `ObservationConvention`: quy định tên/contextual name và nhãn (key-values) phù hợp từng loại observation.
- `ObservationHandler`: nhận sự kiện lifecycle, ví dụ tích hợp ghi metric và tạo trace span.
- `ObservationFilter`: tùy biến key-values/context khi observation hoàn tất; khác với Servlet Filter.

Một observation cho HTTP server thường nằm quanh một lần trao đổi request/response; tên mặc định ở Spring MVC là `http.server.requests`. Ngoài observation tự động, bạn có thể chủ động quan sát một đoạn nghiệp vụ khi cần biết thời gian của đoạn đó.

Tệp `src/main/java/com/example/observe/ObservedCatalog.java`:

```java
package com.example.observe;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedCatalog {
    private final ObservationRegistry registry;

    public ObservedCatalog(ObservationRegistry registry) {
        this.registry = registry;
    }

    public String loadCategory() {
        return Observation.createNotStarted(
                        "catalog.load", registry)
                .lowCardinalityKeyValue("operation", "read")
                .observe(() -> "general");
    }
}
```

`.observe(Supplier<T>)` bao quanh phần xử lý: khởi động observation, thực hiện supplier và kết thúc observation kể cả khi supplier ném exception (theo lifecycle hỗ trợ của API). Với `spring-boot-starter-actuator`, Spring Boot tự cấu hình hạ tầng registry/handler cho các khả năng có trên classpath. Bài ví dụ dùng tên riêng `catalog.load` nên **không thay** metric HTTP `http.server.requests` do Framework cung cấp.

Với workload có thể lỗi, ưu tiên dùng phương thức `observe(...)` hoặc `try`/`finally` đúng vòng đời thay vì `start()` rồi quên `stop()`. Observation bị bỏ dở sẽ khiến duration/trace không phản ánh đúng thực tế.

### 3.1. Cardinality: điều kiện để metrics sử dụng được

**Low cardinality** là tập giá trị có số lượng hữu hạn, ổn định. Ví dụ tốt: `method=GET`, `status=200`, `uri=/api/items/{id}` hoặc `operation=read`. Các nhãn này phù hợp làm chiều phân loại metric.

**High cardinality** là tập giá trị có thể tăng theo số request, ví dụ `itemId=42`, `userId=abc123`, URL chứa ID, request ID. Đưa chúng vào **metric tag** có thể gây bùng nổ số time series, tăng bộ nhớ, chi phí lưu và rủi ro quá tải. Micrometer Observation phân biệt:

| Loại key-value | Metric | Trace | Ví dụ |
| --- | --- | --- | --- |
| `lowCardinalityKeyValue` | Có thể tham gia tag/dimension | Có thể tham gia span attribute | `operation=read` |
| `highCardinalityKeyValue` | Không tự trở thành meter tag | Có thể tham gia span attribute | `itemId=42` nếu được phép lưu |
| Log field | Không tự trở thành metric tag | Không tự xuất hiện trong trace | Sự kiện nghiệp vụ và stack trace |

Không có nghĩa high-cardinality trace tag luôn an toàn: tracing backend cũng có chi phí và chính sách bảo mật. Giá trị cá nhân/secret có thể bị lộ qua span; phải có nguyên tắc lọc/redact tương tự log.

## 4. Quan sát HTTP server tự động trong Spring MVC

Spring Framework hỗ trợ `ServerHttpObservationFilter` (Servlet filter) để tạo server observation cho request/response. Trong ứng dụng Spring Framework thuần, cần đăng ký filter cùng `ObservationRegistry` hữu hiệu. Spring Boot Actuator thường tự cấu hình các thành phần này khi dependencies và tính năng observability tương ứng hiện diện.

Một số nhãn thường gặp theo convention mặc định Spring Framework 6.1:

| Nhãn | Nội dung | Vì sao hữu ích |
| --- | --- | --- |
| `method` | HTTP method như GET/POST | So sánh traffic và latency theo method |
| `uri` | **URI pattern** của handler nếu xác định được | Tổng hợp nhiều `/api/items/42`, `/api/items/43` thành một tuyến |
| `status` | HTTP status response, ví dụ 200/404/500 | Phân biệt thành công và thất bại ở mức HTTP |
| `outcome` | Nhóm kết quả exchange | Theo dõi các nhóm trạng thái |
| `exception` | Exception quan sát được hoặc `none` | Tìm sự cố chưa được xử lý ở phạm vi observation |

Số/loại nhãn và tên có thể khác giữa phiên bản/convention/backend. Đặc biệt, **status 500 không đồng nghĩa tự động có `exception=SomeException`**. Khi `@ExceptionHandler` xử lý exception và chuyển thành response bình thường, exception có thể không thoát qua Servlet observation filter để được ghi là lỗi. Phân biệt **HTTP response status**, **lỗi nghiệp vụ**, và **throwable được công cụ instrumentation quan sát**.

Request không map được hoặc redirect có thể được gán các giá trị URI dự phòng như `NOT_FOUND`, `REDIRECTION` hoặc `UNKNOWN` tùy convention. Vì vậy truy vấn dựa trên route chỉ chính xác khi routing information có thể được instrumentation xác định.

Spring MVC **không tự bao gồm mọi thứ**: filter phía proxy, browser network, TCP handshake, thời gian browser render và một dependency bên ngoài chưa instrument sẽ không có span đúng nghĩa chỉ vì HTTP server observation tồn tại.

## 5. Dựng phép thử có thể kiểm chứng bằng Actuator

Với Boot 3.3, dependency Gradle điển hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đoạn này bổ sung vào project đã có plugin Spring Boot và version quản lý dependency. Với môi trường phát triển nội bộ có thể bật endpoint metrics:

```properties
spring.application.name=web-observe-demo
management.endpoints.web.exposure.include=health,info,metrics
```

Theo mặc định, endpoint Actuator được expose qua HTTP rất hạn chế; `metrics` cần cho phép lộ rõ trong cấu hình. URL thông thường:

```bash
curl -i http://localhost:8080/api/items/42
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
```

Thao tác thứ nhất tạo request, thao tác thứ hai liệt kê tên meter đã xuất hiện; thao tác thứ ba (khi có dữ liệu/handler phù hợp) trả số đo/tags cho `http.server.requests`, chẳng hạn số lượng `COUNT` và thời gian tổng `TOTAL_TIME`. **Không cố định số đo** vì chúng thay đổi theo lưu lượng và thời điểm chạy. Để lọc một tag:

```bash
curl -G "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=uri:/api/items/{id}"
```

Các lệnh trên giả định shell hỗ trợ ký tự xuống dòng `\` như Bash. Với Windows PowerShell, chạy lệnh trên một dòng hoặc dùng quy tắc xuống dòng của PowerShell. Response metrics endpoint là dữ liệu JSON của Actuator; tên meter sử dụng trong URI là tên gốc `http.server.requests`, không nhất thiết trùng tên xuất sang Prometheus.

**Giới hạn:** đây mới là phép kiểm tra instrument/metric tại application instance, không phải hệ thống giám sát tập trung. Muốn thu thập dài hạn, cần meter registry/exporter được cấu hình (Prometheus, OTLP, v.v.), backend lưu và dashboard/alert. Endpoint Actuator có thể lộ thông tin vận hành nhạy cảm, vì vậy cần giới hạn network và authorization khi expose ở môi trường thật.

### 5.1. Kiểm tra bằng integration test

Trong ứng dụng đơn giản ở trên, có thể xác minh request HTTP thật tạo HTTP server meter trong `MeterRegistry`. Tệp `src/test/java/com/example/observe/HttpObservationTest.java`:

```java
package com.example.observe;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class HttpObservationTest {
    @Autowired
    TestRestTemplate http;

    @Autowired
    MeterRegistry meters;

    @Test
    void realRequestRecordsHttpServerTimer() {
        var response = http.getForEntity("/api/items/42", String.class);
        assertTrue(response.getStatusCode().is2xxSuccessful());

        Timer timer = meters.find("http.server.requests")
                .tags("method", "GET", "uri", "/api/items/{id}")
                .timer();

        assertNotNull(timer);
        assertTrue(timer.count() >= 1L);
    }
}
```

Test này giả định cấu hình Actuator/Micrometer HTTP server observation mặc định và ứng dụng chỉ có các endpoint đơn giản như trên. Nó chứng minh **request được gửi qua embedded HTTP server** và có meter ghi nhận ít nhất một lần; không chứng minh trace đã được gửi đến collector, log chứa MDC hoặc downstream propagation hoạt động. Với test chỉ gọi trực tiếp controller method, server observation thường không được tạo; với `MockMvc`, tùy cấu hình instrumentation/filter trong test context mà sự kiện có/không được ghi, vì vậy không được suy diễn tương đương live HTTP.

Kiểm tra chạy bằng:

```bash
./gradlew test --tests com.example.observe.HttpObservationTest
```

Trên Windows dùng `.\gradlew.bat test --tests com.example.observe.HttpObservationTest`. Đây là hướng dẫn thực hiện test cho ví dụ; không phải tuyên bố test đã chạy trong một project cụ thể.

## 6. Distributed tracing: trace/span và correlation ID

**Trace** đại diện một chuỗi hoạt động liên quan đến một request xuyên nhiều component. Mỗi **span** là một đoạn của chuỗi đó; thường có trace ID chung, span ID riêng và parent/child relationship:

```text
Trace ID: abc...
  [HTTP SERVER GET /api/items/{id}]        60 ms
      ├─ [catalog.load]                    15 ms
      └─ [HTTP CLIENT GET /inventory/{id}]  38 ms
            └─ [inventory: HTTP SERVER]    30 ms
```

Số thời gian và ID ở sơ đồ chỉ mang tính minh họa, không phải phép đo. Không cộng tổng các span trong sơ đồ để thay thế request duration; span có thể lồng nhau hoặc chạy song song. Để có trace phân tán, cả phía client và server của lời gọi liên dịch vụ cần instrument và **truyền trace context** đúng cách.

Micrometer Observation chỉ tự thành trace span khi có tracing handler/tracer đúng trên classpath và registry. Thêm `spring-boot-starter-actuator` chưa đủ để xem các trace từ backend. Với Boot 3.3, một cấu hình tracing OpenTelemetry xuất sang Zipkin có thể dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
```

Ví dụ này là cấu hình tracer/exporter **bổ sung** cho ứng dụng web phần trước và cần có Zipkin collector chạy sẵn. Có thể chọn bridge Brave hoặc backend khác theo yêu cầu; không trộn nhiều bridge/exporter mà không có chủ đích. Với Boot 3.3, đường cấu hình Zipkin có dạng `management.zipkin.tracing.*`; không suy đoán nó giống các phiên bản Boot mới hơn.

Để mọi request mẫu có cơ hội được ghi khi học tracing tại môi trường local:

```properties
management.tracing.sampling.probability=1.0
management.zipkin.tracing.endpoint=http://localhost:9411/api/v2/spans
```

Spring Boot 3.3 mặc định sampling khoảng 10%; `1.0` tạo nhiều trace hơn, chỉ hợp lý cho môi trường kiểm chứng lưu lượng thấp. Ở production, chọn sampling theo lưu lượng, chi phí và nhu cầu điều tra. **Không thấy một trace trong backend chưa chắc là hệ thống không xử lý request**, vì có thể request không được sample, exporter/collector không hoạt động hoặc context không truyền qua dịch vụ khác.

### 6.1. Correlation ID trong log

Khi Micrometer Tracing được cấu hình, Spring Boot có khả năng đưa `traceId` và `spanId` vào MDC (Mapped Diagnostic Context) cho log trên luồng đang có span. Ví dụ hình thức log:

```text
2026-10-21 INFO [abc123-traceIdLikeValue-def456] Item lookup completed
```

Đây là **minh họa format**, không phải trace ID hợp lệ có thể tra cứu từ request thực. Trong cấu hình thực, hãy dùng trace ID/format do tracer và logging pattern tạo. Cùng một trace có thể gồm nhiều span ID; hai dòng ở các service khác nhau cùng `traceId` không nhất thiết có cùng `spanId`.

Đối với điều tra, cách làm hiệu quả là lấy `traceId` từ trace backend rồi tìm tất cả log cùng ID trong khoảng thời gian tương ứng. Nếu chỉ thêm một random `requestId` độc lập trên từng service, hệ thống phải có cơ chế truyền ID đó; nó **không tự** tạo quan hệ parent/child hay duration như distributed tracing.

### 6.2. Truyền context khi gọi dịch vụ khác

Spring Boot auto-configure observation/tracing cho một số HTTP client builder. Ví dụ khi có một backend khác:

```java
// Đoạn minh họa bên trong một @Service có RestClient được inject.
RestClient client = builder.baseUrl("http://localhost:8081").build();
String response = client.get()
        .uri("/inventory/{id}", 42)
        .retrieve()
        .body(String.class);
```

Ở đây `builder` là `RestClient.Builder` **do Spring Boot cung cấp** qua dependency injection. Tracing infrastructure có thể tự truyền W3C trace context hoặc propagation format được cấu hình. Nếu bạn tự gọi `RestClient.create()` hoặc `new RestTemplate()` mà bỏ qua builder auto-configured và không gắn observation registry/interceptor tương ứng, propagation tự động có thể bị mất. Phải kiểm tra trace phía downstream, không chỉ log service nguồn.

Đối với `@Async`, task executor, thread pool, virtual thread hoặc reactive pipeline, context/thread-local/MDC **không được bảo đảm** tự đi theo mọi bước chuyển luồng. Cần dùng cơ chế context propagation được hỗ trợ cho version/mô hình thực thi đang dùng và test qua ranh giới thread. Việc tự copy MDC mà quên clear/restore còn có thể làm “dính” ID từ request này sang request khác.

## 7. Theo dõi lỗi và response một cách đáng tin

Một server observation có thể ghi status HTTP 4xx/5xx, nhưng trạng thái `error` trong trace/tag còn phụ thuộc exception có đi qua tầng instrument hay đã bị xử lý. Ví dụ controller dùng `@ExceptionHandler` đổi exception thành response 404; công cụ quan sát ở Servlet filter có thể thấy status 404 mà **không thấy exception thoát ra**.

Vì vậy khi tìm lỗi cần phối hợp:

1. **Metric theo HTTP status/outcome:** endpoint nào tăng 5xx hoặc duration tăng?
2. **Application log ở nơi xử lý exception:** có đủ error code và stack trace theo chính sách bảo mật không?
3. **Trace span:** request đi đến dịch vụ nào, có span lỗi, timeout hoặc latency bất thường không?
4. **Client-visible response:** status/body/header thực sự trả cho người dùng có khớp mong đợi không?

Nếu phải đánh dấu exception đã xử lý là lỗi trong observation, Spring Framework cung cấp khả năng tương tác `ServerRequestObservationContext`, nhưng hãy cấu hình nhất quán, tránh tự gán mọi response 4xx thành “unexpected exception”. Đối với hệ thống thực tế, phân biệt lỗi validate do client, lỗi business kỳ vọng và lỗi hạ tầng.

### 7.1. Log request và response body có nên dùng không?

Ghi toàn bộ body có vẻ giúp debug nhưng thường tạo ba nhóm vấn đề:

- **Bảo mật/quyền riêng tư:** password, token, thông tin thanh toán, PII có thể bị lưu trong log hoặc trace.
- **Hiệu năng:** body lớn/streaming/multipart khiến việc đệm nội dung tốn RAM, I/O và độ trễ.
- **Ngữ nghĩa Servlet:** request input stream chỉ đọc được theo lifecycle; wrapping/đọc sai thời điểm có thể làm hỏng xử lý downstream hoặc không chứa toàn bộ response.

Nếu thật sự cần một số field phục vụ điều tra, hãy log structured fields được chọn lọc, giới hạn độ dài và redact trước khi xuất. Với API audit, cần định nghĩa một cơ chế audit riêng có policy, retention và phân quyền, thay vì dùng log HTTP debug làm nguồn dữ liệu chính thức.

## 8. Kiểm thử từng lớp thay vì nhìn một lần chạy

| Mục tiêu | Cách kiểm tra | Bằng chứng thu được | Điều chưa chứng minh |
| --- | --- | --- | --- |
| Business log đúng nhánh | Unit test với appender/test logger hoặc integration test | Một event được ghi khi branch chạy | MDC, tracer hay HTTP transport |
| MVC response đúng | `MockMvc` với context/filter phù hợp | Status, headers, JSON/view và routing | Socket thật hoặc collector |
| Metric HTTP | Live HTTP `RANDOM_PORT` + `MeterRegistry` | Timer/count và tag route/status sau request | Span đã export |
| Tracing | Chạy tracer/collector, gửi request, tra trace | Server span, trace ID và liên kết span | Mọi request đều được sample |
| Propagation | App A gọi app B qua instrumented client | Trace ID chung, quan hệ span xuyên service | Không tự xác thực mọi network hop |
| Vận hành production | Dashboard/alert + kiểm tra policy | Xu hướng, cảnh báo, giới hạn retention/access | Không thay thế test logic chức năng |

Đối với metric latency, đừng dùng một lần gọi nhanh để khẳng định performance của hệ thống. Cần phân biệt cold start/warmup, phân phối thời gian, traffic mix và những dependency bị mock. Histogram/percentile phụ thuộc cấu hình registry và backend; hãy cấu hình rõ trước khi làm SLO dựa trên p95/p99.

## 9. Các lỗi phổ biến và cách chẩn đoán

**Có log nhưng không có trace ID:** kiểm tra đã thêm tracing bridge chưa, request có active span không, logging pattern có giữ MDC không và có chuyển thread ngoài context không. `spring-boot-starter-actuator` riêng lẻ không đảm bảo log correlation dựa trên tracing.

**Có metric nhưng không thấy trace:** có thể chưa có tracer/exporter, sampling loại request, collector sai endpoint hoặc exporter không kết nối. Metrics và tracing có các pipeline khác nhau mặc dù được tạo từ cùng Observation.

**Không thấy `http.server.requests`:** kiểm tra application thực sự có request sau khi khởi động, observation instrumentation/registry có được cấu hình và enable không, endpoint `metrics` đã expose chưa, và tên meter đúng theo version/convention không. Với Spring Framework không dùng Boot, cần đăng ký `ServerHttpObservationFilter`.

**Metric có quá nhiều chuỗi khác nhau:** kiểm tra tag có raw path, user ID, request ID hoặc query value không; chuyển sang route template/nhãn low-cardinality, giữ thông tin request cụ thể trong log/trace có kiểm soát.

**Trace thiếu downstream service:** dùng HTTP client builder được instrument; kiểm tra context propagation header, sampler của từng service và việc context không bị mất khi chuyển thread.

**Status 500 mà exception tag `none`:** có thể lỗi đã được `@ExceptionHandler` xử lý hoặc filter không nhìn thấy throwable. So status và log handler, đừng quy kết instrument hỏng từ một tag duy nhất.

**Timer thấp nhưng người dùng vẫn chậm:** HTTP server timer thường không bao gồm DNS, TLS negotiation ở client, proxy queue, truyền qua mạng và browser rendering. Cần ghép metric ở client, proxy và máy chủ.

**Quan sát gây thêm tải:** bật 100% tracing/DEBUG hoặc log full body dưới tải lớn có thể ảnh hưởng latency và chi phí. Thiết kế sampling, lọc tag, log level và retention phù hợp; đo tác động trước khi áp dụng đại trà.

## 10. Checklist thực hành

Khi triển khai observability cho Spring MVC, thực hiện theo chuỗi:

1. Xác định endpoint/luồng cần điều tra, status và latency kỳ vọng.
2. Bật Actuator/Observation có kiểm soát; tạo một request rồi xác minh meter `http.server.requests` được cập nhật.
3. Tách log nghiệp vụ có giá trị khỏi access log; không log secret/body không cần thiết.
4. Nếu cần trace, bổ sung một tracer bridge và exporter phù hợp; kiểm tra trace ID trong log và server span ở collector.
5. Dùng HTTP client builder đã được instrument để kiểm chứng một call qua service thứ hai với trace ID chung.
6. Giữ nhãn metric low-cardinality, chọn đúng URI template; cấu hình alert dựa trên status, throughput và latency có ý nghĩa.
7. Kiểm tra sampling, context propagation qua async, exception handling và mức truy cập các endpoint quan sát.

Một hệ thống “quan sát được” khi từ triệu chứng ban đầu như “tỷ lệ 5xx tăng” có thể đi từ **metric** đến request/trace liên quan, rồi đến **log hoặc span** có bằng chứng giải thích. Đó là tiêu chí sử dụng, không phải chỉ có ba thư viện trong danh sách dependency.

### Tài liệu tham khảo

- Spring Framework 6.1 — Observability Support: https://docs.spring.io/spring-framework/reference/6.1/integration/observability.html
- Spring Boot 3.3 — Observability: https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html
- Spring Boot 3.3 — Metrics và Metrics Endpoint: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Tracing và Log Correlation: https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html
- Micrometer — Observation Documentation: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
