# Xác định tiêu chí hoàn tất gắn với mục tiêu và rủi ro

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), một hạng mục chỉ nên được xem là hoàn tất khi nhóm có đủ bằng chứng cho thấy mục tiêu đã đạt và các rủi ro quan trọng đã được xử lý hoặc được chấp nhận đúng thẩm quyền. Nếu tiêu chí hoàn tất chỉ là “test pass”, “không còn bug” hoặc “đã review”, nhóm có thể bỏ qua những điều quan trọng như phạm vi chưa được kiểm tra, mức độ nghiêm trọng của lỗi còn mở, độ tin cậy của môi trường và tác động đối với người dùng.

Tiêu chí hoàn tất cần nối được bốn yếu tố: **mục tiêu cần đạt, rủi ro cần kiểm soát, bằng chứng cần thu thập và điều kiện ra quyết định**. Cách tiếp cận này giúp nhóm xác định rõ khi nào một story, thay đổi, tính năng hoặc bản phát hành đủ điều kiện chuyển sang bước tiếp theo; đồng thời làm minh bạch phần chưa được xác minh và rủi ro còn lại.

Bài học này trình bày cách chuyển mục tiêu và rủi ro thành tiêu chí có thể kiểm chứng, xác định ngưỡng đạt, lựa chọn bằng chứng, xử lý ngoại lệ, phân định trách nhiệm và áp dụng tiêu chí ở các cấp độ công việc.

## 1. Tiêu chí hoàn tất là gì?

### 1.1. Tiêu chí hoàn tất mô tả trạng thái cần đạt

Tiêu chí hoàn tất (*completion criteria*) là tập hợp điều kiện được thống nhất để xác định một hạng mục hoặc một mốc công việc đã đạt trạng thái yêu cầu. Mỗi điều kiện cần có cách xác minh và bằng chứng phù hợp.

Ví dụ, với một thay đổi cho phép người dùng cập nhật địa chỉ giao hàng, tiêu chí hoàn tất có thể yêu cầu:

- Người dùng được phép cập nhật địa chỉ của đơn hàng thuộc quyền sở hữu.
- Người dùng không thể cập nhật đơn hàng của tài khoản khác.
- Địa chỉ mới được lưu và đọc lại chính xác.
- Hệ thống từ chối dữ liệu không hợp lệ theo hợp đồng.
- Các kiểm thử hồi quy quan trọng đạt.
- Không còn lỗi nghiêm trọng chưa được xử lý hoặc chấp nhận theo quy trình.
- Tài liệu và thông tin vận hành bị ảnh hưởng đã được cập nhật.

Các điều kiện này cụ thể hơn câu “chức năng hoạt động tốt” vì người thực hiện và người review có thể xác định bằng chứng nào chứng minh từng điều kiện.

### 1.2. Phân biệt mục tiêu, tiêu chí và bằng chứng

Ba khái niệm có quan hệ nhưng không thay thế nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Mục tiêu | Kết quả cần đạt hoặc rủi ro cần giảm. | Chỉ chủ đơn hàng mới được sửa địa chỉ giao hàng. |
| Tiêu chí hoàn tất | Điều kiện cụ thể để xác nhận mục tiêu đã đạt. | Request từ tài khoản khác bị từ chối và dữ liệu đơn hàng không thay đổi. |
| Bằng chứng | Thông tin cho thấy tiêu chí đã được kiểm tra và đạt. | API test với hai tài khoản, response bị từ chối và trạng thái đơn được đọc lại. |

Một mục tiêu có thể cần nhiều tiêu chí. Một tiêu chí có thể cần nhiều nguồn bằng chứng. Không nên coi việc có test case là bằng chứng rằng mục tiêu đã đạt; cần xem kết quả thực tế và điều kiện thực thi.

### 1.3. Phân biệt tiêu chí hoàn tất với Definition of Done và Acceptance Criteria

Các khái niệm này có thể được dùng cùng nhau:

- **Acceptance Criteria (tiêu chí chấp nhận):** mô tả hành vi hoặc kết quả riêng mà một hạng mục cần đáp ứng từ góc độ nghiệp vụ.
- **Definition of Done (DoD):** thỏa thuận chung về tiêu chuẩn chất lượng áp dụng cho các hạng mục trước khi được coi là hoàn tất.
- **Completion Criteria:** điều kiện để kết luận một hạng mục hoặc một mốc cụ thể đã hoàn tất; có thể kết hợp tiêu chí chấp nhận, DoD, mục tiêu chất lượng và yêu cầu theo rủi ro.

Ví dụ, tiêu chí chấp nhận của chức năng đổi mật khẩu mô tả quy tắc mật khẩu mới và phản hồi khi mật khẩu hiện tại sai. DoD yêu cầu review, kiểm thử liên quan và tài liệu được cập nhật. Tiêu chí hoàn tất của một release có thể bổ sung yêu cầu về kiểm thử bảo mật, tỷ lệ lỗi, giám sát và phương án rollback.

### 1.4. Tiêu chí cần phù hợp với cấp độ quyết định

Không nên dùng cùng một danh sách cho mọi cấp:

| Cấp độ | Câu hỏi cần trả lời | Ví dụ điều kiện |
|---|---|---|
| Task hoặc thay đổi mã | Phần việc kỹ thuật đã được thực hiện và kiểm tra chưa? | Code review, unit test, lint và phân tích tĩnh đạt. |
| Story hoặc yêu cầu | Hành vi người dùng và tiêu chí chấp nhận đã đạt chưa? | Luồng thành công, lỗi và quyền truy cập được xác minh. |
| Tính năng hoặc hệ thống | Các thành phần phối hợp và rủi ro xuyên hệ thống đã được kiểm tra chưa? | Integration test, contract test và E2E đại diện đạt. |
| Release | Bản phát hành có đủ bằng chứng để triển khai không? | Full regression, bảo mật, hiệu năng, migration, giám sát và rollback được xem xét. |
| Vận hành sau triển khai | Hệ thống thực tế có hoạt động trong ngưỡng chấp nhận không? | Smoke test, health, error rate và chỉ số nghiệp vụ đạt. |

Hoàn tất ở cấp story không tự động đồng nghĩa với sẵn sàng phát hành. Tiêu chí phải nêu rõ quyết định đang được đưa ra ở cấp nào.

## 2. Bắt đầu từ mục tiêu cần đạt

### 2.1. Mô tả mục tiêu bằng kết quả có ý nghĩa

Mục tiêu nên mô tả thay đổi có giá trị với người dùng, hệ thống hoặc hoạt động kinh doanh. Tránh dùng hoạt động như “viết test”, “thêm endpoint” hoặc “cập nhật tài liệu” làm mục tiêu cuối cùng nếu chưa nêu kết quả cần đạt.

Ví dụ:

- Mục tiêu chưa rõ: “Thêm kiểm tra phân quyền.”
- Mục tiêu rõ hơn: “Người dùng chỉ có thể đọc và cập nhật tài nguyên thuộc phạm vi quyền của mình.”
- Mục tiêu chưa rõ: “Cải thiện hiệu năng tìm kiếm.”
- Mục tiêu rõ hơn: “Với tải và dữ liệu đã thống nhất, thời gian phản hồi phân vị 95 của truy vấn tìm kiếm không vượt ngưỡng đã xác định.”
- Mục tiêu chưa rõ: “Tăng độ ổn định thanh toán.”
- Mục tiêu rõ hơn: “Yêu cầu thanh toán lặp không tạo giao dịch trùng và trạng thái đơn hàng có thể được khôi phục sau timeout.”

Mục tiêu rõ giúp nhóm chọn đúng loại kiểm thử và ngưỡng đánh giá.

### 2.2. Xác định người dùng và ngữ cảnh

Một kết quả có thể đúng với vai trò này nhưng sai với vai trò khác. Hãy xác định:

- Người dùng hoặc hệ thống hưởng lợi.
- Vai trò, quyền và trạng thái tài khoản.
- Điều kiện ban đầu.
- Dữ liệu và môi trường liên quan.
- Hành vi thành công và thất bại.
- Các giới hạn hoặc giả định quan trọng.

Ví dụ, “người dùng xem được đơn hàng” cần làm rõ người dùng là chủ đơn, nhân viên hỗ trợ hay quản trị viên; đơn đang ở trạng thái nào; dữ liệu nào được phép hiển thị; và hành vi khi đơn không thuộc quyền truy cập.

### 2.3. Phân rã mục tiêu thành kết quả quan sát được

Một mục tiêu lớn thường cần được chia thành các kết quả nhỏ có thể xác minh.

Ví dụ mục tiêu “người dùng thanh toán đơn hàng an toàn” có thể phân rã thành:

1. Tổng tiền được tính theo quy tắc hiện hành.
2. Chỉ người có quyền mới có thể thanh toán đơn.
3. Request gửi nhà cung cấp có số tiền và đơn vị tiền tệ chính xác.
4. Callback được xác minh trước khi cập nhật trạng thái.
5. Callback lặp không tạo giao dịch trùng.
6. Trạng thái đơn và giao dịch được lưu nhất quán.
7. Người dùng nhìn thấy kết quả phù hợp với trạng thái thực tế.
8. Lỗi hoặc timeout có thể được phát hiện và xử lý.

Mỗi kết quả có thể cần tiêu chí riêng ở các tầng kiểm thử khác nhau.

## 3. Xác định rủi ro gắn với mục tiêu

### 3.1. Rủi ro là khả năng mục tiêu không đạt và hậu quả đi kèm

Rủi ro không chỉ là khả năng xuất hiện lỗi. Cần xem xét hậu quả nếu lỗi xảy ra, khả năng phát hiện và phạm vi ảnh hưởng.

Các khía cạnh thường dùng:

- **Tác động đến người dùng:** mất chức năng, dữ liệu sai, trải nghiệm bị gián đoạn.
- **Tác động tài chính:** giao dịch trùng, tính phí sai, mất doanh thu.
- **Bảo mật và quyền riêng tư:** lộ dữ liệu, truy cập trái phép hoặc nâng quyền.
- **Toàn vẹn dữ liệu:** ghi sai, mất dữ liệu hoặc trạng thái không nhất quán.
- **Vận hành:** gián đoạn dịch vụ, khó phục hồi hoặc thiếu khả năng quan sát.
- **Tuân thủ và hợp đồng:** vi phạm nghĩa vụ pháp lý hoặc cam kết dịch vụ.
- **Phạm vi lan rộng:** số người dùng, tenant, service hoặc quy trình bị ảnh hưởng.

