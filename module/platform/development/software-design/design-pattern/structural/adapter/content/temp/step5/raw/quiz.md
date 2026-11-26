Câu 1: Adapter Pattern giải quyết vấn đề thiết kế nào phổ biến nhất?
A. Nối hai interface không khớp mà không sửa client
B. Thêm trách nhiệm mới bằng nhiều wrapper cùng interface
C. Tạo một cây object có thể thao tác đồng nhất
D. Phân phối yêu cầu qua nhiều handler có điều kiện
Đáp án đúng: A

Câu 2: Trong Adapter, Target đóng vai trò gì đối với mã client?
A. Interface gốc của thư viện cần tích hợp
B. Lớp tạo adapter theo cấu hình môi trường
C. Đối tượng quản lý vòng đời của plugin
D. Interface mà client mong muốn sử dụng
Đáp án đúng: D

Câu 3: Trong ví dụ tích hợp thư viện cũ, Adaptee là thành phần nào?
A. Đối tượng cung cấp API cũ cần được chuyển đổi
B. Giao diện ổn định mà mã gọi mới phụ thuộc
C. Bộ kiểm thử chạy trên lớp adapter mới
D. Đối tượng xây dựng request domain từ form
Đáp án đúng: A

Câu 4: Object Adapter thường liên kết Adaptee bằng cách nào?
A. Giữ tham chiếu Adaptee rồi ủy quyền lời gọi
B. Kế thừa trực tiếp toàn bộ implementation Adaptee
C. Đổi chữ ký method của Adaptee lúc biên dịch
D. Sửa mã client để gọi Adaptee thay vì Target
Đáp án đúng: A

Câu 5: Class Adapter cổ điển thường dùng cơ chế OOP nào?
A. Composition thuần túy với các instance Adaptee
B. Kế thừa Adaptee và hiện thực Target
C. Observer để phát sự kiện cho client hiện có
D. Factory Method để cấp một instance duy nhất
Đáp án đúng: B

Câu 6: Trong Java, điều gì giới hạn Class Adapter khi Adaptee là class?
A. Một class không thể implements nhiều interface
B. Một class không thể kế thừa hai class khác nhau
C. Java không cho phép override method kế thừa
D. Java cấm tạo constructor trong lớp kế thừa
Đáp án đúng: B

Câu 7: Khi Adaptee được khai báo final, lựa chọn nào thường dùng được?
A. Object Adapter bao bọc instance của Adaptee
B. Class Adapter extends trực tiếp Adaptee final
C. Subclass Adaptee thay toàn bộ method public
D. Override bytecode của Adaptee ở runtime
Đáp án đúng: A

Câu 8: Client nên phụ thuộc vào thành phần nào để thay SDK dễ hơn?
A. Concrete Adaptee để dùng thêm method nội bộ
B. Target interface thay vì lớp SDK cụ thể
C. Mọi implementation Adapter trong cùng method
D. Factory constructor của SDK tại từng lần gọi
Đáp án đúng: B

Câu 9: PaymentPort nhận Money nhưng SDK cũ yêu cầu số xu, Adapter nên làm gì?
A. Thay đổi Money của domain thành số xu vĩnh viễn
B. Chuyển Money sang đơn vị xu trước khi gọi SDK
C. Buộc controller tự đổi đơn vị trước mọi use case
D. Lưu nguyên số tiền bằng float trong static field
Đáp án đúng: B

Câu 10: Đối với tiền tệ, yêu cầu nào quan trọng khi Adapter đổi đơn vị?
A. Chuyển mọi số tiền sang float để tăng tốc độ
B. Bỏ currency vì SDK mặc định loại tiền đã đúng
C. Dùng phép đổi chính xác và kiểm tra phần làm tròn
D. Luôn làm tròn về số nguyên trước khi đổi đơn vị
Đáp án đúng: C

Câu 11: SDK trả timestamp giây Unix, client dùng Instant, Adapter cần gì?
A. Xem mỗi giá trị giây là mili giây mặc định
B. Gắn timezone hệ điều hành làm epoch mới
C. Đổi đúng đơn vị giây khi tạo Instant
D. Chuyển timestamp thành tên ngày mà không xét offset
Đáp án đúng: C

Câu 12: SDK cũ ném LegacyTimeoutException, hợp đồng mới yêu cầu GatewayTimeout, nên làm gì?
A. Để mọi client import LegacyTimeoutException
B. Bắt toàn bộ lỗi rồi coi giao dịch thành công
C. Bỏ exception và trả null không ghi nguyên nhân
D. Ánh xạ lỗi hạ tầng sang loại lỗi Target quy định
Đáp án đúng: D

Câu 13: Khi Adapter gặp mã kết quả SDK chưa từng định nghĩa trong Target, cách làm nào an toàn?
A. Bắt buộc coi mọi mã lạ là kết quả thành công
B. Chuyển mã lạ thành status OK để tránh lỗi
C. Dùng một mã mặc định bất kể ý nghĩa nghiệp vụ
D. Trả lỗi ánh xạ không hỗ trợ kèm ngữ cảnh
Đáp án đúng: D

Câu 14: Adaptee có thể trả null trong khi Target dùng Optional, Adapter nên làm gì?
A. Trả null thay cho Optional vì client tự biết
B. Tạo Optional.of(null) cho mọi response rỗng
C. Đổi null thành Optional.empty khi không có giá trị
D. Ném lỗi hệ thống cho mọi trường hợp thiếu dữ liệu
Đáp án đúng: C

