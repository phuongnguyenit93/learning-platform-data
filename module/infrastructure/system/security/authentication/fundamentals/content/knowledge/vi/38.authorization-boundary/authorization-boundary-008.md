# Không nhầm authentication với authorization

> **Chương:** Authorization boundary  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này làm rõ ranh giới giữa xác thực danh tính (authentication) và quyết định quyền truy cập (authorization), cách hai bước trao đổi ngữ cảnh, và các lỗi thiết kế khiến một danh tính hợp lệ bị cấp quyền quá rộng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt authentication (AuthN) và authorization (AuthZ) bằng mục tiêu, đầu vào, kết quả và trách nhiệm của từng bước.
2. Giải thích vì sao đăng nhập thành công không đồng nghĩa được phép đọc hoặc thay đổi mọi resource.
3. Phân biệt principal, subject, actor, client, resource, action và authorization context.
4. Mô hình hóa quyền bằng RBAC, ABAC, ReBAC và kết hợp các mô hình.
5. Phân biệt identity claims, authentication context, OAuth scopes và quyền nghiệp vụ của ứng dụng.
6. Thiết kế deny-by-default, least privilege, tenant isolation và object-level authorization.
7. Nhận diện IDOR/BOLA, privilege escalation, confused deputy và lỗi time-of-check-to-time-of-use.
8. Triển khai enforcement ở API/service layer bằng Java/Spring và kiểm thử cả truy cập được phép lẫn bị từ chối.

## 2. Authentication và authorization trả lời hai câu hỏi khác nhau

**Authentication (AuthN)** trả lời: *Request đang được thực hiện dưới danh tính nào, và bằng chứng xác thực có hợp lệ không?*

**Authorization (AuthZ)** trả lời: *Danh tính hoặc workload đó có được phép thực hiện hành động cụ thể trên resource cụ thể trong ngữ cảnh hiện tại không?*

Ví dụ, An đăng nhập vào hệ thống ngân hàng bằng passkey hợp lệ. Authentication xác minh assertion và xác định principal của An. Sau đó An yêu cầu xem tài khoản A-104. Authorization kiểm tra An có quyền đọc A-104, tài khoản có thuộc tenant/khách hàng mà An được phép truy cập, và trạng thái nghiệp vụ có cho phép thao tác hay không.

Một phiên đăng nhập hợp lệ chỉ cho biết hệ thống đã xác minh một principal theo một authentication context. Nó không tự cấp quyền trên mọi tài khoản, hồ sơ, API hoặc thao tác.

| Khía cạnh | Authentication (AuthN) | Authorization (AuthZ) |
|---|---|---|
| Câu hỏi | Bạn là ai / workload nào đang gọi? | Bạn được phép làm gì trên resource nào? |
| Đầu vào | Credential, proof, issuer, session, authentication context | Principal, action, resource, tenant, policy, context |
| Xử lý | Kiểm tra password, passkey, certificate, token hoặc assertion | Đánh giá policy, ownership, role, attribute, relationship |
| Kết quả | Principal đã xác minh và mức assurance/context | Allow, deny hoặc quyết định giới hạn |
| Thất bại | Không xác minh được danh tính hoặc proof | Danh tính hợp lệ nhưng không đủ quyền |
| Ví dụ | WebAuthn assertion hợp lệ | User chỉ được đọc invoice thuộc tổ chức mình |

~~~mermaid
flowchart TD
    R["Incoming request"] --> N["Authentication: verify credential / token"]
    N --> A{"Principal authenticated?"}
    A -->|"No"| X["401 / authentication challenge"]
    A -->|"Yes"| P["Build principal and auth context"]
    P --> Z["Authorization: evaluate action + resource + policy"]
    Z --> D{"Access allowed?"}
    D -->|"No"| F["403 / deny"]
    D -->|"Yes"| E["Execute permitted operation"]
~~~

HTTP status 401 và 403 thường thể hiện hai loại thất bại khác nhau: 401 liên quan tới việc thiếu hoặc không có credential hợp lệ theo cơ chế của endpoint; 403 thể hiện request đã được hiểu/xác định nhưng không được phép. Cách dùng cụ thể còn phụ thuộc protocol và việc server có muốn tiết lộ resource tồn tại hay không.

