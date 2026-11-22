# 27.9. Quản lý consent, incremental authorization và tái xác thực

## 1. Vì sao cần quản lý consent sau khi người dùng đã đăng nhập?

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client**, đăng nhập thành công chưa đồng nghĩa ứng dụng đã được phép sử dụng tất cả API của một provider, và một phiên đăng nhập còn hiệu lực chưa chắc đủ mới hoặc đủ mạnh để thực hiện tác vụ nhạy cảm.

Ví dụ một cổng làm việc:

```text
09:00 Người dùng đăng nhập OIDC
      scope: openid profile email
      -> xem dashboard và hồ sơ

09:20 Người dùng chọn "Đồng bộ lịch"
      -> ứng dụng xin thêm calendar.readonly
      -> IdP hiển thị consent nếu cần
      -> ứng dụng nhận authorization mới

10:00 Người dùng chọn "Đổi thông tin thanh toán"
      -> ứng dụng yêu cầu tái xác thực
      -> xác minh auth_time, assurance và internal policy
      -> chỉ sau đó cho phép đổi dữ liệu
```

Có ba quyết định **khác nhau**:

1. **Authentication:** Ai đang sử dụng ứng dụng? Người đó đã được xác thực khi nào và bằng phương pháp nào?
2. **OAuth2 authorization/consent:** Người dùng và Authorization Server (AS) đã cho phép **OAuth2 client** truy cập tài nguyên nào với scopes nào?
3. **Business authorization:** Internal account hiện tại có quyền thực hiện nghiệp vụ, ví dụ xem lịch hoặc chỉnh sửa thanh toán, hay không?

**Consent** không thay thế authentication; **re-authentication** không tự cấp scopes mới; và access token có scopes phù hợp cũng **không thay business authorization** của Resource Server.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt consent screen, OAuth2 scopes, granted authorization, roles và application preferences.
- Thiết kế **incremental authorization**: chỉ xin thêm quyền khi người dùng sử dụng tính năng cần quyền đó.
- Hiểu incremental authorization thường dùng lại **Authorization Code Flow**, không phải một OAuth2 grant type mới.
- Tùy chỉnh authorization request trong Spring Security bằng `OAuth2AuthorizationRequestResolver`.
- Dùng đúng `prompt=consent`, `prompt=login`, `max_age`, `auth_time`, `acr_values` và `amr`.
- Hiểu khác biệt giữa OIDC reauthentication, MFA/step-up và việc làm mới Spring Security session.
- Đưa OAuth2 `state`, PKCE, OIDC `nonce`, CSRF và account binding vào luồng nâng quyền.
- Kiểm soát `OAuth2AuthorizedClient` và access/refresh tokens sau khi phạm vi được mở rộng.
- Xử lý denied consent, partial scopes, `invalid_grant`, `insufficient_scope`, 401/403 và hết hạn phiên.
- Thiết kế BFF không tiết lộ raw tokens ra trình duyệt.
- Kiểm thử cả tình huống thành công lẫn những lỗi quyền và lỗi nhầm identity.

Mọi domain, client ID, token và scope trong ví dụ đều giả lập. Các đoạn mã chính hướng đến **Spring Security OAuth2/OIDC Client trên Servlet/MVC**; WebFlux có phần riêng. Tên scope của các API là ví dụ; phải đối chiếu provider thật trước khi triển khai.

---

## 2. Bốn lớp quyền: đừng trộn vào một khái niệm

| Lớp | Nơi quyết định chính | Ví dụ |
|---|---|---|
| **Authentication** | OIDC Provider/Spring Security | `sub=alice`, `auth_time=...` |
| **OAuth2 consent/authorization grant** | Authorization Server, người dùng và client policy | Client được phép dùng `calendar.readonly` |
| **Access token scopes/audience** | AS phát hành; Resource Server xác minh | Token có `aud=calendar-api`, `scope=calendar.readonly` |
| **Business authorization** | Ứng dụng/Resource Server | Alice chỉ được xem lịch thuộc tenant A |

Một access token có `calendar.readonly` không đủ chứng minh Alice được xem lịch riêng của Bob. Ngược lại, Alice có vai trò admin trong SaaS cũng không thể dùng API của provider nếu client chưa được AS cấp access token phù hợp.

### 2.1. Đăng nhập không bằng đồng ý truy cập mọi tài nguyên

OIDC Login thường bắt đầu với:

```text
scope=openid profile email
```

Các scopes này liên quan đến xác thực và profile claims. Chúng không tự cấp quyền:

```text
calendar.readonly
drive.file
billing.write
```

Các API permissions cần được xin qua OAuth2 authorization của **đúng provider, client, audience và tài nguyên**.

### 2.2. Consent khác một màn hình "Tôi đồng ý điều khoản"

Cần phân biệt:

- **OAuth2 authorization consent:** Người dùng cho client quyền truy cập API/resource qua AS.
- **Terms of Service acceptance:** Chấp nhận điều khoản của ứng dụng.
- **Privacy preferences:** Cấu hình lựa chọn xử lý dữ liệu tại ứng dụng.
- **Business approval:** Người quản trị cấp role hoặc duyệt giao dịch.
- **Step-up authentication:** Người dùng chứng minh lại danh tính hoặc mức assurance trước thao tác nhạy cảm.

Không thay OAuth2 consent của provider bằng một checkbox trong ứng dụng rồi coi như đã có access token.

### 2.3. Consent không phải yếu tố được thể hiện đầy đủ bởi `Authentication`

Một `OAuth2AuthenticationToken` cho biết user đã đăng nhập, nhưng không đảm bảo authorized client có mọi scope cần thiết. Cần kiểm tra **access token thực tế** và authorization state.

---

## 3. Consent thuộc quyền kiểm soát của ai?

Một Authorization Server quản lý việc cấp authorization dựa trên:

```text
End-User
    +
OAuth2 client
    +
Requested scopes/resources
    +
AS policy, administrator policy và consent history
```

AS có thể:

- Hiển thị consent screen lần đầu.
- Bỏ qua màn hình nếu consent đã được lưu.
- Bắt consent lại khi xin thêm scopes.
- Từ chối quyền bị tổ chức chặn.
- Chỉ cấp một phần quyền yêu cầu nếu provider hỗ trợ granular consent.
- Yêu cầu admin consent hoặc ứng dụng đã được verification.
- Không cấp refresh token dù user đã đồng ý.

**Spring Security không có khả năng ép AS cấp quyền chỉ bằng việc thêm scope vào request.** Client chỉ có thể **yêu cầu**; AS và user/policy quyết định cấp gì.

### 3.1. Những gì ứng dụng nên lưu

Ứng dụng có thể lưu **metadata nghiệp vụ** để giải thích trạng thái:

```text
internalUserId
providerRegistrationId
feature = CALENDAR_SYNC
consentFlowStatus = CONNECTED / NEEDS_CONSENT / REVOKED
lastSuccessfulAuthorizationAt
authorizedClientReference
```

Nhưng trạng thái `CONNECTED` trong DB **không phải nguồn chân lý tuyệt đối** về token hiện còn hợp lệ. Consent có thể bị thu hồi trực tiếp tại provider mà ứng dụng chưa nhận được thông báo.

### 3.2. Authorization Server là nơi phát token

Không thể tự tạo:

```json
{
  "scope": "calendar.readonly"
}
```

trong một JWT hoặc session attribute của ứng dụng rồi tuyên bố API provider đã cho phép.

Token phải được AS đáng tin phát hành, có audience/scope/issuer đúng và được Resource Server kiểm tra.

---

## 4. Incremental authorization là gì?

**Incremental authorization** (cấp quyền tăng dần) là chiến lược **chỉ yêu cầu thêm quyền khi chức năng cụ thể cần sử dụng**, thay vì yêu cầu tập scopes lớn ngay lúc đăng nhập.

Ví dụ:

```text
Lần 1: User sign in
    openid profile

Lần 2: User bấm "Kết nối lịch"
    calendar.readonly

Lần 3: User bấm "Tạo sự kiện"
    calendar.events.write
```

Không nhất thiết ba lần cấp quyền này tạo ra ba access tokens cùng tồn tại. Provider có thể hợp nhất granted scopes trong một authorization, phát token mới có scopes kết hợp, hoặc xử lý token/refresh token khác nhau theo contract.

### 4.1. Vì sao tốt hơn xin tất cả lúc đầu?

- User thấy quyền được xin **đúng ngữ cảnh sử dụng**.
- Giảm quyền không cần thiết của ứng dụng.
- Giảm trở ngại khi onboarding.
- Hỗ trợ nguyên tắc least privilege.
- Dễ giải thích tác động khi user từ chối.
- Cho phép các tính năng không cần quyền nhạy cảm hoạt động bình thường.

### 4.2. Incremental authorization không phải một grant type mới

OAuth2 không có:

```text
grant_type=incremental_authorization
```

cho mô hình phổ biến này.

Thông thường, application **khởi tạo một Authorization Code Flow mới**, lần này yêu cầu scopes mới hoặc kết hợp những scopes đã có, với các provider-specific parameters nếu cần.

Ví dụ authorization request giả lập:

```http
GET /authorize?
    response_type=code
    &client_id=portal-client
    &redirect_uri=https%3A%2F%2Fportal.example%2Flogin%2Foauth2%2Fcode%2Fcorporate
    &scope=openid%20profile%20calendar.readonly
    &state=RANDOM_STATE
    &code_challenge=RANDOM_PKCE_CHALLENGE
    &code_challenge_method=S256
```

Phần line-break chỉ để trình bày; URL thực tế phải URL-encode chuẩn và thuộc client registration đã được AS chấp nhận.

### 4.3. OAuth2 client phải biết token nào đã được cấp quyền gì

Không suy:

```text
Tôi vừa xin calendar.readonly
    => Token trả về chắc chắn có calendar.readonly
```

AS có thể trả:

- Tập scopes được cấp như mong muốn.
- Một tập con.
- Một tập scopes khác theo chính sách.
- Lỗi `access_denied` hoặc policy error.

Client cần xem **scope grant thực tế** và bảo vệ feature tương ứng.

---

## 5. Ví dụ xuyên suốt: dashboard, lịch và thanh toán

Giả sử ứng dụng `https://portal.example` sử dụng OIDC Provider:

```text
Issuer: https://login.example-idp.com
Client registration: corporate
Client ID: portal-bff
```

Tính năng:

| Tính năng | Quyền OAuth2 cần xin | Yêu cầu xác thực |
|---|---|---|
| Xem dashboard | `openid profile` | OIDC Login |
| Xem lịch | `calendar.readonly` | Consent khi dùng lần đầu |
| Tạo lịch | `calendar.events.write` | Consent bổ sung |
| Xem giao dịch nội bộ | Local role và API policy | Phiên hợp lệ |
| Đổi tài khoản nhận thanh toán | Không nhất thiết cần scope mới | Re-authentication mới, có thể MFA |
| Export dữ liệu riêng tư | Scopes theo API và local policy | Có thể vừa consent vừa step-up |

Một thao tác có thể yêu cầu **cả hai**:

```text
Consent for calendar.write
    +
Reauthentication with stronger assurance
```

Chúng là hai kiểm tra độc lập. Nếu đạt reauthentication nhưng AS từ chối `calendar.write`, không được gọi API. Nếu đã có scope nhưng người dùng chưa vượt step-up policy, cũng không được thực hiện thao tác nhạy cảm.

---

## 6. Luồng xin thêm scope

