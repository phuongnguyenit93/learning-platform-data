# ReactiveAuthenticationManager và các hợp đồng trả về Mono

> **Phạm vi:** Spring Security trong ứng dụng **Spring WebFlux (reactive)**, tập trung vào cách `ReactiveAuthenticationManager` xác thực một `Authentication` và ý nghĩa chính xác của các tín hiệu `Mono<Authentication>`. Ví dụ dùng Java 17+ và Spring Security 6.x/7.x.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `ReactiveAuthenticationManager` trong luồng xác thực WebFlux và phân biệt nó với `ReactiveAuthorizationManager`, `ReactiveUserDetailsService` và `AuthenticationManager` của Servlet.
2. Phân biệt ba kết quả hợp lệ của `authenticate`: **phát ra `Authentication`**, **hoàn tất rỗng**, **phát lỗi**.
3. Biết khi nào dùng `Mono.empty()` và khi nào dùng `Mono.error(AuthenticationException)`; tránh biến thông tin đăng nhập sai thành “không hỗ trợ”.
4. Cấu hình manager dựa trên `ReactiveUserDetailsService`, kiểm tra bằng `StepVerifier`, và hiểu cách kết quả tới WebFlux filter chain.
5. Nhận diện lỗi thường gặp liên quan đến blocking, Reactor Context, lỗi bị nuốt và đối tượng `Authentication` được đánh dấu đã xác thực không đúng cách.

## 2. Hợp đồng cốt lõi

`ReactiveAuthenticationManager` thuộc `org.springframework.security.authentication` và có một phương thức chức năng:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

Đầu vào là một `Authentication` cần được kiểm tra: thường là token **chưa xác thực** do lớp lấy thông tin đăng nhập tạo ra (ví dụ `UsernamePasswordAuthenticationToken.unauthenticated(username, password)`). Đầu ra là publisher `Mono<Authentication>` biểu diễn **tối đa một** kết quả xác thực. Kiểu `Mono` mô tả tín hiệu bất đồng bộ, không phải một `Authentication` đã có sẵn.

| Kết quả publisher | Ý nghĩa hợp đồng | Ví dụ |
| --- | --- | --- |
| `onNext(authentication)` rồi `onComplete` | Manager xác thực thành công; đối tượng trả về phải thể hiện principal/authorities đáng tin cậy và trạng thái xác thực phù hợp. | `Mono.just(authenticatedToken)` |
| `onComplete`, không có `onNext` | Manager **không thể kết luận** về token này, điển hình là loại token không thuộc trách nhiệm của nó. Đây không phải tuyên bố “mật khẩu sai”. | `Mono.empty()` |
| `onError(error)` | Manager đã thử xác thực nhưng **thất bại**, ví dụ sai credential, tài khoản bị khóa; thường dùng subclass của `AuthenticationException`. Lỗi hạ tầng cũng có thể đi theo kênh `onError` nhưng phải được phân loại/xử lý đúng. | `Mono.error(new BadCredentialsException("Bad credentials"))` |

Quy tắc quan trọng:

- **Token không được hỗ trợ** bởi manager hiện tại: trả `Mono.empty()` để một tầng điều phối khác có thể thử manager phù hợp.
- **Token được hỗ trợ nhưng credential sai hoặc account không hợp lệ**: trả `Mono.error(...)`, không biến thất bại thành `Mono.empty()`.
- **Thành công**: phát ra đối tượng `Authentication` đã được kiểm tra; không coi việc trả lại token đầu vào chưa xác thực là thành công.
- **Không trả `null`** thay cho `Mono` và không tạo `Mono.just(null)`: Reactor không cho phép giá trị `null` trong `onNext`.
- **Không trả `Mono.never()`** cho trường hợp không biết xử lý: nó không hoàn tất, khiến pipeline có thể chờ mãi; `Mono.empty()` mới là kết quả “không xác định” hợp lệ.

Một `Mono` có thể *hoàn tất rỗng* mà không có exception. Ngược lại, `onError` là tín hiệu kết thúc lỗi, không có `onComplete` sau nó. `AuthenticationException` có thể xuất hiện từ kiểm tra credential hoặc trạng thái người dùng; đừng dựa vào HTTP status để suy ngược cả ba trạng thái vì cách ánh xạ sang HTTP còn phụ thuộc filter/handler đang sử dụng.

