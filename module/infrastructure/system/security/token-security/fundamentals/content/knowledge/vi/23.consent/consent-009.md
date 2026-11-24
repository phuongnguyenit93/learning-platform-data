# Thay đổi scope yêu cầu consent lại

Một ứng dụng quản lý đơn hàng `shop-web` được người dùng cho phép **đọc đơn hàng** trong lần đăng nhập đầu tiên:

~~~text
OIDC client:              shop-web
User:                     user-742
Resource:                 orders-api
Scopes đã được cho phép:  openid profile orders:read
Scopes trong access token: openid profile orders:read (minh họa)
~~~

Sau khi bổ sung tính năng “hủy đơn”, đội phát triển sửa authorization request thành `scope=openid profile orders:read orders:cancel`. Liệu Authorization Server (AS)/OpenID Provider (OP) có được im lặng cấp thêm `orders:cancel` vì người dùng đã từng consent cho `orders:read`? **Không thể chỉ dựa vào lần consent cũ.** Quyền mới cần được kiểm theo policy và **có thể phải yêu cầu người dùng đồng ý lại** trước khi grant được mở rộng. Ngược lại, nếu lần sau client chỉ xin `orders:read` — một phạm vi nhỏ hơn — việc hiển thị lại màn hình đồng ý không tự động là yêu cầu của OAuth 2.0.

**Nguyên tắc cốt lõi:** *Consent là quyết định có ngữ cảnh, không phải một dấu `approved=true` áp dụng vĩnh viễn cho mọi scope*. Khi client yêu cầu **quyền mới hoặc quyền có tác động khác** ngoài những gì đã được cho phép, AS phải đánh giá lại authorization và các điều kiện consent. **OAuth 2.0 không quy định cứ chuỗi scope thay đổi là bắt buộc hiển thị một màn hình consent.** Quy định cụ thể phụ thuộc grant, cách quản trị quyền, chính sách rủi ro, consent/administrative approval hiện có và profile như OpenID Connect.

Bài thuộc chương **Consent** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết hợp mô hình tin cậy và vòng đời token bảo mật, access/refresh token, JWT/opaque token, xác thực–phân quyền OAuth 2.0/OIDC, scope, audience, việc phát hành/thu hồi token và phòng chống token bị đánh cắp hoặc phát lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **scope được yêu cầu**, **scope client được phép xin**, **scope đã được consent/ủy quyền** và **scope AS thực sự cấp** khác nhau thế nào.
2. Phân biệt **scope mở rộng**, **scope thu hẹp**, **scope thay tên** và **thay đổi ngữ nghĩa quyền** để quyết định khi nào cần consent/approval mới.
3. Mô tả cách Authorization Code + PKCE và OIDC hỗ trợ **incremental authorization/consent** khi ứng dụng bổ sung tính năng.
4. Hiểu vai trò `scope`, `prompt=consent`, `prompt=none`, `offline_access` và `consent_required` trong ngữ cảnh OIDC.
5. Thiết kế consent record theo **subject, client, scope, resource/audience, tenant, purpose, policy version** thay vì một cờ boolean dùng chung.
6. Mô tả điều AS **không được** làm khi Refresh Token Grant hoặc Client Credentials Grant cố xin quyền ngoài grant.
7. Phân tích thay đổi consent tác động đến access JWT, opaque token, refresh token, revocation, caching và Resource Server như thế nào.
8. Đề xuất mô hình UX xin quyền từng bước, sự đồng ý có thông tin, quyền từ chối và cách kiểm chứng chính sách.
9. Áp dụng pseudocode và ví dụ Java/Spring Security cho quyết định cấp scope, consent/reconsent và authorization.
10. Xây dựng ma trận kiểm thử bảo mật khi scope/resource/tenant thay đổi và ngăn privilege escalation.

## 2. Consent là gì và không phải gì?

### 2.1. Consent trong OAuth 2.0/OIDC

**Consent** là một cơ chế giúp **Resource Owner** (thường là end user) biết và, theo chính sách, chấp nhận phạm vi truy cập mà một **OAuth client** yêu cầu đối với tài nguyên được bảo vệ. Authorization Server có thể hỏi người dùng, dựa trên quyết định đã được ghi nhận, hoặc áp dụng quyền đã được **quản trị/chấp thuận từ trước** theo mô hình phù hợp.

Ví dụ:

~~~text
Ứng dụng ShopWeb muốn:
  [x] Xem hồ sơ cơ bản: profile
  [x] Xem đơn hàng: orders:read
  [ ] Hủy đơn hàng: orders:cancel

Quyết định:
  Đã cho phép: profile, orders:read
  Chưa cho phép: orders:cancel
~~~

Dấu chọn là mô hình UX minh họa, **không phải yêu cầu giao diện duy nhất của OAuth**. AS/OP phải biết quyền nào đã được cấp, cho client nào, ở ngữ cảnh nào và liệu có cần tương tác mới không.

### 2.2. Consent, authentication và authorization khác nhau

| Khái niệm | Câu hỏi nó giải quyết | Không đồng nghĩa với |
|---|---|---|
| **Authentication** | Người dùng này là ai, được xác minh theo assurance nào? | Đồng ý cho một ứng dụng đọc/hủy đơn. |
| **Consent** | Người dùng/chủ thể có thẩm quyền đã cho phép client xin loại truy cập nào, theo chính sách? | Quyền mặc định trên mọi đối tượng/tenant. |
| **Client authentication** | Client confidential có chứng minh danh tính bằng secret/key/cert tại token endpoint không? | Người dùng đã cho phép scope mới. |
| **Grant/authorization** | AS cho phép scope/resource nào cho client và principal theo các điều kiện của hệ thống? | Luôn phải hiện consent UI, hoặc chỉ cần consent UI. |
| **Access token validation** | RS có chấp nhận token này về issuer, audience, expiry, purpose, scope không? | Consent còn hiệu lực mãi hoặc có quyền trên mọi bản ghi. |
| **Object-level authorization** | Principal có quyền thực hiện hành động cụ thể trên bản ghi/tenant này không? | Chỉ có `scope=orders:read` là đủ. |

Một màn hình ghi “Đồng ý” không thể hợp thức hóa quyền mà user **không có**. Nếu user không được hủy đơn của tenant khác, ngay cả consent cho `orders:cancel` cũng không vượt object-level policy.

### 2.3. Consent không nhất thiết là UI popup

Các hệ thống có thể dùng:

- **Explicit interactive consent:** người dùng chọn đồng ý khi xin quyền mới.
- **Previously recorded consent:** đã có quyết định hợp lệ cho chính client/scope/resource đó.
- **Administrative/organizational approval:** người có thẩm quyền cấp quyền cho ứng dụng trong môi trường tổ chức.
- **Pre-arranged service authorization:** với một số grant máy–máy, quyền được cấu hình trước thay vì consent tương tác của end user.
- **Policy-based omission:** AS có thể không yêu cầu nhắc lại khi đã có cơ sở hợp lệ và đủ theo profile/chính sách.

**Điểm bất biến không phải “luôn có popup”, mà là AS không được tự phát quyền không được ủy quyền.**

## 3. Năm tập quyền cần phân biệt

Một yêu cầu OAuth có thể đi qua nhiều lớp kiểm:

~~~text
CLIENT_REGISTERED_SCOPES  = scope client đăng ký có thể yêu cầu
REQUESTED_SCOPES          = scope trong authorization request hiện tại
ALREADY_CONSENTED_SCOPES  = scope còn hiệu lực đã được cho phép trong ngữ cảnh
CURRENT_POLICY_ALLOWED    = quyền user/organization/client hiện còn được cấp
ISSUED_SCOPES             = scope cuối cùng ghi vào token hoặc token metadata
~~~

Đối với resource/audience cụ thể, một mô hình bảo thủ:

~~~text
ISSUED_SCOPES ⊆ REQUESTED_SCOPES
ISSUED_SCOPES ⊆ CLIENT_REGISTERED_SCOPES
ISSUED_SCOPES ⊆ CURRENT_POLICY_ALLOWED
ISSUED_SCOPES ⊆ valid authorization/consent outcome
~~~

Đây là **bất biến mô hình minh họa**; hợp đồng thực tế có thể có default scopes, alias/canonical scopes, resource-specific semantics hoặc các extension. Điểm chính: **AS phải kiểm mọi lớp ràng buộc**. Không thể lấy union toàn bộ các scopes user từng có và tự gán vào token.

### 3.1. Một ví dụ tập hợp

~~~text
Client: shop-web
Tenant: tenant-beta
Resource: orders-api

Registered:
  {openid, profile, orders:read, orders:cancel}

Already consented:
  {openid, profile, orders:read}

Currently allowed for user:
  {openid, profile, orders:read, orders:cancel}

Newly requested:
  {openid, profile, orders:read, orders:cancel}

Potential NEW permission:
  {orders:cancel}
~~~

`orders:cancel` **được client đăng ký** và **user có thể có quyền**, nhưng vẫn **chưa có consent/authorization outcome** cho client trong ví dụ. Chính sách có thể yêu cầu user đồng ý hoặc một approval phù hợp; AS không thể cấp đơn giản chỉ vì scope nằm trong registration.

### 3.2. Không gộp scope của nhiều Resource Server

~~~text
orders-api:
  orders:read
  orders:cancel

payments-api:
  payments:read
  payments:refund
~~~

`scope=read` hoặc cùng tên `admin` ở hai resource **không nhất thiết có cùng nghĩa**. AS cần policy theo **resource/audience** (ví dụ RFC 8707 Resource Indicators) và client/tenant/grant. Consent cho xem đơn hàng **không mặc định** là consent đọc thông tin thanh toán.

### 3.3. Scope là chuỗi nhưng ý nghĩa là hợp đồng

