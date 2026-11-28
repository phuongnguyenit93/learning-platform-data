# Action plan trong Remediation: Từ phát hiện bảo mật đến khắc phục có bằng chứng

Một cuộc kiểm toán phát hiện nhóm quản trị cloud có quyền truy cập quá rộng. Nhóm kỹ thuật mở ticket “giảm quyền IAM” và đặt trạng thái *In progress*. Ba tuần sau, ticket được đóng với ghi chú “đã điều chỉnh cấu hình”. Tuy nhiên, vẫn còn một service account giữ quyền cũ, ứng dụng phụ thuộc vào quyền đó chưa được kiểm thử và không ai xác nhận rằng rủi ro ban đầu đã giảm. **Có ticket và có thay đổi không đồng nghĩa remediation đã hoàn tất**.

**Action plan** (kế hoạch hành động khắc phục) là bản kế hoạch có cấu trúc chuyển một **finding, control gap hoặc rủi ro đã xác định** thành những hành động có người sở hữu, thứ tự thực hiện, nguồn lực, thời hạn, điều kiện an toàn, tiêu chí nghiệm thu và bằng chứng kiểm chứng. Một action plan tốt cho biết **phải thay đổi điều gì, tại sao, ai chịu trách nhiệm, khi nào, phụ thuộc vào đâu, chứng minh thành công bằng cách nào và làm gì nếu kế hoạch không đạt**.

Trong chương **Remediation** của module **SECURITY_SECURITY_ASSURANCE**, action plan là cầu nối giữa đánh giá rủi ro, security controls, kiểm thử, audit và việc xử lý phát hiện. Mục tiêu của chương trình assurance không phải chỉ tăng tỷ lệ ticket đóng mà là **chứng minh được rằng các thiếu sót ảnh hưởng mục tiêu bảo mật đã được xử lý hoặc được quản trị rủi ro một cách minh bạch** trong suốt quá trình phát triển và vận hành.

Sau bài học, người học có thể lập kế hoạch hành động khắc phục theo mức rủi ro, phân tích nguyên nhân gốc, phân nhỏ công việc và xác định trách nhiệm, xây dựng tiêu chí hoàn thành có thể kiểm tra, quản lý dependencies và control bù trừ, thu thập bằng chứng retest, báo cáo tiến độ và đóng finding có căn cứ.

## 1. Vai trò của Action plan trong vòng đời Remediation

Một vấn đề bảo mật có thể được phát hiện từ kiểm thử xâm nhập, đánh giá cấu hình, threat modeling, vulnerability scanning, incident response, audit, rà soát tuân thủ, đánh giá nhà cung cấp hoặc phản ánh từ người dùng. Các nguồn này có cách biểu đạt khác nhau, nhưng đều cần biến **quan sát ban đầu** thành **quyết định xử lý được theo dõi**.

~~~mermaid
flowchart TD
    A["Nguồn phát hiện: audit / scan / incident / review"] --> B["Xác minh finding và phạm vi ảnh hưởng"]
    B --> C["Đánh giá rủi ro, nghĩa vụ và mức ưu tiên"]
    C --> D["Phân tích nguyên nhân gốc"]
    D --> E["Thiết kế action plan + trách nhiệm + mốc"]
    E --> F["Mitigation tạm và thay đổi có kiểm soát"]
    F --> G["Triển khai hành động và ghi bằng chứng"]
    G --> H["Retest độc lập theo tiêu chí"]
    H --> I{"Đã xử lý được nguyên nhân và rủi ro?"}
    I -->|Chưa| J["Mở lại finding / điều chỉnh kế hoạch"]
    J --> E
    I -->|Đạt| K["Owner nghiệm thu, lưu evidence, đóng"]
    K --> L["Giám sát tái diễn và cải tiến controls"]
~~~

### Phân biệt những hồ sơ liên quan

| Hồ sơ | Đóng vai trò gì? | Không nên nhầm với |
|---|---|---|
| **Finding / issue record** | Ghi nhận sự không phù hợp, điều kiện quan sát, bằng chứng, tác động và scope. | Hành động đã làm hoặc kế hoạch chi tiết. |
| **Risk assessment** | Đánh giá kịch bản đe dọa, mức tác động, khả năng, rủi ro trước và sau xử lý. | Câu trả lời “đã sửa hay chưa” nếu chưa kiểm chứng. |
| **Action plan** | Mô tả **các bước cụ thể** để giảm/loại bỏ vấn đề, owner, lịch, điều kiện kiểm tra. | Ticket chỉ chứa tên công việc và deadline. |
| **Corrective action** | Xử lý nguyên nhân của sự không phù hợp để ngăn tái diễn theo phạm vi. | Sửa triệu chứng tức thời mà không giải quyết root cause. |
| **Containment / mitigation** | Giảm phơi nhiễm trong lúc chưa sửa triệt để. | Bằng chứng control gốc đã hoạt động đúng. |
| **Compensating control** | Biện pháp thay thế giảm rủi ro cho mục tiêu đang chưa được đáp ứng. | Ngoại lệ được chấp thuận tự động hoặc phép thử PASS của control gốc. |
| **Exception / risk acceptance** | Quyết định quản trị đối với rủi ro còn lại trong quyền hạn và thời hạn cụ thể. | Chứng nhận tuân thủ nghĩa vụ pháp luật hoặc hợp đồng. |
| **Change record / deployment** | Ghi nhận thay đổi kỹ thuật, phê duyệt, triển khai, kết quả và rollback. | Retest độc lập rằng finding đã được xử lý trên mọi đối tượng. |
| **Retest / closure record** | Chứng minh tiêu chí sửa đã đạt, gắn approval và evidence. | Ghi chú “done” của người tự triển khai. |

Kế hoạch hành động có thể tham chiếu các hồ sơ này bằng ID ổn định; không cần nhồi mọi dữ liệu thô vào một ticket. Cần giữ khả năng **truy ngược** từ một quyết định đóng finding đến yêu cầu gốc và evidence của lần kiểm tra sau cùng.

## 2. Khi nào một finding đủ điều kiện để lập Action plan?

Đầu vào yếu sẽ dẫn đến kế hoạch khó thực thi. Trước khi giao việc, cần xác định finding thực sự tồn tại và có phạm vi rõ.

### 2.1. Các trường tối thiểu của finding đầu vào

| Thuộc tính | Câu hỏi xác minh | Ví dụ |
|---|---|---|
| **Finding ID và nguồn** | Ai phát hiện, khi nào, bằng phương pháp nào? | F-IAM-017 từ access review quý. |
| **Requirement/control ID** | Tiêu chí mong đợi nào không được đáp ứng? | IAM-PRIV-01: role đặc quyền theo least privilege. |
| **Quan sát thực tế** | Cấu hình/hành vi nào vi phạm, có bằng chứng truy xuất được? | Role wildcard action trên 4 principal. |
| **Asset và owner** | Account, cluster, service, vùng, dữ liệu và người chịu trách nhiệm nào? | Production cloud account A, service thanh toán. |
| **Mốc thời gian** | Finding là trạng thái tại thời điểm nào hay trong kỳ nào? | Snapshot ngày T và lịch sử cấp quyền tháng trước. |
| **Kịch bản rủi ro** | Nếu chưa xử lý thì có thể gây thiệt hại gì? | Credential bị lộ dẫn đến thao tác vượt chức năng. |
| **Impact và priority** | Độ nhạy dữ liệu, exposure, điều kiện khai thác và mức ưu tiên? | Rủi ro cao do tài khoản có quyền write production. |
| **Độ chắc chắn** | Dữ liệu đủ để kết luận FAIL hay chỉ INCONCLUSIVE? | Scanner báo nghi vấn, chưa có runtime test. |
| **Điểm cần xác minh thêm** | Asset ngoài scope, đường bypass hoặc bằng chứng thiếu? | Chưa đối chiếu service account vừa tạo. |

### 2.2. Không biến “thiếu bằng chứng” thành “đã xác nhận sai cấu hình”

Giả sử một scanner không có quyền đọc một region. Kết quả assessment có thể **INCONCLUSIVE** về cấu hình region đó. Kế hoạch hành động ban đầu cần sửa quyền collector và xác minh trạng thái, chứ không được tự khẳng định “logging bị tắt” khi chưa có dữ liệu.

Ngược lại, nếu có bằng chứng log không được gửi tới SIEM, đã có cơ sở mở remediation về pipeline. **Phân biệt vấn đề kỹ thuật và khoảng trống evidence** sẽ giúp chọn đúng hành động và không lãng phí nguồn lực.

### 2.3. Giữ source và version

