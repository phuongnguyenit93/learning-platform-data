# AbstractPreAuthenticatedProcessingFilter và PreAuthenticatedAuthenticationToken trong Spring Security

## 1. Tiền xác thực là gì?

**Pre-authentication (tiền xác thực)** là mô hình trong đó **một hệ thống bên ngoài đã kiểm tra danh tính trước khi request đi vào ứng dụng Spring Security**. Ứng dụng nhận danh tính đã được xác minh, sau đó dùng Spring Security để thiết lập `Authentication`, tra cứu trạng thái tài khoản và gán quyền cho request.

Các nguồn danh tính thường gặp:

- Reverse proxy/API gateway/SSO agent đáng tin cậy đã đăng nhập người dùng và truyền username hoặc subject qua thông tin nội bộ.
- Servlet container đã xác thực người dùng và cung cấp `HttpServletRequest.getUserPrincipal()`.
- Hạ tầng chứng chỉ máy khách X.509; Spring Security cũng có cơ chế X.509 chuyên dụng nên không cần tự viết filter nếu không có yêu cầu riêng.
- Một hệ thống nhận dạng doanh nghiệp có hợp đồng tin cậy rõ ràng về người cấp danh tính và nơi xác minh chứng cứ.

**Hai lớp bảo đảm khác nhau:** hệ thống phía trước chịu trách nhiệm chứng minh “người này là ai”; ứng dụng phía sau kiểm tra danh tính đó có tồn tại, còn hiệu lực và được phép làm gì. Tên “pre-authentication” **không có nghĩa** Spring Security tự tin mọi header/cookie/parameter từ internet, và không có nghĩa mọi tài khoản đã được gán quyền.

Trong Spring Security Servlet, cặp lớp cốt lõi của bài là:

- `AbstractPreAuthenticatedProcessingFilter`: bộ lọc trừu tượng đọc danh tính và credentials từ `HttpServletRequest` rồi chuyển thành yêu cầu xác thực cho `AuthenticationManager`.
- `PreAuthenticatedAuthenticationToken`: kiểu `Authentication` đại diện cho yêu cầu tiền xác thực và kết quả đã được xác nhận. Cùng một class có hai constructor thể hiện hai trạng thái khác nhau.

Bài học dùng Java 17+, Spring Boot 3.x và Spring Security 6.x trên **Servlet/Spring MVC** (API `jakarta.servlet.*`). Không đưa `AbstractPreAuthenticatedProcessingFilter` vào `SecurityWebFilterChain` của Spring WebFlux; reactive có lớp và hợp đồng khác.

## 2. Kiến trúc và ranh giới tin cậy

Luồng thường gặp:

```text
Browser / client
    │ 1. Đăng nhập hoặc xuất trình chứng cứ
    ▼
Identity provider / gateway / servlet container
    │ 2. Xác minh danh tính, loại bỏ thông tin giả mạo
    │ 3. Chỉ gửi danh tính đã được xác nhận qua kênh tin cậy
    ▼
Spring Security Servlet FilterChain
    │
    ▼
AbstractPreAuthenticatedProcessingFilter (subclass)
    │ getPreAuthenticatedPrincipal(request)
    │ getPreAuthenticatedCredentials(request)
    ▼
PreAuthenticatedAuthenticationToken (2 tham số, chưa authenticated)
    ▼
AuthenticationManager
    ▼
PreAuthenticatedAuthenticationProvider
    │ dùng AuthenticationUserDetailsService<UserDetails>
    │ tra cứu trạng thái tài khoản và quyền
    ▼
PreAuthenticatedAuthenticationToken (3 tham số, authenticated)
    ▼
SecurityContext → AuthorizationFilter → Controller
```

**Ranh giới quan trọng nhất là giữa gateway và ứng dụng.** Nếu client tự gửi được `X-Verified-User: admin` vào ứng dụng mà không qua cổng xác thực, attacker có thể mạo danh `admin`. Chỉ chấp nhận header kiểu này khi có đầy đủ biện pháp:

