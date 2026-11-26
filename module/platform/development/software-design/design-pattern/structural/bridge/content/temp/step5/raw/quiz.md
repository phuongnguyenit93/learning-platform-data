Câu 1: Bridge Pattern chủ yếu hướng tới vấn đề nào của thiết kế hướng đối tượng?
A. Tách hai chiều biến thể để chúng tiến hóa độc lập
B. Thích nghi API cũ với interface client mới
C. Bọc thêm trách nhiệm vào cùng interface có sẵn
D. Đơn giản hóa subsystem qua một facade duy nhất
Đáp án đúng: A

Câu 2: Trong Bridge, Abstraction thường giữ quan hệ gì với Implementor?
A. Luôn kế thừa trực tiếp concrete Implementor
B. Chỉ biết tên file triển khai của Implementor
C. Luôn tạo Implementor bằng reflection mỗi lần
D. Chứa tham chiếu đến hợp đồng Implementor
Đáp án đúng: D

Câu 3: Trong Bridge, Implementor interface thường quy định điều gì?
A. Toàn bộ logic nghiệp vụ cấp cao của mọi client
B. Các thao tác nền tảng mà Abstraction cần dùng
C. Cách tạo request HTTP cho tất cả controller
D. Chi tiết giao diện người dùng của từng biến thể
Đáp án đúng: B

Câu 4: RefinedAbstraction có thể mở rộng điều gì mà vẫn dùng chung Implementor?
A. Mã driver riêng cho mỗi hệ điều hành hỗ trợ
B. Lớp JDBC được tạo bởi concrete database adapter
C. Hành vi cấp cao và cách phối hợp các thao tác
D. Danh sách classpath của mọi thư viện runtime
Đáp án đúng: C

Câu 5: ConcreteImplementor thường đảm nhiệm trách nhiệm nào?
A. Quyết định mọi rule nghiệp vụ của Abstraction
B. Tạo giao diện sử dụng cho tất cả các client
C. Hiện thực thao tác thấp tầng cho một biến thể
D. Lưu lịch sử hoàn tác trên mọi request
Đáp án đúng: C

Câu 6: Có 3 loại Remote và 4 loại Device, Bridge giúp tránh vấn đề gì?
A. Định nghĩa interface cho các Device khác nhau
B. Tạo 12 class con ứng với từng cặp biến thể
C. Phải chạy integration test trên bốn thiết bị
D. Phải dùng abstraction thay cho concrete type
Đáp án đúng: B

Câu 7: Ví dụ RemoteControl điều khiển TV và Radio, đâu là Implementor hợp lý?
A. AdvancedRemote chứa nút mute trên UI
B. UniversalRemote phối hợp các lệnh của user
C. Device cung cấp bật/tắt và chỉnh âm lượng
D. RemoteControl chứa state nút điều khiển
Đáp án đúng: C

Câu 8: Khi thêm Projector vào hệ RemoteControl–Device, thay đổi nào hợp lý?
A. Thêm ProjectorImplementor, không nhân bản mọi Remote
B. Tạo lại BasicRemoteProjector và AdvancedRemoteProjector
C. Đổi RemoteControl thành class phụ thuộc trực tiếp máy chiếu
D. Chuyển mọi class Remote thành subclass của Projector
Đáp án đúng: A

Câu 9: Trong Java, cách nối hai phía Bridge dễ thay thế nhất là gì?
A. Dùng static singleton cố định một implementation
B. Tiêm Implementor qua constructor hoặc setter
C. Để Abstraction tự new driver trong từng method
D. Đặt concrete Implementor thành class cha của Abstraction
Đáp án đúng: B

Câu 10: Khi Circle và Rectangle dùng CanvasRenderer hoặc SvgRenderer, hai trục là gì?
A. Tên package hình vẽ và tên file Java
B. Số lượng điểm và thứ tự khai báo class
C. Loại hình vẽ và cách biểu diễn hình vẽ
D. Loại exception và số lần gọi constructor
Đáp án đúng: C

Câu 11: Phương thức Shape.draw() trong Bridge nên phối hợp điều gì?
A. Tự ghi cú pháp SVG và Canvas ngay trong Shape
B. Tự tạo database transaction cho từng lần draw
C. Tự chạy thuật toán parse CSS trong mỗi Shape
D. Tính thông số hình rồi gọi thao tác của Renderer
Đáp án đúng: D

Câu 12: Nếu Abstraction trực tiếp gọi OpenGLDriver cụ thể, điều gì bị ảnh hưởng?
A. Dễ thay mọi backend không cần viết interface
B. Khó thay driver vì phía trên dính implementation
C. Tách biệt hoàn toàn trục shape và renderer
D. Các concrete renderer tự động trở nên bất biến
Đáp án đúng: B

Câu 13: Để unit test Abstraction trong Bridge, nên thay Implementor bằng gì?
A. Fake hoặc spy Implementor để kiểm tra lời gọi
B. Render thật trên mọi thiết bị đồ họa production
C. Mở HTTP server để giả lập tất cả client
D. Tạo subclass cho mọi hệ điều hành có thể
Đáp án đúng: A

Câu 14: Để kiểm chứng CanvasRenderer gọi API vẽ đúng, test nào hữu ích?
A. Test riêng ConcreteImplementor với API thử nghiệm
B. Chỉ test constructor Shape mà không gọi Renderer
C. Chỉ kiểm tra UML bằng tên của các class con
D. Chỉ chạy unit test với Renderer fake duy nhất
Đáp án đúng: A

