# Thiết kế điểm chặn chất lượng (quality gate) với kết quả rõ ràng và người chịu trách nhiệm

## 1. Quality gate là gì và giải quyết vấn đề nào?

**Điểm chặn chất lượng (quality gate)** là một điểm kiểm soát trong vòng đời phát triển hoặc phát hành, tại đó nhóm đánh giá bằng chứng theo các tiêu chí đã xác định để đưa ra kết quả có thể hành động. Gate có thể quyết định một thay đổi được tích hợp, một bản dựng được chuyển sang giai đoạn tiếp theo, một dịch vụ được triển khai hoặc một release được phát hành.

Một gate tốt trả lời được bốn câu hỏi:

1. **Đánh giá điều gì?** Phạm vi, phiên bản, rủi ro và loại bằng chứng cần có.
2. **Điều kiện nào quyết định kết quả?** Tiêu chí đo được, ngưỡng, quy tắc và ngoại lệ.
3. **Kết quả có ý nghĩa gì?** Pass, fail, warning, blocked hoặc trạng thái khác dẫn đến hành động cụ thể nào.
4. **Ai chịu trách nhiệm?** Ai duy trì tiêu chí, ai cung cấp bằng chứng, ai xử lý lỗi và ai có thẩm quyền quyết định.

Trong chiến lược **VALIDATION_TESTING_STRATEGY**, quality gate giúp biến mục tiêu chất lượng thành quyết định nhất quán. Gate có thể kiểm soát chất lượng mã, kiểm thử chức năng, hợp đồng API, bảo mật, hiệu năng, dữ liệu, khả năng vận hành và mức sẵn sàng phát hành. Gate không tự tạo ra chất lượng; nó đánh giá bằng chứng và bảo đảm các vấn đề quan trọng được xử lý bởi đúng người.

Nếu tiêu chí mơ hồ như “test phải tốt”, kết quả phụ thuộc vào cảm nhận của từng người. Nếu gate chỉ hiển thị một dấu xanh mà không nêu phạm vi và bằng chứng, người xem có thể hiểu nhầm rằng toàn bộ hệ thống đã an toàn. Nếu không có owner, một gate thất bại có thể nằm chờ mà không ai chịu trách nhiệm. Vì vậy, thiết kế gate cần gắn tiêu chí, trạng thái, hành động và vai trò vào cùng một quy trình.

## 2. Phân biệt quality gate với kiểm thử, checklist và phê duyệt

Các hoạt động này bổ trợ nhau nhưng có mục đích khác nhau:

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Test/check | Thực hiện một phép xác nhận cụ thể và tạo kết quả | Chạy unit test hoặc quét dependency |
| Checklist | Nhắc người thực hiện xem xét các mục cần thiết | Kiểm tra migration, rollback và tài liệu vận hành |
| Quality gate | Đánh giá một tập tiêu chí và quyết định có được chuyển bước hay không | Chặn merge nếu test bắt buộc thất bại |
| Approval | Một người có thẩm quyền xem xét và chấp thuận quyết định | Release authority phê duyệt phát hành |
| Quality review | Đánh giá tổng hợp về chất lượng, rủi ro và bằng chứng | Cuộc họp readiness trước release |
| Policy | Quy định tiêu chí hoặc giới hạn cần tuân thủ | Không phát hành khi còn lỗ hổng mức nghiêm trọng theo chính sách |

Một gate có thể tổng hợp kết quả của nhiều test, checklist và approval. Nhưng việc một người nhấn nút approve không thay thế bằng chứng kiểm thử; tương tự, tất cả test tự động đạt không nhất thiết có nghĩa release đã đáp ứng mọi yêu cầu vận hành hoặc tuân thủ.

Gate cũng khác dashboard. Dashboard giúp quan sát xu hướng và trạng thái; gate áp dụng quy tắc để tạo kết quả và hành động. Một dashboard có thể hiển thị coverage 85%, nhưng gate cần chỉ rõ 85% được tính trên phạm vi nào, phần 15% còn lại có rủi ro gì và điều kiện nào cho phép chuyển bước.

## 3. Nguyên tắc thiết kế một quality gate đáng tin cậy

### 3.1. Gắn với rủi ro và mục tiêu chất lượng

Chỉ đưa vào gate những tiêu chí có liên quan đến rủi ro hoặc mục tiêu cần bảo vệ. Một gate cho pull request có thể ưu tiên tính đúng đắn, kiểm thử nhanh, lỗi bảo mật nghiêm trọng và chất lượng mã. Gate trước phát hành có thể bổ sung hồi quy, hiệu năng, migration, quan sát vận hành, rollback và ngoại lệ.

Không cần áp dụng cùng một bộ tiêu chí cho mọi thành phần. Một thư viện dùng chung, một dịch vụ thanh toán và một công cụ nội bộ có mức tác động khác nhau. Tiêu chí cần tương xứng với mức rủi ro, phạm vi sử dụng và nghĩa vụ của sản phẩm.

### 3.2. Tiêu chí phải rõ và kiểm chứng được

Mỗi tiêu chí nên có:

