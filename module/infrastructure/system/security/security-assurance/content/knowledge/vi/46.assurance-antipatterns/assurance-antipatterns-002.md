# Thu thập evidence hình thức: Anti-pattern trong Security Assurance và cách khắc phục

**Thu thập evidence hình thức** là anti-pattern trong đó đội dự án hoặc tổ chức chú trọng **có đủ file, ảnh chụp màn hình, dấu tick, biểu mẫu và trạng thái PASS** hơn là chứng minh security control thực sự đáp ứng mục tiêu bảo mật được giao. Một gói tài liệu có thể rất dày, được sắp xếp đẹp và có chữ ký, nhưng vẫn **không trả lời được hệ thống có bảo vệ đúng tài sản, đúng điều kiện và trong đúng khoảng thời gian cần đánh giá hay không**.

Trong chương **Anti-pattern assurance** của module **SECURITY_SECURITY_ASSURANCE**, bài học xem hiện tượng này như một vấn đề cả về kỹ thuật lẫn quản trị. Module hướng đến **đánh giá có bằng chứng** từ phân tích rủi ro, yêu cầu bảo mật, security controls đến kiểm thử, audit và khắc phục phát hiện, nhằm vận hành security assurance liên tục trong phát triển và vận hành. Nếu chứng cứ chỉ phục vụ “điền đủ ô”, toàn bộ chuỗi lập luận đó có thể đứt, khiến tổ chức có cảm giác an toàn sai lệch.

> **Thông điệp chính:** Thu thập được evidence không đồng nghĩa đã chứng minh control đạt; một hiện vật chỉ có giá trị khi **phù hợp claim, có nguồn đáng tin, đúng phạm vi, đúng thời điểm, đủ để kiểm chứng và được diễn giải trung thực**.

Ví dụ: Auditor hỏi liệu **toàn bộ tài khoản đặc quyền production** có được rà soát quyền trong quý III hay không. Nhóm vận hành nộp một ảnh dashboard có nút “Access review completed” và một file Excel với chữ “Done”. Hai hiện vật này có thể chứng minh **một hoạt động đã được ghi nhận**. Chúng chưa chứng minh population đầy đủ, người phê duyệt đủ thẩm quyền, quyết định được thực hiện, quyền dư thừa đã được thu hồi, hoặc tài khoản cấp qua kênh khẩn cấp có được đưa vào đánh giá. Nếu đội vẫn ghi “100% compliant”, đó là ví dụ điển hình của **evidence theater**: hình thức của sự bảo đảm che đi phần chưa được chứng minh.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Nhận diện **thu thập evidence hình thức** và phân biệt với thu thập có mục tiêu phục vụ assurance.
2. Mô tả dấu hiệu của evidence thiếu **relevance, sufficiency, reliability, completeness, accuracy, integrity, timeliness và traceability**.
3. Giải thích vì sao screenshot, báo cáo scan sạch, ticket Done hoặc audit checklist được ký **không tự chứng minh** hiệu quả bảo mật.
4. Phân biệt evidence cho **thiết kế control**, **triển khai control** và **hiệu quả vận hành**; tránh đưa ra claim mạnh hơn dữ liệu.
5. Kiểm tra population, sampling, thời kỳ, tính độc lập của nguồn, phản chứng và chất lượng pipeline thu thập.
6. Lập **evidence plan** bắt đầu từ security objective, criteria, claim và threat/risk thay vì bắt đầu từ danh sách file.
7. Thiết kế hồ sơ evidence có metadata, đường truy xuất nguồn, quyền kiểm tra, giới hạn và triggers đánh giá lại.
8. Đề xuất cách xử lý evidence gap, sai lệch và finding mà không làm đẹp compliance score.
9. Phân tích các tình huống IAM, cloud configuration, logging và remediation để đưa ra kết luận assurance trung thực.

---

## 2. “Evidence hình thức” là gì?

Một hiện vật có thể là bằng chứng hữu ích nếu nó được dùng đúng mục đích. Anti-pattern xuất hiện khi **việc sở hữu hiện vật bị đánh đồng với việc chứng minh một tuyên bố**.

Ba ví dụ:

- **Có chính sách mật khẩu**: chứng minh một văn bản chính sách tồn tại và được ban hành theo hồ sơ. Nó không tự chứng minh mọi tài khoản áp dụng chính sách đó.
- **Có một báo cáo vulnerability scan**: chứng minh một công cụ đã thực hiện phép kiểm tra theo cấu hình và phạm vi nhất định. Nó không tự chứng minh toàn bộ asset production được scan hoặc không có lỗ hổng mới.
- **Có screenshot “Encryption enabled”**: gợi ý trạng thái của một resource tại thời điểm chụp. Nó không tự chứng minh backup, replica, object storage và tất cả đường truy cập dữ liệu đã được bảo vệ theo security requirement.

Vấn đề không nằm ở định dạng PDF, ảnh hay spreadsheet. **Bất cứ định dạng nào cũng có thể chứa evidence tốt hoặc yếu** tùy claim và phương pháp kiểm chứng. Screenshot từ giao diện quản trị có thể giúp auditor xác nhận một cấu hình khi kèm resource ID, nguồn, mốc thời gian và kiểm tra chéo; nhưng một screenshot không đủ để chứng minh hiệu quả vận hành trong sáu tháng nếu không có dữ liệu lịch sử.

### 2.1. Anti-pattern này thường được gọi bằng những tên nào?

- **Evidence theater**: diễn ra hoạt động trông như chứng minh, nhưng thiếu thực chất.
- **Checkbox compliance**: mục tiêu trở thành đánh dấu đủ yêu cầu trên biểu mẫu.
- **Audit-driven paperwork**: tài liệu được gom sát ngày audit để “đủ hồ sơ”, thay vì thu thập từ vận hành.
- **Cargo-cult assurance**: sao chép hình thức của một quy trình assurance mà bỏ mất cơ sở lập luận.
- **Metrics gaming**: tối ưu tỷ lệ xanh, số lượng test, số tài liệu hoặc số ticket đóng thay vì hiệu quả control.

Các tên gọi giúp nhận diện mô thức, **không phải nhãn để kết tội con người**. Nhiều tình huống xuất phát từ requirements mơ hồ, thiếu công cụ, áp lực deadline, phân công owner không rõ hoặc không có quy tắc xác nhận tính đầy đủ của dữ liệu. Cách sửa tốt nhất là thiết kế lại hệ thống đánh giá.

## 3. Vì sao anti-pattern này nguy hiểm?

Việc thu thập evidence hình thức tạo **rủi ro nhận thức sai**: người ra quyết định tin rằng nguy cơ đã được kiểm soát trong khi thông tin thực tế chưa đủ.

### 3.1. Hậu quả đối với security assurance

| Hậu quả | Cơ chế xảy ra | Ví dụ |
|---|---|---|
| **False assurance** | Báo cáo PASS dù control chưa được kiểm chứng | MFA có cấu hình nhưng luồng emergency có thể bypass |
| **Sai ưu tiên rủi ro** | Dashboard che thiếu sót ở tài sản quan trọng | 99% asset xanh nhưng 1% còn lại là tài khoản quản trị toàn tổ chức |
| **Không phát hiện drift** | Chỉ lưu snapshot trước audit | Storage được mở public sau thời điểm chụp |
| **Đóng finding quá sớm** | Ticket/PR Done thay cho retest | Bản vá chưa deploy tới region dự phòng |
| **Bỏ qua hành vi vận hành** | Chỉ chứng minh policy tồn tại | Access review được ký nhưng quyền dư thừa chưa thu hồi |
| **Không truy vết được quyết định** | Báo cáo không gắn version, asset, source | Không biết scan từ build nào và có đúng production không |
| **Mất khả năng phản biện** | Chỉ chọn hiện vật ủng hộ claim | Một pentest finding trái ngược không có trong audit pack |
| **Tăng nguy cơ lộ dữ liệu** | Sao chép log, quyền và secrets vào gói audit rộng | Dữ liệu nhạy cảm bị lan truyền qua email hoặc thư mục chia sẻ |
| **Lãng phí nguồn lực** | Thu thập hàng trăm file không trả lời tiêu chí | Nhiều giờ chụp ảnh thủ công, vẫn phải audit lại |

Đáng chú ý, việc không đủ evidence **không tự chứng minh control sai**. Nó dẫn đến kết luận thích hợp là **NOT DEMONSTRATED / UNKNOWN** đối với phần chưa kiểm tra. Nếu tồn tại bằng chứng trái claim thì mới có cơ sở cho **CONTRADICTED / FAIL**. Phân biệt hai tình huống giúp cả audit lẫn remediation chính xác.

### 3.2. Lời cảnh báo về “cảm giác chắc chắn”

Một release có 500 test PASS nhưng thiếu kiểm tra role support ở endpoint export không thể tuyên bố “không có truy cập trái quyền”. Một công ty có 100 policy PDF cũng không tự có 100 control hoạt động hiệu quả. **Khối lượng hiện vật không phải mức độ bảo đảm**.

