# Audit criteria: Xây dựng tiêu chí kiểm toán bảo mật có thể kiểm chứng

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **audit criteria** và phân biệt nó với mục tiêu kiểm toán, phạm vi, điều kiện kiểm soát, thủ tục đánh giá, bằng chứng và phát hiện.
2. Chuyển mục tiêu bảo mật, rủi ro, yêu cầu nội bộ và nghĩa vụ bên ngoài thành tiêu chí **cụ thể, có nguồn gốc, có phạm vi, có điều kiện đánh giá**.
3. Thiết kế một **audit criteria register** gắn mỗi tiêu chí với đối tượng, owner, yêu cầu, phương pháp kiểm tra, mẫu kiểm tra, bằng chứng, quy tắc quyết định và lịch tái đánh giá.
4. Lựa chọn và kết hợp các phương pháp **examine – interview – test** để đánh giá thiết kế, triển khai và hiệu lực vận hành của security controls.
5. Phân biệt **conformity, nonconformity, not applicable, insufficient evidence và risk acceptance**, tránh kết luận đạt khi dữ liệu không đủ.
6. Viết audit finding có căn cứ, điều kiện thực tế, nguyên nhân, tác động, hành động khắc phục, chủ sở hữu và phương pháp xác minh lại.
7. Tổ chức kiểm toán và security assurance liên tục từ **risk → requirement → audit criterion → control → test → evidence → decision → remediation**.

## 1. Audit criteria là gì và tại sao quan trọng?

**Audit criteria** là tập hợp yêu cầu, chính sách, quy trình, tiêu chuẩn hoặc kỳ vọng được sử dụng làm **căn cứ đối chiếu với bằng chứng kiểm toán**. Nói đơn giản, audit criteria trả lời câu hỏi: **"Đối tượng được kiểm tra phải đáp ứng điều gì?"**

Trong bảo mật, nếu không định nghĩa tiêu chí trước khi thu thập dữ liệu, auditor có thể rơi vào ba tình huống:

- Thu được hàng nghìn log và ảnh chụp cấu hình nhưng không chứng minh được điều kiện đạt.
- Cùng một hiện trạng, mỗi người đánh giá kết luận khác nhau vì kỳ vọng mơ hồ.
- Bị thuyết phục bởi một bộ tài liệu có vẻ đầy đủ mà bỏ qua rủi ro trọng yếu hoặc phạm vi triển khai thực tế.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, tiêu chí kiểm toán là cầu nối giữa **phân tích rủi ro, security objectives, security controls, kiểm thử, audit, finding và remediation**. Chương trình security assurance liên tục cần xác định *đúng cái phải đạt*, *cách kiểm chứng*, *bằng chứng cần có* và *mức độ tin cậy của kết luận*.

Ví dụ không đủ rõ:

> "Quyền truy cập production phải an toàn."

Ví dụ có thể kiểm toán:

> "Trong phạm vi các danh tính người dùng có quyền quản trị production và được xác định từ inventory IAM tại thời điểm đánh giá, việc đăng nhập tương tác phải được bảo vệ bằng MFA theo chính sách SEC-IAM-04 phiên bản 3.2; mọi ngoại lệ phải có phê duyệt còn hiệu lực, phạm vi và hạn xử lý. Việc đáp ứng được kiểm tra bằng cấu hình xác thực, quyền hiệu lực, log thử nghiệm và danh sách ngoại lệ."

Ví dụ thứ hai xác định **đối tượng, yêu cầu, nguồn chính sách, phương pháp và ngoại lệ**. Ngưỡng, công nghệ hoặc tần suất thực tế phải được tổ chức phê duyệt theo rủi ro; bài học không giả định một chính sách mẫu áp dụng cho tất cả hệ thống.

### 1.1. Phân biệt các khái niệm gần nhau

| Thành phần | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Audit objective** | Cuộc kiểm toán muốn xác định điều gì? | Đánh giá mức đáp ứng yêu cầu kiểm soát quyền truy cập production. |
| **Audit scope** | Hệ thống, kỳ, pháp nhân, tenant và khu vực nào được kiểm tra? | Ba production cloud accounts trong quý IV. |
| **Audit criteria** | Lấy yêu cầu nào để đánh giá đạt hay không đạt? | SEC-IAM-04 v3.2: người dùng đặc quyền phải dùng MFA. |
| **Control** | Cơ chế hoặc hoạt động nào giúp đáp ứng yêu cầu? | IdP conditional access, PAM, access review, break-glass governance. |
| **Test procedure** | Người kiểm toán làm gì để đánh giá criterion? | Kiểm tra cấu hình IdP, đối chiếu IAM inventory, chạy negative authentication test được phép. |
| **Audit evidence** | Dữ liệu nào thực sự hỗ trợ kết quả? | Export IAM, policy, IdP config, kết quả đăng nhập thử, event log. |
| **Observation / finding** | Thực tế khác yêu cầu thế nào, tại đâu? | Hai tài khoản đặc quyền không thuộc chính sách MFA được yêu cầu. |
| **Audit conclusion** | Kết quả toàn bộ phạm vi kiểm toán thế nào? | Hai tiêu chí không phù hợp; các tiêu chí còn lại đánh giá trong phạm vi và giới hạn ghi rõ. |

**Một security control không phải tự nó là audit criterion.** Ví dụ "dùng SIEM" là một cơ chế. Tiêu chí cần nói rõ sự kiện nào phải được thu, phát hiện và chuyển cảnh báo trong điều kiện nào.

### 1.2. Tiêu chí kiểm toán không phải tiêu chí tùy ý của auditor

Audit criteria cần có **cơ sở thẩm quyền hoặc cơ sở được các bên liên quan chấp thuận**: yêu cầu pháp lý áp dụng, hợp đồng, tiêu chuẩn trong phạm vi được lựa chọn, policy nội bộ, control baseline, security requirements hay mục tiêu kinh doanh được phê duyệt.

Auditor có thể đề xuất tiêu chí hoặc câu hỏi kiểm tra, nhưng không nên âm thầm biến **best practice cá nhân** thành nghĩa vụ bắt buộc rồi ghi nonconformity khi tổ chức chưa áp dụng yêu cầu đó. Nếu phát hiện rủi ro nằm ngoài tiêu chí, có thể báo **observation, recommendation hoặc risk finding** theo quy chế kiểm toán, tách biệt với vi phạm một yêu cầu đã được xác lập.

## 2. Nguồn hình thành audit criteria

Audit criteria thường đến từ nhiều nguồn, nhưng không phải nguồn nào cũng ràng buộc mọi tổ chức.

| Nguồn | Ví dụ | Cần làm rõ |
|---|---|---|
| **Pháp luật/quy định** | Nghĩa vụ bảo vệ hoặc lưu dữ liệu theo lĩnh vực, khu vực pháp lý. | Pháp nhân, loại dữ liệu, thời điểm hiệu lực, phạm vi áp dụng và cách diễn giải được phê duyệt. |
| **Hợp đồng/điều khoản dịch vụ** | Cam kết thông báo sự cố, quyền audit, bảo vệ dữ liệu, SLA. | Các bên, dịch vụ, ngoại lệ, kỳ hợp đồng, trigger và phép đo. |
| **Tiêu chuẩn/chương trình đánh giá được chọn** | ISO/IEC 27001, SOC 2 Trust Services Criteria hoặc baseline khác. | Phiên bản, scope, loại đánh giá, trách nhiệm và kỳ kiểm tra. |
| **Security policy nội bộ** | Privileged access, encryption, secure change, logging policy. | Owner, phiên bản có hiệu lực, đối tượng và ngoại lệ. |
| **Kiến trúc và security requirements** | Không cho workload public truy cập DB chứa PII; áp dụng least privilege. | Threat model, ranh giới tin cậy, hệ thống và cách kiểm tra. |
| **Risk treatment/control objectives** | Tăng phát hiện lạm dụng quyền quản trị cloud. | Kịch bản rủi ro, mức rủi ro chấp nhận, control và người phê duyệt. |
| **Quy trình vận hành được phê duyệt** | Access review hàng quý; rollback kiểm soát khi deploy. | Tần suất, hồ sơ, người làm, thời gian khắc phục và bằng chứng. |

