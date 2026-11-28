# Use least privilege: giới hạn quyền trong kiến trúc Zero Trust

Một nhân viên cần đọc báo cáo doanh thu của nhóm mình. Tài khoản được thêm vào nhóm finance-users, nhưng nhóm này lại có quyền đọc mọi báo cáo của toàn công ty, tải dữ liệu khách hàng và truy cập môi trường production. Một service xử lý hóa đơn cũng dùng chung credential với một job phân tích. Khi job bị xâm nhập, kẻ tấn công có thể sử dụng quyền của service để đọc dữ liệu ngoài nhiệm vụ.

Trong cả hai trường hợp, danh tính có thể đã được xác thực đúng. Vấn đề nằm ở **phạm vi quyền lớn hơn mức cần thiết**. Zero Trust yêu cầu đánh giá từng yêu cầu truy cập dựa trên danh tính, tài nguyên, hành động và ngữ cảnh; nguyên tắc **least privilege** giới hạn quyền mà một chủ thể thực sự cần để hoàn thành nhiệm vụ trong phạm vi được phê duyệt.

Trong chương **Zero Trust assurance** của module SECURITY_SECURITY_ASSURANCE, học least privilege không chỉ là tạo role ít quyền. Cần chứng minh rằng quyền được thiết kế đúng, gán cho đúng chủ thể, có phạm vi và thời hạn, được enforcement tại mọi đường truy cập, được rà soát và thu hồi hiệu lực, đồng thời có bằng chứng đủ tin cậy để đánh giá trong suốt vòng đời.

> **Nguyên tắc cốt lõi:** Chỉ cấp quyền cần thiết cho **chủ thể, hành động, tài nguyên, phạm vi và khoảng thời gian** cụ thể. Nếu không xác minh được một điều kiện bắt buộc, quyết định truy cập phải tuân theo hành vi fail-safe đã được phê duyệt. Quyền đã cấp cần được theo dõi và thu hồi khi nhiệm vụ hoặc căn cứ cấp quyền kết thúc.

## 1. Least privilege là gì?

**Least privilege** là nguyên tắc bảo mật theo đó mỗi người dùng, tiến trình, ứng dụng, service account, workload hoặc quản trị viên chỉ được cấp **mức quyền tối thiểu cần thiết** để thực hiện nhiệm vụ được ủy quyền.

Một quyết định quyền tối thiểu cần trả lời:

- **Who:** Chủ thể nào đang yêu cầu truy cập? Danh tính được xác thực từ nguồn nào?
- **What action:** Chủ thể cần đọc, ghi, sửa, xóa, ký, triển khai hay quản trị?
- **Which resource:** Tài nguyên, bản ghi, tenant, project, môi trường hoặc đối tượng nào?
- **Which scope:** Phạm vi dữ liệu và thao tác cụ thể đến đâu?
- **When:** Quyền bắt đầu và kết thúc lúc nào? Có cần cấp tạm thời không?
- **Under what context:** Thiết bị, workload, vị trí mạng, mức rủi ro, trạng thái phiên và approval có đáp ứng policy không?
- **Who approved:** Ai có thẩm quyền phê duyệt và bằng chứng nào hỗ trợ quyết định?
- **How verified:** Enforcement được kiểm tra tại API, database, cloud control plane và các đường gián tiếp như thế nào?

Least privilege áp dụng ở nhiều lớp:

| Chủ thể | Ví dụ quyền tối thiểu |
|---|---|
| Nhân viên hỗ trợ | Chỉ xem ticket được phân công; che dữ liệu nhạy cảm không cần cho hỗ trợ |
| Kế toán | Đọc và đối soát hóa đơn thuộc đơn vị được giao; không tự sửa quyền IAM |
| Quản trị viên database | Thực hiện nhiệm vụ vận hành cụ thể qua tài khoản đặc quyền có thời hạn |
| Backend service | Đọc đúng bảng/bucket và gọi đúng API cần cho chức năng |
| Batch worker | Xử lý đúng queue, tenant và loại job được ủy quyền |
| CI/CD runner | Deploy đúng ứng dụng và môi trường sau điều kiện release được phê duyệt |
| Auditor | Đọc evidence và cấu hình trong phạm vi audit; không có quyền sửa production |
| Break-glass operator | Dùng quyền khẩn cấp theo tình huống, thời hạn, giám sát và hậu kiểm |

### 1.1. Least privilege không chỉ là “ít role”

Một role tên READ_ONLY có thể vẫn đọc toàn bộ PII, bí mật thương mại hoặc dữ liệu của mọi tenant. Một role ADMIN có thể được dùng cho cả thao tác nhỏ như xem trạng thái dịch vụ. Vì vậy tên role không chứng minh mức quyền.

Cần xem **effective permissions**: quyền thực tế sau khi kết hợp group membership, role inheritance, policy, resource ACL, cloud IAM, database grants, token claims, delegation, service account và các đường truy cập gián tiếp.

Ví dụ một user không có quyền DELETE trực tiếp nhưng có quyền gọi API quản trị cho phép tạo job xóa dữ liệu; quyền hiệu lực vẫn có thể dẫn tới hành động xóa. Assurance phải đánh giá cả **đường đạt được hành động**, không chỉ một dòng ACL.

### 1.2. Least privilege và Zero Trust

Zero Trust không mặc định tin cậy chủ thể chỉ vì họ ở trong mạng nội bộ, đã đăng nhập trước đó hoặc thuộc một nhóm quen thuộc. Mỗi yêu cầu cần được đánh giá theo policy phù hợp với tài nguyên và ngữ cảnh.

Least privilege là một nguyên tắc quan trọng để giới hạn hậu quả khi:

- Tài khoản người dùng bị chiếm.
- Thiết bị không còn đáp ứng yêu cầu bảo mật.
- Workload bị xâm nhập.
- Token hoặc session bị đánh cắp.
- Một nhóm hoặc role bị cấu hình sai.
- Quản trị viên thao tác nhầm hoặc lạm dụng quyền.
- Một service trở thành confused deputy cho chủ thể ít quyền hơn.

**Authentication** xác minh danh tính; **authorization** quyết định hành động được phép; **least privilege** giới hạn mức quyền mà quyết định authorization có thể cấp.

## 2. Phân biệt các khái niệm quyền liên quan

| Khái niệm | Ý nghĩa | Câu hỏi assurance |
|---|---|---|
| **Least privilege** | Quyền tối thiểu cần thiết | Chủ thể có nhiều quyền hơn nhiệm vụ không? |
| **Need to know** | Chỉ tiếp cận thông tin cần cho công việc | Có thể xem dữ liệu ngoài phạm vi trách nhiệm không? |
| **Default deny** | Không có rule cho phép thì từ chối | Policy thiếu hoặc không xác định có fail-safe không? |
| **Separation of duties (SoD)** | Phân chia thao tác nhạy cảm cho các vai trò khác nhau | Một người có thể tự khởi tạo, phê duyệt và hoàn tất giao dịch quan trọng không? |
| **Just-in-time (JIT) access** | Cấp quyền khi có nhu cầu, trong khoảng thời gian giới hạn | Quyền có tự hết hạn và được thu hồi hiệu lực không? |
| **Just-enough administration (JEA)** | Chỉ cho phép các thao tác quản trị cần thiết | Admin có shell/toàn quyền khi chỉ cần một thao tác cụ thể không? |
| **Privileged access management (PAM)** | Quản lý tài khoản, phiên và thao tác đặc quyền | Credential, session, approval và audit có được kiểm soát không? |
| **Zero Standing Privilege (ZSP)** | Hạn chế quyền đặc quyền thường trực, cấp theo nhu cầu | Có thể loại bỏ quyền admin dài hạn mà vẫn đáp ứng vận hành không? |
| **Access recertification** | Rà soát và xác nhận quyền còn phù hợp | Owner có xem xét đúng population và quyền hiệu lực không? |
| **Attribute-based access control (ABAC)** | Quyết định dựa trên thuộc tính chủ thể, tài nguyên, hành động và môi trường | Thuộc tính đến từ nguồn nào, có mới và đáng tin không? |

Các khái niệm bổ trợ nhau. JIT giúp giảm thời gian quyền tồn tại; JEA giới hạn thao tác; PAM quản lý phiên và credential; recertification kiểm tra quyền theo kỳ. Không cơ chế nào tự bảo đảm least privilege nếu scope, policy hoặc enforcement sai.

## 3. Vì sao quyền quá rộng tạo rủi ro?

### 3.1. Tăng blast radius

Khi một tài khoản bị chiếm, attacker có thể hành động trong phạm vi quyền của tài khoản đó. Quyền càng rộng, số tài nguyên và loại hành động có thể bị ảnh hưởng càng lớn.

Ví dụ:

- Một tài khoản đọc báo cáo chỉ cần dữ liệu tổng hợp nhưng lại có quyền đọc toàn bộ bảng khách hàng.
- Một worker gửi email được cấp quyền đọc mọi secret trong namespace.
- Một CI runner chỉ cần deploy một service nhưng có quyền cluster-admin.
- Một nhân viên chỉ cần hỗ trợ tenant A nhưng được truy cập tenant B.
- Một tài khoản vận hành có thể sửa log hoặc tắt alert phục vụ kiểm toán.

