# Thay đổi danh tính ở hệ thống ngoài, phiên hiện tại và xử lý mất xác thực

## 1. Vấn đề trong mô hình tiền xác thực

Với **pre-authentication (tiền xác thực)**, một hệ thống bên ngoài đã xác minh người dùng trước khi request tới ứng dụng Java: cổng SSO, reverse proxy, application server, hạ tầng xác thực bằng chứng chỉ X.509, v.v. Spring Security nhận một danh tính đã được bên ngoài xác nhận, sau đó dựng `Authentication` và thường bổ sung `GrantedAuthority` từ dữ liệu người dùng của ứng dụng.

Câu hỏi của bài là: **nếu danh tính phía ngoài đổi từ Alice sang Bob, hoặc hệ thống ngoài không còn xác thực được người dùng, một `HttpSession` đang lưu Alice phải được xử lý thế nào?** Đây là bài toán đồng bộ **nguồn danh tính bên ngoài**, **`SecurityContext` trong request** và **trạng thái lưu qua phiên**.

Sau bài học, bạn cần phân biệt được:

1. Danh tính bên ngoài tại **request hiện tại** (đã được hệ thống tin cậy xác minh).
2. `Authentication` đang có trong `SecurityContextHolder`, có thể vừa được khôi phục từ `SecurityContextRepository`.
3. Dữ liệu và vòng đời của `HttpSession`: session ID, `SPRING_SECURITY_CONTEXT`, dữ liệu nghiệp vụ, CSRF token và các thuộc tính khác.
4. Trường hợp **principal đổi**, **principal mất**, **vai trò/quyền đổi nhưng principal giữ nguyên**, **IdP/gateway bị lỗi**, và **session hết hạn**; chúng không phải một sự kiện duy nhất.
5. Cách kiểm thử rằng danh tính cũ không tiếp tục được cấp quyền cho request mới.

**Phạm vi chính:** Spring Security **Servlet** với `AbstractPreAuthenticatedProcessingFilter` / `RequestHeaderAuthenticationFilter` và phiên HTTP. Phần reactive/WebFlux có `SecurityWebFilterChain`, `WebSession` và `ReactiveSecurityContextHolder` khác API; không áp dụng nguyên mã Servlet cho WebFlux.

## 2. Luồng thông thường và nơi xuất hiện danh tính cũ

Một mô hình điển hình:

```text
Browser có cookie JSESSIONID
    |
    v
Gateway / IdP đã kiểm chứng credential
    |  loại bỏ header danh tính do client tự gửi
    |  gắn danh tính tin cậy theo request, ví dụ SM_USER=alice
    v
Spring Security FilterChain
    |  khôi phục SecurityContext từ session (nếu có)
    |  pre-auth filter đọc danh tính bên ngoài
    |  AuthenticationManager / PreAuthenticatedAuthenticationProvider
    |  UserDetailsService tải authorities theo chính sách
    v
Controller và AuthorizationFilter
```

`RequestHeaderAuthenticationFilter` chỉ **đọc giá trị header**; nó **không xác minh chữ ký, mật khẩu hay phiên SSO**. Vì vậy, chỉ được dùng khi hạ tầng bảo đảm ứng dụng không thể bị truy cập trực tiếp bằng header giả mạo. Nếu client có thể gửi `SM_USER: admin` đến ứng dụng thì pre-authentication bằng header không an toàn.

Khi ứng dụng dùng session, `SecurityContextRepository` có thể lưu `Authentication` Alice sau request đầu. Ở request tiếp theo, Spring Security khôi phục Alice trước khi pre-auth filter quyết định có cần đọc lại định danh hay không.

### Ba trạng thái cần quan sát

| Nguồn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `P_ext` | `alice` / `bob` / không có | Principal đã được bên ngoài xác nhận cho request hiện tại |
| `P_ctx` | `Authentication(name=alice)` / rỗng | Danh tính mà Spring Security chuẩn bị dùng để cho phép truy cập |
| `S` | `JSESSIONID=S1`, chứa `SecurityContext` Alice | Trạng thái lưu qua request; có thể đã lỗi thời |

Quy tắc an toàn: request phải được xử lý dựa trên **định danh còn hợp lệ theo chính sách hiện tại**. Việc session vẫn tồn tại **không chứng minh** IdP hoặc gateway vẫn xác thực được người dùng.

## 3. Hành vi mặc định của pre-auth filter

