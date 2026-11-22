# Cơ chế tiếp tục, kết thúc sớm và lan truyền lỗi trong chuỗi WebFilter

## Mục tiêu

Khi một request đi vào Spring WebFlux, nhiều `WebFilter` có thể chạy trước và sau WebHandler. Một filter có thể **chuyển request tới filter tiếp theo**, **kết thúc request ngay tại chỗ**, hoặc **để lỗi đi ngược về lớp xử lý bên ngoài**. Trong Spring Security Reactive, sự lựa chọn này ảnh hưởng trực tiếp tới xác thực, phân quyền, mã HTTP và khả năng kiểm soát lỗi.

Sau bài học, bạn có thể:

1. Giải thích chính xác `WebFilter.filter(ServerWebExchange, WebFilterChain)` và ý nghĩa của `Mono<Void>`.
2. Viết filter tiếp tục qua `return chain.filter(exchange)`, có hậu xử lý đúng cơ chế Reactor.
3. Viết nhánh chặn request bằng cách đặt status và `response.setComplete()` mà không gọi downstream.
4. Theo dõi `onComplete`, `onError`, `cancel`; phân biệt HTTP 403/500 với Reactor error signal.
5. Biết khi nào dùng `doOnError`, `onErrorMap`, `onErrorResume` và khi nào nên để Spring Security/WebFlux xử lý lỗi.
6. Tạo và kiểm thử một ví dụ WebFlux Java 17+ có đủ ba kịch bản: tiếp tục, kết thúc sớm và lỗi.

Bài tập trung vào **kiến trúc WebFilter** của Spring Security Reactive và Spring WebFlux; có đề cập integration với `SecurityWebFilterChain`. Ví dụ hướng tới Spring Boot 3.x, Spring Framework 6.x, Spring Security 6.x, Java 17+.

## 1. Hợp đồng của WebFilter và WebFilterChain

Hai chữ ký API chủ yếu:

```java
// Khai báo API rút gọn để đọc hiểu, không phải file cần tự tạo.
public interface WebFilter {
    Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
}

public interface WebFilterChain {
    Mono<Void> filter(ServerWebExchange exchange);
}
```

`ServerWebExchange` mô tả request và response của WebFlux. `WebFilterChain` đưa phần việc còn lại của request sang filter kế tiếp rồi tới WebHandler. `Mono<Void>` biểu diễn **khi nào quá trình request hoàn tất hoặc thất bại**; nó không chứa body của response. Controller có thể trả `Mono<String>` hay `Flux<T>`, nhưng filter dùng `Mono<Void>` để biểu diễn lifecycle.

Mô hình lồng nhau:

```text
Client
  |
  v
WebFilter A (bắt đầu)
  |
  +-- chain.filter(exchange) --> WebFilter B (bắt đầu)
                                  |
                                  +-- chain.filter(exchange)
                                  |       |
                                  |       v
                                  |    WebHandler / Controller
                                  |       |
                                  |       v
                                  |    publisher hoàn tất/lỗi/hủy
                                  |
                                  v
                              WebFilter B (hậu xử lý)
  |
  v
WebFilter A (hậu xử lý)
  |
  v
WebFlux hoàn tất response
```

Thứ tự đi vào thường từ ngoài vào trong; tín hiệu kết thúc được quan sát theo các operator của từng publisher, từ trong ra ngoài. Điều đó **không có nghĩa mọi đoạn mã chạy trên một thread cố định**. Reactor có thể chuyển lịch thực thi, còn Spring WebFlux quản lý subscription.

Spring Security Reactive bổ sung `WebFilterChainProxy` và một hoặc nhiều `SecurityWebFilterChain`. Một request đi qua global WebFilter chain của WebFlux và, nếu được áp dụng, đi vào các security filters trong `SecurityWebFilterChain`. Global `@Bean WebFilter` với `@Order` và filter do `ServerHttpSecurity` cấu hình là **hai tầng thứ tự khác nhau**.

## 2. Ba cách kết thúc một chuỗi Reactor

Với `Mono<Void>`, bạn phải phân biệt **tín hiệu Reactor** và **kết quả HTTP**.

| Tín hiệu | Điều gì xảy ra? | Liên hệ với HTTP |
|---|---|---|
| `onComplete` | Publisher đã hoàn tất bình thường | Response vẫn có thể là 200, 204, 302, 403, 429… |
| `onError(Throwable)` | Một lỗi chưa được xử lý thành công đi ra publisher | Cần error handler phù hợp để map sang HTTP, thường 5xx nếu lỗi ứng dụng |
| `cancel` | Subscription bị hủy, chẳng hạn client disconnect | Không bảo đảm có thể gửi HTTP response mới |

