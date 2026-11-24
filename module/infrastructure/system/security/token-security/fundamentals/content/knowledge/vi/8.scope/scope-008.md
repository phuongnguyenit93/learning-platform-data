# Scope trong access token

Một ứng dụng quản lý chi tiêu được người dùng cho phép **đọc hóa đơn**, nhưng không cho phép **xóa hóa đơn**. Khi ứng dụng gọi Invoice API, làm sao API phân biệt hai loại thao tác? Trong OAuth 2.0, **scope** là một cách biểu diễn phạm vi truy cập mà Authorization Server (AS) đã cấp cho access token. Chẳng hạn, token có `invoice:read` có thể được dùng để **yêu cầu** đọc hóa đơn, nhưng không mặc nhiên được dùng để xóa hóa đơn.

Có một giới hạn quan trọng: **scope không phải toàn bộ chính sách phân quyền**. Token có `invoice:read` không đồng nghĩa có quyền đọc **mọi hóa đơn**. API vẫn cần kiểm tra chủ thể, client/actor, tenant, quyền trên từng tài nguyên và trạng thái nghiệp vụ. Ngược lại, quyền sở hữu hóa đơn cũng không khiến một token thiếu scope bắt buộc được phép gọi endpoint.

Trong module **Security Token Security Fundamentals**, bài này tập trung vào cách **scope được yêu cầu, cấp phát, biểu diễn và kiểm tra trong access token**, đặt trong bối cảnh JWT, opaque token, OAuth 2.0/OIDC, audience, vòng đời token và phòng chống lạm dụng. Mục tiêu là thực thi đúng nguyên tắc **least privilege**: chỉ cấp và sử dụng quyền cần thiết, ở API phù hợp, trong giới hạn thực tế của chủ thể.

## 1. Scope là gì và không phải là gì?

**Scope** trong OAuth 2.0 là các chuỗi định danh phạm vi truy cập do **Authorization Server** và **Resource Server** thống nhất cách hiểu. OAuth không áp đặt các giá trị cố định như `invoice:read` hay `payment:create`; đó là tên do hệ thống tự thiết kế.

Ví dụ:

| Scope minh họa | Ý nghĩa theo hợp đồng API | Ví dụ thao tác |
|---|---|---|
| `invoice:read` | Có thể yêu cầu đọc hóa đơn được phép xem | `GET /api/invoices/{id}` |
| `invoice:create` | Có thể yêu cầu tạo hóa đơn | `POST /api/invoices` |
| `invoice:write` | Có thể yêu cầu sửa một số thông tin hóa đơn | `PATCH /api/invoices/{id}` |
| `invoice:approve` | Có thể yêu cầu phê duyệt hóa đơn | `POST /api/invoices/{id}/approve` |
| `report:export` | Có thể yêu cầu xuất báo cáo | `POST /api/reports/export` |

Mỗi scope cần được **định nghĩa chính xác**, ví dụ `invoice:write` có bao gồm thay trạng thái phê duyệt không, hay việc phê duyệt phải cần scope riêng? Nếu không có hợp đồng, hai service có thể diễn giải một tên giống nhau theo hai cách, gây vượt quyền hoặc từ chối sai.

### Phân biệt các khái niệm liên quan

| Thành phần | Trả lời câu hỏi | Vì sao không thay thế scope? |
|---|---|---|
| **Issuer — `iss`** | Ai phát hành token? | Issuer đáng tin không có nghĩa token được cấp mọi quyền |
| **Audience — `aud`** | Token dành cho resource server nào? | Đúng đích nhận chưa nói được phép gọi hành động nào |
| **Subject — `sub`** | Token mô tả chủ thể nào? | Danh tính không tự cấp quyền truy cập |
| **Client — `client_id`** | Client nào được cấp token, theo token profile? | Client được đăng ký không có nghĩa được toàn quyền |
| **Scope — `scope`** | Token đã được cấp phạm vi truy cập nào? | Không tự xác định bản ghi/tenant cụ thể được phép |
| **Role/permission** | Chủ thể có vai trò và quyền nghiệp vụ nào? | Role có thể thay đổi và còn phụ thuộc vào tổ chức, tenant, tài nguyên |
| **Ownership/relationship** | Chủ thể có quan hệ gì với một bản ghi? | Có quan hệ không làm một access token thiếu scope trở nên đủ quyền |

Hãy tưởng tượng scope như **giới hạn năng lực được ghi trên giấy ủy quyền**: giấy chỉ cho phép *loại hành động*, còn bên giữ tài nguyên phải kiểm tra *đúng đối tượng và điều kiện*.

## 2. Scope đi qua OAuth 2.0 như thế nào?