1. Ứng dụng không thể bị truy cập trực tiếp từ mạng không tin cậy; kết nối đến backend được bảo vệ bằng network policy và TLS/mTLS khi cần.
2. Gateway luôn **xóa hoặc ghi đè** header danh tính từ client, chỉ tạo header sau khi xác thực thành công.
3. Danh tính được chuẩn hóa, có giới hạn độ dài/định dạng; backend không chấp nhận nhiều giá trị xung đột hoặc chuỗi do client tự tuyên bố.
4. Quyền từ header chỉ được dùng nếu gateway thực sự được ủy quyền cấp quyền; an toàn hơn là tra quyền từ nguồn dữ liệu do ứng dụng quản lý.
5. Có cơ chế xử lý token hết hạn, thu hồi, logout, tenant và thay đổi người dùng; không dựa vào header còn tồn tại trong một kết nối như bằng chứng mãi mãi.

Validate cú pháp header ở backend **không** chứng minh header đến từ gateway. Với mô hình token OAuth2/OIDC hoặc JWT mà backend cần tự kiểm tra chữ ký, audience, issuer và expiry, dùng cơ chế resource server tương ứng thay vì biến JWT chưa kiểm chứng thành một pre-auth principal.

## 3. Cách AbstractPreAuthenticatedProcessingFilter hoạt động

Class nằm ở package:

```java
org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter
```

Một subclass cần override **hai phương thức** nhận request Servlet:

```java
@Override
protected Object getPreAuthenticatedPrincipal(HttpServletRequest request) {
    // Trả về danh tính đã được nguồn phía trước xác minh;
    // trả về null khi không có danh tính.
}

@Override
protected Object getPreAuthenticatedCredentials(HttpServletRequest request) {
    // Trả về chứng cứ đã được xử lý hoặc một giá trị dummy KHÔNG NULL
    // khi principal hợp lệ và cơ chế external không có password ở đây.
}
```

Đây là các chữ ký phương thức minh họa, không phải file Java độc lập. Trong Spring Boot 3.x, import request từ `jakarta.servlet.http.HttpServletRequest`, không dùng `javax.servlet.*` của thế hệ cũ.

### 3.1. Điều kiện tạo Authentication

- Khi security context **chưa chứa** đối tượng `Authentication`, filter cố đọc principal và credentials từ request.
- Nếu principal là `null`, filter mặc định bỏ qua lượt xác thực này và cho chain tiếp tục. Dùng cấu hình bảo vệ endpoint để quyết định kết quả của request không có danh tính.
- Nếu principal có giá trị, filter tạo `new PreAuthenticatedAuthenticationToken(principal, credentials)` rồi đưa cho `AuthenticationManager.authenticate(...)`.
- Provider được chọn sẽ xử lý token. Thông thường provider tải `UserDetails`, kiểm tra trạng thái và trả một token đã xác thực kèm `GrantedAuthority`.
- Khi thành công, filter đặt `Authentication` vào `SecurityContext`, gọi lưu context qua `SecurityContextRepository` và tiếp tục chain. Hành vi lưu lâu dài phụ thuộc repository/session policy được cấu hình.
- Khi thất bại, filter xóa trạng thái xác thực vừa xử lý. Mặc định `continueFilterChainOnUnsuccessfulAuthentication=true`, nên lỗi `AuthenticationException` có thể được nuốt để cơ chế khác xử lý. Đặt `false` khiến lỗi bị ném ra; **không mặc định suy luận** lỗi ấy luôn được chuyển thành HTTP 401/403 vì vị trí filter trong chain cũng ảnh hưởng xử lý exception.

### 3.2. Khi request đã có Authentication

Mặc định, filter **không xác thực lại** nếu security context đã có một `Authentication`. Điều này tối ưu cho session hiện tại, nhưng có thể tạo vấn đề nếu danh tính pre-auth phía trước thay đổi giữa các request.

Các thuộc tính liên quan:

| Phương thức setter | Ý nghĩa |
| --- | --- |
| `setAuthenticationManager(manager)` | Gắn manager có provider hiểu `PreAuthenticatedAuthenticationToken`. Là cấu hình thiết yếu |
| `setCheckForPrincipalChanges(true)` | So sánh principal trong request với authentication hiện tại, xác thực lại khi thay đổi |
| `setInvalidateSessionOnPrincipalChange(true)` | Khi bật kiểm tra đổi principal, vô hiệu hóa session cũ khi phát hiện thay đổi; mặc định là `true` |
| `setContinueFilterChainOnUnsuccessfulAuthentication(false)` | Ném lại `AuthenticationException` ngay khi manager thất bại, thay vì tiếp tục chain |
| `setRequiresAuthenticationRequestMatcher(matcher)` | Giới hạn request nào cần filter xử lý |
| `setAuthenticationDetailsSource(source)` | Bổ sung details (ví dụ metadata request) cho token |
| `setSecurityContextRepository(repository)` | Chọn nơi lưu security context sau khi xác thực thành công |