### So sánh với API đồng bộ

| Servlet/blocking | WebFlux/reactive |
| --- | --- |
| `AuthenticationManager.authenticate(Authentication)` trả `Authentication` hoặc ném `AuthenticationException` | `ReactiveAuthenticationManager.authenticate(Authentication)` trả `Mono<Authentication>`: có giá trị, rỗng hoặc lỗi |
| Thường kết nối `SecurityFilterChain` và bộ lọc Servlet | Kết nối `SecurityWebFilterChain` và `WebFilter` |
| Context truyền thống thường gắn với thread | Context bảo mật reactive đi theo **Reactor Context** của subscription |

Không lấy `AuthenticationManager` từ cấu hình Servlet rồi giả định có thể gọi trực tiếp, đồng bộ trong event loop WebFlux.

## 3. Manager nằm ở đâu trong luồng WebFlux?

```text
HTTP request
    |
    v
SecurityWebFilterChain (các WebFilter bảo mật)
    |
    v
AuthenticationWebFilter (đối với cơ chế xác thực được cấu hình)
    |-- matcher xác định request có cần thử xác thực không
    |-- ServerAuthenticationConverter đọc credential/token từ request
    |      \-- Mono.empty() ở bước converter: không tạo lượt xác thực
    |
    v
ReactiveAuthenticationManager.authenticate(token)
    |-- Mono<Authentication> có giá trị --> xử lý thành công,
    |                                      SecurityContext/Reactor Context
    |-- Mono.empty() ---------------------> không manager nào quyết định
    |                                      (cách xử lý tùy tầng điều phối)
    \-- Mono.error(...) ------------------> xử lý lỗi xác thực
    |
    v
authorizeExchange / ReactiveAuthorizationManager
    |
    v
Handler hoặc phản hồi từ chối truy cập
```

Diễn giải theo từng trách nhiệm:

1. **`SecurityWebFilterChain`** là chuỗi WebFilter bảo mật cho request được chọn. Đây là cấu trúc WebFlux, khác `SecurityFilterChain` của Servlet.
2. **`ServerAuthenticationConverter`** lấy dữ liệu từ HTTP (ví dụ header Basic/Bearer) và tạo token cần xác thực. Nếu converter trả rỗng thì có thể **không có lượt xác thực nào** cho request; trạng thái này khác với *manager đã nhận token rồi trả rỗng*.
3. **`ReactiveAuthenticationManager`** kiểm tra token và trả một trong ba tín hiệu đã nêu. Nó **xác thực danh tính**; nó không tự quyết định request có được vào endpoint `/admin` hay không.
4. Khi xác thực thành công, các filter/handler phù hợp xây dựng và đưa `SecurityContext` vào luồng reactive; `ReactiveSecurityContextHolder` truy cập context qua Reactor Context.
5. **Phân quyền** (ví dụ `authorizeExchange().anyExchange().authenticated()` hoặc kiểm tra role) diễn ra theo cấu hình. Người dùng đã xác thực vẫn có thể bị từ chối vì thiếu quyền.

Lưu ý: sơ đồ là mô hình để học quan hệ trách nhiệm. Thứ tự WebFilter, handler được chọn và phản hồi cụ thể tùy cơ chế HTTP Basic, form login, resource server, filter tùy biến và cấu hình ứng dụng. Đừng mặc định một `Mono.empty()` từ manager sẽ tự động cho đi tiếp hoặc chắc chắn trả 401 trong mọi cấu hình.

## 4. Hiểu sâu ba tín hiệu qua mã Java

### 4.1. Thành công: phát ra một Authentication

```java
Authentication authenticated =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );

Mono<Authentication> success = Mono.just(authenticated);
```

`authenticated(...)` chỉ nên được gọi **sau khi hệ thống đã xác minh credential/token thực sự**. Đoạn trên chỉ minh họa hình dạng kết quả đã được tin cậy; nó **không tự thực hiện kiểm tra mật khẩu**. Bản thành công thường giữ principal và granted authorities, đồng thời nên hạn chế giữ bí mật trong credentials.

### 4.2. Không xác định: hoàn tất rỗng

