# Dự án thực hành: Viết runbook IAM

## 1. Bối cảnh và sản phẩm cần bàn giao

**Runbook IAM** là tài liệu thao tác vận hành có thể thực hiện lặp lại, giúp nhóm phụ trách danh tính xử lý sự kiện **Joiner–Mover–Leaver (JML)**, sự cố cấp/thu hồi quyền, yêu cầu khẩn cấp và đối soát trạng thái. Một runbook tốt phải trả lời: **khi nào kích hoạt, ai được làm, kiểm tra điều kiện gì, thực hiện bước nào, xác minh bằng chứng gì, xử lý lỗi ra sao và khi nào được đóng yêu cầu**.

Đây là dự án thực hành trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Hệ thống giả lập tích hợp HRIS, bộ điều phối IAM, Identity Provider (IdP), SSO, SCIM, chính sách RBAC/ABAC, ứng dụng đích, tài khoản dịch vụ và hệ thống audit. Mục đích không phải viết hướng dẫn bấm nút cho một sản phẩm cụ thể mà là thiết kế **runbook an toàn, có thể kiểm thử, có trách nhiệm rõ ràng**, đặc biệt giảm quyền truy cập tồn dư khi nhân sự thay đổi vai trò hoặc rời tổ chức.

**Đầu ra tối thiểu cần nộp**:

1. Một runbook vận hành chính gồm phiên bản, owner, phạm vi, điều kiện kích hoạt, bước triển khai, điểm dừng, đường escalation và rollback/compensation.
2. Ba thủ tục JML: tạo quyền cho Joiner, cập nhật quyền cho Mover, thu hồi quyền cho Leaver.
3. Một thủ tục xử lý lỗi SCIM/IdP và một thủ tục emergency disable.
4. Bảng kiểm tra kết quả ở IdP và ứng dụng đích, không chỉ trạng thái workflow.
5. Ma trận RACI, ma trận test case, mẫu audit evidence và báo cáo diễn tập.

Đây là bài thực hành với dữ liệu giả; mọi yêu cầu sửa quyền trên hệ thống sản xuất phải theo quy trình phê duyệt và phân quyền thực tế.

## 2. Tình huống giả lập

Tổ chức giả định **Northwind Labs** có khoảng 500 nhân sự, một HRIS làm nguồn dữ liệu chuẩn, một IdP dùng SSO/MFA, ứng dụng CRM qua SCIM, ứng dụng Finance qua API riêng và một bot triển khai CI/CD.

Chính sách giả lập:

| Đối tượng | Điều kiện | Quyền được phép |
|---|---|---|
| Sales VN | Active, phòng Sales, vùng VN | Đọc CRM VN; không xuất toàn bộ dữ liệu |
| Finance | Active, thuộc Finance, được duyệt | Xem báo cáo Finance; không giữ quyền Sales không cần thiết |
| Admin tạm thời | Phê duyệt riêng, có thời hạn | Quyền đúng phạm vi; hết hạn phải thu hồi |
| Contractor | Hợp đồng còn hiệu lực | Chỉ quyền dự án được duyệt |
| Leaver | Đã đến thời điểm chấm dứt | Không còn quyền truy cập tương tác; session/token theo SLA |
| Bot CI/CD | Có owner và mục đích rõ ràng | Quyền máy tối thiểu, quản lý credential riêng |

Những role, ngày hiệu lực và SLA trong bài là **giả định để luyện tập**, không phải chính sách chuẩn cho doanh nghiệp khác.

Các sự kiện mẫu:

~~~yaml
events:
  - eventId: join-101-v1
    version: 1
    personId: test-person-101
    type: JOINER
    department: SALES
    region: VN
    verified: true
    effectiveAt: "2026-12-01T09:00:00+07:00"
  - eventId: move-102-v8
    version: 8
    personId: test-person-102
    type: MOVER
    fromDepartment: SALES
    toDepartment: FINANCE
    effectiveAt: "2026-12-03T09:00:00+07:00"
  - eventId: leave-103-v12
    version: 12
    personId: test-person-103
    type: LEAVER
    effectiveAt: "2026-12-04T18:00:00+07:00"
~~~

Không dùng email/tên hiển thị làm khóa liên kết duy nhất; nên dùng `personId` hoặc ID nguồn ổn định. Các mốc thời gian phải có timezone và được đối chiếu với đồng hồ nhất quán.