## 3. Vì sao ranh giới này quan trọng?

Nếu hệ thống gộp AuthN và AuthZ thành một cờ logged-in, mọi người dùng đăng nhập thành công có thể vô tình nhận cùng một tập quyền. Đây là lỗi nghiêm trọng trong ứng dụng đa người dùng, đa tenant và hệ thống có tài nguyên riêng tư.

Các hậu quả thường gặp:

- User A đọc hoặc sửa dữ liệu của User B bằng cách thay ID trong URL.
- Nhân viên một tenant truy cập resource thuộc tenant khác.
- Token được cấp cho một API lại được dùng ở API khác.
- User có role USER vẫn gọi được endpoint admin do thiếu kiểm tra ở service layer.
- Authentication bằng MFA bị hiểu nhầm là quyền quản trị.
- Một service được tin cậy quá mức và hành động thay người dùng vượt phạm vi ủy quyền.

AuthN tốt xác định đúng principal. AuthZ tốt giới hạn principal đó trong đúng hành động, resource, tenant và thời điểm.

## 4. Các thành phần của authorization decision

Một quyết định quyền truy cập thường cần ít nhất:

- **Subject/principal:** người dùng, workload hoặc service đã được xác thực.
- **Actor:** bên thực sự gửi request hoặc thực hiện hành động. Trong delegation, actor có thể khác subject được đại diện.
- **Action:** hành động cụ thể như invoice:read, user:disable, transfer:approve.
- **Resource:** đối tượng bị tác động, chẳng hạn invoice, account, project hoặc tenant.
- **Context:** thời gian, assurance, session, network, transaction state hoặc môi trường.
- **Policy:** quy tắc quyết định allow/deny và các ràng buộc bổ sung.

Ví dụ:

~~~text
subject = user-104
actor = user-104
action = invoice:read
resource = invoice-778
tenant = tenant-9
context:
  authentication_assurance = MFA
  session_active = true
  request_time = server_time
policy:
  subject belongs to tenant-9
  subject has invoice:read permission
  invoice-778 belongs to tenant-9
decision = ALLOW
~~~

Không lấy subject, tenant hoặc role từ request body rồi coi là sự thật. Principal phải đến từ security context đã xác minh; resource và relationship cần được đọc từ nguồn dữ liệu có thẩm quyền.

## 5. Principal, subject, actor và client

Các thuật ngữ này thường bị dùng lẫn:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Principal** | Danh tính mà security framework gắn với request | User user-104 |
| **Subject** | Thực thể mà policy đánh giá hoặc đại diện | User hoặc service account |
| **Actor** | Bên trực tiếp thực hiện hành động | Admin A đang thao tác thay user B |
| **Client** | Ứng dụng xin token hoặc gửi request | billing-web, mobile-app |
| **Workload identity** | Danh tính của service/process | invoice-worker |
| **Resource owner** | Chủ thể sở hữu hoặc kiểm soát resource | Tenant hoặc account owner |

Trong luồng OAuth delegation, access token có thể biểu diễn client và subject được ủy quyền. Hệ thống phải biết ai là actor, ai là subject, client nào đang gọi và quyền nào được ủy quyền. Không gộp mọi thông tin thành một userId.

## 6. Authentication context có ảnh hưởng tới authorization nhưng không thay thế nó

Authentication context có thể gồm:

- Issuer và subject đã xác minh.
- Thời điểm xác thực (auth_time) và thời điểm token phát hành (iat).
- Phương thức xác thực (amr) và mức assurance (acr) nếu issuer định nghĩa rõ.
- Session ID/version và trạng thái thu hồi.
- Client, audience và token scope.
- Step-up grant gắn với action/resource.

Ứng dụng có thể yêu cầu assurance cao hơn cho một số thao tác, ví dụ thêm authenticator, thay email recovery hoặc chuyển tiền giá trị cao. Tuy nhiên, passkey/MFA thành công chỉ đáp ứng điều kiện xác thực; vẫn cần authorization cho account, beneficiary, amount và action cụ thể.

