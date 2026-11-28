# Policy decision point (PDP): ra quyết định truy cập trong Zero Trust có bằng chứng

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **Policy Decision Point (PDP)** trong kiến trúc **Zero Trust** và phân biệt với **Policy Enforcement Point (PEP)**, **Policy Engine (PE)**, **Policy Administrator (PA)** và các nguồn thông tin chính sách.
2. Xác định các tín hiệu cần thiết để ra quyết định theo **danh tính, thiết bị, tài nguyên, hành động, ngữ cảnh, rủi ro và trạng thái phiên**; đánh giá chất lượng, nguồn gốc và độ mới của tín hiệu.
3. Thiết kế chính sách **least privilege**, **deny by default**, tách tenant, giới hạn object/field/action và điều kiện **step-up authentication** cho truy cập nhạy cảm.
4. Mô tả toàn bộ chuỗi **request → thu thập thuộc tính → đánh giá chính sách → cấp/từ chối/thu hồi → PEP thực thi → ghi bằng chứng và đánh giá lại**.
5. Phát hiện lỗ hổng **PDP bypass**, policy conflict, stale authorization, giả mạo thuộc tính, thiếu kiểm tra ở data plane và fail-open không được phê duyệt.
6. Xây dựng cấu trúc **policy-as-code, versioning, review, rollout, rollback và audit**; thiết kế hoạt động an toàn khi PDP hoặc nguồn tín hiệu bị gián đoạn.
7. Đề xuất **security requirements, negative tests, assurance evidence, metrics và remediation** để chứng minh PDP được thiết kế, triển khai và vận hành hiệu quả.

Trong module **SECURITY_SECURITY_ASSURANCE**, học viên không chỉ học cách bật kiểm soát truy cập mà còn học cách **đánh giá bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật. Chủ đề **Policy decision point** thuộc chương **Zero Trust assurance** là trọng tâm của câu hỏi: **Ai được phép thực hiện hành động nào trên tài nguyên nào, trong hoàn cảnh nào, ai thực sự thực thi quyết định đó và bằng chứng nào chứng minh không có đường đi tắt?**

> **Thông điệp cốt lõi:** PDP tạo ra **quyết định truy cập**; PEP phải **thực thi quyết định** trên từng đường truy cập có liên quan. Một PDP triển khai tốt nhưng API, batch job hoặc database có thể bị truy cập mà không đi qua PEP thì **chưa tạo được bảo đảm Zero Trust**.

## 1. Policy decision point là gì?

**Policy Decision Point (PDP)** là thành phần logic đưa ra hoặc điều phối **quyết định có cho phép một chủ thể truy cập tài nguyên/thực hiện hành động hay không** theo chính sách và tín hiệu có liên quan.

Trong một cách mô tả Zero Trust phổ biến theo **NIST SP 800-207**, PDP là chức năng logic gồm hai thành phần:

- **Policy Engine (PE):** đánh giá tín hiệu/ngữ cảnh và chính sách để xác định quyết định cấp, từ chối hoặc thu hồi quyền truy cập.
- **Policy Administrator (PA):** điều phối việc **thiết lập hoặc kết thúc đường giao tiếp** và cung cấp thông tin điều khiển phù hợp tới **PEP** theo quyết định. Chi tiết token/session/credential phụ thuộc triển khai.

**Policy Enforcement Point (PEP)** chịu trách nhiệm **cho phép, giám sát hoặc chặn luồng thực tế** giữa chủ thể và tài nguyên. Một thiết kế khác có thể dùng thuật ngữ PDP để chỉ riêng **dịch vụ đánh giá policy**, còn PA là thành phần orchestration tách riêng; khi đánh giá phải **ghi rõ mô hình được dùng**, không ép mọi sản phẩm vào cùng một sơ đồ.

### 1.1. Các thành phần trong hệ sinh thái

| Thành phần | Trả lời câu hỏi | Trách nhiệm điển hình |
|---|---|---|
| **Subject / principal** | Ai đang yêu cầu? | Người dùng, workload, device hoặc service identity |
| **Resource** | Đối tượng nào bị truy cập? | API, hồ sơ, object, file, database record, secret, chức năng |
| **Action** | Muốn làm gì? | Read, export, create, update, delete, approve, decrypt, administer |
| **PE / policy engine** | Theo rule và context, quyết định gì? | Đánh giá, kết hợp chính sách, lý do/obligations |
| **PA / policy administrator** | Quyết định được áp vào phiên/kết nối thế nào? | Điều phối establishment/termination, session/token theo thiết kế |
| **PDP** | Chức năng quyết định truy cập tổng thể | PE và có thể gồm PA trong mô hình NIST |
| **PEP** | Chặn/cho phép việc thực hiện thực tế ở đâu? | Gateway, proxy, sidecar, service middleware, DB guard |
| **Policy Information Point (PIP)** | Dữ liệu thuộc tính/ngữ cảnh đến từ đâu? | Directory, device posture, risk engine, asset/tenant metadata |
| **Identity Provider (IdP)** | Chủ thể đã được xác thực ra sao? | Identity proof/authentication, claims, session, credentials |
| **Policy repository** | Rule đang có hiệu lực là phiên bản nào? | Policy-as-code, approval, release và provenance |
| **Telemetry / audit** | Đã quyết định và thực thi thế nào? | Decision logs, enforcement events, anomalies và evidence |

**PIP** là một thuật ngữ quen thuộc trong các kiến trúc authorization, không phải một thành phần bắt buộc phải có tên “PIP” trong mọi bản triển khai Zero Trust. Nguồn tín hiệu có thể phân tán; điều quan trọng là **tính đáng tin và quyền sở hữu** của từng tín hiệu.

### 1.2. Authentication không thay authorization

Một request có:

- **Authentication (AuthN):** Xác minh thực thể đứng sau danh tính hoặc credential.
- **Authorization (AuthZ):** Quyết định thực thể đó **có được thực hiện hành động cụ thể trên tài nguyên cụ thể** không.
- **Policy evaluation:** Đánh giá AuthZ theo thuộc tính, rule và trạng thái thực tế.
- **Enforcement:** Chặn/cho phép thao tác bằng PEP và các giới hạn bổ sung.

MFA thành công hoặc thiết bị “managed” **không tự động cho phép** xuất dữ liệu của tenant khác. Tương tự, kết nối từ mạng nội bộ **không tạo quyền mặc định**. **Zero Trust** yêu cầu xác minh và áp chính sách dựa vào từng truy cập có liên quan, hạn chế đặc quyền theo thực tế và theo dõi biến động ngữ cảnh.

### 1.3. PDP là thành phần logic, không nhất thiết một máy chủ

PDP có thể được triển khai:

- Tập trung dưới dạng dịch vụ quyết định chung.
- Trong mỗi service/cell bằng policy engine cục bộ được phân phối policy có kiểm soát.
- Theo mô hình hybrid: decision service trung tâm cho hành động nhạy cảm, policy snapshot cho một số đường đọc có rủi ro thấp.

Điều quyết định không phải vị trí đặt code, mà là **một quyết định nhất quán, kiểm soát phiên bản, đúng thuộc tính và được enforce ở mọi entry point được xác định**.

## 2. Kiến trúc PDP–PEP và luồng quyết định

### 2.1. Sơ đồ khái niệm

~~~mermaid
flowchart TD
    S["Subject: user / workload"] --> PEP["PEP: gateway, service, proxy"]
    PEP -->|"Decision request"| PA["PDP: Policy Administrator / orchestration"]
    PA --> PE["Policy Engine"]
    PE --> PR["Approved policy repository"]
    PE --> PIP["Trusted context sources / PIP"]
    PIP --> IDP["IdP and identity state"]
    PIP --> DEV["Device posture / risk signals"]
    PIP --> META["Resource / tenant metadata"]
    PE -->|"Decision + reason + constraints"| PA
    PA -->|"Grant/deny/revoke/session control"| PEP
    PEP -->|"Enforced access if permitted"| R["Protected resource"]
    PA --> AUD["Decision audit"]
    PEP --> AUD
    AUD --> MON["Security monitoring + assurance"]
~~~

Sơ đồ giản lược. Một hệ thống có thể để PEP gọi trực tiếp PE, PA quản lý mối liên hệ riêng hoặc policy được xử lý tại edge/service. Chức năng PE/PA có thể hợp nhất. **Không nên suy từ vị trí node rằng PA luôn đứng trước PE trong mọi request hoặc mọi quyết định đều tạo token mới.**

### 2.2. Luồng truy cập ví dụ: xuất hóa đơn

Giả sử nền tảng **InvoiceHub** phục vụ nhiều doanh nghiệp (tenants). Nhân viên tài chính của tenant A muốn xuất file hóa đơn chứa thông tin khách hàng.

1. **Request:** Client gọi `POST /tenants/A/invoices/export` với session/token hợp lệ.
2. **PEP xác thực ngữ cảnh:** Gateway xác thực credential, service xác minh tenant ID trong path và target resource; không tin một header `X-Tenant-ID` do client tự khai.
3. **PDP thu thập tín hiệu:** Subject role, membership tenant, quyền export, mức assurance xác thực, device posture có căn cứ, mức nhạy cảm dataset, thời gian và risk signals.
4. **PE đánh giá policy:** Quyền `invoice.export` có được phép với tập hóa đơn và tenant A không? Có cần step-up hay approval không?
5. **PA/PEP xử lý:** PEP từ chối, yêu cầu hoàn thành bước xác minh bổ sung hoặc cho phép trong giới hạn được quyết định.
6. **Thực thi ở data plane:** Export worker dùng scope tenant A từ context đã xác thực; không chỉ dựa vào ID request tùy ý.
7. **Ghi bằng chứng:** Log decision ID, policy version, subject/resource/action references, thời điểm và outcome; log thực thi file/row scope.
8. **Đánh giá lại:** Nếu quyền export bị thu hồi trước khi job bắt đầu hoặc khi cần kiểm tra lại, workflow phải tái xác minh theo chính sách. Quyết định ban đầu không đương nhiên cấp quyền vĩnh viễn.

### 2.3. Mỗi quyết định có dữ liệu đầu vào và điều kiện

Một mô hình logic:

