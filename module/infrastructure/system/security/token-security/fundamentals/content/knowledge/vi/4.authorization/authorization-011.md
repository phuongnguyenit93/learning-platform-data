# Kiểm tra quyền ở boundary của từng API

Một ứng dụng có thể xác thực người dùng rất tốt, dùng JWT có chữ ký hợp lệ, cấp scope đúng quy trình OAuth 2.0, nhưng vẫn làm lộ dữ liệu nếu **một endpoint bỏ qua kiểm tra quyền**. Ví dụ: Alice được đăng nhập và có scope đọc hóa đơn; nếu API `GET /api/invoices/82` chỉ kiểm scope mà không kiểm hóa đơn 82 thuộc ai, Alice có thể đổi ID để đọc hóa đơn của Bob. Đây là lỗi **Broken Object Level Authorization (BOLA/IDOR)**, không phải lỗi mật khẩu hay thuật toán JWT.

Trong chủ đề **Authorization** của module **Security Token Security Fundamentals**, “kiểm tra quyền ở boundary của từng API” nghĩa là: **mỗi đường vào có thể thực thi hành động được bảo vệ phải thiết lập ngữ cảnh tin cậy, kiểm quyền phù hợp và từ chối an toàn trước khi thực hiện tác dụng phụ hoặc trả dữ liệu**. Boundary không chỉ là API gateway. Nó bao gồm endpoint của từng resource server, controller, resolver, RPC handler, consumer nhận sự kiện và các điểm thực thi lệnh nhạy cảm.

Mục tiêu sau bài này:

- Phân biệt **kiểm token** với **phân quyền** trên hành động và dữ liệu thực.
- Biết các lớp kiểm soát tại gateway, API endpoint, service và kho dữ liệu; xác định trách nhiệm của từng lớp.
- Thiết kế chính sách xét **subject, client/actor, action, resource, tenant và context**, đồng thời tránh cấp quyền dựa vào claims chưa được xác minh.
- Áp dụng kiểm quyền cho đọc/ghi một đối tượng, tập kết quả, batch, service-to-service và các đường vào khác HTTP.
- Viết được ma trận kiểm thử âm tính để tìm lỗi vượt quyền ngang, vượt quyền dọc và vượt tenant.

## 1. “Boundary” là đâu và vì sao mỗi API cần tự bảo vệ?

**Trust boundary** là ranh giới nơi dữ liệu hoặc yêu cầu đi từ vùng có mức tin cậy này sang vùng khác. Mỗi lần vượt ranh giới, thành phần nhận cần xác định bằng chứng nào có thể tin, việc nào được phép làm và điều kiện nào cần kiểm lại.

Một request điển hình:

~~~mermaid
flowchart LR
    C["Client bên ngoài"] --> G["API gateway / edge"]
    G --> A["Invoice API / resource server"]
    A --> S["Service và policy"]
    S --> D[("Cơ sở dữ liệu")]
    A -. "Gọi dịch vụ phụ trợ" .-> B["Downstream API"]
~~~

| Lớp | Kiểm soát thường đặt ở đây | Không thể mặc định thay thế |
|---|---|---|
| **Gateway / ingress** | TLS, xác minh sơ bộ token, giới hạn lưu lượng, lọc đường dẫn, một số chính sách truy cập chung | Kiểm quyền sở hữu hóa đơn, tenant của từng bản ghi và quyền nghiệp vụ sâu bên trong API |
| **Endpoint / resource server** | Kiểm access token dành cho API, scope, vai trò/quyền gọi chức năng, từ chối đường dẫn không có chính sách | Quyền trên từng bản ghi nếu endpoint chưa biết dữ liệu thực tế |
| **Service / use case** | Quyết định quyền gắn với hành động và đối tượng, quan hệ sở hữu, tenant, trạng thái tài nguyên | Bảo vệ tất cả entrypoint nếu chỉ có một caller được kiểm |
| **Repository / data access** | Giới hạn truy vấn theo tenant và chủ thể, row-level security khi phù hợp, cập nhật có điều kiện | Phân quyền chức năng và quyết định liệu thao tác có được phép về mặt nghiệp vụ |
| **Downstream API** | Xác minh token/bằng chứng phù hợp với chính mình, kiểm quyền khi tiếp nhận lệnh | Giả định mọi request từ nội bộ/gateway đều được phép |

Lợi ích của gateway là áp dụng chính sách chung và giảm lượng request xấu đi sâu vào hệ thống. Tuy nhiên, nếu một container, hàng đợi, tác vụ nền hoặc đường mạng nội bộ có thể gọi trực tiếp Invoice API, chính Invoice API vẫn cần bảo vệ. **“Đã đi qua gateway” không phải bằng chứng đầy đủ rằng người gọi được phép đọc hóa đơn 82.**