```java
ReactiveAuthenticationManager onlyUsernamePassword = request -> {
    if (!(request instanceof UsernamePasswordAuthenticationToken)) {
        return Mono.empty(); // Manager này không xử lý loại token ấy
    }
    // Nhánh xử lý username/password thực tế phải gọi hệ thống xác thực.
    return Mono.error(new BadCredentialsException("Bad credentials"));
};
```

Đừng dùng `Mono.empty()` khi username/password sai. Nếu manager đầu tiên nuốt lỗi này, một manager tiếp theo có thể được thử ngoài ý muốn, tạo sai lệch chính sách bảo mật.

### 4.3. Thất bại: phát lỗi

```java
Mono<Authentication> invalidPassword =
        Mono.error(new BadCredentialsException("Bad credentials"));
```

Thông thường hãy để `AuthenticationException` truyền tới lớp xử lý lỗi xác thực. Trong HTTP Basic, failure handler phù hợp thường tạo challenge/401; yêu cầu đã xác thực nhưng thiếu quyền thường dẫn tới 403. Mã phản hồi cuối cùng có thể được cấu hình lại; không coi 401/403 là giá trị mà chính manager trả về.

### 4.4. Các toán tử Reactor cần phân biệt

- `switchIfEmpty(other)` chỉ kích hoạt khi upstream **hoàn tất rỗng**. Dùng có chủ đích để chọn manager dự phòng hoặc chuyển trạng thái rỗng thành lỗi tại ranh giới yêu cầu phải xác thực.
- `onErrorResume(...)` xử lý **lỗi**, không xử lý `Mono.empty()`. Tránh `onErrorResume(e -> Mono.empty())` áp dụng tràn lan: nó che giấu credential sai hoặc sự cố hệ thống.
- `flatMap(...)` ghép công việc trả về `Mono` mà không cần `block()`.
- `Mono.defer(...)` trì hoãn tạo tác vụ đến khi subscribe; `Mono.fromCallable(...)` phù hợp để bọc thao tác đồng bộ, nhưng thao tác blocking phải được lập lịch thích hợp.
- `doOnNext`, `doOnError` dành cho quan sát; không nên sửa trạng thái bảo mật một cách bí mật trong các side effect.
- `retry()` không phải chính sách mặc định cho xác thực: thử lại vô hạn khi sai mật khẩu hoặc dịch vụ lỗi có thể làm tăng tải và tạo hành vi khó kiểm soát.

`Mono` thường là publisher *cold*: việc khai báo pipeline chưa đồng nghĩa request tới kho người dùng đã chạy. WebFlux/Spring Security là thành phần subscribe trong luồng xử lý HTTP. Không tự `subscribe()` trong manager hoặc controller để “kích hoạt” xác thực vì subscription tách rời có thể làm mất xử lý lỗi và context.

## 5. Ví dụ hoạt động: HTTP Basic trong Spring WebFlux

Ví dụ sau dùng `UserDetailsRepositoryReactiveAuthenticationManager` thay vì tự viết logic kiểm tra mật khẩu. Manager này dựa trên `ReactiveUserDetailsService` và `PasswordEncoder`.

**Chuẩn bị:** tạo ứng dụng Spring Boot tương thích Java 17+ với hai dependency **Spring Reactive Web (WebFlux)** và **Spring Security** bằng Spring Initializr hoặc dự án Boot tương đương. Đảm bảo sử dụng WebFlux thay vì thêm Spring MVC trong cùng ví dụ. Tệp nguồn `src/main/java/dev/demo/ReactiveAuthApplication.java`:

```java
package dev.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo123"))
                .roles("READER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    ReactiveAuthenticationManager reactiveAuthenticationManager(
            ReactiveUserDetailsService users, PasswordEncoder encoder) {
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/secure")
        String securePage() {
            return "secured";
        }
    }
}
```

