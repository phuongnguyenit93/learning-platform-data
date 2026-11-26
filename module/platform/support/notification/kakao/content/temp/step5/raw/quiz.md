Ứng dụng muốn người dùng xác thực bằng tài khoản Kakao; sản phẩm nào là điểm bắt đầu phù hợp?
A. Kakao Channel để đăng nhập thay tài khoản Kakao
B. Kakao Share để lưu refresh token của ứng dụng
C. Alimtalk để gửi mẫu thông báo từ doanh nghiệp
D. Kakao Login để cấp quyền đăng nhập theo OAuth
Đáp án đúng: D

Có access token từ Kakao Login; nhận định nào đúng về quyền gửi Alimtalk?
A. Token có thể dùng trực tiếp để gửi đến mọi số điện thoại
B. Token đăng nhập không tự cấp quyền gửi Alimtalk
C. Token cho phép duyệt mọi template mà không xét nhà cung cấp
D. Token tự biến ứng dụng thành tài khoản Kakao Channel
Đáp án đúng: B

Khi dùng Talk Message gửi tới bạn bè của người dùng, cần xét điều gì?
A. Mọi follower Channel mà không cần scope phù hợp
B. Chỉ số điện thoại bất kỳ do người gửi cung cấp
C. Danh sách thuê bao SMTP sẵn có trong doanh nghiệp
D. Quyền API và tập người nhận đủ điều kiện của ứng dụng
Đáp án đúng: D

Kakao Share khác Talk Message API ở hành vi điển hình nào?
A. Ứng dụng tự chọn người nhận mà không có bước UI
B. Bên cung cấp duyệt mẫu giao dịch để tự gửi đi
C. Máy chủ gửi im lặng mọi nội dung theo lịch hẹn
D. Người dùng chủ động chia sẻ qua giao diện Kakao
Đáp án đúng: D

Kakao Channel thường phù hợp với mục đích nào trong tích hợp doanh nghiệp?
A. Duy trì kênh chính thức để tương tác với khách hàng
B. Thay hoàn toàn hệ thống cấp access token của OAuth
C. Tự mở quyền đọc mọi cuộc trò chuyện cá nhân
D. Lưu chữ ký DKIM cho từng thông điệp KakaoTalk
Đáp án đúng: A

Một thông báo xác nhận giao dịch theo mẫu doanh nghiệp nên xem xét sản phẩm nào?
A. Talk Message như quyền nhắn mọi số điện thoại
B. Alimtalk với template và nhà cung cấp phù hợp
C. Kakao Share để hệ thống gửi tự động ngoài giao diện
D. Kakao Login như một API gửi thông báo theo lô
Đáp án đúng: B

Với Alimtalk dùng mẫu đã duyệt, lúc render nội dung cần kiểm soát gì?
A. Mọi biến đầu vào tự thành phần HTML có thể chạy
B. Chỉ cần lưu tên template mà không ghép dữ liệu
C. Tên biến và nội dung phải khớp quy tắc template
D. Có thể bỏ mọi trường bắt buộc trong mẫu đã duyệt
Đáp án đúng: C

Nhà cung cấp phản hồi đã nhận yêu cầu gửi Kakao; trạng thái nào phù hợp?
A. Đã tiếp nhận, cần theo dõi kết quả chuyển phát
B. Chắc chắn người nhận đã mở và xem tin nhắn
C. Mọi chi phí gửi được miễn vì HTTP trả thành công
D. Thông báo được coi là thất bại và retry ngay
Đáp án đúng: A

Refresh token của Kakao Login nên được quản lý theo cách nào?
A. Ghi token đầy đủ trong log để hỗ trợ kiểm tra
B. Đưa vào tham số URL để nhiều client cùng sử dụng
C. Dùng chung một token cho mọi tài khoản người dùng
D. Lưu an toàn, theo dõi hạn và làm mới đúng luồng
Đáp án đúng: D

Khi ứng dụng lưu access token để gọi Kakao API, điều gì cần tránh?
A. Đưa token vào log hoặc nội dung thông báo công khai
B. Giới hạn quyền truy cập token ở máy chủ ứng dụng
C. Cập nhật token khi hết hạn theo cơ chế được cấp
D. Lưu token trong kho secret phù hợp với vòng đời
Đáp án đúng: A

Một sự kiện đơn hàng bị retry có thể tạo hai lệnh gửi; cách nào ngăn trùng hiệu quả?
A. Đổi mã đơn hàng mỗi lần worker chạy lại job
B. Dùng idempotency key theo sự kiện nghiệp vụ
C. Bỏ message ID sau khi gửi để giải phóng bộ nhớ
D. Gửi lại ngay mọi job chưa thấy người nhận đọc
Đáp án đúng: B

Khi nhà cung cấp áp rate limit, cách tích hợp nào phù hợp?
A. Điều tiết queue, retry giới hạn và theo dõi hạn mức
B. Loại bỏ bước lưu trạng thái vì queue sẽ chậm
C. Tăng số worker đến khi mọi HTTP request được nhận
D. Tự dùng access token của người dùng khác để gửi
Đáp án đúng: A

Khi nhận callback trạng thái tin nhắn, cách xử lý nào đáng tin cậy?
A. Bỏ qua tương quan với yêu cầu gửi ban đầu
B. Dựa vào thứ tự đến để tự ghi đè mọi trạng thái
C. Xác thực nguồn và khử trùng lặp theo message ID
D. Tin tất cả POST công khai có trường status hợp lệ
Đáp án đúng: C

Khi provider báo template sai hoặc thiếu quyền, hướng xử lý phù hợp là gì?
A. Retry không giới hạn với cùng template bị từ chối
B. Coi lỗi validation như tín hiệu quá tải tạm thời
C. Sửa cấu hình/quyền, không retry mù cùng payload
D. Đổi danh tính người dùng trong token rồi thử lại
Đáp án đúng: C

Khi so sánh chi phí các kênh Kakao, nên thu thập số liệu nào?
A. Chỉ lượng bộ nhớ của máy phát triển ứng dụng
B. Số lượt gửi, kết quả và biểu phí theo kênh/provider
C. Chỉ thời gian tải trang đăng nhập Kakao Login
D. Số class Java được tạo cho mỗi thông báo
Đáp án đúng: B

Khi xử lý dữ liệu người nhận và nội dung thông báo, biện pháp nào quan trọng?
A. Chia sẻ token Kakao giữa mọi tài khoản trong hệ thống
B. Bỏ kiểm tra quyền vì đã có callback từ provider
C. Giới hạn dữ liệu, kiểm soát quyền và lưu vết phù hợp
D. Đưa thông tin cá nhân đầy đủ vào log truy cập chung
Đáp án đúng: C
