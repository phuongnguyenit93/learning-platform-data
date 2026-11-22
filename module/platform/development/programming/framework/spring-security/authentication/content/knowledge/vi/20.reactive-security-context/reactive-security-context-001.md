# ReactiveSecurityContextHolder và Reactor Context

## 1. Mục tiêu và bài toán

Trong ứng dụng Spring Security chạy trên **Spring WebFlux**, một request có thể đi qua nhiều toán tử `Mono`/`Flux`, được xử lý trên những thread khác nhau và vẫn cần biết **ai đang được xác thực**. `ReactiveSecurityContextHolder` là API để truy cập `SecurityContext` của luồng xử lý reactive thông qua **Reactor Context**.

Sau bài này, bạn cần phân biệt `SecurityContext` với Reactor `Context`, đọc được `Authentication` trong pipeline, hiểu vị trí đặt `contextWrite`, nhận biết phạm vi của từng subscription và kiểm thử việc truyền ngữ cảnh mà không phụ thuộc vào thread hiện tại.

**Phạm vi:** Spring Security 6.x với Java 17+ và Reactor 3.x (phù hợp với hệ sinh thái Spring Boot 3.x). Một số API này vẫn có trong các phiên bản mới hơn.

## 2. Hai loại Context có nhiệm vụ khác nhau

- `Authentication`: biểu diễn principal, authorities, trạng thái xác thực và thông tin liên quan đến một lần xác thực.
- `SecurityContext`: đối tượng của Spring Security chứa `Authentication` (`getAuthentication()` và `setAuthentication()`).
- `reactor.util.context.Context`: tập khóa–giá trị phục vụ một chuỗi xử lý reactive; đi theo **Subscriber/subscription**, không gắn cố định vào một Java thread.
- `ReactiveSecurityContextHolder`: cầu nối của Spring Security để lưu/truy xuất một `Mono<SecurityContext>` trong Reactor Context bằng API công khai. Không cần tự biết khóa nội bộ của Spring Security.

| Khía cạnh | Servlet đồng bộ thông thường | WebFlux dùng Reactor |
| --- | --- | --- |
| Nơi thường đọc security context | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Cơ chế truyền ngữ cảnh chủ đạo | `ThreadLocal` với chiến lược holder mặc định | Reactor Context gắn với subscription |
| Khi chuyển thread | Cần cơ chế truyền `ThreadLocal` phù hợp | Reactor Context vẫn có thể truyền qua các toán tử Reactor trong cùng subscription |
| Cách nhận dữ liệu | Lời gọi trả về đối tượng trực tiếp | `Mono<SecurityContext>` phải được kết hợp vào pipeline |

**Không đồng nhất hai loại Context:** Reactor Context là cơ chế vận chuyển dữ liệu; `SecurityContext` là dữ liệu bảo mật được vận chuyển. Reactor `Context` bất biến ở cấp cấu trúc (`put`/`delete` tạo Context mới), nhưng các đối tượng đặt bên trong như `SecurityContextImpl` không mặc nhiên bất biến.

## 3. Ngữ cảnh đi theo subscription như thế nào?

Một chuỗi reactive được khai báo trước rồi mới thực thi khi có subscriber. `contextWrite(...)` thay đổi ngữ cảnh mà **các toán tử ở phía upstream** nhìn thấy khi tín hiệu subscribe đi từ downstream lên upstream.

```text
Subscriber / WebFlux runtime
        |
        | subscribe + Reactor Context
        v
contextWrite(withAuthentication(auth))
        |
        | Context được đưa lên upstream
        v
flatMap(...) -> ReactiveSecurityContextHolder.getContext()
        |
        v
Authentication -> tên người dùng / authorities
```

Khi dùng `publishOn`, `subscribeOn` hoặc có chuyển thread thông qua các toán tử Reactor, dữ liệu ngữ cảnh không buộc vào thread cũ. Điều kiện là tác vụ vẫn nằm trong chuỗi reactive được nối và subscribe đúng cách. **Một lần `subscribe()` độc lập tạo một subscription riêng**, không tự động nhận mọi ngữ cảnh của chuỗi gọi nó.

Ví dụ về vị trí đặt toán tử:

```java
// ĐÚNG: phép đọc nằm upstream của contextWrite.
Mono<String> ok = readUserName()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

// SAI ý định: readUserName() được tạo trong flatMap downstream
// của contextWrite bên dưới; nó không nhìn thấy phần Context chỉ áp dụng upstream.
Mono<String> missing = Mono.just("go")
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))
    .flatMap(ignored -> readUserName());
```

`readUserName()` là phương thức minh họa trả về `Mono<String>` có đọc `ReactiveSecurityContextHolder`. Đoạn trên minh họa vị trí toán tử, không phải chương trình Java độc lập. Hãy đặt thao tác tạo Context tại biên thích hợp của toàn bộ chuỗi cần sử dụng nó.

## 4. API cốt lõi của ReactiveSecurityContextHolder

| API | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `getContext()` | Trả về `Mono<SecurityContext>` đọc từ Reactor Context của subscriber | Nếu không có context, `Mono` có thể hoàn tất mà không phát giá trị |
| `withAuthentication(authentication)` | Tạo Reactor `Context` chứa một `SecurityContext` từ `Authentication` | Dùng với `.contextWrite(...)`; không cập nhật trạng thái toàn cục |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Tạo Reactor `Context` từ một publisher của `SecurityContext` | Hữu ích khi context được cung cấp bất đồng bộ |
| `clearContext()` | Trả về hàm biến đổi Context để loại bỏ security context ở phạm vi áp dụng | Không tương đương đăng xuất hay thu hồi token/session |

Một cách đọc an toàn khi `SecurityContext` hoặc `Authentication` có thể vắng mặt:

```java
Mono<String> userName = ReactiveSecurityContextHolder.getContext()
    .flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))
    .map(Authentication::getName)
    .defaultIfEmpty("unknown");
```

`Mono.justOrEmpty(...)` tránh phát `null` vào Reactor (Reactor không cho phép phần tử `null`). `defaultIfEmpty` xử lý trường hợp không có giá trị; các lỗi của pipeline vẫn truyền dưới dạng lỗi. Đừng tự suy luận rằng `isAuthenticated() == true` luôn đồng nghĩa người dùng thực đã đăng nhập: một số kiểu `Authentication` như anonymous có semantics riêng. Quy tắc cho phép truy cập phải đến từ Spring Security authorization.

## 5. Ví dụ Java 17+ chạy được: ngữ cảnh vẫn tồn tại qua chuyển thread

Mã bên dưới là một chương trình Java độc lập **khi project đã có** `org.springframework.security:spring-security-core` và `io.projectreactor:reactor-core` trên classpath; với Spring Boot 3 có thể để BOM quản lý phiên bản. File đặt tại `src/main/java/example/ReactiveContextDemo.java`.

```java
package example;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ReactiveContextDemo {
    private static Mono<String> currentUserName() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))
            .map(Authentication::getName)
            .defaultIfEmpty("(khong co Authentication)");
    }

    public static void main(String[] args) {
        // Token giả lập đã được xác thực cho mục đích minh họa;
        // ứng dụng thật phải xác thực qua cơ chế Spring Security.
        Authentication user = UsernamePasswordAuthenticationToken.authenticated(
            "linh",
            null,
            AuthorityUtils.createAuthorityList("ROLE_READER")
        );

        Mono<String> pipeline = Mono.just("request")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> currentUserName());

        String withContext = pipeline
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user))
            .block();

        String withoutContext = pipeline.block();

        System.out.println(withContext);
        System.out.println(withoutContext);
    }
}
```

**stdout chính xác:**

```text
linh
(khong co Authentication)
```

Giải thích:

1. `pipeline` chuyển phần xử lý tiếp theo sang scheduler khác qua `publishOn`.
2. Subscription thứ nhất gắn một `Authentication` vào Reactor Context qua `contextWrite`; `currentUserName()` đọc được `linh`.
3. Subscription thứ hai dùng **chính pipeline đó** nhưng không gắn security context, nên chỉ nhận giá trị mặc định. Hai lần `block()` ở đây phục vụ chương trình demo console; **không sử dụng `block()` trong request processing của WebFlux**.
4. `UsernamePasswordAuthenticationToken.authenticated(...)` chỉ mô phỏng kết quả xác thực đã hoàn tất. Không tạo token này trực tiếp từ input người dùng để cấp quyền trong ứng dụng thực tế.