## 4. Dấu hiệu nhận biết evidence hình thức

Có thể kiểm tra nhanh một gói evidence bằng bảng sau:

| Dấu hiệu | Câu hỏi phản biện | Hệ quả cần xem xét |
|---|---|---|
| Tên file chung chung như “security-proof-final.pdf” | Evidence thuộc control, asset, kỳ và release nào? | Không truy vết được |
| Ảnh dashboard không có mốc thời gian/resource | Chứng minh trạng thái nào, tại thời điểm nào? | Có thể là ảnh cũ hoặc sai môi trường |
| Ticket ghi “Done” | Có retest, nghiệm thu và đúng deployment chưa? | Khả năng đóng sớm |
| Checklist có 100% dấu tick | Tiêu chí PASS cụ thể và dữ liệu nguồn là gì? | Checkbox compliance |
| Scan report không có asset inventory | Có biết các asset bị bỏ sót và credential scan? | Coverage không đáng tin |
| Không có nguyên liệu kiểm thử | Có input, expected/actual, run ID và công cụ không? | Khó kiểm chứng lại |
| Policy/approval được coi là control effectiveness | Có bằng chứng triển khai và vận hành? | Đánh đồng thiết kế với hiệu lực |
| Chỉ nộp các lần test PASS | Những FAIL và finding đã được xử lý ra sao? | Selection bias |
| Một kết quả được tái dùng nhiều kỳ | Điều gì chứng minh evidence còn hiệu lực? | Stale evidence |
| Không có owner/reviewer | Ai chịu trách nhiệm chất lượng dữ liệu và kết luận? | Không có accountability |
| Không ghi exception hay residual risk | Sai lệch được phê duyệt đúng scope/hạn chưa? | Làm đẹp tỷ lệ tuân thủ |
| Nguồn có thể bị mất mà dashboard vẫn xanh | Collector có health check và đối soát nguồn? | False negative kéo dài |

**Một hiện vật yếu không nhất thiết vô giá trị.** Cách đúng là xác định nó **hỗ trợ được đến đâu**, còn thiếu điều kiện gì và cần thêm evidence gì, thay vì vứt bỏ tất cả hoặc chấp nhận vô điều kiện.

## 5. Các nhóm anti-pattern phổ biến

### 5.1. “Có tài liệu” được hiểu thành “đã tuân thủ”

Bằng chứng được nộp: policy, SOP, ma trận RACI, bản thiết kế security architecture.

Lỗ hổng: chúng chủ yếu chứng minh **thiết kế hoặc quyết định quản trị**, chưa xác nhận control được triển khai trên mọi hệ thống và vận hành theo yêu cầu.

**Cách khắc phục:** bổ sung evidence deployment, test control và dữ liệu vận hành, với mapping rõ từ từng yêu cầu tới thiết kế, thực thi, kết quả kiểm tra và kỳ đánh giá.

### 5.2. “Snapshot đẹp” thay cho trạng thái theo thời gian

Một ảnh cho thấy logging đang bật hoặc bucket hiện private.

Lỗ hổng: nếu claim nói “trong toàn bộ quý”, ảnh tại một mốc không chứng minh có hay không một khoảng drift trước đó.

**Cách khắc phục:** bổ sung change history, audit event, state samples có mốc thời gian và kiểm tra nguồn dữ liệu. Khi không có lịch sử, **nêu giới hạn** và không tạo giả bằng chứng cho khoảng trống.

### 5.3. “Công cụ không báo” được hiểu thành “không có vấn đề”

Scanner không tìm thấy CVE hoặc SIEM không cảnh báo.

Lỗ hổng: scanner có thể thiếu asset/credential/rule; SIEM có thể mất dữ liệu hoặc alert bị tắt.

**Cách khắc phục:** xác minh coverage và source health, kiểm thử một vi phạm synthetic được phép, đối chiếu trạng thái bằng nguồn khác.

### 5.4. “Ticket được đóng” thay cho “lỗi đã được xác minh khắc phục”

Bản vá có thể đã merge nhưng runtime vẫn chạy image cũ hoặc cùng lớp lỗi còn tồn tại trên đường khác.

**Cách khắc phục:** yêu cầu deployment proof, retest tiêu chí gốc, negative/positive tests, regression, reviewer và scope coverage trước trạng thái VERIFIED CLOSED.

### 5.5. “100% theo danh sách đã có” thay cho “đã bao phủ toàn hệ thống”

Đội IAM export 40 tài khoản từ một IdP nhưng quên một cloud account và emergency principal.

**Cách khắc phục:** định nghĩa population theo nhiều nguồn, kiểm tra quyền kế thừa, inventory drift, sampling unit, số đối tượng chưa thu thập và giới hạn suy luận.

### 5.6. “Copy–paste evidence” cho nhiều control

Một báo cáo penetration test được gắn vào các claim về authorization, mã hóa, DR và access review mà không nêu phép thử nào hỗ trợ từng claim.

**Cách khắc phục:** dùng evidence mapping có lý do; cùng một tài liệu có thể chứa nhiều chứng cứ khác nhau nhưng **mỗi liên kết evidence–claim phải được giải thích và kiểm tra**.

### 5.7. “Bằng chứng gián tiếp” được nâng thành kết luận trực tiếp

Có email của vendor xác nhận họ “tuân thủ chuẩn an ninh”, nhưng không có scope, ngoại lệ, thời kỳ hoặc các phần trách nhiệm thuộc khách hàng.

**Cách khắc phục:** đánh giá báo cáo độc lập, phạm vi/cửa sổ, controls được bao phủ, shared responsibility và phép thử tích hợp của tổ chức.

### 5.8. “Không có FAIL” do bỏ các lần thử thất bại

Chỉ export report của pipeline cuối cùng PASS, giấu ba lần security test FAIL trước đó; hoặc ghi “all fixed” dù một finding chưa retest.

**Cách khắc phục:** giữ lịch sử test run, phân tích nguyên nhân, liên kết fix và retest; người đánh giá biết phạm vi nào từng FAIL và được giải quyết bằng chứng nào.

### 5.9. “Số lượng kiểm tra” thay cho chất lượng kiểm tra

KPI đếm số report, số checkbox, số lần scan hoặc số test case mà không đánh giá liên quan/rủi ro.

**Cách khắc phục:** đo coverage của claims, asset, threat và kỳ; số phần chưa chứng minh, phản chứng mở và thời gian tới verified remediation.

### 5.10. “Tool-generated = không cần review”

CI/CD, SIEM, CSPM hay control-as-code có thể tự tạo kết quả, nhưng rule sai, API thay đổi, inventory không đủ hoặc collector thiếu quyền vẫn khiến report không đáng tin.

**Cách khắc phục:** kiểm thử evaluator, data-quality gates, version hóa rule, kiểm tra độc lập và có người chịu trách nhiệm kết luận.

### 5.11. “Ngoại lệ = PASS”

Một host chưa được vá nhưng có risk acceptance, dashboard cộng host đó vào “compliant”.

**Cách khắc phục:** tách PASS, FAIL, EXCEPTED, UNKNOWN, NOT APPLICABLE. Ngoại lệ là **quyết định có phạm vi, thời hạn và điều kiện**, không phải bằng chứng control đã đạt.

### 5.12. “Chuẩn bị trước audit” thay cho kiểm soát liên tục

Một tháng trước audit, đội gấp rút chạy scan, chụp cấu hình và xin chữ ký; hồ sơ chỉ phản ánh vài ngày gần nhất.

**Cách khắc phục:** thu thập bằng chứng như một phần của SDLC và vận hành; có nguồn, thời kỳ, retention, theo dõi drift, CAP và review liên tục.

## 6. Bài kiểm tra trọng tâm: evidence hỗ trợ claim nào?

Trước khi thu thập, cần **viết claim có thể kiểm tra**.

**Claim yếu:** “Hệ thống của chúng tôi bảo mật tốt.”

**Claim có phạm vi:** “Trong production release R, các API đọc hồ sơ khách hàng thuộc inventory phiên bản I thực thi kiểm tra quyền theo tenant và object đối với những vai trò đã liệt kê, theo requirement AUTHZ-01, tại thời điểm triển khai và trong cửa sổ quan sát được mô tả.”

Với claim như vậy, đội bảo mật mới xác định được evidence cần:

- Danh sách endpoint đầy đủ với nguồn kiểm kê.
- Policy hoặc ma trận quyền có tiêu chí.
- Code/config/deployment proof đúng release.
- Security test cho allowed/denied/cross-tenant, role và đường export.
- Bằng chứng vận hành hoặc giám sát trong khoảng thời gian cần kết luận.
- Kết quả finding, exception, retest và giới hạn coverage.

Đây là nguyên tắc **claim-driven evidence collection**, trái với **file-driven collection**: thu thập một đống file có sẵn rồi tìm cách gắn nhãn “đã chứng minh”.