```mermaid
sequenceDiagram
    autonumber
    actor U as User / Browser
    participant BFF as Spring Boot OAuth2 Client
    participant S as Session + Pending Intent Store
    participant AS as Authorization Server
    participant API as Calendar API

    U->>BFF: POST /api/connections/calendar/authorize
    Note over BFF: Verify session, CSRF, current account, feature policy
    BFF->>S: Save pending consent intent for account U
    BFF-->>U: Return safe same-origin authorization start URL
    U->>BFF: GET /oauth2/authorization/corporate
    BFF->>S: Bind intent to OAuth2 state, registration, scopes
    BFF-->>U: 302 /authorize with additional calendar.readonly scope + PKCE
    U->>AS: Authenticate/consent as required
    AS-->>U: Redirect code + state, or error
    U->>BFF: GET /login/oauth2/code/corporate
    BFF->>S: Validate state, PKCE, pending consent intent
    BFF->>AS: POST /token with authorization_code
    AS-->>BFF: Access token with granted scopes; refresh token if issued
    BFF->>BFF: Validate same intended user and scope outcome
    BFF->>S: Store/reconcile OAuth2AuthorizedClient
    BFF-->>U: Redirect /settings/calendar?result=connected
    U->>BFF: GET /api/calendar
    BFF->>API: Bearer token for Calendar API
    API-->>BFF: Calendar data
    BFF-->>U: Business JSON, no raw OAuth tokens
```

### 6.1. Không bắt đầu bằng redirect tùy ý từ frontend

Nên có một **server-side feature-to-scope policy**:

```text
CALENDAR_READ -> calendar.readonly
CALENDAR_WRITE -> calendar.events.write
```

Frontend có thể chọn feature:

```json
{"feature":"CALENDAR_READ"}
```

nhưng **không được cung cấp arbitrary scopes**, issuer URI hoặc redirect URI rồi bắt BFF đưa nguyên chúng tới Authorization Server.

### 6.2. Yêu cầu consent phải có intent rõ ràng

Pending intent server-side nên chứa:

```text
intentId: opaque, random
internalUserId: stable local account ID
tenantId: validated tenant
registrationId: corporate
feature: CALENDAR_READ
approvedScopes: [calendar.readonly]
createdAt: ...
expiresAt: ...
consumed: false
expectedExternalIdentity: verified issuer+subject, nếu đã biết
oauthStateBinding: set during authorization request
```

Không để `intent` tồn tại vô hạn. Sau callback, validate, consume atomically và xử lý nếu user logout, session đổi hoặc flow bị bắt đầu ở một tab khác.

### 6.3. Login callback và consent callback có thể cùng URL

Spring Security OAuth2 Login thường xử lý:

```text
/login/oauth2/code/{registrationId}
```

Cho cả sign-in ban đầu và interactive reauthorization, nếu application dùng cùng `oauth2Login()` pipeline.

Vì vậy, callback handler phải phân biệt:

- **Initial login**.
- **Additional-scope consent** của user đã đăng nhập.
- **Reauthentication/step-up**.
- **Account linking** nếu ứng dụng còn hỗ trợ.

Không suy từ query parameter `?action=consent` mà thiếu server-side state/session binding.

---

## 7. `prompt=consent` khác `scope` bổ sung thế nào?

Trong OIDC, tham số:

```text
prompt=consent
```

yêu cầu OpenID Provider hiển thị interaction để người dùng cấp consent theo protocol và policy của nó.

Nhưng để xin quyền API mới, điều cốt lõi vẫn là **tập scopes cần thiết**:

```text
scope=openid profile calendar.readonly
```

Hai tham số có tác dụng khác nhau:

| Thành phần | Mục đích |
|---|---|
| `scope` | Diễn đạt những quyền/claims/tài nguyên client muốn xin |
| `prompt=consent` | Yêu cầu provider tương tác với user để xác nhận consent |
| `prompt=login` | Yêu cầu xác thực lại End-User |
| `prompt=select_account` | Yêu cầu chọn tài khoản provider |
| `prompt=none` | Không hiển thị UI; nếu cần interaction, provider trả lỗi |
| `max_age` | Giới hạn độ cũ authentication tại OP |
| `acr_values` | Thông báo authentication context classes được yêu cầu theo hợp đồng OP |

**Không gửi `prompt=consent` mỗi lần gọi API.** Nó là authorization endpoint parameter trong một interactive authorization request, không phải header của Resource Server.

### 7.1. `prompt=consent` có phải luôn xuất hiện màn hình?

OIDC xác định semantics của prompt, nhưng hành vi thực tế phụ thuộc provider và policy/khả năng interaction. Một số provider có thể hiển thị màn hình, một số trả lỗi hoặc có chính sách admin consent riêng.

Đừng thiết kế business logic dựa trên giả định “người dùng chắc chắn đã nhìn thấy đúng dialog” khi không có chứng cứ provider và kết quả authorization phù hợp.

### 7.2. `prompt=consent` không cấp quyền vượt chính sách

AS có thể từ chối `calendar.events.write` nếu client chưa được phép xin scope hoặc tenant administrator chặn quyền này. Bắt consent lại không làm bypass AS policy.

---

## 8. Ví dụ riêng của Google: `include_granted_scopes`

Theo tài liệu Google OAuth2, một authorization request có thể dùng:

```text
include_granted_scopes=true
```

để hỗ trợ **incremental authorization** của Google.

Ví dụ ý tưởng:

```text
GET https://accounts.google.com/o/oauth2/v2/auth
  ?client_id=...
  &response_type=code
  &scope=openid%20profile%20https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcalendar.readonly
  &include_granted_scopes=true
  &state=...
  &redirect_uri=...
  &code_challenge=...
  &code_challenge_method=S256
```

Google có thể kết hợp granted scopes trước đó với scopes mới theo policy của Google.

### 8.1. Không áp tham số Google cho mọi OIDC Provider

`include_granted_scopes` **không phải một tham số chuẩn bắt buộc của mọi OpenID Provider**. Với một provider enterprise, nó có thể bị bỏ qua hoặc trả `invalid_request`.

Cần strategy theo registration:

```text
registration google:
    include_granted_scopes=true

registration corporate:
    chỉ gửi các tham số OIDC/RFC/provider docs cho phép
```

### 8.2. Đừng giả định Google luôn trả refresh token mới

Khi consent/reauthorization bổ sung, Google không bảo đảm mọi lần code exchange đều trả một refresh token mới. Ứng dụng phải giữ/rotate token theo provider contract và không xóa refresh token cũ chỉ vì response mới thiếu field đó, trừ khi policy/SDK quy định rõ.

### 8.3. `access_type=offline` cũng là provider-specific

Trong Google OAuth2 web-server flow, `access_type=offline` liên quan khả năng xin refresh token. Nó không phải một tham số universal được mọi Authorization Server hiểu.

Đừng dùng một customizer chung tự thêm `access_type=offline` vào tất cả registrations.

---

## 9. Phần nào Spring Security tự quản lý, phần nào ứng dụng phải viết?

Spring Security OAuth2 Client có thể:

- Dựng authorization request từ `ClientRegistration`.
- Tạo và kiểm tra `state`.
- Thêm PKCE theo config/customizer phù hợp.
- Xử lý redirect và authorization code.
- Gọi Token Endpoint.
- Xác thực OIDC ID Token theo cấu hình.
- Tạo `OAuth2AuthenticationToken`/`OidcUser`.
- Lưu `OAuth2AuthorizedClient` theo repository/service.
- Refresh access token khi provider/manager cho phép.
- Tích hợp token với `RestClient`/`WebClient`.

Nhưng ứng dụng phải tự quyết định:

- Feature nào cần scope nào.
- User có **chủ động** xin quyền bổ sung không.
- Consent intent thuộc account/tenant nào.
- Đối chiếu ID Token sau callback có phải cùng user không.
- Scope nào thực sự được cấp và đã đủ cho feature chưa.
- Tái xác thực bao nhiêu phút là đủ mới.
- Level MFA/ACR nào đáp ứng rủi ro nghiệp vụ.
- Logout/disconnect/revocation và consent status được trình bày thế nào.
- Cần lưu nhiều authorized clients/registrations khác nhau hay không.

**Không có một `incrementalAuthorization()` switch phổ quát** tự làm trọn mọi quy tắc trên.

---

## 10. Cấu hình OIDC Login cơ bản trong Spring Boot

Ví dụ Spring Boot 3.x / Spring Security Servlet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-idp:
            issuer-uri: https://login.example-idp.com
```

Scoping ban đầu chỉ dành cho login/profile. Một API cần `calendar.readonly` sẽ dẫn đến **interactive consent request** riêng sau đó nếu user chọn tính năng.

**Không thêm mọi scope nhạy cảm vào login registration chỉ để tránh thiết kế incremental authorization.**

### 10.1. Redirect URI phải thuộc BFF hoặc client theo kiến trúc

Với BFF:

```text
https://portal.example/login/oauth2/code/corporate
```

là callback của **Spring Security backend**, không phải một arbitrary frontend route hay host do người dùng nhập.

### 10.2. Client secret ở backend

Không đưa `client-secret`, access token hoặc refresh token vào JavaScript bundles, HTML bootstrap data hoặc browser storage.

---

## 11. `DefaultOAuth2AuthorizationRequestResolver`

Spring Security Servlet có:

```java
org.springframework.security.oauth2.client.web
    .DefaultOAuth2AuthorizationRequestResolver
```

Đây là implementation của:

```java
OAuth2AuthorizationRequestResolver
```

Nó dựng `OAuth2AuthorizationRequest` theo request và client registration. Có thể gắn customizer:

```java
setAuthorizationRequestCustomizer(
    Consumer<OAuth2AuthorizationRequest.Builder>
)
```

### 11.1. Ví dụ chỉ minh họa: luôn thêm `prompt=consent`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;

@Bean
OAuth2AuthorizationRequestResolver authorizationRequestResolver(
        ClientRegistrationRepository registrations) {

    DefaultOAuth2AuthorizationRequestResolver resolver =
        new DefaultOAuth2AuthorizationRequestResolver(
            registrations,
            "/oauth2/authorization"
        );

    resolver.setAuthorizationRequestCustomizer(
        builder -> builder.additionalParameters(
            params -> params.put("prompt", "consent")
        )
    );

    return resolver;
}
```

Đây là ví dụ về **cách thêm OIDC parameter**. **Không nên áp `prompt=consent` toàn cục trong production** nếu không có yêu cầu rõ, vì có thể tạo consent fatigue và làm login liên tục bị ngắt bởi UI.

### 11.2. Gắn resolver vào OAuth2 Login

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationRequestResolver resolver)
        throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(oauth2 -> oauth2
            .authorizationEndpoint(endpoint -> endpoint
                .authorizationRequestResolver(resolver)
            )
        )
        .oauth2Client(Customizer.withDefaults());

    // CSRF protection vẫn bật.
    return http.build();
}
```

Ở đây `resolver` là bean được khai báo tại mục 11.1, hoặc thay bằng custom resolver theo **intent** tại phần tiếp theo.

### 11.3. Đừng chỉnh authorization URI bằng chuỗi nối tùy tiện

Ví dụ không nên:

```java
authorizationUri + "?scope=calendar.readonly&state=abc"
```

vì dễ:

- Ghi đè `state` do Spring Security tạo.
- Bỏ PKCE/nonce.
- Encode sai URL.
- Gửi scopes/redirect URI không được cho phép.
- Làm hỏng callback validation.

Dùng `OAuth2AuthorizationRequest.Builder`/resolver để để framework tiếp tục xử lý giao thức.

---

## 12. Thay đổi scope theo feature: custom resolver có kiểm soát

Một `DefaultOAuth2AuthorizationRequestResolver` có thể được **wrap** để chỉ thêm scopes trong một flow đã được backend cho phép.

### 12.1. Data model intent

Ví dụ interface thuộc **ứng dụng**, không phải Spring Security:

```java
public interface ConsentIntentService {

    ConsentIntent findApprovedForCurrentRequest(
        HttpServletRequest request,
        String registrationId
    );

