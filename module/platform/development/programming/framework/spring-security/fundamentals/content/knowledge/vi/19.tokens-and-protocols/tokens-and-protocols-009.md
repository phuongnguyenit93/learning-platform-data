# Phân biệt OAuth2 Login, OAuth2 Client và Resource Server trong Spring Security

Spring Security cung cấp nhiều tính năng mang tên OAuth2, nên khi bắt đầu xây dựng ứng dụng rất dễ lẫn ba câu hỏi: **làm sao cho người dùng đăng nhập qua một Identity Provider (IdP)?**, **làm sao ứng dụng lấy access token để gọi API khác?**, và **làm sao API của mình xác minh access token do client gửi đến?** Ba nhu cầu này tương ứng với **OAuth2 Login**, **OAuth2 Client** và **OAuth2 Resource Server**.

Điểm quan trọng nhất là **OAuth2 Login là một tính năng được xây dựng trên nền OAuth2 Client**; hai khái niệm này liên quan nhưng không đồng nghĩa. **Resource Server** lại đứng ở phía *nhận và kiểm tra* Bearer access token. Cả ba đều không tự biến ứng dụng thành **Authorization Server** phát hành token.

Bài viết tập trung vào **Spring Security Servlet / Spring MVC**, sử dụng cách cấu hình `SecurityFilterChain` hiện đại trên nền Java 17+ và Spring Boot 3 / Spring Security 6. Các khái niệm OAuth 2.0 vẫn có giá trị ở môi trường khác, nhưng tên API cho WebFlux là Reactive tương ứng, không nên trộn lẫn.

## 1. Chọn đúng tính năng bằng ba câu hỏi

| Tình huống | Thành phần Spring Security | Vai trò ứng dụng | Dữ liệu nổi bật |
|---|---|---|---|
| Người dùng bấm “Đăng nhập với Google/IdP” trên website | **OAuth2 Login** — `http.oauth2Login(...)` | **Client**, đồng thời là ứng dụng web quản lý phiên đăng nhập | Authorization code, thông tin người dùng; có thể có OIDC ID token |
| Ứng dụng đã đăng nhập người dùng và cần gọi API đối tác bằng token được cấp | **OAuth2 Client** — `http.oauth2Client(...)`, `OAuth2AuthorizedClientManager` | **Client** gửi request ra ngoài | Access token, refresh token nếu được cấp |
| Một job backend cần tự lấy token qua `client_credentials` để gọi API | **OAuth2 Client** | **Client** hoạt động bằng danh tính ứng dụng | Client registration, access token cho ứng dụng |
| API `/api/orders` cần chấp nhận `Authorization: Bearer ...` | **OAuth2 Resource Server** — `http.oauth2ResourceServer(...)` | **Resource Server** nhận request vào | JWT access token hoặc opaque access token |
| Hệ thống cần **phát hành** access token, refresh token, quản lý OAuth grants | **Authorization Server**, được triển khai bằng sản phẩm/thành phần chuyên biệt | **Authorization Server** | Authorization endpoint, token endpoint, keys, grants |

**Bản đồ tư duy:** **Login = đăng nhập người dùng vào ứng dụng**, **Client = lấy/quản lý token để ứng dụng gọi dịch vụ khác**, **Resource Server = bảo vệ API nhận Bearer token**. Một hệ thống có thể đồng thời đóng nhiều vai trò ở các endpoint khác nhau; đây là phân loại theo **chiều luồng request và trách nhiệm bảo mật**, không phải ba kiểu project buộc phải tách riêng.

### Quan hệ giữa các tính năng

```text
                   Spring Security OAuth2 (Servlet)
                              |
          +-------------------+------------------+
          |                                      |
     OAuth2 Client                        OAuth2 Resource Server
          |                                      |
          +-- OAuth2 Login                      +-- JWT validation
          |   (đăng nhập browser)               |
          +-- Authorization Code                +-- Opaque token introspection
          +-- Client Credentials
          +-- Refresh Token
          +-- Authorized Client / Token Manager
```

Sơ đồ nhóm theo trách nhiệm xử lý của ứng dụng. **OAuth2 Login sử dụng hạ tầng OAuth2 Client**, còn Resource Server có cơ chế nhận và xác thực Bearer token của riêng nó. Authorization Server là một vai trò khác, không được tạo ra bằng cách bật ba DSL trên.

## 2. Cùng một hệ thống, ba góc nhìn

Ví dụ một kiến trúc gồm ứng dụng web `portal.example.test`, API `api.example.test` và nhà cung cấp danh tính `idp.example.test`:

```text
    [Browser - người dùng]
              |
              | (1) Mở portal, bấm Đăng nhập
              v
    [Portal / Spring MVC]
       OAuth2 Login + OAuth2 Client
              |           ^
              | Redirect  | Authorization code / tokens
              v           |
       [Identity Provider / Authorization Server]
              ^
              | (3) Khi cần token mới, portal trao đổi với IdP
              |
    [Portal / Spring MVC]
              |
              | (2) Gọi API với Authorization: Bearer ACCESS_TOKEN
              v
       [Orders API / Spring MVC]
          OAuth2 Resource Server
              |
              | Xác thực token, kiểm scope/audience,
              | kiểm quyền trên đơn hàng
              v
         [Dữ liệu nghiệp vụ]
```

Ở bước (1), **portal là client đang thực hiện login cho người dùng**. Ở bước (2), portal **là client gọi API**, còn Orders API **là resource server**. Khi token được phát hành hoặc làm mới, **IdP/authorization server** là nơi chịu trách nhiệm. Một sản phẩm tên là “server” không mặc nhiên là OAuth2 Resource Server; cần xác định nó có **nhận Bearer access token để bảo vệ tài nguyên** hay không.

## 3. OAuth2 Login: đăng nhập người dùng qua IdP

### Khi nào dùng?

Sử dụng OAuth2 Login nếu ứng dụng có giao diện web và muốn người dùng đăng nhập bằng tài khoản do một provider bên ngoài quản lý, như “Sign in with Google” hoặc “Login with công ty”.

Spring Security hỗ trợ OAuth2 Login theo **Authorization Code Grant**. Nếu provider hỗ trợ **OpenID Connect (OIDC)** và client yêu cầu scope `openid`, luồng OIDC có **ID token** phục vụ xác minh danh tính người dùng. OAuth 2.0 tự thân là khung ủy quyền, vì vậy với nhu cầu đăng nhập liên thông theo chuẩn, OIDC thường là lựa chọn phù hợp; một số provider cung cấp user info theo OAuth 2.0 mà không dùng OIDC.

### Trình tự của luồng đăng nhập

1. Browser truy cập một trang cần đăng nhập tại portal.
2. Spring Security chuyển hướng người dùng đến `/oauth2/authorization/{registrationId}`; ví dụ `/oauth2/authorization/company`. Tùy cấu hình, client gửi browser đến authorization endpoint của IdP, mang `state` và các thông tin cần thiết; PKCE có thể được sử dụng theo loại client và cấu hình.
3. Người dùng xác thực tại IdP và đồng ý cấp quyền nếu IdP yêu cầu.
4. IdP chuyển hướng browser về URI callback của ứng dụng, theo mặc định là `{baseUrl}/login/oauth2/code/{registrationId}`, kèm authorization code và state phù hợp.
5. Ứng dụng **trao đổi authorization code với token endpoint** của IdP qua kết nối server-to-server; client nhận token tương ứng, xác minh và xử lý thông tin danh tính theo cơ chế provider.
6. Spring Security xây dựng một `Authentication` đại diện cho người dùng đã đăng nhập, đặt vào `SecurityContext`; với ứng dụng Servlet dùng phiên thông thường, trạng thái đăng nhập được quản lý qua HTTP session.
7. Browser tiếp tục truy cập portal với cookie phiên tương ứng. Browser **không buộc phải tự gửi access token** cho mỗi trang nội bộ của portal.

Các URL minh họa:

```http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.test
```

```http
GET /login/oauth2/code/company?code=EXAMPLE_CODE&state=EXAMPLE_STATE HTTP/1.1
Host: portal.example.test
```

Các giá trị `EXAMPLE_CODE` và `EXAMPLE_STATE` chỉ dùng để mô tả. Authorization code là giá trị ngắn hạn, một lần sử dụng và phải được ràng buộc/kiểm tra đúng quy trình. Đừng gửi thật các code, token hay cookie phiên trong log hoặc ảnh chụp.

### Spring Security lưu điều gì sau đăng nhập?

Khi OAuth2 Login thành công, người dùng thường được biểu diễn bởi `OAuth2AuthenticationToken` trong `SecurityContext`; principal có thể là `OAuth2User` hoặc `OidcUser` với OIDC. Ứng dụng thông thường dùng cookie phiên để duy trì login qua các request trình duyệt. Cơ chế này có thể cùng tồn tại với `OAuth2AuthorizedClient` chứa access token được cấp để gọi API.

**Không nhầm ba dữ liệu:**

- `SecurityContext`: trạng thái xác thực trong ứng dụng hiện tại, phục vụ kiểm tra người dùng đăng nhập và phân quyền đối với portal.
- `OAuth2AuthorizedClient`: dữ liệu liên hệ giữa một client registration, người dùng/chủ thể và token đã được cấp; phục vụ các request OAuth2 từ ứng dụng đến tài nguyên khác.
- `IdToken` của OIDC: bằng chứng danh tính theo OIDC và dành cho phía client đăng nhập; **không dùng ID token thay access token** để gọi resource server.

**OAuth2 Login không tự biến portal thành API Bearer Resource Server.** Nếu portal còn mở REST API nhận `Authorization: Bearer`, cần cấu hình Resource Server phù hợp cho những endpoint đó.

