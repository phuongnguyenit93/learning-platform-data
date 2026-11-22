# Phân tích nguyên nhân lọt lỗi và hành động phòng ngừa

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích lỗi lọt (escaped defect) và phân biệt lỗi được phát hiện trong kiểm thử với lỗi chỉ được phát hiện sau khi phát hành.
- Xác định tác động, phạm vi, thời điểm phát sinh và thời điểm phát hiện của một lỗi lọt.
- Thu thập bằng chứng và tái dựng dòng thời gian mà không vội kết luận nguyên nhân.
- Phân tích nguyên nhân trực tiếp, yếu tố góp phần và điều kiện hệ thống bằng các kỹ thuật phù hợp.
- Phân biệt triệu chứng, nguyên nhân gốc, cơ chế lỗi và khoảng trống kiểm soát.
- Chọn hành động khắc phục, phòng ngừa và phát hiện sớm có thể kiểm chứng.
- Chuyển bài học từ incident thành thay đổi trong yêu cầu, thiết kế, dữ liệu, kiểm thử, CI/CD, monitoring và vận hành.
- Xác định owner, thời hạn, tiêu chí hiệu quả và cách theo dõi hành động sau incident.
- Đánh giá xu hướng lỗi lọt để cải thiện chiến lược kiểm thử và chất lượng sản phẩm.

## 1. Lỗi lọt là gì và vì sao cần phân tích?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, lỗi lọt (escaped defect hoặc escaped bug) là lỗi của sản phẩm không được phát hiện trong các hoạt động kiểm thử hoặc kiểm soát chất lượng dự kiến trước khi sản phẩm được đưa đến môi trường hoặc người dùng ở giai đoạn tiếp theo, thường là production. Lỗi có thể được phát hiện bởi người dùng, monitoring, bộ phận hỗ trợ, đối tác, kiểm toán hoặc một quy trình vận hành sau phát hành.

Ví dụ, nhóm kiểm thử xác nhận luồng thanh toán thành công và bộ test hồi quy đều Pass. Sau phát hành, một số giao dịch bị ghi nhận hai lần khi nhà cung cấp gửi callback lặp. Đây là lỗi lọt nếu hành vi trùng lặp nằm trong phạm vi chất lượng cần bảo vệ nhưng các kiểm soát trước phát hành không phát hiện được.

Phân tích nguyên nhân lỗi lọt không nhằm tìm người để quy trách nhiệm. Mục tiêu là hiểu điều kiện khiến lỗi được tạo ra, vì sao các lớp kiểm soát không phát hiện hoặc không ngăn được nó, và thay đổi nào sẽ giảm khả năng tái diễn hoặc giảm tác động nếu lỗi tương tự xảy ra.

Một incident có thể có nhiều yếu tố góp phần. Ví dụ, yêu cầu chưa nêu rõ xử lý callback lặp, thiết kế thiếu idempotency, dữ liệu test không có sự kiện trùng, sandbox không mô phỏng retry và monitoring chỉ đếm request thành công. Chỉ sửa test hoặc nhắc người kiểm thử “cẩn thận hơn” sẽ không giải quyết toàn bộ điều kiện gây lỗi.

Phân tích có hệ thống giúp:

- Khôi phục dịch vụ và hạn chế tác động hiện tại.
- Xác định nguyên nhân kỹ thuật và điều kiện tổ chức góp phần.
- Phát hiện khoảng trống trong yêu cầu, thiết kế, kiểm thử hoặc vận hành.
- Chọn hành động có khả năng ngăn lỗi tái diễn.
- Bổ sung test hồi quy và tín hiệu giám sát phù hợp.
- Chia sẻ bài học giữa các nhóm có cùng thành phần hoặc rủi ro.
- Đo hiệu quả cải tiến thay vì chỉ đếm số hành động đã đóng.

## 2. Phân biệt lỗi, sự cố và lỗi lọt

Các thuật ngữ liên quan cần được dùng nhất quán để phân tích không nhầm đối tượng.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Error (sai sót) | Hành động hoặc quyết định của con người/tổ chức tạo ra trạng thái sai | Một giả định về callback không được kiểm chứng. |
| Defect/Bug (lỗi trong sản phẩm) | Khiếm khuyết trong yêu cầu, thiết kế, mã, cấu hình hoặc dữ liệu | Xử lý callback không idempotent. |
| Failure (hỏng hóc quan sát được) | Hệ thống biểu hiện hành vi không đáp ứng mong đợi khi thực thi | Một đơn hàng bị ghi nhận hai lần thanh toán. |
| Incident (sự cố) | Sự kiện ảnh hưởng hoặc đe dọa dịch vụ, người dùng, dữ liệu hay hoạt động | Khách hàng bị trừ tiền hai lần và cần đối soát. |
| Escaped defect (lỗi lọt) | Lỗi không được phát hiện trước một ranh giới kiểm soát đã định và được phát hiện ở giai đoạn sau | Lỗi chỉ xuất hiện sau khi triển khai production. |
| Near miss (suýt xảy ra sự cố) | Điều kiện có thể gây tác động nhưng được phát hiện hoặc ngăn trước khi gây hậu quả | Alert phát hiện callback lặp trước khi giao dịch bị ghi trùng. |

Một defect có thể tồn tại mà chưa gây failure. Một failure có thể tạo incident hoặc chỉ ảnh hưởng một giao dịch. Một lỗi lọt không nhất thiết là sự cố nghiêm trọng; mức độ cần đánh giá theo tác động thực tế và khả năng xảy ra.

### 2.1. Xác định ranh giới “lọt”

Tổ chức cần định nghĩa ranh giới dùng để phân loại, ví dụ:

- Lỗi phát hiện sau khi merge nhưng trước khi phát hành.
- Lỗi phát hiện trong staging hoặc acceptance testing.
- Lỗi phát hiện sau production deployment nhưng trước khi mở traffic rộng.
- Lỗi phát hiện bởi người dùng sau khi phát hành.
- Lỗi phát hiện bởi monitoring hoặc bộ phận hỗ trợ sau khi hệ thống hoạt động.

Ranh giới này giúp các nhóm thống kê nhất quán. Nếu nhóm A tính lỗi phát hiện ở staging là escaped defect còn nhóm B chỉ tính lỗi production, tỷ lệ giữa hai nhóm không thể so sánh trực tiếp.

