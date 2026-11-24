# Không dùng client credentials để đại diện user tùy ý

Một dịch vụ `reporting-worker` cần đọc báo cáo từ `orders-api`. Nó xác thực bằng OAuth 2.0 **Client Credentials Grant** và được Authorization Server cấp access token với `client_id=reporting-worker`, `scope=reports:read`. Một lập trình viên sau đó muốn dùng chính token ấy để phê duyệt hoàn tiền “thay người dùng”:

~~~http
POST /users/user-742/refunds/refund-81/approve HTTP/1.1
Host: orders.example.com
Authorization: Bearer <SERVICE_ACCESS_TOKEN>
X-User-Id: user-742
Content-Type: application/json

{"approvedBy":"user-742"}
~~~

Nếu Resource Server chỉ kiểm chữ ký token rồi tin `X-User-Id` hay `approvedBy` từ request, `reporting-worker` có thể **giả danh bất kỳ người dùng nào**. Không có bằng chứng user-742 vừa đăng nhập, ủy quyền hoặc thực hiện phê duyệt. Đây là lỗi **đồng nhất danh tính dịch vụ với danh tính người dùng**.

**Client Credentials Grant xác thực OAuth client và cấp quyền cho client theo chính sách; nó không tự tạo một phiên đăng nhập người dùng.** Một service có thể được tổ chức cấp quyền thực hiện công việc máy–máy, nhưng không được tự chọn `sub=user-admin` hoặc `act_as=user-742` rồi coi đó là quyền người dùng.

Bài thuộc chương **Client credentials** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là ranh giới danh tính khi cấp và sử dụng token OAuth 2.0/OIDC, ý nghĩa `sub`/`client_id`, JWT/opaque token, audience/scope/tenant, token exchange/ủy quyền, kiểm quyền tại Resource Server, lưu trữ, thu hồi và phòng chống token bị đánh cắp/phát lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Client Credentials Grant là **service-to-service authorization**, không phải chứng minh end user đã xác thực.
2. Phân biệt **Resource Owner**, OAuth Client, Authorization Server, Resource Server, **service principal**, **user principal** và **actor** trong delegation.
3. Phân tích `client_id`, `sub`, `iss`, `aud`, `scope`, `act` và các claims tùy biến mà không đồng nhất application với user.
4. Phát hiện lỗ hổng giả danh qua `X-User-Id`, `user_id` trong body/query, token request `sub` tự khai và role/tenant mapping sai.
5. Thiết kế service authorization với **scope, audience, tenant, resource, operation** và object-level policy.
6. Chọn flow phù hợp khi thật sự cần quyền người dùng: **Authorization Code + PKCE/OIDC** hoặc delegation/token exchange đã được AS chấp thuận.
7. Xây dựng policy, ví dụ Java/Spring Security, audit actor và negative tests chống giả danh/BOLA/IDOR.
8. Quản lý bảo mật access token, client secret/private key, revoke và sự cố credential exposure.

## 2. Định nghĩa Client Credentials Grant và ranh giới

Theo **RFC 6749 `4.4**, Client Credentials Grant dành cho **confidential client** dùng danh tính của mình để yêu cầu access token. Nó áp dụng khi client hành động **thay mặt chính nó** hoặc đối với tài nguyên mà authorization đã được **sắp xếp trước** với Authorization Server và resource owner/chủ thể có thẩm quyền.

Điều đó **không có nghĩa**:

> Một service biết client secret thì được tự chọn user ID bất kỳ để có quyền của người đó.

### 2.1. Luồng máy–máy

~~~mermaid
sequenceDiagram
    autonumber
    participant S as Reporting Worker / OAuth Client
    participant AS as Authorization Server
    participant RS as Reports Resource Server
    participant DB as Report Data
    S->>AS: POST /token, grant_type=client_credentials, client auth
    AS->>AS: Kiểm client, grant, resource, scope, service policy
    AS-->>S: Access token aud=reports-api, scope=reports:read
    S->>RS: GET /reports/summary, Bearer access token
    RS->>RS: Kiểm token và service permission/tenant
    RS->>DB: Truy vấn báo cáo được phép
    DB-->>RS: Kết quả
    RS-->>S: Response
~~~

**Không có bước xác thực user qua browser**. Authorization Server xác thực client và đánh giá service policy. Resource Server bảo vệ báo cáo, không tự suy ra có user đang điều khiển worker.

### 2.2. Quyền được cấp trước không đồng nghĩa giả danh

| Tình huống | Đánh giá | Lý do |
|---|---|---|
| `reporting-worker` đọc báo cáo tổng hợp theo service grant | Phù hợp khi được cấp quyền | Service hành động dưới danh tính chính nó. |
| `backup-agent` sao lưu tài nguyên theo tenant grant do admin cấp | Có thể phù hợp | Quyền thuộc service account, có scope/tenant/audit. |
| Service gửi `user_id=admin` để AS phát token như admin | **Không** | Client tự chọn user, không có authentication/delegation proof. |
| Client credentials token được RS coi như mọi user đã đăng nhập | **Không** | Bỏ kiểm user context và authorization. |
| Service gọi endpoint “system export” được policy cho phép | Có thể phù hợp | Audit actor là service, target resource rõ. |
| Service dùng token exchange với subject token hợp lệ và delegation policy | Có thể phù hợp **qua flow khác** | AS phải kiểm subject/actor/grant/scope/audience. |

**Không nói Client Credentials “không bao giờ liên quan resource owner”**: trong doanh nghiệp, chủ thể có thẩm quyền có thể **cấu hình quyền máy–máy trước**. Nhưng quyền đó **không cho service tùy tiện giả danh một end user**.

## 3. Vai trò OAuth và principal: application khác user

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| **Resource Owner** | Tổ chức quản lý dữ liệu hoặc user có thẩm quyền | Chủ thể có thể cho phép truy cập protected resource. |
| **OAuth Client** | `reporting-worker` | Ứng dụng yêu cầu và sử dụng token. |
| **Service principal** | `SERVICE:reporting-worker` | Danh tính dịch vụ được AS/policy công nhận. |
| **End-user principal** | `USER:user-742` | Danh tính user có nguồn xác thực/ủy quyền phù hợp. |
| **Authorization Server** | `https://login.example.com` | Kiểm client và grant rồi phát token. |
| **Resource Server** | `orders-api` | Kiểm token và quyền trên dữ liệu. |
| **Record owner** | `order.owner_user_id=user-742` | Quan hệ dữ liệu/nghiệp vụ, không phải OAuth client identity. |
| **Delegated actor** | `support-service` hành động trong delegation chain | Bên thực thi theo chính sách delegation được chứng thực. |

### 3.1. Vì sao cần typed principal?

`sub=742` không đủ để biết `742` là user hay service. Một mô hình diễn giải rõ:

~~~text
Trusted principal:
  issuer = https://login.example.com
  type   = USER | SERVICE
  id     = user-742 | reporting-worker

Protected record:
  tenant_id  = tenant-beta
  owner_type = USER | ORGANIZATION
  owner_id   = user-742 | tenant-beta

Decision:
  principal type + principal id + tenant + action + resource
~~~

`principal_type` nếu được dùng là **custom claim/hợp đồng nội bộ**, không phải claim bắt buộc của OAuth. Một hệ thống có thể tách token profile, audiences hoặc dùng mapping client/grant đã được AS xác minh. **Không lấy principal type từ `X-Principal-Type` hoặc body do caller gửi.**

### 3.2. Người cấu hình job không phải người đang thực thi

Giả sử admin tạo cron job vào hôm trước:

~~~text
executing_principal = SERVICE:reporting-worker
configured_by_user  = USER:admin-12
operation           = reports:generate
tenant              = tenant-beta
~~~

Không được chuyển nó thành `executing_principal=USER:admin-12` hay `auth_time=now`. Audit phải phân biệt **người cấu hình**, **dịch vụ thực thi** và **đối tượng bị tác động**. Nếu nghiệp vụ đòi quyền ủy quyền theo user vẫn còn hiệu lực lúc job chạy, cần thiết kế delegated grant riêng, không chỉ giữ một user ID lịch sử.

## 4. `client_id` và `sub` không phải bí danh của nhau

### 4.1. JWT access token dành cho service

Ví dụ JWT access token được AS cấp theo profile hệ thống:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "reporting-worker",
  "aud": "reports-api",
  "client_id": "reporting-worker",
  "scope": "reports:read",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893453000,
  "jti": "service-access-31f6"
}
~~~

Đây là **payload minh họa chưa ký**, không phải token sử dụng được. Trong JWT Profile for OAuth 2.0 Access Tokens (**RFC 9068**), trường `sub` của access token cấp bằng Client Credentials thường được khuyến nghị tương ứng với định danh client, và có quy tắc cụ thể theo profile.

