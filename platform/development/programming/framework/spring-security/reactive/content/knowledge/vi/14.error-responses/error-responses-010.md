# Xử lý lỗi khi phản hồi đã được gửi hoặc luồng dữ liệu đã bắt đầu

> **Chủ đề cha:** Phản hồi lỗi trong **Spring Security reactive / Spring WebFlux**. Bài học tập trung vào ranh giới **HTTP response committed**, lỗi phát sinh khi `Mono`/`Flux` đang được ghi ra network và cách phối hợp HTTP error handling với authentication/authorization. Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Framework 6.x, Spring Security 6.x và Reactor**. Mã triển khai chỉ dùng password giả cho môi trường thử nghiệm; trong hệ thống thực phải dùng TLS và hệ thống xác thực tin cậy.

## 1. Mục tiêu và câu hỏi trung tâm

Sau bài này, bạn có thể:

1. Phân biệt **lỗi trước khi phản hồi được commit** và **lỗi sau khi status/headers đã commit**.
2. Hiểu `ServerHttpResponse.isCommitted()`, `setStatusCode(...)` và `beforeCommit(...)` thực sự có thể làm gì.
3. Biết vì sao `@ExceptionHandler`, `WebExceptionHandler`, `ResponseStatusExceptionHandler` hoặc các handler của Spring Security **không thể sửa một response đã gửi** thành 401/403/500.
4. Viết WebFlux API trả JSON error khi lỗi xảy ra **trước body**.
5. Thiết kế **Server-Sent Events (SSE)** để phát lỗi theo **giao thức ứng dụng** khi các event đầu đã ra ngoài.
6. Phân biệt stream error đã xử lý bằng `onErrorResume` với lỗi không được xử lý khiến stream/connection kết thúc.
7. Thử nghiệm request chưa đăng nhập, lỗi đã được ánh xạ thành 503 trước commit, stream có sự kiện lỗi và trường hợp publisher phát `onError`.
8. Phòng tránh gửi lộ nội dung nhạy cảm hoặc dữ liệu chưa phân quyền trong một response đã bắt đầu; hiểu cancellation, timeout, retry, logging và proxy buffering.

**Kết luận sớm:** **HTTP status và headers chỉ có thể được đặt trước khi commit; sau commit không thể “đổi 200 thành 500”.** Với streaming, nếu còn điều khiển được publisher và giao thức cho phép, có thể **phát một bản ghi/sự kiện lỗi có cấu trúc trong body**, hoặc dừng luồng/kết nối. Đây không phải phản hồi HTTP lỗi mới.

## 2. HTTP response committed nghĩa là gì?

Trong WebFlux, một response đi qua các giai đoạn logic:

```text
Request nhận được
    |
    v
Handler / Security xác định status, headers, body publisher
    |
    v
Response chưa committed
    |
    +-- Có lỗi trước khi commit?
    |       -> handler phù hợp có thể chọn 4xx/5xx và error body
    |
    v
Commit status + headers + cookies
    |
    v
Ghi body (có thể một hoặc nhiều DataBuffer/chunks/events)
    |
    +-- Có lỗi sau commit?
    |       -> KHÔNG đổi status/header đã commit được
    |       -> app-level error event nếu protocol cho phép
    |       -> hoặc kết thúc stream/connection, ghi logs/metrics
    |
    v
Hoàn tất hoặc kết thúc bất thường
```

`ServerHttpResponse` được Spring Framework cung cấp qua `ServerWebExchange.getResponse()`. Một khi status/headers đã được commit:

- Không thể đổi status đã gửi từ **200 OK** sang **500 Internal Server Error**, **401 Unauthorized** hoặc **403 Forbidden** cho cùng response.
- Không thể gửi thêm một response header `Content-Type: application/problem+json` mới để biến phần thân đang là SSE/JSON thành error JSON.
- Không thể quay lại xóa những bytes đã gửi cho client, thu hồi dữ liệu hoặc “trả lại” một phần JSON array đã stream.
- `response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR)` có thể trả `false` vì status đã commit; code nên hiểu tín hiệu đó và **không giả định** đã đổi được status.
- Việc gọi thêm `setComplete()` hoặc một error writer không tạo **HTTP response thứ hai**.

**Phân biệt commit với việc client đã thực sự nhìn thấy data:** `isCommitted()` phản ánh trạng thái phía framework/server reactive. Proxy, kernel socket buffer và client có thể tiếp tục buffer, nên thời điểm packet tới client có thể khác. Nhưng đối với ứng dụng, **sau commit không còn cơ hội viết lại status/headers**, dù client chưa render được dữ liệu.

### 2.1 Một lỗi trước commit và một lỗi sau commit

**Trước commit:**

```text
GET /api/report
  -> repository.findById(...) báo lỗi trước khi tạo body
  -> @ExceptionHandler / error handler chọn status 503
  -> HTTP/1.1 503 Service Unavailable
  -> Content-Type: application/problem+json
  -> JSON ProblemDetail
```

**Sau commit:**

```text
GET /stream/live
  -> status 200 và Content-Type: text/event-stream được commit
  -> event đầu tiên đã đi qua response writer
  -> downstream publisher phát onError
  -> KHÔNG thể chuyển status 200 sang 500
  -> client thấy stream dừng bất thường hoặc app-error event
     (nếu ứng dụng đã chủ động chuyển lỗi thành event)
```

Đừng hứa rằng mọi server sẽ đóng TCP bằng cùng một cách hoặc mọi client sẽ nhìn thấy một HTTP 500. Ở tình huống streaming, kết quả có thể phụ thuộc codec, Netty/Jetty, HTTP/1.1 hoặc HTTP/2, chunk buffering, network và reverse proxy.

## 3. ServerHttpResponse API và giới hạn thực tế

| API | Mục đích | Chú ý khi response committed |
| --- | --- | --- |
| `response.isCommitted()` | Kiểm tra response đã commit hay chưa | Là thông tin trạng thái, không phải khóa giao dịch |
| `response.setStatusCode(HttpStatusCode)` | Đặt status trước commit | Trả `false` nếu không thay đổi được do đã commit |
| `response.getHeaders()` | Đọc/thiết lập headers | Sau commit không trông đợi thêm/sửa headers |
| `response.addCookie(...)` | Gửi response cookie | Có thể báo lỗi khi response đã committed |
| `response.beforeCommit(Supplier<? extends Mono<Void>>)` | Đăng ký việc cần chạy ngay **trước khi** commit | Không phải callback “sửa lỗi sau commit” |
| `response.writeWith(...)` | Ghi body từ publisher `DataBuffer` | Lỗi sau khi ghi bắt đầu không tự đổi status |
| `response.writeAndFlushWith(...)` | Ghi và flush theo nhóm publisher | Thường dùng cho response streaming; không bảo đảm recover như một response mới |
| `response.setComplete()` | Hoàn tất phản hồi không ghi thêm body từ caller đó | Không làm lại status hay xóa bytes đã gửi |

Ví dụ **đoạn minh họa trong WebFilter/handler có biến `exchange`**:

```java
ServerHttpResponse response = exchange.getResponse();

if (!response.isCommitted()) {
    boolean changed = response.setStatusCode(
        HttpStatus.SERVICE_UNAVAILABLE
    );
    // changed chỉ nói status có được chấp nhận ở thời điểm gọi hay không.
}
else {
    // Chỉ log/metrics và xử lý lỗi của publisher đúng phạm vi.
    // Không thử dựng một error HTTP response mới ở đây.
}
```

Đoạn trên cần import `org.springframework.http.HttpStatus` và `org.springframework.http.server.reactive.ServerHttpResponse`. Kiểm tra `!isCommitted()` rồi gọi `setStatusCode` **không phải một transaction atomic** với mọi tác vụ async khác; luôn tôn trọng giá trị trả về hoặc để framework quản lý error response. Trong production, không viết nhiều WebFilter cùng giành quyền đặt status.

### 3.1 beforeCommit đúng mục đích

