# Ngoại lệ khi thiếu Authentication hoặc không đủ quyền

## 1. Phân biệt xác thực và phân quyền

Trong module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng spring-security-test trên ứng dụng Servlet và Reactive. Một service có thể từ chối lời gọi vì không tìm thấy Authentication, vì caller là anonymous, hoặc vì caller đã đăng nhập nhưng thiếu authority cần thiết. Các tình huống này không đồng nghĩa và có thể dẫn đến ngoại lệ hoặc phản hồi HTTP khác nhau.

Hai câu hỏi cần tách biệt:

- **Authentication (xác thực):** hệ thống đã xác định được caller là ai chưa?
- **Authorization (phân quyền):** caller có được phép thực hiện hành động này không?

Ví dụ service chỉ cho phép authority invoice:approve gọi phương thức approve. Có bốn trạng thái thường gặp:

1. SecurityContext không có Authentication.
2. Có AnonymousAuthenticationToken, tức request chưa đăng nhập nhưng cơ chế anonymous đã đặt một principal đại diện.
3. Có Authentication hợp lệ nhưng thiếu invoice:approve.
4. Có Authentication và đủ invoice:approve.

Trạng thái 1 và 2 đều không đại diện cho người dùng đã đăng nhập, nhưng khác nhau về mặt kỹ thuật. Trạng thái 3 đã xác thực nhưng không đủ quyền. Vì thế, không nên dùng một thông báo chung “login lỗi” cho mọi trường hợp, cũng không nên mặc định mọi lỗi phân quyền đều là 401.

Sau bài này, bạn có thể:

- Phân biệt AuthenticationException, AuthenticationCredentialsNotFoundException và AccessDeniedException.
- Hiểu vai trò của AnonymousAuthenticationToken, AuthenticationTrustResolver và AuthorizationDeniedException ở các phiên bản hiện đại.
- Giải thích cách ExceptionTranslationFilter chuyển lỗi thành 401 hoặc 403 trong ứng dụng Servlet.
- Cấu hình AuthenticationEntryPoint và AccessDeniedHandler để trả phản hồi nhất quán.
- Kiểm thử trường hợp không có Authentication, anonymous, thiếu authority và đủ quyền bằng @WithMockUser, @WithAnonymousUser, MockMvc.
- Kiểm thử WebFlux bằng WebTestClient, hiểu Reactive SecurityContext và các handler tương ứng.
- Tránh bắt ngoại lệ quá rộng, làm mất thông tin bảo mật hoặc trả thông báo nội bộ cho client.

> **Phạm vi phiên bản:** Ví dụ chính dùng Spring Security 6.x, Spring Boot 3.x và JUnit 5. Spring Security 7.x tiếp tục dùng mô hình authorization manager hiện đại. Một số lớp exception hoặc chi tiết nội bộ có thể khác giữa các thế hệ interceptor; trong code ứng dụng, ưu tiên bắt lớp cha ổn định như AccessDeniedException khi xử lý từ chối phân quyền. Status HTTP còn phụ thuộc entry point, filter chain và exception handler mà ứng dụng cấu hình.

## 2. Các loại trạng thái và ngoại lệ

