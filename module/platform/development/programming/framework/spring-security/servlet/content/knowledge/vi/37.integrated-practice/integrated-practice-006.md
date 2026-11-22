# Tích hợp OAuth2 Login và gọi API bên ngoài thay mặt người dùng

## 1. Mục tiêu của bài thực hành tổng hợp

Một ứng dụng web Spring MVC cho phép người dùng **đăng nhập qua một nhà cung cấp danh tính (Identity Provider, IdP)** rồi truy cập một **API ở hệ thống khác thay mặt đúng người dùng đó**. Ví dụ, người dùng Alice mở một trang quản lý tài khoản, đăng nhập tại IdP và yêu cầu ứng dụng backend lấy hồ sơ từ Partner API. Ứng dụng không được tự ý lấy dữ liệu thuộc Bob, không để lộ access token ra trình duyệt và không nhầm ID Token với access token dành cho API.

Bài thực hành này kết hợp **Spring Security OAuth2 Login** và **Spring Security OAuth2 Client** ở **Servlet stack**, trên **Java 17+, Spring Boot 3.x, Spring Security 6.x**. Ta sẽ dựng một **backend-for-frontend (BFF)** đơn giản:

- Người dùng truy cập backend bằng trình duyệt; Spring Security chuyển tới IdP qua **Authorization Code flow**.
- Backend nhận callback OAuth2/OIDC, hoàn tất xác thực và giữ phiên đăng nhập bằng HttpSession/cookie.
- Spring Security lưu **OAuth2AuthorizedClient** liên kết với **client registration** và principal hiện tại; đối tượng này tham chiếu access token được cấp cho người dùng.
- Khi GET **/api/partner/profile**, backend lấy authorized client của đúng người dùng rồi gửi **Authorization: Bearer access_token** tới **https://api.example.test/v1/profile**.
- Partner API là **resource server** riêng, chịu trách nhiệm xác minh token, issuer/audience, expiry và scope; backend không gửi ID Token hoặc mật khẩu đăng nhập cho Partner API.
- Browser chỉ nhận dữ liệu hồ sơ phù hợp, **không** nhận raw access token, refresh token hay client secret.

**Giới hạn của ví dụ:** tên miền **idp.example.test** và **api.example.test** là placeholder không có dịch vụ thật. Mã là mẫu Spring Boot nhất quán, cần cung cấp IdP hỗ trợ OpenID Connect cùng Partner API, client registration và scopes thực tế để chạy luồng end-to-end. Bài test mock HTTP outbound có thể chạy độc lập với IdP nếu đặt vào dự án Boot đúng phiên bản.

## 2. Phân biệt đăng nhập và quyền gọi API

### 2.1. OAuth2 Login không tự cấp quyền gọi mọi API

**oauth2Login()** cho phép ứng dụng xác thực người dùng qua Authorization Server/IdP và tạo Authentication cho phiên web. **oauth2Client()** hỗ trợ client authorization và quản lý **OAuth2AuthorizedClient** khi ứng dụng cần gọi hệ thống ngoài. Hai chức năng có liên quan nhưng **không đồng nghĩa**.

| Thành phần | Vai trò trong bài | Điều cần tránh |
| --- | --- | --- |
| **Browser** | Giữ session cookie để truy cập BFF | Giữ refresh token hay client secret trong JavaScript |
| **Spring MVC BFF** | OAuth2 Client và RP, xử lý login/callback, lưu authorized client, gọi Partner API | Chuyển tiếp access token tùy ý đến URL do client cung cấp |
| **Authorization Server / IdP** | Xác thực Alice, cấp authorization code, đổi code lấy tokens | Cấp token sai audience hoặc scope vượt yêu cầu |
| **Partner API / Resource Server** | Nhận access token, kiểm tra chính sách của chính API | Tin session cookie của BFF hoặc ID Token thay access token |
| **OAuth2AuthorizedClient** | Liên kết ClientRegistration, principalName, access token và refresh token nếu có | Dùng token của Alice khi xử lý request của Bob |

Trong OIDC thường có:

- **ID Token:** mô tả sự kiện đăng nhập/danh tính cho client (RP), dành cho client có audience phù hợp. **Không** tự động dùng làm Bearer credential của Partner API.
- **Access Token:** credential để gọi resource API, có scope và audience phù hợp với resource server.
- **Refresh Token:** credential nhạy cảm dùng với token endpoint của AS để lấy access token mới khi được cấp. **Không gửi refresh token tới Partner API.**
- **Authorization Code:** mã ngắn hạn từ callback dùng ở backend để trao đổi token; không phải credential API.
- **Session cookie:** cách browser chứng minh phiên đã đăng nhập với BFF; không tương đương access token bên ngoài.

**OAuth2 là giao thức ủy quyền; OIDC bổ sung danh tính đăng nhập.** Khi scope chứa **openid**, IdP phải hỗ trợ OIDC và cấu hình issuer/UserInfo/JWKS đúng. Đừng tự coi một OAuth2 access token không có OIDC là bằng chứng danh tính theo chuẩn OIDC.