Với luồng có người dùng, client có thể xin một hoặc nhiều scope trong **Authorization Code Flow**. AS xem xét quyền của client, người dùng, chính sách và sự chấp thuận khi áp dụng, rồi cấp **scope thực tế**. Client không thể tự quyết định mình đã được cấp những scope nào chỉ bằng cách gửi tham số `scope`.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Mai (resource owner)
    participant C as Expense App (client)
    participant AS as Authorization Server
    participant API as Invoice API (resource server)
    U->>C: Kết nối tài khoản để xem hóa đơn
    C->>AS: Authorization request: scope=invoice:read invoice:write, PKCE
    AS->>AS: Kiểm client, quyền và chính sách/consent
    U->>AS: Xác thực, xác nhận quyền nếu được yêu cầu
    AS-->>C: Authorization code qua redirect
    C->>AS: Đổi code với code_verifier
    AS-->>C: Access token, scope thực cấp: invoice:read
    C->>API: GET /invoices/42 + access token
    API->>API: Xác minh token, aud, scope và quyền bản ghi
    API-->>C: Trả hóa đơn được phép hoặc từ chối
~~~

Trong ví dụ, client đã **yêu cầu** `invoice:read invoice:write` nhưng AS chỉ **cấp** `invoice:read`. Client không được tự coi yêu cầu ban đầu là quyền đã được cấp. AS có thể cấp tập quyền hẹp hơn theo chính sách, hoặc từ chối nếu điều kiện không phù hợp.

**OAuth 2.0 (RFC 6749)** dùng tham số `scope` dạng chuỗi các scope phân cách bằng dấu cách. Nếu scope cấp thực tế **khác** scope được yêu cầu, AS phải cho client biết scope được cấp trong token response theo quy tắc của giao thức; khi giống nhau, trường phản hồi có thể được lược bỏ trong những trường hợp phù hợp. Trong ứng dụng thực tế, cần tuân thủ profile của AS và kiểm quyền thực tế trong access token/ngữ cảnh AS trả về.

Một phản hồi token minh họa:

~~~json
{
  "access_token": "eyJ...redacted...",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "invoice:read"
}
~~~

Trường `scope` trong **token response** cho client biết scope được cấp; đó không nhất thiết là cấu trúc bên trong access token. Với **opaque access token**, client thường không thể đọc claim nội bộ. Với **JWT access token**, Resource Server có thể kiểm `scope` trong payload đã xác minh nếu token profile dùng biểu diễn đó.

### Scope không đồng nghĩa consent

Scope mô tả phạm vi truy cập do AS cấp. **Consent** là quá trình chủ thể/quản trị viên cho phép client truy cập khi chính sách yêu cầu; không phải lúc nào cũng hiện màn hình consent. AS còn cần kiểm client có quyền dùng grant, phạm vi truy cập và tài nguyên đích không. Một client có scope `invoice:read` không tự có quyền đọc hóa đơn của mọi người dùng.

### Scope trong `client_credentials`

Khi một service chạy định kỳ dùng grant `client_credentials`, không nhất thiết có người dùng cuối:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-authentication-redacted>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=invoice%3Areconcile
~~~

AS có thể cấp scope `invoice:reconcile` cho service theo quyền đã đăng ký. Token này mô tả **quyền service**, không phải bằng chứng một người dùng đã đồng ý cho service thay mặt họ. API cần áp dụng chính sách cho service và không tin một `X-User-Id` tự khai để biến token service thành token người dùng.

## 3. Scope được biểu diễn như thế nào trong access token?

OAuth 2.0 **không bắt buộc** access token phải là JWT. Access token có thể là JWT, opaque token hoặc định dạng được AS và resource server hỗ trợ. **Định dạng token** và **scope được cấp** là hai chiều khái niệm độc lập.

### JWT access token

Với **JWT Profile for OAuth 2.0 Access Tokens (RFC 9068)**, `scope` — khi có — là một **JSON string** chứa các scope phân cách bằng khoảng trắng. Ví dụ payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:mai",
  "aud": "invoice-api",
  "client_id": "expense-web",
  "scope": "invoice:read invoice:create",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "token-001"
}
~~~

Cách diễn giải **sau khi token được xác minh**:

- `iss`: AS phát hành token; Resource Server phải tin issuer theo cấu hình.
- `sub`: subject mà token mô tả theo token profile; có thể là người dùng hoặc service.
- `aud`: API dự kiến nhận token. `invoice-api` cần kiểm mình nằm trong audience.
- `client_id`: client được cấp token theo profile; không tự chứng minh bên cầm bearer token chính là client hợp pháp.
- `scope`: hai giá trị **riêng biệt** `invoice:read` và `invoice:create`.
- `exp`: thời điểm hết hạn theo NumericDate; kiểm thời gian và trạng thái theo chính sách.

**Tuyệt đối không dùng claims từ một JWT chỉ mới giải mã Base64URL** để phân quyền. API cần kiểm chữ ký, thuật toán/khóa tin cậy, issuer, audience, thời hạn, token type/profile và những điều kiện khác trước khi dùng `scope`.

