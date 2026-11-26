# Ngữ cảnh trống khác với AnonymousAuthenticationToken

Khi gọi `SecurityContextHolder.getContext().getAuthentication()` và nhận `null`, điều đó có nghĩa là chưa có `Authentication` trong context hiện tại. Nhưng trong một HTTP request được Spring Security bảo vệ, người dùng chưa đăng nhập có thể được biểu diễn bằng một đối tượng `AnonymousAuthenticationToken`. Hai trạng thái này có liên quan nhưng **không đồng nghĩa**.

Phân biệt được chúng giúp viết đúng bài kiểm thử xác thực và phân quyền: một test thuần có thể đang chạy trước khi security filter thiết lập danh tính; một request HTTP đã đi qua `AnonymousAuthenticationFilter` lại có thể mang anonymous token. Trong module **SPRING_SECURITY_TESTING**, bài học thuộc chương **Ngữ cảnh và vòng đời**, giải thích trạng thái của `SecurityContext` trên Servlet, cách Spring Security nhận diện người dùng vô danh và cách kiểm chứng bằng `@WithAnonymousUser`, `MockMvc` cùng các assertion phù hợp.

## 1. Hai trạng thái cần phân biệt

### Context trống

Một `SecurityContext` trống vẫn là một đối tượng context hợp lệ, nhưng chưa có authentication:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();

assertThat(context).isNotNull();
assertThat(context.getAuthentication()).isNull();
~~~

Trên chiến lược mặc định `MODE_THREADLOCAL`, gọi `SecurityContextHolder.getContext()` khi luồng hiện tại chưa có context sẽ lấy/tạo một context rỗng để sử dụng. Vì vậy, lời gọi `getContext()` thông thường không trả về `null`; thứ thường bằng `null` là `getAuthentication()`.

Các tình huống có thể quan sát context trống:

- Bài test thuần vừa bắt đầu và chưa thiết lập danh tính.
- Test đã gọi `SecurityContextHolder.clearContext()` để dọn trạng thái.
- Mã test vừa cài một `SecurityContext` mới bằng `createEmptyContext()` nhưng chưa gán authentication.
- Code đang chạy trước khi chuỗi filter bảo mật thiết lập authentication cho request.
- Ứng dụng tắt hỗ trợ anonymous và request chưa được xác thực, nên filter không tạo anonymous token.

Context trống nói rằng **holder hiện tại chưa chứa authentication**. Nó chưa cho biết request đã được xử lý qua security filter hay chưa, cũng không tự xác định endpoint nên trả `401` hay `403`.

### AnonymousAuthenticationToken

`AnonymousAuthenticationToken` là một triển khai của `Authentication` được Spring Security dùng để biểu diễn người dùng vô danh. Trong cấu hình mặc định, `AnonymousAuthenticationFilter` tạo token này khi request chưa có authentication và hỗ trợ anonymous đang bật.

Một token mặc định thường có:

| Thành phần | Giá trị thường gặp |
| --- | --- |
| Loại đối tượng | `AnonymousAuthenticationToken` |
| Principal | `anonymousUser` |
| Authority | `ROLE_ANONYMOUS` |
| `getName()` | `anonymousUser` |
| `isAuthenticated()` | `true` |
| Ý nghĩa bảo mật | Request được nhận diện là anonymous, không phải người dùng đã đăng nhập |

Ví dụ kiểm tra:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

assertThat(authentication)
        .isInstanceOf(AnonymousAuthenticationToken.class);
assertThat(authentication.getName()).isEqualTo("anonymousUser");
assertThat(authentication.isAuthenticated()).isTrue();
~~~

Điểm dễ nhầm nhất là `isAuthenticated()` trả `true` cho anonymous token. Đây là trạng thái của đối tượng authentication trong cơ chế Spring Security; nó **không có nghĩa người dùng đã đăng nhập đầy đủ** hoặc có quyền truy cập tài nguyên yêu cầu người dùng đã xác thực.

## 2. AnonymousAuthenticationFilter tạo token khi nào?