    void bindOauthState(
        ConsentIntent intent,
        String oauthState
    );
}
```

`ConsentIntent` cần ít nhất:

```java
public record ConsentIntent(
    String id,
    String internalUserId,
    String registrationId,
    Set<String> approvedScopes,
    String feature,
    Instant expiresAt
) {}
```

`HttpServletRequest`, `Set` và `Instant` có imports tương ứng. **Service này phải được triển khai thật** với session, CSRF, account binding, TTL và transaction handling. Không deserialize một object tên `ConsentIntent` từ JSON của browser rồi tin nó là approved.

### 12.2. Resolver wrapper minh họa

```java
import java.util.LinkedHashSet;
import java.util.Set;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public final class IncrementalConsentRequestResolver
        implements OAuth2AuthorizationRequestResolver {

    private final OAuth2AuthorizationRequestResolver delegate;
    private final ConsentIntentService intents;

    public IncrementalConsentRequestResolver(
            ClientRegistrationRepository registrations,
            ConsentIntentService intents) {

        this.delegate =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization"
            );

        this.intents = intents;
    }

    @Override
    public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
        OAuth2AuthorizationRequest original = delegate.resolve(request);
        return customize(request, original);
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request,
            String registrationId) {

        OAuth2AuthorizationRequest original =
            delegate.resolve(request, registrationId);
        return customize(request, original);
    }

    private OAuth2AuthorizationRequest customize(
            HttpServletRequest request,
            OAuth2AuthorizationRequest original) {

        if (original == null) {
            return null;
        }

        // Custom service phải gắn intent với session, user,
        // registration và request này. Không chỉ đọc query param.
        ConsentIntent intent = intents.findApprovedForCurrentRequest(
            request,
            requiredRegistrationId(original)
        );

        if (intent == null) {
            return original; // Login bình thường.
        }

        Set<String> scopes = new LinkedHashSet<>(
            original.getScopes()
        );
        scopes.addAll(intent.approvedScopes());

        OAuth2AuthorizationRequest modified =
            OAuth2AuthorizationRequest.from(original)
                .scopes(scopes)
                .additionalParameters(params -> {
                    if ("google".equals(intent.registrationId())) {
                        params.put(
                            "include_granted_scopes", "true"
                        );
                    }
                })
                .build();

        // Dùng OAuth2 state đã được Spring tạo; service
        // bind thêm pending intent, không thay thế state.
        intents.bindOauthState(intent, modified.getState());

        return modified;
    }

    private String requiredRegistrationId(
            OAuth2AuthorizationRequest request) {
        // Chỗ này cần trích registration ID từ trusted
        // authorization request attributes/routing của app.
        // KHÔNG suy từ scope hoặc một browser query tự do.
        throw new UnsupportedOperationException(
            "Implement trusted registration resolution"
        );
    }
}
```

**Đây là skeleton minh họa extension point**, không phải copy-paste production hoàn chỉnh: `requiredRegistrationId` cần implementation dựa trên trusted registration routing/attributes của ứng dụng. Không deploy đoạn `UnsupportedOperationException` dưới dạng endpoint hoàn chỉnh.

Mục tiêu đoạn code:

1. Giữ authorization request đã được framework xây.
2. Thêm scopes đã được policy cho phép, không phải scopes do user tự khai báo.
3. Giữ nguyên state/PKCE/nonce và các attributes cần thiết.
4. Chỉ thêm parameter đặc thù Google khi đúng registration.
5. Liên kết pending intent với state để validate tại callback.

### 12.3. Tránh một session variable chung cho nhiều tabs

Sai:

```text
session.pendingScope = "calendar.readonly"
```

Khi hai tabs cùng xin quyền cho hai features, value dễ bị ghi đè.

Tốt hơn:

```text
intentId -> user/session/registration/feature/expiry
OAuth2 state -> intentId
```

với single-use semantics, expiry và transaction/checks phù hợp.

### 12.4. Đừng tự bỏ scope `openid`

Nếu application đang dùng OIDC Login, việc xây tập scopes mới chỉ chứa:

```text
calendar.readonly
```

có thể khiến authorization request không còn là OIDC Login như dự kiến.

Khi đang tái cấp quyền trong cùng OIDC registration, cần giữ các scopes nền tảng (`openid` và những scopes thực sự cần) theo provider contract. Với Google incremental authorization, semantics gộp grants có thể do provider quyết định; vẫn phải xác minh response thực tế.

---

## 13. Chính sách bắt đầu consent: POST trước, redirect sau

Một BFF dùng cookie session nên có endpoint bắt đầu flow, ví dụ:

```http
POST /api/features/calendar/connect
Cookie: SESSION=...
X-CSRF-TOKEN: ...
Content-Type: application/json

{"feature":"CALENDAR_READ"}
```

Backend thực hiện:

1. Kiểm tra Spring Security Authentication.
2. Xác định internal account/tenant đáng tin.
3. Kiểm tra feature có được bật cho tenant này không.
4. Ánh xạ `CALENDAR_READ` thành scopes bằng server-side allowlist.
5. Kiểm tra user chưa có quyền cần thiết hoặc cần reauthorization.
6. Tạo pending intent trong backend.
7. Trả một **same-origin authorization start URL**, không trả access token.
8. Frontend top-level navigate tới URL đó.

Ví dụ response:

```json
{
  "authorizationStartUrl": "/oauth2/authorization/corporate"
}
```

### 13.1. Vì sao phải bảo vệ POST bằng CSRF?

Một website lạ không được khiến user đang đăng nhập BFF bắt đầu một consent workflow hoặc thay đổi trạng thái kết nối mà user không chủ động yêu cầu.

OAuth2 `state` giúp liên kết callback với authorization request, nhưng nó **không thay CSRF token cho admin/account-settings POST**.

### 13.2. Không cho browser chọn arbitrary scope

Anti-pattern:

```http
POST /api/authorize
{"scopes":["admin.write","billing.export","*"]}
```

rồi backend đưa nguyên vào authorization request.

Đúng:

```text
Frontend feature = CALENDAR_READ
  |
  v
Backend policy -> allowed scopes for tenant/provider/feature
  |
  v
Authorization request with allowlisted scopes
```

### 13.3. Điều hướng khác XHR

OAuth2 authorization redirect cần browser tương tác với IdP. Không nên khởi tạo bằng `fetch()` rồi mong XMLHttpRequest tự hiển thị login/consent screen đúng cách.

Thông thường:

```javascript
window.location.assign(
  "/oauth2/authorization/corporate"
);
```

sau khi backend đã xác nhận intent.

---

## 14. Sau callback: xác minh đúng user và scope được cấp

Consent bổ sung thường bắt đầu khi user **đã có local session**. Khi callback OAuth2 Login quay về, Spring Security có thể dựng một `OAuth2AuthenticationToken` mới.

Điểm nguy hiểm: người dùng có thể chọn **một tài khoản IdP khác** ở consent screen.

Ví dụ:

```text
Local session:
    internalAccount U = Alice

Intent:
    Alice muốn cấp calendar.readonly

Provider account chooser:
    User vô tình chọn Bob

Callback:
    OIDC identity = Bob
```

Nếu backend chỉ kiểm tra “code exchange thành công” rồi lưu token Bob dưới account Alice, đây là lỗi **cross-account token binding**.

### 14.1. Phải kiểm tra identity binding

Với OIDC:

```text
expected (iss,sub) từ previously linked identity
    ==
verified (iss,sub) từ ID Token mới
```

Nếu khác:

- Từ chối tăng quyền cho Alice.
- Không tự link Bob vào Alice.
- Không thay local account của browser một cách âm thầm.
- Không lưu `OAuth2AuthorizedClient` của Bob dưới principalName Alice.
- Giữ audit và hiển thị lỗi không lộ secrets.

Nếu provider không phải OIDC, dùng stable provider user ID được nhận qua trusted user endpoint, namespace theo provider instance.

### 14.2. Callback còn phải kiểm tra

- OAuth2 `state` hợp lệ và đúng pending intent.
- PKCE, client registration, redirect URI theo framework.
- OIDC ID Token issuer, audience, signature, expiry, nonce theo config.
- Pending intent chưa hết hạn/chưa consumed.
- Local account/tenant vẫn active.
- Scope được cấp có đủ cho feature không.
- Provider đang được phép dùng.
- Không có simultaneous account switch/logout khiến intent bị stale.

### 14.3. Không dùng email làm identity binding

Email có thể đổi, không verified hoặc bị tái sử dụng. OIDC `(iss,sub)` thường là identity key tốt hơn; với OAuth2 provider thuần, cần stable user ID có provider namespace.

### 14.4. Đừng thay authenticated session sai người

Interactive reauthorization được thực hiện trong một session đã tồn tại. Spring Security OAuth2 login success flow có thể thiết lập Authentication mới. Ứng dụng cần thiết kế success handler/identity mapping sao cho local account sau callback vẫn là **đúng account đã bắt đầu** workflow.

Đừng đọc current `Authentication` trong success handler rồi mặc định đó là account nội bộ ban đầu; nó có thể đã là provider principal vừa xác thực.

---

## 15. Granted scopes: request không đồng nghĩa thực cấp

Ví dụ ứng dụng xin:

```text
requestedScopes:
    openid
    profile
    calendar.readonly
    calendar.events.write
```

AS có thể chỉ cấp:

```text
grantedScopes:
    openid
    profile
    calendar.readonly
```

Tùy provider, điều này có thể được biểu diễn qua token response `scope`, token metadata hoặc quyền của token thực tế.

### 15.1. Đọc access token scopes trong Spring Security

`OAuth2AuthorizedClient` có:

```java
OAuth2AccessToken token =
    authorizedClient.getAccessToken();

Set<String> scopes = token.getScopes();
```

Ví dụ kiểm tra:

```java
import java.util.Set;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

public boolean hasCalendarRead(
        OAuth2AuthorizedClient authorizedClient) {

    return authorizedClient != null
        && authorizedClient.getAccessToken() != null
        && authorizedClient.getAccessToken()
            .getScopes()
            .contains("calendar.readonly");
}
```

`OAuth2AccessToken#getScopes()` phản ánh dữ liệu scopes mà Spring Security lưu từ token response/authorization. Với provider có semantics khác hoặc token dùng theo resource-specific permissions, cần đối chiếu đúng contract.

### 15.2. Scope trong response có thể bị bỏ qua khi không đổi

OAuth2 token responses có thể không luôn bao gồm `scope` nếu scopes được cấp giống những gì đã yêu cầu, theo giao thức/implementation. Không tự parse JSON bằng cách đòi field `scope` lúc nào cũng hiện diện.

Spring Security token response client và provider-specific converters có vai trò xử lý response theo contract.

### 15.3. Quy tắc bật feature

```text
if token has required scope
   and authorized client belongs to correct user/provider
   and token valid for target audience
   and local business policy allows:
       enable feature
else:
       show limited state or request consent
```

Không dùng một boolean `consented=true` trong session để bỏ qua kiểm tra token.

---

## 16. `OAuth2AuthorizedClient` và vấn đề storage sau consent

Spring Security có:

```java
OAuth2AuthorizedClientRepository
OAuth2AuthorizedClientService
OAuth2AuthorizedClientManager
```

Một authorized client thường gắn với:

```text
(clientRegistrationId, principalName)
```

Ví dụ:

```text
("corporate", "alice-901")
    -> access token with scopes openid profile

Sau incremental authorization:
("corporate", "alice-901")
    -> access token with scopes openid profile calendar.readonly
```

Nhưng chính xác **replace, merge hay giữ token cũ** phụ thuộc provider và cách repository/service của app hoạt động.

### 16.1. Không tự merge raw tokens

Không thể ghép hai access tokens thành một token:

```text
Token A (profile)
+
Token B (calendar.readonly)
=
Token C (profile + calendar.readonly) // không tồn tại
```

Chỉ Authorization Server có quyền cấp token tương ứng. Nếu provider cho phép combined authorization, **AS** phát token cho scopes đã cấp.

### 16.2. Một registration thường có một authorized client cho principal

Default `OAuth2AuthorizedClientService` key `(registrationId,principalName)` có thể **ghi đè** token cũ khi authorization mới được lưu theo cùng key.

Nếu cần:

```text
profile access token dành cho API A
calendar access token dành cho API B
```

với khác audience, expiry hoặc ownership, có thể cần **registrations riêng** hoặc custom token storage theo audience/resource/authorization ID.

### 16.3. Refresh token có thể bị rotate hoặc không trả mới

AS có thể:

- Cấp refresh token mới.
- Giữ refresh token cũ.
- Không trả refresh token trong response tăng scope.
- Vô hiệu hóa refresh token trước khi authorization lại.
- Yêu cầu user consent lại nếu quyền thay đổi.

Không có một policy universal. Khi response không có refresh token, cách giữ token cũ hay xóa phải dựa trên **provider contract và ràng buộc authorization**; không tự dùng refresh token cũ cho một authorization khác nếu không hợp lệ.

### 16.4. Token cache của feature phải cập nhật

Một UI đã bật `CALENDAR_READ` nhưng backend vẫn giữ authorized client cũ thiếu scope có thể gây vòng lặp consent hoặc API 403.

Cần đảm bảo:

- Save authorized client mới tới đúng store.
- Evict/invalidate cache theo registration/principal.
- Không để pod B dùng stale authorized client từ pod A.
- Refresh token changes được cập nhật atomically.
- Không để callback từ tab cũ ghi đè token có scopes mới bằng token cũ.

---

## 17. Không dùng refresh token để "xin thêm scope" tùy ý

Trong OAuth2, Refresh Token Grant có thể cho phép một tập scope bằng hoặc hẹp hơn authorization đã được cấp theo AS policy. **Nó không phải cách tự mở rộng quyền chưa từng được cấp.**

Ví dụ:

```text
Current grant:
    openid profile

Client sends refresh token and requests:
    calendar.events.write
```

Nếu quyền đó chưa được AS cấp, refresh không được dùng để lách consent.

**Đường thông dụng để xin quyền mới** là một interactive authorization request mới hoặc cơ chế consent/authorization khác được provider công bố.

### 17.1. AuthorizedClientManager không bật browser consent tự động

`OAuth2AuthorizedClientManager` thường xử lý load existing authorization, refresh token, client credentials hoặc grants đã được cấu hình.

Khi API trả:

```http
403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

manager **không tự mở consent page trong browser**. Ứng dụng cần một workflow UX riêng:

```text
API insufficient_scope
  -> feature shows "Connect Calendar"
  -> user explicitly initiates consent
  -> Authorization Code Flow
```

Không tự chuyển mọi 403 thành reauthorization redirect, vì 403 còn có thể là business authorization denial.

### 17.2. Retry consent có giới hạn

Nếu user từ chối quyền, không lập vòng lặp:

```text
consent denied -> redirect consent -> denied -> redirect ...
```

Chỉ yêu cầu lại khi user chủ động dùng tính năng cần quyền, với thông điệp rõ ràng và policy chống consent fatigue.

---

## 18. Consent denial và partial grant là kết quả bình thường

Người dùng có thể không muốn ứng dụng đọc lịch hoặc dữ liệu riêng tư. Đây không phải lỗi cần cưỡng ép tiếp tục.

Ví dụ UI:

```text
"Bạn có thể tiếp tục sử dụng dashboard.
Đồng bộ lịch chưa được bật vì bạn chưa cấp quyền đọc lịch."
```

### 18.1. Những trường hợp cần xử lý

| Kết quả | Hành vi hợp lý |
|---|---|
| User cấp đủ scope | Lưu authorization, bật feature nếu local policy cho phép |
| User chỉ cấp một phần scopes | Bật phần tương thích; khóa thao tác cần quyền còn thiếu |
| User từ chối hoàn toàn | Giữ chức năng cơ bản, cho phép thử lại khi user muốn |
| Admin consent cần thiết | Thông báo cần admin approval theo provider workflow |
| Client chưa được verify | Hiển thị hướng dẫn đúng, không yêu cầu user bỏ qua security warning |
| Provider trả interaction error | Giải thích và cho user chọn retry có kiểm soát |
| User chọn provider account khác | Từ chối binding; yêu cầu chọn đúng account |
| Token response không có refresh token | Xử lý online-only/reconnect theo policy |
| Scope đang granted bị revoke | Hủy trạng thái connected hoặc yêu cầu authorization lại |

### 18.2. Không âm thầm dùng token mạnh hơn

Nếu user từ chối `calendar.events.write`, không lấy một service-admin token hoặc token của account khác để thực hiện thao tác thay họ.

Đó là nguy cơ privilege escalation/confused deputy.

### 18.3. Không coi denied consent là login failure

Nếu user đã đăng nhập bằng `openid profile`, việc từ chối một scope bổ sung **không nhất thiết làm user mất toàn bộ local session**.

Tách **authentication session** khỏi **permission connection status** của feature.

---

## 19. Reauthentication: xác thực lại khác consent

**Reauthentication** là yêu cầu user xác minh lại danh tính với OpenID Provider hoặc ứng dụng trước một thao tác nhạy cảm.

Ví dụ:

```text
Alice đăng nhập từ 09:00
Alice yêu cầu thay đổi payout bank lúc 16:00

Policy:
    must have authenticated within 5 minutes
    MFA or trusted authentication context required
```

Một session còn hạn đến 18:00 **không có nghĩa** xác thực gần nhất tại IdP đủ mới cho thay đổi payout.

### 19.1. `prompt=login`

OIDC cho phép:

```text
prompt=login
```

yêu cầu OP **reauthenticate** End-User, kể cả khi có OP session.

Đây không phải OAuth2 `scope` và không tự cấp API permissions.

### 19.2. `max_age`

OIDC:

```text
max_age=300
```

yêu cầu authentication tại OP không quá **300 giây** theo semantics chuẩn. Nếu authentication cũ hơn, OP phải cố gắng xác thực user lại.

Đặc biệt:

```text
max_age=0
```

về reauthentication semantics tương đương `prompt=login` theo OpenID Connect Core.

### 19.3. `auth_time`

Khi gửi `max_age`, ID Token trả về **phải có claim `auth_time`** theo OIDC Core.

Ví dụ:

```json
{
  "iss": "https://login.example-idp.com",
  "sub": "alice-901",
  "aud": "portal-bff",
  "auth_time": 1979997600,
  "iat": 1979997900,
  "exp": 1980001500
}
```

`auth_time` là thời điểm user **được OP xác thực lần cuối**, không phải thời điểm phát token mới.

### 19.4. `iat` không thay `auth_time`

Một ID Token mới có:

```text
iat = 16:00
```

không chứng minh user vừa gõ password/MFA lúc 16:00. OP có thể phát token mới dựa trên SSO session đã xác thực từ 09:00.

Cần kiểm tra `auth_time` nếu policy yêu cầu freshness.

---

## 20. `prompt=consent` và `prompt=login` không tương đương

| Request parameter | Câu hỏi bảo mật |
|---|---|
| `prompt=consent` | User có được yêu cầu đồng ý cho client quyền truy cập không? |
| `prompt=login` | User có cần tự xác thực lại với OP không? |
| `max_age=300` | Authentication có đủ mới trong 300 giây không? |
| `acr_values=...` | User có cần authentication context cụ thể không? |
| `scope=calendar.readonly` | Client có xin quyền đọc lịch không? |

Ví dụ:

```text
User đang đăng nhập SSO session hợp lệ.
User xin thêm calendar.readonly.
    -> Có thể consent mà không login lại.

User muốn sửa ngân hàng nhận tiền.
    -> Có thể login lại nhưng không xin scope mới.

User muốn export dữ liệu đặc biệt.
    -> Có thể cần cả consent API scope và step-up.
```

### 20.1. Có thể gửi cả hai prompt?

OIDC `prompt` là danh sách phân tách bằng dấu cách, ví dụ:

```text
prompt=login consent
```

nếu provider hỗ trợ và policy thực sự yêu cầu cả authentication lẫn consent.

`prompt=none` **không được kết hợp với các giá trị prompt khác**. Đừng gửi `none login` hoặc `none consent`.

### 20.2. "Đã hiện màn hình login" chưa chứng minh đủ MFA

`prompt=login` yêu cầu OP xác thực lại, nhưng có thể thực hiện bằng password, passwordless hoặc phương thức khác theo OP policy.

Nếu nghiệp vụ yêu cầu MFA/phishing-resistant authentication, còn cần assurance contract, không chỉ request prompt.

---

## 21. Step-up authentication và authentication assurance

**Step-up authentication** nâng mức chắc chắn về identity/possession trước tác vụ nhạy cảm.

Ví dụ:

```text
Login ban đầu:
    password + SSO session

Thao tác nguy hiểm:
    passkey hoặc MFA theo corporate policy
```

Trong OIDC, có các claims/parameters liên quan:

| Thành phần | Vai trò |
|---|---|
| `acr` | Authentication Context Class Reference được OP xác nhận |
| `amr` | Authentication Methods References, các phương thức đã được sử dụng |
| `acr_values` | Danh sách authentication context classes client yêu cầu |
| `auth_time` | Thời điểm user được OP xác thực |
| `max_age` | Ràng buộc freshness |
| `prompt=login` | Yêu cầu xác thực lại |

### 21.1. `acr_values` là yêu cầu, không là chứng cứ

Ví dụ:

```text
acr_values=urn:example:loa:high
```

Chỉ có ý nghĩa nếu OP/tenant công bố, hỗ trợ và gán semantics đáng tin cho `urn:example:loa:high`.

Không dùng chuỗi này như một standard MFA level universal.

### 21.2. Phải kiểm tra claims trả về

Nếu ứng dụng gửi:

```text
acr_values=urn:example:loa:high
```

nhưng ID Token không có `acr` phù hợp, hoặc OP không thực thi requirement, **không nên nâng quyền**.

Tùy use case, có thể dùng OIDC `claims` request để yêu cầu `acr`/`auth_time` thiết yếu, nhưng provider support và exact enforcement phải được kiểm thử.

### 21.3. `amr` có thể khác nhau giữa IdPs

Các giá trị `amr` phụ thuộc chuẩn/triển khai. Không viết:

```java
if (amr.contains("mfa")) {
    allowEverySensitiveAction();
}
```

mà không có agreed mapping/assurance policy theo issuer và tenant.

### 21.4. Một provider khác có thể có mức assurance khác

Nếu internal account liên kết Google và Workforce identities:

```text
OIDC Google login -> local account Alice
OIDC Workforce login -> local account Alice
```

Việc hai identities cùng dẫn đến Alice **không có nghĩa** hai phiên có cùng authentication assurance.

Nghiệp vụ cao rủi ro có thể yêu cầu reauthenticate bằng Workforce provider hoặc bằng app-managed MFA, tùy policy.

---

## 22. Xác minh `auth_time` sau reauthentication

Giả sử backend yêu cầu:

```text
stepUpIntent:
    internalUserId = Alice
    requiredMaxAgeSeconds = 300
    requiredAcr = high, nếu provider hỗ trợ
    initiatedAt = server timestamp
    expiresAt = server timestamp