### 6.1. Claim – Argument – Evidence

Một assurance case tốt thường có:

- **Claim:** điều cần chứng minh, với criteria, scope, thời kỳ.
- **Argument:** lý do mà những control và claim con cùng hỗ trợ claim cha.
- **Evidence:** dữ liệu cụ thể về thiết kế, thực thi và vận hành.
- **Context, assumptions và limitations:** điều kiện và giới hạn suy luận.
- **Counterevidence/defeaters:** điều có thể khiến kết luận sai hoặc làm yếu lập luận.

~~~mermaid
flowchart TD
    A["Security objective / risk"] --> B["Claim G0 có scope và criteria"]
    B --> C["Argument: các điều kiện bắt buộc"]
    C --> D["Claim G1: thiết kế control phù hợp"]
    C --> E["Claim G2: triển khai trên đúng population"]
    C --> F["Claim G3: vận hành có hiệu lực trong kỳ"]
    D --> G["Design review + threat mapping"]
    E --> H["Runtime config + negative security tests"]
    F --> I["Logs + sampling + operating review"]
    G --> J["Đánh giá relevance / sufficiency / freshness"]
    H --> J
    I --> J
    J --> K["Findings, defeaters, assumptions"]
    K --> L["Kết luận assurance có phạm vi và giới hạn"]
~~~

Một gói tài liệu có đủ G, H, I vẫn yếu nếu không giải thích được **tại sao** chúng hỗ trợ các claim con, cách xác định population và các phản chứng nào chưa giải quyết.

## 7. Phân biệt design, implementation và operating effectiveness

Một nguyên nhân lớn của evidence hình thức là **dùng bằng chứng của một giai đoạn để khẳng định giai đoạn khác**.

| Lớp đánh giá | Câu hỏi | Bằng chứng hữu ích | Không thể tự suy ra |
|---|---|---|---|
| **Design adequacy** | Control được thiết kế để xử lý threat/requirement đúng không? | Threat model, design review, policy, data flow | Control đã thực sự chạy |
| **Implementation effectiveness** | Thiết kế được triển khai đúng scope và release không? | Config export, code review, policy evaluation, runtime test | Control vận hành đúng trong cả thời kỳ |
| **Operating effectiveness** | Control được vận hành nhất quán qua các tình huống và khoảng thời gian cần xét không? | Event history, samples, logs, workflow approvals và retest | Không có ngoại lệ ngoài dữ liệu đã quan sát |
| **Assurance conclusion** | Tập lập luận và evidence đủ để hỗ trợ claim nào? | Cross-check, coverage analysis, reviewer và risk disposition | Chứng nhận an toàn tuyệt đối vĩnh viễn |

**Ví dụ về access review:**
- SOP “định kỳ rà soát quyền” chứng minh **thiết kế quy trình**.
- Workflow đã cấu hình gửi yêu cầu review tới owner chứng minh **triển khai**.
- Hồ sơ một quý cho thấy owner ra quyết định, các quyền thừa được thu hồi và có bằng chứng hậu kiểm mới hỗ trợ **hiệu quả vận hành trong quý đó**.

Tương tự, **backup job success** chưa chứng minh dữ liệu **restore** được hoặc đáp ứng RTO/RPO: phải thử phục hồi, đối chiếu integrity và nghiệp vụ theo kịch bản thích hợp.

## 8. Tiêu chí chất lượng của evidence

Một evidence item đáng tin có thể được đánh giá theo nhiều chiều:

| Tiêu chí | Câu hỏi kiểm tra | Lỗi hình thức thường gặp |
|---|---|---|
| **Relevance – phù hợp** | Hiện vật hỗ trợ trực tiếp control/claim nào? | Scan TLS dùng chứng minh authorization |
| **Sufficiency – đủ** | Có đủ evidence theo rủi ro, tập đối tượng và kỳ không? | Một screenshot thay toàn bộ quý |
| **Completeness – đầy đủ nguồn/tập** | Population có bao gồm mọi asset/role/source cần thiết? | Cloud account mới không được scan |
| **Reliability – tin cậy** | Nguồn, phương pháp và người tạo có đáng tin? | Report tự điền không có dữ liệu gốc |
| **Accuracy – chính xác** | Query, bộ lọc, timezone, expected/actual và nhãn có đúng? | Export bị lọc mất tài khoản exception |
| **Integrity – toàn vẹn** | Có thể phát hiện sửa/cắt dữ liệu sau thu thập? | File chỉnh tay không có version và audit trail |
| **Timeliness – đúng thời điểm** | Evidence đúng release, kỳ và điều kiện đang đánh giá? | Test trước thay đổi IAM được dùng sau release |
| **Traceability – truy vết** | Có thể lần từ claim tới hiện vật nguồn và người xác minh? | Attachment không có ID hoặc scope |
| **Independence – độc lập phù hợp** | Có điểm lỗi chung giữa các nguồn hoặc thiên lệch tự đánh giá? | Ba dashboard lấy cùng một log thiếu dữ liệu |
| **Reproducibility – tái kiểm tra** | Có thể chạy lại/đối chiếu phép thử, với quyền hợp lệ? | Chỉ có nhãn PASS, không biết test case |

Không phải mỗi evidence đều cần giá trị tối đa trên mọi chiều. Mức bằng chứng yêu cầu phụ thuộc **loại claim và mức rủi ro**, nhưng phải đánh giá các điểm yếu trọng yếu có thể làm thay đổi kết luận.

### 8.1. Một nguyên tắc quan trọng

**Không được nâng claim cao hơn phần evidence thực sự bao phủ.** Một test đúng trên 20 endpoint có thể hỗ trợ kết luận “20 endpoint được kiểm tra có kết quả X”; nó không hỗ trợ câu “mọi endpoint production đạt” nếu còn endpoint chưa được xác minh.

### 8.2. Lỗi “chúng tôi có hash nên bằng chứng đáng tin”

Hash hoặc chữ ký có thể giúp kiểm tra file không bị đổi sau khi ghi nhận hoặc đúng cơ chế xác thực được thiết kế. Nhưng **hash không chứng minh dữ liệu đầu vào là đầy đủ, chính xác hoặc phản ánh đúng production**.

Cần kiểm tra cả **nguồn gốc và quá trình tạo evidence**, không chỉ tính toàn vẹn của file cuối.

## 9. Population completeness: lỗi làm nhiều gói evidence vô giá trị

Một báo cáo “100% MFA compliant” chỉ có ý nghĩa nếu **mẫu số** là toàn bộ population thuộc requirement.

Ví dụ:

- Danh sách từ IdP có 120 user nhưng còn 5 local-admin account.
- Một cloud account production chưa onboard vào hệ thống kiểm tra.
- Service account và human interactive identity được trộn chung, áp rule không phù hợp.
- Tài khoản break-glass tồn tại nhưng không nằm trong nhóm được kiểm tra.
- Một API gateway route không nằm trong OpenAPI inventory.
- Một vùng dự phòng chạy image hoặc policy khác production chính.

### 9.1. Cách xây và xác minh population

1. Xác định **đơn vị đánh giá**: account, principal, role, VM, bucket, endpoint, ticket hay giao dịch.
2. Định nghĩa **điều kiện bao gồm/loại trừ**, môi trường, phiên bản và thời gian.
3. Chọn **nguồn inventory chính** và nguồn đối chiếu độc lập khi phù hợp.
4. So số lượng dự kiến, thực thu, không thu thập được và trường hợp exception.
5. Kiểm tra pagination, API permissions, cloud account/region và nguồn dữ liệu mới.
6. Đối chiếu identity/asset được tạo/xóa trong kỳ, không chỉ snapshot cuối kỳ.
7. Ghi rõ phần UNKNOWN và không loại khỏi số liệu chỉ để nâng tỷ lệ PASS.

### 9.2. Ví dụ về số liệu dễ đánh lừa

Một tổ chức có 150 tài khoản đặc quyền theo inventory đã xác nhận. Công cụ thu được 140 tài khoản, trong đó 138 PASS và 2 FAIL.

- **Tỷ lệ PASS trong tập đã thu:** 138/140.
- **Tập chưa đánh giá:** 10/150.
- **Không thể kết luận:** “98,6% toàn bộ tài khoản production đáp ứng và không có vấn đề đáng kể.”
- **Kết luận có trách nhiệm:** 138 tài khoản được quan sát đạt; 2 vi phạm; 10 chưa có kết luận. Control tổng thể chưa được chứng minh đạt cho population nếu criteria yêu cầu bao phủ tất cả.

Nếu 10 tài khoản chưa thu là quyền đặc biệt mức cao, ảnh hưởng rủi ro có thể không tương ứng với số lượng chỉ 10/150. **Không dùng trung bình số lượng để che sai lệch ở tài sản trọng yếu.**

## 10. Thời kỳ đánh giá: snapshot không thay cho history

