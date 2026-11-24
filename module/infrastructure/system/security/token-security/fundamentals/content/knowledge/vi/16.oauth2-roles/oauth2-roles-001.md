# Resource owner

Một ứng dụng quản lý đơn hàng cho phép người dùng đăng nhập bằng OpenID Connect (OIDC), sau đó xem đơn hàng qua API. Khi triển khai OAuth 2.0, lập trình viên có thể nói: “Người dùng đăng nhập chính là **resource owner**, vậy access token của người ấy được đọc mọi đơn hàng”. Vế đầu **có thể đúng trong một ngữ cảnh cụ thể**; vế sau **không đúng**.

Trong OAuth 2.0, **resource owner** là *thực thể có khả năng cho phép truy cập một tài nguyên được bảo vệ*. Nếu thực thể ấy là con người, tiêu chuẩn thường gọi họ là *end user*. Resource owner có thể ủy quyền cho một **OAuth client** yêu cầu quyền truy cập; **Authorization Server (AS)** đánh giá và cấp token; **Resource Server (RS)** bảo vệ dữ liệu và kiểm token lẫn quyền thực tế.

Có ba ý cần tách bạch:

- **Ai có thẩm quyền cho phép truy cập?** Resource owner hoặc chủ thể được tổ chức ủy quyền theo mô hình quyền.
- **Token cho phép làm gì và gửi đến đâu?** Authorization Server quyết định scope, audience và các ràng buộc của grant.
- **Có được thao tác trên bản ghi cụ thể không?** Resource Server kiểm policy, tenant, ownership và các quy tắc nghiệp vụ ở thời điểm request.

Bài thuộc chương **OAuth2 roles** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung làm rõ vị trí resource owner trong mô hình tin cậy và vòng đời token, liên hệ JWT, opaque token, access token, refresh token, claims, scope, audience, xác thực, phân quyền, OIDC, thu hồi và bảo vệ chống đánh cắp/phát lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa đúng **resource owner** theo OAuth 2.0 và giải thích khi nào đó là end user, tổ chức hoặc chủ thể được ủy quyền.
2. Phân biệt resource owner với **OAuth client**, **Authorization Server** và **Resource Server**; nhận diện vai trò của từng bên trong một request.
3. Phân biệt **authentication**, **authorization**, **consent** và **quyền truy cập tài nguyên cụ thể**.
4. Mô tả Authorization Code + PKCE/OIDC từ góc nhìn resource owner mà không nhầm ID token với access token.
5. Giải thích mối quan hệ giữa `sub`, `scope`, `aud`, `client_id`, tenant và chủ sở hữu bản ghi.
6. Phân tích trường hợp **client credentials** không có end user trực tiếp, cùng giới hạn của delegation/token exchange.
7. Thiết kế và kiểm thử việc RS áp dụng quyền của resource owner mà không gây IDOR/BOLA, nhầm tenant hoặc token substitution.
8. Nêu các biện pháp giảm rủi ro khi access/refresh token hoặc phiên đăng nhập bị đánh cắp.

## 2. Resource owner theo định nghĩa OAuth 2.0

Theo **RFC 6749**, resource owner là **entity capable of granting access to a protected resource** — thực thể có khả năng cấp phép truy cập tài nguyên được bảo vệ. Khi đó là con người, thực thể ấy được gọi là **end user**.

Trong thực tế, thực thể có khả năng cấp phép có thể xuất hiện ở nhiều dạng:

| Bối cảnh | Ai có thể là resource owner/chủ thể có thẩm quyền? | Điểm cần lưu ý |
|---|---|---|
| Tài khoản cá nhân lưu ảnh | Người dùng sở hữu bộ ảnh | Họ có thể đồng ý cho một client đọc ảnh trong phạm vi được phép. |
| SaaS quản lý doanh nghiệp | Doanh nghiệp/tổ chức và người quản trị **được ủy quyền** thay mặt tổ chức | Người nhấn nút đồng ý chưa chắc là người sở hữu pháp lý mọi dữ liệu. |
| Hệ thống y tế/tài chính | Chủ thể dữ liệu, người đại diện hoặc bên có thẩm quyền theo quy tắc nghiệp vụ và pháp luật áp dụng | OAuth không tự giải quyết tất cả yêu cầu về pháp lý, đại diện và phạm vi sử dụng dữ liệu. |
| Dịch vụ nội bộ dùng service identity | Tổ chức quản lý tài nguyên và policy cho ứng dụng/dịch vụ | Không nhất thiết có end user hiện diện trong mỗi lần xin token. |
| Kho tài liệu dùng chung | Chủ tài liệu, nhóm hoặc workspace có mô hình chia sẻ | Quyền đọc/chỉnh sửa có thể được cấp cho người không sở hữu bản ghi. |

**OAuth không định nghĩa ai là chủ sở hữu pháp lý của tài sản hay dữ liệu trong mọi hệ thống.** Nó định nghĩa các vai trò giao thức và việc một client lấy quyền truy cập từ AS theo chính sách. Tổ chức và ứng dụng phải xác định **ai thực sự có thẩm quyền cấp quyền**.

### 2.1. Resource owner không mặc nhiên là người đang đăng nhập

Một admin có thể đăng nhập để phê duyệt quyền truy cập dữ liệu thuộc tổ chức. Người đăng nhập là **người thực hiện thao tác authorization**, nhưng dữ liệu có thể thuộc tổ chức. Một người dùng có thể đọc tài liệu được chia sẻ mà không phải là **owner** của tài liệu.

Tương tự, nếu `user-742` đăng nhập ở tenant Beta, không có nghĩa người đó được truy cập mọi tài nguyên trong Beta hoặc trong tenant khác. **Một phiên đăng nhập hợp lệ không phải chứng chỉ sở hữu mọi bản ghi.**

### 2.2. Resource owner có luôn xuất hiện trong access token không?

Không. Một access token có thể biểu diễn một principal bằng `sub`, nhưng:

- `sub` là **subject của token theo hợp đồng với issuer**, không phải một claim chuẩn có tên “resource_owner”.
- Với một grant đại diện cho end user, `sub` thường nói về người dùng liên quan.
- Với **client credentials**, `sub` có thể đại diện cho ứng dụng/service, tùy token profile, và không có end user trực tiếp.
- Quyền sở hữu bản ghi thường nằm trong **database hoặc authorization policy**, không thể suy ra chỉ từ `sub`.

Resource Server phải hiểu **token type, issuer, grant/principal model** trước khi diễn giải bất cứ claim nào.

## 3. Bốn vai trò OAuth 2.0 và ranh giới tin cậy

OAuth 2.0 định nghĩa bốn vai trò chính:

| Vai trò | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Resource Owner (RO)** | Ai có thẩm quyền cấp phép truy cập tài nguyên được bảo vệ? | Người dùng `user-742` hoặc tổ chức qua admin hợp lệ. |
| **Client** | Ứng dụng nào muốn truy cập tài nguyên, thay mặt chủ thể hoặc theo quyền của chính nó? | `shop-web`, `analytics-worker`. |
| **Authorization Server (AS)** | Ai xác thực, đánh giá grant và phát hành access token? | `https://login.example.com`. |
| **Resource Server (RS)** | Ai lưu/bảo vệ tài nguyên và xác minh access token? | `orders-api`. |