Cần xác minh **phiên bản và phạm vi** của mỗi nguồn. Một chính sách mới có hiệu lực ngày 1/11 không mặc nhiên dùng để kết luận các hành vi tháng 9 đã vi phạm, trừ khi có nghĩa vụ khác có hiệu lực tại thời điểm đó.

### 2.1. Sử dụng framework và chuẩn tham chiếu đúng cách

- **ISO 19011** cung cấp hướng dẫn kiểm toán hệ thống quản lý, gồm nguyên tắc, quản lý chương trình và phương pháp kiểm toán. Việc tham khảo hướng dẫn này không tự tạo ra mọi yêu cầu bảo mật kỹ thuật.
- **ISO/IEC 27001** đưa ra yêu cầu về hệ thống quản lý an toàn thông tin. Khi kiểm tra tổ chức theo chuẩn này, phải xác định đúng điều khoản, phạm vi ISMS, Statement of Applicability (SoA), yêu cầu kiểm soát và tình trạng thực tế.
- **ISO/IEC 27002** cung cấp hướng dẫn về các kiểm soát an toàn thông tin; không nên mặc định toàn bộ nội dung hướng dẫn đều là nghĩa vụ pháp lý hoặc tiêu chí chứng nhận áp dụng giống nhau.
- **NIST SP 800-53A** mô tả các phương pháp và mục tiêu đánh giá kiểm soát trong hệ thống phù hợp, hữu ích khi xây dựng thủ tục examine, interview, test; cần dùng bản và phạm vi mà tổ chức chọn.
- **SOC 2** là một loại báo cáo assurance với tiêu chí, phạm vi, thời kỳ và ý kiến kiểm toán xác định; không nên tự biến một báo cáo SOC 2 của nhà cung cấp thành xác nhận rằng mọi control của khách hàng đã đạt.

Các nguồn này hỗ trợ **thiết kế audit program** nhưng không thay thế bước xác định quy định, điều khoản hợp đồng, phương pháp và phiên bản thực sự áp dụng.

### 2.2. Xử lý nguồn có thể mâu thuẫn

Ví dụ chính sách A yêu cầu log giữ 90 ngày, hợp đồng B yêu cầu một phạm vi log giữ 180 ngày, còn quy định C có yêu cầu khác cho dữ liệu cá nhân. Không chọn ngẫu nhiên một con số.

Cách xử lý:

1. Xác định dữ liệu, hệ thống, pháp nhân và người nhận liên quan tới từng yêu cầu.
2. Ghi nguồn, ngày hiệu lực, phạm vi và người có thẩm quyền diễn giải.
3. Đưa xung đột tới legal/compliance/risk owner để thống nhất cách thực thi hợp lệ.
4. Tài liệu hóa tiêu chí cuối cùng, lý do áp dụng và ngoại lệ/biện pháp bù trừ nếu có.
5. Kiểm tra cấu hình thực và retention theo đúng tập dữ liệu, không chỉ đọc một biến cấu hình.

**Auditor không tự giải quyết xung đột pháp lý** bằng việc chọn tiêu chí dễ đạt hơn hoặc nghiêm ngặt hơn tùy ý.

## 3. Tiêu chí tốt phải kiểm chứng được

Một tiêu chí hữu ích không nhất thiết dài, nhưng phải đủ chính xác để **hai reviewer độc lập, dùng cùng bằng chứng và quy tắc quyết định, đưa ra kết luận nhất quán**.

### 3.1. Thành phần của một criterion

| Trường | Mục đích | Câu hỏi kiểm tra |
|---|---|---|
| **Criterion ID** | Truy vết ổn định giữa kỳ đánh giá và findings. | Mã duy nhất là gì? |
| **Source/version** | Căn cứ và hiệu lực. | Policy/standard/contract nào, bản nào? |
| **Control objective / risk** | Ý nghĩa bảo mật của tiêu chí. | Chống kịch bản rủi ro nào? |
| **Population / scope** | Mẫu số và đối tượng phải tuân thủ. | Mọi admin user, workload hay một tập được phê duyệt? |
| **Condition / requirement** | Hành vi hoặc trạng thái bắt buộc. | Phải bật gì, ai xét duyệt, điều kiện nào bị cấm? |
| **Time / frequency** | Khi nào và trong khoảng thời gian nào? | Tại thời điểm đánh giá, liên tục, mỗi lần thay đổi hay hàng quý? |
| **Method / evidence** | Cách quan sát và dữ liệu chứng minh. | Examine, interview, test; log hoặc cấu hình nào? |
| **Decision rule** | Khi nào Pass/Fail/Unknown/Not applicable? | Có cho phép ngoại lệ không? Xử lý thiếu dữ liệu thế nào? |
| **Owner / reviewer** | Người chịu trách nhiệm và người đánh giá. | Ai duy trì control, ai phê duyệt conclusion? |

**Ví dụ mơ hồ:** "Hệ thống backup thường xuyên và an toàn."

**Ví dụ kiểm chứng được:** "Đối với các database production được phân loại Critical trong inventory ngày đánh giá, backup job theo chính sách DR-DATA-05 v2 phải được cấu hình và chạy đúng lịch; mỗi database có ít nhất một lần restore thử thành công trong kỳ đánh giá được định nghĩa; bản khôi phục đáp ứng test đọc và nhất quán; thất bại phải có ticket và xử lý theo SLA của chính sách."

Tiêu chí này phân biệt **backup exists** với **recoverability tested**. Nếu chính sách chưa quy định tần suất restore, hãy ghi đó là **thiếu sót cần xây dựng yêu cầu** chứ không tự đặt thành một vi phạm không có cơ sở.

### 3.2. Cách biến tuyên bố mơ hồ thành tiêu chí

~~~mermaid
flowchart TD
    A["Mục tiêu / rủi ro"] --> B["Chọn nguồn yêu cầu có hiệu lực"]
    B --> C["Xác định population và kỳ"]
    C --> D["Viết điều kiện kiểm chứng"]
    D --> E["Chọn phương pháp và evidence"]
    E --> F["Xác định quy tắc Pass/Fail/Unknown"]
    F --> G["Phê duyệt và lập lịch đánh giá"]
    G --> H["Thực thi, phát hiện, khắc phục"]
    H --> G
~~~

Bắt đầu với câu "bảo đảm privileged access được kiểm soát":

1. **Risk:** credential admin bị dùng trái phép.
2. **Requirement:** privileged access được phê duyệt, xác thực phù hợp và thu hồi khi không cần.
3. **Population:** human admin, service principal và break-glass có phạm vi khác nhau; không ép cùng một phép thử nếu bản chất quyền khác nhau.
4. **Criterion A:** mọi quyền admin cấp mới phải có approval hợp lệ và dấu vết cấp quyền.
5. **Criterion B:** mọi human interactive privileged login trong scope phải đáp ứng MFA policy.
6. **Criterion C:** tài khoản admin hết nhiệm vụ phải bị thu hồi theo deadline định sẵn.
7. **Criterion D:** mọi thay đổi quyền admin phải tạo audit event và detection/notification theo mục tiêu được phê duyệt.

Những criterion này liên quan cùng rủi ro nhưng cần **control và evidence khác nhau**. Không gom thành một tiêu chí "IAM đạt" khiến không thể xác định phần nào chưa đạt.

### 3.3. Trạng thái liên tục khác sự kiện trong kỳ

Một số yêu cầu đòi trạng thái tại mọi thời điểm (ví dụ không có public storage không được phê duyệt). Một số yêu cầu liên quan đến mỗi lần xảy ra sự kiện (mọi thay đổi quyền phải có approval). Một số yêu cầu có tần suất (access review theo quý).

Phải định nghĩa:

- **Point-in-time:** ảnh chụp cấu hình tại mốc T chứng minh trạng thái ở T, không chứng minh cả quý.
- **Period of operation:** muốn đánh giá cả quý, cần change history, log, snapshot định kỳ hoặc kiểm tra control qua kỳ.
- **Event-driven:** đánh giá trên population của tất cả event trong kỳ hoặc mẫu đã chọn.
- **Frequency-based:** kiểm tra những lần phải thực hiện theo lịch, deadline và evidence hoàn tất.

