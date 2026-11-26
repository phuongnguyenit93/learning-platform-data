Câu 1: Chữ S trong SOLID là nguyên lý nào?
A. Substitution Safety Principle
B. Single Responsibility Principle
C. Stable Repository Principle
D. Service Segregation Principle
Đáp án đúng: B

Câu 2: Theo SRP, một class nên tập trung vào điều gì?
A. Chỉ có đúng một phương thức public duy nhất
B. Chỉ sử dụng một dependency trong constructor
C. Không bao giờ được cộng tác với class khác
D. Nhóm hành vi có chung một lý do thay đổi
Đáp án đúng: D

Câu 3: Một lớp vừa tính thuế vừa tạo PDF và gửi email có dấu hiệu vi phạm gì?
A. OCP vì lớp không sử dụng abstract factory
B. SRP vì có các lý do thay đổi khác nhau
C. LSP vì lớp chưa kế thừa một class cha
D. ISP vì lớp không khai báo interface chung
Đáp án đúng: B

Câu 4: Refactor đúng khi tách InvoiceService đang vừa tính tổng vừa ghi file PDF là gì?
A. Tách xử lý hóa đơn khỏi việc kết xuất PDF
B. Đổi tất cả method thành static trong cùng lớp
C. Cho Controller nhận mọi dependency của JDBC
D. Tạo một lớp cha trừu tượng cho mọi hóa đơn
Đáp án đúng: A

Câu 5: SRP có bắt buộc một lớp chỉ có một phương thức Java không?
A. Có, vì hai method đã tạo hai lý do thay đổi
B. Có, trừ khi tất cả method đều là private
C. Không, miễn class dùng chính xác một package
D. Không, nhiều method có thể chung trách nhiệm
Đáp án đúng: D

Câu 6: Chữ O trong SOLID thể hiện nguyên lý nào?
A. Open/Closed Principle
B. Object Compatibility Principle
C. Operation Cohesion Principle
D. Override Composition Principle
Đáp án đúng: A

Câu 7: Khi thêm phương thức thanh toán mới khiến phải sửa switch ở nhiều nơi, gợi ý OCP là gì?
A. Thêm điều kiện mới vào mọi switch hiện có
B. Chuyển toàn bộ switch sang constructor của User
C. Sao chép tất cả use case cho mỗi loại thanh toán
D. Mở rộng qua implementation của PaymentPolicy
Đáp án đúng: D

Câu 8: OCP nói thành phần phải đóng với loại thay đổi nào?
A. Hạn chế sửa mã ổn định khi thêm một biến thể
B. Cấm mọi sửa mã ngay cả khi có bug nghiêm trọng
C. Cấm triển khai interface mới cho ứng dụng
D. Cấm thay đổi dữ liệu cấu hình của runtime
Đáp án đúng: A

Câu 9: Trong Java, cơ chế nào thường giúp OCP khi thêm kênh thông báo?
A. Dùng NotificationSender để thay cách gửi
B. Nhánh if dựa trên tên class ở mọi controller
C. Dùng biến static lưu một loại kênh cố định
D. Cho client tự new mọi SDK trong từng lần gửi
Đáp án đúng: A

Câu 10: OCP có nghĩa phải tạo abstraction trước mọi thay đổi có thể tưởng tượng không?
A. Có, cần interface cho tất cả method private
B. Có, mọi giá trị primitive phải thành interface
C. Không, chỉ trừu tượng hóa biến thể có căn cứ
D. Không, vì OCP chỉ áp dụng cho database
Đáp án đúng: C

Câu 11: Chữ L trong SOLID đề cập đến điều gì?
A. Layered Subsystem Principle
B. Liskov Substitution Principle
C. Logical Segregation Principle
D. Local Serialization Principle
Đáp án đúng: B

Câu 12: LSP yêu cầu class con khi thay class cha phải bảo đảm điều gì?
A. Luôn trả về chính xác một concrete subtype
B. Có cùng số lượng field private của class cha
C. Không bao giờ override bất kỳ method public nào
D. Giữ các cam kết hành vi mà client dựa vào
Đáp án đúng: D

Câu 13: Một subtype ném UnsupportedOperationException cho thao tác mà base contract luôn hỗ trợ gây rủi ro gì?
A. Vi phạm LSP vì bỏ hành vi đã cam kết
B. Tuân thủ ISP vì subclass có ít method hơn
C. Tuân thủ DIP vì caller chỉ dùng interface
D. Bảo đảm OCP vì mọi subclass đều immutable
Đáp án đúng: A

Câu 14: Về precondition trong LSP, subtype nên tuân theo quy tắc nào?
A. Được siết input tùy ý để giảm số trường hợp
B. Phải yêu cầu thêm một tham số cho mọi method
C. Không đòi đầu vào chặt hơn hợp đồng lớp cha
D. Phải bỏ mọi validation có trong method gốc
Đáp án đúng: C

