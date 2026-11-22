# Xử lý lỗi token, scope và người dùng không còn khả dụng

## Mục tiêu bài học

Trong chương **OIDC UserInfo** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này hướng dẫn xử lý lỗi và thay đổi trạng thái người dùng tại **OpenID Connect UserInfo Endpoint** khi xây dựng Authorization Server bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**.

UserInfo là OAuth 2.0 Protected Resource trả về claims về End-User đã được xác thực. Client gọi endpoint bằng access token nhận từ OIDC Authentication Flow. Trong vận hành, request có thể thất bại vì token hết hạn/bị thu hồi, token thiếu scope, người dùng bị khóa hoặc xóa, dữ liệu hồ sơ không còn, hay dịch vụ user directory tạm thời không truy cập được.

Không nên gom mọi trường hợp thành một lỗi chung. Mỗi trường hợp có ý nghĩa và cách xử lý khác nhau:

- **Token không hợp lệ:** request không có credential hợp lệ; trả Bearer error **invalid_token**.
- **Thiếu quyền bắt buộc:** token hợp lệ nhưng không có scope cần thiết cho thao tác; trả **insufficient_scope** theo policy.
- **Thiếu claim tùy chọn:** token vẫn hợp lệ, nhưng người dùng không có hoặc OP không muốn tiết lộ một trường; bỏ claim đó khỏi response.
- **Người dùng bị vô hiệu hóa/xóa:** áp dụng chính sách deprovisioning, vô hiệu hóa authorization/token và từ chối truy cập theo policy.
- **User directory tạm thời gặp sự cố:** đây là lỗi hạ tầng; không đánh dấu token hoặc người dùng là invalid chỉ vì không truy vấn được dữ liệu.

Sau bài học, bạn có thể:

1. Giải thích hợp đồng UserInfo theo OpenID Connect Core 1.0 mục 5.3 và Bearer Token Usage RFC 6750.
2. Phân biệt **invalid_token (401)** với **insufficient_scope (403)** và lỗi dịch vụ (5xx).
3. Hiểu vì sao **sub** luôn bắt buộc và client phải so sánh nó với **sub** trong ID Token.
4. Giải thích cách các scope **openid**, **profile**, **email**, **address**, **phone** quyết định claims được trả.
5. Nhận biết hành vi mặc định của **OidcUserInfoAuthenticationProvider** và mapper trong Spring Authorization Server 1.5.8.
6. Tùy chỉnh **userInfoMapper** để đọc hồ sơ hiện tại, lọc claims theo scope và xử lý người dùng không còn khả dụng.
7. Phân biệt tài khoản bị disable/deleted với một trường hồ sơ đang trống hoặc một dịch vụ dữ liệu tạm thời unavailable.
8. Thiết kế revoke access/refresh authorization, cache, error handling, logging và test end-to-end.

> **Tình huống xuyên suốt:** **employee-portal** đã nhận ID Token và access token của user **user-42**. Sau đó, access token hết hạn; người dùng bị khóa; hoặc email bị xóa khỏi hồ sơ. Khi portal gọi **/userinfo**, Authorization Server phải trả kết quả đúng theo từng tình huống, giữ ổn định **sub** và không tiết lộ dữ liệu ngoài scope được cấp.

## 1. UserInfo là một Protected Resource của OIDC

OIDC UserInfo Endpoint trả claims về End-User đã được xác thực. Client lấy endpoint từ Provider Metadata qua thuộc tính **userinfo_endpoint**, sau đó gửi access token nhận từ OIDC Authentication Request.

### 1.1. Request chuẩn

OIDC Core yêu cầu UserInfo Endpoint:

- Sử dụng TLS.
- Hỗ trợ HTTP GET và HTTP POST.
- Chấp nhận access token theo cơ chế OAuth 2.0 Bearer Token Usage.
- Khuyến nghị dùng GET và truyền token trong HTTP **Authorization** header.
- Có thể hỗ trợ CORS để browser-based clients gọi endpoint phù hợp.

Ví dụ request được khuyến nghị:

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer OIDC_ACCESS_TOKEN
Accept: application/json
~~~

Không đưa access token vào query string. URL có thể xuất hiện trong reverse proxy logs, tracing, browser history và hệ thống analytics. Cũng không gửi token trong URL của ảnh, script hoặc referrer.

Client không tự đoán đường dẫn UserInfo. Hãy lấy **userinfo_endpoint** từ OpenID Provider Configuration/Discovery đã xác minh issuer.

### 1.2. UserInfo không phải Token Endpoint

| Endpoint | Credential | Mục đích |
|---|---|---|
| Authorization Endpoint | Browser session và authorization request | Xác thực người dùng, consent, cấp authorization code. |
| Token Endpoint | Authorization code/refresh token và client authentication theo loại client | Cấp access token, ID Token, refresh token. |
| UserInfo Endpoint | OIDC access token dạng Bearer | Trả claims về End-User theo scope đã cấp. |
| Introspection Endpoint | Token cần kiểm tra và credential của caller | Trả trạng thái active và metadata token. |
| Revocation Endpoint | Token cần thu hồi và client authentication theo policy | Vô hiệu hóa token/authorization. |

UserInfo không nhận ID Token thay cho access token. ID Token là kết quả xác thực dành cho OIDC Client; access token là credential được gửi tới UserInfo Protected Resource.

### 1.3. Luồng xử lý tổng quát

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OIDC Client
    participant U as UserInfo Endpoint
    participant AS as Authorization Server
    participant DB as User / Authorization Store

    C->>U: GET /userinfo + Bearer access token
    U->>AS: Validate JWT/access-token state
    AS->>DB: Load authorization and token state
    DB-->>AS: Token active? Scopes? ID Token?
    AS-->>U: Authenticated request context
    U->>DB: Load current user profile (if dynamic mapper)
    DB-->>U: Active user / missing user / unavailable
    alt Token valid and user available
        U-->>C: 200 JSON with sub + allowed claims
    else Token expired, revoked or invalid
        U-->>C: 401 invalid_token
    else Required scope missing
        U-->>C: 403 insufficient_scope
    else User disabled/deleted by policy
        U-->>C: 401 invalid_token after deprovisioning policy
    else User store unavailable
        U-->>C: 503 Service Unavailable
    end
    C->>C: Verify UserInfo sub equals ID Token sub
~~~

