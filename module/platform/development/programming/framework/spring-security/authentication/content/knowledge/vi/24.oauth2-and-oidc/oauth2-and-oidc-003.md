# Luồng Authorization Code và các bước tạo danh tính tại ứng dụng

## 1. Mục tiêu bài học

Khi người dùng chọn **Đăng nhập bằng Google** hoặc bằng một nhà cung cấp danh tính (Identity Provider, IdP) của doanh nghiệp, ứng dụng Spring Boot thường không tự nhận mật khẩu của người dùng. Trình duyệt được chuyển sang IdP để đăng nhập. Sau đó IdP trả về một **authorization code** ngắn hạn. Ứng dụng sử dụng code để lấy các token, xác minh thông tin cần thiết và tạo một phiên đăng nhập ở chính ứng dụng.

Bài học giải thích hai phần gắn với nhau:

1. **Authorization Code flow:** yêu cầu đăng nhập, chuyển hướng, kiểm tra `state`, đổi `code` lấy token, xử lý lỗi và chống tấn công.
2. **Tạo danh tính trong Spring Security:** từ ID Token/OIDC claims hoặc OAuth2 UserInfo đến `OidcUser`/`OAuth2User`, `Authentication`, `SecurityContext`, phiên ứng dụng, quyền nội bộ và liên kết với tài khoản local.

Sau bài này, bạn có thể mô tả chính xác ai chịu trách nhiệm ở mỗi bước, dùng `oauth2Login()` trong Spring Security Servlet, đọc danh tính người dùng đã đăng nhập, nhận biết giới hạn của các loại token và kiểm thử các trường hợp quan trọng.

**Phạm vi:** trọng tâm là ứng dụng Spring Boot **đăng nhập người dùng bằng Authorization Code**, với OIDC là trường hợp tiêu chuẩn để chứng thực danh tính. Đây khác với ứng dụng thuần API chỉ xác minh bearer access token bằng `oauth2ResourceServer()`.

## 2. Phân biệt OAuth 2.0 Authorization Code và OpenID Connect

OAuth 2.0 định nghĩa cơ chế **ủy quyền** để một client lấy access token và gọi tài nguyên được bảo vệ. OAuth 2.0 cơ bản không tự chuẩn hóa cách biểu diễn danh tính người dùng cho đăng nhập ứng dụng.

**OpenID Connect (OIDC)** mở rộng OAuth 2.0 để **xác thực người dùng**. Khi client yêu cầu scope `openid`, OIDC Provider cấp **ID Token** chứa các claims nhận diện và xác thực; client phải xác minh ID Token trước khi coi đó là kết quả đăng nhập đáng tin cậy.

| Thuật ngữ | Mục đích | Có dùng để xác lập danh tính đăng nhập? |
| --- | --- | --- |
| `authorization code` | Mã ngắn hạn, dùng một lần, trình duyệt chuyển đến callback để client đổi token | Không. Code là vật liệu của giao thức, chưa phải danh tính |
| `access token` | Cho phép client gọi API/resource server phù hợp với scope và audience | Không mặc nhiên. Access token dành cho resource server, không dùng thay ID Token |
| `id_token` (OIDC) | Token chứa `iss`, `sub`, `aud`, thời hạn và thông tin xác thực của người dùng | Có, **sau khi xác minh** theo quy tắc OIDC |
| `refresh token` | Xin access token mới mà không cần chạy lại tương tác của user nếu nhà cung cấp cấp token này | Không phải bằng chứng danh tính độc lập |
| `UserInfo` (OIDC) | Endpoint trả thêm các claims người dùng qua access token | Bổ sung profile; cần bảo đảm `sub` khớp ID Token |
| `session cookie` của ứng dụng | Cho browser mang session ID ứng dụng vào request kế tiếp | Được ứng dụng dùng để khôi phục đăng nhập đã tạo, không phải ID Token |
| `Spring Security Authentication` | Đối tượng principal, authorities, trạng thái authenticated trong `SecurityContext` | Chính là biểu diễn danh tính và quyền **bên trong ứng dụng** |

Một số provider cho phép “Login with ...” chỉ dùng OAuth 2.0 + một user profile API, không có ID Token. Spring Security vẫn hỗ trợ qua `DefaultOAuth2UserService` và `OAuth2User`, nhưng ứng dụng phải hiểu hợp đồng đặc thù của provider. Để tạo danh tính thống nhất giữa nhiều IdP, nên ưu tiên OIDC khi có thể.

## 3. Vai trò trong Authorization Code flow

