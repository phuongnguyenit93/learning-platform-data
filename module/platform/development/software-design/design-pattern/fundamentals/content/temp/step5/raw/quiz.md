Câu 1: Khi nào việc áp dụng một design pattern thường đáng cân nhắc?
A. Khi mọi class đều ngắn và không có biến thể nào
B. Khi vấn đề lặp lại và có điểm biến thể rõ ràng
C. Khi chỉ cần đổi định dạng tên biến trong mã Java
D. Khi có thể giảm số package mà không đổi hành vi
Đáp án đúng: B

Câu 2: Ba nhóm mẫu GoF truyền thống được phân loại thế nào?
A. Creational, Persistence và Presentation
B. Creational, Structural và Behavioral
C. Structural, Persistence và Deployment
D. Behavioral, Deployment và Concurrency
Đáp án đúng: B

Câu 3: Bộ mẫu thiết kế GoF cổ điển thường bao gồm bao nhiêu mẫu?
A. 23 mẫu được chia vào ba nhóm chính
B. 12 mẫu chỉ dành cho khởi tạo đối tượng
C. 18 mẫu chỉ dành cho cấu trúc object
D. 30 mẫu chỉ dành cho luồng xử lý event
Đáp án đúng: A

Câu 4: So với kế thừa sâu, composition thường mang lại lợi thế nào?
A. Buộc mọi implementation cố định từ lúc biên dịch
B. Cho phép class con đọc mọi biến private của lớp cha
C. Ghép hành vi linh hoạt bằng các đối tượng cộng tác
D. Loại bỏ nhu cầu xác định hợp đồng giữa đối tượng
Đáp án đúng: C

Câu 5: Nguyên lý Open/Closed ưu tiên kiểu mở rộng nào?
A. Mở mọi field thành public để module khác truy cập
B. Đổi mọi class thành abstract ngay từ lúc tạo
C. Cấm thay đổi mã kể cả khi có lỗi cần sửa
D. Thêm hành vi mới mà hạn chế sửa mã đã ổn định
Đáp án đúng: D

Câu 6: Dependency Inversion gợi ý phần nghiệp vụ quan trọng nên phụ thuộc vào gì?
A. Class JDBC driver do hạ tầng trực tiếp khởi tạo
B. Tên package framework web của môi trường triển khai
C. Abstraction ổn định thay vì implementation cụ thể
D. Cấu hình runtime được lưu trong static global field
Đáp án đúng: C

Câu 7: Trong UML class diagram, mũi tên tam giác rỗng với nét liền thường chỉ gì?
A. Dependency tạm thời giữa các phương thức
B. Composition sở hữu vòng đời đối tượng con
C. Aggregation dùng chung một tài nguyên bên ngoài
D. Generalization giữa lớp con và lớp cha
Đáp án đúng: D

Câu 8: Trong UML, nét đứt kèm tam giác rỗng thường biểu diễn quan hệ nào?
A. Class hiện thực một hợp đồng interface
B. Inheritance class với parent implementation
C. Composition giữa container và thành phần
D. Association giữa hai object cùng vòng đời
Đáp án đúng: A

Câu 9: Trong UML, hình thoi tô đen ở đầu quan hệ mang ý nghĩa gì?
A. Composition: sở hữu phần–toàn thể chặt
B. Dependency được gọi tạm trong một method
C. Interface realization qua phương thức ảo
D. Generalization từ subtype sang superclass
Đáp án đúng: A

Câu 10: Khi cần thể hiện thứ tự thông điệp giữa object theo thời gian, UML nào phù hợp?
A. Class diagram với thuộc tính và quan hệ
B. Package diagram với phụ thuộc giữa module
C. Deployment diagram với node triển khai
D. Sequence diagram với lifeline và message
Đáp án đúng: D

Câu 11: Nếu có nhiều thuật toán tính phí giao hàng thay đổi theo lựa chọn, mẫu nào phù hợp?
A. Observer phát thông báo khi đối tượng thay đổi
B. Memento lưu snapshot để khôi phục trạng thái
C. Composite duyệt cây theo cùng một interface
D. Strategy bọc các thuật toán có thể hoán đổi
Đáp án đúng: D

Câu 12: Đối tượng thay đổi hành vi theo trạng thái nội tại như Draft/Approved, mẫu nào hợp lý?
A. Strategy chỉ hoán đổi thuật toán do client chọn
B. Factory Method tạo đối tượng dựa trên subtype
C. State thay hành vi theo trạng thái hiện tại
D. Bridge tách hai trục mở rộng bằng composition
Đáp án đúng: C

Câu 13: Khi API thư viện cũ không khớp giao diện client mới, mẫu nào hữu ích?
A. Decorator bọc thêm hành vi cùng một interface
B. Observer phát sự kiện cho nhiều bên đăng ký
C. Builder xây dựng object theo từng bước
D. Adapter chuyển API cũ sang hợp đồng client
Đáp án đúng: D

Câu 14: Khi client cần giao diện đơn giản cho hệ subsystem phức tạp, dùng mẫu nào?
A. Facade đưa ra điểm truy cập cấp cao thống nhất
B. Proxy chỉ kiểm soát truy cập cùng một interface
C. Composite biểu diễn cây phần–toàn thể thống nhất
D. Flyweight chia sẻ trạng thái nội tại của object
Đáp án đúng: A

Câu 15: Muốn thêm logging lên một service mà vẫn giữ interface của nó, mẫu nào hợp lý?
A. Decorator bọc service để bổ sung hành vi
B. Adapter thay API cũ bằng hợp đồng không tương thích
C. Builder chia giai đoạn tạo object phức tạp
D. Iterator trừu tượng hóa thứ tự duyệt phần tử
Đáp án đúng: A

