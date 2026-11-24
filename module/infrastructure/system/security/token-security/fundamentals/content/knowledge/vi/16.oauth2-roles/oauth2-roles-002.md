# Client

## Mục tiêu học tập

Trong chương **OAuth2 roles** của học phần bảo mật token, **Client** là ứng dụng yêu cầu quyền truy cập tài nguyên được bảo vệ, thông qua **Authorization Server (AS)** và theo chính sách của hệ thống. Client có thể phục vụ người dùng, hoạt động dưới danh tính của một dịch vụ hoặc đóng cả vai trò Resource Server trong tương tác khác. Hiểu chính xác Client giúp tránh một lỗi thiết kế phổ biến: thấy một ứng dụng có `client_id` hoặc cầm access token rồi mặc nhiên coi nó là **người dùng đã được xác thực** hoặc **bên được phép gọi mọi API**.

Sau bài học, bạn có thể:

1. Định nghĩa vai trò **Client** và phân biệt nó với **Resource Owner**, **Authorization Server** và **Resource Server** trong OAuth 2.0.
2. Giải thích **public client**, **confidential client**, `client_id`, client authentication và vì sao mã JavaScript/mobile không thể giữ client secret như bí mật thật.
3. Theo dõi Client trong luồng **Authorization Code + PKCE** và **Client Credentials**, phân biệt delegated access với application/service access.
4. Hiểu **access token**, **refresh token**, **OIDC ID token** theo đúng nơi nhận và mục đích; phân biệt `client_id`, `sub`, `aud` và `scope`.
5. Thiết kế đăng ký client, redirect URI, phạm vi quyền, lưu trữ token, rotation và bảo vệ token bị đánh cắp/phát lại.
6. Phân tích Client trong ứng dụng **SPA**, **native/mobile**, **web backend/BFF** và **microservices**, cùng các tình huống kiểm thử.

## 1. Client là ai trong OAuth 2.0?

OAuth 2.0 mô tả bốn vai trò chính:

| Vai trò | Trách nhiệm cốt lõi | Ví dụ |
|---|---|---|
| **Resource Owner** | Chủ thể có khả năng cấp quyền truy cập tài nguyên được bảo vệ theo mô hình hệ thống. | Người dùng sở hữu dữ liệu đơn hàng; đôi khi chủ thể khác tùy hệ thống. |
| **Client** | Ứng dụng yêu cầu quyền truy cập tài nguyên, với sự cho phép hoặc ngữ cảnh ủy quyền thích hợp. | Ứng dụng Spend Insights đọc lịch sử đơn của user. |
| **Authorization Server (AS)** | Xác thực/cấp quyền theo luồng phù hợp, xét policy và phát hành access token. | `https://auth.example.test`. |
| **Resource Server (RS)** | Lưu/phục vụ tài nguyên bảo vệ, tiếp nhận và xác minh access token, thực thi quyền. | Orders API ở `https://api.example.test`. |

**Client không đồng nghĩa người dùng.** Một ứng dụng báo cáo có thể gọi Orders API **thay mặt** user đã cho phép; khi đó client là ứng dụng, còn principal/resource owner được phản ánh riêng tùy luồng và profile. Một service chạy theo lịch cũng là Client khi xin token bằng chính danh tính của nó, dù **không có user cuối tương tác**.

### Một bối cảnh cụ thể

~~~text
Người dùng:     user-123
Ứng dụng Client: spend-insights-web
Authorization Server: https://auth.example.test
Resource Server: Orders API, audience orders-api
Mục đích:        Xem những đơn hàng mà user-123 được phép xem
~~~

Trong mô hình này:

- User tương tác với ứng dụng và có thể được AS yêu cầu đăng nhập/chấp thuận.
- Client yêu cầu quyền `orders:read` đối với Orders API.
- AS quyết định có cấp quyền không và phát hành token có audience/scope phù hợp.
- Client trình **access token** cho Orders API.
- Orders API xác minh token rồi kiểm tra quyền của principal trên **từng đơn hàng**.

### Sơ đồ vai trò

~~~mermaid
flowchart LR
    U["Resource Owner (user)"] -->|"Tương tác / đồng ý khi cần"| C["Client: Spend Insights"]
    C -->|"Authorization request / token request"| AS["Authorization Server"]
    AS -->|"Authorization code / access token theo luồng"| C
    C -->|"Access token + API request"| RS["Resource Server: Orders API"]
    RS -->|"Dữ liệu được phép"| C
    AS -.->|"Quy tắc cấp token, khóa xác minh hoặc introspection"| RS
~~~

Đây là sơ đồ **khái niệm**: trong Authorization Code, trình duyệt còn thực hiện redirect giữa Client và AS; không phải mọi mũi tên đều là một HTTP call backend-to-backend.

## 2. Vai trò là quan hệ trong một tương tác, không phải nhãn cố định

Một service có thể đóng vai trò **Resource Server** đối với request phía trước, nhưng trở thành **Client** khi gọi một service khác.

Ví dụ:

~~~text
Shop Frontend (Client A)
    -> Orders API (Resource Server của A)
         -> Billing API (Resource Server của Orders)
~~~

Orders API là RS khi nhận access token từ frontend; đồng thời trở thành Client đối với Billing khi cần gọi Billing API. Việc đổi vai trò **không tự cho phép Orders chuyển tiếp token của frontend sang Billing**.

| Quan hệ | Bên đóng vai Client | Bên đóng vai RS | Token cần thiết |
|---|---|---|---|
| Shop gọi Orders | Shop/BFF | Orders API | Token có audience phù hợp với Orders. |
| Orders gọi Billing | Orders service | Billing API | Token được cấp cho Billing theo grant/policy phù hợp. |
| Billing gọi Audit | Billing service | Audit API | Token dành cho Audit nếu Audit yêu cầu access token. |

AS và RS cũng **có thể cùng được triển khai** trong một hệ thống phần mềm, nhưng hai trách nhiệm phát hành và tiếp nhận vẫn khác nhau. Không coi một dịch vụ được gọi là “nội bộ” là lý do bỏ kiểm tra issuer, audience hoặc quyền.

**Quy tắc:** xác định vai trò theo **từng lời gọi** và **ranh giới tin cậy**. Không dùng cùng một từ “client” để đồng nhất người dùng, trình duyệt, backend, service và ứng dụng đã đăng ký.

## 3. Client được đăng ký với Authorization Server như thế nào?

Trước khi Client dùng các luồng OAuth, AS cần biết **client nào** đang được đăng ký và **được phép** thực hiện những loại yêu cầu nào. Cấu hình được gọi chung là **client registration**.

