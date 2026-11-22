# Vai trò OAuth2 Client, OAuth2 Login và OpenID Connect trong ứng dụng Servlet

**Phạm vi:** Spring Security cho **Servlet/Spring MVC** (Spring Boot 3.x, Spring Security 6.x, Java 17+). Bài này giúp phân biệt OAuth2 Client, OAuth2 Login và OpenID Connect (OIDC), hiểu luồng đăng nhập Authorization Code, biết token nào dùng để xác minh người dùng, token nào dùng để gọi API, và cấu hình được một web application với OIDC provider. Spring WebFlux có cấu hình reactive riêng, không dùng nguyên các API Servlet dưới đây.

## 1. Ba khái niệm cùng xuất hiện nhưng có trách nhiệm khác nhau

**OAuth 2.0** là framework **ủy quyền truy cập tài nguyên**. Một ứng dụng (client) được authorization server cấp quyền gọi một resource server thay mặt người dùng hoặc thay mặt chính ứng dụng. OAuth 2.0 **không tự quy định cách xác thực danh tính người dùng** để một ứng dụng kết luận “người này là ai”.

**OAuth2 Client** trong Spring Security là năng lực của ứng dụng đóng vai **client**: quản lý client registration, khởi tạo các luồng ủy quyền, lấy/lưu access token và sử dụng token để gọi API được cấp quyền. Client có thể chạy cùng người dùng đã đăng nhập hoặc chạy không có người dùng, chẳng hạn batch job dùng grant `client_credentials`.

**OAuth2 Login** dùng luồng OAuth 2.0 `authorization_code` để **đăng nhập người dùng vào chính ứng dụng Spring MVC**. Spring Security nhận kết quả từ provider, thiết lập `Authentication` trong `SecurityContext` và thường duy trì đăng nhập bằng HTTP session. OAuth2 Login có thể chạy với provider OAuth2-specific hoặc provider hỗ trợ OIDC.

**OpenID Connect (OIDC)** bổ sung lớp **xác thực danh tính** trên OAuth 2.0. OIDC provider phát **ID token**, client xác minh các ràng buộc chuẩn để xác nhận danh tính. Khi phạm vi yêu cầu có `openid` và provider hỗ trợ OIDC, Spring Security OAuth2 Login có thể tạo `OidcUser`.

| Khả năng | Giải quyết câu hỏi nào? | Kết quả chính | Không đồng nghĩa với |
| --- | --- | --- | --- |
| `oauth2Client()` | Ứng dụng lấy/quản lý token để gọi API ngoài ra sao? | `OAuth2AuthorizedClient` (registration + principal + access token, có thể có refresh token). | Đăng nhập người dùng hoặc xác minh bearer token của API đến. |
| `oauth2Login()` | User đăng nhập web app qua IdP thế nào? | `Authentication`, `SecurityContext`, thường có session cookie. | Tự động cho phép mọi API hoặc mọi quyền. |
| OIDC với scope `openid` | Làm sao xác minh danh tính theo một giao thức chuẩn? | ID token, `OidcUser`, tùy trường hợp UserInfo. | API authorization. |
| `oauth2ResourceServer()` | API kiểm tra access token do caller gửi đến thế nào? | Xác minh JWT hoặc opaque token và quyền API. | OAuth2 Client hay OAuth2 Login. |
| Authorization Server / OpenID Provider | Ai xác thực user, xin consent, cấp code và token? | Code, access token, ID token (nếu OIDC). | Ứng dụng client tiêu thụ token. |

**Ví dụ:** Portal dùng SSO doanh nghiệp để đăng nhập nhân viên bằng OIDC (**OAuth2 Login + OIDC**), sau đó dùng access token để gọi Calendar API (**OAuth2 Client**). Calendar API kiểm tra access token và quyền xem lịch (**OAuth2 Resource Server**). Nhân viên đăng nhập thành công vào Portal chưa chắc đã có quyền `calendar.read` hay quyền xem lịch của đồng nghiệp.

## 2. Nhận diện các tác nhân và vật liệu trong giao thức

