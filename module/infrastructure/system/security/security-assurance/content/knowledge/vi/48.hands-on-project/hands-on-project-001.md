# Dự án thực hành: Lập Risk Register cho một nền tảng SaaS

**Lập risk register** (sổ đăng ký rủi ro) không chỉ là tạo một bảng liệt kê “High / Medium / Low”. Một risk register có thể hỗ trợ **security assurance** khi mỗi rủi ro liên kết được với tài sản, kịch bản đe dọa, security objective, bằng chứng, control hiện hữu, người chịu trách nhiệm, phương án xử lý, thời hạn và phép kiểm chứng hiệu lực. Điều quan trọng nhất là **không đánh đồng điểm rủi ro do con người ước lượng với bằng chứng rằng một hệ thống đã an toàn**.

Trong dự án thuộc chương **Dự án thực hành** của module **SECURITY_SECURITY_ASSURANCE**, bạn sẽ đóng vai nhóm Security Assurance xây dựng risk register cho một nền tảng SaaS giả định. Bạn thực hành xuyên suốt chuỗi **phân tích rủi ro → ánh xạ yêu cầu và security controls → kiểm thử và thu evidence → quyết định xử lý → remediation và audit → đánh giá lại liên tục**. Dữ liệu, tên tài sản và tình huống đều **mô phỏng**; không có hệ thống thật hoặc yêu cầu thực hiện kiểm thử tấn công trên dịch vụ công cộng.

Kết thúc dự án, bạn cần tạo được một risk register có thể được một reviewer độc lập dùng để tìm hiểu **vì sao rủi ro tồn tại, nó ảnh hưởng điều gì, độ chắc chắn của kết luận đến đâu, ai có quyền xử lý và bằng chứng nào cần có trước khi đóng**.

## 1. Mục tiêu và tiêu chí hoàn thành dự án

Sau dự án, bạn có thể:

1. Xác định **phạm vi, giả định và tài sản** cần đưa vào risk register.
2. Viết **risk scenario** rõ nguyên nhân, threat path, asset, hậu quả và security objective.
3. Phân biệt risk, threat, vulnerability, security finding và evidence gap.
4. Đánh giá **likelihood** và **impact** theo thang đã công bố, giải thích điểm số.
5. Phân biệt **inherent risk**, **current risk** và **projected residual/target risk**.
6. Ánh xạ security controls và kiểm tra bằng chứng hiệu lực hiện hữu.
7. Thiết kế **risk treatment**: mitigate, avoid, transfer/share trong giới hạn, accept theo thẩm quyền hoặc investigate.
8. Chỉ định risk owner, action owner, control owner, reviewer và người phê duyệt.
9. Lập danh sách actions, dependencies, deadlines, control tests và evidence required.
10. Tạo báo cáo tóm tắt có số liệu đúng, minh bạch về gaps, tuổi dữ liệu và rủi ro chưa xử lý.
11. Định nghĩa event triggers để rà soát lại khi môi trường hoặc nguy cơ thay đổi.
12. Bảo toàn audit trail và lập luận giúp người khác phản biện mức rủi ro.

**Điều kiện hoàn thành:** sản phẩm không chỉ có bảng “risk ID, title, score”. Mỗi tình huống trọng yếu phải có **risk statement, scope, rationale, current controls, evidence, treatment, owner, target outcome và verification**. Nếu dữ liệu thiếu, ghi **INCONCLUSIVE/NEEDS_EVIDENCE**, không tự tạo kết luận PASS.

## 2. Bộ sản phẩm cần nộp (deliverables)

Bạn có thể tạo các sản phẩm trong một repository học tập hoặc bộ tài liệu độc lập; đây là **đầu ra của bài thực hành**, không phải yêu cầu chỉnh sửa những file khác của module.

| Sản phẩm | Nội dung bắt buộc | Reviewer tìm gì? |
|---|---|---|
| **A. Scope & asset inventory** | Tài sản, dữ liệu, môi trường, owner, criticality, trust boundaries. | Đã xác định đầy đủ đối tượng cần quản trị chưa? |
| **B. Risk methodology** | Định nghĩa scenario, thang likelihood/impact, mức ưu tiên, confidence, review cadence. | Hai người có thể dùng cùng quy tắc để đánh giá không? |
| **C. Risk register** | Tối thiểu 8 risk scenarios có ID, current assessment, evidence và ownership. | Có thể lần từ risk tới control và tài sản không? |
| **D. Risk treatment plan** | Hành động, điều kiện, deadline, dependencies, mitigation, quyết định cần phê duyệt. | Kế hoạch có khả thi, đo được và đúng thẩm quyền? |
| **E. Evidence index** | Evidence ID, nguồn, scope, timestamp, collector, completeness và giới hạn. | Có thể kiểm chứng từng nhận định quan trọng? |
| **F. Executive summary** | Phân bố rủi ro, coverage, key risks, unresolved unknowns và decisions needed. | Có giúp quản lý hành động mà không che khoảng trống? |
| **G. Review & validation log** | Kiểm tra nguồn, phản biện, thay đổi version, người review và retest plans. | Có khả năng audit, cập nhật và tránh báo cáo sai không? |

**Quy mô gợi ý:** 8–12 rủi ro, 10–15 asset, ít nhất 3 nhóm controls, 2 loại evidence gap và 1 tình huống cần quyết định risk acceptance/exception. Các số này chỉ là phạm vi học tập, **không phải tiêu chuẩn ngành**. Mục tiêu là chất lượng phân tích, không phải số dòng.

## 3. Bối cảnh lab: Nền tảng SaaS Minh Hải (giả định)

Công ty **Minh Hải SaaS** vận hành hệ thống quản lý đơn hàng và hóa đơn cho khách hàng doanh nghiệp. Khách hàng được cô lập theo **tenant ID**. Hệ thống xử lý thông tin liên hệ, hóa đơn và dữ liệu giao dịch; yêu cầu bảo mật nội bộ nhấn mạnh **phân quyền đúng tenant, auditability, bảo vệ dữ liệu, least privilege và khả năng khôi phục**.

### 3.1. Kiến trúc tối giản

~~~mermaid
flowchart TD
    U["Người dùng của các tenant"] --> GW["API Gateway / WAF"]
    GW --> API["A-01 Order API"]
    API --> DB["A-02 Transaction DB"]
    API --> OBJ["A-03 Invoice Bucket"]
    API --> Q["A-11 Async Worker / Queue"]
    IDP["A-10 Identity Provider"] --> API
    IAM["A-04 Cloud IAM"] --> API
    CI["A-05 Build / Deployment"] --> API
    CI --> Q
    API --> LOG["A-06 Audit Pipeline / SIEM"]
    DB --> LOG
    OBJ --> LOG
    DB --> BAK["A-07 Backup Repository"]
    KEY["A-08 KMS / Key Management"] --> DB
    KEY --> BAK
    V["A-09 External Notification SaaS"] --> API
    IAC["A-12 IaC / Policy Repository"] --> IAM
    IAC --> CI
~~~

**Trust boundaries chính:** Internet → gateway → application; application identity → cloud resources; SaaS → vendor; production → audit pipeline; dữ liệu sản xuất → backup/key system; CI/CD → production deployment; tenant A ↔ tenant B qua cùng API.

### 3.2. Danh sách tài sản khởi tạo

| Asset ID | Tài sản / chức năng | Dữ liệu hoặc quyền | Criticality ví dụ | Owner ban đầu |
|---|---|---|---|---|
| **A-01** | Public Order API | Tenant records và authorization logic | Very High | Order Service Owner |
| **A-02** | Transaction PostgreSQL | Giao dịch và đối soát | Very High | Data Platform Owner |
| **A-03** | Invoice Object Storage | Hóa đơn khách hàng | Very High | Billing Service Owner |
| **A-04** | Cloud IAM | Quyền service, admin, trust policy | Very High | Cloud IAM Owner |
| **A-05** | CI/CD và secrets access | Build artifacts, deployment rights | High | Developer Platform Owner |
| **A-06** | SIEM/Log Pipeline | Audit events và điều tra | High | Security Monitoring Owner |
| **A-07** | Backup Repository | Recovery data, copies | Very High | Backup/DR Owner |
| **A-08** | KMS | Encryption keys, decrypt capability | Very High | Key Management Owner |
| **A-09** | Vendor Notification SaaS | Dữ liệu email/thông báo | Medium | Vendor Manager |
| **A-10** | Identity Provider | User/admin identity & MFA | Very High | Identity Owner |
| **A-11** | Async Worker / Queue | Event processing, invoice exports | High | Order Service Owner |
| **A-12** | IaC / Policy Repository | Desired cloud state, review gates | High | Platform Engineering Owner |

Các mức criticality là **giả định dùng trong bài**. Trong hệ thống thật, phải đối chiếu Business Impact Analysis (BIA), data classification, service criticality, dependencies và người sở hữu. Một asset có thể có nhiều owner theo trách nhiệm kỹ thuật/nghiệp vụ; risk owner vẫn phải được xác định cho **kịch bản rủi ro**, không chỉ copy tên admin.

### 3.3. Mốc dữ liệu và giả định

- Tất cả bằng chứng mô phỏng được thu hoặc lập vào **ngày 28/11/2026 (UTC)** trừ khi ghi rõ khác.
- Tập tài sản trên đại diện **phạm vi lab**, chưa chứng minh là toàn bộ hệ thống thật.
- Không có bằng chứng xâm nhập thành công được cung cấp; một finding có thể cho thấy đường truy cập không đúng nhưng **không tự chứng minh dữ liệu đã bị đánh cắp**.
- Hạn xử lý dưới đây do **chính sách giả định của bài** quyết định; người học không được suy ra SLA chung cho mọi tổ chức.
- Dữ liệu cá nhân, mật khẩu, access token, khóa riêng hoặc log nhạy cảm không được đưa vào bản nộp; dùng resource IDs và tham chiếu evidence giả lập.

## 4. Dữ liệu đầu vào: Observation và evidence cards

