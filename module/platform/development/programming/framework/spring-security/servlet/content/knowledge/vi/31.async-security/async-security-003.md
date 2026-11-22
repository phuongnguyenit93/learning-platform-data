# DeferredResult, CompletableFuture và công việc do ứng dụng tự điều phối

## 1. Bức tranh tổng thể trong Spring Security Servlet

Với ứng dụng Spring MVC chạy trên **Servlet stack**, mỗi HTTP request thông thường đi qua Servlet filter chain, Spring Security, `DispatcherServlet`, controller và quay về response trên một thread xử lý request. Khi thao tác bên ngoài mất thời gian (gọi dịch vụ khác, tính toán báo cáo, đợi sự kiện), giữ một servlet thread chờ toàn bộ quá trình sẽ làm giảm khả năng phục vụ request khác.

**Servlet asynchronous processing** cho phép trả thread tiếp nhận request về pool trong lúc kết quả còn đang được chuẩn bị, sau đó hoàn tất response bằng một lần **async dispatch**. Spring MVC hỗ trợ nhiều kiểu return value, trong đó có `DeferredResult<T>` và `CompletableFuture<T>`.

Điều quan trọng cần phân biệt:

1. **Request bất đồng bộ**: HTTP connection vẫn chờ một kết quả; servlet thread ban đầu được nhả ra, nhưng request chưa hoàn tất.
2. **Công việc do ứng dụng điều phối**: ứng dụng tự chọn executor, tạo/chạy task, xử lý timeout, lỗi, hủy, theo dõi tài nguyên và giới hạn tải.
3. **Non-blocking I/O thực sự**: không đồng nghĩa với `DeferredResult` hay `CompletableFuture`. Nếu task dùng JDBC hoặc `Thread.sleep`, worker thread của ứng dụng **vẫn bị block**.
4. **Bảo mật bất đồng bộ**: `SecurityContextHolder` thường gắn với thread. Chuyển sang worker thread không bảo đảm `Authentication`/MDC/request attributes tự đi theo.

Bài này tập trung vào cách phối hợp Spring MVC async và Spring Security trong ứng dụng **Servlet**, không chuyển sang WebFlux hoặc Reactor.

## 2. Vòng đời HTTP request khi dùng async

Một luồng đồng bộ:

```text
Client
  -> Tomcat servlet thread
      -> SecurityFilterChain
      -> DispatcherServlet
      -> Controller gọi I/O chậm và chờ
      -> Controller trả kết quả
      -> ghi HTTP response
  -> thread trở lại pool
```

Một luồng bất đồng bộ dùng `DeferredResult`:

```text
Client -> Tomcat servlet thread #1
            -> SecurityFilterChain
            -> DispatcherServlet / Controller
            -> tạo DeferredResult, đăng ký callback
            -> submit công việc đến executor ứng dụng
            -> return DeferredResult
            -> Servlet async bắt đầu; thread #1 được nhả
                                      |
                                      v
                           Worker thread riêng
                           -> thực hiện công việc
                           -> deferred.setResult(...)
                                      |
                                      v
                     Servlet container async dispatch
                           -> MVC xử lý kết quả
                           -> HTTP response
                           -> hoàn tất async request
```

Thread ở nhánh worker **không phải** servlet request thread ban đầu. `DeferredResult#setResult` chỉ công bố kết quả cho Spring MVC; không nên tự dùng `HttpServletResponse#getWriter()` từ worker để cạnh tranh với cơ chế xử lý response của Spring MVC.

Sau khi controller return, client thường vẫn giữ HTTP connection mở. Do đó request-bound async không phải hệ thống hàng đợi công việc nền bền vững; connection, async context, timeout và bộ nhớ server vẫn cần được quản lý.

## 3. `DeferredResult<T>`: ứng dụng tự quyết định thời điểm hoàn thành

`DeferredResult<T>` là một đối tượng **promise-like** dành cho Spring MVC. Controller tạo nó và trả ngay; một thread hoặc sự kiện khác về sau gọi:

```java
DeferredResult<String> result = new DeferredResult<>(2_000L);

result.onTimeout(() ->
        result.setErrorResult("Operation exceeded its deadline"));

result.onError(error ->
        result.setErrorResult("Operation could not be completed"));

// Khi một worker hoặc callback đã có dữ liệu:
result.setResult("ready");
```

Đây là **đoạn minh họa**, không phải method HTTP hoàn chỉnh; timeout ở constructor tính bằng **mili-giây**. Với API thật nên trả HTTP status/body có contract rõ, không chỉ một chuỗi lỗi.

Những method quan trọng:

| API | Ý nghĩa | Chú ý |
| --- | --- | --- |
| `new DeferredResult<>(timeoutMs)` | Tạo kết quả chờ, có timeout tùy chọn | Không có nghĩa worker sẽ tự bị hủy khi hết hạn |
| `setResult(value)` | Công bố kết quả bình thường | Trả `boolean`; có thể là `false` nếu đã hoàn tất |
| `setErrorResult(valueOrError)` | Công bố lỗi/giá trị lỗi | Nếu truyền exception, MVC đi qua xử lý exception |
| `onTimeout(Runnable)` | Callback khi async request vượt deadline | Có thể set một kết quả lỗi phù hợp |
| `onError(Consumer<Throwable>)` | Callback khi async request gặp lỗi | Phân biệt lỗi transport với lỗi logic của worker |
| `onCompletion(Runnable)` | Callback khi xử lý async đã kết thúc | Hữu ích để cleanup/metrics; không phải dấu hiệu task bị cancel |

**Chỉ một kết quả đầu tiên thắng**: nếu worker và callback timeout cùng gọi `setResult`/`setErrorResult`, chỉ một nhánh giành được completion. Luôn thiết kế theo race này, tránh ghi response hoặc cập nhật nghiệp vụ hai lần khi kết quả đến muộn.

Ví dụ các nguồn kết quả phù hợp với `DeferredResult`: phản hồi từ message broker, callback từ hệ thống ngoài, một sự kiện dài hạn (*long polling*) hoặc tác vụ chạy trên executor. Không nên tự tạo thread mới cho mỗi request.

## 4. `CompletableFuture<T>`: điều phối phép tính và chuỗi xử lý

Java 8+ có `CompletableFuture`, dùng để biểu diễn một phép tính hoàn thành trong tương lai. Với Spring MVC Servlet, trả `CompletableFuture<ResponseEntity<...>>` từ controller được Spring MVC thích nghi vào cơ chế async response.

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> "ready",
                reportExecutor);
```

**Lưu ý:**

- Truyền executor cụ thể là quan trọng. Nếu không truyền executor cho `supplyAsync`, Java thường dùng **`ForkJoinPool.commonPool()`**. Common pool là tài nguyên dùng chung, không phù hợp làm mặc định cho mọi I/O chậm và công việc có tính bảo mật/đa tenant.
- `supplyAsync` chỉ chạy supplier ở một executor, **không làm một hàm blocking trở thành non-blocking**.
- Các stage như `thenApply`, `thenCompose`, `handle`, `exceptionally` có quy tắc chạy khác nhau. Bản không có hậu tố `Async` có thể chạy trên thread hoàn thành stage trước; bản `Async` thường sử dụng executor chỉ định hoặc executor mặc định nếu thiếu.
- Exception thường được bọc trong `CompletionException` khi đọc/ghép future. Không hiển thị exception nội bộ, stack trace hoặc bí mật cho client.
- `orTimeout(...)` hoàn thành future ở trạng thái lỗi khi đến deadline; nó **không chắc dừng được** tác vụ I/O đã chạy. `cancel(true)` trên `CompletableFuture` cũng không có nghĩa mọi tác vụ đã giao executor đều sẽ bị interrupt.

Ví dụ xử lý kết quả:

```java
CompletableFuture<String> normalized =
        CompletableFuture.supplyAsync(() -> "report-ready", reportExecutor)
                .thenApply(String::toUpperCase)
                .exceptionally(error -> "UNAVAILABLE");
```

Đây là **đoạn minh họa** giả định `reportExecutor` đã được định nghĩa; không có HTTP server. `thenApply` không tự chuyển về servlet thread.

## 5. Khi nào chọn `DeferredResult`, `CompletableFuture` hay `Callable`?

| Return type / cơ chế | Ai kiểm soát việc hoàn thành? | Khi phù hợp |
| --- | --- | --- |
| `DeferredResult<T>` | Ứng dụng/callback chủ động gọi `setResult` | Long polling, callback, event-driven completion, cần tách rõ nơi nhận và nơi hoàn tất |
| `CompletableFuture<T>` | Một pipeline Java future hoàn thành | Chạy phép tính hoặc kết hợp kết quả của các dịch vụ khác, xử lý exception theo stage |
| `Callable<T>` | Spring MVC gửi callable tới AsyncTaskExecutor cấu hình cho MVC | Tác vụ có một giá trị trả về và không cần tự quản lý DeferredResult |
| `@Async` ở service | Spring proxy thực thi method trên executor | Tách service task khỏi caller; **không tự thiết lập HTTP response timeout/async contract** |
| Job queue + `202 Accepted` | Worker/queue độc lập khỏi HTTP request | Tác vụ dài, cần retry bền vững, client polling theo job ID |

`Callable` thường dễ hơn khi chỉ cần một computation. `DeferredResult` hợp khi **thời điểm hoàn tất đến từ sự kiện ngoài** hoặc ứng dụng tự định nghĩa. `CompletableFuture` hợp cho các pipeline có dependency và xử lý lỗi theo stage. Dù chọn kiểu nào, executor/timeout/backpressure cần chủ đích.

Không dùng `DeferredResult` làm nơi giữ cả triệu request đợi lâu khi không có giới hạn; mỗi request vẫn tiêu thụ tài nguyên của HTTP server.

## 6. Chương trình Spring Boot 3.3.x / Java 17+ có thể chạy

Ví dụ thực hành cung cấp hai endpoint tương đương:

- `GET /api/reports/deferred/{id}` trả `DeferredResult<ResponseEntity<...>>`.
- `GET /api/reports/future/{id}` trả `CompletableFuture<ResponseEntity<...>>`.

Cả hai yêu cầu **HTTP Basic chỉ cho mục đích demo local**. Ví dụ dùng tên user đã xác thực được **chụp trên request thread** trước khi giao task cho executor. Worker không tự đọc `SecurityContextHolder` để tránh phụ thuộc vào việc truyền context ngầm.

### 6.1. Cấu trúc thư mục

```text
servlet-async-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/async/
    │   │   ├── AsyncDemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── WorkerConfig.java
    │   │   └── ReportController.java
    │   └── resources/application.yml
    └── test/java/demo/async/ReportAsyncTest.java
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` sử dụng **Spring MVC Servlet**, không phải WebFlux. `spring-security-test` hỗ trợ kiểm thử có authentication.

Tạo `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 5s
```

Ứng dụng chỉ bind loopback cho demo. `spring.mvc.async.request-timeout` thiết lập giới hạn chung cho MVC async processing trong bối cảnh phù hợp; giới hạn riêng trên `DeferredResult` hoặc `CompletableFuture#orTimeout` có thể đến sớm hơn. Không coi timeout HTTP là cơ chế tự động kết thúc worker.

