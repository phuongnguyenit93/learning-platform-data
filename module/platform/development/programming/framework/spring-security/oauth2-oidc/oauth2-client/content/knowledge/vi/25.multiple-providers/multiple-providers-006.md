# 25.6. Liên kết nhiều danh tính với một tài khoản nội bộ

## 1. Bài toán: Một người, nhiều nhà cung cấp danh tính

Trong một ứng dụng **Spring Security OAuth 2.0/OIDC Client**, người dùng có thể đăng nhập qua nhiều Identity Providers (IdP), chẳng hạn một OpenID Provider của công ty, một tài khoản Google hoặc một nhà cung cấp OAuth2 khác. Tuy vậy, ứng dụng có thể muốn người dùng nhìn thấy **một tài khoản nội bộ duy nhất**: cùng hồ sơ, đơn hàng, lịch sử và quyền nghiệp vụ.

Ví dụ:

```text
                 TÀI KHOẢN NỘI BỘ
                 user_id = 7b6f...
                 displayName = Alice
                 tenant_id = tenant-a
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
   Google OIDC     Corporate OIDC   GitHub OAuth2
   iss+sub = G1    iss+sub = C9     providerUserId=4421
          |             |             |
          +-------------+-------------+
                        |
                        v
                 Alice đăng nhập
          -> cùng user_id nội bộ
          -> dữ liệu/authorization ứng dụng
```

**Liên kết danh tính (account linking/identity linking)** là việc ứng dụng tạo ra một quan hệ có kiểm soát:

```text
External Identity  --->  Internal Account
```

Đây không chỉ là thao tác “so sánh hai email giống nhau”. Nó là **quyết định bảo mật**: người đã xác thực bằng một external identity sẽ có khả năng đăng nhập hoặc thực hiện hành động dưới quyền của internal account được liên kết.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **tài khoản nội bộ**, **external identity**, **OAuth2/OIDC login session** và **OAuth2AuthorizedClient**.
2. Sử dụng định danh ổn định cho OIDC bằng cặp **`(iss, sub)`**.
3. Xác định khóa định danh cho provider OAuth2 không phải OIDC.
4. Hiểu vì sao **không tự liên kết theo email**, kể cả email được xác minh, khi chưa có chính sách rõ ràng và chứng cứ bổ sung.
5. Thiết kế luồng **login bằng identity đã liên kết** và luồng **link thêm identity mới** riêng biệt.
6. Yêu cầu quyền kiểm soát tài khoản nội bộ và identity mới; phòng account takeover.
7. Dùng `state`, PKCE, OIDC `nonce`, CSRF và kiểm tra xác thực gần đây.
8. Thiết kế schema SQL, unique constraints và transaction cho cạnh tranh liên kết.
9. Hiểu điểm mở rộng Spring Security như `OidcUserService`, `DefaultOAuth2UserService`, success handler và repository/service.
10. Ánh xạ external identity sang **local principal** nhất quán.
11. Phân biệt identity linking với việc lưu access/refresh token để gọi API provider.
12. Thiết kế unlink, logout, revoke, account recovery, đa tenant và audit.
13. Kiểm thử những tình huống va chạm hoặc tấn công.

> Phạm vi: nhiều provider trong **Spring Security OAuth 2.0/OIDC Client**. Ví dụ sử dụng Spring Boot/Spring Security trên Servlet MVC; WebFlux được đối chiếu ở phần riêng. Tên provider, domain và danh tính minh họa không đại diện cho cấu hình sản phẩm thực tế.

---

## 2. Phân biệt bốn lớp identity và authorization

### 2.1. Internal account

Một account ứng dụng thường có ID do chính hệ thống quản lý:

```text
internal_user_id = 7b6f51dc-...
status = ACTIVE
tenant_id = tenant-a
profile = ...
```

ID này quyết định ownership của dữ liệu nghiệp vụ và là đối tượng mà ứng dụng dùng để cấp quyền.

**Một internal account không nhất thiết tương đương một external identity.**

### 2.2. External identity

Một danh tính đã được provider xác thực, ví dụ:

```text
OIDC issuer = https://login.corporate.example
OIDC sub    = 00u3abc...

Google issuer = https://accounts.google.com
Google sub    = 109101...
```

Trong OIDC, `sub` chỉ có ý nghĩa đầy đủ trong namespace của `iss`. Hai issuers có thể cùng phát `sub="123"` cho hai người khác nhau.

### 2.3. Authentication của Spring Security

Sau khi đăng nhập, Spring Security có thể tạo:

```java
OAuth2AuthenticationToken
```

với principal là:

```java
OidcUser  // OIDC provider
OAuth2User // OAuth2 login không OIDC
```

`Authentication.getName()` thường phản ánh tên của principal, nhưng **không được tự giả định đó là internal account ID** khi chưa cấu hình bước ánh xạ.

### 2.4. OAuth2AuthorizedClient

`OAuth2AuthorizedClient` gồm client registration, principal name, access token và có thể refresh token.

Nó phục vụ việc **gọi API phía provider/Resource Server**, không phải bản ghi sở hữu tài khoản nội bộ.

| Thành phần | Chứa gì? | Được dùng để làm gì? |
|---|---|---|
| `InternalAccount` | Local immutable ID, trạng thái, business roles | Dữ liệu và quyền của ứng dụng |
| `ExternalIdentity` | Provider namespace, stable subject, liên kết tới account | Xác định account khi user login bằng provider |
| `Authentication` | Principal hiện tại, authorities, auth details | Spring Security authentication/authorization |
| `OAuth2AuthorizedClient` | Registration, access/refresh tokens, expiry | Gọi downstream APIs theo OAuth2 |

**Không nên đồng nhất `OAuth2AuthorizedClient.getPrincipalName()` với bảng external identities**, trừ khi hệ thống cố ý thiết kế mapping nhất quán và đã kiểm tra tính bảo mật.

---

## 3. Định danh OIDC đáng tin: `(iss, sub)`

Trong OpenID Connect, ID Token chứa:

```json
{
  "iss": "https://login.corporate.example",
  "sub": "alice-00u3",
  "aud": "portal-client",
  "exp": 1980000000,
  "iat": 1979996400
}
```

Đối với **identity đã được xác minh qua OIDC login**, nên sử dụng:

```text
identity_key = (validated_issuer, validated_subject)
```

### 3.1. Tại sao phải có issuer?

Ví dụ:

```text
Provider A: iss=https://id-a.example, sub=123
Provider B: iss=https://id-b.example, sub=123
```

Hai identity này **không phải cùng một người** chỉ vì `sub` bằng nhau.

### 3.2. Tại sao không dùng email?

Email có thể:

- Thay đổi khi người dùng đổi tên hoặc công ty.
- Không được provider trả về.
- Chưa được xác minh.
- Được tái sử dụng cho nhân viên khác sau khi người cũ rời tổ chức.
- Trùng giữa nhiều tài khoản provider.
- Không có cùng nghĩa với quyền sở hữu internal account.

Ngay cả nếu `email_verified=true`, điều đó thông thường chỉ là tuyên bố của provider theo cơ chế của nó tại một thời điểm. Nó **không phải bằng chứng ứng dụng phải gán identity mới vào account hiện hữu cùng email**.

### 3.3. Subject dạng pairwise

Một OpenID Provider có thể phát **pairwise subject identifiers**: cùng người dùng nhưng `sub` có thể khác giữa các OAuth2 clients/sector identifiers.

Do đó:

```text
sub từ client A != sub từ client B
```

không nhất thiết có nghĩa hai người khác nhau.

Không tự nối chúng bằng email nếu chưa có flow linking đã xác minh. Xem issuer và subject theo từng client/sector trong provider contract.

### 3.4. Issuer phải được xác minh, không phải dữ liệu browser tự gửi

Chỉ tin cặp `(iss, sub)` sau khi Spring Security/OIDC client kiểm tra ID Token theo yêu cầu: signature/JWK, issuer, audience, expiry, state/nonce/các điều kiện tương ứng.

Không chấp nhận:

```text
POST /api/link
{"issuer": "...", "subject": "..."}
```

rồi ghi thẳng vào DB. Caller có thể tự đặt `sub` của người khác.

---

## 4. Provider OAuth2 không hỗ trợ OIDC: dùng stable provider user ID

Một số provider hỗ trợ OAuth2 Login nhưng không cung cấp OIDC ID Token. `DefaultOAuth2UserService` có thể gọi UserInfo/user endpoint để nhận attributes.

Ví dụ provider trả:

```json
{
  "id": 44217820,
  "login": "alice-dev",
  "email": "alice@example.com",
  "name": "Alice"
}
```

Nếu provider công bố `id` là định danh tài khoản ổn định, có thể xây:

```text
namespace = oauth2:github
subject   = "44217820"
```

Nhưng phải hiểu contract của provider:

- User ID có ổn định khi đổi username không?
- Có tái sử dụng ID không?
- Có nhiều enterprise instances/hosts không?
- User endpoint có thật sự được gọi bằng access token provider cấp không?
- Response có được xác thực qua HTTPS với TLS đúng không?
- Cơ chế organization/tenant có làm identity namespace khác đi không?

### 4.1. Không dùng display name hoặc username nếu ID ổn định có sẵn

Một tài khoản có thể đổi:

```text
login = alice-dev
```

thành:

```text
login = alice-platform
```

nhưng numeric user ID vẫn giữ nguyên. Nếu khóa bằng `login`, hệ thống có thể coi đó là hai identities, hoặc khi username được chuyển cho người khác sẽ dẫn đến mapping sai.

### 4.2. Một "provider" có thể có nhiều instances

Ví dụ GitHub.com và GitHub Enterprise Server riêng:

```text
oauth2:github.com
oauth2:github.enterprise.example
```

Không gộp user IDs từ hai instances vào cùng namespace. Đối với OIDC, issuer URI thường đã cung cấp namespace này.

### 4.3. Không tự tin một claim từ provider chưa kiểm chứng

Nếu `OAuth2User` được dựng từ dữ liệu frontend gửi lên hoặc một userinfo endpoint không được xác thực, không được dùng nó để link account.

Provider identity cần đến từ một OAuth2/OIDC flow hoàn tất và nguồn claims/attributes đáng tin theo hợp đồng của provider.

---

## 5. Hai luồng phải tách: đăng nhập và liên kết

