# Chuẩn bằng chứng

Trong chương **Security standard**, **chuẩn bằng chứng** (*evidence standard*) là tập tiêu chí và quy tắc mà tổ chức dùng để xác định **bằng chứng nào có thể được chấp nhận, bằng chứng phải được tạo và bảo quản như thế nào, và bằng chứng đủ sức hỗ trợ kết luận bảo mật đến đâu**. Một bộ chuẩn tốt giúp kết quả kiểm thử, cấu hình, log, hồ sơ phê duyệt và báo cáo kiểm toán không chỉ “tồn tại” mà còn **đúng mục tiêu, đúng phạm vi, đáng tin, kịp thời, có thể truy vết và tái kiểm tra**.

Giả sử nền tảng học trực tuyến tuyên bố: “Mọi tài khoản quản trị production đều được bảo vệ bằng MFA”. Ảnh chụp một trang cấu hình MFA là bằng chứng có ích, nhưng chưa chứng minh tất cả tài khoản, ứng dụng, phương thức đăng nhập và cơ chế truy cập khẩn cấp đều được bao phủ trong kỳ đánh giá. Một **chuẩn bằng chứng** phải quy định thêm cách xác định tập tài khoản, nguồn cấu hình đáng tin, phép thử đường đăng nhập, kỳ lấy dữ liệu, cách ghi nhận ngoại lệ và điều kiện để được kết luận “đạt”.

Bài học thuộc module **SECURITY_SECURITY_ASSURANCE**, có mục tiêu xây dựng phương pháp đánh giá có bằng chứng rằng hệ thống đạt các mục tiêu bảo mật, từ rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục finding, và tổ chức assurance liên tục trong phát triển, vận hành. Vì vậy, chuẩn bằng chứng chính là **cầu nối giữa hoạt động kỹ thuật thực tế và một kết luận bảo đảm có thể giải thích, kiểm tra lại**.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích chuẩn bằng chứng và phân biệt nó với security policy, security standard, procedure, control, kết quả kiểm thử và báo cáo assurance.
2. Xác định **claim**, **tiêu chí kiểm chứng**, **control**, **nguồn evidence**, **phạm vi**, **kỳ đánh giá** và **owner**.
3. Đánh giá bằng chứng về tính liên quan, đầy đủ, đáng tin, toàn vẹn, hiện hành, chính xác, độc lập và khả năng tái thực hiện.
4. Thiết kế yêu cầu metadata và quy trình thu thập, phiên bản hóa, bảo quản, phân quyền, lưu trữ và tiêu hủy evidence.
5. Chọn phương pháp kiểm chứng thủ công, tự động và lấy mẫu phù hợp với rủi ro, không suy diễn quá phạm vi dữ liệu.
6. Xây dựng bảng ánh xạ requirement → control → test → evidence → assessment → finding/retest.
7. Đưa ra kết luận **đạt**, **không đạt**, **chưa đủ bằng chứng** hoặc **không áp dụng** với lý do và giới hạn rõ ràng.
8. Triển khai chuẩn bằng chứng vào CI/CD, hệ thống cloud, IAM, logging, incident response và đánh giá nhà cung cấp.

## 2. “Chuẩn bằng chứng” trong security assurance nghĩa là gì?

### 2.1. Không phải chỉ là nơi lưu tài liệu

Một thư mục chứa policy PDF, log, kết quả scanner và screenshot **chưa chắc tạo được assurance**. Nếu không biết dữ liệu thuộc hệ thống nào, có phản ánh production hay không, ai đã tạo, lúc nào, bằng công cụ nào, nó chứng minh requirement nào và các ngoại lệ đã được ghi hay chưa, người đánh giá không thể đưa kết luận tin cậy.

Chuẩn bằng chứng nên xác định tối thiểu:

- **Đối tượng được chứng minh:** mục tiêu bảo mật, requirement, control và claim.
- **Tiêu chí chấp nhận:** thế nào là control đạt, không đạt, chưa thể xác minh hoặc không áp dụng.
- **Loại bằng chứng được phép:** cấu hình thực tế, log, record, test, review, báo cáo độc lập, lời xác nhận có kiểm chứng.
- **Nguồn và phương pháp thu thập:** hệ thống nguồn, công cụ, danh tính người thu thập, truy vấn/script, tần suất.
- **Phạm vi và thời kỳ:** môi trường, tài sản, user, tenant, sản phẩm, phiên bản, thời điểm hoặc kỳ vận hành.
- **Yêu cầu chất lượng:** completeness, integrity, reliability, freshness, relevance, representativeness.
- **Bảo quản và truy cập:** phân loại dữ liệu, kiểm soát sửa/xóa, retention, đường truy vết, quyền xem.
- **Người chịu trách nhiệm:** control owner, evidence producer, evidence owner, reviewer và decision authority.
- **Xử lý sai lệch:** evidence gap, finding, remediation, retest, ngoại lệ và tái đánh giá.

Một tổ chức có thể gọi tài liệu này là **Evidence Collection Standard**, **Assurance Evidence Requirements**, **Control Testing Standard** hoặc một phần của quy trình GRC. Không có một **“chuẩn bằng chứng” phổ quát duy nhất** mặc định bắt mọi hệ thống cùng một cấu trúc và tần suất.

### 2.2. Quan hệ với policy, standard và procedure

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Security policy** | Tổ chức yêu cầu hoặc cam kết nguyên tắc bảo mật gì? | Quyền quản trị production phải được kiểm soát |
| **Security standard** | Tiêu chí và mức tối thiểu phải đáp ứng là gì? | Quyền admin phải có owner, xác thực phù hợp và log |
| **Evidence standard** | Bằng chứng nào, chất lượng ra sao, kiểm tra thế nào để chứng minh yêu cầu? | Xuất danh sách quyền từ nguồn thực, kiểm thử đường admin và đối chiếu lịch sử cấp/thu hồi |
| **Procedure/runbook** | Ai thực hiện từng bước, ở đâu, khi nào? | Trình tự lấy IAM export, chọn mẫu và lưu record đánh giá |
| **Security control** | Biện pháp giảm rủi ro cụ thể là gì? | SSO/MFA, least privilege, approval workflow |
| **Evidence artifact** | Dữ liệu quan sát hoặc record nào được thu thập? | IAM export có timestamp, test report, change log |
| **Assurance claim/result** | Dựa trên evidence có thể kết luận điều gì trong scope nào? | Các đường admin được kiểm tra đáp ứng tiêu chí trong kỳ, trừ ngoại lệ đã ghi |

**Bằng chứng là đầu vào để kết luận**, không phải bản thân kết luận. Một control được cấu hình tồn tại không đồng nghĩa nó vận hành hiệu quả; một báo cáo kiểm toán không tự động chứng minh mọi hệ thống ngoài scope của báo cáo cũng đạt.

### 2.3. Bằng chứng vận hành, kiểm toán và pháp chứng

Cần phân biệt mục đích sử dụng:

1. **Operational evidence:** phục vụ quan sát, kiểm thử và đánh giá control đang hoạt động: CI/CD result, IAM export, log, restore test.
2. **Audit/compliance evidence:** hỗ trợ assessor đối chiếu các yêu cầu trong phạm vi và kỳ audit: policy, approval, sample change records, kết quả kiểm soát.
3. **Incident/forensic evidence:** dùng để tái dựng sự kiện, điều tra và có thể phục vụ thủ tục pháp lý: log gốc, image, timeline, hồ sơ người tiếp nhận, chain of custody.

Các nhóm **có thể giao nhau nhưng không hoàn toàn thay thế nhau**. Một screenshot dashboard có thể hữu ích trong báo cáo vận hành nhưng chưa đáp ứng yêu cầu bảo toàn nguyên trạng và truy vết người tiếp nhận của một cuộc điều tra pháp chứng. Khi evidence có thể dùng cho điều tra/kiện tụng, cần tuân thủ quy trình pháp chứng và pháp lý áp dụng, không áp dụng một checklist chung như thể đủ cho mọi trường hợp.

## 3. Từ mục tiêu bảo mật đến claim cần chứng minh

Chuẩn bằng chứng chỉ có ý nghĩa khi biết **nó dùng để chứng minh điều gì**.

Một claim tốt có:

- **Chủ thể:** hệ thống, tenant, nhóm tài khoản, release, vendor hoặc quy trình.
- **Yêu cầu:** thuộc tính bảo mật hoặc hành vi mà control phải bảo đảm.
- **Phạm vi:** các tài sản, environment, đường truy cập và loại dữ liệu được xét.
- **Thời gian:** trạng thái tại một thời điểm hoặc hiệu quả xuyên suốt một kỳ.
- **Tiêu chí:** điều kiện đạt và cách xử lý ngoại lệ.
- **Giả định và giới hạn:** những gì chưa được quan sát, chưa thử hoặc bị loại trừ có căn cứ.

**Claim quá rộng:** “Hệ thống bảo mật tốt và mọi tài khoản đều an toàn.”

**Claim kiểm chứng được:** “Trong kỳ đánh giá nội bộ đã xác định, tất cả tài khoản con người có quyền quản trị production thuộc inventory được đối chiếu với chính sách MFA, có owner, và các đường đăng nhập quan trọng được thử theo tiêu chí đã phê duyệt; các ngoại lệ được ghi riêng.”

### 3.1. Chuỗi Claim–Argument–Evidence (CAE)

**Claim:** Các thay đổi policy IAM trên production được quản lý và theo dõi theo tiêu chí nội bộ.

**Argument:** Mọi thay đổi thuộc phạm vi đều có định danh owner và nguồn phê duyệt, đi qua đường triển khai được kiểm soát; monitoring phát hiện thay đổi ngoài quy trình; phép kiểm tra đối chiếu trạng thái production và lịch sử thay đổi.

**Evidence:** Danh mục IAM policy, pull request/change record, approval, kết quả pipeline, cloud audit event, kết quả drift detection, bản xuất cấu hình thực tế, ticket xử lý sai lệch.