Những vai trò này **có thể nằm trong một sản phẩm hoặc tổ chức**, nhưng cần giữ tách biệt về **trách nhiệm bảo mật**. Ví dụ AS và RS cùng dùng hạ tầng không có nghĩa RS được bỏ kiểm access token.

### 3.1. Ví dụ khái niệm

~~~text
Resource owner / user: user-742
OAuth client:           shop-web
Authorization Server:   https://login.example.com
Resource Server:        orders-api
Protected resource:     GET /orders/42
~~~

Ứng dụng `shop-web` **không tự trở thành resource owner** chỉ vì nó hiển thị dữ liệu. Nó có thể được cấp quyền để yêu cầu một access token và dùng token gọi API theo scope/audience. Access token lại **không đồng nghĩa API tự cấp quyền trên mọi đơn hàng**.

### 3.2. Sơ đồ các mối quan hệ

~~~mermaid
flowchart LR
    RO[Resource Owner / Người dùng hoặc chủ thể có thẩm quyền]
    C[OAuth Client]
    AS[Authorization Server]
    RS[Resource Server]
    D[(Protected Resource)]

    RO -->|Ủy quyền theo giao thức và chính sách| AS
    C -->|Yêu cầu authorization / token| AS
    AS -->|Access token được cấp cho client| C
    C -->|Gọi API với access token| RS
    RS -->|Kiểm token và quyền trên tài nguyên| D
    RS -. Không mặc nhiên tin client .-> C
~~~

Sơ đồ mô tả logic; ở Authorization Code flow, resource owner tương tác với AS qua trình duyệt và client thường nhận **authorization code** trước khi đổi thành access token. Không nên hiểu sơ đồ là AS gửi raw access token trực tiếp tới browser trong mọi luồng.

## 4. Resource owner, authenticated user, client và resource owner của bản ghi

Tên gần nhau nhưng có thể khác hẳn:

| Khái niệm | Ví dụ | Điều cần phân biệt |
|---|---|---|
| **OAuth Resource Owner** | Người/tổ chức có thẩm quyền cho phép app truy cập dữ liệu | Vai trò trong mô hình ủy quyền OAuth. |
| **Authenticated user** | `user-742` vừa đăng nhập tại OP | Danh tính đã được xác thực; chưa đủ permission trên mọi resource. |
| **OAuth client** | `shop-web` | Ứng dụng yêu cầu token; có `client_id`. |
| **Token subject** | `sub=user-742` | Chủ thể token theo issuer/profile; không tự đồng nghĩa legal/data owner. |
| **Database record owner** | `order.owner_user_id=user-742` | Thuộc tính nghiệp vụ của bản ghi, có thể chỉ một mô hình authorization. |
| **Tenant owner/admin** | `tenant-admin-12` | Quản trị viên được ủy quyền của tổ chức, có phạm vi và điều kiện riêng. |
| **Delegated actor** | `support-agent-8` đang hỗ trợ theo ủy quyền | Có thể hành động thay principal dưới policy kiểm soát; không trở thành owner. |

Ví dụ một đơn hàng có:

~~~json
{
  "id": "order-42",
  "tenant_id": "tenant-beta",
  "created_by": "user-742",
  "assigned_to": "support-agent-8",
  "data_owner_org": "tenant-beta"
}
~~~

Ai được đọc/xóa đơn? **Không thể trả lời chỉ bằng một trường**. Tùy chính sách, người tạo có thể được đọc, support agent được xem nhưng không xóa, admin tổ chức được duyệt, và dữ liệu thuộc tổ chức. Resource Server phải áp dụng policy thực tế, không coi `created_by` hoặc `sub` là toàn bộ authorization.

## 5. Một luồng điển hình: Authorization Code + PKCE và OIDC

Giả sử `user-742` có quyền xem đơn của chính mình ở tenant Beta và muốn dùng `shop-web`. Client dùng Authorization Code + PKCE, đồng thời yêu cầu `openid` nếu cần OIDC login.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner / End User
    participant B as Browser
    participant C as OAuth/OIDC Client (shop-web)
    participant AS as Authorization Server / OP
    participant API as Orders Resource Server

    U->>B: Chọn đăng nhập và xem đơn
    B->>C: GET /login
    C-->>B: Chuyển đến AS kèm client_id, state, PKCE
    B->>AS: Authorization request
    AS->>U: Xác thực và hỏi consent khi cần
    U-->>AS: Hoàn tất authentication/authorization
    AS-->>B: Redirect kèm authorization code
    B->>C: Callback code + state
    C->>AS: Đổi code + code_verifier (+ client authentication nếu áp dụng)
    AS-->>C: Access token (+ ID/refresh token nếu cấp)
    C->>C: Xác minh ID token theo OIDC nếu nhận
    C->>API: GET /orders/42 + Bearer access token
    API->>API: Kiểm token: issuer, audience, expiry, scope
    API->>API: Kiểm tenant và quyền với order-42
    API-->>C: Cho phép hoặc từ chối
    C-->>B: Hiển thị kết quả an toàn
~~~

**Vai trò resource owner ở đâu?** Người dùng tương tác với AS để xác thực và thực hiện bước cho phép truy cập nếu giao thức/chính sách yêu cầu. Client **không nên thu thập mật khẩu resource owner** để “đổi lấy token” trong một ứng dụng hiện đại; cách làm đó phá tách biệt giữa client và hệ thống xác thực.

### 5.1. Authorization request minh họa

~~~http
GET /authorize?response_type=code&
    client_id=shop-web&
    redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
    scope=openid%20orders%3Aread&
    resource=https%3A%2F%2Fapi.example.com%2Forders&
    state=unguessable-state&
    code_challenge=derived-pkce-challenge&
    code_challenge_method=S256
Host: login.example.com
~~~

Request xuống dòng để dễ đọc; ứng dụng thực phải tạo URL, `state` và PKCE hợp lệ qua HTTPS. Tham số `resource` thuộc cơ chế **Resource Indicators for OAuth 2.0 (RFC 8707)** khi AS hỗ trợ; AS không nhất thiết dùng nguyên chuỗi `resource` làm `aud`.

### 5.2. Resource owner không quyết định token bằng cách sửa request

Người dùng có thể đồng ý cho `shop-web` đọc đơn, nhưng nếu client gửi thêm `payments:refund` hoặc `resource=payments-api` mà client/grant/principal không có quyền, **AS không được cấp quyền đó**.

Tại AS, các điều kiện cấp token có thể gồm:

1. Client đã đăng ký và grant được phép.
2. Resource được yêu cầu là tài nguyên hợp lệ client có thể xin.
3. Resource owner/principal đã được xác thực hoặc đại diện hợp lệ theo luồng.
4. Có consent/ủy quyền cần thiết, **không vượt quyền chủ thể**.
5. Scope được cấp nằm trong các giới hạn của client, resource, grant và policy.
6. Audience, thời hạn, token purpose và các claim do AS quyết định.

