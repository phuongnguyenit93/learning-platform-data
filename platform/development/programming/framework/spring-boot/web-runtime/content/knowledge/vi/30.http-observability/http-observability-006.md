# Quan sát lỗi được xử lý và phân biệt với lỗi đã ghi nhận tự động

## 1. Vì sao một HTTP 500 có thể xuất hiện với `error=none`?

Giả sử một ứng dụng Spring Boot gặp lỗi khi xử lý request. Controller ném `InventoryUnavailableException`; một `@ExceptionHandler` bắt lỗi và trả JSON `ProblemDetail` với HTTP status **503**. Người dùng biết yêu cầu đã thất bại. Log của ứng dụng cũng có thể chứa exception. Nhưng biểu đồ `http.server.requests` trong Micrometer lại có thể hiển thị **`error=none`** cho request ấy.

Điều này không nhất thiết là bug của hệ thống metrics. Trong **Spring Framework 6.1 / Spring Boot 3.3**, HTTP server observation thường tự ghi nhận exception làm **observation error** khi exception **chưa được web framework xử lý** và đi ra tới ranh giới instrumentation. Exception đã được `@ExceptionHandler`, `@ControllerAdvice` hay cơ chế trả `ProblemDetail` xử lý thì có thể **không còn exception thoát ra** để filter/server observer nhìn thấy. Response vẫn mang status 4xx/5xx, nhưng observation context chưa được đánh dấu lỗi.

Bài này phân biệt bốn điều thường bị đánh đồng:

1. **Exception xảy ra** trong business/controller/handler.
2. **Exception đã được xử lý** thành một HTTP response (ví dụ 404, 422, 500, 503).
3. **HTTP response status/outcome** mà client thực sự nhận.
4. **Observation error** được ghi trên Micrometer `Observation.Context`, làm cơ sở cho metric tags và — khi có tracing — dấu vết liên quan.

Đồng thời cần phân biệt **log ERROR** với observation error: một dòng log không tự biến thành tag `error` hay đánh dấu trace span error.

**Phạm vi:** Spring Boot 3.3.13, Spring Framework 6.1.x, Micrometer Observation và Java 17+. Khi nâng Spring Framework 7.x hoặc Micrometer/OpenTelemetry major versions, kiểm tra semantic conventions/API theo phiên bản thực tế; ví dụ trong bài cố ý giữ cùng một version family để tránh suy diễn hành vi mới vào hệ thống cũ.

## 2. Mô hình: log, metric, trace và HTTP response không phải một thứ

```text
                         HTTP request
                              │
                    Observation bắt đầu
                              │
                     Controller / Service
                              │
                 Exception xảy ra hay không?
                      ┌───────┴────────┐
                      │                │
                     Không             Có
                      │                │
                HTTP 2xx...      Exception handling
                                       │
                     ┌─────────────────┴─────────────────┐
                     │                                   │
             Được xử lý nội bộ                  Thoát ra tới lớp
            @ExceptionHandler/...                instrumentation
                     │                                   │
              HTTP 4xx/5xx                         Auto record error
                     │                             nếu được quan sát
              context.error có thể null                  │
                     │                                   │
     Optional context.setError(exception)                 │
                     │                                   │
                     └─────────────────┬─────────────────┘
                                       │
                              Observation kết thúc
                                       │
                     ┌─────────────────┴─────────────────┐
                     ▼                                   ▼
              Metrics tags                         Tracing (nếu bật)
           status, outcome, error                span/error association
                                       │
                                Logs là kênh riêng
```

Một exception không được xử lý có thể tự động đi qua instrumentation, nhưng **cách web container, error dispatch, reactive pipeline và các filters chạy** quyết định observer nào nhìn thấy lỗi. Ngược lại, exception được xử lý có thể trả 500 hoàn toàn hợp lệ mà không được đánh dấu vào observation nếu không có thao tác bổ sung.

Đừng suy từ `status >= 500` rằng `context.getError() != null`. Cũng đừng suy từ `error != none` rằng status nhất định bằng 500: lập trình viên có thể đánh dấu một exception nghiệp vụ đã được xử lý thành **HTTP 404**. Hai chiều của tín hiệu mang **ngữ nghĩa khác nhau**.

### 2.1. Một bảng phản ví dụ

| Request | Hành vi | HTTP status | Observation error thường thấy | Ý nghĩa |
|---|---|---:|---|---|
| `GET /demo/ok` | Không có exception | 200 | `none` | Request thành công bình thường |
| `GET /demo/not-found` | Ném exception, `@ExceptionHandler` đổi thành 404, không đánh dấu | 404 | `none` | Client error được xử lý |
| `GET /demo/handled-500` | Exception thật được xử lý thành 500, không đánh dấu | 500 | `none` | **Status 500 không đồng nghĩa error tag có exception** |
| `GET /demo/marked-503` | Exception được xử lý, handler gọi `context.setError(ex)` | 503 | `InventoryUnavailableException` | Đánh dấu có chủ đích |
| `GET /demo/unhandled` | Exception thoát ra pipeline, filter nhìn thấy | Thường 500 | Exception type khi quan sát thấy | Auto-record tùy server/error dispatch |
| Một handler trực tiếp trả `ResponseEntity.status(503)` | Không ném exception | 503 | `none` | HTTP failure status nhưng không có Java exception |
| Một handler tự gọi `setError(ex)` rồi trả 200 | Response success, error context có exception | 200 | Exception type | Có thể tạo telemetry khó hiểu, nên tránh nếu không có lý do |

Các giá trị `error` minh họa giả định instrumentation HTTP server đang bật và dùng convention mặc định của Framework 6.1. Với hệ thống đã custom observation convention, tags có thể đổi; với thiếu dependency/registry hoặc sampling/observation predicate, có thể không có measurement.

## 3. Spring Boot 3.3 tạo HTTP server observation bằng cơ chế nào?

Spring Boot Actuator tích hợp **Micrometer Observation** và auto-configuration HTTP instrumentation. Observation là một sự kiện có **tên**, **thời gian sống**, **context** và **key-values**. Khi có `ObservationHandler` phù hợp, nó được chuyển thành metrics/traces. Boot mặc định gọi HTTP server observation bằng tên:

```text
http.server.requests
```

Trong hệ Prometheus, một timer Micrometer có thể được export thành series như `http_server_requests_seconds_count`, `..._sum`, `..._max` tùy registry/config. Đây không phải tên luôn xuất hiện giống nhau trong mọi backend; tốt nhất dùng tên observation/Micrometer meter ở tầng Java trước khi quyết định tên PromQL.

**Ở Servlet/MVC**, Spring Framework có `org.springframework.web.filter.ServerHttpObservationFilter`. Boot/Actuator cấu hình filter thích hợp để tạo/đóng observation cho HTTP request khi instrumentation được bật.

**Ở Spring WebFlux**, observation được tích hợp ở reactive `HttpHandler`/`WebHttpHandlerBuilder` (không phải servlet filter), với `org.springframework.http.server.reactive.observation.ServerRequestObservationContext`. Boot cấu hình cho runtime reactive khi có observation infrastructure.

Cùng tên observation, nhưng **hai loại request context nằm ở package khác nhau**:

| Servlet/MVC | WebFlux/Reactive |
|---|---|
| `org.springframework.http.server.observation.ServerRequestObservationContext` | `org.springframework.http.server.reactive.observation.ServerRequestObservationContext` |
| `ServerHttpObservationFilter.findObservationContext(HttpServletRequest)` | `ServerRequestObservationContext.findCurrent(exchange.getAttributes())` |
| Servlet filter scope | Reactive HTTP exchange/pipeline |
| `HttpServletRequest` | `ServerWebExchange` |
| `@ExceptionHandler` có thể dùng `HttpServletRequest` | `@ExceptionHandler` có thể dùng `ServerWebExchange` |

