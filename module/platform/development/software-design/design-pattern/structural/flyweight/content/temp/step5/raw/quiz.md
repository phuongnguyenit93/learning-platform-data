Flyweight phù hợp khi có hàng triệu biểu tượng dùng chung cùng một kiểu hiển thị vì sao?
A. Mỗi biểu tượng sẽ giữ riêng bản sao mọi thuộc tính
B. Chia sẻ cấu hình và dữ liệu hiển thị bất biến
C. Mọi biểu tượng phải có một thread cập nhật độc lập
D. Mỗi biểu tượng tự mở kết nối tới kho lưu trữ
Đáp án đúng: B

Intrinsic state trong Flyweight nên có tính chất nào?
A. Luôn được đọc từ database mỗi lần render
B. Ổn định và có thể chia sẻ giữa nhiều đối tượng
C. Luôn chứa vị trí cùng thời gian của từng phần tử
D. Được sửa theo vị trí riêng của từng instance
Đáp án đúng: B

Tọa độ riêng của mỗi biểu tượng khi vẽ thường thuộc nhóm dữ liệu nào?
A. Extrinsic state được truyền theo từng lần vẽ
B. Biến global mutable trong toàn bộ màn hình
C. Intrinsic state được lưu trong object dùng chung
D. Khóa factory bắt buộc trùng ID của đối tượng
Đáp án đúng: A

Flyweight factory thường dùng khóa để thực hiện việc gì?
A. Tạo object mới cho mọi lời gọi kể cả cùng khóa
B. Tự chọn vị trí của từng đối tượng trên màn hình
C. Tra cứu object chia sẻ và tạo mới khi chưa có
D. Lưu trạng thái thao tác của từng client riêng
Đáp án đúng: C

Để tái sử dụng Flyweight cho hai loại biểu tượng khác màu, khóa cache nên biểu diễn gì?
A. ID của mỗi request khi gọi tới phương thức render
B. Tên thread đang xử lý lệnh vẽ của client
C. Vị trí x/y của từng instance được vẽ lên canvas
D. Các thuộc tính intrinsic của kiểu biểu tượng
Đáp án đúng: D

Vì sao intrinsic state bất biến giúp Flyweight an toàn hơn?
A. Ngăn client vô tình thay đổi dữ liệu dùng chung
B. Buộc mọi client phải chạy trong cùng một thread
C. Cho phép object tự thay đổi theo từng thread
D. Bảo đảm factory không bao giờ dùng đến bộ nhớ
Đáp án đúng: A

Nếu một client sửa field màu trên Flyweight đang được nhiều nơi dùng, hệ quả nào có thể xảy ra?
A. Factory tự tạo bản sao khác cho mỗi client
B. Tất cả object tự rollback về màu gốc
C. Extrinsic state của mọi client được xóa ngay
D. Nhiều đối tượng khác vô tình đổi màu theo
Đáp án đúng: D

Khi nhiều thread đồng thời xin cùng khóa chưa có trong factory, cần lưu ý gì?
A. Tắt cache để không còn bất kỳ trạng thái nào
B. Cấm mọi object dùng chung trong ứng dụng đa luồng
C. Tạo và công bố một shared object an toàn luồng
D. Để mỗi thread ghi trực tiếp vào HashMap chung
Đáp án đúng: C

Trong Java, công cụ nào hỗ trợ cache factory cập nhật đồng thời theo khóa?
A. ThreadLocal tạo một Flyweight cho mỗi lần gọi
B. HashMap không đồng bộ với put từ mọi thread
C. ArrayList chứa object không cần kiểm tra khóa
D. Dùng ConcurrentHashMap cùng computeIfAbsent
Đáp án đúng: D

Nếu factory giữ mãi các khóa duy nhất từ input người dùng, rủi ro nào tăng?
A. Flyweight tự dọn mọi entry khi không còn truy cập
B. Mọi object được JVM gộp dù khóa khác nhau
C. Những khóa mới không thể được tạo trong Java
D. Cache phình lớn và giữ tham chiếu lâu dài
Đáp án đúng: D

Chi phí hiệu năng nào cần cân nhắc khi áp dụng Flyweight?
A. Chi phí tra cứu cache và truyền extrinsic state
B. Mỗi lần gọi sẽ sao chép toàn bộ object dùng chung
C. Không còn phát sinh chi phí cấp phát đối tượng
D. Mọi instance buộc dùng một thread riêng khi chạy
Đáp án đúng: A

Để kiểm tra factory tái sử dụng đúng Flyweight, assertion nào hữu ích?
A. Hai khóa khác nhau buộc trỏ đến cùng object
B. Cùng intrinsic key trả cùng object đã tồn tại
C. Hai tọa độ khác nhau phải làm đổi intrinsic key
D. Mỗi lần gọi với cùng khóa tạo một instance mới
Đáp án đúng: B

Khi dùng Flyweight để vẽ, trạng thái vị trí của từng phần tử nên nằm ở đâu?
A. Trong shared object bị sửa trước mỗi lần render
B. Trong một biến static của lớp Flyweight chung
C. Trong dữ liệu client hoặc tham số của lệnh vẽ
D. Trong khóa cache chứa mọi vị trí xuất hiện
Đáp án đúng: C

Trường hợp nào Flyweight ít mang lại lợi ích?
A. Nhiều ký tự cùng tham chiếu một định dạng chữ
B. Rất nhiều node dùng chung kiểu nét vẽ bất biến
C. Có ít object, intrinsic state cũng hiếm khi trùng
D. Rất nhiều đối tượng chia sẻ cấu hình biểu tượng
Đáp án đúng: C

Flyweight khác object pool ở mục đích cơ bản nào?
A. Xóa toàn bộ đối tượng khi không còn request hoạt động
B. Chia sẻ state chung thay vì tái sử dụng tài nguyên
C. Giữ sẵn connection để trả về sau khi dùng xong
D. Cấp riêng một đối tượng cho mỗi client đồng thời
Đáp án đúng: B

Khác biệt quan trọng giữa Flyweight và Singleton là gì?
A. Nhiều instance Flyweight theo khóa intrinsic
B. Flyweight luôn bắt buộc chỉ có đúng một instance
C. Singleton tự chia sẻ theo hàng trăm khóa intrinsic
D. Cả hai đều bắt buộc lưu vị trí riêng của client
Đáp án đúng: A