```

Sau callback, Spring Security đã xác minh ID Token theo OIDC. **Application** còn phải kiểm tra claim policy.

### 22.1. Logic khái niệm

```text
1. Xác minh callback thuộc đúng pending step-up intent.
2. ID Token mới đã được issuer/client validation.
3. (iss,sub) khớp identity đã link với internal account U.
4. auth_time tồn tại theo max_age requirement.
5. auth_time đủ mới theo required freshness và clock skew policy.
6. acr/amr thỏa assurance policy nếu có.
7. Tenant/local account vẫn active.
8. Mark step-up satisfied chỉ cho scope/session/transaction cần thiết.
9. Consume pending intent để ngăn replay.
```

### 22.2. Ví dụ Java kiểm tra freshness

```java
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class OidcFreshnessPolicy {

    public static boolean authenticatedRecently(
            OidcUser user,
            Instant now,
            Duration maxAge,
            Duration allowedClockSkew) {

        Instant authTime = user.getIdToken()
            .getClaimAsInstant("auth_time");

        if (authTime == null) {
            return false;
        }

        // Không chấp nhận time ở tương lai quá clock skew.
        if (authTime.isAfter(now.plus(allowedClockSkew))) {
            return false;
        }

        Duration age = Duration.between(authTime, now);

        return !age.minus(allowedClockSkew).isNegative()
                ? age.compareTo(maxAge.plus(allowedClockSkew)) <= 0
                : true;
    }
}
```

Đoạn này **chỉ minh họa freshness**; trong production cần time source từ trusted clock, policy về skew, account/issuer binding, ACR/AMR và đầy đủ callback checks. Nếu yêu cầu xác thực xảy ra **sau một thời điểm nhất định**, còn phải kiểm tra `auth_time` tương ứng với initiation/challenge time theo policy, không chỉ một max age rộng.

### 22.3. `auth_time` phải đi cùng ID Token đã được xác minh

Không lấy:

```json
{"auth_time":"now"}
```

từ browser JSON rồi coi là bằng chứng MFA. Chỉ dùng claim từ ID Token/OP response đã được framework và policy xác minh.

### 22.4. Freshness của local session khác của OP

Một local Spring session có thể vừa được tạo sau silent login nhưng OP xác thực user từ lâu.

Ngược lại, một OP session có authentication mới nhưng local app session đang thuộc một internal account khác.

Cần kiểm tra **cả account binding lẫn auth freshness**.

---

## 23. Ví dụ `max_age` và `prompt=login` theo yêu cầu

Một Authorization Request cho OIDC step-up:

```http
GET https://login.example-idp.com/authorize?
  response_type=code
  &client_id=portal-bff
  &scope=openid%20profile
  &redirect_uri=https%3A%2F%2Fportal.example%2Flogin%2Foauth2%2Fcode%2Fcorporate
  &state=RANDOM_STATE
  &code_challenge=RANDOM_CHALLENGE
  &code_challenge_method=S256
  &prompt=login
  &max_age=0
```

Trong thực tế có thể chỉ cần `max_age=0` hoặc `prompt=login` theo OIDC semantics; gửi cả hai là ví dụ khi policy/provider cho phép. Với `max_age`, ID Token phải chứa `auth_time`.

### 23.1. Request-level customization

Nếu ứng dụng luôn yêu cầu reauthentication cho **một registration riêng**, có thể cấu hình resolver/customizer theo registration và áp parameter.

Nhưng **không áp `max_age=0` cho mọi login request** nếu điều đó gây reauthentication liên tục, làm mất giá trị SSO và tăng chi phí UX.

### 23.2. Không lấy `max_age` từ URL browser

Một endpoint:

```text
/step-up?max_age=9999999
```

không được cho user tự hạ thấp policy.

Backend phải map feature/transaction risk thành max age và assurance requirement đáng tin.

### 23.3. `login_hint` chỉ là gợi ý UI

Có thể gửi `login_hint` để giúp OP chọn đúng account, nhưng nó **không là bằng chứng** callback sẽ thuộc đúng external identity.

Sau callback vẫn phải xác minh `(iss,sub)`.

---

## 24. `prompt=none` và silent authorization

OIDC cho phép:

```text
prompt=none
```

yêu cầu OP **không hiển thị UI**. Nếu không thể đáp ứng authentication/consent âm thầm, OP trả lỗi.

Những errors có thể gặp:

```text
login_required
consent_required
interaction_required
account_selection_required
```

Tùy provider và tình huống, một số giá trị có thể khác.

### 24.1. Silent check không phải bypass consent

Nếu user chưa cấp `calendar.readonly`, `prompt=none` không được dùng để lách user interaction. OP phải áp chính sách consent; có thể trả `consent_required`.

### 24.2. Third-party cookie restrictions

Một số kỹ thuật silent sign-in dựa vào hidden iframe và OP browser cookies có thể không hoạt động vì third-party cookie restrictions hoặc browser privacy features.

BFF server-side session không bảo đảm OP SSO silent authorization thành công; phải có interactive fallback.

### 24.3. Không lặp vô hạn

```text
prompt=none -> interaction_required
    -> fallback to explicit user action
```

Không gửi lại silent request vô hạn hoặc tự chuyển sang consent prompt không có user intent.

---

## 25. Tái xác thực tại BFF không luôn phải qua OIDC Provider

Một ứng dụng có thể triển khai step-up bằng:

- OIDC reauthentication với `max_age`/`acr`.
- App-local passkey/MFA challenge.
- Password confirmation theo chính sách.
- Transaction-specific confirmation.
- Out-of-band approval cho nghiệp vụ cực nhạy cảm.

Cần phân biệt:

**Local step-up:** ứng dụng kiểm soát chính phép xác minh bổ sung và ghi nhận kết quả server-side.

**OIDC step-up:** ứng dụng yêu cầu OP cung cấp authentication evidence mới, rồi xác minh ID Token claims.

Cả hai đều có thể phù hợp tùy product/security policy.

### 25.1. Không lưu một boolean `isAdmin=true` vô hạn sau step-up

Nếu một step-up chỉ dành cho transaction `PAYMENT_CHANGE #834`, kết quả có thể cần bound tới:

```text
internalAccountId
sessionId hoặc session epoch
transactionId
requiredAssurance
verifiedAt
expiresAt
usedOnce
```

Một session attribute `stepUpPassed=true` không timeout/transaction binding có thể biến một xác minh một lần thành quyền lâu dài.

### 25.2. Session fixation và login callback

Spring Security có session fixation protection theo cấu hình. Một reauthentication callback có thể thay SecurityContext/session attributes.

Thiết kế step-up phải tương thích session migration và không lấy raw session ID từ URL. Nếu callback thay Authentication, cần giữ đúng internal account và không biến reauthentication thành một account switch.

### 25.3. Step-up không thay business approval

Một người dùng xác thực lại bằng MFA vẫn không được sửa dữ liệu của tenant khác hoặc tự tăng account role.

---

## 26. BFF: browser không cần biết OAuth2 tokens

Trong mô hình **Backend for Frontend**, browser giữ:

```text
Cookie: SESSION=<opaque-session-id>
```

Backend giữ:

```text
OAuth2AuthorizedClient
    accessToken
    refreshToken, nếu có
    clientRegistrationId
    principalName
```

### 26.1. Consent UI chỉ đưa browser đi qua redirect

```text
Browser:
    POST start-consent + CSRF
    top-level redirect to OP
    redirect back to BFF
    receive business UI response
```

Không trả:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "id_token": "..."
}
```

về frontend sau incremental authorization.

### 26.2. CSRF cần duy trì

Do browser tự gửi session cookie, endpoint khởi tạo consent hoặc step-up phải bảo vệ CSRF khi nó thay đổi server-side pending intent hoặc account authorization state.

`HttpOnly` không ngăn script cùng origin thực hiện API calls; vẫn cần XSS defenses, CSP, trusted script handling, backend authorization và step-up policy.

### 26.3. Cookie SameSite và OIDC callback

Nếu OP redirect về BFF bằng top-level GET, `SameSite=Lax` thường phù hợp. Với callback `form_post`, cross-site POST có thể không gửi cookie Lax; phải có cookie/response mode design phù hợp.

Không tắt `state` validation để sửa lỗi callback mất session.

---

## 27. Tách consent cho API với liên kết danh tính

Một người dùng có thể:

```text
Internal Account U
    linked with Google identity G
    linked with Workforce identity W
```

**Linking** G/W cho login không có nghĩa được đọc Google Drive, lịch, hoặc Microsoft Graph.

Các workflows độc lập:

| Workflow | Mục đích |
|---|---|
| Link Google identity | Cho phép đăng nhập internal account U qua G |
| Consent calendar.readonly | Cho phép client đọc calendar resource của G |
| Re-authenticate with Workforce | Chứng minh W vẫn kiểm soát identity và đủ mới |
| Change local role | Business authorization theo policy |
| Disconnect calendar integration | Remove/revoke OAuth2 authorized client |
| Unlink Google identity | Xóa một login method của internal account U |

### 27.1. Một account có nhiều Google identities

Nếu cùng internal account U link hai Google accounts, default authorized client store keyed `(registrationId,principalName)` có thể không biểu diễn hai authorized clients cùng lúc.

Cần policy một provider identity mỗi registration hoặc **custom store keyed theo external identity/resource**.

### 27.2. Không tự thay account khi consent chọn provider identity khác

Nếu Alice đã đăng nhập U nhưng authorization dialog chọn Bob, application phải từ chối hoặc chuyển sang workflow account linking riêng sau proof-of-control; không âm thầm lưu token Bob dưới Alice.

---

## 28. Đa tenant: scope và consent phải được phép theo tenant

Ví dụ:

```text
Tenant Alpha:
    Calendar sync được phép
    allowedScope = calendar.readonly

Tenant Beta:
    Calendar sync bị chặn bởi tổ chức
```

Kể cả AS cấp `calendar.readonly` cho một identity của tenant Beta, ứng dụng vẫn không được bỏ qua **tenant business policy**.

### 28.1. Registration phải đúng tenant

Không cho user chọn:

```text
registrationId = tenant-beta-admin-client
```

trong request của tenant Alpha, vì điều đó có thể làm BFF dùng client credential hoặc scopes của tenant khác.

### 28.2. Consent state phải gắn tenant

Pending intent cần:

```text
tenantId
internalAccountId
registrationId
expectedIdentity
feature
approvedScopes
oauthStateBinding
```

Không suy tenant chỉ từ email domain hoặc `sub` trần.

### 28.3. Không tin issuer động do browser nhập

OIDC discovery từ issuer URL tùy ý có thể tạo SSRF và IdP mix-up. Đối với consent/re-auth, chỉ dùng provider registrations đã được onboarding và approve.

---

## 29. Token audience và scope không phải một thứ

Một access token có:

```json
{
  "iss": "https://login.example-idp.com",
  "sub": "alice-901",
  "aud": "calendar-api",
  "scope": "calendar.readonly"
}
```

khác với token:

```json
{
  "iss": "https://login.example-idp.com",
  "sub": "alice-901",
  "aud": "billing-api",
  "scope": "billing.read"
}
```

Cùng scope name hoặc cùng End-User không có nghĩa token có thể được sử dụng tại một API khác.

### 29.1. Có thể cần resource indicator hoặc registration khác

Một provider có thể yêu cầu:

```text
resource=https://calendar-api.example
```

theo RFC 8707 hoặc một parameter audience riêng.

Đừng chỉ thêm scope mới rồi tự gửi token tới mọi Resource Server.

### 29.2. Incremental authorization có thể thay token authorization context

Nếu quyền mới thuộc resource khác, provider có thể không trả một token chung bao phủ cả hai APIs. Thiết kế storage/registration phù hợp **target audiences**, không chỉ một trường `Set<String> scopes`.

---

## 30. Khi access token không đủ scope: xử lý từ Resource Server

Một API có thể trả:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="calendar.readonly"
```

Theo RFC 6750, `insufficient_scope` cho biết token không có quyền cần thiết.

### 30.1. Không tin tuyệt đối header scope từ mọi upstream

BFF không nên lấy bất kỳ chuỗi trong `WWW-Authenticate` rồi đưa vào authorization request không kiểm tra.

Map lỗi upstream tới **feature-to-scope allowlist** đã định nghĩa trong backend.

### 30.2. Phân biệt 401 và 403

| Kết quả | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| 401 `invalid_token` | Token expired/revoked/không hợp lệ | Refresh/re-authorize giới hạn theo provider policy |
| 403 `insufficient_scope` | Token thiếu quyền OAuth2 cho API | Hiển thị consent CTA nếu feature hợp lệ |
| 403 business permission | User không được xem tài nguyên | Không xin scope vô ích để bypass |
| 403 tenant restriction | Tổ chức cấm chức năng | Không cho re-consent nhằm né policy |
| 429 | API rate limited | Backoff/rate policy, không mở login flow |
| 5xx | Provider/resource unavailable | Retry có giới hạn, không lặp consent |

### 30.3. Không tự retry API vô hạn sau consent

Sau authorization mới:

1. Xác minh access token có scope/audience phù hợp.
2. Đảm bảo authorized client được lưu đúng principal.
3. Retry API **có giới hạn** nếu request còn hợp lệ.
4. Không retry các state-changing requests không idempotent một cách mù quáng.
5. Trả lỗi rõ nếu target API vẫn từ chối.