Sơ đồ cho thấy một request có thể cần cả kiểm tra access token lẫn truy vấn hồ sơ hiện tại. Nếu dùng default mapper lấy claims từ ID Token, bước truy vấn user directory có thể không xảy ra ở mỗi request.

## 2. Claims, sub và kiểm tra phía Client

### 2.1. sub luôn bắt buộc

Theo OIDC Core mục 5.3.2, UserInfo Response **MUST luôn chứa claim sub**. **sub** là subject identifier của End-User trong phạm vi issuer.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "sub": "user-42",
  "name": "Nguyen An",
  "email": "an@example.com",
  "email_verified": true
}
~~~

**sub** phải ổn định theo quy tắc subject identifier của OP. Không dùng email, username hoặc số điện thoại làm **sub** nếu những giá trị đó có thể thay đổi, được tái sử dụng hoặc phụ thuộc tenant mà không có thiết kế pairwise subject rõ ràng.

### 2.2. Client phải đối chiếu sub với ID Token

UserInfo Response không mặc nhiên được đảm bảo nói về đúng End-User mà client thấy trong ID Token. OIDC Core yêu cầu client kiểm tra **sub** trong UserInfo **khớp chính xác** với **sub** trong ID Token. Nếu khác, client **MUST không sử dụng các giá trị UserInfo**.

Điều này chống token substitution: client có thể vô tình gửi access token của session A trong khi ghép dữ liệu với ID Token của session B.

Pseudo-code phía client:

~~~java
String idTokenSubject = oidcIdToken.getSubject();
String userInfoSubject = userInfo.getSubject();

if (!Objects.equals(idTokenSubject, userInfoSubject)) {
    throw new OAuth2AuthenticationException(
            new OAuth2Error("invalid_userinfo_response"));
}

// Chỉ sử dụng UserInfo sau khi subject đã được đối chiếu.
~~~

Ví dụ giả định **oidcIdToken** đã được xác minh chữ ký, issuer, audience, expiry và nonce. Không decode payload chưa xác minh rồi lấy **sub** làm trust anchor.

### 2.3. Không trả claim rỗng hoặc null

Vì lý do privacy, OP có thể không trả một claim được client yêu cầu. OIDC Core quy định việc không trả một claim tùy chọn không phải lỗi. Nếu claim không được trả, nên **bỏ hẳn tên claim** khỏi JSON; không trả **null** hoặc chuỗi rỗng.

Ví dụ khi người dùng không cung cấp email:

~~~json
{
  "sub": "user-42",
  "name": "Nguyen An"
}
~~~

Response trên hợp lệ nếu email là claim tùy chọn chưa có/không được tiết lộ. Không nên trả:

~~~json
{
  "sub": "user-42",
  "email": null,
  "email_verified": ""
}
~~~

Đối với **sub**, quy tắc khác: luôn phải có. Nếu hệ thống không thể xác định một subject ổn định, không nên trả một response UserInfo thành công với **sub** giả hoặc rỗng.

## 3. Scope quyết định claims được trả

OIDC Core định nghĩa các scope chuẩn để yêu cầu nhóm claims. Việc cấp scope phải tuân theo client registration, consent, policy và authorization request.

| Scope | Claims tiêu chuẩn thường được yêu cầu |
|---|---|
| **openid** | **sub** và lớp định danh OIDC. |
| **profile** | **name**, **family_name**, **given_name**, **middle_name**, **nickname**, **preferred_username**, **profile**, **picture**, **website**, **gender**, **birthdate**, **zoneinfo**, **locale**, **updated_at**. |
| **email** | **email**, **email_verified**. |
| **address** | **address** object theo schema OIDC. |
| **phone** | **phone_number**, **phone_number_verified**. |

### 3.1. Scope được yêu cầu không phải lúc nào cũng là scope được cấp

Client có thể gửi **scope=openid profile email**, nhưng Authorization Server có thể cấp ít hơn theo client policy, consent hoặc quyền người dùng. UserInfo phải dựa vào **scope thực tế của access token**, không chỉ dựa vào query ban đầu của client.

Ví dụ:

~~~text
Authorization Request:
    scope = openid profile email

Access Token được cấp:
    scope = openid profile

UserInfo Response:
    sub, name, given_name, family_name, ...
    không trả email/email_verified
~~~

Không trả email khi thiếu **email** scope. Nếu client cần email, nó phải thực hiện authorization request mới hoặc quy trình consent phù hợp.

### 3.2. Thiếu scope bắt buộc và thiếu scope của claim tùy chọn

Phải phân biệt hai trường hợp:

- **Endpoint/policy yêu cầu scope bắt buộc** nhưng token không có scope đó: có thể trả **403 insufficient_scope**.
- Token hợp lệ và có **openid**, nhưng thiếu **profile**, **email**, **address** hoặc **phone**: thường trả **200** với các claim tương ứng được bỏ qua.

Không trả **403** chỉ vì người dùng không có email hoặc OP quyết định không tiết lộ email. OIDC Core cho phép OP omit claims vì privacy; việc thiếu claim tùy chọn không phải lỗi.

### 3.3. Không phát claims chỉ vì dữ liệu tồn tại

Giả sử database có email, số điện thoại, địa chỉ và ngày sinh. Nếu access token chỉ có **openid profile**, mapper không được trả **email**, **phone_number** hoặc **address** chỉ vì các trường này sẵn có.

Quy tắc tối thiểu:

1. **sub** luôn được trả.
2. Claim thuộc nhóm scope chỉ được trả khi scope tương ứng có trong access token.
3. Claim có thể bị lược bỏ vì privacy, consent, user preference hoặc policy.
4. Claim không có giá trị thì bỏ qua, không trả null/empty.
5. Claim mở rộng phải có policy, tài liệu và kiểm thử riêng.

## 4. Các nhóm lỗi và HTTP status

OIDC Core mục 5.3.3 quy định UserInfo Error Response theo RFC 6750. Vì vậy, lỗi token và scope phải tuân thủ Bearer Token error semantics.