Resource owner có thể từ chối ủy quyền; AS phải xử lý theo giao thức. **Sự đồng ý không vô hiệu hóa security policy.**

### 5.3. PKCE không thay consent hoặc permission

PKCE giúp ràng buộc việc đổi authorization code với bên đã khởi tạo flow và giảm nguy cơ code interception. Nó **không cấp quyền** cho người dùng, không xác minh ownership của đơn hàng và không làm bearer token chống replay sau phát hành.

Tương tự, `state`/OIDC `nonce` giúp bảo vệ luồng đăng nhập theo những mục đích khác nhau; chúng không phải scope hay resource-level permission.

## 6. Authentication, authorization và consent không giống nhau

### 6.1. Authentication: ai đang đăng nhập?

OP/AS xác minh danh tính resource owner hoặc người dùng theo phương thức áp dụng: mật khẩu, passkey, MFA, SSO hay phương thức khác. Kết quả xác thực tạo ngữ cảnh như `sub`, `auth_time` hoặc mức assurance.

**Đăng nhập thành công chỉ trả lời ai đang được xác thực**, không chứng minh người đó được xem mọi bản ghi hoặc trao mọi scope cho app.

### 6.2. Authorization: quyền nào được phép?

Authorization liên quan đến việc client có được cấp quyền truy cập và sau đó request cụ thể có được chấp nhận. Có ít nhất hai tầng:

- **AS issuance policy:** quyền nào được đưa vào access token cho một client, principal, resource và grant?
- **RS access policy:** principal/client/tenant có được thực hiện operation trên bản ghi này ngay bây giờ không?

Hai tầng dùng dữ liệu khác nhau. AS có thể biết user thuộc tổ chức và đã đồng ý scope đọc, nhưng RS mới biết đơn hàng `order-42` có bị khóa, thuộc tenant nào và đang do ai xử lý.

### 6.3. Consent: người dùng đồng ý cho client làm gì?

**Consent** là sự đồng ý/phê duyệt trong một ngữ cảnh do hệ thống định nghĩa. OAuth authorization có thể gồm màn hình consent, nhưng **không bắt buộc mỗi lần cấp token đều hiển thị consent UI**: các mô hình first-party, consent đã lưu, policy doanh nghiệp hoặc grant máy–máy có thể xử lý khác.

Consent có thể đáp ứng một điều kiện authorization, nhưng **không tự vượt**:

- Giới hạn client registration và grant.
- Quyền trên resource/tenant của người dùng.
- Chính sách tổ chức, điều kiện bảo mật và yêu cầu pháp lý liên quan.
- Audience và scope được AS chấp nhận.
- Điều kiện resource-level authorization tại API.

**Không coi `consent=true` là claim cho phép mọi API và mọi data.**

### 6.4. Ví dụ user đồng ý nhưng vẫn bị từ chối

Giả sử `user-742` đồng ý `orders:read` cho `shop-web`. Token có `scope=orders:read` và `aud=orders-api`. API vẫn từ chối `GET /orders/99` vì đơn hàng đó thuộc `tenant-anpha`, còn user chỉ là thành viên `tenant-beta`. Đây là hành vi **đúng**, không phải OAuth “bị lỗi”.

## 7. Scope, audience và resource owner

**Scope** mô tả phạm vi quyền mà AS cấp cho access token; **audience** mô tả bên nhận token; **resource owner** là chủ thể có thẩm quyền trong mô hình truy cập.

Ví dụ:

~~~text
Resource owner / principal: user-742
OAuth client:                shop-web
Issuer:                      https://login.example.com
Requested scope:             orders:read orders:delete
Granted scope:               orders:read
Access token audience:       orders-api
Target record:               order-42 (tenant-beta)
~~~

Có ba ranh giới riêng:

1. `orders:delete` không được cấp nếu vượt policy/authorization.
2. `orders-api` nhận token nhưng `payments-api` không được chấp nhận nó.
3. `orders:read` không mặc định cho phép đọc đơn của tenant khác.

### 7.1. Phạm vi yêu cầu và phạm vi được cấp

~~~text
requestedScopes = {orders:read, orders:delete}
clientAllowed   = {orders:read, orders:create}
grantAuthorized = {orders:read}
policyAllowed   = {orders:read}

possibleGranted = requested ∩ clientAllowed
                  ∩ grantAuthorized ∩ policyAllowed
                = {orders:read}
~~~

Phép giao là **mô hình dễ hiểu**, không phải thuật toán duy nhất của mọi AS. Tùy policy, AS có thể **từ chối `invalid_scope`** thay vì âm thầm giảm scope. Nếu scope thực tế khác phạm vi yêu cầu, token response phải phản ánh scope được cấp theo yêu cầu của OAuth.

**Không cấp scope bằng phép hợp quyền giữa client và resource owner.** Việc client được phép một scope và user có quyền một scope khác không tự tạo quyền tổng hợp để làm cả hai việc.

### 7.2. Audience phải hướng đến RS được phép

Một token có `scope=orders:read` nhưng `aud=payments-api` **không được** gửi để đọc Orders API. Kể cả AS cấp token hợp lệ theo mật mã, Resource Server phải từ chối sai audience.

Nếu client dùng `resource` của RFC 8707, đó là **giá trị client yêu cầu**, còn `aud` thực tế là kết quả đánh giá chính sách của AS. Client không tự quyết token được dùng tại API nào.

### 7.3. Token đa audience cần cân nhắc ranh giới

Nếu JWT có:

~~~json
{
  "aud": ["orders-api", "payments-api"],
  "scope": "orders:read payments:read"
}
~~~

token có thể dành cho nhiều API, làm tăng khả năng bearer token bị dùng sau khi lộ ở một nơi. Khi APIs có ranh giới tin cậy khác nhau, thường nên cấp **access token riêng theo audience với scope tối thiểu**, thay vì coi mọi resource của cùng tổ chức là một audience chung. AS và từng RS phải thống nhất profile/permission nếu thật sự cần đa audience.

## 8. Access token, ID token và refresh token từ góc nhìn resource owner

Một lần người dùng đăng nhập/ủy quyền có thể tạo nhiều dữ liệu/token khác mục đích:

| Thành phần | Ai nhận/kiểm? | Vai trò | Không được làm |
|---|---|---|---|
| **Authorization code** | OAuth client đổi tại AS | Chứng từ trung gian trong code flow, bị ràng buộc với client/redirect/PKCE | Gửi code như bearer token đến API. |
| **Access token** | Resource Server | Quyền đã cấp để truy cập API theo audience/scope và thời hạn | Dùng tại RS khác hoặc coi là quyền mọi bản ghi. |
| **Refresh token** | Authorization Server | Xin access token mới trong giới hạn grant/client/policy | Gửi refresh token cho RS hoặc để lộ qua logs/browser storage trong BFF. |
| **OIDC ID token** | OIDC Client | Thông tin đã xác thực về user theo OIDC | Dùng làm access token gọi API. |
| **Session cookie của BFF** | Browser ↔ BFF | Tra session đăng nhập phía server | Đưa session ID làm OAuth access token của RS. |

### 8.1. JWT access token minh họa

Ví dụ payload của **JWT access token** (không phải JWT đã ký có thể dùng):

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893453000,
  "jti": "access-942c"
}
~~~