| Trạng thái | Ý nghĩa | Ngoại lệ có thể gặp | Cách hiểu ở tầng HTTP |
|---|---|---|---|
| Không có Authentication trong SecurityContext | Không có đối tượng xác thực để đánh giá principal hiện tại. | Với một số interceptor/cơ chế cũ có thể gặp AuthenticationCredentialsNotFoundException; với authorization manager hiện đại, biểu thức không được cấp quyền và có thể phát sinh AccessDeniedException hoặc AuthorizationDeniedException. | Nếu lỗi đi qua Spring Security filter chain, thường được chuyển tới AuthenticationEntryPoint. |
| AnonymousAuthenticationToken | Request được gắn principal anonymous, chưa phải người dùng đăng nhập. | Method security từ chối thường phát sinh AccessDeniedException hoặc lớp con. | ExceptionTranslationFilter nhận biết anonymous và chuyển tới AuthenticationEntryPoint. |
| Đã xác thực nhưng thiếu authority | Principal hợp lệ nhưng không có quyền cần thiết. | AccessDeniedException; trên các phiên bản có AuthorizationDeniedException, đây là lớp con mang thêm AuthorizationResult. | Thông thường là 403 Forbidden qua AccessDeniedHandler. |
| Đã xác thực và đủ quyền | Chính sách authorization cho phép lời gọi. | Không có ngoại lệ từ quyết định phân quyền đó. | Request tiếp tục và controller trả kết quả bình thường, ví dụ 200 OK. |
| Xác thực thất bại | Credentials/token không hợp lệ, hết hạn hoặc không đáp ứng cơ chế xác thực. | Các lớp AuthenticationException như BadCredentialsException hoặc InsufficientAuthenticationException. | AuthenticationEntryPoint xử lý challenge/401 hoặc redirect tùy cấu hình. |

### 2.1. AuthenticationException

AuthenticationException là lớp cha của các lỗi trong quá trình xác thực. Ví dụ:

- BadCredentialsException: credentials không hợp lệ.
- InsufficientAuthenticationException: mức xác thực hiện có không đủ cho yêu cầu.
- AuthenticationCredentialsNotFoundException: không tìm thấy Authentication cần thiết trong SecurityContext ở những cơ chế yêu cầu nó.

Các lỗi này mô tả việc xác thực hoặc thông tin xác thực không đáp ứng yêu cầu. Chúng không đồng nghĩa với việc một user đã đăng nhập nhưng thiếu authority nghiệp vụ.

### 2.2. AccessDeniedException và AuthorizationDeniedException

AccessDeniedException biểu thị caller không được phép thực hiện hành động. Method security có thể ném ngoại lệ này khi biểu thức @PreAuthorize trả false.

Ở các phiên bản Spring Security hiện đại có AuthorizationDeniedException, lớp này mở rộng AccessDeniedException và mang thêm kết quả authorization. Khi viết handler tương thích nhiều phiên bản, xử lý AccessDeniedException là lựa chọn phù hợp vì bao phủ lớp con.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('invoice:approve')")
public String approve(String invoiceId) {
    return "APPROVED-" + invoiceId;
}
~~~

Nếu Authentication có invoice:read nhưng không có invoice:approve, caller đã xác thực nhưng không đủ quyền. Đây là từ chối authorization, thường được biểu diễn bằng AccessDeniedException ở tầng method.

### 2.3. AuthenticationCredentialsNotFoundException không phải tên khác của 403

AuthenticationCredentialsNotFoundException thuộc nhánh AuthenticationException. Nó thường xuất hiện khi một thành phần bảo mật cần Authentication nhưng SecurityContext không có đối tượng đó, đặc biệt trong một số interceptor hoặc cấu hình cũ.

Với authorization manager và các biểu thức method security hiện đại, một Authentication vắng mặt cũng có thể khiến biểu thức không được cấp quyền và phát sinh AccessDeniedException hoặc AuthorizationDeniedException. Vì vậy, không nên khẳng định rằng mọi lời gọi @PreAuthorize khi SecurityContext trống đều phải ném đúng AuthenticationCredentialsNotFoundException. Hãy xác minh ngoại lệ của phiên bản và interceptor mà ứng dụng thực sự dùng.

Trong một request web, AnonymousAuthenticationFilter thường đặt AnonymousAuthenticationToken nếu chưa có Authentication. Do đó, tình huống “không đăng nhập” trong HTTP thường đi qua nhánh anonymous thay vì giữ SecurityContext trống đến controller.

## 3. Anonymous khác với SecurityContext không có Authentication

Spring Security có thể đặt Authentication đại diện cho anonymous caller để các thành phần sau vẫn có một trạng thái bảo mật nhất quán.