**Nguyên tắc thực thi:** boundary nào nhận yêu cầu thực hiện một hành động thì boundary đó phải có cơ chế **policy enforcement point (PEP)** thích hợp. PEP có thể hỏi một **policy decision point (PDP)** tập trung, nhưng vẫn chịu trách nhiệm thực thi kết quả và chặn thao tác khi không xác minh được quyền.

### Public API là một quyết định chính sách, không phải ngoại lệ ngầm

Một số endpoint như `GET /public/catalog` được phép truy cập không cần đăng nhập. Điều này phải được **khai báo rõ trong chính sách**. Endpoint mới không được tự động trở thành public chỉ vì lập trình viên quên thêm rule; mặc định nên **deny by default**, sau đó cho phép có chủ đích.

## 2. Phân tích quyết định quyền theo một yêu cầu cụ thể

Một quyết định phân quyền đủ rõ thường xét:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| **Subject / principal** | Ai là chủ thể mà bằng chứng tin cậy mô tả? | `user:alice` hoặc `service:billing` |
| **Client / actor** | Ứng dụng nào nhận token, dịch vụ nào đang hành động thay người dùng? | `accounting-web`, `report-service` |
| **Action** | Thao tác thực sự được yêu cầu là gì? | `invoice:read`, `invoice:approve` |
| **Resource** | Đối tượng cụ thể nào bị tác động? | `invoice/82` |
| **Context** | Tenant, vai trò, quan hệ sở hữu, trạng thái, thời gian và rủi ro nào liên quan? | `tenant-a`, hóa đơn chưa khóa |
| **Policy** | Ai được làm thao tác trên đối tượng này với các điều kiện đó? | Người sở hữu hoặc kế toán được phân công |

Đừng đồng nhất các câu hỏi “token hợp lệ?”, “đường dẫn này yêu cầu scope gì?” và “chủ thể có quyền với bản ghi 82 không?”. Cả ba có thể cần thành công, nhưng trả lời những vấn đề khác nhau.

Một cách diễn đạt policy:

~~~text
ALLOW(request) =
    valid_access_token_for_this_resource_server
    AND allowed_operation_for_token_context
    AND subject_or_service_may_access_this_resource
    AND tenant_boundary_satisfied
    AND business_constraints_satisfied
~~~

Đây là mẫu tư duy cho API riêng tư; không phải mọi endpoint đều cần token hoặc người dùng cuối. Với OAuth `client_credentials`, chủ thể có thể là **service**, còn với delegation chủ thể có thể là **người dùng** và actor là một dịch vụ. Policy phải hiểu đúng ngữ nghĩa token của hệ thống, không mặc định mọi `sub` là người dùng.

### Những lớp quyền thường kết hợp

**Functional authorization** kiểm quyền gọi chức năng: nhân viên thông thường không được truy cập endpoint tạo admin hoặc xóa tổ chức. **Object-level authorization** kiểm quyền với từng đối tượng: Alice chỉ được đọc hóa đơn của mình hoặc hóa đơn được phân công. **Field/property-level authorization** kiểm trường nào được xem hoặc thay đổi: người dùng có quyền sửa tên hiển thị nhưng không được tự gán `isAdmin=true`. **Context-based authorization** kiểm tenant, trạng thái phê duyệt, giờ hoạt động hoặc chính sách riêng.

**Scope** thường giới hạn khả năng gọi API được AS cấp cho client; **role** mô tả vai trò trong tổ chức; **permission** mô tả thao tác được phép; **ownership/relation** là quan hệ với đối tượng. Không yếu tố nào tự thay thế tất cả yếu tố còn lại.

## 3. Trước khi dùng quyền trong token: xác minh ngữ cảnh tin cậy

Resource server thường nhận access token OAuth 2.0 dưới dạng **JWT** hoặc **opaque token**. Chúng là hai cách biểu diễn/kiểm chứng, trong khi access token, ID token và refresh token là **vai trò sử dụng** khác nhau.

| Bước | JWT access token | Opaque access token |
|---|---|---|
| **Nhận diện token phù hợp** | Kiểm token profile/loại được API chấp nhận, tránh lẫn ID token | Xác định qua giao thức/hợp đồng với AS |
| **Nguồn tin cậy** | Xác minh chữ ký bằng khóa đáng tin của issuer, chỉ chấp nhận thuật toán mong đợi | Gọi introspection hoặc tra cứu qua kênh và cơ chế xác thực tin cậy |
| **Claims/trạng thái** | Kiểm `iss`, `aud`, `exp`, `nbf` khi áp dụng, và claims yêu cầu | Kiểm trạng thái `active`, audience, phạm vi, chủ thể và thời hạn trả về theo hợp đồng |
| **Thu hồi** | Tự kiểm chữ ký có thể không biết bị thu hồi ngay; cần chiến lược như token sống ngắn/kiểm trạng thái | Có thể biết trạng thái từ AS, nhưng còn phụ thuộc cache và độ trễ cập nhật |
| **Đầu ra mong muốn** | Ngữ cảnh đã xác minh cho policy | Ngữ cảnh đã xác minh cho policy |