```text
Decision = Evaluate(
    verifiedSubject,
    normalizedAction,
    authoritativeResource,
    trustedContext,
    effectivePolicyVersion,
    decisionTime
)

Decision -> {
    effect,
    obligations,
    scopeConstraints,
    expiryOrReevaluationTrigger,
    policyVersion,
    reasonCode,
    decisionId
}
```

Các giá trị `effect`, `obligations` hoặc `reasonCode` chỉ là mẫu chung; cách biểu diễn thực tế phụ thuộc policy engine. Một hệ thống có thể mô hình hóa **STEP_UP** thành một quyết định cần thử thách bổ sung bên ngoài ALLOW/DENY, không phải mọi PDP đều có mã trạng thái step-up.

## 3. Tín hiệu đầu vào: identity, context và nguồn đáng tin

**Chất lượng của PDP phụ thuộc chất lượng dữ liệu nó sử dụng.** Một rule rất chặt vẫn có thể cho phép sai nếu tenant, thiết bị hoặc quyền của người dùng được lấy từ nguồn giả mạo hoặc lỗi thời.

### 3.1. Các nhóm thuộc tính

| Nhóm thuộc tính | Ví dụ | Nguồn nên xác minh |
|---|---|---|
| **Subject** | Subject ID, service identity, nhóm, role, tenant membership | IdP/directory hoặc identity registry đáng tin |
| **Authentication state** | MFA/step-up state, phương thức, auth time | Session/token đã xác minh, IdP authoritative |
| **Device** | Managed status, compliance, health, certificate binding | Device management/attestation đáng tin |
| **Resource** | Resource ID, owner tenant, classification, sensitivity | Resource service/data catalog có thẩm quyền |
| **Action** | `read`, `export`, `approve`, `delete` | Định nghĩa API/operation chuẩn hóa phía server |
| **Session** | Age, assurance, revocation status, bound client | Token/session authority |
| **Environment** | Time, location, network, workload identity | Nguồn được đánh giá, không tin client tự khai |
| **Risk** | Anomaly, threat intelligence, transaction risk | Risk engine/telemetry có provenance |
| **Policy** | Policy version, effective time, rule priority | Approved policy repository và release process |
| **Business state** | Approved invoice, closed payout, active hold | Source-of-truth nghiệp vụ |

Location/network là **tín hiệu bổ sung**, không phải chứng cứ một chủ thể đã được tin cậy. IP có thể thay đổi, proxy có thể che nguồn và context có thể bị spoof. Với workload, cần xác thực **machine identity** thay vì chỉ coi một IP là service identity.

### 3.2. Tín hiệu phải có provenance và freshness

Với mỗi thuộc tính quan trọng, cần biết:

- **Source of truth:** Hệ thống nào phát và ai quản lý?
- **Integrity/authenticity:** Có kiểm chứng chữ ký, transport, session hoặc attestation phù hợp không?
- **Subject/resource binding:** Thuộc tính áp cho đúng identity/resource hay bị đổi chéo?
- **Timestamp/freshness:** Được quan sát khi nào; còn đủ mới cho hành động không?
- **Scope:** Tenant, environment, device và session nào?
- **Failure state:** Nếu nguồn timeout hoặc không đồng bộ, dùng trạng thái nào?
- **Revocation:** Khi role bị thu hồi hoặc thiết bị không compliant, PEP nhận cập nhật ra sao?

Ví dụ `device_compliant=true` do client tự gửi không phải bằng chứng posture đáng tin. PDP phải nhận dữ liệu từ một nguồn device-trust được xác minh hoặc liên kết với chứng thực phù hợp, đồng thời tôn trọng **thời gian hiệu lực và điều kiện thay đổi**.

### 3.3. Tín hiệu thiếu, sai hoặc không xác định

Phân biệt:

| Tình huống | Ý nghĩa | Nguyên tắc quyết định |
|---|---|---|
| **Verified true** | Thuộc tính được xác nhận đúng scope | Có thể dùng trong policy |
| **Verified false** | Nguồn đáng tin xác nhận điều kiện không đạt | Không cho phép theo rule tương ứng |
| **Unknown** | Không có đủ thông tin xác minh | Không tự suy thành true |
| **Stale** | Tín hiệu có thể đã hết thời gian tin cậy | Cần refresh/chặn theo policy |
| **Conflicting** | Hai nguồn cho kết quả khác nhau | Áp ưu tiên nguồn/điều kiện được thiết kế, escalations |
| **Unavailable** | Nguồn lỗi hoặc timeout | Degraded behavior theo mức rủi ro, không silent allow |

Điểm quan trọng: **Không quan sát thấy rủi ro không đồng nghĩa chắc chắn không có rủi ro.** Nếu risk engine không trả về, không nên gán `risk=low` chỉ để request đi tiếp.

### 3.4. Chuẩn hóa tài nguyên và hành động

Policy phải đánh giá **đúng object**:

- Mã tenant trong URL có khớp tenant sở hữu object trong database không?
- Một invoice có được share hợp lệ cho nhiều người hoặc nhiều tổ chức không?
- Hành động `download` thực chất truy cập những file và trường dữ liệu nào?
- Khi resource được đổi owner hoặc trạng thái, quyết định cũ có còn đúng?
- Một job export tạo bất đồng bộ có dùng lại quyền đã hết hạn không?

**BOLA/IDOR** có thể xảy ra khi gateway đã cho `invoice.read` nhưng service không kiểm tra invoice ID có thuộc đúng chủ thể/tenant. PDP phải dựa trên **resource metadata authoritative** và PEP phải enforce ở cấp object/record thích hợp.

## 4. Chính sách truy cập: RBAC, ABAC, ReBAC và deny by default

### 4.1. RBAC: quyền theo vai trò

**Role-Based Access Control (RBAC)** gắn quyền với vai trò. Ví dụ:

- `invoice_viewer` được xem hóa đơn của tenant được phân quyền.
- `invoice_exporter` được yêu cầu export trong scope được duyệt.
- `tenant_admin` quản lý người dùng của tenant mình.

RBAC dễ đọc nhưng **vai trò không đủ để quyết định đối tượng cụ thể**. `invoice_viewer` của tenant A không được đọc mọi hóa đơn của tenant B.

### 4.2. ABAC: quyền theo thuộc tính

**Attribute-Based Access Control (ABAC)** đánh giá thuộc tính của subject, resource, action và environment:

```text
permit invoice.export when:
    subject.role includes "invoice_exporter"
    AND subject.tenantId == resource.tenantId
    AND resource.classification in approvedExportClasses
    AND session.assurance >= policy.requiredAssurance
    AND device.posture == "verified-compliant"
    AND resource.exportHold == false
```

Đây là **pseudocode**, không phải policy engine cụ thể. Các thuộc tính `classification` và `exportHold` phải được lấy từ nguồn có thẩm quyền. Nếu người dùng có thể tự đặt `resource.tenantId`, điều kiện equality không tạo bảo vệ thực.

### 4.3. ReBAC: quyền theo quan hệ

**Relationship-Based Access Control (ReBAC)** xét quan hệ giữa các thực thể:

- User U là member của tenant T.
- Invoice I thuộc tenant T.
- User U được delegated quyền đọc invoice I.
- Team X là owner của document D.

ReBAC phù hợp với sharing/delegation, nhưng cần kiểm tra **đồ thị quan hệ, nguồn cập nhật, thời điểm thu hồi và phạm vi ủy quyền**. Một quan hệ đã hết hạn hoặc sai tenant không nên tiếp tục cấp quyền vì cache chưa đồng bộ.

### 4.4. Kết hợp thay vì chọn một mô hình duy nhất

Một hệ thống thực tế thường kết hợp:

1. **RBAC** quyết định tập hành động sơ bộ.
2. **ABAC** giới hạn theo tenant, classification, device/risk và trạng thái nghiệp vụ.
3. **ReBAC** xác minh ownership, membership hoặc delegation.
4. **Business invariants** ngăn hành vi trái quy trình dù user có role rộng.

Ví dụ: một người có role finance approver vẫn **không được tự phê duyệt khoản thanh toán do chính mình tạo** nếu chính sách separation of duties yêu cầu hai người khác nhau.

### 4.5. Implicit deny và thứ tự ưu tiên

**Default deny:** Không có policy cho phép hợp lệ thì không được truy cập. Các trạng thái cần định nghĩa rõ:

- **PERMIT / ALLOW:** Cho phép với scope và constraints đã xác minh.
- **DENY:** Từ chối theo rule.
- **NOT_APPLICABLE:** Rule cụ thể không áp dụng; không mặc định là PERMIT.
- **INDETERMINATE / ERROR:** Không thể đánh giá đáng tin; không mặc định là PERMIT.
- **CHALLENGE / STEP_UP:** Workflow cần xác thực bổ sung, nếu policy engine có biểu diễn này.

Nếu có nhiều rule cùng áp dụng, phải chọn và chứng minh **combining algorithm**: ví dụ deny-overrides hoặc thứ tự ưu tiên đã được phê duyệt. Không để hai service tự suy diễn khác nhau khi cùng một policy cho cả permit và deny.

### 4.6. Không dùng một quyết định quá rộng

Decision `ALLOW invoice.read` **không tự cấp** quyền:

- `invoice.export`.
- Đọc toàn bộ bảng hóa đơn.
- Đọc thông tin người nhận hoặc trường nhạy cảm khác.
- Gửi dữ liệu sang đối tác.
- Đọc hóa đơn sau khi tenant membership bị thu hồi.

Policy nên ràng buộc **action, resource, tenant, purpose, fields và thời gian** theo nhu cầu, nhưng vẫn cân bằng chi phí vận hành và khả năng kiểm chứng.

## 5. Chu trình quyết định và đánh giá lại

### 5.1. Quyết định ở thời điểm bắt đầu chưa đủ cho mọi phiên

Zero Trust nhấn mạnh khả năng **liên tục đánh giá mức tin cậy trong giới hạn phù hợp**. Không nhất thiết mỗi byte dữ liệu phải gọi PDP qua mạng, nhưng cần xác định:

- Decision có hiệu lực cho **một request**, một connection hay một session?
- Có cấp **scoped capability/token** với thời hạn?
- Tín hiệu nào thay đổi bắt buộc reevaluate: role, risk, device, resource classification, incident?
- Nếu session bị thu hồi, PEP biết và chặn khi nào?
- Streaming, long-running export hoặc batch job sẽ tái xác minh ở giai đoạn nào?
- Khi policy version được thay, các decision cũ còn được chấp nhận theo quy tắc nào?