### 3.2. Rủi ro từ quyền tích lũy

Quyền có thể tăng dần theo thời gian:

- Nhân viên chuyển nhóm nhưng quyền cũ không bị thu hồi.
- Một dự án tạm cấp quyền production rồi quên đóng.
- Group lồng nhau tạo quyền gián tiếp mà reviewer không nhìn thấy.
- Service account được tái sử dụng cho nhiều ứng dụng.
- Role được mở rộng để sửa sự cố rồi không thu hẹp lại.
- Một vendor account còn hoạt động sau khi hợp đồng kết thúc.

Đây là **privilege creep**. Nếu chỉ xem danh sách role trực tiếp, tổ chức có thể bỏ sót quyền kế thừa, quyền từ group, policy và tài khoản phụ.

### 3.3. Quyền quá rộng cũng làm giảm accountability

Khi nhiều người hoặc workload dùng chung một credential, log có thể chỉ ghi một principal chung. Khó xác định ai đã thực hiện thao tác, request thuộc job nào và approval nào hỗ trợ hành động đó.

Least privilege cần đi cùng **identity riêng, traceability và audit**. Shared account có thể làm mất khả năng quy trách nhiệm ngay cả khi quyền của nó được giới hạn.

## 4. Mô hình quyết định truy cập trong Zero Trust

Một mô hình khái niệm có thể gồm:

- **Policy Enforcement Point (PEP):** điểm thực thi cho phép hoặc từ chối request.
- **Policy Decision Point (PDP):** thành phần đánh giá policy.
- **Policy Administrator (PA):** thành phần điều phối cấp hoặc chấm dứt đường truy cập theo kết quả policy.
- **Policy Information Point (PIP):** nguồn thuộc tính/context như identity, device posture, resource classification, risk signals.

Tên gọi và cách phân tách có thể khác giữa các kiến trúc. Điều quan trọng là biết **ai quyết định, ai cung cấp thuộc tính và enforcement nằm ở đâu**.

~~~mermaid
flowchart LR
    S["Subject / Workload"] --> PEP["Policy Enforcement Point"]
    PEP --> PDP["Policy Decision Point"]
    ID["Identity provider"] --> PIP["Policy Information / Context"]
    DEV["Device posture"] --> PIP
    RES["Resource classification"] --> PIP
    RISK["Risk / session signals"] --> PIP
    PIP --> PDP
    PDP --> PA["Policy Administrator"]
    PA --> PEP
    PEP --> R["Protected resource"]
    PDP --> AUD["Decision audit"]
    PEP --> AUD
~~~

### 4.1. Policy phải xét nhiều thuộc tính

Một quyết định không nên chỉ dựa trên user belongs to finance. Có thể cần xét:

- Subject identity và authentication strength.
- Workload identity, service account hoặc client certificate.
- Role, group và delegated permissions.
- Resource owner, tenant, classification và sensitivity.
- Action, method, operation và requested scope.
- Device compliance hoặc workload posture.
- Session age, risk signal, network context.
- Approval, ticket/change reference và thời hạn JIT.
- Trạng thái account, employment, vendor contract hoặc service lifecycle.

Không phải mọi request đều cần tất cả thuộc tính. Policy phải chọn **tập thuộc tính cần thiết và đáng tin** cho risk level; càng thêm tín hiệu càng cần đánh giá freshness, false positives, availability và quyền riêng tư.

### 4.2. Policy decision không đồng nghĩa enforcement

PDP có thể trả PERMIT, nhưng nếu một service khác cho phép truy cập trực tiếp database hoặc object storage thì request có thể bypass PEP. Assurance cần lập bản đồ mọi đường tới tài nguyên và xác minh **PEP không thể bị bỏ qua** trong threat model.

Ví dụ API gateway kiểm tra quyền nhưng database user có quyền đọc toàn bộ schema. Nếu backend có SQL injection hoặc một endpoint khác dùng chung DB credential, giới hạn ở gateway có thể không đủ.

## 5. Xác định quyền tối thiểu theo action và resource

Một quyền nên được mô tả cụ thể hơn là tên role chung.

### 5.1. Mô hình permission

~~~text
Principal : finance-analyst-17
Action    : report.read
Resource  : revenue-report
Scope     : tenant-A / department-3
Context   : managed-device, approved-session
Validity  : 2026-11-28T09:00Z to 2026-11-28T17:00Z
Approval  : ACCESS-REQ-1042
~~~

Đây là ví dụ minh họa. Trong hệ thống thật, principal, scope và context phải được lấy từ nguồn authoritative, còn thời hạn phải được enforcement ở mọi điểm sử dụng quyền.

### 5.2. Resource hierarchy

~~~text
Organization
  ├── Tenant A
  │    ├── Department 1
  │    │    ├── Report X
  │    │    └── Report Y
  │    └── Department 2
  └── Tenant B
       └── Department 3
~~~

Quyền ở cấp Organization có thể kế thừa xuống nhiều tenant. Một policy tưởng như chỉ có một role có thể mở rộng tới hàng nghìn tài nguyên. Cần review **inheritance semantics**, explicit deny/allow precedence và cách xử lý tài nguyên mới được tạo.

### 5.3. Scope càng cụ thể càng tốt, nhưng vẫn vận hành được

Quá rộng: database.read.

Cụ thể hơn: invoice.read trên tenant A.

Cụ thể theo nhiệm vụ: invoice.read cho các hóa đơn thuộc case được phân công, trong thời gian xử lý case.

Tuy nhiên, không nên tạo hàng triệu ACL thủ công nếu policy có thể biểu diễn bằng thuộc tính và relationship. Mục tiêu là **quyền nhỏ nhất có thể quản lý, hiểu và kiểm chứng**, không phải độ phức tạp tối đa.

## 6. RBAC, ABAC và ReBAC

### 6.1. Role-based access control (RBAC)

RBAC cấp quyền qua role. Ví dụ REPORT_READER cho phép đọc báo cáo theo scope được định nghĩa.

Ưu điểm:

- Dễ giải thích và quản trị khi chức năng tương đối ổn định.
- Có thể tích hợp access review, SoD và approval.
- Giúp tránh cấp quyền từng permission rời rạc.

Hạn chế:

- Role có thể phình to và tích lũy quyền.
- Người cùng role có thể cần phạm vi dữ liệu khác nhau.
- Role inheritance/group nesting làm quyền hiệu lực khó nhìn.
- Một role chung có thể không thể hiện tenant, resource hoặc thời hạn.

RBAC cần role engineering, role owner, role mining/review và kiểm tra effective permission.

### 6.2. Attribute-based access control (ABAC)

ABAC quyết định dựa trên thuộc tính subject, resource, action và environment.

~~~text
PERMIT nếu:
  subject.department == resource.department
  AND subject.role contains "REPORT_READER"
  AND subject.accountStatus == "ACTIVE"
  AND resource.classification <= subject.clearance
  AND environment.deviceCompliant == true
  AND request.action == "report.read"
~~~

Ưu điểm là biểu diễn được điều kiện động và phạm vi chi tiết. Hạn chế là phụ thuộc vào **chất lượng thuộc tính**: nguồn, cập nhật, đồng bộ, cách xử lý thiếu giá trị và khả năng giải thích quyết định.

Nếu thuộc tính department bị stale sau khi nhân viên chuyển nhóm, ABAC có thể tiếp tục cấp quyền sai. Nếu deviceCompliant không lấy được, policy phải có hành vi fail-safe đã định nghĩa.

### 6.3. Relationship-based access control (ReBAC)

ReBAC xét mối quan hệ giữa chủ thể và tài nguyên: owner, member, reviewer, assignee, parent-child hoặc delegated relationship.

Ví dụ:

- Người dùng được đọc project khi là thành viên project.
- Nhân viên hỗ trợ chỉ xem ticket đang được assign.
- Quản lý xem báo cáo của nhóm trực thuộc theo quan hệ tổ chức.
- Workload chỉ đọc object thuộc job mà nó đang xử lý.

ReBAC phù hợp khi quyền phụ thuộc đồ thị quan hệ. Cần kiểm soát **ai có thể tạo/sửa relationship**, quan hệ có hết hạn không và thay đổi quan hệ có được phản ánh ngay không.

### 6.4. Kết hợp mô hình

Một hệ thống có thể dùng RBAC để xác định chức năng, ABAC để giới hạn context và ReBAC để xác định mối quan hệ với resource. Không có mô hình nào tự tốt nhất trong mọi trường hợp.

| Use case | Cách kết hợp minh họa |
|---|---|
| Đọc báo cáo | RBAC REPORT_READER + ABAC tenant/department + ReBAC assignment |
| Quản trị cloud | Role operation + JIT approval + device/session context |
| Workload truy cập object | Workload identity + resource attributes + job ownership |
| Hỗ trợ khách hàng | Support role + ticket assignment + field-level masking |
| CI/CD deploy | Pipeline identity + repository/branch/environment attributes + release approval |

## 7. JIT và JEA: cấp quyền đúng lúc, đúng mức