- Đối tượng được đánh giá và phạm vi áp dụng.
- Điều kiện đạt hoặc ngưỡng cụ thể.
- Nguồn bằng chứng và cách thu thập.
- Thời điểm đánh giá và phiên bản liên quan.
- Cách xử lý khi thiếu dữ liệu hoặc công cụ không hoạt động.
- Owner chịu trách nhiệm duy trì và giải thích tiêu chí.

Ví dụ, “hiệu năng tốt” không phải tiêu chí đủ rõ. Một tiêu chí cụ thể hơn có thể là “ở workload đã thống nhất, p95 của endpoint tạo đơn không vượt ngưỡng mục tiêu, tỷ lệ lỗi nằm trong giới hạn và không có giao dịch trùng”. Ngưỡng thật phải lấy từ yêu cầu dịch vụ và baseline đã được chấp thuận.

### 3.3. Kết quả phải dẫn đến hành động

Gate không nên chỉ đưa ra điểm số. Mỗi trạng thái cần chỉ rõ hành động tiếp theo: tiếp tục, sửa lỗi, bổ sung bằng chứng, chờ môi trường, yêu cầu review hoặc xin ngoại lệ. Khi gate fail, thông báo phải giúp người nhận biết tiêu chí nào thất bại và cần liên hệ ai.

### 3.4. Phân biệt lỗi sản phẩm với lỗi quy trình hoặc môi trường

Test fail có thể do lỗi sản phẩm, test không ổn định, dữ liệu sai, môi trường không sẵn sàng hoặc runner bị lỗi. Gate cần giữ trạng thái inconclusive/blocked khi chưa đủ bằng chứng để kết luận. Không tự động chuyển lỗi môi trường thành pass, cũng không quy mọi lỗi runner thành defect sản phẩm.

### 3.5. Có thể truy vết và kiểm toán

Lưu kết quả cùng build ID, commit, phiên bản cấu hình, môi trường, thời điểm, nguồn dữ liệu và artifact. Nếu gate được đánh giá lại, giữ lịch sử lần trước để giải thích vì sao kết quả thay đổi. Một quyết định phát hành cần truy ngược được về tiêu chí và bằng chứng đã dùng.

### 3.6. Có owner và thẩm quyền rõ ràng

Owner của tiêu chí không nhất thiết là người chạy test. Người cung cấp bằng chứng, người xử lý lỗi và người quyết định ngoại lệ có thể là các vai trò khác nhau. Gate cần thể hiện rõ trách nhiệm để không có tình trạng mọi người đều xem kết quả nhưng không ai chịu trách nhiệm.

### 3.7. Tự động hóa phần có thể tự động hóa

Các tiêu chí khách quan và lặp lại như unit test, schema validation, vulnerability scan hoặc ngưỡng coverage phù hợp có thể được tự động hóa. Những đánh giá cần phán đoán như mức chấp nhận rủi ro, tính phù hợp nghiệp vụ hoặc readiness vận hành có thể cần review của con người. Nên tự động hóa việc thu thập bằng chứng và nhắc owner ngay cả khi quyết định cuối cùng cần người phê duyệt.

## 4. Các thành phần của một gate

Một gate có thể được mô hình hóa bằng những thành phần sau:

| Thành phần | Câu hỏi cần trả lời | Nội dung ví dụ |
|---|---|---|
| Gate ID/name | Gate nào đang được đánh giá? | PR Quality Gate, Release Readiness Gate |
| Trigger | Khi nào gate chạy? | Pull request được tạo, build hoàn tất, trước rollout |
| Scope | Đối tượng nào thuộc phạm vi? | Commit, service, artifact, release candidate |
| Criteria | Điều kiện nào cần đáp ứng? | Test bắt buộc đạt, không có finding nghiêm trọng chưa xử lý |
| Threshold | Ngưỡng định lượng là gì? | Coverage tối thiểu theo phạm vi được xác định |
| Evidence | Bằng chứng lấy từ đâu? | CI report, scan report, dashboard, checklist |
| Evaluation | Quy tắc kết hợp kết quả là gì? | Tất cả hard criteria đạt; advisory criteria được ghi nhận |
| Outcome | Kết quả gate là gì? | Pass, fail, warning, blocked, inconclusive |
| Action | Kết quả dẫn đến hành động nào? | Cho merge, chặn deploy, tạo việc khắc phục |
| Owner | Ai duy trì và xử lý? | Service owner, test lead, security owner |
| Approver | Ai có quyền chấp thuận ngoại lệ? | Release authority hoặc người được ủy quyền |
| Expiry/review | Khi nào cần xem xét lại? | Mỗi quý hoặc khi thay đổi rủi ro |

Một gate có thể có nhiều tiêu chí con. Mỗi tiêu chí con cần có trạng thái và bằng chứng riêng để người xem biết chính xác phần nào đạt hoặc chưa đạt.

## 5. Thiết kế tiêu chí và ngưỡng đạt

### 5.1. Bắt đầu từ yêu cầu và rủi ro

Với mỗi mục tiêu chất lượng, xác định rủi ro cần giảm thiểu. Ví dụ:

- Tính đúng đắn: thay đổi có thể làm sai quy tắc nghiệp vụ hoặc dữ liệu.
- Tương thích: thay đổi có thể phá vỡ consumer hoặc API contract.
- Bảo mật: thay đổi có thể tạo lỗ hổng, lộ secret hoặc vượt quyền.
- Hiệu năng: thay đổi có thể làm tăng độ trễ, lỗi hoặc tiêu thụ tài nguyên.
- Độ tin cậy: thay đổi có thể gây timeout, retry sai hoặc mất khả năng phục hồi.
- Vận hành: dịch vụ có thể thiếu metric, cảnh báo, runbook hoặc phương án khôi phục.

Sau đó chọn bằng chứng đủ sức kiểm tra rủi ro. Không dùng một chỉ số tiện đo nhưng không liên quan để đại diện cho mục tiêu. Ví dụ, code coverage cao không chứng minh phân quyền đúng; số lượng test nhiều không chứng minh các hành trình quan trọng đã được xác nhận.

### 5.2. Định nghĩa tiêu chí định lượng

Tiêu chí định lượng cần xác định:

- Chỉ số và đơn vị đo.
- Phạm vi tính toán và mẫu số.
- Cửa sổ thời gian hoặc số lần chạy.
- Ngưỡng đạt, ngưỡng cảnh báo và ngưỡng không đạt.
- Nguồn dữ liệu và cách loại bỏ dữ liệu không hợp lệ.
- Điều kiện môi trường và phiên bản.

Ví dụ với coverage, cần nêu coverage nào: line, branch, requirement hay risk coverage; đo trên phần mã thay đổi hay toàn bộ module; test nào được tính; công cụ nào tạo báo cáo. Không đặt một ngưỡng chung mà không xem xét loại mã và rủi ro.

Ví dụ với hiệu năng, cần nêu workload, thời lượng, số mẫu, percentile, tỷ lệ lỗi và cấu hình tài nguyên. Một p95 đạt trong vài request trên môi trường nhàn rỗi không đại diện cho tải mục tiêu.

### 5.3. Định nghĩa tiêu chí định tính

Một số tiêu chí không thể biểu diễn bằng một con số. Có thể dùng câu hỏi có lựa chọn và bằng chứng bắt buộc:

- Migration đã được review và có phương án phục hồi được thử nghiệm chưa?
- Runbook có nêu dấu hiệu phát hiện, bước xử lý và người liên hệ không?
- Các thay đổi có ảnh hưởng đến dữ liệu nhạy cảm đã được security/privacy review chưa?
- Các ngoại lệ có owner, lý do và hạn hết hiệu lực chưa?

Tiêu chí định tính vẫn phải có điều kiện quan sát được. “Đã review” nên chỉ rõ reviewer, phạm vi, ngày và kết luận; không chỉ đánh dấu checkbox không có bằng chứng.

### 5.4. Dùng hard gate và advisory gate

**Hard gate** là tiêu chí bắt buộc; không đạt thì không được chuyển bước trừ khi có quy trình ngoại lệ hợp lệ và người có thẩm quyền chấp thuận. Ví dụ, test bắt buộc thất bại hoặc phát hiện lỗ hổng vượt ngưỡng không được xử lý.

**Advisory gate** cung cấp cảnh báo hoặc khuyến nghị. Không đạt có thể không chặn ngay, nhưng phải hiển thị rõ tác động và owner. Ví dụ, tài liệu có một mục chưa hoàn thiện nhưng không ảnh hưởng đến vận hành hiện tại có thể là advisory tùy chính sách.

Không nên biến mọi tiêu chí thành hard gate. Quá nhiều cổng cứng làm giảm tốc độ, khuyến khích tìm cách lách và khiến nhóm bỏ qua cảnh báo. Ngược lại, tiêu chí rủi ro nghiêm trọng không nên chỉ là advisory để giữ pipeline xanh.

### 5.5. Tránh tối ưu chỉ số sai lệch

Khi một chỉ số trở thành mục tiêu, nhóm có thể tối ưu con số mà không cải thiện chất lượng. Ví dụ:

- Tăng line coverage bằng assertion không kiểm tra hành vi.
- Giảm số finding bằng cách hạ mức severity hoặc loại scan khỏi phạm vi.
- Đạt thời gian pipeline bằng cách bỏ các test quan trọng.
- Đạt tỷ lệ pass bằng cách retry liên tục hoặc quarantine test thất bại.
- Đóng checklist mà không có artifact.

Để hạn chế, kết hợp nhiều bằng chứng, review định kỳ chất lượng chỉ số và theo dõi tác dụng phụ. Tiêu chí gate cần đo đúng mục tiêu mà nó đại diện.

## 6. Xác định trạng thái và quy tắc kết quả

Một gate nên có tập trạng thái thống nhất. Ví dụ:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| PASS | Tất cả hard criteria đạt và bằng chứng hợp lệ | Cho phép chuyển bước theo phạm vi gate |
| FAIL | Có hard criterion không đạt | Chặn chuyển bước; tạo hoặc liên kết công việc xử lý |
| WARNING | Có advisory criterion chưa đạt hoặc có rủi ro cần chú ý | Cho phép tiếp tục nếu chính sách cho phép; ghi nhận owner và kế hoạch |
| BLOCKED | Không thể đánh giá do môi trường, quyền, dữ liệu hoặc phụ thuộc | Chờ khắc phục điều kiện; không coi là pass |
| INCONCLUSIVE | Có kết quả nhưng bằng chứng mâu thuẫn, thiếu hoặc không đáng tin | Bổ sung bằng chứng hoặc chạy lại |
| WAIVED | Có ngoại lệ được người có thẩm quyền chấp thuận trong phạm vi và thời hạn xác định | Tiếp tục theo điều kiện ngoại lệ; vẫn giữ trạng thái tiêu chí gốc |
| NOT APPLICABLE | Tiêu chí không áp dụng với căn cứ đã được review | Loại khỏi phạm vi đánh giá theo quy tắc |