Nếu dự án cấu hình Gradle `application` plugin với main class `example.ReactiveContextDemo`, có thể chạy bằng `./gradlew run`; không thể dùng `javac` thuần JDK nếu chưa đưa các JAR Reactor/Spring Security vào classpath.

## 6. Dùng trong request WebFlux thật

Với Spring WebFlux và Spring Security được cấu hình đúng, các security web filter đưa `SecurityContext` của request đã xác thực vào Reactor Context. Chẳng hạn, `ReactorContextWebFilter` dùng `ServerSecurityContextRepository` để khởi tạo ngữ cảnh phù hợp. Vì vậy, trong service/controller trả về `Mono` hoặc `Flux`, thông thường chỉ cần **đọc** ngữ cảnh, không tự gọi `withAuthentication` cho từng request.

Ví dụ controller dưới đây dùng Spring WebFlux và Spring Security trong một ứng dụng đã cấu hình xác thực. File `WhoAmIController.java`:

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {
    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "Missing Authentication"
                )
            ));
    }
}
```

Một cấu hình WebFlux Security tối thiểu cho endpoint đó (file `WebSecurityConfig.java`):

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class WebSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/me").authenticated()
                .anyExchange().permitAll())
            .httpBasic(withDefaults())
            .build();
    }
}
```

Project còn cần cấu hình một nguồn user hoặc cơ chế authentication hợp lệ (ví dụ reactive user details service, OAuth2 Resource Server, v.v.). Đoạn trên **không** tạo người dùng demo hoặc cấu hình credential. Trên endpoint yêu cầu authenticated, security filter chain sẽ chặn yêu cầu chưa đủ quyền trước controller theo chính sách đã khai báo. Không dùng code controller làm lớp authorization duy nhất.

Có thể lấy thông tin người dùng qua `Principal`/`@AuthenticationPrincipal` khi thích hợp; `ReactiveSecurityContextHolder` đặc biệt hữu ích ở những thành phần sâu trong reactive pipeline không có tham số HTTP trực tiếp.

## 7. Gắn một SecurityContext có sẵn và xóa trong phạm vi chuỗi

Trong test, tác vụ nền có chính sách rõ ràng, hoặc quá trình tích hợp đặc biệt, có thể gắn context chủ động:

```java
// Đoạn minh họa đặt trong nơi đã có biến Authentication auth
// và phương thức Mono<String> readUserName().
SecurityContext securityContext = new SecurityContextImpl(auth);

Mono<String> scoped = readUserName()
    .contextWrite(ReactiveSecurityContextHolder.withSecurityContext(
        Mono.just(securityContext)
    ));
```

Cần import `org.springframework.security.core.context.SecurityContext`, `SecurityContextImpl` và `reactor.core.publisher.Mono`. `withSecurityContext` nhận `Mono<? extends SecurityContext>`, còn `withAuthentication` là cách viết ngắn khi đã có `Authentication`.

Nếu cần bỏ security context chỉ trong một vùng reactive:

```java
Mono<String> cleared = readUserName()
    .contextWrite(ReactiveSecurityContextHolder.clearContext())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

Trong chuỗi này, thao tác `clearContext` gần phép đọc hơn sẽ loại bỏ security context khỏi phần upstream đó. **Không dùng `clearContext()` thay logout:** đăng xuất còn tùy vào việc hủy session, xóa cookie, vô hiệu hóa token hay chính sách lưu trữ security context của ứng dụng.

Không chỉnh sửa trực tiếp một `SecurityContextImpl` đang được chia sẻ giữa các subscription. Nếu phải thay danh tính hoặc authorities, hãy thiết lập ngữ cảnh phù hợp ở biên xử lý, với đối tượng đúng vòng đời request/subscription.

## 8. Liên hệ với reactive method security

`@EnableReactiveMethodSecurity` giúp áp dụng các annotation như `@PreAuthorize` cho phương thức reactive; Spring Security dùng Reactor Context để lấy thông tin xác thực tại thời điểm subscription.

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {}

@Service
class ReportService {
    @PreAuthorize("hasRole('READER')")
    public Mono<String> getReport() {
        return Mono.just("Bao cao duoc bao ve");
    }
}
```