Bạn nhận được bộ quan sát dưới đây. Hãy phân biệt **điều đã được quan sát, điều đã xác minh và điều còn giả định**.

| Evidence ID | Quan sát mô phỏng | Trạng thái chứng cứ | Scope/giới hạn |
|---|---|---|---|
| **E-01** | Authorization negative test cho thấy 2 trong 6 API endpoints được thử cho phép truy xuất hóa đơn khác tenant. | **CONFIRMED FAILURE** trong đường được thử. | Chưa test tất cả endpoints/versions; chưa có bằng chứng attacker đã khai thác. |
| **E-02** | Test anonymous GET thành công với một object hóa đơn trong bucket A-03; config cho phép public read. | **CONFIRMED FAILURE** cho object và policy trong scope. | Cần inventory object/bucket, log truy cập và data impact. |
| **E-03** | Effective IAM policy cho service account của A-11 có wildcard write trên nhiều production buckets ngoài nhu cầu công việc. | **CONFIRMED GAP** theo least privilege. | Cần map role inheritance, downstream nghiệp vụ và external principals. |
| **E-04** | CI/CD deploy token có thời hạn dài, scope ghi production deployment và rotation history thiếu một kỳ. | **CONFIRMED PROCESS/CONFIG GAP** theo baseline giả định. | Không có bằng chứng token bị lộ hoặc lạm dụng. |
| **E-05** | Synthetic database audit event có tại nguồn A-02 nhưng không xuất hiện ở SIEM A-06 trong cửa sổ kiểm tra. | **CONFIRMED END-TO-END LOGGING GAP** cho đường được thử. | Cần kiểm tra pipeline, quyền, retry và những source khác. |
| **E-06** | Backup jobs A-07 báo thành công; không có restore rehearsal evidence trong khoảng 90 ngày, đồng thời dự kiến đổi KMS key A-08. | **EVIDENCE GAP** về khả năng khôi phục sau rotation. | Không thể suy “backup hỏng”; cần restore/decrypt test trước key deletion. |
| **E-07** | Vendor A-09 công bố retention log quản trị 30 ngày; chuẩn nội bộ dự án yêu cầu 90 ngày cho use case liên quan. | **POLICY DEVIATION TO REVIEW**. | Phải xác định dữ liệu/luồng và khả năng áp dụng của hợp đồng/luật riêng. |
| **E-08** | SCA báo dependency có advisory nghiêm trọng trong image đang dùng bởi A-01, nhưng chưa xác minh reachability và điều kiện khai thác. | **POTENTIAL VULNERABILITY**; cần triage. | Có thể affected nhưng exploitability thực chưa kết luận. |
| **E-09** | Cloud organization inventory cho thấy 12 tài sản lab; collector kiểm được 11, A-09 chưa có bằng chứng config/tenant từ vendor. | **COVERAGE GAP**. | Không tự coi A-09 PASS hoặc FAIL cho tất cả security controls. |
| **E-10** | Thay đổi IAM tuần trước có approval cho A-11 nhưng không cho phép wildcard write. | **AUTHORIZATION MISMATCH** với E-03. | Xác minh bản approval và scope; xem emergency/exception nếu có. |
| **E-11** | Risk owner registry chưa có người nhận trách nhiệm risk scenario liên quan A-07/A-08. | **OWNERSHIP GAP**. | Không mặc định người quản lý KMS có quyền accept mọi rủi ro. |
| **E-12** | CI/CD có một release gần nhất với test PASS ở staging, production IAM/queue khác staging. | **LIMITED TEST EVIDENCE**. | Không suy PASS cho production mà không kiểm tra environment delta. |

### 4.1. Bài tập đầu vào: Phân loại quan sát

Hãy đánh dấu mỗi evidence card thuộc một hoặc nhiều nhóm: **control failure**, **vulnerability observation**, **evidence gap**, **authorization gap**, **ownership gap** và **uncertain threat scenario**. Giải thích vì sao **E-06 không đủ chứng minh không restore được**, và vì sao **E-01 đủ tạo finding trong hai endpoints đã kiểm nhưng chưa đủ chứng minh toàn bộ API endpoints bị lỗi**.

### 4.2. Evidence chất lượng không chỉ là file tồn tại

Mỗi card ở lab là tóm tắt. Nếu áp dụng thực tế, cần raw source, test method, timestamp, người thu, scope, tool version, account/region, permission, verdict và limitations. Ví dụ E-05 cần trace **synthetic event source → collector → queue/parser → SIEM**, không chỉ ảnh chụp màn hình SIEM không có dữ liệu.

## 5. Chuẩn bị phạm vi và risk assessment method

Trước khi đánh giá rủi ro, tạo **risk methodology note** có phiên bản và được reviewer chấp nhận. Trong lab này dùng mô hình minh họa 5×5. Cần lưu phương pháp, không đổi giữa chừng để có số đẹp.

### 5.1. Định nghĩa đơn vị quan sát

Một **risk record** biểu diễn **một kịch bản rủi ro có đường nhân quả và kết quả bất lợi cụ thể**, không phải một scan alert. Một vulnerability có thể góp phần vào nhiều risk scenarios; ngược lại, một risk scenario có thể có nhiều findings/controls.

**Mẫu câu:**

> Do **[threat actor / accidental event]** có thể lợi dụng **[vulnerability / control gap]** trên **[asset / trust boundary]**, dẫn đến **[undesired event]** và gây **[business/security impact]** đối với **[scope / data / service]**.

Ví dụ: “Do API không kiểm tra tenant ownership cho một số yêu cầu đọc, một tài khoản thuộc tenant A có thể truy cập hóa đơn tenant B, dẫn đến lộ dữ liệu khách hàng và vi phạm mục tiêu cô lập tenant trong những đường API bị ảnh hưởng.”

Không viết “Rủi ro: API lỗi” nếu không có threat path và impact.

### 5.2. Likelihood 1–5 cho bài học

| Mức | Tên | Căn cứ minh họa |
|---|---|---|
| **1** | Hiếm trong điều kiện hiện tại | Đường khai thác khó tiếp cận, nhiều điều kiện độc lập hoặc bảo vệ đã kiểm chứng mạnh. |
| **2** | Khó xảy ra | Có đường khả thi hạn chế, điều kiện khai thác không thuận lợi hoặc control giảm khả năng đáng kể. |
| **3** | Có khả năng | Kịch bản hợp lý, preconditions tồn tại, exposure hoặc controls còn lỗ hổng rõ. |
| **4** | Dễ xảy ra | Exposure và đường tấn công tương đối thuận lợi, control gap đã quan sát, attacker có thể thực hiện. |
| **5** | Rất dễ / đang diễn ra theo căn cứ | Đường khai thác lặp lại hoặc hoạt động trái phép đang diễn ra được xác minh. |

Đây là **thang đánh giá định tính có cấu trúc**, không phải tần suất xác suất 20%–100%. **Một lỗ hổng đã được test thành công không tự chứng minh cuộc tấn công đang diễn ra**: vẫn cần phân tích reachability, attacker prerequisites, frequency và threat context để chọn likelihood.

### 5.3. Impact 1–5 cho bài học

| Mức | Tên | Căn cứ minh họa |
|---|---|---|
| **1** | Rất thấp | Tác động cục bộ, không ảnh hưởng đáng kể bảo mật hay hoạt động. |
| **2** | Thấp | Gián đoạn nhỏ, dữ liệu hạn chế, có khả năng phục hồi dễ. |
| **3** | Trung bình | Ảnh hưởng dịch vụ hoặc dữ liệu có phạm vi rõ; cần xử lý phối hợp. |
| **4** | Lớn | Lộ hoặc sai lệch dữ liệu nhạy cảm, gián đoạn đáng kể, điều tra/khôi phục phức tạp. |
| **5** | Nghiêm trọng | Rò rỉ diện rộng, mất khả năng khôi phục trọng yếu hoặc ảnh hưởng kinh doanh/pháp lý nghiêm trọng theo bối cảnh. |

Khi chấm, ghi căn cứ từ **BIA, data classification, customer impact, CIA (confidentiality–integrity–availability)** và obligations. Nếu không có dữ kiện về tài sản hoặc số khách hàng chịu ảnh hưởng, đánh dấu **confidence thấp**, không bịa thiệt hại.

### 5.4. Công thức và phân hạng minh họa

~~~text
Risk score = Likelihood (1..5) × Impact (1..5)

1..4    = LOW
5..9    = MEDIUM
10..15  = HIGH
16..25  = CRITICAL
~~~

Ma trận để dễ hình dung:

| Likelihood \ Impact | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|
| **1** | 1 Low | 2 Low | 3 Low | 4 Low | 5 Medium |
| **2** | 2 Low | 4 Low | 6 Medium | 8 Medium | 10 High |
| **3** | 3 Low | 6 Medium | 9 Medium | 12 High | 15 High |
| **4** | 4 Low | 8 Medium | 12 High | 16 Critical | 20 Critical |
| **5** | 5 Medium | 10 High | 15 High | 20 Critical | 25 Critical |

**Cảnh báo phương pháp:** tích của hai thang ordinal không tạo ra xác suất hay expected monetary loss. Hai kịch bản cùng điểm 12 có thể khác đáng kể về exposure, thời gian xảy ra, uncertainty, regulatory impact và blast radius. Dùng score để **ưu tiên thảo luận**, không thay quyết định chuyên môn và những mandatory requirements. Các ngưỡng Low/Medium/High/Critical là **do lab giả định**, không áp dụng máy móc ngoài dự án.

### 5.5. Quy tắc đánh giá khi chưa đủ bằng chứng

Giữ **assessment_status** và **confidence** riêng:

- **CONFIRMED:** có evidence đáng tin cho những sự thật cơ bản (scope/control gap).
- **PROVISIONAL:** risk estimate dựa trên assumptions đang cần xác minh.
- **INCONCLUSIVE:** thiếu dữ liệu cần để kết luận một kiểm soát hoặc kịch bản cụ thể.
- **NOT_APPLICABLE:** có căn cứ rằng tiêu chí không thuộc scope, không dùng thay cho “không đo được”.

