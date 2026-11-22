# RequestHeaderAuthenticationFilter và dữ liệu danh tính từ header

> **Phạm vi:** Spring Security Servlet, cơ chế **pre-authentication** (tiền xác thực). Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x. Header định danh chỉ đáng tin khi **một hệ thống phía trước đã xác thực người dùng và kiểm soát toàn bộ đường vào ứng dụng**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `RequestHeaderAuthenticationFilter` chỉ đọc danh tính từ HTTP header mà **không kiểm tra mật khẩu, chữ ký hay token**.
2. Mô tả chuỗi `header → PreAuthenticatedAuthenticationToken → AuthenticationManager → PreAuthenticatedAuthenticationProvider → UserDetails/authorities → SecurityContext`.
3. Phân biệt **xác thực ở gateway/SSO**, **nhận danh tính tiền xác thực ở ứng dụng** và **ủy quyền truy cập tài nguyên**.
4. Cấu hình một ví dụ servlet có header `X-Authenticated-User`, giới hạn người dùng được công nhận và xử lý request thiếu/sai header.
5. Nhận diện nguy cơ giả mạo header, đường truy cập trực tiếp vào backend, session giữ danh tính cũ và quyền bị gán sai; thiết kế kiểm thử cả ở Java lẫn hạ tầng proxy.

## 1. Tiền xác thực là gì?

Trong kiến trúc **pre-authentication**, một hệ thống khác đã thực hiện xác thực trước khi request đến ứng dụng Java. Ví dụ: doanh nghiệp dùng một identity-aware reverse proxy, enterprise SSO gateway, web access manager hoặc container đã xác minh danh tính người truy cập. Sau khi thành công, thành phần đó chuyển danh tính đã xác minh cho backend.

```text
Trình duyệt / HTTP client
     │ 1. Gửi cookie/token/credentials cho hệ thống phía trước
     ▼
Gateway / SSO / reverse proxy
     │ 2. THỰC HIỆN xác thực: verify session/token/certificate...
     │ 3. Xóa header nhận từ client, tự đặt header danh tính được xác minh
     │    X-Authenticated-User: lan
     ▼
Spring Boot backend (chỉ nhận traffic từ gateway đáng tin)
     │ 4. RequestHeaderAuthenticationFilter đọc username="lan"
     │ 5. PreAuthenticatedAuthenticationProvider tra user & authorities
     │ 6. SecurityContext có Authentication đã xác thực
     ▼
AuthorizationFilter / controller
     │ 7. Kiểm tra ROLE_READER, ROLE_ADMIN... theo endpoint
     ▼
Kết quả HTTP
```

**Điểm cốt lõi:** `RequestHeaderAuthenticationFilter` **không làm bước 2**. Nó không biết phía trước đã xác minh cookie, password, JWT, MFA hay chưa. Bộ lọc **chỉ lấy tên** từ request header, rồi đi qua hạ tầng `AuthenticationManager` của Spring Security để nạp thông tin tài khoản và quyền. Nếu ai đó có thể gửi trực tiếp một header giả vào ứng dụng, họ có thể mạo danh người khác.

Ví dụ request sau **không phải bằng chứng đăng nhập** nếu nó được gửi trực tiếp từ client chưa được xác minh:

```http
GET /api/me HTTP/1.1
Host: app.example.org
X-Authenticated-User: admin
```

Header chỉ có ý nghĩa sau khi **một proxy tin cậy** loại bỏ mọi giá trị do client tự cung cấp và gắn giá trị từ **kết quả xác thực thực sự**. Không dùng cơ chế này cho một ứng dụng public tự nhận header từ Internet.

### Ba tầng trách nhiệm

| Tầng | Hành động | Ai sở hữu? |
|---|---|---|
| **Authentication upstream** | Chứng minh người dùng là ai, xác minh credential/token/session, MFA nếu cần | SSO/gateway/IdP hoặc hạ tầng |
| **Pre-authentication trong Spring Security** | Nhận định danh đã xác minh, tra tài khoản, lấy authorities và đưa vào `SecurityContext` | `RequestHeaderAuthenticationFilter`, provider và user service |
| **Authorization** | Quyết định tài khoản đó được gọi API nào, thao tác nào | Authorization rules của ứng dụng |