- **Resource Owner / End User:** người sử dụng trình duyệt và đăng nhập tại IdP.
- **User Agent:** trình duyệt mang chuyển hướng giữa các miền, nhưng không nên được giao client secret.
- **OAuth Client / Relying Party (RP):** ứng dụng Spring Boot nhận callback, đổi code và tạo session của mình.
- **Authorization Server / OpenID Provider (OP):** hệ thống xác thực người dùng, trả authorization code và phát hành token.
- **Resource Server / UserInfo endpoint:** nơi có dữ liệu được bảo vệ bằng access token; có thể cùng hoặc khác hệ thống authorization server.

Sơ đồ tổng quát:

```text
Browser                 Spring Boot (OAuth Client)             IdP / OIDC Provider
   |                             |                                      |
   |-- GET /private/me --------->|                                      |
   |<--- 302 /login ------------|                                      |
   |-- GET /oauth2/authorization/google ------------------------------->|
   |                             |  (Spring tạo state, nonce, PKCE*)   |
   |<--- 302 tới /authorize ------|                                      |
   |------------------------ GET /authorize?... ----------------------->|
   |                             |                           Đăng nhập/MFA/consent
   |<------------------ 302 redirect_uri?code=...&state=... ----------|
   |-- GET /login/oauth2/code/google?code=...&state=... -->|
   |                             |-- POST /token (back channel) ------->|
   |                             |<-- access_token, id_token*, ... ----|
   |                             |   Kiểm tra giao thức/ID Token        |
   |                             |   OidcUser + Authentication         |
   |                             |   SecurityContext + local session   |
   |<--------- 302 /private/me --|                                      |
   |-- GET /private/me + session cookie -->|                            |
   |<-- 200, danh tính đã đăng nhập -------|                            |
```

Dấu `*`: `nonce` và `id_token` thuộc OIDC; PKCE tùy loại client/chính sách và nên được dùng theo hướng dẫn OAuth hiện đại. Không phải mọi OAuth 2.0 provider đều phát hành ID Token.

Mấu chốt: **authorization code đi qua browser, còn việc đổi code lấy token diễn ra trực tiếp từ backend đến token endpoint** (đối với ứng dụng web chạy phía server). Browser thường chỉ nhận session cookie của ứng dụng; không cần giữ access token hay ID Token trong JavaScript để duy trì đăng nhập server-side.

## 4. Luồng từng bước, từ request đầu tới phiên đã xác thực

### Bước 1. Người dùng truy cập tài nguyên được bảo vệ

Ví dụ người dùng mở `GET /private/me`. `SecurityFilterChain` thấy endpoint yêu cầu `authenticated()` mà request chưa có Authentication hợp lệ. Với `oauth2Login()`, Spring Security có thể chuyển browser tới trang login rồi tới nhà cung cấp đã cấu hình.

Một lựa chọn trực tiếp là liên kết:

```text
GET /oauth2/authorization/google
```

`google` là **registrationId** trong `ClientRegistrationRepository`, không nhất thiết là tên giao thức. Nếu có nhiều IdP, ứng dụng có thể có `google`, `corporate`, `partner`, mỗi registration có issuer/client credentials và redirect URI riêng.

### Bước 2. Spring dựng authorization request và chuyển hướng browser

Trong Servlet, `OAuth2AuthorizationRequestRedirectFilter` phối hợp `OAuth2AuthorizationRequestResolver` và `ClientRegistrationRepository`. Nó tạo authorization request, gồm các trường phổ biến:

- `response_type=code`: yêu cầu Authorization Code flow.
- `client_id`: nhận diện ứng dụng đã đăng ký với IdP.
- `redirect_uri`: URI callback chính xác đã đăng ký, ví dụ `https://app.example.com/login/oauth2/code/google`.
- `scope=openid profile email` nếu là OIDC.
- `state`: giá trị khó đoán dùng liên kết authorization response với login request đang chờ, hỗ trợ chống login CSRF.
- `nonce` (OIDC khi được dùng): ràng buộc ID Token với phiên xác thực, chống replay.
- `code_challenge` / `code_challenge_method=S256` khi dùng **PKCE**.

Spring lưu thông tin authorization request đang chờ bằng `AuthorizationRequestRepository`. Với luồng Servlet thông dụng, `HttpSessionOAuth2AuthorizationRequestRepository` dùng HTTP session. Cookie này **chưa chứng minh user đã đăng nhập**; nó duy trì trạng thái giao thức và giúp đối chiếu callback.

Sau đó Spring trả HTTP `302 Location: https://idp.example/authorize?...`. Trình duyệt thực sự di chuyển đến IdP.

### Bước 3. IdP xác thực người dùng

