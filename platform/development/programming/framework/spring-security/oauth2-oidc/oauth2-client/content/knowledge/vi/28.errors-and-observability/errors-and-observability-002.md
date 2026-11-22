# 28.2. OAuth2AuthenticationException, OAuth2AuthorizationException và OAuth2Error

## 1. Bài toán: cùng là lỗi OAuth2 nhưng phải xử lý ở những tầng khác nhau

Một ứng dụng Spring Boot dùng **Spring Security OAuth 2.0/OIDC Client** để đăng nhập qua OpenID Provider (OP). Sau đăng nhập, backend dùng access token đã cấp để gọi Reports API. Một ngày, đội vận hành gặp ba tình huống:

1. User bấm **Deny** tại màn hình consent. Browser quay về callback với <code>error=access_denied</code>. Spring Security xử lý lỗi đăng nhập.
2. User đã đăng nhập hợp lệ, nhưng access token dùng gọi Reports API sắp hết hạn. Backend gọi refresh token; Token Endpoint trả <code>invalid_grant</code>.
3. Backend có access token còn hạn nhưng Resource Server trả HTTP 403 với Bearer <code>insufficient_scope</code>.

Nếu gom cả ba thành “OAuth2 lỗi → xóa session → redirect login”, ứng dụng có thể tạo login loop, đăng xuất nhầm người dùng, làm mất token mới của một node khác hoặc che giấu lỗi cấu hình thật sự.

Để xử lý chính xác, cần phân biệt ba kiểu trong Spring Security:

- **<code>OAuth2Error</code>:** object mang thông tin một lỗi theo mô hình OAuth2.
- **<code>OAuth2AuthenticationException</code>:** exception gắn với quá trình authentication, có chứa <code>OAuth2Error</code>.
- **<code>OAuth2AuthorizationException</code>:** exception gắn với thao tác OAuth2 authorization hoặc authorized-client/token processing, cũng chứa <code>OAuth2Error</code>.

Một mã lỗi giống nhau có thể xuất hiện ở nhiều giai đoạn. **Tên exception, OAuth2 error code và HTTP status là ba chiều thông tin khác nhau.**

> **Nguyên tắc xuyên suốt:** Muốn phản ứng đúng, phải biết lỗi xảy ra ở **Authorization Endpoint callback**, **Token Endpoint**, **UserInfo Endpoint**, **authorized-client manager** hay **Resource Server**; sau đó mới nhìn vào <code>getError().getErrorCode()</code>.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Đọc <code>error</code>, <code>error_description</code>, <code>error_uri</code> trong OAuth2 protocol và ánh xạ sang <code>OAuth2Error</code>.
2. Phân biệt <code>OAuth2AuthenticationException</code> và <code>OAuth2AuthorizationException</code> theo điểm phát sinh và failure handling.
3. Hiểu vì sao <code>invalid_grant</code> trong authorization-code login khác <code>invalid_grant</code> khi refresh token.
4. Cấu hình Spring Security OAuth2 Login failure handler cho **Servlet** và **Reactive WebFlux**.
5. Xử lý <code>OAuth2AuthorizationException</code> khi gọi <code>OAuth2AuthorizedClientManager</code> hoặc reactive counterpart.
6. Không đồng nhất HTTP 401/403 của Resource Server với exception ở Token Endpoint.
7. Thiết kế error classification, HTTP mapping, retry, reauthorization và token cleanup theo policy.
8. Ghi logs, metrics và traces an toàn, không để lộ credential, mã authorization code hoặc thông tin cá nhân.
9. Xây unit tests và integration scenarios cho callback, token requests, refresh và downstream API.

## 3. Bản đồ xử lý lỗi

~~~mermaid
flowchart TD
    B["Browser"] --> INIT["OAuth2/OIDC Login"]
    INIT --> OP["OpenID Provider"]
    OP -->|"Callback error=access_denied"| AUTH["Authentication failure pipeline"]
    OP -->|"Authorization code"| TOKEN["Token Endpoint"]
    TOKEN -->|"invalid_client / invalid_grant"| GRANT["Token/authorization processing"]
    GRANT -->|"Khi lỗi thuộc login"| AUTH
    AUTH --> AE["OAuth2AuthenticationException hoặc AuthenticationException khác"]
    GRANT --> AZ["OAuth2AuthorizationException hoặc error được chuyển đổi"]
    AE --> ERR["OAuth2Error"]
    AZ --> ERR
    B --> APP["Ứng dụng đã authenticated"]
    APP --> M["OAuth2AuthorizedClientManager"]
    M -->|"Refresh/client credentials"| TOKEN
    M -->|"Authorize failure"| AZ
    APP --> API["Resource Server"]
    API -->|"HTTP 401 / 403"| H["HTTP client error handling"]
~~~

Sơ đồ mang tính **khái niệm**. Spring Security có thể wrap, translate hoặc handle exception trong authentication provider/filter, nên không nên khẳng định mọi OAuth2 Login error đều được ném thẳng dưới cùng một class ở tất cả các versions.

### 3.1. Bảng phân biệt

| Thành phần | Bản chất | Nơi thường gặp | Thông tin chính |
|---|---|---|---|
| <code>OAuth2Error</code> | Value object | Token errors, authorization errors, validation errors | Mã lỗi, mô tả, URI |
| <code>OAuth2AuthenticationException</code> | <code>AuthenticationException</code> | OAuth2/OIDC Login, authentication providers | <code>getError()</code>, cause |
| <code>OAuth2AuthorizationException</code> | Exception cho OAuth2 authorization | Token request, refresh, authorized-client operation | <code>getError()</code>, cause |
| HTTP client exception | Lỗi giao tiếp HTTP | WebClient/RestClient gọi Resource Server | HTTP status, headers, response |
| <code>AccessDeniedException</code> | Authorization ở Spring Security | Role, tenant, method security, route security | Quyền truy cập bị từ chối |

**Không đồng nhất:** <code>OAuth2AuthenticationException</code> = HTTP 401, <code>OAuth2AuthorizationException</code> = HTTP 403. Những tên này chỉ bối cảnh framework, không phải quy tắc chuyển đổi HTTP.

## 4. OAuth2Error: đối tượng dữ liệu, chưa phải một exception

Class:

~~~java
org.springframework.security.oauth2.core.OAuth2Error
~~~

Một lỗi giao thức OAuth2 thường có ba trường:

~~~json
{
  "error": "invalid_grant",
  "error_description": "The authorization code is expired",
  "error_uri": "https://auth.example.org/docs/errors/invalid-grant"
}
~~~

Trong Spring Security:

| OAuth2 field | Java method | Vai trò |
|---|---|---|
| <code>error</code> | <code>getErrorCode()</code> | Mã lỗi máy có thể phân loại |
| <code>error_description</code> | <code>getDescription()</code> | Mô tả bổ sung, có thể null |
| <code>error_uri</code> | <code>getUri()</code> | URI tài liệu, có thể null |

### 4.1. Tạo OAuth2Error

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;

OAuth2Error error = new OAuth2Error(
    "invalid_grant",
    "Authorization code is no longer valid",
    "https://auth.example.org/docs/errors/invalid-grant");

String code = error.getErrorCode();
String description = error.getDescription();
String uri = error.getUri();
~~~

Có constructor chỉ nhận mã:

~~~java
OAuth2Error simple = new OAuth2Error("invalid_request");
~~~

### 4.2. OAuth2Error không phải HTTP response

Object <code>OAuth2Error</code> không tự chứa HTTP status của response gốc hoặc status mà Portal nên trả cho browser.

Ví dụ <code>invalid_grant</code> tại Token Endpoint thường ở một JSON response HTTP 400, nhưng khi Client phát hiện cùng mã trong một browser login, failure handler có thể redirect về trang đăng nhập. Trong một BFF request đã authenticated, refresh thất bại có thể cần response riêng hoặc reauthorization.

Không suy luận:

~~~text
error.getErrorCode() == "invalid_grant"
⇒ Portal luôn phải trả HTTP 401
~~~

### 4.3. OAuth2ErrorCodes là hằng số, không phải lỗi cụ thể

