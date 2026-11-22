# Xử lý lỗi và giải phóng tài nguyên khi chuỗi Filter/Interceptor bị ngắt trong Spring Boot

## 1. Bài toán

Một HTTP request trong Spring Boot MVC thường đi qua **Servlet FilterChain → DispatcherServlet → HandlerInterceptor → Controller → xử lý response**. Bất kỳ mắt xích nào cũng có thể dừng luồng thông thường:

- Filter **không gọi** `chain.doFilter(...)` vì đã trả HTTP 401, 403, 429, v.v.
- Filter ném `IOException`, `ServletException` hoặc `RuntimeException`.
- `HandlerInterceptor.preHandle(...)` trả `false` hoặc ném exception.
- Controller/service lỗi; Spring MVC dùng `HandlerExceptionResolver` hoặc `@RestControllerAdvice` để tạo error response.
- Client ngắt kết nối, response đã commit, hoặc request chuyển sang **ASYNC/ERROR dispatch**.

Nếu xử lý lỗi không đúng, ứng dụng có thể rò **MDC/ThreadLocal**, lock, permit, file handle, connection hoặc memory; ghi response hai lần; che mất exception gốc; làm security chain không chạy như kỳ vọng. Không thể sửa mọi tình huống bằng duy nhất `afterCompletion` hoặc duy nhất `try/finally`.

Bài hướng dẫn **Spring Boot 3.5.x, Spring MVC Servlet stack, Java 17+**, với project đầy đủ sử dụng Boot **3.5.16** và bộ kiểm thử qua embedded HTTP server thật. Nội dung khác với Spring WebFlux `WebFilter`/Reactor, vì WebFlux không dùng Servlet `FilterChain` cho reactive request pipeline.

**Mục tiêu:** sau bài này bạn có thể chỉ ra *ai sở hữu tài nguyên*, *callback nào chắc chắn được gọi trong nhánh nào*, *nên trả HTTP error ở tầng nào*, và *làm sao chứng minh cleanup xảy ra cả khi request bị ngắt*.

## 2. Nắm đúng vòng đời: filter và interceptor khác nhau

~~~text
HTTP client
    |
    v
Servlet container
    |
    +-- Filter A: before
    |     |
    |     +-- Filter B: before
    |     |     |
    |     |     +-- DispatcherServlet
    |     |             |
    |     |             +-- Interceptor X: preHandle
    |     |             +-- Interceptor Y: preHandle
    |     |             +-- Controller / exception resolver
    |     |             +-- postHandle (nếu phù hợp)
    |     |             +-- afterCompletion (chỉ interceptor preHandle=true)
    |     |
    |     +-- Filter B: finally
    |
    +-- Filter A: finally
    |
    v
HTTP response
~~~

**Servlet Filter** có `doFilter(request,response,chain)`. Nó không có `preHandle(): boolean`; một filter chủ động dừng request bằng cách **không gọi** `chain.doFilter`. Nếu filter đã ở trong `try`, khối `finally` sẽ thực thi khi rời khỏi khối đó, kể cả `return` sớm hoặc exception.

**Spring MVC HandlerInterceptor** có `preHandle`, `postHandle`, `afterCompletion`:

- `preHandle(...)` trả `true`: chuỗi tiếp tục; interceptor đủ điều kiện nhận `afterCompletion` trong luồng đồng bộ.
- `preHandle(...)` trả `false`: Spring bỏ qua handler và các interceptor phía sau. Chính interceptor vừa trả `false` **không được** gọi `afterCompletion` của nó.
- `preHandle(...)` ném exception **trước khi trả `true`**: không chờ `afterCompletion` của chính interceptor đó.
- Những interceptor **trước đó đã preHandle=true** trong cùng chain có thể vẫn nhận `afterCompletion` khi chain bị chặn hoặc gặp lỗi.
- `postHandle` chỉ chạy trong các đường xử lý phù hợp khi handler đã hoàn tất thành công; không dùng nó làm callback cleanup bắt buộc.
- `afterCompletion(request,response,handler,ex)` có thể nhận `ex == null` khi exception đã được `HandlerExceptionResolver` giải quyết. Không suy từ `ex == null` rằng controller chưa từng lỗi.
- Async MVC có vòng đời khác: dispatch đầu tiên có thể kết thúc mà chưa gọi `postHandle`/`afterCompletion`; xem mục 9.

Tài liệu javadoc `HandlerInterceptor.afterCompletion` ghi rõ chỉ gọi nếu `preHandle` của interceptor đó hoàn tất thành công và trả `true`. Đây là một điều kiện bảo vệ quan trọng cho việc quản lý resource.

## 3. Ma trận tình huống: callback nào dọn được gì?

| Tình huống | Filter `finally` của dispatch ban đầu | Interceptor đang xử lý `afterCompletion` | Ai phải xử lý tài nguyên? |
|---|---|---|---|
| Controller trả 200 đồng bộ | Có, khi đã vào `try` | Có, nếu `preHandle=true` | Dọn thread context trong filter; dọn resource của interceptor trong afterCompletion |
| Filter trả 429 sớm không gọi chain | Có | Không vào MVC interceptor | Filter dọn mọi tài nguyên nó đã tạo |
| Filter ném exception | Có | Thường chưa vào MVC nếu lỗi trước DispatcherServlet | Filter dọn; container/error handling phù hợp xử lý HTTP lỗi |
| `preHandle` trả `false` | Có khi chain quay về | **Không** với chính interceptor trả false | Interceptor phải giải phóng resource trước khi trả false; filter vẫn dọn phần của filter |
| `preHandle` ném lỗi | Có | **Không** với chính interceptor ném trước khi trả true | Interceptor dọn trong `catch/finally` của preHandle |
| Một interceptor sau trả `false` | Có | Có đối với các interceptor trước đã trả true | Mỗi chủ tài nguyên tự dọn |
| Controller ném lỗi và `@ExceptionHandler` giải quyết | Có | Có nếu `preHandle=true` | MVC tạo response, các chủ tài nguyên dọn theo lifecycle |
| Controller ném lỗi không được giải quyết | Có | Có nếu `preHandle=true` trong sync dispatch | Exception có thể tới container; không tự viết thêm response đã commit |
| Async request bắt đầu | Có khi initial dispatch thoát | Chưa gọi `afterCompletion` ở initial dispatch | Dọn ThreadLocal theo **thread/dispatch**, resource sống suốt request phải đợi async completion |
| ERROR redispatch | Có thể có **một filter invocation riêng** nếu mapping khớp | Tùy error handler mapping | Tránh dọn hoặc ghi số liệu hai lần |

