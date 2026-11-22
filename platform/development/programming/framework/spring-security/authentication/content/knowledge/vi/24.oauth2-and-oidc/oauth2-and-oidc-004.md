# ClientRegistration, redirect URI và thông tin định danh ứng dụng trong Spring Security

> **Ngữ cảnh:** Một ứng dụng Java 17+ sử dụng Spring Boot 3.x và Spring Security 6.x muốn đăng nhập người dùng qua một nhà cung cấp OAuth 2.0 / OpenID Connect (OIDC), chẳng hạn hệ thống định danh nội bộ. Bài tập trung vào **thông tin nhận dạng ứng dụng khách** (`client_id`, `client_secret`, `registrationId`), cấu hình `ClientRegistration`, **redirect URI** và lỗi tích hợp liên quan. OAuth 2.0 chỉ định quy trình cấp quyền; khi cần xác thực danh tính người dùng bằng giao thức chuẩn, ưu tiên **OIDC** trên OAuth 2.0.

## 1. Sau bài này bạn có thể làm gì?

- Nhận biết **ứng dụng khách (client)**, **nhà cung cấp/authorization server**, **người dùng (resource owner)** và **ứng dụng nhận callback** trong authorization code flow.
- Nói rõ sự khác nhau giữa `registrationId` của Spring, `client_id` do IdP cấp, `client_secret`, `issuer`, `clientName` và danh tính người dùng (`iss` + `sub`).
- Biết những trường nào thuộc `ClientRegistration`, các trường Boot ánh xạ từ `application.yml` và nơi chúng được lưu qua `ClientRegistrationRepository`.
- Ghép chính xác **URI bắt đầu đăng nhập**, **redirect URI nhận authorization code** và **URI trang đích sau đăng nhập**; biết vì sao ba URI này không đồng nghĩa.
- Cấu hình một OAuth 2.0 / OIDC client thật với secret ngoài mã nguồn; kiểm tra lỗi callback, cấu hình proxy HTTPS, scopes và phương thức xác thực client.
- Thiết lập nguyên tắc bảo mật cho redirect URI, `state`, PKCE, OIDC `nonce`, issuer/audience và luân chuyển secret; xây dựng checklist trước khi vận hành.

## 2. Bản đồ vai trò: ai xác định danh tính của ai?

Trong một ứng dụng Spring MVC, các vai trò được tách rõ:

| Vai trò / dữ liệu | Ai sở hữu? | Dùng để làm gì? |
| --- | --- | --- |
| **Client application** | Ứng dụng Spring Boot | Khởi tạo yêu cầu đăng nhập, nhận callback và đổi authorization code tại token endpoint |
| **Authorization Server / OpenID Provider (OP)** | Nhà cung cấp định danh (IdP) | Xác thực user, xử lý consent/chính sách, phát authorization code và token |
| **`client_id`** | IdP cấp cho **ứng dụng khách** | Nhận diện ứng dụng tại authorization/token endpoint; thường xuất hiện trong URL authorization, **không phải mật khẩu** |
| **`client_secret`** hoặc khóa private của client | Ứng dụng bảo mật phía máy chủ quản lý | Xác thực **client confidential** ở token endpoint theo phương thức đã đăng ký |
| **`registrationId`** | Spring Security trong ứng dụng | Tên khóa **nội bộ** để chọn một `ClientRegistration`, ví dụ `company`; không nhất thiết bằng `client_id` |
| **`issuer`** | Nhà cung cấp định danh | Danh tính và gốc metadata tin cậy của IdP; trong OIDC, phải khớp issuer được xác nhận trong ID Token |
| **`sub`** của ID Token | IdP gán cho tài khoản người dùng | Định danh subject; thường ghép với `iss` để xác định duy nhất tài khoản ở phía ứng dụng |
| **`redirect_uri`** | Client khai báo, IdP cho phép | Endpoint trong ứng dụng mà trình duyệt được chuyển **trở lại** mang `code` và `state` |
| **`scope`** | Client yêu cầu, IdP kiểm soát | Phạm vi dữ liệu/quyền yêu cầu; `openid` báo hiệu OIDC cho quy trình đăng nhập |

**Điểm rất dễ nhầm:** `client_id` chứng minh *client đang khai báo mình là ứng dụng nào* chứ không chứng minh *người dùng đang đăng nhập là ai*. Mã này thường là dữ liệu công khai. `client_secret` chỉ có ý nghĩa khi kênh chạy trên server có khả năng giữ bí mật; không được nhúng vào SPA, mã JavaScript trình duyệt, ứng dụng mobile hoặc bản phát hành desktop. Còn `registrationId` là tên cấu hình mà Spring dùng để định tuyến, không phải một credential OAuth.