Spring Security có <code>OAuth2ErrorCodes</code> chứa một số mã chuẩn:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;

OAuth2Error error = new OAuth2Error(
    OAuth2ErrorCodes.INVALID_GRANT);
~~~

<code>OAuth2ErrorCodes.INVALID_GRANT</code> là chuỗi <code>"invalid_grant"</code>; <code>OAuth2Error</code> mới là object lưu thông tin của lỗi cụ thể.

Provider-specific error codes không nhất thiết có constants trong <code>OAuth2ErrorCodes</code>; không tự ép mọi mã lạ thành <code>invalid_grant</code>.

### 4.4. Không tin hoàn toàn error_description

<code>error_description</code> có thể xuất phát từ OP, gateway hoặc một integration bên ngoài. Nó có thể:

- Chứa chi tiết cấu hình nội bộ, username hoặc dữ liệu do user gửi.
- Thay đổi wording khi nâng cấp provider.
- Chứa ký tự gây log injection hoặc HTML không an toàn nếu render trực tiếp.
- Quá dài, khó dùng làm metric label.

Không trả thẳng:

~~~java
response.getWriter().write(error.getDescription());
~~~

nếu chưa có kiểm soát encoding, validation và user-facing policy.

### 4.5. error_uri không phải đích redirect đáng tin

Không viết:

~~~java
response.sendRedirect(error.getUri());
~~~

với URI chưa được kiểm tra. Một <code>error_uri</code> là metadata tài liệu, không phải redirect URI đã được Portal tin cậy. Nếu cần link hướng dẫn, map error category sang help page nội bộ hoặc URI trong allowlist do backend kiểm soát.

## 5. OAuth2AuthenticationException: lỗi trong quá trình xác thực

Class:

~~~java
org.springframework.security.oauth2.core.OAuth2AuthenticationException
~~~

Đây là một loại <code>AuthenticationException</code> của Spring Security. Nó mang một <code>OAuth2Error</code>, cho phép framework xử lý lỗi trong **authentication pipeline**.

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;

OAuth2Error error = new OAuth2Error(
    "invalid_id_token",
    "Unexpected ID Token issuer",
    null);

throw new OAuth2AuthenticationException(error);
~~~

Đây là ví dụ cho **custom validation component**; không phải lời khuyên tự thay thế OIDC signature/issuer/nonce verification mặc định.

### 5.1. OAuth2 Login thất bại ở những chỗ nào?

Trong Servlet OAuth2 Login, các thành phần có thể gồm:

~~~text
OAuth2AuthorizationRequestRedirectFilter
OAuth2LoginAuthenticationFilter
OAuth2LoginAuthenticationProvider
OidcAuthorizationCodeAuthenticationProvider
OAuth2UserService / OidcUserService
AuthenticationFailureHandler
~~~

Các lỗi điển hình:

1. OP trả <code>access_denied</code> khi user từ chối consent.
2. Authorization response không correlate với <code>state</code> và authorization request gốc.
3. Token Endpoint từ chối code hoặc Client authentication.
4. ID Token sai issuer, audience, chữ ký, expiry hoặc nonce.
5. UserInfo endpoint trả response không chấp nhận được.
6. Mapping nội bộ từ chối tài khoản inactive/disabled sau khi identity đã được xác minh.

Không phải mọi lỗi trên đều bảo đảm có cùng exception class hoặc error code trong mọi Spring Security version. Đặc biệt, lỗi kỹ thuật I/O, session storage hoặc custom mapping có thể được wrap/translated.

### 5.2. Browser consent bị từ chối

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant OP as OpenID Provider
    participant RP as Spring Security Client
    participant FH as AuthenticationFailureHandler
    B->>RP: GET /oauth2/authorization/company
    RP-->>B: Redirect OP, state=S1
    B->>OP: Authorization request state=S1
    U->>OP: Deny consent
    OP-->>B: Redirect error=access_denied&state=S1
    B->>RP: GET /login/oauth2/code/company?error=access_denied&state=S1
    RP->>RP: Validate request correlation, process OAuth2 error
    RP->>FH: Authentication failure
    FH-->>B: Redirect /login?error=oauth2
~~~

User từ chối consent là outcome có thể xảy ra hợp lệ, không nhất thiết là hệ thống bị xâm nhập hay OP outage.

### 5.3. Đọc OAuth2Error qua exception

~~~java
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

void classify(AuthenticationException failure) {
    if (failure instanceof OAuth2AuthenticationException oauthFailure) {
        OAuth2Error error = oauthFailure.getError();
        String code = error.getErrorCode();
        // Chuyển code thành category và thông báo an toàn.
    } else {
        // Có thể là authentication exception khác.
    }
}
~~~

Không ép cast mọi <code>AuthenticationException</code> sang <code>OAuth2AuthenticationException</code>, vì login cũng có thể thất bại bởi loại exception khác.

### 5.4. Authentication failure không cho phép bỏ qua trust validation

Không viết:

~~~text
ID Token signature/issuer validation failed
    → bỏ qua
    → lấy email trong JWT chưa được xác minh
    → tạo authenticated principal
~~~

Một OIDC Client phải từ chối authentication khi validation thiết yếu thất bại. Availability không thể cải thiện bằng cách tự đánh dấu user đã xác thực từ claims chưa tin cậy.

## 6. OAuth2AuthorizationException: lỗi authorization/authorized-client

Class:

~~~java
org.springframework.security.oauth2.core.OAuth2AuthorizationException
~~~

Exception này cũng chứa <code>OAuth2Error</code>, nhưng thường được sử dụng khi **OAuth2 authorization hoặc thao tác token** không hoàn thành được.

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;

OAuth2Error error = new OAuth2Error(
    OAuth2ErrorCodes.INVALID_GRANT,
    "Refresh token rejected",
    null);

throw new OAuth2AuthorizationException(error);
~~~

### 6.1. Vai trò của OAuth2AuthorizedClient

<code>OAuth2AuthorizedClient</code> biểu diễn một ClientRegistration đã được cấp access token cho principal:

~~~text
clientRegistrationId
principalName
accessToken
refreshToken (nếu có)
~~~

<code>OAuth2AuthorizedClientManager</code> có thể load token đang có, quyết định refresh/xin token khi cần và lưu token mới. Trong quá trình đó, lỗi Token Endpoint hoặc authorization provider có thể được biểu diễn bằng <code>OAuth2AuthorizationException</code> hoặc được xử lý qua authorized-client failure infrastructure.

### 6.2. Một flow refresh token lỗi

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser
    participant APP as Portal
    participant M as AuthorizedClientManager
    participant DB as Authorized Client Store
    participant OP as Token Endpoint
    participant API as Reports API
    U->>APP: GET /reports, authenticated session
    APP->>M: authorize(company, user-123)
    M->>DB: Load authorized client
    DB-->>M: Access expired, refresh token R0
    M->>OP: grant_type=refresh_token&refresh_token=R0
    OP-->>M: 400 invalid_grant
    M-->>APP: OAuth2AuthorizationException / failure handling
    APP-->>U: Response theo policy, không lộ token
    Note over API: API có thể chưa được gọi
~~~

**Portal HTTP session và OAuth2 authorized client là hai trạng thái khác nhau.** Một refresh token bị từ chối không tự chứng minh user chưa authenticated trong Portal; tùy sản phẩm, có thể cần reauthorize registration cụ thể hoặc kết thúc session.

### 6.3. AuthorizationException không phải business access denied

Nếu user thiếu role <code>ROLE_BILLING_ADMIN</code> để gọi business API, đó là vấn đề permission/authorization của ứng dụng hoặc Resource Server. Đừng tạo:

~~~java
throw new OAuth2AuthorizationException(
    new OAuth2Error("invalid_grant"));
~~~

để biểu diễn mọi trường hợp 403. <code>invalid_grant</code> có nghĩa một OAuth2 grant không được chấp nhận, không phải user thiếu mọi quyền nghiệp vụ.

### 6.4. So sánh khi cùng error code

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;

OAuth2Error error = new OAuth2Error("invalid_grant");

