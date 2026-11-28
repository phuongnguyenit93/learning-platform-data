# Audit finding: ghi nhận, chứng minh và khắc phục phát hiện kiểm toán bảo mật

**Audit finding (phát hiện kiểm toán)** là kết quả đánh giá cho thấy một điều kiện, hành vi, cấu hình hoặc quy trình được quan sát có mối liên hệ đáng kể với **tiêu chí kiểm toán đã xác định**. Phát hiện có thể mô tả một điểm không đáp ứng yêu cầu, một rủi ro, một cơ hội cải tiến hoặc một thực hành được ghi nhận tích cực, tùy mục tiêu và phương pháp đánh giá. Trong security assurance, cụm từ “audit finding” thường được dùng đặc biệt cho **khoảng cách giữa security requirement/control và bằng chứng hiệu lực của control**.

Một finding chất lượng không chỉ nói “hệ thống chưa an toàn”. Nó phải cho phép người đọc trả lời: **Yêu cầu nào phải được đáp ứng? Thực trạng thực tế ra sao? Chứng cứ nào đủ để khẳng định sai lệch? Phạm vi và tác động là gì? Ai sở hữu rủi ro? Cần hành động và kiểm chứng lại thế nào để đóng finding?**

Bài học thuộc chương **Audit và evidence** của module **SECURITY_SECURITY_ASSURANCE**. Module tập trung xây dựng khả năng **đánh giá có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật: từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục finding và tổ chức assurance liên tục trong phát triển, vận hành. Vì vậy, audit finding được xem như **đơn vị truy vết** từ yêu cầu bảo mật đến trạng thái control, hành động khắc phục và bằng chứng kiểm thử sau sửa.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích audit finding và phân biệt finding, observation, evidence gap, risk, vulnerability, incident, exception và corrective action.
2. Sử dụng cấu trúc **criteria – condition – evidence – cause – effect/risk – recommendation** một cách thận trọng, không biến giả thuyết thành sự thật.
3. Xác định assertion và phép kiểm phù hợp để đánh giá **control design** và **operating effectiveness**.
4. Thu thập, sàng lọc và bảo vệ bằng chứng có **nguồn gốc, phạm vi, độ tin cậy, tính toàn vẹn và khoảng thời gian** rõ ràng.
5. Viết tiêu đề, mô tả sai lệch, tác động, mức ưu tiên và giới hạn kết luận theo ngôn ngữ có thể kiểm toán.
6. Đề xuất corrective/preventive actions gắn owner, deadline, tiêu chí chấp nhận và phương pháp retest.
7. Phân biệt đóng việc triển khai, đóng finding đã kiểm chứng, chấp nhận rủi ro và trường hợp chưa đủ bằng chứng.
8. Xây dựng finding register và các chỉ số theo dõi hiệu quả remediation trong continuous assurance.

## 2. Audit finding là gì, và không phải là gì?

### 2.1. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Audit criterion** | Yêu cầu, chính sách, chuẩn, hợp đồng hoặc tiêu chí đánh giá có hiệu lực với scope | Mọi tài khoản quản trị production phải dùng MFA |
| **Audit evidence** | Dữ liệu/hiện vật có thể kiểm chứng dùng hỗ trợ nhận định | IAM policy, danh sách principal, kiểm tra đăng nhập |
| **Audit observation** | Điều auditor quan sát hoặc thu thập được | Có một tài khoản quản trị local không chịu chính sách MFA |
| **Audit finding** | Kết quả so sánh observation với criterion và diễn giải phạm vi/tác động | Control MFA không đáp ứng yêu cầu với một đường admin |
| **Nonconformity** | Không đáp ứng một yêu cầu áp dụng được | Có tài khoản thuộc phạm vi yêu cầu MFA nhưng không được enforce |
| **Vulnerability** | Điểm yếu có thể bị khai thác trong thiết kế/triển khai/vận hành | API endpoint cho phép truy cập vượt quyền |
| **Risk** | Khả năng và hệ quả của sự kiện ảnh hưởng mục tiêu | Kẻ tấn công có thể dùng credential yếu để chiếm quyền |
| **Incident** | Sự kiện được xác định là sự cố theo quy trình tổ chức | Tài khoản admin thực sự bị dùng trái phép |
| **Exception / risk acceptance** | Quyết định cho phép sai lệch hoặc chấp nhận rủi ro có điều kiện | Cho phép ngoại lệ MFA 30 ngày với PAM và giám sát |
| **Corrective action** | Hành động xử lý nguyên nhân hoặc điều kiện không phù hợp | Loại đường local bypass và áp MFA bắt buộc |
| **Retest / verification** | Kiểm tra lại assertion sau khắc phục | Thử các đường admin xác minh không còn bypass |

Các đối tượng này có thể liên kết nhưng **không thay thế nhau**. Một CVE quan trọng có thể dẫn đến audit finding nếu tồn tại criterion phải quản lý lỗ hổng. Một incident có thể bộc lộ audit finding về logging hoặc IAM. Nhưng phát hiện cấu hình sai trong audit không tự chứng minh incident đã xảy ra.

### 2.2. Một finding phải gắn với phạm vi

Ví dụ phát biểu:

> “Toàn bộ hệ thống chưa đáp ứng yêu cầu MFA.”

Phát biểu này quá rộng nếu auditor mới kiểm tra 8/120 principal. Có thể viết chính xác hơn:

> “Trong mẫu 8 principal có quyền quản trị production được kiểm vào ngày 28/11/2026, hai principal local không bị chính sách MFA bao phủ. Mẫu nằm trong nhóm tài khoản quản trị của dịch vụ thanh toán; mức độ phổ biến ở các dịch vụ khác chưa được kiểm chứng.”

Câu sau giúp người đọc biết **đã thấy gì**, **trên bao nhiêu đối tượng**, **ở đâu** và **không thể suy rộng đến đâu**. Nếu inventory toàn bộ 120 principal đáng tin và thử tự động đủ phạm vi, finding có thể nêu số lượng tổng chính xác hơn.

### 2.3. Không có bằng chứng không đồng nghĩa control thất bại

Nếu đội vận hành tuyên bố “đã review quyền hằng quý” nhưng chưa cung cấp hồ sơ review, auditor có thể kết luận **chưa đủ bằng chứng để chứng minh assertion**. Điều đó không tương đương đã xác nhận **không hề có review**.

Nên phân biệt:

- **Confirmed control failure:** dữ liệu hoặc phép kiểm trực tiếp chứng minh yêu cầu không đạt.
- **Evidence deficiency:** thiếu, không thể truy xuất hoặc không đủ tin cậy để chứng minh control.
- **Inconclusive:** có dữ liệu nhưng chưa thể kết luận đạt/không đạt.
- **Potential risk:** giả thuyết tác động từ sai lệch; chưa chứng minh sự cố đã xảy ra.

Cách phân biệt này giúp audit công bằng, tăng chất lượng remediation và tránh tạo các finding không thể retest.

## 3. Vòng đời finding trong audit và assurance

Một finding đi qua nhiều bước, không kết thúc tại lúc auditor phát hành báo cáo.

~~~mermaid
flowchart LR
    S["Scope + audit criteria"] --> T["Thiết kế test/control assertion"]
    T --> E["Thu evidence và quan sát"]
    E --> D["Phân tích sai lệch"]
    D --> V["Xác minh dữ kiện với owner"]
    V --> F["Finding + mức rủi ro"]
    F --> A["Remediation plan + risk decision"]
    A --> R["Triển khai hành động"]
    R --> X["Retest hiệu lực"]
    X --> P{"Đã đạt criterion?"}
    P -- "Chưa" --> A
    P -- "Đạt trong scope" --> C["Đóng finding đã xác minh"]
    C --> M["Monitoring + tái đánh giá"]
    M --> T
~~~

Các mốc kiểm soát:

1. **Planning:** xác nhận scope, criteria, kỳ đánh giá, trách nhiệm và đối tượng.
2. **Fieldwork:** thu cấu hình, log, phỏng vấn, mẫu giao dịch và chạy phép kiểm phù hợp.
3. **Evidence analysis:** đánh giá tính đầy đủ, độ tin cậy, sai lệch và giới hạn.
4. **Draft finding:** viết mô tả, evidence và ảnh hưởng có căn cứ.
5. **Factual validation:** xác minh tính chính xác với control owner; lưu khác biệt quan điểm và quyết định.
6. **Risk rating / report:** xác định mức ưu tiên và phát hành trong quy trình phê duyệt.
7. **Remediation:** chủ sở hữu lập và thực hiện kế hoạch khắc phục.
8. **Independent/authorized retest:** người có thẩm quyền xác minh hiệu lực trên scope cần thiết.
9. **Closure hoặc acceptance:** đóng do verified, giữ mở, hoặc quản lý residual risk theo cơ chế ngoại lệ.
10. **Continuous assurance:** giám sát control drift và tái kiểm tra sau thay đổi.

**Tách vai trò đánh giá và vai trò xử lý** giúp giảm xung đột lợi ích. Tùy quy mô tổ chức, người kiểm chứng có thể cùng đội nhưng nên có cơ chế review/approval đủ độc lập theo mức rủi ro.

## 4. Cấu trúc một finding có thể kiểm toán

Một mô hình hữu ích là **Criteria – Condition – Cause – Effect – Recommendation**, đôi khi được gọi ngắn là mô hình “5C”. Đây là **khung tổ chức phân tích**, không phải quy định bắt buộc của mọi chuẩn audit và không phải finding nào cũng đã xác định được nguyên nhân gốc.

| Thành phần | Câu hỏi | Nội dung cần có |
|---|---|---|
| **Criteria — yêu cầu** | Đáng lẽ điều gì phải đúng? | Yêu cầu có hiệu lực, phiên bản, owner, kỳ và scope áp dụng |
| **Condition — thực trạng** | Dữ liệu cho thấy điều gì? | Observation cụ thể, danh tính/tài sản, số lượng, kỳ kiểm tra |
| **Evidence — bằng chứng** | Dựa vào đâu xác nhận condition? | Evidence ID, nguồn, phương pháp, thời gian, phạm vi |
| **Cause — nguyên nhân** | Vì sao sai lệch tồn tại? | Nguyên nhân được chứng minh hoặc giả thuyết cần điều tra |
| **Effect / Risk — tác động** | Sai lệch có thể ảnh hưởng mục tiêu nào? | Rủi ro, điều kiện khai thác, phạm vi hậu quả, đã xảy ra hay tiềm tàng |
| **Recommendation — hướng xử lý** | Cần làm gì để đạt yêu cầu và giảm tái diễn? | Control objective, biện pháp dự kiến, tiêu chí kiểm chứng |

Ngoài sáu nội dung chính, một finding thực tế nên có **ID, title, severity, confidence, owner, due date, trạng thái, liên kết risk/control, source/evidence, phương pháp retest và lịch sử cập nhật**.

### 4.1. Criteria: không bịa ra yêu cầu

Ví dụ một tổ chức quy định trong security baseline:

> Các principal có quyền quản trị tương tác vào môi trường production phải dùng cơ chế xác thực đa yếu tố; ngoại lệ phải được phê duyệt có thời hạn và có biện pháp bù trừ.