| Khái niệm | Vai trò |
| --- | --- |
| **Resource Owner** | Chủ thể có quyền với dữ liệu; trong luồng có người dùng thường là người dùng. |
| **Client** | Ứng dụng yêu cầu quyền truy cập; ở đây là Spring MVC web app. |
| **Authorization Server** | Xác thực/đưa yêu cầu consent, phát authorization code và tokens. |
| **OpenID Provider (OP)** | Authorization Server hỗ trợ OIDC và phát ID token. |
| **Resource Server** | API nhận access token để kiểm tra quyền trước khi trả tài nguyên. |
| **Client Registration** | Thông tin client ID, provider, redirect URI, scopes, grant type, có thể có client secret. |
| **Principal / Authentication** | User/workload đã được Spring Security xác định và authorities ở ứng dụng. |
| **Authorized Client** | Bản ghi client và principal được cấp token để gọi API. |

Một provider có thể đóng cả vai authorization server và OIDC provider; một ứng dụng cũng có thể cùng lúc đóng nhiều vai. Nhưng phải phân biệt ở **từng request**: browser về web app với session cookie không giống backend gọi API với bearer access token.

**Client ID** thường là định danh công khai. **Client secret** là bí mật dành cho confidential client chạy server-side và không được nhúng vào JavaScript, HTML hay repository. **Redirect URI** phải đăng ký đúng với provider, trỏ về callback mà Spring Security xử lý; tránh wildcard redirect mở rộng hoặc redirect được tạo từ input không đáng tin cậy.

### 2.1 Bốn loại vật liệu dễ nhầm

**Authorization code** là giá trị tạm thời nhà cung cấp trả qua callback sau khi user đăng nhập/đồng ý. Backend đổi code ở token endpoint lấy token; code ngắn hạn và thường chỉ sử dụng một lần. Không dùng code làm bearer access token.

**Access token** thể hiện quyền gọi resource được cấp. Client gửi access token tới **resource server phù hợp**, ví dụ:

```http
GET /v1/calendar HTTP/1.1
Host: calendar.example.net
Authorization: Bearer <access-token-for-calendar>
```

Token có thể là JWT hoặc opaque; format của access token **không mặc nhiên là một hợp đồng cho client**, và có thể chỉ resource server mới được giải thích nội dung. API phải kiểm tra issuer, audience, scope/permissions và các ràng buộc liên quan theo định dạng token.

**ID token** là JWT theo OIDC, hướng đến **client ứng dụng** nhằm xác nhận danh tính và sự kiện đăng nhập. Những claim cốt lõi thường gồm:

- `iss`: OpenID Provider phát hành ID token.
- `sub`: subject identifier của người dùng trong issuer.
- `aud`: audience; phải bao gồm client ID hợp lệ.
- `exp`, `iat`: thời hạn hết hiệu lực và thời điểm phát hành.
- `nonce`: nếu dùng trong authentication request, phải được ràng buộc/kiểm tra theo giao thức.
- Các claim tùy chọn như `name`, `email`, `email_verified`, `auth_time` có thể có hoặc không.

ID token **không phải access token** để gọi API nghiệp vụ. Không đưa ID token vào `Authorization: Bearer` thay access token; resource server thường phải từ chối token sai loại/sai audience.

**Refresh token** (nếu được cấp) giúp client lấy access token mới. Nó không luôn tồn tại: còn tùy provider, grant, scopes, chính sách rotation và consent. Bảo vệ refresh token như bí mật, không ghi log/trả ra frontend tùy tiện.

| Dữ liệu | Dùng để | Không nên làm |
| --- | --- | --- |
| `code` | Đổi token một lần tại token endpoint | Dùng lâu dài, log, replay. |
| `access_token` | Gọi đúng resource server được cấp quyền | Gửi cho API sai audience, nhúng vào URL. |
| `id_token` | Xác thực danh tính ở OIDC client | Sử dụng như API bearer token. |
| `refresh_token` | Xin access token mới theo provider policy | Gửi qua browser hoặc log. |
| Cookie session như `JSESSIONID` | Browser giữ phiên đăng nhập với Servlet app | Xem nó là bearer access token của dịch vụ ngoài. |

