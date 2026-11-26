Câu 1: Trong Command Pattern, mục đích đóng gói thao tác thành object là gì?
A. Buộc Invoker biết toàn bộ API của Receiver
B. Đưa mọi lệnh trực tiếp vào controller gọi
C. Tách bên yêu cầu khỏi nơi thực thi thao tác
D. Chuyển toàn bộ trạng thái ứng dụng sang singleton
Đáp án đúng: C

Câu 2: Vai trò của Invoker trong Command Pattern là gì?
A. Tự triển khai logic nghiệp vụ của mọi Receiver
B. Kích hoạt execute mà không cần biết chi tiết Receiver
C. Định nghĩa cơ chế lưu trữ dữ liệu của ứng dụng
D. Tạo lại đối tượng Command sau mỗi câu lệnh SQL
Đáp án đúng: B

Câu 3: Receiver trong một Command thực hiện nhiệm vụ chính nào?
A. Chứa thao tác nghiệp vụ mà Command ủy quyền
B. Quyết định cách UI sắp xếp các button hành động
C. Chỉ lưu lịch sử các Command đã chạy trước đó
D. Chỉ khởi động task scheduler cho command queue
Đáp án đúng: A

Câu 4: Trong Java, abstraction Command tối thiểu thường khai báo gì?
A. Phương thức execute() để Invoker gọi thống nhất
B. Phương thức render() để tạo giao diện đa nền tảng
C. Phương thức query() để đọc toàn bộ bảng lệnh
D. Phương thức decode() để mở các kết nối mạng
Đáp án đúng: A

Câu 5: Vì sao nút Save nên gắn với SaveCommand thay vì gọi thẳng dịch vụ?
A. UI tự động có khả năng rollback mọi thay đổi
B. UI bắt buộc khởi động thread cho mỗi hành động
C. UI không cần biết chi tiết lưu trữ của Receiver
D. UI sẽ không cần kiểm tra input của người dùng
Đáp án đúng: C

Câu 6: Nếu lệnh chuyển tiền cần accountId và amount, thiết kế nào thích hợp?
A. Đọc accountId từ biến static dùng chung mọi lệnh
B. Để Invoker tự suy số tiền dựa tên lớp Command
C. Truyền trực tiếp HttpServletRequest vào Receiver
D. Giữ dữ liệu yêu cầu trong Command được khởi tạo
Đáp án đúng: D

Câu 7: MacroCommand thường được cấu tạo như thế nào?
A. Lưu nhiều Receiver để chọn một theo tên method
B. Lưu nhiều Command và gọi chúng theo trình tự
C. Tạo một Invoker mới sau khi mỗi lệnh kết thúc
D. Tự chuyển mọi Command sang xử lý đồng thời
Đáp án đúng: B

Câu 8: Trong lệnh tổng hợp, nếu bước ba thất bại sau hai bước thành công, cần xem xét gì?
A. Mặc định tất cả bước trước đã rollback tự động
B. Mặc định gọi lại toàn macro từ đầu không kiểm tra
C. Chính sách xử lý phần đã chạy hoặc bù trừ
D. Mặc định lệnh thứ tư sẽ sửa mọi lỗi trước
Đáp án đúng: C

Câu 9: Để hỗ trợ undo đổi tên tập tin, Command nên ghi nhận điều gì?
A. Chỉ thời điểm nút Undo được vẽ trên giao diện
B. Chỉ hash của lớp Invoker đang khởi chạy
C. Chỉ số thread đang xử lý thao tác rename
D. Đường dẫn hoặc tên cũ cần để khôi phục
Đáp án đúng: D

Câu 10: Một thao tác không thể đảo ngược hoàn toàn nên xử lý Undo thế nào?
A. Xác định giới hạn hoặc thực hiện bước bù phù hợp
B. Giả định gọi execute() lần nữa là đã undo
C. Đưa lệnh lại vào queue và coi là hoàn tác
D. Đổi tên method execute thành undo không sửa logic
Đáp án đúng: A

Câu 11: Redo sau Undo thường làm điều gì với một Command hợp lệ?
A. Gọi undo thêm lần nữa để hoàn thành redo
B. Xóa toàn bộ lịch sử lệnh chưa được thực thi
C. Chỉ kiểm tra nhật ký mà không áp dụng thay đổi
D. Thực hiện lại hành động đã hoàn tác theo chính sách
Đáp án đúng: D

Câu 12: Trong ứng dụng biên tập có Undo và Redo, nên quản lý lịch sử ra sao?
A. Dùng hai cấu trúc lịch sử theo thứ tự Undo/Redo
B. Lưu một biến boolean áp dụng cho mọi Command
C. Dùng một static Command duy nhất cho mọi thao tác
D. Đẩy mọi thao tác đã undo vào hàng đợi network
Đáp án đúng: A

Câu 13: Khi chạy lệnh mới sau một lần Undo, redo history thường được xử lý sao?
A. Giữ nguyên redo để trộn với lệnh mới bất kể thứ tự
B. Xóa nhánh redo cũ vì lịch sử đã rẽ hướng
C. Đổi redo history thành kết quả của database SELECT
D. Chạy hết mọi redo trước rồi mới nhận lệnh hiện tại
Đáp án đúng: B

Câu 14: Một Command đưa vào queue để chạy sau cần mang thông tin nào?
A. Tham chiếu thread cũ của UI đã đóng trước đó
B. Toàn bộ connection đang mở trong JVM của client
C. Địa chỉ trong bộ nhớ của Receiver ở tiến trình khác
D. Payload cần thiết và định danh loại thao tác
Đáp án đúng: D