Chẳng hạn, bộ lọc cố ý trả `403` thông qua `setStatusCode(HttpStatus.FORBIDDEN)` và `setComplete()` có thể phát **onComplete**, vì filter đã tạo response 403 thành công. Một controller trả `Mono.error(new IllegalStateException(...))` có thể phát **onError**, sau đó error handler WebFlux chuyển thành HTTP 500.

`Mono<Void>` không phát một giá trị kiểu `Void`. Vì vậy `doOnNext(...)` không phù hợp để biết khi nào filter hoàn tất; dùng `doOnSuccess(...)` cho thành công, `doOnError(...)` cho lỗi và `doFinally(...)` để quan sát cả hoàn thành, lỗi, hủy.

## 3. Tiếp tục xử lý: trả về `chain.filter(exchange)`

Đây là kiểu filter đơn giản nhất:

```java
@Component
public class PassThroughFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        return chain.filter(exchange);
    }
}
```

Đây là class minh họa trong project WebFlux, cần import `org.springframework.stereotype.Component`, `org.springframework.web.server.WebFilter`, `ServerWebExchange`, `WebFilterChain` và `reactor.core.publisher.Mono`. Lệnh `chain.filter(exchange)` **ủy quyền** xử lý cho phần còn lại của chain, và chính publisher được return sẽ phản ánh kết cục toàn chuỗi.

### 3.1. Hành vi trước, sau và quan sát lỗi

Ví dụ minh họa phần thân `filter(...)` với logger `log` đã khai báo:

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange,
                         WebFilterChain chain) {
    String path = exchange.getRequest().getPath().value();

    return Mono.defer(() -> {
        log.info("BEFORE {}", path);

        return chain.filter(exchange)
            .doOnSuccess(ignored -> log.info("COMPLETE {}", path))
            .doOnError(error -> log.warn("ERROR {}: {}", path,
                error.getClass().getSimpleName()))
            .doFinally(signal -> log.info("FINALLY {}: {}", path, signal));
    });
}
```

- `Mono.defer(...)` tạo publisher cho từng lần subscribe và trì hoãn side effect tới lúc request thực sự được thực thi.
- `doOnSuccess(...)` chạy khi publisher downstream hoàn thành **bình thường**; đối với `Mono<Void>`, tham số callback có thể là `null`.
- `doOnError(...)` chỉ **quan sát lỗi**. Nó không tự thay lỗi, không tạo HTTP response và không bảo đảm error sẽ trở thành 500.
- `doFinally(...)` thấy `SignalType.ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`, hữu ích cho telemetry/cleanup nhẹ.

Sau khi `chain.filter(exchange)` thành công, muốn chạy bước khác thì dùng:

```java
return chain.filter(exchange)
    .then(Mono.fromRunnable(() -> metrics.countCompleted()));
```

Đây là đoạn bên trong filter có đối tượng `metrics` thích hợp; nếu downstream lỗi thì `then(...)` **không** thực thi publisher tiếp theo. Nếu muốn đếm cả lỗi và cancel, đo ở `doFinally` hoặc dùng signal-specific hooks.

### 3.2. Ba lỗi lập trình thường gặp

**Sai — tự subscribe và trả publisher không liên quan:**

```java
chain.filter(exchange).subscribe();
return Mono.empty();
```

Filter trên tạo một subscription khác, có thể làm framework tưởng request đã kết thúc trong khi downstream còn đang chạy. Lỗi, response write, cancellation và Reactor Context không còn theo vòng đời request chính.

**Đúng:**

```java
return chain.filter(exchange);
```

**Sai — tạo publisher nhưng bỏ nó:**

```java
chain.filter(exchange);
return exchange.getResponse().setComplete();
```

Chỉ tạo publisher từ `chain.filter` không có nghĩa phần việc bên trong đã được subscribe/thực thi. Nếu muốn tiếp tục thì phải **return** nó. Nếu muốn kết thúc sớm thì **không** gọi chain; đừng kết hợp hai cách theo mẫu trên.

**Sai — chặn event loop:**

```java
chain.filter(exchange).block();
return Mono.empty();
```

`block()` trong WebFilter của server reactive có thể làm nghẽn event-loop, gây lỗi blocking hoặc phá cấu trúc cancellation/context. Hãy compose bằng operator Reactor.

## 4. Kết thúc sớm: không gọi `chain.filter(exchange)`

Một filter có quyền từ chối request trước controller hoặc trả một response riêng. Ví dụ:

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange,
                         WebFilterChain chain) {
    if ("/blocked".equals(exchange.getRequest().getPath().value())) {
        exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange);
}
```