Risk score có thể là **ước lượng provisional** để ưu tiên thu evidence; phải ghi **assumptions và confidence**, không tự coi thành kết quả kiểm thử.

## 6. Ba lớp rủi ro: Inherent, Current và Projected Residual

Một lỗi phổ biến khi lập risk register là trừ ngay tác dụng của biện pháp **chưa triển khai** rồi báo “residual risk = Low”.

| Trục đánh giá | Nghĩa trong lab | Phải dựa vào gì? |
|---|---|---|
| **Inherent risk** | Rủi ro của kịch bản trước khi xét các controls giảm thiểu được định nghĩa trong phương pháp. | Asset/threat/impact, assumptions và phương pháp nhất quán. |
| **Current risk** | Rủi ro còn tồn tại **với controls hiện hữu được xem xét và xác minh tại thời điểm đánh giá**. | Effective controls, evidence test, known gaps, exposures. |
| **Projected residual / target risk** | Mức dự kiến **nếu** treatment được triển khai và vận hành đạt. | Giả định về hiệu lực treatment, plan và cách retest; chưa phải kết quả thực. |
| **Verified residual risk** | Đánh giá lại **sau** triển khai có bằng chứng, dưới exposure hiện tại. | Retest, runtime evidence, risk owner review và limitations. |

**Không có số điểm thấp nào được tự động “duyệt”**: rủi ro được chấp nhận theo thẩm quyền và ngưỡng tổ chức. Đặc biệt, nghĩa vụ hợp đồng/pháp luật có thể phải đáp ứng ngay cả khi score thấp.

### 6.1. Ví dụ định lượng cho một kịch bản

Giả sử hiện tại lỗ hổng phân quyền làm một endpoint truy xuất dữ liệu tenant khác với likelihood 4, impact 5 → **20 Critical**. Đội engineering đề xuất sửa authorization và thêm security test, dự kiến likelihood xuống 2, impact vẫn 5 → **10 High**.

- **Current = 20** là đánh giá tại thời điểm có lỗ hổng và exposure.
- **Projected = 10** là giả định tương lai theo phương án, **không phải hiện trạng**.
- Sau deploy, cần retest toàn scope, kiểm tra đường bypass và impact, rồi mới có **verified residual**. Có thể vẫn High nếu hệ thống còn path khác hoặc data exposure tiếp tục.
- Nếu có bằng chứng tấn công đang diễn ra, kịch bản có thể cần **incident handling**, không được đợi lịch họp risk committee.

## 7. Quy trình thực hiện dự án từ đầu đến cuối

~~~mermaid
flowchart TD
    S["1. Scope + asset population"] --> O["2. Evidence cards / observations"]
    O --> Q["3. Risk scenarios + control mapping"]
    Q --> A["4. Likelihood/impact + uncertainty"]
    A --> C["5. Existing control effectiveness"]
    C --> R["6. Current risk register"]
    R --> T["7. Risk treatment + ownership"]
    T --> P["8. Approval & action plan"]
    P --> V["9. Verification / retest gates"]
    V --> G["10. Reporting, triggers, review history"]
    G -->|thay đổi asset, threat, evidence, control| Q
~~~

### 7.1. Một lịch thực hành đề xuất

| Phiên | Trọng tâm | Sản phẩm |
|---|---|---|
| **Buổi 1** | Scope, inventory, data classification, requirement mapping. | Asset inventory và risk methodology v1. |
| **Buổi 2** | Risk discovery, viết scenario, phân tích E-01 đến E-12. | Draft register với evidence IDs. |
| **Buổi 3** | Đánh giá likelihood/impact, kiểm tra controls, chọn ưu tiên. | Current risk assessment có rationale. |
| **Buổi 4** | Treatment plan, owners, dependencies, acceptance/verification. | Action plan và decision log. |
| **Buổi 5** | Peer review, fault-injection với dữ liệu, reporting, demo. | Final package có giới hạn và sign-off. |

Thời lượng là gợi ý cho đào tạo; có thể rút gọn theo kỹ năng người học.

## 8. Bước 1 — Tạo Asset Register và chốt population

Khởi tạo bảng tài sản ở mục 3; thêm những trường sau:

~~~text
asset_id
service_or_business_process
environment
account_or_tenant
owner
data_classification
criticality
inbound_outbound_dependencies
control_population_ids
source_inventory_ref
last_verified_at_utc
completeness_status
~~~

### 8.1. Hành động thực hiện

1. Gán scope: production, các service có dữ liệu khách hàng và dependencies phục hồi.
2. Kiểm tra rằng tất cả 12 IDs trong bảng nằm trong population lab.
3. Đối chiếu E-09: collector chỉ có evidence cho **11/12 asset** ở một nguồn. Điều đó **không chứng minh** mọi control của 11 asset PASS.
4. Đánh dấu A-09 **EVIDENCE_GAP** với owner, nguồn cần yêu cầu vendor và thời hạn theo kế hoạch.
5. Ghi exclusions nếu có, kèm lý do; không xóa asset chỉ vì công cụ không đo được.
6. Chốt inventory snapshot/version để risk assessments có cùng phạm vi tại thời điểm đánh giá.

### 8.2. Tiêu chí nghiệm thu

**PASS** nếu mỗi asset có stable ID và owner liên hệ được; population được đối chiếu với nguồn giả lập; mọi asset chưa có evidence được ghi rõ. Nếu thiếu owner hoặc nguồn inventory, status là **NEEDS_RECONCILIATION**, không tự đánh dấu “out of scope”.

## 9. Bước 2 — Viết risk statements có nguyên nhân và hậu quả

Mỗi dòng risk register nên tập trung một **undesired business/security outcome**. Có thể dùng risk ID theo dạng `RISK-001`…`RISK-008`.

### 9.1. Ví dụ tốt và chưa tốt

| Cách ghi | Đánh giá |
|---|---|
| “API có bug.” | **Chưa tốt:** không có threat path, phạm vi, impact hoặc mục tiêu. |
| “RISK-001: Người dùng tenant A khai thác kiểm tra tenant ownership thiếu trên hai endpoint đã xác minh, đọc hóa đơn tenant B và làm lộ dữ liệu khách hàng.” | **Tốt hơn:** có actor, gap, tài sản, sự kiện bất lợi và impact. |
| “Logging lỗi.” | **Chưa tốt:** không nói nguồn, kỳ, rủi ro điều tra. |
| “RISK-005: Do audit events từ database không tới SIEM, truy cập dữ liệu trái phép có thể không được phát hiện hoặc không thể tái dựng đầy đủ, kéo dài thời gian response và gây thiếu bằng chứng.” | **Tốt hơn:** thể hiện risk event và hậu quả, không tự kết luận có tấn công. |
| “Backup không restore được vì chưa ai thử.” | **Sai bằng chứng:** thiếu test không chứng minh restore đã thất bại. |
| “RISK-006: Khi rotation KMS xảy ra mà khả năng restore/decrypt chưa được chứng minh, tổ chức có nguy cơ không khôi phục kịp dữ liệu giao dịch khi cần recovery.” | **Tốt hơn:** rủi ro được mô tả có điều kiện, evidence gap được nêu đúng. |

### 9.2. Tránh duplicate và double counting

Một root cause như wildcard IAM có thể hỗ trợ nhiều kịch bản: unauthorized data modification và gián đoạn do thao tác sai. Có thể tạo records riêng **nếu outcome, impact hoặc treatment khác nhau**, nhưng không copy điểm cùng threat rồi cộng thành tổng tiền rủi ro không có mô hình.

Một vulnerability ở A-01 có thể được scanner phát hiện nhiều lần; nên gắn findings vào cùng risk scenario canonical khi cùng điều kiện và mục tiêu. Có thể giữ nhiều evidence IDs và lịch sử phát hiện mà không tự nhân risk count.

## 10. Bước 3 — Ánh xạ Security Objectives và Controls

Một risk register dùng trong assurance cần cho phép truy vết từ **business objective tới requirement/control và phép kiểm tra**.

| Security objective | Control ID minh họa | Evidence/test cần có |
|---|---|---|
| Cô lập tenant, chặn truy cập trái quyền. | **CTRL-AUTH-01** | Positive/negative cross-tenant tests, effective auth rules, session/role review. |
| Bảo vệ hóa đơn lưu trữ. | **CTRL-DATA-02** | Bucket effective policy, anonymous GET denied, asset inventory, audit access. |
| Least privilege cho machine identities. | **CTRL-IAM-03** | Effective service roles, resource permissions, allowed/denied actions. |
| Quản lý secrets và deployment rights. | **CTRL-CICD-04** | Token scope/TTL, secret inventory, rotation, deploy provenance và audit. |
| Thu đủ audit events để phát hiện/điều tra. | **CTRL-LOG-05** | Source-to-SIEM synthetic test, inventory, log retention/config history. |
| Khả năng khôi phục dữ liệu sau thay đổi. | **CTRL-DR-06** | Restore rehearsal, backup key access, integrity và RTO/RPO theo BIA. |
| Quản lý vendor và retention phù hợp. | **CTRL-VEND-07** | Vendor policy, contract, log retention evidence, shared responsibility. |
| Quản lý component có lỗ hổng. | **CTRL-VULN-08** | SBOM/version, scanner finding, exploit prerequisites, fix/retest. |

Mã control và yêu cầu trên **chỉ phục vụ lab**, không khẳng định là mã từ ISO/NIST/PCI hoặc tiêu chuẩn pháp lý. Nếu sử dụng framework thật, cần tham chiếu phiên bản và applicability đúng; tên control có trong framework **không tự chứng minh đã triển khai hiệu quả**.

### 10.1. Test coverage theo objective