**Lưu ý:** `getPreAuthenticatedPrincipal` không phải hàm tự xác thực request. Nó chỉ **trích xuất** danh tính từ kênh mà kiến trúc đã chứng minh là đáng tin cậy. Nếu session được duy trì, cần quyết định cách làm mới quyền khi tài khoản bị vô hiệu hóa, vai trò thay đổi hoặc user đăng xuất từ SSO; bật `checkForPrincipalChanges` chỉ giải quyết **thay đổi principal**, không tự làm mới mọi quyền hoặc chứng cứ.

## 4. PreAuthenticatedAuthenticationToken: phân biệt yêu cầu và kết quả

Class nằm ở:

```java
org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken
```

Nó kế thừa `AbstractAuthenticationToken` và triển khai `Authentication`. Có **hai constructor** mang ý nghĩa bảo mật khác nhau:

| Cách tạo | Trạng thái | Khi dùng |
| --- | --- | --- |
| `new PreAuthenticatedAuthenticationToken(principal, credentials)` | `isAuthenticated() == false` | Filter gửi yêu cầu xác thực cho manager |
| `new PreAuthenticatedAuthenticationToken(principal, credentials, authorities)` | `isAuthenticated() == true` | Provider trả về kết quả sau khi xử lý yêu cầu và xác minh trạng thái/tra quyền |

Ví dụ độc lập về ý nghĩa object, cần project có dependency Spring Security (đặt trong `TokenDemo.java`):

```java
import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

public class TokenDemo {
    public static void main(String[] args) {
        var requestToken =
                new PreAuthenticatedAuthenticationToken("alice", "UPSTREAM_VERIFIED");

        var resultToken = new PreAuthenticatedAuthenticationToken(
                "alice",
                "UPSTREAM_VERIFIED",
                List.of(new SimpleGrantedAuthority("ROLE_READER")));

        System.out.println("request authenticated = " + requestToken.isAuthenticated());
        System.out.println("result authenticated = " + resultToken.isAuthenticated());
        System.out.println("result authority = "
                + resultToken.getAuthorities().iterator().next().getAuthority());
    }
}
```

Khi chạy `TokenDemo` với Spring Security trên classpath, stdout chính xác:

```text
request authenticated = false
result authenticated = true
result authority = ROLE_READER
```

**Không bao giờ** để controller hoặc custom filter lấy một username/header chưa được xác minh rồi dùng constructor ba tham số để tự nâng `authenticated=true`. Constructor đó không kiểm tra mật khẩu, chữ ký hay độ tin cậy. Nó chỉ biểu diễn trạng thái mà thành phần tạo object khẳng định; chỉ provider hoặc thành phần xác thực đã được thiết kế và kiểm soát phù hợp mới được tạo kết quả đã xác thực.

`getPrincipal()` trả danh tính đang xử lý, thường là username trong request và một `UserDetails` sau khi provider nạp user; `getCredentials()` có thể là dummy từ cơ chế upstream và không đồng nghĩa password. `getAuthorities()` chứa quyền **trong token kết quả**, còn `getDetails()` là metadata tùy nguồn. Không nhầm `details` với `authorities` hoặc dùng metadata để tự cấp role khi chưa kiểm chứng.

## 5. PreAuthenticatedAuthenticationProvider và UserDetailsService

`PreAuthenticatedAuthenticationProvider` là `AuthenticationProvider` hỗ trợ `PreAuthenticatedAuthenticationToken`. Nó giả định khâu xác minh chứng cứ danh tính đã hoàn tất ở hệ thống phía trước, vì vậy **không kiểm tra password như `DaoAuthenticationProvider`**.

Provider thường gọi:

```java
AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>
```

Để tải thông tin liên quan đến `Authentication` đã nhận. Nếu hệ thống đã có `UserDetailsService` tra cứu theo tên, `UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>` giúp chuyển từ giao diện nhận token sang giao diện nhận username. User details mang quyền từ DB/LDAP hoặc nguồn đáng tin, đồng thời cho phép kiểm tra tài khoản bị khóa, vô hiệu hóa, hết hạn theo chính sách.

