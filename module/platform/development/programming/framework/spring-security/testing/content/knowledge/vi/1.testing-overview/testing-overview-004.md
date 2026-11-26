# Đối chiếu tầng HTTP, tầng phương thức và thành phần bảo mật riêng lẻ

## Mục tiêu học tập

Một ứng dụng Spring Security thường có nhiều lớp ra quyết định: bộ lọc xử lý request HTTP, cơ chế bảo vệ phương thức Java và những thành phần nhỏ như bộ chuyển đổi JWT thành quyền, bộ kiểm tra mật khẩu hoặc quy tắc sở hữu tài nguyên. Nếu chỉ kiểm tra một lớp, bạn có thể bỏ sót lỗi ở lớp khác.

Sau bài này, bạn có thể:

- Phân biệt chính xác **kiểm thử tầng HTTP**, **kiểm thử tầng phương thức** và **kiểm thử từng thành phần bảo mật**.
- Lựa chọn `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` hoặc unit test dựa theo cơ chế cần chứng minh.
- Viết các ca **được phép** và **bị từ chối** ở từng tầng, đồng thời nhận diện trường hợp test vô tình bị chặn bởi một cơ chế khác.
- Giải thích giới hạn của mock JWT/OAuth2/OIDC: đã có danh tính giả lập khác với chứng minh quá trình xác minh credential/token.
- Ghép các lớp kiểm thử thành chiến lược bao phủ thực tế cho ứng dụng Servlet và Reactive.