Ví dụ bản mô tả minh họa:

~~~yaml
# Metadata minh họa, không phải định dạng bắt buộc của một AS cụ thể.
client_id: spend-insights-web
client_type: confidential
allowed_grant_types:
  - authorization_code
redirect_uris:
  - https://app.example.test/login/oauth2/code/spend-insights
allowed_resources:
  - orders-api
allowed_scopes:
  - openid
  - profile
  - orders:read
require_pkce: true
client_authentication_method: private_key_jwt
~~~

Cấu hình như trên thường giúp AS kiểm soát:

1. **`client_id`:** định danh đăng ký của ứng dụng, dùng nhận diện client khi yêu cầu.
2. **Loại client:** `public` hoặc `confidential` tùy khả năng bảo vệ credential trong môi trường triển khai.
3. **Grant types:** client được phép dùng `authorization_code`, `client_credentials` hay loại grant được AS hỗ trợ nào.
4. **Redirect URIs:** đích trả authorization response được đăng ký và kiểm tra theo quy tắc giao thức.
5. **Client authentication:** nếu là confidential client, xác thực client ở token endpoint bằng phương thức được hỗ trợ.
6. **Resource/audience và scope:** API nào client được phép xin token để gọi, quyền tối đa có thể đề nghị.
7. **Chính sách bổ sung:** PKCE, TTL, refresh token, mức bảo đảm, consent/admin approval và yêu cầu bảo vệ sender proof.

**`client_id` không phải bí mật.** Nó được đưa vào request OAuth và thường hiển thị cho browser. Không dùng việc một caller biết `client_id=spend-insights-web` làm bằng chứng rằng request thực sự đến từ code hoặc máy chủ của Spend Insights.

### Redirect URI phải được quản lý nghiêm

AS phải đối chiếu redirect URI với giá trị được đăng ký theo quy tắc của profile tương ứng; không cho caller tùy ý yêu cầu đưa authorization code đến host của attacker. Các trường hợp ngoại lệ được tiêu chuẩn định nghĩa (ví dụ một số luồng native loopback) cũng phải được thực thi đúng, không biến thành wildcard tùy ý.

Ví dụ nguy hiểm:

~~~text
Registered: https://app.example.test/callback
Requested:  https://attacker.example.org/collect
~~~

Nếu AS chấp nhận `redirect_uri` tùy tiện, attacker có thể đánh cắp authorization response. Bản thân Client cũng không nên tạo endpoint redirect dạng open redirect để kẻ khác lợi dụng khi xây URL callback.

## 4. Public client và confidential client

OAuth phân loại client theo **khả năng giữ bí mật thông tin xác thực**, không dựa đơn thuần trên việc ứng dụng là “nội bộ”, “bên thứ ba” hay sử dụng HTTPS.

### Public client

**Public client** không thể giữ credential dài hạn như client secret một cách bảo mật trước người sử dụng môi trường thực thi. Ví dụ:

- **Single-Page Application (SPA)** chạy JavaScript trong browser.
- **Native/mobile app** được cài trên thiết bị của người dùng.
- Ứng dụng desktop hoặc thiết bị có môi trường triển khai không thể bảo vệ secret chung.

Nếu nhúng:

~~~javascript
// KHÔNG có ý nghĩa bảo mật: secret lộ trong mã phân phối cho người dùng.
const clientId = "shop-spa";
const clientSecret = "THIS_IS_NOT_A_SECRET_IN_THE_BROWSER";
~~~

thì bất cứ ai xem bundle hoặc phân tích ứng dụng đều có thể lấy client secret. **Thêm client secret không biến SPA thành confidential client**. Public client cần sử dụng các bảo vệ phù hợp như **Authorization Code + PKCE**, redirect URI được quản lý, state/CSRF defenses và token storage thận trọng.

### Confidential client

**Confidential client** có thể bảo vệ credential trong môi trường do nó kiểm soát, ví dụ:

- Web backend chạy trên hạ tầng máy chủ được quản lý.
- BFF giữ token và thực hiện token exchange phía server.
- Service-to-service daemon với secret, private key hoặc client certificate được bảo vệ đúng.

Client authentication có thể dùng `client_secret_basic`, `private_key_jwt` hoặc mTLS khi AS hỗ trợ và chính sách phù hợp. **Không phải confidential client nào cũng cần dùng cùng một phương thức**.

### Bảng so sánh

| Thuộc tính | Public Client | Confidential Client |
|---|---|---|
| Nơi thực thi thường gặp | Browser, thiết bị người dùng. | Backend/service được kiểm soát. |
| Client secret tĩnh | Không thể giữ như bí mật thực sự. | Có thể bảo vệ nếu quản lý đúng. |
| `client_id` | Công khai. | Cũng là định danh công khai, không phải secret. |
| Client authentication tại token endpoint | Không thể dựa vào shared secret nhúng trong ứng dụng. | Bắt buộc theo phương thức đã đăng ký khi profile/AS yêu cầu. |
| Authorization Code + PKCE | Biện pháp quan trọng khi dùng luồng code. | Cũng nên áp dụng PKCE theo chính sách bảo mật hiện đại. |
| Token storage | Phải xét XSS, thiết bị bị chiếm, lifecycle. | Có thể giữ token/secret ở backend, vẫn phải bảo vệ. |
| Rủi ro chính | Lộ token/code, XSS, deep link/callback hijack. | Lộ secret/khóa, SSRF, logs, quyền hệ thống quá rộng. |

**Lưu ý kiến trúc:** một sản phẩm web có cả JavaScript frontend và BFF backend không nhất thiết được mô tả bằng một client type duy nhất cho mọi thành phần. Nếu chính **BFF** là OAuth Client thực hiện code exchange và giữ credentials, phần OAuth client đó có thể là confidential; JavaScript frontend vẫn là môi trường không đáng tin để cất secret.

## 5. Client trong Authorization Code + PKCE

Đây là luồng phổ biến khi ứng dụng phục vụ người dùng. Client không yêu cầu user nhập mật khẩu vào ứng dụng rồi tự cấp token; nó **chuyển user tới Authorization Server** để hoàn tất xác thực và quyết định ủy quyền.

### Các bước chính