**Giới hạn:** Nếu có một tài khoản break-glass cho phép thay đổi trực tiếp chưa thuộc logging hoặc cơ chế giám sát, không thể tuyên bố toàn bộ thay đổi production được bao phủ.

### 3.2. Traceability là yêu cầu cốt lõi

~~~mermaid
flowchart TD
    A["Tài sản và mục tiêu bảo mật"] --> B["Risk scenario / yêu cầu"]
    B --> C["Security control và tiêu chí đạt"]
    C --> D["Evidence standard và test method"]
    D --> E["Dữ liệu nguồn, test, log, record"]
    E --> F["Đánh giá chất lượng và kết luận"]
    F --> G{"Đủ bằng chứng và control đạt?"}
    G -->|"Có"| H["Assurance claim theo phạm vi và kỳ"]
    G -->|"Không hoặc chưa rõ"| I["Finding / evidence gap / remediation"]
    I --> D
    H --> J["Residual risk và quyết định"]
    J --> K["Giám sát thay đổi và review tiếp theo"]
    K --> B
~~~

Một evidence artifact có thể hỗ trợ nhiều requirement, nhưng **phải chứng minh từng quan hệ**. Ngược lại, một requirement quan trọng thường cần nhiều bằng chứng bổ sung nhau: policy thể hiện kỳ vọng, config cho biết trạng thái đã áp dụng, test cho biết hành vi khi thực thi, history cho biết hiệu quả trong kỳ.

## 4. Tám tiêu chí chất lượng bằng chứng

### 4.1. Relevance – đúng nội dung cần chứng minh

Bằng chứng phải gắn với **mục tiêu và control** đang được hỏi.

Ví dụ, báo cáo quét dependency có thể hỗ trợ đánh giá lỗ hổng thư viện nhưng không tự chứng minh API đã có authorization theo lớp học. Một chính sách “yêu cầu kiểm tra quyền” không chứng minh hệ thống thực sự từ chối truy cập chéo lớp.

**Câu hỏi:** Evidence này trực tiếp hỗ trợ claim nào? Nếu bỏ evidence này đi, phần lập luận nào mất chỗ dựa?

### 4.2. Scope/completeness – đủ phạm vi và đầy đủ

Cần biết **tổng thể** cần kiểm tra và phần đã thu thập:

- Tất cả môi trường nào: production, staging, multi-region?
- Tất cả account nào: nhân sự, workload, emergency, bên thứ ba?
- Tất cả tuyến nào: web, mobile, API, background job, batch, admin?
- Kỳ nào: trạng thái tại ngày chụp hay xuyên suốt ba tháng?
- Có loại trừ nào và vì sao? Có tài sản không tìm thấy trong inventory không?

Ví dụ, xuất danh sách 100 tài khoản admin từ một hệ thống IAM là chưa đủ nếu quyền admin còn tồn tại trong cloud account khác hoặc qua local account không nằm trong nguồn xuất.

### 4.3. Provenance – truy xuất được nguồn gốc

Bằng chứng cần cho biết ai hoặc cơ chế nào tạo ra nó, từ đâu, theo thao tác gì và vào thời điểm nào.

Một test report nên có **test suite/version, build hoặc commit, environment, execution time, dataset, actor và kết quả**. Một cấu hình phải có tên hệ thống, account/project, thời điểm export và phạm vi API/query. Một ticket nên có ID, người thay đổi, trạng thái và lịch sử phê duyệt.

Một file tên “final_security_report.pdf” nhưng không xác định nguồn, thời gian và phiên bản sẽ khó dùng làm bằng chứng chắc chắn.

### 4.4. Integrity – toàn vẹn và chống thay đổi không được phép

Cần kiểm soát việc bằng chứng bị sửa, thay thế, xóa hoặc trộn dữ liệu không đúng:

- Phân quyền tách người tạo, người đánh giá và người quản trị kho evidence khi khả thi.
- Giữ dấu vết tạo/sửa/đọc/xóa đối với evidence nhạy cảm.
- Dùng cơ chế lưu trữ có phiên bản, retention/immutability phù hợp rủi ro.
- Có thể ghi digest, chữ ký và thời điểm từ nguồn đáng tin nếu cần.
- Đối chiếu với dữ liệu nguồn chính thức khi đánh giá.

**Lưu ý:** Hash giúp kiểm tra một bản sao có thay đổi so với **giá trị hash đáng tin được ghi nhận trước đó** hay không. Nó **không tự chứng minh** nội dung ban đầu là đúng hoặc do nguồn được tuyên bố tạo ra. Chữ ký số và timestamp đáng tin có thể tăng khả năng xác minh xuất xứ, nhưng vẫn cần quản trị khóa và nguồn.

### 4.5. Freshness/timeliness – còn giá trị ở thời điểm kết luận

Bằng chứng phải phù hợp với **mốc thời gian, kỳ đánh giá và tốc độ thay đổi** của control.

Ví dụ:

- Chính sách có thể được review theo chu kỳ.
- Config cloud có thể thay đổi sau mỗi deployment, cần lấy trạng thái hoặc history tương ứng.
- Quyền IAM có thể biến động khi nhân sự thay vai trò, nên phải xét cấp/thu hồi theo thời kỳ.
- Restore test có giá trị theo hệ thống, loại dữ liệu, phiên bản và điều kiện khôi phục đã thử.
- Báo cáo pentest hoặc vendor assessment có thể không còn bao phủ tính năng mới.

Không nên dùng một con số cố định như “mọi bằng chứng có hiệu lực 30 ngày” cho tất cả control. **Thời hạn chấp nhận phải được thiết kế dựa trên rủi ro, biến động và mục tiêu kiểm chứng**.

### 4.6. Accuracy/reliability – độ chính xác và đáng tin

Nguồn dữ liệu có thể thiếu, sai, bị cấu hình không đồng bộ hoặc chứa kết quả giả. Cần kiểm tra:

- Agent logging còn hoạt động không, có mất sự kiện không?
- Đồng hồ của các hệ thống được đồng bộ ở mức phù hợp không?
- Scanner có bao phủ được asset, có quyền scan phù hợp không?
- Dashboard có dùng cùng định nghĩa và cùng population với risk register?
- Script export có filter gây bỏ sót các tài khoản hoặc policy không?
- Tool version và cấu hình test có được ghi lại không?

Một dashboard “0 cảnh báo” có thể là kết quả tốt, nhưng cũng có thể là dấu hiệu rule đã bị vô hiệu hóa. **Không có quan sát** không đồng nghĩa **không có sự kiện**.

### 4.7. Sufficiency/representativeness – đủ sức kết luận

“Đủ” phụ thuộc claim và rủi ro. Một chứng cứ có thể thuyết phục về **thiết kế control** nhưng không đủ về **hoạt động trong cả quý**. Lấy mẫu 5 ticket sạch không tự chứng minh mọi thay đổi production đều được phê duyệt.

Chuẩn cần quy định:

- Claim cần xác nhận **toàn bộ population** hay có thể dùng **sample**.
- Lý do chọn mẫu: rủi ro, tình huống, thời gian, nhóm tài sản, loại thay đổi.
- Cách xử lý mẫu ngoại lệ, thiếu dữ liệu, fail và các trường hợp emergency.
- Mức độ có thể suy rộng từ kết quả mẫu.
- Khi nào phải kiểm tra sâu hơn hoặc kết luận chưa đủ dữ liệu.

### 4.8. Independence/repeatability – khả năng kiểm tra độc lập và lặp lại

Bằng chứng có giá trị hơn khi một người đánh giá khác có thể kiểm tra nguồn, tái chạy test (trong điều kiện an toàn) hoặc đối chiếu logic mà không cần tin vào lời khẳng định đơn lẻ.

Điều đó không có nghĩa mọi bằng chứng phải do bên kiểm toán ngoài tổ chức tạo. **Self-assessment** vẫn hữu ích khi có metadata và kiểm soát thích hợp. Nhưng người phát triển control cũng tự chứng nhận độc lập về control đó có nguy cơ xung đột lợi ích. Mức độ độc lập phải phù hợp mục đích và được trình bày trung thực.

## 5. Mức độ chứng minh: thiết kế, triển khai, vận hành

Một trong các sai lầm lớn nhất là dùng evidence thuộc một lớp để suy ra kết luận ở lớp khác.

| Lớp đánh giá | Câu hỏi | Ví dụ evidence | Điều chưa thể tự suy ra |
|---|---|---|---|
| **Design effectiveness** | Control có được thiết kế để xử lý đúng rủi ro và kịch bản thất bại? | Threat model, architecture, security requirement, review design | Chưa chắc control đã triển khai |
| **Implementation effectiveness** | Control có tồn tại và áp dụng đúng ở trạng thái/môi trường đang xét? | Config export, policy runtime, code/build đã deploy, test hành vi | Chưa chắc hoạt động ổn định cả kỳ |
| **Operating effectiveness** | Control có thực sự vận hành theo tiêu chí qua thời gian và các sự kiện? | Change history, sample giao dịch, log, periodic test, alert/ticket, incident/retest | Chưa chứng minh những tài sản/đường chưa thuộc scope |

**Ví dụ kiểm soát thay đổi:** có policy “mỗi thay đổi phải được phê duyệt” là design evidence. Một pipeline có approval gate đang bật là implementation evidence. Tập thay đổi production trong kỳ có approval hợp lệ, các thay đổi khẩn cấp được quản lý và trường hợp bypass được phát hiện/xử lý là operating evidence.

**Ví dụ backup:** có tài liệu backup và job success không tự chứng minh có thể khôi phục dữ liệu đúng/đủ trong RPO/RTO. Cần bằng chứng restore test với dữ liệu phù hợp, thời gian, kiểm tra tính toàn vẹn và giới hạn điều kiện kiểm thử.

## 6. Phân loại evidence và trường hợp sử dụng