Ví dụ: user có MFA không đồng nghĩa user được phép xóa account khác. acr hoặc amr cũng không nên được diễn giải tùy tiện; phải dựa trên hợp đồng và semantics của issuer.

## 7. Các mô hình authorization phổ biến

### 7.1. Discretionary Access Control (DAC)

Chủ sở hữu resource có thể quyết định ai được truy cập. Ví dụ, người tạo tài liệu chia sẻ cho một số đồng nghiệp.

Ưu điểm là linh hoạt; rủi ro là quyền có thể lan rộng khó kiểm soát nếu chia sẻ và kế thừa không được quản lý.

### 7.2. Mandatory Access Control (MAC)

Quyền truy cập dựa trên nhãn và clearance được tổ chức áp đặt tập trung. Ví dụ, tài liệu được gắn nhãn Confidential và chỉ principal có clearance phù hợp mới được đọc.

Mô hình này phù hợp môi trường có phân loại dữ liệu nghiêm ngặt; nhãn và clearance phải được quản lý bởi authority đáng tin.

### 7.3. Role-Based Access Control (RBAC)

Quyền được gắn với role; user được gán role theo trách nhiệm công việc.

Ví dụ:

- INVOICE_VIEWER: đọc hóa đơn.
- INVOICE_EDITOR: tạo/cập nhật hóa đơn.
- BILLING_ADMIN: quản trị cấu hình billing.

RBAC dễ quản lý khi vai trò ổn định. Tuy nhiên, role đơn giản có thể quá rộng nếu không gắn tenant, resource ownership và context.

### 7.4. Attribute-Based Access Control (ABAC)

Quyết định dựa trên thuộc tính của subject, resource, action và environment.

Ví dụ:

~~~text
ALLOW invoice:read WHEN
  subject.department == resource.department
  AND subject.tenant_id == resource.tenant_id
  AND resource.classification <= subject.clearance
  AND environment.time within business_hours
~~~

ABAC linh hoạt, nhưng policy phức tạp cần được kiểm thử, version hóa và giải thích được. Thuộc tính phải có nguồn gốc và freshness rõ ràng.

### 7.5. Relationship-Based Access Control (ReBAC)

Quyền được suy ra từ quan hệ giữa subject và resource.

Ví dụ:

- User là owner của project.
- User là member của team sở hữu document.
- User được delegate quyền quản lý account.
- Manager quản lý nhân viên thông qua reporting relationship.

ReBAC hữu ích cho hệ thống có quan hệ chia sẻ, nhóm và tổ chức phức tạp. Cần tránh vòng lặp quan hệ hoặc quyền kế thừa ngoài dự kiến.

### Kết hợp mô hình

Ứng dụng thực tế thường kết hợp:

- RBAC để xác định chức năng theo vai trò.
- ABAC để giới hạn theo tenant, trạng thái và assurance.
- ReBAC để xác định ownership, membership và delegation.

Ví dụ, role cho phép invoice:read, nhưng chỉ khi invoice thuộc tenant của user và user có relationship phù hợp với customer/project.

## 8. OAuth scopes không phải toàn bộ authorization của ứng dụng

OAuth scope mô tả phạm vi client được phép yêu cầu hoặc sử dụng token theo authorization server/resource server contract. Scope có thể là invoices.read hoặc profile.

Nhưng scope thường không đủ để quyết định truy cập một object cụ thể:

- Token có invoices.read không có nghĩa user được đọc mọi invoice.
- API vẫn cần kiểm tra tenant và ownership.
- Client identity không thay subject/actor semantics.
- Scope không nhất thiết biểu diễn mọi quyền nghiệp vụ trong ứng dụng.
- Resource server phải kiểm tra audience, issuer, token type, expiry và scope theo profile.

Một policy hợp lý có thể yêu cầu cả:

1. Token có scope invoices.read.
2. Subject đã xác thực và còn active.
3. Invoice thuộc tenant được phép.
4. Subject có quan hệ hoặc role phù hợp.
5. Resource không bị khóa theo trạng thái nghiệp vụ.

Không coi JWT claim roles do client tự gửi là đáng tin. Chỉ sử dụng claim sau khi xác minh token và khi issuer có authority rõ ràng để phát hành claim đó.

