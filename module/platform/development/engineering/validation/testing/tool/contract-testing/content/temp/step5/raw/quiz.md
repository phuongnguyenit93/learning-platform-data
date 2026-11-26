Câu 1: Trong consumer-driven contract testing, ai xác định tương tác cần được bảo đảm?
A. Provider tự chọn tất cả trường trả ra cho mọi client
B. API gateway tự suy hợp đồng từ request ở production
C. Database tự tạo hợp đồng từ các bảng đang lưu trữ
D. Consumer mô tả request/response mà nó phụ thuộc
Đáp án đúng: D

Câu 2: Trong Pact, consumer test thường tương tác với thành phần nào?
A. Mock provider mô phỏng các tương tác đã mô tả
B. Provider production qua kết nối công khai Internet
C. Cơ sở dữ liệu provider mà không gọi HTTP
D. Pact Broker thay provider trả dữ liệu nghiệp vụ
Đáp án đúng: A

Câu 3: Một pact file cho tương tác HTTP thường chứa gì?
A. Toàn bộ bytecode của consumer và provider
B. Mật khẩu gọi API đã dùng trong môi trường thật
C. Các request mong đợi và response tương ứng
D. Bản snapshot database tại thời điểm phát hành
Đáp án đúng: C

Câu 4: Provider verification của Pact dùng để xác nhận điều gì?
A. Provider hiện tại đáp ứng các tương tác trong pact
B. Consumer thực hiện tất cả thao tác giao diện thành công
C. Mọi service của hệ thống đều đạt SLA về hiệu năng
D. Provider đã triển khai tới mọi môi trường production
Đáp án đúng: A

Câu 5: Provider state trong Pact được dùng để làm gì?
A. Gắn commit Git lên request khi gửi từ mock provider
B. Chuẩn bị dữ liệu để thử đúng tương tác được mô tả
C. Tự tăng phiên bản hợp đồng sau một lần verification
D. Thay mọi matcher của consumer thành giá trị cố định
Đáp án đúng: B

Câu 6: Vì sao response có ID sinh động nên dùng matcher phù hợp trong Pact?
A. Bỏ kiểm tra toàn bộ JSON response của provider
B. Ép provider luôn phát lại ID từ lần chạy đầu tiên
C. Đặt mọi trường trong response bằng giá trị null
D. Kiểm kiểu dữ liệu thay vì khóa cứng ID cụ thể
Đáp án đúng: D

Câu 7: Nếu consumer chỉ đọc field status từ JSON response, hợp đồng nên nhấn mạnh gì?
A. Trường status và ràng buộc giá trị mà consumer cần
B. Mọi field provider trả về dù consumer không sử dụng
C. Toàn bộ schema database mà provider đang quản lý
D. Mọi HTTP header do reverse proxy tự thêm vào
Đáp án đúng: A

Câu 8: Khi request chứa query parameter ảnh hưởng lựa chọn dữ liệu, pact cần thể hiện gì?
A. Chỉ hostname môi trường kiểm thử của consumer
B. Method, path và query cần cho hành vi đó
C. Chỉ content length của body ở request đầu tiên
D. Chỉ số lần retry của client khi gặp lỗi mạng
Đáp án đúng: B

Câu 9: Một Pact consumer test pass nhưng provider chưa chạy verification nói lên gì?
A. Consumer đúng với mock, provider chưa được xác minh
B. Provider thật đã thực hiện đầy đủ tất cả tương tác pact
C. Mọi môi trường triển khai provider đã được xác minh
D. Hợp đồng có thể xóa vì không còn phụ thuộc bên ngoài
Đáp án đúng: A

Câu 10: Vì sao phải cô lập dữ liệu giữa các provider-state test?
A. Tránh lệ thuộc dữ liệu và thứ tự của test trước
B. Để tất cả test dùng chung ID rồi tránh phải setup
C. Để không cần reset cơ sở dữ liệu sau khi kiểm tra
D. Để chỉ chạy một test mỗi lần và bỏ thử song song
Đáp án đúng: A

Câu 11: Pact Broker chủ yếu hỗ trợ công việc nào?
A. Lưu toàn bộ payload production để làm traffic replay
B. Lưu pact và kết quả verification giữa các phiên bản
C. Triển khai source Java trực tiếp tới các server đích
D. Thay thế hoàn toàn gateway của tất cả HTTP API
Đáp án đúng: B

Câu 12: Tính năng can-i-deploy của Pact Broker giúp quyết định gì?
A. Ứng dụng có đủ dung lượng RAM để chạy production
B. Mỗi build đã chạy đủ số lượng unit test bắt buộc
C. Máy chủ đã cập nhật hệ điều hành lên bản mới nhất
D. Kiểm tra tương thích bản phát hành tại môi trường đích
Đáp án đúng: D

Câu 13: Vì sao cần gắn đúng phiên bản consumer khi publish pact?
A. Để Pact Broker đổi mã nguồn consumer tự động
B. Để provider không cần xác minh pact ở lần kế tiếp
C. Để truy vết hợp đồng về bản consumer đã tạo nó
D. Để tất cả hợp đồng cũ bị xóa mỗi khi CI chạy
Đáp án đúng: C

Câu 14: Khi provider phát hành bản mới, bước nào giúp phát hiện phá vỡ tương thích?
A. Chỉ chạy unit test nội bộ không phụ thuộc consumer
B. Verify pact của các consumer với phiên bản provider mới
C. Chỉ so sánh timestamp của hai bản container image
D. Chỉ cập nhật OpenAPI title mà không chạy verification
Đáp án đúng: B