Tra cứu được user bằng username và sinh `Authentication.isAuthenticated() == true` ở backend không chứng minh rằng bản thân backend đã kiểm tra mật khẩu. Bằng chứng nằm ở **hệ thống upstream** và ở cách hạ tầng ngăn header giả lọt vào.

## 2. RequestHeaderAuthenticationFilter hoạt động như thế nào?

Lớp `org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter` mở rộng `AbstractPreAuthenticatedProcessingFilter`. Nó cung cấp hai điểm đọc từ `HttpServletRequest`:

- `getPreAuthenticatedPrincipal(request)`: đọc giá trị header chứa **username/principal**.
- `getPreAuthenticatedCredentials(request)`: mặc định trả chuỗi giả `"N/A"` vì password thường đã được xử lý ở bên ngoài; nếu cấu hình `credentialsRequestHeader`, nó có thể đọc một header khác, nhưng **không tự xác minh** giá trị đó.

Bộ lọc tạo `PreAuthenticatedAuthenticationToken` chưa được tin cậy và gọi `AuthenticationManager.authenticate(...)`. `PreAuthenticatedAuthenticationProvider` thường chuyển username sang một `UserDetails` và authorities thông qua `AuthenticationUserDetailsService`. Sau đó Spring Security đặt kết quả vào `SecurityContext` cho việc ủy quyền trong request.

### Các thuộc tính đáng nhớ

| Thuộc tính | Ý nghĩa và mặc định |
|---|---|
| `principalRequestHeader` | Tên header chứa username; mặc định là `SM_USER` (tương thích Siteminder). Có thể đổi thành `X-Authenticated-User`. |
| `credentialsRequestHeader` | Nếu được đặt, filter lấy credentials từ header đó; mặc định **không đặt** nên dùng giá trị giả `"N/A"`. Đây không phải bước verify credentials. |
| `exceptionIfHeaderMissing` | Mặc định `true`: thiếu header sẽ ném `PreAuthenticatedCredentialsNotFoundException`. Đặt `false` thì nhận principal `null` và có thể tiếp tục chain; phải bảo đảm authorization cuối cùng từ chối request chưa xác thực. |
| `authenticationManager` | Bắt buộc: nơi tiếp nhận `PreAuthenticatedAuthenticationToken` và chạy provider phù hợp. |
| `continueFilterChainOnUnsuccessfulAuthentication` | Kế thừa từ lớp cha, mặc định `true`: lỗi của manager được xử lý và chain có thể tiếp tục. Chỉ an toàn khi không có nhánh xác thực yếu hơn và authorization luôn từ chối request chưa xác thực. |
| `checkForPrincipalChanges` | Mặc định không kiểm tra lại principal nếu `SecurityContext` đã có Authentication; có thể bật để xử lý thay đổi danh tính giữa các request khi dùng session. |
| `invalidateSessionOnPrincipalChange` | Khi bật kiểm tra thay đổi principal, mặc định cho phép vô hiệu hóa session cũ khi danh tính đổi. |

**Thiếu header khác header rỗng:** mặc định điều kiện trong `RequestHeaderAuthenticationFilter` kiểm tra `null`, không thay thế toàn bộ quy tắc kiểm tra “username hợp lệ”. Một header tồn tại nhưng rỗng/không hợp lệ cần bị từ chối bởi gateway và/hoặc logic tra user của ứng dụng. Không tự chuyển header rỗng sang tài khoản mặc định.

### Luồng nội bộ chi tiết

