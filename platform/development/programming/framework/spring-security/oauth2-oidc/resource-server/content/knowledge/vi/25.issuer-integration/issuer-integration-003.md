# Client dành cho người dùng và client máy gọi có thể nhận claims khác nhau

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, cùng một Authorization Server (AS) có thể phát **access token khác cấu trúc claims** cho hai nhóm ứng dụng:

1. **Client phục vụ người dùng**: web application, BFF, ứng dụng mobile hoặc SPA dùng OAuth 2.0 Authorization Code + PKCE để truy cập API theo quyền được cấp liên quan đến một người dùng.
2. **Client máy gọi**: backend job, batch processor, cron worker hoặc một dịch vụ khác dùng `client_credentials` để gọi API theo quyền của chính ứng dụng, **không có một end-user trực tiếp trong luồng cấp token**.

Một token dành cho người dùng có thể chứa `sub` của người dùng, thông tin profile và scope như `orders.read`. Một token máy gọi có thể chứa `client_id`, subject của service application và scope như `orders.import`, nhưng không có `email`, `preferred_username` hoặc một hồ sơ người dùng thật.

> **Điểm cốt lõi:** Resource Server không được giả định **mọi access token đều đại diện con người** hoặc **mọi token đều có cùng claims**. Cần xác minh token, hiểu hợp đồng phát hành của AS, phân biệt subject người dùng với identity của ứng dụng, rồi áp dụng quyền theo đúng loại caller.

Bài học thuộc phần **Tích hợp nhà phát hành**: làm thế nào phối hợp với Authorization Server/Identity Provider để nhận đúng claims cho từng OAuth client; cấu hình Spring Security Resource Server để xác minh, chuyển claims thành principal/authorities, từ chối những token sai mục đích và bảo vệ dữ liệu theo tenant/ownership. Các mẫu code dùng Java 17+, Spring Boot và **Spring Security Servlet/Spring MVC**; phiên bản WebFlux có API tương ứng nhưng không thể sao chép nguyên.

## 1. Trước hết, phân biệt bốn khái niệm

Nhầm lẫn thường gặp là dùng từ *client*, *user*, *subject* và *principal* như một.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **OAuth client** | Ứng dụng đã đăng ký với AS, có `client_id` | `storefront-web`, `inventory-sync` |
| **Resource owner/end-user** | Chủ thể người dùng trong flow có ủy quyền từ con người | Người dùng `person-42` |
| **Access token subject** | Đối tượng được biểu diễn bởi claim `sub` theo token profile của AS | `person-42` hoặc `svc-inventory` |
| **Authenticated principal ở API** | Identity Spring Security tạo **sau khi token được xác minh** | `JwtAuthenticationToken` hoặc `BearerTokenAuthentication` |
| **Scope** | Phạm vi OAuth authorization được AS cấp | `orders.read`, `orders.import` |
| **Application role/permission** | Quyền nghiệp vụ do hệ thống có thẩm quyền quản lý | `ORDER_APPROVER`, `orders.export` |
| **Grant type** | Cơ chế client dùng để nhận access token | `authorization_code`, `client_credentials` |
| **Token type/profile** | Định dạng và mục đích của credential | JWT access token, opaque access token, OIDC ID token |

**Một OAuth client dành cho người dùng không phải bản thân người dùng.** Hàng nghìn người có thể đăng nhập qua cùng `client_id=storefront-web`; phân quyền từng người dựa vào subject và entitlement phù hợp, không chỉ client ID.

**Một machine client không mặc nhiên là administrator.** Việc một backend giữ client secret hoặc private key chỉ giúp nó xác thực với AS để xin token theo những grant/scope được cấp. API phải tiếp tục giới hạn quyền của token.

### 1.1. Client type không tự cho biết grant type của mỗi token

Client đăng ký có thể là public client (SPA/mobile) hoặc confidential client (backend). Một confidential web app có thể dùng Authorization Code cho người dùng **và** một số hệ thống cho phép cùng client dùng grant khác theo cấu hình.

Bởi vậy:

~~~text
client_id=orders-backend
```

**không đủ** để suy ra token đang đại diện end-user hay backend service. Phải có contract phát hành token nói rõ cách nhận biết token purpose/grant và cách AS thiết lập claims. Không lấy `client_id` làm bằng chứng duy nhất khi một client có thể nhận cả user-token và service-token.

## 2. Hai luồng OAuth 2.0 khác nhau

### 2.1. Authorization Code + PKCE: có người dùng tham gia

~~~text
Người dùng
   |
   v
Web/Mobile/SPA OAuth Client
   |
   | Authorization request, PKCE, state
   v
Authorization Server / OIDC Provider
   |
   | Xác thực người dùng, consent/policy nếu cần
   |
   v
Authorization Code
   |
   | Client đổi code với code_verifier
   v
Access Token dành cho Orders API
   |
   | Authorization: Bearer <access-token>
   v
Spring Security Resource Server
   |
   | Verify JWT hoặc introspect opaque token
   v
Authenticated USER principal + authorities
   |
   v
Kiểm tra scope + tenant + order ownership
~~~

Với OIDC login, client thường còn nhận **ID token** để biết kết quả xác thực người dùng. Nhưng **Orders Resource Server** phải tiêu thụ **access token đúng audience**, **không** lấy ID token của OIDC làm API credential chỉ vì nó cũng là JWT.

Trong một flow có user, `sub` của access token thường mang ý nghĩa người dùng theo AS contract. `client_id` vẫn cho biết ứng dụng nào đã nhận/request token.

### 2.2. Client Credentials: không có user đang login trong grant

~~~text
Scheduled Import Worker
   |
   | Xác thực chính nó (client secret / private_key_jwt / mTLS ...)
   | grant_type=client_credentials
   v
Authorization Server Token Endpoint
   |
   | Kiểm tra danh tính client, allowed scopes/audience/policy
   v
Access Token đại diện ứng dụng/khả năng của client
   |
   | Authorization: Bearer <access-token>
   v
Spring Security Resource Server
   |
   | Verify JWT hoặc introspect opaque token
   v
Authenticated SERVICE principal + authorities
   |
   v
Kiểm tra scope import + tenant/service ACL
~~~

**Không có bước end-user đăng nhập** trong chính grant `client_credentials`. RFC 6749 mô tả client thường hành động thay mặt chính nó, hoặc theo một ủy quyền đã được thiết lập trước với AS.

Điều này **không cấm** AS triển khai một service-account identity nội bộ. Nhưng service account được gán `sub` không có nghĩa một người đang ngồi trước màn hình hay đã đồng ý cho truy cập dữ liệu riêng tư của họ.

### 2.3. Hai HTTP token requests minh họa

Với client phục vụ người dùng, OAuth2 Authorization Code flow (sau khi đã được redirect/cấp code) có bước đổi code:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
client_id=storefront-web&
code_verifier=PKCE_VERIFIER
~~~

Đây là ví dụ khái niệm. Client authentication còn tùy public/confidential client; confidential BFF có thể phải xác thực thêm theo cách AS quy định. Không đưa client secret vào SPA/mobile.

Với client máy gọi:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64-client-credentials>

grant_type=client_credentials&
scope=orders.import&
resource=https%3A%2F%2Fapi.example.com%2Forders
~~~

`resource` ở đây minh họa RFC 8707 Resource Indicators; AS chỉ hỗ trợ nếu đã cấu hình. Phương thức client authentication có thể là Basic, `private_key_jwt` hoặc mTLS tùy AS; không có một cơ chế bắt buộc cho mọi triển khai.

**Mục đích:** AS phải xác định **client nào**, **grant nào**, **tài nguyên nào** và **quyền nào** trước khi phát token. Resource Server không được tự suy diễn những thông tin này từ request URL hoặc tên ứng dụng.

## 3. Hai access tokens hợp lệ có thể rất khác nhau

Giả sử AS và Orders API đã thống nhất một **custom claim**:

~~~text
caller_kind = "user" | "service"
```

Claim này **không phải trường bắt buộc theo OAuth 2.0 hoặc RFC 9068**; nó là hợp đồng riêng, phải được AS thiết lập từ grant/client/token policy đáng tin cậy, **không** được lấy từ dữ liệu profile user có thể tự sửa.

### 3.1. Access token khi người dùng đang gọi API

Header JWT ví dụ:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-key-1"
}
~~~

Payload ví dụ:

~~~json
{
  "iss": "https://login.example.com/realms/orders",
  "sub": "person-42",
  "aud": ["orders-api"],
  "client_id": "storefront-web",
  "caller_kind": "user",
  "scope": "orders.read orders.create",
  "preferred_username": "mai",
  "email": "mai@example.test",
  "tenant_id": "tenant-a",
  "exp": 2000000300,
  "iat": 2000000000
}
~~~