Ma trận giả định các callback đã vào phần code tương ứng; nếu exception xảy ra **trước lệnh tạo `try`**, `finally` của đoạn code đó không bảo vệ tài nguyên đã được lấy trước đó. Hãy đặt acquisition và cleanup đúng phạm vi.

## 4. Filter: dọn tài nguyên bằng try/finally đúng cách

### 4.1. Mẫu an toàn cơ bản

~~~java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain) throws ServletException, IOException {

    String previous = MDC.get("requestId");
    String requestId = UUID.randomUUID().toString();

    try {
        MDC.put("requestId", requestId);
        request.setAttribute("requestId", requestId);
        response.setHeader("X-Request-Id", requestId);

        if (isRateLimited(request)) {
            response.sendError(429, "Too many requests");
            return;
        }

        chain.doFilter(request, response);
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

Đây là **trích đoạn method** cho subclass `OncePerRequestFilter`, cần import Servlet/JDK/SLF4J và implementation `isRateLimited`. Project ở mục 8 có file Java hoàn chỉnh với logic tương đương.

Những điểm cần ghi nhớ:

1. `return` trong nhánh rate limiting **vẫn chạy finally**.
2. Nếu `chain.doFilter` ném `IOException`, `ServletException` hoặc unchecked exception, `finally` vẫn chạy trước khi lỗi truyền lên.
3. Khôi phục giá trị MDC trước đó thay vì luôn `clear()` tất cả MDC keys của framework/thư viện khác.
4. `requestId` là dữ liệu **per request**, không đặt vào mutable field của singleton filter.
5. `try/finally` bảo vệ **thread-local MDC** của lượt thực thi hiện tại; nó **không** có nghĩa async response đã kết thúc.
6. Nếu cần tài nguyên tự đóng, đặt acquisition trong `try-with-resources` phù hợp *lifetime*. Đừng đóng response output stream do Servlet container sở hữu chỉ vì filter thoát.

### 4.2. Sai lầm: cleanup chỉ sau chain.doFilter

~~~java
MDC.put("requestId", id);
chain.doFilter(request, response);
MDC.remove("requestId"); // Không chạy nếu downstream ném exception!
~~~

Nếu downstream lỗi, worker thread của Servlet container có thể tiếp tục được tái sử dụng và mang ngữ cảnh request trước. Có thể dẫn đến log correlation sai hoặc rò thông tin chéo giữa requests. Dùng `finally` để tránh.

### 4.3. Sai lầm: return trước vùng try

~~~java
MDC.put("requestId", id);
if (blocked) {
    response.sendError(403);
    return; // Nếu cleanup chỉ nằm ở đoạn sau thì bị bỏ qua.
}
try {
    chain.doFilter(request, response);
} finally {
    MDC.remove("requestId");
}
~~~

Phải đưa nhánh chặn và các thao tác có thể ném lỗi vào **phạm vi try đã bảo vệ**.

### 4.4. Không swallow exception chỉ để giữ response đẹp

Không làm:

~~~java
try {
    chain.doFilter(request, response);
} catch (Exception ex) {
    response.setStatus(200);
}
~~~

Cách này che lỗi server, trả HTTP 200 giả, không ghi đầy đủ failure signal và có thể vô tình ghi tiếp một response đã commit. Để lỗi đi đến đúng cơ chế xử lý, hoặc chuyển đổi có chủ đích thành error response **trước khi response commit**, với status và schema được tài liệu hóa.

**Lưu ý checked exceptions:** `FilterChain.doFilter` khai báo `IOException` và `ServletException`. Trong servlet filter chuẩn, có thể để chúng truyền lên theo method signature. Lỗi chưa xử lý ở bên ngoài `DispatcherServlet` không nhất thiết được `@RestControllerAdvice` xử lý.

### 4.5. Response đã commit: không được ghi lần thứ hai

Trước khi tạo một error body thay thế, kiểm tra `response.isCommitted()`. Nếu server đã flush headers hoặc body, `sendError`, `setStatus`, `resetBuffer` hoặc ghi JSON mới có thể không còn hiệu lực, ném `IllegalStateException` hoặc tạo response hỏng.

Đối với exception khi response đã commit: dọn tài nguyên, log an toàn và để container quản lý kết nối; không cố “sửa status” muộn. Đặc biệt cần thận trọng với streaming/SSE, download lớn và client disconnect.

## 5. Interceptor: false hoặc throw không có afterCompletion của chính nó

### 5.1. Sai lầm phổ biến khi giữ resource

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception {

    Permit permit = acquirePermit();
    request.setAttribute("permit", permit);

    if (!allowed(request)) {
        response.sendError(403);
        return false;
    }
    return true;
}

@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) throws Exception {

    Permit permit = (Permit) request.getAttribute("permit");
    permit.close();
}
~~~

Đây là **pseudocode Java minh họa** có type `Permit`, `acquirePermit`, `allowed` giả định, không thuộc project demo. Lỗi nằm ở nhánh `return false`: Spring không gọi `afterCompletion` của chính interceptor đó, nên permit không được trả. Nếu `sendError` ném exception, resource cũng có thể bị bỏ sót.

### 5.2. Cách viết có cleanup trong preHandle và sau khi handler hoàn tất

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception {

    Permit permit = acquirePermit(); // Type giả định trong pseudocode.
    boolean handedOff = false;

    try {
        if (!allowed(request)) {
            response.sendError(403);
            return false;
        }

        request.setAttribute("my.permit", permit);
        handedOff = true;
        return true;
    } finally {
        if (!handedOff) {
            permit.close(); // Đóng cả false/throw trước khi preHandle=true.
        }
    }
}

@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) throws Exception {

    Permit permit = (Permit) request.getAttribute("my.permit");
    try {
        if (permit != null) {
            permit.close();
        }
    } finally {
        request.removeAttribute("my.permit");
    }
}
~~~