```text
HTTP request từ trusted proxy
       |
       v
RequestHeaderAuthenticationFilter
  principal = request.getHeader("X-Authenticated-User")
  credentials = "N/A"
       |
       +-- principal == null? (hành vi tùy exceptionIfHeaderMissing)
       |
       v
PreAuthenticatedAuthenticationToken(principal, "N/A")
       |
       v
AuthenticationManager
       |
       v
PreAuthenticatedAuthenticationProvider
       |
       v
AuthenticationUserDetailsService
       |
       +--> UserDetailsService / database / directory
       |      - user có tồn tại?
       |      - trạng thái account có cho phép?
       |      - authorities nào được cấp?
       |
       v
Authentication (authenticated=true, principal, authorities)
       |
       v
SecurityContext -> AuthorizationFilter -> Controller
```

`PreAuthenticatedAuthenticationProvider` không tự xác minh mật khẩu hay chữ ký header. Mặc định nó có thể dùng `AccountStatusUserDetailsChecker` để đánh giá trạng thái `UserDetails`, nhưng đó **không** thay thế upstream authentication.

## 3. Ví dụ Spring Boot 3.x / Spring Security 6.x

Giả sử môi trường triển khai có **proxy duy nhất đã xác thực người dùng**, proxy gắn `X-Authenticated-User` và mạng nội bộ chặn client truy cập trực tiếp Spring Boot. Đoạn này minh họa **phần ứng dụng**, không cung cấp cơ chế xác thực upstream.

### 3.1. Gradle dependencies

Trong dự án Spring Boot 3.x đã thiết lập plugin/versions theo BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không cần `spring-security-ldap`, OAuth2 client hay JWT decoder trong ví dụ này: phía trước đã thực hiện xác thực; ứng dụng chỉ làm pre-auth và authorization. Với triển khai thực tế, `UserDetailsService` có thể truy vấn database hoặc hệ thống quản lý tài khoản doanh nghiệp.

### 3.2. Cấu hình SecurityFilterChain và pre-auth provider

Lưu vào `src/main/java/com/example/demo/HeaderSecurityConfig.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class HeaderSecurityConfig {

    @Bean
    UserDetailsService users() {
        // Chỉ mô phỏng một kho tài khoản/role nội bộ.
        // Password này KHÔNG được dùng để xác minh trong pre-auth.
        return new InMemoryUserDetailsManager(
            User.withUsername("lan")
                .password("{noop}unused-in-preauth")
                .roles("READER")
                .build()
        );
    }

    @Bean
    AuthenticationManager preAuthManager(UserDetailsService users) {
        var userDetails =
            new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>(users);

        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(userDetails);
        provider.setThrowExceptionWhenTokenRejected(true);

        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http, AuthenticationManager preAuthManager) throws Exception {

        var headerFilter = new RequestHeaderAuthenticationFilter();
        headerFilter.setPrincipalRequestHeader("X-Authenticated-User");
        headerFilter.setAuthenticationManager(preAuthManager);

        // Vắng header => không tạo Authentication;
        // bất kỳ request chưa xác thực nào phải bị chặn ở authorization.
        headerFilter.setExceptionIfHeaderMissing(false);

        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/me").hasRole("READER")
                .anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                exceptions.authenticationEntryPoint(new Http403ForbiddenEntryPoint()))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(
                headerFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
```

**Từng thành phần có nhiệm vụ gì?**