Không nên dùng WAIVED để thay đổi lịch sử một tiêu chí fail thành pass. Báo cáo cần giữ trạng thái gốc, quyết định ngoại lệ, người chấp thuận và điều kiện áp dụng.

### 6.1. Quy tắc kết hợp

Một quy tắc đơn giản có thể là:

- Nếu có hard criterion FAIL, gate là FAIL.
- Nếu có điều kiện không thể đánh giá, gate là BLOCKED hoặc INCONCLUSIVE theo nguyên nhân.
- Nếu tất cả hard criteria PASS nhưng còn advisory finding, gate là WARNING.
- Nếu tất cả hard criteria PASS và không có cảnh báo chưa xử lý, gate là PASS.
- Nếu có ngoại lệ được chấp thuận, kết quả phải hiển thị rõ trạng thái WAIVED/conditional theo chính sách.

Thứ tự ưu tiên giữa các trạng thái cần được quy định. Ví dụ, không nên hiển thị PASS nếu một tiêu chí bắt buộc chưa có bằng chứng chỉ vì các tiêu chí khác đều đạt.

### 6.2. Kết quả phải giới hạn theo phạm vi

Một gate chỉ xác nhận phạm vi được định nghĩa. PR gate đạt có nghĩa các tiêu chí của PR gate đạt cho commit đó; nó không chứng minh toàn bộ release đã sẵn sàng. Release gate đạt cũng không bảo đảm không còn lỗi, mà cho biết bằng chứng và tiêu chí đã thỏa mãn trong phạm vi đánh giá.

Mọi báo cáo cần hiển thị đối tượng, phiên bản, thời điểm và tiêu chí đã áp dụng. Nếu artifact thay đổi sau khi gate chạy, cần đánh giá lại hoặc chạy gate mới.

## 7. Đặt gate ở đâu trong vòng đời phát triển?

### 7.1. Gate ở pull request

Mục tiêu là phản hồi nhanh trước khi tích hợp thay đổi. Các tiêu chí thường gồm:

- Build và kiểm tra định dạng/lint cần thiết.
- Unit test hoặc component test nhanh.
- Kiểm tra chất lượng mã theo phạm vi thay đổi.
- Kiểm tra secret và lỗ hổng nghiêm trọng theo policy.
- Review bắt buộc và quy tắc ownership.
- Kiểm tra schema hoặc contract nếu thay đổi giao diện.

Gate PR nên ưu tiên tốc độ và độ ổn định. Các test dài có thể chạy ở pipeline sau tích hợp hoặc trước release, nhưng phải có quy tắc đảm bảo chúng được thực hiện trước thời điểm bắt buộc.

### 7.2. Gate sau tích hợp

Sau khi thay đổi được tích hợp, kiểm tra tổ hợp mã và dependency:

- Integration test và contract verification.
- Regression suite theo rủi ro.
- Kiểm tra migration hoặc tương thích schema.
- Kiểm tra cấu hình và image.
- Kiểm thử các luồng liên dịch vụ quan trọng.

Gate này cần xác định rõ phiên bản các dịch vụ và môi trường. Kết quả từ một service đơn lẻ không tự động chứng minh tổ hợp tích hợp đã đạt.

### 7.3. Gate trước phát hành

Gate trước release tổng hợp bằng chứng kỹ thuật, nghiệp vụ và vận hành:

- Kiểm thử bắt buộc và lỗi nghiêm trọng.
- Các rủi ro còn lại và test chưa chạy.
- Bảo mật, privacy, compliance theo phạm vi.
- Hiệu năng, khả năng mở rộng và độ tin cậy.
- Migration, backup, rollback hoặc forward-fix.
- Monitoring, alert, dashboard và runbook.
- Tài liệu phát hành, thông báo và owner trực vận hành.
- Ngoại lệ đã được chấp thuận và thời hạn.

Không nên để gate release phụ thuộc vào một tỷ lệ pass tổng thể duy nhất. Cần kiểm tra các điều kiện trọng yếu riêng biệt.

### 7.4. Gate sau triển khai

Sau khi deploy, thực hiện smoke test, health check, kiểm tra metric và xác nhận các hành trình quan trọng. Nếu dùng canary, gate có thể đánh giá:

- Tỷ lệ lỗi và độ trễ.
- Tỷ lệ giao dịch thành công hoặc chỉ số nghiệp vụ.
- Tình trạng tài nguyên và phụ thuộc.
- Sự cố, cảnh báo và lỗi mới.
- Điều kiện tiếp tục rollout, tạm dừng hoặc rollback.

Gate sau deploy cần có cửa sổ quan sát và ngưỡng dừng rõ. Một smoke test đạt ngay sau deploy không thay thế việc theo dõi hành vi dưới tải thực tế.

## 8. Phân công trách nhiệm và quyền quyết định