Đây cũng là **pseudocode** yêu cầu một `Permit` `AutoCloseable` và import đầy đủ khi tích hợp. Khi `preHandle` trả true, quyền sở hữu resource chuyển sang `afterCompletion`. Khi false/throw, `finally` của `preHandle` dọn ngay.

Cần xét một ngoại lệ thiết kế: nếu `preHandle` đã trả true nhưng ứng dụng **bắt đầu xử lý async**, `afterCompletion` có thể chưa được gọi ở initial dispatch. Nếu permit không thể chờ đến redispatch hay request kết thúc, hoặc có yêu cầu dọn trên timeout/disconnect, dùng lifecycle async chuyên biệt (mục 9), không cố áp dụng máy móc logic sync.

### 5.3. Thứ tự khi nhiều interceptors

Giả sử A và B đều đăng ký, A ở trước B:

| Kết quả `preHandle(A)` | Kết quả `preHandle(B)` | Controller có chạy? | `afterCompletion` |
|---|---|---|---|
| true | true | Có | B rồi A, khi request đồng bộ kết thúc |
| true | false | Không | A được gọi; B **không** được gọi |
| false | chưa chạy | Không | Không có callback của A |
| true | ném exception | Không | A có thể được gọi; B phải cleanup ngay trong preHandle |
| ném exception | chưa chạy | Không | A phải tự cleanup |

Bảng mô tả đồng bộ Servlet MVC. Không lấy `postHandle` làm công cụ release vì callback đó không được gọi trong nhiều đường lỗi/short-circuit.

### 5.4. Interceptor không phải bộ lọc security hoàn chỉnh

Khi từ chối một request tại interceptor, phải quyết định status (401/403/429...), response body nếu có, và trả `false`. Nhưng Spring MVC path matching của interceptor không bao phủ mọi Servlet path, forward hoặc error dispatch như Filter. Với authentication/authorization, ưu tiên **Spring Security FilterChain** được cấu hình phù hợp thay vì thay thế bằng MVC interceptor thủ công.

## 6. Exception handling: lỗi ở tầng nào thì xử lý ở tầng đó

### 6.1. Lỗi trong controller/service và HandlerExceptionResolver

Nếu controller ném exception, `DispatcherServlet` có thể chọn `HandlerExceptionResolver`, chẳng hạn một method `@ExceptionHandler` từ `@RestControllerAdvice`. API có thể trả `ResponseEntity`, `ProblemDetail` hoặc status phù hợp. Khi lỗi được giải quyết, filter bao ngoài vẫn đi qua `finally` theo đường return bình thường.

Ví dụ:

~~~java
@RestControllerAdvice
class ErrorAdvice {
    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<Map<String, String>> handle(IllegalStateException ex) {
        return ResponseEntity.status(503)
                .body(Map.of("code", "SERVICE_UNAVAILABLE"));
    }
}
~~~

Đây là đoạn class minh họa; project hoàn chỉnh ở mục 8 có imports đầy đủ. Không đưa `ex.getMessage()` vào public body khi nội dung có thể chứa secrets hoặc internal details.

**Quan trọng:** `afterCompletion(..., ex)` có thể nhận **null** nếu Spring MVC exception resolver đã xử lý lỗi. Hãy dùng error status/log/metrics có chủ đích; đừng xây logic cleanup chỉ khi `ex != null`.

### 6.2. Lỗi phát sinh từ Filter trước DispatcherServlet

Nếu Filter ném exception **trước** khi gọi `chain.doFilter`, `@RestControllerAdvice` không phải nơi mặc định xử lý nó, vì exception xảy ra bên ngoài MVC exception resolver. Servlet container có thể xử lý/dispatch tới `/error` tùy cấu hình.

Muốn Filter chủ động chặn request, có thể gọi `response.sendError(429)` **khi chưa commit**, sau đó return. Đừng dùng `throw new IllegalStateException` chỉ để trả một HTTP 429 thường lệ.

Khi cần custom error schema thống nhất cho cả MVC và filter, thiết kế một error writer chuyên dùng và xét `isCommitted`, content type, encoding, dispatcher semantics, hoặc dùng error controller theo cách Boot hỗ trợ. Không cố gọi trực tiếp `@ExceptionHandler` của MVC từ Filter.

### 6.3. Lỗi trong HandlerInterceptor

`preHandle` được gọi trong quá trình `DispatcherServlet` thực thi handler chain. Exception ném ở đây **có thể** được Spring MVC exception resolver xử lý, nhưng callback `afterCompletion` của interceptor chưa preHandle=true vẫn **không** trở thành cleanup guarantee. Hai việc “tạo HTTP error response” và “đóng resource đã cấp phát” là **hai trách nhiệm độc lập**.