Đây chỉ là một **payload mẫu**, không phải AS nào cũng phát profile claims trong **access token**. `preferred_username`, `email`, `tenant_id` và `caller_kind` ở đây là thuộc tính có thể phụ thuộc client scopes, mappers và policy của AS.

Ngay cả khi email có mặt, nó không tự chứng minh địa chỉ đã verified hoặc user là admin. Tùy OIDC/AS contract, cần xem riêng `email_verified` nếu thực sự phải xử lý tính xác thực email, và cũng **không dùng email_verified để tự cấp quyền nghiệp vụ**.

### 3.2. Access token khi máy gọi API

Header vẫn có thể là:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-key-1"
}
~~~

Payload:

~~~json
{
  "iss": "https://login.example.com/realms/orders",
  "sub": "svc:inventory-sync",
  "aud": ["orders-api"],
  "client_id": "inventory-sync",
  "caller_kind": "service",
  "scope": "orders.read orders.import",
  "tenant_id": "tenant-a",
  "exp": 2000000300,
  "iat": 2000000000
}
~~~

Token này không có `email` hoặc `preferred_username` của end-user. Điều đó **bình thường** với một token đại diện ứng dụng.

Một số AS có thể dùng `sub=inventory-sync`, một số dùng `sub` là service-account ID, một số dùng subject theo profile riêng. **Không được giả định `sub == client_id` trong mọi implementation.** RFC 9068 khuyến nghị `sub` của token không có resource owner (như `client_credentials`) tương ứng định danh client application theo cách AS quản lý, nhưng AS cụ thể có thể có profile khác.

### 3.3. Bảng so sánh claims

| Claim | Token người dùng | Token máy gọi | Điều Resource Server cần biết |
|---|---|---|---|
| `iss` | Issuer của AS | Issuer của AS | Phải thuộc tập trusted issuers |
| `sub` | Thường là end-user subject | Thường là app/service subject | Không giả định luôn là con người |
| `client_id` | OAuth client ứng dụng phục vụ user | OAuth machine client | Không tự chỉ ra grant type |
| `aud` | Orders API | Orders API | **Cả hai** phải đúng intended resource |
| `scope`/`scp` | Scopes được cấp theo user/client policy | Scopes được cấp theo client policy | Không tự thêm scopes khi thiếu |
| `caller_kind` (tùy biến) | `user` | `service` | Chỉ tin nếu được AS quản lý theo contract |
| `email` | Có thể có hoặc không | Thường không có end-user email | Không dùng làm role |
| `preferred_username` | Có thể có | Có thể vắng hoặc là service-account name | Không dùng làm identity proof |
| `groups`/`roles` | Tùy cấu hình/entitlement | Có thể là application roles khác | Cần mapper/allowlist và nguồn có thẩm quyền |
| `tenant_id` (tùy biến) | Tenant liên quan user | Tenant được client cấp quyền | Không tự chứng minh quyền trên mọi object |
| `azp` | Một số profiles, đặc biệt OIDC ID token | Không phổ quát | Không thay `client_id` một cách mù quáng |
| `gty`/`grant_type` | Có thể là vendor extension | Có thể là vendor extension | **Không phải claim luôn có trong access token** |
| `act` | Có thể có trong token-exchange delegation | Có thể có khi một dịch vụ hành động thay người dùng | Chỉ hiểu theo RFC 8693/AS contract |
| `exp`/`nbf`/`iat` | Thời gian token | Thời gian token | Validate như nhau theo token profile |

Quan trọng: **OAuth grant type trong token request không bắt buộc phải được nhúng vào JWT access token**. Nếu ứng dụng cần một dấu hiệu caller kind, hãy yêu cầu AS phát một claim được xác định trong contract và ràng buộc nó với thông tin grant đã kiểm tra; hoặc thiết kế token profiles/clients tách biệt thật sự.

## 4. `sub`, `client_id` và principal không phải cùng một field

Có ba lỗi identity phổ biến.

### 4.1. Dùng `client_id` để nhận diện user

Giả sử:

~~~text
client_id = storefront-web
sub       = person-42
```

Một người khác cũng dùng cùng ứng dụng:

~~~text
client_id = storefront-web
sub       = person-99
```

Nếu lưu owner của order bằng `client_id`, mọi user trên `storefront-web` có thể bị gom vào một identity. **Không dùng `client_id` thay cho user subject**.

### 4.2. Dùng `sub` làm khóa người dùng mà không xét loại caller

Giả sử token máy gọi:

~~~text
sub       = svc:inventory-sync
client_id = inventory-sync
```

Spring Security JWT mặc định thường đặt `Authentication#getName()` dựa trên `sub`. Nếu service truy vấn `users.findById(authentication.getName())`, nó có thể:

- Không tìm thấy user.
- Tạo “ghost user”/service account ngoài chủ đích.
- Lẫn quyền của người với máy.
- Bỏ qua điều kiện “user phải là owner” bằng tài khoản service.

**Giải pháp:** mô hình hóa riêng `HumanCaller` và `ServiceCaller` hoặc một domain identity có `kind` được xác minh.

### 4.3. Dùng `sub` mà bỏ issuer