Gắn link tới raw evidence, asset inventory, chính sách và kết quả kiểm thử có mốc thời gian. Nếu báo cáo scan được cập nhật hoặc finding bị đổi severity, cần giữ version và lý do. Tránh tham chiếu tới “latest.csv” vì nội dung có thể đã đổi trước khi auditor kiểm chứng.

## 3. Từ Finding đến Problem statement đo được

Kế hoạch thường thất bại khi phát biểu vấn đề mơ hồ: “cải thiện logging”, “tăng bảo mật cloud”, “rà soát quyền truy cập”. Mỗi action plan nên bắt đầu bằng một **problem statement** mô tả **điều kiện hiện tại, điều kiện mong đợi, khoảng lệch và ảnh hưởng**.

Ví dụ:

> “Trong 12 production accounts thuộc scope, 3 account chưa chuyển được control-plane audit events đến kho log tập trung. Điều này vi phạm control LOG-COV-01 và làm giảm khả năng điều tra thay đổi IAM. Trong 3 account, 1 account chưa có quyền connector và 2 account có rule route sai. Mục tiêu khắc phục là mọi account trong inventory gửi được synthetic event tới đích và pipeline cảnh báo khi đường truyền bị lỗi.”

### 3.1. Viết mục tiêu thành công theo SMART

Một mục tiêu hữu ích thường:

- **Specific:** nói rõ control, tài sản và chức năng cần đạt.
- **Measurable:** có phép thử, ngưỡng và bằng chứng rõ.
- **Achievable:** dựa vào năng lực kỹ thuật/nguồn lực, nhưng không hạ tiêu chí an toàn để cho dễ đạt.
- **Relevant:** liên kết rủi ro và security objective, không chỉ cosmetic change.
- **Time-bound:** có deadline và mốc kiểm tra, đáp ứng risk tolerance/nghĩa vụ áp dụng.

**Không nên viết:** “Khắc phục các vấn đề IAM sớm nhất có thể.”

**Nên viết:** “Trước mốc được risk owner phê duyệt, loại bỏ quyền ghi ngoài phạm vi công việc khỏi 4 principal thuộc finding F-IAM-017; xác minh lại effective permissions và quyền truy cập ứng dụng trên toàn bộ principal; kiểm thử rằng thao tác không được phép bị từ chối và luồng nghiệp vụ hợp lệ không gián đoạn; lưu test run, policy version và reviewer sign-off.”

### 3.2. Định nghĩa acceptance criteria độc lập với thao tác

“Hạ version thư viện”, “bật WAF rule”, “tạo PR” hay “merge cấu hình” chỉ là **hành động**. Acceptance criteria phải nói về **kết quả có thể quan sát**:

- Toàn bộ asset được áp dụng bản sửa.
- Đường tấn công/điều kiện sai đã được kiểm thử không còn hoặc rủi ro được giảm theo mục tiêu.
- Control bảo mật vẫn hoạt động và không tạo lỗi nghiệp vụ không chấp nhận được.
- Có nguồn evidence, thời gian, scope và reviewer.
- Không còn ngoại lệ chưa giải quyết ngoài quyết định được phê duyệt.

Không định nghĩa tiêu chí closure theo việc ticket chuyển trạng thái “Resolved”.

## 4. Phân tích nguyên nhân gốc (Root Cause Analysis)

**Root Cause Analysis (RCA)** giúp chuyển từ sửa hiện tượng sang ngăn lỗi tái diễn. Một finding có thể có nhiều nguyên nhân thuộc code, kiến trúc, quy trình, con người, permission hoặc công cụ.

### 4.1. Kỹ thuật 5 Whys có kiểm chứng

Ví dụ: “Một object storage bucket production bị truy cập công khai trái chính sách.”

| Câu hỏi | Trả lời sơ bộ | Bằng chứng cần xác minh |
|---|---|---|
| Vì sao bucket public? | Policy cho phép principal ẩn danh truy cập một số object. | Effective bucket policy, access-control configuration. |
| Vì sao policy được áp dụng? | Pipeline triển khai sử dụng template cũ. | IaC commit, deployment history, template version. |
| Vì sao template cũ còn sử dụng? | Repo không bắt buộc kiểm tra policy theo tổ chức. | CI/CD configuration, PR history, policy test. |
| Vì sao kiểm soát phát hiện không chặn? | Rule posture quét bucket hằng tuần; alert không tới owner. | Scanner schedule, alert route, ticket timeline. |
| Vì sao chưa có owner nhận? | Inventory thiếu mapping giữa bucket và service owner. | Asset inventory, ownership register. |

Kết luận hợp lý thường là **đa nguyên nhân**: policy sai, thiếu guardrail trước triển khai, detection chậm và ownership gap. Kế hoạch chỉ thay bucket policy hôm nay có thể sửa triệu chứng nhưng bucket tương tự sẽ xuất hiện ở lần deploy sau.

**Cảnh báo:** 5 Whys không phải phép chứng minh nguyên nhân. Mỗi “vì sao” là giả thuyết cần test hoặc nguồn xác thực. Dừng khi đã tìm được những nguyên nhân có thể hành động và giải thích được đường dẫn đến failure; không ép một chuỗi tuyến tính nếu thực tế có nhiều nhánh.

### 4.2. Nhóm nguyên nhân thường gặp

- **Thiết kế:** thiếu trust boundary, security requirement hoặc biện pháp thực thi phù hợp.
- **Cấu hình:** drift, sai policy, mặc định không an toàn, thay đổi trực tiếp ngoài IaC.
- **Phát triển:** thiếu validation, review, tests, dependency/secret management.
- **Vận hành:** thiếu owner, lịch patch, offboarding, change gate, runbook.
- **Quan sát:** telemetry thiếu, alert routing sai, không có kiểm thử end-to-end.
- **Quản trị:** thẩm quyền mơ hồ, ngưỡng rủi ro thiếu, exception kéo dài, vendor thiếu bằng chứng.
- **Phụ thuộc:** sản phẩm không hỗ trợ tính năng, nhà cung cấp chậm sửa, chain/subprocessor chưa rõ.

Một action plan trưởng thành thường có **quick containment**, **permanent technical fix**, **systemic preventive action** và **verification**; không nhất thiết phải có bốn ticket riêng nhưng phải theo dõi rõ.

## 5. Đánh giá ưu tiên theo rủi ro, không chỉ theo nhãn severity

Severity của scanner hoặc audit là đầu vào, không phải toàn bộ quyết định. Cần xét **tác động kinh doanh, khả năng khai thác, exposure, dữ liệu, control bù trừ, ràng buộc pháp lý/hợp đồng và thời gian rủi ro tồn tại**.

### 5.1. Thang ưu tiên minh họa

| Tình huống | Ví dụ | Hướng ưu tiên |
|---|---|---|
| **Nguy cơ đang diễn ra hoặc có bằng chứng xâm nhập** | Credential sản xuất bị lộ và đang bị dùng trái phép. | Kích hoạt incident response/containment ngay theo playbook; action plan xử lý hậu quả và nguyên nhân song song. |
| **Rủi ro nghiêm trọng dễ khai thác** | Lỗi authorization ở API public chứa dữ liệu nhạy cảm. | Ưu tiên cao, giảm phơi nhiễm ngay, xác định deadline từ risk policy và nghĩa vụ áp dụng. |
| **Vulnerability có điều kiện khai thác hạn chế** | Lỗi trong service nội bộ có segmentation và quyền chặt. | Đánh giá exposure thực, lập kế hoạch vá và test đường tấn công. |
| **Nonconformity quy trình** | Access review trễ ở nhóm tài khoản ít quyền. | Có owner, kiểm chứng phạm vi, đánh giá tác động và deadline phù hợp. |
| **Evidence gap** | Không thể chứng minh vài account có logging vì collector thiếu quyền. | Sửa đường bằng chứng nhanh để xác định trạng thái control; không tự báo an toàn. |
| **Yêu cầu bên ngoài có thời hạn** | Hợp đồng yêu cầu khắc phục trong một thời hạn xác định. | Theo dõi đồng thời mức rủi ro và nghĩa vụ, escalate nếu không thể đáp ứng. |

**Không có SLA sửa lỗi phổ quát** cho mọi tổ chức hoặc mọi framework. Mốc trong kế hoạch phải xuất phát từ chính sách đã được phê duyệt, risk appetite, yêu cầu pháp lý/hợp đồng, khả năng vận hành và dữ kiện thực tế. Deadline khó đạt không phải lý do âm thầm giảm severity.

### 5.2. Công thức risk ranking chỉ là công cụ hỗ trợ

Tổ chức có thể dùng hệ thống scoring nội bộ gồm criticality, exposure, exploitability, likelihood và impact. Nhưng không nên cộng/trừ điểm mơ hồ rồi coi con số là sự thật khách quan. Cần lưu **căn cứ từng yếu tố** và cơ chế override có thẩm quyền cho các tình huống như attack đang diễn ra, dữ liệu đặc biệt nhạy cảm hoặc nghĩa vụ bắt buộc.