### 2.2. Sơ đồ Authorization Code + delegated API call

~~~text
Browser (Alice)              Spring MVC BFF          IdP / AS             Partner API
      |                            |                     |                      |
      | GET /api/partner/profile   |                     |                      |
      |--------------------------->|                     |                      |
      | 302 tới trang đăng nhập    |                     |                      |
      |<---------------------------|                     |                      |
      | GET /oauth2/authorization/partner                 |                      |
      |--------------------------->|                     |                      |
      | 302 /authorize?... state, nonce, redirect_uri     |                      |
      |<---------------------------|                     |                      |
      |----------------------------------------------->   |                      |
      |       đăng nhập / đồng ý scopes                   |                      |
      |<-----------------------------------------------   |                      |
      | GET /login/oauth2/code/partner?code=...&state=...  |                      |
      |--------------------------->|                     |                      |
      |                            | POST token endpoint |                      |
      |                            |-------------------->|                      |
      |                            | access/ID/refresh   |                      |
      |                            |<--------------------|                      |
      |                            | xác minh login và tạo session              |
      | 302 / hoặc URL ban đầu     |                     |                      |
      |<---------------------------|                     |                      |
      | GET /api/partner/profile   |                     |                      |
      |--------------------------->| resolve OAuth2AuthorizedClient             |
      |                            | GET /v1/profile                            |
      |                            | Authorization: Bearer <access-token>       |
      |                            |------------------------------------------->|
      |                            |          JSON hồ sơ, nếu token hợp lệ       |
      |                            |<-------------------------------------------|
      | 200 JSON hồ sơ đã chọn     |                     |                      |
      |<---------------------------|                     |                      |
~~~

Trong flow thực, Spring Security có thể dùng trang login mặc định trước khi người dùng bấm link **/oauth2/authorization/partner**. Một 302 không đảm bảo luôn trỏ thẳng tới IdP; hãy quan sát response và chính sách exception entry point. **state** chống CSRF trong authorization response; **nonce** được dùng khi triển khai OIDC để liên kết ID Token với login request; **PKCE** bổ sung bảo vệ Authorization Code theo chính sách và loại client. Không bỏ các kiểm tra mặc định chỉ vì callback hoạt động.

## 3. Kiến trúc và yêu cầu trước khi viết code

Cần ba hệ thống hoặc thành phần:

1. **BFF / OAuth2 Client**: Spring Boot 3.x chạy trên **https://app.example.test** ở staging/production; khi local có thể dùng **http://localhost:8080** theo quy định cho phát triển.
2. **IdP / Authorization Server**: có discovery OIDC (**issuer-uri**) và các endpoint authorization, token, JWKS, UserInfo nếu cần. Tạo một **confidential web client** có **client-id**, **client-secret** hoặc hình thức xác thực client được IdP hỗ trợ, **Authorization Code flow**, redirect URI đã đăng ký chính xác.
3. **Partner API**: resource server biết kiểm tra access token của IdP, yêu cầu **scope api.profile.read**, audience dành cho API và trả JSON hồ sơ đã được phân quyền đúng người dùng.

**Đường callback mặc định của Spring Security OAuth2 Login** với registrationId **partner** là:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Ví dụ:

~~~text
Local:       http://localhost:8080/login/oauth2/code/partner
Production:  https://app.example.test/login/oauth2/code/partner
~~~

Các URI này phải được khai báo tại IdP đúng scheme, hostname, port và path. Nếu backend đứng sau reverse proxy terminate HTTPS, hãy cấu hình trusted forwarded headers đúng ở ingress/app, không nhận **X-Forwarded-Host / X-Forwarded-Proto** do client Internet giả mạo. **Redirect URI mismatch** thường xuất hiện do BFF nghĩ request có baseUrl là http nội bộ thay vì https public.

**Scopes:** ví dụ yêu cầu **openid**, **profile** cho đăng nhập OIDC và **api.profile.read** để gọi Partner API. Tên scope cuối là hợp đồng giả định; phải đổi đúng theo Partner API thật. **Scope có trong access token không tự thay thế việc kiểm tra audience**. Partner API phải tự kiểm tra token được cấp cho chính nó.

## 4. Tạo dự án Spring Boot 3.x / Java 17

Một dự án Gradle có wrapper và cấu trúc:

~~~text
oauth-login-bff/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
└── src/
    ├── main/
    │   ├── java/com/example/oauthbff/
    │   │   ├── OAuthBffApplication.java
    │   │   ├── PartnerProfile.java
    │   │   ├── PartnerApiClient.java
    │   │   └── PartnerController.java
    │   └── resources/application.yml
    └── test/java/com/example/oauthbff/
        └── PartnerApiClientTest.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'oauth-login-bff'
~~~

**build.gradle** (pin phiên bản để minh họa, không phải lời khuyên dùng bản vá này vĩnh viễn):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dự án dựa trên Spring Framework 6.1+/Boot 3.2+ để có **RestClient**; cấu hình Boot 3.5 minh họa đáp ứng điều kiện đó. Với phiên bản khác, kiểm tra BOM và API, không pha trộn Spring Security 5.x vào Boot 3.x.

