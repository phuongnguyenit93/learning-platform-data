# Pre-authentication và ranh giới tin cậy với proxy xác thực phía trước

## 1. Pre-authentication là gì?

Trong ứng dụng **Spring Security Servlet**, *pre-authentication* là mô hình **một hệ thống đáng tin phía trước đã xác thực người dùng**, còn ứng dụng phía sau tiếp nhận kết quả xác thực để tạo `Authentication` và thực thi các quy tắc phân quyền riêng.

Ví dụ: người dùng truy cập `https://reports.example.com`; reverse proxy hoặc identity-aware gateway kiểm tra phiên đăng nhập OIDC/SAML, sau đó chuyển request đến Spring Boot cùng thông tin danh tính đã được gateway xác nhận. Ứng dụng không trực tiếp kiểm mật khẩu hoặc thực hiện OAuth2 login ở bước đó, nhưng vẫn phải ánh xạ principal sang quyền được phép sử dụng.

**Điểm nguy hiểm nhất:** HTTP header do client gửi vốn có thể bị giả mạo. `X-Verified-User: alice` chỉ có giá trị như bằng chứng danh tính **khi một proxy đáng tin đã xóa header của client, xác thực người dùng thành công rồi tự tạo header mới**, và backend chỉ nhận request từ proxy đó. Nếu client kết nối thẳng tới backend và tự đặt header, pre-authentication có thể biến thành bỏ qua xác thực hoàn toàn.

Hãy phân biệt:

- **Authentication:** ai là caller; gateway có thể làm bước xác thực ban đầu.
- **Pre-authentication:** backend tiếp nhận kết quả xác thực đã được chuyển giao qua ranh giới tin cậy.
- **Authorization:** caller được làm gì trong ứng dụng; Spring Security/backend vẫn phải kiểm tra.
- **Transport trust:** ai được phép gửi kết quả xác thực cho backend, qua đường mạng nào.
- **Identity claims vs network metadata:** `X-Forwarded-Proto` cho biết scheme, không chứng minh ai đã đăng nhập.

Pre-authentication không phải “bật một filter là được”. Đó là hợp đồng bảo mật **giữa browser/client, proxy xác thực, mạng nội bộ và Resource Application**.

## 2. Kiến trúc đúng và kiến trúc có lỗ hổng

### Luồng mong muốn

```text
                 Internet không đáng tin
Browser/Client ------------------------------------+
                                                   |
                              HTTPS               v
                     +-------------------------------+
                     | Identity-aware reverse proxy  |
                     | 1. Xác thực cookie/token       |
                     | 2. Xóa identity headers đầu vào|
                     | 3. Tạo trusted identity header |
                     +-------------------------------+
                                  |
                                  | mạng kín / mTLS
                                  | X-Verified-User: alice
                                  v
                     +-------------------------------+
                     | Spring Boot Servlet          |
                     | RequestHeaderAuthentication  |
                     | Filter -> AuthenticationMgr   |
                     | -> PreAuthenticatedProvider   |
                     | -> app UserDetails/permissions|
                     | -> authorizeHttpRequests      |
                     +-------------------------------+
                                  |
                                  v
                            Controller/API
```

Nếu proxy từ chối phiên đăng nhập, request **không được chuyển tiếp** cho backend như một request đã xác thực. Nếu proxy xác thực thành công nhưng không thể thiết lập danh tính rõ ràng, phải **fail closed**: không gán principal mặc định, không lấy identity từ header client trước đó.

### Luồng tấn công khi backend bị lộ

```http
GET /api/reports HTTP/1.1
Host: internal-app.example.com
X-Verified-User: admin
```

Nếu backend công khai và dùng `RequestHeaderAuthenticationFilter` để tin trực tiếp `X-Verified-User`, attacker có thể tự nhận là `admin`. **HTTPS của request này không giúp kiểm tra tính đúng đắn của header**; TLS chỉ bảo vệ kết nối đến server mà attacker vừa gọi.

Những câu hỏi phải trả lời trước khi dùng pre-authentication:

1. Backend có thể bị gọi trực tiếp ngoài proxy không?
2. Ai được phép đặt `X-Verified-User` hoặc header tương đương?
3. Proxy có xóa **mọi biến thể** của identity header từ client trước khi gắn giá trị đã xác minh không?
4. Proxy xác thực bằng gì (session OIDC, mTLS, JWT đã kiểm tra, SSO…)?
5. Application lấy roles/scopes từ nguồn nào và giới hạn quyền theo tenant ra sao?
6. Khi proxy/auth service gặp lỗi, request bị từ chối hay vẫn đi qua?

## 3. Spring Security có những thành phần nào?

Trong mô hình Servlet pre-authentication theo request header, có thể gặp:

| Thành phần | Chức năng | Lưu ý an toàn |
| --- | --- | --- |
| `RequestHeaderAuthenticationFilter` | Đọc principal (và tùy chọn credentials) từ một header do hệ thống phía trước gắn | **Không tự xác minh** proxy hoặc user |
| `AbstractPreAuthenticatedProcessingFilter` | Nền tảng cho các filter tiếp nhận danh tính đã xác thực ở nguồn khác | Cần `AuthenticationManager` phù hợp |
| `PreAuthenticatedAuthenticationToken` | Chở principal và credentials qua chuỗi authentication | Không phải JWT và không chứng minh header đáng tin |
| `PreAuthenticatedAuthenticationProvider` | Dùng `AuthenticationUserDetailsService` để lấy `UserDetails` và authorities | Chỉ đặt sau ranh giới tin cậy |
| `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` | Tra cứu/ánh xạ danh tính từ token pre-auth sang user/roles được backend công nhận | Tránh tự tin mọi role từ client |
| `SecurityContext` | Chứa `Authentication` cho request đang xử lý | Phải kiểm soát session/caching nếu danh tính có thể đổi |
| `SecurityFilterChain` | Gắn filter, phân quyền URL và xử lý lỗi | Rule vẫn phải từ chối thiếu hoặc thiếu quyền |

`RequestHeaderAuthenticationFilter` không giống `BearerTokenAuthenticationFilter`: filter thứ hai lấy bearer token để hệ thống Resource Server kiểm chứng JWT hoặc introspect opaque token, còn request-header pre-auth **dựa vào một hệ thống phía trước đã xác thực**. Đừng dùng `RequestHeaderAuthenticationFilter` như cách “giải mã JWT từ header” — nó không làm việc đó.

Tương tự, cơ chế pre-auth dựa vào thông tin client certificate hoặc Java EE container principal có các filter/adapter riêng; danh tính lấy từ **certificate đã xác thực bởi TLS stack** khác với một header text tên `X-Client-Cert` do client bất kỳ gửi.

## 4. Ranh giới tin cậy của HTTP header

Một request header bình thường là dữ liệu **do bên gọi tự cung cấp**. Để nâng nó thành identity assertion, cần có **nguồn phát hành đáng tin và kênh truyền đã khóa**.

Có thể mô tả bất biến của kiến trúc:

```text
Backend chỉ tin X-Verified-User khi:
  caller mạng = proxy đáng tin
  AND proxy đã thực thi authentication
  AND proxy đã xóa/ghi đè header client cung cấp
  AND giá trị header do proxy xây dựng từ kết quả xác thực
  AND backend vẫn kiểm tra user/quyền theo chính sách app.
```

Nếu một mệnh đề không đúng, việc tin header có thể thành lỗ hổng.

**Đặc biệt không dùng `X-Forwarded-For` làm bằng chứng người dùng.** Header đó mô tả chuỗi địa chỉ mạng và chỉ đáng tin khi đã được proxy chuẩn hóa đúng. `X-Forwarded-Proto: https` cũng không phải dấu xác thực danh tính. Giá trị `request.getRemoteAddr()` có thể bị thay đổi bởi một số cơ chế xử lý forwarded headers; nếu dùng nó để xác nhận *peer* thật thì cần hiểu cấu hình container/proxy, hoặc tốt hơn là enforce ở firewall/network policy và mTLS.

Khi có nhiều tầng CDN, load balancer, ingress, API gateway, hãy chỉ rõ tầng nào xác thực user và tầng nào là **nguồn sự thật** về identity header. Một gateway ngoài xác thực đúng nhưng một gateway bên trong vô tình giữ lại header của client vẫn có thể làm hỏng bảo mật.

## 5. Ví dụ Spring Boot 3.3.x, Java 17+, Spring Security Servlet