| Tình huống | HTTP status | Bearer error | Hành động client |
|---|---:|---|---|
| Không gửi access token | 401 | Thường không cần error code chi tiết nếu thiếu credential | Gửi request với Bearer token hợp lệ. |
| Token malformed/expired/revoked | 401 | **invalid_token** | Xin access token mới nếu refresh session còn hợp lệ. |
| Token sai issuer/audience hoặc không dành cho UserInfo | 401 | **invalid_token** | Kiểm issuer, token audience/resource và cấu hình OP. |
| Token thiếu scope bắt buộc của endpoint/policy | 403 | **insufficient_scope** | Xin authorization với scope phù hợp. |
| Chỉ thiếu scope email hoặc profile tùy chọn | 200 | Không phải lỗi | Chấp nhận response thiếu các claim đó. |
| User disabled/deleted theo policy | 401 | **invalid_token** | Bắt đầu authentication mới hoặc xử lý session bị vô hiệu hóa. |
| User directory/database tạm thời unavailable | 503 | HTTP service error | Retry có backoff; không refresh token liên tục. |
| Response không có sub hoặc sub không khớp ID Token | Client phải từ chối response | Lỗi response validation phía client | Không sử dụng claims từ response đó. |

### 4.1. invalid_token: 401 Unauthorized

RFC 6750 định nghĩa **invalid_token** cho access token hết hạn, bị revoke, malformed hoặc không hợp lệ vì lý do khác. Resource Server nên trả HTTP 401 và **WWW-Authenticate** Bearer challenge.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Không đưa raw token, nội dung chữ ký hoặc thông tin nội bộ về user vào **error_description**. Client chỉ cần biết credential không còn sử dụng được.

### 4.2. insufficient_scope: 403 Forbidden

RFC 6750 quy định **insufficient_scope** khi request yêu cầu quyền cao hơn quyền được cấp trong access token. Resource Server nên trả HTTP 403.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="openid email"
Cache-Control: no-store
~~~

Chỉ dùng lỗi này khi scope thực sự là điều kiện bắt buộc của thao tác. Nếu OP có thể trả **sub** nhưng không có email, không cần từ chối toàn bộ UserInfo chỉ vì email không tồn tại hoặc không được cấp.

### 4.3. Không có Bearer credential

Khi request không có thông tin xác thực, RFC 6750 khuyến nghị server không đưa mã lỗi hoặc chi tiết bổ sung trong challenge. Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Không biến request không có token thành response **invalid_token** kèm thông tin chi tiết, vì client chưa cung cấp credential để đánh giá.

### 4.4. Lỗi dịch vụ dữ liệu: 503

Nếu user directory tạm thời mất kết nối, timeout hoặc database failover, không nên trả **invalid_token**. Token có thể vẫn hợp lệ; hệ thống chỉ chưa thể hoàn tất truy vấn profile.

Ví dụ:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 5
Content-Type: application/json
Cache-Control: no-store

{
  "error": "temporarily_unavailable"
}
~~~

Đây là lỗi HTTP dịch vụ của ứng dụng, không phải một Bearer token error. Client nên retry có giới hạn và exponential backoff; không lặp request liên tục hoặc tự động xin token mới trong khi user directory đang lỗi.

## 5. Hành vi mặc định của Spring Authorization Server

Spring Authorization Server 1.5.8 cung cấp OIDC UserInfo endpoint qua **OidcUserInfoEndpointFilter** và **OidcUserInfoAuthenticationProvider**.

### 5.1. Các thành phần chính

| Thành phần | Vai trò |
|---|---|
| **OidcUserInfoEndpointFilter** | Nhận UserInfo request và xử lý response. |
| **OidcUserInfoAuthenticationToken** | Đại diện authentication được tạo cho UserInfo request. |
| **OidcUserInfoAuthenticationProvider** | Kiểm tra authorization/token state và tạo UserInfo authentication result. |
| **OAuth2AuthorizationService** | Truy xuất authorization và token liên quan. |
| **OidcUserInfoAuthenticationContext** | Cung cấp authentication, access token và authorization cho mapper. |
| **OidcUserInfoEndpointConfigurer** | Cấu hình converter, provider, mapper, success/error handler. |
| **OidcUserInfo** | Object claims được serialize thành UserInfo Response. |

Spring Authorization Server cấu hình mapper mặc định để lấy standard claims từ ID Token theo các scope đã được yêu cầu/cấp trong authorization. Điều này giúp response chuẩn hoạt động mà không cần tự viết mapper ngay từ đầu.

### 5.2. Default mapper và custom mapper khác nhau thế nào?

**Default mapper** thường dùng claims đã được phát hành trong ID Token. Ưu điểm là response nhất quán với thông tin tại thời điểm authentication và không phải query user database mỗi lần.

**Custom mapper** cho phép ứng dụng truy vấn dữ liệu mới nhất từ database, LDAP hoặc domain service. Điều này hữu ích khi email, tên hoặc trạng thái user có thể thay đổi sau khi token được cấp. Nhưng ứng dụng phải tự đảm bảo:

- **sub** luôn tồn tại và ổn định.
- Claims được lọc theo scope thực tế.
- Không trả claims vượt consent/privacy policy.
- Tài khoản disable/deleted được xử lý theo lifecycle policy.
- Lỗi hạ tầng không bị nhầm thành token invalid.
- Response không có null/empty claims.
- Subject của response trùng subject của ID Token.

**Quan trọng:** khi thay **userInfoMapper**, bạn chịu trách nhiệm cho logic claims của mapper mới. Đừng giả định custom mapper tự giữ mọi hành vi lọc scope của default mapper.

### 5.3. UserInfo endpoint cần JwtDecoder

Tài liệu Spring Authorization Server 1.5.8 nêu rằng OIDC enable tự cấu hình Resource Server support để xác thực access token tại UserInfo endpoint và cần một **JwtDecoder** bean.

Ví dụ:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Ví dụ này dùng JWK source của Authorization Server. Trong production, khóa ký phải ổn định và **JwtDecoder** phải xác minh chữ ký, issuer và các điều kiện token theo cấu hình.

Nếu ứng dụng dùng opaque/reference access token, không tự giả định built-in OIDC UserInfo endpoint của phiên bản đang dùng sẽ xử lý nó giống Resource Server opaque-token introspection. Hướng dẫn SAS 1.5.8 yêu cầu **JwtDecoder**; hãy xác minh token format và tích hợp thực tế. Nếu cần opaque token, phải có thiết kế hỗ trợ phù hợp và integration tests cho chính endpoint UserInfo.

## 6. Cấu hình UserInfo endpoint

### 6.1. Bật OIDC và endpoint