~~~mermaid
flowchart TD
    A["Request đi vào security filter chain"] --> B{"Đã có Authentication?"}
    B -- "Có" --> C["Dùng principal đã xác thực"]
    B -- "Không" --> D["AnonymousAuthenticationFilter"]
    D --> E["AnonymousAuthenticationToken"]
    C --> F["Method-security interceptor"]
    E --> F
    F --> G{"Authorization được cấp?"}
    G -- "Có" --> H["Thực thi nghiệp vụ"]
    G -- "Không" --> I{"Caller anonymous / chưa đủ trust?"}
    I -- "Có" --> J["AuthenticationEntryPoint"]
    I -- "Không" --> K["AccessDeniedHandler"]
~~~

Các điểm cần nhớ:

- AnonymousAuthenticationToken là một Authentication object, nhưng không có nghĩa người dùng đã đăng nhập.
- AuthenticationTrustResolver được Spring Security dùng để nhận diện trạng thái anonymous hoặc remember-me trong quá trình xử lý từ chối.
- Trong expression, isAnonymous() và isAuthenticated() giúp biểu đạt trạng thái principal; một anonymous token không được coi là người dùng đã xác thực theo nghĩa thông thường của các biểu thức này.
- SecurityContext rỗng khi gọi service trực tiếp ngoài request là tình huống khác với HTTP request đã đi qua AnonymousAuthenticationFilter.

Nếu ứng dụng gọi service từ scheduler, message listener hoặc test thuần không có request, đừng giả định luôn có anonymous token. Hãy thiết lập SecurityContext rõ ràng nếu tác vụ chạy dưới một service account, hoặc thiết kế method không yêu cầu user context khi đó là chủ đích.

## 4. Cấu hình method security và service mẫu

Bật method security trong Spring context:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Tạo service có một phương thức chỉ cho phép authority cụ thể:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    @PreAuthorize("hasAuthority('invoice:approve')")
    public String approve(String invoiceId) {
        return "APPROVED-" + invoiceId;
    }

    @PreAuthorize("hasAuthority('invoice:read')")
    public String read(String invoiceId) {
        return "INVOICE-" + invoiceId;
    }
}
~~~

Trong ứng dụng thật, có thể thêm điều kiện isAuthenticated() để biểu đạt ý định rõ hơn:

~~~java
@PreAuthorize(
    "isAuthenticated() and hasAuthority('invoice:approve')"
)
public String approve(String invoiceId) {
    // ...
}
~~~

Điều kiện hasAuthority vốn đã từ chối anonymous nếu họ không có authority đó. Thêm isAuthenticated() giúp người đọc policy hiểu rõ yêu cầu về trạng thái đăng nhập, nhưng không thay thế kiểm tra authority. Không cấp invoice:approve cho anonymous principal.

**Điều kiện để annotation chạy:** InvoiceService phải là Spring bean và lời gọi phải đi qua method-security proxy. Không dùng new InvoiceService() trong test để xác minh @PreAuthorize; hãy inject bean từ Spring application context.

## 5. Khi nào lỗi method security được chuyển thành 401 hoặc 403?

Một ngoại lệ Java từ service không tự nó chứa HTTP status. Việc ánh xạ xảy ra khi ngoại lệ đi qua tầng xử lý web thích hợp.

### 5.1. Servlet: ExceptionTranslationFilter

Trong Spring Security Servlet, ExceptionTranslationFilter chuyển AuthenticationException và AccessDeniedException thành hành vi HTTP:

- AuthenticationException được chuyển tới AuthenticationEntryPoint.
- AccessDeniedException từ caller anonymous hoặc mức trust chưa đủ thường được chuyển tới AuthenticationEntryPoint để bắt đầu xác thực.
- AccessDeniedException từ principal đã xác thực đầy đủ thường được chuyển tới AccessDeniedHandler.

