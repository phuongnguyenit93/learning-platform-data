# Mono, Flux và Publisher trong luồng xử lý bảo mật Spring Security WebFlux

## Mục tiêu

Bài học giúp bạn hiểu `Publisher<T>`, `Mono<T>` và `Flux<T>`, lần theo luồng xác thực/phân quyền trong Spring Security WebFlux, truy cập danh tính qua `Reactor Context`, chọn toán tử reactive phù hợp và tránh các lỗi như `block()`, `subscribe()` thủ công hoặc hiểu sai `Mono.empty()`.

## 1. Tại sao luồng bảo mật WebFlux dùng Publisher?

Trong Spring MVC/Servlet, xử lý request thường được lập trình theo lối đồng bộ và ứng dụng có thể dựa vào một thread để giữ `SecurityContext` qua `ThreadLocal`. Trong Spring WebFlux, một request đi qua nhiều thao tác I/O bất đồng bộ, có thể đổi thread. Vì thế, Spring Security reactive phối hợp với Reactor để giữ dữ liệu xác thực gắn với **subscription của request**, thay vì giả định danh tính gắn cố định với thread.

`SecurityWebFilterChain` bảo vệ exchange HTTP. Các filter, bộ xác thực và controller kết hợp qua những publisher, để framework quản lý việc đăng ký nhận tín hiệu, thực thi, lỗi và hủy request. Việc trả về `Mono` hay `Flux` **không tự làm một thao tác blocking trở thành non-blocking**; driver truy vấn, HTTP client và thư viện được gọi cũng phải phù hợp.

## 2. Phân biệt Publisher, Mono, Flux

| Loại | Số phần tử `onNext` | Ví dụ trong bảo mật |
| --- | --- | --- |
| `Publisher<T>` | Giao diện chung, không quy định số lượng | Hợp đồng Reactive Streams để `Subscriber` đăng ký |
| `Mono<T>` | 0 hoặc 1 | `Mono<Authentication>`, `Mono<SecurityContext>`, một kết quả truy vấn |
| `Flux<T>` | 0 đến nhiều | `Flux<Report>` hoặc các bản ghi được trả sau khi kiểm tra quyền |
| `Mono<Void>` | Không có phần tử giá trị | Chuỗi `WebFilter.filter(...)` hoàn tất hoặc báo lỗi |

`org.reactivestreams.Publisher<T>` định nghĩa `subscribe(Subscriber)`. Reactor triển khai giao diện này bằng `Mono` và `Flux`, cùng những toán tử như `map`, `flatMap`, `filter`, `switchIfEmpty`, `onErrorResume`.

Một subscription có các tín hiệu chính:

1. `onSubscribe`: nhận `Subscription`; subscriber có thể yêu cầu số lượng phần tử qua `request(n)`.
2. `onNext(value)`: nhận một giá trị, tối đa một lần với `Mono`.
3. `onComplete`: hoàn tất bình thường. `Mono.empty()` không phát `onNext` nhưng vẫn hoàn tất.
4. `onError(error)`: kết thúc bằng lỗi; không phát `onComplete` sau `onError`.
5. `cancel()`: downstream hủy quan tâm; upstream nên ngừng công việc và giải phóng tài nguyên.

Phần lớn publisher Reactor được tạo từ nguồn cold: thao tác được kích hoạt khi có subscription và có thể chạy lại khi đăng ký lần nữa. Các nguồn hot hoặc publisher được chia sẻ/cache là ngoại lệ. **Subscription là cơ chế xử lý dữ liệu, không phải một hình thức cấp quyền**.

Cách chọn: trả `Mono` khi logic tạo không quá một kết quả (một danh tính hoặc một bản ghi); trả `Flux` khi logic tạo nhiều kết quả; trả `Mono<Void>` khi chỉ cần tín hiệu hoàn tất, ví dụ ở filter HTTP. Không dùng `Flux` chỉ vì muốn "bất đồng bộ": `Mono` cũng bất đồng bộ.

## 3. Publisher nằm ở đâu trong quy trình xác thực/phân quyền?

Đây là sơ đồ **khái niệm**, không khẳng định mọi request đều qua tất cả filter hay theo đúng một thứ tự trong mọi cấu hình:

```text
HTTP request
  |
  v
ServerWebExchange -> SecurityWebFilterChain / WebFilter
  |
  +--> Tách credential khỏi request (nếu có)
  |       ServerAuthenticationConverter -> Mono<Authentication>
  |
  +--> ReactiveAuthenticationManager.authenticate(...)
  |       Mono<Authentication>: thành công / rỗng / lỗi
  |
  +--> SecurityContext trong Reactor Context
  |       có thể kết hợp ServerSecurityContextRepository
  |       tùy cơ chế lưu/khôi phục security context
  |
  +--> Authorization cho HTTP exchange hoặc method
  |       đủ quyền: tiếp tục; thiếu quyền: từ chối
  |
  v
Controller/Service -> Mono<T> hoặc Flux<T>
  |
  v
Framework subscribe, ghi HTTP response
WebFilterChain hoàn tất bằng Mono<Void>
```

Vai trò từng thành phần:

- `SecurityWebFilterChain` được cấu hình bởi `ServerHttpSecurity`; nó là chuỗi filter của **WebFlux**, khác `SecurityFilterChain` dành cho Servlet.
- `AuthenticationWebFilter` có thể dùng `ServerAuthenticationConverter` để tạo `Authentication` rồi gọi `ReactiveAuthenticationManager` cho request phù hợp. Nếu không có credential hoặc filter không khớp, nhánh này có thể được bỏ qua.
- `ReactiveAuthenticationManager` xác minh thông tin đăng nhập và trả publisher của đối tượng `Authentication` sau xác thực.
- `ReactiveSecurityContextHolder` đọc/thiết lập `SecurityContext` trong Reactor Context của luồng.
- `authorizeExchange` và reactive method security thực hiện **authorization**, tức đánh giá có được phép truy cập hay không.
- `WebFilter.filter(ServerWebExchange, WebFilterChain)` trả `Mono<Void>` để biểu thị hoàn tất/lỗi xử lý request. Nó không trả boolean "được phép".

**Authentication** hỏi "người dùng là ai?"; **authorization** hỏi "người dùng được làm gì?". Có credential hợp lệ không bảo đảm truy cập được mọi tài nguyên.

### Ba trường hợp của `Mono<Authentication>`

Theo hợp đồng `ReactiveAuthenticationManager.authenticate(...)`:

- Thành công: publisher phát một `Authentication` hợp lệ rồi complete.
- `Mono.empty()`: manager **không xác định được** việc xác thực cho đầu vào, chẳng hạn không hỗ trợ loại token.
- `Mono.error(...)`: manager đã thử và xác thực **thất bại** (ví dụ `BadCredentialsException`).

Đừng đổi mọi lỗi mật khẩu thành `Mono.empty()` bằng `onErrorResume` chung. Khi ở **controller** hoặc repository, `Mono.empty()` lại có thể chỉ là "không có dữ liệu". Không suy ra trực tiếp 401, 403 hay "cho phép" từ một `Mono` rỗng; mã HTTP do Spring Security và cấu hình exception handling/entry point quyết định.

## 4. Toán tử Reactor cần nắm khi đọc code bảo mật

| Toán tử | Mục đích | Ví dụ |
| --- | --- | --- |
| `map` | Biến đổi một giá trị đồng bộ | `Authentication -> username` |
| `flatMap` | Biến một giá trị thành `Mono` khác và nối vào chuỗi | Tải profile bằng repository reactive |
| `flatMapMany` | Biến kết quả `Mono` thành `Flux` | Lấy nhiều bản ghi theo username đã xác thực |
| `filter` | Giữ phần tử thỏa điều kiện | Lọc dữ liệu; không thay thế bảo mật endpoint |
| `switchIfEmpty` | Nhánh khi không có giá trị | Chọn phản hồi phù hợp cho trường hợp không tìm thấy |
| `onErrorResume` | Nhánh xử lý lỗi cụ thể | Khôi phục lỗi nghiệp vụ có chủ đích |
| `defer`, `deferContextual` | Tạo publisher lúc subscribe, có thể đọc context | Tránh tính toán quá sớm |
| `contextWrite` | Bổ sung Reactor Context nhìn thấy bởi upstream | Cung cấp dữ liệu cho subscription |
| `doOnNext`, `doOnError` | Quan sát tín hiệu | Log/audit có kiểm soát, không subscribe thêm |
| `concatMap` | Nối publisher con theo thứ tự | Giữ thứ tự xử lý khi cần |