Chuỗi scope có thể được thay tên, chia tách hoặc mở rộng nghĩa khi phát triển phiên bản mới. Ví dụ v1 `orders:manage` chỉ cho phép sửa ghi chú; v2 lại bao gồm hoàn tiền. Nếu AS xem hai chuỗi giống nhau và “consent cũ vẫn đủ”, user có thể bị cấp **quyền mạnh hơn điều họ đã hiểu**.

Do đó cần quản trị **scope catalog, semantic version/permission mapping, purpose** và migration. Reconsent có thể cần **ngay cả khi chuỗi scope không đổi**, nếu ý nghĩa hoặc xử lý dữ liệu thay đổi đáng kể theo policy.

## 4. Những thay đổi scope nào cần đánh giá lại consent?

| Thay đổi | Ví dụ | Cách xử lý nguyên tắc |
|---|---|---|
| **Thêm scope mới nhạy cảm** | `orders:read` → thêm `orders:cancel` | Không âm thầm cấp; kiểm policy và xin consent/approval mới khi yêu cầu. |
| **Thêm scope dữ liệu cá nhân** | `openid profile` → thêm `email phone` | Cân nhắc minh bạch mục đích, consent và privacy policy. |
| **Chỉ giảm scope** | `orders:read orders:cancel` → chỉ `orders:read` | Thường không cần xin thêm quyền; có thể phát token hẹp hơn. |
| **Yêu cầu lại cùng scope đã consent còn hiệu lực** | `orders:read` → `orders:read` | Có thể tái sử dụng consent nếu phù hợp client/resource/tenant/policy, trừ khi buộc tương tác lại. |
| **Thêm resource/audience khác** | `orders-api` → thêm `payments-api` | Re-evaluate grant/consent theo resource; không mặc định một scope áp dụng mọi API. |
| **Đổi client identity** | `shop-web` → `partner-analytics` | Consent cũ cho shop-web không phải consent cho partner. |
| **Đổi tenant/organization context** | Beta → Anpha | Kiểm consent và quyền tổ chức riêng, tránh cross-tenant escalation. |
| **Đổi mục đích dữ liệu** | Đọc email để gửi hóa đơn → dùng cho marketing | Có thể cần consent mới dù scope string giống nhau, theo chính sách và pháp luật áp dụng. |
| **Đổi ngữ nghĩa scope** | `reports:read` mở rộng để đọc PII nhạy cảm | Version hóa quyền và đánh giá consent lại. |
| **Consent bị thu hồi/hết hạn** | Người dùng rút `orders:read` | Không dùng grant cũ; không cấp access token mới theo scope đã bị thu hồi. |
| **Policy buộc prompt lại** | Reauthentication/consent renewal theo rủi ro | Áp policy ngay cả khi scopes không đổi. |
| **Mở rộng client registration** | AS admin thêm `payments:refund` vào allowlist | **Không tự đồng nghĩa** người dùng đã đồng ý quyền mới. |

**Kết luận:** Phải **đánh giá lại** khi ngữ cảnh hoặc quyền thay đổi. **Có phải hiển thị consent mới** hay không phụ thuộc phương thức approval hợp lệ và profile; **không được mở rộng grant trái phép**.

### 4.1. So sánh bằng tập hợp, không bằng thứ tự chuỗi

~~~text
Previously approved: "openid profile email"
New request:         "email openid profile"

As sets:
  {openid, profile, email} == {email, openid, profile}
~~~

Đổi thứ tự biểu diễn scope **không tạo scope mới**. Một AS/authorization service nên parse token scope thành tập và đối chiếu với catalog thay vì dùng so sánh raw string để hiện consent vô cớ.

### 4.2. Scope alias cần mapping có kiểm soát

Nếu `order.read` và `orders:read` thực sự là alias cùng quyền, AS có thể canonicalize theo **server-owned mapping**, không dựa vào chuỗi client tự định nghĩa. Nếu không chắc alias có cùng ngữ nghĩa, xử lý như thay đổi quyền cần review/authorization mới.

### 4.3. “Cấp ít hơn” khác “tự mặc định thêm quyền”

AS có thể cấp subset được phép và client phải tôn trọng `scope` thực tế trong token/response; việc app hiển thị “tính năng hủy đơn đã bật” dựa trên *requested scopes* thay vì **granted scopes** sẽ khiến ứng dụng xử lý sai hoặc bị bypass ở backend nếu cũng tin UI.

## 5. Quy trình Authorization Code + PKCE khi xin thêm scope

Giả sử user đã dùng `shop-web` với `orders:read`, sau đó bấm nút “Hủy đơn”. Đây là điểm tự nhiên để **incremental authorization** — chỉ xin quyền mạnh hơn khi thật sự cần.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as End-User
    participant B as Browser
    participant C as OIDC Client / BFF
    participant AS as Authorization Server / OP
    participant DB as Consent + Grant Store
    participant RS as Orders API

    U->>B: Bấm Xem đơn hàng
    B->>C: Bắt đầu authorization
    C->>AS: /authorize scope=openid orders:read + state, PKCE
    AS->>DB: Kiểm policy và consent
    AS-->>B: Consent nếu cần và redirect code
    B->>C: Callback code/state
    C->>AS: POST /token code + verifier
    AS-->>C: Access A1 scope=orders:read

    U->>B: Bấm Hủy đơn hàng
    B->>C: Yêu cầu tính năng mới
    C->>AS: /authorize scope=openid orders:read orders:cancel
    AS->>DB: Kiểm scope mới, user, tenant, client và consent
    AS-->>U: Xin đồng ý quyền mới nếu policy yêu cầu
    U-->>AS: Đồng ý hoặc từ chối
    alt Quyền mới được cấp hợp lệ
      AS->>DB: Lưu consent/grant theo ngữ cảnh
      AS-->>B: Redirect authorization code mới
      B->>C: Callback state/code
      C->>AS: Token request với PKCE/client auth
      AS-->>C: Access A2 có scopes thực tế được cấp
      C->>RS: Hủy đơn với A2 và quyền trên bản ghi
      RS-->>C: Cho phép hoặc từ chối theo policy
    else Không có quyền/không đồng ý
      AS-->>B: Authorization error hoặc grant hẹp theo contract
      C-->>B: Không bật tính năng hủy đơn
    end
~~~

Mermaid biểu thị một **quy trình hợp lệ điển hình**, không bắt buộc mọi OP luôn có màn hình consent. Quyết định cuối cùng phải được AS kiểm; Resource Server vẫn phải kiểm **scope, audience, expiry và object-level authorization**.

### 5.1. Authorization request ban đầu

~~~http
GET /oauth2/authorize?response_type=code&
  client_id=shop-web&
  redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
  scope=openid%20orders%3Aread&
  state=STATE_FOR_INITIAL_REQUEST&
  code_challenge=PKCE_CHALLENGE_INITIAL&
  code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

Ví dụ xuống dòng để dễ đọc; thực tế phải encode thành **một HTTPS URL hợp lệ**. `state` và `code_verifier` phải gắn một authorization transaction; không dùng lại verifier hoặc state cố định.

### 5.2. Xin thêm quyền tại điểm sử dụng

~~~http
GET /oauth2/authorize?response_type=code&
  client_id=shop-web&
  redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
  scope=openid%20orders%3Aread%20orders%3Acancel&
  state=NEW_STATE_FOR_INCREMENTAL_REQUEST&
  code_challenge=NEW_PKCE_CHALLENGE&
  code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

**Đây là một authorization request mới**. AS kiểm consent và policy hiện hành, không dùng một access token cũ rồi thêm `scope` vào request tới Resource Server để “nâng quyền”.

### 5.3. Nếu user từ chối thì sao?

Ứng dụng phải chấp nhận khả năng quyền mới không được cấp:

- Không giả vờ `orders:cancel` đã được chấp thuận.
- Không gửi token `orders:read` tới API hủy đơn rồi hy vọng API bỏ kiểm.
- Giữ những chức năng cũ **chỉ khi grant/session cũ vẫn hợp lệ**.
- Có thể giải thích lý do xin quyền, cung cấp lựa chọn hủy thao tác hoặc thử lại khi user chủ động.
- Không tạo vòng lặp redirect consent liên tục để ép user chấp thuận.

Một request bị từ chối có thể trả authorization error như `access_denied`. Nếu AS phát phạm vi hẹp hơn trong trường hợp được protocol/provider hỗ trợ, client phải kiểm **phạm vi được cấp thực tế** và không bật chức năng chưa được cấp.

### 5.4. Consent thay đổi không tự làm user xác thực lại

Việc hỏi “Cho phép ứng dụng hủy đơn?” khác hỏi “Hãy xác minh lại bằng MFA trước khi hủy đơn”. Một hệ thống có thể cần **cả consent và step-up authentication** cho hành động có rủi ro; consent không phải proof user vừa nhập MFA.

## 6. `prompt=consent` và `prompt=none` trong OIDC

**OpenID Connect Core** định nghĩa tham số `prompt` trong authentication request. Nó có thể thay đổi cách OP tương tác với End-User, nhưng không được dùng để bỏ qua kiểm authorization.

### 6.1. `prompt=consent`: yêu cầu tương tác consent

Một OIDC request minh họa:

~~~http
GET /authorize?response_type=code&
  client_id=shop-web&
  redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
  scope=openid%20profile%20email&
  prompt=consent&
  state=STATE_EXAMPLE&
  code_challenge=PKCE_CHALLENGE_EXAMPLE&
  code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

`prompt=consent` yêu cầu OP nhắc người dùng consent theo OIDC. **Không có nghĩa OP phải cấp mọi scope** hoặc user bắt buộc đồng ý; quyền vẫn phụ thuộc policy, consent và các giới hạn khác.

Khi phạm vi mới cần người dùng quyết định, OP có thể hiển thị consent theo policy **ngay cả khi không có `prompt=consent`**, nếu request chứa quyền chưa được cho phép.

### 6.2. `prompt=none`: không được tương tác

