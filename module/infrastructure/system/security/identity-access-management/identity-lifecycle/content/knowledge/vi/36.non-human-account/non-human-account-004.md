# Integration account trong IAM: tài khoản tích hợp giữa các hệ thống

> **Chương:** Non-human account  
> **Bài:** Integration account  
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE  
> **Bối cảnh:** Quản lý vòng đời danh tính trong IAM theo mô hình **Joiner–Mover–Leaver**, từ xác minh và cấp quyền đến rà soát, thay đổi vai trò và thu hồi. Nội dung gắn với **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm **quyền truy cập tồn dư**.

## 1. Integration account là gì?

Một doanh nghiệp cần đồng bộ đơn hàng từ hệ thống bán hàng sang hệ thống kế toán. Cứ 15 phút, một connector tự động gọi API của hai hệ thống, đọc dữ liệu đã phát sinh rồi ghi bản ghi kế toán. Connector không có nhân viên ngồi đăng nhập và bấm nút mỗi lần chạy. Tuy nhiên, hệ thống đích vẫn cần nhận diện caller, kiểm tra quyền và ghi nhận người chịu trách nhiệm.

**Integration account (tài khoản tích hợp)** là **account hoặc principal được dành cho một kết nối tự động giữa các hệ thống, ứng dụng hoặc dịch vụ**, dùng để xác thực và thực hiện các thao tác đã được cấp quyền phục vụ một mục đích tích hợp cụ thể.

Nó thường được xếp vào nhóm **non-human account** vì được vận hành bởi phần mềm hoặc tác vụ thay vì một phiên làm việc thường xuyên của con người. Tuy vậy, hình thức thực tế phụ thuộc hệ thống đích: có thể là service principal, OAuth client, API credential gắn principal, managed identity hoặc **technical user account** do SaaS yêu cầu.

### 1.1. Ví dụ: đồng bộ đơn hàng

~~~text
Nguồn: Sales SaaS
Đích: Accounting SaaS
Tiến trình: order-sync-worker
Danh tính: integration-sales-accounting-prod
Quyền nguồn: orders.read trên đúng tenant
Quyền đích: invoices.create trên đúng tenant
Lịch chạy: mỗi 15 phút
Owner: Integration Platform Team
Căn cứ: SYNC-ORDER-001
~~~

Tài khoản này **không cần** quyền đổi chính sách IAM, xóa toàn bộ hóa đơn, quản trị người dùng hoặc xuất tất cả thông tin khách hàng nếu nhiệm vụ chỉ là đọc đơn hàng và tạo hóa đơn.

### 1.2. Vấn đề nếu mượn account cá nhân

Khi connector dùng username/password hoặc refresh token cá nhân của một nhân viên, các rủi ro xuất hiện:

- Nhân viên nghỉ việc khiến integration dừng hoặc credential tiếp tục tồn tại ngoài kiểm soát.
- Quyền API có thể rộng bằng toàn bộ vai trò người dùng, không đúng least privilege.
- Audit khó phân biệt hành động của người và tác vụ máy.
- MFA/reset mật khẩu của người dùng làm job thất bại.
- Rotation và revoke dễ ảnh hưởng ứng dụng ngoài dự kiến.
- Không có owner kỹ thuật và hồ sơ dependency rõ ràng.

**Nguyên tắc:** Dùng identity tích hợp riêng khi nhà cung cấp hỗ trợ; với integration buộc dùng quyền được ủy quyền bởi người dùng, phải quản lý rõ **người ủy quyền, scope, consent, token và vòng đời** thay vì giả định đó là service principal độc lập.

## 2. Phân biệt Integration account với các khái niệm gần nhau

| Khái niệm | Trọng tâm | Điểm cần phân biệt |
|---|---|---|
| **Integration account** | Danh tính/account dùng cho kết nối hệ thống–hệ thống | Phân loại theo **mục đích sử dụng** |
| **Service identity** | Danh tính logic của một workload/dịch vụ | Phân loại theo **chủ thể** |
| **Service account** | Account được nền tảng cung cấp cho service hoặc automation | Cơ chế và quyền tùy nền tảng |
| **Service principal** | Principal ứng dụng được hệ thống IAM nhận diện | Không nhất thiết là user account |
| **OAuth client** | Client đăng ký với authorization server | Client ID không phải secret; grant phụ thuộc flow |
| **Managed identity** | Danh tính được nền tảng gắn cho workload | Có thể dùng làm principal của integration |
| **Technical user** | Account có dạng người dùng nhưng dùng cho tích hợp tự động | Cần ngoại lệ/kiểm soát login và MFA phù hợp |
| **End-user delegated connection** | Ứng dụng dùng token được user ủy quyền | Quyền phụ thuộc user và consent |
| **API key** | Credential để gọi API | Key **không tự là account** hoặc permission đầy đủ |
| **Webhook signing secret** | Khóa xác minh nguồn và tính toàn vẹn thông điệp | Không giống access token cho API |

**Integration account là vai trò nghiệp vụ/kỹ thuật của một danh tính, không phải một kiểu đối tượng chuẩn duy nhất.**

### 2.1. Identity, account, credential và entitlement

- **Identity/principal:** chủ thể được nhận diện, có identifier ổn định và trust boundary.
- **Account:** đối tượng mà hệ thống đích quản lý, có thể chứa role, profile, trạng thái.
- **Credential:** secret, certificate, private key hoặc proof dùng để xác thực.
- **Token:** bằng chứng được phát theo giao thức, có issuer/audience/expiry/scope.
- **Entitlement:** role/permission/ACL cho biết principal được làm gì và trên tài nguyên nào.

Một integration account có thể rotate credential nhiều lần nhưng giữ cùng principal ID. Khi xóa credential mà không gỡ role, entitlement có thể vẫn tồn tại để credential khác sử dụng.

### 2.2. Account tích hợp không nên là account dùng chung cho mọi connector

Một account được chia cho 12 hệ thống làm mất khả năng phân biệt ai đã gọi API, làm tăng blast radius khi secret lộ và khiến việc đổi secret có thể làm hỏng hàng loạt luồng. Nên tách theo **integration purpose, target, environment và risk boundary** khi khả thi.

## 3. Những nơi Integration account xuất hiện

| Loại tích hợp | Ví dụ | Thao tác |
|---|---|---|
| SaaS–SaaS | CRM đồng bộ Billing | Đọc khách hàng, tạo hóa đơn |
| ETL/ELT | Warehouse lấy dữ liệu từ CRM | Đọc tập dữ liệu chỉ định |
| iPaaS | Connector qua integration platform | Gọi API hai bên |
| ERP–HRIS | Đồng bộ trạng thái nhân sự | Đọc HR event, cập nhật account |
| Ticketing–IAM | Ticket trigger Access Request | Tra cứu ticket, cập nhật trạng thái |
| SIEM/SOAR | Thu log và kích hoạt phản ứng | Đọc log, thực thi hành động được duyệt |
| CI/CD–Cloud | Pipeline triển khai dịch vụ | Deploy phiên bản ứng dụng |
| SaaS–Webhook | Provider gửi event cho receiver | Xác minh signature, xử lý event |
| File exchange | SFTP/managed file transfer | Đọc/ghi thư mục và loại file |
| Monitoring | Connector gửi metrics | Ghi metrics vào collector |

Mỗi kết nối cần **mục đích cụ thể, owner, principal mapping, quyền, secret/trust lifecycle và cách ngắt kết nối**. Một integration có thể cần hai principal riêng: một để đọc từ hệ thống nguồn, một để ghi vào hệ thống đích.

### 3.1. Một integration có thể có nhiều account

Trong đồng bộ CRM → ERP, một API credential chỉ có read trên CRM, một service principal khác có write trên ERP. Không nhất thiết phải dùng cùng identity ở cả hai nhà cung cấp. Việc tách account giúp giảm tác động khi một connector hoặc một vendor bị xâm nhập.

### 3.2. Không nhầm tài khoản connector và tài khoản người dùng

Connector có thể quản lý vòng đời user qua SCIM. **Connector account** dùng quyền quản trị provisioning, trong khi **user accounts** là đối tượng mà connector tạo/gỡ. Nếu connector account bị thu hồi nhầm, cả quy trình Joiner–Mover–Leaver có thể dừng.

