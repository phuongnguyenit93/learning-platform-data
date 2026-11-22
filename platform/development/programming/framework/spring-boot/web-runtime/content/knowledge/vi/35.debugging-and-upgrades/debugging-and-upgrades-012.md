# Xác minh bằng kiểm thử qua máy chủ thật sau khi thay web stack hoặc máy chủ

## 1. Vì sao build xanh và MockMvc xanh vẫn chưa đủ để nâng cấp?

Một ứng dụng Spring Boot có thể chạy tốt với **Spring MVC trên Tomcat**, nhưng sau khi chuyển sang **Jetty**, **Undertow**, hoặc thay hẳn **Spring MVC bằng Spring WebFlux/Reactor Netty**, những kiểm thử chỉ gọi controller bằng mock vẫn xanh trong khi production gặp lỗi:

- Multipart bị từ chối ở parser mới dù `MockMultipartFile` trong unit test vẫn hoạt động.
- HTTP 404/500 có body hoặc content type khác do `/error`, container error dispatch hay reactive error handler.
- Cookie session thay tên, path, SameSite/Secure policy, hoặc session không tồn tại xuyên nhiều request.
- Request headers, URI hoặc form post lớn bị từ chối trước khi request đến controller.
- SSE/NDJSON bị buffer, response đã committed nhưng handler vẫn cố thay status khi lỗi.
- Client ngắt kết nối mà stream writer còn giữ thread/file hoặc reactor subscription chưa cleanup.
- CORS preflight/redirect, URL encoding, route matching và method resolution có khác biệt.
- HTTP/2 ALPN/TLS, proxy headers, keep-alive, compression và timeout hoạt động khác môi trường cũ.
- Một application vô tình vẫn chạy MVC vì cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng nằm trên classpath.

Bài này thuộc nhóm **Gỡ lỗi và nâng cấp** của module **Spring Boot - web-runtime**. Nhiệm vụ là xây **bộ hợp đồng HTTP kiểm chứng qua máy chủ thật** để áp dụng *cùng một tiêu chuẩn* trước và sau khi đổi framework/embedded server.

Phạm vi minh họa: **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x, JUnit 5**. Ví dụ dùng Spring Boot 3.3 nhằm thống nhất API; khi deploy thật, sử dụng nhánh được hỗ trợ bảo mật và đối chiếu những thay đổi của Boot/Framework major version mới. Kết quả test trong bài là **kỳ vọng từ thiết kế**, không phải log Gradle được tác giả thực thi.

Sau bài này bạn có thể:
1. Phân biệt đổi **web stack** với đổi **embedded server**.
2. Xác nhận process test đã mở một cổng TCP thật và biết server nào đang chạy.
3. Dùng `@SpringBootTest(RANDOM_PORT)`, `@LocalServerPort` và JDK `HttpClient` kiểm thử Spring MVC trên Tomcat/Jetty/Undertow.
4. Dùng WebFlux `@AutoConfigureWebTestClient`, `FluxExchangeResult`, `StepVerifier` để kiểm thử SSE/NDJSON và cancellation qua Reactor Netty thật.
5. Kiểm tra lỗi **chỉ** bộc lộ qua network/parser/dispatch bằng một ma trận có thể đưa vào CI.
6. Thiết lập điều kiện go/no-go khi rollout, và tránh gọi một lỗi hạ tầng là lỗi business controller.

## 2. Hai phép thay đổi rất khác nhau

### 2.1. Thay embedded server, giữ Spring MVC

```text
Trước:
  spring-boot-starter-web
      └── Spring MVC / DispatcherServlet
             └── Embedded Tomcat

Sau:
  spring-boot-starter-web
      └── Spring MVC / DispatcherServlet
             └── Embedded Jetty hoặc Undertow
```

Controller có thể giữ `@RestController`, `@GetMapping`, `HttpServletRequest`, `MultipartFile`. Nhưng HTTP parsing, connector threads, Servlet async, multipart implementation, error dispatch, HTTP/2 và giới hạn header có thể thay đổi. Đây là **server migration**, không phải chuyển reactive.

Spring Boot 3.3 hỗ trợ Tomcat, Jetty, Undertow cho Servlet apps. Starter mặc định của `spring-boot-starter-web` kéo Tomcat; muốn dùng Jetty/Undertow phải **loại dependency server cũ và thêm starter mới**.

### 2.2. Thay MVC bằng WebFlux, thường cùng lúc đổi server

```text
Trước:
  Spring MVC / DispatcherServlet
      └── Servlet container (Tomcat/Jetty/Undertow)

Sau:
  Spring WebFlux / DispatcherHandler
      └── Reactor Netty (mặc định)
          hoặc reactive adapter của server được hỗ trợ
```

Đây là thay **framework xử lý request**:
- `HttpServletRequest`, `HttpSession`, Servlet `Filter`, `HandlerInterceptor` không tự chuyển thành `ServerWebExchange`, `WebSession`, `WebFilter`.
- MVC `HttpMessageConverter` khác WebFlux `HttpMessageReader/Writer`.
- Controller method có thể vẫn dùng tên `@GetMapping` nhưng API, threading, cancellation, exception handling và codec behavior khác.
- Blocking JDBC/JPA/RestTemplate không tự thành non-blocking vì controller return `Mono`.
- Default reactive WebFlux server là Reactor Netty, nhưng reactive web applications còn có adapter cho các server khác theo Boot 3.3.

**Bẫy cực phổ biến:** thêm `spring-boot-starter-webflux` vào app vốn có `spring-boot-starter-web` để dùng `WebClient` **không tự chuyển server sang WebFlux**. Boot 3.3 ưu tiên MVC khi cả hai có mặt. Kiểm tra classpath, `WebApplicationType`, actual `WebServerApplicationContext`, logs khởi động và behavior, không dựa riêng tên dependency.

### 2.3. Bảng nhận diện

| Dấu hiệu | MVC/Servlet | WebFlux/Reactive |
|---|---|---|
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Request API | `HttpServletRequest` | `ServerWebExchange` |
| Session API | `HttpSession` | `WebSession` |
| Filter | `jakarta.servlet.Filter` | `WebFilter` |
| Message conversion | `HttpMessageConverter` | `HttpMessageReader/Writer` |
| Streaming controller | `StreamingResponseBody`/`SseEmitter` | `Flux<DataBuffer>`/`Flux<ServerSentEvent<T>>` |
| HTTP server default | Tomcat qua `starter-web` | Reactor Netty qua `starter-webflux` |
| Kiểm tra web context | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Kiểm thử controller mock | `MockMvc` | `WebTestClient.bindToController` |
| Kiểm thử HTTP thực | `RANDOM_PORT` + HTTP client | `RANDOM_PORT` + WebTestClient/JDK client |

**Không giả định mọi API Spring MVC có bản reactive 1:1.** Spring Security cũng đổi từ `SecurityFilterChain` sang `SecurityWebFilterChain`, error handling và session persistence cần ma trận riêng.

## 3. Test mock có giá trị gì, và bỏ sót gì?

Các loại test nên cùng tồn tại, nhưng không thay thế nhau.

| Phương pháp | Có mở HTTP socket? | Kiểm tra tốt | Không kiểm chứng |
|---|---|---|---|
| Unit test Java thuần | Không | Pure business policy | HTTP stack |
| `MockMvc` / `@WebMvcTest` | Không | Controller mapping, binding, validation, advice và Servlet async mock | Container header parser, TCP, real multipart parsing/error dispatch |
| `WebTestClient.bindToController` | Không | WebFlux annotated handlers + codec trong mock | Reactor Netty socket/cancel/parser |
| `@SpringBootTest` mặc định `MOCK` | Thông thường không | Full app beans + mock web layer | Embedded server thật |
| `@SpringBootTest(RANDOM_PORT)` | **Có** | App + embedded server + HTTP transport | Chưa kiểm tra ingress/CDN |
| `WebTestClient.bindToServer` | **Có**, nếu trỏ đúng port live | HTTP response + streaming `Flux` | Không thay browser/proxy thực |
| JDK `HttpClient` | **Có** | Headers/cookies/binary body/HTTP version/stream close | Không tái hiện mọi hành vi browser |
| Staging qua ingress/TLS/HTTP/2 | **Có nhiều hop** | Routing, ALPN, buffering, LB/edge limits | Không thay load/chaos test đủ cường độ |

Trong Boot 3.3:
- `@SpringBootTest(webEnvironment = WebEnvironment.MOCK)` là mặc định, không mở server như `RANDOM_PORT`.
- `RANDOM_PORT` chọn port trống trong test; dùng `@LocalServerPort` thay vì hardcode 8080.
- `DEFINED_PORT` có nguy cơ đụng port khi chạy song song; không cần thiết cho smoke integration tests.
- Với `RANDOM_PORT`, HTTP client và server chạy các threads/transactions khác nhau; `@Transactional` trên **test method** không tự rollback transaction đã commit ở HTTP server.

**Ví dụ bẫy transaction:** nếu test tạo order qua HTTP POST rồi assert DB không còn sau khi test `@Transactional` rollback, bạn có thể sai: transaction chạy ở server thread, khác transaction test thread. Hãy cleanup bằng data fixture, repository delete/rollback endpoint test-only hoặc database container reset; không mặc định rollback sẽ xử lý.

## 4. Kiểm thử “hợp đồng quan sát được”, không bám implementation cũ

Một test migration tốt chỉ xem những gì client và hệ thống vận hành có quyền dựa vào:
- Status code chính xác với đường thành công, business fail, validation fail, not-found, unhandled fail.
- `Content-Type`/charset, nội dung JSON/XML/text/binary, schema và giá trị nghiệp vụ.
- Headers chuẩn: Location, Cache-Control, Content-Disposition, ETag, Vary, CORS; không nhầm thứ tự headers với contract.
- Cookies: tên, path/domain, Secure/HttpOnly/SameSite và continuity giữa requests.
- URL encoding, query parameters, matrix/path variables nếu đã có contract.
- Multipart upload, file size, part count và parser rejection.
- Async: request không kết thúc sớm, timeout và error advice.
- SSE/NDJSON: nội dung từng event/record, order, terminal signals, cancellation/cleanup.
- HTTP/1.1 keepalive, TLS, HTTP/2 khi hạ tầng và security policy yêu cầu.
- Response qua reverse proxy/ingress, compression và large headers/bodies.
- Metrics/logging: status/outcome, aborted requests, resource usage, server startup/close.