### 8.1. Các vai trò thường gặp

| Vai trò | Trách nhiệm chính trong quality gate |
|---|---|
| Service owner | Chịu trách nhiệm chất lượng dịch vụ, rủi ro kỹ thuật và kế hoạch khắc phục |
| Developer/change owner | Cung cấp thay đổi, test, giải thích lỗi và sửa vấn đề thuộc phạm vi |
| Test lead/QA owner | Thiết kế phạm vi kiểm thử, tiêu chí test, chất lượng bằng chứng và báo cáo |
| Platform/CI owner | Duy trì runner, pipeline, môi trường và cơ chế thực thi gate |
| Security owner | Xác định và đánh giá tiêu chí bảo mật, xử lý finding và ngoại lệ thuộc thẩm quyền |
| Product owner/business owner | Xác nhận yêu cầu nghiệp vụ, tác động người dùng và mức chấp nhận nghiệp vụ |
| Operations/SRE owner | Đánh giá khả năng vận hành, monitoring, capacity, incident và rollback |
| Release authority | Đưa ra quyết định phát hành trong phạm vi được ủy quyền |
| Gate owner | Duy trì định nghĩa gate, phiên bản policy, ngưỡng và quy trình xử lý |

Một người có thể đảm nhiệm nhiều vai trò ở nhóm nhỏ. Tuy nhiên, cần chỉ rõ vai trò nào đang được thực hiện và quyền quyết định nào được giao. Người chạy pipeline không mặc nhiên có quyền miễn trừ tiêu chí bảo mật hoặc chấp thuận rủi ro phát hành.

### 8.2. Phân biệt owner của tiêu chí và owner của hành động

Ví dụ, security owner có thể sở hữu chính sách severity và ngưỡng lỗ hổng; developer sở hữu việc sửa finding trong dịch vụ; service owner chịu trách nhiệm bảo đảm finding được xử lý; release authority quyết định ngoại lệ nếu chính sách cho phép.

Với gate bị BLOCKED do môi trường, platform owner xử lý hạ tầng; test lead xác định test nào bị ảnh hưởng; service owner đánh giá rủi ro; release authority quyết định nếu vẫn cần phát hành. Việc phân vai như vậy tránh chuyển trách nhiệm vòng quanh.

### 8.3. Ma trận RACI minh họa

RACI gồm Responsible (thực hiện), Accountable (chịu trách nhiệm cuối cùng), Consulted (được tham vấn) và Informed (được thông báo).

| Hoạt động | Service owner | Test lead | Platform/CI | Security | Product/Business | Release authority |
|---|---|---|---|---|---|---|
| Xác định phạm vi gate dịch vụ | A | R | C | C | C | I |
| Duy trì test và bằng chứng | C | A/R | C | C | I | I |
| Duy trì runner và thực thi pipeline | C | C | A/R | I | I | I |
| Định nghĩa policy bảo mật | C | C | I | A/R | I | I |
| Xử lý lỗi sản phẩm | A | C | C | C | I | I |
| Đánh giá tác động nghiệp vụ | C | C | I | C | A/R | I |
| Chấp thuận ngoại lệ release | C | C | I | C* | C* | A/R* |
| Công bố kết quả gate | A | R | R | C | I | I |

RACI cần được điều chỉnh theo cơ cấu thực tế và chính sách. Dấu * nhắc rằng ngoại lệ bảo mật, privacy, an toàn hoặc tuân thủ có thể cần phê duyệt riêng của người có thẩm quyền chuyên môn; release authority không tự động có quyền miễn trừ các nghĩa vụ đó.

## 9. Xử lý khi gate không đạt

### 9.1. Thông báo phải đủ thông tin

Một thông báo gate fail nên có:

- Gate ID, build/commit và thời điểm.
- Tiêu chí thất bại cùng ngưỡng hoặc expected result.
- Giá trị thực tế và nguồn bằng chứng.
- Phạm vi ảnh hưởng và rủi ro liên quan.
- Owner xử lý và cách liên hệ.
- Hành động tiếp theo và điều kiện chạy lại.

Thông báo “Quality gate failed” mà không có liên kết report hoặc owner không giúp nhóm khắc phục.

### 9.2. Phân loại nguyên nhân

Xác định thất bại thuộc nhóm nào:

- Lỗi sản phẩm hoặc regression.
- Test sai, flaky hoặc assertion không phù hợp.
- Dữ liệu hoặc môi trường không hợp lệ.
- Runner, pipeline hoặc công cụ bị lỗi.
- Thiếu bằng chứng hoặc tiêu chí chưa rõ.
- Vi phạm policy hoặc yêu cầu bắt buộc.

Nếu chưa xác định được nguyên nhân, dùng trạng thái INCONCLUSIVE hoặc BLOCKED theo quy ước. Không gán lỗi cho sản phẩm chỉ dựa trên một thông báo thất bại.

### 9.3. Khắc phục và đánh giá lại

Owner xử lý nguyên nhân, cập nhật bằng chứng và chạy lại gate trên artifact phù hợp. Nếu mã nguồn hoặc cấu hình thay đổi, kết quả cũ cần được đánh giá hiệu lực. Không chỉ rerun cho đến khi xanh mà không giải thích lần fail đầu tiên; retry có thể giúp xác định flaky test nhưng phải giữ lịch sử.