- `iss`: AS phát token.
- `sub`: subject theo token profile, ở ví dụ là **service principal**.
- `client_id`: OAuth client nhận grant, không phải một user tùy ý.
- `aud`: Resource Server được nhận token (`reports-api`).
- `scope`: phạm vi quyền do AS cấp, không tự cho phép mọi tenant/bản ghi.
- `iat`/`nbf`/`exp`: điều kiện thời gian; `jti` có thể định danh token.

**Không có claim `user-742`**, và không được suy ra nó từ request headers.

### 4.2. Token liên quan user qua Authorization Code flow

Một access token khác có thể được cấp sau khi `user-742` đăng nhập/ủy quyền:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-bff",
  "scope": "orders:read",
  "iat": 1893452400,
  "exp": 1893453000,
  "jti": "user-access-91ac"
}
~~~

Ở đây `sub=user-742` theo user-associated grant/profile, nhưng `client_id=shop-bff` vẫn là ứng dụng. **Không gọi client ID là user ID**, hoặc ngược lại. User token vẫn cần kiểm tenant, scope, quyền trên từng đơn.

### 4.3. Không phân loại bằng phép so sánh chuỗi

~~~java
// SAI: không đủ chứng minh principal là SERVICE.
boolean isService = jwt.getSubject()
    .equals(jwt.getClaimAsString("client_id"));
~~~

`sub == client_id` có thể phù hợp một profile nhưng không đủ phân loại bảo mật độc lập. Cần **issuer + token profile + client/grant mapping** và, nếu hệ thống thiết kế, trusted `principal_type` claim do AS phát. Một user và service có thể trùng chuỗi ID; ghép key danh tính cùng **issuer và principal type**.

### 4.4. Opaque token cũng có vấn đề tương tự

Resource Server dùng **OAuth Token Introspection (RFC 7662)** có thể nhận:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "reporting-worker",
  "client_id": "reporting-worker",
  "aud": "reports-api",
  "scope": "reports:read",
  "exp": 1893453000
}
~~~

Ngoài `active`, các fields tùy AS và hợp đồng. `active=true` **không xác thực một end user**; API còn phải kiểm audience, scope, tenant, principal type và resource policy. JWT hay opaque chỉ là định dạng token; không tự giải quyết authorization.

### 4.5. `act` khác `sub` và `client_id`

Token được AS cấp trong một mô hình **delegation/token exchange** có thể chứa actor:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "payments-api",
  "scope": "payments:read",
  "act": {
    "sub": "support-service"
  }
}
~~~

Ví dụ là **payload minh họa**, không đủ chứng minh delegation. Theo RFC 8693, `act` có thể diễn tả bên **đang hành động**; `sub` là subject có quyền được biểu diễn. Client không được tự dựng claim `act` và coi nó là được AS/RS tin. **`act` không mặc nhiên có trong mọi token exchange**; policy quyết định việc delegation, impersonation và cách diễn giải.

## 5. HTTP Client Credentials Grant đúng ngữ nghĩa

Confidential client xác thực với AS/token endpoint rồi xin access token:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <ENCODED_REGISTERED_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&
scope=reports%3Aread&
resource=https%3A%2F%2Fapi.example.com%2Freports
~~~

Body xuống dòng để dễ đọc; request thực phải là một form được encode hợp lệ qua HTTPS. `resource` chỉ áp dụng theo **RFC 8707** nếu AS hỗ trợ; AS quyết định audience dựa trên policy.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "SERVICE_ACCESS_TOKEN_EXAMPLE",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "reports:read"
}
~~~

Ở đây **không có trường chuẩn `user_id`, `username` hoặc `act_as` tự cho client chọn user**. Client secret chỉ dùng xác thực **client**, không phải mọi end user.

### 5.1. Authorization Server phải kiểm

1. Client được đăng ký **confidential**, active và được dùng `client_credentials`.
2. Client authentication qua phương thức đã đăng ký: `client_secret_basic`, `private_key_jwt`, mTLS hoặc cơ chế hỗ trợ.
3. Resource/audience và scopes được phép cho chính client/service grant.
4. Tenant/organization binding nếu grant có ranh giới đa tenant.
5. Access token phát hành đúng issuer, audience, scope, TTL, token profile và sender constraint khi áp dụng.
6. Client bị khóa/revoke hoặc policy thay đổi thì không tiếp tục cấp token trái quy định.

**Biết client secret không có nghĩa được mọi scope**. Mỗi `client_id` chỉ có quyền do AS/RS cấu hình.

### 5.2. Vì sao thường không có refresh token?

