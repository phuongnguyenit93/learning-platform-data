# Xác định owner trong thiết kế chương trình Security Assurance

**Xác định owner** là bước chỉ định rõ **ai có quyền quyết định, ai chịu trách nhiệm cuối cùng, ai thực hiện, ai giữ bằng chứng và ai xác minh** đối với từng mục tiêu, security control, hệ thống, rủi ro và phát hiện trong chương trình assurance. Nếu trách nhiệm không rõ, chương trình có thể có chính sách, kiểm thử và dashboard nhưng vẫn không ai xử lý khi evidence thiếu, control bị sai lệch, ngoại lệ hết hạn hoặc phát hiện audit bị tái diễn.

Trong chương **Thiết kế chương trình assurance** thuộc module **SECURITY_SECURITY_ASSURANCE**, ownership là cơ chế quản trị để biến mục tiêu “đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật” thành việc làm được tổ chức và duy trì. Chương trình cần nối **risk → security requirement → control → implementation → test/evidence → assessment → finding → remediation → verification** với những người hoặc chức danh có quyền và nghĩa vụ cụ thể ở từng mắt xích.

> **Câu hỏi cốt lõi:** Khi một claim bảo mật không còn đủ bằng chứng, một control thất bại hoặc một finding quá hạn, **ai phải nhận tín hiệu, ai có quyền ưu tiên nguồn lực, ai thực hiện sửa, ai được chấp nhận rủi ro và ai có đủ độc lập để xác minh kết luận?**

Ví dụ, một ứng dụng SaaS dùng chung dịch vụ Identity Provider (IdP). Nhóm Identity vận hành MFA; nhóm ứng dụng quản lý các service accounts và quyền; Security Assurance đánh giá evidence; chủ sản phẩm chịu tác động nghiệp vụ. Nếu file quản lý chỉ ghi **“owner = Security”**, khi xuất hiện một tài khoản production có quyền cao không được cưỡng chế xác thực phù hợp, không ai biết ai phải sửa policy, ai phải đánh giá ảnh hưởng, ai cung cấp log và ai phê duyệt ngoại lệ. Một owner được xác định tốt phải phản ánh **phạm vi của quyết định**, không chỉ là tên một phòng ban.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của ownership và accountability trong chương trình security assurance liên tục.
2. Phân biệt **program owner**, **business/service owner**, **system/asset owner**, **control owner**, **risk owner**, **evidence owner/custodian**, **finding/remediation owner**, **exception approver**, **assurance reviewer** và **decision authority**.
3. Xây dựng ánh xạ owner theo tài sản, yêu cầu, control, evidence, đánh giá và rủi ro; không nhầm người vận hành công cụ với người chịu trách nhiệm kết luận.
4. Thiết kế **RACI** và quy tắc phân tách nhiệm vụ (segregation of duties) tương xứng mức rủi ro.
5. Lập một **ownership register** có phạm vi, quyền hạn, người thay thế, tuyến escalation, thời điểm hiệu lực và evidence liên quan.
6. Xử lý hệ thống dùng chung, multi-tenant, dịch vụ cloud, công việc thuê ngoài, thay đổi tổ chức và các đối tượng **orphaned** chưa có owner hợp lệ.
7. Thiết kế luồng xử lý finding, evidence gap, ngoại lệ, retest và closure rõ trách nhiệm.
8. Đánh giá hiệu quả ownership bằng chỉ số đo được, tình huống thực hành và kiểm toán mẫu.

---

## 2. Vì sao chương trình assurance phải có owner?

Security assurance không kết thúc ở việc có một control được thiết kế. Để tuyên bố “control thực thi hiệu quả”, cần người chịu trách nhiệm cho nhiều công đoạn:

| Công đoạn | Câu hỏi cần một owner trả lời |
|---|---|
| **Risk assessment** | Ai quyết định rủi ro nào quan trọng và chấp nhận ở mức nào? |
| **Requirements** | Ai xác nhận security requirement áp dụng cho dịch vụ và dữ liệu nào? |
| **Control design** | Ai định nghĩa biện pháp, tiêu chí PASS/FAIL và phạm vi kiểm tra? |
| **Implementation** | Ai bảo đảm policy/code/config được triển khai đúng tài sản? |
| **Operation** | Ai duy trì control trong production, xử lý drift hoặc lỗi dịch vụ? |
| **Evidence collection** | Ai bảo đảm dữ liệu được thu đúng nguồn, thời kỳ, đối tượng và còn hiệu lực? |
| **Assurance assessment** | Ai xem claim–argument–evidence và chỉ rõ giới hạn của kết luận? |
| **Finding/remediation** | Ai thực hiện corrective action và chịu trách nhiệm hoàn thành đúng hạn? |
| **Independent verification** | Ai được kiểm tra lại và xác nhận đủ điều kiện đóng finding? |
| **Risk acceptance** | Ai có thẩm quyền chịu trách nhiệm rủi ro còn lại và đặt điều kiện? |
| **Change/release review** | Ai làm mới đánh giá khi hệ thống, threat hoặc yêu cầu thay đổi? |

Nếu tất cả được ghi là “team bảo mật” mà không làm rõ **quyền ra quyết định**, có thể xảy ra các lỗi:

- Đội bảo mật phát hiện lỗ hổng nhưng không có quyền thay đổi production.
- Đội vận hành có quyền sửa nhưng không sở hữu risk acceptance.
- Data owner không biết dữ liệu đã được chuyển sang dịch vụ mới.
- Evidence collector chạy thành công nhưng không biết thiếu một cloud account.
- Audit finding đã có ticket nhưng không ai chịu trách nhiệm kiểm chứng closure.
- Người ký ngoại lệ không có quyền chấp nhận tác động lên khách hàng hoặc hợp đồng.

**Ownership là một thuộc tính của hệ thống quản trị, không phải một ô bắt buộc điền cho đủ hồ sơ.**

## 3. Phân biệt owner, responsible, accountable và approver

Những thuật ngữ này thường bị dùng lẫn nhau.

- **Owner**: một cá nhân hoặc vai trò được giao trách nhiệm duy trì một đối tượng/hoạt động theo phạm vi đã xác định. Trong thực tế, phải kiểm tra owner có **quyền hành, năng lực, nguồn lực và đường escalation** tương ứng hay không.
- **Responsible (R)**: người/nhóm trực tiếp thực hiện công việc và sản xuất deliverable; một việc có thể có nhiều R.
- **Accountable (A)**: người giữ trách nhiệm cuối cùng đối với kết quả và quyền phê duyệt/điều phối. Theo cách dùng RACI phổ biến, nên xác định **một A rõ ràng cho một quyết định hoặc hoạt động cụ thể**.
- **Consulted (C)**: bên cung cấp chuyên môn/đầu vào, trao đổi hai chiều.
- **Informed (I)**: bên cần được cập nhật kết quả hoặc thay đổi, nhưng không mặc nhiên có quyền chặn.
- **Approver/authority**: người có quyền đưa ra **một loại quyết định** theo delegation of authority, ví dụ chấp nhận rủi ro cao, duyệt production release hoặc đóng audit finding.

**A của control operation không nhất thiết là A của risk acceptance.** Một kỹ sư IAM có thể được giao thực thi MFA policy; business risk authority mới có quyền chấp nhận rủi ro kinh doanh khi còn ngoại lệ. Một reviewer có thể xác minh rằng evidence thiếu mà không có quyền chấp nhận rủi ro thiếu đó.

### 3.1. Vì sao “mỗi thứ có một owner” vẫn chưa đủ?