Ví dụ khung **SecurityFilterChain**:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(oidc ->
                oidc.userInfoEndpoint(userInfo ->
                    userInfo.userInfoMapper(userInfoMapper)
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung cấu hình cho Spring Authorization Server 1.5.x. Ứng dụng hoàn chỉnh vẫn cần **RegisteredClientRepository**, **OAuth2AuthorizationService**, **AuthorizationServerSettings**, **JWKSource**, **JwtDecoder**, các filter chain đăng nhập và persistence phù hợp.

Nếu chỉ muốn dùng mapper mặc định, bật **.oidc(Customizer.withDefaults())** là đủ cho endpoint theo cấu hình chuẩn; chỉ thêm mapper tùy chỉnh khi có nhu cầu domain cụ thể.

### 6.2. Các hook tùy chỉnh

**OidcUserInfoEndpointConfigurer** cung cấp:

- **userInfoRequestConverter(...)** / **userInfoRequestConverters(...)**: chuyển HTTP request thành authentication token.
- **authenticationProvider(...)** / **authenticationProviders(...)**: thêm hoặc tùy chỉnh provider.
- **userInfoMapper(...)**: ánh xạ **OidcUserInfoAuthenticationContext** thành **OidcUserInfo**.
- **userInfoResponseHandler(...)**: xử lý response thành công.
- **errorResponseHandler(...)**: xử lý **OAuth2AuthenticationException** và trả error response.

Đối với bài toán claims theo user và scope, **userInfoMapper** thường là điểm mở rộng trực tiếp nhất. Đối với lỗi user store tạm thời, có thể cần **errorResponseHandler** riêng để ánh xạ lỗi hạ tầng thành HTTP 503. Giữ cách serialize OAuth2/Bearer error chuẩn cho các lỗi token.

Khi map lỗi scope, hãy kiểm tra status code thực tế của handler: **insufficient_scope** phải ra HTTP 403 theo RFC 6750, còn **invalid_token** phải ra HTTP 401. Không giả định chỉ đặt tên OAuth2 error là framework tự chọn đúng status cho mọi cấu hình.

### 6.3. Mapper có thể truy cập dữ liệu gì?

**OidcUserInfoAuthenticationContext** cung cấp:
- **getAuthentication()** — **OidcUserInfoAuthenticationToken** hiện tại.
- **getAccessToken()** — access token được dùng cho request.
- **getAuthorization()** — **OAuth2Authorization** gắn với access token; có ID Token và access-token state nếu flow là OIDC Authorization Code.

**OAuth2Authorization** lưu principal name, grant type, authorized scopes, token và attributes. **OAuth2Authorization.Token** cung cấp trạng thái **isActive()**, **isExpired()**, **isInvalidated()** cùng claims/metadata.

Không lấy subject từ email hoặc dữ liệu client gửi trong query. Nguồn subject phải là ID Token/authorization đã xác thực hoặc định danh subject ổn định do Authorization Server quản lý.

## 7. Viết mapper lọc claims theo scope

Ví dụ dưới đây minh họa mapper đọc hồ sơ hiện tại từ **UserDirectory**, giữ **sub**, chỉ đưa claims vào response khi scope tương ứng có trong access token và bỏ qua các trường không có giá trị.

### 7.1. Contract dữ liệu của ứng dụng

~~~java
import java.util.Optional;

public interface UserDirectory {
    Optional<UserProfile> findBySubject(String subject);
}

public record UserProfile(
        String subject,
        boolean active,
        String name,
        String givenName,
        String familyName,
        String email,
        Boolean emailVerified) {
}
~~~

**UserDirectory** và **UserProfile** là type do ứng dụng định nghĩa, không phải API Spring. Trong hệ thống thật, subject phải được ánh xạ sang immutable user ID. Không dùng username/email làm khóa liên kết nếu các giá trị này có thể đổi hoặc tái sử dụng.

### 7.2. Mapper mẫu

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;

final class CurrentUserInfoMapper {

    private final UserDirectory userDirectory;

    CurrentUserInfoMapper(UserDirectory userDirectory) {
        this.userDirectory = userDirectory;
    }

    OidcUserInfo map(OidcUserInfoAuthenticationContext context) {
        OAuth2Authorization authorization = context.getAuthorization();

        OAuth2Authorization.Token<OAuth2AccessToken> accessToken =
                authorization.getAccessToken();

        if (accessToken == null || !accessToken.isActive()) {
            throw oauth2Error("invalid_token");
        }

        Set<String> scopes = accessToken.getToken().getScopes();

        if (!scopes.contains(OidcScopes.OPENID)) {
            throw oauth2Error("insufficient_scope");
        }

        OAuth2Authorization.Token<OidcIdToken> idTokenHolder =
                authorization.getToken(OidcIdToken.class);

        if (idTokenHolder == null) {
            throw oauth2Error("invalid_token");
        }

        String subject = idTokenHolder.getToken().getSubject();
        if (subject == null || subject.isBlank()) {
            throw oauth2Error("invalid_token");
        }

        UserProfile user = this.userDirectory.findBySubject(subject)
                .orElseThrow(() -> oauth2Error("invalid_token"));

        if (!user.active() || !subject.equals(user.subject())) {
            throw oauth2Error("invalid_token");
        }

        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("sub", subject);

        if (scopes.contains(OidcScopes.PROFILE)) {
            putIfPresent(claims, "name", user.name());
            putIfPresent(claims, "given_name", user.givenName());
            putIfPresent(claims, "family_name", user.familyName());
            // Bổ sung middle_name, nickname, picture, locale...
            // khi domain model và policy thực sự cung cấp chúng.
        }

        if (scopes.contains(OidcScopes.EMAIL)) {
            putIfPresent(claims, "email", user.email());
            putIfPresent(claims, "email_verified", user.emailVerified());
        }

        return new OidcUserInfo(claims);
    }

    private static void putIfPresent(
            Map<String, Object> claims, String name, Object value) {
        if (value == null) {
            return;
        }
        if (value instanceof String text && text.isBlank()) {
            return;
        }
        claims.put(name, value);
    }

    private static OAuth2AuthenticationException oauth2Error(String code) {
        return new OAuth2AuthenticationException(new OAuth2Error(code));
    }
}
~~~

Đăng ký function bean:

~~~java
@Bean
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
        UserDirectory userDirectory) {

    CurrentUserInfoMapper mapper = new CurrentUserInfoMapper(userDirectory);
    return mapper::map;
}
~~~

**Giới hạn của ví dụ:**
- Đây là mapper theo scope **openid**, **profile**, **email**; cần bổ sung **address** và **phone** nếu ứng dụng phát các scope đó.
- **UserDirectory** phải trả về hồ sơ theo immutable subject. Không tìm theo email từ access token.
- Ví dụ xem user không tồn tại/disabled là **invalid_token** theo policy deprovisioning của ứng dụng. Phải đồng thời có quy trình revoke authorization/refresh token liên quan.
- Không bắt **DataAccessException** rồi đổi thành **invalid_token**; lỗi truy cập dữ liệu tạm thời phải đi theo error path 5xx.
- SAS provider mặc định đã kiểm tra token. Kiểm tra **isActive()** trong mapper là defense-in-depth và làm rõ hợp đồng; không thay thế kiểm tra JWT decoder.
- Nếu thay default mapper, bạn chịu trách nhiệm giữ scope filtering và **sub** contract.

### 7.3. Bổ sung các scope còn lại

Có thể mở rộng mapper theo cùng quy tắc:

~~~java
if (scopes.contains(OidcScopes.ADDRESS) && user.address() != null) {
    claims.put("address", user.address());
}

if (scopes.contains(OidcScopes.PHONE) && user.phoneNumber() != null) {
    claims.put("phone_number", user.phoneNumber());
    if (user.phoneNumberVerified() != null) {
        claims.put("phone_number_verified", user.phoneNumberVerified());
    }
}
~~~

Đoạn mở rộng giả định domain model có **address()**, **phoneNumber()** và **phoneNumberVerified()**. Chỉ thêm các phương thức này khi model thực tế có chúng. Address cần theo cấu trúc OIDC Standard Claims, không trả một chuỗi tùy ý rồi gọi là address object.

## 8. Người dùng không còn khả dụng

“Không còn khả dụng” có thể mô tả nhiều tình huống khác nhau. Chính sách không nên đánh đồng một profile field trống với tài khoản bị khóa hoặc dịch vụ directory đang outage.

### 8.1. Phân loại trạng thái user

| Trạng thái | Ý nghĩa | Xử lý gợi ý tại UserInfo |
|---|---|---|
| User active, có đầy đủ profile | Có thể trả claims được cấp. | 200, **sub** + claims theo scope. |
| User active, thiếu email/phone/address | Một số thuộc tính không có. | 200, bỏ claim thiếu; không trả null/empty. |
| User active, claim bị privacy policy ẩn | OP không được phép tiết lộ claim đó. | 200, bỏ claim bị ẩn. |
| User bị suspend/disabled | Danh tính không còn được phép sử dụng. | Revoke/disable authorization theo policy; trả **invalid_token** (401). |
| User bị xóa/deprovisioned | Subject không còn được phép truy cập. | Revoke grant/token liên quan; trả **invalid_token** (401). |
| User merge hoặc subject mapping thay đổi | Có nguy cơ đổi danh tính giữa token cũ và user mới. | Không remap âm thầm; giữ subject cũ hoặc buộc authorization mới. |
| User database timeout/unavailable | Không xác định được trạng thái hiện tại. | 503; không đánh dấu token invalid. |
| User record lỗi/mâu thuẫn subject | Không thể tạo response có identity đáng tin. | Từ chối response; điều tra data integrity, không trả **sub** khác. |

### 8.2. User bị khóa hoặc xóa

Một access token có thể vẫn còn thời hạn khi người dùng bị khóa. Nếu UserInfo mapper chỉ lấy claims đã lưu trong ID Token, nó có thể tiếp tục trả profile cũ cho đến khi token hết hạn.

Khi có sự kiện deprovisioning, nên:

1. Đánh dấu user disabled/deleted trong nguồn danh tính.
2. Ngăn user tạo authorization mới.
3. Revoke authorization/refresh token theo chính sách.
4. Đánh dấu access token liên quan invalidated nếu Authorization Server quản lý trạng thái đó.
5. Với JWT access token được Resource Server xác minh offline, bảo đảm có introspection/denylist/session-version hoặc TTL đủ ngắn nếu cần hiệu lực sớm.
6. UserInfo mapper kiểm tra trạng thái user hiện tại và từ chối ngay khi tài khoản không còn khả dụng.
7. Client nhận lỗi **invalid_token** và bắt đầu login/reauthorization theo UX.
8. Ghi audit event nội bộ, không ghi raw access token.

**invalid_token** là lựa chọn hợp lý khi policy đã quyết định access token không còn được chấp nhận vì user đã deprovisioned. OIDC không định nghĩa một error code riêng để tiết lộ “user bị khóa” hay “user đã bị xóa”; không nên trả lý do chi tiết cho client.

### 8.3. Không remap subject khi người dùng đổi định danh

Giả sử user có subject **user-42**, sau đó email thay từ **an@example.com** thành **an.nguyen@example.com**. Subject không được tự đổi theo email.

Nếu tài khoản cũ bị xóa và tài khoản mới được tạo, không tái sử dụng **sub=user-42** cho một người khác. Nếu tổ chức cần merge account, cần quy trình migration có kiểm soát và xác định authorization cũ có còn tin cậy hay không.

Client phải luôn so **sub** trong UserInfo với ID Token. Mapper không được trả subject từ một bản ghi user khác chỉ vì lookup theo email cho ra kết quả.

### 8.4. User store tạm thời unavailable

Một timeout database không chứng minh người dùng đã bị xóa. Nếu mapper đổi timeout thành **invalid_token**, client có thể xóa session hoặc buộc login lại hàng loạt trong một outage.

Nên tách exception:
- **UserNotFoundException** hoặc **UserDisabledException**: policy có thể ánh xạ thành **invalid_token**.
- **UserDirectoryUnavailableException**: ánh xạ thành HTTP 503, thêm **Retry-After** phù hợp.
- **DataIntegrityException**: fail request, alert và điều tra; không trả claims không đáng tin.

**OidcUserInfoEndpointConfigurer.errorResponseHandler(...)** là hook xử lý **OAuth2AuthenticationException**. Nếu ứng dụng cần trả 503 cho lỗi user store, hãy chuyển lỗi hạ tầng thành một OAuth2AuthenticationException có mã nội bộ đã quy ước rồi triển khai handler ánh xạ mã đó thành HTTP 503. Giữ serialization chuẩn cho lỗi Bearer/OAuth2 còn lại. Không chuyển mọi exception thành 401.

## 9. ID Token snapshot và UserInfo động

Có hai chiến lược lấy profile.

### 9.1. Dùng claims từ ID Token

Default mapper của Spring Authorization Server sử dụng claims đã được đưa vào ID Token và lọc theo scope đã yêu cầu/cấp.

Ưu điểm:
- Response nhất quán với thông tin tại thời điểm đăng nhập.
- Ít truy vấn database tại UserInfo.
- Ít phụ thuộc vào user directory khi client gọi endpoint.
- Dễ scale khi traffic cao.

Nhược điểm:
- Profile có thể stale sau khi user đổi tên/email.
- User bị khóa sau khi phát token có thể vẫn còn claims snapshot nếu trạng thái access token chưa bị invalidated.
- Không thích hợp nếu nghiệp vụ yêu cầu profile luôn phản ánh dữ liệu hiện tại.

### 9.2. Truy vấn hồ sơ hiện tại bằng custom mapper

Custom mapper truy vấn user directory theo stable **sub** và dựng response ở thời điểm request.

Ưu điểm:
- Dữ liệu profile mới hơn.
- Có thể phát hiện user disabled/deleted.
- Có thể áp privacy policy và claim visibility hiện tại.

Nhược điểm:
- Tăng latency và phụ thuộc database/LDAP.
- Cần timeout, circuit breaker, cache và lỗi 503.
- Có thể làm UserInfo response khác với ID Token snapshot.
- Phải đảm bảo **sub** vẫn khớp ID Token và không bị remap.

### 9.3. Không cache tùy tiện profile và trạng thái tài khoản

Nếu UserInfo cache response trong nhiều phút, email/role/privacy state có thể stale. Nếu cache cả trạng thái active của user, một user vừa bị disable có thể tiếp tục lấy profile.

Nếu cache:
- Cache key phải chứa issuer, subject, tenant và profile version.
- TTL phù hợp với độ nhạy dữ liệu.
- Invalidate khi profile thay đổi, user disable/delete hoặc consent bị revoke.
- Không cache lỗi **invalid_token** dài hạn theo raw token.
- Không cache 503 như trạng thái user disabled.
- Không cache access token hoặc UserInfo response vào shared cache thiếu encryption/access control.

## 10. Cấu hình error handling và deprovisioning

### 10.1. Phân loại lỗi ở domain service

Ví dụ contract:

~~~java
public class UserDisabledException extends RuntimeException {
    public UserDisabledException() {
        super("User is not available");
    }
}

public class UserDirectoryUnavailableException extends OAuth2AuthenticationException {
    public UserDirectoryUnavailableException() {
        super(new OAuth2Error(
                "temporarily_unavailable",
                "User directory is temporarily unavailable",
                null));
    }
}
~~~

Đây là exception do ứng dụng định nghĩa; snippet cần import **OAuth2AuthenticationException** và **OAuth2Error**. Mapper hoặc adapter của user directory có thể ném exception này khi backend tạm thời không truy cập được. Không chứa email, username hoặc raw token trong message vì message có thể xuất hiện ở log hoặc telemetry.

Mapper có thể chuyển user disabled/deleted thành OAuth2 **invalid_token**. Lỗi user directory cần được nhận diện riêng để error handler trả 503.

### 10.2. errorResponseHandler là extension point

Ví dụ vị trí cấu hình:

~~~java
.oidc(oidc -> oidc
    .userInfoEndpoint(userInfo -> userInfo
        .userInfoMapper(userInfoMapper)
        .errorResponseHandler(userInfoFailureHandler)
    )
)
~~~

**userInfoFailureHandler** là **AuthenticationFailureHandler** do ứng dụng cung cấp. Nó cần:

- Giữ cách trả Bearer error chuẩn cho **OAuth2AuthenticationException** như **invalid_token** và **insufficient_scope**.
- Map lỗi user directory tạm thời thành HTTP 503, **Retry-After** và body không tiết lộ chi tiết nội bộ.
- Không trả stack trace hoặc SQL/LDAP exception cho client.
- Ghi metric/audit theo category đã chuẩn hóa.
- Không log access token hoặc toàn bộ UserInfo response.

Nếu thay handler mặc định, kiểm thử cả header **WWW-Authenticate**, status code, content type và response body. Không làm mất error semantics của RFC 6750.

Trong handler tùy chỉnh, giữ nguyên Bearer challenge và error body cho các lỗi token/scope; chỉ map lỗi user-directory infrastructure sang 503. Nếu không cần thay đổi status/format, giữ handler mặc định và xử lý lỗi hạ tầng qua một adapter có kiểm thử riêng.

### 10.3. Deprovisioning phải thu hồi cả refresh path

Chỉ trả **invalid_token** tại UserInfo không tự ngăn client dùng refresh token để lấy access token mới. Khi user bị khóa/xóa, lifecycle service cần revoke authorization/refresh token tương ứng và ngăn cấp token mới.

Với access token JWT mà Resource Server xác minh offline, trạng thái revoke tại Authorization Server không tự truyền tới API. Cần lựa chọn:
- Introspection hoặc online state check.
- Denylist theo **jti**.
- Session/user token version.
- TTL ngắn trong residual window đã chấp nhận.
- Dynamic authorization check ở API nhạy cảm.

UserInfo là một endpoint; deprovisioning phải áp dụng nhất quán cho các Resource Server khác nếu yêu cầu bảo mật là khóa user ngay lập tức.

## 11. Kiểm thử UserInfo endpoint

### 11.1. Ma trận token

| Test case | Kết quả mong đợi |
|---|---|
| Access token hợp lệ, active, có **openid** | 200 và **sub** luôn có. |
| Không có Authorization header | 401 Bearer challenge, không lộ chi tiết. |
| Token malformed | 401 **invalid_token**. |
| Token hết hạn | 401 **invalid_token**. |
| Token bị revoke/invalidate | 401 **invalid_token** nếu state được endpoint kiểm tra. |
| Token sai issuer/signature/audience theo policy | 401 **invalid_token**. |
| Token không có scope **openid** | Từ chối theo policy, thường **insufficient_scope** (403). |
| Token có **openid profile** | Có **sub** và profile claims được phép. |
| Token có **openid email** | Có **sub** và email claims nếu có dữ liệu/được phép. |
| Token chỉ có **openid** | Chỉ cần **sub**; không trả profile/email ngoài scope. |

### 11.2. Ma trận profile và scope

| User data | Scope | Kết quả |
|---|---|---|
| Có tên và email | **openid profile email** | Có thể trả **sub**, profile claims, email claims. |
| Không có email | **openid email** | 200, **sub**; bỏ **email** và **email_verified**. |
| Có email nhưng không có email scope | **openid profile** | Không trả email. |
| Email bị privacy policy ẩn | **openid email** | 200, bỏ email claims. |
| Không có profile fields | **openid profile** | 200, tối thiểu **sub**. |
| User active nhưng phone không có | **openid phone** | 200, bỏ phone claims. |
| Mapper trả **sub** khác ID Token | Bất kỳ scope hợp lệ | Client discard toàn bộ UserInfo response. |

### 11.3. Ma trận user lifecycle và hạ tầng

| Test case | Kết quả mong đợi |
|---|---|
| User active | 200, claims theo scope. |
| User bị disable | Authorization/refresh token bị xử lý theo deprovisioning; UserInfo từ chối bằng **invalid_token**. |
| User bị delete | Không remap sang user khác; token cũ không còn lấy profile. |
| User đổi email | **sub** không đổi; email mới theo mapper động hoặc snapshot policy đã chọn. |
| User merge sang subject mới | Không tự thay **sub** trong UserInfo của token cũ. |
| User directory timeout | 503, **Retry-After**; không đánh dấu token invalid. |
| User directory trả record không nhất quán | Fail request, alert; không phát **sub** không đúng. |
| Authorization store unavailable | Không chấp nhận token khi không thể xác minh state theo policy; xử lý lỗi dịch vụ. |
| UserInfo response cache còn cũ sau disable | Invalidation/TTL phải nằm trong revocation SLA. |

### 11.4. Ví dụ MockMvc kiểm tra token lỗi

Mẫu test minh họa:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class UserInfoEndpointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void expiredTokenIsRejected() throws Exception {
        mvc.perform(get("/userinfo")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer EXPIRED_TEST_ACCESS_TOKEN"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                    HttpHeaders.WWW_AUTHENTICATE,
                    containsString("invalid_token")));
    }

    @Test
    void validTokenWithoutEmailScopeDoesNotExposeEmail()
            throws Exception {
        mvc.perform(get("/userinfo")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer OPENID_PROFILE_ONLY_TOKEN"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sub").value("user-42"))
            .andExpect(jsonPath("$.email").doesNotExist());
    }
}
~~~