Theo **RFC 6749 `4.4.3**, refresh token **SHOULD NOT** được cấp trong Client Credentials Grant. Confidential client có thể **xác thực lại với AS** để xin access token khác khi token cũ hết hạn. Không coi TTL access token là một “phiên đăng nhập user”. Profile/provider riêng nếu có refresh token cần được đánh giá chặt, không phải mặc định của grant này.

### 5.3. Sai phạm: đưa user ID vào token request

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <VALID_SERVICE_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=reports%3Aread&
user_id=user-admin&
tenant_id=tenant-anpha&
act_as=admin
~~~

`user_id`/`act_as` ở đây **không là bằng chứng xác thực/delegation chuẩn** của Client Credentials Grant. AS không được dùng chúng để tạo token `sub=user-admin`. AS có thể từ chối tham số không hợp lệ theo chính sách hoặc bỏ qua an toàn; **tuyệt đối không nâng thành user token** chỉ từ request.

### 5.4. Phân biệt khi BFF có user grant

Confidential BFF có thể xác thực tại token endpoint bằng client secret **trong Authorization Code + PKCE** đã có grant liên quan user. Nhưng **user identity** đến từ authorization transaction/AS, không phải từ client secret.

Không biến Client Credentials flow thành user flow bằng cách ghép `user=...` rồi tin rằng OAuth đã xác thực user.

## 6. Các mẫu giả danh phải chặn

| Mẫu nguy hiểm | Lỗ hổng | Cách đúng |
|---|---|---|
| `grant_type=client_credentials&sub=user-742` | Client tự chọn subject. | AS ấn định service subject theo grant. |
| `X-User-Id: user-742` đi cùng service token | Header tự khai bị xem là user proof. | Nếu cần, chỉ xem như **target user** sau kiểm service policy. |
| JSON `approvedBy=user-742` | Giả mạo người phê duyệt/audit actor. | Server set actor từ verified principal. |
| Query `impersonate=admin` | Cờ giả danh không có authority. | Impersonation policy có approval/step-up/audit riêng. |
| Decode `sub` rồi chọn principal dựa trên tên ID | User/service trùng chuỗi gây nhầm quyền. | Typed principal theo issuer/profile. |
| Service token gọi endpoint chỉ cho user | Service bypass user-only authorization. | Từ chối SERVICE principal, yêu cầu user grant khi cần. |
| Service tự ký JWT có `act` | Claim không được AS tin cậy phát hành. | Token exchange/ủy quyền theo AS policy. |
| Token `aud=reports-api` dùng tại `payments-api` | Sai audience, token substitution. | RS kiểm audience; client xin token đúng resource. |
| Truyền `X-Forwarded-User` giữa microservices tự do | Identity spoofing qua trusted-looking header. | Trust boundary rõ, bỏ header chưa chứng thực, dùng delegation context phù hợp. |

### 6.1. User ID trong request vẫn có thể là dữ liệu mục tiêu

~~~http
POST /support/tickets/581/assign HTTP/1.1
Host: support.example.com
Authorization: Bearer <SUPPORT_SERVICE_ACCESS_TOKEN>
Content-Type: application/json

{"assigneeUserId":"user-742"}
~~~

`assigneeUserId` là **người được phân công ticket**, không phải caller. Resource Server phải xác minh `support-service` có quyền `support:tickets:assign` đối với tenant/ticket và assignee hợp lệ. Audit:

~~~text
actor_type  = SERVICE
actor_id    = support-service
action      = ticket.assign
target_user = user-742
target_id   = ticket-581
~~~

**Không** ghi `actor_id=user-742` chỉ vì JSON chứa giá trị đó.

### 6.2. Nội bộ hoặc mTLS không có nghĩa user đã xác thực

Kubernetes namespace, IP nội bộ hoặc mTLS client certificate có thể xác định **dịch vụ gửi request**, không phải end user. Header `X-User-Id` do upstream gửi chỉ có thể đáng tin nếu có **gateway contract và cơ chế chống spoofing rõ ràng**; ngay cả vậy cần biết user đã được xác thực theo flow nào và service có quyền đại diện hay không.

**Network trust không thay user authorization.**

## 7. Resource Server dùng typed principal và object-level policy

Mỗi request tới Resource Server phải vượt qua các phép kiểm độc lập:

1. Access token đúng **issuer và token purpose/profile**.
2. Chữ ký JWT/thuật toán được kiểm bằng khóa tin cậy, hoặc introspection opaque từ AS tin cậy.
3. `aud` chứa audience API đích; `exp`/`nbf` và trạng thái cần thiết còn hợp lệ.
4. `scope`/permission đủ cho operation; **principal type** được xác minh.
5. Service được phép truy cập **tenant và resource cụ thể**, không chỉ được quyền chung “đọc”.
6. Sender-constrained token có DPoP/mTLS proof được kiểm tại RS nếu áp dụng.
7. Không tin request field `userId` để thay authenticated principal.

### 7.1. USER và SERVICE có endpoint policy khác nhau

| Endpoint | USER principal | SERVICE principal |
|---|---|---|
| `GET /me/orders` | Subject user theo token; lọc ownership/ACL. | **Từ chối** nếu “me” không có nghĩa với service. |
| `GET /orders/{id}` | Kiểm user scope, tenant, ACL. | Chỉ cho service đã cấp quyền trên tenant/resource, không mặc định. |
| `POST /orders/{id}/cancel` | Kiểm user permission, trạng thái, step-up nếu cần. | Service cần quyền **system cancel** riêng, không mượn role user. |
| `POST /batch/reports/generate` | Có thể yêu cầu admin user. | `reporting-worker` theo service grant/tenant. |
| `POST /users/{id}/reset-password` | Self-service theo flow user thích hợp. | Chỉ service admin chuyên biệt nếu có policy nghiêm ngặt/audit. |
| `GET /tenants/{tenant}/exports` | Kiểm membership/role user. | Kiểm service-tenant grant độc lập. |

### 7.2. Tenant boundary không được suy ra từ audience

~~~text
Issuer:             https://login.example.com
Subject:            reporting-worker
Audience:           reports-api
Scope:              reports:read
Allowed tenant:     tenant-beta
Requested resource: /tenants/tenant-anpha/reports
~~~

**Phải từ chối** nếu service không được phép tenant Anpha, dù JWT đúng chữ ký/audience/scope. `aud` xác định API đích, không chỉ định tất cả tổ chức mà API lưu dữ liệu.

### 7.3. SQL tránh BOLA/IDOR đối với service principal

**Không an toàn** khi chỉ biết order ID:

~~~sql
SELECT id, total, tenant_id
FROM orders
WHERE id = :orderId;
~~~

Một mô hình kiểm quyền gắn service với tenant:

~~~sql
SELECT o.id, o.total, o.tenant_id
FROM orders o
JOIN service_tenant_permissions p
  ON p.tenant_id = o.tenant_id
WHERE o.id = :orderId
  AND o.tenant_id = :trustedTargetTenant
  AND p.service_principal_id = :trustedServicePrincipal
  AND p.permission = 'ORDERS_READ'
  AND p.status = 'ACTIVE';
~~~

Đây là schema minh họa. `trustedServicePrincipal` phải đến từ token/identity mapping đã xác minh; tenant từ request phải được đối chiếu với quyền service thật. Có thể cần thêm object ACL, trạng thái resource và RLS. **Service scope không tự thay kiểm quyền tenant/bản ghi**.

### 7.4. Khi không xác định được principal type, hãy fail closed

Nếu token không có bằng chứng đáng tin cho principal type/grant, RS **không suy đoán user** từ header, email hoặc client ID. Từ chối có mã lỗi phù hợp và audit metadata an toàn. Hỗ trợ hệ thống legacy bằng cách chấp nhận “có token là có quyền user” chỉ kéo dài lỗ hổng.

## 8. Khi cần làm thay user: dùng flow có bằng chứng ủy quyền

Một yêu cầu hợp pháp có thể là: người dùng đăng nhập, bấm “Thanh toán”, và Orders Service cần gọi Payments API **theo quyền được ủy quyền từ người dùng**. Điều này đòi **user-associated authorization context**, không chỉ client secret của Orders Service.

### 8.1. User hiện diện: Authorization Code + PKCE/OIDC

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User user-742
    participant B as Browser
    participant C as Web BFF / OAuth Client
    participant AS as Authorization Server / OP
    participant RS as Orders API
    U->>B: Chọn đăng nhập
    B->>C: Bắt đầu authorization flow
    C-->>B: Redirect với state và PKCE challenge
    B->>AS: Authorization request
    AS->>U: Xác thực và consent khi cần
    U-->>AS: Hoàn tất authentication/authorization
    AS-->>B: Redirect với authorization code
    B->>C: Callback code + state
    C->>AS: Đổi code + PKCE + client auth nếu confidential
    AS-->>C: Access token liên quan user grant
    C->>RS: Bearer token aud=orders-api
    RS->>RS: Kiểm token và user/tenant/record policy
    RS-->>C: Đơn hàng được phép
~~~

Trong Authorization Code flow, user identity đến từ **AS và authorization transaction** được xác minh. BFF có thể đồng thời dùng client secret để xác thực **ứng dụng** tại token endpoint. Nhưng client secret **không quyết định `sub=user-742`**; subject đó đến từ user grant.

OIDC `id_token` để OIDC Client xác minh authentication user, **không phải access token của Resource Server**. Orders API phải nhận access token đúng `iss`, `aud`, `scope` và mục đích.

### 8.2. Service gọi tiếp API khác: Token Exchange

~~~text
User token T1:
  sub=user-742
  aud=orders-api
  scope=orders:read

Orders Service cần gọi Payments API:
  Không forward T1 đến payments-api nếu audience sai.
  Không gọi client_credentials rồi thêm sub=user-742.
~~~

Nếu AS hỗ trợ, **OAuth 2.0 Token Exchange (RFC 8693)** cho phép client/service gửi **subject token** đã được kiểm, có thể thêm **actor token**, để xin token mới cho audience/scope khác. AS phải kiểm quyền của subject, actor/client, delegation/impersonation policy và resource đích.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Orders Service / Actor
    participant AS as Authorization Server
    participant P as Payments Resource Server
    O->>AS: Token exchange, subject_token + client auth
    AS->>AS: Kiểm subject, actor, grant, scope, audience
    AS-->>O: Delegated token aud=payments-api nếu được phép
    O->>P: Access token dành cho Payments API
    P->>P: Kiểm iss, aud, scope, actor/subject và quyền
    P-->>O: Cho phép hoặc từ chối
~~~

Một request minh họa (cần AS hỗ trợ và client được cấp quyền exchange):

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <ORDERS_SERVICE_CLIENT_AUTH>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&
subject_token=VALID_USER_ASSOCIATED_ACCESS_TOKEN&
subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&
resource=https%3A%2F%2Fapi.example.com%2Fpayments&
scope=payments%3Aread
~~~

**Không có bảo đảm yêu cầu sẽ thành công.** AS phải kiểm subject token, client có quyền exchange, target resource và permission. RFC 8693 có thể biểu diễn **delegation hoặc impersonation** theo chính sách cụ thể, nhưng không cho một client credentials token tự động giả danh bất kỳ user.

### 8.3. Claim `act` không phải vé vượt quyền

Token delegation có thể chứa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "payments-api",
  "scope": "payments:read",
  "act": {
    "sub": "orders-service"
  }
}
~~~

- `sub`: subject của token theo profile.
- `act`: actor đang hành động nếu profile sử dụng actor claim.
- `client_id`: OAuth client liên quan đến việc xin token; không tự đồng nghĩa `act`.
- `aud`: API được nhận token.

Đây chỉ là cấu trúc minh họa; **AS phải thực sự kiểm delegation/actor**. Resource Server phải validate toàn token, token purpose và policy. Một API có thể cấm delegated service actor ở thao tác nhạy cảm dù `sub` là user.

### 8.4. Job định kỳ không cần giả user

~~~text
actor_type   = SERVICE
actor_id     = reporting-worker
tenant_id    = tenant-beta
action       = reports:generate
grant_source = organization_service_policy
configured_by_user_id = admin-12 (historical metadata)
~~~

`configured_by_user_id` là người **đã tạo lịch** và phải được kiểm ở thời điểm cấu hình, không chứng minh người đó đang xác thực lúc job chạy. Nếu nghiệp vụ cần quyền user còn hiệu lực ở thời điểm chạy, phải có delegated/offline authorization được quản lý và thu hồi, không chỉ lưu user ID.

## 9. AS không được lấy subject từ client credentials request

### 9.1. Bảng ranh giới dữ liệu tin cậy

| Thuộc tính | Nguồn đáng tin | Không được làm |
|---|---|---|
| Client identity | Client authentication theo registration. | Tin `client_id` tự khai như mật khẩu. |
| Grant type | `client_credentials` được đăng ký cho client. | Dùng `act_as` để tự biến flow thành user grant. |
| Subject | Service principal mapping của AS. | Copy `request.user_id`/`request.sub`. |
| Audience | Resource catalog và client grant policy. | Cho `request.aud` tùy ý. |
| Scope | Allowed scopes và service entitlements. | Cấp mọi scope chỉ vì secret hợp lệ. |
| Tenant | Service-to-tenant grant đã được phê duyệt. | Tin tenant header/parameter mà chưa kiểm. |
| Token TTL | AS token policy. | Tin `expires_in` do caller tự chọn. |
| Sender binding | Proof DPoP/mTLS được xác minh nếu hỗ trợ. | Tin header `proof_valid=true`. |

### 9.2. Pseudocode của token issuer

~~~text
function issueClientCredentialsToken(request, tlsContext):
    require HTTPS POST to configured token endpoint
    require request.grant_type == "client_credentials"

    client = authenticateConfidentialClient(request, tlsContext)
    if client inactive or invalid:
        reject invalid_client

    if !client.allowedGrantTypes.contains("client_credentials"):
        reject unauthorized_client

    targetResource = resolveApprovedResource(request.resource)
    if targetResource not permitted for client:
        reject

    requestedScopes = parseAndValidate(request.scope)
    allowedScopes = policy.allowedScopesForService(client, targetResource)
    if requestedScopes exceed allowedScopes:
        reject invalid_scope or narrow according to policy

    servicePrincipal = trustedServiceMapping(client.id)
    if servicePrincipal missing:
        reject

    tenantEntitlements = policy.allowedTenants(client.id)
    if tenant context violates service grant:
        reject

    return issueAccessToken(
        issuer = configuredIssuer,
        subject = servicePrincipal.id,
        principalType = SERVICE,
        clientId = client.id,
        audience = targetResource.canonicalAudience,
        scopes = approvedScopes,
        ttl = policy.accessTokenLifetime
    )
~~~

Đây là pseudocode, không phải thuật toán chuẩn bắt buộc. Claim `principalType` là **custom profile option** nếu được dùng. Tuyệt đối không có nhánh **`request.user_id → user subject`** trong Client Credentials Grant.

### 9.3. User/service ID collision và namespace confusion

Giả sử tồn tại user `admin` và AS cho phép đăng ký client `client_id=admin`. Nếu Client Credentials access token có `sub=admin`, một Resource Server chỉ kiểm `sub` mà không phân biệt principal type có thể coi service này là user admin.

Biện pháp:

1. Tách namespaces hoặc dùng typed principal `(issuer, type, id)`.
2. Giới hạn việc đăng ký `client_id` trùng user identifiers nhạy cảm.
3. RS kiểm token profile/principal type bằng **bằng chứng đáng tin**, không chỉ `sub == client_id`.
4. Tách user-only và service-only permissions hoặc audiences khi kiến trúc yêu cầu.
5. Không nhầm token `scope=orders:read` với user đã được quyền trên mọi đơn.

### 9.4. Cấm “scope = user admin” tự phát

Một scope như `orders:admin` chỉ có nghĩa khi AS/RS định nghĩa rõ. Nếu service có được scope này theo service policy, phải xác định rõ hành động và tenant nào được thực hiện. Không xem nó là bằng chứng user admin đã login hoặc chấp thuận thao tác. Không thực hiện phép union permissions giữa service và user ID do client tự khai.

## 10. Java/Spring Security: tách USER và SERVICE

### 10.1. Xác minh JWT trước khi đọc claims

Với Spring Security Resource Server, một `JwtDecoder` đáng tin phải xác minh chữ ký, issuer, hạn và **audience của chính API**. Ví dụ các validators trọng tâm:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfiguration {
    private static final String ISSUER = "https://login.example.com";
    private static final String AUDIENCE = "orders-api";

    @Bean
    NimbusJwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://login.example.com/oauth2/jwks")
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = token ->
            token.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Audience is not accepted", null)
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator
            )
        );
        return decoder;
    }
}
~~~

Mã chỉ minh họa **issuer + audience** cùng default validators của Spring; production còn cần verify token purpose/profile, allowed algorithms, sender proof nếu dùng, scopes, revocation policy và resource-level authorization. Không giả định cấu hình chỉ có `issuer-uri` tự kiểm audience đúng API; cần test validator thực tế.

### 10.2. Chính sách principal type bắt buộc

Giả sử Authorization Server phát **trusted custom claim** `principal_type` là `USER` hoặc `SERVICE` từ token profile/verified grant; Resource Server đã xác minh token trước khi dùng:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public final class PrincipalPolicy {

    public String requireUser(Jwt verifiedJwt) {
        String type = verifiedJwt.getClaimAsString("principal_type");
        String subject = verifiedJwt.getSubject();

        if (!"USER".equals(type) ||
                subject == null || subject.isBlank()) {
            throw new AccessDeniedException("USER_PRINCIPAL_REQUIRED");
        }
        return subject;
    }

    public String requireService(Jwt verifiedJwt) {
        String type = verifiedJwt.getClaimAsString("principal_type");
        String clientId = verifiedJwt.getClaimAsString("client_id");

        if (!"SERVICE".equals(type) ||
                clientId == null || clientId.isBlank()) {
            throw new AccessDeniedException("SERVICE_PRINCIPAL_REQUIRED");
        }
        return clientId;
    }
}
~~~

`principal_type` không phải OAuth claim chuẩn bắt buộc. **AS phải sinh claim này từ policy/grant được tin**, không copy từ `request.principal_type` do client gửi. Nếu issuer không phát claim, phải có mapping/profile khác đáng tin; **không tự gán mặc định USER**.

### 10.3. User-only endpoint từ chối service token

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MyOrdersController {
    private final PrincipalPolicy principals;
    private final OrderService orders;

    public MyOrdersController(PrincipalPolicy principals,
                              OrderService orders) {
        this.principals = principals;
        this.orders = orders;
    }

    @GetMapping("/me/orders")
    public ResponseEntity<?> myOrders(
            @AuthenticationPrincipal Jwt verifiedJwt) {

        String userId = principals.requireUser(verifiedJwt);
        // Business service must also check scope, tenant and ACL.
        return ResponseEntity.ok(orders.listReadableFor(userId));
    }
}
~~~

`OrderService` là interface minh họa, chưa có implementation. Trong thực tế phải kiểm `scope`/authority, tenant membership và resource policy; `hasAuthority('SCOPE_orders:read')` một mình không chặn BOLA/IDOR nếu principal type bị nhầm.

### 10.4. Endpoint riêng cho tác vụ dịch vụ

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final PrincipalPolicy principals;
    private final ServiceGrantPolicy grants;
    private final ReportGenerator reports;

    public ReportController(PrincipalPolicy principals,
            ServiceGrantPolicy grants, ReportGenerator reports) {
        this.principals = principals;
        this.grants = grants;
        this.reports = reports;
    }

    @PostMapping("/tenants/{tenantId}/reports/generate")
    public ResponseEntity<?> generate(
            @AuthenticationPrincipal Jwt verifiedJwt,
            @PathVariable String tenantId) {

        String serviceId = principals.requireService(verifiedJwt);
        grants.requirePermission(
            serviceId, tenantId, "REPORTS_GENERATE", verifiedJwt
        );
        return ResponseEntity.accepted()
            .body(reports.scheduleForTenant(tenantId, serviceId));
    }
}
~~~

`ServiceGrantPolicy` và `ReportGenerator` là interfaces dịch vụ minh họa, chưa được khai báo. Điểm cốt lõi: **serviceId đến từ verified token**, tenant là target phải kiểm với policy. Không dùng field `actingUser` từ request làm principal.

### 10.5. Spring Authorization Server: đăng ký client chỉ có client credentials

~~~java
import java.util.UUID;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

public final class ServiceClientRegistration {

    private ServiceClientRegistration() {}

    public static RegisteredClient reportingWorker(
            String encodedClientSecret) {

        return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("reporting-worker")
            .clientSecret(encodedClientSecret)
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC
            )
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS
            )
            .scope("reports:read")
            .build();
    }
}
~~~

`encodedClientSecret` phải được AS chuẩn bị theo password encoder/secret management phù hợp, không hardcode raw secret. Đoạn code chỉ minh họa registration; chưa có issuer, keys, token endpoint, resource policies hay persistent repositories. `UUID.randomUUID()` chỉ minh họa ID record, production cần **registration ID ổn định**. Đăng ký scope không tự cho service quyền tất cả tenant.

Nếu cần `principal_type=SERVICE`, AS phải phát bằng **token customizer dựa trên grant/client đã xác minh**, không nhận `principal_type` từ client form.

## 11. Impersonation có kiểm soát là một đặc quyền riêng

Trong các hệ thống hỗ trợ khách hàng, đôi khi nhân viên hỗ trợ cần xem trải nghiệm của một user để khắc phục lỗi. Đây là nhu cầu **có thể hợp pháp**, nhưng **không triển khai bằng `client_credentials` + `user_id`**.

### 11.1. Mô hình phê duyệt rõ ràng

Một quy trình có thể yêu cầu:

1. **Nhân viên hỗ trợ đăng nhập dưới user identity thật**, có MFA/step-up cho quyền nhạy cảm.
2. Có ticket/case, mục đích và căn cứ cho phép rõ, giới hạn tenant và người được hỗ trợ.
3. Kiểm quyền nhân viên, approval hai người hoặc policy tương ứng khi có rủi ro cao.
4. Authorization service/AS phát context/token được tin cậy, **ràng buộc actor và effective subject** theo flow.
5. Token được giới hạn **audience, scope, TTL, resource** và sender binding khi cần.
6. Resource Server chỉ chấp nhận impersonation tại **các endpoint được cho phép**, từ chối chuyển tiền/đổi mật khẩu nếu policy cấm.
7. Audit đầy đủ actor thật, subject/target, ticket, quyết định policy và thời gian.
8. Có revoke/end impersonation và quy trình review hoạt động.

Mô hình có thể chọn **delegation** (bên hỗ trợ hành động như actor trong phạm vi user cho phép) thay vì **impersonation** (được thể hiện là acting-as subject) tùy kiến trúc. Hai cách cần semantics rõ, không chỉ đổi tên claim.

### 11.2. Tại sao không để API “tự cấp quyền” từ service token?

Nếu `support-service` có service token hợp lệ rồi gọi `?impersonate=user-742`, API có thể biết request đến từ support-service, nhưng **không biết có support agent cụ thể nào đã phê duyệt**. Nếu bearer token bị lấy, attacker có thể “impersonate” mọi user bằng cách đổi parameter.

Token/service credentials chỉ chứng minh một phần ranh giới. Muốn impersonation, phải có **authorization decision** độc lập về actor, case, target, operation, scope và thời hạn, với chứng cứ đáng tin.

### 11.3. Đừng xóa dấu vết actor thật

**Sai:**

~~~json
{
  "event": "refund_approved",
  "approved_by": "user-742",
  "client_id": "support-service"
}
~~~

nếu request thật do support agent hoặc automation thực hiện chứ user-742 không trực tiếp phê duyệt.

**Rõ ràng hơn, nếu có impersonation hợp lệ:**

~~~json
{
  "event": "refund_approved",
  "executing_principal_type": "USER",
  "executing_principal_id": "support-agent-8",
  "effective_subject": "user-742",
  "authorization_mode": "approved_impersonation",
  "approval_reference": "case-918",
  "tenant_id": "tenant-beta",
  "decision": "allowed"
}
~~~

Đây là **audit schema minh họa**, không phải chứng minh impersonation đã hợp lệ; hệ thống phải kiểm được approval reference/grant và token. Nếu automation không có user actor hiện diện, hãy ghi `executing_principal_type=SERVICE` thay vì dựng user giả.

## 12. Audit: actor, subject, target và người cấp phép khác nhau

Một bản ghi an toàn nên trả lời:

| Câu hỏi | Trường gợi ý | Nguồn tin cậy |
|---|---|---|
| Ai thực sự gọi API? | `actor_type`, `actor_id` | Verified access token/sender identity, không từ body. |
| Quyền của ai đang được dùng? | `effective_subject` hoặc `delegation_ref` | Token/grant được AS/authorization service kiểm. |
| Ai là mục tiêu của thao tác? | `target_user_id`, `resource_id` | Request đã được validate và đối chiếu với policy. |
| Ai đã tạo lịch hoặc cấp quyền trước? | `configured_by`, `approved_by` | Grant/approval history đã được chứng thực. |
| Operation nào đã được phép? | `action`, `policy_decision` | Authorization engine hoặc service policy. |
| Điều tra sự kiện thế nào? | `trace_id`, `error_code` | Correlation ID tin cậy và sanitized metadata. |

Ví dụ tác vụ định kỳ:

~~~json
{
  "event": "monthly_report_generated",
  "actor_type": "SERVICE",
  "actor_id": "reporting-worker",
  "tenant_id": "tenant-beta",
  "report_id": "report-81",
  "configured_by": "admin-12",
  "authorization_mode": "service_grant",
  "decision": "allowed",
  "trace_id": "b7d9f1225a6e4c7ab30d2189444b5f60"
}
~~~

`configured_by` chỉ là metadata lịch sử đã được xác minh ở thời điểm cấu hình. Nó **không tự chứng minh admin-12 vừa đăng nhập** hoặc chấp thuận request lúc này. Những trường liên kết người dùng cần RBAC, retention và căn cứ audit phù hợp.

### 12.1. Không ghi bearer token hoặc client secret

Các giá trị **không được đẩy nguyên vẹn** vào log, trace, request dump hoặc error reporting:

~~~text
Authorization: Bearer ...
Authorization: Basic ...
client_secret / client_assertion
private_key / PEM / keystore password
access_token / refresh_token / id_token
Cookie / Set-Cookie / session ID
DPoP proof
full JWT or opaque token
HTTP body của token endpoint
signed URL và query có credential
~~~

Token được ký không có nghĩa an toàn để log: bearer access token còn hạn có thể bị phát lại; JWT payload có thể lộ danh tính/scope/tenant. **Không thu thập tại nguồn**; dùng allowlist metadata như service, route template, HTTP status, error code và trace ID. Regex chỉ tìm JWT ba đoạn không phát hiện opaque token/client secret.

### 12.2. “On behalf of” không được suy ra từ tên trường

Một sự kiện tên `processing_on_behalf_of_user` không tự tạo delegation hợp lệ. Cần lưu tham chiếu tới **authorization context đã kiểm**, actor identity và outcome. Nếu không có, chỉ ghi “service xử lý yêu cầu có target user”, không “user đã thực hiện”.

## 13. Token security: xác minh, lưu trữ và chống replay

Client Credentials Grant thường dùng **bearer access token**. Kẻ lấy được bản sao token còn hạn có thể thử gọi Resource Server dưới quyền service đó. Việc API không cho token giả danh user **không loại bỏ** nguy cơ lạm dụng chính service permissions.

### 13.1. JWT access token: chữ ký không đủ

Một Resource Server kiểm JWT cần:

- Đúng **issuer** đáng tin và key/algorithm đã cho phép; không tin `alg=none` hay key URL từ JWT header không kiểm.
- Đúng **token type/profile**; không nhận ID token/client assertion/refresh token làm access token.
- Đúng **audience** của chính API.
- `exp`/`nbf` hợp lệ theo clock skew có giới hạn.
- `scope` và **principal type**/service identity được xác minh.
- Quyền service trên tenant/resource/operation hiện tại.
- DPoP/mTLS proof nếu token có sender constraint theo profile.
- Revocation/state check bổ sung nếu yêu cầu thu hồi nhanh.

**Không thể dùng JWT signature để chứng minh “user đã consent” khi token chỉ là Client Credentials.** Chữ ký chứng minh AS đã phát token với các claims đó, không tự thay ngữ nghĩa grant.

### 13.2. Opaque access token: introspection cũng không đủ

Với opaque token, RS dùng OAuth Token Introspection (RFC 7662) hoặc tra cứu tin cậy. `active=true` cho biết trạng thái token theo AS, không cho phép mọi endpoint. Kiểm scope/audience/tenant/typed principal như JWT. Introspection cache có thể trì hoãn tác động revoke, nên cần TTL/cache policy theo rủi ro.

### 13.3. Access token đúng audience vẫn chỉ có quyền hữu hạn

Ví dụ:

~~~text
Client:       reporting-worker
Audience:     reports-api
Scope:        reports:read
Tenant grant: tenant-beta

Allowed:
  GET /tenants/tenant-beta/reports/summary

Not automatically allowed:
  GET /tenants/tenant-anpha/reports/summary
  POST /tenants/tenant-beta/payments/refund
  POST /users/user-742/change-password
~~~

Nếu một token có nhiều audiences, blast radius có thể tăng nếu bị lộ tại một nơi. AS nên cân nhắc cấp token **resource-specific**, scope tối thiểu và TTL phù hợp.

### 13.4. Sender-constrained token giảm replay nhưng không cấp quyền user

**DPoP (RFC 9449)** hoặc **mTLS certificate-bound access tokens (RFC 8705)** có thể khiến bản sao access token khó dùng nếu attacker không có private key/certificate tương ứng, nhưng:

- AS phải phát token và ràng buộc đúng sender.
- RS phải kiểm proof, binding, thời gian/replay policy khi áp dụng.
- Nếu attacker lấy cả token và khóa hoặc điều khiển process, sender binding có thể không đủ.
- Sender binding không biến `SERVICE` principal thành `USER` principal.

### 13.5. Secret và private key của client

Confidential client cần bảo vệ `client_secret`, `private_key_jwt` key hoặc mTLS certificate private key:

- Lưu ở secret manager/HSM/KMS phù hợp; không hardcode trong source/CI logs/container image.
- Giới hạn RBAC theo service/environment; rotate/revoke khi compromise.
- Bảo vệ token endpoint qua TLS và không ghi Basic header, JWT assertion/secret trong trace.
- Đăng ký method/algorithms/keys cụ thể với AS; không downgrade xác thực khi gặp lỗi.
- Với `private_key_jwt`, assertion có audience token endpoint, issuer/subject client ID, expiry ngắn, chống replay theo policy; đây **không phải user token**.

**Client secret bị lộ có thể cho attacker xin service access token mới**, nên đôi khi blast radius lớn hơn lộ một access token ngắn hạn.

## 14. Thu hồi quyền service không đồng nghĩa logout user

### 14.1. Bốn vòng đời khác nhau

| Trạng thái | Ý nghĩa | Ảnh hưởng |
|---|---|---|
| **Client registration** | `reporting-worker` active/disabled, credentials còn hợp lệ. | AS có thể từ chối cấp token mới cho client bị khóa. |
| **Service grant/tenant permission** | Service được phép `reports:read` tại Beta. | AS hoặc RS cần kiểm quyền hiện hành, tránh stale authorization. |
| **Access token** | Có `exp`, `aud`, `scope` và cơ chế revocation riêng. | Token cũ có thể còn dùng đến hạn nếu RS không kiểm state. |
| **Browser/OP user session** | Phiên đăng nhập của một người dùng. | **Không nhất thiết tồn tại** trong Client Credentials Grant. |

Client Credentials thường **không cần refresh token**; sau access token expiry, confidential client có thể xin token mới bằng chính client authentication. Việc user logout khỏi browser không có liên hệ trực tiếp với một service grant độc lập, trừ khi hệ thống có chính sách liên kết rõ.

### 14.2. Nếu thu hồi service grant ở tenant Beta?

Giả sử admin gỡ quyền `reports:read` của service tại Beta:

1. Ngăn cấp token mới có quyền Beta tại AS.
2. Resource Server kiểm quyền tenant hiện hành nếu cần tác động tức thời, hoặc dùng access token TTL ngắn/denylist/state.
3. Vô hiệu các cache service permissions phù hợp.
4. Audit sự kiện admin revoke và client/service bị ảnh hưởng.
5. Đánh giá những access token còn hạn, kể cả JWT được RS validate offline.

Không mặc định **disable client** đồng nghĩa mọi JWT đã cấp bị từ chối tức thì. Nếu RS dùng opaque introspection, cache vẫn có thể gây trễ.

### 14.3. Khi client secret bị lộ

Playbook:

1. Ngăn lộ tiếp trong logs/telemetry/source/CI/config.
2. Rotate/revoke client secret hoặc private key/cert; vô hiệu client tạm thời khi rủi ro yêu cầu.
3. Kiểm access tokens còn hạn và áp dụng revoke/denylist/state check nếu có.
4. Điều tra hoạt động bất thường, scopes/audiences/tenants mà client có quyền, không chỉ user-facing actions.
5. Đánh giá lại least privilege, key management, logs/backup/export và network access.
6. Thêm canary tests và giám sát credential issuance/rate/invalid_client.

**Không tự động đổi JWT signing key của AS chỉ vì một client secret bị lộ** nếu key ký của AS vẫn an toàn; hai loại secret có phạm vi ảnh hưởng và quy trình ứng cứu khác nhau.

## 15. Ma trận sai lầm và biện pháp

| Lỗi / mối đe dọa | Hậu quả | Biện pháp |
|---|---|---|
| Client Credentials token có `sub=user-admin` lấy từ form | User impersonation từ service grant. | AS set service subject theo trusted mapping; không lấy user từ request. |
| API tin `X-User-Id` dù caller là service | Bypass user authentication. | Typed principal; header chỉ là target nếu policy cho phép. |
| Audit `approved_by` từ request body | Giả mạo lịch sử phê duyệt. | Actor từ verified token; target/approver tách biệt. |
| Client ID trùng user ID và RS chỉ so `sub` | Subject namespace confusion. | Tách namespace, type và issuer/profile checks. |
| Service token được chấp nhận ở `/me` | Service tự nhận user context. | User-only endpoint yêu cầu trusted USER principal. |
| Scope `orders:read` được coi là mọi tenant | BOLA/cross-tenant data leak. | Service–tenant entitlements và object-level policy. |
| Client yêu cầu arbitrary `aud=payments-api` | Token substitution và mở rộng quyền. | AS resource grant, RS audience validation. |
| Client tự ký JWT có `act`/`sub` user | Giả mạo delegated token. | Chỉ token AS tin cậy, policy token exchange. |
| Forward user token Orders sang Payments | Audience confusion. | Token exchange/resource-specific token khi được phép. |
| M2M service dùng ID token thay access token | Token purpose confusion. | RS kiểm access-token profile/purpose. |
| AS copy custom `principal_type=USER` từ request | Client tự nâng thành user. | AS sinh trusted principal type từ grant. |
| JWT chỉ được decode không verify | Attacker sửa claims. | Signature/algorithm/issuer/time/audience validation. |
| Opaque introspection `active=true` được coi là mọi quyền | Bỏ scope/tenant checks. | Kiểm permission và context. |
| Client secret trong repo/log | Xin token service bất hợp pháp. | Secret manager, rotation, log redaction. |
| Bearer token lộ trong APM | Token replay trước `exp`. | Không capture, sender binding nếu phù hợp, TTL/revoke. |
| Service grant bị revoke nhưng cache cũ | Tiếp tục cấp quyền. | State checks/cache invalidation theo rủi ro. |
| IP nội bộ được coi là user proof | Trust boundary bị vượt. | Authenticated identity provenance, không tin headers tùy tiện. |
| Impersonation không có approval/audit | Không có trách nhiệm giải trình. | Token/policy chuyên biệt, actor/effective subject, timebox. |

## 16. Bảng quyết định: chấp nhận token nào cho hành động nào?

Giả định Resource Server có trust issuer `https://login.example.com`, token profile rõ, và mỗi request đều được kiểm issuer, signature/introspection, audience, thời hạn, scope, principal type và resource policy.

