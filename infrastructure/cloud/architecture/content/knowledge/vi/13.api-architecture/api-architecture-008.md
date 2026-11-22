# Xác thực dịch vụ, phân quyền và bảo vệ API công khai

## 1. Vì sao API công khai cần nhiều lớp bảo vệ?

API công khai là giao diện mà ứng dụng web, mobile, đối tác hoặc hệ thống bên ngoài dùng để tương tác với dịch vụ cloud. Một request đến được API Gateway và có token hợp lệ vẫn chưa chứng minh caller được phép đọc hoặc thay đổi dữ liệu mà request yêu cầu. API có thể xác thực người dùng đúng nhưng vẫn để lộ hồ sơ của người khác; có thể giới hạn tốc độ ở gateway nhưng vẫn bị lạm dụng qua nhiều tài khoản; hoặc dùng HTTPS nhưng để lộ secret trong log.

Thiết kế an toàn cần phân biệt ba câu hỏi:

- **Authentication (xác thực):** ai hoặc workload nào đang gọi?
- **Authorization (phân quyền):** caller được phép thực hiện hành động nào trên tài nguyên nào, trong bối cảnh nào?
- **API protection (bảo vệ API):** làm thế nào giảm khả năng lạm dụng, khai thác lỗ hổng, quá tải, rò rỉ dữ liệu và tác động lan rộng?

OAuth 2.0, OpenID Connect (OIDC), workload identity, mutual TLS (mTLS), API Gateway, Web Application Firewall (WAF), rate limiting, schema validation và audit log giải quyết những phần khác nhau của bài toán. Chúng phải phối hợp với kiểm tra quyền trong ứng dụng và ranh giới dữ liệu.

Trong module **CLOUD_ARCHITECTURE**, đây là các quyết định ảnh hưởng trực tiếp đến bảo mật, độ tin cậy, khả năng mở rộng, chi phí và vận hành. Một kiến trúc API tốt xác định rõ danh tính, quyền, đường truyền, giới hạn tải và cách phát hiện/xử lý hành vi bất thường.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt xác thực người dùng, xác thực dịch vụ và ủy quyền cho ứng dụng bên thứ ba.
2. Chọn OAuth 2.0/OIDC flow phù hợp cho public client và machine-to-machine.
3. Thiết kế authorization theo scope, role, attribute, tenant và quyền trên từng object.
4. Kiểm tra token đúng issuer, audience, signature, thời hạn và ngữ cảnh sử dụng.
5. Kết hợp API Gateway, WAF, rate limit, validation, TLS, secrets và audit để bảo vệ API công khai.
6. Nhận diện các lỗi phổ biến như BOLA/IDOR, BFLA, token leakage, SSRF, mass assignment và credential abuse.
7. Xây dựng checklist và quy trình kiểm chứng an toàn trước khi phát hành API.

## 2. Mô hình ranh giới tin cậy của một API

Một request đi qua nhiều thành phần; mỗi thành phần chỉ nên chịu trách nhiệm cho lớp kiểm soát phù hợp.

~~~mermaid
flowchart LR
    Client["Web / Mobile / Partner"] --> Edge["DNS / TLS Edge"]
    Edge --> WAF["WAF / DDoS Protection"]
    WAF --> Gateway["API Gateway"]
    Gateway --> Identity["Identity Provider / Token validation"]
    Gateway --> API["Application API"]
    API --> AuthZ["Resource / tenant authorization"]
    AuthZ --> Data[("Private data store")]
    API --> Audit["Security audit + telemetry"]
    Gateway --> Logs["Gateway access logs"]
~~~

*Sơ đồ logic. Token validation có thể diễn ra tại gateway, tại service hoặc cả hai theo mô hình triển khai. Dù gateway đã xác minh token, ứng dụng vẫn phải kiểm tra quyền nghiệp vụ và quyền trên tài nguyên.*

| Lớp | Câu hỏi cần giải quyết | Ví dụ kiểm soát |
|---|---|---|
| Edge / network | Request có đi qua điểm vào được quản lý? | TLS, DDoS protection, ingress policy |
| WAF / gateway | Request có hợp lệ theo chính sách API và quota? | WAF rules, authentication integration, rate limit, request size |
| Authentication | Caller là user, client hay workload nào? | OIDC, OAuth access token, mTLS, workload identity |
| Authorization | Caller được phép làm hành động này trên resource này không? | Scope, RBAC, ABAC, tenant/ownership check |
| Business logic | Trạng thái và quy tắc nghiệp vụ có cho phép hành động? | Kiểm tra reservation status, payment state, concurrency |
| Data | Dữ liệu và secret được truy cập theo quyền nào? | DB identity, least privilege, encryption, audit |
| Observability | Có thể phát hiện, truy vết và xử lý hành vi bất thường? | Security logs, traces, alerts, incident runbook |

**Không có một lớp duy nhất thay thế tất cả các lớp khác.** Private network không chứng minh caller có quyền; WAF không quyết định người dùng sở hữu reservation; token hợp lệ không làm cho mọi tham số trong request đáng tin.

## 3. Phân biệt xác thực người dùng và xác thực dịch vụ

### 3.1. Người dùng tương tác: xác thực danh tính

Khi một người đăng nhập ứng dụng, hệ thống thường cần xác nhận danh tính qua Identity Provider (IdP). **OpenID Connect (OIDC)** bổ sung lớp xác thực danh tính trên OAuth 2.0 và thường cung cấp ID Token để client biết người dùng đã đăng nhập theo issuer nào, với subject nào.