Trong chuỗi filter Servlet, `AnonymousAuthenticationFilter` chạy sau các cơ chế xác thực thông thường. Nếu `SecurityContext` chưa có `Authentication`, filter tạo `AnonymousAuthenticationToken` và đặt nó vào context hiện tại. Nếu authentication đã tồn tại, filter không thay nó bằng anonymous token.

Có thể hình dung:

~~~text
HTTP request
    │
    ▼
SecurityContextHolderFilter
    │ tải SecurityContext cho request
    ▼
Các authentication filter
    │ có thể đặt Authentication của người dùng đã xác thực
    ▼
AnonymousAuthenticationFilter
    │
    ├─ Authentication đã có ──► giữ nguyên context
    │
    └─ Authentication chưa có ─► tạo AnonymousAuthenticationToken
                                  principal = anonymousUser
                                  authority = ROLE_ANONYMOUS
    │
    ▼
Authorization filter / các thành phần xử lý tiếp theo
    │
    ▼
Controller hoặc phản hồi từ security exception handling
~~~

Sơ đồ mô tả luồng điển hình của cấu hình Servlet. Vị trí và các filter thực tế phụ thuộc cấu hình, cơ chế xác thực và phiên bản Spring Security. Nếu ứng dụng tắt anonymous support hoặc thay đổi filter chain, request chưa xác thực có thể không nhận anonymous token.

Anonymous authentication chủ yếu giúp các thành phần bảo mật làm việc với một trạng thái vô danh tường minh. Nó không tạo tài khoản, không lưu một phiên đăng nhập và không xác minh thông tin đăng nhập.

## 3. Tại sao Spring Security cần anonymous token?

Nếu không có anonymous support, code nghiệp vụ thường phải xử lý hai dạng: có authentication và không có authentication. Anonymous token giúp một request vô danh có một đối tượng `Authentication` nhất quán để các thành phần phân quyền và exception handling đánh giá.

Ví dụ:

- `permitAll()` có thể cho phép request dù không có người dùng đăng nhập.
- `authenticated()` yêu cầu một người dùng được xác thực đầy đủ; anonymous token không đáp ứng điều kiện này.
- `hasRole("READER")` không cho anonymous token quyền `ROLE_READER` mặc định.
- `hasAuthority("ROLE_ANONYMOUS")` có thể nhận diện quyền anonymous nếu ứng dụng giữ authority mặc định; tuy nhiên, không nên dùng quyền này như cơ chế thay thế cho chính sách xác thực.

Spring Security dùng `AuthenticationTrustResolver` để phân biệt anonymous và các mức độ tin cậy khác. Điều này quan trọng vì `AnonymousAuthenticationToken.isAuthenticated()` là `true` nhưng chính sách `authenticated()` vẫn phải từ chối người dùng vô danh.

## 4. Dùng AuthenticationTrustResolver thay vì chỉ kiểm tra isAuthenticated()

Nếu chỉ viết:

~~~java
boolean authenticated = authentication != null
        && authentication.isAuthenticated();
~~~

thì anonymous token cũng làm biến `authenticated` thành `true`. Đây là một lỗi logic thường gặp khi tự viết điều kiện bảo mật hoặc assertion test.

Dùng `AuthenticationTrustResolver` để nhận diện anonymous:

~~~java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;

AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

boolean anonymous = trustResolver.isAnonymous(authentication);
~~~

Ví dụ kiểm tra đầy đủ:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

if (authentication == null) {
    // Chưa có Authentication trong context hiện tại.
} else if (trustResolver.isAnonymous(authentication)) {
    // Đã có anonymous Authentication, không phải người dùng đăng nhập.
} else if (authentication.isAuthenticated()) {
    // Authentication đã được xác thực theo trạng thái của nó.
}
~~~

Trong ứng dụng thực tế, ưu tiên dùng authorization DSL và method security thay vì tự triển khai lại quy tắc xác thực bằng các nhánh điều kiện. `AuthenticationTrustResolver` hữu ích khi cần phân tích trạng thái hoặc viết test cho thành phần tích hợp với Spring Security.

## 5. So sánh vòng đời trong bài test và HTTP request

Một test có thể quan sát hai trạng thái khác nhau tùy vị trí assertion:

~~~text
Luồng JUnit trước request
    │
    ▼