### 9.4. Không có quyền tự bỏ qua gate

Chỉ vai trò được ủy quyền mới có thể chấp thuận ngoại lệ. Việc sửa cấu hình pipeline để bỏ qua check, đổi severity hoặc xóa test nhằm vượt gate phải được xem là thay đổi policy và có review. Mọi ngoại lệ cần lưu lý do, người chấp thuận, phạm vi, thời hạn và biện pháp giảm thiểu.

## 10. Ngoại lệ và waiver có kiểm soát

Có trường hợp gate không thể đạt đúng thời điểm vì phụ thuộc ngoài, môi trường hoặc một rủi ro đã được đánh giá. Nếu policy cho phép ngoại lệ, cần tối thiểu:

1. Gate và tiêu chí cụ thể được miễn trừ.
2. Release candidate hoặc thay đổi áp dụng.
3. Lý do và bằng chứng tại sao không thể đáp ứng.
4. Rủi ro còn lại, tác động và phạm vi phơi nhiễm.
5. Biện pháp giảm thiểu và giới hạn rollout.
6. Owner chịu trách nhiệm theo dõi.
7. Người có thẩm quyền chấp thuận.
8. Thời hạn hết hiệu lực và công việc hoàn tất sau đó.
9. Điều kiện dừng, rollback hoặc kích hoạt incident.

Không được waiver các yêu cầu bị cấm miễn trừ bởi luật, hợp đồng hoặc chính sách bắt buộc. Không dùng waiver để biến trạng thái fail thành pass; báo cáo phải giữ cả kết quả gốc và quyết định ngoại lệ.

Waiver cần hết hạn tự động hoặc yêu cầu review lại khi có build mới, thay đổi phạm vi, sự cố liên quan hoặc hết thời gian đã chấp thuận. Ngoại lệ lặp lại nhiều lần là tín hiệu tiêu chí, năng lực hoặc quy trình cần được cải thiện.

## 11. Ví dụ thiết kế quality gate theo giai đoạn

### 11.1. Gate cho pull request

**Mục tiêu:** ngăn thay đổi có lỗi rõ ràng hoặc vi phạm policy cơ bản đi vào nhánh chính.

| Tiêu chí | Loại | Bằng chứng | Kết quả không đạt |
|---|---|---|---|
| Build và lint thành công | Hard | CI job report | Chặn merge |
| Unit/component test bắt buộc đạt | Hard | Test report theo commit | Chặn merge, giao change owner |
| Không có secret bị phát hiện | Hard | Secret scan report | Chặn merge, xử lý secret theo quy trình |
| Contract test liên quan đạt | Hard khi API thay đổi | Contract verification | Chặn merge hoặc yêu cầu tương thích |
| Review code theo ownership hoàn tất | Hard | Review record | Chờ reviewer được chỉ định |
| Test dài chạy theo lịch | Advisory ở PR | Scheduled pipeline link | Ghi trạng thái và bảo đảm hoàn tất trước release |

Gate này không khẳng định release đã sẵn sàng; nó chỉ xác nhận điều kiện tích hợp của thay đổi.

### 11.2. Gate cho build tích hợp

**Mục tiêu:** xác nhận các thành phần hoạt động cùng nhau ở phiên bản đã chọn.

- Integration test trọng yếu đạt.
- Contract giữa provider và consumer tương thích.
- Migration chạy trên dữ liệu đại diện.
- Không có regression mức nghiêm trọng chưa xử lý.
- Cấu hình và dependency đã được xác định.
- Bằng chứng gắn với build và environment ID.

Nếu môi trường không sẵn sàng, kết quả phải là BLOCKED; gate không thể PASS chỉ vì không có test nào báo fail.

### 11.3. Gate trước phát hành

**Mục tiêu:** xác nhận release candidate đáp ứng các yêu cầu chất lượng, rủi ro và vận hành.

| Nhóm | Tiêu chí ví dụ | Owner chính |
|---|---|---|
| Chức năng | Test bắt buộc và hành trình trọng yếu đạt | Test lead/service owner |
| Tương thích | Contract và migration đạt hoặc có phương án chuyển đổi được phê duyệt | Service owner |
| Bảo mật | Finding vượt ngưỡng được xử lý hoặc theo quy trình ngoại lệ chuyên môn | Security owner |
| Hiệu năng | Workload và SLO mục tiêu được xác nhận | Performance/SRE owner |
| Vận hành | Dashboard, alert, runbook và on-call đã sẵn sàng | Operations/SRE owner |
| Phục hồi | Rollback/forward-fix và backup phù hợp đã được xác minh | Service/Operations owner |
| Rủi ro còn lại | Khoảng trống test và ngoại lệ có owner, hạn và người chấp thuận | Service owner/release authority |

### 11.4. Gate sau triển khai

**Mục tiêu:** quyết định có tiếp tục rollout hay dừng.

- Health check và smoke test đạt.
- Error rate, latency và saturation nằm trong ngưỡng.
- Chỉ số nghiệp vụ quan trọng không suy giảm bất thường.
- Không có incident hoặc alert vượt ngưỡng.
- Canary window đã đủ dữ liệu theo kế hoạch.