`prompt=none` yêu cầu OP **không hiển thị UI đăng nhập hoặc consent**. Nếu authorization request cần tương tác mới, OP phải trả lỗi thích hợp, ví dụ `consent_required` hoặc `login_required` theo ngữ cảnh OIDC, thay vì âm thầm chấp thuận quyền mới.

~~~text
Current consent:
  openid profile

Request:
  scope=openid profile email
  prompt=none

If policy requires new consent:
  no interactive prompt can be shown
  -> return an authorization error (e.g., consent_required)
~~~

Client nên xử lý bằng **luồng authorization tương tác do user khởi tạo**, không retry `prompt=none` vô hạn hoặc fallback sang Client Credentials để xin email của user.

### 6.3. Lưu ý `prompt=consent` không đồng nghĩa “scope mới”

AS/OP có thể yêu cầu user consent lại **ngay cả khi scope không đổi** (ví dụ chính sách recertification hoặc `prompt=consent`). Ngược lại, một quyền mới có thể được cấp trên cơ sở một **administrative approval hợp lệ** nếu policy/profile cho phép, mà không cần bắt user thấy popup.

### 6.4. `offline_access` cần quan tâm riêng

Trong OIDC, `offline_access` liên quan yêu cầu có khả năng truy cập khi user không còn hiện diện, thường thông qua **refresh token** được OP cấp theo điều kiện. Nó **không chỉ là thêm một trường hồ sơ**.

~~~text
Original request:
  scope = openid profile

Updated request:
  scope = openid profile offline_access
~~~

Điều này có thể thay đổi đáng kể vòng đời quyền. Theo OIDC Core, việc xin `offline_access` có các quy tắc consent đặc thù, bao gồm yêu cầu `prompt=consent` trong các trường hợp được quy định hoặc điều kiện phù hợp cho việc thu thập consent; OP phải tuân theo chi tiết chuẩn và chính sách. **Không hiểu rằng chỉ cần nối `offline_access` là AS bắt buộc phát refresh token**.

### 6.5. `max_age` và `auth_time` không thay consent

`max_age` liên quan độ mới của user authentication; `auth_time` ghi thời điểm user được xác thực theo OIDC. Đây không phải bản ghi consent. Một lần người dùng reauthenticate **không tự cấp thêm `payments:refund`**, và một lần consent mới **không tự chứng minh user vừa MFA**.

## 7. Consent record phải gắn đúng ngữ cảnh

Một cờ toàn cục `consent_accepted=true` là quá yếu cho hệ thống đa client, đa resource hoặc nhiều tenant. Tối thiểu, hệ thống cần biết **ai cho phép, cho ứng dụng nào, quyền gì, trong phạm vi nào, theo policy phiên bản nào**.

### 7.1. Một cấu trúc logic minh họa

~~~yaml
# CHỈ LÀ SCHEMA MINH HỌA, KHÔNG PHẢI CẤU HÌNH CHẠY ĐƯỢC.
consentRecord:
  issuer: https://login.example.com
  subjectRef: user-742
  clientId: shop-web
  tenantId: tenant-beta
  resources:
    - orders-api
  grantedScopes:
    - openid
    - profile
    - orders:read
  purposeIds:
    - view-orders
  policyVersion: "2026-11"
  grantedAt: "2026-11-23T08:00:00Z"
  expiresAt: "2027-02-23T08:00:00Z"
  status: ACTIVE
  decisionSource: USER_CONSENT
  revision: 7
~~~

Các trường `tenantId`, `purposeIds`, `policyVersion`, thời hạn và `decisionSource` **không phải trường bắt buộc trong OAuth token response**, mà là metadata quản trị consent/authorization theo thiết kế. Không đưa PII/thông tin grant không cần thiết vào access JWT chỉ để lưu consent record.

### 7.2. Identity key: không ghép user bằng email

Trong OIDC, danh tính bên ngoài nên gắn với **trusted issuer + `sub`** (có thể còn subject/sector/client context theo thiết kế). Email, số điện thoại và `preferred_username` có thể thay đổi hoặc tái sử dụng.

~~~text
unsafeConsentKey = email
betterConsentContext = (issuer, stableSubject, clientId, resource, tenant)
~~~

Nếu cùng email nhưng đến từ issuer khác, consent ở OP A **không tự áp dụng** cho OP B. Cũng không được dùng consent của user A cho user B chỉ vì chung tenant hoặc thiết bị.

### 7.3. Version hóa ngữ nghĩa scope

Một catalog có thể gắn `orders:cancel` với:

~~~yaml
permission:
  scope: orders:cancel
  definitionVersion: 2
  resource: orders-api
  action: cancel
  dataCategories: [order-identity, order-status]
  sensitivity: high
  requiresUserConsent: true
  requiresRecentAuthentication: true
~~~

Đây là **policy ví dụ**; yêu cầu recent authentication độc lập với consent. Khi thay đổi version có tác động đáng kể, AS cần quyết định **consent cũ có đủ** hay phải gia hạn, migration, hoặc reset grant.

### 7.4. Lưu consent an toàn

- Truy cập/ghi consent record theo **trusted user identity, client/grant, resource và tenant**; không nhận `subjectRef` do client tự chọn như authority.
- Dùng transaction/versioning để tránh lost update và race giữa hai consent screens.
- Lưu audit tối thiểu: ai quyết định, thời gian, client, scopes trước/sau, nguồn approval và policy version; không ghi raw token/client secret.
- Có revocation/expiry và đường chỉnh sửa quyền đã cấp.
- Hạn chế retention và PII theo chính sách.
- Có thể phải phân biệt **user consent** với **admin consent**; quyền tổ chức được cấp không nên giả vờ user riêng lẻ đã bấm “Đồng ý”.

## 8. Đánh giá lại scope bằng nguyên tắc least privilege

Một Authorization Server cần đánh giá yêu cầu trong ngữ cảnh, ví dụ:

~~~text
originalRequest = {openid, profile, orders:read}
activeConsent   = {openid, profile, orders:read}
newRequest      = {openid, profile, orders:read, orders:cancel}

newRequestedScopes = newRequest - activeConsent
                   = {orders:cancel}

if newRequestedScopes is not empty:
    evaluate registration, principal permission, client, tenant,
    target resource, consent and risk policy

    when policy requires user interaction:
        request informed consent before issuing new scope
~~~

Nhưng **hiệu tập hợp không đủ cho mọi trường hợp**. Phải đánh giá lại nếu:

- Consent hết hạn hoặc bị thu hồi.
- Client identity, issuer, resource/audience, tenant hoặc mục đích đã thay đổi.
- Scope cũ bị sửa ngữ nghĩa.
- Quyền thực tế của user đã giảm.
- Chính sách buộc hỏi lại hoặc step-up.
- Grant/session/approval không còn phù hợp.

### 8.1. Quyền cấp cuối cùng không vượt quyết định cho phép

~~~text
requested           = {orders:read, orders:cancel}
registered          = {orders:read, orders:cancel}
userAllowed         = {orders:read, orders:cancel}
consentOutcome      = {orders:read}
issuedToOrdersApi   = {orders:read}
~~~

Nếu user từ chối `orders:cancel`, token không được có `orders:cancel`, kể cả registration/client secret/user role có chứa quyền đó. AS có thể từ chối cả flow hoặc cấp subset **khi hợp đồng cụ thể cho phép**; client phải xử lý đúng.

### 8.2. Không xin mọi scope từ đầu chỉ để khỏi hiện consent sau này

Ứng dụng có thể cố xin `orders:cancel payments:refund profile email phone address` ngay ở login đầu tiên để tránh consent screen sau. Điều này gây:

- Quyền/PII được xin trước khi có nhu cầu thực tế.
- User khó hiểu mục đích và có thể chấp thuận một gói quyền quá rộng.
- Access token nếu bị đánh cắp có **blast radius lớn hơn**.
- Khó thu hồi một nhóm quyền riêng mà không ảnh hưởng chức năng khác.

**Incremental authorization** giúp xin đúng quyền tại điểm người dùng kích hoạt chức năng, và làm rõ ngữ cảnh.

## 9. Sự khác biệt giữa authorization request và token request

### 9.1. Token endpoint không phải màn hình xin consent

Trong Authorization Code flow, việc user được yêu cầu consent (nếu có) thường xảy ra trong **authorization interaction** ở OP/AS. Sau đó client đổi authorization code tại **token endpoint**:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <CONFIDENTIAL_CLIENT_AUTH_EXAMPLE>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=CODE_FOR_APPROVED_AUTHORIZATION&
redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
code_verifier=VERIFIER_BOUND_TO_CODE
~~~

AS phải gắn code với client/redirect/PKCE và **grant đã được phê duyệt**. Không để client gửi thêm `scope=orders:cancel` vào token request rồi tự phát quyền mới chỉ vì client đã xác thực.

### 9.2. Access token phản ánh granted scope, không chỉ requested scope

Một response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_EXAMPLE_ONLY",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Theo RFC 6749, trường `scope` phải được trả về khi phạm vi đã cấp **khác phạm vi được yêu cầu** (và có thể xuất hiện trong các trường hợp khác tùy provider). Client nên lưu **quyền thực tế** được cấp theo protocol/profile và không dựa vào màn hình UI đã render trước đó.

### 9.3. Không nhầm ID token với consent outcome

OIDC ID token có `sub`, `iss`, `aud` và các claims xác thực; nó **không tự là danh sách đầy đủ consent cho từng Resource Server**. Một ID token `aud=shop-web` không phải quyền được phép gọi Orders API. Access token cùng AS phát vẫn phải có audience và scope phù hợp.

## 10. Refresh Token Grant không thể dùng để xin scope ngoài grant

Sau khi user đã consent `orders:read`, BFF có thể giữ refresh token để xin access token mới. Nếu BFF thử:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <SHOP_BFF_AUTH_EXAMPLE>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=R1_READ_ONLY_EXAMPLE&
scope=orders%3Aread%20orders%3Acancel
~~~