Auditor phải kiểm tra văn bản này có **hiệu lực**, áp dụng đúng **đối tượng và kỳ đánh giá**, có **định nghĩa quyền quản trị tương tác**, và có ngoại lệ được phê duyệt trước đó hay không.

Không được lấy một “best practice” chưa được phê duyệt rồi ghi thành **vi phạm hợp đồng hoặc tiêu chuẩn**. Có thể báo cáo rủi ro cải tiến dựa trên best practice, nhưng phải phân biệt với nonconformity theo một criterion bắt buộc.

### 4.2. Condition: mô tả thực trạng, không dùng định tính mơ hồ

Không tốt:

> “IAM đang rất yếu và lộn xộn.”

Tốt hơn:

> “Tại thời điểm đánh giá, 2 trong 18 principal có quyền quản trị tương tác thuộc phạm vi dịch vụ A không bị chính sách MFA enforce; người đánh giá đã so khớp inventory role, cấu hình authentication và thử đăng nhập có kiểm soát trên tài khoản thử đại diện.”

Nên có **mẫu số** và phương pháp chọn mẫu. Nếu chỉ có cấu hình role, không có kiểm thử enforcement thực tế, cần mô tả đúng bằng chứng cấu hình thay vì khẳng định đã xác nhận khả năng bypass thực tế.

### 4.3. Cause: tránh nhầm giả thuyết với kết luận

Một tình trạng thiếu MFA có thể do:

- Mẫu IAM provisioning cũ không bật điều kiện MFA.
- Tài khoản local khẩn cấp nằm ngoài cơ chế SSO.
- Policy mới chỉ áp lên nhóm principal tạo sau một thời điểm.
- Ngoại lệ có hạn nhưng không được thu hồi khi hết hạn.
- Đường xác thực bị thay đổi khi triển khai hoặc restore.

Nếu chưa đủ evidence từ change record, policy history và phỏng vấn, có thể viết: **“Nguyên nhân đang xác minh; giả thuyết là quy trình onboarding tài khoản local chưa tích hợp kiểm tra MFA.”** Không được kết luận do một cá nhân bất cẩn chỉ từ sự tồn tại của lỗi.

### 4.4. Effect: diễn đạt tác động có điều kiện

Phát hiện một đường quản trị thiếu MFA tạo **rủi ro truy cập trái phép** khi credential bị lộ hoặc bị đoán, tùy mô hình xác thực và các kiểm soát bù trừ. Nó **không chứng minh** tài khoản đã bị chiếm quyền hoặc dữ liệu đã bị truy xuất.

Có thể tách:

- **Observed impact:** hoạt động nguy hiểm hoặc sự cố đã được chứng minh bằng bằng chứng thực tế.
- **Potential impact:** hậu quả hợp lý nếu điểm yếu bị khai thác.
- **Uncertainty:** những gì chưa thể kết luận từ mẫu và kỳ dữ liệu hiện có.

### 4.5. Recommendation: mục tiêu kiểm soát trước công cụ

Một recommendation tốt tập trung vào kết quả:

> “Bảo đảm mọi đường truy cập quản trị tương tác vào production được enforce MFA hoặc có cơ chế thay thế đã phê duyệt và đánh giá tương đương theo risk policy; áp kiểm tra provisioning và audit định kỳ.”

Cách làm kỹ thuật có thể là tích hợp với IdP, chặn local login, thay authentication policy hoặc kiểm soát break-glass qua PAM. **Không khóa giải pháp duy nhất** khi chưa đánh giá kiến trúc, tính sẵn có và yêu cầu khẩn cấp.

## 5. Thiết kế assertion và phép kiểm trước khi thu bằng chứng

Đánh giá một control tốt bắt đầu bằng **assertion có thể bị chứng minh sai**, không phải bằng cảm giác hệ thống có vẻ an toàn.

Ví dụ:

- **Control objective:** ngăn truy cập quản trị trái phép.
- **Assertion:** mọi principal quản trị tương tác trong scope phải có MFA enforce trên các đường đăng nhập áp dụng.
- **Population:** principal có quyền quản trị production, tại kỳ đánh giá xác định.
- **Expected condition:** không có đường đăng nhập tương tác được phép vượt MFA ngoài ngoại lệ hợp lệ được chính sách cho phép.
- **Test:** đối soát inventory/role, xác định các phương thức đăng nhập, kiểm tra effective policy, kiểm thử được phê duyệt, review exceptions.
- **Evidence:** inventory, policy export, kiểm thử login, logs, exception records.
- **Verdict:** PASS/FAIL/INCONCLUSIVE có phạm vi và giới hạn.

### 5.1. Control design và operating effectiveness

| Loại kiểm tra | Đánh giá điều gì? | Ví dụ |
|---|---|---|
| **Design effectiveness** | Control được thiết kế có đủ khả năng đạt objective trong các giả định đã đặt? | Policy nói rõ những đường admin tương tác phải enforce MFA |
| **Implementation / configuration** | Thiết kế đã triển khai trên hệ thống thuộc phạm vi chưa? | Effective auth policy của tài khoản quản trị A |
| **Operating effectiveness** | Control có hoạt động đúng trong kỳ đánh giá và các tình huống đã thử? | Sample các lần provision/review và test auth enforcement |
| **Monitoring effectiveness** | Có khả năng nhận biết control drift/failure và phản ứng? | Alert khi có tài khoản privileged không thuộc policy |
| **Sustained effectiveness** | Control còn đạt sau change, recovery, onboarding và kiểm tra sau sửa? | Retest qua một chu kỳ provisioning hoặc kiểm tra tự động định kỳ |

Một policy được phê duyệt có thể là bằng chứng **design**, nhưng không đủ để chứng minh **operating effectiveness**. Một test PASS ngày hôm nay chỉ chứng minh hiện trạng trong phạm vi kiểm, không tự chứng minh control hoạt động liên tục cả năm trước.

### 5.2. Scope và kỳ audit

Trước khi ghi finding, cần thống nhất:

- **Asset scope:** account, cluster, host, môi trường, nhà cung cấp và dịch vụ.
- **Control scope:** loại tài khoản, nhóm dữ liệu, loại hành động và đường truy cập.
- **Time period:** tại một thời điểm, một kỳ lịch sử hoặc một loạt các lần thay đổi.
- **Data source:** bản cấu hình, hệ thống audit, hồ sơ phê duyệt và nguồn thay thế.
- **Method:** toàn bộ population, chọn mẫu theo rủi ro hoặc chọn mẫu thống kê nếu thực sự áp dụng.
- **Limitations:** asset không thể truy cập, telemetry thiếu, quyền test hạn chế, clock drift, ngoại lệ chưa xác nhận.

Nếu audit yêu cầu chứng minh **access review đã hoạt động hằng quý trong 12 tháng**, một export quyền hôm nay không đủ. Cần evidence cho các kỳ review và các mẫu hành động thực tế theo scope.

### 5.3. Chọn mẫu đúng cách

Giả sử 800 principal production, auditor chọn 30 principal có rủi ro cao nhất. Tìm 6 principal thiếu MFA trong mẫu đó là finding quan trọng, nhưng không thể nói **20% toàn bộ principal** thiếu MFA vì mẫu được chọn theo rủi ro, không ngẫu nhiên đại diện.

Hãy nêu:

- Tổng population đã biết, và nguồn xác định.
- Cách lọc/ chọn mẫu, lý do và thời gian.
- Số đối tượng đã kiểm thực tế.
- Số vi phạm và ID được bảo vệ phù hợp.
- Giới hạn suy rộng; nếu cần tỷ lệ toàn population, thiết kế phép kiểm đầy đủ hoặc phương pháp lấy mẫu đại diện thích hợp.

Phát hiện một sai lệch nghiêm trọng có thể đủ để đặt finding **ngay cả khi tỷ lệ trong mẫu thấp**, nhưng mức phổ biến phải được trình bày trung thực.

## 6. Bằng chứng audit: đủ, phù hợp và bảo vệ được

Trong audit security, **chất lượng bằng chứng quan trọng hơn số lượng file**. Cần đánh giá liệu evidence có hỗ trợ chính xác claim và phạm vi hay không.

### 6.1. Các chiều chất lượng

| Thuộc tính | Câu hỏi cần kiểm |
|---|---|
| **Relevance** | Artifact có chứng minh đúng assertion và thời gian đang đánh giá? |
| **Reliability** | Nguồn, phương pháp tạo và tính độc lập đáng tin đến đâu? |
| **Sufficiency** | Lượng evidence có đủ cho kết luận theo mục tiêu, rủi ro và sampling? |
| **Accuracy** | Trường, thời gian, giá trị và mapping có đúng/không bị biến đổi sai? |
| **Completeness** | Có record, nguồn, kỳ hoặc môi trường bị bỏ sót? |
| **Authenticity** | Artifact do đúng hệ thống/người phát hành? Có trust anchor hay dấu vết? |
| **Integrity** | Nội dung có được bảo vệ hoặc có cơ chế phát hiện sửa đổi trái phép? |
| **Timeliness** | Bằng chứng có đủ mới hoặc khớp kỳ kiểm được hỏi? |
| **Traceability** | Người kiểm tra khác có thể từ claim truy lại nguồn và phép kiểm? |
| **Confidentiality** | Việc thu và lưu bằng chứng có hạn chế dữ liệu nhạy cảm và quyền đọc? |

Ví dụ, dashboard hiển thị “100% MFA coverage” cần đối chiếu **population** của dashboard với asset/identity inventory. Nếu nó chỉ tính tài khoản SSO mà bỏ tài khoản local, tỷ lệ có thể đúng về mặt phép tính nhưng **không phù hợp với assertion mọi đường admin**.

### 6.2. Các loại evidence và giới hạn

| Evidence | Hữu ích cho | Không tự chứng minh |
|---|---|---|
| Policy/procedure | Thiết kế, trách nhiệm và yêu cầu chính thức | Control đang hoạt động thực tế |
| Configuration snapshot | Trạng thái một đối tượng tại thời điểm cụ thể | Lịch sử cả kỳ hoặc mọi đối tượng ngoài sample |
| API export/IAM effective permissions | Cấu hình quyền thực tế trong phạm vi API | Không có đường bypass khác hoặc con người không lạm dụng |
| Audit logs | Sự kiện đã ghi, actor/time và hoạt động trong scope | Mọi hành vi đã được ghi đầy đủ hoặc log không bị sửa |
| Ticket/change record | Quyết định, phê duyệt và lịch sử hành động | Thay đổi có hiệu lực trên hệ thống đúng như ticket |
| Test result | Assertion hoạt động đối với scenario và môi trường được thử | Các biến thể không được thử |
| Interview | Giải thích quy trình, bối cảnh, giả thuyết | Tình trạng kỹ thuật không có bằng chứng hỗ trợ |
| Independent report | Đánh giá trong scope/kỳ của bên kiểm tra độc lập | Mọi dịch vụ, region và kỳ ngoài scope đều đạt |

### 6.3. Evidence register

Ví dụ cấu trúc bản ghi (giá trị minh họa):