**Không nên assert:**
- Thứ tự JSON properties nếu schema không quy định.
- `Server` response header phải công khai vendor/version.
- Số TCP packets ứng với số `Flux.onNext` events.
- Text/thứ tự của HTML error page mặc định theo container.
- Lỗi client abort nhất thiết là `Broken pipe` hay `IOException` trong đúng 1 ms.
- HTTP status 503 cho **mọi** request mới khi server graceful shutdown; từng implementation từ chối connection khác nhau.

Trước nâng cấp, đo/ghi baseline về response, latency, behavior HTTP và resource. Khi chuyển server, giữ tests **chung** và chỉ bổ sung assertion riêng cho behavior server **được product contract cho phép khác**.

## 5. Ma trận tối thiểu cần chạy trên server thật

| Nhóm | Kịch bản kiểm thử | Vì sao MockMvc không đủ |
|---|---|---|
| Startup | Web stack và server runtime đúng dự kiến | MockMvc không tạo embedded server |
| Success | JSON UTF-8, URI encoding, query | Kiểm tra network serializer, request decoder |
| Content negotiation | `Accept`/`Content-Type` đúng và sai | Server + message converters/codecs |
| Method mapping | GET/POST/OPTIONS/HEAD | Headers, preflight, container routing |
| Error | 404/422/500, `ProblemDetail` và `/error` | Servlet error-page dispatch không chạy như container thật trong MockMvc |
| Multipart | Actual wire-formatted multipart, >size cap | `MockMultipartFile` không kiểm thử parser thật |
| Headers | Cookie/Authorization, oversized headers | Parser từ chối trước controller |
| Session | Cookie jar qua hai requests | Container cookie behavior và session lifecycle |
| Async MVC | `Callable`/`DeferredResult` | Async dispatch thật và executor behavior |
| Streaming | NDJSON/SSE đọc lần lượt | Network flush, body consumer, encoded media |
| Client abort | Đọc event đầu rồi close/cancel | TCP/HTTP transport/cancellation |
| Security | CSRF, CORS, auth session, redirects | Filter ordering và cookies khi đổi stack |
| HTTP/2/TLS | ALPN, cert trust, cipher/hostname | Mock test không có TLS handshake |
| Compression | Content-Encoding/Vary, streaming | Container/proxy encoder behavior |
| Graceful shutdown | SIGTERM khi request đang chạy | Không có network accept/drain trong mock |
| Operations | Actuator readiness/metrics/traces | Middleware, actual web server observation |

Các tests có thể chạy theo lớp: PR checks nhanh (HTTP core), nightly/CI matrix trên Tomcat/Jetty/Undertow và WebFlux, staging qua TLS/ingress, canary metrics và rollback exercise.

## 6. Dự án A: cùng một test suite cho Spring MVC + Tomcat/Jetty/Undertow

Bộ ví dụ Spring Boot 3.3.13 Java 17+ dưới đây cho phép chọn embedded server qua **Gradle project property** mà vẫn giữ cùng source code/HTTP tests. App có các endpoint đủ để bắt lỗi sau nâng cấp:
- `GET /api/hello`: query decoding, JSON/UTF-8, header ổn định, CORS.
- `POST /api/echo`: JSON binding, content-type, lỗi nghiệp vụ có `ProblemDetail`.
- `GET /api/missing`: đường 404 thực (route không tồn tại).
- `GET /api/crash`: unhandled exception đi tới container/error pipeline.
- `POST /api/upload`: multipart HTTP wire, chỉ đọc metadata file.
- `GET /api/async`: Servlet `Callable`.
- `GET /api/stream`: NDJSON stream thực, có probe cleanup.
- `GET /api/session`: session counter qua nhiều requests/cookie jar.

### 6.1. Project layout

```text
server-contract-mvc/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/servercontract/
    │   │   └── ServletContractApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/servercontract/
            └── ServletLiveContractTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'server-contract-mvc'
```

**`build.gradle`:**

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

def serverEngine = (findProperty('serverEngine') ?: 'tomcat').toString()
if (!(serverEngine in ['tomcat', 'jetty', 'undertow'])) {
    throw new GradleException(
            "Choose -PserverEngine=tomcat|jetty|undertow")
}

dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        if (serverEngine != 'tomcat') {
            exclude group: 'org.springframework.boot',
                    module: 'spring-boot-starter-tomcat'
        }
    }

    if (serverEngine == 'jetty') {
        implementation 'org.springframework.boot:spring-boot-starter-jetty'
    }
    if (serverEngine == 'undertow') {
        implementation 'org.springframework.boot:spring-boot-starter-undertow'
    }

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'expectedServerEngine', serverEngine
}
```

Cơ chế:
- Với `-PserverEngine=tomcat`, starter-web giữ mặc định Tomcat.
- Với `jetty` hoặc `undertow`, exclude transitive Tomcat và include server tương ứng.
- Gradle project property là biến **build-time**, không tự đổi server bằng `--server.port` hay một environment variable runtime.
- Có thể kiểm tra dependency tree bằng `gradle dependencies --configuration runtimeClasspath` và `dependencyInsight`, bảo đảm không vô tình kéo nhiều server factories.
- Nếu project còn starters/transitive modules khác kéo Tomcat trở lại, cần xử lý toàn bộ dependency graph, không chỉ một exclusion.

**Không chạy cùng một JAR rồi đổi `serverEngine` vào lúc startup** với build pattern này. Chạy lại `gradle test` với từng property để build classpath khác nhau.

### 6.2. Runtime configuration

**`src/main/resources/application.properties`:**

```properties
server.port=8080

# Mục tiêu là test parser/response thật:
server.max-http-request-header-size=8KB
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB
spring.mvc.async.request-timeout=5s

# Unhandled exception không lộ stack/message ra HTTP client:
server.error.include-message=never
server.error.include-stacktrace=never

# Tránh đổi compression trong core contract tests,
# hãy kiểm tra compression ở suite riêng.
server.compression.enabled=false
```

**Giải thích:** multipart properties này dành cho Servlet stack. Nó không giới hạn mọi JSON body. `server.max-http-request-header-size` được hỗ trợ như common property nhưng parser semantics theo từng server có thể khác; không assert “byte thứ 8193 luôn 431” trên mọi connector. `spring.mvc.async.request-timeout` là deadline MVC async, không phải read timeout của HTTP client.

### 6.3. Application Java 17+

**`src/main/java/com/example/servercontract/ServletContractApplication.java`:**

```java
package com.example.servercontract;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class ServletContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletContractApplication.class, args);
    }
}

record Greeting(String message) {}

class ContractRejectedException extends RuntimeException {
    ContractRejectedException(String message) {
        super(message);
    }
}

@Component
class StreamProbe {
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger finished = new AtomicInteger();
}

@Configuration(proxyBeanMethods = false)
class ServletAsyncConfig implements WebMvcConfigurer {
    @Bean
    ThreadPoolTaskExecutor mvcTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("mvc-contract-");
        return executor;
    }

    private final ThreadPoolTaskExecutor taskExecutor;

    ServletAsyncConfig(ThreadPoolTaskExecutor taskExecutor) {
        this.taskExecutor = taskExecutor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(taskExecutor);
        configurer.setDefaultTimeout(5000L);
    }
}

@RestController
@RequestMapping("/api")
class ServletContractController {
    private final StreamProbe probe;

    ServletContractController(StreamProbe probe) {
        this.probe = probe;
    }

    @CrossOrigin(origins = "https://frontend.example")
    @GetMapping("/hello")
    ResponseEntity<Greeting> hello(@RequestParam String name) {
        return ResponseEntity.ok()
                .header("X-Contract-Version", "1")
                .body(new Greeting("Xin chào " + name));
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> echo(
            @RequestBody Map<String, String> input) {
        String value = input.get("value");
        if (value == null || value.isBlank()) {
            throw new ContractRejectedException("Missing value");
        }
        return Map.of("value", value);
    }

    @GetMapping("/crash")
    String crash() {
        throw new IllegalStateException("internal diagnostic marker");
    }

    @PostMapping(
            path = "/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Map<String, Long> upload(
            @RequestParam("file") MultipartFile file) {
        return Map.of("bytes", file.getSize());
    }

    @GetMapping("/async")
    Callable<String> async() {
        return () -> {
            Thread.sleep(100);
            return "async-ok";
        };
    }

    @GetMapping(
            path = "/stream",
            produces = "application/x-ndjson")
    StreamingResponseBody stream() {
        return output -> {
            probe.active.incrementAndGet();
            try {
                for (int index = 0; index < 30; index++) {
                    byte[] line = ("{\"n\":" + index + "}\n")
                            .getBytes(StandardCharsets.UTF_8);
                    output.write(line);
                    output.flush();

                    try {
                        Thread.sleep(35);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IOException(
                                "stream worker interrupted", ex);
                    }
                }
            } finally {
                probe.active.decrementAndGet();
                probe.finished.incrementAndGet();
            }
        };
    }

    @GetMapping("/session")
    Map<String, Integer> session(HttpSession session) {
        Integer seen = (Integer) session.getAttribute("visits");
        int now = seen == null ? 1 : seen + 1;
        session.setAttribute("visits", now);
        return Map.of("visits", now);
    }
}

@RestControllerAdvice
class ContractAdvice {
    @ExceptionHandler(ContractRejectedException.class)
    ResponseEntity<ProblemDetail> rejected(
            ContractRejectedException exception) {
        ProblemDetail body = ProblemDetail.forStatus(422);
        body.setTitle("Invalid contract input");
        body.setDetail("Required field is missing");
        return ResponseEntity.status(422).body(body);
    }
}
```

**Lưu ý quan trọng về `@Configuration` ở ví dụ này:** tránh đặt `@Bean ThreadPoolTaskExecutor` và constructor inject chính bean đó vào **cùng** `@Configuration` class; trong một số trường hợp đó tạo dependency cycle. Để đảm bảo runnable và không có bean tự phụ thuộc, **tách executor factory và async config** thành hai class như cách thay thế an toàn dưới đây, rồi giữ controller/record/probe/advice như trên:

```java
// Thay class ServletAsyncConfig ở trên bằng hai class này:
@Configuration(proxyBeanMethods = false)
class AsyncExecutorBeans {
    @Bean
    ThreadPoolTaskExecutor mvcTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("mvc-contract-");
        return executor;
    }
}

@Configuration(proxyBeanMethods = false)
class ServletAsyncConfig implements WebMvcConfigurer {
    private final ThreadPoolTaskExecutor taskExecutor;