### Opaque access token

Ví dụ client nhận token opaque:

~~~json
{
  "access_token": "tkn_kX4H...opaque...",
  "token_type": "Bearer",
  "scope": "invoice:read",
  "expires_in": 900
}
~~~

Resource server không thể tự suy scope từ chuỗi opaque. Nó có thể dùng **OAuth 2.0 Token Introspection (RFC 7662)** qua kênh tin cậy:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user:mai",
  "client_id": "expense-web",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "exp": 1800000900
}
~~~

API phải kiểm `active`, resource/audience đích, issuer/ngữ cảnh được tin, thời hạn và scope theo hợp đồng. **Introspection không tự thực hiện phân quyền dữ liệu**. Nếu kết quả tra cứu bị cache, phải xem xét độ trễ thu hồi hoặc thay đổi quyền và đặt thời gian cache phù hợp.

### Những biểu diễn khác do nhà cung cấp định nghĩa

Một số issuer dùng tên `scp` cùng kiểu **array** hoặc `roles`/`permissions` trong access token. Đây là **hợp đồng riêng**, không được giả định tương đương với claim `scope` dạng chuỗi của RFC 9068:

~~~json
{
  "scp": ["invoice:read", "invoice:create"]
}
~~~

Chỉ chuyển `scp` thành authorities sau khi Resource Server **chấp nhận profile tương ứng** và xác minh kiểu dữ liệu, issuer, audience và giá trị. Không tự suy rằng mọi claim có tên gần giống scope đều là quyền hợp lệ.

### OIDC scope không phải API permission trực tiếp

Trong OpenID Connect, các scope như `openid`, `profile`, `email` liên quan đến việc yêu cầu chức năng/claims OIDC theo giao thức. Chúng **không tự cấp** cho client quyền gọi endpoint nghiệp vụ như `POST /api/invoices/{id}/approve`. **ID token** được dùng cho chức năng xác thực người dùng tại client, không phải access token dành cho resource API. API phải kiểm **access token phù hợp audience và mục đích**, thay vì chấp nhận ID token vì thấy có `sub` hoặc `email_verified`.

## 4. Đọc và so khớp scope an toàn

**Scope values phân biệt chữ hoa/chữ thường** theo OAuth 2.0. `invoice:read`, `Invoice:Read` và `invoice:READ` là các giá trị khác nhau, trừ khi AS và API có hợp đồng đặc biệt — nhưng việc chuẩn hóa âm thầm trong lớp bảo mật dễ gây nhập nhằng.

Khi scope được mã hóa dưới dạng chuỗi OAuth, nó gồm **nhiều token phân cách bởi dấu cách**. Không kiểm bằng substring:

~~~text
requiredScope = "invoice:read"

granted = "invoice:read invoice:create"
  -> ALLOW ở tầng scope cho thao tác đọc

granted = "invoice:read:any"
  -> DENY: tên khác, không phải invoice:read

granted = "invoice:read-only"
  -> DENY: tên khác, dù có chung tiền tố

granted = "Invoice:Read"
  -> DENY: khác chữ hoa/chữ thường

granted = "invoice:write"
  -> DENY: write không tự kéo theo read
~~~

**Không giả định thứ bậc ngầm** giữa các scope. Nếu `invoice:admin` bao gồm đọc, viết và phê duyệt, hệ thống phải định nghĩa điều này trong chính sách; không được tự suy chỉ từ dấu hai chấm hoặc từ “admin”. Các scope như `read`, `write` quá chung có thể đụng tên khi dùng nhiều API; nên cân nhắc namespace theo tài nguyên/hành động.

### Bộ kiểm đơn giản bằng mã giả

~~~text
function hasScope(verifiedTokenContext, requiredScope):
    if verifiedTokenContext.invalid:
        return false
    granted = verifiedTokenContext.grantedScopes  // set sau khi parse theo profile
    return granted.containsExactly(requiredScope)
~~~

Nếu trực tiếp parse một claim `scope` theo profile yêu cầu JSON string, quy trình cần:

1. Kiểm claim là **string**, không phải array/object/null.
2. Tách thành từng scope-token theo quy tắc của profile, loại bỏ những phần phân tách không hợp lệ hoặc từ chối token sai định dạng.
3. So khớp scope **nguyên vẹn**, không nối chuỗi, prefix hoặc regex tùy tiện.
4. Kiểm token và quyền nghiệp vụ **trước khi thực hiện hành động**, không chỉ tại giao diện.

Với HTTP bearer token, API nên ưu tiên thư viện OAuth/resource-server đã trưởng thành để parse và kiểm claim, thay vì tự viết bộ giải mã token.

## 5. Từ scope đến quyết định phân quyền ở API