### 2.2. Không đồng nhất lỗi lọt với lỗi do QA

Lỗi có thể được tạo ra trong yêu cầu, kiến trúc, code, cấu hình, migration, tích hợp hoặc vận hành. Kiểm thử là một lớp kiểm soát trong hệ thống chất lượng, không phải lớp duy nhất chịu trách nhiệm cho mọi lỗi. Phân tích cần xem xét toàn bộ chuỗi từ hình thành yêu cầu đến triển khai và vận hành.

## 3. Ưu tiên ứng phó trước khi phân tích sâu

Khi lỗi lọt gây ảnh hưởng đang diễn ra, ưu tiên đầu tiên là bảo vệ người dùng, dữ liệu và dịch vụ. Phân tích nguyên nhân đầy đủ có thể diễn ra sau khi tình huống được kiểm soát.

### 3.1. Đánh giá mức độ và phạm vi tác động

Thu thập thông tin ban đầu:

- Hành vi sai và cách người dùng quan sát được.
- Thời điểm bắt đầu, thời điểm phát hiện và thời điểm kết thúc nếu đã khôi phục.
- Phiên bản, commit, cấu hình và môi trường liên quan.
- Số người dùng, tenant, giao dịch hoặc bản ghi bị ảnh hưởng.
- Tác động đến tiền, dữ liệu, quyền truy cập, an toàn hoặc tính sẵn sàng.
- Có nguy cơ tiếp tục phát sinh hoặc lan sang thành phần khác không?
- Có nghĩa vụ thông báo, báo cáo hoặc bảo toàn bằng chứng không?

Không suy đoán số lượng bị ảnh hưởng chỉ từ số alert. Hãy đối soát bằng dữ liệu có thẩm quyền và nêu rõ mức độ chắc chắn của con số.

### 3.2. Khoanh vùng và giảm thiểu

Tùy tình huống, hành động có thể gồm:

- Tắt feature flag hoặc dừng rollout.
- Rollback phiên bản nếu an toàn và khả thi.
- Giới hạn traffic hoặc vô hiệu hóa một luồng bị lỗi.
- Chặn giao dịch lặp hoặc đưa tác vụ vào hàng đợi xử lý thủ công.
- Cô lập dữ liệu hoặc tài khoản có nguy cơ.
- Tạm dừng job, consumer hoặc integration gây tác động.
- Áp dụng biện pháp bảo vệ tạm thời đã được review.

Biện pháp giảm thiểu cần được đánh giá về tác dụng phụ. Rollback có thể không an toàn nếu migration dữ liệu không tương thích; tắt consumer có thể làm backlog tăng; retry có thể nhân đôi giao dịch. Cần có owner, thời điểm, tiêu chí xác minh và kế hoạch gỡ bỏ biện pháp tạm thời.

### 3.3. Bảo toàn bằng chứng

Giữ lại log, trace, metric, event, phiên bản artifact, cấu hình, dữ liệu liên quan và các quyết định ứng phó theo chính sách. Bảo đảm dữ liệu nhạy cảm được bảo vệ, quyền truy cập có kiểm soát và dấu thời gian được ghi nhận. Không chỉnh sửa hoặc xóa bằng chứng cần thiết cho điều tra, kiểm toán hoặc nghĩa vụ pháp lý.

## 4. Thu thập dữ kiện và tái dựng dòng thời gian

Phân tích đáng tin cậy bắt đầu từ dữ kiện đã xác minh. Cần phân biệt điều đã biết, giả thuyết và thông tin chưa có.

### 4.1. Nguồn bằng chứng

- Ticket, yêu cầu, acceptance criteria và thiết kế.
- Commit, pull request, code review và dependency changes.
- Test plan, test case, execution report và coverage report.
- Build artifact, pipeline log và cấu hình triển khai.
- Database migration, audit log và đối soát dữ liệu.
- Application log, metric, distributed trace và event history.
- Phản hồi người dùng, ticket hỗ trợ và thông tin từ đối tác.
- Lịch sử release, feature flag, rollback và thay đổi môi trường.
- Phỏng vấn người tham gia thiết kế, phát triển, kiểm thử và vận hành.

### 4.2. Dòng thời gian

Tái dựng các mốc quan trọng:

1. Yêu cầu hoặc giả định được đưa ra.
2. Thiết kế và quyết định kỹ thuật được chốt.
3. Mã, cấu hình hoặc dữ liệu được thay đổi.
4. Test được thiết kế và thực thi.
5. Build được tạo và phát hành.
6. Lỗi bắt đầu xuất hiện (nếu xác định được).
7. Hệ thống hoặc người dùng phát hiện lỗi.
8. Các hành động khoanh vùng và khôi phục.
9. Tác động được xác nhận và incident được đóng.

Ví dụ:

| Thời điểm | Sự kiện | Nguồn xác minh |
|---|---|---|
| 09:10 | Release mới được triển khai cho 10% traffic | Deployment record. |
| 09:14 | Callback thanh toán bắt đầu được xử lý theo adapter mới | Trace và version log. |
| 09:18 | Một số callback retry bị ghi nhận thành hai giao dịch | Payment audit và database query. |
| 09:25 | Alert đối soát phát hiện chênh lệch | Monitoring alert. |
| 09:31 | Tắt rollout và chuyển xử lý giao dịch nghi ngờ sang hàng đợi kiểm tra | Incident log. |
| 10:05 | Đã khoanh vùng và xác minh không còn giao dịch mới bị ghi trùng | Reconciliation report. |

Thời gian trong ví dụ chỉ minh họa. Trong điều tra thực tế, cần chuẩn hóa timezone và kiểm tra độ lệch đồng hồ giữa các hệ thống.

### 4.3. Phân biệt dữ kiện và giả thuyết

Ghi rõ:

- **Đã xác minh**: có log, dữ liệu hoặc bằng chứng độc lập hỗ trợ.
- **Giả thuyết**: lời giải thích có vẻ hợp lý nhưng chưa được kiểm tra.
- **Chưa biết**: thiếu dữ liệu hoặc không thể tái hiện.