Đây là test mẫu; cần fixture tạo JWT, JWK, authorization, user profile và scope thật. Không dùng token giả lập trong production. Với expired token, cần tạo JWT có **exp** trong quá khứ hoặc fixture authorization đã hết hạn; với case thiếu email, access token phải hợp lệ và chỉ có scope **openid profile**.

### 11.5. Kiểm tra subject binding phía Client

Integration test nên:
1. Nhận ID Token từ Token Endpoint.
2. Xác minh chữ ký, issuer, audience, expiry và nonce.
3. Gọi UserInfo bằng access token.
4. Đọc **sub** từ UserInfo.
5. So sánh chính xác với **sub** trong ID Token.
6. Nếu khác hoặc thiếu, discard toàn bộ claims.
7. Kiểm tra client không ghi profile response chưa xác minh vào session/database.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| UserInfo trả 401 cho token vừa cấp | Token không đúng issuer/audience, decoder/JWK sai hoặc authorization không được lưu đúng. | Kiểm **JwtDecoder**, issuer, JWK và authorization persistence. |
| Token expired trả 200 | Mapper/controller bỏ qua token validation. | Giữ filter/provider chuẩn và kiểm expiration. |
| Token revoke nhưng UserInfo vẫn trả profile | State revocation không được kiểm hoặc custom path bypass provider. | Kiểm **OAuth2AuthorizationService**, token active state và provider chain. |
| Thiếu email scope nhưng response vẫn có email | Custom mapper trả toàn bộ profile không lọc scope. | Chỉ map email khi access token có **email**. |
| Thiếu email nhưng endpoint trả 403 | Nhầm optional claim absence với insufficient scope. | Bỏ claim không có/không được phép; chỉ 403 cho scope bắt buộc. |
| User bị disable nhưng profile cũ vẫn trả | Default mapper lấy claims snapshot trong ID Token hoặc custom mapper không kiểm user state. | Thêm deprovisioning và mapper động nếu yêu cầu trạng thái hiện tại. |
| User directory outage bị trả 401 | Exception hạ tầng bị chuyển thành invalid token. | Tách exception và trả 503. |
| UserInfo sub khác ID Token | Subject mapping không ổn định hoặc ghép nhầm token/session. | Dùng immutable subject và client-side sub check. |
| UserInfo thiếu sub | Mapper custom quên claim bắt buộc. | Luôn đặt sub trước khi thêm claims tùy chọn. |
| Response có null/empty fields | Mapper serialize tất cả thuộc tính dù không có giá trị. | Omit claim không có giá trị. |
| Client dùng token qua query string | SDK/custom client gọi sai cách. | Dùng Authorization Bearer qua TLS. |
| Opaque token không hoạt động với UserInfo mặc định | Giả định endpoint SAS hỗ trợ cùng cấu hình như generic opaque resource server. | Kiểm JwtDecoder requirement và thiết kế custom integration theo version. |
| Profile cache vẫn có dữ liệu sau disable | Cache chưa invalidated hoặc TTL quá dài. | Purge theo event, giảm TTL và kiểm tra cache key. |
| UserInfo trả claims vượt scope | Mapper không kiểm scope thực tế. | Dựa trên scopes của access token và privacy policy. |
| User bị xóa rồi tạo mới cùng email nhận dữ liệu cũ | Dùng email làm subject/lookup key. | Dùng stable subject, không tái sử dụng sub. |
| API client tự tin UserInfo mà không kiểm sub | Bỏ bước chống token substitution. | Luôn đối chiếu UserInfo sub với ID Token sub. |