| Tình huống | Quyết định | Vì sao |
|---|---|---|
| `reporting-worker` có service scope `reports:read` tại Beta đọc báo cáo Beta | Có thể cho phép | Đúng service principal, resource/tenant/scope policy. |
| Cùng token đọc báo cáo tenant Anpha chưa được cấp | **Từ chối** | Audience/scope đúng không tự vượt tenant boundary. |
| `reporting-worker` gọi `GET /me/orders` | **Từ chối** | Endpoint có ngữ nghĩa user-only; service không có “me” là user. |
| Service token gửi `X-User-Id=user-742` vào `GET /me/orders` | **Từ chối** | Header do caller cung cấp không tạo user authentication. |
| Service được cấp `support:tickets:assign` để gán ticket cho user-742 | Có thể cho phép | User ID là **target**, actor vẫn là service. |
| User-742 đăng nhập bằng Authorization Code + PKCE và có token `orders:read` | Có thể cho phép với đơn được đọc | User grant hợp lệ, còn phải kiểm object-level permission. |
| Orders Service dùng token `aud=orders-api` tại Payments API | **Từ chối** | Sai audience. |
| Orders Service exchange subject token hợp lệ sang token `aud=payments-api` được AS cho phép | Có thể cho phép | Có delegation/impersonation policy độc lập, RS kiểm token mới. |
| Client credential request thêm `sub=admin` | **Từ chối việc cấp quyền user** | Không có subject user đã được xác minh. |
| Access token JWT ký đúng nhưng `principal_type` không rõ | **Fail closed** ở endpoint phụ thuộc type | Không đoán USER/SERVICE. |
| Opaque token `active=true` nhưng thiếu scope endpoint | **Từ chối** | Active không đồng nghĩa authorized operation. |
| Access token của service còn hạn nhưng client bị disabled | Tùy revocation policy và RS state check; không tự có hiệu lực tức thời | JWT kiểm offline có thể còn được nhận đến hạn. |
| Client ID trùng user `admin` và API lấy `sub=admin` làm quyền admin | **Thiết kế lỗi; phải từ chối không đủ type** | Namespace/subject confusion. |
| Internal mTLS kết nối hợp lệ nhưng caller tự khai `X-User-Id` | Chỉ tin service identity, không tin user identity | Chứng thực máy–máy khác chứng thực user. |
| BFF có phiên user hợp lệ nhưng gửi client credentials token cho endpoint user-only | **Từ chối** | BFF phải dùng user-associated grant/context, không lấy session tự khai thay thế. |