Không biến giả thuyết thành sự thật chỉ vì nó phù hợp với nhận định ban đầu. Nếu bằng chứng mới mâu thuẫn, cần cập nhật giả thuyết.

## 5. Xác định cơ chế lỗi và khoảng trống kiểm soát

Một phân tích đầy đủ cần trả lời hai câu hỏi riêng:

1. **Vì sao lỗi được tạo ra?** Điều kiện, giả định, thiết kế hoặc thay đổi nào tạo ra defect?
2. **Vì sao lỗi không được phát hiện trước khi lọt?** Những lớp kiểm soát nào thiếu, không phù hợp, không được thực thi hoặc không tạo đủ tín hiệu?

Hai câu hỏi có thể có câu trả lời khác nhau. Ví dụ, defect được tạo ra do logic retry thiếu idempotency; lỗi lọt vì test không mô phỏng callback lặp và monitoring không đối soát số giao dịch.

### 5.1. Phân tích theo các giai đoạn

| Giai đoạn | Câu hỏi phân tích |
|---|---|
| Yêu cầu | Trường hợp sử dụng, ngoại lệ và tiêu chí chấp nhận có đầy đủ không? |
| Thiết kế | Ranh giới, trạng thái, dependency và failure mode đã được xem xét chưa? |
| Phát triển | Logic, review, static analysis và quy ước có kiểm soát được rủi ro không? |
| Kiểm thử | Test có đúng cấp, dữ liệu, môi trường và assertion không? |
| Tích hợp | Hợp đồng, phiên bản, timeout, retry và thứ tự sự kiện có được kiểm tra không? |
| Phát hành | Cấu hình, migration, rollout và rollback có được xác minh không? |
| Vận hành | Monitoring, alert, runbook và đối soát có phát hiện được hành vi sai không? |
| Học hỏi | Bài học từ lỗi trước có được chuyển thành kiểm soát có hiệu lực không? |

### 5.2. Khoảng trống kiểm thử

Các dạng khoảng trống phổ biến:

- Không có test cho hành vi hoặc trạng thái cần thiết.
- Có test nhưng dữ liệu không kích hoạt điều kiện gây lỗi.
- Test chạy ở cấp quá thấp nên không kiểm tra tương tác thực tế.
- Chỉ kiểm tra happy path, bỏ qua lỗi, retry, timeout hoặc dữ liệu bất thường.
- Assertion không kiểm tra hậu điều kiện nghiệp vụ.
- Test bị bỏ qua, flaky hoặc không chạy trong pipeline bắt buộc.
- Môi trường test khác production ở dependency, quota, cấu hình hoặc dữ liệu.
- Test có chạy nhưng kết quả không được xem xét hoặc cổng chất lượng không chặn.

### 5.3. Khoảng trống ngoài kiểm thử

Không phải mọi lỗi lọt đều có thể được ngăn chỉ bằng thêm test. Có thể cần:

- Làm rõ yêu cầu hoặc thay đổi thiết kế.
- Thêm ràng buộc dữ liệu, transaction hoặc idempotency.
- Cải thiện quản lý cấu hình và secret.
- Thêm canary, feature flag hoặc rollout theo giai đoạn.
- Bổ sung monitoring, alert và reconciliation.
- Cải thiện quyền review hoặc quy trình phê duyệt.
- Tạo khả năng rollback hoặc phục hồi dữ liệu.

## 6. Các kỹ thuật phân tích nguyên nhân

Không có kỹ thuật duy nhất phù hợp cho mọi incident. Chọn phương pháp theo mức độ phức tạp, lượng bằng chứng và mối quan hệ nhân quả cần làm rõ.

### 6.1. Five Whys (5 lần hỏi Vì sao)

Kỹ thuật này bắt đầu từ một vấn đề quan sát được rồi liên tục hỏi “vì sao” để đi sâu hơn vào điều kiện tạo ra vấn đề. Năm lần là gợi ý, không phải con số bắt buộc; có thể cần ít hơn hoặc nhiều hơn.

Ví dụ:

1. Vì sao khách hàng bị ghi nhận thanh toán hai lần? Vì hai callback cùng giao dịch đều tạo bản ghi capture.
2. Vì sao hai callback đều tạo capture? Vì handler không kiểm tra idempotency key trước khi ghi.
3. Vì sao handler không có kiểm tra đó? Vì thiết kế giả định provider chỉ gửi một callback cho mỗi giao dịch.
4. Vì sao giả định này không bị phát hiện? Vì test sandbox chỉ kiểm tra callback đơn và không mô phỏng retry/lặp.
5. Vì sao bộ test không có tình huống lặp? Vì tiêu chí chấp nhận và test strategy chưa mô tả delivery có thể lặp.

Kết luận tạm thời: cần cập nhật hợp đồng xử lý callback, thiết kế idempotency, dữ liệu/test lặp và giám sát giao dịch trùng. Không nên dừng ở câu “tester không nghĩ đến trường hợp này”; câu trả lời đó không chỉ ra điều kiện hệ thống có thể cải thiện.

Giới hạn: Five Whys có thể dẫn đến một chuỗi nguyên nhân quá đơn giản nếu incident có nhiều nhánh hoặc nhiều yếu tố góp phần. Cần kiểm chứng từng câu trả lời bằng bằng chứng và mở rộng thành nhiều nhánh khi cần.

### 6.2. Fishbone / Ishikawa

Sơ đồ xương cá nhóm các yếu tố có thể góp phần theo các nhóm như:

- **People**: năng lực, tải công việc, chuyển giao và giao tiếp.
- **Process**: quy trình review, kiểm thử, release và escalation.
- **Technology**: kiến trúc, code, dependency, cấu hình và công cụ.
- **Data**: dữ liệu test, dữ liệu production, schema và chất lượng dữ liệu.
- **Environment**: môi trường, quota, mạng, thời gian và tài nguyên.
- **Measurement**: metric, alert, assertion và tiêu chí chấp nhận.

Fishbone giúp nhóm không chỉ tập trung vào một nguyên nhân dễ thấy. Các nhánh là danh sách giả thuyết, không phải kết luận; cần xác minh từng yếu tố có thực sự góp phần hay không.

### 6.3. Fault Tree Analysis (FTA)