~~~mermaid
flowchart TD
    A["Ngoại lệ từ controller/service/filter"] --> B{"AuthenticationException?"}
    B -- "Có" --> C["AuthenticationEntryPoint"]
    B -- "Không" --> D{"AccessDeniedException?"}
    D -- "Không" --> E["Exception handler khác"]
    D -- "Có" --> F{"Anonymous / trust chưa đủ?"}
    F -- "Có" --> C
    F -- "Không" --> G["AccessDeniedHandler"]
    C --> H["401 hoặc redirect/challenge theo cấu hình"]
    G --> I["403 Forbidden"]
~~~

Bảng thường gặp với HTTP Basic:

| Caller | Quyết định method | Phản hồi thường thấy |
|---|---|---|
| Chưa đăng nhập / anonymous | Method yêu cầu invoice:approve | 401 Unauthorized theo AuthenticationEntryPoint; challenge hoặc redirect tùy cấu hình |
| Đã đăng nhập, chỉ có invoice:read | Method yêu cầu invoice:approve | 403 Forbidden |
| Đã đăng nhập, có invoice:approve | Được phép | 200 OK nếu controller trả thành công |

**401 và 403 không được quyết định chỉ bởi annotation.** Entry point, loại authentication, trust level, URL authorization và handler của ứng dụng đều ảnh hưởng response. Với form login, entry point có thể redirect tới trang đăng nhập thay vì trả JSON 401. Với API bearer token, challenge thường là 401 và có thể kèm WWW-Authenticate.

### 5.2. Direct method call không tự có HTTP status

Trong test gọi InvoiceService.approve() trực tiếp, kỳ vọng là kết quả hoặc exception Java. Không assert 401/403 vì không có servlet response. Test service nên kiểm tra AccessDeniedException hoặc lớp con tương ứng; test MockMvc mới kiểm tra status HTTP.

Tương tự, nếu scheduler gọi service mà không có request web, ExceptionTranslationFilter không tham gia. Tác vụ cần tự xử lý lỗi ở ranh giới scheduler/job hoặc thiết lập service identity theo thiết kế.

## 6. Cấu hình AuthenticationEntryPoint và AccessDeniedHandler

Với API, nên chuẩn hóa phản hồi khi chưa xác thực và khi đã xác thực nhưng thiếu quyền. Ví dụ Servlet dùng HTTP Basic và trả status nhất quán:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint((request, response, exception) -> {
                    response.setStatus(HttpStatus.UNAUTHORIZED.value());
                    response.setContentType("application/json");
                    response.setHeader("Cache-Control", "no-store");
                })
                .accessDeniedHandler((request, response, exception) -> {
                    response.setStatus(HttpStatus.FORBIDDEN.value());
                    response.setContentType("application/json");
                }))
            .build();
    }
}
~~~

Cấu hình anyRequest().permitAll() ở đây chỉ nhằm để request tới controller và cô lập method security trong bài thực hành. Không dùng nó như chính sách mặc định của ứng dụng thật. Trong production, hãy cấu hình URL authorization đúng yêu cầu, chẳng hạn authenticated() cho các API cần đăng nhập, và định nghĩa public route có chủ đích.

Handler trả thông điệp tổng quát, không đưa stack trace, SQL, tên lớp nội bộ, policy expression hoặc chi tiết dữ liệu nhạy cảm ra response. Có thể log exception ở server với request ID/correlation ID và thông tin đủ để điều tra, nhưng không ghi access token, password hoặc credentials.

Nếu ứng dụng cần response JSON theo chuẩn riêng, có thể dùng ObjectMapper hoặc ProblemDetail để serialize một error body ổn định. Giữ hai nhánh 401 và 403 riêng biệt để client biết cần xác thực hay cần quyền khác.

### Không bắt ngoại lệ quá rộng

Không viết một handler bắt RuntimeException rồi biến mọi lỗi thành 403. Cách đó có thể che lỗi lập trình, lỗi database, timeout hoặc lỗi nghiệp vụ thành “không đủ quyền”. Hãy xử lý AuthenticationException và AccessDeniedException ở security boundary; xử lý lỗi nghiệp vụ như tài nguyên không tồn tại bằng exception/handler riêng.