`AbstractPreAuthenticatedProcessingFilter` có một số thuộc tính quan trọng:

- Khi `SecurityContext` **chưa có `Authentication`**, filter lấy principal/credentials từ request và chuyển cho `AuthenticationManager`. Nhà cung cấp `PreAuthenticatedAuthenticationProvider` thường dùng `AuthenticationUserDetailsService` để tải người dùng và quyền; nó tin rằng bước xác thực gốc đã hoàn tất ở bên ngoài.
- Nếu `SecurityContext` **đã có `Authentication`**, filter **mặc định không xác thực lại**. Do đó, đổi principal bên ngoài có thể bị bỏ qua khi dùng lại session.
- `setCheckForPrincipalChanges(true)` yêu cầu filter so sánh principal trên request mới với danh tính hiện tại; khi phát hiện đổi, filter sẽ thực hiện lại pre-authentication.
- `setInvalidateSessionOnPrincipalChange(true)` quy định hủy session hiện tại khi phát hiện đổi principal trước khi xác thực danh tính mới; thuộc tính này **mặc định là true khi tính năng kiểm tra thay đổi được dùng**. Nêu tường minh giúp policy dễ kiểm tra.
- `setContinueFilterChainOnUnsuccessfulAuthentication(true)` là mặc định: khi `AuthenticationManager` thất bại, chuỗi có thể tiếp tục để cơ chế khác xử lý. Điều này **không có nghĩa request được phép truy cập**; quyết định cuối vẫn dựa vào authorization. Nếu hệ thống chỉ cho phép pre-authentication, cần cấu hình nhánh lỗi và cơ chế trả HTTP status rõ ràng.
- Với `RequestHeaderAuthenticationFilter`, `setExceptionIfHeaderMissing(true)` là mặc định và việc **thiếu header** có thể gây `PreAuthenticatedCredentialsNotFoundException`. Đừng coi ngoại lệ đó là lệnh tự động logout mọi session liên quan. Nếu cho phép header vắng bằng `setExceptionIfHeaderMissing(false)`, cần có policy riêng để chặn dữ liệu xác thực cũ.

**Điểm giới hạn:** `checkForPrincipalChanges` chủ yếu xác định thay đổi *principal*, **không tự phát hiện** việc Alice đã bị khóa tài khoản, quyền Alice bị thu hồi, hoặc phiên SSO của Alice ở IdP đã bị hủy nếu request vẫn có cùng chuỗi tên Alice.

### Mặc định nguy hiểm: session cũ che principal mới

```text
R1: Gateway -> SM_USER=alice, client có S1 hoặc chưa có session
    Spring Security tạo Authentication(alice), lưu trong S1.

R2: Gateway -> SM_USER=bob, client vẫn gửi cookie S1
    checkForPrincipalChanges=false:
       context đã có Alice -> filter có thể bỏ qua Bob -> request nhìn thấy Alice
    checkForPrincipalChanges=true, invalidateSessionOnPrincipalChange=true:
       phát hiện thay đổi -> hủy S1 -> xác thực Bob -> lưu context mới nếu có

R3: Gateway không còn xác minh được ai; client vẫn gửi S1 của Alice
    KHÔNG được giả định session Alice đồng nghĩa với danh tính đang hợp lệ.
    Thiếu external identity cần được chặn và xử lý độc lập.
```

## 4. Phân tích các tình huống thay đổi và mất xác thực

| Tình huống | Điều thường thấy | Kết quả cần thiết |
| --- | --- | --- |
| Alice → Bob, cùng cookie | Trong session còn Alice | Xóa context cũ, hủy hoặc tách session của Alice, xác thực Bob và nạp quyền Bob |
| Alice → không có principal tin cậy | Browser vẫn giữ JSESSIONID | Chặn request; xóa/thu hồi context local theo policy, không dùng Alice cũ |
| Alice vẫn là Alice nhưng role bị thu hồi | Principal string không đổi | Tải/cập nhật quyền theo TTL, version hoặc kiểm tra chính sách; không chỉ dựa vào `principalChanged` |
| Alice bị khóa tại IdP | Gateway phải ngừng xác nhận Alice | Chặn khi tín hiệu không còn hợp lệ; nếu yêu cầu thu hồi tức thời, có thêm cơ chế back-channel/session revocation |
| Gateway/IdP không phản hồi | Không có bằng chứng xác thực mới | Fail closed; 401/503 tùy giao thức và loại lỗi, không dùng cache danh tính không còn đáng tin |
| Session local hết hạn, IdP vẫn xác thực Alice | Không còn `SecurityContext` local | Xác thực pre-auth Alice từ request mới; có thể tạo session local mới |
| Người dùng logout ở ứng dụng | Session và context local bị xóa | Request tiếp theo chỉ được đăng nhập lại nếu hệ thống ngoài vẫn xác thực; logout local không đồng nghĩa logout SSO |
| Người dùng logout khỏi IdP | Phiên IdP bị thu hồi | Gateway phải dừng phát danh tính hoặc gửi sự kiện thu hồi; hủy local session theo mức bảo đảm mong muốn |

