# Thực thi chính sách liên tục trong Zero Trust IAM

> **Chương:** Zero Trust IAM  
> **Bài học:** Thực thi chính sách liên tục (Continuous Policy Enforcement)  
> **Phạm vi:** Quản lý vòng đời danh tính và quyền truy cập trong IAM theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi đổi vai trò. Bài liên hệ **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **thực thi chính sách liên tục** là việc bảo đảm quyết định cho phép truy cập được đánh giá, áp dụng và đánh giá lại ở các điểm kiểm soát thích hợp khi trạng thái liên quan thay đổi; không chỉ kiểm tra một lần lúc đăng nhập.
2. Phân biệt **xác thực (authentication)**, **ủy quyền/phân quyền (authorization)**, **đánh giá chính sách (policy decision)**, **thực thi (enforcement)** và **quản trị chính sách (policy administration)**.
3. Thiết kế luồng phối hợp **Policy Enforcement Point (PEP)**, **Policy Decision Point (PDP)**, **Policy Administrator (PA)**, nguồn thuộc tính, IdP/SSO, SCIM và hệ thống sở hữu tài nguyên.
4. Xây dựng quy tắc cho **subject, action, resource, context**, kết hợp RBAC/ABAC, trạng thái JML, phiên, thiết bị và workload để quyết định allow/deny/challenge hoặc các nghĩa vụ kèm theo.
5. Giải thích độ trễ giữa sự kiện thu hồi và việc chặn request, giới hạn của JWT, cache, phiên lâu dài, kết nối WebSocket và job chạy nền.
6. Thiết kế **fail-safe**, kiểm soát thay đổi chính sách, cơ chế audit và kiểm thử phủ các trường hợp cross-tenant, token cũ, Mover/Leaver, sự kiện đến trễ và chính sách không khả dụng.
7. Đề xuất các chỉ số đánh giá **độ phủ thực thi, độ mới quyết định, thời gian thu hồi, sai lệch policy và tính sẵn sàng**.

## 2. Thực thi chính sách liên tục là gì?

Trong một hệ thống truyền thống, ứng dụng có thể thực hiện:

1. Người dùng đăng nhập SSO.
2. Ứng dụng kiểm tra role vào đầu phiên.
3. Ứng dụng lưu cờ isAdmin hoặc danh sách quyền trong session.
4. Những request tiếp theo được thực hiện dựa trên quyền đã lưu, ít khi đánh giá lại.

Mô hình này gặp vấn đề khi **vai trò thay đổi, tài khoản bị vô hiệu hóa, thiết bị có rủi ro, quyền tạm thời hết hạn hoặc chính sách mới được ban hành**. Một phiên từng hợp lệ có thể tiếp tục thực hiện hành động không còn được ủy quyền.

**Continuous Policy Enforcement (CPE)** là phương pháp thiết kế bảo đảm rằng **mọi hoạt động thuộc phạm vi chính sách được chặn/cho phép bằng quyết định còn hiệu lực**, đồng thời có đường phản ứng với các thay đổi quan trọng trong suốt quá trình sử dụng.

Từ **liên tục** không đồng nghĩa phải gọi một PDP qua mạng ở mỗi mili giây. Tùy rủi ro và loại tài nguyên, việc thực thi có thể xảy ra:

- Tại **mỗi yêu cầu** API hoặc mỗi action nhạy cảm.
- Khi tạo, duy trì, nâng quyền hoặc kết thúc **phiên/kết nối**.
- Trước từng bước có tác dụng phụ trong **workflow dài**.
- Khi nhận **sự kiện**: Mover, Leaver, thu hồi đặc quyền, thay đổi policy, posture rủi ro cao.
- Theo **giới hạn tuổi quyết định/cache** được quy định rõ.
- Tại các ranh giới đặc biệt: export, thanh toán, truy cập secret, tạo credential, truy cập chéo tenant.

### Ví dụ

08:30, nhân viên Hà đăng nhập SSO và có quyền Sales. 09:00, hệ thống HRIS xác nhận Hà chuyển sang Finance, thu hồi quyền Sales. 09:05, Hà gọi API xuất dữ liệu Sales với access token còn hạn đến 10:30.

Nếu API chỉ dựa vào role=sales trong token cũ, request có thể bị cho phép sai. Nếu PEP/PDP có **trạng thái quyền hiện hành** và chính sách export yêu cầu quyền Sales vẫn có hiệu lực, API phải **deny**, bất kể token còn đúng chữ ký và chưa hết hạn.

**Giá trị của thực thi liên tục không nằm ở số lần hỏi PDP, mà ở việc các thay đổi quan trọng thực sự ảnh hưởng đến điểm truy cập đúng hạn.**

## 3. Phân biệt sáu nhiệm vụ thường bị gộp làm một

| Nhiệm vụ | Câu hỏi chính | Thành phần thường liên quan | Không thay thế được |
|---|---|---|---|
| **Identity proofing** | Danh tính ban đầu được chứng minh ra sao? | HR/hợp đồng, onboarding, registry | Quyền sử dụng một tài nguyên cụ thể |
| **Authentication (AuthN)** | Ai đang chứng minh quyền sử dụng danh tính này? | IdP, SSO, MFA, workload issuer | Kiểm tra tenant, role, action |
| **Authorization (AuthZ)** | Chủ thể có được thực hiện hành động trên tài nguyên này không? | Policy, PDP, ứng dụng, database | Tính toàn vẹn của credential |
| **Policy decision** | Với bằng chứng hiện tại, kết quả theo policy nào? | PDP/policy engine | Tự động chặn request nếu không có PEP |
| **Policy enforcement** | Quyết định được thực thi ở đâu, có đường bypass không? | PEP, gateway, backend, data layer | Quản trị vòng đời danh tính |
| **Policy administration** | Ai tạo, duyệt, ban hành, đổi, thu hồi và version policy? | IAM/Security, owners, PA/policy delivery | Bằng chứng request cụ thể đang được phép |

Một **PDP trả deny nhưng API vẫn tiếp tục ghi dữ liệu** là thất bại của enforcement. Một **gateway trả allow cho token hợp lệ nhưng backend không kiểm tra tenant** là lỗ hổng kiểm soát ở cấp đối tượng. Một **role bị xóa ở IdP nhưng ứng dụng đích vẫn giữ grant trực tiếp** là vấn đề vòng đời và đồng bộ quyền.

### Liên hệ với ba nguyên tắc Zero Trust

- **Verify explicitly:** lấy và xác minh các bằng chứng cần thiết cho quyết định.
- **Least privilege access:** giới hạn action/resource/scope/time mà policy có thể cho phép.
- **Assume breach:** một phần có thể bị chiếm; PEP/PDP, telemetry và thu hồi phải giảm phạm vi thiệt hại.

Thực thi liên tục là **cách đưa các nguyên tắc trên vào đường truy cập thực**, không phải một sản phẩm đơn lẻ.

## 4. Kiến trúc tổng thể: chính sách, danh tính và dữ liệu

Trong mô hình NIST SP 800-207, các vai trò chính gồm:

- **Policy Engine / PDP:** đánh giá có cho phép một subject truy cập một resource theo policy và ngữ cảnh không.
- **Policy Administrator (PA):** hỗ trợ thiết lập hoặc kết thúc đường truy cập/kết nối theo quyết định; không nên nhầm với người quản trị IAM.
- **Policy Enforcement Point (PEP):** kiểm soát đường truy cập, thực thi cho phép hoặc chặn.
- **Nguồn thuộc tính:** IdP, nguồn vòng đời, hệ thống thiết bị/workload, inventory, backend tài nguyên và risk telemetry.
- **Chủ thể:** user, service account, workload, ứng dụng đối tác, job tự động.