Với CTRL-AUTH-01, một test trên 2 endpoints không đủ suy toàn bộ application nếu còn endpoint khác. Với CTRL-LOG-05, một event nguồn đến SIEM không bảo đảm mọi loại sự kiện/kỳ/region. Bảng mapping phải ghi **tested scope vs target scope**, những assumptions và điểm cần test thêm.

## 11. Bước 4 — Đánh giá Likelihood, Impact và Confidence

Bạn có thể dùng bảng điểm v1.0 ở mục 5; reviewer phải thấy **vì sao** mức 4 và 5 được chọn thay vì chọn theo cảm tính.

### 11.1. Căn cứ likelihood

- Khả năng tiếp cận asset: public/private, actor cần quyền gì.
- Điều kiện khai thác: input, configuration, user privileges, token lifecycle.
- Kiểm soát phòng ngừa đang có, có test hay không.
- Threat activity, exploitation evidence nếu có; **không tự bịa threat intel**.
- Thời gian exposure, số đối tượng và thay đổi mới.
- Độ tin cậy của evidence và phần chưa test.

### 11.2. Căn cứ impact

- Dữ liệu: hóa đơn, giao dịch, khóa, audit evidence, PII.
- C: mất confidentiality, I: thay đổi dữ liệu, A: outage, mất recoverability.
- Số tenant/asset có thể ảnh hưởng; phạm vi đã chứng minh và worst credible case.
- BIA, sự phụ thuộc service và thời gian để khôi phục.
- Nghĩa vụ pháp lý/hợp đồng: **đánh giá riêng bằng nguồn áp dụng**, không tự gán mức phạt.
- Rủi ro an toàn vật lý nếu môi trường có liên quan; trong lab này không giả định OT.

### 11.3. Confidence riêng, không trộn vào phép nhân

| Confidence | Tiêu chí gợi ý |
|---|---|
| **HIGH** | Evidence đúng nguồn, runtime/effective state và scope được kiểm; limitations rõ. |
| **MEDIUM** | Có evidence đáng tin nhưng một số assumption hoặc phụ thuộc chưa được xác minh. |
| **LOW** | Dữ liệu nguồn thiếu, scope không rõ hoặc impact/likelihood phụ thuộc giả định lớn. |

Confidence **không làm giảm score tự động**. Risk high confidence thấp có thể cần **đánh giá thêm ngay** vì không chắc chắn là một rủi ro quyết định, không nên hạ thành Low.

## 12. Bước 5 — Risk Register mẫu với 8 kịch bản

Dưới đây là một **bản nháp tham chiếu** để bạn đối chiếu; các điểm số có tính giáo dục. `Current` là đánh giá theo giả định hiện trạng tại mốc lab, `Target` là dự kiến sau xử lý và **chưa verified**.

| Risk ID | Kịch bản và tài sản | Evidence / control | Current L×I | Tier hiện tại | Target L×I (giả định) | Confidence |
|---|---|---|---|---|---|---|
| **RISK-001** | Truy xuất chéo tenant qua API A-01. | E-01, CTRL-AUTH-01 | **4×5=20** | Critical | 2×5=10 (High) | High cho test scope; Medium cho all endpoints |
| **RISK-002** | Anonymous read hóa đơn từ object storage A-03. | E-02, CTRL-DATA-02 | **4×5=20** | Critical | 1×5=5 (Medium) | High cho object đã thử; Medium cho toàn bucket |
| **RISK-003** | Service identity A-11 ghi trái quyền qua IAM A-04. | E-03, E-10, CTRL-IAM-03 | **4×4=16** | Critical | 2×4=8 (Medium) | High cho effective role đã kiểm |
| **RISK-004** | CI deploy token dài hạn bị lộ/lạm dụng, gây deploy trái phép. | E-04, CTRL-CICD-04 | **3×4=12** | High | 1×4=4 (Low) | Medium; không có bằng chứng token đã bị lộ |
| **RISK-005** | Thiếu audit logs từ DB A-02 tới SIEM A-06 làm giảm detection/forensic. | E-05, CTRL-LOG-05 | **3×4=12** | High | 1×4=4 (Low) | High cho path đã thử; Medium cho kỳ |
| **RISK-006** | Khi cần restore sau KMS rotation, A-07/A-08 có nguy cơ không đáp ứng recovery objective. | E-06, E-11, CTRL-DR-06 | **3×5=15** | High | 1×5=5 (Medium) | Low/Provisional do thiếu restore test |
| **RISK-007** | Vendor A-09 thiếu retention audit logs theo baseline nội bộ cho use case. | E-07, E-09, CTRL-VEND-07 | **3×3=9** | Medium | 1×3=3 (Low) | Medium; external obligations chưa review |
| **RISK-008** | Vulnerable dependency trên A-01 có thể bị khai thác nếu preconditions thỏa. | E-08, CTRL-VULN-08 | **3×4=12** | High | 1×4=4 (Low) | Low/Provisional về reachability |

**Đếm theo current tiers:** 3 Critical, 4 High, 1 Medium, 0 Low trong **8 kịch bản minh họa**. Đây là số **risk scenarios**, không phải số assets, số vulnerabilities hay xác suất tổ chức bị tấn công. Đừng cộng các scores lại để kết luận “tổng rủi ro = 116” rồi diễn giải như giá trị tài chính hoặc xác suất.

### 12.1. Bản nháp không phải kết quả được kiểm toán

RISK-006 và RISK-008 có độ chắc chắn thấp. Điểm số hiện tại chỉ hỗ trợ **ưu tiên thu evidence và treatment planning**; không được gắn nhãn `VERIFIED` cho việc restore thất bại hay dependency khai thác được khi chưa có kết quả. Điểm target trong bảng không được ghi vào cột **verified_residual** trước retest.

### 12.2. Reviewer có thể thay điểm nếu có căn cứ

Chẳng hạn RISK-004 có thể nghiêm trọng hơn nếu token không chỉ deploy mà còn đọc production secrets trên tài sản critical. Khi đó phải cập nhật threat scenario, scope, impact/likelihood rationale, evidence và version; không chỉ sửa số từ 12 lên 20.

## 13. Bước 6 — Xây Treatment Plan có đo lường

Mỗi risk nên có **một risk treatment strategy** và các hành động cụ thể. Các phương án thường gồm:

- **Mitigate/reduce:** sửa nguyên nhân, giới hạn exposure, thêm control hoặc detection.
- **Avoid:** bỏ chức năng, ngừng use case hoặc decommission asset và xử lý dữ liệu an toàn.
- **Transfer/share một phần tác động:** hợp đồng/đơn vị xử lý/bảo hiểm khi phù hợp; không chuyển toàn bộ trách nhiệm hoặc nghĩa vụ pháp lý bằng một chữ ký.
- **Accept:** chủ thể có thẩm quyền chấp nhận residual risk trong phạm vi/điều kiện/thời hạn được phép.
- **Investigate:** bổ sung test, scope và evidence để quyết định risk treatment đúng.

Không gán `ACCEPT` cho finding chỉ vì chưa có người xử lý; một risk acceptance có **authority, rationale, expiration/review, conditions và monitoring**. Một yêu cầu bên ngoài bắt buộc không tự được miễn do nội bộ chấp thuận rủi ro.

### 13.1. Treatment plan minh họa theo từng risk

| Risk | Immediate containment / assessment | Permanent action | Verification gate |
|---|---|---|---|
| **RISK-001** | Giới hạn endpoint/path lỗi, kiểm tra access logs trong kỳ theo quyền. | Sửa tenant authorization tại data/service layer; thêm negative test tất cả affected routes. | Cross-tenant requests bị deny, legitimate tenant requests PASS, full endpoint inventory reconciled. |
| **RISK-002** | Chặn anonymous access và kiểm tra đối tượng bị ảnh hưởng. | Sửa IaC/storage guardrail, inventory tất cả invoice buckets. | Anonymous GET denied trên full scope, app authorized access PASS, drift alert test. |
| **RISK-003** | Giảm wildcard rights theo thay đổi an toàn; theo dõi sensitive writes. | Least-privilege role mapping + policy-as-code gate. | Effective deny/allow tests cho A-11 và rollback path, app flow PASS. |
| **RISK-004** | Thu hẹp token scope, giới hạn CI quyền production theo thẩm quyền. | Rotate/replace long-lived token bằng short-lived identity và secrets governance. | Old token revoked, new auth works, deploy provenance và audit evidence. |
| **RISK-005** | Khôi phục audit route/collector quyền và tăng kiểm tra nguồn khi cần. | Sửa pipeline, alert khi ingestion gap, source inventory. | Synthetic event từ DB tới SIEM, alert receipt và coverage test đúng kỳ. |
| **RISK-006** | Giữ key cũ an toàn, tạm dừng thao tác xóa key cho tới khi đủ evidence. | Restore/decrypt rehearsal, KMS lifecycle runbook, DR ownership. | Restore test, data integrity, key access và recovery objectives theo BIA. |
| **RISK-007** | Xin raw retention evidence và kiểm tra legal/contractual applicability. | Thương lượng retention/log export hoặc thay vendor/use case theo quyết định. | Retention đạt yêu cầu hoặc phương án thay thế được thẩm quyền chấp nhận, evidence có giới hạn. |
| **RISK-008** | Triage component/version/reachability, giảm attack surface khi phù hợp. | Update dependency, rebuild/redeploy, security regression. | Observed artifact version + scan/retest, exploit preconditions được đánh giá lại. |

**Containment ≠ permanent fix.** **PR merged ≠ control verified.** **Exception approved ≠ requirement PASS.** Mọi treatment cần giữ riêng trạng thái `PLANNED`, `IMPLEMENTED`, `RETESTING`, `VERIFIED` và `RISK_ACCEPTED` theo governance.

### 13.2. Phân loại thời hạn

Chọn ba mốc riêng theo tình huống:

1. **Mitigation due:** cần giảm phơi nhiễm khi nào?
2. **Permanent remediation due:** nguyên nhân phải được xử lý khi nào?
3. **Retest / evidence due:** reviewer có bằng chứng xác minh vào lúc nào?