Diễn giải:

- `iss` là AS phát token.
- `sub` biểu diễn subject theo hợp đồng token; trong ví dụ là user.
- `aud` là Resource Server được cấp.
- `client_id` là OAuth client liên quan đến việc xin token; không phải resource owner.
- `scope` là quyền được cấp ở mức token.
- `exp`/`nbf` giới hạn hiệu lực theo thời gian; `jti` có thể định danh token.

**Không có trường nào tự chứng minh `user-742` là owner của mọi order.** API phải kiểm database/policy. JWT được ký (JWS) thường **không tự được mã hóa**; đừng đặt bí mật hoặc thông tin nhạy cảm không cần thiết trong claims.

### 8.2. OIDC ID token minh họa

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "shop-web",
  "auth_time": 1893452350,
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

`aud=shop-web` vì ID token **dành cho OIDC Client**. Resource Server `orders-api` không được chấp nhận ID token này như access token. OIDC Client xác minh `iss`, `aud`, chữ ký/thuật toán, expiry và các điều kiện của flow như nonce khi áp dụng.

**`sub` là định danh subject**, không phải email có thể đổi, tên hiển thị hay bằng chứng ownership của đơn hàng. Nhiều OIDC Provider dùng pairwise subject identifiers tùy client/sector; không nối dữ liệu giữa các issuer bằng chuỗi `sub` đơn lẻ. Khi cần khóa định danh trong một nguồn tin cậy, thường xét cặp **`(iss, sub)`** theo policy.

### 8.3. Opaque access token minh họa

Nếu AS cấp chuỗi tham chiếu opaque, RS không tự decode claims. RS có thể dùng **OAuth Token Introspection (RFC 7662)**:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "exp": 1893453000
}
~~~

Phản hồi chỉ minh họa; các trường ngoài `active` tùy AS và thỏa thuận của RS. **`active=true` chưa đủ** nếu audience/scope/permission không phù hợp. RS phải tin đúng endpoint introspection, bảo vệ TLS/xác thực RS theo chính sách và xử lý cache/revocation.

**Resource owner có thể là chủ thể được ủy quyền, nhưng không vì vậy mà mọi access token phải chứa tên, email hoặc identity claim đầy đủ của họ.** Giảm claims giúp bảo vệ quyền riêng tư và hạn chế rò dữ liệu khi token bị sao chép.

## 9. Quy trình Authorization Server quyết định quyền của resource owner

AS không chỉ cần biết “người dùng đã login chưa”. Một quyết định cấp token có thể kiểm:

| Nguồn dữ liệu | Ví dụ | Câu hỏi |
|---|---|---|
| Client registration | `shop-web` được authorization code + PKCE, resource `orders-api` | Client này có được xin resource/grant không? |
| Grant/request | `scope=orders:read`, `resource=orders-api` | Đang yêu cầu gì? |
| Authentication context | `sub=user-742`, `auth_time`, assurance | Người dùng đã được xác thực phù hợp chưa? |
| Authorization/consent record | Được phép dùng `orders:read` cho client hiện tại | Có grant phù hợp không? |
| Organization/tenant policy | User thuộc Beta, không thuộc Anpha | Có đủ thẩm quyền theo tổ chức/resource không? |
| Resource policy | Orders API chấp nhận scope đọc đơn | Scope có nghĩa đối với resource này không? |
| Risk/security state | Account bị khóa, client bị thu hồi | Có phải từ chối/step-up/giảm TTL không? |
| Token policy | TTL, issuer, profile, audience, signing key | Phát token loại gì và hạn đến đâu? |

Pseudocode:

~~~text
function approveAccessToken(client, grant, request):
    assert client is registered, active and valid for grant
    assert grant identity/authentication is trustworthy

    resource = resolveRegisteredResource(request.resource)
    if resource not allowed for client or grant:
        reject

    principal = grant.trustedPrincipal
    requested = parseRequestedScopes(request.scope)

    allowed = policy.scopesFor(client, resource, principal, grant)
    if requested exceeds allowed:
        reject or narrow according to protocol and policy

    approved = chooseGrantedScopes(requested, allowed)
    if no valid authorization/consent when required:
        reject or request required interaction

    return issueAccessToken(
        issuer = configuredIssuer,
        subject = principal,
        audience = resource.canonicalAudience,
        scopes = approved,
        expires = policy.maxPermittedExpiry
    )
~~~

Đây là **pseudocode**; không mô tả mọi mã lỗi và bước tương tác OAuth. Trong client credentials, `principal`/grant không nhất thiết là end user, nên phải áp dụng **service policy** thay cho user consent.

**Không lấy `request.userId` hoặc `request.tenantId` làm chủ thể/tenant đã được xác minh** chỉ vì client gửi tham số. Những giá trị đó cần được ràng buộc với grant, phiên xác thực và policy đáng tin.

## 10. Resource Server: kiểm quyền tài nguyên chứ không chỉ kiểm scope

Resource owner thường được thảo luận trong lúc AS nhận ủy quyền, nhưng **RS mới là nơi bảo vệ bản ghi cụ thể**. Với một access token `scope=orders:read`, Orders API phải kiểm:

1. Token đúng định dạng/purpose/profile mà API chấp nhận.
2. Issuer đáng tin và chữ ký/khóa đúng, hoặc introspection hợp lệ.
3. `aud` chứa audience của Orders API; không chấp nhận ID token hoặc token API khác.
4. `exp`, `nbf` và trạng thái cần thiết còn hợp lệ.
5. Scope/permission đủ cho endpoint.
6. Chủ thể/client/tenant có quyền trên đơn được yêu cầu theo policy hiện hành.

### 10.1. Ví dụ truy vấn chống BOLA/IDOR

**Không an toàn:**

~~~sql
SELECT *
FROM orders
WHERE id = :orderId;
~~~

Nếu controller chỉ kiểm “user đã đăng nhập” và token có `orders:read`, một user có thể thay `orderId` để xem đơn của người khác.

**An toàn hơn trong mô hình tenant + ownership:**

~~~sql
SELECT o.id, o.total, o.status
FROM orders o
WHERE o.id = :orderId
  AND o.tenant_id = :trustedTenantId
  AND (
      o.owner_user_id = :trustedPrincipalId
      OR EXISTS (
          SELECT 1
          FROM order_acl a
          WHERE a.order_id = o.id
            AND a.principal_id = :trustedPrincipalId
            AND a.permission = 'READ'
      )
  );
~~~

Đây là **policy minh họa**, không đầy đủ mọi mô hình quyền. `trustedPrincipalId` và `trustedTenantId` phải đến từ context đã xác minh và kiểm membership, không lấy nguyên body/header request chưa tin. Các điều kiện admin/tenant role, trạng thái đơn và dữ liệu chia sẻ có thể yêu cầu policy khác hoặc RLS.

**Quan trọng:** người dùng **không phải record owner** vẫn có thể được đọc nếu có quyền chia sẻ hợp lệ. Không biến kiểm ownership thành quy tắc cứng cho mọi ứng dụng, nhưng cũng không bỏ kiểm resource-level authorization.