~~~mermaid
flowchart TB
    HR["HRIS / hợp đồng / JML"] --> IAM["IAM lifecycle & desired entitlements"]
    IAM --> IDP["IdP / SSO / Workload issuer"]
    IAM --> SCIM["SCIM / provisioning"]
    SCIM --> APPSTATE["Ứng dụng đích: quyền thực tế"]
    IAM --> EVENTS["Event thay đổi quyền / thu hồi"]
    RISK["Device / workload / session risk"] --> ATTR["Nguồn thuộc tính tin cậy"]
    IDP --> ATTR
    IAM --> ATTR
    APPSTATE --> ATTR

    U["Người dùng / workload"] --> PEP["PEP: gateway / API / service"]
    PEP --> PDP["PDP / policy engine"]
    ATTR --> PDP
    RES["Resource metadata: tenant / owner / classification"] --> PDP
    GOV["Policy repository / review / version"] --> PA["Policy administration & rollout"]
    PA --> PDP
    PA --> PEP
    EVENTS --> PDP
    EVENTS --> PEP

    PDP -->|"Permit / Deny / obligations"| PEP
    PEP -->|"Permit sau kiểm tra"| API["Backend / data resource"]
    PEP -->|"Deny / challenge"| STOP["Chặn hoặc yêu cầu điều kiện bổ sung"]
    API --> LOG["Audit / security telemetry"]
    PEP --> LOG
    PDP --> LOG
    LOG --> OPS["Giám sát, điều tra, reconciliation"]
    OPS --> GOV
~~~

**Lưu ý:** sơ đồ là mô hình vai trò, không yêu cầu mọi thành phần là một dịch vụ độc lập. Một hệ thống có thể nhúng policy engine trong backend, có nhiều PEP theo tầng và sử dụng quyết định có cache. Dù triển khai theo kiểu nào, cần bảo đảm **đường tới dữ liệu nhạy cảm không bỏ qua PEP**.

### Hai luồng phải được nối với nhau

**Control plane** xử lý quyết định quản trị: user active hay inactive, quyền nào đáng có, nhóm SCIM nào đã cập nhật, policy version nào được triển khai, phiên nào cần thu hồi.

**Data plane** xử lý request thực: token có hợp lệ không, subject hiện có quyền gì, tài nguyên thuộc tenant nào, action có được thực hiện không, quyết định có được áp dụng trước thao tác thực tế không.

**Thành công của control plane chưa chứng minh data plane đã chặn truy cập.** Một công việc thu hồi chỉ hoàn tất khi các điểm thực thi quan trọng không còn cho phép quyền cũ trong giới hạn SLA đã xác định.

## 5. Mỗi quyết định phải có đầu vào và ý nghĩa rõ ràng

Công thức khái niệm:

**Decision(t) = Evaluate(PolicyVersion(t), SubjectState(t), Action, ResourceState(t), Context(t))**

Ở đây **t** là thời điểm quyết định; thuộc tính có thể đến từ nhiều nguồn với độ trễ khác nhau. Cần biết **nguồn, độ tin cậy và tuổi dữ liệu**.

| Chiều | Ví dụ | Yêu cầu bảo vệ |
|---|---|---|
| **Subject** | usr-123, svc-invoice-sync | Subject ID ổn định, không tin email làm khóa duy nhất |
| **Authentication** | issuer, audience, MFA, auth_time | Chỉ nhận claim/bằng chứng đã xác minh từ issuer tin cậy |
| **Lifecycle** | active, effective role, ngày hợp đồng, JML version | Nguồn authoritative và thời gian hiệu lực rõ |
| **Action** | invoice.read, payment.approve, customer.export | Phân biệt chức năng, không dùng cờ “đã đăng nhập” |
| **Resource** | invoice ID, tenant, owner, classification | Lấy từ backend; không tin giá trị client tự khai |
| **Context** | session age, device/workload posture, risk | Đủ mới, có cơ chế fallback rõ ràng |
| **Governance** | ticket/phê duyệt, SoD, quyền JIT, expiry | Người phê duyệt, phạm vi và hạn dùng được kiểm soát |
| **Policy version** | finance.invoice.read v12 | Truy xuất được policy dùng để ra quyết định |

Một policy có thể dùng **RBAC** để xác nhận vai trò nền tảng, **ABAC** để thu hẹp tenant, loại tài nguyên, môi trường, loại thiết bị và rủi ro. Kiểm tra **quan hệ (ownership, assignee, membership)** có thể cần thiết khi vai trò một mình không xác định được bản ghi nào được truy cập.

### Ví dụ chính sách: đọc hóa đơn và duyệt thanh toán

~~~text
PERMIT invoice.read IF
    subject.status == "active"
    AND subject.hasRole("finance_analyst")
    AND subject.tenantId == resource.tenantId
    AND resource.businessUnit IN subject.allowedBusinessUnits
    AND context.sessionAssurance >= requiredAssurance("invoice.read")
ELSE DENY

PERMIT payment.approve IF
    subject.status == "active"
    AND subject.hasRole("finance_approver")
    AND subject.tenantId == resource.tenantId
    AND subject.id != resource.createdBy
    AND resource.status == "pending_approval"
    AND context.approvalWindowActive
    AND context.stepUpSatisfied
ELSE DENY
~~~

Đây là **pseudocode**, không phải ngôn ngữ policy của một nền tảng cụ thể. Các trường tenant, createdBy và trạng thái giao dịch phải đến từ **nguồn nghiệp vụ đáng tin**, không phải payload user có thể sửa.

## 6. Quyết định Permit, Deny và nghĩa vụ thực thi

PDP có thể hỗ trợ các kết quả khác nhau tùy sản phẩm. Cần hiểu **cách PEP chuyển quyết định thành hành vi**, không mặc định engine nào cũng có chính xác các trạng thái giống nhau.

| Kết quả logic | Ý nghĩa | Trách nhiệm của PEP/ứng dụng |
|---|---|---|
| **Permit / Allow** | Điều kiện được thỏa trong phạm vi quyết định | Chỉ thực thi action/resource/scope được phép; áp dụng obligation |
| **Deny** | Vi phạm một hoặc nhiều điều kiện | Chặn action trước khi có side effect; ghi reason code phù hợp |
| **Challenge / Step-up required** | Mức xác thực hiện tại chưa đủ | Khởi tạo luồng tái xác thực được hỗ trợ, đánh giá lại AuthZ sau khi có bằng chứng mới |
| **Approval required** | Cần phê duyệt nghiệp vụ hoặc JIT elevation | Chuyển workflow; không tự cấp quyền trước khi được duyệt |
| **Indeterminate / Evaluation error** | Không thể đánh giá đủ đáng tin | Không chuyển thành allow mặc định; áp dụng fallback theo rủi ro |
| **Not applicable** | Policy không áp dụng với request | Để cơ chế hợp nhất policy xác định kết quả cuối, thường có deny mặc định theo thiết kế |

**Obligation** là việc PEP phải thực hiện khi cho phép: ghi audit, che trường dữ liệu, hạn chế số bản ghi xuất, giới hạn thời lượng kết nối, yêu cầu thêm phê duyệt hoặc ràng buộc kênh truy cập.

Một lỗi thường gặp là PDP trả **Permit cùng điều kiện “mask PII”**, nhưng API trả dữ liệu chưa che vì chỉ đọc Boolean allow. Khi đó policy đúng trên giấy mà enforcement thất bại.

### Mẫu kết quả có cấu trúc

~~~json
{
  "policy_id": "crm.customer.export",
  "policy_version": 12,
  "decision": "permit",
  "resource_scope": {
    "tenant_id": "tenant-A",
    "dataset_id": "customers-2026"
  },
  "obligations": {
    "max_records": 500,
    "audit_level": "sensitive_export",
    "mask_fields": ["national_id"]
  },
  "decision_valid_until": "2026-11-23T09:05:00Z"
}
~~~

Đây là mẫu để diễn giải khái niệm, không phải schema chuẩn. Ứng dụng phải hiểu rõ **hệ quả khi không thể thực thi obligation**: ví dụ không hỗ trợ che trường được yêu cầu thì phải từ chối hoặc sử dụng đường xử lý đã được phê duyệt, không trả dữ liệu đầy đủ.