~~~yaml
evidence_id: "AUD-EV-2026-048"
assessment_id: "AUD-2026-Q4-PAY"
control_id: "IAM-PRIV-01"
source_system: "central-identity-platform"
artifact_type: "effective-policy-export"
collected_at: "2026-11-28T08:15:00Z"
source_effective_at: "2026-11-28T08:13:00Z"
scope:
  environment: "production"
  service: "payments"
  principal_population: "interactive-privileged"
collector_role: "audit-readonly"
collection_method: "approved API export with reviewed filter"
reference: "restricted-evidence-store/AUD-EV-2026-048"
hash_algorithm: "SHA-256"
hash_value: "EXAMPLE_DIGEST_NOT_REAL"
limitations:
  - "Không bao gồm các tài khoản local của hệ thống legacy"
  - "Chỉ phản ánh policy tại thời điểm source_effective_at"
classification: "INTERNAL-RESTRICTED"
~~~

Digest giả định không phải chứng cứ thật; trong hệ thống thực cần tính và xác minh giá trị từ artifact đã lưu. Điều quan trọng là **ghi rõ giới hạn** ngay trong register, thay vì chỉ ghi ở cuối báo cáo.

### 6.4. Chain of custody và tính toàn vẹn evidence

Một evidence có thể được sao chép, che dữ liệu, xuất sang CSV hoặc gom từ nhiều nguồn. Nên quản lý:

1. **Nguồn gốc:** source, account, tenant, đối tượng, truy vấn hoặc phương pháp thu.
2. **Thu thập:** người/hệ thống thu, thời gian UTC, quyền và công cụ phiên bản nào.
3. **Bảo vệ bản gốc:** kho hạn chế quyền, retention và audit truy cập phù hợp.
4. **Xác minh integrity:** hash/signature/checkpoint khi cần và trust anchor độc lập.
5. **Làm việc trên bản sao:** ghi redaction/normalization, công cụ và dữ liệu biến đổi.
6. **Bàn giao:** ai truy cập/chuyển evidence, khi nào, lý do và dữ liệu nào.
7. **Tái kiểm:** người đánh giá khác có đủ metadata để chạy lại phép kiểm trong quyền hạn thích hợp.

Hash của một file **khớp với checksum đặt cùng thư mục mà cùng admin có thể sửa** không đủ chống giả mạo. Chữ ký hợp lệ của hệ thống export không tự chứng minh dữ liệu **trước lúc export** đã trung thực; cần xét nguồn độc lập, log pipeline và quyền quản trị.

### 6.5. Bằng chứng nhạy cảm

Báo cáo audit có thể chứa đường dẫn nội bộ, tên principal đặc quyền, dữ liệu khách hàng, token hoặc chi tiết cấu hình chưa khắc phục. Không sao chép secret hoặc raw customer data vào file tìm kiếm rộng quyền chỉ để chứng minh finding.

Có thể lưu raw artifact trong kho hạn chế; báo cáo công bố **evidence ID, scope, giá trị đã khử nhạy cảm, phương pháp kiểm chứng và kết luận**. Với tài liệu quá nhạy cảm của bên thứ ba, có thể dùng review có kiểm soát hoặc xác nhận độc lập hợp lệ, song phải ghi chất lượng và giới hạn evidence.

## 7. Viết finding rõ, công bằng và có thể hành động

### 7.1. Tiêu đề finding

Tiêu đề nên chỉ ra **control gap** và **tài sản/phạm vi**, không dùng từ ngữ cảm tính:

| Chưa tốt | Tốt hơn |
|---|---|
| “IAM cực kỳ yếu” | “Hai đường truy cập quản trị production chưa enforce MFA” |
| “Logging không an toàn” | “Audit log thay đổi quyền chưa được chuyển đến kho tập trung tại account X” |
| “Thiếu mọi kiểm soát backup” | “Backup database Y chưa có bằng chứng restore thử trong kỳ đánh giá” |
| “SOC không hoạt động” | “Rule phát hiện thay đổi IAM bị tắt tại môi trường Z” |
| “Dữ liệu đã bị lộ” khi không có chứng cứ | “Role có quyền đọc dữ liệu ngoài phạm vi đã phê duyệt; chưa xác nhận truy xuất thực tế” |

Tên có thể gắn mức độ rủi ro nhưng không thay thế phần mô tả và bằng chứng.

### 7.2. Mẫu đoạn finding chuẩn

> **F-017 — Tài khoản quản trị local không được enforce MFA.** Tiêu chí IAM-POL-07 (phiên bản đang áp dụng từ 01/09/2026) yêu cầu tất cả đường đăng nhập quản trị tương tác tại production có MFA, trừ ngoại lệ được phê duyệt. Trong 18 principal thuộc phạm vi đánh giá ngày 28/11/2026, hai tài khoản local có effective authentication policy không áp MFA; chưa có exception còn hiệu lực (E-041, E-042, E-043). Sai lệch làm tăng nguy cơ truy cập quản trị trái phép nếu credential bị lộ. Chưa có bằng chứng cho thấy hai tài khoản đã bị sử dụng trái phép. Cần hạn chế hoặc bảo vệ các đường đăng nhập này, bổ sung kiểm tra provisioning, rồi retest trên toàn bộ principal thuộc scope đã xác định.

Đây là ví dụ giả định. Nó tách được **criterion**, **condition**, **evidence**, **risk**, **giới hạn** và **hướng xử lý**.

### 7.3. Phát biểu gắn với evidence, không gắn vào ý kiến cá nhân

Thay vì “đội kỹ thuật không biết quản lý quyền”, hãy ghi:

> “Hồ sơ phê duyệt quyền E-052 không chứa actor phê duyệt cấp quyền đặc biệt cho ba yêu cầu thuộc mẫu; current workflow không có trường phê duyệt bắt buộc (E-053). Chưa xác định nguyên nhân quy trình không ghi nhận thông tin này.”

Ngôn ngữ như vậy giảm xung đột giữa auditor và owner, đồng thời khiến finding có thể kiểm chứng hơn.

### 7.4. Khi owner không đồng ý

Có thể bất đồng về:

- Criterion có thực sự áp dụng với service hay không.
- Population mẫu gồm đúng nhóm đối tượng hay chưa.
- Evidence đã hết hạn hay chưa.
- Có compensating control mà auditor chưa kiểm tra hay không.
- Severity hoặc ước lượng tác động có phù hợp.
- Root cause do chính sách hay do lỗi implementation.

Quy trình nên cho control owner **cơ hội cung cấp bằng chứng và sửa dữ kiện**, nhưng không vì bất đồng mà tự động xóa finding. Sau khi xem bằng chứng mới, có thể chỉnh condition/scope/severity hoặc giữ nguyên có ghi lý do, escalation theo quy chế audit.

## 8. Xác định severity và ưu tiên xử lý

**Severity (mức độ nghiêm trọng)** phản ánh tác động và khả năng xảy ra của rủi ro liên quan đến finding theo phương pháp được tổ chức phê duyệt. Nó không phải số lượng lỗi đơn thuần hay cảm giác của auditor.

### 8.1. Những yếu tố đánh giá

| Yếu tố | Câu hỏi |
|---|---|
| **Asset criticality** | Dịch vụ có thiết yếu; dữ liệu có nhạy cảm; môi trường là production? |
| **Exposure** | Đường tấn công có tiếp cận Internet, đối tác, người dùng hay chỉ một mạng bị giới hạn? |
| **Privilege / reach** | Sai lệch cho phép quyền cao hoặc ảnh hưởng nhiều tenant/account? |
| **Exploitability** | Điều kiện khai thác thực tế và các rào cản còn lại ra sao? |
| **Potential impact** | Ảnh hưởng bí mật, toàn vẹn, sẵn có và nghiệp vụ ở mức nào? |
| **Compensating controls** | Có control độc lập đủ hiệu lực, bao phủ scope và được kiểm chứng không? |
| **Breadth / duration** | Có bao nhiêu đối tượng, tồn tại bao lâu, có thay đổi gần đây? |
| **Threat relevance** | Sai lệch liên quan kịch bản tấn công hoặc incident đã thấy không? |
| **Regulatory/contractual requirements** | Có yêu cầu bắt buộc, thời hạn khắc phục hoặc nghĩa vụ đặc biệt không? |
| **Evidence confidence** | Chúng ta chắc chắn đến đâu về condition và phạm vi? |

**Confidence và severity là hai trục khác nhau.** Một nghi vấn tác động nghiêm trọng với evidence chưa đầy đủ có thể yêu cầu thu thập khẩn cấp mà vẫn phải ghi confidence thấp. Một cấu hình sai đã xác nhận với mức rủi ro thấp không trở thành critical chỉ vì auditor rất chắc chắn.

### 8.2. Ví dụ phân loại định tính

| Tình huống giả định | Nhận định ưu tiên | Cần xem thêm |
|---|---|---|
| Đường admin public-facing không có MFA, có quyền thay đổi production | Có thể ưu tiên cao | Quyền thực tế, biện pháp chặn, tài khoản được dùng thế nào |
| Thiếu evidence review một nhóm quyền test đã hết hiệu lực | Có thể ưu tiên thấp/trung bình | Dữ liệu thật có được truy cập? Control bù trừ? |
| Audit log bị tắt trên account chứa dữ liệu nhạy cảm | Có thể cao do thiếu khả năng điều tra | Phạm vi event, thời gian, nguồn log khác |
| Backup restore chưa từng được thử cho dịch vụ nghiệp vụ trọng yếu | Có thể cao tùy RTO/RPO | Failure scenario, recovery alternatives |
| Một ticket thiếu mô tả giải trình cho thay đổi ít ảnh hưởng | Có thể thấp hơn | Tiêu chí bắt buộc và khả năng tái diễn |

Không lấy bảng này làm chuẩn điểm số. Tổ chức phải duy trì **risk rating criteria** riêng, thể hiện đúng risk appetite và yêu cầu ngành.

### 8.3. Compliance status và risk severity không thay thế nhau

Một finding có thể là **không đáp ứng yêu cầu bắt buộc** nhưng tác động trực tiếp tương đối nhỏ, hoặc là **rủi ro kỹ thuật lớn** dù chưa có yêu cầu chính sách tương ứng. Cần lưu:

- Control/compliance verdict.
- Risk severity và rationale.
- Confidence, scope và evidence.
- Deadline/escalation theo quy định.
- Tác động hợp đồng/pháp lý nếu phải xem xét với bộ phận có thẩm quyền.

Tránh ghi “vi phạm pháp luật X” chỉ vì một cấu hình chưa phù hợp best practice. Việc xác định nghĩa vụ pháp lý cần dựa trên luật áp dụng và ý kiến có thẩm quyền.

## 9. Root cause analysis: tìm điều kiện khiến control thất bại

Khắc phục một đối tượng có thể chưa giải quyết nguyên nhân hệ thống. Ví dụ sửa MFA cho hai tài khoản hiện tại nhưng quy trình tạo tài khoản mới vẫn bỏ qua MFA thì finding có thể tái xuất hiện ngay tháng sau.

### 9.1. Phân loại nguyên nhân