### 16.1. Điều kiện để chấp nhận một service action

~~~text
acceptServiceAction(request):
    verifiedAccessToken.issuer is trusted
    AND verifiedAccessToken.audience includes this API
    AND verifiedAccessToken is active / within validity
    AND principal.type == SERVICE
    AND client_id is allowed for this API
    AND scope allows action
    AND serviceGrant permits target tenant
    AND serviceGrant permits target resource and operation
    AND any sender constraint is satisfied
    AND revocation / policy state is acceptable
~~~

**Không có điều kiện “request.user_id có trong database” là đủ để được hành động như user đó.** Tồn tại user không có nghĩa service được impersonate.

### 16.2. Chọn luồng theo nhu cầu

| Nhu cầu | Luồng/cơ chế đề xuất | Không nên làm |
|---|---|---|
| Cron job đọc báo cáo tổng hợp được cấp cho service | Client Credentials + service scopes/tenant policy. | Giả danh user đã cấu hình cron. |
| Browser người dùng đăng nhập rồi xem đơn | Authorization Code + PKCE/OIDC, user access token, BFF nếu phù hợp. | Client Credentials + `user_id`. |
| Orders API gọi Payments thay user đã được ủy quyền | Token exchange/delegation policy hoặc flow được AS hỗ trợ. | Forward access token sai `aud` hoặc tự sửa `sub`. |
| Back-office support giúp user xử lý ticket | Approval/impersonation hoặc delegation chuyên biệt, actor audit. | `?impersonate=...` tùy ý với service token. |
| Service cập nhật trạng thái job của chính nó | Client Credentials, service-only permission. | Tạo user giả để lách endpoint. |
| Cấp quyền trên dữ liệu doanh nghiệp theo admin consent | Service grant được quản trị + AS/RS policy. | Biến quyền tổ chức thành một user session không có thật. |