### 6.4. Exception và thứ tự dọn

Nếu một filter B ở trong filter A cùng dùng `try/finally`, khi có lỗi:

~~~text
A.before
  B.before
    Controller / DispatcherServlet throws
  B.finally
A.finally
container/error handling tiếp tục
~~~

Thực tế nếu DispatcherServlet resolve exception thành response, chuỗi có thể return bình thường; dù vậy A và B vẫn dọn trong `finally`. Nếu `finally` tự ném exception, nó có thể che mất lỗi gốc. Vì vậy cleanup nên an toàn, idempotent khi cần, và log lỗi đóng resource một cách có chủ đích. Với Java `try-with-resources`, lỗi khi close thường được lưu dưới dạng suppressed exception, giúp giữ lỗi chính.

## 7. Tài nguyên có những vòng đời khác nhau

| Tài nguyên | Vòng đời hợp lý | Cách dọn |
|---|---|---|
| `MDC`, ThreadLocal tenant/context | **Một thread hoặc một dispatch** | `finally` trong Filter/Interceptor; khôi phục giá trị trước đó |
| File/InputStream mở trong method đồng bộ | Scope sử dụng stream | `try-with-resources`, không đóng Servlet request stream do container quản lý |
| Lock/semaphore permit | Đến khi công việc được bảo vệ hoàn tất | `try/finally` hoặc callback terminal được quyết định rõ |
| JDBC Connection tự mở | Một transaction/operation | `try-with-resources` nếu ứng dụng trực tiếp sở hữu |
| Connection/EntityManager do Spring Transaction quản lý | Scope Spring transaction | Để Spring quản lý; không tự đóng trong Filter |
| Servlet response writer/output stream | Do container sở hữu | Không tự đóng tùy tiện, tránh double write |
| Async DeferredResult/SSE resource | **Đến khi request hoàn thành, timeout, error/disconnect** | `onCompletion`, `onError`, `AsyncListener` và one-time cleanup |
| Metrics timer/correlation ID | Tùy định nghĩa: dispatch hay whole request | Chọn một điểm terminal, không đếm đôi REQUEST+ERROR |

**Quy tắc ownership:** chỉ đóng tài nguyên bạn đã tạo hoặc đã được chuyển quyền sở hữu rõ ràng. Không đóng `DataSource` hoặc bean singleton dùng chung trong mỗi request. Không khởi tạo/dừng executor hoặc connection pool cho mỗi HTTP request.

### Mẫu Java sync try-with-resources

~~~java
try (InputStream input = Files.newInputStream(path)) {
    return process(input);
}
~~~

Đây là đoạn method minh họa, với `path` là một `Path` được kiểm soát và `process` là phương thức sẵn có; Java đóng input khi rời khối. Với tài nguyên thực sự có vòng đời dài xuyên async, đặt `try-with-resources` bên ngoài phần khởi tạo async **sẽ đóng quá sớm**; phải chuyển cleanup sang callback cuối vòng đời.

## 8. Demo hoàn chỉnh: Filter finally + Interceptor preHandle + xử lý lỗi MVC

Ứng dụng Maven sử dụng:

- `RequestScopeFilter extends OncePerRequestFilter` với `MDC`, request ID, `try/finally`, và bộ đếm `activeScopes` để kiểm thử cleanup.
- `GuardInterceptor` trả `false` với `/api/interceptor-deny`, ném exception trước khi trả true với `/api/interceptor-throw`, và theo dõi callback `afterCompletion` cho request đồng bộ.
- `@RestControllerAdvice` xử lý `IllegalStateException` của MVC thành 503 với một error code an toàn.
- `FilterRegistrationBean` map Filter theo Servlet `/api/*`, `DispatcherType.REQUEST`; interceptor map theo Spring MVC `/api/**`.
- Tests qua `@SpringBootTest(RANDOM_PORT)` và **JDK 17 HttpClient**, xác minh status và active scope counter sau mỗi request.

Các counters chỉ là **dụng cụ dạy học**. Trong production nên dùng metrics/tracing có giới hạn và không giữ toàn bộ request events trong singleton list.

### 8.1. Cấu trúc project

~~~text
chain-cleanup-demo/
  pom.xml
  src/main/java/com/example/cleanup/
    ChainCleanupApplication.java
    RequestScopeFilter.java
    GuardInterceptor.java
    WebPipelineConfiguration.java
    DemoController.java
    ErrorAdvice.java
  src/test/java/com/example/cleanup/
    ChainCleanupIntegrationTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>chain-cleanup-demo</artifactId>
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

### 8.3. ChainCleanupApplication.java

~~~java
package com.example.cleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainCleanupApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainCleanupApplication.class, args);
    }
}
~~~

### 8.4. RequestScopeFilter.java

~~~java
package com.example.cleanup;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestScopeFilter extends OncePerRequestFilter {
    private final AtomicInteger activeScopes = new AtomicInteger();

    public int activeScopeCount() {
        return activeScopes.get();
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String id = UUID.randomUUID().toString();
        String previousMdcValue = MDC.get("demo.requestId");

        activeScopes.incrementAndGet();
        try {
            MDC.put("demo.requestId", id);
            request.setAttribute("demo.requestId", id);
            response.setHeader("X-Request-Id", id);

            String path = request.getServletPath();

            if ("/api/filter-deny".equals(path)) {
                response.sendError(429, "Rate limited");
                return;
            }

            if ("/api/filter-exception".equals(path)) {
                throw new IllegalStateException("Filter failure");
            }

            chain.doFilter(request, response);
        } finally {
            try {
                if (previousMdcValue == null) {
                    MDC.remove("demo.requestId");
                } else {
                    MDC.put("demo.requestId", previousMdcValue);
                }
            } finally {
                activeScopes.decrementAndGet();
            }
        }
    }
}
~~~