Đây là đoạn method minh họa, cần import `org.springframework.http.HttpStatus` và WebFlux API.

Khi path là `/blocked`, **không** gọi `chain.filter(exchange)`, nên các filter **phía sau** và WebHandler **không chạy**. Tuy vậy, filter **phía ngoài đã gọi vào filter này** vẫn nhận tín hiệu hoàn tất và có thể chạy `doOnSuccess`/`doFinally`.

```text
A: vào -> B: kiểm tra /blocked
             -> status = 403
             -> response.setComplete()
             -> KHÔNG gọi chain.filter
A: nhận onComplete (vẫn chạy hậu xử lý)
Client: HTTP 403, không có body từ controller
```

Điểm quan trọng: một HTTP 403 có thể là **thành công của quá trình tạo response**, không phải một `onError`.

### 4.1. `setComplete()` khác `Mono.empty()`

`ServerHttpResponse.setComplete()` biểu thị thao tác hoàn tất response do WebFlux quản lý. Với nhánh chặn, hãy quyết định status/headers trước khi gọi nó. Trả `Mono.empty()` ngay mà không ghi response hoặc đặt status dễ tạo kết quả HTTP gây hiểu lầm, vì framework không biết bạn muốn báo từ chối, rate limit hay thành công.

Một vài tình huống short-circuit:

- Rate limiting: đặt `429 Too Many Requests`, cân nhắc `Retry-After` phù hợp.
- Bảo trì tạm thời: đặt `503 Service Unavailable` và thông tin retry nếu có.
- Redirect: đặt status 3xx và `Location` tin cậy.
- Cache hit: tạo response hoàn chỉnh từ cache với header/content type phù hợp.
- Security từ chối quyền: **ưu tiên cơ chế Spring Security** (authorization, entry point, denied handler) để giữ policy thống nhất.

Không nên tự viết global WebFilter kiểm tra role bằng header user do client tự gửi. Mã 401/403 và kiểm soát danh tính thuộc authentication/authorization đã được xác minh.

### 4.2. HTTP response đã commit

Nếu response đã commit header hoặc gửi body, thay status không còn hiệu lực. `ServerHttpResponse.isCommitted()` giúp nhận diện trạng thái; `setStatusCode(...)` trả boolean cho biết thao tác đặt status có được chấp nhận. Cố sửa status ở `doFinally` thường quá muộn. Hãy chặn request **trước** khi downstream ghi response.

### 4.3. Vì sao `permitAll()` không phải short-circuit?

Rule của Spring Security:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public").permitAll()
    .anyExchange().authenticated()
)
```

`permitAll()` có nghĩa **bước phân quyền cho phép đi tiếp**, không tự sinh response hay bỏ qua controller. Nếu endpoint công khai trả 404 hoặc 500, `permitAll()` không biến nó thành 200. Nếu filter rate limit ở trước chặn request, policy `permitAll()` của security cũng không buộc được request đi tiếp.

## 5. Lỗi đi ngược qua filter như thế nào?

Giả sử controller trả publisher lỗi:

```java
@GetMapping("/failure")
public Mono<String> failure() {
    return Mono.error(new IllegalStateException("demo failure"));
}
```

Đoạn trên là method trong controller có `@RestController` và các import tương ứng. Nếu không có error handler phía trong chuyển lỗi thành response, `onError(IllegalStateException)` truyền ngược tới các filter đang bọc downstream:

```text
Outer WebFilter
  |
  v
Inner WebFilter
  |
  v
Controller -> Mono.error(IllegalStateException)
  |
  +-- error --> Inner.doOnError
                  |
                  +-- error --> Outer.doOnError
                                 |
                                 +--> error handling WebFlux
                                       |
                                       +--> HTTP 500 nếu response
                                            chưa commit