### Luồng authorization code + OIDC (khái niệm)

~~~text
Browser                 Spring Security client                 IdP / OIDC Provider
   |  GET /private                |                                     |
   |----------------------------->|                                     |
   |  302 tới /oauth2/authorization/company                         |
   |<-----------------------------|                                     |
   |  GET /oauth2/authorization/company                             |
   |----------------------------->|                                     |
   |                              | tạo request + state (+PKCE/nonce) |
   |<------------- 302 đến authorization_uri ?client_id&redirect_uri&state...
   |--------------------------------------------------------------------->|
   |                              |                                     | login + consent
   |<----------- 302 đến https://app.example.test/login/oauth2/code/company?code=...&state=...
   |----------------------------->|                                     |
   |                              | xác minh state và request đã lưu  |
   |                              | POST code đến token endpoint      |
   |                              |------------------------------------>|
   |                              |<------------- token response -------|
   |                              | xác minh ID Token nếu dùng OIDC    |
   |<-------------- thiết lập authentication và redirect sau login    |
~~~

Ký hiệu trên đã lược bớt cookie, session, xử lý lỗi và chi tiết TLS. Authorization code đi qua **trình duyệt** tới callback; việc đổi code lấy token diễn ra giữa backend client và token endpoint qua kênh máy chủ. Không tự viết luồng đổi token nếu Spring Security đã cung cấp và đã được cấu hình đúng.

## 3. `ClientRegistration` gồm những gì?

`org.springframework.security.oauth2.client.registration.ClientRegistration` là mô hình mô tả một OAuth 2.0 hoặc OIDC client đã đăng ký. Các thuộc tính quan trọng:

| Thuộc tính Java | Thuộc tính Spring Boot | Ý nghĩa |
| --- | --- | --- |
| `registrationId` | `registration.<id>` (khóa bản đồ) | Định danh cục bộ, duy nhất trong repository |
| `clientId` | `registration.<id>.client-id` | Giá trị `client_id` do IdP cấp cho ứng dụng |
| `clientSecret` | `registration.<id>.client-secret` | Credential của confidential client, giữ ở backend |
| `clientAuthenticationMethod` | `registration.<id>.client-authentication-method` | Cách client xác thực tại token endpoint, chẳng hạn `client_secret_basic` |
| `authorizationGrantType` | `registration.<id>.authorization-grant-type` | Với login qua browser là `authorization_code` |
| `redirectUri` | `registration.<id>.redirect-uri` | Callback URI hoặc template, ví dụ `{baseUrl}/login/oauth2/code/{registrationId}` |
| `scopes` | `registration.<id>.scope` | Các scope yêu cầu, như `openid`, `profile`, `email` |
| `clientName` | `registration.<id>.client-name` | Nhãn hiển thị trên login page, không phải danh tính bảo mật |
| `providerDetails.authorizationUri` | `provider.<id>.authorization-uri` | Endpoint trình duyệt được điều hướng tới để login/consent |
| `providerDetails.tokenUri` | `provider.<id>.token-uri` | Endpoint backend gửi authorization code để đổi token |
| `providerDetails.issuerUri` | `provider.<id>.issuer-uri` | Issuer đã tin cậy, thường dùng OIDC discovery |
| `providerDetails.jwkSetUri` | `provider.<id>.jwk-set-uri` | Endpoint khóa công khai để xác minh chữ ký token |
| `providerDetails.userInfoEndpoint` | `provider.<id>.user-info-uri` và các trường liên quan | Đọc thông tin user nếu có theo cơ chế provider |

`ClientRegistrationRepository` cung cấp khả năng tìm cấu hình theo `registrationId`, ví dụ `findByRegistrationId("company")`. Một triển khai phổ biến là `InMemoryClientRegistrationRepository`. Spring Boot có thể tự dựng repository từ các property. Trong WebFlux, interface tương ứng là `ReactiveClientRegistrationRepository` (ví dụ `InMemoryReactiveClientRegistrationRepository`).

Phân biệt thêm hai lớp:

- `ClientRegistration` = **cấu hình đăng ký ứng dụng với IdP**.
- `OAuth2AuthorizedClient` = thông tin một client đã được cấp quyền, gắn với principal và token tương ứng, do `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` quản lý trong mô hình Servlet.

Đổi `client_id` hoặc đăng ký thêm provider làm thay đổi **cấu hình client**, không tự di chuyển hay làm mới các token đã cấp trước đó.