### 5.1. Luồng A: đăng nhập bằng một identity đã liên kết

```text
User chọn "Sign in with Google"
    |
    v
OAuth2/OIDC login thành công
    |
    v
IdentityKey = (iss, sub)
    |
    v
Lookup external_identity
    |
    +-- Có link tới internalUserId U
    |      -> Tạo local Authentication cho U
    |      -> Dùng business roles/tenant của U
    |
    +-- Không có link
           -> Quy trình tạo account mới,
              hoặc yêu cầu user đăng nhập account hiện tại
              rồi thực hiện explicit linking
```

**Không làm bước “không thấy identity thì tìm email giống rồi đăng nhập account đó”.** Đây là một nguồn account takeover rất phổ biến.

### 5.2. Luồng B: liên kết thêm identity với account đã đăng nhập

```text
User đã đăng nhập account nội bộ U
    |
    v
Bấm "Liên kết Google"
    |
    v
BFF kiểm tra U, CSRF, xác thực gần đây/step-up
    |
    v
Bắt đầu OAuth2/OIDC authorization cho Google
    |
    v
Google xác thực identity G
    |
    v
BFF xác minh state, PKCE, nonce, callback
    |
    v
External identity G chưa gắn account khác?
    |
    +-- Có: từ chối, không chiếm link
    |
    +-- Không: ghi (G -> U) atomically
               audit + thông báo
```

Đây là **quyết định có chủ ý của chủ account U**, cộng với **chứng cứ user điều khiển external identity G**.

### 5.3. Vì sao không dùng một callback “thấy email trùng thì tự link”?

Nếu account U chứa dữ liệu nhạy cảm và provider X cấp được email giống U do cấu hình sai hoặc email tái sử dụng, attacker có thể đăng nhập identity X rồi bị hệ thống auto-link tới U.

Một khi đã link, attacker có thể tiếp tục login như U về sau, dù U đã logout.

**Quy tắc an toàn mặc định:** chỉ auto-login với external identity **đã được link trước**; identity mới thì tạo account mới hoặc dùng một explicit account-linking flow với kiểm tra quyền.

---

## 6. Threat model của account linking

Các rủi ro cần xem trước khi viết controller:

| Mối đe dọa | Ví dụ | Biện pháp |
|---|---|---|
| Account takeover bằng email | Attacker có provider account trùng email U | Không auto-link theo email |
| Login CSRF / account confusion | Callback identity của attacker vào phiên victim | OAuth2 `state` + session binding + intent |
| Link CSRF | Website lạ khiến victim tự link identity | CSRF protection cho hành động bắt đầu link |
| Stolen session | Attacker có session cookie U, thêm identity riêng | Step-up/re-authenticate tài khoản U |
| IdP mix-up | Response từ provider B bị xử lý như A | Registration/issuer/callback binding và validation |
| Subject collision | Hai issuers cùng `sub=123` | Key `(iss, sub)` |
| Stale provider email | Email cũ được tái sử dụng | Không dùng email làm khóa ownership |
| Two-account race | Hai requests cùng gắn identity G vào U và V | Unique constraint + transaction |
| Overly broad session rights | Callback login mới thay user cũ giữa link | Pending intent giữ server-side account U |
| Token theft | Link callback/token bị log hoặc trả browser | Backend-only tokens, redaction |
| Unlink self-lockout | User xóa cách đăng nhập cuối | Chặn hoặc yêu cầu phương án khôi phục |
| Token persistence mismatch | Link xong nhưng token vẫn lưu dưới principal cũ | Quy hoạch authorized client store/mapping |
| Cross-tenant linking | Identity của tenant A gắn account tenant B | Tenant policy và namespace |
| Malicious provider metadata | Dynamic issuer do user chọn | Allowlist và discovery trust |
| Email-based recovery abuse | Chuyển link bằng email không xác minh đủ | Recovery có step-up và policy độc lập |

Không có **một check duy nhất** sửa hết các rủi ro trên. Account linking cần nhiều lớp: authentication, session/CSRF, provider validation, database constraints, business policy và audit.

---

## 7. Bằng chứng kiểm soát cả hai phía

Một link hợp lệ cần **hai điều kiện đồng thời**.

### 7.1. Phía tài khoản nội bộ

Ứng dụng phải biết người bắt đầu link có quyền quản lý account U.

Thông thường:

- Có `Authentication` hợp lệ trong Spring Security session.
- Internal account U còn active.
- User đã đăng nhập gần đây hoặc thực hiện **step-up** bằng MFA/password/passkey theo rủi ro.
- CSRF token hợp lệ cho thao tác bắt đầu link.
- User/tenant policy cho phép thêm provider đó.
- Session không bị thu hồi giữa lúc bắt đầu và hoàn thành.

### 7.2. Phía external identity

Ứng dụng phải có bằng chứng external identity G đã được provider xác thực:

- Redirect tới authorization endpoint đã cấu hình.
- Callback `state` đúng với authorization request.
- PKCE code challenge/verifier theo policy.
- ID Token OIDC hợp lệ, có kiểm tra `iss`, `aud`, expiry, nonce khi áp dụng.
- Với OAuth2 không OIDC, có trustworthy provider user endpoint/stable ID.
- Nếu yêu cầu identity vừa được xác thực, kiểm tra `auth_time`, `max_age`, `acr`/`amr` phù hợp provider.

**Email confirmation không tự thay thế bước xác thực external identity.**

### 7.3. “Prompt login” chưa phải tuyệt đối

OIDC có thể hỗ trợ:

```text
prompt=login
max_age=0
```

nhưng việc thực thi và `auth_time`/`acr` phụ thuộc IdP. Không mặc định chỉ thêm query parameter là đủ chứng minh mới đăng nhập bằng MFA.

Với account linking nhạy cảm, cần kiểm tra authentication freshness và assurance theo IdP contract hoặc yêu cầu app-local step-up bổ sung.

---

## 8. Luồng linking có state ở backend

Trong browser, một thiết kế thường gặp là:

```mermaid
sequenceDiagram
    autonumber
    actor U as Browser / User
    participant App as Spring Boot BFF
    participant Sess as Session / Pending Link Store
    participant IdP as External IdP
    participant DB as Identity DB

    U->>App: POST /api/account/links/start {provider}
    Note over App: Session U authenticated, CSRF, step-up
    App->>Sess: Tạo pending link cho internalUserId U
    App-->>U: Login navigation URL đã allowlist
    U->>App: GET /oauth2/authorization/{registrationId}
    App->>Sess: OAuth2 authorization request; state + PKCE
    App-->>U: 302 tới provider authorize
    U->>IdP: Login/consent với provider
    IdP-->>U: 302 callback code + state
    U->>App: GET /login/oauth2/code/{registrationId}
    App->>Sess: Validate OAuth2 state, session binding, PKCE
    App->>IdP: Back-channel token request
    IdP-->>App: Token / verified OIDC identity
    App->>Sess: Resolve pending link, U, state, expiry
    App->>DB: INSERT external identity -> U (unique)
    DB-->>App: Link created
    App->>Sess: Consume pending link, preserve local login U
    App-->>U: Redirect /settings/connections?linked=1
```

### 8.1. Pending link intent cần dữ liệu gì?

Một bản ghi server-side có thể chứa:

```text
pending_link_id = random opaque value
internal_user_id = U
session_binding = current authenticated session binding
registration_id = google
oauth_state_binding = expected OAuth2 authorization state
created_at = ...
expires_at = ...
consumed = false
required_assurance = recent_login_with_mfa
```

Không lưu refresh token hay client secret trong pending record.

**Mối quan hệ với OAuth2 `state` phải được kiểm chứng.** Nếu app chỉ nhớ “session này đang muốn link Google” nhưng không biết callback tương ứng với authorization request nào, có thể link nhầm khi người dùng mở nhiều tabs hoặc nhiều login flows cạnh tranh.

### 8.2. Không tự thay thế `state` do framework tạo

Spring Security đã quản lý OAuth2 authorization request và `state`. Khi cần gắn business intent, có thể:

- Dùng pending record server-side và tham chiếu tới **state** của authorization request qua custom `OAuth2AuthorizationRequestResolver`/`Repository`.
- Hoặc thiết kế flow riêng có strong transaction binding và một callback route rõ ràng.
- Luôn để Spring Security validate OAuth2 `state` theo giao thức trước khi xử lý identity.

Không tự tạo một `state` tĩnh hoặc dùng user ID/email làm state rồi vô hiệu hóa framework validation.

### 8.3. Session có thể đổi ID sau authentication

Spring Security thường áp dụng session fixation protection khi OAuth2 login hoàn thành. Nếu pending link chỉ gắn vào chuỗi session ID cũ và bỏ qua session migration/change-ID, callback có thể không tìm thấy pending intent.

Dùng một server-side record/session mechanism tương thích lifecycle session, đồng thời xác minh intent vẫn thuộc đúng user/account. Không vì lỗi session migration mà bỏ kiểm tra intent.

---

## 9. Callback có thể thay đổi Authentication hiện tại

Một chi tiết tinh tế: endpoint OAuth2 Login thành công thường thiết lập **Authentication của provider mới**.

Tại success handler:

```text
Trước redirect:
    Browser session được xác thực là InternalAccount U

Sau OAuth2 provider callback:
    Authentication trong filter chain có thể là OAuth2AuthenticationToken(G)
```

Do đó **không được mặc định**:

```java
SecurityContextHolder.getContext().getAuthentication().getName()
```

ở success handler sẽ luôn trả internal user U đã bắt đầu link. Nó có thể trả **external principal G** sau khi provider login thành công.

### 9.1. Lấy internal account gốc từ đâu?

Từ **pending link intent server-side** được tạo trước redirect và gắn với session/state/authentication của U.

Callback cần:

1. Validate OAuth2 callback thành công.
2. Xác định registration/identity G đã được verified.
3. Resolve đúng pending record theo state/session.
4. Xác nhận pending record vẫn hợp lệ, chưa dùng, chưa hết hạn.
5. Xác minh account U còn active và session binding phù hợp.
6. Thực hiện link atomically.
7. Kết thúc flow với **local Authentication của U**, không vô tình đổi browser sang một internal account khác.
8. Consume intent và clear temporary state cả khi thành công hoặc thất bại.