1. Client tạo **`state`** gắn với phiên authorization request và **`code_verifier`** ngẫu nhiên; tính `code_challenge` theo PKCE.
2. Client đưa browser đến authorization endpoint của AS, với `client_id`, `redirect_uri`, `scope`, `state`, PKCE và `resource` nếu AS hỗ trợ.
3. AS xác thực user và xem xét user consent/policy khi cần.
4. AS trả **authorization code** qua redirect URI đã kiểm tra, kèm giá trị giúp Client liên kết response với request.
5. Client kiểm tra `state` và các yêu cầu profile/issuer, rồi đổi code tại token endpoint bằng `code_verifier`; confidential client cũng xác thực client nếu được yêu cầu.
6. AS xác minh code gắn đúng client/redirect/PKCE, grant và policy; phát hành access token và có thể refresh token theo chính sách.
7. Client gọi RS bằng access token đúng audience/scope, RS tiếp tục phân quyền theo dữ liệu.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser
    participant Client as OAuth Client / BFF
    participant AS as Authorization Server
    participant RS as Orders API
    User->>Browser: Chọn Xem đơn hàng
    Browser->>Client: GET /connect
    Client->>Client: Tạo state, code_verifier/code_challenge
    Client-->>Browser: Redirect tới AS authorize
    Browser->>AS: Authorization request có client_id, scope, state, PKCE
    AS->>User: Xác thực / consent nếu cần
    AS-->>Browser: Redirect về registered callback với code + state
    Browser->>Client: GET callback với code + state
    Client->>Client: Kiểm tra state và authorization response
    Client->>AS: POST token với code, verifier + client auth nếu áp dụng
    AS-->>Client: Access token cho Orders API
    Client->>RS: Authorization: Bearer access token
    RS->>RS: Validate issuer, audience, scope và quyền trên order
    RS-->>Client: Dữ liệu được phép
~~~

### Ví dụ authorization request

~~~http
GET /authorize?response_type=code&client_id=spend-insights-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&scope=orders%3Aread&resource=https%3A%2F%2Fapi.example.test%2Forders&state=<STATE_PLACEHOLDER>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Đây là yêu cầu **rút gọn để giảng giải**, không phải request có thể chạy với giá trị placeholder. `resource` là tham số của **RFC 8707** khi AS hỗ trợ, không phải mọi AS đều hỗ trợ mặc định. AS có thể ánh xạ resource URI thành audience `orders-api` theo hợp đồng.

### Phân biệt state, PKCE, consent và client authentication

| Cơ chế | Chức năng chính | Không thay thế |
|---|---|---|
| **`state`** và liên kết phiên | Bảo vệ liên kết authorization response với request, hỗ trợ chống CSRF/login mix-up theo thiết kế. | Không bảo vệ authorization code nếu bị đánh cắp ngoài bối cảnh PKCE. |
| **PKCE** | Gắn authorization code với `code_verifier` mà client tạo và giữ cho giao dịch. | Không phải mật khẩu user và không tự làm client confidential. |
| **User consent** | Chấp thuận cấp quyền cho client khi hệ thống yêu cầu. | Không tự vượt client/tenant policy. |
| **Client authentication** | Chứng minh confidential client tại token endpoint. | Không chứng minh user có quyền trên từng record. |
| **Audience/scope** | Giới hạn token dành cho API nào, thao tác nào. | Không thay authorization object-level tại RS. |

Không dùng `state` rỗng, `code_verifier` cố định cho mọi user hoặc redirect URI tùy ý. Nếu Client hỗ trợ **nhiều Authorization Server**, nó còn phải chống **authorization server mix-up** và kiểm tra issuer của authorization response/token theo profile.

## 6. Client trong Client Credentials grant

Không phải Client nào cũng cần một user đang đăng nhập. Một dịch vụ xử lý hóa đơn theo lịch có thể xin **access token cho chính ứng dụng** bằng grant `client_credentials`.

Ví dụ:

~~~text
Client:        billing-worker
Grant:         client_credentials
Resource:      https://api.example.test/billing
Requested scope: billing:read
Principal:     service/client identity theo hợp đồng AS
Không có:      End-user consent cho từng token request
~~~

~~~mermaid
sequenceDiagram
    participant Worker as Billing Worker (Client)
    participant AS as Authorization Server
    participant API as Billing API
    Worker->>AS: Token request + client authentication + scope/resource
    AS->>AS: Xác minh client, grant, audience/scope policy
    AS-->>Worker: Access token aud=billing-api
    Worker->>API: Authorization: Bearer service access token
    API->>API: Verify issuer, audience, scope và quyền service
    API-->>Worker: Kết quả theo policy
~~~

Một token request minh họa:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Authorization: Basic <ENCODED_CONFIDENTIAL_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=billing%3Aread&resource=https%3A%2F%2Fapi.example.test%2Fbilling
~~~

`Authorization: Basic` chỉ là một **phương thức client authentication** cho confidential client được cấu hình tương ứng; production phải dùng TLS, bảo vệ credential, không log secret và có thể dùng phương thức mạnh hơn như private-key JWT hoặc mTLS. `resource` phụ thuộc hỗ trợ RFC 8707 của AS.

### Những điểm khác biệt quan trọng

- **Không có người dùng cuối** tham gia mỗi yêu cầu cấp token; AS cấp quyền dựa trên chính sách của **client/service**.
- Token không mặc nhiên chứa `sub=user-123` hoặc đại diện cho tài khoản người dùng đã gọi một API phía trước.
- Resource Server phải kiểm tra **service principal** và permission của ứng dụng, không coi `client_id` là user ID.
- RFC 6749 nói refresh token **thường không nên** được cấp trong `client_credentials`; client thường dùng credential của mình xin access token mới khi cần.
- Nếu service cần hành động **thay mặt user**, thiết kế delegation hoặc token exchange theo chính sách thay vì lấy service token quyền rộng để giả lập quyền user.

**Ngộ nhận:** “Client Credentials chỉ là Authorization Code không cần màn hình đăng nhập.” Sai: hai grant có **ngữ cảnh chủ thể và ranh giới ủy quyền khác nhau**.

## 7. Client ID, subject, audience và scope: ai là ai trong token?

Một access token JWT được AS phát hành theo profile hỗ trợ có thể chứa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "client_id": "spend-insights-web",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

**Đây chỉ là payload minh họa**: không phải access token đã ký và không thể dùng để gọi API.

| Claim/thuộc tính | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **`iss`** | Ai phát hành token và phải được RS tin cậy? | `https://auth.example.test`. |
| **`sub`** | Token mô tả chủ thể nào theo profile? | User hoặc service principal được AS xác định. |
| **`client_id`** | OAuth Client nào được AS gắn với việc cấp token? | `spend-insights-web`. |
| **`aud`** | Resource Server/đối tượng nhận nào được phép sử dụng token? | `orders-api`. |
| **`scope`** | Token được cấp những phạm vi truy cập nào? | `orders:read`. |
| **`iat`, `nbf`, `exp`** | Token được phát hành, bắt đầu/hết hiệu lực khi nào? | NumericDate theo giây Unix. |

