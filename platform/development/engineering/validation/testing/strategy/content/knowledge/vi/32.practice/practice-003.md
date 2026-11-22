# Xác định phạm vi, phần loại trừ và giả định cần kiểm chứng

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), phạm vi kiểm thử xác định phần nào của sản phẩm, hành vi và rủi ro sẽ được xác minh trong một hoạt động cụ thể. Phần loại trừ làm rõ những nội dung không được kiểm tra trong phạm vi đó. Giả định mô tả điều nhóm tạm coi là đúng để có thể lập kế hoạch, nhưng vẫn cần kiểm chứng trước hoặc trong quá trình thực hiện.

Ba yếu tố này phải được xác định cùng nhau. Một phạm vi chỉ liệt kê chức năng cần test mà không nêu phần loại trừ có thể tạo cảm giác bao phủ rộng hơn thực tế. Một kế hoạch dựa trên giả định chưa được xác minh có thể thất bại khi môi trường, dữ liệu hoặc dependency không đáp ứng. Một phần loại trừ không có lý do, owner và đánh giá rủi ro có thể che giấu khoảng trống chất lượng.

Bài học này hướng dẫn cách xác định ranh giới kiểm thử, chọn mức chi tiết phù hợp, ghi nhận nội dung trong và ngoài phạm vi, phân biệt giả định với sự kiện đã xác nhận, thiết kế cách kiểm chứng giả định, quản lý thay đổi phạm vi và thực hành trên một tình huống cụ thể.

## 1. Hiểu phạm vi, phần loại trừ và giả định

### 1.1. Phạm vi kiểm thử

Phạm vi kiểm thử (*test scope*) mô tả các thành phần, hành vi, điều kiện và rủi ro mà hoạt động kiểm thử có trách nhiệm cung cấp bằng chứng. Phạm vi cần trả lời:

- Kiểm tra sản phẩm, module, service hoặc release nào?
- Hành vi và luồng nghiệp vụ nào cần xác minh?
- Vai trò, trạng thái và loại dữ liệu nào được xét?
- Tầng kiểm thử nào sẽ được sử dụng?
- Môi trường, nền tảng và cấu hình nào nằm trong kế hoạch?
- Mục tiêu hoặc rủi ro nào cần có bằng chứng?
- Điều kiện nào xác định hoạt động đã hoàn tất?

Phạm vi không chỉ là danh sách màn hình hoặc endpoint. Ví dụ, “kiểm thử checkout” cần làm rõ có bao gồm tính giá, mã giảm giá, quyền sở hữu giỏ hàng, tạo đơn, thanh toán, callback, retry và cập nhật trạng thái đơn hay không.

### 1.2. Phần loại trừ

Phần loại trừ (*out of scope* hoặc exclusion) ghi rõ nội dung không được xác minh trong hoạt động hiện tại. Nó có thể xuất phát từ:

- Không thuộc thay đổi hoặc mục tiêu của release.
- Đã có bằng chứng được chấp nhận ở một tầng hoặc dự án khác.
- Không được hỗ trợ trong phiên bản sản phẩm.
- Không có môi trường hoặc dependency cần thiết.
- Được thực hiện trong một kế hoạch riêng.
- Rủi ro thấp hơn các ưu tiên hiện tại và được chấp nhận có chủ đích.
- Bị giới hạn bởi thời gian, quyền hoặc nguồn lực.

Phần loại trừ không có nghĩa là nội dung đó không quan trọng. Nó chỉ có nghĩa là hoạt động hiện tại không cung cấp bằng chứng cho nội dung đó. Cần ghi lý do, tác động, owner và nơi hoặc thời điểm khác sẽ xử lý nếu vẫn cần kiểm tra.

### 1.3. Giả định cần kiểm chứng

Giả định (*assumption*) là điều được tạm coi là đúng để xây dựng phạm vi hoặc kế hoạch khi chưa có bằng chứng đầy đủ.

Ví dụ:

- API tương thích ngược với phiên bản client đang hỗ trợ.
- Sandbox thanh toán cho phép gửi callback lặp.
- Dữ liệu fixture có thể được tạo trong mỗi test run.
- Người dùng thử nghiệm có đủ vai trò để kiểm tra phân quyền.
- Migration có thể chạy trên bản sao dữ liệu đại diện.
- Browser grid có phiên bản trình duyệt đã cam kết.
- Service phụ thuộc sẽ sẵn sàng trong cửa sổ kiểm thử.

Giả định cần được viết thành phát biểu cụ thể, có người xác minh, cách kiểm tra và thời hạn. Nếu giả định sai, nhóm cần biết phạm vi, lịch hoặc quyết định nào sẽ thay đổi.

### 1.4. Phân biệt sự kiện, giả định, ràng buộc và rủi ro

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Sự kiện đã xác nhận | Có bằng chứng hoặc quyết định đáng tin cậy. | Payment sandbox đã được cấp và kiểm tra kết nối thành công. |
| Giả định | Tạm coi là đúng, cần xác minh. | Sandbox hỗ trợ callback trễ và gửi lặp. |
| Ràng buộc | Điều kiện giới hạn cách thực hiện. | Chỉ được dùng dữ liệu giả trong môi trường staging. |
| Phần loại trừ | Nội dung không được kiểm tra trong hoạt động hiện tại. | Không chạy kiểm thử tải lớn trong sprint này. |
| Rủi ro | Tình huống không chắc chắn có thể ảnh hưởng mục tiêu. | Không kiểm tra tải lớn có thể bỏ sót vấn đề khi lưu lượng tăng. |
| Phụ thuộc | Đầu vào hoặc dịch vụ cần từ bên khác. | Cần nhóm thanh toán cấp tài khoản sandbox. |