    ServletAsyncConfig(ThreadPoolTaskExecutor taskExecutor) {
        this.taskExecutor = taskExecutor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(taskExecutor);
        configurer.setDefaultTimeout(5000L);
    }
}
```

Đoạn thay thế là **một phần của cùng file Java**: chỉ tồn tại **một** định nghĩa `ServletAsyncConfig` trong code cuối. Không giữ hai bản khi copy, nếu không sẽ báo duplicate class. `ThreadPoolTaskExecutor` dùng bounded pool/queue, hỗ trợ `Callable`/`StreamingResponseBody`; `@Bean` do Spring quản lý shutdown.

Các điểm khác:
- `/api/hello` kiểm tra UTF-8 query/JSON và CORS, không dựa vào thứ tự JSON fields.
- `/api/echo` tạo 422 bằng advice, còn `/api/crash` không được advice bắt nên đi qua error pipeline mặc định của Boot/Servlet container.
- `/api/upload` không gọi `file.getBytes()` để tránh copy file lớn vào heap; parser được kiểm tra bằng **HTTP multipart thật**.
- `/api/async` trả `Callable<String>`, response chỉ complete sau async execution/dispatch, không phải ngay khi method return Callable.
- `/api/stream` là response streaming có flush và probe `finally`; khi client đóng, writer có thể thấy IOException hoặc chỉ kết thúc bình thường trước khi socket báo lỗi. Test chỉ assert eventual cleanup.
- `/api/session` tạo và ghi `HttpSession`. Cookie container phổ biến là `JSESSIONID`; test dùng `CookieManager` thay vì hardcode tên cookie.
- `server.error.include-message=never` và `include-stacktrace=never` giúp tránh lộ internal diagnostic marker; vẫn cần chính sách logging/Actuator riêng trong production.
- Một file chỉ có một top-level `public class ServletContractApplication`; các classes khác package-private ở cùng package.

**Nếu viết mã hoàn chỉnh để biên dịch, hãy sử dụng bản `AsyncExecutorBeans` + `ServletAsyncConfig` ở khối thứ hai thay cho class `ServletAsyncConfig` ở khối đầu.** Các tests và hành vi được viết theo bản không có dependency cycle. Chỉ dẫn thay thế này là một bước lắp ghép file rõ ràng, không phải hai project khác nhau.

## 7. JUnit qua HTTP thật cho Spring MVC, không dùng MockMvc

Test suite dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` và JDK `java.net.http.HttpClient`. Với server sống thật:
- Container phải parse URL/query/headers và xử lý Servlet dispatch.
- Multipart gửi đúng wire format qua TCP.
- Error controller xử lý unhandled exception trong môi trường container thật.
- Cookie jar được dùng qua hai requests.
- Response stream được đọc một phần rồi body stream bị đóng chủ động.

**`src/test/java/com/example/servercontract/ServletLiveContractTest.java`:**

```java
package com.example.servercontract;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServletLiveContractTest {

    @LocalServerPort
    int port;

    @Autowired
    ServletWebServerApplicationContext context;

    @Autowired
    StreamProbe probe;

    private HttpClient client() {
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    @Test
    void actualServerMatchesChosenBuild() {
        String expected = System.getProperty(
                "expectedServerEngine", "tomcat");
        String actual = context.getWebServer()
                .getClass().getSimpleName()
                .toLowerCase(Locale.ROOT);

        assertThat(actual).contains(expected);
        assertThat(port).isPositive();
    }

    @Test
    void jsonUtf8AndCustomHeaderSurviveServerChange()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/hello?name=Tr%C3%A0%20%26%20B%C3%A1nh"))
                .GET().build();

        HttpResponse<String> response = client().send(
                request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body())
                .contains("Xin chào Trà & Bánh");
        assertThat(response.headers()
                .firstValue("content-type").orElse(""))
                .contains("application/json");
        assertThat(response.headers()
                .firstValue("x-contract-version").orElse(""))
                .isEqualTo("1");
    }

    @Test
    void corsPreflightIsNotChanged() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/hello?name=Test"))
                .method("OPTIONS",
                        HttpRequest.BodyPublishers.noBody())
                .header("Origin", "https://frontend.example")
                .header("Access-Control-Request-Method", "GET")
                .build();

        HttpResponse<String> response = client().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isBetween(200, 299);
        assertThat(response.headers()
                .firstValue("Access-Control-Allow-Origin")
                .orElse(""))
                .isEqualTo("https://frontend.example");
    }

    @Test
    void jsonInputAndBusinessErrorAreEquivalent()
            throws Exception {
        HttpRequest good = HttpRequest.newBuilder(
                uri("/api/echo"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"value\":\"hello\"}"))
                .build();

        HttpResponse<String> success = client().send(
                good, HttpResponse.BodyHandlers.ofString());
        assertThat(success.statusCode()).isEqualTo(200);
        assertThat(success.body()).contains("\"value\":\"hello\"");

        HttpRequest bad = HttpRequest.newBuilder(
                uri("/api/echo"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{}"))
                .build();

        HttpResponse<String> rejected = client().send(
                bad, HttpResponse.BodyHandlers.ofString());

        assertThat(rejected.statusCode()).isEqualTo(422);
        assertThat(rejected.body())
                .contains("Invalid contract input");
        assertThat(rejected.body())
                .doesNotContain("internal diagnostic marker");
    }

    @Test
    void containerNotFoundAndUnhandledErrorAreVisible()
            throws Exception {
        HttpResponse<String> missing = client().send(
                HttpRequest.newBuilder(uri("/api/missing"))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofString());

        assertThat(missing.statusCode()).isEqualTo(404);

        HttpResponse<String> crash = client().send(
                HttpRequest.newBuilder(uri("/api/crash"))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofString());

        assertThat(crash.statusCode()).isEqualTo(500);
        assertThat(crash.body())
                .doesNotContain("internal diagnostic marker");
    }

    private byte[] multipartBody(int length) throws Exception {
        String boundary = "LiveContractBoundary";
        String prefix = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; "
                + "name=\"file\"; filename=\"sample.txt\"\r\n"
                + "Content-Type: text/plain\r\n\r\n";
        String suffix = "\r\n--" + boundary + "--\r\n";

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(prefix.getBytes(StandardCharsets.UTF_8));
        byte[] file = new byte[length];
        Arrays.fill(file, (byte) 'x');
        out.write(file);
        out.write(suffix.getBytes(StandardCharsets.UTF_8));
        return out.toByteArray();
    }

    @Test
    void multipartIsParsedByRealContainer()
            throws Exception {
        byte[] body = multipartBody(4096);
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/upload"))
                .header("Content-Type",
                        "multipart/form-data; boundary=LiveContractBoundary")
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<String> response = client().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("\"bytes\":4096");
    }

    @Test
    void servletAsyncRequestFinishesBeforeHttpResponse()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/async")).GET().build();

        HttpResponse<String> response = client().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).isEqualTo("async-ok");
    }

    @Test
    void cookieJarPreservesSessionAcrossRequests()
            throws Exception {
        CookieManager cookieManager = new CookieManager(
                null, CookiePolicy.ACCEPT_ALL);
        HttpClient sessionClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .cookieHandler(cookieManager)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/session")).GET().build();

        HttpResponse<String> first = sessionClient.send(
                request, HttpResponse.BodyHandlers.ofString());
        HttpResponse<String> second = sessionClient.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(first.statusCode()).isEqualTo(200);
        assertThat(first.body()).contains("\"visits\":1");
        assertThat(second.statusCode()).isEqualTo(200);
        assertThat(second.body()).contains("\"visits\":2");
    }

    @Test
    void clientCanAbortRealStreamingBodyAndCleanupHappens()
            throws Exception {
        int before = probe.finished.get();

        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/stream"))
                .header("Accept", "application/x-ndjson")
                .GET().build();

        HttpResponse<InputStream> response = client().send(
                request, HttpResponse.BodyHandlers.ofInputStream());

        assertThat(response.statusCode()).isEqualTo(200);

        try (InputStream data = response.body()) {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(data,
                            StandardCharsets.UTF_8));
            assertThat(reader.readLine()).isEqualTo("{\"n\":0}");
            // Đóng body trước khi đọc 30 records.
        }

        await().atMost(Duration.ofSeconds(5))
                .untilAsserted(() -> {
                    assertThat(probe.finished.get())
                            .isGreaterThan(before);
                    assertThat(probe.active.get()).isZero();
                });
    }
}
```

**Kỳ vọng:** **9 tests** chạy với từng server classpath và xác nhận hợp đồng quan sát từ HTTP thực. Đây là rà soát thiết kế; chưa thực thi JDK/Gradle để khẳng định PASS. Những assertions có chủ ý:
- 404/500 chỉ assert **status** cùng nguyên tắc không lộ message; không phụ thuộc body HTML/JSON mặc định của container.
- Multipart test là thật vì dùng JDK HttpClient và encoded boundary; `MockMultipartFile` sẽ không exercise parser mạng.
- Test session dùng `CookieManager` và cùng `HttpClient` qua hai requests, không hardcode cookie name. Khi đổi sang Spring Session/Redis, cookie name có thể đổi; vẫn test continuity.
- Test stream chỉ chứng minh **eventual cleanup**, không khẳng định server đã nhìn thấy đúng một TCP reset hay IOException. Stream hữu hạn có thể hoàn tất bình thường, điều đó chấp nhận được cho test bounded cleanup.
- Server identity test làm test fail rõ nếu classpath vô tình vẫn đang dùng Tomcat.

**Điểm cần sửa khi dùng mã ở mục 6.3:** giữ đúng **bản hai @Configuration classes** ở đoạn thay thế, không giữ bản `ServletAsyncConfig` có self-dependency. Ngoài điều đó, các file có thể được đưa vào project theo layout đã nêu.

### 7.1. Chạy cùng tests qua ba servers

Trong project MVC có JDK17+, Gradle:

```bash
gradle clean test -PserverEngine=tomcat
gradle clean test -PserverEngine=jetty
gradle clean test -PserverEngine=undertow
```

Nếu dùng Gradle Wrapper:
```bash
./gradlew clean test -PserverEngine=tomcat
./gradlew clean test -PserverEngine=jetty
./gradlew clean test -PserverEngine=undertow
```

**Chạy tuần tự** nếu Gradle/test runner chia sẻ build directory; trong CI nên tạo các isolated jobs hoặc Gradle caches/workdirs riêng. Đảm bảo tất cả ba jobs chạy cùng HTTP contract suite và báo engine thật; không chỉ so sánh `build.gradle`.

Nếu một server không khởi động do version dependency incompatibility, test đó **fail rõ**. Không ghi đè server identity test để pass; dùng BOM Spring Boot, kiểm tra transitive dependencies (Jackson, Jetty servlet APIs, embedded server factories) và config properties theo phiên bản.