| Loại bằng chứng | Ví dụ | Phù hợp với claim | Hạn chế |
|---|---|---|---|
| **Normative/policy** | Chính sách, tiêu chuẩn, yêu cầu kỹ thuật | Tổ chức đã xác định quy tắc và phê duyệt mục tiêu | Không chứng minh thực thi |
| **Design** | Threat model, DFD, architecture decision, review | Control xử lý các rủi ro được nhận diện theo thiết kế | Có thể lỗi thời sau thay đổi |
| **Configuration** | IAM/network policy export, SSO setting, storage ACL | Control được cấu hình tại thời điểm thu thập | Có thể không phản ánh đường bypass hoặc lịch sử |
| **Execution/test** | Unit/integration/negative test, restore drill, CI result | Hành vi trong điều kiện kiểm thử cụ thể | Không mặc định đại diện production hoặc mọi kịch bản |
| **Transaction/process record** | Ticket cấp quyền, approval, change record | Quy trình có được thực hiện với trường hợp cụ thể | Mẫu không đủ có thể bỏ sót ngoại lệ |
| **Telemetry/log** | Cloud audit, app log, SIEM event, alert/ticket | Quan sát hành vi, thay đổi, phát hiện và phản ứng | Log có thể thiếu hoặc chưa xác minh toàn vẹn |
| **Independent assessment** | Kết quả audit, pentest, certification có scope | Ý kiến hoặc kết quả đánh giá trong phạm vi đã xét | Không tự áp dụng mọi dịch vụ/kỳ mới |
| **Interview/attestation** | Xác nhận owner, trả lời questionnaire | Hiểu quy trình, cam kết và điểm cần kiểm chứng | Phụ thuộc trí nhớ, thiên lệch, ít chứng minh hiệu quả runtime |
| **Remediation/retest** | Fix PR, deploy record, test sau sửa | Chứng minh tìm ra sai lệch và xác nhận khắc phục | Ticket “Done” chưa chứng minh retest |
| **Incident/forensic** | Timeline, log gốc, chain-of-custody record | Điều tra sự kiện và tác động thực tế | Cần bảo quản đặc thù, có thể chứa dữ liệu hạn chế |

Không nên xếp hạng loại evidence một cách tuyệt đối. Một kết quả test được cấu hình sai có thể kém tin hơn một IAM export được xác thực đúng nguồn; một báo cáo audit tốt nhưng không bao phủ dịch vụ đang dùng có thể ít liên quan hơn phép kiểm tra production phù hợp.

## 7. Thiết kế chuẩn metadata bắt buộc

### 7.1. Vì sao metadata quyết định khả năng kiểm tra?

Khi người đánh giá mở một file nhiều tháng sau, họ phải biết nó là **bằng chứng của cái gì**, không phải suy từ tên tệp. Một evidence record đầy đủ có thể có:

1. **Evidence ID** duy nhất, tên, phiên bản và trạng thái.
2. **Claim/requirement/control/test IDs** được hỗ trợ.
3. **Nguồn dữ liệu**: hệ thống, tài khoản/project, API, query, tool, nơi lưu bản gốc.
4. **Scope**: ứng dụng, environment, region, tenant, asset group, user population.
5. **Thời gian**: lúc sự kiện xảy ra, kỳ được bao phủ, lúc trích xuất, múi giờ.
6. **Producer/owner/reviewer** và vai trò.
7. **Phương pháp**: script/query, version, tham số, điều kiện test, cách chọn mẫu.
8. **Kết quả**: dữ liệu, expected/actual, pass/fail, exceptions và limitations.
9. **Tính toàn vẹn**: cơ chế version/digest/chữ ký nếu dùng, nơi xác minh.
10. **Phân loại dữ liệu và quyền truy cập**.
11. **Retention/disposal** theo chính sách và nghĩa vụ áp dụng.
12. **Liên kết** tới finding, risk, remediation, retest hoặc quyết định được duyệt.

Không phải artifact nào cũng cần hàng chục trường do người dùng nhập thủ công. Nên **tự động thu thập metadata từ hệ thống nguồn** và giới hạn các trường bắt buộc theo loại evidence, rủi ro và mục đích.

### 7.2. Ví dụ evidence record dạng YAML

Đây là **schema minh họa của tổ chức**, không phải cấu trúc bắt buộc của ISO, NIST hay SOC.

~~~yaml
evidence_id: EVD-IAM-ADMIN-2026Q4-01
title: "Kiểm tra MFA và quyền quản trị production"
claim_id: CLAIM-IAM-01
requirement_ids: ["REQ-IAM-01", "REQ-IAM-02"]
control_ids: ["CTRL-IAM-MFA", "CTRL-IAM-REVIEW"]
evidence_type: "configuration-and-test"
scope:
  service: "Learning Platform"
  environments: ["production"]
  identity_sources: ["corporate-idp", "cloud-iam"]
  account_population: "Privileged human accounts in approved inventory"
  exclusions: ["Workload identities assessed separately"]
period:
  start: "2026-10-01T00:00:00+07:00"
  end: "2026-10-31T23:59:59+07:00"
collected_at: "2026-11-02T10:00:00+07:00"
source:
  system: "Identity provider and cloud IAM"
  extraction_method: "Approved read-only export and controlled auth tests"
  procedure_version: "EVD-IAM-PROCEDURE-v3"
  source_reference: "restricted-evidence-repository-reference"
producer_role: "IAM Operations"
reviewer_role: "Security Assurance"
expected:
  - "Privileged accounts are correctly identified and reviewed"
  - "Required authentication controls are enforced in scope"
  - "Exceptions are documented with decision authority"
observations:
  - "Kết quả thực tế cần điền sau khi kiểm tra"
limitations:
  - "Không tự chứng minh service accounts có MFA"
integrity:
  method: "Repository versioning and controlled access"
classification: "Internal-Restricted"
retention: "Theo chính sách và nghĩa vụ hiện hành"
assessment_status: "Pending review"
~~~

**Lưu ý:** Mẫu dùng một kỳ giả định và không công bố kết quả test. Nếu evidence chỉ ghi cấu hình tại ngày 2/11 thì chưa thể suy ra MFA đã thực thi **toàn bộ tháng 10**. Muốn kết luận về cả kỳ, cần nguồn lịch sử, mẫu giao dịch hoặc cơ chế kiểm tra bổ sung phù hợp.

### 7.3. Dữ liệu có nhiều loại thời gian

Một record nên phân biệt:

- **Event time:** thời điểm sự kiện xảy ra.
- **Collection/extraction time:** thời điểm hệ thống trích xuất bản sao.
- **Assessment time:** thời điểm reviewer đánh giá.
- **Validity/coverage period:** khoảng thời gian mà bằng chứng được dùng để hỗ trợ claim.
- **Control/version time:** phiên bản config/build nào đang được kiểm chứng.

Ví dụ export log lúc 10:00 ngày 2/11 có thể chứa sự kiện từ tháng 10; thời điểm trích xuất không đồng nghĩa tất cả sự kiện thuộc ngày 2/11. Múi giờ và đồng bộ đồng hồ quan trọng khi đối chiếu incident, CI/CD và IAM change.

## 8. Thiết lập evidence catalog và ma trận truy vết

### 8.1. Evidence catalog là gì?

**Evidence catalog** là danh mục cho biết mỗi control cần loại bằng chứng nào, ai sản xuất, hệ thống nguồn nào, cách đánh giá, chu kỳ thu thập và nơi bảo quản. Nó giúp việc kiểm tra có thể lặp lại và tránh mỗi cuộc audit đều bắt đầu bằng yêu cầu file thủ công.

| Control ID | Claim cần chứng minh | Evidence bắt buộc minh họa | Owner | Tần suất/trigger |
|---|---|---|---|---|
| IAM-01 | Quyền admin được cấp và thu hồi đúng chính sách | Population export, approval/revoke records, access review, negative test | IAM/Platform | Theo kỳ và khi thay đổi lớn |
| SDLC-01 | Bản phát hành production qua kiểm tra bắt buộc | Build attestation, pipeline logs, approvals, deploy mapping | Engineering/DevOps | Mỗi release thuộc phạm vi |
| NET-01 | Endpoint admin không công khai ngoài phạm vi cho phép | Network policy runtime, discovery, negative access test | Platform | Khi thay policy và theo lịch rủi ro |
| APP-01 | Người dùng không truy cập dữ liệu ngoài quyền | Authorization tests, API inventory, deploy proof, relevant logs | Backend/QA | Mỗi thay đổi bảo mật hoặc release liên quan |
| LOG-01 | Sự kiện quan trọng được thu thập và phát hiện | Log health, synthetic event, rule result, routing ticket | SecOps | Theo kỳ và khi thay telemetry |
| DR-01 | Dữ liệu trọng yếu khôi phục được theo mục tiêu | Backup coverage, restore test, integrity check, RPO/RTO | Operations/DBA | Theo mức trọng yếu, thay đổi dữ liệu |
| VND-01 | Nhà cung cấp trọng yếu đáp ứng requirement đã chọn | Scope report, shared responsibility, gap/action record | Vendor owner/GRC | Onboarding, review và thay đổi vendor |

**Tần suất trên là mô tả nguyên tắc**, không phải yêu cầu mọi tổ chức phải thu thập theo cùng kỳ. Chuẩn phải ghi tần suất cụ thể theo rủi ro khi đưa vào vận hành.

### 8.2. Phân biệt artifact và evidence record

Một artifact là **dữ liệu gốc hoặc bản sao**: file JSON IAM, report JUnit, ticket, audit log. Evidence record là **ngữ cảnh** gắn artifact với claim, nguồn, scope, thời gian, phương pháp và đánh giá.

Nhiều artifact có thể tạo một record cho cùng claim. Một artifact có thể được tham chiếu từ nhiều record, nhưng không nên sao chép và chỉnh sửa tùy tiện khiến mất liên kết với nguồn gốc.

### 8.3. Mỗi requirement cần một phép đánh giá minh bạch

Ví dụ mapping:

| Requirement | Control | Test | Evidence | Cách kết luận |
|---|---|---|---|---|
| Admin chỉ đăng nhập qua đường được bảo vệ | MFA + SSO policy | Thử phương thức hợp lệ và đường bypass trong scope | Config, population, test, log | Đạt nếu đủ coverage và không có ngoại lệ ngoài policy |
| Không truy cập chéo lớp | Object-level authorization | Negative integration test qua API và đường export | Test report, job trace, deploy mapping | Không đạt nếu trả dữ liệu hoặc tạo file ngoài quyền |
| Mọi change nhạy cảm có approval | Change management | Review toàn bộ thay đổi hoặc lấy mẫu có kế hoạch | Change/deploy record và log | Kết luận trong phạm vi/kỳ mẫu hợp lệ, ghi ngoại lệ |
| Khôi phục dữ liệu đạt mục tiêu | Backup + restore runbook | Restore drill, kiểm tra integrity và thời gian | Restore report, dữ liệu đối chiếu | Đạt theo đúng kịch bản đã test và ngưỡng phê duyệt |

Không suy ra “control đạt” từ việc **artifact tồn tại**. Cần có **expected result**, **actual observation**, phương pháp và một người đánh giá chịu trách nhiệm.

## 9. Quy trình thu thập và bảo quản bằng chứng

### 9.1. End-to-end evidence workflow

~~~mermaid
flowchart LR
    A["Claim, control và tiêu chí"] --> B["Chọn population, nguồn và phương pháp"]
    B --> C["Thu thập/kiểm thử"]
    C --> D["Gắn metadata và bảo vệ evidence"]
    D --> E["Quality checks"]
    E --> F["Reviewer đánh giá"]
    F --> G{"Đạt, không đạt hay thiếu?"}
    G -->|"Đạt"| H["Record kết luận và báo cáo giới hạn"]
    G -->|"Không đạt"| I["Finding, remediation, retest"]
    G -->|"Thiếu"| J["Evidence request / thu hẹp claim"]
    I --> C
    J --> B
    H --> K["Retention và tái đánh giá khi thay đổi"]
~~~

**Bước 1 — Lập kế hoạch:** xác định requirement, risk tier, claim, scope, kỳ, loại evidence, người tạo/đánh giá và tiêu chí dừng.

**Bước 2 — Thu thập từ nguồn đáng tin:** ưu tiên API/record chính thức và cơ chế đọc với quyền tối thiểu; mô tả công cụ, query và phiên bản.

**Bước 3 — Kiểm tra kỹ thuật ban đầu:** đảm bảo file không rỗng nếu phải có dữ liệu, định dạng hợp lệ, scope/timestamp phù hợp, không bị lọc ngoài ý muốn, không lẫn nhiều environment.

**Bước 4 — Gắn metadata và bảo vệ:** ID, owner, nguồn, ngày, version, classification, link chứng cứ, quyền truy cập và cơ chế chống thay đổi.

**Bước 5 — Quality review:** đối chiếu nguồn, completeness, exceptions, phương pháp lấy mẫu, khả năng lặp lại và những điều chưa biết.

**Bước 6 — Đánh giá claim:** dựa trên tiêu chí, không dựa chỉ trên lời mô tả “OK” trong ticket.

**Bước 7 — Xử lý finding/gap:** nếu fail hoặc thiếu, phân công owner, kế hoạch, retest và ngày review. Phân biệt control thực sự fail với evidence không thể kết luận.

**Bước 8 — Lưu trữ có kiểm soát và đánh giá lại:** giữ trong thời hạn cần thiết và xóa theo chính sách; đánh giá lại khi control, tài sản hoặc nghĩa vụ thay đổi.

### 9.2. Chuẩn đặt tên và tổ chức dữ liệu

Một quy ước tên file có thể chứa mã control, môi trường, loại artifact và thời điểm, ví dụ:

~~~text
EVD-IAM-01_prod_privileged-population_2026-11-02.json
EVD-IAM-01_prod_mfa-negative-test_build-1428.txt
EVD-SDLC-01_prod_deploy-approval_release-1428.json
EVD-DR-01_prod_restore-drill_scenario-A_2026-11-03.pdf
~~~

Tên file chỉ hỗ trợ tìm kiếm; **không thay thế metadata** về nguồn và integrity. Cần tránh đưa email thật, ID nhạy cảm hoặc token vào tên file. Trong một kho evidence trưởng thành, có thể dùng ID nội bộ và liên kết tới object/version để giảm trùng lặp.

### 9.3. Phân quyền và bảo mật chính bằng chứng

Evidence có thể chứa token, PII, sơ đồ mạng, tài khoản admin, địa chỉ endpoint, log điều tra, cấu hình bí mật. Chuẩn phải:

- Phân loại evidence và hạn chế người đọc theo mục đích.
- Không lưu secret/token đầy đủ nếu chỉ cần xác nhận chúng được quản lý.
- Che hoặc pseudonymize dữ liệu trong bản dùng để chia sẻ, giữ đường đối chiếu nguồn khi được phép.
- Tách kho lưu evidence khỏi nơi công khai hoặc dùng chung rộng rãi.
- Kiểm soát quyền sửa/xóa; lưu lịch sử truy cập và review quyền.
- Quy định cách gửi cho auditor/vendor qua kênh thích hợp và giới hạn số bản sao.
- Xử lý retention, legal hold nếu có và tiêu hủy theo nghĩa vụ.

**Không đánh đổi bảo mật để tạo assurance.** Một bài test xuất toàn bộ hồ sơ học viên thật ra kho chia sẻ của người đánh giá là hành động có thể tạo rủi ro mới; hãy chọn bằng chứng tối thiểu, dữ liệu kiểm thử, tổng hợp hoặc mẫu được bảo vệ.

## 10. Tính toàn vẹn, chain of custody và khả năng xác minh

### 10.1. Kiểm tra evidence không bị thay đổi

Các kỹ thuật có thể sử dụng tùy rủi ro:

- **Versioned repository/object storage:** giữ lịch sử, xác định ai thay và trạng thái trước/sau.
- **Access control và audit trail:** hạn chế sửa và ghi nhận sự kiện quan trọng.
- **Cryptographic digest:** so sánh bản lưu/truyền với digest được lấy và bảo vệ từ trước.
- **Digital signature:** xác nhận khóa ký và dữ liệu ký theo cơ chế quản trị tin cậy.
- **Trusted timestamps:** hỗ trợ chứng minh mốc thời gian của record trong điều kiện xác định.
- **Immutable/WORM retention khi phù hợp:** hạn chế xóa/sửa trong thời kỳ bắt buộc, đi kèm quản lý legal hold nếu có.

Không phải mọi screenshot đều cần chữ ký số, nhưng evidence liên quan finding nghiêm trọng, truy cập đặc quyền hoặc điều tra sự cố có thể cần mức bảo quản cao hơn.

### 10.2. Ví dụ mô tả quy trình kiểm tra digest

Một record có thể ghi:

~~~yaml
artifact_id: EVD-LOG-INCIDENT-017
source_system: "Production audit logging"
collection_time: "2026-11-28T09:30:00+07:00"
original_reference: "restricted-log-export-reference"
digest_algorithm: "SHA-256"
digest_value: "Giá trị thật được hệ thống thu thập tính và lưu"
digest_record_storage: "Kho metadata được bảo vệ"
access_classification: "Restricted"
custody_events:
  - role: "Incident responder"
    action: "Collected and registered artifact"
  - role: "Assurance reviewer"
    action: "Verified artifact and reviewed scope"
~~~

Giá trị digest trong ví dụ là **placeholder**, không phải SHA-256 hợp lệ của artifact nào. Trong quy trình thật, phải tính từ bytes thực, giữ digest theo đường đáng tin và kiểm tra lại khi truy xuất. Không được ghi chuỗi tùy ý rồi tuyên bố integrity đã được xác minh.

### 10.3. Chain of custody khác version history

**Chain of custody** ghi lại quá trình tiếp nhận, lưu giữ, chuyển giao, truy cập và xử lý chứng cứ: ai có quyền kiểm soát, khi nào, đã làm gì và bằng cơ chế nào. Version history là một phần có ích nhưng **không luôn đủ** cho nhu cầu điều tra pháp chứng hoặc thủ tục pháp lý.

Với evidence cho incident, cần quy trình riêng về bảo quản bản gốc, ghi nhận thao tác điều tra, tránh tác động không cần thiết, quyền truy cập và yêu cầu pháp lý phù hợp. Không nên cho rằng chỉ cần ghi một digest là mọi điều kiện pháp chứng đã được đáp ứng.

## 11. Freshness: evidence còn hiệu lực trong bao lâu?

### 11.1. Phân loại theo độ biến động và mục tiêu

| Loại control | Độ biến động điển hình | Evidence nên chú ý |
|---|---|---|
| Chính sách/tiêu chuẩn | Có thể thay theo chu kỳ quản trị | Phiên bản phê duyệt và dấu vết review |
| IAM/privileged access | Thay khi nhân sự, service, quyền và session đổi | Population/historical change, review, negative test |
| Cấu hình cloud/network | Có thể thay theo deploy hoặc vận hành | IaC diff, runtime export, drift/change records |
| Secure CI/CD | Thay mỗi build/release và pipeline config | Build/test/approval result gắn đúng artifact |
| Application authorization | Thay theo phiên bản và business rule | Test theo build, code/config mapping, deployment evidence |
| Vulnerability management | Thay khi có lỗ hổng mới hoặc asset thay phiên bản | Inventory, scan timestamp, triage, retest |
| Logging và alert | Thay theo agent, schema, rule và routing | Health monitoring, synthetic tests, lịch sử xử lý |
| Backup/recovery | Thay theo dữ liệu, kiến trúc, khóa và thời gian mục tiêu | Restore tests, coverage, integrity, RPO/RTO |
| Vendor assurance | Thay theo dịch vụ, report, subprocessor và hợp đồng | Scope report, delta review, incident/change notice |