Điểm mấu chốt:

1. `client_id` **khác `sub`**. Client là ứng dụng; subject là chủ thể token mô tả theo chính sách/grant.
2. `client_id` **khác `aud`**. Client nhận/giữ token nhưng **Resource Server** mới là audience của access token trong tình huống này.
3. `scope` **không phải danh sách mọi quyền hiện tại của user**; nó là phạm vi AS cấp cho client theo grant.
4. `sub` hợp lệ **không chứng minh người đang cầm bearer token chính là user đó**. Token có thể bị sao chép/phát lại.
5. JWT access token không bắt buộc mọi hệ thống tự phát hành cùng cấu trúc; với **opaque access token**, metadata có thể được RS nhận từ introspection đáng tin thay vì payload JWT.

### Ví dụ sai nghiêm trọng

~~~text
if token.client_id == "trusted-web":
    allow any admin operation
~~~

`client_id` có thể hữu ích để kiểm tra client được phép dùng API, nhưng **không thể thay thế scope, principal, audience, quyền của user/service và quyền trên từng tài nguyên**. Ngay cả bearer token do AS cấp cho client hợp lệ cũng có thể bị đánh cắp.

## 8. OAuth Client và OpenID Connect Relying Party

**OAuth 2.0** tập trung vào **ủy quyền truy cập tài nguyên**. **OpenID Connect (OIDC)** bổ sung lớp xác thực danh tính người dùng. Trong OIDC, Client thường còn được gọi là **Relying Party (RP)**.

Khi Client yêu cầu scope `openid` theo OIDC, AS đóng vai trò **OpenID Provider (OP)** và có thể phát **ID token** để RP kiểm tra kết quả xác thực.

| Token | Nơi dùng | Nội dung/ý nghĩa thường gặp |
|---|---|---|
| **Access token** | Client trình cho **Resource Server** theo audience và scope đã cấp. | Quyền yêu cầu API, có thể JWT hoặc opaque. |
| **ID token** | **OIDC Client/RP** xử lý để xác định kết quả xác thực user theo profile. | Claims như `iss`, `sub`, `aud=client_id`, `exp`; có thể có `nonce`, `auth_time`. |
| **Refresh token** | Client trình tại **token endpoint của AS** để xin token mới khi được phép. | Credential nhạy cảm duy trì grant, không phải token để gọi RS. |

Một payload ID token minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "spend-insights-web",
  "iat": 1893456000,
  "exp": 1893456900,
  "nonce": "<CLIENT_REQUEST_NONCE>"
}
~~~

Client/RP cần xác minh ID token theo đúng OIDC profile: issuer, audience, chữ ký, thời hạn, nonce nếu được yêu cầu/áp dụng, và các kiểm tra luồng liên quan. **Không gửi ID token đến Orders API thay access token** chỉ vì hai token được ký bởi cùng một OP. Orders API không phải audience của ID token này.

Trong một OIDC app, Client có thể dùng `(iss, sub)` đã xác minh để liên kết tài khoản nội bộ. Không lấy `email` làm khóa principal bất biến hoặc cấp quyền chỉ vì email có domain trông có vẻ thuộc doanh nghiệp.

## 9. Client có quyền đề nghị, không có quyền tự cấp scope

Client có thể đề nghị:

~~~text
requested = {orders:read, orders:write, payments:refund}
~~~

AS phải xét **client registration, resource, tenant, người dùng, consent, grant và policy**. Ví dụ:

~~~text
client_allowed = {orders:read, orders:write}
user_entitled  = {orders:read, orders:write}
tenant_policy  = {orders:read}
user_consented = {orders:read}

result: chỉ orders:read có thể được cấp trong chính sách minh họa
~~~

AS có thể cấp tập quyền hẹp hơn hoặc từ chối toàn bộ yêu cầu; **Client không được tự nâng scope** bằng cách đổi tham số request hay sửa JWT payload.

### Resource/audience do AS kiểm soát

Với RFC 8707, Client có thể gửi `resource` để chỉ rõ đích mong muốn:

~~~text
resource=https://api.example.test/orders
scope=orders:read
~~~

AS kiểm tra đích đó có nằm trong policy không và phát access token có audience phù hợp, ví dụ `aud=orders-api`. **`resource` và `aud` không bắt buộc giống hệt chuỗi nhau**; cách ánh xạ do AS/profile quyết định.

Một Client không được tự khai `aud=billing-api` rồi coi token được AS cấp cho Orders trở thành token của Billing. Ngược lại, Billing API không được chấp nhận token chỉ vì cùng issuer hoặc vì có tên scope gần giống.

### Consent là một điều kiện, không phải quyền vô hạn

User có thể đồng ý cho Client xem đơn hàng, nhưng **không thể cấp vượt** entitlement của mình hoặc vượt policy tenant. Một app được user đồng ý `orders:read` không mặc nhiên có `orders:write`. Một app first-party hoặc đã có admin consent có thể không cần màn hình hỏi mỗi lần, nhưng vẫn phải bị AS/RS giới hạn quyền.

## 10. Client nhận, giữ và dùng token thế nào?

### Access token phải đến đúng Resource Server

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS>
~~~

RS kiểm tra:

- Token đến từ **issuer tin cậy**, chữ ký JWT/khóa được cấu hình đúng hoặc introspection opaque token đáng tin.
- **Audience** dành cho Orders API, không phải Billing hoặc client OIDC.
- `exp`, `nbf`, loại token, trạng thái thu hồi và sender proof nếu cần.
- Scope `orders:read` thực sự được cấp; quyền owner/tenant trên order 42.

### Refresh token không phải access token

Client có thể nhận refresh token tùy AS/policy. Đó là credential dùng tại **token endpoint**, không gửi kèm `Authorization: Bearer` tới API nghiệp vụ:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN_PLACEHOLDER>&client_id=<PUBLIC_CLIENT_ID>
~~~

Request trên minh họa **public client** và được đơn giản hóa; nếu refresh token bị ràng buộc với sender proof hoặc AS đòi kiểm tra bổ sung thì phải thực hiện đầy đủ. Với confidential client, AS còn yêu cầu client authentication theo cách đã đăng ký; không mặc định chỉ truyền `client_id` là đủ.

Một refresh token chỉ được dùng xin scope trong phạm vi được ủy quyền theo chính sách; **không tự mở rộng quyền**. Cần bảo vệ refresh token mạnh hơn về vòng đời, rotation/reuse detection, lưu trữ và thu hồi.

### Bảng trách nhiệm lưu trữ theo môi trường

