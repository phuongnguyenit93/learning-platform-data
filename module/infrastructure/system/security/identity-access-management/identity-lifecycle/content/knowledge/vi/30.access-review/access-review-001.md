# Access review là gì? Rà soát quyền truy cập để giữ đúng quyền và thu hồi quyền không còn căn cứ

**Access review (rà soát quyền truy cập)** là quy trình có kiểm soát nhằm **đánh giá lại các quyền đã được cấp** cho người dùng, tài khoản, dịch vụ hoặc workload để xác định **quyền nào vẫn cần thiết, phù hợp chính sách và phải được giữ, sửa, thu hồi hoặc chuyển xử lý ngoại lệ**. Việc đánh giá dựa trên **nhiệm vụ hiện tại, trạng thái danh tính, chủ sở hữu tài nguyên, mức rủi ro, bằng chứng sử dụng/quản trị và yêu cầu bảo mật**.

Nhiều tổ chức còn gọi hoạt động này là **access certification**, **entitlement review**, **user access review (UAR)** hoặc **recertification**. Các thuật ngữ có thể khác nhau theo sản phẩm hoặc phạm vi, nhưng điểm chung là **người có thẩm quyền tái xác nhận căn cứ của quyền đang tồn tại**, thay vì mặc nhiên tin rằng một quyền đã từng được phê duyệt thì luôn hợp lệ.

Bài học thuộc chương **Access review** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun tập trung quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh người, tạo account, cấp quyền, rà soát và thu hồi khi thay đổi vai trò hoặc kết thúc quan hệ làm việc. Access review kết nối **HR/VMS, IAM/IGA, IdP/SSO, directory, SCIM, RBAC/ABAC, tài khoản dịch vụ, PAM/PIM và kiểm toán** để giảm **quyền truy cập tồn dư**.

**Thông điệp quan trọng:** Một chiến dịch review chỉ hoàn tất về mặt bảo mật khi **quyết định đã được triển khai và kiểm chứng**. Dấu chọn “Revoke” trong giao diện, email thông báo hay phản hồi API thành công **chưa tự chứng minh quyền thực tế ở hệ thống đích đã mất**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **access review**, phân biệt với **access request, approval, access certification, provisioning, continuous monitoring và audit**.
2. Xác định **ai được review, review những quyền gì, ở ứng dụng/tài nguyên nào, vào thời điểm nào**.
3. Mô tả các vai trò **reviewer, manager, business owner, application/data owner, IAM/IGA, security, provisioning operator và auditor**.
4. Thiết kế review theo **risk tier, sự kiện JML, thời hạn, vai trò đặc quyền, loại subject và nguồn cấp quyền**.
5. Phân biệt **assigned entitlement, effective access, direct grant, nhóm lồng nhau, role kế thừa, local ACL, session và token**.
6. Hiểu các quyết định **KEEP, REVOKE, MODIFY, ESCALATE/NEEDS_INFORMATION** cùng trách nhiệm thực thi.
7. Đọc báo cáo review, nhận diện **orphan account, privilege creep, SoD conflict, quyền không sử dụng, quyền sai tenant và exception quá hạn**.
8. Xây dựng quy trình **campaign → review decision → remediation → readback → evidence → closure**.
9. Áp dụng access review trong **Joiner–Mover–Leaver**, kể cả nhà thầu, IdP liên kết và **service account/workload**.
10. Xác định chỉ số, bằng chứng và kiểm soát để review không trở thành thủ tục “đồng ý hàng loạt”.

## 2. Access review là gì và không phải là gì?

Một ví dụ đơn giản: Hệ thống CRM đang ghi nhận nhân viên An có quyền `customer.export`. Một năm trước An thuộc bộ phận phân tích thị trường; hiện An đã chuyển sang vận hành nội bộ. **Access review** đặt lại câu hỏi:

> An còn nhiệm vụ nào cần xuất dữ liệu khách hàng hay không? Ai chịu trách nhiệm quyết định? Nếu không còn căn cứ, quyền này có bị thu hồi **trên CRM và trên các đường truy cập liên quan** hay chưa?

### 2.1. So sánh với những hoạt động gần kề

| Hoạt động | Câu hỏi chính | Sản phẩm |
|---|---|---|
| **Access request** | Có nên xin cấp quyền mới không? | Request với business justification và scope |
| **Access approval** | Có người đủ thẩm quyền đồng ý đề nghị không? | APPROVE/DENY với căn cứ |
| **Provisioning** | Account/grant đã được tạo hoặc cập nhật chưa? | Trạng thái thao tác đích |
| **Access review** | Những quyền **đang tồn tại** còn phù hợp không? | Giữ, sửa, thu hồi, xử lý ngoại lệ |
| **Access certification** | Quyền đã được người chịu trách nhiệm xác nhận theo yêu cầu kiểm soát chưa? | Decision và bằng chứng review |
| **Access monitoring** | Có hành vi hoặc quyền bất thường đang diễn ra không? | Cảnh báo/tín hiệu phân tích |
| **Access reconciliation** | Quyền thực tế có khớp quyền mong muốn không? | Chênh lệch và kết quả xử lý |
| **Security audit** | Kiểm soát và bằng chứng có đáp ứng tiêu chí không? | Kết luận đánh giá và phát hiện |

**Review không thay thế phê duyệt ban đầu.** Một grant sai từ lúc cấp vẫn cần sửa dù chưa đến lịch review. Ngược lại, phê duyệt ban đầu hợp lệ không chứng minh grant còn phù hợp sau Mover hoặc Leaver.

**Review không chỉ là thu thập chữ ký.** Một manager bấm “Approve all” trong khi không nhìn thấy resource, scope và thời hạn **không tạo ra bằng chứng có chất lượng rằng từng quyền thực sự cần thiết**.

## 3. Vì sao access review quan trọng trong IAM?

Truy cập không đứng yên theo thời gian. Account có thể bị thay đổi hoặc được cấp thêm quyền vì sự cố, chuyển đội, mở dự án hoặc nhu cầu tạm thời.

Những vấn đề điển hình:

- **Privilege creep:** Quyền mới được cộng thêm khi Mover, quyền cũ không bị gỡ.
- **Orphan accounts:** Account không còn người hoặc workload owner chịu trách nhiệm.
- **Stale grants:** Quyền dự án đã kết thúc hoặc contract đã hết hạn.
- **Overprivileged roles:** Vai trò đang chứa nhiều permission hơn nhu cầu.
- **Direct grants:** Quyền được cấp thẳng tại ứng dụng, nằm ngoài role chuẩn.
- **SoD conflicts:** Một subject vừa tạo vừa duyệt cùng giao dịch nếu chính sách cấm.
- **Hidden inheritance:** Nhóm lồng nhau hoặc role hierarchy làm một grant tạo ra nhiều quyền.
- **Local identities:** Ứng dụng có account/credential độc lập, không bị disable khi IdP thay đổi.
- **Service accounts:** Workload ngừng chạy nhưng credential/quyền vẫn tồn tại.
- **Session/token residue:** Grant bị thu hồi nhưng token hoặc phiên còn được chấp nhận.

Access review biến những rủi ro đó thành **quyết định có người chịu trách nhiệm**, gắn với bằng chứng và biện pháp xử lý.

### 3.1. Review không nhằm xóa càng nhiều quyền càng tốt

Một hệ thống an toàn phải vừa **ngăn quyền thừa**, vừa **không làm gián đoạn công việc hợp lệ**. Rà soát có thể xác nhận **KEEP** cho một role thực sự cần, với căn cứ rõ ràng. Nếu quyền cần nhưng scope quá rộng, kết quả phù hợp có thể là **MODIFY** thay vì giữ nguyên hoặc xóa toàn bộ.

**Chỉ số “đã thu hồi bao nhiêu quyền” không đủ đo chất lượng.** Quan trọng hơn là quyền đang tồn tại có căn cứ, phù hợp scope, không vi phạm chính sách và được thu hồi khi căn cứ kết thúc.

## 4. Đơn vị được review: chủ thể, account, role, entitlement hay quyền hiệu dụng?

Một người có thể có nhiều account; một role có thể cấp nhiều permission; một permission có thể đến từ nhiều nguồn.

~~~text
Canonical identity: P-2048
  ├─ IdP account: idp-P-2048
  │    ├─ group: finance-readers
  │    └─ group: project-A-users
  ├─ CRM account: crm-992
  │    └─ local direct grant: customer.export
  ├─ Database account: db-p2048
  │    └─ role: reporting_reader
  └─ Active session / token
       └─ scope/claim có thể còn quyền lịch sử
~~~

Nếu reviewer chỉ xem **group tại IdP**, quyền `customer.export` cấp trực tiếp trên CRM có thể bị bỏ sót. Nếu chỉ xem **account**, reviewer có thể không biết account đó liên kết với identity nào.

### 4.1. Những khái niệm cần rõ

