Facade chủ yếu giải quyết khó khăn nào khi sử dụng một phân hệ phức tạp?
A. Bắt mọi module phải kế thừa cùng một lớp cha
B. Thay mọi triển khai nội bộ bằng một class duy nhất
C. Cung cấp API đơn giản cho các thao tác thường dùng
D. Buộc client điều khiển từng bước kỹ thuật bên trong
Đáp án đúng: C

Một facade đặt hàng cần gọi kho, thanh toán và vận chuyển; nhiệm vụ phù hợp là gì?
A. Gộp toàn bộ dữ liệu thành một singleton chung
B. Thay logic xác thực tiền trong payment service
C. Để client tự gọi ba subsystem theo thứ tự
D. Điều phối các bước trong quy trình đặt hàng
Đáp án đúng: D

Sau khi có Facade, client có bắt buộc mất quyền gọi API subsystem không?
A. Không; facade bắt buộc là lớp con của subsystem
B. Không; client vẫn có quyền truy cập subsystem
C. Có; phải xóa toàn bộ interface cũ khỏi ứng dụng
D. Có; các subsystem phải biến thành lớp private
Đáp án đúng: B

Điểm khác biệt chính giữa Facade và Adapter là gì?
A. Facade chỉ dùng reflection; Adapter dùng kế thừa
B. Facade đơn giản hóa; Adapter chuyển interface
C. Facade chỉ dùng cho REST; Adapter cho JDBC
D. Facade thay đổi thuật toán; Adapter lưu snapshot
Đáp án đúng: B

Khi chọn phương thức facade, tiêu chí nào có ích nhất?
A. Định nghĩa thao tác theo use case của client
B. Tạo một method cho mỗi field của mỗi đối tượng
C. Gộp tất cả chức năng của hệ thống vào một API
D. Công khai mọi method private của subsystem
Đáp án đúng: A

Nếu một facade dần chứa mọi quy tắc nghiệp vụ độc lập, rủi ro nào tăng?
A. Client không cần xử lý lỗi khi gọi API
B. Subsystem tự động trở nên ít phụ thuộc nhau
C. Mọi tác vụ tự chuyển sang bất đồng bộ
D. Thành lớp lớn, khó duy trì và kiểm thử
Đáp án đúng: D

Phụ thuộc của client được giảm ra sao khi sử dụng Facade phù hợp?
A. Client dựa trên API facade, không phải lớp nội bộ
B. Client phải import mọi class hỗ trợ bên dưới
C. Client dùng thẳng cấu trúc DB của subsystem
D. Client tạo thủ công các dependency của facade
Đáp án đúng: A

Subsystem trả nhiều loại lỗi kỹ thuật; facade nên xử lý thế nào?
A. Trả stack trace nội bộ như một field nghiệp vụ
B. Tự retry mọi lỗi vô hạn để client không thấy
C. Ánh xạ lỗi kỹ thuật sang lỗi facade có ý nghĩa
D. Nuốt hết exception rồi luôn thông báo thành công
Đáp án đúng: C

Facade mở tài nguyên rồi chạy nhiều tác vụ; phương án nào an toàn hơn?
A. Để client đóng resource mà facade đã giấu đi
B. Đóng resource kể cả khi thao tác thất bại
C. Chỉ đóng tài nguyên nếu không có exception
D. Giữ connection mãi để tránh tạo kết nối mới
Đáp án đúng: B

Một luồng facade gọi hai service có DB riêng; điều nào cần tránh giả định?
A. Các service tự rollback toàn bộ khi facade lỗi
B. Facade luôn đồng bộ hai database vào một bảng
C. Không có atomic transaction mặc định xuyên service
D. Mọi gọi remote đều chạy chung một JDBC transaction
Đáp án đúng: C

Unit test facade điều phối nhiều dependency nên quan sát điều gì?
A. Tên package chính xác của mọi class được gọi
B. Thời gian JVM tải các thư viện phụ trợ
C. Đầu ra và hành vi cần xác minh của use case
D. Số dòng code chứa trong từng dependency
Đáp án đúng: C

Một facade trả trực tiếp object nội bộ dễ thay đổi của subsystem tạo nguy cơ gì?
A. Ngăn mọi thay đổi trong trạng thái của subsystem
B. Làm facade tự biến thành một lớp Adapter
C. Bảo đảm client không bao giờ cần nâng version
D. Khiến client bị ràng buộc vào cấu trúc nội bộ
Đáp án đúng: D

Khi thêm tính năng mà client cũ vẫn phải chạy, hợp đồng facade nên xử lý sao?
A. Đổi ý nghĩa method cũ mà không thông báo
B. Xóa mọi overload cũ sau lần build tiếp theo
C. Bắt client chỉnh theo mọi thay đổi nội bộ
D. Giữ tương thích hoặc quản lý phiên bản API
Đáp án đúng: D

Phân biệt Facade và Mediator theo luồng giao tiếp điển hình như thế nào?
A. Facade là cửa vào; Mediator điều phối các đối tượng
B. Facade giữ snapshot; Mediator chuyển đổi giao diện
C. Facade tạo clone; Mediator tối ưu đối tượng dùng chung
D. Facade điều phối colleagues; Mediator bọc các object
Đáp án đúng: A

Một facade gọi tuần tự nhiều thao tác độc lập và bị chậm, nên đánh giá gì?
A. Đo bước chậm, chỉ song song khi an toàn
B. Tắt logging và xem như đã xử lý nút thắt
C. Tăng thread cho mọi lời gọi mà không đo lường
D. Bỏ kiểm tra kết quả để rút ngắn thời gian
Đáp án đúng: A

Khi phân hệ chỉ có một API dễ hiểu, quyết định nào hợp lý về Facade?
A. Luôn thêm ba lớp facade dù không đơn giản hóa
B. Không cần thêm facade nếu không có giá trị
C. Luôn thay toàn bộ interface bằng một class tĩnh
D. Bắt buộc chia API hiện tại thành nhiều facade
Đáp án đúng: B