```

Lỗi chỉ truyền qua những đoạn publisher nằm **trong phạm vi** của operator đang quan sát. Nếu `@ExceptionHandler` hoặc `onErrorResume` phía trong đã tiêu thụ lỗi, outer filter có thể chỉ nhìn thấy onComplete. Vì vậy không được suy ra mọi filter đều phát log error chỉ vì HTTP trả 500.

### 5.1. Ba operator cần phân biệt

| Operator | Việc nó làm | Tín hiệu đi tiếp |
|---|---|---|
| `doOnError(error -> log...)` | Quan sát để log/metric | Vẫn là onError nếu callback không gây sự cố mới |
| `onErrorMap(error -> new DomainException(...))` | Chuyển lỗi thành lỗi khác | Vẫn onError với throwable mới |
| `onErrorResume(DomainException.class, e -> fallback)` | Thay error bằng publisher khác nếu khớp loại lỗi | Có thể onComplete khi fallback thành công |
| `doFinally(signal -> ...)` | Quan sát kết thúc, kể cả cancel | Không thay tín hiệu gốc |

Ví dụ minh họa adapter chuyển **một loại lỗi nghiệp vụ cụ thể** thành HTTP 503:

```java
// Exception nghiệp vụ riêng (tạo trong project, không trùng class framework).
class DependencyUnavailableException extends RuntimeException {
    DependencyUnavailableException(String message) {
        super(message);
    }
}

// Phương thức @Bean trong class @Configuration có imports phù hợp.
@Bean
WebFilter dependencyFailureAdapter() {
    return (exchange, chain) -> chain.filter(exchange)
        .onErrorResume(DependencyUnavailableException.class, error -> {
            if (exchange.getResponse().isCommitted()) {
                return Mono.error(error);
            }
            exchange.getResponse().setStatusCode(
                HttpStatus.SERVICE_UNAVAILABLE);
            return exchange.getResponse().setComplete();
        });
}
```

Đoạn trên là **mã minh họa theo phạm vi class**, không phải một file Java độc lập vì còn cần import và bố trí class. Lỗi phải phát ra từ pipeline bên trong filter này và chưa bị handler khác xử lý. Chỉ khi response chưa commit mới có thể đặt status 503. Các loại lỗi khác tiếp tục truyền lên, không bị biến thành 503.

**Không dùng fallback bắt mọi lỗi một cách tùy tiện:**

```java
return chain.filter(exchange)
    .onErrorResume(error -> Mono.empty());
```

Cách này có thể “nuốt” lỗi bảo mật và lỗi lập trình, che giấu sự cố, để client nhận response không phản ánh nguyên nhân. Chọn loại exception cụ thể, có chính sách response và logs, để những lỗi ngoài phạm vi đi tiếp.

### 5.2. Error signal khác exception ném từ code đồng bộ

Trong Reactor, lỗi sinh ra khi subscribe có thể xuất hiện qua `Mono.error(...)` hoặc khi một callback `map`/`flatMap` ném exception. Dù xuất phát từ đâu, khi đã nằm trong publisher, nó đi qua `onError`. Một exception ném **trước khi trả publisher** trong setup path có thể được framework bắt ở tầng khác; dùng `Mono.defer(...)` giúp các side effect/lỗi thuộc giai đoạn thực thi subscription khi phù hợp.

Không thay toàn bộ exception mapping bằng hàng loạt `try/catch` bên ngoài lời gọi `chain.filter`: nhiều lỗi phát sinh **sau** lúc method return, vào thời điểm subscribe và thực thi bất đồng bộ. `try/catch` đồng bộ không tự bắt mọi `onError` của downstream publisher.

## 6. Spring Security Reactive chuyển lỗi xác thực/phân quyền ra HTTP ra sao?

Spring Security WebFlux thường dùng các thành phần:

- `AuthenticationWebFilter`: thực hiện xác thực theo cơ chế đã cấu hình; authentication failure handler có thể trả challenge/redirect hoặc phản ứng khác.
- `AuthorizationWebFilter`: quyết định một request có được phép vào tài nguyên theo `ReactiveAuthorizationManager`.
- `ExceptionTranslationWebFilter`: chuyển những `AuthenticationException`/`AccessDeniedException` phù hợp phát sinh từ phần security chain nằm trong phạm vi nó quan sát thành phản ứng HTTP, qua authentication entry point hoặc access-denied handler.

Trong cấu hình HTTP Basic điển hình:

| Request | Diễn giải security | HTTP thường thấy |
|---|---|---|
| Chưa có credential, endpoint cần authentication | Cần entry point yêu cầu xác thực | `401` và Basic challenge |
| Credential sai | Authentication thất bại | `401` |
| Đã xác thực nhưng thiếu role | Authorization từ chối | `403` |
| Đủ quyền | Tiếp tục tới controller | `200` nếu controller thành công |
| Controller lỗi không được xử lý | Lỗi ứng dụng/WebFlux | `500` nếu response chưa commit |

Các status trên **không phải định luật tuyệt đối**: form login có thể redirect sang trang login; custom handler có thể trả JSON và status khác. `401/403` cũng không bắt buộc tương ứng `Mono.error` ở mọi filter vì security handler có thể viết response và hoàn thành bình thường.

**Vị trí đặc biệt quan trọng:** một global WebFilter nằm **bên ngoài** `WebFilterChainProxy` mà tự ném `AccessDeniedException` có thể nằm ngoài phạm vi bắt lỗi của `ExceptionTranslationWebFilter`. Không tự mặc định sẽ nhận 403; Spring Security kiểm soát tốt nhất khi policy nằm trong `authorizeExchange` và các security handlers chính thống.

Khi tùy biến, dùng:

- `ServerHttpSecurity.authorizeExchange(...)` để yêu cầu `authenticated()`, `hasRole(...)`, `hasAuthority(...)`, `denyAll()`.
- `ServerHttpSecurity.exceptionHandling(...)` với `ServerAuthenticationEntryPoint` hoặc `ServerAccessDeniedHandler` để tùy biến phản ứng authentication/access-denied.
- `ServerHttpSecurity.addFilterAt(WebFilter, SecurityWebFiltersOrder)` khi thật sự cần filter bảo mật đặc thù trong chain; chọn slot phù hợp, hiểu ai đứng trước/sau.
- Global `WebFilter` để đo đạc, thêm correlation ID, kiểm tra vấn đề chung với ứng dụng; đừng lẫn `@Order` của bean toàn cục với `SecurityWebFiltersOrder` bên trong security chain.

## 7. Cancel và timeout không phải lúc nào cũng là onError

Client có thể đóng kết nối giữa chừng, upstream có thể chủ động cancel subscription. `doOnError` không tự được gọi trong trường hợp chỉ có cancellation. Muốn quan sát cả ba kết cục:

```java
return chain.filter(exchange)
    .doFinally(signal -> {
        switch (signal) {
            case ON_COMPLETE -> metrics.completed();
            case ON_ERROR -> metrics.failed();
            case CANCEL -> metrics.cancelled();
            default -> { }
        }
    });