Hạn trong hệ thống thật do **risk policy, exposure, BIA và obligations** xác định, không có mốc universal “Critical luôn 24h” áp dụng mọi nơi. Nếu deadline trễ, phải escalated/replanned có lưu lịch sử; không chỉ thay due date trên dashboard.

## 14. Bước 7 — Owner, RACI và quyền chấp nhận rủi ro

Một cột `owner=DevOps` không đủ để có accountability. Phải phân biệt:

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| **Risk owner** | Quyết định treatment/rủi ro còn lại theo quyền, chịu kết quả nghiệp vụ. | Business Owner của nền tảng hóa đơn. |
| **Asset/service owner** | Hiểu asset, dependencies, ưu tiên và nguồn lực triển khai. | Billing Service Owner. |
| **Control owner** | Xác định tiêu chí control và hiệu lực cần chứng minh. | Identity Security Owner cho IAM. |
| **Action owner** | Hoàn thành task, lập kế hoạch và cung cấp evidence. | Platform Engineering Engineer/Lead. |
| **Security assessor** | Xác minh scenario, evidence, assumptions và current control results. | Security Assurance Analyst. |
| **Independent verifier** | Retest, kiểm tra acceptance và giới hạn kết luận. | Security QA / Reviewer. |
| **Approving authority** | Chấp thuận risk acceptance, ngoại lệ hoặc release theo chính sách. | Authorized Business Risk Owner / Committee. |
| **Legal/Privacy/Compliance** | Xác định nghĩa vụ bên ngoài và quyền cho phép treatment. | Data Protection/Compliance Role. |

### 14.1. Bảng giao trách nhiệm RACI minh họa

| Công việc | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Discovery/risk statement | Security Assessor | Assurance Lead | Asset/Control Owner | Risk Owner |
| Impact/likelihood assessment | Security + Service Team | Business Risk Owner | Data Owner, Legal khi cần | Audit |
| Treatment design | Engineering/Control Owner | Service Owner | Security, Operations | Business Owner |
| Approve residual risk | Authorized Risk Owner | Risk Governance theo policy | Security/Legal/Compliance | Assurance |
| Implementation | Engineering | Service Owner | Change Authority/SRE | Risk Owner |
| Retest & closure | Independent Verifier | Control/Issue Owner | Engineering | Risk, Audit |

Ma trận là **mẫu để điều chỉnh**. Cần bảo đảm risk owner của RISK-006 được xác định (E-11 còn thiếu), và không nhầm người quản lý backup với người được ủy quyền chấp nhận nguy cơ mất dữ liệu của cả doanh nghiệp.

### 14.2. Khi owner chưa xác định

Ghi `OWNER_UNASSIGNED` và mở action định danh, kèm escalation. Không tự bỏ risk khỏi báo cáo vì “chưa ai nhận”. Đối với critical/high, thiếu owner bản thân là một **governance gap** cần được quản lý.

## 15. Bước 8 — Tạo Evidence Register và liên kết hai chiều

Một risk record có thể tham chiếu nhiều evidence IDs. Một evidence có thể hỗ trợ nhiều risks nhưng cần **nêu điều gì thực sự được chứng minh**.

~~~mermaid
flowchart TD
    O["Business/security objective"] --> REQ["Requirement/Control ID"]
    REQ --> R["Risk scenario + owner"]
    R --> EV["Evidence ID, source, scope, time"]
    EV --> TEST["Test methodology and result"]
    TEST --> CR["Current risk rating + confidence"]
    CR --> ACT["Treatment plan + change/deployment"]
    ACT --> RET["Independent retest"]
    RET --> VR["Verified residual assessment"]
    VR --> DEC["Risk-owner decision / monitor"]
~~~

### 15.1. Metadata bằng chứng

| Field | Mục đích |
|---|---|
| `evidence_id` | ID ổn định, link từ risk, finding và action. |
| `source_system/resource_id` | Nguồn chính xác: cloud API, scanner, IdP, SIEM, vendor. |
| `occurred_at/collected_at_utc` | Thời gian trạng thái xảy ra và thời điểm thu chứng cứ. |
| `collector_id/tool_version` | Người hoặc công cụ, quyền thu và cách thực hiện. |
| `scope/population` | Những tài sản/đường/API/regions đã kiểm. |
| `method/expected/actual` | Cách test, tiêu chí dự kiến và kết quả thực. |
| `data_quality` | Pagination, API errors, missing scopes, duplicate và confidence. |
| `artifact_location/digest` | Link kho và kiểm soát integrity/version. |
| `reviewer/verdict/limitations` | Người đánh giá và điều chưa được chứng minh. |
| `classification/retention` | Kiểm soát dữ liệu nhạy cảm và lưu theo chính sách. |

**Hash hoặc chữ ký số** có thể giúp truy vết integrity/authenticity theo nguồn tin cậy nhưng **không chứng minh dữ liệu đã đầy đủ hoặc phép thử đúng phạm vi**. Ví dụ file scan thiếu A-09 vẫn có SHA-256 hợp lệ.

### 15.2. Bài tập nối evidence

- E-01 → RISK-001 → CTRL-AUTH-01 → retest route/tenant authorization.
- E-02 → RISK-002 → CTRL-DATA-02 → anonymous deny + authorized allow.
- E-03/E-10 → RISK-003 → CTRL-IAM-03 → permission + change authorization.
- E-05 → RISK-005 → CTRL-LOG-05 → synthetic event end-to-end.
- E-06/E-11 → RISK-006 → CTRL-DR-06 → restore test + owner authorization.
- E-07/E-09 → RISK-007 → CTRL-VEND-07 → evidence completeness + obligation review.
- E-08 → RISK-008 → CTRL-VULN-08 → component reachability and version verification.

Không chuyển một `evidence_ref` thành `PASS` nếu không có verdict và test criteria tương ứng.

## 16. Bước 9 — Mẫu Risk Register dạng CSV

CSV sau là ví dụ có thể copy vào công cụ bảng dữ liệu hoặc GRC để học. Nó **chỉ chứa trường cốt lõi**, nên cần liên kết với assessment/risk treatment/evidence records đầy đủ ở các mục khác. Nhãn `target_score` là **dự kiến**, không phải kết quả verified.

~~~csv
risk_id,asset_ids,control_id,evidence_ids,scenario,current_l,current_i,current_score,current_tier,confidence,target_l,target_i,target_score,treatment,status
RISK-001,A-01,CTRL-AUTH-01,E-01,Cross-tenant invoice access,4,5,20,CRITICAL,MEDIUM,2,5,10,MITIGATE,OPEN
RISK-002,A-03,CTRL-DATA-02,E-02,Anonymous read of invoices,4,5,20,CRITICAL,MEDIUM,1,5,5,MITIGATE,OPEN
RISK-003,A-04+A-11,CTRL-IAM-03,E-03+E-10,Unapproved wildcard write,4,4,16,CRITICAL,HIGH,2,4,8,MITIGATE,OPEN
RISK-004,A-05,CTRL-CICD-04,E-04,Long-lived deployment token misuse,3,4,12,HIGH,MEDIUM,1,4,4,MITIGATE,OPEN
RISK-005,A-02+A-06,CTRL-LOG-05,E-05,Database audit ingest gap,3,4,12,HIGH,MEDIUM,1,4,4,MITIGATE,OPEN
RISK-006,A-07+A-08,CTRL-DR-06,E-06+E-11,Recovery failure after key rotation,3,5,15,HIGH,LOW,1,5,5,INVESTIGATE_AND_MITIGATE,NEEDS_EVIDENCE
RISK-007,A-09,CTRL-VEND-07,E-07+E-09,Vendor audit retention gap,3,3,9,MEDIUM,MEDIUM,1,3,3,ASSESS_OBLIGATIONS,OPEN
RISK-008,A-01,CTRL-VULN-08,E-08,Potential dependency exploitation,3,4,12,HIGH,LOW,1,4,4,INVESTIGATE_AND_PATCH,NEEDS_EVIDENCE
~~~

### 16.1. Kiểm tra phép tính

Các cột phải thoả `current_score = current_l * current_i` và `target_score = target_l * target_i`; tier map đúng quy tắc mục 5.4.

~~~text
assert 1 <= current_l <= 5
assert 1 <= current_i <= 5
assert current_score == current_l * current_i
assert current_tier == classify(current_score)
assert risk_id is unique
assert evidence_ids refer to known evidence cards
assert all in-scope assets have stable asset_ids
assert a target risk is never reported as verified without retest
~~~

Đây là **logic kiểm tra**, không phải script phải chạy. Trong thực tế, dùng validation trong spreadsheet, GRC hoặc code tùy lựa chọn. **Không coi cột confidence là kết quả toán học**: nó mô tả độ chắc chắn của các assumptions/evidence.

### 16.2. Nếu dùng bảng tính

Bạn có thể tính `current_score` bằng công thức nhân cột likelihood và impact; bảo vệ cột công thức, dùng data validation cho giá trị 1–5 và statuses, không sửa số bằng tay để khớp dashboard. Thêm bảng tra risk tiers theo version và snapshot lịch sử thay vì đổi ngưỡng mà không ghi nhận.

## 17. Bước 10 — Mẫu Risk Record đầy đủ bằng YAML

YAML này là **dữ liệu mô phỏng cho một rủi ro**, không phải schema chuẩn của NIST, ISO hay một công cụ GRC. Dùng để học cách tổ chức hồ sơ, không chứa secret thật.

~~~yaml
risk_record:
  risk_id: "RISK-001"
  record_version: "1.0"
  title: "Cross-tenant access to invoice resources"
  service_name: "SECURITY_SECURITY_ASSURANCE"
  project: "Minh Hai SaaS - Hands-on Lab"
  created_at_utc: "2026-11-28T04:00:00Z"
  assessment_as_of_utc: "2026-11-28T05:00:00Z"
  status: "OPEN_CRITICAL"