`beforeCommit` được thiết kế cho công việc cần hoàn tất **trước** khi phản hồi commit: bổ sung headers, correlation ID, logic quan sát hoặc hoàn tất một bước reactive ngắn phù hợp. Ví dụ:

```java
exchange.getResponse().beforeCommit(() ->
    Mono.fromRunnable(() ->
        log.debug("Response is about to commit")
    )
);
```

Đây là **snippet**, cần có `exchange`, `log` và import Reactor `Mono`. Không dùng callback này để chạy blocking I/O, không `Thread.sleep`, không `block()`. **Nó không chạy sau commit để sửa lỗi đã phát sinh**, và nếu bản thân callback thất bại còn có thể gây ra lỗi commit.

### 3.2 Những thao tác không thể “sửa” lỗi muộn

Các ý tưởng sau đều sai nếu body đã phát ra:

- Gọi `response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR)` rồi kỳ vọng client thấy 500.
- Dựng `ResponseEntity.status(500).body(problem)` trong một `onErrorResume` ở **bên ngoài một body writer đã commit**, rồi mong WebFlux gửi HTTP response thứ hai.
- Gửi `WWW-Authenticate` sau khi một SSE stream bắt đầu để “đổi” response thành 401.
- Ném `ResponseStatusException(HttpStatus.FORBIDDEN)` sau event đầu và nghĩ exception handler có thể đổi status.
- Dùng `response.getHeaders().set(...)` sau commit mà không có cơ chế trailers hợp lệ được thiết kế trước; trailers không thay thế HTTP status.
- Log exception rồi trả `Mono.empty()` trong handler lỗi toàn cục, nhưng không báo cho client stream đã bị rút ngắn.
- Gọi `subscribe()` thủ công để viết thông báo lỗi song song với response đang được WebFlux sở hữu, gây **hai writer** tranh cùng response.

## 4. Chuỗi exception handling của WebFlux

WebFlux có một số cơ chế xử lý lỗi. Cần hiểu phạm vi của chúng:

| Cơ chế | Dùng để làm gì | Ranh giới committed |
| --- | --- | --- |
| `@ExceptionHandler` trong `@RestControllerAdvice` | Ánh xạ exception từ handler sang `ResponseEntity`/`ProblemDetail`/body | Có thể tạo response khi lỗi được bắt **trước commit** |
| `ResponseStatusException` | Gắn HTTP status cho lỗi được xử lý ở WebFlux | Không viết lại được status đã commit |
| `WebExceptionHandler` | Xử lý exception đi qua `WebFilter`/`WebHandler` | Có thể trả response mới khi còn khả năng commit |
| `WebFluxResponseStatusExceptionHandler` | Xử lý `ResponseStatusException`, `@ResponseStatus` | **Javadoc nêu rõ:** nếu response đã committed, lỗi không được resolve và được propagate |
| `ErrorWebExceptionHandler` của Spring Boot | Render lỗi toàn cục khi có thể | Không thể tạo error body/status mới sau commit |
| Reactor `onErrorResume` *bên trong stream publisher* | Chuyển nguồn lỗi thành event/fallback hợp lệ trước khi body writer nhận `onError` | Có thể phát **in-band event**, không đổi status HTTP |
| `doOnError` / `doFinally` | Ghi nhận lỗi, metrics, signal/cancellation | Không “nuốt” lỗi và không tạo HTTP response |
| `ServerAuthenticationEntryPoint` | Xử lý authentication challenge (ví dụ Basic 401) | Phải diễn ra trước khi response đã gửi |
| `ServerAccessDeniedHandler` | Xử lý từ chối truy cập (thường 403) | Không đổi được response 200 đã commit |

Một `@ControllerAdvice` thường phù hợp cho **lỗi JSON trước khi server bắt đầu ghi body**. Đối với lỗi xảy ra sau sự kiện đầu tiên của `Flux`, không nên tự động kỳ vọng advice được gọi và gửi body JSON sạch. Spring Framework Javadoc về `WebFluxResponseStatusExceptionHandler` ghi rõ rằng nếu response đã commit, exception vẫn unresolved và được truyền tiếp.

### 4.1 Spring Security nằm ở đâu trong lỗi này?

Spring Security WebFlux dùng `SecurityWebFilterChain` và các WebFilter như authentication/authorization, trong đó cơ chế xử lý `AccessDeniedException` có thể gọi `ServerAuthenticationEntryPoint` hoặc `ServerAccessDeniedHandler` tùy principal và loại lỗi.

**Trước khi ghi body:** nếu người dùng không có credential, yêu cầu protected endpoint có thể nhận **401**; nếu người đã xác thực nhưng thiếu role, có thể nhận **403**.

**Sau khi body stream đã bắt đầu:** nếu một bước trong stream phát hiện quyền bị thu hồi hoặc một method security check xảy ra muộn, response có thể đã là **200**; Spring Security không thể thay status/headers đã commit. Điều đó **không có nghĩa phải tiếp tục phát dữ liệu**: hãy **dừng stream**, không gửi thêm dữ liệu nhạy cảm và phát tín hiệu lỗi theo giao thức ứng dụng nếu điều đó được phép và an toàn.

**Bài học quan trọng về thiết kế:** Thực hiện các phép xác thực/phân quyền quyết định việc **có được mở stream hay không** trước khi phát phần body đầu. Nếu quyền có thể thay đổi trong một stream dài, thiết kế kiểm tra lại quyền tại các mốc phù hợp **trước khi phát event kế tiếp**, và đưa ra chính sách dừng stream rõ ràng khi quyền bị thu hồi. Không phát dữ liệu chờ kiểm tra quyền.

## 5. Lỗi trong Reactor: onNext, onError và onComplete

Một publisher tuân theo hợp đồng Reactive Streams:

```text
onSubscribe
    |
    +-- onNext(value1)
    +-- onNext(value2)
    +-- ...
    |
    +-- onComplete
    |
    hoặc
    +-- onError(exception)
```

**`onError` là tín hiệu kết thúc**. Sau khi một publisher đã phát `onError`, nó không được tiếp tục phát `onNext` trong chính subscription đó. `onErrorResume` không “làm publisher lỗi tiếp tục như chưa có gì”; nó **chuyển sang một publisher thay thế** trước khi downstream subscriber nhận lỗi, nếu đặt ở đúng vị trí.

Trong WebFlux HTTP response, subscriber là phần framework/codec/body writer. Khi publisher body trả `onError`, server phải xử lý lỗi trong khi response có thể đã commit. Nếu đã commit, không còn quyền gửi status mới.

### 5.1 Bắt lỗi trước khi đi vào body writer

```java
Flux<ServerSentEvent<String>> events = upstreamEvents
    .onErrorResume(DependencyUnavailableException.class, ex ->
        Flux.just(ServerSentEvent.<String>builder()
            .event("app-error")
            .data("DEPENDENCY_UNAVAILABLE")
            .build())
    );
```

Đây là **snippet** có biến `upstreamEvents`, class exception và imports phù hợp. Nó minh họa: handler nhận **event stream đã được biến đổi**, bao gồm một event báo lỗi thay vì `onError` không được xử lý. Khi sự kiện lỗi xuất hiện sau các event trước đó, HTTP status vẫn là status đã commit (thường **200**).

**Cảnh báo:** Một event tên `app-error` **không phải** `HTTP 500`, cũng không phải lỗi network của JavaScript `EventSource.onerror`. Client cần chủ động đọc `app-error` và xử lý theo **contract** đã tài liệu hóa.

### 5.2 Bắt lỗi sai vị trí

```java
Flux<String> unsafe = source
    .map(this::serialize)
    .doOnError(log::warn);

// Sau đó, ở một tầng bên ngoài response.writeWith(...):
// cố đổi HTTP status khi log báo lỗi.
```

Đây là **pseudocode minh họa**, không có `source` / `serialize` / `log` sẵn. `doOnError` chỉ quan sát tín hiệu, không recover. Nếu serialization hoặc nguồn dữ liệu lỗi **sau commit**, đặt status 500 lúc ấy quá muộn.