var loginFailure = new OAuth2AuthenticationException(error);
var tokenFailure = new OAuth2AuthorizationException(error);

System.out.println(loginFailure.getError().getErrorCode());
System.out.println(tokenFailure.getError().getErrorCode());
~~~

Cả hai đều trả <code>invalid_grant</code>. Nhưng **cách ứng dụng phản ứng phải dựa trên operation và stage**, không dựa duy nhất vào code.

## 7. Những nguồn lỗi theo OAuth2/OIDC protocol

### 7.1. Authorization Endpoint callback

Browser có thể nhận redirect:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.org/login/oauth2/code/company?error=access_denied&state=STATE_VALUE
~~~

Lỗi nằm trên **authorization response qua browser**. Client phải correlate state/request và không nhận một callback tự dựng từ website attacker là hợp lệ.

### 7.2. Token Endpoint

Client gửi:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=SECRET_VALUE
~~~

Server trả:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant",
  "error_description": "Refresh token expired or revoked"
}
~~~

Trong code, lỗi có thể được token response client chuyển thành <code>OAuth2AuthorizationException</code> và truyền lên authorized-client manager.

### 7.3. UserInfo Endpoint

OIDC Client có thể gọi UserInfo endpoint bằng access token. HTTP 401/403 từ UserInfo khác với browser callback state mismatch. Cần xác minh token audience/scope, UserInfo contract và claims policy.

### 7.4. Resource Server

Backend gọi:

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.org
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Resource Server trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="reports.write"
~~~

Đây là **HTTP response downstream**, không nhất thiết ném trực tiếp <code>OAuth2AuthorizationException</code>. <code>WebClient</code>/<code>RestClient</code> có thể ném HTTP response exception riêng.

### 7.5. Internal application policy

OIDC Login được xác minh nhưng user thuộc account nội bộ bị disabled:

~~~text
OP authentication succeeds
    ↓
Internal user profile says DISABLED
    ↓
Portal denies application login
~~~

Đây là policy của **Portal**, không phải lý do tự gán <code>invalid_grant</code> cho OP. Nếu ứng dụng tạo custom <code>OAuth2AuthenticationException</code>, dùng error code nội bộ tách biệt, không làm giả lỗi do Token Endpoint trả.

## 8. Mã lỗi thường gặp và bối cảnh của chúng

| Mã lỗi | Nguồn thường gặp | Ý nghĩa | Hướng xử lý đầu tiên |
|---|---|---|---|
| <code>invalid_request</code> | Authorization/Token Endpoint | Request thiếu/sai parameter | Kiểm tra converter, scope, URI và form encoding |
| <code>unauthorized_client</code> | Authorization/Token Endpoint | Client không được dùng grant/flow | Kiểm tra ClientRegistration policy |
| <code>access_denied</code> | Authorization Endpoint | User/OP từ chối authorization | Quay về login, không retry mù |
| <code>unsupported_response_type</code> | Authorization Endpoint | Response type không được hỗ trợ | Sửa registration/flow |
| <code>invalid_scope</code> | Authorization/Token Endpoint | Scope sai hoặc không được phép | Kiểm tra consent và provider policy |
| <code>server_error</code> | Authorization Endpoint, một số extension | OP gặp lỗi máy chủ | Đánh giá upstream availability |
| <code>temporarily_unavailable</code> | Authorization Endpoint | OP tạm thời unavailable | Bounded retry/backoff theo flow |
| <code>invalid_client</code> | Token Endpoint | Client authentication thất bại | Secret/key/JWT client assertion/mTLS |
| <code>invalid_grant</code> | Token Endpoint | Code/refresh grant không hợp lệ | Expiry, reuse, PKCE, revocation, race |
| <code>unsupported_grant_type</code> | Token Endpoint | Grant type không được hỗ trợ | Provider capability và registration |
| <code>invalid_token</code> | Resource Server Bearer challenge | Access token không chấp nhận | Issuer/audience/expiry/revocation |
| <code>insufficient_scope</code> | Resource Server Bearer challenge | Scope thiếu | Scope/consent/Resource Server policy |
| <code>login_required</code> | OIDC Authorization Endpoint | Không thể silent login | Chuyển interactive flow khi phù hợp |
| <code>interaction_required</code> | OIDC Authorization Endpoint | Cần UI interaction | Không retry prompt=none liên tục |
| <code>consent_required</code> | OIDC Authorization Endpoint | Cần consent | Cho user tương tác nếu đúng policy |

Các mã này đến từ nhiều RFC/profiles. **Không phải tất cả đều hợp lệ trong JSON của Token Endpoint**, và không có ánh xạ trực tiếp một-một sang HTTP status của Portal.

### 8.1. invalid_client

Nguyên nhân:

- Client secret đã rotate nhưng một số node còn secret cũ.
- Client ID sai hoặc bị vô hiệu hóa.
- OP yêu cầu <code>private_key_jwt</code>, Client lại gửi <code>client_secret_basic</code>.
- JWT client assertion sai <code>iss</code>/<code>sub</code>/<code>aud</code>, expiry, key hoặc signature.
- mTLS certificate sai hoặc đã hết hạn.

Đây thường là vấn đề **Client authentication/cấu hình hạ tầng**, không nhất thiết user nhập lại mật khẩu sẽ sửa được.

### 8.2. invalid_grant trong authorization code

Có thể do:

- Code hết hạn hoặc dùng lại.
- Callback/redirect URI không khớp.
- <code>code_verifier</code> không khớp PKCE.
- Code được phát cho ClientRegistration khác.
- Grant bị OP từ chối theo policy.

Không bỏ kiểm tra <code>state</code> hoặc PKCE chỉ để login chạy khi gặp <code>invalid_grant</code>.

### 8.3. invalid_grant trong refresh token

Có thể do:

- Refresh token hết hạn hoặc đã bị revoke.
- OP bật rotation và R0 đã được request khác dùng.
- OP phát hiện token reuse và thu hồi token family.
- Refresh token gắn với Client/issuer khác.
- Refresh result không được lưu đúng, dẫn tới tái sử dụng R0.

Với nhiều replicas, **không mặc định invalid_grant là user chủ động logout**.

### 8.4. insufficient_scope

Một JWT access token có chữ ký và expiry hợp lệ vẫn có thể thiếu scope <code>reports.write</code>. Resource Server trả 403; refresh lại cùng scope thường không nâng quyền. Cần kiểm tra grant consent, Resource Server audience, role/tenant ownership.

## 9. Servlet OAuth2 Login: AuthenticationFailureHandler

Trong Servlet stack, <code>oauth2Login()</code> có thể gắn <code>AuthenticationFailureHandler</code> để xử lý lỗi trong login filter.

### 9.1. Dependencies và OIDC registration

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

### 9.2. Failure handler trả thông báo an toàn

~~~java
package example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

public final class SafeLoginFailureHandler
        implements AuthenticationFailureHandler {

    private static final Logger log =
        LoggerFactory.getLogger(SafeLoginFailureHandler.class);

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException failure) throws IOException {

        String category = "authentication_failed";

        if (failure instanceof OAuth2AuthenticationException oauth2Failure) {
            String code = oauth2Failure.getError().getErrorCode();
            category = "access_denied".equals(code)
                ? "user_denied" : "oauth2_failure";
        }

        // Chỉ ghi category có giới hạn, không log raw code/state/token.
        log.warn("oauth2_login_failed category={}", category);

        // Fixed internal redirect; không dùng error_uri hay nextUrl tùy ý.
        response.sendRedirect(
            request.getContextPath() + "/login?error=oauth2");
    }
}
~~~

Ở production, có thể bổ sung correlation ID, provider alias và metric tags, nhưng tránh raw error description hoặc URL query chứa <code>code</code>, <code>state</code>.

### 9.3. Gắn vào SecurityFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2LoginSecurityConfig {

    @Bean
    SafeLoginFailureHandler safeLoginFailureHandler() {
        return new SafeLoginFailureHandler();
    }

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            SafeLoginFailureHandler failureHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .failureHandler(failureHandler))
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Trang <code>/login?error=oauth2</code> nên hiển thị thông báo đã được biên tập, ví dụ “Đăng nhập chưa hoàn tất. Hãy thử lại hoặc liên hệ hỗ trợ.”