### 9.2. Không dùng email hoặc provider principal để đoán lại U

Sai:

```text
Callback G có email alice@example.com
    -> tìm internal account bằng email
    -> link G vào kết quả
```

Đúng:

```text
PendingLinkIntent đã xác minh: internalUserId U
Verified external identity: G
DB transaction: link G -> U nếu policy và uniqueness cho phép
```

### 9.3. Normal login callback và linking callback không giống nhau

Một callback không có pending link hợp lệ nên được xử lý như **login thông thường** (nếu đó là flow thực sự) hoặc từ chối theo routing policy, **không tự link**.

Một số hệ thống dùng route/authorization request marker riêng cho account linking để tránh nhập nhằng. Nếu dùng chung callback, logic phải phân biệt hai intents rõ ràng và không bao giờ cho `link=true` từ browser query tự biến một login callback thành linking operation.

---

## 10. `state`, PKCE, OIDC `nonce` và CSRF có vai trò khác nhau

| Cơ chế | Bảo vệ |
|---|---|
| OAuth2 `state` | Liên kết authorization response với authorization request; chống login CSRF trong thiết kế phù hợp |
| PKCE | Gắn authorization code với code verifier do client giữ |
| OIDC `nonce` | Gắn ID Token với OIDC authentication request, ngăn replay theo OIDC |
| BFF session cookie | Chứng minh phiên browser–backend; cần bảo vệ session hijacking |
| CSRF token | Bảo vệ POST bắt đầu link/unlink với cookie authentication |
| Step-up/recent authentication | Giảm nguy cơ kẻ lấy được session tự thêm login method |
| Database uniqueness | Ngăn một external identity bị gắn đồng thời vào hai account |
| Authorization check | Đảm bảo U có quyền quản lý account và registration đó |

**Không tắt CSRF protection** cho account settings vì “OAuth2 đã có state”. `state` chỉ bảo vệ OAuth2 flow, không bảo vệ mọi API thay đổi dữ liệu.

### 10.1. Bắt đầu link nên là POST có CSRF

Một endpoint minh họa:

```http
POST /api/account/links/start HTTP/1.1
Cookie: SESSION=...
X-CSRF-TOKEN: ...
Content-Type: application/json

{"registrationId":"google"}
```

Controller kiểm tra:

- Authenticated account.
- Provider nằm trong server-side allowlist.
- CSRF do Spring Security validate.
- Reauthentication/step-up đủ mới.
- Account chưa bị locked/disabled.
- Limits/rate limiting.

Sau đó backend tạo pending intent và trả URL bắt đầu OAuth2 authorization (không trả OAuth2 tokens).

### 10.2. Redirect OAuth2 vẫn là top-level browser navigation

Frontend dùng:

```javascript
window.location.assign(startUrl);
```

để thực hiện Authorization Code Flow, thay vì bắt đầu OAuth2 login bằng một `fetch()` kỳ vọng JSON và để XMLHttpRequest theo redirect tới IdP.

---

## 11. Kiến trúc dữ liệu: account và external identities

Một schema SQL minh họa:

```sql
CREATE TABLE internal_account (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL,
    namespace VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    registration_id VARCHAR(120) NOT NULL,
    provider_display_name VARCHAR(200),
    provider_email VARCHAR(320),
    email_verified BOOLEAN,
    linked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_login_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_external_identity_account
        FOREIGN KEY (account_id)
        REFERENCES internal_account(id),
    CONSTRAINT uq_external_identity_namespace_subject
        UNIQUE (namespace, subject)
);

CREATE INDEX idx_external_identity_account
    ON external_identity(account_id);
```

**Đây là schema custom minh họa**, không phải bảng mặc định của Spring Security hay `JdbcOAuth2AuthorizedClientService`.

### 11.1. `namespace` được xây như thế nào?

Với OIDC:

```text
namespace = validated ID Token iss
subject = validated ID Token sub
```

Với OAuth2 không OIDC:

```text
namespace = canonical provider instance identifier
subject = stable provider user ID from trusted provider API
```

Ví dụ:

```text
namespace = oauth2:github.com
subject = 44217820
```

Không dùng một hằng `provider="oauth2"` cho mọi nhà cung cấp.

### 11.2. Vì sao UNIQUE(namespace, subject) là ràng buộc cốt lõi?

Một external identity phải trỏ tới **tối đa một internal account** tại một thời điểm. Nếu hai accounts đều lưu cùng external identity, lần login sau sẽ không có một account duy nhất để xác định quyền.

Ràng buộc DB là tuyến phòng thủ cuối, bổ sung cho check ở Java. Một check kiểu:

```java
if (!repository.existsByNamespaceAndSubject(...)) {
    repository.save(...);
}
```

**không atomic** giữa hai transactions.

### 11.3. Có nên unique `(account_id, registration_id)`?

Phụ thuộc business rule:

- Nếu mỗi account chỉ được link **một Google identity** cho registration `google`, thêm unique constraint tương ứng.
- Nếu sản phẩm cho phép **hai tài khoản Google khác nhau** thuộc cùng internal account, không thêm constraint đó mà phải thiết kế cách chọn identity/token khi gọi API.
- Nếu một registration có thể trỏ nhiều issuer/provider instances, khóa registration không thay namespace.

Không mặc định Spring `OAuth2AuthorizedClientService` lưu được **nhiều provider identities thuộc cùng một registration và cùng principal name**; mặc định lookup thường theo `(registrationId, principalName)`.

### 11.4. Không coi `provider_email` là unique identity

Có thể lưu email như **attribute hiển thị hoặc gợi ý UX**, nhưng không dùng nó làm khóa unique định danh ngoài. Email đã đổi nên có policy cập nhật, không làm identity link chuyển sang người khác.

### 11.5. Tách secret storage

Không thêm raw refresh token vào bảng `external_identity` chỉ vì dễ query. Nếu cần downstream provider API access, lưu token qua `OAuth2AuthorizedClientRepository/Service` hoặc token vault được bảo vệ. Schema identity mapping và token storage có lifecycle khác nhau.

---

## 12. Transaction và race condition khi nhiều account cùng link một identity

Giả sử Alice (U1) và Bob (U2) gần như đồng thời hoàn thành OAuth2 login cho cùng external identity G:

```text
Request A:
    SELECT G -> không thấy
Request B:
    SELECT G -> không thấy

Request A:
    INSERT G -> U1

Request B:
    INSERT G -> U2
```

Nếu không có uniqueness, G có thể bị gắn cho cả hai accounts.

Với constraint:

```sql
UNIQUE(namespace, subject)
```

chỉ một insert có thể thành công.

### 12.1. Transaction pseudocode

```text
@Transactional linkVerifiedIdentity(
    expectedInternalAccountId,
    verifiedExternalIdentity
):
    1. Load internal account U; require ACTIVE.
    2. Confirm current policy allows this provider/tenant.
    3. Check existing identity by (namespace, subject).
    4. If linked to U:
           -> treat as already linked, if flow proof still valid.
    5. If linked to another account:
           -> reject, never reassign silently.
    6. Otherwise INSERT G -> U.
    7. Flush/commit; unique constraint enforces exclusivity.
    8. Emit audit/domain event after successful commit.
```

Trong production, phải xử lý database unique constraint violation từ race và trả một lỗi business **không tiết lộ account bị liên kết** cho người không có quyền.

### 12.2. Java service minh họa

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdentityLinkingService {

    private final InternalAccountRepository accounts;
    private final ExternalIdentityRepository identities;

    public IdentityLinkingService(
            InternalAccountRepository accounts,
            ExternalIdentityRepository identities) {
        this.accounts = accounts;
        this.identities = identities;
    }

    @Transactional
    public void linkVerified(
            UUID expectedAccountId,
            VerifiedExternalIdentity verified) {

        InternalAccount account = accounts
            .findById(expectedAccountId)
            .orElseThrow(() ->
                new IllegalStateException("Account not available"));

        if (!account.isActive()) {
            throw new IllegalStateException("Account is inactive");
        }

        var existing = identities.findByNamespaceAndSubject(
            verified.namespace(),
            verified.subject()
        );

        if (existing.isPresent()) {
            if (existing.get().getAccountId()
                    .equals(expectedAccountId)) {
                return; // Idempotent nếu caller đã được xác thực đúng.
            }
            throw new IdentityAlreadyLinkedException();
        }

        ExternalIdentity identity = new ExternalIdentity(
            UUID.randomUUID(),
            account.getId(),
            verified.namespace(),
            verified.subject(),
            verified.registrationId(),
            Instant.now()
        );

        identities.saveAndFlush(identity);
    }
}
```

`InternalAccount`, `ExternalIdentity`, repositories, exception và `VerifiedExternalIdentity` là types do ứng dụng định nghĩa. Đây là **khung logic transaction**, không phải một ứng dụng JPA độc lập có thể chạy ngay.

Trong flow thật, caller chỉ được gọi `linkVerified` **sau** khi đã kiểm tra pending intent, CSRF/step-up và external identity validation. `VerifiedExternalIdentity` phải được tạo bởi trusted authentication infrastructure, không deserialize trực tiếp từ frontend JSON.

### 12.3. Xử lý unique conflict ở transaction boundary

Nếu `saveAndFlush` gặp unique violation, transaction có thể bị đánh dấu rollback-only. Không bắt exception rồi tiếp tục làm nhiều DB writes trong **cùng transaction hỏng**.

Có thể:

- Để transaction rollback rồi map `DataIntegrityViolationException` tại API/service boundary bên ngoài.
- Đọc lại identity trong transaction mới nếu cần phân biệt idempotent và conflict.
- Không tự động chuyển link sang account đang yêu cầu.

### 12.4. Idempotency không phải re-link

Nếu request link G→U được retry sau khi DB commit nhưng HTTP response mất, có thể trả “đã liên kết” khi **G vẫn thuộc U** và proof/session policy hợp lệ.

Nếu G hiện thuộc V, retry của U **không được xóa G→V**. Việc chuyển quyền sở hữu là một workflow khác và cần chứng cứ mạnh hơn.

---

## 13. Thiết kế `VerifiedExternalIdentity` làm ranh giới dữ liệu

Một kiểu nội bộ có thể là:

```java
public record VerifiedExternalIdentity(
    String namespace,
    String subject,
    String registrationId,
    String displayName,
    String email,
    boolean emailVerified
) {
    public VerifiedExternalIdentity {
        if (namespace == null || namespace.isBlank()
                || subject == null || subject.isBlank()
                || registrationId == null || registrationId.isBlank()) {
            throw new IllegalArgumentException(
                "External identity key is required"
            );
        }
    }
}
```

**Quan trọng:** Record constructor chỉ xác minh tính **không rỗng**, không chứng minh token hay provider đã được xác thực.

Bản ghi chỉ được coi là `Verified` nếu xây dựng từ một trust boundary đã hoàn tất:

- OIDC principal với ID Token đã được Spring Security xác minh theo issuer/client.
- OAuth2User trả về từ trusted provider user endpoint qua flow đã xác thực.
- Registration ID thuộc danh sách đã cấu hình và được phép.
- Subject được lấy từ claim/attribute ổn định được provider cam kết.

### 13.1. Chuyển OidcUser thành identity key

Ví dụ logic thuần trong code sau khi OAuth2 Login hoàn tất:

```java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public VerifiedExternalIdentity fromOidc(
        String registrationId,
        OidcUser user) {

    String issuer = user.getIdToken()
        .getIssuer()
        .toString();

    String subject = user.getSubject();

    String email = user.getEmail();

    return new VerifiedExternalIdentity(
        issuer,
        subject,
        registrationId,
        user.getFullName(),
        email,
        Boolean.TRUE.equals(
            user.getClaimAsBoolean("email_verified")
        )
    );
}
```

Mẫu code trên giả định `OidcUser` được Spring Security tạo ra **sau OIDC token validation**. Không nhận một ID Token raw string từ browser rồi tự parse claims mà bỏ signature/issuer/audience checks.

### 13.2. Provider-specific user attributes

Với một OAuth2 provider không OIDC, cần mapper riêng theo registration:

```text
github:
    namespace = oauth2:github.com
    subject = stable numeric id từ verified OAuth2User

