Câu 1. Một API quản lý đơn hàng cần truy vấn đơn theo mã; đường dẫn nào biểu diễn tài nguyên rõ nhất?
A. GET /getOrder?orderId=123 để gọi thao tác đọc
B. POST /orders/find với lệnh truy vấn trong body
C. GET /orders/123 để lấy tài nguyên theo định danh
D. GET /executeOrder?id=123 để chạy xử lý nghiệp vụ
Đáp án đúng: C

Câu 2. Trước khi chốt hợp đồng API mới, cách nào phản ánh thiết kế theo nhu cầu consumer?
A. Xác định luồng sử dụng và dữ liệu consumer cần
B. Tạo schema theo toàn bộ cột database hiện hữu
C. Chỉ dùng payload do framework tự sinh từ entity
D. Chờ triển khai xong mới hỏi consumer về field
Đáp án đúng: A

Câu 3. Khi POST /orders tạo mới thành công, hợp đồng HTTP nào phù hợp nhất?
A. HTTP 200 mà không nêu tài nguyên vừa được tạo
B. HTTP 204 với body chứa toàn bộ order vừa tạo
C. HTTP 404 cho đến khi hệ thống tìm thấy order
D. HTTP 201 và Location trỏ tới order được tạo
Đáp án đúng: D

Câu 4. Trong PATCH cập nhật hồ sơ, vì sao hợp đồng phải phân biệt field vắng mặt và null?
A. Vắng mặt giữ nguyên, null có thể là xóa
B. Vắng mặt luôn có nghĩa đặt thành chuỗi rỗng
C. Null mặc định nghĩa là bỏ qua mọi thay đổi
D. JSON không cho phép property nhận giá trị null
Đáp án đúng: A

Câu 5. Consumer sửa đơn dựa trên version cũ, nhưng dữ liệu đã đổi; phản hồi nào diễn đạt xung đột tốt?
A. HTTP 200 và tự ghi đè mà không thông báo
B. HTTP 409 khi quy tắc cập nhật phát sinh xung đột
C. HTTP 404 cho mọi trường hợp khóa version sai
D. HTTP 503 để client thử lại mà không đọc dữ liệu
Đáp án đúng: B

Câu 6. Một request thiếu xác thực khác với request đã xác thực nhưng thiếu quyền; cặp phản hồi phù hợp là gì?
A. 403 cho chưa xác thực, 200 cho thiếu quyền
B. 404 cho chưa xác thực, 401 cho thiếu quyền
C. 401 khi chưa xác thực, 403 khi bị từ chối quyền
D. 429 khi chưa xác thực, 400 khi không đủ quyền
Đáp án đúng: C

Câu 7. Thiết kế response lỗi dùng chung nên ưu tiên thành phần nào?
A. Stack trace server và nội dung biến môi trường
B. Chỉ thông điệp tự do không có cấu trúc ổn định
C. Mã lỗi ổn định, thông điệp và request ID
D. Tên lớp Java tạo exception phía backend
Đáp án đúng: C

Câu 8. Trong JSON Schema, khai báo một property trong required có nghĩa gì?
A. Property chỉ được nhận chuỗi không rỗng
B. Property phải xuất hiện nhưng null luôn hợp lệ
C. Property bắt buộc là number khác 0
D. Property phải có mặt; null tùy kiểu cho phép
Đáp án đúng: D

Câu 9. Provider thêm một field tùy chọn vào response; trường hợp nào thường tương thích với consumer cũ?
A. Client kiểm tra đúng tập field và từ chối mọi field lạ
B. Client bỏ qua field ngoài phần hợp đồng cần dùng
C. Provider đồng thời đổi kiểu field đang là bắt buộc
D. Provider xóa field mà client đã phụ thuộc trước đó
Đáp án đúng: B

Câu 10. Provider đổi field amount từ number thành string; nguy cơ hợp đồng là gì?
A. Kiểu dữ liệu luôn tương đương khi giá trị giống nhau
B. Client tự động chấp nhận mọi schema khác nhau
C. Consumer cũ có thể không giải mã hoặc tính toán được
D. Đổi kiểu số sang chuỗi chỉ làm giảm kích thước JSON
Đáp án đúng: C

Câu 11. OpenAPI hữu ích trong thiết kế và review hợp đồng HTTP vì mô tả được gì?
A. Chỉ các bảng và khóa ngoại trong hệ quản trị
B. Paths, tham số, request body và các responses
C. Chỉ cấu hình container dùng để chạy service
D. Chỉ biểu đồ phụ thuộc module trong ứng dụng
Đáp án đúng: B

Câu 12. Khi schema khai báo quantity là số nguyên tối thiểu 1, kiểm thử nào sát hợp đồng nhất?
A. Chỉ dùng số lượng 50 để kiểm tra thành công
B. Dùng chuỗi '1' rồi giả định server sẽ tự ép kiểu
C. Chỉ so độ dài JSON không kiểm tra dữ liệu
D. Thử 0, 1 và giá trị không phải integer
Đáp án đúng: D