IdP thực hiện đăng nhập, MFA, SSO/session check và có thể hỏi consent. **Ứng dụng Spring không nhìn thấy mật khẩu của người dùng** ở bước này.

Nếu thành công, IdP chuyển trình duyệt về URI callback đã đăng ký với `code` và `state`. Nếu thất bại hoặc user từ chối, callback có thể mang `error` và `state` thay vì `code`.

Ví dụ cú pháp (giá trị chỉ minh họa, không có hiệu lực):

```http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/google?code=ONE_TIME_CODE&state=RANDOM_STATE
```

Không đặt code hoặc token thật vào log, analytics, crash report hay URL bên ngoài. Thực hành tốt còn gồm `Referrer-Policy` phù hợp, HTTPS và hạn chế tài nguyên bên thứ ba trên trang callback.

### Bước 4. Callback phải khớp authorization request đã khởi tạo

`OAuth2LoginAuthenticationFilter` mặc định xử lý đường dẫn:

```text
/login/oauth2/code/{registrationId}
```

Filter xác định registration, lấy authorization request đang chờ và đối chiếu `state` với callback. Callback không có request tương ứng, sai `state` hoặc mã lỗi phải dẫn tới **thất bại đăng nhập**, không được tự xây dựng một principal bằng chuỗi query parameter.

Đây cũng là lý do không nên tùy tiện thay cách lưu authorization request, cấu hình cookie/session hoặc routing callback khi triển khai qua nhiều node. Nếu state mất do session sai, callback hợp lệ vẫn không xử lý được.

### Bước 5. Backend đổi authorization code lấy token

Ứng dụng gửi request `POST` tới **token endpoint của IdP** qua kênh server-to-server. Tùy loại client, nó dùng cơ chế xác thực client đã đăng ký như `client_secret_basic` hoặc `private_key_jwt`. Nếu áp dụng PKCE thì gửi cả `code_verifier` để IdP so với challenge ở bước đầu. Authorization code cần đúng client và redirect URI, thường có tuổi thọ ngắn và chỉ dùng một lần.

Dạng minh họa:

```http
POST /token HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fgoogle
```

Phần minh họa chưa thể hiện client authentication hoặc PKCE verifier; trong ứng dụng thật Spring Security gửi các tham số và credentials cần thiết theo `ClientRegistration`.

Token response OIDC thường có `access_token`, `token_type`, `expires_in`, `id_token`; `refresh_token` chỉ khi provider/chính sách cấp. Nếu chỉ OAuth 2.0, ID Token có thể không tồn tại.

### Bước 6. Xác minh ID Token và nạp thông tin người dùng

Đối với OIDC, client cần xác minh kết quả giao thức, bao gồm khi phù hợp:

1. Chữ ký ID Token qua khóa được tin cậy (theo thuật toán và key policy cấu hình).
2. `iss` khớp issuer IdP dự kiến, không tin issuer tùy ý do callback cung cấp.
3. `aud` chứa client ID thích hợp; xử lý `azp` khi giao thức yêu cầu.
4. `exp`, `iat` và các ràng buộc thời gian có liên quan.
5. `nonce` khớp yêu cầu trước đó nếu đã gửi.
6. Kiểm tra các điều kiện bổ sung theo profile/response type/provider.

Spring Security OIDC dùng cơ chế riêng của `OidcAuthorizationCodeAuthenticationProvider` và `OidcUserService`; thông thường không cần tự viết bộ xác minh JWT ở controller. Nếu dùng UserInfo endpoint để lấy profile, nội dung `sub` phải tương ứng với ID Token. Không tin một JSON từ UserInfo URL tự điền hoặc chỉ đọc claim bằng thao tác Base64 decode mà không kiểm chứng.

**ID Token để ứng dụng nhận diện người dùng; access token để gọi API.** Đưa ID Token làm bearer token đến API không phải là thay thế tương đương cho access token.

### Bước 7. Spring Security tạo principal và Authentication

Sau khi token exchange/validation thành công, Spring tạo user principal:

- OIDC: `OidcUser`, thường là `DefaultOidcUser`, cung cấp ID Token, các claims và UserInfo (nếu được nạp).
- OAuth 2.0 không OIDC: `OAuth2User` từ `OAuth2UserService`, thường là `DefaultOAuth2UserService`.
- Kết quả đăng nhập dạng `OAuth2AuthenticationToken` chứa principal, authorities, `authenticated=true` và `authorizedClientRegistrationId`.

Đây là bước biến “IdP đã xác thực người dùng” thành **“ứng dụng có một Authentication hợp lệ”**. Từ đó security rules như `authenticated()`, `hasRole(...)` hoặc method security có dữ liệu để xử lý.