Giả sử Mai thuộc tenant A và sở hữu hóa đơn `INV-42`. Bình thuộc tenant B và sở hữu hóa đơn `INV-99`. Expense App có access token liên quan đến Mai:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:mai",
  "aud": "invoice-api",
  "scope": "invoice:read invoice:write",
  "tenant_id": "tenant-a",
  "exp": 1800000900
}
~~~

API cần kiểm **nhiều lớp đồng thời**:

| Kiểm tra | Câu hỏi | Ví dụ kết quả |
|---|---|---|
| **Token validation** | Token có đúng issuer, chữ ký/trạng thái và thời hạn? | Token hợp lệ |
| **Audience** | `aud` có chứa `invoice-api` không? | Đúng |
| **Scope** | Thao tác đọc có được cấp `invoice:read`? | Đúng |
| **Subject/actor** | Ai được đại diện và client/service nào đang hành động? | Mai; Expense App |
| **Tenant/resource policy** | Hóa đơn có thuộc tenant và phạm vi Mai được phép xem? | `INV-42` có; `INV-99` không |
| **Business constraints** | Bản ghi có bị khóa, đang chờ phê duyệt hay có hạn chế khác? | Tùy thao tác |

**Kết quả:** Expense App có thể đọc hóa đơn `INV-42` nếu đáp ứng đầy đủ policy, nhưng không được đọc `INV-99` chỉ vì có `invoice:read`. Nếu token thiếu `invoice:delete`, không được xóa bất kỳ hóa đơn nào, kể cả hóa đơn của Mai.

### Các lớp quyền: functional, object và property

- **Functional authorization:** scope/quyền cho phép gọi chức năng, ví dụ `invoice:approve` cho endpoint phê duyệt.
- **Object-level authorization:** người dùng/service được thao tác trên bản ghi nào? Cần kiểm owner, tenant và quan hệ truy cập thật.
- **Property-level authorization:** được xem/sửa trường nào? `invoice:write` không có nghĩa được tự sửa `approvedBy`, `tenantId` hoặc `isAdmin`.
- **Contextual constraints:** tình trạng hóa đơn, thời gian, tách nhiệm vụ, độ mới xác thực cho giao dịch nhạy cảm.

Scope là một phần của **policy enforcement**, không thay thế các lớp còn lại.

### Ma trận endpoint minh họa

| Endpoint | Scope tối thiểu | Kiểm tra bổ sung bắt buộc |
|---|---|---|
| `GET /api/invoices/{id}` | `invoice:read` | Đúng tenant, quyền trên hóa đơn, lọc field trả về |
| `GET /api/invoices` | `invoice:read` | Chỉ trả bản ghi caller được xem; giới hạn dữ liệu trong truy vấn |
| `POST /api/invoices` | `invoice:create` | Không nhận tenant/owner vượt quyền, validate dữ liệu |
| `PATCH /api/invoices/{id}` | `invoice:write` | Đúng bản ghi, chỉ sửa trường được phép, trạng thái cho phép |
| `POST /api/invoices/{id}/approve` | `invoice:approve` | Vai trò người duyệt, tách nhiệm vụ, trạng thái, step-up nếu chính sách đòi |
| `DELETE /api/invoices/{id}` | `invoice:delete` | Đúng chủ thể/tenant, trạng thái cho phép xóa, ghi audit |

Các tên scope ở đây chỉ là ví dụ. Nếu chính sách dùng **RBAC/ABAC/ReBAC**, resource server cần kết hợp role, thuộc tính và quan hệ thay vì dựa riêng vào scope.

## 6. Resource Server thực thi scope ở boundary nào?

Client không đáng tin cậy để quyết định mình có đủ scope. Backend phải kiểm trước khi trả dữ liệu hoặc thay đổi trạng thái.

~~~mermaid
flowchart TD
    A["Client gửi access token và yêu cầu"] --> B{"Token dành cho API, còn hiệu lực?"}
    B -- "Không" --> X["401 invalid_token"]
    B -- "Có" --> C{"Có scope nguyên vẹn cho action?"}
    C -- "Không" --> Y["403 insufficient_scope"]
    C -- "Có" --> D["Tải/khóa resource trong phạm vi được phép"]
    D --> E{"Chủ thể/client có quyền trên bản ghi và tenant?"}
    E -- "Không" --> Z["403 hoặc 404 theo chính sách"]
    E -- "Có" --> F{"Trạng thái và điều kiện nghiệp vụ hợp lệ?"}
    F -- "Không" --> W["Từ chối theo policy"]
    F -- "Có" --> G["Thực thi và ghi audit an toàn"]
~~~

Một **API gateway** có thể kiểm token hoặc scope chung để từ chối sớm, nhưng **resource server** vẫn phải bảo vệ mọi đường vào (REST, gRPC, GraphQL, WebSocket, job/queue consumer) theo policy. Gateway không biết toàn bộ quyền sở hữu hóa đơn; đường gọi nội bộ hoặc tác vụ nền có thể không đi qua gateway.