**OIDC `openid`** là yêu cầu dùng lớp xác thực OIDC. `profile`/`email` có thể cho phép nhận thêm claims hoặc UserInfo, nhưng không đảm bảo email, tên hay roles sẽ xuất hiện. Để định danh ổn định, cặp **`iss` + `sub`** thường đáng tin cậy hơn email, vì email có thể đổi hoặc chưa xác minh. Claims nhận diện không tự quyết định authorization nghiệp vụ.

## 3. Authorization Code + OIDC chạy thế nào trên Servlet?

Giả sử Spring MVC Portal chạy tại `http://localhost:8080`, có registration ID `idp` và provider OIDC được cấu hình chính xác.

```text
Browser                    Spring MVC / Spring Security                   OIDC Provider
   |                                    |                                    |
   | GET /me                            |                                    |
   |----------------------------------->|                                    |
   | 302 /login (nếu chưa đăng nhập)    |                                    |
   |<-----------------------------------|                                    |
   | GET /oauth2/authorization/idp      |                                    |
   |----------------------------------->|                                    |
   | 302 /authorize?...state=...        |                                    |
   |<-----------------------------------|                                    |
   | GET authorization endpoint                                              |
   |------------------------------------------------------------------------->|
   |                User login / consent nếu cần                              |
   | 302 callback?code=...&state=...                                          |
   |<-------------------------------------------------------------------------|
   | GET /login/oauth2/code/idp?code=...&state=...                            |
   |----------------------------------->|                                    |
   |                                    | POST token endpoint đổi code       |
   |                                    |----------------------------------->|
   |                                    | access token + ID token (+refresh?)|
   |                                    |<-----------------------------------|
   |                                    | Xác minh OIDC, xây OidcUser        |
   |                                    | Lưu Authentication/authorized client|
   | 302 về trang đích                  |                                    |
   |<-----------------------------------|                                    |
   | GET /me + session cookie           |                                    |
   |----------------------------------->|                                    |
   | 200 JSON phản hồi                   |                                    |
   |<-----------------------------------|                                    |
```

**Từng bước:**

1. `OAuth2AuthorizationRequestRedirectFilter` quản lý đường dẫn mặc định `/oauth2/authorization/{registrationId}`, tạo authorization request với `client_id`, `scope`, `redirect_uri`, `response_type=code`, `state` và các tham số liên quan. Spring lưu request gốc để so khớp callback.
2. Browser được chuyển tới provider; ứng dụng Spring MVC **không nhận mật khẩu của user**. Provider có thể yêu cầu MFA, consent hoặc tận dụng phiên SSO có sẵn.
3. Provider chuyển browser về callback mặc định `/login/oauth2/code/{registrationId}` với `code` và `state`. `OAuth2LoginAuthenticationFilter` tiếp nhận kết quả, kiểm tra sự tương quan/điều kiện thích hợp rồi đổi code tại token endpoint.
4. Với OIDC, Spring Security xác minh ID token theo metadata/khóa công khai của provider, các claim/ràng buộc phù hợp (issuer, audience, thời hạn, nonce nếu sử dụng), có thể lấy UserInfo, rồi tạo `OidcUser`.
5. OAuth2 Login tạo `Authentication` trong `SecurityContext`, được duy trì qua session trong mô hình web truyền thống. Browser thường chỉ gửi session cookie đến ứng dụng ở request tiếp theo.
6. OAuth2 Client có thể lưu `OAuth2AuthorizedClient` để backend sử dụng access token khi gọi resource server ngoài. **Không tự động phát access token cho trình duyệt hoặc gọi mọi API với token đó.**

**State, nonce và PKCE khác nhau:**

- `state` ràng buộc callback với authorization request ban đầu, là biện pháp phòng login CSRF/mix-up trong ngữ cảnh thích hợp. Không bỏ kiểm tra vì redirect callback “trông có vẻ đúng”.
- `nonce` giúp ràng buộc ID token với authentication request trong OIDC, giảm replay/token substitution khi được dùng theo giao thức.
- **PKCE** dùng `code_challenge` và `code_verifier` để ràng buộc authorization code với bên khởi tạo; đặc biệt cần với public client, và nên xem xét ở confidential client khi provider/Spring hỗ trợ. PKCE **không thay thế `state` hoặc nonce**. Tính năng PKCE kích hoạt cụ thể phụ thuộc loại client/cấu hình; cần kiểm tra authorization request thật thay vì mặc định suy đoán mọi luồng đã có PKCE.
- Redirect URI hợp lệ, HTTPS, không làm lộ code và kiểm soát session là yêu cầu bổ sung. Không tắt validation để sửa lỗi tích hợp.