### 10.2. Ví dụ Java/Spring Security Resource Server

Đoạn service-level minh họa cách tách token validation với quyền của bản ghi. Giả định Spring Security đã cấu hình JWT decoder kiểm issuer, audience, thuật toán, hạn và loại access token.

~~~java
import java.util.Arrays;
import org.springframework.security.oauth2.jwt.Jwt;

public final class OrderAccessPolicy {

    private final MembershipRepository memberships;
    private final OrderRepository orders;
    private final OrderAclRepository acl;

    public OrderAccessPolicy(
            MembershipRepository memberships,
            OrderRepository orders,
            OrderAclRepository acl) {
        this.memberships = memberships;
        this.orders = orders;
        this.acl = acl;
    }

    public boolean mayReadOrder(
            Jwt verifiedAccessJwt,
            String targetTenantId,
            String orderId) {

        String subject = verifiedAccessJwt.getSubject();

        // Thiếu claims cần thiết => từ chối.
        if (subject == null || targetTenantId == null) {
            return false;
        }

        // Scope chỉ là một điều kiện của authorization.
        String scope = verifiedAccessJwt.getClaimAsString("scope");
        if (scope == null ||
                !Arrays.asList(scope.split(" ")).contains("orders:read")) {
            return false;
        }

        if (!memberships.isActiveMember(subject, targetTenantId)) {
            return false;
        }

        return orders.findByIdAndTenantId(orderId, targetTenantId)
                .map(order ->
                    order.ownerUserId().equals(subject) ||
                    acl.mayRead(subject, order.id())
                )
                .orElse(false);
    }
}
~~~

Các interface repository và record `Order` chưa được cung cấp; code minh họa **định hướng**, không phải file biên dịch độc lập. Production cần chuẩn hóa scope/authority theo profile, xử lý claims null, phân biệt service principal và end user, tối ưu truy vấn, transaction/race policy, tenant isolation và audit.

Nếu dùng `@PreAuthorize("hasAuthority('SCOPE_orders:read')")`, biểu thức đó giúp kiểm scope đã ánh xạ nhưng **không tự kiểm owner, tenant hay bản ghi**. Đưa object-level policy vào service/authorization layer và áp dụng nhất quán cho read, update, delete, list, export, download, batch và async jobs.

## 11. Khi resource owner là tổ chức hoặc chủ thể được ủy quyền

Trong SaaS doanh nghiệp, một tổ chức có thể quản lý dữ liệu, trong khi chỉ một số nhân viên được phép đồng ý cho ứng dụng thứ ba truy cập. Người đang thao tác consent screen **không nhất thiết là chủ sở hữu từng bản ghi**.

Ví dụ:

~~~text
Organization: tenant-beta
Owner/policy authority: tenant-beta
Administrator: admin-12
Analyst: analyst-7
Third-party client: reporting-tool
Protected API: invoices-api
Requested scope: invoices:read
~~~

Một chính sách có thể cho phép `admin-12` phê duyệt client `reporting-tool` đọc hóa đơn trong tenant Beta, còn `analyst-7` chỉ được sử dụng ứng dụng nhưng **không thể phê duyệt quyền truy cập toàn tổ chức**.

Hệ thống cần phân biệt:

1. **Organizational authority:** tổ chức có quyền kiểm soát dữ liệu và policy cho tenant.
2. **Delegated administrator:** người được ủy quyền để duyệt/grant access theo phạm vi cụ thể.
3. **End user:** người đăng nhập và thực hiện công việc hằng ngày.
4. **OAuth client:** ứng dụng được phê duyệt để truy cập resource theo quyền đã cấp.
5. **Resource Server:** API còn phải kiểm tenant, role, scope và record-level permissions khi nhận request.

### 11.1. User consent không luôn thay admin consent

Người dùng cá nhân có thể cho phép client đọc **dữ liệu cá nhân trong quyền của họ**. Nhưng yêu cầu như “đọc mọi hóa đơn của tổ chức” có thể cần **admin consent** hoặc enterprise policy. Nếu user không có thẩm quyền, AS không được mặc định nâng cấp quyền chỉ vì consent screen có nút “Đồng ý”.

Ngược lại, admin consent không có nghĩa mọi end user được cấp quyền quản trị. Client được tổ chức cho phép tích hợp vẫn có thể cần access token theo subject/grant và RS áp dụng quyền cụ thể.

### 11.2. Tenant boundary không phải audience boundary

~~~text
Issuer: https://login.example.com
Audience: invoices-api
Tenant: tenant-beta
Subject: analyst-7
Scope: invoices:read
~~~

`aud=invoices-api` chỉ nói token hướng đến Billing/Invoices API, **không nói token dành cho mọi tenant**. Nếu người dùng đổi đường dẫn `/tenants/beta` thành `/tenants/anpha`, Resource Server phải kiểm membership và permission tại tenant Anpha hoặc từ chối.

Nếu issuer phục vụ nhiều tenant, hai user có cùng email hoặc client_id không chắc thuộc cùng authority. Khi kiểm danh tính, phải ràng buộc issuer, subject, tenant và mô hình quyền đúng thiết kế.

### 11.3. Phê duyệt quyền trên phạm vi hẹp

Một cách giảm rủi ro:

~~~text
Consent / grant:
  client = reporting-tool
  tenant = tenant-beta
  resource = invoices-api
  scope = invoices:read
  allowed invoice category = monthly_summary
  valid until = policy-defined date
~~~

Scope có thể mô tả quyền chung, còn các ràng buộc chi tiết như loại hóa đơn phải được AS/RS biết qua **policy hoặc claims theo hợp đồng**. Không nhất thiết đưa mọi điều kiện vào JWT; với quyền thay đổi thường xuyên, RS có thể truy vấn policy hiện hành.

## 12. Client Credentials: không có end user trực tiếp

Resource owner thường được giảng bằng ví dụ người dùng nhấn “Allow”. Nhưng OAuth 2.0 còn có **Client Credentials Grant** cho client hành động trong phạm vi quyền của chính nó.

Ví dụ `reporting-worker` tự động lấy dữ liệu tổng hợp:

~~~http
POST /token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <illustrative-client-credentials>

grant_type=client_credentials&
scope=reports%3Aread&
resource=https%3A%2F%2Fapi.example.com%2Freports
~~~

AS xác thực confidential client, kiểm grant/resource/scope và cấp token theo **service policy**.