| Lớp | Ví dụ |
|---|---|
| **Design gap** | Chính sách chưa định nghĩa đường quản trị local |
| **Provisioning gap** | Mẫu cấp tài khoản không yêu cầu MFA |
| **Implementation gap** | Policy đúng nhưng chưa áp trên một account/region |
| **Monitoring gap** | Không phát hiện principal ngoài MFA scope |
| **Governance gap** | Ngoại lệ không có owner hoặc hết hạn vẫn tồn tại |
| **Dependency gap** | Tài khoản khẩn cấp phụ thuộc hệ thống định danh chung bị lỗi |
| **Knowledge/process gap** | Runbook không chỉ rõ kiểm chứng effective auth policy |
| **Change/drift gap** | Deploy làm thay rule/permission, không có regression test |

Một lỗi có thể có nhiều nguyên nhân đóng góp. Không quy kết con người trước khi phân tích cách quy trình, công cụ, giao diện và kiểm soát cho phép sai lệch.

### 9.2. Phương pháp 5 Whys có kiểm chứng

Ví dụ chuỗi giả định:

1. **Vì sao** hai tài khoản local thiếu MFA? Vì effective policy không áp đường local.
2. **Vì sao** policy không áp? Vì provisioning workflow bỏ nhóm tài khoản này.
3. **Vì sao** workflow bỏ qua? Vì template cũ không bao gồm loại account khẩn cấp.
4. **Vì sao** template không được cập nhật? Vì kiểm tra sau thay đổi policy không đối soát mọi principal.
5. **Vì sao** không đối soát? Vì không có owner và automated control coverage check cho population này.

Từng câu trả lời phải được xác minh qua template version, deployment history, owner record và test. Nếu bước thứ ba chưa có chứng cứ, **dừng tại giả thuyết** thay vì cố đi hết năm lần “vì sao”.

### 9.3. Causal mapping

~~~mermaid
flowchart TD
    POLICY["Yêu cầu MFA production"] --> TEMPLATE["Provisioning template"]
    TEMPLATE --> ACCOUNT["Tài khoản local được tạo"]
    ACCOUNT --> GAP["Authentication không enforce MFA"]
    REVIEW["Không đối soát principal toàn phạm vi"] --> GAP
    GAP --> RISK["Tăng nguy cơ truy cập admin trái phép"]
    CHANGE["Thay policy nhưng thiếu regression test"] --> REVIEW
    RISK --> FIX["Corrective action + preventive guard"]
~~~

Mối quan hệ trong sơ đồ là mẫu phân tích, không tự chứng minh là nguyên nhân thật. Khi lập RCA thực tế, mỗi quan hệ cần evidence hoặc nhãn **hypothesis**.

## 10. Từ finding đến corrective/preventive action

### 10.1. Phân biệt các hành động

- **Immediate containment / mitigation:** giảm rủi ro đang hiện hữu, ví dụ tạm khóa hai đường admin không cần dùng.
- **Correction:** sửa tình trạng sai tại một đối tượng, ví dụ bật MFA cho hai tài khoản.
- **Corrective action:** xử lý nguyên nhân làm sai lệch phát sinh, ví dụ sửa provisioning template và kiểm tra coverage.
- **Preventive action:** giảm khả năng lỗi tương tự xảy ra ở các đội/tài sản khác, ví dụ policy-as-code và kiểm tra trước go-live.
- **Compensating control:** biện pháp thay thế hạn chế rủi ro trong khi control chính chưa đạt, ví dụ PAM, giới hạn nguồn truy cập và giám sát chặt.
- **Retest/verification:** chứng minh control objective đã đạt sau thay đổi; có thể gồm kiểm thử hiệu lực qua kỳ.

**Correction không luôn đồng nghĩa corrective action.** Đóng finding chỉ vì đã chỉnh hai tài khoản trong mẫu có thể bỏ sót tài khoản khác và nguyên nhân tái phát.

### 10.2. Hành động SMART, theo rủi ro

Một action nên có:

1. **Finding/control reference:** sửa khoảng trống nào, criterion nào.
2. **Scope:** account, service, environment, loại principal và nhóm dữ liệu.
3. **Expected result:** assertion có thể kiểm chứng.
4. **Owner:** vai trò chịu trách nhiệm thực hiện, người phê duyệt khi cần.
5. **Due date:** thời hạn tương ứng risk tier hoặc SLA được phê duyệt.
6. **Dependencies:** thay IAM policy, IdP, network, IaC, ảnh hưởng nghiệp vụ.
7. **Implementation evidence:** PR, change record, policy version, deployment.
8. **Retest plan:** test dương/âm, population, môi trường, tiêu chí PASS.
9. **Residual risk:** ngoại lệ và kế hoạch giám sát trong lúc chưa hoàn thành.
10. **Review cadence:** điểm kiểm tra tiến độ và điều kiện escalation.

Ví dụ:

| Action ID | Mục tiêu | Owner | Bằng chứng triển khai | Điều kiện retest |
|---|---|---|---|---|
| AC-01 | Enforce MFA cho mọi admin tương tác trong service A | Identity team | Policy version + account list | Kiểm tra effective permission và test đường admin |
| AC-02 | Sửa provisioning để tài khoản mới không thoát control | Platform team | IaC/workflow diff + CI test | Tạo tài khoản thử theo các loại đường hỗ trợ |
| AC-03 | Cảnh báo khi principal privileged không thuộc MFA population | Detection team | Detection rule + alert route | Thử tạo tình huống gap trong sandbox, xác nhận alert |
| AC-04 | Rà soát và làm hết hạn exception | Governance owner | Exception register + approval | Không còn exception quá hạn, test review process |
| AC-05 | Mở rộng kiểm tra cho dịch vụ khác | Security assurance | Coverage inventory + test report | Không còn gap trong population đã xác định |

Các tên và action chỉ là minh họa; thời hạn và chủ thể thực tế phải được xác định trong quy trình tổ chức.

### 10.3. Tiêu chí đóng phải được thỏa thuận trước

Nếu tiêu chí đóng chỉ ghi “đã cập nhật policy”, owner có thể hoàn thành về tài liệu mà không sửa được control. Tốt hơn:

> “Tại kỳ retest, toàn bộ principal quản trị tương tác trong inventory của service A đều có MFA enforced trên các đường login đã xác định hoặc có ngoại lệ hợp lệ được risk owner phê duyệt theo policy; phép thử đường bypass trái quy định bị từ chối, hệ thống giám sát cảnh báo đúng khi tạo principal ngoài population.”

Nếu một ngoại lệ được chấp thuận, verdict và trạng thái finding phải phân biệt **control đạt** với **rủi ro được chấp nhận** theo chính sách. Không ghi PASS khi test chưa chứng minh assertion hoặc ngoại lệ không được phép bởi criterion.

## 11. Retest: kiểm chứng hiệu lực sau khi khắc phục

**Retest** không phải chỉ xác minh rằng nhóm kỹ thuật đã merge pull request hoặc đánh dấu task Done. Đây là hoạt động **kiểm tra lại assertion từng không đạt** bằng phương pháp phù hợp, trên phạm vi có liên quan và với bằng chứng mới có thể đối chiếu.

### 11.1. Chuẩn bị retest

Một retest plan nên ghi rõ:

| Trường | Câu hỏi |
|---|---|
| Finding ID / control ID | Assertion nào cần được kiểm tra lại? |
| Baseline | Criterion nào có hiệu lực trong kỳ retest? Có thay đổi yêu cầu hợp lệ? |
| Population | Những tài khoản/tài sản/luồng dữ liệu nào cần nằm trong scope? |
| Change inventory | Những thay đổi nào được triển khai, vào môi trường nào, lúc nào? |
| Positive test | Một hoạt động hợp lệ theo control phải được cho phép như thế nào? |
| Negative test | Hành vi không được phép có thực sự bị từ chối hay cảnh báo không? |
| Sampling | Kiểm tra toàn population hay lấy mẫu, chọn mẫu theo cách nào? |
| Operational period | Control cần vận hành trong bao lâu để đủ chứng minh hiệu lực? |
| Evidence | Log, policy, test result và chứng cứ độc lập nào phải lưu? |
| Pass/fail conditions | Điều kiện chính xác nào tạo PASS, FAIL hoặc INCONCLUSIVE? |
| Owner/assessor | Ai sửa, ai xác minh, ai duyệt quyết định đóng? |

Không nhất thiết mọi finding đều cần thử tấn công thực tế. Đối với control quản trị, có thể cần kiểm tra workflow, mẫu hồ sơ và chu kỳ thực hiện. Đối với IAM/network, controlled authorization test hoặc cấu hình hiệu lực có thể thích hợp. Phương pháp phải tương xứng với rủi ro, được cấp quyền và không làm hại production.

### 11.2. Retest hai lớp: correction và nguyên nhân

Với finding “tài khoản local quản trị thiếu MFA”:

1. **Kiểm tra correction:** hai tài khoản vi phạm ban đầu đã bị khóa, bị xóa hoặc được enforce MFA đúng không?
2. **Kiểm tra population:** toàn bộ principal tương tự thuộc scope có trường hợp nào khác không?
3. **Kiểm tra preventive control:** tạo một tài khoản thử theo workflow mới có buộc MFA hoặc bị chặn trước production không?
4. **Kiểm tra phát hiện drift:** khi giả lập một account không đúng policy trong môi trường thử, hệ thống có cảnh báo đúng không?
5. **Kiểm tra vận hành:** evidence cho thấy owner định kỳ rà soát các đường admin và exception như quy trình định nghĩa không?

Nếu chỉ bước 1 đạt, có thể kết luận **correction của hai đối tượng thành công**, nhưng chưa đóng được finding có nguyên nhân rộng hơn hoặc phạm vi remediation toàn hệ thống.

### 11.3. Mẫu retest record

~~~yaml
retest_id: "AUD-RT-2026-011"
finding_id: "AUD-F-2026-017"
control_id: "IAM-PRIV-01"
tested_at: "2026-11-28T10:20:00Z"
assessment_scope:
  service: "payments"
  environment: "production"
  population: "interactive-privileged-principals"
  evaluated_count: 18
baseline_version: "IAM-POL-07-v3"
methods:
  - "Reconcile privileged principal inventory with effective authentication policy"
  - "Check approved exceptions and validity"
  - "Execute controlled positive/negative auth tests on representative test paths"
implementation_refs:
  - "change/CHG-2026-119"
  - "policy/iam-mfa-v4"
evidence_refs:
  - "AUD-EV-2026-081"
  - "AUD-EV-2026-082"
  - "AUD-EV-2026-083"
observations:
  tested_noncompliant_principals: 0
  expired_exceptions: 0
  newly_created_test_principal_enforced: true
result: "PASS_WITH_SCOPE"
limitations:
  - "Chỉ đánh giá service payments trong phạm vi nguồn inventory đã xác minh"
  - "Không suy rộng đến các dịch vụ hoặc account nằm ngoài kỳ kiểm"
assessor_role: "security-assurance-reviewer"
closure_approval_ref: "audit-approval/AUD-017"
~~~