Một thay đổi tên hiển thị như `Alice Nguyen` → `Alice N.` không nhất thiết là đổi người dùng. Nên nhận dạng bằng **ID ổn định có namespace** (ví dụ issuer + subject + tenant) thay vì tên hiển thị hay email có thể thay đổi/tái sử dụng. `principalChanged(request, currentAuthentication)` có thể được override khi cấu trúc danh tính của hệ thống yêu cầu so sánh khác với hành vi mặc định; phải kiểm thử đầy đủ nhánh so sánh đó.

### Phân biệt 401, 403 và 503

- **401 Unauthorized:** request không có xác thực hợp lệ, cần một bước xác thực lại. Phù hợp API khi thiếu tín hiệu external identity mà policy yêu cầu.
- **403 Forbidden:** đã được nhận diện nhưng không đủ quyền; hoặc khi bạn chủ ý dùng `Http403ForbiddenEntryPoint` trong mô hình pre-auth (entry point này trả 403). Không suy diễn mọi pre-auth failure đều tự động là 403.
- **503 Service Unavailable:** hệ thống ngoài đang lỗi và không thể đưa ra quyết định xác thực mới; chỉ trả khi ứng dụng biết chắc đó là sự cố phụ thuộc. Vẫn phải từ chối truy cập.
- **302 redirect:** có thể thích hợp cho giao diện trình duyệt qua gateway SSO, theo quy trình đăng nhập; API thường cần mã lỗi rõ ràng.

**Không trả 200 cùng danh tính cũ** chỉ vì hệ thống ngoài đang lỗi.

## 5. Cấu hình ví dụ cho Servlet: đồng bộ principal và từ chối khi mất danh tính

Ví dụ dưới đây sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x**. Đây là ứng dụng minh họa hoàn chỉnh khi đặt trong một dự án Boot Servlet có các dependency được liệt kê; dùng `MockMvc` để thử, **không đưa trực tiếp cổng HTTP minh họa ra Internet**. Chỉ sử dụng header `SM_USER` khi reverse proxy tin cậy đã thực sự xác thực người dùng, xóa header giả mạo từ client và ngăn đường truy cập bypass proxy.

Trong `build.gradle` của dự án Spring Boot đã cấu hình plugin và BOM phiên bản tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Đặt file `src/main/java/example/PreAuthDemoApplication.java`:

```java
package example;

import java.io.IOException;
import java.security.Principal;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class PreAuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PreAuthDemoApplication.class, args);
    }

    @Bean
    UserDetailsService demoUsers() {
        // Dữ liệu minh họa: pre-auth KHÔNG xác minh password này.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}unused")
                .roles("USER").build(),
            User.withUsername("bob")
                .password("{noop}unused")
                .roles("USER").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        var repository = new HttpSessionSecurityContextRepository();

        var lookup =
            new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>(
                users);
        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(lookup);

        // Không khai báo filter này thành @Bean riêng:
        // tránh để Spring Boot đăng ký nó hai lần bên ngoài security chain.
        var preauth = new RequestHeaderAuthenticationFilter();
        preauth.setPrincipalRequestHeader("SM_USER");
        preauth.setAuthenticationManager(new ProviderManager(provider));
        preauth.setSecurityContextRepository(repository);
        preauth.setCheckForPrincipalChanges(true);
        preauth.setInvalidateSessionOnPrincipalChange(true);
        preauth.setExceptionIfHeaderMissing(true);

        return http
            .securityContext(context ->
                context.securityContextRepository(repository))
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            // Chặn mất tín hiệu ngoài ngay cả khi session còn Alice.
            .addFilterBefore(
                new RequireExternalIdentityFilter(repository),
                AbstractPreAuthenticatedProcessingFilter.class)
            .addFilterAt(
                preauth, AbstractPreAuthenticatedProcessingFilter.class)
            .build();
    }

    static final class RequireExternalIdentityFilter
            extends OncePerRequestFilter {

        private final HttpSessionSecurityContextRepository repository;

        RequireExternalIdentityFilter(
                HttpSessionSecurityContextRepository repository) {
            this.repository = repository;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            String externallyVerified = request.getHeader("SM_USER");
            if (externallyVerified == null
                    || externallyVerified.isBlank()) {

                var logout = new SecurityContextLogoutHandler();
                logout.setSecurityContextRepository(repository);
                logout.logout(request, response,
                    SecurityContextHolder.getContext().getAuthentication());

                response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }
            chain.doFilter(request, response);
        }
    }
}

@RestController
class IdentityProbeController {

    @GetMapping("/whoami")
    String whoami(Principal principal) {
        return principal.getName();
    }
}
```