Câu 15: Trong queue có retry, đặc tính nào giúp lệnh hạn chế tác dụng phụ lặp?
A. Idempotency key hoặc cơ chế chống xử lý trùng
B. Tự tăng thread priority cho mọi lần thực thi lại
C. Luôn tạo Command mới mà không giữ request ID
D. Gọi execute liên tục đến khi response HTTP 200
Đáp án đúng: A

Câu 16: Trong Java/Spring, cách gắn Receiver vào Command nào dễ kiểm thử?
A. Tìm bean toàn cục trong method execute mỗi lần
B. Tạo Receiver thật bên trong singleton Invoker
C. Tiêm dependency qua constructor theo interface
D. Gắn Receiver bằng field static có thể đổi tùy ý
Đáp án đúng: C

Câu 17: Invoker chạy nhiều Command song song trên một Receiver cần chú ý gì?
A. Tên file Java của các concrete Command đã đủ khác
B. Khả năng thread-safe của Receiver và trạng thái chia sẻ
C. Số lượng interface Command trong thư mục source
D. Chỉ số bytecode của phương thức execute()
Đáp án đúng: B

Câu 18: Với command thay đổi hai aggregate trong một database, transaction thường nên đặt ở đâu?
A. Chỉ ở phương thức render của UI Invoker
B. Chỉ trong constructor của lớp Command
C. Quanh nghiệp vụ execute cần tính nguyên tử
D. Chỉ ở bước tạo object Receiver lúc startup
Đáp án đúng: C

Câu 19: Nếu Invoker cần biết kết quả lệnh chạy async, thiết kế nào phù hợp?
A. Chờ bằng vòng lặp vô hạn bên trong giao diện
B. Đọc trực tiếp field private của thread đang chạy
C. Trả Future hoặc trạng thái công việc có thể tra cứu
D. Giả định lệnh hoàn tất ngay khi đưa vào queue
Đáp án đúng: C

Câu 20: Command khác Strategy ở trọng tâm mục đích nào?
A. Chỉ tổ chức nhiều cách tính cùng một phép toán
B. Chỉ thay thế một thuật toán cho object context
C. Chỉ cài interface để đổi cách sắp xếp dữ liệu
D. Đóng gói yêu cầu thực thi thay vì chọn thuật toán
Đáp án đúng: D

Câu 21: Command khác Observer trong tương tác đối tượng thế nào?
A. Publisher phát thông báo đến danh sách subscriber
B. Subscriber lắng nghe thay đổi trạng thái subject
C. Invoker kích hoạt một yêu cầu được đóng gói
D. Nhiều observer được gọi khi có sự kiện phát sinh
Đáp án đúng: C

Câu 22: Trong UI có menu và phím tắt cùng thực hiện Save, cách dùng Command nào hợp lý?
A. Mỗi thao tác sao chép logic lưu vào event handler
B. Menu ghi SQL còn phím tắt trực tiếp gọi file system
C. Mỗi Invoker tự thay đổi interface của Receiver
D. Cả hai Invoker dùng chung hợp đồng SaveCommand
Đáp án đúng: D

Câu 23: Khi unit test SaveCommand, nên kiểm chứng phần nào?
A. Tham số và số lần gọi Receiver qua fake hoặc mock
B. Kích thước window sau khi click Save trên mọi OS
C. Tốc độ vẽ icon của toolbar theo cấu hình theme
D. Khả năng JDBC pool phục hồi sau khi máy chủ mất mạng
Đáp án đúng: A

Câu 24: Khi kiểm thử Invoker, có thể dùng spy Command để xác nhận gì?
A. Receiver đã tạo đủ database index ở production
B. Lệnh được kích hoạt vào đúng thời điểm yêu cầu
C. Tất cả lịch sử Undo đều nhất quán qua các phiên
D. Mọi message queue đều bảo đảm đúng một lần giao
Đáp án đúng: B

Câu 25: Khi deserialize Command từ queue, biện pháp nào cần thiết?
A. Cho phép reflection tạo bất cứ class theo payload
B. Kiểm tra loại lệnh, quyền và schema payload
C. Chỉ kiểm tra tên topic rồi thực thi không xác thực
D. Bỏ bước validate để tránh tốn thời gian queue
Đáp án đúng: B

Câu 26: Để chẩn đoán lệnh nền thất bại, metadata nào hữu ích?
A. Màu giao diện nơi người dùng nhấn button
B. Vị trí con trỏ trong editor tại lúc khởi động
C. Tên đầy đủ mọi class được JVM nạp từ lúc start
D. Command ID, thời điểm, kết quả và lý do lỗi
Đáp án đúng: D

Câu 27: Khi lệnh có tác động gửi email hoặc gọi dịch vụ ngoài, undo nên được hiểu thế nào?
A. Có thể cần thao tác bù, không tự đảo ngược được
B. Transaction database sẽ thu hồi email đã gửi
C. Gọi undo tự xóa request ở hệ thống đối tác
D. Xóa Command object luôn thu hồi tác dụng phụ
Đáp án đúng: A

Câu 28: Đổi lấy khả năng mở rộng của Command Pattern, chi phí thiết kế thường là gì?
A. Mất khả năng thực hiện tác vụ bất đồng bộ
B. Thêm lớp Command và cơ chế quản lý vòng đời
C. Buộc tất cả Receiver kế thừa chung một concrete class
D. Không thể dùng Command với Java lambda expression
Đáp án đúng: B
