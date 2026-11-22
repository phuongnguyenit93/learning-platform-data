# OAuth2AuthorizedClientManager và gọi API được bảo vệ từ ứng dụng Spring Security Servlet

## 1. Bài toán: ứng dụng Servlet phải gọi một API cần OAuth 2.0 access token

Một ứng dụng Spring Boot sử dụng **Spring Security Servlet** có thể vừa phục vụ trình duyệt vừa đóng vai trò **OAuth 2.0 Client** khi gọi API ở hệ thống khác. Giả sử:

- Người dùng đăng nhập vào ứng dụng web và muốn xem hồ sơ của chính mình từ `https://resource.example.test/users/me`. Yêu cầu này dùng **quyền ủy quyền của người dùng**, thường qua `authorization_code` (và `refresh_token` khi được cấp).
- Ứng dụng tự đồng bộ báo cáo với `https://resource.example.test/reports`, không cần người dùng ủy quyền từng lần. Yêu cầu này có thể dùng **`client_credentials`** để lấy token cho danh tính ứng dụng.
- API đích (resource server) xác thực `Authorization: Bearer <access-token>` và kiểm tra scope/audience/quyền. Ứng dụng đang gọi API là *client*, không được mặc định coi mình là resource server chỉ vì phải xử lý access token để gọi ra ngoài.

Để quản lý việc chọn đăng ký OAuth client, lấy token, dùng lại token còn hạn, làm mới hoặc cấp lại token khi hợp lệ và lưu trạng thái authorized client, Spring Security cung cấp **`OAuth2AuthorizedClientManager`**.

### Các thành phần và vai trò

| Thành phần | Trách nhiệm |
| --- | --- |
| `ClientRegistration` | Mô tả OAuth client: `registrationId`, client ID/secret, grant type, authorization/token URI, scope... |
| `ClientRegistrationRepository` | Tra cứu các `ClientRegistration` theo `registrationId`, ví dụ `user-api` hoặc `report-api` |
| `OAuth2AuthorizedClient` | Kết hợp `ClientRegistration`, tên principal và access token (có thể có refresh token) đã được cấp |
| `OAuth2AuthorizedClientRepository` | Lưu/đọc authorized client theo request/response Servlet và principal, thường gắn với phiên/trạng thái web |
| `OAuth2AuthorizedClientService` | Lưu/đọc authorized client theo client registration ID và principal name, không phụ thuộc Servlet request |
| `OAuth2AuthorizedClientProvider` | Thực thi các cơ chế `authorization_code`, `refresh_token`, `client_credentials`... được bật |
| `OAuth2AuthorizedClientManager` | Điều phối provider, kho lưu và chu kỳ cấp/đổi token qua `authorize(...)` |
| `RestClient`/`WebClient`/`RestTemplate` | Gửi HTTP tới API đích; access token phải được gắn vào request đúng cách |

**`OAuth2AuthorizedClient` không đồng nghĩa `Authentication`**: `Authentication` biểu diễn người dùng/service đã xác thực **tại ứng dụng**, còn authorized client biểu diễn OAuth 2.0 token đã cấp cho một client và principal để gọi **tài nguyên bên ngoài**. Có một principal hợp lệ không đảm bảo đã có quyền đối với mọi API đích.

## 2. Cơ chế của OAuth2AuthorizedClientManager

API trung tâm của interface là:

~~~java
OAuth2AuthorizedClient authorizedClient =
    authorizedClientManager.authorize(authorizeRequest);
~~~

Đây là **trích đoạn trong ứng dụng đã có bean/config phù hợp**, không phải file Java độc lập. `OAuth2AuthorizeRequest` nêu ít nhất `clientRegistrationId` và `principal`; các thuộc tính bổ sung có thể cung cấp thông tin request hoặc tham số grant khi cần.

Luồng tổng quát:

~~~text
Controller / Service / HTTP client interceptor
               │
               │ OAuth2AuthorizeRequest(registrationId, principal)
               ▼
       OAuth2AuthorizedClientManager
               │
               ├─ Tìm ClientRegistration phù hợp
               ├─ Đọc OAuth2AuthorizedClient hiện có theo principal + registration
               ├─ Hỏi OAuth2AuthorizedClientProvider có cần/có thể cấp token?
               │     ├─ access token còn hạn → có thể dùng lại
               │     ├─ token gần/hết hạn + refresh token → thử refresh_token
               │     ├─ client_credentials → lấy access token mới khi cần
               │     └─ thiếu điều kiện grant → chưa thể authorize
               ├─ Lưu authorized client sau khi cấp/đổi token thành công
               └─ Trả OAuth2AuthorizedClient (có thể null)
               │
               ▼
  HTTP request: Authorization: Bearer <access-token>
               │
               ▼
   Resource Server kiểm tra token và quyền
