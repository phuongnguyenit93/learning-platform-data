# Tổ chức đánh giá lỗi với các bên có quyền quyết định

## 1. Vì sao cần tổ chức đánh giá lỗi?

Một lỗi phần mềm hiếm khi chỉ liên quan đến người tìm thấy lỗi hoặc người viết đoạn mã gây ra lỗi. Việc đánh giá có thể cần thông tin từ kiểm thử, phát triển, chủ sở hữu dịch vụ, chuyên gia nghiệp vụ, vận hành, bảo mật, dữ liệu, hỗ trợ khách hàng và người có quyền quyết định phát hành. Nếu thiếu đúng bên liên quan, nhóm có thể đánh giá sai tác động, chọn mức ưu tiên không phù hợp, trì hoãn xử lý rủi ro hoặc đưa ra quyết định mà không ai có thẩm quyền chịu trách nhiệm.

**Đánh giá lỗi (defect review)** là hoạt động xem xét có cấu trúc một lỗi hoặc nhóm lỗi để xác nhận thông tin, hiểu tác động, xác định mức độ nghiêm trọng, quyết định ưu tiên và cách xử lý, giao owner cùng thời hạn, đồng thời xác định liệu lỗi có ảnh hưởng đến phát hành hoặc vận hành hay không. Hoạt động này có thể diễn ra trong buổi triage định kỳ, cuộc họp release readiness hoặc một phiên đánh giá khẩn cấp.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, tổ chức đánh giá lỗi cần bảo đảm ba điều:

- Quyết định dựa trên bằng chứng và hiểu biết phù hợp, không chỉ dựa trên chức danh hoặc ý kiến lớn tiếng nhất.
- Người tham gia có đúng quyền hạn để quyết định nội dung thuộc phạm vi của họ.
- Mỗi kết luận tạo ra hành động có owner, thời hạn và điều kiện hoàn tất.

Không phải lỗi nào cũng cần một cuộc họp đông người. Lỗi nhỏ, dễ tái hiện và nằm trong quyền xử lý của một nhóm có thể được giải quyết qua quy trình thông thường. Lỗi có tác động liên dịch vụ, ảnh hưởng dữ liệu, bảo mật, khách hàng hoặc quyết định phát hành cần tập hợp đúng chuyên gia và người có thẩm quyền. Mục tiêu là có quyết định đúng lúc, đủ căn cứ và có thể truy xuất.

## 2. Phân biệt defect review, triage và incident review

Các hoạt động có liên quan nhưng trả lời những câu hỏi khác nhau:

| Hoạt động | Câu hỏi chính | Kết quả thường có |
|---|---|---|
| Defect triage | Lỗi có hợp lệ không, thuộc phạm vi nào, mức độ và ưu tiên ra sao, ai xử lý? | Phân loại, severity/priority, owner, trạng thái và hạn |
| Defect review | Các bên có trách nhiệm đã hiểu bằng chứng, tác động và phương án xử lý chưa? | Quyết định sửa, hoãn, loại bỏ, chấp nhận rủi ro hoặc điều tra thêm |
| Incident response | Dịch vụ đang bị ảnh hưởng thế nào và cần làm gì để khôi phục? | Giảm tác động, khôi phục dịch vụ, thông tin liên lạc và điều phối xử lý |
| Incident/post-incident review | Vì sao sự cố xảy ra, phản ứng có hiệu quả không và cần cải thiện điều gì? | Nguyên nhân, bài học, hành động phòng ngừa và theo dõi |
| Change/release review | Thay đổi có đủ bằng chứng và đáp ứng điều kiện chuyển bước không? | Quyết định phát hành, điều kiện, ngoại lệ hoặc hoãn |

Defect review không thay thế incident response. Khi hệ thống đang gây tác động cho người dùng, ưu tiên trước hết là giảm thiểu và khôi phục dịch vụ; điều tra nguyên nhân sâu có thể tiếp tục sau. Ngược lại, một lỗi được phát hiện trong kiểm thử trước phát hành có thể cần defect review và release decision nhưng chưa phải incident đang diễn ra.

Một lỗi có thể đi qua nhiều hoạt động. Ví dụ, một defect gây sai số dư được phát hiện trong sản xuất sẽ được xử lý qua incident response; sau khi ổn định, nhóm thực hiện post-incident review, mở defect để theo dõi sửa lỗi gốc và bổ sung kiểm thử hồi quy.

## 3. Khi nào cần tổ chức defect review?

Chọn hình thức đánh giá theo mức độ ảnh hưởng, độ bất định và phạm vi quyết định.

### 3.1. Xử lý trong nhóm

Phù hợp khi lỗi:

- Có phạm vi trong một thành phần do một nhóm sở hữu.
- Tác động thấp, đã hiểu rõ và không ảnh hưởng điều kiện phát hành.
- Có cách tái hiện và phương án sửa rõ.
- Không cần quyết định từ domain, security, operations hoặc nhóm phụ thuộc.

Nhóm vẫn cần ghi nhận kết luận, owner và trạng thái trong hệ thống quản lý lỗi. Không nên bỏ qua việc lưu bằng chứng chỉ vì không tổ chức cuộc họp.