| Loại Client/mô hình | Cách lưu trữ đáng cân nhắc | Rủi ro cần xử lý |
|---|---|---|
| **Web BFF/confidential** | Giữ access/refresh token trong backend; browser chỉ có session ID opaque qua cookie `HttpOnly; Secure`. | CSRF, XSS thao tác qua phiên, session fixation, rò rỉ backend secrets. |
| **SPA/public** | Giảm token tồn tại trong JavaScript; cân nhắc BFF hoặc cơ chế token in-memory khi kiến trúc bắt buộc. | XSS đọc/dùng token, refresh policy, cross-origin, CSRF nếu dùng cookie. |
| **Native/mobile/public** | OS secure storage/keystore, browser ngoài ứng dụng cho authorization theo best practice. | Backup, deep-link interception, malware, thiết bị bị chiếm, rotation. |
| **Backend service/confidential** | Secret manager/keystore, giới hạn người có quyền truy cập, không lưu token trong log. | Lộ client credentials, token dài hạn, quyền service quá rộng. |

**`HttpOnly`** giúp chặn JavaScript đọc cookie qua API thông thường nhưng **không ngăn XSS gửi request** khi browser tự đính cookie. **`Secure`** giới hạn browser gửi cookie qua HTTPS, không mã hóa cookie khi nằm trên ổ đĩa. Nếu dùng cookie làm credential, **CSRF protection** vẫn quan trọng.

### Không đưa token vào URL

Bearer token trong URL query có thể đi vào browser history, log, proxy, analytics và Referer. Ưu tiên `Authorization` header hoặc một cơ chế session cookie được thiết kế có chủ đích; không gửi access/refresh token qua query URL. Mã authorization code cũng phải được đổi sớm, kiểm tra PKCE và không bị ghi log/tái sử dụng.

## 11. Client trong SPA, native, BFF và microservices

### 11.1. SPA chạy trong browser

SPA là **public client** khi chính JavaScript/browser trực tiếp thực hiện vai trò OAuth Client. Nếu phải trực tiếp xin token, dùng luồng Authorization Code + PKCE được AS hỗ trợ và bảo vệ callback, state, token storage. **Không nhúng secret** vào bundle JavaScript.

Vì XSS có thể đánh cắp hoặc sử dụng access token hiện có, nên cân nhắc **BFF** khi ứng dụng có backend tin cậy và cần duy trì phiên an toàn hơn. DPoP có thể giảm tác động khi token đơn lẻ bị sao chép, nhưng XSS cùng origin vẫn có thể yêu cầu môi trường client dùng khóa.

### 11.2. Native/mobile app

Native app là public client trong đa số thiết kế vì người dùng kiểm soát thiết bị cài ứng dụng. Theo best practice, dùng **external user-agent/system browser** cho authorization thay vì thu mật khẩu trong webview không phù hợp; dùng Authorization Code + PKCE. Redirect qua app link/universal link hoặc loopback phải được xác minh theo platform/profile để giảm nguy cơ ứng dụng khác chiếm authorization response.

Không coi một client secret chung đóng gói trong APK/IPA là bí mật. Lưu credential bằng OS secure storage/keystore phù hợp, bảo vệ refresh token và hỗ trợ logout/rotation.

### 11.3. Web Backend for Frontend (BFF)

BFF có thể là **confidential OAuth Client**: nó giữ client credential và access/refresh token trong backend, dùng một session cookie host-only với `HttpOnly; Secure; SameSite` cho browser.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant Browser
    participant BFF as Web BFF (OAuth Client)
    participant AS as Authorization Server
    participant RS as Orders API
    U->>Browser: Mở app và đăng nhập
    Browser->>BFF: Start login
    BFF->>AS: Luồng Authorization Code + PKCE qua browser
    AS-->>BFF: Code và token response theo các bước redirect/token
    BFF->>BFF: Lưu token phía server, tạo session
    BFF-->>Browser: Set-Cookie session HttpOnly + Secure
    Browser->>BFF: GET /orders + session cookie
    BFF->>BFF: Session/CSRF/authorization checks
    BFF->>RS: Gửi access token đúng audience
    RS-->>BFF: Dữ liệu đúng quyền
    BFF-->>Browser: Response đã lọc phù hợp
~~~

Sơ đồ đã giản lược các lần redirect; BFF không được bỏ `state`, PKCE, kiểm tra issuer/authorization response, client auth (nếu áp dụng) hoặc consent/policy. **BFF không xóa rủi ro CSRF/XSS thao tác**, chỉ giúp giảm việc OAuth token trực tiếp xuất hiện trong JavaScript.

### 11.4. Microservices gọi nhau

Một Orders service có thể vừa là RS đối với browser, vừa là Client khi gọi Billing:

~~~text
Browser -> Orders:
  token audience = orders-api

Orders -> Billing:
  cần token audience = billing-api
  và scope phù hợp với Billing
~~~

Các lựa chọn khi Orders gọi Billing:

| Mô hình | Cách dùng | Giới hạn quan trọng |
|---|---|---|
| **Client Credentials** | Orders gọi Billing với danh tính/quyền của service Orders. | Không tự mang quyền user đã gọi Orders. |
| **Token Exchange (RFC 8693)** | AS xem xét trao đổi token để cấp token đúng audience/scope downstream. | Không phải tự sửa payload JWT; AS phải hỗ trợ và chặn nâng quyền. |
| **Delegated/on-behalf-of theo hệ thống** | Giữ ngữ cảnh user khi service gọi tiếp nếu AS/profile hỗ trợ. | Kiểm tra subject, actor/client, audience/scope và owner/tenant. |
| **Token nhiều audience có chủ đích** | Các RS chấp nhận nếu AS và policy cấp rõ ràng. | Mở rộng phạm vi ảnh hưởng khi token bị lộ; mỗi RS vẫn xác minh. |

**Không tắt audience validation** của Billing chỉ để chuyển tiếp token có `aud=orders-api`. Một service được phép gọi API không có nghĩa nó có quyền tự tạo principal user hoặc xin mọi scope.

## 12. Client authentication không phải user authentication

Khi một confidential Client xác thực với AS ở token endpoint, AS biết một bên có thể chứng minh thông tin xác thực của client đó. Điều này **khác** việc xác thực user và **khác** việc client có quyền trên dữ liệu.

~~~text
client authentication:
  "Đây là service spend-insights-backend đã đăng ký."

user authentication:
  "End-user user-123 đã được OP/AS xác thực theo cơ chế yêu cầu."

authorization:
  "Client này được cấp orders:read cho principal/context này,
   và user-123 có được đọc order-42 không?"
~~~

### Phương thức xác thực client và các lưu ý

