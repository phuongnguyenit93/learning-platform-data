# Tôn trọng hợp đồng reactive và tránh đưa mã chặn luồng vào chuỗi

> **Bối cảnh:** Spring Security fundamentals, nhóm “Điểm mở rộng”. Bài học tập trung vào ứng dụng **Spring WebFlux + Spring Security reactive**: khi tùy biến xác thực, phân quyền, truy xuất tài khoản, xử lý exception hoặc filter, phải giữ nguyên hợp đồng `Mono»/`Flux» và tránh chặn event-loop. Ví dụ dùng **Java 17, Spring Boot 3.3.x, Spring Security 6.x và Reactor 3.6.x**. Ứng dụng Servlet/Spring MVC dùng những interface và mô hình thực thi khác; không sao chép các ví dụ reactive sang Servlet mà không điều chỉnh.

## 1. Điều gì thực sự cần được tôn trọng?

Một phương thức reactive không trở nên không chặn luồng chỉ vì kiểu trả về là `Mono<T>» hoặc `Flux<T>». Bản thân logic **bên trong** pipeline cũng phải tránh các lời gọi chờ đồng bộ: JDBC/JPA, `RestTemplate», `Thread.sleep», `Future.get», đọc file theo API blocking hoặc `Mono.block()».

Trong WebFlux, một số lượng nhỏ event-loop thread có thể phục vụ nhiều kết nối nhờ công việc được diễn tả dưới dạng **publisher**. Khi request cần chờ I/O, publisher chưa phát kết quả; event-loop có thể phục vụ công việc khác. Nếu custom security code giữ một event-loop thread trong lúc chờ database, cả các request không liên quan cũng có thể bị tăng độ trễ.

Ví dụ trực quan:

```text
HTTP request
   |
   v
SecurityWebFilterChain (WebFlux)
   |
   +--> AuthenticationWebFilter / ReactiveAuthenticationManager
   |          |
   |          +--> Trả Mono<Authentication> (không block để lấy Authentication)
   |
   +--> AuthorizationWebFilter / ReactiveAuthorizationManager
   |          |
   |          +--> Kết hợp Mono<Authentication> với Mono<quyền truy cập>
   |
   +--> Handler/controller phản ứng với kết quả
              |
              v
        Mono/Flux hoàn tất, lỗi hoặc bị hủy
```

**“Hợp đồng reactive”** bao gồm nhiều đặc tính gắn với nhau:

1. **Lazy/deferred:** xây dựng publisher không đồng nghĩa thực hiện tất cả I/O ngay; phần lớn công việc bắt đầu khi có subscription.
2. **Non-blocking:** không chiếm thread chỉ để chờ kết quả network/database trong những vị trí cần không chặn.
3. **Composition:** trả publisher để Spring Security và Reactor **kết nối** nó vào pipeline; không tự gọi `subscribe()» rồi trả kết quả giả.
4. **Signal rõ ràng:** giá trị (`onNext»), kết thúc không có giá trị (`onComplete»), lỗi (`onError») và hủy (`cancel») có ý nghĩa khác nhau.
5. **Context theo subscriber:** thông tin security được truyền qua **Reactor Context**; không mặc nhiên nằm trong một `ThreadLocal» cố định.
6. **Cancellation/timeout:** request bị hủy hoặc timeout cần được truyền tới nguồn dữ liệu nếu nguồn có hỗ trợ; công việc bị tách bởi `subscribe()» riêng có thể tiếp tục chạy không kiểm soát.
7. **Fail closed:** khi không xác minh được quyền, không tự động cấp quyền hoặc trả `true» để che lỗi.

### Tại sao “bọc bằng Mono.just” chưa đủ?

```java
// SAI — câu lệnh JDBC đã chạy và chặn thread trước khi Mono được tạo.
Mono<UserRecord> user = Mono.just(jdbcRepository.findUser(username));
```

```java
// SAI — Mono được tạo trước, nhưng callback vẫn chạy mã JDBC blocking
// trên thread thực thi callback (có thể là event-loop).
Mono<UserRecord> user = Mono.fromCallable(
    () -> jdbcRepository.findUser(username)
);
```

```java
// Cách ly tạm thời nếu bắt buộc giữ một adapter JDBC đồng bộ.
// Đoạn code là fragment: jdbcRepository/UserRecord do dự án định nghĩa.
Mono<UserRecord> user = Mono.fromCallable(
    () -> jdbcRepository.findUser(username)
).subscribeOn(Schedulers.boundedElastic());
```

Ví dụ thứ ba chỉ đúng khi bạn **chủ động cách ly nguồn đồng bộ** bằng scheduler phù hợp. Đây là giải pháp chuyển tiếp, **không biến JDBC thành I/O reactive**. Connection pool của JDBC và worker của `boundedElastic» vẫn là tài nguyên hữu hạn; production nên ưu tiên API thật sự không chặn như R2DBC hoặc HTTP client reactive khi phù hợp.

## 2. Đâu là các điểm mở rộng reactive của Spring Security?

| Nhu cầu | Interface reactive | Hợp đồng quan trọng |
| --- | --- | --- |
| Xác thực token/credential | `ReactiveAuthenticationManager» | `authenticate(Authentication)» trả `Mono<Authentication>»; thành công phát kết quả, không hỗ trợ có thể trả `Mono.empty()», lỗi xác thực phát `onError» |
| Trích xuất credential từ HTTP | `ServerAuthenticationConverter» | `convert(ServerWebExchange)» trả `Mono<Authentication>»; không gọi nguồn dữ liệu blocking khi parse |
| Tải tài khoản | `ReactiveUserDetailsService» | `findByUsername(String)» trả `Mono<UserDetails>»; rỗng khi không có user, lỗi I/O là `onError» |
| Ra quyết định ủy quyền | `ReactiveAuthorizationManager<T>» | `check(Mono<Authentication>, T)» trả `Mono<AuthorizationDecision>» ở Spring Security 6.x; compose bằng `flatMap» |
| Lưu/tải security context | `ServerSecurityContextRepository» | `load»/`save» và `SecurityContext» phải tuân hợp đồng Mono, không truy cập session store blocking ngay trên event-loop |
| Lỗi cần xác thực | `ServerAuthenticationEntryPoint» | `commence(...)» trả `Mono<Void>» mô tả ghi response |
| Lỗi đã xác thực nhưng thiếu quyền | `ServerAccessDeniedHandler» | `handle(...)» trả `Mono<Void>» |
| Authentication thành công/thất bại | `ServerAuthenticationSuccessHandler», `ServerAuthenticationFailureHandler» | Trả `Mono<Void>» liên kết với việc hoàn tất response/chuỗi |
| Web filter bổ sung | `WebFilter» | `filter(exchange, chain)» trả `Mono<Void>» và dùng `chain.filter(exchange)» đúng cách |
| Method security reactive | `@EnableReactiveMethodSecurity», `@PreAuthorize» | Dựa trên Reactor Context và các phương thức trả `Publisher» phù hợp |

**Chú ý về phiên bản:** trong Spring Security 6.x, interface `ReactiveAuthorizationManager» có phương thức `check» trả `Mono<AuthorizationDecision>». Khi nâng cấp major version, hãy đối chiếu Java API của chính phiên bản đang chạy; đừng sao chép chữ ký của bản mới hơn một cách máy móc.

Một số quy ước quan trọng:

- Với **`ReactiveAuthenticationManager»**, `Mono.empty()» có nghĩa manager không thể quyết định/xác thực loại token đó; nó **không đồng nghĩa đăng nhập thành công**. Credential sai phải trả tín hiệu lỗi xác thực thích hợp.
- Với **`ReactiveUserDetailsService»**, user không tồn tại có thể biểu diễn bằng `Mono.empty()»; lỗi database/IdP phải truyền `onError», không đổi thành user vắng mặt.
- Với **`ReactiveAuthorizationManager»**, bài kiểm tra tùy biến nên phát **quyết định true/false rõ ràng**. Đừng giả định `Mono.empty()» mang ý nghĩa “deny” trong mọi cách kết hợp manager.
- Với `Mono<Void>», một giá trị “void” không được phát ra qua `onNext»; điều quan trọng là publisher mô tả việc ghi response/lỗi và hoàn tất đúng lúc.

## 3. Đúng và sai khi triển khai một quyết định phân quyền

Giả sử bạn phải hỏi dịch vụ quyền xem tài khoản có được đọc báo cáo hay không. Một service reactive trả `Mono<Boolean>»:

```java
// Fragment: entitlementClient là một API HTTP/database reactive thật.
Mono<Boolean> canRead(String username) {
    return entitlementClient.lookup(username)
        .map(record -> record.canReadReports())
        .switchIfEmpty(Mono.just(false));
}
```

Bộ kiểm tra quyền phải **compose** publisher, không lấy Boolean ngay bằng `block()»:

```java
// SAI — có thể chặn event-loop hoặc bị Reactor báo lỗi block().
// Giả định entitlementClient và authentication đã được khai báo.
boolean allowed = entitlementClient.lookup(authentication.getName())
    .map(record -> record.canReadReports())
    .block();
return Mono.just(new AuthorizationDecision(allowed));
```

```java
// ĐÚNG — lambda minh họa logic ReactiveAuthorizationManager.
// authentication là Mono<Authentication>.
return authentication
    .flatMap(auth -> entitlementClient.lookup(auth.getName())
        .map(record -> new AuthorizationDecision(record.canReadReports())))
    .defaultIfEmpty(new AuthorizationDecision(false));
```

Khi tạo manager thật, cần kiểm tra `Authentication» có hợp lệ, không dựa riêng vào `isAuthenticated()» vì token anonymous có thể báo cờ authenticated nội bộ. Mẫu ứng dụng đầy đủ ở phần 5 dùng thêm điều kiện loại trừ `AnonymousAuthenticationToken».

Các lỗi composition thường gặp:

```java
// SAI: map tạo Mono<Mono<Boolean>>, chưa lấy kết quả async bên trong.
// Đây là fragment, authMono và entitlementClient cần được định nghĩa.
Mono<Mono<Boolean>> nested = authMono.map(auth ->
    entitlementClient.canRead(auth.getName()));
```

```java
// ĐÚNG: flatMap đưa kết quả của publisher con vào chuỗi chung.
Mono<Boolean> allowed = authMono.flatMap(auth ->
    entitlementClient.canRead(auth.getName()));
```

```java
// SAI: subscribe() tạo một luồng công việc rời; trả true ngay,
// không đợi quyền và không chuyển lỗi/cancel vào request.
entitlementClient.canRead(username).subscribe(result -> audit(result));
return Mono.just(new AuthorizationDecision(true));
```

```java
// ĐÚNG: mọi bước có ảnh hưởng tới quyết định đều nằm trong publisher.
return entitlementClient.canRead(username)
    .map(AuthorizationDecision::new)
    .defaultIfEmpty(new AuthorizationDecision(false));
```

Trong fragment `subscribe()», `audit» là phương thức giả định; đó là **phản ví dụ**, không phải đoạn độc lập để chạy. Một logger/metric non-blocking phụ trợ có thể sử dụng `doOnNext», `doOnError», `doFinally», nhưng **không dùng side effect để quyết định cấp quyền**; quyết định phải đến từ publisher được trả về.

### Chọn `map», `flatMap», `switchIfEmpty», `onErrorResume»

| Operator | Dùng khi | Lưu ý bảo mật |
| --- | --- | --- |
| `map(fn)» | Chuyển đổi đồng bộ, nhanh, không chờ I/O | Không gọi JDBC/HTTP blocking trong `fn» |
| `flatMap(fn)» | `fn» trả `Mono<R>» như truy vấn quyền, token validation | Giữ async, lỗi, cancellation trong chuỗi |
| `switchIfEmpty(other)» | Không có kết quả cần fallback hợp lệ | Không biến “không có quyền” thành mặc định cho phép |
| `onErrorResume» | Phân loại/điều chỉnh lỗi đã hiểu | Không được dùng `onErrorReturn(true)» hoặc nuốt mọi lỗi rồi cấp quyền |
| `timeout(Duration)» | Giới hạn thời gian đợi | `TimeoutException» không phải “user không tồn tại”; fail closed |
| `retryWhen» | Retry có điều kiện cho lỗi transient | Cần giới hạn lần thử/backoff; không retry mù các phép xác thực một lần |
| `doOnError»/`doFinally» | Ghi metric/log phụ trợ, cleanup | Side effect phải nhẹ và không blocking |
| `subscribeOn» | Chọn scheduler cho nguồn subscription, thường để cô lập adapter blocking | Đặt gần `Mono.fromCallable» bao lời gọi blocking |
| `publishOn» | Chuyển scheduler cho phần xử lý downstream | Không tự sửa một lời gọi blocking đã chạy upstream |

## 4. Vì sao event-loop và Reactor Context quan trọng với Security?

### 4.1 Blocking làm ảnh hưởng nhiều request

WebFlux trên Reactor Netty thường dùng event-loop với số thread giới hạn. Khi một handler/manager dành 200 ms chờ JDBC, các tác vụ khác đang chờ thread đó cũng bị chậm. Dưới tải cao, p95/p99 latency, timeout, queue và số request thất bại có thể tăng. Việc một API chạy “đúng” ở môi trường dev ít request không chứng minh nó không gây hại dưới tải.

Những thao tác cần rà soát trong authentication/authorization path:

- `Mono.block()», `Flux.blockFirst()», `Flux.blockLast()», `blockOptional()».
- `Thread.sleep», `Object.wait», `Future.get», `CompletableFuture.join».
- `RestTemplate», `HttpURLConnection», SDK HTTP đồng bộ, truy cập LDAP blocking.
- JDBC/JPA/`EntityManager», JDBC session repository, file I/O đồng bộ, synchronized lock giữ lâu.
- Password hashing/cryptography hoặc JSON mapping quá nặng chạy trực tiếp trên event-loop (đây thường là việc CPU-intensive, dù không chờ I/O).
- Cache client “reactive” nhưng implementation bên trong thực chất gọi SDK đồng bộ.

**Không phải mọi hàm synchronous đều sai.** `map» chạy một phép so sánh authority hoặc đọc field từ object trong bộ nhớ là phù hợp. Vấn đề là blocking I/O, chờ đồng bộ hoặc tính toán kéo dài, làm mất tính đáp ứng của scheduler.

### 4.2 SecurityContextHolder và ReactiveSecurityContextHolder

Trong Servlet, `SecurityContextHolder» thường dựa trên `ThreadLocal». WebFlux có thể đổi thread khi `publishOn», `flatMap» hoặc callback I/O hoàn tất; vì vậy lấy principal bằng `SecurityContextHolder.getContext()» trong reactive callback dễ nhận context rỗng/sai.

Đúng trong WebFlux:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
```

Khi request đi qua Spring Security WebFlux, framework thiết lập ngữ cảnh phù hợp trên Reactor Context. Không tự copy `SecurityContext» sang ThreadLocal bằng tay để “sửa” một lỗi đổi thread.

Để chủ động tạo context trong một unit test riêng, có thể viết:

```java
Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
    "reader",
    "n/a",
    List.of(new SimpleGrantedAuthority("ROLE_READER"))
);

Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(username)
    .expectNext("reader")
    .verifyComplete();
```

Đoạn là **fragment unit test**, cần các import Spring Security/Reactor Test/JUnit tương ứng; không phải file Java độc lập. Nó chứng minh việc cung cấp context cho **subscription**. `contextWrite» phục vụ Reactor Context; nó không biến ThreadLocal tùy ý thành đáng tin sau khi đổi scheduler.

### 4.3 Không tự subscribe trong filter/handler

Một `WebFilter» có dạng `Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)». Trả `chain.filter(exchange)» hoặc một publisher kết hợp với nó để framework điều khiển lifecycle. Không gọi `chain.filter(exchange).subscribe()» rồi trả `Mono.empty()»: việc ghi response có thể diễn ra ngoài chuỗi, gây race, hai lần commit, mất lỗi hoặc mất security context.

```java
// Fragment minh họa filter hợp lệ, không tự subscribe.
@Bean
WebFilter timingFilter() {
    return (exchange, chain) -> {
        long started = System.nanoTime();

        return chain.filter(exchange)
            .doFinally(signalType -> {
                long elapsedNanos = System.nanoTime() - started;
                // Chỉ ghi metric nhẹ, không làm I/O blocking ở đây.
            });
    };
}
```

`doFinally» có thể chạy trên thread nào đó của Reactor; nếu metric exporter là blocking, cần dùng cơ chế xử lý riêng đã được thiết kế, không để exporter chặn event-loop.

## 5. Dự án Spring Boot WebFlux chạy được: phân quyền dựa trên Mono

Ví dụ sau cấu hình HTTP Basic, hai tài khoản demo `reader» và `guest», một `ReactiveAuthorizationManager<AuthorizationContext>» và một service quyền giả lập trả `Mono<Boolean>» không blocking. Sử dụng timer `Mono.delay» **chỉ để mô phỏng một kết quả async**; trong hệ thống thật, thay bằng WebClient/R2DBC/reactive SDK. Điều kiện quyền gồm: có authentication thật, có role READER và policy service cấp quyền. Khi không có kết quả, ứng dụng từ chối mặc định.

### 5.1 Cấu trúc

```text
reactive-security-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/reactivesecurity/
    │   └── ReactiveSecurityDemoApplication.java
    └── test/java/com/example/reactivesecurity/
        └── ReactiveSecurityDemoApplicationTest.java
```

### 5.2 Maven — chỉ dùng WebFlux

Tạo `pom.xml». Không thêm `spring-boot-starter-web» cho ví dụ này: khi cả Servlet MVC và WebFlux cùng có mặt, Spring Boot có thể chọn ứng dụng Servlet tùy cấu hình, khiến bạn tưởng đang thử reactive filter trong khi stack đã thay đổi.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-security-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
```

### 5.3 Java source

Tạo file `src/main/java/com/example/reactivesecurity/ReactiveSecurityDemoApplication.java»:

```java
package com.example.reactivesecurity;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo123")
            .roles("READER")
            .build();

        UserDetails guest = User.withUsername("guest")
            .password("{noop}demo123")
            .roles("GUEST")
            .build();

        return new MapReactiveUserDetailsService(List.of(reader, guest));
    }

    @Bean
    AsyncReportPolicy asyncReportPolicy() {
        return new AsyncReportPolicy();
    }

    @Bean
    ReactiveAuthorizationManager<AuthorizationContext> reportAuthorization(
            AsyncReportPolicy reportPolicy) {

        return (authentication, context) -> authentication
            .filter(auth -> auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken))
            .filter(auth -> auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority())))
            .flatMap(auth -> reportPolicy.canReadReports(auth.getName()))
            .map(AuthorizationDecision::new)
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    @Bean
    SecurityWebFilterChain filterChain(
            ServerHttpSecurity http,
            ReactiveAuthorizationManager<AuthorizationContext> reportAuthorization) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/me").authenticated()
                .pathMatchers("/secure/reports").access(reportAuthorization)
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    // Mô phỏng một phụ thuộc bất đồng bộ; không gọi Thread.sleep().
    static final class AsyncReportPolicy {
        Mono<Boolean> canReadReports(String username) {
            return Mono.delay(Duration.ofMillis(10))
                .map(tick -> "reader".equals(username));
        }
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("public ok");
        }

        @GetMapping("/secure/reports")
        Mono<String> reports() {
            return Mono.just("reports ok");
        }

        @GetMapping("/me")
        Mono<String> currentUser() {
            return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
        }
    }
}
```

### 5.4 Giải thích những dòng quan trọng

1. **`MapReactiveUserDetailsService»** tạo tài khoản trong bộ nhớ. `{noop}» chỉ để dễ thử; password plaintext là không an toàn trong sản phẩm thật. Spring Security dùng provider reactive phù hợp với `ReactiveUserDetailsService» để xác thực Basic.
2. **`reportAuthorization»** nhận một `Mono<Authentication>». Nó filter anonymous, kiểm tra authority theo cấu hình và **`flatMap»** vào lời gọi policy trả `Mono<Boolean>». Không gọi `block», `subscribe», JDBC hoặc HTTP đồng bộ.
3. **`new AuthorizationDecision(false)»** là mặc định khi không có authentication hoặc kết quả. Quy tắc cấp quyền được viết rõ ràng; không coi `Mono.empty()» là “cho qua”.
4. **`Mono.delay»** không chặn thread 10 ms; Reactor phát signal sau khoảng thời gian đó. Đây là mô phỏng async **có chủ đích**, không được hiểu là một truy vấn tới hệ thống phân quyền thật.
5. **`/me»** đọc username từ `ReactiveSecurityContextHolder», minh họa context gắn với subscriber và giữ tính reactive.
6. **HTTP Basic** xử lý trường hợp chưa có credential bằng challenge 401; người dùng đã xác thực nhưng bị policy từ chối thường nhận 403. Lời gọi quyền lỗi không nên chuyển thành granted.
7. **CSRF được giữ theo mặc định**: demo chỉ có GET, không cần tắt. Khi thêm POST hoặc giao diện dùng session/cookie, đánh giá CSRF theo mô hình client; đừng tắt mặc định chỉ vì 403 khi gửi form.

### 5.5 Kiểm tra hành vi bằng HTTP

Từ thư mục dự án có `pom.xml», cần Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Mở terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/secure/reports
curl -i -u guest:demo123 http://localhost:8080/secure/reports
curl -i -u reader:demo123 http://localhost:8080/secure/reports
curl -i -u reader:demo123 http://localhost:8080/me
```

| Request | HTTP mong đợi | Nội dung chính |
| --- | --- | --- |
| `GET /public» không credential | 200 | `public ok» |
| `GET /secure/reports» không credential | 401 | Basic challenge; chưa đăng nhập |
| `GET /secure/reports» với `guest» | 403 | Đã đăng nhập nhưng thiếu quyền |
| `GET /secure/reports» với `reader» | 200 | `reports ok» |
| `GET /me» với `reader» | 200 | `reader» |

Header như `Date» và body lỗi do framework tạo có thể khác nhau; bảng chỉ dựa trên status và body controller ổn định của ví dụ. Việc thấy status đúng **không tự chứng minh không blocking**; còn cần kiểm tra đường gọi và độ trễ khi có tải.

### 5.6 WebTestClient kiểm tra 401/403/200 và Reactor Context

Tạo `src/test/java/com/example/reactivesecurity/ReactiveSecurityDemoApplicationTest.java»:

```java
package com.example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveSecurityDemoApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousIsChallenged() {
        client.get().uri("/secure/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void guestIsDenied() {
        client.get().uri("/secure/reports")
            .headers(headers -> headers.setBasicAuth("guest", "demo123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void readerIsAllowed() {
        client.get().uri("/secure/reports")
            .headers(headers -> headers.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports ok");
    }

    @Test
    void reactiveContextContainsAuthenticatedUser() {
        client.get().uri("/me")
            .headers(headers -> headers.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader");
    }
}
```

Các test này kiểm tra hành vi bảo mật của tuyến HTTP. Muốn xác nhận custom async service được dùng đúng, có thể thêm `StepVerifier» cho `Mono<Boolean>», test error/timeout và một phép đo độ trễ khi nhiều request song song. Những ví dụ code ở trên hướng dẫn cách tự chạy; không thay thế kiểm thử trên môi trường và dependencies của dự án thực tế.

## 6. Thay mô phỏng bằng I/O thật: API nào nên dùng?

| Tác vụ trong Security | API phù hợp reactive | Tránh khi chạy trên event-loop |
| --- | --- | --- |
| Tra cứu tài khoản | `ReactiveUserDetailsService» + R2DBC/reactive driver | Repository JPA/JDBC gọi trực tiếp trong `flatMap» |
| Tra cứu quyền qua HTTP | `WebClient» hoặc HTTP client non-blocking | `RestTemplate», `HttpURLConnection» đồng bộ |
| Truy vấn Redis/session | Reactive Redis client, `ReactiveRedisOperations» | Redis client sync hoặc session store blocking |
| Kiểm tra token với IdP | Reactive authentication manager/decoder/client phù hợp | Gọi SDK đồng bộ trong converter |
| Đọc config/secret động | Client async hoặc snapshot có bộ nhớ đệm được quản lý | Đọc file/hệ thống secret sync mỗi request |
| Mã hóa/kiểm tra password | Đánh giá chi phí CPU và cách Spring Security/provider sắp xếp scheduler | Chạy vòng hash nặng tùy ý trên event-loop |

Ví dụ adapter gọi dịch vụ quyền bằng WebClient **(fragment, cần bean `WebClient» và contract API thật)**:

```java
record PermissionReply(boolean allowed) {}

Mono<Boolean> canReadReports(String username) {
    return webClient.get()
        .uri("/permissions/reports/{username}", username)
        .retrieve()
        .bodyToMono(PermissionReply.class)
        .map(PermissionReply::allowed)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Empty permission response")))
        .timeout(Duration.ofSeconds(2));
}
```

`WebClient» trả publisher và không yêu cầu gọi `block()». `retrieve()» mặc định biến nhiều phản hồi 4xx/5xx thành lỗi; **phải phân loại** theo hợp đồng dịch vụ, ví dụ 404 có thật sự nghĩa là “không có quyền” hay chỉ là sai route? Khi service timeout, đừng tự động cấp quyền. Lỗi “không thể kiểm tra quyền” có thể được trình bày thành lỗi hệ thống 5xx với logging an toàn; hoặc từ chối quyền 403 nếu chính sách rõ ràng chọn deny-on-outage. Hai cách đều phải **fail closed** và giữ thông tin chẩn đoán nội bộ.

Nếu cần cache quyền, phải xác định TTL, phạm vi tenant, invalidation và sự kiện thu hồi. Cache stale có thể cấp quyền đã bị rút; việc “dùng cache cho nhanh” không miễn trừ kiểm soát thu hồi quyền.

## 7. Khi bắt buộc gọi thư viện blocking: cách cô lập đúng

Một số hệ thống có JDBC/LDAP/SDK đồng bộ chưa thể thay ngay. Cách chuyển tiếp với Reactor:

```java
// Fragment: legacyAccountStore là SDK/repository đồng bộ của dự án.
Mono<UserRecord> findUser(String username) {
    return Mono.fromCallable(() ->
            legacyAccountStore.findByUsername(username))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(2));
}
```

Lý do dùng `fromCallable» là để trì hoãn thực thi lời gọi đến lúc có subscription; `subscribeOn(Schedulers.boundedElastic())» chuyển công việc blocking sang worker pool được giới hạn thay vì chiếm event-loop. Không đặt lời gọi blocking **ngoài** `fromCallable», nếu không nó đã chạy trước lúc có scheduler.

**Giới hạn và rủi ro còn lại:**

- `boundedElastic» không tạo ra “I/O non-blocking thật”; mỗi lời gọi JDBC/LDAP vẫn giữ một worker trong lúc chờ.
- Worker/queue có giới hạn; nếu một lượng lớn request cùng chờ database, thời gian chờ vẫn tăng hoặc hàng đợi bị đầy.
- `timeout» trên publisher **không đảm bảo có thể ngắt một JDBC call** đã bắt đầu; cần timeout đúng ở driver, network và pool.
- Phải giới hạn concurrency và connection pool theo khả năng thực tế, tránh tạo thêm request chỉ vì thấy có scheduler riêng.
- `publishOn(boundedElastic())» chỉ chuyển **downstream**; nếu blocking xảy ra upstream trước đó, việc “publishOn ở cuối” không cứu được.
- Không viết `Schedulers.boundedElastic().schedule(...)» trong manager rồi trả kết quả cho phép ngay; như thế lại tách công việc khỏi security flow.
- Nếu mã CPU-intensive như hashing rất nặng, cần xem chiến lược scheduler và giới hạn tải; `boundedElastic» chủ yếu dành cho blocking I/O, không phải lời giải chung cho mọi workload CPU.

Ưu tiên thực sự lâu dài là chuyển sang R2DBC/HTTP client reactive nếu các thành phần tương ứng hỗ trợ. Đừng dùng một wrapper `Mono» để che đi lỗi thiết kế thread hoặc pool.

## 8. Xử lý lỗi, timeout, retry và cancellation mà không làm lỏng bảo mật

Một phần khó của reactive security là **lỗi bất đồng bộ không đồng nghĩa “không có quyền”**. Ví dụ dịch vụ entitlement trả lỗi 503; manager vẫn phải ngăn request tới tài nguyên, đồng thời cho monitoring biết dependency đang hỏng.

### Phân biệt trạng thái

| Tín hiệu trong pipeline | Ý nghĩa tiềm năng | Xử lý an toàn |
| --- | --- | --- |
| `Mono.just(true)» từ policy có bằng chứng | Cho phép theo quy tắc hiện tại | Trả `AuthorizationDecision(true)» |
| `Mono.just(false)» | Quy tắc không cho phép | Trả `AuthorizationDecision(false)» |
| `Mono.empty()» từ policy | Không có kết quả / không đưa ra quyết định | Định nghĩa rõ và mặc định từ chối |
| `Mono.error(TimeoutException)» | Không nhận được phản hồi kịp | Fail closed, ghi metric outage |
| `Mono.error(WebClientResponseException)» | Dịch vụ trả lỗi HTTP | Phân loại 4xx/5xx theo API contract; không grant |
| Request `cancel()» | Client bỏ request hoặc timeout upstream | Không tiếp tục side effect cấp quyền ngoài luồng |

Một anti-pattern nguy hiểm:

```java
// SAI — phụ thuộc lỗi lại tự động mở quyền.
return entitlementService.canRead(username)
    .onErrorReturn(true)
    .map(AuthorizationDecision::new);
```

Một lựa chọn **fail closed** nhưng cần cân nhắc semantic HTTP:

```java
// Từ chối khi service bị lỗi; cần log/metric outage riêng.
// Fragment: entitlementService/username là biến có trong scope.
return entitlementService.canRead(username)
    .onErrorResume(EntitlementUnavailableException.class, error ->
        Mono.just(false))
    .map(AuthorizationDecision::new);
```

Trả false khi outage có thể khiến client nhận 403, dù root cause là 5xx phía hệ thống. Nếu sản phẩm yêu cầu khách hàng nhận 503, cần để exception chạy tới cơ chế xử lý lỗi server phù hợp và đảm bảo **không** chuyển tới handler tài nguyên. Không mặc định biến tất cả lỗi runtime thành deny 403 rồi làm mất thông tin vận hành.

### Giới hạn timeout và retry

```java
// Fragment minh họa, chỉ retry lỗi tạm thời đã được nhận diện.
// client gọi I/O non-blocking, không chạy retry một thao tác một lần
// như authorization-code exchange nếu giao thức không cho phép.
return entitlementService.canRead(username)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .filter(TransientEntitlementFailure.class::isInstance));
```

`Retry» cần import từ `reactor.util.retry.Retry»; hai tên exception `TransientEntitlementFailure»/`EntitlementUnavailableException» trong các fragment chỉ là **kiểu miền giả định do ứng dụng định nghĩa**, không phải class dựng sẵn của Spring Security. Retry chỉ những thao tác phù hợp, có giới hạn, có backoff/jitter và không làm bùng nổ lưu lượng khi dependency đang hỏng.

**Cancellation:** không dùng `subscribe()» độc lập để gửi request kiểm quyền; nếu request HTTP bị hủy, pipeline chung có cơ hội chuyển tín hiệu cancel tới `WebClient»/driver. Việc đã bắt đầu một lời gọi blocking trên `boundedElastic» có thể không dừng ngay dù subscriber cancel; đánh giá và kiểm soát bằng timeout ở nguồn.

## 9. Những lỗi phổ biến trong điểm mở rộng reactive

### Lỗi 1 — Dùng interface Servlet trong WebFlux

`HttpSecurity», `SecurityFilterChain», `OncePerRequestFilter», `AuthenticationManager», `UserDetailsService», `AccessDeniedHandler» là các API quen thuộc trong Servlet stack. WebFlux dùng `ServerHttpSecurity», `SecurityWebFilterChain», `WebFilter», `ReactiveAuthenticationManager», `ReactiveUserDetailsService», `ServerAccessDeniedHandler». Một số khái niệm giống nhau nhưng không thể thay interface và ép kiểu là chạy được.

### Lỗi 2 — Tưởng `Mono.just(blockingCall())» là reactive

Tham số của `Mono.just» được đánh giá ngay, trước khi publisher được trả về. Nếu cần cứu một thư viện sync, dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())» theo phạm vi hẹp; tốt nhất thay bằng client non-blocking.

### Lỗi 3 — Gọi `block()» ở `ReactiveAuthenticationManager» hoặc `ReactiveAuthorizationManager»

`block()» chờ dữ liệu ngay, phá khả năng phục vụ đồng thời của event-loop và có thể ném `IllegalStateException» khi chạy trên thread được Reactor đánh dấu non-blocking. Trả `Mono» của phép xác thực/quyền cho framework để framework subscribe đúng ngữ cảnh.

### Lỗi 4 — Dùng `subscribe()» hoặc callback riêng để cấp quyền

Nếu viết `permissionMono.subscribe(allowed -> allowedFlag.set(allowed))» rồi lập tức trả một `AuthorizationDecision» từ flag, sẽ xuất hiện race. Cách đúng là `permissionMono.map(AuthorizationDecision::new)» nằm ngay trong chuỗi authorization.

### Lỗi 5 — Đánh đồng `Mono.empty()» với thành công

`Mono.empty()» không phát phần tử; trong các điểm mở rộng nó có thể nghĩa là “không hỗ trợ token”, “không tìm thấy user” hoặc “không đưa ra quyết định”. Giải thích theo từng hợp đồng, dùng default deny ở authorization khi phù hợp, và không biến lookup lỗi thành empty làm che hỏng backend.

### Lỗi 6 — Lạm dụng `onErrorResume»

`onErrorResume(error -> Mono.just(true))» là **fail-open**. `onErrorResume(error -> Mono.empty())» cũng có thể sai nếu luồng sau đó dùng default permissive hoặc biến outage thành user không tồn tại. Xử lý có chọn lọc những exception đã hiểu; bảo lưu root cause/metric để phát hiện sự cố.

### Lỗi 7 — Truy cập `SecurityContextHolder» từ callback reactive

Thread thay đổi là bình thường. Dùng `ReactiveSecurityContextHolder»/Reactor Context. Với method security reactive, giữ kiểu trả về tương thích Reactor và bật `@EnableReactiveMethodSecurity» khi cần; không nhét `.block()» vào SpEL hay service quyền.

### Lỗi 8 — Giả định offload là vô hạn

`boundedElastic» là scheduler có giới hạn, vẫn có thể quá tải. Offload mọi thứ sang scheduler chỉ che đi vấn đề kiến trúc. Không dùng `parallel()» để chạy JDBC; `Schedulers.parallel()» phù hợp tác vụ CPU ngắn, không phải blocking I/O.

### Lỗi 9 — Bỏ qua lỗi từ IdP hoặc dịch vụ quyền

Một HTTP 503/token endpoint timeout là lỗi dependency, không phải quyền hợp lệ. Trả HTTP phù hợp mà không để lộ token, user, stack trace hay chi tiết tenant. Đừng để custom filter tự commit response sớm rồi chain tiếp tục ghi lần hai.

### Lỗi 10 — Chỉ test status, không test độ trễ hoặc cancellation

Một handler dùng `block()» vẫn có thể trả đúng 200, 401, 403 trong thử nghiệm đơn lẻ. Cần thêm test mô phỏng phụ thuộc chậm, lỗi timeout, concurrency, subscriber cancellation và cảnh báo khi event-loop bị giữ lâu.

## 10. Kiểm thử và quan sát hợp đồng reactive

Một bộ QA có giá trị cho điểm mở rộng Security reactive:

1. **Kiểm tra loại stack:** ứng dụng thực sự dùng Spring WebFlux; không vô tình thêm Servlet starter khiến Spring Boot chọn MVC.
2. **Hành vi chức năng:** anonymous thường nhận 401 khi cần đăng nhập, tài khoản được cấp quyền nhận 200, tài khoản thiếu quyền nhận 403.
3. **Ngữ cảnh:** `ReactiveSecurityContextHolder» truy cập đúng authentication sau khi pipeline chuyển scheduler.
4. **Lỗi phụ thuộc:** user service/entitlement/IdP timeout hoặc trả error phải không cấp quyền; có log/metric nội bộ phân biệt.
5. **Không blocking:** tìm trực tiếp `block()», `subscribe()», JDBC/JPA, `RestTemplate», `Thread.sleep», `get()/join()» trong security code và các hàm được gọi sâu bên dưới.
6. **Tải song song:** mô phỏng nhiều request, quan sát số event-loop thread, độ trễ p95/p99, Reactor Netty connection pool, `boundedElastic» queue, latency tới IdP/database.
7. **Cancellation:** bỏ request trước khi nguồn hoàn tất, kiểm tra việc cancel lan tới client/driver có hỗ trợ; không còn nhiệm vụ ngoài luồng tiếp tục cấp quyền.
8. **Thông tin nhạy cảm:** không log raw password, Basic Authorization header, access/refresh token, session cookie, khóa ký, stack trace gửi client.
9. **Conformance API:** review đúng chữ ký `ReactiveAuthenticationManager», `ReactiveAuthorizationManager», `ServerAuthenticationConverter» và handler theo Spring Security version thực tế.

Có thể dùng **BlockHound** trong môi trường kiểm thử để phát hiện nhiều thao tác blocking trên thread non-blocking, nếu phiên bản Java/Reactor/BlockHound tương thích. Đây là **công cụ bổ trợ**, không phát hiện mọi blocking hoặc mọi vấn đề hiệu năng; kết hợp static code review, integration test và đo tải mới đủ tin cậy.

Với `StepVerifier», có thể kiểm tra publisher thành công/lỗi/empty và timeout. Với `WebTestClient», kiểm tra toàn bộ HTTP contract. Ví dụ test trong phần 5 đã chứng minh đường 401/403/200; bổ sung test khi quyền bị lỗi là trách nhiệm của adapter thực tế để không phát sinh fail-open.

## 11. Lộ trình rà soát một custom security extension

Khi cần thêm một cơ chế xác thực/phân quyền mới vào WebFlux:

1. **Chọn đúng hook:** parse credential bằng `ServerAuthenticationConverter», authenticate bằng `ReactiveAuthenticationManager», authorize bằng `ReactiveAuthorizationManager»; dùng exception handler đúng cho reactive. Đừng đưa mọi logic vào một `WebFilter» tự viết nếu framework đã có hook.
2. **Vẽ đường I/O:** mỗi lần đọc account, token, role, tenant, session, JWK hoặc entitlement đang dùng thư viện nào? Có đồng bộ/đợi thread ở đâu?
3. **Chuyển sang client reactive thật** khi có thể; nếu không, cô lập nguồn blocking bằng `fromCallable + boundedElastic», giới hạn tài nguyên và ghi rõ nợ kỹ thuật.
4. **Đặt policy fail-closed:** kết quả rỗng, token không hợp lệ, timeout, service lỗi, cancel đều không được tự động cho phép.
5. **Compose toàn bộ pipeline:** trả `Mono»/`Flux», dùng `flatMap» cho I/O, không tự `subscribe» hay `block». Đọc security context bằng Reactor Context.
6. **Tách phản hồi và quan sát:** client nhận HTTP hợp lý, hệ thống nhận root cause/metric; không lộ thông tin xác thực.
7. **Viết test:** ít nhất anonymous, thiếu quyền, đủ quyền, phụ thuộc chậm/hỏng, cancellation nếu có side effect, và tải song song nếu thay đổi ảnh hưởng throughput.

## 12. Kết luận

- **Trả `Mono» không đủ:** các thao tác trong security chain cũng phải không blocking hoặc được cô lập đúng ranh giới.
- **`flatMap» kết nối lời gọi bất đồng bộ**, còn `block()» phá chuỗi; `subscribe()» trong filter/manager có thể tách quyền, lỗi và cancellation khỏi request.
- **Spring Security WebFlux dùng hook reactive và Reactor Context**, không mặc định dùng `ThreadLocal SecurityContextHolder» của Servlet.
- **Fail closed** khi không xác minh được credential/quyền; phân loại empty, false, error và timeout theo đúng hợp đồng.
- `boundedElastic» là cầu nối có giới hạn cho API blocking; ưu tiên R2DBC, `WebClient» và reactive SDK cho hệ thống mới.
- Kiểm thử cả **ngữ nghĩa bảo mật, error/timeout, không blocking và hành vi khi tải cao**.

## Tài liệu tham khảo chính thức

- Spring Security — Reactive Applications: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- Spring Security — Reactive Method Security và Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security 6.3 API — `ReactiveAuthorizationManager»: https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/ReactiveAuthorizationManager.html
- Project Reactor — Reactor 3 Reference Guide, FAQ “How Do I Wrap a Synchronous, Blocking Call?”: https://projectreactor.io/docs/core/release/reference/
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html