**JWT payload có thể được đọc mà không cần khóa**; việc giải mã Base64URL không chứng minh claim là thật. Khi kiểm JWT, API cần chính sách ràng buộc **issuer**, **audience**, token profile, thuật toán và khóa hợp lệ; không chấp nhận thuật toán do token tự chọn ngoài allowlist. JWT có chữ ký hợp lệ nhưng `aud` dành cho Profile API phải bị Invoice API từ chối.

Payload minh họa dưới đây chỉ có ý nghĩa **sau khi** được issuer xác nhận và token đã qua kiểm tra:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:alice",
  "aud": "invoice-api",
  "client_id": "accounting-web",
  "scope": "invoice:read invoice:write",
  "tenant_id": "tenant-a",
  "exp": 1800003600
}
~~~

Claims tùy biến như `tenant_id` và `client_id` có ý nghĩa phụ thuộc **token profile/hợp đồng phát hành**. Không coi một giá trị tenant, role hay user ID do frontend tự gửi là nguồn xác thực. Nếu quyền thành viên tenant có thể thay đổi giữa vòng đời token, hệ thống phải xác định khi nào cần tra cứu nguồn dữ liệu hiện hành thay vì hoàn toàn phụ thuộc claim cũ.

**ID token** của OIDC nhằm truyền thông tin xác thực đến client; không được sử dụng như bearer access token để gọi resource API. **Refresh token** dùng tại authorization server để xin access token mới; không đưa vào API nghiệp vụ như bằng chứng quyền. Với bearer token bị đánh cắp, bên giữ token có thể thử dùng nó; vì vậy chữ ký và `sub` không chứng minh người gửi request trực tiếp là Alice.

### Ranh giới của AuthN và AuthZ

Sau khi token qua kiểm định, API có thể trả lời “đây là một access token được chấp nhận cho Invoice API, liên quan đến subject Alice và scope đọc/ghi hóa đơn”. API vẫn **chưa biết** Alice có được sửa hóa đơn 82 không. Từ đây mới đến kiểm tra quyền đối tượng và chính sách nghiệp vụ.

## 4. Đặt policy ở boundary: kiểm từ tuyến API đến bản ghi

Thiết kế rõ ràng thường có hai lớp bổ sung cho nhau:

1. **Endpoint policy** trả lời ai được gọi chức năng nào. Ví dụ `GET /api/invoices/{id}` yêu cầu `invoice:read`, còn `POST /api/invoices/{id}/approve` cần `invoice:approve` và role phù hợp. Mọi endpoint mới phải được khai báo hoặc mặc định bị từ chối.
2. **Resource policy** trả lời chủ thể có quyền với **đối tượng cụ thể** và trạng thái hiện tại không. Ví dụ kế toán tenant A không được phê duyệt hóa đơn tenant B; người lập hóa đơn không tự phê duyệt nếu quy trình yêu cầu tách trách nhiệm.

Một ma trận minh họa:

| Endpoint | Quyền chức năng tối thiểu | Quyền đối tượng/ngữ cảnh cần kiểm |
|---|---|---|
| `GET /api/invoices/{id}` | `invoice:read` | Đúng tenant và là chủ sở hữu, người được phân công hoặc role có quyền xem |
| `GET /api/invoices` | `invoice:read` | Chỉ trả về tập bản ghi caller được xem; lọc tenant và quan hệ |
| `POST /api/invoices` | `invoice:create` | Không cho chọn tenant/owner vượt quyền; kiểm dữ liệu tạo |
| `PATCH /api/invoices/{id}` | `invoice:write` | Có quyền sửa đúng hóa đơn; chỉ cho sửa các field được phép; trạng thái cho phép chỉnh |
| `POST /api/invoices/{id}/approve` | `invoice:approve` | Đúng tenant, có vai trò phê duyệt, không vi phạm separation of duties |
| `DELETE /api/invoices/{id}` | `invoice:delete` | Đúng tenant, có quyền xóa, hóa đơn chưa ở trạng thái cấm xóa |
| `POST /api/admin/users/{id}/roles` | Quyền quản trị phù hợp | Chỉ thay role trong phạm vi tenant và không cấp cao hơn quyền được phép |

Các tên scope và role ở bảng là **quy ước ví dụ**, không phải chuẩn chung của OAuth. AS có thể cấp scope để gọi endpoint; policy của chính API vẫn là nơi quyết định điều kiện trên tài nguyên cụ thể.