### 3.2. Xác định tình huống gây rủi ro

Với từng mục tiêu, hãy hỏi:

- Điều gì có thể khiến mục tiêu không đạt?
- Thành phần hoặc ranh giới nào dễ phát sinh lỗi?
- Có dữ liệu, vai trò hoặc trạng thái nào làm thay đổi kết quả?
- Nếu một dependency chậm hoặc không sẵn sàng thì điều gì xảy ra?
- Lỗi có thể bị che giấu bởi retry, cache hoặc trạng thái cũ không?
- Có thể phát hiện lỗi trước khi người dùng bị ảnh hưởng không?

Ví dụ, mục tiêu “callback thanh toán chỉ được xử lý một lần” có các tình huống rủi ro như callback gửi lặp, đến sai thứ tự, chữ ký sai, service restart giữa giao dịch hoặc hai worker xử lý đồng thời.

### 3.3. Ưu tiên theo khả năng và tác động

Có thể sử dụng thang định tính:

| Mức | Khả năng | Tác động |
|---|---|---|
| Thấp | Khó xảy ra hoặc có nhiều kiểm soát hiệu quả. | Ảnh hưởng nhỏ, dễ khôi phục. |
| Trung bình | Có điều kiện thực tế để xảy ra. | Ảnh hưởng một nhóm chức năng hoặc người dùng. |
| Cao | Điểm vào phổ biến, thay đổi thường xuyên hoặc kiểm soát còn yếu. | Có thể ảnh hưởng dữ liệu, giao dịch hoặc nhiều người dùng. |
| Rất cao | Dấu hiệu xảy ra rõ, dễ khai thác hoặc đã có sự cố. | Có thể gây mất dữ liệu, thiệt hại tài chính, lộ thông tin hoặc gián đoạn diện rộng. |

Một cách định hướng đơn giản là kết hợp khả năng xảy ra và tác động. Tuy nhiên, không nên phụ thuộc hoàn toàn vào điểm số. Rủi ro có xác suất thấp nhưng hậu quả nghiêm trọng vẫn có thể cần tiêu chí bắt buộc.

### 3.4. Xem xét rủi ro còn lại sau kiểm soát

Rủi ro ban đầu có thể giảm sau khi áp dụng kiểm soát, nhưng hiếm khi biến mất hoàn toàn. Ví dụ, retry và idempotency giảm nguy cơ giao dịch trùng nhưng vẫn có thể còn rủi ro khi database mất kết nối trong một khoảng thời gian cụ thể.

Tiêu chí hoàn tất cần chỉ ra:

- Rủi ro nào đã được kiểm tra và có bằng chứng.
- Rủi ro nào đã được giảm bằng thiết kế hoặc kiểm soát.
- Rủi ro nào chưa được kiểm tra.
- Rủi ro nào được chấp nhận có điều kiện.
- Ai có thẩm quyền chấp nhận và khi nào cần xem xét lại.

Không được coi rủi ro chưa kiểm tra là rủi ro đã được kiểm soát.

## 4. Chuyển mục tiêu và rủi ro thành tiêu chí có thể kiểm chứng

### 4.1. Mỗi tiêu chí cần có điều kiện và kết quả rõ

Một tiêu chí tốt nên xác định:

- Điều kiện ban đầu hoặc ngữ cảnh.
- Hành động hoặc sự kiện cần kiểm tra.
- Kết quả mong đợi.
- Ngưỡng đạt nếu là chỉ số định lượng.
- Phạm vi áp dụng.
- Bằng chứng cần lưu.
- Cách xử lý khi không đạt.

Ví dụ:

“Với người dùng A đã xác thực và đơn hàng thuộc tài khoản B, khi A gọi API đọc chi tiết đơn, hệ thống trả phản hồi từ chối theo hợp đồng, không trả dữ liệu đơn và không tạo tác dụng phụ.”

Tiêu chí này xác định vai trò, dữ liệu, hành động và kết quả. Nó cũng bảo vệ rủi ro truy cập chéo tài khoản.

### 4.2. Dùng tiêu chí định lượng khi mục tiêu có thể đo

Một số mục tiêu cần ngưỡng cụ thể:

- Thời gian phản hồi.
- Tỷ lệ lỗi.
- Tỷ lệ xử lý thành công.
- Số lượng yêu cầu đồng thời.
- Mức sử dụng CPU, memory hoặc dung lượng.
- Tỷ lệ dữ liệu được đối soát.
- Thời gian phục hồi hoặc khôi phục.

Ví dụ, “API nhanh” không thể được xác nhận nhất quán. Có thể định nghĩa: “Ở mức tải 200 request/giây trong 15 phút với tập dữ liệu đại diện, p95 latency không vượt 400 ms và tỷ lệ lỗi không vượt 0,5%.” Các con số cần xuất phát từ yêu cầu sản phẩm, SLO hoặc quyết định kỹ thuật đã thống nhất; không tự đặt ngưỡng tùy tiện.

### 4.3. Dùng tiêu chí định tính có cấu trúc khi khó đo trực tiếp