Nếu bất kỳ tiêu chí dừng nào bị kích hoạt, rollout cần tạm dừng hoặc rollback theo runbook. Người trực vận hành cần biết ai được quyền tiếp tục rollout sau khi xử lý.

## 12. Mẫu đặc tả quality gate

Ví dụ dưới đây minh họa cách lưu gate và trách nhiệm. Ngưỡng là giá trị mẫu; dự án phải thay bằng tiêu chí đã được thống nhất.

~~~yaml
quality_gate:
  id: RELEASE-READINESS-01
  name: "Release readiness gate"
  trigger: "release-candidate-created"
  scope:
    artifact: "service release candidate"
    require_build_identity: true

  owners:
    gate_owner: "quality engineering"
    service_owner: "service team"
    evidence_owner: "test lead"
    platform_owner: "ci platform"
    security_owner: "security team"
    approver: "release authority"

  criteria:
    - id: REGRESSION-CORE
      description: "Core regression suite"
      type: hard
      expected: "all mandatory tests passed"
      evidence: "regression-report"
      owner: "test lead"

    - id: SECURITY-CRITICAL
      description: "Critical security findings"
      type: hard
      expected: "no unresolved critical finding"
      evidence: "security-scan-report"
      owner: "security team"

    - id: OPERATIONS-READY
      description: "Monitoring and runbook readiness"
      type: hard
      expected: "dashboard, alerts and runbook reviewed"
      evidence: "operations-readiness-record"
      owner: "operations team"

    - id: DOCUMENTATION
      description: "Release notes completeness"
      type: advisory
      expected: "release notes reviewed"
      evidence: "release-notes-review"
      owner: "product team"

  outcomes:
    pass: "all hard criteria pass"
    fail: "one or more hard criteria fail"
    blocked: "required evidence cannot be collected"
    warning: "hard criteria pass with advisory items open"

  exception:
    requires_approver: true
    requires_owner: true
    requires_expiry: true
    preserve_original_status: true
~~~

Định dạng thực tế phụ thuộc hệ thống CI hoặc công cụ quản lý policy. Điều quan trọng là mọi tiêu chí đều có ID, loại, expected result, nguồn bằng chứng và owner; kết quả tổng hợp có quy tắc rõ.

## 13. Mẫu thông báo kết quả gate

Một thông báo hữu ích có thể theo cấu trúc:

~~~text
QUALITY GATE: RELEASE-READINESS-01
SUBJECT: service-api / release-4.8.0-rc2
BUILD: build-1842
EVALUATED_AT: 2027-01-18T09:30:00Z
RESULT: BLOCKED

PASSED:
- REGRESSION-CORE: 184/184 mandatory tests passed
- SECURITY-CRITICAL: no unresolved critical findings

NOT READY:
- OPERATIONS-READY: runbook review evidence missing

OWNER:
- Operations owner: operations-team

NEXT ACTION:
- Attach reviewed runbook and on-call confirmation
- Re-evaluate this gate against build-1842

DECISION:
- Deployment is blocked until the hard criterion is satisfied
~~~

Thông báo cần trỏ đến artifact và công việc xử lý trong hệ thống chính thức. Không đưa secret, dữ liệu cá nhân hoặc chi tiết lỗ hổng nhạy cảm vào kênh thông báo rộng.

## 14. Quản trị và cải tiến quality gate

### 14.1. Phiên bản hóa policy

Lưu định nghĩa gate trong repository hoặc hệ thống có lịch sử thay đổi. Mỗi thay đổi ngưỡng, phạm vi, trạng thái hoặc người phê duyệt cần có review và lý do. Báo cáo phải cho biết phiên bản policy được dùng để đánh giá.

### 14.2. Rà soát định kỳ

Rà soát khi:

- Có incident hoặc lỗi lọt qua gate.
- Sản phẩm thay đổi kiến trúc, dữ liệu hoặc mức độ rủi ro.
- Tỷ lệ blocked, flaky hoặc waiver tăng.
- Pipeline trở nên quá chậm hoặc có nhiều false positive.
- Chính sách bảo mật, pháp lý hoặc chất lượng thay đổi.
- Owner hoặc cấu trúc nhóm thay đổi.

### 14.3. Theo dõi hiệu quả

Các chỉ số hữu ích gồm:

- Tỷ lệ gate pass/fail/blocked theo loại gate.
- Thời gian từ khi gate fail đến khi có owner xử lý.
- Thời gian chờ và tổng thời gian gate.
- Tỷ lệ false positive và inconclusive.
- Số lượng và tuổi của waiver.
- Số lỗi lọt qua gate và mức độ nghiêm trọng.
- Tỷ lệ finding lặp lại hoặc test flaky.
- Tỷ lệ tiêu chí có bằng chứng và owner còn hiệu lực.

Không dùng tỷ lệ pass cao làm mục tiêu duy nhất. Nếu gate luôn pass nhưng vẫn có incident nghiêm trọng, cần xem lại tiêu chí, phạm vi và chất lượng bằng chứng. Nếu gate fail thường xuyên do môi trường, cần cải thiện nền tảng thay vì hạ tiêu chí tùy tiện.

### 14.4. Loại bỏ tiêu chí không còn giá trị