Chuẩn phải quy định **cửa sổ chấp nhận** theo rủi ro và kỳ của claim, ví dụ một evidence cấu hình dùng cho một ngày cụ thể, hay một tập record được dùng để đánh giá hoạt động trong một quý. “Gần đây” là một đánh giá có ngữ cảnh, không có nghĩa mọi control đều cần chụp lại hàng ngày.

### 11.2. Sự kiện khiến evidence cũ không còn đủ

- Thêm endpoint, IAM role, nhóm admin hoặc môi trường production.
- Thay identity provider, network gateway, storage, pipeline hoặc policy.
- Có sự cố hoặc finding chỉ ra control không hoạt động như giả định.
- Nhà cung cấp thay phạm vi dịch vụ, bên xử lý phụ hoặc báo cáo audit.
- Phép thử mới cho thấy một đường bypass chưa được cover.
- Log pipeline mất dữ liệu hoặc metric definition thay đổi.
- Hết hạn ngoại lệ, thay risk appetite hoặc nghĩa vụ compliance.

Khi trigger xảy ra, không nhất thiết bỏ toàn bộ evidence cũ: cần **xác định claim và control nào bị ảnh hưởng**, bổ sung assessment cho phần thay đổi và cập nhật kết luận.

## 12. Lấy mẫu evidence và giới hạn kết luận

### 12.1. Vì sao lấy mẫu cần phương pháp?

Với hàng nghìn change tickets hoặc tài khoản, kiểm tra mọi record thủ công có thể tốn kém. Có thể dùng automation cho population lớn hoặc lấy mẫu có kế hoạch. Tuy nhiên, **mẫu phải phù hợp mục tiêu assurance**.

Ví dụ tổ chức có 400 thay đổi production trong kỳ, gồm 25 thay đổi khẩn cấp, 75 thay đổi liên quan bảo mật và 300 thay đổi thông thường (giả định các nhóm không chồng nhau trong ví dụ). Nếu chỉ lấy 10 thay đổi bình thường do team tự chọn, kết quả không đại diện cho thay đổi khẩn cấp hoặc đường bypass.

Một thiết kế mẫu mang tính minh họa:

1. Xác định **population** từ nguồn chính thức, đối chiếu log triển khai để tìm thay đổi ngoài ticket.
2. Đánh giá **mức rủi ro và nhóm trường hợp**: emergency, quyền đặc biệt, network, database, thông thường.
3. Quy định chiến lược chọn mẫu: toàn bộ nhóm rủi ro cao nếu phù hợp, hoặc mẫu phân tầng/được chọn ngẫu nhiên theo phương pháp có căn cứ.
4. Lưu tiêu chí, thời kỳ, số record, nguồn và các trường hợp không lấy được.
5. Kiểm tra expected/actual, ghi deviations và mở rộng đánh giá nếu phát hiện sai lệch.
6. Chỉ kết luận trong phạm vi và **mức suy rộng mà phương pháp hỗ trợ**.

### 12.2. Sampling theo rủi ro và sampling thống kê

| Loại | Ưu điểm | Hạn chế |
|---|---|---|
| **Judgmental/risk-based sampling** | Tập trung ngoại lệ, tài sản trọng yếu và đường có khả năng fail | Không tự tạo cơ sở suy rộng tỷ lệ sai lệch thống kê tới toàn population |
| **Random/statistical sampling** | Có thể hỗ trợ một số suy luận về population nếu thiết kế và giả định thống kê phù hợp | Cần xác định population, phương pháp, mức tin cậy, cách xử lý sai lệch; có thể bỏ qua tình huống hiếm nhưng rất nghiêm trọng |
| **100% automated inspection** | Hữu ích cho rule/config và record có thể kiểm tra tự động | Chỉ kiểm tra điều mà script/rule phát hiện; tool có thể sai hoặc không có độ phủ |
| **Hybrid** | Kết hợp bao phủ tự động với test sâu tình huống trọng yếu | Cần quản trị nhiều nguồn và bảo đảm kết quả nhất quán |

Không có tỷ lệ lấy mẫu “10%” hoặc số lượng “25 record” nào tự động đúng cho mọi chương trình. Audit bên ngoài có thể có phương pháp sampling riêng. Chuẩn nội bộ nên nêu khi nào chấp nhận sampling, ai phê duyệt, điều kiện mở rộng khi fail và giới hạn kết luận.

### 12.3. Xử lý ngoại lệ trong mẫu

Nếu 2 trong 20 ticket được chọn thiếu phê duyệt, không nên tự kết luận “90% control hiệu quả” rồi đánh dấu đạt nếu tiêu chí yêu cầu mọi change nhạy cảm phải được phê duyệt. Cần:

- Kiểm tra ticket thiếu có thực sự là sai lệch, thông tin bị ghi ở nguồn khác hay ngoại lệ hợp lệ.
- Đánh giá mức độ nghiêm trọng, đường bypass và root cause.
- Xác định có cần mở rộng sample hoặc đánh giá toàn population liên quan.
- Ghi finding/risk và yêu cầu remediation/retest.
- Báo cáo đúng tiêu chí kiểm soát, không che sai lệch sau một điểm trung bình.

## 13. Evidence cho kiểm thử bảo mật và CI/CD

### 13.1. Bằng chứng một phép thử chất lượng

Một test report hỗ trợ assurance nên chứa:

- **Test ID** và requirement/control/abuse case được kiểm chứng.
- **Mục tiêu và precondition**: người dùng, quyền, đối tượng, dữ liệu kiểm thử.
- **Environment và build**: commit, artifact version/digest, config liên quan.
- **Method**: công cụ, script/test version, tham số và trường hợp dữ liệu.
- **Expected result** so với **actual result**, không chỉ pass/fail.
- **Side effects**: DB, queue, file, external API, log, trạng thái sau test.
- **Time và performer**, dữ liệu nguồn và link log hoặc report.
- **Exceptions/limitations**: trường hợp chưa bao phủ, lỗi hạ tầng, test bị skip.
- **Review** và kết luận theo tiêu chí.

### 13.2. Ví dụ: test chống truy cập chéo lớp

**Requirement:** giảng viên của lớp 42 không được xuất dữ liệu của lớp 43 nếu không có quyền tương ứng.

**Test:** sử dụng actor A được cấp quyền lớp 42, gọi đường xuất lớp 43 trong môi trường kiểm soát. Expected: bị từ chối, không có export job/file chứa dữ liệu lớp 43, có audit event thích hợp.

**Evidence:** kết quả integration test với role/class fixture, response và kiểm tra side effects, job trace, quyền runtime, build/deploy mapping và thời điểm thực thi.

Lưu ý: một HTTP 403 **chưa đủ** nếu worker vẫn chạy job bất đồng bộ hoặc file được lưu ở đường tải không kiểm soát. Với claim cho production, test ở staging phải có bằng chứng về **tính tương đương có liên quan** và rằng bản chạy thật là bản đã kiểm tra; nếu không, ghi giới hạn.

### 13.3. CI/CD evidence có thể tự động hóa

Một pipeline có thể xuất:

~~~yaml
evidence_id: EVD-RELEASE-1428
service: "learning-api"
release: "1428"
commit_reference: "commit-identifier-from-source-control"
artifact_reference: "approved-artifact-id"
environment: "production"
tests:
  - requirement: "Authorization regression"
    suite: "authz-negative-tests"
    result: "pass"
  - requirement: "Dependency policy"
    suite: "dependency-check"
    result: "pass-with-reviewed-exceptions"
change_approval: "approved-change-record-id"
deployment_record: "runtime-deployment-reference"
observed_at: "2026-11-28T08:45:00+07:00"
limitations:
  - "Không bao gồm quyền ở hệ thống báo cáo bên thứ ba"
assessment: "Cần reviewer xác minh nguồn và ngoại lệ"
~~~

Mẫu **không phải log deploy thật**. Trong hệ thống thực, cần xác minh pipeline không thể bị bypass ngoài quy trình, test không bị skip, artifact mang đúng version và production thật sự chạy artifact đó. Một trường “pass” do script tự gán không có provenance sẽ có giá trị assurance thấp.

### 13.4. Kiểm soát evidence automation bị sai

Automation giảm thao tác nhưng cũng có thể tạo “bằng chứng đẹp” sai sự thật khi:

- API token thu thập hết hạn khiến export rỗng nhưng job vẫn trả exit code 0.
- Query filter chỉ lấy resource có tag, bỏ sót tài sản chưa được tag.
- Tool chạy ở staging thay vì production.
- Dashboard tính tỷ lệ theo total sai do asset inventory thiếu.
- Pipeline test bị skip mà báo cáo vẫn xem là xanh.
- Timestamp hoặc timezone sai khiến các record ngoài kỳ lọt vào.
- Kết quả từ nhiều tenant bị gộp, che sai lệch của một tenant trọng yếu.

Nên kiểm thử **chính đường thu thập bằng chứng** bằng kiểm tra schema, số lượng record, kiểm tra dữ liệu rỗng, so population với nguồn khác, trạng thái công cụ và review định kỳ.

## 14. Evidence cho IAM, cloud và vận hành

### 14.1. Identity và privileged access

Để chứng minh control MFA và quyền admin, cần ít nhất ba lớp:

1. **Xác định population:** tất cả danh tính và cơ chế truy cập admin thuộc scope, gồm trường hợp tài khoản đặc biệt nếu áp dụng.
2. **Đối chiếu control runtime:** IdP/MFA/conditional access, role và chính sách phân quyền thực tế, đường bypass hoặc emergency access.
3. **Kiểm tra hoạt động trong kỳ:** cấp/quyền/thu hồi, access review, xác thực thử, log sự kiện và ngoại lệ.

Kết luận “100% accounts have MFA” phải ghi rõ **mẫu số**, nơi lấy inventory, nhóm ngoại lệ, phương pháp áp dụng MFA và các đường đăng nhập đã kiểm tra.

### 14.2. Cấu hình cloud/network