~~~text
Issuer A: sub = person-42
Issuer B: sub = person-42
```

Hai subjects đó không tự cùng một người. Với multi-issuer, canonical external identity thường là **`(iss, sub)`**, hoặc ánh xạ cặp này sang user ID nội bộ qua một directory đáng tin.

Token máy gọi cũng cần namespace issuer/client. Đừng dùng mỗi `client_id` làm khóa global nếu cùng client ID có thể tồn tại tại nhiều AS.

## 5. OAuth2 access token khác OIDC ID token

Cần phân biệt kỹ ba tài liệu/token surfaces:

| Surface | Đối tượng tiêu thụ chính | Nội dung/ý nghĩa |
|---|---|---|
| **Access token** | Resource Server/API | Quyền truy cập tài nguyên; `aud` và scopes |
| **OIDC ID token** | OIDC client/Relying Party | Kết quả authentication của end-user, issuer/sub/audience của client |
| **UserInfo response** | OIDC client đã có access token phù hợp | Claims profile người dùng theo OIDC |

Ví dụ một OIDC ID token:

~~~json
{
  "iss": "https://login.example.com/realms/orders",
  "sub": "person-42",
  "aud": "storefront-web",
  "name": "Mai",
  "email": "mai@example.test",
  "exp": 2000000300
}
~~~

Trong khi access token dành cho API phải có `aud=orders-api` hoặc resource indicator đúng contract.

**Không được dùng ID token làm bearer credential cho Orders API** chỉ vì nó có `sub`, `email` và chữ ký hợp lệ. `openid profile email` là các scopes/claims của **OIDC identity flow**, không mặc nhiên là permission đọc/ghi orders.

Máy dùng `client_credentials` không có một end-user đang login trong grant, nên **thông thường không có OIDC ID token của người dùng**. Nếu AS phát các loại token đặc biệt trong flow khác, phải xác định mục đích và profile riêng; không suy luận từ định dạng JWT.

## 6. Vì sao AS phát claims khác nhau?

Nhiều IdP/Authorization Server có chính sách claim publication phụ thuộc:

1. **Grant flow:** có user đang authenticate hay chỉ client credentials?
2. **Registered OAuth client:** client nào được cấp scope/audience/profile nào?
3. **Consent và authorization:** người dùng hay client được phép truy cập gì?
4. **Client scope và protocol mapper:** những trường nào được đưa vào access token, ID token và UserInfo?
5. **Resource/`audience`:** API đích cần những claims nào?
6. **Assigned roles/permissions:** vai trò user khác service-account/application roles.
7. **Token lifetime và issuer policy:** môi trường, client assurance level, token type.
8. **Privacy/data minimization:** API không cần tên/email thì AS có thể không gửi.
9. **Tenant context:** một user hoặc workload có thể được cấp phạm vi tenant riêng.
10. **Token format:** JWT access token chứa claims trong payload; opaque token chỉ lộ thông tin qua introspection contract.

### 6.1. Mapping ở AS cần được thiết kế theo token mục đích

Ví dụ một policy hợp lý:

~~~text
Client: storefront-web
Grant: authorization_code
User present: yes
Audience: orders-api
Claims in access token:
  iss, sub(user), aud, client_id, scope, caller_kind=user
  tenant_id if authorized
  optional profile claims only if needed

Client: inventory-sync
Grant: client_credentials
User present: no
Audience: orders-api
Claims in access token:
  iss, sub(service/application), aud, client_id, scope,
  caller_kind=service, tenant_id if authorized
  no end-user profile attributes
~~~

Bảng này là **hợp đồng minh họa**, không có một cấu hình chuẩn duy nhất áp dụng cho Keycloak, Entra ID, Auth0, Okta, Spring Authorization Server hoặc IdP khác. Mỗi nhà phát hành có cách cấu hình claim mapping riêng.

### 6.2. Service account role khác role người dùng

Một số IdP có khái niệm **service account** liên kết với OAuth client máy. Quyền cấp cho service account có thể xuất hiện trong claim `roles`, `realm_access`, `resource_access` hoặc namespace khác theo vendor.

Không được đọc:

~~~json
{
  "roles": ["realm-admin"]
}
~~~

rồi tự chuyển thành `ROLE_ADMIN` của Orders API trừ khi đây đúng là **role có thẩm quyền trên API này** và contract cho phép. Một role quản trị IdP hoặc quản trị client khác không đồng nghĩa quyền duyệt refund.

### 6.3. Claim `gty`/`grant_type` không phải tiêu chuẩn universal

Một số AS nhúng loại grant hoặc token purpose vào JWT, ví dụ:

~~~json
{
  "gty": "client-credentials"
}
~~~

Nhưng tên claim và giá trị có thể là **vendor-specific**. Không xây security code giả định mọi JWT OAuth2 đều chứa `grant_type=client_credentials`. Nếu cần phân loại, định nghĩa claim được AS kiểm soát hoặc dùng token profile đã được kiểm chứng.

## 7. Thiết kế contract claims trước khi viết Java code

Một Resource Server có thể yêu cầu AS đáp ứng contract:

| Điều kiện | User token | Machine token |
|---|---|---|
| Issuer | Cùng issuer hoặc allowlist | Cùng issuer hoặc allowlist |
| Audience | `orders-api` | `orders-api` |
| Token type | OAuth access token, không phải ID token | OAuth access token |
| `sub` | Subject người dùng ổn định | Service/app subject ổn định theo AS |
| `client_id` | Một trong các user-facing clients đã duyệt | Một trong machine clients đã duyệt |
| `caller_kind` | `user` do AS thiết lập | `service` do AS thiết lập |
| Scopes | `orders.read`, `orders.create` tùy policy | `orders.import`, `orders.read` tùy policy |
| Optional profile claims | Có thể có | Không bắt buộc; thường vắng |
| Tenant claim | Chỉ nếu AS có thẩm quyền | Chỉ nếu AS có thẩm quyền |
| Không có claim bắt buộc | **Reject** | **Reject** |
| Unknown role/permission | Không map thành quyền | Không map thành quyền |

**Đặc biệt:** `caller_kind` phải được AS suy ra từ **grant/client authentication/token issuance context** mà client không thể tự thay đổi. Nếu client có quyền viết custom user attribute `caller_kind=service`, claim đó không đủ đáng tin để phân loại.

### 7.1. Nên có nguồn thẩm quyền cho tenant và role

Một user có thể thuộc tenant A và tenant B; một machine client có thể chỉ được nhập inventory của tenant A. `tenant_id` trong access token có thể dùng nếu AS thực sự quản lý membership/delegation. Nếu quyền tenant nằm ở database của Orders API, token claim chỉ là input định danh và phải được đối chiếu với ACL hiện tại.

### 7.2. Không bắt machine token có email

Sai:

~~~java
// SAI: machine token hợp lệ không nhất thiết có email.
String email = jwt.getClaimAsString("email");
if (email == null) {
    throw new BadCredentialsException("Missing email");
}
~~~

Đây có thể gây 401 hàng loạt cho service clients dù token đúng issuer/audience. **Đồng thời** cũng không được vì thiếu email mà chuyển sang một admin role mặc định.

Đúng hơn là yêu cầu các claims cần thiết cho **loại caller đã xác minh**:

~~~text
User token -> yêu cầu human sub, caller_kind=user, user client đúng
Machine token -> yêu cầu service identity, caller_kind=service, client_id đúng
```

## 8. Spring Security Resource Server xác thực những gì?

Một JWT bearer request thường đi theo:

~~~text
Authorization: Bearer <JWT>
            |
            v
BearerTokenAuthenticationFilter
            |
            v
JwtAuthenticationProvider
            |
            v
JwtDecoder
  - verify signature / public key
  - validate issuer
  - validate audience
  - validate exp, nbf
  - validate token profile/type as configured
            |
            v
JwtAuthenticationConverter
  - scopes -> SCOPE_*
  - custom caller-kind -> CALLER_USER / CALLER_SERVICE
            |
            v
JwtAuthenticationToken
            |
            v
SecurityContextHolder
            |
            v
HTTP + method + business authorization
~~~

Spring Security mặc định thường:

- Xác minh JWT bằng `JwtDecoder` đã cấu hình.
- Ánh xạ `scope` hoặc `scp` sang authorities `SCOPE_*`.
- Đặt `Authentication#getPrincipal()` là một `Jwt`.
- Đặt `Authentication#getName()` theo `sub` nếu có.

Nó **không tự hiểu** custom claim `caller_kind`, không phân loại human/service theo email, và không tự ánh xạ mọi `roles`/`groups` của IdP thành authorities.

Các customization của ví dụ tiếp theo có ba lớp:

1. **`JwtDecoder` validators**: reject token sai issuer/audience/caller contract.
2. **`JwtAuthenticationConverter`**: tạo marker authority `CALLER_USER` hoặc `CALLER_SERVICE` từ token đã xác minh và hợp đồng phát hành.
3. **HTTP/service authorization**: phân quyền endpoint theo scope và caller kind, rồi kiểm tra tenant/ownership.

## 9. Cấu hình JWT Resource Server cho hai loại caller

Giả sử AS đã cam kết:

- Public issuer: `https://login.example.com/realms/orders`.
- Orders API là audience `orders-api`.
- Chữ ký access token dùng RS256 với JWK Set do AS quản trị.
- JWT access token có `sub`, `client_id`, `caller_kind`.
- `caller_kind=user` chỉ được phát cho các client user-facing đã duyệt.
- `caller_kind=service` chỉ được phát cho các machine clients đã duyệt.
- Không nhận một token loại khác bằng cách tự dự đoán.
- `caller_kind` và `client_id` do AS cấp trong token **đã được ký**, không do request header tự khai.

### 9.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Với Spring Boot starter, module Resource Server và JOSE/JWT cần thiết được quản lý theo BOM. Không phối trộn các Spring Security versions ngoài ý muốn.

### 9.2. Config values

~~~yaml
app:
  security:
    issuer: https://login.example.com/realms/orders
    jwk-set-uri: https://login.example.com/realms/orders/certs
    audience: orders-api
~~~

Đây là **namespace config do ứng dụng minh họa định nghĩa**, không phải auto-configuration properties của Spring Boot.

### 9.3. Validator dành riêng cho caller contract

Tạo một validator kiểm tra `caller_kind`, `client_id`, `sub` trên một JWT mà decoder đã verify chữ ký. Validator này **không được dùng để thay** các validators issuer, time hoặc audience.

~~~java
package com.example.orders.security;

import java.util.Set;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class CallerContractValidator
        implements OAuth2TokenValidator<Jwt> {

    private static final Set<String> USER_CLIENTS =
        Set.of("storefront-web", "orders-mobile");

    private static final Set<String> SERVICE_CLIENTS =
        Set.of("inventory-sync", "fulfillment-worker");

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String kind = jwt.getClaimAsString("caller_kind");
        String clientId = jwt.getClaimAsString("client_id");
        String subject = jwt.getSubject();

        if (subject == null || subject.isBlank()
                || clientId == null || clientId.isBlank()) {
            return invalid();
        }

        boolean isApprovedUser =
            "user".equals(kind) && USER_CLIENTS.contains(clientId);

        boolean isApprovedService =
            "service".equals(kind)
                && SERVICE_CLIENTS.contains(clientId);

        if (!isApprovedUser && !isApprovedService) {
            return invalid();
        }

        return OAuth2TokenValidatorResult.success();
    }

    private static OAuth2TokenValidatorResult invalid() {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Caller token contract is not satisfied",
                null
            )
        );
    }
}
~~~

**Giới hạn quan trọng:** Allowlist client IDs là **policy ví dụ** và không phải thứ duy nhất xác minh grant. Nó có tác dụng vì **AS contract đã khẳng định** `caller_kind` được ràng buộc với issuance flow thật. Nếu một client được phép nhận **cả user token và service token**, hoặc AS không thể bảo đảm `caller_kind` đáng tin, validator này chưa đủ để chứng minh loại caller; cần profile/issuer policy chặt hơn.

### 9.4. Kết hợp issuer, audience, time và caller validators

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator,
                new CallerContractValidator()
            )
        );

        return decoder;
    }
}
~~~