SecurityContextHolder.getContext()
    └─ Authentication = null
       (context trống, chưa thiết lập danh tính)
    │
    ▼
MockMvc.perform(GET /public)
    │
    ▼
Security filter chain
    ├─ SecurityContextHolderFilter tải context
    ├─ AnonymousAuthenticationFilter tạo anonymous token
    ├─ AuthorizationFilter đánh giá quyền
    └─ Controller có thể nhận AnonymousAuthenticationToken
    │
    ▼
Kết thúc request
    └─ context của request được dọn theo vòng đời filter
~~~

Do đó, cùng một test thread có thể thấy `Authentication == null` trước khi gọi `MockMvc.perform(...)`, nhưng controller nhận `AnonymousAuthenticationToken` khi request đi qua filter chain với anonymous support bật.

Cũng cần phân biệt test holder với request context. `@WithAnonymousUser` có thể đặt anonymous context cho test thông qua Spring TestContext listener; khi `MockMvc` đã tích hợp Spring Security, test context có thể được cấp cho request. Ngược lại, một request không gắn người dùng nhưng đi qua security filter cũng có thể được `AnonymousAuthenticationFilter` tạo anonymous token độc lập.

## 6. Kiểm thử context trống bằng code

Khi mục tiêu là xác minh trạng thái ban đầu hoặc việc dọn context, có thể tạo một context trống một cách tường minh:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class EmptySecurityContextTest {

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void newContextHasNoAuthentication() {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();

        assertThat(context).isNotNull();
        assertThat(context.getAuthentication()).isNull();

        SecurityContextHolder.setContext(context);

        assertThat(SecurityContextHolder.getContext()).isSameAs(context);
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication()).isNull();
    }
}
~~~

Trong ví dụ này, `createEmptyContext()` chỉ tạo context mới; nó chưa tự đặt context vào holder. Lời gọi `setContext(context)` mới cài context vào luồng hiện tại. Sau đó `clearContext()` dọn holder trong `@AfterEach` để test khác không nhận trạng thái tồn dư.

Không nên assert rằng `SecurityContextHolder.getContext()` bằng `null` sau `clearContext()`. Với chiến lược mặc định, lần gọi `getContext()` tiếp theo có thể tạo một context trống mới. Hãy kiểm tra `getAuthentication()` hoặc kiểm tra trạng thái trước khi gọi `getContext()` lần nữa nếu mục tiêu là xác minh việc dọn.

## 7. Kiểm thử anonymous token bằng @WithAnonymousUser

`@WithAnonymousUser` thuộc `spring-security-test` và được xử lý bởi `WithSecurityContextTestExecutionListener`. Nó tạo một anonymous authentication giả lập cho bài test. Annotation này hữu ích khi muốn kiểm thử service hoặc method security trong vai trò anonymous mà không cần gửi HTTP request.

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(SpringExtension.class)
class AnonymousUserTest {

    @Test
    @WithAnonymousUser
    void listenerSetsAnonymousAuthentication() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication)
                .isInstanceOf(AnonymousAuthenticationToken.class);
        assertThat(authentication.getName()).isEqualTo("anonymousUser");
        assertThat(authentication.getAuthorities())
                .extracting("authority")
                .contains("ROLE_ANONYMOUS");
        assertThat(authentication.isAuthenticated()).isTrue();
    }
}
~~~

Test này kiểm tra đối tượng anonymous do listener tạo, không kiểm tra hành vi của `AnonymousAuthenticationFilter` trong một HTTP request. Nếu mục tiêu là xác minh filter chain, hãy dùng `MockMvc` với security filter được tích hợp.

Có thể đặt `@WithMockUser` ở cấp lớp rồi ghi đè một test bằng `@WithAnonymousUser`:

~~~java
@WithMockUser(username = "lan", roles = "READER")
class MixedIdentityTests {

    @Test
    void readerIsDefault() {
        // Authentication mặc định là "lan".
    }

    @Test
    @WithAnonymousUser
    void thisMethodRunsAsAnonymous() {
        // Phương thức này dùng AnonymousAuthenticationToken.
    }
}
~~~