## 9. Authentication thành công không đồng nghĩa resource ownership

Một lỗi phổ biến là endpoint nhận ID resource từ URL và chỉ kiểm tra user đã đăng nhập:

~~~http
GET /api/invoices/778
Authorization: Bearer <access-token>
~~~

Nếu server chỉ kiểm tra token hợp lệ rồi query invoice theo ID 778, user có thể đổi ID thành 779 và đọc invoice của người khác. Đây là dạng Insecure Direct Object Reference (IDOR), thường được gọi trong API security là Broken Object Level Authorization (BOLA).

Kiểm soát:

- Lấy principal từ token/session đã xác minh.
- Truy vấn resource trong phạm vi tenant/ownership mà principal được phép.
- Kiểm tra action cụ thể, không chỉ endpoint.
- Không dựa vào UUID khó đoán làm authorization.
- Dùng query có tenant/owner predicate khi phù hợp.
- Kiểm thử bằng cách đổi ID sang object của user/tenant khác.

Định danh khó đoán có thể giảm enumeration nhưng không thay authorization.

## 10. Tenant isolation

Trong SaaS multi-tenant, principal thường thuộc một hoặc nhiều tenant. Mỗi request cần xác định tenant context từ nguồn đáng tin và kiểm tra resource thực sự thuộc tenant đó.

Không nên:

- Tin tenantId do client gửi mà không kiểm tra membership.
- Dùng một repository query theo resource ID mà không kèm tenant constraint.
- Lấy role ở tenant A rồi áp dụng cho tenant B.
- Dùng cache key thiếu tenant dimension.
- Đưa tenant từ header chưa được gateway xác minh thành authority.

Ví dụ truy vấn có phạm vi:

~~~sql
SELECT id, status, total
FROM invoice
WHERE id = :invoice_id
  AND tenant_id = :authorized_tenant_id;
~~~

authorized_tenant_id phải được xác định từ principal và policy server-side. Nếu query không trả record, ứng dụng có thể trả 404 để tránh tiết lộ sự tồn tại của object; quyết định này cần nhất quán với API contract.

## 11. Deny by default và least privilege

**Deny by default** nghĩa là nếu không có policy rõ ràng cho phép thì request bị từ chối. Không suy luận quyền từ việc endpoint chưa khai báo rule.

**Least privilege** nghĩa là principal chỉ nhận quyền tối thiểu cần thiết trong thời gian và phạm vi cần thiết.

Thực hành:

- Mặc định endpoint yêu cầu authentication.
- Từng action/resource có policy rõ.
- Role và scope không rộng hơn nhu cầu.
- Quyền admin tách khỏi quyền user thông thường.
- Tài khoản đặc quyền dùng step-up và session freshness.
- Quyền tạm thời có expiry và audit.
- Quyền được thu hồi khi user chuyển nhóm/offboard.
- Workload identity có scope/audience riêng.

Không tạo role SUPER_USER cho tiện rồi dùng ở mọi service. Nếu cần break-glass, phải có quy trình, thời hạn, approval và giám sát riêng.

## 12. Privilege escalation

Privilege escalation xảy ra khi principal có được quyền cao hơn mức được phê duyệt.

### Vertical privilege escalation

User thường truy cập chức năng admin hoặc thực hiện action đặc quyền.

Ví dụ: đổi request field role=user thành role=admin, gọi endpoint nội bộ không có method-level authorization hoặc lợi dụng claim mapping sai.

### Horizontal privilege escalation

User có quyền ở cùng mức nhưng truy cập dữ liệu của user khác.

Ví dụ: An đọc hồ sơ của Bình bằng cách thay userId trong URL.

### Các nguồn gốc thường gặp

- Tin role/tenant từ client.
- Kiểm tra quyền ở UI nhưng không kiểm tra ở API.
- Chỉ bảo vệ controller mà bỏ quên service hoặc background job.
- Role inheritance hoặc group mapping quá rộng.
- JWT claim cũ không được cập nhật sau khi quyền bị thu hồi.
- Cache authorization không có tenant/principal/policy version.
- Service account có quyền rộng và bị dùng thay user.