## 17. Ma trận kiểm thử an ninh bắt buộc

Chỉ dùng **test clients, test users và tokens giả trong môi trường cô lập**, không dùng client secret hoặc bearer token production.

### 17.1. AS token issuance tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Client Credentials hợp lệ | Confidential client đúng auth, scope/resource được phép | Access token gắn **service principal**, aud/scope đúng. |
| Client secret sai | Gửi Basic sai | Không cấp token, lỗi `invalid_client` hoặc lỗi phù hợp. |
| Client bị disabled | Secret đúng nhưng registration inactive | Không cấp access token mới. |
| Client không được grant `client_credentials` | Xin grant trái registration | `unauthorized_client`/lỗi phù hợp. |
| Public client tự dùng Client Credentials | Client không có confidential authentication | Không được cấp theo Client Credentials Grant. |
| Thêm `user_id=user-admin` | Client credentials request có user ID tự khai | Không tạo user token hoặc subject admin. |
| Thêm `sub=user-742` | Form query có `sub` không đáng tin | Subject vẫn service/được policy chọn; không giả user. |
| Thêm `principal_type=USER` | Caller cố nâng type | AS không copy; từ chối hoặc giữ trusted SERVICE type. |
| Scope vượt grant | Client xin `payments:refund` ngoài grant | Không cấp scope đó. |
| Audience ngoài allowlist | Xin `resource=payments-api` không có quyền | Không cấp token cho Payments. |
| Tenant ngoài service grant | Client xin token/permission cho Anpha | AS giới hạn/từ chối; RS cũng kiểm. |
| Hai client trùng identifier user | Đăng ký client `admin` rồi xin CC token | Mapping/namespace policy không cho service thành user admin. |
| Rate limit | Spam token requests | AS giới hạn theo policy, không lộ secret trong response. |
| Rotate client secret | Secret cũ sau kỳ overlap | Không tiếp tục cấp token bằng secret đã revoke. |