**Continuous evaluation** là thiết kế **điểm ra quyết định, trigger và giới hạn thời gian** có kiểm chứng, không phải câu khẩu hiệu “kiểm tra liên tục”.

### 5.2. Các trigger phổ biến

| Trigger | Rủi ro | Hành động PDP/PEP cần xét |
|---|---|---|
| Người dùng bị thu hồi role | Quyền cũ vẫn còn hiệu lực | Invalidate cache, reevaluate và terminate session/operation khi cần |
| Thiết bị mất compliance | Workload không còn đáng tin | Chặn hành động nhạy cảm hoặc yêu cầu remediation |
| MFA/session hết thời hạn assurance | Assurance cho thao tác mới không đủ | Yêu cầu step-up hoặc deny |
| Resource chuyển tenant/owner | Decision cũ trỏ sai phạm vi | Đánh giá lại ownership và action |
| Risk score tăng | Tín hiệu tài khoản bị chiếm | Step-up, hạn chế hoặc revoke theo policy |
| Chính sách mới được phát hành | Rule và obligations thay đổi | Kết thúc hiệu lực policy cũ theo rollout plan |
| Incident/compromise | Chủ thể hoặc secret không đáng tin | Containment, deny/revoke, theo dõi |
| Export job bắt đầu sau thời gian chờ | Quyền khi submit có thể đã thay đổi | Recheck trước khi đọc và giao file |

### 5.3. Step-up là hành động có phạm vi

Với thao tác rủi ro cao, policy có thể yêu cầu **xác thực bổ sung**:

- Người đọc báo cáo thông thường không cần bước thêm nếu đủ điều kiện.
- Khi tải dữ liệu cá nhân hàng loạt, yêu cầu xác thực mạnh/fresh hơn.
- Khi thay người nhận thanh toán, cần xác minh lại và kiểm tra business authorization.

Sau step-up phải **gắn kết quả với đúng subject, action, resource/scope và thời điểm**. Không coi MFA vừa hoàn thành cho một chức năng là tấm vé mở mọi thao tác privileged.

### 5.4. Revocation và caching

Caching giúp giảm latency nhưng có thể giữ quyền cũ. Một quyết định cache nên được ràng buộc theo:

```text
cacheKey = (
  verifiedPrincipalId,
  normalizedAction,
  authoritativeResourceId,
  tenantId,
  relevantContextFingerprint,
  effectivePolicyVersion,
  subjectPrivilegeEpoch
)

cacheEntry = {
  decision: "PERMIT" or "DENY",
  expiresAt: policyBoundedExpiry,
  sourceFreshness: checkedAt,
  constraints: approvedScope
}
```

Đây là mô hình minh họa, **không phải cache key an toàn tuyệt đối**. Nếu membership hoặc resource ownership thay đổi mà không làm thay đổi cache key, PEP vẫn có thể dùng quyết định sai. Cần có **TTL phù hợp, invalidation/revocation, version/epoch, negative tests và monitoring**. Với hành động nhạy cảm nên giới hạn hoặc tránh permit caching nếu không chứng minh được thời gian thu hồi chấp nhận được.

## 6. PEP: quyết định tốt không có nghĩa enforce đầy đủ

### 6.1. Complete mediation

**Complete mediation** yêu cầu mọi đường truy cập thuộc phạm vi bảo vệ phải đi qua kiểm tra quyền phù hợp. Có thể có nhiều PEP:

- API gateway kiểm tra request đầu vào và policy tổng quát.
- Application service kiểm tra **object-level/tenant authorization**.
- Database layer hoặc row-level security nếu được thiết kế hỗ trợ.
- Worker/queue consumer kiểm tra scope của job và resource.
- Object storage download gateway hoặc signed URL issuance.
- Admin/debug interface và internal API.

Chỉ đặt một PEP ở gateway **không đủ** nếu service có endpoint trực tiếp nội bộ, cron job, message handler, service account có quyền database rộng hoặc một presigned URL bỏ qua kiểm tra người tải sau khi phát hành.

### 6.2. Bypass và confused deputy

**Confused deputy** xảy ra khi một service có đặc quyền cao bị lợi dụng để hành động thay cho người dùng không được phép.

Ví dụ:

1. Người dùng B chỉ có quyền trong tenant B.
2. Service exporter có quyền đọc mọi tenant.
3. API kiểm tra user “được export” nhưng không gắn tenant với dataset.
4. Người dùng B gửi invoice IDs của tenant A.
5. Service exporter đọc dữ liệu tenant A bằng quyền dịch vụ.

Vì thế PEP phải enforce **ủy quyền của người yêu cầu đối với resource cụ thể**, không chỉ kiểm tra quyền kỹ thuật của exporter. Workload identity chỉ chứng minh service **là ai**, không chứng minh yêu cầu nghiệp vụ **được phép**.

### 6.3. TOCTOU: kiểm tra rồi dữ liệu đổi

**Time of Check to Time of Use (TOCTOU)** là khoảng cách giữa lúc PDP quyết định và lúc hành động thực thi. Trong thời gian đó:

- Role bị thu hồi.
- Invoice đổi owner.
- Export job chạy sau một giờ.
- Trạng thái duyệt thanh toán thay đổi.
- Tenant bị suspended hoặc hold.

Biện pháp có thể gồm:

- Reevaluate trước thao tác nhạy cảm.
- Kiểm tra invariant trong cùng transaction ở tầng dữ liệu.
- Dùng optimistic version checks hoặc database constraints.
- Gắn decision với target và context cụ thể.
- Theo dõi expiration và cancel/terminate job khi điều kiện không còn đúng.

### 6.4. Obligations cần được enforce

Một PDP có thể trả về điều kiện thực thi:

- Chỉ đọc fields đã cho phép.
- Chỉ xuất tối đa số record hoặc scope định trước.
- Redact thông tin nhạy cảm.
- Bắt buộc ghi audit event.
- Yêu cầu step-up hoặc phê duyệt bổ sung.
- Giới hạn phiên và expiry.

Nếu PEP **không thể thực hiện obligation bắt buộc**, không được âm thầm biến decision thành unrestricted ALLOW. Hợp đồng PDP–PEP phải xác định **cách mô tả, kiểm tra và xử lý unsupported obligations**.

## 7. Threat model cho PDP và đường quyết định

### 7.1. Các kịch bản tấn công

| Kịch bản | Nguyên nhân | Kiểm soát cần có |
|---|---|---|
| **Attribute spoofing** | Client tự gán role, tenant, device posture | Source authentication, server-side resolution |
| **Policy bypass** | Truy cập API/DB trực tiếp không qua PEP | Complete mediation, network/service access limits |
| **Policy tampering** | Attacker sửa rule trong repository hoặc control plane | SoD, signed/approved rollout, integrity checks |
| **Over-privileged PDP** | Decision service hoặc PEP có quyền quản trị toàn hệ thống | Least privilege và tách control/data plane |
| **Stale permit** | Cache không bị invalidated khi thu hồi quyền | Bounded TTL, epochs, revocation events |
| **Cross-tenant authorization** | Resource tenant được lấy từ client | Authoritative ownership, negative tests |
| **Confused deputy** | Worker đặc quyền rộng làm theo user request | Propagated identity/context và resource authorization |
| **Fail-open** | PDP/PIP timeout dẫn đến mặc định allow | Explicit safe fallback và deny sensitive actions |
| **Policy conflict** | Rule trái nhau, precedence không xác định | Approved combining semantics và conflict tests |
| **Decision replay** | Token/decision dùng lại cho object/action khác | Binding, expiry, audience và nonce khi phù hợp |
| **Log tampering** | Admin xóa audit của quyết định trái phép | Protected logging, separation of duties |
| **Denial of service PDP** | Lượng decision requests lớn hoặc PIP chậm | Rate limit, isolation, capacity, bounded evaluation |
| **Wrong resource mapping** | IDOR, tenant mismatch, stale metadata | Canonical resource ID và ownership validation |
| **Insecure emergency mode** | Break-glass không giới hạn hoặc không audit | Time-bound JIT access, approval và review |

### 7.2. Threat model cần liệt kê mọi trust boundary

~~~mermaid
flowchart LR
    C["Untrusted client"] --> GW["Gateway PEP"]
    GW --> APP["Application PEP"]
    APP --> DB[("Data store")]
    APP --> WRK["Export worker"]
    WRK --> OBJ[("Export storage")]
    GW --> PDP["PDP / policy service"]
    APP --> PDP
    PDP --> DIR["Directory / IdP"]
    PDP --> CTX["Device + risk signals"]
    PDP --> POL["Policy repository"]
    ADM["Privileged administrator"] --> POL
    WRK -. "Authorized job context" .-> PDP
~~~

Với từng đường, xác định: nguồn dữ liệu, danh tính và authentication của kết nối, quyền sửa metadata, quyền thay policy, ngữ cảnh authorization, khả năng bỏ qua PEP và bằng chứng có sẵn.

### 7.3. Đánh giá thiệt hại khi chính PDP bị compromise

Nếu attacker kiểm soát PDP, một quyết định giả có thể mở đường cho nhiều tài nguyên. Giảm blast radius bằng:

- Tách quyền quản trị policy và vận hành PEP.
- Bảo vệ control-plane identities, deployment và policy artifacts.
- Tách policy theo môi trường/cell/tenant khi phù hợp.
- Bảo vệ logs độc lập khỏi tài khoản quản trị PDP.
- Giới hạn scope của grants và tokens; PEP vẫn kiểm tra điều kiện cơ bản.
- Có plan rollback và thu hồi policy version/token bị ảnh hưởng.
- Theo dõi anomaly về permit rates, deny overrides và policy changes.

Không phụ thuộc hoàn toàn vào một PDP toàn quyền mà không phân tích **common-mode failure** và phạm vi rủi ro.

## 8. Chính sách phải được thiết kế thành yêu cầu kiểm thử được

### 8.1. Ví dụ tập yêu cầu cho InvoiceHub