### 9.4. Failure handler không quản lý toàn bộ exceptions

<code>oauth2Login().failureHandler(...)</code> hoạt động trong **login authentication pipeline**. Nó không tự bắt:

- Một service gọi <code>OAuth2AuthorizedClientManager</code> và refresh thất bại sau login.
- HTTP 403 khi <code>WebClient</code> gọi Reports API.
- Lỗi background job.
- Lỗi trong arbitrary controller ngoài authentication filter.

Các điểm đó cần error handling riêng. <code>@ControllerAdvice</code> cũng **không thay thế** login failure handler vì OAuth2 Login callback thường được xử lý trong Spring Security filters trước controller.

## 10. Servlet: xử lý OAuth2AuthorizationException trong manager

Một service trong Portal có thể:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("company")
        .principal(authentication)
        .build();

try {
    OAuth2AuthorizedClient client = manager.authorize(request);

    if (client == null) {
        throw new IllegalStateException("No authorized client available");
    }

    // Dùng access token của đúng ClientRegistration/principal.
} catch (OAuth2AuthorizationException ex) {
    String code = ex.getError().getErrorCode();
    // Phân loại code + operation + registration, sau đó recovery.
}
~~~

Đây là **đoạn code rút gọn** giả định method đã có <code>manager</code> và <code>authentication</code>. Với <code>DefaultOAuth2AuthorizedClientManager</code> trong Servlet, request/response context của web repository có thể cần được cung cấp hoặc lấy từ integration; service manager cho background job lại dùng storage khác.

### 10.1. Kết quả null không phải OAuth2Error

<code>OAuth2AuthorizedClientManager.authorize(...)</code> có thể trả <code>null</code> khi không authorize được theo provider/context phù hợp. Đó không tự động là <code>OAuth2AuthorizationException</code> hoặc <code>OAuth2Error("invalid_grant")</code>.

### 10.2. Không retry vô hạn

Sai:

~~~java
while (true) {
    try {
        return manager.authorize(request);
    } catch (OAuth2AuthorizationException ignored) {
        // Gửi lại cùng grant/refresh token vô hạn.
    }
}
~~~

<code>invalid_client</code> cần sửa credential/config; <code>invalid_grant</code> có thể do token đã bị sử dụng lại; outage có thể cần bounded backoff, không phải vòng lặp vô tận.

### 10.3. Không trả HTTP 401 cho mọi lỗi token

User có Portal session hợp lệ nhưng Reports API token refresh thất bại. Có thể cần reauthorization cho registration <code>company</code>, hoặc báo chức năng báo cáo tạm thời unavailable. Không nhất thiết vô hiệu hóa toàn bộ Portal session.

Policy phụ thuộc yêu cầu bảo mật: nếu token bị revoke do tài khoản user disabled, Portal có thể cần hủy local session theo chính sách. Nhưng đó là **quyết định có căn cứ**, không phải default cho mọi <code>OAuth2AuthorizationException</code>.

## 11. Authorized-client failure handler và token cleanup

Spring Security có các abstraction:

~~~text
OAuth2AuthorizationSuccessHandler
OAuth2AuthorizationFailureHandler
RemoveAuthorizedClientOAuth2AuthorizationFailureHandler
~~~

chúng giúp manager phối hợp persistence/cleanup theo kết quả cấp hoặc refresh token.

### 11.1. Vì sao xóa authorized client sau invalid_grant?

Nếu OP xác nhận refresh token không còn hợp lệ, retry token cũ liên tục là không tốt. Một failure handler có thể remove authorized client cũ và yêu cầu authorization lại.

### 11.2. Nhưng cluster có refresh-token rotation race

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Instance A
    participant B as Instance B
    participant DB as Shared Token Store
    participant OP as Token Endpoint

    A->>DB: Load(company,user-123)
    DB-->>A: A0 / R0, version=7
    B->>DB: Load(company,user-123)
    DB-->>B: A0 / R0, version=7
    A->>OP: Refresh R0
    OP-->>A: A1 / R1
    B->>OP: Refresh R0
    OP-->>B: invalid_grant
    A->>DB: Save A1/R1, version=8
    B->>DB: Remove record theo principal?
    Note over DB: B có thể xóa version 8 nếu delete không điều kiện
~~~

Chia sẻ DB **không tự serialize** token refresh requests.

### 11.3. Điều phối theo authorized-client key

Một policy an toàn hơn:

~~~text
key = registrationId + trustedPrincipalKey

1. Load authorized client.
2. Nếu access token đủ hạn → dùng.
3. Acquire distributed lock/single-flight theo key.
4. Load lại token sau lock.
5. Nếu node khác đã refresh → dùng bản mới.
6. Nếu cần → gọi Token Endpoint bằng refresh token mới nhất.
7. Atomic save cả access/refresh token và version/CAS.
8. Nếu invalid_grant → so sánh bản mới nhất trước khi remove.
9. Release lock có kiểm tra owner.
~~~

Đây là **pseudocode kiến trúc**, không phải hành vi mặc định của <code>DefaultOAuth2AuthorizedClientManager</code>.

### 11.4. Custom failure handler có thể làm mất default behavior

Nếu:

~~~java
manager.setAuthorizationFailureHandler(customFailureHandler);
~~~

hãy xác minh custom handler có còn làm những bước cleanup cần thiết theo policy. Handler chỉ log có thể giữ token invalid mãi; handler remove mọi error lại có thể xóa token hợp lệ khi Token Endpoint 503.

Không remove authorized client theo browser-supplied principal hoặc không điều kiện khi một phiên bản token mới vừa được lưu ở node khác.

## 12. Reactive WebFlux: OAuth2AuthorizationException đi qua Mono

Trong WebFlux:

~~~text
ReactiveOAuth2AuthorizedClientManager.authorize(...)
    → Mono<OAuth2AuthorizedClient>
~~~

Một lỗi có thể đến như **error signal của publisher**, không phải exception ngay khi tạo Mono.

### 12.1. Ví dụ phản ứng theo error signal

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> result =
    manager.authorize(authorizeRequest)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authorized client")))
        .doOnError(
            OAuth2AuthorizationException.class,
            ex -> recordSafeCategory(ex.getError().getErrorCode()));
~~~

Trong ví dụ, <code>manager</code>, <code>authorizeRequest</code> và method <code>recordSafeCategory</code> là dependencies của service đã có. <code>doOnError</code> chỉ quan sát, không tự recover.

### 12.2. onErrorResume cần recovery đúng policy

Nguy hiểm:

~~~java
.onErrorResume(OAuth2AuthorizationException.class,
    ex -> Mono.just(authorizedClientOfAnotherUser))
~~~

Đây là cross-user token leakage. Không bao giờ dùng token của principal khác để chữa lỗi.

Nếu resource là public và sản phẩm cho phép fallback riêng, có thể dùng dữ liệu public an toàn. Với endpoint cần user authorization, lỗi phải được propagate/recovered bằng reauthorization hợp lệ chứ không bypass quyền.

### 12.3. Tránh block() và subscribe() thủ công

Sai trong reactive handler:

~~~java
OAuth2AuthorizedClient client =
    manager.authorize(authorizeRequest).block();
~~~

Blocking Netty event-loop có thể gây latency/starvation hoặc lỗi runtime.

Sai:

~~~java
manager.authorize(authorizeRequest)
    .subscribe(client -> callApi(client));

return Mono.just("done");
~~~

Request có thể trả thành công trước khi authorize/API call hoàn tất, lỗi bị tách khỏi controller và Reactor Context bị mất.

Đúng hơn:

~~~java
return manager.authorize(authorizeRequest)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Not authorized")))
    .flatMap(client -> callApi(client));
~~~

## 13. WebFlux: authentication failure handler của oauth2Login

Reactive Spring Security cung cấp <code>ServerAuthenticationFailureHandler</code>, dùng với OAuth2 Login WebFilters.