### 5.3. Tách ba loại hạn

- **Mitigation deadline:** thời điểm cần giảm phơi nhiễm tạm thời.
- **Permanent remediation deadline:** thời điểm nguyên nhân được sửa.
- **Evidence/retest deadline:** thời điểm bằng chứng chứng minh kết quả phải được hoàn tất và review.

Một thay đổi deploy trước deadline nhưng chưa retest không tự động đạt trạng thái **Verified Closed**.

## 6. Chọn phương án xử lý và ranh giới quyền quyết định

Một finding có thể được xử lý bằng nhiều quyết định, với mức bảo đảm khác nhau:

| Phương án | Ví dụ | Bằng chứng cần có |
|---|---|---|
| **Remediate / fix** | Sửa lỗ hổng code, thu hồi quyền, thay cấu hình. | Source diff/change record, deploy evidence, test control gốc đạt. |
| **Mitigate tạm thời** | WAF, segmentation, tắt endpoint, hạn chế dữ liệu. | Test biện pháp tạm, monitoring và kế hoạch sửa triệt để. |
| **Avoid** | Ngừng chức năng hoặc decommission asset sinh rủi ro. | Chứng cứ ngừng đường truy cập, tắt dependency, xóa/quản trị dữ liệu. |
| **Transfer/share một phần rủi ro** | Hợp đồng hỗ trợ, bảo hiểm hoặc giao nhiệm vụ cho vendor. | Phân chia trách nhiệm và năng lực thực tế; không được coi trách nhiệm bảo mật biến mất. |
| **Accept theo thẩm quyền** | Tiếp tục vận hành một ngoại lệ nội bộ có thời hạn. | Risk assessment, owner, approval, điều kiện, expiry và cơ chế giám sát. |
| **Investigate further** | Phép quét có khả năng false positive hoặc thiếu chứng cứ. | Test bổ sung, dữ liệu và quyết định có căn cứ. |

**Risk acceptance không tương đương remediation thành công.** Nếu một finding vẫn tồn tại nhưng rủi ro được chấp nhận, cần đóng/đưa trạng thái theo quy trình governance với nhãn khác **Verified Fixed**. Phải giữ rõ **control gốc có đáp ứng hay không**. Cơ chế chấp nhận rủi ro nội bộ không tự miễn nghĩa vụ pháp luật, hợp đồng hoặc yêu cầu chương trình đánh giá bên ngoài.

## 7. Chia Action plan thành các gói công việc có thể thực thi

Một kế hoạch lớn nên chia thành **work packages** hoặc action items độc lập có kết quả và owner rõ. Từng action cần đủ nhỏ để quan sát tiến độ nhưng không bị chia vụn khiến nghiệm thu khó liên kết mục tiêu bảo mật.

### 7.1. Bộ trường tối thiểu cho mỗi action

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| **action_id** | Định danh duy nhất, liên kết finding và parent plan. | ACT-IAM-017-02. |
| **action_type** | Containment, corrective, preventive, detection, verification. | Corrective. |
| **owner** | Người/nhóm chịu trách nhiệm thực hiện, không phải người “theo dõi chung”. | Platform IAM Engineer. |
| **accountable** | Người chịu trách nhiệm cuối về kết quả và nguồn lực. | Identity Security Owner. |
| **scope** | Asset, account, vùng, repo, dữ liệu hoặc role chịu tác động. | 4 production principals. |
| **task / deliverable** | Hành động cụ thể và output mong đợi. | Giảm action wildcard theo role mapping. |
| **dependencies** | Công việc phải hoàn tất trước và lý do. | Inventory effective permissions được chốt. |
| **deadline và milestone** | Mốc cụ thể, có thể kiểm tra. | PR approved, staged deploy, production deploy, retest. |
| **acceptance criteria** | Điều kiện đạt với phương pháp đo. | Không còn quyền vượt scope; nghiệp vụ smoke test PASS. |
| **evidence required** | File, run ID, query, change, log và reviewer link cần thu. | Effective policy export + test deny/allow. |
| **status và blocker** | Trạng thái có quy tắc chuyển, nguyên nhân trễ và escalation. | BLOCKED_BY_VENDOR hoặc TESTING. |
| **rollback/contingency** | Cách xử lý khi thay đổi tạo lỗi không chấp nhận. | Khôi phục policy bản trước có kiểm soát, giữ mitigation. |

### 7.2. Phân loại action theo mục đích

~~~text
Finding F-017
  ├─ ACT-01: giảm rủi ro ngay (containment)
  ├─ ACT-02: sửa cấu hình/code trong phạm vi bị ảnh hưởng
  ├─ ACT-03: xử lý nguyên nhân hệ thống trong pipeline/chính sách
  ├─ ACT-04: cải thiện phát hiện/giám sát sự tái diễn
  └─ ACT-05: retest độc lập và nghiệm thu closure
~~~

Nếu cùng một action xử lý nhiều findings, phải tạo quan hệ **many-to-many** rõ: một PR có thể sửa ba bugs, nhưng từng finding cần có bằng chứng rằng tiêu chí riêng đã đạt. Không tự đóng cả ba chỉ vì PR được merge.

### 7.3. Mô hình Action plan theo kết quả đầu ra

**Deliverable tốt:** “Automated policy gate từ chối cấu hình object storage public trái whitelist và đã có test âm/dương chạy thành công cho template production.”

**Deliverable yếu:** “Đã làm thêm security testing.”

Điểm khác biệt là ở việc chỉ rõ **trạng thái quan sát được** và **cách kiểm chứng**, không phải số giờ nhân viên đã làm.

## 8. Thiết lập Ownership, RACI và quyền phê duyệt

Kế hoạch không nên chỉ ghi “Assigned to DevOps”. Người triển khai có thể nghỉ việc hoặc đổi nhóm, nhưng một **accountable owner** phải chịu trách nhiệm về kết quả tới khi finding được đóng hoặc xử lý rủi ro bằng quyết định phù hợp.

| Hoạt động | Responsible (thực hiện) | Accountable (chịu trách nhiệm) | Consulted | Informed |
|---|---|---|---|---|
| Xác minh finding và phạm vi | Security Analyst / Assessor | Control Owner | System Owner | Risk/Compliance |
| Phân tích RCA | Engineering / Platform Team | Service Owner | Security, SRE | Audit/Risk |
| Đặt ưu tiên và deadline | Risk / Security | Business Risk Owner theo thẩm quyền | Legal/Compliance khi cần | Engineering |
| Thiết kế và triển khai fix | Engineering Owner | Service Owner | Security, Data Owner | Operations |
| Phê duyệt production change | Change Authority theo quy trình | Change/Service Owner | Security, Incident Lead khi cần | Stakeholders |
| Kiểm tra độc lập / retest | Security Assurance / Qualified Reviewer | Control/Assurance Owner | Engineering | Risk Owner |
| Chấp nhận residual risk | Người được ủy quyền theo risk policy | Risk Owner | Security/Legal/Compliance | Audit |
| Đóng finding | Issue/Assurance Owner theo chính sách | Control Owner / Risk Governance | Reviewer | Reporting stakeholders |

Đây là ma trận minh họa. Cơ cấu thực tế thay đổi theo tổ chức, nhưng cần tránh để một cá nhân **tự tạo vấn đề, tự sửa, tự kiểm thử và tự phê duyệt closure** ở những rủi ro đòi độc lập.

### 8.1. Owner và assignee không phải một

- **Assignee:** làm task kỹ thuật, có thể thay khi đổi ca hoặc team.
- **Action owner:** chịu trách nhiệm đưa action đạt acceptance criteria.
- **Finding owner:** bảo đảm tất cả actions và bằng chứng giải quyết finding.
- **Risk owner:** có quyền chấp nhận hoặc yêu cầu giảm residual risk.
- **Verifier:** kiểm tra bằng chứng và kết quả retest, không chỉ xác nhận ticket được cập nhật.

Đối với finding liên quan nhiều team, chỉ định một đầu mối accountable, đồng thời chia actions có owner độc lập; không để “mọi người cùng chịu trách nhiệm” dẫn đến không ai có quyền xử lý blocker.

## 9. Sắp xếp dependencies, mốc và đường găng

Nhiều kế hoạch chậm vì các bước được đặt theo thứ tự sai. Ví dụ không thể thu hồi role IAM hiện tại trước khi ứng dụng phụ thuộc được sửa, hoặc không thể kiểm tra data integrity sau migration khi chưa có nguồn đối soát.