| Phương thức | Ý tưởng | Cần bảo vệ |
|---|---|---|
| **Client secret** | Client biết secret và trình theo phương thức đã đăng ký, thường qua token endpoint TLS. | Không hardcode/log; rotation; chỉ dùng với môi trường giữ bí mật được. |
| **Private Key JWT** | Client ký assertion bằng private key đã đăng ký. | Key lifecycle, audience assertion, thời hạn/jti và chính sách AS. |
| **mTLS client authentication** | Client chứng minh dùng khóa của TLS client certificate khi kết nối AS. | Certificate trust, TLS termination, rotation, ánh xạ danh tính. |

**Client authentication không tự ngăn access token bị đánh cắp/phát lại ở RS.** Với bearer access token, attacker có bản sao token còn hạn vẫn có thể dùng trong phạm vi quyền, không cần biết client secret dùng lúc xin token. Nếu threat model yêu cầu hạn chế sử dụng token bị sao chép, AS/RS có thể triển khai **DPoP (RFC 9449)** hoặc **mTLS certificate-bound access token (RFC 8705)**; RS phải kiểm tra proof/certificate tương ứng.

## 13. Resource Server nên tin điều gì về Client?

Một token có thể đã được AS ký hợp lệ, nhưng RS vẫn phải tự xác minh **nơi phát hành, nơi nhận, thời hạn và quyền**. Với access token dạng JWT:

~~~mermaid
flowchart TD
    A["Client trình access token tới API"] --> B{"Có token đúng loại và dạng?"}
    B -- Không --> R1["401 / Từ chối"]
    B -- Có --> C{"Issuer, chữ ký/key/algorithm đáng tin?"}
    C -- Không --> R1
    C -- Có --> D{"audience đúng API, exp/nbf/trạng thái phù hợp?"}
    D -- Không --> R1
    D -- Có --> E{"Client được phép gọi API theo policy, nếu cần?"}
    E -- Không --> R2["403 / Từ chối"]
    E -- Có --> F{"Scope cho action được cấp?"}
    F -- Không --> R2
    F -- Có --> G{"Principal có quyền trên object/tenant?"}
    G -- Không --> R2
    G -- Có --> OK["Cho phép trong phạm vi chính sách"]
~~~

Với opaque token, phần xác minh có thể dùng **token introspection (RFC 7662)** từ AS tin cậy, kiểm tra `active`, audience, scope, subject và trạng thái theo hợp đồng. Không dựa vào chiều dài token hoặc chuỗi `client_id` từ request do caller tự gửi.

### Pseudocode cho Orders API

~~~text
handle(GET /orders/{id}, request):
    rawToken = parseExpectedAccessToken(request)
    if missing or malformed:
        return 401

    token = verifyWithTrustedIssuerOrIntrospection(rawToken)
    if token invalid or not token.active:
        return 401
    if not token.audienceContainsExactly("orders-api"):
        return 401

    if policy.restrictsClients and not policy.clientAllowed(token.clientId):
        return 403
    if "orders:read" not in token.grantedScopes:
        return 403

    order = loadOrderFromDatabase(id)
    if order absent:
        return 404
    if not canRead(token.principal, order, currentTenantPolicy):
        return 403

    return 200 with authorized order fields
~~~

Nếu API yêu cầu proof DPoP/mTLS, phải xác minh thêm sender binding trong quá trình chấp nhận token, **không** chuyển sang bearer khi proof thiếu hoặc sai. Mã giả trên không bao gồm các bước mật mã chi tiết; hãy dùng middleware/ thư viện được kiểm chứng.

### Ví dụ Java: `client_id` không thay quyền người dùng

~~~java
import java.util.Objects;
import java.util.Set;

record VerifiedAccessToken(
    String subject,
    String clientId,
    Set<String> audiences,
    Set<String> scopes,
    String tenantId,
    boolean active
) {}

record Order(String id, String ownerId, String tenantId) {}

final class OrderAccessPolicy {
    static boolean canRead(VerifiedAccessToken token, Order order) {
        if (token == null || order == null || !token.active()) {
            return false;
        }
        if (token.audiences() == null
                || !token.audiences().contains("orders-api")
                || token.scopes() == null
                || !token.scopes().contains("orders:read")) {
            return false;
        }
        if (token.clientId() == null
                || !Set.of("shop-web", "spend-insights-web")
                    .contains(token.clientId())) {
            return false;
        }
        return token.subject() != null
                && token.tenantId() != null
                && Objects.equals(token.subject(), order.ownerId())
                && Objects.equals(token.tenantId(), order.tenantId());
    }
}
~~~

`VerifiedAccessToken` **chỉ được tạo bởi lớp đã xác minh** access token, issuer, audience, thời hạn, loại token và các ràng buộc nếu cần. Đây là ví dụ đọc đơn **thay mặt user**, không phù hợp mặc định với client-credentials service principal; service flow cần policy riêng. `Order` phải được tải từ nguồn dữ liệu đáng tin, không lấy ownership do client khai trong request body.

Một caller không được tự đặt header `X-Client-Id: shop-web` hoặc `X-User-Id: user-123` để cấp quyền. Những trường đó chỉ đáng tin nếu đến từ **trusted gateway/security context** theo cơ chế được kiểm soát, không phải metadata Internet tự khai.

## 14. Client phải bảo vệ token, secret và phiên của mình thế nào?

| Rủi ro | Sai lầm thường gặp | Biện pháp trọng tâm |
|---|---|---|
| **Lộ client secret** | Hardcode secret trong SPA, APK, repository hoặc log. | Public client không dùng shared secret giả; confidential client dùng vault/keystore, rotation. |
| **Authorization code interception** | Không dùng PKCE, callback dễ bị chiếm, code rơi vào log. | Authorization Code + PKCE, redirect URI chính xác, state và response validation. |
| **Access token theft** | Lưu token tùy ý, ghi vào URL/log, TTL dài/scope rộng. | Hạn chế nơi lưu, redaction, TTL/scope/audience hẹp, dùng BFF khi phù hợp. |
| **Refresh token theft** | Refresh token nằm ở frontend lâu dài, không rotation/thu hồi. | Bảo vệ refresh token theo loại client, rotation/reuse detection hoặc sender binding theo policy. |
| **Bearer replay** | Tưởng chữ ký JWT ngăn sao chép token. | TLS, sender-constrained token khi cần, thu hồi/phát hiện bất thường. |
| **Token substitution** | Gửi ID token hoặc access token của API khác tới Orders. | Phân biệt token type, issuer, audience và scope. |
| **Confused deputy** | Service tin caller có `client_id` hợp lệ là có mọi quyền. | Kiểm tra delegation, principal, quyền service và object/tenant. |
| **Consent phishing** | User chấp thuận app giả mạo scope nhạy cảm. | Xác minh client, màn hình consent rõ ràng, policy/admin approval. |
| **CSRF/session hijacking** | Cookie auth không SameSite/CSRF; không invalidate session. | HttpOnly/Secure/SameSite, CSRF token/Origin, session rotation/logout server-side. |