Một bản ghi chỉ chứa \`owner: platform-team\` có thể thiếu:

1. **Owner của vấn đề gì?** Quyền vận hành service, định nghĩa security control, quản lý evidence hay chấp nhận rủi ro?
2. **Phạm vi nào?** Production hay staging, region nào, tenant nào, đường API nào?
3. **Thời điểm nào?** Owner có còn làm ở đơn vị đó không, có người kế nhiệm?
4. **Quyền nào?** Có được duyệt ngoại lệ, rollback hay chuyển risk state không?
5. **Ai được hỗ trợ và ai xác minh độc lập?** Không để người tự triển khai rồi tự xác nhận mọi kết luận rủi ro cao.
6. **Khi vắng mặt xử lý ra sao?** Có backup, escalation chain và tiêu chí chuyển giao?
7. **Bằng chứng trách nhiệm?** Có acknowledgement, quyết định được lưu và hành động thực tế?

Bởi vậy, chương trình nên quản lý ownership theo **đối tượng, vai trò, quyền và thời hạn**, không chỉ một chuỗi tên.

## 4. Các loại owner cần phân biệt trong Security Assurance

Một mô hình phân vai hữu ích:

| Loại | Chịu trách nhiệm chính | Không nên hiểu sai |
|---|---|---|
| **Executive sponsor** | Bảo trợ ngân sách, định hướng rủi ro, giải quyết bế tắc liên đơn vị | Không nhất thiết vận hành từng control |
| **Assurance program owner** | Thiết kế/chạy chương trình, control inventory, cadence, evidence quality và báo cáo | Không tự động là risk owner của mọi hệ thống |
| **Business/process owner** | Mục tiêu nghiệp vụ, quy trình, mức ảnh hưởng và yêu cầu vận hành | Không nhất thiết có quyền sửa IAM/KMS |
| **Service/system owner** | Vòng đời dịch vụ, tài sản, change/release, dependency và vận hành | Không đồng nghĩa sở hữu mọi control dùng chung |
| **Data owner** | Phân loại, mục đích sử dụng, quyền truy cập và các nghĩa vụ dữ liệu | Không tự động là người quản trị hệ thống lưu dữ liệu |
| **Security control owner** | Định nghĩa và duy trì tiêu chí, phạm vi, thiết kế và hiệu lực của một control | Không được suy rằng đã ký policy thì control đang hoạt động |
| **Control operator** | Thực thi hoặc vận hành công cụ/quy trình kiểm soát | Không nhất thiết có quyền chấp nhận rủi ro còn lại |
| **Evidence owner/custodian** | Nguồn, quality, freshness, collection, integrity, retention và khả năng truy xuất evidence | Không tự động được kết luận control PASS |
| **Assurance assessor/reviewer** | Đánh giá claim, argument, evidence, phản chứng và giới hạn | Không nên duyệt rủi ro thay business owner khi không có thẩm quyền |
| **Risk owner** | Chịu trách nhiệm quyết định và theo dõi rủi ro cụ thể trong thẩm quyền | Không biến risk accepted thành technical compliance |
| **Finding/remediation owner** | Phân tích, CAP, triển khai và chứng minh hành động khắc phục | Ticket Done chưa có nghĩa verified fixed |
| **Exception approver** | Phê duyệt sai khác cụ thể đúng mức rủi ro, phạm vi và thời hạn | Không thể miễn nghĩa vụ bên ngoài ngoài thẩm quyền |
| **Independent verifier/auditor** | Xác minh retest/closure hoặc đưa kết luận audit theo mandate | Không nên tự chứng nhận tất cả công việc do chính mình tạo |

**Một người có thể giữ nhiều vai trò** trong tổ chức nhỏ, nhưng cần ghi rõ khi nào họ đang hành động trong vai trò nào và có những quyết định nào cần review độc lập hoặc được ủy quyền riêng. Đừng tạo bộ máy cồng kềnh chỉ để có nhiều chữ ký; yêu cầu phân vai phải tương xứng rủi ro và tính độc lập cần thiết.

## 5. Thiết kế ownership theo đối tượng, không theo sơ đồ tổ chức chung chung

Security assurance làm việc với nhiều **đối tượng cần quản trị**. Hãy tạo một mô hình truy vết:

~~~mermaid
flowchart TD
    A["Business/security objective"] --> B["Risk + asset/service"]
    B --> C["Requirement + control"]
    C --> D["Implementation/operation"]
    D --> E["Test + evidence source"]
    E --> F["Assurance claim + assessment"]
    F --> G{"PASS / FAIL / UNKNOWN?"}
    G -- "FAIL" --> H["Finding + CAP + retest"]
    G -- "UNKNOWN" --> I["Evidence gap + collection fix"]
    G -- "PASS" --> J["Review + periodic reassessment"]
    H --> K["Remediation owner + independent verifier"]
    I --> L["Evidence owner + control owner"]
    J --> M["Assurance program owner"]
    B --> N["Business risk owner"]
    N --> O["Risk/exception decision"]
~~~

Với mỗi đối tượng, chọn **owner có đủ thẩm quyền trên đối tượng đó**:

- Một **asset** cần service/system owner và nguồn inventory.
- Một **security requirement/control** cần control owner chốt tiêu chí.
- Một **evidence source** cần evidence custodian bảo đảm khả năng thu thập và chất lượng.
- Một **assurance assessment** cần assessor/approver theo quy định.
- Một **finding** cần remediation owner chịu trách nhiệm hành động.
- Một **residual risk/exception** cần người có quyền quyết định, không chỉ người tạo ticket.

### 5.1. Ví dụ về granularity

Nếu công ty có policy “mọi dịch vụ production phải ghi sự kiện quản trị”, một owner cấp tổ chức có thể quản lý **tiêu chuẩn logging**, trong khi mỗi service owner chịu trách nhiệm **phát sự kiện đúng schema**, platform owner chịu trách nhiệm **ingestion**, SOC chịu trách nhiệm **rule và giám sát**, assurance owner chịu trách nhiệm **đánh giá bằng chứng**.

Gán duy nhất “SOC là logging owner” có thể che việc thiếu log bắt nguồn từ backend không phát event. Phải phân rã theo **control objective và chặng của data flow**.

## 6. Phương pháp xác định owner từ đầu

Có thể dùng quy trình bảy bước thay vì chỉ hỏi người quản lý “ai nhận ticket này?”.

**Bước 1 — Xác định đối tượng:** đang tìm owner cho service, control, risk, data set, evidence source hay một finding cụ thể? Nếu chưa rõ thì không nên gán tên.

**Bước 2 — Chốt phạm vi:** environment, region/account, tenant, dữ liệu, time window, dependency và security requirement nào được bao gồm?

**Bước 3 — Xác định quyết định bắt buộc:** ai phải điều chỉnh policy, triển khai sửa, chi ngân sách, phê duyệt release, chấp nhận rủi ro hoặc xác minh closure?

**Bước 4 — Kiểm tra năng lực và quyền:** người/role được gán có đủ quyền hệ thống, thông tin, nguồn lực, mandate và khả năng điều phối không?

**Bước 5 — Gắn trách nhiệm thực hiện:** ai viết code, vận hành control, thu evidence, kiểm thử và trả lời finding?

**Bước 6 — Phân tách nhiệm vụ:** ai review, ai xác nhận kết quả, ai phê duyệt rủi ro? Có xung đột lợi ích đáng kể không?

**Bước 7 — Ghi vào ownership register:** có owner chính, delegate/backup, tuyến escalation, ngày hiệu lực, acceptance và review trigger.

### 6.1. Tiêu chí chọn owner

Một owner phù hợp thường đáp ứng:

| Tiêu chí | Câu hỏi xác minh |
|---|---|
| **Decision authority** | Có thể đưa ra hoặc xin cấp quyết định đúng loại? |
| **Operational control** | Có quyền điều phối người vận hành và nguồn lực thực hiện? |
| **Domain knowledge** | Hiểu hệ thống, data flow, threat/control và tác động? |
| **Accountability** | Sẵn sàng nhận kết quả kể cả khi không đạt? |
| **Evidence access** | Có thể yêu cầu và kiểm tra nguồn evidence cần thiết? |
| **Capacity** | Có đủ thời gian và ngân sách, không chỉ “được chỉ tên”? |
| **Coverage** | Có thật sự bao phủ asset/region/tenant/control đã giao? |
| **Continuity** | Có backup, kế nhiệm và lịch rà soát owner khi đổi tổ chức? |
| **Conflict of interest** | Có cần một reviewer khác để bảo đảm độc lập? |

Nếu không ai đáp ứng đầy đủ, đây là **governance gap** phải được escalated, không nên điền đại một tên để hoàn tất biểu mẫu.

## 7. RACI: phân quyền hành động cụ thể

RACI là công cụ để **không bỏ quên trách nhiệm và quyền quyết định**. Nó không thay văn bản ủy quyền, quy trình change hay vai trò pháp lý.

Ví dụ ma trận RACI cho một chương trình security assurance (chỉ minh họa, cần điều chỉnh theo tổ chức):

**Ký hiệu:** **A** – accountable; **R** – thực hiện; **C** – tham vấn; **I** – được thông báo; **—** – không tham gia trực tiếp.

| Hoạt động | Program lead | Service owner | Control owner | Evidence custodian | Security assurance | Risk authority | Independent verifier |
|---|---|---|---|---|---|---|---|
| Định nghĩa phạm vi chương trình | **A** | C | C | I | R | C | I |
| Xác minh inventory dịch vụ/asset | I | **A** | C | R | C | I | I |
| Chốt criteria và control scope | C | C | **A** | C | R | C | I |
| Triển khai control production | I | **A** | R | C | C | I | I |
| Thu và bảo quản evidence | I | C | **A** | R | C | I | I |
| Đánh giá claim, evidence gap | C | C | C | R | **A** | I | R |
| Đề xuất CAP cho finding | I | **A** | R | C | C | I | I |
| Xác minh retest và closure | I | C | C | R | **A** | I | R |
| Phê duyệt residual risk/exception | I | C | C | I | C | **A** | I |
| Tổng hợp báo cáo chương trình | **A** | I | C | C | R | C | I |

**Giải thích quan trọng:**

- Trong ví dụ này, mỗi **hoạt động** có một A rõ. Không suy ra chỉ một A cho toàn chương trình.
- “Independent verifier” giữ **R** khi trực tiếp thử lại; Security Assurance có thể là A của quy trình đánh giá nếu mô hình governance quy định vậy.
- “Service owner” có thể ủy quyền cho engineering lead thực hiện CAP, nhưng vẫn chịu trách nhiệm cuối cùng trong phạm vi dịch vụ.
- Risk authority phê duyệt **quyết định rủi ro**; không có quyền ép reviewer đổi kết quả kỹ thuật FAIL thành PASS.
- Nếu audit bên ngoài có quyền kết luận riêng, vai trò auditor và thẩm quyền audit phải được thiết kế theo mandate cụ thể, không bị thay bởi ma trận nội bộ.
- Với chương trình nhỏ, một người có thể mang hai vai; cần ghi cơ chế review bổ sung khi phân tách thực tế không thể đạt.

### 7.1. RACI không đủ nếu không có “bằng chứng quyền hạn”

Một bảng A/R có thể được duyệt nhưng không có ai nhận việc thật. Nên có:
- Quyết định phân công hoặc role assignment được ghi nhận.
- Acknowledgement của người nhận và supervisor/manager khi cần.
- Nơi liên hệ, on-call/escalation và người dự phòng.
- Đường tới tài liệu thẩm quyền phê duyệt (delegation matrix).
- Cơ chế kiểm tra owner vẫn còn hoạt động khi thay đổi team.

## 8. Phân tách trách nhiệm: bảo đảm tính độc lập phù hợp

Một trong các rủi ro lớn nhất là **người tạo bằng chứng tự quyết định bằng chứng đủ và tự phê duyệt mọi sai lệch**.

### 8.1. Những cặp vai cần cân nhắc tách

| Công việc 1 | Công việc 2 | Rủi ro nếu cùng người không kiểm soát |
|---|---|---|
| Thiết kế/triển khai control | Độc lập xác minh hiệu quả | Có thể bỏ qua lỗi do chính thiết kế tạo ra |
| Thu và lọc evidence | Phê duyệt kết luận assurance | Có thể chọn dữ liệu thuận lợi, bỏ FAIL |
| Đề xuất ngoại lệ | Phê duyệt ngoại lệ | Có thể hạ chuẩn để tránh CAP |
| Tự sửa vulnerability | Đánh dấu VERIFIED CLOSED | Ticket Done thay cho retest |
| Quản lý inventory | Xác nhận tính đầy đủ không có đối chiếu | Tài sản bị bỏ sót không được phát hiện |
| Quyết định release | Chấp nhận rủi ro vượt quyền | Có thể ưu tiên deadline hơn an toàn/tuân thủ |

Không nhất thiết tách mỗi thao tác sang một bộ phận. Có thể dùng **peer review, dual approval, sampling độc lập, đối chiếu nguồn và audit trail**, tùy mức rủi ro và quy mô đội. Cần tránh tạo “độc lập hình thức” khi hai reviewer chỉ ký tên trên cùng một dashboard lỗi.

### 8.2. Owner vẫn chịu trách nhiệm dù ủy quyền thực hiện

Một control owner có thể giao vận hành cho platform team, thuê ngoài cho vendor hoặc dùng công cụ tự động. Nhưng **trách nhiệm quản trị và xử lý rủi ro theo thẩm quyền nội bộ không tự biến mất**.

Ví dụ, nhà cung cấp vận hành hệ thống lưu trữ; tổ chức vẫn cần một service/data owner nội bộ xác định phân loại dữ liệu, requirement, bằng chứng từ vendor và phương án xử lý khi evidence thiếu.

## 9. Gắn owner với Control Catalog và Asset Inventory

Một thiết kế chương trình tốt không duy trì ownership trong bảng tách rời mà không thể tra cứu. Hãy nối:

**Asset / Service / Data → Risk → Requirement → Control → Implementation → Evidence → Assurance assessment → Finding / Exception.**

### 9.1. Control register tối thiểu

| Trường | Ý nghĩa |
|---|---|
| Control ID/version | Nhận diện control và thay đổi tiêu chí |
| Objective/requirement | Security property và nguồn áp dụng |
| Scope/population | Tài sản/identity/data/luồng nào chịu kiểm soát |
| Accountable control owner | Người chịu trách nhiệm định nghĩa và hiệu lực control |
| Operators | Đội triển khai/vận hành |
| Evidence owner | Ai đảm bảo dữ liệu/test và khả năng truy xuất |
| Assessor/reviewer | Ai đánh giá claim và retest |
| Risk owner | Người có quyền quyết định residual risk khi control chưa đạt |
| Cadence/triggers | Nhịp test, nguồn dữ liệu và sự kiện review |
| Fallback/escalation | Xử lý khi owner vắng mặt hoặc mất quyền |
| Effective period | Thời kỳ gán trách nhiệm và các lần chuyển giao |

### 9.2. Vì sao nguồn inventory quan trọng?

Nếu thiếu một cloud account trong asset inventory, owner mapping từ inventory cũng có thể **bỏ sót cả tài sản lẫn trách nhiệm**. Do đó nên đối chiếu nhiều nguồn được phép:

- Service catalog và CI/CD deployment inventory.
- Cloud account/project/subscription registry.
- IAM identities và privileged roles.
- Data catalog và luồng nhạy cảm.
- Runtime discovery, networking, API gateway routes.
- Vendor register và hệ thống tích hợp.
- Change/release records.

Không phải công ty nào cũng cần một công cụ GRC phức tạp; nhưng phải có **source of truth, lịch đối soát và quy tắc xử lý xung đột**.

## 10. Quy tắc gán owner trong môi trường nhiều đội

Một control thường băng qua nhiều hệ thống. Cần chọn **điểm chịu trách nhiệm cuối** theo quyết định và chia phần vận hành cụ thể.

### 10.1. Kiểm soát truy cập

Mục tiêu: người dùng chỉ truy cập dữ liệu đã được cấp quyền.

- **Identity platform owner:** vận hành đăng nhập, MFA, token issuance và IdP policy.
- **Application/service owner:** bảo đảm backend thực thi object-/tenant-level authorization.
- **Data owner:** xác định quyền đối với dữ liệu và phạm vi sử dụng.
- **Control owner:** đặt criteria và kiểm tra liên kết giữa các lớp.
- **Evidence owner:** cung cấp token test, policy export, endpoint inventory và log.
- **Assurance reviewer:** kiểm tra test, coverage, phản chứng và kết luận.
- **Risk authority:** quyết định residual risk/exception trong thẩm quyền.

Nếu có cross-tenant exposure, không nên đẩy hết sang IdP khi nguyên nhân là API tin tenant ID từ client. Ownership phải dựa trên **điểm control bị sai**, không chỉ biểu tượng của dịch vụ nằm trong diagram.

### 10.2. Security logging end-to-end

Mục tiêu: sự kiện quản trị ở production được ghi và có thể truy vết.

| Đoạn luồng | Owner phù hợp | Ví dụ evidence |
|---|---|---|
| Ứng dụng tạo sự kiện | Application owner | Event taxonomy, test event tại source |
| Agent/forwarder | Platform/SRE owner | Agent config, queue metrics |
| Kho ingestion/SIEM | Logging platform/SOC | Source inventory, event counts, retention |
| Detection rule | Detection engineering/SOC | Rule version, synthetic alert test |
| Control objective và kết luận | Security control/assurance owner | Coverage mapping, evidence quality review |
| Rủi ro khi thiếu log | Service/business risk authority | Impact assessment, exception/CAP |

Nếu hai trong tám ứng dụng ngừng gửi log, owner của ứng dụng cần sửa phần phát event nếu lỗi ở ứng dụng; platform xử lý forwarder nếu lỗi pipeline; SOC sửa detection nếu parser sai. Program owner bảo đảm **đúng owner nhận action**, không cần tự thao tác mọi component.

### 10.3. Backup và Disaster Recovery

Một backup job có thể thuộc vận hành hạ tầng, nhưng **khôi phục nghiệp vụ** cần phối hợp service owner, data owner, KMS/IAM owner và DR coordinator. Ai có quyền kết luận đạt RTO/RPO phải dựa trên tiêu chí nghiệp vụ đã duyệt và evidence kiểm thử, không chỉ dashboard backup thành công.

## 11. Mô hình shared responsibility với cloud và nhà cung cấp

Việc sử dụng cloud managed service hoặc thuê ngoài không được để control “vô chủ”.

### 11.1. Ma trận trách nhiệm song phương

| Công việc | Provider thường làm | Tổ chức khách hàng cần làm |
|---|---|---|
| Bảo mật hạ tầng nền tảng | Theo mô hình dịch vụ/hợp đồng | Kiểm tra giới hạn trách nhiệm và bằng chứng liên quan |
| Cấu hình IAM trong tenant/account | Có thể cung cấp chức năng nền | Chịu trách nhiệm quyền thực tế và phê duyệt |
| Mã hóa dữ liệu | Có thể cung cấp encryption service | Chọn cấu hình, quản lý quyền/khóa theo thỏa thuận |
| Logging | Có thể phát logs hoặc cung cấp API | Bật nguồn, ingest/retention, kiểm tra coverage |
| Vulnerability remediation | Vá phần thuộc provider theo trách nhiệm | Vá code/config/dependency thuộc khách hàng |
| Audit evidence | Cung cấp báo cáo/certification theo scope | Đối chiếu report, kỳ, ngoại lệ và control khách hàng |
| Incident | Xử lý phần dịch vụ mình quản lý | Điều phối đánh giá tác động dữ liệu, thông báo, phục hồi |

**Không có mô hình phân chia trách nhiệm chung áp dụng cho mọi nhà cung cấp và mọi hợp đồng.** Cần đọc nghĩa vụ và dịch vụ đã ký theo quy trình tổ chức. Một báo cáo kiểm toán của vendor không tự chứng minh security control ở phần cấu hình khách hàng đã đạt.

### 11.2. Cần một owner nội bộ có quyền yêu cầu evidence

Kể cả khi vendor vận hành control, tổ chức cần một **internal accountable owner** cho phạm vi sử dụng, rủi ro, dữ liệu và việc đánh giá evidence. Vendor contact có thể là responsible party, nhưng không nên là người duy nhất giữ quyết định risk acceptance của doanh nghiệp nếu hợp đồng không trao quyền đó.

Nếu vendor không cung cấp evidence theo yêu cầu, trạng thái phù hợp có thể là **NOT DEMONSTRATED** cho claim, kèm đánh giá rủi ro và đường escalation. Không tự gán PASS vì “nhà cung cấp uy tín”.

## 12. Ownership register: dữ liệu cần quản lý

Ownership register là nơi lưu **quan hệ giữa đối tượng và chủ thể được giao**. Nó nên có phiên bản, kiểm soát truy cập và liên kết tới bằng chứng phân công.

### 12.1. Các trường quan trọng

| Trường | Mục đích |
|---|---|
| Object ID/type | Service, control, evidence source, risk, finding, exception |
| Scope | Account, region, environment, data, role hoặc đường truy cập |
| Accountable owner | ID/role có người nhận trách nhiệm cuối |
| Responsible teams | Đội thi hành và các delegate |
| Decision authority | Loại quyết định owner được phép đưa ra |
| Evidence source/access | Nơi lấy thông tin để đánh giá và hành động |
| Backup/delegate | Người dự phòng khi owner vắng mặt |
| Escalation path | Cấp xử lý khi blocked, quá hạn, xung đột |
| Effective from/to | Thời kỳ gán trách nhiệm, trạng thái hiệu lực |
| Acceptance/last reviewed | Owner đã nhận trách nhiệm, review gần nhất |
| Dependency links | Các control, asset, risk, change liên quan |
| SLA/cadence | Nhịp phản hồi, kỳ kiểm tra và mốc cần làm |
| Ownership-change trigger | Team transfer, incident, account mới, change/release |

Một **team alias** giúp quản lý thay đổi nhân sự nhưng **không đủ** nếu không có người chịu trách nhiệm hiện tại và đầu mối escalation. Định danh cá nhân nên được quản lý theo IAM/HR directory và phân quyền dữ liệu phù hợp; tránh nhúng thông tin riêng tư không cần thiết vào tài liệu phổ biến.

### 12.2. Mẫu YAML minh họa

Đây là **schema ví dụ cho học tập**, không phải tiêu chuẩn bắt buộc hoặc một quyết định phân công thật:

~~~yaml
ownership_record:
  id: OWN-EXAMPLE-006
  object:
    type: security_control
    id: IAM-PRIV-ACCESS-01
    version: "1.2"
    objective: "Privileged human access requires approved strong authentication"
  scope:
    environments: [production]
    cloud_accounts_ref: "restricted/inventory/production-accounts"
    identity_types: [human-interactive, emergency-break-glass]
    exclusions:
      - "machine identities governed by separate workload-identity control"
  accountable:
    owner_role: IAM_CONTROL_OWNER
    owner_directory_ref: "restricted/directory/iam-control-owner"
    accepted_at_utc: "2026-11-24T09:00:00Z"
    authority: [define_control_criteria, initiate_remediation, request_review]
  responsible:
    implementation_team: IDENTITY_PLATFORM
    operations_team: IAM_OPERATIONS
    evidence_team: SECURITY_TELEMETRY
  supporting_roles:
    business_risk_owner: AUTHORIZED_SERVICE_RISK_OWNER
    assurance_reviewer: SECURITY_ASSURANCE_REVIEWER
    independent_verifier: INDEPENDENT_CONTROL_VALIDATOR
  delegation:
    backup_owner_role: IAM_CONTROL_DEPUTY
    escalation_role: SECURITY_GOVERNANCE_LEAD
    delegation_record_ref: "restricted/governance/delegations/OWN-006"
  evidence:
    control_spec_ref: "restricted/controls/IAM-PRIV-ACCESS-01"
    population_ref: "restricted/inventory/privileged-identities"
    checks_ref: "restricted/tests/privileged-authentication"
    source_owner_role: SECURITY_TELEMETRY
  governance:
    effective_from_utc: "2026-11-24T00:00:00Z"
    review_frequency: quarterly
    owner_last_verified_utc: "2026-11-24T09:00:00Z"
    review_triggers:
      - cloud-account-added
      - identity-provider-changed
      - material-iam-security-finding
      - control-owner-team-changed
    status: ACTIVE
~~~

Các mã, đường dẫn và ngày chỉ là **placeholder**. Ghi \`status: ACTIVE\` chưa chứng minh owner thực sự có quyền, đã chấp thuận và đang làm việc; người kiểm tra phải xác nhận bằng phân công, role directory và evidence hoạt động.

Một bản ghi ownership **không nên chứa secret/token hay dữ liệu nhạy cảm**. Nên dùng reference tới nguồn quản lý có kiểm soát.

## 13. Xác định owner cho finding, CAP và retest

Khi một control không đạt, cần một luồng trách nhiệm thống nhất.

~~~mermaid
flowchart TD
    A["Control test / audit finding"] --> B["Triage theo asset, control và risk"]
    B --> C["Gán remediation owner có quyền xử lý"]
    C --> D["Định nghĩa CAP + closure criteria"]
    D --> E["Sửa code/config/process"]
    E --> F["Thu evidence deployment và regression"]
    F --> G["Independent retest theo criteria"]
    G --> H{"Đã đủ bằng chứng và đạt chưa?"}
    H -- "Chưa" --> I["RETEST FAILED / PARTIAL / UNKNOWN"]
    I --> J["Sửa tiếp, xử lý gap hoặc risk decision"]
    J --> E
    H -- "Đạt" --> K["Authorized closure + update assurance case"]
    K --> L["Theo dõi tái diễn và owner review"]
~~~

### 13.1. Trách nhiệm tách theo trạng thái

| Trạng thái | Người chịu trách nhiệm | Điều kiện chuyển tiếp |
|---|---|---|
| Finding mới | Triage owner / control owner | Xác nhận ảnh hưởng, severity, root-cause hypothesis |
| Action plan | Remediation owner và service owner | CAP có hành động, deadline, acceptance và nguồn lực |
| Implemented | Engineering/SRE operator | Code/config đã thay và deployment evidence |
| Pending retest | Assurance verification coordinator | Test plan đúng phạm vi, artifact và thời điểm |
| Retest failed | Remediation owner | Sửa tiếp, không đóng finding |
| Evidence gap | Evidence owner / control owner | Thu nguồn đúng, chứng minh scope/quality |
| Verified fixed | Independent verifier | Điều kiện đóng được kiểm chứng theo scope |
| Verified closed | Authorized closure authority | Hồ sơ quyết định và residual risk đã cập nhật |
| Risk accepted | Authorized risk owner | Phạm vi, thời hạn, điều kiện theo dõi và nghĩa vụ |

**Owner của remediation không mặc nhiên là owner của closure.** Một pull request merged hoặc ticket Done chỉ chứng minh một hành động kỹ thuật đã xảy ra. Cần người có mandate xác minh lại rằng issue không còn tái hiện trong phạm vi và rằng bằng chứng đủ.

### 13.2. Không đẩy “unknown” vào vùng vô chủ

Khi test trả **UNKNOWN** vì scanner mất quyền hoặc account inventory thiếu, cần một owner xử lý **evidence gap**; không thể kết luận control PASS hay tự gán lỗi cho service owner nếu nguồn thất bại nằm ở collector. Tuy vậy, business/service risk owner vẫn cần được thông báo khi thiếu bằng chứng ảnh hưởng tới quyết định sản xuất.

## 14. Risk owner và exception approver: không được gán nhầm

Một risk owner phải có **thẩm quyền và trách nhiệm đối với hậu quả của rủi ro**, không chỉ quyền tạo bản ghi trong hệ thống GRC.

### 14.1. Risk ownership

Một hồ sơ rủi ro có thể cần:
- Kịch bản threat/failure, tài sản và tác động.
- Inherent và residual risk theo phương pháp được duyệt.
- Owner có quyền quyết định trong giới hạn thẩm quyền.
- Action/mitigation và người thực hiện riêng.
- Evidence về hiệu lực của compensating control.
- Điều kiện đánh giá lại khi có thay đổi hoặc incident.
- Lịch báo cáo/escalation nếu rủi ro vượt ngưỡng.

**Owner không thể chấp nhận rủi ro vượt delegation.** Ví dụ trưởng nhóm ứng dụng có thể đề xuất trì hoãn một bản vá, nhưng rủi ro về dữ liệu khách hàng production có thể đòi business risk authority và các bên phụ trách nghĩa vụ hợp đồng, quyền riêng tư hoặc tuân thủ.

### 14.2. Exception ownership

Một ngoại lệ nên có:
- **Requester:** đề nghị sai khác, cung cấp lý do.
- **Control owner:** kiểm tra requirement và mức sai khác.
- **System/service owner:** giữ tài sản và điều kiện vận hành.
- **Compensating-control owner:** thực thi và xác minh biện pháp tạm.
- **Risk owner / authorized approver:** chấp thuận hoặc từ chối trong thẩm quyền.
- **Exception custodian:** theo dõi hiệu lực, hạn, evidence và cảnh báo.
- **Remediation owner:** khắc phục để trở về baseline.
- **Assurance reviewer:** kiểm tra phạm vi và điều kiện theo evidence.

Một exception hết hạn, sai scope hoặc mất compensating control không được “tự sống tiếp” chỉ vì ticket tồn tại. Phải có owner và trigger escalation rõ, đồng thời giữ trạng thái technical noncompliance tách khỏi risk acceptance.

## 15. Evidence ownership: ai chịu trách nhiệm dữ liệu được tin cậy?

Nhiều chương trình có owner cho security controls nhưng bỏ qua **owner của nguồn evidence**. Đây là một lỗ hổng thực chất.

Ví dụ, control yêu cầu audit logs đầy đủ nhưng **ai** chịu trách nhiệm:
- Danh mục các ứng dụng phải gửi log?
- Collector có quyền đọc từ mọi cloud account?
- Schema và query trong evaluator?
- Mốc thời gian, timestamp, lost events và pagination?
- Khi SIEM parser thay đổi, ai kiểm tra lại rule?
- Lưu trữ, retention, integrity và quyền truy cập evidence?
- Việc thông báo “không đủ evidence” cho người quyết định?

### 15.1. Phân chia evidence owner và evidence producer

- **Evidence producer:** hệ thống hoặc nhóm tạo sự kiện/kết quả gốc, như application team phát audit event.
- **Evidence custodian:** vận hành thu thập, truy xuất, bảo quản và metadata.
- **Control evidence owner:** chịu trách nhiệm evidence plan đáp ứng scope/criteria của control.
- **Assurance assessor:** kiểm tra evidence có phù hợp và đủ để kết luận; có thể yêu cầu bổ sung hoặc đánh dấu UNKNOWN.

Các vai này có thể trùng trong một tổ chức nhỏ nhưng cần **nêu rõ nghĩa vụ và giới hạn kết luận**.

### 15.2. Các chỉ số chất lượng evidence mà owner phải theo dõi

| Thuộc tính | Câu hỏi owner cần trả lời |
|---|---|
| Completeness | Đã thu mọi source/asset thuộc population? |
| Freshness | Thời điểm đánh giá có đủ mới so với rủi ro? |
| Accuracy | Rule/query và timestamp đúng? |
| Integrity | Bằng chứng có thể bị thay/cắt mà không phát hiện? |
| Reliability | Collector có quyền, đủ sức đọc và xử lý API errors? |
| Relevance | Bằng chứng hỗ trợ đúng claim hay chỉ liên quan chung? |
| Period | Kết luận là snapshot hay toàn cửa sổ vận hành? |
| Reproducibility | Có thể lặp phép kiểm tra với run ID, input/expected/actual? |
| Independence | Có nguồn lỗi chung hoặc thiên lệch tự đánh giá? |
| Historical gaps | Có khoảng mất log hay data source không thể khôi phục? |

Không có evidence **không đồng nghĩa control chắc chắn thất bại**. Nhưng thiếu nguồn trọng yếu làm giảm khả năng ra quyết định; evidence owner phải có quyền escalated khi phát hiện, không âm thầm thay UNKNOWN thành PASS.

## 16. Khi không xác định được owner: xử lý orphaned assets/controls

Đối tượng **orphaned** là tài sản, control, evidence source, risk hoặc finding **không có owner còn hiệu lực hoặc đủ thẩm quyền trong phạm vi cần thiết**.

Ví dụ:
- Service cũ còn chạy production nhưng đội phát triển đã giải thể.
- Một cloud account mới được tạo nhưng chưa được đưa vào service catalog.
- Security rule vẫn chạy nhưng người viết rule đã chuyển nhóm, không ai review false positive.
- Finding high-risk được gán cho một tài khoản đã nghỉ việc.
- Vendor integration có hợp đồng nhưng không có đầu mối nội bộ nhận rủi ro.
- Exception được duyệt năm trước nhưng chủ sở hữu tài sản đã đổi.

### 16.1. Không điền owner giả để tăng tỷ lệ bao phủ

Các giá trị như \`owner: unknown\`, \`owner: security\` hoặc \`owner: shared-team\` chỉ có thể là **trạng thái tạm/đầu mối phối hợp**, không được trình bày như accountability đầy đủ nếu không biết người nhận thực.

Một quy trình orphan management:

1. Phát hiện owner vắng, không phản hồi, hết hiệu lực hoặc mất quyền.
2. Tạo vấn đề governance với object ID, asset criticality và rủi ro.
3. Giao **temporary coordinating owner** được ủy quyền theo cơ chế tổ chức, đồng thời ghi rõ owner chính chưa xác lập.
4. Xác minh hệ thống đang chạy ở đâu và những control/finding trọng yếu có ảnh hưởng.
5. Escalate tới service portfolio/business management và risk authority phù hợp.
6. Phân công owner chính có năng lực, quyền và bằng chứng nhận trách nhiệm.
7. Xác nhận handover, review evidence hiện trạng và những việc quá hạn.
8. Cập nhật register, thông báo bên liên quan và theo dõi tái diễn.

**Không nên tự động tắt một dịch vụ production chỉ vì không tìm thấy owner**; việc containment/decommission phải qua đánh giá tác động, quyền quyết định và quy trình an toàn.

### 16.2. Pseudocode kiểm tra coverage

~~~text
for object in required_assurance_objects:
    ownership = ownership_register.lookup(object.id)

    if ownership is missing:
        flag("ORPHANED_OBJECT", object.id)
        notify(governance_escalation_owner)
        continue

    if ownership.owner_inactive or ownership.scope_mismatch:
        flag("INVALID_OWNER_ASSIGNMENT", object.id)
        notify(governance_escalation_owner)
        continue

    if ownership.effective_until_expired:
        flag("EXPIRED_OWNERSHIP", object.id)
        notify(governance_escalation_owner)
        continue

    if object.is_high_risk and ownership.no_valid_escalation:
        flag("MATERIAL_OWNERSHIP_GAP", object.id)
        notify(security_assurance_program_owner)
~~~

Đây là logic minh họa, **không phải script sẵn sàng chạy production**. Cần xác minh dữ liệu HR/IAM, phân quyền và quy tắc privacy trước khi tự động đánh giá trạng thái nhân sự; tránh gửi thông tin cá nhân không cần thiết trong cảnh báo.

## 17. Chuyển giao owner khi có thay đổi

Ownership không phải thuộc tính cố định vĩnh viễn. Nó phải được cập nhật khi:
- Đội sở hữu sản phẩm được tái cấu trúc.
- Một dịch vụ chuyển từ build team sang operations.
- Cloud account/region, identity domain hoặc data flow mới xuất hiện.
- Nhà cung cấp thay đổi trách nhiệm hoặc hợp đồng kết thúc.
- Control hoặc security requirement được sửa đổi.
- Nhân sự owner rời vai trò hoặc vắng mặt dài hạn.
- Hệ thống decommission, merge hoặc split service.
- Incident cho thấy quyền hiện có không đủ để xử lý rủi ro.

### 17.1. Checklist chuyển giao

| Nội dung bàn giao | Điều cần xác minh |
|---|---|
| Asset/service scope | Đúng inventory, môi trường, region, dữ liệu và dependency |
| Active controls | Control objectives, config, owner và cadence |
| Evidence sources | Access, source-health, retention, query, dashboard limitations |
| Open findings | Severity, CAP, deadline, retest status |
| Exceptions/risks | Phạm vi, expiry, compensating control và quyền quyết định |
| Active changes/releases | Những thay đổi có thể làm mất hiệu lực evidence |
| Runbooks | Incident, rollback, access review, DR và emergency procedure |
| Contacts/delegation | Owner mới, backup và escalation |
| Acceptance | Người nhận xác nhận và thời điểm hiệu lực |
| Historical trace | Giữ owner cũ, thời kỳ trách nhiệm và quyết định liên quan |

Handover tốt phải nêu cả **những vấn đề chưa hoàn thành**, không chỉ giao tài liệu đẹp. Không nên xoá lịch sử owner trước để làm cho finding quá hạn không có người chịu trách nhiệm.

### 17.2. Giai đoạn chuyển tiếp

Nếu người cũ rời trước khi người mới nhận, phải có **interim ownership** được ủy quyền. Không nên để khoảng trống “sẽ bổ sung sau”. Với những rủi ro trọng yếu, cần escalation và xem xét biện pháp bảo vệ tạm thời khi thiếu khả năng vận hành.

## 18. Trách nhiệm trong thay đổi và phát hành

Một change có thể làm biến đổi không chỉ hệ thống mà cả ownership của control/evidence.

Ví dụ release mới:
- Bổ sung API export với data owner khác.
- Chuyển token validation từ application sang gateway.
- Đưa log ingestion sang nền tảng thuê ngoài.
- Tăng số lượng cloud account và region.
- Tái cấu trúc nhóm vận hành.

Trước GO/NO-GO cần xác minh:

1. **Ai sở hữu control trước và sau thay đổi?**
2. Các giả định về ownership có còn đúng ở trust boundary mới?
3. Evidence source nào được thay, ai kiểm tra dữ liệu và query?
4. Rủi ro và findings đang mở có owner nhận handoff?
5. Ai có quyền rollback/forward fix và phê duyệt exception?
6. Monitoring, on-call và incident escalation đã được cập nhật?
7. Assurance case/claim có cần reviewer xác nhận lại phạm vi không?

Một release có thể đạt test chức năng nhưng **chưa sẵn sàng vận hành** nếu chưa có owner cho service mới, logging source hoặc critical control. Đây là một **release readiness risk**, cần được báo đúng mức thay vì chỉ tập trung vào pipeline.

## 19. Case study A: xác định owner cho API SaaS đa tenant

**Toàn bộ tên, số liệu và tình huống trong mục này là giả định để học.**

### 19.1. Bối cảnh

Một nền tảng SaaS có:
- 48 endpoint xử lý hồ sơ khách hàng.
- 4 cloud account production.
- Một IdP chung cho người dùng.
- Một hệ thống export bất đồng bộ.
- Một kho SIEM nhận audit events.
- Release R mới thêm signed download links.

Security objective: **không để user tenant A đọc dữ liệu thuộc tenant B qua các đường API trong phạm vi**.

### 19.2. Finding và sự đùn đẩy trách nhiệm

Pentest phát hiện signed URL có thể dùng từ một tenant không được phép trong tình huống thử nghiệm được phê duyệt. Nhóm Identity nói token đã đúng; backend nói đường export do platform vận hành; platform nói dữ liệu thuộc data team; security team nói “finding đã gửi”.

Không bên nào có thể đơn phương kết luận toàn bộ mục tiêu đã đạt. Bảng ownership cần phân rã:

| Đối tượng | Accountable owner | Responsible / phối hợp | Evidence |
|---|---|---|---|
| Policy tenant ownership | Data/security control owner | Product + AppSec | Requirement, role/tenant matrix |
| Authorization trong API | API service owner | Backend team | Code/config, negative/positive tests |
| Signed URL và object access | Export service owner | Platform + storage engineering | Link policy, expiry/access tests |
| IdP token identity | Identity platform owner | IAM team | IdP policy, token validation tests |
| Tập endpoint và phiên bản | API service owner | Release/QA | Router inventory, release manifest |
| Audit logging | Logging control owner | App + SIEM team | Source-to-SIEM checks, alerts |
| CAP cho finding | Assigned remediation owner | API/Export engineering | Change record, root-cause action |
| Retest và closure | Assurance verification authority | Independent tester | Test run, scope review, decision |
| Residual risk/exception | Authorized business risk owner | GRC + security advisor | Risk assessment, dated approval |

**Nguyên tắc:** có thể có nhiều Responsible, nhưng **mỗi hoạt động và quyết định cần A rõ**, không có một trường “global owner” có thể thay tất cả quyền trên.

### 19.3. Phân công cho CAP cụ thể

| Action | Owner thực hiện | Tiêu chí xác minh |
|---|---|---|
| Sửa tenant check tại lúc tạo export job | Backend/Export lead | Không tạo job trái quyền |
| Sửa kiểm tra ownership khi tải output | Export service owner | Signed URL không vượt quyền tenant/object |
| Đối chiếu 48 endpoint và async flows | API service owner | Inventory được kiểm chứng từ nhiều nguồn |
| Security regression trên đúng release R | Security test owner | Negative/positive cases, đúng artifact |
| Xác minh logging các truy cập bị từ chối | Logging evidence owner | Raw event tới SIEM, coverage và alert |
| Đánh giá tác động dữ liệu lịch sử | Data/privacy owner | Impact assessment có phạm vi và giới hạn |
| Retest và đóng finding | Independent assurance reviewer | Bằng chứng đúng closure criteria |

### 19.4. Kết quả sau phân công

Giả sử team đã sửa signed URL và retest trên 47/48 endpoint, nhưng một đường export cũ chưa có inventory và bằng chứng. Không được ghi “48 endpoint đã an toàn” dù mọi owner đã ký. **Ownership tốt giúp chỉ ra ai phải xử lý phần chưa chứng minh**, chứ không thay cho phép thử.

Kết luận assurance phù hợp có thể là:

> “Những đường đã được thử trên release R có bằng chứng đáp ứng authz theo ma trận được duyệt; một đường export còn thiếu xác minh nên top-level claim bao phủ toàn bộ 48 endpoint chưa đủ cơ sở kết luận. API/Export owner chịu trách nhiệm hoàn thiện test, assurance reviewer kiểm tra trước khi đóng, business risk owner được thông báo về residual risk.”

Đây là chuỗi **quản trị và bằng chứng**, không chỉ danh sách người được gắn ticket.

## 20. Case study B: hai ứng dụng mất security logging trong kỳ

### 20.1. Tình huống

Một công ty có tám ứng dụng quan trọng. Control ghi audit events yêu cầu toàn bộ hành động đặc quyền từ các ứng dụng production được gửi về SIEM. Audit phát hiện log của hai ứng dụng không được ingest trong ba ngày.

Ticket ban đầu gán cho “Security Operations” vì SIEM thuộc SOC. Nhưng điều tra cho thấy:
- Một ứng dụng không phát event theo schema mới.
- Ứng dụng còn lại có agent bị cấu hình sai sau release.
- SOC thiếu source-health alert cho cả hai.

### 20.2. Cách chia owner

| Vấn đề | Accountable owner | Responsible / evidence |
|---|---|---|
| Event schema tại source | Application service owner | Backend, test event source |
| Collector/forwarder | Platform operations owner | SRE, agent config và queue records |
| SIEM source inventory/alerts | SOC detection owner | Detection engineer, heartbeat và alert test |
| Tổng thể logging control | Logging control owner | Control criteria, coverage mapping |
| Assurance gap của kỳ audit | Assurance assessment owner | Reviewer, evidence, limitations |
| Risk về khoảng log mất | Authorized service/business risk owner | Impact assessment và decision |

### 20.3. Điều không được làm

Không thể dùng kết quả “logging đã được sửa và hiện hoạt động” để chứng minh **trong ba ngày trước đó có đủ audit events**. Không được chỉ đổi ticket SOC thành Closed rồi xoá historical gap.

Nên:
1. Xác định nguyên nhân và thời kỳ mất dữ liệu.
2. Tìm evidence lịch sử từ nguồn khác nếu phù hợp.
3. Mỗi owner sửa đúng phần của mình.
4. Test synthetic end-to-end và alert mất nguồn.
5. Reviewer xác minh current operation, giữ limitation của kỳ cũ.
6. Risk owner xử lý tác động và nghĩa vụ liên quan theo thẩm quyền.
7. Cập nhật control/evidence ownership khi thêm ứng dụng mới.

## 21. Đưa ownership vào lịch vận hành assurance

Một chương trình không thể chỉ giao owner lúc kickoff rồi bỏ đó.

### 21.1. Cadence minh họa

| Nhịp / Trigger | Hoạt động | Owner điển hình |
|---|---|---|
| Khi onboarding service/account | Đăng ký asset, data, control, evidence và risk owner | Service owner + program owner |
| Khi tạo/change requirement | Kiểm tra control catalog và quyền quyết định | Control owner + assurance lead |
| Theo lịch kiểm tra control | Thu evidence, xác minh quality/coverage, xử lý UNKNOWN | Evidence owner + control owner |
| Khi phát hiện FAIL | Triage, risk impact, CAP, containment | Control/service/remediation owners |
| Khi cần ngoại lệ | Đánh giá scope, compensating control, expiry, approval | Risk authority + GRC + control owner |
| Trước major release | Xem impact tới owner, test, evidence và runbook | Release/service owner + assurance |
| Sau finding đã sửa | Retest, reviewer kết luận, cập nhật hồ sơ | Independent verifier + closure authority |
| Định kỳ theo chương trình | Review orphan items, quá hạn, role mapping và delegation | Program owner + governance |
| Khi incident / threat mới | Xem lại assumptions, control và owner phù hợp | Incident commander + affected owners |

Tần suất cụ thể phải dựa trên chính sách, mức rủi ro, tốc độ thay đổi hệ thống và yêu cầu audit. Không nên áp cùng chu kỳ hàng quý cho một control biến đổi nhiều lần mỗi ngày mà không có cơ chế theo sự kiện.

### 21.2. Owner acknowledgement

Khi nhận control hay risk mới, owner nên xác nhận:
- Hiểu security objective, scope và tiêu chí.
- Có nguồn lực, quyền, thông tin và đường liên hệ.
- Nhận các finding, exception và nghĩa vụ đang mở.
- Biết thời hạn và tiêu chí escalation.
- Biết reviewer và ai có quyền ra quyết định cuối.

Việc acknowledgement phải có giá trị thực tế; không nên chỉ yêu cầu bấm “I accept” mà chưa cung cấp quyền truy cập hoặc lịch sử vấn đề.

## 22. Chỉ số cho chất lượng ownership

Những chỉ số hữu ích:

| Chỉ số | Giá trị | Lưu ý |
|---|---|---|
| **Owner coverage** | Tỷ lệ asset/control/risk có owner hợp lệ | Population phải đủ, không tính owner placeholder là hợp lệ |
| **Orphaned critical assets** | Số tài sản quan trọng không có accountable owner | Ưu tiên theo rủi ro, không che bằng tỷ lệ chung |
| **Owner acknowledgement latency** | Thời gian từ lúc gán đến khi người nhận xác nhận | Cần kiểm tra quyền/năng lực chứ không chỉ click |
| **Assignment validity** | Tỷ lệ mapping còn đúng sau thay đổi tổ chức | Cần đối chiếu directory, scope, quyền |
| **Finding assignment time** | Thời gian finding có remediation owner có thể thực thi | Không đo nhầm auto-assign tới hộp thư rỗng |
| **Overdue CAP by owner** | Các hành động quá hạn theo trách nhiệm | Phân biệt blockers do dependency hoặc quyền |
| **Evidence gaps without owner** | Số source/claim thiếu người xử lý UNKNOWN | Không được gán mọi gap mặc định cho auditor |
| **Exception expiry ownership** | Ngoại lệ có owner theo dõi và người duyệt hợp lệ | Ngoại lệ hết hạn vẫn cần xử lý |
| **Verified closure turnaround** | Từ khi fix implemented tới khi reviewer xác nhận | Retest chất lượng quan trọng hơn tốc độ |
| **Handover completeness** | Tỷ lệ bàn giao kèm unresolved items/evidence | Không chỉ đếm biên bản |
| **Repeated ownership conflicts** | Số finding bị chuyển qua lại nhiều nhóm | Dấu hiệu shared responsibility chưa rõ |

**Ownership metrics không phải xác suất hệ thống an toàn.** 100% object có owner hợp lệ là điều kiện governance tốt, nhưng không thay kiểm tra thực tế của security controls.

### 22.1. Chất lượng hơn tốc độ

Tự động gán mọi finding cho \`security-team\` có thể làm dashboard “100% assigned”, nhưng vẫn không có người đủ quyền sửa và chịu trách nhiệm. Chỉ số nên phân biệt:

- Assigned.
- Acknowledged.
- Owner authorized/capable.
- Action in progress.
- Implemented.
- Independently verified.

Mỗi trạng thái thể hiện một mức tiến độ khác nhau.

## 23. Anti-patterns khi xác định owner

| Anti-pattern | Hậu quả | Giải pháp |
|---|---|---|
| **“Security owns everything”** | Đội bảo mật không có quyền sửa mọi asset | Chỉ rõ control/service/risk/evidence owner theo đối tượng |
| **Owner là tên phòng ban chung** | Không có người nhận, backup và escalation | Role + responsible individual/rotation + authority |
| **Người làm cũng tự phê duyệt toàn bộ** | Xung đột lợi ích và false assurance | Independent review hoặc kiểm tra bù trừ |
| **Owner chỉ trên sơ đồ tổ chức** | Service mới không cập nhật | Liên kết runtime inventory và change/release |
| **Owner không có quyền/nguồn lực** | Ticket tồn đọng dù gán đủ | Kiểm tra delegation, budget, capacity |
| **Không ai chịu evidence gap** | UNKNOWN được biến thành PASS hoặc bỏ qua | Evidence owner/source-health responsibility |
| **Risk owner = ticket creator** | Sai người có thẩm quyền chấp nhận rủi ro | Delegation matrix và business impact |
| **Vendor được xem là owner duy nhất** | Mất internal accountability | Giao internal accountable owner và vendor R |
| **Không có đường chuyển giao** | Finding, exception và control thành orphaned | Handover checklist, backup, history |
| **Nhiều A cho một quyết định** | Tranh quyền hoặc trì hoãn quyết định | Chốt authority, một A rõ theo hoạt động |
| **Không bao giờ review mapping** | Account, region, đội và role thay đổi | Periodic/event-driven ownership verification |
| **Gán owner sau khi incident xảy ra** | Chậm triage và recovery | Ownership ngay từ onboarding và release |
| **Đóng finding khi owner báo Done** | Chưa retest hoặc kiểm tra scope | Tách remediation owner và verifier/closure authority |
| **Giả vờ đầy đủ bằng owner placeholder** | Orphaned asset bị che | Theo dõi placeholder như governance gap |
| **Coi risk acceptance là control PASS** | Sai assurance conclusion | Giữ technical status và decision riêng |
| **Chỉ có email cá nhân làm đầu mối** | Owner nghỉ việc, mất liên hệ | Quản lý role/service alias, backup và thời điểm hiệu lực |
| **RACI có nhưng không có bằng chứng thực hiện** | Bảng đẹp nhưng không accountability | Acknowledgement, work evidence, review |

## 24. Bài tập thực hành

### Bài tập A — Phân vai cho security logging

Một hệ thống có năm microservice, một collector chung và một SIEM. Một service không còn gửi audit events sau release, trong khi các service khác vẫn gửi bình thường.

1. Viết control objective và phạm vi logging.
2. Chỉ định **control owner, application owner, collector owner, evidence owner, assurance reviewer và risk owner**.
3. Thiết kế RACI cho sửa event schema, sửa collector, kiểm tra alert và quyết định closure.
4. Nêu evidence từng owner phải cung cấp và người nào có quyền quyết định retest đạt.
5. Viết nội dung escalation nếu không tìm được owner của microservice.
6. Giải thích vì sao không thể dùng tình trạng SIEM hiện “Healthy” để kết luận log của cả năm microservice đầy đủ.

### Bài tập B — Tài khoản cloud vô chủ

Tổ chức mới thêm một cloud account production bằng công cụ tự động. Account chạy workload chứa dữ liệu khách hàng, nhưng không có service catalog entry, owner và collector không có quyền đọc.

1. Phân loại các governance/control/evidence gaps có thể xảy ra.
2. Nêu owner tạm thời, tuyến escalation và những quyền quyết định cần có.
3. Đề xuất cách tìm owner chính và xác minh phạm vi tài sản/dữ liệu.
4. Viết kế hoạch cập nhật ownership register và evidence plan.
5. Giải thích vì sao việc tự đặt owner \`security\` không làm sự thiếu trách nhiệm biến mất.
6. Xây acceptance criteria để account được đưa vào assurance coverage đầy đủ.

### Bài tập C — Risk acceptance sai thẩm quyền

Một đội phát triển muốn trì hoãn vá lỗ hổng quan trọng trên API có dữ liệu nhạy cảm. Engineering manager tự ký “risk accepted” vì deadline release gần tới. Security assurance chưa đánh giá scope và compensating controls.

1. Phân biệt change approval, remediation ownership và quyền chấp nhận rủi ro.
2. Xác định người cần tham vấn và người có thẩm quyền quyết định theo risk policy.
3. Nêu các trường trong exception record và evidence bắt buộc.
4. Đề xuất CAP, deadline, monitoring và điều kiện thu hồi quyết định.
5. Viết kết luận audit đúng khi finding chưa verified fixed.
6. Giải thích vì sao một chữ ký không thể biến technical FAIL thành PASS.

### Bài tập D — Trùng ownership trong multi-tenant API

Một API export dùng chung IAM, object storage, data processing và signed download links. Khi xảy ra truy cập chéo tenant, từng nhóm cho rằng lỗi thuộc nhóm khác.

1. Vẽ dependency graph giữa các thành phần và control objectives.
2. Chỉ ra owner accountability cho chính sách tenant isolation, enforcement và bằng chứng.
3. Gán một remediation owner cho CAP, các responsible operators và independent verifier.
4. Đề xuất negative/positive tests và đối chiếu endpoint inventory.
5. Thiết kế escalation khi hai service owner không thống nhất trách nhiệm.
6. Viết tiêu chí closure có phạm vi để không tuyên bố bảo mật tuyệt đối.

### Bài tập E — Thay đổi nhân sự và ngoại lệ hết hạn

Một owner kiểm soát IAM chuyển công tác; trên hệ thống còn ba finding chưa retest và một exception sẽ hết hạn trong bảy ngày. Người kế nhiệm chưa chấp nhận ownership.

1. Nêu những đối tượng có nguy cơ orphaned.
2. Thiết kế interim ownership và yêu cầu chấp thuận chuyển giao.
3. Xác định ai theo dõi expiry, ai có quyền gia hạn và ai đánh giá rủi ro.
4. Đề xuất công việc quan trọng trước ngày ngoại lệ hết hạn.
5. Nêu evidence của handover và các điều kiện không được sửa lịch sử.
6. Thiết kế một metric phát hiện rủi ro ownership tương tự sớm.

**Gợi ý:** Câu trả lời đúng cần làm rõ **ai có quyền thực hiện, ai có trách nhiệm cuối, ai xác minh độc lập, ai chấp nhận rủi ro, phạm vi nào và bằng chứng nào**. Một danh sách tên người không đủ để chứng minh chương trình có ownership đáng tin.

## 25. Checklist áp dụng khi xác định owner

Trước khi đưa một service/control/risk mới vào chương trình, hãy kiểm tra:

- [ ] Đối tượng cần owner đã có ID, loại và phạm vi rõ.
- [ ] Mục tiêu bảo mật, control/requirement và kỳ đánh giá được xác định.
- [ ] Có accountable owner hợp lệ cho từng quyết định trọng yếu.
- [ ] Responsible implementer/operator được ghi rõ.
- [ ] Có evidence producer/custodian và người chịu data-quality gates.
- [ ] Có service/system/data owner khi ảnh hưởng tài sản hoặc dữ liệu.
- [ ] Có risk owner đủ thẩm quyền khi có residual risk/exception.
- [ ] Có reviewer/independent verifier phù hợp rủi ro.
- [ ] RACI không có hoạt động trọng yếu thiếu A, không nhập nhằng nhiều A.
- [ ] Owner đã chấp nhận trách nhiệm và có quyền/nguồn lực cần thiết.
- [ ] Có backup, escalation path, lịch phản hồi và tình huống vắng mặt.
- [ ] Scope của owner đúng environment, account, region, role và thời kỳ.
- [ ] Shared controls có phân chia trách nhiệm end-to-end.
- [ ] Cloud/vendor responsibility có internal accountable owner.
- [ ] Finding/CAP/exception/retest/closure có owner khác nhau khi cần.
- [ ] Owner mapping liên kết asset inventory, control catalog và evidence plan.
- [ ] Có kiểm tra đối tượng orphaned và xử lý owner placeholder.
- [ ] Có handover checklist khi thay đổi team, vendor hoặc service.
- [ ] Change/release/incident có trigger review lại ownership.
- [ ] Quyết định, acknowledgement, retest và evidence được lưu có truy vết.
- [ ] Không dùng số lượng người được gán để thay kết luận security control đạt.

Checklist hỗ trợ đánh giá quản trị nhưng **không thay thế xác minh thực tế** quyền hạn của owner, chất lượng bằng chứng và hiệu quả của security controls.

## 26. Ghi nhớ

**Xác định owner** trong chương trình Security Assurance là thiết kế một mạng trách nhiệm **có quyền, có phạm vi, có bằng chứng và có đường escalation** cho toàn bộ vòng đời của mục tiêu bảo mật. Không phải tìm một “đầu mối Security” cho mọi việc, mà là xác định người chịu trách nhiệm cuối cùng phù hợp với **từng đối tượng và từng loại quyết định**.

Một thiết kế đáng tin giữ được chuỗi:

**Risk / Security objective → Asset/Service/Data owner → Security requirement & Control owner → Implementation operator → Evidence custodian → Assurance assessor → Finding/CAP owner → Independent verifier → Authorized risk/exception decision → Continuous review.**

Chương trình hoạt động hiệu quả khi mọi control trọng yếu và finding có owner hợp lệ, evidence gap không bị bỏ quên, người thực hiện sửa không tự thay thế bước xác minh cần thiết, ngoại lệ không bị chấp nhận sai quyền và việc chuyển giao không làm thất lạc trách nhiệm. **Ownership không phải một trường metadata để điền đủ; đó là điều kiện để mỗi kết luận assurance có người giải thích, người hành động và người chịu trách nhiệm.**