### Mã giả kiểm trước khi đọc một hóa đơn

~~~text
function getInvoice(request, id):
    ctx = validateAccessToken(
        request.bearer,
        issuer = "https://auth.example.test",
        audience = "invoice-api",
        purpose = "access"
    )
    if ctx.invalid:
        return HTTP_401

    if not ctx.grantedScopes.containsExactly("invoice:read"):
        return HTTP_403_insufficient_scope

    invoice = repository.findWithinTenant(id, ctx.verifiedTenant)
    if invoice == null:
        return HTTP_404

    if not policy.canRead(
        subject = ctx.subject,
        clientOrActor = ctx.clientOrActor,
        invoice = invoice
    ):
        return HTTP_403_or_404_by_policy

    return HTTP_200_with_allowed_fields
~~~

Các trường như `verifiedTenant`, `clientOrActor` và `grantedScopes` là **ngữ cảnh được API xây dựng từ token/introspection đã xác minh và nguồn quyền đáng tin**, không phải các claim bắt buộc luôn có trong mọi JWT. Nếu tenant hoặc quyền thành viên có thể thay đổi, API có thể tra cứu quyền **hiện hành** thay vì dựa hoàn toàn vào claim tại thời điểm cấp token.

## 7. Triển khai scope với Spring Security (Java)

Trong Spring Security 6.x, Resource Server sử dụng JWT thường ánh xạ scope thành authority theo tiền tố `SCOPE_`. Chẳng hạn token có `scope: "invoice:read invoice:create"` có thể tạo các authority `SCOPE_invoice:read` và `SCOPE_invoice:create`. Đây là hành vi thông dụng nhưng có thể được tùy biến trong `JwtAuthenticationConverter`.

Ví dụ cấu hình kiểm scope ở endpoint:

~~~java
@Configuration
@EnableMethodSecurity
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                .hasAuthority("SCOPE_invoice:read")
            .requestMatchers(HttpMethod.POST, "/api/invoices")
                .hasAuthority("SCOPE_invoice:create")
            .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                .hasAuthority("SCOPE_invoice:approve")
            .requestMatchers(HttpMethod.PATCH, "/api/invoices/**")
                .hasAuthority("SCOPE_invoice:write")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Đây là **mẫu minh họa chưa đầy đủ**: cần cấu hình nguồn issuer/JWK đáng tin, validator `aud=invoice-api`, thuật toán/token profile, các vấn đề CSRF/CORS tùy kiến trúc và mọi route còn thiếu (ví dụ DELETE). `denyAll` giúp endpoint mới không vô tình thành public.

**Lưu ý thứ tự matcher:** Những rule khái quát có thể che rule cụ thể. Ví dụ `POST /api/invoices/**` đặt trước `POST /api/invoices/*/approve` có thể làm route duyệt bị gán sai scope. Cần kiểm thứ tự rule và test từng HTTP method/path thật.

Kiểm scope bằng Spring Security chỉ là lớp **quyền chức năng**. Service vẫn cần kiểm object-level authorization:

~~~java
@Service
public class InvoiceQueryService {
    private final InvoiceRepository repository;
    private final InvoicePolicy policy;

    public InvoiceDto getInvoice(UUID id, VerifiedPrincipal principal) {
        Invoice invoice = repository
            .findByIdAndTenantId(id, principal.tenantId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND));

        if (!policy.canRead(principal.subjectId(), invoice)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        return InvoiceDto.fromAllowedFields(invoice, principal);
    }
}
~~~

`VerifiedPrincipal` và `InvoicePolicy` trong ví dụ là **kiểu ứng dụng tự định nghĩa**, phải được cung cấp từ ngữ cảnh đã xác minh. Không cho frontend truyền một body chứa `subjectId` hoặc `tenantId` rồi tin đó là quyền. Chức năng update cần kiểm lại điều kiện nghiệp vụ trong transaction để tránh race condition/TOCTOU.

### Nếu issuer dùng claim khác `scope`

Khi issuer sử dụng `scp` dạng array hoặc cú pháp khác, cấu hình converter tương ứng **chỉ khi token profile cho phép**. Không tự động chấp nhận tất cả claim `roles`, `permissions` hay `scp` từ bất kỳ issuer nào. Giữ tập issuer tin cậy, audience, kiểu claim và mapping thành authority rõ ràng trong cấu hình và kiểm thử.

## 8. Scope trong hệ thống nhiều API và token exchange

Scope không được đánh giá tách rời **audience**. Một token có `invoice:read` nhưng `aud=report-api` phải bị **Invoice API từ chối**, vì token không dành cho Invoice API.

~~~text
Token A:
  aud   = report-api
  scope = "invoice:read"

Request đến Invoice API:
  -> DENY: sai audience, dù có tên scope invoice:read
~~~

