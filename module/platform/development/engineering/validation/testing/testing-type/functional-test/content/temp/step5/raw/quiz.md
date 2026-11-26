Câu 1. Với chức năng đăng nhập, test nào xác minh đúng quy tắc khóa tài khoản sau 5 lần sai?
A. Gửi 5 lần sai rồi thử đăng nhập đúng và kiểm tra khóa
B. Đăng nhập đúng 5 lần rồi kiểm tra không có thông báo
C. Gửi một mật khẩu sai rồi thử chuyển sang màn hình khác
D. Đăng nhập đúng một lần rồi đổi kích thước màn hình
Đáp án đúng: A

Câu 2. Sau POST tạo đơn trả 201 và orderId, xác nhận chức năng đầy đủ nên kiểm tra gì?
A. Chỉ đo thời gian phản hồi để biết thao tác thành công
B. Đọc lại đơn theo ID, đối chiếu các trường đã lưu
C. Chỉ đếm số dòng log được in sau thao tác tạo đơn
D. Chỉ kiểm tra rằng response là JSON cú pháp hợp lệ
Đáp án đúng: B

Câu 3. Với PATCH chỉ sửa địa chỉ nhận hàng, trường hợp nào phát hiện việc ghi đè dữ liệu ngoài ý muốn?
A. Đọc địa chỉ trước khi gửi yêu cầu cập nhật
B. Tạo thêm một đơn có địa chỉ nhận hàng tương tự
C. So sánh thời gian phản hồi trước và sau cập nhật
D. Kiểm tra địa chỉ mới và các trường khác giữ nguyên
Đáp án đúng: D

Câu 4. Sau khi xóa một bản ghi bằng API, oracle nào phù hợp khi hợp đồng quy định xóa hẳn?
A. GET theo ID trả kết quả không còn bản ghi đó
B. DELETE trả mã 200 dù bản ghi vẫn còn trong DB
C. Trình duyệt chuyển về trang danh sách đã lọc
D. Giao diện hiển thị thông báo mà không kiểm tra dữ liệu
Đáp án đúng: A

Câu 5. Với quy tắc chỉ quản trị viên được xóa người dùng, ca âm nào cần có?
A. Admin gửi DELETE cho tài khoản hợp lệ
B. Admin mở trang danh sách tài khoản đang hoạt động
C. User thường gửi DELETE, bị từ chối và dữ liệu còn
D. User thường đăng nhập rồi đọc hồ sơ của chính mình
Đáp án đúng: C

Câu 6. Một trường số lượng chỉ cho phép số nguyên 1–99; trường hợp nào kiểm tra biên dưới?
A. Nhập 50 và so với một đơn hàng bình thường
B. Nhập 0 và 1, xác minh từ chối và chấp nhận
C. Nhập 20 và 21, so thời gian xử lý từng giá trị
D. Nhập 99 và 100, xác minh biên trên của trường
Đáp án đúng: B

Câu 7. Giảm giá 10% chỉ áp dụng khi tổng đơn ít nhất 500.000 đồng; cặp ca nào nhạy với lỗi so sánh?
A. Tổng 100.000 và 200.000 đồng
B. Tổng 700.000 và 800.000 đồng
C. Tổng 499.999 và 500.000 đồng
D. Tổng 900.000 và 1.000.000 đồng
Đáp án đúng: C

Câu 8. Với hệ thống làm tròn tổng tiền đến đồng nguyên, bộ kiểm tra chức năng nào đáng ưu tiên?
A. Chỉ giá tiền chia hết cho 100, không có phần lẻ
B. Chỉ đơn có một mặt hàng, giá nguyên cố định
C. Chỉ đơn đã thanh toán bằng số dư ví điện tử
D. Giá trị sát ngưỡng làm tròn và tổng nhiều dòng
Đáp án đúng: D

Câu 9. API tạo giao dịch hỗ trợ idempotency key. Test nào kiểm tra hành vi đúng?
A. Gửi hai key khác nhau và yêu cầu cùng transactionId
B. Gửi lại cùng key và payload, không tạo hai giao dịch
C. Gửi một request thành công rồi xóa log trên server
D. Gửi hai payload khác nhau và bỏ qua mã trạng thái
Đáp án đúng: B

Câu 10. API GET /orders?status=PAID hoạt động đúng khi nào?
A. Chỉ trả đơn có trạng thái PAID theo dữ liệu nguồn
B. Trả tất cả đơn và chỉ đổi nhãn trạng thái ngoài UI
C. Chỉ trả đơn chưa thanh toán để người dùng dễ kiểm tra
D. Trả đơn theo thứ tự tạo dù trạng thái không phù hợp
Đáp án đúng: A

Câu 11. Với danh sách được phân trang và sắp theo createdAt, cách nào hạn chế lỗi trùng hoặc mất bản ghi khi thời gian trùng nhau?
A. Bỏ qua sort khi số lượng bản ghi tăng lên
B. Chỉ so số dòng ở trang đầu tiên của kết quả
C. Đổi toàn bộ dấu thời gian thành chuỗi không chuẩn
D. Thêm khóa phụ ổn định và kiểm tra ranh giới trang
Đáp án đúng: D

Câu 12. Form hiển thị lỗi thiếu email ở frontend nhưng backend vẫn nhận request không email; lỗi chức năng nào cần ghi nhận?
A. Kiểm tra chỉ ở UI, API chưa thực thi quy tắc tương ứng
B. Backend nhận JSON đúng nên mọi yêu cầu đã hợp lệ
C. Frontend có thông báo nên không cần thử endpoint
D. API chỉ cần xác nhận một header để bỏ qua email
Đáp án đúng: A