Chúng đều cung cấp `setError(Throwable)` thông qua observation context. **Đừng import sai package** rồi nghĩ một handler WebFlux có thể dùng Servlet `HttpServletRequest`, hoặc ngược lại.

### 3.1. Dependency nào cần có?

Trong nhiều ứng dụng Spring Boot:
- `spring-boot-starter-web` hoặc `spring-boot-starter-webflux`: web runtime.
- `spring-boot-starter-actuator`: quản lý và auto-configure Micrometer observation/metrics.
- `micrometer-registry-prometheus`: tùy chọn, để expose/export Prometheus metrics.
- Micrometer Tracing bridge + tracer/exporter: **chỉ khi muốn distributed traces**.

**Chỉ thêm Actuator không bảo đảm trace được gửi ra một tracing backend.** Metrics timer có thể có mà traces chưa có exporter; cũng có thể có logs nhưng metrics instrumentations đã bị disable. Nên kiểm tra dependencies và cấu hình của từng tín hiệu.

Spring Boot 3.3 cũng có `management.observations.http.server.requests.name` để đổi tên observation, và `management.observations.enable.*` để vô hiệu các observation theo prefix. Nếu tự đổi tên, câu lệnh truy vấn meter trong bài phải đổi theo.

## 4. Các key-value mặc định: `error`, `status`, `outcome`, `uri`

Ở Spring Framework 6.1, mặc định HTTP server observation ghi **low-cardinality** keys:

| Key | Giá trị minh họa | Nói lên điều gì |
|---|---|---|
| `method` | `GET` | HTTP method |
| `status` | `200`, `404`, `503`, `UNKNOWN` | Status response đã được gửi/nhận diện |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Nhóm status HTTP 2xx/4xx/5xx |
| `uri` | `/demo/marked-503`, `NOT_FOUND`, `UNKNOWN` | Route pattern hoặc fallback có cardinality thấp |
| `error` | `none`, `InventoryUnavailableException` | Class name của exception đã được ghi nhận trong observation |
| `exception` | Tương tự `error` | **Deprecated** trong convention 6.1; đừng xây dashboard mới dựa hoàn toàn vào nó |

Cụ thể:
- `status=503` là thông tin **kết quả HTTP**, không chứng minh một Java exception đã đi qua instrumentation.
- `outcome=SERVER_ERROR` được suy từ status 5xx; không nhất thiết là `error` đã được gán.
- `error=none` thường có nghĩa observation không được gắn Throwable, **không chứng minh trong business chưa bao giờ có exception**.
- `uri` là pattern khi framework biết mapping, ví dụ `/orders/{id}`, giúp giảm cardinality.
- `http.url` được tài liệu Framework liệt kê là một **high-cardinality key**. Nó phù hợp với trace trong một số mô hình, không nên đưa raw URL/query/user ID vào metrics tags có thể bùng nổ số series.

**Quan trọng về tên:** Spring Framework 6.1 có cả `error` và key `exception` deprecated trong tài liệu. Đừng nhầm logic của Boot 2.x `WebMvcMetricsFilter`/`exception` cũ với observation mới của Boot 3.x. Luôn dùng tên tags thực được registry trả về và xem semantic conventions của phiên bản đang chạy.

### 4.1. Metrics, tracing và logs nhìn một request khác nhau

```text
HTTP 503
  ├── Metric: http.server.requests{
  │       status="503",
  │       outcome="SERVER_ERROR",
  │       error="InventoryUnavailableException",
  │       uri="/demo/marked-503"
  │    }
  ├── Trace/span: error/event thông qua tracing handler
  │    nếu có bridge, sampling và exporter phù hợp
  └── Log: WARN/ERROR tùy chính sách ghi log ứng dụng
```

Ba nhánh này không tự có quan hệ một–một:
- Một log `ERROR` được viết bởi controller advice có thể không tác động Observation.
- Một request HTTP 500 có thể có error tag none nếu exception đã được giải quyết.
- Một request HTTP 404 có thể ghi nhận Throwable nếu application chủ động đánh dấu.
- Một error đã ghi trong observation không bảo đảm một backend tracing đã nhận span (sampling/exporter có thể thiếu).

## 5. “Lỗi đã ghi nhận tự động” trong MVC nghĩa là gì?

Spring Framework mô tả rõ: `ServerHttpObservationFilter` tự xem exception là error khi exception **không được web framework xử lý** và **đi lên tới filter**. Với:

```text
Controller throws Exception
         │
         ▼
DispatcherServlet
         │
         ├── @ExceptionHandler / HandlerExceptionResolver xử lý thành ResponseEntity
         │          │
         │          └── không còn exception thoát ra ngoài
         │                   → filter thường không biết lỗi Java gốc
         │
         └── exception không được xử lý
                    │
                    ▼
           lọt lên Servlet filter
                    │
                    ▼
           context.setError(...) tự động theo instrumentation
```

**Giới hạn lớp quan sát Servlet:** filter có phạm vi theo thứ tự filters và request handling phía sau nó. Một lỗi do **Servlet container error handling** xử lý ở tầng thấp hơn hoặc một filter chạy ngoài scope observation không mặc định có active span/context. Spring Framework ghi rõ nếu cần quan sát lỗi tầng container riêng phải dùng instrumentation thích hợp của container (ví dụ Tomcat Valve) và phân biệt với HTTP request observation.

Trong MVC, việc có `@ResponseStatus`/`ResponseStatusException` hoặc `ResponseEntityExceptionHandler` có thể biến Throwable thành error response **trước** khi đi tới filter. Do đó số lượng exception trong log/HTTP response có thể lớn hơn số exception được gắn tag. Đây là hành vi theo vị trí instrument, không đơn giản là “Actuator mất lỗi”.

**Không nên ép toàn bộ lỗi 4xx thành observation error.** Một request `/orders/123` không tồn tại được xử lý thành 404 là một business event dự kiến. Bạn có thể chỉ cần đo status/outcome/route, và dùng business metric riêng cho các sự kiện đáng chú ý. Đánh dấu mỗi 404 như exception trong error dashboards sẽ làm tăng nhiễu.

## 6. “Lỗi đã được xử lý” không đồng nghĩa “lỗi không quan trọng”

Exception được xử lý trong ba tình huống rất khác:

1. **Kịch bản dự kiến:** user yêu cầu tài nguyên không có → 404, lỗi validation → 400/422; có thể không cần đánh dấu observation error.
2. **Hỏng phụ thuộc tạm thời:** DB/broker/downstream unavailable → 503, circuit breaker open → 503; thường nên đánh dấu nguyên nhân thực sự nếu request thất bại.
3. **Lỗi lập trình/unknown exception:** `NullPointerException` hoặc invariant violation → 500; nếu custom `@ExceptionHandler` đổi thành response thân thiện, vẫn phải cân nhắc đánh dấu observation error để metrics/tracing không bỏ sót.

Không phải quy tắc “mọi 5xx phải gắn một Throwable”: một HTTP 503 chủ động trả vì bảo trì không nhất thiết có exception Java thật. Bạn có thể đo 503 bằng status/outcome và business availability metrics. **Đừng tạo một fake Throwable cho mọi status code chỉ để có tag.**

Một bảng quyết định thực tiễn:

| Trường hợp | HTTP status khuyến nghị | Có `setError(ex)`? | Lý do |
|---|---:|---|---|
| Validation input sai thường gặp | 400/422 | Thường không | Client cần sửa dữ liệu |
| Resource không tồn tại | 404 | Thường không | Business absence dự kiến |
| Không đủ quyền | 403 | Thường không | Authorization denial là signal riêng |
| Rate limit | 429 | Thường không | Theo dõi rate-limit metrics riêng |
| Từ chối vì bảo trì chủ động | 503 | Có thể không | Status đã phản ánh unavailability; có thể không có Throwable |
| Downstream timeout đã được xử lý | 504/503 | Thường có | Đây là operational failure thật, đáng gắn cause |
| DB exception được map thành ProblemDetail 503 | 503 | Thường có | Tránh che lỗi đã được xử lý |
| NullPointerException được catch-all map thành 500 | 500 | Có | Unexpected server bug |
| Một request thành công nhờ fallback | 200 | Cân nhắc observation riêng | Có thể làm HTTP span bị đánh dấu lỗi dù client thành công |