~~~json
{
  "iss": "https://login.example.com",
  "sub": "reporting-worker",
  "client_id": "reporting-worker",
  "aud": "reports-api",
  "scope": "reports:read",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

Ví dụ trên theo ngữ cảnh token profile minh họa. Trong JWT Profile for OAuth 2.0 Access Tokens, `sub` của client credentials có cách biểu diễn theo profile; hệ thống phải xác định principal là **client/service**, không tự xem nó là end user.

**Không có end-user resource owner trực tiếp tương tác trong yêu cầu client credentials này.** Tài nguyên vẫn thuộc tổ chức/chủ thể có thẩm quyền theo mô hình quản lý và tổ chức đã cấu hình authorization policy cho client. Không được giả vờ rằng service này vừa nhận “user consent” hoặc được phép giả danh một người dùng.

### 12.1. “Client là resource owner” có đúng không?

Trong một số tình huống, client có quyền trên tài nguyên do chính nó kiểm soát; tài liệu OAuth 2.0 mô tả client credentials dùng khi client hành động **thay mặt chính nó** hoặc cho tài nguyên đã được sắp xếp cấp quyền trước với AS. Tuy nhiên, **đừng mặc định mọi client credentials token đại diện cho một người hoặc owner cụ thể**.

Đối với API, cần có phân biệt rõ:

~~~text
principal.type = USER
principal.id   = user-742

versus

principal.type = SERVICE
principal.id   = reporting-worker
~~~

Một Service Token không thể tự gọi endpoint “Đổi mật khẩu cho user-742” chỉ vì `sub` có giá trị phù hợp hoặc client ID nằm trong mạng nội bộ. API phải dùng service-specific permission và policy.

### 12.2. Không dùng Resource Owner Password Credentials

**Resource Owner Password Credentials (ROPC)** là grant lịch sử cho phép client nhận trực tiếp username/password của resource owner. Nó làm tăng rủi ro lộ mật khẩu, chống lại phân tách vai trò client/AS và không tương thích tốt với MFA, federation, passkey.

**OAuth 2.0 Security Best Current Practice (RFC 9700) yêu cầu không sử dụng ROPC grant.** Với ứng dụng hiện đại, ưu tiên Authorization Code + PKCE và luồng xác thực qua AS/OP; cho máy–máy, dùng client credentials hoặc cơ chế phù hợp khi được AS cho phép.

Không xây màn hình đăng nhập của client để thu password của resource owner rồi gửi thẳng đến token endpoint chỉ vì “OAuth có password grant”.

## 13. Delegation, token exchange và actor khác với resource owner

Hệ thống nhiều microservice có thể cần một service gọi service khác **thay mặt người dùng**. Đây là delegation; nó không biến service trung gian thành chủ sở hữu tài nguyên.

Ví dụ:

~~~text
User:           user-742
Frontend:       shop-web
Orders service: orders-api
Billing service: billing-api

Token 1:
  subject = user-742
  audience = orders-api
  scope = orders:read

Orders service needs to call Billing API:
  cannot simply forward Token 1 to billing-api.
~~~

Nếu AS hỗ trợ **OAuth 2.0 Token Exchange (RFC 8693)**, client/service có thể xin token mới hướng tới Billing API, với subject/actor/permission theo grant và chính sách được phê duyệt.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Shop Client
    participant O as Orders Service
    participant AS as Authorization Server
    participant B as Billing Service

    C->>O: Access token aud=orders-api
    O->>O: Kiểm token và quyền user
    O->>AS: Token exchange, yêu cầu billing-api
    AS->>AS: Kiểm subject token, actor/client, delegation và scope
    AS-->>O: Access token aud=billing-api nếu được phép
    O->>B: Gọi với token billing-api
    B->>B: Kiểm iss, aud, scope và quyền tài nguyên
    B-->>O: Kết quả hoặc từ chối
~~~

Một delegated token có thể chứa claim `act` theo profile token exchange để mô tả actor. **`act` không đồng nghĩa với `sub`, `client_id` hoặc `azp`**. Những trường này chỉ các vai trò khác nhau; RS phải xác minh chuỗi ủy quyền/actor đúng chính sách.

**Token exchange không tự cấp quyền rộng hơn**: AS phải kiểm resource đích, scope, quyền của actor và principal. Nếu không đủ quyền, từ chối exchange. Không tắt audience validation ở Billing để “tái sử dụng” access token Orders.

## 14. Người dùng rút consent hoặc bị thu hồi quyền

Một grant được cấp hôm qua không chắc còn hợp lệ hôm nay. Resource owner hoặc người quản trị có thể rút quyền; user có thể bị khóa, xóa membership tenant, giảm role hoặc thu hồi phiên.

### 14.1. Những trạng thái cần phân biệt

| Sự kiện | Tác động mong muốn | Không được mặc định |
|---|---|---|
| User **rút consent** cho client | Ngăn hoặc giới hạn việc cấp token mới, có thể revoke grant/token theo policy | Mọi JWT access token đã cấp biến mất ngay ở RS không kiểm trạng thái. |
| User **logout khỏi browser/BFF** | Hủy session ứng dụng phía server; xóa cookie | OP session và mọi access/refresh token cùng hết hiệu lực tức thì. |
| AS **revoke refresh token** | Không tiếp tục dùng refresh grant để lấy access token mới | Access JWT cũ ở RS tự trở thành invalid ngay. |
| RS/AS **revoke access token** | Từ chối token theo cơ chế revocation/state của hệ thống | Cache introspection và validator cục bộ không có độ trễ. |
| User **mất quyền tenant** | Ngăn truy cập dữ liệu tenant theo policy hiện hành | JWT có role/tenant claim cũ sẽ tự cập nhật. |
| Admin **vô hiệu client** | Không cấp grant/token mới và xử lý token hiện có theo policy | Chỉ thay cấu hình client là đủ vô hiệu mọi token cũ. |

### 14.2. JWT, opaque token và quyền thay đổi

- **JWT access token tự chứa:** RS có thể xác minh offline. Một role/scope cũ vẫn có thể được tin đến `exp` nếu không có denylist, token version hoặc state check.
- **Opaque access token:** RS có thể introspect để hỏi `active` và metadata hiện tại. Khả năng phát hiện revoke nhanh hơn tùy AS, nhưng cache làm trễ.
- **Refresh token:** thường sống dài hơn, nên bảo vệ nghiêm ngặt, rotation/reuse detection và ràng buộc grant/client theo policy.

**Không coi `exp` còn hạn là bằng chứng quyền hiện tại vẫn phù hợp** với hành động rủi ro cao. API có thể cần kiểm membership/permission mới tại thời điểm request.

### 14.3. Khi resource owner “xóa quyền truy cập ứng dụng”

Ứng dụng nên có đường để user/admin xem và rút quyền client đã cấp, theo tính năng của AS/IdP. Quy trình có thể gồm:

1. Đánh dấu grant/consent không còn active.
2. Ngăn cấp token mới qua grant đó.
3. Revoke refresh token liên quan.
4. Revoke/giới hạn access token hiện có theo khả năng AS/RS.
5. Invalidate browser session tại BFF khi policy yêu cầu.
6. Cập nhật authorization cache và audit metadata.

**Không log access/refresh token thô** trong audit; ghi mã grant/client/issuer, thời điểm, người thực hiện và kết quả theo chính sách quyền riêng tư.

## 15. Rủi ro bảo mật liên quan Resource Owner

| Sai lầm / kiểu tấn công | Ví dụ | Biện pháp |
|---|---|---|
| **Nhầm authentication với authorization** | User đăng nhập thành công được xem mọi đơn | Kiểm scope, tenant và object-level policy tại RS. |
| **BOLA/IDOR** | Sửa `/orders/42` thành `/orders/99` để xem bản ghi khác | Truy vấn theo tenant/principal/ACL hoặc policy tương đương. |
| **Client mạo danh resource owner** | Client tự gửi `userId=admin` rồi AS ký `sub=admin` | Subject phải đến từ grant/authentication đã tin. |
| **Consent phishing** | Client/màn hình giả yêu cầu quyền rộng hoặc đánh lừa user | Đăng ký redirect URI, hiển thị client/scope rõ ràng, phishing-resistant login và risk checks. |
| **Scope escalation** | Client xin `payments:refund` ngoài quyền | AS kiểm client/grant/resource/policy; scope tối thiểu. |
| **Sai audience** | Token `aud=orders-api` được dùng tại `payments-api` | RS kiểm audience và token purpose chính xác. |
| **Dùng ID token thay access token** | ID token `aud=shop-web` gửi vào API | Tách validator ID token/Access token. |
| **Nhầm service principal là user** | Client credentials token được áp role user | Phân biệt grant/principal type, service permissions. |
| **Nhầm tenant** | User admin tenant A dùng quyền đó ở tenant B | Membership/role theo target tenant, policy riêng. |
| **Token bị đánh cắp/replay** | Access bearer token lộ qua log rồi bị trình lại | Lưu/truyền an toàn, TTL ngắn, DPoP/mTLS khi cần, revocation. |
| **Refresh token reuse** | Hai bên dùng refresh token đã rotate | Rotation, reuse detection, quản lý concurrency ở client/BFF. |
| **Session fixation/CSRF** | Attacker ép session đã biết hoặc gửi request cookie-auth | Rotate session ID, CSRF protection, SameSite và Origin checks. |
| **Claims chưa xác minh** | Backend tự Base64URL-decode JWT rồi tin `sub` | Xác minh chữ ký/issuer/aud/exp và profile trước dùng. |
| **User rút quyền nhưng cache cũ** | ACL/tenant đã đổi, API vẫn cho phép | Invalidate cache, state check theo mức rủi ro. |

### 15.1. Vì sao bearer token không chứng minh “resource owner đang hiện diện”?

Nếu attacker lấy access token còn hạn của `user-742`, attacker có thể gửi token tới đúng Resource Server. Token vẫn chứa `sub=user-742`, `aud=orders-api` và chữ ký hợp lệ. **Nó không chứng minh người dùng thật vừa thao tác request hiện tại**.

MFA trong lúc login không tự bảo vệ token đã bị lấy sau đó. Các lớp phòng vệ:

- HTTPS và bảo vệ token khỏi logs, URL, analytics, browser storage không phù hợp.
- TTL access token ngắn, scope/audience hẹp và quyền resource-level.
- Refresh token rotation, bảo vệ client và phát hiện reuse.
- DPoP hoặc mTLS sender-constrained access token khi threat model yêu cầu; RS phải kiểm proof/binding.
- Reauthentication/step-up trước giao dịch nhạy cảm nếu session assurance không đủ.
- Revoke/denylist/introspection và giám sát rủi ro khi compromise.

### 15.2. Kiến trúc BFF và session cookie

Trong web app dùng **Backend-for-Frontend**, backend là OAuth Client, giữ access/refresh token trong server-side token store; browser chỉ mang cookie `HttpOnly` trỏ đến phiên. Điều này hạn chế JavaScript sao chép OAuth token, nhưng cookie session vẫn là bearer secret có thể bị đánh cắp.

Cần `Secure`/`HttpOnly`/`SameSite` phù hợp, session fixation protection, idle/absolute expiry, logout invalidation và CSRF/XSS defense. BFF phải kiểm phiên trước khi gọi API; RS vẫn xác minh access token và quyền bản ghi.

### 15.3. Quyền riêng tư và dữ liệu của resource owner

Token hoặc audit logs có thể chứa subject, tenant, scopes và thông tin nhạy cảm. Chỉ phát hành claim cần thiết cho audience; tránh đặt email, số điện thoại, danh sách quyền rộng hoặc dữ liệu nghiệp vụ cá nhân vào JWT nếu không cần.

Không lưu raw Authorization header, ID token hoặc refresh token trong exception/trace. Một access token dù hết hạn vẫn có thể bộc lộ dữ liệu; nên redact ngay tại nguồn.

## 16. Bảng quyết định cho tình huống thực tế

Giả định `orders-api` chỉ nhận access token do `https://login.example.com` cấp, `aud=orders-api`, endpoint đọc yêu cầu `orders:read`.

| Tình huống | Kết luận | Vì sao |
|---|---|---|
| `user-742` đăng nhập và xem đơn của chính mình tại tenant Beta, token đúng scope/aud | Có thể cho phép sau các kiểm tra đầy đủ | Authentication, token validation và object-level policy đều phải đạt. |
| `user-742` đăng nhập và xem đơn `user-999` không được chia sẻ | Từ chối | Đăng nhập/scope không trao quyền sở hữu bản ghi khác. |
| User được chia sẻ quyền đọc đơn của đồng nghiệp qua ACL hợp lệ | Có thể cho phép theo ACL/policy | Không phải owner vẫn có thể có permission được ủy quyền. |
| User admin tenant Anpha xem đơn ở Beta không có membership | Từ chối | Quyền tenant Anpha không tự áp cho Beta. |
| `shop-web` xin `payments:refund` dù resource owner chỉ có quyền đọc đơn | AS không cấp quyền vượt phép | Client request/consent không vượt policy. |
| ID token đúng `aud=shop-web` được gửi làm bearer cho `orders-api` | RS từ chối | ID token dành cho OIDC Client, sai mục đích/audience. |
| JWT access token đúng chữ ký, `aud=payments-api` | RS từ chối | Sai audience. |
| Access token bị lộ, `sub=user-742` không đổi | Có nguy cơ replay nếu bearer còn hiệu lực | Token không chứng minh người gửi hiện tại là user. |
| Client credentials token của `reporting-worker` gọi endpoint chỉ cho user | Từ chối nếu service không có quyền | Không tự chuyển service principal thành end user. |
| Client credentials token đúng resource và service permission | Có thể cho phép | Không nhất thiết cần end user tương tác. |
| Người dùng rút consent, JWT cũ còn hạn | Tùy thiết kế revocation/state; không tự invalid | Cần TTL, RS state check hoặc denylist theo policy. |
| Opaque token introspect `active=true` nhưng thiếu scope | RS từ chối | Active không bằng được phép endpoint. |
| Access token có `orders:read` nhưng subject đã bị gỡ khỏi tenant | RS từ chối theo policy hiện hành | Không tin role/tenant stale như quyền vĩnh viễn. |
| Request thiếu `sub` hoặc principal type cần thiết | Fail closed theo token profile/policy | Không đoán danh tính hay owner từ header client gửi. |

## 17. Bài thực hành

### Bài 1 — Xác định bốn vai trò

Hệ thống:

~~~text
Người dùng:       user-742
Ứng dụng:         shop-web
Nhà phát token:   login.example.com
API dữ liệu:      orders-api
Đơn hàng:         order-42
~~~

Trả lời:

1. **Resource owner là ai?** Nếu user có thẩm quyền cho phép client truy cập dữ liệu của mình, đó là `user-742`; nếu dữ liệu do tổ chức kiểm soát, cần xét authority của tổ chức và đại diện được ủy quyền.
2. **OAuth Client là ai?** `shop-web`.
3. **Authorization Server là ai?** `login.example.com`.
4. **Resource Server là ai?** `orders-api`.
5. **Tại sao scope đọc đơn chưa đủ?** Vì RS còn phải kiểm tenant, ACL, ownership và trạng thái `order-42`.

### Bài 2 — Nhìn vào claims

Cho token minh họa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "exp": 1893453000
}
~~~