thì nó **không tự có quyền `orders:cancel`**. Theo **RFC 6749 `6**, scope tùy chọn trong refresh request **không được chứa phạm vi ngoài scope đã cấp ban đầu**. AS phải từ chối việc mở rộng trái phép, hoặc xử lý scope theo policy/chuẩn phù hợp; không chỉ copy `scope` mà client muốn vào access token.

### 10.1. Khi muốn thêm quyền phải làm gì?

Cần một **authorization request mới** theo flow phù hợp để AS kiểm user/client/grant/tenant/resource và, khi chính sách yêu cầu, xin **consent/approval mới**. Grant mới hoặc grant đã được cập nhật đúng cách mới có thể cấp quyền bổ sung. **Không giả định refresh token cũ được tự động nâng quyền** khi một authorization transaction khác thành công.

### 10.2. Downscoping khi refresh

~~~text
Original grant:
  orders:read orders:cancel

Refresh request:
  scope=orders:read

Possible issued access token:
  scope=orders:read
~~~

Việc giảm scope không đòi quyền bổ sung, nhưng AS vẫn kiểm client, grant, token validity, user status, consent revocation và current policy. Một refresh token bị revoke **không thể được cứu** bằng request scope hẹp hơn.

### 10.3. Refresh token rotation khác consent renewal

Refresh token rotation phát R2 thay R1, có thể phát hiện replay của R1 đã spent. **Đây là bảo vệ credential**, không phải hành vi user đồng ý một scope mới. Đồng ý thêm quyền cũng không chứng minh R1 chưa bị đánh cắp. Không gửi refresh token tới UserInfo hoặc Orders API; nó dành cho **AS token endpoint**.

### 10.4. Access token JWT cũ không tự đổi scope

Nếu A1 chứa `scope=orders:read`, AS nhận consent mới cho `orders:cancel` không làm claim trong A1 tự thay đổi. Client phải nhận **access token mới** được AS cấp đúng quyền; Resource Server kiểm token thực tế, không đọc flag consent từ UI.

## 11. Client Credentials: không có end user để “consent lại” theo mặc định

Một công việc máy–máy dùng `grant_type=client_credentials` được cấp quyền của **dịch vụ**, không phải bằng chứng user đang hiện diện.

~~~text
Client:          billing-worker
Grant:           client_credentials
Tenant:          tenant-beta
Existing scope:  invoices:read
Requested next:  invoices:read invoices:write
~~~

Để bổ sung `invoices:write`, AS cần kiểm client registration, permission policy, tenant, resource và **administrative/organizational approval** nếu có. Không thể chỉ thấy client secret hợp lệ rồi cấp quyền mới.

**Có thể không có consent UI của end user** trong trường hợp này. Chủ thể có thẩm quyền quản trị service grant phải phê duyệt phù hợp và có audit; đừng gắn nhãn “user đã consent” cho một hành động chỉ được admin/service policy chấp thuận.

RFC 6749 nêu refresh token **SHOULD NOT** được phát trong Client Credentials Grant. Confidential client thường xin access token mới bằng chính client authentication khi token hết hạn; phương thức ấy **không tự mở rộng scopes**.

## 12. Thêm Resource Server hoặc audience cũng cần đánh giá

### 12.1. Cùng tên scope ở hai API có thể mang nghĩa khác

~~~text
Resource orders-api:
  scope=read -> đọc đơn hàng

Resource payments-api:
  scope=read -> đọc thông tin thanh toán
~~~

Consent `read` cho Orders **không tự là consent `read` cho Payments**. Một consent model chỉ lưu danh sách scope strings mà **không có resource/audience/purpose context** có thể dẫn tới cross-resource privilege escalation.

### 12.2. RFC 8707 Resource Indicators

Khi AS hỗ trợ, authorization request có thể chỉ rõ:

~~~text
resource=https://api.example.com/orders
scope=orders:read
~~~

Nếu client muốn đổi thành:

~~~text
resource=https://api.example.com/payments
scope=payments:read
~~~

AS phải kiểm grant/consent cho resource mới, đăng ký client, user/tenant permissions và policy. **`aud` là quyết định phát hành của AS** theo mapping resource; nó không nhất thiết bằng đúng chuỗi `resource` từng ký tự.

### 12.3. Multi-audience làm tăng blast radius

Một bearer token được chấp nhận ở nhiều API có thể bị lộ ở một nơi rồi bị replay ở nơi khác. AS nên cân nhắc resource-specific access tokens, TTL hợp lý, least privilege và thông tin consent rõ **API nào** sẽ nhận quyền.

## 13. Consent nhiều tenant và administrative approval

Giả sử:

~~~text
Issuer:     https://login.example.com
Subject:    user-742
Client:     analytics-web
Audience:   reports-api

Current consent:
  tenant-beta, reports:read -> ACTIVE

New request:
  tenant-anpha, reports:read
~~~

Không được tái sử dụng consent tenant Beta để mở quyền tenant Anpha. AS phải xác minh subject, membership, tổ chức, role, tenant-specific approval, client và resource; RS tiếp tục kiểm tenant/object-level authorization.

| Tình huống | Cơ sở cho phép có thể phù hợp | Không được suy diễn |
|---|---|---|
| User đồng ý chia sẻ email cơ bản | User consent theo OIDC/OP policy. | Quyền tenant admin. |
| Admin Beta cho SaaS đọc báo cáo Beta | Admin consent có authority cho Beta. | Quyền Anpha. |
| Admin cấp service grant cho `billing-worker` | Organizational/service policy. | User cụ thể vừa consent. |
| User có consent nhưng không có quyền xóa báo cáo | Không cấp scope/action vượt user permissions. | Consent biến user thành superuser. |
| Client mới muốn lại scope cũ của client khác | Cần consent/approval riêng theo client. | Consent cũ chuyển giao được chỉ nhờ tên app giống nhau. |

### 13.1. Chỉ lưu tenant ID không tạo ranh giới bảo mật

Request `X-Tenant-Id: tenant-anpha` do caller gửi không phải bằng chứng được quyền tenant đó. AS/RS kiểm tenant context từ **principal/grant/policy đáng tin**, không tự chấp nhận tenant claim trong request.

### 13.2. Consent không thay object-level authorization

Ngay cả khi user đã consent `reports:read` cho Beta, họ có thể chỉ được xem một số báo cáo. Resource Server còn phải kiểm ownership, ACL và data classification cho **từng bản ghi**. Consent là một lớp trong permission model, không tự cho tất cả dữ liệu.

## 14. Thu hồi consent và token đã cấp

### 14.1. Thu hồi hôm nay không tự sửa JWT hôm qua

~~~text
09:55  AS phát A1, scope=orders:read orders:cancel, exp=10:10.
10:00  User rút consent cho orders:cancel.
10:01  Client thử refresh grant cũ.
10:02  Orders API nhận A1 vẫn còn thời gian sử dụng.
10:10  A1 tự hết hạn.
~~~

**AS:** ngăn cấp token mới với quyền đã bị thu hồi, cập nhật/revoke grant/refresh token family theo policy.

**RS:** Nếu chỉ validate JWT cục bộ, A1 **có thể còn được chấp nhận** đến `exp`. Muốn chặn tức thời cần state/denylist/token-version check hoặc kiến trúc tương đương. Với opaque access token, introspection có thể báo inactive nhưng caching vẫn có độ trễ.

**Không hứa rút consent có hiệu lực tức thì ở mọi API** khi hệ thống chưa có cơ chế revoke token còn hiệu lực.

### 14.2. RFC 7009 Token Revocation

**RFC 7009** mô tả endpoint để client yêu cầu thu hồi token tại AS. Tác động đến token khác trong grant phụ thuộc profile/provider và cách RS kiểm trạng thái. API nghiệp vụ không tự thu hồi refresh grant chỉ vì UI báo “đã bỏ quyền”.

### 14.3. Refresh token khi consent bị rút

AS có thể:

- Revoke refresh grant/family, yêu cầu authorization mới.
- Giữ grant hẹp và chỉ phát scope còn được phép nếu protocol/policy cho phép.
- Dùng grants/families riêng theo resource hoặc nhóm scope.
- Áp absolute/idle expiry và rotation/reuse detection độc lập.

Client không được tiếp tục gửi một refresh token đã revoke hoặc lấy UserInfo/role cache cũ để khôi phục quyền.

### 14.4. Consent và session cũng không đồng nhất

User vẫn có thể **đăng nhập tại OP** nhưng đã rút consent của một ứng dụng. Ngược lại, user logout khỏi web/BFF chưa chắc AS grant đã bị revoke. ID token, access token, refresh token, browser session và consent record có **vòng đời khác nhau**.

### 14.5. Sự kiện thu hồi phải đi qua cache

Consent cache của AS, token introspection cache, Resource Server permission cache và frontend feature flags có thể lưu thông tin cũ. Thiết kế cần TTL, invalidation và **fail-closed semantics** theo rủi ro, không chỉ xóa nút UI rồi coi quyền đã bị thu hồi ở backend.

## 15. Consent UI: rõ ý nghĩa, đúng thời điểm, chấp nhận từ chối

### 15.1. Trình bày sự thay đổi chứ không chỉ scope string

**Khó hiểu:**

~~~text
ShopWeb requests:
  orders:read orders:cancel offline_access
  [Allow]
~~~

**Dễ hiểu hơn:**

~~~text
ShopWeb đã được phép:
  - Xem những đơn hàng bạn có quyền đọc.

ShopWeb yêu cầu thêm:
  - Hủy những đơn hàng bạn có quyền hủy.
  - Duy trì quyền truy cập khi bạn không mở ứng dụng
    (nếu offline_access được xin và thực sự có tác dụng này).

[Cho phép quyền bổ sung] [Không cho phép]
~~~

Thông tin phải phản ánh **scope thực, resource, mục đích và thời hạn** theo policy, không giấu quyền ghi/xóa đằng sau “truy cập tài khoản”.

### 15.2. Incremental authorization tốt hơn xin mọi scope ngay ở login

Nếu người dùng mới muốn xem đơn, không cần xin `payments:refund`, `orders:cancel`, `phone` và `address` trước khi tính năng được dùng. Xin ít scope giúp giảm PII và **blast radius khi access token bị lộ**.

Tuy vậy, không biến incremental consent thành trải nghiệm bị làm phiền liên tục. AS nên tái sử dụng **consent còn hiệu lực đúng ngữ cảnh**, chỉ hiển thị lại khi có lý do chính đáng hoặc `prompt`/policy yêu cầu.

### 15.3. Consent screen là bề mặt bảo mật

- Bind quyết định với authorization transaction, client ID, redirect URI, user/session, scopes và resource.
- Có CSRF protection, clickjacking protection và giao diện nhận biết client đáng tin.
- Không dùng form hidden field `approvedScopes` do browser tự sửa làm authority nếu chưa validate server-side.
- Kiểm version và trạng thái consent; không để request cũ ghi đè quyết định revoke mới.
- Từ chối là hợp lệ: không ép loop hoặc âm thầm xin qua grant khác.

### 15.4. Consent khác reauthentication và MFA

Việc hỏi “cho phép hủy đơn” **không tự chứng minh** user đã thực hiện MFA gần đây. Một thao tác nhạy cảm có thể cần **cả consent và step-up authentication**; kiểm `auth_time`, `acr`/`amr` theo profile chứ không coi `prompt=consent` là MFA.

## 16. Luồng quyết định phía Authorization Server

~~~mermaid
flowchart TD
    A[Authorization request] --> B[Validate client, issuer, redirect, PKCE context]
    B --> C{Client allowed requested scopes and resources?}
    C -- No --> X[Reject or narrow according to protocol]
    C -- Yes --> D{User and tenant policy permit?}
    D -- No --> X
    D -- Yes --> E[Load consent or other valid authorization context]
    E --> F{Scope semantics, purpose, tenant and resource unchanged?}
    F -- Yes --> G{Prompt or policy requires interaction?}
    F -- No --> H[Evaluate new permission and applicable approval]
    H --> I{Valid noninteractive authority exists?}
    I -- Yes --> J[Persist verified authorization outcome]
    I -- No --> K{Interactive consent allowed?}
    K -- No --> L[Return authorization error]
    K -- Yes --> M[Show informed consent tied to request]
    M --> N{Permission approved?}
    N -- No --> X
    N -- Yes --> J
    G -- Yes --> M
    G -- No --> O[Reuse valid prior grant]
    J --> P[Calculate effective granted scopes]
    O --> P
    P --> Q[Issue code or token within approved grant]
~~~

Trong OIDC với `prompt=none`, nếu bắt buộc tương tác, AS **không hiển thị UI** mà trả authorization error thích hợp như `consent_required`. Sơ đồ là logic học tập, không định nghĩa mọi HTTP error hoặc quy trình admin consent.

### 16.1. Pseudocode xác định quyền mới

~~~text
function evaluateConsentNeed(request, verifiedUser, client):
    requested = normalizeRequestedScopes(request.scope)
    resources = resolveApprovedResources(request.resource)

    assert client.active and request.redirectUri matches registration
    assert requested within client.allowedScopesAndResources

    userAllowed = policy.currentPermissions(
        verifiedUser, client, resources, request.tenant
    )
    if requested exceeds userAllowed:
        reject or narrow according to protocol and policy

    old = consentStore.findValid(
        trustedIssuer, verifiedUser.sub, client.id,
        resources, request.tenant, purpose
    )

    prior = validScopesConsideringVersionExpiryAndRevocation(old)
    newlyRequested = requested minus prior

    needsInteraction = (
        policy.requiresConsent(newlyRequested, request.purpose)
        OR policy.requiresReconsent(old, currentContext)
        OR request.prompt contains "consent"
    )

    if needsInteraction:
        if request.prompt contains "none":
            reject with consent_required
        decision = showConsentBoundToAuthorizationTransaction(
            verifiedUser, client, resources, requested, purpose
        )
        if decision denies required permission:
            reject or narrow only when policy permits
        consentStore.atomicSave(decision, policyVersion, audit)

    granted = calculateScopesFromValidatedGrant(
        requested, userAllowed, consentAndApprovalOutcome
    )
    issueAuthorizationCodeBoundTo(
        verifiedUser, client, redirectUri, pkceChallenge,
        granted, resources, transaction
    )
~~~

Pseudocode không thay implementation chuẩn OAuth/OIDC. Thực tế cần xử lý client registration, redirect matching, user authentication, CSRF/state/PKCE, exact errors, atomic code usage và consent concurrency. **`verifiedUser` phải đến từ authentication đáng tin, không từ `request.user_id`.**

### 16.2. Consent race: hai tab và revoke đồng thời

~~~text
Tab A: user approves orders:read.
Tab B: user approves orders:read orders:cancel.
Tab C: user revokes orders:cancel.
~~~

Consent store cần revision/compare-and-set/transaction để không mất update, và policy xác định precedence giữa **approval mới** với **revocation mới hơn**. Không chỉ dùng last-write-wins trên record không có version; đừng gộp mọi consent thành union rồi làm quyền bị revoke sống lại.

## 17. Java: tính toán scope mới và quyết định có cần consent lại

Một authorization service có thể tách phép kiểm quyền thành **pure policy function** để dễ kiểm thử, nhưng đừng nhầm phép tính scope với toàn bộ OAuth Authorization Server.

### 17.1. Java 17: quyết định consent

Ví dụ sử dụng `Set` để tránh nhầm **thứ tự scope string** với **sự thay đổi quyền**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public final class ScopeConsentPolicy {
    private ScopeConsentPolicy() {}

    public enum Decision {
        REUSE_VALID_CONSENT,
        SHOW_INTERACTIVE_CONSENT,
        CONSENT_REQUIRED_WITHOUT_UI,
        REJECT_NOT_PERMITTED
    }

    public static Decision evaluate(
            Set<String> requestedScopes,
            Set<String> clientRegisteredScopes,
            Set<String> principalAllowedScopes,
            Set<String> consentedScopes,
            boolean consentContextStillValid,
            boolean promptConsent,
            boolean promptNone) {

        Objects.requireNonNull(requestedScopes);
        Objects.requireNonNull(clientRegisteredScopes);
        Objects.requireNonNull(principalAllowedScopes);
        Objects.requireNonNull(consentedScopes);

        // "prompt=none" không được kết hợp với prompt khác theo OIDC.
        if (promptConsent && promptNone) {
            throw new IllegalArgumentException("invalid_prompt_combination");
        }

        if (!clientRegisteredScopes.containsAll(requestedScopes)
                || !principalAllowedScopes.containsAll(requestedScopes)) {
            return Decision.REJECT_NOT_PERMITTED;
        }

        Set<String> notYetConsented = new HashSet<>(requestedScopes);
        notYetConsented.removeAll(consentedScopes);

        boolean needsConsent = promptConsent
            || !consentContextStillValid
            || !notYetConsented.isEmpty();

        if (!needsConsent) {
            return Decision.REUSE_VALID_CONSENT;
        }
        return promptNone
            ? Decision.CONSENT_REQUIRED_WITHOUT_UI
            : Decision.SHOW_INTERACTIVE_CONSENT;
    }
}
~~~

### 17.2. Giải thích phạm vi của hàm

Hàm trên **chỉ minh họa policy tiêu biểu**: nếu client/user chưa được quyền, reject; nếu consent record còn phù hợp và cover scopes, có thể reuse; nếu cần consent mới và `prompt=none`, phải xử lý lỗi không tương tác.

**Không phải mọi application đều buộc gọi consent UI khi có scope mới:** Nếu có **valid noninteractive administrative authorization** hoặc profile/policy cho phép, thuật toán hoàn chỉnh sẽ xét thêm nguồn approval đó trước khi chọn UI. Hàm ở trên cố tình **không mô hình hóa** admin approval để người học nhìn rõ trường hợp user consent.

Bộ gọi còn phải bảo đảm:

- `consentContextStillValid` đến từ **issuer, subject, client, resource, tenant, purpose, policy version, expiry và revoke state đã xác minh**, không phải boolean từ request browser.
- `principalAllowedScopes` do AS/authorization backend tính, không copy role do client gửi.
- `requestedScopes` phải parse từ request chuẩn, kiểm naming và canonical scope semantics.
- Phương thức không phát token; AS vẫn phải xác thực user, client, redirect URI, PKCE/grant và xác minh kết quả tương tác.
- `SHOW_INTERACTIVE_CONSENT` chưa đồng nghĩa user đã đồng ý; **chỉ quyết định sau khi user thực sự cho phép** mới cập nhật grant.
- `REJECT_NOT_PERMITTED` là mã nội bộ; OAuth/OIDC error response cụ thể cần tuân giao thức.
- **Thay đổi ý nghĩa cùng một tên scope** phải được phản ánh bằng `consentContextStillValid=false` hoặc policy/version mới.

### 17.3. Ví dụ kết quả

~~~text
registered = {openid, profile, orders:read, orders:cancel}
allowed    = {openid, profile, orders:read, orders:cancel}
consented  = {openid, profile, orders:read}

requested = {openid, profile, orders:read}
context valid = true
promptConsent = false
promptNone = false
  -> REUSE_VALID_CONSENT

requested = {openid, profile, orders:read, orders:cancel}
context valid = true
promptConsent = false
promptNone = false
  -> SHOW_INTERACTIVE_CONSENT

requested = {openid, profile, orders:read, orders:cancel}
context valid = true
promptConsent = false
promptNone = true
  -> CONSENT_REQUIRED_WITHOUT_UI

requested = {openid, profile, payments:refund}
  -> REJECT_NOT_PERMITTED
~~~

Khi resource hoặc tenant thay đổi, **không được giữ `context valid=true`** chỉ vì cùng một tập scope string.

## 18. Spring Authorization Server: consent lưu ở đâu?

Hệ sinh thái Java có thể sử dụng **Spring Authorization Server** để xử lý OAuth 2.0/OIDC authorization, client registration và consent. Bài này minh họa **khái niệm cấu hình**, không thay security filter chain hoặc authorization endpoint của một AS hoàn chỉnh.

### 18.1. Registration yêu cầu PKCE và consent

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

public final class RegisteredClientExample {
    private RegisteredClientExample() {}

    public static RegisteredClient shopWeb(String encodedSecret) {
        return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("shop-web")
            .clientSecret(encodedSecret)
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC
            )
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE
            )
            .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN
            )
            .redirectUri("https://shop.example.com/callback")
            .scope("openid")
            .scope("profile")
            .scope("orders:read")
            .scope("orders:cancel")
            .clientSettings(
                ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build()
            )
            .build();
    }
}
~~~

**`requireAuthorizationConsent(true)` không có nghĩa user đã consent tất cả scopes được đăng ký.** Nó cấu hình AS yêu cầu xử lý consent theo framework. Một record consent có thể cho `orders:read` và **chưa** cho `orders:cancel`, dù client registration liệt kê cả hai.

**`requireProofKey(true)` liên quan PKCE**, bảo vệ Authorization Code flow; nó không thay user consent, client authentication hoặc Object-Level Authorization.

### 18.2. Vì sao scope trong RegisteredClient chưa đủ?

Một `RegisteredClient` chỉ biểu diễn **client có thể yêu cầu scope nào**. Quyền token thực sự được cấp cần đi qua:

~~~text
RegisteredClient scopes
    ∩ requested scopes
    ∩ authenticated principal/tenant policy
    ∩ consent or other valid grant approval
    ∩ resource/audience constraints
    -> authorized scopes in grant/token
~~~

Nếu thêm `orders:cancel` vào builder sau deploy, client chỉ mới được **phép xin** scope đó — không tự có consent của user. Đừng chuyển `client.getScopes()` thành `JWT.scope` mà bỏ các lớp kiểm.

### 18.3. Authorization consent service

Spring Authorization Server cung cấp abstraction **`OAuth2AuthorizationConsentService`** để lưu và tra consent của một registered client/principal. Triển khai có thể dùng in-memory cho test hoặc persistent store cho production.

Conceptual flow:

~~~text
authorization request arrives
  -> AS identifies registered client and authenticated principal
  -> load OAuth2AuthorizationConsent by client + principal
  -> compare requested scopes with consented authorities/scopes
  -> show consent when framework/policy requires
  -> save validated consent outcome
  -> continue authorization code issuance
~~~

**Lưu ý multi-tenant:** consent service mặc định không thay bạn quản lý mọi metadata như **resource, tenant, purpose, scope semantic version, expiry hoặc consent revocation**. Một hệ thống B2B có thể cần custom repository/authorization policy hoặc mô hình grant bổ sung để đảm bảo không dùng consent Beta cho Anpha. Không dựa chỉ vào một record theo client/principal nếu quyền thực tế có nhiều tài nguyên hoặc nhiều mục đích.

### 18.4. Production cần registration ổn định

`UUID.randomUUID()` trong đoạn minh họa là ID tạm khi dựng một bản ghi; production nên có **client registration ID ổn định trong persistent repository**, không tạo lại record mỗi lần AS restart rồi làm sai consent/grant mapping. `encodedSecret` phải do server chuẩn bị bằng password encoder/secret management thích hợp; raw client secret thuộc confidential client, **không đưa cho browser**.

### 18.5. Consent UI trong Spring phải đi cùng server-side validation

Nếu custom UI lấy danh sách scopes và quyết định user, AS phải đối chiếu scopes user đã chọn với **request/registration/policy trên server** trước khi lưu `OAuth2AuthorizationConsent`. Không tin hidden form fields hoặc session ID do caller sửa được. Dùng CSRF protection và ràng buộc authorization request/transaction để tránh scope injection.

### 18.6. Spring Resource Server vẫn kiểm token riêng

Ví dụ một endpoint hủy đơn chỉ nhận token đủ quyền:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {
    private final OrdersPolicy ordersPolicy;

    public OrdersController(OrdersPolicy ordersPolicy) {
        this.ordersPolicy = ordersPolicy;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:cancel')")
    @PostMapping("/orders/{orderId}/cancel")
    public void cancel(@PathVariable String orderId) {
        // Scope chỉ là lớp đầu tiên.
        // Ứng dụng phải kiểm owner/tenant/status của đơn hiện tại.
        ordersPolicy.requireCancelPermission(orderId);
        ordersPolicy.cancel(orderId);
    }
}
~~~

`OrdersPolicy` là hợp đồng nghiệp vụ minh họa, chưa triển khai trong bài. Trong thực tế, cấu hình bảo mật phải bật method security (`@EnableMethodSecurity`), Resource Server JWT/opaque validation, issuer/audience/expiry/token type và principal/tenant mapping. **Spring expression `hasAuthority` chỉ kiểm authority đã map**, không tự xác minh người dùng có quyền hủy đúng order.

### 18.7. Một thay đổi scope không biến access token thành “có consent vĩnh viễn”

Resource Server phải dùng scope/token hiện tại; nếu cần tác động revoke tức thì, thêm state/denylist/policy check. Không yêu cầu `orders:cancel` từ UI rồi cho backend bypass check dựa trên cookie `consentApproved`.

## 19. Lỗi OAuth/OIDC và xử lý ở client

### 19.1. Những lỗi thường gặp

| Tình huống | Error/đặc tả có thể áp dụng | Client nên xử lý |
|---|---|---|
| User từ chối quyền mới | `access_denied` ở authorization endpoint. | Không bật tính năng cần scope đó; giữ scope cũ nếu grant còn hợp lệ. |
| `prompt=none` nhưng cần user consent | `consent_required` theo OIDC. | Bắt đầu authorization tương tác khi user chủ động, không retry silent vô hạn. |
| `prompt=none` nhưng user chưa có phiên login | `login_required` theo OIDC. | Thực hiện login nếu cần, không giả vờ consent. |
| Xin scope không hợp lệ/vượt policy | `invalid_scope` hoặc lỗi profile tương ứng. | Sửa request hoặc xin grant hợp lệ, không tự bypass. |
| Resource indicator không được AS cho phép | `invalid_target` theo RFC 8707 khi được hỗ trợ. | Không tự đổi audience, xử lý resource grant. |
| Client bị chặn grant hoặc authentication sai | `unauthorized_client`/`invalid_client` theo nơi phát sinh. | Kiểm registration/credentials, không downgrade authentication. |
| Refresh token xin thêm scope ngoài grant | `invalid_scope`/`invalid_grant` theo ngữ cảnh. | Quay lại authorization flow mới; không retry refresh để leo thang. |
| Access token cũ thiếu scope khi gọi API | HTTP `403`, Bearer `insufficient_scope` nếu đúng profile. | Xin quyền qua authorization flow hợp lệ, không gửi scope trong API query. |
| Access token hết hạn/revoked | HTTP `401`, Bearer `invalid_token` khi phù hợp. | Refresh hoặc reauthorize theo policy; không dùng token cũ mãi. |
| Consent record bị revoke/hết hạn | AS yêu cầu approval mới hoặc từ chối. | Hủy/graceful degradation, không dùng cached `approved=true`. |

Mã lỗi cụ thể và status HTTP phụ thuộc **endpoint** (authorization, token hay Resource Server), profile và provider; bảng không có ý nghĩa tất cả lỗi luôn trả cùng JSON. Với redirect-based authorization errors, AS thường trả qua redirect URI theo OAuth/OIDC khi an toàn và hợp lệ.

### 19.2. Không nhầm `consent_required` và `invalid_scope`

- **`consent_required`** trong OIDC có thể nghĩa là có một yêu cầu mà OP chỉ giải quyết được khi tương tác xin consent, nhưng client đã yêu cầu không được hiển thị UI.
- **`invalid_scope`** có thể nghĩa scope được yêu cầu không hợp lệ, sai cách viết hoặc không thể cấp theo quy tắc.
- **`access_denied`** thường biểu thị Resource Owner hoặc AS từ chối authorization.

Không tự làm một loop cứ tăng scope hoặc bỏ `prompt=none` cho đến khi token trả thành công mà không xét rủi ro/ý định người dùng.

### 19.3. Client phải đọc granted scope trong response

Nếu AS trả access token chỉ có `orders:read`, client không được lập tức enable “Cancel order” vì *trước đó đã yêu cầu `orders:cancel`*. Với JWT, có thể dùng authorized-client/token metadata đáng tin theo profile; với opaque token, RS kiểm bằng introspection. **Không tự decode JWT chưa xác minh để quyết định quyền**.

### 19.4. Lỗi consent không cho phép fallback sang Client Credentials

Nếu browser user từ chối `payments:refund`, BFF **không được âm thầm dùng client_credentials của chính backend rồi giả `user_id`** để thực hiện hoàn tiền. Service permissions là một authority khác và phải có endpoint/grant/policy riêng; không được dùng làm lối đi vòng user consent.

## 20. Threat model: lỗi khiến phạm vi quyền bị mở rộng

| Sai lầm hoặc kiểu tấn công | Hậu quả | Biện pháp |
|---|---|---|
| **Copy requested scopes vào token** | Client xin `admin` rồi được cấp dù chưa có quyền. | AS xác minh registration, policy và consent outcome. |
| **Lưu duy nhất `consent=true`** | Một lần đồng ý thành quyền cho mọi scope về sau. | Consent record theo scope, client, issuer/sub, resource, tenant, purpose và version. |
| **Dùng consent client A cho client B** | Ứng dụng khác thừa hưởng quyền cũ. | Bind consent với registered client identity. |
| **Scope cùng tên ở hai audiences** | `read` của Orders mở sang Payments. | Resource-specific grant/consent và audience validation. |
| **Không version scope semantics** | Consent cũ “đọc báo cáo” mở thành đọc PII. | Scope catalog version và quyết định reconsent. |
| **Consent vượt user permissions** | User không có quyền xóa nhưng “đồng ý” thành admin. | AS kiểm quyền subject/tenant; RS kiểm object-level authorization. |
| **`prompt=none` bị bỏ qua** | AS âm thầm cấp thêm scope cần UI. | Nếu cần interaction, trả lỗi OIDC phù hợp. |
| **`prompt=consent` bị lạm dụng** | Client ép user đồng ý qua vòng lặp. | Cho phép từ chối, rate limit, UX rõ ràng. |
| **Refresh token xin scope mới** | R1 read-only đổi thành access token admin. | Không vượt grant gốc theo RFC 6749 `6. |
| **Client Credentials vượt user consent** | BFF dùng service token giả user sau khi user từ chối. | User grant và service permission riêng, không impersonate tùy ý. |
| **Form consent tin hidden fields** | Browser tự đổi `approvedScopes`. | Server-side scope validation, CSRF và transaction binding. |
| **Consent UI clickjacking/CSRF** | Quyền bị cấp ngoài ý chí user. | Anti-CSRF, CSP/frame protection và request correlation. |
| **Consent cache không gắn tenant** | Beta được dùng vào Anpha. | Cache keys theo subject/client/resource/tenant/policy. |
| **Revoke không cập nhật grant** | Token mới vẫn chứa quyền đã rút. | Invalidate AS grant/consent cache, re-evaluate issuance. |
| **JWT cũ còn hạn** | RS vẫn cho phép sau khi consent bị revoke. | TTL/state/denylist/introspection theo risk/SLA. |
| **Race hai consent transactions** | Ghi đè revoke bằng approval cũ. | Version/CAS/transaction và conflict policy. |
| **Consent key chỉ là email** | Email đổi/tái sử dụng, quyền gắn sai user. | Trusted issuer + verified subject. |
| **UI mô tả khác scope thực** | User thấy “đọc” nhưng cấp quyền “xóa”. | Review scope-to-text mapping và contract tests. |
| **Log raw access token/code trong consent flow** | Credential leakage qua APM/trace. | Log metadata allowlist, scrub tại nguồn. |
| **Scope đủ nhưng đối tượng không thuộc user** | BOLA/IDOR hoặc cross-tenant access. | Resource Server kiểm ACL/ownership và tenant. |