Không biến giả định thành sự kiện chỉ vì nó đã xuất hiện trong nhiều tài liệu. Không biến ràng buộc thành phần loại trừ nếu vẫn cần một phương án kiểm tra đáp ứng ràng buộc đó.

## 2. Xác định phạm vi từ mục tiêu và thay đổi

### 2.1. Bắt đầu bằng mục tiêu kiểm thử

Trước khi liệt kê test, hãy nêu kết quả cần xác minh. Mục tiêu nên mô tả hành vi hoặc rủi ro, không chỉ hoạt động kỹ thuật.

Ví dụ:

- Mục tiêu chưa rõ: “Kiểm thử API đơn hàng.”
- Mục tiêu rõ hơn: “Xác minh chỉ người dùng có quyền mới đọc và cập nhật được đơn hàng thuộc phạm vi của mình.”
- Mục tiêu chưa rõ: “Test thanh toán mới.”
- Mục tiêu rõ hơn: “Xác minh số tiền gửi nhà cung cấp chính xác, callback được xác thực và request lặp không tạo giao dịch trùng.”

Mục tiêu giúp xác định nội dung nào cần đưa vào phạm vi và bằng chứng nào là đủ.

### 2.2. Xác định thay đổi và vùng bị ảnh hưởng

Đọc thông tin thay đổi có thẩm quyền như yêu cầu, acceptance criteria, change request, thiết kế, API contract và release note. Xác định:

- Thành phần trực tiếp được sửa.
- Thành phần dùng chung bị ảnh hưởng.
- Consumer hoặc service phụ thuộc.
- Schema, event, cấu hình và feature flag liên quan.
- Hành trình người dùng đi qua thay đổi.
- Vai trò và dữ liệu có thể chịu tác động.
- Các lỗi hoặc incident trước đây ở cùng vùng.

Không chỉ kiểm tra file hoặc module được sửa. Một thay đổi ở contract có thể ảnh hưởng nhiều consumer; thay đổi schema có thể ảnh hưởng job nền và báo cáo.

### 2.3. Phân tích tác động theo chiều ngang và chiều dọc

Phân tích theo chiều ngang xem xét các thành phần có quan hệ với nhau:

- Service gọi service nào?
- API hoặc event nào được dùng chung?
- Dữ liệu đi qua những kho nào?
- Có dependency bên ngoài không?
- Có client, browser hoặc thiết bị nào tiêu thụ hành vi này?

Phân tích theo chiều dọc đi theo một luồng từ người dùng đến dữ liệu và vận hành:

1. Người dùng thực hiện hành động.
2. UI hoặc client gửi request.
3. API xác thực và phân quyền.
4. Service áp dụng quy tắc nghiệp vụ.
5. Dữ liệu được lưu hoặc sự kiện được phát.
6. Worker hoặc service khác xử lý.
7. Kết quả được phản ánh cho người dùng.
8. Log, metric và alert ghi nhận trạng thái.

Cả hai góc nhìn giúp phát hiện phần cần kiểm tra mà chỉ đọc danh sách file thay đổi có thể bỏ sót.

### 2.4. Xác định cấp độ và ranh giới

Phạm vi có thể được xác định theo:

- Sản phẩm hoặc release.
- Module, service hoặc API.
- Chức năng và user journey.
- Yêu cầu hoặc rủi ro.
- Tầng kiểm thử.
- Nền tảng, browser, thiết bị hoặc cấu hình.
- Dữ liệu, vai trò và trạng thái.
- Thời gian hoặc cửa sổ vận hành.

Ghi cả ranh giới đầu và cuối. Ví dụ, test API checkout có thể bắt đầu tại HTTP endpoint và kết thúc khi order record được lưu; nó không xác minh rendering của UI hoặc giao dịch thực với nhà cung cấp.

## 3. Chọn mức độ chi tiết của phạm vi

### 3.1. Tránh phạm vi quá rộng hoặc quá mơ hồ

Các mô tả như “kiểm thử toàn bộ hệ thống”, “đảm bảo chất lượng checkout” hoặc “test tất cả chức năng liên quan” không đủ để lập kế hoạch.

Cần phân rã thành:

- Hành vi thành công.
- Hành vi từ chối và lỗi.
- Trạng thái trước và sau thao tác.
- Vai trò và quyền.
- Dữ liệu hợp lệ, không hợp lệ và biên.
- Tích hợp và dependency.
- Quan sát và phục hồi.
- Nền tảng hoặc cấu hình cần hỗ trợ.

Không cần liệt kê từng test case ở tài liệu chiến lược, nhưng phải đủ cụ thể để test plan có thể được tạo mà không cần đoán mục tiêu.

### 3.2. Phân rã theo luồng nghiệp vụ

Ví dụ với chức năng đặt hàng:

| Nhóm hành vi | Nội dung có thể thuộc phạm vi |
|---|---|
| Giỏ hàng | Thêm, sửa, xóa sản phẩm; kiểm tra tồn kho và giá. |
| Tính tiền | Thuế, phí, mã giảm giá, làm tròn và đơn vị tiền tệ. |
| Quyền | Chủ giỏ hàng, người dùng khác, tài khoản bị khóa. |
| Tạo đơn | Trạng thái ban đầu, mã đơn và dữ liệu lưu. |
| Thanh toán | Request, callback, timeout, retry và idempotency. |
| Xử lý nền | Message, consumer, cập nhật trạng thái và lỗi xử lý. |
| Thông báo | Nội dung và thời điểm gửi email hoặc thông báo. |
| Lịch sử | Đơn xuất hiện đúng với người có quyền. |
| Vận hành | Log, trace, metric và khả năng điều tra. |

Từ danh sách này, nhóm chọn phần nằm trong phạm vi của thay đổi cụ thể và ghi rõ phần chưa được kiểm tra.

### 3.3. Phân rã theo trạng thái và vai trò

Một chức năng có thể thay đổi hành vi theo trạng thái hoặc quyền. Phạm vi nên xác định các chiều quan trọng:

- Người dùng chưa xác thực và đã xác thực.
- Chủ sở hữu và người không sở hữu.
- Tài khoản hoạt động, bị khóa hoặc hết hạn.
- Bản ghi mới, đang xử lý, hoàn tất hoặc bị hủy.
- Dữ liệu thiếu, sai định dạng, trùng hoặc vượt giới hạn.
- Request đầu tiên, request lặp và request đồng thời.
- Phản hồi thành công, từ chối, timeout và lỗi dependency.

Không cần kiểm tra mọi tổ hợp nếu số lượng quá lớn. Hãy ưu tiên tổ hợp theo rủi ro và ghi rõ ma trận được chọn.

### 3.4. Chọn tầng kiểm thử phù hợp

Phạm vi cần nói rõ bằng chứng được tạo ở tầng nào:

| Tầng | Phạm vi thường phù hợp |
|---|---|
| Unit/component | Quy tắc cục bộ, validation, tính toán và chuyển trạng thái. |
| Contract/API | Request, response, schema, xác thực và quyền ở ranh giới API. |
| Integration | Database, transaction, broker và dependency thật hoặc sandbox. |
| System/E2E | Hành trình xuyên thành phần và trải nghiệm người dùng. |
| Non-functional | Hiệu năng, tải, bảo mật, khả năng phục hồi và khả năng quan sát. |
| Manual/exploratory | Hành vi mới, vùng chưa rõ và tình huống khó liệt kê trước. |

Nếu mục tiêu là xác minh quyền truy cập API, UI test có thể bổ sung trải nghiệm nhưng không thay thế kiểm tra server-side. Nếu mục tiêu là rendering trên browser, API test không cung cấp bằng chứng đó.

## 4. Ghi rõ nội dung trong phạm vi

### 4.1. Mỗi mục trong phạm vi cần có lý do

Một mục nên có:

- Tên thành phần hoặc hành vi.
- Mục tiêu hoặc rủi ro được bảo vệ.
- Các trạng thái, vai trò và dữ liệu quan trọng.
- Tầng kiểm thử hoặc phương pháp.
- Môi trường và dependency.
- Bằng chứng dự kiến.
- Owner hoặc nhóm chịu trách nhiệm.

Ví dụ:

| Mục trong phạm vi | Lý do | Cách xác minh |
|---|---|---|
| Callback thanh toán hợp lệ và sai chữ ký | Rủi ro cập nhật trạng thái từ callback giả mạo. | API và integration test với sandbox. |
| Callback gửi lặp | Rủi ro tạo giao dịch hoặc tác dụng phụ trùng. | Integration test idempotency và đọc lại trạng thái. |
| Người dùng khác truy cập đơn | Rủi ro lộ dữ liệu và thao tác trái phép. | API authorization test với hai tài khoản. |
| Trạng thái đơn trên UI | Rủi ro người dùng thấy kết quả sai. | E2E test đại diện trên browser hỗ trợ. |

### 4.2. Phân biệt kiểm tra bắt buộc và kiểm tra bổ sung

Có thể gắn mức ưu tiên:

- **Bắt buộc:** cần bằng chứng trước quyết định hoàn tất hoặc phát hành.
- **Theo rủi ro:** chạy khi thay đổi, tín hiệu hoặc điều kiện kích hoạt xuất hiện.
- **Bổ sung:** cung cấp hiểu biết hoặc độ bao phủ thêm nhưng không phải gate hiện tại.
- **Định kỳ:** chạy theo lịch hoặc chu kỳ rộng hơn.

Mỗi loại cần có điều kiện kích hoạt. Không nên dùng nhãn “bổ sung” để âm thầm loại bỏ một kiểm tra bảo mật hoặc nghĩa vụ bắt buộc.

### 4.3. Liên kết với tiêu chí hoàn tất

Mỗi mục trong phạm vi nên liên kết với một tiêu chí có thể kiểm chứng. Ví dụ, “kiểm tra callback” chưa đủ; tiêu chí cần xác định callback hợp lệ cập nhật trạng thái, callback sai chữ ký bị từ chối và callback lặp không tạo tác dụng phụ.

Phạm vi trả lời kiểm tra cái gì; tiêu chí hoàn tất trả lời kết quả nào được xem là đạt.

## 5. Ghi rõ phần loại trừ và lý do

### 5.1. Phần loại trừ phải cụ thể