## 4. Mục tiêu an ninh đối với Integration account

Một thiết kế tích hợp tốt phải đáp ứng:

1. **Danh tính rõ:** có ID không nhập nhằng với human identity.
2. **Chủ sở hữu rõ:** technical owner và business/data owner.
3. **Nguồn xác thực đáng tin:** không dựa vào display name hoặc địa chỉ IP.
4. **Quyền tối thiểu:** action/resource/tenant/environment cụ thể.
5. **Bằng chứng triển khai:** mapping account, scope và target readback.
6. **Credential được bảo vệ:** không lộ secret qua code, log hay ticket.
7. **Rotation không gây outage:** có kế hoạch chuyển credential.
8. **Đời sống gắn nhu cầu:** integration ngừng thì account/grant được retire.
9. **Có thể kiểm toán:** truy nguyên được connector/job và actions.
10. **Phục hồi và thu hồi:** biết làm gì khi account bị compromise hoặc owner thay đổi.

### 4.1. Đặc quyền cho provisioning connector

Một integration quản lý User/Group qua SCIM có thể cần quyền tạo, sửa, disable account. Đây là **quyền quản trị rất nhạy cảm**. Hạn chế target tenant, connector trust, group assignment, phạm vi API và approver; không cấp thêm quyền dữ liệu kinh doanh nếu không phục vụ nhiệm vụ.

### 4.2. Nhất quán giữa source và target

Một account có thể bị khóa tại identity provider nhưng vẫn còn local SaaS role hoặc API key. IAM phải biết **đường truy cập thực tế**, không suy quyền đã hết chỉ từ một trạng thái.

## 5. Kiến trúc tham chiếu cho một integration

~~~mermaid
flowchart LR
    OWNER[Business và Technical Owner] --> REG[Integration Registry / IGA]
    REG --> IAM[Policy, Approval, Lifecycle]
    VAULT[Secret Manager / Trust Platform] --> WORK[Integration Connector]
    IAM --> VAULT
    WORK --> SOURCE[Source SaaS API]
    WORK --> TARGET[Target SaaS API]
    IAM --> SOURCE
    IAM --> TARGET
    SOURCE --> VERIFY[Readback / Reconciliation]
    TARGET --> VERIFY
    VERIFY --> AUDIT[Audit và Monitoring]
    REG --> AUDIT
    WORK --> AUDIT
~~~

**Luồng tổng quát:**

1. Chủ hệ thống đăng ký nhu cầu đồng bộ, dữ liệu được trao đổi và rủi ro.
2. IAM/IGA xét owner, trust, quyền cần thiết và chấp thuận phù hợp.
3. Tạo principal/account riêng tại từng target hoặc tại authorization server.
4. Lưu secret trong vault hoặc thiết lập federation/managed identity nếu khả thi.
5. Connector nhận credential/token đúng cách và thực hiện lệnh trong phạm vi cho phép.
6. Resource Server kiểm tra issuer/audience, quyền action/resource, tenant và điều kiện policy.
7. Ghi audit tương ứng với connector identity, integration ID, job run và correlation ID.
8. Khi scope hoặc lifecycle thay đổi, điều chỉnh/thu hồi grants, credential và session.
9. Readback để xác minh quyền hiệu lực thực tế.

### 5.1. Control plane khác data plane

- **Control plane:** nơi tạo account, gán role, phê duyệt, lưu owner, đổi trust và revoke.
- **Data plane:** nơi API/connector dùng quyền để đọc, sửa, ghi hoặc xóa dữ liệu.

Một record trong IAM có trạng thái REVOKED không tự chứng minh data plane đã từ chối token còn hạn hoặc local role tại SaaS.

### 5.2. Không sử dụng connector như “superuser trung tâm”

Một iPaaS có nhiều luồng không nên nhận chung một credential cloud-admin chỉ vì nó là nền tảng tích hợp. Nên tách theo connector, environment, tenant và resource scope; chỉ tích hợp nào cần quyền cao mới được xét riêng.

## 6. Những mô hình xác thực phổ biến

| Cơ chế | Cách dùng trong integration | Những điều phải kiểm tra |
|---|---|---|
| OAuth 2.0 client credentials | M2M khi AS/target hỗ trợ | Client authentication, scope, audience, issuer |
| OAuth authorization code + refresh token | Connector làm việc trong phạm vi user đã consent | User linkage, consent, refresh token và revoke |
| Private-key JWT / client certificate | Chứng minh client bằng key | Key management, clock và trusted issuer |
| mTLS | Xác thực peer ở kết nối TLS | Trust store/CA, certificate SAN, quyền ứng dụng |
| Managed/workload identity | Workload lấy token qua platform/trust | Issuer, subject, environment, permitted resource |
| API key | Tích hợp SaaS legacy | Secret storage, rotation, scopes, last used |
| SFTP SSH key | MFT/file integration | Authorized key, path isolation, key rotation |
| Basic authentication | Hệ thống legacy yêu cầu user/password | Ngoại lệ, TLS, vault, hạn chế interactive login |
| Signed webhook | Provider gửi event tới receiver | Signature, timestamp/replay và secret rotation |

### 6.1. OAuth client credentials là trường hợp thường gặp, không phải bắt buộc

OAuth client credentials phù hợp khi workload làm việc dưới danh tính client, không cần đại diện một người dùng cuối. Authorization Server có thể phát token sau client authentication, nhưng **target API vẫn phải kiểm tra resource-level authorization**. Scope xuất hiện trong token không tự cho phép truy cập mọi object.

### 6.2. User-delegated integration không đồng nghĩa non-human principal

Một SaaS chỉ hỗ trợ kết nối do user bấm consent. Dù automation chạy sau đó, token có thể vẫn mang authority của **người dùng đã ủy quyền**. Khi user Mover hoặc Leaver, quyền và token phải được đánh giá lại. Đừng gắn nhãn “service account độc lập” cho một delegated authorization chỉ vì nó chạy tự động.

### 6.3. Technical user và MFA

Một số vendor chỉ cho API truy cập bằng user account. Nếu phải tạo dedicated technical user, hãy xác nhận phương án được vendor hỗ trợ, hạn chế interactive login, áp dụng credential/vault, scope và kiểm toán. Không cố bypass MFA bằng cách dùng mật khẩu của người thật hay tự động lấy OTP trái chính sách.

### 6.4. Webhook xác thực khác API polling

Webhook có thể dùng shared secret để ký payload. Receiver cần kiểm tra chữ ký trên đúng raw payload theo hợp đồng, timestamp và nonce/event ID để chống replay. Một webhook signing secret **không mặc nhiên là access token** được phép dùng các API khác.

## 7. Phân biệt AuthN, AuthZ và consent

**Authentication (AuthN)** trả lời “Ai gọi API và có chứng minh được danh tính không?”.  
**Authorization (AuthZ)** trả lời “Principal đó có được làm action này trên resource này không?”.  
**Consent/delegation** xác định ai đã cho phép connector thay mặt user thực hiện việc gì theo luồng mà nhà cung cấp hỗ trợ.

~~~mermaid
sequenceDiagram
    participant C as Connector
    participant AS as Authorization Server
    participant API as Target API
    participant PDP as RBAC / ABAC Policy
    C->>AS: Chứng minh client/workload identity
    AS->>AS: Kiểm tra trust và quyền cấp token
    AS-->>C: Access token cho target audience
    C->>API: GET hoặc POST + access token
    API->>API: Validate token issuer/audience/exp/profile
    API->>PDP: Principal, action, target tenant/resource
    PDP-->>API: PERMIT hoặc DENY
    API-->>C: Response + request correlation
~~~

### 7.1. Token hợp lệ chưa có quyền trên mọi tài nguyên

Access token có scope orders.read vẫn có thể không được phép đọc order của tenant khác. API cần kiểm tra object owner, tenant, customer boundary, classification và các điều kiện khác.

### 7.2. Audience và issuer bắt buộc đúng contract

Không chấp nhận token dành cho CRM ở một ERP API chỉ vì cả hai cùng sử dụng một IdP. Resource Server phải áp dụng token validation profile phù hợp, gồm issuer, audience, signature/introspection, expiry, token type và quyền.

### 7.3. Không tin header tự khai