## 13. Bài tập thực hành

**Bối cảnh:** Authorization Server phục vụ **employee-portal**, **mobile-app** và **partner-console**. Ba client có các scope khác nhau. Một người dùng bị khóa sau khi đã nhận access token còn hạn; đồng thời user directory có một đợt gián đoạn ngắn.

### Yêu cầu

1. Bật OIDC UserInfo endpoint và cấu hình **JwtDecoder** đúng với JWK source.
2. Dùng default mapper để xác minh behavior scope-to-claims trước khi tùy chỉnh.
3. Tạo **UserDirectory** lookup theo immutable **sub**, không theo email.
4. Viết custom mapper trả **sub** bắt buộc và lọc claims theo **openid**, **profile**, **email**, **address**, **phone**.
5. Kiểm tra token thiếu **openid**, token expired, revoked và token có audience/issuer sai.
6. Khi user không có email, trả response không có **email/email_verified**, không trả null/empty.
7. Khi user bị disabled/deleted, revoke authorization/refresh token theo policy và trả **invalid_token**.
8. Khi user directory timeout, trả 503 và **Retry-After**; không revoke token do lỗi hạ tầng.
9. Đảm bảo client kiểm tra UserInfo **sub** bằng ID Token **sub**.
10. Test profile update: email thay đổi nhưng **sub** giữ nguyên.
11. Test account merge/deletion: không remap subject cũ sang user mới.
12. Test response cache, event invalidation và nhiều Authorization Server instance.
13. Kiểm logs không có raw access token, email hoặc toàn bộ UserInfo body.
14. Đo latency và tỷ lệ lỗi của UserInfo endpoint theo từng category.

