# Token scope: thiết kế và thực thi quyền truy cập tối thiểu

> **Chương:** Token authentication  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích scope trong access token, cách giới hạn quyền theo API và tài nguyên, cách phân biệt scope với role/audience, và cách kiểm tra quyền token an toàn ở resource server.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích scope là gì, scope được yêu cầu/cấp/phát hành/sử dụng ở đâu trong OAuth 2.0.
2. Phân biệt scope với authentication, role, permission, audience, resource indicator và client identity.
3. Thiết kế scope theo hành động và tài nguyên với nguyên tắc least privilege.
4. Hiểu mối quan hệ giữa user consent, client permission, delegated access và service-to-service access.
5. Xác minh scope trong JWT hoặc opaque access token đúng cách, đồng thời kiểm tra audience và trạng thái token.
6. Thiết kế downscoping, token exchange, token lifetime, revocation và policy khi scope thay đổi.
7. Triển khai kiểm tra scope ở Java/Spring và xây dựng ma trận kiểm thử chống privilege escalation.

## 2. Token scope là gì?

Trong OAuth 2.0, **scope** là cách client biểu đạt phạm vi truy cập mà nó muốn được cấp cho một access token. Authorization server quyết định scope thực tế được cấp dựa trên client, resource owner, chính sách, consent và các điều kiện khác.

Ví dụ, một ứng dụng lịch muốn đọc sự kiện của người dùng:

~~~text
Client yêu cầu:
scope = calendar.events.read

Authorization server đánh giá:
- Client có được phép yêu cầu scope này không?
- User có consent hoặc chính sách tổ chức cho phép không?
- Scope có phù hợp với resource/audience không?
- Có giới hạn bổ sung theo tenant, tài khoản hoặc thời gian không?

Access token được cấp:
scope = calendar.events.read
~~~

Resource server nhận access token và kiểm tra scope có đủ cho endpoint/hành động hiện tại hay không. Nếu token chỉ có calendar.events.read, API không nên cho phép tạo, sửa hoặc xóa sự kiện.

**Scope không phải mật khẩu, không phải danh tính và không tự chứng minh người dùng đã xác thực bằng MFA.** Scope biểu đạt phạm vi ủy quyền được token mang theo theo mô hình của authorization server.

## 3. Scope trả lời “được làm gì?”, không trả lời “ai?” hoặc “ở đâu?”

Các khái niệm liên quan cần được tách biệt:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Subject** | Ai là chủ thể mà token đại diện? | sub = user-104 |
| **Client** | Ứng dụng nào xin token? | client_id = calendar-web |
| **Scope** | Token được cấp phạm vi hành động nào? | calendar.events.read |
| **Audience** | Token được phát hành cho resource server nào? | aud = calendar-api |
| **Role** | Principal có vai trò nào trong tổ chức/tenant? | EDITOR, BILLING_ADMIN |
| **Permission** | Principal được làm hành động nào trên tài nguyên nào? | invoice:read trên INV-42 |
| **Authentication assurance** | Danh tính đã được xác thực theo mức/phương thức nào? | MFA/passkey theo policy |
| **Resource indicator** | Client muốn token dành cho resource nào? | URI định danh API hoặc resource |

Một token có scope invoices.read nhưng audience là profile-api không nên được chấp nhận tại billing-api. Một token có audience đúng và scope invoices.read cũng không tự động cho phép đọc mọi hóa đơn; authorization vẫn có thể cần kiểm tra tenant, ownership, trạng thái và quan hệ với đối tượng.

Scope thường là một phần của quyết định ủy quyền, không phải toàn bộ policy. API phải hiểu scope theo hợp đồng giữa client, authorization server và resource server.

## 4. Vòng đời scope trong OAuth 2.0

Scope xuất hiện qua nhiều bước:

1. **Client registration:** authorization server xác định client được phép yêu cầu những scope nào.
2. **Authorization request:** client yêu cầu một hoặc nhiều scope cho giao dịch.
3. **Authorization/consent:** authorization server đánh giá policy, user consent và giới hạn tổ chức.
4. **Token issuance:** authorization server cấp access token với tập scope được chấp thuận.
5. **Resource access:** client gửi access token tới resource server.
6. **Token validation:** resource server xác minh token, audience/resource, thời hạn, trạng thái và scope.
7. **Authorization:** API kiểm tra scope cùng principal, action, resource, tenant và policy.
8. **Change/revocation:** quyền có thể thay đổi; token có thể hết hạn, bị thu hồi hoặc cần cấp lại với scope mới.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Resource owner
    participant Client as OAuth client
    participant AS as Authorization server
    participant API as Resource server

    Client->>AS: Authorization request + requested scope
    AS->>AS: Check client, resource, policy and consent
    AS-->>User: Consent / authorization step if required
    User-->>AS: Approve or deny
    AS-->>Client: Authorization code
    Client->>AS: Exchange code (PKCE/client authentication as applicable)
    AS-->>Client: Access token with granted scope
    Client->>API: Request + access token
    API->>API: Validate token, audience, expiry and scope
    API->>API: Check object/tenant authorization
    API-->>Client: Allowed response or access denied
~~~

Client yêu cầu scope không có nghĩa authorization server phải cấp toàn bộ. Resource server cũng không nên tin scope được gửi riêng trong request body/header bên cạnh token.

## 5. Cách biểu diễn scope

OAuth 2.0 core định nghĩa tham số scope là danh sách các chuỗi scope phân tách bằng dấu cách ASCII. Ý nghĩa cụ thể của từng chuỗi do authorization server và resource server thống nhất.

Ví dụ trong authorization request:

~~~http
GET /authorize?
  response_type=code&
  client_id=calendar-web&
  redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&
  scope=openid%20profile%20calendar.events.read&
  state=opaque-state
~~~

Ví dụ access token dạng JWT có claim scope:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-104",
  "aud": "calendar-api",
  "scope": "calendar.events.read calendar.settings.read",
  "exp": 2000000000
}
~~~

Trong JWT access token profile, scope có thể được biểu diễn theo quy ước của profile; một số authorization server dùng claim scope dạng chuỗi, một số hệ thống nội bộ có thể dùng định dạng khác. Resource server phải tuân theo hợp đồng token cụ thể, không đoán cấu trúc.

### Scope không phải URL hoặc tên endpoint tùy ý

Scope nên là từ vựng quyền ổn định và có tài liệu. Tránh tạo scope theo mọi URL/ID động như GET:/invoices/INV-42 hoặc read:user-104. Các điều kiện đối tượng cụ thể nên được kiểm tra ở authorization layer hoặc biểu diễn qua cơ chế resource-specific authorization phù hợp.

## 6. Thiết kế scope theo least privilege

Một thiết kế tốt cấp đúng hành động mà client cần, trong đúng API và khoảng thời gian cần thiết.

Ví dụ cho API quản lý hóa đơn:

| Scope | Phạm vi minh họa |
|---|---|
| invoices.read | Đọc hóa đơn được policy cho phép |
| invoices.create | Tạo hóa đơn theo quy tắc nghiệp vụ |
| invoices.update | Cập nhật trường được phép |
| invoices.submit | Gửi hóa đơn vào quy trình phê duyệt |
| invoices.approve | Thực hiện hành động phê duyệt nếu principal có đủ quyền |
| invoices.export | Xuất dữ liệu hóa đơn; có thể cần assurance và policy bổ sung |

Không nên tạo một scope duy nhất invoices.full_access cho mọi ứng dụng nếu chúng chỉ cần đọc hoặc tạo. Scope quá rộng làm tăng tác động khi token bị đánh cắp hoặc client bị xâm nhập.

### Tách quyền đọc và ghi

Phân biệt read/write giúp client chỉ được cấp quyền cần thiết:

- Ứng dụng dashboard chỉ cần invoices.read.
- Worker tạo hóa đơn có thể chỉ cần invoices.create.
- Ứng dụng phê duyệt cần invoices.approve, nhưng vẫn phải kiểm tra người phê duyệt có được phép với hóa đơn cụ thể hay không.
- Công cụ hỗ trợ có thể cần quyền đọc giới hạn, không nên có quyền xóa hoặc sửa.

Scope đặt tên rõ ràng, có versioning và chủ sở hữu. Khi thay đổi semantics, không âm thầm tái sử dụng tên scope cũ với quyền rộng hơn.

## 7. Scope có giới hạn theo resource/audience

Scope trả lời phạm vi hành động, còn audience/resource xác định token được dùng ở đâu. Hai chiều này bổ sung cho nhau.