Đây là ví dụ học tập gồm API chỉ đọc để minh họa `RequestHeaderAuthenticationFilter` và `PreAuthenticatedAuthenticationProvider`. Để chạy local, backend chỉ bind vào loopback `127.0.0.1`. **Không coi việc truy cập loopback là bằng chứng header được xác thực**: tiến trình trên cùng máy vẫn có thể tự đặt header. Trong production, phải đưa ứng dụng sau proxy xác thực có kiểm soát mạng, không công bố cổng backend và dùng identity store/permission nghiệp vụ thật.

### 5.1. Cấu trúc dự án

```text
preauth-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/preauth/
    │   │   ├── PreAuthApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ReportController.java
    │   └── resources/application.yml
    └── test/java/demo/preauth/PreAuthIntegrationTest.java
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

Trong ứng dụng này, address loopback giúp tránh truy cập từ mạng ngoài vào backend trên cùng host. Nếu chạy qua Kubernetes/network namespace khác, phải dùng network policy/service binding tương ứng chứ không thể áp nguyên giá trị loopback.

Tạo `src/main/java/demo/preauth/PreAuthApplication.java`:

```java
package demo.preauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PreAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(PreAuthApplication.class, args);
    }
}
```

### 5.2. Cấu hình pre-authentication và quyền

Tạo `src/main/java/demo/preauth/SecurityConfig.java`:

```java
package demo.preauth;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationManager preAuthManager() {
        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();

        provider.setPreAuthenticatedUserDetailsService(token -> {
            String name = String.valueOf(token.getPrincipal());

            // Dữ liệu học tập: thay bằng identity/tenant store của ứng dụng.
            UserDetails user = switch (name) {
                case "alice" -> User.withUsername("alice")
                        .password("{noop}unused")
                        .authorities("REPORT_READ")
                        .build();
                case "admin" -> User.withUsername("admin")
                        .password("{noop}unused")
                        .authorities("REPORT_READ", "REPORT_ADMIN")
                        .build();
                default -> throw new UsernameNotFoundException(
                        "Unknown pre-authenticated principal");
            };
            return user;
        });

        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager preAuthManager)
            throws Exception {

        RequestHeaderAuthenticationFilter preAuthFilter =
                new RequestHeaderAuthenticationFilter();
        preAuthFilter.setPrincipalRequestHeader("X-Verified-User");
        // Thiếu header => không có principal, để authorization từ chối.
        preAuthFilter.setExceptionIfHeaderMissing(false);
        preAuthFilter.setAuthenticationManager(preAuthManager);
        preAuthFilter.setCheckForPrincipalChanges(true);

        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/health")
                                .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports")
                                .hasAuthority("REPORT_READ")
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                                .hasAuthority("REPORT_ADMIN")
                        .anyRequest().denyAll())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((request, response, error) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .addFilterAt(preAuthFilter,
                        AbstractPreAuthenticatedProcessingFilter.class)
                .build();
    }
}
```

**Giải thích từng quyết định:**

1. `RequestHeaderAuthenticationFilter` **chỉ đọc** `X-Verified-User`. Không có chữ ký hoặc kiểm tra nguồn header ở lớp này, nên proxy và network boundary là điều kiện bắt buộc.
2. `setExceptionIfHeaderMissing(false)` khiến header thiếu không tự ném lỗi ngay tại bước đọc; request không được xác thực và các rule protected sẽ từ chối. Với `authenticationEntryPoint` ở trên, các đường dẫn yêu cầu authentication thường trả `401`.
3. `PreAuthenticatedAuthenticationProvider` lấy user details theo tên do proxy đã xác thực. Demo cho phép `alice` đọc báo cáo, còn `admin` có thêm quyền quản trị. **Không đọc `X-Role` do client tự gắn** để cấp `REPORT_ADMIN`.
4. `SessionCreationPolicy.STATELESS` làm ví dụ tái xác thực từ request mỗi lần, tránh giữ một user được xác thực trong HTTP session khi proxy identity đã đổi. Nếu ứng dụng production dùng session, phải thiết kế kỹ cách đồng bộ logout, principal changes và session fixation.
5. Filter được tạo **bên trong `SecurityFilterChain`**, không khai báo là một `@Bean Filter` riêng. Cách này tránh Spring Boot vô tình auto-register filter thêm một lần ngoài security chain.
6. `.addFilterAt(..., AbstractPreAuthenticatedProcessingFilter.class)` đặt filter tại vị trí pre-auth trong chuỗi security. Với project có nhiều `SecurityFilterChain`, phải bảo đảm đúng chain áp dụng và tránh đăng ký cùng filter nhiều lần.
7. `anyRequest().denyAll()` giúp chỉ mở các URL được thiết kế rõ. Đây không phải cấu hình cho tất cả ứng dụng, mà là chính sách tối thiểu của demo.
8. `password("{noop}unused")` chỉ thỏa cấu trúc `UserDetails` demo; **không dùng password này để login**, vì không có username/password authentication trong flow.

Điểm quan trọng: ứng dụng này chỉ an toàn khi **header nhận vào thực sự do proxy đáng tin tạo**. Bản thân `SecurityConfig` không thể chứng minh điều đó, nên không công khai cổng 8080 ra Internet.

### 5.3. Controller kiểm tra principal và authorities

Tạo `src/main/java/demo/preauth/ReportController.java`:

```java
package demo.preauth;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/reports")
    public Map<String, Object> reports(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return Map.of(
                "principal", authentication.getName(),
                "authorities", authorities);
    }

    @GetMapping("/api/admin")
    public Map<String, Boolean> admin() {
        return Map.of("allowed", true);
    }
}
```

Controller không trả raw header, cookie hoặc access token. Nó sử dụng `Authentication` đã được Spring Security đặt vào security context. Trong production nên tránh công khai toàn bộ authorities cho caller; endpoint `/api/reports` này chỉ phục vụ demo.

## 6. Chạy ứng dụng và đọc kết quả cho đúng

Chạy bằng Gradle wrapper đã có của dự án:

```bash
./gradlew bootRun
```

Trên Windows PowerShell dùng `.\gradlew.bat bootRun`.

Gọi endpoint không yêu cầu xác thực:

```bash
curl -i http://127.0.0.1:8080/api/health
```

Đáp ứng thành công có HTTP 200 và JSON tương đương:

```json
{"status":"ok"}
```

Gọi reports **không có header pre-auth**:

```bash
curl -i http://127.0.0.1:8080/api/reports
```

Mong đợi response `401 Unauthorized` trong cấu hình demo.

Gọi reports với **header giả lập**:

```bash
curl -i http://127.0.0.1:8080/api/reports \
    -H "X-Verified-User: alice"