```

Đây là đoạn minh họa trong method filter với `metrics` cung cấp sẵn, API Reactor `SignalType` và Java 17 switch expression. Không viết response từ `doFinally` khi signal là CANCEL vì client có thể không còn kết nối. Ghi nhận metric nên nhanh, không block event-loop.

`timeout(Duration...)` của Reactor có thể tạo `TimeoutException` nếu publisher chậm và hủy upstream; trong khi timeout của client/proxy bên ngoài có thể biểu hiện thành cancel/disconnect. Không mặc định mọi timeout trở thành 504. Muốn chuyển timeout thành một mã HTTP cần mapping cụ thể, kiểm tra response chưa commit và bảo đảm không rò rỉ nội dung lỗi.

## 8. Project chạy được: ba trường hợp trên cùng một WebFilter chain

Ta tạo ứng dụng WebFlux nhỏ dùng hai global WebFilter và controller. Spring Security vẫn được tích hợp nhưng cấu hình `permitAll` **chỉ cho mục đích học luồng filter** để không che khuất ba kết quả. Cấu hình này không phải chính sách sản phẩm.

### 8.1. Khởi tạo Gradle project

Dùng Spring Initializr chọn Gradle, Java 17+, Spring Boot 3.x, Spring Reactive Web, Spring Security, Spring Boot Starter Test. Trong `build.gradle` do Initializr sinh, các dependency cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là **mảnh Gradle cấu hình dependency**, không phải toàn bộ `build.gradle` độc lập. Giữ plugin Spring Boot, repositories, dependency management, Java toolchain và wrapper mà Initializr tạo. Không thêm `spring-boot-starter-web` vào demo inbound WebFlux.

Bố cục tệp:

```text
src/main/java/demo/webfilterflow/
  FlowApplication.java
  WebSecurityConfig.java
  FlowFilters.java
  FlowController.java
src/test/java/demo/webfilterflow/
  FlowIntegrationTests.java
```

### 8.2. `FlowApplication.java`

```java
package demo.webfilterflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlowApplication.class, args);
    }
}
```

### 8.3. `WebSecurityConfig.java`

```java
package demo.webfilterflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebSecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().permitAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(login -> login.disable())
            .build();
    }
}
```

Toàn bộ endpoint GET được phép qua authorization nhằm quan sát behavior của các global filters. HTTP Basic/form login được tắt để không có redirect/challenge ngoài mục đích bài. CSRF giữ nguyên mặc định; demo chỉ dùng GET nên không phải tắt CSRF để chạy.

### 8.4. `FlowFilters.java`: outer observer và inner gate

```java
package demo.webfilterflow;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@Configuration
public class FlowFilters {