1. `users()` là kho tài khoản **mô phỏng** chứa duy nhất `lan` và `ROLE_READER`. Trong production, thay nó bằng `UserDetailsService` truy vấn người dùng có hiệu lực và chính sách roles thực tế. Không nhận mọi chuỗi header tùy ý rồi tự cấp `ROLE_ADMIN`.
2. `UserDetailsByNameServiceWrapper` chuyển từ một `Authentication` sang việc gọi `UserDetailsService.loadUserByUsername`; provider sử dụng dữ liệu đã tra cứu để công nhận danh tính và authorities. Nó **không** thực hiện `PasswordEncoder.matches` trong luồng này.
3. `ProviderManager` chứa `PreAuthenticatedAuthenticationProvider`, không có `DaoAuthenticationProvider` cho một đường login bằng password khác.
4. `RequestHeaderAuthenticationFilter` lấy username từ `X-Authenticated-User`, không nhận giá trị header đó làm password hoặc JWT.
5. `setExceptionIfHeaderMissing(false)` là **lựa chọn chủ ý của ví dụ**: nếu không có header thì filter bỏ qua pre-auth; cùng với `anyRequest().authenticated()`, `Http403ForbiddenEntryPoint` và không có login khác, truy cập bị chặn. Mặc định của filter vẫn là `true` (ném exception).
6. `SessionCreationPolicy.STATELESS` yêu cầu mỗi request có danh tính được xác minh lại ở upstream, không dựa vào session đăng nhập trước tại Spring Security.
7. `formLogin` và `httpBasic` bị tắt để ví dụ không mở thêm đường xác thực vượt qua kiến trúc gateway. `Http403ForbiddenEntryPoint` trả 403 khi ứng dụng không có Authentication hợp lệ.
8. `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` đưa pre-auth filter vào filter chain trước giai đoạn authorization. Không đăng ký chính `headerFilter` làm một Servlet `Filter` bean riêng: tránh nguy cơ nó được chạy hai lần ngoài `SecurityFilterChain`.

Ví dụ chỉ minh họa **cơ chế**, chưa cung cấp kho user sản xuất, hạ tầng SSO và chính sách giới hạn network. **Không triển khai public nguyên trạng** rồi dựa vào việc khó đoán tên header để bảo vệ hệ thống.

### 3.3. Endpoint đọc danh tính và quyền

Lưu vào `src/main/java/com/example/demo/MeController.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    public record MeResponse(String username, List<String> authorities) {}

    @GetMapping("/api/me")
    public MeResponse me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
        return new MeResponse(authentication.getName(), roles);
    }
}
```

`Authentication` có trong controller vì endpoint cần `ROLE_READER`. Giá trị `authentication.getName()` xuất phát từ principal được proxy chuyển vào và được `UserDetailsService` chấp nhận; danh sách authorities là dữ liệu quyền do ứng dụng nạp.

Để chạy ứng dụng demo, cần một class `@SpringBootApplication` ở package `com.example.demo` (hoặc package cha) với `SpringApplication.run(...)`, build bằng Spring Boot Gradle plugin và chạy `./gradlew bootRun`; trên Windows dùng `gradlew.bat bootRun`. Không chạy file config bằng lệnh `javac` đơn lẻ vì cần Spring Boot runtime/dependencies.

## 4. Điều kiện bắt buộc ở reverse proxy / SSO

Ví dụ phía trên chỉ an toàn nếu hạ tầng đạt **cả ba điều kiện**:

1. **Toàn bộ request** đến backend phải đi qua một gateway được xác thực; backend không có ingress hoặc cổng public, không có đường truy cập phụ/health/debug nào bỏ qua kiểm soát ngoài chính sách.
2. Gateway **xóa hoặc ghi đè** mọi bản sao header định danh từ client (bao gồm các biến thể, duplicate headers và các header khác có thể được ứng dụng diễn giải thành danh tính). Chỉ tạo `X-Authenticated-User` từ **kết quả xác thực upstream**.
3. Kênh gateway → backend được bảo vệ bằng mạng riêng đã kiểm soát, TLS/mTLS khi phù hợp, và quyền truy cập tối thiểu. Không dùng danh sách IP client hay `X-Forwarded-For` như bằng chứng đăng nhập.

Một tình huống đúng: client gửi `X-Authenticated-User: admin` nhưng thực tế xác thực SSO là `lan`. Gateway phải **loại bỏ giá trị admin** và chuyển đến ứng dụng `X-Authenticated-User: lan`. Nếu client chưa xác thực, gateway từ chối ngay, không chuyển request dưới một identity tự chọn.

### Mẫu Nginx có auth_request (minh họa triển khai)

Nginx có thể gọi một auth service nội bộ để quyết định 2xx/401/403; ví dụ rút gọn dưới đây **chỉ đúng** khi `auth-service` thật sự kiểm tra session/token và trả header danh tính từ kết quả xác thực đó:

```nginx
location = /_auth {
    internal;
    proxy_pass http://auth-service.internal/verify;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";

    # Không cho client cung cấp sẵn danh tính cho auth service.
    proxy_set_header X-Authenticated-User "";
}

location / {
    auth_request /_auth;

    # Tên user trả về bởi auth service SAU KHI xác minh.
    auth_request_set $verified_user $upstream_http_x_authenticated_user;

    # Ghi đè header danh tính do client gửi tới.
    proxy_set_header X-Authenticated-User $verified_user;

    proxy_pass http://spring-backend.internal:8080;
}
```

Giải thích: `auth_request` chỉ cho qua khi auth subrequest được chấp thuận; `auth_request_set` lấy header do **auth service tin cậy** cung cấp, còn `proxy_set_header` ghi lại identity trước khi chuyển cho Spring Boot. Nếu auth service không trả username, biến thường rỗng và backend sẽ từ chối theo chính sách tài khoản. Phải cấu hình chính xác URI/upstream, forwarding cookie/token, timeout và error handling cho sản phẩm đang dùng. Cấu hình này **không tự tạo SSO** và không có ý nghĩa nếu `spring-backend.internal` vẫn truy cập được từ mạng không tin cậy.

### Vì sao không thể “tự tin header” chỉ vì có HTTPS?

HTTPS mã hóa đường truyền; nó **không xác thực nội dung header do client tự đặt**. Một request có TLS hợp lệ vẫn có thể mang `X-Authenticated-User: ceo` do người gọi tạo. Chỉ khi mối quan hệ xác thực và tin cậy giữa gateway/backend được thiết lập, ứng dụng mới có thể sử dụng header đó làm identity.

## 5. Các trạng thái request và phản hồi

Giả sử dùng đúng ví dụ Java trong mục 3, gửi request qua đường **đã được gateway bảo vệ**:

| Trạng thái request tại backend | Spring Security xử lý | Kỳ vọng |
|---|---|---|
| `X-Authenticated-User: lan`; user còn hiệu lực | Tra user `lan`, cấp `ROLE_READER` | `GET /api/me` trả 200 và danh tính `lan` |
| Không có header | Filter bỏ qua pre-auth do config `false`; endpoint yêu cầu xác thực | 403 |
| `X-Authenticated-User: nguoi-khong-ton-tai` | `UserDetailsService` không thấy user; không có `Authentication` hợp lệ | 403 trong cấu hình không có fallback khác |
| Header rỗng | Không tìm ra tài khoản có username rỗng | Bị từ chối; nên loại bỏ sớm ở gateway |
| `X-Authenticated-User: lan` nhưng tài khoản bị disable | `AccountStatusUserDetailsChecker` có thể từ chối account theo trạng thái `UserDetails` | 403 trong cấu hình ví dụ |
| Header hợp lệ nhưng không có `ROLE_READER` | Xác thực danh tính có thể thành công, authorization bị từ chối | 403 cho `/api/me` |
| Upstream xác thực thất bại | Gateway không chuyển request | Thường 401/403 từ gateway, phụ thuộc hệ thống |
| Request vào trực tiếp backend và tự đặt `X-Authenticated-User: lan` | **Filter không thể phân biệt request giả với request hợp lệ** | Rủi ro giả mạo danh tính: lỗi nghiêm trọng của hạ tầng |

**Không lấy việc API trả 200 khi gửi header bằng curl trực tiếp làm bằng chứng hệ thống an toàn.** Điều đó chỉ chứng minh filter hoạt động; nó còn chứng minh nguy cơ mạo danh nếu cổng ứng dụng bị mở trực tiếp cho người dùng cuối.

### Hành vi khi header thiếu: không suy diễn status của cấu hình khác

Với `exceptionIfHeaderMissing=true` mặc định, filter ném `PreAuthenticatedCredentialsNotFoundException`. HTTP status thực tế phụ thuộc vị trí filter và exception handling của ứng dụng; đừng khẳng định mọi cấu hình sẽ trả 401 hoặc 403 tự động. Ở ví dụ đã cố ý đặt `false` và dùng rule bắt buộc xác thực cùng `Http403ForbiddenEntryPoint`, nên có đường đi 403 rõ ràng cho request chưa xác thực.