Các khái niệm cần phân biệt:

- **ID Token:** thông tin xác thực phiên đăng nhập theo OIDC, dành cho client để biết danh tính người dùng. Không dùng ID Token thay access token để gọi API.
- **Access Token:** credential đại diện quyền truy cập một resource/API trong phạm vi được cấp. API nhận access token và xác minh theo hợp đồng của issuer.
- **Refresh Token:** credential dùng để lấy access token mới theo chính sách issuer/client; phải bảo vệ như secret, giới hạn lưu trữ và rotation/revocation theo khả năng.
- **Session cookie:** có thể được ứng dụng web dùng để duy trì phiên; cần thuộc tính Secure, HttpOnly, SameSite phù hợp và cơ chế chống CSRF nếu authentication tự động gửi theo cookie.

Với ứng dụng web/mobile công khai, một hướng phổ biến là **Authorization Code Flow with PKCE**. Người dùng được chuyển đến IdP đăng nhập và đồng ý quyền; client nhận authorization code rồi đổi code theo cơ chế PKCE. PKCE giảm nguy cơ kẻ khác đánh cắp code và đổi token trong luồng public client.

Không nên dùng Implicit Flow hoặc Resource Owner Password Credentials Grant cho thiết kế mới. Client không thể giữ bí mật như một máy chủ đáng tin cậy không nên nhúng client secret tĩnh vào app mobile, desktop hay JavaScript chạy trong trình duyệt.

### 3.2. Dịch vụ gọi dịch vụ: xác thực workload

Ví dụ Booking API gọi Payment API hoặc function gửi message đến queue. Không có người dùng tương tác trực tiếp ở mỗi request; caller là **workload identity**.

Các phương án thường gặp:

- **Workload identity / managed identity:** runtime nhận danh tính do nền tảng cấp, dùng token ngắn hạn để truy cập dịch vụ cloud mà không nhúng access key tĩnh.
- **OAuth 2.0 Client Credentials Grant:** service client lấy access token từ authorization server để gọi API theo scope/audience đã cấp.
- **mTLS:** client và server xác thực chứng chỉ hai chiều khi thiết lập kết nối TLS; có thể dùng chứng chỉ workload hoặc service mesh identity.
- **Signed request / provider-specific identity:** một số dịch vụ dùng chữ ký request hoặc cơ chế danh tính riêng của nhà cung cấp.

Chọn cơ chế có vòng đời credential, rotation, revocation và audit rõ. Nếu một function chỉ cần ghi vào một queue, cấp quyền publish đúng queue đó; không cấp quyền quản trị toàn bộ tài khoản cloud.

### 3.3. Phân biệt các loại credential

| Credential | Mục đích | Giới hạn quan trọng |
|---|---|---|
| ID Token | Thông tin xác thực đăng nhập cho OIDC client | Không dùng thay access token gọi API |
| OAuth Access Token | Mang quyền truy cập tới API/resource | API phải kiểm tra issuer, audience, expiry và quyền theo hợp đồng |
| Refresh Token | Xin token mới | Có giá trị cao, cần bảo vệ và quản lý rotation/revocation |
| API Key | Nhận diện project/client hoặc áp quota đơn giản tùy hệ thống | Không chứng minh danh tính người dùng, thường không đủ làm authorization |
| Client Secret | Xác thực một confidential client với IdP | Lưu như secret, rotation và không nhúng vào public client |
| mTLS Certificate | Xác thực endpoint/workload ở lớp TLS | Cần quản lý CA, issuance, expiration, rotation và identity mapping |
| Cloud Access Key | Credential truy cập cloud API | Tránh long-lived key khi có workload identity/short-lived credentials |

**API key không phải quyền truy cập phổ quát.** Nếu API dùng key để phân loại client, vẫn cần authentication phù hợp và authorization theo user/resource. Khóa bị lộ nên có thể thu hồi/rotation và theo dõi usage.

## 4. OAuth 2.0 và OIDC: chọn flow đúng

OAuth 2.0 là framework ủy quyền; OIDC thêm chức năng xác thực người dùng. Trong thiết kế API, cần xác định ai là client, API nào là resource server, authorization server nào phát token và quyền nào được cấp.

| Tình huống | Flow/mô hình thường phù hợp | Lưu ý |
|---|---|---|
| Web app hoặc mobile app có người dùng | Authorization Code + PKCE | Public client không giữ được client secret; redirect URI phải khớp chính xác |
| Backend server gọi API thay mặt chính nó | Client Credentials | Scope/audience chỉ cấp quyền workload cần |
| Ứng dụng cần gọi API thay mặt người dùng | Authorization Code + PKCE và delegated scopes | API phải phân biệt user context với service identity |
| Service trong cùng cloud gọi managed service | Workload/managed identity | Ưu tiên token ngắn hạn và role theo resource |
| Kết nối service-to-service cần xác thực cả hai đầu tại transport | mTLS kết hợp identity/authorization | Chứng chỉ không tự mô tả đầy đủ quyền nghiệp vụ |

### 4.1. Authorization Code + PKCE

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Web/Mobile Client
    participant I as Identity Provider
    participant A as API
    U->>C: Bắt đầu đăng nhập
    C->>I: Authorization request + PKCE challenge
    I->>U: Xác thực và consent nếu cần
    I-->>C: Authorization code qua redirect URI
    C->>I: Đổi code + PKCE verifier
    I-->>C: ID token + access token theo yêu cầu
    C->>A: API request + access token
    A->>A: Validate token và authorize resource
~~~