Kiểm soát cần bao phủ mọi đường gọi: HTTP, message queue, scheduled job, admin console và service-to-service.

## 13. Confused deputy và delegation

**Confused deputy** xảy ra khi một service có quyền rộng bị client thuyết phục dùng quyền của chính service để truy cập tài nguyên mà client không được phép.

Ví dụ: một document service có service credential đọc mọi tenant. API nhận tenantId từ user rồi dùng service credential để tải file mà không kiểm tra user có membership trong tenant đó hay không.

Kiểm soát:

- Kiểm tra quyền của subject trước khi service sử dụng quyền workload.
- Phân biệt actor, subject và client.
- Truyền delegation context có xác thực và giới hạn.
- Không tin X-User-Id hoặc header tương tự từ internet client.
- Giới hạn service identity theo resource/audience.
- Audit cả actor service và subject được đại diện.

### Delegation

Một admin có thể được ủy quyền quản lý tài khoản của user khác. Policy phải ghi rõ:

- Ai ủy quyền (grantor).
- Ai được ủy quyền (delegate/actor).
- Subject hoặc resource nào nằm trong phạm vi.
- Action nào được phép.
- Thời hạn và điều kiện thu hồi.
- Có cho phép delegate tiếp hay không.

Không suy ra quyền delegate chỉ từ việc một user biết ID của người khác hoặc có role chung.

## 14. Token claims và quyền truy cập

Token có thể mang:

- iss: issuer.
- sub: subject.
- aud: audience.
- exp, iat, nbf: thời hạn.
- scope hoặc scp: scope theo profile.
- roles/groups: role/group nếu issuer định nghĩa.
- tenant hoặc organization context.
- acr, amr, auth_time: authentication context trong OIDC khi được hỗ trợ.

Resource server cần:

1. Xác minh chữ ký bằng key phù hợp và trust configuration.
2. Kiểm tra issuer, audience, thời hạn và token profile.
3. Xác định principal/subject và client/actor theo contract.
4. Đọc scope/role claim chỉ khi issuer được tin cậy để phát hành.
5. Kiểm tra trạng thái account/session khi yêu cầu freshness hoặc revocation.
6. Đánh giá object/tenant authorization trong ứng dụng.

Không dùng aud để thay authorization. Audience cho biết token được phát hành cho resource nào; nó không khẳng định subject có quyền trên mọi object thuộc resource đó.

## 15. Policy decision và policy enforcement

Kiến trúc có thể tách:

- **Policy Decision Point (PDP):** đánh giá policy và trả allow/deny/obligations.
- **Policy Enforcement Point (PEP):** chặn hoặc cho request đi tiếp theo quyết định.
- **Policy Information Point (PIP):** cung cấp thuộc tính/quan hệ từ directory, database hoặc service.
- **Policy Administration Point (PAP):** quản lý policy và phiên bản.

~~~mermaid
flowchart LR
    REQ["Request + authenticated principal"] --> PEP["Policy Enforcement Point"]
    PEP --> PDP["Policy Decision Point"]
    PDP <-->|"Subject / role / attributes"| PIP["Policy Information Point"]
    PDP <-->|"Ownership / membership"| REL["Relationship store"]
    PAP["Policy Administration Point"] --> PDP
    PDP --> DEC["Allow / Deny / Obligations"]
    DEC --> PEP
    PEP --> RES["Resource operation"]
    PDP --> AUD["Decision audit"]
~~~

Một policy decision nên có:

- Principal/actor và client đã xác định.
- Action/resource/tenant.
- Decision và reason code.
- Policy version.
- Obligations như masking, approval hoặc audit.
- Thời hạn hiệu lực hoặc cache guidance.

Không để PDP trả allow dựa trên thuộc tính thiếu hoặc stale mà không có quy tắc rõ. Nếu policy service lỗi, hành động nhạy cảm thường cần fail closed hoặc dùng fallback đã được phê duyệt; không mặc định allow.

## 16. Authorization phải được kiểm tra ở điểm thực thi

UI có thể ẩn nút Delete, nhưng attacker vẫn có thể gọi API trực tiếp. Gateway có thể xác minh token, nhưng service vẫn cần kiểm tra resource ownership và business rule.