~~~mermaid
flowchart LR
    A["A1: Chốt asset và quyền hiện tại"] --> B["A2: Thiết kế policy quyền tối thiểu"]
    B --> C["A3: Kiểm thử tương thích staging"]
    C --> D["A4: Deploy canary"]
    D --> E["A5: Rollout production"]
    E --> F["A6: Retest hiệu lực IAM"]
    F --> G["A7: Sign-off và đóng finding"]
    A --> H["A0: Giảm phơi nhiễm tức thời"]
    H -.-> E
    I["A8: Bổ sung preventive policy-as-code"] --> G
~~~

**Dependencies** là quan hệ phải hoàn tất trước khi action sau an toàn hoặc có thể thực hiện, không chỉ một danh sách tham khảo. Plan nên ghi:

- **Predecessor** và **condition** (“A3 PASS về luồng thanh toán” trước “A4 deploy”).
- Thời gian/nguồn lực cần, chủ sở hữu, lịch triển khai.
- **Blocker**: vendor, change window, test environment, khóa quản trị, approval, dữ liệu hay nhân lực.
- **Critical path**: chuỗi quyết định deadline thực tế.
- **Fallback**: khi predecessor trễ, có thể giảm phạm vi, duy trì mitigation hoặc xin thay phương án theo quyền?
- **Gate độc lập**: công việc đã hoàn tất nhưng chưa được xác minh không tự mở khóa bước deploy rủi ro cao.

### 9.1. Tránh tiến độ 90% mãi không xong

Một task “90%” không có deliverable dễ kéo dài. Nên dùng milestone có thể kiểm tra như “PR merge”, “staging test PASS”, “production deployed”, “control rechecked”, “closure approved”. Theo dõi phần việc **chưa đạt acceptance**, không chỉ số giờ đã chi.

### 9.2. Gắn kế hoạch vào quy trình Change Management

Thay đổi firewall, IAM, database schema hoặc routing có thể gây gián đoạn. Action plan cần tham chiếu change record, thời gian dự kiến, phê duyệt, test trước triển khai, rollback và kế hoạch liên lạc. Một lỗi “sửa bảo mật” nhưng làm hỏng ứng dụng trọng yếu có thể tạo rủi ro mới cần được đánh giá.

## 10. Mitigation, compensating controls và ngoại lệ trong lúc chờ sửa

Nhiều vấn đề không thể sửa trong vài giờ: EOL system, vendor chưa phát hành patch, database migration mất nhiều tuần, đổi kiến trúc identity cần phối hợp. Cần **interim protection** có thời hạn và bằng chứng.

### 10.1. Plan phải ghi hai đường đi đồng thời

~~~text
Đường 1 — Giảm phơi nhiễm ngay:
  giới hạn nguồn truy cập / tắt tính năng rủi ro / bổ sung giám sát
  -> kiểm thử hiệu lực mitigation
  -> theo dõi tới khi xử lý triệt để

Đường 2 — Khắc phục lâu dài:
  root cause / thiết kế thay thế / triển khai
  -> kiểm thử bảo mật và chức năng
  -> retest control gốc và nghiệm thu
  -> gỡ mitigation tạm khi an toàn và được duyệt
~~~

### 10.2. Một biện pháp tạm phải có những gì?

| Thuộc tính | Ví dụ |
|---|---|
| Risk scenario được giảm | API chưa sửa authorization có thể đọc bản ghi ngoài phạm vi. |
| Biện pháp | Tạm ngừng chức năng export cho mọi account không thiết yếu. |
| Bằng chứng thực thi | Feature flag trạng thái production + thử request bị từ chối. |
| Giới hạn | Một API nội bộ khác chưa kiểm thử; phải chặn tại gateway. |
| Monitoring | Alert khi có request bất thường hoặc thay đổi feature flag. |
| Owner và expiry | Product Security Owner, review theo mốc nội bộ. |
| Điều kiện thu hồi | Fix đã đạt retest, rollback được chuẩn bị, risk owner đồng ý. |

**Mitigation có thể giảm rủi ro nhưng không chứng minh nguyên nhân gốc biến mất.** Một WAF rule chặn payload đã biết không thay cho việc sửa query không an toàn trong code khi yêu cầu control gốc là xử lý đầu vào đúng cách.

### 10.3. Ngoại lệ phải theo đúng thẩm quyền

Nếu deadline không thể đạt và tổ chức có cơ chế policy exception, cần hồ sơ riêng hoặc liên kết chặt: risk assessment, scope, owner, điều kiện bù trừ, approval, expiry, review và hành động khi hết hạn. Với pháp luật/hợp đồng hoặc chương trình chứng nhận có quy định riêng, **phê duyệt nội bộ không tự thay đổi nghĩa vụ**. Ghi kết luận kiểm soát thực tế và quyết định rủi ro thành các trường khác nhau.

## 11. Thực thi an toàn: Design, Test, Deploy, Observe

Một remediation plan phải kiểm soát cả **rủi ro của việc sửa**. Ví dụ giảm quyền IAM có thể làm ngừng giao dịch thanh toán; thay khóa có thể làm mất khả năng decrypt backup; bật chặn mạng có thể cô lập kênh ứng cứu sự cố.

### 11.1. Quy trình triển khai gợi ý

1. **Design review:** xác nhận sửa đúng nguyên nhân, ranh giới tin cậy, tính tương thích, dữ liệu và nguy cơ xuất hiện lỗi mới.
2. **Implementation:** thay đổi code/IaC/policy trong quy trình quản lý phiên bản, có review người có thẩm quyền.
3. **Pre-production test:** kiểm thử âm/dương của security control, tính năng nghiệp vụ, migration, latency và backward compatibility.
4. **Change approval:** đánh giá rủi ro triển khai, cửa sổ thay đổi, rollback, người trực và phương án liên lạc.
5. **Staged rollout:** canary/percentage/phân vùng nếu phù hợp; giữ metric giám sát và gate dừng.
6. **Production verification:** xác nhận artifact version, deployment completion, effective configuration và những luồng bị ảnh hưởng.
7. **Independent retest:** verifier kiểm tra tiêu chí gốc trên scope, không chỉ xem CI xanh.
8. **Handover:** cập nhật runbook, inventory, baseline, alert, knowledge transfer và lịch giám sát tái diễn.

### 11.2. Rollback không phải lúc nào cũng an toàn

Nếu đổi mã hóa hoặc schema dữ liệu, rollback có thể mất dữ liệu hoặc tái mở lỗ hổng. Cần thiết kế phương án an toàn trước deploy: backup có thể restore, forward fix, chuyển chế độ hạn chế, feature flag hoặc rollback có xác minh. Mỗi phương án phải có **điều kiện kích hoạt, rủi ro và người quyết định**.

### 11.3. Cơ chế dừng khi fix gây hại

Các tín hiệu cần theo dõi sau rollout gồm error rate, failed auth, customer impact, data integrity, SIEM ingest và cảnh báo security. Khi vượt ngưỡng đã duyệt, nhóm có thẩm quyền dừng hoặc revert theo runbook. Việc hệ thống “không báo lỗi” chưa chứng minh không còn đường bypass; vẫn cần security retest.

## 12. Retest và Verification: Chứng minh điều kiện đã được sửa

Mấu chốt của action plan là **verification based on acceptance criteria**. Người thực hiện thay đổi cung cấp triển khai và evidence; reviewer kiểm tra lại control gốc hoặc mục tiêu rủi ro ở phạm vi phù hợp.

### 12.1. Bốn lớp kiểm tra

| Lớp | Câu hỏi cần trả lời | Evidence |
|---|---|---|
| **Deployment evidence** | Thay đổi nào đã tới những asset nào, khi nào? | Commit, pipeline/run ID, image digest, change ticket, configuration snapshot. |
| **Control implementation** | Cấu hình/logic mới có hiện diện và hiệu lực tại runtime? | Effective policy, deployment inventory, security test. |
| **Operating effectiveness** | Hành vi bảo vệ thực sự xảy ra trong trường hợp cần thiết? | Allow/deny tests, audit events, scanner retest, synthetic controls, review theo kỳ. |
| **Risk outcome** | Đường tấn công gốc đã bị đóng hoặc rủi ro còn lại nằm trong mức được chấp nhận? | Threat scenario retest, exposure review, data/asset validation, risk decision. |

Một PR merge là **deployment/progress evidence**, không tự chứng minh hiệu lực ở production. Một scan sạch có thể hữu ích nhưng không chứng minh mọi tình huống nếu scanner không đủ credential hoặc không bao phủ toàn bộ population.

### 12.2. Tiêu chí chấp nhận phải đo hai chiều

Với finding “service account có quyền wildcard”:

- **Negative/security test:** service account **không** thực hiện được những action không được cấp.
- **Positive/business test:** service account **vẫn** thực hiện được action cần thiết của ứng dụng.
- **Coverage:** mọi service account, access path và environment trong scope được kiểm tra.
- **Observability:** thay đổi quyền và các lần deny/allow trọng yếu có thể truy vết.
- **Period:** nếu cần chứng minh hiệu lực trong kỳ, có thêm lịch sử config và kiểm tra drift, không chỉ point-in-time.

### 12.3. Phân loại kết quả

- **PASS:** bằng chứng đáng tin, đúng phạm vi và thời gian cho thấy các tiêu chí sửa đã đạt.
- **FAIL:** test chứng minh điều kiện không đạt hoặc còn đường lỗi theo tiêu chí.
- **INCONCLUSIVE:** không đủ bằng chứng hoặc môi trường/test coverage không cho phép kết luận.
- **NOT_APPLICABLE:** tiêu chí thật sự ngoài phạm vi và có lý do phê duyệt.

Một finding **không được đóng là VERIFIED FIXED** nếu retest đang INCONCLUSIVE. Có thể ghi “Fix deployed, awaiting evidence” để phản ánh tiến độ, nhưng phải giữ trách nhiệm đến khi hoàn tất.

## 13. Tổ chức Evidence chain cho Action plan

Một record có thể liên kết:

~~~mermaid
flowchart TD
    F["Finding ID + original evidence"] --> R["Requirement/control ID + risk scenario"]
    R --> RCA["Root cause analysis"]
    RCA --> PL["Action plan version + approvals"]
    PL --> A1["Action A: containment / mitigation"]
    PL --> A2["Action B: permanent fix"]
    PL --> A3["Action C: preventive controls"]
    A1 --> E["Change + test + operational evidence"]
    A2 --> E
    A3 --> E
    E --> RT["Independent retest + verdict"]
    RT --> CL["Closure decision / residual risk / review"]
    CL --> MN["Monitoring / recurrence detection"]
~~~

### 13.1. Evidence metadata tối thiểu

| Trường | Ý nghĩa |
|---|---|
| **evidence_id và type** | Tách raw export, test output, reviewer decision và deployment record. |
| **related_finding/action/control** | Truy vết đúng đối tượng kiểm soát. |
| **source và locator** | Hệ thống, resource IDs, tenant, API/query hoặc ticket. |
| **collected_at/event_time** | Mốc thời gian UTC, kỳ áp dụng, độ trễ nguồn khi cần. |
| **collector và method version** | Ai/công cụ nào tạo, tham số và điều kiện kiểm thử. |
| **scope/population** | Những asset, principal, dataset hoặc API endpoint đã kiểm tra. |
| **integrity/version** | Hash, object version, provenance/lineage phù hợp. |
| **classification/access** | Dữ liệu nhạy cảm, quyền chia sẻ, chính sách retention. |
| **verdict/limitations** | Kết quả, những phần chưa thử, lỗi API hoặc assumptions. |
| **reviewer/sign-off** | Ai đánh giá và chấp nhận kết quả, timestamp và version. |

Không đính kèm secrets, token hay dữ liệu khách hàng không cần thiết vào ticket. Có thể lưu bản gốc ở kho evidence được phân quyền, chỉ liên kết theo ID và cung cấp bản redacted với lineage.

### 13.2. Bằng chứng fix khác bằng chứng cải tiến hệ thống

- **Fix evidence:** chứng minh tài sản bị lỗi đã được sửa.
- **Prevention evidence:** chứng minh cơ chế không cho cấu hình/tình huống tương tự tái xuất hiện.
- **Detection evidence:** chứng minh tổ chức sẽ phát hiện nếu control thất bại lần nữa.
- **Governance evidence:** chứng minh quyết định, thẩm quyền, thời hạn và rủi ro được quản lý.

Có fix nhưng thiếu prevention có thể vẫn đóng finding hẹp theo acceptance criteria được duyệt, nhưng systemic action còn mở nếu kế hoạch yêu cầu. Không che một action chưa đạt bằng việc gộp vào “các việc sau này”.

## 14. Theo dõi tiến độ: Trạng thái có định nghĩa rõ

Không nên dùng trạng thái “Done” cho nhiều giai đoạn khác nhau.

| Trạng thái minh họa | Điều kiện vào | Điều kiện ra |
|---|---|---|
| **NEW** | Finding được ghi và chưa phân loại. | Đã xác minh scope, risk, owner. |
| **TRIAGED** | Rủi ro và tính hợp lệ được xác nhận. | Action plan có owner, deadlines và acceptance criteria. |
| **PLANNED** | Kế hoạch được phê duyệt, phụ thuộc rõ. | Action bắt đầu triển khai hoặc chờ blocker được xác định. |
| **IN_PROGRESS** | Có công việc đang thực hiện. | Đã deploy, bị block hoặc đổi plan có approval. |
| **BLOCKED** | Dependency/vendor/change window ngăn tiến độ. | Có phương án unblock và cập nhật thời gian/rủi ro. |
| **MITIGATED** | Biện pháp tạm đã được kiểm chứng. | Permanent fix/exception theo dõi tiếp; chưa mặc định closed. |
| **IMPLEMENTED** | Thay đổi được triển khai theo scope. | Có evidence retest, không đồng nghĩa PASS. |
| **VERIFYING** | Reviewer đang đánh giá evidence/control. | PASS, FAIL hoặc INCONCLUSIVE kèm quyết định. |
| **VERIFIED_CLOSED** | Acceptance criteria và điều kiện governance đạt; được ký duyệt. | Monitoring; nếu tái diễn mở lại hoặc issue mới có liên kết. |
| **RISK_ACCEPTED** | Quyết định rủi ro hợp lệ, đúng scope và hạn. | Reassessment khi expiry/thay đổi; không tương đương fixed. |
| **REOPENED** | Retest FAIL hoặc có evidence mới phá kết luận closure. | Kế hoạch mới/phiên bản mới có owner và deadline. |

### 14.1. Không tự động chuyển “IMPLEMENTED” thành “CLOSED”

Hệ thống tracking có thể đồng bộ một deployment ticket thành “đã thực hiện”. Nhưng finding cần **verifier sign-off** riêng. Ví dụ deploy chính sách IAM hoàn tất lúc 10:00, reviewer chỉ kiểm thử được 3/4 tài khoản; trạng thái phù hợp là **VERIFYING/INCONCLUSIVE**, không phải đóng tất cả.

### 14.2. Những sự kiện phải replan

- Một task nằm trên critical path quá hạn.
- Root cause ban đầu bị bác bỏ hoặc phát hiện thêm nguyên nhân.
- Phát hiện có rủi ro cao hơn, exploit mới, thay đổi exposure hoặc sự cố xảy ra.
- Vendor không cung cấp patch hay bằng chứng đúng kỳ.
- Scope tăng: asset mới, dữ liệu nhạy cảm hơn, region mới.
- Mitigation mất hiệu lực hoặc gây tác động nghiệp vụ.
- Retest FAIL hoặc evidence thiếu coverage.
- Nguồn lực/owner thay đổi và không còn đáp ứng mốc cam kết.

**Replan** phải lưu lý do, impact, phiên bản lịch, quyết định và ai phê duyệt; không chỉ sửa due date để không hiển thị overdue.

## 15. Báo cáo Action plan và quản trị escalations

Các nhóm cần các mức chi tiết khác nhau:

| Đối tượng | Họ cần biết gì? | Nhịp và hình thức gợi ý |
|---|---|---|
| **Engineering / Operations** | Action, dependency, test failure, blocker, phạm vi triển khai và rollback. | Board công việc, daily/weekly theo rủi ro. |
| **Security / Assurance** | Control ID, trạng thái evidence, retest, residual risk, drift và overdue. | Finding register và bảng kiểm tra theo kỳ. |
| **Business/Risk Owner** | Tác động nghiệp vụ, deadline, chi phí, rủi ro còn lại, quyết định cần ký. | Risk review theo ngưỡng và sự kiện. |
| **Legal/Compliance** | Nghĩa vụ bên ngoài, thông báo, mốc hợp đồng/luật, trạng thái ngoại lệ hợp lệ. | Báo cáo theo nghĩa vụ áp dụng. |
| **Audit / Management** | Severity, trend, blockers, tiến độ và bằng chứng nghiệm thu. | Executive dashboard có drill-down tới evidence. |

### 15.1. Mẫu cập nhật ngắn

~~~text
Finding: F-017 / Control: IAM-PRIV-01 / Severity: HIGH
Accountable: Identity Security Owner
Current risk: HIGH, mitigation đã triển khai/test đến ngày ...
Target: effective least privilege + business flow PASS
Progress: 2/4 actions VERIFIED, 1 IMPLEMENTED, 1 BLOCKED
Milestone: production rollout [date], retest [date]
Blocker: ứng dụng batch còn phụ thuộc wildcard permission
Temporary controls: restrict subnet + alert, evidence [ref]
Decision needed: phê duyệt lịch migration, ưu tiên nguồn lực
Next review / escalation: [timestamp, owner]
~~~