Một ảnh IAM chụp cuối quý không chứng minh không có quyền admin không phê duyệt được cấp rồi thu hồi giữa quý.

## 4. Audit criteria register: tài liệu trung tâm

Không nên để tiêu chí rải rác trong email hoặc từng bảng tính của auditor. **Audit criteria register** giúp gắn requirement với test, evidence và owner theo phiên bản.

### 4.1. Mẫu YAML minh họa

~~~yaml
criterion_id: AC-IAM-001
title: "Approval cho thay đổi quyền quản trị production"
source:
  document: "SEC-IAM-04"
  version: "3.2"
  effective_from: "2026-10-01"
objective: "Ngăn cấp đặc quyền production trái thẩm quyền"
scope:
  environments: ["production"]
  assets: "IAM inventory tại đầu và cuối kỳ, kèm change records"
  event_population: "mọi lần cấp hoặc tăng quyền admin trong kỳ"
assessment_period:
  start_utc: "2026-11-01T00:00:00Z"
  end_utc_exclusive: "2026-12-01T00:00:00Z"
criterion:
  requirement: "Mỗi thay đổi phải có approval hợp lệ trước khi hiệu lực"
  exception_policy: "SEC-EXC-02"
assessment:
  methods: ["examine", "test", "interview"]
  evidence:
    - "IAM raw change audit"
    - "role binding history"
    - "approved change records"
    - "exception approvals"
  decision_rule:
    pass: "Mọi item được kiểm tra có approval đúng scope và thời điểm"
    fail: "Có item hợp lệ trong mẫu kiểm tra thiếu approval cần có"
    inconclusive: "Nguồn không đủ hoặc không xác minh được completeness"
owner: "IAM platform team"
reviewer: "Independent assurance reviewer"
~~~

Đây là **schema minh họa**, không phải cấu hình dùng được trực tiếp trong công cụ audit nào. Điều kiện PASS trong ví dụ là kết luận **đối với population/mẫu được kiểm tra**, không tự suy rằng kiểm tra mẫu nhỏ chứng minh 100% mọi thay đổi trong toàn kỳ.

### 4.2. Traceability matrix

| Risk ID | Requirement | Criterion ID | Control | Phương pháp | Evidence ID |
|---|---|---|---|---|---|
| R-IAM-01 | Không cấp admin ngoài thẩm quyền. | AC-IAM-001 | Approval workflow + IAM audit. | Examine approval, test đối chiếu lịch sử quyền. | EV-001, EV-002. |
| R-LOG-02 | Nhận biết thay đổi làm yếu audit. | AC-LOG-003 | Audit logging + tamper alert. | Test trong sandbox và examine pipeline logs. | EV-010, EV-011. |
| R-DR-03 | Khôi phục dữ liệu Critical đúng RPO. | AC-DR-002 | Backup + replication + restore. | Quan sát restore và đối chiếu recovery point. | EV-020, EV-021. |
| R-APP-04 | Không cho phép truy cập API ngoài quyền. | AC-APP-004 | Server-side authorization. | Negative authorization test, code/config examine. | EV-030, EV-031. |
| R-TPR-05 | Dữ liệu gửi vendor trong phạm vi cho phép. | AC-TPR-005 | Data minimization + scoped token. | Review data flow, test payload và access deny. | EV-040, EV-041. |

Một tiêu chí có thể hỗ trợ nhiều risk và một risk có thể cần nhiều criteria. **Coverage của register** phải được đánh giá theo rủi ro: không đồng nghĩa số tiêu chí càng nhiều càng tốt.

## 5. Phương pháp đánh giá: examine, interview, test

Ba nhóm phương pháp thường bổ trợ nhau:

| Phương pháp | Thực hiện | Loại bằng chứng | Giới hạn |
|---|---|---|---|
| **Examine (xem xét)** | Kiểm tra chính sách, cấu hình, raw log, architecture diagram, ticket và records. | Documents, exports, config snapshots, event history. | Có thể cũ, bị chỉnh sửa, không phản ánh vận hành. |
| **Interview (phỏng vấn)** | Hỏi owner, operator, người phê duyệt, người trực về quy trình và thực tế. | Lời giải thích, xác nhận vai trò, bối cảnh và minh họa thao tác. | Lời nói đơn thuần không đủ chứng minh control đang hoạt động. |
| **Test (thử nghiệm)** | Quan sát/đưa input có kiểm soát để xem behavior hoặc chạy truy vấn trên dữ liệu nguồn. | Kết quả kiểm thử, log, trạng thái, độ trễ, alert và deny response. | Giới hạn bởi scope, môi trường, dữ liệu, thời điểm và an toàn. |

**Triangulation:** kết hợp nhiều loại nguồn để tăng độ tin cậy. Ví dụ để đánh giá offboarding tài khoản:

1. Examine HR/identity termination records và chính sách thu hồi quyền.
2. Examine IAM audit/access inventory tại các mốc phù hợp.
3. Interview owner về trường hợp ngoại lệ.
4. Test truy cập bằng test account đã được phép hoặc xác minh denial qua evidence phù hợp.

Nếu chính sách nói tự động thu hồi trong 24 giờ nhưng audit ghi một account vẫn hoạt động 5 ngày, bằng chứng cấu hình "automation enabled" không đủ để kết luận đạt.

### 5.1. Thiết kế thủ tục kiểm tra chuẩn

Mỗi test procedure cần mô tả:

- **Purpose:** tiêu chí và claim nào được kiểm tra.
- **Preconditions:** quyền, môi trường, population, kỳ đánh giá, version.
- **Steps:** cách chọn dữ liệu, câu truy vấn, hành động quan sát, expected outputs.
- **Evidence:** nguồn gốc, định dạng, liên kết raw/normalized, timestamp và người thực hiện.
- **Acceptance:** điều kiện Pass, Fail, Unknown/Inconclusive.
- **Safety:** chỉ thao tác được ủy quyền; giới hạn thay đổi vào production; cleanup.
- **Limitations:** phần control chưa được thử, độ tin cậy của nguồn và khả năng tổng quát hóa.

Một thủ tục kiểm toán tốt cho phép người đánh giá khác **thực hiện lại ở phạm vi tương đương**, đồng thời biết rõ khi nào kết quả không thể tái lập vì dữ liệu biến động.

## 6. Lựa chọn population và lấy mẫu đúng cách

### 6.1. Population là gì?

**Population** là toàn bộ đối tượng hoặc sự kiện thuộc điều kiện của criterion trong kỳ đánh giá. Ví dụ: mọi sự kiện cấp quyền admin production từ 1/11 đến trước 1/12 UTC, hoặc toàn bộ storage bucket chứa dữ liệu Confidential đang tồn tại ngày 28/11.

Nếu population không đầy đủ, một mẫu ngẫu nhiên từ bảng đã lọc có thể tạo kết luận sai dù từng item trong mẫu được đánh giá đúng.

Các lỗi thường gặp:

- Chỉ xuất audit ở một cloud region, bỏ các region khác.
- Không bao gồm service accounts, break-glass và quyền gián tiếp qua group.
- Chỉ xem quyền tại cuối kỳ, bỏ thay đổi phát sinh rồi thu hồi trước đó.
- API phân trang nhưng client chỉ tải trang đầu.
- Log được lấy mẫu, thiếu event do retention/ingestion lỗi.
- Nhiều bảng dùng ID khác nhau dẫn tới de-dup sai hoặc bỏ sót.

### 6.2. Full population hay sampling?

| Cách kiểm tra | Phù hợp khi | Hạn chế cần ghi |
|---|---|---|
| **100% population automated test** | Có tập dữ liệu đầy đủ, quy tắc kiểm chứng rõ, chi phí thấp. | Chất lượng kết quả phụ thuộc nguồn và logic test; dữ liệu đầy đủ chưa chắc field đáng tin. |
| **Statistical sampling** | Muốn suy luận một tính chất của population theo mức tin cậy và sai số xác định, với thiết kế mẫu hợp lệ. | Cần phương pháp thống kê, khung mẫu, giả định và kích thước mẫu được quyết định trước. |
| **Risk-based / judgmental sampling** | Tập trung tài sản Critical, quyền cao, ngoại lệ, thay đổi nhạy cảm hoặc giai đoạn có sự cố. | Giúp tìm vấn đề nhưng không cho phép suy tỷ lệ lỗi của toàn population như mẫu xác suất. |
| **Targeted negative testing** | Cần xác minh một tình huống bị cấm, ví dụ user không có quyền đọc secret. | Một tình huống fail/pass không đại diện mọi đường truy cập. |