### 7.2. Cần thêm negative tests thực

Các tests phía trên là **smoke suite thành công**. Bổ sung:
- Multipart file **64KB+1**: container có thể trả 413/400/connection reset theo implementation; kiểm tra **không lưu file**, không đòi mọi server cùng error JSON.
- HTTP header vượt 8KB: parser có thể từ chối 400/431/close trước controller; cần test dưới và trên threshold trên mỗi server.
- Long URI, invalid percent encoding và duplicate headers: kiểm tra parser/normalization.
- Oversized JSON body: `spring.servlet.multipart.max-file-size` không chặn JSON tự động; phải có app/ingress size policy riêng.
- Unsupported media type → thường 415, unacceptable Accept → thường 406; test theo contract/content negotiator.
- Redirect slash, encoded slash/semicolon và path variables: kiểm tra canonicalization và proxy behavior, tránh request smuggling/path traversal.
- Slowloris/slow POST, keep-alive reuse, idle timeout và max connections: chạy load/chaos suite, không biến CI unit tests thành stress tool.
- Servlet error dispatch từ unhandled exception: inspect status/content type/traces và `/error`, không dùng MockMvc để suy container behavior.

## 8. Vì sao lỗi 500 của server thật khác lỗi 500 trong MockMvc?

Spring Boot Servlet stack hỗ trợ lỗi từ container qua error page dispatch đến `/error` / `BasicErrorController` khi phù hợp. Khi exception đã được `@ExceptionHandler` giải quyết, response có thể đi thẳng trở lại client. Khi exception **không** được xử lý ở controller, container/web framework xử lý status, dispatch và body theo version/configuration.

```text
GET /api/crash
       │
       ▼
DispatcherServlet
       │
 IllegalStateException
       │
 @ExceptionHandler? Không
       │
 Servlet error dispatch / Boot Error MVC
       │
       ▼
HTTP 500 + body được Boot/container quyết định
```

Trong mock MVC, request không đi qua một Servlet container thật như Tomcat/Jetty; hành vi error-page dispatch không thể suy từ test controller-only. Tài liệu Boot Testing nhấn mạnh lý do sử dụng **fully running server** khi cần kiểm chứng error page.

Trong WebFlux, `DefaultErrorWebExceptionHandler`/`WebExceptionHandler` có pipeline khác; không thể giả định cùng một `BasicErrorController`. Khi đổi stack:
- Giữ status và client-visible problem contract cố định ở **application error mapper** nếu sản phẩm cần.
- Không dựa vào default error HTML/JSON của một server.
- Bảo đảm exception message/stacktrace không lộ ra client.
- Test lỗi xảy ra trước response commit và **sau** khi stream đã gửi chunk đầu tiên.
- Nhớ 500 response có thể không đồng nghĩa Micrometer observation có `error != none` nếu exception đã được handler giải quyết; metrics cần kiểm thử policy riêng.

## 9. Chuyển WebFlux cần một project và test riêng

Đổi từ MVC sang WebFlux **không chỉ đổi Tomcat sang Netty**. Dự án dưới đây có endpoint contracts tương đương và thêm reactive streaming/cancellation. Nó cố ý **không kéo `spring-boot-starter-web`** để Spring Boot chạy reactive server.

### 9.1. Project layout

```text
server-contract-webflux/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivecontract/
    │   │   └── ReactiveContractApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivecontract/
            └── ReactiveLiveContractTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'server-contract-webflux'
```

**`build.gradle`:**

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
server.max-http-request-header-size=8KB
spring.codec.max-in-memory-size=256KB
server.error.include-message=never
server.error.include-stacktrace=never
```

**Không có `spring.servlet.multipart.*`**, vì project không dùng Servlet multipart. Nếu bổ sung multipart WebFlux, dùng `spring.webflux.multipart.*` và kiểm thử parser WebFlux; không chuyển nguyên test `MultipartFile`/`MockMultipartFile` sang WebFlux rồi giả định như cũ.

### 9.2. Reactive application Java 17+

**`src/main/java/com/example/reactivecontract/ReactiveContractApplication.java`:**

```java
package com.example.reactivecontract;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
public class ReactiveContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContractApplication.class, args);
    }
}

record Greeting(String message) {}
record Echo(String value) {}
record Tick(long n) {}

class ContractRejectedException extends RuntimeException {
    ContractRejectedException(String message) {
        super(message);
    }
}

@Component
class ReactiveProbe {
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger cancellations = new AtomicInteger();
}

@RestController
@RequestMapping("/api")
class ReactiveContractController {
    private final ReactiveProbe probe;

    ReactiveContractController(ReactiveProbe probe) {
        this.probe = probe;
    }

    @CrossOrigin(origins = "https://frontend.example")
    @GetMapping("/hello")
    Mono<ResponseEntity<Greeting>> hello(
            @RequestParam String name) {
        return Mono.just(ResponseEntity.ok()
                .header("X-Contract-Version", "1")
                .body(new Greeting("Xin chào " + name)));
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<Echo> echo(@RequestBody Mono<Echo> input) {
        return input.flatMap(value -> {
            if (value.value() == null
                    || value.value().isBlank()) {
                return Mono.error(
                        new ContractRejectedException("Missing value"));
            }
            return Mono.just(value);
        });
    }

    @GetMapping("/crash")
    Mono<String> crash() {
        return Mono.error(new IllegalStateException(
                "internal diagnostic marker"));
    }

    @GetMapping("/async")
    Mono<String> async() {
        return Mono.delay(Duration.ofMillis(100))
                .map(unused -> "async-ok");
    }

    @GetMapping(
            path = "/ndjson",
            produces = "application/x-ndjson")
    Flux<Tick> ndjson() {
        return Flux.interval(Duration.ofMillis(30))
                .take(3)
                .map(Tick::new);
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(40))
                .map(i -> ServerSentEvent.<String>builder()
                        .id(Long.toString(i))
                        .data("tick-" + i)
                        .build())
                .doOnSubscribe(s ->
                        probe.active.incrementAndGet())
                .doFinally(signal -> {
                    probe.active.decrementAndGet();
                    if (signal == SignalType.CANCEL) {
                        probe.cancellations.incrementAndGet();
                    }
                });
    }

    @GetMapping("/session")
    Mono<Map<String, Integer>> session(WebSession session) {
        Integer before = session.getAttribute("visits");
        int now = before == null ? 1 : before + 1;
        session.getAttributes().put("visits", now);
        return Mono.just(Map.of("visits", now));
    }
}

@RestControllerAdvice
class ReactiveContractAdvice {
    @ExceptionHandler(ContractRejectedException.class)
    ResponseEntity<ProblemDetail> rejected(
            ContractRejectedException exception) {
        ProblemDetail body = ProblemDetail.forStatus(
                HttpStatus.UNPROCESSABLE_ENTITY);
        body.setTitle("Invalid contract input");
        body.setDetail("Required field is missing");
        return ResponseEntity.status(
                HttpStatus.UNPROCESSABLE_ENTITY).body(body);
    }
}
```

Giải thích:
- App dùng `Mono.delay` và `Flux.interval` không block Reactor Netty event-loop bằng `Thread.sleep`.
- `Flux<Tick>` có `take(3)` nên HTTP NDJSON finite stream hoàn tất.
- SSE `Flux<ServerSentEvent<String>>` không có completion để client **chủ động cancel** sau hai events.
- Probe ghi nhận `doFinally(CANCEL)` trong reactive chain. Cancellation do operator khác cũng có thể tạo signal này; test xác định client là bên hủy.
- `WebSession` khác `HttpSession`, và cookie name mặc định có thể khác. Session attributes trong ví dụ là in-memory của **một** test server, không phải shared giữa MVC và WebFlux.
- Không dùng `subscribe()` bên trong controller; nếu làm vậy, source tách khỏi HTTP lifecycle, server khó cancel/cleanup đúng.
- Không dùng `Mono.block()` trong handler; JDK blocking I/O/JPA cần architecture riêng khi chuyển sang reactive.
- Bài demo cố ý không có auth để tập trung HTTP behavior. Ứng dụng thật phải đổi `SecurityFilterChain` thành `SecurityWebFilterChain` nếu chuyển security stack, kiểm thử CSRF/auth/cookies.
- Một file có một `public class` đúng tên `ReactiveContractApplication.java`; các records/controllers/advice package-private cùng package.

## 10. WebFlux test với real Reactor Netty, không bindToController

**`src/test/java/com/example/reactivecontract/ReactiveLiveContractTest.java`:**

```java
package com.example.reactivecontract;