~~~text
Access token:
  subject = user-104
  audience = billing-api
  scope = invoices.read

Ý nghĩa:
  Token dành cho billing-api.
  Có phạm vi đọc hóa đơn theo policy.
  Không được dùng ở identity-api hoặc admin-api.
~~~

Nếu nhiều API dùng chung một authorization server, không nên tạo một token audience quá rộng cho mọi dịch vụ nếu có thể cấp token riêng theo resource. Một token dành cho API A không nên được API B chấp nhận chỉ vì chữ ký cùng issuer hợp lệ.

### Resource indicators

OAuth Resource Indicators (RFC 8707) cho phép client chỉ rõ resource mà nó muốn access token hướng tới. Authorization server có thể dùng thông tin này để phát hành token phù hợp với resource, thay vì chỉ dựa vào scope chung.

Resource indicator không thay thế audience validation. Resource server vẫn cần kiểm tra token có thực sự dành cho nó theo profile/issuer đã thống nhất.

## 8. Scope, role và permission trong hệ thống nhiều tenant

Scope thường biểu đạt quyền mà client/token có thể sử dụng; role là thuộc tính hoặc quan hệ của principal trong tổ chức; permission là quyết định cụ thể đối với action/resource.

Ví dụ:

~~~text
Access token:
  sub = user-104
  aud = billing-api
  scope = invoices.read

Application state:
  account = A-104
  tenant = T1
  role = VIEWER

Request:
  GET /tenants/T1/invoices/INV-42

Authorization:
  1. Token hợp lệ và audience đúng.
  2. Scope invoices.read có mặt.
  3. Principal là thành viên tenant T1.
  4. Role/policy cho phép đọc INV-42.
  5. Tài nguyên không bị hạn chế bởi trạng thái nghiệp vụ.
~~~

Nếu scope đúng nhưng user không thuộc tenant, API vẫn từ chối. Nếu user có role ADMIN nhưng token thiếu scope cần thiết hoặc token dành cho API khác, API cũng không nên tự mở rộng quyền.

Không nhét toàn bộ ma trận quyền đối tượng vào scope. Scope quá chi tiết và thay đổi liên tục sẽ làm token lớn, khó quản lý consent và dễ lỗi khi dữ liệu quyền thay đổi.

## 9. Scope trong delegated access và service-to-service

### 9.1. Delegated access — client hành động thay user

Trong authorization code flow, client có thể nhận access token với scope được cấp theo sự đồng ý/chính sách của resource owner. Resource server cần hiểu token đại diện cho ai, client nào và phạm vi ủy quyền là gì.

Ví dụ:

~~~text
User: An
Client: report-portal
Resource: document-api
Granted scope: documents.read

Ý nghĩa:
report-portal có thể yêu cầu đọc tài liệu thay An,
nhưng API vẫn kiểm tra An có quyền trên tài liệu cụ thể.
~~~

### 9.2. Client credentials — service tự gọi API

Trong Client Credentials Grant, client đại diện chính nó, không có resource owner end-user trong grant đó. Scope được cấp là quyền của client/service theo chính sách authorization server.

Ví dụ:

~~~text
Client: nightly-report-worker
Audience: reporting-api
Scope: reports.generate
Subject/client identity: service principal
~~~

Không ghi nhận service token như thể nó chứng minh một người dùng cụ thể đã đăng nhập. Nếu service cần hành động thay user, phải dùng cơ chế delegation/token exchange phù hợp và giữ rõ actor service lẫn subject được đại diện.

## 10. User consent không phải lúc nào cũng là nguồn cấp quyền duy nhất

Authorization server có thể quyết định scope dựa trên:

- Danh sách scope client được đăng ký.
- User consent hoặc consent đã cấp trước.
- Chính sách tổ chức/admin consent.
- Nhóm người dùng, tenant, loại tài khoản và trạng thái.
- Resource/audience và mục đích token.
- Assurance của phiên, thời điểm xác thực và rủi ro.
- Hạn chế theo thời gian, quota hoặc điều kiện nghiệp vụ.

Một client yêu cầu admin.users.write không có nghĩa user có quyền cấp scope đó. Authorization server phải kiểm tra client registration và policy. Với tài khoản doanh nghiệp, administrator có thể cấp hoặc thu hồi consent cho toàn tenant; user thông thường không được vượt chính sách này.