## 7. Điểm thực thi chính sách ở đâu?

Thực thi liên tục cần thiết kế **nhiều điểm chặn**, vì một cổng mạng hoặc một màn hình đăng nhập không nhìn thấy toàn bộ thuộc tính nghiệp vụ.

| Vị trí PEP | Làm tốt | Giới hạn cần xử lý |
|---|---|---|
| **IdP / Conditional Access** | Kiểm tra điều kiện trước khi cấp phiên/token | Không tự xử lý ownership của từng record ứng dụng |
| **API Gateway / Zero Trust Proxy** | Xác minh credential, điều phối policy, chặn action ở biên | Có thể không thấy tenant/owner/classification từ database |
| **Backend application** | Kiểm tra action, object, workflow, SoD, tenant | Cần thống nhất, tránh route thiếu kiểm tra |
| **Data layer** | Row/column-level security, scope dữ liệu, chặn truy vấn | Phải ánh xạ subject/tenant chính xác, tránh service account quyền rộng |
| **Service mesh / inter-service layer** | Chứng thực service, policy kết nối, giới hạn đường đi | mTLS hoặc mesh allow không thay AuthZ nghiệp vụ |
| **Secret broker / PAM** | Kiểm tra trước khi cấp credential hoặc quyền đặc biệt | Credential đã cấp có thể tồn tại đến hết hạn nếu thiếu revoke |
| **Message broker / worker** | Kiểm tra producer/consumer, quyền subscription và job action | Job bất đồng bộ cần xác minh lại trước side effect |
| **Storage / object gateway** | Quyền truy cập object và scope bucket/prefix | Signed URL hoặc link đã cấp có vòng đời riêng |

### Không được kiểm tra chỉ ở UI

Ẩn nút “Delete” khỏi màn hình của user không chặn người đó gọi trực tiếp API delete. Backend hoặc điểm thực thi đáng tin phải kiểm tra action. Với GraphQL, kiểm tra cấp query ở gateway có thể không đủ; từng resolver/đối tượng hoặc trường nhạy cảm cần được bảo vệ theo cách phù hợp.

### Tránh bỏ sót đường truy cập phụ

Một tài nguyên có thể truy cập qua REST API, batch job, export worker, admin console, database connection hoặc object-storage pre-signed URL. **Chính sách cần bao phủ tất cả đường có thể gây ra tác dụng tương đương**, không chỉ endpoint phổ biến.

Ví dụ quyền customer.export được chặn tại API chính nhưng user vẫn có thể gọi report-runner dùng token dịch vụ toàn quyền. Đây là lỗi **đường ủy quyền gián tiếp** và phải xử lý bằng principal/scope đúng, kiểm soát job, xác minh người yêu cầu và audit đầy đủ.

## 8. Điểm khác biệt với continuous authentication

**Continuous authentication** tập trung vào việc bằng chứng xác thực/phiên có còn đủ tin cậy: người dùng có cần step-up, phiên có bị chiếm hoặc thiết bị có rủi ro không?

**Continuous policy enforcement** rộng hơn: dù danh tính được xác thực mạnh, một thao tác vẫn phải bị từ chối nếu **role, tenant, trạng thái tài nguyên, policy, SoD hoặc thời hạn grant** không còn cho phép.

Ví dụ nhân viên Finance hoàn thành MFA chống phishing ở 09:00. Đến 09:05, người đó cố duyệt payment do chính mình tạo. Dù mức xác thực còn rất mới, policy SoD phải **deny**. Việc yêu cầu MFA lại không giải quyết xung đột nhiệm vụ.

Một ví dụ khác: tài khoản service A có mTLS hợp lệ nhưng cố đọc dữ liệu tenant B khi chỉ được ủy quyền tenant A. **Kết nối tin cậy không cấp quyền dữ liệu**.

Cần phối hợp AuthN, AuthZ, posture, lifecycle và policy; không gộp thành “trust score” duy nhất rồi mặc định allow khi score cao.

## 9. Sự kiện nào làm quyết định phải thay đổi?

Một hệ thống muốn thực thi liên tục cần **danh sách trigger chính sách**, không chỉ cơ chế kiểm tra request.

| Trigger | Bằng chứng cần cập nhật | Hệ quả mong đợi |
|---|---|---|
| **Joiner** có hiệu lực | User active, role được duyệt, hạn hợp đồng | Chỉ cấp quyền đủ dùng vào thời điểm được phép |
| **Mover** chuyển vai trò | Nhóm, grant, scope, SoD, policy version | Thu hồi quyền cũ, áp dụng quyền mới sau phê duyệt |
| **Leaver**/disable khẩn cấp | Tình trạng subject, phiên, token, tài khoản đích | Chặn đường truy cập liên quan theo SLA |
| Quyền JIT hết hạn | Elevation grant, session, credential | Dừng action đặc quyền dù kết nối đang mở |
| Device/workload posture đổi | Compliance, risk, quarantine, bằng chứng thời gian | Đánh giá lại hành động nhạy cảm |
| Resource đổi owner/tenant | Ownership, classification, trạng thái workflow | Không dùng kết quả authorize cũ cho object mới |
| Policy mới được phát hành | Policy version, mức ưu tiên/deny, obligations | PEP/PDP áp dụng version theo rollout đã định |
| Token/credential bị nghi lộ | Session, secret, revocation, trust state | Chặn hoặc giới hạn theo risk playbook |
| Phê duyệt bị hủy | Approval ID, thời hạn, người phê duyệt | Không cho tiếp tục action phụ thuộc approval |
| Hệ thống policy lỗi | Kết quả không xác định, nguồn thiếu | Không tự mở quyền; dùng fallback đã phê duyệt |

### Dòng thời gian quyền thay đổi

~~~text
08:50  IdP phát hành access token cho nhân viên Sales; hạn đến 10:50.
09:00  HRIS phát sự kiện Mover: người này không còn được export dữ liệu Sales.
09:01  IAM tính quyền mới, gỡ customer.export trong desired entitlements.
09:02  IdP đổi nhóm, publish revocation/policy event.
09:03  Ứng dụng CRM nhận sự kiện, làm mất hiệu lực cache liên quan.
09:04  Token cũ gọi POST /customers/export.
09:04  Backend kiểm quyền hiện tại và action; trả Deny.
09:05  SCIM ứng dụng khác còn chậm, reconciliation tiếp tục xử lý.
~~~

Nếu ứng dụng CRM **không nhận được sự kiện** hoặc chỉ đọc claim role cũ trong JWT, request 09:04 vẫn có thể được cho phép. Do đó cần thiết kế **thu hồi tại PEP hoặc API**, kiểm tra độ trễ và đối soát khi thông điệp bị mất.

## 10. Vòng đời JML phải nối được tới runtime enforcement

### 10.1. Joiner — cấp đúng quyền có điều kiện

Nhà thầu mới được xác minh theo nguồn hợp đồng, có sponsor, dự án, thời điểm bắt đầu và kết thúc. Quy trình:

1. Tạo subject ID và danh tính IdP, thiết lập phương thức xác thực phù hợp.
2. Định nghĩa role chuẩn, resource scope và ngày hết hạn theo yêu cầu công việc.
3. Đồng bộ tài khoản/quyền tới ứng dụng bằng SCIM hoặc API, xác nhận kết quả.
4. Chỉ cho request khi **ngày hiệu lực, trạng thái danh tính, authorization và điều kiện phiên** đều đạt.
5. Kiểm thử thời điểm trước khi hợp đồng bắt đầu và sau khi hết hạn.

Chỉ có user record trong IdP không phải bằng chứng đủ để allow truy cập production.

### 10.2. Mover — thu hồi quyền cũ không chờ hết token

Khi nhân viên đổi từ Support sang Finance:

- Xác định **desired entitlements** mới và các quyền cũ phải gỡ.
- Xử lý role kế thừa, grant trực tiếp, quyền export và phân tách nhiệm vụ.
- Cập nhật IdP/SCIM, ghi nhận app chưa áp dụng và retry/reconciliation.
- Invalidate decision cache liên quan hoặc kiểm tra quyền hiện tại khi cần.
- Kiểm tra các phiên/token còn hạn; dùng cơ chế revoke phù hợp với sản phẩm.
- Gọi thử những action nhạy cảm của vai trò cũ để chứng minh đã deny.
- Chỉ cấp Finance khi có phê duyệt và điều kiện tương ứng, tránh cộng dồn tự động.

**Một Mover có thể vẫn cần quyền cũ trong thời gian chuyển giao**, nhưng phải có phê duyệt, scope nhỏ, SoD được đánh giá, thời hạn và audit. Đó là một grant ngoại lệ có vòng đời, không phải bỏ qua chính sách.

### 10.3. Leaver — ngừng quyền hiệu lực ở mọi đường

Các bước:

1. Nguồn authoritative thông báo mốc kết thúc hoặc quyết định vô hiệu hóa khẩn cấp.
2. IAM/IdP chặn đăng nhập mới và xử lý phiên, refresh token, quyền hiện có.
3. SCIM/API deprovision tài khoản và nhóm ở ứng dụng đích; xử lý thất bại có cảnh báo.
4. Thu hồi hoặc thay API key, PAT, SSH key, certificate, delegation, local account và secret cá nhân.
5. Kiểm kê automation/service account có owner liên quan; chuyển owner hợp lệ hoặc retire.
6. PEP/API áp dụng trạng thái subject không còn active hoặc đường chặn phù hợp.
7. Kiểm thử request bằng credential cũ tại các ứng dụng/tài nguyên quan trọng và xác nhận SLA.

**Disable tại IdP không bảo đảm một JWT tự chứa được API kiểm offline lập tức không còn giá trị.** Cần kết hợp thời hạn token, introspection/tra cứu trạng thái, sự kiện revocation, phiên ứng dụng và đường chặn dữ liệu theo mức rủi ro.

### Ma trận JML và bằng chứng hoàn tất

| Sự kiện | Control plane | Data plane cần quan sát |
|---|---|---|
| Joiner | User/role được phê duyệt, provision thành công | Allow đúng hành động và resource; deny ngoài phạm vi |
| Mover | Diff quyền, SCIM/group update, version mới | Request với role cũ bị deny trong SLA; role mới đúng scope |
| Leaver | Disabled/revoked/deprovisioned | Session, API và đường credential phụ không còn quyền |
| Hết hạn ngoại lệ | Grant JIT/temporary hết hiệu lực | Action cao bị deny kể cả kết nối cũ còn mở |
| Rà soát quyền | Quyết định keep/revoke và owner | Effective permissions phản ánh kết quả rà soát |

## 11. JWT, session và lý do không thể chỉ dựa vào claim cũ

### 11.1. Bằng chứng xác thực và quyền hiện hành khác nhau

Resource server có thể xác minh JWT access token theo:

- Chữ ký và thuật toán dự kiến;
- Issuer tin cậy;
- Audience đúng API;
- Thời hạn exp/nbf;
- Loại token, phạm vi, sender constraints khi có;
- Trạng thái danh tính/phiên và quyền hiện hành theo chính sách;
- Authorization theo action/resource/tenant thực tế.

**ID token của OpenID Connect** phục vụ client xác nhận sự kiện đăng nhập; không dùng mặc định thay access token cho API. **OAuth 2.0 access token** có thể là JWT hoặc opaque; cơ chế xác minh phụ thuộc cách token được cấp và resource server triển khai.

JWT hợp lệ về mặt chữ ký chỉ xác nhận một số claim được phát hành. Nó không tự chứng minh **claim quyền vẫn còn hiện hành sau Mover/Leaver**.

### 11.2. Các cách phản ánh thu hồi

| Cơ chế | Lợi ích | Rủi ro/giới hạn |
|---|---|---|
| Token thời hạn ngắn | Giảm thời gian claim cũ có thể dùng | Không chặn tức thời; refresh flow cần bảo vệ |
| Token introspection | Có thể lấy trạng thái hiện hành từ nguồn phù hợp | Phụ thuộc latency/availability và cache |
| Tra cứu trạng thái subject/quyền | Có thể từ chối theo JML ngay ở API nhạy cảm | Cần nguồn authoritative đủ mới và có fail-safe |
| Event-driven revocation | Thông báo nhanh thay đổi cho PEP/session | Event có thể trễ/mất; cần version, retry và reconciliation |
| Session/token version hoặc deny list | Cho phép chặn phiên đã cấp khi chính sách hỗ trợ | Cần nơi lưu version/thu hồi và cách kiểm ở resource server |
| Sender-constrained token | Giảm khả năng phát lại token bị lấy cắp | Không thay việc kiểm quyền, không bảo đảm posture hiện tại |
| Decision cache có TTL ngắn | Cân bằng hiệu năng và độ mới | Vẫn tồn tại cửa sổ stale, phải giới hạn theo rủi ro |

Không có cơ chế nào là “revoke tức thì mọi token trong mọi hệ thống” nếu ứng dụng đích không tham gia quy trình đó.

## 12. Cache quyết định: hiệu năng và tính nhất quán

Việc yêu cầu mọi microservice truy vấn hàng loạt hệ thống tại mỗi request có thể làm tăng độ trễ và điểm lỗi. Vì vậy policy decision hoặc dữ liệu thuộc tính thường được cache. Đây là tối ưu có điều kiện, không phải giấy phép duy trì quyền vô hạn định.

### Cache key phải phản ánh đối tượng quyết định

Một cache key chỉ gồm user ID là nguy hiểm nếu dùng cùng kết quả cho mọi action/resource. Có thể cần xét:

- Subject/principal và trạng thái phiên;
- Action;
- Resource ID/tenant hoặc phạm vi chính sách được xác định rõ;
- Policy version;
- Entitlement/lifecycle version;
- Các tín hiệu ngữ cảnh liên quan;
- Thời hạn bằng chứng, điều kiện của grant và độ nhạy hành động.

Ví dụ kết quả Permit cho invoice.read ở tenant A không thể tái sử dụng để cho phép payment.approve hoặc invoice.read ở tenant B.

### Những nguyên tắc cho cache

1. **TTL theo rủi ro:** export dữ liệu, secret và quyền admin yêu cầu độ mới cao hơn nội dung ít nhạy cảm.
2. **Không kéo dài quá hiệu lực quyền:** cache hết hạn trước hoặc không muộn hơn grant JIT/ngoại lệ liên quan.
3. **Invalidation theo sự kiện:** JML, policy mới, revoke phiên, device/workload risk có thể vô hiệu các entry.
4. **Versioning:** sự kiện cũ không được phục hồi grant sau revoke mới.
5. **Không chia sẻ nhầm scope:** cache tenant A không được làm nguồn Permit cho tenant B.
6. **Quan sát:** metric stale cache hits, invalidation lag, policy version drift, quyết định gần hết hạn.
7. **Fallback có kiểm soát:** khi PDP không khả dụng, chỉ sử dụng cached Permit nếu policy cho phép rõ với đúng scope và TTL.

### Ví dụ nhận event đến sai thứ tự

~~~text
Sequence 101: user được cấp role crm_exporter đến 09:00.
Sequence 102: role bị thu hồi lúc 09:00.
Network delay: event 102 đến PEP trước event 101.

Nếu PEP áp dụng event cuối cùng nhận được:
    quyền crm_exporter bị cấp lại sai.

Nếu PEP so lifecycleVersion và effectiveAt:
    chỉ trạng thái mới nhất/đúng thời điểm được giữ.
    event cũ bị bỏ qua, tạo audit/cảnh báo nếu cần.
~~~

Tính đúng cần một hợp đồng rõ về **ordering, deduplication, idempotency và authoritative state**. Khi có khoảng trống event, reconciliation chủ động giúp phát hiện mismatch giữa desired state và actual state.