Cần thống nhất policy với SRE/observability team: `error` tag có nghĩa **lỗi vận hành cần chú ý** hay **bất kỳ Throwable từng bị ném**? Nếu không định nghĩa, dashboard và alert sẽ có ý nghĩa mơ hồ dù code chạy đúng.

## 7. Đánh dấu lỗi đã xử lý trong Spring MVC

Tài liệu Spring Framework 6.1 đưa API:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.filter.ServerHttpObservationFilter;

ServerHttpObservationFilter.findObservationContext(request)
        .ifPresent(context -> context.setError(exception));
```

Đây là **mảnh code** trong một phương thức đang có `request: HttpServletRequest` và `exception: Exception`. `findObservationContext` trả Optional; nếu request không có observation context, `ifPresent` chỉ không làm gì, không gây lỗi NullPointerException.

Cách dùng điển hình là trong `@ExceptionHandler` trước khi trả `ResponseEntity` hoặc `ProblemDetail`. Điều này **đánh dấu observation** đã tạo cho request hiện tại, không khởi tạo một observation thứ hai, không thay HTTP status và không tự ném lại exception.

**Thứ tự quan trọng:** nên gọi `setError` **trước khi observation kết thúc**, tức khi request handling vẫn đang ở trong lifecycle. Gọi sau response/async task ngoài request scope có thể quá muộn hoặc không còn context.

Nếu một handler bắt nhiều exceptions, chỉ đánh dấu theo policy; đừng gắn lỗi dự kiến/không mong muốn indiscriminately. Nếu một exception đã được auto-record, thêm `setError` không có lợi ích mặc định. Với các request qua các filters/custom error handlers, cần đảm bảo cùng context và không vô tình ghi đè một lỗi gốc hữu ích bằng wrapper lỗi khác.

## 8. Ví dụ Java 17+ runnable: Spring MVC và bốn tình huống

Project `mvc-http-observation-demo` dùng Spring Boot 3.3.13, embedded Tomcat và Actuator. Có một controller với các endpoints:
- `/demo/ok`: 200, không có Throwable.
- `/demo/not-found`: 404 đã xử lý, **không** gọi `setError`.
- `/demo/handled-500`: 500 đã xử lý, **không** đánh dấu — dùng để chứng minh status khác error.
- `/demo/marked-503`: 503 đã xử lý và gọi `setError` trong ControllerAdvice.
- `/demo/unhandled`: ném exception không có matching handler — dùng để thảo luận auto-record và container error dispatch (không assert error class cố định).

### 8.1. Cấu trúc project

```text
mvc-http-observation-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/observation/
    │   │   └── MvcObservationApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/observation/
            └── HttpObservationIntegrationTest.java
```

### 8.2. Gradle build

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-actuator` cung cấp Micrometer metrics/Observation integration. Chưa thêm tracing bridge/exporter; vì thế ví dụ **kiểm tra metrics**, không tuyên bố có trace đã xuất tới Jaeger/Tempo.

### 8.3. Application properties

`src/main/resources/application.properties`:

```properties
server.port=8080
spring.application.name=mvc-http-observation-demo

# Chỉ expose endpoint metrics cho demo, KHÔNG phải cấu hình production.
management.endpoints.web.exposure.include=health,info,metrics

# Mặc định trong Boot 3.3 là http.server.requests.
# Nếu đổi tên, test và curl truy vấn meter cũng phải đổi.
management.observations.http.server.requests.name=http.server.requests
```

**Bảo mật Actuator:** `/actuator/metrics` cung cấp thông tin vận hành. Trên production nên giới hạn authentication/authorization, network, management port và endpoint exposure phù hợp; không công khai metrics, env/config hoặc prometheus tuỳ tiện. `management.endpoints.web.exposure.include` chỉ quyết định endpoint **exposed**, không phải cấp quyền truy cập an toàn.

### 8.4. Controller, exceptions và ControllerAdvice

`src/main/java/com/example/observation/MvcObservationApplication.java`:

```java
package com.example.observation;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.ServerHttpObservationFilter;

@SpringBootApplication
public class MvcObservationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcObservationApplication.class, args);
    }
}

@RestController
class ObservationDemoController {

    @GetMapping("/demo/ok")
    String ok() {
        return "ok";
    }

    @GetMapping("/demo/not-found")
    String notFound() {
        throw new MissingItemException("Item not found");
    }

    @GetMapping("/demo/handled-500")
    String handledWithoutMarking() {
        throw new HandledBugException("Handled bug");
    }

    @GetMapping("/demo/marked-503")
    String handledWithMarking() {
        throw new InventoryUnavailableException(
                "Inventory service unavailable");
    }

    @GetMapping("/demo/unhandled")
    String unhandled() {
        throw new IllegalStateException("Unhandled demo failure");
    }
}

@RestControllerAdvice
class ObservationDemoAdvice {

    @ExceptionHandler(MissingItemException.class)
    ResponseEntity<ProblemDetail> missing(MissingItemException ex) {
        return problem(
                HttpStatus.NOT_FOUND,
                "Missing item",
                "The requested item does not exist");
    }

    @ExceptionHandler(HandledBugException.class)
    ResponseEntity<ProblemDetail> bugWithoutMarking(
            HandledBugException ex) {
        // Cố ý KHÔNG setError, nhằm chứng minh 500 != error tag.
        return problem(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Handled bug",
                "An internal failure was handled");
    }

    @ExceptionHandler(InventoryUnavailableException.class)
    ResponseEntity<ProblemDetail> unavailable(
            InventoryUnavailableException ex,
            HttpServletRequest request) {

        // Điểm quan trọng nhất của bài:
        // Gắn exception đã được @ExceptionHandler xử lý
        // vào context HTTP server observation hiện tại.
        ServerHttpObservationFilter.findObservationContext(request)
                .ifPresent(context -> context.setError(ex));

        return problem(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Inventory unavailable",
                "Please retry later");
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String title, String detail) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                status, detail);
        body.setTitle(title);
        return ResponseEntity.status(status).body(body);
    }
}

class MissingItemException extends RuntimeException {
    MissingItemException(String message) {
        super(message);
    }
}

class HandledBugException extends RuntimeException {
    HandledBugException(String message) {
        super(message);
    }
}

class InventoryUnavailableException extends RuntimeException {
    InventoryUnavailableException(String message) {
        super(message);
    }
}
```

**Tính runnable của mã:**
- Đây là **một file Java** đúng tên `MvcObservationApplication.java`. Chỉ có một top-level `public class`. Các controller, advice và exception classes khác package-private và nằm cùng package nên component scanning áp dụng được.
- `@RestControllerAdvice` xử lý ba exception types cụ thể. `IllegalStateException` cố ý không có matching handler, giúp thảo luận lỗi thoát ra pipeline.
- `ProblemDetail` tồn tại từ Spring Framework 6, và `ResponseEntity<ProblemDetail>` được framework serialize thành error response body theo contract.
- Method `unavailable` lấy `HttpServletRequest` và gọi đúng `ServerHttpObservationFilter.findObservationContext(request)` ở **Servlet stack**.
- `problem(...)` đặt HTTP response status độc lập với `context.setError(ex)`.
- App không định nghĩa custom `SecurityFilterChain` hoặc `@EnableWebMvc`, nên giữ Boot MVC/Actuator auto-configuration theo demo.