Một snapshot network policy có thể hỗ trợ claim trạng thái tại thời điểm trích xuất. Nếu cần chứng minh “mọi thay đổi mạng production được review trong kỳ”, cần thêm **change history, approval, drift detection và những đường thay đổi ngoài IaC**.

Ví dụ không chỉ đọc IaC repository mà bỏ qua manual change được thực hiện trong console. Chuẩn evidence nên yêu cầu đối chiếu **desired state** với **observed runtime state**.

### 14.3. Logging và phát hiện

Để đánh giá detection, có thể kết hợp:

- Log source inventory và trạng thái ingest.
- Chính sách retention và quyền đọc/sửa/xóa.
- Synthetic event theo phạm vi an toàn để xác nhận pipeline.
- Alert rule, routing, ticket và thời gian xử lý.
- Kiểm tra những sự kiện có lẽ phải xuất hiện nhưng không có.
- Change history khi agent hoặc schema log thay đổi.

Chỉ đếm số alert không đủ: không có alert có thể nghĩa là ít sự kiện, cũng có thể là cảm biến đã hỏng. Evidence chuẩn phải đánh giá **sức khỏe của hệ thống chứng cứ**.

### 14.4. Backup và recovery

Một claim đầy đủ nên xác định **dữ liệu gì**, **điểm khôi phục**, **thời gian mục tiêu**, **kịch bản** và **mức toàn vẹn mong muốn**. Evidence:

- Phạm vi backup và cấu hình bảo vệ bản sao.
- Job logs và cảnh báo khi thất bại.
- Kết quả restore test trên dữ liệu tương đương.
- Thời gian khôi phục, dữ liệu có thể phục hồi và phép đối chiếu.
- Khả năng tiếp cận khóa giải mã, quyền và phụ thuộc cần thiết.
- Những trường hợp chưa test như sự cố multi-region hoặc mất identity provider.

**RPO** là mục tiêu về khoảng mất dữ liệu tối đa chấp nhận; **RTO** là mục tiêu thời gian phục hồi chức năng/dịch vụ. Cần ghi rõ giá trị do tổ chức phê duyệt, không lấy mức nhà cung cấp quảng cáo thay thế mục tiêu của hệ thống cụ thể.

## 15. Evidence của audit, tiêu chuẩn và nhà cung cấp

### 15.1. Đọc đúng phạm vi báo cáo

Báo cáo audit, chứng nhận hoặc kết quả đánh giá bên thứ ba có thể giảm công sức kiểm tra, nhưng phải biết:

- Tổ chức, sản phẩm, dịch vụ và địa điểm nào được bao phủ.
- Control hoặc tiêu chí nào được đánh giá và có bao gồm **đường tích hợp của mình** không.
- Ngày hoặc kỳ đánh giá, loại kết luận, ngoại lệ và những hệ thống bị loại trừ.
- Trách nhiệm của người mua còn phải tự thực hiện.
- Subprocessor/subservice nào nằm ngoài phạm vi.
- Có việc khắc phục/finding mở ảnh hưởng tới claim hay không.

Ví dụ, chứng nhận ISO/IEC 27001 hỗ trợ một nhận định về hệ thống quản lý an toàn thông tin **trong scope chứng nhận**, không tự chứng minh mọi endpoint ứng dụng đạt tất cả security requirement. Báo cáo SOC 2 phải được đọc theo tiêu chí, loại báo cáo, phạm vi, kỳ và các điều kiện áp dụng. Không coi bất kỳ nhãn “compliant” nào là chứng minh tuyệt đối rằng sản phẩm không có lỗ hổng.

### 15.2. Phần việc của tổ chức mua dịch vụ

Một SaaS vendor có thể cung cấp hạ tầng và kiểm soát bảo mật mạnh, nhưng chính tổ chức sử dụng vẫn có thể chịu trách nhiệm về:

- Cấu hình tenant, bật/tắt cơ chế xác thực phù hợp.
- Cấp quyền user, role, đặc quyền, service accounts.
- OAuth scopes, API keys và luồng dữ liệu chuyển vào dịch vụ.
- Phân loại dữ liệu, giới hạn mục đích và retention theo nghĩa vụ.
- Giám sát hoạt động của tài khoản và tích hợp.
- Kế hoạch offboarding, thu hồi quyền và dữ liệu.

Chuẩn bằng chứng nên có **shared responsibility mapping** để tránh hồ sơ vendor tốt che đi control phía khách hàng đang fail.

## 16. Kết luận đánh giá: đạt, không đạt, thiếu hay không áp dụng?

### 16.1. Quy tắc kết luận phải được viết trước

Một cơ chế trạng thái nội bộ có thể dùng:

| Trạng thái | Điều kiện | Hành động |
|---|---|---|
| **Đạt (Pass/Supported)** | Evidence đủ chất lượng và control đáp ứng tiêu chí trong scope/kỳ đã xác định | Ghi claim, phương pháp, giới hạn; duy trì giám sát |
| **Không đạt (Fail/Unsupported)** | Có sai lệch được kiểm chứng so với tiêu chí | Tạo finding, phân tích tác động, khắc phục và retest |
| **Chưa đủ bằng chứng (Insufficient evidence)** | Không có cơ sở tin cậy để xác nhận đạt/không đạt toàn phần | Yêu cầu thu thập thêm, mở rộng test hoặc thu hẹp claim |
| **Không áp dụng (Not applicable)** | Yêu cầu không liên quan trong scope có lý do và người phê duyệt thích hợp | Ghi căn cứ; xem lại khi scope thay đổi |
| **Ngoại lệ hợp lệ (Exception)** | Sai khác với policy nội bộ được cấp có thẩm quyền cho phép có điều kiện | Theo dõi riêng; không tự đổi kết quả fail thành pass |

Các trạng thái là **quy ước minh họa**, không mặc nhiên đúng với quy tắc đánh giá của mọi chương trình audit hoặc chứng nhận.

### 16.2. Phân biệt evidence gap với control failure

Nếu không lấy được IAM export vì API token hết hạn, không thể suy ra **control IAM bị lỗi**, nhưng cũng không thể kết luận **control đạt**. Đó là evidence gap cần xử lý.

Nếu negative test xác nhận người dùng ngoài quyền vẫn tải được dữ liệu, đó là **control failure** trong phạm vi test, cần finding và đánh giá tác động.

Nếu test ở staging đạt nhưng chưa biết production chạy đúng bản, kết luận nên ghi **“đạt trong môi trường kiểm thử; chưa đủ bằng chứng cho production”**, thay vì nói “production an toàn”.

### 16.3. Kết luận phải nói rõ mức tin cậy

Một assessor có thể trình bày:

> **Claim:** Các đường xuất dữ liệu học viên production trong danh mục được kiểm soát quyền theo đối tượng.
>
> **Kết quả:** Các negative tests của release được kiểm tra đã từ chối truy cập ngoài quyền; chưa đủ bằng chứng về một batch export cũ nằm ngoài test suite.
>
> **Giới hạn:** Không đưa ra kết luận đối với batch export nói trên và thời kỳ trước khi logging được kích hoạt.
>
> **Hành động:** Giao owner xác minh batch flow, bổ sung test, cập nhật đánh giá trước khi chấp nhận claim toàn phạm vi.

Sự minh bạch về giới hạn là dấu hiệu của assurance đáng tin, không phải sự yếu kém của người đánh giá.

## 17. Những sai lầm thường gặp

**“Có file trong kho nghĩa là có bằng chứng đạt.”** Không. Artifact phải hỗ trợ một claim và đáp ứng tiêu chí về scope, nguồn, kỳ, tính toàn vẹn và nội dung.

**“Có chính sách nghĩa là control đã vận hành.”** Chính sách thể hiện yêu cầu, cần thêm triển khai và kiểm tra hiệu quả hoạt động.

**“Một screenshot đủ cho mọi kỳ audit.”** Screenshot thường là trạng thái tại một thời điểm, khó thể hiện toàn bộ lịch sử và ngoại lệ.

**“Báo cáo có chữ PASS thì chắc chắn đúng.”** Cần xem test có bị skip, tool có đúng scope, source có đáng tin và pass criteria có phù hợp không.

**“Không có alert chứng minh không bị tấn công.”** Có thể hệ thống thiếu log hoặc rule phát hiện thất bại; phải kiểm tra coverage và health.

**“Hash chứng minh dữ liệu ban đầu chính xác.”** Hash chỉ hỗ trợ kiểm tra integrity so với giá trị chuẩn đã tin cậy, không tự xác nhận tính đúng của nguồn hoặc nhận định.

**“Đã audit độc lập thì không cần xem scope.”** Kết luận độc lập có phạm vi, thời kỳ, tiêu chí và ngoại lệ, không bao phủ tự động mọi dịch vụ.

**“Sample pass nghĩa là 100% population pass.”** Cần phương pháp lấy mẫu và giới hạn suy rộng, có thể yêu cầu kiểm tra toàn bộ nhóm rủi ro trọng yếu.

**“Evidence thiếu nghĩa là hệ thống fail.”** Thiếu evidence và control fail là hai tình trạng khác; cả hai không được đánh dấu đạt.

**“Không nên ghi limitations vì làm báo cáo xấu.”** Kết luận không nêu giới hạn dễ dẫn đến quyết định rủi ro sai.

**“Một lần thu thập đủ dùng mãi.”** Sau thay đổi quyền, code, cloud, dữ liệu hoặc vendor, bằng chứng có thể hết khả năng hỗ trợ claim cũ.

**“Càng lưu nhiều bằng chứng càng bảo mật.”** Thu thập quá mức có thể lộ secret/PII và tăng gánh nặng bảo quản. Chọn dữ liệu **đủ và phù hợp**, bảo vệ theo phân loại và retention.

## 18. Tình huống xuyên suốt: chứng minh MFA cho quản trị production

### 18.1. Bối cảnh

