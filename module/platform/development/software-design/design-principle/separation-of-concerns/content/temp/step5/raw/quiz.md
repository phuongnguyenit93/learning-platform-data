Câu 1: Một Controller vừa dựng HTML, tính giảm giá và ghi SQL vi phạm Separation of Concerns ở đâu?
A. Chia nghiệp vụ thành nhiều service theo use case
B. Trộn giao diện, nghiệp vụ và truy cập dữ liệu
C. Giữ DTO riêng khi trả dữ liệu cho client web
D. Tạo repository độc lập để kiểm soát truy vấn
Đáp án đúng: B

Câu 2: Trong Separation of Concerns, một concern thường được hiểu như thế nào?
A. Một lớp Java bắt buộc chỉ có một phương thức public
B. Một bảng dữ liệu được quản lý bởi một singleton
C. Một mối quan tâm có trách nhiệm và lý do thay đổi
D. Một package luôn tương ứng một tiến trình riêng
Đáp án đúng: C

Câu 3: Nếu cần thay giao diện web bằng CLI mà không đổi xử lý đơn hàng, thiết kế nào hợp lý?
A. Di chuyển toàn bộ quy tắc đơn hàng sang CLI mới
B. Bắt repository phân tích tham số dòng lệnh CLI
C. Cho domain entity trực tiếp render template HTML
D. Dùng hai adapter đầu vào gọi chung dịch vụ nghiệp vụ
Đáp án đúng: D

Câu 4: Thành phần nào phù hợp chịu trách nhiệm ánh xạ JSON request thành lệnh nghiệp vụ?
A. Lớp domain quản lý cấu hình Jackson của server
B. Lớp repository xử lý tất cả thông tin HTTP header
C. Lớp giao tiếp HTTP chuyển DTO sang dữ liệu ứng dụng
D. Bộ driver database chọn URL cho request REST
Đáp án đúng: C

Câu 5: Quy tắc không cho chuyển tiền vượt số dư nên được bảo vệ ở đâu?
A. Chỉ trong JavaScript của trang nhập số tiền
B. Chỉ trong template dùng để hiển thị giao dịch
C. Chỉ trong bộ chuyển JSON của HTTP controller
D. Tầng nghiệp vụ duy trì bất biến dù không có UI
Đáp án đúng: D

Câu 6: Repository trong ứng dụng được phân chia rõ concern thường tập trung vào gì?
A. Truy xuất và lưu trữ dữ liệu theo hợp đồng
B. Hiển thị thông báo lỗi theo ngôn ngữ giao diện
C. Kiểm soát màu nút bấm và bố cục màn hình
D. Quyết định chính sách giảm giá cho mọi người
Đáp án đúng: A

Câu 7: Khi use case trực tiếp khởi tạo HttpClient và gọi API bên ngoài, thay đổi nào giúp tách concern?
A. Đưa logic gọi mạng vào getter của domain entity
B. Cho Controller trực tiếp thực hiện toàn bộ use case
C. Đặt hợp đồng cổng dịch vụ rồi chuyển gọi mạng ra adapter
D. Lưu endpoint HTTP trong static field của entity
Đáp án đúng: C

Câu 8: Lợi ích của interface giữa application service và kho dữ liệu là gì?
A. Bảo đảm mọi truy vấn database đều nhanh hơn
B. Tự phát hiện mọi lỗi về transaction lúc biên dịch
C. Tự loại bỏ mọi phụ thuộc của web vào service
D. Giúp thay nguồn lưu trữ mà ít ảnh hưởng quy tắc
Đáp án đúng: D

Câu 9: Vì sao không nên trả JPA Entity trực tiếp làm REST response khi có trường nội bộ?
A. Giúp schema API thay đổi độc lập với database
B. Giúp client nhận ít trường hơn mà không cần mapping
C. Bảo đảm lazy loading không chạy ngoài transaction
D. Làm lộ dữ liệu và gắn hợp đồng API với persistence
Đáp án đúng: D

Câu 10: Một thao tác đặt hàng cần trừ kho và ghi đơn nguyên tử; concern nào điều phối transaction?
A. View template xác định lúc commit toàn bộ SQL
B. Application service ở ranh giới use case thích hợp
C. HTTP DTO tự mở transaction khi được deserialize
D. Domain entity tự truy cập connection pool trực tiếp
Đáp án đúng: B

Câu 11: Khi service báo OrderNotFound, việc đổi thành HTTP 404 nên được xử lý ở đâu?
A. Tại lớp HTTP adapter hoặc exception mapping
B. Trong domain entity để trả ResponseEntity chuẩn
C. Trong kho dữ liệu bằng cách ghi status vào bảng
D. Trong bộ driver để chuyển ngoại lệ thành JSON
Đáp án đúng: A

Câu 12: Để test nghiệp vụ tính phí mà không cần database, kiến trúc nên hỗ trợ gì?
A. Luôn khởi động đầy đủ database production
B. Dùng fake dependency thay persistence thực tế
C. Đưa quy tắc phí vào view rồi snapshot HTML
D. Gắn mọi nghiệp vụ vào một singleton repository
Đáp án đúng: B

Câu 13: Test nào xác minh được repository ánh xạ đúng vào schema database?
A. Chỉ unit test domain với repository fake
B. Integration test dùng database kiểm thử phù hợp
C. Chỉ snapshot giao diện từ browser có mock
D. Chỉ kiểm tra tên lớp implements interface
Đáp án đúng: B

Câu 14: Đăng nhập và phân quyền dùng ở nhiều endpoint là ví dụ của loại concern nào?
A. Concern chỉ liên quan một template HTML đơn
B. Concern chỉ thuộc mapping từ Entity sang DTO
C. Concern xuyên suốt cần cơ chế nhất quán
D. Concern chỉ thuộc thuật toán tính phí giao hàng
Đáp án đúng: C