## 3. Cấu trúc chuẩn của một runbook

Mỗi runbook phải chứa metadata và các phần sau:

| Trường | Nội dung bắt buộc |
|---|---|
| `runbookId`, `version` | Mã định danh và phiên bản tài liệu |
| `owner`, `reviewer` | Nhóm chịu trách nhiệm và người duyệt nội dung |
| `scope` | Ứng dụng, danh tính, môi trường nằm trong phạm vi |
| `trigger` | Event HRIS, cảnh báo, ticket hoặc lệnh khẩn cấp hợp lệ |
| `prerequisites` | Xác minh danh tính, thẩm quyền, policy, phê duyệt, kết nối |
| `safetyChecks` | Điểm kiểm tra tránh thao tác sai người, sai quyền, sai hệ thống |
| `procedure` | Bước thực thi cụ thể, đầu vào và kết quả từng bước |
| `verification` | Readback, thử truy cập ALLOW/DENY, SLA |
| `failureHandling` | Retry, cảnh báo, escalation, compensation |
| `evidence` | Correlation ID, event ID, audit, timestamp, kết quả |
| `closureCriteria` | Điều kiện PASS và người xác nhận |
| `reviewCycle` | Ngày rà soát lại tài liệu sau thay đổi hệ thống |

### Mẫu đầu runbook

~~~yaml
runbookId: IAM-JML-OPERATIONS
version: "1.0-draft"
owner: IAM Operations
reviewer: Security Engineering
environment: sandbox
scope:
  - HRIS
  - IdP
  - CRM-SCIM
  - Finance-API
trigger: Approved lifecycle event or authorized incident
requiredEvidence:
  - eventId
  - personId
  - policyVersion
  - approver
  - correlationId
  - observedAccess
~~~

Đừng ghi token, mật khẩu hoặc private key trực tiếp trong runbook hay ticket; chỉ ghi tham chiếu tới secret manager và bằng chứng không chứa bí mật.

## 4. Xây dựng ma trận trách nhiệm RACI

Một thủ tục chỉ an toàn khi xác định ai có quyền yêu cầu, phê duyệt, thực hiện và xác minh.

| Công việc | HR | Manager | IAM Ops | App Owner | Security |
|---|---|---|---|---|---|
| Xác nhận Joiner/Leaver | A/R | C | I | I | I |
| Phê duyệt quyền nghiệp vụ | C | A/R | C | C | C |
| Thực thi provisioning | I | I | A/R | C | C |
| Xác nhận quyền ứng dụng | I | C | R | A/R | C |
| Quyền đặc biệt / SoD exception | I | C | R | C | A |
| Emergency disable | C | I | R | C | A |
| Đối soát quyền tồn dư | I | C | R | A/R | C |

R = Responsible, A = Accountable, C = Consulted, I = Informed. Đây là ma trận gợi ý cho lab, cần điều chỉnh theo cơ cấu tổ chức. Người thực hiện không mặc nhiên có quyền tự phê duyệt ngoại lệ của mình.

## 5. Runbook Joiner: tạo identity và cấp quyền

**Trigger:** có sự kiện nguồn hợp lệ cho nhân sự mới, được xác minh, đã tới ngày hiệu lực và có phê duyệt bắt buộc.

### Trước khi thao tác

1. Xác minh event ID, person ID, hợp đồng, trạng thái HR, `effectiveAt`, phiên bản sự kiện.
2. Tra cứu tài khoản hiện hữu theo khóa ổn định để tránh duplicate nếu email thay đổi.
3. Tính entitlement theo RBAC/ABAC; kiểm tra least privilege và xung đột SoD.
4. Kiểm tra approval của role nhạy cảm và expiry nếu có.
5. Ghi correlation ID, policy version và danh sách target.

### Thực thi

1. Tạo hoặc liên kết identity tại IdP, không cấp quyền vượt phạm vi.
2. Áp dụng nhóm, thuộc tính và điều kiện MFA/SSO.
3. Gửi provisioning tới CRM qua SCIM và Finance qua connector nếu có quyền phù hợp.
4. Đọc lại trạng thái user, nhóm, role ở từng target.
5. Dùng tài khoản giả kiểm tra một hành động ALLOW và ít nhất hai hành động DENY.
6. Ghi kết quả từng target; chỉ đóng khi hoàn tất các target bắt buộc.