Tất cả số liệu và ID là ví dụ. Một bản retest thực tế cần có dữ liệu gốc và nguồn inventory đủ để người khác kiểm tra lại 18 principal, chứ không chỉ điền “noncompliant = 0”.

### 11.4. Khi chưa thể xác minh effectiveness ngay

Một số control phải vận hành qua thời gian: review quyền theo quý, backup restore theo kỳ, vulnerability remediation theo SLA hoặc alert escalation trong ca trực. Sau khi cập nhật procedure, vẫn có thể chưa đủ kỳ vận hành để xác minh effectiveness.

Khi đó:

- Ghi **đã triển khai thiết kế/correction**, chưa kết luận operating effectiveness.
- Định nghĩa **mốc bằng chứng tương lai** như lần review tiếp theo hoặc kỳ diễn tập đầu tiên.
- Duy trì finding ở trạng thái phù hợp (ví dụ AWAITING_VALIDATION) hoặc quyết định risk acceptance có thời hạn.
- Không lấy một mẫu walkthrough ngay sau thay đổi để khẳng định cả chu kỳ vận hành đã đạt.
- Cập nhật kết luận khi có record thực tế hoặc kết quả test bù trừ phù hợp.

## 12. Trạng thái finding, closure và reopening

### 12.1. State machine tham khảo

~~~mermaid
flowchart TD
    DRAFT["DRAFT: đang kiểm chứng dữ kiện"] --> CONF["CONFIRMED: evidence đủ"]
    CONF --> OPEN["OPEN: owner + kế hoạch"]
    OPEN --> PROG["IN_REMEDIATION"]
    PROG --> TEST["READY_FOR_RETEST"]
    TEST --> PASS{"Retest đạt scope?"}
    PASS -- "Có" --> CLOSED["CLOSED_VERIFIED"]
    PASS -- "Không" --> PROG
    OPEN --> ACC["ACCEPTED_RISK / EXCEPTION"]
    ACC --> REVIEW["REVIEW_AT_EXPIRY"]
    REVIEW --> PROG
    CLOSED --> REOPEN["REOPENED khi control tái vi phạm"]
    REOPEN --> PROG
~~~

Sơ đồ là ví dụ workflow, không phải chuẩn bắt buộc. Một chương trình có thể dùng các tên trạng thái khác, nhưng cần tránh đặt **RESOLVED** với ý nghĩa lẫn lộn giữa “owner nói đã sửa” và “assessor đã xác minh”.

### 12.2. Thẩm quyền đóng finding

Nên định nghĩa rõ:

- **Control owner:** cung cấp change record và bằng chứng sửa.
- **Assessor:** thực hiện hoặc đánh giá phép kiểm xác nhận control đạt.
- **Risk owner:** xem xét rủi ro còn lại và các ngoại lệ theo quyền hạn.
- **Audit lead/approval role:** phê duyệt closure theo quy trình và mức độ nghiêm trọng.
- **Independent reviewer (nếu cần):** kiểm tra các finding trọng yếu hoặc có tranh chấp.

Không nên để chính người triển khai một control quan trọng tự đánh PASS cuối cùng chỉ dựa vào mô tả công việc đã làm, khi chính sách yêu cầu review độc lập.

### 12.3. Bốn kiểu kết thúc khác nhau

| Kết quả xử lý | Ý nghĩa | Báo cáo nên thể hiện |
|---|---|---|
| **CLOSED_VERIFIED** | Retest đáp ứng criteria trên scope đã phê duyệt | Reference test, owner, approver, ngày đóng, giới hạn |
| **RISK_ACCEPTED** | Sai lệch/rủi ro còn tồn tại nhưng được chấp thuận có điều kiện | Risk owner, rationale, controls bù trừ, expiry và review |
| **NOT_APPLICABLE_RECLASSIFIED** | Criterion được xác nhận không áp dụng cho scope | Lý do, phê duyệt và tài liệu thay đổi phạm vi |
| **SUPERSEDED / MERGED** | Finding được gộp hoặc thay bằng finding khác đúng phạm vi | Liên kết mới, lý do, bảo toàn lịch sử, không mất action |

**RISK_ACCEPTED không phải một loại PASS.** Đội audit phải giữ dấu vết control gap và các điều kiện chấp nhận. Một finding bị gộp không được biến mất khỏi KPI nếu rủi ro chưa được xử lý.

### 12.4. Khi nào cần reopen?

Reopen hoặc tạo finding liên quan mới khi:

- Control từng được xác minh đạt nhưng phát hiện tái vi phạm trong cùng scope.
- Một change/deployment làm mất hiệu lực correction.
- Bằng chứng đóng trước đây bị chứng minh không đầy đủ hoặc sai.
- Ngoại lệ hết hạn mà remediation chưa đạt.
- Kiểm tra sau sự cố cho thấy nguyên nhân gốc vẫn tồn tại.

Cần phân biệt **lỗi tái diễn** với **một sai lệch mới ở scope khác**, để theo dõi root cause và trend chính xác.

## 13. Risk acceptance, exception và escalation

### 13.1. Khi remediation chưa thể thực hiện ngay

Một số rủi ro cần xử lý chậm vì phụ thuộc vendor, vòng nâng cấp hoặc thay đổi kiến trúc. Thay vì xóa finding hoặc ghi “accepted” tùy tiện, cần một hồ sơ:

1. **Finding ID và criterion:** control nào chưa đạt.
2. **Scope và dữ liệu:** tài sản, môi trường, thông tin bị ảnh hưởng.
3. **Risk rationale:** likelihood, tác động, compensating control và rủi ro còn lại.
4. **Owner và approver:** người có thẩm quyền thực sự chấp nhận rủi ro.
5. **Thời hạn và review:** khi nào phải khắc phục/tái đánh giá.
6. **Điều kiện giới hạn:** ví dụ chỉ trong sandbox hoặc chỉ có dữ liệu giả lập.
7. **Monitoring:** alert, kiểm tra thủ công, hạn chế quyền trong kỳ ngoại lệ.
8. **Exit criteria:** phép retest và điều kiện chuyển sang trạng thái verified.

Nếu tiêu chí gốc bắt buộc và không cho ngoại lệ, cần xử lý theo cơ chế không đáp ứng tương ứng; risk acceptance nội bộ không tự làm thay đổi nghĩa vụ theo hợp đồng hoặc pháp luật.

### 13.2. Escalation khi finding quá hạn

Ví dụ escalation policy nội bộ:

| Tình trạng | Xử lý |
|---|---|
| Action sắp hết hạn | Nhắc owner và báo nguy cơ trễ |
| Quá hạn không có bằng chứng | Escalate theo risk tier, giữ finding mở |
| Có giải pháp nhưng chưa retest | Giữ AWAITING_VALIDATION, phân công người kiểm chứng |
| Có ngoại lệ mới | Yêu cầu phê duyệt theo quyền hạn và expiry |
| Rủi ro tăng do thay đổi | Đánh giá lại severity, scope, hạn và biện pháp tức thời |
| Có sự cố liên quan finding | Liên kết incident, bảo toàn evidence và điều chỉnh kế hoạch |

Thời hạn và cấp escalation do tổ chức phê duyệt; không nên sáng tác SLA chung áp cho mọi công ty hoặc mọi framework.

### 13.3. Không dùng chấp nhận rủi ro để che mất dữ kiện

Một finding nên giữ nguyên evidence cho thấy điều kiện không đạt, ngay cả khi risk owner lựa chọn vận hành tiếp với biện pháp bù trừ. Không sửa lại bản đánh giá từ FAIL thành PASS chỉ vì đã ký ngoại lệ. Hai câu hỏi là khác nhau:

- **Control đã đạt criterion?**
- **Tổ chức đã ra quyết định chấp nhận residual risk đúng thẩm quyền?**

Một cuộc audit có thể cần đưa cả hai kết quả vào báo cáo.

## 14. Mẫu finding record có thể dùng lại

### 14.1. Schema YAML tham khảo

~~~yaml
finding_id: "AUD-F-2026-017"
assessment_id: "AUD-2026-Q4-PAY"
title: "Interactive production admin paths lack MFA enforcement"
status: "OPEN"
reported_at: "2026-11-28T09:00:00Z"
last_updated_at: "2026-11-28T09:00:00Z"
control:
  control_id: "IAM-PRIV-01"
  criterion_ref: "IAM-POL-07-v3"
  assertion: "All interactive privileged access paths enforce MFA"
scope:
  service: "payments"
  environment: "production"
  population_source: "privileged-principal-inventory"
  population_count: 18
  inspected_count: 18
  affected_count: 2
condition: >
  Two local privileged identities were outside the effective
  MFA enforcement policy during the assessment.
evidence:
  - "AUD-EV-2026-041"
  - "AUD-EV-2026-042"
  - "AUD-EV-2026-043"
cause:
  status: "HYPOTHESIS"
  description: "Legacy local identity provisioning may bypass the policy"
risk:
  severity: "HIGH"
  confidence: "HIGH_FOR_CONDITION"
  potential_impact: "Unauthorized privileged access if credentials are compromised"
  observed_incident: "NOT_ESTABLISHED"
recommendation: >
  Close MFA bypass paths, enforce control at provisioning,
  and monitor privileged identities outside the enforcement scope.
ownership:
  control_owner: "identity-team"
  risk_owner: "payments-risk-owner"
  assessment_owner: "security-assurance-team"
remediation:
  action_ids: ["AC-01", "AC-02", "AC-03"]
  target_date: "2026-12-05"
  expected_retest: "Reconcile entire population and test effective auth paths"
  evidence_refs: []
exceptions:
  status: "NONE_VALIDATED"
assurance:
  verdict: "FAIL"
  scope_limitations:
    - "Chỉ bao phủ service payments và đường admin đã xác định"
history:
  - timestamp: "2026-11-28T09:00:00Z"
    action: "confirmed"
    actor_role: "audit-reviewer"
~~~

Đây là dữ liệu ví dụ, không mô tả kết quả audit thực tế và không phải schema chuẩn của hệ thống GRC. Cấu trúc nhấn mạnh sự khác biệt giữa **condition chắc chắn**, **cause còn là hypothesis**, **risk có thể xảy ra**, **verdict không đạt** và **owner sửa/owner chấp nhận rủi ro**.

### 14.2. Phiên bản và audit trail

Khi một finding thay đổi severity, scope hoặc root cause, nên giữ lịch sử:

- Phiên bản criterion đang áp dụng tại thời điểm phát hiện và tại retest.
- Thời gian thay đổi, người cập nhật và bằng chứng mới.
- Lý do thay severity, deadline hoặc risk decision.
- Ngày implement correction và ngày retest độc lập.
- Liên kết finding gộp, bị thay thế hoặc được mở lại.
- Quyền xem, sửa và phê duyệt hồ sơ theo phân quyền.

Nếu system được đổi chính sách sau khi audit, không tự ý viết lại lịch sử rằng tại kỳ cũ policy khác. Phân biệt **đã thay requirement** với **đã sửa implementation để đáp ứng requirement**.

### 14.3. Bản trình bày cho người ra quyết định

Một bảng tóm tắt nên có đủ:

| Finding ID | Control gap | Risk severity | Status | Owner | Due | Retest |
|---|---|---|---|---|---|---|
| AUD-F-017 | MFA admin local chưa enforce toàn scope | High (ví dụ) | Open | Identity team | 05/12 | Chưa thực hiện |
| AUD-F-018 | Audit log nguồn X chưa đến kho trung tâm | High (ví dụ) | In remediation | Platform team | 08/12 | Chờ dữ liệu |
| AUD-F-019 | DR test chưa chứng minh RPO | Medium/High tùy BIA | Awaiting validation | Resilience team | 12/12 | Lên kế hoạch |
| AUD-F-020 | Policy review có minh chứng đầy đủ | Không phải gap mới | Closed verified | GRC team | — | PASS trong scope |

Bảng chỉ là ví dụ, không thay thế evidence register. Có thể tách **finding của audit** với **test đã đạt** để không tạo record closure không có lịch sử lỗi nếu hệ thống chỉ lưu nonconformities.

## 15. Case study 1: audit log cloud bị thiếu nhưng dashboard vẫn xanh

Một tổ chức vận hành dịch vụ tài chính trên nhiều cloud account. Security baseline yêu cầu các hành động thay đổi chính sách IAM production phải được thu vào kho audit tập trung, bảo quản trong kỳ quy định, và việc mất nguồn log phải được phát hiện.

Đội audit kiểm tra một account mới vừa đưa vào production. Dashboard của SIEM báo các collector đang hoạt động bình thường. Tuy nhiên, inventory cấp tổ chức có **25 account** trong khi danh sách nguồn SIEM chỉ có **24**.

### 15.1. Xác lập criterion và condition

**Criterion (giả định):** mọi account production trong danh mục cần có cloud control-plane audit log về thay đổi IAM, được gửi đến log store tập trung và có monitoring khi mất luồng.

**Condition đã kiểm:**

- Account A thuộc inventory production, được xác nhận đang hoạt động.
- Account A không xuất hiện trong danh sách nguồn ingested của SIEM trong kỳ kiểm.
- Log tại nguồn của account A có một sự kiện thay đổi policy test hợp lệ được tạo theo phê duyệt.
- Không tìm thấy sự kiện đó trong centralized log index sau cửa sổ chờ hợp lệ.
- Dashboard “100% collector healthy” chỉ tính những collector đã được onboarding.

### 15.2. Evidence register ví dụ

| Evidence ID | Nội dung | Chứng minh điều gì | Giới hạn |
|---|---|---|---|
| E-101 | Cloud organization account inventory | Account A thuộc scope production | Chỉ phản ánh mốc export |
| E-102 | SIEM data-source inventory | A không nằm trong nguồn đã đăng ký | Có thể ingestion dùng tên mapping khác, cần đối soát |
| E-103 | Audit event test ở nguồn A | Event IAM đã phát sinh | Chỉ chứng minh event mẫu |
| E-104 | Kết quả truy vấn index theo source/event ID | Event test chưa tìm thấy ở đích trong kỳ | Cần kiểm tra retention, lag và filter |
| E-105 | Collector routing/pipeline config | Không cấu hình route cho A | Có thể là nguyên nhân kỹ thuật đã xác minh |
| E-106 | Baseline và onboarding procedure | Yêu cầu audit và cách bàn giao | Phải xác minh phiên bản, hiệu lực |

Một auditor nên kiểm tra thêm khả năng event bị gắn sai account ID hoặc đi sang index khác trước khi xác nhận sự thiếu hụt; nếu không, có thể kết luận sai do truy vấn tìm kiếm quá hẹp.

### 15.3. Viết finding

**F-LOG-01 — Account production mới chưa đưa audit IAM vào luồng thu tập trung.**

- **Criteria:** baseline quản lý logging yêu cầu nguồn audit IAM của mọi account production được gửi và giám sát tại central log store.
- **Condition:** account A trong inventory production không có luồng đến store trung tâm; event thử được xác nhận ở nguồn nhưng không thấy tại đích theo phương pháp E-104 và cấu hình routing E-105.
- **Risk:** hành động quản trị quan trọng trong account A có thể không được giám sát/điều tra kịp thời; nếu hệ thống nguồn bị can thiệp hoặc hết retention, thông tin có thể không khôi phục được.
- **Cause:** kết quả đối chiếu E-105 với workflow cho thấy cấu hình onboarding chưa tạo log sink cho account mới; nguyên nhân quy trình provisioning chưa tự động bật sink cần phân tích tiếp.
- **Scope:** account A, event class IAM, kỳ test; chưa khẳng định mọi event của account trong quá khứ đều bị mất.
- **Recommendation:** bảo đảm onboarding account tự cấu hình audit sink, kiểm tra từ nguồn đến SIEM và phát hiện tài sản không có telemetry.

### 15.4. Action và retest

1. Cấu hình nguồn audit và đích nhận cho account A, review quyền sửa/xóa sink.
2. Thực hiện event test mới có marker và xác minh có mặt tại source/collector/SIEM trong độ trễ quy định.
3. Đối soát toàn bộ **25 account** với nguồn event bắt buộc; không chỉ kiểm tra account A.
4. Tạo provisioning gate: account production mới không được hoàn tất khi chưa xác minh log flow.
5. Bổ sung alert định kỳ khi inventory xuất hiện account không có dữ liệu hoặc heartbeat kỳ vọng.
6. Đánh giá khả năng thu bổ sung dữ liệu lịch sử, ghi rõ khoảng không thể chứng minh.

**Closure assertion:** tất cả account production thuộc inventory được đánh giá có luồng event phù hợp, alert khi source im lặng hoạt động trong controlled test, và policy được áp lên account mới khi provision. Nếu chỉ hiện một log ở dashboard, điều kiện đóng chưa đủ.

## 16. Case study 2: backup được ghi “PASS” nhưng không có bằng chứng restore

Dịch vụ đơn hàng có BIA yêu cầu RTO 120 phút và RPO 15 phút. Đội vận hành trả lời audit: “Backup job thành công 100% và có kế hoạch DR được phê duyệt.” Auditor tìm thấy:

- Cấu hình backup và kết quả job đều ghi thành công.
- Có tài liệu runbook đã review.
- Chưa có diễn tập restore dịch vụ đầu cuối trong kỳ đánh giá.
- Backup dùng khóa thuộc account chính; chưa có bằng chứng giải mã ở account recovery.
- Kết quả thử một database nhỏ trong sandbox không đại diện cho khối lượng production.

### 16.1. Không tạo finding sai loại

Có thể tách ba assertion:

| Assertion | Bằng chứng hiện có | Verdict tham khảo |
|---|---|---|
| Backup được tạo theo kỳ yêu cầu | Job log và backup inventory hợp lệ | **PASS_WITH_SCOPE** cho backup creation |
| Có khả năng khôi phục dữ liệu và khóa khi primary mất | Không có test restore account DR | **INCONCLUSIVE** hoặc FAIL nếu criterion yêu cầu thử restore và không thực hiện |
| Dịch vụ đáp ứng RTO/RPO theo kịch bản mất primary | Chưa có end-to-end exercise đo T0/T1/Tdata | **NOT_TESTED/FAIL** tùy đúng criterion và kỳ |

Nếu criterion bắt buộc **phải diễn tập DR ít nhất một lần trong năm**, việc không có hồ sơ và xác nhận chưa diễn tập có thể đủ chứng minh **nonconformity về yêu cầu diễn tập**. Nhưng nó không tự chứng minh “chắc chắn không thể khôi phục”.

### 16.2. Finding và hành động

**F-DR-02 — Chưa chứng minh hiệu lực phục hồi dịch vụ theo RTO/RPO đã được phê duyệt.**

- **Condition:** không có bài test đầu cuối theo scope/kỳ được yêu cầu; kết quả backup job chỉ chứng minh một phần chuỗi.
- **Risk:** sau mất primary, có thể không giải mã/khôi phục được dữ liệu, hoặc phục hồi quá ngưỡng nghiệp vụ, gây gián đoạn và mất dữ liệu.
- **Recommendation:** thực hiện diễn tập restore có đo mốc, kiểm tra key/identity/network, độ nhất quán database/message và chức năng nghiệp vụ.
- **Action:** phân công resilience owner, lập runbook, chạy bài test ở môi trường phù hợp, lưu evidence và khắc phục lỗi được phát hiện.
- **Retest:** kiểm tra T0/T1/Tdata, điểm dữ liệu cuối nhất quán, security gates và kết luận RTO/RPO theo kịch bản; không chỉ cần “restore finished”.

### 16.3. Bài học cho assurance

Câu “có backup” là một **design/implementation claim**. Câu “có thể phục hồi dịch vụ trong 2 giờ, mất tối đa 15 phút dữ liệu” là một **outcome claim**. Outcome cần thử và bằng chứng khác với config.

Một finding tốt phân tách **điểm thiếu kiểm thử** với **tình trạng kỹ thuật chưa biết**, nhờ đó đội khắc phục biết cần bổ sung bằng chứng gì mà không bị yêu cầu chứng minh điều bất khả thi.

## 17. Khi finding liên quan bên thứ ba hoặc nhiều đội

Security controls hiện đại thường được chia sẻ giữa application, platform, cloud provider, identity provider, nhà cung cấp SaaS và đội SOC. Nếu một control không đạt, cần xác định:

- Bên nào sở hữu requirement và risk acceptance?
- Bên nào triển khai/điều hành control ở từng đoạn?
- Ai có quyền sửa cấu hình, ai kiểm chứng?
- Bằng chứng của vendor bao phủ đúng dịch vụ, region, kỳ và responsibility boundary nào?
- Có subprocessor hoặc hệ thống phụ thuộc bị loại trừ?
- Nếu nhiều đội liên quan, có owner chịu trách nhiệm đầu cuối không?

Ví dụ, SaaS cung cấp audit log nhưng khách hàng phải **bật export**. Nếu dữ liệu không tới SIEM, finding nên ghi rõ trách nhiệm cấu hình và kiểm tra của cả hai bên, không tự quy trách nhiệm toàn bộ cho vendor chỉ vì dịch vụ do vendor cung cấp.

### 17.1. Phát hiện tranh chấp trách nhiệm

Một tình huống phổ biến:

- Platform team nói SOC chưa tạo rule.
- SOC nói platform chưa gửi log.
- Application team nói log có ở stdout.
- Vendor nói customer chưa bật audit export.

Auditor cần **truy cùng một event** qua source → pipeline → rule/alert, đối chiếu shared responsibility, rồi giao action tương ứng từng mắt xích. Không để finding treo vì các bên liên tục chuyển trách nhiệm.

### 17.2. Evidence từ nhà cung cấp

Một báo cáo độc lập của vendor có thể hữu ích, nhưng phải kiểm tra:

- Service và hệ thống thuộc scope.
- Thời kỳ báo cáo và những thay đổi sau đó.
- Kết quả, ngoại lệ, hạn chế và trách nhiệm bổ sung của khách hàng.
- Các control ngoài phạm vi được chứng nhận/đánh giá.
- Mức tin cậy của bằng chứng đối với criterion cụ thể.

Không suy rộng một chứng nhận hoặc kết quả kiểm thử ở một sản phẩm sang tất cả sản phẩm trong hệ sinh thái vendor.

