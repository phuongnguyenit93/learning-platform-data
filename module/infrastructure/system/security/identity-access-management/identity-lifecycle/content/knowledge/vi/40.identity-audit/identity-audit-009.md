# Audit finding trong IAM: phát hiện kiểm toán, bằng chứng và khắc phục

> **Chương:** Identity audit  
> **Bài:** Audit finding  
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE  
> **Bối cảnh:** Quản lý vòng đời danh tính trong IAM theo **Joiner–Mover–Leaver**, từ xác minh, tạo tài khoản, cấp quyền, thay đổi vai trò đến rà soát và thu hồi. Phân tích liên quan **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và quyền truy cập tồn dư**.

## 1. Audit finding là gì?

Một công ty quy định tài khoản nhân viên phải bị vô hiệu tại các ứng dụng quan trọng trong thời hạn được phê duyệt sau khi người đó nghỉ việc. Khi kiểm tra một mẫu hồ sơ Leaver, auditor thấy ba tài khoản SaaS vẫn hoạt động sau thời điểm phải thu hồi, dù công cụ IAM đã ghi nhận lệnh gửi thành công. Auditor thu thập chính sách, dữ liệu HRIS, lịch sử connector và trạng thái tài khoản tại SaaS để xác định sai lệch, tác động và nguyên nhân.

Kết quả có thể trở thành một **audit finding (phát hiện kiểm toán)**: kết luận được hỗ trợ bởi **tiêu chí kiểm soát, bằng chứng về thực tế và đánh giá rủi ro**, chỉ ra một sai lệch hoặc điểm yếu cần được quản lý, sửa chữa và theo dõi.

**Trong Identity and Access Management (IAM), audit finding** là phát hiện về việc thiết kế hoặc vận hành kiểm soát danh tính/quyền truy cập **không đáp ứng tiêu chí đã xác định**, hoặc có điểm yếu khiến mục tiêu bảo mật, tuân thủ hay vận hành không đạt kỳ vọng.

Audit finding không đơn thuần là cảnh báo SIEM, dòng log bất thường, một screenshot hoặc ý kiến chủ quan. Nó là **một nhận định có khả năng kiểm tra lại**: kiểm soát nào được mong đợi, tình trạng nào được quan sát, bằng chứng nào chứng minh, tác động là gì, nguyên nhân nào được xác định và ai phải giải quyết.

### 1.1. Ví dụ một câu finding đầy đủ

> Theo chính sách deprovisioning nội bộ, tài khoản của nhân viên Leaver thuộc nhóm ứng dụng quan trọng phải được thu hồi trong thời hạn được phê duyệt. Kiểm tra 40 hồ sơ Leaver trong kỳ cho thấy 5 hồ sơ còn quyền tại ít nhất một ứng dụng sau deadline; trong đó 2 hồ sơ có local SaaS role không được workflow SCIM xử lý. Bằng chứng HRIS và target readback hỗ trợ sai lệch; nguyên nhân sơ bộ là inventory thiếu local grants và thiếu đối soát trạng thái quyền thực tế. Rủi ro: quyền truy cập tồn dư có thể bị sử dụng sau khi quan hệ lao động kết thúc. Khuyến nghị: mở rộng inventory, bổ sung revoke/readback cho local grants và xác minh các hồ sơ đang tồn dư.

Con số trên **là tình huống minh họa**, không phải báo cáo kiểm toán của một tổ chức thật.

### 1.2. Mục tiêu học tập

Sau bài học, người đọc có thể:

1. Phân biệt audit finding với observation, event, alert, incident và control deficiency.
2. Viết finding theo **criteria–condition–cause–effect/risk**, có evidence và scope.
3. Thu thập bằng chứng phù hợp từ HRIS, IdP, SCIM, SaaS, cloud IAM và access review.
4. Đánh giá severity theo mức rủi ro, quyền đặc biệt và khả năng kiểm soát.
5. Xác định root cause và viết corrective action plan có owner, deadline, tiêu chí hoàn tất.
6. Quản lý exceptions, compensating controls và residual risk minh bạch.
7. Re-test và chỉ đóng finding khi có bằng chứng khắc phục đủ phạm vi.
8. Đo xu hướng finding, overdue, repeated findings và hiệu lực kiểm soát theo vòng đời IAM.

## 2. Audit finding khác alert, observation và incident

Các khái niệm có liên quan nhưng không thể dùng thay nhau.

| Khái niệm | Ý nghĩa | Ví dụ IAM |
|---|---|---|
| **Log event** | Bản ghi một hành động hoặc thay đổi | SCIM PATCH group membership nhận HTTP 204 |
| **Alert** | Tín hiệu cần xem xét theo rule | Một quyền privileged vẫn active sau cutoff |
| **Observation** | Điều kiểm tra viên ghi nhận ban đầu | Có account chưa thấy bằng chứng revoke |
| **Exception** | Trường hợp không đáp ứng rule hoặc được chấp thuận khác biệt | Giữ một account tạm thời theo phê duyệt |
| **Control deficiency** | Khiếm khuyết trong thiết kế/vận hành kiểm soát | Không đối chiếu local grants khi Leaver |
| **Audit finding** | Kết luận có tiêu chí, bằng chứng, mức độ và yêu cầu xử lý | 5/40 Leaver hồ sơ thu hồi quá hạn do thiếu inventory |
| **Security incident** | Sự kiện làm tổn hại hoặc có khả năng tổn hại an ninh cần ứng phó | Tài khoản Leaver thực hiện export trái phép |
| **Risk acceptance** | Quyết định quản trị chấp nhận rủi ro còn lại theo thẩm quyền | Chấp thuận ngoại lệ có thời hạn và biện pháp bù trừ |
| **Corrective action** | Hành động giải quyết nguyên nhân/điểm yếu | Bổ sung connector, đối soát tự động, kiểm thử |
| **Follow-up / retest** | Kiểm tra khắc phục đã có hiệu lực | Chạy Leaver test và target readback trên các hệ thống |

### 2.1. Alert chưa chắc là finding

SIEM báo “privileged login sau 18:00” chỉ là tín hiệu; có thể là ca trực được phê duyệt. Muốn kết luận finding phải so với tiêu chí có hiệu lực, identity/role scope và bằng chứng. Không ghi “vi phạm” chỉ dựa trên dấu hiệu chưa xác minh.

### 2.2. Finding không đồng nghĩa có attacker

Một lỗi cấp quyền quá rộng có thể chưa bị khai thác nhưng vẫn là finding đáng xử lý. Ngược lại, khi có bằng chứng truy cập trái phép, phải khởi động **incident response** tương ứng; không để quy trình kiểm toán chậm trễ xử lý sự cố đang diễn ra.

### 2.3. Observation có thể chuyển thành finding sau xác minh

Ví dụ auditor thấy user.status=ACTIVE nhưng chưa biết account thuộc service account được phê duyệt hay nhân viên Leaver. Cần kiểm tra identity mapping, loại account và scope trước khi lập finding chính thức.

### 2.4. Risk acceptance không biến lỗi thành “không có finding”

Một risk owner có thể chấp nhận ngoại lệ theo chính sách, nhưng lịch sử finding, bằng chứng, thời hạn và trách nhiệm phải được lưu. Không xóa finding khỏi báo cáo chỉ vì chưa thể sửa ngay.

## 3. Bộ khung chuẩn để viết một Audit finding

Một finding IAM có thể theo cấu trúc **5C** hoặc biến thể tương tự:

| Thành phần | Câu hỏi cần trả lời | Nội dung minh họa |
|---|---|---|
| **Criteria (tiêu chí)** | Điều gì phải đúng, và dựa trên nguồn nào? | Policy yêu cầu revoke Leaver trước deadline |
| **Condition (thực trạng)** | Điều gì thực tế không đạt? | 5/40 account còn active quá hạn |
| **Cause (nguyên nhân)** | Vì sao sai lệch xảy ra? | Connector không quản lý local roles |
| **Consequence/Effect (tác động)** | Sai lệch gây hậu quả hoặc rủi ro gì? | Residual access sau Leaver |
| **Corrective action (khắc phục)** | Cần làm gì, ai làm, khi nào và cách chứng minh? | Mở inventory, thu hồi grants, readback, test |

Có thể bổ sung **scope, period, sample method, criteria version, severity, evidence references, control owner, management response, residual risk và verification plan**.

### 3.1. Criteria phải là tiêu chí có thẩm quyền

Nguồn tiêu chí có thể là:

- Chính sách IAM/JML, Access Control hoặc quy trình deprovision được phê duyệt.
- Yêu cầu contract, regulatory hoặc compliance thực sự áp dụng cho tổ chức.
- Security architecture/policy được công bố có version và effective date.
- Cam kết SLA/SLO được quản trị, ví dụ thời hạn thu hồi privilege.
- Yêu cầu hệ thống như SoD, least privilege, MFA, access recertification.
- Internal control design được owner phê duyệt.

**Không tự bịa một yêu cầu pháp lý hoặc mặc định mọi công ty phải thu hồi trong 24 giờ.** Nếu tổ chức chưa có chính sách xác định, finding có thể liên quan **thiếu tiêu chí/quy trình quản trị** thay vì gán vi phạm một SLA không tồn tại.

### 3.2. Condition cần dữ liệu kiểm chứng được

Không viết “nhiều tài khoản có vấn đề” nếu có thể xác định **bao nhiêu account trong mẫu nào, tại hệ thống nào, vượt ngưỡng bao lâu**. Kết luận cần phù hợp bằng chứng; nếu chỉ kiểm tra mẫu 40 trên quần thể 400, không suy 5 lỗi nghĩa là 50 lỗi cho toàn tổ chức mà thiếu phương pháp thống kê hợp lệ.