Chạy ứng dụng bằng công cụ build đã tạo dự án (ví dụ `./gradlew bootRun` trên macOS/Linux, `gradlew.bat bootRun` trên Windows). Các lệnh HTTP để quan sát:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/secure
curl -i -u alice:demo123 http://localhost:8080/secure
curl -i -u alice:wrong http://localhost:8080/secure
```

| Yêu cầu | Kết quả mong đợi với cấu hình mặc định ở ví dụ |
| --- | --- |
| `GET /public` không credential | 200, body `public` vì `permitAll()` |
| `GET /secure` không credential | 401 và HTTP Basic challenge |
| `GET /secure` với `alice:demo123` | 200, body `secured` |
| `GET /secure` với `alice:wrong` | 401 do xác thực thất bại |

Giải thích:

- Converter của HTTP Basic tạo token chứa username/password khi có Basic credential hợp lệ về cú pháp.
- Manager truy vấn `ReactiveUserDetailsService`, dùng `PasswordEncoder` kiểm tra mật khẩu đã mã hóa; khi thành công, manager trả `Authentication` tin cậy.
- Rule `authenticated()` chỉ cho qua request có danh tính đã xác thực. `permitAll()` là **quy tắc phân quyền**, không yêu cầu manager phải xác thực mọi request công khai.
- Tài khoản cố định và mật khẩu demo chỉ dùng để học. Hệ thống thật cần kho người dùng phù hợp, quản trị bí mật, HTTPS, chống brute force và xử lý lỗi không tiết lộ trạng thái tài khoản.

**Giới hạn của ví dụ:** `MapReactiveUserDetailsService` chỉ lưu user trong bộ nhớ, không có persistence. Nếu dùng database thực, chọn client/reactive repository phù hợp và tránh gọi JDBC blocking trực tiếp trên event loop.

## 6. Kiểm thử hợp đồng bằng StepVerifier

Để cô lập **ý nghĩa ba tín hiệu** khỏi HTTP, tệp `src/test/java/dev/demo/ReactiveAuthenticationManagerContractTest.java` sau tạo manager giả lập. Nó cố ý kiểm tra chuỗi `good` để mô phỏng kết quả; **không dùng cách lưu/so sánh mật khẩu này trong sản phẩm**.

```java
package dev.demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveAuthenticationManagerContractTest {

    private ReactiveAuthenticationManager demoManager() {
        return request -> {
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }
            if (!"good".equals(request.getCredentials())) {
                return Mono.error(new BadCredentialsException("Bad credentials"));
            }
            Authentication authenticated =
                    UsernamePasswordAuthenticationToken.authenticated(
                            request.getPrincipal(),
                            null,
                            List.of(new SimpleGrantedAuthority("ROLE_READER"))
                    );
            return Mono.just(authenticated);
        };
    }

    @Test
    void successfulAuthenticationEmitsExactlyOneValue() {
        var input = UsernamePasswordAuthenticationToken
                .unauthenticated("alice", "good");

        StepVerifier.create(demoManager().authenticate(input))
                .assertNext(result -> {
                    assertTrue(result.isAuthenticated());
                    assertEquals("alice", result.getName());
                    assertTrue(result.getAuthorities().stream()
                            .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
                })
                .verifyComplete();
    }

    @Test
    void unsupportedTokenCompletesWithoutValue() {
        var input = new TestingAuthenticationToken("alice", "good");

        StepVerifier.create(demoManager().authenticate(input))
                .verifyComplete();
    }

    @Test
    void invalidCredentialsFailWithAuthenticationException() {
        var input = UsernamePasswordAuthenticationToken
                .unauthenticated("alice", "wrong");

        StepVerifier.create(demoManager().authenticate(input))
                .expectError(BadCredentialsException.class)
                .verify();
    }
}
```

Nếu dùng Gradle và dependency WebFlux/Security từ Spring Boot, bổ sung dependency kiểm thử Reactor nếu starter-test chưa mang theo:

```groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
}
```

Chạy `./gradlew test` (hoặc `gradlew.bat test` trên Windows). Ba test phải **pass**: test 1 chứng minh có một `onNext` rồi hoàn tất, test 2 chứng minh không có `onNext` nhưng hoàn tất bình thường, test 3 chứng minh có `onError` kiểu `BadCredentialsException`. Đây là kiểm thử contract, không khẳng định toàn bộ filter chain hay dữ liệu user thực đã được kiểm thử.

Để kiểm thử tích hợp HTTP, dùng `WebTestClient` gửi request không credential, credential sai và credential đúng; kiểm tra status/header và quyền truy cập route thật. Kiểm thử ở cả hai tầng giúp tránh nhầm “manager trả đúng tín hiệu” với “toàn bộ ứng dụng phản hồi đúng chính sách”.

## 7. Kết hợp nhiều manager đúng cách

Một ứng dụng có thể hỗ trợ nhiều cách xác thực, ví dụ username/password và bearer token. `DelegatingReactiveAuthenticationManager` thử các manager được cấu hình và sử dụng **kết quả không rỗng đầu tiên**. Trong Spring Security 6.5/7.x, lỗi ở delegate mặc định **không** được coi như kết quả rỗng để tự động thử manager kế tiếp (`continueOnError` mặc định là `false`).

Mẫu lựa chọn theo loại token:

```java
ReactiveAuthenticationManager usernamePasswordOnly =
        token -> token instanceof UsernamePasswordAuthenticationToken
                ? realUsernamePasswordManager.authenticate(token)
                : Mono.empty();