### 20.1. Giả mạo client và consent phishing

Attacker có thể đăng ký OAuth client với tên/logo giống ứng dụng thật. User nhìn thấy màn hình consent và nghĩ đang cấp quyền cho ứng dụng hợp pháp. AS cần kiểm **registered redirect URI, verified publisher/client identity khi hỗ trợ**, hiển thị scope/resources rõ và hạn chế open redirect.

### 20.2. Consent fatigue không phải tính năng

Nhắc consent lặp lại cho các quyền rộng, không liên quan tính năng có thể làm user bấm “Cho phép” theo thói quen. Xin quyền lúc cần (incremental authorization), giải thích tác động và có nút từ chối thật là thiết kế tốt hơn.

### 20.3. Consent không bảo vệ bearer token khỏi bị lấy

Ngay cả consent hợp lệ, access token bị lộ qua log, XSS hoặc hệ thống lưu trữ vẫn có thể bị replay khi còn hiệu lực. Kết hợp **TTL ngắn, audience/scope tối thiểu, token storage an toàn, sender constraints nếu áp dụng và revocation strategy**.

## 21. Audit và giám sát các thay đổi consent

Một sự kiện consent phải trả lời: **ai cho phép, cho client nào, scope/resource/tenant nào, khi nào và dựa trên policy nào?**