Câu hỏi và đáp án gợi ý:

- `client_id` là resource owner? **Không**, đó là OAuth client ID.
- `sub` là legal owner của mọi order? **Không**, đó là token subject; quan hệ sở hữu cần policy/dữ liệu riêng.
- `aud` biểu thị ai? **Resource Server được nhận token**.
- `scope` có chứng minh quyền đọc order của tenant khác không? **Không**.
- Nếu token bị sửa `sub` nhưng chữ ký không hợp lệ thì sao? **RS phải từ chối**.
- Nếu token là JWT hợp lệ nhưng đã hết hạn thì sao? **RS từ chối** bất kể subject/owner.

### Bài 3 — Kiểm thử âm tính cho API và AS

Tạo test cases:

1. Client lạ tự khai `client_id=shop-web` nhưng không qua grant hợp lệ.
2. Authorization Code callback có `state` sai hoặc PKCE verifier không khớp.
3. User không được phép resource/tenant nhưng nhấn “Allow”.
4. Token có scope đúng nhưng audience của API khác.
5. ID token được dùng làm access token.
6. Access token đúng audience/scope nhưng `order.owner_user_id` là người khác và không có ACL.
7. User admin ở tenant A cố thao tác tenant B.
8. Client credentials token được gán role của end user không tồn tại.
9. Actor service cố token exchange đến API khác khi chưa được ủy quyền.
10. Access token đã bị revoke nhưng còn hạn JWT, kiểm theo chính sách trạng thái đã cam kết.
11. Browser cookie bị đánh cắp và phát lại; kiểm session expiry/revocation/CSRF.
12. Refresh token cũ bị dùng lại sau rotation.
13. Resource Server nhận `sub` từ header request thay vì token/context đã xác minh.
14. Token hợp lệ nhưng quyền người dùng đã bị thay đổi sau phát hành.