    private static final Logger log =
        LoggerFactory.getLogger(FlowFilters.class);

    @Bean
    @Order(-200)
    public WebFilter traceWebFilter() {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();

            return Mono.defer(() -> {
                log.info("BEGIN {}", path);

                return chain.filter(exchange)
                    .doOnSuccess(ignored ->
                        log.info("COMPLETE {}", path))
                    .doOnError(error ->
                        log.warn("ERROR {} {}", path,
                            error.getClass().getSimpleName()))
                    .doFinally(signal ->
                        log.info("FINALLY {} {}", path, signal));
            });
        };
    }

    @Bean
    @Order(-190)
    public WebFilter gateWebFilter() {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();

            if ("/stop".equals(path)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            return chain.filter(exchange);
        };
    }
}
```

Trong hai bean này, `@Order(-200)` chạy trước `@Order(-190)`. Các filter framework khác có thể xen vào tùy cấu hình; không dùng những giá trị này để suy đoán thứ tự bên trong `SecurityWebFilterChain`.

Khi request vào `traceWebFilter`, log `BEGIN` được ghi lúc subscribe; `gateWebFilter` kiểm tra path. Với `/stop`, gate đặt `403` và hoàn tất mà không gọi chain tiếp. `traceWebFilter` bên ngoài vẫn quan sát completion, **không nhất thiết quan sát onError**. Với `/failure`, controller phát lỗi và trace nhận `doOnError` nếu chưa có handler phía trong xử lý.

### 8.5. `FlowController.java`

```java
package demo.webfilterflow;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class FlowController {

    @GetMapping("/ok")
    public Mono<String> ok() {
        return Mono.just("ok");
    }

    @GetMapping("/stop")
    public Mono<String> shouldNotRun() {
        return Mono.just("controller-was-called");
    }

    @GetMapping("/failure")
    public Mono<String> failure() {
        return Mono.error(new IllegalStateException("demo failure"));
    }
}
```

Handler `/stop` có mặt thật nhưng không nên được gọi vì gate chặn trước. `/failure` cố tình phát lỗi để quan sát đường onError; ứng dụng thực phải xử lý lỗi nghiệp vụ theo policy riêng.

### 8.6. Chạy và kiểm tra HTTP

Từ root của project Initializr:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Khi server lắng nghe ở cổng mặc định 8080, gửi request:

```bash
curl -i http://localhost:8080/ok
curl -i http://localhost:8080/stop
curl -i http://localhost:8080/failure
```

Trên PowerShell, dùng `curl.exe` nếu `curl` là alias khác. Kỳ vọng:

| Request | HTTP status | Body |
|---|---|---|
| `GET /ok` | `200` | `ok` |
| `GET /stop` | `403` | Không có body do controller viết |
| `GET /failure` | `500` khi Boot xử lý lỗi chưa được map | Body lỗi do WebFlux/Boot tạo; không giả định nội dung cố định |

Dự kiến quan sát ở log của filter đối với **mỗi request độc lập**:

```text
/ok:
  BEGIN /ok
  COMPLETE /ok
  FINALLY /ok onComplete

/stop:
  BEGIN /stop
  COMPLETE /stop
  FINALLY /stop onComplete

/failure:
  BEGIN /failure
  ERROR /failure IllegalStateException
  FINALLY /failure onError
```

Đây là **sơ đồ tín hiệu dự kiến**, không phải stdout cố định cần đối chiếu từng dấu cách/format log; Spring/Netty có thể in thêm log và nhiều request có thể xen kẽ. Với `/stop`, HTTP 403 đi kèm Reactor completion bình thường là kết quả chủ ý. Với `/failure`, lỗi được error handler chung xử lý thành HTTP 500 khi response chưa commit.

### 8.7. `FlowIntegrationTests.java`

```java
package demo.webfilterflow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FlowIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void continueReachesController() {
        client.get().uri("/ok")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void earlyFinishSkipsController() {
        client.get().uri("/stop")
            .exchange()
            .expectStatus().isForbidden()
            .expectBody().isEmpty();
    }

    @Test
    void errorGetsMappedByWebFlux() {
        client.get().uri("/failure")
            .exchange()
            .expectStatus().is5xxServerError();
    }
}
```

Chạy:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

**Kỳ vọng 3 test pass** khi các class/dependencies đúng như ví dụ. Test dùng WebTestClient với cổng ngẫu nhiên, kiểm tra kết quả thực qua HTTP. Không cam kết stdout của Gradle/JUnit cố định. Để kiểm thử signal cụ thể trong filter đơn lẻ có thể dùng `StepVerifier` của Reactor Test, nhưng HTTP integration test ở đây đủ chứng minh controller nào được gọi và HTTP status cuối cùng.

## 9. Tự giải thích từng kịch bản

### `GET /ok`

```text
trace: BEGIN
  gate: path != /stop -> return chain.filter(exchange)
    security: permitAll -> tiếp tục
    controller: Mono.just("ok") -> WebFlux ghi body