PKCE gồm code verifier ngẫu nhiên và code challenge được gửi ở bước authorization. Khi đổi code, client gửi verifier để IdP kiểm tra. Luồng thật còn cần state để liên kết request/response và chống CSRF login, cùng nonce khi OIDC client cần liên kết ID Token với auth request.

### 4.2. Client Credentials cho machine-to-machine

Một service confidential client xác thực với authorization server và lấy access token theo scope/API được phép:

~~~text
Payment reconciliation worker
    -> Authorization Server: client authentication + requested scope
    <- Access token (audience = payment-api)
    -> Payment API: Authorization: Bearer <access-token>
    <- Response theo quyền được cấp
~~~

Client secret, private key hoặc certificate phải được lưu trong secret manager/KMS hoặc cơ chế bảo vệ tương đương, không commit vào repository. Ưu tiên workload identity/federation nếu nền tảng hỗ trợ để giảm credential tĩnh.

### 4.3. Audience và scope

- **Audience (aud):** token được phát cho resource/API nào. API nên từ chối token phát cho API khác.
- **Scope:** quyền được cấp theo cách diễn giải của authorization server/resource server, ví dụ reservation:read.
- **Role:** nhóm quyền trong hệ thống, ví dụ support-agent hoặc booking-admin; role không tự thay thế kiểm tra resource.
- **Client identity:** xác định ứng dụng/workload gọi, khác với user identity trong delegated scenario.

Một token có scope reservation:read vẫn không có nghĩa user được đọc mọi reservation. API phải kiểm tra quyền đối với đúng bản ghi và tenant.

## 5. Xác minh access token đúng cách

### 5.1. Nếu dùng JWT access token

JWT thường có header, payload và signature. Payload được mã hóa dạng Base64URL, **không mặc định được mã hóa bí mật**. Không đặt password, secret hoặc thông tin nhạy cảm vào claim chỉ vì token có chữ ký.

Resource server cần xác minh tối thiểu theo hợp đồng issuer:

1. **Signature:** chữ ký hợp lệ bằng key đáng tin cậy lấy từ issuer/JWKS, thuật toán nằm trong allowlist đã cấu hình.
2. **Issuer (iss):** đúng authorization server đã được tin cậy.
3. **Audience (aud):** chứa đúng API/resource nhận token.
4. **Expiration (exp):** token chưa hết hạn; kiểm tra nbf khi được dùng và cho phép clock skew nhỏ có giới hạn.
5. **Token type/profile:** xác nhận đây là access token đúng profile, không nhận nhầm ID Token.
6. **Authorization claims:** scopes/roles/tenant/subject được sử dụng theo định nghĩa và chính sách API.
7. **Revocation/rotation model:** hiểu thời gian sống token và cách xử lý khi user/session/credential bị thu hồi.

Không tin alg do token tự khai mà không áp dụng allowlist. Khi xoay signing key, resource server cần cập nhật JWKS/key cache có kiểm soát và xử lý kid chưa biết. Chỉ giải mã JWT để đọc claim **không phải xác minh token**.

### 5.2. Nếu dùng opaque access token

Opaque token không tự chứa claim JWT để API xác minh cục bộ. Resource server có thể dùng **token introspection** hoặc cơ chế tra cứu của issuer để kiểm tra token còn hiệu lực, client/subject, audience và scope. Đánh đổi là thêm network dependency, latency và yêu cầu bảo vệ/cache kết quả introspection phù hợp.

### 5.3. Token có thể bị lộ: giảm blast radius

- Access token ngắn hạn theo khả năng issuer, scope/audience tối thiểu.
- Không ghi token vào URL query string, analytics, error page hoặc log.
- Với browser app, ưu tiên BFF/server-side session khi phù hợp; tránh lưu token dài hạn trong nơi JavaScript không đáng tin có thể đọc.
- Với mobile, dùng secure storage của nền tảng; bảo vệ redirect URI và deep link.
- Xoay/thu hồi credential khi lộ; có incident procedure và audit.
- Tránh truyền token của người dùng tới downstream service không cần quyền đó. Có thể dùng token exchange/delegation phù hợp hoặc service identity riêng.

## 6. Authorization: scope, role, attribute và quyền trên tài nguyên

**Authentication trả lời ai đang gọi. Authorization trả lời request cụ thể có được phép không.** Kiểm tra authorization phải được thực hiện tại mỗi hành động truy cập dữ liệu hoặc thay đổi trạng thái có ý nghĩa.

### 6.1. RBAC: quyền theo vai trò

Role-Based Access Control gán quyền theo vai trò. Ví dụ:

| Role | Năng lực điển hình | Giới hạn |
|---|---|---|
| guest | Xem listing công khai, quản lý booking của chính mình | Không xem dữ liệu cá nhân người khác |
| host | Quản lý listing thuộc host và booking liên quan | Không truy cập listing của host khác |
| support-agent | Xem một số thông tin cần cho hỗ trợ | Dữ liệu nhạy cảm phải có lý do, audit và masking |
| finance-operator | Đối soát giao dịch theo phạm vi được giao | Không thay đổi thông tin định danh hoặc quyền quản trị |
| platform-admin | Quản lý nền tảng theo trách nhiệm | Quyền đặc quyền được kiểm soát, cấp có thời hạn và audit |

Role giúp quản lý tập quyền; không nên biến một role thành bypass toàn bộ resource-level checks.

### 6.2. Scope: quyền của client/API