Thay vào đó, xác định error boundary từ sớm: lỗi domain trong publisher có thể chuyển thành **event theo giao thức**; lỗi serialization/transport sau khi bytes đã đi ra thì không thể hồi phục đầy đủ bằng status, nên phải log/metric và để kết nối kết thúc đúng cách.

### 5.3 onErrorResume không phải chữa mọi lỗi

Một `onErrorResume(Throwable.class, ...)` bắt mọi lỗi và biến thành “thành công” có thể che security exception, lỗi hạ tầng nghiêm trọng hoặc lộ dữ liệu sai. Chỉ xử lý **những loại lỗi đã biết** và có event protocol tương ứng. Không biến `AccessDeniedException` thành event “OK” rồi tiếp tục stream dữ liệu nhạy cảm.

Trong ứng dụng streaming có quyền truy cập, hãy phân loại:

- **Lỗi tạm thời từ upstream:** có thể phát `app-error` với mã không nhạy cảm và kết thúc luồng.
- **Quyền bị thu hồi:** ngừng gửi dữ liệu; có thể phát sự kiện “access-revoked” tối giản nếu giao thức/authorization cho phép, sau đó kết thúc.
- **Bug serialization/codec/transport:** thông thường không thể đảm bảo gửi một event hợp lệ nữa; để publisher lỗi, ghi nhận sự cố, client kết nối lại theo policy.
- **Client đã hủy subscription:** không cố phát thêm event, vì subscriber không còn nhận dữ liệu.

## 6. Bài thực hành: hai kiểu lỗi trên một WebFlux server

Ta sẽ xây API có hai loại response:

1. **JSON request thông thường**, lỗi xảy ra trước khi body được viết → `@RestControllerAdvice` tạo **503** với `ProblemDetail`.
2. **SSE stream**, sau một event data thì nguồn phát lỗi. Với endpoint xử lý đúng, ta biến lỗi thành **event `app-error`** và hoàn tất; với endpoint cố tình không bắt lỗi, publisher phát `onError` và server có thể kết thúc stream bất thường.

HTTP Basic được bật để nhìn rõ Spring Security xử lý 401 **trước** khi stream mở. Các user và mật khẩu chỉ dùng trong bài thực hành localhost.

### 6.1 Dependencies và cấu trúc project

Tạo Spring Boot **3.x**, Java **17+**, Gradle Groovy, chọn Spring Reactive Web và Spring Security. Phần dependencies của `build.gradle` trong project đã có Spring Boot plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm đồng thời `spring-boot-starter-web` cho HTTP server demo. Nếu MVC và WebFlux cùng có mặt, Spring Boot thường chọn MVC mặc định; `SecurityWebFilterChain` thuộc reactive HTTP stack, không phải Servlet `SecurityFilterChain`.

Tạo các file:

```text
src/main/java/com/example/streamfailures/
  StreamFailuresApplication.java
  SecurityConfig.java
  ErrorDemoController.java
  EarlyErrorAdvice.java
  ResponseAuditWebFilter.java
src/test/java/com/example/streamfailures/
  StreamErrorPublisherTest.java
  StreamErrorHttpTest.java
```

Toàn bộ class nằm trong package `com.example.streamfailures`. Đây là **các file Java độc lập**, không ghép nhiều `public class` vào một file. Gradle wrapper biên dịch chúng cùng dependencies; **không chạy từng file bằng `javac` trần** mà thiếu Spring và Reactor.

### 6.2 StreamFailuresApplication.java

`src/main/java/com/example/streamfailures/StreamFailuresApplication.java`:

```java
package com.example.streamfailures;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamFailuresApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamFailuresApplication.class, args);
    }
}
```

### 6.3 SecurityConfig.java: authentication/authorization trước stream

`src/main/java/com/example/streamfailures/SecurityConfig.java`:

```java
package com.example.streamfailures;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/api/**", "/stream/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }
}
```

**Giải thích bảo mật:**

- `/public/**` được phép truy cập không credential; `/api/**` và `/stream/**` đòi authentication hợp lệ.
- HTTP Basic filter xác thực credential **trước** khi controller tạo SSE publisher cho protected route. Vì vậy request `GET /stream/handled` không có Basic header sẽ bị trả **401** mà không rò rỉ event data.
- `MapReactiveUserDetailsService` và password demo chỉ để bài có thể chạy. Production phải dùng Identity Provider/user store an toàn, HTTPS/TLS và không log `Authorization` header.
- `authenticated()` chỉ kiểm tra đã đăng nhập; nếu stream chứa dữ liệu phân biệt role/tenant, cần thêm `hasRole`/`hasAuthority` hoặc quyền tài nguyên tại service **trước khi phát event**.
- `anyExchange().denyAll()` từ chối request ngoài allowlist theo security chain này.
- Ví dụ chỉ GET; CSRF mặc định vẫn có thể ảnh hưởng POST/PUT/DELETE. Không tắt CSRF để “chữa” lỗi đang phát sinh trong SSE GET.

### 6.4 ErrorDemoController.java: JSON error và hai kiểu SSE

`src/main/java/com/example/streamfailures/ErrorDemoController.java`:

```java
package com.example.streamfailures;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ErrorDemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/api/early-error",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<String> earlyError() {
        // Publisher lỗi trước khi WebFlux có dữ liệu body để ghi.
        return Mono.error(new DemoFailureException(
            "Simulated dependency failure"
        ));
    }

    @GetMapping(
        value = "/stream/handled",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> handledStream() {
        return eventsThenFailure()
            .onErrorResume(DemoFailureException.class, ex ->
                Mono.just(ServerSentEvent.<String>builder()
                    .event("app-error")
                    .data("DEPENDENCY_UNAVAILABLE")
                    .build())
            );
    }

    @GetMapping(
        value = "/stream/unhandled",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> unhandledStream() {
        // Cố ý KHÔNG onErrorResume: minh họa lỗi giữa body.
        return eventsThenFailure();
    }

    private Flux<ServerSentEvent<String>> eventsThenFailure() {
        var first = ServerSentEvent.<String>builder()
            .id("1")
            .event("item")
            .data("first")
            .build();

        return Flux.concat(
            Mono.just(first).delayElement(Duration.ofMillis(40)),
            Mono.<ServerSentEvent<String>>error(
                new DemoFailureException(
                    "Simulated stream dependency failure"
                )
            )
        );
    }
}

// Exception dùng nội bộ ví dụ, không phải public class trong file này.
final class DemoFailureException extends RuntimeException {
    DemoFailureException(String message) {
        super(message);
    }
}
```

**Giải thích nguồn:**

1. `earlyError()` trả một `Mono.error` **trước khi có onNext**. WebFlux/`@ExceptionHandler` có cơ hội xây HTTP error response đúng nghĩa.
2. `eventsThenFailure()` phát `ServerSentEvent` đầu tiên, sau đó phát `onError`. `delayElement` giúp minh họa trình tự nhưng **không là bảo đảm tuyệt đối về thời điểm network flush**; nó không được dùng để chứng minh `isCommitted()`.
3. `handledStream()` đặt `onErrorResume` **trước khi Flux đến body writer**, biến `DemoFailureException` thành một event cuối có tên `app-error` với data là **mã lỗi không nhạy cảm**. Response vẫn là SSE; HTTP status của một stream đã bắt đầu vẫn là 200.
4. `unhandledStream()` cố tình để `onError` lan ra. Sau event đầu, server có thể đã commit; trong trường hợp này handler HTTP không thể biến thành JSON 500 sạch. Cách kết thúc TCP/HTTP2 cụ thể phụ thuộc runtime/buffering và **không phải một giao thức ứng dụng ổn định**.
5. Trong ứng dụng thực, lỗi từ data source là `TimeoutException`, `WebClientResponseException`, lỗi database, lỗi serialize hoặc quyền; dùng mapping cụ thể thay vì `onErrorResume(Throwable.class)` mặc định cho mọi lỗi.
6. Nếu lỗi là **security denial**, tốt nhất là kiểm quyền trước khi phát item đầu, không đợi đến khi stream đã lộ nội dung.