### 21.1. Audit event minh họa

~~~json
{
  "event": "oauth_consent_changed",
  "issuer": "https://login.example.com",
  "subject_ref": "internal-user-ref-742",
  "client_id": "shop-web",
  "tenant_ref": "tenant-beta",
  "resource": "orders-api",
  "scopes_before": ["openid", "profile", "orders:read"],
  "scopes_after": ["openid", "profile", "orders:read", "orders:cancel"],
  "change_type": "SCOPE_ADDED",
  "decision_source": "USER_CONSENT",
  "policy_version": "2026-11",
  "result": "APPROVED",
  "trace_id": "6fcb1a7e44974c59b4b8a2dc1110e280"
}
~~~

Ngay cả `subject_ref`, `tenant_ref`, danh sách scope cũng có thể là dữ liệu liên kết user và có tính nhạy cảm. Thiết lập RBAC, retention và chỉ ghi dữ liệu tối thiểu. **Không** log access/refresh token, authorization code, client secret, session cookie hoặc raw authorization header.

### 21.2. Phân biệt sự kiện theo nguồn quyền

~~~text
CONSENT_REQUESTED
CONSENT_APPROVED
CONSENT_DENIED
CONSENT_REVOKED
CONSENT_EXPIRED
CONSENT_CONTEXT_CHANGED
ADMIN_APPROVAL_GRANTED
ADMIN_APPROVAL_REVOKED
SCOPE_ISSUANCE_REJECTED
GRANT_REVOKED
TOKEN_REVOKED
~~~