### Scope và audience hẹp giúp gì?

Nếu token dành cho `orders-api` chỉ có `orders:read` bị lộ, Billing API phải từ chối vì sai audience, và Orders phải từ chối thao tác ghi không được cấp. **Điều này chỉ giảm phạm vi thiệt hại**, không chứng minh ai đang trình token là Client gốc khi token còn là bearer token.

### Revocation và quyền thay đổi

Client không nên giả định `exp` còn trong tương lai nghĩa là user chưa bị khóa, consent chưa bị rút hoặc role chưa thay đổi. AS/RS có thể sử dụng TTL phù hợp, refresh grant revocation, token introspection/denylist, session version hoặc kiểm tra quyền hiện hành đối với hành động nhạy cảm. Với JWT tự xác minh cục bộ, thu hồi quyền **không tự tức thời** nếu RS không kiểm tra trạng thái.

### Logging/audit

Ghi dấu vết an toàn như `client_id` đã xác minh, issuer, audience, action, kết quả và reason code theo chính sách; **không ghi nguyên access token, refresh token, client secret, authorization code hoặc cookie phiên**. Client ID thường không phải secret, nhưng vẫn nên tránh phơi thông tin nhạy cảm khác qua log.

## 15. Các ngộ nhận về OAuth Client

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “Client là user đang đăng nhập.” | Client là ứng dụng, user là một chủ thể khác. | Phân biệt `client_id` và `sub`/principal. |
| “Biết `client_id` là đã xác thực Client.” | `client_id` là định danh công khai. | Confidential client cần client authentication phù hợp; public client dùng biện pháp khác như PKCE. |
| “SPA có client secret nên trở thành confidential.” | Secret nằm trong mã browser có thể bị trích xuất. | SPA trực tiếp làm OAuth Client là public client. |
| “PKCE là cơ chế user login.” | PKCE gắn code exchange với verifier. | AS vẫn phải xác thực user/policy khi cần. |
| “Client Credentials đại diện cho user cuối.” | Grant có thể chỉ dựa trên danh tính/quyền của service. | Không tự gán user ID cho service token. |
| “Đã consent thì Client có mọi quyền của user.” | Consent và scope bị giới hạn bởi policy/grant/resource. | AS chỉ cấp phạm vi thực tế được cho phép. |
| “ID token có chữ ký của AS thì dùng làm access token.” | ID token dành cho OIDC RP, audience thường là client ID. | RS yêu cầu access token đúng audience. |
| “Client được cấp Orders token thì forward sang Billing.” | Billing có thể không thuộc audience. | Xin token cho Billing theo luồng được AS hỗ trợ. |
| “Một Client vừa là RS là mâu thuẫn.” | Vai trò phụ thuộc từng tương tác. | Orders có thể là RS đối với frontend và Client đối với Billing. |
| “Client auth chứng minh bearer token không bị trộm.” | Attacker có thể dùng lại access token đã lộ mà không có client secret. | Sender proof khi cần, bảo vệ vòng đời token. |
| “Token `scope=orders:read` cho đọc mọi đơn.” | Scope không thay kiểm tra ownership/tenant. | RS kiểm tra object-level authorization. |
| “Không cấp refresh token tức Client không bao giờ xin token mới.” | Client có thể chạy lại grant/luồng phù hợp. | Phân biệt grant gốc, refresh và policy. |

## 16. Ma trận kiểm thử Client và token

Giả sử AS tin cậy có hai client: `spend-insights-web` (được cấp `orders:read` theo user) và `billing-worker` (được cấp `billing:read` theo service). Orders API kiểm tra `aud=orders-api` và owner/tenant.

| Tình huống | Kỳ vọng | Lý do |
|---|---|---|
| Spend Insights thực hiện Code + PKCE, user đồng ý, AS cấp `orders:read` | **Có thể cấp access token** nếu policy đạt. | Client, grant, user, audience, consent phù hợp. |
| Spend Insights xin `payments:refund` ngoài registration | **Không tự cấp scope**. | Request không vượt client/tenant policy. |
| Public SPA gửi secret nhúng trong mã và đòi được coi confidential | **Không chấp nhận suy luận đó**. | Secret phân phối công khai không chứng minh client. |
| Authorization response trả về redirect URI khác đăng ký | **Từ chối theo giao thức**. | Chặn chuyển code sai đích. |
| Client đổi code nhưng `code_verifier` sai | **Từ chối token request**. | PKCE không đạt. |
| Client đã đăng nhập user nhưng không có consent bắt buộc | **Chưa cấp quyền** cho scope cần consent. | Login không thay consent. |
| Billing Worker dùng Client Credentials đúng cấu hình | **Có thể cấp service token** cho Billing. | Grant app-only theo policy. |
| Billing Worker tự thêm `sub=user-123` vào payload muốn phát | **Không được tin**. | Client không có quyền tự quyết định subject của token AS. |
| Token có `client_id=spend-insights-web` nhưng `aud=billing-api` gửi Orders | **Từ chối**. | Audience không khớp. |
| OIDC ID token `aud=spend-insights-web` dùng gọi Orders | **Từ chối**. | Sai mục đích/đối tượng nhận. |
| Token Orders đúng issuer/audience/scope nhưng owner khác | **Từ chối**. | Không có object-level authorization. |
| Orders forward token `aud=orders-api` sang Billing | **Billing từ chối**. | Token sai đích; cần token mới phù hợp. |
| `client_id` hợp lệ nhưng access token hết hạn | **Từ chối**. | Identity của Client không thay `exp`. |
| Token còn hạn nhưng refresh grant bị thu hồi | **Không cấp token mới** theo revoked grant; xử lý token cũ theo RS policy. | Refresh grant và access token đã cấp có vòng đời khác nhau. |
| Bearer access token bị sao chép, chưa hết hạn | **Có nguy cơ bị sử dụng lại**. | Client authentication không tự ràng buộc holder tại RS. |

Kiểm thử cần bao gồm **đúng và sai client type**, sai redirect, sai issuer, state/PKCE không khớp, grant không được phép, sai audience, thiếu scope, sai tenant, session logout, secret bị rotation và token bị đánh cắp. Khi chạy integration test, kiểm tra cả client/AS lẫn Resource Server — chỉ test một bên không chứng minh toàn bộ luồng an toàn.