### 7.1. Just-in-time access

JIT giảm quyền đặc quyền thường trực bằng cách cấp quyền trong khoảng thời gian phục vụ một nhiệm vụ cụ thể.

Một request JIT nên ghi:

- Người hoặc workload yêu cầu.
- Resource/action/scope.
- Lý do và ticket/change/incident liên quan.
- Thời gian bắt đầu, hết hạn và giới hạn thời lượng.
- Approver và separation-of-duties check.
- Điều kiện device/session/MFA nếu cần.
- Cách thu hồi và kiểm chứng sau khi hết hạn.
- Audit evidence của request, approval, activation và use.

JIT không đơn giản là thêm một trường expiresAt vào database. **Mọi enforcement point cần thực sự từ chối quyền sau expiry**, và token/session/credential cũ không được tiếp tục giữ quyền ngoài thời hạn theo thiết kế.

### 7.2. Just-enough administration

JEA giới hạn tập thao tác quản trị. Thay vì cấp shell root, một operator có thể được phép:

- Xem trạng thái một service.
- Khởi động lại đúng workload.
- Đọc log đã redacted.
- Chạy một runbook được phê duyệt.
- Thực hiện một migration cụ thể có change approval.

JEA có thể dùng command allowlist hoặc workflow API. Cần xem các command có tham số nguy hiểm, khả năng thực thi shell tùy ý, đường gọi gián tiếp và quyền của process chạy command.

### 7.3. JIT/JEA không loại bỏ nhu cầu review

Một người có thể được cấp quyền tạm thời lặp đi lặp lại, tạo thành quyền thường trực trên thực tế. Cần monitor:

- Tần suất request và thời lượng.
- Cùng một approver phê duyệt cho chính request của mình.
- Request không gắn ticket hoặc không có kết quả công việc.
- Quyền không được thu hồi sau khi hết hạn.
- JIT scope rộng hơn nhiệm vụ.
- Break-glass được dùng thường xuyên.

## 8. Privileged access và PAM

Tài khoản đặc quyền có khả năng thay đổi security controls, truy cập dữ liệu nhạy cảm, quản trị hạ tầng hoặc ảnh hưởng nhiều người dùng.

PAM có thể bao gồm:

- Privileged account inventory và ownership.
- Credential vaulting/rotation.
- JIT/JEA request và approval.
- Session brokering/recording khi phù hợp.
- MFA và device controls.
- Command/action restrictions.
- Audit và alerting.
- Emergency access/break-glass.
- Periodic review và decommission.

### 8.1. Không dùng tài khoản admin cho công việc hàng ngày

Tách tài khoản thường và tài khoản quản trị giúp giảm nguy cơ thao tác đặc quyền do phishing hoặc ứng dụng người dùng bị xâm nhập.

Một quản trị viên có thể dùng tài khoản thường để đọc email và tài khoản riêng để quản trị. Tài khoản đặc quyền chỉ được kích hoạt khi cần và phải có policy phù hợp.

### 8.2. Session management

Với phiên đặc quyền, cần kiểm tra:

- Session có gắn đúng principal, ticket, target và thời hạn?
- Có thể chia sẻ session hoặc chuyển sang tài khoản khác không?
- Credential có bị lộ trong clipboard, terminal history hoặc log?
- Session bị chấm dứt khi approval hết hạn hoặc risk context thay đổi?
- Có thể truy vết command/action tới người thực hiện?
- Session recording có được bảo vệ và retention phù hợp?
- Cơ chế giám sát có làm lộ dữ liệu nhạy cảm ngoài scope không?

Không phải mọi hệ thống đều cần ghi lại toàn bộ màn hình/terminal. Chọn mức giám sát theo rủi ro, mục đích và nghĩa vụ áp dụng.

## 9. Service identities và workload least privilege

Machine identity thường tồn tại lâu, hoạt động tự động và có thể được cấp quyền rộng để giảm lỗi vận hành. Đây là nguồn rủi ro đáng kể trong Zero Trust.

### 9.1. Một workload, một danh tính phù hợp

Không nên dùng chung service account cho các workload có nhiệm vụ khác nhau. Nếu invoice-worker và analytics-worker cùng dùng một credential, khó giới hạn quyền và quy nguồn khi có sự cố.

Mỗi workload cần:

- Owner và purpose.
- Identity riêng theo ứng dụng/môi trường khi phù hợp.
- Credential ngắn hạn hoặc cơ chế federation phù hợp.
- Permission cụ thể cho API, queue, database, storage.
- Tenant/resource scope rõ.
- Rotation/revocation và lifecycle.
- Audit principal và correlation/job ID.

### 9.2. Tránh quyền wildcard

Policy dạng resource * hoặc action * có thể cần trong một số thành phần bootstrap/management rất hẹp, nhưng phải có rationale và kiểm soát đặc biệt. Với runtime workload, nên giới hạn tài nguyên và action cụ thể.

### 9.3. Workload không được tự cấp quyền cho chính nó

Một service có quyền tạo role binding, đổi IAM policy hoặc gắn service account đặc quyền có thể tự nâng quyền. Cần phân tách **runtime identity** và **deployment/admin identity**, bảo vệ control plane và review mọi policy mutation.

## 10. Data-plane và control-plane least privilege

Trong cloud/Kubernetes, cần phân biệt:

- **Control plane:** tạo, sửa, xóa resource, IAM, network policy, deployment, secrets và cấu hình.
- **Data plane:** đọc/ghi dữ liệu thực tế, gọi API, truy cập object, xử lý message.

Một role có quyền control plane có thể gián tiếp lấy quyền data plane, ví dụ sửa workload để gắn service account có quyền đọc bucket. Vì vậy chỉ kiểm tra quyền trực tiếp trên bucket là chưa đủ.

Assurance cần phân tích **privilege escalation paths** từ quyền tạo/sửa workload, policy, secret hoặc pipeline tới dữ liệu và hệ thống đích.

### 10.1. Ví dụ Kubernetes

Một developer không có quyền đọc Kubernetes Secret nhưng có quyền tạo pod trong namespace và gắn service account có quyền đọc Secret. Tùy cấu hình admission/RBAC và workload, developer có thể tạo một đường truy cập gián tiếp.

Cần kiểm tra:

- Ai được tạo/sửa pod và deployment?
- Ai được chỉ định serviceAccountName?
- Ai được tạo RoleBinding/ClusterRoleBinding?
- Ai được exec vào pod hoặc mount host path?
- Ai được đọc secret qua API hoặc qua workload?
- Admission policy có hạn chế privileged container, host namespace và service account không?
- Network policy có ngăn workload không cần thiết truy cập secret service/metadata không?

**Không thể kết luận least privilege chỉ từ RoleBinding.** Quyền của người deploy, admission, service account, node và workload runtime đều có thể tạo đường quyền hiệu lực.

## 11. Quyền kế thừa và privilege graph

Quyền hiệu lực thường đến từ nhiều nguồn:

- Direct role assignment.
- Group membership và nested groups.
- Role inheritance.
- Resource ACL.
- Cloud IAM policies và grants.
- Organization/folder/project hierarchy.
- Service account và workload identity.
- Token claims và delegation.
- API gateway/service mesh policy.
- Database grants, stored procedures và views.
- CI/CD pipeline credentials.
- Emergency access.

### 11.1. Privilege graph

Có thể biểu diễn chủ thể, group, role, policy, resource và action thành một đồ thị. Mỗi cạnh biểu diễn một quan hệ cấp quyền hoặc đường đạt tới quyền.

~~~mermaid
flowchart LR
    U["User A"] --> G["Group: Finance"]
    G --> R["Role: Report Admin"]
    R --> P["Policy: Read / Export"]
    P --> T["Tenant A Reports"]
    P --> X["Tenant B Reports"]
    W["Batch Worker"] --> S["Shared Service Account"]
    S --> DB["All Customer Records"]
    D["Developer"] --> DEP["Deploy permission"]
    DEP --> W
~~~

Trong ví dụ, group finance vô tình có quyền tới Tenant B; shared service account đọc mọi customer record; developer có đường deploy để tác động workload đặc quyền.

### 11.2. Phân tích đường leo thang quyền

Một review cần tìm:

- Chủ thể ít quyền có thể sửa policy/role không?
- Có thể tạo workload với identity đặc quyền không?
- Có thể đọc secret hoặc token của service khác không?
- Có thể thay đổi pipeline để lấy credential production không?
- Có thể sửa resource ownership hoặc tenant mapping không?
- Có thể tắt logging/monitoring trước khi thao tác không?
- Có thể dùng quyền quản trị một thành phần để tác động thành phần khác không?

Các công cụ phân tích IAM/attack paths có thể hỗ trợ, nhưng output cần được xác minh theo **quyền thực tế, điều kiện và khả năng khai thác**. Một cạnh trong graph không phải lúc nào cũng là đường thực thi được; ngược lại, graph thiếu quan hệ có thể bỏ sót đường leo thang.

## 12. Quy trình cấp quyền theo least privilege

Một workflow có thể gồm:

~~~mermaid
flowchart TD
    A["Access request"] --> B["Xác thực requester và business need"]
    B --> C["Xác định resource/action/scope"]
    C --> D["Tính effective permissions và conflict SoD"]
    D --> E["Chọn quyền tối thiểu + thời hạn"]
    E --> F["Approval theo risk/ownership"]
    F --> G{"Được duyệt?"}
    G -- "Không" --> H["DENIED + audit"]
    G -- "Có" --> I["Provision quyền có giới hạn"]
    I --> J["Verify enforcement và expiry"]
    J --> K["Monitor usage / anomaly"]
    K --> L["Expire / revoke / recertify"]
    L --> M["Kiểm chứng effective access đã mất"]
~~~

### 12.1. Request phải mô tả nhiệm vụ

Một request tốt không ghi “cần admin”. Nó nêu:

- Tác vụ cụ thể và lý do.
- Resource/environment/tenant.
- Action cần thực hiện.
- Phạm vi và dữ liệu có thể truy cập.
- Thời hạn.
- Ticket/incident/change reference.
- Người chịu trách nhiệm.
- Biện pháp thay thế ít quyền hơn đã xem xét.

### 12.2. Approval theo rủi ro

Không phải mọi quyền đều cần cùng cấp phê duyệt. Quyền đọc tài liệu nội bộ có thể do resource owner phê duyệt; quyền quản trị IAM, truy cập PII lớn hoặc ký giao dịch có thể cần nhiều cấp, SoD và kiểm tra độc lập.

Approval phải đến từ người có thẩm quyền và không được tự động suy ra từ việc requester thuộc một group.

### 12.3. Provisioning và verification

Sau khi duyệt:

- Gán quyền vào đúng principal/resource.
- Đặt thời hạn và scope.
- Kiểm tra quyền hiệu lực sau khi áp dụng.
- Kiểm tra không phát sinh quyền ngoài dự kiến qua inheritance.
- Ghi approval, policy version, actor và timestamp.
- Kiểm tra expiry/revocation ở đúng enforcement points.

Không coi IAM API trả success là bằng chứng effective permissions đúng; cần đọc lại trạng thái thực và thực hiện negative test phù hợp.

## 13. Revocation: thu hồi quyền hiệu lực

Thu hồi quyền thường phức tạp hơn xóa một dòng assignment. Quyền có thể còn trong:

- Access token hoặc session đã phát hành.
- Cache của policy decision point.
- Group membership đồng bộ trễ.
- Nested group hoặc role inheritance.
- Cloud credentials tạm thời.
- Database connection pool.
- Signed URL hoặc delegated token.
- Service account secret hoặc certificate.
- Long-running job đã lấy quyền trước đó.
- Break-glass session.

### 13.1. Các bước thu hồi

1. Xác định **principal và mọi đường cấp quyền**.
2. Xóa/disable assignment, role, group membership hoặc policy grant có liên quan.
3. Thu hồi hoặc chấm dứt session/token/credential theo cơ chế hỗ trợ.
4. Làm mới cache hoặc policy state nếu cần.
5. Dừng job/session có quyền đang hoạt động khi risk yêu cầu.
6. Kiểm tra access thực tế tại API, database, cloud resource và các đường gián tiếp.
7. Lưu bằng chứng, người thực hiện, thời điểm và kết quả.
8. Theo dõi retry/failure; không đánh dấu hoàn tất khi còn đường truy cập.

### 13.2. Expiry không tự đồng nghĩa revoke

Một grant có expiresAt chỉ có tác dụng nếu mọi enforcement point kiểm tra nó hoặc credential được phát hành có giới hạn phù hợp. Nếu token chứa role và còn hiệu lực sau khi grant bị xóa, hệ thống có thể tiếp tục chấp nhận quyền tới khi token hết hạn hoặc cơ chế revoke được áp dụng.

Cần xác định **revocation latency objective** theo rủi ro và kiến trúc, đo thực tế, và không hứa thu hồi tức thời nếu hệ thống không hỗ trợ.

## 14. Separation of duties và xung đột quyền

Một người có thể có từng permission riêng lẻ hợp lệ nhưng kết hợp lại tạo khả năng gian lận hoặc che giấu hành động.

Ví dụ:

- Người tạo vendor payment đồng thời phê duyệt và giải ngân.
- Người triển khai production đồng thời thay đổi approval policy.
- Người quản trị HSM vừa tạo khóa, tự phê duyệt backup và xóa audit.
- Người yêu cầu quyền JIT cũng tự phê duyệt.
- Người sửa dữ liệu kiểm toán đồng thời có quyền xóa log.

### 14.1. SoD matrix

| Vai trò A | Vai trò B | Xung đột cần xem | Control |
|---|---|---|---|
| Payment creator | Payment approver | Tự tạo và tự duyệt giao dịch | Dual approval |
| Access requester | Access approver | Tự cấp quyền cho mình | Independent approval |
| IAM policy editor | IAM auditor | Tự sửa và tự chứng nhận policy | Separation and immutable audit |
| HSM key custodian | HSM security officer | Một người kiểm soát toàn bộ key ceremony | Dual control/quorum |
| Production deployer | Release approver | Tự triển khai thay đổi chưa duyệt | Protected release workflow |
| Data exporter | Data access reviewer | Tự xác nhận export của mình | Independent review |

Không phải mọi cặp role đều cần cấm tuyệt đối. Cần xác định **toxic combinations**, mức độ rủi ro, ngoại lệ, biện pháp bù đắp và cách giám sát.

### 14.2. SoD không chỉ là role name

Hai role khác tên vẫn có thể tạo cùng một quyền hiệu lực. Ví dụ APPROVER và RELEASE_MANAGER có thể đều gọi được API phê duyệt. Phải kiểm tra **effective actions và quyền kế thừa**, không chỉ đối chiếu nhãn role.

## 15. Break-glass và quyền khẩn cấp

Break-glass là cơ chế truy cập khẩn cấp khi quy trình thông thường không đáp ứng sự cố. Đây là một ngoại lệ có kiểm soát, không phải tài khoản admin dùng hàng ngày.

Một cơ chế break-glass cần:

- Mục đích và tình huống được phép.
- Danh tính riêng, credential bảo vệ và quyền tối thiểu theo tình huống.
- Quy trình kích hoạt và approval theo khả năng vận hành khẩn cấp.
- Thời hạn ngắn, tự động hết hạn hoặc trigger thu hồi.
- Logging/alert độc lập, không để người dùng xóa dấu vết.
- Notification tới owner/security team.
- Hậu kiểm và recertification sau khi sử dụng.
- Kiểm tra định kỳ khả năng sử dụng và khả năng thu hồi.

Có thể có tình huống cần kích hoạt trước khi đủ approver để khôi phục dịch vụ. Khi đó cần **compensating controls**: ghi lý do, giới hạn scope, alert tức thời, review độc lập sau sự kiện và thời hạn rõ. Không nên để emergency account là một đường bypass không audit.

## 16. Least privilege cho dữ liệu và quyền riêng tư

Quyền đọc dữ liệu có thể gây tác động lớn ngay cả khi không thể sửa hoặc xóa. Cần xét:

- Field-level access: nhân viên có cần xem toàn bộ PII không?
- Row-level/tenant-level access: có cần xem mọi record không?
- Purpose limitation: quyền có gắn với mục đích công việc không?
- Export/download: có cần quyền tải hàng loạt không?
- Search: có thể truy vấn mọi cá nhân hoặc chỉ hồ sơ được phân công?
- Logs/analytics: quyền truy cập bản sao dữ liệu có được giới hạn?
- Masking: có thể hiển thị dữ liệu đã che bớt không?
- Retention: quyền truy cập dữ liệu cũ có còn cần thiết?

Ví dụ nhân viên hỗ trợ cần xác nhận email đã che một phần và trạng thái giao hàng, nhưng không cần xem số giấy tờ hoặc dữ liệu thanh toán đầy đủ.

**Read-only không đồng nghĩa low risk.** Đọc, tìm kiếm, export và suy luận có thể tạo ra phơi lộ dữ liệu nghiêm trọng.

## 17. Java 17: đánh giá quyền theo principal, resource và scope

Ví dụ dưới đây minh họa một policy tối giản cho API báo cáo nhiều tenant. Một principal chỉ được đọc báo cáo nếu:

- Principal và resource có dữ liệu hợp lệ.
- Có role REPORT_READER.
- Tenant khớp.
- Resource thuộc department mà principal được phép truy cập.
- Scope là REPORT_READ.

~~~java
import java.util.Objects;
import java.util.Set;

record AccessPrincipal(
        String subject,
        String tenantId,
        Set<String> roles,
        Set<String> departments) {}

record ReportResource(
        String reportId,
        String tenantId,
        String departmentId) {}

enum Permission {
    REPORT_READ,
    REPORT_EXPORT,
    REPORT_DELETE
}

enum Decision {
    PERMIT,
    DENY,
    REVIEW_REQUIRED
}

final class LeastPrivilegePolicy {
    private LeastPrivilegePolicy() {}