**Điểm dừng:** thiếu nguồn xác minh, identity trùng không thể phân giải, approval thiếu hoặc SoD vi phạm. Khi connector thất bại, không tự tạo tài khoản thứ hai; tra cứu theo `externalId` rồi retry/reconcile.

**PASS:** identity ổn định, account đúng trạng thái, đủ quyền hợp lệ, không có quyền ngoài phạm vi, audit có thể truy vết.

## 6. Runbook Mover: thay đổi quyền không tích lũy entitlement

**Trigger:** HRIS cập nhật phòng ban, vai trò, vùng hoặc loại hợp đồng.

### Phân tích trước khi cấp/thu hồi

~~~text
before = effectivePermissions(personId)
desiredAfter = policy(verifiedCurrentAttributes, approvals)
toAdd = desiredAfter - before
toRemove = before - desiredAfter
~~~

1. Xác nhận event mới hơn trạng thái đã xử lý; không dùng sự kiện cũ ghi đè dữ liệu hiện tại.
2. Kiểm tra danh tính không ở trạng thái Leaver/suspended có hiệu lực.
3. Xác định quyền cần giữ, thêm, gỡ và quyền ngoại lệ còn hiệu lực.
4. Với role xung đột SoD, phải xử lý thu hồi hoặc phê duyệt ngoại lệ trước khi mở quyền mới.
5. Thực hiện ở IdP và ứng dụng, kiểm tra nested groups/direct grants.
6. Thử phiên cũ và phiên mới; bảo đảm quyền bị gỡ không còn tác dụng quá SLA.

**Không mặc định “gỡ role tại IdP” là đã thu hồi quyền**: ứng dụng có thể giữ role cục bộ, cookie hoặc token mang claim cũ. Runbook cần kiểm tra quyền hiệu lực ở API.

**PASS:** tập quyền cuối khớp `desiredAfter`, các quyền không hợp lệ bị từ chối, không có quyền cũ tích lũy sau nhiều lần Mover.

## 7. Runbook Leaver: thu hồi quyền và xử lý bàn giao

**Trigger:** sự kiện nghỉ việc, chấm dứt hợp đồng hoặc yêu cầu khóa khẩn cấp đã được xác thực.

### Thao tác theo mức độ ưu tiên

1. Xác minh person ID, nguồn lệnh, thời điểm hiệu lực và loại Leaver; ngăn thao tác nhầm người.
2. Khi Leaver có hiệu lực, chặn đăng nhập mới ở IdP theo SLA.
3. Xử lý refresh token, access token, SSO session và phiên ứng dụng theo kiến trúc revocation/expiry.
4. Gửi deactivate qua SCIM và gỡ groups, roles, ACL, direct grants.
5. Kiểm tra tài khoản local, VPN, PAT, SSH keys, API keys và chứng chỉ theo phạm vi kiểm soát.
6. Bàn giao dữ liệu, quyền owner của repository, bot/service account và tài sản theo chính sách.
7. Kiểm tra đăng nhập mới và các hành động dùng phiên/credential cũ đều bị chặn trong deadline được phê duyệt.
8. Đối soát mọi target, ghi cảnh báo và remediation nếu còn quyền tồn dư.

**Phân biệt disable và delete:** giữ dữ liệu hoặc tài khoản inactive để bảo toàn chứng cứ có thể là yêu cầu hợp lệ; đừng xóa vội tài khoản máy hoặc tài liệu công việc. Một JWT self-contained có thể còn hiệu lực đến `exp` nếu resource server không hỗ trợ thu hồi sớm; runbook phải nêu chính xác giới hạn và biện pháp giảm rủi ro.

**PASS:** không còn truy cập trái phép sau SLA; mọi lỗi từng phần có owner, deadline và bằng chứng xử lý.

## 8. Runbook emergency disable

Emergency disable áp dụng khi có sự cố như nghi lộ tài khoản, chấm dứt khẩn cấp hoặc phát hiện hành vi truy cập trái phép. Mục tiêu đầu tiên là **containment**, không phải hoàn tất bàn giao.