**Cảnh báo về cách dùng:** `HandledBugException` được cố ý bỏ đánh dấu cho mục đích học tập. Đây **không phải chính sách khuyến nghị** cho lỗi server không mong đợi trong sản phẩm thực. Trong production thường muốn gắn lỗi nghiêm trọng đã được xử lý để metrics/traces hỗ trợ điều tra.

### 8.5. Chạy ứng dụng

Trong thư mục project với JDK 17+ và Gradle được cài:

```bash
gradle bootRun
```

Nếu project có Gradle Wrapper: `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trong Windows PowerShell. Chạy trên port 8080; không cần database hay dịch vụ ngoài.

Gửi requests:

```bash
curl -i http://localhost:8080/demo/ok
curl -i http://localhost:8080/demo/not-found
curl -i http://localhost:8080/demo/handled-500
curl -i http://localhost:8080/demo/marked-503
curl -i http://localhost:8080/demo/unhandled
```

Dự kiến:
- `/demo/ok` → **200**, text body `ok`.
- `/demo/not-found` → **404**, response `ProblemDetail`.
- `/demo/handled-500` → **500**, response `ProblemDetail` nhưng **không chủ động set observation error**.
- `/demo/marked-503` → **503**, response `ProblemDetail` và `InventoryUnavailableException` được gắn vào context observation.
- `/demo/unhandled` → **500** do container/error handler tiêu chuẩn; behavior của `error` tag có thể phụ thuộc đường đi error dispatch và cấu hình servlet filter.

Trong demo, body `ProblemDetail` có dạng tương tự:

```json
{
  "type": "about:blank",
  "title": "Inventory unavailable",
  "status": 503,
  "detail": "Please retry later",
  "instance": "/demo/marked-503"
}
```

Spring Boot có thể thêm/không thêm một số fields theo configuration và lỗi; **không assert full JSON byte-for-byte** nếu mục tiêu chỉ là status và tags. `instance` được framework tạo khi có URL context và phù hợp; không phải API response business contract bắt buộc ở mọi cài đặt.

## 9. Quan sát metric với Actuator `/actuator/metrics`

Sau khi gửi từng request, xem danh sách meters:

```bash
curl -s http://localhost:8080/actuator/metrics
```

Tìm tên `http.server.requests`. Có thể truy vấn meter:

```bash
curl -s \
  "http://localhost:8080/actuator/metrics/http.server.requests"
```

Truy vấn có lọc tags bằng query parameters (curl `-G` để tự URL encode):

```bash
curl -sG \
  "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/demo/not-found" \
  --data-urlencode "tag=error:none"

curl -sG \
  "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/demo/handled-500" \
  --data-urlencode "tag=error:none"

curl -sG \
  "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/demo/marked-503" \
  --data-urlencode "tag=error:InventoryUnavailableException"
```

Dự kiến các series/measurement tương ứng xuất hiện sau khi request hoàn tất và registry thu thập. Những response từ `/actuator/metrics` có JSON về `name`, `description`, `measurements`, `availableTags`; không tự khẳng định output JSON có thứ tự field cố định hoặc một giá trị timing nhất định.

**Điều cần đọc đúng:**
- `/demo/handled-500` có thể có `status=500`, `outcome=SERVER_ERROR`, **`error=none`**.
- `/demo/marked-503` có thể có `status=503`, `outcome=SERVER_ERROR`, **`error=InventoryUnavailableException`**.
- `/demo/not-found` có `status=404`, `outcome=CLIENT_ERROR`, **`error=none`**.

Nếu một test/endpoint không xuất hiện, kiểm tra Actuator, meter registry, observation enablement, path mapping và thời điểm kết thúc request. Đừng dùng tên Prometheus `http_server_requests_seconds_count` để truy vấn `/actuator/metrics`; endpoint Actuator nhận **tên Micrometer meter** `http.server.requests`.

### 9.1. Nếu muốn Prometheus

Thêm dependency **tùy chọn** vào `dependencies`:

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Đổi exposure:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Sau đó:

```bash
curl -s http://localhost:8080/actuator/prometheus
```

Tên metric trong Prometheus có thể được chuyển đổi thành `http_server_requests_seconds_count`, `_sum`, `_max` theo registry naming/meter configuration. Không ghép chuỗi metric/label cố định vào dashboard mà chưa xem output thực tế. Trên production phải bảo vệ Actuator/Prometheus endpoint bằng network controls/authentication; không mở public chỉ để nhìn tags.

## 10. Integration test chứng minh status và observation error độc lập

Dùng **JUnit + Spring Boot Test + Micrometer MeterRegistry** để gọi HTTP thật và kiểm tra có time-series đúng tags. Test không chỉ gọi thẳng method của ControllerAdvice, vì làm vậy **không tạo HTTP server observation**.

**`src/test/java/com/example/observation/HttpObservationIntegrationTest.java`:**

```java
package com.example.observation;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpObservationIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    MeterRegistry meterRegistry;

    private HttpResponse<String> get(String path)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                        "http://127.0.0.1:" + port + path))
                .GET()
                .build();

        return HttpClient.newHttpClient().send(
                request,
                HttpResponse.BodyHandlers.ofString());
    }

    private void assertRecorded(
            String uri, String status, String error) {

        await().atMost(Duration.ofSeconds(5))
                .untilAsserted(() -> {
                    Timer timer = meterRegistry
                            .find("http.server.requests")
                            .tag("uri", uri)
                            .tag("method", "GET")
                            .tag("status", status)
                            .tag("error", error)
                            .timer();

                    assertThat(timer).isNotNull();
                    assertThat(timer.count()).isGreaterThan(0);
                });
    }

    @Test
    void handledNotFoundHasStatus404ButNoErrorTag()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/not-found");

        assertThat(response.statusCode()).isEqualTo(404);
        assertRecorded("/demo/not-found", "404", "none");
    }

    @Test
    void handled500MayHaveErrorNone()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/handled-500");

        assertThat(response.statusCode()).isEqualTo(500);
        assertRecorded("/demo/handled-500", "500", "none");
    }

    @Test
    void markedExceptionAppearsInErrorTag()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/marked-503");

        assertThat(response.statusCode()).isEqualTo(503);
        assertRecorded("/demo/marked-503",
                "503", "InventoryUnavailableException");
    }

    @Test
    void successfulRequestHasNoErrorTag()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/ok");

        assertThat(response.statusCode()).isEqualTo(200);
        assertRecorded("/demo/ok", "200", "none");
    }
}
```

`spring-boot-starter-test` cung cấp AssertJ, Awaitility và JUnit cho project Boot 3.3. `HttpClient` ở đây là Java 17 JDK HTTP client, không cần thêm thư viện third-party. `await()` chờ meter series xuất hiện trong một khoảng cho phép, tránh race timing giữa response network và observation completion.

**Đây là kết quả kỳ vọng, không phải test đã chạy trong tài liệu.** Chạy:

```bash
gradle test
```

Nếu context có cấu hình observation bị vô hiệu, registry khác hoặc custom naming/tags, assertions phải được điều chỉnh. Trong demo mặc định Actuator với SimpleMeterRegistry, tests dự kiến tìm được timer. Nếu chạy concurrent tests làm meter count tăng, chỉ assert `count()>0` thay vì đòi bằng một.

**Giới hạn test:**
- Bốn tests chứng minh hai dimensions `status` và `error` độc lập ở các handler được chọn.
- Không assert exact auto-recorded exception ở `/demo/unhandled` vì Servlet container/error dispatch có thể thay đổi lớp Throwable ghi nhận và request scope.
- Nó không chứng minh tracing backend nhận span; chưa thêm tracing exporter.
- Nếu đổi `management.observations.http.server.requests.name` hoặc custom `ServerRequestObservationConvention`, tên/tag cũng thay.
- Một Spring MVC `@WebMvcTest` slice có thể thiếu Actuator observation infrastructure; vì mục tiêu đo metric HTTP thực, dùng `@SpringBootTest(RANDOM_PORT)`.

## 11. Spring WebFlux: cùng vấn đề nhưng context retrieval khác

Ở WebFlux, HTTP request được xử lý qua `HttpHandler`/reactive pipeline. Exception được controller hoặc `@ExceptionHandler` chuyển thành response có thể không tới lớp observation ở dạng terminal error. Để **chủ động đánh dấu exception đã xử lý**, Spring Framework 6.1 dùng:

```java
import org.springframework.http.server.reactive.observation.ServerRequestObservationContext;
import org.springframework.web.server.ServerWebExchange;