## 4. Các thành phần Spring Security liên quan

| Thành phần | Chức năng |
| --- | --- |
| `ClientRegistration` | Chứa client ID, grant, redirect URI, scopes và endpoint provider. |
| `ClientRegistrationRepository` | Tra cứu registration theo `registrationId`, ví dụ `idp`. |
| `OAuth2AuthorizationRequestRedirectFilter` | Khởi tạo yêu cầu và redirect browser đến authorization endpoint. |
| `AuthorizationRequestRepository` | Lưu authorization request gốc để kiểm tra callback; mặc định thường gắn với session. |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback authorization code để đăng nhập. |
| `OAuth2UserService` / `OidcUserService` | Tạo principal từ thông tin user/provider sau bước xác thực tương ứng. |
| `Authentication` và `SecurityContext` | Lưu user và authorities ở ứng dụng. |
| `OAuth2AuthorizedClient` | Gắn registration, principal, access token, refresh token nếu có. |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Lưu và tải authorized client theo request/session hoặc storage service. |
| `OAuth2AuthorizedClientManager` | Điều phối authorize/re-authorize, hỗ trợ các grant và refresh phù hợp provider đã cấu hình. |

**Điểm phân biệt:** `oauth2Login()` kích hoạt luồng đăng nhập user, còn `oauth2Client()` cung cấp hỗ trợ làm client đối với API. Hai chức năng có thể sử dụng cùng client registration và authorized client, nhưng không tự động thay thế nhau.

Nếu provider chỉ hỗ trợ OAuth2 login theo các attribute riêng, principal thường là `OAuth2User`. Khi request scope `openid` với provider OIDC, principal có thể là `OidcUser` có thêm ID token và UserInfo. Không ép kiểu `OidcUser` khi provider OAuth2-only.

## 5. Ví dụ hoàn chỉnh: Spring Boot MVC đăng nhập qua OIDC

Mục tiêu: trang công khai có link login, endpoint `GET /me` chỉ cho user đã login, trả subject OIDC và scopes đã cấp mà **không làm lộ token**. Ví dụ dùng **server-side confidential client**, không phải SPA/browser public client.

### 5.1 Tạo project và đăng ký client ở provider

Tạo dự án Gradle qua Spring Initializr với **Spring Boot 3.x**, **Java 17+**, các dependency **Spring Web**, **Spring Security**, **OAuth2 Client**. Dùng Gradle wrapper của project để chạy. Provider phải hỗ trợ OIDC discovery, scope `openid`, authorization-code grant và callback:

```text
http://localhost:8080/login/oauth2/code/idp
```

Tại provider, đăng ký client ID/secret thật, redirect URI chính xác và scopes cần dùng. Với production, dùng HTTPS và domain thật. `idp` là **registration ID tự đặt trong Spring**, phải khớp tên trong config và đường dẫn callback. Các URL `example.com` bên dưới chỉ là **placeholder**, không thể dùng để login nếu chưa có provider thật.

**`src/main/resources/application.yml`**

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          idp:
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          idp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Ví dụ issuer có thể mang dạng `https://identity.example.com/realms/company`; ứng dụng cần giá trị issuer thật, đúng metadata do OP công bố. Spring Boot tự phát hiện OIDC authorization/token/JWKS (và UserInfo nếu có) thông qua `issuer-uri` khi provider hỗ trợ discovery. Biến môi trường giữ client secret ở backend, không commit vào Git.

### 5.2 Cấu hình SecurityFilterChain Servlet

**`src/main/java/com/example/oidcdemo/SecurityConfig.java`**