~~~mermaid
flowchart TD
    A[Yêu cầu / cảnh báo sự cố] --> B[Kiểm tra nguồn và thẩm quyền]
    B --> C[Khóa danh tính / hạn chế truy cập tức thời]
    C --> D[Revoke session, token, credential khả thi]
    D --> E[Chặn tài nguyên nhạy cảm / cảnh báo ứng dụng]
    E --> F[Kiểm tra API và nhật ký truy cập]
    F --> G{Đã chặn đúng phạm vi?}
    G -->|Chưa| H[Escalate incident commander]
    G -->|Rồi| I[Chuyển workflow offboarding / điều tra]
~~~

**Điểm an toàn:** nếu không xác thực được thẩm quyền yêu cầu, không thực hiện khóa tùy tiện trên hệ thống thật; chuyển xác minh qua kênh sự cố đã quy định. Đối với sự cố có căn cứ khẩn cấp, chính sách có thể cho phép người chịu trách nhiệm trực ca khóa trước và hoàn thiện phê duyệt sau; quyền này phải được quy định rõ.

Sau containment, cần thu thập bằng chứng không chứa secret, thông báo owner, xem xét credential rotation và kiểm soát việc mở khóa lại. Chỉ phục hồi account khi xác minh được chủ thể, lý do, trạng thái HR và phê duyệt hợp lệ.

## 9. Runbook xử lý lỗi SCIM/connector

Một lỗi đặc trưng là connector timeout sau khi ứng dụng đã thực hiện thao tác. Không được tự động cho rằng yêu cầu chưa chạy.

~~~mermaid
sequenceDiagram
    participant I as IAM
    participant A as SCIM App
    participant R as Reconciler
    I->>A: Create/update/deactivate
    A--xI: Timeout
    I->>R: Mark PENDING, attach correlationId
    R->>A: GET/Search by stable externalId
    A-->>R: Actual user/groups/active
    R->>R: Diff actual vs approved desired state
    R->>A: Idempotent correction if needed
    A-->>R: Applied
    R->>A: Readback and access verification
    A-->>R: Expected state
~~~

### Bảng xử lý

| Lỗi | Hành động runbook | Điều kiện đóng |
|---|---|---|
| Timeout | Lookup trạng thái thực trước retry | Trạng thái cuối đúng, không duplicate |
| `429` | Backoff theo Retry-After nếu có, giới hạn retry | Hội tụ trước SLA hoặc escalation |
| `5xx` | Retry có backoff, theo dõi target | Readback và audit thành công |
| `409` | Kiểm tra trùng ID/mapping; không tự hợp nhất | Đúng người, đúng account |
| `404` | Xác minh mapping và thực trạng quyền | Không còn quyền bị cấm hoặc đã sửa mapping |
| Schema/mapping lỗi | Tạm dừng thao tác rủi ro, sửa và kiểm thử lại | Không thay đổi sai người hoặc entitlement |
| Một target thất bại | Ghi partial failure, alert owner | Có remediation và xác minh đích |

Retry phải có ngân sách, giới hạn và dead-letter/escalation khi thất bại. Không dùng vòng lặp vô hạn hoặc cấp lại quyền khi source đã Leaver.

## 10. Runbook reconciliation và phát hiện quyền tồn dư

Reconciliation dùng dữ liệu chính sách hiện hành và inventory thực tế để tìm tài khoản mồ côi, nhóm không còn phù hợp, quyền cấp trực tiếp hoặc service account thiếu owner.

~~~text
expected = policy.calculate(authoritativeIdentityState, approvedExceptions)
actual = inventory.effectiveGrants(idp, apps, localRoles, directACLs)

unexpected = actual - expected
missing = expected.required - actual
orphanAccounts = inventory.activeAccounts - expected.authorizedActiveAccounts
~~~

### Thủ tục

1. Thu thập snapshot từ HRIS, IdP, ứng dụng và inventory service identities với timestamp.
2. Kiểm tra kết nối/pagination để không coi dữ liệu thiếu là “không có quyền”.
3. Tính `unexpected`, `missing`, kiểm tra SoD và entitlement hết hạn.
4. Phân loại ưu tiên: quyền admin tồn dư, Leaver còn active, quyền dữ liệu nhạy cảm, quyền nghiệp vụ thông thường.
5. Tạo ticket có owner và bằng chứng; quyền nguy hiểm cần containment theo chính sách.
6. Áp dụng thay đổi có phê duyệt phù hợp, đọc lại và thử API.
7. Chốt finding sau khi đã kiểm tra access thực tế, không chỉ sau khi connector trả thành công.