### 3.2. Triage liên nhóm

Cần khi lỗi:

- Đi qua nhiều dịch vụ hoặc nhóm sở hữu.
- Liên quan contract, dữ liệu dùng chung hoặc thay đổi phụ thuộc.
- Có tác động đến hành trình nghiệp vụ mà một nhóm không thể tự đánh giá.
- Cần thống nhất ưu tiên hoặc kế hoạch sửa giữa provider và consumer.
- Có nguyên nhân chưa rõ giữa sản phẩm, dữ liệu, môi trường và hạ tầng.

### 3.3. Đánh giá có người quyết định phát hành

Cần khi lỗi:

- Có thể làm thay đổi quyết định release hoặc rollout.
- Ảnh hưởng đến chức năng trọng yếu, doanh thu, dữ liệu hoặc cam kết dịch vụ.
- Chưa thể sửa trước hạn nhưng cần cân nhắc ngoại lệ.
- Có rủi ro còn lại cần người có thẩm quyền chấp thuận.
- Có tranh chấp về mức độ, phạm vi hoặc chấp nhận rủi ro.

### 3.4. Đánh giá khẩn cấp

Với lỗi đang gây tác động lớn, không chờ lịch triage định kỳ. Kích hoạt incident process hoặc escalation theo chính sách, gọi đúng người có quyền điều phối và ra quyết định. Defect record có thể được cập nhật sau khi hành động khẩn cấp đã bắt đầu, nhưng cần bảo toàn mốc thời gian và quyết định.

## 4. Thành phần tham gia và quyền hạn

Không cần mời tất cả vai trò vào mọi buổi đánh giá. Chọn người dựa trên thông tin họ nắm giữ và quyền quyết định cần thiết.

| Vai trò | Đóng góp trong đánh giá lỗi | Quyền hoặc trách nhiệm thường có |
|---|---|---|
| Facilitator/triage lead | Điều phối, giữ phạm vi, xác nhận quyết định và action | Bảo đảm quy trình rõ; không tự quyết mọi vấn đề chuyên môn |
| Reporter/tester | Mô tả điều kiện phát hiện, bước tái hiện, expected/actual result và evidence | Làm rõ bằng chứng, bổ sung bước tái hiện |
| Developer/component owner | Phân tích mã, nguyên nhân kỹ thuật, độ phức tạp và phương án sửa | Chịu trách nhiệm xử lý trong thành phần được giao |
| Service owner | Đánh giá tác động dịch vụ, dependency và rủi ro còn lại | Chịu trách nhiệm chất lượng và kế hoạch xử lý của service |
| Product/business owner | Giải thích quy tắc nghiệp vụ, người dùng bị ảnh hưởng và giá trị ưu tiên | Quyết định ưu tiên nghiệp vụ trong phạm vi được giao |
| Test lead/QA owner | Đánh giá mức bao phủ, khả năng tái hiện, regression impact và kiểm thử xác minh | Đề xuất test bổ sung và tiêu chí đóng |
| Operations/SRE | Đánh giá tác động vận hành, metric, khả năng giảm thiểu và khôi phục | Điều phối hoặc tư vấn hành động vận hành theo quyền hạn |
| Security/privacy specialist | Đánh giá rủi ro bảo mật, quyền riêng tư và nghĩa vụ chuyên môn | Quyết định hoặc tư vấn theo policy chuyên môn |
| Data owner/DB specialist | Đánh giá tính toàn vẹn, migration, khôi phục và đối soát dữ liệu | Xác nhận rủi ro và biện pháp dữ liệu |
| Support/customer representative | Cung cấp tín hiệu khách hàng, tần suất và mức độ ảnh hưởng thực tế | Thông tin tác động và nhu cầu truyền thông |
| Release authority | Cân nhắc readiness, ngoại lệ và điều kiện phát hành | Quyết định release trong phạm vi được ủy quyền |

### 4.1. Người cần có mặt để ra quyết định

Trước buổi review, xác định loại quyết định cần đưa ra. Nếu cần quyết định ưu tiên nghiệp vụ, phải có product/business owner hoặc người được ủy quyền. Nếu cần chấp thuận rủi ro bảo mật, phải có người có thẩm quyền bảo mật theo policy. Nếu lỗi ảnh hưởng release, release authority cần nhận kết luận hoặc tham gia trực tiếp tùy quy trình.

Không nên kết thúc bằng câu “các bên đồng ý” nếu không rõ ai chịu trách nhiệm cuối cùng. Có thể có nhiều người được tham vấn, nhưng quyền quyết định cuối cùng phải gắn với vai trò cụ thể.

### 4.2. Người không cần tham gia trực tiếp

Những người chỉ cần biết kết quả có thể nhận biên bản hoặc thông báo sau buổi review. Giảm số người tham dự giúp cuộc họp tập trung và không biến việc đánh giá thành một buổi cập nhật trạng thái dài. Người có thông tin chuyên môn quan trọng nhưng không thể dự có thể gửi nhận xét trước hoặc chỉ định đại diện có thẩm quyền phù hợp.

