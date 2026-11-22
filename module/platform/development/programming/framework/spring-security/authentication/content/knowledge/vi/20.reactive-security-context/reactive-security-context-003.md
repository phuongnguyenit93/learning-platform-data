# ServerSecurityContextRepository và WebSessionServerSecurityContextRepository trong Spring Security WebFlux

## 1. Bài toán: danh tính được giữ ở đâu giữa các HTTP request?

Trong WebFlux, sau khi xác thực thành công, Spring Security có một `Authentication` (đại diện cho principal, quyền và trạng thái xác thực) được đặt trong `SecurityContext`. Nhưng HTTP request tiếp theo là một lần xử lý mới: nếu ứng dụng cần nhớ người dùng đã đăng nhập bằng biểu mẫu, nó phải **lưu và nạp lại** `SecurityContext`.

Hai thành phần của bài này giải quyết hai mức khác nhau:

- **`ServerSecurityContextRepository`** là *giao diện chiến lược*: định nghĩa cách lấy và lưu `SecurityContext` theo một `ServerWebExchange`.
- **`WebSessionServerSecurityContextRepository`** là *cách cài đặt cụ thể*: dùng `WebSession` của Spring WebFlux để lưu `SecurityContext` ở phía server giữa các request.

Tên package cần nhớ: `org.springframework.security.web.server.context`. Đây là **WebFlux/reactive**, không phải `SecurityContextRepository` và `HttpSessionSecurityContextRepository` của Servlet.

### Phân biệt bốn khái niệm

| Thành phần | Vai trò | Phạm vi |
| --- | --- | --- |
| `Authentication` | Người dùng là ai, authorities là gì, có được xác thực hay chưa | Dữ liệu danh tính |
| `SecurityContext` | Đối tượng bao `Authentication` | Ngữ cảnh bảo mật |
| `ReactiveSecurityContextHolder` | Truy cập context qua **Reactor Context** trong luồng xử lý hiện tại | Chuỗi reactive của request |
| `ServerSecurityContextRepository` | Nạp/lưu context phục vụ **những request kế tiếp** | Cơ chế persistence do implementation quyết định |

Reactor Context không phải kho session lâu dài. Đưa authentication vào `ReactiveSecurityContextHolder` chỉ giúp các bước trong chuỗi reactive nhìn thấy nó; muốn duy trì đăng nhập ở request sau cần cơ chế lưu/nạp thích hợp.

## 2. Hợp đồng của ServerSecurityContextRepository

API cốt lõi (đã giản lược annotation):

```java
public interface ServerSecurityContextRepository {
    Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
    Mono<SecurityContext> load(ServerWebExchange exchange);
}
```

- `load(exchange)`: phát ra một `SecurityContext` nếu tìm thấy; **`Mono.empty()`** nếu không có. Không trả `null` thay cho một `Mono`.
- `save(exchange, context)`: trả `Mono<Void>`; thao tác lưu diễn ra khi publisher được **subscribe** và hoàn tất khi publisher hoàn thành. Gọi phương thức rồi bỏ `Mono` sẽ không đảm bảo đã lưu.
- `ServerWebExchange` cung cấp request/response và khả năng truy cập `WebSession`; đây là API reactive, không dùng `HttpServletRequest`.
- Việc xác thực credential (password, token...) thuộc `ReactiveAuthenticationManager` hay cơ chế xác thực tương ứng; repository **không tự xác minh mật khẩu**.

Trong phiên bản Spring Security 6.x, chữ ký `save` nhận `SecurityContext`; các bản mới có thể mô tả tham số nullable để phục vụ xóa context. Khi minh họa code tùy biến, nên bám chữ ký của phiên bản dự án.

## 3. WebSessionServerSecurityContextRepository hoạt động thế nào?

`WebSessionServerSecurityContextRepository` ghi `SecurityContext` dưới một key trong `WebSession.getAttributes()`; khi `load`, nó lấy lại context từ phiên tương ứng. Key mặc định được công bố qua hằng `DEFAULT_SPRING_SECURITY_CONTEXT_ATTR_NAME`; có thể thay bằng `setSpringSecurityContextAttrName(...)` nếu cần tích hợp riêng.

**Luồng đăng nhập và request tiếp theo:**