### 3.3. Cause không nên là suy đoán

“Tại người dùng bất cẩn” thường không giải thích cơ chế. Cần tìm hiểu source mapping, approval design, SCIM capability, retry/race, owner assignment, configuration drift, risk acceptance và review process.

Nếu chưa kiểm chứng được nguyên nhân, ghi **“nguyên nhân đang được xác minh”**, không gắn lời khẳng định thiếu chứng cứ. Có thể nêu contributing factors riêng.

### 3.4. Effect phân biệt thực tế và tiềm tàng

- **Observed impact:** đã có bằng chứng privileged action sau termination.
- **Potential risk:** local role còn active có thể cho phép truy cập trái chính sách, nhưng chưa thấy misuse.

Không viết “dữ liệu đã bị đánh cắp” chỉ vì có quyền tồn dư mà không có evidence exfiltration.

### 3.5. Corrective action phải có thể xác minh

“Nhắc các đội tuân thủ tốt hơn” thường không đủ. Một plan tốt có:

- Scope: target connectors, user cohorts, grants.
- Fix ngay: thu hồi những quyền tồn dư đã biết.
- Fix gốc: bổ sung inventory, desired-state checks, reviewer ownership.
- Owner và approver.
- Due date/SLA và dependency.
- Evidence requirements.
- Retest methodology và acceptance criteria.
- Biện pháp giảm rủi ro tạm thời đến khi fix.

## 4. Quy trình tạo Finding từ kiểm tra thực tế

~~~mermaid
flowchart TD
    A[Audit Scope & Criteria] --> B[Collect Evidence]
    B --> C[Validate Source, Identity & Completeness]
    C --> D{Does condition depart from criteria?}
    D -- Không --> E[Document Tested Control / No Finding]
    D -- Có --> F[Draft Observation]
    F --> G[Confirm Facts with Control Owner]
    G --> H[Root Cause & Risk Assessment]
    H --> I[Formal Finding & Management Response]
    I --> J[Corrective Action Plan]
    J --> K[Implement & Preserve Evidence]
    K --> L[Independent Retest]
    L --> M{Criteria Met and Residual Risk addressed?}
    M -- Chưa --> N[OPEN / PARTIAL / ESCALATED]
    N --> J
    M -- Có --> O[VERIFIED_CLOSED]
~~~

Quy trình có thể khác giữa internal audit, second-line compliance, external audit hoặc engineering control assessment. **Sự xác nhận của owner không thay thế chứng cứ độc lập** khi finding yêu cầu kiểm tra lại.

### 4.1. Xác định audit universe

Trước khi chọn mẫu, phải biết quần thể:

- Workforce identities: employees, contractors, guests, partners.
- Non-human identities: service principals, workloads, integrations, robots.
- Targets: IdP, SaaS, source control, cloud, databases, PAM, legacy systems.
- Grants: group-derived, direct roles, ACL, delegation, session/token paths.
- Events: Joiner, Mover, Leaver, request/approval, recertification, exception.
- Kỳ: event effectiveAt, policy version, target system version.

Nếu audit universe thiếu direct grants và accounts local, finding “không có sai lệch” trên quần thể không đầy đủ cũng có thể gây hiểu nhầm.

### 4.2. Chọn kiểm soát và expected behavior

Ví dụ:

~~~text
Control ID: IAM-JML-LEAVER-07
Objective: Chặn quyền truy cập của Leaver theo approved cutoff
Trigger: HRIS Leaver event hợp lệ
Scope: IdP + critical SaaS + cloud IAM
Evidence: lifecycle event, command history, target readback
Exception: Có phê duyệt và thời hạn rõ
~~~

Đây là **control minh họa**, không phải yêu cầu chung hoặc ID chuẩn bên ngoài.

### 4.3. Thu thập và đối chiếu evidence

Không chỉ đọc log IAM; cần target readback khi kết luận về quyền hiệu lực. Nguồn evidence phải có provenance, timestamp, identity mapping, tenant scope, người/công cụ thu thập và tình trạng dữ liệu.

### 4.4. Trao đổi với management

Gửi observation để owner xác nhận facts, business context, target capability và exceptions. Management có thể cung cấp bằng chứng phản biện. Auditor cần đánh giá độc lập, sửa kết luận nếu evidence mới hợp lệ, tránh ép dữ liệu vào finding dự kiến.

### 4.5. Phân loại và theo dõi

Ghi severity/risk owner, corrective action, dueAt, status, retest results và next review date. Khi sự cố tức thời được nhận diện, đồng thời dùng incident workflow mà không đợi kỳ audit kết thúc.

## 5. Phạm vi Audit finding trong vòng đời danh tính

Một finding thường thuộc một hoặc nhiều nhóm:

| Miền | Mẫu sai lệch | Bằng chứng thường cần |
|---|---|---|
| **Identity enrollment** | Account được tạo không có xác minh/sponsor | Request, HRIS/contract, approval |
| **Joiner provisioning** | User có quyền trước ngày hiệu lực | EffectiveAt, target grant, policy |
| **Mover** | Role cũ không bị gỡ sau đổi nhiệm vụ | Before/after grants, effective role |
| **Leaver** | Account/session vẫn active quá hạn | HRIS, IdP, target readback, access logs |
| **Access request** | Quyền được cấp thiếu approval | Ticket, approval, grant log |
| **Role design** | Role quá rộng hoặc xung đột | RBAC/ABAC policy, permissions, SoD |
| **Access recertification** | Reviewer auto-KEEP, thiếu owner | Campaign snapshot, reviewer decisions |
| **Privileged access** | Admin role standing, không JIT/approval | PAM/IAM binding, activation |
| **Non-human identity** | Service principal orphan, key dài hạn | Registry, owner, role, credential |
| **Federation/SSO** | Mapping sai principal/group, MFA thiếu | IdP policy, token claims, RP config |
| **Session management** | Session không revoke theo Leaver | IdP/RP sessions, resource access |
| **Logging/audit** | Không có target evidence hoặc log bị mất | Event trace, pipeline health |
| **Exception governance** | Exception quá hạn không reassess | Exception register, owner, expiry |
| **Segregation of Duties** | Một actor tự request, approve và grant | Approval/role/event history |

### 5.1. Một phát hiện có thể liên quan nhiều kiểm soát

Một Leaver còn cloud-admin có thể do HRIS event đến muộn, connector bỏ sót IAM binding và target không hỗ trợ revoke token tức thời. Nên phân biệt **finding chính**, **contributing control deficiencies** và các hành động khắc phục để tránh tạo nhiều ticket trùng mà không ai chịu trách nhiệm toàn bộ.

### 5.2. Không ép mọi vấn đề thành “user management”

Một principal phi con người không có hợp đồng nhân sự. Nếu workload vẫn còn quyền sau khi service decommission, finding nên bám **service lifecycle and ownership**, không giả vờ có HRIS Leaver event.

## 6. Evidence: thế nào là đủ, đúng và có thể tái hiện?

**Bằng chứng kiểm toán** phải liên quan trực tiếp đến tiêu chí, đủ tin cậy và có phạm vi/thời điểm rõ ràng. Dữ liệu trích xuất cần cho phép người kiểm tra khác hiểu kết luận.

### 6.1. Nhóm nguồn evidence phổ biến

| Nguồn | Chứng minh được điều gì | Hạn chế |
|---|---|---|
| **HRIS/contract events** | Trạng thái/biến động nhân sự và cutoff | Không chứng minh target đã revoke |
| **IdP logs** | Identity status, authentication, group membership | Không bao phủ local SaaS role |
| **SCIM operation logs** | Request/response tới User/Group | HTTP ACK không thay effective access |
| **Target readback** | Account/grant state tại hệ thống đích | Có thể stale hoặc thiếu session view |
| **Cloud IAM inventory** | Principal/role/policy bindings | Không tự xác định token/session cũ |
| **PAM records** | Privileged activation, session lifecycle | Không bao phủ mọi local admin |
| **Access review records** | Decision, reviewer, justification | Quyết định REVOKE không chứng minh remediation |
| **Application/API audit logs** | Resource actions thực tế | Có thể thiếu coverage/retention |
| **Change records** | Approval, config/role changes | Ticket closed không chứng minh enforcement |
| **Security policy** | Criteria/control design | Cần xác nhận version/effectiveAt |

### 6.2. Provenance và reliability

Một evidence record nên có:

~~~text
evidenceId
sourceSystem / tenant
collectionMethod (API export / signed log / readback / observation)
subjectId / targetAccountId / resourceId
observedAt / collectedAt / ingestedAt
sourceVersion / queryParameters / asOf
collectorIdentity / toolVersion
integrityReference / checksum nếu phù hợp
redactionClass / retentionPolicy
relatedControlId / findingId
~~~

Không phải mọi field đều có trong một SaaS; ghi rõ điểm thiếu thay vì tạo giá trị đoán. Raw token, password và private key không được sao chép vào evidence package.

### 6.3. Readback quan trọng hơn command ACK khi kết luận revoke

Một lệnh SCIM PATCH active=false được chấp nhận chưa chứng minh local session, refresh token hoặc direct ACL không còn. Nếu finding nói “quyền chưa được thu hồi”, cần xác định đúng **access path** và bằng chứng trạng thái thực tế.

### 6.4. Point-in-time và dữ liệu hiện tại khác nhau