OAuth scopes diễn đạt quyền client được cấp tới API. Ví dụ reservation:read, reservation:create, reservation:cancel, payment:status:read. Scope nên có ý nghĩa rõ và giới hạn theo resource server. Scope rộng như admin:* cần được cân nhắc và kiểm soát chặt. Scope thường không đủ để quyết định chủ sở hữu của một booking cụ thể.

### 6.3. ABAC: quyền theo thuộc tính và ngữ cảnh

Attribute-Based Access Control đánh giá thuộc tính của subject, resource, action và environment/context. Ví dụ:

~~~text
subject.tenantId == reservation.tenantId
subject.userId == reservation.guestId
action == "cancel" && reservation.status == "PENDING"
request.time < reservation.cancellationDeadline
~~~

ABAC phù hợp các quy tắc cần xét owner, tenant, phân loại dữ liệu, trạng thái và thời gian. Chính sách cần minh bạch, có test và tránh viết rải rác không nhất quán trong nhiều endpoint.

### 6.4. Kết hợp nhiều lớp authorization

Một quyết định hợp lệ có thể yêu cầu:

1. Token hợp lệ, audience đúng API.
2. Client có scope reservation:read.
3. User có role phù hợp.
4. Reservation thuộc user/tenant được phép.
5. Trạng thái nghiệp vụ cho phép thao tác.
6. Request không vi phạm policy đặc biệt như dữ liệu bị legal hold hoặc tài khoản bị khóa.

Không nên chỉ kiểm tra role admin ở đầu request rồi bỏ qua các ranh giới khác. Quyền đặc quyền cũng cần xác định phạm vi, audit và quy trình phê duyệt.

## 7. Bảo vệ quyền trên từng object: BOLA/IDOR và BFLA

Một API có thể kiểm tra token và scope đúng nhưng vẫn mắc lỗi **Broken Object Level Authorization (BOLA)**, thường được gọi cùng nhóm vấn đề IDOR. Lỗi xảy ra khi caller thay ID trong URL/body và đọc hoặc thay đổi object mà mình không được phép.

### Ví dụ dễ bị tấn công

~~~http
GET /v1/reservations/rs-1002
Authorization: Bearer <valid-access-token>
~~~

Server tìm reservation theo ID và trả nội dung mà không kiểm tra guest/host/tenant có quyền xem bản ghi. Attacker đổi thành rs-1003 và lấy dữ liệu của người khác.

### Thiết kế an toàn hơn

~~~java
public ReservationView getReservation(
        String reservationId,
        CurrentPrincipal principal) {

    Reservation reservation = repository.findById(reservationId)
        .orElseThrow(NotFoundException::new);

    boolean isGuest = reservation.guestId().equals(principal.userId());
    boolean isAuthorizedHost =
        hostAccessPolicy.canRead(principal, reservation.propertyId());
    boolean isSupportAccess =
        supportPolicy.canReadWithCase(principal, reservation.id());

    if (!(isGuest || isAuthorizedHost || isSupportAccess)) {
        throw new NotFoundException();
    }
    return ReservationView.from(reservation);
}
~~~

Đây là ví dụ pseudocode Java; policy thật cần xét tenant, role, trạng thái và audit. Trả 404 thay cho 403 có thể giảm tiết lộ sự tồn tại của resource trong một số API, nhưng phải nhất quán với hợp đồng và logging nội bộ. Không nên để client tự gửi ownerId rồi coi đó là bằng chứng quyền sở hữu.

**Broken Function Level Authorization (BFLA)** là tình trạng user có quyền thấp gọi được endpoint/chức năng chỉ dành cho vai trò cao hơn, ví dụ POST /admin/refunds. Ẩn nút trên giao diện không phải authorization; API phải kiểm tra quyền ở server cho từng function/action.

| Principal | Resource | Action | Kết quả mong muốn |
|---|---|---|---|
| Guest A | Reservation của A | Read | Allow |
| Guest A | Reservation của B | Read | Deny |
| Host A | Listing của A | Update | Allow trong policy |
| Host A | Listing của B | Update | Deny |
| Support không có case | Hồ sơ nhạy cảm | Read | Deny |
| Support có case và quyền phù hợp | Hồ sơ trong phạm vi case | Read | Allow + audit |
| Guest | Endpoint admin refund | Execute | Deny |

## 8. API Gateway, WAF và bảo vệ lớp mạng

### 8.1. API Gateway là điểm thực thi policy chung

Gateway thường hỗ trợ routing, TLS integration, auth integration, quota, rate limiting, request size limit, một số schema validation, access logs, metrics, correlation ID và custom domain. Nó không thay thế resource authorization và business validation. Gateway có thể biết token mang scope nào nhưng chỉ ứng dụng thường biết reservation thuộc tenant nào và có đủ điều kiện hủy hay không.

### 8.2. WAF và DDoS protection

WAF bảo vệ traffic web/API ở lớp ứng dụng bằng tập rule phát hiện/chặn mẫu request như injection, payload bất thường, bot hoặc rate-based patterns tùy sản phẩm. DDoS protection giảm tác động của volumetric/protocol attacks tại edge/network.

WAF có thể false positive hoặc bỏ lọt payload mới; không sửa lỗi SQL injection trong code, authorization sai hay business logic dễ bị lạm dụng. Rule managed cần được quan sát, tinh chỉnh có kiểm soát và đánh giá false positive. Rate-based WAF không thay quota theo user/tenant. Backend nên chỉ nhận traffic từ đường ingress được thiết kế để tránh bypass WAF.

### 8.3. Network access và private service

API public có thể dùng public edge, trong khi backend, database, queue và internal API đặt trong private network. Service-to-service access nên giới hạn theo source/destination, identity và port thực tế; private IP không tự làm kết nối đáng tin.

