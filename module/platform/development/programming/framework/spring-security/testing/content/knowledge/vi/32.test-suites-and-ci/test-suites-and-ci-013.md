# Phát hiện test không có khẳng định hoặc chỉ kiểm tra dữ liệu tự giả lập

## 1. Vì sao một test xanh có thể không tạo ra bằng chứng?

Trong một dự án Spring Security, test sau có thể luôn xanh:

~~~java
@Test
void privateEndpointTest() throws Exception {
    mockMvc.perform(get("/api/private"));
}
~~~

Nó có gửi một mock request, nhưng **không có assertion nào về kết quả**. Nếu endpoint vô tình đổi từ `401` sang `200`, test vẫn có thể xanh. Một lỗi cấu hình bảo mật nghiêm trọng đã không làm bộ test thất bại.

Trường hợp khác tinh vi hơn:

~~~java
@Test
void jwtTest() throws Exception {
    mockMvc.perform(get("/api/reports")
            .with(jwt().jwt(token -> token
                    .subject("alice")
                    .claim("scope", "reports.read"))))
        .andExpect(status().isOk());
}
~~~

Test thứ hai **có assertion hợp lệ** nhưng chỉ xác nhận ứng dụng chấp nhận `JwtAuthenticationToken` **do test tự tạo**. Nó không chứng minh JWT được gửi qua HTTP, chữ ký được xác minh, issuer đúng hoặc token hết hạn bị từ chối.

