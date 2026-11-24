# Policy enforcement – thực thi chính sách phân quyền trong IAM lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **policy enforcement** trong Authorization là gì, khác với **authentication**, **policy decision**, **role assignment** và provisioning ra sao.
- Phân biệt **Policy Enforcement Point (PEP)**, **Policy Decision Point (PDP)**, **Policy Information Point (PIP)** và **Policy Administration Point (PAP)**.
- Thiết kế **deny by default, least privilege, complete mediation** và kiểm tra quyền tại backend cho từng hành động/tài nguyên.
- Thực thi **RBAC/ABAC**, quyền theo đối tượng, quan hệ chủ sở hữu, tenant isolation và những điều kiện bổ sung như step-up hoặc approval.
- Phối hợp **IdP, SSO, OAuth/OIDC, SCIM, Joiner–Mover–Leaver (JML)** và quản trị tài khoản dịch vụ để chống quyền tồn dư.
- Xử lý **policy cache, attribute stale, token cũ, TOCTOU, PDP lỗi, phân quyền liên dịch vụ** và xung đột chính sách.
- Áp dụng mẫu thiết kế trong **Java/Spring Security**, kiểm tra truy vấn dữ liệu, kiểm thử âm tính, audit và reconciliation.

## 1. Policy enforcement là gì?

**Policy enforcement (thực thi chính sách phân quyền)** là quá trình một thành phần đáng tin cậy **áp dụng quyết định phân quyền lên một yêu cầu truy cập thực tế**: cho phép, từ chối, hoặc yêu cầu đáp ứng các điều kiện bắt buộc trước khi hành động được thực hiện.

Câu hỏi trọng tâm là: **Chủ thể này có được thực hiện hành động cụ thể trên tài nguyên cụ thể, trong ngữ cảnh hiện tại không; và hệ thống có thật sự chặn khi điều kiện không thỏa không?**

Ví dụ:

- Nhân viên FinanceReader chỉ được xem hóa đơn của tenant và đơn vị được duyệt.
- Nhân viên Support đã chuyển sang Finance không được tiếp tục đọc dữ liệu khách hàng qua phiên cũ.
- Người được phép yêu cầu cấp admin vẫn cần approval và step-up trước khi thực hiện.
- Service account triển khai phần mềm chỉ được thao tác trên project production đã được duyệt.
- Nhà thầu hết hợp đồng phải bị chặn ở API ngay cả khi trình duyệt còn session.

**Phân biệt hai bước:** *policy decision* trả lời PERMIT hay DENY; *policy enforcement* bảo đảm tài nguyên chỉ được truy cập khi quyết định và các điều kiện được thực thi.

Một policy có thể đúng trên giấy, PDP trả DENY đúng, nhưng API bỏ qua kết quả và vẫn gửi dữ liệu. Đó là **lỗi enforcement**, không phải lỗi viết chính sách.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, policy enforcement kết nối việc xác minh danh tính, tài khoản, quyền đã được duyệt và thay đổi **Joiner–Mover–Leaver** với hành động thực tế. Nó phối hợp với **IdP/SSO, SCIM, RBAC/ABAC, quản trị service identity, audit và reconciliation** để giảm **quyền truy cập tồn dư**.

### 1.1. Phân biệt các chức năng

| Chức năng | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Identity proofing** | Đây có đúng chủ thể được khai báo không? | Đối chiếu hồ sơ với nhân viên thực |
| **Authentication** | Ai đang đăng nhập? | IdP xác thực passkey/MFA |
| **Authorization policy** | Quy tắc cho phép những gì? | FinanceReader chỉ xem hóa đơn Finance |
| **Policy decision** | Request cụ thể có được phép không? | PDP trả DENY đối với invoice-412 |
| **Policy enforcement** | Thao tác có thực sự bị chặn/giới hạn? | Backend không trả invoice-412 |
| **Provisioning** | Tài khoản, group, role đã được tạo/thu hồi? | SCIM gỡ role cũ |
| **Reconciliation** | Quyền thực tế có đúng với quyền mong muốn? | Phát hiện group còn dư |
| **Audit** | Có bằng chứng về quyết định và kết quả? | Decision log, execution status |

**Ẩn nút ở frontend không phải enforcement đầy đủ.** Nếu endpoint vẫn cho phép gọi trực tiếp, người dùng có thể bỏ qua giao diện.

## 2. Mô hình yêu cầu authorization

Một quyết định thường cần các thành phần:

~~~text
AuthorizationRequest =
  subject + action + resource + environment/context
~~~

| Thành phần | Ví dụ | Nguồn đáng tin |
| --- | --- | --- |
| **Subject** | identityId, loại chủ thể, role, employment status | Phiên/token xác minh, HRIS/IGA |
| **Action** | invoice.read, invoice.approve, role.grant | Định nghĩa tại backend |
| **Resource** | invoiceId, owner, classification, tenantId | Database, resource catalog |
| **Environment** | thời gian, thiết bị, authentication assurance | Risk service, session đáng tin |
| **Relationship** | owner, delegatedTo, managerOf | Nguồn quan hệ được quản trị |
| **Policy context** | policyVersion, approval, expiry, security block | PAP/IGA và kho chính sách |

Ví dụ request nội bộ:

~~~json
{
  "subject": {
    "identityId": "person-1042",
    "lifecycleStatus": "ACTIVE",
    "approvedRoles": ["FinanceReader"],
    "department": "Finance",
    "tenantId": "tenant-a"
  },
  "action": "invoice.read",
  "resource": {
    "id": "inv-412",
    "ownerDepartment": "Finance",
    "tenantId": "tenant-a"
  },
  "environment": {
    "authenticated": true,
    "assuranceSatisfied": true
  }
}
~~~

**Dữ liệu minh họa, không phải schema chuẩn.** Không được để client tự điền toàn bộ phần subject và resource rồi coi đó là thuộc tính đã xác minh. Backend phải xây dựng request từ những nguồn có thẩm quyền.

### 2.1. Policy ví dụ

~~~text
PERMIT invoice.read WHEN
    subject.lifecycleStatus == ACTIVE
    AND subject.hasApprovedRole("FinanceReader")
    AND subject.tenantId == resource.tenantId
    AND subject.department == resource.ownerDepartment
    AND environment.assuranceSatisfied
ELSE DENY
~~~

Đây là mã giả độc lập với engine. Kết quả đúng còn phụ thuộc **ngữ nghĩa thuộc tính, độ mới, cách ánh xạ role, mối quan hệ và thời điểm đánh giá**.

## 3. PEP, PDP, PIP và PAP

Một kiến trúc authorization có thể phân tách các trách nhiệm:

| Thành phần | Công việc | Ví dụ |
| --- | --- | --- |
| **Policy Administration Point (PAP)** | Tạo, sửa, review, version và phân phối chính sách | Quản trị Policy as Code, approval workflow |
| **Policy Decision Point (PDP)** | Đánh giá request bằng chính sách và attributes | Policy engine hoặc authorization service |
| **Policy Information Point (PIP)** | Cung cấp attributes/relationships cần cho quyết định | Identity registry, HRIS, resource DB, risk engine |
| **Policy Enforcement Point (PEP)** | Thực thi quyết định ở đường truy cập | API middleware, service method, DB policy |
| **Policy Store** | Giữ và phân phối phiên bản policy | Versioned repository |
| **Audit/Monitoring** | Theo dõi request, quyết định, thực thi và lỗi | SIEM, event store, dashboard |