## 17. Tình huống tự luyện

**Tình huống A — SPA có secret.** Một nhóm đặt `client_secret` vào biến JavaScript đã minify rồi khai báo SPA là confidential client. Có an toàn không?

**Giải thích:** Không. Người dùng có thể đọc bundle hoặc quan sát chương trình. Client không thể chứng minh secret còn bí mật. Dùng cấu hình public client với Authorization Code + PKCE; hoặc để BFF backend giữ credential.

**Tình huống B — Nhầm Client với subject.** Resource Server thấy `client_id=shop-web` và `sub=user-123` trong token. Nên dùng trường nào để tra ownership đơn hàng?

**Giải thích:** Theo hợp đồng delegated token, `sub` đã xác minh mô tả principal/user; `client_id` nhận diện ứng dụng được cấp token. Không dùng client ID để kết luận user là chủ đơn, và vẫn cần đối chiếu tenant/quyền thật.

**Tình huống C — Client Credentials dùng cho user.** Orders service có service token với quyền đọc Billing. Một user không được đọc hóa đơn yêu cầu Orders trả hóa đơn của người khác. Orders có thể dùng quyền service để trả không?

**Giải thích:** Không. Service token cho phép Orders gọi Billing theo phạm vi service nhưng không tự ủy quyền tiết lộ dữ liệu đó cho user. Cần policy tại Orders/Billing về actor, user và đối tượng dữ liệu; tránh confused deputy.

**Tình huống D — ID token đi lạc.** Client OIDC có ID token `aud=shop-web` và access token `aud=orders-api`. Nó gửi ID token tới Orders API do ID token có `sub`. Kết quả?

**Giải thích:** Orders phải từ chối. ID token là bằng chứng xác thực cho OIDC Client/RP, không phải quyền truy cập Orders API.

**Tình huống E — Cùng AS, khác API.** Orders và Billing tin cùng Authorization Server. Client có token `aud=orders-api`, `scope=orders:read`. Có thể dùng ở Billing không?

**Giải thích:** Không. Cần token dành cho Billing với scope phù hợp; nếu gọi downstream có thể dùng client credentials, token exchange hoặc cơ chế delegation được AS cho phép.

**Tình huống F — User rút consent.** User ngắt kết nối client, nhưng một access token JWT đã phát hành vẫn còn `exp` 10 phút ở tương lai. RS chỉ kiểm tra chữ ký và thời gian. Token có thể tiếp tục dùng không?

**Giải thích:** Có thể. AS phải chặn grant/refresh mới; nếu muốn token cũ hết hiệu lực nhanh, RS cần cơ chế thu hồi/trạng thái phù hợp. Client và user phải hiểu tác động của disconnect/logout.

**Tình huống G — DPoP và XSS.** SPA dùng DPoP-bound access token. Attacker có thể chạy JavaScript trong origin đang đăng nhập và yêu cầu client tạo proof. DPoP có ngăn mọi hành động trái phép không?

**Giải thích:** Không. DPoP giúp khi attacker **chỉ có bản sao token mà không dùng được private key**. XSS cùng origin có thể khiến client sử dụng khóa trong ngữ cảnh bị chiếm; vẫn cần chống XSS và authorization.

**Tình huống H — Một service hai vai.** Orders nhận token từ Shop, sau đó cần gửi email qua Notifications API. Nó có thể là RS và Client cùng lúc không?

**Giải thích:** Có. Vai trò phụ thuộc lời gọi: Orders là RS đối với Shop và Client đối với Notifications. Mỗi quan hệ phải dùng credential, audience và policy đúng.

## Checklist thiết kế OAuth Client

1. **Định danh đúng vai trò:** phân biệt Client, Resource Owner, AS, RS; ghi rõ vai trò theo từng tương tác.
2. **Đăng ký đúng kiểu:** public/confidential theo khả năng giữ credential; không nhúng secret vào SPA/mobile.
3. **Giới hạn client registration:** redirect URI, grant types, resource/audience, scope, client authentication và PKCE theo chính sách.
4. **Dùng luồng phù hợp:** Authorization Code + PKCE cho user interaction; Client Credentials cho service permissions; không dùng service token giả user.
5. **Phân biệt token:** access token đến RS; OIDC ID token đến RP; refresh token đến AS token endpoint.
6. **Tách `client_id`, `sub`, `aud`, `scope`:** client không phải chủ thể, audience không phải client ID của access token và scope không phải quyền trên mọi object.
7. **Cấp quyền tối thiểu:** AS xét user/tenant consent và policy; không mặc nhiên cấp mọi scope client xin.
8. **Bảo vệ authorization response:** state, PKCE, redirect URI, issuer/mix-up checks và ràng buộc code khi áp dụng.
9. **Giữ token và secret an toàn:** BFF/vault/OS keystore khi phù hợp; không log secret/access/refresh token, không dùng token trong URL.
10. **Thiết kế vòng đời:** TTL, refresh rotation, client credential rotation, session logout, revocation và quyền bị thay đổi.
11. **Kiểm tra tại Resource Server:** signature/introspection, issuer, audience, exp/nbf, type, scope, proof nếu cần và quyền owner/tenant.
12. **Thiết kế downstream rõ ràng:** client credentials, token exchange hoặc delegation đúng AS; không forward token sai audience.
13. **Kiểm thử thất bại:** sai grant, sai client type, secret lộ, redirect/PKCE/state lỗi, audience/scope sai, ID token nhầm, replay, BOLA và cross-tenant.

## Ghi nhớ

**OAuth 2.0 Client là ứng dụng yêu cầu truy cập tài nguyên được bảo vệ, không phải mặc nhiên là người dùng hay Resource Server.** `client_id` nhận diện ứng dụng, nhưng **không phải bí mật**; public client không thể dùng client secret nhúng trong mã để chứng minh danh tính; confidential client phải bảo vệ và xác thực credential theo đăng ký. Trong luồng có user, Client dùng **Authorization Code + PKCE** và tuân thủ consent/policy; trong `client_credentials`, nó nhận quyền **ứng dụng**, không tự đại diện cho user. Access token chỉ được sử dụng đúng **issuer, audience, scope, thời hạn và mục đích**; Resource Server phải tiếp tục phân quyền theo bản ghi/tenant. Lưu trữ, refresh, thu hồi và sender-constraining giúp giảm rủi ro token bị đánh cắp hoặc phát lại, nhưng **không biến Client thành bên được phép làm mọi việc**.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Relying Party and ID Token](https://openid.net/specs/openid-connect-core-1_0.html)