## 5. Chuẩn bị thông tin trước buổi review

Một buổi review hiệu quả bắt đầu từ defect record đủ chất lượng. Facilitator cần yêu cầu người báo cáo chuẩn bị:

- Defect ID, tiêu đề ngắn và trạng thái hiện tại.
- Build, commit, phiên bản dịch vụ và môi trường phát hiện.
- Thời điểm, tần suất và điều kiện xảy ra.
- Bước tái hiện, dữ liệu đầu vào và kết quả mong đợi/thực tế.
- Log, ảnh, video, trace, request/response đã làm sạch.
- Người dùng, tenant, giao dịch hoặc luồng nghiệp vụ bị ảnh hưởng.
- Phạm vi dịch vụ và dependency liên quan.
- Workaround hiện có và giới hạn của workaround.
- Lịch sử tái hiện, test liên quan và defect tương tự.
- Tác động nếu lỗi không được sửa trước mốc quyết định.

### 5.1. Kiểm tra chất lượng báo cáo

Nếu thiếu thông tin để xác nhận lỗi, không vội kết luận “không phải bug”. Có thể chuyển sang trạng thái cần thêm thông tin và chỉ định người bổ sung. Cần phân biệt:

- **Không tái hiện được:** hiện tại chưa tái hiện trong điều kiện đã thử; chưa đủ căn cứ kết luận lỗi không tồn tại.
- **Không phải lỗi:** hành vi thực tế phù hợp với yêu cầu đã được xác nhận.
- **Trùng lặp:** đã có defect khác theo dõi cùng vấn đề; cần liên kết bản ghi.
- **Ngoài phạm vi:** vấn đề không thuộc sản phẩm hoặc phiên bản đang đánh giá; cần chỉ rõ nơi chuyển tiếp.
- **Thiếu bằng chứng:** thông tin hiện tại chưa đủ để xác định.

### 5.2. Bảo vệ thông tin nhạy cảm

Log, request, ảnh chụp hoặc database snapshot có thể chứa token, dữ liệu cá nhân, thông tin thanh toán hoặc bí mật nội bộ. Trước khi chia sẻ, cần làm sạch dữ liệu và dùng kênh có quyền truy cập phù hợp. Không đính kèm secret vào defect ticket hoặc gửi rộng qua email/chat.

### 5.3. Chuẩn bị phân tích tác động

Service owner hoặc người phụ trách kỹ thuật nên chuẩn bị bản đồ thành phần và consumer bị ảnh hưởng. Product owner chuẩn bị thông tin về quy tắc nghiệp vụ và nhóm người dùng. Test lead xác định suite, requirement và regression case liên quan. Operations chuẩn bị metric hoặc log vận hành nếu lỗi đã xảy ra trong môi trường thật.

## 6. Đánh giá mức độ nghiêm trọng và mức ưu tiên

Severity và priority trả lời hai câu hỏi khác nhau:

- **Severity (mức độ nghiêm trọng):** hậu quả của lỗi nếu xảy ra hoặc tiếp tục tồn tại.
- **Priority (mức ưu tiên):** mức khẩn cấp và thứ tự cần xử lý dựa trên tác động, thời hạn, khả năng khắc phục và quyết định kinh doanh.

Một lỗi nghiêm trọng có thể cần ưu tiên xử lý ngay. Tuy nhiên, một lỗi ít nghiêm trọng hơn nhưng chặn phát hành, ảnh hưởng nhiều khách hàng hoặc có thời hạn hợp đồng gần kề cũng có thể được ưu tiên cao.

### 6.1. Các chiều đánh giá severity

- Mức độ sai lệch chức năng hoặc dữ liệu.
- Số lượng và loại người dùng bị ảnh hưởng.
- Tác động đến tiền, giao dịch, dữ liệu hoặc hoạt động.
- Rủi ro bảo mật, quyền riêng tư, an toàn và tuân thủ.
- Khả năng gây lan truyền sang dịch vụ khác.
- Mức độ mất khả năng sử dụng hoặc phục hồi.
- Khả năng phát hiện trước khi người dùng chịu tác động.

### 6.2. Các chiều đánh giá priority

- Thời điểm cần phát hành hoặc nghĩa vụ phải đáp ứng.
- Tần suất xuất hiện và xu hướng tăng.
- Có workaround an toàn hay không.
- Chi phí trì hoãn và ảnh hưởng đến roadmap.
- Mức độ phụ thuộc của nhóm khác.
- Khả năng sửa và xác minh trong thời gian còn lại.
- Mức độ rủi ro còn lại nếu hoãn.

### 6.3. Ví dụ thang severity

Tổ chức có thể dùng thang như sau, nhưng cần thống nhất định nghĩa cụ thể:

| Mức | Diễn giải | Ví dụ |
|---|---|---|
| Critical | Tác động rất nghiêm trọng đến an toàn, bảo mật, dữ liệu, giao dịch hoặc dịch vụ cốt lõi; cần hành động khẩn cấp | Lộ dữ liệu nhạy cảm diện rộng, ghi sai số dư, dịch vụ thanh toán ngừng hoạt động |
| High | Chức năng quan trọng bị hỏng, nhiều người dùng bị ảnh hưởng hoặc không có workaround phù hợp | Không thể hoàn tất đơn hàng cho một nhóm lớn người dùng |
| Medium | Chức năng bị suy giảm hoặc có lỗi trong điều kiện nhất định, tác động có giới hạn | Một bộ lọc báo cáo cho kết quả sai trong một trường hợp ít gặp |
| Low | Tác động nhỏ, thường có workaround dễ dàng và không ảnh hưởng dữ liệu trọng yếu | Hiển thị sai một nhãn phụ nhưng hành vi chính vẫn đúng |

Không dùng ví dụ như quy tắc cứng cho mọi sản phẩm. Một lỗi hiển thị có thể là nghiêm trọng nếu khiến người dùng xác nhận sai giao dịch; một lỗi chỉ xảy ra với ít người vẫn có thể critical nếu liên quan đến quyền riêng tư hoặc an toàn.

### 6.4. Severity không phải là mức ưu tiên

Ví dụ, một lỗi hiển thị nhỏ trong bản phát hành sắp diễn ra có thể được ưu tiên cao vì sửa nhanh và dễ gây nhầm lẫn cho người dùng. Một lỗi mức high trong chức năng chưa bật có thể được lên kế hoạch xử lý theo điều kiện kích hoạt, nhưng rủi ro cần được theo dõi. Mọi quyết định trì hoãn lỗi nghiêm trọng phải có owner, lý do và thẩm quyền phù hợp.

## 7. Đánh giá tác động và phạm vi ảnh hưởng

Defect review cần vượt ra ngoài câu hỏi “lỗi nằm ở file nào”. Hãy đánh giá:

### 7.1. Tác động chức năng

- Hành vi nào sai và expected behavior là gì?
- Có luồng thay thế hoặc workaround không?
- Lỗi ảnh hưởng một thao tác hay toàn bộ hành trình?
- Có thể gây sai trạng thái hoặc tác dụng phụ lặp lại không?

### 7.2. Tác động dữ liệu

- Dữ liệu bị mất, sai, trùng, thiếu hoặc không nhất quán?
- Có thể phục hồi từ backup hoặc tái tạo không?
- Có cần đối soát, sửa dữ liệu hoặc bù trừ giao dịch?
- Migration hoặc job nền có thể làm lan rộng lỗi không?

### 7.3. Tác động người dùng và nghiệp vụ

- Ai bị ảnh hưởng: khách hàng, nhân viên nội bộ, đối tác hay nhóm vận hành?
- Ảnh hưởng ở khu vực, tenant, loại tài khoản hoặc phiên bản nào?
- Tần suất và thời gian tồn tại của lỗi?
- Có ảnh hưởng doanh thu, cam kết dịch vụ hoặc uy tín không?

### 7.4. Tác động kỹ thuật và phụ thuộc

- Provider/consumer nào bị ảnh hưởng?
- Có thay đổi contract, schema, event hoặc cấu hình?
- Lỗi có lan sang queue, cache, search index hoặc hệ thống báo cáo?
- Có thể tái hiện trên môi trường khác không?

### 7.5. Tác động bảo mật và tuân thủ

- Có khả năng truy cập vượt quyền, lộ dữ liệu hoặc ghi log thông tin nhạy cảm?
- Có nghĩa vụ thông báo, lưu bằng chứng hoặc xử lý theo thời hạn không?
- Có yêu cầu chuyên môn hoặc quy trình báo cáo bắt buộc?

Nếu một chiều chưa đủ thông tin, ghi rõ bất định và người cần điều tra. Không tự đánh giá bằng 0 chỉ vì chưa có bằng chứng.

## 8. Quy trình tổ chức một buổi defect review

### Bước 1: Xác định mục tiêu và loại quyết định

Facilitator xác định buổi review cần quyết định điều gì: xác nhận defect, phân severity, ưu tiên sửa, phân công owner, đánh giá release impact, chấp thuận workaround hay yêu cầu điều tra thêm. Một buổi họp không có câu hỏi quyết định rõ dễ biến thành trao đổi lan man.

### Bước 2: Chọn đúng người tham gia

Mời reporter/tester, service/component owner, test lead và vai trò chuyên môn cần thiết. Nếu có quyết định phát hành hoặc ngoại lệ, xác định người có thẩm quyền trước khi họp. Chỉ mời những người có thông tin hoặc trách nhiệm cần thiết.

### Bước 3: Gửi thông tin trước

Chia sẻ defect record, bằng chứng đã làm sạch, build/environment, tác động sơ bộ và câu hỏi cần quyết định. Với lỗi khẩn cấp, có thể trao đổi đồng thời trong incident channel nhưng vẫn cần lưu quyết định vào hồ sơ chính thức.

### Bước 4: Xác nhận sự kiện và bằng chứng

Bắt đầu bằng những điều đã biết: hành vi quan sát, điều kiện, phiên bản, tần suất và cách tái hiện. Phân biệt sự kiện với giả thuyết. Ví dụ, “API trả 500 trong 3/10 lần gọi” là quan sát; “database connection pool bị cạn” là giả thuyết cần bằng chứng.