| ID | Mục tiêu | Tiêu chí chấp nhận |
|---|---|---|
| **PDP-01** | Không có quyền mặc định | Không có permit rule hợp lệ thì DENY |
| **PDP-02** | Cô lập tenant | Subject tenant B không export invoice tenant A |
| **PDP-03** | Resource binding đáng tin | Tenant/owner lấy từ source-of-truth, không tin client field |
| **PDP-04** | Role và action scope | Quyền read không tự mở export/delete |
| **PDP-05** | Xác thực mạnh khi cần | Sensitive export thiếu fresh assurance bị chặn/challenge |
| **PDP-06** | Chính sách có version | Mỗi decision truy được effective policy version |
| **PDP-07** | Thu hồi quyền có hiệu lực | Permit cache/session hết hiệu lực trong giới hạn phê duyệt |
| **PDP-08** | Safe failure | PDP/PIP unavailable không dẫn đến permit không xác minh |
| **PDP-09** | Complete mediation | Gateway, service, worker và export delivery đều có enforcement |
| **PDP-10** | Obligations được thực thi | Unsupported mandatory obligation không tạo allow không giới hạn |
| **PDP-11** | Bằng chứng quyết định | Decision ID có outcome, reason, subject/resource/action ref và thời điểm |
| **PDP-12** | Control plane được bảo vệ | Policy change có approval, audit, negative access test và rollback |

Yêu cầu là **mẫu giáo dục**, không tự động tương đương tuân thủ bất kỳ tiêu chuẩn cụ thể. Mọi tiêu chí phải được bổ sung scope, owner, thời gian, test method và evidence.

### 8.2. Traceability: rủi ro tới quyết định có bằng chứng

~~~mermaid
flowchart TD
    OBJ["Mục tiêu bảo vệ dữ liệu và tenant"] --> RISK["Risk scenario:<br/>cross-tenant export"]
    RISK --> REQ["Authorization requirement PDP-02"]
    REQ --> RULE["Approved policy / version"]
    RULE --> PE["Policy Engine decision"]
    PE --> PEP["PEP enforcement"]
    PEP --> TEST["Cross-tenant negative test"]
    TEST --> EV["Decision + execution evidence"]
    EV --> CL["Scoped assurance claim"]
    EV --> GAP["Finding / remediation / retest"]
    GAP --> RULE
~~~

### 8.3. Phân loại control

- **Preventive:** deny-by-default, object-level authorization, policy integrity, token scope.
- **Detective:** decision monitoring, abnormal permits, unverified attributes, bypass detection.
- **Corrective:** revoke, terminate sessions, rollback policy, quarantine workload, fix PEP.
- **Governance:** policy owner, change approval, exceptions, risk assessment và periodic review.

Một control trên giấy **không phải bằng chứng operating effectiveness**. Kiểm thử phải chỉ ra request thực tế đến PEP và bị chặn hoặc cho phép **đúng phạm vi**.

## 9. Policy-as-code và cấu hình mẫu

### 9.1. Vì sao cần version và review?

Policy có thể trở thành **mã thực thi có quyền cấp truy cập**. Một thay đổi nhỏ, chẳng hạn bỏ điều kiện `resource.tenantId == subject.tenantId`, có thể gây lộ dữ liệu của nhiều doanh nghiệp.

Policy-as-code giúp:

- Xác định một phiên bản rule **có thể review và kiểm thử**.
- Phân biệt cấu hình **được phê duyệt** với cấu hình đang có hiệu lực.
- Áp quality gates: static analysis, policy unit tests, negative tests và simulation.
- Phân phối/rollback theo change ID, artifact digest và môi trường.
- Phát hiện **policy drift** giữa những PDP hoặc PEP.
- Lưu **lý do quyết định**, phiên bản và phạm vi để phục vụ audit.

Policy-as-code không tự giải quyết correctness. Nếu policy tham chiếu thuộc tính thiếu tin cậy hoặc **PEP không thực thi**, hệ thống vẫn có thể bị bypass.

### 9.2. Ví dụ hồ sơ chính sách YAML

Mẫu sau là **hồ sơ logic minh họa**, không phải cú pháp chính thức của một sản phẩm authorization. Những tham chiếu cần gắn với thư viện/quy trình thực tế được phê duyệt.

~~~yaml
zeroTrustPolicy:
  id: ZT-INVOICE-EXPORT-PDP-01
  version: "3.2"
  status: approved-example
  systemId: INVOICEHUB-PRODUCTION

  ownership:
    businessOwnerRole: Invoice Data Owner
    policyOwnerRole: Access Governance Owner
    implementationOwnerRole: Platform Authorization Team
    riskOwnerRole: InvoiceHub Risk Owner

  protectedOperation:
    action: invoice.export
    resourceType: invoice-set
    dataClass: restricted
    enforcementPoints:
      - invoice-api
      - export-worker
      - export-download-gateway

  trustedSources:
    principal: verified-idp-and-membership-registry
    resourceOwner: invoice-database-source-of-truth
    authnContext: verified-session-authority
    devicePosture: approved-device-trust-service
    risk: approved-risk-signals

  decision:
    defaultEffect: DENY
    requiredConditions:
      - authenticated-subject
      - active-tenant-membership
      - export-role-granted
      - subject-tenant-matches-resource-tenant
      - resource-not-under-export-hold
      - session-assurance-fresh-enough
    onMissingCriticalAttribute: DENY_OR_CHALLENGE_BY_POLICY
    onPdpUnavailable: DENY_SENSITIVE_OPERATION
    combiningRuleReference: APPROVED-DENY-OVERRIDES-POLICY

  constraints:
    requireServerSideResourceResolution: true
    maximumExportScopeReference: DATA-EXPORT-LIMITS
    requiredAuditEvent: INVOICE-EXPORT-DECISION
    permittedFieldSetReference: EXPORT-FIELD-WHITELIST

  session:
    decisionLifetimeReference: SENSITIVE-EXPORT-TTL
    reevaluateBeforeExecution: true
    reevaluateBeforeDelivery: true
    revocationSignalReference: ROLE-AND-SESSION-REVOCATION

  assurance:
    requiredTests:
      - TEST-CROSS-TENANT-EXPORT-DENIED
      - TEST-REQUEST-ATTRIBUTE-SPOOFING-DENIED
      - TEST-READ-ROLE-CANNOT-EXPORT
      - TEST-MFA-STEPUP-REQUIRED
      - TEST-PDP-OUTAGE-DENIES-SENSITIVE
      - TEST-REVOKED-ROLE-BLOCKS-DELAYED-JOB
      - TEST-DIRECT-WORKER-BYPASS-BLOCKED
      - TEST-AUDIT-OBLIGATION-ENFORCED
    evidenceReferences:
      - EV-POLICY-VERSION-CHECK
      - EV-PDP-NEGATIVE-TEST-RESULTS
      - EV-EXPORT-PEP-DECISION-LOGS
    openFindings:
      - FIND-LEGACY-EXPORT-WORKER-RECHECK
~~~

**Diễn giải:**

- `defaultEffect: DENY` mô tả yêu cầu; chỉ có ý nghĩa khi engine và PEP **thật sự triển khai**.
- `trustedSources` phải được xác minh về provenance, freshness và mapping.
- `enforcementPoints` là **population cần kiểm tra**, không phải bằng chứng chúng đã được bảo vệ.
- `reevaluateBeforeDelivery` cần thiết nếu thời điểm download khác xa thời điểm tạo file và chính sách yêu cầu quyền còn hiệu lực.
- `DENY_OR_CHALLENGE_BY_POLICY` là tên trạng thái minh họa, phải được chuyển thành quy tắc điều kiện xác định khi triển khai.
- Các evidence IDs chỉ là tham chiếu, không phải bản thân evidence.

### 9.3. Mô hình request/decision

Ví dụ request đã được PEP chuẩn hóa và xác minh:

```json
{
  "decisionRequestId": "REQ-12345",
  "subject": {
    "id": "u-104",
    "tenantId": "tenant-a",
    "roles": ["invoice_exporter"],
    "authnTime": "2026-11-28T02:01:00Z"
  },
  "resource": {
    "id": "invoice-batch-77",
    "tenantId": "tenant-a",
    "classification": "restricted"
  },
  "action": "invoice.export",
  "context": {
    "devicePosture": "verified-compliant",
    "risk": "low",
    "checkedAt": "2026-11-28T02:03:00Z"
  }
}
```

Ví dụ kết quả quyết định đã được xử lý:

```json
{
  "decisionId": "DEC-90871",
  "effect": "PERMIT",
  "policyVersion": "3.2",
  "resourceScope": {
    "tenantId": "tenant-a",
    "resourceId": "invoice-batch-77"
  },
  "mandatoryObligations": [
    "audit_export",
    "apply_field_whitelist",
    "recheck_before_delivery"
  ],
  "validUntil": "2026-11-28T02:08:00Z",
  "reasonCode": "INVOICE_EXPORT_CONDITIONS_MET"
}
```

Tất cả ID, timestamp và dữ liệu ở trên là **giả định để minh họa**. Trong thực tế, PEP không được tin `roles` hoặc `tenantId` chỉ vì chúng xuất hiện trong JSON do client gửi. Context phải được **server-side validated** từ nguồn có thẩm quyền và kết quả phải được ràng buộc với đối tượng gốc.

### 9.4. Pseudocode thực thi chính sách

```text
function decideAndEnforce(clientRequest, verifiedConnection):
    subject = resolveVerifiedSubject(verifiedConnection)
    target = loadAuthoritativeResource(clientRequest.resourceId)
    action = normalizeAllowedAction(clientRequest.operation)

    if subject is unknown or target is unknown or action is invalid:
        return denyAndAudit("UNVERIFIABLE_IDENTITY_RESOURCE_OR_ACTION")

    if not isTenantRelationPermitted(subject, target):
        return denyAndAudit("TENANT_SCOPE_MISMATCH")

    context = collectTrustedSignals(
        subject, target, action, requiredFreshnessFor(action)
    )
    if context.hasCriticalMissingOrStaleSignals:
        return safeFailureOrStepUpAsApprovedPolicyRequires()

    decision = evaluateApprovedPolicy(
        subject, target, action, context, effectivePolicyVersion()
    )

    if decision.effect != "PERMIT":
        return denyOrTriggerApprovedChallenge(decision)

    if not canEnforceAllMandatoryObligations(decision):
        return denyAndAudit("UNSUPPORTED_MANDATORY_OBLIGATION")

    result = executeUsingServerValidatedScope(
        subject, target, action, decision.constraints
    )
    auditDecisionAndActualEnforcement(decision, result)
    return result
```