Một gate có thể tích tụ check cũ, trùng lặp hoặc không còn liên quan. Mỗi tiêu chí nên có owner và mục tiêu rõ. Khi loại bỏ, cần đánh giá rủi ro mà nó từng bảo vệ và xác nhận có kiểm soát thay thế hay không.

### 14.5. Kiểm tra chính gate

Gate cũng là một thành phần cần được kiểm thử. Cần xác nhận:

- Hard failure thực sự chặn hành động.
- Warning hiển thị nhưng không chặn sai chính sách.
- Thiếu evidence tạo BLOCKED/INCONCLUSIVE thay vì PASS.
- Waiver chỉ hoạt động với người có thẩm quyền và đúng phạm vi.
- Waiver hết hạn hoặc mất hiệu lực đúng điều kiện.
- Kết quả gắn với đúng build, commit và policy version.
- Artifact và lịch sử vẫn truy xuất được.
- Thông báo gửi đúng owner và không lộ dữ liệu nhạy cảm.

## 15. Những sai lầm thường gặp

- **Tiêu chí mơ hồ:** mỗi người hiểu “đủ tốt” theo cách khác nhau.
- **Không có nguồn bằng chứng:** gate dựa vào checkbox hoặc lời xác nhận không truy xuất được.
- **Không có owner:** finding không được xử lý và tiêu chí không được duy trì.
- **Một gate cho mọi giai đoạn:** PR bị chặn bởi kiểm thử dài không cần thiết hoặc release thiếu kiểm tra vận hành.
- **Tất cả tiêu chí đều hard:** pipeline quá cứng, nhóm tìm cách bypass và cảnh báo mất ý nghĩa.
- **Tất cả tiêu chí đều advisory:** rủi ro nghiêm trọng không được kiểm soát.
- **Dùng một chỉ số làm đại diện chất lượng:** coverage hoặc pass rate không chứng minh mọi hành vi quan trọng.
- **Thiếu trạng thái blocked/inconclusive:** môi trường lỗi bị hiểu nhầm là sản phẩm đạt hoặc không đạt.
- **Retry đến khi pass:** che giấu flaky test và làm mất lịch sử thất bại.
- **Waiver không thời hạn:** ngoại lệ trở thành trạng thái mặc định.
- **Không kiểm tra quyền waiver:** người không có thẩm quyền có thể bỏ qua policy.
- **Không phiên bản hóa gate:** không thể giải thích tiêu chí nào đã áp dụng cho release cũ.
- **Không kiểm thử chính gate:** một lỗi cấu hình có thể cho phép deploy dù hard check thất bại.
- **Không xem xét tác dụng phụ:** gate tăng thời gian chờ nhưng không cải thiện khả năng phát hiện rủi ro.

## 16. Checklist thiết kế và vận hành quality gate

### Khi thiết kế

- [ ] Mục tiêu chất lượng và rủi ro được nêu rõ.
- [ ] Trigger, scope và artifact được xác định.
- [ ] Mỗi tiêu chí có điều kiện đạt, ngưỡng và nguồn bằng chứng.
- [ ] Hard criteria và advisory criteria được phân biệt.
- [ ] Trạng thái PASS, FAIL, WARNING, BLOCKED, INCONCLUSIVE, WAIVED và NOT APPLICABLE có ý nghĩa rõ.
- [ ] Quy tắc kết hợp kết quả không cho phép thiếu evidence thành PASS.
- [ ] Gate có owner và người có thẩm quyền cho ngoại lệ.
- [ ] Tiêu chí phù hợp với giai đoạn và mức rủi ro.

### Khi triển khai

- [ ] Gate gắn với đúng commit, build, môi trường và policy version.
- [ ] Bằng chứng được lưu và có thể truy xuất.
- [ ] Thông báo nêu tiêu chí thất bại, giá trị thực tế, owner và hành động.
- [ ] Hard failure chặn đúng hành động cần kiểm soát.
- [ ] Warning và blocked được xử lý theo chính sách.
- [ ] Quyền waiver được giới hạn và có lịch sử.
- [ ] Dữ liệu nhạy cảm được bảo vệ trong report và notification.

### Khi vận hành và cải tiến

- [ ] Có người xử lý finding và thời hạn rõ.
- [ ] Waiver có lý do, người chấp thuận và ngày hết hiệu lực.
- [ ] Gate được rà soát khi rủi ro hoặc kiến trúc thay đổi.
- [ ] Theo dõi false positive, flaky, blocked, thời gian và lỗi lọt qua.
- [ ] Các tiêu chí cũ được review trước khi loại bỏ.
- [ ] Gate được kiểm thử để xác nhận hành vi chặn và ngoại lệ.

## Kết luận

Quality gate hiệu quả cần kết hợp tiêu chí đo được, bằng chứng có thể truy vết, trạng thái dẫn đến hành động và người chịu trách nhiệm rõ ràng. Thiết kế gate theo rủi ro và theo từng giai đoạn giúp nhóm phản hồi nhanh ở pull request, xác nhận tích hợp sau build, đánh giá readiness trước phát hành và kiểm soát rollout sau triển khai. Khi hard gate, advisory, blocked và waiver được phân biệt; owner và quyền quyết định được công bố; policy được phiên bản hóa và chính gate được kiểm thử, quyết định chất lượng sẽ nhất quán và có thể giải thích.