Ví dụ lắp ráp provider (đây là **đoạn mã** nằm trong phương thức cấu hình, không phải chương trình độc lập):

```java
PreAuthenticatedAuthenticationProvider provider =
        new PreAuthenticatedAuthenticationProvider();

provider.setPreAuthenticatedUserDetailsService(
        new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>(
                userDetailsService));

AuthenticationManager manager = new ProviderManager(provider);
```

`ProviderManager` gọi các provider theo thứ tự, chọn provider hỗ trợ kiểu token và xử lý kết quả hoặc exception tương ứng. Trong ví dụ này chỉ có một provider, nên không có username/password fallback. Cân nhắc cẩn thận nếu ứng dụng đồng thời hỗ trợ form login, HTTP Basic, session và pre-auth: mỗi filter cần manager hợp lệ, thứ tự lọc rõ ràng và chính sách không cho phép dữ liệu pre-auth đáng ngờ đi vào cơ chế khác.

Một lựa chọn khác là `PreAuthenticatedGrantedAuthoritiesUserDetailsService`: nó lấy authorities từ `token.getDetails()` khi details triển khai `GrantedAuthoritiesContainer`. Chỉ dùng khi upstream **thực sự có quyền định nghĩa role** và đường truyền đã được bảo vệ; không tự tin role nhận qua header do client gửi. Nếu quyền thuộc ứng dụng, nạp bằng `UserDetailsService` thường dễ kiểm soát và thu hồi hơn.

## 6. Ví dụ Spring Boot 3 + Spring Security Servlet

Ví dụ minh họa toàn chuỗi: một gateway đáng tin xác thực người dùng và cung cấp header `X-Verified-User`; backend chỉ nhận request từ gateway. Trong **unit/integration test** có thể tự đặt header để mô phỏng gateway, nhưng trong production **không chạy cấu hình này ở cổng backend mở trực tiếp cho client**.

Tạo project Spring Boot 3.x, Java 17+, Spring MVC/Servlet (không dùng WebFlux). Trong `build.gradle` của project có plugin Spring Boot và dependency management, cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Các tệp nằm trong `src/main/java/com/example/preauth/` với package `com.example.preauth`.

### 6.1. Subclass đọc danh tính từ header tin cậy

**`GatewayPreAuthFilter.java`**

```java
package com.example.preauth;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter;

public final class GatewayPreAuthFilter extends AbstractPreAuthenticatedProcessingFilter {

    @Override
    protected Object getPreAuthenticatedPrincipal(HttpServletRequest request) {
        String user = request.getHeader("X-Verified-User");
        if (user == null || !user.matches("[A-Za-z0-9._-]{1,64}")) {
            return null;
        }
        return user;
    }

    @Override
    protected Object getPreAuthenticatedCredentials(HttpServletRequest request) {
        return "UPSTREAM_VERIFIED";
    }
}
```

Giải thích: filter chỉ đọc header và kiểm tra hình thức username. Không có API ở đây chứng minh gateway đã xác thực. Chuỗi `UPSTREAM_VERIFIED` là **dummy không rỗng**, không phải mật khẩu hay chứng cứ mật mã. Provider tiêu chuẩn yêu cầu credentials khác `null` đối với principal hợp lệ; nó không so khớp dummy. Đây là lý do phải đặt bảo mật ở ranh giới ingress.

Ứng dụng production còn phải cấm/chuẩn hóa header nhiều giá trị, có kiểm soát ingress và gắn danh tính canonical theo hợp đồng với IdP. Regex chỉ là ví dụ tối giản, có thể không phù hợp với email, subject UUID dài hoặc ký tự Unicode. Không dùng giá trị từ `X-Forwarded-User` hoặc header tự đặt khi chưa xây dựng được mô hình tin cậy rõ ràng.

### 6.2. Cấu hình provider, filter chain và user

**`SecurityConfig.java`**