Một evidence item cần nêu nó mô tả **trạng thái tại mốc T** hay **hoạt động trong khoảng T0–T1**.

| Claim | Evidence có thể phù hợp | Evidence chưa đủ |
|---|---|---|
| Storage private tại T | Config state + resource ID tại T, kiểm tra đường truy cập liên quan | Ảnh không có resource/timestamp |
| Storage không public trong quý | History của policy/config và source coverage suốt quý, đánh giá drift | Một snapshot cuối quý |
| MFA được enforce lúc login | Cấu hình IdP và thử đường đăng nhập trong scope | Checkbox “MFA required” không đối chiếu đường đặc biệt |
| Quyền được review trong quý | Review decisions, ticket, population lịch sử, hành động thu hồi | Email mời họp hoặc biểu mẫu rỗng |
| Audit log đầy đủ trong tháng | Source inventory, event coverage, pipeline health, history, tests | Dashboard chỉ báo tổng sự kiện cuối tháng |
| Khôi phục đáp ứng RTO/RPO | Kết quả diễn tập/sự cố đúng kịch bản, đo T0/T1 và kiểm tra dữ liệu | Job backup xanh |

### 10.1. Không phục hồi bằng chứng lịch sử bằng lời khẳng định hiện tại

Giả sử logging pipeline ngừng 12 giờ trong tháng 9. Tháng 10, đội vận hành sửa và tạo synthetic event thành công. Bằng chứng tháng 10 hỗ trợ **control hiện hoạt động**, nhưng không chứng minh log tháng 9 đã được thu đầy đủ.

Nếu nguồn độc lập không khôi phục được khoảng trống, cần giữ **historical evidence gap**, điều tra tác động và cập nhật assurance/audit/risk register. Không được sửa kết quả cũ thành PASS vì “hiện nay đã ổn”.

### 10.2. Evidence freshness và invalidation

Một evidence có thể chính xác khi tạo nhưng không còn đại diện sau:
- Thay release, API route, role hoặc IdP.
- Đổi KMS, network, logging schema, cloud account.
- Phát hiện lỗ hổng mới ảnh hưởng assumption.
- Vendor thay dịch vụ/trách nhiệm.
- Đến kỳ đánh giá mới cần operating evidence.
- Một test rule hoặc collector được phát hiện sai.

Evidence plan cần có **review triggers**; chỉ ghi “valid forever” mà không có cơ sở là anti-pattern.

## 11. Lấy mẫu: đừng biến sample thành toàn bộ population

Khi dữ liệu rất lớn, audit có thể dùng **sampling**. Evidence hình thức thường bỏ qua phương pháp lấy mẫu và chỉ trình bày kết quả tốt.

### 11.1. Những thông tin bắt buộc của mẫu

- **Population:** tập đối tượng nào, trong thời kỳ nào?
- **Sampling unit:** user, access grant, transaction, change ticket hay log event?
- **Selection method:** random, stratified, risk-based, judgmental hay toàn bộ?
- **Sample size:** bao nhiêu, vì sao phù hợp với mục tiêu?
- **Coverage of high-risk segments:** có admin, break-glass, multi-region, ngoại lệ?
- **Observed exceptions:** số lượng, mức rủi ro, cách xác minh và mở rộng kiểm tra.
- **Inference limits:** có được phép suy rộng thống kê hay chỉ dùng để phát hiện?

### 11.2. Ví dụ audit cấp quyền

Một đội chọn 20 ticket mới nhất trong 1.200 thay đổi quyền và thấy cả 20 đều có approval. Kết quả chỉ chứng minh **20 ticket đó có bằng chứng approval**, không tự chứng minh toàn bộ 1.200 trường hợp đều đúng. Ticket cũ, emergency grants và thay đổi trực tiếp ngoài workflow có thể bị bỏ qua.

Nếu mục tiêu là ước lượng tỷ lệ sai lệch của population, cần phương pháp lấy mẫu xác suất cùng giả định phù hợp và cách xử lý ngoại lệ. Nếu mục tiêu là phát hiện rủi ro cao, có thể dùng risk-based sampling, nhưng không tự suy tỷ lệ mẫu thành xác suất sai lệch trên toàn tập.

**Không trộn hai mục đích** để kết luận: một mẫu có chủ đích rất hữu ích cho việc tìm lỗi, nhưng chưa chắc đại diện thống kê.

## 12. Provenance và chain of custody: nguồn bằng chứng phải kiểm tra được

**Provenance** cho biết evidence được tạo ở đâu, bằng cách nào, từ dữ liệu/phiên bản nào và ai chịu trách nhiệm. **Chain of custody** mô tả sự bàn giao/bảo quản có kiểm soát, đặc biệt quan trọng với chứng cứ incident, điều tra hoặc nghĩa vụ pháp lý.

Một evidence record có thể lưu:

- Source system, API/query, công cụ và rule version.
- Người hoặc service principal thu thập, quyền/điều kiện thu thập.
- Asset/identity/resource IDs, environment, region, release.
- Timestamp lấy dữ liệu và **observation window**.
- Input/expected/actual đối với test; bộ lọc/pagination đối với export.
- Raw artifact reference và bản tổng hợp đã xử lý.
- Hash/version/retention/access control khi phù hợp.
- Những thao tác biến đổi/lọc/redact được thực hiện.
- Reviewer và kết luận trong phạm vi nào.

### 12.1. Kiểm soát dữ liệu nhạy cảm

Bằng chứng bảo mật có thể chứa:
- Danh sách tài khoản quản trị hoặc principal có quyền cao.
- Network diagram, internal hostnames và đường truy cập nhạy cảm.
- Log chứa IP, identity, hành động và dữ liệu cá nhân.
- Vulnerability details, cấu hình secrets hoặc token.
- Báo cáo đánh giá nhà cung cấp có hạn chế chia sẻ.

Không nên “gom càng nhiều càng tốt” vào một thư mục ai cũng xem được. Thu thập **tối thiểu cần thiết cho claim**, gắn ID để truy cập ở kho hạn chế quyền, có retention và audit trail. Nếu cần redaction, phải bảo đảm phần bị ẩn không phá khả năng đánh giá; khi cần, reviewer có quyền phù hợp phải kiểm tra raw evidence riêng.

### 12.2. Một CSV sạch có thể che lỗi nguồn

Nếu file được xuất sau khi người thu thập tự lọc bỏ những dòng không khớp hoặc missing values, reviewer chỉ nhìn CSV có thể không nhận ra **selection bias**. Cần lưu query, điều kiện lọc, tổng dòng trước/sau và giải thích các bản ghi loại trừ. Đối với dữ liệu nguồn lỗi, không được điền giá trị PASS mặc định khi không có quan sát.

## 13. Nguồn độc lập và phản chứng: đừng chỉ chọn dữ liệu thuận lợi

Một assurance argument đáng tin phải kiểm tra **counterevidence** và nguồn sai chung.

### 13.1. Nguồn không độc lập

Ví dụ ba dashboard:
1. SIEM overview.
2. Security posture summary.
3. Audit management report.

Cả ba đều lấy từ **cùng một log pipeline**. Nếu pipeline mất dữ liệu 12 giờ, ba dashboard đều có thể không phát hiện vi phạm trong khoảng đó. **Ba biểu đồ không tương đương ba nguồn chứng minh độc lập**.

Có thể tăng độ tin cậy bằng:
- Đối chiếu runtime state với audit events.
- Kiểm tra cloud control plane và application authorization tests.
- Dùng synthetic event xuyên suốt nguồn–đích.
- Kiểm tra source-health, queue loss, dropped events.
- Cho reviewer khác thử tái kiểm tra dữ liệu gốc.

### 13.2. Những phản chứng cần được giữ lại

- Security test FAIL ở một endpoint trong scope.
- Finding high/critical chưa verified fixed.
- Incident có dấu hiệu control bị bypass.
- Log source bị thiếu trong một khoảng thời gian.
- Policy exception vượt hạn hoặc vượt asset scope.
- Một DR drill không đạt RTO/RPO trong kịch bản đã duyệt.
- Scan sau release phát hiện runtime còn dependency yếu.

Phản chứng có thể làm claim **CONTRADICTED** hoặc làm liên kết evidence–claim **không còn đủ tin cậy**. Ticket remediation đã tạo là dấu hiệu đang xử lý, không phải bằng chứng phản chứng biến mất.

### 13.3. Câu hỏi phản biện quan trọng

**“Nếu tất cả evidence đang trình bày đều chính xác, claim có vẫn có thể sai không?”**

Ví dụ 50 security tests PASS nhưng 1 endpoint export chưa nằm trong inventory. Claim “mọi đường đọc dữ liệu đều enforce authorization” vẫn có thể sai. Câu hỏi trên giúp tìm tiền đề bị bỏ sót thay vì chỉ bổ sung file để trông đủ hồ sơ.

## 14. Phân biệt PASS, FAIL, UNKNOWN, EXCEPTED và NOT APPLICABLE