## 4. Cấu hình OIDC client bằng Spring Boot

Giả sử ứng dụng phục vụ tại `https://app.example.test`, sử dụng IdP có issuer `https://id.example.test/realms/staff`. Đội quản trị IdP đã tạo một **Web application confidential client** cho backend và cấp `client_id`/`client_secret` qua hệ thống quản lý secret.

Với một dự án Spring Boot dùng Gradle Groovy, thêm các dependency cốt lõi:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Khai báo `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: staff-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: "Company SSO"
        provider:
          staff-idp:
            issuer-uri: "https://id.example.test/realms/staff"
~~~

**Các giá trị trong ví dụ là tên miền và biến cấu hình minh họa.** Trước khi chạy, phải được IdP cung cấp `client_id`/`client_secret` thật trong một môi trường được phê duyệt, bảo đảm DNS/TLS truy cập được, và đăng ký callback public phù hợp. Không commit secret thật vào file YAML, test fixture hay log. Trong môi trường có secret manager/Kubernetes Secret/Vault, inject bí mật vào runtime theo chính sách quản trị.

Các dòng quan trọng:

1. `registration.company` làm `registrationId = "company"`; đường dẫn bắt đầu đăng nhập mặc định là `/oauth2/authorization/company`.
2. `provider: staff-idp` trỏ tới cấu hình provider; **`company` và `staff-idp` là hai tên cấu hình khác nhau**. Có thể có nhiều registration dùng chung một provider.
3. `client-id` là mã ứng dụng do IdP cấp; phải thuộc đúng client, tenant/realm và environment. Không thay bằng user id, group id, email hoặc `registrationId`.
4. `client-secret` dùng tại token endpoint theo `client_secret_basic` nếu IdP đã cấp và hỗ trợ. Nếu IdP yêu cầu `private_key_jwt` hoặc cơ chế khác, phải cấu hình tương thích; không đổi tùy ý.
5. `authorization-grant-type: authorization_code` dành cho luồng đăng nhập có tương tác browser; `client_credentials` là cấp token cho máy chủ/ứng dụng, không có người dùng đăng nhập hoặc callback browser.
6. `scope: openid` kích hoạt xử lý **OIDC** trong Spring Security khi provider hỗ trợ; `profile`/`email` chỉ đề nghị claims, không bảo đảm IdP phát chúng hay biến chúng thành authorities.
7. `provider.staff-idp.issuer-uri` cho phép framework khám phá OIDC/OAuth metadata nếu provider công bố discovery hợp lệ. Quá trình khởi tạo có thể cần truy cập metadata; issuer sai, TLS lỗi hoặc IdP không công bố metadata có thể khiến ứng dụng không khởi động được. Nếu provider không hỗ trợ discovery, phải cấu hình chính xác các endpoint cần thiết theo tài liệu của provider.

### Cấu hình Java Servlet để bật OAuth2 Login

Tệp `src/main/java/example/security/SecurityApplication.java` trong dự án Spring Boot có các dependencies trên:

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String publicPage() {
            return "Welcome";
        }

        @GetMapping("/private")
        String privatePage() {
            return "Signed in";
        }
    }
}
~~~

Ví dụ là **một Spring Boot application đầy đủ về phần code Java tối thiểu**; để thực sự đăng nhập, cần provider thật, credentials, HTTPS/trust, callback được đăng ký và các build plugins Spring Boot/JDK của dự án. Không biên dịch file này đơn lẻ bằng `javac` vì nó dùng thư viện Spring; trong dự án Boot chạy `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`). Truy cập `/private` khi chưa đăng nhập sẽ khởi động cơ chế xác thực theo cấu hình login; request hoàn tất chỉ khi IdP và callback hoạt động.

Nếu ứng dụng của bạn là **WebFlux**, phải dùng `SecurityWebFilterChain`/`ServerHttpSecurity` và repository reactive tương ứng; ví dụ `HttpSecurity` ở đây dành riêng cho Servlet.

## 5. Redirect URI: ba đường dẫn không được nhầm với nhau

Giả sử `registrationId = company`:

| Loại URL | Ví dụ | Bên xử lý |
| --- | --- | --- |
| **Khởi động OAuth Login** | `https://app.example.test/oauth2/authorization/company` | Spring Security phía client nhận yêu cầu và tạo authorization request |
| **Authorization endpoint của IdP** | `https://id.example.test/realms/staff/protocol/openid-connect/auth` (tùy IdP) | IdP hiển thị đăng nhập/consent |
| **OAuth redirect URI / callback** | `https://app.example.test/login/oauth2/code/company` | Spring Security phía client nhận `code` và `state` |
| **Trang đích sau login** | `https://app.example.test/private` hoặc saved request | Ứng dụng điều hướng người dùng sau khi xác thực hoàn tất |