import java.time.Duration;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveLiveContractTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveWebServerApplicationContext context;

    @Autowired
    ReactiveProbe probe;

    @Test
    void reallyStartsReactorNettyServer() {
        String actual = context.getWebServer()
                .getClass().getSimpleName()
                .toLowerCase(Locale.ROOT);
        assertThat(actual).contains("netty");
    }

    @Test
    void jsonAndUtf8Contract() {
        client.get()
                .uri("/api/hello?name=Tr%C3%A0%20%26%20B%C3%A1nh")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Contract-Version", "1")
                .expectBody()
                    .jsonPath("$.message")
                    .isEqualTo("Xin chào Trà & Bánh");
    }

    @Test
    void reactiveJsonBindingAndErrorAdvice() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new Echo("hello"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.value").isEqualTo("hello");

        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{}")
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Invalid contract input");
    }

    @Test
    void reactiveUnhandledErrorReturns500() {
        client.get().uri("/api/crash")
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody()
                .jsonPath("$.status")
                .isEqualTo(500);
    }

    @Test
    void asynchronousResponseCompletes() {
        client.get().uri("/api/async")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("async-ok");
    }

    @Test
    void ndjsonRecordsArriveAndComplete() {
        FluxExchangeResult<Tick> result = client.get()
                .uri("/api/ndjson")
                .accept(MediaType.parseMediaType(
                        "application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new Tick(0),
                        new Tick(1),
                        new Tick(2))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void sseCancelEventuallyReachesLiveServer() {
        int before = probe.cancellations.get();

        FluxExchangeResult<String> result = client.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(String.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext("tick-0", "tick-1")
                .thenCancel()
                .verify(Duration.ofSeconds(5));

        await().atMost(Duration.ofSeconds(5))
                .untilAsserted(() ->
                        assertThat(probe.cancellations.get())
                                .isGreaterThan(before));
    }

    @Test
    void cookieIsReusedWithExplicitHeader() {
        EntityExchangeResult<byte[]> first = client.get()
                .uri("/api/session")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.visits").isEqualTo(1)
                .returnResult();

        String setCookie = first.getResponseHeaders()
                .getFirst(HttpHeaders.SET_COOKIE);

        assertThat(setCookie).isNotBlank();
        String cookiePair = setCookie.split(";", 2)[0];

        client.get().uri("/api/session")
                .header(HttpHeaders.COOKIE, cookiePair)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.visits").isEqualTo(2);
    }
}
```

**Kỳ vọng:** tám tests xác nhận app thật đang lắng nghe bằng Reactor Netty, API JSON/async/errors, NDJSON, SSE cancel và session continuity. Những tests này không gọi `WebTestClient.bindToController`, nên thực sự gửi HTTP tới random port do Boot khởi tạo.

**Lưu ý có chủ đích:**
- `@AutoConfigureWebTestClient` ở `RANDOM_PORT` auto-bind client tới embedded server thật.
- `StepVerifier.verify(Duration)` và Awaitility `atMost` ngăn test vô hạn khi stream có lỗi.
- `thenCancel` trên response body của HTTP client live có thể dẫn tới network stream cancellation; server probe là bằng chứng bổ sung. Phản hồi cancellation là bất đồng bộ và có thể nhạy với TCP/proxy/version — nếu test flake, chẩn đoán transport/probe chứ không khẳng định “server phải nhận ngay”.
- `WebSession` là một contract khác `HttpSession`; hai dự án demo không khẳng định session cookies/serialized attributes tương thích giữa stack.
- Với server khác Reactor Netty, thay expected server identity tương ứng hoặc tách thành matrix; **không xóa test identity** chỉ để suite xanh.

Chạy:

```bash
gradle test
```

Đây là một suite có source code hoàn chỉnh về HTTP basic + streaming. Chưa thử TLS, H2 hay ingress vì chúng cần hạ tầng và certificates riêng; những tests đó được chỉ rõ ở các mục sau.

## 11. Chuyển WebFlux server khỏi Reactor Netty: đừng nhầm với đổi stack

Một WebFlux application có thể chạy trên server adapter khác nếu được Spring Boot phiên bản đó hỗ trợ. Ví dụ Spring Boot 3.3 tài liệu hướng dẫn thay default Reactor Netty bằng Undertow trong Gradle thông qua module replacement:

```groovy
// Fragment từ hướng dẫn Spring Boot 3.3 cho WebFlux:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-undertow'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    modules {
        module('org.springframework.boot:spring-boot-starter-reactor-netty') {
            replacedBy(
                'org.springframework.boot:spring-boot-starter-undertow',
                'Use Undertow instead of Reactor Netty')
        }
    }
}
```

**Fragment**, không phải toàn file build; phải được tích hợp vào project Gradle theo DSL phù hợp. Reactor Netty vẫn có thể là dependency cần thiết cho **WebClient HTTP connector** trong một số cấu hình, dù server không dùng Reactor Netty. Nếu giữ Netty ở client classpath, điều đó không nhất thiết cho biết server đang dùng Netty. Vì vậy test bằng **runtime web server class** và thực tế HTTP, không chỉ nhìn `dependencyInsight`.

Khi thay adapter Netty→Tomcat/Jetty/Undertow:
- Spring WebFlux vẫn là `DispatcherHandler`.
- Các WebFlux `WebFilter`/`ServerWebExchange` API vẫn thuộc reactive stack.
- HTTP framing/parsing, WebSocket, HTTP2, compression, limits và runtime resources có thể khác.
- Có thể phải điều chỉnh HTTP client connector/dependencies cho WebTestClient; không để build xanh nhưng HTTP client không thể mở kết nối.
- Cần chạy cùng streaming/cancel suite trên server target và test transports dưới load.

**Không đổi sang Servlet stack chỉ vì classpath có Tomcat.** WebFlux trên Servlet-based reactive adapter vẫn là reactive framework; MVC + Tomcat mới là Servlet MVC app.

## 12. Multipart khác nhau khi đổi Servlet container và đổi sang WebFlux

### 12.1. Giữ MVC, đổi Tomcat → Jetty/Undertow

Trong Spring MVC, `MultipartFile` được tạo sau khi Servlet multipart parser xử lý request. Cấu hình phổ biến:

```properties
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB
spring.servlet.multipart.file-size-threshold=0B
```

Vẫn phải test qua **HTTP multipart wire format**:
- Một file dưới cap → 200.
- Một file vượt cap → bị từ chối; có thể 413, 400 hoặc connection reset tùy parser/swallow/error dispatch.
- Tổng request chứa nhiều files + part headers vượt cap.
- Trường nhiều parts; filename dài; Content-Disposition malformed.
- Multipart temp disk cleanup khi request fail/client abort.

`MockMultipartFile` chỉ là một object test, không ép Tomcat/Jetty/Undertow parse bytes thực. Trong code MVC mục 7, `multipartBody(...)` tạo boundary và part headers thực để exercise container path.

**Không nhầm `server.tomcat.max-swallow-size` với max upload file.** Swallow size chỉ điều chỉnh lượng request body Tomcat đọc bỏ sau khi đã từ chối, không kiểm soát kích thước file hợp lệ. Jetty/Undertow có parser settings khác; không copy `server.tomcat.*` rồi hy vọng có tác dụng.

### 12.2. MVC → WebFlux

WebFlux nhận `FilePart`/`Part` hoặc `Flux<PartEvent>`, không dùng cùng Servlet MultipartResolver. Các properties:

```properties
spring.webflux.multipart.max-in-memory-size=16KB
spring.webflux.multipart.max-disk-usage-per-part=128KB
spring.webflux.multipart.max-parts=4
spring.webflux.multipart.max-headers-size=2KB
spring.codec.max-in-memory-size=64KB
```

Ý nghĩa:
- `spring.codec.max-in-memory-size` kiểm soát **decoder aggregation** cho những codecs/reader chịu property, **không phải toàn bộ request body**.
- WebFlux `max-in-memory-size` là limit form non-file parts và threshold spool file parts xuống disk.
- `max-disk-usage-per-part` chặn disk usage của từng file part khi parser spool.
- `max-parts` chặn số parts, tránh nhiều fields nhỏ gây parser overhead.
- `max-headers-size` là header **bên trong mỗi multipart part**, không phải HTTP headers ở socket.
- `Flux<PartEvent>` streaming có ownership/DataBuffer/total-byte quota riêng; đừng giả định non-streaming spool settings bảo vệ mọi custom streaming code.

Nếu chuyển một endpoint upload MVC sang WebFlux, phải viết **new server integration tests** cho file-size, disk-temp, success/error/cancel, không chỉ đổi import từ `MultipartFile` sang `FilePart`.

## 13. Giới hạn HTTP header, URI, form và codec: kiểm thử đúng parser

Một thay đổi embedded server có thể làm request nhỏ được chấp nhận nhưng request nhiều cookies/headers bị từ chối ngay ở HTTP parser.

Spring Boot 3.3 common property:

```properties
server.max-http-request-header-size=8KB
```

Theo docs Boot 3.3, Tomcat tính **tổng request line + các headers** theo giới hạn, còn Netty có semantics riêng cho từng header. Jetty/Undertow cũng có implementation/decoder config riêng. Vì vậy cùng `8KB` không bảo đảm identical behavior.

Các kiểm thử:
- Gửi 1 header `X-Test` dài nhưng nhỏ hơn cap.
- Gửi nhiều headers tổng vượt cap.
- Gửi cookie lớn và Authorization.
- Long query/initial request line.
- Method/transfer-encoding edge cases.
- Có proxy trước app hay không.

**Không đòi duy nhất HTTP 431**. Request headers quá lớn có thể dẫn tới 400, 431 hoặc connection reset tùy server/layer; phải có **quy định sản phẩm tại ingress** nếu client cần một error response chuẩn.

**Không tăng limit toàn bộ để chữa lỗi cookie phình**. Một header lớn nhân với nhiều concurrent connections có thể tăng memory và DoS surface. Kiểm tra serialization token, forwarded headers, CORS/security và route design trước.

### 13.1. Content-Length không đủ

HTTP request body có thể dùng chunked transfer hoặc proxy HTTP/2 framing. `Content-Length` có thể không tồn tại, và compression có thể làm kích thước sau giải mã khác kích thước wire.

Muốn giới hạn raw body thật:
- Giới hạn ingress/proxy.
- MVC route đọc `ServletInputStream` theo byte quota.
- WebFlux route đọc `Flux<DataBuffer>` với counter/bounded join.
- Dùng multipart parser quotas cho uploads.
- Đặt max in-flight bytes/concurrency/disk limits.

**Đừng giả định `spring.servlet.multipart.max-request-size` bảo vệ JSON body**. **Đừng giả định `spring.codec.max-in-memory-size` bảo vệ total streamed body**. Hai hiểu nhầm này chỉ lộ ra khi kiểm thử payload thật qua server.

## 14. Async & streaming: khi server change lộ ra race

### 14.1. Servlet async không kết thúc khi controller return Callable

```java
@GetMapping("/async")
Callable<String> async() {
    return () -> {
        Thread.sleep(100);
        return "ready";
    };
}
```

Trong MockMvc cần `request().asyncStarted()`, `request().asyncResult(...)` và `asyncDispatch(...)` để test response cuối. Nhưng kiểm tra behavior Servlet async request/connection thật cần **HTTP client đến RANDOM_PORT**, như `/api/async` ở project MVC.

Một lỗi server migration có thể xảy ra sau controller method return, trong async dispatch hoặc khi response flush. Nếu chỉ unit-test Callable bằng cách `call()` thẳng, không exercise web runtime.

### 14.2. NDJSON/SSE không được xem “một onNext = một TCP packet”

HTTP server/proxy có thể:
- Buffer bytes rồi flush theo threshold.
- Gộp nhiều records thành một network write.
- Nén body làm thời điểm phát dữ liệu thay đổi.
- Mở HTTP/2 DATA frames không trùng Java item boundaries.
- Giữ connection khi client đọc chậm hoặc dừng đọc.

Vì vậy test nên parse **records/events**, không assert số TCP segments hay thời điểm chính xác từng write. Với SSE, đọc `data`/`id` theo protocol; với NDJSON, parse mỗi line thành JSON object.

### 14.3. Client abort thật khác `StepVerifier.thenCancel` local

```java
// Local unit test: KHÔNG có HTTP connection.
StepVerifier.create(Flux.interval(Duration.ofMillis(20)))
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