Gộp mọi trạng thái không phải FAIL vào PASS là một anti-pattern nghiêm trọng.

| Trạng thái | Khi sử dụng | Có được tính là đáp ứng control kỹ thuật? |
|---|---|---|
| **PASS / SUPPORTED** | Có evidence phù hợp, đủ, còn hiệu lực theo criteria và scope | Có, trong giới hạn được nêu |
| **FAIL / CONTRADICTED** | Có evidence đáng tin về việc không đáp ứng | Không |
| **UNKNOWN / NOT DEMONSTRATED** | Thiếu evidence, dữ liệu không đủ, source bị lỗi hoặc scope chưa rõ | Không thể kết luận |
| **EXCEPTED** | Có sai khác nằm trong ngoại lệ được duyệt đúng phạm vi, thời gian, điều kiện | Không được tự đồng nhất với PASS |
| **NOT APPLICABLE** | Requirement thực sự không áp dụng theo tiêu chí có căn cứ | Không nằm trong mẫu số yêu cầu áp dụng |
| **PENDING RETEST** | Action đã thực hiện nhưng chưa xác minh hiệu quả | Chưa được coi verified fixed |

Một exception có thể được phép theo chương trình quản trị rủi ro nhưng không có nghĩa security requirement kỹ thuật ban đầu đã đạt. Nếu chương trình audit có quy tắc phân loại riêng, cần ghi rõ cách trình bày để người dùng không hiểu “approved exception” thành “no risk”.

## 15. Cách sửa: thiết kế evidence plan trước khi thu thập

Thay vì giao nhiệm vụ “nộp 15 file cho control”, hãy bắt đầu với **bảng liên kết quyết định–claim–tiêu chí–phép kiểm tra**.

### 15.1. Quy trình tám bước

1. **Xác định quyết định:** auditor, risk owner, release manager hay security assurance lead cần kết luận gì?
2. **Viết claim có phạm vi:** hệ thống, asset, data, environment, release, thời kỳ, security property.
3. **Chốt criteria:** yêu cầu/policy/control version và thế nào là đạt, không đạt, chưa đủ.
4. **Phân rã argument:** control design, enforcement, operation, dependency, exception, residual risk.
5. **Định nghĩa population:** nguồn và cách đối chiếu để biết toàn bộ đối tượng phải chịu đánh giá.
6. **Lập evidence plan:** mỗi claim con có nguồn, phương pháp, tần suất, chất lượng, owner và phản chứng cần tìm.
7. **Thu, xác minh, giải thích:** kiểm tra raw data, metadata, coverage, time và mâu thuẫn; lưu limitations.
8. **Kết luận và duy trì:** reviewer đánh giá, findings/CAP, retest và triggers làm evidence hết hiệu lực.

~~~mermaid
flowchart TD
    A["Quyết định / Security objective"] --> B["Claim + phạm vi + criteria"]
    B --> C["Argument / subclaims"]
    C --> D["Population + evidence plan"]
    D --> E["Collect raw evidence + provenance"]
    E --> F{"Quality/coverage/freshness đủ?"}
    F -- "Không" --> G["UNKNOWN, evidence gap, action"]
    F -- "Có" --> H{"Có phản chứng hoặc finding?"}
    H -- "Có" --> I["FAIL/CHALLENGED, CAP & retest"]
    H -- "Không" --> J["Supported conclusion có giới hạn"]
    G --> K["Review, kiểm chứng lại"]
    I --> K
    J --> L["Risk/assurance decision"]
    K --> D
    L --> M["Change/release triggers và reassessment"]
    M --> B
~~~

Không được bỏ nhánh UNKNOWN. Nếu collector không có quyền đọc một account, việc trả “0 finding” của account đó là **không có quan sát**, không phải PASS.

### 15.2. Evidence plan mẫu

| Claim con | Tiêu chí | Evidence cần | Giới hạn cần kiểm tra |
|---|---|---|---|
| G1: policy được định nghĩa | Approved policy/role matrix, đúng version | Policy record, owner approval | Chưa chứng minh thực thi |
| G2: control triển khai đầy đủ | Mọi asset trong population dùng cấu hình phù hợp | Inventory + runtime config + tests | Asset ngoài inventory, đường deploy khác |
| G3: control hiệu quả | Các đường vi phạm bị chặn, luồng hợp lệ giữ được | Negative/positive tests, test run | Scope của cases, release/env |
| G4: control hoạt động trong kỳ | Sự kiện, review và hành động đầy đủ theo criteria | Logs, workflow history, sampled records | Missing events, source gaps, sample |
| G5: risk/exception được quản lý | Ngoại lệ đúng thẩm quyền/hạn, residual risk có owner | Risk decisions, CAP, monitoring | Không biến risk acceptance thành PASS |

Mỗi hàng phải có **người chịu trách nhiệm và reviewer**, không chỉ một đường dẫn trống.

## 16. Evidence contract: chuẩn tối thiểu cho mỗi hiện vật

Một **evidence contract** quy định để một kết quả được sử dụng trong đánh giá, nó phải có những trường và phép kiểm tra nào.

| Trường | Ý nghĩa |
|---|---|
| Evidence ID | Mã duy nhất, không trùng và không thay phiên bản âm thầm |
| Claim/control ID | Tuyên bố nào được hỗ trợ và criteria phiên bản nào |
| Source/artifact reference | Đường tới hiện vật gốc được phân quyền |
| Collection method | API/query/script/test/manual review và phiên bản phương pháp |
| Scope | Asset IDs, account/region, environment, release/build, role |
| Time | UTC collected time và observation window |
| Population & coverage | Số đối tượng dự kiến, thu được, thiếu và loại trừ |
| Raw and derived values | Input, expected/actual, transformations, filtering |
| Result & exceptions | PASS/FAIL/UNKNOWN/EXCEPTED và lý do |
| Quality checks | Completeness, freshness, integrity, source health |
| Contradictions | Finding/test FAIL/incident hoặc nguồn trái chiều |
| Reviewer | Ai xác minh, lúc nào, kết luận và limitations |
| Expiry/review triggers | Khi nào không còn đại diện cho claim |
| Retention/access | Quyền truy cập, lịch sử, chính sách lưu và bảo vệ dữ liệu |

### 16.1. Ví dụ YAML: kết quả một phép kiểm tra IAM

Dữ liệu dưới đây là **giả định học tập**, không phải chứng cứ thực tế:

~~~yaml
evidence:
  id: EV-PRIV-2026-Q3-014
  claim_id: G-PRIV-ACCESS-REVIEW
  control_id: IAM-REVIEW-01
  requirement_version: "v3"
  source:
    system: identity-governance-platform
    export_ref: "restricted/evidence/iam/quarter3/export"
    query_ref: "restricted/evidence/iam/quarter3/query"
    collector_role: security-assurance-engineer
    tool_version: "collector-2.1"
  period:
    from_utc: "2026-07-01T00:00:00Z"
    to_utc: "2026-09-30T23:59:59Z"
    collected_at_utc: "2026-10-02T08:00:00Z"
  scope:
    environment: production
    account_inventory_ref: "restricted/inventory/prod-accounts"
    expected_accounts: 4
    collected_accounts: 3
    expected_privileged_identities: 150
    collected_privileged_identities: 140
    sample_method: "complete-population-check-planned"
  assessment:
    identities_with_review_record: 138
    identities_without_review_record: 2
    identities_not_collected: 10
    review_decision_execution_checked: false
    status: NOT_DEMONSTRATED
    rationale: >
      One account is missing from the export and review decisions
      have not yet been reconciled with actual access changes.
  quality:
    collection_complete: false
    source_health_checked: true
    independent_population_crosscheck: pending
  open_questions:
    - "Which privileged identities are in the missing account?"
    - "Were access removal decisions executed within the required period?"
  reviewer:
    role: independent-security-assurance-reviewer
    status: PENDING
  remediation_ref: "restricted/findings/IAM-GAP-014"
~~~

Tập dữ liệu có **138 review records** không đồng nghĩa **138 quyền đã được xác minh phù hợp**, vì còn thiếu kiểm tra các quyết định thu hồi được thực thi. Một evidence item tốt nêu rõ điều này thay vì gán PASS.

### 16.2. Công cụ xuất evidence không phải nguồn chân lý tuyệt đối

Một bản JSON có metadata đầy đủ chưa đủ nếu query nguồn sai. Người đánh giá cần **mở hiện vật nguồn**, xác minh phép thu thập, sampling/coverage và đối chiếu kết quả với hệ thống thực. Schema là công cụ giúp kiểm tra, không thay bản thân kiểm chứng.

## 17. Tình huống thực hành 1: Access review đặc quyền

**Bối cảnh giả định:** tổ chức có 4 cloud account production và 150 principal tương tác được xem là có đặc quyền. Control IAM-REVIEW-01 yêu cầu rà soát quyền theo quý và xử lý quyết định thu hồi theo tiêu chí áp dụng.