**Ý nghĩa chính của đoạn mã:**

1. `RequestHeaderAuthenticationFilter` đọc header do **một gateway đáng tin** đặt vào request; nó không tự xác minh nguồn gốc header. `UserDetailsService` minh họa chỉ dùng để tìm user và role, không kiểm tra mật khẩu trong pre-auth.
2. `setCheckForPrincipalChanges(true)` so sánh principal mỗi request. `setInvalidateSessionOnPrincipalChange(true)` tránh mang session Alice sang Bob. Nếu chọn `false` thì phải giải quyết rõ khả năng các thuộc tính session của Alice còn nằm trong phiên của Bob.
3. Dùng **cùng** `HttpSessionSecurityContextRepository` cho security context của chain và pre-auth filter, để lưu/đọc nhất quán. Với Spring Security 6, không giả định một filter tự đặt `SecurityContextHolder` sẽ mặc nhiên được lưu giữa các request; filter custom cần lưu bằng repository thích hợp.
4. `RequireExternalIdentityFilter` chạy trước pre-auth filter. Khi header thiếu/rỗng, nó dọn security context, vô hiệu session local và kết thúc request với 401. Do đó session trước đó **không** được sử dụng làm bằng chứng xác thực thay thế.
5. `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` định nghĩa phản hồi khi một request không được xác thực tới tài nguyên bảo vệ. Các trường hợp exception phát sinh **ở chính authentication filter** cần được kiểm tra riêng theo cấu hình failure handler; không giả định mọi exception ở filter đều tự động được chuyển thành 401 bởi entry point.
6. `RequireExternalIdentityFilter` là **biện pháp minh họa cho một tập route chỉ dành cho pre-auth**. Ứng dụng có health endpoint, callback hoặc nhiều `SecurityFilterChain` cần giới hạn phạm vi và thứ tự filter tương ứng, tránh chặn các endpoint công khai ngoài ý muốn.

**Giới hạn bảo mật của mã minh họa:** check header không chứng minh header thực sự đáng tin. Việc cô lập network, xác thực proxy-to-app, xóa header client tự gửi, xác định principal ổn định và chính sách không cache header xác thực đã hết hạn phải được thực hiện ở kiến trúc triển khai. Không dùng mẫu này để mở cổng backend cho client tùy ý gửi `SM_USER`.

## 6. Kiểm thử chuyển danh tính, giữ session và mất tín hiệu ngoài