## 7. Kiểm thử trực tiếp method security với @WithMockUser

Test service kiểm tra chính sách mà không phụ thuộc filter chain. Dùng @SpringBootTest để nạp bean thật:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class InvoiceMethodSecurityTest {

    @Autowired
    InvoiceService invoices;

    @Test
    @WithMockUser(username = "lan", authorities = "invoice:approve")
    void callerWithApproveAuthorityCanApprove() {
        assertEquals("APPROVED-INV-42", invoices.approve("INV-42"));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "invoice:read")
    void authenticatedCallerWithoutApproveAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> invoices.approve("INV-42"));
    }

    @Test
    @WithAnonymousUser
    void anonymousCallerIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> invoices.approve("INV-42"));
    }

    @Test
    void noAuthenticationInSecurityContextIsDenied() {
        org.springframework.security.core.context.SecurityContextHolder
            .clearContext();

        assertThrows(AccessDeniedException.class,
            () -> invoices.approve("INV-42"));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "invoice:approve")
    void callerWithApproveAuthorityCanRead() {
        assertEquals("INVOICE-INV-42", invoices.read("INV-42"));
    }
}
~~~

Các ca chính cần có:

- Có đúng authority: phương thức được thực thi.
- Đã xác thực nhưng authority sai: method bị từ chối.
- Anonymous: method bị từ chối.
- Không có Authentication trong SecurityContext: method bị từ chối theo policy hiện đại.

Tùy interceptor và phiên bản, khi không có Authentication có thể gặp AuthenticationCredentialsNotFoundException thay vì AccessDeniedException. Nếu codebase có thành phần legacy hoặc custom interceptor, hãy assert loại exception thực tế mà cấu hình sử dụng; không giả định mọi stack đều ném cùng một class.

@WithMockUser mặc định tạo user có role USER nếu không chỉ định role/authority. Vì vậy, nếu method yêu cầu invoice:approve thì cần khai báo authorities rõ ràng. @WithAnonymousUser tạo anonymous authentication để kiểm tra nhánh anonymous một cách tường minh.

### Kiểm tra AuthenticationCredentialsNotFoundException

Nếu một thành phần bảo mật cụ thể của ứng dụng yêu cầu Authentication phải tồn tại và ném AuthenticationCredentialsNotFoundException khi SecurityContext trống, hãy viết test riêng cho chính thành phần đó. Đây là hợp đồng của interceptor/cấu hình cụ thể, không phải assertion phổ quát cho mọi @PreAuthorize hiện đại.

## 8. Kiểm thử HTTP Servlet bằng MockMvc

Để kiểm tra ánh xạ exception thành HTTP, controller gọi service thật:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/invoices")
public class InvoiceController {

    private final InvoiceService invoices;

    public InvoiceController(InvoiceService invoices) {
        this.invoices = invoices;
    }

    @GetMapping("/{id}/approve")
    public String approve(@PathVariable String id) {
        return invoices.approve(id);
    }
}
~~~