Không đưa ra kết luận "95% tài khoản an toàn" từ 20 tài khoản được chọn thủ công. Nếu cần tỷ lệ tin cậy thống kê, phải thiết kế phương pháp lấy mẫu và reporting phù hợp; **không tự chế cỡ mẫu chung cho mọi cuộc audit**.

### 6.3. Ví dụ kiểm tra 300 lần tăng quyền

Population có 300 sự kiện tăng quyền trong kỳ. Auditor chọn 40 trường hợp risk-based, gồm toàn bộ thay đổi tới quyền cấp cluster và các sự kiện ngoài giờ, tìm thấy 3 trường hợp thiếu approval.

Có thể kết luận:

- **3 trường hợp trong mẫu đã không đáp ứng criterion** nếu source và approval được xác minh.
- Cần đánh giá tác động, root cause và mở rộng phạm vi xem xét.
- Không được tuyên bố "tỷ lệ thiếu approval của toàn kỳ = 3/40 = 7,5%" theo nghĩa thống kê đại diện, vì mẫu chọn theo rủi ro.
- Nếu không xác minh được 300 sự kiện là population đầy đủ, còn có **scope/telemetry gap** cần ghi riêng.

### 6.4. Xác minh tính đầy đủ của nguồn

Trước khi test, xem:

1. Có inventory tài sản/identities và các sự kiện trong kỳ không?
2. API export có pagination token, timeout, rate limit hoặc filter ẩn không?
3. Có đối chiếu số record với nguồn hoặc sequence/heartbeat không?
4. Có parser error, dropped events, storage lag hoặc retention hết hạn không?
5. Có actor/target không thể nối vì thiếu identifier không?
6. Có evidence được chỉnh sửa sau acquisition không? Provenance và hash được quản lý ra sao?

**Không có sự kiện trong log** có thể là **không xảy ra hành vi** hoặc **không quan sát được hành vi**. Kiểm toán không được coi hai khả năng là một.

## 7. Chất lượng bằng chứng để ra quyết định

Bằng chứng cần **thích hợp (appropriate)** và **đủ (sufficient)** đối với criterion. Lượng file lớn không thay thế tính liên quan hay nguồn đáng tin.

### 7.1. Sáu câu hỏi về evidence

| Thuộc tính | Câu hỏi | Dấu hiệu vấn đề |
|---|---|---|
| **Relevance** | Có trực tiếp chứng minh điều kiện của criterion? | Chụp dashboard CPU cho tiêu chí MFA. |
| **Reliability** | Nguồn, quyền, integrity và quá trình thu có đáng tin? | CSV được sửa tay không có nguồn đối chiếu. |
| **Completeness** | Bao phủ đúng population, kỳ, tenant, region và field? | Chỉ log một cluster trong năm cluster. |
| **Recency** | Phù hợp thời điểm/kỳ kiểm toán? | Chính sách mới cho kỳ cũ, scan đã quá lâu. |
| **Corroboration** | Có nguồn độc lập hoặc test hỗ trợ claim không? | Chỉ lời cam kết "chúng tôi luôn review". |
| **Traceability** | Reviewer truy từ finding tới raw event/test/version được không? | Ảnh chụp không ID, không timestamp, không môi trường. |

### 7.2. Design effectiveness, implementation và operating effectiveness

Một security control có thể tồn tại dưới ba trạng thái rất khác:

- **Thiết kế phù hợp (design):** chính sách, logic và phân quyền được xây sao cho nếu hoạt động đúng sẽ đáp ứng criterion.
- **Đã triển khai (implementation):** công cụ, cấu hình, workflow thực sự tồn tại trong hệ thống thuộc scope.
- **Hoạt động hiệu lực (operating effectiveness):** control đã vận hành đúng, đủ thời gian và đạt kết quả trong tình huống cần thiết.

Ví dụ:

| Claim | Bằng chứng có thể dùng | Không được kết luận chỉ từ |
|---|---|---|
| Chính sách phân quyền được phê duyệt. | Policy có owner/version/approval. | Lời nói "có chính sách". |
| MFA được cấu hình cho admin production. | IAM inventory và IdP policy snapshot, effective assignments. | File PDF mô tả quy định MFA. |
| MFA thực sự bị bắt buộc khi đăng nhập. | Test được phép, authentication logs, conditional-access evaluation. | Nhìn thấy checkbox "enabled". |
| Thay đổi quyền được xét duyệt trong quý. | Population change events, approval timestamps, exceptions. | Một ticket mẫu hoặc lịch review. |
| Thay đổi audit log được phát hiện. | Source audit, detection rule, thử nghiệm và alert timeline. | Rule tồn tại trong SIEM nhưng chưa từng chạy. |

**Có thể đạt ở một cấp và chưa đủ bằng chứng ở cấp khác**. Do đó thiết kế audit program cần nói rõ đang đánh giá **design**, **implementation**, **operation** hay **effectiveness**; không gom mọi đánh giá thành "control passed".

### 7.3. Bằng chứng dẫn xuất và dữ liệu nhạy cảm

Khi dùng bảng normalized event, report tổng hợp hoặc screenshot:

- Lưu tham chiếu raw/source, query, parser version, timestamp và người thu.
- Ghi các phép biến đổi có thể làm thay đổi kết luận: timezone conversion, filtering, dedup, aggregation.
- Dùng evidence ID và kho truy cập kiểm soát; tránh nhúng token, PII hoặc secret vào ticket công khai.
- Khi vì quyền riêng tư phải redaction, dùng bản dẫn xuất và lưu dấu phương pháp.
- Không sửa nguyên bản evidence rồi coi nó là raw.

Hash hoặc storage immutable có thể hỗ trợ integrity sau acquisition nhưng **không tự chứng minh nguồn đúng hoặc dữ liệu đầy đủ**.

## 8. Quy tắc đánh giá và xử lý ngoại lệ

### 8.1. Kết luận theo từng criterion

Một bộ trạng thái minh họa:

| Kết quả | Ý nghĩa | Hành động |
|---|---|---|
| **Conform / PASS** | Bằng chứng đủ, thích hợp và đáp ứng tiêu chí trong scope đã kiểm tra. | Lưu chứng cứ, kết luận và kỳ đánh giá tiếp theo. |
| **Nonconform / FAIL** | Có bằng chứng hợp lệ cho thấy đối tượng không đáp ứng yêu cầu áp dụng. | Ghi finding, tác động, owner, hành động và retest. |
| **Inconclusive / Insufficient evidence** | Không đủ bằng chứng hoặc không xác minh được nguồn/population để quyết định. | Thu thêm dữ liệu, ghi gap, không tính là PASS. |
| **Not applicable** | Có căn cứ cho thấy criterion không áp dụng cho đối tượng/kỳ. | Ghi lý do, người phê duyệt và bằng chứng scope. |
| **Not assessed / Not run** | Có áp dụng nhưng chưa thực hiện phép đánh giá. | Ghi phạm vi bỏ trống và kế hoạch kiểm tra. |
| **Accepted risk / Exception** | Chưa đáp ứng yêu cầu nhưng rủi ro được người có thẩm quyền xử lý theo cơ chế ngoại lệ. | Lưu approval, controls bù trừ, scope, expiry; không biến thành PASS. |

Nếu pháp lý hoặc chương trình kiểm toán dùng hệ thuật ngữ riêng, cần mapping rõ vào các trạng thái tương ứng. **Chấp nhận rủi ro** là quyết định quản trị, không làm thay đổi thực tế một control đã/đang không đáp ứng criterion.

### 8.2. Quy tắc xử lý một trường hợp ngoại lệ