### 4.1. application.yml: registration và IdP provider

Tệp **src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner-idp
            client-id: "${PARTNER_CLIENT_ID}"
            client-secret: "${PARTNER_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - api.profile.read
        provider:
          partner-idp:
            issuer-uri: "https://idp.example.test/realms/demo"

partner:
  api:
    base-url: "https://api.example.test"
~~~

Giải thích:

- **registration.partner** là một **client registration** duy nhất. Trùng tên **partner** trong **@RegisteredOAuth2AuthorizedClient("partner")** và link **/oauth2/authorization/partner** là có chủ ý.
- **provider.partner-idp.issuer-uri** cho phép Spring thực hiện OIDC discovery. **Issuer URL ví dụ phải được thay bằng URL thật** có metadata hợp lệ, HTTPS và JWKS endpoint phù hợp. Discovery có thể diễn ra khi ứng dụng khởi động: nếu IdP giả/không truy cập được, ứng dụng có thể **không startup**, chứ không chỉ lỗi khi người dùng đăng nhập.
- **client-id / client-secret** được lấy từ biến môi trường; không commit giá trị thật. IdP có thể yêu cầu phương thức xác thực client khác; ví dụ **client_secret_basic** chỉ phù hợp confidential web client đã đăng ký.
- **scope api.profile.read** là quyền đề nghị cấp. AS có thể cấp ít hơn; backend phải kiểm tra token thực sự có scope cần thiết trước khi dùng, và Partner API vẫn phải thực thi policy của nó.
- **redirect-uri** sử dụng các template variables được Spring Security OAuth2 client hỗ trợ. Bảo đảm đường callback public khớp registration tại IdP và trusted proxy configuration.
- **partner.api.base-url** phải là một endpoint được cấu hình và kiểm soát ở phía server. **Không** nhận URL API từ query parameter của user rồi chuyển access token đến đó, vì sẽ tạo SSRF/token exfiltration.

### 4.2. Application và SecurityFilterChain

Tệp **src/main/java/com/example/oauthbff/OAuthBffApplication.java**:

~~~java
package com.example.oauthbff;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class OAuthBffApplication {
    public static void main(String[] args) {
        SpringApplication.run(OAuthBffApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                // Xác thực người dùng qua OAuth2/OIDC Login.
                .oauth2Login(Customizer.withDefaults())
                // Cho phép ứng dụng quản lý OAuth2 Authorized Client.
                .oauth2Client(Customizer.withDefaults())
                // CSRF của Spring Security vẫn bật theo mặc định.
                .build();
    }
}
~~~

**Không dùng SessionCreationPolicy.STATELESS cho BFF có oauth2Login** nếu bạn chưa thiết kế cơ chế lưu OAuth2 Authorization Request, state, SecurityContext và authorized clients thay thế. Đường browser login và callback thường cần trạng thái phiên. Không copy cấu hình Resource Server dùng Bearer JWT stateless sang web BFF này.

**Không tắt CSRF để “sửa callback login”.** Authorization Code callback phổ biến dùng GET với code/state, trong khi BFF sử dụng cookie/session để xác thực browser. Với POST/PUT/DELETE làm thay đổi trạng thái, tiếp tục áp dụng CSRF protection. Nếu app triển khai nhiều SecurityFilterChain, bảo đảm login/callback/endpoint cần thiết đi qua chain đúng.

### 4.3. DTO nhận dữ liệu API, không nhận token từ browser

Tệp **src/main/java/com/example/oauthbff/PartnerProfile.java**:

~~~java
package com.example.oauthbff;

// JSON Partner API được giả định:
// {"id":"42","displayName":"Alice"}
public record PartnerProfile(String id, String displayName) {
}
~~~

**PartnerProfile** chỉ chứa dữ liệu ứng dụng đã cho phép hiển thị. Trong hệ thống thật, tránh trả nguyên response JSON của Partner API nếu nó có trường nhạy cảm hoặc quyền object-level khác nhau; map sang DTO do BFF kiểm soát.

### 4.4. Backend gọi Partner API bằng access token đã được ủy quyền

Tệp **src/main/java/com/example/oauthbff/PartnerApiClient.java**:

~~~java
package com.example.oauthbff;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PartnerApiClient {

    private final RestClient restClient;

    public PartnerApiClient(
            RestClient.Builder builder,
            @Value("${partner.api.base-url}") String baseUrl) {
        this.restClient = builder.baseUrl(baseUrl).build();
    }

    public PartnerProfile fetchProfile(OAuth2AccessToken accessToken) {
        // BFF không gọi API khi token không có scope yêu cầu.
        if (!accessToken.getScopes().contains("api.profile.read")) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Delegated scope missing");
        }

        try {
            PartnerProfile profile = restClient.get()
                    .uri("/v1/profile")
                    .headers(h -> h.setBearerAuth(
                            accessToken.getTokenValue()))
                    .retrieve()
                    .body(PartnerProfile.class);

            if (profile == null) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "Partner API returned no profile");
            }
            return profile;
        } catch (RestClientResponseException exception) {
            // Không trả raw token, URL có secret hoặc body lỗi từ Partner API.
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, "Partner API request failed");
        }
    }
}
~~~