## 13. Chính sách cho kết nối và công việc sống lâu

Một request HTTP ngắn thường dễ chặn trước khi xử lý. Nhưng có nhiều tình huống hành động kéo dài qua sự kiện thu hồi:

- WebSocket hoặc streaming gắn với phiên trong nhiều giờ;
- Job export dữ liệu chạy nền, đã nhận lệnh và tạo file sau 20 phút;
- Workflow duyệt thanh toán nhiều bước;
- Message queue có hàng nghìn sự kiện chờ;
- Connection database hoặc service-to-service tồn tại lâu;
- Pre-signed URL có thời hạn độc lập với phiên SSO.

### Mô hình ranh giới thực thi

| Loại hoạt động | Điểm kiểm tra khuyến nghị | Đường thu hồi cần tính |
|---|---|---|
| Request CRUD | Trước thao tác và ở tầng dữ liệu cần thiết | Request tiếp theo deny; xử lý side effect đang diễn ra |
| WebSocket/streaming | Khi kết nối, tại action/message nhạy cảm hoặc theo policy interval | Đóng/giới hạn kết nối khi revoke/risk event |
| Job export | Khi tạo job, khi worker nhận job, trước khi đọc/xuất file và khi cấp link tải | Hủy job, khóa artifact, làm link hết hiệu lực theo khả năng hệ thống |
| Payment workflow | Khi tạo, chuyển bước và ngay trước commit | Chặn ở bước nhạy cảm nếu role/SoD/approval đổi |
| Message consumer | Khi tiêu thụ, trước thao tác vào resource; không tin toàn bộ message | Dừng consumer hoặc từ chối message sau policy change |
| Secret lease | Trước khi phát hành và trong thời hạn lease | TTL ngắn, rotate/revoke lease khi có sự cố |
| Database session | Khi thiết lập và trước transaction nhạy cảm theo mô hình áp dụng | Kết thúc session hoặc giới hạn quyền hiện hành |

### Ví dụ job export kéo dài

Một nhân viên có quyền export lúc 10:00, gửi yêu cầu tạo job. 10:03, nhân viên bị Leaver; 10:15, worker mới bắt đầu xuất dữ liệu.

Nếu worker chỉ tin “job đã được duyệt lúc 10:00”, dữ liệu vẫn có thể bị xuất dù quyền đã bị thu hồi. Thiết kế cần cân nhắc:

1. Lưu **actor/subject ID, action, resource scope, approval và policy context** khi tạo job.
2. Worker có identity riêng với quyền tối thiểu nhưng **không biến quyền người dùng hết hạn thành quyền vĩnh viễn của service**.
3. Kiểm tra authorization **tại thời điểm thực thi** và trước phát hành artifact, theo ngữ nghĩa đã xác định.
4. Nếu cần hoàn thành một tác vụ không thể hủy sau khi người yêu cầu rời đi, phải có **ủy quyền nghiệp vụ thay thế rõ ràng**, không im lặng dùng quyền cũ.
5. Liên kết artifact/link tải với người nhận còn quyền, hạn sử dụng và khả năng vô hiệu hóa.

Tùy nghiệp vụ, hệ thống có thể đóng băng một quyết định được phê duyệt cho giai đoạn xử lý đã bắt đầu, nhưng cần chính sách minh bạch về **hiệu lực của ủy quyền, phạm vi và điều kiện hủy**, đặc biệt với dữ liệu nhạy cảm.

## 14. Race condition và TOCTOU trong thực thi

**Time-of-check to time-of-use (TOCTOU)** là khoảng giữa lúc hệ thống kiểm tra điều kiện và lúc thao tác thật diễn ra. Nếu resource hoặc quyền thay đổi ở khoảng giữa, quyết định có thể không còn phù hợp.

Ví dụ:

~~~text
10:00:00  API đọc payment: trạng thái pending, creator là B.
10:00:01  PDP quyết định user A được approve.
10:00:02  Payment được sửa/hoán đổi trạng thái bởi một xử lý khác.
10:00:03  API ghi approved dựa vào bản kiểm tra cũ.
~~~

Cách giảm rủi ro phụ thuộc kiến trúc:

- **Kiểm tra lại các điều kiện quyết định tại transaction boundary** cho thao tác không thể đảo ngược.
- Sử dụng optimistic locking hoặc version của resource: chỉ update nếu trạng thái vẫn là pending và version đúng.
- Kết hợp chính sách SoD trong cùng vùng nhất quán với transaction nghiệp vụ khi cần.
- Gắn policy decision với **resource ID, action, version và phạm vi** cụ thể; không cho thay đối tượng sau khi kiểm tra.
- Dùng idempotency key cho thao tác lặp lại nhằm ngăn tạo tác dụng phụ ngoài ý muốn.
- Không mặc định có thể rollback các hiệu ứng bên ngoài như email, webhook hoặc chuyển khoản.

### Pseudocode xử lý thanh toán

~~~java
// Pseudocode Java minh họa, không phải implementation production.
ApprovalResult approvePayment(Principal caller, String paymentId) {
    AccessToken token = tokenVerifier.verify(caller.token(), "finance-api");
    SubjectState subject = iamState.current(token.subjectId());

    return transaction.run(() -> {
        Payment payment = paymentRepo.lockForUpdate(paymentId);
        AuthContext context = trustedContext.from(caller);
        Decision decision = policy.decide(
            subject,
            "payment.approve",
            payment.authorizationAttributes(), // tenant, createdBy, state, version
            context
        );

        audit.recordDecision(subject.id(), paymentId, decision, policy.version());

        if (!decision.isPermit() || !decision.obligationsSatisfied()) {
            throw new AccessDeniedException();
        }

        if (!payment.isPending() || payment.createdBy().equals(subject.id())) {
            throw new AccessDeniedException();
        }

        paymentRepo.markApprovedWithVersion(payment.id(), payment.version());
        return ApprovalResult.approved();
    });
}
~~~

Điểm chính là **giữ kiểm tra trạng thái resource và thực hiện side effect trong cơ chế nhất quán phù hợp**. Nếu policy engine gọi qua mạng trong transaction, cần cân nhắc timeout, lock duration và thiết kế tách bước; không biến pseudocode này thành hướng dẫn luôn phải thực hiện network call khi đang giữ database lock.

## 15. Chính sách dưới dạng mã và vòng đời thay đổi

CPE không thể an toàn nếu policy thay đổi tùy ý hoặc các ứng dụng dùng phiên bản không đồng nhất mà không được theo dõi.

**Policy-as-code** là cách biểu diễn, quản lý thay đổi, kiểm thử và triển khai các quy tắc truy cập bằng artifact có kiểm soát. Công cụ có thể là OPA/Rego, Cedar hoặc cơ chế policy riêng; mỗi hệ thống có cú pháp, mô hình và ngữ nghĩa khác nhau.

### Một vòng đời policy tham chiếu

~~~mermaid
flowchart LR
    A["Yêu cầu nghiệp vụ/rủi ro"] --> B["Thiết kế rule và data contract"]
    B --> C["Review owner + Security + SoD"]
    C --> D["Static/unit tests + deny/allow cases"]
    D --> E["Staging / shadow evaluation"]
    E --> F["Rollout có version và giới hạn phạm vi"]
    F --> G["PEP/PDP áp dụng, metric + audit"]
    G --> H{"Sai lệch / false deny / bypass?"}
    H -->|"Có"| I["Rollback/điều chỉnh có kiểm soát"]
    I --> D
    H -->|"Không"| J["Rà soát định kỳ và theo sự kiện"]
    J --> A
~~~

### Điều kiện cần cho release policy