Ví dụ policy yêu cầu MFA cho quản trị viên, còn tài khoản emergency access dùng cơ chế bảo vệ và giám sát đặc thù.

Auditor cần xác định:

1. Policy có cho phép cơ chế ngoại lệ đó không?
2. Tài khoản nào thuộc phạm vi, mục đích và quyền hiệu lực?
3. Ai phê duyệt, ngày hiệu lực/hết hạn và điều kiện giám sát?
4. Control bù trừ đã hoạt động và được test chưa?
5. Ngoại lệ có được rà soát và thu hồi khi hết nhu cầu không?

Nếu policy **không** cho ngoại lệ, một giấy chấp nhận rủi ro nội bộ có thể là quyết định tạm thời, nhưng auditor vẫn cần báo cáo sự không phù hợp theo yêu cầu áp dụng. Nếu policy định nghĩa một con đường tuân thủ thay thế hợp lệ, cần đánh giá theo đúng điều kiện của con đường đó.

### 8.3. Severity không thay thế verdict

Một nonconformity có thể có **mức ảnh hưởng thấp hoặc cao**; ngược lại một dữ liệu thiếu có thể tạo **assurance gap nghiêm trọng** khi phạm vi là hệ thống Critical. Vì vậy nên tách:

- **Criterion verdict:** Pass/Fail/Inconclusive/Not applicable.
- **Risk severity:** tác động, xác suất/khả năng lạm dụng, phạm vi phơi nhiễm, tính khẩn cấp.
- **Evidence confidence:** mức độ tin cậy và đủ dữ liệu cho kết luận.

Không tự động gán tất cả FAIL là Critical hay tất cả Inconclusive là Low.

## 9. Ví dụ đầy đủ: kiểm toán quyền IAM và logging ở cloud production

### 9.1. Bối cảnh

Tổ chức có ba production cloud accounts và các workload Kubernetes. Risk assessment xác định hai kịch bản ưu tiên:

- **R1:** một danh tính có quyền cấp đặc quyền admin trái chính sách.
- **R2:** thay đổi cấu hình tắt audit logging khiến hoạt động không được phát hiện.

Tổ chức có các policy được phê duyệt:

- **SEC-IAM-04 v3.2:** các thay đổi cấp quyền quản trị production phải có phê duyệt hợp lệ và audit trail.
- **SEC-LOG-07 v1.4:** audit nguồn trọng yếu phải được bật và việc vô hiệu hóa phải được cảnh báo theo thời gian mục tiêu được phê duyệt.

Mục đích kiểm toán là **đánh giá tiêu chí trong kỳ tháng 11**, không xác nhận mọi rủi ro IAM/cloud đã được loại bỏ.

### 9.2. Ma trận tiêu chí

| Criterion ID | Điều kiện đạt | Population/scope | Phương pháp | Evidence |
|---|---|---|---|---|
| AC-IAM-01 | Thay đổi quyền admin có approval đúng actor, resource và thời điểm trước khi có hiệu lực. | Mọi IAM/RBAC privilege grant trong 3 accounts và clusters production trong kỳ. | Examine IAM audit + approved change; test join quyền hiệu lực. | EV-01 export audit, EV-02 approval records. |
| AC-IAM-02 | Human admin interactive sign-in chịu chính sách MFA được phê duyệt, trừ đường compliance thay thế hợp lệ nếu có. | Effective privileged human accounts trong scope. | Examine IdP policy + test access theo quyền được cấp. | EV-03 IAM inventory, EV-04 IdP config, EV-05 test result. |
| AC-LOG-01 | Tất cả nguồn audit được xác định Critical đã bật và đang gửi event đầy đủ theo baseline trong kỳ. | Cloud audit, IdP audit, Kubernetes API audit của scope. | Examine inventory/config; source heartbeat, completeness checks. | EV-06 source coverage, EV-07 pipeline health. |
| AC-LOG-02 | Một hành động làm yếu audit được phát hiện và chuyển alert trong mốc được phê duyệt. | Hành vi kiểm thử được phép trên audit policy/collector. | Test positive/negative và đo event → alert → delivered. | EV-08 raw event, EV-09 rule version, EV-10 alert/case timeline. |
| AC-GOV-01 | Exception liên quan IAM/logging có owner, approval, hạn và rà soát. | Mọi exception còn hiệu lực trong kỳ. | Examine exception register, review approvals và expiry. | EV-11 exceptions, EV-12 reviews. |

Chú ý **AC-IAM-01 và AC-LOG-01 đòi đánh giá population và health khác nhau**. Một bản xuất IAM đầy đủ không bảo đảm Kubernetes API audit đã được bật, và một test SIEM thành công không bảo đảm người trực xử lý alert đúng yêu cầu.

### 9.3. Thủ tục kiểm tra AC-IAM-01

**Bước A — Scope:** xác định ba account, clusters, namespaces, service principals và đối tượng có quyền cấp admin. Chốt epoch/kỳ đánh giá theo UTC.

**Bước B — Population:** xuất IAM change audit có thành công, bao gồm create/update/bind/unbind, các role có quyền tương đương admin và thay đổi quyền gián tiếp qua group nếu nằm trong yêu cầu.

**Bước C — Completeness:** kiểm tra account/region coverage, pagination, filter, ingestion lag, duplicate và missing actor/target; đối chiếu với inventory và configuration history.

**Bước D — Matching:** nối event với approval record theo actor, target, action, scope và thời gian; không chỉ kiểm tra ticket tồn tại.

**Bước E — Test:** thực hiện một change có kiểm soát trong sandbox để xác minh log mang đủ field phục vụ criterion; dùng lại truy vấn cho tập production đã được cấp phép.

**Bước F — Verdict:** đối với event thiếu approval, xác nhận yêu cầu có áp dụng và không có exception hợp lệ; lập finding. Với event thiếu raw audit, đánh dấu inconclusive hoặc data gap theo nguồn, không coi là pass.

### 9.4. Kết quả tình huống

Giả sử export đã kiểm tra cho thấy:

- 134 sự kiện thay đổi quyền được xác định là thuộc population.
- Sau khi đối chiếu có 130 sự kiện có approval hợp lệ.
- 2 sự kiện thiếu approval theo policy.
- 2 sự kiện có record audit nhưng không đủ actor ID để xác minh approval.
- AC-LOG-02 test tạo event lúc 10:00:00, alert lúc 10:01:15 và delivered lúc 10:01:30; mục tiêu minh họa là delivered trong 2 phút.

**Kết luận đúng:**

- **AC-IAM-01: FAIL** cho các trường hợp xác minh thiếu approval; đồng thời mở data-quality finding cho hai event không đủ actor, không lặng lẽ coi là đạt.
- **AC-LOG-02:** test đã đáp ứng thời gian *cho tình huống kiểm thử được mô tả*, với điều kiện log/alert có nguồn gốc rõ và đường truyền là đường cần kiểm tra. Kết quả này không tự chứng minh mọi kỹ thuật tắt logging đều bị phát hiện.
- Nếu chưa kiểm tra completeness của toàn bộ nguồn, không nên tuyên bố "134 là toàn bộ sự kiện trong kỳ" như một sự thật đã được xác minh.

### 9.5. Mẫu bảng kết quả theo từng criterion

~~~text
ASSESSMENT_ID: AUD-2026-11-CLOUD
CRITERION_ID: AC-IAM-01
SOURCE: SEC-IAM-04 v3.2
SCOPE: 3 production accounts + defined Kubernetes clusters
PERIOD: [2026-11-01T00:00:00Z, 2026-12-01T00:00:00Z)
POPULATION: 134 identified events; completeness checks attached
METHODS: examine + join test + authorized sandbox behavior test
RESULT: FAIL
OBSERVATION: 2 changes without valid prior approval; 2 events
             missing actor identifier, treated as data quality gap
EVIDENCE: EV-01, EV-02, EV-03
LIMITATIONS: indirect permissions mapping needs periodic refresh
OWNER: IAM platform lead
REVIEWER: assurance reviewer
REMEDIATION: enforce approval gate, repair actor attribution,
             add regression detection tests
RETEST: pending
~~~

Mẫu chỉ minh họa định dạng trình bày. Trong thực tế cần tách **nonconformity do thiếu approval** với **evidence/data gap do thiếu actor** khi quy trình ghi findings riêng.

