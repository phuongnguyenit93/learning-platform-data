# Phân biệt Publisher rỗng, kết quả từ chối và tín hiệu lỗi trong Spring Security Reactive

Khi làm việc với Spring Security trên WebFlux, ba kết quả dễ bị nhầm lẫn là **Publisher hoàn thành nhưng không phát giá trị**, **Publisher phát ra một quyết định không cấp quyền**, và **Publisher kết thúc bằng lỗi**. Chúng có thể dẫn tới kết quả HTTP giống nhau ở một số tình huống, nhưng ở tầng Reactor và trong hợp đồng của từng API, chúng mang ý nghĩa khác nhau. Phân biệt đúng giúp tránh vô tình cho phép truy cập, che giấu lỗi xác thực và chẩn đoán sai mã 401/403.

Bài này tập trung vào Reactor `Mono`, `ReactiveAuthenticationManager`, `ReactiveAuthorizationManager`, `AuthorizationWebFilter` và cách Spring Security chuyển quyết định thành kết quả xử lý yêu cầu. Ví dụ dùng Java 17+ và minh họa giao diện `check(...)` của Spring Security 6.3; các phiên bản mới hơn có thêm hoặc ưu tiên `authorize(...)` nhưng nguyên tắc phân biệt tín hiệu vẫn giữ nguyên.

## 1. Nhìn tín hiệu trước khi diễn giải ý nghĩa nghiệp vụ

Một `Mono<T>` phát tối đa một giá trị. Ba dạng cần nhận diện:

~~~text
Mono.empty()                        : subscribe → onComplete
Mono.just(decisionFalse)            : subscribe → onNext(decisionFalse) → onComplete
Mono.error(exception)               : subscribe → onError(exception)
~~~

- **Rỗng (`empty`)**: không có `onNext`, kết thúc bình thường bằng `onComplete`. Không có đối tượng kết quả để kiểm tra.
- **Từ chối (`deny`)**: một **giá trị quyết định** đã được phát, ví dụ `new AuthorizationDecision(false)`. Luồng vẫn có thể hoàn tất bình thường; bản thân `false` không phải tín hiệu `onError`.
- **Lỗi (`error`)**: Publisher phát `onError(Throwable)`, rồi dừng. Lỗi có thể là sự cố kỹ thuật hoặc một ngoại lệ bảo mật có chủ ý; phải xét kiểu ngoại lệ và nơi phát sinh.

| Cách biểu diễn | `onNext`? | Kết thúc | Ý nghĩa trực tiếp ở tầng Reactor |
| --- | --- | --- | --- |
| `Mono.empty()` | Không | `onComplete` | Không phát kết quả |
| `Mono.just(new AuthorizationDecision(true))` | Có, `isGranted()==true` | `onComplete` | Có quyết định cấp quyền |
| `Mono.just(new AuthorizationDecision(false))` | Có, `isGranted()==false` | `onComplete` | Có quyết định từ chối |
| `Mono.error(new IllegalStateException(...))` | Không | `onError` | Thực thi thất bại |
| `Mono.error(new AccessDeniedException(...))` | Không | `onError` | Từ chối được biểu diễn bằng ngoại lệ |

Điểm cốt lõi: **không thể nhìn thấy `Mono.empty()` rồi kết luận “được phép” hoặc “bị từ chối” nếu chưa biết hợp đồng của phương thức trả về Mono đó**. Tương tự, lỗi là *kiểu tín hiệu*, còn “từ chối” là *ý nghĩa bảo mật*: một lần từ chối có thể bắt đầu từ giá trị `AuthorizationDecision(false)` và sau đó được chuyển thành `AccessDeniedException`.

## 2. Cùng một Publisher rỗng nhưng ý nghĩa thay đổi theo API

### 2.1. Tại ReactiveAuthenticationManager: chưa xác định được người dùng

`ReactiveAuthenticationManager.authenticate(Authentication)` trả `Mono<Authentication>`. Theo hợp đồng của giao diện này:

| Giá trị trả về | Diễn giải |
| --- | --- |
| `Mono.just(authenticated)` | Xác thực thành công; phát một đối tượng `Authentication` phù hợp |
| `Mono.empty()` | Bộ quản lý này **không xác định được** có thể xác thực đối tượng đầu vào hay không |
| `Mono.error(new BadCredentialsException(...))` | Xác thực **thất bại**; ví dụ thông tin đăng nhập sai |