enterprise-gitlab:
    namespace = oauth2:gitlab.enterprise.example
    subject = stable id theo instance
```

Không giả định mọi provider đều có `sub`. `OAuth2User.getName()` phụ thuộc cấu hình `user-name-attribute`, và có provider dùng nickname hoặc handle không ổn định.

---

## 14. Nhiều ClientRegistration trong Spring Boot

Ví dụ `application.yml` trên Spring Boot 3.x:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email

          workforce:
            provider: workforce-oidc
            client-id: ${WORKFORCE_CLIENT_ID}
            client-secret: ${WORKFORCE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

        provider:
          workforce-oidc:
            issuer-uri: https://login.corporate.example
```

Các values là placeholder; không commit secrets vào repository.

`google` có thể dùng provider defaults mà Spring Boot hỗ trợ. Một OIDC provider tự cấu hình dùng `issuer-uri` để discovery và validate expected issuer, tùy provider metadata/phiên bản.

### 14.1. Registration ID không thay identity key

`registrationId="workforce"` là tên do ứng dụng chọn để tìm OAuth2 ClientRegistration. Nó **không phải issuer** và cũng không phải user ID.

Ví dụ:

```text
registrationId = workforce
issuer = https://login.corporate.example
sub = 123
```

Nếu sau này đổi tên registration thành `workforce-v2` nhưng issuer+sub giữ nguyên, không nên tự tạo identity mới cho cùng người dùng chỉ vì key cấu hình thay đổi, trừ khi policy migration quy định khác.

### 14.2. Không cho frontend gửi arbitrary issuer URI

Không nên triển khai dynamic registration:

```text
GET /login?issuer=https://attacker.example
```

rồi tự động tin discovery endpoint mà browser truyền vào. Điều này có thể dẫn tới issuer mix-up, metadata injection, token leakage và SSRF.

Đối với enterprise multi-tenant dynamic IdPs, cần tenant allowlist, provider onboarding và validation nghiêm ngặt.

### 14.3. Provider nào có email_verified?

OIDC có chuẩn claim `email_verified` nếu provider phát claim đó. Với OAuth2 UserInfo không theo OIDC, field tương tự có thể có semantics khác hoặc không tồn tại.

Không mặc định:

```java
user.getAttribute("email_verified")
```

là một boolean đáng tin với mọi OAuth2 provider.

---

## 15. `SecurityFilterChain` và OAuth2 Login

