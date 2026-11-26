Một bài E2E cho hành trình đặt hàng nên kiểm chứng phạm vi nào?
A. Chỉ logic tính tiền của một hàm Java
B. Hành trình qua UI, API và dữ liệu
C. Chỉ schema JSON mà API công bố
D. Chỉ cách trình duyệt vẽ màu của nút
Đáp án đúng: B

Sau khi người dùng thanh toán thành công, assertion E2E nào mạnh nhất?
A. Chỉ xác nhận nút Thanh toán không bị ẩn
B. Chỉ xác nhận HTTP trả về status thành công
C. Đơn hàng có trạng thái và bản ghi phù hợp
D. Đếm số lần framework gọi hàm trong frontend
Đáp án đúng: C

Bài E2E thất bại do dữ liệu khách hàng từ lần chạy trước, cách phòng tránh nào phù hợp?
A. Khởi tạo và dọn dữ liệu riêng cho mỗi bài
B. Cho mọi bài dùng chung một tài khoản cố định
C. Tăng số lượt retry dù dữ liệu vẫn trùng
D. Chạy test theo thứ tự tên tệp để ổn định
Đáp án đúng: A

Khi kiểm thử giao diện thay đổi vị trí phần tử, locator nào thường bền hơn?
A. Locator theo vai trò và tên hiển thị ổn định
B. Locator theo thứ tự phần tử thứ ba trong DOM
C. Locator theo CSS class sinh động sau mỗi build
D. Locator theo tọa độ chuột đã ghi trong video
Đáp án đúng: A

Trong Selenium, cách nào phù hợp để chờ một nút có thể tương tác?
A. Ngủ một khoảng cố định sau mọi thao tác
B. Chờ đến khi toàn bộ test suite kết thúc
C. Chạy lại thao tác liên tục không có giới hạn
D. Dùng explicit wait cho nút tương tác được
Đáp án đúng: D

E2E lúc pass lúc fail vì nội dung tải bất đồng bộ, bước đầu nên kiểm tra gì?
A. Giảm timeout mọi bước xuống một giá trị nhỏ
B. Cơ chế đồng bộ với điều kiện sẵn sàng thực tế
C. Tắt mọi assertion cho phần giao diện tải chậm
D. Giữ trạng thái trình duyệt giữa nhiều bài test
Đáp án đúng: B

Khi nhiều job CI chạy E2E song song, làm sao tránh xung đột dữ liệu?
A. Dùng chung mã đơn hàng để dễ đối chiếu log
B. Cho job nhanh nhất được ưu tiên thao tác ghi
C. Tạo dữ liệu riêng cho mỗi job và lần chạy
D. Bật cache trình duyệt chung để giảm thời gian
Đáp án đúng: C

Với mục tiêu E2E xuyên suốt hệ thống, dùng mock toàn bộ backend gây hạn chế nào?
A. Làm bài test phụ thuộc trạng thái database thật
B. Không kiểm tra được nhiều nhánh UI phức tạp
C. Không chạy được các thao tác click trên trình duyệt
D. Bỏ sót lỗi tích hợp giữa UI và dịch vụ thật
Đáp án đúng: D

Khi dùng Playwright Java kiểm thử bảng kết quả cập nhật, cách chờ nào phù hợp?
A. Dựa vào assertion có cơ chế đợi trạng thái
B. Dùng Thread.sleep giống nhau cho mọi bảng
C. Tải lại trang liên tục sau mỗi lần nhấn nút
D. Chỉ kiểm tra kết quả ngay sau click đầu tiên
Đáp án đúng: A

Một hệ thống thanh toán gọi dịch vụ ngoài khó kiểm soát, môi trường E2E nên làm gì?
A. Dùng dữ liệu thẻ thật cho mọi lần chạy CI
B. Tắt bước thanh toán và chỉ kiểm tra giỏ hàng
C. Chấp nhận lỗi ngẫu nhiên từ dịch vụ bên thứ ba
D. Dùng sandbox với các kịch bản ổn định
Đáp án đúng: D

Khi bài E2E trên CI thất bại nhưng khó tái hiện, bằng chứng nào hữu ích?
A. Chỉ tổng số bước đã chạy trong suite
B. Screenshot, trace và log theo lần chạy
C. Tên nhánh Git mà không có thông tin lỗi
D. Chỉ thời gian hoàn thành bài test thành công
Đáp án đúng: B

Một bộ E2E quá chậm trên mỗi pull request, cách phân tầng nào phù hợp?
A. Bỏ tất cả E2E để chỉ chạy kiểm thử đơn vị
B. Chạy smoke trên PR, full suite theo lịch
C. Buộc mọi PR chạy full suite ở mọi hệ điều hành
D. Chạy một luồng duy nhất nhưng bỏ qua kết quả
Đáp án đúng: B

Bài E2E hiển thị thông báo thành công nhưng đơn hàng không được lưu; nên bổ sung gì?
A. Chỉ assertion màu sắc của thông báo trên UI
B. Chỉ kiểm tra địa chỉ URL có đổi sau submit
C. Đọc lại đơn hàng qua API hoặc database
D. Bỏ kiểm tra vì thông báo UI đã cho biết thành công
Đáp án đúng: C

Khi một bài E2E fail ngẫu nhiên, việc retry pass nên được hiểu thế nào?
A. Cần điều tra nguyên nhân thiếu ổn định
B. Là bằng chứng bài test hoàn toàn chính xác
C. Là lý do bỏ log từ lần fail đầu tiên
D. Là cách thay thế việc xác định điểm đồng bộ
Đáp án đúng: A

Page Object trong E2E thường giúp ích gì cho việc bảo trì?
A. Thay đổi test thành kiểm thử hiệu năng tự động
B. Cắt mọi kết nối thật tới dịch vụ phía sau
C. Bảo đảm không còn lỗi DOM sau mỗi lần cập nhật
D. Gom locator và thao tác của màn hình có nghĩa
Đáp án đúng: D

Khi test E2E tạo dữ liệu nhưng bước cuối fail, cách dọn dữ liệu nào phù hợp?
A. Chỉ dọn dữ liệu khi tất cả assertion đều pass
B. Chờ người chạy thủ công xóa dữ liệu sau CI
C. Đặt cleanup ở cơ chế chạy dù test thất bại
D. Tái sử dụng dữ liệu còn lại ở lần chạy tiếp
Đáp án đúng: C
