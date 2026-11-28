# Chấp nhận rủi ro

Trong chương **Quản lý rủi ro**, **chấp nhận rủi ro** (*risk acceptance*) là quyết định có ý thức và được cấp có thẩm quyền phê duyệt về việc **tiếp tục duy trì một hoạt động dù vẫn tồn tại rủi ro đã được xác định**. Quyết định này được đưa ra sau khi xem xét mục tiêu cần bảo vệ, mức rủi ro hiện tại, các biện pháp kiểm soát đang hoạt động, phương án xử lý khác, nghĩa vụ áp dụng và giới hạn chấp nhận của tổ chức.

Chấp nhận rủi ro không phải lời tuyên bố rằng hệ thống đã an toàn tuyệt đối, không phải bỏ qua lỗ hổng, và không tự miễn nghĩa vụ pháp luật, hợp đồng hoặc tiêu chí bắt buộc. Ví dụ, một nền tảng học trực tuyến có thể cân nhắc tạm duy trì một thành phần cũ trong thời gian nâng cấp, nếu đường tiếp cận đã được giới hạn và kiểm chứng, mức rủi ro còn lại phù hợp thẩm quyền, và có điều kiện, thời hạn, cơ chế đánh giá lại. Ngược lại, việc một endpoint công khai có thể làm lộ dữ liệu học viên nhưng chưa có biện pháp hạn chế không thể được coi là đã xử lý chỉ nhờ một chữ ký.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu không dừng ở việc ghi nhận ai chấp nhận rủi ro. Người học phải biết **chứng minh bằng bằng chứng** rằng mức rủi ro còn lại được mô tả đúng: từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục finding và giám sát liên tục trong phát triển, vận hành.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt risk acceptance với risk mitigation, avoidance, sharing/transfer, exception và việc đóng finding.
2. Xác định kịch bản, phạm vi, điều kiện và giới hạn có thể xem xét chấp nhận.
3. Phân biệt inherent risk, current/residual risk, target risk, risk appetite và risk tolerance.
4. Xây dựng hồ sơ chấp nhận rủi ro có risk owner, căn cứ, bằng chứng, phê duyệt, điều kiện, thời hạn và trigger đánh giá lại.
5. Diễn giải vai trò của CISO, risk owner, control owner, Legal/Compliance và assessor/auditor.
6. Áp dụng Claim–Argument–Evidence để đánh giá mức tin cậy của các control bù trừ.
7. Quản lý vòng đời accepted risk từ đề xuất, quyết định, theo dõi đến gia hạn, thu hồi hoặc hoàn tất khắc phục.

## 2. Chấp nhận rủi ro là gì?

### 2.1. Một quyết định về rủi ro còn lại

Rủi ro bảo mật là khả năng các tình huống bất định ảnh hưởng mục tiêu về tính bí mật, toàn vẹn, sẵn sàng hoặc hoạt động kinh doanh. Không phải mọi rủi ro đều có thể bị loại bỏ hoàn toàn. Ngay cả khi dịch vụ có MFA, phân quyền tối thiểu, kiểm thử bảo mật và giám sát tốt, vẫn có khả năng xảy ra lỗi, khai thác mới hoặc sự cố ở bên thứ ba.

**Risk acceptance** là lựa chọn giữ lại một mức rủi ro đã phân tích, trong phạm vi và thẩm quyền xác định. Nó phải trả lời ít nhất:

- **Rủi ro nào?** Kịch bản, điều kiện xảy ra, tài sản và hậu quả.
- **Mức nào?** Likelihood, impact, current/residual risk và độ bất định theo phương pháp đã phê duyệt.
- **Vì sao?** Những phương án giảm, tránh và chia sẻ rủi ro đã được xem xét như thế nào?
- **Cơ sở nào?** Control nào có hiệu quả và bằng chứng nào chứng minh điều đó?
- **Ai chịu trách nhiệm?** Người quyết định đúng thẩm quyền, người vận hành control, người giám sát.
- **Đến khi nào?** Điều kiện duy trì, hạn xem xét, trigger tái đánh giá và hành động khi điều kiện thất bại.

Một quyết định có thể có lý do hợp lý về chi phí và thời gian, nhưng **lợi ích kinh doanh không tự thay thế bằng chứng về rủi ro**.

### 2.2. Các khái niệm liên quan

| Khái niệm | Nội dung | Lưu ý |
|---|---|---|
| **Inherent risk** | Rủi ro trước khi xem xét tác động của các control xử lý rủi ro, theo quy ước đánh giá | Không phản ánh đầy đủ trạng thái hiện tại nếu đã có control |
| **Current/residual risk** | Rủi ro còn lại sau khi xét hiệu quả các control hiện thực tế | Không tính hiệu quả của control mới chỉ nằm trong kế hoạch |
| **Target risk** | Mức rủi ro kỳ vọng sau các hành động tương lai | Chưa phải mức đã được chứng minh |
| **Risk appetite** | Loại và mức rủi ro tổ chức sẵn sàng chấp nhận để theo đuổi mục tiêu | Do cấp quản trị phù hợp xác định |
| **Risk tolerance** | Giới hạn/mức biến động cụ thể được phép trong một hoạt động hoặc mục tiêu | Phải nêu quy ước và cách đo |
| **Risk owner** | Người có trách nhiệm đối với phương án xử lý rủi ro và thẩm quyền quyết định theo ủy quyền | Không nhất thiết trực tiếp sửa lỗi kỹ thuật |
| **Control owner** | Người triển khai, vận hành và cung cấp bằng chứng về control | Không mặc nhiên có quyền accept rủi ro |
| **Accepted risk** | Rủi ro đã có quyết định giữ lại hợp lệ, còn hiệu lực trong điều kiện xác định | Vẫn phải theo dõi và đánh giá lại |

Tổ chức có thể dùng thuật ngữ *risk retention* cho việc giữ rủi ro và *risk acceptance* cho quyết định phê duyệt chính thức. Điều cần thiết là các thuật ngữ được định nghĩa nhất quán trong chính sách.

### 2.3. Acceptance, exception và finding khác nhau

- **Risk acceptance:** quyết định quản trị về hậu quả bất định đối với mục tiêu.
- **Policy exception/waiver:** cho phép một sai lệch cụ thể khỏi chính sách hoặc tiêu chuẩn **nội bộ**, trong giới hạn thẩm quyền và điều kiện nhất định.
- **Finding:** sai lệch được phát hiện qua kiểm thử, giám sát hoặc audit với bằng chứng và tiêu chí liên quan.
- **Remediation:** hành động loại bỏ hoặc giảm nguyên nhân của sai lệch, thường cần kiểm thử lại.
- **Compliance status:** kết quả đáp ứng hoặc chưa đáp ứng một bộ yêu cầu đã xác định.