Tạo `src/main/java/demo/async/AsyncDemoApplication.java`:

```java
package demo.async;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
```

### 6.2. Cấu hình Spring Security cho API

Tạo `src/main/java/demo/async/SecurityConfig.java`:

```java
package demo.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/reports/**").hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Không dùng `{noop}` hoặc mật khẩu trong source ở production.** Đây chỉ là credential test cho loopback, không phải hướng dẫn triển khai login thật. API production thường nhận bearer token/OIDC, dùng TLS và kiểm tra scope/quyền nghiệp vụ. Vì endpoint demo chỉ thực hiện GET, cấu hình này không cần hủy CSRF một cách tùy tiện.

`hasRole("READER")` yêu cầu authority `ROLE_READER`; chỉ request có Basic credential hợp lệ và role phù hợp mới vào controller. Spring Security thực hiện authorization ở request boundary **trước** khi controller bắt đầu tác vụ worker.

### 6.3. Executor ứng dụng có giới hạn rõ ràng

Tạo `src/main/java/demo/async/WorkerConfig.java`:

```java
package demo.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerConfig {

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("report-worker-");
        return pool;
    }
}
```

Spring quản lý vòng đời/khởi tạo Bean `ThreadPoolTaskExecutor`. Queue không vô hạn: khi hai core threads và queue đã sử dụng, pool có thể tăng đến bốn threads; nếu tất cả đều bận và queue đầy, việc submit có thể bị từ chối. Đây là **backpressure**, không nên đổi sang một queue vô hạn để giấu quá tải.

Giá trị core/max/queue chỉ mang tính minh họa. Chọn kích thước theo CPU, mức chặn I/O, connection pool của downstream, SLO, memory và tải đo được. Không tự lấy `maxPoolSize=1000` vì nghĩ nhiều thread đồng nghĩa nhiều throughput.

### 6.4. Controller cho hai kiểu bất đồng bộ

Tạo `src/main/java/demo/async/ReportController.java`:

```java
package demo.async;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
public class ReportController {

    private final Executor executor;

    public ReportController(@Qualifier("reportExecutor") Executor executor) {
        this.executor = executor;
    }

    @GetMapping("/api/reports/deferred/{id}")
    public DeferredResult<ResponseEntity<Map<String, String>>> deferred(
            @PathVariable String id, Principal principal) {

        // Chụp thông tin tối thiểu khi request còn ở security thread.
        String requestedBy = principal.getName();
        DeferredResult<ResponseEntity<Map<String, String>>> result =
                new DeferredResult<>(1_500L);

        result.onTimeout(() -> result.setErrorResult(unavailable()));
        result.onError(error -> result.setErrorResult(unavailable()));

        try {
            executor.execute(() -> {
                try {
                    result.setResult(buildReport(id, requestedBy));
                } catch (RuntimeException error) {
                    result.setErrorResult(unavailable());
                }
            });
        } catch (RejectedExecutionException rejected) {
            result.setErrorResult(unavailable());
        }

        return result;
    }

    @GetMapping("/api/reports/future/{id}")
    public CompletableFuture<ResponseEntity<Map<String, String>>> future(
            @PathVariable String id, Principal principal) {

        String requestedBy = principal.getName();
        try {
            return CompletableFuture
                    .<ResponseEntity<Map<String, String>>>supplyAsync(
                            () -> buildReport(id, requestedBy), executor)
                    .orTimeout(1_500L, TimeUnit.MILLISECONDS)
                    .exceptionally(error -> unavailable());
        } catch (RejectedExecutionException rejected) {
            return CompletableFuture.completedFuture(unavailable());
        }
    }

    private static ResponseEntity<Map<String, String>> buildReport(
            String id, String requestedBy) {
        // Mô phỏng một đoạn công việc blocking ngắn.
        try {
            TimeUnit.MILLISECONDS.sleep(120);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Report computation interrupted",
                    interrupted);
        }