Thêm `src/test/java/example/PreAuthFlowTests.java`; `@AutoConfigureMockMvc` kích hoạt security filter chain trong môi trường test. Test truyền header trực tiếp để mô phỏng gateway **sau khi đã xác thực**, không phải để chứng minh gateway chống giả mạo.

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PreAuthFlowTests {

    @Autowired
    MockMvc mvc;

    @Test
    void principalChangeInvalidatesOldSessionAndUsesBob() throws Exception {
        MvcResult aliceResult = mvc.perform(
                get("/whoami").header("SM_USER", "alice"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"))
            .andReturn();

        MockHttpSession oldSession =
            (MockHttpSession) aliceResult.getRequest().getSession(false);
        assertNotNull(oldSession);

        MvcResult bobResult = mvc.perform(
                get("/whoami")
                    .session(oldSession)
                    .header("SM_USER", "bob"))
            .andExpect(status().isOk())
            .andExpect(content().string("bob"))
            .andReturn();

        assertTrue(oldSession.isInvalid());

        MockHttpSession bobSession =
            (MockHttpSession) bobResult.getRequest().getSession(false);
        assertNotNull(bobSession);
        assertNotSame(oldSession, bobSession);
    }

    @Test
    void missingExternalIdentityRejectsExistingLocalSession()
            throws Exception {
        MvcResult aliceResult = mvc.perform(
                get("/whoami").header("SM_USER", "alice"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"))
            .andReturn();

        MockHttpSession oldSession =
            (MockHttpSession) aliceResult.getRequest().getSession(false);
        assertNotNull(oldSession);

        mvc.perform(get("/whoami").session(oldSession))
            .andExpect(status().isUnauthorized());

        assertTrue(oldSession.isInvalid());

        mvc.perform(get("/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void independentRequestsDoNotSharePrincipals() throws Exception {
        mvc.perform(get("/whoami").header("SM_USER", "alice"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        mvc.perform(get("/whoami").header("SM_USER", "bob"))
            .andExpect(status().isOk())
            .andExpect(content().string("bob"));
    }
}
```

Chạy test trong module Spring Boot đã có các dependency:

```bash
./gradlew test --tests "example.PreAuthFlowTests"
```

Windows PowerShell: `.\gradlew.bat test --tests "example.PreAuthFlowTests"`.

Khi ba test pass, kỳ vọng đã được xác nhận là: Bob không được dùng `Authentication` Alice khi đổi principal, session Alice bị invalidated, thiếu danh tính ngoài trả 401 ngay cả nếu cookie cũ còn tồn tại, và hai request độc lập không chia sẻ danh tính. `MockMvc` không in các giá trị này thành stdout; chúng được kiểm tra bằng JUnit assertions. Đây là integration test với servlet mock, không phải kiểm thử hạ tầng gateway/SSO thật.

### Các kiểm thử cần bổ sung khi triển khai thực tế

| Test | Dữ liệu đưa vào | Assertion cốt lõi |
| --- | --- | --- |
| Đổi principal qua cùng cookie | S1/Alice → S1/Bob | Bob hiển thị Bob; S1 không còn hợp lệ; dữ liệu riêng Alice không xuất hiện |
| Không đổi principal | S1/Alice → S1/Alice | Đúng Alice; không hủy phiên vô cớ nếu policy cho phép giữ |
| Header bị thiếu/rỗng | S1/Alice → header vắng/blank | 401 (hoặc kết quả fail-closed đã thiết kế); không được truy cập dưới Alice |
| Principal không có ở user directory | Header người dùng không tồn tại | Không xác thực thành công, không giữ tài khoản trước đó; kiểm tra status ở failure path |
| Quyền đổi nhưng principal giống | Alice USER → Alice bị thu hồi quyền ADMIN | Quyền ADMIN bị từ chối trong thời hạn thu hồi đã cam kết |
| Đồng thời đổi Alice → Bob | Hai request gần như cùng lúc, cùng cookie | Không rò dữ liệu; xử lý race condition và version/session theo policy |
| Đăng xuất SSO | IdP thu hồi SSO session | Request mới không được hưởng xác thực cũ; nếu yêu cầu tức thời, xử lý sự kiện back-channel |
| Outage gateway/IdP | Không có bằng chứng xác thực mới | 401 hoặc 503, không dùng principal cũ |
| Kẻ tấn công tự chèn header | Client gửi `SM_USER: admin` | Proxy xóa/ghi đè header, hoặc backend từ chối truy cập trực tiếp |
| Session timeout | S1 hết hạn, gateway vẫn hợp lệ | Có thể pre-auth lại từ request hợp lệ; không khôi phục thuộc tính session đã mất |

Một request **đã được cho phép và đang xử lý** khi quyền vừa bị thu hồi có thể hoàn tất tùy chính sách tính nhất quán. Thay đổi ở IdP thường chỉ ảnh hưởng request kế tiếp trừ khi hệ thống có cơ chế hủy giao dịch đang chạy. Đừng tuyên bố tính năng kiểm tra principal mỗi request cung cấp khả năng thu hồi tức thời đối với công việc đã chạy.

## 7. Chính sách nhất quán session và quyền

### 7.1. Chọn kiểu lưu security context

**Mô hình session local:** `HttpSessionSecurityContextRepository` lưu `SecurityContext` qua request. Ưu điểm: giảm thao tác tra cứu lặp; nhược điểm: phải xử lý principal đổi, quyền cũ, logout từ IdP và session phân tán. Khi đổi người dùng, hủy session giúp tránh việc các thuộc tính như giỏ hàng, bộ lọc thông tin cá nhân, CSRF token hoặc dữ liệu form cũ bị gắn nhầm với Bob.

**Mô hình xác thực lại trên mỗi request:** không dựa vào session để duy trì principal; áp dụng khi gateway cung cấp bằng chứng đáng tin cho *mỗi* request và policy cho phép. `SessionCreationPolicy.STATELESS` có thể thay cơ chế lưu context trong một số ứng dụng, nhưng chỉ đổi sang STATELESS **không** tự xác thực header và cũng không thay thế kiểm tra nguồn gốc identity. Các hệ thống dùng bearer token/JWT có cơ chế xác thực khác với pre-auth header.

### 7.2. Quyền thay đổi nhưng tên không đổi

`principalChanged` phát hiện Alice → Bob, **không tự bảo đảm** cập nhật role khi Alice vẫn tên Alice. Nếu Alice mất `ROLE_ADMIN` ở directory trong khi `Authentication` local vẫn chứa authority cũ thì có thể xảy ra quyền tồn đọng.

Các chiến lược thường dùng: revalidate quyền mỗi request ở điểm cần thiết; kiểm tra phiên bản danh tính/quyền tại gateway hoặc repository; đặt TTL ngắn cho cache; revoke hoặc invalidate session khi có sự kiện cập nhật; và test rõ **thời gian tối đa để thay đổi quyền có hiệu lực**. Chọn theo tải, độ trễ, yêu cầu bảo mật và khả năng của IdP; không gọi TTL là thu hồi tức thời.

### 7.3. Logout local và logout upstream

`SecurityContextLogoutHandler` thường xóa xác thực local và có thể invalidate `HttpSession`. Nó **không tự kết thúc** phiên của IdP. Nếu gateway vẫn xác thực Alice ở request tiếp theo, pre-auth có thể đăng nhập Alice trở lại ngay; muốn logout SSO cần dùng giao thức phù hợp của IdP/gateway (ví dụ front-channel/back-channel logout theo sản phẩm/giao thức) và xử lý redirect/cookie bên ngoài.

Tương tự, khi IdP báo logout nhưng ứng dụng vẫn có session local, nên có sự kiện thu hồi gắn với session đã phát sinh, hoặc bảo đảm request mới luôn đòi tín hiệu còn hợp lệ. Với nhiều node, chỉ invalidating một session ở một node chưa chắc xóa được các session tương ứng trên node khác.

### 7.4. Principal có nhiều thuộc tính

So sánh mỗi username không đủ nếu có multi-tenant, issuer khác nhau, tài khoản bị đổi tên hoặc tái sử dụng username. Thiết kế ID bất biến, có namespace; bảo đảm `Authentication.getName()`, dữ liệu ánh xạ người dùng và logic `principalChanged` nhất quán. Không âm thầm coi hai principal cùng email nhưng khác issuer/tenant là cùng người dùng.

## 8. Những lỗi triển khai phổ biến

1. **Tin header từ Internet:** người dùng tự đặt `SM_USER: admin` và chiếm quyền. Biện pháp: backend chỉ nhận kết nối qua gateway tin cậy; gateway xóa mọi giá trị danh tính client gửi vào và điền giá trị mới đã xác thực; bảo vệ giao tiếp nội bộ.
2. **Không bật kiểm tra principal đổi:** session Alice tồn tại, gateway đã chuyển Bob nhưng app vẫn dùng Alice. Biện pháp: bật `setCheckForPrincipalChanges(true)` hoặc dùng mô hình revalidate có bảo đảm tương đương.
3. **Giữ session qua đổi người dùng mà không phân tích dữ liệu riêng:** Bob có thể nhìn thấy state của Alice. Biện pháp: ưu tiên invalidate session khi đổi; nếu bắt buộc giữ, chỉ sao chép thuộc tính đã được kiểm duyệt và test quyền sở hữu từng giá trị.
4. **Đồng nhất header vắng với logout an toàn:** nếu không có guard, session có thể còn chứa xác thực cũ; ngoại lệ từ filter cũng không tự bảo đảm cleanup bền vững. Biện pháp: có policy cụ thể cho missing/blank/invalid external identity trước khi truy cập protected resource.
5. **Tưởng `continueFilterChainOnUnsuccessfulAuthentication(false)` giải quyết cả principal=null:** thiết lập này liên quan lỗi từ `AuthenticationManager` và không thay thế policy xử lý danh tính vắng. Biện pháp: phân nhánh thiếu principal một cách riêng biệt.
6. **Đồng nhất đổi principal với đổi quyền:** khi cùng Alice nhưng vai trò thay đổi, so sánh tên có thể vẫn trả “không đổi”. Biện pháp: cập nhật authority bằng cơ chế revocation/version/TTL phù hợp.
7. **Dùng `SecurityContextHolder.clearContext()` rồi tưởng đã logout mọi request:** lệnh này chỉ tác động context hiện tại; không tự xóa context đã lưu trong session/repository. Biện pháp: dùng luồng logout/repository phù hợp và invalidate session khi cần.
8. **Đọc session trên các request thuộc nhiều node mà không đồng bộ policy:** node này đã thu hồi, node khác vẫn còn auth. Biện pháp: session store/revocation nhất quán và kịch bản test multi-node.
9. **Đăng ký pre-auth filter hai lần:** một lần thành Servlet `Filter` bean của Boot, một lần trong `SecurityFilterChain`. Biện pháp: tạo filter ở phạm vi cấu hình chain hoặc tắt servlet auto-registration khi filter là bean dùng riêng cho security chain.
10. **Đảo lẫn mã lỗi:** thiếu xác thực nhưng trả 200, hoặc hệ thống upstream outage nhưng vẫn phục vụ quyền admin. Biện pháp: định nghĩa rõ 401/403/503, bảo đảm authorization từ chối trạng thái không đáng tin.
11. **Không kiểm thử cùng cookie:** chỉ chạy Alice với cookie riêng và Bob với cookie riêng có thể bỏ sót lỗi principal change. Biện pháp: test chuyển user trên chính S1, đồng thời kiểm tra dữ liệu nghiệp vụ lưu trong session không lẫn.
12. **Giả định địa chỉ IP hoặc User-Agent chứng minh cùng người dùng:** các thuộc tính này không phải định danh xác thực; NAT, proxy và thiết bị có thể thay đổi. Dùng ID được IdP xác nhận qua kênh tin cậy.

## 9. Checklist thiết kế và kiểm chứng

- [ ] Đã xác định duy nhất hệ thống chịu trách nhiệm **xác thực gốc** và cách backend kiểm chứng đường đi đáng tin.
- [ ] Có định danh principal ổn định, có issuer/tenant khi cần, cùng quy tắc so sánh nhất quán.
- [ ] Biết rõ authentication được giữ trong `SecurityContextRepository` nào và session được tạo/xóa vào lúc nào.
- [ ] Khi Alice → Bob trên cùng cookie, context và dữ liệu session riêng Alice không còn được dùng cho Bob.
- [ ] Khi external identity **mất, rỗng, hết hạn hoặc không đáng tin**, request bị từ chối ngay cả nếu đã có local session.
- [ ] Đã phân biệt thay đổi principal với cập nhật role, khóa tài khoản, logout và upstream outage.
- [ ] Có yêu cầu cụ thể về độ trễ thu hồi: request kế tiếp, TTL vài phút, back-channel hoặc thu hồi tức thời.
- [ ] Đã kiểm thử 401/403/503, failure handler, request đồng thời, session timeout và multi-node theo kiến trúc thật.
- [ ] Không để lộ token, cookie session, credential hoặc toàn bộ `SecurityContext` trong log; dùng request/correlation ID và user ID đã xử lý dữ liệu nhạy cảm đúng cách.

**Kết luận kỹ thuật:** trong pre-authentication, `Authentication` local là ảnh chụp trạng thái đã được chấp nhận ở một thời điểm, không phải bằng chứng vĩnh viễn rằng IdP vẫn xác thực cùng người dùng. Kiểm tra thay đổi principal và xử lý session là điều kiện thiết yếu; **mất định danh ngoài và thay đổi quyền cần thêm chính sách riêng**.

## 10. Tài liệu chính thống

- Spring Security — Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security — API `AbstractPreAuthenticatedProcessingFilter`, nhất là `setCheckForPrincipalChanges` và `setInvalidateSessionOnPrincipalChange`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- Spring Security — API `RequestHeaderAuthenticationFilter` và `exceptionIfHeaderMissing`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
- Spring Security — API `PreAuthenticatedAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Handling Logouts: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — API `SecurityContextLogoutHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