Fault tree bắt đầu từ một sự kiện đỉnh (top event), sau đó phân rã thành các điều kiện cần kết hợp để sự kiện xảy ra. Cổng AND/OR giúp thể hiện quan hệ logic.

Ví dụ, “đơn hàng bị ghi nhận thanh toán hai lần” có thể xảy ra khi:

- Callback được gửi lặp **OR** request bị retry sau timeout.
- Và handler không có idempotency hoặc khóa giao dịch phù hợp.
- Và database cho phép tạo hai bản ghi capture cho cùng một giao dịch.

FTA hữu ích khi nhiều điều kiện cùng tạo ra sự cố, đặc biệt với hệ thống có rủi ro cao. Cần tránh đưa mọi khả năng vào cây mà không có bằng chứng hoặc đánh giá xác suất phù hợp.

### 6.4. Change analysis và so sánh trước/sau

So sánh:

- Commit, dependency và cấu hình giữa phiên bản tốt gần nhất và phiên bản lỗi.
- Schema, dữ liệu seed và migration.
- Feature flag, rollout percentage và môi trường.
- Hành vi response, event và trạng thái trước/sau.
- Metric và trace trước/sau khi thay đổi.

Có thể dùng bisect hoặc rollback có kiểm soát để xác định thay đổi liên quan. Không nên rollback tùy tiện nếu thay đổi dữ liệu không thể đảo ngược hoặc có nguy cơ gây thêm tác động.

### 6.5. Timeline và event correlation

Kết hợp timestamp, correlation ID, trace ID và business ID để xác định thứ tự sự kiện xuyên hệ thống. Điều này đặc biệt quan trọng với hệ thống bất đồng bộ, retry hoặc nhiều service.

### 6.6. Phân tích barrier và defense-in-depth

Liệt kê các lớp bảo vệ đáng lẽ phải ngăn hoặc phát hiện lỗi: validation, code review, unit test, contract test, integration test, staging, canary, monitoring, reconciliation và quy trình hỗ trợ. Xác định lớp nào hoạt động, lớp nào thất bại hoặc không tồn tại.

Một lớp kiểm soát có thể không phát hiện lỗi nhưng lớp sau vẫn có thể giới hạn tác động. Phân tích cần xem cả khả năng phòng ngừa, phát hiện và giảm thiểu.

## 7. Nguyên tắc phân tích không đổ lỗi

Phân tích incident hiệu quả cần tạo môi trường để người tham gia nói thật về giả định, quyết định và khó khăn. Nếu người tham gia sợ bị trừng phạt vì nêu sai sót, tổ chức sẽ mất thông tin quan trọng.

### 7.1. Tập trung vào hệ thống và điều kiện

Thay vì hỏi “Ai đã làm sai?”, hãy hỏi:

- Người thực hiện có thông tin gì tại thời điểm quyết định?
- Quy trình và công cụ đã hướng dẫn hoặc cho phép điều gì?
- Những tín hiệu nào có sẵn và tín hiệu nào bị thiếu?
- Giả định nào hợp lý trong bối cảnh lúc đó nhưng không còn đúng?
- Hệ thống có cơ chế phát hiện hoặc ngăn lỗi độc lập không?
- Tải công việc, quyền hạn hoặc thời gian có ảnh hưởng đến lựa chọn không?

### 7.2. Không xóa bỏ trách nhiệm

Không đổ lỗi không có nghĩa bỏ qua trách nhiệm hoặc hành vi cố ý vi phạm chính sách. Mục tiêu là phân tích nguyên nhân hệ thống một cách công bằng, đồng thời xử lý vấn đề về quyền, quy trình hoặc hành vi theo cơ chế phù hợp. Hai hoạt động cần được phân biệt để điều tra kỹ thuật không biến thành phiên quy kết cá nhân.

### 7.3. Dùng ngôn ngữ trung lập

Mô tả hành động và điều kiện cụ thể:

- Nên viết: “Pipeline không chạy integration suite vì job bị loại khỏi điều kiện trigger sau khi đổi tên thư mục.”
- Tránh viết: “Nhóm QA quên kiểm thử.”

Câu đầu có thể kiểm chứng và dẫn đến thay đổi trigger. Câu sau quy kết nhưng không chỉ ra cách ngăn lặp lại.

## 8. Phân tích nguyên nhân trong các giai đoạn phát triển

### 8.1. Yêu cầu và phân tích nghiệp vụ

Kiểm tra:

- Yêu cầu có mô tả đủ happy path, error path và edge case không?
- Acceptance criteria có đo được và không mâu thuẫn không?
- Quy tắc có phụ thuộc tenant, vai trò, vùng, thời gian hoặc trạng thái không?
- Có bên liên quan hoặc consumer nào chưa được tham vấn không?
- Tài liệu có ghi giả định về retry, thứ tự, tính duy nhất hoặc dữ liệu không?

Hành động có thể gồm bổ sung decision table, state model, ví dụ dữ liệu, review chéo và truy vết yêu cầu đến test.

### 8.2. Thiết kế và kiến trúc

Kiểm tra:

- Có xác định failure mode và dependency không?
- Thiết kế có xử lý timeout, retry, duplicate và partial failure không?
- Có bất biến dữ liệu hoặc transaction boundary rõ không?
- Ranh giới bảo mật và quyền có được xác định không?
- Thiết kế có thể điều khiển và quan sát để kiểm thử không?

Hành động có thể gồm thêm idempotency, constraint, circuit breaker, validation, state transition guard hoặc observability.

### 8.3. Phát triển và code review

Kiểm tra:

- Code có xử lý nhánh và ngoại lệ theo yêu cầu không?
- Có thay đổi dependency hoặc default không được đánh giá không?
- Review có xem xét tác động đến caller/consumer không?
- Có static analysis hoặc rule bảo vệ phù hợp không?
- Test unit có assertion và dữ liệu biên đủ không?

Hành động có thể gồm cải thiện review checklist theo rủi ro, thêm test ở cấp phù hợp, refactor để tăng testability hoặc kiểm soát dependency.

### 8.4. Kiểm thử

Kiểm tra:

- Phạm vi test có bao phủ hành vi và rủi ro đã xác định không?
- Dữ liệu có đại diện và tạo được tình huống gây lỗi không?
- Môi trường có khác production ở điểm quan trọng không?
- Test có bị skip, flaky hoặc không chạy trong pipeline không?
- Assertion có xác minh hậu điều kiện và side effect không?
- Kết quả có được review và có cổng chất lượng phù hợp không?

Hành động có thể gồm thêm regression test, contract test, test data, môi trường đại diện, mutation test hoặc phân tích coverage.

### 8.5. Phát hành và vận hành

Kiểm tra:

- Rollout có đủ nhỏ để phát hiện sớm không?
- Có canary, feature flag và rollback an toàn không?
- Monitoring có đo đúng hành vi nghiệp vụ không?
- Alert có phát hiện lỗi trước khi người dùng chịu tác động lớn không?
- Runbook và owner có rõ không?
- Có đối soát dữ liệu hoặc phát hiện bất thường không?

Hành động có thể gồm canary analysis, synthetic monitoring, business metric, reconciliation job, alert mới và diễn tập rollback.

## 9. Từ nguyên nhân đến hành động khắc phục và phòng ngừa

Phân tích chỉ tạo giá trị khi chuyển thành hành động cụ thể. Cần phân biệt hành động giảm thiểu hiện tại, sửa lỗi trực tiếp và thay đổi giúp ngăn tái diễn.

### 9.1. Containment – khoanh vùng tạm thời

Containment giảm tác động ngay lập tức, ví dụ tắt flag, giới hạn traffic hoặc chuyển giao dịch nghi ngờ sang xử lý thủ công. Đây thường là biện pháp tạm thời và cần có điều kiện gỡ bỏ.

### 9.2. Corrective action – hành động khắc phục

Corrective action xử lý nguyên nhân đã xác định hoặc sửa defect hiện tại. Ví dụ, thêm kiểm tra idempotency để callback lặp không tạo giao dịch mới.

### 9.3. Preventive action – hành động phòng ngừa

Preventive action giảm khả năng lỗi tương tự xuất hiện ở các thành phần hoặc quy trình khác. Ví dụ, chuẩn hóa hợp đồng xử lý webhook cho mọi payment provider, bổ sung review checklist cho retry/idempotency và tạo test pattern dùng chung.

### 9.4. Detection action – hành động tăng khả năng phát hiện

Một số lỗi không thể ngăn hoàn toàn. Có thể bổ sung đối soát, alert, metric, trace hoặc synthetic check để phát hiện sớm và giới hạn thời gian tác động.

### 9.5. Recovery action – hành động phục hồi

Xây dựng khả năng khôi phục dữ liệu, hoàn tiền, replay event hoặc phục hồi trạng thái khi lỗi xảy ra. Phục hồi cần được kiểm tra trong điều kiện an toàn, không chỉ có tài liệu.

## 10. Thiết kế hành động có hiệu quả

Một hành động tốt phải thay đổi điều kiện tạo lỗi hoặc tăng khả năng phát hiện, không chỉ tạo thêm thủ tục.

### 10.1. Mô tả hành động cụ thể

Mỗi hành động nên nêu:

- Vấn đề hoặc nguyên nhân được xử lý.
- Thay đổi cần thực hiện và phạm vi áp dụng.
- Owner chịu trách nhiệm.
- Thời hạn và mức ưu tiên.
- Phụ thuộc hoặc nguồn lực cần thiết.
- Bằng chứng hoàn thành.
- Tiêu chí xác minh hiệu quả.
- Cách duy trì sau khi đóng hành động.

Ví dụ:

> Thêm integration test phát lại cùng một payment callback ba lần với cùng event ID; xác minh chỉ có một capture record và order state không bị cập nhật lặp. Owner: Payment team. Hoàn thành khi test chạy ổn định trên CI và được đưa vào regression suite bắt buộc.

Hành động này rõ hơn “tăng cường kiểm thử thanh toán” vì có điều kiện, kết quả và bằng chứng cụ thể.

### 10.2. Ưu tiên theo rủi ro và sức ảnh hưởng

Ưu tiên hành động dựa trên:

- Mức nghiêm trọng và phạm vi lỗi.
- Khả năng tái diễn.
- Số thành phần hoặc nhóm dùng chung chịu ảnh hưởng.
- Khả năng phát hiện hiện tại.
- Mức độ khó khôi phục.
- Chi phí và thời gian thực hiện.
- Khả năng giảm nhiều rủi ro bằng một thay đổi nền tảng.

Một cải tiến framework dùng chung có thể giảm rủi ro ở nhiều module; một test đơn lẻ có thể xử lý một đường đi cụ thể. Cần cân bằng hành động nền tảng và hành động trực tiếp.

### 10.3. Tránh hành động yếu

Các hành động sau thường không đủ nếu đứng một mình:

- “Nhắc mọi người cẩn thận hơn.”
- “Tăng cường kiểm thử.”
- “Viết thêm tài liệu” mà không có owner hoặc thực hành.
- “Không để lỗi tái diễn” mà không có cơ chế kiểm soát.
- “Thêm một test” nhưng test không tái hiện nguyên nhân hoặc không có assertion.

Có thể bổ sung đào tạo hoặc tài liệu khi thiếu năng lực là yếu tố góp phần, nhưng cần gắn với thay đổi quy trình, công cụ hoặc bằng chứng thực hành.

## 11. Chuyển bài học thành kiểm thử hồi quy

Một lỗi lọt đã được xác nhận nên tạo ra cơ hội cải thiện bộ test. Tuy nhiên, không phải lúc nào cũng chỉ cần thêm một test giống tình huống đã xảy ra.

### 11.1. Tái hiện lỗi

Trước khi sửa, nếu an toàn và có thể, hãy tạo một test hoặc kịch bản tái hiện defect. Kịch bản cần:

- Dữ liệu và trạng thái đầu vào rõ.
- Các bước kích hoạt xác định.
- Kết quả sai có thể quan sát.
- Kết quả mong đợi sau khi sửa.
- Cách chạy độc lập và tái lập.

Test tái hiện giúp xác nhận cơ chế lỗi và chứng minh bản sửa xử lý đúng trường hợp.

### 11.2. Chọn cấp test phù hợp