### 6.5 EarlyErrorAdvice.java: xử lý khi body chưa bắt đầu

`src/main/java/com/example/streamfailures/EarlyErrorAdvice.java`:

```java
package com.example.streamfailures;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class EarlyErrorAdvice {

    @ExceptionHandler(DemoFailureException.class)
    public ResponseEntity<ProblemDetail> handle(DemoFailureException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.SERVICE_UNAVAILABLE
        );
        problem.setTitle("Dependency unavailable");
        problem.setDetail("The request cannot be completed.");

        return ResponseEntity.status(
            HttpStatus.SERVICE_UNAVAILABLE
        ).body(problem);
    }
}
```

Đây là **class đầy đủ** theo Spring Framework 6.x. `ProblemDetail` là kiểu chuẩn cho error response theo RFC 9457. Nó tạo **503 Service Unavailable** với thông tin đã được lọc, không trả ra `ex.getMessage()` từ downstream vì exception message có thể chứa password/token/query/database nội bộ.

**Không suy luận quá mức:** Advice này xử lý `DemoFailureException` khi WebFlux còn có thể tạo error response, ví dụ `/api/early-error`. Nó **không đảm bảo** có thể gửi một `ProblemDetail` sau khi SSE body đã được commit. Trong trường hợp đó, exception handler có thể không được chọn hoặc không thể viết error body như dự kiến.

### 6.6 ResponseAuditWebFilter.java: quan sát commit và lỗi

Một WebFilter có thể ghi lại trạng thái response khi lỗi xảy ra, đồng thời đăng ký callback trước commit. Quan trọng là **quan sát, không tự sửa response muộn**.

`src/main/java/com/example/streamfailures/ResponseAuditWebFilter.java`:

```java
package com.example.streamfailures;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class ResponseAuditWebFilter implements WebFilter {

    private static final Logger log =
        LoggerFactory.getLogger(ResponseAuditWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        ServerHttpResponse response = exchange.getResponse();
        String requestId = exchange.getRequest().getId();

        response.beforeCommit(() ->
            Mono.fromRunnable(() ->
                log.debug(
                    "Committing requestId={} status={}",
                    requestId, response.getStatusCode()
                )
            )
        );

        return chain.filter(exchange)
            .doOnError(error ->
                log.warn(
                    "Request failed requestId={} committed={} type={}",
                    requestId,
                    response.isCommitted(),
                    error.getClass().getSimpleName()
                )
            )
            .doFinally(signal ->
                log.debug(
                    "Finished requestId={} signal={}",
                    requestId, signal
                )
            );
    }
}
```

**Phạm vi logger:**

- `beforeCommit` chạy trước khi response commit; dùng để quan sát thời điểm, **không phải late error hook**.
- `doOnError` quan sát lỗi mà filter thực sự nhìn thấy; tùy vị trí WebFilter và exception handlers, không phải mọi lỗi application đều lan tới logger này.
- `doFinally` nhận `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL` (và các trạng thái Reactor khác nếu có) để hỗ trợ metrics. Nó không tự ghi thêm dữ liệu.
- Không log `Authorization`, body, exception message có thể chứa PII/secret. `requestId` do server tạo phù hợp để đối chiếu log hơn việc tin một header tùy ý từ client; nếu dùng trace ID phải kiểm soát kích thước/nguồn.
- WebFilter **không được gọi `subscribe()`** để gửi body mới, không tự bắt toàn bộ `onError` và trả empty như thể request thành công.

## 7. Kiểm thử publisher thuần: sự khác nhau giữa xử lý và không xử lý

Bài test đầu không cần Spring application context. Nó kiểm tra **tín hiệu Reactor** mà controller tạo ra, không dự đoán HTTP status của một kết nối đã bị cắt.

Tạo `src/test/java/com/example/streamfailures/StreamErrorPublisherTest.java`:

```java
package com.example.streamfailures;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;
import reactor.test.StepVerifier;

class StreamErrorPublisherTest {

    private final ErrorDemoController controller =
        new ErrorDemoController();

    @Test
    void handledStreamTurnsErrorIntoLastApplicationEvent() {
        StepVerifier.create(controller.handledStream())
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("item");
                assertThat(event.data()).isEqualTo("first");
                assertThat(event.id()).isEqualTo("1");
            })
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("app-error");
                assertThat(event.data()).isEqualTo(
                    "DEPENDENCY_UNAVAILABLE");
            })
            .verifyComplete();
    }

    @Test
    void unhandledStreamEmitsItemThenErrorSignal() {
        StepVerifier.create(controller.unhandledStream())
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("item");
                assertThat(event.data()).isEqualTo("first");
            })
            .expectError(DemoFailureException.class)
            .verify();
    }

    @Test
    void earlyFailureHasErrorWithoutBodyValue() {
        StepVerifier.create(controller.earlyError())
            .expectError(DemoFailureException.class)
            .verify();
    }
}
```

Kết quả **kỳ vọng**:

| Test | Chuỗi tín hiệu |
| --- | --- |
| `handledStreamTurnsErrorIntoLastApplicationEvent` | `onNext(item)` → `onNext(app-error)` → `onComplete` |
| `unhandledStreamEmitsItemThenErrorSignal` | `onNext(item)` → `onError(DemoFailureException)` |
| `earlyFailureHasErrorWithoutBodyValue` | `onError(DemoFailureException)` trước mọi `onNext` |

**Không nhầm phạm vi test:** Publisher test xác minh thứ tự signal, **không chứng minh event đầu đã flush trên socket** hay status đã committed. Điều đó đòi hỏi HTTP integration test và có thể cần công cụ mạng cụ thể để quan sát timing.

Chạy:

```bash
./gradlew test --tests '*StreamErrorPublisherTest'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*StreamErrorPublisherTest'
```

Không có stdout bắt buộc ngoài kết quả Gradle/JUnit do runtime tạo. Các kết quả nêu trên là assertions được thiết kế từ source, **chưa phải kết quả build đã thực thi tại đây**.

## 8. Kiểm thử HTTP: 401 trước khi stream, 503 trước body và 200 với app-error event

Tạo `src/test/java/com/example/streamfailures/StreamErrorHttpTest.java`:

```java
package com.example.streamfailures;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StreamErrorHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingWorksWithoutAuthentication() {
        client.get()
            .uri("/public/ping")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void noCredentialIsRejectedBeforeStreamStarts() {
        client.get()
            .uri("/stream/handled")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void earlyErrorCanProduceAReal503ProblemResponse() {
        client.get()
            .uri("/api/early-error")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
            .expectBody()
            .jsonPath("$.title").isEqualTo("Dependency unavailable");
    }

    @Test
    void handledSseKeepsHttp200AndSendsAppErrorEvent() {
        Flux<ServerSentEvent<String>> events = client.get()
            .uri("/stream/handled")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .returnResult(
                new ParameterizedTypeReference<
                    ServerSentEvent<String>>() {}
            )
            .getResponseBody();

        StepVerifier.create(events)
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("item");
                assertThat(event.data()).isEqualTo("first");
            })
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("app-error");
                assertThat(event.data()).isEqualTo(
                    "DEPENDENCY_UNAVAILABLE");
            })
            .verifyComplete();
    }
}
```

Test dùng Spring Boot **HTTP server thật trên random port**, đi qua Spring Security filter chain thay vì bind trực tiếp controller. `WebTestClient` nhận SSE bằng `ServerSentEvent<String>` rồi `StepVerifier` kiểm cả event name và data.

**Không thêm assertion kiểu `/stream/unhandled` phải trả 500.** Với publisher có lỗi sau event đầu, status có thể đã là 200 và hành vi transport phụ thuộc buffering/runtime. Một integration test cụ thể có thể quan sát stream lỗi hoặc connection close, nhưng **không có một kết quả status 500 phổ quát** để ràng buộc mọi container/client.

Các kết quả dự kiến:

- `GET /public/ping` → 200.
- `GET /stream/handled` không credential → **401** trước body vì Spring Security yêu cầu authenticated.
- `GET /api/early-error` với Basic hợp lệ → **503** và RFC 9457 `ProblemDetail` vì lỗi được ánh xạ trước khi response bắt đầu.
- `GET /stream/handled` với Basic hợp lệ → HTTP **200** và hai events `item` / `app-error` vì ứng dụng đã chủ động định nghĩa error frame.

Chạy:

```bash
./gradlew test --tests '*StreamErrorHttpTest'
```

Mã Java đã được rà soát để làm ví dụ thống nhất với Spring Boot/Spring Security 6.x, nhưng **cần chạy Gradle trong project để xác nhận thực tế**, đặc biệt với codec và behavior của HTTP test runtime bạn đang sử dụng.

### 8.1 Tại sao HTTP 200 vẫn là “có lỗi”?

Ở SSE, HTTP status mô tả **việc bắt đầu và chấp nhận HTTP response**. Một kết nối SSE có thể tồn tại hàng phút hoặc giờ, gồm nhiều sự kiện. Lỗi của nguồn dữ liệu phút thứ năm không thể quay ngược thời gian để đổi status gửi ở phút đầu.

Vì vậy protocol application cần một trong hai quy ước:

- `event: app-error`, `data: DEPENDENCY_UNAVAILABLE` rồi đóng stream có chủ đích;
- Hoặc kết thúc kết nối; client xử lý reconnect/resume theo `id`, checkpoint và chính sách retry.

Nếu cần báo lỗi ở cấp **toàn bộ request** với HTTP status 503, phải kiểm tra điều kiện quan trọng **trước khi mở luồng**, ví dụ xác thực, authorization, kiểm tra tồn tại nguồn dữ liệu, xác nhận upstream đã sẵn sàng. Không thể luôn biết mọi lỗi tương lai của một stream dài trước lúc trả status.

## 9. Chạy thử bằng curl và quan sát trực tiếp

Khởi chạy:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu dùng port mặc định, các URL ở `http://localhost:8080`. Chỉ dùng HTTP trên localhost với mật khẩu demo; khi triển khai thực tế phải dùng **HTTPS/TLS**.

### 9.1 Lỗi trước commit

```bash
curl -i http://localhost:8080/api/early-error
curl -i -u reader http://localhost:8080/api/early-error
```

Với lệnh `-u reader`, curl hỏi password tương tác. Nhập `reader-demo-password`.

- Không có credential → dự kiến **401** Basic challenge.
- Có credential đúng → dự kiến **503** và body ProblemDetail JSON. Header content-type thường là `application/problem+json`; các header khác tùy server.

Dạng body kỳ vọng sau khi có Basic credential:

```json
{
  "type": "about:blank",
  "title": "Dependency unavailable",
  "status": 503,
  "detail": "The request cannot be completed."
}
```

Đây là **minh họa các field chính**, không phải raw response byte-for-byte; framework có thể thêm `instance` hoặc thay thứ tự property. Không dùng regex cố định với mọi trường để kết luận test pass.

### 9.2 Lỗi sau khi SSE đã bắt đầu

```bash
curl -i -N -u reader http://localhost:8080/stream/handled
```

`-N` tắt output buffering của curl để quan sát event stream dễ hơn. Nhập password demo. Kỳ vọng **nội dung SSE có dạng**:

```text
id:1
event:item
data:first

event:app-error
data:DEPENDENCY_UNAVAILABLE

```

Khoảng trắng sau dấu hai chấm hoặc thứ tự metadata có thể khác tùy encoder; đừng phụ thuộc raw bytes khi test, hãy decode thành `ServerSentEvent`. HTTP status thường là **200**, vì đây là luồng SSE được chấp nhận và event lỗi do ứng dụng phát **trong body**.

Đối chiếu endpoint không xử lý:

```bash
curl -i -N -u reader http://localhost:8080/stream/unhandled
```

Nó có cùng event đầu rồi publisher phát `onError`. **Không dự đoán cố định status hoặc mã lỗi curl**: nếu HTTP response đã commit, không thể làm lại HTTP status; transport có thể bị đóng/reset và client nhận lỗi hoặc chỉ thấy stream thiếu kết thúc bình thường. Hãy kiểm tra logs/metrics và quan sát khác biệt giữa event app-error có chủ đích với transport failure.

## 10. SSE event lỗi nên chứa những gì?

Một event có cấu trúc có thể có contract như sau:

```text
event: app-error
data: {"code":"DEPENDENCY_UNAVAILABLE","retryable":true,"requestId":"..."}
```

Đây là **ví dụ giao thức ứng dụng**, không phải format bắt buộc của Spring Security hay một HTTP error response. Nếu dùng JSON trong `data`, serialize dữ liệu đúng codec (ví dụ Jackson), không tự nối chuỗi có ký tự đặc biệt mà không escape.

Đề xuất các trường:

| Trường | Vai trò | Cần tránh |
| --- | --- | --- |
| `code` | Mã lỗi ổn định cho client quyết định UI/retry | Tên exception nội bộ/SQL/code stack trace |
| `retryable` | Client có thể thử lại hay không theo contract | Đánh dấu mọi lỗi là retryable |
| `requestId` / `traceId` | Phục vụ hỗ trợ và correlation | Dùng dữ liệu nhận dạng nhạy cảm hoặc token |
| `lastEventId` | Hỗ trợ resume nếu server có khả năng phát lại | Hứa replay khi server không lưu checkpoint |
| `message` | Thông báo thân thiện người dùng | Lộ thông tin account, tenant, dữ liệu bí mật |
| `terminal` | Client biết lỗi là cuối stream hay tiếp tục được | Mơ hồ khiến client treo vô hạn |

**Chỉ phát sự kiện lỗi nếu còn có thể ghi body** và việc phát thông báo không vi phạm security policy. Nếu đã xảy ra lỗi giao thức/serializer và không còn ghi được `text/event-stream` hợp lệ, việc cố “chèn JSON error” có thể làm hỏng stream hơn nữa.

### 10.1 EventSource client không tự hiểu app-error

Ở browser, JavaScript `EventSource` nhận các event có tên custom qua `addEventListener`. Ví dụ:

```javascript
const source = new EventSource("/stream/handled");

source.addEventListener("item", (event) => {
  console.log("item:", event.data);
});

source.addEventListener("app-error", (event) => {
  console.warn("Application error:", event.data);
  source.close();
});

source.onerror = () => {
  console.warn("Transport failed or disconnected");
};
```

**Đây là snippet client**, cần môi trường browser và endpoint có cơ chế auth/cookie phù hợp. `EventSource` không cho bạn tùy ý đặt Basic `Authorization` header bằng API chuẩn; ví dụ Java server dùng Basic nên để thử trực tiếp hãy dùng curl/WebTestClient, hoặc thiết kế auth browser qua cookie/session/token flow phù hợp. Đừng đưa credential vào query string để né giới hạn của EventSource.

`app-error` là một event do server định nghĩa, **khác** `EventSource.onerror` xảy ra khi transport có vấn đề. Nếu bạn chọn event name `error` có thể dễ gây nhầm lẫn với error event của browser; bài dùng `app-error` cho rõ.

## 11. Với NDJSON, JSON array, file download và WebSocket thì sao?

Không phải định dạng streaming nào cũng cho phép chèn event lỗi có cấu trúc:

### 11.1 SSE (text/event-stream)

SSE thiết kế để có nhiều event độc lập, nên dễ đưa vào **in-band event** báo lỗi rồi kết thúc. Client phải parse event type và xử lý. HTTP status **không** phản ánh mọi event domain lỗi về sau.

### 11.2 NDJSON (application/x-ndjson)

NDJSON cho phép mỗi dòng là một JSON object độc lập. Nếu **contract được định nghĩa trước**, bạn có thể trả:

```text
{"type":"data","id":"1","value":"first"}
{"type":"error","code":"DEPENDENCY_UNAVAILABLE"}
```

Nhưng client phải biết phân biệt `type=data` và `type=error`. Nếu client nghĩ mọi dòng là record nghiệp vụ, một dòng lỗi có thể làm parse sai hoặc làm tăng dữ liệu đếm nhầm. Không thay đổi contract giữa chừng mà không versioning/test.