Các điểm chính:

1. **RestClient.Builder** được Spring Boot 3.2+ tự cấu hình khi có spring-web; ta dùng dependency injection, không tạo một client được cấu hình bằng URL người dùng truyền vào.
2. **setBearerAuth(...)** đặt token vào header **Authorization** cho request **đến Partner API cố định**. Không gửi token vào query string, browser response hoặc logs.
3. Scope được kiểm tra **ở BFF trước outbound call** để phản hồi rõ cho người dùng, nhưng đây **không phải** cơ chế bảo vệ duy nhất. Partner API phải xác minh token cryptographically hoặc qua introspection và kiểm tra **issuer, audience, expiry và permissions**.
4. **RestClientResponseException** biểu diễn HTTP error do Partner API trả về. Ví dụ chuyển thành **502 Bad Gateway** chung và không lộ upstream response. Hệ thống thật cần ánh xạ các lỗi có chủ đích, telemetry an toàn và chính sách reauthorization khi access token bị thu hồi/401.
5. Nếu response 200 nhưng body trống, ứng dụng trả 502 thay vì gửi null rồi coi là thành công. Không dùng dữ liệu chưa kiểm tra để quyết định quyền/ownership.
6. Khi triển khai thật, cấu hình **timeout, connection pool, retry chỉ cho operations phù hợp, circuit breaker và observability**. Không tự động retry POST nhạy cảm vì có thể nhân đôi side effect; không retry vô hạn khi Partner API trả 401.

**Lưu ý:** access token được truyền vào phương thức như kiểu **OAuth2AccessToken**, không phải ID Token. Không tạo token từ chuỗi username hoặc Authentication.getName(); chỉ AS mới phát token có giá trị với resource server.

### 4.5. Controller lấy OAuth2AuthorizedClient cho đúng principal

Tệp **src/main/java/com/example/oauthbff/PartnerController.java**:

~~~java
package com.example.oauthbff;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PartnerController {

    private final PartnerApiClient partnerApiClient;

    public PartnerController(PartnerApiClient partnerApiClient) {
        this.partnerApiClient = partnerApiClient;
    }

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
                "message", "Open /oauth2/authorization/partner to sign in");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication current) {
        return Map.of("user", current.getName());
    }

    @GetMapping("/api/partner/profile")
    public PartnerProfile partnerProfile(
            @RegisteredOAuth2AuthorizedClient("partner")
            OAuth2AuthorizedClient authorizedClient) {

        // Resolved cho registration partner và principal của request.
        // Token có thể được refresh theo authorized-client manager policy.
        return partnerApiClient.fetchProfile(
                authorizedClient.getAccessToken());
    }
}
~~~

**@RegisteredOAuth2AuthorizedClient("partner")** dùng cơ chế argument resolution của Spring Security OAuth2 Client để lấy một authorized client đã gắn với principal/registration. Nó giúp tránh tự tìm raw access token trong session attribute hoặc gửi token từ browser. Cơ chế authorized-client manager có thể xử lý **refresh token** khi được cấu hình, có refresh token hợp lệ và theo policy; **đừng giả định mọi AS đều cấp refresh token** hoặc mọi error 401 sẽ tự refresh thành công.

**Nếu authorized client chưa được cấp/không còn hợp lệ:** tùy cấu hình resolver/manager, request có thể dẫn tới luồng authorization mới, lỗi xác thực, hoặc cần xử lý nghiệp vụ riêng. Không nhận clientId do browser tự chọn tùy ý rồi dùng token từ registration khác. Giữ registration id cố định cho từng Partner API đã được phê duyệt.

**Tách biệt Identity vs Authorization:** Người dùng Alice đăng nhập được không đồng nghĩa được quyền gọi **/v1/profile** hay nhận bản ghi của người khác. Nếu BFF cung cấp endpoint cho phép chỉ định profileId, phải áp object-level checks và bảo đảm Partner API cũng enforce subject/tenant. Ví dụ chỉ có endpoint **current profile**, không nhận userId tùy ý để giảm nguy cơ IDOR.

## 5. Chạy flow thật từng bước

### 5.1. Đăng ký client ở IdP

Trong hệ quản trị IdP, tạo một **confidential OIDC client**:

- **Client ID/secret** cho web BFF; bật Authorization Code flow và client authentication tương ứng.
- Redirect URI: **http://localhost:8080/login/oauth2/code/partner** cho local development (hoặc HTTPS public URI tương ứng ở staging/prod).
- Được phép scopes **openid profile api.profile.read**, và AS phải phát **access token dùng được với Partner API**.
- Nếu Partner API đòi một **audience/resource indicator**, cấu hình phía AS/client theo giao thức của provider; scope đúng nhưng audience sai vẫn bị Partner API từ chối.
- Đặt redirect URI allowlist chính xác, không dùng wildcard rộng hoặc open redirect. Dùng **PKCE** khi AS/client policy yêu cầu và để tăng bảo vệ authorization code.
- Nếu refresh token được phép, xem điều kiện IdP phát nó; một số IdP yêu cầu **offline_access** hoặc chính sách consent riêng. Không đòi refresh token nếu ứng dụng không cần giữ quyền lâu dài.

Thiết lập hai biến môi trường **PARTNER_CLIENT_ID** và **PARTNER_CLIENT_SECRET** trong runtime an toàn trước khi start. Không đưa secret vào source, test snapshot hoặc lệnh command-line có thể bị lộ.

### 5.2. Chạy app

~~~bash
./gradlew bootRun
~~~

Trong PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi **issuer-uri** còn là idp.example.test, startup/discovery sẽ không kết nối được IdP thật; phải thay issuer và API base URL trước khi test end-to-end. Nếu issuer được cấu hình thật nhưng không hỗ trợ OIDC discovery, cần cung cấp các provider endpoints đúng theo tài liệu của nhà cung cấp.

### 5.3. Thực hiện trên trình duyệt

1. Mở **http://localhost:8080/**, nhận JSON chào mừng.
2. Đi tới **http://localhost:8080/oauth2/authorization/partner** để bắt đầu authorization code login.
3. Trình duyệt được chuyển tới IdP; đăng nhập tài khoản thử nghiệm Alice và đồng ý scopes phù hợp.
4. IdP redirect về **/login/oauth2/code/partner?code=...&state=...**. Spring Security kiểm tra state, đổi code tại token endpoint và tạo phiên đăng nhập.
5. Truy cập **http://localhost:8080/api/me** để xác minh principal đăng nhập (tên trả về do IdP/Spring cung cấp, không nhất thiết là chuỗi "alice").
6. Truy cập **http://localhost:8080/api/partner/profile**. BFF lấy authorized client và gọi Partner API với access token dành cho Alice.
7. Quan sát JSON response hồ sơ đã được mapping. Không thấy token/refresh token trong URL, HTML, localStorage hoặc JSON response của BFF.

**Đừng dùng curl -L để vô tình in authorization code, Set-Cookie hoặc secret vào CI log.** Authorization Code flow cần browser/session/state, các lệnh curl thủ công có thể được dùng để xem redirect/header với dữ liệu giả trong môi trường cô lập nhưng không phải phương án hoàn chỉnh để kiểm chứng login.

## 6. Kiểm thử API client mà không cần IdP thật

Một lỗi phổ biến trong bài tích hợp là chỉ kiểm thử **@WithMockUser** rồi tuyên bố access token đã được gửi tới Partner API. Test này không đủ: @WithMockUser chỉ đặt Authentication giả, **không tự sinh OAuth2AuthorizedClient hoặc làm HTTP outbound request**.

Ta có thể kiểm thử phần outbound một cách quyết định bằng **@RestClientTest**, **MockRestServiceServer** và **OAuth2AccessToken giả**. Chúng kiểm tra đúng header Authorization và scope guard; chúng **không** mô phỏng toàn bộ OAuth2 Login callback.

Tệp **src/test/java/com/example/oauthbff/PartnerApiClientTest.java**:

~~~java
package com.example.oauthbff;

import java.time.Instant;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.server.ResponseStatusException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match
        .MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match
        .MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match
        .MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response
        .MockRestResponseCreators.withSuccess;

@RestClientTest(PartnerApiClient.class)
@TestPropertySource(properties =
        "partner.api.base-url=https://api.example.test")
class PartnerApiClientTest {

    @Autowired
    PartnerApiClient partnerApiClient;

    @Autowired
    MockRestServiceServer server;