Tránh ghi chung “các kiểm thử khác nằm ngoài phạm vi”. Hãy nêu rõ:

- Nội dung hoặc hành vi không được kiểm tra.
- Nền tảng hoặc cấu hình không được chạy.
- Tầng kiểm thử không được thực hiện.
- Dữ liệu hoặc dependency không được sử dụng.
- Thời gian hoặc môi trường không nằm trong hoạt động.
- Lý do và người xác nhận.

Ví dụ:

| Phần loại trừ | Lý do | Rủi ro hoặc giới hạn |
|---|---|---|
| Kiểm thử tải lớn trên production | Không được phép tạo tải gây ảnh hưởng người dùng. | Hiệu năng tải lớn chỉ được xác minh trên môi trường riêng. |
| Browser phiên bản đã hết hỗ trợ | Không còn trong ma trận sản phẩm được cam kết. | Không cung cấp bằng chứng cho phiên bản cũ đó. |
| Tích hợp giao dịch thật với nhà cung cấp | Chỉ dùng sandbox trong kiểm thử. | Chưa xác minh toàn bộ luồng thanh toán production. |
| Kiểm thử di trú dữ liệu lịch sử | Thay đổi hiện tại không tác động schema và đã có kế hoạch riêng. | Cần liên kết đến hoạt động migration khác nếu có yêu cầu. |

### 5.2. Phân biệt ngoài phạm vi với chưa thể thực hiện

Hai trạng thái này khác nhau:

- **Ngoài phạm vi có chủ đích:** đã quyết định không kiểm tra trong hoạt động hiện tại.
- **Chưa thể thực hiện:** thuộc mục tiêu hoặc kế hoạch nhưng đang bị chặn bởi môi trường, dữ liệu, quyền hoặc dependency.

Ví dụ, kiểm thử browser phụ được yêu cầu nhưng browser grid đang hỏng là BLOCKED, không phải OUT OF SCOPE. Việc đổi trạng thái thành ngoài phạm vi để làm báo cáo gọn hơn sẽ che giấu một khoảng trống bằng chứng.

### 5.3. Đánh giá rủi ro của phần loại trừ

Với mỗi exclusion, hãy hỏi:

- Điều gì có thể xảy ra nếu không kiểm tra?
- Có người dùng hoặc tài sản quan trọng nào bị ảnh hưởng?
- Có bằng chứng khác giảm rủi ro không?
- Có thể kiểm tra ở release hoặc môi trường khác không?
- Có cần hạn chế rollout hoặc bật monitoring bổ sung không?
- Ai có quyền chấp nhận phần rủi ro còn lại?
- Khi nào phải xem xét lại?

Phần loại trừ rủi ro cao cần được escalation và phê duyệt. Người viết test plan không tự có quyền miễn trừ gate.

### 5.4. Không dùng phần loại trừ để né nghĩa vụ

Các yêu cầu pháp lý, hợp đồng, bảo mật, quyền riêng tư hoặc an toàn có thể không được loại khỏi phạm vi bởi quyết định thông thường của nhóm dự án. Nếu chưa rõ nghĩa vụ, cần hỏi owner chuyên môn và giữ trạng thái chưa được xác nhận.

Một mục không có người kiểm tra hoặc không có môi trường không tự động trở thành phần loại trừ hợp lệ.

## 6. Xác định và quản lý giả định

### 6.1. Viết giả định thành phát biểu có thể kiểm tra

Một giả định tốt nên cụ thể, có thể đúng hoặc sai và có cách xác minh.

Ví dụ chưa tốt: “Môi trường sẽ ổn định.”

Ví dụ tốt hơn: “Môi trường integration sẽ có database schema phiên bản X, broker hoạt động và payment sandbox truy cập được trước ngày bắt đầu E2E.”

Ví dụ chưa tốt: “Dữ liệu test có sẵn.”

Ví dụ tốt hơn: “Data owner sẽ cung cấp fixture cho ba vai trò và hai trạng thái đơn hàng trong namespace riêng trước khi test runner khởi chạy.”

### 6.2. Phân loại giả định

Có thể nhóm giả định theo nguồn:

- **Nghiệp vụ:** quy tắc hoặc hành vi được hiểu theo cách đã nêu.
- **Kỹ thuật:** contract, kiến trúc hoặc dependency hoạt động theo mô tả.
- **Môi trường:** phiên bản, cấu hình và tài nguyên sẵn sàng.
- **Dữ liệu:** fixture, chất lượng và quyền sử dụng đáp ứng nhu cầu.
- **Nguồn lực:** người có kỹ năng và thời gian sẵn có.
- **Vận hành:** monitoring, rollback và hỗ trợ có thể được sử dụng.
- **Bên ngoài:** nhà cung cấp, sandbox hoặc dịch vụ thứ ba đáp ứng điều kiện.

Phân loại giúp giao giả định cho đúng owner.

### 6.3. Ghi owner và hạn xác minh

Mỗi giả định nên có:

- Assumption ID.
- Nội dung.
- Cơ sở hoặc nguồn hình thành.
- Owner xác minh.
- Cách kiểm chứng.
- Thời hạn hoặc mốc cần xác minh.
- Hậu quả nếu sai.
- Trạng thái.
- Hành động tiếp theo.

Ví dụ:

| ID | Giả định | Cách kiểm chứng | Owner | Hạn |
|---|---|---|---|---|
| A-01 | Sandbox hỗ trợ callback lặp. | Gửi hai callback cùng transaction ID trong môi trường thử nghiệm. | Payment integration owner | Trước integration test |
| A-02 | Có tài khoản cho ba vai trò. | Đăng nhập và xác minh quyền từng tài khoản. | QA data owner | Trước E2E |
| A-03 | Migration tương thích dữ liệu hiện tại. | Chạy migration trên snapshot đã xử lý và đối soát. | Database owner | Trước release candidate |
| A-04 | Browser grid có phiên bản được hỗ trợ. | Chạy capability check và smoke test. | QA automation owner | Trước full regression |

### 6.4. Ưu tiên giả định theo hậu quả nếu sai

Không phải giả định nào cũng cần xác minh ngay. Ưu tiên theo:

- Mức ảnh hưởng nếu giả định sai.
- Khả năng giả định sai.
- Thời điểm cần kết quả.
- Thời gian cần để xác minh.
- Mức độ ảnh hưởng đến các công việc khác.
- Khả năng có phương án thay thế.

Giả định có thể chặn toàn bộ test hoặc ảnh hưởng release cần được xác minh sớm. Một giả định ít tác động và dễ đảo ngược có thể được theo dõi trong quá trình thực hiện.

## 7. Thiết kế cách kiểm chứng giả định

### 7.1. Chọn phương pháp theo loại giả định

| Loại giả định | Cách kiểm chứng có thể dùng |
|---|---|
| Nghiệp vụ | Review với product owner, ví dụ acceptance criteria, prototype hoặc workshop. |
| Contract/API | Contract test, schema validation và thử request/response. |
| Dependency | Health/readiness probe, sandbox call và integration test. |
| Môi trường | Environment smoke, version check, quota và network check. |
| Dữ liệu | Validate schema, sample review, fixture creation và đối soát. |
| Nguồn lực | Xác nhận lịch, kỹ năng, owner và quyền truy cập. |
| Hiệu năng | Benchmark hoặc load test trên môi trường đại diện. |
| Vận hành | Walkthrough runbook, diễn tập rollback và xác minh alert. |

Không chọn phương pháp chỉ vì nó dễ thực hiện. Cần bảo đảm nó kiểm tra đúng điều giả định đang khẳng định.

### 7.2. Xác định tiêu chí xác nhận hoặc bác bỏ

Mỗi phép kiểm chứng cần có kết quả mong đợi. Ví dụ, giả định “sandbox hỗ trợ callback lặp” có thể được xác nhận khi:

- Có thể gửi cùng transaction ID nhiều lần.
- Hệ thống nhận diện request lặp.
- Chỉ có một giao dịch hoặc tác dụng phụ được ghi nhận.
- Trạng thái cuối cùng nhất quán.
- Log/trace đủ để đối chiếu.

Nếu chỉ nhận được HTTP 200 từ endpoint, chưa đủ chứng minh hành vi idempotency.

### 7.3. Xử lý khi giả định sai

Khi giả định bị bác bỏ:

1. Ghi bằng chứng và thời điểm.
2. Đánh giá mục tiêu, test và lịch bị ảnh hưởng.
3. Xác định giả định thay thế có cơ sở hay không.
4. Điều chỉnh phạm vi, phương pháp hoặc nguồn lực.
5. Đánh giá rủi ro và phần loại trừ mới.
6. Xin phê duyệt nếu thay đổi ảnh hưởng gate hoặc cam kết.
7. Thông báo cho nhóm bị ảnh hưởng.
8. Cập nhật tài liệu và trạng thái giả định.

Không tiếp tục dùng giả định cũ trong các tài liệu khác sau khi đã có bằng chứng bác bỏ.

### 7.4. Phân biệt giả định đã xác nhận với điều kiện vẫn đang theo dõi

Có thể dùng các trạng thái:

- OPEN: chưa xác minh.
- VALIDATING: đang kiểm chứng.
- CONFIRMED: có bằng chứng hỗ trợ.
- REJECTED: bằng chứng bác bỏ.
- SUPERSEDED: được thay bằng giả định hoặc quyết định mới.
- ACCEPTED RISK: chưa xác minh nhưng rủi ro được chấp nhận đúng thẩm quyền và có thời hạn.

CONFIRMED không có nghĩa giả định đúng vĩnh viễn. Khi môi trường, phiên bản hoặc dependency thay đổi, cần xác minh lại nếu điều kiện ban đầu không còn đúng.

## 8. Phân biệt phạm vi, ràng buộc và phụ thuộc

### 8.1. Ràng buộc

Ràng buộc là điều kiện phải tuân thủ khi thực hiện, ví dụ:

- Chỉ kiểm thử trên staging.
- Không gửi email hoặc giao dịch thật.
- Chỉ sử dụng dữ liệu giả.
- Không thực hiện tải cao trong giờ làm việc.
- Chỉ sử dụng phiên bản browser được hỗ trợ.
- Không truy cập dữ liệu production.

Ràng buộc không phải lý do để bỏ mục tiêu. Hãy tìm phương pháp khác đáp ứng mục tiêu trong giới hạn đó hoặc ghi rõ khoảng trống cần quyết định.

### 8.2. Phụ thuộc

Phụ thuộc là đầu vào cần từ một nhóm, service, công cụ hoặc nhà cung cấp:

- Tài khoản sandbox.
- Schema hoặc API contract.
- Fixture từ data owner.
- Quyền truy cập network.
- Browser/device grid.
- Build của service khác.
- Lịch review bảo mật.
- Hỗ trợ từ operations.

Phụ thuộc cần owner, thời điểm cần có và phương án khi trễ. Không ghi “đang chờ” mà không có người chịu trách nhiệm.

### 8.3. Phần loại trừ và phụ thuộc chưa sẵn sàng

Nếu một phụ thuộc chưa sẵn sàng, nội dung cần kiểm tra vẫn có thể nằm trong phạm vi nhưng trạng thái là BLOCKED. Chỉ chuyển thành exclusion khi có quyết định rõ, lý do, đánh giá rủi ro và thẩm quyền chấp nhận.

Ví dụ, payment sandbox chưa được cấp không làm mục tiêu xác minh tích hợp tự biến mất. Nhóm có thể tiếp tục unit/contract test nhưng phải ghi phần integration đang bị chặn.

## 9. Liên kết phạm vi với rủi ro và ma trận truy vết

### 9.1. Từ mục tiêu đến phạm vi

Với mỗi mục tiêu, ghi:

- Rủi ro liên quan.
- Phần kiểm thử nằm trong phạm vi.
- Phần loại trừ nếu có.
- Giả định cần xác minh.
- Test hoặc hoạt động tạo bằng chứng.
- Tiêu chí hoàn tất.
- Owner và trạng thái.

Điều này giúp reviewer nhìn thấy mục tiêu nào được bảo vệ và mục tiêu nào còn khoảng trống.

### 9.2. Ma trận ví dụ

| Mục tiêu/rủi ro | Trong phạm vi | Loại trừ | Giả định cần kiểm chứng | Bằng chứng |
|---|---|---|---|---|
| Tính đúng tổng tiền | Unit/API cho thuế, phí, giảm giá và biên | Không kiểm tra hóa đơn giấy | Quy tắc làm tròn được product xác nhận | Unit test, API result |
| Ngăn callback giả mạo | Kiểm tra chữ ký và quyền cập nhật trạng thái | Không gửi callback thật từ production | Sandbox dùng cùng thuật toán xác minh | Contract và integration test |
| Ngăn giao dịch trùng | Callback lặp, retry và idempotency | Không kiểm tra tải cực đại trong sprint | Sandbox cho phép phát lại callback | Integration test và trace |
| Hiển thị trạng thái đơn | E2E trên browser chính | Browser cũ ngoài ma trận hỗ trợ | Browser grid có phiên bản chuẩn | E2E report và screenshot |
| Khả năng phục hồi | Timeout và service restart trong test env | Không fault injection trên production | Có thể cô lập service test | Recovery test và log |

Ma trận là công cụ lập kế hoạch, không phải bằng chứng thực thi. Cần cập nhật trạng thái sau khi test chạy.

### 9.3. Phát hiện khoảng trống

Có thể tìm các trường hợp:

- Mục tiêu có rủi ro nhưng không có test.
- Test có nhưng không liên kết mục tiêu hoặc rủi ro.
- Mục trong phạm vi không có môi trường hoặc dữ liệu.
- Exclusion không có lý do hoặc owner.
- Giả định chưa xác minh nhưng đã được dùng làm cơ sở cho lịch.
- Bằng chứng thay thế không kiểm tra cùng hành vi.
- Rủi ro cao bị loại khỏi phạm vi mà không có quyết định.

Các khoảng trống cần được phân loại và giao người xử lý trước mốc quyết định tương ứng.

## 10. Quản lý thay đổi phạm vi

### 10.1. Trigger cần xem xét lại phạm vi

Phạm vi cần được đánh giá lại khi:

- Yêu cầu hoặc acceptance criteria thay đổi.
- Kiến trúc, API, schema hoặc dependency thay đổi.
- Có defect nghiêm trọng hoặc production escape.
- Môi trường, dữ liệu hoặc công cụ không đáp ứng.
- Lịch hoặc nguồn lực thay đổi.
- Một giả định quan trọng bị bác bỏ.
- Có nền tảng hoặc nhóm người dùng mới.
- Chính sách hoặc nghĩa vụ thay đổi.

Không chờ đến cuối dự án nếu thông tin mới làm kế hoạch hiện tại không còn đúng.

### 10.2. Đánh giá tác động trước khi thay đổi

Trước khi thêm hoặc bỏ phạm vi, xem xét:

- Mục tiêu và rủi ro nào bị ảnh hưởng?
- Test hoặc bằng chứng nào cần thêm, bỏ hoặc thay đổi?
- Lịch và effort thay đổi bao nhiêu?
- Có cần môi trường, dữ liệu hoặc kỹ năng mới?
- Phần loại trừ nào được tạo ra?
- Rủi ro còn lại là gì?
- Ai có quyền phê duyệt?

Thay đổi làm giảm bằng chứng cho rủi ro cao cần được review và phê duyệt theo chính sách, không chỉ cập nhật tài liệu.

### 10.3. Giữ lịch sử và baseline

Ghi lại:

- Phiên bản phạm vi trước và sau.
- Nội dung thêm/bớt.
- Lý do và nguồn yêu cầu.
- Người đề xuất, reviewer và approver.
- Tác động đến lịch, nguồn lực và rủi ro.
- Ngày hiệu lực.
- Kết quả xác minh sau thay đổi.