```java
// Network integration test: getResponseBody() thuộc live WebTestClient.
FluxExchangeResult<String> result = liveClient.get()
        .uri("/api/events")
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
        .expectNext("tick-0", "tick-1")
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

Trong ví dụ thứ hai, `liveClient` phải đang bound tới **một server chạy thật**, bằng `@AutoConfigureWebTestClient` + `RANDOM_PORT` hoặc `WebTestClient.bindToServer().baseUrl(...)`. Để kết luận server nhận cancellation, kết hợp server probe và bounded await. Nếu nguồn reactive code tự `subscribe()` ra ngoài request, nó có thể tiếp tục dù client cancel: test phải phát hiện resource leak này.

### 14.4. Khi client ngắt giữa file upload/download

Kiểm tra:
- Tài nguyên `DataBuffer` được release khi error/cancel, không double-release.
- Spring MVC `StreamingResponseBody`/`SseEmitter` cleanup trong `finally`, `onCompletion`, `onTimeout`, `onError` phù hợp.
- File staging/temp xóa trên complete/error/cancel, và orphan reaper cho JVM crash.
- Nếu response đã committed 200, không kỳ vọng có thể thay thành JSON 500 sau lỗi giữa stream.
- Nếu client abort sau khi server commit DB/payment, cancellation **không rollback commit**; cần idempotency/reconciliation cho retry.
- Không đòi đúng một exception `Broken pipe`: Tomcat/Jetty/Netty/OS khác nhau.

## 15. TLS/SSL bundles và HTTP/2: kiểm thử bằng handshake thực

MockMvc/WebTestClient mock không có TLS handshake. Khi đổi server hoặc nâng Boot, phải chạy network verification cho TLS và HTTP/2 nếu product sử dụng.

Với Spring Boot 3.3, có thể cấu hình **SSL bundles** (PEM hoặc JKS/PKCS12) và tham chiếu trong server:

```properties
# Ví dụ fragment cấu hình PKCS12 đã chuẩn bị:
spring.ssl.bundle.jks.local-server.keystore.location=classpath:local-server.p12
spring.ssl.bundle.jks.local-server.keystore.password=changeit
spring.ssl.bundle.jks.local-server.keystore.type=PKCS12

server.ssl.bundle=local-server
server.port=8443
server.http2.enabled=true
```

**Đây là fragment**, chỉ chạy khi `local-server.p12` có private key/certificate phù hợp. Production dùng secret manager/mount có quyền giới hạn và certificate chain hợp lệ; không hardcode mật khẩu `changeit` như secret production.

Tạo lab-only certificate trên máy của bạn:

```bash
keytool -genkeypair \
  -alias localhost \
  -storetype PKCS12 \
  -keystore local-server.p12 \
  -storepass changeit \
  -keypass changeit \
  -keyalg RSA -keysize 2048 \
  -validity 3 \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

keytool -exportcert -rfc \
  -alias localhost \
  -keystore local-server.p12 \
  -storepass changeit \
  -file local-server.crt
```

Trong project mẫu cần đặt `local-server.p12` vào `src/main/resources` **chỉ cho lab**, hoặc cung cấp đường dẫn filesystem config an toàn. Không commit private key vào repository có chia sẻ. Dùng certificate/trust chain của CA hợp lệ ở production.

Xác minh:

```bash
curl -v --cacert local-server.crt \
  https://localhost:8443/api/hello?name=Test

curl -v --http2 --cacert local-server.crt \
  https://localhost:8443/api/hello?name=Test
```

`curl --http2` yêu cầu curl build hỗ trợ HTTP/2, và giao thức được negotiate qua ALPN với TLS. Nếu client/server không thống nhất ALPN hoặc server adapter cần dependency/config HTTP/2 riêng, request có thể sử dụng HTTP/1.1; **không xem “curl trả 200” là bằng chứng HTTP/2**. Kiểm tra verbose output `ALPN` và HTTP version negotiated, hoặc JDK HttpClient `HttpResponse.version()`.

Cách kiểm thử JDK HTTP client với truststore chuẩn:

```java
// Fragment trong network integration test; không dùng trust-all SSL.
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input =
        Files.newInputStream(Path.of("local-truststore.p12"))) {
    trustStore.load(input, "changeit".toCharArray());
}
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, tmf.getTrustManagers(), null);

HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpResponse<String> response = client.send(
        HttpRequest.newBuilder(
                URI.create("https://localhost:8443/api/hello?name=Test"))
                .GET().build(),
        HttpResponse.BodyHandlers.ofString());

assertEquals(HttpClient.Version.HTTP_2, response.version());
```

Imports cần thiết gồm `java.security.KeyStore`, `java.nio.file.Files`/`Path`, `javax.net.ssl.TrustManagerFactory`/`SSLContext`, `java.net.URI`, `java.net.http.*`, `org.junit.jupiter.api.Assertions.assertEquals`. **Mảnh test** yêu cầu truststore chứa certificate/CA tin cậy và server thực hỗ trợ h2; không bảo đảm chạy nguyên đoạn nếu chưa tạo `local-truststore.p12`. Không dùng `curl -k` hay disable hostname verification để “pass” TLS test.

**Mỗi server có chi tiết HTTP/2 riêng** (ALPN/native support/optional dependencies), cần đối chiếu tài liệu server/Boot 3.3 thực tế. Với TLS termination ở ingress, app có thể chỉ thấy HTTP/1.1 từ proxy: phải test protocol trên **đúng hop** yêu cầu HTTP/2, không nhầm client→ingress với ingress→application.

## 16. Proxy/ingress có thể che khác biệt server backend

```text
External client
      │  TLS + HTTP/2
      ▼
CDN / API Gateway / NGINX
      │  Có thể buffer, rewrite, limit, compress
      ▼
Spring Boot server
      │  HTTP/1.1 hoặc HTTP/2 tuỳ topology
      ▼
Controller / downstream
```

Các vấn đề:
- Proxy trả 413 do body size trước khi Boot nhận request.
- Proxy từ chối headers quá lớn/long URI trước embedded server.
- Proxy buffering làm SSE không đến browser từng event.
- `X-Forwarded-For`/`Forwarded` và `X-Forwarded-Proto` xử lý không đúng có thể làm redirects sang HTTP, cookie Secure sai hoặc redirect loops.
- NGINX/Ingress giữ old connections khi rollout, timeout sớm hơn server.
- CORS preflight có thể được gateway xử lý, nên request không tới controller.
- HTTP/2 có thể chỉ ở client→proxy, không phải proxy→Boot.
- Compression/gzip làm số network bytes khác response body sau decode.

**Có ít nhất ba môi trường test:**
1. Local `RANDOM_PORT`: bỏ qua proxy, nhắm đúng embedded server.
2. Staging ingress: đúng routing, TLS, headers/limits, compression và HTTP protocol thực.
3. Canary production: đo 4xx/5xx, latency, cancellations, memory và client-side errors trong rollout.

Không phải lỗi staging luôn là lỗi Java controller. Dùng correlation request IDs an toàn, proxy access logs và server observations để xác định **tầng đầu tiên từ chối**. Đừng đưa Authorization token, raw Cookie, session IDs hoặc PII vào test logs/metric tags.

## 17. Authentication, sessions và security khi đổi stack

Một suite HTTP contract chỉ gồm anonymous GET sẽ bỏ sót nhiều lỗi quan trọng:
- SecurityFilterChain MVC không tương đương SecurityWebFilterChain WebFlux.
- Cookie `JSESSIONID` và reactive `WebSession`/Spring Session có thể không có cùng name/config/serializer.
- Cookie Secure/SameSite/HttpOnly/Domain/Path có thể đổi khi TLS termination khác.
- CSRF protection trên state-changing requests có thể không hoạt động do security filters mất/đổi.
- Authentication principal/session attribute có thể không đọc được sau schema/serializer nâng cấp.
- Redirect tới login hoặc OAuth callback tính scheme/host sai do forwarded headers.
- CORS policy và credentials khác nhau giữa proxy/MVC/WebFlux.

Test bắt buộc với **client có cookie jar thật**:
1. Login với test user (không dùng production credentials).
2. Giữ Set-Cookie; request đã auth tới protected endpoint.
3. POST với CSRF token đúng và thử thiếu token → expected 403 theo policy.
4. Logout/invalidate; cookie cũ không còn quyền.
5. Canary/mixed versions: phiên tạo trên V1, đọc V2, rồi quay V1 nếu product contract yêu cầu.
6. Rollback sau session V2 write; không chỉ rollback image, vì Redis/JDBC session bytes vẫn là V2.
7. TLS/SameSite/Domain khi frontend cross-site thực sự dùng cookie.

**Không coi local demo `/api/session` là đủ cho Spring Security.** Nó chỉ kiểm tra session continuity trong **một** embedded server. Tích hợp thực cần test login/role/CSRF/Spring Session theo configuration sản phẩm và auth context của các releases.

## 18. Threading, resource leaks và hiệu năng sau server migration

Đổi container có thể thay:
- Servlet worker thread pool và acceptor configuration.
- Reactor Netty event-loop và ByteBuf direct memory.
- Request/body parsing, async continuation và timeout.
- Connection pool, keep-alive, HTTP/2 concurrency.
- TLS handshakes và SSL engine.
- Backpressure/stream buffering behavior.
- Error dispatch/probe metrics naming.

Không so hiệu năng chỉ bằng một HTTP request localhost; benchmark cần warmup, đủ traffic concurrency, payload distribution, GC/heap/direct memory, CPU, jitter và proxy path giống production.

**Khác biệt quan trọng MVC ↔ WebFlux:**
- MVC có thể dùng blocking JDBC/RestClient theo request thread, và `Callable/StreamingResponseBody` cần executor hữu hạn.
- WebFlux event-loop không được chạy blocking `Thread.sleep`/JDBC trực tiếp; dùng non-blocking APIs hoặc offload với boundedElastic khi chưa migrate được phụ thuộc.
- `Flux<DataBuffer>` có thể mang pooled buffers; ai consume phải release đúng. Application giữ buffer qua cancellation cần lifecycle rõ.
- Vừa đổi web stack vừa đổi DB client/ORM/HTTP client làm regression khó phân loại; chia rollout thành những thay đổi nhỏ nếu có thể.
- Không giả định `@Async` detached task được HTTP graceful shutdown chờ. Các job cần executor shutdown policy hoặc durable broker.

Sau nâng cấp, quan sát:
- HTTP p50/p95/p99 và in-flight request counts.
- Thread pool active/queue/rejections.
- JVM heap, direct memory, buffer leak warnings, GC pause.
- 4xx/5xx theo route, request parser rejects, error dispatch.
- Stream cancellation/completion, active connections.
- Timeouts, retries và outbound HTTP client errors.
- Multipart temp disk và orphan files.
- Graceful shutdown SIGTERM→exit duration, in-flight request drain.
- HTTP/2 stream resets, TLS handshake failures, proxy 499/502/503.

## 19. Dependency và auto-configuration regression

Nâng Spring Boot hoặc đổi embedded server có thể tạo thay đổi ngầm trong transitive dependencies và autoconfiguration:
- `javax.servlet.*` đổi thành `jakarta.servlet.*` khi nâng Boot 2→3; class cũ không biên dịch trên Boot3.
- Spring Boot 3.3 cần Java 17+; Java bytecode của dependencies phải phù hợp.
- Tomcat/Jetty/Undertow servlet API level và webserver factories có thể xung đột với library kéo version khác.
- Thêm `spring-boot-starter-webflux` chỉ để dùng WebClient thường giữ MVC, như mục 2.
- Một bean tự khai báo `WebServerFactoryCustomizer` hoặc `WebMvcConfigurer` có thể thay server routing/headers behavior; không chỉ starter quyết định.
- `@EnableWebMvc` hoặc `@EnableWebFlux` có thể tắt bớt auto-config mặc định; xem toàn bộ configuration diff.
- Micrometer/Actuator observation instrumentation và HTTP server tags có thể khác version; kiểm tra metrics contract.
- Jackson modules/codecs có thể thay JSON date/enum/null behavior, nên dùng golden response schemas.
- Spring Security version nâng có thể thay request matcher/filter chains hoặc serialization session.

Lệnh kiểm tra trong Gradle:

```bash
gradle dependencies --configuration runtimeClasspath