ServerRequestObservationContext.findCurrent(
        exchange.getAttributes())
        .ifPresent(context -> context.setError(exception));
```

Đây là **mảnh code** trong handler có `ServerWebExchange exchange` và `Exception exception`. So với MVC:
- Không có `HttpServletRequest` hay Servlet `ServerHttpObservationFilter`.
- Cùng tên class `ServerRequestObservationContext` nhưng package `...http.server.reactive.observation` khác Servlet.
- `exchange.getAttributes()` chứa context ở lifecycle của HTTP exchange; `findCurrent(...)` trả Optional.
- `setError(ex)` không đổi response status hay terminate reactive pipeline.
- Không chuyển Java `ThreadLocal`/Servlet request attributes sang WebFlux theo trực giác; context propagation có quy tắc khác.

### 11.1. Ví dụ WebFlux độc lập (Java 17+)

Để chạy riêng ví dụ WebFlux, tạo project thứ hai `webflux-http-observation-demo`, không thêm `spring-boot-starter-web`. `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
server.port=8081
spring.application.name=webflux-http-observation-demo
management.endpoints.web.exposure.include=health,metrics
```

`src/main/java/com/example/reactiveobservation/ReactiveObservationApplication.java`:

```java
package com.example.reactiveobservation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.observation.ServerRequestObservationContext;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveObservationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveObservationApplication.class, args);
    }
}

@RestController
class ReactiveObservationController {

    @GetMapping("/reactive/handled")
    Mono<String> handled() {
        return Mono.error(new ReactivePartnerDownException(
                "Partner did not respond"));
    }

    @GetMapping("/reactive/ok")
    Mono<String> ok() {
        return Mono.just("ok");
    }
}

@RestControllerAdvice
class ReactiveObservationAdvice {

    @ExceptionHandler(ReactivePartnerDownException.class)
    ResponseEntity<ProblemDetail> handled(
            ReactivePartnerDownException exception,
            ServerWebExchange exchange) {

        ServerRequestObservationContext.findCurrent(
                        exchange.getAttributes())
                .ifPresent(context -> context.setError(exception));

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "The upstream service is temporarily unavailable");
        problem.setTitle("Partner unavailable");

        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}

class ReactivePartnerDownException extends RuntimeException {
    ReactivePartnerDownException(String message) {
        super(message);
    }
}
```

Chỉ có một top-level `public class` đúng file name; class khác package-private ở cùng package để component scan. Trong `handled()`, Reactor `Mono.error(...)` ném lỗi khi được subscribe. Handler `@ExceptionHandler` nhận Throwable từ reactive pipeline, đánh dấu observation context và trả `ResponseEntity`/`ProblemDetail`.

Chạy project WebFlux thứ hai:

```bash
gradle bootRun
curl -i http://localhost:8081/reactive/handled
curl -i http://localhost:8081/reactive/ok
curl -s http://localhost:8081/actuator/metrics/http.server.requests
```

Dự kiến `/reactive/handled` trả 503, error tag `ReactivePartnerDownException` khi observation được đăng ký và có meter; `/reactive/ok` trả 200 và `error=none`. Dùng Actuator metrics filter tương tự mục 9 với `uri=/reactive/handled`, `error=ReactivePartnerDownException`.

**Lưu ý WebFlux:** không gọi `block()` bên trong reactive controller/filter vì có thể chặn Netty event-loop. Không coi lỗi bị bắt bởi `onErrorResume` rồi return `Mono.just(...)` là lỗi đã tự động được observer nhận biết; nó cũng là một hình thức xử lý trước observation boundary. Nếu nghiệp vụ muốn đánh dấu, bạn cần policy ghi nhận tương ứng **trong HTTP exchange còn active**.

### 11.2. Nếu handler là WebExceptionHandler thay vì @ExceptionHandler

Trong WebFlux, một `WebExceptionHandler` có thể biến error thành status/body. Khi exception bị xử lý thành completion bình thường trước khi quan sát kết thúc, signal error cũng có thể không lan tới observation instrumentation. Có thể truy cập `ServerWebExchange` trong handler và tìm `ServerRequestObservationContext.findCurrent(exchange.getAttributes())` khi còn lifecycle hợp lệ.

**Không sửa mọi WebExceptionHandler thành “mark all errors” không phân biệt.** Các lỗi dự kiến như 404, validation 400/422 và security denials thường cần metrics nghiệp vụ/cơ sở khác. Kiểm tra thứ tự exception handlers, response committed state và policy error status.

## 12. @ExceptionHandler, ProblemDetail, @ResponseStatus và ResponseStatusException

Những cơ chế này liên quan HTTP response, nhưng không nhất thiết tạo observation error:

| Cơ chế | Điều làm được | Exception có nhất thiết còn thoát ra observation? |
|---|---|---|
| `@ExceptionHandler` / `@ControllerAdvice` | Bắt lỗi, map thành status/body | Không, vì đã xử lý |
| `ResponseEntity<ProblemDetail>` | Tạo error response chuẩn có status/detail | Không; có thể không có Throwable |
| `ResponseStatusException` | Diễn đạt HTTP error status bằng exception | Framework có resolver xử lý trước filter |
| `@ResponseStatus` trên exception/handler | Map status theo framework | Có thể được giải quyết trong MVC/WebFlux |
| `ResponseEntity.status(500)` trực tiếp | Trả status 500 | Không có Throwable để auto-record |
| `DefaultErrorAttributes`/`/error` | Mô tả lỗi theo Error MVC/Boot | Không đồng nghĩa observation context biết exception gốc |
| Một exception không xử lý được | Đi lên middleware/container | Có thể được auto-record nếu vượt observation boundary |

**ProblemDetail là mô hình HTTP error body**, không phải một Micrometer Error Event. Một JSON có `"status": 503` không tự động set `context.error`. Tương tự việc log stack trace trong `@ControllerAdvice` không tự thêm error tag.

Trong Spring Boot 3.x, `ErrorAttributes`/`BasicErrorController` xử lý lỗi ở tầng web MVC; metadata lỗi của Boot ở error dispatch **không tự thay thế** Micrometer `ServerRequestObservationContext.setError`. Nếu cần correlation giữa hai, ứng dụng phải thiết kế rõ chứ không giả định filter lấy được exception từ mọi request attribute.

## 13. Nhận biết đúng “đã ghi nhận tự động” hay “đã ghi thủ công”

Đừng chỉ nhìn vào HTTP status hoặc một log rồi kết luận exception được thu tự động. Có ba mức thông tin:

**Mức A — Observation context tự ghi lỗi:** exception thoát ra HTTP observation instrumentation, framework ghi `context.error`. Điều này có thể phụ thuộc Servlet filter order, web container và reactive pipeline. Đường có unhandled exception là ứng viên rõ ràng nhất.

**Mức B — Ứng dụng chủ động ghi trên HTTP observation:** `findObservationContext/findCurrent(...)` rồi `setError(ex)` trong handled-exception path. Mục đích là **bảo toàn nguồn gốc lỗi** dù đã map thành HTTP response.

**Mức C — Ứng dụng ghi custom business observation/metric:** ví dụ `inventory.fallback`, `payment.declined` hoặc `downstream.timeout` khi không muốn gắn lỗi lên request HTTP thành công. Đây là tín hiệu riêng, không cần sử dụng `setError` trên server request span.

Cần ghi rõ trong policy vận hành:
- Những exception nào nên đánh dấu request error?
- 4xx expected cases có tính error không?
- 5xx mapped từ unexpected exception có cần mark không?
- Fallback thành công có được coi là failed HTTP request không?
- Khi thiếu observation context (request bypass/disabled), cần fallback metric/log nào?
- Cách tránh duplicate alerts khi cả status 5xx và error tag cùng báo lỗi?
- Thông tin nào bị coi là sensitive/PII và không được đưa vào tags/logs?

## 14. Một request có thể cần metric business riêng thay vì setError

Ví dụ hệ thống gọi downstream inventory, bị timeout nhưng có cache fallback hợp lệ, cuối cùng trả HTTP 200 với dữ liệu đủ tin cậy. Nếu gắn `context.setError(timeout)` trên HTTP server observation, dashboard có thể hiểu request 200 là lỗi, mặc dù client nhận trải nghiệm thành công. Tùy SLO, điều này có thể là **hợp lý** hoặc **gây nhiễu**.

Một cách khác: ghi business counter riêng:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

// Mảnh code trong service được inject MeterRegistry registry.
Counter fallback = Counter.builder("inventory.fallback")
        .tag("reason", "timeout")
        .register(registry);

fallback.increment();
```