Câu 13. API trả danh sách có phân trang, dữ liệu liên tục thay đổi; điều gì hỗ trợ kết quả trang ổn định hơn?
A. Chỉ tăng limit cho mọi request phân trang
B. Dùng offset nhưng bỏ sort để giảm tải
C. Cho client đổi thứ tự sắp xếp ở mỗi trang
D. Cursor gắn thứ tự sắp xếp ổn định đã định nghĩa
Đáp án đúng: D

Câu 14. Một API thanh toán có thể nhận lại cùng request sau timeout; hợp đồng nên có gì?
A. Idempotency key và quy tắc xử lý gửi lại
B. Client phải thay transaction ID ở mọi lần thử
C. Mỗi retry được phép ghi thêm một khoản thanh toán
D. Bắt client tự đọc database nội bộ của provider
Đáp án đúng: A

Câu 15. Khi đổi field bắt buộc sang tên mới, chiến lược versioning nào giảm rủi ro cho consumer cũ?
A. Đổi thẳng tên field trong cùng bản mà không báo
B. Giữ hợp đồng cũ trong thời gian chuyển đổi/version mới
C. Đổi status code thành 200 để client bỏ qua field
D. Chỉ nâng phiên bản build mà không chỉnh tài liệu
Đáp án đúng: B

Câu 16. Consumer-driven contract testing tập trung xác minh điều gì?
A. Provider luôn đáp ứng mọi hành vi chưa từng công bố
B. Các tương tác mà consumer thực sự phụ thuộc
C. Một hợp đồng chứa mọi đặc tả code nội bộ provider
D. Consumer luôn chạy chung database của provider
Đáp án đúng: B

Câu 17. Provider verification mang lại giá trị gì so với chỉ dùng stub ở consumer?
A. Kiểm tra provider thực đáp ứng kỳ vọng đã ghi
B. Chứng minh mọi luồng end-to-end đã chạy chính xác
C. Loại bỏ nhu cầu test lỗi khi dịch vụ phụ thuộc chậm
D. Đảm bảo provider và consumer luôn dùng cùng JVM
Đáp án đúng: A

Câu 18. Với API phát sự kiện OrderCreated, hợp đồng message nào quan trọng?
A. Chỉ thời gian process khởi động trong container
B. Chỉ tên method Java emitEvent trong provider
C. Chỉ số thread xử lý đồng thời tại thời điểm phát
D. Loại sự kiện, phiên bản và schema của payload
Đáp án đúng: D

Câu 19. Trong hợp đồng RPC, việc thêm một trường request required không có default dễ gây hậu quả gì?
A. Client cũ tự sinh dữ liệu bắt buộc dù không biết
B. Client cũ có thể không gửi đủ trường mới
C. Đổi request schema không ảnh hưởng bản nào đang dùng
D. Provider tự chuyển trường cũ sang mới trong mọi trường hợp
Đáp án đúng: B

Câu 20. Một API trả 429 khi client vượt rate limit; thiết kế phản hồi nào giúp client phục hồi?
A. Mô tả giới hạn và thời điểm thử lại theo hợp đồng
B. Trả chung mã 500 cho mọi lỗi quá số lần gọi
C. Bỏ mọi header liên quan đến giới hạn request
D. Tự đổi dữ liệu của client để giảm số lần gọi
Đáp án đúng: A

Câu 21. API dùng OAuth scope; cách thiết kế quyền hạn hợp lý là gì?
A. Cấp quyền ghi cho mọi client chỉ cần đọc dữ liệu
B. Kiểm tra scope chỉ trong UI, bỏ qua ở backend
C. Xác định scope tối thiểu cho từng operation
D. Để mọi token có cùng quyền vì đã đăng nhập
Đáp án đúng: C

Câu 22. Response enum có thêm trạng thái mới; lúc nào đây là thay đổi đáng lo?
A. Client luôn có nhánh unknown xử lý hợp lý
B. Provider giữ nguyên kiểu trường enum là string
C. Client cũ dùng switch đóng và không có fallback
D. Provider đã mô tả danh sách enum trong schema
Đáp án đúng: C

Câu 23. Một bộ contract test chạy qua hết; khẳng định nào đúng về giới hạn của kết quả?
A. Đã chứng minh mọi luồng liên dịch vụ đúng cuối cùng
B. Không cần chạy test tích hợp với hệ thống thật nữa
C. Đã xác minh toàn bộ xử lý nhất quán ở database
D. Vẫn cần test hành vi nghiệp vụ và tích hợp thực tế
Đáp án đúng: D

Câu 24. Consumer cũ và mới cùng sử dụng API; test nào hữu ích trước khi deploy provider mới?
A. Verify provider với hợp đồng consumer cũ và mới
B. Chỉ chạy unit test của lớp controller bên provider
C. Chỉ đọc tài liệu schema mà không chạy verification
D. Chỉ test contract consumer mới nhất đang phát triển
Đáp án đúng: A