Một cấu hình Servlet tối thiểu:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/assets/**").permitAll()
                .requestMatchers("/api/account/links/**").authenticated()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        // Giữ CSRF protection cho endpoints thay đổi state.
        return http.build();
    }
}
```

Đoạn này bật OAuth2/OIDC Login cho nhiều registrations đã khai báo. **Nó chưa thực hiện account linking**; phải xây mapping, pending intent, success handling và local Authentication theo các phần tiếp.

### 15.1. OAuth2 login thành công không đồng nghĩa được phép link

Spring Security chứng minh callback OAuth2 hợp lệ. Nhưng việc G→U có được tạo không còn phụ thuộc:

- Internal account U của người bắt đầu link.
- Provider được chọn.
- Reauthentication freshness.
- Tenant policy.
- External identity G đã thuộc account khác chưa.
- Linking consent và audit.

Không auto-link trong `Oauth2UserService.loadUser()` chỉ vì có `OAuth2User` với email trùng.

---

## 16. Điểm mở rộng Spring Security cho bước ánh xạ identity

### 16.1. `OAuth2UserService`

Với OAuth2 provider không OIDC:

```java
org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService
```

Nó giúp lấy user attributes từ provider theo access token và UserInfo endpoint phù hợp.

### 16.2. `OidcUserService`

Với OIDC login:

```java
org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService
```

Nó tạo/điền OIDC principal dựa trên ID Token và UserInfo theo protocol/configuration.

### 16.3. Custom user service dùng để làm gì?

Có thể dùng wrapper/delegate để:

1. Lấy `OidcUser`/`OAuth2User` đã xác thực từ framework.
2. Tạo stable external identity key.
3. Tìm internal account đã link.
4. Map domain-specific profile hoặc authorities theo local policy.
5. Trả một principal application-specific có internal account ID.

Ví dụ phác thảo ý tưởng:

```java
OidcUserService delegate = new OidcUserService();

OAuth2UserService<OidcUserRequest, OidcUser> customService =
    userRequest -> {
        OidcUser oidc = delegate.loadUser(userRequest);

        String issuer = oidc.getIdToken()
            .getIssuer()
            .toString();
        String subject = oidc.getSubject();

        // Lookup identity map; account linking cần flow riêng.
        // Trả local principal phù hợp nếu mapping đã tồn tại.
        return oidc;
    };
```

**Đoạn code trên minh họa extension point, chưa phải full account-mapping implementation.** Trong linking flow chưa có external identity map, không được âm thầm gán theo email.

### 16.4. Thành công authentication và thành công linking là hai sự kiện khác nhau

Một OAuth2 login success handler có thể phân nhánh:

```text
if validated pending link intent:
    -> link external identity to pre-existing internal account
    -> preserve/restore intended local principal session
else:
    -> normal external identity login
    -> mapped internal account hoặc onboarding
```

Tuy nhiên, success handler được gọi **sau một số bước security authentication và authorized client persistence**. Cần hiểu thứ tự filter chain của phiên bản đang dùng và tránh vô tình lưu token dưới sai principal hoặc thay session của user.

### 16.5. Không viết code “nửa login, nửa link” trong một controller

Một controller không nên nhận raw `code`/`state` rồi tự gọi Token Endpoint nếu Spring Security đã có OAuth2 Login infrastructure. Điều này dễ bỏ sót PKCE, nonce, redirect URI và state validation.

Ưu tiên sử dụng OAuth2 Login chuẩn và customizations tại những extension points được document, với clear separation giữa authentication và business linking.

---

## 17. Local principal nhất quán sau khi login bằng nhiều IdPs

Mục tiêu:

```text
Google identity G -> internal account U
Corporate identity C -> internal account U

Cả hai lần login:
    Authentication.getName() -> stable internal account key U
```

Nhưng **không nên chỉ override `getName()` rồi coi mọi thứ đã xong**.

### 17.1. Hai lớp identity trong một principal

Một custom principal có thể chứa:

```text
internalUserId = U
externalIdentityKey = (iss, sub)
registrationId = google
displayName = Alice
authorities = được tính từ local policy
```

Dữ liệu external identity phục vụ audit và provider API access; internalUserId phục vụ business authorization.

### 17.2. Quyền ứng dụng không nên chỉ tin provider claims

Ví dụ provider trả:

```text
email = alice@company.example
groups = ["engineering"]
```

Điều đó không tự đồng nghĩa Alice có role `ROLE_ADMIN` trong ứng dụng.

Local authorities có thể đến từ database và policy của tenant, với claims từ IdP được dùng như **tín hiệu đã được trust theo mapping**.

Một provider identity gắn cùng account U không nên mặc nhiên hợp nhất mọi quyền ở các tenants khác nhau.

### 17.3. Local account disabled phải có hiệu lực với mọi linked identities

Nếu `InternalAccount(U).status=DISABLED`, đăng nhập qua Google hoặc Workforce đều phải bị từ chối hoặc bị hạn chế theo policy.

Không chỉ disable username/password login rồi quên OAuth2 login paths.

### 17.4. Session sau linking phải thuộc đúng U

Sau callback identity mới G, không để browser bị chuyển sang user V chỉ vì success handler lấy lại mapping G khác U hoặc auto onboarding. Nếu G đã link với V, **từ chối linking** và giữ session U (hoặc bắt reauthenticate theo policy), không silent switch.

---

## 18. `OAuth2AuthorizedClientService` và giới hạn của khóa mặc định

Spring Security OAuth2 Client thường load authorized client theo:

```java
loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
)
```

Nghĩa là một logical key thường là:

```text
(registrationId, principalName)
```

Với local principal U:

```text
("google", "U") -> Google token cho U
("workforce", "U") -> Workforce token cho U
```

Điều này hợp lý **nếu mỗi registration gắn một external identity duy nhất** cho U.

### 18.1. Nếu một internal account link hai Google identities?

```text
U -> Google G1
U -> Google G2

Cả hai dùng registrationId = google
PrincipalName = U
```

Service mặc định keyed `(google,U)` **không biểu diễn đồng thời hai authorized clients** với cùng key.

Lựa chọn:

1. **Giới hạn một external identity cho mỗi registration/provider** theo business policy.
2. Tách registrations nếu có cấu hình OAuth clients khác nhau và được quản trị.
3. Thiết kế custom authorized client store keyed bằng external identity ID nếu phải có nhiều accounts cùng provider.
4. Làm rõ UI chọn identity nào khi gọi provider API và tránh token overwrite.

Không sử dụng `(registrationId, internalUserId)` một cách vô tư nếu sản phẩm thật sự hỗ trợ nhiều identities cùng provider.

### 18.2. Linking identity khác cấp API access

Liên kết Google để **đăng nhập** có thể chỉ yêu cầu scopes OIDC cơ bản:

```text
openid profile email
```

Nếu sau đó muốn đọc Google Drive API, cần quyền API và consent riêng. Không tự cho rằng identity đã link thì có access token đủ scope để gọi mọi Google services.

### 18.3. Authorized client principal key có thể thay đổi khi custom mapping

Trong default OAuth2 Login, authorized client có thể được lưu theo principal name từ external identity.

Nếu sau đó authentication dùng local account ID, một service lookup theo local ID có thể **không thấy token đã lưu dưới external subject**.

Phải xây quy ước nhất quán giữa:

- OAuth2AuthenticationToken principal.
- User service/success handler.
- OAuth2AuthorizedClientRepository/Service.
- Backend API client và token refresh.
- Session/tenant mapping.

Không sửa bằng cách copy refresh tokens không kiểm soát giữa stores hoặc set một global “current authorized client”.

---

## 19. Login với identity đã liên kết: thuật toán an toàn

Pseudocode:

```text
onOidcLoginSuccess(validatedOidcPrincipal, registrationId):
    key = identityKey(
        iss = validatedOidcPrincipal.idToken.issuer,
        sub = validatedOidcPrincipal.idToken.subject
    )

    identity = identityRepository.findByKey(key)

    if identity == null:
        return beginExplicitOnboardingOrLinkFlow()

    account = accountRepository.findById(identity.accountId)

    if account == null or account.disabled:
        rejectLogin()

    if tenantPolicyRejectsIdentity(account, registrationId, key):
        rejectLogin()

    localAuthorities = authorizationService.loadAuthorities(account)

    authentication = createTrustedLocalAuthentication(
        internalUserId = account.id,
        linkedIdentity = key,
        authorities = localAuthorities
    )

    persistAuthenticationAndAuthorizedClientConsistently()
    issueSession()
```

### 19.1. Không auto-create duplicate accounts mỗi lần login

Nếu provider từng phát `sub=123` cho user U và email đổi, lookup `(iss,sub)` vẫn phải tìm U.

### 19.2. Không auto-merge accounts bằng email

Nếu external identity chưa có mapping:

```text
Email same -> không tự join
```

Có thể hiển thị UX:

> “Bạn đã có tài khoản? Hãy đăng nhập bằng phương thức hiện có rồi chọn Liên kết tài khoản.”

Không tiết lộ công khai chi tiết account khác tồn tại chỉ từ email nếu có nguy cơ user enumeration.

### 19.3. Signup mới cũng cần policy

Nếu cho phép auto-create internal account khi identity chưa link, phải phân biệt:

- Provider issuer được chấp nhận?
- Email domain có phải điều kiện onboarding hay chỉ hiển thị?
- Có yêu cầu invitation/tenant membership?
- Provider account thuộc một organization/enterprise instance đáng tin không?
- Có cần verified email hoặc các claims khác theo business policy?

Ngay cả khi cho signup tự động, **không gán identity vào account U hiện có chỉ do email trùng**.

---

## 20. Liên kết provider khi session có thể bị chiếm đoạt

Một attacker đánh cắp BFF session cookie có thể thử:

```text
Session Alice -> Settings -> Link attacker's OAuth2 identity
```

Nếu không có step-up, attacker có thể tạo một login method bền vững cho Alice. Sau đó ngay cả khi session cũ hết hạn, attacker vẫn login qua identity của mình.

### 20.1. Recent authentication/step-up

Các hành động nhạy cảm nên có policy:

```text
last_strong_auth_at <= N phút
```

hoặc yêu cầu:

- Xác minh password/passkey.
- MFA theo chính sách.
- OIDC reauthentication với `max_age`/`acr`.
- Trusted device/transaction confirmation.
- Approval của administrator trong doanh nghiệp nếu cần.

N không phải một con số phổ quát; chọn theo threat model.

### 20.2. Không coi session age là authentication freshness

Một session vừa được làm mới idle timeout chưa chứng minh user vừa xác thực bằng MFA.

Cần thông tin last authentication hoặc assurance đáng tin. Với OIDC, `auth_time` và `acr`/`amr` có semantics theo issuer và negotiated requirements.

### 20.3. Thông báo sau khi link

Gửi một notification qua kênh account đã đăng ký hoặc audit UI:

```text
Một phương thức đăng nhập mới vừa được liên kết:
Provider: Workforce OIDC
Time: ...
```

Thông báo **không thay thế bước xác minh link**, nhưng giúp phát hiện account compromise.

Tránh gửi raw subject, access token hoặc sensitive provider attributes trong notification.

---

## 21. Unlink: xóa liên kết không được khóa người dùng khỏi tài khoản

Khi user muốn bỏ một provider:

```http
DELETE /api/account/links/{identityId}
Cookie: SESSION=...
X-CSRF-TOKEN: ...
```

Backend cần:

1. Xác minh user đang quản lý đúng account U.
2. Yêu cầu recent authentication/step-up nếu policy.
3. Bảo đảm identityId thực sự thuộc U.
4. Không cho phép vô hiệu hóa **phương thức đăng nhập cuối cùng** nếu không có recovery method hợp lệ.
5. Transactional unlink/mark inactive.
6. Remove/revoke authorized client của identity tương ứng theo chính sách.
7. Invalidate các sessions hoặc yêu cầu reauthentication nếu thay đổi bảo mật đủ lớn.
8. Ghi audit và notification.

### 21.1. Không nên chỉ xóa row rồi thôi

Có thể còn:

- OAuth2AuthorizedClient trong Redis/JDBC.
- Refresh token chưa revoke ở provider.
- Sessions trên các thiết bị khác.
- Background jobs đang gọi provider API.
- Scheduled sync integrations.
- Cached local authorities.
- Recovery methods có liên quan.

Identity unlink và **OAuth2 authorization revocation** là những việc khác nhau nhưng thường cần phối hợp.

### 21.2. Last login method và recovery

Ví dụ U có:

```text
Google identity G
Workforce identity C
Password login disabled
```

Có thể unlink G nếu C vẫn dùng được. Nhưng nếu Workforce access bị thu hồi khi nhân viên nghỉ việc, cần recovery strategy độc lập phù hợp policy.

Không hứa có thể recover chỉ bằng email nếu email identity không phải nguồn chứng cứ ownership đáng tin.

### 21.3. Transfer identity từ account U sang V

Không âm thầm thực hiện:

```sql
UPDATE external_identity
SET account_id = :new_account_id
WHERE namespace = ... AND subject = ...;
```

vì đây là **chuyển quyền đăng nhập**. Nếu business thật sự hỗ trợ transfer/merge, phải có policy proof-of-control cả hai accounts, step-up, audit, rollback/notification và xử lý dữ liệu/tenant boundaries.

---

## 22. Account recovery và account merge không đồng nghĩa account linking

### 22.1. Linking

Một account U đang được xác thực và thêm một external identity G **chưa thuộc account khác**.

### 22.2. Recovery

User không còn truy cập phương thức đăng nhập nào, cần chứng minh quyền sở hữu account U bằng các recovery factors đã đăng ký.

### 22.3. Merge

Hai internal accounts U và V đều có dữ liệu/authorization khác nhau, cần hợp nhất.

**Merge phức tạp hơn linking rất nhiều**:

- Ownership đơn hàng, thanh toán, dữ liệu nhạy cảm.
- Membership và tenant roles.
- Linked identities và active sessions.
- OAuth2 authorized clients và refresh tokens.
- Audit trail, legal obligations.
- Conflicting resource IDs, data retention.
- User consent và khả năng hoàn tác.

Không thực hiện merge tự động vì email trùng.

### 22.4. Nếu identity đã link vào account V

Thông điệp hiển thị cho user U nên tránh lộ thông tin quá cụ thể:

```text
Danh tính này hiện không thể liên kết.
Vui lòng dùng quy trình hỗ trợ/khôi phục tài khoản.
```

Backoffice có thể lưu reason code `IDENTITY_ALREADY_LINKED` và audit, nhưng không tiết lộ email/tên account V cho U khi chưa có quyền.

---

## 23. Đa tenant và đa tổ chức

Trong SaaS, một external identity có thể được dùng để truy cập nhiều organizations. Có ít nhất hai kiến trúc:

**Kiến trúc A: global person account**

```text
External Identity G -> Global Internal User U
U -> Membership tenant-a (role Member)
U -> Membership tenant-b (role Admin)
```

**Kiến trúc B: tenant-scoped account**

```text
External Identity G -> Local User UA in tenant-a
External Identity G -> Local User UB in tenant-b
```

Kiến trúc B có thể cố ý cho một identity liên quan tới nhiều user records **ở các tenants khác nhau**. Khi đó unique key phải phản ánh chính xác policy, ví dụ `(tenant_id, namespace, subject)` thay vì unique toàn cục.

### 23.1. Chọn policy trước khi chọn unique constraint

Nếu global identity chỉ được link một global account, `UNIQUE(namespace,subject)` hợp lý.

Nếu cho phép cùng external identity trong nhiều tenant-local accounts, cần constraint tenant-aware và business logic rõ. Đừng tự bỏ uniqueness làm mọi account dễ bị link trùng không kiểm soát.

### 23.2. Tenant từ URL không tự là trusted tenant

Một request:

```text
POST /tenants/tenant-b/link
```

không chứng minh principal có quyền quản lý account trong tenant B.

Phải xác minh membership, role và identity provider restrictions. `tenant_id` dùng trong pending link intent cần đến từ trusted server-side authorization context.

### 23.3. Enterprise OIDC và home tenant

Một OIDC provider có thể phát tenant-specific issuer hoặc claims như tenant ID. Cần tuân theo issuer/tenant validation contract của provider, không chỉ đọc tên miền email của user.

Nếu tenant policy yêu cầu managed corporate identities, liên kết consumer identity cùng email không tự đáp ứng.

---

## 24. Chống liên kết nhầm qua nhiều tabs và nhiều devices

Một browser có thể có hai tabs:

```text
Tab A: đang link Google
Tab B: đang link Workforce
```

Nếu app lưu một biến session:

```text
pending_registration = google
```

rồi Tab B ghi đè thành workforce, callback Tab A có thể gắn sai business intent.

### 24.1. Key pending record bằng authorization transaction

Nên:

- Có pending link ID ngẫu nhiên.
- Gắn với expected internal account U.
- Gắn với đúng OAuth2 `state`/authorization request.
- Gắn với registration ID và TTL ngắn.
- Single-use/consume atomically.
- Có chính sách khi session đổi, logout hoặc login khác.
- Không để pending record từ tab cũ tự động link identity vào account mới.

### 24.2. Multi-device

Nếu user bắt đầu link trên laptop rồi hoàn tất authentication trên điện thoại khác, thông thường OAuth2 callback quay về browser session của laptop. Nếu sản phẩm có cross-device linking flow, cần chứng cứ giao dịch riêng và chống session swapping.

Không tự coi một OAuth2 `code` được gửi qua chat/QR là đủ để gắn vào account khác.

### 24.3. Provider account chooser

Người dùng có thể đang đăng nhập nhiều tài khoản Google. UX nên giúp họ xác nhận **tài khoản provider nào** sẽ được link, ví dụ hiển thị email/avatar sau khi đã verify identity.

Nhưng quyết định lưu DB vẫn dựa trên **stable subject key**, không dựa trên email được hiển thị ở màn hình xác nhận.

---

## 25. Race giữa unlink và login/link

Một request có thể xóa link G→U trong lúc request OAuth callback của G đang xử lý.

Ví dụ:

```text
Thread A: Login bằng G, đọc G->U
Thread B: User unlink G, xóa mapping
Thread A: Tạo session cho U theo snapshot cũ
```

Nếu policy yêu cầu unlink có hiệu lực tức thì, cần xem cách đồng bộ:

- Version/state của external identity.
- Session revocation hoặc short-lived authentication caches.
- Transaction boundaries.
- Kiểm tra trạng thái link trước khi commit authentication.
- Conditional writes với tombstone nếu có callback đến muộn.
- Audit và eventual consistency guarantees.

Không nên chỉ kiểm tra link một lần rồi giữ trong global cache vô hạn.

### 25.1. Tombstone

Thay vì xóa row ngay, có thể giữ:

```text
identity_state = ACTIVE / UNLINKED
version = 12
```

để một callback cũ không vô tình tạo lại G→U sau khi U vừa unlink. Đây là custom application model, không phải field mặc định của Spring Security.

### 25.2. Re-link cũng phải chứng minh lại external identity

Nếu G đã unlink hôm qua, hôm nay user muốn link lại, không dựa vào snapshot `id` hoặc browser-supplied email. Thực hiện lại flow với provider và pending intent.

---

## 26. SecurityContext và OAuth2 token storage sau linking

Giả sử Alice có:

```text
Local account: U
Google identity: G
Workforce identity: C
```

Sau Google login:

```text
Authentication local principal = U
Authorized client for registration google = Token_G
```

Sau Workforce login:

```text
Authentication local principal = U
Authorized client for registration workforce = Token_C
```

### 26.1. Đừng trả OAuth2AuthorizedClient về frontend

Một object `OAuth2AuthorizedClient` có thể chứa `accessToken` và `refreshToken`. Nó không phải dữ liệu DTO của `/api/account/links`.

Response nên là:

```json
{
  "connections": [
    {
      "id": "opaque-link-id-1",
      "provider": "Google",
      "displayName": "alice@example.com",
      "linkedAt": "2026-10-01T12:00:00Z"
    },
    {
      "id": "opaque-link-id-2",
      "provider": "Workforce",
      "displayName": "Alice (Corporate)",
      "linkedAt": "2026-10-10T07:00:00Z"
    }
  ]
}
```

Không trả raw `iss+sub` nếu không cần, đặc biệt với identifiers có thể dùng để correlation người dùng giữa services.

### 26.2. Login identity không tương đương API access

Một người dùng có thể **liên kết danh tính** Google để đăng nhập nhưng không cấp scope đọc Google Calendar.

Nếu app cần Calendar API, cần một OAuth2 authorization riêng với đúng consent, scopes và token persistence. Không tự mở rộng permissions khi linking.

### 26.3. Token revocation và unlink

Khi user unlink provider:

- Xóa/mất hiệu lực mapping dùng để đăng nhập.
- Nếu không còn cần token API, remove authorized client và gọi revocation endpoint nếu AS hỗ trợ/contract yêu cầu.
- Với nhiều sessions, có thể cần invalidate những sessions được xác thực bằng identity đó.
- Không chắc provider logout sẽ revoke toàn bộ tokens.
- Refresh token rotation và concurrent jobs cần policy nhất quán.

---

## 27. Ranh giới backend–browser trong link flow

Trong mô hình BFF/server-side OAuth2 Login:

```text
Browser:
    Session cookie + OAuth authorization redirect
Backend:
    OAuth2 client credentials, access token, refresh token
```

Link flow không nên đưa raw provider tokens vào:

```text
localStorage
sessionStorage
window.__TOKEN__
HTML inline script
frontend JSON response
URL query hoặc fragment
browser-readable cookie
```

Authorization code xuất hiện trong callback URL theo protocol nhưng backend phải đổi code qua back-channel, không trả token response cho JS.

### 27.1. Session cookies vẫn là credentials

`HttpOnly`, `Secure`, `SameSite` và session fixation protection giúp bảo vệ session. `SameSite` không thay CSRF token. Đăng nhập linking từ cross-site IdP redirect cần cookie policy tương thích callback GET/form POST.

### 27.2. XSS có thể khởi động link flow

Ngay cả nếu session cookie HttpOnly, XSS cùng origin vẫn có thể gửi POST và đọc CSRF token theo policy frontend. Step-up và reauthentication trước khi link giúp giảm tác động của một session hoặc script compromise, nhưng không thay CSP/output encoding.

### 27.3. Không lộ tokens trong logs

Cấm log raw:

```text
Authorization: Bearer ...
access_token
refresh_token
id_token
code_verifier
client_secret
authorization_code
session_cookie
```

Có thể audit:

```text
event=EXTERNAL_IDENTITY_LINKED
internalAccountRef=<pseudonymized>
provider=google
externalIdentityRef=<opaque link ID>
result=success
requestId=...
```

---

## 28. Quy trình đăng nhập sau khi link: không bị lẫn provider

Ví dụ Alice link Google và Workforce rồi login qua Workforce:

```text
Workforce callback:
    iss = https://login.corporate.example
    sub = corporate-991

Identity map:
    (workforce issuer, corporate-991) -> U

Authentication:
    localUserId U
    currentAuthenticationProvider workforce
    businessAuthorities from trusted local policy
```

Một bước mapping nên đảm bảo:

- Account U vẫn active.
- Provider/issuer được cho phép trong tenant.
- Identity link vẫn active.
- Sign-in risk/step-up policy áp dụng.
- Nếu Workforce source bị disable hoặc group membership thay đổi, local policy được reevaluate.
- Không tự nâng quyền chỉ vì identity khác của U có một claim `admin`.

### 28.1. Cùng internal account nhưng sessions có provenance khác

Ứng dụng có thể ghi:

```text
session 1:
    authenticated_via = google
    assurance = low

session 2:
    authenticated_via = workforce
    assurance = high
```

Các hành động nhạy cảm có thể yêu cầu một authentication provider hoặc assurance level nhất định. Linking nhiều identities không có nghĩa **mọi phương thức đăng nhập đều tương đương mức tin cậy**.

### 28.2. Không kết hợp tùy tiện các claims từ các lần login cũ

Ví dụ `employee=true` ở Workforce nhưng Alice hiện login qua một Google account không thuộc doanh nghiệp. Policy có thể yêu cầu recent Workforce authentication trước khi truy cập HR data.

Không giữ claim `employee=true` vô hạn chỉ vì local account U từng link Workforce identity.

---

## 29. Quyền quản trị, deprovision và SCIM/JIT onboarding

Trong enterprise, internal account có thể được tạo bởi:

- JIT provisioning sau login provider đáng tin.
- Invitation flow.
- SCIM provisioning.
- Admin console.
- HR/account directory sync.

Liên kết một external identity mới **không phải** quy trình bypass provisioning.

### 29.1. IdP account bị disable

Nếu corporate identity C bị disable ở IdP:

- Lần login sau bằng C nên thất bại.
- Sessions hiện hữu có thể còn sống tới khi expiration/revocation nếu không có back-channel deprovision integration.
- Internal account U có thể còn Google login; có được dùng Google sau khi nhân viên nghỉ việc không là **business policy**.

Nếu internal account đã bị disabled do deprovision, tất cả identity logins tới U phải bị từ chối.

### 29.2. Khi chuyển tenant

Không tự chuyển external identity C từ tenant A sang tenant B chỉ vì user chọn tenant trong UI. Cần authorization, policy và thường có explicit migration/approval.

### 29.3. Verified domain không tự đủ

Một provider trả email với domain doanh nghiệp không chứng minh người dùng được tổ chức ủy quyền vào tenant cụ thể. Có thể cần kiểm tra organization membership, tenant claims, invitation hoặc managed account policies.

---

## 30. Kiểm thử linking: happy path chưa đủ

### 30.1. Các test mức service

| Test | Kỳ vọng |
|---|---|
| Link G chưa thuộc ai vào U đã xác thực | Tạo G→U |
| Link lại G→U với proof hợp lệ | Idempotent theo policy |
| Link G đã thuộc V vào U | Từ chối, không transfer |
| Hai threads link G vào U/V | Unique constraint chỉ cho một |
| Account U disabled | Không tạo link |
| Tenant policy cấm provider | Không tạo link |
| Thiếu external identity proof | Không tạo link |
| Provider email trùng U nhưng khác subject | Không auto-link |
| Provider email thay đổi, subject giữ nguyên | Vẫn login đúng U |
| OIDC `iss` khác, `sub` trùng | Không coi là cùng identity |
| Không có email claim | Vẫn có thể nhận stable identity theo policy |
| Một identity đã UNLINKED có callback cũ | Không re-activate không có flow mới |
| Unlink phương thức login cuối | Từ chối hoặc kích hoạt recovery flow đúng |
| Logout sau link | Session/token behavior theo policy |

### 30.2. OAuth2/OIDC protocol tests

Cần kiểm thử:

- `state` sai hoặc bị replay.
- Authorization Code đã dùng lại.
- PKCE verifier sai.
- OIDC ID Token issuer/audience/expiry sai.
- `nonce` không khớp khi áp dụng.
- Provider registration khác expected pending link.
- Callback không có pending intent nhưng lại đi theo link branch.
- Pending intent hết hạn hoặc consumed.
- Hai tabs bắt đầu link khác providers cùng lúc.
- Session của U logout hoặc chuyển user giữa lúc redirect.
- IdP mix-up hoặc dynamic issuer không trong allowlist.

**Không bỏ qua Spring Security protocol validations** trong test. Với test mock OAuth2 Login, cần hiểu mock có thể bypass các network/token validation thực tế.

### 30.3. MockMvc và Spring Security Test

Spring Security Test có post-processors:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Ví dụ test khái niệm:

```java
mockMvc.perform(
        post("/api/account/links/start")
            .with(oidcLogin())
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"registrationId\":\"google\"}")
    )
    .andExpect(status().is2xxSuccessful());
```

Đây là snippet JUnit/MockMvc minh họa, cần setup MVC security, account session mapping, mocks và imports đầy đủ.

`oidcLogin()` mô phỏng user đã xác thực; nó **không chứng minh full OIDC redirect/token exchange/nonce verification**. Với vấn đề account linking, cần integration/contract tests cho callback và pending intent.

### 30.4. Test CSRF

Một `POST /api/account/links/start` có session hợp lệ nhưng **không có CSRF token** phải bị từ chối theo Servlet Spring Security CSRF policy.

Không dùng `.with(csrf())` trong mọi test rồi quên frontend thật phải gửi CSRF header/token.

### 30.5. Test uniqueness dưới concurrency

Có thể dùng `CountDownLatch` để hai workers cùng thực hiện link G→U và G→V.

Test cần xác minh:

```text
COUNT(external_identity WHERE namespace=N AND subject=S) = 1
```

và link cuối cùng trỏ đúng **một** account. Không chỉ assert “một Java thread thấy `exists=true`”; DB unique constraint mới là lớp enforce khi race.

### 30.6. Test quyền OAuth2 authorized client

Nếu U có Google và Workforce identity:

- Tokens của Google không được gửi cho Workforce API.
- Tokens của Bob không được U sử dụng.
- Link/unlink không vô tình thay principalName storage key của các authorized clients khác.
- Khi một identity bị unlink, token API access được remove/revoke đúng policy.
- Nếu same registration có nhiều identities, custom store chọn đúng external identity.

---

## 31. Những lỗi triển khai thường gặp

### Lỗi 1 — Dùng email để auto-link

```text
if (externalEmail == internalEmail) {
    link();
}
```

**Hậu quả:** nguy cơ account takeover do email bị thay đổi/tái sử dụng hoặc provider assurance yếu.

**Cách đúng:** explicit linking flow với proof-of-control cả internal account và external identity.

### Lỗi 2 — Chỉ lưu `sub`

Hai issuers có thể cùng `sub`. Dùng `(iss,sub)` sau validation OIDC hoặc provider namespace+stable ID với OAuth2.

### Lỗi 3 — Dùng `registrationId` làm issuer

`registrationId` là config alias của application, không nhất thiết là issuer/trust namespace.

### Lỗi 4 — Dùng email_verified như quyền sở hữu internal account

`email_verified` chỉ là một claim theo semantics của provider. Nó không cấp quyền đổi account mapping.

### Lỗi 5 — Link ngay khi OAuth2 callback thành công

Callback chứng minh external identity, nhưng không chứng minh người đó được phép link vào một internal account cụ thể nếu thiếu server-side pending intent.

### Lỗi 6 — Success handler lấy current Authentication làm account U

Sau callback, current Authentication có thể đã là external user mới. Lấy U từ pending intent được bảo vệ.

### Lỗi 7 — Bỏ CSRF cho link/unlink API

`state` không thay CSRF token của application settings.

### Lỗi 8 — Không có DB unique constraint

Hai concurrent callbacks có thể gắn cùng identity vào hai accounts.

### Lỗi 9 — Tự động chuyển external identity khi conflict

Không làm `UPDATE account_id` theo ý muốn caller. Đây là quyền đăng nhập, cần recovery/transfer workflow riêng.

### Lỗi 10 — Chặn một identity trong DB nhưng không invalidate sessions

User có thể tiếp tục sử dụng session đã tạo trước khi unlink/deprovision. Xác định session revocation policy.

### Lỗi 11 — Coi identity linking là cấp OAuth2 scopes

Linking cho login không có nghĩa provider đã cấp Calendar/Drive/Graph API permissions.

### Lỗi 12 — Giả định authorized client store hỗ trợ nhiều identities cùng registration

Default `(registrationId,principalName)` có giới hạn; cần business rule hoặc custom storage nếu có nhiều identity tokens cùng provider.

### Lỗi 13 — Lưu raw ID Token/refresh token vào bảng identity mapping

Không cần để nhận diện user; làm tăng rủi ro leak, retention và privilege.

### Lỗi 14 — User tự chọn issuer URL bất kỳ

Dynamic provider discovery không được allowlist có thể tạo mix-up/SSRF và token leakage.

### Lỗi 15 — Cache local user theo email vô hạn

Email không phải stable key; đổi email hoặc deprovision có thể làm mapping sai.

### Lỗi 16 — Unlink last login method không có recovery

User có thể vĩnh viễn không vào lại account. Yêu cầu alternative login/recovery method đã được xác minh.

### Lỗi 17 — Kế thừa role mạnh nhất từ mọi linked providers

Liên kết identities không cho phép nâng quyền tùy ý. Roles phải do application/trusted provider policies quyết định với freshness/tenant controls.

### Lỗi 18 — Login qua provider yếu sau đó dùng quyền vốn yêu cầu MFA của provider mạnh

Có thể phải kiểm tra authentication assurance/provenance và step-up theo resource sensitivity.

---

## 32. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách khoanh vùng |
|---|---|---|
| Login Google tạo account mới dù trước đó link | Khóa issuer/sub khác hoặc mapping không lưu | So sánh validated issuer + stable subject, DB transaction |
| Login Workforce vào account khác | Auto-link theo email hoặc registration alias sai | Kiểm tra lookup và account ownership |
| Link callback trả `invalid_state` | Session/pending OAuth2 request mất hoặc callback sai | Kiểm tra state repository, cookie SameSite, multi-tabs |
| Link thành công nhưng browser đổi sang external user | Success handler thay local Authentication | Phân tách login/link và restore local session U |
| Provider email không xuất hiện | Scope/claim policy hoặc provider không trả | Dựa stable subject, không require email nếu policy không bắt buộc |
| User đổi email rồi không login được | Dùng email làm identity key | Sửa mapping sang `(iss,sub)` |
| Va chạm DB unique | Identity đã link hoặc concurrent link | Rollback; map conflict an toàn, không tự reassignment |
| Link không persist sau restart | Chỉ lưu trong session/InMemory map | Dùng persistent identity DB |
| Token API bị mất sau khi custom getName | Authorized client principal key thay đổi | Căn chỉnh user mapping và service keys |
| Cùng một Google registration overwrite token | Hai linked identities trên một key | Chọn one-per-registration policy hoặc custom store |
| Unlink rồi vẫn gọi được API | Refresh token/session còn tồn tại | Remove/revoke token, invalidate sessions theo policy |
| User admin role tồn tại sau deprovision | Cache authorities hoặc policy sai | Revalidate account status/roles/tenant |
| Corporate identity cùng email với personal identity | Hai different providers/trust levels | Không auto merge, dùng explicit link |
| Login callback bị CSRF hoặc mất session | Cookie flags/response mode không phù hợp | Kiểm tra redirect GET/form POST và state repository |
| Lỗi chỉ khi mở hai tabs | Pending link intent bị ghi đè | Bind intent theo OAuth state/transaction |
| Account bị chiếm sau liên kết mới | Không yêu cầu step-up, session bị đánh cắp | Bật step-up/notifications/audit/revocation |
| User không unlink được phương thức cuối | Đúng policy bảo vệ recovery | Cung cấp flow thêm recovery method trước |

### 32.1. Đừng debug bằng cách log ID Token

Có thể log:

```text
registrationId=workforce
issuerNamespace=<approved provider>
identityRef=<opaque ID>
linkIntentId=<opaque short correlation>
result=LINKED|ALREADY_LINKED|DENIED
```

Không log:

```text
id_token
access_token
refresh_token
client_secret
authorization_code
session_cookie
```

Trường `iss` và `sub` có thể là identifiers cá nhân; cần hạn chế logging/raw metrics labels theo chính sách dữ liệu.

---

## 33. Các tình huống thực hành

### Tình huống A — Alice có Google và Workforce cùng email

Hai providers trả `alice@example.com`.

**Cách xử lý:** coi là **hai external identities khác nhau**; Alice phải đăng nhập internal account U rồi explicitly link identity mới. Sau link, cả hai có thể đăng nhập U.

### Tình huống B — Attacker đăng ký email đã bị tái sử dụng

Provider mới cấp email trùng tài khoản cũ.

**Cách xử lý:** không auto-link theo email. Dùng trusted stable identity key và proof-of-control của internal account.

### Tình huống C — Hai issuers phát `sub=123`

**Cách xử lý:** khóa OIDC phải là `(iss,sub)`, không chỉ `sub`.

### Tình huống D — Alice link Google trên tab A, Workforce trên tab B

**Cách xử lý:** pending link transaction được bound theo OAuth2 state và registration; không dùng một session variable cuối cùng ghi đè.

### Tình huống E — Success handler nhận principal Google, không thấy local user U

**Cách xử lý:** lấy U từ pending link intent server-side, không từ current OAuth2AuthenticationToken vừa được xác thực.

### Tình huống F — Google identity đã thuộc account V

**Cách xử lý:** từ chối link vào U, không xóa hay chuyển V. Nếu thực sự cần merge/recovery, dùng workflow riêng.

### Tình huống G — Alice đổi email ở provider

**Cách xử lý:** update display attribute nếu cần, giữ link bằng stable OIDC subject/provider user ID.

### Tình huống H — Alice muốn link hai Google accounts

**Cách xử lý:** xác định one-per-registration policy hoặc thiết kế custom storage key cho hai authorized clients; tránh overwrite token.

### Tình huống I — Corporate IdP thu hồi identity của nhân viên

**Cách xử lý:** lần login qua provider đó phải thất bại; internal account U có được tiếp tục qua Google hay không do business deprovision policy.

### Tình huống J — User đang active nhưng xóa identity cuối cùng

**Cách xử lý:** yêu cầu thêm recovery/login method khác trước khi unlink; không để user tự khóa tài khoản mà không hiểu hậu quả.

### Tình huống K — User chỉ có OIDC Login, không có password

**Cách xử lý:** step-up có thể dùng reauthentication tại trusted IdP/MFA, không bắt user nhập một password ứng dụng không tồn tại.

### Tình huống L — Provider OAuth2 không có `sub`

**Cách xử lý:** dùng stable ID từ trusted provider user endpoint và namespace của đúng provider instance.

### Tình huống M — OAuth2 provider trả `email_verified` không rõ semantics

**Cách xử lý:** không dùng claim như bằng chứng link; xác thực stable provider ID và policy provider cụ thể.

### Tình huống N — Browser giữ access token sau link

**Cách xử lý:** nếu thiết kế là BFF, tokens phải ở backend; không trả OAuth2AuthorizedClient/raw tokens cho JavaScript.

### Tình huống O — Linked identity có quyền admin tại IdP khác

**Cách xử lý:** chỉ áp local business roles được policy/tenant mapping cho phép; link identity không mặc nhiên cấp admin.

### Tình huống P — Hai requests link cùng external identity đồng thời

**Cách xử lý:** DB unique constraint + transaction; một request thắng, request còn lại nhận conflict an toàn.

### Tình huống Q — OAuth2 Login bình thường bị hiểu nhầm là linking

**Cách xử lý:** callback phải có pending link intent hợp lệ, bind với state/session. Nếu không, xử lý normal login/onboarding riêng.

### Tình huống R — User unlink nhưng background sync vẫn có refresh token

**Cách xử lý:** cleanup/revoke authorized client và job access theo policy, phối hợp concurrent refresh.

---

## 34. Câu hỏi tự kiểm tra

**1. Một internal account có thể có nhiều external identities không?**  
Có, theo data model linking. Nhưng các identities phải được xác minh và gắn qua policy rõ ràng.

**2. Với OIDC nên dùng identity key nào?**  
Cặp `(validated iss, validated sub)`.

**3. Hai providers trả cùng `sub` có đồng nghĩa cùng user không?**  
Không. `sub` chỉ có nghĩa trong issuer namespace tương ứng.

**4. Hai providers trả cùng email có nên auto-link không?**  
Không theo mặc định. Email không phải bằng chứng đầy đủ về quyền sở hữu internal account.

**5. Vì sao `email_verified=true` chưa đủ?**  
Nó là claim theo chính sách của provider, không phải authorization để gán một external identity vào account nội bộ hiện có.

**6. OAuth2 Login callback đã thành công có đủ điều kiện link không?**  
Không. Còn cần pending intent, account ownership/step-up, tenant policy và DB uniqueness.

**7. Vì sao success handler không nên lấy account U từ current Authentication?**  
Sau callback, Authentication có thể là external identity vừa đăng nhập, không phải local account gốc của linking flow.

**8. `state`, PKCE và CSRF bảo vệ cùng một việc?**  
Không. Chúng xử lý authorization-response correlation, code binding và state-changing BFF requests tương ứng.

**9. Ràng buộc DB quan trọng nhất cho identity key là gì?**  
Uniqueness trên provider identity key, ví dụ `(namespace,subject)` theo global-account policy.

**10. `existsBy...` rồi `save` có đủ chống race không?**  
Không. Hai transactions có thể cùng thấy chưa tồn tại; DB unique constraint và transaction vẫn cần.

**11. `ClientRegistration.registrationId` có phải OIDC issuer không?**  
Không. Registration ID là local config alias, không phải issuer identity namespace.

**12. Provider OAuth2 không có OIDC ID Token phải làm gì?**  
Lấy stable provider user ID qua trusted OAuth2 user endpoint và namespace rõ ràng.

**13. Linking identity có tự cấp Google Drive scope không?**  
Không. API access cần OAuth2 authorization/consent đúng resource.

**14. `OAuth2AuthorizedClientService` thường keyed theo gì?**  
`(clientRegistrationId,principalName)`.

**15. Điều gì xảy ra nếu một local principal có hai Google identities cùng registration?**  
Default authorized client service có thể chỉ biểu diễn một record theo cùng key; cần business limit hoặc custom storage.

**16. Khi provider identity đã gắn account V, U nên làm gì?**  
Từ chối linking; dùng recovery/merge workflow riêng nếu được phép.

**17. Có nên cho unlink phương thức login cuối không?**  
Thông thường phải chặn hoặc yêu cầu recovery method đã được xác minh trước.

**18. Linking có làm mọi authentication methods có assurance như nhau không?**  
Không. Provider provenance/MFA/auth_time có thể ảnh hưởng quyền thao tác nhạy cảm.

**19. Khi internal account U bị disabled, Google linked identity có login U được không?**  
Không theo policy disable account; mọi external login mappings phải kiểm tra trạng thái U.

**20. Vì sao cần audit link/unlink?**  
Đây là thay đổi login capabilities và có nguy cơ account takeover, cần truy vết và cảnh báo.

---

## 35. Bảng thuật ngữ trọng tâm

| Khái niệm | Ghi nhớ |
|---|---|
| Internal account | Tài khoản nghiệp vụ riêng của ứng dụng, có stable local ID |
| External identity | Danh tính được provider xác thực |
| Identity key OIDC | `(iss,sub)` sau khi ID Token đã validate |
| OAuth2 provider user ID | Stable ID từ trusted user endpoint, namespace theo instance |
| `registrationId` | Alias cấu hình OAuth2 client; không đồng nhất issuer |
| Account linking | Gắn identity đã xác minh vào account nội bộ qua proof-of-control |
| Account login | Lookup identity đã linked để xác định local account |
| Account merge | Gộp hai internal accounts; phức tạp hơn linking |
| Pending link intent | Giao dịch server-side gắn account U, provider, state, TTL |
| OAuth2 `state` | Liên kết authorization request và callback |
| PKCE | Gắn authorization code và verifier |
| OIDC `nonce` | Gắn ID Token và authentication request |
| Step-up | Chứng minh xác thực mới/mạnh hơn trước thay đổi nhạy cảm |
| Unique constraint | Ngăn một identity key bị gắn vào hai accounts ngoài policy |
| Transaction | Ghi linking atomic, rollback khi conflict |
| `OidcUserService` | Tải/xây OIDC principal, có thể custom mapping |
| `DefaultOAuth2UserService` | Xử lý OAuth2 UserInfo cho provider không OIDC |
| `OAuth2AuthenticationToken` | Authentication từ OAuth2/OIDC login |
| Local principal | Principal ứng dụng gắn stable internal user ID |
| `OAuth2AuthorizedClient` | Access/refresh token của registration/principal |
| Identity unlink | Bỏ phương thức đăng nhập; cần xử lý sessions/tokens/recovery |
| Identity provenance | Provider, issuer, authentication assurance của login |
| Tenant isolation | Không link hoặc login chéo security namespace trái phép |
| JIT onboarding | Tạo account khi identity mới được xác thực theo policy |
| Deprovision | Vô hiệu hóa account/permissions theo lifecycle tổ chức |
| Audit | Ghi lại thay đổi link/unlink bằng metadata tối thiểu |

### Kết luận

Trong hệ thống **Spring Security OAuth 2.0/OIDC Client tích hợp nhiều providers**, mục tiêu của account linking là cho phép **nhiều external identities đã được xác thực** cùng dẫn đến **một internal account ổn định**. Điều này giúp người dùng có nhiều phương thức đăng nhập mà vẫn giữ dữ liệu và quyền nghiệp vụ nhất quán.

Tuy nhiên, việc nối hai identities là **thay đổi khả năng truy cập tài khoản**, không phải phép ghép email. Kiến trúc an toàn cần:

1. Dùng **`(iss,sub)`** cho OIDC hoặc provider namespace + stable user ID cho OAuth2 không OIDC.
2. Phân biệt **normal login** với **explicit linking flow**.
3. Chứng minh user kiểm soát account U và external identity G, với `state`, PKCE, nonce, CSRF và step-up phù hợp.
4. Ràng buộc linking transaction với **server-side pending intent** để callback không nhầm account.
5. Dùng unique constraint và transaction để ngăn duplicate/conflicting mappings.
6. Tách identity mapping với OAuth2 token storage, đồng thời đảm bảo consistent principal/registration keys.
7. Xử lý unlink, logout, revocation, account recovery, deprovision và tenant policy đúng lifecycle.
8. Không tự nâng quyền, không auto-merge theo email và không bao giờ expose raw OAuth2 tokens.

**Thiết kế đúng là nhiều phương thức xác thực cùng dẫn đến một account nội bộ, không phải nhiều nguồn claims tùy ý cùng có quyền chiếm account đó.**

## Tài liệu tham khảo

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — issuer, subject, ID Token, nonce, auth_time, pairwise subject.
- [Spring Security — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) — login, authorized principals và customization.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html) — user service, authorization request resolver, success/failure handler.
- [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html) — client registration, authorized clients, managers/repositories.
- [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html) — OIDC principal loading.
- [Spring Security API — DefaultOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultOAuth2UserService.html) — OAuth2 UserInfo support.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — bảo vệ state-changing endpoints.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — session fixation, authentication lifecycle.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749) — OAuth2 authentication/authorization grants.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636) — Authorization Code protection.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700) — OAuth2 security considerations, CSRF, issuer/redirect and token protections.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) — authentication/re-authentication controls.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — session security controls.