Câu 15: Cách tách logging trải khắp các use case nào thường phù hợp?
A. Dùng decorator hoặc interceptor ở ranh giới phù hợp
B. Chép cùng đoạn log vào mọi dòng domain rule
C. Đưa toàn bộ sự kiện log vào mọi field JPA
D. Gọi logging từ view để thay thế service
Đáp án đúng: A

Câu 16: Vì sao không nên đưa tất cả validation vào controller rồi bỏ qua domain?
A. Domain sẽ tự xác nhận input nếu không có rule
B. Repository luôn ngăn được mọi lỗi giá trị nghiệp vụ
C. Controller luôn là entry point duy nhất của ứng dụng
D. Đường gọi khác UI vẫn có thể làm sai bất biến
Đáp án đúng: D

Câu 17: Thành phần quản lý secrets và endpoint theo môi trường nên được đặt theo concern nào?
A. Cấu hình hạ tầng được tiêm qua ranh giới rõ
B. Quy tắc domain chứa mật khẩu cố định trong code
C. View template phân phối khóa bí mật cho các class
D. DTO response mang connection string tới client
Đáp án đúng: A

Câu 18: Nếu module nghiệp vụ import trực tiếp package của web framework, tín hiệu nào xuất hiện?
A. Mã domain bị liên kết với chi tiết trình bày
B. Lớp web được cô lập khỏi mọi thay đổi nghiệp vụ
C. Hợp đồng ứng dụng đã tự động độc lập framework
D. Mọi truy vấn persistence sẽ được thực thi nhanh
Đáp án đúng: A

Câu 19: Để ranh giới component có ý nghĩa, API trao đổi nên làm gì?
A. Chuyển trực tiếp mọi đối tượng driver và session
B. Cho phép bên gọi tùy ý sửa trạng thái shared cache
C. Thể hiện dữ liệu cần thiết, tránh lộ chi tiết nội bộ
D. Buộc client biết tất cả class concrete đang dùng
Đáp án đúng: C

Câu 20: Nếu một thay đổi về email template buộc sửa phương thức tính thuế, triệu chứng chính là gì?
A. Hai component có hợp đồng tách biệt rõ ràng
B. Hai trách nhiệm không liên quan bị ràng buộc nhau
C. Đã giảm coupling nhờ chia package bằng tên
D. Dữ liệu persistence đang được tái sử dụng tốt
Đáp án đúng: B

Câu 21: Trong quá trình refactor tách một lớp trộn nhiều concern, bước nào giảm rủi ro?
A. Đổi mọi tên class và xóa test để bắt đầu lại
B. Tách toàn bộ class cùng lúc không đối chiếu output
C. Thay luôn database và framework trong cùng commit
D. Bổ sung characterization tests rồi tách từng trách nhiệm
Đáp án đúng: D

Câu 22: Lợi thế thực tiễn của việc giữ giao diện ngoài domain rule là gì?
A. Dễ thay kênh tương tác và test nghiệp vụ độc lập
B. Loại bỏ hoàn toàn mọi nhu cầu chạy integration test
C. Buộc domain dùng chung tất cả HTTP DTO và header
D. Cho phép UI quyết định chính sách giá mà không test
Đáp án đúng: A

Câu 23: Nếu một service chỉ chuyển mọi lời gọi sang tầng khác mà không thêm quy tắc, nên xem xét gì?
A. Mọi service bắt buộc phải có ít nhất ba tầng wrapper
B. Cần thêm kế thừa để làm sâu chuỗi lời gọi hơn
C. Có thể đang tạo lớp chuyển tiếp không mang giá trị
D. Bắt buộc chuyển tiếp qua message broker từ nay
Đáp án đúng: C

Câu 24: Tách mỗi phương thức nhỏ thành một microservice có phải luôn cải thiện SoC không?
A. Có, vì mọi concern đều phải triển khai tiến trình riêng
B. Có, vì tách process tự xóa coupling dữ liệu
C. Không, chi phí mạng và vận hành có thể vượt lợi ích
D. Không, vì các module Java không hỗ trợ interface
Đáp án đúng: C

Câu 25: Chỉ số hoặc dấu hiệu nào gợi ý một class đang ôm nhiều concern?
A. Mọi method tuân theo cùng một hợp đồng nghiệp vụ
B. Nhiều nhóm method đổi vì các lý do không liên quan
C. Thay một thuật toán chỉ phải sửa một module
D. Các dependency đều thuộc một capability ổn định
Đáp án đúng: B

Câu 26: Khi thay database SQL bằng document store, điều gì nên được khoanh vùng?
A. Toàn bộ giao diện web và quy tắc chiết khấu
B. Adapter lưu trữ và phần ánh xạ dữ liệu cụ thể
C. Mọi use case phải đổi sang trả tài liệu database
D. Tất cả DTO public phải mang loại tài khoản DB
Đáp án đúng: B

Câu 27: Nếu hai thành phần phải trao đổi rất nhiều state nội bộ, bước đánh giá nào hợp lý?
A. Đẩy toàn bộ field thành public để giảm mapping
B. Thêm dependency vòng để cả hai tự xem dữ liệu
C. Gộp hệ thống vào một static utility không test
D. Xem lại trách nhiệm, hợp đồng và độ kết dính
Đáp án đúng: D

Câu 28: Tradeoff quan trọng khi tách concern thành quá nhiều lớp là gì?
A. Tăng indirection và chi phí hiểu luồng xử lý
B. Giảm mọi khả năng thay đổi phần mềm về sau
C. Loại bỏ nhu cầu đặt tên API giữa các lớp
D. Tự bảo đảm tất cả phần mềm chạy nhanh hơn
Đáp án đúng: A