---

## 31. Consent management UI: hiển thị quyền thực sự

Một màn hình “Ứng dụng đã kết nối” có thể hiển thị:

```text
Google Calendar
    Trạng thái: Đã kết nối
    Quyền: Đọc lịch
    Tài khoản: alice@example.com
    Cấp quyền gần nhất: ...
    Hành động: Kết nối lại | Ngắt kết nối
```

Dữ liệu trên chỉ nên lấy từ **trusted local state đã đối chiếu với token/provider** và không làm lộ raw tokens hoặc excessive personal claims.

### 31.1. Không nói "user đã đồng ý vĩnh viễn"

Consent có thể bị thu hồi tại IdP. Access token có thể hết hạn; refresh token có thể bị rotate/revoke hoặc tenant policy thay đổi.

Tốt hơn:

```text
Connection status = Active / Needs consent / Needs reconnect / Revoked / Error
```

và kiểm tra lại tại thời điểm gọi API.

### 31.2. Quyền tối thiểu

Một feature chỉ đọc lịch không nên xin quyền chỉnh sửa hoặc xóa calendar events. Nếu người dùng cần write access sau, hãy xin bổ sung trong một workflow mới.

### 31.3. Giải thích trước khi redirect

Ví dụ:

> “Để hiển thị lịch trong dashboard, ứng dụng cần quyền đọc sự kiện. Bạn có thể tiếp tục dùng các tính năng khác nếu không cấp quyền.”

Không gây hiểu nhầm rằng bắt buộc phải cho phép truy cập dữ liệu không liên quan tới chức năng cơ bản.

---

## 32. Thu hồi consent và ngắt kết nối

Một người dùng có thể ngắt kết nối trong SaaS hoặc thu hồi access tại provider.

### 32.1. Ngắt kết nối trong ứng dụng

Luồng:

```text
POST /api/connections/calendar/disconnect + CSRF
    |
    +-- Authorization check cho account/tenant
    +-- Mark connection as disconnecting
    +-- Block new usage
    +-- Remove authorized client / token records theo policy
    +-- Call AS revocation endpoint nếu hỗ trợ/được phép
    +-- Stop background sync jobs
    +-- Audit và notify
```

Xóa local record **không mặc nhiên** khiến AS revoke token. RFC 7009 mô tả token revocation khi AS triển khai.

### 32.2. Thu hồi tại provider

User có thể revoke app access trong trang quản lý account của provider. SaaS không nhất thiết được notification tức thì. Lần sử dụng sau có thể gặp `invalid_grant` hoặc `invalid_token`.

Ứng dụng phải xử lý bằng cách:

- Không sử dụng credentials đã biết không hợp lệ.
- Remove/mark authorized client disconnected.
- Không lặp refresh vô hạn.
- Chỉ yêu cầu user re-consent khi họ muốn tính năng.
- Đảm bảo background jobs không tiếp tục spam API.

### 32.3. Logout không bằng consent revocation

- **Logout BFF**: kết thúc local session.
- **OIDC RP-Initiated Logout**: có thể chấm dứt OP session.
- **OAuth2 token revocation**: thu hồi access/refresh token nếu AS hỗ trợ.
- **Disconnect integration**: dừng sử dụng permissions và xóa local authorization.

Các operations có thể phối hợp, nhưng không phải một lệnh duy nhất.

---

## 33. Privacy và data minimization sau consent

Ngay cả khi AS đã cấp scope, ứng dụng vẫn cần:

- Chỉ lấy fields cần thiết.
- Giới hạn retention của dữ liệu từ provider.
- Kiểm tra user/tenant ownership ở backend.
- Không tự sử dụng dữ liệu cho mục đích khác ngoài tính năng người dùng hiểu.
- Phân quyền cho background syncing.
- Có khả năng disconnect/delete dữ liệu theo product policy và luật áp dụng.
- Không log raw API responses chứa dữ liệu riêng tư.

Consent là một điều kiện của OAuth2 authorization, **không phải giấy phép vô hạn** cho mọi cách xử lý dữ liệu.

### 33.1. Dữ liệu mới có thể cần consent UX mới

Nếu `calendar.readonly` từng dùng chỉ để hiển thị lịch, sau đó app muốn phân tích lịch để xây báo cáo chia sẻ với tổ chức, cần đánh giá lại privacy/purpose và user notice/consent theo policy. Không suy rằng scope còn hạn thì mọi purpose đều được tự động chấp nhận.

---

## 34. SecurityContext và local session sau step-up

Một OIDC step-up callback có thể thành công nhưng application cần phân biệt:

```text
OIDC Authentication từ provider
    ->
Local account U đã được xác thực
    ->
Step-up satisfied cho operation O
```

Nếu OIDC provider callback được Spring Security xử lý như một login mới, `Authentication` có thể được thay bằng provider principal mới. Cần ánh xạ lại **đúng local account**, không để session vô tình chuyển sang một user khác.

### 34.1. Đừng tự tin session có user đúng sau redirect

Trước redirect:

```text
Spring session -> Alice internal account U
```

Sau callback:

```text
OIDC principal -> có thể khác nếu account chooser chọn Bob
```

Phải kiểm tra `(iss,sub)` và pending transaction binding trước khi đánh dấu step-up thành công.

### 34.2. Không để step-up trở thành quyền admin mới

Không viết:

```java
session.setAttribute("ROLE_ADMIN", true);
```

chỉ vì đã yêu cầu MFA.

Step-up chứng minh freshness/assurance, không cấp business role. Một resource operation vẫn phải kiểm tra role/ownership.

### 34.3. Token không nhất thiết cần thay đổi khi step-up

Với một bước xác minh nội bộ trước thay đổi payout, application có thể chỉ cần proof-of-fresh-auth mà không cần xin access token scopes mới. Điều này tránh những authorization requests không cần thiết.

---

## 35. Reauth và consent trong hệ thống đa provider

Các providers có thể hỗ trợ khác nhau:

| Năng lực | OIDC Provider chuẩn | OAuth2 thuần | Vendor cụ thể |
|---|---|---|---|
| `prompt=login` | OIDC định nghĩa | Không phải universal OAuth2 | Theo docs |
| `max_age` / `auth_time` | OIDC định nghĩa | Không có ID Token chuẩn | Theo docs |
| `acr_values` | OIDC định nghĩa | Không universal | Theo config/assurance policy |
| `prompt=consent` | OIDC định nghĩa | Không universal | Có thể custom |
| Incremental scopes | Dùng authorization request/scopes | Phụ thuộc AS | Có thể có extension |
| `include_granted_scopes` | Không universal OIDC | Không universal | Google hỗ trợ |
| Refresh token rotation | Theo AS policy | Theo AS policy | Cần test |
| Admin consent | Theo provider/organization | Theo provider | Có thể bắt buộc |
| Partial consent | Provider-dependent | Provider-dependent | Cần test |

### 35.1. Không tạo một `ProviderAuthorizationCustomizer` chung cho tất cả

Ví dụ thiếu an toàn:

```text
Mọi provider:
    prompt=consent
    include_granted_scopes=true
    access_type=offline
    acr_values=mfa
```

Một số providers không hiểu parameters, một số semantics khác, có nơi bỏ qua không báo lỗi. Dùng registration-specific configuration và **contract tests**.

### 35.2. Tenant policy có thể chặn scopes

Provider cho phép client xin quyền không có nghĩa SaaS cho user tenant đó dùng tính năng. Tenant authorization có thể cấm calendar integration, payment export hoặc offline access.

Enforce trước consent request và trước mỗi downstream API call.

---

## 36. Bảo mật redirect, scope và prompt customization

Một attacker có thể cố:

```text
GET /oauth2/authorization/corporate?scope=admin.write
GET /reauth?max_age=100000
GET /oauth2/authorization/corporate?redirect_uri=https://evil.example
```

Nếu custom resolver tin các parameters đó, BFF có thể:

- Yêu cầu scopes ngoài policy.
- Làm loãng reauthentication requirement.
- Đưa authorization code tới redirect URI attacker.
- Bị login CSRF/authorization flow confusion.
- Gửi credentials tới provider không đúng.
- Tạo consent fatigue để social engineer người dùng.

### 36.1. Các kiểm tra tối thiểu

1. Chọn registration từ allowlist/trusted tenant context.
2. Chọn scopes từ server-side feature policy.
3. Chọn `prompt`/`max_age`/`acr` từ risk policy.
4. Không thay `state`/PKCE/nonce do framework quản lý.
5. Chỉ redirect tới registered callback URI.
6. Ràng buộc pending intent với session/account, state, registration và TTL.
7. Xác minh same external identity sau callback.
8. Kiểm tra granted scopes/auth_time/assurance, không chỉ HTTP success.
9. Lưu tokens backend-only.
10. Audit và rate limit repeated consent/reauth attempts.

### 36.2. Chống open redirect

Không trả:

```text
return_to=https://attacker.example
```

rồi redirect sau callback không kiểm tra.

Nên cho các **same-origin relative paths** trong allowlist hoặc server-side continuation IDs. Authorization response code, state hoặc tokens không được lộ qua redirects/Referer logs.

### 36.3. Chống login CSRF và mix-up

Với nhiều issuers/ClientRegistrations, kiểm tra callback tới đúng registration/issuer và authorization request đã bắt đầu. Một ID Token từ issuer B không được nhận như issuer A chỉ vì subject hoặc email giống nhau.

---

## 37. Refresh token rotation và consent scope update cùng lúc

Giả sử một dashboard có nhiều concurrent requests:

```text
Existing authorized client:
    AT1 scopes: openid profile
    RT1

Request A:
    refresh RT1 -> AT2 / RT2

Request B:
    interactive consent -> AT3 scopes: openid profile calendar.readonly
    possibly RT3

Request C:
    load cached authorized client -> AT1
```

Nếu không có coordination, một `saveAuthorizedClient` của Request A đến muộn có thể **ghi đè authorized client vừa được B lưu** và làm mất scope mới.

### 37.1. Không giả định storage update atomic theo authorization semantics

Một store keyed `(registrationId,principalName)` có thể hỗ trợ last-write-wins, không biết response nào là newer authorization with additional scopes.

### 37.2. Hướng xử lý

- Lưu authorized client với version/authorization epoch nếu cần.
- Re-read/current authorized client trước conditional write.
- Phân biệt refresh của authorization cũ với interactive authorization mới.
- Quản lý refresh token rotation bằng per-client concurrency control.
- Không tự union scopes và giữ token cũ nếu AS không phát token tương ứng.
- Nếu token mới thuộc resource/audience khác, cân nhắc registration/storage key khác.
- Khi user disconnect, ngăn in-flight refresh ghi lại tokens.

### 37.3. Không hạ cấp authorization do stale callback

Một tab mở từ trước có thể hoàn tất consent cho scope hẹp **sau** tab khác đã cấp scope rộng.

Backend phải có policy về ordering/epochs và token storage, không để callback cũ overwrite authorization mới mà không kiểm soát.

---

## 38. Lỗi OAuth2/OIDC và cách phản hồi UX

