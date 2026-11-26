Câu 1. Dependency Rule trong Clean Architecture yêu cầu hướng phụ thuộc mã nguồn ra sao?
A. Use case import repository triển khai của database
B. Lớp ngoài phụ thuộc abstraction thuộc lớp trong
C. Entity nghiệp vụ import controller để nhận request
D. Lớp trong phụ thuộc trực tiếp framework phía ngoài
Đáp án đúng: B

Câu 2. Entity theo nghĩa Clean Architecture cần hiểu thế nào?
A. Luôn là lớp có annotation @Entity của ORM
B. Luôn là bảng vật lý mà database cấp khóa
C. Luôn chứa logic chuyển đổi JSON cho API
D. Cốt lõi nghiệp vụ, độc lập công nghệ ORM
Đáp án đúng: D

Câu 3. Trong một luồng đặt hàng, lớp use case phù hợp nhất để thực hiện việc gì?
A. Chỉ format response JSON và status HTTP
B. Chỉ cấu hình kết nối JDBC tới database
C. Điều phối các quy tắc của thao tác đặt hàng
D. Chỉ khai báo route của controller web
Đáp án đúng: C

Câu 4. Controller HTTP trong Clean Architecture nên tương tác với phần nào?
A. Gọi trực tiếp các entity qua SQL driver
B. Gọi input boundary hoặc use case phù hợp
C. Định nghĩa schema database cho từng request
D. Tự quyết định quy tắc giá và chiết khấu
Đáp án đúng: B

Câu 5. Khi use case cần lưu Order, giao diện persistence gateway thường được định nghĩa ở đâu?
A. Lớp trong, nơi use case cần port lưu trữ
B. Lớp ngoài chỉ nơi cụ thể dùng ORM nào
C. Màn hình web trực tiếp nơi nhận đơn hàng
D. Lớp framework cung cấp mặc định một gateway
Đáp án đúng: A

Câu 6. Vai trò của repository adapter ngoài cùng là gì?
A. Xác định quy tắc nghiệp vụ cốt lõi của Order
B. Buộc entity domain gọi trực tiếp cơ sở dữ liệu
C. Tạo DTO giao diện thay cho toàn bộ use case
D. Hiện thực gateway bằng adapter lưu trữ cụ thể
Đáp án đúng: D

Câu 7. Khi thay PostgreSQL bằng kho lưu trữ khác, thiết kế nào ít ảnh hưởng use case?
A. Use case phụ thuộc port lưu trữ ổn định
B. Use case tạo trực tiếp JDBC connection mới
C. Entity chứa câu SQL dùng cú pháp PostgreSQL
D. Controller giữ chi tiết khóa chính của database
Đáp án đúng: A

Câu 8. Composition root trong Clean Architecture chủ yếu làm nhiệm vụ nào?
A. Xác định tất cả business rule trong entity
B. Chứa truy vấn SQL đặc thù của từng use case
C. Lắp ráp port và adapter khi khởi tạo hệ thống
D. Thay mọi controller bằng một entity chung
Đáp án đúng: C

Câu 9. Điều gì vi phạm Dependency Rule ở lớp nghiệp vụ?
A. Controller ánh xạ JSON thành input model
B. Adapter gọi input boundary của use case
C. Main module khởi tạo adapter cho ứng dụng
D. Use case import HTTP controller bên ngoài
Đáp án đúng: D

Câu 10. Vì sao không nên để use case trả trực tiếp kiểu framework response như ResponseEntity?
A. Vì use case không thể tạo bất kỳ giá trị trả về
B. Vì làm nghiệp vụ phụ thuộc framework web
C. Vì response HTTP luôn là dữ liệu bất biến
D. Vì chỉ adapter database mới trả được dữ liệu
Đáp án đúng: B

Câu 11. Một dự án có đúng bốn tầng thư mục nhưng business rule vẫn import ORM; kết luận nào đúng?
A. Đã là Clean Architecture vì đủ bốn tầng
B. Tầng ngoài luôn được phép gọi ngược vào domain
C. Cần xem hướng phụ thuộc, số tầng chưa đủ
D. Chỉ cần đổi tên thư mục để hợp lệ kiến trúc
Đáp án đúng: C

Câu 12. Khi đổi web framework, thiết kế nào giúp giữ use case ổn định?
A. Use case nhận trực tiếp HttpServletRequest
B. Adapter web mới vẫn gọi cùng input boundary
C. Entity đọc thông tin session của framework cũ
D. Controller cũ được copy toàn bộ vào domain
Đáp án đúng: B