Cách xử lý của Filter:

1. `activeScopes` tăng **trước vùng try** nhưng ngay sau đó là `try`; mọi câu lệnh có thể return/throw theo nghiệp vụ ở **trong** try, và nhánh finally giảm counter.
2. `/api/filter-deny` trả HTTP **429** và không gọi chain, nhưng finally vẫn dọn MDC/counter.
3. `/api/filter-exception` ném `IllegalStateException` **trước DispatcherServlet**, nên advice MVC không phải cơ chế mặc định nhận lỗi đó.
4. Các path khác gọi downstream; lỗi được giải quyết hoặc không được giải quyết vẫn quay qua finally của filter.
5. `MDC` được khôi phục thay vì xóa toàn bộ MDC map; tránh làm mất các keys khác do logging/security/observability framework tạo.
6. Với async, count ở đây là **active filter dispatches**, không phải toàn bộ request đang chờ response; project demo chỉ dùng request đồng bộ.

Không dùng `activeScopes` làm rate limiter production. Rate limiting đúng cần counters/permits có phân định chủ thể, xử lý nhiều instances, timeout, fairness và logic release theo request-lifecycle.

### 8.5. GuardInterceptor.java

~~~java
package com.example.cleanup;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public final class GuardInterceptor implements HandlerInterceptor {
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger completed = new AtomicInteger();

    public int activeCount() {
        return active.get();
    }

    public int completedCount() {
        return completed.get();
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {

        String path = request.getServletPath();

        if ("/api/interceptor-deny".equals(path)) {
            response.sendError(403, "Denied");
            return false; // Chính interceptor này không có afterCompletion.
        }

        if ("/api/interceptor-throw".equals(path)) {
            throw new IllegalStateException("preHandle failed");
        }

        active.incrementAndGet();
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        try {
            completed.incrementAndGet();
        } finally {
            active.decrementAndGet();
        }
    }
}
~~~

Vì `GuardInterceptor` chỉ tăng counter **sau khi đã qua mọi nhánh chặn hoặc throw**, nó không phải release resource cho `preHandle=false`. Trong ứng dụng có permit/lock thật, phải dùng mẫu cleanup `try/finally` tại `preHandle` ở mục 5; không lấy ví dụ counter đơn giản này làm mẫu sở hữu resource phức tạp.

`afterCompletion` có thể nhận `ex == null` sau khi Spring xử lý exception thành response; code không dựa vào tham số đó để quyết định cleanup.

### 8.6. WebPipelineConfiguration.java

~~~java
package com.example.cleanup;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebPipelineConfiguration implements WebMvcConfigurer {
    private final GuardInterceptor guard;

    public WebPipelineConfiguration(GuardInterceptor guard) {
        this.guard = guard;
    }

    @Bean
    FilterRegistrationBean<RequestScopeFilter> requestScopeRegistration() {
        FilterRegistrationBean<RequestScopeFilter> registration =
                new FilterRegistrationBean<>(new RequestScopeFilter());

        registration.setName("requestScopeFilter");
        registration.addUrlPatterns("/api/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(20);
        return registration;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(guard).addPathPatterns("/api/**");
    }
}
~~~

**Hai hệ thống path matching khác nhau:**

- `addUrlPatterns("/api/*")` là Servlet prefix pattern, map Filter trên URL `/api/...`.
- `addPathPatterns("/api/**")` là Spring MVC interceptor path pattern.
- `DispatcherType.REQUEST` chỉ cho Filter chạy trên initial request dispatch trong demo; ERROR dispatch đến `/error` không làm `activeScopes` bị cộng đôi.
- Filter được tạo trực tiếp trong `FilterRegistrationBean` và **không** khai báo `@Component`, tránh một filter bean tự auto-register thêm mapping rộng `/*`.

### 8.7. DemoController.java

~~~java
package com.example.cleanup;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/api/ok")
    public String ok() {
        return "ok";
    }

    @GetMapping("/api/handled-failure")
    public String failed() {
        throw new IllegalStateException("Simulated service failure");
    }

    @GetMapping("/api/interceptor-deny")
    public String denied() {
        return "unreachable";
    }

    @GetMapping("/api/interceptor-throw")
    public String thrownByInterceptor() {
        return "unreachable";
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "public";
    }
}
~~~

Các mapping `/api/filter-deny` và `/api/filter-exception` **không cần controller**, vì Filter xử lý/throw trước khi DispatcherServlet. Với MVC `/api/interceptor-deny` và `/api/interceptor-throw`, controller mapping vẫn có mặt để Spring chọn handler và gọi `preHandle` của interceptor.

### 8.8. ErrorAdvice.java

~~~java
package com.example.cleanup;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ErrorAdvice {
    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> serviceFailure(
            IllegalStateException exception) {

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("code", "SERVICE_UNAVAILABLE"));
    }
}
~~~

Trong demo, exception của controller và interceptor bên trong `DispatcherServlet` được Spring MVC xử lý thành **503**. Exception do Filter tự throw bên ngoài MVC có thể đi tới Servlet container và thông thường thành **500**, không dùng handler ở đây.

Project không có Spring Security; status 403 trong interceptor chỉ minh họa cơ chế short-circuit, không phải policy authentication/authorization có thể dùng trong production.

### 8.9. Chạy bằng Maven và thử bằng curl