### 11.3 JSON array đang ghi dở

Với `application/json` dạng array streaming:

```text
[{"id":1},{"id":2},
```

nếu lỗi xuất hiện trước ký tự đóng `]`, body có thể là **JSON không hợp lệ**. Không thể đơn giản viết `{"status":500}` vào giữa array rồi kỳ vọng client hiểu; cũng không thể quay lại đầu response để đổi content-type/status. Với yêu cầu **all-or-nothing**, hãy gom/validate kết quả trước khi commit (chú ý giới hạn bộ nhớ), hoặc dùng NDJSON/SSE với contract rõ thay vì một array lớn.

### 11.4 File download / video stream

Khi đã gửi một phần file, không thể thay thành JSON 500. Client cần phát hiện incomplete transfer bằng content length, checksum, range/resume, storage metadata hoặc transport error. Không trả một file thiếu bytes nhưng vẫn đánh dấu “download thành công” trong nghiệp vụ.

### 11.5 WebSocket

Sau HTTP Upgrade, WebSocket không còn là response HTTP thông thường. Lỗi ứng dụng nên được biểu diễn bằng message/close frame theo protocol đã thiết kế, rồi dừng kết nối; không thể gửi HTTP 500 như một response mới sau upgrade. Kiểm quyền **trước handshake** và khi cần trong session; không phát message nhạy cảm sau khi quyền đã bị thu hồi.

### 11.6 GraphQL subscriptions và gRPC streaming

Những giao thức này có cách riêng để báo lỗi/termination (GraphQL payload/error, gRPC status/trailers) và phải tuân theo **protocol contract** của chúng. Không suy diễn quy tắc “SSE event app-error” cho mọi streaming framework.

## 12. Phân quyền phải đến trước dữ liệu nhạy cảm

Đây là liên hệ trực tiếp giữa chủ đề lỗi muộn với **Spring Security reactive**.

### 12.1 Đúng: pre-authorization trước khi phát Flux

```java
public Flux<DomainEvent> streamForUser(String userId) {
    return permissionService.canSubscribe(userId)
        .flatMapMany(allowed -> {
            if (!allowed) {
                return Flux.error(
                    new AccessDeniedException("Not permitted"));
            }
            return eventRepository.findEventsForUser(userId);
        });
}
```

Đây là **method snippet** trong service có các dependency `permissionService`, `eventRepository` và import `AccessDeniedException`, `Flux`. Điều quan trọng là `canSubscribe` được kiểm tra trước khi `eventRepository` phát event đầu tiên. Nếu `canSubscribe` trả `Mono.empty()`, đoạn trên không tự tạo `false`; production nên làm rõ policy bằng `defaultIfEmpty(false)` và xử lý lỗi theo hướng fail closed.

**Nếu permission check trả false và chưa có body**, WebFlux security có cơ hội trả 403 qua cơ chế phù hợp. Nếu cùng một response đã phát dữ liệu, không thể sửa thành 403 và **dữ liệu đã gửi không thu hồi được**.

### 12.2 Đúng hơn: decision fail closed rõ ràng

```java
public Flux<DomainEvent> streamForUser(String userId) {
    return permissionService.canSubscribe(userId)
        .defaultIfEmpty(false)
        .flatMapMany(allowed -> {
            if (!allowed) {
                return Flux.error(
                    new AccessDeniedException("Not permitted"));
            }
            return eventRepository.findEventsForUser(userId);
        });
}
```

Đây vẫn là snippet, không phải Java file chạy độc lập. Với stream dài, phải quyết định **thời điểm quyền được kiểm lại** (ví dụ token/session expiry, quyền theo tài nguyên, tenant membership). Kiểm quyền ban đầu không tự động bảo đảm tất cả sự kiện phát ra trong một giờ sau vẫn được phép nếu chính sách thay đổi.

### 12.3 Sai: gửi trước rồi mới kiểm quyền

```java
return sensitiveDataFlux
    .doOnNext(data -> {
        // Kiểm quyền sau khi data đã được cho đi là QUÁ MUỘN.
    });
```

Đây là **pseudocode cảnh báo**. Không dùng `doOnNext` như enforcement mechanism nếu nó chỉ ghi log/check sau khi item đã tiến gần tới writer. Phải sắp xếp permission check **trước khi phát item** hoặc tại cổng phân quyền giữa nguồn dữ liệu và output, không để dữ liệu sensitive đi trước policy.

### 12.4 Không bắt security exception thành “data thành công”

Ví dụ nguy hiểm:

```java
return protectedEvents
    .onErrorResume(AccessDeniedException.class, ex ->
        Flux.just(ServerSentEvent.<String>builder()
            .event("item")
            .data("default-public-data")
            .build())
    );
```

Đây là **snippet cảnh báo**, cần có biến `protectedEvents`. Nếu upstream báo access denied, việc tự động trả event `item` như thành công có thể che lỗi authorization và làm client nghĩ dữ liệu được cấp phép. Nếu cần kết thúc stream do quyền bị thu hồi, dừng nguồn và phát thông báo từ chối tối giản **chỉ khi contract và bảo mật cho phép**; không tiếp tục trả dữ liệu giả dạng thành công.

## 13. Retry, timeout và cancellation sau khi đã có event đầu

### 13.1 retryWhen có thể phát trùng dữ liệu

`retryWhen(...)` **resubscribe nguồn** khi có lỗi. Nếu nguồn đã phát ba sự kiện và phản hồi đã gửi chúng, một lần retry có thể phát lại ba event đó hoặc tạo kết quả khác. Client có thể nhận:

```text
event id=1
event id=2
event id=3
upstream fails
retry:
event id=1  <-- có thể trùng
event id=2  <-- có thể trùng
event id=3  <-- có thể trùng
event id=4
```

Khi cần retry trong stream, hãy định nghĩa event IDs, checkpoint/resume, idempotency hoặc retry ở **từng truy vấn chưa phát dữ liệu**. Không đặt retry toàn stream chỉ để “không báo lỗi”, nhất là với event liên quan tiền/giao dịch/quyền.

### 13.2 timeout không tự trả 504 sau commit

`Flux.timeout(Duration...)` có thể phát `TimeoutException` khi không có event đủ lâu. Nếu response chưa commit, error handler có thể chọn một HTTP status phù hợp. Nếu đang có stream 200, timeout là **một stream error**, không thể tự động thành HTTP 504. Có thể chuyển timeout thành `app-error` có code `UPSTREAM_TIMEOUT` và kết thúc, hoặc đóng kết nối để client reconnect theo policy.

### 13.3 Client hủy request

Khi browser chuyển trang, người dùng bấm “Stop”, proxy mất kết nối hoặc client hủy subscription, reactive pipeline có thể nhận **CANCEL**. `doFinally(signal -> ...)` có thể ghi metrics. Không cố phát “lỗi HTTP” cho client đã đóng kết nối.

Nếu upstream tạo tài nguyên (DB cursor, SSE subscription, file stream), bảo đảm cleanup thông qua Reactor operators như `usingWhen` hoặc resource lifecycle được driver hỗ trợ. Không dựa vào `onComplete` làm cleanup duy nhất vì cancel/error cũng phải giải phóng tài nguyên.

### 13.4 Side effect đã xảy ra không tự được rollback

Nếu controller đã ghi bản ghi DB hoặc gửi message rồi response lỗi giữa chừng, việc đóng stream không tự hoàn tác side effect. Đừng hứa “request failed = transaction rolled back” khi transaction đã commit hoặc nằm ngoài phạm vi. Dùng transaction boundaries, outbox/idempotency keys và trạng thái nghiệp vụ riêng với trạng thái HTTP streaming.

## 14. ServerWebExchange, Reactor Context và xử lý exception