Một Authentication thường chứa:

```text
Authentication (OAuth2AuthenticationToken)
├── principal: OidcUser
│   ├── idToken: iss, sub, aud, exp, ...
│   ├── userInfo: profile claims nếu có
│   └── authorities: OIDC_USER, SCOPE_* hoặc vai trò đã ánh xạ
├── authenticated: true
└── authorizedClientRegistrationId: google
```

Tùy phiên bản Spring Security và mapper, bộ authorities cụ thể có thể khác nhau. `SCOPE_profile` không đồng nghĩa `ROLE_ADMIN`.

### Bước 8. Gắn danh tính với tài khoản nội bộ (nếu ứng dụng cần)

Ứng dụng có thể chỉ cần `OidcUser` để biết ai đang đăng nhập; nhưng phần lớn sản phẩm có tài khoản nội bộ, phân quyền, dữ liệu riêng, trạng thái người dùng, tenant và chính sách khác IdP.

Hãy tách ba lớp:

- **External identity:** một subject do IdP xác minh.
- **Local account:** bản ghi user nội bộ có ID do ứng dụng sở hữu.
- **Authorization:** vai trò/quyền/tenant do chính sách ứng dụng quyết định.

Đối với OIDC, khóa liên kết bền vững thường là **cặp (`iss`, `sub`)**. `sub` chỉ là duy nhất trong phạm vi issuer, nên một `sub` giống nhau từ hai IdP khác nhau không được tự xem là cùng người.

Sơ đồ ánh xạ:

```text
OIDC ID Token: iss=https://login.example/realm-a, sub=user-9021
                     |
                     v
external_identity(issuer, subject)  --unique--> local_user_id=UUID
                     |
                     v
app_user(id, status, tenant, ...)
                     |
                     v
membership + role_policy + resource authorization
```

Email, tên hiển thị hoặc ảnh đại diện là dữ liệu profile dễ thay đổi; **không dùng email chưa được kiểm chứng để tự động ghép vào tài khoản đã có**. Kể cả `email_verified=true`, việc liên kết tài khoản cũ giữa IdP và ứng dụng vẫn cần chính sách minh bạch để tránh chiếm đoạt tài khoản khi email có thể được tái cấp phát.

Quy trình tạo/link local identity cần được xử lý có giao dịch và ràng buộc unique:

1. Đọc `iss`, `sub` từ **ID Token đã kiểm chứng**.
2. Tìm `external_identity` theo đúng cả hai giá trị.
3. Nếu đã link, lấy user nội bộ; kiểm tra trạng thái disabled/locked/tenant.
4. Nếu chưa link, tuân thủ chính sách sản phẩm: tạo account mới, yêu cầu lời mời, quản trị viên phê duyệt hoặc yêu cầu user link vào account đang tồn tại bằng một phiên xác thực riêng.
5. Lưu bản ghi liên kết với khóa unique để hai login đồng thời không sinh hai danh tính.
6. Nạp authorities từ nguồn quyền được phê duyệt và cung cấp cho Spring Security.
7. Không lưu access token, ID Token hay client secret trong bảng user/profile tùy tiện.

Ví dụ cấu trúc bảng **minh họa**, cần tùy chỉnh theo cơ sở dữ liệu:

```sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE external_identity (
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id),
    PRIMARY KEY (issuer, subject)
);

CREATE INDEX ix_external_identity_user_id ON external_identity(user_id);
```

Các bảng này không tự xác thực OIDC; chỉ ghi mối quan hệ với một user đã xác minh ở lớp giao thức.

### Bước 9. SecurityContext, session và authorized client

Khi OAuth2 login thành công, Spring Security đặt Authentication vào `SecurityContextHolder` của request và lưu context qua `SecurityContextRepository`/cơ chế thành công xác thực được cấu hình. Với ứng dụng web server-side dùng session, request sau có thể lấy lại Authentication qua cookie session.

Đồng thời Spring có thể lưu thông tin **authorized client**, như access token/refresh token, qua `OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService`. Đây là trách nhiệm khác với lưu `SecurityContext`.

| Nơi lưu | Chứa gì? | Dùng khi nào? |
| --- | --- | --- |
| `AuthorizationRequestRepository` | Authorization request đang chờ, `state`, dữ liệu giao thức | Trong thời gian chuyển hướng đi IdP và nhận callback |
| `SecurityContextRepository` | Authentication đã thành công, dùng cho các request của ứng dụng | Kiểm tra người dùng đã login và quyền truy cập |
| `OAuth2AuthorizedClientRepository/Service` | Client registration + OAuth access/refresh token được cấp | Khi ứng dụng cần gọi resource server thay mặt user |
| Local user database | ID nội bộ, mapping issuer/subject, trạng thái và vai trò | Danh tính và chính sách thuộc sở hữu ứng dụng |