Một account inactive vẫn còn dữ liệu lưu trữ không nhất thiết là sai; cần phân biệt **tài khoản được giữ vì retention** với **đường truy cập vẫn có hiệu lực**.

## 11. Runbook service account và machine identity

Service accounts, CI/CD bot và workload identities không được quản lý y hệt người dùng. Runbook riêng cần mô tả owner, business purpose, quyền được duyệt, môi trường được phép, phương thức xác thực, expiry, rotation và xử lý khi owner Mover/Leaver.

Trình tự minh họa khi owner bot nghỉ việc:

1. Tra cứu tất cả service principal, repository, deployment secret và integration do người đó sở hữu.
2. Phân công owner mới có thẩm quyền; phê duyệt chuyển giao và giữ audit trail.
3. Thu hồi quyền người cũ vào vault, CI/CD và ứng dụng quản lý.
4. Rotation secret/key nếu chính sách đòi hỏi hoặc có rủi ro đã bị biết; cập nhật consumer hợp lệ.
5. Thử bot hoạt động bình thường với credential mới và xác minh credential cũ không còn dùng được.
6. Đối soát service identity không còn owner và thiết lập chu kỳ rà soát quyền.

Không tự động xóa service account đang chạy tiến trình quan trọng chỉ vì owner là Leaver; cần quyết định disposition dựa trên phụ thuộc dịch vụ.

## 12. Mẫu checklist vận hành

Sao chép checklist sau vào ticket thử nghiệm:

~~~markdown
### IAM Operation Checklist
- [ ] Event/request hợp lệ; ID và version chính xác
- [ ] Đúng personId và trạng thái nguồn hiện hành
- [ ] effectiveAt và timezone đã được kiểm tra
- [ ] RBAC/ABAC, approval và SoD đã được đánh giá
- [ ] Danh sách target và owner xử lý đã xác định
- [ ] Thực thi IdP và SCIM/API đúng phạm vi
- [ ] Đã readback account, group, direct grants ở từng target
- [ ] Kiểm thử ALLOW và DENY tại API/PEP
- [ ] Session/token/credential cũ đã được xử lý theo SLA
- [ ] Lỗi từng phần/retry đã có remediation
- [ ] Service account/asset ownership đã được bàn giao khi cần
- [ ] Audit và correlationId đầy đủ, không chứa secret
- [ ] Người có thẩm quyền xác nhận điều kiện đóng
~~~

Nếu một bước không áp dụng, ghi `N/A` với lý do. Không đánh dấu hoàn tất mặc định khi chưa có chứng cứ kiểm chứng.

## 13. Kịch bản diễn tập và tiêu chí kiểm thử runbook

| ID | Diễn tập | Kỳ vọng |
|---|---|---|
| RB01 | Joiner hợp lệ | Có đúng quyền Sales VN, không có quyền admin |
| RB02 | Joiner bị gửi trùng | Một identity, không duplicate entitlement |
| RB03 | Mover Sales → Finance | Quyền Finance đủ dùng, quyền Sales hết hiệu lực |
| RB04 | Leaver theo lịch | Đăng nhập mới và quyền cũ bị chặn đúng hạn |
| RB05 | Leaver khẩn cấp | Containment và escalation hoạt động đúng |
| RB06 | SCIM timeout sau thao tác thành công | Lookup, retry và reconcile không tạo bản sao |
| RB07 | Event Mover cũ đến sau Leaver | Không phục hồi quyền cũ |
| RB08 | Token/session còn hiệu lực | Phát hiện hoặc chặn theo SLA |
| RB09 | Service bot có owner rời đi | Owner mới hợp lệ, quyền người cũ mất |
| RB10 | Ứng dụng đích không kết nối | Báo partial failure, không đóng giả thành công |
| RB11 | Role cục bộ còn sau gỡ group | Reconciliation phát hiện quyền tồn dư |
| RB12 | Audit log thiếu hoặc lộ secret | Không đủ điều kiện đóng; yêu cầu sửa |