**Admin approval không phải user consent**: hai nguồn cần nhãn khác nhau, nhất là khi xử lý quyền tổ chức và quyền dịch vụ.

### 21.3. Metrics không chứa user/token ID

~~~text
oauth_consent_decision_total{result=approved|denied|error}
oauth_consent_reprompt_total
oauth_consent_revoked_total
oauth_scope_issuance_rejected_total{reason=policy|scope|resource}
oauth_consent_store_conflict_total
oauth_grant_revocation_total
~~~

Không dùng raw email, subject, access token, refresh token hoặc grant family làm metric labels. Theo dõi số lần consent tăng bất thường sau deploy, silent authorization loops và scope mismatch giữa request với token.

### 21.4. Sự cố: token có `orders:cancel` mà consent chưa có

1. So sánh `requested_scopes`, `granted_scopes` và `issued_scopes`.
2. Kiểm client registration vừa thay đổi.
3. Kiểm authorization policy và scope semantic mapping/version.
4. Xác minh consent/approval có nguồn hợp lệ và đúng tenant/resource.
5. Kiểm AS có copy registration scopes vào token hay không.
6. Kiểm refresh token có bị dùng để mở rộng grant trái phép không.
7. Đánh giá revoke JWT/opaque tokens đã cấp sai và API calls bị ảnh hưởng.
8. Sửa server policy và thêm regression tests.

**Ẩn nút hủy đơn ở UI không sửa được JWT được cấp sai scope**. Ranh giới quyết định phải nằm ở AS và RS.

## 22. Kiểm thử consent và reconsent

### 22.1. Fixture

~~~text
Issuer:   https://login.example.com
Client:   shop-web
User:     user-742
Tenant:   tenant-beta
Resource: orders-api

Registered scopes:
  openid profile orders:read orders:cancel

Current user permissions:
  openid profile orders:read orders:cancel

Prior valid consent:
  openid profile orders:read

Newly requested:
  orders:cancel
~~~

Mỗi test dùng dữ liệu và authorization code riêng để tránh nhầm code đã dùng/revoked với case đang kiểm.

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Same scopes, consent còn hạn | Xin lại `orders:read`. | Có thể reuse consent theo policy. |
| Chỉ thay thứ tự scope | `profile openid orders:read`. | Không coi là scope mới. |
| Thêm scope nhạy cảm | Xin `orders:cancel` chưa consent. | AS đánh giá permission/consent; không tự phát quyền. |
| User đồng ý scope mới | Quyết định được lưu theo transaction hợp lệ. | Có thể phát scope nếu mọi policy cho phép. |
| User từ chối | Consent interaction trả denied. | Không cấp scope mới, error/subset theo contract. |
| Scope mới, `prompt=none` | AS không thể silent grant khi cần consent. | `consent_required` hoặc lỗi phù hợp, không hiển thị UI. |
| Same scope, `prompt=consent` | Yêu cầu tương tác rõ. | OP xử lý prompt đúng OIDC, không cấp ngoài policy. |
| Downscope | Chỉ xin `orders:read` từ grant rộng hơn. | Không tăng quyền; không yêu cầu consent mới chỉ vì giảm scope. |
| Client chưa đăng ký quyền | Thêm `orders:cancel` ngoài allowlist. | Không phát quyền dù user có role. |
| User không có quyền | User chỉ được đọc nhưng muốn cancel. | Không phát cancel dù click consent. |
| Consent thuộc client khác | Dùng record `shop-mobile` cho `shop-web`. | Không reuse chéo client. |
| Consent thuộc issuer khác | Cùng email nhưng issuer khác. | Không reuse. |
| Consent thuộc user khác | B lấy record của A. | Không reuse. |
| Tenant khác | Consent Beta cho request Anpha. | Không cấp quyền Anpha theo consent Beta. |
| Audience khác | Consent Orders cho Payments. | Không cấp Payments theo consent Orders. |
| Scope semantics v2 mạnh hơn v1 | Cùng string, policy version đổi. | Re-evaluate consent/approval. |
| Consent bị revoke hoặc hết hạn | Record không active. | Không dùng để cấp token mới. |
| Admin approval hợp lệ | Có authority tổ chức được xác minh. | Có thể cấp theo policy, không ghi giả user consent. |
| Browser sửa form | `approvedScopes=payments:refund`. | AS chặn scope injection/CSRF. |
| Race và revoke | Tab cũ lưu approval sau revoke mới. | Versioning không hồi sinh quyền bị rút. |
| Refresh request xin scope ngoài grant | R1 read-only xin cancel. | Không mở rộng grant. |
| Client Credentials tự thêm quyền | Service secret hợp lệ, chưa có approval. | Không cấp permission mới. |
| JWT cũ sau revoke | JWT valid nhưng consent vừa bị rút. | Kiểm behavior theo TTL/state policy, không giả định instant revocation. |
| Opaque token cache sau revoke | Introspection cache stale. | Kiểm freshness/invalidation policy. |
| BOLA | User có read scope nhưng đọc order tenant khác. | RS từ chối. |
| Token bị log trong consent UI | Canary access token trong APM. | Test thất bại nếu secret xuất hiện. |