| Đối tượng | Ví dụ | Câu hỏi review |
|---|---|---|
| **Identity/subject** | Nhân viên P-2048 | Còn engagement/điều kiện truy cập không? |
| **Application account** | `crm-992` | Account thuộc ai, còn cần không? |
| **Role** | `finance_reader` | Role có phù hợp nhiệm vụ hiện tại? |
| **Entitlement/grant** | `invoice.export@project-A` | Permission này còn căn cứ không? |
| **Group membership** | `project-A-analysts` | Nhóm có tạo quyền gián tiếp nào? |
| **Direct ACL/share** | Read/write trên thư mục/báo cáo | Quyền ngoài vai trò có owner không? |
| **Privileged eligibility** | Có thể kích hoạt cloud admin | Còn cần khả năng nâng quyền không? |
| **Active privileged grant** | Admin 30 phút | Có hết hạn/thu hồi đúng không? |
| **Credential/token/session** | API key, PAT, refresh token | Có đường truy cập tồn dư độc lập không? |
| **Resource** | Database/tenant/secret | Ai còn được phép với resource này? |

**Quyền được gán (assigned access)** khác **quyền hiệu dụng (effective access)**. Một API có thể từ chối theo ABAC dù user có role; ngược lại, một direct ACL hoặc token cũ có thể duy trì truy cập dù role mới đã bị gỡ.

## 5. Ai tham gia access review?

| Vai trò | Trách nhiệm thường gặp | Giới hạn cần biết |
|---|---|---|
| **Beneficiary/subject** | Người hoặc workload đang có quyền | Không nên tự chứng nhận quyền nhạy cảm của chính mình nếu policy cấm |
| **Manager** | Xác minh nhiệm vụ, bộ phận, thay đổi vai trò | Có thể không hiểu chi tiết permission ứng dụng |
| **Application owner** | Xác minh role/permission và cách cấp tại ứng dụng | Không nhất thiết biết mọi hợp đồng nhân sự |
| **Data/resource owner** | Quyết định ai được truy cập dữ liệu/tài nguyên do mình sở hữu | Cần đủ thông tin về request và subject |
| **IAM/IGA team** | Tổ chức campaign, dữ liệu, workflow, connector, theo dõi remediation | Không tự thay business owner chấp nhận quyền |
| **Security/PAM/SoD reviewer** | Đánh giá quyền đặc biệt, rủi ro và xung đột | Không thay manager xác minh mọi nhiệm vụ |
| **HR/VMS owner** | Xác nhận employment/engagement/status | Không trực tiếp quyết định mọi quyền nghiệp vụ |
| **Service owner** | Xác nhận workload còn chạy và quyền máy còn cần | Phải có người chịu trách nhiệm hiện hành |
| **Auditor/compliance** | Kiểm tra chất lượng, chứng cứ và ngoại lệ | Không mặc nhiên là người cấp/thu hồi quyền |

### 5.1. Người review phải thực sự hiểu quyền

Manager có thể biết An làm dự án nào, nhưng không rõ role `DB_OWNER` có thể xóa schema và thay policy. Data owner có thể hiểu độ nhạy dữ liệu nhưng không biết các nested group của AD.

Vì vậy có thể dùng **nhiều tầng review**:

- Manager xác nhận **người và nhiệm vụ**.
- Application/resource owner xác nhận **quyền và phạm vi**.
- Security/PAM xác nhận **đặc quyền, SoD và rủi ro**.

Không buộc một reviewer thiếu kiến thức phải đoán; hỗ trợ **ESCALATE/NEEDS_INFORMATION** và chuyển tới owner phù hợp.

## 6. Những câu hỏi cốt lõi của từng quyết định review

Một quyết định có chất lượng cần trả lời:

1. **Ai?** Canonical identity hay workload ID nào sở hữu quyền? Account mapping có đúng không?
2. **Đang làm gì?** Nhiệm vụ, role, dự án và engagement hiện hành?
3. **Quyền nào?** Action/role/group/direct grant cụ thể, không chỉ tên nhóm khó hiểu?
4. **Ở đâu?** Application, tenant, project, environment, resource và loại dữ liệu?
5. **Vì sao?** Căn cứ nghiệp vụ, request/approval, manager hoặc sponsor?
6. **Đến khi nào?** Thời hạn, điều kiện kết thúc hoặc nguồn sự kiện cần theo dõi?
7. **Rủi ro?** Admin/export/delete, data sensitivity, SoD, quyền mở rộng?
8. **Đang dùng được không?** Quyền cấp trực tiếp, kế thừa, token/session hoặc cache?
9. **Ai xác nhận?** Reviewer có thẩm quyền và không xung đột lợi ích?
10. **Kết quả?** Giữ, sửa, thu hồi hay yêu cầu điều tra; khi nào quyền thực sự đổi?

**“Account đang active” không đủ để giữ mọi quyền**, đặc biệt khi một người còn engagement B nhưng đã kết thúc engagement A.

## 7. Kiến trúc review trong Identity Lifecycle

~~~mermaid
flowchart TD
    H["HR / VMS<br/>JML + engagement status"] --> I["IAM / IGA<br/>Canonical identity + desired access"]
    D["IdP / Directory<br/>Groups + accounts"] --> INV["Access inventory / snapshot"]
    APP["App / API / DB<br/>Roles, ACL, local users"] --> INV
    PAM["PAM/PIM + cloud<br/>Privileged + machine access"] --> INV
    I --> INV
    INV --> C["Review campaign<br/>Population, scope, risk, owner"]
    C --> R["Reviewer: business + app owner<br/>KEEP / MODIFY / REVOKE / ESCALATE"]
    R --> G["IAM remediation workflow<br/>approval, expiry, change"]
    G --> P["SCIM / API / PAM / directory<br/>Provision / deprovision"]
    P --> V["Readback effective access<br/>role, ACL, token, session"]
    V --> A["Audit + exceptions<br/>evidence of decisions and result"]
    V --> I
    A --> C
~~~

Sơ đồ là mô hình logic. Một ứng dụng có thể không hỗ trợ SCIM hoặc quyền chỉ tồn tại dưới ACL cục bộ; một số quyết định được thực thi qua workflow thủ công có kiểm soát. **Không được kết luận review bao phủ tất cả chỉ vì một connector trả dữ liệu thành công.**

### 7.1. Access review là vòng phản hồi

IAM có một **desired access model**: chủ thể nên có những quyền nào. Đích thực tế có **effective access**. Access review giúp phát hiện sự lệch giữa hai tập này, đưa quyết định quản trị trở lại IAM, sau đó xác minh đích đã hội tụ.

~~~text
Authoritative sources + policy
          ↓
Desired access
          ↓ so sánh
Observed / effective access
          ↓
Reviewer xác định căn cứ
          ↓
KEEP / MODIFY / REVOKE / ESCALATE
          ↓
Target change + readback + audit
~~~

## 8. Review thường kỳ và review theo sự kiện

Access review có thể được khởi tạo theo **lịch**, **sự kiện** hoặc **mức rủi ro**.

| Loại review | Khi nào thực hiện | Ví dụ |
|---|---|---|
| **Periodic certification** | Theo chu kỳ do tổ chức đặt | Rà soát quyền Finance mỗi quý hoặc theo mức rủi ro |
| **Joiner readiness review** | Khi onboarding hoặc quyền ban đầu khác thường | Xác nhận role baseline và ngoại lệ |
| **Mover-triggered review** | Khi đổi nhóm, project, vị trí, site | Thu hồi vai trò/dữ liệu của nhiệm vụ cũ |
| **Leaver-triggered validation** | Khi kết thúc engagement | Chặn tất cả quyền không còn căn cứ |
| **Privileged access review** | Theo lịch chặt hơn hoặc biến cố rủi ro | PIM eligibility, cloud admin, vault |
| **Project/contract expiry review** | Khi dự án hoặc hợp đồng kết thúc | Quyền repo/tenant của contractor |
| **Resource ownership change** | Chủ dữ liệu/app đổi | Chuyển người có thẩm quyền review |
| **Risk/anomaly-triggered review** | Phát hiện grant ngoài chuẩn, role drift | Direct ACL hoặc key không có owner |
| **Access exception review** | Ngoại lệ sắp hết hạn hoặc kéo dài | Temporary export permission |

**Không có chu kỳ review tối ưu chung** cho mọi quyền. Rủi ro của account domain admin, quyền đọc một trang nội bộ và service principal production khác nhau; lịch review nên phù hợp **mức độ ảnh hưởng, khả năng giám sát, yêu cầu tổ chức và độ tin cậy nguồn dữ liệu**.

### 8.1. Review định kỳ không thay thế thu hồi kịp thời

Nếu nhân viên Leaver hôm nay, không thể đợi đến đợt review quý sau mới disable account. **JML deprovisioning là hành động theo sự kiện**, còn periodic review là lớp phát hiện bổ sung.

## 9. Chọn phạm vi campaign: review ai và những gì?

Một **review campaign** là tập hợp các đối tượng và quyền cần xem xét trong một khoảng thời gian, với reviewer, tiêu chí, deadline và workflow đã xác định.

Ví dụ campaign:

~~~text
Campaign: CR-FINANCE-2026-Q4
Population:
  - Tất cả human subject thuộc Finance
  - Contractor có grant vào Finance applications
  - Các service account sở hữu Finance data
Targets:
  - Invoice API, Finance Drive, Reporting DB
Review focus:
  - Role, direct ACL, export, privileged eligibility
  - Entitlement ngoài project/tenant được giao
As-of snapshot:
  2026-12-01T00:00:00Z
Review window:
  01/12 -> 15/12
Owner:
  Finance Data Owner + IAM Campaign Lead
Remediation:
  Bắt đầu theo chính sách khi có quyết định,
  không đợi campaign đóng nếu quyền nguy hiểm.
~~~

Đây là **ví dụ giả lập**, không phải quy trình mặc định. Một campaign cũng có thể theo **ứng dụng, resource, nhóm quyền đặc biệt hoặc người sở hữu**, không nhất thiết theo phòng ban.

### 9.1. Ranh giới phạm vi phải được công bố

Nếu chỉ thu thập nhóm IdP nhưng không có direct ACL trong ứng dụng, báo cáo phải nêu **direct ACL chưa bao phủ**, thay vì tính coverage 100% cho toàn ứng dụng.

### 9.2. Snapshot và biến động trong thời gian review

Campaign kéo dài hai tuần, trong khi người dùng có thể Mover hoặc Leaver ngay trong khoảng đó. Cần ghi:

- **snapshotAt/asOf**: Dữ liệu nào đã được reviewer nhìn thấy?
- **decisionAt**: Khi nào reviewer quyết định?
- **effectiveAt**: Quyền đáng lẽ thay đổi lúc nào?
- **targetAppliedAt**: Khi nào connector/ứng dụng áp?
- **accessVerifiedAt**: Khi nào quyền thực tế được xác minh?

**Review từ snapshot cũ không cho phép ghi đè trạng thái mới.** Nếu một Leaver đã bị disable sau snapshot, hệ thống không được hồi sinh quyền của họ chỉ vì reviewer chọn KEEP trên bản cũ.

## 10. Chất lượng dữ liệu quyết định chất lượng review

Một reviewer chỉ có thể quyết định tốt khi nhìn thấy **dữ liệu đúng, đủ và giải thích được**.

| Dữ liệu cần có | Nguồn phù hợp | Rủi ro nếu thiếu |
|---|---|---|
| Canonical identity ID | IAM/HR/VMS correlation | Nhầm account giữa hai người |
| Trạng thái employment/engagement | HR/VMS | Giữ quyền của Leaver/contractor hết hạn |
| Tên và ý nghĩa permission | App owner/entitlement catalog | Reviewer chấp nhận quyền không hiểu |
| Scope tài nguyên | API/app/DB/cloud metadata | Không thấy quyền xuyên tenant/project |
| Grant provenance | IGA request, role, direct grant, JIT | Không biết vì sao quyền được cấp |
| Đối tượng reviewer/owner | Role catalog, app/data catalog | Giao người không có thẩm quyền |
| Quyền kế thừa | Nested groups, role hierarchy | Đánh giá thiếu quyền hiệu dụng |
| Direct/local permissions | Target app/ACL/PAM | Bỏ sót quyền ngoài IAM |
| Last-used telemetry (nếu có) | Audit/usage logs | Có thể giúp phát hiện quyền dư |
| Chính sách và SoD | IAM governance/PDP | Không nhận biết xung đột |
| Trạng thái token/session | AS, IdP, app, PAM | Thu hồi role nhưng vẫn còn phiên |
| Data confidence | Connector health, sync lag | Dữ liệu trống bị hiểu nhầm là không có quyền |

### 10.1. Dữ liệu chưa biết không được hiểu là không có quyền

Nếu ứng dụng không trả về local ACL do connector lỗi, campaign cần trạng thái **UNKNOWN/INCOMPLETE_DATA**, không coi mọi quyền local là bằng 0.

### 10.2. Last login và last used không phải căn cứ duy nhất

Không dùng quyền trong 90 ngày **có thể là tín hiệu** để hỏi lại nhưng không tự chứng minh quyền không cần: một số nhiệm vụ là kiểm toán cuối năm, khắc phục sự cố hoặc break-glass. Ngược lại, quyền **được dùng thường xuyên** chưa chắc là hợp lệ; nó có thể đang bị lạm dụng hoặc thuộc role quá rộng.

**Review cần business necessity và policy**, không chỉ biểu đồ usage.

## 11. Các kiểu access review phổ biến

### 11.1. User-centric/manager review

Reviewer thấy toàn bộ quyền hoặc nhóm quyền của những người mình quản lý, xác minh chúng còn phù hợp nhiệm vụ không.

**Ưu điểm:** Manager hiểu biến động công việc, biết ai Mover/Leaver. **Giới hạn:** Có thể không hiểu quyền kỹ thuật hoặc resource-specific.

### 11.2. Application-centric review

Application owner xem người nào có account và entitlement trên hệ thống, kiểm quyền theo ý nghĩa của ứng dụng.

**Ưu điểm:** Hiểu role/ACL và rủi ro. **Giới hạn:** Có thể không biết trạng thái hợp đồng, nhiệm vụ từng người.

### 11.3. Resource-centric/data owner review

Resource owner xem tất cả subject được phép truy cập một kho dữ liệu, dự án, bucket, database hoặc API.

**Ưu điểm:** Dễ xác minh need-to-know theo tài nguyên. **Giới hạn:** Cần dữ liệu ánh xạ account–identity và owner đúng.

### 11.4. Role/group certification

Review định nghĩa role hoặc membership: ai đang có role, role chứa những permission gì và có còn phù hợp không.

**Cẩn trọng:** Giữ role không tự cho phép mọi resource nếu ABAC giới hạn project/tenant. Sửa định nghĩa role có thể ảnh hưởng **nhiều subject cùng lúc**, cần change review khác với quyết định giữ một assignment.

### 11.5. Privileged/SoD review

Tập trung quyền có tác động lớn như admin, secret access, production deploy, policy editor, SoD conflict và **PIM eligible roles**. Cần reviewer có thẩm quyền bảo mật và phương án thu hồi nhanh.

### 11.6. Non-human/service account review

Review workload identity, service principal, API key, owner, mục đích, resource, môi trường và credential lifetime. Không hỏi đơn giản “nhân viên nào đang sử dụng tài khoản này?” nếu subject là một service.

## 12. Các quyết định KEEP, REVOKE, MODIFY và ESCALATE

| Quyết định | Ý nghĩa | Bước tiếp theo |
|---|---|---|
| **KEEP / CERTIFY** | Quyền còn cần và phù hợp phạm vi/chính sách tại thời điểm đánh giá | Lưu căn cứ, owner, mốc review/expiry |
| **REVOKE** | Quyền không còn căn cứ hoặc vi phạm policy | Gửi lệnh gỡ, kiểm các nguồn grant và readback |
| **MODIFY / REDUCE** | Vẫn cần nhưng role/scope/time rộng hơn cần thiết | Cấp hoặc giữ phần hợp lệ, thu hồi phần dư |
| **ESCALATE** | Reviewer thiếu thẩm quyền hoặc phát hiện rủi ro | Chuyển owner/security/SoD |
| **NEEDS_INFORMATION** | Chưa đủ dữ liệu để quyết định | Bổ sung source/evidence theo deadline |
| **EXCEPTION_REVIEW** | Tạm giữ theo ngoại lệ được phê duyệt | Gắn risk owner, TTL, kiểm soát bù trừ |
| **REASSIGN_REVIEWER** | Reviewer sai hoặc vắng mặt | Đưa tới reviewer độc lập phù hợp |

**Không nên mặc định “không ai phản hồi = KEEP”** đối với quyền nhạy cảm. Cơ chế xử lý quá hạn phải được định nghĩa theo rủi ro, bao gồm escalation và cách bảo vệ dịch vụ hợp lệ; không được âm thầm chứng nhận thay người.

### 12.1. “MODIFY” khác “REVOKE rồi cấp bừa role khác”

Nếu người dùng đang có `report.admin@all-projects` nhưng chỉ cần `report.read@project-A`, cần điều chỉnh quyền đúng scope với approval và khả năng triển khai. Nếu ứng dụng không hỗ trợ scope hẹp, không tự giữ role admin rộng vì “không còn lựa chọn”.

### 12.2. Cần biết hiệu quả của REVOKE

Một entitlement có thể được cấp từ hai role. Gỡ một role **không chắc mất permission** nếu role khác vẫn cấp. Reviewer và remediation engine cần biết **grant provenance**, kiểm tra permission hiệu dụng và các đường truy cập song song.

## 13. Mô hình trạng thái của một review item

Một **review item** là đơn vị quyết định, ví dụ “Subject P-2048 có `invoice.export@project-A` qua role Finance Exporter”.

Một mô hình trạng thái:

~~~text
DISCOVERED
    ↓
ASSIGNED_TO_REVIEWER
    ↓