Đây là pseudocode **minh họa tư duy**, không phải thư viện có thể triển khai nguyên trạng. Trong hệ thống thực phải xử lý lỗi/tranh chấp, concurrency, timeout, TOCTOU, transaction boundaries, redaction, idempotency và an toàn của audit. **Không dùng policy trả PERMIT để thay thế kiểm tra quyền trên chính tài nguyên tại thời điểm thực thi**.

## 10. Điểm quyết định cho request, phiên và workload

### 10.1. Ba cấp kiểm tra

| Cấp | Đối tượng | Ví dụ | Kiểm soát |
|---|---|---|---|
| **Session/connection** | Có mở kênh với một service không? | Thiết bị quản lý kết nối tới private app | Identity, posture, session expiry |
| **Request/API operation** | Có được gọi hành động cụ thể? | `invoice.export` hay `invoice.read` | Action/role/context policy |
| **Object/data operation** | Có được truy cập đúng record/field? | Invoice thuộc tenant nào? | Resource ownership, field scope và business invariant |

Một quyết định cho phép mở kết nối tới service **không cấp quyền mặc định cho mọi endpoint hoặc record bên trong**. Ngược lại, một request đến đúng endpoint vẫn có thể sai **object/field/tenant**.

### 10.2. Workload-to-workload Zero Trust

PDP cũng phải xem xét service identity và hành động của **machine workload**:

- mTLS hoặc token workload giúp xác thực service caller.
- Policy giới hạn **service A được gọi operation nào ở service B**.
- Data service cần xem **ngữ cảnh người dùng gốc** nếu thao tác thay mặt người dùng.
- Batch job có job identity, scope, TTL, submitter, approval và khi cần **recheck tại execution time**.
- Pipeline, admin jobs và backup process phải có quyền riêng, không lạm dụng “internal service”.

Ví dụ exporter đã được phép đọc từ DB với machine identity, nhưng điều đó **không có nghĩa exporter được đọc mọi tenant theo bất kỳ yêu cầu user nào**. Authorization của workload và authorization nghiệp vụ cần kết hợp.

### 10.3. Long-running và asynchronous operations

Một job có thể được chấp thuận lúc 09:00 nhưng chỉ chạy lúc 11:00. Trong khoảng thời gian đó, quyền có thể thay đổi.

Một thiết kế phù hợp cần xác định:

1. Quyền nào được kiểm tra lúc **submit**.
2. Quyền nào được kiểm tra lúc **job start**.
3. Có quyền nào cần kiểm tra tiếp trong lúc **đọc từng phần dữ liệu**.
4. Quyền nào được kiểm tra lúc **delivery/download**.
5. Có cơ chế **cancel** khi session/role bị thu hồi không.
6. Một phần output đã tạo được bảo vệ/xóa/retention thế nào.
7. Log nào chứng minh **decision scope và actual data scope** tương ứng.

Không mặc định mọi job phải dừng ngay khi user logout; **nghĩa vụ và chính sách nghiệp vụ** quyết định tính hợp lệ của tiếp tục xử lý. Nhưng phải có tiêu chí rõ, đặc biệt với job xuất dữ liệu nhạy cảm.

## 11. Khi PDP hoặc nguồn tín hiệu không khả dụng

### 11.1. Thiết kế safe failure

PDP có thể bị gián đoạn vì mất mạng, crash, quá tải, dependency timeout hoặc rollout lỗi. PIP cũng có thể không trả về thuộc tính cần thiết.

Với mỗi hành động, định nghĩa trước:

- Có cần **online PDP decision** hay có thể dùng decision cache đã xác minh?
- Hành động có thể **delay/queue** thay vì thực thi?
- Cache được dùng trong **thời hạn và version** nào?
- Khi thiếu thuộc tính quan trọng, có yêu cầu **challenge/step-up** hay deny?
- Có hành động emergency nào được phép và ai phê duyệt?
- PEP phải báo trạng thái **indeterminate/error** và ghi evidence thế nào?

### 11.2. Ma trận degraded behavior

| Hành động | PDP/PIP lỗi | Hành vi có thể được phê duyệt | Rủi ro cần kiểm tra |
|---|---|---|---|
| Xem nội dung công khai | PDP chưa cần thiết cho quyền đọc này | Tiếp tục theo public-access policy | Nội dung có thực sự public? |
| Đọc dữ liệu riêng tư | Không xác minh đủ quyền | Deny hoặc dùng scoped cache rất ngắn khi có căn cứ | Stale role/tenant membership |
| Xuất tập dữ liệu nhạy cảm | Thiếu tín hiệu hoặc PDP không khả dụng | Deny/queue chờ đánh giá lại | Lộ dữ liệu hàng loạt |
| Thay người nhận thanh toán | Không có fresh authorization | Deny/hold | Gian lận và integrity |
| Đăng nhập admin | IdP/step-up không khả dụng | Dừng, hoặc emergency workflow riêng theo policy | Privilege escalation |
| Workload tiếp tục phiên hiện tại | PDP ngắt kết nối | Bounded continuation nếu đáp ứng freshness/revocation policy | Stale permit, session hijack |
| Audit/decision log pipeline lỗi | Mất observability | Durable buffer hoặc controlled stop theo criticality | Silent loss of accountability |

**Fail-open/closed không phải chỉ là một switch toàn cục.** Có thể một tác vụ ít rủi ro tiếp tục bằng dữ liệu đã được đánh giá và một tác vụ nhạy cảm phải fail-closed. Không được vì outage mà cho phép **đọc chéo tenant, bypass MFA hoặc bỏ kiểm tra policy**.

### 11.3. Degraded mode cần được kiểm thử

Kiểm thử ít nhất:

- PDP trả timeout trước decision.
- PDP trả error/indeterminate.
- Policy repository có version lỗi.
- Device posture source không trả kết quả.
- IdP thu hồi role nhưng event propagation bị chậm.
- PEP đang dùng cache sau thời hạn.
- Token/decision signature không hợp lệ hoặc sai audience.
- Audit pipeline không nhận event.
- Policy được rollback trong khi job export đang chạy.

Test phải chứng minh **actual enforcement** và ghi **degraded decision/alert**, không chỉ chứng minh có log timeout.

## 12. PDP phân tán, caching và ranh giới resiliency

### 12.1. Centralized, embedded và hybrid

| Kiến trúc | Ưu điểm | Rủi ro/đánh đổi |
|---|---|---|
| **Centralized PDP** | Policy dễ chuẩn hóa, quyết định và audit tập trung | Latency, outage và blast radius của một service |
| **Embedded/local PE** | Latency thấp, độc lập hơn với mạng | Policy drift, phân phối version, revocation delay |
| **Hybrid** | Có thể cân bằng sensitivity và availability | Complexity, ownership và trường hợp conflict |

**“Dùng một policy engine duy nhất” không tự đồng nghĩa policy nhất quán** nếu PEP ở mỗi hệ thống truyền thuộc tính khác nhau hoặc có đường không gọi engine.

### 12.2. Điểm cần thử khi phân phối policy

- Local PE có nhận đúng **approved policy artifact/digest**?
- Có signature hoặc integrity protection khi phân phối?
- Có thể phát hiện/cô lập instance chạy **policy cũ hoặc không hợp lệ**?
- Có behavior an toàn khi policy update bị lỗi giữa chừng?
- Decision và enforcement logs có ghi đúng policy version?
- Có thể rollback mà không vô tình bật lại rule bị cấm?
- Khi permission bị thu hồi, local cache hết hiệu lực trong giới hạn nào?

### 12.3. Tính sẵn sàng không được đánh đổi bí mật và toàn vẹn

Một PDP HA có nhiều replicas vẫn có thể lỗi chung nếu tất cả:

- Phụ thuộc cùng IdP/PIP và policy store.
- Dùng chung database/queue hoặc secret.
- Nhận cùng bản policy sai trong một rollout.
- Dùng chung quyền admin có thể sửa rules trên toàn môi trường.
- Không có audit độc lập hoặc health monitoring cho decision correctness.

Đánh giá **common-mode failure và blast radius** cũng quan trọng như đánh giá uptime của decision API.

## 13. Change management, trách nhiệm và ngoại lệ

### 13.1. Vòng đời chính sách

~~~mermaid
flowchart TD
    A["Risk / requirement / policy proposal"] --> B["Policy authoring and versioning"]
    B --> C["Review: security, business, data owner"]
    C --> D["Static analysis + unit/negative tests"]
    D --> E["Approved release artifact"]
    E --> F["Canary / staged deployment"]
    F --> G["Effective policy + PEP verification"]
    G --> H["Decision telemetry / drift detection"]
    H --> I{"Incident, change or policy gap?"}
    I -- "Yes" --> J["Rollback / remediation / retest"]
    J --> B
    I -- "No" --> K["Periodic policy and access review"]
    K --> A
~~~

### 13.2. Quản trị thay đổi

Một change record cần:

1. **Policy ID/version**, phạm vi hệ thống, tenants, resources và actions.
2. Risk scenario, requirement IDs và lý do thay đổi.
3. Người đề xuất, reviewer và phê duyệt đúng thẩm quyền.
4. Diff giữa policy cũ/mới và **tác động tới permit/deny population**.
5. Unit/negative/integration tests; test với những request **đáng lẽ phải bị từ chối**.
6. Kế hoạch staged rollout, monitoring, rollback và kill switch an toàn.
7. Bằng chứng effective policy trên từng PDP/PEP hoặc môi trường.
8. Kết quả theo dõi và những exceptions/gaps còn tồn tại.

Đặc biệt, một policy change khiến **permit tăng đột biến** cần được phân tích theo action/tenant/resource, không mặc định là cải thiện trải nghiệm người dùng.