Câu 13. Muốn unit test use case không kết nối database thật, nên dùng gì?
A. Fake implementation của gateway được tiêm vào
B. Controller production trỏ tới database chính
C. Entity tự gọi repository tĩnh ở môi trường test
D. Mỗi test khởi tạo toàn bộ application server
Đáp án đúng: A

Câu 14. Để tự động phát hiện domain import package infrastructure, nên làm gì?
A. Dùng unit test chỉ xác minh số bản ghi lưu
B. Chỉ kiểm tra file README sau mỗi lần merge
C. Dùng formatter để đổi tên package theo chuẩn
D. Thêm kiểm thử phụ thuộc kiến trúc trên CI
Đáp án đúng: D

Câu 15. Use case cần giao dịch nhưng không muốn phụ thuộc thư viện transaction; hướng thiết kế nào phù hợp?
A. Định nghĩa port giao dịch, thực hiện ở lớp ngoài
B. Nhúng annotation ORM vào mọi entity nghiệp vụ
C. Bắt controller trực tiếp commit từng câu SQL
D. Loại bỏ mọi transaction khi lưu nhiều bản ghi
Đáp án đúng: A

Câu 16. Nếu use case phát sự kiện nghiệp vụ và cần gửi tới message broker, nên tổ chức thế nào?
A. Domain tạo connection tới broker mỗi khi phát sự kiện
B. Entity chuyển sự kiện trực tiếp sang bytecode broker
C. Use case gọi port, adapter ngoài gửi tới broker
D. Web controller luôn phát event thay mọi use case
Đáp án đúng: C

Câu 17. Output boundary dùng để đưa kết quả từ use case ra ngoài; adapter nào có thể implement nó?
A. Domain entity được đánh dấu làm HTTP route
B. Gateway database trực tiếp kết xuất HTML
C. Presenter chuyển output thành view model
D. Mọi lớp framework đều cần kế thừa use case
Đáp án đúng: C

Câu 18. Database schema và cấu hình ORM thuộc khu vực nào trong cách nhìn Clean Architecture?
A. Chi tiết hạ tầng ở lớp ngoài của ứng dụng
B. Quy tắc nghiệp vụ cốt lõi ở entity domain
C. Định nghĩa input boundary của mọi use case
D. Trách nhiệm chính của presentation interface
Đáp án đúng: A

Câu 19. Khi nghiệp vụ cần gọi dịch vụ thanh toán bên ngoài, cách nào giữ use case độc lập?
A. Use case biết rõ URL và HTTP client của đối tác
B. Entity lưu cấu hình API key cùng business rule
C. Controller tự thanh toán trước khi gọi use case
D. Use case gọi port thanh toán, adapter thực thi
Đáp án đúng: D

Câu 20. Một use case cần dữ liệu từ hai gateway; cách wiring nào phù hợp?
A. Tiêm cả hai port, ghép implementation ở root
B. Gộp cả hai database adapter vào entity nghiệp vụ
C. Để gateway A tự import controller của gateway B
D. Tạo dependency ngược từ use case vào module web
Đáp án đúng: A

Câu 21. Dùng input model riêng cho use case có lợi ích đặc trưng nào?
A. Use case cần biết mọi field của HTTP request
B. Dữ liệu đúng nhu cầu, độc lập giao thức web
C. Buộc mọi adapter dùng DTO của framework web
D. Loại bỏ hoàn toàn bước validate đầu vào
Đáp án đúng: B

Câu 22. Khi thay dịch vụ gửi email thực bằng giả lập trong test, điều gì giúp thực hiện dễ dàng?
A. Use case tự khởi tạo SMTP client mới
B. Entity gọi trực tiếp thư viện gửi email
C. Port email cho phép thay adapter khi test
D. Controller luôn tắt toàn bộ logic gửi email
Đáp án đúng: C

Câu 23. Trong luồng tạo đơn, đặt kiểm tra quy tắc hạn mức tín dụng ở đâu để nhiều UI dùng chung?
A. Chỉ ở JavaScript của giao diện người dùng
B. Chỉ ở controller HTTP dành cho ứng dụng web
C. Chỉ trong ràng buộc dữ liệu của database
D. Trong entity hoặc use case giữ quy tắc nghiệp vụ
Đáp án đúng: D

Câu 24. Dấu hiệu nào cho thấy entity đang gắn quá chặt với cơ chế lưu trữ?
A. Entity tự kiểm tra tổng số tiền phải không âm
B. Entity import Hibernate Session để tự query
C. Use case gọi entity để áp dụng quy tắc giảm giá
D. Gateway mapping dữ liệu sang object domain
Đáp án đúng: B