Đoạn này giữ checks về issuer/time mặc định và thêm audience/caller contract. Nếu profile thực tế yêu cầu **JWT access token type `at+jwt`** theo RFC 9068, cần áp dụng **type/profile validator tương ứng phiên bản Spring Security**; không thay toàn bộ validations bằng một kiểm tra `caller_kind`.

**Đặc biệt:** `client_id` đúng không làm một JWT sai chữ ký trở thành hợp lệ. Việc signature verification của `NimbusJwtDecoder` phải thành công trước khi claim authorization được dùng.

## 10. Map scope và caller kind thành GrantedAuthority

Nếu JWT có:

~~~json
{
  "scope": "orders.read",
  "caller_kind": "user"
}
~~~

Spring Security mặc định tạo `SCOPE_orders.read`, nhưng không có `CALLER_USER`. Một converter có thể giữ scope authorities và thêm **marker ứng dụng** từ contract đã xác minh.

### 10.1. Converter cho JWT đã xác minh

~~~java
package com.example.orders.security;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class CallerAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final JwtGrantedAuthoritiesConverter scopeConverter =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        List<GrantedAuthority> authorities = new ArrayList<>();

        Collection<GrantedAuthority> scopes =
            scopeConverter.convert(jwt);

        if (scopes != null) {
            authorities.addAll(scopes);
        }

        String kind = jwt.getClaimAsString("caller_kind");

        if ("user".equals(kind)) {
            authorities.add(
                new SimpleGrantedAuthority("CALLER_USER"));
        } else if ("service".equals(kind)) {
            authorities.add(
                new SimpleGrantedAuthority("CALLER_SERVICE"));
        }

        return authorities;
    }
}
~~~

`CALLER_USER` và `CALLER_SERVICE` là **marker authorities do API tự quy ước**, không phải OAuth scopes và không phải role mặc định của Spring Security.

**Không thêm `SCOPE_orders.import` chỉ vì `caller_kind=service`.** Quyền import vẫn phải được AS cấp thật qua `scope`/entitlement nguồn có thẩm quyền. Caller kind xác định loại chủ thể, không đồng nghĩa quyền nghiệp vụ.

### 10.2. Đăng ký JwtAuthenticationConverter

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Configuration
public class JwtAuthenticationMappingConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(
            new CallerAuthoritiesConverter()
        );

        return converter;
    }
}
~~~

Các `scope` authorities vẫn được giữ nhờ `JwtGrantedAuthoritiesConverter`. Nếu một triển khai tự thay danh sách bằng **chỉ `CALLER_USER`**, API cần `SCOPE_orders.read` sẽ bị 403 dù AS thực sự cấp quyền đọc.

### 10.3. Tại sao converter chỉ nên chạy sau validation?

Một converter được cấu hình cho Resource Server nhận `Jwt` do decoder xác minh. Nhưng đừng tự gọi converter với một JWT object tự dựng từ Base64 payload rồi xem authorities nhận được là bằng chứng đã authenticated.

**Sự tin cậy bắt đầu từ decoder**: chữ ký, issuer, audience, timestamp và caller contract đã được kiểm tra. Converter chỉ ánh xạ cách biểu diễn quyền đó thành tên authority của ứng dụng.

## 11. Bảo vệ HTTP endpoint theo loại caller **và** scope

Thiết kế minh họa:

| Endpoint | Ai được gọi | Quyền bắt buộc |
|---|---|---|
| `GET /api/me` | User token | `CALLER_USER` + `SCOPE_profile.read` |
| `GET /api/orders/**` | User hoặc service | `SCOPE_orders.read` + business policy |
| `POST /api/orders/**` | User token | `CALLER_USER` + `SCOPE_orders.create` |
| `POST /api/import/jobs` | Machine token | `CALLER_SERVICE` + `SCOPE_orders.import` |
| `/api/admin/**` | Policy riêng đã phê duyệt | Không mở chỉ vì client credentials |
| URL khác | Không caller nào | `denyAll()` |

### 11.1. Dùng AuthorizationManagers.allOf

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        AuthorizationManager<RequestAuthorizationContext> humanReadProfile =
            AuthorizationManagers.allOf(
                AuthorityAuthorizationManager.hasAuthority("CALLER_USER"),
                AuthorityAuthorizationManager.hasAuthority(
                    "SCOPE_profile.read")
            );

        AuthorizationManager<RequestAuthorizationContext> humanCreateOrder =
            AuthorizationManagers.allOf(
                AuthorityAuthorizationManager.hasAuthority("CALLER_USER"),
                AuthorityAuthorizationManager.hasAuthority(
                    "SCOPE_orders.create")
            );

        AuthorizationManager<RequestAuthorizationContext> machineImport =
            AuthorizationManagers.allOf(
                AuthorityAuthorizationManager.hasAuthority("CALLER_SERVICE"),
                AuthorityAuthorizationManager.hasAuthority(
                    "SCOPE_orders.import")
            );

        return http
            // Ví dụ API chỉ xác thực bằng bearer header.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .access(humanReadProfile)

                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .access(humanCreateOrder)

                .requestMatchers(HttpMethod.POST, "/api/import/jobs")
                    .access(machineImport)

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Ví dụ này phân quyền **coarse-grained ở HTTP layer**, chưa giải quyết ownership/tenant khi service trả dữ liệu. `SCOPE_orders.read` được cấp cho cả user và machine token **chỉ nếu** hai loại token có contract cho phép cùng hành động, trong phạm vi tài nguyên phù hợp.

Đoạn code tắt CSRF **chỉ vì giả định API thuần bearer header**, không dùng cookie tự gửi để xác thực. Nếu ứng dụng dùng browser session, BFF, cookie access token hoặc form login, phải đánh giá CSRF riêng.

### 11.2. Vì sao kiểm tra marker và scope cùng lúc?

Nếu rule chỉ là:

~~~java
.requestMatchers(HttpMethod.POST, "/api/import/jobs")
    .hasAuthority("SCOPE_orders.import")
~~~

thì một user token được AS vô tình cấp scope `orders.import` cũng có thể qua tầng HTTP. Điều đó có thể đúng hoặc sai tùy policy.

Nếu yêu cầu nghiệp vụ là “import chỉ cho **machine workload đã duyệt**”, cần cả:

~~~text
CALLER_SERVICE AND SCOPE_orders.import
```

Tương tự, endpoint `/api/me` hiển thị thông tin người dùng **không nên** được gọi bằng machine token rồi coi service account như user.

### 11.3. `authenticated()` chưa đủ

Một policy:

~~~java
.requestMatchers("/api/users/**").authenticated()
~~~

có thể cho cả machine token và user token qua tầng HTTP. Nếu endpoint bắt buộc human-user context, hãy dùng marker/policy phù hợp; nếu machine được phép gọi thì cần quyền và ownership riêng.

## 12. Resource-level authorization phải khác theo principal kind

Một user token và machine token cùng có `SCOPE_orders.read` nhưng **không nhất thiết được xem cùng tập orders**.

Ví dụ:

~~~text
User token:
  subject = person-42
  client  = storefront-web
  scope   = orders.read
  policy  = đọc order của chính user trong tenant được phép

Machine token:
  subject = svc:inventory-sync
  client  = inventory-sync
  scope   = orders.read
  policy  = đọc subset inventory-related orders của tenant-a
```

Nếu service code chỉ làm:

~~~java
String owner = authentication.getName();

return orderRepository.findByOwnerId(owner);
~~~

nó có thể sai cho máy gọi vì `getName()` là service subject, không phải user owner. Hệ thống có thể trả rỗng, hoặc tệ hơn là bypass ownership bằng default role.

### 12.1. Domain identity rõ kind

~~~java
public sealed interface CallerIdentity
        permits HumanCaller, ServiceCaller {

    String issuer();
}

public record HumanCaller(
        String issuer,
        String userSubject,
        String clientId
) implements CallerIdentity {}

public record ServiceCaller(
        String issuer,
        String serviceSubject,
        String clientId
) implements CallerIdentity {}
~~~

Đây là **domain types do ví dụ định nghĩa**, không phải Spring Security sẵn có. Chúng chỉ nên được tạo **sau JWT validation hoặc introspection thành công**. `issuer` giúp phân biệt identity namespaces.

### 12.2. Adapter từ JWT đã authenticated

~~~java
public CallerIdentity resolveCaller(Jwt jwt) {
    String issuer = jwt.getIssuer().toString();
    String subject = jwt.getSubject();
    String clientId = jwt.getClaimAsString("client_id");
    String kind = jwt.getClaimAsString("caller_kind");

    // Giả định CallerContractValidator đã được áp dụng.
    if ("user".equals(kind)) {
        return new HumanCaller(issuer, subject, clientId);
    }
    if ("service".equals(kind)) {
        return new ServiceCaller(issuer, subject, clientId);
    }
    throw new AccessDeniedException("Unsupported caller kind");
}
~~~