- **Nguồn sự thật:** policy owner và nơi lưu version chính thức.
- **Review:** người sở hữu tài nguyên, IAM/Security và người kiểm tra xung đột SoD khi cần.
- **Test:** allow đúng; deny sai tenant, sai action, token cũ, quyền hết hạn và posture không đạt.
- **Phân phối:** PEP/PDP nào sử dụng version nào, rollout/rollback được kiểm soát thế nào.
- **Tính tương thích:** cấu trúc subject/resource attributes có thay đổi, client nào chưa hỗ trợ obligation mới.
- **Telemetry:** policy decision và version sau rollout, lỗi evaluation, false deny, sự khác nhau giữa các PEP.
- **Thủ tục khẩn cấp:** phương án rollback/hotfix không mở quyền bừa bãi và có audit.

**Rollback một policy** không có nghĩa được phục hồi các grant đã thu hồi vì Leaver hoặc sự cố. Quy tắc kiểm soát phiên bản policy và trạng thái vòng đời danh tính phải được quản lý tách biệt nhưng phối hợp.

## 16. Xử lý lỗi PDP, IdP và tín hiệu bắt buộc

Một hệ thống liên tục đánh giá điều kiện cần xác định rõ **khi không đánh giá được thì phải làm gì**.

| Lỗi | Rủi ro | Hướng xử lý theo mức nhạy cảm |
|---|---|---|
| PDP timeout | Không có quyết định mới | Không mặc định allow; dùng fail closed hoặc cache đã phê duyệt rất hẹp |
| HR/IAM state không cập nhật | Trạng thái JML stale | Theo dõi lag; với action nhạy cảm cần nguồn quyền còn đủ mới |
| SCIM không cập nhật đích | Actual rights khác desired | Alert, retry, reconciliation, chặn bổ sung nơi có thể |
| Device/workload risk service lỗi | Không biết posture hiện tại | Không chuyển unknown thành healthy; limit/deny hành động cần tín hiệu |
| Policy bundle lỗi | PEP có thể dùng version cũ hoặc không load | Xác thực bundle/version, rollback có kiểm soát, không nới quyền trái policy |
| Event thu hồi bị mất | Quyền cũ vẫn trong cache/phiên | TTL, polling/lookup, reconciliation và kiểm thử chặn |
| Clock skew | TTL hoặc hiệu lực sai | Đồng bộ thời gian, xử lý sai lệch có giới hạn, log timestamp nguồn |
| Audit service lỗi | Mất khả năng điều tra và bằng chứng | Với action nhạy cảm, xác định chính sách fail-safe/queue audit bền vững |

### Fail closed không đồng nghĩa làm hỏng toàn bộ hệ thống

**Fail closed** là tránh cho phép khi không thể xác minh điều kiện bắt buộc. Tuy nhiên, tổ chức có thể phân loại:

- **Action cao:** cấp admin, thay IAM policy, xuất dữ liệu nhạy cảm, duyệt thanh toán → yêu cầu đánh giá đủ bằng chứng; không cho phép nếu thiếu điều kiện bắt buộc.
- **Action thấp:** đọc nội dung công khai hoặc ít nhạy cảm → có thể có mode suy giảm riêng nếu được đánh giá rủi ro và phê duyệt.
- **Nghiệp vụ khẩn cấp:** dùng **break-glass** có danh tính, phạm vi, thời hạn, giám sát và phê duyệt phù hợp, không dùng quyền “allow all” vô hạn.

Cần thử nghiệm failure mode để chính sách vừa **an toàn** vừa có phương án duy trì hoạt động hợp lệ.

## 17. Thực thi liên tục cho service account và workload

Một API call giữa hai service phải kiểm soát **workload identity, quyền tài nguyên và ngữ cảnh runtime**. Không có user đăng nhập không có nghĩa có thể bỏ đánh giá lại.

### Các yếu tố chính

- Workload có **principal riêng** và owner; không dùng một key admin chung cho nhiều job.
- Token/chứng chỉ được cấp qua workload identity federation, issuer phù hợp hoặc cơ chế quản lý bí mật đáng tin; có **audience và lifetime** rõ.
- Quyền **theo action/resource/tenant/environment**, không vì cùng cluster hoặc cùng mạng mà được truy cập mọi dữ liệu.
- Posture runtime hoặc attestations phù hợp có thể làm điều kiện bổ sung với tài nguyên nhạy cảm.
- Khi job bị retire, secret bị lộ, owner thay đổi hoặc phiên bản bị quarantine, cần cơ chế **ngừng cấp credential và chặn credential/quyền còn sử dụng được**.
- Giám sát các principal máy có quyền tạo key, sửa policy, assume role hoặc cấp quyền cho principal khác.

### Phân tách build, deploy và runtime

| Principal | Nhu cầu quyền | Tránh cấp |
|---|---|---|
| CI build | Đọc source và phụ thuộc, ghi artifact | IAM production admin |
| Release signer | Ký/attest artifact theo policy | Credential dùng chung không kiểm soát |
| Deploy job | Cập nhật workload đã phê duyệt trong môi trường cụ thể | Đọc toàn bộ dữ liệu nghiệp vụ |
| Application runtime | Gọi API/dữ liệu cần thiết | Quyền deploy hoặc sửa trust policy |
| Audit collector | Ghi/đọc telemetry được phép | Xóa mọi log hoặc sửa IAM rộng |

Khi kỹ sư Leaver, service do nhóm còn sử dụng cần **chuyển ownership hợp lệ**, không giữ API key cá nhân. Service account có vòng đời riêng: đăng ký, đổi quyền/owner/môi trường, retire. Đây là phép tương tự JML cho danh tính máy, không nhất thiết dùng đúng SCIM hoặc quy trình nhân sự để quản lý instance.

## 18. Audit: chứng minh đã thực thi chứ không chỉ ra quyết định

Để điều tra truy cập và chứng minh SLA thu hồi, cần log được **request, policy version, kết quả PDP, hành vi PEP và trạng thái nguồn bằng chứng**.

### Một bản ghi minh họa

~~~json
{
  "timestamp": "2026-11-23T09:04:11Z",
  "event_type": "policy_enforcement",
  "correlation_id": "req-731a",
  "subject_id": "usr-123",
  "session_ref": "hash-of-session-reference",
  "application": "crm-api",
  "action": "customer.export",
  "resource_type": "customer_dataset",
  "resource_id": "dataset-2026",
  "resource_scope": "tenant-A",
  "subject_lifecycle_version": 48,
  "policy_id": "crm.customer.export",
  "policy_version": 12,
  "decision": "deny",
  "enforcement_action": "blocked_before_export",
  "reason_code": "ROLE_REVOKED",
  "evidence_time": "2026-11-23T09:03:55Z"
}
~~~

Đây là ví dụ cấu trúc, không phải schema chuẩn. **Không ghi access token, refresh token, session cookie, mật khẩu, private key hoặc toàn bộ dữ liệu khách hàng vào log.** Có thể dùng tham chiếu phiên đã xử lý phù hợp, phân quyền xem log, bảo đảm tính toàn vẹn và retention theo quy định.

### Phân biệt quyết định và tác động

Một log PDP “deny” không đủ nếu ứng dụng bỏ qua kết quả và vẫn tạo dữ liệu. Nên quan sát thêm:

- **Enforcement outcome:** blocked/allowed/challenge/obligation_applied.
- **Resource effect:** có bản ghi bị thay đổi, file được phát hành hoặc thông điệp được gửi không.
- **Policy/attribute version:** quyết định dùng trạng thái nào.
- **Nguồn tín hiệu:** tính xác thực và thời điểm lấy.
- **Correlation ID:** liên kết event JML, request và kết quả ở ứng dụng đích.

Với hoạt động nhạy cảm, có thể cần cơ chế audit bền vững hoặc outbox pattern để giảm khoảng trống giữa kết quả thao tác và log, tùy yêu cầu kiến trúc.

## 19. Chỉ số vận hành: đo tính liên tục theo kết quả thực