Tương tự, `setContinueFilterChainOnUnsuccessfulAuthentication(false)` khiến filter ném lại `AuthenticationException` nếu manager từ chối; cần kiểm tra exception handling theo filter order của ứng dụng, không mặc định rằng mọi lỗi sẽ được tự chuyển sang response 403. Giữ mặc định `true` trong ví dụ **chỉ an toàn** vì không có bất kỳ cơ chế login dự phòng nào và toàn bộ route đều yêu cầu Authentication.

## 6. Kiểm thử ứng dụng bằng MockMvc

Bổ sung file `src/test/java/com/example/demo/HeaderPreauthTests.java`. Đây là **test lớp Spring Security**, cố tình mô phỏng request *đã đi qua gateway*; test này **không xác minh mức độ an toàn của reverse proxy ngoài thực tế**.

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HeaderPreauthTests {

    @Autowired
    MockMvc mvc;

    @Test
    void trustedHeaderLoadsPrincipalAndRoles() throws Exception {
        mvc.perform(get("/api/me").header("X-Authenticated-User", "lan"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("lan"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_READER"));
    }

    @Test
    void missingHeaderIsDenied() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownUserIsDenied() throws Exception {
        mvc.perform(get("/api/me")
                .header("X-Authenticated-User", "nonexistent"))
            .andExpect(status().isForbidden());
    }

    @Test
    void emptyHeaderIsDenied() throws Exception {
        mvc.perform(get("/api/me")
                .header("X-Authenticated-User", ""))
            .andExpect(status().isForbidden());
    }
}
```

**Lưu ý test thực thi:** chương trình cần `@SpringBootApplication` ở package tương thích, dependencies tại mục 3.1 và Spring Boot 3.x/Spring Security 6.x. Chạy với `./gradlew test --tests com.example.demo.HeaderPreauthTests` hoặc tương đương trên Windows. Không có một stdout cố định khác ngoài kết quả test pass/fail của môi trường Gradle tương ứng.

Phải có **kiểm thử tích hợp gateway riêng**, ví dụ:

- Client chưa đăng nhập gửi header tùy ý từ Internet → gateway chặn (không thể trở thành `lan`/`admin`).
- Client đã xác thực là `lan` cố gửi `X-Authenticated-User: admin` → backend chỉ thấy username được gateway xác nhận là `lan`.
- Truy cập trực tiếp IP/port backend từ mạng public hoặc môi trường không tin cậy → bị mạng/ingress chặn.
- Auth service timeout/down hoặc không trả định danh → không có đường bỏ qua SSO.
- Có nhiều bản sao header hoặc biến thể encoding/casing → proxy chuẩn hóa và chỉ gửi một định danh được kiểm soát.
- Đổi user/logout/thu hồi tài khoản upstream → xác thực request tiếp theo thay đổi tương ứng; không giữ phiên backend trái chính sách.

MockMvc chỉ kiểm tra **xử lý sau khi header đã đến**, không kiểm tra danh tính trong header có bị giả mạo trên đường từ client đến gateway hay không.

## 7. Quản lý danh tính, authorities và session

### 7.1. Header định danh khác header quyền hạn

`X-Authenticated-User: lan` chỉ mô tả **ai đang truy cập** theo upstream. Nó không chứa quy tắc `ROLE_ADMIN`. Ví dụ `UserDetailsService` trả vai trò `ROLE_READER`, nên ứng dụng có thể dùng:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").hasRole("READER")
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated())
```

Đây là **đoạn cấu hình thay thế** cho phần authorization của mẫu trên, không phải một chương trình Java độc lập. Với `hasRole("READER")`, Spring Security tìm authority `ROLE_READER`. Không tự cấp tất cả roles cho mỗi username được forward, và không coi client header như `X-Role: ADMIN` là nguồn quyền đáng tin.

Nếu upstream chuyển groups/scopes qua header, chỉ đọc chúng khi hạ tầng đã xác thực, ký/ràng buộc đúng thông tin và ngăn client sửa. Với các quyền quan trọng, ưu tiên kho policy/role của ứng dụng hoặc một cơ chế xác minh claims rõ ràng; thống nhất cách thu hồi và đồng bộ quyền.

### 7.2. Định danh ổn định và phạm vi tenant

`lan` có thể trùng giữa các tổ chức. Nếu gateway có nhiều IdP/tenant, nên định nghĩa principal rõ ràng, ví dụ một ID ổn định được upstream bảo đảm duy nhất trong domain hoặc cặp `issuer + subject`. Không ghép username hiển thị tự do thành primary key dùng phân quyền. Xác minh giới hạn độ dài, charset, Unicode normalization, case folding và danh tính được phép trong hệ thống.

Dù username đã có trong header, việc tra cứu user vẫn phải kiểm tra account đang còn hoạt động, tenant khớp và quyền còn hiệu lực. Đây là **xử lý user data/authorization**, không đồng nghĩa với việc xác minh lại session upstream.

### 7.3. Stateless so với session

Ví dụ dùng `SessionCreationPolicy.STATELESS` để không giữ Authentication qua nhiều request backend. Mỗi request cần được upstream xác thực và chuyển identity. Nếu ứng dụng lại lưu `SecurityContext` vào HTTP session, `AbstractPreAuthenticatedProcessingFilter` có thể bỏ qua xác thực khi đã có principal; lúc người dùng chuyển tài khoản trên SSO nhưng browser còn session cũ, ứng dụng phải chủ động thiết kế cách đồng bộ hoặc hủy session.

Trong chế độ cần session, cân nhắc `setCheckForPrincipalChanges(true)` và xử lý invalidation, cùng với login/logout, session fixation, CSRF và thời gian thu hồi danh tính. Đừng bật cờ đơn lẻ rồi kết luận đã giải quyết mọi trường hợp gateway logout, network race hoặc user switch.

## 8. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Tin mọi `X-Authenticated-User` từ Internet | Client tự đặt tên bất kỳ | Gateway xác thực, strip/overwrite header, chặn kết nối trực tiếp vào backend |
| Cho phép gửi header `admin` là có quyền admin | Header chỉ là chuỗi | Kho user/authorities được quản lý riêng, rules rõ ràng |
| Nghĩ `PreAuthenticatedAuthenticationProvider` sẽ verify JWT/password | Provider chỉ nạp `UserDetails` cho principal đã được coi là xác thực ở upstream | Verify token ở gateway hoặc dùng JwtDecoder/resource server nếu backend tự cần verify |
| Lấy `X-Forwarded-For` hoặc một IP nguồn làm “username đã đăng nhập” | Forwarding/IP không chứng minh cá nhân | Xác thực danh tính thực sự trước khi đặt header |
| Tắt `exceptionIfHeaderMissing` rồi để `permitAll()` cho tất cả routes | Request thiếu header được phép truy cập | Bắt buộc auth cho routes cần bảo vệ và không mở fallback không mong muốn |
| Chỉ bật HTTPS mà không strip header do client gửi | TLS không xác thực nội dung header | Bắt buộc proxy overwrite header từ kết quả auth |
| Dùng session cũ khi upstream đổi user | Principal có thể không được kiểm tra lại | Stateless hoặc thiết kế principal-change/session-invalidation |
| Ghi toàn bộ header vào log | Có thể rò danh tính, token/cookie hoặc PII | Log có cấu trúc, chỉ giữ thông tin vận hành cần thiết |
| Thấy test MockMvc pass và bỏ kiểm thử proxy | MockMvc không có hạ tầng mạng/SSO thực | Kiểm thử end-to-end chống header spoof và direct backend access |

## 9. Checklist đưa vào vận hành

1. Xác định chính xác **ai xác thực upstream** (SSO proxy, auth service, IdP) và điều kiện nào khiến proxy đặt header danh tính.
2. Bảo đảm **100% đường truy cập backend** đều qua proxy và không thể truy cập trực tiếp từ nguồn không tin cậy, kể cả một cổng quản trị hay ingress phụ.
3. Gateway xóa/ghi đè `X-Authenticated-User` và mọi header tương đương do client đưa vào; kiểm tra duplicate, case và các đường request bất thường.
4. Đảm bảo đoạn proxy → backend an toàn: network policy, TLS/mTLS nếu phù hợp, chỉ định upstream có quyền truy cập.
5. Chỉ chấp nhận username có cấu trúc thống nhất, duy nhất trong miền quản lý phù hợp; không chấp nhận giá trị rỗng hoặc giá trị đặc biệt không được kiểm soát.
6. User service chặn tài khoản không tồn tại, disabled, locked, ngoài tenant và không tự cấp quyền vì có header.
7. SecurityFilterChain áp dụng cho đúng routes; mọi tài nguyên cần bảo vệ có rule `authenticated()` / `hasRole(...)`; kiểm tra không có lối bypass qua form/basic login khác.
8. Kiểm tra cookie/session theo vòng đời danh tính upstream. Với API stateless, không dùng lại principal từ session cũ.
9. Test cả Java và network: thiếu header, user không hợp lệ, giả mạo identity, duplicate header, upstream lỗi, thu hồi quyền, direct backend access.
10. Giám sát lỗi pre-auth, user lookup và 403 theo correlation ID; không log bí mật, không đưa chi tiết nội bộ ra HTTP response.

## 10. Tự kiểm tra

**Câu 1.** `RequestHeaderAuthenticationFilter` xác thực mật khẩu của người dùng hay chưa?  
**Trả lời:** Chưa. Nó đọc principal từ header. Việc chứng minh danh tính phải xảy ra ở hệ thống phía trước; provider thường chỉ nạp `UserDetails` và quyền.

**Câu 2.** Vì sao header `X-Authenticated-User: admin` không đáng tin khi xuất hiện từ một kết nối Internet trực tiếp?  
**Trả lời:** Bất cứ client nào cũng có thể tự viết header đó. Phải ngăn backend truy cập trực tiếp và để proxy đã xác thực strip/overwrite header.

**Câu 3.** `exceptionIfHeaderMissing=false` có luôn là lỗi bảo mật không?  
**Trả lời:** Không tự động, nhưng chỉ an toàn khi request thiếu identity vẫn bị chặn ở authorization và không tồn tại nhánh fallback cho phép truy cập. Ví dụ dùng `anyRequest().authenticated()`, 403 entry point và không có cơ chế login khác.

**Câu 4.** Vì sao `UserDetailsByNameServiceWrapper` không thay thế gateway SSO?  
**Trả lời:** Nó chỉ dùng username trong `Authentication` để tra `UserDetails` và authorities; nó không thể biết upstream đã chứng minh danh tính hay chưa.

**Câu 5.** Một request vào backend với username hợp lệ và role hợp lệ có thể vẫn nguy hiểm trong trường hợp nào?  
**Trả lời:** Khi caller tự chọn header hoặc có đường trực tiếp bỏ qua gateway. Khi ấy ứng dụng sẽ “xác thực” một danh tính không hề được chứng minh.

## Tài liệu tham khảo

- [Spring Security 6.5 — Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html): mô hình và vai trò của `RequestHeaderAuthenticationFilter`.
- [Spring Security — RequestHeaderAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/site/docs/6.1.x/api/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): các header, mặc định `SM_USER`, missing-header exception.
- [Spring Security 6.5 — AbstractPreAuthenticatedProcessingFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): `SecurityContext`, continue chain, principal change.
- [Spring Security — PreAuthenticatedAuthenticationProvider Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html): provider chỉ nạp thông tin user, không tự xác thực credentials.
- [Spring Security — UserDetailsByNameServiceWrapper Javadoc](https://docs.spring.io/spring-security/site/docs/6.0.2/api/org/springframework/security/core/userdetails/UserDetailsByNameServiceWrapper.html): ánh xạ tên từ `Authentication` sang `UserDetails`.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): thứ tự và vai trò của các security filters.