`redirect_uri` là nơi **Authorization Server gửi authorization response về browser**; nó không phải URL dẫn user tới login của IdP, cũng không phải trang dashboard sau đăng nhập. Các hệ thống có **logout callback/post-logout redirect URI** riêng, không được trộn với OAuth 2.0 authorization callback.

Spring Security Servlet mặc định dùng:

~~~text
Initiate login : /oauth2/authorization/{registrationId}
Callback       : /login/oauth2/code/{registrationId}
redirect-uri   : {baseUrl}/login/oauth2/code/{registrationId}
~~~

Với public base URL `https://app.example.test` và `registrationId = company`, URI mà IdP phải **cho phép chính xác** là:

~~~text
https://app.example.test/login/oauth2/code/company
~~~

Nếu bạn khởi động ứng dụng cục bộ ở `http://localhost:8080` và IdP cho phép callback thử nghiệm, URI tương ứng là `http://localhost:8080/login/oauth2/code/company`. Đừng thêm callback localhost vào client production khi không có nhu cầu và chính sách cho phép.

**Quy tắc khớp:** Authorization server nên thực hiện so khớp redirect URI chính xác với danh sách đã đăng ký. Đặc biệt chú ý scheme (`http` so với `https`), domain, cổng, context path, viết hoa/thường, dấu gạch chéo cuối và `registrationId`. Tránh wildcard, domain do người dùng nhập, redirect callback tới host không kiểm soát và đường dẫn có hành vi open redirect. Ngoại lệ tiêu chuẩn về loopback redirect của một số native app không phải lý do để mở wildcard cho web backend.

### Thay đổi callback phải đổi cả ba nơi

Ví dụ có yêu cầu nhận callback tại `/auth/callback/company`, phải đồng bộ:

1. `ClientRegistration.redirectUri`: `{baseUrl}/auth/callback/{registrationId}`.
2. Filter xử lý authorization response của Spring Security: `/auth/callback/*`.
3. Danh sách redirect URI chính xác trong IdP: `https://app.example.test/auth/callback/company`.

Cấu hình Servlet minh họa:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                    .redirectionEndpoint(endpoint -> endpoint
                            .baseUri("/auth/callback/*")))
            .build();
}
~~~

Code này **thay thế** phương thức `securityFilterChain` trong ví dụ trước, không khai báo song song hai bean cùng chức năng. Đồng thời sửa dòng YAML thành:

~~~yaml
redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
~~~

Nếu bạn chỉ sửa YAML mà quên cập nhật `redirectionEndpoint`, IdP có thể trả code thành công nhưng Spring không bắt callback ở đường mới. Nếu chỉ sửa endpoint Spring mà quên cấu hình IdP, IdP có thể từ chối ngay authorization request với lỗi `redirect_uri_mismatch` hoặc lỗi tương đương.

## 6. `{baseUrl}`, HTTPS proxy và đường dẫn triển khai

Các biến template URI mà Spring Security hỗ trợ gồm `{baseScheme}`, `{baseHost}`, `{basePort}`, `{basePath}`, `{registrationId}`; `{baseUrl}` biểu thị tổ hợp scheme, host, port và base path. Điều này hữu ích khi cùng cấu hình chạy ở local, staging, production.

Ví dụ ứng dụng thực tế:

~~~text
Browser:     https://app.example.test/portal/private
Reverse proxy / ingress: TLS termination at public edge
Backend:     http://service:8080/portal/private

Callback public expected:
https://app.example.test/portal/login/oauth2/code/company
~~~

Nếu backend thấy scheme nội bộ là `http`, host `service` hoặc port `8080` và tính ra:

~~~text
http://service:8080/portal/login/oauth2/code/company
~~~

thì IdP rất có thể từ chối hoặc browser không thể truy cập callback. Cần kiểm tra cấu hình trusted forwarded headers (`Forwarded` / `X-Forwarded-*`), host public và context path. Với Spring Boot Servlet, cơ chế `server.forward-headers-strategy` có thể dùng theo môi trường; ví dụ `framework` chỉ phù hợp khi reverse proxy của bạn **loại bỏ/ghi đè header do client bên ngoài gửi** và ứng dụng chỉ tin proxy được kiểm soát.

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Không bật tin mọi `X-Forwarded-Host` đến từ internet: attacker có thể tác động URL được dựng nếu proxy không lọc header. Hai lựa chọn thường được cân nhắc là:

- **Callback absolute URI cho production:** cấu hình `redirect-uri: "https://app.example.test/login/oauth2/code/company"` để có giá trị cố định theo environment. Cần cấu hình riêng ở staging/local và bảo đảm path callback đúng.
- **Template `{baseUrl}`:** linh hoạt nhiều môi trường; xác minh nghiêm ngặt public origin, context path và chính sách forwarded headers qua integration test.

Nếu gateway gắn tiền tố `/portal` nhưng app không thấy tiền tố tương ứng, phải quyết định nơi rewrite path và xử lý forwarded prefix cho nhất quán; đừng sửa redirect URI đơn lẻ khi mapping callback chưa tương thích.

## 7. Thông tin định danh ứng dụng trong IdP

Khi tạo client ở IdP, bạn thường phải khai báo một tập hợp dữ liệu như sau:

| Mục IdP | Giá trị minh họa | Đối chiếu với Spring |
| --- | --- | --- |
| Client type | Confidential web application (backend) | Client có thể giữ secret ở server |
| Client ID | `app-web-prod` (do IdP cấp) | `client-id`, **không phải** `company` |
| Client secret / authentication method | Secret qua Vault, xác thực HTTP Basic ở token endpoint | `client-secret` / `client-authentication-method` |
| Grant types | Authorization Code | `authorization-grant-type: authorization_code` |
| Allowed redirect URIs | `https://app.example.test/login/oauth2/code/company` | Redirect thực tế phải khớp giá trị này |
| Issuer/tenant/realm | `https://id.example.test/realms/staff` | `provider.staff-idp.issuer-uri` |
| Allowed scopes | `openid`, `profile`, `email` | Các scope được phép và được yêu cầu |
| Allowed origins / CORS (nếu có) | Các origin do IdP yêu cầu | Không nhầm cấu hình CORS với redirect URI allowlist |
| Post-logout redirect URIs (nếu có) | URI logout được IdP cho phép | Tách biệt authorization callback |

**Client ID khác nhau giữa môi trường:** nhiều tổ chức tạo riêng ứng dụng `app-web-local`, `app-web-staging`, `app-web-prod`, mỗi client có credential và callback allowlist riêng. Cách này giới hạn phạm vi ảnh hưởng khi lộ secret và giúp rotate độc lập.

**Một client nhiều provider/tenant:** nếu có hai IdP hoặc nhiều realm, mỗi `ClientRegistration` cần trỏ tới đúng issuer và credential của client đó. Không tự nhận `issuer-uri`, `redirect-uri`, `client-id` từ HTTP query chưa tin cậy để thay đổi runtime registration. Mọi provider được dùng trong đăng nhập phải nằm trong registry đã phê duyệt, với chính sách mapping user và account linking rõ ràng.

## 8. Confidential client, public client và PKCE

| Trường hợp | Có bảo vệ được secret? | Luồng nên dùng |
| --- | --- | --- |
| Backend web/BFF xử lý token | Có, nếu secret chỉ ở server | Authorization Code; dùng client authentication phù hợp; ưu tiên PKCE khi IdP hỗ trợ |
| SPA chạy trong browser | Không | Authorization Code + PKCE với **public client**; không phát hành secret cho browser |
| Native mobile/desktop | Không | Authorization Code + PKCE và callback/loopback đã đăng ký đúng policy |
| Service-to-service không có browser/user | Có thể | `client_credentials`, không dùng callback login hoặc ID Token của user |

**PKCE** thêm `code_challenge` trong authorization request và `code_verifier` khi đổi code, giúp giảm nguy cơ kẻ khác dùng được authorization code bị chặn bắt. Nó **không** làm `client_secret` trở nên an toàn khi nhúng vào SPA. Spring Security hỗ trợ PKCE; đối với public client phù hợp, framework tự kích hoạt theo cấu hình `client-authentication-method: none` và thiếu `client-secret`, hoặc có thể cấu hình yêu cầu PKCE với client hỗ trợ. Hãy xác minh PKCE yêu cầu tại IdP, đặc biệt khi có confidential client.

Ba giá trị bảo mật khác nhau:

- **`state`:** ràng buộc authorization response với yêu cầu đã khởi tạo, chống callback giả mạo/CSRF và giúp giữ liên hệ với phiên đăng nhập.
- **PKCE `code_verifier`:** ràng buộc lượt đổi authorization code với phía đã tạo authorization request.
- **OIDC `nonce`:** ràng buộc ID Token với yêu cầu xác thực tương ứng, giảm nguy cơ replay; framework và provider phải phối hợp đúng quy cách.