~~~java
package example.security;

import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOAuth2LoginConfig {

    @Bean
    ServerAuthenticationFailureHandler oauth2FailureHandler() {
        return (webFilterExchange, failure) -> {
            if (failure instanceof OAuth2AuthenticationException oauth2) {
                String code = oauth2.getError().getErrorCode();
                // Ghi category đã giới hạn, không ghi raw description.
            }

            var response = webFilterExchange.getExchange().getResponse();
            response.setStatusCode(HttpStatus.SEE_OTHER);
            response.getHeaders().setLocation(
                URI.create("/login?error=oauth2"));
            return response.setComplete();
        };
    }

    @Bean
    SecurityWebFilterChain webChain(
            ServerHttpSecurity http,
            ServerAuthenticationFailureHandler oauth2FailureHandler) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/login", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authenticationFailureHandler(oauth2FailureHandler))
            .build();
    }
}
~~~

Đây là mẫu minh họa cho Spring Security versions hỗ trợ DSL tương ứng; API cụ thể có thể khác giữa phiên bản. Khác Servlet ở chỗ handler trả <code>Mono&lt;Void&gt;</code> và làm việc với <code>ServerWebExchange</code>.

Một <code>OAuth2AuthorizationException</code> trong reactive business service không tự được handler này xử lý: nó đi theo publisher chain của service/controller. Tương tự, HTTP 401/403 từ downstream WebClient có handler riêng.

## 14. Resource Server HTTP 401/403: không nhầm với Token Endpoint

<code>WebClient.retrieve()</code> thường biến non-2xx statuses thành HTTP client exception theo cấu hình mặc định, không mặc nhiên tạo <code>OAuth2AuthorizationException</code>.

### 14.1. Phân loại phản hồi downstream

| Phản hồi | Ý nghĩa có thể | Hướng xử lý |
|---|---|---|
| 401 Bearer <code>invalid_token</code> | Token expired/revoked/sai issuer/audience | Kiểm tra token/refresh/reauthorize theo policy |
| 401 không Bearer error | Header thiếu, gateway hoặc auth scheme khác | Kiểm tra HTTP client và proxy |
| 403 <code>insufficient_scope</code> | Token thiếu scope | Xem scopes/consent; không refresh mù |
| 403 khác | Role/tenant/ownership/WAF | Kiểm tra Resource Server authorization |
| 429 | Rate limit | Bounded backoff |
| 502/503 | Downstream outage | Retry có giới hạn nếu idempotent |

### 14.2. WebClient onStatus

~~~java
return reportsWebClient.get()
    .uri("/v1/reports")
    .retrieve()
    .onStatus(
        status -> status.value() == 401,
        response -> Mono.error(
            new DownstreamAuthenticationException(
                "Reports access token rejected")))
    .onStatus(
        status -> status.value() == 403,
        response -> Mono.error(
            new DownstreamPermissionException(
                "Reports permission denied")))
    .bodyToMono(ReportDto.class);
~~~

<code>DownstreamAuthenticationException</code>, <code>DownstreamPermissionException</code> và <code>ReportDto</code> là **application-defined types** trong ví dụ, không phải Spring Security built-ins. Cần định nghĩa chúng theo domain contract.

Nếu muốn phân biệt chính xác <code>invalid_token</code> và <code>insufficient_scope</code>, đọc <code>WWW-Authenticate</code> theo parser/HTTP contract phù hợp, không match chuỗi body tùy tiện.

### 14.3. OAuth2 WebClient filters

<code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code> và <code>ServletOAuth2AuthorizedClientExchangeFilterFunction</code> có thể tích hợp token/authorized-client manager với WebClient.

Việc filter có tự chuyển HTTP 401/403 thành authorization failure, xóa token hay không phụ thuộc **constructor, failure handler và Spring Security version**. Không mặc định cho rằng WebClient luôn remove token bị Resource Server từ chối.

## 15. Classification theo error code và operation

Một thiết kế bền vững tách:

~~~text
Upstream OAuth2Error / AuthenticationException / AuthorizationException
    ↓
Normalize error code
    ↓
Classifier: CATEGORY
    ↓
Policy theo operation/stage
    ├── User-facing response
    ├── Reauthorization
    ├── Retry/backoff
    ├── Token cleanup
    └── Metrics/tracing
~~~

### 15.1. Classifier ví dụ

~~~java
package example.oauth2;

import org.springframework.security.oauth2.core.OAuth2Error;

public final class OAuth2FailureClassifier {

    public enum Category {
        USER_DENIED,
        CLIENT_CONFIGURATION,
        GRANT_NOT_VALID,
        INTERACTION_REQUIRED,
        UPSTREAM_TEMPORARY,
        INSUFFICIENT_PERMISSION,
        OTHER
    }

    public Category classify(OAuth2Error error) {
        if (error == null) {
            return Category.OTHER;
        }

        String code = error.getErrorCode();

        if ("access_denied".equals(code)) {
            return Category.USER_DENIED;
        }
        if ("invalid_client".equals(code)
                || "unauthorized_client".equals(code)
                || "unsupported_grant_type".equals(code)) {
            return Category.CLIENT_CONFIGURATION;
        }
        if ("invalid_grant".equals(code)) {
            return Category.GRANT_NOT_VALID;
        }
        if ("login_required".equals(code)
                || "interaction_required".equals(code)
                || "consent_required".equals(code)) {
            return Category.INTERACTION_REQUIRED;
        }
        if ("server_error".equals(code)
                || "temporarily_unavailable".equals(code)) {
            return Category.UPSTREAM_TEMPORARY;
        }
        if ("insufficient_scope".equals(code)) {
            return Category.INSUFFICIENT_PERMISSION;
        }
        return Category.OTHER;
    }
}
~~~

**Category không quyết định duy nhất hành động.** <code>invalid_grant</code> khi login callback khác refresh token invalid_grant; <code>invalid_client</code> của backend worker khác lỗi authorization policy của user.

### 15.2. Những thông tin cần chuyển cùng category

~~~text
operation = oauth2_login | token_refresh | client_credentials | api_call
stage = authorization_callback | token_endpoint | userinfo | resource_server
registrationId = company
grantType = authorization_code | refresh_token | client_credentials
principalKey = trusted internal key, không lấy từ browser
errorCategory = grant_not_valid
~~~

Không dùng raw OAuth2Error description làm chính sách security. Hãy dùng operation + category + trusted context.

### 15.3. Unknown provider-specific errors

Một provider có thể trả <code>policy_error_1234</code> không có trong OAuth2ErrorCodes. Nên giữ mã gốc trong diagnostics nội bộ đã lọc và gắn normalized category <code>OTHER</code> cho UI/metrics. Không tự đổi mọi error lạ thành <code>invalid_grant</code>.

## 16. Mapping sang HTTP response an toàn

### 16.1. Browser OIDC Login

Một authentication failure handler có thể redirect:

~~~text
303 /login?error=oauth2
~~~

hoặc dùng behavior mặc định do Spring Security cung cấp. Browser không nên nhận stack trace, Client secret, raw OP description hay error URI chưa tin cậy.

### 16.2. BFF gọi dịch vụ downstream

User đã authenticated nhưng Reports API integration thất bại:

~~~json
{
  "type": "https://portal.example.org/problems/reports-unavailable",
  "title": "Không thể tải báo cáo",
  "status": 503,
  "detail": "Dịch vụ báo cáo tạm thời chưa sẵn sàng."
}
~~~

Đây là **ví dụ Problem Details**, không phải status bắt buộc cho mọi OAuth2AuthorizationException. Nếu lỗi do user cần cấp consent mới, một reauthorization flow có thể phù hợp hơn. Nếu client secret sai, phải cảnh báo vận hành.

### 16.3. Khi nào 401/403?

- **401** tại Portal khi request đến Portal chưa được authenticated hoặc credential Portal không hợp lệ.
- **403** khi principal đã có nhưng không được phép thực hiện business operation.
- **502/503** khi backend dependency không thể phục vụ theo contract, không thể giải quyết bằng user login.

Không tự map:

~~~text
OAuth2AuthenticationException -> always 401
OAuth2AuthorizationException  -> always 403
~~~

### 16.4. Không đưa upstream error_description lên URL

Sai:

~~~text
/login?message=<raw upstream description>
~~~

URL có thể đi vào browser history, Referer, access logs, analytics và cảnh báo bảo mật. Dùng code/message đã biên tập ở server và correlation ID tách biệt.

## 17. Multi-provider và tenant isolation

Một portal có:

~~~text
company → issuer https://idp.company.example
partner → issuer https://login.partner.example
~~~

Khi lỗi xảy ra:

1. Xác định ClientRegistration đã chọn.
2. Kiểm tra issuer/token endpoint đúng request gốc.
3. Phân biệt principal của Company và Partner.
4. Chỉ cleanup token đúng registration/principal/tenant.
5. Không “fallback” sang token của registration khác để cứu request.

### 17.1. OIDC identity không chỉ là email

OIDC dùng cặp <code>(iss, sub)</code> để định danh user trong trust domain của issuer. Hai providers có thể có cùng email hoặc cùng subject string mà vẫn là hai identities khác nhau.

Không lưu authorized-client theo email chưa verify hoặc dùng user-supplied principal key; có nguy cơ cross-user/tenant token leakage.

### 17.2. Mix-up có thể trông như invalid_grant

Nếu Client xử lý callback Provider A bằng Token Endpoint của Provider B, OP có thể trả <code>invalid_grant</code>. Root cause là **registration/issuer binding sai**, không phải code chỉ hết hạn.

Không sửa bằng cách thử mọi Token Endpoint cho đến khi code được chấp nhận. Điều đó tạo rủi ro OAuth mix-up/credential disclosure.

## 18. Observability: stage quan trọng hơn tên class

Chương **Lỗi và quan sát** cần phân biệt:

~~~text
OAuth2 Login
    authorization initiated
    callback received
    state validation
    token exchange
    authentication success/failure

OAuth2 Authorized Client
    cache hit/miss
    refresh attempted
    refresh success/failure
    client-credentials token request

Downstream API
    HTTP 2xx/401/403/429/5xx
    invalid_token / insufficient_scope
~~~

Nếu chỉ có một metric <code>oauth2_error_total</code>, đội vận hành rất khó biết user từ chối consent hay Client secret hỏng.

### 18.1. Structured logging

Một event phù hợp:

~~~text
event=oauth2_token_refresh_failed
registrationId=company
stage=token_endpoint
grantType=refresh_token
errorCategory=grant_not_valid
errorCode=invalid_grant
correlationId=01EXAMPLE
httpStatus=400
refreshAttempt=1
~~~

Không log:

~~~text
access_token=...
refresh_token=...
client_secret=...
authorization_code=...
code_verifier=...
id_token=...
state=...
nonce=...
session_cookie=...
client_assertion=...
~~~

Không mặc định log raw <code>error_description</code>: một provider có thể vô tình đưa account ID, endpoint, dữ liệu input hoặc thông tin hạ tầng vào mô tả.

### 18.2. Metrics có giới hạn cardinality

~~~text
oauth2_login_failure_total{provider,category}
oauth2_token_request_total{provider,grant_type,result}
oauth2_token_refresh_failure_total{provider,error_category}
oauth2_authorized_client_lookup_miss_total{provider}
oauth2_callback_state_mismatch_total{provider}
oauth2_downstream_401_total{service}
oauth2_downstream_403_total{service}
oauth2_token_endpoint_latency_seconds{provider}
~~~

Không gắn raw username, email, subject, jti, access token, state, description hoặc request ID làm metric labels. Cardinality có thể gây bùng nổ và tạo rủi ro lộ dữ liệu.

### 18.3. Distributed tracing

Một BFF request có thể có:

~~~text
traceId=request-123
  ├── span oauth2.authorized_client.lookup
  ├── span oauth2.token.refresh
  └── span reports.api.call
~~~

Span attributes nên chứa provider alias, normalized category, stage, grant type, HTTP status/latency. Không đưa OAuth2 credentials hoặc HTTP Authorization headers vào traces.

### 18.4. Correlation ID không nên là OAuth2 state

<code>state</code> có mục đích security correlation của authorization flow. Không dùng raw state làm tracing ID hay ghi trong URL logs chỉ để dễ điều tra. Hãy tạo một correlation ID độc lập, không phải secret.

## 19. Phân cấp độ nghiêm trọng của lỗi

| Tình huống | Mức quan tâm vận hành |
|---|---|
| User từ chối consent | Expected user outcome; không mặc nhiên incident |
| <code>invalid_client</code> tăng mạnh sau deploy | Cảnh báo cấu hình secret/key |
| Refresh <code>invalid_grant</code> tăng cùng số replicas | Khả năng rotation race/đồng bộ token |
| Authorization-code <code>invalid_grant</code> tăng | PKCE/callback/code reuse/redirect issue |
| State mismatch tăng | Cookie/SameSite/session store hoặc login CSRF attempts |
| OP <code>server_error</code>, latency tăng | Provider outage |
| API 403 tăng | Scope/role/tenant policy change |
| API 401 tăng | Token expiry/issuer/audience/gateway |

Không dùng mỗi sự kiện <code>access_denied</code> do user tự bấm Deny để bật high-severity alert. Ngược lại, <code>invalid_client</code> tăng đột biến sau secret rotation cần được theo dõi chặt.

## 20. Retry, reauthorization và cleanup không thể đồng nhất

### 20.1. Lỗi thường không nên retry y nguyên

- <code>invalid_client</code> do secret/key sai.
- <code>unsupported_grant_type</code>.
- <code>unauthorized_client</code>.
- <code>invalid_scope</code> do registration policy.
- <code>invalid_grant</code> do code đã dùng hoặc refresh token đã rotate.

Retry cùng input có thể tăng lỗi/rate limit mà không giải quyết vấn đề.

### 20.2. Lỗi tạm thời có thể retry giới hạn

- HTTP 503/502 từ Token Endpoint.
- HTTP 429 và Retry-After phù hợp.
- Network timeout sau khi phân loại ngữ nghĩa operation.

Thiết kế retry:

1. Timeout tổng và số lần thử tối đa.
2. Exponential backoff + jitter.
3. Không retry operation có side effect nếu không có idempotency policy.
4. Không log/request dump secret.
5. Không tự gửi lại cùng authorization code/refresh token khi không biết OP đã xử lý nó hay chưa.

### 20.3. Refresh timeout là trường hợp khó

~~~text
Client gửi refresh_token=R0
OP tạo access A1 + refresh R1
Response bị mất do network timeout
Client không biết R0 đã bị tiêu thụ hay chưa
~~~

Retry R0 có thể bị <code>invalid_grant</code> hoặc kích hoạt reuse detection. Không có transaction chuẩn giữa OP và local token DB. Cần thiết kế recovery, single-flight và conditional token state updates theo policy.

### 20.4. Đừng tự động revoke mọi token

Timeout, 503 hoặc invalid scope không tự có nghĩa token cũ bị thu hồi. Xóa toàn bộ authorized client theo mọi exception vừa gây mất session, vừa có thể che root cause.

## 21. Security: chống rò rỉ thông tin qua error handling

### 21.1. Không phản chiếu HTML hoặc query thô

Nếu OP trả mô tả chứa HTML đặc biệt, UI phải escape và/hoặc không render raw content. Một login error page không được trở thành reflected XSS.

### 21.2. Không làm open redirect

<code>OAuth2Error.getUri()</code> không phải URL hậu kiểm đã tin cậy. Không <code>sendRedirect</code> tới URI đó trừ khi đã kiểm soát đích.

### 21.3. Không bỏ token validation để “cứu” đăng nhập

ID Token sai signature, issuer, audience hoặc nonce phải bị từ chối. Không tự đọc email từ một JWT chưa xác minh rồi tạo Authentication để tránh lỗi cho user.

### 21.4. Không cho browser chọn token principal

Nếu refresh của user A lỗi, không dùng:

~~~text
?retryAs=userB
~~~