Một connector gửi header X-Service-Name: trusted-sync không đủ chứng minh caller là service đó. Phải ràng buộc request với principal đáng tin qua token/credential và policy.

## 8. Thiết kế account theo mục đích, môi trường và tenant

Với cùng một luồng dữ liệu, những boundary thường cần tách account:

| Boundary | Vì sao nên tách |
|---|---|
| Development / staging / production | Ngăn key dev gây thay đổi prod |
| Source / destination | Quyền đọc và ghi khác nhau |
| Customer tenant A / tenant B | Chống đọc/ghi chéo tenant |
| HR integration / finance integration | Phân loại dữ liệu và rủi ro khác nhau |
| Job runtime / deployment pipeline | Deploy-admin không cần cho runtime |
| Privileged connector / ordinary connector | Không cho mọi job kế thừa quyền admin |
| Partner A / partner B | Thu hồi một đối tác không ảnh hưởng đối tác khác |

### 8.1. Tên tài khoản nên tự giải thích

Ví dụ quy ước nội bộ minh họa:

~~~text
intg-sales-to-finance-prod
intg-hris-to-idp-prod
intg-customer-data-warehouse-staging
~~~

Đây là **tên hiển thị**. Hệ thống cần ID ổn định, namespace, owner và target account reference để tránh nhầm khi tên thay đổi.

### 8.2. Shared account chỉ là ngoại lệ có kiểm soát

Nếu vendor bắt buộc dùng một service user chung cho nhiều luồng, ghi rõ các integrations cùng phụ thuộc, scope/owner của từng luồng, cách rotate, audit bổ sung và kế hoạch giảm phụ thuộc. Không che giấu shared credential dưới nhãn “integration”.

### 8.3. Cấp quyền cả ở nguồn lẫn đích

Một connector đọc source và ghi target có thể gây lỗi bảo mật ngay cả khi một phía dùng least privilege. Đánh giá đồng thời khả năng xuất dữ liệu từ nguồn và thay đổi dữ liệu ở đích, tránh grant read-all từ nguồn hoặc write-all tại đích.

## 9. Registry và ownership của Integration account

Một danh sách API keys không đủ để quản lý vòng đời. Doanh nghiệp cần **integration registry**: tích hợp nào đang chạy, nguồn–đích nào, owner nào và principal nào có quyền.

Ví dụ **JSON giả lập**:

~~~json
{
  "integrationId": "intg-sales-accounting-prod",
  "purpose": "Đồng bộ đơn hàng thành hóa đơn",
  "environment": "production",
  "status": "ACTIVE",
  "source": {
    "system": "sales-saas",
    "tenant": "tenant-a",
    "principalId": "source-connection-42",
    "actions": ["orders.read"]
  },
  "destination": {
    "system": "accounting-saas",
    "tenant": "tenant-a",
    "principalId": "destination-client-18",
    "actions": ["invoices.create"]
  },
  "runtime": "order-sync-worker",
  "technicalOwner": "integration-platform",
  "businessOwner": "finance-operations",
  "dataClassification": "confidential",
  "authMethods": ["OAUTH_CLIENT_CREDENTIALS", "MANAGED_IDENTITY"],
  "secretReferences": ["vault://integrations/sales-accounting"],
  "schedule": "Every 15 minutes",
  "reviewBy": "2027-02-23T09:00:00+07:00",
  "changeTicket": "CHG-2841"
}
~~~

Đây không phải schema chính thức của vendor. Registry không chứa client secret, private key, refresh token hoặc access token nguyên dạng.

### 9.1. Chủ thể và trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| Technical owner | Vận hành connector, secret rotation, log/incident, availability |
| Business owner | Xác nhận tích hợp còn cần thiết |
| Data owner | Duyệt loại dữ liệu, phạm vi đọc/ghi, retention |
| Target system owner | Duyệt role/grant ở hệ thống đích |
| IAM/Security | Policy, SoD, access review, audit, exceptions |

Với integration đặc quyền, người tự yêu cầu không nên mặc định tự phê duyệt và tự xác minh grant. Các vai trò có thể do cùng người giữ trong một hệ thống nhỏ nhưng cần risk/SoD policy rõ.

### 9.2. Một account có thể phục vụ nhiều integrations

Nếu vendor chỉ cho một technical user chung, registry phải mô tả tất cả workflows phụ thuộc. Khi một luồng ngừng, không xóa account khi luồng khác còn cần; thay vào đó gỡ phạm vi quyền không còn căn cứ và có kế hoạch tách identity.

### 9.3. Stable ID khác display name

Dùng identity ID, tenant, issuer và target account reference làm khóa. Tên hoặc email alias có thể thay đổi và được tái sử dụng, không đủ để xác định account nào cần revoke.

## 10. Least Privilege xuyên suốt nguồn và đích

Một integration là cầu nối giữa các hệ thống, nên phân tích quyền **trên cả hai phía**, không chỉ target nơi chạy connector.

| Trục | Câu hỏi | Ví dụ |
|---|---|---|
| Principal | Connector nào? | order-sync-worker-prod |
| Source action | Được đọc gì? | orders.read |
| Source resource | Đọc thuộc tenant nào? | Sales tenant A |
| Destination action | Được ghi gì? | invoices.create |
| Destination resource | Ghi vào đâu? | Accounting tenant A |
| Data fields | Thu thập dữ liệu tối thiểu? | ID, ngày, tổng tiền |
| Environment | Dev có truy cập prod? | Không |
| Time | Quyền cần trong bao lâu? | Theo lifecycle, JIT cho admin |
| Delegation | Có tạo grants khác không? | Không cấp iam.roles.assign |
| Audit | Có truy được run không? | integration ID + correlation ID |

### 10.1. Data minimization đi cùng authorization

Chỉ cần mã đơn hàng và tổng tiền thì không nên cấp read-all customer profiles. Nếu API hỗ trợ filter/field selection, dùng chúng để giảm lượng dữ liệu nhạy cảm xử lý.

### 10.2. Quyền đọc rộng cũng nguy hiểm

Một nguồn cho read-all nhưng đích chỉ write một loại báo cáo vẫn tạo kênh có thể bị lạm dụng để trích xuất dữ liệu. Đánh giá đồng thời **exfiltration ở nguồn** và **modification ở đích**.

### 10.3. RBAC và ABAC

Role RBAC có thể là orders-reader và invoice-writer. ABAC kiểm tra tenantId, classification, môi trường và trạng thái integration.

~~~text
PERMIT nếu:
    principal.type == INTEGRATION
    AND principal.status == ACTIVE
    AND principal.integrationId == "intg-sales-accounting-prod"
    AND action == "invoices.create"
    AND resource.tenantId == principal.tenantId
    AND principal.environment == "production"
    AND grant.approvalStatus == VALID
~~~

Đây là pseudo-policy. Không tin những thuộc tính caller tự khai trong HTTP header; cần kiểm tra từ token/trust policy và resource catalog đáng tin.

### 10.4. Secondary grants

Tài khoản có quyền role.assign, apiKey.create hoặc document.share có thể tạo access tồn tại sau khi credential hiện tại hết hạn. Những quyền này cần giới hạn, phê duyệt và kiểm toán riêng.

## 11. Credential security và rotation

Credential tích hợp có thể bị sử dụng ngoài giờ chạy nếu bị lộ. Tài khoản không có người tương tác thường có token/key tồn tại lâu và ít được chú ý.

### 11.1. Biện pháp cơ bản

1. Ưu tiên managed identity, workload federation hoặc credential ngắn hạn khi provider hỗ trợ.
2. Nếu dùng secret tĩnh, lưu trong vault hoặc secret manager.
3. Không hardcode API key trong code/config/image, cũng không đưa vào ticket.
4. Không in Authorization header, token, key vào logs/CI output.
5. Giới hạn người được xem/export/rotate credential.
6. Gắn owner, inventory, last-used telemetry, rotation schedule.
7. Kiểm tra quyền của credential và trust/runtime được phép sử dụng.
8. Revoke/rotate theo incident response khi nghi bị lộ.

### 11.2. Rotation với hai key song song

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant V as Vault
    participant A as API Provider
    participant C as Connector
    O->>A: Yêu cầu key mới
    A-->>O: Credential version mới
    O->>V: Lưu version mới an toàn
    C->>V: Lấy credential mới
    C->>A: Gọi thử API scope hẹp
    A-->>C: Success
    O->>A: Revoke key cũ
    O->>A: Kiểm chứng old key bị chặn