| Lỗi/symptom | Nguyên nhân có thể | Xử lý |
|---|---|---|
| `access_denied` | User từ chối consent hoặc AS policy cấm | Giữ core session; báo feature chưa được kết nối |
| `consent_required` | Silent request không đủ consent | Cho phép user chủ động bắt interactive consent |
| `interaction_required` | OP cần interaction | Top-level browser redirect có kiểm soát |
| `login_required` | OP cần login/re-login | Bắt interactive login/reauth flow |
| `account_selection_required` | OP chưa chọn được account | Account chooser rồi identity-binding check |
| `invalid_scope` | Scope không được provider/client hỗ trợ | Sửa config/policy; không retry vô hạn |
| `invalid_request` | Tham số customizer sai hoặc unsupported | Kiểm tra prompt/max_age/acr/provider docs |
| `invalid_grant` | Code/refresh token expired/replayed/revoked | Cleanup/reconnect, kiểm tra rotation race |
| `invalid_client` | Client authentication sai | Alert backend, secret rotation/config |
| OIDC `auth_time` thiếu | `max_age` không được gửi/thực thi, OP không compliant | Không đánh dấu step-up thành công |
| OIDC `acr` không đủ | OP không đáp ứng assurance policy | Từ chối thao tác nhạy cảm, hướng dẫn reauth phù hợp |
| Consent success nhưng API 403 | Scope/audience/ownership sai | Kiểm tra token và Resource Server policy |
| Consent success nhưng account đổi | IdP account chooser chọn identity khác | Từ chối binding và giữ local account đúng |
| CSRF 403 tại start-consent | Thiếu/sai CSRF token | Sửa frontend CSRF flow, không disable CSRF |
| Callback `invalid_state` | Mất session, stale tab, state mismatch | Reject callback, restart với intent mới |
| OAuth2 callback đổi auth session | Login pipeline tạo authentication mới | Local principal mapping & pending flow |
| Không có refresh token mới | Provider không cấp mỗi lần consent | Dựa contract; không tự assume |
| Consent cứ lặp | Token store stale, scope không granted, AS policy | Kiểm tra persisted authorized client & scopes |
| API trả 401 sau reauth | Token audience/expiry sai | Không nhầm reauth với API authorization |

### 38.1. Tránh redirect loops

Nếu user liên tục từ chối scope:

```text
Dashboard -> consent -> denied -> dashboard -> consent -> ...
```

thì frontend cần giữ trạng thái `NEEDS_CONSENT` hoặc `DECLINED` và chỉ bắt đầu lại khi user chủ động chọn tính năng.

### 38.2. Lỗi API 403 không phải lúc nào cũng thiếu scope

Orders API có thể trả 403 vì Alice không sở hữu đơn hàng; xin scopes mới sẽ không giải quyết được. Phân biệt OAuth2 Bearer error với application-specific business denial.

---

## 39. Kiểm thử custom authorization request

Các test nên xác nhận:

- Login bình thường không bị tự thêm `calendar.readonly`.
- Intent `CALENDAR_READ` hợp lệ thêm đúng scope.
- Client registration khác không nhận parameter Google.
- OAuth2 `state` giữ đúng correlation.
- PKCE và OIDC attributes cần thiết không bị mất.
- Không nhận arbitrary scopes trong query/JSON.
- Pending intent hết hạn không tạo consent.
- User B không dùng được intent của user A.
- Hai tabs không overwrite trạng thái.
- Tenant bị disable không thể tiếp tục flow.
- Callback từ wrong issuer hoặc wrong subject bị từ chối.

### 39.1. Test builder bảo toàn state

Ví dụ JUnit 5:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.LinkedHashSet;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

class IncrementalRequestTest {

    @Test
    void addsScopeWithoutReplacingState() {
        OAuth2AuthorizationRequest original =
            OAuth2AuthorizationRequest.authorizationCode()
                .authorizationUri("https://id.example/authorize")
                .clientId("portal-client")
                .redirectUri("https://portal.example/callback")
                .scopes(Set.of("openid", "profile"))
                .state("random-state-for-test")
                .build();

        Set<String> scopes = new LinkedHashSet<>(
            original.getScopes()
        );
        scopes.add("calendar.readonly");

        OAuth2AuthorizationRequest modified =
            OAuth2AuthorizationRequest.from(original)
                .scopes(scopes)
                .additionalParameters(params ->
                    params.put(
                        "include_granted_scopes", "true"
                    )
                )
                .build();

        assertThat(modified.getState())
            .isEqualTo(original.getState());

        assertThat(modified.getScopes())
            .contains("openid", "profile", "calendar.readonly");
    }
}
```

Test này kiểm tra request builder behavior. Nó **không** chứng minh OP đồng ý cấp scope, không kiểm tra callback state validation và không kiểm tra actual granted scopes.

### 39.2. Integration test với Authorization Server

Cần môi trường có provider behavior thực tế hoặc contract mock đủ sát để kiểm tra:

1. Consent request thành công.
2. AS không cấp scope ngoài client policy.
3. User từ chối.
4. Partial scopes nếu provider hỗ trợ.
5. Wrong account ở OP account chooser.
6. Refresh token response và reuse/rotation.
7. Token audience/scope được Resource Server chấp nhận.
8. Admin consent tenant restrictions.
9. Re-consent sau revoke.
10. Callback bắt đầu trên tab cũ.

Không chỉ mock `OAuth2AuthorizedClientManager` luôn trả fake token rồi khẳng định “đã test incremental authorization”.

---

## 40. Kiểm thử tái xác thực và step-up

Các trường hợp cần có:

| Trường hợp | Kỳ vọng |
|---|---|
| `max_age=300`, `auth_time` mới 1 phút | Có thể đạt freshness nếu các checks khác pass |
| `max_age=300`, `auth_time` cũ 2 giờ | Không đạt |
| `max_age=0`, ID Token không có `auth_time` | Không đạt |
| `auth_time` ở tương lai vượt clock skew | Từ chối |
| `acr` thấp hơn yêu cầu | Không đạt step-up |
| User đăng nhập provider account khác | Không đạt |
| Tenant bị vô hiệu hóa giữa redirect/callback | Không đạt |
| `state` mismatch | Reject |
| Pending intent đã consumed | Reject replay |
| Step-up chỉ dành cho operation A, dùng cho B | Reject |
| Step-up hết hạn | Reject |
| Local account disabled sau callback | Reject |
| OP trả interaction error | Không tự đánh dấu verified |
| Có consent scope nhưng không đạt step-up | Không cho thao tác nhạy cảm |
| Đạt step-up nhưng không có API scope | Không gọi API cần scope |

### 40.1. `MockMvc` và Spring Security Test

Spring Security Test có thể mô phỏng OIDC login:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Ví dụ khái niệm:

```java
mockMvc.perform(
    post("/api/features/calendar/connect")
        .with(oidcLogin())
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"feature\":\"CALENDAR_READ\"}")
).andExpect(status().is2xxSuccessful());
```

Cần chuẩn bị MockMvc, security filter chain, approved feature policy và intent storage để test hoàn chỉnh. `oidcLogin()` chỉ **mock Authentication**, không tự thực hiện browser redirect/code exchange hoặc validate OIDC signatures, state, nonce và `auth_time` từ AS thật.

### 40.2. CSRF negative test

Cùng POST nhưng thiếu `.with(csrf())` phải bị từ chối nếu security chain dùng cookie session CSRF policy mặc định. Không tắt CSRF chỉ để test pass.

---

## 41. WebFlux/reactive: cùng policy, APIs khác

Trong Spring WebFlux, ý tưởng giống hệt:

```text
Browser -> WebFlux BFF -> Authorization Server -> Resource Server
```

Nhưng stack đổi:

| Servlet/MVC | WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `DefaultOAuth2AuthorizationRequestResolver` | `DefaultServerOAuth2AuthorizationRequestResolver` |
| `OAuth2AuthorizationRequestResolver` | `ServerOAuth2AuthorizationRequestResolver` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `SecurityContextHolder` | `ReactiveSecurityContextHolder` |

### 41.1. Reactive authorization request customization

WebFlux có resolver tương ứng cho `ServerWebExchange` và publisher result. Có thể điều chỉnh additional parameters/scopes theo **trusted server-side intent** mà không block Reactor event loop.

Đừng copy một Servlet resolver đọc `HttpServletRequest` vào WebFlux hoặc gọi `.block()` để load consent state.

### 41.2. Reactor Context không là consent store

`ReactiveSecurityContextHolder` cho phép đọc Authentication trong subscription, nhưng:

- Không persist OAuth2 consent history.
- Không thay `ServerOAuth2AuthorizedClientRepository`.
- Không tự quản lý refresh token rotation.
- Không chứng minh người dùng vừa xác thực MFA.

Các consent/step-up policy và token storage vẫn phải được triển khai riêng.

---

## 42. Consent, reauth và session lifecycle

Một user session có nhiều đồng hồ:

```text
BFF session:
    idle timeout 30 phút

Access token:
    expires_in 10 phút

Refresh token:
    policy của AS

OIDC authentication:
    auth_time cách đây 45 phút

Step-up intent:
    TTL 5 phút

Step-up proof:
    valid cho một action hoặc ngắn hạn