Không tự bỏ các kiểm tra này để “sửa nhanh” callback lỗi. Session/cookie lưu authorization request phải được bảo vệ; trong hệ thống nhiều instance, cần cấu hình lưu trữ phiên phù hợp để callback tìm thấy yêu cầu gốc. Khi callback `state` sai/mất, phân tích vấn đề session, cookie, proxy, SameSite, load balancer hoặc request repository; không tự chấp nhận `state` bất kỳ.

## 9. Client ID, issuer và danh tính người dùng trong OIDC

OAuth 2.0 định nghĩa **ủy quyền truy cập tài nguyên**. OIDC mở rộng nó với ID Token để diễn đạt **xác thực người dùng** trong ngữ cảnh issuer cụ thể. Với OIDC:

- `client_id` nhận diện **ứng dụng** với IdP. Một ứng dụng phục vụ hàng nghìn người dùng vẫn dùng cùng một `client_id` theo môi trường.
- `iss` định danh **nhà phát hành ID Token** và phải trùng issuer tin cậy đã cấu hình.
- `aud` phải chứa **client_id** của ứng dụng nhận ID Token; kiểm tra audience là một phần quan trọng của validation.
- `sub` nhận diện **người dùng** ở phạm vi issuer; khi cần key người dùng bền vững, dùng cặp `(iss, sub)`. Không giả định `sub` ổn định giữa IdP hoặc client khi provider áp dụng subject dạng pairwise.
- `email` và `preferred_username` là claims tùy provider và có thể thay đổi; không dùng làm định danh bảo mật duy nhất nếu không có chính sách rõ.
- `scope=openid` yêu cầu OIDC; `scope=profile,email` đề nghị thêm claims. **Scope không tự biến thành quyền admin hoặc Spring authorities**.

Spring Security, khi đã cấu hình OIDC phù hợp, xác minh các điều kiện cốt lõi của ID Token qua thành phần OIDC; không nên lấy token từ callback rồi tự decode Base64 và tin mọi claim. Cần phân biệt ID Token dùng cho **client nhận diện user** với Access Token dùng để **gọi protected resource**; không dùng ID Token tùy tiện làm Bearer Access Token cho API riêng.

Ví dụ lấy đúng thông tin đã được Spring xử lý trong một controller đã được bảo vệ:

~~~java
package example.security;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "issuer", user.getIdToken().getIssuer().toString(),
                "subject", user.getSubject());
    }
}
~~~

Đây là **controller minh họa trong ứng dụng chỉ cho OIDC users**; nếu ứng dụng hỗ trợ cả OAuth2 không OIDC hoặc xác thực khác, tham số `OidcUser` có thể không có và phải xử lý theo loại principal. Endpoint trả issuer + subject chỉ nên sử dụng khi chức năng thực sự yêu cầu; production cần xem xét không phơi bày định danh cho client ngoài nhu cầu.

## 10. Kiểm tra `ClientRegistration` bằng Java 17 và JUnit 5

Không nhất thiết phải kết nối IdP thật để kiểm tra rằng các trường `ClientRegistration` được ánh xạ đúng. Ví dụ dưới tạo repository trong bộ nhớ và xác minh các trường cốt lõi; đây là **unit test chạy được** khi dự án có `spring-boot-starter-oauth2-client` và JUnit 5.