```text
[POST /login với username/password]
  -> AuthenticationWebFilter + ReactiveAuthenticationManager xác thực
  -> tạo SecurityContext chứa Authentication
  -> repository.save(exchange, context)
  -> WebSession chứa context; session id được đổi khi lưu để giảm session fixation
  -> trình duyệt duy trì session cookie

[GET /whoami với cookie của cùng phiên]
  -> WebFlux khôi phục WebSession từ cookie / session store
  -> ReactorContextWebFilter dùng repository.load(exchange)
  -> SecurityContext được đưa vào Reactor Context
  -> Authorization và handler đọc Authentication trong luồng reactive
```

Hình dung đúng: **cookie mang mã phiên**, còn context được lưu phía server trong `WebSession`; thông thường cookie không mang toàn bộ `Authentication`. `WebSession` có thể được quản lý bởi bộ nhớ cục bộ hoặc kho session chia sẻ tùy cấu hình. `WebSessionServerSecurityContextRepository` không tự tạo một JWT, cũng không mặc định lưu vào Redis/database.

Đặc điểm đáng chú ý:

1. Khi lưu context, implementation **thay đổi session ID** để chống kiểu tấn công session fixation.
2. `load` khi không có context trả publisher rỗng; request không vì thế tự biến thành request đã đăng nhập.
3. `setCacheSecurityContext(true)` có thể cache kết quả `load` bằng `Mono.cache()` để tránh nạp lặp trong cùng đường xử lý. Đây là cache của publisher, **không phải cache phân tán hoặc thay thế session store**.
4. Khi session bị hủy hoặc hết hạn, context đã lưu không còn sẵn có ở request sau; cần xác thực lại.

## 4. Ai gọi save, ai gọi load? Hai cấu hình dễ bị nhầm

Trong chuỗi WebFlux:

- `ReactorContextWebFilter` dùng repository được cấu hình trên `ServerHttpSecurity.securityContextRepository(...)` để **nạp** context vào `ReactiveSecurityContextHolder`.
- Các cơ chế xác thực dựa trên `AuthenticationWebFilter`, ví dụ `formLogin`, có cấu hình repository riêng để **lưu** kết quả xác thực. Theo cấu hình form login thông thường, `WebSessionServerSecurityContextRepository` được dùng để lưu.
- `SecurityContextServerWebExchangeWebFilter` hỗ trợ `ServerWebExchange.getPrincipal()` đọc principal từ reactive context.

**Điểm quyết định:** đặt `http.securityContextRepository(repo)` **chỉ định đường nạp** và không tự động buộc mọi `AuthenticationWebFilter` dùng cùng repository để lưu. Khi thay đổi chiến lược, kiểm tra cả **đường save lẫn đường load**. Nếu login lưu vào repository A nhưng request kế tiếp nạp từ repository B, đăng nhập có thể thành công rồi lập tức bị coi như chưa đăng nhập.

## 5. Ví dụ chạy được: form login giữ context bằng WebSession

Tạo ứng dụng Spring Boot 3.x, Java 17+, chọn **Spring Reactive Web (WebFlux)** và **Spring Security**. Các dependency Gradle tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo file `src/main/java/demo/SessionSecurityDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class SessionSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionSecurityDemoApplication.class, args);
    }

    @Bean
    ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository) {
        return http
                .securityContextRepository(repository) // Nạp trên request mới
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .formLogin(form -> form
                        .securityContextRepository(repository)) // Lưu sau login
                .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails user = User.withUsername("reader")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    @GetMapping("/whoami")
    Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> authentication.getName());
    }
}
```

**Cách quan sát:**

1. Chạy `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) từ project Spring Boot vừa tạo, hoặc chạy `main` trong IDE.
2. Dùng trình duyệt mở `http://localhost:8080/whoami`. Vì chưa có authentication, Spring Security chuyển tới trang login.
3. Đăng nhập `reader` / `demo123` bằng form mặc định; CSRF token được form này xử lý. Sau khi đăng nhập, truy cập lại `/whoami`: response body là chính xác `reader`.
4. Reload trang vẫn nhận `reader` khi cookie phiên còn hợp lệ. Xóa cookie phiên hoặc mở phiên trình duyệt mới: phải đăng nhập lại.

Ví dụ dùng `{noop}` **chỉ để học**, không dùng mật khẩu không mã hóa hay user hard-code trong môi trường thật. Production cần password encoder an toàn (ví dụ bcrypt), user store và chính sách xác thực phù hợp. CSRF protection của Spring Security được giữ nguyên cho form login.