- Unit test cho logic thuần hoặc điều kiện trực tiếp.
- Component test cho trạng thái và tương tác nội bộ.
- Contract test cho thay đổi schema/API/event.
- Integration test cho transaction, database, queue và dependency.
- E2E test cho hành trình người dùng xuyên hệ thống khi rủi ro nằm ở phối hợp nhiều thành phần.
- Non-functional test cho tải, phục hồi, bảo mật hoặc độ tin cậy.

Chọn cấp thấp nhất có thể kiểm tra nguyên nhân một cách đáng tin cậy, rồi thêm test ranh giới nếu lỗi phụ thuộc tích hợp. Không nên chỉ thêm E2E nếu nguyên nhân có thể được kiểm tra rõ hơn ở cấp component.

### 11.3. Kiểm tra lớp lỗi lân cận

Từ một lỗi callback lặp, có thể mở rộng kiểm tra:

- Callback đến trễ.
- Callback sai thứ tự.
- Retry sau timeout.
- Hai worker xử lý đồng thời cùng event.
- Event được replay sau khi consumer restart.
- Idempotency key hết hạn hoặc thiếu.
- Database commit thành công nhưng acknowledgement thất bại.

Mục tiêu là kiểm tra cùng cơ chế lỗi và các biến thể có liên quan, không phải thêm mọi tổ hợp tưởng tượng.

### 11.4. Đưa test vào pipeline đúng thời điểm

Test hồi quy cần chạy trong pipeline hoặc chu kỳ phù hợp với rủi ro. Nếu test chỉ chạy thủ công trước release, lỗi có thể tái diễn trong nhiều lần merge. Nếu test quá nặng, có thể chạy ở integration/nightly pipeline nhưng cần một kiểm soát nhanh hơn bảo vệ thay đổi.

### 11.5. Xác minh test thực sự phát hiện lỗi

Có thể dùng mutation test hoặc cố ý đưa lại defect trong môi trường cô lập để xác minh test thất bại như mong đợi. Nếu test vẫn Pass khi lỗi được tái tạo, assertion hoặc dữ liệu chưa kiểm tra đúng hành vi.

## 12. Cải thiện các lớp kiểm soát ngoài test

Lỗi lọt thường cần nhiều lớp bảo vệ phối hợp.

### 12.1. Yêu cầu và thiết kế

- Bổ sung trường hợp ngoại lệ và trạng thái.
- Dùng decision table, state machine hoặc sequence diagram khi logic phức tạp.
- Xác định bất biến và hợp đồng dữ liệu.
- Review threat model và failure mode.
- Làm rõ tính idempotent, retry, timeout và thứ tự sự kiện.

### 12.2. Phát triển và review

- Thêm static analysis hoặc rule kiểm tra phù hợp.
- Review theo rủi ro và dependency.
- Dùng code owner cho thành phần trọng yếu nhưng tránh một người thành cổng duy nhất.
- Tăng testability bằng dependency injection, clock abstraction và test seam có kiểm soát.
- Quản lý dependency và cấu hình có version.

### 12.3. Dữ liệu và môi trường

- Bổ sung dữ liệu biên, dữ liệu lỗi và nhóm hiếm.
- Giữ quan hệ và tính toàn vẹn dữ liệu.
- Mô phỏng dependency và có integration test với dependency thật ở phạm vi phù hợp.
- Giảm khác biệt giữa staging và production ở các yếu tố liên quan.
- Version hóa fixture, seed và migration.

### 12.4. Phát hành

- Canary hoặc rollout theo nhóm nhỏ.
- Feature flag và khả năng tắt an toàn.
- Kiểm tra health, smoke và business metric sau triển khai.
- Migration theo expand-and-contract khi cần.
- Rollback hoặc forward-fix có quy trình và đã diễn tập.

### 12.5. Monitoring và phản hồi

- Metric nghiệp vụ như giao dịch trùng, đối soát lệch hoặc tỷ lệ hoàn tất.
- Alert dựa trên ngưỡng và cửa sổ phù hợp.
- Correlation ID, trace và log có cấu trúc.
- Synthetic monitoring cho hành trình quan trọng.
- Kênh phản hồi người dùng và quy trình phân loại ticket.

## 13. Đo hiệu quả của hành động phòng ngừa

Đóng ticket không đồng nghĩa rủi ro đã giảm. Cần xác minh hành động có thay đổi kết quả thực tế hay không.

### 13.1. Chỉ số lỗi lọt

- Số lỗi lọt theo thời gian.
- Tỷ lệ lỗi lọt theo mức nghiêm trọng.
- Tỷ lệ lỗi được phát hiện bởi người dùng so với monitoring.
- Tỷ lệ lỗi tái diễn cùng cơ chế hoặc cùng nguyên nhân.
- Thời gian từ khi lỗi bắt đầu đến khi được phát hiện (MTTD).
- Thời gian từ khi phát hiện đến khi khôi phục (MTTR).

Các chỉ số cần có định nghĩa mẫu số và ranh giới. Ví dụ, số lỗi lọt tuyệt đối có thể tăng khi số release hoặc độ phức tạp sản phẩm tăng. Nên xem cùng số thay đổi, mức độ phơi nhiễm hoặc số giao dịch khi có dữ liệu phù hợp.

### 13.2. Chỉ số về kiểm thử

- Tỷ lệ lỗi được phát hiện trước production.
- Tỷ lệ lỗi có regression test sau khi khắc phục.
- Tỷ lệ test mới được chạy tự động trong pipeline.
- Flaky rate và tỷ lệ test bị skip.
- Thời gian từ defect đến test bảo vệ.
- Tỷ lệ test tái hiện được cơ chế lỗi đã biết.

Không tối ưu bằng cách tăng số test mà không xem chất lượng assertion và khả năng phát hiện. Một test chỉ chạy mã nhưng không thất bại khi defect quay lại không tạo ra kiểm soát hữu ích.

### 13.3. Chỉ số về hành động

- Tỷ lệ hành động hoàn thành đúng hạn.
- Tỷ lệ hành động có bằng chứng hiệu quả.
- Số hành động quá hạn hoặc không có owner.
- Tỷ lệ hành động được áp dụng cho các thành phần liên quan.
- Số incident tái diễn sau khi đóng hành động.