Ví dụ, một bộ quản lý chỉ hỗ trợ token loại A có thể trả rỗng khi gặp loại B để bộ quản lý khác xử lý, **nếu** cơ chế phối hợp được cấu hình cho phép thử tiếp. Nhưng nếu đã biết tên đăng nhập/mật khẩu không hợp lệ, trả rỗng như thể “không liên quan” có thể che giấu lỗi và tạo đường rẽ không mong muốn. Với trường hợp xác thực thất bại đã xác định, hãy phát `AuthenticationException` thích hợp. Không được tự suy ra “`Mono.empty()` = đăng nhập thành công”.

Cũng cần phân biệt `ReactiveSecurityContextHolder.getContext()` rỗng (không có ngữ cảnh bảo mật ở điểm đọc) với kết quả của `authenticate(...)`. Không có ngữ cảnh không đồng nghĩa một chính sách tài nguyên đã cấp quyền.

### 2.2. Tại ReactiveAuthorizationManager: không quyết định, từ chối, hay sự cố

Trong API Spring Security 6.3, `ReactiveAuthorizationManager<T>.check(Mono<Authentication>, T)` trả `Mono<AuthorizationDecision>`:

- `Mono.just(new AuthorizationDecision(true))`: chính sách trả lời **ALLOW**.
- `Mono.just(new AuthorizationDecision(false))`: chính sách trả lời **DENY**.
- `Mono.empty()`: chính sách **không đưa ra quyết định** (*abstain/no decision*), không phải một quyết định cấp quyền.
- `Mono.error(cause)`: không hoàn tất việc đánh giá theo cách bình thường; cần giữ nguyên hoặc xử lý có chủ đích loại lỗi.

Từ Spring Security 6.4, API `authorize(...)` được bổ sung để trả về `AuthorizationResult`; ở các phiên bản mới, nên kiểm tra chữ ký cụ thể và dùng API được khuyến nghị cho phiên bản đó. Về mặt ý nghĩa, **không có quyết định** vẫn khác **quyết định không cấp quyền**.

Không phải mọi nơi nhận `Mono<AuthorizationDecision>` đều xử lý `empty` giống nhau. Các thành phần phối hợp nhiều chính sách có thể có quy tắc riêng về bỏ phiếu, ưu tiên hoặc kết quả mặc định. Phải đọc hợp đồng của **thành phần tiêu thụ** kết quả, không chỉ của bộ quản lý tạo kết quả.

### 2.3. Tại verify: hoàn thành rỗng có thể là THÀNH CÔNG

`ReactiveAuthorizationManager.verify(...)` trả `Mono<Void>`: phương thức này **không phát đối tượng kết quả khi kiểm tra thành công**. Đối với cách triển khai mặc định trong Spring Security 6.3, quyết định không cấp quyền và trường hợp không có quyết định đều dẫn tới `AccessDeniedException`; quyết định cấp quyền dẫn tới hoàn thành bình thường.

~~~text
check(...) → AuthorizationDecision(true)  → verify(...) → onComplete   (cho qua)
check(...) → AuthorizationDecision(false) → verify(...) → onError(AccessDeniedException)
check(...) → Mono.empty()                 → verify(...) → onError(AccessDeniedException)
check(...) → onError(IllegalStateException) → verify(...) → onError(IllegalStateException)
~~~

Đây là chỗ dễ nhầm nhất: **`Mono<Void>` hoàn thành rỗng sau `verify` là một kết quả kiểm tra thành công**, trong khi **`Mono<AuthorizationDecision>` hoàn thành rỗng ở `check` nghĩa là chưa có quyết định**. Kiểu trả về và tầng xử lý quyết định ý nghĩa, không phải chỉ chữ “empty”.

Một `Mono<Void>` dùng cho `WebFilter.filter` cũng thường hoàn thành mà không phát giá trị khi xử lý thành công. Đừng dùng `switchIfEmpty` trên `Mono<Void>` để tự đoán rằng đường xử lý đã từ chối truy cập.

## 3. Bối cảnh trong chuỗi Spring Security WebFlux

Có thể đọc luồng xử lý theo các bước tư duy sau (thứ tự cụ thể phụ thuộc cấu hình chuỗi bộ lọc):