### Ví dụ lỗi BOLA khi chỉ kiểm scope

Giả sử Alice có token với `sub=user:alice`, `tenant_id=tenant-a` và `scope=invoice:read`. API triển khai:

~~~text
GET /api/invoices/{id}:
    claims = verifyAccessToken(request.bearer)
    requireScope(claims, "invoice:read")
    return database.findInvoice(id)      // SAI: chưa kiểm owner/tenant
~~~

Alice có thể thử đổi `id` từ 41 sang 82, hoặc truyền ID ngẫu nhiên, để xem tài liệu không thuộc quyền của mình.

Luồng đúng cần thêm kiểm tra trên dữ liệu thực:

~~~text
GET /api/invoices/{id}:
    ctx = verifyAccessToken(
        request.bearer,
        issuer = "https://auth.example.test",
        audience = "invoice-api",
        purpose = "access"
    )
    if ctx.invalid:
        return 401

    if not ctx.scopeContains("invoice:read"):
        return 403

    invoice = database.findInvoiceWithinTenant(id, ctx.verifiedTenant)
    if invoice == null:
        return 404

    if not policy.mayReadInvoice(ctx.subject, ctx.client, invoice):
        return 403_or_404_by_policy

    return 200, projectFieldsAllowedFor(ctx.subject, invoice)
~~~

Điểm then chốt:

- **Tìm theo tenant được xác minh** ngay ở lớp dữ liệu giúp giảm nguy cơ lộ dữ liệu chéo tenant. Tenant trong URL chỉ là **tham số yêu cầu**, không tự là tenant được phép.
- **Kiểm quan hệ với bản ghi thực**, chẳng hạn owner, thành viên nhóm, người được phân công hoặc vai trò kế toán của tenant.
- **Lọc cả field đầu ra** nếu một số trường chỉ được xem bởi nhóm có quyền riêng.
- **403 hoặc 404** có thể được lựa chọn để hạn chế lộ việc đối tượng tồn tại. Mã phản hồi phải được áp dụng nhất quán theo chính sách; trả 404 không thay cho kiểm quyền.

## 5. Ba lỗi thường gặp khi kiểm sai boundary

### 5.1. BOLA/IDOR: vượt quyền ngang

Alice được đọc tài nguyên của Alice nhưng đổi `id` để xem tài nguyên của Bob. Một mã ID khó đoán không thay thế phân quyền. Hệ thống phải kiểm quyền trên **từng ID** dù đối tượng được định danh bằng số thứ tự, UUID hay khóa ngẫu nhiên.

### 5.2. Broken Function Level Authorization: vượt quyền dọc

Tài khoản thường gọi thẳng `DELETE /api/admin/tenants/7` hoặc đổi HTTP method từ `GET` sang `POST`. Nếu ứng dụng chỉ ẩn nút admin trong UI mà backend không giới hạn quyền chức năng, tài khoản thường vẫn có thể thực hiện. Các route, method, phiên bản API và đường dẫn tương đương phải dùng chính sách rõ ràng.

### 5.3. Broken Object Property Level Authorization: vượt quyền trên field

API cho Alice sửa tên hồ sơ qua `PATCH /api/users/me` nhưng bind toàn bộ JSON vào entity:

~~~json
{
  "displayName": "Alice",
  "isAdmin": true,
  "tenantId": "tenant-b"
}
~~~

Nếu không có allowlist field được sửa và kiểm quyền trên từng thuộc tính, Alice có thể nâng quyền dù endpoint “sửa hồ sơ” đã kiểm scope. Lớp service phải chỉ cập nhật các trường được cấp phép, **không** sao chép nguyên request vào entity nhạy cảm.

## 6. Mẫu triển khai với Spring Security

Trong ứng dụng Java/Spring, nên phân tách **quyền gọi endpoint** và **quyền với bản ghi**. Ví dụ sau là cấu trúc minh họa cho một resource server dùng JWT access token, với Spring Security 6.x:

~~~java
@Configuration
@EnableMethodSecurity
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public/catalog").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                .hasAuthority("SCOPE_invoice:read")
            .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                .hasAuthority("SCOPE_invoice:approve")
            .requestMatchers(HttpMethod.PATCH, "/api/invoices/**")
                .hasAuthority("SCOPE_invoice:write")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Đây là **một phần cấu hình**, không phải cấu hình sản xuất đầy đủ. Mặc định ánh xạ scope thành authority dạng `SCOPE_...` là hành vi thường gặp với JWT trong Spring Security nhưng có thể được tùy biến. Cần cấu hình **issuer** đáng tin và **validator của audience** đối với chính API; chỉ bật kiểm chữ ký mà không kiểm `aud` là chưa đủ. Cần kiểm thêm token profile/loại access token khi áp dụng, cấu hình CSRF phù hợp loại client/credential và bảo đảm không có security filter chain nào bỏ lọt route.