    private static OAuth2AccessToken accessToken(Set<String> scopes) {
        Instant now = Instant.now();
        return new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-access-token-alice",
                now.minusSeconds(30),
                now.plusSeconds(300),
                scopes);
    }

    @Test
    void forwardsOnlyAccessTokenAsBearerHeader() {
        server.expect(requestTo(
                        "https://api.example.test/v1/profile"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer test-access-token-alice"))
                .andRespond(withSuccess(
                        "{\"id\":\"42\",\"displayName\":\"Alice\"}",
                        MediaType.APPLICATION_JSON));

        PartnerProfile result = partnerApiClient.fetchProfile(
                accessToken(Set.of("api.profile.read")));

        assertThat(result.id()).isEqualTo("42");
        assertThat(result.displayName()).isEqualTo("Alice");
        server.verify();
    }

    @Test
    void missingDelegatedScopeDoesNotCallPartnerApi() {
        assertThatThrownBy(() -> partnerApiClient.fetchProfile(
                accessToken(Set.of("openid", "profile"))))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("403");

        // Không đăng ký request expectation: nếu service cố gửi
        // outbound HTTP, mock server sẽ phát hiện request ngoài dự kiến.
        server.verify();
    }
}
~~~

Chạy chỉ bộ test outbound trong một project đã có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.oauthbff.PartnerApiClientTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.oauthbff.PartnerApiClientTest
~~~

**Dự kiến hai test đạt** khi mã được lắp đúng vào project Boot 3.5 như mẫu. Test đầu xác minh request đến **đúng hostname/path cố định**, method **GET**, header **Authorization: Bearer test-access-token-alice**, và JSON mapping. Test sau xác minh thiếu scope bị chặn trước outbound request. Đây là **kỳ vọng từ mã**, chưa phải kết quả đã biên dịch/chạy trong môi trường thực.

### 6.1. Ma trận kiểm thử tích hợp cần bổ sung

| Tình huống | Cấp kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Chưa có session → GET /api/partner/profile | MockMvc/web integration | Không vào controller; chuyển sang login/IdP theo entry point |
| Alice login qua OIDC | Test IdP integration | State và callback được xác minh; session gắn đúng Alice |
| Client có access token hợp lệ, scope đúng | Client unit/mock HTTP | Gửi Bearer token đúng Partner API; nhận profile |
| Token thiếu api.profile.read | Client unit | Không gửi outbound request; 403 ở BFF theo demo |
| Bob đăng nhập sau Alice | Full session integration | BFF chỉ lấy authorized client gắn với Bob, không dùng token của Alice |
| Access token hết hạn, có refresh token | OAuth2 client integration | Authorized-client manager xử lý refresh nếu được cấu hình và AS chấp nhận |
| Access token hết hạn, không refresh được | OAuth2 client integration | Yêu cầu reauthorization hoặc lỗi an toàn, không loop vô hạn |
| Partner API trả 401/token revoked | End-to-end | BFF không tự nâng quyền; có chiến lược retry/relogin rõ ràng |
| Partner API trả 403/insufficient_scope | End-to-end | Không tiếp tục bằng service/admin token để vượt qua quyền |
| Partner API trả 5xx/timeout | Client/integration | Trả lỗi kiểm soát, không lộ raw token hoặc nội dung nhạy cảm |
| API nhận token audience sai | Resource server integration | 401/403 theo policy resource server; không tin scope đơn thuần |
| Logout BFF | Web integration | Session browser hết hiệu lực, authorized-client storage được xử lý theo policy |
| Nhiều replica BFF | Distributed integration | Session/auth request/authorized-client store tương thích và không cross-user |
| XSS/CSRF vào endpoint state-changing | Security integration | CSRF và cookie policy vẫn bảo vệ BFF |
| Proxy đặt X-Forwarded-Host giả | Edge integration | Callback không bị chuyển sang hostname do client kiểm soát |

**MockMvc hỗ trợ** request post-processors như **oauth2Login()** và **oauth2Client()** trong spring-security-test để dựng authentication và authorized client ở test context. Tuy vậy, những post-processor này không xác minh chữ ký ID Token hoặc chạy authorization code flow thật. Phải có test với IdP thử nghiệm cho state/nonce, callback, issuer, audience và persistence.

### 6.2. Không nhầm OAuth2 Login test với test delegated token

Một kiểm thử kiểu **.with(oauth2Login())** có thể chứng minh endpoint đọc principal đã đăng nhập hoạt động, nhưng **không bảo đảm @RegisteredOAuth2AuthorizedClient có token thật** hoặc request tới Partner API mang Bearer đúng. Cần kiểm tra riêng:

- Bean/scope của authorized-client repository/manager.
- Token của registration **partner** thuộc principal hiện tại.
- Request outbound gửi **access token** thay vì ID Token.
- Lỗi token hết hạn, refresh thất bại và reauthorization.
- Test multi-user: không chia sẻ authorized client sai giữa các principals.

## 7. Refresh token, lưu trữ authorized client và phiên

### 7.1. Access token hết hạn thì sao?

**OAuth2AuthorizedClient** gồm ClientRegistration, principalName, access token và refresh token (nếu có). Spring Security có các thành phần như **OAuth2AuthorizedClientManager**, **OAuth2AuthorizedClientService** và **OAuth2AuthorizedClientRepository** để quản lý client đã được cấp quyền.

Một **authorized-client manager** phù hợp có thể dùng **refresh_token grant** khi access token gần/đã hết hạn và AS đã cấp refresh token hợp lệ. Nhưng không được suy ra mọi ứng dụng có behavior tự động refresh giống nhau khi:

- Bạn chỉ đọc raw token từ HttpSession rồi tự gửi nó.
- Bạn cấu hình custom authorized-client manager/provider thiếu refreshToken support.
- AS không cấp refresh token hoặc refresh token đã bị thu hồi.
- User session hết hạn hoặc authorized-client repository không còn thông tin.
- Resource server trả 401 do revocation/audience sai chứ không chỉ access token exp.

**Không retry vô hạn bằng cùng token**. Với 401 từ Partner API, hãy phân loại: exp, token revoked, wrong audience, missing entitlement hoặc AS outage. Nếu cần refresh/retry, chỉ làm một cách kiểm soát, không log giá trị token và không che 403 thiếu quyền bằng client_credentials của service.

### 7.2. Session và token storage

Trong demo servlet BFF:

- Browser có session cookie; Spring Security lưu authentication context liên quan request.
- Authorized client được lưu/đọc qua repository/service theo cấu hình. Một triển khai đơn giản có thể dùng **InMemoryOAuth2AuthorizedClientService**; production nhiều replica cần lưu trữ bền vững/chia sẻ đúng cách.
- **Không lưu access token/refresh token vào JavaScript localStorage chỉ để gọi Partner API** nếu kiến trúc chọn BFF. Backend nắm token và chỉ trả dữ liệu được phép.
- Bảo vệ authorized-client store vì refresh token cho phép lấy token mới; áp encryption at rest, giới hạn quyền đọc, rotation/retention và audit.
- Khi user logout, phải định nghĩa việc xóa session, xóa authorized client trong local store và có cần **revocation tại AS** hay không. **Logout ở BFF không mặc nhiên thu hồi access token đã phát**.
- Với nhiều instance, kiểm tra shared session store, OAuth2 Authorization Request/state/nonce persistence và cơ chế authorized-client storage. Sticky session một mình không thay thế thiết kế fault tolerance.
- Nếu cần quyền được thu hồi tức thì, resource server/AS phải có chiến lược TTL, introspection hoặc denylist; không chỉ dựa vào thời điểm browser logout.

### 7.3. Token chỉ được sử dụng với đích tin cậy

RestClient trong ví dụ lấy baseUrl từ cấu hình server. Trong production:

- Dùng HTTPS và xác minh TLS certificate; không tắt hostname verification.
- Cấu hình outbound allowlist hostname, kiểm soát DNS/egress, redirect policy và timeout để giảm SSRF/token leakage.
- Không chấp nhận một tham số URL từ browser để tạo điểm đến cho **Authorization: Bearer**.
- Đặc biệt cẩn trọng HTTP 3xx: một HTTP client có thể có chính sách follow redirect khác nhau; **không để Authorization header bị chuyển tiếp tới hostname không tin cậy**.
- Không đưa Bearer token vào query string, exception message, metrics label, access logs hoặc URL của distributed tracing.
- Tránh biến BFF thành proxy tổng quát có thể gọi mọi method/path bằng quyền của người dùng mà không kiểm tra CSRF, method, scope và object-level authorization.

## 8. Cookie, CSRF, SameSite, browser và reverse proxy

**OAuth2 Login cho web browser thường sử dụng session cookie**, vì thế phải thiết kế song song với các biện pháp browser security:

- **HttpOnly:** JavaScript không đọc session cookie.
- **Secure:** chỉ gửi cookie qua HTTPS trong production.
- **SameSite:** lựa chọn tương thích với login redirect/callback và kiến trúc frontend, không áp một giá trị cứng mà không kiểm thử; cân nhắc OIDC form_post nếu sử dụng.
- **CSRF:** giữ bảo vệ cho POST/PUT/PATCH/DELETE làm thay đổi trạng thái; OAuth2 state không thay thế CSRF token cho mọi endpoint của BFF.
- **Session fixation:** để Spring Security thay session identifier khi đăng nhập theo chính sách; không disable chỉ để callback đỡ lỗi.
- **Redirect validation:** chỉ IdP redirect URI đã đăng ký; không dùng returnUrl bên ngoài tùy ý tạo open redirect.
- **Forwarded headers:** khi ingress terminate TLS, chỉ chấp nhận headers đã được proxy tin cậy chuẩn hóa; tránh nhận scheme/host trực tiếp từ attacker.
- **CORS:** nếu frontend SPA ở origin khác gọi BFF bằng cookie, cấu hình CORS credentials cụ thể, CSRF và cookie policy riêng. CORS **không** tự chứng minh authorization.
- **Content Security Policy:** hạn chế XSS để giảm nguy cơ trình duyệt dùng session đã đăng nhập thực hiện request ngoài ý muốn.

**Browser session không nên có endpoint nào trả token chỉ vì user đã đăng nhập.** Kể cả khi token không nằm trong localStorage, XSS có thể điều khiển một session đang đăng nhập để gọi BFF; phải bảo vệ UI, chống CSRF và giới hạn scope/những thao tác BFF cho phép.

## 9. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Browser bị redirect vô hạn tới IdP | Session/state không lưu được, cookie không được gửi, callback path sai | Kiểm tra cookie, public URL, trusted headers, session store |
| **redirect_uri mismatch** | baseUrl nội bộ khác HTTPS public, port/path prefix sai, URI chưa đăng ký | So URI gửi tới IdP với allowlist redirect URI thực tế |
| Startup fail khi đặt issuer-uri | OIDC discovery URL sai/không reachable/TLS lỗi | Thay issuer thật, xác nhận metadata/JWKS qua môi trường tin cậy |
| Login thành công nhưng API 401 | Access token hết hạn, audience sai, issuer sai, revoked | Kiểm tra token contract, resource server validation và authorized-client refresh |
| API 403 dù login thành công | Token không có scope hoặc user không có quyền resource | Kiểm tra consent/scopes/entitlements; không dùng ID token thay access token |
| BFF trả 403 ngay trước outbound | Access token không chứa api.profile.read theo policy demo | Kiểm tra scope thực tế của token và registration/consent |
| BFF trả 502 | Partner API 4xx/5xx hoặc response rỗng do mapping demo | Kiểm tra upstream status an toàn, circuit breaker và hợp đồng JSON |
| Bob nhìn thấy hồ sơ Alice | Token/repository cache theo clientId thay vì principal, hoặc IDOR | Ràng buộc authorized client theo principal, test multi-user và object ownership |
| Callback trả 404 | Sai filter chain path, context path hoặc proxy rewrite | Kiểm tra /login/oauth2/code/partner và Spring Security filter mapping |
| Sau logout vẫn dùng được access token đã lộ | JWT có exp còn hạn và AS/resource server không thu hồi | TTL ngắn, revocation/introspection theo nhu cầu |
| BFF chạy một node nhưng fail multi-node | Session/state/authorized-client store cục bộ | Dùng shared persistence và kiểm tra consistency |
| UserInfo/login hoạt động, Partner API từ chối token | Token dành cho client/UserInfo khác, thiếu API audience/scope | Cấu hình audience/resource và permission riêng cho Partner API |
| 401 từ API dẫn tới retry liên tục | Client không phân loại expired/revoked/missing scope | Giới hạn retry, dùng refresh/reauth đúng policy |
| Login trên HTTP nội bộ sau proxy bị sai cookie/redirect | TLS termination/forwarded header xử lý sai | Cấu hình trusted proxy scheme/host và Secure cookies |

**Log an toàn khi chẩn đoán:** ghi request ID, registrationId, tên endpoint, upstream HTTP status và loại lỗi; **không ghi access token, refresh token, authorization code, client secret, session cookie, OIDC state/nonce**. Khi bật DEBUG/TRACE Spring Security, dùng môi trường kiểm soát và tránh log request headers chứa secrets.

## 10. Checklist nghiệm thu bài thực hành

### OAuth2 Login

- IdP có OIDC discovery và client registration tương thích, redirect URI đúng **{baseUrl}/login/oauth2/code/{registrationId}**.
- Authorization Code flow chạy qua state validation; nonce/ID Token validation đúng với OIDC; cấu hình PKCE theo AS/client policy.
- Session cookie, CSRF, session fixation, SameSite và forwarded headers được kiểm tra ở local và public HTTPS environment.
- **oauth2Login()** xác thực người dùng; không nhầm login authentication với quyền resource API.

### OAuth2 Authorized Client

- Access token được liên kết với đúng **registrationId** và **principalName**.
- Client secret, refresh token, authorized-client storage không được đưa vào browser.
- Refresh behavior được kiểm thử với token hết hạn; khi không thể refresh, hệ thống từ chối an toàn hoặc reauthorize.
- Logout/session expiry và token revocation được thiết kế rõ, không xem logout là tự hủy mọi JWT.

### Partner API

- BFF chỉ gọi **base URL cố định, HTTPS, allowlisted** và gửi access token trong header Bearer.
- Token có **scope api.profile.read**, issuer/audience mà Partner API yêu cầu; Partner API tự enforce user/tenant/resource ownership.
- Nếu Partner API lỗi, BFF không phản chiếu raw token hoặc upstream error body nhạy cảm.
- Không tự chuyển sang service/admin credentials khi access token người dùng bị deny.
- Có timeout, safe retry/backoff và outbound rate limits phù hợp.

### Kiểm thử

- Test unit phần gọi API khẳng định **đúng Bearer header**, endpoint và scope guard bằng **MockRestServiceServer**.
- Test callback/login và session bằng Spring Test/OIDC test IdP, **không** lấy @WithMockUser làm bằng chứng token thực.
- Test hai người dùng có authorized client khác nhau và quyền resource khác nhau.
- Test access token expired/refresh/revoke, Partner 401/403/5xx, outage/timeout và session/logout.
- Test production proxy HTTPS/public redirect URI, path prefix, CSRF, cookie và CORS nếu frontend ở origin khác.
- Kiểm chứng access/refresh/ID tokens không xuất hiện trong HTML, JSON, URL, log hay metrics.

**Kết luận:** **OAuth2 Login** xác thực người dùng để tạo phiên web; **OAuth2 Client** giữ quyền truy cập đã được AS cấp cho **đúng principal**; **Partner API** quyết định access token có hợp lệ và được phép truy cập tài nguyên hay không. Một BFF an toàn gọi API ngoài bằng **access token có scope và audience phù hợp**, giữ bí mật ở backend, xử lý expiry/refresh/revocation và kiểm thử đầy đủ login, outbound Bearer header, session isolation cùng các lỗi âm.