    static Decision evaluate(
            AccessPrincipal principal,
            ReportResource resource,
            Permission permission) {

        if (principal == null || resource == null
                || permission == null
                || principal.subject() == null
                || principal.subject().isBlank()
                || principal.tenantId() == null
                || principal.tenantId().isBlank()
                || principal.roles() == null
                || principal.departments() == null
                || resource.reportId() == null
                || resource.reportId().isBlank()
                || resource.tenantId() == null
                || resource.departmentId() == null) {
            return Decision.REVIEW_REQUIRED;
        }

        // Tenant isolation is enforced server-side.
        if (!Objects.equals(
                principal.tenantId(), resource.tenantId())) {
            return Decision.DENY;
        }

        // This policy grants read only, not export or delete.
        if (permission != Permission.REPORT_READ) {
            return Decision.DENY;
        }

        if (!principal.roles().contains("REPORT_READER")
                || !principal.departments().contains(
                        resource.departmentId())) {
            return Decision.DENY;
        }

        return Decision.PERMIT;
    }
}
~~~

**Giới hạn của demo:**

- AccessPrincipal phải được tạo từ identity và entitlement đã xác minh, không lấy trực tiếp từ JSON client.
- departments và tenantId cần nguồn authoritative, cập nhật kịp thời.
- Ví dụ chỉ minh họa một loại resource và action; production cần kiểm soát mọi endpoint, repository, cache, export, batch job và direct storage path.
- REVIEW_REQUIRED phải được xử lý an toàn, không tự động permit.
- Policy này không thay thế authentication, audit, SoD, approval hoặc access recertification.
- Quyền có thời hạn cần được enforcement ở token/session/resource boundary, không chỉ thêm field vào object.

### 17.1. JUnit 5: kiểm thử quyền tối thiểu

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.Set;
import org.junit.jupiter.api.Test;

class LeastPrivilegePolicyTest {
    private static AccessPrincipal analyst(
            String tenant, Set<String> departments) {
        return new AccessPrincipal(
                "analyst-1", tenant,
                Set.of("REPORT_READER"), departments);
    }

    private static ReportResource report(
            String tenant, String department) {
        return new ReportResource(
                "report-42", tenant, department);
    }

    @Test
    void permitsReadWithinAssignedDepartment() {
        assertEquals(Decision.PERMIT,
                LeastPrivilegePolicy.evaluate(
                        analyst("tenant-A", Set.of("finance")),
                        report("tenant-A", "finance"),
                        Permission.REPORT_READ));
    }

    @Test
    void deniesCrossTenantRead() {
        assertEquals(Decision.DENY,
                LeastPrivilegePolicy.evaluate(
                        analyst("tenant-A", Set.of("finance")),
                        report("tenant-B", "finance"),
                        Permission.REPORT_READ));
    }

    @Test
    void deniesDepartmentOutsideAssignment() {
        assertEquals(Decision.DENY,
                LeastPrivilegePolicy.evaluate(
                        analyst("tenant-A", Set.of("finance")),
                        report("tenant-A", "hr"),
                        Permission.REPORT_READ));
    }

    @Test
    void deniesExportAndDeleteForReaderRole() {
        var principal = analyst(
                "tenant-A", Set.of("finance"));

        assertEquals(Decision.DENY,
                LeastPrivilegePolicy.evaluate(
                        principal, report("tenant-A", "finance"),
                        Permission.REPORT_EXPORT));
        assertEquals(Decision.DENY,
                LeastPrivilegePolicy.evaluate(
                        principal, report("tenant-A", "finance"),
                        Permission.REPORT_DELETE));
    }

    @Test
    void deniesMissingRole() {
        var noRole = new AccessPrincipal(
                "analyst-1", "tenant-A",
                Set.of(), Set.of("finance"));

        assertEquals(Decision.DENY,
                LeastPrivilegePolicy.evaluate(
                        noRole, report("tenant-A", "finance"),
                        Permission.REPORT_READ));
    }

    @Test
    void requiresReviewWhenIdentityOrResourceIsIncomplete() {
        assertEquals(Decision.REVIEW_REQUIRED,
                LeastPrivilegePolicy.evaluate(
                        null, report("tenant-A", "finance"),
                        Permission.REPORT_READ));
        assertEquals(Decision.REVIEW_REQUIRED,
                LeastPrivilegePolicy.evaluate(
                        analyst("tenant-A", Set.of("finance")),
                        null, Permission.REPORT_READ));
    }
}
~~~

Unit tests chỉ chứng minh logic của hàm demo. Cần integration tests để xác nhận principal được xây từ token/identity thật, entitlement được đồng bộ, policy được gọi ở mọi route và repository không có đường bypass.

## 18. Policy-as-code và kiểm soát thay đổi quyền

Policy-as-code giúp lưu quy tắc authorization trong dạng có thể version, review, test và deploy có kiểm soát.

Một policy nên có:

- Owner, purpose và phạm vi.
- Subject/resource/action attributes.
- Default decision và precedence.
- Cách xử lý missing/unknown attributes.
- Thời hạn và điều kiện context.
- Test cases positive/negative.
- Version, approver và deployment environment.
- Rollback và audit.

Ví dụ YAML khái niệm:

~~~yaml
policy_id: "REPORT-READ-LEAST-PRIVILEGE"
version: "3"
default_decision: "DENY"
subject:
  required:
    - "verified_identity"
    - "active_account"
    - "tenant_membership"
resource:
  required:
    - "resource_id"
    - "tenant_id"
    - "department_id"
rules:
  - id: "allow-assigned-report-reader"
    effect: "PERMIT"
    actions: ["report.read"]
    conditions:
      - "subject.role contains REPORT_READER"
      - "subject.tenant_id == resource.tenant_id"
      - "subject.department_ids contains resource.department_id"
      - "request.scope == REPORT_READ"
  - id: "deny-export-for-reader"
    effect: "DENY"
    actions: ["report.export", "report.delete"]
    conditions:
      - "subject.role contains REPORT_READER"
exceptions:
  require:
    - "owner"
    - "approval_reference"
    - "scope"
    - "expires_at"
    - "reassessment"
~~~

Đây là cấu trúc minh họa, không phải ngôn ngữ policy chuẩn của một engine cụ thể. Cần xác định **precedence giữa allow/deny**, semantics của group/role, cách xử lý missing claims và cách engine evaluate trong thực tế.

### 18.1. CI checks cho policy

- Syntax/schema validation.
- Unit tests cho policy cases.
- Negative tests cho missing/unknown attributes.
- SoD conflict detection.
- Privilege expansion diff so với version trước.
- Policy review/approval.
- Deployment promotion theo environment.
- Runtime policy version telemetry.
- Drift detection và rollback.

Một thay đổi nhỏ như thêm resource wildcard có thể mở rộng rất nhiều quyền. CI nên tạo **effective permission diff** để reviewer nhìn thấy tác động, không chỉ xem vài dòng YAML.

## 19. Threat modeling cho least privilege

| Threat scenario | Kịch bản | Biện pháp cần đánh giá |
|---|---|---|
| **Credential theft** | Token của analyst bị đánh cắp và dùng để export dữ liệu | Scope hạn chế, short-lived token, step-up và anomaly detection |
| **Privilege escalation** | Developer có quyền deploy workload với service account đặc quyền | Tách deployment/runtime identities, admission policy, review |
| **Group nesting abuse** | User nhận quyền admin qua nested group không được thấy trong review | Effective entitlement graph, group ownership và access review |
| **Stale entitlement** | Nhân viên chuyển nhóm nhưng role cũ còn hiệu lực | JML integration, recertification và revoke verification |
| **Confused deputy** | Service đặc quyền thực hiện yêu cầu vượt quyền của caller | Delegation context, resource-level authorization |
| **Token/session persistence** | Grant đã revoke nhưng token cũ vẫn được chấp nhận | Revocation strategy, token lifetime, session invalidation |
| **JIT approval abuse** | Requester tự duyệt hoặc scope rộng hơn ticket | SoD, approval policy, scope verification |
| **Break-glass misuse** | Tài khoản khẩn cấp được dùng thường xuyên | Alert, expiry, post-event review |
| **Policy bypass** | API gateway kiểm tra nhưng direct database path bỏ qua | PEP inventory, network/DB enforcement, bypass tests |
| **Privilege creep** | Role dần tích lũy quyền sau nhiều ngoại lệ | Permission diff, owner review, expiry |
| **Tenant escape** | Query hoặc cache key thiếu tenant scope | Server-side tenant binding, cross-tenant tests |
| **Audit tampering** | Admin xóa dấu vết thao tác đặc quyền | Immutable/independent audit pipeline, SoD |

### 19.1. Threat model cần bao phủ đường truy cập

Một tài nguyên có thể được truy cập qua:

- Web/API.
- Admin console.
- Direct database connection.
- Object storage URL.
- Queue consumer.
- Batch/ETL job.
- CI/CD pipeline.
- Support tooling.
- Break-glass account.
- Vendor integration.

Nếu chỉ kiểm thử API gateway, các đường khác có thể vẫn vượt least privilege.

## 20. Control mapping: từ risk tới evidence