Một runbook được coi là **có thể sử dụng** khi người không tham gia soạn tài liệu vẫn thực hiện được kịch bản với dữ liệu đầu vào rõ ràng, biết điểm dừng/escalation, xác minh quyền tại đích và ghi evidence. Không chỉ đánh giá “đã chạy hết bước” mà phải đánh giá kết quả bảo mật.

## 14. Mẫu báo cáo sau diễn tập

~~~markdown
# IAM Runbook Drill Report

Runbook ID / Version:
Date / Environment:
Executor / Approver:
Event IDs / Correlation IDs:
Policy version:

| Case ID | Trigger | Expected | Actual | ObservedAt | Evidence | Status |
|---|---|---|---|---|---|---|
| RB01 | JOINER | Sales VN ALLOW, Export DENY | ... | ... | ... | ... |
| RB03 | MOVER | Finance ALLOW, Sales DENY | ... | ... | ... | ... |
| RB04 | LEAVER | Sign-in DENY | ... | ... | ... | ... |

Findings:
- Severity / owner / action / due date / verification:

Lessons learned:
- Bước chưa rõ:
- Chỗ cần tự động hóa:
- Chỗ cần giám sát:

Review approval:
~~~

Không đưa bí mật, mã OTP hoặc token thật vào bằng chứng. Với lỗi chưa khắc phục, ghi chính xác trạng thái và owner thay vì gắn nhãn PASS.

## 15. Tiêu chí nghiệm thu dự án

Nhóm học viên tự đánh giá bài nộp theo những tiêu chí:

| Tiêu chí | Điểm tối đa | Điều kiện đạt |
|---|---:|---|
| Runbook có đầy đủ metadata, owner, trigger, điều kiện và scope | 15 | Có thể tìm đúng tài liệu và biết ai chịu trách nhiệm |
| JML có điều kiện dừng, cấp/thu hồi đúng quyền | 25 | Joiner/Mover/Leaver theo least privilege và nguồn trạng thái |
| Xử lý lỗi và an toàn retry/replay | 15 | Không duplicate, không phục hồi stale grants |
| Kiểm tra effective access | 15 | Có readback và ALLOW/DENY thực tế |
| Service account và handover | 10 | Có owner, secret rotation và kiểm tra continuity |
| Audit, evidence, escalation | 10 | Truy vết được và không lộ secret |
| Diễn tập và báo cáo findings | 10 | Có kết quả PASS/FAIL và kế hoạch remediation |
| **Tổng** | **100** | **Đạt từ 80 điểm và không có lỗi thu hồi quyền nghiêm trọng chưa xử lý** |

Điểm số là rubric cho bài học; ngưỡng triển khai thật do tổ chức quyết định. Các lỗi như cho Leaver truy cập lại, bỏ qua phê duyệt đặc quyền hoặc thu hồi nhầm người phải được sửa trước khi coi runbook đủ an toàn, bất kể tổng điểm.

## 16. Câu hỏi tự đánh giá

1. Vì sao trạng thái `active=false` ở SCIM chưa chứng minh quyền truy cập đã bị thu hồi?
2. Khi sự kiện Mover cũ đến sau Leaver, runbook dùng dữ liệu nào để ngăn cấp quyền trở lại?
3. Có cần xóa ngay service account khi owner nghỉ việc không? Vì sao?
4. Nếu ứng dụng trả timeout sau khi đã tạo user, thao tác an toàn tiếp theo là gì?
5. Bằng chứng nào cho phép đóng một yêu cầu revoke quyền nhạy cảm?
6. Khi token JWT cũ vẫn hợp lệ, runbook phải mô tả giới hạn và biện pháp xử lý như thế nào?
7. Ai có quyền duyệt ngoại lệ SoD, và tại sao người thực hiện không nên tự duyệt?

**Kết luận:** Runbook IAM tốt không chỉ giúp nhóm vận hành hoàn thành các bước Joiner–Mover–Leaver. Nó phải hướng dẫn nhân sự **ra quyết định đúng, thực thi quyền chính xác, phát hiện lỗi tích hợp, thu hồi quyền tồn dư và chứng minh kết quả bằng audit/readback**. Đây là yêu cầu cốt lõi để vòng đời danh tính vận hành nhất quán và có thể kiểm toán.