Câu 15: Về postcondition trong LSP, subtype không nên làm gì?
A. Làm yếu các cam kết đầu ra của lớp cha
B. Trả về giá trị đáp ứng đầy đủ mọi bất biến
C. Giữ cùng cách mô tả lỗi của hợp đồng chung
D. Duy trì dữ liệu ở trạng thái hợp lệ sau gọi
Đáp án đúng: A

Câu 16: Vì sao Square extends MutableRectangle có setter width/height độc lập thường rắc rối?
A. Do Java không cho subclass override phương thức setter
B. Do Rectangle chỉ được phép có constructor không tham số
C. Do Square không thể gọi method area() từ superclass
D. Bất biến cạnh bằng nhau có thể phá kỳ vọng của client
Đáp án đúng: D

Câu 17: Chữ I trong SOLID biểu thị nguyên lý nào?
A. Implementation Sharing Principle
B. Interface Segregation Principle
C. Inheritance Selection Principle
D. Internal Service Principle
Đáp án đúng: B

Câu 18: Một interface OfficeMachine buộc máy in đơn giản cài scan() và fax() vi phạm gì?
A. ISP vì client bị ép phụ thuộc thao tác không cần
B. DIP vì máy in có thể được inject qua constructor
C. OCP vì interface có nhiều lớp triển khai khác nhau
D. SRP vì interface chứa nhiều kiểu dữ liệu đầu vào
Đáp án đúng: A

Câu 19: Thay interface OfficeMachine cồng kềnh bằng thiết kế nào hợp ISP?
A. Giữ nguyên interface và trả null ở scan, fax
B. Tách Printable, Scannable và Faxable
C. Thêm default method ném lỗi cho mọi máy in
D. Buộc mọi client chuyển sang class cụ thể
Đáp án đúng: B

Câu 20: Lợi ích của interface nhỏ theo ISP đối với mã client là gì?
A. Client luôn phải biết mọi implementation hiện tại
B. Mọi interface tự động không cần unit test riêng
C. Client chỉ phụ thuộc năng lực thực sự sử dụng
D. Mọi thay đổi ứng dụng đều không thể gây lỗi
Đáp án đúng: C

Câu 21: Chữ D trong SOLID là nguyên lý nào?
A. Data Initialization Principle
B. Dependency Inversion Principle
C. Delegation Isolation Principle
D. Database Interface Principle
Đáp án đúng: B

Câu 22: DIP định hướng module nghiệp vụ cấp cao phụ thuộc vào gì?
A. Concrete driver JDBC tạo bên trong use case
B. Cấu hình HTTP framework cho mọi domain rule
C. Abstraction thay vì chi tiết triển khai hạ tầng
D. Class Controller đang chứa các request mapping
Đáp án đúng: C

Câu 23: Nếu OrderService khởi tạo trực tiếp new SqlOrderRepository(), vấn đề DIP ở đâu?
A. Service đã phụ thuộc một interface repository ổn định
B. Repository đã được thay bằng fake trong mọi unit test
C. Service cấp cao ràng buộc implementation lưu trữ
D. Chi tiết persistence hiện đã độc lập mọi use case
Đáp án đúng: C

Câu 24: Khi triển khai DIP bằng Java, cách wiring nào giúp test được OrderService?
A. Service tự new Connection và QueryBuilder mỗi lần
B. Service dùng static global context để tìm entity
C. Repository import trực tiếp từng Controller cụ thể
D. Constructor nhận OrderRepository interface do bên ngoài cấp
Đáp án đúng: D

Câu 25: Dependency Injection và Dependency Inversion khác nhau như thế nào?
A. DI và DIP là hai tên cho cùng một từ khóa của Java
B. DI là cơ chế cấp dependency, DIP là nguyên tắc thiết kế
C. DIP chỉ áp dụng khi dùng framework Spring Boot
D. DI luôn bảo đảm DIP ngay cả khi inject concrete class
Đáp án đúng: B

Câu 26: Một abstraction phục vụ DIP nên thuộc phía nào khi domain cần đọc tỷ giá?
A. Buộc thuộc thư viện HTTP client của đối tác
B. Buộc thuộc package driver JDBC của database
C. Thuộc phía chính sách cần năng lực đọc tỷ giá
D. Buộc thuộc cụ thể class controller REST
Đáp án đúng: C

Câu 27: Một subtype đáp ứng chữ ký method nhưng trả sai ngữ nghĩa hợp đồng cho thấy điều gì?
A. ISP chỉ xét số lượng package được import
B. SRP chỉ cần đếm số dòng trong method
C. LSP cần kiểm thử hành vi, không chỉ kiểu tĩnh
D. DIP bắt buộc mọi object trả cùng reference
Đáp án đúng: C

Câu 28: Khi dự án nhỏ xuất hiện hàng chục interface chỉ có một implementation không có biến thể, đánh đổi gì cần cân nhắc?
A. Luôn cải thiện cohesion bất kể mọi lý do thay đổi
B. Luôn tăng tốc runtime vì Java có nhiều interface
C. Bắt buộc dùng inheritance để giảm số lớp
D. Tăng tầng trung gian mà lợi ích chưa rõ
Đáp án đúng: D