Snapshot lúc 10:00 có thể cho thấy cloud-admin vẫn active; readback lúc 15:00 thấy đã mất. Hai dữ kiện không mâu thuẫn. Finding có thể là **thu hồi quá hạn** dù hiện tại đã được sửa. Lưu cả evidence lịch sử và remediation readback.

### 6.5. Thiếu log không chứng minh không có sự kiện

Một application không phát audit logs cho local token. Auditor không được viết “không có misuse” chỉ vì log trống. Có thể lập finding về **insufficient logging/control evidence** nếu tiêu chí yêu cầu, đồng thời nói rõ giới hạn kết luận.

### 6.6. Chain of custody

Trong điều tra nghiêm trọng, lưu việc ai thu thập, chuyển giao, đọc/chỉnh và bảo quản evidence; có thể dùng hash/chữ ký số, append-only store và quyền truy cập độc lập. Hash chỉ hỗ trợ phát hiện thay đổi khi thiết kế chuỗi tin cậy đúng; không tự làm evidence không thể bị giả mạo.

## 7. Đơn vị kiểm toán, mẫu và tỷ lệ sai lệch

Kết quả rất khác nhau tùy **đơn vị kiểm tra**:

- Một **identity** có thể có nhiều target accounts.
- Một **account** có thể mang nhiều grants.
- Một **grant** có thể được cấp qua nhiều nguồn.
- Một **workflow Leaver** có thể chứa nhiều tasks.
- Một **review campaign** có thể chứa nhiều review items.
- Một **role** có thể ảnh hưởng hàng nghìn subjects.

### 7.1. Định nghĩa mẫu trước khi đếm

Ví dụ audit 40 Leaver workflows, 5 workflow có ít nhất một target quá hạn:

~~~text
Workflow exception rate = 5 / 40 * 100 = 12,5%
~~~

Nếu 40 workflow tương ứng 240 target accounts mà 7 accounts quá hạn:

~~~text
Target-account exception rate = 7 / 240 * 100 = 2,92%
~~~

Cả hai số có thể đúng nhưng **không thay thế nhau**. Báo cáo cần ghi tử số, mẫu số, cohort, kỳ kiểm tra và mức rủi ro.

### 7.2. Không tính attempts như các đơn vị độc lập

Connector gỡ một role qua ba retries không tạo ba findings hay ba quyền tồn dư. Ghi operationId và attemptId riêng, đếm đúng grant/account/workflow theo mục tiêu.

### 7.3. Sampling và phạm vi kết luận

Nếu chọn mẫu theo rủi ro (chủ yếu privileged users), exception rate phản ánh mẫu đó, không tự đại diện toàn bộ nhân viên. Khi muốn suy diễn thống kê tới quần thể, cần thiết kế mẫu/ngưỡng tin cậy phù hợp; tài liệu này không giả định mọi đợt audit đều là random sample.

### 7.4. Null và UNKNOWN không phải PASS

Target không trả dữ liệu về trạng thái session: observation là **UNKNOWN**. Không xếp vào compliant chỉ vì không thấy access. Cũng không kết luận có vi phạm nếu thiếu bằng chứng; báo scope limitation/control evidence gap và hành động xác minh.

### 7.5. Phân nhóm theo rủi ro

Ngoài overall exceptions, báo riêng high/critical grants, production-admin, finance approver, guest và non-human account. Hai critical findings có thể cần ưu tiên hơn vài chục minor exceptions.

## 8. Root cause analysis: tìm nguyên nhân thật sự

Một finding tốt nêu sai lệch có thể kiểm chứng; corrective action tốt giải quyết **nguyên nhân** khiến sai lệch lặp lại.

### 8.1. Ví dụ từ triệu chứng đến nguyên nhân

~~~text
Triệu chứng:
  Leaver vẫn có quyền Finance export sau cutoff

Phát hiện trung gian:
  IdP group đã gỡ, nhưng direct SaaS role vẫn active

Câu hỏi nguyên nhân:
  Vì sao direct role không có trong revoke plan?
  Vì sao access inventory chỉ lấy group từ IdP?
  Vì sao target readback chỉ kiểm tra account.active?
  Vì sao access review không phát hiện local grant?
  Vì sao owner/policy không yêu cầu scope coverage?

Root cause có thể được xác minh:
  Inventory và connector thiết kế thiếu local grants,
  không có control bắt buộc reconciliation effective access.
~~~

### 8.2. Five Whys không phải công thức điền đủ năm câu

Hỏi “tại sao” nhiều tầng để tìm thiết kế/process/control gap nhưng không ép đúng năm lần hoặc dừng tại lỗi cá nhân. Có thể dùng causal diagram, process mapping, fault tree hoặc phân tích incident nếu phù hợp.

### 8.3. Phân biệt root cause và contributing factors

- **Root cause:** nguyên nhân chính nếu được khắc phục sẽ ngăn hoặc giảm đáng kể tái diễn.
- **Contributing factor:** làm tăng xác suất/tác động, ví dụ connector retry thiếu alert hoặc owner thiếu training.
- **Trigger:** event cụ thể làm vấn đề xuất hiện, ví dụ Leaver hôm đó.
- **Detection gap:** tại sao hệ thống không phát hiện kịp, ví dụ thiếu SIEM rule.

Có thể có nhiều root causes hợp lệ; cần evidence cho từng kết luận.

### 8.4. Corrective action không nên chỉ xử lý mẫu đã kiểm toán

Thu hồi 5 accounts được phát hiện là **immediate remediation**. Nếu 400 accounts khác không được kiểm tra, vẫn cần **population-wide discovery** và fix nguyên nhân connector/inventory. Không chỉ “sửa mẫu cho auditor xem”.

### 8.5. Management disagreement

Owner có thể phản biện severity, scope hoặc cause bằng evidence. Ghi nhận response, kiểm chứng tài liệu và điều chỉnh nếu đúng. Không nhầm disagreement về đánh giá rủi ro với bằng chứng cho thấy condition không tồn tại.

## 9. Severity và mức ưu tiên của Audit finding

Không có một bảng severity duy nhất áp dụng cho mọi tổ chức. Nên dùng rubric được owner/risk function phê duyệt và giữ version.

| Yếu tố | Câu hỏi | Gợi ý đánh giá |
|---|---|---|
| **Độ nhạy dữ liệu** | Quyền liên quan tài chính, PII, bí mật? | Critical data tăng impact |
| **Đặc quyền** | Admin, policy.write, credential.create, delete? | Có thể nâng privilege |
| **Phạm vi** | Một user/tenant hay nhiều hệ thống? | Blast radius |
| **Exploitability** | Credential/phiên có thể sử dụng thực tế? | Need evidence, không suy đoán |
| **Thời gian tồn dư** | Quyền mở bao lâu sau cutoff? | Exposure window |
| **Tần suất** | Lỗi cá biệt hay lặp trong population? | Systemic weakness |
| **Kiểm soát bù trừ** | Có deny gateway, session revoke, JIT? | Giảm risk nếu verified |
| **Detection/response** | Có cảnh báo, owner, SLO rõ? | Khả năng phản ứng |
| **Regulatory/contract** | Tiêu chí áp dụng có bắt buộc? | Xem nguồn thật, không bịa |
| **Khả năng tái diễn** | Fix riêng lẻ hay lỗi thiết kế? | Root cause priority |

### 9.1. Ví dụ severity mang tính minh họa

| Mức | Kịch bản giả định | Hướng ưu tiên |
|---|---|---|
| **Critical** | Leaver vẫn có production-admin và credential đang usable | Containment/incident path theo policy |
| **High** | Hàng loạt Leaver trong SaaS nhạy cảm quá hạn, thiếu verification | Khắc phục sớm, owner cấp phù hợp |
| **Medium** | Một số group membership stale nhưng scope thấp và có kiểm soát khác | Time-bound remediation và retest |
| **Low** | Audit evidence metadata thiếu field nhỏ, control vẫn effective | Sửa quy trình và evidence quality |

Không khẳng định mọi trường hợp production-admin đều phải được xếp Critical nếu chưa xét thực tế; rubric, tình trạng privilege và risk context quyết định.

### 9.2. Likelihood và impact cần căn cứ

Nếu chưa thấy attacker lợi dụng, có thể vẫn có likelihood dựa trên mức độ exposed và credential viability. Viết rõ **potential impact** và điều kiện xảy ra. Không suy exfiltration chỉ từ account ACTIVE.

### 9.3. Severity có thể thay đổi khi xuất hiện evidence

Finding ban đầu Medium do nghi thiếu log; readback sau đó cho thấy active credential có quyền xóa production database. Có thể re-rate theo quy trình có audit, lưu severity history thay vì overwrite âm thầm.

## 10. Audit finding điển hình: Leaver còn quyền truy cập

### 10.1. Finding minh họa

| Thành phần | Nội dung |
|---|---|
| Finding ID | IAM-FIND-LEAVER-001 |
| Criteria | Chính sách Leaver yêu cầu thu hồi quyền critical trước cutoff đã phê duyệt |
| Scope | 40 Leaver workflows tại ba SaaS và một IdP |
| Condition | 5 workflow còn quyền quá hạn; 2 có direct local roles |
| Evidence | HRIS effectiveAt, IAM command, SCIM ACK, target readback |
| Root cause | Inventory không bao gồm local grants; thiếu effective-access reconciliation |
| Risk | Residual access có thể bị dùng sau khi hết quan hệ lao động |
| Action owner | IAM Engineering và Target Application Owner |
| Fix ngay | Revoke quyền còn tồn dư, đánh giá sessions/tokens |
| Fix hệ thống | Mở inventory, bổ sung connector, readback, monitor |
| Retest | Kiểm tra quần thể mới, đường grant khác và cutoff |