Đây là bài tổng quan trong module **SPRING_SECURITY_TESTING**. Mục đích xuyên suốt là kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test`, tập trung vào bằng chứng kiểm thử tại đúng lớp xử lý.

## 1. Tại sao cùng một yêu cầu bảo mật cần nhiều tầng kiểm thử?

Xét yêu cầu nghiệp vụ:

> Chỉ nhân viên có quyền `orders:approve` được phê duyệt đơn hàng. Người dùng thông thường không được phê duyệt, kể cả khi họ đã đăng nhập.

Ứng dụng có thể triển khai yêu cầu này theo nhiều cách:

1. **Tại HTTP:** `SecurityFilterChain` bảo vệ `POST /api/orders/approve`.
2. **Tại phương thức:** `@PreAuthorize("hasAuthority('orders:approve')")` đặt trên `ApprovalService.approve()`.
3. **Tại thành phần riêng lẻ:** `ApprovalPolicy` kiểm tra trạng thái đơn hàng, chủ sở hữu, người duyệt hoặc dữ liệu quyền của doanh nghiệp; các thành phần khác ánh xạ scope JWT thành `GrantedAuthority`.

Một test chỉ gọi `ApprovalPolicy.canApprove(...)` có thể chứng minh đúng **quy tắc nghiệp vụ**, nhưng không chứng minh request đã đi qua Spring Security. Một test `MockMvc` có thể chứng minh API chặn người thiếu quyền, nhưng nếu request bị chặn vì **thiếu CSRF token** thì bạn chưa kiểm tra được cơ chế phê duyệt.

Ba tầng phải được hiểu như **những phạm vi quan sát khác nhau**.

### 1.1. Bức tranh xử lý

~~~mermaid
flowchart TD
    T["Bài kiểm thử"] --> H["HTTP: MockMvc / WebTestClient"]
    H --> F["Servlet SecurityFilterChain / Reactive SecurityWebFilterChain"]
    F --> C["Controller / Handler"]
    C --> M["Method security: @PreAuthorize / interceptor"]
    M --> P["Thành phần riêng lẻ: converter, policy, validator"]
    P --> D["Dữ liệu / nghiệp vụ"]
    T --> MT["Test gọi bean Spring"]
    MT --> M
    T --> UT["Unit test thuần Java"]
    UT --> P
~~~

Sơ đồ này diễn đạt ba **đường thử**:

- Test HTTP đi từ request qua chuỗi bảo mật web và có thể đi tiếp xuống method security, policy, nghiệp vụ.
- Test phương thức gọi thẳng **bean Spring được quản lý**, giúp quan sát interceptor/proxy mà không cần đi qua URL, CORS, CSRF hoặc bộ lọc HTTP.
- Unit test thành phần gọi trực tiếp một lớp/hàm được thiết kế tách biệt, giúp cô lập quy tắc và kiểm tra nhiều tổ hợp dữ liệu.

Không nên kết luận các thành phần luôn chạy theo một thứ tự cố định trong mọi kiến trúc. Ứng dụng có thể không sử dụng method security, có nhiều filter chain, hoặc dùng các thành phần bảo mật khác nhau tùy endpoint.

## 2. Bảng đối chiếu ba tầng

| Tiêu chí | Tầng HTTP | Tầng phương thức | Thành phần riêng lẻ |
| --- | --- | --- | --- |
| **Đối tượng quan sát** | Request/response qua Spring MVC hoặc WebFlux. | Lời gọi phương thức có interceptor hoặc proxy bảo mật. | Hàm, converter, validator, policy hoặc manager cụ thể. |
| **Công cụ tiêu biểu** | `MockMvc`, `WebTestClient`, `spring-security-test`. | Spring test context, `@WithMockUser`, `SecurityContext`, `StepVerifier` khi Reactive. | JUnit, AssertJ, Mockito khi cần mock phụ thuộc. |
| **Giả lập thường dùng** | User, roles, JWT, OAuth2/OIDC principal; CSRF token. | Principal/authorities; dữ liệu phụ thuộc service. | Object `Jwt`, `Authentication`, dữ liệu policy hoặc repository giả. |
| **Phát hiện tốt** | Sai request matcher, filter, entry point, CSRF, HTTP status, response headers. | Sai `@PreAuthorize`/`@PostAuthorize`, sai điều kiện ở service, cấu hình bật method security. | Sai chuyển đổi claim → authority, sai so sánh ownership, sai quy tắc dữ liệu. |
| **Không tự chứng minh** | Token giả lập đã qua xác minh chữ ký; mọi method được gọi ngoài HTTP đều an toàn. | HTTP filter/CSRF/CORS đã chạy; credential thật đã được kiểm tra. | Spring proxy/filter đã được gắn; hành vi HTTP hoàn chỉnh. |
| **Chi phí tương đối** | Trung bình đến cao tùy test context và hạ tầng. | Trung bình nếu cần Spring context; có thể thấp hơn test HTTP đầy đủ. | Thấp và nhanh khi lớp ít phụ thuộc. |
| **Kết quả thường kiểm tra** | `200`/`201`, `401`, `403`, body, header, tác động dữ liệu. | Giá trị trả về hoặc `AccessDeniedException`/reactive error. | Giá trị đúng/sai, tập authorities, exception hoặc state. |

Không có tầng nào “cao cấp” hơn về giá trị tuyệt đối. Mỗi tầng trả lời một câu hỏi khác, và việc chọn sai tầng sẽ tạo ra kết luận bảo mật thiếu cơ sở.

## 3. Chuẩn bị một hợp đồng bảo mật xuyên suốt

Ta dùng ứng dụng Spring MVC minh họa có ba đường dẫn:

| Đường dẫn | Chính sách |
| --- | --- |
| `GET /api/me` | Chỉ người dùng đã xác thực. |
| `GET /api/admin/audit` | Chỉ người có `ROLE_ADMIN`. |
| `POST /api/orders/approve` | Request phải được xác thực và có CSRF token hợp lệ; service chỉ thực hiện khi có authority `orders:approve`. |

Ví dụ sau giả định **Spring Boot 3.x và Spring Security 6.x**, đã có Spring MVC, Spring Security, Spring Security Test, JUnit 5 và thư viện kiểm thử Spring Boot tương ứng. Những phiên bản khác có thể thay đổi package hoặc API cấu hình.

Cấu hình Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class DemoSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
        // CSRF được giữ ở chế độ mặc định.
    }
}
~~~

Service được bảo vệ ở tầng phương thức:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class ApprovalService {

    @PreAuthorize("hasAuthority('orders:approve')")
    public String approve() {
        return "approved";
    }
}
~~~

Controller nhận request rồi gọi service:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
class DemoController {

    private final ApprovalService approvalService;

    DemoController(ApprovalService approvalService) {
        this.approvalService = approvalService;
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin/audit")
    String audit() {
        return "audit-ok";
    }

    @PostMapping("/api/orders/approve")
    String approve() {
        return approvalService.approve();
    }
}
~~~

Để kiểm tra bằng `MockMvc`, bổ sung phụ thuộc kiểm thử:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Đây là hợp đồng minh họa để giải thích **lớp nào bảo vệ điều gì**. Trong dự án thực tế, HTTP policy và method policy cần thống nhất về ý nghĩa nghiệp vụ; không phải ứng dụng nào cũng cần đặt cùng một điều kiện ở cả hai lớp.

## 4. Tầng HTTP: chứng minh request đi qua bảo vệ web

### 4.1. Những gì test HTTP thực sự nhìn thấy

Ở Servlet, `MockMvc` có thể gửi request qua các filter của ứng dụng trong test context mà không phải mở một cổng mạng. Khi dùng `@SpringBootTest` cùng `@AutoConfigureMockMvc`, ứng dụng thường nạp cấu hình bảo mật thực tế và đưa các filter vào `MockMvc`.

Test HTTP có thể phát hiện:

- Sai cấu hình `requestMatchers`, ví dụ quên bảo vệ `/api/admin/**`.
- Anonymous request được chuyển sang entry point sai.
- Người đã xác thực nhưng thiếu authority vẫn truy cập được route nhạy cảm.
- CSRF bị bỏ qua hoặc áp dụng sai ở các HTTP method làm thay đổi trạng thái.
- Security headers hoặc response body không như chính sách.
- Lỗi phát sinh khi kết nối filter, controller và method security qua request.

**Điểm cần giữ rõ:** nếu gắn `user()`, `@WithMockUser` hay `jwt()` trong bài test, Spring Security Test tạo sẵn trạng thái xác thực. Bài kiểm thử đó có thể kiểm tra **phân quyền HTTP** nhưng không kiểm tra mật khẩu hoặc chữ ký JWT.

### 4.2. Ví dụ MockMvc với ca cho phép và từ chối

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class HttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotOpenProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void regularUserCannotOpenAudit() throws Exception {
        mvc.perform(get("/api/admin/audit")
                .with(user("linh").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAudit() throws Exception {
        mvc.perform(get("/api/admin/audit")
                .with(user("mai").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit-ok"));
    }

    @Test
    void requestWithApprovalAuthorityAndCsrfSucceeds()
            throws Exception {
        mvc.perform(post("/api/orders/approve")
                .with(user("mai").authorities(
                    new SimpleGrantedAuthority("orders:approve")))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("approved"));
    }

    @Test
    void requestWithNoApprovalAuthorityIsForbidden()
            throws Exception {
        mvc.perform(post("/api/orders/approve")
                .with(user("linh").authorities(
                    new SimpleGrantedAuthority("orders:read")))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
~~~

Giải thích kết quả:

- `GET /api/me` từ người chưa xác thực nhận `401` vì ví dụ cấu hình HTTP Basic. Với form login, kết quả có thể là chuyển hướng `302` thay vì `401`.
- `GET /api/admin/audit` từ `ROLE_USER` nhận `403` do quy tắc `hasRole("ADMIN")` ở **tầng HTTP**.
- Hai test `POST /api/orders/approve` có `csrf()` để không bị chặn vì thiếu CSRF. Trong ví dụ, đường dẫn POST chỉ yêu cầu **đã xác thực** ở HTTP, còn điều kiện `orders:approve` đến từ **method security** của service.
- Người có authority `orders:approve` nhận `200` và nội dung thành công; người có `orders:read` nhưng không có `orders:approve` nhận `403`.

Cặp test cuối minh họa một trường hợp **test đi từ HTTP nhưng phát hiện lỗi ở tầng phương thức**. Khi chẩn đoán, cần biết test đã đi qua những lớp nào để không ghi công nhầm cho HTTP matcher.

### 4.3. Đừng để CSRF che lỗi phân quyền

Nếu viết:

~~~java
mvc.perform(post("/api/orders/approve")
        .with(user("linh").authorities(
            new SimpleGrantedAuthority("orders:read"))))
    .andExpect(status().isForbidden());
~~~

bài test có thể **xanh dù bạn xóa** `@PreAuthorize`. Nguyên nhân là request thiếu CSRF token, nên `CsrfFilter` chặn trước khi đi tới service.

Khi muốn kiểm thử phân quyền của một endpoint POST, hãy giữ CSRF hợp lệ trong cả ca được phép và bị từ chối. Khi muốn kiểm thử CSRF, hãy giữ nguyên danh tính/quyền và lần lượt thử token thiếu, sai, hợp lệ.

### 4.4. Kiểm tra cấu hình security mà MockMvc thực sự sử dụng

Nếu tự tạo client qua `MockMvcBuilders.webAppContextSetup(context)`, nên áp dụng `springSecurity()`:

~~~java
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Khi dùng `@WebMvcTest`, test context dạng slice có thể không nạp đầy đủ tất cả security configuration và service của ứng dụng. Khi đó `403`/`200` có thể xuất phát từ một cấu hình khác production. Hãy xác định rõ chain nào được nạp; dùng `@SpringBootTest` nếu mục tiêu là kiểm tra tích hợp đầy đủ giữa web security và các bean ứng dụng.

Tầng HTTP cũng có thể kiểm tra credential thực: ví dụ `httpBasic("linh", "wrong")` qua filter và `AuthenticationProvider` đã được cấu hình. Tuy nhiên, điều đó khác với `.with(user(...))`, vốn thiết lập sẵn danh tính.

## 5. Tầng phương thức: chứng minh Spring thực thi chính sách trên bean

### 5.1. Khác biệt cốt lõi

Một service có thể được gọi từ controller, job, message consumer hoặc service khác. Nếu quyền chỉ được đặt trên URL, những đường gọi không qua HTTP có thể không được bảo vệ bằng chính sách đó.

Method security đưa điều kiện vào thời điểm gọi phương thức, ví dụ:

~~~java
@PreAuthorize("hasAuthority('orders:approve')")
public String approve() {
    return "approved";
}
~~~

Trong Spring Security 6.x, cần bật phương thức bảo mật, thường bằng `@EnableMethodSecurity` với ứng dụng Servlet hoặc phương pháp imperative tương ứng. Spring sử dụng interceptor/proxy để áp dụng điều kiện. Vì thế, test có ý nghĩa phải gọi **bean Spring đã được bảo vệ**, không phải object tự tạo bằng `new ApprovalService()`.

### 5.2. Test trực tiếp service bean

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest
class MethodSecurityTest {

    @Autowired
    ApprovalService approvalService;

    @Test
    @WithMockUser(authorities = "orders:approve")
    void approverCanApprove() {
        assertThat(approvalService.approve()).isEqualTo("approved");
    }

    @Test
    @WithMockUser(authorities = "orders:read")
    void readerCannotApprove() {
        assertThatThrownBy(() -> approvalService.approve())
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Ở đây, test **không gửi request HTTP**. Không có `POST`, không cần CSRF token, không cần status `403`. Kết quả đúng ở tầng này là **method trả kết quả mong đợi hoặc ném ngoại lệ phân quyền**.

Những gì test phương thức chứng minh:

- Điều kiện `@PreAuthorize` thực sự được Spring áp dụng khi gọi bean.
- Cùng một service trả kết quả khác nhau khi `SecurityContext` chứa các authorities khác nhau.
- Nếu ai đó vô tình xóa annotation hoặc đổi điều kiện, ca bị từ chối sẽ thất bại.

Những gì test chưa chứng minh:

- Filter HTTP có bảo vệ đúng đường dẫn không.
- CORS/CSRF/HTTP security headers có đúng không.
- Người dùng đã được xác thực bằng credential hay token thực hay chưa.
- Lời gọi tự tạo object, lời gọi nội bộ `this.approve()` hoặc đường đi khác có chắc chắn qua proxy hay không.

**Lưu ý tự gọi trong cùng bean:** nếu một phương thức trong service gọi phương thức được bảo vệ của chính nó bằng `this.method()`, lời gọi nội bộ có thể bỏ qua proxy và do đó bỏ qua interceptor. Cần kiểm chứng đường gọi thực sự của ứng dụng; không chỉ nhìn thấy annotation rồi mặc nhiên kết luận tất cả đường gọi đều an toàn.

### 5.3. SecurityContext và @WithMockUser ở tầng phương thức

`@WithMockUser` là cách ngắn gọn để Spring Security Test chuẩn bị một `Authentication` giả lập. Trong ứng dụng Servlet, `SecurityContextHolder.getContext().getAuthentication()` thường giúp lấy principal hiện tại.

Nếu cần principal có dữ liệu riêng, dùng `@WithUserDetails` hoặc `@WithSecurityContext` với factory tùy chỉnh. Điều quan trọng là **chủ thể và authorities trong test** phản ánh đúng điều kiện mà method security đang đọc.

Ví dụ, `hasRole("ADMIN")` thường cần authority `ROLE_ADMIN`; còn `hasAuthority("orders:approve")` cần đúng chuỗi `orders:approve`. Hai điều kiện này không tương đương.

### 5.4. Cẩn thận với quyền theo đối tượng

Ví dụ một phương thức chỉ cho người sở hữu đơn hàng được xem:

~~~java
@PreAuthorize("@orderAccess.canView(authentication.name, #orderId)")
public OrderDetail getOrder(long orderId) {
    return repository.getDetail(orderId);
}
~~~

Đây là đoạn mã minh họa: ứng dụng phải có bean `orderAccess`, repository và kiểu `OrderDetail`.

Test cần chuẩn bị **ít nhất hai đơn hàng có chủ khác nhau** và kiểm tra:

- `linh` được xem đơn do `linh` sở hữu.
- `linh` bị từ chối khi xem đơn của `mai`, dù cả hai có cùng `ROLE_USER`.
- ID không tồn tại và trạng thái tài nguyên đặc biệt được xử lý theo hợp đồng.
- Nếu là thao tác ghi, người bị từ chối không tạo ra thay đổi dữ liệu.

Các test này thuộc tầng phương thức nếu gọi bean Spring được bảo vệ. Riêng tính đúng của hàm `orderAccess.canView(...)` có thể được kiểm thử sâu hơn ở tầng thành phần riêng lẻ.

## 6. Thành phần riêng lẻ: cô lập quy tắc để kiểm tra nhiều trường hợp

“Thành phần bảo mật riêng lẻ” không có nghĩa là dựng toàn bộ Spring Security rồi gửi HTTP request. Bạn kiểm tra trực tiếp một đơn vị có đầu vào, đầu ra rõ ràng, chẳng hạn:

- `JwtGrantedAuthoritiesConverter` hoặc converter tùy biến: ánh xạ claim thành danh sách quyền.
- `PasswordEncoder`: kiểm tra tính nhất quán của mã hóa và so sánh mật khẩu trong phạm vi thuật toán được chọn.
- Chính sách `OrderAccessPolicy`: quyết định người dùng có được đọc đơn hàng không.
- Hàm kiểm tra trạng thái tài khoản, chủ sở hữu hoặc điều kiện nghiệp vụ có ảnh hưởng đến quyền.
- `AuthorizationManager` tùy biến nếu ứng dụng xây dựng quyết định phân quyền ở đối tượng này.

Đây là tầng rất phù hợp để kiểm tra nhiều tổ hợp đầu vào, điều kiện biên và quy tắc bị thay đổi. Unit test ở đây thường nhanh, dễ đọc và có lỗi rõ nguyên nhân.

### 6.1. Ví dụ: kiểm thử converter ánh xạ scope JWT

Với một resource server, scope trong JWT thường được ánh xạ thành các authority có tiền tố `SCOPE_`. Bạn có thể kiểm tra trực tiếp converter mà không cần khởi động web server:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtGrantedAuthoritiesConverter;

import static org.assertj.core.api.Assertions.assertThat;

class JwtAuthoritiesConverterTest {

    private final JwtGrantedAuthoritiesConverter converter =
        new JwtGrantedAuthoritiesConverter();

    @Test
    void scopesBecomePrefixedAuthorities() {
        Jwt jwt = Jwt.withTokenValue("fake-token")
            .header("alg", "RS256")
            .claim("scope", "reports.read orders.approve")
            .build();

        assertThat(converter.convert(jwt))
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder(
                "SCOPE_reports.read", "SCOPE_orders.approve");
    }

    @Test
    void absentScopeProducesNoScopeAuthority() {
        Jwt jwt = Jwt.withTokenValue("fake-token")
            .header("alg", "RS256")
            .claim("sub", "linh")
            .build();

        assertThat(converter.convert(jwt)).isEmpty();
    }
}
~~~

**Điểm cần hiểu:** object `Jwt` ở đây được tạo trực tiếp trong bộ nhớ, không được kiểm tra chữ ký dù header mang tên thuật toán. Bài test chứng minh **chuyển đổi claim → authority**, không chứng minh bearer token thật hợp lệ.

Nếu ứng dụng dùng claim tên riêng, hoặc quy tắc chuyển role từ nhiều claim, bạn có thể viết một converter riêng rồi tạo bảng test cho chuỗi rỗng, claim thiếu, kiểu dữ liệu sai, authority trùng lặp và quyền không hợp lệ theo hợp đồng.

### 6.2. Ví dụ: kiểm thử chính sách sở hữu đơn hàng thuần Java

~~~java
record Order(long id, String ownerUsername) {}

final class OrderAccessPolicy {

    boolean canView(String requester, Order order) {
        return requester != null
            && order != null
            && requester.equals(order.ownerUsername());
    }
}
~~~

Unit test:

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderAccessPolicyTest {

    private final OrderAccessPolicy policy = new OrderAccessPolicy();
    private final Order order = new Order(42L, "linh");

    @Test
    void ownerCanView() {
        assertThat(policy.canView("linh", order)).isTrue();
    }

    @Test
    void otherUserCannotView() {
        assertThat(policy.canView("mai", order)).isFalse();
    }

    @Test
    void missingPrincipalCannotView() {
        assertThat(policy.canView(null, order)).isFalse();
    }

    @Test
    void missingOrderCannotBeViewed() {
        assertThat(policy.canView("linh", null)).isFalse();
    }
}
~~~

Bốn test này nhanh và chỉ nhắm vào một quy tắc. Nhưng chúng **không chứng minh** controller hay service thực sự gọi `OrderAccessPolicy` ở nơi cần thiết. Do đó cần ít nhất một test method security hoặc HTTP để chứng minh policy được **kết nối vào luồng xử lý** và chặn người thiếu quyền.

### 6.3. Unit test không thay thế kiểm thử tích hợp của converter

Ví dụ, bạn đã kiểm tra converter tạo `SCOPE_reports.read`, nhưng ứng dụng cấu hình `hasAuthority("ROLE_reports.read")`. Converter đúng theo thiết kế riêng mà **đường tích hợp vẫn sai**.

Một test HTTP hoặc method security cần xác minh rằng authority sau khi ánh xạ được dùng đúng để ra quyết định. Các đường test bổ sung có thể kiểm tra JWT có chữ ký không hợp lệ, sai issuer, hết hạn hoặc audience không đúng với `JwtDecoder` và validator thực sự.

## 7. Servlet và Reactive: cùng ba tầng nhưng cơ chế truyền ngữ cảnh khác

### 7.1. So sánh ngữ cảnh bảo mật

| Nội dung | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Bảo vệ HTTP | `SecurityFilterChain` với Servlet filters. | `SecurityWebFilterChain` với WebFilters. |
| Test HTTP | `MockMvc` và security request post-processors. | `WebTestClient` gắn vào application context và `SecurityMockServerConfigurers`. |
| Mock user | `user()`, `@WithMockUser`. | `mockUser()`, hoặc annotation tương thích với test context thích hợp. |
| Mock JWT | `jwt()`. | `mockJwt()`. |
| Mock OAuth2/OIDC | `oauth2Login()`, `oidcLogin()`. | `mockOAuth2Login()`, `mockOidcLogin()`. |
| Ngữ cảnh trong ứng dụng | Thường truy cập qua `SecurityContextHolder`. | Truy cập theo Reactor context qua `ReactiveSecurityContextHolder`. |
| Method security | `@EnableMethodSecurity`. | `@EnableReactiveMethodSecurity`. |

Không nên dùng `ThreadLocal` của Servlet như cơ chế truyền authentication giữa những bước bất đồng bộ trong WebFlux. Với luồng Reactive, context được truyền theo subscription, nên bài test phải quan sát việc thực thi publisher thay vì chỉ khởi tạo object `Mono`/`Flux`.

### 7.2. Ví dụ HTTP ở WebFlux: WebTestClient

Trong một **ứng dụng WebFlux riêng** có endpoint `GET /api/admin/audit` và cấu hình `SecurityWebFilterChain` yêu cầu `ROLE_ADMIN` cho `/api/admin/**`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.*;

@SpringBootTest
class ReactiveHttpSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void init() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void userCannotReadAdminAudit() {
        client.mutateWith(mockUser("linh").roles("USER"))
            .get().uri("/api/admin/audit")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadAdminAudit() {
        client.mutateWith(mockUser("mai").roles("ADMIN"))
            .get().uri("/api/admin/audit")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Ví dụ này kiểm tra **tầng HTTP Reactive**, với principal giả lập. Bạn có thể mở rộng để thử `mockJwt()`, `mockOAuth2Login()`, `mockOidcLogin()` và `csrf()` theo chính sách được cấu hình.

**Phạm vi cần nhớ:** các thao tác `mutateWith(mockUser(...))`, `mutateWith(mockJwt())` áp dụng cho client gắn mock server/application context trong tiến trình test. Nếu `WebTestClient` gửi HTTP đến server đang chạy ở một cổng thật, mock principal trong test process không tự xuất hiện trong server; cần gửi credential hoặc token qua request.

### 7.3. Method security trong Reactive phải thực thi publisher

Với WebFlux, service có thể trả `Mono<String>`:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveApprovalService {

    @PreAuthorize("hasAuthority('orders:approve')")
    public Mono<String> approve() {
        return Mono.just("approved");
    }
}
~~~

Ứng dụng cần bật `@EnableReactiveMethodSecurity` và inject **bean Spring** vào test. Có thể truyền authentication qua Reactor context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication
    .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

import java.util.List;

@SpringBootTest
class ReactiveMethodSecurityTest {

    @Autowired
    ReactiveApprovalService service;

    @Test
    void reactiveApproverCanApprove() {
        Authentication auth = UsernamePasswordAuthenticationToken
            .authenticated("mai", "n/a", List.of(
                new SimpleGrantedAuthority("orders:approve")));

        StepVerifier.create(service.approve().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth)))
            .expectNext("approved")
            .verifyComplete();
    }

    @Test
    void reactiveReaderIsDenied() {
        Authentication auth = UsernamePasswordAuthenticationToken
            .authenticated("linh", "n/a", List.of(
                new SimpleGrantedAuthority("orders:read")));

        StepVerifier.create(service.approve().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth)))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

Đây là **kiểm thử tầng phương thức Reactive**; `StepVerifier` subscribe để đoạn mã bảo mật được thực thi. Nếu chỉ gọi `service.approve()` rồi bỏ qua publisher, bạn có thể không kích hoạt những bước xử lý quan trọng.

Ví dụ Reactive ở mục này thuộc một ứng dụng WebFlux riêng, không nên ghép nguyên xi với bộ cấu hình Servlet ở mục 3. Các class WebFlux và Servlet có cơ chế context/filter khác nhau, dù cùng kiểm tra chính sách “có quyền thì cho phép”.

## 8. Đặt JWT, OAuth2 và OIDC đúng tầng kiểm thử

Ba nhóm bằng chứng thường bị trộn lẫn khi viết bài test:

| Tình huống | Tầng thích hợp | Cần hiểu kết quả |
| --- | --- | --- |
| Converter ánh xạ `scope` sang `SCOPE_*` | Thành phần riêng lẻ | Mapping claim → authority đúng. |
| `@PreAuthorize` với authority từ user mock | Phương thức | Bean được chặn hoặc cho phép đúng theo authority. |
| `MockMvc` với `jwt()` trên URL yêu cầu scope | HTTP | URL và downstream policy áp dụng đúng authority của JWT giả lập. |
| `WebTestClient` với `mockJwt()` | HTTP Reactive | WebFilterChain và handler chấp nhận/từ chối principal giả lập đúng. |
| `oauth2Login()` / `oidcLogin()` hoặc mock tương ứng | HTTP / logic sau login | Ứng dụng dùng principal, claims và quyền sau đăng nhập đúng. |
| JWT chữ ký sai, issuer không hợp lệ, token hết hạn | HTTP tích hợp qua xác thực thật | Decoder/validator từ chối token theo chính sách. |
| OAuth2 authorization code callback, state/nonce, session | Tích hợp hoặc end-to-end | Luồng đăng nhập thật và các kiểm tra liên quan được thực thi. |

Cần phân biệt hai lời khẳng định:

- **“Người có authority này được xem tài nguyên.”** Test dùng JWT/OIDC mock có thể chứng minh chính sách phân quyền nếu cấu hình web/method đúng.
- **“Server xác minh đúng bằng chứng danh tính.”** Cần kiểm thử cơ chế tiếp nhận và xác minh credential/token thực tế. Tạo sẵn `JwtAuthenticationToken` không phải phép kiểm thử chữ ký.

Đối với các ứng dụng dùng nhiều nguồn danh tính, nên kiểm tra thêm mapping giữa issuer, scope, group hoặc claim tùy biến và authority nội bộ. Một lỗi converter có thể khiến cả HTTP và method security đưa ra quyết định sai dù biểu thức phân quyền không sai.

## 9. Ba cách phát hiện cùng một lỗi: ví dụ quy tắc phê duyệt

Giả sử thành viên nhóm thay đổi nhầm yêu cầu từ `orders:approve` thành `orders:read`.

### 9.1. Ở tầng thành phần

Nếu một policy hoặc converter cung cấp quyền phê duyệt, unit test có thể phát hiện người chỉ có quyền đọc được đánh dấu là có quyền duyệt. Test thường cho biết chính xác **hàm nào trả sai**.

### 9.2. Ở tầng phương thức

Test `@WithMockUser(authorities = "orders:read")` gọi `ApprovalService.approve()` phải ném `AccessDeniedException`. Nếu annotation bị xóa hoặc đổi sai, test sẽ thất bại dù HTTP route không thay đổi.

### 9.3. Ở tầng HTTP

Test gửi `POST /api/orders/approve` với người có quyền đọc, **CSRF token hợp lệ**, rồi mong đợi `403`. Nó phát hiện hợp đồng API bị phá vỡ và xác minh hành vi của các lớp kết hợp trong đường request. Nếu test thiếu CSRF token, `403` có thể đến từ CSRF filter nên không phát hiện được thay đổi ở method security.

Bảng phân biệt nguyên nhân:

| Test thất bại | Nghi ngờ chính | Cách thu hẹp |
| --- | --- | --- |
| Unit policy/converter sai | Quy tắc dữ liệu hoặc mapping sai. | Kiểm tra input, expected output và ranh giới claim/authority. |
| Unit đúng, method test sai | Annotation, proxy, method security config hoặc SecurityContext sai. | Gọi bean Spring, xác minh `@EnableMethodSecurity` và authorities thực. |
| Method đúng, HTTP test sai | Request matcher, filter, entry point, CSRF, controller wiring. | Giữ các điều kiện khác cố định và kiểm tra chain thực sự được nạp. |
| Mock HTTP đúng, token thật sai | Decoder/validator, issuer/audience, cấu hình resource server. | Gửi bearer token qua xác thực thật ở test tích hợp. |
| Các test nội bộ đúng, trình duyệt lỗi | CORS, cookie, HSTS, reverse proxy, redirect, môi trường triển khai. | Kiểm tra request thực và response headers/session. |

Đây cũng là lý do một **bộ test có vài tầng bổ sung nhau** thường mang lại bằng chứng tốt hơn một bộ rất nhiều test chỉ gửi cùng kiểu mock request.

## 10. Lập ma trận test theo “lớp chịu trách nhiệm”

Ví dụ về kế hoạch kiểm thử tối thiểu cho ứng dụng phê duyệt đơn hàng:

| Chính sách/rủi ro | Thành phần riêng lẻ | Phương thức | HTTP |
| --- | --- | --- | --- |
| Phân biệt `orders:read` và `orders:approve` | Converter/policy cho quyền chính xác. | Reader bị từ chối; approver được phép. | Cặp `POST` cùng CSRF hợp lệ, khác authority. |
| Chỉ admin xem audit | Có thể unit test role mapping. | Test method nếu audit service có annotation. | `ROLE_USER` nhận `403`; `ROLE_ADMIN` nhận `200`. |
| Anonymous không xem hồ sơ | Không nhất thiết có unit test. | Tùy phương thức có cần bảo vệ riêng. | Anonymous nhận `401` hoặc redirect theo entry point. |
| CSRF chặn POST không hợp lệ | Test phần tạo/đọc token nếu có tùy biến. | Không phải trách nhiệm của service. | Thiếu/sai token bị từ chối, đúng token được xử lý. |
| Không xem đơn của người khác | Policy sở hữu với các ca biên. | Bean service từ chối người không sở hữu. | Endpoint không lộ dữ liệu hoặc tác động ghi trái phép. |
| JWT scope → authority | Unit test `JwtGrantedAuthoritiesConverter` hoặc converter tùy biến. | Kiểm tra quyền tại service. | Mock JWT có/không scope, rồi thêm test token thật khi cần. |
| Response security headers | Test config nếu có policy tùy biến. | Không phải trách nhiệm của service. | Assert các header theo cấu hình thực. |

Ma trận này giúp tránh viết lại mọi tổ hợp dữ liệu qua toàn bộ application context. Ví dụ, kiểm tra 50 biến thể của policy sở hữu trong unit test có thể hiệu quả; dùng một số ca đại diện ở method và HTTP để xác nhận policy thực sự được áp dụng trong đường xử lý.

## 11. Những dấu hiệu cho thấy bài test đang kiểm tra sai tầng

### 11.1. “Tôi test method security bằng cách gọi new Service()”

Nếu bạn tự tạo service, `@PreAuthorize` có thể không hoạt động vì interceptor/proxy của Spring không được dùng. Cần lấy bean từ Spring context và kích hoạt method security.

### 11.2. “Tôi test quyền POST nhưng không truyền CSRF”

Kết quả `403` có thể do CSRF. Hãy cung cấp `csrf()` khi mục tiêu là role/authority; chỉ bỏ token trong test **chủ đích kiểm tra CSRF**.

### 11.3. “Tôi dùng jwt() nên đã kiểm tra JWT an toàn”

`jwt()` và `mockJwt()` dựng authentication giả lập. Muốn kiểm tra chữ ký, thời hạn và issuer, cần đi qua decoder/validator hoặc bài tích hợp phù hợp.

### 11.4. “Unit test policy đúng nghĩa là endpoint đã được bảo vệ”

Hàm policy đúng nhưng controller quên gọi, method annotation thiếu hoặc filter chain sai thì API vẫn có thể lộ dữ liệu. Cần test liên kết tại phương thức hoặc HTTP.

### 11.5. “Tôi test WebTestClient tại RANDOM_PORT bằng mockUser()”

Mock security dành cho test client gắn mock server trong cùng tiến trình. Gọi server qua mạng cần credential/token thật; mock principal không tự truyền qua HTTP.

### 11.6. “Tôi chỉ kiểm tra trường hợp admin được 200”

API có thể bị mở công khai và test admin vẫn thành công. Thêm test người không có quyền bị từ chối; test này phải thất bại nếu bỏ quy tắc bảo vệ.

### 11.7. “Mọi lỗi thiếu quyền đều là 403”

Mã phản hồi phụ thuộc trạng thái xác thực và cấu hình entry point/handler. Anonymous request trong ứng dụng HTTP Basic có thể nhận `401`; ứng dụng form login có thể trả `302`; policy ẩn tài nguyên có thể trả `404`. Test cần mô tả **hợp đồng cụ thể**.

## 12. Bài thực hành

Thực hiện lần lượt trên ứng dụng Servlet minh họa, sau đó chọn một phần để chuyển sang WebFlux:

1. **Tầng HTTP:** dùng `MockMvc` viết ca anonymous bị từ chối ở `GET /api/me`, `ROLE_USER` bị từ chối tại `/api/admin/audit` và `ROLE_ADMIN` được phép.
2. **Tầng phương thức:** gọi bean `ApprovalService` với `@WithMockUser(authorities = "orders:approve")` rồi với `orders:read`. Xác minh giá trị trả về và `AccessDeniedException`.
3. **Phân biệt nguyên nhân:** viết `POST /api/orders/approve` thiếu CSRF token. Tạm thời bỏ `@PreAuthorize` trong môi trường thực hành và xem test thiếu CSRF có còn `403` không. Sau đó thêm CSRF hợp lệ để chứng minh test quyền phát hiện lỗi.
4. **Thành phần:** viết unit test converter JWT gồm scope hợp lệ, thiếu scope và tên authority mong đợi. Giải thích vì sao test này không xác minh chữ ký.
5. **Chính sách sở hữu:** thêm một `OrderAccessPolicy` với trường hợp người sở hữu, người khác và principal rỗng; tích hợp policy vào service được bảo vệ rồi xác nhận bằng test.
6. **Reactive:** tạo một ứng dụng WebFlux nhỏ tương ứng, dùng `WebTestClient` gắn application context để kiểm tra cặp `mockUser()` được phép/bị từ chối; nếu dùng reactive method security, xác minh publisher bằng `StepVerifier`.
7. **Kiểm thử thực tế:** bổ sung một bài test gửi credential hoặc bearer token không hợp lệ qua HTTP thật ở test context. So sánh bằng chứng thu được với test mock principal.

**Tiêu chí hoàn thành:** với mỗi test, bạn có thể trả lời bốn câu hỏi: *thành phần nào được chạy, đầu vào nào bị thay đổi, điều kiện nào tạo ra kết quả, và điều gì chưa được kiểm chứng?*

## 13. Ghi nhớ

Kiểm thử bảo mật hiệu quả dựa trên sự phối hợp giữa ba tầng:

- **HTTP** xác nhận request đi qua filter/WebFilter, các quy tắc URL, CSRF và cơ chế bảo vệ web.
- **Phương thức** xác nhận proxy/interceptor bảo vệ những lời gọi service khi đã có `SecurityContext` phù hợp.
- **Thành phần riêng lẻ** xác nhận converter, policy và các phép biến đổi dữ liệu/quyền hoạt động đúng với nhiều trường hợp.

Trong Servlet, `MockMvc` là công cụ trung tâm cho HTTP; trong WebFlux, `WebTestClient` được dùng với cấu hình bảo mật Reactive. `@WithMockUser`, `jwt()`, `mockJwt()` và các tiện ích OAuth2/OIDC giúp tạo danh tính giả lập để thử quyết định được phép hoặc bị từ chối. Khi mục tiêu là kiểm tra chính quá trình xác thực credential/token, bạn phải cho request đi qua cơ chế xác thực thực tế.

Một bộ kiểm thử có giá trị không chỉ cho thấy “request bị từ chối”, mà còn chỉ ra **đúng tầng nào đã từ chối, vì quy tắc nào và bằng chứng đó mạnh đến đâu**.