trace: doOnSuccess -> COMPLETE
trace: doFinally(ON_COMPLETE)
HTTP 200, body ok
```

### `GET /stop`

```text
trace: BEGIN
  gate: path == /stop
    -> setStatusCode(403)
    -> response.setComplete()
    -> không gọi chain tiếp theo
trace: doOnSuccess -> COMPLETE
trace: doFinally(ON_COMPLETE)
HTTP 403, controller /stop không chạy
```

Ở đây từ `COMPLETE` trong log không đồng nghĩa HTTP 200; nó chỉ báo publisher kết thúc bình thường.

### `GET /failure`

```text
trace: BEGIN
  gate: path != /stop -> chain.filter
    controller: Mono.error(IllegalStateException)
trace: doOnError -> ERROR
trace: doFinally(ON_ERROR)
WebFlux error handler -> HTTP 500 (khi chưa commit)
```

Nếu thêm `onErrorResume(IllegalStateException.class, ...)` bên **trong** trace và tạo response thành công, trace có thể chỉ thấy completion. Nếu handler đặt **bên ngoài** trace, trace có thể vẫn thấy onError nhưng HTTP response sau cùng đã được chuyển thành fallback. Thứ tự operator quyết định hành vi có thể quan sát.

## 10. Chọn đúng tầng xử lý cho từng nhu cầu

| Nhu cầu | API hoặc cơ chế ưu tiên | Lý do |
|---|---|---|
| Log request, correlation ID, metrics | Global `WebFilter` + `doFinally` | Không phụ thuộc authentication |
| Request đi tiếp vào controller | `return chain.filter(exchange)` | Bảo toàn subscription và lifecycle |
| Chặn traffic theo quota/quy định hạ tầng | WebFilter/gateway với status rõ ràng | Chủ động short-circuit trước downstream |
| Phân quyền theo role, scope, principal | `ServerHttpSecurity.authorizeExchange` | Tích hợp auth context và 401/403 |
| Xử lý thiếu credential | `ServerAuthenticationEntryPoint` / authentication failure handler | HTTP Basic, form, OAuth có behavior khác nhau |
| Xử lý quyền không đủ | `ServerAccessDeniedHandler` | Đúng semantics của security |
| Thêm WebFilter bảo mật vào chain | `addFilterAt` với `SecurityWebFiltersOrder` | Xác định vị trí trong security pipeline |
| Xử lý exception nghiệp vụ | `@ExceptionHandler`, WebFlux error handler hoặc fallback có điều kiện | Không nuốt toàn bộ lỗi tại filter chung |

Một global WebFilter có thể chạy **trước** một số security filter; một security filter lại có thể dừng request trước controller. Vì vậy muốn dự đoán HTTP status và error signal phải xét **vị trí cụ thể của operator** chứ không chỉ loại exception hay tên endpoint.

## 11. Lỗi thường gặp

1. **Không trả publisher từ `chain.filter`.** Chỉ tạo publisher chưa bảo đảm downstream được xử lý; return đúng publisher.
2. **Tự gọi `subscribe()`.** Tách request ra khỏi lifecycle/trace/cancellation do framework quản lý.
3. **Gọi `block()` trong event-loop.** Có thể nghẽn server; compose operator bất đồng bộ.
4. **Tưởng HTTP 403 là `onError`.** Một filter viết response 403 rồi `setComplete()` có thể kết thúc bình thường.
5. **Short-circuit mà không đặt HTTP status.** Client có thể nhận response gây hiểu nhầm.
6. **Dùng `doOnError` để kỳ vọng lỗi tự được chuyển thành status.** Nó chỉ quan sát; error handler quyết định response.
7. **Bắt mọi lỗi bằng `onErrorResume(e -> Mono.empty())`.** Dễ nuốt lỗi bảo mật/lập trình, che giấu sự cố.
8. **Cố ghi response trong `doFinally`.** Headers/body có thể đã commit hoặc client đã disconnect.
9. **Cố sửa status khi response đã commit.** Kiểm tra `isCommitted()` và xử lý sớm.
10. **Đánh đồng `permitAll` với bỏ qua toàn bộ filter.** `permitAll` chỉ cho bước authorization tiếp tục.
11. **Nhầm global `@Order` và `SecurityWebFiltersOrder`.** Hai tầng có thứ tự cấu hình khác nhau.
12. **Tự ném `AccessDeniedException` từ global filter rồi mong chắc chắn có 403.** Error translator bảo mật chỉ bắt lỗi trong phạm vi phù hợp.
13. **Không phân biệt cancel với error.** `doOnError` không đại diện cho client disconnect; `doFinally` có thể nhận `CANCEL`.
14. **Log nguyên giá trị Authorization header.** Filter có thể tiếp xúc credential/token; không ghi bí mật vào logs.
15. **Đọc `SecurityContextHolder` kiểu thread-local trong reactive pipeline.** Dùng `ReactiveSecurityContextHolder`/injection WebFlux cho ngữ cảnh bảo mật nằm trong subscription.

## 12. Câu hỏi kiểm tra

**Câu 1.** Một filter trả `response.setComplete()` cùng status 429 mà không gọi `chain.filter(exchange)`. Điều gì xảy ra?

**Đáp án:** Các filter downstream và controller không chạy. Những filter đã vào trước đó vẫn có thể thấy onComplete và thực hiện hậu xử lý. HTTP 429 không bắt buộc là Reactor onError.

**Câu 2.** Sửa đoạn mã sau:

```java
chain.filter(exchange).subscribe();
return Mono.empty();
```

**Đáp án:** `return chain.filter(exchange);`. Framework kiểm soát subscription, lỗi và cancellation; filter không tự subscribe.

**Câu 3.** Vì sao `doOnError` ở filter ngoài không chạy khi controller lỗi?

**Đáp án:** Có thể lỗi đã được `@ExceptionHandler` hoặc `onErrorResume` ở tầng bên trong chuyển thành publisher hoàn thành bình thường trước khi đến outer filter. Cần kiểm tra phạm vi downstream và vị trí handler.

**Câu 4.** Với API JWT, muốn hạn chế `/admin` cho `SCOPE_admin` nên dùng global WebFilter tự so sánh token hay security DSL?

**Đáp án:** Dùng `authorizeExchange(...).hasAuthority("SCOPE_admin")` cùng JWT resource server/authority mapping đã xác minh. Security DSL cung cấp semantics authentication/authorization thống nhất.

**Câu 5.** Sau khi response gửi một phần body, filter có thể chuyển từ 200 sang 503 bằng `onErrorResume` không?

**Đáp án:** Thường không vì headers đã commit; phải ghi nhận và truyền lỗi/xử lý kết nối phù hợp, không cố gửi response thứ hai.

**Câu 6.** Khi client ngắt kết nối, `doOnError` có bắt buộc chạy không?

**Đáp án:** Không. Client disconnect có thể làm subscription nhận `CANCEL`; quan sát bằng `doFinally` để phân biệt cancel với error.

## Điểm cần nhớ

```text
WebFilter.filter(...) -> Mono<Void>