Không đánh dấu “2/4 = 50% rủi ro đã giảm” trừ khi có mô hình rủi ro chứng minh cách tổng hợp. Số action hoàn thành là **progress metric**, không tự mô tả phần trăm rủi ro giảm.

### 15.2. Escalation có kích hoạt rõ

Một blocker cần trigger: quá hạn bao nhiêu, chạm nghĩa vụ nào, mitigation còn bảo vệ không, ai phê duyệt replan hoặc pause service. Không để cảnh báo overdue chỉ được gửi cho chính người đang block mà thiếu đường lên risk owner/management theo chính sách.

## 16. Metrics đánh giá hiệu quả kế hoạch khắc phục

Các chỉ số nên xem **tốc độ, chất lượng và mức giảm rủi ro**, không chỉ số lượng finding đóng.

| Metric | Ý nghĩa | Lưu ý diễn giải |
|---|---|---|
| **Open findings by risk** | Số finding chưa giải quyết phân theo mức rủi ro và loại control. | Cần population đầy đủ, dedup và scope rõ. |
| **Overdue finding rate** | Tỷ lệ finding vượt hạn đã phê duyệt trên tập áp dụng. | Phải bao gồm finding chờ verification và đã replan nếu còn nghĩa vụ. |
| **Time to mitigate** | Từ mốc phát hiện/xác nhận đến khi mitigation có hiệu lực. | Mitigation không đồng nghĩa fix triệt để. |
| **Time to verified remediation** | Từ mốc theo contract tới khi verifier PASS và đủ điều kiện closure. | Không lấy deployment date làm endpoint nếu chưa retest. |
| **Reopen/recurrence rate** | Tỷ lệ finding đã đóng bị mở lại hoặc lỗi tương tự tái diễn. | Tách lỗi mới có root cause khác; cần tiêu chí mapping. |
| **Evidence completeness** | Tỷ lệ action có đủ bằng chứng theo acceptance criteria. | Có file không đồng nghĩa chứng minh đúng control. |
| **Verification failure rate** | Tỷ lệ action đã triển khai nhưng retest không đạt. | Có thể phản ánh test tốt hơn, không chỉ kỹ thuật yếu. |
| **Root-cause closure** | Tỷ lệ finding có nguyên nhân gốc được xử lý và kiểm tra. | Cần phân biệt symptom fix và systemic prevention. |
| **Compensating control health** | Biện pháp bù trừ đang hiệu lực cho finding chưa đóng. | Không dùng trung bình để che một control quan trọng bị mất. |
| **Risk-weighted backlog** | Tập finding cần ưu tiên theo risk tier, critical assets và exposure. | Trọng số phải có phương pháp được duyệt, không phải tỷ lệ an toàn tổng thể. |
| **Age of oldest critical finding** | Thời gian một finding critical còn mở. | Cần điều tra cả owner, blockers, reason for delay. |

### 16.1. Ví dụ phép tính

Giả sử trong kỳ có 20 findings rủi ro cao đang theo dõi: 6 đã VERIFIED_CLOSED, 3 đã triển khai nhưng retest chưa xong, 8 đang thực hiện và 3 quá hạn chưa có mitigation hữu hiệu.

- **Verified closure:** 6/20 = **30%** trên tập 20 finding theo dõi.
- **Implemented but unverified:** 3/20 = **15%**; không tính là đóng.
- **Overdue unmitigated:** 3/20 = **15%**; cần ưu tiên escalation.
- **Remaining in progress:** 8/20 = **40%**.

Những tỷ lệ này là **chỉ số trạng thái**, không chứng minh mức rủi ro chung đã giảm 30%. Để biết rủi ro giảm, phải xem từng kịch bản, exposure, bảo vệ bù trừ và kết quả retest.

### 16.2. Thời gian khắc phục trung bình có thể gây ảo giác

Nếu chỉ tính Mean Time to Remediate trên những finding đã đóng, các finding khó và tồn lâu vẫn mở sẽ bị loại khỏi mẫu số, làm chỉ số quá lạc quan. Báo thêm **open age, overdue, median/P90 theo severity và số chưa được kiểm chứng**. Mỗi kỳ cần nói rõ cohort theo ngày phát hiện hay ngày đóng, timezone và cách xử lý finding reopen.

### 16.3. Tránh làm đẹp dashboard

Một nhóm có thể hạ severity hoặc dời due date để giảm số overdue. Quy trình quản trị nên lưu **severity history, original due date, approvals, revised due date, reason và change audit trail**. Hạn được điều chỉnh theo rủi ro không đồng nghĩa vi phạm cũ chưa từng tồn tại.

## 17. Action plan mẫu: Khắc phục rủi ro object storage public

Tình huống minh họa: một hệ thống hóa đơn dùng cloud object storage. Audit phát hiện hai bucket trong production được đặt public read theo policy không phù hợp, dữ liệu thử có thể được tải về bằng request không có chứng thực. Đội vận hành đã tắt public read cho một bucket nhưng bucket còn lại thuộc pipeline export cũ; IaC template tạo bucket mới vẫn cho phép public policy. Không có cảnh báo nào đến service owner khi cấu hình thay đổi.

**Business impact giả định:** hóa đơn có thể chứa dữ liệu khách hàng; exposure không được chấp nhận theo policy. Tổ chức cần hành động giảm truy cập ngay và xử lý nguyên nhân hệ thống, không chỉ thay thuộc tính một bucket.

### 17.1. Problem statement và tiêu chí thành công

- **Finding:** F-STORAGE-023 — Public access không được phép với dữ liệu hóa đơn production.
- **Security objective:** chỉ các principal được ủy quyền mới có thể đọc hóa đơn theo quyền nghiệp vụ.
- **Control:** DATA-ACCESS-05 — lưu trữ hóa đơn không cho phép anonymous access; thay đổi policy được giám sát.
- **Scope:** hai bucket đã phát hiện và toàn bộ bucket phục vụ hóa đơn theo inventory.
- **Root causes:** IaC template thiếu policy-as-code gate, inventory/owner mapping thiếu, monitoring không gửi alert.
- **Acceptance:** không còn anonymous read trên mọi bucket thuộc scope; authorized application vẫn truy cập được; pipeline không tạo lại bucket public trái chính sách; alert đi tới owner với sự kiện kiểm thử; verifier ký retest.
- **Ràng buộc:** bảo toàn log điều tra, tránh làm mất dữ liệu, kiểm tra tương thích ứng dụng sau khi chặn truy cập.

### 17.2. Work packages

| ID | Mức ưu tiên và hành động | Owner | Phụ thuộc | Acceptance và evidence |
|---|---|---|---|---|
| **A0** | Ngay: giới hạn anonymous access ở hai bucket và đánh giá nghi vấn truy cập trái phép. | Cloud Operations + IR | Quyền thay đổi đã phê duyệt theo incident/change policy. | Effective policy, test anonymous deny, business flow allow, log và IR record. |
| **A1** | Kiểm kê mọi bucket hóa đơn, owner và data classification. | Asset/Cloud Team | Inventory sources, quyền API. | Population đối chiếu từ cloud API và CMDB, không còn bucket không owner. |
| **A2** | Sửa IaC module để mặc định chặn public read ngoài ngoại lệ có cơ chế duyệt. | Platform Engineering | RCA và requirement rõ. | PR, policy tests positive/negative, review, IaC version. |
| **A3** | Thử thay đổi staging, canary rồi rollout cho mọi bucket production thuộc scope. | Service Engineering | A1, A2 và change approval. | Deploy IDs, effective policies, functional tests, rollback readiness. |
| **A4** | Tạo detection cho drift và kiểm tra kênh alert tới owner. | Security Monitoring | Inventory/owner A1, event source. | Synthetic config-change event, alert và receipt của nhóm trực. |
| **A5** | Retest control gốc và báo cáo residual risk. | Security Assurance | A0–A4 đạt theo phạm vi. | Kiểm tra anonymous deny/authorized allow toàn scope, alert test, evidence chain và sign-off. |

### 17.3. Lịch minh họa theo milestones

Dưới đây là kế hoạch **giả định**, không phải SLA tiêu chuẩn:

| Mốc | Điều kiện thực hiện | Nếu không đạt |
|---|---|---|
| **M0 — Containment** | Chặn truy cập public không được phép, kiểm tra hiệu lực ngay khi phát hiện. | Escalate IR/risk owner, hạn chế dịch vụ hoặc chọn biện pháp an toàn khác. |
| **M1 — Scope confirmed** | Hoàn tất inventory và phân loại dữ liệu, owner rõ. | Không tuyên bố toàn scope đã được sửa; tiếp tục rà soát. |
| **M2 — Preventive change** | IaC/guardrail có test và review đầy đủ. | Giữ mitigations, xử lý blocker, không phát hành module chưa an toàn. |
| **M3 — Controlled deployment** | Cấu hình mới triển khai đúng asset, test nghiệp vụ đạt. | Dừng rollout theo điều kiện và change record. |
| **M4 — Verification** | Retest security/detection, bằng chứng đầy đủ, risk owner xem residual risk. | FAIL/INCONCLUSIVE và replan; không đóng finding. |
| **M5 — Closure** | Reviewer/owner sign-off, monitoring owner tiếp nhận và lưu dấu vết. | Giữ trạng thái đang xác minh, báo blocker. |

### 17.4. Phân biệt hai trường hợp sau rollout

**Trường hợp A:** cả hai bucket đã deny anonymous read, app vẫn hoạt động, nhưng IaC template cũ chưa sửa. Finding hẹp về **cấu hình hiện tại** có thể được đánh giá lại theo acceptance criteria đã duyệt; song **systemic root-cause action còn mở** và nguy cơ tái diễn vẫn tồn tại. Không được nói kế hoạch toàn bộ đã hoàn thành.

**Trường hợp B:** IaC template đã sửa nhưng một bucket từng tạo ngoài IaC chưa được nhận diện. Pipeline xanh không chứng minh toàn bộ population. Cần bổ sung inventory, test effective policy cho bucket này và xử lý owner. Nếu evidence về độ bao phủ chưa đầy đủ, kết luận toàn scope **INCONCLUSIVE hoặc FAIL theo tiêu chí cụ thể**, không tự gán PASS.

### 17.5. Mốc thực tế và quyết định rủi ro

Nếu phát hiện dữ liệu khách hàng đã bị truy cập trái phép, ngoài action plan còn có thể cần incident response, đánh giá vi phạm dữ liệu và nghĩa vụ báo cáo theo luật/hợp đồng áp dụng. Việc chặn truy cập hiện tại **không xóa** các tác động đã xảy ra; remediation plan phải liên kết incident, audit evidence, quyết định của Legal/Privacy khi cần và việc thông báo hợp lệ.

## 18. Mẫu Action plan dạng YAML

Ví dụ sau mô tả record có thể đưa vào hệ thống quản trị; **không phải schema chuẩn hay script triển khai**. Các ID, mốc, trạng thái và con số chỉ phục vụ minh họa.

~~~yaml
action_plan:
  id: "REMEDIATION-PLAN-EXAMPLE-003"
  version: "1.0"
  finding_id: "F-STORAGE-023"
  service: "invoice-storage"
  environment: "production"
  created_at_utc: "2026-11-28T05:00:00Z"
  control_id: "DATA-ACCESS-05"
  objective: "Prevent unauthorized anonymous access to invoices"
  original_assessment: "FAIL"
  accountable_owner: "Invoice Service Owner"
  security_reviewer: "Security Assurance Team"
  risk_owner: "Customer Data Risk Owner"
  plan_status: "IN_PROGRESS"

finding:
  observed_condition: "Two production buckets allowed anonymous read"
  scope:
    source_inventory: "CMDB-CLOUD-INVENTORY-2026-11"
    affected_assets: ["invoice-bucket-a", "invoice-bucket-b"]
    population_check_required: true
  risk:
    category: "unauthorized-data-access"
    inherent_rating: "HIGH"
    residual_rating: "PENDING_REASSESSMENT"
    legal_contract_review_required: true
  root_causes:
    - "IaC template omitted public-access guardrail"
    - "Configuration drift alert not routed to asset owner"
    - "Inventory ownership mapping incomplete"

objectives_and_acceptance:
  - "All invoice buckets in verified scope deny anonymous reads"
  - "Authorized application functionality passes"
  - "IaC guardrail rejects disallowed public policies"
  - "Drift alert reaches accountable owner"
  - "Independent security retest passes for full scope"

interim_protection:
  id: "MIT-001"
  action: "Block public access and monitor access anomalies"
  owner: "Cloud Operations Lead"
  test_status: "PASS_ON_KNOWN_BUCKETS"
  coverage_limitation: "Full inventory reconciliation pending"
  evidence: "restricted/remediation/003/mitigation-test"
  expires_when: "Verified remediation and risk-owner approval"

actions:
  - id: "ACT-001"
    kind: "SCOPE"
    owner: "Cloud Inventory Lead"
    depends_on: []
    status: "IN_PROGRESS"
    deliverable: "Reconciled invoice bucket inventory"
    acceptance_test: "All cloud accounts and regions checked"
    required_evidence: ["inventory-export", "reconciliation-report"]
  - id: "ACT-002"
    kind: "CORRECTIVE"
    owner: "Platform Engineering"
    depends_on: ["ACT-001"]
    status: "PLANNED"
    deliverable: "Non-public storage baseline and IaC tests"
    acceptance_test: "Policy tests reject disallowed public configurations"
    required_evidence: ["reviewed-pr", "policy-test-output"]
  - id: "ACT-003"
    kind: "DEPLOYMENT"
    owner: "Service Engineering"
    depends_on: ["ACT-001", "ACT-002"]
    status: "PLANNED"
    deliverable: "Controlled rollout to verified production scope"
    acceptance_test: "Anonymous deny and authorized allow on each asset"
    required_evidence: ["change-record", "effective-policy-export"]
  - id: "ACT-004"
    kind: "PREVENTIVE_DETECTION"
    owner: "Security Monitoring"
    depends_on: ["ACT-001"]
    status: "PLANNED"
    deliverable: "Public-policy drift alert and owner routing"
    acceptance_test: "Synthetic alert reaches on-call within approved window"
    required_evidence: ["alert-test", "receipt-confirmation"]
  - id: "ACT-005"
    kind: "VERIFICATION"
    owner: "Security Assurance Reviewer"
    depends_on: ["ACT-003", "ACT-004"]
    status: "NOT_STARTED"
    deliverable: "Retest and independent closure decision"
    acceptance_test: "All acceptance criteria supported by evidence"
    required_evidence: ["retest-report", "reviewer-signoff"]

schedule:
  milestones:
    - id: "M0"
      name: "Containment verified"
      status: "COMPLETE_FOR_KNOWN_SCOPE"
    - id: "M1"
      name: "Scope reconciled"
      status: "PENDING"
    - id: "M2"
      name: "Fix deployed"
      status: "PENDING"
    - id: "M3"
      name: "Retest and closure decision"
      status: "PENDING"
  due_dates_source: "APPROVED_RISK_TREATMENT_RECORD"
  replan_requires_approval: true

governance:
  change_management_required: true
  rollback_plan_reference: "restricted/remediation/003/change-runbook"
  notify_on:
    - "missed-milestone"
    - "new-affected-asset"
    - "compensating-control-failure"
    - "security-incident"
  close_only_after_retest: true
  keep_original_finding_history: true

evidence:
  storage: "restricted-remediation-evidence"
  access: "need-to-know"
  artifact_metadata_required: true
  assessment_status: "RETEST_PENDING"
~~~

### 18.1. Đọc đúng trạng thái của mẫu

- `PASS_ON_KNOWN_BUCKETS` nghĩa là biện pháp tạm đã được kiểm tra trên **hai bucket đã biết**, không chứng minh phạm vi đã đầy đủ.
- `ACT-003: PLANNED` nghĩa là chưa có rollout; không thể tự ghi `original_assessment: PASS`.
- `ACT-005: NOT_STARTED` cho biết chưa có retest độc lập; plan chưa được đóng.
- Các due dates lấy từ hồ sơ risk treatment đã duyệt; bài học không bịa mốc SLA phổ quát.
- `assessment_status: RETEST_PENDING` phản ánh tình trạng chứng cứ chứ không phải cho phép tiếp tục vận hành vô điều kiện.

### 18.2. Link plan, change, exception và retest

Một tổ chức có thể triển khai YAML vào hệ thống GRC/ticketing hoặc dùng biểu mẫu khác. Những quan hệ tối thiểu cần giữ là **finding_id → action_ids → change_ids → evidence_ids → retest_id → closure decision**. Nếu có exception, gắn riêng **exception_id, expiry và decision owner** thay vì âm thầm thay deadline của finding.

## 19. Khi Action plan không đạt: Phát hiện và phục hồi kế hoạch

Kế hoạch hoàn hảo trên giấy vẫn có thể sai vì giả định thiếu, dependency thay đổi hoặc kỹ thuật có tác dụng phụ.

### 19.1. Các dấu hiệu cảnh báo sớm