Câu 16: Khi trì hoãn tải ảnh lớn cho đến lần truy cập đầu, nên dùng mẫu nào?
A. Facade gom các thao tác subsystem thành một API
B. Observer gửi thay đổi trạng thái tới subscriber
C. Virtual Proxy quản lý truy cập và khởi tạo trễ
D. Memento lưu trạng thái cũ để khôi phục
Đáp án đúng: C

Câu 17: Khi nhiều view cần nhận thông báo lúc dữ liệu đổi, mẫu nào phù hợp?
A. Strategy hoán đổi thuật toán cho từng yêu cầu
B. Observer thông báo tới các subscriber đã đăng ký
C. Prototype tạo bản sao object từ mẫu có sẵn
D. Interpreter đánh giá cú pháp của ngôn ngữ nhỏ
Đáp án đúng: B

Câu 18: Khi các UI widget phụ thuộc chằng chịt lẫn nhau, mẫu nào giúp giảm liên kết trực tiếp?
A. Adapter ánh xạ interface của thư viện không khớp
B. Decorator thêm hành vi vào mỗi widget độc lập
C. Mediator điều phối tương tác giữa các widget
D. Singleton cung cấp một instance dùng chung
Đáp án đúng: C

Câu 19: Nếu superclass khai báo factory method và subclass quyết định sản phẩm, đó là mẫu nào?
A. Abstract Factory tạo cả họ sản phẩm qua object nhà máy
B. Builder xây object phức tạp theo chuỗi bước
C. Prototype sao chép object từ một instance mẫu
D. Factory Method để subclass chọn sản phẩm tạo ra
Đáp án đúng: D

Câu 20: Khi cần tạo cả họ Button và Checkbox tương thích theo giao diện, mẫu nào phù hợp?
A. Factory Method chỉ mô tả một cách tạo qua override
B. Abstract Factory tạo họ object cùng biến thể
C. Singleton bảo đảm một object cho toàn bộ ứng dụng
D. Iterator cung cấp cursor duyệt nhiều widget
Đáp án đúng: B

Câu 21: Muốn xây OrderRequest với nhiều thuộc tính tùy chọn nhưng vẫn dễ đọc, mẫu nào hợp lý?
A. Builder tạo object qua các bước cấu hình rõ ràng
B. Observer đăng ký nhận event sau khi object đổi
C. Facade rút gọn cách gọi vào các subsystem
D. Bridge tách hai chiều biến thể implementation
Đáp án đúng: A

Câu 22: Mẫu nào cố định khung thuật toán trong class cha nhưng cho subclass thay vài bước?
A. Strategy với đối tượng thuật toán được tiêm
B. Chain of Responsibility chuyển lời gọi dọc chuỗi
C. Command gói thao tác thành đối tượng riêng
D. Template Method với bước hook hoặc abstract
Đáp án đúng: D

Câu 23: Muốn xếp thao tác người dùng vào hàng đợi để thực thi sau, mẫu nào giúp ích?
A. Command đóng gói thao tác cùng tham số cần thiết
B. State chuyển logic theo tình trạng của đối tượng
C. Observer thông báo nhiều subscriber khi đổi dữ liệu
D. Proxy trì hoãn việc tạo tài nguyên tốn kém
Đáp án đúng: A

Câu 24: Một yêu cầu phê duyệt cần được chuyển dần qua nhiều cấp, mẫu nào phù hợp?
A. Mediator tập trung tương tác nhiều bên tại một điểm
B. Strategy chọn một thuật toán xử lý cố định
C. Chain of Responsibility chuyển yêu cầu qua các cấp
D. Memento giữ snapshot trước khi thay đổi trạng thái
Đáp án đúng: C

Câu 25: Khi nào sử dụng Singleton cho dependency dễ gây bất lợi nhất?
A. Khi object không có dữ liệu thay đổi giữa các lần gọi
B. Khi trạng thái chia sẻ làm test cô lập trở nên khó
C. Khi instance cần dùng chung một interface ổn định
D. Khi vòng đời object được quản lý qua dependency injection
Đáp án đúng: B

Câu 26: Trong Java, kiểm thử class phụ thuộc interface giúp ích điều gì?
A. Buộc mọi test phải khởi động server ứng dụng thật
B. Dùng fake dependency để xác nhận hành vi của class
C. Loại bỏ mọi nhu cầu kiểm chứng hợp đồng interface
D. Cho phép test bỏ qua tất cả các assertion kết quả
Đáp án đúng: B

Câu 27: Nếu một switch lớn kiểm tra loại thanh toán tăng thêm nhánh mỗi lần có provider mới, nên xem xét gì?
A. Chuyển toàn bộ switch sang constructor của entity
B. Tăng visibility của mọi field để gọi trực tiếp
C. Tách biến thể thành các class triển khai riêng
D. Thêm static singleton cho từng nhánh trong switch
Đáp án đúng: C

Câu 28: Tiêu chí thực tế quan trọng khi lựa chọn mẫu GoF cho codebase nhỏ là gì?
A. Càng nhiều lớp trừu tượng càng bảo đảm mã dễ đọc
B. Lợi ích mở rộng phải xứng với độ phức tạp phát sinh
C. Mọi vấn đề phải dùng đúng một pattern GoF riêng
D. Ưu tiên pattern khó nhất để chuẩn bị thay đổi chưa rõ
Đáp án đúng: B