~~~

Nếu provider không hỗ trợ overlap, cần kế hoạch cutover khác. Không giả định việc key mới hoạt động đồng nghĩa key cũ đã hết hiệu lực.

### 11.3. Refresh token có thể sống lâu hơn access token

Một delegated OAuth connection có thể liên tục đổi refresh token lấy access token. Cần xử lý refresh token storage, binding, rotation, revocation và consent. Người dùng logout không mặc định chặn mọi refresh token theo mọi provider.

### 11.4. Rotation khác thu hồi entitlement

Đổi API key không gỡ role trong SaaS; gỡ role không tự xóa key trong vault. Credential lifecycle, account lifecycle và permission lifecycle phải được quản trị riêng.

## 12. Joiner: tạo Integration account và đưa vào hoạt động

Joiner của integration bắt đầu khi xuất hiện một kết nối mới có nhiệm vụ chính đáng, **không đồng nghĩa nhân viên mới vào làm**.

Quy trình:

1. Xác nhận source, destination, mục đích, dữ liệu và lịch chạy.
2. Phân loại rủi ro: PII, tài chính, production, admin, cross-tenant.
3. Chỉ định technical owner, business/data owner và on-call.
4. Chọn identity model theo khả năng nhà cung cấp.
5. Xác định OAuth client/service principal/technical user hoặc delegated connection.
6. Xác định authentication, issuer, audience, runtime trust.
7. Phê duyệt scopes/roles ở **cả nguồn và đích**, xử lý SoD.
8. Tạo account/principal/grant và lưu secret reference.
9. Kiểm chứng account mapping, effective access và tenant.
10. Chạy positive/negative tests theo action/resource.
11. Thiết lập log, monitoring, rotation/reviewBy và decommission trigger.
12. Ghi change ticket, owner và chứng cứ hoàn tất.

### 12.1. Hai approval có thể cần thiết

Source data owner duyệt việc đọc/xuất dữ liệu; target owner duyệt việc tạo/sửa bản ghi. Một người có quyền sửa ERP không tự có thẩm quyền xuất toàn bộ dữ liệu từ CRM.

### 12.2. Account provisioned sớm không có nghĩa quyền được mở sớm

Có thể tạo principal trước ngày go-live nhưng hạn chế issuance/role/scope production tới thời điểm được duyệt. Với quyền nhạy cảm, readback và kiểm tra tại resource server là cần thiết.

### 12.3. Chống tạo trùng khi retry

Khi automation gặp timeout rồi thử lại, không tự tạo credential/account thứ hai ngoài inventory. Dùng integration ID, request ID, target resource mapping, và kiểm tra trạng thái desired/actual với idempotency.

## 13. Mover: integration thay đổi scope, target hoặc chủ sở hữu

Một integration có thể thay đổi mà không bị xóa: chuyển tenant, chuyển vendor, thay API endpoint, bổ sung chức năng write, thay môi trường hoặc được giao cho một team khác.

### 13.1. Tính quyền mong muốn trước khi chuyển

Ví dụ đồng bộ dữ liệu từ tenant A sang tenant B:

~~~text
Trước:
    CRM tenant-a: contacts.read
    ERP tenant-a: orders.create

Sau:
    CRM tenant-b: contacts.read
    ERP tenant-b: orders.create

Điều kiện hoàn tất:
    approval của owner tenant-b hợp lệ
    rights tenant-b được cấp đúng
    connector chạy được trong phạm vi mới
    rights tenant-a bị thu hồi khi hết nhu cầu
    readback cả hai tenant
~~~

Chỉ thêm quyền mới mà không gỡ quyền cũ tạo **residual access**; role cũ có thể được dùng ngay cả khi connector đã chuyển traffic.

### 13.2. Đổi vendor không xóa hết kết nối cũ tự động

Khi chuyển CRM A sang CRM B, cần kiểm tra:

- API client và refresh token ở CRM A.
- Webhook subscription và secret ký webhook.
- Scheduled export jobs vẫn chạy ở SaaS A.
- Direct grants, local service user và audit permissions.
- Data transfer/config backup còn chứa credential.
- Connector khác dùng chung account với luồng cũ.

Việc xóa workflow trong iPaaS **không tự hủy OAuth app consent** hoặc API key tại vendor cũ.

### 13.3. Handover owner kèm access review của con người

Khi technical owner chuyển bộ phận, rà cả quyền quản trị integration platform, đọc vault, sửa schedule, sửa connection và xem dữ liệu export. Người owner cũ không nên tiếp tục giữ quyền secret-manager nếu không còn nhiệm vụ.

### 13.4. Dual-run cần hạn kết thúc

Trong migration, có thể chạy song song connector cũ/mới. Cần approved window, phạm vi dữ liệu, cách tránh ghi trùng, owner và deadline revoke. Một “đợt chạy thử tạm thời” không có cutoff có thể trở thành hai đường privileged access lâu dài.

## 14. Leaver: decommission tài khoản tích hợp

Leaver của integration xảy ra khi luồng đồng bộ bị dừng, hợp đồng SaaS kết thúc, dữ liệu đã chuyển xong hoặc connector được thay thế.

**Quy trình ngừng tích hợp an toàn:**

1. Xác định owner và sự chấp thuận ngừng kết nối.
2. Lập danh sách source/destination accounts, grants, tokens, queues, webhooks và dependencies.
3. Ngừng job/connector theo kế hoạch, bảo đảm không mất dữ liệu nghiệp vụ cần xử lý.
4. Chặn cấp/refresh token mới ở các authority phù hợp.
5. Thu hồi client secrets, API keys, certificates hoặc delegated authorizations.
6. Gỡ role, group, ACL, resource policy ở **mọi target**.
7. Hủy webhook subscription và xử lý queue/task tồn đọng theo policy.
8. Kiểm tra session/token cũ còn có thể dùng theo profile.
9. Readback hiệu lực quyền, trạng thái account/trust và audit.
10. Chốt VERIFIED_CLOSED khi đủ bằng chứng; nếu chưa thì PARTIAL/PENDING_VERIFICATION.

### 14.1. Dừng lịch chạy không phải revoke

Tắt cron có thể ngừng các request theo kế hoạch, nhưng attacker có API key vẫn có thể gọi API trực tiếp. Xóa cấu hình client khỏi iPaaS có thể không xóa grant của OAuth client tại vendor.

### 14.2. Không xóa dữ liệu kinh doanh vô điều kiện

Việc xóa integration account không đồng nghĩa phải xóa invoice, customer record hoặc transaction đã phát sinh hợp lệ. Xử lý retention, archival và ownership dữ liệu là quyết định riêng.

### 14.3. Token còn hạn sau revoke

Một JWT bearer token có exp 10:00 có thể còn được chấp nhận sau khi role bị gỡ lúc 09:30 nếu API chỉ kiểm tra signature/exp và không đánh giá entitlement mới. Cần token/session controls, introspection/denylist hoặc runtime authorization theo policy và khả năng target.

### 14.4. Không đánh dấu complete khi target không phản hồi

Khi source SaaS revoke thành công nhưng destination SaaS outage, không thể kết luận toàn integration đã hết quyền. Giữ PARTIAL với missing evidence, owner, escalation và biện pháp containment phù hợp.

## 15. JML của nhân viên owner không phải JML của connector

Một integration production có thể tiếp tục hoạt động khi engineer đang quản lý nó chuyển team hoặc nghỉ việc.

| Sự kiện con người | Quyền con người | Hành động integration |
|---|---|---|
| Owner Joiner | Cấp quyền quản trị/vault theo nhiệm vụ | Không tự tạo connector nếu không có business need |
| Owner Mover | Gỡ quyền secret/admin cũ | Reassign owner/reviewer và xem grants |
| Owner Leaver | Disable login và quyền cá nhân theo SLA | Bàn giao owner, kiểm tra secret từng được tải |
| Partner contact Leaver | Rút quyền người đại diện đối tác | Xem token ủy quyền và sponsorship |
| Integration Leaver | Không bắt buộc có nhân viên nghỉ | Decommission accounts và rights |