| Chỉ số | Định nghĩa | Ý nghĩa |
|---|---|---|
| **Enforcement coverage** | Tỷ lệ endpoint/action/tài nguyên nhạy cảm được kiểm soát ở điểm thực thi | Phát hiện đường bypass |
| **Policy version consistency** | Số PEP/PDP còn dùng policy version cũ quá giới hạn | Phát hiện rollout lệch |
| **Revocation latency** | Từ Mover/Leaver/revoke tới lúc API từ chối quyền cũ | Đo hiệu quả chặn quyền tồn dư, p95/p99 |
| **Event-to-enforcement latency** | Từ sự kiện posture/policy tới khi điểm truy cập đổi hành vi | Đo tốc độ phản ứng với rủi ro |
| **Stale-decision exposure** | Số request hoặc thời lượng Permit dựa trên trạng thái vượt freshness limit | Đo rủi ro cache và event lag |
| **Policy evaluation failure rate** | Lỗi PDP, thiếu thuộc tính, timeout, indeterminate | Đo độ ổn định và chất lượng nguồn |
| **Obligation compliance rate** | Tỷ lệ permit kèm obligation được thực thi đầy đủ | Phát hiện lộ dữ liệu dù PDP đúng |
| **Cross-scope deny coverage** | Tỷ lệ bài kiểm thử sai tenant/action được chặn | Đo AuthZ thực ở cấp tài nguyên |
| **False deny / false challenge** | Những lần bị chặn hoặc yêu cầu xác thực không phù hợp sau điều tra | Cân bằng bảo mật và UX |
| **Provisioning drift** | Chênh lệch desired/actual entitlements tại đích | Phát hiện SCIM lỗi và grant trực tiếp |
| **Orphaned privileged identity count** | Principal/key đặc quyền không owner hoặc không còn nghiệp vụ | Giảm đường truy cập tồn dư |

**Không dùng chỉ số “100% request được PDP trả lời” làm bằng chứng duy nhất.** PEP có thể bỏ qua deny, áp dụng sai obligation hoặc backend mở đường khác tới cùng resource. Các bài thử end-to-end phải xác minh kết quả dữ liệu thực.

## 20. Ma trận kiểm thử thực thi chính sách liên tục

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| E1 | User active, đúng role, đúng action, đúng tenant, tín hiệu đủ mới | Permit và thực thi trong scope được phép |
| E2 | Cùng user gọi action không có role | Deny tại backend/PEP |
| E3 | Đúng role nhưng resource thuộc tenant khác | Deny ở cấp object/record |
| E4 | JWT còn hạn chứa role cũ sau Mover | Quyền cũ bị từ chối trong SLA đã định |
| E5 | Leaver còn session ứng dụng cục bộ | Không tiếp tục truy cập theo SLA offboarding |
| E6 | Quyền JIT vừa hết hạn, WebSocket vẫn mở | Action đặc quyền tiếp theo bị chặn/phiên bị giới hạn |
| E7 | PDP trả Permit nhưng yêu cầu mask trường PII | PEP/backend áp dụng mask; không thể mask thì không trả dữ liệu chưa bảo vệ |
| E8 | Policy version mới có deny, một PEP còn cache version cũ | Event/TTL/giám sát phát hiện và chặn trong giới hạn quy định |
| E9 | Sự kiện grant cũ đến sau revoke mới | Không phục hồi quyền do out-of-order |
| E10 | SCIM không xóa được grant ở SaaS | Alert, retry/reconcile; không đánh dấu hoàn tất |
| E11 | PDP timeout khi export dữ liệu nhạy cảm | Fail closed theo chính sách |
| E12 | Mất nguồn posture bắt buộc | Không tự coi unknown là compliant |
| E13 | Job export được tạo trước khi user Leaver, chưa chạy | Kiểm lại quyền trước khi xử lý/phát hành theo policy |
| E14 | Quyền thanh toán bị đổi giữa khi kiểm tra và commit | Không cập nhật dựa vào state cũ; kiểm tra version/transaction |
| E15 | Token dành cho API A được gửi tới API B | Deny vì audience sai |
| E16 | Workload đúng identity nhưng sai resource scope | Deny, dù mTLS hợp lệ |
| E17 | Frontend ẩn chức năng, người dùng gọi API trực tiếp | API vẫn deny nếu không có quyền |
| E18 | Resource có đường phụ qua worker/storage link | Đường phụ cũng bị giới hạn theo policy |
| E19 | Thay đổi policy rollout gây false deny | Phát hiện qua audit/metric, có rollback kiểm soát |
| E20 | Access token/credential cũ sau khi bot retire | Bị chặn ở dịch vụ đích trong SLA |

### Kiểm thử phải quan sát tới data plane

Trong E4 hoặc E5, không chỉ xem dấu tích “revoke thành công” trên bảng quản trị. Cần dùng principal/credential kiểm thử đã được ủy quyền để:

1. Ghi thời điểm Mover/Leaver có hiệu lực và trạng thái quyền trước/sau.
2. Thực hiện request được phép trước đây bằng phiên/token cũ.
3. Xác nhận deny và **không có side effect hoặc dữ liệu lộ**.
4. Kiểm tra log có subject, action, resource, policy version và reason code.
5. Đo thời điểm cuối cùng request còn được allow và thời điểm từ chối ổn định.
6. Thử các đường truy cập phụ: local account, signed URL, job nền, API key và quyền kế thừa.

Các phép thử phải thực hiện trong môi trường và phạm vi có ủy quyền, tránh tác động dữ liệu thật nếu không có kế hoạch kiểm thử được phê duyệt.

## 21. Bài tập tình huống: khi Mover, policy và job export gặp nhau

### Bối cảnh

Doanh nghiệp có IdP/SSO, IAM lifecycle và SCIM quản lý người dùng trên CRM, Finance và Data Lake. Một API Gateway xác minh JWT, mỗi backend có policy engine hoặc gọi PDP. Hệ thống xuất báo cáo dùng queue và worker riêng.

**Dòng thời gian:**

- **08:45:** Nhân viên Trang đăng nhập, nhận access token CRM có hạn đến 10:45 với role support_manager.
- **09:00:** Trang chuyển từ Support sang Finance theo HRIS. Quyền Support không còn hiệu lực, nhưng một grant export cũ tồn tại trực tiếp tại CRM.
- **09:02:** IdP gỡ group Support; SCIM gửi cập nhật tới CRM nhưng nhận lỗi và chưa xử lý xong.
- **09:03:** Chính sách mới v12 yêu cầu quyền export riêng và chỉ cho dữ liệu tenant được phê duyệt. PEP A đã tải v12; PEP B vẫn dùng v11.
- **09:04:** Trang gọi POST /reports/export qua PEP B bằng JWT cũ; job được đưa vào queue.
- **09:06:** Backend báo policy deny với lý do ROLE_REVOKED, nhưng worker export vẫn đang giữ quyền dịch vụ đọc toàn bộ tenant.
- **09:10:** Job được worker lấy ra; dữ liệu có thể được xuất ra object storage và tạo signed URL.
- **09:15:** Security phát hiện sai lệch giữa desired và actual rights; một sự kiện revoke v13 được phát tới hệ thống.
- **09:17:** Event đến PEP B sau event grant v12 do trễ mạng.

### Câu hỏi

1. Chỉ ra tối thiểu **năm điểm kiểm soát** mà quyền đã thu hồi có thể bị bỏ qua.
2. Với request lúc 09:04 và job lúc 09:10, chính sách nên ra quyết định ở đâu?
3. Cần xử lý trường hợp PEP B sử dụng v11 và event đến sai thứ tự thế nào?
4. Phân biệt quyền của **Trang** với quyền kỹ thuật của **worker**; vì sao worker không được tự hợp thức hóa yêu cầu từ user đã mất quyền?
5. Khi phát hiện lỗi, những phiên, grant, credential, cache và artifact nào cần đánh giá?
6. Đề xuất cách kiểm thử và **ba chỉ số** chứng minh sự cố không tái diễn.

### Gợi ý lời giải

**1. Điểm hở:** JWT còn role cũ; SCIM lỗi giữ grant trực tiếp; PEP B dùng policy cũ; gateway/worker không kiểm soát kết quả deny; queue chứa job tạo trước thời điểm kiểm tra; worker có quyền service quá rộng; signed URL có thể cấp quyền tải sau khi user bị thu hồi; event out-of-order có thể phục hồi quyền.