### 3.1. Luồng quyết định và thực thi

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User / API Client
    participant PEP as PEP: Backend
    participant PIP as PIP: Trusted Attributes
    participant PDP as PDP: Policy Engine
    participant DB as Resource Store
    participant AUD as Audit

    U->>PEP: Request action + resource
    PEP->>PEP: Xác thực và lấy principal
    PEP->>PIP: Tải JML, roles, owner, tenant
    PIP-->>PEP: Dữ liệu có nguồn và độ mới
    PEP->>PDP: Evaluate(subject, action, resource, context)
    PDP-->>PEP: Decision + constraints / obligations
    alt PERMIT và các điều kiện được đáp ứng
        PEP->>DB: Thực hiện action đúng scope
        DB-->>PEP: Kết quả
    else DENY / thiếu chứng cứ
        PEP-->>U: Từ chối an toàn
    end
    PEP->>AUD: Decision và execution outcome
~~~

PDP có thể gọi PIP trực tiếp hoặc nhúng trong ứng dụng. Dù tổ chức khác nhau, **PEP phải nằm trên mọi đường có thể tác động tới tài nguyên** và không thể bị bỏ qua bằng cách gọi API phụ.

### 3.2. PDP tập trung và PDP nhúng

**PDP tập trung** giúp chia sẻ quy tắc, quản trị và audit nhất quán. Đổi lại, nó phụ thuộc mạng, cần xử lý độ trễ và outage.

**PDP nhúng** đánh giá ngay tại dịch vụ với policy bundle được phân phối. Nó có thể giảm độ trễ nhưng phải quản lý **policy version, tính toàn vẹn bundle, cache, rollout và việc mỗi instance đã cập nhật**.

Không có cách nào tự động bảo đảm chính sách đúng. Thiết kế cần xét độ nhạy dữ liệu, khả năng phục hồi, độ trễ và đường phân phối thay đổi.

## 4. Các nguyên tắc enforcement nền tảng

### 4.1. Deny by default

Khi không có quy tắc cho phép rõ hoặc thiếu điều kiện bắt buộc, PEP cần hành xử an toàn.

~~~text
Explicit DENY          -> BLOCK
No matching PERMIT     -> BLOCK
Missing critical facts -> INDETERMINATE -> xử lý an toàn
Authentication invalid -> không tạo authenticated principal
~~~

**INDETERMINATE không có nghĩa là PERMIT.** Nó cho biết engine không thể đưa quyết định đáng tin, ví dụ do lỗi PIP. Hành động đặc quyền thường phải **fail closed**, trừ cơ chế ngoại lệ được tổ chức thiết kế riêng.

### 4.2. Least privilege

Chỉ thực thi permission và scope cần thiết. FinanceReader không tự được approve, delete, export-all hoặc cấp FinanceAdmin.

### 4.3. Complete mediation

Mọi đường thực thi cùng hành động nghiệp vụ phải có enforcement:

- HTTP REST, GraphQL, gRPC và các endpoint quản trị.
- Bulk API, export/import, URL tải dữ liệu.
- Background jobs, queue consumer, scheduler và webhook.
- Truy cập DB, object storage, cache/search index.
- Service-to-service, cloud control plane, tài khoản dịch vụ.

Nếu UI chặn xuất dữ liệu nhưng queue worker nhận job do client tạo trực tiếp, cơ chế enforcement chưa đầy đủ.

### 4.4. Không tin client

Client có thể đề nghị action và resource ID; **role, tenant, approval, trạng thái JML và độ bảo đảm xác thực** phải lấy từ nguồn đã xác minh. Header tự khai rằng người gửi là admin không phải bằng chứng quyền.

### 4.5. Tách nhiệm vụ và truy vết

Quyền sửa policy, quyền phê duyệt, quyền thực thi và quyền xem/xóa log nên được phân tách phù hợp. Mỗi yêu cầu nhạy cảm cần chứng cứ ai yêu cầu, policy nào quyết định, kết quả và hành động thực tế.

## 5. Decision, obligation, advice và enforcement

Một PDP có thể trả:

~~~json
{
  "decisionId": "authz-9918",
  "decision": "PERMIT",
  "policyVersion": "finance-read-v8",
  "constraints": {
    "tenantId": "tenant-a",
    "department": "Finance",
    "maxRows": 100
  },
  "obligations": ["AUDIT_ACCESS"]
}
~~~

Đây là **response minh họa**, không phải schema chuẩn chung. PEP phải bảo đảm truy vấn không thể lấy dữ liệu tenant khác, tối đa 100 hàng và ghi audit theo yêu cầu.

Nếu PEP bỏ qua **maxRows** và trả hàng nghìn dòng, **quyết định có thể đúng nhưng việc thực thi sai**.

Các khái niệm:

- **Decision:** PERMIT/DENY; một số engine hỗ trợ NOT_APPLICABLE hoặc INDETERMINATE.
- **Obligation:** điều kiện/hành động bắt buộc gắn với decision, ví dụ log, lọc dữ liệu hoặc step-up trước khi thực thi.
- **Advice:** thông tin hoặc hướng dẫn không bắt buộc theo contract.
- **Constraint:** giới hạn của quyền được phép, ví dụ tenant, thời gian hoặc số lượng bản ghi.

Tùy engine, những giá trị như **STEP_UP_REQUIRED** hay **APPROVAL_REQUIRED** có thể là trạng thái workflow riêng, không phải giá trị chuẩn của mọi policy language. **Chưa thỏa điều kiện thì chưa được thực hiện hành động**.

## 6. Enforcement theo nhiều lớp

| Lớp | PEP tiêu biểu | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Frontend** | Ẩn nút/menu | Trải nghiệm rõ ràng | Không bảo vệ API trực tiếp |
| **API Gateway** | Token, route/scope check | Chặn yêu cầu sai sớm | Thường thiếu dữ liệu owner từng object |
| **Service Backend** | Authorization middleware, domain method | Biết action, resource, tenant | Phải bao phủ mọi đường nghiệp vụ |
| **Database** | Row-Level Security, query filter, grants | Defense in depth cho dữ liệu | Không thay policy nghiệp vụ toàn ứng dụng |
| **Object Storage** | Object/bucket policies, signed URL | Chặn tại tài nguyên | URL đã phát có hạn và vòng đời riêng |
| **Job Worker** | Reauthorize lúc thực thi | Chặn job chạy sau Mover/Leaver | Cần truyền đúng actor/delegation context |
| **Cloud IAM** | Resource policies, roles, conditions | Enforcement ở control plane | Có thể không biết phê duyệt HRIS |
| **Service Mesh** | Workload identity, mTLS, route policy | Lọc service-to-service | Không tự biết quyền từng invoice |

**Phòng thủ nhiều lớp** không có nghĩa mọi lớp có thể tự PERMIT vượt qua lớp khác. Cần xác định rõ nơi quyết định cuối và cách các lớp kết hợp DENY.

## 7. IdP, SSO và token là đầu vào authorization

**Authentication xác định ai đang truy cập; authorization quyết định được làm gì.**

Trong OIDC/SSO:

- IdP xác thực và có thể cấp ID token cho ứng dụng RP.
- Ứng dụng xác minh ID token, thiết lập phiên riêng.
- Client có thể nhận **access token** để gọi Resource Server.
- API xác minh token đúng issuer, audience, thời hạn và scope/claims theo loại token.
- PEP đánh giá **permission thực tế** theo action, resource và tình trạng JML.

**ID token không tự là access token dành cho API.** Một access token hợp lệ cũng **không đồng nghĩa người dùng có quyền trên mọi object**.

### 7.1. Điều PEP API cần kiểm tra

- Token/phiên được xác thực bởi nguồn tin cậy, không bị client tự tạo.
- Đúng issuer/audience, thời hạn, chữ ký hoặc introspection phù hợp.
- Principal được ánh xạ với đúng identity/account/tenant.
- Scope/authority đủ cho **loại hành động**.
- Role, approval, relationship, resource ownership và trạng thái nhân sự **hiện hành** còn cho phép.
- Với thao tác rủi ro cao, assurance/freshness và step-up đạt policy.