Phòng vệ theo lớp:

- Gateway: xác thực token, issuer/audience, coarse-grained scope.
- Controller: kiểm tra action-level permission và request contract.
- Service: kiểm tra ownership, tenant, relationship và business state.
- Repository/query: giới hạn dữ liệu theo principal/tenant khi phù hợp.
- Database: row-level security/constraint như defense-in-depth nếu kiến trúc hỗ trợ.

Không đặt toàn bộ authorization trong frontend. Không giả định gateway đã kiểm tra đủ mọi điều kiện nghiệp vụ.

## 17. Java/Spring Security: phân biệt AuthN và AuthZ

Spring Security có thể xác minh authentication thông qua filter chain và áp dụng authorization ở request hoặc method level. Ví dụ:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                .hasAuthority("SCOPE_invoices.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth.jwt())
        .build();
}
~~~

Đoạn cấu hình xác thực bearer JWT và áp dụng coarse-grained authorization. hasRole("ADMIN") thường kiểm tra authority có prefix ROLE_; hasAuthority so khớp authority chính xác. Mapping claim thành authority phải được cấu hình rõ theo issuer.

### Object-level authorization ở service

~~~java
@Service
class InvoiceService {
    private final InvoiceRepository invoices;
    private final InvoicePolicy policy;

    InvoiceService(
            InvoiceRepository invoices,
            InvoicePolicy policy) {
        this.invoices = invoices;
        this.policy = policy;
    }

    InvoiceView read(
            AuthenticatedPrincipal principal,
            UUID invoiceId) {

        Invoice invoice = invoices.findById(invoiceId)
            .orElseThrow(InvoiceNotFoundException::new);

        policy.require(
            principal,
            "invoice:read",
            invoice
        );

        return InvoiceView.from(invoice);
    }
}
~~~

Đây là ví dụ khung. Trong hệ thống multi-tenant, tốt hơn có thể truy vấn trực tiếp theo cả invoiceId và tenant đã được xác minh để giảm khả năng object bị nạp ngoài phạm vi. Policy vẫn cần kiểm tra membership/ownership nếu quyền phức tạp hơn tenant equality.

### Method security

~~~java
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceView readInvoice(UUID invoiceId) {
    // Object-level checks still belong in the service/domain policy.
}
~~~

Method annotation có thể bảo vệ chức năng ở mức coarse-grained. Nó không tự chứng minh caller sở hữu invoiceId. Cần kiểm tra object-level authorization trong service/domain layer.

## 18. TOCTOU và authorization freshness

**Time-of-check-to-time-of-use (TOCTOU)** xảy ra khi policy được kiểm tra ở một thời điểm nhưng resource hoặc quyền thay đổi trước khi hành động thực sự commit.

Ví dụ:

1. Service kiểm tra An là owner của account A.
2. Quyền ownership bị thu hồi hoặc account bị chuyển tenant.
3. Một transaction khác vẫn tiếp tục chuyển tiền dựa trên kết quả cũ.

Với hành động nhạy cảm:

- Đặt authorization check gần điểm commit.
- Dùng transaction/locking hoặc version check khi dữ liệu cần nhất quán.
- Kiểm tra resource state và account/session version.
- Giới hạn thời gian cache policy.
- Invalidate cache khi role, membership hoặc ownership thay đổi.
- Không dùng quyết định allow cũ cho một action khác.

Không phải mọi request đều cần khóa toàn bộ dữ liệu. Chọn consistency phù hợp với tác động nghiệp vụ và threat model.

## 19. Authorization trong background jobs và service-to-service

Request không phải lúc nào cũng đến trực tiếp từ browser. Message queue, scheduler, webhook và worker cũng cần authorization.

Ví dụ:

- Worker xử lý invoice event cần xác định service principal và tenant của event.
- Scheduled job có thể chạy với quyền hệ thống nhưng chỉ trên phạm vi đã định.
- Webhook provider đã được xác thực bằng chữ ký nhưng event vẫn phải được kiểm tra có thuộc merchant/account hiện tại.
- Admin job phải ghi actor, approver và reason.