gradle dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-boot-starter-tomcat

gradle dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-boot-starter-webflux
```

Lưu dependency graph và image digest trong CI artifact; nếu test cho rằng đang dùng Jetty nhưng runtime server vẫn là Tomcat, chặn merge. Khi làm cross-version tests, không nên giữ Gradle caches/config từ một target rồi cho target khác chạy với dependencies không tái resolve.

## 20. Chạy matrix trong CI và chọn test gates

Một pipeline nâng web runtime hợp lý:

```text
Commit / Pull Request
   │
   ├── javac + static analysis + unit tests
   ├── MVC mock/controller-slice tests
   ├── MVC RANDOM_PORT Tomcat contract suite
   ├── MVC RANDOM_PORT Jetty contract suite
   ├── MVC RANDOM_PORT Undertow contract suite
   └── WebFlux RANDOM_PORT Netty contract suite
                 │
                 ▼
          Artifact/Image build
                 │
                 ▼
       Staging HTTPS/HTTP2/Ingress
           ├── auth/session/CSRF
           ├── multipart limits
           ├── SSE/NDJSON/disconnect
           ├── header/URI parser
           └── graceful/timeout/load
                 │
                 ▼
          Canary rollout with SLIs
                 │
          PASS ───┴─── FAIL
           │            │
        Promote      Halt/rollback
```

**Không bắt buộc mọi project cần cả bốn servers production.** Nếu project chỉ chạy Tomcat→Jetty, CI có thể chạy baseline Tomcat + candidate Jetty. Nếu còn cả hai trong rollout, cả hai phải đạt **cùng external contract**. Tránh tự tạo matrix quá rộng rồi bỏ qua các request quan trọng.

### 20.1. GitHub Actions (ý tưởng hoàn chỉnh theo workspace)

```yaml
name: mvc-server-matrix
on:
  pull_request:
  workflow_dispatch:

jobs:
  live-contract:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        server: [tomcat, jetty, undertow]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Run HTTP server contract
        run: gradle clean test -PserverEngine=${{ matrix.server }}