UNDER_REVIEW
    ├── NEEDS_INFORMATION ──> UNDER_REVIEW
    ├── ESCALATED ──────────> UNDER_REVIEW
    ├── KEEP_DECIDED ───────> CERTIFIED
    ├── MODIFY_DECIDED ────> REMEDIATION_PENDING
    └── REVOKE_DECIDED ────> REMEDIATION_PENDING
                                   ↓
                             TARGET_UPDATE
                                   ↓
                              READBACK
                            /          \
                        VERIFIED      FAILED/UNKNOWN
                           ↓             ↓
                       CLOSED       EXCEPTION_OPEN
                                          ↓
                                  REMEDIATE + RETRY
~~~

Tên state chỉ mang tính **minh họa**; các sản phẩm IGA có enum và workflow khác nhau.

**Điểm quan trọng:** `REVOKE_DECIDED`, `REMEDIATION_PENDING` và `CLOSED_VERIFIED` là ba trạng thái khác nhau. Nếu connector thất bại hoặc chỉ gỡ được một trong ba grant, review chưa hoàn tất về mặt quyền hiệu dụng.

## 14. Quy trình Access Review từ đầu đến cuối

~~~mermaid
sequenceDiagram
    autonumber
    participant H as HR/VMS + IAM
    participant T as Target app / IdP / PAM
    participant C as IGA Campaign
    participant R as Reviewer
    participant X as Remediation
    participant A as Audit / Verification

    H->>C: Canonical identity + trạng thái JML
    T->>C: Account, role, direct grant + scope
    C->>C: Chuẩn hóa + mapping + assign reviewer
    C->>R: Review item + business context + risk
    R->>C: KEEP / MODIFY / REVOKE / ESCALATE
    C->>C: Validate decision, authority, SoD
    C->>X: Action với phần phải sửa/thu hồi
    X->>T: Deprovision/modify grant qua connector
    T-->>X: Kết quả thao tác
    X->>A: Yêu cầu readback
    A->>T: Kiểm account, role, ACL, effective access
    T-->>A: Trạng thái thực tế
    A-->>C: VERIFIED hoặc exception
    C->>C: Đóng item có bằng chứng/owner
~~~

### 14.1. Chuẩn bị

1. Xác định mục tiêu, phạm vi, risk tier và lịch review.
2. Thu thập dữ liệu account/grant ở target.
3. Map account với đúng canonical identity/workload.
4. Phân biệt direct entitlement, inherited grant, policy exception.
5. Bổ sung HR/VMS engagement, project/tenant, owner và provenance.
6. Kiểm tra độ đầy đủ dữ liệu và chất lượng connector.
7. Chọn reviewer có quyền quyết định, chống self-certification trái policy.

### 14.2. Rà soát

1. Reviewer đọc **nghĩa của permission**, không chỉ group name.
2. Xác định nhu cầu, phạm vi, thời hạn và rủi ro.
3. Xem ticket/approval và trạng thái công việc hiện tại.
4. Kiểm SoD và những quyền hiện có khác.
5. Chọn KEEP, REVOKE, MODIFY hoặc ESCALATE.
6. Ghi lý do, evidence reference và thời điểm.

### 14.3. Remediation và closure

1. Tạo tác vụ thay đổi tại target.
2. Gỡ hoặc giảm scope, không tự động cấp nhiều quyền hơn.
3. Xử lý lỗi một phần, retry có kiểm soát và owner escalation.
4. Readback trạng thái và quyền hiệu dụng khi phù hợp.
5. Kiểm phiên/token/credential nếu đặc quyền hoặc chính sách yêu cầu.
6. Chỉ đóng item khi đạt tiêu chí; hạng mục chưa đạt phải có exception tracking.

## 15. Xem xét RBAC, ABAC và PBAC khi review

**RBAC** nhóm permission theo role; **ABAC** thêm điều kiện dựa trên thuộc tính; **PBAC** tổ chức policy theo các quy tắc được đánh giá tại PDP/PEP. Access review cần hiểu cả **role được cấp** lẫn **điều kiện quyền thực sự**.

Ví dụ:

~~~text
User: P-2048
Role được gán: finance_reader
Thuộc tính hiện tại:
  projectIds = [PRJ-17]
  tenant = tenant-vn
  engagement = ACTIVE

Resource:
  invoice INV-200
  projectId = PRJ-52
  tenant = tenant-vn

Quyết định API:
  DENY vì user không thuộc PRJ-52,
  dù có role finance_reader.
~~~

Nếu reviewer chỉ thấy role `finance_reader` và kết luận “người này đọc được mọi hóa đơn”, họ có thể đánh giá sai. Ngược lại, nếu quyền ABAC được tính từ thuộc tính đã lỗi thời sau Mover, API có thể cho phép dự án cũ.

### 15.1. Role mining không thay thế access review

**Role mining** tìm mẫu quyền để đề xuất role. Nếu quyền lịch sử đã thừa, thuật toán có thể đưa mẫu sai vào candidate. **Access review** xác minh tính hợp lệ của quyền và là nguồn đầu vào tốt để làm sạch dữ liệu role engineering.

### 15.2. Policy có thể từ chối dù role đang được gán

Một role còn trong directory nhưng PDP đã chặn vì account Leaver có thể làm **khả năng sử dụng** thấp hơn entitlement được gán. Vẫn cần xử lý **grant không còn căn cứ** để tránh được kích hoạt lại hoặc dùng qua đường API thiếu policy.

## 16. Separation of Duties (SoD) trong review

**SoD** ngăn một người giữ hoặc sử dụng tổ hợp quyền có thể gây gian lận, che giấu hoặc sai sót khi chính sách cấm.

| Quyền A | Quyền B | Điều cần review |
|---|---|---|
| `payment.create` | `payment.approve` | Có thể tự tạo và tự duyệt giao dịch không? |
| `user.provision` | `access.certify` | Người cấp quyền có tự xác nhận quyền do mình cấp không? |
| `vendor.create` | `payment.release` | Có đường tạo đối tác giả và thanh toán không? |
| `policy.modify` | `audit.log.delete` | Có thể thay policy và xóa dấu vết không? |
| `backup.delete` | `production.admin` | Rủi ro thao túng hệ thống và mất khả năng phục hồi |

### 16.1. Static và Dynamic SoD

- **Static SoD:** Không gán cùng subject hai role xung đột.
- **Dynamic SoD:** Có thể có role nhưng cấm kết hợp trong một phiên hoặc hành động cụ thể, ví dụ không duyệt hóa đơn do chính mình tạo.

**Review phải xét quyền hiệu dụng từ mọi nguồn**, không chỉ role trong một ứng dụng. Có thể có tổ hợp quyền rủi ro xuyên CRM, Payment và Cloud IAM.

### 16.2. Ngoại lệ SoD cần bằng chứng

Nếu công việc đặc biệt đòi một người tạm thực hiện hai vai trò thường tách biệt, ngoại lệ phải được **risk owner đủ thẩm quyền** chấp thuận, có thời hạn, kiểm soát bù trừ, giám sát và hậu kiểm. Reviewer không tự chuyển conflict sang KEEP vì “đội đang thiếu người”.

## 17. Privileged access review: một lớp cần nghiêm ngặt hơn

Quyền đặc quyền có khả năng tác động đến nhiều người hoặc hệ thống khác, nên review cần phân biệt:

- **Standing admin:** Quyền luôn tồn tại.
- **PIM eligible:** Chưa active nhưng có thể kích hoạt đặc quyền.
- **Active JIT grant:** Đặc quyền trong khoảng thời gian cụ thể.
- **PAM credential/session:** Secret hoặc phiên truy cập mục tiêu.
- **Direct cloud IAM role:** Quyền có thể nằm ngoài group IdP.
- **Break-glass:** Đường truy cập khẩn cấp riêng.

### 17.1. Đừng chỉ xem quyền đã kích hoạt

Một nhân viên Mover không còn vận hành production có thể **không có phiên admin đang mở**, nhưng vẫn **ELIGIBLE** để kích hoạt lại vai trò admin. Review phải xử lý **khả năng cấp lại quyền**, không chỉ các hành động gần đây.

### 17.2. Đặc quyền gián tiếp

Người có thể sửa CI/CD pipeline, secret manager, policy IAM hoặc nhóm quản trị có thể tạo ra tác động cấp admin, dù không mang role tên `admin`. Cần inventory và review **blast radius** của permission.

### 17.3. Quyền khẩn cấp ít dùng

Break-glass có thể không xuất hiện trong log suốt nhiều tháng nhưng vẫn cần cho khả năng phục hồi. Không xóa chỉ dựa trên last-used=never; review **mục đích, owner, khả dụng, bảo vệ credential, điều kiện kích hoạt và hậu kiểm** theo policy.

## 18. Review tài khoản dịch vụ và workload identity

**Non-human identities** như service principal, automation user, database bind account, CI/CD runner và OAuth client có thể có quyền rất lớn và sống lâu hơn người tạo.