`ServerWebExchange` đại diện HTTP request/response ở WebFlux. `ReactiveSecurityContextHolder` đưa `SecurityContext` vào Reactor Context gắn với subscription. Không dùng `SecurityContextHolder.getContext()` theo `ThreadLocal` trong một `Flux` kéo dài qua nhiều thread rồi kỳ vọng luôn có principal đúng.

Các dạng lỗi phổ biến:

- `AuthenticationException` trước khi bắt đầu response: cơ chế Spring Security có thể tạo challenge (401) hoặc redirect login.
- `AccessDeniedException` do role/method security trước commit: có thể thành 403.
- `ResponseStatusException` trước commit: WebFlux handler có thể áp dụng HTTP status được chỉ định.
- Lỗi repository giữa stream: cần xử lý như một lỗi của dữ liệu streaming, không phải tự động dựng response HTTP lỗi mới.
- Lỗi transport hoặc serialization: rất có thể chỉ còn cách kết thúc connection và ghi logs.

Khi gọi `subscribe()` thủ công để chạy side effect ngoài stream, bạn tạo một subscription mới. Nó có thể **không kế thừa đúng Reactor SecurityContext**, không thuộc lifecycle request và không báo lỗi đúng kênh. Trả `Mono`/`Flux` về framework hoặc ghép publishers bằng `flatMap`/`then`/`concatMap`.

### 14.1 Lỗi thuộc security filter khác lỗi thuộc controller

HTTP Basic authentication có thể thất bại **trước khi controller chạy**. Vì vậy không nên dựa vào `@RestControllerAdvice` chuyên xử lý lỗi domain để tùy biến 401/403 của Spring Security. Muốn thay challenge/access-denied response, dùng `ServerHttpSecurity.exceptionHandling(...)` với `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler` tương ứng.

Với response đã bắt đầu, **ngay cả custom entry point/access denied handler** cũng không thể thay đổi status/headers đã commit. Đừng dùng chúng làm giải pháp “bắt mọi lỗi cuối stream”.

### 14.2 Chọn đúng handler cho thời điểm

| Muốn đạt | Nên làm |
| --- | --- |
| HTTP 400/404/500/503 JSON chính thức | Xác định và ánh xạ lỗi **trước khi commit**, dùng advice/error handler phù hợp |
| HTTP 401 vì thiếu/sai credentials | Để Spring Security authentication filter/entry point xử lý trước body |
| HTTP 403 vì quyền không đủ | Để authorization kiểm tra **trước khi phát dữ liệu** |
| SSE đã phát event rồi downstream lỗi | Định nghĩa app-error event **trong publisher** hoặc đóng stream |
| File download đang dở | Đóng/fail transport, cho client phát hiện incomplete file và resume nếu hỗ trợ |
| Không gửi thêm dữ liệu do quyền bị thu hồi | Cancel/terminate stream an toàn; không tiếp tục phát item nhạy cảm |
| Debug committed state | `isCommitted()`, structured logs, metrics, tracing, integration tests |
| Đảm bảo all-or-nothing | Trì hoãn bắt đầu body cho tới khi điều kiện quan trọng đã hoàn tất, hoặc dùng workflow/job async |

## 15. Lỗi thường gặp khi “xử lý lỗi đã quá muộn”

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Luôn trả `ResponseEntity.status(500)` trong `onErrorResume` bất kể body đã gửi | Không thể đổi status/headers, có thể gây thêm lỗi ghi response | Tách lỗi precommit và stream error |
| Nghĩ `@RestControllerAdvice` bảo đảm đổi 200 thành 500 sau event đầu | Handler không có khả năng rollback HTTP response | Dùng in-band event hoặc stream termination |
| Tạo `ProblemDetail` JSON giữa SSE đang ghi | Phá định dạng `text/event-stream` | Phát SSE event có code an toàn nếu contract cho phép |
| Coi SSE `app-error` là HTTP error status | Client bỏ sót lỗi vì chỉ nhìn response 200 | Client phải parse event type |
| Chỉ `doOnError(log)` rồi coi như đã recover | Publisher vẫn onError, stream vẫn fail | Dùng `onErrorResume` có chọn lọc nếu có recovery hợp lệ |
| Bắt mọi exception thành event `item` mặc định | Che security failure hoặc lỗi nghiêm trọng | Map lỗi cụ thể; fail closed |
| Gọi `block()` trong WebFlux event-loop | Có thể treo/chặn thread, mất reactive context | Dùng reactive operators |
| Gọi `subscribe()`/ghi body lần hai trong error handler | Hai subscriptions/writers tranh response | Giữ publisher do WebFlux quản lý |
| Cố ghi `WWW-Authenticate` khi stream đang trả 200 | Không thể gửi challenge hợp lệ sau commit | Authenticate trước khi mở stream |
| Phát dữ liệu trước khi kiểm quyền | Đã rò rỉ dữ liệu, không thể thu hồi | Authorize trước event đầu và revalidate phù hợp |
| Dùng `retryWhen` cho toàn stream không có checkpoint | Client nhận event trùng | Dùng ID/resume/idempotency |
| Không test cancel/timeout | Rò rỉ subscription/resource | Có cleanup on cancel/error |
| Tin `isCommitted() == false` bảo đảm chưa có ai đang commit | Race với async tasks | Để framework quản lý writers, kiểm return của setStatusCode |
| Chỉ xem status 200 để kết luận stream thành công | Luồng có thể kết thúc sớm/lỗi domain | Quan sát completion, event code và integrity |
| Ghi exception message vào event lỗi | Lộ SQL path, URL nội bộ, credential | Dùng error code công khai và trace ID an toàn |
| Mong proxy flush mọi event ngay | Buffering làm client nhận trễ | Cấu hình/kiểm thử reverse proxy theo giao thức |
| Tưởng 403 sau POST luôn do authorization | CSRF có thể chặn trước method security | Kiểm tra CSRF + policy theo thứ tự |
| Không phân biệt domain và transport error | Client reconnect sai hoặc bỏ sót lỗi nghiệp vụ | Tài liệu hóa event protocol và reconnect policy |

## 16. Thực hành nâng cao: xử lý lỗi trước khi mở stream

Giả sử một SSE stream cần lấy cấu hình, xác thực scope và kiểm tra dependency trước khi trả bất kỳ item nào.

**Gợi ý thiết kế (method snippet):**

```java
public Flux<ServerSentEvent<String>> openStream(String resourceId) {
    return accessPolicy.canStream(resourceId)
        .defaultIfEmpty(false)
        .flatMapMany(allowed -> {
            if (!allowed) {
                return Flux.error(new AccessDeniedException(
                    "Stream access denied"
                ));
            }

            return dependencyService.checkReady(resourceId)
                .thenMany(eventSource.watch(resourceId));
        });
}
```

Đây là **snippet kiến trúc**, cần có `accessPolicy`, `dependencyService` và `eventSource` thật; các class/exception được dùng phải import phù hợp. Lợi ích:

1. Nếu không đủ quyền, `Flux` phát error trước khi có event data; handler/entry point có cơ hội trả status hợp lệ.
2. Nếu dependency không sẵn sàng, có cơ hội ánh xạ sang 503 **trước khi mở SSE**.
3. Khi điều kiện đầu vào ổn, data publisher mới chạy.
4. Nếu dependency lỗi **sau một thời gian watch**, vẫn phải xử lý lỗi stream như các mục trước; preflight không thể bảo đảm nguồn không bao giờ lỗi.

**Lưu ý:** `checkReady` chỉ là readiness check có khả năng race: dependency có thể chết ngay sau khi check. Nếu yêu cầu nguyên tử, cần protocol/workflow hạ tầng đảm bảo thay vì chỉ ping trước khi stream.

### 16.1 Khi nào buffering toàn bộ response là hợp lý?

Nếu endpoint phải trả một JSON object/array **chỉ khi có đủ dữ liệu**, bạn có thể dùng `collectList()` hoặc tổng hợp kết quả trong giới hạn bộ nhớ rồi viết body sau khi toàn bộ source hoàn tất:

```java
return reportRepository.fetchRows(query)
    .collectList()
    .map(rows -> new ReportResponse(rows));
```