### 13.3. Phân chia trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| **Business/data owner** | Xác định hoạt động và dữ liệu nào được phép truy cập |
| **Security architect** | Threat model, Zero Trust principles và policy requirements |
| **Access governance owner** | Phê duyệt RBAC/ABAC/ReBAC model và quyền thay đổi policy |
| **PDP/policy-engine owner** | Thiết kế, triển khai, phân phối rule và bảo đảm correctness |
| **PEP/application owner** | Enforce ở API/object/job, obligations và chống bypass |
| **IdP/device/risk source owner** | Cung cấp thuộc tính đúng, có freshness và revocation |
| **Platform/SRE** | Capacity, availability, observability và failure handling |
| **Risk owner** | Xử lý/cho phép ngoại lệ theo thẩm quyền thực tế |
| **Security assurance / QA** | Lập test, đánh giá evidence, scope và findings |
| **Internal audit** | Đánh giá độc lập theo phạm vi được giao |

### 13.4. RACI minh họa

**R**: trực tiếp thực hiện; **A**: chịu trách nhiệm cuối cùng; **C**: tham vấn; **I**: được thông báo.

| Hoạt động | Data owner | Security/governance | PDP team | PEP team | Assurance |
|---|---|---|---|---|---|
| Xác định quyền theo dữ liệu/nghiệp vụ | **A/R** | C | C | C | I |
| Thiết kế rule và combining logic | C | **A** | **R** | C | C |
| Quản lý phiên bản và triển khai policy | I | C | **A/R** | R | C |
| Enforce resource/object access | C | C | C | **A/R** | C |
| Kiểm tra provenance/freshness tín hiệu | C | **A** về chuẩn | R | R | C |
| Kiểm thử độc lập và audit evidence | C | C | C | C | **A/R** |

Với vấn đề chấp nhận rủi ro, phải dùng **risk approval authority thực tế**, không tự suy người có quyền merge policy cũng có quyền chấp nhận bỏ authorization.

### 13.5. Emergency/break-glass

Trường hợp khẩn cấp có thể cần cơ chế truy cập ngoài quy trình thông thường, nhưng phải có:

- Danh tính riêng và xác thực phù hợp.
- Phạm vi tối thiểu, thời hạn và lý do.
- Independent approval hoặc review theo mức rủi ro.
- Log và cảnh báo có khả năng đối chiếu độc lập.
- Kiểm soát cấp quyền/thu hồi tự động nếu phù hợp.
- Hậu kiểm truy cập dữ liệu, thay đổi và quyền còn sót.

**Break-glass không phải “allow all khi PDP down”.** Một đường emergency không thể được kiểm tra hoặc giới hạn không phải phương án resilience đáng tin.

## 14. Kiểm thử PDP/PEP theo thiết kế, triển khai và vận hành

### 14.1. Ba lớp assurance

| Lớp | Câu hỏi | Evidence |
|---|---|---|
| **Design effectiveness** | Policy model có đáp ứng risk/least privilege/tenant isolation? | Threat model, architecture, policy standard, design review |
| **Implementation** | PDP, PIP, PEP, identity và data layer có cấu hình như thiết kế? | Effective policy, deployment, source config, PEP inventories |
| **Operating effectiveness** | Decision trong kỳ có đúng, được enforce và thu hồi khi cần? | Request traces, negative tests, revocation runs, audit sampling |
| **Completeness** | Những đường truy cập và populations nào đã được kiểm tra? | API/worker/data path enumeration, access logs, inventory |
| **Evidence integrity** | Log, change records và test results có đáng tin? | Protected audit, SoD, version/correlation và access review |

Một sơ đồ có PEP chưa chứng minh mọi request đi qua PEP. Một quyết định PERMIT của PE cũng chưa chứng minh **constraints được thực hiện**.

### 14.2. Ma trận kiểm thử

| Kiểm thử | Expected behavior | Bằng chứng |
|---|---|---|
| User có read nhưng không export | DENY export | Decision log, API response và không có file |
| User tenant B đọc invoice A | DENY kể cả đổi invoice ID | Decision + DB/object access test |
| Client giả mạo device compliant | Không dùng claim giả | Verified signal provenance và rejection |
| MFA không đủ fresh | Challenge/deny, không export trước step-up | Session events và actual export state |
| Resource đổi owner giữa check và action | Không thao tác sai owner | Version/transaction assertions |
| PDP timeout | Safe failure theo policy | Fault injection, PEP response, audit |
| PIP/role lookup timeout | Unknown, không silent permit | Degraded status + control test |
| Role revoked khi export chờ queue | Job bị reevaluate/cancel theo policy | Revocation timing và job logs |
| Export worker được gọi trực tiếp | Không bypass enforcement | Network/identity authorization test |
| Decision có mandatory redaction | Output đã redact hoặc bị từ chối | Export file inspection trong test an toàn |
| Policy version cũ trong một replica | Alert/drift, không áp sai policy | Version reconciliation/rollout evidence |
| Admin tự sửa policy không phê duyệt | Bị chặn hoặc phát hiện, rollback | SoD/access negative test và change audit |
| Audit pipeline mất sự kiện | Degraded/alert, control response | Logging health và synthetic failure test |

Test phải ghi **expected và actual**, môi trường/version, scope, subject/resource references và lý do PASS/FAIL. Không thực hiện test xâm nhập dữ liệu thật ngoài phạm vi được phép.

### 14.3. Gherkin: các trường hợp then chốt

```gherkin
Feature: Zero Trust PDP and PEP access assurance

  Scenario: A valid login does not authorize a foreign tenant record
    Given user U1 is authenticated for tenant T1
    And invoice I2 is owned by tenant T2
    When U1 requests invoice I2 through the application
    Then the relevant PEP must deny the object access
    And the decision and enforcement outcomes must be auditable

  Scenario: A read privilege cannot be reused for export
    Given user U2 is allowed to read invoices in tenant T1
    And U2 has no invoice.export permission
    When U2 requests a bulk invoice export
    Then the export must be denied
    And no asynchronous export job may be started for the request

  Scenario: Spoofed tenant or device attributes cannot grant access
    Given user U3 has no valid membership in tenant T2
    When U3 submits client-controlled tenant and compliance headers
    Then the PDP must rely on verified authoritative attributes
    And the request must not obtain tenant T2 access

  Scenario: A sensitive export requires fresh assurance
    Given user U4 has an authenticated session
    And the authentication assurance is too old for sensitive export
    When U4 requests restricted invoice export
    Then the workflow must challenge or deny according to policy
    And no restricted file may be delivered before required checks pass

  Scenario: Missing critical PIP data does not become permission
    Given a resource owner attribute is required to decide access
    And the authoritative resource metadata source times out
    When an access decision is requested
    Then the decision must not become an unverified permit
    And a degraded or indeterminate condition must be recorded

  Scenario: A revoked role stops a delayed export
    Given U5 submitted an export while authorized
    And the export worker has not yet started
    And U5's export privilege has been revoked
    When the worker attempts to execute the job
    Then the required authorization recheck must fail
    And the worker must not deliver restricted data

  Scenario: A direct worker invocation cannot bypass PDP enforcement
    Given an export worker can read restricted records
    And caller W6 lacks valid export authority
    When W6 invokes the worker outside the public API gateway
    Then the worker must reject the operation
    And no protected dataset may be exported

  Scenario: Mandatory policy obligations must be enforced
    Given a policy permits export only with field redaction and audit
    And the export component cannot apply the required redaction
    When an otherwise authorized export is attempted
    Then the export must not proceed without the mandatory obligation
    And the failure must be recorded

  Scenario: PDP outage does not grant sensitive access
    Given sensitive payment changes require a live policy decision
    And the PDP service is unavailable
    When a subject requests a beneficiary change
    Then the change must not be committed
    And the PEP must report the approved degraded outcome

  Scenario: Policy rollout does not silently retain an older version
    Given policy version V2 revokes a previously permitted export
    And one PDP instance still runs version V1
    When the deployment verification process runs
    Then it must identify the version mismatch
    And the instance must follow the approved containment policy
```

Các scenario là **yêu cầu kiểm thử** chứ không phải bằng chứng chạy thành công. Để kết luận PASS cần runner logs, code/test references, môi trường, thời kỳ, actual resource state, policy version và report được bảo vệ.

### 14.4. Test attribute quality và policy conflict

Những tình huống bổ sung:

1. Role vừa thu hồi nhưng token còn hiệu lực.
2. Resource owner đổi; decision cache chưa invalidated.
3. Token có signature đúng nhưng **audience/scope** không dành cho resource đang gọi.
4. Subject có hai role, một permit và một deny; combining rule phải nhất quán.
5. Policy không có rule áp dụng; implicit deny phải có hiệu lực.
6. PIP trả unknown trong lúc secondary source trả stale value.
7. Client cung cấp `risk=low`; service phải không tin claim này.
8. Policy engine báo lỗi evaluation; PEP không coi là allow.
9. Obligation yêu cầu audit nhưng audit sink lỗi; system phải theo safe-failure policy.
10. Một connection đã được phép vẫn không được tự do gọi object khác.

### 14.5. Test không chỉ ở unit test

Một rule unit test có thể đúng nhưng production sai vì:

- Gateway không gọi PDP cho route mới.
- Service gọi PDP nhưng truyền **sai action**.
- DB mapping trả tenant từ tham số client.
- PEP chỉ kiểm tra ở request submit, worker không kiểm tra khi chạy.
- Policy version local khác bản được phê duyệt.
- Admin endpoint trực tiếp bỏ qua authorization middleware.
- Service account được cấp quyền database quá rộng và được khai thác qua confused deputy.

Do đó cần **integration, end-to-end, runtime/config review, negative và failure-path tests**. Việc test một API route không đủ nếu còn những ingress/egress khác trong cùng risk scenario.

## 15. Audit evidence và bảo vệ thông tin trong decision logs

### 15.1. Một decision record hữu ích

Nên có metadata:

- Decision/request ID để liên kết với PEP/action logs.
- Subject/workload reference đã xác minh; **không cần full PII**.
- Resource ID hoặc safe reference; tenant scope.
- Action chuẩn hóa.
- Policy ID/version và rule/combining outcome.
- Context source versions/freshness hoặc hash/reference khi cần.
- Thời gian request, evaluation, expiration/reevaluation.
- Decision effect và reason code.
- Obligations/constraints được yêu cầu và trạng thái thực thi.
- PDP/PEP instance, release và environment.
- Lỗi/unknown/degraded status và exception reference nếu có.

**Không đưa access token, password, private key, dữ liệu cá nhân thô hoặc toàn bộ resource content vào log để “có bằng chứng”.** Evidence phải được bảo vệ bằng access controls, integrity/retention và logging health.