Không coi message queue là trust boundary tuyệt đối. Message có thể bị replay, gửi nhầm tenant hoặc phát ra từ producer bị compromise. Xác minh producer, event identity, schema, tenant và business authorization.

## 20. Các lỗi authorization thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Đăng nhập thành công được coi là có mọi quyền | Mọi user có thể truy cập chức năng ngoài phạm vi | Tách AuthN và AuthZ |
| Chỉ ẩn nút ở UI | Gọi API trực tiếp vẫn thực hiện được | Enforce ở server/service |
| Chỉ kiểm tra role, không kiểm tra object | IDOR/BOLA | Object-level ownership/relationship checks |
| Tin tenantId từ request | Cross-tenant access | Lấy tenant từ principal/policy server-side |
| Tin role claim chưa xác minh | Privilege escalation | Verify token và issuer claim mapping |
| Scope được coi là quyền trên mọi object | Đọc dữ liệu user khác | Kết hợp scope với tenant/ownership |
| Gateway allow là service bỏ qua policy | Business rule bị bypass | Kiểm tra quyền tại domain/service |
| Workload credential quá rộng | Confused deputy và lateral movement | Audience/scope tối thiểu và delegation rõ |
| Cache allow quá lâu | Quyền đã thu hồi vẫn còn hiệu lực | TTL/version/invalidation |
| Không kiểm tra TOCTOU | Action commit sau khi quyền bị thu hồi | Recheck/version/transaction boundary |
| Admin role dùng chung cho mọi môi trường | Cross-environment privilege | Tách role, client và environment |
| Background job tin message tenant | Cross-tenant processing | Xác minh producer và tenant/resource binding |
| Ẩn lỗi bằng cách trả dữ liệu rỗng | Khó phát hiện policy bypass | Decision rõ, audit và response nhất quán |

## 21. Ma trận kiểm thử authentication và authorization boundary

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Không có credential tới endpoint protected | Authentication challenge/401 theo contract |
| JWT sai chữ ký/issuer/audience/expiry | Authentication từ chối |
| Token hợp lệ nhưng thiếu scope | Authorization từ chối |
| User đăng nhập hợp lệ đọc object của user khác | Deny/404 theo policy |
| User có role nhưng resource thuộc tenant khác | Deny |
| Client gửi tenant ID khác tenant principal | Không thay đổi authorization context |
| User có MFA nhưng không có admin role | Không truy cập admin endpoint |
| Role claim từ issuer không được tin cậy | Không ánh xạ thành authority |
| OAuth scope hợp lệ nhưng object ownership sai | Deny |
| User bị offboard nhưng JWT chưa hết hạn | Policy/session version/introspection chặn theo SLA |
| Membership bị thu hồi trong khi request đang chạy | Action nhạy cảm recheck/version policy |
| Delegation hết hạn | Actor không còn được thực hiện delegated action |
| Service credential hợp lệ nhưng subject không có quyền | Deny |
| Webhook chữ ký hợp lệ nhưng event thuộc tenant khác | Deny hoặc quarantine |
| Background job gửi resource ID ngoài phạm vi | Deny và audit |
| Policy service unavailable cho thao tác nhạy cảm | Fail closed/fallback đã phê duyệt |
| Authorization cache cũ sau revoke | Cache invalidation/version check chặn |
| User đổi ID object trong URL | Không truy cập object khác |
| Admin break-glass hết hạn | Quyền bị thu hồi |
| Deny decision | Không tạo side effect và có reason code phù hợp |

Kiểm thử cả positive và negative cases. Với mỗi action, cần thử principal đúng/sai, tenant đúng/sai, role đúng/sai, object owner khác nhau, token thiếu scope và trạng thái account thay đổi.

## 22. Tình huống phân tích

### Tình huống A: user đăng nhập nhưng đọc hóa đơn người khác

An đăng nhập thành công. API GET /api/invoices/778 chỉ kiểm tra JWT hợp lệ rồi trả dữ liệu theo ID.

**Phân tích:** AuthN đúng nhưng AuthZ thiếu object-level check. Cần kiểm tra tenant, ownership hoặc relationship ở service/query layer.