```

**Chú ý placeholder:** trong workflow thực, expression ở dòng `run` phải là `-PserverEngine=` nối với GitHub Actions syntax `${{{ matrix.server }}`. Nếu dùng JS/template rendering để sinh Markdown, giữ nguyên expression `${{{ matrix.server }}` thành `$` + `{{ matrix.server }}` (hai dấu mở). Hãy sử dụng mẫu chuẩn sau khi copy:

```yaml
      - name: Run HTTP server contract
        run: gradle clean test -PserverEngine=${{{ matrix.server }}
```

Chỉ giữ **một** step `Run HTTP server contract` trong workflow hoàn chỉnh; khối đầu mô tả skeleton và khối sau chỉ thay dòng command sai cấu trúc GitHub expression. Dự án WebFlux chạy trong workflow riêng tương tự với `gradle test`.

**Thực hành CI:** lưu JUnit XML reports, build logs và runtime server identity. Khi test fail, giữ request/response **không chứa secrets** hoặc dữ liệu PII, và lưu cả container/proxy logs ở staging. Một failure chỉ xảy ra trên Undertow vẫn là regression có giá trị dù các server còn lại xanh.

## 21. Một số kiểm thử quan trọng chưa có trong demo cần bổ sung

Dự án minh họa không thể liệt kê hết business contract; một bản migration thực cần thêm các test có giá trị riêng:

**1. Redirect, Location và proxy proto:** request từ HTTPS external qua proxy phải tạo `Location: https://...` đúng, không http redirect loop. Test trusted-forwarded-header configuration; không tin forwarded headers giả mạo từ client trực tiếp.

**2. Multipart và async upload timeout:** gửi file đúng boundary, file quá lớn, client abort giữa body, temp file cleanup. Test bằng `HttpClient`, `curl --data-binary` hoặc client streaming, không chỉ MockMultipartFile.

**3. Authentication/CSRF/SameSite:** dùng browser/HTTP client có cookie jar, login, logout và post protected; khi đổi security stack, xác minh role authorization không regress.

**4. Validation errors:** `@Valid` với Bean Validation starter cần dependency/config, test invalid JSON/schema, 400/422/415; nếu Boot3 không có starter-validation, đừng giả định `@NotBlank` được enforce tự động.

**5. Error sau response commit:** stream 200 đã flush event 1 rồi producer lỗi; xác minh client thấy prefix + termination/error và resource cleanup, không cố assert HTTP 500.

**6. Chunked uploads/large bodies:** kiểm tra `Transfer-Encoding: chunked`, Content-Length absence, backpressure và total-byte counting, không nhầm codec cap với wire body cap.

**7. CORS và OPTIONS:** preflight hợp lệ + origin sai bị chặn, headers/credentials policy, khác nhau qua gateway.

**8. HTTP methods/encoded URI:** DELETE/PUT/PATCH/HEAD/OPTIONS, path variable chứa UTF-8/reserved chars, trailing slash và matrix params nếu API đã dùng. Tránh relax path matching vô điều kiện để pass test nếu mở đường path traversal.

**9. WebSocket/SSE:** connect, gửi/nhận nhiều frames/events, ping/heartbeat, client disconnect, session close và reconnect cursor; khác biệt TCP fragmentation/cancellation.

**10. Resource exhaustion:** nhiều slow clients, giữ connection lâu, chunked uploads, multipart temp disk, active thread pools và direct memory. Dùng load test chuyên biệt, không chạy DoS load vào hệ thống ngoài phạm vi được phép.

**11. Graceful shutdown:** SIGTERM khi HTTP request/SSE đang chạy, readiness→drain, bounded exit, connection reset theo server, job durability; không chỉ gọi Spring context.close trong unit test.

**12. Observability:** HTTP server observation `http.server.requests` status/outcome/error/tags trên runtime thật; một handled 500 có thể `error=none` nếu exception được advice xử lý và không gọi `setError`; không dựa mỗi error tag cho availability SLO.

## 22. “Golden contract” và diff results giữa baseline và candidate

Khi so Tomcat V1 với Jetty V2 hoặc MVC với WebFlux, đừng diff raw HTTP response bytes trực tiếp rồi coi mọi thay đổi là regression:

| Trường | Nên so sánh thế nào |
|---|---|
| HTTP status | Exact nếu là contract |
| JSON response | Parse JSON, so fields/types/semantics, bỏ qua thứ tự object keys |
| Content-Type | So media type/charset contract, không hardcode thứ tự parameters |
| Response headers | Chỉ headers documented; bỏ dynamic Date/Server nếu không là contract |
| Cookies | Name, Path, Domain, Secure, HttpOnly, SameSite, expiry; bỏ random session ID |
| Error response | Status + stable error code/ProblemDetail fields, không stack trace |
| Streaming | Event/data order + completion/cancel, không số network packets |
| Multipart | Accepted/rejected policy và file integrity, không body HTML của parser |
| HTTP/2/TLS | Negotiated protocol, trust chain, hostname, ALPN, header preservation |
| Timing | SLO/p99 và upper bounds có margin, không assert đúng milliseconds |
| Availability | Error ratio từ client/proxy/server, không chỉ server 5xx completed |

**Golden fixtures** nên có request method/URI, sanitized headers/body, expected status/JSON schema/cookies/traces; đừng lưu session cookie real, bearer token, database ID/PII trong test snapshots.

Khi thay Spring Boot version, có thể thay JSON error mặc định mà product contract không quy định. Nếu business clients đang parse error body mặc định, đó vẫn là một **de facto contract** cần phát hiện và quyết định ổn định hóa qua custom error mapper trước khi nâng cấp.

**Giữ tối thiểu hai dạng test:**
- *Compatibility test* kiểm tra những điều không được thay đổi.
- *Intentional-change test* kiểm tra behavior mới mà product đã duyệt, với migration guidance và docs API cho client.

## 23. Troubleshooting khi đổi web runtime

| Triệu chứng | Nguyên nhân điển hình | Cách xác minh |
|---|---|---|
| Test chạy “Jetty” nhưng log vẫn Tomcat | Transitive starter Tomcat còn | Assert actual server class + dependencyInsight |
| Thêm WebFlux nhưng app vẫn MVC | Cả hai starters trên classpath | Kiểm tra ServletWebServerApplicationContext/DispatcherServlet |
| Unit/MockMvc xanh, production 500 | Container error dispatch/multipart/parser khác | RANDOM_PORT và log từ server thực |
| HTTP 404 khác HTML/JSON | Server error pipeline/content negotiation | Assert status + custom problem contract |
| Multipart upload lỗi trên Jetty | Parser limits/temp/part headers khác | Actual boundary upload qua HTTP |
| 500 nhưng app handler không được gọi | Parser/container/proxy từ chối sớm | Request logs/gateway logs/server traces |
| Session mất sau đổi stack | Cookie name/serializer/store/SecurityContext khác | Cookie jar, same store, cross-instance test |
| UTF-8 query khác kết quả | URL encoding/URI parsing/forwarded config | Percent-encoded requests và response JSON |
| CORS preflight pass local nhưng fail staging | Proxy/auth CORS handling | OPTIONS qua ingress đúng headers |
| SSE bị gom thành một response | Container/proxy buffering/compression | `curl -N` và live WebTestClient |
| SSE cancel không làm server cleanup ngay | OS/connector signal bất đồng bộ hoặc detached task | Bounded Awaitility + server probe |
| Netty memory tăng sau stream abort | DataBuffer leak/cancel cleanup không đúng | Leak detection/direct memory metrics |
| Header 8KB chấp nhận Tomcat nhưng Netty khác | Header limit semantics khác | Per-server parser boundary tests |
| WebFlux JSON lớn lỗi codec | `max-in-memory-size` decoder aggregation | Test exact payload/data codec |
| Servlet `@Async` test không đúng | Mock async dispatch vs detached job | Đo response lifecycle qua HTTP thật |
| HTTP/2 chỉ đàm phán HTTP/1.1 | ALPN/curl/server TLS HTTP2 config | Inspect protocol negotiated/cert chain |
| Redirect mất HTTPS | Forwarded headers/proxy trust config | Request through ingress, Location + Cookie Secure |
| Client thấy timeout còn server trả 200 | Client/proxy timeout nhỏ hơn server | Correlation IDs và multi-hop logs |
| Rollback image vẫn có session lỗi | Dữ liệu session format V2 còn Redis | Cross-version session reader/write tests |
| Context test port đụng 8080 | Dùng DEFINED_PORT/hardcoded | RANDOM_PORT + @LocalServerPort |
| Test có @Transactional nhưng DB vẫn có record | Server transaction ở thread riêng | Explicit cleanup/isolation qua DB test fixture |
| Test flake do sleep chính xác | Timing network/scheduler không định tính | Latch + bounded eventual assertions |
| Probe active âm hoặc rò | Cleanup nhiều lần/subscribe nhiều lần | Separate per-request state, idempotent cleanup |
| HTTP 200 nhưng client nhận body thiếu | Disconnect sau headers/partial flush | Stream checksum/record count/retry semantics |

## 24. Checklist trước khi promote ứng dụng

- [ ] Xác nhận thực tế **web stack** và **embedded server**, không suy từ tên starter.
- [ ] Nếu thay server, loại đúng default starter và khởi tạo đúng replacement.
- [ ] Nếu MVC→WebFlux, bỏ Servlet-only filters/APIs, đánh giá blocking calls.
- [ ] Cùng một bộ HTTP contract tests chạy trên baseline và candidate.
- [ ] Test `@SpringBootTest(RANDOM_PORT)` với JDK HttpClient hoặc live WebTestClient.
- [ ] Test actual server class không phụ thuộc logs bị đổi format.
- [ ] Test UTF-8 query, JSON body, status 200/404/422/500, content negotiation.
- [ ] Test CORS preflight, redirects và trusted forwarded headers.
- [ ] Test session cookie continuity và auth/CSRF nếu có.
- [ ] Test multipart bytes thật, part headers, file/request size limits.
- [ ] Test Servlet async Callable/DeferredResult và reactive Mono/Flux tương ứng.
- [ ] Test finite NDJSON/SSE, early disconnect/cancellation/cleanup.
- [ ] Test streaming error sau response committed, không kỳ vọng 500 mới.
- [ ] Test HTTP header/URI limits trên server thật và proxy.
- [ ] Test TLS trust/hostname và HTTP/2 negotiated version nếu sản phẩm yêu cầu.
- [ ] Test latency/resource usage dưới concurrent load, temp disk/direct memory.
- [ ] Test graceful SIGTERM, readiness/ingress drain và rollback.
- [ ] Không tự giả định @Transactional test rollback dữ liệu server-side HTTP.
- [ ] Chạy cùng schema/auth/session compatibility tests trên mixed releases.
- [ ] Đo logs/metrics ở gateway và server vì request có thể bị chặn trước controller.
- [ ] Không leak secrets/PII trong test snapshots, curl logs hay metrics.
- [ ] Giữ rollback target tương thích dữ liệu đã ghi, không chỉ tương thích image.

## 25. Câu hỏi tự kiểm tra

**1. Thay Tomcat bằng Jetty có biến Spring MVC thành WebFlux không?**  
Không. Đây là đổi embedded Servlet container, MVC vẫn dùng DispatcherServlet.

**2. Thêm spring-boot-starter-webflux vào ứng dụng MVC có tự chạy Reactor Netty không?**  
Không theo mặc định Boot 3.3: MVC được ưu tiên khi cả hai starters có mặt. WebFlux starter có thể chỉ được dùng để lấy WebClient.

**3. MockMvc đã test 500 từ controller exception, tại sao cần thêm real server test?**  
Vì Servlet container error-page dispatch/BasicErrorController, parser/headers/cookies và network behavior không được MockMvc mô phỏng đầy đủ.

**4. Vì sao @SpringBootTest không có RANDOM_PORT chưa đủ cho socket tests?**  
Mặc định là MOCK environment; RANDOM_PORT khởi động embedded server thật và cung cấp cổng qua @LocalServerPort.

**5. Có cần assert chính xác server class không?**  
Nên assert hoặc ghi log runtime web server identity khi đây là mục tiêu migration, để tránh classpath vô tình giữ Tomcat/Netty cũ.

**6. Nếu cả hai server trả JSON với properties ở thứ tự khác, có phải regression?**  
Chưa chắc. Nếu thứ tự không là contract, hãy parse JSON và so schema/values thay vì raw bytes.

**7. Vì sao một file multipart upload mock 100KB pass nhưng real server reject?**  
MockMultipartFile không thực sự đi qua Servlet parser với file/request size limits và header/boundary rules của container.

**8. Vì sao 8KB header limit có behavior khác Tomcat và Reactor Netty?**  
Vì HTTP parser/config semantics khác theo server; Boot 3.3 document Tomcat tính tổng request line+headers, Netty có giới hạn theo từng header.

**9. Có thể test client abort bằng StepVerifier trên Flux local rồi kết luận socket đã đóng?**  
Không. Phải test response body từ client kết nối server thật, và quan sát cancellation/cleanup ở server qua bounded wait.

**10. Vì sao không assert 500 sau khi SSE đã flush 200?**  
Vì headers/status có thể đã committed; lỗi sau đó thường kết thúc stream/connection, không tạo HTTP 500 mới.

**11. Test HTTP/2 thành công phải assert điều gì?**  
Giao thức thực sự negotiated là HTTP/2 cùng TLS/ALPN/trust/hostname, không chỉ HTTP status 200 hoặc curl --http2 option.

**12. Nếu test @Transactional qua RANDOM_PORT, DB write của server có tự rollback không?**  
Không. Server xử lý ở thread/transaction riêng, cần explicit cleanup hoặc DB isolation trong integration test.

**13. CORS pass trên localhost nhưng fail qua ingress vì sao?**  
Gateway có thể xử lý OPTIONS/rewrite Origin, headers hoặc security/filter chains; cần test đúng hop thực tế.

**14. Sticky load balancing có sửa session incompatibility giữa V1/V2 không?**  
Không. Pod recreation/rollback và shared serialized session data vẫn phải có dual-reader/schema compatibility.

**15. Khi demo stream close body sớm mà probe finished cuối cùng tăng, đã chứng minh đúng một IOException chưa?**  
Chưa. Nó chỉ chứng minh callback eventually kết thúc; vì stream hữu hạn, server có thể hoàn tất tự nhiên. Muốn chứng minh transport abort phải thêm connector-side evidence.

## 26. Tài liệu chính thức để đối chiếu

1. Spring Boot **3.3 Embedded Web Servers** — thay Tomcat bằng Jetty/Undertow, thay Reactor Netty bằng reactive server khác; Gradle/Maven dependency practices. https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
2. Spring Boot **3.3 Testing Spring Boot Applications** — `MOCK`/`RANDOM_PORT`, `@LocalServerPort`, WebTestClient và giới hạn `@Transactional` across server threads. https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
3. Spring Boot **3.3 Reactive Web Applications** — chọn MVC hay WebFlux khi hai starters cùng tồn tại, Reactor Netty default. https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
4. Spring Boot **3.3 Servlet Web Applications** — Spring MVC, multipart, embedded servers và web filters. https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
5. Spring Boot **3.3 Common Application Properties** — HTTP headers, multipart, codecs, TLS, compression, async. https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
6. Spring Framework — **WebTestClient** (mock bind options, `bindToServer` và `FluxExchangeResult` cho streaming). https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
7. Spring Framework — **MockMvc Async Requests** (async dispatch) và lý do chưa đủ cho container. https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html
8. Spring Framework — **MVC Async Requests** (`Callable`, `DeferredResult`, `StreamingResponseBody`, `SseEmitter`). https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
9. Spring Framework — **WebFlux** (reactive pipeline, body codecs, backpressure, WebSession). https://docs.spring.io/spring-framework/reference/web/webflux.html
10. Spring Framework — **Data Buffers and Codecs**, pooled memory và release semantics. https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
11. Spring Boot **3.3 Graceful Shutdown**, request draining và server-specific behaviors. https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
12. Spring Boot **3.3 SSL**, SSL bundles và server TLS. https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
13. Project Reactor — **StepVerifier** và virtual-time testing. https://projectreactor.io/docs/core/release/reference/testing.html
14. Apache Tomcat **10.1 HTTP Connector**, request headers, form post, swallow và connector limits. https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
15. RFC **9110 HTTP Semantics** (4xx/5xx, Content-Type, Content Negotiation) và RFC **9113 HTTP/2**. https://www.rfc-editor.org/rfc/rfc9110.html , https://www.rfc-editor.org/rfc/rfc9113.html

**Tóm lại:** Khi đổi **web stack** hoặc **embedded HTTP server**, build/test mock xanh không đủ bảo đảm HTTP contract giữ nguyên. Hãy chạy **cùng một bộ kiểm thử qua máy chủ thật** (Spring Boot `RANDOM_PORT`) trước/sau nâng cấp, xác minh server runtime identity và từng hợp đồng client-visible: status, headers, JSON, cookies, multipart, async, streaming, cancellation, error dispatch, TLS/HTTP2 và ingress. Khi phát hiện khác biệt, phân loại theo framework, container, proxy và business contract; quyết định sửa hay chấp nhận thay đổi trước khi promote, không để khách hàng phát hiện trong rolling deployment.