### 15.1. Nguy cơ dùng personal access token

Một connector được tạo bằng token cá nhân của nhân viên An có thể dừng khi An Leaver, hoặc tiếp tục có quyền nhờ refresh token vẫn còn. Không giả định cả hai đều xử lý đúng JML. Cần inventory delegated connections và chủ động chuyển sang mô hình vendor-supported có owner phù hợp.

### 15.2. Handover không phải gửi secret qua chat

Chuyển ownership ở registry/vault/IdP và role assignment để người kế nhiệm được phép quản trị; không copy client secret hiện tại qua email, ticket hoặc chat. Nếu secret đã từng được phát tán, rotate/revoke theo mức rủi ro.

### 15.3. Rà quyền người quản trị integration riêng

Người có thể sửa workflow hoặc đọc vault đôi khi có quyền hiệu quả cao hơn connector đang chạy. Access recertification phải xét cả **human admin entitlements** và **non-human connector entitlements**, với đối tượng review khác nhau.

## 16. SCIM/IAM provisioning connector là integration account đặc quyền

Một connector dùng SCIM có thể tự động tạo User, cập nhật thuộc tính, thêm/gỡ Group và disable User trong các SaaS. Điều đó giúp Joiner–Mover–Leaver nhưng cũng làm connector thành mục tiêu quan trọng của attacker.

| Capability | Khi có thể cần | Kiểm soát |
|---|---|---|
| users.read | Đối chiếu account | Chỉ target tenant |
| users.create/update | Joiner, Mover | Desired state và field mapping được quản trị |
| groups.read | Đối chiếu membership | Không cần quyền policy admin |
| groups.members.update | Gán/gỡ role qua Group | SoD, group allowlist, readback |
| users.disable | Leaver | Event HR/IAM đáng tin và approval policy |
| clientSecrets.manage | Hiếm khi thuộc provisioning | Tách khỏi connector nếu không cần |
| iam.policy.write | Không phải quyền thông thường của SCIM | Không gộp vào role provisioning |
| audit.log.delete | Không cần | Không cấp |

### 16.1. SCIM không bao quát toàn bộ authorization

SCIM chuẩn hóa User/Group resources và các thao tác theo khả năng của provider. Nó **không mặc định** quản trị tất cả local roles, OAuth token, API keys, browser sessions hoặc cloud service principals. Reconciliation cần hiểu role mapping và các quyền trực tiếp ở SaaS.

### 16.2. Sai thứ tự JML có thể hồi sinh quyền

Một Mover event cũ đến sau Leaver không được làm connector thêm group trở lại. Dùng lifecycle version, effectiveAt, desired-state checks và xử lý idempotent; không tin chỉ thứ tự hàng đợi.

### 16.3. Tách connector admin khỏi connector dữ liệu

Một connector đọc orders không cần quyền user provisioning; một connector provisioning không tự cần export tất cả dữ liệu tài chính. Tách principal và approval giảm blast radius.

### 16.4. Không disable cả integration account khi chỉ gỡ một quyền

Nếu SCIM connector đang phục vụ nhiều target/flow, chỉ một quyền không còn cần có thể được gỡ ở target liên quan mà vẫn giữ connector phục vụ các quyền được chấp thuận khác. Nhưng phải review rủi ro dùng chung và xem khả năng tách account.

## 17. IdP, SSO, SCIM và OAuth trong Integration Account

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Vai trò |
|---|---|
| **IdP** | Xác thực identities và quản lý trust/group trong phạm vi platform |
| **SSO** | Đăng nhập tương tác của con người vào ứng dụng |
| **OAuth Authorization Server** | Cấp access token theo client, user delegation, scopes và policy |
| **SCIM** | Đồng bộ User/Group/membership theo capability provider |
| **SaaS API** | Cung cấp resource access với account/role/ACL riêng |
| **Secrets manager** | Bảo vệ secret, hỗ trợ rotation và access logs |
| **IAM/IGA** | Owner, approvals, lifecycle, recertification, reconciliation |
| **PAM/PIM** | Kiểm soát privileged use/activation khi phù hợp |

### 17.1. SSO không phải phương án mặc định cho connector

Một integration M2M thường nên dùng OAuth client credentials, managed identity, federation hoặc mTLS khi có hỗ trợ. Không tự động hóa browser SSO của nhân viên để lấy session cookie rồi dùng làm service identity.

### 17.2. User-delegated OAuth cần nguồn quyền của user

Nếu app được user cấp consent, scope được phép có thể phụ thuộc role/user consent và trạng thái user. Với Mover/Leaver cần đánh giá lại kết nối và revoke authorization hoặc chuyển owner theo điều kiện vendor, không bỏ qua vì connector vẫn chạy.

### 17.3. SCIM provisioning không phải JIT access

SaaS tạo user bằng SCIM hoặc khi SSO login không tự tạo entitlement có hạn. Quyền của từng user và account của connector đều cần lifecycle riêng.

### 17.4. Provider capabilities là ranh giới thiết kế

Không mặc định vendor hỗ trợ mọi thứ như client credentials, fine-grained scopes, native expiry, token revocation, SCIM role mapping hay nhiều keys overlap. Phải ghi nhận capability và compensating controls dựa trên contract thực tế.

## 18. Trạng thái và sự kiện vòng đời integration

Một state machine giúp không nhầm “đã approve” với “đã hoạt động” hoặc “đã gửi revoke” với “đã ngừng quyền”.

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> APPROVED: Phê duyệt scope và owner
    REQUESTED --> REJECTED: Không đủ điều kiện
    APPROVED --> PROVISIONING: Tạo account/grant/trust
    PROVISIONING --> VERIFYING: Readback
    VERIFYING --> ACTIVE: Target grants hợp lệ
    VERIFYING --> PARTIAL: Chưa đúng desired state
    ACTIVE --> CHANGING: Mover hoặc rotate
    CHANGING --> VERIFYING: Apply thay đổi
    ACTIVE --> RETIRING: Decommission
    RETIRING --> REVOKING: Revoke trust/roles/credentials
    REVOKING --> VERIFYING_REVOKE: Xác minh hết quyền
    VERIFYING_REVOKE --> VERIFIED_CLOSED: Đủ bằng chứng
    VERIFYING_REVOKE --> PARTIAL: Còn quyền hoặc chưa xác minh
    PARTIAL --> VERIFYING: Khắc phục cấp/thay
    PARTIAL --> REVOKING: Khắc phục thu hồi
    REJECTED --> [*]
    VERIFIED_CLOSED --> [*]
~~~

Các trạng thái là mô hình đào tạo. Trong sản phẩm thật có thể dùng nhiều workflow/state machines cho request, credential, target account và grant.

### 18.1. Desired state và observed state

- **Desired state:** Account nên active/retired? Role nào cần giữ? Trust nào được phép?
- **Observed state:** Target thực sự có principal/role/credential nào?
- **Reconciliation:** Tính sai lệch và sửa đúng theo policy, không chỉ tin việc gửi lệnh.

### 18.2. Concurrency và retry

Một job rotation chạy cùng job revoke cần bảo đảm không vô tình tạo key mới sau khi integration RETIRED. Dùng lifecycle version, idempotency key và trạng thái hợp lệ trước khi apply.

### 18.3. Event timestamp và timezone

Với expiration hoặc contract end, cần phân biệt thời điểm có hiệu lực nghiệp vụ với thời điểm message được xử lý. Không kéo dài quyền vì connector nhận event trễ.

## 19. Kiểm toán và monitoring integration account

Audit cần giúp trả lời: **Connector nào dùng principal nào để đọc/ghi dữ liệu nào, do ai duyệt, vào thời điểm nào, và quyền đó còn hợp lệ không?**

Một record **giả lập**:

~~~json
{
  "eventId": "intg-access-2841",
  "integrationId": "intg-sales-accounting-prod",
  "principalId": "destination-client-18",
  "principalType": "INTEGRATION",
  "ownerTeam": "integration-platform",
  "source": "sales-saas/tenant-a",
  "target": "accounting-saas/tenant-a",
  "action": "invoices.create",
  "resourceRef": "accounting/tenant-a/invoices",
  "decision": "PERMIT",
  "policyVersion": "finance-integration-v4",
  "jobRunId": "order-sync-run-20261123-0915",
  "timestamp": "2026-11-23T09:15:10+07:00",
  "correlationId": "order-2841"
}
~~~