Không cần phát hành JWT riêng của ứng dụng chỉ để một server-rendered app biết user đang đăng nhập. Cookie session có thể là đủ. Nếu ứng dụng tự phát hành token nội bộ, đó là **một thiết kế thêm** về ký, audience, thời hạn, rotation, logout/revocation; nó không tự xảy ra chỉ vì `oauth2Login()` đã thành công.

## 5. Các lớp và endpoint chính của Spring Security Servlet

| Thành phần | Vai trò |
| --- | --- |
| `ClientRegistration` | Cấu hình IdP: client ID/secret, scope, authorization URI, token URI, redirect URI, issuer/JWKs |
| `ClientRegistrationRepository` | Tra cứu `ClientRegistration` theo registrationId |
| `OAuth2AuthorizationRequestRedirectFilter` | Bắt đầu login và chuyển hướng trình duyệt tới IdP |
| `OAuth2AuthorizationRequestResolver` | Dựng authorization request, `state` và các tham số liên quan |
| `AuthorizationRequestRepository` | Lưu/đối chiếu request trong lúc chờ callback |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback authorization code |
| `OAuth2LoginAuthenticationProvider` | Xử lý đăng nhập OAuth2 thông thường, không OIDC |
| `OidcAuthorizationCodeAuthenticationProvider` | Xử lý đăng nhập OIDC theo Authorization Code |
| `OAuth2UserService` / `OidcUserService` | Lấy và chuyển đổi thông tin user theo loại provider |
| `OAuth2AuthenticationToken` | Kết quả Authentication trong ứng dụng |
| `SecurityContextHolder` / `SecurityContextRepository` | Giữ/khôi phục authentication theo request/session |
| `OAuth2AuthorizedClientRepository` | Quản lý authorized client dùng khi gọi API bên ngoài |

Các đường mặc định cần nhớ:

```text
/oauth2/authorization/{registrationId}    # bắt đầu đăng nhập
/login/oauth2/code/{registrationId}       # callback mà Spring Security xử lý
/login                                    # trang đăng nhập mặc định khi cần
```

Nếu thay đổi `authorizationEndpoint().baseUri(...)` hay `redirectionEndpoint().baseUri(...)`, phải thay cả link bắt đầu login và redirect URI đã đăng ký ở IdP. Không nên tạo thêm một controller tự đọc `code` để “hoàn thành login” nếu Spring Security đang chịu trách nhiệm xử lý callback.

## 6. Dự án Spring Boot Java 17+ chạy được với IdP OIDC thật

Ví dụ dùng **Spring Boot 3.5.16**, Spring Security Servlet và Google làm OIDC Provider. Đây là một phiên bản cụ thể để tái lập bài thực hành; khi xây hệ thống mới, hãy chọn nhánh Spring Boot còn được hỗ trợ.

**Điều kiện chạy luồng đăng nhập thật:** cần tạo OAuth/OIDC client trong Google Cloud, đặt đúng authorized redirect URI, có client ID/secret. Mã Java compile được khi tải được Maven dependencies. Không thể hoàn thành phiên login thật chỉ với credentials giả.

Cấu trúc:

```text
oidc-code-flow/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/demo/oidc/LoginApplication.java
└── src/test/java/demo/oidc/LoginApplicationTest.java
```

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>oidc-code-flow</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope: openid, profile, email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
server:
  port: 8080