Không phải mọi mục tiêu đều có thể biểu diễn bằng một con số. Ví dụ, khả năng sử dụng, khả năng đọc hiểu thông báo hoặc mức độ dễ vận hành có thể cần đánh giá theo checklist hoặc tiêu chuẩn.

Một tiêu chí định tính vẫn cần:

- Phạm vi đánh giá.
- Người hoặc vai trò đánh giá.
- Tiêu chuẩn hoặc rubric.
- Bằng chứng quan sát.
- Kết quả đạt/chưa đạt và lý do.

Ví dụ: “Thông báo lỗi xác định trường cần sửa, dùng ngôn ngữ phù hợp và không làm mất dữ liệu người dùng đã nhập.” Có thể đánh giá bằng test UI, review nội dung và các kịch bản lỗi đã xác định.

### 4.4. Tiêu chí phải phân biệt pass, fail và chưa đủ bằng chứng

Các trạng thái nên được phân biệt:

- **PASS:** bằng chứng đáp ứng tiêu chí.
- **FAIL:** bằng chứng cho thấy tiêu chí không đạt.
- **BLOCKED:** chưa thể kiểm tra do môi trường, quyền hoặc phụ thuộc.
- **NOT RUN:** chưa thực thi.
- **NOT APPLICABLE:** không áp dụng, có lý do và người xác nhận.
- **WAIVED:** được miễn có phê duyệt và ghi nhận rủi ro.

Không nên gộp BLOCKED, NOT RUN hoặc WAIVED vào PASS. Chúng thể hiện mức độ bằng chứng khác nhau và có thể ảnh hưởng đến quyết định hoàn tất.

## 5. Chọn bằng chứng phù hợp với từng tiêu chí

### 5.1. Không có một tầng kiểm thử bao phủ mọi rủi ro

Chọn tầng dựa trên nơi rủi ro phát sinh:

| Loại mục tiêu hoặc rủi ro | Bằng chứng phù hợp |
|---|---|
| Quy tắc tính toán hoặc validation cục bộ | Unit test, property-based test và review logic. |
| Hợp đồng request/response hoặc event | Contract test và API test. |
| Persistence, transaction và migration | Integration test với database tương thích. |
| Giao tiếp giữa service | Integration test với dependency thật hoặc sandbox. |
| Hành trình người dùng quan trọng | UI/E2E test đại diện. |
| Hiệu năng và tải | Load test, stress test và metrics trên môi trường đại diện. |
| Bảo mật và phân quyền | Security test, API authorization test, SAST/DAST và review. |
| Khả năng phục hồi | Fault injection có kiểm soát, recovery test và diễn tập. |
| Khả năng vận hành | Smoke test, health check, log, metrics, alert và runbook review. |

Nếu dùng mock hoặc stub, cần ghi rõ phần nào được mô phỏng. Một mock thành công không chứng minh dependency thật hoạt động.

### 5.2. Xác định bằng chứng tối thiểu đủ mạnh

Bằng chứng cần đủ để đưa ra kết luận nhưng không cần lặp lại mọi kiểm tra ở mọi tầng. Ví dụ:

- Unit test bao phủ các giá trị biên của công thức.
- Integration test xác minh kết quả được lưu đúng.
- Một E2E test đại diện xác minh hành trình người dùng.

Không cần chạy toàn bộ tổ hợp giá trị biên qua E2E nếu unit test và integration test đã cung cấp bằng chứng phù hợp cho các rủi ro tương ứng.

### 5.3. Đánh giá chất lượng bằng chứng

Bằng chứng chỉ có giá trị khi có thể tin cậy và truy vết. Cần xem xét:

- Test có thực sự chạy trên phiên bản đang đánh giá không?
- Môi trường có đủ đại diện cho rủi ro không?
- Dữ liệu và vai trò có đúng điều kiện không?
- Assertion có kiểm tra hành vi thực hay chi tiết triển khai?
- Kết quả có thể tái lập và chẩn đoán không?
- Test có flaky hoặc bị retry che giấu thất bại không?
- Log, trace, screenshot hoặc báo cáo có gắn với đúng run không?
- Có phần nào bị skip hoặc mô phỏng mà chưa ghi nhận không?

Một báo cáo xanh từ môi trường sai phiên bản không phải bằng chứng đủ mạnh cho release hiện tại.

### 5.4. Liên kết tiêu chí với nguồn yêu cầu

Mỗi tiêu chí cần truy vết về mục tiêu, yêu cầu, rủi ro hoặc chính sách tương ứng. Có thể dùng ID để liên kết:

- Objective ID.
- Risk ID.
- Requirement hoặc acceptance criterion.
- Test case hoặc suite.
- Build, commit và environment ID.
- Kết quả và bằng chứng.

Truy vết giúp xác định test nào cần chạy khi yêu cầu thay đổi và rủi ro nào chưa có bằng chứng.

## 6. Xác định ngưỡng chất lượng và điều kiện chặn

### 6.1. Phân biệt ngưỡng bắt buộc và mục tiêu cải tiến

Không phải mọi chỉ số đều phải là cổng chặn. Có thể phân loại:

- **Hard gate:** điều kiện bắt buộc; không đạt thì không được chuyển bước nếu không có ngoại lệ đúng thẩm quyền.
- **Soft threshold:** tín hiệu cần xem xét và có thể yêu cầu hành động tùy bối cảnh.
- **Target:** mục tiêu cải tiến theo thời gian, không nhất thiết chặn từng lần phát hành.
- **Observation:** chỉ số được theo dõi để phát hiện xu hướng.

Ví dụ, không còn lỗi bảo mật mức nghiêm trọng chưa được xử lý có thể là hard gate. Thời gian chạy test suite giảm 10% có thể là target. Tỷ lệ flaky có thể là soft threshold kèm yêu cầu điều tra khi vượt ngưỡng.

### 6.2. Đặt ngưỡng dựa trên yêu cầu và dữ liệu

Ngưỡng cần được xác định từ:

- SLO/SLA hoặc cam kết với người dùng.
- Mức rủi ro được chấp nhận.
- Dữ liệu vận hành và lịch sử hiệu năng.
- Quy định hoặc tiêu chuẩn nội bộ.
- Khả năng kỹ thuật và giới hạn môi trường.
- Chi phí khi đạt hoặc không đạt.

Không nên chọn ngưỡng chỉ vì công cụ mặc định hoặc vì con số dễ đạt. Nếu chưa có dữ liệu, có thể đặt ngưỡng tạm thời, ghi rõ giả định và thời điểm đánh giá lại.

### 6.3. Tránh chỉ số dễ bị thao túng

Một số chỉ số có thể tạo hành vi không mong muốn nếu được dùng đơn độc:

- Tỷ lệ test pass cao có thể đạt được bằng cách bỏ qua test thất bại.
- Code coverage cao không chứng minh assertion có ý nghĩa.
- Số bug thấp có thể do khám phá không đủ.
- Thời gian pipeline thấp có thể do loại bỏ test quan trọng.
- Không có lỗi production trong thời gian ngắn không chứng minh rủi ro thấp.

Hãy kết hợp nhiều tín hiệu và kiểm tra cách tính chỉ số. Ghi rõ mẫu số, phạm vi, thời gian và các test bị loại trừ.

### 6.4. Xác định tiêu chí chặn theo mức độ nghiêm trọng

Có thể định nghĩa chính sách:

- Lỗi critical hoặc high ảnh hưởng dữ liệu, tiền, quyền truy cập hoặc an toàn phải chặn cho đến khi được sửa hoặc có quyết định đúng thẩm quyền.
- Lỗi medium cần đánh giá tác động, phạm vi và biện pháp giảm thiểu.
- Lỗi low có thể được ghi nhận và lên kế hoạch xử lý nếu không vi phạm tiêu chuẩn bắt buộc.
- Test bắt buộc chưa chạy hoặc môi trường không đáng tin phải được xem xét như khoảng trống bằng chứng, không phải pass.

Phân loại mức độ cần dựa trên chính sách của tổ chức và hậu quả thực tế. Không dùng severity như một cách để hạ thấp lỗi nhằm đạt điều kiện phát hành.

## 7. Gắn tiêu chí hoàn tất với rủi ro theo quy trình

Có thể sử dụng quy trình sau cho một story, tính năng hoặc release.

### Bước 1: Xác định mục tiêu và cấp độ quyết định

Ghi rõ kết quả cần đạt và đang quyết định hoàn tất ở cấp task, story, tính năng hay release.

### Bước 2: Liệt kê rủi ro liên quan

Xác định tình huống có thể làm mục tiêu không đạt, hậu quả, khả năng xảy ra và phạm vi ảnh hưởng.

### Bước 3: Chọn rủi ro cần kiểm soát trước khi hoàn tất

Ưu tiên rủi ro có tác động cao, có khả năng xảy ra, khó phát hiện hoặc liên quan đến nghĩa vụ bắt buộc. Ghi rõ rủi ro nào không nằm trong phạm vi và lý do.

### Bước 4: Chuyển từng mục tiêu và rủi ro thành tiêu chí

Viết điều kiện có thể quan sát, ngưỡng nếu cần, phạm vi áp dụng và trạng thái khi không đạt.

### Bước 5: Chọn phương pháp và bằng chứng

Xác định test layer, review, kiểm tra vận hành hoặc nguồn bằng chứng khác. Ghi môi trường, dữ liệu, vai trò và phiên bản.

### Bước 6: Xác định gate và người quyết định

Phân loại điều kiện bắt buộc, mục tiêu và cảnh báo. Nêu ai xác nhận kết quả và ai có quyền chấp nhận ngoại lệ.

### Bước 7: Thực thi và đánh giá bằng chứng

Chạy kiểm tra, xem xét kết quả, phân loại failure và xác minh test có đủ tin cậy không. Không kết luận đạt chỉ dựa trên trạng thái pipeline nếu thiếu bằng chứng cần thiết.

### Bước 8: Ghi rủi ro còn lại và quyết định

Nếu có khoảng trống, ghi tác động, biện pháp giảm thiểu, owner, thời hạn và người chấp nhận. Quyết định hoàn tất phải phản ánh đúng mức bằng chứng hiện có.

### Bước 9: Cập nhật khi mục tiêu hoặc rủi ro thay đổi