Câu 15: Nếu API cũ trả response dạng chuỗi phân tách, Adapter phù hợp xử lý gì?
A. Đưa nguyên chuỗi vào mọi domain entity
B. Parse dữ liệu rồi ánh xạ thành DTO Target
C. Yêu cầu client hiểu định dạng legacy gốc
D. Đổi toàn bộ mô hình domain sang chuỗi thô
Đáp án đúng: B

Câu 16: Vì sao không nên đặt trực tiếp type của SDK trong Target interface?
A. Làm tăng số lượng request HTTP trong client
B. Làm Java không thể biên dịch một class adapter
C. Làm lớp Target luôn bị đánh dấu deprecated
D. Làm rò rỉ dependency và cản trở thay Adaptee
Đáp án đúng: D

Câu 17: Một API cung cấp CompletionStage nhưng Target là đồng bộ, rủi ro khi bridge là gì?
A. Mọi CompletionStage đều chạy xong trước khi trả
B. SDK tự chuyển sang callback đồng bộ khi gọi join
C. Chờ kết quả có thể chặn thread và gây timeout
D. Việc chờ luôn không ảnh hưởng đến thông lượng
Đáp án đúng: C

Câu 18: Khi Adaptee hỗ trợ gọi theo trang còn Target muốn stream, Adapter cần chú ý gì?
A. Luôn tải toàn bộ trang vào RAM trước mọi lời gọi
B. Lấy trang theo nhu cầu và giải phóng tài nguyên
C. Tạo một stream không bao giờ đóng kết nối nguồn
D. Bỏ dấu hiệu hết dữ liệu khi chuyển sang stream
Đáp án đúng: B

Câu 19: Nếu SDK không thread-safe, Adapter dùng chung nên giải quyết thế nào?
A. Mặc định mọi method SDK đều thread-safe
B. Đưa instance SDK vào public static mutable field
C. Bỏ kiểm tra vì Adapter có interface bất biến
D. Điều phối truy cập hoặc tạo instance theo chính sách
Đáp án đúng: D

Câu 20: Tại sao tiêm SDK vào Object Adapter qua constructor có ích?
A. Bắt buộc tạo một SDK mới mỗi lần gọi method
B. Cho phép client đổi chữ ký interface Target
C. Loại bỏ mọi nhu cầu kiểm tra dữ liệu đầu vào
D. Dễ thay SDK giả trong unit test và cấu hình
Đáp án đúng: D

Câu 21: Adapter và Facade khác nhau cơ bản theo mục tiêu nào?
A. Adapter gom mọi subsystem; Facade sửa interface client
B. Adapter chuyên tạo object; Facade chuyên lưu snapshot
C. Adapter đổi interface; Facade đơn giản hóa subsystem
D. Adapter quản lý undo; Facade quản lý chuỗi sự kiện
Đáp án đúng: C

Câu 22: Adapter và Decorator có khác biệt quan trọng nào?
A. Adapter đổi hợp đồng; Decorator giữ hợp đồng để mở rộng
B. Adapter luôn kế thừa; Decorator luôn tạo class final
C. Adapter thêm trạng thái; Decorator chuyển đổi kiểu số
D. Adapter tạo thuật toán; Decorator chọn successor
Đáp án đúng: A

Câu 23: Để unit test phép chuyển đổi tiền trong Adapter, cần khẳng định gì?
A. Thư viện SDK thật có giao diện đẹp trên trình duyệt
B. SDK fake nhận đúng đơn vị và số tiền quy đổi
C. Adapter có ít method hơn mọi interface hệ thống
D. Tất cả nhánh giao dịch đều được chạy trên production
Đáp án đúng: B

Câu 24: Kiểm thử integration Adapter với SDK thật nhằm phát hiện điều gì?
A. Cú pháp của giao diện người dùng trên mọi thiết bị
B. Khả năng thay mọi repository trong ứng dụng khác
C. Sai khác chữ ký, dữ liệu và lỗi từ integration thực
D. Độ bao phủ của toàn bộ business rule trong domain
Đáp án đúng: C

Câu 25: Khi đổi SDK phiên bản mới, regression test của Adapter nên ưu tiên gì?
A. Giữ nguyên hành vi Target với các tình huống quan trọng
B. Đổi hợp đồng Target theo mọi method mới của SDK
C. Bỏ toàn bộ test cũ vì SDK đã tăng version
D. Chỉ kiểm tra constructor mới không ném exception
Đáp án đúng: A

Câu 26: Nếu Adapter ném exception làm lộ token/secret của SDK, cách xử lý phù hợp là gì?
A. Gắn request token nguyên vẹn vào mọi log lỗi
B. Trả toàn bộ headers SDK cho client để debug
C. Cho phép stack trace chứa secret trong API response
D. Ẩn secret khi chuyển lỗi và ghi log có kiểm soát
Đáp án đúng: D

Câu 27: Khi một SDK phục vụ nhiều client Target khác nhau, cách thiết kế nào khả thi?
A. Bắt mọi client sửa API trực tiếp theo SDK duy nhất
B. Đưa mọi Target vào một lớp Adaptee global
C. Có adapter riêng theo từng Target cần tương thích
D. Sao chép toàn bộ mã SDK vào từng client
Đáp án đúng: C

Câu 28: Khi nào không cần thêm Adapter cho một thư viện mới?
A. Khi interface đã phù hợp và wrapper không thêm giá trị
B. Khi SDK có hơn hai phương thức public
C. Khi client cần viết unit test cho integration
D. Khi có thể tạo một lớp proxy quanh SDK
Đáp án đúng: A