### Bước 5: Đánh giá tác động và rủi ro

Xác định thành phần, consumer, người dùng, dữ liệu và hành trình bị ảnh hưởng. Đánh giá severity, khả năng xảy ra, phạm vi phơi nhiễm, khả năng phát hiện và khôi phục. Ghi rõ phần chưa biết.

### Bước 6: Đề xuất phương án

Các phương án có thể gồm:

- Sửa lỗi ngay và bổ sung test hồi quy.
- Thực hiện workaround hoặc giảm phạm vi tính năng.
- Tắt feature flag hoặc rollback.
- Điều tra thêm vì bằng chứng chưa đủ.
- Chấp nhận rủi ro có thời hạn theo thẩm quyền.
- Đóng lỗi vì không tái hiện được hoặc không phải lỗi, với căn cứ.
- Liên kết duplicate và tiếp tục theo dõi bản ghi chính.

### Bước 7: Ra quyết định và xác định quyền hạn

Ghi ai quyết định, tiêu chí nào được dùng và lý do. Nếu không có người có thẩm quyền, không ghi quyết định như đã được phê duyệt; chuyển lên cấp phù hợp hoặc giữ trạng thái chờ.

### Bước 8: Giao owner và thời hạn

Mỗi hành động cần một owner, ngày đến hạn, đầu ra mong đợi và người xác minh. Có thể có nhiều người hỗ trợ nhưng cần một người chịu trách nhiệm điều phối hoàn tất.

### Bước 9: Xác nhận đóng hoặc theo dõi

Defect chỉ được đóng khi đáp ứng tiêu chí đóng đã thống nhất: sửa đúng, test xác minh đạt, regression được cập nhật, dữ liệu được đối soát nếu cần và bằng chứng được lưu. Nếu hoãn, cần trạng thái, lý do, rủi ro và ngày review tiếp.

## 9. Chương trình nghị sự cho buổi review

Một buổi review thông thường có thể kéo dài 20–45 phút tùy số lượng và độ phức tạp:

| Phần | Nội dung | Kết quả mong đợi |
|---|---|---|
| Mở đầu | Mục tiêu, build, phạm vi và quyết định cần có | Mọi người hiểu câu hỏi cần giải quyết |
| Xác nhận lỗi | Steps, expected/actual, evidence và khả năng tái hiện | Thống nhất sự kiện đã biết |
| Tác động | Người dùng, dữ liệu, dịch vụ, bảo mật và vận hành | Bản đồ phạm vi ảnh hưởng |
| Phân loại | Severity, priority, release impact và bất định | Mức đánh giá có căn cứ |
| Phương án | Sửa, workaround, rollback, điều tra hoặc hoãn | Lựa chọn và trade-off |
| Quyết định | Người có thẩm quyền, điều kiện và ngoại lệ | Quyết định rõ |
| Hành động | Owner, hạn, test xác minh và thông báo | Action log có thể theo dõi |

Với một lỗi duy nhất nhưng nghiêm trọng, thời gian có thể ngắn hơn nếu quyết định khẩn cấp đã rõ. Với nhóm lỗi lớn, nên gửi trước danh sách và xử lý theo mức rủi ro để không dành thời gian ngang nhau cho mọi lỗi.

## 10. Quyền quyết định và ma trận trách nhiệm

### 10.1. RACI minh họa

RACI giúp phân biệt Responsible (thực hiện), Accountable (chịu trách nhiệm cuối cùng), Consulted (được tham vấn) và Informed (được thông báo).

| Hoạt động | Reporter/tester | Test lead | Service owner | Product owner | Specialist | Release authority |
|---|---|---|---|---|---|---|
| Cung cấp bằng chứng và tái hiện | R | A/C | C | I | C | I |
| Xác nhận phạm vi kiểm thử | C | A/R | C | C | C | I |
| Phân tích nguyên nhân kỹ thuật | C | C | A/R | I | C | I |
| Đánh giá tác động nghiệp vụ | C | C | R | A/R | C | I |
| Đánh giá chuyên môn bảo mật/dữ liệu | C | C | R | I | A/R | I |
| Đề xuất severity/priority | C | R | A | C | C | I |
| Quyết định sửa/hoãn trong service | I | C | A/R | C | C | I |
| Chấp thuận rủi ro release | I | C | R | C | C* | A* |
| Xác nhận test sau sửa | R | A | C | I | C | I |

Ma trận cần được điều chỉnh theo tổ chức. Với ngoại lệ bảo mật, quyền riêng tư, an toàn hoặc tuân thủ, specialist có thể có quyền phê duyệt riêng theo policy; dấu * nhắc rằng release authority không tự động có quyền miễn trừ mọi yêu cầu chuyên môn.

### 10.2. Phân biệt quyết định kỹ thuật và quyết định nghiệp vụ

Developer hoặc service owner có thể xác định phương án kỹ thuật và độ phức tạp sửa. Product owner đánh giá giá trị, khách hàng và thứ tự ưu tiên nghiệp vụ. Security/privacy specialist đánh giá rủi ro chuyên môn. Release authority quyết định có phát hành trong điều kiện đã biết hay không.