Nếu yêu cầu, kiến trúc, dữ liệu hoặc môi trường thay đổi, xem xét lại tiêu chí và test liên quan. Không tiếp tục dùng tiêu chí cũ nếu nó không còn bảo vệ mục tiêu hiện tại.

## 8. Ví dụ: tiêu chí hoàn tất cho thay đổi thanh toán

Giả sử nhóm phát triển chức năng thanh toán mới. Mục tiêu là cho phép người dùng thanh toán đúng số tiền, tránh giao dịch trùng và phản ánh chính xác trạng thái đơn.

### 8.1. Mục tiêu và rủi ro

| Mục tiêu | Rủi ro nếu không đạt |
|---|---|
| Tính đúng số tiền cần thanh toán. | Thu sai tiền, thiếu tiền hoặc sai phí. |
| Chỉ chủ đơn mới được thanh toán. | Người dùng khác thao tác trái phép. |
| Callback được xác minh. | Callback giả mạo làm thay đổi trạng thái. |
| Request lặp không tạo giao dịch trùng. | Người dùng bị tính tiền nhiều lần. |
| Trạng thái đơn và giao dịch nhất quán. | Đơn báo đã thanh toán trong khi giao dịch thất bại hoặc ngược lại. |
| Người dùng nhận được phản hồi đúng. | UI hiển thị thành công hoặc thất bại sai thực tế. |

### 8.2. Tiêu chí và bằng chứng

| Tiêu chí hoàn tất | Bằng chứng | Loại gate |
|---|---|---|
| Tổng tiền đúng với giá, thuế, phí và giảm giá theo quy tắc. | Unit test cho phân vùng và giá trị biên; API test cho request tổng hợp. | Bắt buộc. |
| Người dùng khác không thể thanh toán đơn không thuộc quyền. | API authorization test với hai tài khoản; xác minh không có tác dụng phụ. | Bắt buộc. |
| Callback chỉ được chấp nhận khi chữ ký hợp lệ. | Unit test chữ ký và integration test với callback sandbox. | Bắt buộc. |
| Callback lặp không tạo giao dịch hoặc sự kiện trùng. | Integration test gửi lặp và đọc lại trạng thái; kiểm tra idempotency. | Bắt buộc. |
| Trạng thái đơn và giao dịch nhất quán sau thành công hoặc lỗi. | Integration test cho transaction, timeout và recovery. | Bắt buộc. |
| Người dùng nhìn thấy kết quả phù hợp. | E2E test đại diện cho thành công và trạng thái chờ/lỗi. | Bắt buộc với hành trình cốt lõi. |
| Log và audit không chứa token hoặc dữ liệu nhạy cảm không cần thiết. | Kiểm tra log, secret scanning và review cấu hình. | Bắt buộc. |
| Có giám sát và cảnh báo cho lỗi callback. | Kiểm tra metric, alert và runbook. | Điều kiện release/operations. |

### 8.3. Quyết định khi một tiêu chí chưa đạt

Nếu integration test callback thất bại do sandbox không sẵn sàng, trạng thái là BLOCKED hoặc chưa đủ bằng chứng. Không được ghi PASS. Nhóm cần khôi phục sandbox hoặc dùng bằng chứng thay thế có giới hạn và ghi rõ phần chưa được xác minh.

Nếu test xác nhận callback giả mạo được chấp nhận, đây là lỗi bảo mật ảnh hưởng trực tiếp đến tính toàn vẹn giao dịch. Tiêu chí bắt buộc chưa đạt và cần chặn quyết định hoàn tất cho đến khi sửa hoặc có quy trình chấp nhận rủi ro hợp lệ theo chính sách.

Nếu một chỉ số dashboard phụ không đạt nhưng không ảnh hưởng gate đã thống nhất, nhóm có thể tạo hành động cải tiến với owner và thời hạn, đồng thời ghi rõ lý do không chặn.

## 9. Áp dụng tiêu chí ở các giai đoạn phát triển

### 9.1. Refinement và lập kế hoạch

Trước khi bắt đầu, nhóm cần:

- Làm rõ mục tiêu và người dùng.
- Xác định tiêu chí chấp nhận.
- Nhận diện rủi ro chính.
- Xác định loại bằng chứng có thể cần.
- Kiểm tra khả năng chuẩn bị dữ liệu và môi trường.
- Làm rõ ngưỡng hoặc điều kiện chưa thống nhất.

Nếu tiêu chí không thể kiểm chứng vì thiếu định nghĩa, cần giải quyết câu hỏi trước hoặc ghi rõ giả định.

### 9.2. Trong phát triển

Trong lúc triển khai:

- Viết test cho logic và các trường hợp biên.
- Thực hiện review theo tiêu chí.
- Chạy kiểm tra tự động trong CI.
- Cập nhật tài liệu, schema và cấu hình.
- Ghi nhận rủi ro mới phát sinh.
- Bổ sung test khi phát hiện giả định không đúng.

Tiêu chí có thể được tinh chỉnh khi nhóm hiểu rõ hơn về giải pháp, nhưng thay đổi cần được thông báo và thống nhất với chủ sở hữu mục tiêu.

### 9.3. Khi tích hợp

Khi các thành phần phối hợp:

- Xác minh contract và tương thích.
- Chạy integration test với phụ thuộc phù hợp.
- Kiểm tra migration và dữ liệu.
- Xác minh phân quyền ở ranh giới thật.
- Đánh giá hành vi lỗi, retry và xử lý bất đồng bộ.
- Kiểm tra log, trace và khả năng chẩn đoán.

### 9.4. Trước phát hành

Ở cấp release, xem xét:

- Full regression và phạm vi nền tảng đã cam kết.
- Kiểm thử bảo mật và các lỗi nghiêm trọng còn mở.
- Hiệu năng, tải và giới hạn tài nguyên.
- Migration, backup và rollback.
- Feature flag và cấu hình.
- Health, metrics, alert và runbook.
- Rủi ro còn lại và quyết định chấp nhận.

### 9.5. Sau triển khai

Một số tiêu chí chỉ có thể xác nhận trong môi trường thật:

- Smoke test an toàn đạt.
- Error rate và latency trong ngưỡng.
- Không có dấu hiệu dữ liệu sai hoặc giao dịch bất thường.
- Alert và dashboard hoạt động.
- Rollout hoặc rollback theo đúng quy trình.

Nếu điều kiện sau triển khai không đạt, cần kích hoạt hành động đã xác định như dừng rollout, tắt feature flag hoặc rollback.

## 10. Quản lý ngoại lệ và chấp nhận rủi ro

### 10.1. Phân biệt waiver với việc bỏ qua kiểm tra

Waiver là quyết định có chủ đích cho phép tiếp tục dù một tiêu chí chưa đạt hoặc chưa thể xác minh. Nó phải có cơ sở và đúng thẩm quyền.

Một waiver nên ghi:

- Tiêu chí chưa đạt hoặc chưa có bằng chứng.
- Lý do và nguyên nhân.
- Tài sản, người dùng và phiên bản bị ảnh hưởng.
- Mức độ và phạm vi rủi ro.
- Biện pháp giảm thiểu tạm thời.
- Người chịu trách nhiệm xử lý.
- Người có thẩm quyền chấp nhận.
- Thời hạn hết hiệu lực và điều kiện xem xét lại.

Không dùng waiver để đổi trạng thái test thất bại thành pass. Kết quả kiểm thử vẫn phải giữ nguyên; waiver chỉ ảnh hưởng quyết định quản lý rủi ro.

### 10.2. Không miễn trừ yêu cầu bắt buộc tùy tiện

Một số điều kiện có thể bị ràng buộc bởi pháp luật, hợp đồng, chính sách bảo mật hoặc yêu cầu an toàn. Người thực hiện test không tự có quyền miễn trừ. Nếu tiêu chí thuộc loại bắt buộc, phải chuyển đến cơ quan hoặc vai trò có thẩm quyền theo quy trình tổ chức.

### 10.3. Theo dõi ngoại lệ còn hiệu lực

Ngoại lệ có thể trở thành nợ chất lượng nếu không được theo dõi. Cần có danh sách tập trung, cảnh báo khi gần hết hạn và quy trình thu hồi. Khi rủi ro hoặc bối cảnh thay đổi, phải xem xét lại ngay cả khi waiver chưa hết hạn.

## 11. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| Product owner / người đại diện nghiệp vụ | Xác định mục tiêu, giá trị người dùng và tiêu chí nghiệp vụ. |
| QA / test engineer | Chuyển mục tiêu và rủi ro thành điều kiện kiểm chứng, đánh giá chất lượng bằng chứng và chỉ ra khoảng trống. |
| Developer | Tạo kiểm thử phù hợp, cung cấp bằng chứng kỹ thuật và xử lý lỗi. |
| Tech lead / architect | Đánh giá rủi ro kỹ thuật, ranh giới hệ thống và tiêu chuẩn kiến trúc. |
| Security / privacy | Xác định yêu cầu bảo mật, quyền riêng tư và rủi ro liên quan. |
| Operations / SRE | Xác định tiêu chí vận hành, giám sát, phục hồi và readiness. |
| Release manager / người có thẩm quyền | Tổng hợp bằng chứng, xem xét gate và quyết định chuyển giai đoạn theo quyền được giao. |
| Cả nhóm | Thống nhất tiêu chí, cập nhật khi thay đổi và không che giấu khoảng trống bằng chứng. |

QA có thể điều phối đánh giá nhưng không phải người duy nhất chịu trách nhiệm về chất lượng. Người sở hữu mục tiêu và rủi ro cần tham gia quyết định.

## 12. Mẫu tiêu chí hoàn tất gắn với mục tiêu và rủi ro

~~~text
Tên hạng mục / tính năng / release:
Cấp độ quyết định:
Phiên bản / môi trường:
Chủ sở hữu mục tiêu:

Mục tiêu cần đạt:
Người dùng / bên liên quan:
Điều kiện ban đầu:

Rủi ro liên quan:
- Tình huống:
- Tác động:
- Khả năng:
- Mức ưu tiên:
- Kiểm soát hiện có:

Tiêu chí hoàn tất:
1. Điều kiện:
   - Kết quả mong đợi:
   - Ngưỡng / phạm vi:
   - Bằng chứng:
   - Trạng thái:
2. Điều kiện:
   - Kết quả mong đợi:
   - Ngưỡng / phạm vi:
   - Bằng chứng:
   - Trạng thái:

Gate bắt buộc:
Mục tiêu cải tiến / soft threshold:
Test chưa chạy hoặc bị chặn:
Phần không áp dụng và lý do:

Rủi ro còn lại:
Biện pháp giảm thiểu:
Waiver / người phê duyệt / thời hạn:
Quyết định:
Người xác nhận:
Ngày xem xét:
~~~

### 12.1. Checklist review tiêu chí

- [ ] Mục tiêu mô tả kết quả có ý nghĩa.
- [ ] Cấp độ quyết định được xác định.
- [ ] Người dùng và ngữ cảnh được làm rõ.
- [ ] Rủi ro có tình huống và hậu quả cụ thể.
- [ ] Tiêu chí có điều kiện, kết quả và phạm vi quan sát được.
- [ ] Ngưỡng định lượng có nguồn và cơ sở.
- [ ] Bằng chứng phù hợp với rủi ro và tầng kiểm thử.
- [ ] Pass, fail, blocked, not run và waived được phân biệt.
- [ ] Gate bắt buộc được tách khỏi mục tiêu cải tiến.
- [ ] Có người xác nhận và người quyết định.
- [ ] Ngoại lệ có owner, thời hạn và cơ sở chấp nhận.
- [ ] Rủi ro còn lại được ghi nhận.
- [ ] Tiêu chí có thể truy vết đến yêu cầu, test và build.

## 13. Những sai lầm thường gặp

- **Dùng “test pass” làm tiêu chí duy nhất:** không cho biết mục tiêu và rủi ro nào đã được kiểm tra.
- **Dùng tiêu chí mơ hồ:** các thành viên có thể hiểu “đủ tốt” theo cách khác nhau.
- **Chỉ đo số lượng:** số test hoặc code coverage không chứng minh chất lượng hành vi.
- **Đặt ngưỡng không có cơ sở:** con số tùy tiện có thể quá dễ hoặc không thực tế.
- **Không xác định cấp độ:** hoàn tất story bị nhầm với sẵn sàng release.
- **Không xét rủi ro:** lỗi nghiêm trọng có thể bị xem ngang với lỗi nhỏ.
- **Coi blocked hoặc skipped là pass:** tạo cảm giác bao phủ sai.
- **Dùng waiver để xóa kết quả thất bại:** làm mất tính toàn vẹn của bằng chứng.
- **Không chỉ định người quyết định:** ngoại lệ và rủi ro còn lại không có chủ sở hữu.
- **Không cập nhật khi yêu cầu thay đổi:** tiêu chí không còn bảo vệ mục tiêu hiện tại.
- **Chỉ QA sở hữu tiêu chí:** các quyết định nghiệp vụ, kiến trúc và vận hành bị tách rời.
- **Không giữ bằng chứng:** kết luận hoàn tất không thể được review hoặc tái xác minh.

## 14. Danh sách rà soát trước khi xác nhận hoàn tất

- [ ] Mục tiêu cần đạt được mô tả rõ và gắn với nhu cầu.
- [ ] Rủi ro được nhận diện theo khả năng, tác động và phạm vi ảnh hưởng.
- [ ] Mỗi rủi ro quan trọng có kiểm soát và bằng chứng tương ứng.
- [ ] Tiêu chí hoàn tất có thể quan sát và kiểm chứng.
- [ ] Ngưỡng được xác định từ yêu cầu, SLO hoặc cơ sở đã thống nhất.
- [ ] Tầng kiểm thử và nguồn bằng chứng phù hợp.
- [ ] Phiên bản, môi trường, dữ liệu và vai trò được ghi nhận.
- [ ] Test bắt buộc đã chạy hoặc có trạng thái blocked/waived rõ ràng.
- [ ] Lỗi còn mở được đánh giá theo mức độ và tác động.
- [ ] Không có lỗi bắt buộc bị che giấu bằng retry hoặc skip.
- [ ] Rủi ro còn lại có owner và biện pháp giảm thiểu.
- [ ] Ngoại lệ được phê duyệt đúng thẩm quyền và có thời hạn.
- [ ] Quyết định hoàn tất ở đúng cấp độ task, story, feature hoặc release.
- [ ] Bằng chứng có thể truy vết đến yêu cầu, commit/build và test run.
- [ ] Có kế hoạch xem xét lại khi mục tiêu, rủi ro hoặc môi trường thay đổi.

## Kết luận

Tiêu chí hoàn tất có giá trị khi chúng chuyển mục tiêu và rủi ro thành điều kiện quan sát được, gắn với bằng chứng đủ tin cậy và xác định rõ ngưỡng ra quyết định. Nhóm cần phân biệt mục tiêu, tiêu chí và bằng chứng; chọn tầng kiểm thử theo nơi rủi ro phát sinh; tách gate bắt buộc khỏi mục tiêu cải tiến; đồng thời ghi nhận các trường hợp chưa chạy, bị chặn hoặc được miễn trừ. Khi người sở hữu mục tiêu, phát triển, QA, bảo mật và vận hành cùng thống nhất tiêu chí, quyết định hoàn tất sẽ minh bạch và phản ánh đúng mức độ rủi ro còn lại.