| Tiêu chí | Human access review | Workload access review |
|---|---|---|
| Identity | Canonical person, HR/VMS | Workload/service ID, service catalog |
| Owner | Manager/sponsor | Technical/service owner |
| Eligibility | Engagement/nhiệm vụ công việc | Workload còn hoạt động và có mục đích |
| Credential | MFA, user session, token | Key, certificate, managed identity, secret |
| Permission | Role/project/tenant | API scope/audience, environment, resource |
| Evidence | Task/project/ticket | Deployment/service dependency, change ID |
| Trigger | Joiner/Mover/Leaver | Service deploy/change/decommission/owner change |
| Revocation | Role, account, session/token | Credential, role, service principal và dependency |

### 18.1. Các câu hỏi khi review workload

1. Service này còn chạy hoặc còn được triển khai không?
2. Ai chịu trách nhiệm kỹ thuật hiện tại?
3. Credential nào đã được cấp, có hết hạn/rotation không?
4. Scope/audience có vượt mục đích không?
5. Có quyền cloud admin, secret access hoặc khả năng thay chính sách không?
6. Workload có production/staging separation không?
7. Có cách thay bằng managed identity hoặc credential ngắn hạn khi phù hợp không?
8. Service đã ngừng nhưng tài khoản vẫn active vì lý do gì?
9. Owner cũ Leaver thì ai đã nhận bàn giao và đánh giá secret từng được biết?
10. Nếu revoke, có ảnh hưởng production không và cần rollout an toàn thế nào?

**Không xóa bừa service account production chỉ vì người tạo đã nghỉ.** Cần xác minh dependency, chuyển owner, giảm quyền và rotate/revoke credential theo rủi ro. Nhưng cũng **không giữ ownerless privileged workload vô thời hạn**.

## 19. Guest, contractor và federated identities

Trong môi trường có đối tác hoặc nhà thầu:

- **IdP đối tác** xác thực người dùng, nhưng tổ chức vẫn phải quyết định họ được vào tài nguyên nào.
- **Engagement/sponsor** có hạn và scope, không chỉ account đang active.
- Một subject có thể được **liên kết bằng `(issuer, sub)`** hoặc mapping federation có thẩm quyền.
- Account guest trong ứng dụng có thể tồn tại lâu hơn hợp đồng.
- Quyền được cấp qua **SCIM, group, app role hoặc direct share** cần được xét cùng nhau.

### 19.1. Một người, nhiều engagement

Nếu contractor kết thúc dự án A nhưng hợp đồng B vẫn có hiệu lực, reviewer nên **REVOKE** grant A không còn căn cứ, trong khi quyền B có thể **KEEP** nếu đã xác minh. Không tự coi account active phục vụ B là lý do giữ mọi quyền từ A.

### 19.2. Sponsor không phải chủ dữ liệu cho mọi quyền

Sponsor xác nhận nhà thầu còn làm dự án; data owner có thể phải xác nhận quyền export dữ liệu nhạy cảm. Một campaign chỉ giao sponsor review tất cả mà không cung cấp semantics của permission sẽ có nguy cơ certifying quá quyền.

## 20. Access review trong Joiner lifecycle

**Joiner** thường được provision theo role catalog/birthright policy khi một người bắt đầu làm việc. Access review hỗ trợ **kiểm tra độ chính xác của quyền ban đầu và phát hiện ngoại lệ**.

Ví dụ:

~~~text
Joiner: Lan, Finance Analyst tại PRJ-17
Authoritative event: HR-JOIN-2088
Role expected: finance_reader@PRJ-17

Observed at target:
  finance_reader@PRJ-17
  finance_exporter@ALL_PROJECTS

Review:
  KEEP finance_reader@PRJ-17 nếu đúng nhiệm vụ
  REVOKE finance_exporter@ALL_PROJECTS nếu không có căn cứ
  Kiểm tra vì sao connector/role mapping cấp quá rộng
~~~

### 20.1. Review không thay ngưỡng kiểm soát lúc cấp

Không nên để Joiner nhận global admin ngay rồi “review sau” nếu quyền chưa được phê duyệt. Ngay từ access request/provisioning phải có **least privilege và eligibility**.

### 20.2. Kiểm người và thời điểm

Account có thể được tạo trước ngày bắt đầu để chuẩn bị onboarding, nhưng quyền công việc cần phù hợp **effectiveAt**. Một reviewer nên thấy đúng person ID/account mapping, không chỉ email có thể bị tái sử dụng.

## 21. Access review trong Mover lifecycle

**Mover** là lý do điển hình để review theo sự kiện: một người vẫn là nhân viên hợp lệ nhưng **nhiệm vụ và quyền** thay đổi.

### 21.1. Ví dụ Mover

~~~text
Subject: P-2048
Trước Mover:
  Team: Sales
  Rights:
    CRM lead.read@A
    CRM lead.export@A
    quote.approve@A

Sau Mover:
  Team: Finance
  Task: invoice reconciliation@B
  Desired rights:
    invoice.read@B

Review results:
  REVOKE lead.export@A
  REVOKE quote.approve@A
  REVOKE lead.read@A nếu không còn engagement hợp lệ
  KEEP/GRANT invoice.read@B theo policy, với căn cứ mới
~~~

### 21.2. Vì sao review cần đi cùng provisioning?

Nếu IAM chỉ thêm Finance role mà không chạy review quyền cũ, người dùng có thể tích lũy quyền Sales. Nếu review phát hiện cần thu hồi nhưng SCIM target không gỡ được group, **MOVER chưa hoàn tất về hiệu quả quyền**.

### 21.3. Token và session cũ

JWT access token đã phát trước Mover có thể chứa scope/claim cũ đến hết hạn; ứng dụng có thể giữ local session. Review quyết định REVOKE cần nối với **cơ chế kiểm tra trạng thái hiện hành, token/session invalidation hoặc giới hạn TTL phù hợp**.

## 22. Access review trong Leaver lifecycle

**Leaver** là tình huống yêu cầu **thu hồi theo sự kiện**, không chờ chiến dịch định kỳ. Review có thể giúp phát hiện các đường truy cập còn sót mà quy trình deprovisioning tự động chưa bao phủ.

~~~mermaid
flowchart TD
    H["HR/VMS<br/>Leaver effectiveAt"] --> I["IAM: canonical subject<br/>all accounts + engagements"]
    I --> D["IdP/Directory<br/>disable/revoke group"]
    I --> P["PIM/PAM<br/>eligibility, grant, session"]
    I --> A["SCIM/App/DB<br/>role, ACL, local account"]
    I --> T["Tokens/credentials<br/>PAT, API key, SSH, OAuth"]
    D --> R["Target readback + negative tests"]
    P --> R
    A --> R
    T --> R
    R --> Q{"Còn quyền trái policy?"}
    Q -->|Không| C["Closed with evidence"]
    Q -->|Có / Unknown| E["Exception + owner<br/>compensating control"]
    E --> R
~~~

### 22.1. Những lỗi thường gặp sau Leaver

- IdP user đã disabled, nhưng CRM local account vẫn active.
- Quyền dự án được cấp direct share ngoài IAM.
- Token JWT tự chứa còn thời hạn tại Resource Server.
- PAM eligible role chưa bị xóa.
- Mật khẩu admin/shared credential từng được người nghỉ biết.
- Một service account vẫn dùng secret mà người đó từng quản trị.
- Hệ thống chưa đồng bộ trạng thái trên replica/cache.

**Review phục vụ phát hiện và xác minh**; nó không thay hành động revoke thực tế. Một quyết định “REVOKE” cần được theo dõi tới khi target chứng minh truy cập không còn hiệu lực.

### 22.2. Quyền lịch sử không được khôi phục cho Rejoiner

Người quay lại công ty có thể được liên kết với identity cũ sau xác minh, nhưng không nên tự phục hồi mọi role/grant đã được review và thu hồi trước Leaver. **Rejoiner cần eligibility/role theo nhiệm vụ mới** và căn cứ hiện hành.

## 23. Khi nào review một quyền là “KEEP” hợp lệ?

KEEP cần có lý do đáng tin, ví dụ:

- Subject còn engagement hợp lệ, đúng identity.
- Quyền thực sự cần cho nhiệm vụ hiện tại.
- Resource/tenant/project đúng phạm vi.
- Role hoặc entitlement không quá mức nhiệm vụ.
- Không xung đột SoD hoặc được xử lý theo ngoại lệ có thẩm quyền.
- Grant provenance và owner rõ ràng.
- Thời hạn/review schedule phù hợp.
- Không có tín hiệu tài khoản/credential đã bị compromise chưa giải quyết.

### 23.1. Mẫu lý do KEEP

~~~text
Subject: P-2048
Entitlement: invoice.read@PRJ-17
Reviewer: Finance Data Owner
Reason:
  Đang phụ trách đối soát hoá đơn PRJ-17,
  assignment FIN-218 còn hiệu lực.
  Chỉ read trong project; không có export/admin.
Decision: KEEP
Review as-of: 2026-12-01
Review again: khi project kết thúc hoặc Mover,
  và theo chu kỳ review được duyệt.
~~~

Người review không cần viết tiểu luận cho từng quyền nếu form đã có **mã nhiệm vụ, resource và evidence reference**. Nhưng một quyết định KEEP không có lý do hoặc gắn với owner không còn trách nhiệm sẽ khó kiểm toán.