| Risk ID | Requirement | Control | Assessment / test | Evidence |
|---|---|---|---|---|
| RISK-LP-01: quyền trực tiếp quá rộng | REQ-LP-01: scope theo action/resource/tenant | CTRL-LP-01: fine-grained authorization | Cross-tenant/resource negative tests | Policy/config, test reports |
| RISK-LP-02: quyền kế thừa bị bỏ sót | REQ-LP-02: tính effective permissions | CTRL-LP-02: entitlement graph/review | Nested group/role expansion tests | IAM export, graph, reviewer record |
| RISK-LP-03: privileged standing access | REQ-LP-03: JIT/JEA theo nhiệm vụ | CTRL-LP-03: PAM and time-bound grants | Expiry/revocation/session tests | Request/approval/activation logs |
| RISK-LP-04: service account dùng chung | REQ-LP-04: identity riêng và least privilege | CTRL-LP-04: workload identity controls | Wrong workload/permission tests | Identity registry, IAM policy |
| RISK-LP-05: quyền cũ chưa thu hồi | REQ-LP-05: revoke effective access | CTRL-LP-05: lifecycle/revocation workflow | Token/cache/session negative tests | Revocation records, retest |
| RISK-LP-06: SoD conflict | REQ-LP-06: toxic combinations được ngăn hoặc kiểm soát | CTRL-LP-06: SoD policy | Self-approval/dual-control tests | Role matrix, approval audit |
| RISK-LP-07: bypass PEP | REQ-LP-07: mọi đường truy cập được enforcement | CTRL-LP-07: layered PEP/data-plane controls | Direct DB/storage/queue tests | Network, DB, API policy evidence |
| RISK-LP-08: emergency privilege tồn tại lâu | REQ-LP-08: break-glass có hạn và hậu kiểm | CTRL-LP-08: emergency access governance | Activation/expiry/post-review tests | Emergency logs, review records |

Các ID là ví dụ để học cách traceability. Khi triển khai thật, cần liên kết với risk register, access control standard, IAM policy và control catalogue đã được phê duyệt.

## 21. Kiểm thử least privilege: positive, negative và operational

Một kế hoạch kiểm thử cần chứng minh **quyền cần thiết vẫn hoạt động** và **quyền ngoài scope bị từ chối**.

| Test ID | Tình huống | Kết quả mong đợi | Evidence |
|---|---|---|---|
| TEST-LP-01 | Analyst đọc report đúng tenant/department | Permit | Integration test + decision log |
| TEST-LP-02 | Analyst đọc tenant khác | Deny | Cross-tenant test |
| TEST-LP-03 | Reader cố export/delete | Deny | Action-scope test |
| TEST-LP-04 | Principal thiếu role hoặc inactive | Deny | Identity/role test |
| TEST-LP-05 | Nested group cấp quyền admin ngoài dự kiến | Phát hiện privilege expansion, không tự permit | Effective entitlement report |
| TEST-LP-06 | JIT grant hết hạn | Request mới bị deny tại PEP | Expiry and enforcement test |
| TEST-LP-07 | Grant bị revoke nhưng token/cache còn | Token/session cũ không tiếp tục vượt policy ngoài revocation objective | Revocation latency test |
| TEST-LP-08 | Requester tự phê duyệt quyền đặc quyền | Từ chối theo SoD | Approval workflow test |
| TEST-LP-09 | Service account gọi API ngoài nhiệm vụ | Deny | Workload identity/permission test |
| TEST-LP-10 | Developer tạo pod gắn service account đặc quyền | Admission/RBAC policy chặn hoặc kiểm soát theo approval | Kubernetes negative test |
| TEST-LP-11 | Truy cập database trực tiếp bỏ qua API | Bị chặn bởi DB/network/data-layer controls | Direct-path test |
| TEST-LP-12 | Signed URL đã hết hạn | Không còn truy cập được | Storage access test |
| TEST-LP-13 | Break-glass kích hoạt | Có alert, scope và expiry | Emergency access exercise |
| TEST-LP-14 | Break-glass hết hạn | Quyền bị thu hồi hiệu lực | Effective-access retest |
| TEST-LP-15 | Attribute service lỗi hoặc trả UNKNOWN | Fail-safe theo policy | Failure injection |
| TEST-LP-16 | Resource mới được tạo trong tenant | Không tự nhận quyền rộng ngoài rule | New-resource policy test |
| TEST-LP-17 | Access review phát hiện quyền không còn cần | Revoke và xác minh toàn đường | Review/remediation record |
| TEST-LP-18 | Một quyền được thêm qua policy change | Effective permission diff được review | Policy CI evidence |
| TEST-LP-19 | Cache chứa quyết định PERMIT cũ | Cache invalidation/TTL theo risk objective | Cache/revocation test |
| TEST-LP-20 | Batch job xử lý record ngoài assigned scope | Deny/quarantine và audit | Queue/job integration test |

### 21.1. Kiểm thử không được gây tác động ngoài scope

Các thử nghiệm privilege escalation, break-glass, direct DB access và token replay phải được **ủy quyền, giới hạn trong test environment hoặc tài khoản kiểm thử**, tránh xóa dữ liệu hoặc làm gián đoạn production. Khi cần xác minh production, dùng phương pháp read-only, canary hoặc kiểm tra cấu hình/telemetry có kiểm soát.

### 21.2. Kiểm tra hiệu lực thu hồi

Đo thời gian từ lúc revoke được phê duyệt tới lúc mọi enforcement point từ chối quyền. Ghi rõ:

- Thời điểm revoke request.
- Thời điểm IAM/IdP/policy update.
- Cache/token/session expiry.
- Thời điểm từng API/data store từ chối.
- Các đường chưa thể kiểm tra.
- Mức objective và sai lệch.

Không kết luận revoke hoàn tất chỉ từ trạng thái assignment đã xóa.

## 22. Claim – Argument – Evidence cho least privilege assurance

Một assurance claim cần nêu **đúng chủ thể, tài nguyên, action, scope, environment và kỳ đánh giá**.

| Thành phần | Ví dụ cho báo cáo nhiều tenant |
|---|---|
| **Claim** | Trong release và phạm vi được đánh giá, analyst chỉ đọc được report thuộc tenant/department được giao; các quyền export/delete và truy cập chéo tenant bị từ chối |
| **Argument** | Principal được xác minh; entitlement có nguồn; policy ràng buộc role, tenant, department và action; PEP được áp dụng ở các đường truy cập; quyền được review và revoke |
| **Evidence: identity** | IdP/workload identity config, principal mapping, account lifecycle |
| **Evidence: entitlement** | Effective permission export, group/role graph, resource ACL |
| **Evidence: policy** | Version policy, approval, default deny, rule tests |
| **Evidence: enforcement** | API/DB/storage/network config, direct-path tests |
| **Evidence: lifecycle** | JIT request, approval, expiry, revocation and recertification |
| **Evidence: operation** | Access logs, privileged session records, anomaly alerts |
| **Assumptions** | Identity attributes và resource ownership được cập nhật từ nguồn authoritative |
| **Limitations** | Một vendor support path chưa có runtime evidence; một legacy batch account còn quyền rộng |
| **Conclusion** | PASS/FAIL/INCONCLUSIVE trong scope; residual risk và remediation |

### 22.1. Design, implementation và operating effectiveness

| Mức | Câu hỏi | Evidence |
|---|---|---|
| **Design effectiveness** | Quyền, policy, SoD, JIT/JEA và revocation được thiết kế để giảm risk? | Architecture, role model, access matrix, threat model |
| **Implementation effectiveness** | Các policy và enforcement points được triển khai đúng? | IAM config, PEP inventory, API/DB/storage tests |
| **Operating effectiveness** | Quyền thực tế có được cấp/review/revoke đúng trong kỳ? | Access population, JIT logs, review decisions, revoke samples |
| **Remediation effectiveness** | Finding về quyền dư đã được sửa trên mọi đường? | Effective permission diff, retest, runtime evidence |

Một bảng role được phê duyệt chỉ hỗ trợ design. Muốn kết luận operating effectiveness, cần xem **population request, cấp quyền, usage, expiry, exception và revoke** trong kỳ đánh giá.

## 23. Mẫu least privilege assurance record bằng YAML

Mẫu sau chỉ phục vụ học tập. Placeholder phải được thay bằng evidence reference có thật khi dùng trong tổ chức.

~~~yaml
least_privilege_assurance_id: "LP-ASSURE-003"
module: "SECURITY_SECURITY_ASSURANCE"
scope:
  application: "reporting-platform"
  environment: "production"
  tenant_scope: ["tenant-A"]
  resources: ["revenue-report"]
  assessed_period: "<start-to-end>"
principal:
  type: "human"
  identity_ref: "<verified-principal-reference>"
  owner: "<business-owner>"
  department: "finance"
entitlement:
  role: "REPORT_READER"
  actions: ["report.read"]
  denied_actions: ["report.export", "report.delete"]
  resource_scope: ["department-3"]
  source_policy: "<policy-id-and-version>"
  effective_permission_snapshot: "<evidence-reference>"
lifecycle:
  access_request: "<request-id>"
  approval: "<approver-and-record>"
  valid_from: "<ISO-8601>"
  expires_at: "<ISO-8601>"
  recertification_ref: "<review-record>"
  revocation_test: "<test-reference-or-pending>"