### 22.2. Pseudocode tests

~~~text
test "new scope needs valid authorization outcome":
    requested = {openid, profile, orders:read, orders:cancel}
    consented = {openid, profile, orders:read}
    result = authorize(requested, consented, requireConsentForNew=true)
    assert result does not issue orders:cancel before user approval

test "silent authorization cannot add unseen scope":
    consented = {orders:read}
    requested = {orders:read, orders:cancel}
    result = authorize(prompt="none", requested, consented)
    assert result is consent_required or equivalent policy error
    assert no new cancel-scope access token is issued

test "refresh cannot expand original grant":
    R1.grantedScopes = {orders:read}
    result = refresh(R1, scope={orders:read, orders:cancel})
    assert no access token has orders:cancel

test "cross-tenant consent isolation":
    consent = approve(user742, shopWeb, tenantBeta, ordersApi, ordersRead)
    result = authorize(user742, shopWeb, tenantAnpha, ordersApi, ordersRead)
    assert consent of Beta is not reused as authority for Anpha

test "revocation wins against stale save":
    approve(scope=ordersCancel, revision=10)
    revoke(scope=ordersCancel, revision=11)
    trySaveStaleApproval(scope=ordersCancel, revision=10)
    assert currentGrant(ordersCancel) is not active
~~~

Đây là pseudocode để thiết kế tests. Integration tests thật phải đi qua token endpoint/AS, signed JWT hoặc opaque token metadata, persistence, concurrency và RS permission enforcement.

## 23. Bài tập tình huống có đáp án

### Bài 1 — Đổi thứ tự scope

~~~text
Consent active: openid profile email
New request:    email openid profile
~~~

**Đáp án:** Không phải scope mới chỉ vì thứ tự đổi; nếu consent vẫn hợp lệ, không thay resource/client/tenant/purpose và policy không bắt tương tác, có thể reuse.

### Bài 2 — Thêm quyền hủy đơn

~~~text
Old consent: orders:read
New request: orders:read orders:cancel
User role: can cancel owned orders
~~~

**Đáp án:** Role cho biết user **có thể** hủy trong giới hạn quyền, không tự là consent cho client xin `orders:cancel`. Nếu policy cần consent, phải xin và kiểm decision. RS vẫn phải xác minh ownership/trạng thái đơn khi thực hiện.

### Bài 3 — Cùng scope, đổi resource

~~~text
Old: resource=orders-api; scope=read
New: resource=payments-api; scope=read
~~~

**Đáp án:** Không tái sử dụng consent chỉ vì tên `read` giống nhau. Đánh giá resource permissions, client allowlist, audience và consent/approval riêng.

### Bài 4 — Consent bị revoke, access JWT còn hạn

User rút `orders:cancel` lúc 10:00. JWT A1 có scope đó và `exp=10:10`; RS chỉ kiểm signature/expiry offline.

**Đáp án:** Không bảo đảm RS từ chối từ 10:00. Muốn hiệu lực nhanh cần denylist/token version/state checks hoặc token TTL/introspection design phù hợp. AS phải không phát token mới với scope đã rút.

### Bài 5 — `prompt=none` gặp scope mới

Client xin `orders:cancel` nhưng chưa consent và `prompt=none`.

**Đáp án:** OP không được hiển thị UI; nếu tương tác bắt buộc, trả lỗi OIDC như `consent_required`. Client khởi động flow tương tác khi user chọn tính năng, không tự nâng quyền.

### Bài 6 — Admin đồng ý cho service

`billing-worker` được tổ chức Beta cho `invoices:read`, muốn `invoices:write`.

**Đáp án:** Đây có thể là organizational admin approval của service grant, không nhất thiết popup user consent. AS cần kiểm authority admin, tenant, scopes/resources và audit; client secret không tự trao quyền viết.

### Bài 7 — Scope giữ tên nhưng đổi nghĩa

`reports:read` ban đầu chỉ đọc số liệu tổng hợp. Bản mới cho phép đọc dữ liệu cá nhân chi tiết.

**Đáp án:** Không chỉ so tên scope. Cần version/purpose review và đánh giá lại consent/approval khi tác động quyền thay đổi, theo policy và quy định áp dụng.

### Bài 8 — Client xin quyền rồi lại dùng access token cũ

Frontend hiện “Đã đồng ý hủy đơn”, nhưng access token chỉ có `orders:read`.

**Đáp án:** Không bật quyền hủy ở backend. Phải nhận **token mới** có granted scope hợp lệ, RS còn kiểm object-level permission. UI toast không thay JWT claims/grant.

## 24. Checklist triển khai

- [ ] Phân biệt requested, registered, consented/approved, currently allowed và issued scopes.
- [ ] Consent không là một cờ toàn cục dùng cho mọi quyền và mọi thời điểm.
- [ ] Scope parsing/canonicalization dùng catalog phía AS; thay thứ tự chuỗi không tạo quyền mới.
- [ ] Thêm scope có tác động mới phải được đánh giá consent/approval và policy trước khi cấp.
- [ ] Giảm scope không bị xem là escalation chỉ vì raw string khác.
- [ ] Đổi issuer, client, resource/audience, tenant, purpose hoặc scope semantics cần đánh giá lại context.
- [ ] AS kiểm quyền user/organization; consent không biến người thiếu quyền thành admin.
- [ ] Incremental authorization đi qua flow phù hợp, thường Authorization Code + PKCE.
- [ ] OIDC `prompt=consent` và `prompt=none` được xử lý đúng, không silent grant quyền cần UI.
- [ ] `offline_access`/refresh-token issuance được đánh giá riêng theo OIDC/AS policy.
- [ ] Refresh Token Grant không tăng scope ngoài grant gốc; cần authorization mới hợp lệ cho scope mới.
- [ ] Client Credentials có service/admin approval riêng, không giả end-user consent.
- [ ] Consent record gắn issuer, subject, client, scopes, resource, tenant, purpose, version, expiry và revoke status theo mô hình.
- [ ] Consent UI có thông tin quyền bổ sung rõ ràng, CSRF/clickjacking protection và quyền từ chối thật.
- [ ] Atomic consent storage với revision/transaction không phục hồi quyền đã revoke qua race.
- [ ] AS phát token trong authorized scopes/audiences, không copy requested scopes tùy ý.
- [ ] Client dùng granted scopes thực tế; không dựa trên UI/ID token làm phép chứng minh quyền API.
- [ ] RS kiểm access token issuer, audience, expiry, purpose, scope và quyền bản ghi/tenant.
- [ ] Thu hồi consent ngăn phát token mới; có SLA/cơ chế xử lý JWT/opaque tokens đang còn hiệu lực.
- [ ] Access/refresh token không bị lộ qua browser log, APM, URL hoặc consent audit.
- [ ] Audit sự thay đổi theo subject/client/resource/tenant/policy và phân biệt admin vs user approval.
- [ ] Có tests cho new scope, downscope, changed audience, wrong client/issuer/tenant, revoke, `prompt=none`, refresh escalation và BOLA.
- [ ] Thiếu bằng chứng authorization hợp lệ thì **fail closed**.

**Ghi nhớ:** **Thay đổi scope cần đánh giá lại authorization và consent, nhưng không phải mọi thay đổi chuỗi đều bắt buộc hiện lại màn hình đồng ý.** Thêm quyền, thay mục đích, đổi resource/tenant/client hoặc đổi ngữ nghĩa scope có thể cần approval/reconsent mới; giảm scope thường không cần thêm quyền. **Refresh token không phải đường nâng quyền**, và Resource Server vẫn phải kiểm token cùng quyền trên tài nguyên ngay cả sau khi user đã consent.

## 25. Tài liệu chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** `3.3` scope, `4.1` authorization code, `4.4` client credentials, `6` refreshing an access token và token-response `scope`.
- **OpenID Connect Core 1.0:** `prompt=consent`, `prompt=none`, `consent_required`, `offline_access` và mối quan hệ authentication/consent.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** authorization security, PKCE, tokens và replay.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** ràng buộc authorization code trong flow yêu cầu scope mới.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource/audience scoping và policy.
- **RFC 9396 — OAuth 2.0 Rich Authorization Requests:** `authorization_details` cho quyền cần biểu diễn hơn scope strings.
- **RFC 9126 — OAuth 2.0 Pushed Authorization Requests (PAR):** cơ chế đẩy authorization request bảo vệ bối cảnh tham số.
- **RFC 9101 — JWT-Secured Authorization Request (JAR):** ràng buộc integrity của request parameters.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** `scope`, `aud`, `client_id` và RS validation.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `iat`.
- **RFC 8725 — JWT Best Current Practices:** issuer/audience validation và token substitution.
- **RFC 7662 — OAuth 2.0 Token Introspection:** active state/metadata của opaque access token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoke grants/tokens sau consent changes.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** `insufficient_scope`, `invalid_token` và bảo vệ bearer credential.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained tokens.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** client authentication và token binding.
- **OWASP OAuth 2.0 Cheat Sheet / Authorization Cheat Sheet:** least privilege, token handling, redirect/consent-related threats.
- **OWASP API Security Top 10:** Broken Object Level Authorization và Broken Function Level Authorization.
- **Spring Authorization Server Reference:** `RegisteredClient`, `ClientSettings.requireAuthorizationConsent`, `OAuth2AuthorizationConsentService` và consent UI.
- **Spring Security OAuth2 Client / Resource Server Reference:** authorized-client scopes, JWT/opaque token validation và permission enforcement.