Các import thuộc `org.springframework.context.annotation`, `org.springframework.stereotype.Service`, `org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity`, `org.springframework.security.access.prepost.PreAuthorize` và `reactor.core.publisher.Mono`. Đây là hai thành phần Spring trong cùng ứng dụng, không phải file Java tự chạy; hãy gọi qua Spring-managed bean để proxy/interceptor method security hoạt động. Với mô hình reactive phổ biến, phương thức được bảo vệ trả về `Mono` hoặc `Flux`; không chuyển thành giá trị đồng bộ rồi kỳ vọng ngữ cảnh reactive vẫn có sẵn.

`hasRole('READER')` kiểm tra authority `ROLE_READER`. Phân quyền ở mức HTTP (`authorizeExchange`) và phương thức (`@PreAuthorize`) có thể phối hợp, nhưng cần cấu hình đúng mỗi lớp.

## 9. Kiểm thử context của hai subscription

Trong project có `reactor-test`, JUnit Jupiter và `spring-security-core`, file `src/test/java/example/ReactiveContextTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveContextTest {
    @Test
    void authenticationIsScopedToOneSubscription() {
        Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
            "alice", null, AuthorityUtils.createAuthorityList("ROLE_READER")
        );

        Mono<String> source = ReactiveSecurityContextHolder.getContext()
            .flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))
            .map(Authentication::getName);

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();

        // Subscription mới không nhận context của subscription trước.
        StepVerifier.create(source)
            .verifyComplete();
    }
}
```

Chạy bằng `./gradlew test` nếu dự án dùng Gradle và đã có các dependency test thích hợp. Test xác nhận cùng một publisher có thể được subscribe nhiều lần với context khác nhau, đồng thời tránh thao tác `SecurityContextHolder` toàn cục.

Ngoài unit test, với endpoint WebFlux có xác thực thật, dùng `WebTestClient` kiểm tra cả yêu cầu có credential hợp lệ, không có credential, và credential không đủ authority; tránh chỉ kiểm thử đường đi đã tự chèn `Authentication`.

## 10. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân hay gặp | Cách sửa |
| --- | --- | --- |
| `ReactiveSecurityContextHolder.getContext()` rỗng | Chưa có authentication, pipeline chạy ngoài security chain, hoặc context bị mất ở biên subscription | Xác nhận luồng request được Spring Security xử lý và kiểm tra phạm vi subscribe |
| Đọc được user ở đoạn đầu nhưng mất ở đoạn sau | Đặt `contextWrite` sai vị trí hoặc gọi `subscribe()` riêng | Giữ một pipeline liên tục; đặt `contextWrite` ở downstream của phép đọc cần thấy context |
| Dùng `SecurityContextHolder.getContext()` trong `publishOn` thấy sai/rỗng | Dựa vào `ThreadLocal` qua chuyển thread | Dùng `ReactiveSecurityContextHolder.getContext()` trong pipeline reactive |
| Dùng `map(sc -> sc.getAuthentication())` dẫn tới lỗi khi null | Reactor không chấp nhận phần tử `null` | Dùng `flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))` |
| Test có context nhưng request thật thất bại | Test tự gắn token, chưa kiểm chứng authentication/filter chain thực | Tách unit test context và integration test xác thực/authorization |
| Gọi `block()` hoặc `subscribe()` thủ công trong controller/service | Tách lifecycle khỏi WebFlux, có nguy cơ block event-loop hoặc mất context | Trả về và kết hợp `Mono`/`Flux` bằng `map`/`flatMap`, để framework subscribe |
| Gọi `clearContext()` rồi cho rằng đã logout | Chỉ xóa dữ liệu context trong phạm vi pipeline | Sử dụng logout/session/token strategy phù hợp |

**Nguyên tắc thực hành:** trong một reactive request, để Spring Security thiết lập context đã được xác thực; đọc context tại thời điểm subscribe bằng `ReactiveSecurityContextHolder`; giữ các bước xử lý trong cùng chuỗi `Mono`/`Flux`; dùng `contextWrite` chủ yếu cho test và các trường hợp đặc biệt có kiểm soát. Không dùng context do client tự khai báo làm chứng cứ xác thực.

## 11. Tài liệu đối chiếu

- Spring Security API — `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