### 15.2. Correlate decision với actual enforcement

Một chuỗi evidence lý tưởng:

```text
Request REQ-12345
  -> PEP invoice-api route invoice.export
  -> PDP decision DEC-90871 (policy 3.2, PERMIT, tenant A)
  -> PEP applies field-scope and audit obligations
  -> Export job JOB-771 created with tenant A scope
  -> Worker rechecks decision before processing
  -> Output FILE-120 contains only approved fields
  -> Download gateway confirms authorized recipient
  -> Outcome recorded in protected audit store
```

Nếu chỉ có `DEC-90871 PERMIT` nhưng không có job/output/delivery evidence, auditor **chưa thể kết luận dữ liệu được thực thi đúng giới hạn**. Nếu policy trả DENY mà log data access cho thấy DB vẫn trả record, đó là **enforcement failure nghiêm trọng**.

### 15.3. Evidence matrix

| Assurance question | Evidence gợi ý | Giới hạn cần khai báo |
|---|---|---|
| Policy có đúng mục tiêu? | Requirements, threat model, policy review | Chưa chứng minh implementation |
| Policy version có hiệu lực? | Signed artifact, deployment, effective config | Có thể có PEP khác chưa cập nhật |
| Tín hiệu đáng tin? | IdP/PIP config, provenance tests | Tín hiệu có thể stale hoặc mapping sai |
| PEP có kiểm tra mọi đường? | Endpoint/worker inventory và bypass tests | Legacy/third-party path chưa scan |
| Request DENY có bị chặn thật? | PDP+PEP logs, negative test, actual DB/file state | Chỉ test môi trường/scope được chỉ định |
| Thu hồi quyền hiệu quả? | Revocation drill, cache invalidation/TTL | Phạm vi workload/session chưa bao phủ |
| Outage xử lý an toàn? | Fault injection, degraded logs và alert | Không đại diện mọi lỗi đồng thời |
| Audit không bị sửa/xóa? | IAM/SoD, log integrity và access reviews | Nguồn vendor log có thể giới hạn |
| Control hoạt động trong kỳ? | Production sampling, change/incident records | Mẫu và thời gian phải công bố |

### 15.4. Không tạo assurance claim rộng hơn evidence

Ví dụ một claim đúng phạm vi:

> **Claim:** Trong bản triển khai InvoiceHub production được đánh giá, các yêu cầu `invoice.export` qua Invoice API và Export Worker đã kiểm tra authorization theo policy version 3.2; các thử nghiệm truy cập chéo tenant được thực thi và bị từ chối đúng theo yêu cầu.
>
> **Argument:** PEP xác định subject/resource/tenant từ nguồn được xác minh; PDP kiểm tra role, tenant và assurance; worker tái xác minh trước export; audit liên kết decision và output.
>
> **Evidence:** Policy artifact, effective config, identity/resource mapping, cross-tenant negative tests, worker execution logs và protected audit records.
>
> **Limitations:** Legacy support export path và một vendor download link chưa được đánh giá đầy đủ; không kết luận toàn hệ thống được bảo vệ trước mọi trường hợp bypass.

**Đúng ngữ nghĩa Zero Trust assurance** là nêu rõ những gì đã được kiểm tra và phần nào chưa có bằng chứng, rồi theo dõi finding/plan khắc phục.

## 16. Đo hiệu quả PDP và continuous assurance

### 16.1. Những metric nên dùng

| Metric | Ý nghĩa | Giới hạn/cảnh giác |
|---|---|---|
| **PEP coverage** | Tỷ lệ đường truy cập nằm trong scope có enforcement kiểm chứng được | Mẫu số cần gồm API, worker, storage, admin và legacy |
| **Decision trace coverage** | Request có thể liên kết PDP decision ↔ PEP actual outcome | Log thành công không tự chứng minh action đúng |
| **Policy version consistency** | PDP/PEP chạy policy được phê duyệt | Policy digest có thể giống nhưng context mapping khác |
| **Stale decision rate** | Tần suất dùng decision/cache quá hạn hoặc sai version | Detection thiếu có thể làm metric đẹp giả |
| **Revocation latency** | Từ lúc quyền bị thu hồi đến khi enforcement ngăn truy cập | Cần định nghĩa điểm bắt đầu/kết thúc |
| **Missing critical attributes** | Quyết định thiếu dữ liệu cần thiết | Không nên tự chuyển thành permit |
| **Denied request rate** | Tần suất từ chối theo action/tenant | Nhiều deny không nhất thiết là dấu hiệu xấu |
| **Permit anomalies** | Permit tăng bất thường theo user/action/policy version | Cần xem rollout và nghiệp vụ thực tế |
| **Policy conflict rate** | Rule xung đột/không xác định khi đánh giá | Phải phân biệt rule không áp dụng và bug |
| **Decision latency/availability** | PDP có đáp ứng deadline? | Uptime cao không chứng minh correctness |
| **Fallback/degraded use** | Lần dùng cache/break-glass do outage | Mỗi fallback cần scope và expiry |
| **Open authorization findings** | Gaps còn tồn tại và retest status | Exception không được tính là PASS |

### 16.2. Ví dụ tính coverage

Giả sử kiểm kê độc lập xác nhận **40 đường truy cập** cần PEP. Trong đó:

- 30 đường có evidence PEP enforcement và negative tests đạt.
- 6 đường có PEP nhưng chưa có kiểm thử actual enforcement đủ scope.
- 4 đường legacy chưa áp PEP.

```text
Verified enforcement coverage = 30 / 40 = 75%
Unverified enforcement paths = 6
Known unprotected legacy paths = 4
```

**75% chỉ phản ánh 40 đường đã biết**, không chứng minh 75% tổng số đường truy cập nếu inventory chưa đầy đủ. Hơn nữa, 30 đường có test PASS trong kỳ không tự chứng minh các lần truy cập thật khác **không bị bypass**; cần thêm logs, monitoring và test sau thay đổi.

### 16.3. Continuous policy assurance

Thiết lập trigger đánh giá lại khi:

- Thêm API route, queue consumer, admin endpoint hoặc direct storage access.
- Thêm tenant, resource type, field nhạy cảm hoặc mục đích xử lý.
- Thay IdP/session/token, MFA/step-up hoặc device posture mechanism.
- Thay role membership, delegation và revocation distribution.
- Thay policy engine, PIP, PEP library, SDK hoặc service mesh.
- Thay chính sách, combining semantics, data classification hoặc retention.
- Rollout một phiên bản mới hoặc phát hiện policy drift.
- Có incident cross-tenant access, stale permission, bypass hoặc logging gap.
- Thay vendor, cloud region hoặc Zero Trust control plane.

Mỗi trigger nên liên kết **change ID → affected resources/actions → test suite → actual evidence → finding/approval**. PDP assurance là **chương trình liên tục** chứ không phải một cuộc rà soát sơ đồ duy nhất.

## 17. Tình huống tổng hợp: đăng nhập an toàn nhưng export sai tenant

Nền tảng InvoiceHub dùng SSO + MFA và một gateway có PDP tập trung. Nhóm dự án báo cáo “Zero Trust đã triển khai” vì gateway cho phép request chỉ sau khi AuthN thành công và gọi PDP.

Một đợt assurance độc lập phát hiện:

1. Policy chỉ kiểm tra user có role `invoice_exporter`, **không kiểm tra tenant của invoice**.
2. Gateway truyền `resource.tenantId` lấy từ header của client, không đối chiếu với DB.
3. Export worker chạy bất đồng bộ bằng service account có thể đọc **mọi tenant**.
4. Worker dùng authorization decision được ghi lúc submit; **không tái kiểm tra khi bắt đầu**.
5. Người dùng bị thu hồi quyền nhưng export job vẫn chạy từ queue sau một giờ.
6. Link tải file được cấp theo URL đoán được và không còn xác thực người tải sau khi phát hành.
7. Decision log chỉ ghi PERMIT/DENY, không ghi actual object/tenant scope, policy version hoặc output.

### 17.1. Root cause và risk

| Vấn đề | Lớp lỗi | Tác động |
|---|---|---|
| Chỉ xét role | Policy design/ABAC scope | Quyền export quá rộng |
| Tin header tenant | PIP/attribute integrity | Attacker tự thay resource context |
| Worker quyền toàn tenant | PEP/workload authorization | Confused deputy, data leakage |
| Job không tái kiểm tra | Continuous evaluation/TOCTOU | Stale permit sau revocation |
| Download không reauth | PEP bypass/delivery | File nhạy cảm có thể bị đọc sai người |
| Decision log thiếu scope | Evidence/monitoring | Không chứng minh actual enforcement |

**MFA thành công không ngăn được lỗ hổng trên.** Authentication giúp biết user là ai, còn authorization cần kiểm tra **đúng tài nguyên/hành động/ngữ cảnh và mọi đường truy cập**.

### 17.2. Kế hoạch remediation theo chiều sâu

**Bước 1 — Containment:** Kiểm soát quyền export, vô hiệu hóa đường tải không an toàn và điều tra những file có thể đã lộ. Bảo toàn evidence và kích hoạt quy trình incident nếu có dấu hiệu disclosure.

**Bước 2 — Sửa policy:** Bổ sung tenant/resource owner authoritative, deny by default, giới hạn action và scope; có test cross-tenant.

**Bước 3 — Sửa attribute sourcing:** Lấy identity/tenant membership từ nguồn xác minh; resource ownership từ database hoặc service authority. Không tin header tự khai.

**Bước 4 — Sửa PEP:** Kiểm tra object-level authorization tại service/worker, không chỉ gateway. Service account chỉ có quyền kỹ thuật tối thiểu cần thiết.

**Bước 5 — Thu hồi/quản lý phiên:** Reevaluate khi job start/delivery, có cancel/revocation và phù hợp TTL. Kiểm tra thực tế revocation latency.

**Bước 6 — Secure delivery:** Giới hạn link theo recipient, tenant/resource, expiry và audit; rà soát các bản export tồn tại và retention.

**Bước 7 — Evidence:** Correlate decision ID, effective policy version, worker execution, resource tenant, output field scope và actual delivery.

**Bước 8 — Retest:** Negative tests cho header spoofing, role mismatch, cross-tenant export, revoked delayed job, direct worker call và URL download.