## 10. Viết audit finding từ tiêu chí và bằng chứng

Một finding hữu ích thường trình bày:

1. **Criterion:** yêu cầu chính xác, nguồn, phiên bản và phạm vi.
2. **Condition:** thực trạng quan sát được, bao nhiêu trường hợp, ở đâu, khi nào.
3. **Evidence:** raw/source ID, test result, dữ liệu đối chiếu và giới hạn.
4. **Cause:** nguyên nhân đã được xác minh hoặc giả thuyết đang điều tra; không đoán.
5. **Effect/risk:** tác động hoặc rủi ro hợp lý, không thổi phồng thành sự cố đã xảy ra nếu chưa có bằng chứng.
6. **Recommendation/action:** control sửa cần thiết, owner, deadline, cách xác minh.
7. **Management response:** phản hồi, plan hoặc risk acceptance theo thẩm quyền.
8. **Retest result:** kết luận sau khắc phục bằng phép kiểm chứng, không chỉ xác nhận có ticket đóng.

### 10.1. Ví dụ finding

**Criterion:** SEC-IAM-04 v3.2 yêu cầu phê duyệt trước khi cấp đặc quyền trong production.

**Condition:** trong tập event đã kiểm tra, hai lần tăng quyền admin thành công không có approval hợp lệ tương ứng theo actor, target và timestamp.

**Evidence:** IAM audit event EV-0012, EV-0013; danh sách approval EV-0021 và truy vấn đối chiếu có version.

**Risk:** quyền được tăng mà không qua xét duyệt có thể làm tăng khả năng lạm dụng và khó quy trách nhiệm. Bằng chứng hiện có **chưa chứng minh** các tài khoản đó đã bị chiếm quyền hoặc thực hiện tấn công.

**Root cause:** chưa xác định; cần điều tra các đường cấp quyền qua API/automation ngoài workflow.

**Action:** giới hạn đường thay đổi quyền, bổ sung approval gate và detection, đánh giá quyền hiện tại, rà soát hoạt động trong kỳ; có owner, hạn và regression tests.

**Closure:** chỉ đóng khi việc sửa đã được triển khai và kiểm tra với test case có thay đổi không được phép, cùng review những quyền còn hiệu lực. Trường hợp không thể sửa theo hạn phải có exception/risk decision rõ; không chuyển status của finding sang "resolved" chỉ vì đã phê duyệt plan.

### 10.2. Tránh nhầm finding với recommendation

| Trường hợp | Cách trình bày phù hợp |
|---|---|
| Có yêu cầu rõ và thực tế không đáp ứng. | Nonconformity/finding theo chính sách kiểm toán. |
| Evidence thiếu, không thể xác minh control. | Evidence gap hoặc inconclusive với action bổ sung. |
| Control đạt yêu cầu nhưng có thể tăng mức bảo vệ. | Improvement opportunity/recommendation, không giả danh vi phạm. |
| Risk ngoài scope/criterion hiện có. | Risk observation và đề xuất risk assessment, không tùy ý gán nonconformity. |
| Ngoại lệ được chấp thuận hợp lệ nhưng tạo residual risk. | Ghi risk/exception, kiểm tra điều kiện và ngày hết hạn. |

## 11. Ranh giới kiểm toán, tính độc lập và đạo đức

### 11.1. Tính độc lập không đồng nghĩa xa rời hệ thống

Người đánh giá nên có vị thế đủ độc lập để kiểm tra bằng chứng và báo cáo finding khách quan. Chủ sở hữu control có thể cung cấp tài liệu và giải thích nhưng không nên tự đơn phương xóa kết quả fail do mình gây ra.

Với tổ chức nhỏ khó phân vai, cần các biện pháp bù trừ như reviewer khác phê duyệt kết luận, giữ raw evidence chống sửa, hoặc đánh giá định kỳ bởi bên độc lập theo rủi ro.

### 11.2. Kiểm tra có quyền và giới hạn tác động

Audit test kỹ thuật cần:

- Phạm vi và quyền được xác nhận trước khi thực hiện.
- Dữ liệu/test account và môi trường phù hợp.
- Không tự ý xóa log, tắt MFA production, cấp cluster-admin hay làm gián đoạn dịch vụ để chứng minh điểm yếu.
- Ghi lại thao tác tạo ra thay đổi, thời gian, người thực hiện và cleanup.
- Có phương án xử lý khi test vô tình kích hoạt incident response.

Một bài test xâm nhập thực tế không nhất thiết là cách tốt nhất để chứng minh criterion nếu có thể dùng negative access test, sandbox, policy simulation hoặc replay event được kiểm soát.

### 11.3. Bảo vệ bằng chứng kiểm toán

Bằng chứng IAM, audit log, kiến trúc hoặc báo cáo vendor có thể chứa dữ liệu cá nhân, bí mật, thông tin bảo mật nhạy cảm. Cần áp dụng:

- RBAC, phân loại dữ liệu, lưu trữ mã hóa và audit truy cập.
- Redaction trên bản dẫn xuất; giữ nguồn phù hợp theo thẩm quyền.
- Retention theo mục đích, kỳ kiểm toán và nghĩa vụ áp dụng.
- Link tới bằng chứng gốc bằng ID; không sao chép secrets vào báo cáo.
- Integrity/hash/version khi cần, với chain-of-custody phù hợp mức rủi ro.

**Audit criteria phải điều chỉnh theo khả năng thu dữ liệu hợp pháp và an toàn**, nhưng không nên lược bỏ rủi ro trọng yếu chỉ vì dữ liệu khó tiếp cận. Nếu không kiểm tra được, ghi rõ limitation và tìm cách đánh giá thay thế.

## 12. Audit criteria cho bên thứ ba và cloud shared responsibility

Khi kiểm toán một SaaS hoặc cloud provider, cần tách:

- **Vendor criterion:** nhà cung cấp phải đáp ứng điều gì theo hợp đồng/phạm vi báo cáo?
- **Customer criterion:** tổ chức phải cấu hình hoặc vận hành gì tại tenant/integration?
- **Shared criterion:** hoạt động yêu cầu cả hai phối hợp như incident notification, access revocation hoặc data deletion.

Ví dụ:

| Criterion | Bên chịu trách nhiệm | Cách đánh giá |
|---|---|---|
| Vendor bảo vệ dữ liệu trong data plane theo phạm vi thỏa thuận. | Vendor. | Scope báo cáo độc lập, hợp đồng, technical evidence phù hợp. |
| Tenant production bật MFA và hạn chế quyền API token. | Customer. | Tenant config, IAM export, negative test. |
| Sự cố ảnh hưởng dữ liệu được thông báo qua kênh và thời hạn được thỏa thuận. | Vendor và customer. | Contract, contact list, exercise hoặc incident sample. |
| Offboarding thu hồi token và ngừng data flow. | Customer. | Revoke test, network/API logs, integration inventory. |
| Vendor xóa dữ liệu theo thỏa thuận và nghĩa vụ áp dụng. | Vendor. | Deletion procedure, confirmation, scope/retention limits. |

Đọc báo cáo SOC 2/ISO của vendor phải đối chiếu **pháp nhân, hệ thống, kỳ, loại kiểm tra, exceptions, phạm vi subservice và nghĩa vụ phía khách hàng**. Báo cáo bên thứ ba không tự chứng minh cấu hình IAM/API của tenant khách hàng đạt.

Nếu vendor không chia sẻ raw event vì bảo mật, có thể dùng assurance report, walkthrough có kiểm soát hoặc test phía khách hàng, nhưng ghi rõ phần không có bằng chứng trực tiếp và độ tin cậy còn lại.

## 13. Audit criteria cho hệ thống cloud-native và vận hành liên tục

### 13.1. Những criterion kỹ thuật tiêu biểu