## 18. Giao tiếp audit finding và quyền truy cập thông tin

### 18.1. Ba đối tượng đọc chính

| Đối tượng | Cần biết | Mức chi tiết |
|---|---|---|
| **Control owner/technical team** | Condition, evidence, reproduction, root cause, giải pháp, retest | Kỹ thuật chi tiết nhưng không chia sẻ secret trái quyền |
| **Risk/business owner** | Tác động nghiệp vụ, severity, deadline, lựa chọn giảm rủi ro, quyết định mở | Tóm tắt rõ phạm vi, mức bất định |
| **Audit/security assurance** | Criterion, population, phương pháp, evidence integrity, review trail và closure | Truy vết đầy đủ với quyền hạn phù hợp |

### 18.2. Giữ ngôn ngữ trung lập

Auditor nên chỉ ra điều được chứng minh, không đưa nhận xét về tính cách hoặc động cơ của một cá nhân.

Chưa tốt:

> “Đội vận hành cẩu thả nên làm rò rỉ hệ thống.”

Tốt hơn:

> “Quy trình cấp quyền hiện tại không yêu cầu xác minh quyền hiệu lực sau khi triển khai. Kết quả sample cho thấy ba role có quyền ngoài baseline; chưa tìm thấy evidence truy xuất dữ liệu trái phép trong các nguồn đã kiểm.”

### 18.3. Khi có dấu hiệu incident thực sự

Nếu trong audit xuất hiện bằng chứng trực tiếp về hành vi tấn công đang diễn ra, không nên chỉ chờ kỳ báo cáo audit. Cần kích hoạt quy trình incident handling/escalation phù hợp với severity, bảo toàn chứng cứ và giới hạn quyền phân phối. Audit finding và incident case có thể liên kết, nhưng **không thay thế quy trình ứng cứu khẩn cấp**.

### 18.4. Bảo mật báo cáo và chứng cứ

Tài liệu có thể tiết lộ lỗ hổng chưa sửa, đường quản trị, tài khoản đặc quyền, kiến trúc và dữ liệu khách hàng. Nên có classification, quyền theo vai trò, lưu trữ audit trail, chính sách retention và cơ chế redaction khi chia sẻ. Báo cáo lãnh đạo có thể che ID nhạy cảm nhưng vẫn giữ bằng chứng gốc trong kho phù hợp để auditor tái kiểm.

## 19. KPI cho chương trình quản lý finding

Một dashboard có ý nghĩa không chỉ đếm số finding mở/đóng mà phải theo dõi **tác động, thời gian xử lý, hiệu lực retest và độ bao phủ của việc kiểm tra**.

### 19.1. Metrics tham khảo

| KPI | Cách đo | Giới hạn diễn giải |
|---|---|---|
| **Open findings by severity** | Finding mở phân theo mức rủi ro và tuổi | Nhiều finding hơn có thể do audit sâu hơn, không nhất thiết hệ thống tệ hơn |
| **Overdue findings** | Finding quá hạn chưa đạt điều kiện xử lý / tổng finding đã đến hạn | Cần tránh đổi deadline tùy tiện để làm KPI đẹp |
| **Remediation cycle time** | Từ finding xác nhận đến triển khai correction | Không chứng minh retest đã đạt |
| **Verified closure time** | Từ confirmed finding đến retest PASS + phê duyệt đóng | Phải ghi rõ nhóm finding và thời gian thực tế |
| **Retest pass rate** | Retest PASS / tổng retest có kết quả hợp lệ | Không phản ánh những finding chưa được đưa đi retest |
| **Reopened/recurrence rate** | Finding tái vi phạm sau verified closure / tổng finding liên quan | Cần chuẩn hóa mã nguyên nhân và scope |
| **Evidence quality gap** | Assertion thiếu evidence thích hợp / assertion thuộc phạm vi cần đánh giá | Không coi evidence thiếu thành control FAIL không căn cứ |
| **Control coverage** | Control trong scope đã được xác minh / tổng control phải đánh giá | Mẫu số phải lấy từ control register, không chỉ từ control đã test |
| **Critical exception overdue** | Ngoại lệ critical hết hạn chưa được xử lý / tổng ngoại lệ đến hạn | Ngoại lệ không có expiry cũng cần cảnh báo |
| **Repeat root causes** | Nhóm finding có cùng nguyên nhân qua các kỳ | Dữ liệu RCA phải có mức confidence và đủ tính nhất quán |
| **Finding aging by owner** | Tuổi finding theo đội/dịch vụ | Không nên làm lệch severity để đạt chỉ tiêu |
| **Closure validation coverage** | Finding đã đóng có test/evidence/approval phù hợp / tổng finding đóng | Tránh đóng chỉ bằng ticket Done |

### 19.2. Tránh KPI tạo hành vi xấu

Nếu đánh giá đội kỹ thuật chủ yếu theo **số finding đóng**, họ có thể:

- Đổi tên finding để loại khỏi mẫu số.
- Hạ severity hoặc lùi hạn không có căn cứ.
- Đóng finding sau khi sửa tài liệu chứ chưa sửa control.
- Bỏ qua scope có vấn đề vì chưa kiểm được.
- Xem accepted risk như verified closure.

Nên phối hợp **risk-weighted backlog**, chất lượng bằng chứng, tỷ lệ retest đạt, mức tái diễn và độ bao phủ audit. Không dùng metric để khuyến khích che giấu sự không chắc chắn.

### 19.3. Ví dụ tính chỉ số

Giả sử một chương trình có 40 finding thuộc kỳ theo dõi:

- 12 được retest PASS và đã phê duyệt đóng.
- 8 đã triển khai correction nhưng chưa đủ bằng chứng retest.
- 14 đang remediation.
- 4 có risk acceptance còn hiệu lực.
- 2 đang tranh luận điều kiện áp dụng và được đánh INCONCLUSIVE.

Nếu chỉ đếm “đã xử lý” = 12 + 8 + 4 = 24 thì dễ báo **60% hoàn thành** nhưng con số này gộp ba trạng thái khác nhau.

Báo cáo đúng hơn:

- **Verified closure coverage:** 12/40 = 30%.
- **Implemented, awaiting validation:** 8/40 = 20%.
- **In remediation:** 14/40 = 35%.
- **Risk accepted under conditions:** 4/40 = 10%.
- **Needs criterion/evidence resolution:** 2/40 = 5%.

Những con số là giả định; việc quyết định một tỷ lệ có “tốt” hay không phải xét severity, kỳ đánh giá và yêu cầu xử lý.

## 20. Continuous assurance: biến finding thành kiểm soát tái diễn

### 20.1. Liên kết finding với các hệ thống vận hành

Một finding có thể dẫn đến nhiều thay đổi:

- **Architecture baseline:** thay thiết kế để loại bỏ điểm lỗi.
- **Policy-as-code/IaC:** kiểm tra sớm cấu hình trước khi lên production.
- **CI/CD gating:** chặn deployment không đáp ứng control cần thiết.
- **Detection rules:** cảnh báo khi một cấu hình vi phạm tái xuất hiện.
- **Asset/identity inventory:** bổ sung đối tượng bị bỏ sót khỏi population.
- **Training/runbook:** hướng dẫn vận hành khắc phục nguyên nhân quy trình.
- **Risk register:** quản lý rủi ro chưa xử lý đủ.
- **Audit test suite:** giữ lại test case dẫn đến finding để kiểm tra regression.

Ví dụ, finding “cloud account mới không gửi audit log” nên dẫn đến **provisioning gate và kiểm tra inventory** để những account tiếp theo không tái phạm, chứ không chỉ bật log ở account đã phát hiện.

### 20.2. Triggers kiểm tra lại

- Onboard tài sản/tài khoản mới.
- Thay IAM/role, authentication flow hoặc break-glass.
- Thay cloud region, KMS, log sink và retention.
- Thay pipeline CI/CD, image base, runtime hoặc policy.
- Bổ sung vendor hoặc subprocessor có quyền truy cập mới.
- Phát hiện incident liên quan control đã từng fail.
- Bằng chứng cho thấy điều kiện PASS trước đây không còn đúng.
- Đến kỳ audit, access review, DR exercise hoặc ngoại lệ hết hạn.

Đối với control có thể tự động hóa, một test regression có thể chạy khi change và theo lịch. Với control cần judgment hoặc phê duyệt con người, phải có workflow/hồ sơ phù hợp.

### 20.3. Mô hình đóng vòng

~~~mermaid
flowchart LR
    AUD["Audit finding + evidence"] --> ROOT["Root cause & risk decision"]
    ROOT --> FIX["Correction + preventive control"]
    FIX --> RET["Retest theo assertion"]
    RET --> DEC{"PASS với scope?"}
    DEC -- "Không" --> ROOT
    DEC -- "Có" --> BAS["Cập nhật baseline / test / runbook"]
    BAS --> MON["Continuous monitoring + drift"]
    MON --> CHANGE["Change hoặc kỳ audit mới"]
    CHANGE --> AUD
~~~

Nếu một finding mở lại nhiều lần, cần xem nguyên nhân gốc, trách nhiệm và khả năng của hệ thống kiểm soát, không chỉ giao thêm một correction tương tự. Tái diễn có thể là dấu hiệu rằng **design assurance** hoặc change management chưa giải quyết được vấn đề.

## 21. Các sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Auditor không tìm thấy hồ sơ nên control chắc chắn không tồn tại.” | Phải tách evidence deficiency khỏi control failure đã xác nhận. |
| “Một sample fail nghĩa là 100% population fail.” | Kết luận chỉ áp cho sample hoặc population đã kiểm; muốn suy rộng phải có phương pháp phù hợp. |
| “Control được ghi trong policy nên hoạt động hiệu quả.” | Policy chứng minh design, cần evidence implementation/operating effectiveness. |
| “Bật MFA ở SSO nghĩa là mọi admin được bảo vệ.” | Phải tính local, API, break-glass và các đường quyền trong scope. |
| “Có vulnerability là đã xảy ra incident.” | Vulnerability là khả năng bị khai thác; incident cần bằng chứng và phân loại riêng. |
| “Risk critical vì auditor thấy đáng sợ.” | Severity phải có risk rationale và phương pháp xếp hạng nhất quán. |
| “Finding thiếu cause nên không được ghi.” | Có thể ghi finding với condition rõ và cause ở trạng thái hypothesis đang xác minh. |
| “Khắc phục hai tài khoản trong mẫu là đủ.” | Cần xem toàn population và provisioning root cause. |
| “Ticket Done là finding đã đóng.” | Retest + phê duyệt theo assertion, scope và kỳ mới cho closure verified. |
| “Risk accepted nghĩa là control PASS.” | Risk acceptance và compliance/control verdict là hai trục khác nhau. |
| “Giữ checksum cạnh log là bảo đảm chứng cứ nguyên vẹn.” | Cần trust anchor, quản lý quyền và chuỗi xử lý chứng cứ phù hợp. |
| “Không có incident trong log nghĩa là rủi ro thấp.” | Logging có thể thiếu; không có bằng chứng không chứng minh không xảy ra. |
| “Sửa severity sẽ làm biến mất rủi ro.” | Điều chỉnh severity cần có evidence mới hoặc thay đổi risk context. |
| “Không cần giữ lịch sử khi gộp finding.” | Giữ mapping và audit trail để tránh mất obligation và che KPI. |
| “Một lần retest PASS chứng minh control sẽ luôn đạt.” | Cần monitor drift, regression và kiểm tra khi hệ thống thay đổi. |
| “Report càng nhiều dữ liệu thô càng tốt.” | Evidence phải đủ và truy xuất được nhưng bảo mật thông tin nhạy cảm. |