        return ResponseEntity.ok(Map.of(
                "id", id,
                "requestedBy", requestedBy,
                "status", "ready"));
    }

    private static ResponseEntity<Map<String, String>> unavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", "report unavailable"));
    }
}
```

Điểm cần hiểu ở code:

- `principal.getName()` được đọc **trên servlet request thread** sau khi Spring Security xác thực. Worker chỉ nhận string `requestedBy`; nó không sử dụng `SecurityContextHolder` ngầm.
- Mỗi request tạo một `DeferredResult` riêng; một worker hoàn thành nó bằng `setResult`.
- `CompletableFuture.supplyAsync(..., executor)` dùng **executor có giới hạn**, không chiếm common pool mặc định.
- `orTimeout(1_500L, ...)` tác động đến trạng thái future, **không tự dừng `sleep` hoặc request HTTP bên ngoài**.
- `onTimeout`, `onError`, `exceptionally` và rejection branch trả body lỗi nhất quán với status `503` trong demo. Production cần mapping lỗi phù hợp (`429`/`503`/`504` tùy nguồn và contract), retry policy và correlation ID.
- `TimeUnit.MILLISECONDS.sleep(120)` mô phỏng **blocking** work. Không phải bằng chứng rằng toàn bộ pipeline non-blocking.
- Nếu timeout và task completion đua nhau, chỉ kết quả đầu có tác dụng; một `setResult` muộn có thể trả `false` và không làm thay đổi HTTP response.
- App không để lộ stack trace ra response. Nên ghi lỗi trong log an toàn, có giới hạn thông tin nhạy cảm, theo dõi saturation và timeout.

Ví dụ này cố ý là **request-bound**. Với thao tác lâu phút/giờ hoặc cần retry qua restart, không nên để một HTTP request mở và chỉ trả `DeferredResult`.

## 7. Chạy thử và quan sát HTTP response

Khởi động bằng Gradle wrapper của project:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Không có credential:

```bash
curl -i http://127.0.0.1:8080/api/reports/deferred/R1
```

Spring Security sẽ từ chối trước khi controller chạy; với HTTP Basic demo, thông thường status là **401 Unauthorized**.

Có credential local cho mục đích học tập:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/api/reports/deferred/R1
```

Khi request thành công, body JSON tương đương:

```json
{
  "id": "R1",
  "requestedBy": "alice",
  "status": "ready"
}
```