Một nền tảng học trực tuyến chạy ứng dụng Java trên cloud. CISO yêu cầu báo cáo: “Toàn bộ tài khoản con người có quyền admin production được bảo vệ bằng MFA và có owner hợp lệ trong quý vừa qua”. Nhóm Platform trình một screenshot giao diện identity provider hiển thị **MFA enabled**.

Vì sao screenshot chưa đủ?

- Nó có thể chỉ phản ánh một identity provider, không bao gồm cloud IAM và tài khoản local.
- Chưa biết tài khoản nào có quyền admin thật, kể cả role nhận tạm.
- Chưa kiểm tra đường đăng nhập không qua IdP hoặc emergency access.
- Không chứng minh MFA đã áp dụng trong **cả quý**, có thể mới bật hôm qua.
- Không xác nhận các quyền đã được phê duyệt hoặc thu hồi đúng lúc.
- Có thể chưa kiểm tra log/telemetry khi sử dụng quyền đặc biệt.

### 18.2. Xây evidence plan

| Mã | Phần claim | Test/đối chiếu | Evidence |
|---|---|---|---|
| E1 | Population đầy đủ | Đối chiếu IdP, cloud IAM, ứng dụng admin và danh sách nhân sự liên quan | Inventory hợp nhất, query và mapping |
| E2 | Mọi account có owner và lý do | Đối chiếu phê duyệt, vai trò và quyền hiện tại | Access review, ticket, owner mapping |
| E3 | MFA bảo vệ đường đăng nhập thuộc scope | Kiểm tra config và thử các phương thức đăng nhập có kiểm soát | MFA policy export, negative tests |
| E4 | Không có đường bypass chưa quản lý | Phân tích break-glass, local admin, API và service identity theo scope phù hợp | Exception register, test, monitoring |
| E5 | Hoạt động đúng trong kỳ | Kiểm tra lịch sử cấp/thu hồi, thay chính sách và audit log | IAM changes, policy history, samples |
| E6 | Giải quyết sai lệch | Truy vết finding, owner, sửa và retest | Ticket, change, new test result |

**Control owner:** IAM/Platform. **Evidence producer:** những hệ thống và nhóm sở hữu IAM, log và thay đổi. **Reviewer:** nhóm security assurance hoặc người đánh giá được giao. **Risk owner:** người có thẩm quyền đối với rủi ro truy cập admin của dịch vụ.

### 18.3. Ba kết quả có thể xuất hiện

**Trường hợp A:** Toàn bộ population và đường thuộc phạm vi đã được kiểm tra, evidence đủ và không có trường hợp không đáp ứng. Có thể kết luận đạt theo scope/kỳ, nêu giả định và chu kỳ review.

**Trường hợp B:** Có hai account admin có thể đăng nhập mà không qua điều kiện xác thực yêu cầu. Đây là **control failure** trong phạm vi, cần đánh giá rủi ro, giới hạn/thu hồi và retest. Không dùng kết quả đa số account đạt để che lỗi trọng yếu.

**Trường hợp C:** Không xác định được số local admin ở một môi trường cũ. Chưa thể kết luận về toàn scope. Cần bổ sung inventory/test, ghi **insufficient evidence** và có thể tăng ưu tiên kiểm tra vì thiếu khả năng quan sát.

### 18.4. Mẫu kết luận gửi CISO

~~~text
Claim ID: CLAIM-IAM-ADMIN-01
Scope: Human privileged access to production systems in approved inventory
Period: Internal assessment quarter
Evidence: Identity exports, access review, login tests, audit history
Method: Population reconciliation + targeted negative tests + change review
Result: [Pass / Fail / Insufficient evidence — assessed after review]
Known exclusions: Workload identities (separate assessment)
Limitations: Any legacy/local paths not yet verified must be listed
Findings: IDs, owner, impact, target date, retest result
Risk decision: Made by authorized risk owner, not inferred from test count
Next review: According to changes and risk-based evidence standard
~~~

Bản mẫu để trống kết quả thay vì tự ghi “Pass”. Chỉ khi evidence đã có và được kiểm tra mới điền kết luận cụ thể.

## 19. Tình huống mở rộng: bằng chứng cho khắc phục finding

Một bài penetration test xác nhận backend cho phép giảng viên đọc hồ sơ lớp khác. Team backend tạo pull request sửa logic phân quyền và đánh dấu ticket “Done”.

Để kết luận finding được khắc phục, chuẩn bằng chứng nên yêu cầu:

1. **Finding gốc:** ID, endpoint, actor, dữ liệu, điều kiện gây lỗi, expected/actual, impact.
2. **Root cause và fix scope:** thiếu object-level authorization, các tuyến tương tự đã kiểm tra.
3. **Change evidence:** code review, commit, build, artifact/deployment record.
4. **Negative retest:** actor lớp A yêu cầu dữ liệu lớp B bị từ chối; kiểm tra side effects ở queue, storage và cache.
5. **Positive test:** actor hợp lệ vẫn truy cập được đúng dữ liệu, không phá chức năng nghiệp vụ.
6. **Runtime verification:** bằng chứng bản build đúng đã chạy ở môi trường được kết luận.
7. **Monitoring:** log và cảnh báo, nếu liên quan, có hoạt động trong scope.
8. **Reviewer và ngày kiểm tra:** người kiểm chứng, điều kiện, evidence links và giới hạn.

Nếu fix chỉ đạt ở môi trường thử mà chưa deploy, finding có thể đang ở trạng thái **awaiting production verification** theo workflow nội bộ. Nếu một đường batch khác chưa kiểm tra, kết luận cần nêu nó như open question hoặc finding riêng.

~~~mermaid
flowchart LR
    A["Finding có bằng chứng lỗi"] --> B["Fix / commit"]
    B --> C["Build + security regression tests"]
    C --> D["Deploy vào môi trường mục tiêu"]
    D --> E["Retest và kiểm tra side effects"]
    E --> F{"Đạt theo tiêu chí?"}
    F -->|"Có"| G["Reviewer kết luận, cập nhật risk"]
    F -->|"Không / thiếu evidence"| H["Mở lại hoặc bổ sung kiểm tra"]
    H --> B
~~~

Một risk acceptance được phê duyệt có thể giúp quản trị rủi ro trong khi chờ remediation, nhưng **không tự biến negative test thất bại thành kết quả đạt** hoặc miễn tiêu chí audit bắt buộc.

## 20. Quản trị chương trình chuẩn bằng chứng

### 20.1. RACI minh họa

| Hoạt động | CISO/GRC | Control owner | Evidence producer | Assessor/reviewer | Risk owner |
|---|---|---|---|---|---|
| Thiết lập evidence standard | A/R | C | C | C | I |
| Xác định tiêu chí cho control cụ thể | A hoặc C theo ủy quyền | R | C | C | I |
| Thu thập từ nguồn và gắn metadata | I | A | R | C | I |
| Review chất lượng evidence | C | C | C | A/R | I |
| Xử lý control failure | C | A/R | R hỗ trợ | C/retest | I |
| Đánh giá residual risk/đề xuất xử lý | R tư vấn | C | C | C | A quyết định trong thẩm quyền |
| Audit độc lập | C/cung cấp hồ sơ | C | C | A/R theo chức năng audit | I |

R = thực hiện, A = chịu trách nhiệm cuối cùng, C = tham vấn, I = nhận thông tin. Bảng chỉ là **ví dụ**. Một tổ chức có thể đặt GRC ở tuyến hai, Internal Audit độc lập ở tuyến ba, và có nhiều control owner. Cần điều chỉnh để tránh người tự tạo evidence cũng tự ký kết luận độc lập mà không công bố xung đột.

### 20.2. Mức độ ưu tiên evidence

Không nên dành cùng công sức cho mọi control. Ưu tiên cao khi:

- Hệ thống chứa nhiều dữ liệu nhạy cảm hoặc có quyền quản trị.
- Có đường Internet-facing, kết nối bên thứ ba hoặc tenant boundary.
- Control có lịch sử thất bại, nhiều finding hoặc ngoại lệ.
- Không có nguồn quan sát đầy đủ; assessment phụ thuộc lời xác nhận.
- Có thay đổi code, IaC, IAM, key, log hoặc data flow.
- Có thời hạn audit/hợp đồng hoặc yêu cầu báo cáo cho cấp quản trị.
- Một control ảnh hưởng nhiều dịch vụ (identity provider, CI/CD, backup).

Evidence standard càng trưởng thành càng cần **tự động hóa phần lặp lại**, tập trung assessor vào kịch bản khó, bất định và rủi ro lớn thay vì sao chụp màn hình hàng loạt.

### 20.3. Các chỉ số chất lượng chương trình

| Metric | Đo điều gì | Cảnh báo khi diễn giải |
|---|---|---|
| % control có evidence record đủ metadata | Độ đầy đủ quản trị bằng chứng | Có metadata chưa chứng minh nội dung đúng |
| % control critical có evidence hợp lệ trong kỳ | Độ phủ đánh giá đối với control trọng yếu | Scope không đủ sẽ làm số liệu đẹp giả |
| % evidence bị từ chối vì sai nguồn/thời kỳ | Chất lượng pipeline thu thập | Ít lỗi có thể do không review đủ |
| Thời gian từ event đến evidence sẵn cho review | Khả năng kiểm tra gần thời gian thực | Nhanh không đảm bảo đúng |
| % remediation có retest được xác minh | Chất lượng đóng finding | “Done” không thay test |
| % control có nguồn automation được kiểm tra health | Độ tin cậy automated assurance | Có health check nhưng sai logic vẫn có thể lỗi |
| Số evidence gap trọng yếu quá hạn | Độ bất định chưa được xử lý | Thiếu evidence không được che bằng risk score thấp |
| % thay đổi quan trọng kích hoạt review evidence | Năng lực duy trì assurance liên tục | Thay đổi ngoài inventory có thể không được tính |
| Số sự cố truy cập trái phép kho evidence | Rủi ro từ chính hoạt động kiểm chứng | Không có sự cố báo cáo chưa chắc không có vấn đề |