Baseline giúp biết nhóm đã cam kết kiểm tra điều gì tại thời điểm đưa ra quyết định.

### 10.4. Không thay đổi trạng thái để làm đẹp báo cáo

Các trạng thái cần giữ đúng bản chất:

- PASS: tiêu chí đã được kiểm tra và đạt.
- FAIL: kiểm tra đã chạy và không đạt.
- BLOCKED: thuộc phạm vi nhưng chưa thể thực hiện.
- NOT RUN: chưa được thực thi.
- OUT OF SCOPE: được loại trừ có chủ đích.
- WAIVED: rủi ro hoặc tiêu chí được miễn có phê duyệt.

BLOCKED không phải OUT OF SCOPE; WAIVED không phải PASS. Báo cáo phải thể hiện khoảng trống bằng chứng và quyết định quản trị riêng.

## 11. Thực hành: xác định phạm vi cho thay đổi checkout

Giả sử sản phẩm bổ sung phương thức thanh toán mới. Nhóm cần xác minh người dùng có thể thanh toán đúng số tiền, callback được xử lý an toàn và đơn hàng phản ánh trạng thái chính xác.

### 11.1. Viết mục tiêu

- Tính tiền đúng theo giá, thuế, phí và giảm giá.
- Chỉ chủ đơn hàng được phép khởi tạo thanh toán.
- Callback phải được xác thực.
- Request hoặc callback lặp không tạo giao dịch trùng.
- Trạng thái đơn nhất quán sau thành công, thất bại hoặc timeout.
- Người dùng nhận được phản hồi phù hợp với trạng thái giao dịch.

### 11.2. Xác định phần trong phạm vi

| Hạng mục | Phương pháp | Lý do |
|---|---|---|
| Quy tắc tính tiền và giá trị biên | Unit/API | Kiểm tra tính đúng và các ranh giới dữ liệu. |
| Quyền sở hữu đơn | API authorization | Bảo vệ dữ liệu và thao tác trái phép. |
| Callback hợp lệ và sai chữ ký | Contract/integration | Xác minh hợp đồng và kiểm soát xác thực. |
| Callback lặp và timeout | Integration/recovery | Kiểm tra idempotency và trạng thái nhất quán. |
| Hành trình thanh toán | E2E trên browser hỗ trợ | Xác minh trải nghiệm xuyên hệ thống. |
| Log và trace giao dịch | Observability check | Hỗ trợ điều tra và đối soát. |

### 11.3. Ghi phần loại trừ

- Không tạo giao dịch thật trên nhà cung cấp production.
- Không chạy stress test trên hệ thống production.
- Không kiểm tra browser đã hết hỗ trợ.
- Không thực hiện migration lịch sử nếu thay đổi hiện tại không sửa schema.

Mỗi exclusion cần lý do và đánh giá rủi ro. Ví dụ, không có giao dịch production nghĩa là nhóm chỉ có bằng chứng từ sandbox; nếu release cần xác minh hành vi thực với nhà cung cấp, cần một kế hoạch hoặc kiểm tra production an toàn riêng.

### 11.4. Ghi giả định cần kiểm chứng

| ID | Giả định | Kiểm chứng | Owner | Hạn |
|---|---|---|---|---|
| A-01 | Sandbox hỗ trợ callback lặp. | Phát lại callback cùng transaction ID. | Payment owner | Trước integration test |
| A-02 | Có tài khoản chủ đơn và người dùng khác. | Xác minh quyền và dữ liệu từng tài khoản. | QA data owner | Trước API/E2E |
| A-03 | Browser grid có phiên bản được hỗ trợ. | Capability check và smoke test. | QA automation | Trước E2E |
| A-04 | Log có transaction ID và correlation ID. | Tạo giao dịch thử và truy vấn trace. | Service owner | Trước test recovery |

### 11.5. Quyết định khi giả định không đúng

Nếu sandbox không hỗ trợ callback lặp, nhóm có thể:

1. Xác nhận có API hoặc công cụ test-support để mô phỏng callback.
2. Kiểm tra idempotency ở integration test với dependency giả lập có hợp đồng rõ.
3. Ghi giới hạn rằng callback từ nhà cung cấp thật chưa được xác minh.
4. Đánh giá rủi ro còn lại và yêu cầu người có thẩm quyền quyết định.
5. Không tuyên bố toàn bộ tích hợp callback đã đạt nếu bằng chứng chỉ bao phủ logic nội bộ.

Nếu tài khoản người dùng khác chưa được cấp, test quyền sở hữu vẫn nằm trong phạm vi nhưng bị BLOCKED. Nhóm cần giải quyết dependency hoặc xin quyết định ngoại lệ; không tự chuyển mục đó thành OUT OF SCOPE.

## 12. Mẫu tài liệu phạm vi, loại trừ và giả định

~~~text
Tên sản phẩm / module / release:
Mục tiêu kiểm thử:
Phiên bản / commit:
Owner:
Ngày lập:
Revision:

PHẠM VI TRONG
1. Thành phần / hành vi:
   - Mục tiêu hoặc Risk ID:
   - Vai trò / trạng thái / dữ liệu:
   - Tầng kiểm thử / phương pháp:
   - Môi trường / cấu hình:
   - Bằng chứng dự kiến:
   - Owner:
2. ...