Tại sao `whoami()` đọc từ `ReactiveSecurityContextHolder` mà không truy cập `WebSession` trực tiếp? Bởi web filter đã khôi phục context cho request vào **Reactor Context**; business handler chỉ cần đọc identity qua API bảo mật, tránh phụ thuộc trực tiếp vào nơi lưu session.

## 6. Test đúng hành vi lưu/nạp qua hai exchange

Test sau không cần chạy HTTP server; nó chủ động tạo **hai `ServerWebExchange` khác nhau dùng chung một `MockWebSession`**. Điều này kiểm tra persistence tốt hơn việc chỉ save/load trên cùng một exchange.

Thêm dependency test:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Tạo file `src/test/java/demo/WebSessionRepositoryTest.java`:

```java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.web.server.MockWebSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WebSessionRepositoryTest {

    @Test
    void savesContextAndLoadsItFromAnotherRequest() {
        var repository = new WebSessionServerSecurityContextRepository();
        var sharedSession = new MockWebSession();

        var loginExchange = MockServerWebExchange
                .builder(MockServerHttpRequest.post("/login"))
                .session(sharedSession)
                .build();

        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        "reader", "ignored",
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));
        SecurityContext context = new SecurityContextImpl(authentication);

        // StepVerifier subscribe và chờ Mono<Void> save hoàn tất.
        StepVerifier.create(repository.save(loginExchange, context))
                .verifyComplete();

        var nextExchange = MockServerWebExchange
                .builder(MockServerHttpRequest.get("/whoami"))
                .session(sharedSession)
                .build();

        StepVerifier.create(repository.load(nextExchange))
                .assertNext(loaded -> {
                    assertEquals("reader", loaded.getAuthentication().getName());
                    assertEquals(
                            "ROLE_USER",
                            loaded.getAuthentication().getAuthorities()
                                    .iterator().next().getAuthority());
                })
                .verifyComplete();

        var unrelatedExchange = MockServerWebExchange
                .builder(MockServerHttpRequest.get("/whoami"))
                .session(new MockWebSession())
                .build();

        StepVerifier.create(repository.load(unrelatedExchange))
                .verifyComplete(); // Chưa có SecurityContext: Mono.empty()
    }
}
```

Chạy `./gradlew test`; test minh họa kỳ vọng **PASS**: cùng session thì load được authentication; session khác thì không có context. Test chỉ xác nhận hợp đồng repository, chưa thay thế kiểm thử HTTP/cookie/CSRF thực tế. `StepVerifier` dùng subscribe đúng với tính lazy của Reactor.

## 7. Khi nào dùng WebSession, khi nào không dùng?

| Tình huống | Lựa chọn điển hình | Lý do |
| --- | --- | --- |
| Ứng dụng WebFlux đăng nhập bằng form, giữ trạng thái đăng nhập trong cookie session | `WebSessionServerSecurityContextRepository` | Nạp lại `SecurityContext` từ phiên ở request sau |
| API yêu cầu Basic/Bearer credential ở **mỗi request**, không cần nhớ context giữa request | `NoOpServerSecurityContextRepository` | `save` không lưu; `load` luôn rỗng |
| Hệ thống nhiều instance cần duy trì login khi request tới node khác | Repository dựa trên `WebSession` **kèm session store chia sẻ** | Cần hạ tầng session có thể truy cập từ nhiều node, không chỉ đổi implementation của repository |
| Đăng nhập tùy biến có bước tự tạo authentication | Lưu context rõ ràng bằng repository và đưa vào Reactor Context khi cần trong request hiện tại | Tránh trạng thái chỉ tồn tại ở request hiện tại |

Ví dụ cấu hình **API stateless với HTTP Basic**, dành cho một ứng dụng API thuần (độc lập với ví dụ form login ở trên):

```java
@Bean
SecurityWebFilterChain statelessApi(ServerHttpSecurity http) {
    var noOp = NoOpServerSecurityContextRepository.getInstance();

    return http
            .securityContextRepository(noOp) // Không nạp context từ session
            .authorizeExchange(exchanges ->
                    exchanges.anyExchange().authenticated())
            .httpBasic(basic -> basic.securityContextRepository(noOp))
            .formLogin(form -> form.disable())
            .build();
}
```