Cần báo cáo metric cùng **định nghĩa mẫu số, nguồn, thời kỳ, phạm vi và hạn chế**, tránh kết luận “100% compliance” chỉ từ số tệp có trong kho.

## 21. Triển khai chuẩn bằng chứng theo từng giai đoạn

### Giai đoạn 1 — Xác định phạm vi và control trọng yếu

Chọn các control ảnh hưởng rủi ro cao: đặc quyền IAM, bảo vệ dữ liệu, secure deploy, network policy, logging, restore. Thu thập owner, risk scenario, criteria và những evidence hiện có.

### Giai đoạn 2 — Định nghĩa quality rules

Với từng loại evidence, thống nhất metadata bắt buộc, nguồn được phép, cách kiểm tra completeness, phương pháp lấy mẫu, yêu cầu integrity, thời gian chấp nhận, điều kiện pass/fail/insufficient và người review.

### Giai đoạn 3 — Thí điểm một hoặc hai claim

Ví dụ thử “MFA cho admin production” và “Authorization cho API export”. Thu thập evidence từ nguồn thật, kiểm tra những đường bị bỏ sót, đo công sức và cải tiến procedure.

### Giai đoạn 4 — Kết nối CI/CD, IAM, cloud và ticket

Tự động xuất artifact ID, phiên bản, test result, config hoặc log có liên kết; bảo vệ dữ liệu theo phân loại. Giữ cơ chế kiểm tra chất lượng pipeline, không chỉ nhận các status do tool trả.

### Giai đoạn 5 — Gắn với finding và risk decision

Khi test fail, thiếu dữ liệu hoặc drift, tạo record có owner, mức ảnh hưởng, deadline và retest. Reviewer cập nhật kết luận khi evidence mới đến, risk owner quyết định residual risk theo thẩm quyền.

### Giai đoạn 6 — Vận hành liên tục và cải tiến

Định kỳ đánh giá độ phủ, nguồn dữ liệu mới, scope changes, sự cố, ngoại lệ và chi phí của việc thu thập. Xóa những artifact không còn cần thiết theo retention thay vì giữ vĩnh viễn mọi dữ liệu nhạy cảm.

**Mục tiêu cuối không phải tạo một kho tài liệu khổng lồ**, mà là một quy trình đưa ra kết luận bảo mật **đúng, hữu ích, có bằng chứng và luôn có thể cập nhật**.

## 22. Bài tập thực hành

### Bài tập A — Đánh giá bốn bằng chứng

Nhóm Platform khẳng định: “Tất cả thay đổi production được review và phê duyệt”. Họ cung cấp:

1. Policy PDF ghi mọi thay đổi cần approval.
2. Screenshot pipeline có một nút approval.
3. Danh sách 20 pull request có reviewer.
4. Log deployment có 150 lần triển khai trong quý.

Hãy chỉ ra bằng chứng nào hỗ trợ **design**, **implementation**, **operating effectiveness**, và những khoảng trống còn lại. Đề xuất cách đối chiếu 150 deployment với PR/change records, xử lý emergency/manual deploy, xác định population và sampling.

**Gợi ý:** Có policy và screenshot chưa chứng minh mọi deployment trong quý được phê duyệt. Phải đối chiếu population từ nguồn triển khai thật với approval, theo quy tắc đã xác định và ghi ngoại lệ. 20 PR do team tự chọn có thể không đại diện.

### Bài tập B — Viết evidence contract cho authorization

Requirement: “Giảng viên không được xem hoặc xuất dữ liệu của lớp chưa được phân quyền”.

Hãy định nghĩa:

- Claim, scope, kỳ và security invariant.
- Control owner, evidence producer, reviewer.
- Các đường API, queue/worker và storage cần bao phủ.
- Test positive, negative, thu hồi quyền và side effects.
- Evidence metadata bắt buộc: build, actor, lớp, test version, timestamp, environment.
- Điều kiện pass, fail, insufficient evidence.
- Trigger xem xét lại khi thêm tính năng batch export.

**Gợi ý:** Một test response 403 không đủ nếu export worker vẫn tạo file; phải kiểm tra end-to-end và deployment mapping.

### Bài tập C — Kiểm tra integrity của evidence

Một reviewer nhận hai bản log incident có cùng tên file nhưng nội dung khác nhau. Bản đầu có digest lưu trong ticket, bản sau có người gửi qua chat và ghi “đây là bản đúng”.

Hãy nêu:

1. Cần xác minh nguồn gốc của mỗi bản như thế nào?
2. Digest có chứng minh bản nào là “đúng sự thật” không?
3. Những custody events và metadata nào cần bổ sung?
4. Có nên sửa trực tiếp bản gốc trước khi xác minh không?
5. Nếu log có dữ liệu học viên, cách chia sẻ cho assessor thế nào?

**Định hướng:** So với digest đáng tin đã ghi trước đó để kiểm tra thay đổi, rồi đối chiếu nguồn log gốc và lịch sử truy xuất. Digest không tự xác nhận nguồn, tính đầy đủ hay nội dung đúng. Bảo toàn bản gốc và thực hiện kiểm tra trên bản sao được quản lý phù hợp.

### Bài tập D — Chọn mẫu và giới hạn

Trong quý có 600 thay đổi, gồm 30 thay đổi khẩn cấp, 70 thay đổi IAM/network và 500 thay đổi thông thường (giả định ba nhóm tách biệt). Nhóm audit kiểm tra 12 thay đổi thông thường và không thấy sai lệch.

Hãy đánh giá claim “mọi thay đổi production đều được phê duyệt”. Đề xuất:

- Cách xác minh population 600 có đầy đủ hay không.
- Phương pháp chọn mẫu kết hợp nhóm high-risk và normal.
- Cách xử lý khi một emergency change thiếu approval.
- Điều kiện cần để suy rộng kết quả và báo cáo uncertainty.
- Evidence cần lưu để reviewer khác có thể tái kiểm tra.

**Gợi ý:** 12 trường hợp bình thường không chứng minh hai nhóm còn lại. Không tự suy ra tỷ lệ tuân thủ 100% khi chưa kiểm tra những đường thay đổi có rủi ro cao.

### Bài tập E — Báo cáo evidence gap

Một nhà cung cấp SaaS gửi chứng nhận an toàn thông tin cho phạm vi hosting, nhưng tính năng phân tích học tập mới chưa được bao phủ. Product muốn kết luận vendor “đạt mọi tiêu chí”.

Hãy viết kết luận gồm claim được chứng minh, phần không thuộc scope, bằng chứng cần bổ sung cho tính năng mới, shared responsibility phía khách hàng và quyết định risk owner cần xem xét. Tránh tự động đánh dấu fail toàn bộ hoặc pass toàn bộ khi mới chỉ có evidence thiếu phạm vi.

## 23. Checklist triển khai chuẩn bằng chứng

Một tổ chức có thể dùng checklist dưới đây để kiểm tra mức trưởng thành của chương trình; **tick đủ ô không đồng nghĩa mọi security control đã đạt**.

- [ ] Có evidence standard được phê duyệt, scope và phiên bản rõ.
- [ ] Có claim, control, requirement IDs và traceability map.
- [ ] Có tiêu chí pass, fail, insufficient evidence và not applicable.
- [ ] Định nghĩa evidence types phù hợp rủi ro và mức đánh giá design/implementation/operating.
- [ ] Có metadata tối thiểu về nguồn, scope, period, owner, method, build và results.
- [ ] Có chuẩn kiểm tra integrity/provenance và kho lưu trữ có kiểm soát.
- [ ] Có phân loại dữ liệu, quyền đọc/sửa/xóa, retention và xử lý bản sao.
- [ ] Có phương pháp xác nhận population và sampling phù hợp.
- [ ] Có cách kiểm tra tính đúng của script, API, dashboard và pipeline evidence.
- [ ] Có giới hạn freshness/validity dựa trên risk và trigger khi thay đổi.
- [ ] Có reviewer độc lập ở mức phù hợp, công bố giới hạn self-assessment.
- [ ] Có quy trình evidence request, gap, finding, remediation và retest.
- [ ] Có report nêu rõ kết quả, ngoại lệ, độ bất định và residual risk.
- [ ] Có áp dụng cho cloud, IAM, SDLC, log, backup, incident và vendor theo scope.
- [ ] Có cơ chế xử lý evidence điều tra/forensic theo yêu cầu riêng.
- [ ] Có metrics để cải tiến chất lượng, không chỉ đếm số tài liệu.
- [ ] Có đánh giá lại standard khi hệ thống, nghĩa vụ hoặc chương trình assurance thay đổi.

## 24. Ghi nhớ

- **Chuẩn bằng chứng xác định điều kiện để dữ liệu có giá trị chứng minh**, không chỉ định dạng file hay nơi lưu screenshot.
- Một evidence tốt phải **đúng claim, đúng phạm vi, đúng kỳ, có nguồn gốc, đáng tin, toàn vẹn, đủ bao phủ và có thể kiểm tra lại**.
- Phân biệt **thiết kế**, **triển khai**, **hiệu quả vận hành**: evidence ở lớp này không tự chứng minh lớp kia.
- **Thiếu bằng chứng**, **control không đạt** và **không áp dụng** là những trạng thái khác nhau; không tự đánh dấu đạt khi chưa biết.
- Hash, chữ ký, audit log, version và chain of custody hỗ trợ các yêu cầu bảo quản khác nhau; không kỹ thuật đơn lẻ nào tự chứng minh nội dung nguồn là đúng.
- Lấy mẫu cần có **population, phương pháp, phạm vi suy rộng và cách xử lý ngoại lệ**; không suy ra tuân thủ tuyệt đối từ vài mẫu đạt.
- Security assurance có thể truy vết bằng chuỗi **risk → requirement → control → test/evidence → assessment → finding/retest → residual risk**.
- Evidence phải được **cập nhật khi phát triển và vận hành thay đổi**, đồng thời bảo vệ chính dữ liệu chứng cứ khỏi lộ lọt hoặc chỉnh sửa trái phép.