controls:
  - id: "CTRL-LP-01"
    evidence_refs: ["<policy-config>", "<cross-tenant-test>"]
  - id: "CTRL-LP-05"
    evidence_refs: ["<revocation-record>", "<effective-access-retest>"]
  - id: "CTRL-LP-06"
    evidence_refs: ["<SoD-matrix>", "<approval-workflow-test>"]
assessment:
  release: "<release-id>"
  policy_version: "<policy-version>"
  tested_at: "<ISO-8601>"
  tests: ["TEST-LP-02", "TEST-LP-03", "TEST-LP-07"]
  result: "INCONCLUSIVE"
  limitations:
    - "Legacy batch access path not assessed"
findings:
  - "<finding-id-or-none>"
residual_risk:
  owner: "<authorized-risk-owner>"
  decision_ref: "<risk-decision-or-pending>"
reassessment_triggers:
  - "Role, group, tenant, resource or policy change"
  - "Job transfer, termination, incident or privilege escalation finding"
~~~

Không lưu token, password, private key hoặc dữ liệu nhạy cảm trực tiếp trong record. Dùng reference ID tới evidence có kiểm soát truy cập và retention.

## 24. Finding mẫu: quyền đọc toàn tenant qua nested group

Giả định một analyst chỉ cần đọc báo cáo của department 3. Một nested group được thêm vào finance-readers, group này kế thừa role có quyền đọc báo cáo của mọi tenant. Bản access review chỉ hiển thị group trực tiếp nên không phát hiện.

| Trường | Ví dụ |
|---|---|
| **Finding ID** | FND-LP-003 |
| **Criteria** | REQ-LP-02: quyền hiệu lực phải được tính từ direct và inherited entitlements |
| **Condition** | Analyst có quyền đọc Tenant B qua nested group không nằm trong báo cáo review |
| **Evidence** | Group graph, effective permission calculation, cross-tenant test |
| **Risk** | Dữ liệu tenant khác có thể bị truy cập ngoài nhiệm vụ |
| **Root cause cần xác minh** | Access review chỉ kiểm tra direct assignments, không expand inheritance |
| **Owner** | IAM owner và finance application owner |
| **Khắc phục (remediation)** | Thu hẹp nested group, tách role theo tenant/department, cập nhật entitlement review |
| **Verification** | Recompute effective permissions, test truy cập Tenant B bị deny, rà các principal liên quan |
| **Residual risk** | Một số báo cáo legacy có thể dùng shared service account cần đánh giá riêng |

Không đóng finding chỉ vì xóa user khỏi group trực tiếp. Cần tính lại **mọi quyền kế thừa và đường gián tiếp**, kiểm tra token/session/cache và xác minh tại resource thực tế.

## 25. Audit least privilege: population, sampling và evidence

### 25.1. Xác định population đầy đủ

Population không chỉ là danh sách user. Cần xác định trong scope:

- Human identities và guest/vendor accounts.
- Service accounts và workload identities.
- Privileged/admin accounts.
- Roles, groups, nested groups và policy grants.
- Resource ACLs và cloud IAM bindings.
- Temporary/JIT permissions.
- Break-glass accounts/sessions.
- API keys, tokens, certificates và delegated credentials.
- Direct database/storage access.
- Legacy accounts và integration identities.

Đối chiếu inventory với IdP, IAM, cloud, Kubernetes, database, PAM, application logs và deployment pipelines theo phạm vi. Nếu một hệ thống không nằm trong inventory, quyền của nó có thể bị bỏ sót.

### 25.2. Sampling

Ví dụ auditor chọn 25 access grants trong population 300 và phát hiện 4 grant không có owner hoặc justification hiện hành. Kết luận chắc chắn từ mẫu là **4/25 grant đã kiểm tra có sai lệch**. Không suy ra 16% của toàn bộ 300 grant nếu cách chọn mẫu không được thiết kế để hỗ trợ suy rộng thống kê.

Cần lấy mẫu có trọng số rủi ro: admin, export, cross-tenant, production, service accounts và quyền có thể thay đổi policy nên được chú ý hơn.

### 25.3. Evidence quality

| Thuộc tính | Câu hỏi audit |
|---|---|
| **Completeness** | Có đầy đủ direct, inherited, temporary, delegated và service identities không? |
| **Relevance** | Evidence chứng minh quyền nào, action nào và resource scope nào? |
| **Provenance** | Nguồn IAM/IdP, thời gian, policy version và người tạo? |
| **Integrity** | Export/config/log có được bảo vệ khỏi sửa/xóa? |
| **Freshness** | Snapshot có khớp kỳ và runtime hiện tại? |
| **Repeatability** | Có thể tái tính effective permissions và lặp test? |
| **Independence** | Reviewer có độc lập với requester/owner khi cần? |
| **Traceability** | Grant có liên kết request, approval, ticket, expiry và revoke? |

Ảnh chụp role list không đủ nếu không thể thấy nested groups hoặc resource-level permissions. Một access review đã ký không chứng minh reviewer có population đầy đủ.

## 26. Metrics quản trị least privilege

| Metric | Ý nghĩa | Giới hạn |
|---|---|---|
| **Standing privileged account count** | Số tài khoản có quyền đặc quyền thường trực | Phải phân loại service/emergency accounts |
| **JIT adoption** | Mức sử dụng quyền tạm thời cho nhiệm vụ phù hợp | JIT lặp lại có thể thành standing privilege |
| **Expired grant still effective** | Quyền đã hết hạn nhưng còn dùng được | Cần kiểm tra mọi PEP/token/cache |
| **Access review coverage** | Entitlements được review / population thuộc scope | Population thiếu làm tỷ lệ sai lệch |
| **Inherited permission coverage** | Quyền kế thừa đã được expand và review | Cần xử lý graph lớn và stale relationships |
| **Unowned entitlement count** | Quyền không có owner/justification | Mức độ tác động tùy resource/action |
| **Excess privilege findings** | Quyền vượt nhu cầu đã xác định | Cần đo severity và thời gian tồn tại |
| **Revocation latency** | Thời gian từ revoke tới effective deny | Phải tách từng enforcement point |
| **SoD conflict count** | Xung đột quyền chưa được xử lý | Một số exception cần compensating controls |
| **Break-glass usage** | Số lần và phạm vi kích hoạt | Ít sử dụng không chứng minh quy trình sẵn sàng |
| **Direct-path bypass findings** | Đường truy cập bỏ qua PEP | Cần inventory và threat model đầy đủ |

Không báo “least privilege 98%” nếu chưa định nghĩa mẫu số, scope và tiêu chí. Nên tách **quyền được review, quyền thực sự tối thiểu, quyền có thời hạn, revoke hiệu lực và bypass coverage**.

## 27. Governance và trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| **Business/resource owner** | Xác định nhiệm vụ, tài nguyên, scope và nhu cầu quyền |
| **Identity/IAM owner** | Quản lý identity, group, role, policy, provisioning và revocation |
| **Application owner** | Enforce authorization ở API/data layer và duy trì access model |
| **Platform/cloud owner** | Quyền control plane/data plane, workload, network và resource policies |
| **PAM/security operations** | Quản trị privileged credentials, sessions, JIT/JEA và break-glass |
| **Approver** | Xác nhận business need và scope theo thẩm quyền |
| **Access reviewer** | Xác nhận entitlement còn cần, kiểm tra conflict và evidence |
| **Risk owner** | Quyết định residual risk/exception theo thẩm quyền |
| **Auditor/assessor** | Kiểm tra population, controls, evidence và remediation |

Người yêu cầu quyền không nên tự phê duyệt quyền của mình khi policy yêu cầu độc lập. Owner tài nguyên cần xác nhận **need**, còn IAM/platform phải bảo đảm grant được thực thi đúng scope.

## 28. Continuous least privilege assurance

Least privilege cần được duy trì xuyên suốt vòng đời, vì tổ chức, ứng dụng, tenant và workload thay đổi liên tục.

| Giai đoạn | Hoạt động | Evidence |
|---|---|---|
| **Design** | Role/permission model, trust boundary, SoD và JIT design | Architecture, access matrix, threat model |
| **Onboarding** | Cấp quyền ban đầu theo nhiệm vụ | Request, approval, entitlement record |
| **Development** | Policy-as-code, test default deny và resource scope | PR, policy diff, unit/integration tests |
| **Deployment** | Kiểm tra IAM, PEP, DB/storage và workload identity | Runtime config, deployment evidence |
| **Operations** | Monitor access patterns, privilege changes, JIT và break-glass | Logs, alerts, session records |
| **Mover/role change** | Recompute effective permissions, thu hồi quyền cũ | JML event, entitlement diff, revoke test |
| **Offboarding** | Disable identity, token/session, credentials và delegated access | Deprovision record, effective-access test |
| **Recertification** | Owner/reviewer xác nhận quyền còn cần | Review population, decision, remediation |
| **Incident** | Revoke/cô lập, điều tra privilege misuse | Incident record, access timeline, retest |
| **Reassessment** | Đánh giá lại khi resource, policy, trust hoặc business purpose đổi | Updated risk/control/evidence mapping |