Nếu dùng mTLS/service mesh, cần quản lý CA, certificate issuance/rotation, peer identity và policy. mTLS chứng minh danh tính ở lớp transport theo trust configuration; ứng dụng vẫn cần authorization cho hành động.

## 9. Giới hạn tốc độ, quota và chống lạm dụng

Rate limiting bảo vệ năng lực hệ thống và giúp phân bổ tài nguyên công bằng. Có thể áp dụng nhiều tầng:

| Tầng | Khóa giới hạn | Mục đích |
|---|---|---|
| Edge/WAF | IP/prefix, request pattern | Giảm flood và hành vi bot đơn giản |
| API Gateway | API key, route, stage, client | Bảo vệ backend khỏi traffic vượt ngưỡng |
| Identity/application | User, tenant, partner, operation | Tránh một tài khoản hoặc tenant tiêu thụ bất công |
| Business | Hành động có chi phí/rủi ro cao | Giới hạn gửi OTP, tạo booking, refund, export |
| Dependency | DB connection, payment provider, downstream service | Bảo vệ hệ thống phụ thuộc và giới hạn concurrency |

Rate limit có thể dùng token bucket, leaky bucket hoặc thuật toán cửa sổ tùy implementation. Cần xác định rate, burst, concurrency, quota, response và mức nhất quán của bộ đếm phân tán. Nhiều gateway/region có thể không cập nhật bộ đếm tức thời; phải đánh giá mức sai lệch chấp nhận được.

Không dùng riêng IP làm định danh client: nhiều người dùng có thể chung NAT/proxy, còn attacker có thể phân tán IP. Kết hợp account/client/tenant và risk signal với quyền riêng tư phù hợp.

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 5

{
  "type": "https://api.example.com/problems/rate-limited",
  "title": "Too many requests",
  "status": 429,
  "detail": "Request limit reached. Try again later."
}
~~~

Client nên retry có backoff/jitter và không lặp thao tác ghi nếu thiếu idempotency.

## 10. Kiểm tra đầu vào và ngăn các lớp khai thác phổ biến

### 10.1. Schema validation và mass assignment

API cần kiểm tra kiểu dữ liệu, độ dài, enum, range, format, nested object và giới hạn kích thước trước khi xử lý. Chỉ bind những field client được phép thay đổi; không map toàn bộ JSON request trực tiếp vào entity nhạy cảm.

~~~json
{
  "guestCount": 2,
  "status": "CONFIRMED",
  "ownerId": "attacker-user",
  "isAdmin": true
}
~~~

Nếu backend bind trực tiếp vào entity, attacker có thể thử thay đổi trạng thái, owner hoặc đặc quyền. Dùng request DTO allowlist field và kiểm tra mọi chuyển trạng thái ở business layer.

### 10.2. Injection và truy vấn dữ liệu

- Dùng parameterized query/prepared statement; tránh ghép chuỗi SQL từ input.
- Escape/encode theo đúng output context; validation không thay thế output encoding.
- Giới hạn query complexity, pagination size, filter depth và sort field được phép.
- Với GraphQL, giới hạn depth/complexity, introspection theo policy và batching/alias abuse.
- Không để client điều khiển tùy ý URL server sẽ fetch; kiểm tra SSRF.

### 10.3. SSRF và outbound access

**Server-Side Request Forgery (SSRF)** xảy ra khi API nhận URL/địa chỉ do caller kiểm soát và server truy cập tới đích không mong muốn, ví dụ metadata endpoint hoặc dịch vụ nội bộ.

Biện pháp: ưu tiên allowlist hostname/destination; chặn link-local, loopback, private/internal IP và metadata endpoints khi nghiệp vụ không cần; kiểm tra DNS resolution và redirect; giới hạn egress ở network layer; timeout, response size limit và content-type validation. Bộ lọc URL đơn giản có thể bị bypass qua DNS rebinding, redirect hoặc biểu diễn IP khác nhau; cần kiểm soát cả tầng ứng dụng lẫn egress.

### 10.4. CORS và CSRF

**CORS** là cơ chế trình duyệt kiểm soát JavaScript từ origin nào được đọc response cross-origin. CORS không phải cơ chế xác thực hay authorization; client ngoài trình duyệt có thể gọi API trực tiếp.

Nếu dùng cookie tự động gửi cho phiên người dùng, cần chống **CSRF** bằng SameSite phù hợp, anti-CSRF token/origin validation và các biện pháp theo framework. Với bearer token được gửi chủ động trong Authorization header, mô hình rủi ro CSRF khác nhưng token storage và XSS trở nên quan trọng.

Chỉ cho phép origin cần thiết và kiểm tra preflight/headers/methods. Cấu hình CORS chặt vẫn không thay thế kiểm tra quyền ở API.

## 11. Secrets, key rotation và vòng đời danh tính

Credential lộ thường là vấn đề vòng đời và vận hành, không chỉ lỗi khi tạo secret. Cần quy định:

1. **Issuance:** ai hoặc workload nào được cấp credential; mục đích, scope và owner.
2. **Storage:** secret manager/KMS hoặc secure storage; tránh source control, image layer, command history và plaintext logs.
3. **Use:** short-lived token, workload identity, least privilege và network path phù hợp.
4. **Rotation:** lịch hoặc rotation theo sự kiện; hỗ trợ overlap key cũ/mới để tránh gián đoạn khi cần.
5. **Revocation:** mất thiết bị, nghi ngờ lộ token, nhân sự nghỉ việc, service decommission.
6. **Audit:** ai tạo, đọc, rotate, dùng credential; log có owner và retention phù hợp.