```java
package com.example.oidcdemo;

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
                .requestMatchers("/", "/index.html", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

`oauth2Login` cho phép Spring Security xử lý redirect/callback và tạo trạng thái đăng nhập. `oauth2Client` hỗ trợ sử dụng OAuth2 authorized clients. Mặc định CSRF protection vẫn hoạt động cho unsafe HTTP methods; đoạn demo không tắt CSRF hoặc cho phép mọi API chỉ vì người dùng đã đăng nhập.

### 5.3 Controller đọc OidcUser và authorized client

**`src/main/java/com/example/oidcdemo/MeController.java`**

```java
package com.example.oidcdemo;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OidcUser user,
            @RegisteredOAuth2AuthorizedClient("idp")
                OAuth2AuthorizedClient client) {

        // Không xuất ID token, access token hoặc refresh token.
        return Map.of(
            "subject", user.getSubject(),
            "grantedScopes", client.getAccessToken().getScopes()
        );
    }
}
```

Controller này được thiết kế cho **OIDC provider** đúng chuẩn; `OidcUser` không phù hợp nếu bạn đổi sang một OAuth2-only provider. `@RegisteredOAuth2AuthorizedClient("idp")` tải client đã được ủy quyền của principal hiện tại. Nó không bảo đảm token được cấp mọi scope; đọc từ token thật, không gán quyền theo scope được yêu cầu trong YAML.

### 5.4 Trang HTML và ứng dụng chính

**`src/main/resources/static/index.html`**

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>OIDC demo</title>
</head>
<body>
  <h1>Đăng nhập OIDC</h1>
  <a href="/oauth2/authorization/idp">Đăng nhập qua IdP</a>
  <a href="/me">Xem danh tính</a>
</body>
</html>
```

**`src/main/java/com/example/oidcdemo/OidcDemoApplication.java`**

```java
package com.example.oidcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcDemoApplication.class, args);
    }
}
```

Các file Java cần Spring dependencies trên classpath, **không chạy bằng `javac` thuần**. Khi đã cấu hình provider thật và biến môi trường, chạy từ project có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell: `.\gradlew.bat bootRun`. Truy cập `http://localhost:8080/` rồi nhấn đăng nhập. Sau khi IdP hoàn tất luồng, mở `/me`.

Ví dụ dữ liệu trả về (giá trị subject và scopes phụ thuộc provider):

```json
{
  "subject": "employee-123",
  "grantedScopes": ["openid", "profile", "email"]
}
```

Dù trả subject, endpoint vẫn cần authentication; không công bố token. HTTP session giữ trạng thái đăng nhập của **web app**; authorized client giữ token để backend gọi **API được cấp quyền**. Ở môi trường thực tế, dùng authorities và business rules để kiểm tra quyền xem dữ liệu.

## 6. OAuth2 Client gửi access token đến Resource Server

Giả sử sau login backend cần gọi `https://calendar-api.example.net/v1/calendar`. `OAuth2AuthorizedClient` đại diện cho một client đã được cấp access token; ứng dụng có thể lấy nó từ request trong controller. Đoạn **minh họa tích hợp** sau là một method đặt trong Spring MVC controller đã import `@GetMapping`, `@RegisteredOAuth2AuthorizedClient` và `OAuth2AuthorizedClient`; URL API cần thay bằng endpoint thật:

```java
@GetMapping("/calendar")
public String calendar(
        @RegisteredOAuth2AuthorizedClient("idp")
            OAuth2AuthorizedClient client) {

    String accessToken = client.getAccessToken().getTokenValue();

    return org.springframework.web.client.RestClient.create()
        .get()
        .uri("https://calendar-api.example.net/v1/calendar")
        .headers(h -> h.setBearerAuth(accessToken))
        .retrieve()
        .body(String.class);
}
```

**Không gửi ID token thay access token** và không gửi access token của OIDC provider cho một API ngoài không phải đối tượng nhận token. Việc call thành công phụ thuộc **audience, scope, consent, resource server policy**. Nếu resource server trả 401/403, login đã hoàn tất vẫn có thể đúng; cần kiểm tra loại token, hạn token, issuer/audience và quyền API.

`OAuth2AuthorizedClient` có thể chứa refresh token; quản lý vòng đời token nên dùng các cơ chế Spring Security thích hợp như `OAuth2AuthorizedClientManager` với provider hỗ trợ `refresh_token`. Đọc trực tiếp `getAccessToken().getTokenValue()` **không phải một hợp đồng tự refresh trong mọi trường hợp**. Đừng tự viết retry vô hạn, log token hoặc truyền token vào URL.