ReactiveAuthenticationManager combined =
        new DelegatingReactiveAuthenticationManager(
                bearerTokenManager,
                usernamePasswordOnly
        );
```

Đoạn trên là **mẫu tích hợp**, không phải một tệp biên dịch độc lập: `realUsernamePasswordManager` và `bearerTokenManager` cần được cung cấp từ cấu hình của ứng dụng; ví dụ chỉ thể hiện vai trò `Mono.empty()` cho loại token không thuộc trách nhiệm. Với cơ chế cụ thể như OAuth2 Resource Server, hãy ưu tiên cấu hình chuẩn của Spring Security để framework chọn đúng converter/manager thay vì tự ghép giao thức.

Không bật chế độ tiếp tục sau lỗi chỉ để “thử cho qua”: khi một manager đã nhận diện loại credential và kết luận sai, việc thử tiếp có thể làm thay đổi biên tin cậy. Nếu nghiệp vụ thực sự cần fallback, phải định nghĩa rõ loại token, loại lỗi, thứ tự ưu tiên, hành vi quan sát và kiểm thử các đường tấn công.

## 8. Reactor Context, thread và thao tác blocking

`ReactiveSecurityContextHolder` đọc thông tin xác thực từ Reactor Context gắn với **subscription**, không nên giả định nó nằm trong một `ThreadLocal` ổn định xuyên suốt các bước `flatMap`, `publishOn`, v.v.

Một handler/service chạy trong request đã được Spring Security xác thực có thể đọc:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
```

Đây là **đoạn phương thức minh họa**, cần import `reactor.core.publisher.Mono` và `org.springframework.security.core.context.ReactiveSecurityContextHolder` trong lớp chứa nó. Khi không có `SecurityContext`, publisher có thể hoàn tất rỗng. Không dùng `block()` hoặc `subscribe()` tự phát để lấy tên; nên trả `Mono` lên tầng WebFlux.

Về hiệu năng, “trả `Mono`” **không tự khiến công việc blocking thành non-blocking**. Ví dụ truy vấn JDBC, gọi SDK đồng bộ hoặc chạy thuật toán hash CPU-intensive trực tiếp trên event loop sẽ cản trở những request khác. Ưu tiên API reactive cho I/O; với thao tác bắt buộc đồng bộ, bọc tác vụ thích hợp bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, theo dõi tải và giới hạn concurrency. `ReactiveAuthenticationManagerAdapter` có thể chuyển một `AuthenticationManager` đồng bộ sang API reactive; nó là giải pháp tương thích, không biến nguồn dữ liệu blocking thành reactive thực chất.

Ví dụ lập lịch một hàm blocking **để minh họa**, không phải implementation manager đầy đủ:

```java
Mono<Boolean> matchesPassword(String raw, String encoded,
                              PasswordEncoder encoder) {
    return Mono.fromCallable(() -> encoder.matches(raw, encoded))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Cần import `PasswordEncoder`, `Mono` và `Schedulers`. Trong dự án thật, ưu tiên manager do framework cung cấp vì nó đã xử lý nhiều chi tiết như xác minh account, password encoder và cấu trúc exception. Không tạo thread/scheduler riêng cho từng request.

## 9. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Trả `Mono.empty()` khi mật khẩu sai | Có thể kích hoạt fallback manager và khiến logic an ninh khó kiểm soát | Với credential sai đã xác định, phát `BadCredentialsException` bằng `Mono.error` |
| Trả `Mono.just(tokenĐầuVào)` dù chưa xác thực | Cấp sai niềm tin hoặc khiến trạng thái principal/authorities không nhất quán | Chỉ tạo token tin cậy sau khi xác minh thành công |
| Trả `null` hoặc `Mono.just(null)` | Vi phạm Reactor contract, dẫn tới lỗi runtime | Luôn trả một `Mono` không null; dùng `Mono.empty()` khi không xử lý được loại token |
| `onErrorResume(e -> Mono.empty())` cho mọi lỗi | Nuốt lỗi credential và lỗi hạ tầng | Chỉ bắt loại lỗi được cho phép theo chính sách, giữ lỗi xác thực đúng nghĩa |
| `block()` trong manager/`WebFilter` | Khóa event-loop, giảm thông lượng hoặc phát sinh lỗi blocking | Dùng composition reactive; cô lập thao tác blocking trên scheduler phù hợp |
| `subscribe()` thủ công trong manager | Công việc rời khỏi chuỗi HTTP, lỗi và Reactor Context khó kiểm soát | Trả publisher cho Spring Security subscribe |
| Trộn `HttpSecurity` với `ServerHttpSecurity` | Lệch mô hình Servlet/WebFlux, cấu hình không áp dụng như tưởng | Dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và API reactive tương ứng |
| Ghi log password, bearer token, stack trace chi tiết ra response | Rò rỉ credential hoặc thông tin nội bộ | Ẩn dữ liệu nhạy cảm, ghi audit an toàn, phản hồi lỗi nhất quán |
| Cho rằng `Mono.empty()` từ manager đồng nghĩa request công khai | Nhầm xác thực với phân quyền; có thể tạo lỗ hổng | Phân quyền độc lập qua `authorizeExchange`, test các route được bảo vệ |
| Đặt `retry()` vô hạn quanh xác thực | Tăng tải, làm lỗi kéo dài và che giấu nguyên nhân | Chỉ retry hạ tầng idempotent theo chính sách có giới hạn, không retry credential sai |

## 10. Tự kiểm tra

1. Một manager chỉ hỗ trợ `UsernamePasswordAuthenticationToken` nhận một loại token bearer lạ. Nên trả gì? **`Mono.empty()`** nếu nó thực sự không biết xử lý loại token ấy.
2. Manager hỗ trợ username/password nhưng mật khẩu không đúng. Nên trả gì? **`Mono.error(new BadCredentialsException(...))`**.
3. Kết quả `Mono.just(authenticated)` đã có nghĩa endpoint `/admin` sẽ thành công? **Không**. Sau xác thực vẫn phải qua rule phân quyền.
4. Converter trả `Mono.empty()` khác manager trả `Mono.empty()` ở đâu? **Converter chưa tạo token để thử**, còn manager đã nhận token nhưng không kết luận; hệ quả HTTP phụ thuộc chuỗi filter.
5. Vì sao không nên gọi `block()` để lấy `SecurityContext`? Vì request đang theo luồng reactive và context thuộc subscription; blocking/thread assumption có thể làm sai ngữ nghĩa và giảm hiệu năng.
6. Nên kiểm thử contract nào tối thiểu? Thành công có đúng một `Authentication` đáng tin, loại token không hỗ trợ hoàn tất rỗng, credential sai phát `AuthenticationException` và endpoint thực tuân theo HTTP security policy.

## 11. Tài liệu chính thức để tra cứu

- [ReactiveAuthenticationManager — API contract](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [AuthenticationWebFilter — WebFlux authentication flow](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [WebFlux Security configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Reactive HTTP request authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)

**Ghi nhớ:** `ReactiveAuthenticationManager` không trả “true/false”. Nó trả một publisher có **ba kết cục khác nhau**: `Authentication` hợp lệ, **rỗng khi không quyết định**, hoặc **lỗi khi xác thực thất bại**. Sự phân biệt này là nền tảng để ghép nhiều manager an toàn và để filter chain diễn giải đúng trạng thái xác thực.