Các import cần cho đoạn này là `org.springframework.security.web.server.context.NoOpServerSecurityContextRepository` và các kiểu đã có ở ví dụ chính. Đoạn là **một method cấu hình thay thế** trong class `@Configuration`, không thêm đồng thời vào ứng dụng form-login mà không định nghĩa phạm vi `SecurityWebFilterChain` rõ ràng. Ứng dụng/client phải gửi `Authorization` mỗi request để xác thực. `NoOp` chỉ chặn **lưu/nạp SecurityContext**, không có nghĩa mọi tính năng khác của WebFlux đều ngừng sử dụng `WebSession`; CSRF, request cache hoặc mã ứng dụng vẫn có thể dùng session tùy cấu hình.

## 8. Lỗi thực tế thường gặp và cách chẩn đoán

**(1) Đăng nhập thành công rồi request sau lại 401/redirect login.** Kiểm tra session cookie có được gửi lại không, session store có giữ session không, session đã hết hạn chưa, và nhất là **repository dùng để save có trùng repository dùng để load không**. Khi có nhiều security chain, kiểm tra chain thực sự match URL đó.

**(2) Gọi `repository.save(exchange, context);` nhưng không thấy được lưu.** `Mono` là lazy; phải nối vào pipeline hoặc subscribe trong test. Trong WebFlux handler hãy dùng `flatMap`, `then`, `contextWrite` khi phù hợp; không gọi `block()` trên event-loop để ép side effect.

**(3) Có context ở request hiện tại nhưng request tiếp theo không có.** `ReactiveSecurityContextHolder.withAuthentication(...)` hay `withSecurityContext(...)` chỉ bổ sung **Reactor Context** cho subscription hiện tại; nó không thay `repository.save`. Ngược lại, lưu vào session không đồng nghĩa các operator đã chạy trước đó lập tức có context mới.

**(4) Dùng `SecurityContextHolder.getContext()` trong WebFlux rồi thấy null/rỗng hoặc sai ngữ cảnh.** `SecurityContextHolder` truyền thống phụ thuộc ThreadLocal; pipeline reactive có thể chuyển thread. Dùng `ReactiveSecurityContextHolder.getContext()` và giữ các thao tác trong pipeline.

**(5) Tưởng dùng WebSession nghĩa là token nằm trong cookie.** Cookie thường chỉ chứa session ID; security context nằm ở phía server. Không log hoặc serialize credential/secret thô vào context, session hay response.

**(6) Login bị CSRF 403 khi POST bằng curl/Postman.** Form login mặc định có CSRF protection: cần lấy token hợp lệ và giữ cookie của cùng phiên. Không vô hiệu hóa CSRF toàn cục chỉ để làm request thử chạy được.

**(7) Chạy nhiều instance và lúc được lúc mất login.** Nếu session được lưu ở bộ nhớ từng node, cookie đúng nhưng node khác không nạp được session cũ. Cấu hình session store chung (ví dụ Spring Session và một backend tương thích), cân nhắc session timeout, rotation, cookie `Secure`/`HttpOnly`/`SameSite`, và HTTPS.

**(8) Nhầm API Servlet với Reactive.** `HttpSessionSecurityContextRepository`, `SecurityContextHolderFilter`, `HttpSecurity` là luồng Servlet. Với WebFlux, dùng `ServerSecurityContextRepository`, `WebSession`, `ServerHttpSecurity` và Reactor Context.

## 9. Checklist áp dụng cho một hệ thống thực tế

1. Xác định ứng dụng thật sự cần **stateful login** hay **credential mỗi request**.
2. Chọn repository cho việc **load** và xác minh các filter xác thực dùng repository tương thích cho việc **save**.
3. Nếu dùng WebSession, bảo đảm cookie hoạt động, session store phù hợp môi trường triển khai, thời hạn phiên và xử lý logout được kiểm thử.
4. Giữ authentication trong Reactor Context khi xử lý request; không dựa vào ThreadLocal.
5. Test tối thiểu: session mới chưa đăng nhập; login rồi request tiếp theo thành công; session khác/hết hạn bị từ chối; logout không còn identity; đổi node vẫn giữ session nếu ứng dụng cần phân tán.
6. Khi lưu context theo cách tùy biến, kiểm tra error/completion của `Mono<Void>` và không phản hồi login thành công trước khi việc lưu bắt buộc hoàn tất.

### Tài liệu chính thức để tra cứu API

- Spring Security 6.3 — `ServerSecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/context/ServerSecurityContextRepository.html
- Spring Security 6.3 — `WebSessionServerSecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/6.3.7/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security — WebFlux Security configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Framework — `MockServerWebExchange.Builder.session(WebSession)`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/mock/web/server/MockServerWebExchange.Builder.html