Ví dụ, việc cho phép một hệ thống legacy chưa tuân thủ chuẩn nội bộ về thay secret có thể cần **cả hồ sơ ngoại lệ và quyết định chấp nhận rủi ro**. Ngoại lệ có thời hạn không khiến control trở thành “đạt” về mặt kỹ thuật. Một auditor vẫn có thể ghi nhận tiêu chí chưa đáp ứng theo chương trình đánh giá tương ứng.

## 3. Khi nào có thể xem xét chấp nhận?

Các tình huống thường thấy:

1. **Rủi ro hiện tại ở trong mức chấp nhận đã phê duyệt**, bằng chứng xác nhận control liên quan hoạt động.
2. **Rủi ro còn lại không thể loại bỏ hoàn toàn** dù đã áp dụng các biện pháp hợp lý.
3. **Sửa ngay tạo rủi ro phụ đáng kể** cho dữ liệu, vận hành hoặc tính sẵn sàng; có thể cần cách giảm rủi ro theo giai đoạn.
4. **Một thành phần cần thời gian thay thế**, trong lúc đó đã có control bù trừ được kiểm chứng và điều kiện theo dõi rõ.
5. **Chi phí và lợi ích của các phương án xử lý khác nhau** được đánh giá, và quyết định giữ một phần rủi ro nằm trong thẩm quyền.

Ngược lại, không nên dùng acceptance như giải pháp mặc định khi:

- Rủi ro vượt appetite/tolerance hoặc có tác động nghiêm trọng mà cấp hiện tại không có quyền phê duyệt.
- Không xác định được tài sản, đường tiếp cận, độ phủ control hoặc hiệu quả vận hành vì thiếu bằng chứng trọng yếu.
- Có khả năng gây vi phạm nghĩa vụ pháp lý/hợp đồng bắt buộc mà không có cơ chế hợp pháp để xử lý.
- Người đề xuất chưa xem xét biện pháp giảm thiểu khả thi hoặc chỉ viện dẫn áp lực tiến độ.
- Control bù trừ được nêu tên nhưng chưa kiểm thử, không có owner hoặc không có cách phát hiện khi thất bại.

### Bảng ví dụ quyết định

| Kịch bản | Nhận định ban đầu | Hướng xử lý phù hợp |
|---|---|---|
| Lỗ hổng ít phơi bày, đường khai thác được xác minh bị chặn, tác động giới hạn | Có thể xem xét acceptance | Lưu evidence, người phê duyệt, điều kiện và lịch review |
| Hệ thống legacy không nâng cấp ngay được nhưng đã giới hạn và giám sát đường input | Có thể cân nhắc tạm thời | Phê duyệt đúng thẩm quyền, control bù trừ, thời hạn nâng cấp |
| API công khai trả dữ liệu lớp học ngoài quyền, không có cách giới hạn tác động | Không nên chấp nhận theo quy trình thông thường | Sửa, tắt hoặc giới hạn chức năng; escalate |
| Thiếu inventory tài khoản admin, chưa kiểm tra MFA và log | Chưa đủ bằng chứng | Kiểm tra trạng thái và độ phủ trước khi quyết định |
| Một nghĩa vụ bảo mật pháp lý hoặc hợp đồng chưa được đáp ứng | Không tự miễn bằng acceptance nội bộ | Tham vấn Legal/Compliance, xử lý nghĩa vụ theo cơ chế phù hợp |

“Có thể xem xét” không có nghĩa “phải chấp nhận”. Quyết định cuối cùng phụ thuộc mức rủi ro, nghĩa vụ và thẩm quyền thực tế.

## 4. Đánh giá kịch bản trước khi chấp nhận

Một đề nghị chỉ ghi “CVE mức medium” hay “score 8/25” là chưa đủ. Rủi ro phải có bối cảnh và hậu quả.

Có thể viết risk statement:

> Do **[điểm yếu hoặc điều kiện]** tại **[tài sản/quy trình]**, **[sự kiện hoặc hành động]** có thể dẫn đến **[hậu quả]**, ảnh hưởng **[mục tiêu bảo mật/kinh doanh]**.

Ví dụ:

> Do bộ xử lý báo cáo Java dùng phiên bản thư viện cũ với đường nhận file có thể bị lạm dụng, một input độc hại có thể gây hành vi xử lý ngoài dự kiến, khiến dịch vụ ngừng hoạt động hoặc làm lộ dữ liệu báo cáo học tập.

Câu này vẫn cần kiểm chứng: nguồn file thực tế, phân quyền upload, đường thực thi thư viện, quyền process, khả năng lan rộng và hậu quả dữ liệu. Gọi hệ thống “nội bộ” chưa đủ để chứng minh nó không thể bị khai thác.

### 4.1. Danh sách dữ liệu cần thu thập

| Nội dung | Câu hỏi | Bằng chứng |
|---|---|---|
| Tài sản và mục tiêu | Dữ liệu/hoạt động nào cần bảo vệ, tầm quan trọng? | Asset inventory, data classification, BIA |
| Threat và đường tác động | Nguồn sự kiện nào, điều kiện khai thác nào? | Threat model, data flow, đường truy cập |
| Exposure | Có thể tiếp cận từ Internet, VPN, hệ thống trung gian hay service account? | Cấu hình IAM/network và phép thử |
| Control hiện tại | Có phòng ngừa, phát hiện, phản ứng, phục hồi nào? | Test report, log, policy runtime, diễn tập |
| Likelihood | Căn cứ cho khả năng/tần suất trong kỳ là gì? | Dữ liệu sự kiện, threat intel phù hợp, giả định |
| Impact | Có thể mất gì: CIA, dữ liệu cá nhân, doanh thu, nghĩa vụ? | BIA, mapping dữ liệu, ý kiến nghiệp vụ/Legal |
| Uncertainty | Còn đường nào chưa test, log nào bị thiếu? | Evidence gap, phạm vi và assumption |
| Phương án | Giảm/né tránh/chia sẻ với chi phí và tác động nào? | Kế hoạch kỹ thuật, các phương án, lịch triển khai |
| Thẩm quyền | Ai chịu risk, ai được phê duyệt? | Risk policy và ma trận phân quyền |

### 4.2. Ví dụ mô hình điểm và giới hạn

Giả sử dùng ma trận nội bộ likelihood và impact từ 1 đến 5, với điểm minh họa bằng tích hai mức:

| Giai đoạn | Likelihood | Impact | Điểm minh họa | Ý nghĩa |
|---|---:|---:|---:|---|
| Inherent | 4 | 4 | 16 | Trước hiệu quả control |
| Current/residual | 2 | 4 | 8 | Chỉ nếu các control hiện tại được xác minh |
| Target | 1 | 4 | 4 | Mức kỳ vọng sau nâng cấp và retest |
| Accepted | 2 | 4 | 8 | Mức hiện tại nếu người có thẩm quyền đồng ý theo điều kiện |

Các điểm là **nhãn quy ước**, không phải xác suất hay giá trị thiệt hại đo được. Điểm 8 không tự có nghĩa tổn thất 8% hoặc nguy cơ thấp. Nếu chưa xác minh mức residual, trạng thái đúng là **chưa đủ bằng chứng**, không được tự gán 8 chỉ vì đã đặt lịch nâng cấp.

Thang điểm không thay thế phân tích kịch bản cực đoan. Một sự kiện có khả năng hiếm nhưng gây mất dữ liệu thiết yếu hoặc hậu quả rất nghiêm trọng có thể đòi hỏi escalation riêng, bất kể tổng điểm.

## 5. Risk appetite, tolerance và thẩm quyền

**Risk appetite** xác định loại và mức rủi ro tổ chức sẵn sàng giữ để đạt mục tiêu. **Risk tolerance** chuyển định hướng đó thành giới hạn có thể áp dụng cho dịch vụ hoặc quy trình. Các giới hạn cần được cấp quản trị phù hợp phê duyệt.

Ví dụ minh họa cho nền tảng học trực tuyến:

- Rất ít chấp nhận nguy cơ lộ diện rộng thông tin cá nhân của học viên do lỗi phân quyền.
- Một lỗ hổng liên quan tới luồng xuất dữ liệu được chứng minh có thể truy cập chéo lớp phải bị chặn hoặc sửa trước khi mở cho người dùng theo baseline nội bộ.
- Một ngoại lệ ảnh hưởng hệ thống trọng yếu phải được báo cấp có thẩm quyền cao hơn risk owner của nhóm nhỏ.
- Điều kiện kiểm soát bắt buộc theo luật hoặc hợp đồng không được gỡ bỏ chỉ bằng quyết định nội bộ.

Các quy định trên chỉ là **ví dụ về chính sách doanh nghiệp**, không phải chuẩn pháp lý chung.

### 5.1. Ma trận thẩm quyền mẫu

| Mức độ/đặc điểm | Người phê duyệt minh họa | Điều kiện |
|---|---|---|
| Rủi ro thấp, trong tolerance | Risk owner của dịch vụ được ủy quyền | Hồ sơ đầy đủ, theo dõi và đánh giá lại |
| Rủi ro trung bình, có ngoại lệ control | Risk owner theo phân cấp; Security/CISO phản biện | Control bù trừ, test/evidence, lịch xử lý |
| Rủi ro cao, liên quan nhiều đơn vị | Ban điều hành/ủy ban rủi ro theo ủy quyền | Đánh giá phương án, nghĩa vụ, tác động và giới hạn |
| Vượt appetite hoặc vi phạm nghĩa vụ bắt buộc | Escalation để thay phương án và xử lý theo yêu cầu | Không xử lý như approval thông thường |

Ma trận minh họa phải được thay bằng **delegation matrix** thực tế. CISO có thể có quyền veto hoặc phê duyệt một số mức rủi ro nếu tổ chức giao; không mặc nhiên CISO có toàn quyền chấp nhận mọi rủi ro. Risk owner chịu trách nhiệm với hậu quả kinh doanh và quyết định theo quyền hạn, control owner chịu trách nhiệm triển khai, assessor/auditor đánh giá bằng chứng theo chức năng.

## 6. Vòng đời quyết định chấp nhận rủi ro

~~~mermaid
flowchart TD
    A["Nhận diện risk và risk owner"] --> B["Đánh giá current risk, control, evidence"]
    B --> C["Kiểm tra appetite, nghĩa vụ, thẩm quyền"]
    C --> D{"Có đủ điều kiện xem xét?"}
    D -->|"Không hoặc chưa rõ"| E["Giảm/né tránh, bổ sung test hoặc escalate"]
    E --> B
    D -->|"Có"| F["So sánh phương án và control bù trừ"]
    F --> G["Hồ sơ đề nghị: scope, rationale, condition, expiry"]
    G --> H{"Cấp có thẩm quyền phê duyệt?"}
    H -->|"Không"| E
    H -->|"Có"| I["Theo dõi control, finding và trigger"]
    I --> J{"Hết hạn hoặc điều kiện thay đổi?"}
    J -->|"Có"| B
    J -->|"Không"| I
~~~

### Bước 1 — Nhận diện đúng kịch bản

Ghi nhận risk statement, asset, mục tiêu, impact, nguyên nhân, thời kỳ, scope, nguồn phát hiện; liên kết finding, incident, change hoặc lỗ hổng có liên quan. Xác định risk owner và control owner. Một vulnerability có thể liên quan nhiều rủi ro, một rủi ro cũng có thể chứa nhiều điểm yếu.

### Bước 2 — Đánh giá current/residual risk bằng chứng cứ

Kiểm tra kiến trúc thực, config production, quyền truy cập, test và log. Phân biệt **control đã vận hành** với **control chỉ mới dự kiến**, đồng thời nêu assumptions, evidence gaps, confidence.

Một ảnh chụp cấu hình của tháng trước không đủ để chứng minh quyền truy cập hiện tại sau nhiều thay đổi. “Chưa có cảnh báo” không chứng minh không xảy ra sự kiện nếu chưa kiểm tra hệ thống detection còn hoạt động.

### Bước 3 — Kiểm tra giới hạn chấp nhận và nghĩa vụ

Đối chiếu appetite, tolerance, thang mức rủi ro, dữ liệu cần bảo vệ, phạm vi khách hàng, quy định hợp đồng và pháp luật. Cần tham vấn Legal/Compliance khi nghĩa vụ chưa rõ hoặc có yếu tố dữ liệu riêng tư, thông báo sự cố, phạm vi audit.

Một chữ ký acceptance **không xóa nghĩa vụ pháp lý** và không tự chuyển trạng thái compliance “không đạt” thành “đạt”.

### Bước 4 — Phân tích các lựa chọn