### 17.1. Gói evidence ban đầu trông “đẹp”

Đội vận hành nộp:

- Một file Excel chứa 140 hàng tài khoản với cột Review = Done.
- Một screenshot dashboard hiện “100% review tasks completed”.
- Một email từ quản lý ghi “All privileged access reviews finished”.
- Một report PDF export từ công cụ workflow.
- Một ticket chính có trạng thái Closed.

Auditor đặt câu hỏi: **Tập 140 tài khoản được xác định từ đâu?** Đội trả lời từ ba cloud account; account thứ tư mới tạo chưa được đồng bộ. Trong 140 hàng, hai tài khoản review chưa có bằng chứng người duyệt đủ thẩm quyền. Có năm quyết định “remove access” nhưng chưa có log kiểm tra quyền đã thực sự thu hồi.

### 17.2. Evidence gap theo từng claim

| Claim | Những gì có | Còn thiếu |
|---|---|---|
| G1: đúng population | Danh sách 140 principal | Một cloud account, 10 principal, đối chiếu loại account/role |
| G2: review theo kỳ | Review Done trong workflow | Quyết định/reviewer hợp lệ, sự kiện theo kỳ |
| G3: hành động sau review | Ticket Closed | Bằng chứng thu hồi năm quyền trên IAM runtime |
| G4: không có đường bypass | Một screenshot workflow | Emergency principal, direct grants và role inheritance |
| G5: kết luận toàn production | Dashboard 100% | Không đủ scope, có mâu thuẫn với inventory |

**Kết luận lúc này:** Không thể khẳng định control đã được thực hiện đầy đủ trong quý trên toàn bộ production. Các trường hợp thiếu review có thể dẫn tới finding; các phần chưa thu thập là **NOT DEMONSTRATED**, không tự coi là FAIL hay PASS.

### 17.3. Cách sửa quy trình đánh giá

1. Đối chiếu cloud account inventory với IdP, IAM và privileged role graph.
2. Xác nhận population cả kỳ, gồm tài khoản đã tạo/xóa trong kỳ và đường break-glass.
3. Thu danh sách review decisions với reviewer identity, timestamp, kết quả và phê duyệt.
4. Kiểm tra năm quyết định thu hồi bằng IAM change records và trạng thái thực.
5. Rà soát ngoại lệ hợp lệ theo phạm vi/thời hạn, không cộng vào PASS.
6. Tạo finding/CAP cho các trường hợp thực sự sai; giữ evidence gaps riêng.
7. Cho reviewer độc lập kiểm tra mẫu hoặc toàn bộ đối tượng trọng yếu theo tiêu chí.
8. Cập nhật conclusion, ghi lịch sử thay đổi và điều kiện đánh giá kỳ tiếp theo.

### 17.4. Không sửa kết quả bằng cách “bổ sung chữ ký”

Nếu có ba tài khoản đã không được rà soát đúng hạn, việc yêu cầu owner ký sau kỳ **không tự chứng minh review đã diễn ra đúng kỳ cũ**. Có thể hoàn thành corrective review ở kỳ sau và xử lý rủi ro, nhưng không được viết lại thời điểm lịch sử. Đây là ranh giới quan trọng giữa **remediation hiện tại** và **bằng chứng hoạt động trong quá khứ**.

## 18. Tình huống thực hành 2: Cloud storage “100% private”

**Bối cảnh giả định:** chương trình yêu cầu mọi object store chứa dữ liệu nhạy cảm ở production không cho phép public access trái policy.

Báo cáo hàng tháng có 68/68 buckets PASS và một screenshot console. Tuy nhiên:

- Report chỉ bao phủ những bucket có tag do team platform đặt.
- Một tài khoản cloud mới chưa onboard vào scanner.
- Công cụ không đọc object-level policy của một loại storage mới.
- Một bucket từng bị mở public trong khoảng 45 phút, sau đó đã đóng trước ngày chụp ảnh.
- Không có evidence đối chiếu public-access change events với config snapshots.

### 18.1. Lỗ hổng trong cách thu thập

Đây là tổ hợp:
- **Incomplete population** do nguồn inventory chỉ lấy resource có tag.
- **Coverage mismatch** do không kiểm tra object-level policy.
- **Point-in-time bias** do ảnh được chụp sau khi sửa drift.
- **Missing event history** nên không biết lúc nào exposure bắt đầu/kết thúc.
- **False assurance** do gán kết luận toàn production.

### 18.2. Evidence plan phù hợp hơn

| Yêu cầu | Evidence cần | Quality gate |
|---|---|---|
| Biết toàn bộ storage assets | Account/region inventory, runtime discovery, data classification | Không bỏ account, region, untagged resource |
| Không public ngoài policy | Cloud config/policy evaluation theo loại resource | Kiểm tra rule inheritance/ACL, scope và phiên bản |
| Phát hiện drift | Change events + state check theo kỳ phù hợp | Source health, event lag, collector permissions |
| Có kiểm soát ngăn chặn | Preventive policy/admission nếu hỗ trợ | Negative test cho resource trái chuẩn |
| Có xử lý sai lệch | Finding, containment, incident assessment, CAP và retest | Closure criteria, reviewer, evidence nguồn |
| Có kết luận theo thời gian | Lịch sử config và event trong cửa sổ cần đánh giá | Thời điểm, missing periods, limitations |

**Không kết luận** rằng dữ liệu không bị truy cập trái phép chỉ vì bucket hiện private. Nếu thiếu access logs trong giai đoạn public, cần ghi bất định lịch sử và quyết định xử lý có thẩm quyền.

### 18.3. Điều kiện đủ để đưa ra kết luận hiện tại

Có thể viết: “Tại thời điểm kiểm tra T, các object store thuộc inventory đã đối chiếu được đánh giá bằng policy rule phiên bản V; không phát hiện public access trái policy trong phạm vi. Các sai lệch lịch sử và các nguồn không được hỗ trợ được nêu riêng.” Đây là **kết luận có giới hạn**, không phải bảo đảm vô điều kiện.

## 19. Tình huống thực hành 3: Scanner sạch và finding đã đóng

**Bối cảnh giả định:** một security scanner phát hiện CVE trên sáu workload production. Đội kỹ thuật cập nhật dependency ở repo chính và xuất báo cáo scan mới không còn CVE. Ticket remediation chuyển Done.

### 19.1. Những câu hỏi phải kiểm tra

- Report scan mới chạy trên **source/repo** hay trên artifact thực tế đang chạy?
- Cả sáu workload đã deploy image chứa bản vá chưa?
- Container/instance autoscale hoặc DR site còn bản cũ không?
- Scanner có đủ quyền và đã thực sự phân tích tất cả asset liên quan không?
- Version và component chịu ảnh hưởng được nhận diện đúng trong SBOM/runtime không?
- Có regression test cho chức năng bảo mật/nghiệp vụ bị tác động không?
- Nguyên nhân root cause của việc dùng dependency yếu đã được quản lý chưa?
- Kết quả retest có đúng closure criteria và được reviewer kiểm chứng không?

### 19.2. Kết luận theo tiến độ

| Trạng thái quan sát | Kết luận hợp lý |
|---|---|
| PR merge | Fix implemented in source |
| CI build PASS | Artifact xây dựng/test theo cấu hình CI đã định |
| Ba trong sáu workload deploy bản mới | Partially implemented/deployed |
| Scan chỉ ba workload và không thấy CVE | Chỉ có evidence cho ba workload đã scan |
| Sáu workload xác nhận đúng artifact, retest và regression đạt | Có cơ sở verified fixed trong scope |
| Có một workload DR chưa thu bằng chứng | Overall finding chưa thể kết luận fully remediated nếu DR thuộc scope |

**Ticket đóng không thay cho technical verification.** Nếu scanner “sạch” vì target không reachable hoặc thiếu quyền, đó là lỗi thu thập evidence, không phải phát hiện đã được khắc phục.

## 20. Tình huống thực hành 4: Logging dashboard xanh nhưng nguồn mất

Một SIEM dashboard báo “100% log pipeline healthy” vì job tổng hợp dashboard vẫn chạy. Sau incident, tổ chức phát hiện audit events từ hai trong số tám ứng dụng quan trọng không được gửi về SIEM trong ba ngày.

### 20.1. Vì sao bằng chứng ban đầu sai?

- Chỉ kiểm tra **dashboard query chạy thành công**, không kiểm tra mỗi nguồn có event.
- Không có expected-source inventory, source heartbeat hoặc synthetic event.
- Tổng volume từ sáu ứng dụng còn lại đủ lớn nên không có cảnh báo giảm.
- Không đối chiếu source event count với số nhận tại đích.
- Không kiểm tra logic rule khi event format đổi sau release.

### 20.2. Kế hoạch cải tiến