```java
package com.example.preauth;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService userDetailsService() {
        var alice = new User(
                "alice",
                "PREAUTH_ONLY_NO_LOCAL_LOGIN",
                List.of(new SimpleGrantedAuthority("ROLE_READER")));
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService userDetailsService) throws Exception {

        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(
                new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>(
                        userDetailsService));
        AuthenticationManager manager = new ProviderManager(provider);

        var filter = new GatewayPreAuthFilter();
        filter.setAuthenticationManager(manager);
        filter.setCheckForPrincipalChanges(true);
        filter.setContinueFilterChainOnUnsuccessfulAuthentication(true);
        filter.setSecurityContextRepository(new NullSecurityContextRepository());

        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .securityContext(context -> context
                        .securityContextRepository(new NullSecurityContextRepository()))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(new Http403ForbiddenEntryPoint()))
                .authorizeHttpRequests(requests -> requests
                        .anyRequest().authenticated())
                .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
```

Giải thích từng quyết định:

1. `UserDetailsService` trong ví dụ chỉ chứa `alice` với quyền `ROLE_READER`; không cấp quyền từ header. Mật khẩu trong dữ liệu demo là giá trị vô dụng cho pre-auth, **không dùng để đăng nhập bằng password**. Trong hệ thống thật, tra cứu DB/LDAP và kiểm tra account policy.
2. `PreAuthenticatedAuthenticationProvider` biến token yêu cầu thành kết quả có authorities sau khi nạp `UserDetails`. Không cần `PasswordEncoder` vì user đã được upstream xác minh.
3. `GatewayPreAuthFilter` được tạo **bên trong** cấu hình filter chain, tránh trở thành một `Filter` bean mà Spring Boot tự đăng ký lần nữa ở servlet container. Nếu bắt buộc tạo bean filter, vô hiệu hóa đăng ký tự động của container bằng `FilterRegistrationBean.setEnabled(false)`.
4. `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` đưa bộ lọc vào Spring Security Servlet chain tại vị trí có thứ tự xác định; không thêm thành `@Component` servlet filter chạy ngoài security chain.
5. `SessionCreationPolicy.STATELESS` + `NullSecurityContextRepository` khiến demo không duy trì authentication qua HTTP session: **mỗi request cần danh tính upstream mới**. Tránh hiểu rằng `setCheckForPrincipalChanges(true)` tự tạo cơ chế tái kiểm tra session; tùy ứng dụng, chính sách session và quyền phải được thiết kế riêng.
6. Khi header thiếu/không hợp lệ hoặc tài khoản không tồn tại, không có authentication hợp lệ và endpoint được bảo vệ từ chối truy cập. `Http403ForbiddenEntryPoint` được chọn vì đây là demo chỉ dùng pre-auth; không triển khai login challenge. Cách xử lý lỗi khác nhau giữa 401 và 403 tùy giao thức, UX và entry point.
7. Demo không thêm `httpBasic()` hoặc `formLogin()`. Nếu bật thêm cơ chế khác, cần phân tích đường đi request và không vô tình cho phép bypass quy tắc xác thực upstream.
8. Endpoint demo chỉ đọc (GET), cấu hình CSRF mặc định vẫn giữ. Ứng dụng thực có thao tác ghi, cookie/session hoặc frontend trình duyệt phải đánh giá CSRF và cách xử lý token phù hợp.

**`PreAuthApplication.java`**

```java
package com.example.preauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PreAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(PreAuthApplication.class, args);
    }
}
```

**`WhoAmIController.java`**

```java
package com.example.preauth;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public String whoami(Principal principal) {
        return principal.getName();
    }
}
```

Các tệp Java trên là chương trình Spring Boot hoàn chỉnh khi đặt vào một project Boot 3.x đã khai báo plugin, dependencies và main class đúng package. Phần xác nhận header thuộc **hệ thống gateway ngoài ứng dụng**, nên ví dụ chỉ hoàn chỉnh về wiring Spring Security; chưa phải một giải pháp SSO production nếu chưa triển khai ranh giới tin cậy.

### 6.3. Test filter → provider → SecurityContext → controller

Dùng Spring Boot Test và MockMvc để kiểm tra mã nội bộ mà không cần triển khai reverse proxy thật. Tệp `src/test/java/com/example/preauth/PreAuthIntegrationTest.java`:

```java
package com.example.preauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PreAuthIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsKnownTrustedPrincipal() throws Exception {
        mvc.perform(get("/whoami").header("X-Verified-User", "alice"))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void rejectsRequestWithoutPrincipal() throws Exception {
        mvc.perform(get("/whoami"))
                .andExpect(status().isForbidden());
    }

    @Test
    void rejectsUnknownPrincipal() throws Exception {
        mvc.perform(get("/whoami").header("X-Verified-User", "mallory"))
                .andExpect(status().isForbidden());
    }

    @Test
    void rejectsMalformedPrincipal() throws Exception {
        mvc.perform(get("/whoami").header("X-Verified-User", "alice,bob"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy trong project Gradle có wrapper:

```bash
./gradlew test
```

Trên Windows dùng `.\gradlew.bat test`. Các test được kỳ vọng thành công nếu project Boot 3.x có dependency trên; đây là **kỳ vọng của mã minh họa**, không phải khẳng định đã chạy kiểm thử trong repository. Header trong MockMvc là dữ liệu giả lập upstream **đã được xác nhận**; test này chỉ kiểm thử ứng dụng nhận thông tin đúng cách, **không kiểm chứng** gateway thật đã chống spoofing. Bổ sung kiểm thử ingress/network policy trong môi trường tích hợp.

Trong môi trường thử nghiệm **cách ly** có thể gửi:

```bash
curl -i http://localhost:8080/whoami
curl -i -H 'X-Verified-User: alice' http://localhost:8080/whoami
```

Với demo trên, request đầu dự kiến `403 Forbidden`; request thứ hai dự kiến `200 OK` và body `alice`. Cũng vì lý do đó, **đừng** công khai cổng demo để client tùy ý tự đặt header; production phải đặt gateway đã xác thực phía trước.

## 7. Chính xác ai kiểm tra gì?

Cần phân biệt trách nhiệm để không hiểu sai từ “authenticated”:

| Thành phần | Xác thực chứng cứ như password/token/chứng chỉ? | Xử lý danh tính và quyền? |
| --- | --- | --- |
| IdP / gateway / container | **Có**, theo giao thức upstream và hợp đồng tin cậy | Có thể chuẩn hóa subject, claims |
| `AbstractPreAuthenticatedProcessingFilter` | **Không**; chỉ lấy principal/credentials | Tạo token chưa xác thực và gọi manager |
| `PreAuthenticatedAuthenticationProvider` | **Không kiểm tra lại** mật khẩu của upstream | Dùng `AuthenticationUserDetailsService` tải user, kiểm tra trạng thái theo policy, tạo token kết quả |
| `AuthorizationFilter` và access rules | Không làm login | Kiểm tra quyền truy cập endpoint |
| `SecurityContextHolder` | Không tạo bằng chứng danh tính | Giữ authentication của luồng xử lý hiện tại |

Cụ thể, `PreAuthenticatedAuthenticationToken("alice", "UPSTREAM_VERIFIED")` **chưa được xác thực** vì `isAuthenticated=false`. `PreAuthenticatedAuthenticationToken(userDetails, ..., authorities)` **được đánh dấu đã xác thực** do provider trả. Tính đúng đắn tổng thể phụ thuộc cả hai: upstream thực sự xác minh danh tính **và** backend chỉ nhận thông tin từ upstream tin cậy.

Lưu ý về trạng thái tài khoản: tự tạo `UserDetails` mà luôn trả enabled/active dù tài khoản bị khóa sẽ làm mất lớp bảo vệ ở ứng dụng. Triển khai thực phải định nghĩa nguồn trạng thái, độ trễ đồng bộ, chính sách thu hồi phiên/quyền; provider không thể tự biết một tài khoản đã bị khóa trong hệ thống ngoài nếu nguồn `UserDetails` không cập nhật.

## 8. Hai chiến lược cung cấp danh tính thường gặp

### 8.1. Servlet container đã thiết lập principal

Nếu container thực sự áp dụng container-managed authentication, subclass có thể đọc:

```java
@Override
protected Object getPreAuthenticatedPrincipal(HttpServletRequest request) {
    var principal = request.getUserPrincipal();
    return principal == null ? null : principal.getName();
}