| Lĩnh vực | Ví dụ criterion có thể đo | Evidence thường dùng |
|---|---|---|
| **IAM** | Các lần tăng đặc quyền trong kỳ có approval hợp lệ; user admin chịu MFA policy. | IAM inventory/history, IdP policy, approval audit, access tests. |
| **Kubernetes workload** | Workload thuộc scope không chạy privileged/hostPath ngoài exception đã phê duyệt. | Admission policy, PodSpecs hiện thực, runtime snapshot, exception register. |
| **Network segregation** | Các đường truy cập nhạy cảm chỉ cho phép source/destination được định nghĩa. | Network policy, effective rules, authorized reachability tests, flow logs. |
| **Encryption & keys** | Data store thuộc scope dùng encryption và key ownership phù hợp policy. | Storage/IAM/KMS config, key access tests, rotation/audit. |
| **Security logging** | Nguồn critical gửi event và việc ngừng nguồn được cảnh báo. | Source inventory, pipeline health, canary, alert evidence. |
| **Detection & response** | Một threat use case xác định tạo alert đúng kênh trong mục tiêu thời gian. | Rule version, positive/negative tests, event-alert-case timeline. |
| **Change management** | Thay đổi production có review/approval và artifact traceability. | Git commit, CI/CD records, deployed digest, approvals. |
| **Vulnerability remediation** | Findings trong scope được xử lý theo SLA/risk policy hoặc có ngoại lệ hợp lệ. | Scanner scope, tickets, patch status, retest/exception. |
| **Backup/DR** | Dịch vụ Critical phục hồi đạt tiêu chí RTO/RPO đã phê duyệt trong kịch bản test. | Exercise, recovery point markers, timestamps, data validation. |
| **Third-party** | Tích hợp quan trọng chỉ dùng permissions/data đã phê duyệt và có review còn hiệu lực. | OAuth/IAM snapshot, data-flow tests, vendor evidence review. |

Đây là **ví dụ loại criterion**, không phải bộ chuẩn kiểm toán bắt buộc. Từng hàng phải được chuyển thành requirement cụ thể với threshold, scope, period và decision rule của tổ chức.

### 13.2. Liên hệ IaC, Policy as Code và Continuous Control Monitoring

Một số criterion phù hợp kiểm tra tự động:

- Không tạo storage bucket public trong phạm vi data classification nhất định.
- Không cấp cloud IAM wildcard permission ngoài danh sách đã phê duyệt.
- Kubernetes workload có securityContext/Pod Security phù hợp baseline.
- Backup retention và logging source được cấu hình theo policy.
- Artifact deployed có digest thuộc tập đã được phê duyệt.

**Policy as Code** có thể kiểm tra cấu hình trước deploy và quan sát trạng thái sau deploy. Tuy nhiên, cần phân biệt:

1. **Pre-deployment test:** xác minh manifest/IaC định triển khai không vi phạm criterion.
2. **Runtime drift test:** xác minh trạng thái thực sau khi deploy.
3. **Operating effectiveness:** xác minh controls thực sự ngăn chặn, ghi log hoặc xử lý hành vi theo thời gian.

Một pipeline CI green không chứng minh runtime chưa bị sửa qua console/API sau deploy. Continuous monitoring cũng không thay thế hoàn toàn review con người khi criterion cần đánh giá ngữ cảnh, phê duyệt và hiệu quả.

### 13.3. Ví dụ pseudo-policy và quy tắc quyết định

~~~text
CRITERION: AC-K8S-SEC-005
SOURCE: K8S-BASELINE v2.4
POPULATION: all production pods within approved cluster inventory
CONDITION:
  privileged == false
  AND hostPID == false
  AND hostNetwork == false
  UNLESS approved exception applies with correct scope and validity

CHECK:
  compare workload templates + actual PodSpec
  review admission policy and denial events
  inspect exceptions by namespace / workload / expiry

PASS:
  checked population meets policy or documented valid path
FAIL:
  observed workload violates applicable policy
INCONCLUSIVE:
  cluster/pod inventory or runtime state not reliably available
EVIDENCE:
  cluster scope, scan/query version, timestamp,
  effective PodSpec, approval record and reviewer
~~~

**Cẩn trọng:** trường hợp policy cho phép ngoại lệ phải được giải thích đúng theo văn bản có hiệu lực. Không được bỏ qua các workload thiếu telemetry và coi là compliant.

## 14. Từ audit criteria đến chương trình assurance liên tục

~~~mermaid
flowchart TD
    A["Risk & security objectives"] --> B["Requirements & scope"]
    B --> C["Audit criteria register"]
    C --> D["Controls & owners"]
    D --> E["Examine / Interview / Test"]
    E --> F["Evidence quality review"]
    F --> G{"Verdict"}
    G -->|Conform| H["Lưu evidence, theo dõi và tái đánh giá"]
    G -->|Nonconform| I["Finding + remediation + retest"]
    G -->|Inconclusive| J["Làm rõ data gap + kiểm tra lại"]
    I --> E
    J --> E
    H --> A
~~~

### 14.1. Khi nào phải cập nhật criteria?

- Thay đổi luật, hợp đồng, policy hoặc framework/version.
- Thay đổi kiến trúc, cloud account, cluster, data classification hoặc trust boundary.
- Có rủi ro mới, phát hiện security incident hoặc thay đổi mức tác động.
- Phát hiện criterion không thể đo hoặc bằng chứng quá yếu.
- Biên bản kiểm toán cho thấy reviewer diễn giải tiêu chí không nhất quán.
- Thay đổi chủ sở hữu control, quy trình, nhà cung cấp hay cách thu telemetry.
- Các ngoại lệ kéo dài, findings lặp lại hoặc nguy cơ drift.

Đổi criterion sau khi thấy kết quả fail để hợp thức hóa trạng thái không nên được dùng làm cách đóng finding. Nếu yêu cầu thực sự cần điều chỉnh, ghi decision, thẩm quyền, ngày hiệu lực, rủi ro và **kết quả theo tiêu chí cũ**, rồi áp dụng tiêu chí mới đúng thời điểm.

### 14.2. Quản lý phiên bản tiêu chí

Đề xuất kiểm soát:

- Mỗi criterion có ID ổn định, semantic/version hoặc lịch sử sửa đổi.
- Ghi source version, effective date, approved date, scope change.
- Khi thay đổi threshold hoặc phương pháp đánh giá, ghi tác động lên so sánh giữa các kỳ.
- Test procedure và evidence result tham chiếu **criterion version** đã dùng.
- Không ghi đè lịch sử đánh giá cũ khi cập nhật policy.
- Có reviewer signoff và lưu artifact ở nơi kiểm soát truy cập.

### 14.3. KPI hỗ trợ quản lý chương trình

| Chỉ số | Cách đọc | Lưu ý |
|---|---|---|
| **Criteria coverage** | Tỷ lệ risk/control objectives trong scope có criterion và owner rõ. | Tiêu chí tồn tại không đồng nghĩa test hiệu quả. |
| **Assessment execution coverage** | Tỷ lệ criterion đến hạn được đánh giá đủ theo phương pháp đã định. | Không tính Not run như Pass. |
| **Evidence sufficiency rate** | Tỷ lệ phép đánh giá có evidence thích hợp và đủ cho verdict. | Mẫu số, định nghĩa và độ tin cậy phải công bố. |
| **Nonconformity trend** | Số finding theo loại, severity, kỳ, rủi ro và tỷ lệ tái diễn. | Số finding ít có thể phản ánh kiểm tra yếu. |
| **Remediation retest rate** | Findings đã được xác minh lại / findings đã báo khắc phục. | Ticket đóng chưa đủ để tính retest thành công. |
| **Exception aging** | Ngoại lệ quá hạn, sắp hết hạn và rủi ro tồn dư. | Cần owner, phạm vi và điều kiện rà soát. |
| **Data-quality gap** | Tỷ lệ criterion chưa kết luận do thiếu nguồn/population. | Đặc biệt quan trọng ở môi trường cloud và log phân tán. |
| **Assessment consistency** | Số bất đồng reviewer theo tiêu chí/quy tắc đánh giá. | Dùng cải tiến criterion mơ hồ. |

Chỉ số phải giúp **ưu tiên hành động**, không khuyến khích auditor giảm chất lượng để tăng tỷ lệ Pass.

## 15. Bài tập tình huống: tiêu chí thiếu chính xác