CONTINUE:
  return chain.filter(exchange)
  -> downstream chạy, kết quả đi ngược về outer filters

EARLY FINISH:
  response.setStatusCode(...)
  return response.setComplete()      // không gọi chain.filter
  -> downstream dừng, outer filters vẫn có thể thấy onComplete

ERROR:
  Mono.error(e) -> onError ngược qua các operator
  doOnError: quan sát
  onErrorMap: đổi lỗi
  onErrorResume: có thể phục hồi
  error handler: có thể map sang HTTP response nếu chưa commit

CANCEL:
  subscription bị hủy -> doFinally(CANCEL)
  không giả định còn khả năng trả HTTP
```

Trong Spring Security Reactive, **HTTP status**, **Reactor signal** và **quyết định xác thực/phân quyền** là ba khái niệm khác nhau. Hiểu cả ba mới giải thích được vì sao một filter dừng request, vì sao log hoàn tất vẫn đi kèm 403, hoặc vì sao lỗi chỉ tới một số filter trong chain.

## Tài liệu chính thức

- [Spring Framework — WebFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework — WebFilterChain API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/server/WebFilterChain.html)
- [Spring Framework — WebExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/server/WebExceptionHandler.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — ExceptionTranslationWebFilter](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [Project Reactor — Error handling operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