Tệp `src/test/java/example/security/ClientRegistrationContractTest.java`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class ClientRegistrationContractTest {

    @Test
    void resolvesExpectedClientIdentityAndRedirectTemplate() {
        ClientRegistration registration =
                ClientRegistration.withRegistrationId("company")
                        .clientId("web-test-client")
                        .clientSecret("test-only-secret")
                        .clientAuthenticationMethod(
                                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(
                                AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                        .scope("openid", "profile")
                        .authorizationUri("https://id.example.test/oauth2/authorize")
                        .tokenUri("https://id.example.test/oauth2/token")
                        .jwkSetUri("https://id.example.test/oauth2/keys")
                        .issuerUri("https://id.example.test")
                        .clientName("Test SSO")
                        .build();

        InMemoryClientRegistrationRepository repository =
                new InMemoryClientRegistrationRepository(registration);

        ClientRegistration actual = repository.findByRegistrationId("company");

        assertNotNull(actual);
        assertEquals("company", actual.getRegistrationId());
        assertEquals("web-test-client", actual.getClientId());
        assertEquals(AuthorizationGrantType.AUTHORIZATION_CODE,
                actual.getAuthorizationGrantType());
        assertEquals("{baseUrl}/login/oauth2/code/{registrationId}",
                actual.getRedirectUri());
        assertEquals("https://id.example.test",
                actual.getProviderDetails().getIssuerUri());
    }
}
~~~

Lệnh chạy trong dự án Spring Boot dùng Gradle wrapper:

~~~bash
./gradlew test --tests example.security.ClientRegistrationContractTest
~~~

Trên Windows dùng `.\gradlew.bat test --tests example.security.ClientRegistrationContractTest`. Kết quả mong đợi: **JUnit test pass**; không có stdout riêng từ lớp test. Chuỗi `test-only-secret` ở đây là dữ liệu giả nằm trong một phép thử không kết nối mạng; không bao giờ dùng nó như secret thật.

Test này chỉ kiểm tra model/repository. Nó **không** chứng minh HTTPS/TLS, metadata discovery, callback HTTP, token exchange, cookie state, PKCE hoặc xác minh ID Token end-to-end. Các yếu tố đó cần integration test với IdP thử nghiệm hoặc môi trường staging được phép.

### Kiểm tra redirect thực tế bằng browser/HTTP

Trong môi trường thử nghiệm có cấu hình hợp lệ:

1. Truy cập `https://app.example.test/oauth2/authorization/company`.
2. Quan sát HTTP 302 do Spring tạo: header `Location` phải hướng đến **authorization endpoint của IdP** với `client_id` và `redirect_uri` đúng (cùng `response_type=code`, `state` và các tham số khác do framework tạo).
3. Trên IdP, thử login bằng tài khoản test. Callback ở `https://app.example.test/login/oauth2/code/company` phải vào đúng Spring filter và hoàn tất đổi code.
4. Xác minh người dùng chỉ truy cập `/private` khi đã được xác thực; trả lỗi nếu `state` sai, code hết hạn, issuer không hợp lệ hoặc token/audience sai.

Chỉ dùng công cụ network/debugger trên môi trường thử nghiệm. Authorization code, `state`, cookie session và token có thể chứa dữ liệu nhạy cảm; không chụp hoặc chia sẻ raw callback query trong log/ticket. Không gõ `code` tùy ý vào callback để giả lập login thành công.

## 11. Sự cố thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra đúng |
| --- | --- | --- |
| IdP báo `redirect_uri_mismatch` / invalid redirect URI | URL public khác giá trị đăng ký ở IdP | So sánh scheme, host, port, path, `registrationId`, slash cuối; xem URL thật trong authorization request |
| Callback nhận 404 hoặc vào handler khác | `ClientRegistration.redirectUri` và Spring redirection endpoint không khớp | Mặc định filter `/login/oauth2/code/*` hoặc điều chỉnh cả hai đầu nếu đã đổi |
| Authorization URL có `client_id` không mong đợi | Dùng nhầm client của staging/tenant hoặc nhầm registration | Đối chiếu cặp `registrationId` – `client_id` – `issuer` và cấu hình runtime |
| Token endpoint báo `invalid_client` | Client secret sai/hết hạn, sai authentication method, sai client type | Kiểm tra credential backend và phương thức IdP hỗ trợ; không in secret |
| Token endpoint báo `invalid_grant` | Code hết hạn/đã dùng, redirect URI không nhất quán, PKCE verifier sai | Kiểm tra flow và timing; mỗi authorization code chỉ được dùng đúng quy cách |
| Callback báo state/session không tìm thấy | Browser mất session cookie, proxy/load balancer/session store lỗi | Kiểm tra cookie policy, SameSite, TLS, session persistence và auth request repository |
| URI thành `http://internal:8080/...` | Backend sinh `{baseUrl}` từ host/protocol nội bộ | Kiểm tra trusted forwarded headers và ingress; kiểm thử public origin |
| OIDC token bị từ chối vì issuer/audience | Sai realm/issuer, client ID không đúng hoặc cấu hình provider lệch | Xác minh discovery, issuer metadata và client registration, không tắt validation |
| Không thấy đường đăng nhập dự kiến | Sai `registrationId`, chưa có repository phù hợp hoặc đổi authorization endpoint | Kiểm tra `/oauth2/authorization/{registrationId}` và security configuration |
| Mở được đăng nhập nhưng không có quyền truy cập ứng dụng | Scope/claims/authorities mapping chưa đúng | Tách lỗi authentication khỏi authorization; rà soát mapping nhóm/roles |
| Sau đổi secret, các instance trả lỗi không đồng đều | Instance chưa cập nhật credentials hoặc còn session/authorized client cũ | Rà soát chiến lược rotation, rollout và trạng thái token/cookie |

Đừng giải quyết các lỗi này bằng cách **mở wildcard callback**, vô hiệu hóa TLS, bỏ `state`, tin mọi ID Token, chuyển sang implicit flow, hoặc in `client_secret` để đối chiếu. Những thay đổi ấy che lỗi tích hợp và mở lỗ hổng bảo mật.

## 12. Quy trình thay đổi `client_id`, secret và redirect URI

Khi triển khai sang môi trường mới hoặc rotate credential, nên thực hiện tuần tự:

1. **Xác định client/IdP chính xác:** lưu metadata không bí mật của ứng dụng gồm tên môi trường, owner, `registrationId`, `client_id`, `issuer`, grant và callback chính xác.
2. **Đăng ký client ở IdP:** bật `authorization_code`, cấu hình client type, authentication method, scopes, redirect allowlist và chính sách PKCE. Tạo client riêng cho production khi có thể.
3. **Cấp bí mật an toàn:** inject `client_secret`/private key qua secret manager hoặc kênh triển khai được duyệt; phân quyền và audit quyền đọc.
4. **Đồng bộ callback:** so sánh `ClientRegistration.redirectUri`, filter xử lý callback và danh sách ở IdP; kiểm thử cả sau proxy và với context path nếu có.
5. **Triển khai và kiểm chứng:** kiểm thử authorization request, callback, ID Token, đăng nhập thất bại, session và redirect sau login; dùng tài khoản test.
6. **Rotate có cửa sổ kiểm soát:** nếu IdP cho phép nhiều secret hợp lệ song song, cập nhật app từng đợt rồi thu hồi secret cũ; nếu không, lên kế hoạch đồng bộ và rollback. Không lưu secret cũ trong ticket.
7. **Theo dõi vận hành:** tỷ lệ login thành công/thất bại, lỗi `invalid_client`/`invalid_grant`, callback 4xx/5xx, issuer mismatch và TLS handshake; tránh log raw token/code/state.

Một ứng dụng phục vụ nhiều tenant cần chính sách xác định tenant từ nguồn đáng tin trước khi chọn registration. Không dựa vào email domain người dùng chưa được xác thực để tự động chọn client với quyền cao hoặc host redirect tùy ý.

## 13. Checklist trước khi đưa OAuth2/OIDC client vào production

- [ ] `registrationId` duy nhất, ánh xạ đúng `client_id`, `issuer`, provider endpoints và môi trường triển khai.
- [ ] Đúng loại client: backend confidential / SPA public; secret không hiện diện trong frontend bundle, Git, URL, log hoặc telemetry.
- [ ] Dùng Authorization Code, PKCE theo chính sách provider; không dùng `client_credentials` để đăng nhập con người.
- [ ] Redirect URI công khai là HTTPS, khớp chính xác allowlist tại IdP, không chứa wildcard/open redirect.
- [ ] URI bắt đầu login, URI callback và URI sau login được thiết kế rõ; custom callback sửa đồng bộ Spring filter và IdP.
- [ ] `{baseUrl}` tính đúng scheme, host, port, base path qua reverse proxy tin cậy; header giả từ client không được ảnh hưởng redirect.
- [ ] Spring Security giữ và kiểm tra `state`, PKCE/nonce đúng quy tắc, session/cookie được bảo vệ.
- [ ] OIDC ID Token được xác minh chữ ký, issuer, audience, hiệu lực và các ràng buộc cần thiết; key người dùng dựa trên issuer + subject.
- [ ] Scope/claims và quyền ứng dụng được ánh xạ/kiểm tra tường minh; `client_id` không dùng như quyền của người dùng.
- [ ] Có integration test cho redirect URI sai, `invalid_client`, state mismatch, code hết hạn, issuer/audience sai và không có session.
- [ ] Rotation của secret, certificate/keys và thay đổi IdP metadata có owner, quan sát lỗi và cách rollback an toàn.

**Điểm ghi nhớ:** `ClientRegistration` mô tả **ứng dụng Spring đăng ký với một IdP**. `registrationId` là khóa trong Spring, `client_id` là định danh ứng dụng tại IdP, còn `client_secret` là bí mật của ứng dụng nếu nó là confidential client. `redirect_uri` là callback đã được IdP cho phép, phải trùng đường Spring thực sự xử lý. Danh tính của **người dùng** trong OIDC được xác minh từ token và issuer, không suy ra từ `client_id` hoặc chỉ từ email.

## Tài liệu đối chiếu

- [Spring Security — OAuth 2.0 Login: Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — OAuth 2.0 Login: Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth 2.0 Client: Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — Authorization Grants and PKCE](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security — OAuth 2.0 Login with WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