1. Xác định danh mục 8/8 nguồn cùng loại event bắt buộc và owner.
2. Kiểm tra collector permissions, queue lag, dropped events, retention.
3. Tạo synthetic event được phép từ từng nguồn và xác nhận đến đích.
4. Đối chiếu event counts/schemas theo cửa sổ và phân biệt nguồn ít event với nguồn mất log.
5. Cảnh báo khi một nguồn không có heartbeat hoặc chậm quá ngưỡng được duyệt.
6. Sửa root cause và retest end-to-end; lưu evidence.
7. Ghi rõ **khoảng trống ba ngày**: không thể tự khẳng định có đủ log nếu không khôi phục từ nguồn khác.
8. Cập nhật audit finding, assurance case, CAP và kiểm tra lại sau thay đổi.

Một dashboard mới xanh là evidence cho **hiệu lực hiện tại**; nó không thể lấp sự thiếu hụt chứng cứ lịch sử bằng cách đổi màu nhãn.

## 21. Tự động hóa thu thập evidence: giảm công sức nhưng không tự tăng độ tin cậy

Tự động hóa có lợi khi dữ liệu nhiều, thay đổi thường xuyên và cần lịch sử có thể lặp. Nhưng automation cũng có thể **tự động hóa sai sót** nếu không có quality gates.

### 21.1. Những thành phần cần kiểm soát

| Thành phần | Rủi ro | Biện pháp |
|---|---|---|
| Collector credentials | Thiếu quyền hoặc có quyền quá rộng | Least privilege, kiểm tra quyền và scope |
| Asset discovery | Bỏ account/region/tag mới | Reconciliation với nguồn inventory khác |
| API pagination/rate limiting | Chỉ lấy một phần dữ liệu | Count pages, retries, completeness checks |
| Time/window logic | Sai timezone, snapshot thay kỳ | UTC, kiểm tra boundary và dữ liệu lịch sử |
| Rule engine | Logic luôn PASS hoặc false positives | Positive/negative fixtures, peer review |
| Data transformation | Mất dòng NULL/exception/FAIL | Ghi filter, dòng trước/sau, provenance |
| Evidence storage | File có thể bị sửa/xóa, lộ dữ liệu | Versioning, access control, audit trail |
| Dashboard aggregation | Gộp UNKNOWN/EXCEPTED vào PASS | Phân tách trạng thái, minh bạch mẫu số |
| Change/release integration | Kết quả cũ dùng cho artifact mới | Bind release/build/config, invalidate khi đổi |
| Action/closure pipeline | Ticket tự đóng sau deploy | Retest evidence, reviewer và closure criteria |

### 21.2. Kiểm thử chính pipeline evidence

Một phép thử tốt có **mẫu vi phạm có kiểm soát**. Ví dụ trên môi trường test được phép:
- Tạo resource cấu hình trái policy, xác nhận evaluator báo FAIL.
- Tắt một collector trong cửa sổ thử nghiệm, xác nhận trạng thái UNKNOWN và alert source gap.
- Thử một exception hết hạn, xác nhận không được chuyển sang PASS.
- Thử asset mới chưa có tag, xác nhận inventory vẫn nhận diện.
- Thử release ID khác, xác nhận evidence cũ không tự được tái sử dụng.

Những phép thử này cần giới hạn an toàn, tránh tạo lộ dữ liệu, tài nguyên public thật hoặc làm gián đoạn production. Chúng là phép thử **chất lượng cơ chế đo**, không phải bằng chứng bao quát mọi nguy cơ.

### 21.3. Trạng thái dữ liệu không được mặc định thành tuân thủ

~~~text
For each expected control target:
  if target not collected or source health invalid:
      result = UNKNOWN
  else if verified requirement not applicable:
      result = NOT_APPLICABLE
  else if control violation observed:
      if an approved, in-scope, current exception exists:
          result = EXCEPTED
      else:
          result = FAIL
  else:
      result = PASS

Do not calculate overall PASS without validating:
  population completeness,
  criteria and rule version,
  observation period,
  evidence provenance,
  material contradictions.
~~~

Đây là pseudocode về đánh giá bằng chứng, **không phải một engine production hoàn chỉnh**. Quy tắc thực cần được review theo control và rủi ro của tổ chức.

## 22. Vai trò và trách nhiệm: không ai sở hữu “tập file” vô danh

Chương trình evidence chất lượng cần chủ thể chịu trách nhiệm ở từng bước.

| Vai trò | Trách nhiệm |
|---|---|
| **Business/system owner** | Xác định tác động nghiệp vụ, chấp nhận rủi ro theo thẩm quyền |
| **Control owner** | Mô tả mục tiêu, tiêu chí, population, kỳ đánh giá và xử lý ngoại lệ |
| **Engineering/SRE/IAM/Data team** | Vận hành control và cung cấp evidence thực thi/vận hành |
| **Security assurance lead** | Xây assurance argument, evidence plan và kết luận có phạm vi |
| **Detection/telemetry owner** | Xác minh source health, logging, rule và tính đầy đủ nguồn |
| **GRC/compliance** | Quản lý mapping, lịch audit, policy, retention, exception/CAP |
| **Independent reviewer/auditor** | Thẩm tra evidence, tìm lỗ hổng và phản chứng, ghi nhận giới hạn |
| **Risk authority** | Quyết định residual risk theo quyền được giao; không tự sửa kết quả kỹ thuật |

Một người có thể kiêm nhiều vai trò trong đội nhỏ, nhưng vẫn cần **review tương xứng với mức rủi ro** và dấu vết các quyết định. Không nên để người tự tạo rule, tự chọn dữ liệu, tự loại FAIL và tự phê duyệt mọi kết luận quan trọng mà không có giám sát.

### 22.1. Cơ chế hỏi ngược thay vì đòi thêm file

Khi reviewer thấy một báo cáo PASS, hãy hỏi:
1. Claim nào đang được hỗ trợ?
2. Nguồn và population được kiểm chứng thế nào?
3. Nếu một asset ngoài danh sách xuất hiện, ai phát hiện?
4. Nếu nguồn mất dữ liệu thì trạng thái chuyển về gì?
5. Một finding mới hoặc test FAIL ảnh hưởng kết luận thế nào?
6. Bằng chứng còn đúng cho release/kỳ hiện tại không?
7. Ai sở hữu residual risk và quyết định đóng vấn đề?

Bảy câu hỏi này thường phát hiện lỗ hổng nhanh hơn việc yêu cầu chụp thêm mười screenshot.

## 23. Đánh giá mức trưởng thành của chương trình evidence

Có thể hình dung lộ trình bốn giai đoạn:

### Giai đoạn 1 — Lưu hiện vật rời rạc

- Audit pack tạo sát hạn.
- Không có evidence schema.
- Không rõ scope, kỳ, source hay owner.
- Trạng thái PASS chủ yếu dựa vào self-declaration.

**Vấn đề cần giải quyết:** chốt control catalog, claim, criteria và ownership.

### Giai đoạn 2 — Có mapping và metadata

- Mỗi control có evidence plan.
- Artifact có ID, source, version, timestamp, phạm vi.
- Có review, ghi unknown và limitations.
- Findings/exception được liên kết đúng mục tiêu.

**Vấn đề cần giải quyết:** population completeness và chất lượng nguồn.

### Giai đoạn 3 — Tích hợp SDLC/vận hành

- Evidence được thu theo sự kiện/chu kỳ phù hợp với risk.
- Tự động đối chiếu asset, policy, release và logging source.
- Có test cho rule và collector, cảnh báo evidence gap.
- CAP, retest và reviewer nối với finding.

**Vấn đề cần giải quyết:** không để automation tạo false confidence hoặc tự động đóng vấn đề thiếu xác minh.

### Giai đoạn 4 — Assurance hướng quyết định

- Claim–Argument–Evidence và counterevidence có thể truy vết.
- Evidence bị đánh dấu cần xem lại sau change/release/threat.
- Review độc lập theo mức rủi ro, residual risk minh bạch.
- Kết luận nêu **phạm vi, confidence, limitations và điều kiện hiệu lực**.

**Kết quả mong đợi:** người ra quyết định có thể chọn GO/NO-GO, remediation, acceptance hoặc cần thêm evidence dựa trên lập luận thay vì khối lượng tài liệu.

## 24. Metrics chống “evidence theater”

Nên đo **chất lượng chứng minh**, không chỉ sản lượng hồ sơ.