Thử endpoint future:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/api/reports/future/R2
```

Body JSON tương đương:

```json
{
  "id": "R2",
  "requestedBy": "alice",
  "status": "ready"
}
```

Thứ tự các property JSON không được bảo đảm vì Java `Map.of(...)` không có contract thứ tự. Giá trị request ID do bạn truyền trong URL. Không in Basic password hoặc bearer token vào log production; hai lệnh `curl -u` trên **HTTP loopback chỉ để demo**. Với truy cập mạng thật bắt buộc dùng HTTPS và cơ chế credential phù hợp.

Không thể dựa vào client response để kết luận servlet thread đã được nhả: cần xem metrics/thread traces, async request lifecycle và cấu hình executor.

## 8. Kiểm thử Spring Security + MockMvc async dispatch

Với Spring MVC async, bài test không nên dừng ở việc controller trả `DeferredResult`: cần xác minh **giai đoạn async dispatch** sau khi kết quả worker đã có.

Tạo `src/test/java/demo/async/ReportAsyncTest.java`:

```java
package demo.async;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAsyncTest {

    @Autowired
    MockMvc mvc;

    @Test
    void unauthenticatedRequestIsRejectedBeforeAsyncWork()
            throws Exception {
        mvc.perform(get("/api/reports/deferred/R1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void deferredResultCompletesWithCapturedPrincipal()
            throws Exception {
        MvcResult pending = mvc.perform(
                        get("/api/reports/deferred/R1")
                                .with(httpBasic("alice", "demo-only")))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("R1"))
                .andExpect(jsonPath("$.requestedBy").value("alice"));
    }

    @Test
    void completableFutureCompletesWithCapturedPrincipal()
            throws Exception {
        MvcResult pending = mvc.perform(
                        get("/api/reports/future/R2")
                                .with(httpBasic("alice", "demo-only")))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("R2"))
                .andExpect(jsonPath("$.status").value("ready"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Test này gồm ba điều:

1. Request không có Basic credential không được đi qua authorization boundary.
2. MVC đã bắt đầu xử lý bất đồng bộ (`asyncStarted`).
3. Kết quả được hoàn tất trong bước `asyncDispatch`, với principal đã chụp đúng.

MockMvc không thay thế stress test thật với Tomcat và downstream I/O; nó không chứng minh ứng dụng xử lý đúng client disconnect, tốc độ mạng, queue saturation hoặc race timeout. Nên thêm test với executor stub chủ động hoàn thành chậm/reject để kiểm tra `503`, và test concurrency có giới hạn ở môi trường staging.

## 9. Vấn đề Spring Security: `SecurityContextHolder` theo thread

Theo cấu hình mặc định, `SecurityContextHolder` thường dùng `ThreadLocal` để lưu `SecurityContext`. Điều đó có nghĩa:

```java
// Trên servlet thread:
String user = SecurityContextHolder.getContext()
        .getAuthentication().getName();
```

không đảm bảo tương đương với:

```java
// Trên thread mà ứng dụng tự submit:
executor.execute(() -> {
    Authentication a =
            SecurityContextHolder.getContext().getAuthentication();
    // a có thể null; không được giả định còn user của request.
});
```

Hai đoạn trên chỉ minh họa API và cần import tương ứng; worker lambda không phải một request handler tự động mang theo context. Việc trả `DeferredResult` hoặc `CompletableFuture` **không tự động truyền `SecurityContext`** vào mọi thread do ứng dụng tự quản lý.

Nếu một worker dùng security context bị rò từ task trước, nguy cơ còn nghiêm trọng hơn: request của user B có thể sử dụng quyền user A. Tuyệt đối không đặt `SecurityContext` của request lên một worker thread mà không đảm bảo khôi phục/xóa theo `finally`.

### Phương án khuyến nghị khi worker chỉ cần user ID

Đọc danh tính và những dữ kiện bất biến tối thiểu **khi request còn đang được Spring Security kiểm soát**:

```java
@GetMapping("/api/example")
public DeferredResult<String> example(Principal principal) {
    String requestedBy = principal.getName();
    DeferredResult<String> output = new DeferredResult<>(2_000L);
    executor.execute(() -> output.setResult("requester=" + requestedBy));
    return output;
}
```

Đoạn này chỉ minh họa: phải đặt trong controller có `executor` đã cấu hình và xử lý timeout/rejection trong sản phẩm thật. Đừng chuyển nguyên `HttpServletRequest`, `HttpSession` hoặc toàn bộ đối tượng authentication mutable sang task nếu không thật sự cần.

Dữ liệu đã chụp có thể **bị cũ** nếu quyền bị thu hồi trong lúc job chạy rất lâu. Với thao tác nhạy cảm như chuyển tiền hoặc xuất dữ liệu nhiều tenant, service cần tái xác minh quyền/ownership ở thời điểm thực hiện thay đổi, không chỉ dựa vào quyền đã chụp lúc nhận HTTP request.

## 10. Khi worker thực sự cần `SecurityContext`

Spring Security cung cấp các wrapper executor như:

- `DelegatingSecurityContextExecutor`
- `DelegatingSecurityContextAsyncTaskExecutor`
- Các wrapper tương tự cho `ExecutorService`, `Runnable`, `Callable`.

Với `AsyncTaskExecutor` trong ứng dụng Spring Boot:

```java
@Bean("securityAwareReportExecutor")
AsyncTaskExecutor securityAwareReportExecutor(
        @Qualifier("reportExecutor")
        ThreadPoolTaskExecutor delegate) {
    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
```

Đây là **đoạn method trong `@Configuration`**, cần thêm imports:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
```

Decorator có thể chụp `SecurityContext` của caller khi task được submit, thiết lập nó trong lúc worker chạy và khôi phục/clear sau đó. Dùng wrapper đúng cách, **không** tự tạo một `ThreadLocal` global để chứa user. Cũng không dùng một `SecurityContext` cố định của admin cho mọi task nếu quyền phải theo từng request.

Lưu ý đây **không phải** cơ chế authorization độc lập. Khi muốn dùng `SecurityContextHolder` trong worker:

1. Controller phải được bảo vệ bởi `SecurityFilterChain` trước khi submit.
2. Task được submit trong đúng execution context khi wrapper chụp authentication.
3. Quyền có thể thay đổi sau khi task bắt đầu; business service vẫn kiểm tra quyền ở đúng thời điểm.
4. Executor và context propagation phải có scope rõ, không để credentials/token bị log hoặc chuyển sang công việc không đáng tin.
5. Nếu task cần chạy rất lâu hoặc sống qua process restart, **không nên** mang `SecurityContext` của request làm nguồn quyền lâu dài.

Spring Security có tích hợp riêng cho Spring MVC async **`Callable`** (ví dụ `WebAsyncManagerIntegrationFilter` giúp context khi xử lý Callable ở executor của MVC), nhưng cơ chế này **không có nghĩa** mọi `DeferredResult` completion callback, arbitrary worker thread hay `CompletableFuture.supplyAsync` đều được truyền context tự động.

## 11. Timeout của request và timeout của task là hai chuyện khác

Có nhiều loại deadline:

| Deadline | Quản lý bởi | Điều xảy ra khi hết hạn |
| --- | --- | --- |
| Async request timeout ở Servlet/MVC | Container/Spring MVC hoặc `DeferredResult(timeout)` | HTTP request có thể hoàn tất ở trạng thái lỗi/timeout |
| `CompletableFuture.orTimeout(...)` | Trạng thái future | Future hoàn thành exceptionally, **tác vụ gốc có thể vẫn chạy** |
| HTTP client read/connect timeout | HTTP client gọi downstream | Một I/O cụ thể có thể dừng/báo lỗi |
| Database statement/query timeout | DB driver hoặc database | Một truy vấn có thể bị hủy/báo lỗi theo cơ chế driver |
| Business deadline | Quy trình nghiệp vụ | Quyết định có cho phép hoàn tất tác vụ sau hạn hay phải rollback/hủy |

Trong code ví dụ, HTTP/deferred timeout là 1,5 giây và MVC default là 5 giây. Request có thể trả lỗi vì deadline 1,5 giây, nhưng worker bị kẹt I/O vẫn có thể chiếm một slot của executor.

Với tác vụ blocking thật, cần **cấu hình timeout ở downstream client**, giới hạn queue, cân nhắc cancellation khả thi và làm nghiệp vụ idempotent. Đừng coi `setErrorResult(503)` là dấu hiệu backend đã dừng mọi side effect.

Ví dụ kiểm tra kết quả muộn:

```java
boolean accepted = deferredResult.setResult(value);
if (!accepted) {
    // Request đã hoàn thành bằng nhánh khác: không cố ghi response lần nữa.
}
```

Đoạn này giả định có `deferredResult` và `value` trong scope. Nếu job là thao tác cập nhật dữ liệu, việc response hết hạn **không tự đảo ngược commit** đã xảy ra trong database.

## 12. Lỗi, saturation và backpressure

Một lỗi production phổ biến là tạo executor có queue vô hạn. Khi downstream chậm, request HTTP tới liên tục, queue tăng nhanh và chiếm RAM dù servlet thread ban đầu đã được nhả.

Ví dụ executor demo có `core=2`, `max=4`, `queueCapacity=8`. Khi queue đầy và bốn workers bận, task mới có thể bị `RejectedExecutionException`/`TaskRejectedException`; controller nên trả **503 hoặc trạng thái backpressure được thiết kế** thay vì mở vô hạn thêm thread.

Theo dõi các metric thực:

- số task active, queue depth và queue age;
- số rejection mỗi phút, timeout request và timeout downstream;
- latency p50/p95/p99 ở endpoint và từng dependency;
- số request async đang mở, Tomcat worker utilization và DB connection pool;
- số task hoàn thành **sau khi HTTP response đã timeout**.

Một `CompletableFuture` pipeline có nhiều stage `thenApplyAsync` nhưng không chỉ định executor có thể chuyển việc sang common pool dù stage đầu dùng pool riêng. Hãy truyền executor ở mọi stage bất đồng bộ khi cần chính sách tài nguyên nhất quán.

**Không nên lấy request/user input làm tham số tạo thread pool mới.** Dùng các executor được quản lý, có metrics và giới hạn ở mức service. Nếu một job có thể tốn cả phút, chuyển sang kiến trúc job queue thay vì giữ hàng nghìn async contexts.

## 13. `@Async`, `@Transactional` và trạng thái gắn với thread

`@Async` là một công cụ của Spring để thực thi method thông qua proxy/executor được cấu hình. Nó không phải `DeferredResult`; controller có thể kết hợp nhưng vẫn phải tuân thủ contract HTTP.

Đối với ứng dụng dùng `@Transactional`:

```java
@Transactional
public Report loadReport(String id) {
    return reportRepository.findById(id).orElseThrow();
}
```

Đây là **method minh họa**, giả định có `Report`, `reportRepository` và transaction management. Transaction thông thường gắn với thread; khi request thread submit task, transaction hiện tại **không tự truyền sang worker**. Worker gọi service/proxy có `@Transactional` đúng cách để mở transaction mới khi cần.

Không giữ JPA entity managed từ request thread rồi truy cập lazy relationship trên worker sau khi transaction đã đóng. Có thể gặp `LazyInitializationException` hoặc race dữ liệu. Hãy truyền ID/dữ liệu bất biến, mở transaction trong service của worker và tạo DTO đã materialize.

Với `@Async`, lưu ý **self-invocation**: gọi một method `@Async` từ method khác trong **cùng instance** thường bỏ qua Spring proxy, khiến method chạy đồng bộ. Khi cần task được điều phối rõ, cấu hình executor và gọi qua bean/proxy đúng cách.

Một tác vụ nền dài hạn cũng không nên giữ transaction mở qua một cuộc gọi HTTP chậm; chỉ bao transaction quanh đơn vị đọc/ghi cần thiết.

## 14. MDC, tracing và request-scoped data

Ngoài `SecurityContext`, nhiều ứng dụng dùng MDC (`traceId`, `correlationId`), locale, tenant context hoặc request attributes qua `ThreadLocal`. Chúng **không tự truyền an toàn** sang thread pool chỉ vì controller trả `CompletableFuture`.

Cách đơn giản là truyền các giá trị tối thiểu đã chuẩn hóa trong một context object bất biến, ví dụ:

```java
public record WorkContext(
        String principalId,
        String tenantId,
        String correlationId) {}
```

Đây là **một Java record độc lập** có thể lưu trong file `WorkContext.java` ở package của ứng dụng. Chỉ đưa dữ liệu cần thiết, không chứa raw access token, cookie hoặc toàn bộ HTTP headers.

Nếu cần MDC/tracing tự động, dùng task decorator hoặc giải pháp context propagation phù hợp với Spring/observability stack; phải dọn `ThreadLocal` trong `finally`. Với tracing, nên dựa trên thư viện context propagation được hỗ trợ, tránh tự nhân bản trace baggage chứa thông tin nhạy cảm.

Không truy cập `RequestContextHolder.currentRequestAttributes()` trong worker mà mặc định request attributes còn tồn tại. Servlet request có thể đã timeout/complete, và việc đọc stream/body/session trên worker sau completion không an toàn.

## 15. Async dispatch và filter chain của Servlet

Khi MVC bắt đầu async, một lần dispatch sau đó thường hoàn thành xử lý response. Các filter Servlet có cấu hình **dispatcher types**, có thể chạy ở `REQUEST`, `ASYNC`, `ERROR` khác nhau.

Một số lưu ý:

- `OncePerRequestFilter` và filter Spring Security có logic riêng về async dispatch. **Không mặc định** một filter sẽ chạy đúng một hay đúng hai lần trong mọi container/configuration.
- Một security rule bảo vệ controller không được bỏ qua chỉ vì return type là `DeferredResult`.
- Async redispatch không có nghĩa được phép tái sử dụng `Authentication` của một request khác.
- Đừng tự gọi `SecurityContextHolder.clearContext()` ở servlet request thread để “dọn” context của worker; Spring Security và executor wrapper có lifecycle riêng. Nếu bạn tự set context trên worker, **worker phải tự restore/clear trong finally**.
- Test `401` cho unauthenticated request ở giai đoạn đầu, sau đó test `asyncDispatch` cho request có quyền. Với nhiều filter chain/dispatcher mappings, test ở mức Tomcat thật khi thay đổi filter registration.

Những thư viện Servlet cũ không hỗ trợ async hoặc filter registration thiếu `asyncSupported` có thể làm `Async support must be enabled` xuất hiện. Spring Boot mặc định cấu hình nhiều thành phần cần thiết, nhưng custom Servlet filters vẫn phải khai báo async support đúng khi muốn tham gia đường đi này.

## 16. Dùng `DeferredResult` để chờ sự kiện bên ngoài

Một tình huống khác với `supplyAsync` là đợi sự kiện từ message broker hoặc notification:

```java
// Ví dụ kiến trúc, không phải một controller hoàn chỉnh:
DeferredResult<String> waiting = new DeferredResult<>(5_000L);
pendingRequests.put(correlationId, waiting);
waiting.onCompletion(() -> pendingRequests.remove(correlationId));
return waiting;
```

Khi consumer nhận một sự kiện có `correlationId` hợp lệ:

```java
DeferredResult<String> waiting =
        pendingRequests.remove(event.correlationId());

if (waiting != null) {
    waiting.setResult(event.payload());
}
```

Các đoạn này minh họa: giả định có `pendingRequests`, `correlationId`, `event` với API tương ứng. Trong production, **đừng dùng correlation ID không đoán được làm cơ chế authorization duy nhất**. Phải đảm bảo sự kiện thuộc đúng principal/tenant, giới hạn số pending requests, có cleanup on timeout/error, không để leak memory, và biết sự kiện có thể đến trước/lại/sau khi request đã đóng.

Nếu ứng dụng chạy nhiều replicas, map in-memory ở node A không tự được thấy bởi consumer node B. Khi long polling thực sự cần scale, phải thiết kế routing, event store/broker hoặc shared coordination phù hợp. Có thể trả dữ liệu từ DB theo cursor nếu bài toán phù hợp thay vì tạo hàng loạt pending futures.

## 17. Khi nào nên trả `202 Accepted` thay vì giữ HTTP connection?

Dù async Servlet nhả request thread, **connection còn đang chờ**. Với thao tác dài, có thể bị cắt bởi timeout của browser, load balancer, ingress hoặc API gateway trước khi ứng dụng có kết quả.

Đối với job chạy nhiều phút, dễ retry, cần chống mất dữ liệu khi instance restart:

```text
POST /api/report-jobs
    |
    v
Kiểm tra Authentication + Authorization
    |
    v
Ghi job record và enqueue message bền vững
    |
    v
202 Accepted
Location: /api/report-jobs/{jobId}
    |
    v
Worker độc lập chạy job, ghi trạng thái
    |
    v
GET /api/report-jobs/{jobId}
    -> QUEUED / RUNNING / SUCCEEDED / FAILED
```

Trong mô hình này, user/caller phải được xác thực và được quyền **tạo job**, rồi được phép **xem kết quả job đó**. Không để user A đoán job ID của user B rồi tải report khác tenant. Dùng idempotency key và transaction/outbox khi cần nhất quán giữa DB và queue.

`DeferredResult` phù hợp request chờ ngắn, có deadline rõ và tài nguyên đã giới hạn. Job queue phù hợp tác vụ cần độ bền, điều phối độc lập và khả năng khôi phục sau lỗi.

## 18. Các lỗi phổ biến và cách xác minh

| Biểu hiện | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Servlet thread vẫn bận lâu | Controller block trước khi trả `DeferredResult` | Đưa phần chậm vào executor hoặc callback, chỉ tạo object trên request thread |
| Nhiều request dẫn đến OOM | Queue/pending DeferredResult không giới hạn | Executor bounded, giới hạn concurrent requests và cleanup |
| `SecurityContextHolder` trong worker là `null` | Context gắn với request thread | Chụp dữ liệu tối thiểu hoặc dùng security-context-aware executor |
| User B nhìn thấy user A | Rò ThreadLocal/SecurityContext/tenant cache | Restore/clear context, scope theo request và test concurrency |
| HTTP response trả timeout nhưng công việc vẫn chạy | Timeout chỉ đóng request/future, không hủy downstream I/O | Thiết kế cancellation, deadline downstream và idempotency |
| `CompletableFuture` chạy common pool ngoài ý muốn | Thiếu executor ở `supplyAsync`/stage `Async` | Truyền executor cụ thể |
| 503 khi tải cao | Pool/queue đã bão hòa | Đo queue/active/rejection, tối ưu throughput và backpressure |
| Chỉ `MockMvc` kiểm tra status đầu tiên | Chưa gọi `asyncDispatch` | Dùng `request().asyncStarted()` rồi `asyncDispatch(result)` |
| `@Async` method thực ra chạy cùng thread | Self-invocation bỏ qua Spring proxy | Di chuyển method sang bean khác/gọi qua proxy |
| `LazyInitializationException` ở worker | JPA context/transaction không theo thread | Truyền ID/DTO; mở transaction riêng ở service worker |
| Correlation ID mất khi đổi thread | MDC/trace context không được truyền | Task decorator, library context propagation, cleanup |
| User không còn quyền nhưng job vẫn sửa dữ liệu | Chỉ kiểm tra authorization lúc nhận request | Tái kiểm tra quyền/tenant ở điểm commit khi phù hợp |
| `setResult` sau timeout không thay response | Request đã hoàn tất bằng nhánh khác | Kiểm tra boolean completion và cleanup an toàn |
| `asyncSupported` exception | Custom Servlet filter không tương thích async | Kiểm tra filter registration/dispatcher types |

### Quy trình điều tra ngắn

1. Xác định request có qua Spring Security và được authorize không.
2. Xem controller có trả async return type trước khi phần chậm chạy không.
3. Xem executor nào thực sự chạy task; active threads và queue có giới hạn không.
4. Kiểm tra deadline nào kết thúc trước: MVC, proxy, HTTP client, DB hay future.
5. Kiểm tra request timeout có để lại task/side effect chạy ngầm không.
6. Kiểm tra `Authentication`, tenant và trace context được tạo/truyền/dọn thế nào.
7. Test lại end-to-end với request không auth, auth nhưng thiếu quyền, timeout, rejection, client disconnect và concurrent users.

## 19. Checklist triển khai an toàn

- Chọn `DeferredResult` khi **sự kiện do ứng dụng phát tín hiệu hoàn thành**, `CompletableFuture` khi muốn hợp thành các stage; không nhầm async Servlet với non-blocking I/O.
- Không gọi blocking I/O trên servlet thread trước khi trả async result.
- Sử dụng executor bounded, có thread name, metrics, shutdown và backpressure phù hợp.
- Có timeout HTTP, timeout downstream, xử lý race timeout/completion và chính sách cancellation.
- Catch/sanitize lỗi từ worker; không trả exception nội bộ hoặc token/PII ra client.
- Spring Security xác thực và phân quyền request trước khi bắt đầu task.
- Truyền principal/tenant an toàn; không mặc định `SecurityContextHolder` tự có trên worker.
- Nếu dùng security context propagation, dùng wrapper chuẩn và bảo đảm restore/clear.
- Chỉ dùng immutable DTO/ID giữa thread; transaction, JPA persistence context và request scope không tự truyền.
- Kiểm thử `asyncDispatch`, 401/403, 503/rejection, timeout, session/context leak và concurrent users.
- Giới hạn pending futures, queues và event listeners; cleanup khi request timeout/complete.
- Với job lâu hoặc yêu cầu tồn tại sau restart, dùng job queue + `202 Accepted`, không giữ HTTP request mở.

## Ghi nhớ

`DeferredResult` cho Spring MVC biết rằng **ứng dụng sẽ quyết định lúc nào có response**. `CompletableFuture` mô tả **một pipeline phép tính/async task**, có thể được MVC dùng để hoàn tất response bất đồng bộ. Cả hai cho phép nhả servlet thread ban đầu nhưng **không miễn phí worker threads, không tự hủy tác vụ sau timeout, không bảo đảm non-blocking và không tự truyền mọi `SecurityContext` sang thread tự quản lý**. Thiết kế đúng phải bao gồm executor có giới hạn, timeout và xử lý lỗi, truyền danh tính an toàn, kiểm thử async dispatch và lựa chọn job queue khi công việc vượt vòng đời HTTP request.