| Hướng xử lý | Ý nghĩa | Ví dụ |
|---|---|---|
| **Mitigate/reduce** | Giảm likelihood hoặc impact bằng control | Nâng cấp thư viện, giới hạn quyền, thêm kiểm thử |
| **Avoid** | Ngừng hoặc không mở hoạt động tạo risk | Tắt đường import hoặc trì hoãn tính năng |
| **Share/transfer** | Chia sẻ một số hậu quả qua hợp đồng/bảo hiểm | Hỗ trợ ứng phó từ nhà cung cấp, bảo hiểm phù hợp |
| **Accept/retain** | Giữ một phần residual risk theo quyết định | Chạy legacy worker trong phạm vi cô lập có thời hạn |

Cần so sánh tác động nghiệp vụ, rủi ro phụ của phương án (ví dụ nâng cấp gấp có thể làm sai dữ liệu), chi phí, khả năng thực thi, bằng chứng giảm rủi ro và nghĩa vụ liên quan. **Chọn acceptance chỉ vì ít việc hơn** là cơ sở yếu.

### Bước 5 — Viết đề nghị có điều kiện

Hồ sơ nêu rõ service, môi trường, endpoint, loại dữ liệu, tài khoản, phiên bản, đường tấn công được xét; bằng chứng, mức rủi ro còn lại, phương án khác, người chịu trách nhiệm, điều kiện được tiếp tục vận hành, trigger dừng/đánh giá lại và thời hạn.

Với một ngoại lệ tạm thời, phải có **kế hoạch khắc phục** và phép retest xác nhận hiệu quả. Nếu tiếp tục lâu dài trong tolerance, vẫn phải xác định chu kỳ đánh giá lại phù hợp.

### Bước 6 — Quyết định và lưu dấu vết

Cấp có thẩm quyền xem thông tin cân bằng gồm điều đã biết, phần bất định, tác động nếu sự kiện xảy ra và phương án đối ứng. Ghi người duyệt, vai trò, ngày, phiên bản tài liệu, điều kiện, ý kiến phản biện quan trọng, ngày hết hạn hoặc chu kỳ review. Nếu không được phê duyệt, chuyển sang phương án xử lý khác.

Không đi tìm người ký mới có ít thông tin hơn để né kết luận risk review ban đầu.

### Bước 7 — Theo dõi liên tục và xử lý trigger

Theo dõi điều kiện như ingress, IAM, alert, restore, cấu hình, độ phơi bày và lịch remediation. Khi có khai thác mới, thay đổi data flow, control fail hoặc hết hạn, đánh giá lại ngay theo mức độ rủi ro.

### Bước 8 — Gia hạn, thu hồi hoặc đóng

Nếu khắc phục đã thực hiện, phải **retest trước khi kết luận** mức residual mới và đóng theo quy trình. Nếu muốn gia hạn, cần đánh giá lại bằng chứng hiện tại, số lần gia hạn, phương án, lý do chưa sửa và thẩm quyền. Không chỉ sửa ngày hết hạn trên hồ sơ cũ.

## 7. Bằng chứng trong quyết định chấp nhận

Security assurance giúp câu hỏi “đủ an toàn để chấp nhận chưa?” trở thành các **claim có thể kiểm chứng**.

| Claim | Bằng chứng nên xem | Giới hạn |
|---|---|---|
| Luồng nhập legacy không truy cập được từ Internet | Network/IAM export runtime, sơ đồ data flow, negative access test | Có thể tồn tại proxy, peering hoặc luồng trung gian chưa kiểm tra |
| Service account có quyền tối thiểu | Role/policy thực tế, phép thử ngoài quyền, access review | Chỉ có tài liệu role là chưa đủ |
| Tấn công bất thường sẽ được phát hiện | Log ingest, synthetic event, rule và alert routing, ticket triage | Có rule nhưng không có người nhận chưa chứng minh response |
| Backup giảm hậu quả sự cố | Restore drill, kiểm tra dữ liệu, thời gian, khóa giải mã | Backup job success chưa đủ chứng minh restore |
| Thay đổi vá đã giảm exposure | Diff code/config, kết quả test trước/sau, release evidence | Test một tuyến không chứng minh tất cả tuyến đã được bảo vệ |
| Control bù trừ có hiệu quả theo kỳ | Historical log, change history, kiểm thử định kỳ | Ảnh chụp một thời điểm không chứng minh hoạt động liên tục |

### 7.1. Ba lớp hiệu quả

1. **Design effectiveness:** Control có xử lý đúng kịch bản không, kể cả đường bypass?
2. **Implementation effectiveness:** Control có thực sự được triển khai đúng trong hệ thống, môi trường, tài khoản và luồng thuộc phạm vi?
3. **Operating effectiveness:** Control có hoạt động ổn định theo kỳ, kể cả khi thay đổi, lỗi hoặc có sự kiện?

Chỉ sau khi phân tích cả ba lớp theo nhu cầu rủi ro mới có cơ sở kết luận residual risk. Nếu thiếu bằng chứng trọng yếu, cách báo cáo đúng có thể là **chưa đủ căn cứ**; thiếu thông tin không có nghĩa rủi ro thấp.

### 7.2. Chất lượng evidence

Kiểm tra **relevance, scope, freshness, provenance/integrity, completeness/representativeness và repeatability**. Cần có dấu thời gian, phiên bản, nguồn, owner, khoảng thời gian, điều kiện test và giới hạn. Bằng chứng nhạy cảm như log chứa dữ liệu học viên phải được lưu với quyền truy cập phù hợp, có thể che dữ liệu khi cung cấp bản đánh giá nhưng vẫn giữ đường đối chiếu nguồn.

### 7.3. Claim–Argument–Evidence (CAE)

**Claim:** Trong phạm vi worker báo cáo production được xác định, nguồn input và quyền truy cập của worker được giới hạn theo tiêu chí đã phê duyệt.

**Argument:** Gateway và IAM chặn đường truy cập ngoài scope; quyền process được hạn chế; log và cảnh báo có khả năng phát hiện sự kiện bất thường; kế hoạch cô lập giới hạn tác động.

**Evidence:** Data flow và inventory thực tế, config gateway/IAM, negative tests, log/synthetic alert, diễn tập tạm dừng worker, change record và kết quả review trong kỳ.

**Limitations:** Các tuyến input chưa được kiểm chứng, quyền bên thứ ba chưa đánh giá hoặc môi trường khác phải được ghi rõ. Claim không được khẳng định vượt phạm vi bằng chứng.

## 8. Control bù trừ và giới hạn

**Compensating control** là biện pháp thay thế/bổ sung nhằm giảm rủi ro khi control chính chưa thể triển khai ngay. Một control được gọi là “bù trừ” không tự động chứng minh nó tương đương yêu cầu gốc.