### 17.2. Resource Server authorization tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| User-only endpoint | Service token gọi `/me/orders` | Từ chối. |
| Fake header | Thêm `X-User-Id=user-742` | Không đổi principal thành user. |
| Fake body actor | `{"approvedBy":"admin"}` | Audit actor vẫn là verified SERVICE; policy từ chối nếu thiếu quyền. |
| Target user hợp lệ | Service được cấp gán ticket cho user-742 | Cho phép **gán mục tiêu** nhưng actor là service. |
| Wrong audience | `aud=reports-api` gọi `orders-api` | Từ chối. |
| Wrong scope | Token thiếu permission operation | Từ chối. |
| Wrong tenant | Beta service token thao tác Anpha | Từ chối. |
| BOLA/IDOR | Đổi ID từ report Beta sang report tenant khác | Từ chối. |
| Subject collision | `sub=admin` nhưng type=SERVICE | Không hưởng quyền USER admin. |
| Missing type | Token không có trusted type/profile | Fail closed. |
| JWT wrong issuer | Token ký bởi issuer chưa tin | Từ chối. |
| Invalid signature | Client sửa `sub` của JWT | Từ chối. |
| Expired JWT | `exp` trong quá khứ | Từ chối. |
| Opaque `active=true` | Thiếu `aud`/scope/user context cần thiết | Không chấp nhận sai policy. |
| ID token substitution | OIDC ID token gửi như access token | Từ chối token purpose/audience. |
| DPoP proof không hợp lệ | Sender-bound token thiếu proof | Từ chối. |
| Client bị revoke, token còn hạn | Test theo state/revocation policy thực tế | Không suy đoán revoke có hiệu lực tức thời nếu RS offline. |
| Service-to-user escalation | Service token gọi `/users/admin/change-password` | Chỉ cho phép qua flow/policy admin đặc biệt, mặc định từ chối. |

### 17.3. Delegation/impersonation tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Token exchange hợp lệ | Subject token user tin cậy + actor đủ quyền + aud/scope hợp lệ | AS **có thể** phát delegated token đúng hạn/quyền. |
| Subject token giả | Client tự tạo JSON có `sub=user-admin` | AS từ chối. |
| Client tự chọn subject bất kỳ | `requested_user=user-742` mà không có authorization proof | Không phát delegated user token. |
| Actor không được phép | Service không có exchange grant đến Payments | Từ chối. |
| Forward sai audience | T1 cho Orders gửi thẳng Payments | Payments từ chối. |
| Privileged impersonation không có ticket/approval | Service cố act-as user | Từ chối theo policy. |
| Revoke delegation | Approval/grant đã bị rút | Không phát token mới; RS xử lý token còn hạn theo state policy. |
| Audit actor mismatch | Body nói `approvedBy=user-742` nhưng actor service | Không ghi giả user đã thực hiện. |
| High-risk operation | Token delegated chỉ có scope đọc cố hoàn tiền | Từ chối. |

### 17.4. Pseudocode test có thể tái sử dụng

~~~text
test "client credentials never chooses arbitrary user subject":
    client = registerConfidentialService(
        clientId = "reporting-worker",
        scopes = {"reports:read"}
    )
    token = tokenEndpoint.clientCredentials(
        client = client,
        extraParams = {
            "sub": "user-admin",
            "user_id": "user-742",
            "principal_type": "USER"
        }
    )
    assert token is rejected
           OR token has verified SERVICE subject and policy
    assert token does NOT grant user-admin privileges

test "service bearer denied on user-only endpoint":
    serviceToken = issueValidServiceAccessToken(aud="orders-api")
    response = GET("/me/orders",
                   bearer=serviceToken,
                   headers={"X-User-Id": "user-742"})
    assert response.status in {403, 401}
    assert no user records are exposed

test "service granted for tenant Beta cannot read Anpha":
    token = issueServiceToken(
        client="reporting-worker", scope="reports:read",
        aud="reports-api"
    )
    grantTenant(token.client, "tenant-beta")
    assert GET("/tenants/tenant-anpha/reports",
               bearer=token) is denied
~~~

Pseudocode này không là bài test chạy trực tiếp. Tạo fresh tokens cho mỗi case, xác minh **kết quả cuối tại AS và RS**, không chỉ nhìn response code của một thành phần. Khi policy cho phép bỏ qua custom param, test vẫn phải chứng minh nó **không làm token hoặc quyền bị nâng thành user**.

## 18. Bài tập tình huống có đáp án gợi ý