### Cấu hình tối thiểu cho web login

Trong ứng dụng Spring Boot Servlet có starter OAuth2 Client và client registration hợp lệ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebLoginSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

Đây là **mã cấu hình Spring Boot/Spring Security**, không thể chạy riêng chỉ với lệnh `javac` vì cần dependency framework, provider, client registration và runtime Servlet. Khi có nhiều filter chain, phải gán `securityMatcher` và thứ tự ưu tiên thích hợp.

Trong `application.yml`, client registration của provider OIDC thường có dạng:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company-idp:
            issuer-uri: https://idp.example.test/issuer
```

Đây là cấu hình **minh họa cấu trúc**; `idp.example.test` không phải IdP thật. Phải khai báo đúng issuer theo IdP thực tế, đăng ký chính xác redirect URI tại IdP và cung cấp `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` an toàn qua môi trường hoặc secret manager. Với public client/PKCE, phương thức client authentication và lưu trữ secret cần thiết kế phù hợp; không đặt client secret bảo mật trong mã JavaScript frontend.

### Login và logout

Với ứng dụng web dùng session, sau khi xác thực người dùng có thể điều hướng các trang trong portal dựa trên session. **Logout cục bộ** có thể xóa trạng thái xác thực/phiên trong portal, nhưng **không tự mặc định đăng xuất phiên SSO ở IdP**, thu hồi mọi access token hoặc đăng xuất mọi ứng dụng khác. OIDC có các cơ chế logout liên thông riêng khi IdP hỗ trợ; cần cấu hình rõ nếu sản phẩm yêu cầu single logout.

## 4. OAuth2 Client: lấy và dùng token để gọi API ra ngoài

### Khi nào dùng?

OAuth2 Client được dùng khi ứng dụng của mình **là bên chủ động gọi một API được bảo vệ bởi OAuth2**. Việc này có thể xảy ra khi:

- Người dùng đã đăng nhập và ứng dụng muốn gọi API thay mặt chính người dùng (**delegated access**).
- Một tác vụ backend hoặc microservice cần gọi API bằng danh tính dịch vụ (**client credentials**), không có người dùng tương tác.
- Ứng dụng cần quản lý access token, refresh token và các lần cấp lại phù hợp với grant được sử dụng.

Ở Spring Security Servlet, hạ tầng quan trọng gồm:

| Thành phần | Vai trò |
|---|---|
| `ClientRegistration` | Thông tin khai báo một OAuth2 client: registrationId, provider, grant type, client ID, scopes, endpoints |
| `ClientRegistrationRepository` | Tra thông tin các client registration đã cấu hình |
| `OAuth2AuthorizedClient` | Kết hợp client registration, chủ thể liên quan và access token (cùng refresh token nếu có) |
| `OAuth2AuthorizedClientService` | Lưu/tra authorized client theo client registration và principal; phù hợp các trường hợp lưu trạng thái ngoài web request |
| `OAuth2AuthorizedClientRepository` | Lưu/tra authorized client gắn với request/response và principal trong môi trường web |
| `OAuth2AuthorizedClientManager` | Quản lý việc authorize/re-authorize bằng provider theo grant, kể cả refresh khi được hỗ trợ và cấu hình |
| `oauth2Client(...)` DSL | Kích hoạt/cấu hình phần hỗ trợ OAuth2 Client trong `HttpSecurity`, nhất là authorization code và các thành phần liên quan |

**Tên `OAuth2AuthorizedClient` không có nghĩa “người dùng đã login vào website”.** Nó nghĩa là **một client đã có authorization và token** tương ứng cho việc truy cập tài nguyên. Một backend job dùng `client_credentials` vẫn có authorized client dù không hề có người dùng đang mở browser.

### Hai dạng sử dụng quan trọng

**A. Dùng quyền đã cấp của người dùng**

Một ứng dụng portal có thể dùng `oauth2Login()` cho browser login và dùng `oauth2Client()` / authorized client infrastructure để gọi một API bên ngoài. Token phải lấy từ `OAuth2AuthorizedClient` hoặc cơ chế client được quản lý, không lấy ID token làm access token. Luồng authorization code có thể phát hành refresh token tùy provider, scopes và chính sách.

**B. Gọi API giữa các dịch vụ bằng `client_credentials`**

Ví dụ job `reporting-service` cần đọc inventory API mà không có browser:

```text
reporting-service             IdP / Authorization Server
      |  POST token endpoint (client_credentials)
      |------------------------------------>|
      |<-------------- access token -------|
      |
      | Authorization: Bearer access_token
      |------------------------------------> inventory-api
      |                         inventory-api xác minh token
      |<---------------- dữ liệu phù hợp ---|