### 28.1. Trigger đánh giá lại

- Thay đổi team, role, manager, tenant hoặc hợp đồng vendor.
- Thêm resource, API, action hoặc data class mới.
- Thay đổi group nesting, policy inheritance hoặc IAM hierarchy.
- Thêm workload/service account hoặc pipeline.
- Thay đổi trust boundary, cloud account, cluster hoặc network path.
- Incident, credential theft, privilege escalation hoặc audit finding.
- JIT/break-glass được sử dụng bất thường.
- Revocation không đạt latency objective.
- Resource owner thay đổi hoặc entitlement không còn owner.
- Thay đổi quy định, policy hoặc mức phân loại dữ liệu.

### 28.2. Continuous monitoring không đồng nghĩa giám sát mọi người quá mức

Telemetry nên tập trung vào **quyết định truy cập, thay đổi quyền, hành động đặc quyền, bất thường và trạng thái control**. Cần giảm dữ liệu cá nhân không cần thiết trong logs, giới hạn người truy cập và đặt retention phù hợp.

Zero Trust assurance không phải lý do để thu thập vô hạn hành vi người dùng. Monitoring cũng phải có purpose, scope và governance.

## 29. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai | Cách hiểu phù hợp |
|---|---|---|
| “User đã đăng nhập thì được tin trong mạng nội bộ.” | Authentication không quyết định mọi quyền | Đánh giá từng request theo resource và context |
| “Role READ_ONLY luôn ít rủi ro.” | Có thể đọc toàn bộ dữ liệu nhạy cảm | Đánh giá data scope, export và linkability |
| “Chỉ cần xem direct role assignments.” | Group nesting, inheritance và delegation có thể mở quyền | Tính effective permissions |
| “JIT tự động là least privilege.” | Scope có thể quá rộng hoặc quyền không bị revoke | Kiểm tra purpose, scope, expiry và enforcement |
| “Admin account ít dùng thì an toàn.” | Credential vẫn có thể bị chiếm và quyền vẫn thường trực | PAM, JIT, MFA, monitoring và review |
| “Service account dùng chung tiện quản lý.” | Khó quy nguồn và giới hạn blast radius | Identity riêng theo workload/purpose |
| “Xóa grant là revoke ngay.” | Token, session, cache, signed URL hoặc job còn hiệu lực | Verify effective access trên mọi PEP |
| “Read-only không thể gây hại.” | Đọc/export dữ liệu có thể tạo phơi lộ nghiêm trọng | Least privilege cho read, search và export |
| “SoD chỉ cần tách role name.” | Quyền hiệu lực có thể trùng qua API/group | Phân tích toxic combinations và action paths |
| “Break-glass có password riêng là đủ.” | Có thể tồn tại vô thời hạn và không audit | Scope, expiry, alert, hậu kiểm và retest |
| “PDP deny thì hệ thống đã bảo vệ.” | Có thể có đường bypass PEP/direct data access | Inventory và kiểm thử mọi access paths |
| “Access review hoàn thành nghĩa quyền đã tối thiểu.” | Reviewer có thể không thấy population đầy đủ | Kiểm tra effective entitlement và evidence |
| “Không có alert nghĩa là không lạm dụng.” | Logging/detection có thể thiếu hoặc bị tắt | Kiểm tra telemetry coverage và test alert |
| “Wildcard chỉ là tiện lợi kỹ thuật.” | Có thể mở rộng blast radius rất lớn | Scope cụ thể, rationale và exception |
| “Quyền hết hạn trong database là đã hết hiệu lực.” | Enforcement point có thể không kiểm tra expiry | Test token/session/cache và resource access |
| “Least privilege là cấp càng ít càng tốt.” | Có thể cản trở nhiệm vụ hợp lệ hoặc tạo workaround nguy hiểm | Cấp đủ cho nhiệm vụ, có lý do và kiểm chứng |

## 30. Bài tập tình huống

Một nền tảng SaaS nhiều tenant có các thành phần:

- support-portal cho nhân viên hỗ trợ.
- billing-service xử lý hóa đơn.
- analytics-worker tạo báo cáo.
- Kubernetes và cloud IAM.
- CI/CD pipeline triển khai production.
- PAM cho nhóm vận hành.

Sau một lần audit, phát hiện:

1. Support role có quyền đọc hồ sơ mọi tenant.
2. billing-service và analytics-worker dùng chung service account.
3. Developer có quyền deploy pod với service account đặc quyền.
4. Một grant JIT hết hạn nhưng token còn được chấp nhận.
5. Requester có thể tự approve quyền production.
6. Break-glass account chưa từng được diễn tập và không có alert.
7. Access review chỉ liệt kê direct group membership.
8. API gateway enforce policy nhưng database cho phép kết nối từ subnet rộng.

**Hãy thực hiện:**

1. Xác định ít nhất sáu **effective privilege paths** và mức tác động.
2. Thiết kế RBAC/ABAC/ReBAC cho support, billing và analytics.
3. Tách workload identities và xác định permission tối thiểu cho từng service.
4. Thiết kế JIT/JEA/PAM và SoD cho production access.
5. Đề xuất cách thu hồi token/session/cache và kiểm tra revocation latency.
6. Phân tích quyền control plane có thể dẫn tới data-plane privilege escalation.
7. Xây dựng positive/negative test plan cho direct DB, cross-tenant, expired JIT, self-approval và break-glass.
8. Viết Claim–Argument–Evidence có giới hạn và liệt kê evidence còn thiếu.
9. Xác định owner, remediation và retest cho từng finding.
10. Chọn metrics để theo dõi privilege creep và effective access.

**Gợi ý tự đối chiếu:** không chỉ xóa quyền support đọc mọi tenant; cần kiểm tra API, DB, export và cache. Tách service account giảm shared blast radius. Developer deploy pod đặc quyền là đường control-plane escalation. JIT phải được enforce tại PEP, không chỉ lưu expiry. Approval cần độc lập. Break-glass phải được test và audit. Population access review phải expand inheritance.

## 31. Checklist đánh giá least privilege trong Zero Trust

- [ ] Xác định đầy đủ human identities, service accounts, workload identities, vendors và emergency accounts.
- [ ] Inventory resource, action, scope, environment, tenant và các đường truy cập.
- [ ] Authentication được tách khỏi authorization; danh tính/thuộc tính đến từ nguồn tin cậy.
- [ ] Quyết định truy cập dựa trên subject, action, resource và context phù hợp.
- [ ] Default deny áp dụng khi không có policy cho phép hoặc thuộc tính bắt buộc không xác minh được.
- [ ] RBAC/ABAC/ReBAC được chọn theo use case, có owner và semantics rõ.
- [ ] Effective permissions bao gồm nested groups, inheritance, ACLs, grants, tokens và delegation.
- [ ] Quyền read/search/export/delete được phân biệt theo mức rủi ro.
- [ ] Tenant/resource scope được enforcement ở API, database, storage, queue và batch.
- [ ] Control-plane permissions không tạo đường leo thang ngoài dự kiến tới data plane.
- [ ] Service identity riêng theo workload/purpose; không dùng credential chung tùy tiện.
- [ ] JIT/JEA có request, rationale, scope, approval, expiry và enforcement.
- [ ] PAM quản lý credential/session/recording/rotation theo risk và privacy.
- [ ] Separation of duties ngăn self-approval và toxic combinations.
- [ ] Break-glass có điều kiện kích hoạt, scope, expiry, alert, hậu kiểm và diễn tập.
- [ ] Revocation kiểm tra token, session, cache, group, credential, job và direct access.
- [ ] Recertification có population đầy đủ, reviewer có thẩm quyền và decision trail.
- [ ] Policy-as-code có version, review, negative tests và effective permission diff.
- [ ] PEP không thể bị bypass qua database, object storage, queue, admin tools hoặc legacy path.
- [ ] Monitoring ghi nhận decision và hành động đặc quyền, có integrity/retention và hạn chế dữ liệu không cần.
- [ ] Metrics tách standing privilege, JIT, expiry, review, revocation latency, SoD và bypass.
- [ ] Findings có owner, deadline, root cause, remediation và deployment-linked retest.
- [ ] Assurance claim nêu rõ principal, resource, action, scope, environment, period và limitations.
- [ ] Thay đổi identity, role, resource, workload, policy, tenant hoặc incident kích hoạt reassessment.

**Ghi nhớ:** Least privilege trong Zero Trust là **giới hạn quyền hiệu lực theo đúng chủ thể, hành động, tài nguyên, phạm vi và thời gian**, đồng thời xác minh liên tục rằng các điều kiện ấy vẫn đúng. Trong SECURITY_SECURITY_ASSURANCE, cần chứng minh chuỗi **identity/context → policy decision → enforcement → effective permissions → lifecycle/revocation → monitoring/audit → finding/remediation → reassessment**. Một role có tên “read-only”, một JIT grant hay một access review đã ký không đủ để kết luận quyền thực tế đã tối thiểu; bằng chứng phải bao phủ cả quyền kế thừa, đường truy cập gián tiếp, token/session và các điểm thực thi thực tế.