Token có thể đã phát trước khi người dùng bị Leaver hoặc Mover. Do đó **mật mã token đúng không chứng minh quyền hiện hành còn hợp lệ**.

### 7.2. Step-up như điều kiện thực thi

Một yêu cầu cấp quyền admin có thể đòi xác thực chống phishing, gần thời điểm hành động, và được ràng buộc với role/resource đang cấp. Sau step-up, backend phải **kiểm tra lại role và trạng thái JML** trước commit; authentication mạnh không cấp quyền thiếu approval.

## 8. RBAC: role không thay thế object check

**Role-Based Access Control (RBAC)** xác định các permission của vai trò.

| Role minh họa | Permission | Không được tự suy ra |
| --- | --- | --- |
| FinanceReader | invoice.read trong phạm vi được duyệt | invoice.approve, invoice.delete |
| FinanceApprover | invoice.approve theo giới hạn | role.grant |
| SupportAgent | case.read, case.update theo phân công | payroll.read |
| IAMReviewer | access.review | self-grant admin |
| WorkloadDeployer | deployment.execute trên project cụ thể | tenant-wide cloud admin |

Một role **FinanceReader** cho biết loại hành động có thể được phép, nhưng vẫn cần kiểm **hóa đơn thuộc tenant, department và phạm vi dữ liệu** nào.

### 8.1. Role cũ và role kế thừa

Role có thể được gán trực tiếp ở SaaS, qua group của IdP, hoặc role kế thừa qua nhóm lồng nhau. Khi Mover, group đã bị gỡ nhưng token hoặc role cục bộ còn tồn tại. PEP cần nguồn entitlement thích hợp, không tự tin một claim role stale.

### 8.2. Policy xung đột

Nếu FinanceReader cho phép đọc hóa đơn nhưng security block yêu cầu chặn mọi truy cập của account đang bị điều tra, kết quả phải theo **quy tắc kết hợp đã định**. Không mặc định rule PERMIT tìm thấy đầu tiên luôn thắng.

## 9. ABAC: thuộc tính và điều kiện thời điểm

**Attribute-Based Access Control (ABAC)** quyết định quyền từ thuộc tính subject, action, resource và environment.

~~~text
PERMIT invoice.read WHEN
    subject.lifecycleStatus == ACTIVE
    AND subject.approvedRole == FinanceReader
    AND subject.tenantId == resource.tenantId
    AND subject.department == resource.ownerDepartment
    AND resource.classification <= subject.clearance
    AND context.riskLevel != HIGH
ELSE DENY
~~~

Đây là mã giả. Mức classification/clearance phải có **thứ bậc được định nghĩa**, không dựa trên so sánh chuỗi.

### 9.1. Nguồn thuộc tính có thẩm quyền

| Thuộc tính | Nguồn thường dùng | Nguy cơ khi sai |
| --- | --- | --- |
| Employment status, effectiveAt | HRIS/nguồn hợp đồng | Leaver được PERMIT |
| Approved role, exception expiry | IGA/approval store | Quyền quá hạn |
| Tenant, owner, classification | Resource DB/catalog | Lộ dữ liệu chéo tenant |
| Assurance, auth_time | IdP/session đã kiểm chứng | Step-up giả |
| Risk/device state | Risk engine được phê duyệt | Tín hiệu không đáng tin |
| Delegation | Delegation/relationship registry | Ủy quyền đã kết thúc |

**PIP phải có quyền sở hữu dữ liệu rõ ràng.** Người dùng tự sửa department trong profile không thể khiến policy tin họ vừa chuyển sang Finance.

### 9.2. Dữ liệu thiếu

Nếu PIP không đọc được lifecycle status, một PEP thực thi chức năng approve thanh toán không nên tự giả định ACTIVE. Cần ghi **INDETERMINATE**, bảo đảm hành vi an toàn và có owner xử lý lỗi.

## 10. Object-level authorization và quan hệ

Một người có quyền hỗ trợ khách hàng có thể xem **ticket được phân công cho mình**, nhưng không được xem mọi ticket của tổ chức.

~~~text
subject = person-1042
role = SupportAgent
action = ticket.read

ticket-A.assignedAgent = person-1042 -> PERMIT
ticket-B.assignedAgent = person-2091 -> DENY
~~~

Đây là **object-level authorization**. Các chính sách phức tạp có thể dùng quan hệ (Relationship-Based Access Control – ReBAC): owner, member, manager, delegatedTo.

### 10.1. BOLA/IDOR

Ví dụ endpoint:

~~~text
GET /api/invoices/412
GET /api/invoices/413
~~~

Nếu backend chỉ yêu cầu đã đăng nhập rồi trả invoice theo ID, đổi 412 sang 413 có thể lộ dữ liệu người khác. Đó là lỗi **Broken Object Level Authorization (BOLA)**.

Không nên xem ID khó đoán, URL chỉ hiển thị cho owner hoặc UI ẩn link là cơ chế phân quyền. **Backend phải kiểm từng object và action**.

### 10.2. Quyền ủy quyền có hạn

Quyền delegated access có thể có ngày hết hạn, scope và người ủy quyền. PEP phải kiểm **approval vẫn hợp lệ và quan hệ còn tồn tại**, không dùng quyền ủy quyền từ dự án đã kết thúc.

## 11. Multi-tenant enforcement và lọc dữ liệu

**Tenant isolation** là điều kiện riêng so với role. FinanceReader ở tenant-A không được đọc dữ liệu tenant-B.

Một client có thể gửi:

~~~json
{
  "tenantId": "tenant-b",
  "invoiceId": "inv-412"
}
~~~

Backend không được dùng tenantId này làm bằng chứng người dùng thuộc tenant-b. Tenant context phải đến từ **principal/session và membership đã xác minh**, rồi so với owner tenant của tài nguyên.

### 11.1. SQL giới hạn tài nguyên

~~~sql
SELECT
    id,
    tenant_id,
    owner_department,
    amount
FROM invoices
WHERE id = :invoiceId
  AND tenant_id = :authorizedTenantId
  AND owner_department = :authorizedDepartment;
~~~

Đây là SQL trên bảng giả định. Tham số authorizedTenantId và authorizedDepartment **phải do backend tính từ nguồn tin cậy**, không sao chép từ request body.

### 11.2. Row-Level Security

Một số database hỗ trợ **Row-Level Security (RLS)** để chặn truy vấn dòng ngoài scope ngay ở database. Đây là **defense in depth**, không thay toàn bộ policy.

Cần kiểm:

- Session/connection pool thiết lập và xóa tenant context đúng mỗi request/transaction.
- Service/DB role có khả năng bypass RLS được giới hạn.
- Background jobs và migrations có policy phù hợp.
- Dữ liệu cache, search index, file/object storage cũng được bảo vệ.
- Business approval, SoD, step-up vẫn được kiểm ở tầng ứng dụng.

Một connection được tái sử dụng với tenant context từ người dùng trước có thể gây rò dữ liệu nghiêm trọng.

## 12. Java/Spring Security: enforcement tại HTTP và method

Các ví dụ sau minh họa hướng thiết kế; triển khai sản xuất cần cấu hình framework, JWT validation, authority mapping và transaction phù hợp.

### 12.1. HTTP authorization

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasAuthority("ADMIN_ACCESS")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(jwt -> {}));
        return http.build();
    }
}
~~~

Đây là **khung minh họa**, không phải cấu hình production hoàn chỉnh. Cần cấu hình đúng trusted issuer, audience, JWT validator, authority mapping, CSRF/session theo loại client và xử lý lỗi.

**Authenticated không đồng nghĩa được đọc mọi object.**