Các con số trên chỉ minh họa; finding thực cần evidence IDs và policy version thật.

### 10.2. ACK không chứng minh quyền đã mất

SCIM PATCH User.active=false có thể thành công nhưng local role, session, API key hoặc resource ACL vẫn có quyền theo provider contract. Kết luận phải dựa trên **đường quyền cụ thể**, không chỉ response HTTP 2xx.

### 10.3. Không có login không phải bằng chứng revoke

Một account không phát sinh login sau Leaver vẫn có thể active trái chính sách. Ngược lại, account active cũng không chứng minh đã có hành vi đánh cắp dữ liệu; phải tách **observed condition** với **potential impact**.

### 10.4. Đo thời gian đúng

~~~text
Leaver effectiveAt: 17:00
SCIM ACK:           17:01
Target role absent: 17:04 (readback observed)
Finding verified:   17:05
~~~

Được phép nói time-to-verified là 5 phút trong ví dụ; không được nói chính xác role bị chặn lúc 17:04 nếu chỉ có điểm quan sát.

### 10.5. Retest phải vượt ra ngoài mẫu ban đầu

Thu hồi 5 grants đã biết là correction; nếu connector vẫn bỏ qua local role cho 400 accounts khác, nguyên nhân chưa khắc phục. Cần population review, thiết kế discovery mới và thử nghiệm Leaver mới.

## 11. Audit finding: Mover tích lũy quyền cũ

Mover cần cập nhật quyền khi thay vị trí, team, region, project, tenant hoặc level.

### 11.1. Tình huống

~~~text
Change: Finance -> Operations

Desired grants:
  finance.invoice.approve = REVOKED
  operations.dashboard.view = ACTIVE

Observed grants:
  finance.invoice.approve = ACTIVE    <-- Finding condition
  operations.dashboard.view = ACTIVE
~~~

### 11.2. Cấp quyền mới chưa đủ hoàn tất Mover

Workflow chỉ thêm Operations group mà quên gỡ Finance group dẫn tới **privilege accumulation**. Finding liên quan state reconciliation và SoD; không nhất thiết cần disable user toàn cục.

### 11.3. Bằng chứng

HRIS role-change effectiveAt, desired entitlement catalog, group/ACL before-after, request approvals, target readback, session/role cache nếu có.

### 11.4. RBAC và ABAC

Trong RBAC cần gỡ role/grant cũ. Trong ABAC, department/region/classification có thể thay đổi dù role name không đổi; stale attributes hoặc authorization cache gây quyền sai. Cần evidence về attribute source/freshness và effective policy decision.

### 11.5. Action

Tính desired-state diff, revoke previous entitlements, kiểm tra SoD, phát hiện Mover không có remove operations, xác minh target, giới hạn migration overlap được phê duyệt.

## 12. Audit finding: Joiner được mở quyền quá sớm

### 12.1. Khác biệt giữa provision và enable

Tổ chức có thể tạo preboarding account trước ngày đi làm. Điều đó không mặc định vi phạm. Nếu chính sách cho phép account ở trạng thái DISABLED cho tới ngày bắt đầu, cần audit **thời điểm quyền có hiệu lực**, không chỉ createdAt.

### 12.2. Condition và criteria

Một user được mở quyền production-data trước startDate dù policy yêu cầu chỉ mở từ effectiveAt. Finding cần đối chiếu HRIS startDate, target active/grant history, approval và policy version.

### 12.3. Cause có thể có

Provisioning không kiểm tra effectiveAt; role inheritance áp ngay khi user được thêm vào group; connector target đồng bộ quá sớm; hoặc mapping nhầm user/tenant.

### 12.4. Corrective action

Tách account creation và access activation, kiểm thử boundary dates/timezones, áp policy trước khi cấp quyền, đối soát trước/đúng/sau startDate.

## 13. Audit finding: Access Recertification chỉ hoàn tất trên giấy

Access review giúp owner xác nhận quyền còn phù hợp, nhưng tỷ lệ người đã bấm KEEP/REVOKE không nói lên mọi quyền đã được xử lý.

| Condition | Nguyên nhân/rủi ro | Evidence |
|---|---|---|
| Role nằm ngoài campaign | Coverage gap | Inventory và snapshot |
| Reviewer là chính người có role, policy cấm tự review | SoD | Reviewer authority history |
| Auto-KEEP quá hạn trái policy | Review không thực chất | Workflow rules |
| KEEP thiếu justification với admin role | Business need không rõ | Decision evidence |
| REVOKE được chọn nhưng grant vẫn active | Remediation gap | Decision + target readback |
| Reviewer đã Leaver | Owner không hợp lệ | HRIS và campaign assignment |
| Xóa pending items khỏi mẫu số | Thổi phồng completion | Immutable snapshot/exclusion audit |
| Service principals bị loại khỏi scope | Non-human coverage gap | NHI inventory |

### 13.1. Ba metric phải tách

~~~text
Decision completion = valid decisions / in-scope items

Remediation completion =
  verified changed grants / grants requiring remediation

Coverage = reviewable grants included / eligible inventory grants
~~~

Kỳ review 100% decision completion trên 70% inventory không chứng minh 100% quyền đã được rà soát.

### 13.2. Chất lượng review khác tốc độ review

Một reviewer tự approve admin role của mình hoặc auto-KEEP tất cả items để đạt deadline có thể tạo finding. Cần authority, SoD, justification, evidence và risk-based follow-up.

### 13.3. Fix

Snapshot đầy đủ, owners rõ, validation reviewer, high-risk escalation, remediation verification và audit trail của mọi exclusion.

## 14. Audit finding: Non-human identity không có owner hoặc quá quyền

Workloads, integrations, service principals và API keys thuộc IAM audit dù không có HRIS record.

| Condition | Cause khả dĩ | Rủi ro |
|---|---|---|
| Service principal orphan | Registry không theo deployment | Không có reviewer/retirement |
| API key không biết chủ | Credential inventory thiếu | Không kiểm soát secret |
| Dev runtime dùng prod-admin | Shared principal | Cross-environment blast radius |
| CI federation trust quá rộng | Thiếu issuer/subject/audience binding | Job khác có thể lấy token |
| Service retired vẫn xin token mới | Trust/STS chưa revoke | Quyền tồn dư |
| Rotate key nhưng key cũ vẫn usable | Rotation không verify | Credential tồn dư |
| Human owner Leaver còn quyền vault | Thiếu human JML | Credential bị lạm dụng |
| Shared technical user cho nhiều connector | Vendor limitation | Khó quy trách nhiệm |

### 14.1. MFA của người không phải yêu cầu áp máy móc cho máy

Workload thường dùng mTLS, managed identity, federation hoặc client auth; không nhất thiết dùng OTP tương tác. Tiêu chí audit phải phù hợp loại principal và mục đích.

### 14.2. Token ngắn hạn không tự giảm standing privileges

Token 5 phút có thể xin mới liên tục nếu workload trust/role còn active. Audit privilege bindings, issuer/subject trust và khả năng issuance, không chỉ thời hạn token.

### 14.3. Human owner nghỉ không tự xóa workload

Backup service vẫn cần chạy thì phải bàn giao owner, revoke human admin grants, xem secret export/rotation và review service role; không disable máy không có kế hoạch.

### 14.4. Runtime trust là boundary riêng

Một Kubernetes ServiceAccount không tự có quyền cloud. Finding cần kiểm tra mapping namespace/subject/issuer/audience sang cloud IAM principal, scope và target.

## 15. Audit finding: Federation, SSO và session

### 15.1. Những lỗi thường rà soát

- SAML/OIDC issuer/audience/signature/token type validation không đúng.
- Account linking bằng email thiếu xác minh, thay vì trusted issuer+subject.
- IdP group mapping thành role quá rộng hoặc sai tenant.
- MFA/step-up thiếu ở thao tác đặc quyền theo policy.
- RP session dùng lại ID anonymous sau login.
- IdP disable nhưng RP session không bị chặn đúng SLA.
- Token/refresh token/local role tồn dư.
- Partner federation trust không retire sau hợp đồng.
- Thiếu authentication và authorization audit correlation.

### 15.2. Authentication không thay authorization

IdP xác thực user đúng nhưng ứng dụng nhận group stale rồi vẫn cấp finance.export là vấn đề role mapping/cache. Reset password không giải quyết sai lệch entitlement.

### 15.3. Ví dụ finding Session fixation

**Criteria:** local authenticated session ID không tái sử dụng pre-auth identifier có thể bị biết trước.

**Condition:** ứng dụng giữ S0 sau callback login; S0 được server ánh xạ tới user đã xác thực.

**Cause:** Custom authentication callback không đi qua session rotation strategy.

**Risk:** Người biết S0 trước login có thể dùng phiên user.

**Action:** Đổi ID, vô hiệu old-ID authentication mapping, kiểm thử mọi nodes. Test phải dùng test accounts được phép, không dùng phiên thật của người khác.

### 15.4. Partner federation

Sau khi hợp đồng đối tác hết hạn, trust connection có thể còn cho token mới dù guest accounts đã disable. Audit gồm partner issuer trust, credential/authorization và session/grants, không chỉ human Leaver.

## 16. Audit finding: evidence logging thiếu hoặc không đáng tin

Có hai finding khác nhau:

- **Control failure đã có bằng chứng:** direct grant thực sự còn active.
- **Evidence/control gap:** IAM chỉ có command ACK, không đủ thông tin để xác minh target.