~~~mermaid
flowchart TD
    Start["Chuẩn bị credential mới"] --> Store["Lưu trong secret manager"]
    Store --> Deploy["Cập nhật client/pipeline theo version"]
    Deploy --> Verify["Xác minh request bằng credential mới"]
    Verify --> Revoke["Thu hồi credential cũ"]
    Revoke --> Audit["Ghi nhận và kiểm tra usage bất thường"]
~~~

Không xoay key tùy tiện nếu không có quy trình cập nhật toàn bộ consumer. Một giai đoạn overlap có kiểm soát có thể cần thiết; key cũ phải được thu hồi sau khi xác minh consumer đã chuyển.

## 12. Log, audit và phát hiện hành vi bất thường

API security cần quan sát cả **request outcome** và **hành động có ý nghĩa nghiệp vụ**.

| Nguồn | Trường dữ liệu hữu ích | Mục tiêu |
|---|---|---|
| Gateway access log | Request ID, route, status, latency, client ID đã bảo vệ, source IP theo policy | Tìm endpoint lỗi và pattern traffic |
| Auth/IdP audit | Login success/failure, MFA, grant, token issuance/revocation | Phát hiện account/credential abuse |
| Authorization audit | Subject, action, resource reference, tenant, decision/reason | Điều tra truy cập trái phép |
| Application security event | Validation failure, suspicious object access, rate-limit event | Phát hiện lạm dụng ở tầng nghiệp vụ |
| WAF/DDoS telemetry | Rule, action, source pattern, rate event | Nhận diện traffic độc hại và false positive |
| Secret/IAM audit | Credential read/rotate, role change, policy update | Theo dõi quyền đặc quyền và lộ credential |

Không log bearer token, refresh token, password, client secret, private key hoặc toàn bộ payment payload. Pseudonymize/mask user identifier và IP nếu cần theo chính sách dữ liệu. Bảo vệ log khỏi sửa/xóa trái phép, đặt retention và hạn chế người đọc.

### Cảnh báo hữu ích

- Tăng đột biến login failure, token issuance hoặc refresh bất thường.
- Nhiều request 403/404 tới ID resource tuần tự hoặc có pattern enumeration.
- Một client gọi endpoint đắt tiền vượt ngưỡng quota.
- Scope/resource truy cập không phù hợp baseline của service.
- Thay đổi CORS, WAF, gateway route, IAM role hoặc key rotation ngoài quy trình.
- Token hoặc API key xuất hiện trong log/scanner/secret detection.

Alert cần gắn với owner và hành động. Một số 401/403 đơn lẻ là traffic bình thường; cần threshold, baseline và correlation để tránh false alarm.

## 13. Kiến trúc tham khảo cho nền tảng đặt phòng

Giả sử hệ thống có Web/Mobile client, Booking API, Payment API, Notification worker và database. Người dùng đọc booking của mình; host quản lý listing; nhân viên hỗ trợ có quyền giới hạn theo case.

~~~mermaid
flowchart TD
    Web["Web / Mobile"] --> Edge["CDN / DDoS / WAF"]
    Edge --> GW["API Gateway"]
    GW --> IdP["OIDC Provider"]
    GW --> Booking["Booking API"]
    GW --> Payment["Payment API"]
    Booking --> Policy["Resource + tenant authorization"]
    Policy --> DB[("Booking DB")]
    Booking --> Outbox[("Outbox")]
    Outbox --> Bus[["Event Bus / Queue"]]
    Bus --> Notify["Notification worker"]
    Payment --> Provider["Payment provider"]
    Booking --> Audit["Audit / traces"]
    Payment --> Audit
~~~

### 13.1. Quy tắc xác thực

- Web/Mobile dùng OIDC Authorization Code + PKCE để đăng nhập.
- Access token được phát cho API audience phù hợp; ID Token không dùng làm bearer credential gọi API.
- API xác minh issuer, signature, expiry, audience và các claim cần thiết.
- Worker Notification dùng workload identity hoặc role/service credential ngắn hạn để đọc đúng queue và gọi provider.
- Booking gọi Payment bằng service identity riêng; khi cần tác động thay mặt user, truyền context/ủy quyền có kiểm soát thay vì chia sẻ access token người dùng tùy tiện.

### 13.2. Quy tắc phân quyền

| Hành động | Điều kiện tối thiểu |
|---|---|
| Guest đọc booking | Token hợp lệ + scope read + guest/tenant sở hữu booking |
| Guest hủy booking | Owner hoặc policy actor phù hợp + trạng thái còn hủy được + deadline hợp lệ |
| Host xem booking liên quan | Host có quyền đối với property tương ứng + trường dữ liệu được phép xem |
| Support đọc thông tin nhạy cảm | Role phù hợp + ticket/case được gắn + audit và masking |
| Notification gửi email | Workload identity được phép đọc queue và dùng secret/provider credential cần thiết |
| Payment capture/refund | Service/user role phù hợp + trạng thái giao dịch hợp lệ + idempotency |

### 13.3. Bảo vệ API công khai

- WAF và DDoS protection ở edge; gateway có payload size limit, route policy, authentication integration và quota.
- Rate limit theo client, user, tenant và hành động đắt tiền.
- Backend chỉ nhận traffic từ gateway/private ingress phù hợp; DB không public.
- Request schema allowlist, validation và output filtering.
- Egress payment provider được kiểm soát; TLS và credential rotation.
- Audit event ghi quyết định nhạy cảm, không ghi token hoặc dữ liệu thanh toán đầy đủ.