### 12.2. Method-level enforcement

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class InvoiceService {
    private final InvoiceRepository invoices;

    InvoiceService(InvoiceRepository invoices) {
        this.invoices = invoices;
    }

    @PreAuthorize("@invoiceAuthorization.canRead(authentication, #invoiceId)")
    @Transactional(readOnly = true)
    public InvoiceDto readInvoice(String invoiceId) {
        // Repository cũng thực thi tenant/resource scope đáng tin.
        return invoices.findAuthorizedInvoice(invoiceId);
    }
}
~~~

Đoạn mã giả định có bean invoiceAuthorization và repository triển khai an toàn. Trong thực tế:

- Method security phải được bật và không bị bypass bởi đường gọi khác.
- Bộ kiểm phải tải **resource ownership, tenant, lifecycle status và entitlement** từ nguồn tin cậy.
- Không trả dữ liệu rộng rồi yêu cầu frontend tự lọc.
- Nếu resource đổi owner sau check, cần transaction/conditional query hoặc tái kiểm tra.
- Phải kiểm trực tiếp các phương thức tạo/sửa/xóa, không chỉ read.

### 12.3. Mã giả xử lý quyền ở domain layer

~~~java
Decision authorize(Actor actor, Action action) {
    Identity current = identityStore.loadCurrent(actor.identityId());
    Resource resource = resourceStore.loadTrusted(action.resourceId());

    if (!current.isActive()) {
        return Decision.deny("LIFECYCLE_NOT_ACTIVE");
    }

    Decision decision = policyEngine.evaluate(
        current, action.type(), resource, trustedContext()
    );

    if (!decision.isPermit() || !obligationsSatisfied(decision)) {
        return Decision.deny("POLICY_NOT_SATISFIED");
    }

    return decision;
}
~~~

Đây là **mã giả**, không phải các class có sẵn. Cần bảo vệ race condition giữa quyết định và commit, tránh đánh giá trên resource do client tự khai.

## 13. Policy as Code và quản lý vòng đời chính sách

**Policy as Code** giúp version, review, test, rollout và audit quy tắc phân quyền thay vì chỉnh thủ công không có lịch sử.

Quy trình thường có:

1. Resource owner mô tả nhu cầu quyền và dữ liệu cần bảo vệ.
2. Security/IAM xác định nguồn thuộc tính, điều kiện và hành vi deny.
3. Chính sách được review, kiểm tra SoD và test âm tính.
4. CI/CD hoặc PAP phân phối policy được duyệt đến PDP.
5. Các instance công bố policyVersion đang dùng.
6. Monitoring đánh giá hiệu quả, drift và lỗi rollout.
7. Một rollback phải được duyệt và không vô tình khôi phục quyền quá rộng.

Ví dụ cấu trúc **minh họa, không phải cú pháp OPA/Rego, Cedar hay XACML**:

~~~yaml
policyId: finance-invoice-read
version: 8
effect: permit
subject:
  lifecycleStatus: ACTIVE
  approvedRole: FinanceReader
action: invoice.read
resource:
  tenant: same-as-subject
  department: same-as-subject
conditions:
  requiredAuthenticationSatisfied: true
obligations:
  - audit-access
defaultEffect: deny
~~~

### 13.1. Phân phối policy và xung đột

Nếu một service còn policy v7 rộng hơn trong khi các instance khác đã dùng v8, hai request tương đương có thể nhận kết quả khác nhau.

Cần quản trị:

- Bản policy đã được ký hoặc xác minh tính toàn vẹn khi cần.
- Version, thời điểm effective và trạng thái rollout.
- Phép kết hợp policy (explicit deny có ưu tiên không, rule theo tenant xử lý thế nào).
- Cơ chế cảnh báo instance stale.
- Rollback có phê duyệt thay vì tự mở PERMIT khi gặp lỗi.

### 13.2. Policy được duyệt vẫn cần enforcement đúng

Một chính sách có version và test tốt vẫn có thể bị bypass nếu service bỏ qua PEP hoặc áp một decision từ tenant khác. Do đó phải kiểm tra **PDP correctness** và **PEP coverage** tách biệt.

## 14. Cache chính sách, quyền và thuộc tính

Caching giúp giảm độ trễ khi PEP gọi PDP/PIP, nhưng cũng tạo rủi ro **quyết định cũ được dùng sau Mover, Leaver hoặc một sự kiện bảo mật**.

| Thành phần được cache | Ví dụ | Rủi ro |
| --- | --- | --- |
| **Role/entitlement** | FinanceReader đọc từ IdP 15 phút trước | Role đã gỡ nhưng phiên còn quyền |
| **Employment status** | ACTIVE lấy từ HRIS lần trước | Leaver đã effective nhưng PEP chưa biết |
| **Resource attribute** | Invoice owner hoặc tenant cũ | Quyền được áp trên đối tượng đã đổi chủ |
| **Policy bundle** | Service A dùng v7, service B dùng v8 | Cùng request nhưng quyết định khác |
| **Decision PERMIT** | Cho phép đọc invoice-412 | Bị dùng lại cho invoice khác |
| **Access token/session** | Token chứa role Support trước Mover | API tiếp tục dùng claim cũ |

### 14.1. Cache key và độ mới

Nếu dùng decision cache, khóa cache phải phản ánh những thành phần quyết định liên quan: **subject, action, resource, tenant, policy version, thuộc tính và phiên bản dữ liệu cần thiết**.

Không được dùng cùng PERMIT cho hai tài nguyên khác nhau chỉ vì cùng role. Không được dùng quyết định của tenant-A cho tenant-B.

Tùy mức rủi ro:

- Định nghĩa **TTL** và giới hạn freshness của role/attribute/policy.
- Có cơ chế **invalidation** khi JML, approval, role hoặc security block đổi.
- Với hành động nhạy cảm, kiểm quyền trực tiếp hoặc dữ liệu mới nhất.
- Gắn version với quyết định, cảnh báo khi instance chưa nhận policy mới.
- Nếu không thể kiểm dữ liệu bắt buộc, **không suy ra PERMIT**.

### 14.2. Replication và đồng bộ không tức thời

Thay đổi có thể đi qua HRIS → IGA → directory → IdP → SCIM → ứng dụng → session. Mỗi lớp có độ trễ. **Directory replication thành công không đồng nghĩa authorization đã hội tụ**, vì token hoặc role local có thể còn cũ.

Một bản ghi **đã gửi lệnh revoke** không chứng minh PEP cuối đã DENY. Nên đo **effectiveAt**, **requestedAt**, **appliedAt**, **observedAt** và **verifiedAt** khi có thể, tách rõ lớp nguồn với lớp thực thi.

## 15. Khi PDP hoặc PIP gặp lỗi

Một số hệ thống gọi PDP qua mạng, hoặc dùng PIP đọc status nhân sự, risk score và owner tài nguyên. Khi chúng không khả dụng, PEP cần một **chiến lược fail-safe có chủ đích**.

~~~mermaid
flowchart TD
    A["PEP nhận request"] --> B["Xác minh principal và context"]
    B --> C{"PDP/PIP có dữ liệu đủ tin cậy?"}
    C -->|"Không"| D["INDETERMINATE / ERROR"]
    D --> E{"Có fallback an toàn được duyệt?"}
    E -->|"Không"| F["DENY/BLOCK + alert"]
    E -->|"Có"| G["Áp fallback giới hạn scope/TTL, audit"]
    C -->|"Có"| H["PDP đánh giá"]
    H --> I{"Kết quả"}
    I -->|"DENY"| F
    I -->|"PERMIT"| J{"Đáp ứng obligations và context?"}
    J -->|"Không"| F
    J -->|"Có"| K["PEP thực thi đúng scope"]
~~~

**Fail closed** rất quan trọng khi cấp role admin, duyệt thanh toán hoặc truy xuất dữ liệu nhạy cảm. Nhưng doanh nghiệp cũng cần khả năng xử lý sự cố khẩn cấp:

- Có thể dùng **policy bundle dự phòng** đã được phê duyệt và ký/xác minh.
- Có thể duy trì quyền đọc ít rủi ro trong một cửa sổ giới hạn khi policy cho phép.
- Có thể dùng **break-glass** với xác thực, owner, hạn, phạm vi và hậu kiểm riêng.
- Không mở một nhánh **“PDP timeout thì cho tất cả”**.

### 15.1. Circuit breaker không tự là policy

Circuit breaker giúp tránh quá tải khi PDP lỗi, nhưng hành vi khi circuit mở **vẫn phải tuân thủ chính sách**. Khả năng chịu lỗi của hệ thống không được biến thành cho phép vượt quyền.

### 15.2. Dữ liệu UNKNOWN

Nếu nguồn không đọc được employment status, kết luận đúng là **không đủ dữ liệu**. Không thể tự xem người dùng ACTIVE chỉ vì không có sự kiện Leaver trong cache.

## 16. Time-of-check to time-of-use (TOCTOU)

**Time-of-check to time-of-use (TOCTOU)** là khoảng giữa thời điểm kiểm quyền và lúc thực sự sử dụng quyền. Tài nguyên hoặc vai trò có thể đổi trong khoảng đó.

~~~text
10:00:00  FinanceApprover yêu cầu approve invoice-412
10:00:01  PDP trả PERMIT
10:00:03  Approval bị thu hồi hoặc invoice đổi owner
10:00:06  Backend mới ghi trạng thái APPROVED
~~~

Nếu ứng dụng chỉ giữ quyết định cũ mà không xét trạng thái mới, thao tác có thể diễn ra sau khi quyền đã mất.

### 16.1. Cách giảm nguy cơ

- Đặt enforcement **gần nơi thực thi** nhất có thể.
- Dùng transaction hoặc conditional update gắn với owner/tenant/version nếu phù hợp.
- Đọc lại role, approval, policy hoặc resource trước **commit** ở hành động nhạy cảm.
- Gắn quyết định với **resourceVersion, policyVersion, identityVersion** nếu kiến trúc hỗ trợ.
- Không chấp nhận một quyết định cũ vô thời hạn.
- Thiết kế idempotency để retry không chạy thao tác hai lần.

Ví dụ SQL minh họa thao tác giới hạn điều kiện:

~~~sql
UPDATE invoices
SET approval_status = 'APPROVED'
WHERE id = :invoiceId
  AND tenant_id = :authorizedTenantId
  AND approval_status = 'PENDING'
  AND version = :expectedVersion;
~~~

Điều kiện update giúp giảm race condition đối với **trạng thái invoice**, nhưng **không thay** việc kiểm actor, approval, SoD và policy hiện hành. Những kiểm soát phải kết hợp theo transaction và mô hình rủi ro.

## 17. Policy enforcement giữa các microservice

Một request từ người dùng có thể đi qua gateway, Invoice Service, queue và Report Worker.

~~~mermaid
flowchart LR
    User["User / OAuth Client"] --> GW["API Gateway: coarse PEP"]
    GW --> S1["Invoice Service: domain PEP"]
    S1 --> PDP["Authorization Service"]
    S1 --> Queue["Async Queue"]
    Queue --> S2["Report Worker: recheck"]
    S2 --> DB["Data Store / query filter"]
    S1 --> AUD["Audit"]
    S2 --> AUD
~~~

### 17.1. Gateway không biết mọi quyền nghiệp vụ

Gateway thường xác minh bearer token, audience, scope hoặc route. Nó có thể không biết invoice-412 thuộc tenant nào, ai tạo hay có approval chưa. **Domain service hoặc tầng dữ liệu cần PEP phù hợp**.

### 17.2. Truyền danh tính và quyền ủy quyền

Khi service A gọi service B, có ít nhất hai danh tính cần phân biệt:

1. **User principal** – người hoặc chủ thể đã khởi phát yêu cầu.
2. **Workload principal** – service A được xác thực đang gọi service B.

Có thể còn **delegated authority** xác định service được phép hành động thay user tới đâu.

Không tin header người dùng tự gửi như X-User-Id từ mạng không đáng tin. Dùng kênh và token đúng audience, xác thực workload (ví dụ managed identity/mTLS) và cơ chế truyền authority được thiết kế rõ.

### 17.3. Confused deputy

Report Service có quyền đọc toàn bộ database để vận hành. Nếu người dùng chỉ cần gửi invoiceId, service dùng quyền mạnh của chính mình mà không kiểm **người khởi phát có quyền đọc invoice đó**, người dùng có thể lợi dụng service làm thay điều không được phép.

Đây là một dạng **confused deputy**. Phải kiểm đúng **principal, purpose, delegated scope và tài nguyên**.

### 17.4. Background jobs

Một yêu cầu export được duyệt lúc 10:00; worker chạy lúc 11:00, sau khi người dùng bị Leaver. Tùy policy, worker phải **tái kiểm quyền ở thời điểm chạy** và kiểm quyền khi trả kết quả, không tin quyết định cũ một cách máy móc.

Điều tương tự áp dụng cho webhook, scheduled jobs, signed download URL và lệnh bất đồng bộ.

## 18. Joiner: chỉ cho quyền từ khi đủ điều kiện

Trong **Joiner lifecycle**:

1. HRIS/nguồn hợp đồng xác nhận người mới, relationship, workerType và **effectiveAt**.
2. Identity proofing thiết lập đúng chủ thể; identity registry tạo ID bền vững.
3. IdP provision account và authenticator theo policy.
4. IGA tính desired entitlement, kiểm approval và SoD.
5. SCIM/API cấp account/role tại ứng dụng.
6. PEP **chỉ cho phép hành động khi quyền đã hợp lệ**, kể cả account được tạo sớm.
7. Reconciliation đọc lại account và quyền thực tế.

### 18.1. Preboarding

Có thể tạo account trước ngày làm việc nhưng chưa mở quyền dữ liệu nhạy cảm. Nếu PEP chỉ kiểm account tồn tại thì user có thể truy cập sớm.

~~~text
PERMIT workforce.read WHEN
  identity.proofingComplete
  AND relationship.status == ACTIVE
  AND now >= relationship.effectiveAt
  AND subject.hasApprovedEntitlement("WORKFORCE_READ")
ELSE DENY
~~~

Đây là mã giả. Một cổng preboarding hợp lệ có thể có scope **hạn chế riêng** trước effectiveAt. Không dùng quyền preboarding để truy cập hệ thống production.

### 18.2. Hủy Joiner

Khi ứng viên không nhận việc, IAM cần hủy kích hoạt, thu hồi group/account đã chuẩn bị và xử lý sự kiện trễ. PEP phải kiểm trạng thái hiện hành; **account đã tạo không còn là bằng chứng cho phép truy cập**.

## 19. Mover: chặn quyền cũ sau khi đổi vai trò

**Mover** thay đổi role, bộ phận, dự án, đơn vị, người quản lý hoặc phạm vi trách nhiệm. Employment status có thể vẫn ACTIVE, nhưng quyền trước đây không còn phù hợp.

| Hệ thống | Quyền trước | Desired sau Mover | Enforcement cần thiết |
| --- | --- | --- | --- |
| CRM | SupportCustomerRead | ABSENT | Chặn đọc dữ liệu Support |
| ERP | Không có | InvoiceRead | Cho phép sau khi đủ điều kiện |
| Analytics | SupportDashboard | FinanceDashboard | Chặn scope cũ, kiểm scope mới |
| Cloud IAM | SupportOpsRole | ABSENT | Chặn thao tác đặc quyền |
| VPN | BasicVPN | BasicVPN | Tiếp tục kiểm lifecycle |
| Session | Claim Support cũ | Claim/phiên mới | Đánh giá lại hoặc revoke theo risk |

### 19.1. Provisioning và enforcement phải phối hợp