Ví dụ Java 17+ dưới đây là **một chương trình console độc lập về mã nguồn**, cần thư viện `reactor-core` trên classpath. Trong dự án Spring Boot WebFlux, dependency đó đã được kéo theo:

**`src/main/java/demo/ReactorSignalsDemo.java`**

```java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactorSignalsDemo {
    public static void main(String[] args) {
        Mono<String> user = Mono.just("linh")
                .map(String::toUpperCase);

        Flux<Integer> ids = Flux.just(1, 2, 3)
                .filter(id -> id != 2)
                .map(id -> id * 10);

        System.out.println(user.block());
        System.out.println(ids.collectList().block());
    }
}
```

Stdout chính xác:

```text
LINH
[10, 30]
```

`block()` trong ví dụ này **chỉ phục vụ chương trình console/test**. Không dùng cách đó trên đường xử lý HTTP của WebFlux. Với I/O bất đồng bộ, hãy nối publisher bằng `flatMap`. Đoạn minh họa sau nằm **trong một phương thức trả `Mono<Profile>`**, giả định repository đã cung cấp `Mono<Profile> findByUsername(String)`:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .flatMap(username -> profileRepository.findByUsername(username));
```

Dùng `map` ở bước gọi repository sẽ tạo `Mono<Mono<Profile>>`; `flatMap` cho ra `Mono<Profile>` như hợp đồng mong muốn.

## 5. Reactor Context: nơi mang danh tính

Trong ứng dụng reactive, đọc principal bằng:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
}
```

Đây là **đoạn phương thức minh họa** đặt trong một component xử lý reactive request có context. `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>`; không dùng `SecurityContextHolder.getContext()` đồng bộ để giả định một request luôn chạy trên một thread.

Hiểu đúng Reactor Context:

1. Context gắn với **subscriber/subscription**, có thể theo chuỗi khi Reactor chuyển thread, chứ không phải một biến thread-local toàn cục.
2. Context bất biến theo nghĩa phương thức thay đổi trả context mới; `contextWrite` tạo context cho **phía upstream** tính từ vị trí toán tử đó.
3. Spring Security gắn context theo cơ chế filter xác thực. Trong một unit test hoặc publisher riêng, có thể dùng `ReactiveSecurityContextHolder.withAuthentication(authentication)`.
4. Reactor Context chỉ đại diện ngữ cảnh lúc xử lý subscription; **không phải** cơ chế lưu session hoặc token cho request tiếp theo.
5. Khi tích hợp callback, executor hay API nằm ngoài Reactor, cần kiểm tra cách truyền context; không giả định nó tự đi theo mọi thread.

Minh họa Context cơ bản:

```java
Mono<String> trace = Mono.deferContextual(ctx ->
        Mono.just("user=" + ctx.get("username")))
    .contextWrite(ctx -> ctx.put("username", "linh"));

// Trong main hoặc test, trace.block() tạo chuỗi: "user=linh".
```

Khóa `username` ở đây chỉ dùng để học `Context`. **Tự gắn khóa này không có nghĩa người dùng đã được xác thực.** Khi làm việc với Spring Security, sử dụng `ReactiveSecurityContextHolder` cùng manager và quy tắc xác thực thực tế.

## 6. Ví dụ WebFlux: endpoint công khai, danh tính và báo cáo

Dùng Spring Boot với Java 17+, có `spring-boot-starter-webflux` và `spring-boot-starter-security`. Trong một dự án Gradle Spring Boot đã cấu hình plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Không đồng thời thêm `spring-boot-starter-web` cho ví dụ này: khi cả MVC và WebFlux có mặt, Spring Boot thường chọn ứng dụng Servlet nếu không cấu hình loại ứng dụng tường minh.

**`src/main/java/demo/securityreactive/DemoApplication.java`** (một file Java 17+ với một lớp public):

```java
package demo.securityreactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/reports").hasRole("ANALYST")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("VIEWER")
                .build();
        UserDetails analyst = User.withUsername("analyst")
                .password(encoder.encode("analyst-pass"))
                .roles("ANALYST")
                .build();
        return new MapReactiveUserDetailsService(viewer, analyst);
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    Mono<String> publicMessage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> "hello " + authentication.getName());
    }

    @GetMapping("/reports")
    Flux<Report> reports() {
        return Flux.just(
                new Report("R1", "internal"),
                new Report("R2", "internal")
        );
    }
}

record Report(String id, String classification) {}
```