để tìm token user B. Authorized-client lookup phải dựa trên Authentication và trusted internal identity context.

### 21.5. Không catch Exception rồi cho quyền

Sai:

~~~java
try {
    validateIdToken(idToken);
} catch (Exception ex) {
    return authenticatedFromUnverifiedClaims(idToken);
}
~~~

Điều này bỏ trust validation của OIDC. Error recovery phải **fail closed** khi xác minh identity không đạt.

## 22. Testing: kiểm tra object và exception

### 22.1. Unit test OAuth2Error

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class OAuth2ErrorTest {

    @Test
    void exposesCodeDescriptionAndUri() {
        var error = new OAuth2Error(
            OAuth2ErrorCodes.INVALID_GRANT,
            "Grant rejected",
            "https://auth.example.org/docs/errors");

        assertEquals("invalid_grant", error.getErrorCode());
        assertEquals("Grant rejected", error.getDescription());
        assertEquals(
            "https://auth.example.org/docs/errors",
            error.getUri());
    }

    @Test
    void codeOnlyErrorHasOptionalFieldsEmpty() {
        var error = new OAuth2Error("invalid_request");
        assertEquals("invalid_request", error.getErrorCode());
        assertNull(error.getDescription());
        assertNull(error.getUri());
    }
}
~~~

### 22.2. Unit test hai exceptions

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OAuth2ExceptionTest {

    @Test
    void authenticationExceptionCarriesOAuth2Error() {
        var failure = new OAuth2AuthenticationException(
            new OAuth2Error("access_denied"));
        assertEquals(
            "access_denied",
            failure.getError().getErrorCode());
    }

    @Test
    void authorizationExceptionCarriesOAuth2Error() {
        var failure = new OAuth2AuthorizationException(
            new OAuth2Error("invalid_grant"));
        assertEquals(
            "invalid_grant",
            failure.getError().getErrorCode());
    }
}
~~~

### 22.3. Test classifier

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2Error;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OAuth2ClassifierTest {

    @Test
    void separatesClientFailureAndGrantFailure() {
        var classifier = new OAuth2FailureClassifier();

        assertEquals(
            OAuth2FailureClassifier.Category.CLIENT_CONFIGURATION,
            classifier.classify(new OAuth2Error("invalid_client")));

        assertEquals(
            OAuth2FailureClassifier.Category.GRANT_NOT_VALID,
            classifier.classify(new OAuth2Error("invalid_grant")));
    }
}
~~~

### 22.4. Reactive StepVerifier

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveAuthorizationFailureTest {

    @Test
    void propagatesAuthorizationException() {
        var failure = new OAuth2AuthorizationException(
            new OAuth2Error("invalid_grant"));

        Mono<String> result = Mono.error(failure);

        StepVerifier.create(result)
            .expectErrorSatisfies(ex -> {
                if (!(ex instanceof OAuth2AuthorizationException oauth2)) {
                    throw new AssertionError("Wrong exception type");
                }
                assertEquals(
                    "invalid_grant",
                    oauth2.getError().getErrorCode());
            })
            .verify();
    }
}
~~~

Với reactive test cần dependency <code>io.projectreactor:reactor-test</code>. Test này xác minh propagation, **không thay** integration test với Token Endpoint.

## 23. Integration tests theo từng giai đoạn

| Tình huống | Kỳ vọng |
|---|---|
| User từ chối consent | Authentication failure handler, không tạo session mới |
| Callback state sai | Từ chối login, không bỏ state validation |
| ID Token issuer/audience/nonce sai | Từ chối OIDC authentication |
| Code hết hạn/dùng lại | Token Endpoint invalid_grant, login không hoàn tất |
| Client secret sai | invalid_client, user-facing error an toàn + config alert |
| Refresh token revoked | Manager failure, reauthorization/cleanup policy |
| Hai nodes refresh R0 | Không xóa nhầm R1/new state khi B nhận invalid_grant |
| Token Endpoint 503 | Bounded retry, không xóa token hợp lệ bừa |
| Reports API 401 invalid_token | Classify downstream token issue |
| Reports API 403 insufficient_scope | Không retry refresh vô hạn |
| UserInfo 401 | OIDC login/UserInfo policy đúng |
| error_uri ngoại miền | Không open redirect |
| error_description chứa HTML | Không reflected XSS |
| Hai providers trùng email/sub | Không nhầm principal/issuer |
| Reactive manager Mono.error | Error propagated, không block/subscribe thủ công |

### 23.1. Mock login không thay OIDC protocol test

Spring Security Test có:

~~~text
MockMvc.with(oauth2Login()) / with(oidcLogin())
WebTestClient.mutateWith(mockOidcLogin())
~~~

Các công cụ này giúp mô phỏng user đã authenticated, nhưng **không xác minh thật** state, PKCE, Token Endpoint, UserInfo, ID Token signature hoặc callback error translation. Cần integration OP test và token endpoint fixtures phù hợp.

### 23.2. Test failure handler không lộ upstream data

Kiểm tra:

- Redirect chỉ tới URL nội bộ đã cho phép.
- Không có raw <code>error_description</code> trong response URL/HTML.
- Không có access token, refresh token, authorization code, state, nonce hoặc secret trong logs.
- Login failure không tạo authenticated session.
- Unknown provider error vẫn được xử lý an toàn.

## 24. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Login redirect về /login?error | OAuth2 Login authentication failure | Callback/state/token/ID Token validation |
| User bấm Deny nhưng logs ERROR nhiều | Classification chưa đúng | Đưa access_denied vào expected user outcome |
| invalid_state sau scale-out | Session/correlation không shared | Spring Session, cookie, load balancer |
| invalid_grant ngay callback | Code expiry/reuse, PKCE, redirect | Token request và authorization flow |
| invalid_grant khi refresh | Expired/revoked/rotation race | Token store, single-flight, OP policy |
| invalid_client sau deploy | Secret/key/mTLS rotation mismatch | Client registration và deployment version |
| User vẫn login nhưng downstream unavailable | Session và authorized client khác trạng thái | Reauthorization/integration error |
| API 401 nhưng không thấy OAuth2AuthorizationException | HTTP Resource Server error | WebClient/RestClient và WWW-Authenticate |
| API 403 và refresh liên tục | insufficient_scope bị nhầm expiry | Scope/consent/authorization |
| OP server_error tăng | Outage/latency | Provider health/circuit breaker |
| UserInfo bị từ chối | Access token/scope/claims | UserInfo configuration |
| error_uri dẫn tới website lạ | Open redirect | Không redirect raw error_uri |
| Raw token xuất hiện trong traces | HTTP instrumentation thu headers/body | Redact credentials |
| WebFlux block() bị lỗi | Blocking reactive publisher | Compose Mono |
| ControllerAdvice không bắt callback | Security filter đã handle trước MVC | oauth2Login.failureHandler |
| Callback rơi vào API chain | Chain matcher/order sai | Chọn chain browser đúng |
| Client credentials lỗi mà user nhận 401 | Upstream→Portal status mapping sai | Domain-specific error mapping |

### 24.1. Checklist chẩn đoán

~~~text
1. Lỗi xảy ra ở endpoint nào?
   - Authorization initiation?
   - Authorization callback?
   - Token Endpoint?
   - UserInfo?
   - Resource Server?
2. Có đúng ClientRegistration/issuer không?
3. Request đã authenticated tại Portal chưa?
4. Error code đến từ OP, Resource Server hay custom code?
5. Có OAuth2Error trong exception không?
6. Grant type là authorization_code, refresh_token hay client_credentials?
7. Có lỗi network/proxy/session/PKCE/nonce không?
8. Có khả năng token refresh race giữa nodes không?
9. Có cần retry/reauthorize/alert hay chỉ thông báo user?
10. Logs/metrics có an toàn, không chứa credentials?
~~~

## 25. Bài tập thực hành

### Bài 1 — OAuth2Error có tự bị throw không?

~~~java
OAuth2Error error = new OAuth2Error("invalid_grant");
~~~

**Đáp án:** Không. Đây là dữ liệu; phải có exception hoặc một flow khác sử dụng nó thì mới biểu diễn failure ở Java control flow.