```

Trong client credentials, token thường biểu diễn quyền của **ứng dụng**; đừng mặc nhiên xem nó là người dùng cuối. Server có thể áp dụng client authentication bằng secret, private-key JWT, mTLS hoặc phương thức thích hợp. Ở backend, **client secret phải lưu an toàn**, không đưa vào mã nguồn hoặc trình duyệt.

Cấu hình đăng ký một client machine-to-machine, tách biệt với ví dụ web login phía trên:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: service-idp
            authorization-grant-type: client_credentials
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            scope: inventory.read
        provider:
          service-idp:
            token-uri: https://idp.example.test/oauth2/token
```

Giả sử `inventory` đã được đăng ký đúng ở authorization server và dữ liệu bí mật được nạp từ môi trường, ứng dụng có thể tạo `OAuth2AuthorizedClientManager` cho tác vụ backend:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration
public class ServiceOAuth2ClientConfig {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Với một service cần sử dụng token, phần lấy authorized client có thể như sau (mã thuộc ứng dụng có cấu hình ở trên, không độc lập với framework):

```java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("inventory")
                .principal("reporting-service")
                .build();

OAuth2AuthorizedClient authorizedClient =
        authorizedClientManager.authorize(request);

if (authorizedClient == null) {
    throw new IllegalStateException("Không lấy được authorized client");
}

String accessToken = authorizedClient.getAccessToken().getTokenValue();
// Dùng accessToken trong Authorization: Bearer khi gọi đúng inventory API.
// Không ghi token thật vào log hoặc in ra console.
```

Cần các import bổ sung `OAuth2AuthorizeRequest` và `OAuth2AuthorizedClient` cùng biến `authorizedClientManager` được inject. Đoạn gọi trên minh họa **cách sử dụng API của Spring Security trong service**, không phải một class Java hoàn chỉnh độc lập. Tên `reporting-service` được dùng để gắn authorized client với một principal định danh dịch vụ trong manager; nó không chứng minh có người dùng đã đăng nhập.

Lưu ý manager loại `AuthorizedClientServiceOAuth2AuthorizedClientManager` thích hợp cho service không phụ thuộc `HttpServletRequest`. Trong luồng web có người dùng, có thể dùng `DefaultOAuth2AuthorizedClientManager` hoặc cách tích hợp `RestClient`/`WebClient` phù hợp với request. Hãy chọn manager theo ngữ cảnh và grant; **không mặc định lấy một access token của người dùng bất kỳ** cho job nền.

### OAuth2 Client có tự làm mới token không?

Spring Security cung cấp hạ tầng refresh token và `OAuth2AuthorizedClientProvider` tương ứng, nhưng hành vi **phụ thuộc provider/grant, cách tạo manager và cách gọi authorize**. Không được chỉ bật `oauth2Client()` rồi kết luận mọi client tự động có refresh token, tự rotation, hoặc tự tái xác thực ở mọi ngữ cảnh. Authorization server quyết định có cấp refresh token và áp dụng chính sách sử dụng thế nào.

## 5. Resource Server: xác minh Bearer token ở API

### Khi nào dùng?

Dùng **OAuth2 Resource Server** khi ứng dụng của bạn cung cấp API và mỗi request cần được bảo vệ bằng OAuth2 access token. Client có thể là browser-based app, backend, mobile app hay một dịch vụ khác; API không phụ thuộc vào việc client đã đăng nhập bằng Google hay dùng grant nào, miễn token đã được authorization server cấp hợp lệ cho API và thỏa quy tắc.

Request đi vào API:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

`Bearer` biểu thị cách trình token. **Sự hiện diện của header không đủ**: Spring Security phải xác minh token theo cơ chế JWT hoặc introspection, sau đó áp dụng quyền truy cập.

### Hai cách kiểm tra access token

**JWT access token**: resource server sử dụng `JwtDecoder` để kiểm tra chữ ký và các claim phù hợp. Khi cấu hình `issuer-uri`, Spring Security có thể khám phá metadata/key của issuer và xác minh `iss`, `exp`, `nbf` theo cấu hình mặc định tương ứng. **Audience `aud` cần được cấu hình/kiểm tra đúng cho API** nếu không được framework tự thiết lập theo yêu cầu cụ thể của bạn. Scope thường được ánh xạ thành authority `SCOPE_<scope>`.

**Opaque access token**: resource server thường sử dụng `OpaqueTokenIntrospector` để hỏi authorization server/introspection endpoint token còn active và có quyền gì. Dạng JWT cũng có thể được kiểm tra bằng introspection khi hệ thống muốn kiểm tra trạng thái động; từ “opaque” ở đây nói về **phương thức xác minh** qua introspection chứ không chỉ vẻ ngoài của chuỗi token.

Cả hai đều cần TLS, kiểm tra phạm vi quyền và chính sách thu hồi thích hợp. **Resource Server không tự cấp access token, không tự cấp refresh token, không tự thiết lập màn hình login redirect.**

### Mẫu cấu hình API JWT

Thêm dependency thích hợp trong Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Cấu hình issuer của authorization server (URL minh họa, cần IdP thực tế):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
```

Mã cấu hình trong Spring Boot Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiResourceServerConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Đây là ví dụ cấu hình trong một **ứng dụng Spring Boot có dependencies thích hợp**; ứng dụng phải trỏ tới issuer/JWKS thật và có controller API tương ứng. Scope `orders.read` chỉ là tên quyền minh họa; quyền thật do authorization server phát hành và API thực thi. Đừng xem `hasAuthority("SCOPE_orders.read")` là đủ cho mọi kiểm tra quyền với từng đơn hàng; quy tắc sở hữu tài nguyên và nghiệp vụ vẫn phải kiểm tra.

### 401, 403 và login redirect

Một resource server điển hình trả **401 Unauthorized** cho request thiếu/không hợp lệ token, có thể kèm `WWW-Authenticate: Bearer`. Với token hợp lệ nhưng thiếu quyền, thường trả **403 Forbidden**. Nó **không phải** hành vi bắt browser chuyển tới trang đăng nhập của provider: đó là chức năng khác trong OAuth2 Login.

Khi cấu hình cùng OAuth2 Login trên một ứng dụng, nếu muốn API luôn phản hồi 401/403 thay vì HTML login/302, hãy tạo **filter chain riêng** cho `/api/**` và cấu hình entry point phù hợp. Tránh để toàn bộ API dùng cùng chính sách session/redirect của browser một cách tình cờ.

## 6. Ba DSL có giống nhau vì đều tên OAuth2 không?

```java
http.oauth2Login(Customizer.withDefaults());          // Browser đăng nhập qua IdP
http.oauth2Client(Customizer.withDefaults());         // Ứng dụng đóng vai OAuth2 Client
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));       // API nhận và kiểm JWT Bearer
```

**Không nên sao chép cả ba vào mọi `SecurityFilterChain`.** Những dòng này là các điểm cấu hình cho ba nhu cầu khác nhau; chúng không mặc định phải có mặt trong cùng một chuỗi. Thay vào đó hãy xác định:

| Câu hỏi kiến trúc | Câu trả lời dẫn tới |
|---|---|
| App có cho người dùng tương tác đăng nhập qua IdP không? | OAuth2 Login |
| App có gọi API khác bằng token OAuth2 không? | OAuth2 Client |
| App có xác minh access token đi vào endpoint của chính nó không? | OAuth2 Resource Server |
| App có tự phát hành access token cho client khác không? | Authorization Server độc lập |
| App có vừa đăng nhập người dùng vừa gọi API giúp người dùng không? | OAuth2 Login **và** OAuth2 Client |
| App có giao diện browser và một số REST API Bearer không? | Tổ hợp Login/Client và Resource Server, với các filter chain phù hợp |

Sử dụng `oauth2Login()` cho giao diện web thường đã kéo theo hạ tầng OAuth2 Client cần thiết cho login. Bật thêm `oauth2Client()` có giá trị khi ứng dụng cần cấu hình hành vi client/outbound riêng. **Không nhất thiết viết cả hai chỉ để có nút đăng nhập**.

Tương tự, việc thêm dependency OAuth2 Client cho phép dùng hạ tầng client nhưng không có nghĩa server đã chấp nhận mọi inbound JWT. Quyền bảo vệ API cần cấu hình Resource Server và bộ validator tương ứng.

## 7. Một ứng dụng hỗn hợp: browser login và Bearer API

Đây là trường hợp dễ nhầm nhất. Giả sử cùng một Spring Boot service có:

- Các trang `/dashboard`, `/account` cho người dùng browser đã đăng nhập qua OIDC.
- Các endpoint `/api/orders/**` cho ứng dụng khác gửi Bearer access token.
- Sau đăng nhập, portal có thể dùng OAuth2 Client để gọi thêm API downstream.

Ta có thể chia hai `SecurityFilterChain`, với API được ưu tiên trước browser:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MixedSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
```

Đoạn Java này là **một phương án triển khai trong dự án Spring Boot 3 / Spring Security 6** có cả starter OAuth2 Client và Resource Server, client registration, issuer, controller và tài nguyên cần thiết. Nó không tự chạy bằng `javac` ngoài Spring Boot. Trong ứng dụng thật, **chỉ dùng một lớp cấu hình phù hợp với kiến trúc**; đừng đặt đồng thời các `SecurityFilterChain` mẫu ở phần trước và ở phần này mà không kiểm tra thứ tự và vùng match.

Tại sao tách như vậy?

1. `apiChain` chỉ áp dụng `/api/**`. Nó nhận Bearer token, xác minh JWT và không dùng HTTP session để lưu `SecurityContext`. Chính sách CSRF được tắt **chỉ trong chain giả định API hoàn toàn Bearer-only**, vì browser cookie không được dùng làm credential xác thực ở chain này.
2. `browserChain` áp dụng phần request còn lại. Nó dùng OAuth2 Login và có thể sử dụng OAuth2 Client để gọi API khác. Với web login dựa vào session/cookie, cần duy trì chống CSRF khi có thao tác đổi trạng thái; ví dụ không tắt CSRF toàn cục.
3. `@Order(1)` và `@Order(2)` quyết định chain được xét trước, còn `securityMatcher` quyết định request nào thuộc chain. Spring Security thường chỉ sử dụng **filter chain đầu tiên khớp** request.
4. `/oauth2/authorization/{registrationId}` và `/login/oauth2/code/{registrationId}` được xử lý bởi browser chain; tránh áp `securityMatcher("/api/**")` cho login callback.

**Điều kiện quan trọng:** Cấu hình trên chỉ phù hợp nếu `/api/**` thực sự dùng Bearer header và không cần cookie/session để xác thực. Nếu API được gọi bằng cookie phiên của browser, CSRF có thể vẫn là nguy cơ và cần chiến lược bảo vệ khác. Việc tắt CSRF dựa trên mô hình request và credential, không chỉ vì tên đường dẫn có `api`.

### Nhìn một request sẽ biết chain nào chạy

| Request | Chain | Kết quả kỳ vọng |
|---|---|---|
| Browser truy cập `GET /dashboard` chưa login | Browser | Redirect vào luồng OAuth2 Login khi cần |
| Browser callback `GET /login/oauth2/code/company` | Browser | Xử lý code/state và hoàn tất login khi hợp lệ |
| Mobile gửi `GET /api/orders` kèm Bearer JWT hợp lệ, có `orders.read` | API | Kiểm tra token, kiểm authority và tiếp tục tới controller |
| Mobile gửi `GET /api/orders` không có token | API | Thường trả 401, không chuyển sang trang login HTML |
| Token hợp lệ nhưng thiếu `orders.read` | API | Thường trả 403 |
| Browser gọi `POST /account/change-email` bằng session | Browser | Cần đáp ứng CSRF protection và phân quyền tương ứng |

## 8. Token, session và Authentication: không đặt chung một giỏ

Mọi ví dụ đều có từ “token”, nhưng có các đối tượng khác nhau:

| Đối tượng | Thường thấy ở đâu? | Mục tiêu |
|---|---|---|
| **Authorization code** | Redirect callback sau khi IdP cho phép, dùng ngắn hạn | Client trao đổi ở token endpoint để nhận token |
| **OIDC ID token** | OAuth2/OIDC Login client | Xác minh thông tin danh tính của người dùng cho client |
| **Access token** | OAuth2 Client gửi sang Resource Server | Cho phép truy cập API trong scope/audience hợp lệ |
| **Refresh token** | Client gửi đến Authorization Server | Xin access token mới theo chính sách |
| **Session cookie / JSESSIONID** | Browser trao đổi với web app | Định danh phiên đăng nhập/trạng thái trên web app |

Một browser đăng nhập thành công bằng OIDC có thể có **session cookie** của portal, trong khi access token do IdP phát hành được portal quản lý phía server. Browser không bắt buộc phải thấy access token ở localStorage. Đó là một thiết kế BFF/server-rendered khả thi.

**Access token không phải ID token.** Dù hai token có thể đều có dạng JWT, resource server phải kiểm tra **access token** được dành cho API của mình, gồm issuer, audience, thời hạn, scope và những ràng buộc phù hợp. Một ID token dành cho OAuth2 Client không được tự xem là access token của API.

**SecurityContext không bằng OAuth2AuthorizedClient.** Sau login, `Authentication` cho biết ai đang xác thực trong portal; `OAuth2AuthorizedClient` là nơi quản lý token/grant được cấp để client gọi dịch vụ khác. Hai đối tượng có liên hệ nhưng phục vụ hai quyết định khác nhau.

**JWT không tự tạo login session.** Resource Server có thể xác minh JWT trên mỗi request và vận hành stateless. OAuth2 Login thường tạo session browser; đó là hai mô hình trạng thái riêng, có thể chung codebase nhưng nên ranh giới rõ.

## 9. Khác biệt về endpoint và lỗi thường gặp

| Thành phần | Endpoint/đường truyền thường gặp | Khi lỗi |
|---|---|---|
| OAuth2 Login | `/oauth2/authorization/company`, callback `/login/oauth2/code/company` | Login failure, redirect phù hợp, lỗi `state`, `redirect_uri`, ID token, provider |
| OAuth2 Client | Token endpoint của IdP; request từ app tới API bên ngoài | `invalid_client`, `invalid_grant`, timeout, scope không phù hợp, refresh thất bại |
| Resource Server | Request vào `/api/**` với `Authorization: Bearer` | 401 khi thiếu/sai token; 403 khi thiếu quyền |
| Authorization Server | Authorization endpoint, token endpoint, JWKS, introspection/revocation tùy server | Từ chối grant, cấp token, thu hồi token |

Dòng `spring.security.oauth2.client.registration.company` dùng cho client đăng nhập/gọi API, trong khi `spring.security.oauth2.resourceserver.jwt.issuer-uri` dùng cho API xác minh token. Hai cấu hình có thể cùng trỏ tới một IdP nhưng **không thay thế nhau**.

Đừng tự suy rằng Resource Server sẽ tự mở `/oauth2/token`: Spring Security Resource Server chỉ **kiểm token được gửi đến**, không biến ứng dụng thành một token issuer.

## 10. Lỗi cấu hình và cách chẩn đoán

### Lỗi 1 — Bật `oauth2ResourceServer().jwt()` rồi chờ có nút Google Login

Resource Server không tạo authorization redirect hoặc session login. Để browser đăng nhập cần **OAuth2 Login** và client registration tương ứng.

### Lỗi 2 — Bật `oauth2Login()` rồi cho rằng mọi `/api/**` nhận Bearer token

OAuth2 Login xử lý browser login và `SecurityContext`; kiểm Bearer token từ client khác cần **Resource Server**. Nếu app có cả hai, tách chain và kiểm tra hành vi redirect/401 đúng thiết kế.

### Lỗi 3 — Nghĩ `oauth2Client()` sẽ tự cấp token

OAuth2 Client **xin token từ Authorization Server** thông qua grant hợp lệ; Spring Security Client không ký/phát hành token cho bên khác. Nếu muốn cấp token, phải có Authorization Server phù hợp.

### Lỗi 4 — Dùng `client_credentials` để đại diện người dùng đã login

`client_credentials` thông thường đại diện cho **client application**, không mang quyền ủy quyền trực tiếp của người dùng cuối. Nếu API yêu cầu truy cập theo danh tính user, cần luồng ủy quyền cho user, chính sách scope/resource và token phù hợp.

### Lỗi 5 — API nhận ID token như access token

ID token của OIDC được phát hành để client xác nhận đăng nhập, không phải giấy phép truy cập mọi API. Resource Server phải validate access token dành cho nó; không chỉ đọc `sub` rồi cho phép truy cập.

### Lỗi 6 — Có chữ ký JWT hợp lệ là đủ

Resource Server vẫn phải kiểm `iss`, `aud`, `exp`, `nbf`, scope/quyền, thuật toán/key, và các điều kiện nghiệp vụ. Đặc biệt, **audience validator có thể cần cấu hình riêng**. Một token hợp lệ của API A không mặc nhiên được phép dùng ở API B.

### Lỗi 7 — Tắt session và CSRF cho toàn bộ ứng dụng “vì OAuth2”

Nếu browser dùng session/cookie để login, tắt CSRF toàn cục có thể mở rủi ro. API Bearer-only và web login cần chính sách riêng; `SessionCreationPolicy.STATELESS` ở API chain không nên áp lẫn sang browser chain.

### Lỗi 8 — Lưu access token/refresh token vào log hoặc đưa vào URL

Token là credential. Dùng HTTPS, secret store/kho token an toàn, giới hạn scope và lifetime; không ghi token trong log, analytics, shell history, URL, exception message hay hệ thống telemetry.

### Lỗi 9 — Không phân biệt lỗi 401 và 403

401 nghĩa là request không có xác thực hợp lệ theo yêu cầu; 403 thường nghĩa là đã được xác thực nhưng không đủ quyền. Nếu API bị redirect sang HTML login, hãy xem lại **filter chain/entry point**, không mặc định coi đó là lỗi access token.

### Lỗi 10 — Không để ý proxy, issuer và redirect URI

Login có thể thất bại vì `redirect_uri` không trùng URI đã đăng ký, sai `{baseUrl}` sau reverse proxy hoặc sai hostname/scheme. Resource Server có thể từ chối token do `iss` không khớp, JWKS không truy cập được hoặc `aud` không hợp lệ. Cần xử lý đúng forwarded headers từ proxy đáng tin; không mở trust vô hạn cho header từ Internet.

## 11. Ví dụ Java 17 độc lập để luyện nhận diện vai trò

Trước khi viết cấu hình Spring, một cách thực hành nhanh là phân loại tình huống theo chiều hoạt động. Ví dụ Java sau **chỉ là mô hình học tập** để ghi nhớ ba vai trò, không thực thi OAuth2 và không cấp/kiểm token thật.

Tạo tệp `OAuth2RoleChooserDemo.java`:

```java
public class OAuth2RoleChooserDemo {
    enum UseCase {
        LOGIN_BROWSER,
        CALL_EXTERNAL_API,
        VALIDATE_INCOMING_BEARER
    }

    static String springFeature(UseCase useCase) {
        return switch (useCase) {
            case LOGIN_BROWSER -> "OAuth2 Login (uses OAuth2 Client)";
            case CALL_EXTERNAL_API -> "OAuth2 Client";
            case VALIDATE_INCOMING_BEARER -> "OAuth2 Resource Server";
        };
    }

    public static void main(String[] args) {
        System.out.println("Browser login: " +
                springFeature(UseCase.LOGIN_BROWSER));
        System.out.println("Outbound API: " +
                springFeature(UseCase.CALL_EXTERNAL_API));
        System.out.println("Inbound Bearer: " +
                springFeature(UseCase.VALIDATE_INCOMING_BEARER));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac OAuth2RoleChooserDemo.java
java OAuth2RoleChooserDemo
```

Đầu ra chính xác:

```text
Browser login: OAuth2 Login (uses OAuth2 Client)
Outbound API: OAuth2 Client
Inbound Bearer: OAuth2 Resource Server
```

Ví dụ độc lập sử dụng `switch` expression của Java 17. Các ví dụ `SecurityFilterChain`, `OAuth2AuthorizedClientManager` trong phần trước là **code phụ thuộc Spring Boot/Spring Security**, nên cần project với dependencies và IdP thực tế; không thể kỳ vọng biên dịch bằng `javac` trần.

## 12. Checklist thực hành cho một ứng dụng cụ thể

1. **Viết sơ đồ request**: ai gọi ai, request nào là browser redirect, request nào có Bearer token đi vào, request nào client gửi ra ngoài.
2. **Xác định role** của từng service: OAuth2 Client, Resource Server, Authorization Server hoặc nhiều vai trò.
3. **Chọn dependency**: với Spring Boot dùng starter `spring-boot-starter-oauth2-client` cho Login/Client, và `spring-boot-starter-oauth2-resource-server` cho API Bearer.
4. **Đăng ký client** với IdP: client ID, client authentication, grant type, redirect URI và scope đúng; không nhúng secret vào frontend.
5. **Cấu hình login chain** nếu cần browser login: authorization code/OIDC, state/PKCE, session và CSRF phù hợp.
6. **Cấu hình client outbound** nếu cần gọi API: authorized-client manager, lưu/refresh token an toàn, scope/audience đúng tài nguyên.
7. **Cấu hình API chain** nếu cần inbound Bearer: issuer, JWT hoặc introspection, audience, authority mapping và business authorization.
8. **Thử các nhánh lỗi**: anonymous browser redirect, API thiếu token 401, token thiếu scope 403, token sai issuer/audience, refresh hết hạn, logout và revocation.
9. **Kiểm tra rò rỉ bí mật**: không log authorization code, client secret, access token, refresh token hay session cookie; kiểm soát HTTPS và cấu hình proxy.

### Bốn câu hỏi tự kiểm tra

**Câu 1:** Website có nút “Login with IdP” và sau login cần gọi một API bên ngoài thay người dùng. Cần thành phần nào?

**Trả lời:** OAuth2 Login cho browser authentication, và hạ tầng OAuth2 Client/authorized client để quản lý access token khi gọi API bên ngoài. Nếu API bên ngoài do một ứng dụng khác quản lý, chính ứng dụng API đó là Resource Server.

**Câu 2:** Một ứng dụng không có UI, chỉ nhận `Authorization: Bearer` từ mobile app. Có cần `oauth2Login()` không?

**Trả lời:** Không. Phần cần thiết là Resource Server, chọn JWT validation hoặc introspection. Login browser chỉ cần nếu sản phẩm thực sự có luồng đăng nhập tương tác.

**Câu 3:** Backend job cần lấy token bằng `client_credentials` để gọi API. Bật Resource Server ở job có giúp xin token không?

**Trả lời:** Không. Job đóng vai **OAuth2 Client**, dùng client registration và authorized-client manager/provider thích hợp để xin access token từ Authorization Server.

**Câu 4:** Một service có `oauth2Login()`, `oauth2Client()` và `oauth2ResourceServer()` thì đã phát hành được refresh token cho client khác chưa?

**Trả lời:** Chưa. Các tính năng ấy không thay thế Authorization Server và token endpoint. Service chỉ có thể phát hành OAuth tokens nếu có thành phần Authorization Server được thiết kế, cấu hình và vận hành riêng.

**Ghi nhớ:** **OAuth2 Login là tình huống người dùng đăng nhập qua IdP; OAuth2 Client là ứng dụng xin và dùng token để gọi API; OAuth2 Resource Server là API xác minh token đi vào.** Luồng đúng được xác định bởi vai trò request, cách quản lý trạng thái và trách nhiệm bảo mật của từng thành phần.

## Tài liệu tham khảo chính thức

- [Spring Security — OAuth2 overview, Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): phân loại Resource Server, Client, Authorization Server và vị trí của Login trong Client.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/): luồng đăng nhập dựa trên authorization code.
- [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): client registration, redirect URI và cấu hình `oauth2Login`.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `oauth2Client`, `OAuth2AuthorizedClientManager` và các grant.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT Bearer token.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): kiểm tra token qua introspection.