1. **Nhận yêu cầu và tìm thông tin xác thực.** Bộ lọc xác thực có thể trích xuất thông tin từ Basic, Bearer token, session hoặc cơ chế khác. Không có thông tin phù hợp chưa phải là `AuthorizationDecision(false)`.
2. **Xác thực danh tính khi có đầu vào phù hợp.** `ReactiveAuthenticationManager` thành công sẽ cung cấp `Authentication`; thất bại đã xác định phát lỗi xác thực. `Mono.empty()` tại đây chỉ nói bộ quản lý đó chưa xác định được kết quả.
3. **Đưa danh tính vào ngữ cảnh reactive.** Spring Security có thể cung cấp `SecurityContext` thông qua Reactor `Context`; không nên mặc định nó là một biến `ThreadLocal` có thể đọc ở mọi luồng.
4. **Đánh giá quyền truy cập.** `AuthorizationWebFilter` phối hợp `ReactiveAuthorizationManager` với yêu cầu và thông tin xác thực; chính sách có thể cấp quyền hoặc từ chối.
5. **Xử lý quyết định/lỗi.** Lỗi từ chối truy cập được xử lý bằng cơ chế bảo mật tương ứng; lỗi kỹ thuật không nên tự động biến thành “được phép”.

Ví dụ quy tắc WebFlux:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .pathMatchers("/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
~~~

`hasRole("ADMIN")` kiểm tra quyền tương ứng `ROLE_ADMIN` theo quy ước mặc định. Người dùng đã xác thực nhưng không có quyền đó phải bị từ chối; một token không hợp lệ phải được xử lý ở bước xác thực, trước khi có cơ sở tin vào vai trò do token khai báo. Trong ứng dụng thực tế, hãy ưu tiên các quy tắc có sẵn như `hasRole`, `authenticated` và `denyAll` thay vì tự xây chính sách khi không cần thiết.

### Tại sao không thể gán cứng empty/deny/error thành HTTP 200/401/403/500?

Mã HTTP được quyết định sau khi tín hiệu đi qua các bộ lọc, bộ xử lý ngoại lệ, lựa chọn điểm bắt đầu xác thực và cấu hình ứng dụng:

| Tình huống | Kết quả thường gặp | Điều cần nhớ |
| --- | --- | --- |
| Chưa xác thực, truy cập đường dẫn cần đăng nhập | 401 với HTTP Basic/Bearer, hoặc chuyển hướng tới trang đăng nhập | Phụ thuộc `ServerAuthenticationEntryPoint` và cơ chế đăng nhập |
| Đã xác thực, thiếu quyền | 403 | `ServerAccessDeniedHandler` thường đảm nhận phản hồi |
| Token sai/hết hạn | Phản hồi lỗi xác thực, thường là 401 với Bearer | Đây là thất bại xác thực, không phải “abstain” |
| Chính sách từ chối bằng `AuthorizationDecision(false)` | Sau chuyển đổi thường thành lỗi từ chối truy cập | Không đồng nhất một `onNext(false)` với `onError` |
| Kho chính sách hoặc dịch vụ phụ thuộc bị lỗi | Lỗi kỹ thuật được lan truyền hoặc xử lý theo chính sách lỗi | Không mặc nhiên gắn mọi lỗi với 403/500 |
| Handler trả `Mono.empty()` khi đã được cấp quyền | Có thể là phản hồi không có nội dung thân | Không phải dấu hiệu Spring Security đã từ chối |

Trong Spring Security WebFlux, `ExceptionTranslationWebFilter` xử lý `AccessDeniedException` và lựa chọn giữa bắt đầu quá trình xác thực với xử lý từ chối tùy tình trạng danh tính. Giá trị HTTP cuối cùng còn tùy các cấu hình khác. Do đó, hãy lần theo ngoại lệ, bộ lọc và chính sách thay vì đoán kết quả chỉ từ một `Mono`.

## 4. Ví dụ cấu hình: chủ động đưa ra quyết định DENY khi thiếu danh tính

Đoạn sau là một lớp cấu hình hoàn chỉnh cho dự án Spring Boot dùng WebFlux và Spring Security. Nó minh họa cách phân biệt “không có đối tượng xác thực” với “không đủ quyền”, đồng thời trả **quyết định rõ ràng** tại điểm kiểm tra. Tên file: `SecurityConfig.java` (thêm `package` theo cấu trúc dự án).

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        ReactiveAuthorizationManager<AuthorizationContext> adminOnly =
                (authentication, context) -> authentication
                        .map(auth -> new AuthorizationDecision(
                                auth.isAuthenticated()
                                        && auth.getAuthorities().stream()
                                        .anyMatch(authority ->
                                                "ROLE_ADMIN".equals(authority.getAuthority()))
                        ))
                        .defaultIfEmpty(new AuthorizationDecision(false));

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/admin/**").access(adminOnly)
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Giải thích từng điểm:

- `authentication` là `Mono<Authentication>`. Có giá trị thì `map` kiểm tra người dùng đã xác thực và có `ROLE_ADMIN` hay không; kết quả luôn là `AuthorizationDecision(true/false)`.
- Nếu nguồn xác thực rỗng, `map` không chạy. `defaultIfEmpty(new AuthorizationDecision(false))` cung cấp **quyết định từ chối**, tránh để phương thức chính sách trả về “không quyết định” ngoài ý muốn.
- Nếu nguồn xác thực phát lỗi, `defaultIfEmpty` **không bắt lỗi**; lỗi vẫn được chuyển tiếp. Đây là hành vi mong muốn khi một sự cố cần được phát hiện.
- `access(adminOnly)` cho phép dùng chính sách riêng trong `authorizeExchange`. Với nhu cầu chỉ kiểm tra vai trò, `hasRole("ADMIN")` ngắn gọn hơn và nên là lựa chọn thông thường.

Đây là ví dụ chính sách, không phải giải pháp quản lý người dùng/token hoàn chỉnh. Muốn chạy trong dự án Spring Boot, cần `spring-boot-starter-webflux` và `spring-boot-starter-security`. Nếu ứng dụng đang dùng Spring MVC/Servlet, cấu hình tương ứng là một hệ API khác (ví dụ `SecurityFilterChain` thay vì `SecurityWebFilterChain`).

## 5. Kiểm chứng bằng StepVerifier: năm trường hợp tách bạch

Trong dự án Gradle với Spring Boot 3.3 / Spring Security 6.3, có thể thêm các phụ thuộc kiểm thử thường dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Đặt file `AuthorizationSignalsTest.java` trong `src/test/java` (bổ sung `package` đúng dự án). Đây là phép thử đơn vị đối với tín hiệu và hợp đồng `verify`, chưa phải phép thử HTTP end-to-end.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;

class AuthorizationSignalsTest {

    private final Mono<Authentication> noAuthentication = Mono.empty();
    private final Object resource = new Object();

    @Test
    void emptyPublisherHasNoDecision() {
        ReactiveAuthorizationManager<Object> abstain =
                (authentication, target) -> Mono.empty();

        StepVerifier.create(abstain.check(noAuthentication, resource))
                .verifyComplete(); // Không có onNext, cũng không có onError
    }

    @Test
    void deniedDecisionIsAValue() {
        Mono<AuthorizationDecision> denied =
                Mono.just(new AuthorizationDecision(false));

        StepVerifier.create(denied)
                .assertNext(decision -> assertFalse(decision.isGranted()))
                .verifyComplete(); // Có giá trị false, kết thúc bình thường
    }

    @Test
    void technicalErrorIsNotAnEmptyCompletion() {
        Mono<AuthorizationDecision> failed =
                Mono.error(new IllegalStateException("policy store unavailable"));

        StepVerifier.create(failed)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "policy store unavailable".equals(error.getMessage()))
                .verify();
    }

    @Test
    void verifyRejectsBothAbstentionAndDenial() {
        ReactiveAuthorizationManager<Object> abstain =
                (authentication, target) -> Mono.empty();
        ReactiveAuthorizationManager<Object> deny =
                (authentication, target) ->
                        Mono.just(new AuthorizationDecision(false));

        StepVerifier.create(abstain.verify(noAuthentication, resource))
                .expectError(AccessDeniedException.class)
                .verify();

        StepVerifier.create(deny.verify(noAuthentication, resource))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void verifyCompletesNormallyForGrant() {
        ReactiveAuthorizationManager<Object> allow =
                (authentication, target) ->
                        Mono.just(new AuthorizationDecision(true));

        StepVerifier.create(allow.verify(noAuthentication, resource))
                .verifyComplete(); // Mono<Void> thành công, không phát onNext
    }
}
~~~

Chạy trong dự án đã bật JUnit Platform:

~~~bash
./gradlew test --tests '*AuthorizationSignalsTest'
~~~

Trên Windows có thể dùng `gradlew.bat test --tests "*AuthorizationSignalsTest"`. **Kết quả kỳ vọng**: cả năm phép thử thành công. Chú ý đây là kết quả kỳ vọng từ logic và hợp đồng API của Spring Security 6.3, không phải bản ghi stdout từ một lần chạy thực tế.

Trong phiên bản Spring Security sử dụng `authorize(...)` thay cho `check(...)`, cần điều chỉnh phần kiểm tra giá trị quyết định theo chữ ký `AuthorizationResult` của phiên bản đó. Các phép thử nên luôn ghi rõ phiên bản để tránh lẫn giao diện cũ/mới.

## 6. Đọc tín hiệu khi gỡ lỗi

Các toán tử Reactor thường dùng có phạm vi khác nhau:

| Toán tử | Kích hoạt khi nào? | Dùng để |
| --- | --- | --- |
| `doOnNext(value -> ...)` | Có `onNext` | Quan sát quyết định ALLOW/DENY |
| `doOnError(error -> ...)` | Có `onError` | Ghi nhận lỗi và loại ngoại lệ |
| `doOnSuccess(value -> ...)` của `Mono` | Mono hoàn tất thành công; `value` có thể là `null` nếu rỗng | Phân biệt thành công có/không có giá trị |
| `switchIfEmpty(fallback)` | Nguồn hoàn thành không phát giá trị | Quy định nhánh thay thế cho trường hợp rỗng |
| `onErrorResume(Type.class, handler)` | Nguồn phát lỗi khớp kiểu | Khôi phục lỗi đã xác định |
| `materialize()` | Chuyển tín hiệu thành đối tượng có thể quan sát | Phân tích `onNext/onComplete/onError` khi kiểm thử |

Ví dụ phân biệt hai nhánh của Reactor:

~~~java
Mono<AuthorizationDecision> decision = lookupDecision();

Mono<AuthorizationDecision> evaluated = decision
        .switchIfEmpty(Mono.just(new AuthorizationDecision(false)))
        .doOnNext(result ->
                System.out.println("granted = " + result.isGranted()))
        .doOnError(error ->
                System.err.println("authorization error: " + error.getClass().getSimpleName()));
~~~

Đây là **đoạn mã tích hợp minh họa**, vì `lookupDecision()` là hàm ứng dụng cần tự định nghĩa. Nếu nó trả rỗng, sẽ in `granted = false`; nếu nó trả quyết định từ chối, cũng in `granted = false`; nếu phát lỗi thì nhánh `doOnError` chạy và lỗi vẫn được chuyển tiếp. `doOnError` chỉ quan sát, không “nuốt” lỗi.

Đặc biệt lưu ý hai điều:

1. **`switchIfEmpty` không chữa `onError`**; `onErrorResume` không xử lý nguồn chỉ hoàn thành rỗng. Dùng sai toán tử sẽ làm nhánh dự phòng không bao giờ chạy.
2. **Không dùng `onErrorResume(error -> Mono.empty())` một cách chung chung ở vị trí thực thi an ninh.** Nó có thể xóa mất dấu vết của lỗi xác thực, lỗi đánh giá quyền hoặc sự cố kho chính sách. Cũng không dùng `defaultIfEmpty(new AuthorizationDecision(true))` chỉ để “cho hệ thống chạy tiếp”. Khi cơ sở đưa ra quyết định không sẵn có, xác định chính sách từ chối an toàn hoặc lan truyền lỗi có kiểm soát.

Đối với `Mono<Void>`, `doOnNext` không có giá trị để quan sát dù tác vụ thành công. Muốn biết đường xử lý hoàn tất hay lỗi, quan sát tín hiệu kết thúc hoặc đo kết quả tại API cụ thể. Sau khi gọi `verify(...)`, một `switchIfEmpty(...)` sẽ nhìn thấy Mono hoàn thành rỗng ngay cả trong trường hợp **đã được cấp quyền**.

## 7. Đối chiếu các tình huống thực tế

**Tình huống A — Hai cơ chế xác thực.** Bộ quản lý dành cho loại token A nhận token B: `Mono.empty()` có thể biểu thị “không hỗ trợ loại này”. Bộ quản lý thích hợp khác có thể thử nếu được ghép bằng một cơ chế ủy quyền tương ứng. Nhưng token A có chữ ký sai hoặc mật khẩu sai là thất bại đã xác định: dùng lỗi xác thực, không giả vờ là “chưa xác định”.

**Tình huống B — Người dùng hợp lệ nhưng thiếu vai trò.** `Authentication` hợp lệ được đưa vào bộ đánh giá; `hasRole("ADMIN")` hoặc chính sách tương đương trả quyết định không cấp quyền. Đây là **DENY**, không phải thiếu kết quả; thành phần thực thi quyền sẽ chuyển quyết định thành lỗi từ chối, thường dẫn tới 403 khi người dùng đã xác thực.

**Tình huống C — Chính sách tùy chỉnh không có quyết định.** Một `ReactiveAuthorizationManager.check(...)` trả `Mono.empty()` vì không áp dụng chính sách nào. Ở tầng `check` đó là *abstain*. Khi gọi `verify` mặc định, trường hợp này bị từ chối bằng `AccessDeniedException`. Nếu ứng dụng có quy tắc phối hợp chính sách riêng, phải kiểm tra cách nó xử lý *abstain* trước khi kết luận kết quả cuối.

**Tình huống D — Dịch vụ tra cứu quyền gặp sự cố.** Một lời gọi phụ thuộc trả `Mono.error(new IllegalStateException(...))`. Đó là lỗi hệ thống cần giám sát và xử lý, không phải “không có kết quả”. Chuyển mọi lỗi thành ALLOW hoặc hoàn thành rỗng có thể dẫn tới quyền truy cập sai.

**Tình huống E — Handler không trả phần thân.** Một phương thức WebFlux được cho phép và trả `Mono<Void>` hoàn tất bình thường. Đây là kiểu hoàn thành phù hợp với tác vụ không phát dữ liệu; không được suy ra yêu cầu đã bị chặn chỉ từ trạng thái rỗng.

## 8. Lỗi thường gặp và cách tự kiểm tra

- **Nhầm giá trị với tín hiệu:** `AuthorizationDecision(false)` là `onNext` mang giá trị từ chối; chỉ khi tầng thực thi chuyển đổi nó mới trở thành `onError(AccessDeniedException)`.
- **Nhầm hai tầng `check` và `verify`:** rỗng ở `check` là không có quyết định; rỗng ở `verify` khi thành công là hợp đồng của `Mono<Void>`.
- **Nuốt ngoại lệ xác thực:** biến `BadCredentialsException` thành `Mono.empty()` có thể khiến cơ chế khác tiếp tục thử khi không nên.
- **Tự quyết định HTTP status từ Mono:** 401, 403, chuyển hướng hay phản hồi lỗi khác phụ thuộc bộ lọc, kiểu ngoại lệ và cơ chế cấu hình.
- **Thiếu chính sách mặc định:** khi xây quyền tùy chỉnh, xác định rõ xử lý nếu không có danh tính, không có dữ liệu quyền hoặc chính sách không áp dụng.
- **Kiểm thử chỉ nhánh ALLOW:** cần thử ít nhất empty, deny, error và đường chuyển đổi qua `verify`; với HTTP, bổ sung kiểm thử người dùng ẩn danh, người dùng thiếu quyền và người dùng đủ quyền.
- **Dùng API sai phiên bản:** `check(...)` của Spring Security 6.3 khác với API `authorize(...)` được khuyến nghị ở các phiên bản mới; xác nhận dependency thực tế trước khi sao chép mã.

Tự trả lời bốn câu hỏi mỗi khi thấy một Publisher rỗng trong đường bảo mật: **Publisher này trả kiểu gì? Hợp đồng của phương thức tạo nó nói rỗng nghĩa là gì? Thành phần nào tiêu thụ nó tiếp theo? Tại điểm nào và bằng ngoại lệ nào quyết định được biến thành phản hồi HTTP?** Trả lời được bốn câu hỏi đó sẽ phân biệt được “chưa quyết định”, “bị từ chối” và “bị lỗi” mà không đánh đồng chúng.

## Tài liệu đối chiếu

- [ReactiveAuthenticationManager — hợp đồng kết quả xác thực](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [ReactiveAuthorizationManager — API 6.3, check và verify](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security — WebFlux method authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — authorize HTTP requests trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Project Reactor — API Mono và các toán tử tín hiệu](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