scope:
  business_process: "Order and invoice management"
  environment: "production"
  assets: ["A-01", "A-03"]
  data_classification: "CUSTOMER_CONFIDENTIAL"
  affected_population: "Two confirmed endpoint paths"
  population_limitations:
    - "Four other sampled endpoints have no confirmed cross-tenant failure"
    - "Complete API inventory has not been independently reconciled"

risk_scenario:
  threat_actor: "Authenticated user from another tenant"
  threat_event: "Access invoice belonging to a different tenant"
  vulnerability: "Tenant ownership check missing on selected API paths"
  business_impact:
    confidentiality: "HIGH"
    integrity: "NOT_CONFIRMED_IN_THIS_SCENARIO"
    availability: "NOT_CENTRAL_TO_THIS_SCENARIO"
  statement: >
    An authenticated user may request invoice resources belonging to
    another tenant through affected API endpoints because ownership
    enforcement is incomplete, potentially exposing customer data.
  current_exposure: "Confirmed on two tested paths"
  evidence_of_exploitation: "NOT_PROVIDED"

requirement_and_controls:
  objective: "Tenant data isolation"
  control_id: "CTRL-AUTH-01"
  requirement_version: "INTERNAL-LAB-2026-v1"
  current_controls:
    - id: "CTRL-AUTH-01"
      outcome: "FAIL_ON_TESTED_PATHS"
      evidence_ids: ["E-01"]
    - id: "CTRL-GW-DEFENSE"
      outcome: "INCONCLUSIVE"
      limitations: "Gateway rules are not a substitute for tenant authorization"

evidence:
  original_finding_id: "FIND-AUTH-LAB-001"
  source_event_ids: ["E-01"]
  test_method: "Authorized and unauthorized tenant resource requests"
  test_scope: "Six sampled endpoints; failure confirmed on two"
  raw_artifact_reference: "restricted/lab/risk-001/test-output"
  collected_at_utc: "2026-11-28T03:00:00Z"
  completeness: "PARTIAL_API_COVERAGE"
  reviewer: "Security Assurance Reviewer"
  raw_evidence_contains_customer_data: false

assessment:
  methodology_version: "RISK-METHOD-LAB-1.0"
  inherent:
    likelihood: 4
    impact: 5
    score: 20
    tier: "CRITICAL"
  current:
    likelihood: 4
    impact: 5
    score: 20
    tier: "CRITICAL"
    confidence: "MEDIUM_FOR_FULL_API_SCOPE"
  rationale: >
    Access to other tenants' records is demonstrated on tested paths,
    but API inventory completeness and historical exploitation remain unknown.
  projected_target_after_treatment:
    likelihood: 2
    impact: 5
    score: 10
    tier: "HIGH"
    status: "NOT_VERIFIED"
  verified_residual:
    status: "NOT_ASSESSED"
    score: null
  reassess_on:
    - "new-api-endpoint"
    - "authorization-code-change"
    - "confirmed-abuse"
    - "mitigation-failure"

ownership:
  risk_owner: "Customer Data Business Risk Owner"
  service_owner: "Order Service Owner"
  control_owner: "Application Security Owner"
  treatment_owner: "API Engineering Lead"
  independent_verifier: "Security Assurance Reviewer"

treatment:
  strategy: "MITIGATE"
  immediate_action:
    description: "Limit or disable vulnerable read paths using approved change controls"
    verification: "Unauthorized requests denied with valid business traffic working"
  permanent_actions:
    - id: "ACT-001"
      description: "Enforce tenant ownership server-side for every invoice endpoint"
      acceptance: "Positive and negative tests pass across reconciled API scope"
      status: "PLANNED"
    - id: "ACT-002"
      description: "Add automated cross-tenant regression tests in release pipeline"
      acceptance: "Unauthorized test case fails gate on intentionally unsafe sample"
      status: "PLANNED"
    - id: "ACT-003"
      description: "Assess exposure history and data impact using available logs"
      acceptance: "Incident/privacy/legal assessment documented where required"
      status: "PLANNED"
  dependencies:
    - "Endpoint inventory and release approval"
    - "Business-critical invoice workflow test"
  due_dates_source: "APPROVED_RISK_TREATMENT_POLICY"
  rollback_or_contingency: "Disable affected feature or use approved safe fallback"

verification:
  required_evidence:
    - "Production deployment version and change record"
    - "Effective authorization behavior test"
    - "Full endpoint population reconciliation"
    - "Authorized business-flow regression results"
  verdict: "RETEST_PENDING"
  reviewer_signoff_required: true
  next_review: "AFTER_REMEDIATION_OR_MATERIAL_CHANGE"

governance:
  risk_acceptance:
    state: "NOT_REQUESTED"
    approved_by: null
    valid_until: null
  external_obligations: "ASSESS_SEPARATELY_IF_APPLICABLE"
  original_assessment_preserved: true
  evidence_store: "restricted-learning-assurance"
~~~

### 17.1. Đọc đúng ý nghĩa bản ghi

- `control outcome: FAIL_ON_TESTED_PATHS` đã có evidence E-01; không cần tự “xóa” vì nhóm sắp sửa.
- `completeness: PARTIAL_API_COVERAGE` ngăn kết luận tất cả endpoints đều sai hoặc đều an toàn.
- `evidence_of_exploitation: NOT_PROVIDED` không xác nhận đã có breach; có thể cần điều tra dựa trên tác động và nghĩa vụ.
- `projected_target_after_treatment: NOT_VERIFIED` là **ước lượng**, không được dùng làm verified residual.
- `due_dates_source` tham chiếu policy, không bịa SLA ngành.
- `risk_acceptance: NOT_REQUESTED` cho thấy **không có quyết định được phép giữ rủi ro** chỉ từ việc tạo hồ sơ.

### 17.2. Trạng thái chính xác quan trọng hơn đẹp

Một record có nhiều `INCONCLUSIVE` hoặc `NOT_ASSESSED` chưa phải sai. Nó sai khi báo cáo cuối **quên các trường này** và chỉ hiện “RISK-001 target High” như thể đã sửa. Risk register cần thể hiện trạng thái **vẫn cần hành động**.

## 18. Bước 11 — Tạo Risk Treatment Decision Log

Đối với mỗi risk, thêm quyết định có version và người có quyền. Ví dụ:

| Trường | Giá trị mô phỏng |
|---|---|
| Decision ID | DEC-RISK-006-v1 |
| Risk ID | RISK-006 |
| Current assessment | 15 High, confidence Low, thiếu restore test |
| Proposed decision | Không xóa key cũ; ưu tiên restore/decrypt rehearsal |
| Authority | Data/Business Risk Owner có thẩm quyền về recoverability |
| Security reviewer | Security Assurance Reviewer |
| Evidence basis | E-06, E-11, backup metadata và thiếu rehearsal |
| Conditions | Không thay key lifecycle bất khả đảo trước khi có recovery evidence |
| Deadline source | BIA/DR và risk treatment policy của tổ chức |
| Next gate | Restore test PASS, integrity đối soát và recovery decision |
| Residual risk | Chưa verified, phải reassess sau test |
| Audit fields | Timestamp, actor, role, version và lý do |

**Không tự động gán “risk accepted”** chỉ vì một cá nhân đã ký nhờ nghỉ bảo trì. Nếu chấp nhận, phải có risk-owner approval đúng quyền, scope/time/conditions rõ; những nghĩa vụ pháp lý/hợp đồng liên quan recoverability phải kiểm tra riêng.

### 18.1. Những kết quả quyết định cần phân biệt

- **APPROVED_TREATMENT:** đồng ý kế hoạch; không có nghĩa action đã triển khai.
- **ACCEPTED_WITH_CONDITIONS:** người có quyền chấp nhận residual risk hiện hữu theo phạm vi/hạn và nghĩa vụ.
- **REJECTED:** treatment hoặc acceptance không được phép; phải tìm phương án khác.
- **NEEDS_EVIDENCE:** thiếu dữ liệu để quyết định hoặc cần test.
- **ESCALATED:** vượt thẩm quyền, deadline hoặc rủi ro cao cần cấp cao hơn.
- **VERIFIED_CLOSED:** action đạt acceptance và reviewer ký theo tiêu chí; risk record có thể tiếp tục được monitoring dù finding đóng.

Một bảng risk không có decision status khiến quản lý không biết **điểm cao đã được xử lý, đã chấp nhận hay chỉ đang nằm trên giấy**.

## 19. Bước 12 — Ưu tiên backlog theo nhiều chiều

Sắp risk chỉ bằng score có thể dẫn đến quyết định kém: một điểm 12 trên production customer data có thể cần hành động trước một điểm 15 trên môi trường cô lập theo risk context.

### 19.1. Nguyên tắc ưu tiên

1. **Active incident/exploitation:** xử lý theo incident response khi có bằng chứng hoặc nghi vấn hợp lý; không chờ điểm.
2. **Control failure critical:** unauthorized cross-tenant, public data exposure, IAM privilege escalation đã xác nhận.
3. **High-impact uncertainty:** DR recovery chưa được chứng minh trong thời điểm sắp rotation, source telemetry không đủ.
4. **External deadlines:** nghĩa vụ pháp luật/hợp đồng hoặc customer commitment đã được xác minh.
5. **Attack path & exposure:** public, reachable, lateral movement, trust boundary.
6. **Dependencies:** một action sửa root cause có thể giải quyết nhiều risk records.
7. **Mitigation effectiveness:** có thể giảm phơi nhiễm an toàn ngay không, bằng chứng gì?
8. **Cost/resource/time:** cân nhắc nhưng không được đổi nghĩa vụ bắt buộc thành “không cần làm”.
9. **Confidence:** risk có thông tin thiếu cần assessment nhanh thay vì tự gán Low.

### 19.2. Một thứ tự tham khảo

Trong lab, có thể đưa RISK-001 và RISK-002 vào làn xử lý khẩn về exposure, RISK-003 vào làn ưu tiên đặc quyền, đồng thời xử lý RISK-006 **trước KMS rotation** như điều kiện phụ thuộc. RISK-005 cần khôi phục logging để các kết luận sau đáng tin. RISK-008 cần nhanh chóng xác định exploitability trước khi đưa quyết định patch/mitigation. Thứ tự thực tế phụ thuộc threat context và authority, không phải luôn 001→008.