Không ghi raw access token, client secret, customer PII không cần thiết hoặc password vào logs. Khi job xử lý dữ liệu tài chính/nhân sự, cần bảo vệ log và dashboard theo data classification.

### 19.1. Ba luồng audit cần nối được

1. **Control plane:** account created, owner changed, role granted/revoked, approval.
2. **Credential/AS:** key issued/rotated/revoked, token issuance, failed client auth.
3. **Data plane:** API call, action/resource, tenant, outcome, request correlation.

Dùng integration ID, principal ID và job run ID giúp phân biệt yêu cầu của từng integration ngay cả khi có shared runtime.

### 19.2. Các chỉ số nên theo dõi

| KPI / Alert | Ý nghĩa |
|---|---|
| Integrations không có current owner | Orphan technical/business accountability |
| API keys quá hạn rotation | Rủi ro credential tồn dư |
| Credential dùng từ runtime bất thường | Có thể bị lộ hoặc sai trust |
| Grants không dùng trong kỳ rà soát | Cơ hội least privilege |
| Nhóm connectors có quyền IAM admin | Bề mặt đặc quyền cao |
| Token issuance sau retirement | Trust/refresh authorization còn mở |
| Số account có nhiều workflows không kiểm soát | Shared identity risk |
| Số webhook replay/invalid signatures | Phát hiện tấn công/hệ thống lỗi |
| Revoke-to-enforced lag | Thời gian quyền tồn dư |
| Target drift và PARTIAL items | Chất lượng reconciliation |
| Secret rotation failures | Nguy cơ outage khi đổi key |
| Cross-tenant denied attempts | Cấu hình sai hoặc lạm dụng |

### 19.3. Không suy không có log là không có quyền

Một connector có thể chỉ chạy cuối tháng; nguồn telemetry có thể thiếu. LastUsedAt=unknown không đủ để xóa ngay production account. Kết hợp owner review, dependency map và target account/grant inventory.

### 19.4. Phân biệt security incident và lỗi dữ liệu

API gọi thành công nhưng đồng bộ sai mapping có thể gây lỗi nghiệp vụ; một request bị từ chối do thiếu quyền có thể là dấu hiệu least privilege hoạt động đúng. Monitoring phải phân loại authorization failures, credential failures, rate limits và data integrity errors để xử lý thích hợp.

## 20. Threat model và những lỗi thường gặp

Một integration account thường có khả năng đọc dữ liệu hàng loạt hoặc ghi thay đổi tự động. Do đó một credential bị chiếm có thể gây tác động lớn ngay cả khi không có giao diện admin.

| Mối đe dọa/lỗi | Kịch bản | Kiểm soát đề xuất |
|---|---|---|
| Secret lộ trong repository | API key bị commit vào Git | Revoke/rotate, secret scanning, least privilege |
| Secret bị log | Connector in Authorization header | Log redaction, giới hạn debug |
| Shared service user | 8 workflows dùng chung một user | Tách identity, dependency inventory |
| Overprivileged OAuth client | Scope admin mọi tenant | Consent review, resource-level policy |
| Wrong audience | Token CRM bị ERP nhận sai | Issuer/audience/profile validation |
| Consent tồn dư | User Leaver nhưng app vẫn có refresh token | Revoke authorization theo provider contract |
| SaaS local role | Gỡ group ở IdP nhưng vẫn có admin | Target readback, reconciliation |
| Webhook spoofing | Receiver xử lý payload chưa kiểm chữ ký | Signature, replay protection, allowlist thích hợp |
| Cross-tenant access | Connector dùng token tenant A ghi B | Tenant binding và object-level authorization |
| Wrong environment | Dev key dùng cho production | Tách principal/trust/secret |
| Retry tạo bản ghi trùng | Network timeout sau POST thành công | Idempotency key, reconciliation dữ liệu |
| Race trong retirement | Rotation job tạo key sau revoke | State machine, lifecycle version |
| CI compromise | Job lạ lấy được workload token | Giới hạn issuer/subject/branch/environment |
| Orphan account | Partner ngừng hợp tác nhưng API key còn | Contract-linked review/deprovision |
| Third-party platform breach | iPaaS lưu nhiều client secrets | Vault/token protection, isolation, revocation plan |
| Privileged SCIM connector | Attacker disable hàng loạt user | Scope, approval, alert, rate/anomaly controls |

### 20.1. HTTP 401, 403, 429 phản ánh vấn đề khác nhau

Nhiều API dùng 401 khi xác thực thất bại, 403 khi authenticated principal không đủ quyền, 429 khi vượt rate limit. Nhưng **ngữ nghĩa chi tiết tùy provider**. Không xử lý 403 bằng cách tự nâng role, cũng không coi mọi 429 là credential hết quyền.

### 20.2. Retry cần giữ bất biến dữ liệu

Một lệnh tạo invoice gửi đi, target đã lưu nhưng response bị mất; retry không có idempotency có thể tạo hai hóa đơn. IAM chỉ đảm bảo quyền, còn connector phải thiết kế idempotency key và dữ liệu correlation theo API contract.

### 20.3. Webhook replay và signature rotation

Receiver nên xác minh chữ ký trên payload theo đúng định dạng provider, giới hạn timestamp window và lưu event ID khi thích hợp để loại replay. Nếu rotating signing secret, phải giới hạn thời gian overlap và xóa key cũ; không coi biết endpoint URL là quyền gửi event hợp lệ.

### 20.4. Shared credential làm mờ audit

Nếu hai workflows dùng cùng account/secret, SaaS có thể chỉ biết principal chung. Phải có thêm integration ID, job run ID, correlation ID và hạn chế quyền, song vẫn cần kế hoạch tách account nếu phù hợp.

## 21. Policy, pseudocode và Java minh họa

### 21.1. Policy mẫu quản trị Integration account

~~~yaml
integrationPolicy:
  integrationId: intg-sales-accounting-prod
  classification: confidential
  owners:
    technical: integration-platform
    business: finance-operations
  source:
    system: sales-saas
    tenant: tenant-a
    allowedActions:
      - orders.read
  destination:
    system: accounting-saas
    tenant: tenant-a
    allowedActions:
      - invoices.create
  authentication:
    preferred: OAUTH_CLIENT_CREDENTIALS
    requireTrustedIssuer: true
    requireAudienceValidation: true
    allowPersonalTokens: false
  security:
    disallowCrossTenantAccess: true
    noSharedAdminPrincipal: true
    requireAuditCorrelation: true
  lifecycle:
    reviewCadenceDays: 90
    onOwnerLeaver: TRANSFER_OWNER_AND_REVIEW_SECRETS
    onIntegrationRetired: REVOKE_ALL_TARGET_GRANTS
    onReadbackFailure: PARTIAL_AND_ESCALATE
~~~

Đây là **schema giả lập cho bài học**, không phải cấu hình dùng trực tiếp ở một IAM, iPaaS, SaaS hoặc policy engine. Những capability và giá trị chính sách phải phù hợp hệ thống thực.

### 21.2. Pseudocode cấp quyền cho integration

~~~text
function provisionIntegration(request):
    integration = trustedRegistry.validate(request.integrationId)
    source = resourceCatalog.get(request.sourceTarget)
    destination = resourceCatalog.get(request.destinationTarget)

    if integration.owner is NONE:
        return BLOCKED_MISSING_OWNER

    if not approvals.validForExactRequest(request):
        return DENY

    if source.tenantId != destination.tenantId
       and not policy.allowsExplicitCrossTenantMapping(request):
        return DENY

    if not policy.isLeastPrivilegeScope(request.sourceActions,
                                         request.destinationActions):
        return DENY

    credentialPlan = credentialService.chooseSupportedAuthentication(
        request, source, destination
    )
    principalMappings = targetProvisioner.createOrReuseIdempotently(
        integration.id, request, credentialPlan
    )

    if not targetVerifier.matchesDesiredPermissions(principalMappings):
        markPartialWithOwnerAndEvidence(integration.id)
        return PARTIAL

    registry.markActive(integration.id)
    return ACTIVE_WITH_AUDIT
~~~