- Action bị BLOCKED nhiều kỳ nhưng không có owner giải quyết.
- Replan liên tục bằng cách đổi due date mà không cập nhật residual risk.
- Mitigation đã hết hiệu lực, không ai test lại.
- Evidence thu từ staging được dùng để đóng finding production.
- Inventory có thêm asset ngoài scope nhưng action không đổi.
- Change record có deploy PASS, nhưng security retest vẫn FAIL.
- Người sửa fix cũng là người tự ký closure ở một finding rủi ro cao.
- Khắc phục hiện tượng lặp lại; root cause chưa được chứng minh.
- Một nhà cung cấp báo “đang xử lý” nhiều tháng, không có phương án thay thế.
- Đến kỳ audit không tìm được báo cáo evidence/version của lần đóng.

### 19.2. Quy trình khi phát hiện kế hoạch sai

1. **Chốt sự thật:** xác minh status thực tế, control đang có hiệu lực hay không, scope và timestamp.
2. **Đánh giá tác động mới:** thay đổi risk rating/priority khi exposure, dữ liệu hoặc threat thay đổi.
3. **Điều chỉnh bảo vệ tạm:** containment/compensating controls an toàn, có phép thử và owner.
4. **Xác định blocker/root cause mới:** phụ thuộc nào không còn hợp lệ, cần ai quyết định.
5. **Replan có version:** điều chỉnh tasks, nguồn lực, dependencies, deadlines, acceptance và approval.
6. **Cập nhật stakeholder:** báo nguy cơ vượt SLA/contract, kế hoạch thay thế và mốc review.
7. **Thực hiện và retest:** không chỉ đổi trạng thái cho khớp deadline.
8. **Giữ audit trail:** bản cũ, lý do thay đổi, approvals và findings chưa xử lý.

### 19.3. Khi nào cần đóng theo phương án khác?

Nếu tài sản thực sự được **decommission** và dữ liệu/đường truy cập đã được xử lý an toàn, có thể đóng theo trạng thái **RISK_REMOVED_BY_DECOMMISSION** hoặc tương đương theo chính sách, với evidence tắt dịch vụ, xóa/di chuyển dữ liệu, revoke secrets và kiểm tra dependency. Nếu **risk accepted**, dùng trạng thái governance riêng với expiry. Không gán cả hai thành “fixed by patch”.

## 20. Sai lầm phổ biến khi lập Action plan

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ mở ticket “fix security issue”, không mô tả tiêu chí. | Không ai biết khi nào đủ điều kiện đóng. | Problem statement, requirement/control ID và acceptance criteria. |
| Đặt một người “đầu mối” nhưng không có accountable owner. | Task bị bỏ quên khi đổi nhóm hoặc có blocker. | RACI, owner chịu kết quả và quyền escalation. |
| Sửa đúng một asset được scan mà không đối chiếu population. | Các asset khác vẫn lỗi và finding tái diễn. | Inventory, scope reconciliation và test toàn tập phù hợp. |
| Bỏ qua root cause, chỉ thay cấu hình tạm. | Pipeline hoặc quy trình tái tạo lỗi. | Corrective + preventive actions với bằng chứng riêng. |
| Lấy severity scanner làm mọi quyết định ưu tiên. | Không xét exploitability, dữ liệu, exposure và nghĩa vụ. | Risk-based prioritization có lý do và phê duyệt. |
| Cho phép risk acceptance thay cho fix nhưng vẫn báo control PASS. | Dashboard compliance thiếu trung thực. | Tách risk decision, control outcome và exception status. |
| Không có mitigation khi permanent fix chậm. | Rủi ro tiếp tục không kiểm soát trong thời gian chờ. | Interim protection có owner, test, expiry và monitoring. |
| Triển khai IAM/firewall fix không test chức năng. | Làm gián đoạn hệ thống trọng yếu hoặc mất khả năng phục hồi. | Staging, canary, business tests, rollback và change gate. |
| Kết thúc ở PR merged hoặc config deployed. | Không biết control đã hiệu lực trên production. | Independent security retest và reviewer approval. |
| Dùng kết quả scanner đã cũ sau khi kiến trúc đổi. | Bằng chứng không còn đại diện. | Evidence freshness, change triggers và retest. |
| Ghi “90% done” nhưng không có milestones. | Tiến độ không thể xác minh; blocker không nổi lên. | Deliverables có điều kiện đạt và mốc rõ. |
| Gia hạn deadline nhưng không ghi lý do/approval. | Giấu overdue và làm mất trách nhiệm. | Original due date, change history, risk reassessment. |
| Trộn các finding vào một change rồi đóng hết. | Không có evidence cho từng mục tiêu kiểm soát. | Many-to-many mapping và acceptance từng finding. |
| Dùng thông tin nhà cung cấp “đã khắc phục” thay vì xác minh tenant. | Chưa biết sản phẩm/hệ thống của mình đã nhận fix. | Vendor evidence + customer-side version/config/function tests. |
| Không kiểm tra recurrence sau closure. | Cùng một lỗi tái xuất hiện mà không bị phát hiện. | Monitoring trigger, regression test và control owner review. |

## 21. Checklist nghiệm thu một Remediation Action plan

Trước khi chấp nhận kế hoạch ở mức **đã sẵn sàng triển khai**, reviewer kiểm tra:

1. **Nguồn và finding:** Có finding ID, nguồn quan sát, control/requirement và evidence ban đầu đáng tin?
2. **Problem statement:** Có mô tả trạng thái hiện tại, tiêu chí mong đợi và tác động rõ?
3. **Scope:** Tất cả asset, account, service, region, loại dữ liệu và stakeholder liên quan được đối chiếu?
4. **RCA:** Nguyên nhân đã được phân tích với evidence, không chỉ giả định?
5. **Risk prioritization:** Có exposure, impact, likelihood, nghĩa vụ và rủi ro còn lại?
6. **Options:** Đã so sánh sửa ngay, mitigation, dừng chức năng, thay vendor hoặc risk treatment phù hợp?
7. **Ownership:** Có action owner, accountable owner, người duyệt và verifier đúng quyền?
8. **Tasks:** Mỗi action có scope, deliverable, acceptance criteria, evidence và deadline?
9. **Dependencies:** Có predecessor, change window, nguồn lực, milestone và blocker/escalation?
10. **Interim protection:** Nếu fix chậm, biện pháp tạm có test, owner, expiry, monitoring?
11. **Change safety:** Có kế hoạch test, rollback/contingency, giám sát và communication?
12. **Evidence:** Có raw/source metadata, deployment record, test results, version và storage kiểm soát quyền?
13. **Verification:** Có independent retest theo control gốc và nghiệp vụ, không chỉ xác nhận ticket?
14. **Governance:** Ngoại lệ, risk acceptance, legal/contract constraints được phân biệt và phê duyệt đúng cơ chế?
15. **Progress:** Reporting không che overdue, replan history, missing evidence và risk drift?
16. **Closure:** Có kết quả PASS/FAIL/INCONCLUSIVE theo từng tiêu chí, sign-off và lý do đóng?
17. **Prevention:** Có cơ chế giám sát tái diễn, regression test, ownership và update baseline?

### Câu hỏi tự đánh giá

Một finding phát hiện API cho phép người dùng đọc dữ liệu ngoài quyền. Nhóm phát triển đã merge PR sửa authorization, test đơn vị PASS và đóng ticket. Tuy nhiên, một phiên bản ứng dụng cũ vẫn chạy ở cluster dự phòng; security test chỉ chạy trên staging, còn dữ liệu audit tại production không đủ xác định mọi đường API đã kiểm tra.

**Câu hỏi:** Action plan đã hoàn thành chưa? Hành động tiếp theo nên là gì?

**Gợi ý:** **Chưa có bằng chứng đủ để đóng verified remediation.** Cần đối chiếu deployment inventory trên primary và standby, triển khai bản sửa đúng phạm vi, kiểm thử authorization cả request hợp lệ và trái quyền trên từng đường/API quan trọng được phép thử, xác minh audit/logging, bổ sung bằng chứng nguồn và reviewer sign-off. Nếu còn cluster cũ hoặc không đủ evidence, trạng thái nên là IN_PROGRESS/VERIFYING với finding còn mở; trong lúc chờ, duy trì mitigation có kiểm chứng và đánh giá rủi ro người dùng đang bị ảnh hưởng.

**Action plan chỉ thực sự tạo giá trị remediation khi nó biến phát hiện bảo mật thành công việc có thể thực thi, ràng buộc đúng người và thời gian, xử lý cả nguyên nhân gốc lẫn rủi ro tức thời, sau đó chứng minh bằng kiểm thử và evidence rằng mục tiêu kiểm soát đã được đáp ứng. “Đã triển khai” là một cột mốc; “đã kiểm chứng giải quyết rủi ro” mới là cơ sở để đóng vấn đề một cách có trách nhiệm.**