## 14. Các tình huống tấn công và cách kiểm chứng

| Tình huống | Kiểm chứng | Kiểm soát kỳ vọng |
|---|---|---|
| Token hợp lệ nhưng sai audience | Dùng token dành cho API khác gọi endpoint | API từ chối |
| Token hết hạn hoặc chữ ký sai | Dùng expired/tampered token trong test | 401, không xử lý nghiệp vụ |
| BOLA/IDOR | User A thay resource ID sang bản ghi của B | Deny, không lộ dữ liệu |
| BFLA | User thường gọi endpoint admin/refund | Deny ở server |
| Tenant breakout | Client đổi tenant ID trong body/header | Tenant lấy từ trusted context và kiểm tra quyền |
| Mass assignment | Thêm role, ownerId, status vào request | Field không được phép bị reject/ignore an toàn |
| Credential stuffing/brute force | Tạo pattern login fail có kiểm soát trong test | Rate/risk control, alert, không khóa nhầm user hàng loạt |
| API abuse | Gọi endpoint export/search đắt tiền với concurrency cao | Quota, page limit, concurrency cap, alert |
| SSRF | Thử URL trỏ tới metadata/private address trong test cô lập | Request bị chặn theo allowlist/egress control |
| CORS misconfiguration | Origin không được phép gửi request/read response | Browser policy đúng; authorization vẫn ở server |
| Secret leakage | Quét repository, image, logs và pipeline artifacts | Secret detection, revoke/rotate và incident response |

Các phép thử phải nằm trong môi trường và phạm vi được ủy quyền, dùng dữ liệu giả lập; tránh thử payload gây gián đoạn trên production.

## 15. Tích hợp bảo vệ vào vòng đời phát triển

Một quy trình API an toàn không chỉ là security review trước release. Có thể tích hợp:

1. **Design:** data flow, trust boundary, threat modeling, scope/role/resource policy và abuse cases.
2. **Build:** dependency scanning, secret scanning, SAST và schema/contract validation.
3. **Test:** unit tests cho policy, negative authorization tests, API security tests, fuzz/input validation và rate-limit tests.
4. **Deploy:** IaC policy checks, least-privilege pipeline identity, secrets injection, WAF/gateway config review.
5. **Operate:** access/audit logs, SLO, abuse detection, key rotation, incident response và periodic access review.
6. **Retire:** thu hồi client, OAuth grants, API keys, certificates, service accounts, webhook subscriptions và secrets.

### Các nguyên tắc review

- Mọi endpoint có mô tả authentication requirement và authorization rule.
- API phân biệt public/anonymous, user-authenticated, partner và workload-to-workload.
- Mọi resource ID từ client được kiểm tra ownership/tenant relationship tại server.
- Token audience và scope được ràng buộc đúng API; refresh token không đi vào log/browser storage tùy tiện.
- Gateway và WAF có quota, payload/rule policy nhưng không thay business authorization.
- Service identity, secret, certificate và permission có owner/vòng đời rõ.
- Log có thể điều tra nhưng không làm lộ dữ liệu xác thực.

## 16. Đánh đổi theo tư duy Well-Architected

| Góc nhìn | Quyết định | Lợi ích và đánh đổi |
|---|---|---|
| **Security** | OAuth/OIDC, workload identity, least privilege, BOLA checks, WAF | Giảm truy cập trái phép; tăng quản lý policy, key và false positive |
| **Reliability** | Token validation cache có giới hạn, IdP fallback strategy, rate/concurrency controls | Giảm phụ thuộc và quá tải; cache có thể làm chậm nhận biết revocation |
| **Performance efficiency** | Gateway policy phù hợp, JWKS cache, authorization query tối ưu | Giảm latency/chi phí introspection; cần xử lý key rotation và cache invalidation |
| **Cost optimization** | Phân tầng WAF/log retention, quota và chống abuse | Hạn chế chi phí request độc hại; quan sát đầy đủ vẫn cần ngân sách |
| **Operational excellence** | Policy-as-code, audit, dashboards, runbooks, key lifecycle automation | Dễ kiểm soát và điều tra; cần owner và quy trình ngoại lệ |
| **Sustainability** | Chặn traffic rác sớm, tránh xử lý request vô ích | Giảm compute và data transfer; rule không chính xác có thể chặn user hợp lệ |

Ví dụ, kiểm tra token tại gateway giúp chặn token sai sớm, giảm tải backend. Tuy nhiên nếu gateway cache JWKS quá lâu, token mới có thể bị từ chối khi key rotation; nếu cache token introspection quá lâu, token bị thu hồi có thể được chấp nhận quá thời gian mong muốn. Cần chọn TTL theo threat model, issuer behavior và yêu cầu vận hành.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng ID Token để gọi API | Nhầm credential dành cho client với access token | Dùng access token đúng audience/resource |
| Chỉ decode JWT, không verify signature | Attacker có thể sửa claim | Verify chữ ký, issuer, audience, expiry và profile |
| API key được coi như danh tính người dùng | Không kiểm soát ownership/tenant | Authentication riêng và authorization trên resource |
| Kiểm tra role ở UI | Gọi endpoint trực tiếp vẫn vượt quyền | Enforcement ở server từng endpoint/action |
| Kiểm tra quyền khi list nhưng không khi get/update theo ID | BOLA/IDOR | Object-level authorization cho mọi thao tác |
| Tin tenantId client gửi | Tenant breakout | Tenant context lấy từ identity và kiểm tra resource |
| Gateway xác thực nên backend bỏ qua authorization | Người dùng có thể truy cập object không thuộc quyền | Resource-level policy ở service sở hữu dữ liệu |
| Nhúng client secret trong mobile/browser | Credential bị trích xuất | Public client dùng PKCE; backend dùng secret manager |
| CORS được xem là firewall | Non-browser client vẫn gọi API | AuthN/AuthZ và rate limits ở server |
| WAF được xem là giải pháp cho mọi lỗ hổng | Business logic/API authorization vẫn lỗi | SAST, test và security review theo endpoint |
| Token/API key xuất hiện trong log | Credential bị lộ qua hệ thống quan sát | Redaction, log allowlist và secret scanning |
| Retry API ghi không có idempotency | Có thể tạo thao tác trùng | Idempotency key và trạng thái operation |