Đây là **mảnh code**, không phải class standalone. Tag `reason` chỉ nên lấy giá trị giới hạn trước (`timeout`, `unavailable`, `validation`), **không** dùng message lỗi chứa URL/user/session ID làm tag. Nếu fallback vẫn khiến response partial/degraded, cân nhắc thêm SLO metric/response header nghiệp vụ có kiểm soát.

Một ví dụ nếu muốn dùng Micrometer Observation custom:

```java
Observation.createNotStarted(
        "inventory.lookup", observationRegistry)
        .lowCardinalityKeyValue("dependency", "inventory")
        .observe(() -> service.lookup());
```

Đây là **mảnh code ý tưởng** với `observationRegistry`/`service` đã inject. Nếu lambda ném exception, Micrometer Observation API có thể ghi error theo instrumentation phù hợp. Nếu lambda đã bắt và xử lý lỗi trước khi thoát, lại quay về vấn đề **handled exception**: muốn ghi lỗi cần policy chủ động.

**Không ép một lỗi nhỏ của dependency vào HTTP server error tag** khi nó đã được fallback thành công mà không ảnh hưởng contract client, trừ khi bạn định nghĩa error như “có failure nội bộ bất kỳ” và dashboard biết phân biệt.

## 15. Khi nào status/outcome đủ, khi nào phải có exception tag?

### 15.1. Status/outcome cho SLO HTTP

Một SLO availability thường lấy tỷ lệ HTTP 5xx (có ngoại lệ theo contract). Với tình huống 500 đã được xử lý, **status=500/outcome=SERVER_ERROR** vẫn có thể giúp SLO phát hiện request lỗi dù `error=none`. Đừng xây alert 5xx chỉ dựa trên `error != none`.

Ví dụ phân loại:
- **Availability error rate:** dựa trên HTTP status/outcome và service contract.
- **Exception class breakdown:** dựa trên `error` tags; có thể thiếu handled exceptions nếu không đánh dấu.
- **Business rejection rate:** đo từ kết quả nghiệp vụ (decline payment, invalid request), không suy từ HTTP 500.
- **Trace exemplars:** phụ thuộc sampling/instrumentation/exporter, không bảo đảm mọi request xuất trace.

### 15.2. Exception tag để chẩn đoán nguyên nhân

Nếu một 503 có thể do `SocketTimeoutException`, `DatabaseException` hoặc `CircuitBreakerOpenException`, error tag sẽ giúp phân nhóm. Tuy nhiên exception class name là **low-cardinality** nếu chỉ một tập hữu hạn; nếu tạo dynamic exception classes/tags từ message, cardinality có thể nổ.

**Không dùng stack trace, exception message, URL chứa token, customer IDs trong low-cardinality tags.** Chúng có thể tiết lộ secrets và tăng số series. Nếu cần nguyên nhân chi tiết, dùng structured logs/traces có redaction và retention policy.

### 15.3. Traces khi được bật

Khi có `micrometer-tracing` bridge và exporter, observation có thể dẫn tới span events/status dựa vào handler của tracing instrumentation. Nhưng:
- Sampling có thể bỏ phần lớn traces.
- Một trace có thể tồn tại mà không có error event được đánh dấu.
- `context.setError(ex)` thêm error vào observation context; cách span ghi exception event/status phụ thuộc tracer/bridge/handler.
- Log `ERROR` không tự tạo span error nếu không có integration/callback.
- Một exception được mark hai lần từ layers khác nhau có thể tạo duplicate events hoặc gán nhầm cause nếu policy không rõ.

**Không cam kết "setError chắc chắn gửi một trace ERROR tới Jaeger"** nếu không kiểm tra tracing stack và sampling.

## 16. HTTP client-side errors có thể khác server-side errors

Một ứng dụng vừa nhận HTTP requests vừa gọi downstream qua `RestClient`/`RestTemplate`/`WebClient`. Có thể xuất hiện:

```text
Browser → Spring Boot A → Spring Boot B
  │             │                │
  │         client observation   │
  │         http.client.requests │
  │             │                │
  │         server observation   │
  │         http.server.requests │
  │                              │
  └──── HTTP 200 or 503 ◄─────────┘
```

Ví dụ service A gọi B, B trả 503; RestClient `retrieve()` ném `HttpServerErrorException`; A có thể catch exception và trả cached value 200. Ở đây:
- **Client-side observation** của A có status 503 từ downstream B, có hoặc không có error tag tùy client instrumentation.
- **Server-side observation** của A có status 200 vì client cuối nhận thành công.
- **Server-side observation** của B có status 503, và error tag tùy B có xử lý exception hay không.
- Một distributed trace có thể có nhiều spans và nhiều nơi ghi error; không ép đồng nhất các tags.

Spring Boot 3.3 có thể instrument các HTTP clients nếu tạo bằng Boot-configured builders; tự `RestClient.create()`/`WebClient.create()` có thể không nhận ObservationRegistry mặc định. Do đó trước khi điều tra "trace đứt", phải xem từng client và việc truyền trace context.

**Điểm trọng tâm:** bài này nói **HTTP server observation** và handled exception; `setError` trên server context **không chữa** việc HTTP client không được instrument, không thay đổi status downstream và không kết nối trace khi thiếu context propagation.

## 17. Async, Reactor Context và lỗi xảy ra sau khi response kết thúc

Một số lỗi không nằm trong phạm vi HTTP request dù request đã kích hoạt công việc:

- Controller trả HTTP 202, sau đó background job thất bại.
- Controller fire-and-forget `CompletableFuture`/`Executor` rồi trả 200.
- Reactive pipeline bị cancel sau khi client ngắt kết nối.
- Servlet async dispatch/error xảy ra sau response commit.
- Một scheduler xử lý event từ queue nhiều phút sau khi API trả HTTP 200.
- Một WebSocket session giữ nhiều messages lâu sau HTTP handshake.

Trong những trường hợp này, **HTTP server observation có thể đã kết thúc** hoặc context không còn hiệu lực. Không dựa vào việc “có request gốc” để gọi `ServerHttpObservationFilter.findObservationContext(request)` từ một background thread sau vài phút. Hãy tạo **observation/trace span riêng cho background work**, truyền context theo cách có chủ đích và dùng correlation IDs an toàn.

Với WebFlux, `ThreadLocal` không tự theo mọi operator. Spring Boot 3.3 hỗ trợ property:

```properties
spring.reactor.context-propagation=auto
```

Thuộc tính này điều khiển automatic context propagation khi đủ dependencies/support, không biến mọi custom publisher thành thread-safe và không tự bảo đảm background worker đã inherit đúng trace. Ưu tiên Reactor Context và kiểm thử trên actual scheduler hops.