Cần JDK 17+ và Maven. Trong thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Sau khi server lắng nghe cổng 8080, chạy:

~~~bash
curl -i http://localhost:8080/api/ok
curl -i http://localhost:8080/api/interceptor-deny
curl -i http://localhost:8080/api/filter-deny
curl -i http://localhost:8080/api/handled-failure
curl -i http://localhost:8080/api/filter-exception
curl -i http://localhost:8080/public/ping
~~~

Kết quả logic dự kiến:

| URL | HTTP | Ý nghĩa |
|---|---|---|
| `/api/ok` | 200 | Filter finally + interceptor afterCompletion |
| `/api/interceptor-deny` | 403 | `preHandle=false`, không chạy controller |
| `/api/filter-deny` | 429 | Filter `return` sớm nhưng vẫn finally |
| `/api/handled-failure` | 503 | Controller lỗi, advice xử lý |
| `/api/interceptor-throw` | 503 | preHandle ném trước true; advice xử lý nhưng interceptor không afterCompletion |
| `/api/filter-exception` | 500 | Exception xảy ra trước DispatcherServlet; không mặc định qua MVC advice |
| `/public/ping` | 200 | Ngoài scope filter và interceptor |

Các body lỗi 403/429/500 có thể thay đổi theo Servlet container và Spring Boot error configuration, nên không coi JSON mặc định là contract cố định. Chỉ response 503 do advice tạo được kỳ vọng có field `"code":"SERVICE_UNAVAILABLE"`. Header `X-Request-Id` có trên request thuộc filter scope nếu response/dispatch giữ lại header; với một số error dispatch, container có thể ảnh hưởng header cuối cùng, nên test cleanup không nên dựa độc quyền vào header error.

## 9. HTTP integration tests chứng minh cleanup khi bị ngắt

Không dùng riêng `MockMvc` để xác nhận Servlet registration behavior: test infrastructure có thể khác embedded container mapping/dispatcher lifecycle. Bộ test dưới đây gọi HTTP qua TCP thực, kiểm tra **status**, các counters và callback.

File `src/test/java/com/example/cleanup/ChainCleanupIntegrationTest.java`:

~~~java
package com.example.cleanup;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.servlet.FilterRegistrationBean;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ChainCleanupIntegrationTest {
    @LocalServerPort
    int port;

    @Autowired
    FilterRegistrationBean<RequestScopeFilter> registration;

    @Autowired
    GuardInterceptor guard;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        return client.send(request,
                HttpResponse.BodyHandlers.ofString());
    }

    private void assertNoActiveScopes() {
        assertEquals(0, registration.getFilter().activeScopeCount());
        assertEquals(0, guard.activeCount());
    }

    @Test
    void synchronousSuccessCleansFilterAndInterceptor() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/ok");

        assertEquals(200, result.statusCode());
        assertEquals("ok", result.body());
        assertTrue(result.headers().firstValue("X-Request-Id").isPresent());
        assertEquals(before + 1, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void interceptorFalseDoesNotCallOwnAfterCompletion() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/interceptor-deny");

        assertEquals(403, result.statusCode());
        assertEquals(before, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void filterShortCircuitStillRunsFinally() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/filter-deny");

        assertEquals(429, result.statusCode());
        assertEquals(before, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void mvcHandledExceptionStillCleansBothLayers() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/handled-failure");

        assertEquals(503, result.statusCode());
        assertTrue(result.body().contains("SERVICE_UNAVAILABLE"));
        assertEquals(before + 1, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void preHandleThrowDoesNotGetItsOwnAfterCompletion() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/interceptor-throw");

        assertEquals(503, result.statusCode());
        assertEquals(before, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void filterExceptionStillRunsFinally() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/filter-exception");

        assertEquals(500, result.statusCode());
        assertEquals(before, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void outsideApiScopeIsUnaffected() throws Exception {
        HttpResponse<String> result = get("/public/ping");

        assertEquals(200, result.statusCode());
        assertEquals("public", result.body());
        assertFalse(result.headers().firstValue("X-Request-Id").isPresent());
        assertNoActiveScopes();
    }
}
~~~

**Tương thích Java 17:** `java.net.http.HttpClient` trong JDK 17 chưa triển khai `AutoCloseable`, vì vậy ví dụ dùng `HttpClient.newHttpClient()` thông thường, **không** đặt client trong try-with-resources. Các test mặc định chạy tuần tự; nếu cấu hình JUnit chạy song song, không nên so sánh một global active counter bằng 0 ngay khi một request khác còn xử lý, cần test isolation.

Chạy:

~~~bash
mvn test
~~~

Bộ test trên **không** chạy sẵn trong tài liệu này; output được mô tả theo mã Java và Spring MVC/Servlet behavior. Trong CI của dự án, chạy thực tế để xác minh startup, dependency versions và container behavior. Nếu `ERROR` dispatch xảy ra ở URL khác, bộ test vẫn chỉ đòi hỏi status và resource counters, không pin error JSON/HTML mặc định.

## 10. Async MVC: finally của initial dispatch không đồng nghĩa request đã hoàn tất

Spring MVC `Callable`, `DeferredResult`, `WebAsyncTask`, `ResponseBodyEmitter`, `SseEmitter` và các reactive return types có thể bắt đầu Servlet async processing:

~~~text
REQUEST dispatch:
  Filter.before
    Interceptor.preHandle
      Controller trả DeferredResult
      request.startAsync()
    AsyncHandlerInterceptor.afterConcurrentHandlingStarted
  Filter.finally              <-- thread ban đầu thoát, response còn mở

Worker/event thread:
  setResult(...) hoặc setErrorResult(...)

ASYNC dispatch:
  (Filters map ASYNC và có policy tương ứng)
    DispatcherServlet tiếp tục render response
    Interceptor callbacks theo async lifecycle
  completion callback          <-- request thật sự hoàn tất
~~~

Trong initial dispatch, `postHandle` và `afterCompletion` **không bắt buộc được gọi**; Spring Framework cung cấp `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` để cleanup thread-bound context của initial thread khi async bắt đầu. Callback này khác với `afterCompletion` của dispatch hoàn tất.

### 10.1. ThreadLocal/MDC: dọn trên từng thread

Nếu một filter thiết lập MDC trên container thread, `finally` nên dọn MDC của **thread đó** ngay khi filter dispatch kết thúc, dù async response còn mở. Thread có thể được tái sử dụng cho request khác. Đừng giữ MDC trong ThreadLocal của initial thread đến khi `DeferredResult.onCompletion` chạy trên thread khác; cleanup của thread khác không xóa được ThreadLocal của thread ban đầu.

Khi muốn MDC có trong async worker hoặc async redispatch, cần **propagate context có chủ đích** và dọn ở từng thread. Với `OncePerRequestFilter`, xem `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()` và Servlet registration `DispatcherType.ASYNC`/`ERROR`. Chỉ bật `asyncSupported=true` không có nghĩa Filter tự được chạy ở ASYNC dispatch.

### 10.2. Tài nguyên sống suốt request: dọn khi onCompletion

Ví dụ tài nguyên riêng cho một async operation, pseudocode:

~~~java
DeferredResult<String> result = new DeferredResult<>(5000L);
AutoCloseable resource = acquireResource(); // Ví dụ, cần method thật.
AtomicBoolean closed = new AtomicBoolean();

Runnable cleanup = () -> {
    if (closed.compareAndSet(false, true)) {
        try {
            resource.close();
        } catch (Exception ex) {
            // Log an toàn, không ghi vào HTTP response đã commit.
        }
    }
};

result.onCompletion(cleanup);
result.onTimeout(() -> result.setErrorResult(
        new IllegalStateException("Timed out")));
result.onError(error -> {
    // Ghi nhận/cancel background work; không lộ secrets.
});
return result;
~~~

Đây là **đoạn minh họa**, không phải method chạy độc lập; cần import `DeferredResult`, `AtomicBoolean` và định nghĩa `acquireResource`. `onCompletion` là callback terminal có thể được kích hoạt bởi kết thúc bình thường, timeout, network error. `AtomicBoolean` giúp cleanup idempotent khi còn những đường dọn khác. Nếu async setup thất bại **trước khi đăng ký callback**, phải cleanup ở ngay nhánh setup thất bại.

Khi dùng raw Servlet API, `AsyncListener.onComplete/onError/onTimeout/onStartAsync` có thể được dùng, nhưng listener registration/lifecycle phải đúng. Với Spring MVC, thường ưu tiên `DeferredResult` callbacks hoặc `CallableProcessingInterceptor`/`DeferredResultProcessingInterceptor` thay vì can thiệp bừa vào `AsyncContext`.

### 10.3. Client disconnect và streaming

Với `ResponseBodyEmitter` hoặc `SseEmitter`, lỗi IO khi client đóng kết nối không có nghĩa code có thể ghi thêm JSON lỗi. Spring MVC/container có cơ chế phát thông báo async error và hoàn tất request. Tránh gọi `emitter.complete()`/ghi thêm dữ liệu sau write failure khi framework đã xử lý, và dọn business resources qua callback phù hợp.

Một response đã commit không thể chuyển từ HTTP 200 đang stream sang 500 JSON chuẩn chỉ bằng cách bắt exception. Monitor disconnect, cancel background work và close resources theo idempotent lifecycle.

## 11. Phân biệt các loại cleanup và chính sách xử lý lỗi

### 11.1. Thread-bound cleanup

Các ví dụ gồm `MDC`, tự quản lý `ThreadLocal`, dữ liệu tenant context, tracing context tự thiết lập. Nếu đã set trong filter, **dọn trong finally cùng thread**. Đừng tự xóa SecurityContext, RequestContextHolder hoặc các ThreadLocal do framework quản lý nếu không sở hữu chúng.

### 11.2. Resource cleanup theo request

Connection, semaphore permit hoặc lock thuộc request cần đóng **chính xác khi công việc thực tế đã hoàn tất**. Với sync method, `try-with-resources` phù hợp. Với async, cần callback terminal. Nếu resource được trao cho tầng sau, phải xác định rõ nơi chuyển ownership.

### 11.3. Error response

- **Filter reject có chủ đích:** status cụ thể như 429/403/401 khi chưa commit; không gọi chain.
- **Interceptor reject có chủ đích:** set status/sendError rồi trả false, cleanup resource trước return.
- **Controller/service lỗi:** `@ExceptionHandler`, `ResponseEntityExceptionHandler`, `ProblemDetail`, status theo contract.
- **Filter exception chưa xử lý:** để container/Servlet error pipeline quyết định hoặc có error writer riêng; `@RestControllerAdvice` không bao hết.
- **Response đã commit:** ưu tiên dọn/log; không cố ghi lại body/status.
- **Client disconnect:** coi là tín hiệu hủy/lỗi vận chuyển, không mặc định là bug nghiệp vụ hay HTTP 500 công khai.

### 11.4. Logging/observability

Nên ghi exception class, status, request/correlation ID, thời lượng và stage xảy ra lỗi. Không dump `Authorization`, cookies, raw body, query chứa token hoặc exception cause chứa PII. Nếu request trải qua REQUEST và ERROR/ASYNC dispatch, hãy quyết định metrics theo **logical HTTP request** hay theo dispatch, tránh cộng đôi.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| MDC của user trước xuất hiện ở request sau | Không dọn trong finally hoặc cleanup chỉ sau chain | Restore/remove trong finally cùng thread |
| Filter chặn request nhưng active counter không giảm | `return` đặt ngoài try | Đưa nhánh short-circuit vào phạm vi try/finally |
| Interceptor permit bị leak khi trả false | Chỉ release trong afterCompletion | Release ngay trong preHandle false path |
| Interceptor ném lỗi và không cleanup | preHandle chưa trả true | Catch/finally trong preHandle trước khi throw |
| Controller đã trả 503 nhưng afterCompletion ex null | Exception đã được MVC resolver xử lý | Không dùng ex-null làm điều kiện duy nhất |
| 500 do filter không vào RestControllerAdvice | Lỗi xảy ra trước DispatcherServlet | Xử lý tại filter/container/error pipeline |
| Lỗi xảy ra khi response đã stream một phần | Response committed | Không sendError/ghi JSON lần hai |
| Dùng postHandle để giải phóng resource | postHandle không luôn chạy khi lỗi/short-circuit | finally/afterCompletion tùy owner |
| Async response timeout nhưng permit vẫn giữ | Chỉ dọn trong initial dispatch hoặc thiếu terminal callback | DeferredResult.onCompletion/AsyncListener và idempotent release |
| MDC còn trên async worker | Không propagate/cleanup thread context | Set/restore per worker/dispatch |
| Async metrics tăng hai lần | Đếm cả REQUEST và ASYNC/ERROR như 2 requests | Quyết định một terminal point cho logical request |
| Filter xuất hiện hai lần | Auto-register Filter bean cùng Security chain | Loại registration thừa hoặc disable container registration |
| Catch Exception rồi trả 200 | Swallow error | Giữ status đúng và propagate unexpected failures |
| Client disconnect tạo lỗi ghi body thứ hai | Catch IOException rồi cố write lại | Log an toàn và cleanup, không double-write |
| Thủ công close Spring-managed JDBC/EntityManager | Sai ownership | Để transaction manager quản lý |
| Cleanup callback tự ném lỗi và che lỗi gốc | Cleanup không robust | Bảo vệ close và log lỗi phụ, dùng try-with-resources khi hợp lý |
| Tests chỉ kiểm tra 200, không test fail paths | Leak xảy ra ở nhánh hiếm | Test 403/429/500/503, preHandle false/throw, async timeout |

## 13. Checklist triển khai production

1. **Phân loại tầng:** lỗi phát sinh trước hay sau DispatcherServlet? Filter, Interceptor, Controller, container hay async callback?
2. **Chọn owner resource:** ai tạo, ai giữ, ai chuyển ownership và ai close?
3. **Đặt cleanup đúng phạm vi:** ThreadLocal trong dispatch finally; request-scoped permit trong sync afterCompletion hoặc async terminal callback; tự mở stream/connection bằng try-with-resources.
4. **Không phụ thuộc afterCompletion khi preHandle=false/throw.** Dọn ngay trong preHandle.
5. **Không phụ thuộc postHandle cho exception cleanup.**
6. **Giữ exception gốc:** không swallow, không ghi 200 giả, tránh cleanup exception che root cause.
7. **Kiểm tra response.isCommitted() trước khi cố tạo error response** và không double write.
8. **Phân biệt intentional rejection với programming failure**, trả status đúng semantics.
9. **Kiểm soát dispatcher types** và `OncePerRequestFilter` async/error policies, tránh double registration.
10. **Không lấy dữ liệu nhạy cảm đưa vào log/correlation/header**; giữ requestId an toàn.
11. **Kiểm thử trên embedded server thật** cho FilterRegistrationBean URL/order/short-circuit, bổ sung MVC MockMvc tests khi cần.
12. **Viết async lifecycle tests** gồm timeout/disconnect nếu application dùng DeferredResult/SSE/streaming.
13. **Cân nhắc HTTP connection pool/threads:** cleanup sai khiến pool cạn và request treo; nên theo dõi metrics và alerts.
14. **Rà soát bản Spring Boot/Framework:** Servlet vs WebFlux, API packages, starter và error/async behavior theo phiên bản.
15. **Kiểm tra cả error dispatch trên deploy thực tế**, nhất là khi qua reverse proxy hoặc chạy WAR ngoài embedded container.

**Kết luận:** một chuỗi HTTP có thể dừng ở nhiều tầng. Với **Filter**, cleanup của mỗi lượt dispatch nên đặt trong `try/finally` bao cả nhánh return sớm. Với **HandlerInterceptor**, `afterCompletion` chỉ đáng tin khi chính `preHandle` đã trả `true` trong luồng đồng bộ; mọi resource cấp phát trước khi false/throw phải được release ở chính preHandle. Với **async**, tách dọn thread context khỏi kết thúc vòng đời request. Lỗi phải được biến thành response tại đúng tầng và không bao giờ che exception hoặc ghi thêm lên response đã commit.

## Tài liệu chính thức

- Spring Framework 6.2 — HandlerInterceptor lifecycle / afterCompletion condition: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html
- Spring Framework 6.2 — Handler Interception: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
- Spring Framework 6.2 — Asynchronous Requests, Callable/DeferredResult/AsyncHandlerInterceptor: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework 6.2 — OncePerRequestFilter Javadoc, async/error dispatch: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — MVC @ExceptionHandler semantics: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — MVC Exceptions / HandlerExceptionResolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework — RFC 9457 Error Responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Boot 3.5 — Servlet Web Applications, FilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Embedded Servlet Container/dispatcherTypes: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 API — FilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
