Lớp InvoiceService vừa tính thuế, vừa gửi email và xuất báo cáo; cải tiến trách nhiệm nào phù hợp?
A. Cho lớp kế thừa một BaseService nhiều chức năng
B. Đặt cả ba quy tắc trong một constructor
C. Tách các phần có lý do thay đổi độc lập
D. Giữ một lớp nhưng dời code vào hàm private
Đáp án đúng: C

Trong separation of concerns, controller HTTP nên chịu trách nhiệm chính nào?
A. Chuyển request thành lời gọi nghiệp vụ và response
B. Quản lý trực tiếp transaction của từng database
C. Chứa toàn bộ quy tắc tính giá của domain
D. Khởi tạo và giám sát pool kết nối hạ tầng
Đáp án đúng: A

Thiết kế nào thể hiện encapsulation tốt khi Account không được có số dư âm?
A. Cập nhật số dư qua method kiểm tra bất biến
B. Để giao diện kiểm tra rồi setter nhận mọi giá trị
C. Cho client gán trực tiếp field balance public
D. Cho mọi class ghi trực tiếp vào collection nội bộ
Đáp án đúng: A

Một interface nhằm thể hiện abstraction hữu ích nên tập trung vào điều gì?
A. Trạng thái private của class triển khai cụ thể
B. Toàn bộ option cấu hình của framework
C. Chi tiết SQL và driver của từng môi trường
D. Năng lực cần dùng, không lộ cách triển khai
Đáp án đúng: D

Dấu hiệu nào cho thấy một lớp có cohesion cao?
A. Các method giao tiếp với nhiều subsystem không liên quan
B. Các field được chia sẻ qua nhiều chức năng độc lập
C. Các thành phần thay đổi vì nhiều yêu cầu khác nhau
D. Các method và field phục vụ cùng trách nhiệm
Đáp án đúng: D

Service tự `new MySqlCustomerRepository()` trong code nghiệp vụ gây ảnh hưởng nào?
A. Khó thay thế và kiểm thử phụ thuộc lưu trữ
B. Loại bỏ nhu cầu quản lý vòng đời repository
C. Dễ thay repository nhờ phụ thuộc kiểu cụ thể
D. Tăng đóng gói nhờ client biết cách kết nối
Đáp án đúng: A

Single Responsibility Principle nên được hiểu chính xác ra sao?
A. Một module nên có một lý do thay đổi nhất quán
B. Mỗi class phải có một instance tại runtime
C. Mỗi hàm được phép gọi tối đa một collaborator
D. Một class chỉ được khai báo đúng một method
Đáp án đúng: A

Ứng dụng cần thêm quy tắc giảm giá mới mà ít sửa code đang ổn định; áp dụng nguyên tắc nào?
A. Sửa chuỗi if trong mọi nơi gọi hàm giảm giá
B. Mở rộng qua strategy mới phía sau interface
C. Tạo một enum trung tâm chứa mọi SQL giảm giá
D. Sao chép service hiện tại cho mỗi chương trình
Đáp án đúng: B

Theo Liskov Substitution Principle, lớp con có hành vi nào là đáng ngại?
A. Thay đổi cách tối ưu bên trong mà không đổi contract
B. Giữ nguyên điều kiện đầu vào của lớp cha
C. Tự tăng điều kiện đầu vào so với hợp đồng cha
D. Cung cấp kết quả phù hợp hậu điều kiện cha
Đáp án đúng: C

Một interface quá lớn buộc CsvExporter cài method gửi email; nên làm gì?
A. Cho CsvExporter ném UnsupportedOperationException
B. Chia interface theo nhóm nhu cầu của client
C. Đưa method gửi email vào một static helper
D. Thêm abstract base class chứa các method rỗng
Đáp án đúng: B

Dependency Inversion Principle hướng dependency của domain service về đâu?
A. Implementation của driver database đang chạy
B. Controller và cách ánh xạ URL của web layer
C. Class factory framework có nhiều helper runtime
D. Abstraction cho collaborator thay vì client cụ thể
Đáp án đúng: D

Nếu lõi nghiệp vụ phải import REST controller và JDBC adapter, vấn đề thiết kế nào nổi bật?
A. Cohesion tăng do tái dùng class của controller
B. Chiều phụ thuộc chĩa từ core ra chi tiết
C. Chia tầng tốt vì tất cả lớp đều nhìn thấy nhau
D. Đóng gói tốt vì business gọi trực tiếp adapter
Đáp án đúng: B

Khi cần thay chiến lược thanh toán mà không đổi OrderService, thiết kế nào phù hợp?
A. OrderService gọi static method của từng gateway
B. OrderService sở hữu PaymentPort rồi ủy quyền
C. OrderService đọc config và tự dùng SDK tương ứng
D. OrderService kế thừa PaymentGateway cụ thể
Đáp án đúng: B

Unit test nghiệp vụ phụ thuộc cổng dữ liệu nên được tổ chức thế nào?
A. Mock toàn bộ class nghiệp vụ cần được kiểm tra
B. Luôn dùng database production để có dữ liệu thật
C. Chạy logic thật với fake cho dependency ngoài
D. Chỉ kiểm tra mock DAO được tạo không null
Đáp án đúng: C

Tạo interface cho mọi class dù chỉ có một triển khai đơn giản có nhược điểm nào?
A. Làm cho mọi dependency đều biến mất khỏi mã
B. Luôn bảo đảm mở rộng không phải sửa code
C. Tự động làm các object không còn state mutable
D. Thêm indirection mà chưa tạo giá trị thay thế
Đáp án đúng: D

Sau khi đổi driver lưu trữ mà phải sửa controller, domain và unit test, điều gì nên xem lại?
A. Phong cách đặt tên biến trong từng controller
B. Số method private trong lớp kiểm thử domain
C. Ranh giới abstraction và hướng coupling giữa lớp
D. Số lượng enum trong tầng ứng dụng khi chạy
Đáp án đúng: C