**2. Thời điểm quyết định:** API kiểm tra trước khi enqueue; worker kiểm tra lại **actor, action, resource scope và thời điểm hiệu lực** trước khi đọc dữ liệu, kiểm soát việc tạo artifact và cấp link tải. Nếu công việc được thiết kế tiếp tục theo phê duyệt độc lập của một chủ thể/owner khác, phải có authorization chính thức, không tự lấy role service account làm căn cứ.

**3. Version và event:** kiểm tra policy version được phát hành, đặt giới hạn rollout, giám sát PEP lệch version và vô hiệu cache. Sự kiện mang version/epoch hoặc effective time có nguồn tin cậy; không dùng thứ tự **nhận** làm thứ tự **hiệu lực**. Cần reconciliation để sửa trạng thái thực.

**4. Quyền worker:** service identity chỉ có scope đọc cần thiết để chạy công việc hợp lệ. Nó không tạo quyền nghiệp vụ mới cho Trang. Phải mang actor/authorization context qua queue theo cách chống giả mạo, có thời hạn và được kiểm tra lại.

**5. Khoanh vùng:** thu hồi quyền trực tiếp customer.export, kiểm tra phiên/token CRM, chặn action export nếu cần, vô hiệu grant/cache lỗi thời, xử lý job đang chờ/chạy, kiểm tra artifact/signed URL đã phát hành, rà soát worker service account và các đường truy cập phụ. Giữ audit và mốc thời gian.

**6. Kiểm thử/đo:** replay token cũ sau Mover phải deny; worker nhận job tạo trước revoke phải chặn trước export; event grant cũ không phục hồi quyền mới bị thu hồi; policy version drift được phát hiện. Theo dõi **revocation latency p95**, **policy version consistency** và **số job/artifact được tạo sau khi actor mất quyền**; có thể thêm obligation enforcement rate.

### Bài tập mở rộng

Hệ thống bắt buộc có độ trễ P99 rất thấp và PDP đôi khi mất kết nối. Hãy thiết kế **cache key, TTL, nguồn version và fallback** khác nhau cho hai hành động: xem thông báo chung và xuất danh sách khách hàng nhạy cảm. Giải thích vì sao cùng một chiến lược cache/fail-open không phù hợp cho cả hai.

## 22. Checklist triển khai và tài liệu tham khảo

### Checklist

- [ ] Xác định ranh giới **AuthN, AuthZ, policy decision và enforcement**.
- [ ] Có inventory action/resource nhạy cảm và đường truy cập tương đương: API, batch, queue, database, signed URL, stream.
- [ ] Mỗi policy có subject, action, resource, context, nguồn thuộc tính đáng tin và version rõ ràng.
- [ ] RBAC kết hợp ABAC/quan hệ và SoD khi cần; deny mặc định khi không có quyền.
- [ ] PEP thực sự chặn trước side effect và thực thi obligation như masking, audit, giới hạn dữ liệu.
- [ ] Quyền JML sau Joiner/Mover/Leaver được phản ánh ở data plane trong SLA.
- [ ] Đã đánh giá JWT, refresh token, local session, credential, cache và đường truy cập tồn dư.
- [ ] Quyết định cache đúng scope, action, policy/entitlement version, TTL; có invalidation/reconciliation.
- [ ] Sự kiện đến trễ, trùng hoặc sai thứ tự không thể tái cấp quyền đã thu hồi.
- [ ] Kết nối dài, export job, queue consumer và transaction có điểm kiểm tra phù hợp.
- [ ] Thao tác không thể đảo ngược kiểm tra trạng thái tài nguyên gần thời điểm commit; xử lý TOCTOU.
- [ ] Workload/service account có principal riêng, owner và quyền hẹp; không làm đường vòng cho quyền user hết hạn.
- [ ] Policy-as-code hoặc quy trình tương đương có review, test, rollout, metric, rollback có kiểm soát.
- [ ] PDP/IdP/nguồn posture lỗi có fallback theo rủi ro, không tự allow action nhạy cảm.
- [ ] Audit liên kết event JML → quyết định PDP → kết quả PEP → tác động trên resource.
- [ ] Kiểm thử cross-tenant, quyền sai, token cũ, SCIM lỗi, policy drift, obligation và job bất đồng bộ.
- [ ] Có người chịu trách nhiệm cho revocation latency, policy coverage, lỗi evaluation và false deny.

### Thuật ngữ cần nhớ

| Thuật ngữ | Giải thích |
|---|---|
| **Continuous Policy Enforcement** | Áp dụng và đánh giá lại kiểm soát truy cập ở điểm thực thi khi quyền/ngữ cảnh/chính sách thay đổi |
| **PEP** | Policy Enforcement Point: thành phần chặn/cho phép hoặc áp dụng nghĩa vụ |
| **PDP** | Policy Decision Point: đánh giá policy cho request |
| **PA** | Policy Administrator: quản lý thiết lập/chấm dứt đường truy cập theo mô hình ZTA |
| **Policy-as-code** | Quản lý, kiểm thử, version và phát hành chính sách như artifact có kiểm soát |
| **RBAC / ABAC** | Quyền theo vai trò / quyền theo thuộc tính, tài nguyên và ngữ cảnh |
| **JML** | Joiner–Mover–Leaver: vòng đời từ gia nhập tới đổi vai trò và rời đi |
| **SCIM** | Chuẩn đồng bộ user/group giữa các hệ thống; không thay runtime enforcement |
| **Decision freshness** | Độ mới của dữ liệu và version làm căn cứ quyết định |
| **Revocation latency** | Thời gian từ sự kiện thu hồi đến khi quyền thật sự không còn sử dụng được |
| **Obligation** | Điều kiện PEP/ứng dụng phải thực thi cùng một quyết định Permit |
| **TOCTOU** | Khoảng cách giữa lúc kiểm tra điều kiện và lúc sử dụng tài nguyên |
| **Fail closed** | Không cho phép hành động khi không thể xác minh điều kiện bắt buộc |
| **Residual access** | Quyền, phiên, token hoặc credential còn sử dụng sau khi không còn ủy quyền |

### Tài liệu tham khảo khái niệm

- **NIST SP 800-207 — Zero Trust Architecture:** vai trò PE/PDP, PA, PEP và quyết định truy cập không dựa vào tin cậy ngầm.
- **NIST SP 800-53 — Security and Privacy Controls:** kiểm soát AC, IA, AU, CM và các quy tắc liên quan đến thực thi và audit.
- **NIST SP 800-63 — Digital Identity Guidelines:** xác minh danh tính, xác thực, mức bảo đảm và quản lý phiên.
- **RFC 7643/RFC 7644 — SCIM:** mô hình và giao thức đồng bộ user/group trong vòng đời IAM.
- **OpenID Connect Core / OAuth 2.0:** phân biệt danh tính đăng nhập, access token và ngữ nghĩa resource server.
- **OWASP API Security Top 10:** kiểm tra authorization ở cấp đối tượng/chức năng và đường API.
- **OPA/Rego, Cedar và tài liệu policy engine tương ứng:** tham khảo cách định nghĩa, kiểm thử và triển khai policy; không giả định ngữ nghĩa giống nhau giữa các engine.

**Điểm cốt lõi:** Thực thi chính sách liên tục không dừng ở câu hỏi **“PDP có trả allow không?”** mà phải chứng minh **“ở thời điểm và phạm vi được ủy quyền, PEP có thực sự chỉ cho hành động hợp lệ xảy ra, có phản ứng kịp khi quyền hoặc rủi ro đổi, và không để phiên/token/quyền tồn dư vượt qua lớp kiểm soát không?”**. Đó là cầu nối giữa **IdP, SSO, SCIM, RBAC/ABAC, vòng đời JML và khả năng bảo vệ tài nguyên thực** trong Zero Trust IAM.
