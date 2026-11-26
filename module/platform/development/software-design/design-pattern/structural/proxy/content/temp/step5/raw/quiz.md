Proxy và đối tượng thật nên có quan hệ hợp đồng như thế nào?
A. Proxy triển khai cùng interface với đối tượng thật
B. Proxy bắt buộc kế thừa lớp giao diện người dùng
C. Proxy chỉ cung cấp API riêng, khác với target
D. Proxy đổi toàn bộ hợp đồng thành câu lệnh SQL
Đáp án đúng: A

Virtual Proxy hữu ích với đối tượng khởi tạo rất tốn kém nhờ điều gì?
A. Tạo mới target sau mỗi lần gọi dù còn dùng
B. Khởi tạo target khi toàn bộ request kết thúc
C. Khởi tạo toàn bộ target ngay lúc tạo proxy
D. Trì hoãn tạo target tới khi thật sự cần dùng
Đáp án đúng: D

Protection Proxy nên làm gì khi client không có quyền thực hiện lệnh?
A. Tạo target mới với quyền của tài khoản khác
B. Chuyển tiếp rồi chỉ ghi cảnh báo quyền
C. Cho phép gọi target nhưng xóa kết quả
D. Từ chối trước khi chuyển tiếp tới target
Đáp án đúng: D

Proxy dùng cache trước service thật cần quản lý yếu tố nào?
A. Lịch sử tạo class của mọi client đang gọi
B. Lệnh SQL nội bộ của những service không liên quan
C. Chính sách hết hạn và vô hiệu dữ liệu cache
D. Thứ tự nạp thư viện Java khi khởi động JVM
Đáp án đúng: C

Remote Proxy giúp client gọi service ở máy khác như thế nào?
A. Bảo đảm mọi RPC luôn thành công và tức thời
B. Ẩn chi tiết gọi mạng và chuyển đổi thông điệp
C. Chuyển toàn bộ dữ liệu vào cùng một JVM duy nhất
D. Thay mọi kết nối mạng bằng lời gọi method nội bộ
Đáp án đúng: B

JDK Dynamic Proxy phù hợp để tạo đại diện cho những loại hợp đồng nào?
A. Các interface Java được proxy triển khai
B. Mọi static method của lớp triển khai cụ thể
C. Mọi final class mà không cần interface nào
D. Bất kỳ private constructor trong class bất biến
Đáp án đúng: A

InvocationHandler.invoke nhận thông tin nào để xử lý lời gọi tới JDK Proxy?
A. Một JDBC Connection và tên bảng được gọi
B. Tham chiếu proxy, Method và mảng arguments
C. Danh sách Spring Bean cùng DataSource mặc định
D. Một HTTP request đã được parse thành JSON
Đáp án đúng: B

Khi InvocationHandler chuyển tiếp lời gọi, cách nào bảo toàn hành vi target?
A. Bỏ mọi đối số và gửi giá trị mặc định tới target
B. Chỉ thực thi phần before mà không gọi target
C. Gọi Method trên target với arguments tương ứng
D. Gọi Method trên chính proxy để sinh đệ quy
Đáp án đúng: C

Với Spring AOP dựa trên proxy, advice thường chạy khi nào?
A. Đối tượng không đi qua proxy nào của Spring
B. Bean tự gọi private method bằng tham chiếu this
C. Java gọi trực tiếp constructor của mọi đối tượng
D. Caller bên ngoài gọi method qua proxy của bean
Đáp án đúng: D

Vì sao self-invocation trong cùng bean có thể bỏ qua advice của Spring Proxy?
A. Spring bắt buộc gọi lại advice hai lần liên tiếp
B. JVM cấm mọi method trong cùng class gọi nhau
C. Transaction tự chuyển sang một service khác
D. Lời gọi qua this không đi qua proxy bên ngoài
Đáp án đúng: D

Khi @Transactional dùng cơ chế proxy, điều kiện gọi nào quan trọng?
A. Mọi hàm private mặc định mở một transaction
B. Không cần Spring quản lý bean có annotation
C. Lời gọi cần đi qua proxy để áp interceptor
D. Chỉ cần method gọi trực tiếp bằng this là đủ
Đáp án đúng: C

Với class-based proxy của Spring, final method tạo hạn chế gì?
A. Không thể override final method để chặn lời gọi
B. Final method bắt buộc gọi trực tiếp từ interface
C. Final method luôn được bọc qua kế thừa class
D. Final method tự chạy advice trước khi vào target
Đáp án đúng: A

Một proxy thêm logging quanh target nên xử lý exception thế nào?
A. Chuyển mọi exception thành kết quả mặc định
B. Bỏ lỗi để client tin mọi thao tác đều thành công
C. Giữ đúng hợp đồng lỗi thay vì nuốt exception
D. Chỉ ghi lỗi rồi tự retry vô hạn với mỗi request
Đáp án đúng: C

Khi cân nhắc đưa proxy vào đường gọi thường xuyên, cần đánh giá gì?
A. Tự thêm mọi wrapper mà không cần đo hiệu năng
B. Chi phí intercept, cache và round-trip khi có RPC
C. Bỏ đo latency vì proxy không chạm tới target
D. Giả định mọi proxy đều giảm độ trễ thành một nửa
Đáp án đúng: B

Một lazy proxy được nhiều thread gọi cùng lúc cần lưu ý điều gì?
A. Chỉ khởi tạo target trong thread đóng ứng dụng
B. Đảm bảo khởi tạo target an toàn và đúng một lần
C. Để mỗi thread tạo riêng target rồi giữ mãi không giới hạn
D. Tắt đồng bộ ngay cả khi target có state mutable
Đáp án đúng: B

Kiểm thử một Protection Proxy hiệu quả nên xác minh điều gì?
A. Chặn caller thiếu quyền và forward khi đủ quyền
B. Kiểm tra chỉ tên class Proxy có chứa chữ Security
C. Chỉ so số lượng constructor của target thực tế
D. Chỉ xác minh proxy đã được tạo mà không gọi
Đáp án đúng: A