### Requested scope và granted scope

Luôn phân biệt:

- **Requested scope:** client muốn được cấp.
- **Granted scope:** authorization server thực sự cấp.
- **Effective permission:** quyền mà resource server quyết định cho request cụ thể sau khi xét scope, principal, resource và policy.

Client không nên giả định mọi scope đã yêu cầu đều được cấp. Sau khi nhận token, client cần xử lý đúng trường hợp quyền bị giảm hoặc bị từ chối.

## 11. Scope trong JWT và opaque access token

### 11.1. JWT access token

JWT có thể mang scope trong claim. Resource server thường xác minh:

1. Chữ ký theo thuật toán và khóa được tin cậy từ issuer.
2. Issuer đúng authorization server đã cấu hình.
3. Audience/resource đúng API đang xử lý.
4. Thời hạn exp, nbf và các điều kiện thời gian liên quan.
5. Token type/profile và các claim bắt buộc.
6. Scope có mặt và đúng semantics cho endpoint.
7. Trạng thái account/token nếu hệ thống có cơ chế kiểm tra bổ sung.

Không chỉ Base64-decode payload rồi tin scope. JWT parse được không đồng nghĩa chữ ký hợp lệ.

### 11.2. Opaque access token

Opaque token là chuỗi không chứa claim có thể đọc trực tiếp theo cách JWT thường được dùng. Resource server có thể xác minh thông qua introspection endpoint hoặc cơ chế tra cứu server-side.

Kết quả introspection có thể cho biết token còn active, scope, client, subject, audience hoặc thời hạn tùy profile. Resource server phải xác thực với introspection endpoint, bảo vệ kết quả/cache và chỉ tin authorization server được cấu hình.

### 11.3. Không suy đoán token type

ID token, access token, refresh token và API key có mục đích khác nhau. Resource server không nên nhận bất kỳ JWT hợp lệ nào như access token. Phải kiểm tra đúng loại token, issuer, audience và profile.

## 12. Token scope không thay thế kiểm tra đối tượng

Một scope như documents.read thường chỉ cho phép thực hiện loại hành động đọc trong API. Nó không tự nói rằng user được đọc mọi tài liệu.

Ví dụ, API nhận:

~~~http
GET /api/tenants/T1/documents/DOC-42
Authorization: Bearer <access-token>
~~~

Resource server cần kiểm tra:

- Token có hợp lệ, đúng audience và còn hiệu lực?
- Token có scope documents.read?
- Subject đã xác minh ánh xạ tới account nào?
- Account có membership ở tenant T1?
- DOC-42 có thuộc tenant T1 và có được chia sẻ cho account này không?
- Có chính sách che dữ liệu, legal hold hoặc trạng thái khóa nào không?

Đây là cách tránh **Broken Object Level Authorization (BOLA/IDOR)**. Nếu API chỉ kiểm tra scope mà không kiểm tra quyền đối tượng, token có scope đọc có thể trở thành chìa khóa đọc dữ liệu của mọi tenant.

## 13. Downscoping: cấp token hẹp hơn

**Downscoping** là giảm phạm vi quyền của token mới so với quyền ban đầu. Ví dụ, một backend có token đọc/ghi tài liệu nhưng một tác vụ chỉ cần đọc metadata; backend có thể xin token mới chỉ với documents.metadata.read nếu authorization server hỗ trợ.

~~~text
Token ban đầu:
  aud = document-api
  scope = documents.read documents.write documents.delete

Token downscoped:
  aud = document-api
  scope = documents.metadata.read

Tác dụng:
  Giới hạn tác động nếu token dùng cho tác vụ phụ bị lộ.
~~~

Downscoping phải được authorization server kiểm soát. Client không thể tự xóa một scope khỏi chuỗi token rồi tuyên bố token mới có quyền thấp hơn; token có chữ ký hoặc trạng thái do server quản lý phải được phát hành lại đúng quy trình.

### Token exchange và delegation

OAuth Token Exchange (RFC 8693) có thể hỗ trợ đổi một token đầu vào lấy token mới với subject/actor, audience và scope phù hợp theo policy. Resource server cần hiểu ai là actor, ai là subject được đại diện và token mới được cấp cho resource nào.