~~~

Những điểm phải hiểu đúng:

1. **`authorize(...)` không có nghĩa luôn gửi network request đến authorization server.** Manager/provider có thể sử dụng authorized client và access token còn hạn, hoặc xác định chưa cần làm gì.
2. **Kết quả có thể `null`** nếu không có authorized client phù hợp và các provider đang cấu hình không thể cấp mới trong tình huống đó. Không truy cập `getAccessToken()` mà không kiểm tra kết quả.
3. **Grant type cần provider tương ứng.** Một manager chỉ bật `clientCredentials()` sẽ không làm mới token bằng `refresh_token` của user, và ngược lại.
4. **Quá trình `authorization_code` tương tác với browser** diễn ra qua redirect tới authorization server rồi callback, do security filters và ứng dụng cấu hình. Không nên giả định chỉ gọi `manager.authorize(...)` sẽ tự hiển thị consent/redirect cho một user chưa ủy quyền.
5. **Các lỗi mạng, cấu hình và OAuth2** có thể làm `authorize(...)` ném exception; client phải có chính sách xử lý lỗi, timeout và retry thích hợp. Không vô hạn retry khi client secret sai hoặc consent bị thu hồi.

## 3. Chọn đúng manager theo ngữ cảnh

Có hai triển khai phổ biến, cùng dùng interface `OAuth2AuthorizedClientManager` nhưng có ranh giới vận hành khác nhau.

| Tiêu chí | `DefaultOAuth2AuthorizedClientManager` | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| --- | --- | --- |
| Môi trường hướng tới | Có `HttpServletRequest`/`HttpServletResponse` trong luồng request Servlet | Ngoài HTTP request: job, background worker, message consumer; cũng dùng được trong Servlet |
| Nơi lưu | `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientService` |
| Ngữ cảnh principal | Thường người dùng đang đăng nhập và phiên web | Tên principal/service do ứng dụng cung cấp |
| Grant hay dùng | `authorization_code` + `refresh_token` cho người dùng | `client_credentials` cho ứng dụng hoặc grant phù hợp trong background |
| Sai lầm thường gặp | Dùng trong thread chạy `@Scheduled` không có Servlet request | Dùng chung một principal cố định cho token của nhiều user khác nhau |

**Quy tắc:** với request từ trình duyệt đã ủy quyền, dùng manager có repository tương ứng Servlet. Với token service-to-service cần dùng trong scheduled job, chọn service manager, không dựa vào phiên trình duyệt.

Tên principal góp phần xác định authorized client được lưu. Dùng một tên như `reporting-service` cho `client_credentials` có thể hợp lý vì token đại diện cho ứng dụng; **không dùng chung tên đó để lưu access token cấp riêng cho từng người dùng**.

### Repository khác Service như thế nào?

- `OAuth2AuthorizedClientRepository` có API lấy/lưu/xóa với request, response và `Authentication`. Một cấu hình có thể lưu trong session hoặc ủy quyền cho service theo trạng thái principal.
- `OAuth2AuthorizedClientService` có API truy cập theo `clientRegistrationId` và `principalName`, không yêu cầu Servlet request. Spring Boot có thể cung cấp implementation in-memory theo cấu hình; với môi trường nhiều node, restart và yêu cầu bền vững cần đánh giá persistence chia sẻ, cơ chế mã hóa và quy trình thu hồi.
- Lưu token không đảm bảo token luôn hợp lệ: phía resource server vẫn quyết định signature/introspection, expiry, audience, scopes và policy tại thời điểm gọi.

## 4. Chuẩn bị dự án Spring Boot và cấu hình OAuth client

Ví dụ sau dành cho **Java 17+, Spring Boot 3.2+ / Spring Security 6.x**, sử dụng `RestClient` của Spring Framework 6.1+. Các URL/domain/credentials đều là **giá trị ví dụ**, cần thay bằng authorization server và resource server thực tế trước khi chạy.