**Tiêu chí hoàn thành:** token lỗi nhận **invalid_token**; scope bắt buộc thiếu nhận **insufficient_scope**; claim tùy chọn không có được omit; user disabled/deleted bị deprovision; user store outage trả 503; **sub** luôn đúng và client kiểm tra khớp ID Token.

## 14. Checklist trước khi triển khai production

- [ ] UserInfo endpoint chỉ hoạt động qua HTTPS/TLS.
- [ ] Client gửi access token bằng Authorization Bearer, không dùng query string.
- [ ] Endpoint hỗ trợ GET và POST theo OIDC Core.
- [ ] Client lấy **userinfo_endpoint** từ Provider Metadata đã xác minh.
- [ ] **JwtDecoder** và JWK/issuer được cấu hình đúng cho Spring Authorization Server.
- [ ] Token phải hợp lệ, chưa hết hạn và chưa bị revoke theo state policy.
- [ ] **invalid_token** trả 401 và Bearer challenge phù hợp.
- [ ] **insufficient_scope** trả 403 chỉ khi scope thật sự bắt buộc.
- [ ] Scope tùy chọn thiếu không làm request thất bại; claims tương ứng được bỏ qua.
- [ ] **sub** luôn có và ổn định.
- [ ] Client so sánh UserInfo **sub** với ID Token **sub**; mismatch thì discard response.
- [ ] Claims được lọc theo scope thực tế của access token.
- [ ] Claim không có giá trị bị omit, không trả null/empty.
- [ ] PII chỉ được trả theo consent, scope và privacy policy.
- [ ] User disabled/deleted kích hoạt deprovisioning và revoke authorization/refresh token.
- [ ] Không remap subject cũ sang user mới khi email/username thay đổi.
- [ ] User directory outage trả 503, không biến thành invalid token.
- [ ] Cache có TTL/invalidation phù hợp với profile update và deprovisioning SLA.
- [ ] Error handler không tiết lộ SQL, LDAP, user existence hoặc token details.
- [ ] Logs/traces không chứa raw access token, UserInfo body hoặc PII không cần thiết.
- [ ] Đã test JWT expiry/revocation, scope, missing user, disabled user và database outage.
- [ ] Đã test nhiều instance, restart, cache invalidation và subject mismatch.
- [ ] Đã kiểm tra hành vi đúng với Spring Authorization Server version thực tế.