Trong chương **Bộ kiểm thử và CI** của module `SPRING_SECURITY_TESTING`, người học cần kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên Servlet và Reactive, bao gồm `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Vì thế, một test bảo mật có giá trị không chỉ phải **chạy**, mà còn phải **khẳng định điều quan sát được từ hệ thống thật sự đang kiểm thử**.

Mục tiêu của bài:

1. Nhận diện test **không có assertion**, assertion luôn đúng hoặc assertion không liên quan yêu cầu.
2. Phân biệt **fixture / mock input** với **output của System Under Test (SUT)**.
3. Phân tích đúng giới hạn của `@WithMockUser`, `user()`, `jwt()`, `oauth2Login()`, `mockJwt()` và `mockOidcLogin()`.
4. Chuyển test yếu thành test có ca **được phép** và **bị từ chối**, kiểm chứng status, body, header và side effect theo hợp đồng.
5. Dùng `StepVerifier` đúng cách để thực sự subscribe `Mono`/`Flux`.
6. Thiết lập quy trình review và CI nhằm phát hiện lỗ hổng “test xanh giả”, hiểu vai trò của coverage và mutation testing.

## 2. Phân loại các mức bằng chứng trong một test

Khi review một test, đặt câu hỏi: **“Nếu cơ chế bảo mật tôi muốn kiểm tra bị tắt hoặc triển khai sai, assertion nào sẽ thất bại?”**

| Nhóm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Không có assertion** | `mockMvc.perform(get(...));` | Có thể chỉ cho biết request không ném exception tại điểm gọi |
| **Assertion hình thức** | `assertNotNull(request);` ngay sau khi test tự tạo request | Chủ yếu kiểm tra dữ liệu test tự tạo |
| **Assertion yếu về hành vi** | `status().isOk()` với principal do test tự cấp | Kiểm tra một phần đường xử lý, chưa kiểm tra nguồn authentication |
| **Assertion policy rõ ràng** | USER `403`, ADMIN `200`, anonymous `401` | Kiểm tra phân quyền theo tình huống cụ thể |
| **Assertion authentication thực** | HTTP Basic sai mật khẩu `401`, đúng mật khẩu `200` | Kiểm tra đường xác minh credentials nếu provider thật được bật |
| **Assertion giao thức/token** | JWS ký sai `401`, ký đúng nhưng thiếu scope `403` | Kiểm tra decoder/validator và policy nếu không bị mock |
| **Assertion side effect** | Request bị chặn và dữ liệu nhạy cảm không bị thay đổi | Kiểm tra việc từ chối có thực sự bảo vệ hệ thống |

Không có một con số assertion tối thiểu áp dụng cho mọi test. Một assertion có mục tiêu rõ có thể mạnh hơn hàng chục assertion chỉ kiểm tra DTO do test dựng sẵn. Ngược lại, test có nhiều matcher vẫn có thể vô giá trị khi matcher không đi qua component cần kiểm tra.

### 2.1. Cấu trúc một test bảo mật có sức phát hiện lỗi

Một test nên làm rõ ít nhất bốn phần:

1. **Threat / yêu cầu:** người chưa đăng nhập không xem được báo cáo; người có `ROLE_USER` không được xóa tài khoản khác.
2. **Stimulus:** request HTTP hoặc lời gọi bean thực tế, gồm credentials/headers cần thiết.
3. **Observation:** status/body/header/error/side effect từ **SUT**, không phải từ object do test tự tạo.
4. **Counterexample:** ca trái ngược hoặc biến thể đối chứng để phát hiện policy bị mở quá rộng hoặc bị khóa hoàn toàn.

Ví dụ câu chấp nhận:

> Với `GET /api/admin`, khách không có credentials nhận `401`; tài khoản USER đã xác thực nhận `403`; ADMIN đã xác thực nhận `200`.

Nó mô tả ba trạng thái khác nhau và cho test một tiêu chí rõ hơn “endpoint hoạt động”.

## 3. Test không có assertion: phát hiện và sửa

### 3.1. Những mẫu mã nguồn đáng nghi

~~~java
@Test
void noAssertions() throws Exception {
    mockMvc.perform(get("/api/admin"));
}

@Test
void printOnly() throws Exception {
    var response = mockMvc.perform(get("/api/admin")).andReturn();
    System.out.println(response.getResponse().getStatus());
}

@Test
void ignoredResult() {
    client.get().uri("/api/admin").exchange();
}

@Test
void emptyBranch() {
    if (isUserAllowed()) {
        // không assert gì
    }
}
~~~

Các test trên có thể phát hiện exception khi setup hoặc request thất bại nghiêm trọng, nhưng **không kiểm tra hợp đồng bảo mật**. `System.out.println` chỉ ghi log; `.andReturn()` hay `.exchange()` chỉ thu response, không có kỳ vọng cụ thể.

Test JUnit Jupiter **không bắt buộc** có một hàm `assertEquals`. Assertions có thể nằm trong các API khác như `.andExpect(...)`, `.expectStatus()`, `StepVerifier` hoặc `assertThrows(...)`; vì vậy không nên dùng quy tắc máy móc “không thấy `assert*` thì test chắc chắn sai”.

### 3.2. Sửa bằng assertion trên hành vi quan sát được

~~~java
@Test
void anonymousCannotReadAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin"))
           .andExpect(status().isUnauthorized());
}

@Test
void userCannotReadAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin")
            .with(user("reader").roles("USER")))
           .andExpect(status().isForbidden());
}

@Test
void adminCanReadAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin")
            .with(user("admin").roles("ADMIN")))
           .andExpect(status().isOk())
           .andExpect(content().string("admin"));
}
~~~

Ví dụ giả định `SecurityFilterChain` yêu cầu authentication cho `/api/admin`, chỉ cho `ROLE_ADMIN`, dùng **HTTP Basic entry point** khi chưa có credentials, và controller trả chuỗi `admin`. Với form login, request anonymous có thể nhận `302` thay vì `401`; assertion phải phản ánh **security chain thực tế**, không sao chép máy móc.

`.andExpect(status().isUnauthorized())` sẽ thất bại nếu guest bỗng được `200`, nhưng nó vẫn chưa chứng minh provider đã kiểm tra password bởi không có credentials nào được gửi. Để kiểm tra password, xem mục 6.

## 4. Assertion chỉ kiểm tra dữ liệu do test tự giả lập

### 4.1. Test tự tạo cả input lẫn kết quả mong đợi

~~~java
@Test
void meaninglessRoleTest() {
    var roles = List.of("ROLE_ADMIN", "ROLE_USER");
    assertTrue(roles.contains("ROLE_ADMIN"));
}
~~~

Trong test trên, Spring Security, authorization manager và endpoint **không hề chạy**. Assertion kiểm tra `List` của chính test. Nó không cho biết người dùng thật nào được cấp quyền.

Một biến thể khác:

~~~java
@Test
void fakeJwtClaimsLookCorrect() {
    Jwt jwt = Jwt.withTokenValue("fake")
        .header("alg", "none")
        .claim("scope", "reports.read")
        .build();

    assertEquals("reports.read", jwt.getClaimAsString("scope"));
}
~~~

Đây chỉ là kiểm tra dữ liệu `Jwt` do test tự dựng. Nó **không** gửi bearer token qua decoder, không kiểm tra chữ ký và không chạy policy. Nếu mục tiêu thực sự là test builder/serialization, có thể là một unit test phụ trợ, nhưng tên “JWT security test” sẽ gây hiểu nhầm.

### 4.2. Không đồng nhất fixture với SUT

Phân biệt:

- **Fixture:** username, roles, JWT claims, response của mock server, dữ liệu được insert trước test.
- **SUT:** Spring Security filters, authentication providers, authorization managers, token decoder/validator, controller/service hoặc cơ chế tích hợp mà ta muốn kiểm tra.
- **Observation:** response status, error, principal/authorities do SUT tính ra, bản ghi database thay đổi hoặc không thay đổi, outbound HTTP request do SUT gửi.

Ví dụ, tạo `OAuth2AuthorizedClient` với access token `"fake-token"` rồi assert `authorizedClient.getAccessToken().getTokenValue()` bằng chính chuỗi `"fake-token"` **không chứng minh token endpoint đã được gọi**. Để chứng minh giao thức OAuth2 Client, phải kích hoạt token grant và quan sát `POST` tới token endpoint thử nghiệm.

### 4.3. Mock quá sâu có thể làm biến mất đối tượng cần kiểm tra

~~~java
// Anti-pattern khi mục tiêu là kiểm tra decoder thực:
when(jwtDecoder.decode(anyString())).thenReturn(fakeJwt);
~~~

Nếu `JwtDecoder` luôn trả `Jwt` do Mockito cung cấp, test không thể phát hiện lỗi chữ ký, hạn, issuer hoặc algorithm trong decoder thật. Test đó có thể phù hợp để cô lập controller, **nhưng không nên được ghi nhận là test JWT validation**.

Tương tự, nếu mock `AuthenticationManager` luôn chấp nhận hoặc mock cả service chứa `@PreAuthorize`, một test HTTP `200` có thể không đi qua các cơ chế cần kiểm tra.

## 5. Một ứng dụng Servlet mẫu để kiểm tra quality của test

Ví dụ Spring Boot Servlet nhỏ:

~~~java
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AuditController {

    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/audit")
    Map<String, String> audit(Authentication authentication) {
        return Map.of("principal", authentication.getName());
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }
}
~~~

Cấu hình bảo mật:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuditSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(requests -> requests
                    .requestMatchers("/api/public").permitAll()
                    .requestMatchers("/api/admin").hasRole("ADMIN")
                    .requestMatchers("/api/audit").authenticated()
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-password"))
                .roles("ADMIN")
                .build());
    }
}
~~~

Fixture có username/password **chỉ phục vụ test**. Trong môi trường thật cần tài khoản và secret được quản lý an toàn. Cấu hình này giữ mặc định CSRF; các ví dụ `GET` không cần CSRF token. Nếu muốn test `POST`, phải xét CSRF tách biệt.

Test context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuditSecurityTests {
    @Autowired
    MockMvc mockMvc;

    // Các phương thức @Test bên dưới đặt trong lớp này.
}
~~~

Ví dụ giả định Spring Boot application thực sự nạp controller và `AuditSecurityConfig`; `@AutoConfigureMockMvc` giữ Spring Security filters mặc định. Không sử dụng `addFilters = false` khi mục tiêu là kiểm tra HTTP security.

## 6. Viết cặp test chứng minh authentication chứ không chỉ mock principal

### 6.1. Test policy với principal giả

~~~java
@Test
void policyAllowsAnyAlreadyAuthenticatedUserAtAuditEndpoint()
        throws Exception {
    mockMvc.perform(get("/api/audit")
            .with(user("not-in-user-store").roles("USER")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.principal")
            .value("not-in-user-store"));
}
~~~

Test có ích: endpoint yêu cầu `authenticated()`; principal do `spring-security-test` cung cấp được xử lý đúng. Nhưng `not-in-user-store` không tồn tại trong `UserDetailsService`. Test **không kiểm tra tra cứu account hoặc password**.

### 6.2. Test authentication bằng HTTP Basic credentials

~~~java
@Test
void wrongPasswordIsRejected() throws Exception {
    mockMvc.perform(get("/api/audit")
            .with(httpBasic("reader", "wrong-password")))
        .andExpect(status().isUnauthorized());
}

@Test
void rightPasswordIsAuthenticated() throws Exception {
    mockMvc.perform(get("/api/audit")
            .with(httpBasic("reader", "reader-password")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.principal").value("reader"));
}

@Test
void unknownUsernameIsRejected() throws Exception {
    mockMvc.perform(get("/api/audit")
            .with(httpBasic("unknown", "any-password")))
        .andExpect(status().isUnauthorized());
}

@Test
void anonymousRequestIsRejected() throws Exception {
    mockMvc.perform(get("/api/audit"))
        .andExpect(status().isUnauthorized());
}
~~~

`httpBasic(...)` tạo header HTTP Basic; **nó không tự gắn principal đã được xác thực**. Các request được đưa qua security filters và provider thật của **test context** để kiểm tra credentials. Đây là bằng chứng tốt hơn về authentication so với `with(user(...))`.

### 6.3. Thêm hai phía của authorization

~~~java
@Test
void readerCannotAccessAdmin() throws Exception {
    mockMvc.perform(get("/api/admin")
            .with(httpBasic("reader", "reader-password")))
        .andExpect(status().isForbidden());
}

@Test
void adminCanAccessAdmin() throws Exception {
    mockMvc.perform(get("/api/admin")
            .with(httpBasic("admin", "admin-password")))
        .andExpect(status().isOk())
        .andExpect(content().string("admin"));
}
~~~

Với các ca trên, nếu `hasRole("ADMIN")` bị xóa hoặc vô tình đổi sang `permitAll()`, ít nhất ca `readerCannotAccessAdmin` phải thất bại. Nếu mọi tài khoản bị từ chối vì provider hỏng, ca `adminCanAccessAdmin` sẽ thất bại.

Một bộ test bảo mật vững nên có cả **ca dương** (đúng credentials, đủ quyền) và **ca âm** (thiếu credentials, sai credentials, thiếu quyền), không chỉ có một nhóm.

## 7. Kiểm tra mục tiêu của từng assertion

| Mục tiêu muốn chứng minh | Assertion nên quan sát | Đừng dừng ở |
| --- | --- | --- |
| Guest không vào endpoint bảo vệ | `401`/redirect theo entry point thực | `perform(...)` không ném exception |
| USER không vào admin | `403` với một user **đã xác thực** | Một user giả được cấp role khác trong list test |
| ADMIN được phép | `200` và body mong đợi | `assertNotNull(mockUser)` |
| Password sai bị từ chối | Gửi HTTP Basic/form credentials sai, assert auth failure | `@WithMockUser` được phép |
| JWT sai chữ ký bị từ chối | Gửi bearer JWS ký bằng khóa khác qua decoder thật, assert `401` | `jwt()` hoặc `mockJwt()` với claims tự tạo |
| Token thiếu scope không đủ quyền | Token đã xác thực nhưng scope thiếu, assert `403` | Assert một `List` chứa `SCOPE_reports.read` |
| CSRF bảo vệ write request | POST thiếu CSRF `403`, POST có token + auth phù hợp thành công | Chỉ một GET được `200` |
| Không có side effect khi bị chặn | Dữ liệu trước và sau request không đổi | Chỉ HTTP response `403` |
| OIDC callback xác minh ID token | Integration test IdP/test server, token thật và validator | `oidcLogin()` tạo principal giả |

Không nhất thiết assert mọi header/body trong mọi test. Chọn các tín hiệu đủ mạnh để phân biệt đúng tình huống. Với lỗi authorization, `403` quan trọng; với lỗi authentication, kết quả phải phù hợp entry point của cơ chế đó. Một status đơn lẻ có thể chưa cho biết filter nào từ chối, đặc biệt khi CSRF tham gia.

## 8. Reactive test: `exchange()` không thay thế assertions

WebFlux dùng `WebTestClient` để kiểm tra HTTP policy. Một test yếu:

~~~java
@Test
void emptyReactiveTest() {
    webTestClient.get()
        .uri("/api/admin")
        .exchange();
}
~~~

Vẫn thiếu kỳ vọng về status/body. Một test tốt hơn:

~~~java
@Test
void mockUserCannotAccessReactiveAdmin() {
    webTestClient.mutateWith(mockUser("reader").roles("USER"))
        .get()
        .uri("/api/admin")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void mockAdminCanAccessReactiveAdmin() {
    webTestClient.mutateWith(mockUser("admin").roles("ADMIN"))
        .get()
        .uri("/api/admin")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("admin");
}
~~~

Ví dụ giả định một WebFlux application context có `SecurityWebFilterChain` yêu cầu `ROLE_ADMIN`, và `webTestClient` đã được bind bằng `WebTestClient.bindToApplicationContext(context).apply(springSecurity()).configureClient().build()`. Với HTTP Basic entry point, thêm ca guest `401`; nếu cấu hình form login redirect thì assert redirect thay vì `401`.

### 8.1. Test password thật trong WebFlux

Khi muốn kiểm tra `ReactiveAuthenticationManager` và `ReactiveUserDetailsService` thay vì mock user, gửi Basic header:

~~~java
@Test
void wrongReactivePasswordIsRejected() {
    webTestClient.get()
        .uri("/api/admin")
        .headers(h -> h.setBasicAuth("admin", "wrong-password"))
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void correctReactivePasswordAndRoleWork() {
    webTestClient.get()
        .uri("/api/admin")
        .headers(h -> h.setBasicAuth("admin", "admin-password"))
        .exchange()
        .expectStatus().isOk();
}
~~~

Các ca này chỉ kiểm tra provider thật khi **WebFlux test context thực sự cấu hình HTTP Basic và có user store dùng các credentials trên**. Không thể lấy `SecurityFilterChain` Servlet của mục 5 rồi cho rằng `WebTestClient.bindToApplicationContext` sẽ chạy nó: Servlet và Reactive dùng filter chain khác nhau.

`WebTestClient.bindToServer()` với `@SpringBootTest(RANDOM_PORT)` có thể kiểm tra thêm đường HTTP socket. Các `mockUser()`/`mockJwt()` không tự truyền principal qua mạng; khi thử authentication thật, phải gửi headers, cookies hoặc token.

## 9. Publisher Reactive: không subscribe thì chưa kiểm tra lỗi

Với Reactive method security, đoạn sau quá yếu:

~~~java
@Test
void monoIsNotNull() {
    Mono<String> result = protectedService.readReport();
    assertNotNull(result);
}
~~~

Nó chỉ nhìn thấy **publisher object**. Nhiều chuỗi Reactive là *lazy*: authorization, truy vấn dữ liệu và lỗi có thể chỉ xảy ra khi subscribe.

Giả sử service Spring bean có:

~~~java
@PreAuthorize("hasAuthority('REPORT_READ')")
public Mono<String> readReport() {
    return Mono.just("report");
}
~~~

Test phù hợp:

~~~java
@Test
@WithMockUser(authorities = "REPORT_READ")
void permittedUserGetsReport() {
    StepVerifier.create(protectedService.readReport())
        .expectNext("report")
        .verifyComplete();
}

@Test
@WithMockUser(authorities = "PROFILE_READ")
void missingAuthorityIsDenied() {
    StepVerifier.create(protectedService.readReport())
        .expectError(AccessDeniedException.class)
        .verify();
}
~~~

Ở đây test cần nạp `@EnableReactiveMethodSecurity`, service phải là **Spring bean được proxy**, và `spring-security-test`/test listener phải tạo đúng Reactor SecurityContext. `StepVerifier` thực sự subscribe và kiểm tra tín hiệu `onNext`/`onComplete` hoặc `onError`.

Test `assertNotNull(result)` có thể xanh ngay cả khi `@PreAuthorize` bị vô hiệu hóa. Ngược lại, ca âm yêu cầu `AccessDeniedException` sẽ phát hiện policy không còn chặn.

Không viết `.subscribe()` thủ công trong test rồi kết thúc trước khi publisher phản hồi; việc kiểm tra bất đồng bộ phải có completion/error assertion rõ ràng. Với luồng không kết thúc, thiết kế `StepVerifier` theo semantics của publisher, giới hạn timeout phù hợp và kiểm tra cancellation khi cần.

## 10. Cảnh giác assertion chỉ kiểm tra mock interaction

Đôi khi test dùng Mockito:

~~~java
verify(auditRepository).save(any());
~~~

Nó chỉ chứng minh code gọi một mock method. Nó không xác minh database thật đã lưu bản ghi, không chứng minh transaction commit và cũng không chắc dữ liệu nhạy cảm được bảo vệ.

**Interaction assertions có giá trị** khi hành vi mong muốn chính là “không gọi một dependency ở nhánh bị từ chối”, nhưng phải dùng đúng bối cảnh:

~~~java
// Nếu service thực hiện authorization trước khi gọi repository:
assertThrows(AccessDeniedException.class,
    () -> protectedService.deleteRecord("other-owner"));

verifyNoInteractions(repository);
~~~

Đây là một ví dụ mang tính thiết kế: `protectedService` phải đi qua security proxy hoặc check thực, và `repository` là dependency mock được inject dưới service. Nó không phù hợp để assert cho một hàm Reactive mà chưa subscribe. Với Reactive service, cần subscribe bằng `StepVerifier` rồi mới kiểm tra interactions.

**Phân biệt hai câu hỏi:**

- “Có gọi dependency không?” → `verify(...)`, `verifyNoInteractions(...)` phù hợp.
- “Người không đủ quyền có thể thay đổi dữ liệu thật không?” → thêm integration test với repository/database và assert trạng thái trước/sau.

Không coi một `verify(...)` đơn lẻ là bằng chứng end-to-end nếu dependency được mock chính là nơi thực hiện chính sách hoặc lưu trữ cần kiểm chứng.

## 11. Side effect và thuộc tính bảo mật âm

Kiểm tra `403` là cần thiết, nhưng với hành động nguy hiểm nên bổ sung bằng chứng **không có side effect**:

~~~java
@Test
void userCannotDeleteAnotherUsersRecord() throws Exception {
    long before = records.count();

    mockMvc.perform(delete("/api/records/{id}", protectedRecordId)
            .with(user("reader").roles("USER"))
            .with(csrf()))
        .andExpect(status().isForbidden());

    assertEquals(before, records.count());
    assertTrue(records.existsById(protectedRecordId));
}
~~~

Ví dụ này **giả định** repository `records` và `protectedRecordId` là test fixtures đã được tạo trước test, endpoint thực sự có rule từ chối USER. `.with(csrf())` giúp tách nguyên nhân từ chối do **authorization** khỏi `403` do thiếu CSRF. Nếu không cung cấp CSRF khi CSRF đang bật, test có thể xanh vì request bị CSRF filter chặn trước khi đến rule quyền cần kiểm tra.

Để tránh kiểm tra dữ liệu của test thay vì SUT, nên xác nhận `protectedRecordId` thuộc fixture đúng, gọi request, rồi **đọc lại trạng thái repository sau request**. Với database và `RANDOM_PORT`, đảm bảo transaction fixture được commit để server nhìn thấy dữ liệu.

### 11.1. Cặp test chống “deny all”

Nếu service luôn trả `403` cho tất cả request, test “USER bị từ chối” có thể xanh. Vì vậy, thêm ca cùng endpoint:

~~~java
@Test
void adminCanDeleteAuthorizedRecord() throws Exception {
    mockMvc.perform(delete("/api/records/{id}", disposableRecordId)
            .with(user("admin").roles("ADMIN"))
            .with(csrf()))
        .andExpect(status().isNoContent());

    assertFalse(records.existsById(disposableRecordId));
}
~~~

Fixture `disposableRecordId` phải riêng với bản ghi của ca từ chối, nếu không test sẽ phụ thuộc thứ tự. Với nghiệp vụ có soft delete, thay `existsById` bằng assertion đúng trạng thái mềm thay vì giả định bản ghi bị xóa vật lý.

## 12. JWT/OAuth2/OIDC: đừng nhầm fake principal với validation

| Helper | Điều làm được | Không tự chứng minh |
| --- | --- | --- |
| Servlet `with(user(...))` | Principal/role giả trong request MockMvc | User store/password |
| Servlet `with(jwt())` | `JwtAuthenticationToken` giả với claims/authorities | JWS signature, `iss`/`aud`/`exp` validation |
| Servlet `with(oauth2Login())` | `OAuth2AuthenticationToken` giả sau login | Redirect/callback, token endpoint |
| Servlet `with(oidcLogin())` | `OidcUser` giả với claims | ID token signature, nonce, issuer/audience |
| Reactive `mockUser()` | Reactive authentication giả | Password/HTTP Basic |
| Reactive `mockJwt()` | JWT principal giả | `ReactiveJwtDecoder`, JWS signature |
| Reactive `mockOAuth2Login()`/`mockOidcLogin()` | OAuth2/OIDC principal giả | Authorization code flow, token exchange |

### 12.1. Một test giả JWT tốt nếu đặt tên đúng

~~~java
@Test
void jwtPrincipalWithReadScopeMayAccessReports() throws Exception {
    mockMvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
        .andExpect(status().isOk());
}
~~~

Đây có thể là một **authorization policy test** đúng nếu `/api/reports` có rule yêu cầu `SCOPE_reports.read`. Cần thêm ca thiếu scope bị `403`. Nhưng test này **không chạy JWT decoder**; một token giả mang giá trị `exp` quá khứ không khiến decoder thật tự động được gọi.

### 12.2. Nếu yêu cầu là JWT validation

Test phải:

1. Cấu hình `JwtDecoder`/`ReactiveJwtDecoder` thật với khóa và validators phù hợp.
2. Tạo JWS **được ký thật** bằng khóa test, gửi `Authorization: Bearer <token>` qua request.
3. Có token hợp lệ và đủ scope → thành công.
4. Có token sai chữ ký hoặc hết hạn → authentication thất bại, thường `401`.
5. Có token chữ ký/hạn hợp lệ nhưng thiếu scope → authorization thất bại, thường `403`.
6. Không mock decoder thành luôn trả token hợp lệ khi test mục tiêu là chữ ký/issuer/hạn.

Mọi assertions phải quan sát kết quả server xử lý token, **không chỉ assert claims của JWT trước khi gửi**.

### 12.3. Nếu yêu cầu là OAuth2/OIDC protocol

`oauth2Login()`/`oidcLogin()` có thể kiểm tra controller đọc principal sau login. Nếu yêu cầu là “client đã đổi authorization code thành token đúng”, cần dùng IdP/token server thử nghiệm và kiểm tra HTTP token request thật. Nếu yêu cầu là “ID token sai chữ ký hoặc nonce bị từ chối”, cần test validator/flow thật. Một mock principal `200` không đủ.

## 13. Kiểm thử API âm với `401`, `403` và CSRF

Một bộ test dễ gây hiểu nhầm khi chỉ kiểm tra status mà không biết **filter nào từ chối**.

| Request | Ngữ cảnh | Kết quả thường gặp | Điều chứng minh |
| --- | --- | --- | --- |
| GET bảo vệ, guest, HTTP Basic entry point | Chưa xác thực | `401` | Endpoint không mở công khai |
| GET admin, USER đã xác thực | Thiếu `ROLE_ADMIN` | `403` | Authorization chặn USER |
| POST bảo vệ, USER đã xác thực, thiếu CSRF | CSRF bật | `403` | **CSRF** chặn request; chưa kết luận policy role |
| POST bảo vệ, USER có CSRF, thiếu quyền | CSRF hợp lệ | `403` | Có thể quy cho authorization nếu rule tương ứng được chạy |
| POST bảo vệ, ADMIN có CSRF | Đủ quyền và CSRF | `2xx` theo API | Luồng được phép |
| GET bảo vệ, form login | Guest | Thường redirect `302` | Authentication entry point là trang đăng nhập |

Không biến mã `403` thành một lời khẳng định tổng quát “authorization chính xác”: `403` có thể do CSRF, custom access denied handler hoặc policy khác. Muốn kiểm tra rule cụ thể, phải **kiểm soát những điều kiện khác** để request có thể đi tới rule đó.

## 14. Kiểm tra cả nhánh dương lẫn nhánh âm

Một ma trận tối thiểu cho tài nguyên quản trị:

| Test | Input | Kỳ vọng | Lỗi có thể bị bắt |
| --- | --- | --- | --- |
| Guest bị chặn | Không credentials | `401`/redirect | `permitAll` nhầm |
| User sai mật khẩu | Basic sai | `401` | Authentication provider chấp nhận sai |
| User đúng mật khẩu | Basic đúng | `200` ở endpoint riêng | Provider từ chối tất cả |
| USER thiếu quyền | Basic đúng nhưng `ROLE_USER` | `403` ở admin | Admin policy bị mở |
| ADMIN đủ quyền | Basic đúng với `ROLE_ADMIN` | `200` | Deny-all, mapping role sai |
| CSRF thiếu | POST với user hợp lệ, không CSRF | `403` | CSRF bị tắt ngoài ý muốn |
| CSRF đủ | POST với quyền hợp lệ và CSRF | `2xx` | Endpoint không hoạt động |
| JWT sai chữ ký | JWS ký khóa khác | `401` | Decoder không validate |
| JWT thiếu scope | JWS hợp lệ, thiếu scope | `403` | Scope policy bị mở |

Không nhất thiết mọi endpoint cần tất cả ca. Đặt ma trận theo **bề mặt tấn công và thành phần quan trọng**. Endpoint chỉ `permitAll` không cần password test, nhưng endpoint sửa quyền tài khoản phải có test authorization và side effect.

## 15. Dùng mutation testing để biết assertions có bắt được lỗi không

Coverage cao không đồng nghĩa test có assertion tốt. Một test có thể chạy qua 100% dòng của `SecurityFilterChain` nhưng vẫn chỉ gọi `perform(...)` mà không kiểm tra status.

**Mutation testing** cố ý thay đổi logic trong mã để đánh giá test có phát hiện thay đổi không. Ví dụ:

~~~java
.requestMatchers("/api/admin").hasRole("ADMIN")
~~~

Một đột biến giả định:

~~~java
.requestMatchers("/api/admin").permitAll()
~~~

Nếu bộ test có ca guest/USER bị chặn, nó phải đỏ. Nếu chỉ có ca ADMIN `200`, test vẫn xanh, dù chính sách đã mất bảo vệ.

Không phải mọi công cụ mutation testing đều tự sinh ra đúng đột biến cho cấu hình Spring Security. Các điều kiện phát sinh từ DSL, reflection, proxy hoặc bean wiring có thể nằm ngoài phạm vi mutators của công cụ. Vì vậy, có thể thực hiện **một bài thử mutation thủ công trong nhánh cô lập**, rồi khôi phục code, hoặc dùng công cụ như PIT khi phù hợp để bổ sung đánh giá.

### 15.1. Đọc đúng các loại mutation

| Kết quả mutation | Ý nghĩa |
| --- | --- |
| **Killed** | Có test thất bại khi logic bị biến đổi; đây là tín hiệu tích cực |
| **Survived** | Các test được chạy không phát hiện đột biến; cần xem thêm assertion hoặc phạm vi test |
| **No coverage** | Đột biến không được thực thi bởi tests hiện có |
| **Timed out/error** | Có thể do mutation, build hoặc môi trường; cần phân tích, không tự coi là killed |
| **Equivalent mutation** | Mã đổi nhưng hành vi không đổi trong mọi input liên quan; không thể đánh giá như lỗi thật |

Một tỷ lệ mutation score không phản ánh đầy đủ mọi ràng buộc bảo mật. Dùng nó để chỉ ra vùng yếu và thảo luận test scenarios, không thay thế security review hoặc integration tests.

## 16. Đánh giá test suite trong CI: nhiều lớp tín hiệu

Một pipeline tốt không chỉ chạy tests mà còn giúp phát hiện test **bị bỏ qua, không có hiệu lực hoặc quá nhiều mock**.

### 16.1. Tầng cơ bản: build và JUnit

Với Gradle:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    testLogging {
        events "failed", "skipped"
    }
    reports {
        junitXml.required = true
        html.required = true
    }
}
~~~

Trong CI, chạy tác vụ test theo module thực tế:

~~~bash
./gradlew test
~~~

Đây là **ví dụ lệnh cho dự án sử dụng Gradle**, không phải chỉ thị chạy trong bước soạn tài liệu này. CI cần kiểm tra số test được phát hiện, số test bị skip và exit code của task. Một task báo `BUILD SUCCESSFUL` nhưng không tìm thấy test hoặc toàn bộ test bị `@Disabled` **không thể được coi là bằng chứng bộ test bảo mật đã chạy**.

### 16.2. Coverage chỉ là tín hiệu phụ

JaCoCo có thể cho biết dòng/nhánh nào đã được thực thi:

~~~groovy
plugins {
    id 'jacoco'
}

tasks.named('test') {
    finalizedBy tasks.named('jacocoTestReport')
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
    reports {
        xml.required = true
        html.required = true
    }
}
~~~

Để áp ngưỡng coverage, có thể thêm `jacocoTestCoverageVerification` với `violationRules` phù hợp. Nhưng ngưỡng cao chỉ cho thấy code được chạy, không bảo đảm request đã bị từ chối đúng hay JWT được validate.

Ví dụ `GET /api/admin` với `with(user("admin"))` có thể chạy qua code authorization, nhưng không kiểm tra mật khẩu. Coverage không phân biệt được **nguồn principal** mà test sử dụng.

### 16.3. Static analysis và review patterns

Một công cụ lint nội bộ có thể đánh dấu để review các mẫu:

- `@Test` chỉ có `perform(...)` hoặc `exchange()` mà không có `andExpect`/`expectStatus`/assertions.
- `StepVerifier` không có kỳ vọng tín hiệu hữu ích hoặc publisher bị tạo nhưng không subscribe.
- `System.out.println` là quan sát duy nhất.
- `assertTrue(true)`, `assertNotNull(new Object())`, `assertEquals(expected, expected)`.
- Assert trực tiếp trên claims/authorities do test tự tạo khi tên test khẳng định “token verified”.
- `@WithMockUser`/`mockJwt()` xuất hiện trong test mang tên “passwordAuthenticationWorks” hoặc “invalidSignatureIsRejected”.
- `@AutoConfigureMockMvc(addFilters = false)` trong các lớp được coi là security integration tests.
- Mock `JwtDecoder`, `AuthenticationManager` hoặc cả service chứa `@PreAuthorize` trong test nhận là kiểm chứng những thành phần ấy.
- `@Disabled`, `@Ignore`, chỉ chạy một tập test qua filter hoặc test bị loại khỏi CI task.
- Test âm `403` nhưng thiếu CSRF trên `POST` khi muốn kiểm tra role.

**Không tự động gán tất cả là bug.** Có test mock principal rất đúng mục tiêu; có test cần in log để chẩn đoán bổ sung. Static analysis nên tạo **danh sách review**, sau đó developer xác định SUT và hành vi thực, thay vì chỉ đếm cú pháp `assert...`.

## 17. Một checklist review có thể đưa vào pull request

Với mỗi test bảo mật mới hoặc vừa sửa, reviewer kiểm tra:

1. **Mục tiêu:** test có mô tả một ràng buộc bảo mật cụ thể không?
2. **SUT:** thành phần nào đang thật sự chạy: filter, provider, decoder, authorization manager hay chỉ mock?
3. **Input:** principal/authorities/claims có được test dựng sẵn không, hay được suy ra từ HTTP credentials qua provider thật?
4. **Assertion:** ít nhất một điều kiện quan sát được từ SUT có thể thất bại khi policy bị phá không?
5. **Ca âm/dương:** có một ca bị từ chối và một ca được phép phù hợp ranh giới không?
6. **Lỗi nguyên nhân:** `403` có thể do CSRF thay vì role không? `401` có thể do thiếu user fixture thay vì password?
7. **Side effect:** request bị từ chối có chắc không gây thay đổi dữ liệu cần bảo vệ?
8. **Identity mapping:** authorities có đúng với policy và đúng nguồn tin cậy không?
9. **Isolation:** fixture, session, database, test tokens và clock có bị dùng chung giữa tests không?
10. **CI:** test có được phát hiện và chạy thật không? Có bị skip theo profile hoặc tag không?
11. **Naming:** tên test có trung thực về phạm vi mock/integration và hành vi được chứng minh không?
12. **Failure demonstration:** nếu bỏ `hasRole(...)` hoặc cho decoder chấp nhận token sai, test nào sẽ đỏ?

Một cách review hiệu quả là yêu cầu tác giả mô tả **“đột biến tối thiểu nào sẽ làm test này thất bại?”**. Nếu không có câu trả lời rõ, assertion có thể chưa ràng buộc hành vi mong muốn.

## 18. Một chiến lược phân lớp test tránh tự lừa mình

| Lớp | Mục tiêu | Ví dụ | Chi phí |
| --- | --- | --- | --- |
| Unit/policy | Quy tắc phân quyền độc lập | `@WithMockUser`, `@PreAuthorize` và `StepVerifier` | Thấp |
| Mock HTTP integration | Web filters, controllers, method security | `MockMvc` / `WebTestClient` với chain thực | Trung bình |
| Authentication integration | Provider/decoder/authorization được kích hoạt từ credentials | Basic/form/Bearer thật qua mock HTTP | Trung bình |
| Embedded HTTP | Status/headers/cookies qua socket thật | `@SpringBootTest(RANDOM_PORT)` | Cao hơn |
| External protocol contract | Token exchange/OIDC callback/IdP contract | Authorization server hoặc token endpoint test | Cao |
| End-to-end môi trường | Proxy/TLS/IdP/session trên đường thực | Environment kiểm soát, account/secret test | Cao nhất |

Không cần thay mọi `@WithMockUser` bằng login thật. Làm vậy thường khiến test chậm và khó khoanh vùng lỗi. Thay vào đó, **đặt tên và phạm vi trung thực**: nhiều test mock nhanh bao phủ permission matrix, kết hợp số lượng phù hợp integration tests để xác nhận đường xác thực không bị mock.

Với OAuth2/OIDC, dùng fake principal để kiểm tra logic sau login, nhưng có ca khác kiểm tra authorization code, token endpoint, chữ ký và session nếu hệ thống cần bảo đảm đó. Với JWT, dùng `mockJwt()` để kiểm tra claims/role policy, có ca khác dùng JWS ký thật để kiểm tra `JwtDecoder`.

## 19. Bộ câu hỏi thực hành

### Bài 1 — Tìm assertion bị thiếu

Cho test:

~~~java
@Test
void adminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin"))
           .andDo(print());
}
~~~

Hãy thêm assertion status đúng cho guest theo entry point, bổ sung USER `403` và ADMIN `200`. Giải thích vì sao `.andDo(print())` không đủ để phát hiện admin endpoint bị cấu hình `permitAll()`.

### Bài 2 — Từ fixture tự giả thành authentication thật

So sánh `with(user("reader").roles("USER"))` với `with(httpBasic("reader", "reader-password"))`. Viết ca username không tồn tại, mật khẩu sai, mật khẩu đúng. Nêu chính xác test nào có gọi user store/password encoder.

### Bài 3 — Phân biệt CSRF và authorization

Với `DELETE /api/records/123`, viết ca USER có CSRF nhưng thiếu role, và ADMIN có CSRF được phép. Sau đó viết ca ADMIN thiếu CSRF bị từ chối. Giải thích lý do không dùng một `403` thiếu CSRF để khẳng định rule role hoạt động.

### Bài 4 — Lấy bằng chứng từ SUT

Một test tạo JWT có `scope=reports.read` rồi assert chính claim ấy. Hãy biến nó thành policy test gửi `jwt()` qua endpoint, thêm ca thiếu scope. Nếu mục tiêu là validation, đề xuất test JWS ký đúng/sai/hết hạn qua decoder thật.

### Bài 5 — Test Reactive chưa subscribe

Biến `assertNotNull(service.readReport())` thành hai `StepVerifier` tests với `@WithMockUser`: đủ `REPORT_READ` nhận dữ liệu, thiếu `REPORT_READ` phát `AccessDeniedException`. Giải thích tại sao publisher được tạo chưa có nghĩa authorization hoàn tất.

### Bài 6 — Mutation giả định

Giả sử security config đổi `.hasRole("ADMIN")` thành `.permitAll()`. Chỉ ra test nào ở ma trận mục 14 phải thất bại. Nếu không có test nào thất bại, hãy bổ sung một ca âm; sau đó khôi phục policy.

### Bài 7 — Định nghĩa CI gate có ý nghĩa

Thiết kế một CI job chạy JUnit, báo số tests/skipped, sinh coverage và xuất danh sách test đáng nghi cần review. Đừng dừng ở ngưỡng coverage: bổ sung một số ca bảo mật “canary” mà nếu rule sai sẽ thất bại.

## 20. Những kết luận không nên đưa vào báo cáo kiểm thử

| Đã quan sát | Kết luận hợp lệ | Kết luận vượt quá bằng chứng |
| --- | --- | --- |
| `@WithMockUser` có role admin → `200` | Policy chấp nhận mock admin | Password/admin login đã được xác minh |
| `jwt()` có scope read → `200` | Policy chấp nhận JWT principal giả có scope | Chữ ký JWT thật đã được xác thực |
| `oidcLogin()` có claim email → body trả đúng email | Controller đọc đúng OIDC principal giả | OIDC nonce/issuer/signature đã được kiểm tra |
| `httpBasic()` sai password → `401` | Test context từ chối credentials sai qua filters | Hệ thống production với external IdP đã hoạt động |
| `MockMvc` có `401`/`403` đúng | HTTP security trong mock Servlet pipeline hoạt động theo test | Socket/proxy/TLS đã được kiểm tra |
| `RANDOM_PORT` trả `200` | Server HTTP thử nghiệm phục vụ request | Mọi route production, tài khoản và hạ tầng đều an toàn |
| 100% line coverage | Code được thực thi ở mức đo đạc | Test đã kiểm chứng đủ các ràng buộc bảo mật |
| Mutation score cao | Nhiều đột biến thuộc phạm vi công cụ bị tests phát hiện | Không còn lỗi bảo mật hoặc logic chưa được mutate |

Trong báo cáo QA, ghi rõ **đối tượng được kiểm tra**, **input là giả lập hay thực**, **component thật sự chạy** và **giới hạn chưa bao phủ**. Điều này quan trọng hơn việc chỉ đưa ra con số “100% tests passed”.

## 21. Tổng kết

**Một test xanh không phải bằng chứng nếu nó không có điều kiện thất bại gắn với yêu cầu bảo mật.** Test không có assertion, test chỉ kiểm tra dữ liệu mình vừa tạo, hoặc test tự gắn `SecurityContext` rồi kết luận password/JWT/OIDC đã được xác minh là những ví dụ phổ biến của **false confidence**.

Để nâng giá trị của bộ kiểm thử Spring Security:

- Viết assertions vào kết quả thực của SUT: status, response, lỗi, principal, dữ liệu sau request.
- Có cả ca **cho phép** và **từ chối** để phát hiện lỗi “permit all” lẫn “deny all”.
- Chọn đúng ranh giới: `@WithMockUser`/`mockJwt()` cho policy; credentials/JWS thật qua provider/decoder cho authentication.
- Với Reactive, subscribe và kiểm tra signals bằng `StepVerifier`.
- Đọc `403` theo đúng nguồn gốc, không nhầm CSRF với thiếu role.
- Dùng CI, code review, coverage và mutation testing như những **tín hiệu bổ trợ**, không thay thế phân tích bảo mật.

## 22. Tài liệu tham khảo

- [Spring Security — MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): tích hợp security filters và MockMvc assertions.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user()`, `httpBasic()` và authentication requests.
- [Spring Security — MockMvc OAuth2 Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): JWT/OAuth2/OIDC test helpers và phạm vi giả lập.
- [Spring Security — Reactive Web Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): WebTestClient và reactive security tests.
- [Spring Security — Reactive Method Testing](https://docs.spring.io/spring-security/reference/reactive/test/method.html): `StepVerifier` và method authorization tests.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions, lifecycle và test discovery.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): test tasks, reports và test filtering.
- [JaCoCo — Documentation](https://www.jacoco.org/jacoco/trunk/doc/): coverage reports và giới hạn đo đạc.
- [PIT — Mutation Testing](https://pitest.org/): kiểm tra khả năng phát hiện đột biến.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` và tín hiệu Reactive.