Câu 15: Với hợp đồng response JSON, thêm field tùy chọn thường có hệ quả gì?
A. Có thể tương thích nếu consumer không cần field mới
B. Luôn phá vỡ mọi consumer dù không ai đọc field mới
C. Luôn khiến Pact Broker xóa kết quả verification cũ
D. Tự động thay đổi HTTP method trên toàn bộ endpoint
Đáp án đúng: A

Câu 16: Đổi tên field JSON bắt buộc mà consumer đang dùng gây rủi ro gì?
A. Consumer có thể không đọc được dữ liệu như hợp đồng
B. Provider tự chèn lại tên cũ khi trả response HTTP
C. Pact tự sửa mã nguồn Java của consumer đã triển khai
D. Gateway tự đổi tên JSON key trong mọi response
Đáp án đúng: A

Câu 17: Khi provider có trạng thái dữ liệu không tồn tại, nên mô tả tương tác nào?
A. Chỉ request thành công và bỏ các tình huống không có
B. Chỉ mock timeout thay cho mọi lỗi nghiệp vụ
C. Request tương ứng và response lỗi như HTTP 404
D. Chỉ kiểm tra log database không có response
Đáp án đúng: C

Câu 18: Vì sao không nên khóa cứng timestamp biến đổi vào kỳ vọng contract?
A. Làm Pact không thể kiểm tra các field JSON số nguyên
B. Làm test mong manh khi provider trả thời điểm mới
C. Làm provider luôn ghi đè timezone của mọi consumer
D. Làm test mất khả năng xác minh HTTP status code
Đáp án đúng: B

Câu 19: Pact dùng matching rule cho một field số nhằm mục đích gì?
A. Thay phần verify provider bằng phép đo tốc độ xử lý
B. Bỏ kiểm tra field đó khỏi response mặc định
C. Ép provider sinh đúng số thứ tự của request
D. Kiểm kiểu hoặc điều kiện thay vì giá trị cố định
Đáp án đúng: D

Câu 20: Trong luồng CI, webhook của Pact Broker có thể hỗ trợ gì?
A. Tự sửa lỗi tương thích API trong source code Java
B. Tự tạo database production cho mỗi consumer mới
C. Tự cấp quyền admin cho mọi thành viên release
D. Kích hoạt verify khi hợp đồng Pact được cập nhật
Đáp án đúng: D

Câu 21: Kiểm thử hợp đồng message/event khác HTTP ở đối tượng được kiểm gì?
A. Chỉ status code của HTTP gateway trung gian
B. Chỉ class exception nội bộ của Java publisher
C. Payload và metadata của message mà bên nhận sử dụng
D. Chỉ thời gian giữ kết nối TCP giữa hai service
Đáp án đúng: C

Câu 22: Trong Spring Cloud Contract, bản hợp đồng thường mô tả điều gì?
A. Phương thức getter của mọi entity trong database
B. Thứ tự build tất cả service trong một hệ thống
C. Đầu vào yêu cầu và đầu ra mong đợi của provider
D. Số thread tối đa của ứng dụng khi phát tải
Đáp án đúng: C

Câu 23: Spring Cloud Contract có thể sinh loại kiểm thử nào cho provider?
A. Benchmark JMH đo tốc độ từng phương thức nội bộ
B. Test xác minh provider thực thi đúng contract
C. Kiểm thử trình duyệt tự sinh cho mọi màn hình UI
D. Migration SQL tự sinh theo schema của database
Đáp án đúng: B

Câu 24: Stub của Spring Cloud Contract có ích gì với consumer?
A. Thay provider production trong tất cả request thật
B. Chứng minh provider hiện tại đã vượt mọi test khi stub chạy
C. Mô phỏng hành vi provider để consumer test độc lập
D. Tự lưu tất cả giao dịch HTTP vào database của consumer
Đáp án đúng: C

Câu 25: Nếu consumer test dùng stub thuộc phiên bản provider đã cũ, nguy cơ nào?
A. Test tự cập nhật stub mới nhất bất kể cấu hình version
B. Test pass dù hợp đồng provider hiện tại đã thay đổi
C. Provider hiện tại sẽ tự chỉnh response để giống stub cũ
D. Pact Broker sẽ chạy lại toàn bộ unit test ở consumer
Đáp án đúng: B

Câu 26: Khi dùng Spring Cloud Contract, vì sao cần chạy test sinh ra trên provider thật?
A. Để thay toàn bộ kiểm thử unit trước khi merge code
B. Để đo CPU của provider dưới mọi mức tải đồng thời
C. Để xác nhận implementation thực đáp ứng contract
D. Để loại bỏ mọi nhu cầu tích hợp service thật sau này
Đáp án đúng: C

Câu 27: Hợp đồng consumer/provider có thể thay thế hoàn toàn E2E test không?
A. Có, vì kiểm tra pact đồng nghĩa test đầy đủ hệ thống
B. Có, vì pact cũng đo tải và toàn bộ security policy
C. Có, vì mock provider luôn có đúng trạng thái production
D. Không, hợp đồng không bao quát mọi luồng tích hợp thực
Đáp án đúng: D

Câu 28: Quy trình CI hợp lý khi consumer thay đổi yêu cầu API là gì?
A. Chỉ đẩy mã consumer, bỏ qua verification của provider
B. Chỉ publish pact mới mà không chạy các bài consumer test
C. Chỉ thay đổi tag release rồi coi tương thích đã được xác nhận
D. Chạy consumer test, publish pact và verify provider
Đáp án đúng: D