### 13.4. Đánh giá định tính

Retrospective có thể xem xét:

- Nhóm có hiểu rõ hơn về cơ chế lỗi không?
- Quy trình mới có dễ thực hiện và ít phụ thuộc cá nhân hơn không?
- Alert mới có tạo tín hiệu hữu ích hay nhiều false positive?
- Test mới có phát hiện được biến thể của lỗi không?
- Hành động có tạo gánh nặng vận hành lớn hơn lợi ích không?

### 13.5. Đo trước và sau

Đặt đường cơ sở trước khi triển khai hành động nếu có thể. Sau đó theo dõi trong khoảng thời gian đủ đại diện. Với lỗi hiếm, không thấy lỗi tái diễn trong vài ngày chưa chứng minh biện pháp hiệu quả. Có thể dùng kiểm thử có chủ đích, diễn tập hoặc fault injection để xác minh kiểm soát mới hoạt động.

## 14. Quản lý hành động và theo dõi sau incident

Một bảng hành động cần giúp nhóm biết việc gì phải làm, ai chịu trách nhiệm và bằng chứng nào xác nhận hiệu quả.

| Trường | Nội dung |
|---|---|
| Action ID | Mã định danh hành động. |
| Nguyên nhân/khoảng trống | Yếu tố hoặc lớp kiểm soát được xử lý. |
| Hành động | Thay đổi cụ thể, có thể kiểm chứng. |
| Loại | Containment, corrective, preventive, detection hoặc recovery. |
| Phạm vi | Service, module, quy trình hoặc nhóm liên quan. |
| Owner | Người chịu trách nhiệm hoàn thành. |
| Due date | Thời hạn và mốc kiểm tra. |
| Priority | Mức ưu tiên theo rủi ro. |
| Evidence | PR, test report, dashboard, diễn tập hoặc tài liệu. |
| Effectiveness criteria | Điều kiện chứng minh rủi ro đã giảm. |
| Status | Open, in progress, blocked, completed hoặc verified. |
| Review date | Ngày xem xét lại hiệu quả. |

### 14.1. Phân biệt hoàn thành và xác minh hiệu quả

- **Completed**: thay đổi đã được thực hiện và có bằng chứng triển khai.
- **Verified**: đã kiểm tra rằng thay đổi tạo ra kết quả mong đợi hoặc giảm rủi ro theo tiêu chí.

Ví dụ, PR thêm test đã merge là completed. Khi test chạy trong CI, thất bại khi tái tạo defect và bảo vệ đúng hành vi qua các lần chạy, hành động mới có bằng chứng verified.

### 14.2. Quản lý hành động bị chặn

Nếu hành động phụ thuộc vào nền tảng, vendor hoặc nguồn lực khác, ghi rõ blocker, rủi ro tạm thời và biện pháp giảm thiểu. Không đóng hành động chỉ vì đã tạo ticket cho nhóm khác.

### 14.3. Chia sẻ bài học có chọn lọc

Chia sẻ kết luận và biện pháp với các nhóm có cùng dependency hoặc kiểu rủi ro. Loại bỏ thông tin nhạy cảm, dữ liệu cá nhân và secret khỏi tài liệu phổ biến. Bài học nên mô tả cơ chế và kiểm soát, không chỉ kể lại sự kiện.

## 15. Ví dụ xuyên suốt: lỗi thanh toán bị ghi nhận hai lần

Giả sử sau một release, một số đơn hàng bị ghi nhận hai giao dịch capture. Provider gửi lại callback sau khi không nhận được acknowledgement đúng hạn. Payment adapter xử lý mỗi callback như một giao dịch mới.

### 15.1. Tác động và containment

- Đối soát phát hiện hai capture cho cùng một payment reference.
- Nhóm dừng rollout adapter mới và chuyển giao dịch nghi ngờ sang hàng đợi kiểm tra.
- Các giao dịch bị ảnh hưởng được xác định bằng provider reference, order ID và thời gian.
- Bộ phận vận hành xử lý hoàn tiền hoặc điều chỉnh theo quy trình được phê duyệt.

### 15.2. Nguyên nhân và yếu tố góp phần

**Cơ chế lỗi đã xác minh:** callback lặp được xử lý như callback mới vì handler không kiểm tra idempotency theo event/payment reference trước khi ghi capture.

**Yếu tố góp phần:**

- Thiết kế giả định provider chỉ gửi một callback.
- Acceptance criteria không nêu delivery có thể lặp.
- Integration test chỉ gửi một callback thành công.
- Sandbox test không có kịch bản retry hoặc acknowledgement chậm.
- Monitoring theo dõi HTTP success nhưng không đối soát số capture trên mỗi payment.
- Rollout ban đầu không có canary metric cho giao dịch trùng.

### 15.3. Hành động

| Loại | Hành động | Bằng chứng hiệu quả |
|---|---|---|
| Corrective | Thêm idempotency key và unique constraint phù hợp cho capture | Callback cùng event ID gửi nhiều lần chỉ tạo một capture. |
| Preventive | Cập nhật contract và checklist cho mọi webhook consumer | Review xác nhận retry, duplicate và thứ tự được xem xét. |
| Regression | Thêm integration test callback lặp, trễ và đồng thời | Test thất bại khi bỏ cơ chế idempotency và Pass sau khi sửa. |
| Detection | Thêm metric/alert về số capture trên mỗi payment reference | Alert phát hiện bất thường trước khi phạm vi mở rộng. |
| Recovery | Xây dựng đối soát và quy trình xử lý giao dịch trùng | Diễn tập xác định, khoanh vùng và khôi phục được dữ liệu. |
| Release | Canary theo tỷ lệ giao dịch và kiểm tra business metric | Rollout dừng khi metric vượt ngưỡng đã phê duyệt. |

### 15.4. Xác minh sau cải tiến

Nhóm chạy test với callback lặp, callback đến trễ, hai worker xử lý đồng thời và retry sau timeout. Sau đó diễn tập trên staging với dữ liệu tổng hợp, kiểm tra unique constraint, audit, alert và quy trình đối soát. Khi triển khai, nhóm theo dõi metric theo từng giai đoạn rollout.