Khi dịch vụ A cần gọi API B thay mặt người dùng, không nên chuyển tiếp nguyên access token có audience của A sang B. Nếu AS hỗ trợ, **OAuth 2.0 Token Exchange (RFC 8693)** có thể cấp token downstream với audience B và scope đã giảm phù hợp.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Report API
    participant AS as Authorization Server
    participant B as Invoice API
    C->>A: Access token aud=report-api
    A->>A: Xác minh token và quyền tại A
    A->>AS: Token exchange xin aud=invoice-api, scope=invoice:read
    AS->>AS: Kiểm grant, actor/client và giới hạn ủy quyền
    AS-->>A: Access token downstream scope được cấp phù hợp
    A->>B: Gọi Invoice API với token dành cho B
    B->>B: Kiểm aud, scope và quyền trên bản ghi
    B-->>A: Trả dữ liệu được phép
~~~

Không tự thêm `scope`, `sub` hoặc `aud` vào JWT rồi xem đó là token mới. Token downstream chỉ có hiệu lực khi được AS/phương thức phát hành đáng tin xác nhận và có ràng buộc audience, actor, quyền phù hợp.

### Scope giảm quyền (downscoping)

Giả sử client được cấp khả năng đọc và ghi hóa đơn, nhưng Report API chỉ cần đọc để lập báo cáo. Token gửi đến Invoice API **nên chỉ có `invoice:read`**, không cần `invoice:write`. Giảm quyền ở **đúng điểm cấp token** giúp hạn chế hậu quả khi token bị lộ.

**Resource Indicators (RFC 8707)** cho phép client chỉ định resource mục tiêu khi xin token theo profile AS hỗ trợ. Scope trả lời “được làm gì?”, resource/audience trả lời “ở đâu?”. Nếu hệ thống cho phép một scope tên giống nhau ở nhiều API, các API vẫn cần phân biệt audience và định nghĩa quyền theo resource của mình.

## 9. Scope và vòng đời token: làm mới, thu hồi, quyền thay đổi

**Access token có scope đã cấp tại thời điểm phát hành**. Khi người dùng bị gỡ role hay bị xóa khỏi tenant, access token tự chứa như JWT có thể vẫn hợp lệ đến `exp` nếu RS không tra trạng thái quyền mới. Opaque token qua introspection có khả năng phản ánh trạng thái gần hiện tại hơn, nhưng vẫn phụ thuộc cache và cách AS cập nhật dữ liệu.

Các nguyên tắc quan trọng:

1. **Scope cấp trong token không được tự nâng**. Client muốn scope bổ sung phải đi qua AS và chính sách cấp quyền; không sửa payload hoặc giả role để tăng quyền.
2. **Refresh token không tự chứng minh quyền mới hay xác thực lại**. Đổi refresh token có thể xin access token mới trong giới hạn grant/AS; AS quyết định scope được cấp và có thể từ chối nếu grant/quyền thay đổi.
3. **Thu hồi quyền quan trọng** cần kế hoạch: thời hạn token ngắn, introspection, danh sách thu hồi/phiên bản quyền hoặc tra entitlement hiện hành, tùy kiến trúc.
4. **Bearer token bị đánh cắp** có thể bị phát lại tại API phù hợp trong thời gian hiệu lực, dù scope hẹp. Dùng HTTPS/TLS, bảo vệ nơi lưu, không log token, cân nhắc mTLS/DPoP hoặc token ràng buộc người gửi nếu hỗ trợ.
5. **Hành động nhạy cảm** có thể cần reauthentication/step-up và xác nhận giao dịch, ngoài scope và quyền nghiệp vụ.
6. **Ghi audit** subject, client/actor, resource, action và quyết định quyền; không ghi nguyên bearer/refresh token.

Mỗi lần dùng access token, RS phải kiểm **đúng issuer, audience, hiệu lực và scope/quyền**. Scope không thay thế các bước đó.

## 10. Lỗi thiết kế scope thường gặp

| Sai lầm | Nguy cơ | Cách sửa |
|---|---|---|
| Coi scope **đã xin** là scope **đã cấp** | Client dùng quyền chưa được AS chấp thuận | Dựa vào token/ngữ cảnh quyền do AS xác minh |
| Kiểm `scope.contains("read")` | `invoice:read:any` bị nhầm thành `invoice:read` | Tách scope và so sánh toàn bộ token |
| Cho `invoice:write` mặc nhiên bao gồm `invoice:read` | Suy quyền vượt hợp đồng | Định nghĩa quan hệ quyền rõ ràng; kiểm chính xác |
| Token đúng scope nhưng sai `aud` | Dùng token của API A ở API B | Kiểm audience của resource server hiện tại |
| Chỉ kiểm scope, không kiểm owner/tenant | BOLA/IDOR, đọc bản ghi người khác | Kiểm object-level/tenant và data filters |
| Dùng scope quá rộng như `admin` cho nhiều API | Token bị lộ có tác động lớn | Tách quyền theo hành động/resource, giảm quyền khi cấp |
| Tin `roles`/`scope` do client gửi trong header | Giả mạo quyền | Chỉ dùng context đã xác minh từ issuer/chính sách tin cậy |
| Đồng nhất scope trong user token và service token | Service tự giả người dùng, bypass policy | Phân biệt grant, subject, client/actor và quyền nghiệp vụ |
| API dùng OIDC ID token thay access token | Nhầm mục đích token và audience | Chỉ nhận access token đúng profile dành cho API |
| Scope nằm trong token cũ dù role đã bị thu hồi | Tiếp tục truy cập ngoài quyền hiện hành | Chính sách token TTL, kiểm entitlement/trạng thái/thu hồi |
| Scope khác cách đặt tên giữa các dịch vụ | Phân quyền không nhất quán | Quản lý catalog scope với hợp đồng và test |