Đây là method minh họa đặt trong một service/adapter đã nhận `Jwt` từ Spring Security, với imports các record và `AccessDeniedException`. Không lấy `Jwt` từ `JWTParser.parse(rawToken).getJWTClaimsSet()` rồi dùng logic tương tự; claim chưa xác minh vẫn là input không đáng tin.

### 12.3. Policy theo object

~~~java
public OrderDto readOrder(
        CallerIdentity caller,
        String tenantId,
        String orderId) {

    Order order = orderRepository
        .findByIdAndTenantId(orderId, tenantId)
        .orElseThrow(NotFoundException::new);

    if (caller instanceof HumanCaller human) {
        if (!orderPolicy.canUserRead(
                human.issuer(), human.userSubject(), order)) {
            throw new AccessDeniedException("Forbidden");
        }
    } else if (caller instanceof ServiceCaller service) {
        if (!orderPolicy.canServiceRead(
                service.issuer(), service.clientId(), order)) {
            throw new AccessDeniedException("Forbidden");
        }
    } else {
        throw new AccessDeniedException("Unsupported caller");
    }

    return toDto(order);
}
~~~

`Order`, `OrderDto`, repositories, `NotFoundException`, `orderPolicy` và `toDto(...)` thuộc **ứng dụng nghiệp vụ minh họa**. Điều cần giữ là **query ràng buộc tenant và policy theo caller kind**. Đừng cấp quyền “machine đọc tất cả” chỉ vì không có user subject.

### 12.4. Token chứa `tenant_id` cũng không thay membership

`tenant_id=tenant-a` trong token đã xác minh cho biết AS phát biểu tenant context theo contract. Nhưng nếu Orders API tự quản lý membership, Resource Server vẫn phải đối chiếu DB/ACL hiện tại.

Đối với máy gọi, quyền có thể cần giới hạn theo client ID + tenant + operation + resource instance; đối với user, theo subject + tenant + owner/role. Cả hai phải ngăn lỗi BOLA/IDOR.

## 13. Opaque token cũng có thể khác claims theo client

Không phải AS nào cũng phát JWT. Với opaque token, Resource Server gọi introspection endpoint tin cậy:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-client-credentials>

token=opaque-reference-token
~~~

Token user có thể introspect ra:

~~~json
{
  "active": true,
  "sub": "person-42",
  "client_id": "storefront-web",
  "scope": "orders.read",
  "caller_kind": "user",
  "aud": ["orders-api"]
}
~~~

Token machine có thể ra:

~~~json
{
  "active": true,
  "sub": "svc:inventory-sync",
  "client_id": "inventory-sync",
  "scope": "orders.import",
  "caller_kind": "service",
  "aud": ["orders-api"]
}
~~~

Các `caller_kind`, `aud` và `sub` ở đây thuộc **AS contract minh họa**; RFC 7662 không buộc mọi response có đủ tất cả trường này.

**Không được** tự tạo `OAuth2AuthenticatedPrincipal` cho token có `active=false`. Delegate introspector phải xác nhận token hợp lệ trước khi mapping custom claims.

### 13.1. Principal của opaque token khác JWT

| Token flow | Principal sau xác thực | Điểm tùy chỉnh |
|---|---|---|
| JWT | Thường là `Jwt` qua `JwtAuthenticationToken` | `JwtDecoder`, `JwtAuthenticationConverter` |
| Opaque | `OAuth2AuthenticatedPrincipal` qua `BearerTokenAuthentication` | `OpaqueTokenIntrospector`, converter tương ứng |

Không cast opaque principal thành `Jwt`. Nếu dùng chung controller cho hai token mechanisms, nhận `Authentication` hoặc xây domain caller adapter tách theo loại authentication.

### 13.2. Wrapper introspector bảo toàn scopes

Ví dụ custom:

~~~java
package com.example.orders.security;

import java.util.LinkedHashSet;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class CallerKindOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public CallerKindOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Authentication trước, mapping sau.
        OAuth2AuthenticatedPrincipal p = delegate.introspect(token);

        String kind = p.getAttribute("caller_kind");
        String clientId = p.getAttribute("client_id");

        boolean user = "user".equals(kind)
            && "storefront-web".equals(clientId);

        boolean service = "service".equals(kind)
            && "inventory-sync".equals(clientId);

        if (!user && !service) {
            throw new BadOpaqueTokenException(
                "Unexpected caller contract");
        }

        var authorities = new LinkedHashSet<GrantedAuthority>(
            p.getAuthorities());

        authorities.add(new SimpleGrantedAuthority(
            user ? "CALLER_USER" : "CALLER_SERVICE"));

        return new DefaultOAuth2AuthenticatedPrincipal(
            p.getName(),
            p.getAttributes(),
            authorities
        );
    }
}
~~~

**Lưu ý:** ví dụ rút gọn chỉ minh họa cách **bọc delegate** và giữ scopes. Trong production, contract còn phải kiểm tra `aud`/resource binding, loại token, issuer/identity source, danh sách client IDs và field types; không chỉ dựa vào `active=true`.

Với opaque response **không có `iss`**, có thể dùng identity source từ introspection endpoint được cấu hình tin cậy theo contract. Không tự lấy issuer từ header client.

## 14. Đặc biệt: `roles` và `groups` có thể khác giữa user và service

Một số AS phát:

~~~json
{
  "roles": ["orders-reader"],
  "groups": ["sales-team"]
}
~~~

cho user token; machine token có:

~~~json
{
  "roles": ["inventory-importer"]
}
~~~

hoặc **không có** cả hai claims.

Spring Security mặc định **không có một quy tắc universal** tự map mọi `roles`, `groups` của mọi AS thành quyền API. Cần quyết định rõ:

- Role nào thuộc `orders-api`, không phải management realm của IdP?
- Role do user có thể sửa hay do admin/policy có thẩm quyền cấp?
- Role có scope tenant hay global?
- Khi AS không trả role, fail closed hay chỉ không thêm authority?
- Role của service account có được coi là human role không? Thường **không**.
- Mapping theo issuer/client cần allowlist gì?

Ví dụ mapping:

| Input từ nguồn có thẩm quyền | Authority ứng dụng | Loại caller |
|---|---|---|
| `scope=orders.read` | `SCOPE_orders.read` | Cả hai nếu contract cho phép |
| `roles=["order-viewer"]` | `ROLE_ORDER_VIEWER` | User policy đã duyệt |
| `roles=["inventory-importer"]` | `ROLE_INVENTORY_IMPORTER` | Service policy đã duyệt |
| `permissions=["orders.export"]` | `PERM_ORDERS_EXPORT` | Theo entitlement AS |
| `email` chứa `admin` | **Không tạo quyền** | Không áp dụng |
| Machine thiếu `groups` | Không tự thêm user group | Không áp dụng |
| Unknown role `root` | Không map admin | Không áp dụng |

**Không convert mọi chuỗi bằng `"ROLE_" + value.toUpperCase()`**. Một role `admin` của IdP console không tự tương đương role quản trị Orders API.

## 15. Machine client không nên mượn quyền của user

Một service có thể gọi API trong hai bối cảnh khác nhau.

### 15.1. Service hành động **cho chính nó**

~~~text
Inventory Worker
  -> client_credentials
  -> access token with client/service subject
  -> Orders API
```

Nó được phép thực hiện các quyền **application-level** đã cấp, ví dụ nhập dữ liệu inventory của tenant được đăng ký.

### 15.2. Service hành động **thay mặt người dùng**

~~~text
Person-42 -> BFF -> Orders API
              |
              +-> Another API on behalf of Person-42
```

Trong trường hợp thứ hai, nếu downstream cần cả **user identity** và **actor/service identity**, chỉ dùng machine `client_credentials` không tự bảo toàn sự ủy quyền của người dùng. Có thể cần:

- Access token đã cấp cho đúng downstream audience theo flow của client.
- Một token exchange theo **RFC 8693** hoặc cơ chế on-behalf-of do AS hỗ trợ.
- Actor/delegation semantics rõ ràng, có thể qua `act` claim khi sử dụng profile token exchange.
- Scope và resource restrictions giảm quyền phù hợp.
- Audit ghi actor và subject đúng ngữ nghĩa.

**Không** tự thêm:

~~~json
{
  "sub": "person-42",
  "caller_kind": "user"
}
~~~