Chỉ là pseudocode, không phải mã production: cần xử lý transaction, network retries, secret handling, approval expiry, access review, TOCTOU, target-specific errors và resource existence.

### 21.3. Pseudocode kiểm tra API thực tế

~~~text
function authorizeIntegrationAction(apiRequest):
    token = tokenValidator.validateWithTrustedConfig(apiRequest.accessToken)
    if token is INVALID:
        return UNAUTHENTICATED

    if token.audience != thisApiExpectedAudience:
        return DENY

    principal = identityRegistry.resolveTrustedPrincipal(token)
    if principal is NONE or principal.status != ACTIVE:
        return DENY

    resource = resourceCatalog.get(apiRequest.resourceId)
    if resource is NONE:
        return NOT_FOUND

    if resource.tenantId != principal.allowedTenantId:
        return DENY

    if not policyEngine.permit(
        principal,
        apiRequest.action,
        resource,
        trustedRuntimeContext()
    ):
        return DENY

    audit.recordWithoutSecrets(principal, apiRequest, resource)
    return PERMIT
~~~

Không tin một HTTP header tự khai principalId, tenantId hoặc integrationId. Backend cần xác thực token theo profile cụ thể và đối chiếu resource/tenant từ nguồn đáng tin.

### 21.4. Java: mô hình scope tối thiểu sau xác thực

~~~java
import java.util.Set;

record IntegrationPrincipal(
        String principalId,
        String integrationId,
        String tenantId,
        boolean active) {}

record IntegrationGrant(
        String principalId,
        String tenantId,
        String resourceId,
        Set<String> actions) {}

final class IntegrationAccessPolicy {
    static boolean permits(
            IntegrationPrincipal subject,
            IntegrationGrant grant,
            String action,
            String resourceId) {

        if (subject == null || grant == null || !subject.active()) {
            return false;
        }

        return subject.principalId().equals(grant.principalId())
                && subject.tenantId().equals(grant.tenantId())
                && resourceId.equals(grant.resourceId())
                && grant.actions() != null
                && grant.actions().contains(action);
    }
}
~~~

Mẫu Java **chỉ minh họa điều kiện scope** sau khi principal đã được xác thực. Nó chưa kiểm tra token issuer/audience/expiry, ownership, resource tenant lấy từ server, SoD, ABAC, session revocation hay thời hạn grant. Không sử dụng như authorization implementation hoàn chỉnh.

## 22. Case study: đồng bộ CRM sang ERP

### 22.1. Bối cảnh nghiệp vụ

Công ty đồng bộ đơn hàng từ CRM SaaS sang ERP. Tác vụ chạy mỗi 15 phút và lưu các hóa đơn ở tenant A.

**Yêu cầu:**

- Không mượn password người vận hành.
- Source principal chỉ đọc orders trong tenant A.
- Destination principal chỉ được tạo invoices trong tenant A.
- Connector không được tạo user, đổi IAM policy hoặc xóa invoices.
- Secret/trust được bảo vệ, rotation có owner.
- API calls có audit integration ID, job run và correlation.
- Có quy trình chuyển vendor, chuyển owner và decommission.

### 22.2. Chuỗi triển khai

~~~mermaid
sequenceDiagram
    participant O as Owners / IAM
    participant V as Secret Vault / Trust
    participant C as CRM-ERP Connector
    participant CRM as CRM API
    participant ERP as ERP API
    participant A as Audit / Reconciliation
    O->>O: Approve source read, target create và tenant A
    O->>V: Provision credential/trust riêng
    C->>V: Lấy proof/token hợp lệ
    C->>CRM: Đọc orders đúng scope
    CRM-->>C: Order data tối thiểu
    C->>ERP: Create invoices với idempotency key
    ERP-->>C: Results + invoice references
    C->>A: Ghi run ID, counts, correlation
    O->>A: Reconcile principal/grants/owner
~~~

### 22.3. Biến cố 1: technical owner Leaver

Engineer phụ trách nghỉ việc nhưng connector vẫn là thành phần quan trọng. IAM gỡ quyền người đó khỏi iPaaS, vault và target admin, chuyển owner, kiểm tra secret từng được export và rotate theo rủi ro. **Không tắt connector đơn thuần vì owner nghỉ.**

### 22.4. Biến cố 2: doanh nghiệp chuyển sang ERP mới

Chạy hai môi trường đích trong cửa sổ migration. IAM phê duyệt role ERP mới, giới hạn dual-run, theo dõi nguy cơ tạo invoice trùng, rồi gỡ role, OAuth consent và credentials ở ERP cũ. Chỉ khi readback thành công mới coi đường cũ đã retire.

### 22.5. Biến cố 3: token còn quyền sau revoke

Account source bị revoke nhưng token còn hạn. Nếu CRM API vẫn chấp nhận token cũ, trạng thái “revoked” trong control plane chưa chứng minh hết data access. Cần target-specific token/session controls và đo effective revocation time.

### 22.6. Biến cố 4: ERP trả 429

Job tăng backoff và retry theo contract; **không xin quyền admin mới** chỉ vì 429. Với POST, dùng idempotency key/correlation để tránh bản ghi trùng khi retry sau timeout.

### 22.7. Tiêu chuẩn hoàn tất thực tế

Tích hợp đạt yêu cầu khi job xử lý đúng dữ liệu **và** principal, scope, tenant, credential, owner, audit và vòng đời được quản trị. Chạy thành công không đủ chứng minh permission đúng; rotation/revoke thành công ở API quản trị không đủ chứng minh mọi token đã bị chặn.

## 23. Kiểm thử Integration account

| Bài kiểm thử | Kỳ vọng |
|---|---|
| Account riêng cho CRM→ERP | Có owner, principal IDs ở hai target |
| API credentials đúng issuer | Chỉ xác thực đúng profile |
| Secret/key không khớp | Từ chối |
| Access token hết hạn | Từ chối |
| Token đúng signature nhưng sai audience | Từ chối |
| Token từ issuer không tin | Từ chối |
| Connector chỉ read, thử source delete | Từ chối |
| Connector chỉ create, thử target IAM admin | Từ chối |
| Tenant A đọc/ghi tenant B | Từ chối |
| Dev credential gọi prod | Từ chối hoặc không được cấp token |
| Account disabled nhưng old token còn | Chặn theo revocation policy |
| SCIM PATCH thành công nhưng role local còn | Chưa VERIFIED |
| Gỡ một grant, baseline grant khác hợp lệ | Không xóa nhầm quyền khác |
| User delegated token khi user Leaver | Re-evaluate/revoke theo provider |
| Technical user bị khóa interactive login | API flow vẫn dùng cơ chế được hỗ trợ |
| Key rotation có two-key overlap | Connector chuyển key đúng cửa sổ |
| Old key usable quá thời hạn rotation | Phát hiện, revoke, escalation |
| Integration owner Leaver | Bàn giao owner, thu hồi human admin rights |
| Integration bị decommission | Revoke trust, roles, secrets và webhook |
| SaaS source thành công, target timeout | PARTIAL, có retry/evidence |
| Retry POST sau lost response | Không tạo bản ghi trùng |
| Webhook signature sai | Từ chối |
| Webhook event ID bị replay | Không xử lý lại trái policy |
| Missing timestamp hoặc quá replay window | Từ chối theo hợp đồng webhook |
| Shared secret xuất hiện trong log | Phát hiện và xử lý incident |
| Không có technical owner | Không tự gọi completed; tạo exception |
| Sai thứ tự Mover sau Leaver | Không tái cấp quyền |
| Target API outage khi readback | PENDING/PARTIAL |
| Local SaaS role vẫn còn sau group removal | Báo residual access |
| Job tự tạo role phụ có hạn dài | Phát hiện secondary grants |
| Provider không có native token revoke | Nêu rõ residual window và containment |
| Đối tác ngừng hợp tác | Thu hồi grants/keys theo hợp đồng và policy |

### 23.1. Kiểm thử hiệu lực ở target, không chỉ trạng thái portal

Không chỉ assert connectionStatus=DISABLED trong iPaaS. Kiểm tra target role, principal, key state và access outcome theo phương pháp an toàn, không gây thay đổi production ngoài scope.

### 23.2. Không làm lộ credential trong test