```

Trong bản demo local, bạn sẽ thấy HTTP 200 với JSON tương đương:

```json
{
  "principal": "alice",
  "authorities": ["REPORT_READ"]
}
```

**Cảnh báo thiết yếu:** chính việc `curl` trên cùng máy tự giả header mà vẫn được xác thực cho thấy **pre-auth filter không kiểm tra danh tính**. Chỉ cấu hình proxy và giới hạn kết nối trực tiếp mới biến header thành identity assertion đáng tin. Không dùng đường gọi trực tiếp trên trong production.

Kiểm tra thiếu quyền:

```bash
curl -i http://127.0.0.1:8080/api/admin \
    -H "X-Verified-User: alice"
```

Mong đợi HTTP `403 Forbidden` vì `alice` đã được nhận diện nhưng thiếu `REPORT_ADMIN`. Ngược lại, `X-Verified-User: admin` trong demo sẽ đi qua rule này, nhấn mạnh rằng **bất kỳ client nào có quyền trực tiếp gắn header vào backend đều có thể giả `admin`**.

## 7. Kiểm thử Java 17+ bằng MockMvc

Tạo `src/test/java/demo/preauth/PreAuthIntegrationTest.java`:

```java
package demo.preauth;

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
class PreAuthIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noIdentityHeaderMeansUnauthenticated() throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void trustedIdentityIsMappedToApplicationPermission()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .header("X-Verified-User", "alice"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal").value("alice"))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("REPORT_READ"));
    }

    @Test
    void knownUserWithoutAdminPermissionIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin")
                        .header("X-Verified-User", "alice")
                        .header("X-Verified-Role", "ADMIN"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unknownPrincipalIsNotAutomaticallyTrusted()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .header("X-Verified-User", "mallory"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminPermissionComesFromApplicationUserDetails()
            throws Exception {
        mvc.perform(get("/api/admin")
                        .header("X-Verified-User", "admin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.allowed").value(true));
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test xác nhận việc **chuyển header thành principal** và ánh xạ permission theo ứng dụng; chúng **không chứng minh proxy đã thật sự xác thực người dùng**. MockMvc cố ý cho phép bạn giả lập header để kiểm thử filter. Cần kiểm thử xuyên suốt tại ingress/proxy: request từ Internet có tự đặt `X-Verified-User: admin` nhưng không có credential hợp lệ vẫn phải bị chặn.

## 8. Ví dụ ở reverse proxy: xác thực trước khi gắn header

Một hệ thống có thể dùng Nginx `auth_request` để hỏi một dịch vụ xác thực nội bộ. Đoạn dưới **chỉ là các `location` trong HTTPS `server` block đã cấu hình certificate và proxy đáng tin**, không phải file Nginx đầy đủ.

```nginx
# Mọi request /api/ phải được auth service cho phép trước.
location /api/ {
    auth_request /_verify_identity;
    auth_request_set $verified_user $upstream_http_x_verified_user;

    # Ghi đè header client tự gửi bằng kết quả auth subrequest.
    proxy_set_header X-Verified-User $verified_user;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_pass http://127.0.0.1:8080;
}

# Nginx gọi nội bộ; Internet client không gọi trực tiếp location này.
location = /_verify_identity {
    internal;
    proxy_pass http://127.0.0.1:8081/verify;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Authorization $http_authorization;
}
```

Để mô hình hoạt động đúng:

1. Auth service ở `127.0.0.1:8081/verify` thực sự kiểm chứng session hoặc bearer token, **không** chỉ echo một identity header do client gửi.
2. Khi thành công, auth service trả `2xx` và header **do chính nó tạo** `X-Verified-User: <principal đã xác minh>`. Với unauthenticated request, nó trả `401` hoặc `403`, không cấp user.
3. Nginx `auth_request` chỉ forward request vào ứng dụng khi xác thực của subrequest thành công. `auth_request_set` lấy identity từ response của auth service; `proxy_set_header` thay giá trị header nhận từ client. Nếu không có tên user hợp lệ, backend không nên cấp quyền.
4. Cổng 8080 **không được mở trực tiếp cho Internet**; ví dụ cùng host dùng loopback. Với nhiều container/host, dùng mạng nội bộ giới hạn nguồn kết nối, firewall/network policy hoặc mTLS.
5. Cần kiểm tra **header trùng lặp/alias** và cách proxy chuẩn hóa tên header. Không chấp nhận hai giá trị mâu thuẫn rồi “lấy đại giá trị đầu tiên”.
6. Cơ chế `auth_request` của bản Nginx được triển khai phải khả dụng; cách cấu hình proxy auth khác (ingress external auth, Envoy ext_authz, API gateway) có contract tương tự.

Chính sách đóng khi lỗi: auth service unreachable/timeout hoặc trả response không hợp lệ phải làm request thất bại; **không có fallback** “proxy vẫn cho qua nếu auth server lỗi”. Sau khi auth thành công, proxy phải kiểm soát cả header tên user, tenant và role theo whitelist được duyệt.

## 9. Cách diễn giải danh tính an toàn trong backend

Một identity assertion hữu ích có thể có:

```text
X-Verified-User: user-42
X-Verified-Tenant: tenant-acme
```

Tuy nhiên, **hai header vẫn không thay thế được kiểm tra nghiệp vụ**:

- Nếu token/session được xác minh thuộc tenant `A`, proxy không được cho client tự chọn `X-Verified-Tenant: B`.
- Backend phải tra cứu principal và kiểm tra user có còn hoạt động, thuộc tenant nào, role nào, được thao tác tài nguyên nào.
- Những quyền như `REPORT_ADMIN` tốt nhất lấy từ authority store được backend kiểm soát hoặc một assertion **có ký/được truyền qua kênh xác thực mạnh** và đã thẩm định đúng audience.
- ID ổn định (`sub`/subject có namespace issuer) thường phù hợp hơn display name hoặc email có thể thay đổi.
- Nếu có nhiều identity providers, định danh user nên gắn với **issuer + subject**; cùng chuỗi `"alice"` từ hai issuer không mặc nhiên là cùng người.

Tùy yêu cầu compliance, bạn có thể chọn **ủy quyền hoàn toàn cho gateway** (backend tin assertion về user và roles đã kiểm chứng) hoặc **ủy quyền một phần** (gateway xác thực, backend quyết định quyền). Trong cả hai trường hợp, backend cần biết **nguồn assertion nào được phép cấp quyền gì**.

Ví dụ những thông tin nên giữ lại trong log audit nội bộ: correlation ID, principal ID sau chuẩn hóa, issuer/tenant ID đã xác thực, route, kết quả quyền, proxy ID, mã lỗi. Không log cookie, bearer token, private claims hoặc toàn bộ authentication header.

## 10. Tấn công và lỗi triển khai phổ biến

| Nguy cơ / biểu hiện | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| Người lạ gửi `X-Verified-User: admin` và truy cập được | Backend exposed hoặc proxy giữ header client | Chặn truy cập backend trực tiếp; proxy xóa/ghi đè mọi identity headers |
| Auth service timeout nhưng request vẫn qua | Gateway fail-open | Fail closed, theo dõi 5xx và chặn nếu không có identity assertion |
| User đã logout vẫn vào API | Session/cookie ở gateway còn hiệu lực hoặc backend tái dùng SecurityContext cũ | Thống nhất session revocation, request-level authentication, timeout |
| User A được quyền của user B | Cache/security context giữ danh tính giữa request, mapping principal sai | Stateless hoặc kiểm tra thay đổi principal; scope cache theo user/tenant |
| Có header user nhưng app trả 401 | Không nhận được header, principal không tồn tại, sai tên header | Kiểm tra proxy upstream header, user-details lookup và entry point |
| Có principal nhưng app trả 403 | Thiếu authority của tài nguyên | Kiểm tra `GrantedAuthority`, quyền object/tenant, không tự mở role |
| Proxy gắn `X-Verified-Role: ADMIN` từ client | Không tách chứng cứ xác thực khỏi metadata tùy ý | Role từ backend store hoặc assertion đã xác thực |
| Application tin `X-Forwarded-For` làm source IP thật | Header bị spoof hoặc có nhiều tầng proxy | Tin IP ở network boundary/proxy thực sự, không dùng header tùy ý |
| Hai header với tên khác chữ hoa/thường | Normalization và duplicate handling không thống nhất | Chuẩn hóa tại edge, chỉ gửi một assertion duy nhất |
| Header identity chứa dấu phẩy/ký tự lạ | Chuỗi nhiều giá trị hoặc injection | Quy định encoding, chiều dài, kiểm tra định dạng và reject ambiguities |
| App chạy sau ingress nhưng backend service là public | Sai policy của LoadBalancer/Ingress/firewall | Kiểm tra network exposure từ bên ngoài, không chỉ tài liệu kiến trúc |
| Gateway tin token sai audience/issuer | Xác thực upstream chưa đúng contract | Validate signature, issuer, audience, expiry, token type tại auth service |

Một lỗi đặc biệt nguy hiểm là đặt cùng một header trên request từ Internet và từ proxy nội bộ, sau đó thử phân biệt theo một biến `X-Forwarded-For`. Kẻ tấn công cũng có thể tạo giá trị này. Quy tắc hợp lệ phải dựa vào **kênh đã kiểm soát và nguồn gắn identity assertion**, không dựa vào dấu hiệu dễ giả.

## 11. Mối liên hệ với session, CSRF và CORS

**Session:** hệ thống pre-auth có thể tạo Spring Security session trong một số cấu hình. Nếu header xác thực thay đổi từ user A sang user B nhưng session cũ vẫn giữ `Authentication`, ứng dụng có thể gán nhầm danh tính. Demo chọn `SessionCreationPolicy.STATELESS` để xác thực từng request. Với ứng dụng session-based thật, cần kiểm tra principal changes, session invalidation và đồng bộ logout với gateway.

**CSRF:** nếu frontend sử dụng cookie session tự động được trình duyệt gửi đến gateway, các request ghi dữ liệu vẫn có thể chịu rủi ro CSRF. CORS chỉ hạn chế JavaScript đọc response cross-origin, **không thay thế CSRF protection**. Đừng tắt CSRF toàn cục chỉ vì proxy đã đăng nhập user. Ví dụ demo chỉ dùng GET, không hủy CSRF.

**CORS:** một preflight `OPTIONS` có thể không mang cookie/session hoặc không đi qua authorization flow như request thực. Cần đặt chính sách CORS và gateway auth đúng thứ tự cho endpoint thực tế, không tự cấp identity từ header ngoài để “làm OPTIONS chạy được”.

**HTTPS:** proxy xác thực phải dùng TLS cho client; đoạn proxy → backend cũng cần kiểm soát, có thể dùng mTLS/re-encryption khi không ở cùng trust zone. Header identity đi trên HTTP trong mạng mở có thể bị quan sát, thay đổi hoặc replay.

**Caching:** proxy/CDN không được cache response riêng của user rồi phân phát cho user khác. Vary/cache-control phải được thiết kế theo user/credential khi endpoint chứa dữ liệu cá nhân.

## 12. So sánh với các giải pháp xác thực khác

| Kiểu tích hợp | Ai xác thực danh tính? | Khi nào nên cân nhắc |
| --- | --- | --- |
| Pre-auth + trusted header | Identity proxy/gateway phía trước | Backend nằm trong mạng tin cậy, cần tích hợp với SSO/proxy sẵn có |
| `oauth2Login()` | Spring Security application tham gia OAuth2/OIDC authorization code flow | Web application muốn tự quản lý login/session OIDC |
| `oauth2ResourceServer().jwt()` | Backend tự xác minh access token JWT từ client/proxy | API cần tính độc lập, không muốn tin header text |
| Opaque token introspection | Backend hỏi authorization server để xác minh token | Provider dùng opaque token hoặc cần trạng thái token online |
| Servlet container mTLS/X.509 pre-auth | TLS stack đã kiểm tra certificate và cung cấp peer identity | Mạng nội bộ/server-to-server với chứng chỉ client tin cậy |

Nếu backend không thể khóa direct access, tốt hơn nên **xác minh một bearer token hoặc identity assertion được ký** trong chính backend, theo issuer/audience/expiration/revocation, thay vì tin `X-Verified-User`. Nếu cần truyền thông tin user từ gateway qua nhiều trust zones, mTLS hoặc signed short-lived assertion có phạm vi riêng thường vững chắc hơn header thuần không xác thực.

**Không chuyển bearer access token của browser vào `X-Verified-User` rồi coi như principal hợp lệ**: chuỗi token cần được validate theo contract. Nếu gateway đã validate, cần đánh giá tiêu chuẩn để backend có thể tin quyết định đó; nếu chưa validate, dùng Resource Server.

## 13. Kiểm thử xuyên suốt ranh giới proxy

Unit/MockMvc test chỉ chứng minh code ánh xạ identity thành authorities. Bảo mật pre-auth cần **negative tests từ phía Internet**, ví dụ:

1. Không đăng nhập; gửi `X-Verified-User: admin` ở request public. Gateway phải trả `401/403`, backend không được phục vụ nội dung.
2. Đăng nhập như `alice`; cố gắn `X-Verified-User: admin` hoặc `X-Verified-Role: REPORT_ADMIN`. Backend vẫn phải nhận diện `alice` với chỉ quyền được cấp từ nguồn đáng tin.
3. Gửi identity header hai lần, khác casing hoặc alias. Proxy phải loại bỏ/chuẩn hóa và từ chối trường hợp mơ hồ theo chính sách.
4. Gọi trực tiếp vào port backend từ máy ngoài. Kết nối phải bị từ chối ở network boundary, không chỉ gặp lỗi Security của Spring.
5. Auth service down/timeout/5xx. Proxy không được fail-open.
6. User bị khóa, logout hoặc mất role ngay trước request tiếp theo. Backend không được dùng session/cache cũ để tiếp tục cấp quyền.
7. Thay issuer/tenant của assertion trong mô hình nhiều domain. Không thể dùng identity tương tự để vượt quyền sang tenant khác.
8. Các request ghi dữ liệu vẫn tuân thủ CSRF/idempotency/authorization; preflight không vô tình được xem là login.
9. Header `Host`, `Forwarded`/`X-Forwarded-*` giả từ Internet không thay đổi authority hay canonical URL ngoài ý muốn.
10. Theo dõi log đầy đủ correlation ID giữa proxy/auth service/backend nhưng không chứa credential.

Một bài test có thể dùng `curl` qua **public HTTPS proxy** như sau:

```bash
curl -i https://reports.example.com/api/admin \
  -H "X-Verified-User: admin" \
  -H "X-Verified-Role: REPORT_ADMIN"
```

Nếu request **không có credential xác thực hợp lệ**, kết quả **phải là từ chối**; không thể dự đoán chính xác 401 hay 403 nếu chưa biết cấu hình gateway. Endpoint ví dụ không tồn tại tại hostname minh họa, nên câu lệnh trên là kịch bản kiểm thử cần thay bằng public host của hệ thống thật.

## 14. Phân biệt “đã xác thực” với “được phân quyền”

Một identity proxy có thể xác minh user `"alice"` rất chính xác, nhưng điều đó **không tự cho phép** user đọc mọi tài nguyên. Spring Security vẫn cần:

```java
.requestMatchers(HttpMethod.GET, "/api/reports")
.hasAuthority("REPORT_READ")
```

Với ứng dụng đa tenant, `REPORT_READ` có thể chỉ cho phép đọc reports của **tenant thuộc user**. Hãy kiểm tra ownership ở tầng service/database; authority tổng quát không phải một xác nhận user được đọc object ID bất kỳ.

Nên tránh diễn giải role qua header text tự do như:

```text
X-Verified-User: alice
X-Verified-Roles: ADMIN,SUPERUSER
```

Nếu thực sự cần role do identity provider cấp, proxy phải xác thực và chuẩn hóa role cùng scope/issuer/audience, backend phải giới hạn tập role được công nhận. Thực tế nhiều sản phẩm chọn chỉ chuyển **subject ID bất biến** và để backend tra cứu permissions theo dữ liệu nghiệp vụ, nhất là khi role thay đổi thường xuyên.

## 15. Checklist trước khi triển khai

- Proxy hoặc identity gateway thật sự thực thi authentication cho mọi request tới vùng được bảo vệ.
- Mọi identity headers đến từ Internet bị **xóa/ghi đè**, kể cả header trùng và biến thể tên.
- Backend không thể bị truy cập trực tiếp bên ngoài proxy (firewall, internal load balancer, Kubernetes NetworkPolicy, mTLS…).
- Kênh proxy → app có tính toàn vẹn/bảo mật tương xứng với dữ liệu identity.
- Có hợp đồng rõ `X-Verified-User` chứa ID nào, định dạng/độ dài, cách phân biệt issuer/tenant.
- `RequestHeaderAuthenticationFilter` chỉ đặt trong filter chain thích hợp, không đăng ký Servlet filter ngoài ý muốn.
- `PreAuthenticatedAuthenticationProvider` ánh xạ đúng user từ nguồn đáng tin; unknown user bị từ chối.
- `Authentication` được tạo theo đúng request, logout và principal changes không gây reuse sai danh tính.
- Authorization được kiểm tra riêng theo endpoint và object/tenant; không tin role client tự gửi.
- CSRF/CORS/session/HSTS/cache vẫn được cấu hình độc lập; không tắt bảo vệ chỉ để chạy qua proxy.
- Có test spoof header, direct access, auth-service down, stale session, duplicate identity, role escalation.
- Log/metric/audit không ghi cookie, bearer token, raw identity assertion chứa thông tin nhạy cảm.

## Ghi nhớ

Spring Security pre-authentication **không xác thực lại người dùng** bằng một HTTP header; nó tiếp nhận **kết quả xác thực đã được hệ thống phía trước chứng minh**. `RequestHeaderAuthenticationFilter` đọc principal, `PreAuthenticatedAuthenticationProvider` biến principal ấy thành một `Authentication` có authorities, còn SecurityFilterChain quyết định quyền truy cập. Thiết kế chỉ an toàn khi **proxy là nguồn identity duy nhất đáng tin, request từ Internet không thể giả header và backend không thể bị gọi vòng qua proxy**. Khi không bảo đảm được ranh giới này, hãy để backend tự kiểm chứng token/assertion hoặc dùng một kênh xác thực mạnh thay thế.