Các rule trên phân biệt chức năng; chúng **chưa** quyết định Alice được đọc hóa đơn 82. Lớp service cần kiểm quyền đối tượng:

~~~java
@Service
public class InvoiceQueryService {
    private final InvoiceRepository invoices;
    private final InvoicePolicy policy;

    public InvoiceDto readInvoice(UUID id, VerifiedPrincipal principal) {
        Invoice invoice = invoices
            .findByIdAndTenantId(id, principal.tenantId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND));

        if (!policy.canRead(principal.subjectId(),
                            principal.clientId(), invoice)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        return InvoiceDto.fromAllowedFields(invoice, principal);
    }
}
~~~

`VerifiedPrincipal` là **kiểu ngữ cảnh minh họa** do ứng dụng xây dựng từ token đã được xác minh và thông tin quyền đáng tin cậy; nó không phải class có sẵn của Spring. Controller có nhiệm vụ lấy ngữ cảnh đáng tin từ `SecurityContext` rồi gọi service. Không cho frontend tự dựng `VerifiedPrincipal` qua body/header.

Nếu dùng `@PreAuthorize` hay method security, các annotation đó có thể là thêm một PEP. Tuy nhiên, **kiểm scope ở controller/method không thể thay thế kiểm bản ghi** trong use case. Phải đảm bảo các đường gọi khác như scheduled job, queue consumer, RPC handler và invocation nội bộ vẫn đi qua chính sách phù hợp, kể cả khi proxy method security không được kích hoạt trong một số kiểu gọi nội bộ.

### Lưu ý về audience khi cấu hình resource server

Giả sử token được cấp cho `profile-api`, nhưng cũng có scope `invoice:read`. Invoice API phải từ chối ngay ở bước kiểm token, trước khi đi vào logic service. Spring Security cần được cấu hình kiểm `aud=invoice-api` theo hợp đồng phát hành, bằng `OAuth2TokenValidator<Jwt>` hoặc cơ chế tương đương của phiên bản framework đang dùng. **Không xem scope hay issuer trùng khớp là điều kiện thay thế audience.**

## 7. Với danh sách, tìm kiếm, batch và dữ liệu nhiều tenant

Quyền từng đối tượng không chỉ cần cho `GET /{id}`. Những API trả nhiều đối tượng hoặc thay đổi hàng loạt có thể rò rỉ dữ liệu mạnh hơn nếu bỏ qua lọc quyền.

### API trả danh sách

Sai:

~~~text
GET /api/invoices?tenantId=tenant-b:
    verifyScope("invoice:read")
    return repository.findAllByTenant(request.tenantId)
~~~

Đúng là truy vấn giới hạn theo **tenant được phép** và điều kiện quan hệ:

~~~text
GET /api/invoices:
    ctx = verifyAndAuthorizeRequest()
    allowedTenantIds = policy.allowedTenantsFor(ctx.subject)
    return repository.search(
        tenantId IN allowedTenantIds,
        visibleTo = ctx.subject,
        filters = validateSafeFilters(request.filters)
    ).map(projectAllowedFields)
~~~

Nếu người dùng được phép xem hóa đơn của nhóm kế toán thay vì chỉ hóa đơn mình sở hữu, điều kiện `visibleTo` phải biểu diễn chính sách đó và được kiểm trực tiếp theo dữ liệu thực. **Không tải mọi bản ghi rồi lọc bằng Java sau khi phân trang** nếu điều đó làm sai tổng số, gây lộ metadata, phá giới hạn hoặc tiêu thụ tài nguyên quá mức. Giới hạn quyền nên được áp dụng trước hoặc trong truy vấn đáng tin cậy.

### API cập nhật hàng loạt

Với `POST /api/invoices/batch-approve` chứa nhiều ID, hãy quyết định rõ policy **all-or-nothing** hay **partial success**. Cả hai cách đều phải:

1. Xác minh token và quyền chức năng trên batch.
2. Kiểm quyền trên **từng ID** và từng tenant theo ngữ cảnh tin cậy.
3. Kiểm trạng thái/phê duyệt thích hợp với **từng hóa đơn**.
4. Nếu thao tác nguyên tử, từ chối toàn bộ khi có đối tượng không hợp lệ; nếu cho phép từng phần, chỉ thao tác đối tượng được phép và không tiết lộ dữ liệu của đối tượng bị từ chối.
5. Kiểm lại điều kiện quan trọng trong transaction, hoặc dùng update có điều kiện, để tránh quyền/trạng thái thay đổi giữa lúc kiểm và lúc ghi.