Token exchange không tự động an toàn chỉ vì dùng RFC; cần xác thực client, giới hạn token được đổi, tránh confused deputy và ghi nhận delegation rõ ràng.

## 14. Scope thay đổi, token lifetime và revocation

Scope được ghi trong access token thường phản ánh quyết định tại thời điểm phát hành. Nếu quyền user bị thu hồi sau đó, token self-contained vẫn có thể được chấp nhận cho đến khi hết hạn nếu resource server không có cơ chế kiểm tra trạng thái mới.

Các cách quản lý:

- **Short-lived access token:** giảm thời gian token cũ còn hiệu lực.
- **Refresh token rotation/revocation:** kiểm soát khả năng cấp token mới; refresh token cần được bảo vệ nghiêm ngặt.
- **Introspection:** resource server hỏi trạng thái token theo nhu cầu hoặc cache có thời hạn.
- **Revocation endpoint:** client hoặc hệ thống quản trị yêu cầu thu hồi token theo RFC 7009; hiệu lực ở resource server phụ thuộc kiến trúc và khả năng đồng bộ trạng thái.
- **Event-driven revocation:** phát sự kiện thu hồi/disable account tới các dịch vụ; cần xử lý mất sự kiện và đồng bộ lại.
- **Policy re-evaluation:** kiểm tra quyền đối tượng/tenant ở mỗi request hoặc theo cache ngắn hạn.

Không nên đặt token lifetime quá dài chỉ để giảm số lần refresh. Ngược lại, token quá ngắn có thể tăng tải và làm trải nghiệm kém; chọn thời hạn theo rủi ro, khả năng revoke và loại client.

## 15. Scope naming và quản trị thay đổi

Một bộ scope cần từ vựng nhất quán, dễ đọc, dễ kiểm thử và có owner.

Ví dụ naming:

~~~text
resource.action

invoices.read
invoices.create
invoices.update
invoices.approve
users.profile.read
users.profile.update
reports.generate
~~~

Đây là quy ước thiết kế, không phải cú pháp bắt buộc của OAuth. Một số hệ thống dùng URI scope hoặc namespace riêng; điều quan trọng là semantics phải được công bố và nhất quán.

Quy tắc quản trị:

- Mỗi scope có mô tả, owner, resource server và endpoint/action tương ứng.
- Không tái sử dụng tên scope cũ với quyền rộng hơn mà không có migration rõ.
- Phân biệt scope dành cho user-delegated và scope dành cho machine/service nếu policy khác nhau.
- Có versioning hoặc chiến lược deprecation khi semantics thay đổi.
- Không cấp scope mặc định quá rộng chỉ để client cũ hoạt động.
- Theo dõi scope hiếm dùng, scope không còn owner hoặc không còn endpoint sử dụng.
- Tài liệu hóa consent screen bằng ngôn ngữ người dùng hiểu, không chỉ hiển thị chuỗi kỹ thuật.

## 16. Java/Spring: kiểm tra scope ở resource server

Spring Security OAuth2 Resource Server có thể xác minh JWT và ánh xạ scope thành authority theo quy ước mặc định SCOPE_. Ví dụ:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                .hasAuthority("SCOPE_invoices.read")
            .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                .hasAuthority("SCOPE_invoices.create")
            .requestMatchers(HttpMethod.PATCH, "/api/invoices/**")
                .hasAuthority("SCOPE_invoices.update")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Cấu hình trên là ví dụ; ứng dụng vẫn phải thiết lập issuer/JWK và kiểm tra audience dành cho API. Chỉ bật JWT decoder mà không xác minh audience đúng có thể khiến API nhận token phát hành cho resource khác.

Một controller/service nên tiếp tục kiểm tra quyền đối tượng:

~~~java
@PreAuthorize("hasAuthority('SCOPE_invoices.read')")
InvoiceView readInvoice(UUID invoiceId, UUID tenantId) {
    Account account = currentPrincipal.requireAccount();
    Tenant tenant = tenants.requireMembership(account.id(), tenantId);
    Invoice invoice = invoices.findByIdAndTenant(invoiceId, tenant.id())
        .orElseThrow(ResourceNotFoundException::new);

    if (!policy.canReadInvoice(account, tenant, invoice)) {
        throw new AccessDeniedException("Access denied");
    }
    return InvoiceView.from(invoice);
}
~~~