Ví dụ, một ứng dụng legacy chưa hỗ trợ MFA trực tiếp cho quản trị viên. Biện pháp có thể gồm cổng truy cập trung gian có xác thực mạnh, giới hạn nguồn mạng, quyền tối thiểu, log phiên, cảnh báo sử dụng quyền đặc biệt và thời hạn thay thế. Nhưng nếu tồn tại đường đăng nhập trực tiếp bỏ qua cổng, hoặc một chương trình compliance yêu cầu MFA trực tiếp mà không có cơ chế bù trừ tương đương được công nhận, thì hồ sơ chưa thể được coi đạt yêu cầu đó.

Control bù trừ cần:

- Mô tả chính xác **rủi ro và đường tác động** đang giảm.
- Có **control owner** và cách đo/test được.
- Được triển khai đúng phạm vi hiện tại.
- Có **bằng chứng vận hành**, không chỉ kiến trúc dự kiến.
- Có cơ chế phát hiện khi control mất hiệu lực.
- Được đối chiếu với nghĩa vụ bắt buộc; xem xét điều kiện đặc thù của từng chương trình compliance.

Không nên dùng “có WAF/SIEM” làm lời đáp mặc định cho mọi rủi ro. WAF có thể không chặn lỗi phân quyền theo dữ liệu; SIEM có thể phát hiện chậm hơn lúc dữ liệu đã bị xuất trái phép.

## 9. Mẫu hồ sơ acceptance

Ví dụ dưới đây minh họa một biểu mẫu nội bộ. Các ngày, mã và giá trị điểm **không phải dữ liệu của một hệ thống thực**, cũng không phải ngưỡng quy định của framework.

~~~yaml
acceptance_id: RA-REPORT-014
risk_id: RISK-REPORT-014
title: "Tiếp tục dùng thư viện xử lý file legacy trong thời gian nâng cấp"
scope:
  service: "learning-report-worker"
  environment: "production"
  assets: ["report-data", "worker-service-account"]
  covered_entry_points: ["controlled-report-ingest"]
scenario: >
  Input độc hại vào thư viện xử lý file cũ có thể gây hành vi
  ngoài dự kiến, ảnh hưởng tính toàn vẹn, bí mật hoặc tính sẵn sàng.
current_risk:
  method: "Ma trận nội bộ minh họa 1-5"
  likelihood: 2
  impact: 4
  score: 8
  confidence: "Trung bình trong phạm vi đã kiểm tra"
assumptions:
  - "Worker không nhận input trực tiếp từ Internet"
  - "IAM role của worker chỉ có quyền với dữ liệu báo cáo cần xử lý"
existing_controls:
  - id: NET-12
    evidence: "Cấu hình runtime và negative access tests"
  - id: IAM-05
    evidence: "IAM policy export và kiểm thử ngoài quyền"
  - id: LOG-02
    evidence: "Log pipeline, synthetic alert và kết quả triage"
rationale: >
  Chấp nhận có điều kiện trong thời gian kiểm thử tương thích
  nâng cấp, không mở rộng nguồn input hoặc phạm vi dữ liệu.
alternatives:
  - "Tạm dừng import báo cáo"
  - "Nâng cấp ngay với kế hoạch kiểm thử/chuyển đổi"
risk_owner: "Business owner được ủy quyền"
control_owners: ["Platform", "Backend", "Security Operations"]
security_review: "CISO/GRC theo chính sách"
approval:
  decision: "Approved subject to conditions"
  authority: "Risk owner theo phân cấp"
  approved_at: "2026-11-28"
  expires_at: "2026-12-12"
conditions:
  - "Không thêm public ingress"
  - "Không cấp quyền mới cho service account"
  - "Cảnh báo khi thay ingress, IAM hoặc xuất hiện input bất thường"
remediation:
  owner: "Backend Team"
  action: "Nâng cấp và chạy regression/security tests"
  due_at: "2026-12-10"
reassessment_triggers:
  - "Threat intelligence mới làm thay đổi exploitability"
  - "Thay input source, mạng, IAM hoặc dữ liệu"
  - "Control bù trừ thất bại hoặc có incident"
status: "Ví dụ minh họa; không phải quyết định đã ban hành"
~~~

**Giải thích:** Scope cho biết quyết định bao phủ điều gì; assumptions tạo điều kiện để tái đánh giá; current risk chỉ có giá trị nếu evidence đủ; approval ghi đúng thẩm quyền; remediation nêu hành động và retest; triggers có thể làm quyết định hết phù hợp **trước ngày hết hạn**.

Một hồ sơ chỉ ghi “chấp nhận lỗ hổng đến cuối tháng” thiếu bản chất kịch bản, owner, điều kiện và cách giám sát.

## 10. Tình huống xuyên suốt: worker báo cáo Java

### 10.1. Bối cảnh

Nền tảng học trực tuyến có dịch vụ Java xử lý file báo cáo. Nhóm backend phát hiện phiên bản thư viện xử lý file cũ có vấn đề bảo mật liên quan đến input không tin cậy. Nếu nâng cấp tức thời, API của thư viện mới có thể làm chuyển đổi sai dữ liệu, ảnh hưởng chức năng báo cáo trong kỳ thi. Nhóm đề nghị **duy trì thư viện cũ trong hai tuần**.

Bước đầu tiên không phải phê duyệt hay bác bỏ dựa trên một CVE score. Cần hỏi:

- Người dùng nào có thể upload file, kể cả qua hệ thống trung gian?
- Worker có thể đọc hoặc ghi loại dữ liệu nào; IAM role có quá rộng không?
- Vấn đề được phát hiện có liên quan tới code path và loại input đang dùng không?
- Có thể cô lập worker khỏi Internet và những service khác không?
- Có log và cảnh báo đủ để phát hiện input bất thường không?
- Tạm dừng import có gây rủi ro nghiệp vụ gì; có phương án dự phòng không?
- Có nghĩa vụ pháp luật/hợp đồng nào ảnh hưởng quyết định không?

### 10.2. Phương án cần so sánh

| Phương án | Lợi ích | Rủi ro/chi phí cần xem |
|---|---|---|
| **A. Tạm tắt worker** | Loại bỏ đường xử lý nguy hiểm trong lúc sửa | Gián đoạn báo cáo, xử lý backlog và phương án thay thế |
| **B. Nâng cấp ngay** | Giảm thời gian dùng phiên bản cũ | Có thể sai kết quả do incompatibility, cần regression test |
| **C. Chấp nhận có điều kiện hai tuần** | Có thời gian nâng cấp/kiểm thử cẩn thận | Vẫn có khả năng khai thác; phụ thuộc hiệu quả cô lập/giám sát |
| **D. Giới hạn luồng nhập và nâng cấp từng phần** | Có thể giảm exposure và duy trì một phần dịch vụ | Phức tạp vận hành, cần xác minh giới hạn và dữ liệu |