### Nhiều tenant và row-level security

Trong hệ thống nhiều tenant, lỗi chỉ kiểm role `ADMIN` mà quên tenant là rất nguy hiểm: admin tenant A không mặc nhiên là admin tenant B. Truy vấn hoặc database row-level security (RLS) có thể tăng khả năng ngăn vượt tenant. Tuy nhiên, RLS không tự biết chính sách như “người tạo hóa đơn không được tự phê duyệt”; lớp nghiệp vụ vẫn cần kiểm.

## 8. API-to-API, gateway và các entrypoint không phải REST

### Service-to-service và delegation

Nếu Report Service A gọi Invoice API B thay mặt Alice, B cần biết token/bằng chứng đó **dành cho B** và quyền có hiệu lực là gì. Không lấy token `aud=report-api` chuyển sang B rồi hy vọng B chấp nhận vì “đều là dịch vụ nội bộ”. Có thể dùng **OAuth 2.0 Token Exchange** hoặc cơ chế phát hành token downstream đáng tin cậy để cấp token phù hợp với B, trong phạm vi AS hỗ trợ và policy cho phép.

Phân biệt hai trường hợp:

- **`client_credentials`:** token thường biểu diễn **quyền của client/service**. API áp dụng policy dành cho service, không tự gán danh tính người dùng từ một header.
- **Delegation / on-behalf-of:** token/ngữ cảnh có thể biểu diễn subject là người dùng và actor là service. API phải kiểm quyền của người dùng trên dữ liệu **và** giới hạn delegation của actor/client theo hợp đồng token.

Header như `X-User-Id` hay `X-Tenant-Id` do client tự điền không phải bằng chứng phân quyền. Trong hạ tầng tin cậy, một gateway có thể truyền ngữ cảnh đã xác thực bằng cơ chế riêng, nhưng backend phải **xác minh nguồn, tính toàn vẹn, đường truyền và ràng buộc quyền** thay vì tin bất cứ header trùng tên.

### GraphQL, gRPC, WebSocket và hàng đợi

| Kiểu đường vào | Điểm dễ bỏ lọt | Kiểm soát cần có |
|---|---|---|
| **GraphQL** | Một query lấy nhiều node/field; resolver bỏ kiểm quyền từng đối tượng | Kiểm ở resolver/service, object và field; giới hạn truy vấn, không chỉ kiểm endpoint `/graphql` |
| **gRPC** | Interceptor kiểm danh tính nhưng một method bỏ kiểm role/tenant | Kiểm ở method handler và use case; xác minh metadata/credential qua kênh tin cậy |
| **WebSocket** | Token chỉ được kiểm khi kết nối, nhưng subscription tới phòng khác không được kiểm | Kiểm subscribe/action và quyền với từng channel, xét thay đổi quyền trong phiên dài |
| **Webhook** | Endpoint public nhận lệnh từ đối tác và tin payload tự khai | Xác minh chữ ký/mTLS theo thiết kế, chống replay, kiểm mapping đối tác → tài nguyên/quyền |
| **Queue consumer / async job** | Job nhận message chứa `userId` do upstream đưa vào rồi tự thực thi quyền admin | Xác minh provenance của message, quyền dịch vụ, authorization context tối thiểu; kiểm lại quyền khi cần |
| **Admin/maintenance endpoint** | Đường riêng bypass gateway hoặc security filter | Đặt policy rõ và giới hạn truy cập ở entrypoint thực tế |

Khi một thao tác được kích hoạt từ nhiều đường vào, hãy tái sử dụng **policy trong use case/service** để giảm nguy cơ có một đường gọi bỏ qua kiểm quyền. Gateway, controller và interceptor có thể thêm lớp từ chối sớm nhưng không tạo bảo đảm thay cho policy nghiệp vụ.

## 9. Thay đổi quyền, thu hồi token và kiểm tra trong giao dịch

Quyền có thể thay đổi sau lúc phát hành access token: người dùng bị gỡ khỏi tenant, role admin bị thu hồi, hóa đơn chuyển trạng thái đã khóa. Với JWT tự xác minh, resource server có thể chấp nhận token đến khi `exp` dù quyền bên ngoài đã đổi, nếu chỉ dựa vào claims tại thời điểm cấp. Với opaque token/introspection, thông tin hiệu lực có thể cập nhật nhanh hơn nhưng vẫn phụ thuộc cơ chế cache và cập nhật phía AS.

Các cách giảm độ trễ quyền:

- Giữ **thời hạn access token** phù hợp với rủi ro; không xem refresh token là bằng chứng quyền tài nguyên.
- Với quyền nhạy cảm hoặc hay thay đổi, **tra cứu policy/entitlement hiện tại** khi xử lý request, hoặc dùng cơ chế phiên bản quyền, danh sách thu hồi hay introspection phù hợp.
- Khi xóa role hoặc khóa tài khoản, xác định chính sách thu hồi session/refresh token và ảnh hưởng của access token còn sống.
- Trước khi ghi dữ liệu, **kiểm lại trạng thái quan trọng** trong transaction hay lệnh cập nhật có điều kiện. Việc kiểm lúc đọc rồi ghi sau nhiều giây mà không kiểm lại tạo nguy cơ **TOCTOU** (time-of-check/time-of-use).
- Với tác vụ có thể bị gửi lặp, dùng **idempotency key** hoặc cơ chế chống replay phù hợp; nó bổ sung cho phân quyền và không cho phép bỏ qua kiểm token.

Ví dụ phê duyệt hóa đơn:

~~~text
transaction:
    invoice = lockAndLoadInvoice(id, verifiedTenant)
    if invoice is missing:
        reject
    if not currentPolicy.mayApprove(subject, actor, invoice):
        reject
    if invoice.status != "PENDING":
        reject
    invoice.status = "APPROVED"
    audit(subject, actor, invoice.id, "APPROVE")
commit
~~~

Lệnh cập nhật phải thất bại an toàn nếu quyền, tenant hoặc trạng thái không còn phù hợp. Bản ghi audit nên phản ánh **subject, client/actor, hành động, tài nguyên và kết quả**, không ghi toàn bộ access token hoặc thông tin bí mật.

## 10. HTTP 401, 403, 404 và phản hồi an toàn

| Điều kiện | Phản hồi thường gặp | Diễn giải |
|---|---|---|
| Thiếu hoặc sai access token đối với API riêng tư | **401 Unauthorized** | API chưa có ngữ cảnh xác thực được chấp nhận; với bearer token gửi thử thách `WWW-Authenticate` phù hợp |
| Token hợp lệ nhưng thiếu scope hoặc quyền gọi chức năng | **403 Forbidden** | Đã kiểm token nhưng không đủ quyền |
| Token hợp lệ, đúng chức năng, nhưng không được truy cập đối tượng | **403** hoặc **404** theo chính sách | 404 có thể giảm tiết lộ sự tồn tại của đối tượng; không phải quy tắc bắt buộc |
| Không tìm thấy đối tượng trong phạm vi dữ liệu được phép | **404 Not Found** | Không có tài nguyên khả kiến phù hợp |
| Dữ liệu không còn ở trạng thái cho phép cập nhật | **409 Conflict** hoặc mã nghiệp vụ phù hợp | Điều kiện trạng thái không còn thỏa; vẫn phải kiểm quyền trước khi tiết lộ chi tiết |
| Request công khai được chính sách cho phép | **200** hoặc mã thành công phù hợp | Không có token vẫn được phép theo rule đã khai báo |

Ví dụ thử thách bearer token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Cache-Control: no-store
~~~

Không trả stack trace, nội dung claims nhạy cảm, kết quả tìm kiếm của tenant khác hoặc toàn bộ quyền nội bộ trong thông báo lỗi. **CORS không phải cơ chế authorization**: CORS chủ yếu điều khiển việc trình duyệt cho phép JavaScript từ origin khác đọc phản hồi; attacker vẫn có thể gọi API ngoài trình duyệt. Tương tự, nút bị ẩn trong frontend không phải bằng chứng backend đã kiểm quyền.

## 11. Kế hoạch kiểm thử quyền theo ma trận âm tính

Kiểm thử bảo mật nên tập trung vào **yêu cầu hợp lệ về cú pháp nhưng sai quyền**, vì đây là nơi một API có thể trả dữ liệu ngoài ý muốn.