Chạy trong dự án có Gradle Wrapper bằng `./gradlew bootRun` (PowerShell: `.\gradlew.bat bootRun`). Mẫu không thể biên dịch bằng `javac` đơn lẻ nếu thiếu các thư viện Spring/Reactor; Gradle cung cấp classpath đó. Các lớp package-private và record cùng một file vẫn hợp lệ trong Java 17.

Thử các request sau:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u viewer:viewer-pass http://localhost:8080/me
curl -i -u viewer:viewer-pass http://localhost:8080/reports
curl -i -u analyst:analyst-pass http://localhost:8080/reports
```

| Request | Kết quả mong đợi | Giải thích |
| --- | --- | --- |
| `GET /public`, anonymous | `200`, body `public` | `permitAll()` |
| `GET /me`, anonymous | `401` theo HTTP Basic trong ví dụ | Chưa được xác thực |
| `GET /me`, viewer | `200`, body `hello viewer` | Đã xác thực, đọc principal từ Reactor Context |
| `GET /reports`, viewer | `403` | Đã xác thực nhưng thiếu `ROLE_ANALYST` |
| `GET /reports`, analyst | `200`, dữ liệu báo cáo | Có `ROLE_ANALYST` |

`roles("ANALYST")` sinh authority `ROLE_ANALYST`, nên `hasRole("ANALYST")` tự áp dụng tiền tố `ROLE_`. Định dạng body/header lỗi phụ thuộc cấu hình và content negotiation; điều cần kiểm chứng ở đây là **ranh giới truy cập**.

Các tài khoản/mật khẩu hardcode chỉ để học ở máy cục bộ. Trong production, cần quản lý credential an toàn, không giữ mật khẩu mẫu trong source. Bài này chỉ có `GET`; **không tùy tiện vô hiệu hóa CSRF** cho ứng dụng trình duyệt dùng cookie/session.

### Theo dõi `GET /reports`

1. Request đi vào WebFlux và các filter bảo mật.
2. HTTP Basic chuyển credential phù hợp thành `Authentication`; manager xác minh.
3. Quy tắc `hasRole("ANALYST")` được đánh giá trước khi controller được gọi.
4. Nếu thiếu quyền, truy cập bị từ chối. Nếu đủ quyền, controller trả `Flux<Report>` với hai phần tử.
5. Framework subscribe và mã hóa kết quả thành HTTP response. Controller **không tự gọi `subscribe()`**.

Việc trả `Flux<Report>` chỉ có nghĩa nhiều phần tử nghiệp vụ. Nó **không bảo đảm** hệ thống tái kiểm tra quyền trên từng bản ghi. Nếu bản ghi có chủ sở hữu hoặc mức nhạy cảm riêng, phải thiết kế điều kiện truy vấn và kiểm tra quyền theo bản ghi; filter ở endpoint chỉ là một tầng bảo vệ.

## 7. Test Reactor Context bằng StepVerifier

Để kiểm tra publisher có thể đọc danh tính trong một subscription mà không chạy HTTP server, tạo file test sau. Cần `spring-boot-starter-test` và `reactor-test` như đã khai báo:

**`src/test/java/demo/securityreactive/ReactiveContextTest.java`**

```java
package demo.securityreactive;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveContextTest {
    @Test
    void readsAuthenticatedPrincipalFromContext() {
        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        "linh",
                        "unused",
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))
                );

        Mono<String> username = ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(authentication)
                );

        StepVerifier.create(username)
                .expectNext("linh")
                .verifyComplete();
    }
}
```

Chạy `./gradlew test --tests demo.securityreactive.ReactiveContextTest` (PowerShell: `.\gradlew.bat test --tests demo.securityreactive.ReactiveContextTest`). Test phải PASS: `StepVerifier` subscribe, thấy đúng một giá trị `linh` rồi `onComplete`. Đây là test truyền context, **không phải** test xác minh mật khẩu hay HTTP 401/403; cần kiểm thử endpoint riêng.

## 8. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `block()`, `blockFirst()`, `blockLast()` trong controller/WebFilter | Chặn event loop hoặc gây lỗi trên thread non-blocking | Trả publisher và nối bằng `flatMap`, `concatMap` |
| `subscribe()` thủ công trong controller/filter | Mất quản lý vòng đời response, lỗi, cancellation hoặc context | Trả `Mono`/`Flux` để framework subscribe |
| `SecurityContextHolder.getContext()` kiểu Servlet | Có thể thiếu hoặc đọc sai principal do đổi thread | Dùng `ReactiveSecurityContextHolder.getContext()` |
| `map` với hàm trả `Mono` | Tạo `Mono<Mono<T>>` | Dùng `flatMap` |
| Nuốt `AuthenticationException` bằng `onErrorResume(... -> Mono.empty())` | Che giấu credential sai và sai hợp đồng manager | Phân biệt không xử lý được token với xác thực thất bại |
| Tưởng `Flux.filter(...)` đủ phân quyền bản ghi | Có thể lộ thông tin ở service/truy vấn khác | Kiểm soát quyền ở endpoint, service và điều kiện lấy dữ liệu |
| Đặt `contextWrite` ở vị trí không đúng | Toán tử downstream không nhìn thấy giá trị mới | Nhớ Context truyền từ subscriber lên upstream |
| `Mono.just(blockingCall())` | Hàm blocking chạy ngay khi dựng publisher | Dùng nguồn non-blocking hoặc trì hoãn/cô lập blocking đúng cách |
| Dùng `flatMap` rồi giả định luôn giữ thứ tự | Tác vụ con có thể hoàn tất lệch thứ tự | Dùng `concatMap` khi thứ tự quan trọng |

Một số tình huống nâng cao cũng cần chú ý:

- **Backpressure:** `request(n)` giúp điều tiết nhu cầu dữ liệu giữa subscriber và publisher tương thích. Nó không phải giới hạn request/rate limit và không thay thế phân quyền.
- **Cancellation:** khi client ngắt stream, nguồn reactive nên dừng công việc, trả tài nguyên; đừng tạo subscription phụ khiến việc đó khó thực hiện.
- **Luồng dài:** kiểm tra quyền tại đầu HTTP request không đồng nghĩa tự động kiểm tra lại khi role bị thu hồi trong lúc stream đang mở. Với yêu cầu thu hồi tức thời, cần thiết kế kiểm tra lại/đóng stream.
- **Nguồn blocking:** JDBC đồng bộ hoặc SDK blocking không trở thành non-blocking chỉ nhờ bọc trong `Mono`. Ưu tiên driver reactive hoặc cách cô lập blocking có kiểm soát, đồng thời xem xét cách truyền context.
- **Method security:** có thể dùng `@EnableReactiveMethodSecurity` và `@PreAuthorize` cho phương thức trả `Mono`/`Flux`. Kiểm tra phương thức thực sự đi qua Spring proxy và viết test cho quyền; lời gọi nội bộ trong cùng bean có thể bỏ qua proxy.

## 9. Bài tập tự kiểm tra

1. Thêm `GET /profile` trả `Mono<String>` chứa username. Chứng minh anonymous bị chặn và tài khoản hợp lệ đọc đúng danh tính.
2. Thêm vai trò `AUDITOR` và endpoint chỉ dành cho role đó. Phân biệt thử nghiệm 401 (chưa đăng nhập) với 403 (đăng nhập nhưng thiếu quyền).
3. Thay `Flux.just(...)` bằng repository reactive truy vấn theo username đã xác thực; thử một user truy cập bản ghi của user khác.
4. Viết StepVerifier cho trường hợp có và không có Reactor Security Context; giải thích tại sao `Mono.empty()` không tự đồng nghĩa HTTP 403.
5. Tạo một `Flux` chậm và hủy subscription trong test; quan sát việc dừng producer và cleanup.

**Ghi nhớ:** `Publisher` xác định hợp đồng phát tín hiệu; `Mono`/`Flux` mô tả số lượng giá trị; Spring Security quyết định xác thực/phân quyền trong pipeline đó. Đọc danh tính bằng Reactor Context, để framework quản lý subscription và áp dụng kiểm tra quyền tại đúng lớp nghiệp vụ.

## Tham khảo chính thức

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security API — ReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