Phương án C chỉ có cơ sở nếu residual risk đã được xác định đáng tin cậy, không vi phạm nghĩa vụ và người phê duyệt đủ thẩm quyền. Sự bất định cao hoặc đường khai thác chưa biết có thể khiến lựa chọn A/D an toàn hơn.

### 10.3. Điều kiện acceptance có thể đặt ra

Một quyết định tạm thời có thể yêu cầu:

1. **Network/data flow:** không có đường public ingress tới worker hoặc gateway chưa được đánh giá; lưu kết quả kiểm tra từ các nguồn mạng liên quan.
2. **IAM:** service account chỉ có quyền dữ liệu báo cáo cần thiết; negative tests chứng minh từ chối hành động ngoài scope.
3. **Detection:** log và alert được kiểm thử bằng sự kiện có kiểm soát, người trực có runbook và escalation.
4. **Containment:** có khả năng dừng nhận input nhanh nếu phát hiện khai thác; phải có người trực chịu trách nhiệm.
5. **Release control:** thay network, quyền hoặc nguồn input phải kích hoạt tái đánh giá; feature mới không tự được hưởng ngoại lệ cũ.
6. **Remediation:** người phụ trách nâng cấp, mốc hoàn thành và retest có kiểm chứng; quyết định không được tự gia hạn.
7. **Governance:** risk owner chấp thuận sau khi xem phản biện của Security và nghĩa vụ từ Legal/Compliance khi liên quan.

### 10.4. Khi nào quyết định không còn hiệu lực?

Sau một tuần, team product mở luồng upload file trực tiếp từ bên ngoài. Đây là **thay đổi điều kiện nguồn input**, có thể tăng likelihood. Quyết định cũ không thể tiếp tục được dùng làm chứng cứ rằng residual risk vẫn bằng mức đã đánh giá. Cần kiểm tra lại exposure, có thể giới hạn/tạm dừng luồng mới và yêu cầu quyết định mới theo thẩm quyền.

Nếu phát hiện control cô lập worker đã fail, dù chưa tới ngày hết hạn, phải xử lý trigger theo chính sách. **Ngày hết hạn là giới hạn thời gian, không phải cam kết rằng mọi điều kiện sẽ giữ nguyên cho đến ngày đó.**

### 10.5. Khi remediation hoàn tất

Team backend triển khai thư viện mới và chạy đủ regression/security tests, kiểm tra artifact đúng bản deploy, cấu hình và log. Assessor đối chiếu kết quả với finding gốc và cập nhật residual risk. Chỉ khi đạt điều kiện đóng, ngoại lệ được đóng theo quy trình, với hồ sơ quyết định cũ vẫn được giữ phục vụ audit. Không kết luận “đã sửa” chỉ từ commit được merge hoặc ticket đổi sang Done.

## 11. Risk acceptance trong hồ sơ assurance và audit

Một chương trình bảo mật cần quản lý **risk**, **finding**, **exception**, **remediation** và **assurance claim** bằng các quan hệ truy vết, tránh dùng một trạng thái thay tất cả.

| Đối tượng | Nội dung theo dõi | Ví dụ kết luận |
|---|---|---|
| **Risk** | Kịch bản, khả năng, tác động, current residual, owner | Rủi ro đang được chấp nhận có điều kiện |
| **Finding** | Kiểm soát/tiêu chí đã thất bại và evidence | Vẫn ghi nhận sai lệch, chưa retest |
| **Exception** | Sai khác với policy nội bộ có được cho phép tạm thời? | Đã duyệt, còn hạn theo điều kiện |
| **Remediation** | Owner, action, deadline, kết quả retest | Đang xử lý, chưa xác minh hiệu quả |
| **Assurance claim** | Bằng chứng có chứng minh mục tiêu bảo mật? | Chỉ được kết luận trong phạm vi đã kiểm tra |
| **Compliance** | Mức đáp ứng yêu cầu áp dụng theo chương trình | Không tự chuyển “không đạt” thành “đạt” nhờ approval |

Một số chương trình nội bộ có thể cho phép đóng finding theo disposition “risk accepted”. Dù vậy cần lưu lịch sử sai lệch, liên kết quyết định và tiếp tục giám sát accepted risk. Nếu tiêu chí audit yêu cầu control thực sự đạt hoặc retest pass, không thể thay thế bằng chữ ký acceptance.

**Ví dụ:** Lần kiểm thử authorization phát hiện có thể xuất dữ liệu ngoài lớp. Risk owner quyết định tạm giới hạn tính năng trong mạng quản trị và theo dõi; finding về control chưa sửa không được viết lại thành “test pass”. Chỉ khi kết quả mới chứng minh việc truy cập trái phép bị chặn theo tiêu chí thì mới có căn cứ cập nhật trạng thái kỹ thuật.

### 11.1. Phân tách thực thi và đánh giá

- **Engineering/Platform:** vận hành control, cung cấp trạng thái, thực hiện remediation.
- **Security/GRC/CISO:** xây phương pháp, phản biện đánh giá, xác định evidence gaps và báo cáo.
- **Risk owner:** quyết định xử lý/chấp nhận trong thẩm quyền.
- **Legal/Compliance:** làm rõ nghĩa vụ và điều kiện không được miễn bằng chính sách nội bộ.
- **Internal audit/assessor độc lập:** đánh giá quy trình và bằng chứng với mức độc lập phù hợp.

Người tự vận hành control và tự ký kết luận độc lập về control đó tạo nguy cơ xung đột lợi ích. Nếu không có đánh giá độc lập, phải nêu rõ mức độ tự đánh giá và giới hạn trong báo cáo.

## 12. Xử lý bất đồng và quyết định khẩn cấp

### 12.1. Khi Security và Product không đồng thuận

Giả sử Product cho rằng rủi ro thấp vì chưa có sự cố, Security cho rằng cao vì endpoint chứa dữ liệu nhạy cảm và log thiếu. Không nên lấy trung bình hai điểm. Cần:

1. Kiểm tra lại **dữ kiện**: phạm vi dữ liệu, đường truy cập, control, bằng chứng.
2. Phân biệt **độ bất định** với **khác biệt về khẩu vị rủi ro**.
3. So sánh phương án giới hạn hoạt động với phương án phát hành đầy đủ.
4. Ghi ý kiến và bằng chứng phản biện.
5. Chuyển quyết định tới cấp được ủy quyền; nếu vượt appetite hoặc có nghĩa vụ bắt buộc, không xử lý như phê duyệt thường.