## 24. Khi nào review một quyền phải dẫn tới REVOKE hoặc MODIFY?

Những tín hiệu:

- Engagement đã **ENDED** hoặc subject không còn owner.
- Không có nhiệm vụ cần permission.
- Role/tài nguyên vượt tenant/project hợp lệ.
- Quyền admin/export được cấp như ngoại lệ nhưng hết TTL.
- Direct ACL trùng hoặc bổ sung quyền ngoài role chuẩn không có approval.
- Role gây SoD conflict không có căn cứ ngoại lệ.
- App/workload bị decommission.
- Credential bị lộ hoặc có dấu hiệu sử dụng trái phép.
- Chưa biết ai sở hữu account/secret.
- Quyền được cấp dựa trên job/manager cũ trước Mover.

**“Không thấy dùng trong logs” là tín hiệu điều tra, không phải luôn là đủ lý do REVOKE**. Cũng không được tiếp tục giữ quyền cực kỳ nhạy cảm chỉ vì reviewer chưa có thời gian kiểm tra: cần escalation, kiểm soát tạm thời và deadline.

### 24.1. MODIFY phải đo bằng quyền hiệu dụng

Ví dụ `storage.admin@all-buckets` cần giảm còn `storage.read@bucket-A`. Sau khi sửa, phải kiểm:

- API cho phép đọc bucket A theo nhiệm vụ.
- API từ chối thao tác admin ở A.
- API từ chối đọc bucket B.
- Permission admin không tồn tại qua role kế thừa/token khác.

## 25. Một review record nên lưu những trường nào?

Ví dụ dữ liệu JSON giả lập:

~~~json
{
  "campaignId": "CR-FINANCE-2026-Q4",
  "reviewItemId": "RI-2048-INV-EXPORT",
  "snapshotAt": "2026-12-01T00:00:00Z",
  "beneficiary": {
    "kind": "HUMAN",
    "canonicalId": "P-2048",
    "engagementId": "ENG-713",
    "accountId": "invoice-user-2048"
  },
  "target": {
    "applicationId": "invoice-app",
    "entitlement": "invoice.export",
    "tenantId": "tenant-vn",
    "resourceScope": "project-A",
    "grantSource": "direct-grant"
  },
  "risk": {
    "classification": "SENSITIVE_EXPORT",
    "sodConflict": false
  },
  "review": {
    "reviewerRole": "finance-data-owner",
    "decision": "REVOKE",
    "reasonCode": "MOVER_SCOPE_ENDED",
    "evidenceRef": "HR-MOVER-991",
    "decidedAt": "2026-12-02T11:00:00Z"
  },
  "remediation": {
    "requestedAt": "2026-12-02T11:05:00Z",
    "targetState": "ACCESS_REMOVED",
    "verified": false,
    "status": "PENDING_TARGET_READBACK"
  }
}
~~~

**`verified=false` là điều quan trọng:** Người duyệt đã quyết định REVOKE nhưng target chưa xác nhận. Không chuyển item sang CLOSED chỉ để báo cáo campaign hoàn tất.

Đây là **schema minh họa**, không phải cấu trúc bắt buộc của sản phẩm IGA. Những trường như `engagementId`, `risk.classification` và `grantSource` phải được xây từ **nguồn có thẩm quyền** chứ không tin thông tin do requester nhập tùy ý.

### 25.1. Bảo vệ dữ liệu review

Review có thể phơi bày sơ đồ người–hệ thống–đặc quyền của tổ chức. Cần giới hạn reviewer theo scope, ẩn secret/token nguyên văn, kiểm soát retention, ghi audit người xem/sửa và tránh gửi toàn bộ entitlement list nhạy cảm qua email không được bảo vệ.

## 26. Mã giả cho kiểm tra chất lượng và đóng review item

Ví dụ Python minh họa **logic workflow** chứ không thực hiện gọi IAM/PAM thật:

~~~python
# Pseudocode giáo dục: không phải hệ thống thực thi authorization.
def evaluate_review_item(item, authoritative, target):
    issues = []

    subject_id = item["subjectId"]
    entitlement = item["entitlement"]
    resource = item["resourceId"]

    identity = authoritative.identity(subject_id)
    if identity is None:
        issues.append("UNKNOWN_IDENTITY")
    elif not identity.has_current_eligible_engagement(resource):
        issues.append("NO_CURRENT_BUSINESS_ELIGIBILITY")

    owner = authoritative.resource_owner(resource)
    if owner is None:
        issues.append("UNKNOWN_RESOURCE_OWNER")

    observed = target.read_effective_access(subject_id, resource, entitlement)
    if observed is None:
        issues.append("INCOMPLETE_TARGET_DATA")

    return {
        "readyForReview": len(issues) == 0,
        "issues": issues,
        "observedAccess": observed
    }


def can_close_revoke_item(decision, remediation, readback):
    if decision != "REVOKE":
        return False
    if remediation["status"] != "APPLIED":
        return False
    if readback is None or not readback["confidenceSufficient"]:
        return False

    # Kiểm quyền thực tế theo phạm vi quyết định.
    return readback["effectivePermission"] is False


# Không tự xóa entitlement khi reviewer chưa quyết định.
# Không mặc định KEEP khi thiếu dữ liệu hoặc task hết hạn.
# Ngoại lệ phải có owner, deadline và biện pháp an toàn.
~~~

**Giới hạn:** Ví dụ không xử lý account mapping giữa ứng dụng, nested groups, nhiều grant source, phiên/token, tenant, policy deny, lỗi đồng bộ hoặc retry. Hệ thống thật cần connector an toàn, idempotency, SoD, audit và **test end-to-end**.

## 27. Remediation: từ quyết định của reviewer đến thay đổi thực tế

**Remediation** là quá trình thực thi các quyết định REVOKE/MODIFY và giải quyết ngoại lệ đã phát hiện.

| Tình huống | Thao tác có thể cần | Cách xác minh |
|---|---|---|
| Role không còn cần | Remove role/assignment trong app | Đọc lại role + kiểm quyền API |
| Group IdP sai | Gỡ membership | Kiểm directory/IdP và target app |
| Direct ACL thừa | Xóa quyền trực tiếp | Readback ACL trên resource |
| PAM eligible quá hạn | Revoke eligibility | Không còn khả năng kích hoạt |
| JIT active grant | Chấm dứt grant, session nếu cần | Phiên/target không còn quyền |
| Contractor Leaver | Disable account, revoke role và token | Readback IdP/SCIM/app/RS |
| Service principal bỏ dùng | Deprovision workload/credential | Target từ chối credential cũ |
| Quyền export quá rộng | Chuyển sang read hẹp | Negative test export và ngoài scope |
| SoD conflict | Gỡ tổ hợp hoặc đặt ràng buộc | Test workflow/chính sách SoD |
| Account không xác định owner | Điều tra mapping; hạn chế theo risk | Đối chiếu identity và quyền |

### 27.1. SCIM chỉ là một đường chuyển thay đổi

**SCIM** có thể tạo, sửa hoặc deprovision user/group ở ứng dụng hỗ trợ. Nhưng không phải mọi ứng dụng đều triển khai SCIM, và **thành công ở SCIM không tự chứng minh local ACL/session/PAT đã bị thu hồi**.

### 27.2. IdP logout không bằng revoke mọi token

SSO logout hoặc disable account có thể chặn **đăng nhập mới**, nhưng access token đã phát hoặc local session có thể tiếp tục được Resource Server chấp nhận đến khi có cơ chế thu hồi/kiểm trạng thái. Quyền nhạy cảm cần phương án xác minh theo rủi ro.

### 27.3. Một số quyền có nhiều nguồn

Nếu permission vẫn tồn tại sau khi gỡ role A do role B cũng cấp, cần xác định **grant B có căn cứ còn hiệu lực không**. Không tự xóa B nếu nó phục vụ engagement khác; nhưng cũng không đánh dấu “revoke effective access” thành công khi hành động trái policy vẫn được phép.

## 28. Xử lý review quá hạn, ngoại lệ và thiếu thông tin

Một campaign sẽ có item chưa được phản hồi, lỗi connector và quyền khó giải thích.

### 28.1. Reviewer không trả lời

- Nhắc và escalation theo chính sách.
- Chuyển reviewer nếu manager/owner đã Mover hoặc Leaver.
- Với đặc quyền rủi ro cao, có thể cần **tạm hạn chế** khi không có căn cứ được xác nhận.
- Không tạo chứng nhận giả bằng thao tác “auto KEEP” không có nguồn quyền rõ.
- Nếu tự động hóa quyết định theo policy, lưu rule/version và nguồn dữ liệu làm căn cứ.

### 28.2. Target không nhận lệnh thu hồi

- Giữ item **REMEDIATION_PENDING / EXCEPTION_OPEN**.
- Thử lại có kiểm soát, tránh lệnh trùng ảnh hưởng sai subject.
- Xác định biện pháp bù trừ: chặn ở IdP, PEP, VPN/ZTNA hoặc target khác nếu phù hợp.
- Có owner, deadline, severity và thông báo cho security khi quá hạn.
- Readback sau phục hồi và cập nhật audit.