```

**Chúng không phải cùng một lifetime.**

### 42.1. Refresh access token không phải reauthentication

AS có thể cấp access token mới bằng refresh token **mà user không tương tác**. Điều đó không cập nhật sự kiện `auth_time` theo nghĩa user chủ động xác thực lại.

### 42.2. Browser reload không phải reauthentication

SPA reload trang và tạo network requests mới không chứng minh user nhập lại credentials.

### 42.3. Session ID rotation không phải MFA

Spring Security có session fixation protection có thể đổi session ID sau login, nhưng session ID mới không chứng minh authentication assurance cao hơn.

### 42.4. Consent mới không nhất thiết làm auth_time mới

Người dùng có thể đồng ý cho thêm scope khi OP session đã xác thực từ trước mà không phải login lại.

---

## 43. Các anti-pattern cần tránh

### Anti-pattern 1: Xin tất cả scopes lúc đăng nhập

```text
openid profile email calendar.write drive.full_access billing.admin ...
```

nếu người dùng chỉ muốn xem dashboard. Cần feature-level incremental authorization.

### Anti-pattern 2: Đồng nhất consent với role

```text
User consented -> ROLE_ADMIN
```

Đây là sai security boundary. Consent là quyền API do AS cấp, role là business authorization.

### Anti-pattern 3: `prompt=consent` cho mọi request

Dễ tạo consent fatigue, không tự tăng scope hay bảo đảm refresh token.

### Anti-pattern 4: `prompt=login` được coi là MFA

Login lại có thể không đạt assurance/ACR policy cần thiết.

### Anti-pattern 5: Dùng `iat` thay `auth_time`

Token mới được phát không chứng minh vừa xác thực lại user.

### Anti-pattern 6: Thêm scope bằng frontend input tự do

Dễ mở rộng quyền ngoài policy và gây consent phishing.

### Anti-pattern 7: Không kiểm tra identity sau callback

User có thể chọn tài khoản provider khác rồi backend gán token sai internal account.

### Anti-pattern 8: Ghi đè OAuth2 state

Tự tạo state đoán được hoặc sửa redirect URI/PKCE/nonce làm hỏng bảo vệ flow.

### Anti-pattern 9: Dùng refresh grant để xin quyền chưa được cấp

Refresh không tự vượt consent/AS policy.

### Anti-pattern 10: Trả token về JavaScript trong BFF

Phá ranh giới backend-only token storage.

### Anti-pattern 11: Consent denied thì logout toàn ứng dụng

Một feature bị từ chối không nhất thiết làm local login invalid.

### Anti-pattern 12: API trả 403 thì tự chuyển về consent

403 có thể là resource ownership hoặc tenant policy. Không tự lặp grant flow.

### Anti-pattern 13: Reauth được dùng cho mọi hành động về sau

Step-up proof cần TTL, session/account và đôi khi transaction binding.

### Anti-pattern 14: Mặc định mọi OIDC providers hiểu `include_granted_scopes`

Đó là parameter riêng của Google và providers có extension tương thích.

### Anti-pattern 15: Coi scope requested là scope granted

Phải kiểm tra authorization/token response thực tế.

### Anti-pattern 16: Xóa một authorization cũ mà không xét refresh-token rotation

Có thể làm mất grants hợp lệ hoặc gây race/invalid_grant.

### Anti-pattern 17: Dùng token của provider account B cho internal account A

Cần `(iss,sub)`/stable provider ID check và authorized client ownership.

### Anti-pattern 18: Tắt CSRF để POST start-consent hoạt động

Browser-cookie BFF vẫn phải chống CSRF; OAuth2 `state` không thay API CSRF token.

---

## 44. Tình huống vận dụng

### Tình huống A — User chỉ muốn đọc dashboard

**Hành vi phù hợp:** login với scopes tối thiểu, chưa yêu cầu quyền calendar/drive.

### Tình huống B — User lần đầu bật Calendar Sync

**Hành vi:** ứng dụng giải thích quyền, tạo pending intent, redirect tới IdP xin thêm calendar scope, lưu token chỉ khi grant hợp lệ.

### Tình huống C — User từ chối Calendar Sync

**Hành vi:** giữ dashboard hoạt động, không ép logout hoặc spam consent screen.

### Tình huống D — Google trả token có combined scopes

**Hành vi:** dựa trên provider contract (`include_granted_scopes=true` khi phù hợp), xác minh scopes thực cấp và lưu authorized client an toàn.

### Tình huống E — Provider không trả refresh token sau re-consent

**Hành vi:** không tự giả định refresh token sẽ xuất hiện; giữ hoặc thay token record theo contract/authorization semantics.

### Tình huống F — API trả 403 do Alice không sở hữu tài nguyên

**Hành vi:** từ chối business operation, không xin scope mới để vượt quyền.

### Tình huống G — User chọn Bob ở Google account chooser

**Hành vi:** check `(iss,sub)` mismatch, không lưu token Bob dưới session Alice.

### Tình huống H — Đổi tài khoản thanh toán sau 8 giờ

**Hành vi:** yêu cầu OIDC reauthentication/step-up theo policy, kiểm tra `auth_time`, ACR/MFA nếu cần.

### Tình huống I — OP trả ID Token có `iat` mới nhưng `auth_time` cũ

**Hành vi:** không coi là fresh login; token issue time không thay auth event time.

### Tình huống J — Provider không hỗ trợ `acr_values=...`

**Hành vi:** dùng auth assurance mechanism được provider xác nhận hỗ trợ hoặc app-local step-up; không đánh dấu MFA thành công.

### Tình huống K — `prompt=none` trả `interaction_required`

**Hành vi:** không bypass consent; hiển thị nút user chủ động interactive authorization.

### Tình huống L — Tenant chặn scope `billing.write`

**Hành vi:** SaaS policy từ chối flow dù provider có thể cấp scope.

### Tình huống M — Hai tabs xin scopes khác nhau đồng thời

**Hành vi:** intent keyed by OAuth state, token storage chống stale overwrite.

### Tình huống N — Logout sau khi consent

**Hành vi:** local session kết thúc; authorized client/token revocation theo policy riêng.

### Tình huống O — User revoke app ở provider

**Hành vi:** API/refresh failures được xử lý, mark disconnected và chỉ cho user re-consent khi muốn.

### Tình huống P — Refresh đồng thời với consent callback

**Hành vi:** đảm bảo callback grant mới không bị refresh token cũ ghi đè.

### Tình huống Q — Step-up chỉ cho một giao dịch

**Hành vi:** pending proof gắn transaction ID, TTL ngắn, consume một lần.

### Tình huống R — SPA cố đọc refresh token từ backend

**Hành vi:** không có token endpoint trả raw tokens; BFF proxy nghiệp vụ giữ credentials phía server.

### Tình huống S — Admin đã đồng ý thay user tại doanh nghiệp

**Hành vi:** dựa trên provider/admin consent policy, không suy mọi end-user đã cấp quyền cá nhân cho mọi scope.

### Tình huống T — Token có scope đúng nhưng audience sai

**Hành vi:** không gọi API bằng token sai audience; xin authorization cho đúng resource/client.

---

## 45. Câu hỏi tự kiểm tra

**1. Consent và authentication có giống nhau không?**  
Không. Consent cho phép OAuth2 client sử dụng quyền API; authentication xác định ai đang đăng nhập.

**2. Incremental authorization có phải một grant type mới?**  
Không. Thường là một Authorization Code Flow mới với scopes bổ sung.

**3. Vì sao không xin mọi scope ngay khi login?**  
Least privilege, quyền theo ngữ cảnh và tránh gây consent fatigue.

**4. `prompt=consent` làm gì?**  
Yêu cầu tương tác consent ở OP theo semantics/provider policy, không tự cấp thêm quyền.

**5. `prompt=login` khác `prompt=consent` thế nào?**  
Đầu yêu cầu reauthentication; sau yêu cầu consent.

**6. `max_age=0` có ý nghĩa gì?**  
Theo OIDC Core, yêu cầu active reauthentication, tương đương về semantics với `prompt=login`.

**7. Khi dùng `max_age`, ID Token cần claim nào?**  
`auth_time`.

**8. Vì sao `iat` không thay `auth_time`?**  
`iat` là thời điểm token phát hành, không phải thời điểm user được OP xác thực.

**9. `acr_values` có tự bảo đảm MFA không?**  
Không. Cần provider contract và kiểm tra `acr`/assurance thực tế.

**10. Có thể cho browser tự chọn `scope=admin.write` không?**  
Không. Dùng server-side feature-to-scope allowlist và business authorization.

**11. `include_granted_scopes=true` có dùng với mọi provider không?**  
Không. Đây là tính năng được Google hỗ trợ; provider khác có semantics khác.

**12. Callback consent nên kiểm tra gì ngoài `state`?**  
PKCE/nonce, registration/issuer, intent, session/account/tenant binding, granted scopes và identity.

**13. Vì sao cần kiểm tra `(iss,sub)` sau callback?**  
Người dùng có thể chọn account provider khác, gây gán token sai internal user.

**14. Scope được request có chắc được cấp không?**  
Không. AS/user/policy quyết định scopes thực cấp.

**15. `OAuth2AuthorizedClient` để làm gì?**  
Lưu client registration và access/refresh tokens theo principal, phục vụ API calls.

**16. Refresh token có tự xin được scope mới chưa được consent không?**  
Không theo nguyên tắc OAuth2 authorization; cần interactive authorization hoặc provider-specific hợp đồng.

**17. API trả 403 có nên luôn xin lại consent?**  
Không. Phải phân biệt insufficient_scope với business authorization denial.

**18. Logout có tự revoke mọi token provider không?**  
Không mặc định. Local session logout và token revocation khác nhau.

**19. XSS có bị BFF chặn hoàn toàn không?**  
Không. BFF giảm raw token exposure, nhưng XSS vẫn có thể gọi API bằng session.

**20. Vì sao step-up phải có TTL/transaction binding?**  
Tránh một xác minh một lần trở thành quyền lâu dài cho mọi hành động.

**21. `prompt=none` có cho phép bỏ qua consent không?**  
Không. OP sẽ trả lỗi nếu không thể đáp ứng không tương tác.

**22. Một account có nhiều providers có cùng assurance không?**  
Không. Mỗi provider/method có authentication provenance và trust policy riêng.

**23. Consent callback có thể thay local Authentication không?**  
Có. OAuth2 Login callback có thể đặt Authentication mới; app phải giữ account binding đúng.

**24. Ai quyết định business role sau consent?**  
Application/Resource Server authorization policy, không phải consent screen đơn thuần.

**25. Những tests cần thiết nhất là gì?**  
Request scope/params, state/PKCE, identity binding, granted scopes, reauth auth_time/acr, denied consent, token lifecycle và tenant isolation.

---

## 46. Ghi nhớ trọng tâm

| Thành phần | Ý nghĩa |
|---|---|
| OAuth2 consent | User/AS cho phép client dùng quyền API |
| Scope | Phạm vi client yêu cầu/được cấp, không là local role |
| Incremental authorization | Xin quyền tại thời điểm cần chức năng |
| Authorization Code Flow | Luồng thường được dùng lại cho scopes mới |
| `prompt=consent` | Yêu cầu consent interaction ở OP |
| `include_granted_scopes=true` | Google-specific hỗ trợ scopes tích lũy |
| `prompt=login` | Yêu cầu OP reauthenticate End-User |
| `max_age` | Giới hạn age của active OP authentication |
| `max_age=0` | Yêu cầu active reauthentication |
| `auth_time` | Thời điểm OP xác thực End-User |
| `acr` | Authentication context class |
| `amr` | Authentication methods references |
| `acr_values` | Yêu cầu context classes, cần provider contract |
| `prompt=none` | Không tương tác; trả lỗi khi interaction cần thiết |
| `OAuth2AuthorizationRequestResolver` | Điểm mở rộng tạo authorization request |
| `DefaultOAuth2AuthorizationRequestResolver` | Resolver Servlet chuẩn, có customizer |
| `OAuth2AuthorizationRequest.from(...)` | Clone và sửa scopes/additional parameters |
| `state` | Bảo vệ authorization response correlation |
| PKCE | Gắn authorization code với verifier |
| OIDC `nonce` | Gắn ID Token với authentication request |
| CSRF token | Bảo vệ POST tạo intent hoặc thay đổi setting |
| Pending consent intent | Server-side state gắn account/tenant/feature/OAuth state |
| `OAuth2AuthorizedClient` | Access/refresh token và registration/principal |
| `OAuth2AuthorizedClientManager` | Authorize/refresh theo providers đã cấu hình |
| Granted scopes | Quyền AS đã thực sự cấp, cần kiểm tra |
| Audience | Resource đích của access token |
| Reauthentication | Xác minh lại identity, không tự cấp scopes |
| Step-up | Nâng freshness/assurance cho hành động nhạy cảm |
| BFF | Browser giữ session cookie; tokens ở backend |
| Token revocation | Thao tác riêng với AS nếu hỗ trợ |
| Tenant policy | Kiểm soát scopes, registrations và quyền nghiệp vụ |
| `insufficient_scope` | Bearer token thiếu quyền API được yêu cầu |
| `login_required` | OP cần user authentication |
| `consent_required` | OP cần interactive consent |
| `interaction_required` | OP không thể đáp ứng yêu cầu silent |
| Provider contract | Quyết định chính xác semantics và extension parameters |

### Kết luận

**Consent**, **incremental authorization** và **tái xác thực** là ba quá trình bổ sung nhưng không thể thay thế cho nhau trong Spring Security OAuth 2.0/OIDC Client:

1. **Consent:** AS và user cho OAuth2 client quyền truy cập resource với những scopes cụ thể.
2. **Incremental authorization:** ứng dụng xin những scopes mới khi người dùng thực sự cần tính năng; thường dùng Authorization Code Flow mới và provider-specific parameters.
3. **Reauthentication/step-up:** ứng dụng yêu cầu user chứng minh lại identity và mức assurance đủ mới trước hành động nhạy cảm, thường qua `prompt=login`, `max_age`, `auth_time`, `acr`/`amr` theo OIDC contract.

Một thiết kế an toàn phải **khởi tạo flow theo user intent**, bảo vệ `state`/PKCE/nonce và CSRF, **xác minh cùng provider identity sau callback**, lưu tokens dưới đúng authorized client owner, kiểm tra **granted scopes** thay vì scopes đã xin, và áp local business authorization tại Resource Server.

**Đừng coi một consent screen đã đóng là bằng chứng user có quyền API, và đừng coi một ID Token mới phát là bằng chứng vừa xác thực MFA.** Chỉ những quyền và authentication evidence đã được xác minh theo đúng provider contract mới đủ cho quyết định bảo mật.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorization Grant Support: Customizing the Authorization Request](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html) — `OAuth2AuthorizationRequestResolver`, `prompt` và authorization request customization.
- [Spring Security — Advanced OAuth2 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html) — OAuth2 Login callbacks, authorization request, user services và handlers.
- [Spring Security — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html) — managers, repositories, token lifecycle.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — CSRF với browser session.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — sessions và reauthentication lifecycle.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — `prompt`, `max_age`, `auth_time`, `acr`, `amr`, OIDC authentication.
- [Google — OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server) — incremental authorization và `include_granted_scopes`.
- [Google — OAuth2 Best Practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices) — consent theo ngữ cảnh và handling partial grants.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749) — scopes, authorization code, token responses và errors.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750) — `insufficient_scope` và Bearer errors.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636) — code interception protection.
- [RFC 8707 — OAuth 2.0 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707) — target resource/audience restriction.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009) — token revocation khi AS hỗ trợ.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700) — OAuth2 security considerations.
- [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) — OP logout và khác biệt với token revocation.