IGA yêu cầu gỡ role, nhưng SCIM/API hoặc directory replication có thể chậm. PEP của ứng dụng phải hạn chế sử dụng role cũ theo chính sách hiện hành nếu có cơ chế truy cập nguồn mới hoặc invalidation. Tuy nhiên **PEP không thay thế deprovisioning**: role/credential cũ vẫn cần được thu hồi và đối soát.

### 19.2. Ngăn privilege creep

Chỉ thêm role mới mà không gỡ role cũ sẽ khiến người dùng tích lũy quyền qua nhiều lần Mover. Cần tính **desired access**, so với **observed access**, thu hồi EXTRA_ACCESS và kiểm tra quyền hiệu lực ở các đích.

### 19.3. Step-up không khôi phục quyền

Một người đã dùng passkey và hoàn thành step-up vẫn phải bị DENY nếu role Support đã hết hiệu lực. **Assurance và authorization là hai điều kiện độc lập**.

## 20. Leaver: chặn các đường truy cập tồn dư

**Leaver** yêu cầu chặn quyền khi quan hệ việc làm/hợp đồng hết hiệu lực, đồng thời xử lý account, entitlement, phiên, token và các principal liên quan.

- **HRIS/nguồn hợp đồng** xác định thời điểm kết thúc và quan hệ nào bị ảnh hưởng.
- **IdP** chặn đăng nhập mới và xử lý phiên/credential theo chính sách.
- **SCIM/API** deprovision account/role tại SaaS và hệ thống khác.
- **API/backend PEP** kiểm trạng thái hiện hành, không cho session/token cũ tự vượt qua Leaver.
- **Cloud/VPN** gỡ quyền, key, certificate hoặc đường truy cập độc lập khi có.
- **Reconciliation** xác minh thực trạng từng đích, quản lý ngoại lệ có owner.

### 20.1. Timeline minh họa

~~~text
18:00  HRIS: relationship TERMINATED
18:01  IdP disable account
18:02  SaaS-A SCIM deactivate thành công
18:03  SaaS-B API lỗi; local session vẫn còn
18:04  SaaS-B backend đọc trạng thái quyền hiện hành -> DENY
18:09  SaaS-B deprovision hoàn tất, session được xử lý
18:10  IAM đối soát từng hệ thống bắt buộc
~~~

Các thời điểm là **dữ liệu giả định**, không phải SLA chung. Nếu SaaS-B tiếp tục PERMIT vì chỉ kiểm cookie/role cache từ hôm trước, offboarding chưa an toàn.

### 20.2. Nhiều quan hệ làm việc

Một người kết thúc hợp đồng tại pháp nhân A nhưng vẫn là nhân viên hợp lệ của pháp nhân B. Policy cần kiểm **quan hệ nào cấp quyền cho tài nguyên cụ thể**, không tự chặn mọi quyền của identity khi chỉ một relationship kết thúc.

### 20.3. Nguy cơ token và phiên

Một JWT còn thời hạn có thể chứa role cũ. Khi yêu cầu chặn gần tức thời, cần thiết kế **short-lived token, revocation/introspection, session invalidation hoặc current-state lookup** theo khả năng hệ thống. Không tuyên bố mọi token có thể revoke tức thì nếu API không hỗ trợ.

## 21. Tài khoản dịch vụ và workload principal

**Service account, bot, CI/CD pipeline, workload identity** cần chính sách riêng. Chúng không có employment status như con người.

| Điều kiện | Ví dụ | Mục đích |
| --- | --- | --- |
| **Principal** | deploy-job-prod | Định danh service/job |
| **Owner** | platform-team | Có người chịu trách nhiệm |
| **Purpose** | release deployment | Không dùng cho tác vụ khác |
| **Environment** | production | Phân tách dev/prod |
| **Audience** | deployment-api | Credential không dùng sai API |
| **Scope** | deployment.create | Không thành cloud admin toàn cục |
| **Expiry** | credential ngắn hạn | Giảm cửa sổ lạm dụng |
| **Approval** | release approval | Kiểm soát thao tác nguy hiểm |
| **Lifecycle** | active / decommissioned | Thu hồi khi workload kết thúc |

### 21.1. Workload có quyền cao không được làm thay user tùy ý

Nếu người dùng gửi lệnh cho service triển khai, PEP cần kiểm:

- User có quyền yêu cầu hành động không.
- Service có quyền thực thi trên tài nguyên không.
- Phạm vi và phiên bản release đã được duyệt không.
- SoD, approval và hạn dùng còn hiệu lực không.

Không sử dụng quyền cao của service principal để bỏ qua user authorization.

### 21.2. Owner Mover/Leaver

Khi người phụ trách workload chuyển vai trò hoặc nghỉ việc, cần **gỡ quyền quản trị của người cũ, bàn giao owner, rà credential/trust và quyền workload**. Không xóa một dịch vụ đang chạy sản xuất chỉ vì owner cũ đã Leaver.

## 22. Approval, SoD, JIT và ngoại lệ

Một số quyền được phép chỉ khi có **business approval**, **Segregation of Duties (SoD)** hoặc **Just-in-Time (JIT) privilege**.

### 22.1. Ví dụ rule approval

~~~text
PERMIT payment.approve WHEN
  subject.hasApprovedRole("PaymentApprover")
  AND approval.validFor(payment.id)
  AND approval.expiresAt > now
  AND subject.identityId != payment.createdBy
  AND payment.amount <= approval.maxAmount
  AND authentication.freshStrongProof
ELSE DENY
~~~

Mã giả này cho thấy role đơn lẻ chưa đủ. Approval cho payment-A không được áp cho payment-B; người đã tạo giao dịch không tự phê duyệt nếu policy SoD cấm.

### 22.2. JIT/PAM

Một quy trình kích hoạt admin hợp lệ thường cần:

1. Kiểm eligibility và role đã được phê duyệt.
2. Step-up đủ mức, gần thời điểm hành động.
3. Approval hoặc cơ chế break-glass đúng chính sách.
4. Cấp entitlement hẹp và có ngày hết hạn.
5. PEP chặn hành động khi expiry qua.
6. IAM thu hồi role và reconciliation xác minh.

**Một quyền JIT đã hết hiệu lực phải bị DENY dù connector gỡ role đang bị chậm.**

### 22.3. Ngoại lệ không phải bypass cố định

Break-glass cần scope, thời hạn, owner, credential bảo vệ, logging và review hậu sự cố. Không viết rule “nếu PDP không hoạt động thì ai cũng được phép quản trị”.

## 23. Audit: chứng minh quyết định và tác động

Một log authorization hữu ích trả lời:

- **Ai** hoặc workload nào yêu cầu?
- **Action/resource/tenant** là gì?
- **Nguồn thuộc tính và policy version** nào được dùng?
- PDP trả PERMIT, DENY hay INDETERMINATE?
- **PEP có chặn/thực thi đúng phạm vi không?**
- Obligations được đáp ứng chưa?
- Có lỗi cache, PDP/PIP, token hoặc JML không?

### 23.1. Bản ghi mẫu

~~~json
{
  "correlationId": "req-20261123-1241",
  "decisionId": "authz-7721",
  "identityId": "person-1042",
  "principalType": "HUMAN",
  "clientId": "finance-portal",
  "action": "invoice.read",
  "resourceRef": "inv-412",
  "tenantRef": "tenant-a",
  "policyId": "finance-invoice-read",
  "policyVersion": 8,
  "decision": "DENY",
  "reasonCode": "RESOURCE_TENANT_MISMATCH",
  "enforcementResult": "BLOCKED",
  "evaluatedAt": "2026-11-23T10:00:00+07:00"
}
~~~

Đây là **JSON minh họa**, không phải schema chuẩn chung.

### 23.2. Ba kết quả khác nhau