CISO có thể được giao quyền chặn phát hành theo chính sách; điều này cần xác định trước. Chữ ký của risk owner cũng không thay thế kiểm tra pháp lý khi nghĩa vụ bên ngoài chưa rõ.

### 12.2. Trường hợp sự cố hoặc thay đổi khẩn cấp

Một quyết định trong sự cố sản xuất có thể phải thực hiện nhanh, chẳng hạn tạm mở quyền khẩn cấp để phục hồi hệ thống. Chính sách có thể có cơ chế **emergency approval có giới hạn**: người có thẩm quyền, phạm vi, thời hạn rất ngắn, log bắt buộc và hậu kiểm.

Điều kiện khẩn cấp **không** cho phép bỏ toàn bộ ghi nhận rủi ro. Khi chưa đủ thông tin, có thể ưu tiên cô lập, hạ phạm vi hoặc tạm dừng chức năng để tránh hậu quả lớn; sau đó kiểm tra và bổ sung hồ sơ.

## 13. Theo dõi acceptance trong phát triển và vận hành

Chấp nhận rủi ro không phải hành động một lần. Cần kết nối với SDLC, change management, vulnerability management, SOC, incident response và audit.

| Hoạt động | Bằng chứng/trạng thái cần quan sát | Trigger |
|---|---|---|
| Threat modeling | Phạm vi tài sản, dữ liệu và đường tấn công | Chuyển kiến trúc, thêm luồng truy cập |
| Secure development | Code path, dependency, test security | Thư viện có khai thác mới, thêm endpoint |
| CI/CD và release | Artifact, config, policy check, feature flag | Bypass security gate, mở thêm ingress |
| IAM và vận hành | Role, secret, tài khoản, drift | Tăng quyền, mất điều kiện least privilege |
| Logging/SOC | Log health, alert, ticket, incident | Không phát hiện được sự kiện mô phỏng, control fail |
| Backup/recovery | Restore test, RPO/RTO theo mục tiêu | Thử khôi phục thất bại, dữ liệu mới |
| Audit/GRC | Approval, expiry, exception, finding, remediation | Đến hạn, audit yêu cầu kiểm tra khác |
| Nhà cung cấp | Hợp đồng, kiến trúc, báo cáo sự cố liên quan | Thay dịch vụ, phạm vi truy cập hoặc nghĩa vụ |

**Continuous assurance** nghĩa là bằng chứng và đánh giá được cập nhật với tốc độ thay đổi và mức rủi ro, không phải chạy mọi test mỗi phút. Những acceptance phụ thuộc điều kiện động như network, IAM hoặc telemetry nên có giám sát theo sự kiện và kiểm tra định kỳ.

### 13.1. Gia hạn có kiểm soát

Trước khi gia hạn một ngoại lệ, phải xem lại:

- Lý do remediation chưa hoàn tất; kế hoạch mới có khả thi không?
- Exposure, threat intelligence, loại dữ liệu, quyền và phạm vi có thay đổi?
- Control bù trừ có còn hoạt động, test và evidence đủ mới?
- Có incident, near miss hoặc finding mới làm thay đổi đánh giá?
- Lần gia hạn thứ mấy; có tạo thành nợ bảo mật kéo dài?
- Risk owner và thẩm quyền còn phù hợp không?
- Có phương án giảm, tránh hoặc chia sẻ tốt hơn trước?

Không nên chỉ kéo dài ngày trên bản ghi, hoặc gia hạn tự động khi owner không phản hồi.

## 14. Đo lường và báo cáo accepted risk

| Chỉ số | Ý nghĩa | Giới hạn |
|---|---|---|
| Accepted risks theo mức ảnh hưởng và tài sản trọng yếu | Nhìn mức tập trung rủi ro tồn đọng | Số lượng không cho biết tổng mức thiệt hại |
| Tỷ lệ có approver/owner đúng thẩm quyền | Đánh giá trách nhiệm quản trị | Có chữ ký chưa chắc phân tích đúng |
| Tỷ lệ có evidence hợp lệ theo kỳ | Đánh giá độ tin cậy của căn cứ | Evidence sai scope vẫn có thể tạo chỉ số giả |
| Số ngoại lệ quá hạn và số lần gia hạn | Xem mức nợ khắc phục | Không ép đóng bằng thủ thuật thay trạng thái |
| Tỷ lệ control bù trừ qua test | Đánh giá hiệu quả thay thế | Test phải có độ phủ và độc lập phù hợp |
| Thời gian từ trigger đến tái đánh giá | Kiểm tra khả năng phản ứng với thay đổi | Sẽ sai nếu không có cơ chế phát hiện trigger |
| Tỷ lệ remediation được retest | Xem rủi ro tạm có được xử lý thật | Ticket Done không có nghĩa rủi ro giảm |
| Số incident liên quan accepted risk | Học từ giả định và hậu quả thực tế | Chỉ số phụ thuộc năng lực phát hiện và báo cáo sự cố |

Báo cáo CISO/ban lãnh đạo nên làm rõ **những acceptance trọng yếu, rủi ro có evidence yếu, ngoại lệ quá hạn, trigger đã xảy ra, quyết định cần cấp trên và kế hoạch khắc phục**. Chỉ số “100% phiếu đã ký” là chỉ số thủ tục, không phải bảo đảm an toàn.

## 15. Sai lầm thường gặp

**“Có chữ ký chấp nhận nghĩa là rủi ro đã được loại bỏ.”** Không. Acceptance chỉ ghi quyết định giữ rủi ro trong điều kiện; phải theo dõi residual risk.

**“Rủi ro thấp theo score thì luôn chấp nhận được.”** Không. Score định tính phụ thuộc giả định và ngưỡng, có thể che tác động nghiêm trọng hoặc nghĩa vụ bắt buộc.

**“Không có sự cố là bằng chứng nguy cơ thấp.”** Không chắc. Có thể hệ thống phát hiện không hoạt động hoặc chưa có tình huống kích hoạt.

**“Có kế hoạch nâng cấp nghĩa là residual risk đã giảm.”** Kế hoạch tạo target risk. Chỉ bằng chứng control đã triển khai và vận hành mới hỗ trợ đánh giá current risk.

**“WAF hoặc SIEM bù cho mọi thiếu sót.”** Không. Cần kiểm tra phù hợp với threat path, khả năng bypass và hiệu quả phát hiện/giới hạn hậu quả.

**“Gia hạn mãi vẫn là ngoại lệ tạm.”** Gia hạn lặp lại có thể che nợ bảo mật; mỗi lần cần đánh giá mới và thẩm quyền phù hợp.