### Bài 2 — Hai exceptions cùng mã

~~~java
new OAuth2AuthenticationException(new OAuth2Error("invalid_grant"));
new OAuth2AuthorizationException(new OAuth2Error("invalid_grant"));
~~~

**Đáp án:** Không được giả định cách xử lý giống nhau. Cần xem lỗi xảy ra khi login hay khi lấy/refresh authorized client.

### Bài 3 — access_denied từ consent

User chọn Deny trên OP.

**Đáp án:** Dẫn về login page với thông báo phù hợp; không tự retry consent vô hạn hoặc alert critical nếu đây là user outcome bình thường.

### Bài 4 — invalid_client sau secret rotation

Mọi token requests từ node A lỗi, node B vẫn thành công.

**Đáp án:** Kiểm tra secret/key versions và deployment config giữa replicas, không buộc mọi user login lại một cách máy móc.

### Bài 5 — invalid_grant khi refresh

Portal session vẫn hợp lệ nhưng refresh token bị revoke.

**Đáp án:** Có thể cần reauthorization một ClientRegistration hoặc cleanup theo policy; không nhất thiết invalidate toàn bộ Portal session.

### Bài 6 — Refresh race

Node A đã lưu R1, node B nhận invalid_grant với R0.

**Đáp án:** Không xóa không điều kiện token record của A. Cần reread, version/CAS và điều phối refresh theo key.

### Bài 7 — error_uri

Provider trả URI đến website lạ.

**Đáp án:** Không dùng <code>sendRedirect(error.getUri())</code> với URI không tin cậy; dùng help page nội bộ.

### Bài 8 — Resource Server 403

Reports API trả insufficient_scope.

**Đáp án:** Đây là lỗi authorization downstream; cần scopes/consent/policy, không tự ném invalid_grant để buộc login.

### Bài 9 — Reactive blocking

~~~java
OAuth2AuthorizedClient client = manager.authorize(request).block();
~~~

**Đáp án:** Không block trên Netty event-loop; dùng flatMap và error signal.

### Bài 10 — Mã OAuth2 và HTTP status

**Hỏi:** Vì sao <code>OAuth2ErrorCodes.INVALID_CLIENT</code> không phải HTTP status 401?

**Đáp án:** Nó là mã giao thức; endpoint response và Portal HTTP mapping phụ thuộc authentication method, context và chính sách.

### Bài 11 — ControllerAdvice không bắt OAuth2 Login

Callback thất bại trước khi request tới controller.

**Đáp án:** Cấu hình failure handler trên Spring Security authentication filter; ControllerAdvice không tự bắt mọi filter exception.

### Bài 12 — Unknown custom error

Provider trả <code>policy_error_739</code>.

**Đáp án:** Normalize vào category OTHER, lưu mã đã lọc trong diagnostics và tra contract provider. Không ép nó thành invalid_grant nếu chưa có bằng chứng.

### Bài 13 — Metric error_description

**Hỏi:** Vì sao không đưa mô tả lỗi thô làm metric label?

**Đáp án:** Có thể chứa PII, không ổn định, cardinality cao và gây rò rỉ. Dùng stage/category/provider alias giới hạn.

### Bài 14 — Callback state mismatch

Callback có state S2, authorization request gốc có S1.

**Đáp án:** Không bỏ state verification dù ID Token có thể ký đúng; phải từ chối flow không correlate.

### Bài 15 — WebClient error

WebClient nhận HTTP 401 từ Reports API nhưng không thấy OAuth2AuthorizationException.

**Đáp án:** HTTP client có exception/status pipeline riêng. Cần kiểm tra Resource Server header và OAuth2 filter wiring, không mặc định gọi manager là nguồn lỗi.

### Bài 16 — Bài thực hành tổng hợp

Thiết kế hệ thống:

1. OIDC Login với authorization code, state, PKCE theo provider.
2. AuthenticationFailureHandler với thông báo trung tính.
3. Authorized-client manager có refresh provider.
4. Token store phân vùng đúng registration/principal.
5. Refresh rotation handling cho hai replicas.
6. WebClient gọi API với access token đúng audience/scope.
7. Classifier tách error code khỏi operation/stage.
8. Domain HTTP mapping an toàn, không trả upstream description.
9. Logs, metrics và tracing có provider alias, normalized category, correlation ID.
10. Unit tests ba types; integration tests callback, token, UserInfo, Resource Server.
11. Test lỗi 401/403 không gây lặp refresh.
12. Test lỗi invalid_grant khi node B dùng refresh token đã rotate và không xóa token mới của A.

Giải thích vì sao **không thể dùng một quy tắc “mọi OAuth2Error → logout” cho toàn hệ thống**.

## 26. Tổng kết

- <code>OAuth2Error</code> là **dữ liệu lỗi**, có <code>errorCode</code>, <code>description</code> và <code>uri</code>; nó không phải exception hoặc HTTP response.
- <code>OAuth2AuthenticationException</code> là authentication exception có <code>OAuth2Error</code>, thường gặp trong OAuth2/OIDC Login và được Spring Security authentication infrastructure xử lý.
- <code>OAuth2AuthorizationException</code> mang <code>OAuth2Error</code> trong OAuth2 authorization/authorized-client/token operations như token refresh.
- Cùng <code>invalid_grant</code> có thể đến từ code exchange hoặc refresh; phải nhìn <code>operation</code>, <code>stage</code>, registration và principal context.
- Authorization callback, Token Endpoint JSON errors, UserInfo và Resource Server Bearer 401/403 là **những nguồn lỗi khác nhau**.
- Không đồng nhất tên exception với HTTP 401/403. HTTP response cần theo contract của Portal, chính sách authentication/authorization và trạng thái dependency.
- Servlet <code>oauth2Login().failureHandler(...)</code> xử lý lỗi trong login filter; authorized-client failures và downstream HTTP errors có handler riêng.
- WebFlux dùng Mono error signals; tránh <code>block()</code>/<code>subscribe()</code> tùy tiện hoặc fallback sang token của người khác.
- Với refresh-token rotation, <code>invalid_grant</code> có thể phát sinh do concurrent refresh; đừng xóa token state mới bằng unconditional delete.
- Không log tokens, code, session cookie hoặc raw OAuth2 error descriptions; không redirect tới <code>error_uri</code> chưa tin cậy.
- Observability hiệu quả cần stage, normalized category, grant type, provider alias, correlation ID và bounded metric labels.
- Unit tests constructor/getError không thay integration tests của callback/Token Endpoint/Resource Server hoặc multi-instance concurrency.

### Tài liệu tham khảo

- **Spring Security Java API — OAuth2Error:** <code>getErrorCode()</code>, <code>getDescription()</code>, <code>getUri()</code>.
- **Spring Security Java API — OAuth2AuthenticationException:** OAuth2 errors trong authentication processing.
- **Spring Security Java API — OAuth2AuthorizationException:** OAuth2 errors trong authorization/token operations.
- **Spring Security Java API — OAuth2ErrorCodes:** các mã lỗi chuẩn.
- **Spring Security Reference — OAuth2 Login (Servlet/Reactive):** callback, authentication failure handler, OIDC validation.
- **Spring Security Reference — OAuth2 Client:** authorized-client manager/providers, token clients, success/failure handlers.
- **Spring Security Reference — Reactive OAuth2 Client:** <code>ReactiveOAuth2AuthorizedClientManager</code> và reactive error handling.
- **Spring Security Reference — OAuth2 Resource Server:** Bearer error responses, 401/403 và <code>WWW-Authenticate</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization/Token Endpoint error responses.
- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage:** invalid_token và insufficient_scope.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code binding và lỗi liên quan.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token rotation, replay, mix-up protection.
- **OpenID Connect Core 1.0:** OIDC errors, ID Token validation và UserInfo.
- **RFC 9457 — Problem Details for HTTP APIs:** biểu diễn lỗi HTTP ổn định cho application clients.
- **OWASP Logging Cheat Sheet:** logging security events an toàn, tránh credentials/PII.