**Cancellation ≠ error**: client đóng tab, timeout, network disconnect hoặc stream bị `take(1)` cancel không nhất thiết là một server exception. Chỉ đánh dấu request error khi policy có nguyên nhân đáng ghi nhận, không biến mọi CANCEL signal thành 5xx.

## 18. @ControllerAdvice global: tránh mark vô tội vạ

Bạn có thể nghĩ đến:

```java
// Mảnh code không khuyến nghị làm mặc định:
@ExceptionHandler(Exception.class)
ResponseEntity<ProblemDetail> catchEverything(
        Exception ex, HttpServletRequest request) {

    ServerHttpObservationFilter.findObservationContext(request)
            .ifPresent(context -> context.setError(ex));

    return ResponseEntity.status(500)
            .body(ProblemDetail.forStatus(500));
}
```

Đoạn trên là **mảnh minh họa trong Spring MVC**; nếu đưa vào app ví dụ mục 8 cùng các handlers khác, thứ tự/chi tiết matching exceptions sẽ bị ảnh hưởng. Nó có vài nhược điểm:
1. Tất cả exception đi tới đây bị map thành 500, kể cả lỗi validation/resource 404 đáng ra là 4xx.
2. Error tag bị ghi cho nhiều expected client errors, tăng nhiễu.
3. Che mất chi tiết xử lý chuẩn của `ResponseEntityExceptionHandler`/`ProblemDetail`.
4. Một số errors ở filters/container không đi tới ControllerAdvice nên vẫn không coverage 100%.
5. Nó dễ log/reveal quá nhiều dữ liệu nếu cộng thêm `log.error("{}", ex)` thiếu redaction.

**Policy tốt hơn:** phân loại exception theo semantic, mapping status, mức độ và lựa chọn `setError`. Nếu có base exception advice, tách rule “expected client issues” khỏi “unexpected operational failures”. Đừng làm ControllerAdvice ném lại exception chỉ để instrumentation thấy nó; có thể thay đổi response và error dispatch ngoài ý muốn.

## 19. Customize observation convention: chỉ khi cần và giữ cardinality thấp

Spring Boot 3.3 cho phép:
- MVC: bean kế thừa `org.springframework.http.server.observation.DefaultServerRequestObservationConvention` để bổ sung low/high cardinality key-values, hoặc implement `ServerRequestObservationConvention` nếu muốn thay convention.
- WebFlux: package tương ứng `org.springframework.http.server.reactive.observation.DefaultServerRequestObservationConvention`.
- `ObservationFilter`: post-process observation context và keys theo Micrometer.
- `ObservationPredicate`: loại observations có chủ đích.
- `management.observations.http.server.requests.name`: đổi tên.
- `management.observations.enable.*`: bật/tắt theo prefix.

Tuy nhiên nếu mục tiêu chỉ là **đánh dấu exception đã xử lý**, **không cần thay toàn bộ convention**. Dùng `setError(ex)` như Framework hướng dẫn là rõ ràng hơn và tránh phá các tags chuẩn.

**Ví dụ không nên làm:** lấy `exception.getMessage()` làm low-cardinality tag `error_detail`. Message có thể chứa SQL, path, PII, token và hàng triệu biến thể. Nếu muốn biết lỗi ở bước nào, dùng enum/domain category hữu hạn ở custom metric (ví dụ `category=downstream_timeout`), còn stack trace đặt trong logs/traces đã có redaction.

**Tags mặc định không tự mã hóa đúng ngữ nghĩa nghiệp vụ.** `status=404` có thể là lỗi path hoặc tài nguyên không tồn tại, `error=none` chỉ nói observation chưa được gắn Throwable. Hãy định nghĩa dashboard theo contract chứ không gán phán đoán tuyệt đối cho từng tag.

## 20. Security, logging và dữ liệu nhạy cảm

Khi xử lý lỗi, rất dễ có thói quen đưa toàn bộ exception vào response/log/metric:

```java
// Không khuyến nghị:
log.error("Failed request: {}", request.getRequestURI(), exception);
```

Việc log exception **đôi lúc cần thiết**, nhưng phải kiểm soát URL/query/path và stack trace vì chúng có thể chứa PII, access tokens hoặc nội dung do attacker nhập. Đối với môi trường nhiều tenant, logs cần có tenant/correlation metadata **đã xác minh** và khả năng lọc quyền truy cập.

Gợi ý:
- Client response **không trả stack trace**/SQL/password/token cho người dùng.
- Dùng `ProblemDetail` với title/detail an toàn, mã lỗi ổn định và request/correlation ID không nhạy cảm.
- Metrics tags chỉ chứa route template, method, status, exception **class** hoặc category hữu hạn.
- Traces có thể chứa high-cardinality context nhưng vẫn phải redaction theo retention policy.
- Logging sampling, rate limiting và dedup để không flood khi downstream lỗi hàng nghìn request/giây.
- Actuator/Prometheus endpoints phải được bảo vệ, không dựa vào việc “chỉ dùng nội bộ” khi hạ tầng có thể đổi.
- Tránh metrics tags từ raw path: `/users/123`, `/users/456` phải quy về `/users/{id}` nếu có mapping, không tạo series cho từng user.
- Khi dùng `@ExceptionHandler`, chỉ gọi `setError(ex)` trên **exception thực sự phù hợp** chứ không ghi message nhạy cảm vào context tags.

**Tránh suy từ status code rằng request “an toàn” hay “không an toàn”.** Authentication/authorization filters có thể trả 401/403 trước controller; theo policy security, nên theo dõi audit/access-denied metrics riêng. HTTP server observation vẫn chỉ là một trong các nguồn giám sát.

## 21. Troubleshooting: vì sao error tag không như mong đợi?

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| 500 response nhưng `error=none` | `@ExceptionHandler` đã xử lý trước observation | Xem advice và cân nhắc `setError(ex)` |
| 404 nhưng `error=none` | Business not-found hoặc default handler đã xử lý | Thường hợp lý; theo dõi status/outcome |
| 503 có error tag loại lạ | Exception wrapper được ghi thay cause | Xem stack/handler và chọn exception đại diện có chủ đích |
| Không có `http.server.requests` meter | Thiếu Actuator/registry, observation bị disable, path chưa gọi | Kiểm tra dependencies, registry, `management.observations.enable.*` |
| `/actuator/metrics` trả 404 | Endpoint chưa expose hoặc Actuator chưa có | Bật exposure có chọn lọc, kiểm tra management base path |
| `/actuator/metrics` trả 401/403 | Spring Security/management policy đang chặn | Xác thực đúng, không bỏ security cho production |
| Marked exception không hiện tag | Gọi `setError` sau observation kết thúc hoặc sai context | Gọi trong `@ExceptionHandler` khi exchange còn active, kiểm tra stack |
| Java MVC không tìm `findObservationContext` | Import nhầm WebFlux class/package | Dùng `org.springframework.web.filter.ServerHttpObservationFilter` |
| WebFlux cố inject `HttpServletRequest` | Lẫn Servlet và reactive stack | Dùng `ServerWebExchange` + `ServerRequestObservationContext.findCurrent(...)` |
| Test với `@WebMvcTest` không có meter | Test slice thiếu HTTP server instrumentation | Dùng `@SpringBootTest(RANDOM_PORT)` + Actuator |
| Test nhìn metrics quá sớm | Observation chưa stop hoặc registry export trì hoãn | Chờ bounded theo điều kiện và kiểm tra measurement |
| Metric `exception` không giống bản cũ | Boot 3.x observation rewrite; `exception` deprecated | Dùng `error` ở 6.1 và version-specific semantics |
| HTTP status 200 nhưng span error | Fallback bên trong bị đánh dấu trên server observation | Xem policy và cân nhắc custom dependency metric |
| Log ERROR nhưng trace không error | Log và observation/tracing là kênh độc lập | Kiểm tra bridge/sampling và `setError` |
| Có metric nhưng không có trace | Không cấu hình tracer/exporter hoặc sampling bỏ | Kiểm tra Micrometer Tracing/OTel exporter |
| Prometheus metric không đúng tên | Registry chuyển tên meter/timer thành Prometheus series | Xem `/actuator/prometheus`; Actuator dùng dot name |
| URL cardinality tăng mạnh | Dùng raw path/query/user ID làm tags | Dùng URI template và fixed categories |
| Error ở Tomcat filter/Valve không xuất hiện | Ngoài scope `ServerHttpObservationFilter` | Instrument container/filter phù hợp |
| Async job lỗi sau HTTP 202 nhưng server metric 2xx | Request đã kết thúc; job là tác vụ khác | Instrument background observation riêng |
| Cùng một lỗi được đếm nhiều lần | Đếm server status, client status và custom error counter cùng nhau | Tách tín hiệu theo layer và dedup alert |