PHẦN LOẠI TRỪ
1. Nội dung:
   - Lý do:
   - Tác động / rủi ro còn lại:
   - Phương án hoặc kế hoạch khác:
   - Người xác nhận / approver:
   - Thời điểm xem xét lại:
2. ...

GIẢ ĐỊNH CẦN KIỂM CHỨNG
1. Assumption ID:
   - Phát biểu:
   - Cơ sở:
   - Cách kiểm chứng:
   - Owner:
   - Hạn:
   - Hậu quả nếu sai:
   - Trạng thái:
2. ...

RÀNG BUỘC
- Môi trường:
- Dữ liệu:
- Bảo mật / quyền:
- Thời gian:
- Công cụ / license:
- Quy định khác:

PHỤ THUỘC
- Dependency:
- Owner:
- Thời điểm cần:
- Phương án khi trễ:

TIÊU CHÍ HOÀN TẤT:
RỦI RO CÒN LẠI:
THAY ĐỔI ĐÃ PHÊ DUYỆT:
NGƯỜI XÁC NHẬN:
NGÀY REVIEW LẠI:
~~~

### 12.1. Checklist review trước khi thực thi

- [ ] Mục tiêu kiểm thử mô tả kết quả và rủi ro cần xác minh.
- [ ] Thành phần, hành vi, vai trò, trạng thái và dữ liệu được xác định.
- [ ] Ranh giới đầu/cuối của mỗi luồng được mô tả.
- [ ] Tầng kiểm thử và bằng chứng phù hợp với mục tiêu.
- [ ] Phần loại trừ có nội dung, lý do và tác động rõ.
- [ ] BLOCKED được phân biệt với OUT OF SCOPE.
- [ ] Giả định có thể kiểm chứng, owner và thời hạn.
- [ ] Ràng buộc và phụ thuộc được ghi nhận.
- [ ] Giả định rủi ro cao được xác minh trước mốc cần thiết.
- [ ] Mục tiêu và rủi ro truy vết đến test và tiêu chí hoàn tất.
- [ ] Phần giảm phạm vi có review và phê duyệt đúng thẩm quyền.
- [ ] Có quy trình cập nhật khi thay đổi hoặc giả định sai.

## 13. Những sai lầm thường gặp

- **Ghi phạm vi quá chung:** người thực hiện phải tự đoán hành vi và điều kiện.
- **Chỉ liệt kê module:** bỏ sót trạng thái, vai trò, dữ liệu và dependency.
- **Không ghi phần loại trừ:** người đọc mặc định mọi thứ đều đã được kiểm tra.
- **Dùng OUT OF SCOPE cho nội dung bị BLOCKED:** che giấu khoảng trống bằng chứng.
- **Giả định không có owner:** không ai xác minh điều kiện nền.
- **Dùng giả định như sự kiện:** kế hoạch dựa trên điều chưa được chứng minh.
- **Không đánh giá rủi ro của exclusion:** bỏ kiểm tra mà không hiểu hậu quả.
- **Dùng mock nhưng tuyên bố tích hợp thật đạt:** bằng chứng không tương đương mục tiêu.
- **Không cập nhật phạm vi khi thay đổi:** tài liệu không còn phản ánh sản phẩm.
- **Không giữ baseline:** không biết quyết định trước đó đã cam kết điều gì.
- **Gộp waiver vào PASS:** báo cáo che giấu rủi ro còn lại.
- **Không liên kết phạm vi với nguồn lực:** cam kết không có người, thời gian hoặc môi trường để thực hiện.

## 14. Đánh giá chất lượng phạm vi trước khi phê duyệt

Một phạm vi tốt cần đáp ứng các câu hỏi:

1. Mục tiêu và rủi ro được mô tả rõ chưa?
2. Người đọc có thể xác định chính xác hành vi nào được kiểm tra không?
3. Vai trò, trạng thái, dữ liệu và môi trường có được xác định không?
4. Phần loại trừ có lý do và người chịu trách nhiệm không?
5. Giả định quan trọng có cách xác minh và hạn không?
6. Ràng buộc có phương pháp thực hiện tương ứng không?
7. Dependency có owner và phương án khi trễ không?
8. Bằng chứng dự kiến có đủ mạnh cho quyết định không?
9. Có nguồn lực và lịch để thực hiện không?
10. Rủi ro còn lại có được ghi nhận và chấp nhận đúng thẩm quyền không?

Nếu câu trả lời còn thiếu ở một mục quan trọng, phạm vi chưa đủ cơ sở để phê duyệt. Có thể phê duyệt có điều kiện khi các điều kiện, owner và mốc hoàn thành được ghi rõ; không nên dùng trạng thái phê duyệt chung để che giấu phần chưa giải quyết.

## Kết luận

Xác định phạm vi kiểm thử cần làm rõ nội dung được kiểm tra, phần được loại trừ và các giả định đang dùng để lập kế hoạch. Phạm vi phải xuất phát từ mục tiêu và rủi ro, được phân rã theo hành vi, vai trò, trạng thái, dữ liệu và tầng kiểm thử. Phần loại trừ cần nêu lý do, tác động và thẩm quyền; giả định cần có cách kiểm chứng, owner và thời hạn. Khi các yếu tố này được liên kết với tiêu chí hoàn tất, nguồn lực và bằng chứng, nhóm có thể lập kế hoạch thực tế, nhận diện khoảng trống sớm và đưa ra quyết định chất lượng minh bạch.