## 22. Bài tập tự kiểm tra

**Câu 1.** Một tổ chức có policy yêu cầu quarterly access review. Auditor chỉ nhận được role export ở thời điểm audit, không có hồ sơ review của các quý trước. Nên ghi kết luận gì?

**Gợi ý:** Export chỉ hỗ trợ kiểm tra trạng thái quyền hiện tại. Cần thêm hồ sơ phê duyệt/review theo kỳ để đánh giá operating effectiveness; nếu không có evidence, ghi evidence deficiency hoặc nonconformity về lưu hồ sơ khi criterion cụ thể yêu cầu.

**Câu 2.** Auditor kiểm tra 12 trong 400 endpoint có quyền đặc biệt, phát hiện ba endpoint thiếu EDR. Có thể nói 25% toàn bộ endpoint thiếu EDR không?

**Gợi ý:** Không nếu mẫu không đại diện ngẫu nhiên hoặc chưa kiểm toàn bộ. Ghi 3/12 trong mẫu và phương pháp chọn mẫu; mở rộng kiểm tra population theo mức rủi ro.

**Câu 3.** Finding đã mở vì hai principal thiếu MFA. Owner bật MFA cho hai principal rồi đóng ticket. Những gì còn thiếu để closure verified?

**Gợi ý:** Cần đối soát inventory phạm vi, test effective auth paths, kiểm tra exception, nguyên nhân provisioning và bằng chứng retest; đóng theo thủ tục phê duyệt phù hợp.

**Câu 4.** Báo cáo viết “Công ty đã bị đánh cắp dữ liệu” dựa vào việc một role có quyền đọc bucket quá rộng. Có đúng không?

**Gợi ý:** Không. Quyền quá rộng là risk/condition; hành vi đọc hoặc exfiltration phải có evidence độc lập. Nêu potential impact và phạm vi chưa biết.

**Câu 5.** Nhà cung cấp phản hồi đã có SOC 2 report, nhưng dịch vụ đang đánh giá ngoài scope của report. Có thể dùng report để đóng finding không?

**Gợi ý:** Không suy rộng. Cần evidence đúng service/control/kỳ hoặc test thay thế; nếu thiếu thì giữ INCONCLUSIVE hoặc finding theo criterion.

**Câu 6.** Nguyên nhân của finding chưa được xác định nhưng condition và criterion đã rõ. Có nên chờ RCA hoàn chỉnh trước khi lập finding?

**Gợi ý:** Không nhất thiết. Có thể lập finding có căn cứ, ghi cause ở trạng thái chưa xác minh và yêu cầu điều tra như một action.

**Câu 7.** Auditor thấy một tài khoản quản trị không có MFA nhưng có ngoại lệ được risk owner phê duyệt, còn hiệu lực và được phép theo policy. Có nên chấm FAIL giống trường hợp không có ngoại lệ không?

**Gợi ý:** Phải xem criterion có cho phép ngoại lệ, ngoại lệ có bao phủ đúng scope, bù trừ thực sự và evidence đầy đủ không. Nếu thỏa criterion, có thể khác với FAIL; vẫn ghi residual risk/exception và review khi hết hạn.

**Câu 8.** Một finding có severity HIGH nhưng confidence LOW vì log nguồn thiếu. Có nên hạ severity xuống LOW cho khớp confidence không?

**Gợi ý:** Không tự động. Severity dựa trên rủi ro; confidence phản ánh mức tin cậy của condition/impact. Cần đánh dấu bất định và ưu tiên thu evidence hoặc áp biện pháp bảo vệ theo risk context.

**Câu 9.** Đội audit muốn chấp nhận cấu hình đã sửa mà chưa qua một chu kỳ vận hành. Nên ghi trạng thái nào?

**Gợi ý:** Có thể ghi correction implemented, design verified và AWAITING_OPERATIONAL_VALIDATION, tùy quy tắc tổ chức. Không khẳng định operating effectiveness cả kỳ nếu chưa có dữ liệu.

**Câu 10.** Một finding bị reopened sau khi đã VERIFIED CLOSED. Cần điều tra vấn đề gì ngoài lỗi cấu hình vừa xuất hiện?

**Gợi ý:** Cần xem nguyên nhân tái diễn, change management, regression checks, ownership, thời điểm drift và tính đầy đủ của closure scope trước đó.

## 23. Bài thực hành: viết audit finding cho hệ thống production

Bạn là security assurance assessor trong một công ty vận hành nền tảng thanh toán. Tổ chức yêu cầu **mọi thay đổi quyền trên production phải được phê duyệt, ghi audit và có thể điều tra**, tài khoản quản trị tương tác phải dùng MFA, còn quyền truy cập dữ liệu được đánh giá theo nguyên tắc tối thiểu.

**Dữ kiện giả định:**

- Inventory hiện có 40 principal privileged production; 34 thuộc SSO và sáu là tài khoản local.
- MFA policy được enforce cho toàn bộ 34 tài khoản SSO. Trong sáu tài khoản local, hai có exception hợp lệ còn thời hạn, hai đã vô hiệu hóa, hai tài khoản hoạt động không có MFA hoặc ngoại lệ.
- Audit log của cloud account A đến SIEM, nhưng account B mới tạo chưa được onboard audit feed.
- Đội vận hành cung cấp change ticket của account B nhưng chưa có dấu vết event trong SIEM.
- Owner đã sửa hai tài khoản MFA bằng IAM policy mới, nhưng chưa có retest đường local login.
- Trong kỳ trước đã xuất hiện finding tương tự tại một service khác; root cause ở đây chưa rõ.
- Không có evidence cho thấy các tài khoản thiếu MFA thực sự bị chiếm quyền.

**Nhiệm vụ:**

1. Viết ít nhất **hai finding khác nhau**: một về MFA scope, một về thiếu audit feed.
2. Với mỗi finding, định nghĩa criterion, condition, scope, population, evidence, risk, confidence, root-cause hypothesis, recommendation và severity rationale.
3. Tách rõ nhóm tài khoản **có ngoại lệ hợp lệ**, **đã vô hiệu hóa** và **hoạt động nhưng thiếu kiểm soát**.
4. Không suy rộng số lượng lỗi ở account B sang các account khác khi chưa có inventory/evidence.
5. Tạo evidence register với ít nhất sáu E-ID: inventory, authentication policy, test event, log route, exception, provisioning workflow.
6. Lập corrective/preventive action plan có owner, due date và test dương/âm.
7. Thiết kế retest chứng minh kết quả trên toàn 40 principal hoặc giải thích tại sao population phải thay đổi; kiểm tra cả onboarding cloud account mới.
8. Mô tả rủi ro còn lại và khi nào cần risk acceptance có thời hạn.
9. Đề xuất một KPI đo verified closure và một KPI phát hiện control drift trong tương lai.

**Tiêu chí đánh giá:**

| Tiêu chí | Đạt khi |
|---|---|
| Bằng chứng | Mọi claim quan trọng liên kết evidence ID và nguồn |
| Đúng phạm vi | Không suy rộng vượt population hoặc kỳ đã kiểm |
| Criteria | Yêu cầu có hiệu lực, gắn scope chính xác |
| Nguyên nhân | Tách confirmed cause khỏi hypothesis |
| Rủi ro | Tác động tiềm tàng không bị viết thành incident đã xảy ra |
| Kế hoạch | Có owner, thời hạn, correction và preventive control |
| Retest | Có tiêu chí PASS và phép kiểm hiệu lực rõ ràng |
| Governance | Trạng thái và risk acceptance không bị nhầm với control PASS |

## 24. Checklist trước khi phát hành hoặc đóng audit finding

- [ ] Finding có ID, tiêu đề cụ thể, owner, severity và kỳ đánh giá.
- [ ] Criterion có nguồn, phiên bản, phạm vi và thời điểm có hiệu lực.
- [ ] Condition mô tả tình trạng quan sát được, không chứa suy diễn hoặc tính từ cảm tính.
- [ ] Có population, sample size và phương pháp chọn mẫu.
- [ ] Evidence có ID, nguồn, thời gian, phương pháp thu và khả năng truy xuất.
- [ ] Evidence đủ, liên quan, đáng tin, còn hiệu lực và phù hợp scope.
- [ ] Có kiểm soát tính toàn vẹn, quyền truy cập và dữ liệu nhạy cảm phù hợp.
- [ ] Phân biệt design, implementation, operating effectiveness và monitoring.
- [ ] Tách impact đã xảy ra khỏi potential impact và unknown.
- [ ] Severity có risk rationale, confidence được đánh giá riêng.
- [ ] Root cause chỉ ghi là confirmed khi có bằng chứng; nếu chưa thì đánh hypothesis.
- [ ] Đã cho control owner xác minh factual accuracy và ghi các bất đồng.
- [ ] Recommendation nhắm đến mục tiêu control và ngăn tái diễn.
- [ ] Action có scope, owner, hạn, dependency, expected result và acceptance criteria.
- [ ] Retest có test plan, population, positive/negative cases và bằng chứng mới.
- [ ] Trạng thái “implemented” không bị nhầm với “verified closed”.
- [ ] Risk acceptance/exception có phê duyệt, phạm vi, hạn và biện pháp bù trừ.
- [ ] Closure lưu reviewer, approver, thời gian, scope, residual risk và test result.
- [ ] Có cơ chế reopen/tái đánh giá khi control drift hoặc finding tái diễn.
- [ ] Dashboard tách verified closure, pending retest, accepted risk và evidence gaps.
- [ ] Những finding quan trọng đã được chuyển thành CI/CD gate, monitoring hoặc regression test khi thích hợp.

## Kết luận

**Audit finding là cầu nối giữa một yêu cầu bảo mật với tình trạng thực tế được chứng minh bằng bằng chứng.** Một finding tốt có criterion đúng hiệu lực, condition cụ thể, phương pháp kiểm tra minh bạch, evidence đáng tin, phạm vi và giới hạn rõ, phân tích rủi ro công bằng, root cause được xác minh khi có thể, và hành động khắc phục có thể kiểm thử.

Trong **SECURITY_SECURITY_ASSURANCE**, công việc không dừng ở việc phát hành báo cáo hay chuyển ticket sang Done. Chương trình assurance có giá trị khi **mỗi finding được truy vết đến control, owner, corrective action, retest và quyết định rủi ro có thẩm quyền**, đồng thời các bài học được chuyển thành kiểm soát phòng ngừa, giám sát drift và đánh giá liên tục. Khi đó, audit giúp hệ thống thực sự cải thiện mức bảo mật thay vì chỉ tạo ra một danh sách lỗi.