## 22. Checklist thiết kế và triển khai

- [ ] Xác nhận version Spring Boot/Framework và tên observation thực tế.
- [ ] Phân biệt `status/outcome` của HTTP với `error/exception` của observation.
- [ ] Xác định các `@ExceptionHandler`/`@ControllerAdvice`/`WebExceptionHandler` bắt Throwable rồi trả response.
- [ ] Phân loại lỗi dự kiến 4xx và lỗi vận hành/bug 5xx theo chính sách rõ.
- [ ] Đối với handled exception cần quan sát, gọi `context.setError(ex)` trên HTTP observation context hiện hành.
- [ ] Với MVC dùng `ServerHttpObservationFilter.findObservationContext(request)`.
- [ ] Với WebFlux dùng `ServerRequestObservationContext.findCurrent(exchange.getAttributes())`.
- [ ] Không ném lại exception chỉ vì thiếu metric tag, làm thay đổi HTTP response ngoài ý muốn.
- [ ] Không dựa vào `error != none` làm chỉ số duy nhất cho HTTP availability SLO.
- [ ] Không biến tất cả 404/validation/403 thành observation error thiếu chọn lọc.
- [ ] Đánh giá fallback 200: dùng custom metric riêng nếu request thành công nhưng dependency gặp sự cố.
- [ ] Actuator/Micrometer registry hoạt động và `http.server.requests` timer được tạo.
- [ ] Kiểm tra cả status 404 + no error, status 500 + no error và status 503 + marked error trong integration tests.
- [ ] Test HTTP thật để đảm bảo observation lifecycle tồn tại, không chỉ gọi thẳng advice method.
- [ ] Tracing bridge/exporter/sampling được cấu hình và kiểm thử riêng nếu muốn span.
- [ ] Bảo vệ metrics endpoints, redaction logs/traces và giữ low-cardinality tags.
- [ ] Đo lỗi background và downstream ở layer riêng; không nhầm với HTTP server request error.
- [ ] Khi nâng Boot/Framework major version, đối chiếu semantic conventions mới và cập nhật dashboard.

## 23. Câu hỏi tự kiểm tra

**1. Vì sao `@ExceptionHandler` trả HTTP 500 nhưng `error=none`?**  
Exception đã được controller advice giải quyết trước khi nó có thể tới lớp HTTP observation instrumentation. Status 500 vẫn được ghi từ response, nhưng context chưa có error.

**2. `ServerHttpObservationFilter.findObservationContext(request).ifPresent(ctx -> ctx.setError(ex))` có tự đổi HTTP 500 thành 503 không?**  
Không. Nó chỉ ghi Throwable trên observation context; status phải được handler/response thiết lập riêng.

**3. 404 có bắt buộc là observation error không?**  
Không. 404 có thể là một client/business error dự kiến. `status=404` và `outcome=CLIENT_ERROR` vẫn cho phép đo, còn `error` có thể là none.

**4. HTTP 500 có luôn là Java exception không?**  
Không. Handler có thể trả `ResponseEntity.status(500)` trực tiếp mà không ném exception.

**5. Trong WebFlux dùng API nào để tìm observation context?**  
`org.springframework.http.server.reactive.observation.ServerRequestObservationContext.findCurrent(exchange.getAttributes())`.

**6. Dùng `Exception.class` catch-all rồi mark mọi Throwable có ổn không?**  
Không phải mặc định tốt. Nó có thể biến validation/not-found thành lỗi vận hành, che handling chuẩn và gây nhiễu; phải phân loại.

**7. Log ERROR đã đủ để metrics error tag xuất hiện chưa?**  
Chưa. Log là một tín hiệu riêng; muốn observation error thì context phải có Throwable theo auto-record hoặc mark có chủ đích.

**8. Có thể có `http.server.requests{status="200",error="SomeException"}` không?**  
Có, nếu ứng dụng đánh dấu lỗi trong request đã fallback và trả 200. Nên quyết định policy sao cho dashboards biết diễn giải.

**9. Nếu HTTP client B trả 503 nhưng service A fallback và trả 200, server observation của A nên là gì?**  
Status của HTTP A vẫn là 200. Lỗi downstream nên được ghi ở client/dependency observation hoặc business fallback metric phù hợp; đừng nhầm status B với status A.

**10. Tại sao không assert error tag của unhandled exception trong một test mặc định đơn giản?**  
Vì Servlet filter scope/error dispatch và wrapper exceptions có thể khiến class được ghi khác. Test có thể assert status và điều kiện instrumentation cụ thể, nhưng không cứng nhắc giả định mọi container ghi cùng class.

**11. Spring Boot Actuator có tự export distributed traces chỉ vì có dependency không?**  
Không. Cần tracer bridge/exporter, sampling và cấu hình phù hợp. Metrics và traces dù dựa trên Observation vẫn có đường xuất khác nhau.

**12. Tại sao không gắn exception message vào metric tags?**  
Vì rò rỉ secrets/PII và tạo cardinality lớn. Dùng exception class/nhóm lỗi hữu hạn, còn chi tiết đặt trong logs/traces đã kiểm soát.

## 24. Tài liệu chính thức để đối chiếu

1. Spring Framework 6.1 — **Observability Support**, HTTP Server Instrumentation (MVC và WebFlux), handled exception + `setError`, low-cardinality keys: https://docs.spring.io/spring-framework/reference/6.1/integration/observability.html
2. Spring Boot 3.3.13 — **Metrics**, HTTP server requests, custom conventions, handled exceptions trong Spring MVC/WebFlux: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
3. Spring Boot 3.3.13 — **Observability**, Micrometer Observation, metrics/traces/logging, context propagation: https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html
4. Spring Framework 6.1 — **MVC Exceptions and HandlerExceptionResolver**: https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-servlet/exceptionhandlers.html
5. Spring Framework 6.1 — **MVC Error Responses, ProblemDetail**: https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-rest-exceptions.html
6. Spring Framework 6.1 — **WebFlux Error Responses, @ExceptionHandler, ProblemDetail**: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/ann-rest-exceptions.html
7. Spring Boot 3.3.13 — **Actuator endpoints and security**: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
8. Micrometer — **Observation Documentation**: https://docs.micrometer.io/micrometer/reference/observation.html
9. OpenTelemetry — **Trace Semantic Conventions, HTTP spans**: https://opentelemetry.io/docs/specs/semconv/http/

**Kết luận:** Một HTTP request có ít nhất **hai tín hiệu độc lập**: response status/outcome và Throwable được ghi trên HTTP observation context. Exception đã được Spring MVC/WebFlux xử lý thường không tự đi tới lớp instrumentation. Khi thật sự cần biểu diễn nguyên nhân đã xử lý, dùng `setError(exception)` trong đúng lifecycle với đúng API Servlet/WebFlux; đồng thời giữ HTTP status chính xác, metrics cardinality thấp, log/traces an toàn và một policy phân loại lỗi nhất quán.