Với mỗi case, hãy nêu **bên phải chặn**: AS, OIDC Client, BFF hoặc RS. Không nên dồn mọi kiểm tra vào một bên.

### Bài 4 — Thiết kế authorization cho tài liệu tổ chức

Một workspace chứa tài liệu `doc-73` do tổ chức sở hữu, người tạo là `author-11`, người xem là `analyst-7`, admin là `admin-12`. Client `reporting-tool` yêu cầu `docs:read docs:export`.

Hãy xác định:

- Ai có quyền **duyệt client** theo tổ chức?
- Có cần consent của user, admin hay chính sách doanh nghiệp?
- Phạm vi `docs:export` có nhạy cảm hơn `docs:read` không?
- RS cần kiểm tenant, ACL và policy export thế nào?
- Khi admin rút quyền client, access/refresh token và cache phải xử lý ra sao?
- Logs/audit lưu thông tin gì mà không ghi token hay dữ liệu tài liệu?

**Gợi ý:** Resource owner trong mô hình này có thể là tổ chức; admin là người có thẩm quyền được ủy quyền; người tạo tài liệu không nhất thiết quyết định việc cấp quyền cho toàn workspace.

## 18. Checklist triển khai

- [ ] Đã định nghĩa resource owner là chủ thể **có thẩm quyền cho phép truy cập**, không mặc định luôn là người dùng cuối.
- [ ] Đã phân biệt đủ bốn vai trò OAuth: Resource Owner, Client, Authorization Server và Resource Server.
- [ ] Đã tách login/authentication, consent, token issuance và resource-level authorization.
- [ ] AS xác minh client registration, grant, principal/authority, resource, scope và policy trước khi phát token.
- [ ] Với OIDC, client xác minh ID token đúng issuer, audience, thời hạn và flow-specific checks; không gửi ID token cho API.
- [ ] Access token chỉ được dùng tại Resource Server đúng issuer, audience và token purpose/profile.
- [ ] RS kiểm scope **và** tenant/ownership/ACL/ABAC/RBAC theo từng resource và action.
- [ ] `sub` được diễn giải theo issuer/profile và principal type; không mặc định là email hoặc record owner.
- [ ] Client credentials được xử lý như service grant, không giả định luôn có end user/consent.
- [ ] Không dùng Resource Owner Password Credentials trong luồng mới; ưu tiên Authorization Code + PKCE theo BCP.
- [ ] Admin consent/organizational grants có thẩm quyền và ranh giới tenant rõ ràng.
- [ ] Token exchange/delegation được kiểm actor, subject, audience và scope theo policy; không forward sai audience.
- [ ] Có cơ chế rút consent, revoke grant/token, giảm scope và xử lý quyền thay đổi sau phát hành.
- [ ] Access/refresh token, session cookie và authorization code được bảo vệ khỏi log, browser leak, replay và storage compromise.
- [ ] Có TTL, refresh token rotation/reuse detection và sender-constrained token khi rủi ro yêu cầu.
- [ ] Có kiểm thử chống IDOR/BOLA, sai tenant, client impersonation, token substitution, stale claims và wrong grant.
- [ ] Không cấp quyền chỉ vì người dùng đã đăng nhập, token có chữ ký đúng hoặc consent screen đã được chấp nhận.
- [ ] Khi không đủ thông tin tin cậy về quyền, hệ thống **fail closed**.

**Ghi nhớ:** **Resource owner** trong OAuth 2.0 là thực thể có khả năng cho phép truy cập tài nguyên được bảo vệ. Client xin quyền; Authorization Server kiểm và phát token; Resource Server xác minh token **và** chính sách truy cập bản ghi. Resource owner có thể là end user, tổ chức hoặc được thể hiện qua người có thẩm quyền ủy quyền tùy mô hình, nhưng **không đồng nghĩa tự động với `sub`, `client_id` hay record owner**. Access token đúng audience và scope vẫn chưa đảm bảo có quyền với mọi tài nguyên, và bearer token bị đánh cắp vẫn có thể bị phát lại.

### Tài liệu chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** định nghĩa bốn vai trò, grant, client, Resource Owner và access/refresh token.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** gửi access token và các nguy cơ bearer replay.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ authorization code flow.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource/audience được yêu cầu trong OAuth.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access JWT claims và Resource Server validation.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, expiry và cấu trúc claim.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái và metadata access token opaque.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token/grant theo khả năng AS.
- **RFC 8693 — OAuth 2.0 Token Exchange:** delegated actor, subject và audience của token đổi.
- **RFC 8725 — JSON Web Token Best Current Practices:** kiểm issuer/audience và chống token confusion.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ authorization flow và không sử dụng ROPC.
- **OpenID Connect Core 1.0:** ID token, `sub`, `aud`, nonce và xác thực user.
- **OWASP API Security Top 10:** Broken Object Level Authorization (BOLA), Broken Function Level Authorization và API authorization.