Câu 13. API tạo tài khoản phải từ chối email đã tồn tại; kết quả kiểm thử nào có ý nghĩa nhất?
A. Response chứa thông báo, bất kể tài khoản có được thêm
B. Response trả 200 và tạo hai tài khoản cùng địa chỉ email
C. Response báo xung đột và không thêm tài khoản trùng
D. Response tạo tên hiển thị khác nhưng giữ nguyên email
Đáp án đúng: C

Câu 14. Trong luồng đặt lại mật khẩu bằng token một lần, test nào phát hiện lỗi tái sử dụng?
A. Yêu cầu token mới rồi kiểm tra thời gian nhận email
B. Dùng token thành công, dùng lại phải bị từ chối
C. Mở trang login sau khi đã đổi xong mật khẩu
D. Chỉ đổi tên người dùng trước khi gửi yêu cầu token
Đáp án đúng: B

Câu 15. Sau đặt đơn, dịch vụ phát OrderCreated để cập nhật tồn kho bất đồng bộ; kỳ vọng chức năng nào phù hợp?
A. Tồn kho buộc phải đổi trước khi API đặt đơn trả về
B. API đặt đơn phải trả một sự kiện hoàn chỉnh trong body
C. Tồn kho đạt trạng thái mong đợi sau khi sự kiện xử lý
D. Mọi hệ thống phải dùng chung một transaction database
Đáp án đúng: C

Câu 16. Khi kiểm thử xử lý bất đồng bộ, cách assert nào giảm thất bại ngẫu nhiên do thời điểm chạy?
A. Sleep cố định 1 ms rồi so dữ liệu ngay lập tức
B. Chỉ kiểm tra rằng message đã được đưa lên queue
C. Chỉ kiểm tra log của consumer trước khi message tới
D. Chờ có giới hạn và kiểm tra điều kiện cuối mong đợi
Đáp án đúng: D

Câu 17. Tác vụ thanh toán có trạng thái Pending, Success và Failed; với timeout, test cần xác minh điều gì?
A. Timeout được phép tự đổi thành Success dù chưa xác nhận
B. Timeout phải tạo thêm giao dịch mới mà không ghi lại
C. Timeout luôn khiến tài khoản người dùng bị xóa
D. Trạng thái chưa xác định được xử lý và đối soát đúng
Đáp án đúng: D

Câu 18. Consumer có thể nhận lặp sự kiện trừ tiền; test nào chứng minh xử lý lặp an toàn?
A. Gửi một sự kiện rồi kiểm tra tốc độ hiển thị UI
B. Đọc queue khi chưa có dữ liệu nào được phát ra
C. Gửi lại cùng eventId, kiểm tra không trừ thêm tiền
D. Thay eventId ở mỗi lần gửi và bỏ kiểm tra số dư
Đáp án đúng: C

Câu 19. Một bộ lọc cho phép giá trị rỗng có nghĩa là không lọc; test nào phân biệt sai lệch?
A. Gửi giá trị hợp lệ rồi so dữ liệu với bộ lọc khác
B. Gửi rỗng và kiểm tra không loại nhầm bản ghi
C. Gửi ký tự đặc biệt rồi bỏ qua kết quả truy vấn
D. Gửi khóa không tồn tại rồi luôn kỳ vọng HTTP 500
Đáp án đúng: B

Câu 20. Sau sửa quy tắc khuyến mại, kế hoạch regression test nào phù hợp nhất?
A. Chỉ chạy lại test giao diện đăng nhập người dùng
B. Chỉ kiểm thử vùng code vừa thêm theo số dòng
C. Chạy lại ca giảm giá, biên và luồng tổng thanh toán
D. Chỉ kiểm thử một mức giá trung bình từng có kết quả
Đáp án đúng: C

Câu 21. Với một test case API, vì sao chỉ assert HTTP 200 thường chưa đủ?
A. Response có thể 200 nhưng dữ liệu nghiệp vụ sai
B. HTTP 200 luôn được trả trong mọi trường hợp lỗi
C. Mã trạng thái HTTP không bao giờ có ý nghĩa chức năng
D. Kiểm tra status code luôn làm API chạy không ổn định
Đáp án đúng: A

Câu 22. Payment callback được gửi hai lần bởi cổng thanh toán; test nào phản ánh hợp đồng chức năng đúng?
A. Mỗi callback tạo một khoản thanh toán mới trong hệ thống
B. Callback đầu cập nhật đơn nhưng callback sau xóa đơn đó
C. Callback sau bị bỏ qua dù callback đầu chưa xử lý thành công
D. Cùng paymentId chỉ ghi nhận một thanh toán thành công
Đáp án đúng: D

Câu 23. Khi người dùng ở hai timezone đặt lịch cho cùng thời điểm UTC, cần kiểm tra điều gì?
A. Hai máy bắt buộc hiển thị cùng giờ địa phương
B. Giá trị UTC tương đương dù giờ hiển thị khác nhau
C. Hệ thống bỏ thông tin offset sau khi ghi lịch
D. Lịch tạo sau phải tự chuyển sang múi giờ của server
Đáp án đúng: B

Câu 24. Khi yêu cầu thay đổi điều kiện hủy đơn, cách nào chọn test hồi quy có căn cứ?
A. Dựa trên truy vết yêu cầu tới kịch bản và điều kiện biên
B. Chỉ dùng danh sách test chạy nhanh nhất ở lần trước
C. Bỏ toàn bộ test cũ để viết lại chỉ từ giao diện hiện tại
D. Chọn ngẫu nhiên test từ các module không liên quan
Đáp án đúng: A