Không suy sai lệch thứ nhất chỉ từ sự thiếu dữ liệu của thứ hai.

### 16.1. Các vấn đề thường gặp

- Thiếu sourceEventId, workflowId, operationId, attemptId.
- Thiếu effectiveAt dẫn tới không thể đo SLA.
- Dùng email thay immutable subjectId/target namespace.
- Retry overwrite thất bại cũ.
- Thiếu observedAt/sourceVersion, evidence stale.
- Pipeline mất events nhưng không có health alert.
- Logs bị chỉnh/xóa không có audit trail.
- Log raw bearer token, password hoặc PII dư thừa.
- Không correlate principal, action, resource và tenant.

### 16.2. Tính toàn vẹn và privacy

Có thể sử dụng append-only evidence store, retention lock, hash chaining và quyền truy cập tách biệt. Không khẳng định một checksum tự làm log bất biến. Hạn chế PII, encrypt, retention/legal hold và audit chính hành động xem/export logs.

### 16.3. Fix

Canonical event schema, producer trust, source-to-sink reconciliation, pipeline heartbeat, missing-evidence alert, authorized evidence repository và kiểm thử audit end-to-end.

## 17. Mẫu dữ liệu cho Audit finding

### 17.1. Các trường cần quản lý

| Nhóm | Thông tin |
|---|---|
| Identity | findingId, title, findingType, status |
| Criteria | controlId, policyVersion, criteriaRef, effectiveDate |
| Scope | audit period, tenant, systems, population, sample method |
| Condition | observed facts, affectedItems, numerator/denominator |
| Evidence | evidenceRefs, source, observedAt, provenance |
| Analysis | cause, contributing factors, actual impact, potential risk |
| Severity | rating, modelVersion, risk tier |
| Owners | control owner, action owner, risk owner, reviewer |
| CAPA | actions, dueAt, milestones, dependencies |
| Exceptions | exceptionRef, compensating controls, expiry |
| Verification | retestMethod, evidenceRef, tester, outcome |
| History | status transitions, timestamps, approvals |

### 17.2. JSON mô phỏng

~~~json
{
  "findingId": "IAM-FIND-LEAVER-001",
  "title": "Local SaaS role tồn dư sau Leaver",
  "auditId": "IAM-AUDIT-2026-Q4",
  "control": {
    "id": "IAM-JML-LEAVER-07",
    "version": "v3",
    "criteriaRef": "policy/iam-leaver/v3"
  },
  "scope": {
    "sampledWorkflows": 40,
    "exceptionWorkflows": 5,
    "sampleMethod": "risk-based",
    "targetSystems": ["finance-saas", "idp"]
  },
  "condition": "5/40 workflow còn entitlement quá hạn",
  "evidenceRefs": ["evidence/find001/role-a", "evidence/find001/role-b"],
  "rootCause": "Inventory thiếu direct local role",
  "severity": "HIGH",
  "severityModelVersion": "risk-model-v5",
  "status": "OPEN",
  "actions": [{
    "id": "ACT-001",
    "owner": "iam-engineering",
    "goal": "Local grant discovery + target readback",
    "acceptanceCriteria": "All in-scope grants reconciled",
    "dueAt": "2026-12-15T10:00:00Z"
  }],
  "schemaVersion": "1.0"
}
~~~

Schema và dữ liệu này là ví dụ, không phải chuẩn của auditor/provider. Lưu raw evidence trong kho riêng có version/permissions; finding chỉ tham chiếu. Không lưu tokens/secret/PII dư thừa.

### 17.3. State history

~~~text
DRAFT -> VALIDATED -> OPEN -> ACTION_IN_PROGRESS
      -> READY_FOR_RETEST -> RETEST_FAILED
      -> ACTION_IN_PROGRESS -> READY_FOR_RETEST
      -> VERIFIED_CLOSED
~~~

Không xóa lần retest failed. Mỗi transition có actor, time, reason và evidence. Overdue là thuộc tính thời gian của một OPEN finding, không nhất thiết là trạng thái độc lập.

## 18. Corrective Action Plan (CAPA)

### 18.1. Immediate correction và systemic fix

- **Immediate:** revoke grants được phát hiện, hạn chế credential/session, xử lý incident nếu có.
- **Systemic:** sửa inventory, connector, approval, policy, review, monitoring và regression tests.

### 18.2. Action có thể xác minh

Thay “cải thiện IAM” bằng yêu cầu cụ thể: “Đưa direct-role discovery vào Leaver workflow cho Finance SaaS; gỡ role trái policy, readback, alert nếu quá deadline; chứng minh bằng cohort mới và test cases”.

### 18.3. Phân công vai trò

| Vai trò | Trách nhiệm |
|---|---|
| Finding owner | Theo dõi finding và lịch sử |
| Control owner | Chịu trách nhiệm hiệu lực kiểm soát |
| Action owner | Triển khai fix |
| Risk owner | Xử lý residual risk/exceptions |
| Target owner | Xác minh state ở target |
| Independent tester | Re-test acceptance criteria |
| Management sponsor | Nguồn lực và dependency |

Owner tự đánh dấu DONE chưa phải independent verification.

### 18.4. Deadline, dependency và gia hạn

Nếu cần vendor API hoặc migration, ghi milestones, interim controls, owner, approval extension và deadline mới. Không gia hạn âm thầm để làm đẹp overdue rate.

### 18.5. Fix nguyên nhân, không chỉ mẫu

Thu hồi năm accounts trong mẫu là correction; nếu connector vẫn bỏ qua local grants, recurrence vẫn xảy ra. CAPA phải kiểm soát được quần thể và chứng minh hiệu lực trong kỳ mới.

## 19. Exceptions, compensating controls và residual risk

Một finding không phải lúc nào cũng có thể khắc phục ngay: vendor không hỗ trợ revoke active token, migration cần giữ dual access hoặc hệ thống legacy thiếu API. Tuy nhiên, việc chưa thể xử lý phải được quản trị theo rủi ro.

### 19.1. Exception cần đầy đủ thông tin

| Trường | Ý nghĩa |
|---|---|
| exceptionId, findingId | Liên kết exception với audit |
| reason, scope | Tại sao chưa thể tuân thủ và ảnh hưởng quyền nào |
| affectedSubjects/targets | Identity, tenant, system và grant |
| riskAssessment | Likelihood, impact, residual risk |
| riskOwner/approver | Người có thẩm quyền chấp nhận |
| acceptedAt/expiresAt | Thời hạn rõ ràng |
| compensatingControls | Biện pháp giảm rủi ro đã xác minh |
| monitoring | Alerts, owner, review cadence |
| remediationPlan | Bước fix gốc và dependency |
| evidenceRefs | Phê duyệt và bằng chứng |

### 19.2. Ví dụ kiểm soát bù trừ

SaaS không hỗ trợ hủy access token hiện có. Tùy contract và threat model, có thể cân nhắc token TTL ngắn, deny tại gateway, resource-side authorization checks hoặc chặn local account. Phải **kiểm thử biện pháp thực sự chặn được đường truy cập**; không chỉ ghi “gateway enabled”.

### 19.3. Risk accepted không giống verified closed

Nếu risk owner chấp thuận ngoại lệ có thời hạn, finding vẫn tồn tại với status/record thích hợp và ngày rà soát lại. Không đổi nó thành VERIFIED_CLOSED khi root cause và control deficiency chưa được khắc phục.

### 19.4. Exception hết hạn và lịch sử

Khi hết hạn mà vấn đề còn, phải escalated/renew theo thẩm quyền; không tự gia hạn hay ẩn khỏi dashboard. Một exception được phê duyệt hôm nay cũng không xóa lịch sử vi phạm trong kỳ trước.

## 20. Retest và tiêu chí đóng Finding

Đóng finding cần có bằng chứng corrective action **thực sự xử lý tiêu chí đã thất bại**, không chỉ ticket đã được deploy.

### 20.1. Acceptance criteria cho finding Leaver local grant

1. Local grants thuộc scope xuất hiện trong inventory.
2. Workflow revoke tất cả grants trái policy.
3. Readback chứng minh grant/role đã mất tại target.
4. Session/token được xử lý theo capability/SLO đã công bố.
5. Log liên kết sourceEventId, operationId, observedAt và policyVersion.
6. Event Mover cũ không tái cấp quyền sau Leaver.
7. Cohort Leaver mới đạt control trong phạm vi được kiểm tra.
8. SIEM alert khi target chưa verified đúng hạn.

Đây là tiêu chí minh họa; có thể điều chỉnh theo control và vendor, nhưng mọi thay đổi phải có lý do/approval, không sửa tiêu chí âm thầm để dễ pass.

### 20.2. Design vs operating effectiveness

- **Thiết kế:** workflow/config có thể đạt mục tiêu kiểm soát không?
- **Vận hành:** trong trường hợp thực tế và test được phép, control có thực thi hiệu quả không?

Một commit hoặc policy document được duyệt không đủ nếu target connector vẫn bỏ sót direct role.

### 20.3. Re-test với phạm vi xác định

Ghi rõ tester, test case, environment, sampled population, version, evidenceRef, observedAt và outcome. Nếu chỉ thử finance-saas thì không tuyên bố cloud IAM đã được verified.

### 20.4. Negative và regression tests

Sau khi sửa, nên kiểm tra user vẫn được làm action hợp lệ, Leaver/Mover không được làm action đã revoke, cross-tenant request bị chặn và IdP/SCIM workflow xử lý retry đúng. Dùng test principal và tài nguyên được phép.

### 20.5. Retest failed và reopen