Annotation ở cấp phương thức giúp ca kiểm thử anonymous tách biệt khỏi danh tính mặc định của lớp.

## 8. Kiểm thử request anonymous bằng MockMvc

Đối với HTTP Servlet, `AnonymousAuthenticationFilter` cần có trong chuỗi filter của `MockMvc`. Spring Boot thường cấu hình các filter khi dùng `@AutoConfigureMockMvc`; nếu tự dựng MockMvc, hãy áp dụng `springSecurity()`.

Một request postprocessor có sẵn là `anonymous()`:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;

mockMvc.perform(get("/api/profile").with(anonymous()))
        .andExpect(status().isUnauthorized());
~~~

Kết quả `401` phụ thuộc endpoint và entry point, ví dụ cấu hình HTTP Basic. Với form login, phản hồi có thể là redirect `302`. Nếu endpoint `permitAll()`, request anonymous có thể thành công `200`.

Ví dụ lớp test sau giả định ứng dụng có endpoint `GET /api/profile` yêu cầu `authenticated()` và cấu hình HTTP Basic:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AnonymousHttpSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotAccessProtectedEndpoint() throws Exception {
        mockMvc.perform(get("/api/profile").with(anonymous()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserCanAccessEndpoint() throws Exception {
        mockMvc.perform(get("/api/profile").with(user("lan").roles("READER")))
                .andExpect(status().isOk());
    }
}
~~~

Hai test trên giả định `/api/profile` yêu cầu người dùng đã xác thực, và entry point HTTP Basic trả `401` cho anonymous. Request postprocessor `anonymous()` đặt anonymous authentication cho request; `user("lan")` đặt một người dùng giả lập. Cả hai đều phục vụ kiểm tra authorization ở tầng HTTP khi filter chain được bật.

Không dùng `standaloneSetup(controller)` thiếu security filter rồi kết luận anonymous filter đã hoạt động. Khi filter không chạy, controller có thể nhận giá trị khác hoặc request không được kiểm tra theo chính sách thật.

## 9. Quan sát anonymous token trong controller

Để thấy sự khác biệt giữa context trước request và context trong request, có thể dùng một endpoint chỉ phục vụ mục đích minh họa. Giả sử endpoint `GET /api/identity` được cấu hình `permitAll()`:

~~~java
@RestController
class IdentityController {

    @GetMapping("/api/identity")
    Map<String, Object> identity(Authentication authentication) {
        return Map.of(
                "name", authentication == null ? "none" : authentication.getName(),
                "type", authentication == null
                        ? "none" : authentication.getClass().getSimpleName(),
                "authenticated", authentication != null
                        && authentication.isAuthenticated()
        );
    }
}
~~~

Khi gọi endpoint bằng request không có user và anonymous support đang bật, controller có thể nhận `AnonymousAuthenticationToken`, tên `anonymousUser`, và trường `authenticated` là `true`. Đó là lý do trường JSON `authenticated` tự tạo trong ví dụ **không nên dùng làm tiêu chí xác định người dùng đã đăng nhập**.

Nếu muốn trả thông tin anonymous rõ ràng, có thể dùng `AuthenticationTrustResolver`:

~~~java
AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

boolean anonymous = trustResolver.isAnonymous(authentication);
~~~

Trong ứng dụng sản xuất, không nên phơi bày chi tiết lớp authentication hoặc thông tin nội bộ không cần thiết qua endpoint debug. Ví dụ này chỉ giúp hiểu trạng thái trong request; hãy kiểm tra authorization qua kết quả cho phép/từ chối thay vì xây một endpoint chẩn đoán bảo mật.

## 10. Tác động đến authorization và HTTP status

Sự khác biệt giữa context trống và anonymous token thể hiện rõ trong quá trình authorization và xử lý exception:

| Tình huống | Trạng thái bảo mật | Hành vi điển hình |
| --- | --- | --- |
| Chưa có authentication trước filter | `Authentication == null` | Chưa đủ thông tin để kết luận request đã được phân loại anonymous |
| Request qua anonymous filter | `AnonymousAuthenticationToken` | Được nhận diện là anonymous |
| Quy tắc `permitAll()` | Không yêu cầu đăng nhập | Cho phép cả anonymous |
| Quy tắc `authenticated()` | Yêu cầu người dùng được xác thực đầy đủ | Anonymous bị từ chối |
| Quy tắc `hasRole("READER")` | Cần authority `ROLE_READER` | Anonymous mặc định không có quyền |
| Người dùng đã xác thực nhưng thiếu role | Authentication không anonymous, thiếu authority | Thường trả `403 Forbidden` |
| Anonymous bị chặn ở endpoint bảo vệ | Authentication được trust resolver nhận diện anonymous | Exception handling thường gọi authentication entry point: `401` hoặc redirect |

Trong chuỗi filter mặc định, `ExceptionTranslationFilter` sử dụng `AuthenticationTrustResolver` để phân biệt trường hợp anonymous với trường hợp người dùng đã xác thực nhưng bị từ chối. Với anonymous, framework thường bắt đầu quy trình xác thực qua `AuthenticationEntryPoint`. Với người dùng đã xác thực nhưng thiếu quyền, `AccessDeniedHandler` thường xử lý và trả `403`.

Mã HTTP cuối cùng còn phụ thuộc cấu hình entry point, access denied handler, cơ chế đăng nhập và endpoint. Vì vậy, khi viết test, nêu rõ giả định như HTTP Basic, form login hoặc custom entry point để assertion `401`/`302`/`403` có ý nghĩa.

## 11. Anonymous support có thể bị thay đổi

Spring Security bật anonymous support trong cấu hình HTTP thông thường. Tuy nhiên, ứng dụng có thể tùy chỉnh hoặc tắt nó:

~~~java
http.anonymous(anonymous -> anonymous.disable());
~~~

Khi anonymous support bị tắt, filter không tạo `AnonymousAuthenticationToken`. Request không có thông tin xác thực có thể để `SecurityContextHolder` không có authentication, tùy các filter và cơ chế khác trong ứng dụng.

Cũng có thể tùy chỉnh principal hoặc authority anonymous:

~~~java
http.anonymous(anonymous -> anonymous
        .principal("guest")
        .authorities("ROLE_GUEST"));
~~~

Khi cấu hình tùy chỉnh, không giả định tên luôn là `anonymousUser` hay authority luôn là `ROLE_ANONYMOUS`. Viết test dựa trên chính sách ứng dụng hoặc giá trị cấu hình thực tế. Nếu authorization rule dùng `hasRole("GUEST")`, anonymous token tùy chỉnh có authority `ROLE_GUEST` có thể được phép bởi rule đó; hãy cân nhắc kỹ vì bạn đang trao quyền cho mọi request vô danh.

Tắt anonymous support không đồng nghĩa endpoint tự động an toàn. Quy tắc authorization vẫn phải được khai báo rõ ràng, và test cần xác minh kết quả request theo cấu hình thật.

## 12. Đối chiếu với Reactive và WebTestClient

Trong WebFlux, không dùng `SecurityContextHolder` dạng ThreadLocal để đọc context của pipeline. Spring Security Reactive truyền context qua Reactor Context và cung cấp `ReactiveSecurityContextHolder`. Filter tương ứng với Servlet `AnonymousAuthenticationFilter` là `AnonymousAuthenticationWebFilter`: khi pipeline request chưa có authentication và anonymous support đang bật, filter cung cấp anonymous authentication cho phần xử lý tiếp theo.

Có thể đọc authentication trong một reactive pipeline như sau:

~~~java
Mono<Authentication> authentication =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication);
~~~

Nếu không có security context trong Reactor Context, `ReactiveSecurityContextHolder.getContext()` có thể hoàn tất rỗng (`Mono.empty()`). Nếu request đã đi qua anonymous web filter, pipeline có thể nhận một `SecurityContext` chứa `AnonymousAuthenticationToken`. Vì thế, ở Reactive cũng cần phân biệt **không có context trong Reactor Context** với **có context chứa anonymous authentication**.

Với `WebTestClient`, một request không gắn người dùng sẽ được filter chain xử lý theo cấu hình anonymous của ứng dụng. Khi muốn mô phỏng một người dùng đã xác thực, dùng configurer như `mockUser(...)`; không dùng `SecurityContextHolder` của test thread để suy ra danh tính trong pipeline.

~~~java
webTestClient.get()
        .uri("/api/profile")
        .exchange()
        .expectStatus().isUnauthorized();
~~~

Đoạn trên giả định endpoint yêu cầu xác thực và entry point cấu hình để trả `401`. Kết quả có thể khác nếu ứng dụng dùng form login, custom entry point hoặc tắt anonymous support. Trong bài test reactive method security, `@WithAnonymousUser` có thể được đưa vào Reactor Context nhờ `ReactorContextTestExecutionListener`; đây là cơ chế test riêng, còn HTTP filter vẫn chịu trách nhiệm cho request WebFlux.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách kiểm tra đúng |
| --- | --- | --- |
| `getAuthentication() == null` nghĩa là request anonymous | Nó chỉ nói context hiện tại chưa có authentication | Quan sát request sau filter hoặc dùng `@WithAnonymousUser`/`anonymous()` |
| `AnonymousAuthenticationToken.isAuthenticated()` là người dùng đăng nhập | Anonymous token thường trả `true` | Dùng `AuthenticationTrustResolver.isAnonymous(...)` |
| `SecurityContextHolder.getContext()` trả null sau `clearContext()` | Với strategy mặc định, lần gọi tiếp theo có thể tạo context rỗng mới | Kiểm tra authentication, không assert context null |
| `@WithAnonymousUser` kiểm thử anonymous filter | Nó đặt context cho test qua listener | Dùng MockMvc request qua filter chain để kiểm tra filter |
| Request `401` chứng minh `Authentication` là null | Filter có thể đã tạo anonymous token rồi exception handling gọi entry point | Kiểm tra cả context trong request và HTTP response nếu cần |
| Request `403` luôn nghĩa user đã đăng nhập | CSRF hoặc cấu hình khác cũng có thể gây `403` | Kiểm tra response, CSRF và authorization rule |
| `ROLE_ANONYMOUS` là quyền người dùng guest thật | Đây là authority mặc định để nhận diện anonymous | Tùy chỉnh và kiểm tra authority theo cấu hình; không cấp quyền nhạy cảm cho anonymous |

## 14. Bài thực hành

Tạo một ứng dụng Servlet có endpoint `/api/profile` yêu cầu `authenticated()` và endpoint `/public` dùng `permitAll()`. Bật Spring Security anonymous support mặc định, sau đó thực hiện:

1. Viết test thuần tạo `SecurityContext` mới bằng `SecurityContextHolder.createEmptyContext()`, xác minh context khác null nhưng authentication null.
2. Gọi `SecurityContextHolder.clearContext()` trong cleanup và giải thích vì sao không nên assert `getContext()` bằng null sau khi gọi lại.
3. Dùng `@WithAnonymousUser` để kiểm tra `AnonymousAuthenticationToken`, principal và authority.
4. Dùng `MockMvc` với `.with(anonymous())` gọi `/public`, xác minh request được phép.
5. Gọi `/api/profile` dưới anonymous và user `READER`; kiểm tra phản hồi tương ứng với HTTP Basic.
6. Dùng `AuthenticationTrustResolverImpl` để chứng minh anonymous token có `isAuthenticated() == true` nhưng vẫn được nhận diện là anonymous.
7. Tắt anonymous support trong một cấu hình test riêng và quan sát sự khác nhau trong request chưa xác thực.
8. Thử tùy chỉnh principal/authority anonymous; đánh giá ảnh hưởng tới các rule `hasRole` và `hasAuthority`.

Sau bài thực hành, hãy trả lời được: **Context có tồn tại không? Authentication có tồn tại không? Nếu có, trust resolver phân loại nó thế nào?** Ba câu hỏi này giúp tránh nhầm trạng thái context nội bộ với danh tính của HTTP request.

## Tài liệu tham khảo

- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
- [Spring Security API — AnonymousAuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AnonymousAuthenticationToken.html)
- [Spring Security API — AuthenticationTrustResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html)
- [Spring Security API — AnonymousAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AnonymousAuthenticationFilter.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