**Bối cảnh:** chính sách của công ty viết "Mọi hệ thống quan trọng phải có khả năng khôi phục và giám sát bảo mật tốt". Auditor kiểm tra ba hệ thống và kết luận đều đạt vì có backup và dashboard. Sau một sự cố, đội vận hành không giải mã được backup của hệ thống A, SIEM không nhận log từ cluster B và alert của hệ thống C không có người trực tiếp nhận.

### 15.1. Phân tích vấn đề

1. **Nguồn yêu cầu mơ hồ:** không xác định hệ thống quan trọng là những hệ thống nào; không định nghĩa recoverability và giám sát tốt.
2. **Thiếu tiêu chí đo:** RTO/RPO, thời điểm restore test, logging source coverage, detection, routing và SLA chưa được làm rõ.
3. **Bằng chứng không đủ:** backup job và dashboard chỉ thể hiện một phần cấu hình, không chứng minh khôi phục hoặc phản ứng thật.
4. **Population thiếu:** chưa đối chiếu danh sách mọi hệ thống Critical và các nguồn telemetry bắt buộc.
5. **Audit conclusion vượt phạm vi:** trạng thái "đạt" được đưa ra dù chưa thử khả năng giải mã, khôi phục và nhận alert.
6. **Finding cần xử lý cả hai cấp:** lỗ hổng vận hành thực tế và lỗ hổng thiết kế audit criteria/assessment procedure.

### 15.2. Viết lại ba tiêu chí

**AC-DR-01:** "Đối với mọi hệ thống Critical theo BIA và scope đánh giá, phải có restoration exercise trong chu kỳ chính sách; thành công được xác định bằng khôi phục chức năng nghiệp vụ, kiểm tra dữ liệu, quyền giải mã và mốc RTO/RPO được chấp thuận. Kết quả chưa thử không được tính là đạt."

**AC-LOG-01:** "Đối với mọi nguồn audit Critical theo logging inventory, hệ thống phải phát và truyền event về pipeline theo baseline; có kiểm tra telemetry health/coverage và ghi nhận vùng dữ liệu thiếu."

**AC-DET-01:** "Đối với những use case phát hiện thuộc phạm vi ưu tiên, thử nghiệm có kiểm soát phải tạo alert đủ context và đến đúng người/kênh trong mốc thời gian được chấp thuận; positive, negative và routing test được lưu kết quả."

Các chu kỳ và ngưỡng phải lấy từ chính sách có hiệu lực, BIA và risk appetite. Nếu tổ chức chưa có, báo một **control design gap** và yêu cầu owner phê duyệt thay vì giả định một tiêu chuẩn mới rồi cho FAIL tất cả.

### 15.3. Ma trận kiểm tra sau sửa

| Test ID | Điều kiện kiểm thử | Expected | Evidence |
|---|---|---|---|
| DR-T01 | Khôi phục bản backup A trong môi trường được phép, sử dụng key và quyền của đường recovery. | Giải mã, khôi phục và kiểm tra chức năng/data integrity theo contract; ghi achieved RTO/RPO. | Restore job, key-access test, app validation, timeline. |
| LOG-T01 | So inventory với nguồn cloud/K8s và kiểm tra heartbeat. | Mọi nguồn bắt buộc trong scope có telemetry hợp lệ hoặc gap được ghi. | Asset inventory, source health và audit records. |
| DET-T01 | Tạo sự kiện phát hiện có kiểm soát trong phạm vi đã duyệt. | Alert có actor/target, delivered đúng kênh, thời gian trong SLA. | Raw event, detection rule version, alert/case timeline. |
| DET-T02 | Hành vi hợp lệ gần giống rule nhưng không vi phạm. | Không báo sai theo negative test contract. | Fixture/authorized test, test result. |
| GOV-T01 | Kiểm tra một số exception theo thẩm quyền và kỳ. | Phạm vi, approval, hạn, compensating control và review đều đầy đủ. | Exception register, approvals, test evidence. |

Khi kiểm tra lần đầu có thể có kết quả **FAIL hoặc INCONCLUSIVE**, đây là kết quả có giá trị vì chỉ ra nơi cần sửa và bằng chứng còn thiếu.

## 16. Checklist trước khi chốt một audit criterion

- [ ] Criterion có ID, source, version, ngày hiệu lực và owner.
- [ ] Audit objective và risk/control objective được diễn giải rõ.
- [ ] Phạm vi gồm hệ thống, dữ liệu, account, tenant, môi trường và kỳ đánh giá.
- [ ] Population có mẫu số hoặc tiêu chí xây dựng danh sách đối tượng.
- [ ] Điều kiện đạt mô tả trạng thái/hành vi có thể quan sát, không dùng từ mơ hồ.
- [ ] Threshold, deadline, frequency và phương pháp đo được chốt khi cần.
- [ ] Có quy tắc cụ thể cho ngoại lệ, biến thể hợp lệ và trường hợp không áp dụng.
- [ ] Đã phân biệt đánh giá design, implementation và operating effectiveness.
- [ ] Phương pháp examine/interview/test được chọn theo rủi ro và tính khả thi.
- [ ] Có danh mục evidence cần thu, nguồn, timestamp, phiên bản và cách bảo vệ.
- [ ] Kiểm tra completeness của nguồn trước khi tin vào kết quả từ dữ liệu.
- [ ] Sampling có phương pháp và giới hạn kết luận rõ.
- [ ] Kết quả Pass/Fail/Inconclusive/Not assessed/Not applicable được định nghĩa.
- [ ] Risk acceptance được ghi riêng, không biến sự không phù hợp thành Pass.
- [ ] Finding liên kết criterion, condition, evidence và impact mà không suy diễn quá mức.
- [ ] Remediation có owner, deadline, test chấp nhận và retest.
- [ ] Bằng chứng được lưu đúng quyền, bảo toàn provenance, bảo vệ PII/secret.
- [ ] Có reviewer đủ độc lập và khả năng tái hiện/đối chiếu kết luận.
- [ ] Những thay đổi policy, kiến trúc, threat hoặc nguồn log kích hoạt review criterion.
- [ ] Kết luận báo cáo chỉ áp dụng cho **đúng phạm vi, kỳ, phương pháp và dữ liệu đã kiểm chứng**.

## 17. Câu hỏi tự đánh giá

1. Audit objective, audit criteria và audit evidence khác nhau ở điểm nào? Hãy đặt một ví dụ cho quyền truy cập cloud.
2. Vì sao "SIEM đã được bật" không đủ làm criterion cho năng lực phát hiện hành vi tắt audit logging?
3. Một policy version mới có hiệu lực từ tháng 11 có thể dùng trực tiếp để kết luận mọi sự kiện tháng 9 không phù hợp không? Cần xem gì?
4. Khi auditor tìm thấy một thay đổi quyền thiếu approval trong mẫu risk-based, có được suy tỷ lệ lỗi của toàn bộ population không?
5. Làm thế nào phân biệt control được thiết kế phù hợp, đã được triển khai và vận hành hiệu lực?
6. Khi raw IAM log thiếu actor ID, vì sao không nên mặc định event đạt hoặc không có rủi ro?
7. Risk acceptance có làm cho một nonconformity tự động trở thành Pass không?
8. Một báo cáo SOC 2 của SaaS có tự chứng minh tenant khách hàng đã bật MFA và phân quyền đúng không?
9. Nếu hai reviewer dùng cùng evidence nhưng ra kết luận khác nhau, cần xem lại những yếu tố nào của criterion và test procedure?
10. Hãy viết một criterion có ID, source/version, population, period, condition, evidence, method và verdict cho mục tiêu backup recovery hoặc detection engineering mà bạn lựa chọn.

**Điểm cốt lõi:** **Audit criteria là thước đo đã được xác lập và có thể kiểm chứng**, không phải tên một công cụ hay cảm nhận của người đánh giá. Trong security assurance, một tiêu chí có giá trị khi liên kết được **rủi ro và yêu cầu với control thực tế, phép thử thích hợp, bằng chứng đủ độ tin cậy, quy tắc kết luận minh bạch và vòng khắc phục**. Chỉ khi đó audit mới hỗ trợ cải thiện bảo mật liên tục thay vì tạo một danh sách checkbox đã được đánh dấu.