Lần test thất bại phải được giữ trong history. Nếu tìm thấy quyền tồn dư sau lần verified closure, ghi recurrence/drift và reopen hoặc tạo linked finding theo policy; đừng sửa lịch sử cho giống như chưa từng pass.

### 20.6. Independent verification

Đối với finding rủi ro cao, reviewer kiểm thử nên đủ độc lập với người sửa lỗi theo chính sách tổ chức. Không nhất thiết phải là bên ngoài doanh nghiệp; quan trọng là thẩm quyền và tính khách quan.

## 21. Trạng thái vòng đời của một Finding

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> VALIDATED: Criteria và evidence đủ
    DRAFT --> DISMISSED: Không thuộc scope hoặc false positive
    VALIDATED --> OPEN: Phát hành finding
    OPEN --> ACTION_IN_PROGRESS: Kế hoạch được phê duyệt
    OPEN --> RISK_ACCEPTED: Ngoại lệ hợp lệ
    ACTION_IN_PROGRESS --> READY_FOR_RETEST: Có remediation evidence
    READY_FOR_RETEST --> VERIFIED_CLOSED: Retest PASS
    READY_FOR_RETEST --> RETEST_FAILED: Retest FAIL
    RETEST_FAILED --> ACTION_IN_PROGRESS
    RISK_ACCEPTED --> ACTION_IN_PROGRESS: Cần sửa nguyên nhân
    VERIFIED_CLOSED --> REOPENED: Recurrence / drift
    REOPENED --> ACTION_IN_PROGRESS
    VERIFIED_CLOSED --> [*]
    DISMISSED --> [*]
~~~

### 21.1. Transition tối thiểu

| Transition | Điều kiện |
|---|---|
| DRAFT → VALIDATED | Criteria, condition, scope, evidence có thể kiểm tra |
| VALIDATED → OPEN | Severity, owner, management response được ghi |
| OPEN → ACTION_IN_PROGRESS | Action plan, owner, due date và milestones |
| ACTION_IN_PROGRESS → READY_FOR_RETEST | Fix thực thi và có evidence |
| READY_FOR_RETEST → VERIFIED_CLOSED | Retest theo acceptance criteria đạt |
| READY_FOR_RETEST → RETEST_FAILED | Có test outcome, failure reason |
| OPEN → RISK_ACCEPTED | Risk owner phê duyệt scope, expiry, controls |
| VERIFIED_CLOSED → REOPENED | Recurrence có evidence, linked history |

### 21.2. Dismissed không phải xóa dấu vết

Một observation có thể bị dismissed do evidence phản biện hợp lệ; phải giữ quyết định và lý do, không xóa audit record.

### 21.3. Overdue là thuộc tính

Finding vừa OPEN vừa overdue nếu đã qua approved dueAt. Giữ originalDueAt và extension history, không thay deadline lén.

### 21.4. Re-rate severity

Khi bằng chứng cho thấy quyền nhạy cảm hơn dự đoán, có thể nâng severity theo rubric. Ghi old/new value, authority, timestamp và risk model version.

## 22. Case study: IAM Audit Leaver ở ba hệ thống

### 22.1. Bối cảnh

Một doanh nghiệp dùng HRIS, IdP, Finance SaaS và Cloud IAM. Policy yêu cầu quyền critical applications của Leaver được thu hồi trước cutoff và có bằng chứng tại target.

Auditor kiểm tra **40 Leaver workflows** trong kỳ, đối chiếu HRIS effectiveAt, IdP group status, connector operations, SaaS direct roles và cloud IAM inventory. Đây là **tình huống giả lập**.

### 22.2. Kết quả quan sát

| Đơn vị kiểm tra | Số |
|---|---:|
| Leaver workflows trong mẫu | 40 |
| Workflow có ít nhất một quyền quá hạn | 5 |
| Target accounts trong mẫu | 240 |
| Target accounts quá hạn | 7 |
| Workflow có direct SaaS role chưa revoke | 2 |
| Workflow thiếu bằng chứng session termination | 3 |

### 22.3. Hai tỷ lệ có mẫu số khác nhau

~~~text
Workflow exception rate = 5 / 40 * 100 = 12,50%

Target-account exception rate = 7 / 240 * 100 = 2,92%
~~~

Mẫu được chọn theo rủi ro thì không tự suy ra tỷ lệ exception của cả doanh nghiệp. Hai tỷ lệ đo hai đơn vị khác nhau.

### 22.4. Một timeline cụ thể

~~~text
subjectId: employee-1042
HRIS effectiveAt:             2026-11-03T10:00:00Z
SCIM group removal ACK:       2026-11-03T10:01:00Z
Target account active=false:  observed at 10:03
Direct finance.export role:   ACTIVE, observed 10:20
Role absent after correction: observed at 11:05
~~~

Dữ liệu giả lập cho thấy ACK đã thành công nhưng local role vẫn tồn dư sau cutoff. Không tự khẳng định exact enforcement time bằng mốc readback.

### 22.5. Finding statement

**Criteria:** Policy yêu cầu Leaver critical access bị thu hồi và verified đúng cutoff.

**Condition:** Năm workflow trong mẫu còn quyền quá hạn; hai có direct role ngoài scope SCIM group cleanup.

**Cause:** Inventory thiếu direct local grants; verification chỉ kiểm tra account.active.

**Risk:** Residual access có thể bị dùng sau khi quan hệ lao động kết thúc; không có bằng chứng misuse không đồng nghĩa không có quyền.

**Action:** Thu hồi quyền còn tồn, mở inventory/adapters, sửa closure criteria, tạo monitoring và retest.

### 22.6. CAPA và trách nhiệm

| Hành động | Owner | Bằng chứng đạt |
|---|---|---|
| Revoke các target grants quá hạn | SaaS/Cloud Owner | Target readback |
| Rà sessions/tokens | IdP và App Owners | Evidence hoặc limitation/exception |
| Discover direct roles | IAM Engineering | Coverage report |
| Sửa workflow và retry logic | IAM Platform | Integration regression tests |
| Alert overdue high-risk | Security Operations | Rule test và dashboard |
| Re-test độc lập | Audit | Test report theo acceptance criteria |

### 22.7. Đóng finding khi nào?

Không đóng chỉ vì connector code đã merge. Phải xác minh grants được thu hồi, discovery đủ scope, controls thực thi trong cohort mới, và exception còn lại có rủi ro/owner/time-bound được quản trị theo policy.

## 23. Dashboard và KPI để theo dõi Audit findings

Một dashboard hiệu quả không chỉ đếm số ticket đóng. Nó cần hiển thị **severity, tuổi finding, rủi ro còn lại, deadline, scope và kết quả retest**.

| Metric | Diễn giải | Sai lầm thường gặp |
|---|---|---|
| Open findings | Số finding chưa giải quyết | Không phân loại rủi ro |
| High/Critical open | Backlog nhạy cảm | Bị che bởi nhiều Low đã đóng |
| Overdue findings | Chưa xử lý sau approved due date | Đổi deadline lén |
| Time-to-contain | Thời gian tới containment có evidence | Không phải systemic fix |
| Time-to-action-complete | Owner hoàn thành action items | Không phải verified closure |
| Time-to-verified-close | Thời gian tới retest PASS | Có thể bao gồm thời gian chờ auditor |
| Repeat findings | Lỗi cùng root cause tái diễn | Cần phân loại finding category nhất quán |
| Exception aging | Thời gian residual risk được chấp thuận | Risk accepted không phải zero risk |
| Evidence completeness | Criteria/condition/provenance đủ | Không chứng minh control effectiveness |
| Audit universe coverage | Đã kiểm tra bao nhiêu hệ thống/grants | Kết quả ít findings do scope hẹp |
| Residual access after cutoff | Grants còn active trái policy | Cần target readback |
| CAPA effectiveness | Control mới vận hành đạt hay không | Chỉ xem code deployed |

### 23.1. Ba nghĩa của completion

~~~text
Action completion:
  Owner đã triển khai thay đổi theo kế hoạch.

Verification completion:
  Retest đã đánh giá thay đổi theo criteria.

Finding closure:
  Finding đạt VERIFIED_CLOSED với bằng chứng đủ scope.
~~~

Một chương trình audit có 100% action tickets DONE vẫn có thể còn nhiều findings OPEN do test chưa đạt hoặc thiếu evidence.

### 23.2. Verified Closure Rate

~~~text
Verified Closure Rate (%) =
    findings ở trạng thái VERIFIED_CLOSED trong cohort
    / all in-scope findings của cohort
    * 100
~~~

Phải công bố cohort, date cutoff, policy exclusions, denominator và as-of. Khi mẫu số bằng 0, kết quả là N/A, không tự hiển thị 100%.

### 23.3. Risk-tier breakdown

Một finding production-admin còn OPEN có thể ưu tiên hơn 20 low findings đã đóng. Dashboard nên có số lượng critical overdue, owner, scope, residual access và interim controls.

### 23.4. Số findings giảm chưa chắc kiểm soát tốt hơn

Nếu kỳ này bỏ cloud IAM hoặc service principals khỏi audit universe, có thể ít findings vì audit coverage kém. So sánh giữa kỳ cần xem cả population, sampling method, test depth, criteria version và detection capability.

### 23.5. Định nghĩa repeat finding nhất quán

Một nhóm lỗi cùng root cause nhưng xuất hiện ở nhiều SaaS có thể được gom thành systemic finding hoặc liên kết findings. Tổ chức cần quy tắc tránh vừa đếm trùng vừa bỏ sót tác động ở các targets.