Sử dụng test principals, fixtures và vault giả lập hoặc môi trường kiểm thử có quyền. Không dump token vào build logs để debug hay gửi secret production vào chat.

## 24. Hiểu lầm thường gặp

**“Integration account luôn là service principal.”** Không: vendor có thể dùng OAuth client, API key gắn user, managed identity hoặc technical user.

**“Client ID là mật khẩu.”** Client ID thường là định danh; việc chứng minh client dựa trên phương thức xác thực phù hợp.

**“Chỉ cần account đăng nhập được là có quyền.”** Authentication khác authorization trên action/resource.

**“SSO đã thành công thì connector có mọi role.”** SSO không thay entitlement/tenant policy của API.

**“SCIM disable user thì mọi integration key cũng chết.”** Không mặc định; cần kiểm tra account/key/token/target cụ thể.

**“OAuth client credentials nghĩa là user đã consent.”** Client credentials thường biểu diễn client identity, khác delegated user authorization.

**“Đổi mật khẩu account là thu hồi toàn bộ role.”** Rotation credential không gỡ entitlement.

**“Token access ngắn hạn thì quyền luôn ngắn hạn.”** Client có thể xin token mới nếu trust và standing grant còn.

**“Dừng scheduler là account đã retire.”** Key/token còn hiệu lực có thể được gọi trực tiếp.

**“Gỡ Group ở IdP là đủ.”** Local roles, direct ACL và sessions có thể còn.

**“Một technical user dùng chung dễ audit hơn.”** Nó thường giảm khả năng phân biệt workflows và tăng blast radius.

**“Client chỉ đọc API nên không có rủi ro.”** Read-all dữ liệu nhạy cảm có thể là đường exfiltration rất lớn.

**“HTTP 200 tức nghiệp vụ và security đã đúng.”** Response thành công không thay data-integrity checks hoặc effective access verification.

**“Owner nghỉ thì phải xóa connector.”** Phải phân biệt lifecycle của người và connector còn phục vụ kinh doanh.

**“Không có log lastUsed nghĩa là account chết.”** Có thể là job hiếm chạy hoặc telemetry thiếu.

## 25. Bài tập tình huống

### A. CRM connector dùng mật khẩu của quản lý bán hàng

Mỗi đêm, connector đọc dữ liệu CRM bằng account người thật. Manager sắp chuyển team.

**Phân tích:** Quyền và tính sẵn sàng phụ thuộc human JML; thiếu separation. Ưu tiên dedicated integration identity; nếu vendor chỉ hỗ trợ user delegation, kiểm tra consent/approval và chuẩn bị cutover theo contract.

### B. Một API key cho ba môi trường

Dev, staging và prod dùng chung key có quyền xuất toàn bộ dữ liệu của prod.

**Phân tích:** Sai boundary. Tách credential/principal, scope, tenant, environment; revoke key chung sau khi migration an toàn và đọc lại hiệu lực.

### C. Webhook nhận sự kiện giả

Một endpoint nhận payload chứa eventId và order data, nhưng không kiểm signature.

**Phân tích:** Attacker có thể gửi sự kiện giả. Kiểm HMAC/certificate theo provider, timestamp, replay window và event de-duplication; không tin mỗi endpoint URL bí mật.

### D. SCIM connector cấp lại user sau Leaver

Event Leaver đến trước, sau đó retry của Mover cũ thêm user vào group.

**Phân tích:** Lỗi event ordering/desired state. Sử dụng lifecycle version, effectiveAt, idempotency và kiểm tra trạng thái nguồn mới nhất trước apply.

### E. Dừng connector nhưng key vẫn active

Tổ chức đã hủy integration với partner nhưng quên API key của partner ở SaaS.

**Phân tích:** Leaver chưa hoàn tất. Cần kiểm tra mọi credential, OAuth authorization, role, webhook và target access; khi thiếu bằng chứng vẫn PARTIAL.

### F. Token còn hạn sau revoke

IAM disable principal lúc 10:00 nhưng resource server tiếp tục chấp nhận JWT đến 11:00.

**Phân tích:** Entitlement validity và token validity khác nhau. Thiết kế online status check, expiry phù hợp hoặc revocation/containment để đáp ứng SLA.

## 26. Checklist thiết kế và vận hành Integration account

1. **Purpose:** integration phục vụ nghiệp vụ cụ thể, có ticket?
2. **Owner:** business/data/technical owner và on-call rõ?
3. **Identity:** principal/account IDs riêng, không dùng human login khi có thể?
4. **Source:** hệ thống và tenant nguồn xác định?
5. **Destination:** hệ thống và tenant đích xác định?
6. **Data:** trường dữ liệu, classification, retention được giới hạn?
7. **Actions:** read/write/deploy/user-manage chỉ khi cần?
8. **Environment:** dev/staging/prod tách identity và secret?
9. **AuthN:** client credentials, federation, mTLS hoặc technical user được hỗ trợ?
10. **Consent:** nếu delegated, user/scope và expiry được quản trị?
11. **Issuer/audience:** Resource Server kiểm tra đúng token profile?
12. **RBAC/ABAC:** role, resource, tenant, environment được enforce?
13. **SoD:** người yêu cầu/approver có thẩm quyền độc lập khi cần?
14. **Vault:** secret được lưu ở nơi an toàn, không hardcode?
15. **Rotation:** có kế hoạch cutover, revoke old secret và readback?
16. **Token:** access/refresh lifetime và revoke behavior được hiểu?
17. **Webhook:** signature và replay protections hoạt động?
18. **Retry:** idempotency và data consistency được bảo đảm?
19. **Provision:** tạo account và grants có audit, tránh trùng?
20. **Joiner:** có reviewBy và connector inventory?
21. **Mover:** gỡ scopes, accounts, trust và role ở target cũ?
22. **Leaver:** revoke keys, tokens, permissions, webhook subscriptions?
23. **Human JML:** owner Leaver không làm orphan credential?
24. **SCIM:** connector admin được hạn chế và kiểm chứng?
25. **SSO/IdP:** không nhầm human login với M2M identity?
26. **Multi-tenant:** request tenant A không thể chạm tenant B?
27. **Secondary grants:** API keys, share links, roles phát sinh được rà?
28. **Audit:** principal, integration/job-run ID, target/action/resource được ghi?
29. **Monitoring:** secret misuse, key rotation lỗi, unauthorized attempts có cảnh báo?
30. **Review:** account và human admins đều được recertification?
31. **Readback:** actual roles/credentials tại source/target khớp desired state?
32. **Partial:** có owner, deadline, containment nếu không verified?
33. **Tests:** token audience, tenant, webhook replay, retry, Mover/Leaver race?
34. **Governance:** có hồ sơ approval, exception, risk và kế hoạch retire?

## 27. Tổng kết

**Integration account** là account hoặc principal chuyên dùng để **kết nối tự động giữa các hệ thống**. Nó thuộc nhóm **non-human account** theo mục đích, nhưng có nhiều biểu hiện kỹ thuật: OAuth client, service principal, managed identity, API key gắn account, technical user hoặc kết nối được user ủy quyền.

Phải luôn phân biệt:

- **Identity/account:** chủ thể và đối tượng quản lý.
- **Credential/trust:** cách connector chứng minh danh tính.
- **Role/entitlement:** hành động và tài nguyên thực sự được phép.
- **Token/session:** cơ chế sử dụng quyền, có vòng đời độc lập.
- **Owner/integration lifecycle:** ai chịu trách nhiệm và lúc nào phải thay đổi/thu hồi.

Trong **Joiner–Mover–Leaver**, account tích hợp cần được **đăng ký với owner, cấp quyền hẹp cho cả nguồn và đích, thay đổi theo nhiệm vụ/tenant/vendor, rồi decommission với readback**. Các hệ thống **IdP, SSO, OAuth, SCIM, RBAC/ABAC, secret manager và audit** đóng các vai trò bổ trợ, không một công cụ nào tự giải quyết trọn vẹn mọi đường truy cập.

**Ghi nhớ:** Một integration chạy thành công chưa chắc được cấp quyền an toàn. Integration account đúng chuẩn phải **có danh tính rõ, scope hẹp, secret được bảo vệ, owner chịu trách nhiệm, quyền đổi được và thu hồi có bằng chứng** để giảm **quyền truy cập tồn dư**.