### 28.3. Reviewer thấy entitlement không hiểu

Không yêu cầu reviewer “đánh dấu giữ cho an toàn”. Cần **data dictionary, app owner explanation, grant provenance và risk label**; nếu vẫn không rõ, escalation.

## 29. Tại sao một campaign đạt 100% review chưa chắc hiệu quả?

Hãy so sánh:

~~~text
Campaign A:
  1000 / 1000 items được click KEEP
  0 revoke, 0 exception
  Reviewer không thấy scope/permission meaning
  Không có target readback
  => Completion = 100%, effectiveness chưa được chứng minh.

Campaign B:
  960 / 1000 items đã quyết định
  70 REVOKE, 30 MODIFY
  20 quyết định thu hồi chưa verified
  40 items chờ owner giải thích
  => Completion < 100%, nhưng minh bạch các rủi ro còn mở.
~~~

Một báo cáo chất lượng cần tách **decision completion**, **remediation completion** và **verified access correction**. Nếu chỉ đo số nút đã được bấm, hệ thống có thể khuyến khích reviewer xác nhận hàng loạt mà không hiểu.

### 29.1. Quyền nào chưa bao phủ?

Nếu 100% item trong danh sách được review nhưng danh sách **không chứa direct ACL, workload và local accounts**, coverage tổng thể không thể được công bố là 100% cho toàn bộ ứng dụng.

## 30. Các chỉ số và bằng chứng kiểm toán

| Chỉ số | Điều cần đo | Bẫy cần tránh |
|---|---|---|
| **Inventory coverage** | Tỷ lệ ứng dụng/loại quyền được thu thập | Trống dữ liệu ≠ không có quyền |
| **Identity mapping coverage** | Account map đúng người/workload | Map bằng email/tên dễ nhầm |
| **Reviewer assignment quality** | Item có owner đủ thẩm quyền | Người chỉ quản lý HR không hiểu DB admin |
| **Decision completion** | Tỷ lệ item có quyết định hợp lệ | Không phản ánh target đã sửa |
| **Remediation completion** | Tỷ lệ REVOKE/MODIFY đã triển khai | API 200 chưa chứng minh effect |
| **Verified closure** | Tỷ lệ item có readback phù hợp | Cần scope test đầy đủ |
| **Stale access findings** | Grant hết nhiệm vụ, quá hạn hoặc không có owner | Phải xét nguồn grant khác hợp lệ |
| **Privileged exposure** | Standing/eligible high-risk roles còn tồn tại | Không chỉ đếm role name “admin” |
| **SoD findings** | Xung đột quyền hiệu dụng | Có thể phát sinh xuyên ứng dụng |
| **Unowned workload accounts** | Service principal không còn owner | Xóa bừa có thể gây outage |
| **JML convergence** | Từ Mover/Leaver tới quyền thực tế hợp lệ | Không tính thời điểm gửi command làm kết quả |
| **Exception aging** | Item chưa xác minh tồn tại bao lâu | Không để ngoại lệ vô thời hạn |
| **Review decision reversals** | Trường hợp reviewer KEEP sai phải sửa | Không tối ưu bằng che giấu sai sót |
| **Certification evidence quality** | Có căn cứ, approver, resource và policy | Chữ ký hàng loạt không đủ |
| **Access drift recurrence** | Quyền đã gỡ nhưng xuất hiện lại | Kiểm nguồn cấp và sync lại role cũ |

### 30.1. Bằng chứng nên giữ

- Campaign ID/scope, snapshot time và độ phủ dữ liệu.
- Review item ID, identity/account mapping và permission semantics.
- Reviewer, quyền hạn của reviewer và thời điểm quyết định.
- Reason code, task/approval hoặc căn cứ KEEP/REVOKE/MODIFY.
- SoD/risk flags, exception/approval riêng khi cần.
- Lệnh remediation, hệ thống đích, kết quả và timestamp.
- Readback/negative test liên quan tới quyền thực tế.
- Policy/version, các sự kiện JML và correlation ID.
- Kết quả unresolved items, owner, deadline và biện pháp bù trừ.

Không lưu **mật khẩu, private key, access token nguyên văn, OTP** hoặc hồ sơ nhân sự không cần thiết trong tập evidence. Quyền truy cập vào báo cáo review phải bị hạn chế, vì nó tiết lộ cấu trúc đặc quyền của tổ chức.

## 31. Tình huống A: manager xác nhận mọi quyền của nhân viên

**Bối cảnh:** Manager mới nhận 30 người và được giao 1.500 access review items. Giao diện chỉ hiển thị chuỗi `APP_GRP_0172`, không mô tả mục đích. Manager bấm KEEP ALL để hoàn thành đúng hạn.

**Sai sót:** Quyết định không dựa trên thông tin có thể đánh giá. Một group có thể cấp export toàn tenant hoặc admin production.

**Cách cải thiện:**

1. Thêm tên nghiệp vụ, app, scope, risk và permission semantics.
2. Giảm số item lặp bằng cách nhóm role hợp lý nhưng giữ khả năng xem chi tiết.
3. Chuyển entitlement kỹ thuật phức tạp tới application/data owner.
4. Nêu Mover/Leaver flag và grant provenance.
5. Cho phép ESCALATE hoặc NEEDS_INFORMATION.
6. Đo decision quality, không chỉ tỷ lệ bấm hoàn tất.

**Bài học:** Reviewer được giao trách nhiệm phải có **khả năng hiểu và bằng chứng đủ để quyết định**.

## 32. Tình huống B: Mover tích lũy quyền từ hai phòng ban

**Bối cảnh:** Phương chuyển Sales → Finance. IAM đã cấp Finance role nhưng không gỡ CRM export. Reviewer Finance chỉ thấy role Finance nên chọn KEEP toàn bộ.

**Vấn đề:** Campaign theo bộ phận hiện tại đã **bỏ quyền ở ứng dụng cũ**. Chỉ xem một hệ thống hoặc một scope làm mất đường quyền tồn dư.

**Cách xử lý:**

1. Review theo **canonical identity across applications**.
2. So sánh role/project hiện tại với entitlement từ Sales.
3. Kiểm direct grant, nested group và token/session.
4. REVOKE quyền Sales không còn căn cứ; giữ quyền phục vụ engagement khác nếu có.
5. Xác minh CRM không còn cho export trái policy.
6. Cập nhật rule Mover để tự khởi tạo access review khi đổi nhiệm vụ.

**Bài học:** **Mover phải tính cả quyền cần thêm và quyền phải gỡ**.

## 33. Tình huống C: Leaver nhưng token cũ vẫn dùng được

**Bối cảnh:** HR/VMS phát Leaver cho contractor lúc 18:00. IdP disable account và IGA đánh dấu REVOKE các role. Tuy nhiên API vẫn chấp nhận một JWT access token đã phát lúc 17:50 cho tới 18:50.

**Vấn đề:** Role removal và IdP disable chưa đồng nghĩa Resource Server không còn chấp nhận token. Nếu policy yêu cầu thu hồi ngay tại mốc Leaver, cần cơ chế bổ sung.

**Cách xử lý:**

- Kiểm đường token validation, introspection hoặc account-state check của API.
- Thu hồi refresh token/grant/session theo khả năng.
- Xem xét token lifetime và biện pháp chặn quyền cấp bách tại PEP.
- Readback bằng phép thử được phép và an toàn.
- Không đóng Leaver khi quyền ngoài policy vẫn còn.
- Ghi rõ độ trễ thực tế và trách nhiệm từng hệ thống.

**Bài học:** **Certified REVOKE không đồng nghĩa verified deprovisioning**.

## 34. Tình huống D: service principal không có owner

**Bối cảnh:** `svc-payment-reconcile` có `db.read` và `vault.secret.read` trên production. Người tạo service principal nghỉ việc từ sáu tháng trước. Team hiện tại không chắc workflow nào dùng credential.

**Rủi ro:** Có thể có quyền quá rộng, secret chưa rotate và workload mồ côi; nhưng xóa tức thời có thể làm hỏng quy trình thanh toán.

**Cách xử lý:**

1. Tìm workload/deployment/calling logs và service catalog.
2. Xác định owner mới có thẩm quyền.
3. Đánh giá quyền và data classification.
4. Ưu tiên giảm quyền `vault.secret.read` nếu không phục vụ nhiệm vụ, theo phương án an toàn.
5. Rotate/revoke credential từng bị người cũ biết khi rủi ro yêu cầu.
6. Kiểm thử job sau thay đổi và readback quyền ngoài scope bị từ chối.
7. Nếu không còn workload hợp lệ, deprovision có kiểm soát.

**Bài học:** **Review non-human identities** cần hiểu dependency sản xuất và quản trị credential.

## 35. Tình huống E: role đã gỡ nhưng permission vẫn tồn tại