## 24. SQL mẫu cho finding metrics

Giả định PostgreSQL read model có một hàng trên mỗi finding, tổng hợp từ immutable audit events. Đây là ví dụ phân tích, không phải schema hay implementation bắt buộc.

### 24.1. Backlog theo severity

~~~sql
SELECT
    severity,
    status,
    COUNT(*) AS finding_count
FROM iam_audit_findings
WHERE audit_program_id = :auditProgramId
  AND tenant_id = :authorizedTenantId
GROUP BY severity, status;
~~~

Tenant của người xem phải được backend authorization xác nhận; không được tin input client tự gán tenantId bất kỳ.

### 24.2. Tìm các finding quá hạn

~~~sql
SELECT
    finding_id,
    control_id,
    severity,
    action_owner_id,
    original_due_at,
    approved_due_at,
    status
FROM iam_audit_findings
WHERE status NOT IN ('VERIFIED_CLOSED', 'DISMISSED')
  AND approved_due_at < :trustedAsOf
  AND tenant_id = :authorizedTenantId
ORDER BY severity_rank DESC, approved_due_at ASC;
~~~

Việc loại hay báo riêng RISK_ACCEPTED phụ thuộc chính sách; không mặc định chấp nhận rủi ro thì hết overdue. Giữ original_due_at để truy xuất history gia hạn.

### 24.3. Verified closure rate theo control

~~~sql
SELECT
    control_id,
    COUNT(*) AS total_findings,
    COUNT(*) FILTER (
        WHERE status = 'VERIFIED_CLOSED'
    ) AS closed_findings,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE status = 'VERIFIED_CLOSED'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS closed_pct
FROM iam_audit_findings
WHERE audit_id = :auditId
  AND tenant_id = :authorizedTenantId
GROUP BY control_id;
~~~

### 24.4. Tính thời gian tới verified closure

~~~sql
SELECT
    severity,
    COUNT(*) AS verified_count,
    AVG(
        EXTRACT(EPOCH FROM (verified_closed_at - opened_at))
    ) AS avg_seconds_to_verified_close
FROM iam_audit_findings
WHERE status = 'VERIFIED_CLOSED'
  AND verified_closed_at >= opened_at
  AND tenant_id = :authorizedTenantId
GROUP BY severity;
~~~

**Lưu ý survivorship bias:** chỉ tính findings đã đóng khiến các finding open lâu biến mất khỏi số trung bình. Báo cùng outstanding age, percentiles và overdue counts.

### 24.5. Không nhân findings khi JOIN

Một finding có nhiều corrective actions, mỗi action có nhiều retest attempts. JOIN thẳng rồi COUNT(*) sẽ nhân số hàng. Aggregate per findingId trước hoặc dùng unique finding projection, trong khi giữ attempts như dữ liệu riêng.

### 24.6. Historical as-of

Một report kết thúc ngày 30/09 không được lấy retest PASS tháng 11 để thay đổi kết quả tháng 9 trừ khi có quy tắc restatement công bố. Lưu effective events và audit snapshot để tái hiện.

## 25. Java và pseudocode cho quản trị finding

### 25.1. Model dữ liệu Java tối giản

~~~java
import java.time.Instant;
import java.util.List;

record IdentityAuditFinding(
        String findingId,
        String controlId,
        String severity,
        String status,
        String actionOwnerId,
        Instant dueAt,
        List<String> evidenceRefs
) {
    IdentityAuditFinding {
        if (findingId == null || controlId == null
                || severity == null || status == null
                || dueAt == null) {
            throw new IllegalArgumentException("Missing finding fields");
        }
    }
}
~~~

Đây là model minh họa, chưa có multi-tenant authorization, database, lifecycle validation, policy/rating model hay audit history. Không dùng nó làm toàn bộ hệ thống audit production.

### 25.2. Pseudocode cho trạng thái VERIFIED_CLOSED

~~~text
function verifyAndCloseFinding(findingId, retest):
    finding = trustedStore.load(findingId)

    if finding.status not in {READY_FOR_RETEST, RETEST_FAILED}:
        return INVALID_TRANSITION

    if not reviewerAuthorized(retest.tester, finding):
        return DENY

    if not policyVersionAndCriteriaKnown(finding):
        return INVALID_CRITERIA

    if not allRequiredActionsImplemented(finding):
        return NOT_READY

    evidence = protectedEvidenceStore.resolve(retest.evidenceRefs)

    if not evidenceCoversScopeTimeAndCriteria(finding, evidence):
        return INSUFFICIENT_EVIDENCE

    if not independentRetestPasses(finding, evidence):
        appendAuditEvent(RETEST_FAILED, finding, evidence)
        return RETEST_FAILED

    appendAuditEvent(VERIFIED_CLOSED, finding, evidence)
    return VERIFIED_CLOSED
~~~

Cần kiểm soát concurrency/version, SoD, exception approvals, evidence integrity và transition history. Không cho client tự đặt status VERIFIED_CLOSED mà bỏ verification service.

### 25.3. Không xóa lịch sử khi retest mới pass

Nếu retest đầu FAIL và lần hai PASS, cả hai là facts quan trọng. Lưu event append-only với actor, time, criteria version và evidenceRef; read model có thể thể hiện state mới nhất.

### 25.4. Change management và release

Khi action owner thông báo connector fix đã deploy, đó là evidence của remediation implementation. Auditor vẫn phải re-test desired vs actual grant ở target, không suy outcome từ trạng thái CI pipeline.

## 26. Những anti-pattern trong quản lý Audit finding

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng alert làm finding ngay | False positive | Xác minh criteria/evidence |
| Tuyên bố vi phạm mà không có policy | Criteria không có căn cứ | Dẫn chính sách có version |
| Finding mô tả mơ hồ | Không biết sửa gì | Condition có scope/count/IDs |
| Chỉ đổ lỗi con người | Fix không chạm root cause | Phân tích process/system |
| Dựa riêng vào SCIM HTTP 204 | Tưởng quyền đã hết | Target effective-access verification |
| Chỉ xem IdP group | Bỏ local/direct grants | Inventory toàn diện |
| Tính retry attempts như nhiều lỗi | Thổi số | Đếm đúng đơn vị |
| Dùng email làm identity key | Nhầm người/account | Immutable ID/namespace |
| Thiếu sample method | Suy rộng không hợp lệ | Công bố population/cohort |
| Gộp actual impact với potential risk | Phóng đại phát hiện | Tách observed/potential |
| Severity do cảm tính | Ưu tiên sai | Risk rubric có version |
| Fix chỉ accounts trong mẫu | Recurrence | Systemic CAPA/population review |
| Chủ sửa lỗi tự đóng finding | Thiếu verification độc lập | Retest có evidence |
| Xóa failed retest | Mất audit trail | Append-only history |
| Exception không hết hạn | Rủi ro tồn dư vô hạn | Owner, expiry, monitoring |
| Thay deadline để đẹp KPI | Sai báo cáo | Giữ original/approved due |
| Bỏ non-human identities | Service privileges mồ côi | NHI registry và review |
| Không kiểm tra token/session | Residual access sau Leaver | IdP/RP/target evidence |
| Log raw tokens/PII | Rò dữ liệu audit | Redaction/least privilege |
| Chỉ đo finding closed count | Che critical backlog | Severity/coverage/SLO |
| Gộp nhiều root causes vô căn cứ | Khắc phục sai | Causal analysis/evidence |
| Tự động xóa finding sau deploy | Không chứng minh control | Re-test và sign-off |

### 26.1. Sửa finding không phải sửa số liệu

Một dashboard có ít finding không có nghĩa quyền thực tế an toàn. Phải tập trung **control hiệu quả, coverage đầy đủ, entitlement đúng và evidence truy xuất được**.

### 26.2. Không biến retrospective audit thành sự cố giả

Nếu condition chỉ là thiếu evidence, không nên khẳng định có breach. Ngược lại, nếu có actual residual permission nguy hiểm đang dùng được, phải xử lý khẩn theo policy, không chỉ mở ticket chờ kỳ audit.

## 27. Ma trận kiểm thử Finding và CAPA

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Observation không có criteria | Chưa phát hành finding chính thức |
| Criteria đã hết hiệu lực trước kỳ audit | Dùng đúng version hoặc điều chỉnh |
| User được tạo sớm nhưng DISABLED đúng policy | Không tự coi Joiner violation |
| User có production access trước effectiveAt | Finding nếu trái control |
| Mover role mới thêm, role cũ còn | Condition về residual entitlement |
| Leaver đã IdP disable nhưng SaaS local role còn | Condition theo target scope |
| SCIM ACK nhưng chưa có readback | Evidence gap/PENDING |
| Group A gỡ nhưng grant B hợp lệ còn | Đánh giá đúng expected access |
| Direct role ngoài IdP | Đưa vào inventory/condition |
| Reviewer tự KEEP admin trái SoD | Invalid review decision |
| REVOKE decision chưa thực thi | Remediation finding |
| Access review campaign bỏ service accounts | Coverage finding |
| Service principal owner Leaver | Reassign owner và rà grants |
| Workload retired vẫn lấy token mới | Finding trust/issuance tồn dư |
| IdP session hết nhưng RP vẫn active | Re-evaluate theo session SLA |
| SAML/OIDC mapping dựa email dễ nhầm | Điều tra issuer/subject mapping |
| API logs không có sau cutoff | Không kết luận không có misuse |
| Evidence source trả timeout | UNKNOWN, không PASS |
| Auditor lấy mẫu risk-based | Không suy tỷ lệ toàn dân số vô căn cứ |
| Một account có nhiều grants | Đếm đúng audit unit |
| Một finding có nhiều action tickets | Không nhân số finding |
| Severity tăng do evidence mới | Lưu history và authority |
| CAPA chỉ xử lý đúng mẫu | Không pass systemic acceptance |
| CAPA đã deploy nhưng retest FAIL | Giữ OPEN/RETEST_FAILED |
| Retest thiếu target evidence | Không VERIFIED_CLOSED |
| Owner tự duyệt exception không đủ quyền | Reject/ESCALATE |
| Exception đã hết hạn | Alert và đánh giá lại |
| Risk accepted | Không giả thành resolved control |
| Finding closed rồi quyền tái xuất hiện | Link recurrence/REOPENED |
| Hai tenant cùng local ID | Không gộp identity |
| Dashboard không có data vì pipeline lỗi | Alert pipeline gap |
| Finding log bị sửa/xóa | Tamper alert hoặc integrity failure |
| User tenant A đọc finding tenant B | Authorization DENY |
| Due date bị sửa không approval | Phát hiện và bảo toàn original |
| Historical report as-of quý cũ | Không dùng retest events tương lai |
| Mẫu số bằng 0 | Rate = N/A, không 100% |
| Critical finding còn OPEN | Hiển thị riêng bất kể closure tổng |