## 18. Checklist nghiệm thu API công khai

### Danh tính và token

- [ ] Đã phân biệt user identity, client identity và workload identity.
- [ ] Web/mobile dùng flow phù hợp như Authorization Code + PKCE.
- [ ] Không dùng ID Token thay access token; API kiểm tra đúng issuer/audience/signature/expiry.
- [ ] Scope, role và client permission có phạm vi tối thiểu.
- [ ] Refresh token, client secret, API key và certificate có storage, rotation, revocation và owner.

### Authorization

- [ ] Mỗi endpoint/action có policy rõ, thực thi tại server.
- [ ] Mọi object ID/tenant ID được kiểm tra ownership và relationship.
- [ ] Có negative tests cho BOLA/IDOR, BFLA, tenant breakout và mass assignment.
- [ ] Hành động đặc quyền có audit và cơ chế phê duyệt thích hợp.
- [ ] Service-to-service chỉ được gọi đúng API/resource cần thiết.

### API protection

- [ ] TLS và certificate lifecycle được quản lý; backend origin không bypass điểm vào.
- [ ] WAF/DDoS, gateway, payload limit và schema validation được cấu hình phù hợp.
- [ ] Rate limit/quota áp dụng ở tầng thích hợp; DB/downstream concurrency được bảo vệ.
- [ ] CORS/CSRF được thiết kế theo kiểu credential/client thực tế.
- [ ] SSRF, injection, pagination/query complexity và abuse cases được kiểm tra.

### Vận hành

- [ ] Gateway, IdP, authorization, WAF và secret audit có thể truy vết.
- [ ] Log không chứa token/password/secret và có retention/access policy.
- [ ] Alert có owner và runbook cho credential abuse, authorization anomaly và traffic spike.
- [ ] Có quy trình rotate/revoke credential, disable client và xử lý token leakage.
- [ ] Có dashboard về latency, 4xx/5xx, 401/403, throttling và business outcomes.

## 19. Bài tập thực hành

**Bối cảnh:** Một nền tảng cho thuê chỗ ở công khai API cho Web, Mobile và đối tác đại lý. API hỗ trợ xem listing, tạo reservation, hủy reservation, xem payment status và endpoint hỗ trợ khách hàng. Gần đây có sự cố user thay ID trong URL để đọc booking của người khác; đối tác đại lý có lúc vượt quota; một API key bị commit nhầm lên repository.

Hãy thiết kế mô hình bảo vệ:

1. Phân loại caller: end user, partner client, internal workload và support agent.
2. Chọn flow OAuth/OIDC hoặc workload identity cho từng caller.
3. Định nghĩa audience, scopes và roles phù hợp; giải thích quyền nào cần kiểm tra thêm ở resource level.
4. Viết ma trận authorization cho get/cancel reservation, payment status và support access.
5. Đề xuất kiểm tra token, key rotation và quy trình thu hồi API key đã lộ.
6. Thiết kế Gateway/WAF, quota, rate limits theo IP/client/user/tenant và giới hạn concurrency.
7. Nêu biện pháp cho BOLA, BFLA, mass assignment, SSRF và log leakage.
8. Xác định audit fields, alert và runbook khi có dấu hiệu truy cập chéo tenant.
9. Đề xuất test âm tính (negative tests) và tiêu chí nghiệm thu trước khi release.

**Gợi ý tự kiểm tra:** Không chỉ thêm role vào token rồi coi sự cố BOLA đã được giải quyết. Reservation API cần xác minh quan hệ giữa principal và reservation ở server. Partner API key có thể hỗ trợ nhận diện client/quota nhưng không thay credential và quyền theo hợp đồng. Khi key lộ, phải xác định phạm vi usage, revoke/rotate, kiểm tra log và loại bỏ key khỏi các artifact có thể truy cập.

## 20. Ghi nhớ

**Authentication xác định caller; authorization quyết định caller được làm gì trên resource nào; API protection giảm lạm dụng và giới hạn tác động của request.** OAuth 2.0/OIDC, workload identity, mTLS, API Gateway, WAF, rate limit và audit giải quyết các lớp khác nhau và phải được cấu hình theo trust boundary cụ thể.

Một API an toàn không dừng ở việc token hợp lệ. Nó cần kiểm tra đúng audience và scope, xác minh quyền trên từng object/tenant, xác thực workload riêng, kiểm soát traffic và đầu vào, bảo vệ credential, ghi audit có giới hạn dữ liệu và kiểm thử negative cases. Các kiểm soát phải được vận hành và đo lường liên tục để cân bằng bảo mật với trải nghiệm, độ tin cậy, hiệu năng, khả năng mở rộng và chi phí.
