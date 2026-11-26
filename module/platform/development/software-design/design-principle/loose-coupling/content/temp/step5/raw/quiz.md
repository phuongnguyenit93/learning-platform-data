OrderService tự `new JdbcOrderRepository()`; thiết kế nào giúp giảm phụ thuộc triển khai?
A. Chuyển lệnh SQL vào class của REST controller
B. Thêm một static factory chỉ trả JDBC repository
C. Cho OrderService kế thừa JdbcOrderRepository
D. Tiêm Repository interface qua constructor
Đáp án đúng: D

Theo Dependency Inversion, hướng import giữa core và adapter dữ liệu nào phù hợp?
A. Core import implementation vì cần tái dùng code SQL
B. Adapter phụ thuộc port của core, không có chiều ngược
C. Core gọi trực tiếp driver vì SQL được tối ưu hơn
D. Hai lớp import nhau để chọn implementation lúc chạy
Đáp án đúng: B

Constructor injection thường có lợi ích nào khi thiết kế thành phần Java?
A. Mọi dependency được lưu thành biến static dùng chung
B. Khai báo dependency rõ và dễ thay bằng fake
C. Các phụ thuộc không còn cần có interface nào
D. Object tự xây mọi dependency ngay trong constructor
Đáp án đúng: B

Một lớp cho client sửa trực tiếp `public Map` nội bộ gây rủi ro gì khi refactor?
A. Client phụ thuộc vào biểu diễn dữ liệu bên trong lớp
B. Class có thể thay Map thành List mà không ảnh hưởng ai
C. Các bất biến dữ liệu được bảo vệ bằng kiểu Map
D. Client chỉ biết hành vi công khai không biết cấu trúc
Đáp án đúng: A

Muốn đổi cấu trúc lưu trữ nhưng giữ client không phải sửa, nên ổn định điều gì?
A. Tên file cấu hình JDBC của riêng adapter
B. Giữ hợp đồng thao tác, che schema lưu trữ
C. Tên class triển khai của mỗi repository cụ thể
D. Cách framework lưu session của database
Đáp án đúng: B

Một unit test cần thay cổng gửi email mà không chạm SMTP thật; lựa chọn nào đúng?
A. Giữ tài khoản email thật trong một biến global
B. Tiêm fake EmailSender qua cùng contract của service
C. Mock chính use case rồi coi logic đã được test
D. Cho service tạo SMTPClient bằng toán tử new
Đáp án đúng: B

Một interface chung buộc client chỉ đọc dữ liệu phải triển khai method ghi; nên làm gì?
A. Bắt client ném lỗi cho mọi method không dùng
B. Thêm một service locator để lấy object interface
C. Đưa toàn bộ method vào lớp cha có body rỗng
D. Chia interface theo nhu cầu của client
Đáp án đúng: D

Một thành phần phát event để dịch vụ khác xử lý sau; lợi ích và đánh đổi nào có thể có?
A. Gọi bất đồng bộ sẽ tạo transaction chung nguyên tử
B. Broker bảo đảm từng consumer nhận đúng một lần
C. Mọi service nhận event ngay cả khi không đăng ký
D. Giảm phụ thuộc thời gian, cần xử lý trễ và trùng event
Đáp án đúng: D

Đổi tên một required field trong API đã có client cũ; cách tiến hóa nào ít gây đứt gãy?
A. Bỏ hợp đồng API và đọc dữ liệu từ database
B. Thay ngay field cũ vì client sẽ tự phát hiện schema
C. Giữ compatibility hoặc version contract theo kế hoạch
D. Cho client truy cập trực tiếp object trong service mới
Đáp án đúng: C

Vì sao service locator global có thể làm dependency khó quan sát?
A. Phụ thuộc thật bị giấu trong lời gọi lấy dịch vụ
B. Nó tự kiểm tra tính tương thích của mọi interface
C. Nó loại bỏ nhu cầu tạo các object tại thời gian chạy
D. Nó buộc constructor khai báo hết các dependency
Đáp án đúng: A

Đưa ORM entity trực tiếp vào API public gây coupling nào đáng chú ý?
A. Client gắn với cấu trúc entity vốn thay đổi nội bộ
B. Client chỉ còn phụ thuộc hợp đồng DTO độc lập DB
C. Thay đổi schema dữ liệu không thể ảnh hưởng entity
D. Dữ liệu truyền ra luôn được bảo vệ mọi bất biến
Đáp án đúng: A

Để test ranh giới giữa hai thành phần phụ thuộc interface, kiểm tra nào hữu ích?
A. Chỉ kiểm tra mọi method private có cùng thứ tự
B. Chỉ đếm số lần constructor của adapter được gọi
C. Xác minh contract đầu vào, đầu ra và cách báo lỗi
D. Chỉ so tên package của interface với implementation
Đáp án đúng: C

Hai service cùng đọc và ghi bảng DB do service khác sở hữu tạo vấn đề gì?
A. Mỗi service tự quản lý schema mà không ảnh hưởng ai
B. Database tự bảo đảm các service không phụ thuộc nhau
C. Coupling trực tiếp vào schema và vòng đời thay đổi
D. Contract giữa service được tách rõ qua API công khai
Đáp án đúng: C

Vì sao không nên tạo interface cho mọi class đơn giản chỉ để có loose coupling?
A. Mọi implementation đều trở nên bất biến khi có interface
B. Interface luôn thay thế được integration test giữa module
C. Dependency injection chỉ hỗ trợ class có hai interface
D. Indirection tăng dù chưa có ranh giới thay đổi thực
Đáp án đúng: D

Hai package import lẫn nhau làm thay đổi lan truyền; bước cải thiện nào thích hợp?
A. Cho hai package kế thừa cùng class chứa state
B. Đặt các class vào cùng package để bỏ mọi interface
C. Tách hợp đồng chung để dependency đi một chiều
D. Thêm nhiều static getter để truy cập vòng qua nhau
Đáp án đúng: C

Sau khi thay adapter lưu trữ, thước đo nào cho thấy ranh giới đã giảm coupling?
A. Phần nghiệp vụ và các test contract ít phải thay đổi
B. Số module import trực tiếp adapter tăng sau mỗi lần đổi
C. Tất cả call site chuyển sang new adapter bằng tay
D. Mọi class của ứng dụng cần sửa để khớp adapter mới
Đáp án đúng: A