**Phần quan trọng của least privilege là “không cấp scope nếu không cần”**, chứ không chỉ “API kiểm scope sau khi đã cấp quá nhiều quyền”. Cấp phát, lưu trữ, truyền tải và thực thi quyền phải được thiết kế nhất quán.

## 11. Phản hồi HTTP khi token sai hoặc thiếu scope

Với Resource Server dùng OAuth 2.0 Bearer Token (RFC 6750), cần phân biệt:

| Tình huống | Mã thường dùng | Ý nghĩa |
|---|---|---|
| Không có access token với API riêng tư | **401 Unauthorized** | Chưa có token hợp lệ để xác minh |
| Token sai chữ ký, hết hạn, sai issuer/audience/loại token | **401 Unauthorized** | `invalid_token` — token không hợp lệ cho API |
| Token hợp lệ nhưng thiếu scope yêu cầu | **403 Forbidden** | `insufficient_scope` — không đủ phạm vi quyền |
| Scope đúng nhưng không có quyền xem bản ghi/tenant | **403** hoặc **404** theo policy | Không có quyền đối tượng; có thể giấu sự tồn tại của bản ghi |

Ví dụ HTTP response:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="invoice:approve"
Cache-Control: no-store
~~~

Tham số `scope` của challenge có thể cho biết phạm vi cần có; đây là **thông tin về yêu cầu quyền**, không phải lệnh cấp quyền. Client phải xin cấp lại từ AS nếu chính sách cho phép. Không phản hồi quá chi tiết về tài nguyên mà caller không có quyền, và không ghi token vào response hoặc log.

## 12. Kiểm thử scope: trường hợp có quyền và không có quyền

Một API được xem là kiểm scope đúng chỉ khi **token hợp lệ nhưng không có quyền phù hợp bị từ chối an toàn**.

| Trường hợp | Điều kiện | Kỳ vọng tại Invoice API |
|---|---|---|
| Token có `invoice:read` | Đúng issuer/audience; chủ thể sở hữu hóa đơn | Cho phép đọc nếu mọi policy khác đạt |
| Token chỉ có `invoice:write` | Gọi endpoint yêu cầu `invoice:read` | **403**, nếu không có quy tắc quyền bao hàm được định nghĩa |
| Token có `invoice:read:any` | Endpoint yêu cầu chính xác `invoice:read` | **403**, không so khớp substring |
| Token có `Invoice:Read` | Endpoint yêu cầu `invoice:read` | **403**, phân biệt case |
| Token thiếu claim scope cần thiết | Token hợp lệ nhưng không có quyền chức năng | **403** |
| Token có nhiều scope hợp lệ | `invoice:read invoice:create` | Chỉ cho thao tác tương ứng với scope được cấp |
| Token đúng scope nhưng sai audience | `aud=report-api` | **401**, token không dành cho Invoice API |
| Token đúng scope nhưng sai tenant | Mai tenant A yêu cầu hóa đơn tenant B | **403/404**, không để lộ dữ liệu |
| Token sai chữ ký hoặc đã hết hạn | Payload tự ghi `invoice:approve` | **401**, không tin claims |
| Token `client_credentials` | `sub` là service, không có user thật | Chỉ cho phép quyền service theo policy |
| Token user có scope duyệt nhưng role bị gỡ | Entitlement hiện hành không còn | Từ chối theo chính sách quyền hiện hành |
| Access token mới từ refresh token | AS cấp scope đã thu hẹp | Chỉ dùng **scope mới đã cấp** |
| Gửi OIDC ID token có `openid` | ID token gọi endpoint hóa đơn | **401**, sai mục đích |
| Gateway kiểm scope nhưng gọi thẳng backend | Gọi không qua gateway | Backend vẫn phải từ chối nếu không được phép |
| Batch gồm hóa đơn của nhiều tenant | Có scope `invoice:approve` nhưng một số ID ngoài quyền | Không duyệt ID trái quyền; xử lý atomic/partial theo policy |

### Bài tập tình huống

Hệ thống có hai API:

~~~text
Invoice API:
  audience = invoice-api
  read     = invoice:read
  approve  = invoice:approve

Payment API:
  audience = payment-api
  create   = payment:create
~~~

Mai thuộc tenant A, chỉ có quyền xem hóa đơn `INV-42`. Một client có access token đã được xác minh:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:mai",
  "aud": "invoice-api",
  "scope": "invoice:read payment:create",
  "tenant_id": "tenant-a",
  "exp": 1800000900
}
~~~

Giả sử token còn hạn, có chữ ký hợp lệ và hai scope trên thực sự được AS cấp:

**Câu 1: Có thể đọc hóa đơn `INV-42` không?**

Có thể, nếu API kiểm được quyền trên bản ghi, tenant và các điều kiện nghiệp vụ. `invoice:read` là **đủ về mặt scope**, chưa phải toàn bộ điều kiện.

**Câu 2: Có thể phê duyệt `INV-42` không?**

Không, vì thiếu `invoice:approve`; hơn nữa Mai không có vai trò phê duyệt theo tình huống.

**Câu 3: Có thể dùng token này tạo thanh toán tại Payment API không, vì có `payment:create`?**

Không. `aud=invoice-api` chứ không phải `payment-api`. Payment API phải từ chối token sai audience, bất kể scope mang tên liên quan đến thanh toán.

**Câu 4: Nếu Mai đổi URL để đọc hóa đơn `INV-99` thuộc tenant B thì sao?**

Invoice API vẫn phải từ chối theo quyền object/tenant. Scope không mở rộng phạm vi dữ liệu.

**Câu 5: Nếu client thay payload token thành `"scope": "invoice:approve"` thì sao?**

Việc tự sửa JWT làm chữ ký không còn hợp lệ (trừ khi kẻ tấn công chiếm được khóa/chuỗi tin cậy). API phải xác minh token trước khi tin claim, không dùng giá trị do client tự thay.

## 13. Checklist khi thiết kế scope cho API

1. **Định nghĩa scope rõ ràng:** Mỗi tên scope có action/resource và ý nghĩa không nhập nhằng, phân biệt các quyền rủi ro cao?
2. **Cấp theo least privilege:** AS có kiểm client, user/service, grant, resource đích, consent/policy và chỉ cấp scope thực sự được phép?
3. **Phân biệt requested vs granted:** Client có dùng quyền **thực tế được cấp**, không dựa trên tham số mình từng yêu cầu?
4. **Đúng hợp đồng biểu diễn:** API có biết scope là string tách dấu cách hay `scp` dạng khác theo profile issuer? Có so khớp nguyên giá trị?
5. **Kiểm token và audience:** JWT/opaque có được xác minh bằng chữ ký/introspection tin cậy; `iss`, `aud`, thời hạn và loại token có hợp lệ?
6. **Kiểm tại Resource Server:** Mỗi endpoint và đường vào nhạy cảm có policy scope cụ thể, deny-by-default cho route mới?
7. **Bổ sung quyền dữ liệu:** Có kiểm tenant, owner, permission/role, field và trạng thái nghiệp vụ trên tài nguyên thực?
8. **Bảo vệ delegation:** Service A gọi B có token phù hợp audience B và scope giảm quyền theo nhu cầu?
9. **Quản lý vòng đời:** Quyền bị thu hồi, refresh token bị lộ hoặc access token bị đánh cắp sẽ được giới hạn tác động bằng cách nào?
10. **Thử các trường hợp âm tính:** Có test thiếu scope, khác chữ hoa/thường, scope gần giống, sai audience, token giả, sai tenant và bypass gateway?

**Ghi nhớ:** Scope trong access token thể hiện **phạm vi truy cập đã được Authorization Server cấp cho token**, không phải yêu cầu mà client tự tuyên bố, cũng không phải quyền sở hữu mọi tài nguyên. Resource Server phải xác minh token đúng **issuer, audience, mục đích và thời hạn**, kiểm **scope theo hợp đồng**, rồi tiếp tục áp dụng **phân quyền trên đối tượng và điều kiện nghiệp vụ**. Đó là cốt lõi của least privilege trong OAuth 2.0.

### Chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** tham số `scope`, phạm vi được yêu cầu/cấp, các luồng grant.
- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage:** `invalid_token`, `insufficient_scope` và cách phản hồi `WWW-Authenticate`.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** claim `scope` của JWT access token.
- **RFC 7519 — JSON Web Token (JWT):** claims như `iss`, `aud`, `sub`, `iat`, `exp`.
- **RFC 7662 — OAuth 2.0 Token Introspection:** phản hồi `active` và `scope` từ AS cho opaque/reference token.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** ràng buộc resource đích khi xin token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** phát hành token downstream theo giới hạn phù hợp.
- **OpenID Connect Core 1.0:** scope/claims dành cho OIDC và phân biệt ID token với API access token.