~~~text
Authentication: SUCCEEDED
Authorization: DENY
Enforcement: BLOCKED
~~~

Và:

~~~text
Authentication: SUCCEEDED
Authorization: PERMIT
Enforcement: FAILED (database unavailable)
~~~

**PDP trả PERMIT không có nghĩa giao dịch đã chạy thành công.** Ngược lại, DENY thành công nghĩa là hành động đã bị ngăn, không phải lỗi hệ thống cần mở quyền.

Không ghi password, OTP, private key, full access/refresh token, session cookie hoặc dữ liệu nhạy cảm không cần vào audit log. Dùng reference an toàn và retention phù hợp.

## 24. Những lỗ hổng enforcement phổ biến

| Lỗ hổng | Ví dụ | Cách phòng vệ |
| --- | --- | --- |
| **Missing PEP** | Endpoint delete không gọi policy | Kiểm thử mọi đường thực thi |
| **Frontend-only control** | Ẩn nút nhưng API vẫn cho | Chặn tại backend |
| **BOLA/IDOR** | Đổi ID để đọc tài nguyên khác | Object-level authorization |
| **Broken Function Level Authorization** | Reader gọi API Admin | Permission theo action |
| **Mass assignment** | Client sửa role, owner hoặc status | Allowlist field được phép cập nhật |
| **Tenant spoofing** | Client tự khai tenantId khác | Tenant context đáng tin |
| **Confused deputy** | Service quyền cao làm thay user trái phép | Kiểm user+workload và delegated scope |
| **Stale group/role** | Token cũ sau Mover còn quyền | Invalidate/recheck/revoke phù hợp |
| **PDP fail-open** | PDP timeout thì mặc định PERMIT | Fail-safe, exception riêng |
| **TOCTOU** | Role bị gỡ trước khi DB commit | Conditional update/transaction |
| **Policy conflict** | Rule allow ghi đè deny bảo mật | Quy tắc kết hợp rõ |
| **Incorrect decision cache** | PERMIT tenant-A dùng tenant-B | Context/version đầy đủ |
| **Unsafe impersonation** | Admin support giả user không audit | Delegation có thẩm quyền |
| **Async bypass** | Export job chạy sau Leaver | Reauthorize khi chạy/trả kết quả |
| **Service excessive privilege** | Cloud role wildcard | Least privilege và owner lifecycle |

### 24.1. Test âm tính bắt buộc

Một hệ thống chỉ có bài test PERMIT thành công sẽ khó phát hiện bypass. Cần thử:

- Đúng role nhưng **sai tenant**.
- Đúng tenant nhưng **không sở hữu resource**.
- Approval hết hạn hoặc bị thu hồi.
- Người dùng tự gửi role=ADMIN trong request.
- Mover/Leaver còn token hoặc session cũ.
- PDP/PIP không khả dụng.
- Cache policy và cache attribute quá cũ.
- Hai request đồng thời khi resource đổi owner.
- Background job chạy sau khi identity bị khóa.
- Workload principal đúng nhưng user không có quyền yêu cầu.

## 25. Kiểm thử và triển khai policy an toàn

### 25.1. Ma trận test

| Subject/context | Action | Resource | Kỳ vọng |
| --- | --- | --- | --- |
| ACTIVE FinanceReader tenant-A | invoice.read | Invoice Finance tenant-A | PERMIT nếu đủ điều kiện |
| ACTIVE FinanceReader tenant-A | invoice.read | Invoice tenant-B | DENY |
| ACTIVE FinanceReader tenant-A | invoice.approve | Invoice tenant-A | DENY |
| FinanceApprover thiếu approval | invoice.approve | Invoice tenant-A | DENY |
| FinanceApprover tự tạo invoice | invoice.approve | Chính invoice đó | DENY theo SoD |
| FinanceApprover xác thực quá cũ | invoice.approve | Invoice tenant-A | Chặn, yêu cầu step-up |
| Mover rời Finance, token còn role cũ | invoice.read | Invoice Finance | DENY |
| Leaver còn session | invoice.read | Mọi invoice | DENY |
| Workload không có scope | invoice.export | Invoice tenant-A | DENY |
| PIP lỗi lifecycle status | invoice.approve | Invoice tenant-A | INDETERMINATE và chặn |

Các giá trị kỳ vọng theo **policy minh họa**; từng tổ chức cần bổ sung ngoại lệ, scope, phân loại dữ liệu và trường hợp thực tế.

### 25.2. End-to-end test

Kiểm thử phải chứng minh:

- PDP trả đúng, và PEP **ngăn side effect** khi DENY.
- Không có endpoint, gRPC, queue hoặc admin API nào bypass.
- Policy version/attribute được áp dụng đúng instance.
- JML events làm invalidation hoặc kích hoạt kiểm tra lại.
- Audit phân biệt policy decision và business result.
- Fail-safe hoạt động khi PDP/PIP timeout hoặc mạng bị chia cắt.
- Quyền theo tenant/owner được kiểm ngay trên resource.
- Break-glass có giới hạn và được kiểm toán.

### 25.3. Shadow evaluation và rollout

Một policy mới có thể được đánh giá ở **shadow mode** để so kết quả dự kiến với policy đang thực thi, nhưng shadow result **không nên tự cấp quyền thật**.

Rollout nên gồm approval, kiểm thử, canary, version tracking, giám sát và kế hoạch rollback có kiểm soát. Rollback về policy cũ rộng hơn có thể **mở lại đặc quyền**, nên phải đánh giá bảo mật trước.

## 26. Chỉ số vận hành

| Chỉ số | Mục đích |
| --- | --- |
| **Policy evaluation latency** | Theo dõi độ trễ PDP |
| **Enforcement coverage** | Bao nhiêu API/domain operation có PEP được kiểm chứng |
| **Decision distribution** | PERMIT/DENY theo action/resource và risk |
| **Indeterminate rate** | Phát hiện lỗi PIP/PDP |
| **Fail-open incidents** | Phát hiện thao tác không có quyết định hợp lệ vẫn được chạy |
| **Stale policy/attribute age** | Theo dõi dữ liệu cũ dẫn tới quyền tồn dư |
| **BOLA/tenant isolation findings** | Đo lỗ hổng cấp đối tượng/tenant |
| **SoD violation count** | Giám sát vi phạm phân tách nhiệm vụ |
| **JIT expiry compliance** | Quyền tạm thời hết hạn đúng policy |
| **Leaver denial latency** | Từ effectiveAt đến khi PEP chặn theo policy |
| **Audit completeness** | Đủ actor, action, resource, decision và outcome |
| **Service identity policy coverage** | Workload có owner, expiry và scope hợp lệ |

**Tỷ lệ login SSO thành công hay số lần PDP PERMIT không chứng minh hệ thống phân quyền an toàn.** Cần đối soát trạng thái thực tế và kiểm tra PEP không có đường bypass.

## 27. Tình huống tổng hợp: cổng tài chính nhiều tenant

Giả sử doanh nghiệp có Finance Portal, đăng nhập OIDC SSO và dữ liệu hóa đơn trong nhiều tenant.

### 27.1. Joiner

**An** được tuyển vào Finance, effectiveAt 01/12/2026. HRIS xác nhận hồ sơ, IdP tạo account và IGA phê duyệt FinanceReader qua SCIM.

- Trước effectiveAt, An chỉ có preboarding scope nếu policy cho phép.
- Sau effectiveAt, backend kiểm FinanceReader, tenant và department trước khi trả invoice.
- Reconciliation xác minh đã có quyền đúng và không có FinanceAdmin.

### 27.2. Mover

Ngày 10/01/2027, An chuyển sang Operations. IGA tính desired mới, gỡ FinanceReader; token cũ vẫn có claim Finance.