vào token machine hoặc một header rồi xem như đã được người dùng ủy quyền. Một machine token đã xác thực service A không tự trở thành token của person-42 chỉ vì caller gửi thêm `X-User-Id: person-42`.

### 15.3. Service-to-service forwarding và audience

Nếu API A nhận access token `aud=api-a`, API A **không tự forward** token đó tới API B và kỳ vọng B chấp nhận. B phải ràng buộc `aud=api-b` hoặc resource phù hợp. Khi cần downstream delegation, xin token đúng audience/scope theo cơ chế AS đã duyệt.

Điều này quan trọng cho cả user-facing và machine-to-machine flows.

## 16. Các issuer khác nhau có thể công bố claim khác nhau

Trong một hệ thống tích hợp nhiều nhà phát hành:

~~~text
Issuer A user token:
  scope = "orders.read"
  client_id = "storefront-web"
  sub = "person-42"

Issuer B service token:
  scp = ["orders.import"]
  client_id = "inventory-sync"
  sub = "service-18"
```

Có thể phải chuẩn hóa tên claim:

~~~text
scope / scp -> OAuth authorities
sub         -> canonical subject theo issuer
client_id   -> OAuth client
caller kind -> theo contract issuer/token profile
```

Nhưng **đừng quy đổi field sai ngữ nghĩa**. Ví dụ `roles` của issuer B không tự tương đương `roles` của issuer A.

Nếu API hỗ trợ nhiều JWT issuers, nên dùng **trusted issuer allowlist** với `JwtIssuerAuthenticationManagerResolver` hoặc issuer-specific decoder/manager repository. Claim `iss` lấy từ payload chưa verify chỉ được dùng để route tới một trusted manager; không để token từ attacker chỉ định arbitrary JWKS/metadata URL.

### 16.1. Cùng `client_id` tại hai issuers chưa chắc cùng ứng dụng

~~~text
(issuer A, client_id=worker)
(issuer B, client_id=worker)
```

là hai client registrations độc lập trừ khi hệ thống có federation mapping rõ. Máy gọi nên được audit theo **issuer + client ID + service subject + tenant** tùy contract, không chỉ `client_id`.

### 16.2. User profile có thể khác theo issuer

Một issuer có thể trả `email`, issuer khác không; một issuer trả `preferred_username`, issuer khác chỉ có `sub`. Không bắt tất cả user tokens có cùng display fields nếu API không cần, và không dùng email làm canonical identity xuyên issuer.

## 17. AS và Resource Server phải thống nhất trách nhiệm

Một nguyên nhân của “user token có roles, machine token không có” có thể chỉ là **AS chưa cấu hình protocol mapper cho đúng client/grant**, không nhất thiết là bug Spring Security.

Bảng phân công:

| Việc | Authorization Server | Resource Server |
|---|---|---|
| Xác thực end-user | Có trong user-authentication flow | Không tự login lại user cho bearer API |
| Xác thực machine client tại token endpoint | Có | Không xem client secret như bearer token |
| Quyết định client/grant allowed scopes | Có | Không tự thêm scope thiếu |
| Đặt `sub`/`client_id`/`aud` | Có theo profile | Validate và hiểu đúng |
| Đặt custom `caller_kind` | Có theo contract đã quản trị | Validate + map marker |
| Phát profile claims | Có thể theo client scopes/mappers | Không coi profile là entitlement |
| Ký JWT hoặc lưu opaque token state | Có | Verify JWT hoặc introspect |
| Mapping claim → authorities | Có thể phát standardized entitlements | Map theo allowlist ứng dụng |
| Quyết định order thuộc tenant/owner nào | Có thể cấp coarse tenant claim | **Phải enforce object/resource policy** |
| Thu hồi/rotate credentials | Có | Enforce token status/time/key policy |
| Audit và anomaly detection | Có | Ghi caller kind, resource, decision đúng |

### 17.1. Kiểm tra từ phía AS khi machine token thiếu claim

Thay vì sửa converter ngay, nên xác minh:

1. Machine client có được phép dùng `client_credentials`?
2. AS đã gán đúng **client scopes** và **audience** chưa?
3. Role/permission được gán cho **service account/application** hay chỉ gán cho human users?
4. Protocol mapper có đưa entitlement vào **access token**, không chỉ ID token/UserInfo?
5. Custom `caller_kind` có được thiết lập **từ token issuance policy**?
6. AS có phát `sub`/`client_id` theo JWT access token profile đã chọn?
7. Token được gửi tới đúng API, đúng issuer/tenant/environment?
8. Machine token có bị dùng để gọi endpoint chỉ chấp nhận human user?

### 17.2. Không đòi “mọi token phải giống nhau”

Một trường hợp hoàn toàn hợp lý:

~~~text
User token:
  sub person-42
  client_id storefront-web
  scope orders.read
  preferred_username mai

Machine token:
  sub svc:inventory-sync
  client_id inventory-sync
  scope orders.import
  no preferred_username
```

Đây không nhất thiết là lỗi. Mục tiêu là **API có contract đúng theo token purpose**, không phải ép machine token có tất cả fields của end-user.

## 18. Phân biệt 401, 403 và lỗi claim mapping

| Triệu chứng | Lớp nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Token máy gọi không có `email` | Claim profile không thuộc machine contract | Không bắt email nếu không cần |
| Token máy gọi không có `sub` dù contract yêu cầu | Issuer/token profile mismatch | Sửa AS contract hoặc reject |
| Token có `client_id` nhưng thiếu `caller_kind` bắt buộc | Issuer mapper thiếu | Reject, không đoán |
| `caller_kind=service` nhưng client ID thuộc user allowlist | Token purpose mismatch | Reject |
| JWT signature/issuer/audience sai | Authentication failure | 401 theo bearer entry point |
| Token hết hạn | Authentication failure | 401 |
| Opaque token `active=false` | Authentication failure | 401 |
| Token hợp lệ nhưng user gọi import service-only | Authorization failure | 403 |
| Machine có `SCOPE_orders.read` nhưng gọi `/api/me` | Không phải human caller | 403 |
| User hợp lệ đọc order tenant khác | Object-level authorization | 403/404 theo policy |
| Machine có role nhưng API không nhận ra | Mapper/claim contract | Sửa mapping đã duyệt, không tự grant admin |
| Auth service/JWKS outage | Dependency failure | Không fail open |
| Client ID đúng nhưng grant purpose sai | Grant/profile contract | AS policy và caller-kind validation |
| `sub` user trùng `sub` service | Identity collision | Thêm namespace issuer/kind |
| OIDC ID token bị gửi tới API | Wrong token audience/type | Từ chối |

**401** thường liên quan thiếu hoặc xác thực token thất bại; **403** thường liên quan token đã xác thực nhưng thiếu quyền. Lỗi hạ tầng có thể được mapping thành 5xx hoặc trạng thái khác tùy exception handling/version; không xem mọi timeout là permission denial.

### 18.1. Vì sao không thêm quyền khi thấy 403?

Một cách sửa sai:

~~~java
if (clientId.equals("inventory-sync")) {
    authorities.add(
        new SimpleGrantedAuthority("SCOPE_orders.write"));
}
~~~

nếu AS chỉ cấp `orders.read`, đây là **privilege escalation**. Sửa đúng cần điều chỉnh client authorization/entitlement tại AS hoặc chính sách API nếu nghiệp vụ thực sự yêu cầu.

## 19. Unit test claim contract

Các unit tests giúp chứng minh validator **không xem mọi `sub` là user**.

### 19.1. Tạo Jwt test object

~~~java
package com.example.orders.security;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CallerContractValidatorTest {

    private final CallerContractValidator validator =
        new CallerContractValidator();

    private Jwt jwt(
            String subject,
            String clientId,
            String kind) {

        return Jwt.withTokenValue("unit-test-only")
            .header("alg", "RS256")
            .issuer("https://login.example.com/realms/orders")
            .subject(subject)
            .claim("client_id", clientId)
            .claim("caller_kind", kind)
            .issuedAt(Instant.now())
            .expiresAt(Instant.now().plusSeconds(600))
            .build();
    }

    @Test
    void userClientWithUserPurposeIsAccepted() {
        var token = jwt("person-42", "storefront-web", "user");
        assertFalse(validator.validate(token).hasErrors());
    }

    @Test
    void serviceClientWithServicePurposeIsAccepted() {
        var token = jwt(
            "svc:inventory-sync",
            "inventory-sync",
            "service"
        );
        assertFalse(validator.validate(token).hasErrors());
    }

    @Test
    void userClientCannotClaimServicePurpose() {
        var token = jwt("person-42", "storefront-web", "service");
        assertTrue(validator.validate(token).hasErrors());
    }

    @Test
    void missingPurposeIsRejected() {
        var token = jwt("person-42", "storefront-web", null);
        assertTrue(validator.validate(token).hasErrors());
    }
}
~~~