### 17.3. Claim–Argument–Evidence sau đánh giá

Trước khắc phục:

> **Claim được hỗ trợ:** Các request qua gateway của InvoiceHub trong phạm vi kiểm tra có xác thực SSO/MFA và gọi PDP để đánh giá role cơ bản trước export.
>
> **Evidence:** Gateway config, AuthN flow, PDP decision logs và kiểm thử role-based decision.
>
> **Limitations:** Không đủ bằng chứng Zero Trust authorization ở cấp tenant/object, worker, delayed job và delivery; tồn tại những đường có nguy cơ bị bypass.
>
> **Action:** Mở security findings, quyết định mức độ xử lý theo rủi ro, sửa policy/PEP và test lại trước khi mở rộng claim.

Sau khắc phục, chỉ mở rộng kết luận đến những tài nguyên, actions, environments, policy versions và thời kỳ **được kiểm chứng thực tế**.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao không đủ? | Cách cải thiện |
|---|---|---|
| Coi PDP như tường lửa hoặc gateway | PDP quyết định, PEP mới enforce | Chỉ rõ PE/PA/PEP và đường truy cập |
| Coi MFA là quyền truy cập mọi thứ | AuthN khác AuthZ | Subject–resource–action policy |
| Dựa vào IP/VPN để tin mặc định | Network location không chứng minh quyền | Workload/user identity và context |
| Chỉ RBAC theo role | Bỏ owner, tenant, business state | ABAC/ReBAC/object authorization |
| Đọc tenant ID từ header client | Có thể bị spoof | Resolve từ server-side source of truth |
| Dùng một PERMIT cho mọi action | Không giới hạn scope | Per-action/resource/field permission |
| Gateway kiểm tra nhưng worker không | PEP bypass/confused deputy | Complete mediation, independent recheck |
| Dùng allow cache vô hạn | Quyền đã thu hồi vẫn có hiệu lực | Bounded TTL, revocation và freshness |
| PIP timeout được coi risk thấp | Unknown ≠ verified safe | Degraded handling, no implicit permit |
| Step-up cấp quyền mọi thao tác | Không ràng buộc action/resource | Fresh assurance bound to context |
| Policy conflict được giải bằng thứ tự tình cờ | Engine khác nhau có thể xử lý khác | Approved combining semantics/tests |
| Không kiểm tra obligations | PEP có thể bỏ redaction/audit | Mandatory obligation enforcement |
| Rollout policy không có negative tests | Permit quá rộng khó được phát hiện | Diff, impact simulation và staged release |
| Dùng log decision làm bằng chứng end-to-end | Không biết DB/file thực sự truy cập thế nào | Correlate PDP↔PEP↔resource outcome |
| PDP downtime dẫn đến allow all | Fail-open gây lộ dữ liệu | Safe failure theo risk/action |
| Central PDP = không còn single point of failure | Shared PIP/IdP/policy vẫn lỗi chung | Resilience và common-mode threat model |
| Chỉ đếm số policy rules | Không phản ánh coverage hoặc correctness | Test đường truy cập và dữ liệu |
| Chấp nhận exception vô thời hạn | Quyền rộng bị giữ mãi | Owner, expiry, risk approval và retest |
| Audit chứa token/PII thô | Bằng chứng tự trở thành nguồn rò rỉ | Log metadata tối thiểu, bảo vệ integrity |
| Tuyên bố “Zero Trust hoàn tất” từ sơ đồ | Không chứng minh operating effectiveness | Scoped claim–argument–evidence |

## 19. Bài tập thực hành

### Bài tập 1 — Gán PE, PA, PEP và PIP

Một kiến trúc có IdP, device management, policy engine, API gateway, microservice, export worker, database và logging service.

**Yêu cầu:** Vẽ luồng truy cập, chỉ rõ **PE, PA, PEP, nguồn PIP** theo mô hình bạn chọn, mô tả luồng grant/deny/revoke và ít nhất **hai cách bypass** nếu chỉ kiểm tra tại gateway. Phân biệt chức năng logic với sản phẩm vật lý.

### Bài tập 2 — Viết policy tenant isolation

Nhân viên tenant A có role `invoice_viewer`; đối tượng I2 thuộc tenant B. Một tài khoản khác của tenant A có quyền export nhưng session assurance đã hết hạn.

**Yêu cầu:** Viết rule ABAC kết hợp RBAC, mô tả authoritative sources, default-deny, effect cho cả hai request và test expected/actual. Chỉ ra vì sao không tin tenant ID do client khai.

### Bài tập 3 — Thu hồi role và cache

User U có quyền export lúc 10:00; lúc 10:05 admin thu hồi role; job được tạo lúc 10:01 nhưng chỉ bắt đầu lúc 10:20. PDP decision cache TTL 30 phút.

**Yêu cầu:** Xác định các điểm TOCTOU, đề xuất revocation propagation, recheck và giới hạn cache theo mục tiêu đã phê duyệt. Viết ít nhất ba negative tests và metric **revocation latency**.

### Bài tập 4 — PDP unavailable

PDP central service lỗi; risk engine trả timeout; một user cần xem dashboard công khai, một user muốn export dữ liệu cá nhân và một operator muốn thay người nhận thanh toán.

**Yêu cầu:** Thiết kế bảng degraded behavior theo từng action, bảo đảm không biến unknown thành allow. Xác định fallback nào có thể dùng cache đã xác minh và bằng chứng cần ghi khi degraded.

### Bài tập 5 — Confused deputy qua worker

Service exporter dùng machine identity đọc mọi tenant. API kiểm tra user có `exporter` role nhưng không check invoice owner, worker nhận invoice IDs tùy ý.

**Yêu cầu:** Phân tích threat model, thiết kế PEP ở API/service/worker/database và ít nhất năm acceptance tests chống cross-tenant export. Phân biệt workload authentication với business authorization.

### Bài tập 6 — Policy-as-code change

Một rule mới cho phép đội support đọc dữ liệu khách hàng theo yêu cầu hỗ trợ. Policy diff có khả năng mở rộng quyền tới mọi tenant.

**Yêu cầu:** Thiết kế review, deny-overrides, scope delegation, JIT elevation, expiry, simulation trước rollout, canary, monitoring và rollback. Viết cấu trúc evidence package cho change.

### Bài tập 7 — Gherkin và assurance case

Nhóm phát triển cung cấp screenshot cấu hình PDP và 10 unit tests PASS nhưng chưa có runtime decision traces, PEP bypass tests hoặc kết quả object-level authorization.

**Yêu cầu:** Viết **Claim–Argument–Evidence–Limitations** chỉ với chứng cứ hiện có. Đề xuất các integration/negative/failure-path tests cần bổ sung để kết luận policy được enforce.

### Bài tập 8 — Đo coverage và drift

Inventory có 40 entry points cần enforcement, 30 đã test PASS, 6 có PEP nhưng chưa test đủ, 4 legacy không có PEP. Một cloud account khác chưa được quét và một local PDP chạy policy cũ.

**Yêu cầu:** Tính verified coverage trên **40 đường đã biết**, giải thích giới hạn mẫu số, đề xuất metric drift và nguồn đối chiếu độc lập. Ghi findings, owner, severity dựa trên risk và retest criteria.

## 20. Checklist đánh giá Policy Decision Point

- **Scope:** Có định nghĩa protected resources, actions, subjects, tenants, environments và data flows không?
- **Architecture:** PE, PA, PDP, PEP, IdP, PIP và policy repository có chức năng và owner rõ?
- **AuthN/AuthZ:** Có tách danh tính/xác thực khỏi quyết định truy cập cụ thể?
- **Trusted context:** Subject, device, resource, risk, session và business state có provenance/freshness?
- **Default deny:** Không có allow hợp lệ, rule không áp dụng hoặc lỗi đánh giá có bị chặn?
- **Policy semantics:** RBAC/ABAC/ReBAC và combining rule có rõ, nhất quán, test được?
- **Tenant/object scope:** Resource owner từ source-of-truth, không tin client header/URL?
- **PEP coverage:** Gateway, service, worker, storage, admin/legacy và đường download đã được kiểm tra?
- **Complete mediation:** Có đường direct/batch/storage bypass không; có kiểm thử?
- **Obligations:** Mandatory redaction, audit, limit, challenge hoặc session constraints có được thực thi?
- **Session:** Quyết định được ràng buộc với action/resource, thời hạn và trigger reevaluate?
- **Revocation:** Role/session/resource change có hiệu lực trong giới hạn đã duyệt; cache có invalidation?
- **Step-up:** Xác thực bổ sung có gắn đúng thao tác, subject, thời điểm và mức rủi ro?
- **Failure behavior:** PDP/PIP unavailable hoặc indeterminate không tự thành permit?
- **Resilience:** PDP HA, local policy, shared dependencies, stale version và common-mode risks đã được test?
- **Policy-as-code:** Rule có version, approval, integrity, quality gates, rollout và rollback?
- **Control plane:** Ai được thay policy, deploy engine, cấp quyền, sửa audit; có SoD?
- **Audit:** Có decision ID liên kết actual enforcement; log không chứa secret/PII không cần thiết?
- **Testing:** Có negative cross-tenant, role mismatch, attribute spoofing, bypass, revocation, outage và TOCTOU?
- **Evidence:** Test có expected/actual, policy version, release, environment, reviewer và limitations?
- **Metrics:** Đã đo enforcement coverage, drift, revocation latency, stale permits và degraded decisions?
- **Findings:** Gap và exceptions có risk owner, remediation, expiry và retest?
- **Continuous assurance:** Thay API, data class, vendor, identity, policy, PEP hoặc incident có trigger review/test lại?

**Điều cần ghi nhớ:** **Policy decision point** là chức năng ra quyết định truy cập dựa trên chính sách và tín hiệu đáng tin, không phải tấm vé “đã xác thực thì được vào”. Trong **Zero Trust assurance**, tổ chức cần chứng minh **policy đúng → input đúng → quyết định đúng → PEP thực thi đúng → quyền được thu hồi đúng → evidence đủ phạm vi**. Khi một mắt xích thiếu, đặc biệt là object-level enforcement, tín hiệu đáng tin hoặc kiểm tra các đường đi tắt, việc có PDP vẫn chưa đủ để khẳng định bảo vệ theo Zero Trust.