### 19.3. Risk score không phải một số cộng được

Không cộng 20+20+16+... rồi xem tổng số là “mức độ bảo mật của công ty”, cũng không báo “giảm từ 116 xuống 43 = giảm 63% nguy cơ tấn công”. Phép nhân 1–5 là **ordinal planning aid**; muốn định lượng mức giảm xác suất hoặc tổn thất cần phương pháp và dữ liệu thích hợp riêng.

## 20. Bước 13 — Review cadence, triggers và liên tục cập nhật

Risk register **không phải bảng làm một lần để nộp audit**. Cần phiên bản, người chịu trách nhiệm và những sự kiện làm thông tin cũ hết hiệu lực.

| Trigger | Risk records có thể ảnh hưởng | Review cần làm |
|---|---|---|
| Phát hành API mới hoặc đổi tenant authorization | RISK-001, RISK-008 | Endpoint inventory, DAST/negative tests và artifact versions. |
| Cấu hình bucket, dữ liệu hoặc region mới | RISK-002 | Effective storage policy, data classification và public access check. |
| IAM role/role trust/service account thay đổi | RISK-003, RISK-004 | Approval scope, effective roles, least privilege và session/token review. |
| CI token rotation, registry/build incident | RISK-004, RISK-008 | Token validity, provenance, dependency risk. |
| SIEM pipeline mất heartbeat hoặc parser/schema đổi | RISK-005 | Synthetic event, source coverage, logging evidence quality. |
| KMS key rotation, backup schema hoặc restore failure | RISK-006 | Decrypt dependencies, backup integrity, RTO/RPO impact. |
| Vendor thay subprocessor, log retention, contract | RISK-007 | Data flow/contract applicability, vendor controls và evidence. |
| CVE mới, exploit telemetry hoặc SBOM đổi | RISK-008 | Affected versions, reachability, remediation priority. |
| Exception hết hạn, mitigation FAIL, overdue action | Risk tương ứng | Risk reassessment, escalation, new decision. |

### 20.1. Versioning và lịch sử

Ghi `risk_version`, `assessed_at_utc`, `previous_score`, `new_score`, `reason_for_change`, `evidence_ids`, `assessor`, `approver`. Một bản sửa config thành công hôm nay không xóa việc risk đã tồn tại ở kỳ trước. Giữ **effective dates** để audit có thể phân biệt quá khứ và hiện tại.

### 20.2. Rà soát định kỳ bổ sung cho event-driven

Event-driven review phụ thuộc nguồn tín hiệu. Nếu collector không onboard một account thì **không có event chưa chắc không có thay đổi**. Vì vậy vẫn cần periodic inventory reconciliation, sampling và independent assurance review, nhất là cho population/telemetry coverage.

## 21. Bước 14 — Báo cáo rủi ro cho quản lý và các bên liên quan

Một risk register dễ bị biến thành một biểu đồ đẹp che giấu các khoảng trống. Báo cáo nên tách **risk severity, coverage, status, confidence, treatment và quyết định cần thực hiện**.

### 21.1. Executive summary mẫu

~~~text
Risk register scope: 8 scenarios / 12 lab assets
Current severity: 3 Critical, 4 High, 1 Medium
Verified remediation: 0 (lab actions are proposed, not deployed)
Known control failures: cross-tenant auth, public invoice access,
  wildcard service privileges, database audit forwarding
Evidence uncertainty: backup restore, dependency reachability,
  vendor log/tenant coverage
Ownership gap: RISK-006 risk owner not yet assigned
Projected target risk: illustration only — NOT VERIFIED
Decisions needed:
  - authorize safe containment for confirmed high-exposure findings
  - assign risk owner for recoverability and set key-rotation gate
  - approve treatment resources and verification schedule
Next review triggers: deployment, IAM changes, logging/backup failure,
  vendor changes, newly confirmed exploit paths
~~~

### 21.2. Current vs projected summary

Theo bảng mẫu:

| Tier | Current (8 risks) | Projected target sau treatment **chưa verified** |
|---|---:|---:|
| Critical | 3 | 0 |
| High | 4 | 1 |
| Medium | 1 | 3 |
| Low | 0 | 4 |

Cột target **không chứng minh tổ chức đã giảm rủi ro**. Một báo cáo nói “Critical giảm từ 3 xuống 0” khi chưa có triển khai/verification là sai lệch. Nên ghi “Projected after planned treatment; subject to testing and risk owner review”.

### 21.3. Đừng che uncertainty trong một thẻ màu xanh

Nếu 12 assets là target population nhưng một nguồn chỉ có data cho 11, phải ghi rõ **coverage của nguồn đó = 11/12**, không chuyển thành “11 assets secure”. Một risk record có confidence thấp không tự có điểm nhỏ; phải có owner thu thêm evidence và thời điểm rà soát.

### 21.4. Báo cáo theo đối tượng

- **Engineering:** actions, technical dependencies, owner, tests, rollback.
- **Security assurance:** control verdict, evidence completeness, scope và reviewer.
- **Risk owner/business:** severity, impact, residual risk, acceptance decision và nguồn lực cần.
- **Legal/compliance:** obligations, nonconformity, exceptions và evidence cho đối tượng áp dụng.
- **Audit:** version history, source/evidence chain, scoring rationale và closure tests.

## 22. Kiểm tra chất lượng Risk Register trước khi nộp

Hãy chủ động tìm các lỗi thường làm risk register trông có vẻ hoàn chỉnh nhưng không đáng tin.

| Kiểm tra | Lỗi cần bắt | Kết quả mong đợi |
|---|---|---|
| **Unique IDs** | Hai kịch bản có cùng risk ID; asset ID tham chiếu không tồn tại. | IDs chuẩn, quan hệ được xác minh. |
| **Scope reconciliation** | Asset A-09 bị bỏ vì vendor không cung cấp evidence. | A-09 vẫn trong inventory, limitation được ghi. |
| **Scenario clarity** | Risk ghi “vulnerability high” không có threat path. | Actor/event/asset/impact cụ thể. |
| **Score consistency** | L4×I5 nhưng score ghi 15; tier sai. | Score và tier đúng matrix đã version. |
| **Evidence semantics** | E-06 bị diễn giải thành “restore đã thất bại”. | INCONCLUSIVE về restore capability, assessment risk có assumption. |
| **Exploitability uncertainty** | E-08 bị ghi “remote exploit confirmed”. | Chỉ ghi potential và nhiệm vụ triage. |
| **Target vs verified residual** | L1×I5 được báo current dù fix chưa triển khai. | Target riêng, verified residual pending. |
| **Owner & authority** | RISK-006 không risk owner nhưng hiện APPROVED. | Ownership gap/escalation, không tự duyệt. |
| **Acceptance/exception** | Risk accepted được map sang control PASS. | Risk decision và original control result tách biệt. |
| **Time/version** | Risk review cũ trước key rotation vẫn báo current. | Invalidation triggers và assessed_at rõ. |
| **Remediation evidence** | PR merged nhưng finding đóng. | Retest trên runtime đúng scope, reviewer sign-off. |
| **Dependencies** | Rotate/delete KMS key trước restore rehearsal. | Key lifecycle change có recovery gate. |
| **Governance/reporting** | Chỉ công bố “projected 0 critical”. | Current, projected chưa verified, unknown và blockers. |
| **External applicability** | Ghi vendor 30 ngày là “vi phạm luật” khi chưa kiểm. | Chỉ xác nhận lệch baseline lab; legal assessment riêng. |

### 22.1. Negative test: Thử làm hỏng dữ liệu

Để xác minh bảng có guardrails, thử trong bản dữ liệu lab riêng:

1. Xóa E-02 khỏi RISK-002 nhưng giữ `confidence=HIGH`.
2. Đặt current score RISK-003 thành 12 dù L4×I4.
3. Đổi projected residual RISK-006 thành verified Low khi chưa restore.
4. Ghi RISK-007 là `EXCEPTION_APPROVED` dù approval ID trống.
5. Xóa A-09 khỏi population để coverage thành 100%.
6. Gán cùng một risk ID cho hai scenarios khác nhau.
7. Xóa risk owner của một critical risk và thử publish dashboard.
8. Thay `assessed_at` mà không giữ lịch sử risk version.

**Kỳ vọng:** validation/reviewer phát hiện và từ chối bản ghi hoặc đánh dấu **NEEDS_REVIEW/INCONCLUSIVE**, không tự làm sạch thông tin sai để giữ tỷ lệ hoàn thành.

## 23. Tình huống bổ sung: Risk Register trước khi mở region mới

Nhóm sản phẩm muốn mở thêm **region B** với một tenant khách hàng lớn. Họ đề xuất clone production stack đã có vào region B, chuyển dữ liệu hóa đơn và sử dụng chung IdP/KMS policy. Báo cáo hiện tại cho biết “3 Critical, 4 High, 1 Medium” nhưng risk owner muốn ký release ngay vì “các rủi ro đã có plan”.

Thông tin mới:

- A-03 sẽ có bucket mới tại region B; IaC guardrail chưa chứng minh đã chạy cho region này.
- A-06 SIEM collector chưa onboard region B.
- A-08 KMS policy cho backup region B khác region A.
- Vendor A-09 có thể xử lý dữ liệu thông báo ở nơi mới theo hợp đồng chưa đánh giá.
- A-01 dùng một release artifact mới; cross-tenant negative tests chỉ chạy trên artifact cũ.
- A-10 có federation policy riêng cho support administrators tại region B.
- Business Owner nêu target residual của RISK-001 là High và muốn coi như đã đạt dù chưa triển khai fix.

### 23.1. Nhiệm vụ

Hãy xây một **risk register delta** cho việc mở region B, tối thiểu:

1. Xác định tài sản, data flows và trust boundaries mới.
2. Gắn những risk IDs cũ bị thay đổi scope/assumptions.
3. Tạo **ít nhất hai risk scenarios mới** nếu outcome khác biệt đáng kể.
4. Ghi evidence còn thiếu và owner phải cung cấp.
5. Đánh giá liệu release/change approval cũ còn hợp lệ không.
6. Đề xuất pre-release GO/NO-GO gates có quan hệ với các risks.
7. Giữ current/target/verified residual tách biệt.
8. Ghi những quyết định cần business risk owner, security, legal/privacy/contract owner.
9. Xác định post-release monitoring và review triggers.
10. Viết executive note dưới 200 từ nói rõ liệu đủ căn cứ GO hay chưa.

### 23.2. Gợi ý đáp án

**Không đủ căn cứ GO với dữ liệu hiện tại** nếu các gate nêu là bắt buộc: cross-tenant tests trên artifact/region mới thiếu, logging region B chưa được chứng minh, recoverability/key policy chưa test, privacy/vendor data-flow chưa review và risk owners chưa chấp thuận đúng tình trạng. Có thể lựa chọn giảm scope, dùng môi trường không có dữ liệu khách hàng hoặc hoàn tất gate bổ sung trước release theo đúng chính sách; không coi “đã có action plan” đồng nghĩa xử lý.

Ví dụ risk delta:

- **RISK-001-v2:** thêm affected region B; phải retest tenant isolation trên artifact mới.
- **RISK-002-v2:** public invoice bucket risk cần đối chiếu guardrail region B.
- **RISK-005-v2:** logging gap mở rộng vì SIEM chưa có connector region B.
- **RISK-006-v2:** recoverability risk tăng uncertainty do KMS policy/backup mới.
- **RISK-009 (mới):** data residency/processing mismatch với vendor khi chuyển region; cần contract/privacy review, không tự kết luận vi phạm.
- **RISK-010 (mới):** support federation path có thể bypass privileged access policy mới; cần effective access và negative tests.

Hai rủi ro mới chỉ là **hypotheses** cho tới khi evidence và applicability được xác minh. Không tự sao chép risk score từ region A sang region B vì exposure và responsibilities có thể khác.

## 24. Bài tập phản biện chéo theo vai trò

Chia nhóm bốn vai trò: **Service Owner**, **Security Assurance Reviewer**, **Business Risk Owner**, **Internal Auditor**. Mỗi người phải đặt ít nhất hai câu hỏi có thể buộc sửa register.

### 24.1. Service Owner

- Những actions nào có thể làm ngưng luồng xuất hóa đơn hoặc backup?
- Có phụ thuộc kỹ thuật nào chưa thể rollback an toàn?
- Kế hoạch đã thử business-critical flows sau khi giảm IAM permissions chưa?

### 24.2. Security Assurance Reviewer

- Evidence nào xác minh control gốc FAIL, evidence nào chỉ cho thấy nghi vấn?
- Các scores có giải thích threat path và confidence hay chỉ là cảm nhận?
- Có đường bypass chưa thử hoặc population coverage gap không?

### 24.3. Business Risk Owner

- Kịch bản nào thực sự chạm tới dữ liệu/dịch vụ trọng yếu và nghĩa vụ bên ngoài?
- Ai có quyền accept residual risk và điều kiện/expiry là gì?
- Nếu treatment thất bại hoặc deadline trễ, lựa chọn avoid/limit service nào khả thi?

### 24.4. Internal Auditor

- Có thể tái dựng score và quyết định của phiên bản cũ tại mốc ngày 28/11 không?
- Có thể lần từ một risk đến evidence gốc, test run và reviewer sign-off không?
- “Risk closed” có phải đã verified control effectiveness hay chỉ task hoàn thành?

Reviewer ghi kết luận thành **review notes** gắn risk IDs. Không yêu cầu mọi người đồng ý điểm số; quan trọng là **bất đồng có luận cứ, evidence và người có quyền quyết định**.

## 25. Rubric chấm điểm dự án (100 điểm)

| Tiêu chí | Điểm tối đa | Kết quả xuất sắc |
|---|---:|---|
| **Scope & inventory** | 10 | Asset IDs, data criticality, boundaries, ownership và coverage/unknown rõ. |
| **Risk scenario quality** | 15 | Tối thiểu 8 kịch bản không trùng, threat path và impact xác định. |
| **Method & scores** | 15 | Likelihood/impact rationale nhất quán, tiers đúng, confidence tách riêng. |
| **Control & evidence linkage** | 15 | Risk → control → source/test → verdict/limitation truy vết được. |
| **Risk treatment design** | 15 | Containment/permanent fix, dependencies, actionable acceptance và test. |
| **Governance & ownership** | 10 | Risk owner, action owner, authority, exception/acceptance rõ. |
| **Residual risk semantics** | 5 | Current vs projected vs verified không bị trộn. |
| **Executive reporting** | 5 | Summary có current, unknown, risk decisions và không làm đẹp. |
| **Validation & negative tests** | 5 | Phát hiện được missing scope, score sai, stale/false evidence. |
| **Presentation & audit trail** | 5 | Tài liệu dễ review, có version/time, giới hạn bảo mật và history. |
| **Tổng** | **100** | Đủ giá trị để peer review và dùng làm nền cho assurance planning. |

### 25.1. Các lỗi nghiêm trọng cần đánh dấu bắt buộc sửa

Dù tổng điểm cao, reviewer cần yêu cầu chỉnh nếu xảy ra:

- Dùng target residual score chưa được verified để tuyên bố hiện trạng đã an toàn.
- Biến scanner không có quyền/thiếu data thành PASS.
- Tự gọi việc risk owner chấp nhận rủi ro là control original PASS.
- Đánh dấu finding `VERIFIED_CLOSED` khi chưa có retest đúng scope.
- Bỏ critical asset khỏi mẫu số do công cụ không theo dõi được.
- Thay quyền phê duyệt hoặc nghĩa vụ bên ngoài bằng chữ ký không đúng thẩm quyền.
- Chèn credentials hoặc dữ liệu khách hàng thật vào bản báo cáo thực hành.

## 26. Checklist nghiệm thu Risk Register cuối cùng

Trước khi nộp, tự kiểm tra:

1. **Scope** đã xác định business process, boundaries, dữ liệu và kỳ đánh giá?
2. **Asset inventory** có stable IDs, owners, classification và đối chiếu nguồn?
3. **Completeness** có liệt kê unassessed/unknown assets và evidence gaps?
4. **Risk statement** có actor/threat event, vulnerability/control gap, asset, hậu quả?
5. **Controls** có control ID, requirement version và mục tiêu cụ thể?
6. **Evidence** có source, time, scope, method, collected/expected/actual và limitations?
7. **Current state** có được đánh giá từ controls đang hiệu lực, không phải planned controls?
8. **Inherent vs current** có định nghĩa nhất quán theo phương pháp?
9. **Likelihood** có căn cứ attack path/exposure và không bị nhầm với confirmed breach?
10. **Impact** có căn cứ CIA, data, BIA và obligations phù hợp?
11. **Scoring** đúng matrix, không trộn ordinal score với xác suất tổn thất?
12. **Confidence** có phản ánh uncertain reachability, restore hoặc vendor coverage?
13. **Target risk** có được đánh dấu dự kiến, chưa verified trước khi retest?
14. **Treatment** có chiến lược và phương án thay thế khi không thể sửa ngay?
15. **Immediate mitigation** có thể kiểm tra hiệu lực và giám sát trong khi chờ fix?
16. **Ownership** có risk owner, action owner, control owner, verifier và cấp duyệt?
17. **Milestones** có deadline source, dependencies, escalation và replan history?
18. **Risk acceptance** có đúng thẩm quyền, expiry, residual risk và giới hạn?
19. **External obligations** có xem riêng khi control thuộc luật/hợp đồng?
20. **Verification** có positive/negative tests, đúng environment và population?
21. **Change/release integration** có rollback và artifact/version evidence?
22. **Closure** phân biệt action completed, control PASS, risk accepted và false positive?
23. **Review cadence** có periodic + event triggers và trigger owner?
24. **Data protection** không đưa secrets/PII vào register rộng quyền?
25. **Executive summary** có current tiers, blockers, unknown và action decision rõ?
26. **Audit trail** có history, phương pháp/version, reviewer và khả năng tái lập?

### Câu hỏi tự đánh giá cuối dự án

Một thành viên báo: “Chúng ta có 8 risks, đã lên plan cho tất cả và projected target chỉ còn 1 High, 3 Medium, 4 Low. Vậy tổng thể có thể công bố đã giảm rủi ro xuống mức chấp nhận.”

**Câu trả lời cần có:** **Chưa.** Tám risk scenarios đã có **kế hoạch** không chứng minh remediation đã triển khai, controls đã hiệu lực hoặc residual risk đã được **đánh giá và chấp nhận** bởi người có quyền. Bản target chỉ là ước lượng theo giả định; có thể sai nếu test thất bại, asset scope thay đổi hoặc có attack paths chưa biết. Cần theo dõi containment, triển khai có kiểm soát, retest, cập nhật **verified residual**, xác minh obligations và phê duyệt risk treatment/acceptance theo thẩm quyền. Báo cáo phải trình bày **3 Critical / 4 High / 1 Medium hiện tại** theo bộ dữ liệu lab, kèm confidence và những gap chưa giải quyết.

**Một risk register tốt không làm rủi ro biến mất trên giấy. Nó tạo ra một bản đồ có thể kiểm tra về điều có thể xảy ra, điều đã biết và chưa biết, các controls đang hiệu lực, người có trách nhiệm quyết định, những hành động cụ thể sẽ giảm phơi nhiễm và bằng chứng cần có để chứng minh thay đổi thực sự. Khi được cập nhật theo sự kiện và được phản biện độc lập, risk register trở thành nền tảng thực hành của continuous security assurance thay vì một bảng màu đỏ/vàng/xanh chỉ để hoàn tất kiểm toán.**