| Nhóm kiểm thử | Đầu vào | Kết quả kỳ vọng |
|---|---|---|
| **Không có token** | Gọi endpoint riêng tư không có Authorization | **401**, không thực thi tác dụng phụ |
| **Sai issuer / chữ ký / thuật toán** | JWT do bên không tin cậy phát hành hoặc bị sửa | Từ chối trước khi đọc claims để cấp quyền |
| **Sai audience** | Token hợp lệ dành cho API khác | Từ chối |
| **Token sai mục đích** | Dùng ID token hoặc refresh token gọi resource API | Từ chối |
| **Token hết hạn / chưa có hiệu lực** | `exp` quá hạn hoặc `nbf` ở tương lai | Từ chối |
| **Thiếu scope** | Gọi `POST /approve` chỉ với `invoice:read` | **403** hoặc từ chối tương đương |
| **Vượt quyền chức năng** | User thường gọi API admin qua URL trực tiếp | Từ chối dù UI không hiển thị chức năng |
| **Vượt quyền ngang** | Alice đọc ID hóa đơn của Bob cùng tenant | Từ chối hoặc 404 theo policy |
| **Vượt tenant** | Admin tenant A gọi ID thuộc tenant B | Từ chối hoặc 404 theo policy |
| **Field nhạy cảm** | Tự gửi `isAdmin=true`, `tenantId` khác, `ownerId` khác trong JSON | Không ghi các field không được phép; từ chối phù hợp |
| **Danh sách/batch** | Query chứa ID hỗn hợp được phép và không được phép | Không trả/ghi đối tượng trái quyền; đúng semantics batch đã định |
| **Sai đường vào** | Gọi trực tiếp backend, GraphQL resolver, gRPC, consumer hoặc API phiên bản cũ | Mọi đường vào đều áp dụng policy thích hợp |
| **Delegation sai** | Token có `aud=service-A` đem gọi service B hoặc giả `X-User-Id` | Từ chối |
| **Quyền bị thu hồi** | Role/tenant membership đổi sau khi token cấp | Theo chính sách quyền hiện hành, không cấp quyền lỗi thời cho thao tác nhạy cảm |
| **Race / replay** | Hai request đồng thời phê duyệt cùng hóa đơn | Không thực thi sai hoặc nhân đôi do kiểm/giao dịch không nguyên tử |

### Tình huống tổng hợp

API nhận request:

~~~http
PATCH /api/invoices/82 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...redacted...
Content-Type: application/json

{"description":"Đã kiểm tra","status":"APPROVED","tenantId":"tenant-b"}
~~~

Access token đã được xác minh, chứa:

~~~json
{
  "sub": "user:alice",
  "aud": "invoice-api",
  "scope": "invoice:read invoice:write",
  "tenant_id": "tenant-a"
}
~~~

Hóa đơn 82 thực tế thuộc **tenant B**, đang chờ phê duyệt, và Alice chỉ có quyền sửa **description** cho hóa đơn được phân công trong tenant A.

**Câu hỏi:** Có thể cho phép request vì access token hợp lệ và có `invoice:write` không?

**Đáp án:** Không. Dù token hợp lệ cho Invoice API và có quyền chức năng viết, request **vượt tenant**, cố sửa `status` vốn thuộc hành động phê duyệt và tự khai `tenantId` khác quyền đã xác minh. Boundary phải áp dụng đồng thời kiểm **tenant**, **quyền đối tượng**, **quyền field** và **trạng thái nghiệp vụ**. Trả 403 hoặc 404 theo chính sách mà không cập nhật bất cứ trường nào. Một request hợp lệ khác để sửa description vẫn cần quyền trên đúng hóa đơn.

## 12. Checklist thiết kế API trước khi đưa vào sử dụng

1. **Liệt kê mọi entrypoint** (REST/method, GraphQL, gRPC, WebSocket, webhook, job, queue) và xác định policy cho từng hành động.
2. **Deny by default**, khai báo rõ endpoint public; không phụ thuộc việc frontend ẩn nút hoặc gateway đã kiểm một lần.
3. **Xác minh token đúng mục đích**: issuer, chữ ký/khóa hoặc introspection, audience, loại token/profile, thời hạn/trạng thái và cơ chế thu hồi phù hợp.
4. **Phân biệt subject, client và actor**; không suy mọi access token đại diện người dùng, cũng không tin header user/tenant tự khai.
5. **Kiểm quyền chức năng** bằng scope/permission/role phù hợp với endpoint và HTTP method.
6. **Kiểm quyền đối tượng và tenant** trên dữ liệu thực; áp dụng điều kiện quyền vào truy vấn danh sách, batch và update.
7. **Kiểm quyền trường và hành động**, tránh mass assignment, response field leakage và cho phép sửa trạng thái không được cấp quyền.
8. **Kiểm lại chính sách quan trọng trước commit**; quản lý quyền thay đổi, race condition, replay và tính nguyên tử.
9. **Thống nhất phản hồi từ chối** (401/403/404), giới hạn tiết lộ thông tin, ghi audit an toàn và giám sát hành vi bất thường.
10. **Kiểm thử cả trường hợp âm tính**, đặc biệt việc đổi ID, đổi tenant, đổi method, thay claims, đi thẳng backend và gọi các entrypoint ít được dùng.

**Ghi nhớ:** Một access token hợp lệ chỉ thiết lập một phần **ngữ cảnh đáng tin cậy**. Mỗi API phải xác minh token dành cho mình và thực thi chính sách ở boundary; lớp nghiệp vụ tiếp tục kiểm **ai được làm hành động gì, trên đúng đối tượng nào, trong tenant và trạng thái nào**. Đây là cách ngăn token hợp lệ bị biến thành quyền truy cập không hợp lệ.