### 27.1. Kiểm thử bảo mật hệ thống audit

Audit tool cũng cần RBAC/ABAC, tenant isolation, retention policy, evidence references và logging thao tác của auditor/owner. Không để một action owner vừa sửa cấu hình IAM vừa âm thầm xóa finding và evidence.

### 27.2. Kiểm thử sự chính xác của nguyên nhân

Một finding “SCIM không revoke” có thể thực ra do target direct role nằm ngoài SCIM scope. Retest phải đánh giá nguồn grant và desired state, tránh sửa nhầm module.

### 27.3. Test bằng dữ liệu không nhạy cảm

Sử dụng fixtures, principals và hệ thống được cấp phép; không cần truy cập session token hoặc secret thật để trình bày hay xác minh logic finding.

## 28. Bài tập tự đánh giá

### A. Leaver quá hạn nhưng không có log đăng nhập

Một tài khoản vẫn active sau cutoff, không thấy sign-in nào.

**Cách xử lý:** Nếu criteria yêu cầu disable đúng hạn, đó có thể là finding dù không có sign-in. Không khẳng định đã có data theft. Thu thập account state, role/credential scope, policy và thời gian, rồi yêu cầu revoke/readback.

### B. Mover role cũ còn vì group lồng

SCIM gỡ một group nhưng nested group khác tiếp tục cấp role.

**Cách xử lý:** Finding về effective entitlement reconciliation và role mapping. Phân biệt grant source, sửa policy/connector và test quyền thực tế.

### C. Campaign recertification 100% KEEP

Reviewer hoàn tất mọi task đúng hạn, nhưng nhiều quyền privileged không có justification.

**Cách xử lý:** Decision completion cao không chứng minh quality. So sánh với criteria reviewer authority/justification, đánh giá severity và kiểm soát bù trừ.

### D. API key của job không có owner

Một integration vẫn chạy, engineer tạo key đã nghỉ.

**Cách xử lý:** Kiểm tra workload business need, chuyển owner, thu hồi human vault access, rà key/trust/role; không tắt workload production vô điều kiện.

### E. Control owner đã sửa code

Ticket ghi “Merged” và “Deployed”, nhưng không có target readback.

**Cách xử lý:** Action có thể đã implemented; finding chưa đủ VERIFIED_CLOSED cho tới khi retest đạt.

### F. Severity ban đầu Low, sau đó tìm thấy cloud-admin

Evidence mới cho thấy quyền cao hơn giả định.

**Cách xử lý:** Re-rate theo rubric, giữ lịch sử, cân nhắc containment khẩn và cập nhật CAPA.

### G. Ngoại lệ do vendor không hỗ trợ session revoke

Risk owner chấp thuận kiểm soát tạm trong 30 ngày.

**Cách xử lý:** Lưu time-bound exception, test hiệu lực control bù trừ, theo dõi expiry và kế hoạch sửa; không xóa finding lịch sử.

### H. Auditor thiếu dữ liệu 30% hệ thống

SIEM không có logs từ ba SaaS.

**Cách xử lý:** Công bố scope limitation/evidence gap, không suy “không có lỗi”; xem finding về auditability nếu policy yêu cầu, khắc phục pipeline/inventory.

## 29. Checklist viết và đóng Audit finding IAM

1. **Bài toán:** finding liên quan identity, entitlement, session hay logging?
2. **Criteria:** có chính sách/control có thẩm quyền và version?
3. **Period:** effective dates và audit window đúng?
4. **Population:** biết toàn bộ inventory thuộc phạm vi?
5. **Sampling:** method được ghi rõ, không suy rộng tùy tiện?
6. **Identity mapping:** dùng immutable IDs và target namespace?
7. **Condition:** nêu hành vi/trạng thái sai một cách đo được?
8. **Numerator/denominator:** định nghĩa đơn vị đếm và cohort?
9. **Evidence:** có nguồn, timestamp, version, collector, integrity?
10. **Freshness:** target readback đủ mới và đúng scope?
11. **Trust:** source logs và event producers đáng tin?
12. **Cause:** root cause được kiểm chứng, không đổ lỗi cảm tính?
13. **Effect:** tách observed impact với potential risk?
14. **Severity:** áp rubric có version và risk factors?
15. **Owner:** finding, control, action và risk owner rõ?
16. **Management response:** có xác nhận/ý kiến phản biện và chứng cứ?
17. **JML:** Joiner/Mover/Leaver được xét theo effectiveAt?
18. **IdP/SSO:** login và RP session không bị coi là một quyền duy nhất?
19. **SCIM:** ACK không thay hiệu lực target?
20. **RBAC/ABAC:** role, attribute, resource, tenant và quyền kế thừa?
21. **Non-human:** service principal/API key/owner/trust có trong inventory?
22. **Access review:** coverage, valid decision, remediation đủ?
23. **Privilege:** JIT/PAM/admin SoD được kiểm tra khi phù hợp?
24. **Residual access:** đo đường quyền thật còn sau cutoff?
25. **Immediate correction:** các quyền sai đã biết được xử lý?
26. **Systemic CAPA:** nguyên nhân chính đã được sửa?
27. **Acceptance criteria:** có định nghĩa pass có thể kiểm chứng?
28. **DueAt:** deadline, dependencies, extensions có audit?
29. **Compensating control:** có test hiệu lực thay vì chỉ mô tả?
30. **Exception:** được phê duyệt, time-bound và có owner?
31. **Retest:** có tester, method, scope, outcome, evidenceRefs?
32. **Independent review:** đủ thẩm quyền/khách quan theo policy?
33. **History:** failed retests và severity changes không bị xóa?
34. **Closure:** không coi action DONE là finding VERIFIED_CLOSED?
35. **Reopen:** recurrence/drift liên kết finding gốc?
36. **Audit security:** không log raw tokens/secrets/PII dư thừa?
37. **Access control:** người xem finding/evidence có quyền theo tenant?
38. **Retention:** logs và evidence có hạn phù hợp/pháp lý áp dụng?
39. **Dashboard:** báo Critical open, overdue và coverage song song?
40. **Reporting:** as-of, metric versions, original cohort được giữ?
41. **Testing:** negative cases, out-of-order, stale roles, timeout được xét?
42. **Governance:** không đổi criteria hoặc mẫu số âm thầm?
43. **Incident path:** quyền nguy hiểm đang usable có escalation ngay?
44. **Outcome:** có bằng chứng rủi ro thực sự giảm?

## 30. Tổng kết

**Audit finding trong Identity Audit** là một kết luận được quản trị, dựa trên **criteria, condition, evidence, cause, impact/risk và corrective actions**. Một finding hữu ích không chỉ “nêu lỗi”, mà phải đủ rõ để biết **kiểm soát nào không đạt, ai chịu trách nhiệm và làm sao chứng minh đã khắc phục**.

- **Criteria:** yêu cầu nào thật sự có hiệu lực trong kỳ kiểm tra.
- **Condition:** sai lệch có thể tái hiện, đúng identity/entitlement/tenant/period.
- **Evidence:** đáng tin, đủ phạm vi và có provenance.
- **Cause:** lỗi thiết kế, vận hành, mapping hay khả năng kiểm chứng.
- **Risk:** tách tác động quan sát được khỏi hệ quả tiềm tàng.
- **CAPA:** vừa xử lý sai lệch hiện tại vừa ngăn tái diễn.
- **Retest:** kiểm tra hiệu lực target và control, không đóng theo cảm tính.

Trong IAM theo **Joiner–Mover–Leaver**, audit finding có thể liên quan preboarding sai thời điểm, quyền Mover tồn dư, Leaver chưa thu hồi, access recertification hình thức, IdP/SSO/SCIM không đồng bộ, RBAC/ABAC quá rộng, tài khoản dịch vụ mồ côi hoặc logging thiếu bằng chứng.

**Ghi nhớ:** **Một finding không kết thúc khi ticket báo “Done”; nó chỉ được đóng khi tiêu chí kiểm soát đã được chứng minh đạt trong phạm vi có thẩm quyền, nguyên nhân được giải quyết hoặc residual risk được quản trị minh bạch.** Audit có giá trị khi giúp **giảm quyền truy cập tồn dư và ngăn sai lệch tái diễn**, không chỉ cải thiện số liệu trên dashboard.