**BFF/server-side model:** Browser chỉ gửi cookie phiên đến Portal; Portal dùng access token để gọi API phía sau. Mô hình này giảm nhu cầu giữ access token ở JS, nhưng vẫn phải bảo vệ session cookie, CSRF và authorization.

### 6.1 Client credentials khác OAuth2 Login

Service-to-service hoặc batch job chạy không có user thường cần **`client_credentials`**. Nó không tự sinh OIDC ID token hay HTTP session người dùng và không cần màn hình login. Ví dụ registration riêng:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          service-api:
            provider: machine-idp
            client-id: ${SERVICE_CLIENT_ID}
            client-secret: ${SERVICE_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - api.read
        provider:
          machine-idp:
            token-uri: https://identity.example.com/oauth2/token
```

Manager dành cho code chạy **ngoài HttpServletRequest** có thể dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` với client-credentials provider. Đây là **snippet bean** (cần import các kiểu liên quan từ Spring OAuth2 Client), không phải thay toàn bộ ví dụ OIDC phía trên:

```java
@Bean
OAuth2AuthorizedClientManager backgroundClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations, authorizedClients
    );
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

Khi gọi `manager.authorize(...)`, tạo `OAuth2AuthorizeRequest` với `clientRegistrationId="service-api"` và principal ổn định như `"scheduled-job"`, kiểm tra kết quả khác null rồi sử dụng access token đúng Resource Server. Principal này phục vụ quản lý authorized client, **không phải user cuối**. Trong ứng dụng vừa có login vừa có background job, thiết kế manager/authorized-client provider theo từng grant và ngữ cảnh thực tế.

## 7. OAuth2 Login không tự biến ứng dụng thành Resource Server

**Web user gọi ứng dụng đã login qua session:**

```http
GET /me HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=<session-id>
```

Spring Security Servlet truy xuất `SecurityContext` gắn với session. Không yêu cầu browser gửi ID token trong header để đọc `/me`.

**Một mobile app/service gọi API với bearer token:**

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token-for-orders-api>
```

Nếu backend cần xử lý request thứ hai, phải triển khai **OAuth2 Resource Server** (JWT validation hoặc opaque-token introspection, issuer/audience/scope và quyền API). Chỉ thêm `spring-boot-starter-oauth2-client` + `oauth2Login()` không khiến API tự xác minh bearer token được đưa vào.

Một ứng dụng có thể hỗ trợ cả browser session và bearer API, nhưng cần thiết kế filter chain, entry point, CSRF, session và authorization rõ ràng. Chỉ vì đã có OIDC Login không có nghĩa endpoint API chấp nhận access token của mọi provider.

### 7.1 Role/authority không tự xuất hiện từ OIDC

User đã được xác minh danh tính chưa chắc có `ROLE_ADMIN`. `openid` cung cấp cơ chế identity; group/role có thể là claim tùy provider, cần map vào `GrantedAuthority` hoặc lấy từ hệ thống quyền nội bộ theo quy tắc đáng tin cậy. Ví dụ biến thể SecurityConfig:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/", "/index.html", "/error").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Đây là **đoạn thay thế** trong DSL, không phải chương trình đầy đủ. Nếu chưa map `ROLE_ADMIN`, request `/admin/**` bị chặn là đúng. Cần kiểm tra object-level authorization, ownership và tenant boundaries ở backend thay vì tin role/email client gửi lên.

## 8. Bảo mật xuyên suốt vòng đời login và token

### 8.1 Khi khởi tạo và xử lý redirect

- **State** phải gắn callback với request login khởi đầu; không bỏ xác minh hoặc tái dùng authorization request vô hạn.
- **Nonce OIDC** được kiểm tra theo luồng OIDC thích hợp; không coi nonce là access token.
- **PKCE** nên theo quy tắc của loại client/provider; HTTPS và redirect URI chính xác vẫn cần.
- **Callback** phải ở domain/port/scheme được provider cho phép. Đặc biệt sau reverse proxy, cấu hình external base URL và forwarded headers từ proxy **đáng tin cậy** để tránh redirect sai; không tin dữ liệu forwarding do client tùy ý cung cấp.
- Không dùng wildcard redirect quá rộng hay gắn code/token vào URL có thể rò rỉ sang bên thứ ba.

### 8.2 Khi lưu session và tokens

- Với web app Servlet, SecurityContext thường được duy trì trong HTTP session; session cookie production cần HTTPS, Secure, HttpOnly phù hợp, SameSite/domain/path hợp lý và session-fixation protection.
- Login qua OIDC **không tắt CSRF** cho POST/PUT/PATCH/DELETE khi ứng dụng dùng cookie session. OAuth2 `state` bảo vệ callback trong luồng login, không thay CSRF token cho mọi thao tác nghiệp vụ.
- Access token/refresh token thuộc thành phần backend quản lý; không in log, không đính vào query string, không trả trong JSON `/me`. Bảo vệ storage và quyền truy cập; nếu nhiều server cùng sử dụng session/token, thiết kế nơi lưu phù hợp.
- Refresh token có thể hết hạn, rotation hoặc bị thu hồi; xử lý refresh thất bại bằng reauthorization/login lại khi cần, không retry vô hạn.
- **Logout ứng dụng khác logout IdP**. Xóa session Portal không nhất thiết kết thúc SSO session tại provider; nếu cần Single Logout, triển khai OIDC RP-initiated logout hoặc cơ chế provider hỗ trợ.

### 8.3 Khi xác định người dùng và quyền

- Xác nhận issuer/audience/chữ ký/expiry và nonce đúng chuẩn; đừng tự base64-decode ID token rồi tự tin đó là danh tính.
- Cặp **`iss + sub`** phù hợp hơn email khi làm định danh liên kết tài khoản lâu dài; email có thể đổi, vắng mặt hoặc chưa được xác minh.
- **Scope của access token** là quyền liên quan resource; **quyền truy cập dữ liệu trong app** vẫn cần mapping và kiểm tra rõ ràng.
- Một token được cấp cho resource A không mặc nhiên được dùng ở resource B; API phải kiểm tra audience và authorization.

## 9. Kiểm chứng trên trình duyệt và bằng HTTP client

Sau khi điền provider thật và chạy ứng dụng:

**Kiểm tra authorization redirect:**

```bash
curl -i http://localhost:8080/oauth2/authorization/idp
```

Thường thấy HTTP **302** cùng `Location` sang authorization endpoint có `client_id`, `response_type=code`, `redirect_uri`, `scope` và `state`. Các tham số `nonce`, PKCE challenge hoặc khác có thể xuất hiện theo provider/config. `curl` chỉ kiểm tra redirect ban đầu, **không mô phỏng đầy đủ login/consent tương tác**.

**Kiểm tra bằng browser:**

1. Mở `http://localhost:8080/` rồi nhấp liên kết đăng nhập.
2. Kiểm tra trong DevTools → Network chuỗi redirect đến IdP và callback `/login/oauth2/code/idp`; tránh sao chép hoặc chia sẻ code/token/cookie ở URL và header.
3. Đăng nhập tại provider, xác nhận quay về web app và có session cookie hợp lệ. Truy cập `GET /me` để thấy subject/scopes đúng với dữ liệu IdP.
4. Xóa session hoặc logout rồi truy cập `/me`: chưa đăng nhập thì thường được redirect đến trang login (trừ khi custom entry point). Nếu IdP còn SSO session, có thể đăng nhập lại không cần nhập password.
5. Với API bên ngoài, kiểm tra access token được gửi đến **đúng audience** và có scope thực tế; phân biệt 401 (token/identity không hợp lệ) với 403 (thiếu quyền).

**Kiểm tra trường hợp lỗi:** sai redirect URI có thể bị provider từ chối; mất session/state giữa redirect và callback thường làm login thất bại; đổi issuer/JWKS sai phải bị từ chối; POST ứng dụng thiếu CSRF token khi dùng session có thể bị 403 dù OIDC login thành công.

## 10. Bảng chẩn đoán lỗi tích hợp

| Hiện tượng | Nguyên nhân có thể | Cách xác minh và xử lý |
| --- | --- | --- |
| Không vào được `/oauth2/authorization/idp` | Thiếu OAuth2 Client dependency, sai registration ID, client config chưa tạo. | Kiểm tra starter, `spring.security.oauth2.client.registration.idp` và route. |
| Provider báo `redirect_uri_mismatch` | Callback khác URI đã đăng ký: port, scheme, host, proxy. | So `redirect_uri` trên request với allowlist provider; rà proxy URL. |
| Không đọc được OIDC metadata | `issuer-uri` sai, provider không support discovery, lỗi mạng/TLS. | Kiểm tra issuer và endpoint discovery qua kết nối đáng tin cậy; không tắt TLS. |
| Callback báo invalid state/missing authorization request | Session mất, cookie không gửi, state không khớp, cụm server không chia sẻ session. | Rà session cookie, SameSite/Secure, proxy, session storage và callback. |
| ID token invalid / issuer / audience / nonce | Provider trả token không hợp lệ hoặc config sai. | Kiểm tra issuer, client ID, clock, public keys/metadata; không bỏ kiểm tra xác thực. |
| Principal không phải `OidcUser` | Dùng OAuth2-only provider hoặc scope `openid` không có/không hợp lệ. | Chọn kiểu `OAuth2User` khi OAuth2-only, hoặc cấu hình OIDC đúng. |
| `@RegisteredOAuth2AuthorizedClient` không có client | Sai registration, principal/session đổi, authorized client chưa lưu. | Kiểm tra registration ID, authenticated principal và client repository/service. |
| Đã login nhưng API ngoài trả 401 | Access token sai resource, hết hạn, thiếu bearer header, issuer/audience sai. | Dùng access token dành cho API; kiểm tra token lifecycle và resource server. |
| API ngoài trả 403 | Token hợp lệ nhưng thiếu scope/role/quyền dữ liệu. | Kiểm tra consent/scope thực tế và authorization phía API. |
| Portal liên tục redirect đến login | Cookie/session bị mất, callback bị lỗi, URL/proxy sai. | Xem Network và session cookie; bảo vệ cấu hình multi-instance. |
| Đã logout nhưng login lại không hỏi password | IdP vẫn có SSO session. | Phân biệt local logout với OP logout; thiết kế OIDC logout nếu nghiệp vụ cần. |

## 11. Chọn đúng cơ chế theo ứng dụng

| Bài toán | Cấu hình chính cần xem xét | Có người dùng tương tác? |
| --- | --- | --- |
| Spring MVC web đăng nhập SSO | `oauth2Login` + OIDC registration | Có |
| Web Portal đăng nhập rồi gọi API thay user | OIDC Login + OAuth2 Client + đúng API scopes/audience | Có |
| Background job gọi API theo danh tính service | OAuth2 Client với `client_credentials` | Không |
| REST API xác minh Bearer JWT/opaque token | OAuth2 Resource Server | Không nhất thiết |
| Ứng dụng vừa nhận browser cookie vừa nhận bearer API | Kết hợp session login và resource-server filters/authorization cẩn thận | Tùy request |
| SPA public client đăng nhập trực tiếp bằng browser | Authorization Code + PKCE, không đặt client secret trong frontend | Có |

**Checklist:** Xác định chính xác vai trò; dùng provider/issuer tin cậy; đặt client secret an toàn; cấu hình redirect URI chính xác; xử lý state/nonce/PKCE phù hợp; không nhầm ID token và access token; giữ session/cookie, CSRF và permissions đúng; mapping claims/roles có kiểm soát; đảm bảo API xác minh audience/scope; bảo vệ token và quản lý refresh/logout; kiểm thử cả login thành công lẫn callback, session và quyền API thất bại.

**Ghi nhớ:** **OAuth2 Client** quản lý quyền và access token để **gọi API**; **OAuth2 Login** thiết lập **phiên người dùng** trong Spring Security Servlet; **OIDC** cung cấp **xác thực danh tính chuẩn** dựa trên ID token. Ba chức năng bổ sung cho nhau, nhưng không thay thế vai trò Resource Server hay authorization logic của ứng dụng.