### Bài 1 — Client hợp lệ nhưng sai mục đích

Dữ kiện:

~~~text
Client: reporting-worker
Grant: client_credentials
Scope: reports:read
Audience: reports-api
Token sub: reporting-worker

API call:
  POST /users/user-742/refunds/refund-81/approve
  X-User-Id: user-742
~~~

**Câu hỏi:** Một JWT hợp lệ có làm request này hợp lệ không?

**Đáp án:** Không. Token thuộc service, đúng audience chỉ ở Reports API, không có bằng chứng user đang phê duyệt hoặc service được quyền approve-refund. Payments/Orders Resource Server phải từ chối do wrong audience/permission/principal type.

### Bài 2 — Service xử lý user ID là target

~~~text
Actor: SERVICE:support-service
Granted scope: support:tickets:assign
Allowed tenant: tenant-beta
Operation: assign ticket-581 to user-742
~~~

**Câu hỏi:** Có được ghi `assigned_by=user-742`?

**Đáp án:** Không nếu user-742 là target. Service có thể thực hiện assignment khi policy cho phép, nhưng audit `assigned_by`/`actor` phải phản ánh service hoặc người vận hành được chứng thực. `assignee_user_id=user-742` là trường mục tiêu.

### Bài 3 — Orders gọi Billing thay user

~~~text
User token T1: sub=user-742, aud=orders-api, scope=orders:read
Orders service token T2: sub=orders-service, aud=billing-api,
                         scope=billing:read
~~~

**Câu hỏi:** Có thể dùng T2 rồi gửi `X-User-Id=user-742` để Billing xem như user-742 không?

**Đáp án:** Không. T2 thể hiện quyền service, không phải delegated user context. Nếu yêu cầu nghiệp vụ là acting on behalf of user, cần subject token hợp lệ và token exchange/delegation được AS/RS hỗ trợ, hoặc cơ chế internal delegation có trust boundary/authorization rõ. T2 có thể đủ cho **service-level billing operation** nếu chính sách đó đúng mục đích, nhưng audit phải phản ánh service actor.

### Bài 4 — Admin consent cấp cho tích hợp SaaS

Tổ chức Beta cấp service grant cho `data-exporter` đọc các báo cáo thuộc Beta qua `reports-api`. Không có user đang đăng nhập khi job chạy.

**Câu hỏi:** Đây có vi phạm câu “không đại diện user tùy ý” không?

**Đáp án:** Không, nếu service hoạt động **dưới quyền riêng đã được tổ chức cấp**, chỉ trong tenant/scope/resource được phép, và audit theo service principal. Không được giả rằng một cá nhân cụ thể vừa phê duyệt từng lần chạy.

### Bài 5 — Cùng chuỗi `sub` ở user và service

Issuer có user `admin`, và một client đăng ký `client_id=admin`. Service token `sub=admin` được dùng vào endpoint `/admin/users`; RS chỉ tra database bằng `sub` rồi cấp admin role.

**Câu hỏi:** Lỗi nằm ở đâu?

**Đáp án:** **Principal namespace/subject confusion**. RS đã không phân biệt user/service identity theo issuer/token profile. Cần typed principal và policy fail closed, đồng thời quản trị client ID namespaces. Không thể dựa vào chuỗi `sub` để suy ra token là user.

### Bài 6 — Token bị lộ trong trace

Một APM ghi `Authorization: Bearer SERVICE_TOKEN` của `reporting-worker`. Token còn hạn 10 phút và service có quyền đọc nhiều báo cáo.

**Câu hỏi:** Vì sao vẫn nghiêm trọng nếu token không thể giả user?

**Đáp án:** Kẻ giữ bản sao vẫn có thể **lạm dụng quyền dịch vụ** trong audience/scope/tenant token cho phép; nếu client secret còn bị lộ, có thể xin token mới. Ngăn ghi tiếp, đánh giá revoke/state/TTL/sender binding, điều tra access và siết least privilege.

## 19. Checklist thiết kế và triển khai

- [ ] Định nghĩa rõ Client Credentials Grant là quyền **của OAuth client/service**, không chứng minh user đang đăng nhập.
- [ ] Phân biệt OAuth Client, Resource Owner, Authorization Server, Resource Server, service principal và end-user principal.
- [ ] Confidential client được xác thực bằng method đã đăng ký; không coi `client_id` là secret.
- [ ] AS không lấy `sub`, `user_id`, `act_as` hoặc `principal_type=USER` trực tiếp từ Client Credentials request.
- [ ] AS kiểm client/grant, scope, resource/audience, TTL, client status và service tenant grant.
- [ ] User và service IDs có namespace/typing rõ, tránh collisions và token subject confusion.
- [ ] JWT/opaque access token được Resource Server kiểm issuer, audience, expiry, token purpose, scope và principal type.
- [ ] User-only endpoints từ chối service token, kể cả khi có `X-User-Id`/body chứa user ID.
- [ ] Service-only endpoints kiểm service permissions và tenant/resource/operation cụ thể, không chỉ scope tổng quát.
- [ ] Resource Server chống BOLA/IDOR bằng kiểm ownership/ACL/tenant policy cho từng bản ghi.
- [ ] User ID trong request được xử lý như **target data** nếu nghiệp vụ cần, không thay security principal.
- [ ] Nhu cầu user-present sử dụng Authorization Code + PKCE/OIDC và access token đúng audience.
- [ ] Delegation/on-behalf-of có subject token/grant/actor được AS kiểm, không tự giả user bằng client credentials.
- [ ] Impersonation đặc quyền có approval, scope/timebox, actor audit, revoke và step-up khi cần.
- [ ] Audit phân biệt actor, effective subject, target user, configured-by và authorization mode.
- [ ] Client secret/private key/cert được bảo vệ ở secret manager/HSM/KMS, rotation/revocation và least privilege.
- [ ] Không ghi raw access/refresh token, client secret, Basic header, JWT assertion hoặc DPoP proof vào log/trace.
- [ ] Access token có TTL/scopes/audiences tối thiểu; sender binding khi phù hợp threat model.
- [ ] Thu hồi client/service grant và thu hồi JWT/opaque access token có chiến lược phù hợp khả năng AS/RS.
- [ ] Không phát refresh token như mặc định của Client Credentials Grant; xin access token mới bằng client auth khi cần.
- [ ] Có negative tests cho giả `sub`, `X-User-Id`, sai principal type, tenant, audience, scope và quyền đối tượng.
- [ ] Khi không đủ bằng chứng xác thực/ủy quyền, hệ thống **fail closed**.

**Ghi nhớ:** **Client Credentials Grant chứng minh danh tính OAuth client và cấp quyền máy–máy**, không mặc định đại diện cho bất kỳ người dùng cuối nào. `client_id` hoặc một client secret hợp lệ **không trao quyền chọn `sub`, giả user hay vượt tenant**. Nếu một service cần hành động hợp lệ thay user, dùng user-associated authorization/delegation được AS xác minh; nếu chỉ cần làm việc tự động, hãy cấp **service permissions riêng** và audit đúng actor. Resource Server phải kiểm **issuer, audience, scope, principal type, tenant và quyền trên từng tài nguyên**, không chỉ thấy bearer token hợp lệ rồi tin mọi header/body.

## 20. Tài liệu chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** `4.4` Client Credentials Grant, confidential client, access token/refresh token và bốn vai trò OAuth.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer credential và nguy cơ replay khi bị lộ.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** claims `iss`, `sub`, `client_id`, `aud`, `scope`; ngữ nghĩa subject với Client Credentials.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `nbf` và issuer-specific claims.
- **RFC 8725 — JSON Web Token Best Current Practices:** issuer/audience validation, algorithm confusion, token-substitution defense.
- **RFC 7662 — OAuth 2.0 Token Introspection:** metadata và trạng thái của opaque access token.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** giới hạn resource/audience của access token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** `subject_token`, `actor_token`, delegation, impersonation và `act`.
- **RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT assertions và xác thực client, khác user identity tự khai.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ authorization code khi người dùng hiện diện.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoke token/grant tại Authorization Server.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained access tokens.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client auth/token binding.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth authorization flows, public/confidential clients và chống lạm dụng token.
- **OpenID Connect Core 1.0:** ID token và user authentication, không phải service impersonation.
- **OWASP API Security Top 10:** Broken Object Level Authorization (BOLA), Broken Function Level Authorization và tenant/resource authorization.
- **OWASP OAuth 2.0 Cheat Sheet / Secrets Management Cheat Sheet:** client secrets, token storage, audience/scope và logging.
- **Spring Security OAuth2 Resource Server / Spring Authorization Server Reference:** JWT validation, `RegisteredClient`, service client registration và authorization policy.