```

Spring Boot/Spring Security có metadata mặc định cho registration `google`. Với một IdP doanh nghiệp, thêm provider config/issuer discovery và dùng registration riêng. Không commit client secret vào repository. Sau khi khởi tạo application chạy sau reverse proxy, bảo đảm `{baseUrl}` được tính đúng theo host và HTTPS public, với cấu hình forwarded headers tin cậy.

Trong Google Cloud, đăng ký redirect URI chính xác:

```text
http://localhost:8080/login/oauth2/code/google
```

Tạo `src/main/java/demo/oidc/LoginApplication.java`:

```java
package demo.oidc;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/error").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().denyAll())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("login", "/oauth2/authorization/google");
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private/me")
    public Map<String, String> currentIdentity(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject());
    }
}
```

Khi login OIDC thành công, `@AuthenticationPrincipal OidcUser` là một cách lấy danh tính đã được Spring Security xây dựng tại request handler. Hai giá trị trả về minh họa khóa liên kết `issuer + subject`. Ứng dụng thực tế thường trả ID local trong endpoint nội bộ thay vì phát tán profile/token thô.

Chạy trên máy phát triển, thiết lập biến môi trường trước (cú pháp ví dụ cho Bash):

```bash
export OIDC_CLIENT_ID="client-id-da-dang-ky"
export OIDC_CLIENT_SECRET="client-secret-tu-secret-manager"
mvn spring-boot:run
```

Mở browser tới:

```text
http://localhost:8080/private/me
```

Kết quả mong đợi:

1. Browser bị chuyển đến trang login nếu chưa xác thực.
2. Sau khi chọn Google, browser đến authorization endpoint với `state` và các tham số OIDC do Spring xử lý.
3. Đăng nhập/consent xong, browser trở lại `/login/oauth2/code/google`.
4. Spring đổi code, xử lý OIDC và tạo session; browser có thể được chuyển lại `/private/me`.
5. Endpoint trả JSON như `{"issuer":"https://accounts.google.com","subject":"<subject-do-IdP-cap>"}`. **Giá trị subject thực tế khác nhau theo tài khoản**; đây chỉ là hình dạng dữ liệu, không phải output cố định để hard-code.

Lưu ý: `/public` trả body đúng là `public` mà không cần login. Các Location header, cookie và response của IdP thay đổi theo môi trường, nên bài thực hành không giả lập một auth code/token cố định.

## 7. Kiểm thử controller và chính sách bằng MockMvc

Để kiểm thử đoạn code Spring mà không cần đăng nhập Google thật, dùng `spring-security-test` với `oidcLogin()`. Cơ chế này đặt một OIDC principal mô phỏng vào security context của request test; nó **không kiểm chứng token chữ ký**, cũng không gửi browser qua IdP.

Tạo `src/test/java/demo/oidc/LoginApplicationTest.java`:

```java
package demo.oidc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "spring.security.oauth2.client.registration.google.client-id=test-client",
    "spring.security.oauth2.client.registration.google.client-secret=test-secret"
})
@AutoConfigureMockMvc
class LoginApplicationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void authenticatedOidcUserProvidesIssuerAndSubject() throws Exception {
        mvc.perform(get("/private/me")
            .with(oidcLogin().idToken(token -> token
                .issuer("https://issuer.example")
                .subject("subject-123"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.issuer").value("https://issuer.example"))
            .andExpect(jsonPath("$.subject").value("subject-123"));
    }

    @Test
    void anonymousBrowserIsPromptedToSignIn() throws Exception {
        mvc.perform(get("/private/me").accept("text/html"))
            .andExpect(status().is3xxRedirection());
    }
}
```

Chạy từ thư mục dự án:

```bash
mvn test
```

Kết quả mong đợi: ba test pass. Với Spring Boot 3.5.16, code dùng `@AutoConfigureMockMvc` trong thư viện test Spring Boot. Nếu test endpoint trả `issuer`/`subject` đúng, điều đó chứng minh cách controller đọc OIDC principal và security rules cơ bản; **chưa phải kiểm thử đầy đủ Authorization Code flow**.

Kiểm thử tích hợp với một provider thật cần kiểm tra thêm: redirect URI, state validation, token exchange, xác minh ID Token/nonce, hành vi khi từ chối consent, session/logout, và khả năng hoạt động qua ingress/proxy. Không dùng `oidcLogin()` giả lập để kết luận chữ ký JWT hoặc token endpoint đã được cấu hình an toàn.

## 8. Nơi ứng dụng ánh xạ local account và authorities

Có hai điểm mở rộng phổ biến:

**`OidcUserService`:** nhận `OidcUserRequest` với ID Token và access token, nạp thông tin user rồi trả `OidcUser`. Ứng dụng có thể bọc một `OidcUserService` mặc định để đọc `iss`/`sub`, tìm hoặc cấp phát tài khoản local, kiểm tra trạng thái và trả principal/authorities đã chuẩn hóa. Nếu thực hiện cấp phát ở bước này, cần giao dịch database, ràng buộc unique và xử lý race.

**`GrantedAuthoritiesMapper`:** chuyển authorities nhận từ provider/OIDC user thành authorities mà ứng dụng sử dụng. Ví dụ `OIDC_USER` và `SCOPE_email` không tự trở thành `ROLE_EDITOR`. Mapper có thể tra kho quyền nội bộ dựa trên issuer/subject đã xác thực.

Mẫu cấu hình **rút gọn để chỉ ra hook**, không phải file Java độc lập:

```java
@Bean
SecurityFilterChain appSecurity(
        HttpSecurity http,
        GrantedAuthoritiesMapper roles) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .oauth2Login(oidc -> oidc
            .userInfoEndpoint(userInfo -> userInfo
                .userAuthoritiesMapper(roles)))
        .build();
}
```

Hook này có thể thay cho bean `securityFilterChain` ở ví dụ trước khi ứng dụng cung cấp `GrantedAuthoritiesMapper`. Không khai báo hai filter chain giống nhau với matcher trùng nhau. Nếu cần gọi API/database để lấy role trong lúc xử lý authentication, một `OAuth2UserService`/`OidcUserService` tùy biến thường phù hợp hơn một mapper làm nhiệm vụ phức tạp.

**Thứ tự logic để tạo identity tại ứng dụng:**

```text
ID Token đã xác minh
    |
    +--> issuer + subject  ---> local identity mapping (unique)
    |                              |
    |                              +--> localUserId
    |                              +--> enabled/locked status
    |                              +--> tenant membership
    |                              +--> app roles / permissions
    |
    +--> OidcUser + mapped authorities
                   |
                   v
           OAuth2AuthenticationToken
                   |
                   v
              SecurityContext
                   |
                   v
        Authorization & Controller
```

Tại sao không dùng `email` làm tên định danh chính? Email có thể đổi, chưa được xác minh hoặc thuộc người khác sau khi tái cấp phát; `iss + sub` là khóa danh tính OIDC được thiết kế cho RP. Với nhiều tenant/realm, cần đúng issuer, không lấy mỗi tên miền tùy ý để ghép user.

## 9. `state`, `nonce`, PKCE và các kiểm soát bảo mật

| Cơ chế | Bảo vệ điều gì? | Nơi áp dụng |
| --- | --- | --- |
| `state` | Liên kết authorization response với request mà client đã khởi tạo; ngăn login CSRF/mix-up theo mô hình phù hợp | Request khởi tạo và callback; lưu/đối chiếu state |
| `nonce` | Ràng buộc ID Token với yêu cầu OIDC, chống replay ID Token | OIDC authorization request và ID Token validation |
| PKCE `S256` | Khi code bị chặn/lộ, attacker không có code verifier tương ứng để đổi token | Authorization request chứa challenge; token request mang verifier |
| Client authentication | Xác nhận client hợp lệ tại token endpoint, theo loại client đã đăng ký | Server-side token exchange |
| Exact redirect URI matching | Hạn chế đưa authorization code đến endpoint không được phép | Đăng ký IdP và callback |
| `iss`/`aud`/signature/expiry validation | Không nhận ID Token sai issuer/client hoặc hết hạn/bị sửa | OIDC token verification |
| HTTPS + cookie security | Chống lộ code, session, credentials trên mạng | Browser ↔ app ↔ IdP |
| User/account authorization | Người dùng đã login chỉ làm hành động được phép | Application security policy |

**Những điểm quan trọng khi triển khai:**

- Dùng **Authorization Code + PKCE** theo yêu cầu của loại client và thông lệ hiện đại; không dùng Implicit flow cho thiết kế mới.
- Không gửi client secret, refresh token, access token hoặc ID Token vào browser JavaScript nếu lựa chọn kiến trúc server-side session.
- Không tự dùng query parameter `state`, `code`, `id_token` làm chứng cứ user đã login mà bỏ bước validation/exchange.
- Chống open redirect: đừng đưa đích sau đăng nhập lấy từ query chưa xác minh vào `Location`.
- Đối với nhiều IdP, chống nhầm issuer và client registration; callback phải gắn đúng authorization request/provider.
- Chính sách cookie session phù hợp: HTTPS, `Secure`, `HttpOnly`, `SameSite` theo luồng redirect thực tế; kiểm soát session fixation, logout và CSRF.
- Không tắt CSRF toàn ứng dụng chỉ vì đang dùng OAuth2 Login. Ứng dụng có session cookie và action thay đổi trạng thái vẫn cần cơ chế chống CSRF phù hợp.
- Với app sau reverse proxy, xử lý `Forwarded`/`X-Forwarded-*` **chỉ khi từ proxy đáng tin cậy**. Base URL sai thường làm redirect URI mismatch và có thể dẫn tới lỗi nghiêm trọng nếu tin host header tùy ý.
- Không log authorization code, client secret, refresh token, cookie session hoặc toàn bộ ID Token. Nên giám sát login failures theo loại lỗi mà không làm lộ dữ liệu nhạy cảm.

## 10. Các lỗi hay gặp và cách phân biệt nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `redirect_uri_mismatch` ở IdP | Callback trong `ClientRegistration` khác địa chỉ đã đăng ký; sai HTTP/HTTPS, host, port, path | Kiểm tra redirect URI **chính xác**, và public base URL qua proxy |
| Callback báo thiếu/mất `state` | Session chứa authorization request không còn; cookie sai; nhiều node không chia sẻ session; state khác | Kiểm tra `AuthorizationRequestRepository`, session/cookie, routing |
| Login về callback nhưng không có ID Token | Provider chỉ hỗ trợ OAuth2 thông thường; thiếu scope `openid` | Nếu cần OIDC, cấu hình provider và scope `openid` chính xác |
| `invalid_client` ở token endpoint | Sai client ID/secret, cơ chế client authentication hoặc client registration | Xác minh credentials và phương thức token auth |
| `invalid_grant` khi đổi code | Code hết hạn/đã dùng, mismatch redirect URI, PKCE verifier sai | Chỉ exchange một lần, kiểm tra thời hạn, URI/PKCE |
| ID Token không hợp lệ | Sai issuer, audience, nonce, thời hạn hoặc chữ ký/khóa | Kiểm tra metadata/clock skew/client registration, không tắt validation |
| Handler có `OAuth2AuthenticationToken` nhưng user không vào trang admin | Chưa ánh xạ `ROLE_ADMIN` hay local user bị hạn chế | Phân biệt authentication với authorization; kiểm tra authorities |
| User có email đúng nhưng link nhầm account | Dùng email chưa xác minh/không ổn định thay issuer+sub | Thiết kế bảng identity link và kiểm tra quyền sở hữu |
| Request sau callback lại bị coi anonymous | Session không được giữ/được lưu sai, cookie không gửi lại, session policy stateless | Kiểm tra `SecurityContextRepository`, cookie, node/session store |
| Login chạy tốt nhưng API trả 401 với access token | OAuth2 Login session khác Resource Server bearer JWT; token không có audience phù hợp | Cấu hình `oauth2ResourceServer()` ở API nếu cần và gửi đúng token |
| Đăng nhập lại với user khác nhưng vẫn thấy quyền cũ | Session cũ/chính sách refresh quyền và logout chưa rõ | Kiểm tra session invalidation, account link, authority caching |

Trình tự debug hiệu quả: kiểm tra redirect có dùng đúng client registration → callback có giữ `state` và cookie không → token exchange thành công không → ID Token/user claims hợp lệ không → principal trong `SecurityContext` là ai → app roles và local account link có đúng không. Không nhảy thẳng đến chỉnh `hasRole(...)` khi lỗi thực tế nằm ở token exchange.

## 11. Các câu hỏi tự kiểm tra

1. **Vì sao callback chứa `code` vẫn chưa chứng minh user là ai?** Code mới chỉ là grant được cấp cho một client/flow; ứng dụng còn phải đối chiếu request/state, đổi code tại token endpoint và xác minh kết quả xác thực.
2. **Phân biệt `id_token` và `access_token`?** ID Token chứng minh kết quả OIDC với client sau khi được xác minh; access token dành để gọi resource server tương ứng.
3. **Ai tạo `Authentication` của Spring?** Các thành phần OAuth2/OIDC login của Spring Security sau khi nhận token, xác minh và nạp principal; controller chỉ đọc kết quả.
4. **Spring Security có tự tạo account trong bảng `app_user` không?** Không. Đó là bước sản phẩm tùy chọn do ứng dụng xây dựng.
5. **Vì sao dùng (`iss`, `sub`) thay `email` để link user?** Subject ổn định trong phạm vi issuer; email có thể thay đổi, không được xác minh hoặc tái sử dụng.
6. **`ROLE_ADMIN` có tự có từ scope `email` không?** Không. OAuth scopes và application roles là hai nguồn authority khác nhau, cần mapping rõ.
7. **Sau callback, làm sao request tiếp theo còn đăng nhập?** Một cơ chế `SecurityContextRepository`/session của ứng dụng khôi phục Authentication từ session cookie hoặc cơ chế trạng thái đã cấu hình.
8. **Bài test dùng `oidcLogin()` đã kiểm tra chữ ký ID Token chưa?** Chưa. Nó đưa một principal giả lập vào request để kiểm tra xử lý controller/authorization.
9. **Nếu chỉ bảo vệ API bằng bearer JWT thì có cần `oauth2Login()`?** Không nhất thiết. API resource server thường dùng `oauth2ResourceServer()` để xác minh access token được gửi theo từng request.

## 12. Tài liệu chính thức

- Spring Security OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security OAuth 2.0 Login – core configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security OAuth 2.0 Login – advanced configuration và hooks: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security OAuth 2.0 Client – Authorization Code: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- Spring Security Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- OIDC Core 1.0 specification: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- PKCE (RFC 7636): https://www.rfc-editor.org/rfc/rfc7636