Đoạn test dùng `Jwt` dựng trong bộ nhớ, **không xác minh chữ ký**. Nó chỉ kiểm tra logic của `CallerContractValidator`; không thay test `JwtDecoder` thật. `Jwt.Builder` helpers có thể khác theo Spring Security version; nếu cần, dùng `.claim("iss", ...)`, `.claim("sub", ...)` trong fixture được hỗ trợ.

### 19.2. Test authority mapping

Mục tiêu:

~~~text
User token:
  scope="orders.read"
  caller_kind="user"
=> SCOPE_orders.read + CALLER_USER

Machine token:
  scope="orders.import"
  caller_kind="service"
=> SCOPE_orders.import + CALLER_SERVICE

Unknown caller_kind:
=> validator phải reject trước khi converter tạo Authentication
```

Một unit test converter nên xác nhận:

- Giữ nguyên mọi `SCOPE_*` đã được cấp.
- Không tự thêm scope import/write.
- Không thêm `ROLE_ADMIN` từ email/username.
- Marker type chỉ xuất hiện theo contract.
- Không phụ thuộc `groups`/`email` vắng mặt.

### 19.3. Test Web authorization

Với `MockMvc` và Spring Security Test:

~~~java
mvc.perform(post("/api/import/jobs")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("CALLER_SERVICE"),
            new SimpleGrantedAuthority("SCOPE_orders.import")
        )))
    .andExpect(status().isOk());
~~~

Ví dụ giả định endpoint tồn tại, không có CSRF requirement trong bearer-only test chain và business code thành công. **Mock token** chỉ chứng minh authorization rule; nó có thể bypass decoder và custom converter.

Phải có test khác:

~~~java
mvc.perform(post("/api/import/jobs")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("CALLER_USER"),
            new SimpleGrantedAuthority("SCOPE_orders.import")
        )))
    .andExpect(status().isForbidden());
~~~

Kết quả này cho thấy scope import **không đủ** nếu endpoint yêu cầu machine caller. Imports `post`, `status`, `jwt`, `SimpleGrantedAuthority` theo Spring Test/MockMvc.

### 19.4. JWT integration test phải dùng token ký thật

Để chứng minh toàn bộ pipeline:

1. Tạo RSA key pair dành riêng test.
2. Fake JWKS endpoint trả public key test.
3. Tạo JWT **ký thật** với `iss`, `aud`, `exp`, `client_id`, `caller_kind`, `scope`.
4. Gửi header `Authorization: Bearer <signedJwt>` qua real security filters.
5. Verify token user đúng nhận human marker và token service đúng nhận service marker.
6. Reject signature sai, issuer sai, audience sai, token expired.
7. Reject `caller_kind=service` được ký cho `storefront-web` trái contract.
8. Reject `caller_kind` thiếu hoặc client ID lạ.
9. Verify không có end-user email vẫn không làm service token hợp lệ bị reject nếu contract không đòi email.
10. Verify 403 khi service token gọi endpoint chỉ cho user.
11. Verify ownership/tenant ACL tại service.
12. Verify token ID token cho OIDC client không qua API audience/token-type policy.

**Không** dùng private production signing key hoặc thực hiện decode Base64 rồi giả định test đã verify chữ ký.

## 20. Ma trận kiểm thử âm tính theo claim

| Token | Principal kind mong đợi | Kết quả |
|---|---|---|
| User token đúng issuer/aud/client/kind | `user` | Authentication pass; authorization tùy scope |
| Machine token đúng issuer/aud/client/kind | `service` | Authentication pass; authorization tùy scope |
| User token thiếu email | `user` | Có thể pass, nếu email không bắt buộc |
| Machine token thiếu email | `service` | Pass theo service contract |
| Machine token có `preferred_username` là tên service account | `service` | Không coi là human user |
| User token có `caller_kind=service` nhưng client user | Không hợp lệ | Reject |
| Machine client có `caller_kind=user` | Không hợp lệ | Reject |
| Thiếu `caller_kind` khi contract bắt buộc | Không xác định | Reject |
| Claim kind có giá trị `admin` | Không xác định | Reject, không map role |
| `aud=billing-api` | Không hợp lệ cho Orders API | Reject |
| Wrong issuer/signature/expiry | Không hợp lệ | Reject |
| Có `SCOPE_orders.import` nhưng là user token | `user` | Import machine-only bị 403 |
| Có `SCOPE_profile.read` nhưng là machine token | `service` | `/api/me` bị 403 |
| Có `orders.read` nhưng order tenant khác | User hoặc service | Reject tại service |
| Hai issuers cùng `sub` | Tách identity | Không hợp nhất |
| Client Credentials token được giả danh `X-User-Id` | `service` | Không chuyển thành user |
| Opaque `active=false` | Không có principal | Reject |
| AS timeout khi introspect | Không xác minh được | Không fail open |

Một hệ thống mạnh **không chỉ test token đầy đủ claims**, mà còn test các field thiếu, sai kiểu, token purpose bị giả và đồng nhất identity sai.

## 21. Bảo mật credential và lifecycle của client

### 21.1. Public client của người dùng

Với SPA/mobile, OAuth client thường không thể giữ secret như backend. Dùng Authorization Code + PKCE và các biện pháp bảo vệ session/redirect/CSRF liên quan kiến trúc.

Không lưu client secret trong JavaScript bundle hoặc mobile app rồi xem nó bí mật.

### 21.2. Confidential machine client

Với `client_credentials`, dùng phương thức xác thực client được AS hỗ trợ và tổ chức phê duyệt, ví dụ:

- Secret được giữ trong secret manager và xoay vòng.
- Private key JWT client authentication nếu thích hợp.
- Mutual TLS nếu hạ tầng cung cấp.
- Workload identity/federation khi AS hỗ trợ.
- Scopes/audiences tối thiểu theo workload.
- Token lifetime ngắn phù hợp SLO và năng lực refresh.

**Không gửi client credentials tới Orders API** như thể chúng là access token. Client chứng thực với AS, rồi dùng **access token đã cấp** để gọi Resource Server.

### 21.3. Opaque vs JWT, revocation

JWT xác minh cục bộ thường không cần hỏi AS mỗi request sau khi có key; việc revoke trước hạn cần thiết kế thêm nếu có yêu cầu.

Opaque token introspection có thể cập nhật `active=false` sớm hơn theo AS policy, nhưng cache introspection hoặc directory vẫn có thể gây stale permission. Không xem `client_credentials` là token luôn có quyền vô hạn.

## 22. Privacy và data minimization

Một nguyên tắc tích hợp nhà phát hành là **đưa vào access token những gì Resource Server thực sự cần**.

Ví dụ Orders API cần:

~~~text
iss, sub, aud, exp, scope, client_id, caller_kind
tenant context theo contract nếu cần
```

Nó có thể **không cần**:

~~~text
birthdate, home address, full user profile,
email, phone number, mọi group trong toàn tổ chức
```

Đưa tất cả OIDC profile claims vào access token để API “có đủ dữ liệu” có thể tăng PII exposure khi token bị log hoặc truyền qua nhiều dịch vụ.

Đối với machine token, thường không có lý do đưa human profile claims vào. Nếu cần audit người chịu trách nhiệm vận hành workload, lưu metadata đó trong trusted registry/admin inventory, không giả làm `sub` người dùng trong token client credentials.

### 22.1. Không log raw bearer token

Nên log các thông tin đã được chuẩn hóa ở mức tối thiểu:

~~~text
requestId=trace-123
issuerRef=orders-prod
callerKind=service
clientRef=inventory-sync
subjectRef=<stable-internal-ref>
endpoint=/api/import/jobs
decision=DENY
reason=missing_scope
bearerToken=[REDACTED]
~~~

Không ghi raw Authorization header, ID token, private signing key, client secret hoặc toàn bộ JWT claims/opaque response vào production logs.

## 23. Một quy trình điều tra khi hai client nhận claims khác nhau

Khi developer hỏi “cùng AS mà token của web có `email`/`roles`, token job không có”, hãy đi theo thứ tự:

**Bước 1 — Xác định đúng token.** Là access token, ID token hay UserInfo response? Không so sánh ID token của browser với access token của machine.

**Bước 2 — Xác định grant.** Web đang dùng Authorization Code hay token exchange? Job đang dùng client credentials thật hay một stored user token?

**Bước 3 — Xác định issuer và intended audience.** Cả hai có đúng `iss` và `aud=orders-api` không? Có khác realm/environment không?

**Bước 4 — Xác định AS client registration.** `client_id`, client scopes, allowed grants, audience, service account roles và protocol mappers có khác nhau không?

**Bước 5 — Xác định claim source.** Email từ user profile; service entitlement từ client/service-account authorization; không mặc nhiên phải có cùng fields.

**Bước 6 — Xác định claim contract của API.** API cần `sub`, `client_id`, caller purpose, scope nào? Có bắt nhầm email cho machine không?

**Bước 7 — Xác định mapper của Resource Server.** `JwtGrantedAuthoritiesConverter` mặc định đọc scope/scp; nó không tự hiểu arbitrary `roles`, `groups`.

**Bước 8 — Xác định HTTP rule.** Token hợp lệ vẫn có thể thiếu `SCOPE_orders.import` hoặc sai `CALLER_SERVICE`.

**Bước 9 — Xác định service policy.** Tenant membership, owner/ACL và resource state có thể từ chối dù HTTP 200 ở endpoint khác.

**Bước 10 — Viết test cho AS mapping.** Có unit, signed-token integration và end-to-end test với client/grant thực; không thêm role mặc định chỉ để 403 biến mất.

### 23.1. Không sửa bằng cách “copy toàn bộ user claims cho machine”

Nếu job thiếu `email`, cách sửa đúng thường là **không yêu cầu email** ở machine path. Nếu job thiếu permission, hãy cấp entitlement đúng từ AS cho application client. Không gán email giả hoặc role admin cho machine chỉ để thỏa code dùng chung.

## 24. Những hiểu nhầm thường gặp

**“Cùng Authorization Server thì mọi access token phải có cùng claims.”** Sai. Client, grant, scopes, mappers và resource audience có thể làm token khác nhau.

**“Có `sub` nghĩa là con người.”** Sai. RFC 9068 cho phép access token không có resource owner dùng `sub` chỉ ứng dụng/client.

**“Machine token không bao giờ có `sub`.”** Sai. Tùy token profile, `sub` có thể là service/application identity.

**“`sub == client_id` cho mọi client_credentials.”** Không được giả định. Contract phụ thuộc AS; RFC 9068 có khuyến nghị định danh client app.

**“User client có `client_id`, vậy `client_id` là user ID.”** Sai. Nhiều users có thể dùng cùng client.

**“Client ID một mình cho biết có end-user hay không.”** Không chắc khi một client hỗ trợ nhiều grant types; cần token-purpose/grant contract đáng tin.

**“Machine client không có email là token hỏng.”** Sai nếu email không thuộc service token contract.

**“OIDC `openid profile email` nghĩa Orders API có quyền đọc mọi hồ sơ.”** Sai. OIDC identity scopes không thay OAuth API business scopes.

**“ID token dùng được ở Resource Server vì cũng là JWT.”** Sai. Phải dùng access token đúng audience/type.

**“`roles` có trong JWT thì Spring tự chuyển thành mọi `ROLE_*`.”** Không mặc định. Cần mapping rõ và nguồn entitlement đáng tin.

**“Tên service account có chữ admin nghĩa là ROLE_ADMIN.”** Sai. Display/username không phải quyền.

**“M2M token có quyền mạnh hơn user token.”** Không mặc định. Hai loại có quyền khác nhau theo policy, nên least privilege.

**“Client credentials token có thể thay mặt bất kỳ user bằng X-User-Id.”** Sai. Cần delegation/token exchange/AS policy nếu thực sự hành động thay người dùng.

**“Cùng `SCOPE_orders.read` nghĩa mọi caller đọc cùng dữ liệu.”** Sai. Service business authorization còn xét subject, tenant và owner.

**“Custom JWT converter tự đảm bảo JWT đã được ký đúng.”** Không. Decoder thực hiện verify; converter chỉ ánh xạ claims đã xác thực trong pipeline chuẩn.

**“Thấy 403 nên tự bổ sung scope.”** Nguy hiểm. Scope phải có nguồn cấp quyền có thẩm quyền.

**“Chỉ test MockMvc.with(jwt()) đủ chứng minh AS phát đúng claim.”** Không. Mock có thể bypass decoder/real issuer issuance.

## 25. Câu hỏi tự kiểm tra

**1.** Vì sao `client_credentials` token có thể không có `email` hoặc `preferred_username`?

> Vì grant không có end-user đang đăng nhập; token chủ yếu đại diện ứng dụng hoặc service identity.

**2.** `sub` trong JWT luôn là human user ID đúng không?

> Không. Trong JWT access token profile, token không có resource owner có thể dùng `sub` chỉ application/client identity.

**3.** `client_id` trong user token có phải định danh người dùng?

> Không. Nó nhận diện OAuth client ứng dụng, còn user identity thường được nhận từ subject và issuer.

**4.** Có thể phân biệt user/machine chỉ bằng `client_id` không?

> Chỉ khi AS/client registration contract bảo đảm client đó duy nhất cho loại token ấy; nếu client hỗ trợ nhiều grants thì không đủ.

**5.** Có claim `grant_type` chuẩn bắt buộc trên mọi access token không?

> Không. OAuth grant được gửi trong token request; claims trong access token phụ thuộc profile và AS. `gty`/`grant_type` trong JWT có thể là extension của nhà cung cấp.

**6.** ID token và access token khác nhau chủ yếu ở đâu?

> ID token phục vụ OIDC authentication của user ở client; access token cho phép Resource Server truy cập tài nguyên đúng audience/scope.

**7.** Spring Security mặc định chuyển `scope=orders.read` thành gì?

> Thường thành authority `SCOPE_orders.read`, sau khi token đã được xác minh.

**8.** Spring Security có tự map `roles=["inventory-importer"]` không?

> Không universal. Cần custom mapper/claim contract.

**9.** Tại sao marker `CALLER_SERVICE` phải đi cùng `SCOPE_orders.import`?

> Caller kind xác định loại principal; scope thể hiện quyền thao tác. Một cái không thay thế cái còn lại.

**10.** Machine client có `SCOPE_orders.read` có được xem order của mọi tenant?

> Không. Cần service ACL/tenant binding và resource-level authorization.

**11.** Token máy gọi có thể đại diện user khi nào?

> Khi có authorization/delegation đúng contract như token exchange/on-behalf-of; client credentials đơn thuần không tự là user token.

**12.** Muốn biết tại sao machine token thiếu roles, nên kiểm tra tầng nào trước?

> AS client registration, service account entitlements, client scopes/protocol mappers và access-token issuance policy.

**13.** Nếu token có `caller_kind=service` nhưng được cấp cho một user-facing client, phải làm gì?

> Từ chối theo caller contract nếu đây là tổ hợp không được phép.

**14.** Có nên yêu cầu tất cả tokens chứa profile claims để dùng chung một DTO?

> Không. Thiết kế domain principal/DTO theo đúng caller kind và data minimization.

**15.** Vì sao integration test cần JWT được ký bằng test key?

> Để thực sự kiểm tra decoder, issuer, audience, caller kind và mapping; mock authentication không chứng minh trust chain.

## 26. Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code, Client Credentials, access token, scopes.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): Authorization Code với proof key, đặc biệt cho public clients.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `iss`, `sub`, `client_id`, `aud`, scopes và subject của token không có resource owner.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `client_id`, `scope`, `sub`, attributes của opaque tokens.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): ràng buộc tài nguyên dự kiến/audience.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): delegation, impersonation và actor `act`.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience validation, algorithm confusion và cross-token confusion.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo và end-user profile claims.
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification, `JwtAuthenticationConverter`, `scope`/`scp` mapping.
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, `OAuth2AuthenticatedPrincipal`, authorities.
- [Spring Security — JwtGrantedAuthoritiesConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): claim name, scope prefix và custom authorities.
- [Spring Security — JwtAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): tạo `JwtAuthenticationToken` từ verified JWT.
- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuers/issuer-aware manager.
- [Spring Security — HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, `AuthorizationManagers.allOf`, rule order.
- [Spring Authorization Server — Reference](https://docs.spring.io/spring-authorization-server/reference/): server-side token customization, registered clients và client authentication.

**Tổng kết:** token của **client phục vụ người dùng** và **client máy gọi** có thể có **claims hoàn toàn khác nhau** vì chúng biểu diễn những principals và authorization contexts khác nhau. Resource Server phải xác minh JWT/introspection đúng cách, kiểm tra issuer/audience/token type, hiểu `sub` cùng `client_id` theo AS contract, chỉ ánh xạ scopes/roles có căn cứ và phân quyền theo human/service identity. Đừng giả định `email` luôn tồn tại, đừng xem machine client là human user, và đừng biến dữ liệu profile thành quyền. Thiết kế đúng gồm **claim contract tại Authorization Server**, **validation/conversion tại Spring Security**, rồi **tenant/ownership authorization tại business service**.