Các thành phần currentPrincipal, repository và policy là phần minh họa do ứng dụng định nghĩa. Không lấy scope từ query/body/header do client tự gửi. Scope phải đến từ access token đã xác minh hoặc kết quả introspection đáng tin.

### Kiểm tra audience

Tùy phiên bản Spring Security, có thể thêm validator để kiểm tra claim aud ngoài issuer/time validation. Ví dụ khái niệm:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains("billing-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Invalid audience", null)
        );
~~~

Đoạn validator cần được kết hợp với decoder/validator hiện có, không thay thế issuer, timestamp và chữ ký validation. Cấu hình cụ thể phụ thuộc phiên bản framework và profile token của authorization server.

## 17. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Coi scope là role | Quyền client/token bị nhầm với vai trò nghiệp vụ của user | Tách scope, role và object permission |
| Chỉ kiểm tra scope, bỏ qua audience | Token dành cho API khác có thể bị chấp nhận | Kiểm tra audience/resource cho từng API |
| Cấp full access cho mọi client | Token bị lộ gây tác động lớn | Chia scope theo action và least privilege |
| Tin requested scope là granted scope | Client tự giả định quyền chưa được cấp | Đọc granted scope từ token/response theo profile |
| Tin scope trong body/header | Caller tự khai quyền | Chỉ dùng claim từ token đã xác minh/introspection |
| Không kiểm tra tenant/object | BOLA/IDOR dù scope hợp lệ | Kiểm tra principal, tenant, ownership và policy |
| Dùng access token làm ID token hoặc ngược lại | Nhầm mục đích và resource nhận | Xác minh token type, issuer, audience, profile |
| Token sống quá lâu | Quyền bị thu hồi nhưng token còn dùng được | Short lifetime, introspection/revocation và policy refresh |
| Downscope bằng cách sửa payload JWT | Chữ ký không hợp lệ hoặc semantics bị giả | Xin token mới qua authorization server |
| Dùng client credentials nhưng ghi nhận user đã consent | Audit sai actor và quyền | Phân biệt service principal với user delegation |
| Thay semantics scope mà không version/deprecate | Client cũ có thể nhận quyền rộng bất ngờ | Quản trị scope và migration có kiểm soát |

## 18. Ma trận kiểm thử token scope

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Token hợp lệ có invoices.read gọi GET trong đúng audience | Qua scope check; tiếp tục kiểm tra object/tenant |
| Token chỉ có invoices.read gọi POST tạo hóa đơn | Từ chối |
| Token có scope đúng nhưng audience là API khác | Từ chối |
| Token hết hạn hoặc chữ ký sai | Từ chối |
| Client yêu cầu scope rộng nhưng server chỉ cấp scope hẹp | Client chỉ có quyền theo scope đã cấp |
| Caller gửi scope=admin trong body/header | Không thay đổi quyền token |
| User có role ADMIN nhưng token thiếu scope cần thiết | Từ chối theo policy token |
| Token có scope read nhưng user không thuộc tenant | Từ chối |
| User có scope read và tenant membership nhưng không có quyền trên object | Từ chối |
| Client credentials token gọi endpoint chỉ dành cho delegated user | Từ chối hoặc xử lý theo policy service riêng |
| Downscoped token gọi endpoint write | Từ chối |
| Scope bị thu hồi nhưng access token cũ còn sống | Hành vi đúng với chiến lược revocation/lifetime đã thiết kế |
| Introspection endpoint không truy cập được | Fallback theo policy, không tự coi token active |
| Token exchange yêu cầu audience/scope không được phép | Authorization server từ chối |
| Scope đã deprecated | Client mới không được cấp; client cũ được xử lý theo kế hoạch deprecation |
| Scope claim có định dạng không đúng profile | Từ chối an toàn, không parse rộng tùy tiện |

Ngoài status code, cần xác minh dữ liệu thực tế không bị trả về hoặc thay đổi trái quyền. Kiểm thử cả JWT và opaque token nếu hệ thống hỗ trợ hai dạng.

## 19. Tình huống phân tích

### Tình huống A: dashboard chỉ cần đọc nhưng được cấp toàn quyền

Một dashboard chỉ hiển thị hóa đơn nhưng authorization server cấp invoices.full_access vì cấu hình client đơn giản. Nếu token bị lộ, attacker có thể sửa hoặc xóa hóa đơn.