Test MockMvc với Spring Boot 3.x:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class InvoiceHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void unauthenticatedRequestGets401() throws Exception {
        mvc.perform(get("/invoices/INV-42/approve"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedCallerWithoutAuthorityGets403() throws Exception {
        mvc.perform(get("/invoices/INV-42/approve")
                .with(user("lan").authorities(
                    new SimpleGrantedAuthority("invoice:read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void callerWithAuthorityGets200() throws Exception {
        mvc.perform(get("/invoices/INV-42/approve")
                .with(user("lan").authorities(
                    new SimpleGrantedAuthority("invoice:approve"))))
            .andExpect(status().isOk())
            .andExpect(content().string("APPROVED-INV-42"));
    }
}
~~~

Các kỳ vọng trên dựa vào cấu hình ApiSecurityConfig với HTTP Basic entry point, access denied handler, controller và service thật. Request không gắn user sẽ đi qua anonymous authentication rồi bị method security từ chối; ExceptionTranslationFilter chuyển nhánh anonymous tới entry point. Request gắn user nhưng thiếu authority bị chuyển tới AccessDeniedHandler.

Nếu ứng dụng dùng form login, test anonymous có thể nhận redirect thay vì 401. Nếu request bị URL authorization chặn trước controller, test 403 có thể chưa đi tới method security. Trong bài thực hành, cấu hình permitAll() có chủ đích giúp cô lập lớp method; ứng dụng thật phải có URL policy phù hợp.

### Dùng @WithMockUser trên test MockMvc

Cũng có thể đặt @WithMockUser trên test method/class để thiết lập SecurityContext cho request. Tuy nhiên, khi cần kiểm thử nhiều tập quyền trong cùng class, request post-processor .with(user(...)) làm principal của từng request rõ ràng hơn. Không dùng đồng thời hai cách một cách tùy tiện rồi không biết authentication nào đang được request sử dụng.

### JWT, OAuth2 và OIDC giả lập

Với resource server, có thể dùng jwt() của Spring Security Test để tạo JwtAuthenticationToken giả lập có authority phù hợp:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mvc.perform(get("/invoices/INV-42/approve")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("invoice:approve"))))
    .andExpect(status().isOk());
~~~

OAuth2 Login/OIDC Login có helper riêng như oauth2Login() và oidcLogin(). Các helper này kiểm tra authorization với Authentication đã dựng trong test; chúng không xác minh chữ ký JWT, issuer, audience, token expiration hoặc trao đổi authorization code với identity provider thật. Muốn kiểm thử xác thực token, cần integration test riêng cho decoder/converter và cấu hình resource server.

## 9. WebFlux: AuthenticationEntryPoint và ServerAccessDeniedHandler

Reactive web dùng các kiểu handler riêng:

- ServerAuthenticationEntryPoint xử lý yêu cầu xác thực/chưa đủ mức xác thực.
- ServerAccessDeniedHandler xử lý caller đã xác thực nhưng không có quyền.

Cấu hình WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint((exchange, exception) -> {
                    exchange.getResponse().setStatusCode(
                        HttpStatus.UNAUTHORIZED
                    );
                    return exchange.getResponse().setComplete();
                })
                .accessDeniedHandler((exchange, exception) -> {
                    exchange.getResponse().setStatusCode(
                        HttpStatus.FORBIDDEN
                    );
                    return exchange.getResponse().setComplete();
                }))
            .build();
    }
}
~~~

permitAll() ở đây chỉ phục vụ bài thực hành để request tới controller và method security quyết định. HTTP Basic được bật để cấu hình có entry point xác thực; trong ứng dụng thực tế, thay bằng policy và authentication mechanism phù hợp.

Service Reactive:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveInvoiceService {

    @PreAuthorize("hasAuthority('invoice:approve')")
    public Mono<String> approve(String id) {
        return Mono.just("APPROVED-" + id);
    }
}
~~~

Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/reactive/invoices")
public class ReactiveInvoiceController {

    private final ReactiveInvoiceService invoices;

    public ReactiveInvoiceController(ReactiveInvoiceService invoices) {
        this.invoices = invoices;
    }

    @GetMapping("/{id}/approve")
    public Mono<String> approve(@PathVariable String id) {
        return invoices.approve(id);
    }
}
~~~

Test WebTestClient:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class ReactiveInvoiceSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void anonymousCallerGets401() {
        client.get().uri("/reactive/invoices/INV-42/approve")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedCallerWithoutAuthorityGets403() {
        client.mutateWith(mockUser("lan").authorities(
                new SimpleGrantedAuthority("invoice:read")))
            .get().uri("/reactive/invoices/INV-42/approve")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authorizedCallerGets200() {
        client.mutateWith(mockUser("lan").authorities(
                new SimpleGrantedAuthority("invoice:approve")))
            .get().uri("/reactive/invoices/INV-42/approve")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("APPROVED-INV-42");
    }
}
~~~

Các test giả định ứng dụng thực sự chạy WebFlux, nạp ReactiveSecurityConfig, ReactiveInvoiceController và ReactiveInvoiceService. Reactive SecurityContext được truyền trong Reactor Context; không đọc SecurityContextHolder như thể đây là luồng Servlet ThreadLocal. WebTestClient gửi request và subscribe Mono nên có thể quan sát quyết định method security.

Khi test service trực tiếp trả Mono, cần subscribe bằng StepVerifier hoặc subscriber tương ứng với Reactor Context. Chỉ gọi approve("INV-42") để nhận publisher mà không subscribe chưa chứng minh method authorization đã chạy.

### JWT/OAuth2/OIDC trên WebFlux

Spring Security Test có helper Reactive tương ứng như mockJwt(), mockOAuth2Login() và mockOidcLogin(). Chúng dựng authentication giả lập để kiểm tra authorization. Hãy cấp authority đúng mà method yêu cầu; ví dụ invoice:approve không tự tương đương SCOPE_invoice.approve. Nếu muốn kiểm thử converter scope, dùng authority được converter tạo hoặc test converter riêng.

## 10. Tách lỗi phân quyền khỏi lỗi nghiệp vụ

Không phải mọi exception từ service đều là lỗi security:

| Loại lỗi | Ví dụ | Cách xử lý phù hợp |
|---|---|---|
| Chưa xác thực | Không có credentials hoặc token không hợp lệ | AuthenticationEntryPoint / cơ chế xác thực; thường 401 hoặc redirect. |
| Không đủ quyền | Có principal nhưng thiếu invoice:approve | AccessDeniedHandler; thường 403. |
| Không tìm thấy tài nguyên | Invoice ID không tồn tại | Exception nghiệp vụ/404 theo API contract. |
| Dữ liệu không hợp lệ | Trạng thái invoice không cho phép duyệt | Validation hoặc business exception; có thể 400/409 tùy hợp đồng. |
| Lỗi hạ tầng | Database timeout, service dependency lỗi | Error handling vận hành; không chuyển thành 403. |

Nếu một người dùng không được phép biết tài nguyên có tồn tại hay không, API có thể chủ động trả cùng một phản hồi cho “không tồn tại” và “không được phép” để tránh tiết lộ thông tin. Đây là quyết định thiết kế chống dò quét tài nguyên, cần áp dụng nhất quán; không phải quy tắc bắt buộc rằng mọi AccessDeniedException phải biến thành 404.

Đối với exception do method security ném ra sau khi controller đã bắt đầu xử lý, hãy bảo đảm nó được chuyển tới security exception translation hoặc handler được thiết kế cho đúng loại lỗi. Tránh một @ExceptionHandler(RuntimeException.class) trả 200/500 tùy tiện và vô tình nuốt AccessDeniedException.

## 11. Những lỗi thường gặp khi kiểm thử

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test service mong 401 nhưng nhận exception. | Direct Java call không có HTTP response. | Assert exception ở service test; assert status ở MockMvc/WebTestClient. |
| Không có Authentication nhưng không ném AuthenticationCredentialsNotFoundException. | AuthorizationManager hiện đại có thể biểu diễn kết quả bằng AccessDeniedException/AuthorizationDeniedException. | Assert theo hợp đồng của interceptor/version; không giả định một exception cho mọi cấu hình. |
| Anonymous và user thiếu authority đều trả cùng một status. | Test không phân biệt principal anonymous với authenticated principal. | Dùng @WithAnonymousUser hoặc request không credentials cho nhánh 401; dùng user(...) với authority sai cho nhánh 403. |
| MockMvc anonymous trả 302. | Form login entry point redirect tới trang login. | Kiểm tra HTTP entry point; chỉ assert 401 nếu API được cấu hình trả 401. |
| MockMvc trả 403 dù service policy đúng. | URL authorization hoặc CSRF chặn request trước service. | Kiểm tra filter chain; kết hợp service test và HTTP test. |
| User thiếu quyền vẫn gọi được service. | Method security chưa bật, bean không qua proxy hoặc test tự tạo service. | Bật @EnableMethodSecurity và inject bean thật. |
| Test có @WithMockUser nhưng request dùng authentication khác. | Request post-processor hoặc test setup ghi đè SecurityContext. | Chọn một cách thiết lập principal rõ ràng cho mỗi test. |
| WebFlux mất Authentication trong policy. | Lấy SecurityContext từ ThreadLocal hoặc test không thiết lập Reactor Context. | Dùng reactive security configurer và ReactiveSecurityContextHolder khi cần. |
| Handler trả chi tiết exception cho client. | Dùng exception.getMessage() hoặc stack trace làm response. | Trả mã lỗi chung, log chi tiết ở server có kiểm soát. |
| Tất cả lỗi RuntimeException thành 403. | Handler quá rộng che lỗi nghiệp vụ/hạ tầng. | Chỉ xử lý AuthenticationException và AccessDeniedException ở security boundary. |
| JWT mock được coi là xác thực token thật. | Test helper chỉ tạo Authentication giả lập. | Tách authorization test khỏi token decoder/issuer/signature integration test. |

## 12. Bài thực hành và tiêu chí hoàn thành

1. Tạo InvoiceService với @PreAuthorize("hasAuthority('invoice:approve')"), bật @EnableMethodSecurity và inject bean thật vào test.
2. Dùng @WithMockUser(authorities = "invoice:approve") để chứng minh lời gọi được phép; dùng invoice:read để chứng minh caller đã xác thực nhưng thiếu quyền bị từ chối.
3. Dùng @WithAnonymousUser để kiểm thử anonymous; tạo một test không thiết lập Authentication để quan sát hành vi khi SecurityContext trống trong phiên bản đang dùng.
4. Ghi nhận ngoại lệ thực tế cho hai trường hợp trên. Giải thích khi nào AuthenticationCredentialsNotFoundException có thể xuất hiện và vì sao AuthorizationDeniedException/AccessDeniedException có thể là kết quả của authorization manager hiện đại.
5. Cấu hình AuthenticationEntryPoint và AccessDeniedHandler; dùng MockMvc kiểm tra 401, 403 và 200 với HTTP Basic.
6. Thay entry point bằng form login hoặc cấu hình khác, quan sát vì sao anonymous có thể nhận redirect thay vì 401.
7. Trên WebFlux, bật @EnableReactiveMethodSecurity, cấu hình ServerAuthenticationEntryPoint và ServerAccessDeniedHandler, dùng WebTestClient để kiểm tra anonymous, thiếu authority và đủ authority.
8. Thử JWT/OAuth2/OIDC helper để tạo Authentication giả lập. Phân biệt kết quả authorization với việc token thật được xác minh.
9. Tạo một lỗi nghiệp vụ như InvoiceNotFoundException và bảo đảm nó không bị handler security biến thành 403.
10. Rà soát response error để bảo đảm không lộ stack trace, thông tin credentials hoặc chi tiết policy nội bộ.

**Tiêu chí hoàn thành:** Người học phân biệt được trạng thái không có Authentication, anonymous và authenticated nhưng thiếu quyền; hiểu ngoại lệ Java ở tầng method và phản hồi HTTP ở tầng web; kiểm thử được cả ca được phép lẫn bị từ chối bằng bean Spring thật, MockMvc và WebTestClient. Cấu hình handler phải trả phản hồi phù hợp mà không làm mất phân biệt giữa lỗi xác thực, lỗi phân quyền và lỗi nghiệp vụ.

## Tài liệu tham khảo

- [Spring Security 6.5 — Exception Translation](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — Reactive Exception Handling](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)