Đây là method snippet. Nó trì hoãn việc ghi body cho đến khi có toàn bộ danh sách, nên lỗi nguồn trước khi hoàn thành có thể được ánh xạ thành error status trước commit. **Đổi lại**, tốn bộ nhớ, latency và mất ưu điểm streaming; không dùng cho tập dữ liệu vô hạn hoặc lớn không có giới hạn.

Nếu cần xử lý dữ liệu rất lớn, mô hình **asynchronous job** thường tốt hơn: POST tạo job → status endpoint cho tiến độ/kết quả → tải file khi đã hoàn chỉnh. Khi đó lỗi có thể được biểu diễn thành trạng thái job thay vì cố sửa status của một stream đã bắt đầu.

## 17. Checklist kiểm thử và quan sát production

### 17.1 Trước khi response có body

- [ ] Kiểm tra missing credentials/invalid credentials được Spring Security trả 401 hoặc login redirect đúng cơ chế.
- [ ] Kiểm tra authenticated user không đủ role/scope nhận 403 **trước khi dữ liệu nhạy cảm phát ra**.
- [ ] Kiểm tra lỗi validation, dependency và business exception trước commit được ánh xạ đúng 4xx/5xx.
- [ ] Kiểm tra `ProblemDetail` không chứa exception message nội bộ, secret hoặc thông tin tenant không được tiết lộ.

### 17.2 Sau khi stream có item đầu

- [ ] Test stream xử lý lỗi domain phát một event `app-error` **theo contract**, rồi hoàn tất hoặc dừng theo thiết kế.
- [ ] Test stream không xử lý lỗi phát `onError` và **không** kỳ vọng HTTP status 500 cố định.
- [ ] Test SSE client không chỉ nhìn status 200 mà còn hiểu event type, error code, completion/reconnect.
- [ ] Test client cancellation và resource cleanup.
- [ ] Test timeout, retry, event ID/resume, tránh phát trùng dữ liệu khi resubscribe.
- [ ] Kiểm tra permission revalidation cho stream dài và không gửi event sau khi quyền bị thu hồi.
- [ ] Với JSON array/file download, kiểm tra incomplete payload detection và integrity.
- [ ] Test với reverse proxy/load balancer và cấu hình buffering, timeouts phù hợp.

### 17.3 Log và metrics

- [ ] Ghi request ID/trace ID, route, loại lỗi, `response.isCommitted()` và signal `COMPLETE/ERROR/CANCEL` khi có thể.
- [ ] Đếm riêng **HTTP errors trước commit**, **in-band domain error events** và **transport/stream failures**.
- [ ] Không chỉ dựa vào metric HTTP 5xx: lỗi của một stream 200 cần thêm metric nghiệp vụ.
- [ ] Tránh log password, access token, cookies, raw response body hoặc SQL/stack trace vào event trả cho client.
- [ ] Có alert cho số stream kết thúc bất thường và tỷ lệ reconnect bất thường.
- [ ] Thử nghiệm đóng kết nối giữa chừng với nhiều loại client và HTTP/1.1/HTTP2 khi sản phẩm hỗ trợ.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `onErrorResume` trong một SSE publisher vẫn có thể hoạt động sau event đầu dù HTTP status không đổi?

**Trả lời:** Nó thay đổi **tín hiệu data của publisher trước body writer**, không thử tạo response HTTP mới. Nếu formatter/transport vẫn có thể viết SSE, nó có thể phát `app-error` và hoàn tất, trong khi status đã commit vẫn giữ nguyên.

**Câu 2.** `ServerHttpResponse.isCommitted()` có chứng minh event đầu đã được người dùng nhìn thấy trên màn hình không?

**Trả lời:** Không. Nó phản ánh trạng thái commit ở phía reactive server; proxy, socket và client có thể buffer. Nhưng sau commit không thể sửa status/headers.

**Câu 3.** Nếu `WebFluxResponseStatusExceptionHandler` nhận `ResponseStatusException(500)` sau khi response đã commit, có đổi status được không?

**Trả lời:** Không. Javadoc của handler nói lỗi vẫn unresolved và được propagate khi response committed.

**Câu 4.** GET protected SSE không credential có nên mở stream rồi gửi event `app-error` không?

**Trả lời:** Không theo mô hình Basic trong bài. Spring Security cần xác thực **trước** khi cho phát body; thiếu credential nhận 401/challenge. Không mở luồng nhạy cảm rồi mới phát hiện người gọi chưa có quyền.

**Câu 5.** HTTP 200 SSE và event `app-error` có mâu thuẫn không?

**Trả lời:** Không. HTTP 200 mô tả response được mở thành công; `app-error` là lỗi phát sinh trong quá trình truyền dữ liệu do giao thức ứng dụng định nghĩa.

**Câu 6.** Có thể viết một JSON ProblemDetail vào cuối một JSON array đã gửi dở không?

**Trả lời:** Không theo contract JSON array. Body sẽ có nguy cơ invalid JSON. Nếu cần truyền lỗi giữa dòng, dùng SSE/NDJSON có schema riêng hoặc chuyển sang job/buffered response.

**Câu 7.** Tại sao không nên dùng `retryWhen` toàn bộ stream sau lỗi muộn?

**Trả lời:** Retry có thể resubscribe nguồn và phát lại event đã gửi, dẫn đến duplicate. Dùng event ID, resume/checkpoint, idempotency hoặc retry ở nguồn chưa phát dữ liệu.

**Câu 8.** Dùng `doOnError` ghi log rồi trả `Flux` có nghĩa đã recover?

**Trả lời:** Không. `doOnError` chỉ quan sát lỗi. Downstream vẫn nhận `onError` nếu không có operator như `onErrorResume` hợp lệ.

**Câu 9.** Nếu client đã hủy subscription, có nên cố gửi event lỗi cuối cùng không?

**Trả lời:** Không. Client có thể không còn đọc; thay vào đó cleanup resource và ghi metrics `CANCEL`.

**Câu 10.** Vì sao method security exception phát sinh sau khi đã gửi dữ liệu là lỗi thiết kế nghiêm trọng?

**Trả lời:** Dữ liệu đã phát không thu hồi được và không thể đổi status thành 403. Phải đặt authorization **trước event đầu**, đồng thời revalidate khi stream kéo dài nếu policy yêu cầu.

## 19. Tổng kết

**Ba nguyên tắc phải thuộc:**

1. **Trước commit:** Xác thực, phân quyền, validate và mapping error càng sớm càng tốt; khi chưa có body, framework có thể phát 401/403/4xx/5xx phù hợp với HTTP.
2. **Sau commit:** Không thể tạo “response lỗi mới” bằng cách đổi status/headers. Nếu streaming protocol cho phép, **chủ động chuyển lỗi thành sự kiện/bản ghi trong luồng trước body writer**; nếu không, kết thúc stream/connection và ghi nhận lỗi.
3. **An toàn dữ liệu:** Không chờ đến sau event đầu mới xác nhận quyền. Với stream dài, có chính sách revalidation, cancellation, retry/idempotency và client-side error interpretation rõ.

Đối với Spring Security WebFlux, lỗi phân quyền ở đầu request vẫn là một vấn đề **HTTP authentication/authorization**. Một lỗi phát sinh bên trong `Flux` đã streaming lại là vấn đề **Reactive Streams và giao thức body**. Phân biệt hai ranh giới này giúp tránh việc hứa trả 500 sau khi client đã nhận 200, hoặc tệ hơn, để lộ dữ liệu trước khi phát hiện người dùng không có quyền.

### Tài liệu chính thức và chuẩn tham khảo

- [Spring Framework 6.2 — WebFluxResponseStatusExceptionHandler Javadoc: response committed thì error unresolved](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/handler/WebFluxResponseStatusExceptionHandler.html)
- [Spring Framework — ServerHttpResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html)
- [Spring Framework — WebFlux reactive core và WebExceptionHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux annotated controllers, return values/SSE](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — Error Responses và ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — ServerHttpSecurity.ExceptionHandlingSpec](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html)
- [Project Reactor — Error Handling Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