### Tình huống B: MFA được dùng như quyền admin

Ứng dụng cho phép bất kỳ user nào có amr=mfa gọi endpoint admin.

**Phân tích:** amr mô tả phương thức xác thực theo semantics issuer, không phải role. Cần role/permission riêng, và có thể thêm assurance/freshness làm điều kiện phụ.

### Tình huống C: scope rộng nhưng object không thuộc tenant

Access token có invoices.read, nhưng invoice ID được gửi thuộc tenant khác.

**Phân tích:** Scope chỉ cho phép loại API operation theo contract. Resource server vẫn phải kiểm tra tenant và object ownership.

### Tình huống D: service dùng quyền của chính nó thay user

Document service có quyền đọc mọi file. User yêu cầu tải file bằng cách gửi tenant ID khác; service sử dụng workload token để đọc mà không kiểm tra user membership.

**Phân tích:** Confused deputy. Kiểm tra user/subject trước khi dùng workload privilege, giới hạn delegation context và audit actor/subject.

### Tình huống E: quyền đã thu hồi nhưng cache vẫn allow

Admin xóa membership của user. Một node khác giữ authorization cache cũ và tiếp tục cho phép sửa dữ liệu.

**Phân tích:** Cần version hóa policy/relationship, cache TTL phù hợp và invalidation/event propagation. Với action quan trọng, kiểm tra trạng thái gần điểm commit.

## 23. Quy trình thiết kế và vận hành

Trước khi phát hành authorization policy, hãy xác định:

1. Principal/subject/actor/client được lấy từ nguồn nào?
2. Authentication context nào cần cho action: assurance, auth_time, session hoặc sender binding?
3. Resource và tenant được xác định từ nguồn authoritative nào?
4. Action nào được phân biệt; có quyền read/write/delete/admin riêng không?
5. Policy dùng RBAC, ABAC, ReBAC hay kết hợp?
6. OAuth scope và role claim được map theo issuer contract nào?
7. Object-level ownership và tenant isolation được enforce ở đâu?
8. Có deny-by-default và least privilege không?
9. Delegation có actor, subject, scope, resource và expiry rõ không?
10. Workload/service identity có thể trở thành confused deputy không?
11. Cache policy có version, TTL và invalidation khi revoke không?
12. TOCTOU được xử lý tại transaction/commit boundary nào?
13. Background job, webhook và queue consumer có authorization không?
14. Deny/allow decision có audit, reason code và policy version không?
15. Có kiểm thử IDOR/BOLA, cross-tenant access, privilege escalation và stale permission không?

## 24. Ghi nhớ trọng tâm

- **Authentication xác minh danh tính; authorization quyết định quyền.** Hai bước liên quan nhưng không thể thay thế nhau.
- **Đăng nhập thành công không có nghĩa được đọc mọi resource.** Mỗi action cần policy phù hợp.
- **Principal, subject, actor và client có thể khác nhau.** Đặc biệt trong delegation và service-to-service.
- **RBAC, ABAC và ReBAC giải quyết các chiều quyền khác nhau.** Ứng dụng thực tế thường kết hợp chúng.
- **OAuth scope không thay object-level authorization.** Resource server vẫn kiểm tra tenant, ownership và business state.
- **Deny by default và least privilege là nền tảng.** Không có rule allow rõ thì từ chối.
- **Kiểm tra ở UI hoặc gateway là chưa đủ.** Enforce tại service/domain và nơi thực hiện side effect.
- **IDOR/BOLA thường là lỗi AuthZ.** UUID khó đoán không thay kiểm tra ownership.
- **Delegation phải ràng buộc actor, subject, resource, action và expiry.** Nếu không, service có thể thành confused deputy.
- **Quyền có thể thay đổi giữa lúc check và commit.** Dùng version, transaction và cache invalidation phù hợp.

Authentication cho biết request được thực hiện dưới danh tính nào và với mức bằng chứng ra sao. Authorization quyết định danh tính đó được làm gì, trên tài nguyên nào và trong điều kiện nào. Giữ ranh giới này rõ ràng giúp hệ thống tránh biến một lần đăng nhập hợp lệ thành quyền truy cập không giới hạn.