Một quyết định tốt cần ghi rõ ai có quyền cho từng phần. Không yêu cầu product owner quyết định chi tiết kỹ thuật ngoài chuyên môn; cũng không để kỹ sư tự chấp nhận rủi ro nghiệp vụ hoặc tuân thủ mà họ không được ủy quyền.

## 11. Xử lý bất đồng trong đánh giá lỗi

Bất đồng thường xuất hiện khi các nhóm có dữ liệu hoặc mục tiêu khác nhau. Có thể áp dụng quy trình:

1. Tách dữ kiện đã xác nhận khỏi giả thuyết và ý kiến.
2. Xác định điểm bất đồng cụ thể: tái hiện, severity, phạm vi, nguyên nhân hay ưu tiên.
3. Yêu cầu bằng chứng bổ sung có thời hạn và owner.
4. Dùng tiêu chí severity/priority đã thống nhất thay vì thương lượng theo chức danh.
5. Nếu cần, mời domain expert hoặc specialist độc lập.
6. Chuyển quyết định lên người có thẩm quyền khi vượt quyền của nhóm.
7. Ghi nhận ý kiến khác biệt và lý do quyết định cuối cùng.

Không nên trì hoãn vô hạn vì chưa đạt đồng thuận tuyệt đối. Nếu cần hành động khẩn cấp, người có quyền điều phối chọn biện pháp tạm thời an toàn, ghi nhận giả định và đặt thời điểm review lại.

### 11.1. Tránh thiên kiến trong review

- Không xem reporter là người phải chứng minh lỗi bằng mọi giá; trách nhiệm là cùng xác minh.
- Không mặc định lỗi ít gặp là ít nghiêm trọng.
- Không hạ severity chỉ vì sửa khó hoặc ảnh hưởng kế hoạch.
- Không tăng severity chỉ để đẩy lỗi lên đầu danh sách.
- Không đóng lỗi vì không tái hiện được trong một lần thử.
- Không để chức danh hoặc thâm niên thay thế bằng chứng.
- Không quy lỗi cho cá nhân; tập trung vào hành vi hệ thống và điều kiện gây lỗi.

## 12. Tổ chức review cho lỗi liên dịch vụ

Khi lỗi đi qua nhiều service, cần xác định:

- Service nào tạo dữ liệu hoặc phát sự kiện?
- Service nào tiêu thụ API/event?
- Contract và phiên bản nào được sử dụng?
- Ai sở hữu dữ liệu nguồn và ai sở hữu bản sao/cache?
- Lỗi xuất hiện ở provider, consumer, gateway hay môi trường?
- Có thể giảm tác động bằng rollback hoặc tắt một consumer không?
- Bằng chứng từ mỗi service có cùng mốc thời gian và correlation ID không?

Nên chỉ định một incident/defect coordinator để tổng hợp tiến độ. Mỗi service owner chịu trách nhiệm phân tích và hành động trong thành phần của mình. Nhóm điều phối không thay thế ownership của từng service.

Ví dụ, trạng thái thanh toán đúng ở provider nhưng sai ở order service. Payment owner xác nhận event đã phát; order owner kiểm tra consumer và trạng thái lưu; platform owner kiểm tra broker; test lead xác định contract/integration test cần bổ sung. Release authority đánh giá tác động đến phát hành sau khi có kết luận.

## 13. Khi lỗi trở thành incident

Nếu lỗi đang gây gián đoạn hoặc tác động thực tế, kích hoạt incident process theo ngưỡng của tổ chức. Defect review cần phối hợp với incident commander hoặc incident lead:

- Incident lead điều phối giảm thiểu và khôi phục.
- Service owner cung cấp phân tích kỹ thuật và hành động trong service.
- Operations/SRE theo dõi tình trạng, metric và rollout.
- Support/customer communication owner quản lý thông tin đến người dùng theo chính sách.
- Security/privacy/legal specialist tham gia nếu có nghĩa vụ chuyên môn.
- Defect owner theo dõi sửa lỗi gốc và kiểm thử hồi quy sau sự cố.

Trong giai đoạn khẩn cấp, không để cuộc họp defect review làm chậm rollback hoặc biện pháp bảo vệ. Ghi lại mốc thời gian và quyết định ngay khi có thể. Sau khi dịch vụ ổn định, tổ chức review nguyên nhân và hành động phòng ngừa.

## 14. Theo dõi action và tiêu chí đóng lỗi

Mỗi quyết định cần được chuyển thành action record. Một action tốt có:

- Mô tả hành động cụ thể và đầu ra có thể xác minh.
- Một owner chịu trách nhiệm điều phối.
- Due date hoặc mốc review.
- Mức ưu tiên và quan hệ với release/incident.
- Điều kiện hoàn tất và người xác minh.
- Liên kết đến defect, commit, test hoặc bằng chứng.

### 14.1. Tiêu chí đóng defect

Tùy loại lỗi, có thể cần:

- Nguyên nhân đã được xử lý hoặc rủi ro đã được quyết định theo policy.
- Test xác minh tái hiện lỗi trước sửa và đạt sau sửa.
- Regression test được bổ sung hoặc cập nhật.
- Kiểm tra liên quan ở các consumer hoặc môi trường cần thiết đã hoàn tất.
- Dữ liệu bị ảnh hưởng đã được đối soát/khôi phục.
- Tài liệu, runbook và cảnh báo được cập nhật nếu cần.
- Bằng chứng và quyết định được lưu trong defect record.

Không đóng defect chỉ vì code đã merge. Cần xác minh hành vi trên build phù hợp và đáp ứng điều kiện đóng.

### 14.2. Lỗi hoãn hoặc chấp nhận rủi ro

Nếu không sửa ngay, record cần có:

- Lý do hoãn và phạm vi ảnh hưởng.
- Workaround hoặc giới hạn sử dụng.
- Người sở hữu rủi ro.
- Người có thẩm quyền chấp thuận nếu policy yêu cầu.
- Hạn review hoặc điều kiện hết hiệu lực.
- Điều kiện kích hoạt hành động khẩn cấp.

Trạng thái hoãn không có nghĩa lỗi đã được giải quyết. Cần theo dõi tuổi lỗi và rà soát định kỳ.

## 15. Đo lường hiệu quả của hoạt động defect review

Một số chỉ số có thể giúp cải thiện quy trình:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Time to triage | Thời gian từ khi báo lỗi đến khi có phân loại và owner | Phát hiện chậm trễ trong tiếp nhận |
| Time to decision | Thời gian từ khi đủ bằng chứng đến khi có quyết định | Đánh giá hiệu quả điều phối |
| Time to acknowledge | Thời gian owner xác nhận trách nhiệm | Phát hiện action bị bỏ trống |
| Defect reopen rate | Tỷ lệ lỗi mở lại sau khi đóng | Đánh giá chất lượng sửa và xác minh |
| Escaped defect rate | Lỗi phát hiện sau phát hành so với tổng lỗi theo phạm vi đo | Xem xét khoảng trống kiểm thử |
| Aging by severity | Tuổi lỗi theo mức nghiêm trọng | Ưu tiên lỗi tồn đọng rủi ro cao |
| Unowned defect count | Số lỗi chưa có owner | Đánh giá kỷ luật phân công |
| Decision reversal rate | Tỷ lệ quyết định phải đảo ngược do thiếu thông tin | Cải thiện chất lượng bằng chứng |
| Action completion rate | Tỷ lệ hành động hoàn tất đúng hạn | Đánh giá khả năng thực thi |
| Recurrence rate | Lỗi cùng nguyên nhân xuất hiện lại | Đánh giá hiệu quả phòng ngừa |

Không dùng metric để tạo áp lực đóng lỗi nhanh hoặc làm giảm severity. Chỉ số cần được đọc cùng bối cảnh, mức độ phức tạp và rủi ro. Một nhóm có nhiều defect được ghi nhận có thể đang minh bạch hơn chứ không nhất thiết có chất lượng kém hơn.

## 16. Mẫu biên bản defect review

Có thể dùng mẫu sau để lưu kết quả:

~~~yaml
defect_review:
  review_id: DR-2026-041
  defect_id: PAY-1842
  reviewed_at: "2026-11-16T09:00:00Z"
  release_candidate: "payment-4.8.0-rc2"

participants:
  facilitator: "quality-lead"
  reporter: "test-engineer"
  service_owner: "payment-team"
  product_owner: "payments-product"
  specialist:
    - "security-reviewer"
  release_authority: "release-manager"

evidence:
  environment: "integration-payment"
  build_id: "build-1842"
  reproduction: "reproduced-3-of-5-runs"
  artifacts:
    - "approved-artifact-reference"

assessment:
  severity: high
  priority: urgent
  impact: "Một số yêu cầu hoàn tiền có thể bị xử lý trùng"
  affected_scope:
    - "refund-api"
    - "payment-event-consumer"
  uncertainty:
    - "Chưa xác nhận tỷ lệ xảy ra dưới tải cao"

decision:
  outcome: "fix-before-release"
  rationale: "Rủi ro giao dịch trùng vượt ngưỡng chấp nhận"

actions:
  - id: ACT-01
    description: "Sửa xử lý idempotency và bổ sung regression test"
    owner: "payment-service-owner"
    due: "2026-11-17"
    verifier: "payment-test-owner"
    status: open

follow_up:
  next_review: "2026-11-17T10:00:00Z"
  release_blocker: true
~~~

Mẫu này minh họa cấu trúc, không phải phân loại mặc định. Tên, mức severity, priority, người tham gia và quyết định phải dựa trên tình huống thật. Không đưa dữ liệu khách hàng hoặc secret vào biên bản.

## 17. Mẫu chương trình nghị sự và thông báo

### 17.1. Agenda

~~~text
DEFECT REVIEW
Mục tiêu:
Defect ID / nhóm lỗi:
Release/build liên quan:
Facilitator:
Người có quyền quyết định:

1. Xác nhận bằng chứng và điều kiện tái hiện
2. Phạm vi dịch vụ, người dùng và dữ liệu bị ảnh hưởng
3. Severity, priority và rủi ro còn lại
4. Phương án sửa, workaround, rollback hoặc điều tra
5. Quyết định và căn cứ
6. Owner, thời hạn, verifier và follow-up
~~~

### 17.2. Thông báo sau review

~~~text
DEFECT:
REVIEW DATE:
BUILD/RELEASE:
DECISION:
RATIONALE:
SEVERITY / PRIORITY:
AFFECTED SCOPE:

ACTION ITEMS:
- Action:
  Owner:
  Due:
  Verification:

RISK / EXCEPTION:
Approver:
Expiry or review date:
Conditions:

NEXT REVIEW:
RECORD LINK:
~~~

Thông báo cần được lưu tại hệ thống theo dõi chính thức và gửi đến các bên cần biết. Kênh trao đổi nhanh chỉ hỗ trợ phối hợp; không thay thế hồ sơ quyết định.

## 18. Những sai lầm thường gặp

- **Mời sai thành phần:** thiếu người hiểu domain hoặc người có quyền quyết định.
- **Mời quá đông người:** cuộc họp mất tập trung và không rõ trách nhiệm.
- **Không chuẩn bị evidence:** dành thời gian tranh luận về những điều chưa xác minh.
- **Đánh đồng severity và priority:** quyết định không phản ánh cả hậu quả và thời điểm cần xử lý.
- **Để chức danh quyết định thay bằng chứng:** người có tiếng nói lớn nhất áp đặt kết luận.
- **Coi không tái hiện là không có lỗi:** bỏ qua điều kiện hiếm hoặc môi trường khác biệt.
- **Chỉ xem mã nguồn:** bỏ qua dữ liệu, người dùng, dependency và vận hành.
- **Không ghi bất định:** giả thuyết bị hiểu nhầm thành sự thật.
- **Không xác định quyền waiver:** người không có thẩm quyền chấp thuận rủi ro.
- **Không giao owner và hạn:** quyết định không chuyển thành hành động.
- **Đóng lỗi ngay sau khi merge:** chưa xác minh trên build và chưa cập nhật regression.
- **Dùng defect review thay incident response:** làm chậm hành động khôi phục khi người dùng đang bị ảnh hưởng.
- **Đổ lỗi cá nhân:** làm giảm khả năng chia sẻ thông tin và tìm nguyên nhân hệ thống.
- **Không theo dõi lỗi hoãn:** rủi ro tồn đọng không được xem xét lại.

## 19. Checklist tổ chức đánh giá lỗi

### Trước buổi review

- [ ] Mục tiêu và quyết định cần có được xác định.
- [ ] Defect record có ID, build, môi trường và bước tái hiện.
- [ ] Expected/actual result và bằng chứng đã được chuẩn bị.
- [ ] Phạm vi người dùng, dịch vụ, dữ liệu và dependency được mô tả.
- [ ] Thông tin nhạy cảm đã được làm sạch và chia sẻ đúng quyền.
- [ ] Severity/priority sơ bộ và các điểm chưa rõ được nêu.
- [ ] Người có chuyên môn và người có quyền quyết định đã được xác định.

### Trong buổi review

- [ ] Phân biệt dữ kiện, giả thuyết và ý kiến.
- [ ] Xác nhận tính hợp lệ và khả năng tái hiện của lỗi.
- [ ] Đánh giá tác động chức năng, dữ liệu, nghiệp vụ, kỹ thuật và bảo mật.
- [ ] Phân biệt severity với priority.
- [ ] Xem xét workaround, sửa lỗi, rollback và biện pháp giảm thiểu.
- [ ] Ghi quyết định, căn cứ và người có thẩm quyền.
- [ ] Mỗi action có owner, hạn và điều kiện hoàn tất.

### Sau buổi review

- [ ] Biên bản và liên kết evidence được lưu.
- [ ] Owner đã xác nhận nhận việc.
- [ ] Defect được liên kết với requirement, test, release hoặc incident khi phù hợp.
- [ ] Regression test và tiêu chí đóng được xác định.
- [ ] Ngoại lệ có approver, điều kiện và thời hạn.
- [ ] Hành động quá hạn được escalation.
- [ ] Quyết định được xem xét lại khi có bằng chứng mới hoặc phạm vi thay đổi.

## Kết luận

Đánh giá lỗi có chất lượng cần đúng người, đúng bằng chứng và đúng thẩm quyền. Hãy xác định trước quyết định cần đưa ra, mời các vai trò có thông tin hoặc quyền cần thiết, chuẩn bị defect record và evidence, đánh giá tác động cùng severity/priority, rồi ghi quyết định thành action có owner và thời hạn. Với lỗi liên dịch vụ hoặc sự cố đang diễn ra, cần phối hợp với service owner, specialist và incident process tương ứng. Khi kết luận, ngoại lệ và hành động được lưu truy xuất, nhóm có thể xử lý lỗi nhất quán, giảm tranh chấp và bảo vệ quyết định phát hành.