**“Risk acceptance có thể xóa yêu cầu compliance.”** Quyết định nội bộ không thể miễn nghĩa vụ pháp lý, hợp đồng và tiêu chí bắt buộc của chương trình audit.

**“CISO hoặc kỹ sư sửa lỗi luôn có quyền duyệt risk.”** Thẩm quyền phụ thuộc phân cấp chính thức; người đánh giá và người ra quyết định có thể khác nhau.

**“Finding đã được risk accepted nên phải báo đạt.”** Không. Báo cáo phải phân biệt sai lệch kỹ thuật, exception hợp lệ, residual risk và kết luận audit.

**“Ngày hết hạn chưa tới nên luôn an toàn.”** Một thay đổi IAM, data flow hoặc khai thác mới có thể làm điều kiện acceptance không còn đúng ngay lập tức.

## 16. Bài tập thực hành

### Bài tập A — Đề nghị chấp nhận thiếu căn cứ

Một ứng dụng Java sử dụng thư viện cũ. Team đề xuất giữ nguyên một tháng vì: “đã có API gateway”, “không thấy incident”, “đã có ticket nâng cấp”.

Hãy phân loại:

1. Điều nào là **giả định cần kiểm tra**, điều nào **không chứng minh rủi ro thấp**?
2. Cần evidence gì về đường input, network/IAM, code path, log và dữ liệu?
3. Có phương án giới hạn/tắt chức năng hoặc sửa trước một phần không?
4. Ai phê duyệt; cần điều kiện, hạn và trigger nào?
5. Nếu có nghĩa vụ hợp đồng bắt buộc về vá lỗ hổng, cần làm gì?

**Gợi ý:** Gateway có thể có bypass hoặc luồng không qua gateway; chưa thấy incident không đủ khi coverage detection chưa được kiểm tra; ticket chỉ là kế hoạch. Phải xác nhận current control và nghĩa vụ trước khi quyết định.

### Bài tập B — Điều kiện thay đổi trước ngày hết hạn

Một phiếu acceptance được duyệt vì worker chỉ nhận file từ nguồn nội bộ. Mười ngày trước hạn, bản phát hành mới cho phép import trực tiếp từ tài khoản người dùng bên ngoài.

Hãy xác định:

- Những assumption và risk score cũ nào không thể dùng lại mà không kiểm tra?
- Ai phải phát hiện và báo thay đổi; ai có quyền giới hạn luồng import?
- Cần kiểm thử và lấy bằng chứng mới nào?
- Cần cập nhật finding, exception, risk và approval như thế nào?

**Định hướng:** Thay đổi nguồn input có thể làm exposure/likelihood tăng; phải đánh giá lại ngay, không dựa vào ngày hết hạn. Tùy kết quả, tạm tắt, giảm phạm vi hoặc trình phê duyệt mới đúng thẩm quyền.

### Bài tập C — Viết một phiếu acceptance ngắn

Một service account dùng để gửi thông báo có quyền đọc dữ liệu rộng hơn mức cần thiết; team chưa thể giảm quyền ngay do tích hợp bên thứ ba.

Hãy viết đề nghị gồm:

1. Risk statement, asset, impact và đường lạm dụng tài khoản.
2. Scope tài khoản, môi trường, dữ liệu, quyền hiện tại.
3. Likelihood, impact, mức uncertainty và evidence gaps.
4. Existing/compensating controls và phép kiểm thử cho từng control.
5. Phương án tránh, giảm, chia sẻ hoặc chấp nhận có điều kiện.
6. Risk owner, control owner, reviewer và cấp phê duyệt.
7. Rationale, conditions, expiry, triggers, remediation và retest.
8. Kết luận đạt điều kiện đề nghị, không đạt hay chưa đủ bằng chứng.

**Gợi ý:** Nếu không biết chính xác quyền service account và phạm vi dữ liệu bên thứ ba có thể truy cập, chưa có cơ sở kết luận residual risk thấp. Cần export quyền thực tế, negative test, audit log và đánh giá luồng tích hợp.

## 17. Checklist trước khi trình quyết định

Checklist giúp rà soát chất lượng hồ sơ, **không tự biến việc tick đủ mục thành bằng chứng rủi ro đã an toàn**:

- [ ] Risk scenario, tài sản, mục tiêu và hậu quả được viết đủ rõ để đánh giá.
- [ ] Scope dịch vụ, tài khoản, môi trường, dữ liệu và kỳ đánh giá cụ thể.
- [ ] Current/residual risk, giả định, uncertainty và phương pháp phân loại được ghi rõ.
- [ ] Control hiện tại có evidence từ trạng thái thật và phép thử phù hợp.
- [ ] Đã so sánh giảm, tránh, chia sẻ rủi ro với acceptance.
- [ ] Đã kiểm tra appetite, tolerance, nghĩa vụ pháp lý/hợp đồng và tiêu chí chương trình áp dụng.
- [ ] Risk owner, control owner, reviewer và approver đúng thẩm quyền.
- [ ] Có rationale, điều kiện, giới hạn, thời hạn/chu kỳ và trigger.
- [ ] Nếu tạm thời, có remediation, owner, deadline và retest.
- [ ] Finding/exception/compliance được ghi nhận trung thực, không tự đổi fail thành pass.
- [ ] Có giám sát trigger, lưu lịch sử quyết định và kênh escalation.
- [ ] Người quyết định đã được thông tin về rủi ro còn lại và **những điều chưa được chứng minh**.

## 18. Ghi nhớ

- **Risk acceptance là quyết định quản trị có trách nhiệm**, không phải bằng chứng hệ thống không còn lỗ hổng.
- Chỉ dựa trên **current/residual risk được đánh giá với evidence phù hợp**; target risk của một kế hoạch tương lai chưa phải kết quả đã đạt.
- **Risk owner/cấp được ủy quyền** quyết định; Security/CISO tư vấn và đánh giá, control owner triển khai, Legal/Compliance làm rõ nghĩa vụ, assessor/auditor kiểm chứng theo chức năng.
- Không thể dùng acceptance nội bộ để miễn **nghĩa vụ tuân thủ bắt buộc** hoặc che giấu finding.
- Quyết định phải truy vết **risk → controls → tests/evidence → residual risk → acceptance → monitoring/reassessment**.
- Với ngoại lệ tạm thời, cần **điều kiện, ngày hết hạn, trigger, remediation và retest**; khi phạm vi hay control thay đổi, đánh giá lại trước khi tiếp tục dựa trên quyết định cũ.