## Tổng kết

OIDC UserInfo Endpoint phải xử lý riêng **tính hợp lệ của access token**, **scope được cấp**, **claims thực sự có thể tiết lộ** và **trạng thái hiện tại của End-User**. RFC 6750 quy định **invalid_token** là 401 và **insufficient_scope** là 403; OIDC Core cho phép bỏ claim tùy chọn không có/không được tiết lộ nhưng bắt buộc UserInfo Response phải có **sub**. Client phải đối chiếu **sub** đó với ID Token và discard response nếu không khớp.

Spring Authorization Server 1.5.8 cung cấp **OidcUserInfoAuthenticationProvider**, **OidcUserInfoAuthenticationContext** và **OidcUserInfoEndpointConfigurer.userInfoMapper(...)**. Default mapper lấy standard claims từ ID Token theo scope; custom mapper có thể lấy profile hiện tại nhưng phải tự giữ scope filtering, subject stability, privacy và error semantics. Khi user bị disable/deleted, hệ thống cần deprovision authorization/refresh tokens và từ chối token theo policy; khi user directory chỉ tạm thời unavailable, trả lỗi dịch vụ 503 thay vì kết luận token invalid.

Bài toán chỉ hoàn chỉnh khi test được toàn bộ đường đi từ access token, authorization state, user directory đến UserInfo response và client-side sub validation.

## Tài liệu tham khảo

1. [OpenID Connect Core 1.0 incorporating errata set 2 — Section 5.3 UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html): UserInfo request, TLS, GET/POST, Bearer token, sub, successful response, error response và response validation.
2. [OpenID Connect Core 1.0 — Section 5.4 Requesting Claims using Scope Values](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims): claims được yêu cầu bằng profile, email, address, phone.
3. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): invalid_token, insufficient_scope, HTTP 401/403 và WWW-Authenticate.
4. [Spring Authorization Server 1.5.8 — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): enable endpoint, default claims, custom ID Token và custom mapper.
5. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OidcUserInfoEndpointConfigurer, converter, provider, mapper và response/error handlers.
6. [Spring Authorization Server 1.5.8 — OidcUserInfoAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcUserInfoAuthenticationProvider.html): provider và setUserInfoMapper.
7. [Spring Authorization Server 1.5.8 — OidcUserInfoEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcUserInfoEndpointConfigurer.html): extension points cho UserInfo endpoint.
8. [Spring Authorization Server 1.5.8 — OidcUserInfoAuthenticationContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcUserInfoAuthenticationContext.html): access token và authorization context.
9. [Spring Authorization Server 1.5.8 — OAuth2Authorization API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.html): authorization, token và scopes.
10. [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): authorization model, token state, scope và token lifecycle.
11. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và cách Resource Server xử lý access token.
12. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Metadata và userinfo_endpoint.