**Phân tích:** scope vượt nhu cầu. Tạo scope đọc riêng, cấp token theo least privilege và giữ quyền sửa/xóa ở client/workflow khác có yêu cầu rõ.

### Tình huống B: scope đúng nhưng sai audience

Một access token có invoices.read được phát cho reporting-api. billing-api chỉ kiểm tra chữ ký và scope nên chấp nhận token.

**Phân tích:** thiếu audience validation. billing-api phải từ chối token không dành cho nó, dù issuer và chữ ký hợp lệ.

### Tình huống C: user đọc dữ liệu tenant khác

Token của An có documents.read và audience đúng. An đổi tenant ID và document ID trong URL để lấy tài liệu của Bình.

**Phân tích:** scope chỉ cấp loại hành động, không tự cấp quyền đối tượng. API phải kiểm tra membership, tenant, ownership/sharing và policy cho tài liệu cụ thể.

### Tình huống D: quyền bị thu hồi nhưng JWT chưa hết hạn

Admin gỡ scope/role của user, nhưng JWT self-contained cũ còn hiệu lực 30 phút.

**Phân tích:** claim trong token là ảnh chụp tại thời điểm cấp. Hệ thống cần quyết định chấp nhận cửa sổ hiệu lực ngắn hay bổ sung introspection, denylist/event revocation hoặc kiểm tra policy server-side.

### Tình huống E: worker gọi thay user

Một worker dùng client credentials với scope documents.read để đọc tài liệu. Audit ghi request như thể An đã đăng nhập và yêu cầu.

**Phân tích:** sai actor attribution. Token đại diện service principal; nếu tác vụ cần quyền của An, phải dùng delegation/token exchange đúng profile, và audit ghi cả service actor lẫn user subject.

## 20. Quy trình thiết kế và vận hành

Trước khi phát hành hoặc thay đổi scope, hãy xác định:

1. Scope thuộc resource server nào và bảo vệ action nào?
2. Client nào được phép yêu cầu scope này; public/confidential và delegated/service khác nhau ra sao?
3. Authorization server dựa trên consent, admin policy, tenant và assurance nào để cấp?
4. Requested scope và granted scope được client xử lý thế nào?
5. Token được ràng buộc audience/resource ra sao?
6. Resource server xác minh issuer, signature, token type, thời hạn, audience và scope thế nào?
7. Có cần thêm kiểm tra object, tenant, owner hoặc trạng thái nghiệp vụ không?
8. Token lifetime, refresh, introspection, revocation và downscoping được thiết kế ra sao?
9. Thay đổi/deprecation scope có owner, versioning, migration và audit không?
10. Có kiểm thử scope escalation, audience confusion, token replay và cross-tenant access không?
11. Log có ghi token/secret không; có thể truy vết client, subject, scope và resource an toàn không?
12. Khi client hoặc user bị thu hồi quyền, thời gian tối đa để resource server ngừng chấp nhận là bao lâu?

## 21. Ghi nhớ trọng tâm

- **Scope biểu đạt phạm vi ủy quyền của access token**, không phải danh tính, role hay bằng chứng MFA.
- **Requested scope khác granted scope.** Authorization server quyết định quyền thực tế theo client, user consent và policy.
- **Scope và audience/resource phải được kiểm tra cùng nhau.** Token dành cho API khác không được chấp nhận chỉ vì có scope trùng tên.
- **Least privilege:** chia quyền đọc/ghi/quản trị, cấp đúng nhu cầu, giới hạn thời gian và resource.
- **Scope không thay object authorization.** API vẫn phải kiểm tra principal, tenant, ownership và quyền trên từng tài nguyên.
- **Phân biệt delegated user token và client credentials/service token.** Audit và policy phải nhận diện đúng actor và subject.
- **Token scope có thể cũ sau khi quyền thay đổi.** Thiết kế lifetime, introspection, revocation và policy refresh phù hợp.
- **Downscoping phải do authorization server cấp token mới**, không phải sửa claim trong token hiện tại.

Scope hữu ích khi nó là hợp đồng quyền rõ ràng giữa client, authorization server và resource server. Kết hợp scope hẹp, audience đúng, xác minh token và authorization theo đối tượng sẽ giảm tác động của token bị lộ hoặc client bị xâm nhập mà vẫn giữ luồng tích hợp dễ quản lý.