Câu 15: Điểm phân biệt Bridge và Adapter theo mục tiêu thiết kế là gì?
A. Bridge chỉ dịch lỗi; Adapter phân tách hai trục
B. Bridge tách trục biến thể; Adapter nối API lệch
C. Bridge dùng kế thừa; Adapter bắt buộc dùng singleton
D. Bridge chỉ dùng Java; Adapter chỉ dùng thư viện native
Đáp án đúng: B

Câu 16: Bridge khác Strategy chủ yếu ở điểm nhấn nào?
A. Strategy luôn có hai hệ phân cấp song song
B. Bridge chỉ có thể đổi implementation lúc compile
C. Bridge phát triển hai hệ phân cấp độc lập
D. Strategy chỉ hoạt động qua đa kế thừa trong Java
Đáp án đúng: C

Câu 17: Khi nào composition đơn thuần chưa đủ để gọi thiết kế là Bridge?
A. Khi class có một field interface được tiêm
B. Khi object được lắp bằng dependency injection
C. Khi các class được chia thành package riêng
D. Khi không tồn tại hai chiều thay đổi độc lập
Đáp án đúng: D

Câu 18: Nếu chỉ một renderer cố định và không có trục thứ hai, quyết định nào phù hợp?
A. Bắt buộc tạo RefinedAbstraction cho mỗi method
B. Có thể chưa cần Bridge để tránh lớp thừa
C. Bắt buộc viết Implementor cho từng loại exception
D. Tạo class cho mọi tổ hợp chưa có nhu cầu
Đáp án đúng: B

Câu 19: Bridge và Dependency Inversion liên quan với nhau thế nào?
A. Phía Abstraction phải import mọi concrete driver
B. Implementor tự biết mọi RefinedAbstraction cụ thể
C. Phía Abstraction dựa hợp đồng của Implementor
D. Client phải truy cập nội bộ concrete implementation
Đáp án đúng: C

Câu 20: Trong cấu hình runtime cần đổi backend renderer, cách nào phù hợp?
A. Thay toàn bộ class hierarchy khi khởi động lại
B. Lắp Implementor khác vào Abstraction qua cấu hình
C. Sửa source của Abstraction trước khi mỗi request
D. Để client sửa field private bên trong concrete driver
Đáp án đúng: B

Câu 21: Một Implementor interface lộ quá nhiều OpenGL API cụ thể gây hệ quả gì?
A. Mọi renderer tự nhiên cùng chia sẻ một ngữ nghĩa
B. Bất kỳ backend mới nào cũng không cần adapter
C. Abstraction chỉ còn phụ thuộc vào logic miền
D. Ranh giới Bridge rò rỉ chi tiết nền tảng
Đáp án đúng: D

Câu 22: Trong hệ thông báo gồm Urgent/Normal và Email/SMS, Bridge có thể tổ chức sao?
A. Mỗi cặp ưu tiên–kênh phải có subclass riêng
B. Kênh Email kế thừa trực tiếp class Urgent
C. Mỗi loại thông báo tự viết lại toàn bộ SMTP
D. Ưu tiên thông báo tách khỏi kênh gửi
Đáp án đúng: D

Câu 23: Thêm kênh Push vào Bridge thông báo ảnh hưởng phần nào chủ yếu?
A. Thêm Implementor mới cho cơ chế gửi Push
B. Sao chép toàn bộ Urgent và Normal theo kênh mới
C. Đổi hợp đồng nghiệp vụ của mọi notification
D. Buộc mọi client dùng trực tiếp Push SDK
Đáp án đúng: A

Câu 24: Trong Bridge, Abstraction bắt buộc là abstract class Java không?
A. Không, đó là vai trò; có thể là class cụ thể
B. Có, vì mọi Bridge cần từ khóa abstract Java
C. Có, vì Implementor luôn là superclass của nó
D. Không, vì Abstraction bắt buộc là interface rỗng
Đáp án đúng: A

Câu 25: Để refactor 12 class như PdfLocal/PdfCloud, CsvLocal/CsvCloud, bước nào phù hợp?
A. Thêm một cấp kế thừa cho mỗi cặp báo cáo
B. Đưa mọi nhánh xuất vào một switch toàn cục
C. Tạo lớp Facade bao toàn bộ 12 class nguyên bản
D. Tách kiểu báo cáo khỏi cơ chế xuất dữ liệu
Đáp án đúng: D

Câu 26: Một biến thể RefinedAbstraction mới nên phụ thuộc những gì?
A. Danh sách tất cả concrete Implementor đang có
B. Tên thư viện riêng của backend được chọn
C. Hợp đồng Implementor và logic cấp cao riêng
D. Mã source của mọi RefinedAbstraction khác
Đáp án đúng: C

Câu 27: Nếu dùng Bridge nhưng mỗi RefinedAbstraction vẫn có switch theo backend, đó là dấu hiệu gì?
A. Hai trục chưa tách hết khỏi logic tầng trên
B. Bridge bảo đảm tính độc lập của backend đã đủ
C. ConcreteImplementor không cần định nghĩa nữa
D. Các backend tự động trở thành singleton dùng chung
Đáp án đúng: A

Câu 28: Kiểm thử tổ hợp nhiều Abstraction và Implementor nên ưu tiên cách nào?
A. Chỉ test một cặp rồi khẳng định mọi cặp sẽ hoạt động
B. Bỏ test backend vì đã có interface Java
C. Chạy một lớp con chứa toàn bộ cặp cùng lúc
D. Tách test hợp đồng mỗi trục và vài tổ hợp trọng yếu
Đáp án đúng: D