| Chỉ số | Có ích khi | Cần tránh |
|---|---|---|
| **Claim-to-evidence traceability** | Biết claim quan trọng nào có mapping và review | Chỉ đo có đường link, không xem đúng nội dung |
| **Verified population coverage** | Đo số asset/identity trong toàn population đã đánh giá | Bỏ UNKNOWN khỏi mẫu số |
| **Evidence freshness** | Biết evidence có đúng release/period | Data mới nhưng query sai vẫn yếu |
| **Source-health coverage** | Phát hiện collector và nguồn logging mất dữ liệu | Chỉ đo dashboard đang chạy |
| **Open evidence gaps by risk** | Ưu tiên những thiếu sót làm sai quyết định trọng yếu | Che nhóm high-risk trong tỷ lệ chung |
| **Contradiction resolution time** | Theo dõi việc xử lý finding/test FAIL | Đóng do tạo ticket thay vì retest |
| **Verified remediation rate** | Biết finding đã được xác minh sửa theo criteria | Đếm PR merged là closure |
| **Exception age/expiry** | Theo dõi sai khác kéo dài | Gộp exception vào compliant |
| **Independent review coverage** | Kiểm tra những claim rủi ro cao được phản biện | Review chỉ ký tên, không truy xuất nguồn |
| **Evidence reuse validity** | Biết việc tái dùng evidence sau release có hợp lệ | Tự tái dùng mọi snapshot vĩnh viễn |

**Một chương trình có ít file nhưng mỗi file đủ chất lượng** có thể đáng tin hơn một chương trình có hàng nghìn file không thể đối chiếu. Các metric nên dùng để cải tiến quy trình, không tạo incentive giấu FAIL hay bớt asset khỏi inventory.

## 25. Checklist chống thu thập evidence hình thức

Trước khi chấp nhận một evidence item hoặc gói assurance, kiểm tra:

- [ ] Có security objective/claim cụ thể, không chỉ tên control?
- [ ] Criteria, requirement version và định nghĩa PASS/FAIL rõ ràng?
- [ ] Asset, role, environment, release/build và observation window xác định?
- [ ] Population đã được đối chiếu đầy đủ, có xử lý tài sản mới và thiếu nguồn?
- [ ] Evidence liên quan trực tiếp tới claim, không lấy report bất kỳ gắn vào?
- [ ] Phân biệt bằng chứng thiết kế, triển khai và hiệu quả vận hành?
- [ ] Có raw source/query/test method, run ID, timestamp và người thu thập?
- [ ] Các dữ liệu bị lọc, NULL, lỗi API hoặc thiếu trang được giải thích?
- [ ] Evidence mới đủ và phản ánh đúng kỳ, không phải ảnh snapshot sai thời gian?
- [ ] Nguồn có health check, đối chiếu coverage và thử phát hiện vi phạm?
- [ ] Có cách kiểm tra integrity, truy vết lịch sử và kiểm soát quyền xem?
- [ ] Đã kiểm tra giả định về tính độc lập và nguồn lỗi chung?
- [ ] FAIL, contradiction và historical gaps được giữ lại, không xóa để dashboard xanh?
- [ ] UNKNOWN, EXCEPTED, NOT APPLICABLE và PASS được phân biệt?
- [ ] Finding đóng có retest, deployment proof và reviewer theo tiêu chí?
- [ ] Residual risk và ngoại lệ có owner, scope, thời hạn, quyền phê duyệt?
- [ ] Có điều kiện invalidate evidence sau thay đổi hoặc incident?
- [ ] Người độc lập phù hợp có thể đi từ claim đến hiện vật gốc?
- [ ] Kết luận chỉ nói đúng điều evidence hỗ trợ, không khẳng định tuyệt đối?
- [ ] Evidence được lưu tối thiểu, bảo mật và retention đúng yêu cầu?

Checklist này giúp **đặt câu hỏi đúng**, nhưng **không thay evidence thật hoặc một cuộc review có năng lực**.

## 26. Bài tập thực hành

### Bài tập A — Audit pack IAM có nhiều file nhưng thiếu proof

Một doanh nghiệp nộp 32 file, 14 screenshot và dashboard 100% review completed cho control rà soát quyền admin. Khi kiểm tra, 1/5 cloud account chưa được thu, 4 account có owner phê duyệt sau hạn và 7 quyết định thu hồi không có bằng chứng đã thực thi.

**Yêu cầu:**

1. Nêu ít nhất năm dấu hiệu evidence hình thức.
2. Phân rã claim “admin rights được rà soát và xử lý đúng kỳ” thành subclaims.
3. Lập bảng evidence plan có population, source, period, expected/actual, reviewer.
4. Phân loại PASS, FAIL và UNKNOWN cho những đối tượng được nêu; không tự suy kết quả của các account chưa thu.
5. Viết kết luận assurance ngắn cho auditor, kèm limitation và CAP.

### Bài tập B — Báo cáo scan sạch

Đội sản phẩm nói “không còn vulnerability” vì scan pipeline không tìm CVE mới. Tuy nhiên report được tạo từ source code ở release R+1 trong khi production chạy R, một vùng DR không được scan và tài khoản collector vừa mất quyền.

**Yêu cầu:**

1. Chỉ ra lỗi version, scope, data-quality và suy luận.
2. Phân biệt “không phát hiện trong lần scan” với “không tồn tại lỗ hổng”.
3. Đề xuất kiểm tra artifact/version thực, phạm vi DR và quyền scanner.
4. Đặt tiêu chí cho trạng thái NOT DEMONSTRATED so với VERIFIED FIXED.
5. Nêu trigger phải đánh giá lại security assurance sau deploy.

### Bài tập C — Logging sau một sự cố

Một hệ thống mất audit events trong 18 giờ, đội vận hành sửa pipeline và có screenshot hiện “Healthy”. Auditing team dự định đánh dấu PASS cho cả tháng.

**Yêu cầu:**

1. Evidence nào hỗ trợ trạng thái hiện tại?
2. Vì sao screenshot không lấp được 18 giờ lịch sử?
3. Thiết kế source-health checks và event-reconciliation cần bổ sung.
4. Viết kết luận cho kỳ audit với historical gap rõ ràng.
5. Đề xuất finding/CAP và retest để phòng tái diễn.

### Bài tập D — Ba dashboard cùng nguồn

Security review dùng ba dashboard độc lập về mặt giao diện: Cloud security overview, Compliance score và Risk heatmap. Cả ba lấy từ một scanner chỉ thấy tài sản có tag.

**Yêu cầu:**

1. Phân tích sự phụ thuộc nguồn chung và nguy cơ false negative.
2. Đề xuất inventory independent cross-check.
3. Thiết kế test cho tài sản không có tag và tài sản thuộc region mới.
4. Giải thích cách công bố confidence và giới hạn evidence.
5. Viết cách đo coverage không loại UNKNOWN khỏi mẫu số.

### Bài tập E — Gói báo cáo “tuân thủ 100%”

Một chương trình báo cáo:

~~~text
Evidence files attached:     200/200
Automated checks executed:   100%
Findings closed:             100%
Compliance dashboard:        GREEN

Nhưng:
- 12 trong 40 checks không có acceptance criteria rõ.
- 5 controls chỉ được chứng minh bằng policy PDF.
- 3 high-risk findings đóng ngay sau PR merge, chưa retest.
- 1 cloud account production không nằm trong scanner inventory.
- Nhiều evidence lấy từ release cũ.
~~~

**Yêu cầu:**

1. Giải thích vì sao số lượng và màu xanh không chứng minh mục tiêu bảo mật.
2. Đề xuất tình trạng claim cho từng nhóm vấn đề: supported, contradicted, not demonstrated hoặc pending retest.
3. Xây danh sách công việc theo ưu tiên rủi ro, không chỉ theo số file.
4. Viết một mẫu thông báo cho người quyết định release hoặc auditor, tránh diễn đạt quá mức.
5. Chọn ba metrics thay thế có thể giúp cải thiện chất lượng assurance.

**Gợi ý:** Người học không cần cố gán FAIL cho tất cả trường hợp. Hãy làm rõ **evidence không đủ** khác **evidence chứng minh control sai**, và chỉ dùng kết luận theo đúng phạm vi đã xác minh.

## 27. Ghi nhớ

**Thu thập evidence hình thức** xảy ra khi tổ chức đánh đồng **đã nộp hiện vật** với **đã chứng minh security control hoạt động hiệu quả**. Phản ứng đúng không phải tăng số screenshot, PDF hay biểu mẫu, mà là chuyển sang **evidence được thiết kế từ claim, criteria, threat và quyết định cần hỗ trợ**.

Trong module **SECURITY_SECURITY_ASSURANCE**, chuỗi giá trị cần giữ là:

**Security objective / Risk → Claim có phạm vi → Argument và control criteria → Population và evidence plan → Thu thập có provenance → Kiểm tra coverage, freshness, integrity và phản chứng → Kết luận PASS/FAIL/UNKNOWN có lý do → Finding/CAP/exception → Retest, review và cập nhật liên tục.**

Một chương trình assurance trưởng thành phải trả lời được **đang chứng minh điều gì, bằng nguồn nào, trên tập tài sản và khoảng thời gian nào, những gì chưa được kiểm tra, điều gì trái với kết luận, ai xác minh và điều gì khiến bằng chứng mất hiệu lực**. Giá trị của evidence không nằm ở độ dày của tập tài liệu, mà ở khả năng giúp tổ chức **đánh giá rủi ro trung thực, phát hiện lỗ hổng và ra quyết định bảo mật có căn cứ**.