@Override
protected Object getPreAuthenticatedCredentials(HttpServletRequest request) {
    return "CONTAINER_VERIFIED";
}
```

Đây là đoạn phương thức để thay thế trong subclass, không phải chương trình chạy độc lập. Có sẵn `J2eePreAuthenticatedProcessingFilter` phục vụ trường hợp này. **Không giả định** `request.getUserPrincipal()` luôn có giá trị trên mọi embedded servlet container; phải cấu hình hệ thống authentication ở container trước. Mã ứng dụng hoặc một filter khác tự gắn `Principal` vào request mà không xác minh sẽ không tạo ra bằng chứng đáng tin.

### 8.2. Gateway chuyển username qua HTTP header

Khi đã bảo vệ ingress, `RequestHeaderAuthenticationFilter` có sẵn trong Spring Security và có thể thay việc viết subclass nếu chỉ cần đọc một header. Theo tài liệu, nó thường dùng header mặc định `SM_USER` và có thể cấu hình `principalRequestHeader`. Tuy nhiên bản thân lớp này **không chứng minh header là thật**. Việc dùng lớp có sẵn hay subclass chỉ thay đổi cách trích xuất, không thay thế kiểm chứng ở gateway.

**Chọn custom subclass khi** cần lấy principal qua request attribute đã xác thực, xử lý chuẩn hóa danh tính đặc thù, hoặc có hợp đồng lọc request cần kiểm soát rõ ràng. **Chọn lớp sẵn có khi** giao thức đã được hỗ trợ chuẩn (X.509, container, trusted request header), tránh viết lại bộ lọc không cần thiết.

## 9. Xử lý lỗi, session và thay đổi danh tính

Các tình huống quan trọng:

| Tình huống | Điều cần diễn giải/kiểm thử |
| --- | --- |
| Không có principal | Filter bỏ qua xác thực; authorization/entry point quyết định phản hồi |
| Header có nhưng user không tồn tại | Provider/user details service không cấp authentication; không tự tạo user/quyền dựa trên header |
| Tài khoản bị vô hiệu hóa hoặc khóa | Phải bị từ chối theo chính sách tải/kiểm tra `UserDetails` |
| Upstream không xác thực nhưng vẫn đặt header | Lỗ hổng mạo danh **bên ngoài** phạm vi filter; phải sửa ở ingress |
| Principal đổi trong session | Cân nhắc `setCheckForPrincipalChanges(true)` và invalidation; kiểm tra session/tenant isolation |
| Quyền user đổi nhưng principal giữ nguyên | Có thể cần làm mới `UserDetails`, session hoặc token; đổi-principal check không đủ |
| AuthenticationManager ném exception | Tùy `continueFilterChainOnUnsuccessfulAuthentication`, cơ chế khác và vị trí filter mà request tiếp tục hoặc lỗi được đẩy ra |
| Nhiều auth mechanism | Ràng buộc filter chain theo URL và thứ tự rõ ràng; không dùng fallback vô tình tạo bypass |

Đối với **stateless** như ví dụ, context không lưu qua session; request sau muốn được xác thực phải tiếp tục đi qua upstream để nhận danh tính. Đối với **stateful session**, lựa chọn `SecurityContextRepository` phù hợp, tính đến session fixation và logout đồng bộ. Cấu hình `SecurityContextHolderFilter` trong Spring Security hiện đại thường yêu cầu việc **lưu rõ ràng** context; filter pre-auth có API `setSecurityContextRepository` để đáp ứng khi cần. Chỉ thay `SecurityContextHolder.getContext().setAuthentication(...)` thủ công thường không đủ để duy trì trạng thái giữa các request.

Phân biệt lỗi credential thông thường và pre-auth: ứng dụng chỉ dùng pre-auth có thể chọn `Http403ForbiddenEntryPoint` để trả 403 khi request chưa có authentication; dịch vụ REST dùng bearer token hoặc giao diện tương tác có thể chọn entry point khác. Không tuyên bố một HTTP status duy nhất áp dụng cho mọi cấu hình.

## 10. Lỗi phổ biến

1. **Tin vào header từ client.** Nếu backend nhận trực tiếp `X-Verified-User: admin` thì có thể bị mạo danh dù code Spring Security đúng cú pháp. Phải xác minh gateway và chặn đường truy cập vòng.
2. **Gọi constructor ba tham số ngay từ filter.** Tự đánh dấu token `authenticated=true` bằng danh tính chưa được kiểm chứng có thể bỏ qua manager/provider. Dùng constructor hai tham số cho request.
3. **Dùng `getPreAuthenticatedCredentials() == null` cho principal hợp lệ.** Provider tiêu chuẩn có thể từ chối. Dùng dummy không rỗng khi upstream không có password được chuyển tới backend.
4. **Nhầm `UserDetailsService` với cơ chế login.** Service chỉ nạp user và quyền; chứng cứ đã được xác minh trước. Cần `AuthenticationManager`/`PreAuthenticatedAuthenticationProvider` trong đường đi.
5. **Không giới hạn nguồn authorities.** Header tự khai `ROLE_ADMIN` không đủ để backend cấp quyền; chỉ dùng claims/role từ nguồn có tin cậy rõ ràng.
6. **Đăng ký cùng filter hai lần.** Khi filter là Spring bean và còn được thêm vào `HttpSecurity`, Spring Boot có thể tự đăng ký ở container; tạo tại chỗ hoặc vô hiệu đăng ký container.
7. **Không xử lý thay đổi principal/session.** Khi login SSO thay user mà session cũ vẫn chứa authentication cũ, có nguy cơ lẫn danh tính. Xét `checkForPrincipalChanges` và session invalidation.
8. **Nuốt mọi exception rồi cho `permitAll()`.** Mặc định filter có thể cho chain tiếp tục sau lỗi, nhưng authorization vẫn phải bảo vệ tài nguyên; cơ chế fallback phải được chủ động thiết kế.
9. **Dùng sai web stack.** `AbstractPreAuthenticatedProcessingFilter` là Servlet filter; WebFlux có pipeline reactive khác, không dùng class này trong `SecurityWebFilterChain`.
10. **Bỏ qua test trust boundary.** MockMvc đặt header chỉ chứng minh backend xử lý đúng. Phải kiểm tra gateway strip/overwrite header và mạng không cho truy cập thẳng backend.

## 11. Bài tập tự luyện

1. Viết một subclass dựa trên `request.getUserPrincipal()` rồi giải thích cách container xác thực user trước khi request đến Spring Security. So sánh ưu/nhược với header từ gateway.
2. Dùng `UserDetailsService` lấy quyền từ database và khóa tài khoản `alice`. Viết test xác minh tài khoản khóa không được vào `/whoami` dù gateway vẫn gửi danh tính hợp lệ.
3. Thêm một request `X-Verified-User: bob` sau khi đã xác thực `alice` trong một session stateful. Bật/tắt `checkForPrincipalChanges`, kiểm tra kết quả và chính sách vô hiệu hóa session.
4. Viết kiểm thử ở biên ingress: gửi header giả từ internet phải bị gateway xóa hoặc từ chối; gửi request qua đường nội bộ được cấp danh tính thì backend mới nhận. Mục tiêu là chứng minh **nguồn xác thực**, không chỉ format header.
5. So sánh `PreAuthenticatedAuthenticationToken` hai và ba constructor; giải thích vì sao boolean `isAuthenticated` không phải bằng chứng mã hóa của danh tính.

## 12. Ghi nhớ

- `AbstractPreAuthenticatedProcessingFilter` **trích xuất** danh tính pre-auth từ Servlet request, tạo token yêu cầu và gọi `AuthenticationManager`.
- `PreAuthenticatedAuthenticationToken` hai tham số là **request chưa xác thực**; ba tham số đại diện cho **kết quả đã xác thực** kèm quyền.
- `PreAuthenticatedAuthenticationProvider` dùng `AuthenticationUserDetailsService` để tải user và authorities; đây không phải password authentication.
- Thành công của cơ chế phụ thuộc vào **upstream tin cậy**, chính sách quyền và trạng thái tài khoản ở backend, cùng lifecycle của `SecurityContext`.
- Khi không có nguồn tiền xác thực đáng tin cậy, **không nên** thêm một header rồi xem nó là đăng nhập. Hãy dùng cơ chế xác thực phù hợp của Spring Security.

**Tài liệu chính thức để tra cứu:** Spring Security Pre-Authentication Scenarios (https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html); Javadoc `AbstractPreAuthenticatedProcessingFilter` (https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html); Javadoc `PreAuthenticatedAuthenticationToken` (https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationToken.html); Spring Security Servlet Architecture (https://docs.spring.io/spring-security/reference/servlet/architecture.html); Spring Security Authentication Persistence (https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html).