Các dependency Gradle tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Nếu ứng dụng **còn nhận Bearer token** từ client bên ngoài thì có thể cần thêm `spring-boot-starter-oauth2-resource-server`; đây là vai trò khác. Để **gọi ra API bằng OAuth2 Client**, chỉ starter OAuth2 Client đã cung cấp các thành phần cần thiết.

Ví dụ `application.yml` gồm hai client registrations:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          user-api:
            provider: user-idp
            client-id: ${USER_API_CLIENT_ID}
            client-secret: ${USER_API_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - api.read
          report-api:
            provider: service-idp
            client-id: ${REPORT_API_CLIENT_ID}
            client-secret: ${REPORT_API_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          user-idp:
            issuer-uri: https://login.example.test/realms/demo
          service-idp:
            token-uri: https://login.example.test/oauth2/token
~~~

Ý nghĩa:

- `registration.user-api` dùng **authorization code**. `issuer-uri` đòi hỏi nhà cung cấp có metadata discovery tương thích; tùy nhà cung cấp, có thể phải cấu hình tường minh authorization URI, token URI, JWK set URI, user-info URI.
- `redirect-uri` phải được đăng ký chính xác với authorization server, dùng HTTPS ở production và đúng host/path qua reverse proxy. `scope` chỉ yêu cầu quyền; authorization server mới quyết định quyền được cấp.
- `registration.report-api` dùng **client credentials**, nên cần `token-uri` và client credentials. Grant này thường **không có refresh token**; khi access token hết hạn, provider xin access token mới bằng thông tin client.
- `${...}` là Spring placeholder để đọc biến môi trường hoặc cấu hình bên ngoài. **Không commit client secret**, authorization code, access token hoặc refresh token vào Git/log.
- Dùng đúng registration ID trong `OAuth2AuthorizeRequest`; ID là tên nội bộ của cấu hình, không phải URL và không tự bằng scope hoặc client ID.

Nếu provider cấp access token không phải loại/định dạng mà resource server chấp nhận, đổi registration không giải quyết được; phải kiểm tra audience/resource indicator, scope và hợp đồng của cả hai phía.

## 5. Cấu hình hai OAuth2AuthorizedClientManager

File `OAuth2ClientManagersConfig.java` trong package `com.example.demo`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class OAuth2ClientManagersConfig {

    @Bean("servletAuthorizedClientManager")
    OAuth2AuthorizedClientManager servletAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("serviceAuthorizedClientManager")
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Ở đây hai bean có cùng interface, vì vậy khi inject vào controller/service phải dùng **`@Qualifier`** (hoặc lựa chọn bean một cách tường minh) để tránh lỗi ambiguous dependency.

**Vì sao hai provider khác nhau?**

- Với `user-api`, bước đầu tiên phải là browser làm OAuth2 authorization redirect/callback; manager xử lý authorized client đã tồn tại và có thể dùng provider `refreshToken()` nếu được cấp refresh token.
- Với `report-api`, provider `clientCredentials()` tự xin machine access token từ token endpoint khi chưa có hoặc khi token cần cấp lại. Không nên dùng browser session hoặc cố chạy OAuth2 Login cho một backend job.
- Một manager có thể được cấu hình nhiều provider, nhưng lựa chọn ở đây giúp **làm rõ ranh giới user token và service token**, giảm nguy cơ gửi nhầm loại token xuống API.

Những manager này có cơ chế success/failure handler để lưu hoặc xóa authorized client theo trường hợp. Khi gặp lỗi như refresh token bị thu hồi, cần xử lý OAuth2 failure phù hợp; không giả định framework tự khởi chạy consent cho người dùng hay tự retry mọi lỗi. Không truy xuất token từ kho bằng tay rồi bỏ qua manager trong mọi lần gọi, vì có thể vô tình dùng token đã hết hạn.

## 6. Kết nối OAuth2 Login với Servlet SecurityFilterChain

File `SecurityConfig.java`, ví dụ tối thiểu cho luồng browser:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/user/**", "/api/machine/**")
                .authenticated()
                .anyRequest().permitAll())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

`oauth2Login(...)` hỗ trợ flow đăng nhập tương tác; `oauth2Client(...)` bật các tích hợp OAuth2 Client cho ứng dụng Servlet. Chính sách `authenticated()` ở ví dụ bảo vệ các endpoint proxy phía trước; ứng dụng production phải bổ sung phân quyền, giới hạn endpoint và chính sách CSRF/CORS phù hợp.

**Đừng tắt CSRF toàn cục** chỉ vì ứng dụng gọi Bearer API ở phía downstream. Khi browser xác thực với chính ứng dụng bằng session cookie, các request có tác dụng ghi từ browser vẫn cần được đánh giá CSRF độc lập với việc backend dùng Bearer token khi gọi API khác.

Khi người dùng chưa đăng nhập, Spring Security có thể đưa browser tới trang đăng nhập rồi tới provider. Với registration `user-api`, đường khởi tạo thường là `/oauth2/authorization/user-api`, callback mặc định có dạng `/login/oauth2/code/user-api`. Hãy kiểm tra redirect URI đã đăng ký và cấu hình proxy; mã ủy quyền được đổi lấy token bởi các thành phần OAuth2 Login, không do controller tự parse callback.

## 7. Gọi API được bảo vệ bằng RestClient

Ví dụ dưới đây là file `DownstreamApiController.java` trong cùng package `com.example.demo`. Dự án đã có các bean từ mục 5, 6 và cấu hình registration ở mục 4. URI của resource server là ví dụ, cần thay URL thật. Chỉ xử lý GET để tập trung vào OAuth2 Client; nghiệp vụ khác cần thiết kế method, error mapping và validation riêng.

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.RestClient;

@RestController
public class DownstreamApiController {

    private final OAuth2AuthorizedClientManager servletManager;
    private final OAuth2AuthorizedClientManager serviceManager;
    private final RestClient api;

    public DownstreamApiController(
            @Qualifier("servletAuthorizedClientManager")
            OAuth2AuthorizedClientManager servletManager,
            @Qualifier("serviceAuthorizedClientManager")
            OAuth2AuthorizedClientManager serviceManager,
            RestClient.Builder restClientBuilder) {
        this.servletManager = servletManager;
        this.serviceManager = serviceManager;
        this.api = restClientBuilder
            .baseUrl("https://resource.example.test")
            .build();
    }

    @GetMapping("/api/user/profile")
    public String userProfile(Authentication authentication) {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("user-api")
                .principal(authentication)
                .build();

        // Phải gọi trong request Servlet với principal đã xác thực.
        OAuth2AuthorizedClient authorized =
            servletManager.authorize(request);

        if (authorized == null) {
            throw new ResponseStatusException(
                HttpStatus.FORBIDDEN,
                "Nguoi dung chua uy quyen OAuth2 client nay");
        }

        return api.get()
            .uri("/users/me")
            .headers(headers -> headers.setBearerAuth(
                authorized.getAccessToken().getTokenValue()))
            .retrieve()
            .body(String.class);
    }

    @GetMapping("/api/machine/reports")
    public String reports() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("report-api")
                .principal("reporting-service")
                .build();

        OAuth2AuthorizedClient authorized =
            serviceManager.authorize(request);

        if (authorized == null) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Khong lay duoc access token cho report-api");
        }

        return api.get()
            .uri("/reports")
            .headers(headers -> headers.setBearerAuth(
                authorized.getAccessToken().getTokenValue()))
            .retrieve()
            .body(String.class);
    }
}
~~~

**Phân tích chi tiết:**

1. Với `/api/user/profile`, tham số `Authentication` do Spring Security lấy từ context người dùng. Principal này phải tương ứng với lần người dùng đăng nhập/cấp quyền; không tự thay bằng một tên cố định. `DefaultOAuth2AuthorizedClientManager` và `OAuth2AuthorizedClientRepository` hoạt động trong **luồng Servlet request** mà Spring MVC có request/response hiện hành.
2. Nếu chưa có authorized client được cấp qua authorization redirect, `authorize(...)` có thể trả `null`. Phản hồi 403 ở đây chỉ là **quyết định minh họa của controller**. Ứng dụng có thể hướng người dùng tới consent/login flow một cách phù hợp, nhưng **không tự ý gọi lại authorization endpoint bằng retry vô hạn**.
3. Với `/api/machine/reports`, giá trị `"reporting-service"` là tên principal ổn định để quản lý machine authorized client; nó **không phải credentials của người dùng**. Service manager có thể dùng lại token hoặc xin token mới từ provider theo trạng thái.
4. `headers.setBearerAuth(...)` chỉ thêm access token vào **outbound HTTP request** tại thời điểm gọi. Controller không đưa access token vào JSON trả cho browser.
5. Resource server đích chịu trách nhiệm kiểm tra token và scope. Nhận HTTP 403 từ downstream **không nhất thiết** có nghĩa token hết hạn; cũng có thể thiếu scope/quyền hoặc sai audience.
6. Ví dụ dùng `RestClient` là HTTP client đồng bộ. Với ứng dụng reactive `WebFlux`, cách quản lý context và sử dụng `WebClient` có khác; bài này chỉ nói về **Spring Security Servlet**.
7. `RestClient.retrieve()` có thể ném exception cho response 4xx/5xx. Trong production nên cấu hình timeout, hạn chế retry, ánh xạ lỗi downstream và quan sát an toàn, thay vì để lộ trực tiếp body lỗi chứa chi tiết nhạy cảm.

**Lưu ý về token:** dùng `authorized.getAccessToken().getTokenValue()`. Nếu đăng nhập OIDC, **ID token** mô tả đăng nhập của user cho client; không thay ID token cho access token để gọi resource server trừ khi API có hợp đồng riêng được thiết kế rõ.

## 8. Hai luồng được chạy như thế nào?

### 8.1. User delegated access: authorization_code + refresh_token

~~~text
Browser ── GET /oauth2/authorization/user-api ──▶ Spring Security
Browser ◀──────── redirect tới Authorization Server ──┘
Browser ───────── đăng nhập/consent ──────────────▶ Authorization Server
Browser ◀──────── redirect tới /login/oauth2/code/user-api (code + state)
Spring Security ───── đổi code bằng token ────────▶ Authorization Server
Spring Security ───── lưu authorized client ──────▶ Repository/session/service
Browser ───────── GET /api/user/profile ─────────▶ Controller
Controller ───── servletManager.authorize(...) ──▶ Authorized client
Controller ───── Bearer access token ─────────────▶ Resource Server /users/me
Browser ◀──────── kết quả nghiệp vụ ────────────── Controller
~~~

Spring Security cần xác minh `state` trong callback và dùng các cơ chế giao thức phù hợp (PKCE khi áp dụng). Không tự viết logic callback/token exchange thủ công nếu các filter chuẩn đã xử lý. Refresh token chỉ có khi provider thực sự cấp và grant/provider hỗ trợ nó.

Nếu user logout hoặc grant bị thu hồi, hãy đánh giá chính sách xóa authorized client khỏi kho và xử lý session. Xóa session web, thu hồi access token tại authorization server và xóa authorized-client record là **các hành động khác nhau**; không tự suy ra tất cả đã xảy ra chỉ vì một cookie bị xóa.

### 8.2. Machine-to-machine: client_credentials

~~~text
Backend job / Servlet controller
    │
    └─ serviceManager.authorize("report-api", "reporting-service")
                    │
                    ├─ Đã có access token còn hiệu lực → dùng lại
                    └─ Chưa có/đã hết hạn → POST token endpoint
                             grant_type=client_credentials
                             client authentication + scope
                                    │
                                    ▼
                        Authorization Server cấp token
                                    │
                                    ▼
                    Lưu OAuth2AuthorizedClient theo principal
                                    │
                                    ▼
              GET /reports + Authorization: Bearer <token>
                                    │
                                    ▼
                          Resource Server kiểm quyền
~~~

Không cần trình duyệt, authorization code hay redirect trong luồng này. Token gắn với client/service, nên đừng coi nó là “token của người dùng đang gọi controller”; nếu endpoint phía trước cần user permission thì vẫn phải kiểm tra riêng **ai được phép kích hoạt công việc**.

Machine token có thể được chia sẻ giữa các invocation cùng registration và principal, nhưng chỉ trong phạm vi chính sách caching/storage. Nếu thay client secret hoặc thu hồi cấp quyền, request cấp token mới có thể thất bại dù record cũ còn trong kho.

## 9. Access token hết hạn, refresh token và lỗi authorize

Trường hợp hay gặp:

| Trạng thái | Dự kiến với provider phù hợp |
| --- | --- |
| Access token còn hạn | Có thể trả lại authorized client mà không gọi token endpoint |
| Access token sắp/hết hạn, refresh token có sẵn và được chấp nhận | `refreshToken()` xin access token mới; authorized client được cập nhật |
| Access token hết hạn, không có refresh token, client_credentials | `clientCredentials()` xin access token khác bằng client credentials |
| Access token hết hạn, user authorization_code nhưng không có refresh token | Có thể cần người dùng chạy lại tương tác authorization flow |
| Refresh token bị thu hồi hoặc trả `invalid_grant` | Authorize có thể thất bại; cần xử lý xóa token cũ/ủy quyền lại theo chính sách |
| Token còn thời hạn nhưng API trả 403 | Có thể thiếu scope, vai trò, audience, tenant; refresh không khắc phục mọi lỗi |
| Token endpoint tạm thời 5xx/timeout | Backoff, retry giới hạn, metrics; không lặp vô hạn hoặc tạo token storm |

Một số provider áp dụng **clock skew** để chủ động cấp mới khi token gần hết hạn; hãy kiểm tra phiên bản và cấu hình thực tế. Đừng tự làm phép so sánh expiration thiếu độ lệch đồng hồ rồi cache token riêng trong controller, vì có thể dùng token hết hạn hoặc làm mất cơ chế refresh.

**Giao thức OAuth2 không đồng nghĩa token luôn là JWT.** Access token có thể là chuỗi opaque. Client chỉ cần gắn đúng Bearer token vào request; resource server có thể dùng JWT validation hoặc token introspection tùy thiết kế.

Nếu gọi downstream trả `401 invalid_token`, cần phân biệt token đã hết hạn, token sai audience và lỗi mạng/proxy. Tự động làm mới token vô hạn sau mọi 401 là nguy hiểm: đôi khi token vẫn hợp lệ nhưng đang được gửi sai resource, hoặc API không cấp quyền. Hãy xử lý có số lần retry tối đa và quan sát mã lỗi thực tế.

### Tại sao không gọi token endpoint trực tiếp trong mọi controller?

Tự viết `POST /token` cho mỗi request dễ dẫn đến lặp token exchange, quản lý cache/expiry sai, lỗi lưu refresh token, rò secret vào log và khó bảo trì. `OAuth2AuthorizedClientManager` chuẩn hóa cơ chế quản lý, nhưng **không loại bỏ** nhu cầu thiết lập provider đúng, storage an toàn, timeout và xử lý HTTP lỗi.

## 10. Servlet request và background job: ranh giới quan trọng

**`DefaultOAuth2AuthorizedClientManager`** được thiết kế cho HTTP request có Servlet context. Đặt lệnh `authorize(...)` của nó trong `@Scheduled`, task chạy bất đồng bộ hoặc thread được tạo thủ công có thể thiếu HttpServletRequest/Response, gây lỗi hoặc không lưu đúng token. Đừng “copy” context của người dùng sang job chỉ để qua lỗi nếu không có chính sách bảo mật và lifecycle rõ ràng.

Với background công việc của ứng dụng, tái dùng **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
public class ReportTokenJob {
    private final OAuth2AuthorizedClientManager manager;

    public ReportTokenJob(
            @Qualifier("serviceAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @Scheduled(fixedDelayString = "PT30M")
    public void checkAuthorization() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("report-api")
                .principal("reporting-service")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null) {
            throw new IllegalStateException(
                "Cannot authorize report-api");
        }

        // Từ đây có thể gọi API bằng client.getAccessToken().
        // Không log token hoặc gửi trả token cho user.
    }
}
~~~

Đây là **class mẫu có Spring dependencies**, cần bật scheduling (ví dụ `@EnableScheduling` trên cấu hình ứng dụng) mới có tác vụ chạy định kỳ. Nếu chỉ muốn gọi API mỗi 30 phút, nên đặt HTTP call ở service dùng token này, thêm timeout và chống chạy trùng job trên nhiều instance.

**Không dùng service manager với một principal chung để lấy token của từng người dùng ở background** khi chưa có mô hình lưu trữ, consent, bảo vệ refresh token và quyền truy cập từng user. Một job dùng delegated token của user là một thiết kế phức tạp hơn machine client credentials.

## 11. Phân tách lỗi và trách nhiệm giữa các tầng

| Lỗi/hiện tượng | Nơi cần xem trước | Cách chẩn đoán |
| --- | --- | --- |
| Không tìm thấy client registration | Cấu hình `registrationId`, property binding | Đối chiếu tên chính xác, profile môi trường và bean repository |
| Không lấy được access token client_credentials | Authorization server/token URI, client authentication, secret, scope | Kiểm tra lỗi OAuth2 và cấu hình; không ghi secret/token ra log |
| `authorize(...)` trả `null` cho user | User chưa hoàn tất consent/code flow, thiếu authorized client hoặc provider không phù hợp | Kiểm tra login, callback, principal, repository, registration |
| Browser redirect liên tục | Session/cookie, redirect URI, state, hostname/proxy, client registration | Kiểm tra HTTPS, cookies, proxy forwarding và URI tại provider |
| Có token nhưng API đích trả 401 | Token thiếu/sai/hết hạn, audience/issuer không khớp, format header | Xem `WWW-Authenticate` và resource server logs an toàn |
| API đích trả 403 | Token hợp lệ nhưng scope/quyền không đủ hoặc chính sách từ chối | Kiểm tra scope được cấp, authority mapping và tài nguyên |
| Token được refresh trên mỗi request | Khác principal/registration mỗi lần, storage không bền, clock skew hoặc token lifetime ngắn | Kiểm tra khóa lưu, expiry, persistence và số lần gọi token endpoint |
| Scheduled job gặp lỗi Servlet context | Dùng nhầm `DefaultOAuth2AuthorizedClientManager` | Đổi sang `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| Có lỗi bean `OAuth2AuthorizedClientManager` không duy nhất | Khai báo hai manager, injection thiếu qualifier | Dùng `@Qualifier`/bean name theo mục 5 |
| Test chạy ở local nhưng production mất phiên | Dùng in-memory hoặc session không chia sẻ giữa node | Thiết kế lưu trữ/persistence, cân bằng tải và session phù hợp |
| Downstream HTTP lỗi không được xử lý | `RestClient.retrieve()` phát sinh exception | Map response status, đặt timeout, retry có giới hạn và circuit breaker khi cần |

Đừng suy luận từ một status code duy nhất. Phân biệt ba miền: (1) browser xác thực vào ứng dụng; (2) ứng dụng xin token OAuth2 từ authorization server; (3) resource server nhận/kiểm token khi API được gọi. Mỗi miền có nguyên nhân lỗi và log riêng.

## 12. Kiểm thử có ý nghĩa

### 12.1. Test quản lý authorized client

Dùng test double hoặc một OAuth2 authorization server thử nghiệm để xác nhận:

1. Lần đầu `client_credentials` chưa có authorized client thì manager gọi token endpoint và lưu token.
2. Lần kế tiếp khi token còn hạn, manager có thể trả token đã lưu mà không xin token mới.
3. Khi token hết hạn, manager có thể xin token mới theo client credentials; với delegated access và refresh token hợp lệ, provider thử refresh.
4. Khi token endpoint trả lỗi, ứng dụng không lặp vô hạn hoặc rò client secret.
5. Hai principal/registration ID khác nhau không vô tình đọc nhầm token của nhau.
6. Manager phục vụ request Servlet có principal phù hợp và không gây lỗi do thiếu request context.

Để kiểm thử HTTP client, dùng **MockWebServer/WireMock** (hoặc stub server tương đương) và kiểm tra request đến resource server nhận **chính xác một** header `Authorization: Bearer <token-test>`; không log token thực trong test report. Đồng thời thử trả 401/403/5xx và timeout từ resource server để xác nhận error mapping.

### 12.2. Test luồng browser

Với authorization code, test phải bao phủ redirect, tham số `state` và callback, session, consent cũng như token storage. `MockMvc` có thể xác minh filter/controller dưới điều kiện giả lập, nhưng **không thay thế** test tích hợp với authorization server và browser thật qua HTTPS/proxy. Khi đăng nhập OIDC, kiểm tra claims cần thiết, issuer và mapping user; tránh coi access token là ID token.

### 12.3. Gọi thử tại môi trường phát triển

Khởi động ứng dụng đã cấu hình IdP/resource server thử nghiệm (các domain `example.test` trong README chỉ là placeholder), sau đó:

~~~bash
# Chạy từ trình duyệt để thực hiện login/callback tương tác:
# http://localhost:8080/oauth2/authorization/user-api

# Sau khi đăng nhập hợp lệ trong cùng phiên browser:
# http://localhost:8080/api/user/profile

# Route service-token vẫn chịu auth của ứng dụng phía trước:
curl -i http://localhost:8080/api/machine/reports
~~~

Lệnh `curl` cuối **không tự có browser session**, nên với `SecurityFilterChain` ví dụ nó có thể nhận redirect/login hoặc lỗi xác thực trước khi controller lấy machine token. Đây là hành vi mong đợi nếu route yêu cầu `authenticated()`. Muốn machine job gọi không có browser, hãy dùng chính service manager bên trong job và bảo vệ điểm kích hoạt job bằng cơ chế phù hợp.

Không đưa ra stdout/HTTP 200 giả định: response phụ thuộc authorization server, dữ liệu API, proxy, session, scope và cấu hình thật.

## 13. Nguyên tắc triển khai an toàn

- **Dùng access token, không dùng ID token** để gọi resource server trừ khi API có giao thức riêng được xác định rõ.
- **Bảo vệ secret và token:** TLS, secret manager/env, không ghi vào URL, query string, log, exception, frontend HTML hoặc browser localStorage khi backend giữ token.
- **Không chuyển tiếp mù quáng header Authorization từ client inbound sang downstream.** Dùng đúng authorized client tương ứng user/service và scope/audience của API đích.
- **Không cho client điều khiển tùy ý URL downstream.** Giữ allowlist target host/path để giảm SSRF và tránh gửi Bearer token đến endpoint do người dùng chọn.
- **Giới hạn scope tối thiểu.** Machine client không nên có quyền rộng hơn nghiệp vụ cần; delegated token phải gắn với đúng user và resource.
- **Phân quyền endpoint nội bộ độc lập:** token đủ quyền gọi resource server không thay thế kiểm tra ai có quyền nhấn nút/gọi controller phía trước.
- **Duy trì CSRF defense** nếu ứng dụng Servlet nhận session cookie từ browser và có thao tác thay đổi trạng thái.
- **Phân biệt token expiry và HTTP lỗi từ downstream:** refresh token không chữa thiếu quyền hoặc sai audience.
- **Chọn lưu trữ phù hợp:** service in-memory có thể mất token khi restart; session/repository cần đánh giá khi chạy nhiều node. Với refresh token, mã hóa và giới hạn truy cập vào kho lưu.
- **Quan sát an toàn:** metric về cấp lại token, refresh thất bại, 401/403 downstream, latency; log chỉ registration ID, mã lỗi và correlation ID, tuyệt đối không log access/refresh token hay client secret.

### Checklist tự đánh giá

- [ ] `ClientRegistrationRepository` chứa đúng registration ID, grant type, token/authorization endpoint và scopes.
- [ ] User flow có OAuth2 Login/authorization callback thật, redirect URI hợp lệ và principal được liên kết đúng.
- [ ] Service flow dùng `client_credentials` và manager dựa trên `OAuth2AuthorizedClientService`.
- [ ] Manager có provider phù hợp: `authorizationCode()`, `refreshToken()`, `clientCredentials()` theo từng client.
- [ ] Mỗi `authorize(...)` kiểm tra null và có chiến lược xử lý OAuth2 lỗi.
- [ ] Outbound HTTP chỉ mang đúng `Authorization: Bearer <access-token>` đến host được kiểm soát.
- [ ] Đã test token mới, token còn hạn, token hết hạn, refresh/grant lỗi, thiếu scope và mất storage.
- [ ] Đã kiểm tra phân quyền của Servlet endpoints, session/CSRF, proxy/HTTPS và quan sát lỗi an toàn.

**Ghi nhớ:** `OAuth2AuthorizedClientManager` là bộ điều phối **authorized client và vòng đời access token** cho OAuth2 Client trong Spring Security. Trong request Servlet theo người dùng, chọn `DefaultOAuth2AuthorizedClientManager` kết hợp repository; trong tác vụ nền hoặc `client_credentials`, chọn `AuthorizedClientServiceOAuth2AuthorizedClientManager` kết hợp service. Dù manager lấy và cập nhật token thành công, ứng dụng vẫn phải gửi đúng Bearer header, bảo vệ token, xử lý lỗi HTTP và tuân thủ phân quyền của resource server.