**Bối cảnh:** User bị REVOKE `storage_admin`. Connector đã remove role và trả success. Một quyền `storage.delete@bucket-A` vẫn hoạt động do direct ACL được cấp nhiều tháng trước.

**Bản chất:** Có **nhiều nguồn grant**. Review mới gỡ một đường cấp quyền, chưa đạt mục tiêu thu hồi permission.

**Cách xử lý:**

- Liệt kê **role, direct ACL, resource policy và nested membership**.
- Xác định grant nào còn căn cứ.
- Thu hồi quyền không hợp lệ ở từng nguồn.
- Kiểm API negative test hoặc cách xác minh phù hợp.
- Lưu kết quả sau khi effective access đúng, không đóng sớm.

## 36. Tình huống F: quyền hiếm dùng nhưng là break-glass

**Bối cảnh:** Công cụ phát hiện account khẩn cấp không được sử dụng hơn một năm và đề nghị xóa vì “unused”.

**Bản chất:** Quyền ít dùng có thể **được thiết kế để chỉ sử dụng khi khủng hoảng**. Quyết định phù hợp không thể chỉ dựa usage.

**Cách review:**

- Kiểm mục đích, bảo vệ authenticator/credential, người quản lý và đường sử dụng.
- Xác minh giới hạn quyền và điều kiện khẩn cấp.
- Diễn tập trong môi trường hoặc quy trình được phép.
- Xác nhận alert, logging, hậu kiểm và rotation.
- Cân nhắc KEEP dưới policy đặc biệt hoặc MODIFY để hạn rủi ro.

**Bài học:** **Tần suất sử dụng không tự chứng minh tính cần thiết hoặc tính không cần thiết**.

## 37. Câu hỏi tự kiểm tra

**Câu 1.** Access review khác access request như thế nào?

**Gợi ý:** Request đề nghị quyền mới; review đánh giá lại **quyền đã tồn tại** dựa trên nhu cầu và trạng thái hiện tại.

**Câu 2.** Manager chọn REVOKE, connector gửi lệnh thành công. Đã được coi là thu hồi thực tế chưa?

**Gợi ý:** Chưa đủ. Cần readback tại target và xét quyền qua nguồn grant/phiên/token khác theo phạm vi.

**Câu 3.** Quyền không được dùng sáu tháng có bắt buộc phải xóa?

**Gợi ý:** Không. Cần kiểm mục đích, rủi ro, nhiệm vụ hiếm, break-glass và evidence.

**Câu 4.** Người dùng vẫn active nhưng chuyển bộ phận. Có thể KEEP quyền bộ phận cũ vì account đang hoạt động không?

**Gợi ý:** Không tự động. Review theo engagement/nhiệm vụ và grant provenance.

**Câu 5.** Reviewer không hiểu ý nghĩa group `APP_GRP_0172` thì nên làm gì?

**Gợi ý:** Yêu cầu app owner diễn giải, bổ sung permission catalog hoặc ESCALATE, không chứng nhận bừa.

**Câu 6.** Leaver đã disable IdP; ứng dụng local account vẫn active. Review có cần xử lý không?

**Gợi ý:** Có. Đường quyền ngoài IdP cần được deprovision và kiểm chứng.

**Câu 7.** Workload `svc-report` không có manager. Vậy bỏ qua access review?

**Gợi ý:** Không. Dùng technical/service owner và service catalog; review quyền/credential lifecycle.

**Câu 8.** Người có role Finance Reader truy cập hóa đơn thuộc tenant khác. Review chỉ nên nhìn role name hay cần xem resource scope?

**Gợi ý:** Cần tenant/resource context và RBAC/ABAC effective authorization.

**Câu 9.** Một role PIM đang ELIGIBLE nhưng chưa ACTIVE. Có cần review?

**Gợi ý:** Có, vì subject vẫn có khả năng kích hoạt đặc quyền.

**Câu 10.** Campaign hoàn thành 100% nhưng chưa có bằng chứng remediation. Có thể kết luận quyền đều đúng không?

**Gợi ý:** Không. Tách decision completion, remediation completion và verified closure.

**Câu 11.** Một contractor hết A nhưng còn B. Review nên xử lý thế nào?

**Gợi ý:** Gỡ grants A, kiểm B còn căn cứ, tránh thu hồi quá rộng hoặc giữ quyền A do account vẫn active.

**Câu 12.** Reviewer KEEP quyền vì người dùng thường xuyên sử dụng. Điều đó đủ không?

**Gợi ý:** Không. Tần suất sử dụng không thay business necessity, policy và risk/SoD review.

## 38. Checklist triển khai Access Review

- [ ] **Mục đích:** Đã định nghĩa rõ phạm vi, risk tier và kết quả mong muốn của campaign?
- [ ] **Định danh:** Account map được đúng canonical identity hoặc workload ID?
- [ ] **JML:** HR/VMS engagement, job/department, project và mốc hiệu lực được đối chiếu?
- [ ] **Inventory:** Đã bao phủ IdP/directory, app local roles, direct ACL, nested groups, cloud/PAM và các đích bắt buộc?
- [ ] **Data quality:** Phân biệt missing/unknown với không có quyền; kiểm connector health và snapshot?
- [ ] **Permission semantics:** Reviewer hiểu role/group cấp những action/resource nào?
- [ ] **Scope:** Tenant, project, environment và data classification được hiển thị đủ?
- [ ] **Reviewer:** Đúng owner, độc lập khi policy đòi SoD, có phương án thay người vắng mặt?
- [ ] **Business evidence:** Có nhiệm vụ, ticket, engagement hoặc owner xác minh căn cứ KEEP?
- [ ] **Decision:** KEEP, MODIFY, REVOKE và ESCALATE được ghi rõ, có reason/decision time?
- [ ] **Least privilege:** Có phát hiện role quá rộng, quyền export/admin và permission không cần?
- [ ] **SoD:** Đã xét xung đột quyền trong/cross-app và các ngoại lệ có hạn?
- [ ] **Privileged:** Standing/eligible/JIT roles, PAM session và secret access được review theo rủi ro?
- [ ] **Non-human:** Service account/workload có owner, mục đích, credential và expiry?
- [ ] **External:** Contractor/guest/federated subject được rà soát theo sponsor/engagement?
- [ ] **Joiner:** Quyền baseline đúng nhiệm vụ, không clone ngoại lệ người tiền nhiệm?
- [ ] **Mover:** Có review quyền cũ và quyền mới, nhiều engagement và token/session tồn dư?
- [ ] **Leaver:** Không chờ periodic campaign; tất cả quyền bắt buộc phải deprovision theo event?
- [ ] **Provisioning:** SCIM/API/direct target change có owner và retry có kiểm soát?
- [ ] **Readback:** Đã xác minh role, ACL, resource permission, session/token theo chính sách?
- [ ] **No silent keep:** Không coi reviewer không phản hồi là chứng nhận hợp lệ mà thiếu policy?
- [ ] **Exceptions:** Những item chưa xác minh có owner, risk, deadline và kiểm soát bù trừ?
- [ ] **Version:** Snapshot, decision, remediation, policy và review evidence có mốc thời gian?
- [ ] **Metrics:** Tách inventory coverage, decision completion, remediation và verified closure?
- [ ] **Privacy:** Không log password/secret/token hoặc chia sẻ entitlement list vượt thẩm quyền?
- [ ] **Reconciliation:** Có phát hiện quyền cũ tái xuất hiện sau khi đã thu hồi?
- [ ] **Governance:** Đã đưa những vấn đề lặp lại vào cải tiến role catalog/JML workflow?
- [ ] **Kết luận:** Có bằng chứng **quyền đang được thực thi đúng** thay vì chỉ hoàn tất giao diện?

## 39. Tổng kết

**Access review là hoạt động rà soát lại những quyền đã được cấp để xác định chủ thể còn thực sự cần, được phép và có căn cứ sử dụng từng quyền hay không.** Nó khác **access request** (xin quyền mới), **approval** (quyết định đề nghị) và **provisioning** (thực hiện thay đổi). Review có chất lượng phải có **dữ liệu đúng, người review đủ thẩm quyền, thông tin scope/rủi ro rõ ràng, quyết định có căn cứ và hành động khắc phục được kiểm chứng**.

Trong IAM, review kết nối **Joiner** (quyền ban đầu phải phù hợp nhiệm vụ), **Mover** (quyền cũ không được tích lũy), **Leaver** (không giữ quyền khi engagement kết thúc) với **IdP/SSO, SCIM, RBAC/ABAC, PAM/PIM, quản lý service account và kiểm toán**. Không chỉ hỏi “nên giữ hay gỡ?” mà còn phải hỏi “**đã giữ đúng phạm vi hay gỡ thực sự ở mọi đường truy cập bắt buộc chưa?**”.

**Một chiến dịch review hoàn chỉnh không được đánh giá chỉ bằng số nút KEEP/REVOKE đã bấm.** Chất lượng nằm ở **business necessity, least privilege, xử lý SoD, khắc phục quyền sai, readback quyền hiệu dụng và khả năng giảm quyền truy cập tồn dư** trong suốt vòng đời danh tính.