An gọi API đọc invoice, nhưng backend PEP kiểm trạng thái/role hiện hành và **DENY**. IAM tiếp tục thu hồi group/role, xử lý phiên và đối soát quyền cũ. **Xác thực đúng không làm quyền Finance còn hợp lệ sau Mover.**

### 27.3. Leaver

An nghỉ việc. IdP chặn login mới nhưng một local session của Finance Portal chưa hết hạn. PEP kiểm lifecycle status hiện hành và DENY. Các job export chưa chạy được đánh giá lại theo policy; token/phiên và các account SaaS được thu hồi, reconciliation xác minh.

### 27.4. PDP lỗi khi duyệt thanh toán

Finance Portal không gọi được PDP trong lúc một người dùng yêu cầu phê duyệt thanh toán. Hệ thống **không tự PERMIT vì user đã MFA**, mà chặn hoặc dùng quy trình ngoại lệ đã được phê duyệt. Audit ghi lỗi và owner chịu trách nhiệm khắc phục.

## 28. Checklist thiết kế policy enforcement

| Câu hỏi | Bằng chứng |
| --- | --- |
| Authentication, authorization decision và enforcement đã tách rõ? | Thiết kế OP/RP/PEP/PDP |
| PEP bảo vệ mọi endpoint, job và service? | Inventory, integration tests |
| Có deny-by-default? | Negative tests |
| Principal lấy từ token/session đã kiểm chứng? | Issuer/audience/signature/identity link |
| Action được kiểm theo permission cụ thể? | Role–permission mapping |
| Resource, owner và tenant được kiểm? | Object-level tests và query scope |
| PIP thuộc tính có nguồn có thẩm quyền? | HRIS/IGA/resource ownership |
| Policy conflict và obligations được định nghĩa? | Policy combining rules |
| Approval, SoD và JIT được kiểm? | Records có expiry và scope |
| Mover có chặn role/token cũ? | Current-state tests, invalidation |
| Leaver còn session có bị DENY? | Session test và deprovision workflow |
| SCIM/API được dùng đúng vai trò? | Provisioning và reconciliation |
| Có xử lý TOCTOU? | Transaction/version checks |
| DB và object storage có defense in depth? | RLS/query filtering, object policy |
| Microservice kiểm user và workload authority? | Delegation và mTLS/token |
| Async jobs tái kiểm quyền khi cần? | Job authorization test |
| PDP/PIP outage xử lý an toàn? | Fallback/runbook và fault tests |
| Cache có TTL, key và invalidation đúng? | Policy/identity/resource versions |
| Có kiểm policy rollout nhiều instance? | Version telemetry và drift |
| Log tách decision và execution? | Correlation ID, action, result |
| Không lộ token/secret trong audit? | Redaction, quyền đọc và retention |
| Workload có owner và least privilege? | Service identity inventory |
| Có test BOLA, tenant spoofing và mass assignment? | Negative test matrix |
| Có KPI enforcement coverage và residual access? | Dashboard và owner |

## 29. Những nhầm lẫn thường gặp

1. **“Có rule Admin là đủ.”** Không có PEP ở endpoint, rule có thể bị bỏ qua.
2. **“OIDC/SSO đăng nhập thành công nghĩa là được phép.”** Authentication không quyết định quyền nghiệp vụ.
3. **“Ẩn nút là chặn quyền.”** Backend vẫn cần kiểm.
4. **“Gateway đã kiểm scope, service không cần kiểm invoice owner.”** Gateway thường thiếu ngữ cảnh đối tượng.
5. **“PDP PERMIT là backend có thể bỏ constraints.”** PEP phải thực thi đầy đủ điều kiện.
6. **“Token còn hạn thì role chắc chắn còn hợp lệ.”** Mover/Leaver có thể thu hồi quyền trước khi token hết hạn.
7. **“PDP lỗi thì mặc định cho phép.”** Cần fail-safe và ngoại lệ được kiểm soát.
8. **“Cùng role thì xem được mọi tenant.”** Tenant isolation là điều kiện riêng.
9. **“Object ID khó đoán nên không cần kiểm quyền.”** ID không phải chứng cứ authorization.
10. **“SoD chỉ là so hai role.”** Còn có điều kiện theo actor, creator và giao dịch.
11. **“SCIM deactivation chấm dứt mọi token/phiên.”** Phạm vi SCIM khác session management.
12. **“Một PERMIT cache dùng được cho mọi resource.”** Decision phụ thuộc context và version.
13. **“Service quyền cao được làm thay mọi người dùng.”** Cần cả user và workload authority.
14. **“Step-up có thể sửa quyền cấp nhầm.”** Xác thực mạnh không hợp thức hóa entitlement không được duyệt.
15. **“Leaver chỉ cần disable IdP.”** API, SaaS, token và local session cần xử lý riêng.
16. **“Log PERMIT nghĩa là giao dịch thành công.”** Quyết định khác kết quả thực thi.

## 30. Câu hỏi tự đánh giá

1. Policy enforcement khác policy decision ra sao? Cho ví dụ PDP đúng nhưng PEP sai.
2. PEP, PDP, PIP, PAP có trách nhiệm gì và dữ liệu đi qua chúng thế nào?
3. Vì sao deny by default và complete mediation quan trọng hơn chỉ ẩn nút?
4. Vì sao access token hợp lệ chưa đủ để đọc invoice-412?
5. RBAC FinanceReader cần kết hợp điều kiện ABAC tenant và department ra sao?
6. BOLA khác thiếu quyền trên API Admin ở điểm nào?
7. Khi client gửi tenantId giả, backend nên làm gì?
8. PDP trả PERMIT kèm maxRows và audit obligation. PEP phải làm gì?
9. Nếu PIP không trả employment status, vì sao không mặc định ACTIVE?
10. Caching có thể khiến role Support còn hiệu lực sau Mover như thế nào?
11. Giải thích TOCTOU khi role bị thu hồi giữa lúc PDP quyết định và DB commit.
12. Vì sao export worker cần kiểm lại quyền khi chạy?
13. User principal khác workload principal thế nào trong service-to-service call?
14. Leaver còn session nhưng IdP disabled: PEP phải hành xử ra sao?
15. Step-up thành công có cho phép bỏ qua approval và SoD không?
16. Vì sao service account cần owner và policy riêng?
17. Viết một negative test chống đọc chéo tenant.
18. Làm sao theo dõi policy rollout tới mọi service instance?
19. Audit cần ghi gì để phân biệt DENY và lỗi DB sau PERMIT?
20. Nêu ba KPI đánh giá enforcement thật thay vì chỉ đếm rule hoặc lần đăng nhập.

## 31. Ghi nhớ

**Policy enforcement** biến **quyết định phân quyền thành hành vi thực tế**. Một hệ thống IAM không chỉ kiểm role, mà phải xác định **đúng chủ thể, hành động, tài nguyên, tenant, thuộc tính, thời điểm, phê duyệt và ngữ cảnh**. **PEP** đáng tin chặn hoặc thực thi theo **PDP**, dựa trên thuộc tính **PIP** và chính sách được quản trị bởi **PAP**.

Trong **Joiner–Mover–Leaver**, **IdP/SSO** hỗ trợ xác thực, **SCIM/API** quản lý tài khoản, **RBAC/ABAC** xác định entitlement, còn **PEP ở backend/API/data plane** bảo đảm quyền được áp dụng đúng tại thời điểm sử dụng. Để giảm **quyền truy cập tồn dư**, cần **deny by default, kiểm quyền từng đối tượng/tenant, chống bypass, xử lý cache và phiên cũ, bảo vệ workload principal, tái kiểm khi JML thay đổi, audit và reconciliation**. **Một quyết định PERMIT hay một lệnh deprovision thành công không tự chứng minh mọi đường truy cập đã an toàn**; bằng chứng cuối là thao tác hợp lệ được thực hiện đúng scope và thao tác trái quyền thực sự bị chặn.