Chỉ đóng incident action khi có bằng chứng test và vận hành phù hợp. Việc thêm một dòng kiểm tra trong code hoặc ghi chú vào tài liệu chưa đủ để kết luận rủi ro đã được kiểm soát.

## 16. Những sai lầm thường gặp

- **Tìm một cá nhân để quy trách nhiệm**: làm mất thông tin về điều kiện hệ thống. Hãy phân tích quyết định và kiểm soát trong bối cảnh thực tế.
- **Dừng ở triệu chứng**: chỉ sửa dữ liệu sai mà không xử lý cơ chế tạo lỗi. Hãy xác định defect và điều kiện tái diễn.
- **Dừng ở một câu trả lời “vì sao”**: incident có thể có nhiều yếu tố góp phần. Hãy dùng timeline, fishbone hoặc fault tree khi cần.
- **Coi giả thuyết là sự thật**: kết luận thiếu bằng chứng. Hãy ghi rõ điều đã xác minh và điều chưa biết.
- **Chỉ thêm test**: bỏ qua thiết kế, cấu hình, release và monitoring. Hãy chọn hành động theo khoảng trống thực tế.
- **Thêm test nhưng assertion yếu**: test chạy nhưng không phát hiện defect. Hãy tái hiện lỗi và chứng minh test thất bại khi lỗi tồn tại.
- **Chỉ sửa riêng một service**: cùng cơ chế có thể tồn tại ở consumer khác. Hãy xem xét phạm vi tái sử dụng và dependency.
- **Đóng action khi PR merge**: chưa chứng minh hiệu quả. Hãy xác định tiêu chí verified và kiểm tra sau triển khai.
- **Đặt hành động chung chung**: không có owner hoặc kết quả đo. Hãy mô tả thay đổi, deadline và evidence.
- **Không bảo toàn bằng chứng**: mất dữ liệu để điều tra hoặc đối soát. Hãy lưu log, trace và artifact theo chính sách.
- **Bỏ qua near miss**: mất cơ hội sửa trước khi có hậu quả. Hãy ghi nhận và xử lý tín hiệu suýt xảy ra sự cố.
- **Không cập nhật bài học dùng chung**: lỗi tương tự lặp ở module khác. Hãy chia sẻ theo dependency và rủi ro liên quan.
- **Đóng incident quá sớm**: dịch vụ đã khôi phục nhưng tác động dữ liệu và action còn mở. Hãy tách trạng thái khôi phục khỏi trạng thái học hỏi/khắc phục.

## 17. Quy trình phân tích nguyên nhân và phòng ngừa lỗi lọt

Nhóm có thể áp dụng trình tự sau:

1. **Bảo vệ người dùng và dữ liệu**: đánh giá tác động, khoanh vùng, khôi phục và bảo toàn bằng chứng.
2. **Xác định ranh giới lỗi lọt**: ghi nhận lỗi được phát hiện ở giai đoạn nào và theo định nghĩa của tổ chức.
3. **Tái dựng timeline**: nối yêu cầu, code, test, release, telemetry và phản hồi người dùng.
4. **Xác minh cơ chế lỗi**: tái hiện hoặc kiểm tra dữ liệu để xác định điều kiện tạo failure.
5. **Phân tích lớp kiểm soát**: xác định vì sao yêu cầu, review, test, release hoặc monitoring không ngăn/phát hiện lỗi.
6. **Tìm yếu tố góp phần**: dùng Five Whys, fishbone, fault tree hoặc change analysis theo độ phức tạp.
7. **Đề xuất hành động**: kết hợp containment, corrective, preventive, detection và recovery khi phù hợp.
8. **Chuyển bài học thành kiểm thử**: tạo test tái hiện, mở rộng biến thể liên quan và đưa vào pipeline phù hợp.
9. **Giao owner và tiêu chí hiệu quả**: xác định deadline, evidence và điều kiện verified.
10. **Theo dõi và chia sẻ**: đánh giá xu hướng, kiểm tra tái diễn và áp dụng bài học cho thành phần có cùng rủi ro.

## 18. Tự kiểm tra

Trước khi kết thúc phân tích một lỗi lọt, hãy tự hỏi:

- Tác động, phạm vi và ranh giới phát hiện đã được xác định chưa?
- Dịch vụ và dữ liệu đã được bảo vệ, khôi phục và đối soát chưa?
- Timeline có dựa trên nguồn bằng chứng và timezone thống nhất không?
- Đã phân biệt dữ kiện, giả thuyết và điều chưa biết chưa?
- Cơ chế tạo lỗi đã được xác minh chưa?
- Đã phân tích cả lý do lỗi được tạo ra và lý do các lớp kiểm soát không phát hiện chưa?
- Có xem xét yêu cầu, thiết kế, code, test, dữ liệu, cấu hình, release và monitoring không?
- Phân tích có tránh quy kết cá nhân và vẫn giữ trách nhiệm rõ ràng không?
- Hành động có cụ thể, có owner, deadline và bằng chứng hiệu quả không?
- Test mới có tái hiện defect và thất bại khi lỗi quay lại không?
- Các thành phần khác có cùng cơ chế rủi ro đã được xem xét chưa?
- Hành động đã được xác minh hiệu quả hay mới chỉ hoàn thành về mặt triển khai?
- Bài học và dữ liệu nhạy cảm được chia sẻ theo đúng quyền và chính sách không?

## Kết luận

Phân tích nguyên nhân lỗi lọt cần đi từ tác động và bằng chứng đến cơ chế lỗi, khoảng trống kiểm soát và hành động có thể kiểm chứng. Nhóm cần phân biệt vì sao defect được tạo ra với vì sao nó vượt qua các lớp kiểm soát, tái dựng timeline, xem xét các yếu tố kỹ thuật và tổ chức, rồi chọn biện pháp khắc phục, phòng ngừa, phát hiện và phục hồi phù hợp. Bài học chỉ thực sự được áp dụng khi test hồi quy có thể tái hiện lỗi, các kiểm soát liên quan được cập nhật, owner xác minh hiệu quả và các thành phần có cùng rủi ro được xem xét. Cách tiếp cận không đổ lỗi nhưng dựa trên bằng chứng giúp tổ chức giảm lỗi tái diễn và cải thiện liên tục chiến lược kiểm thử.
