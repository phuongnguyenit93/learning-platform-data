Câu 1: SpotBugs chủ yếu dựa vào đầu vào nào để phân tích mã Java?
A. Mã Java chưa biên dịch cùng thông tin lớp liên quan
B. Log Java khi chạy thử cùng thông tin lớp liên quan
C. Bytecode Java đã biên dịch cùng thông tin lớp liên quan
D. Báo cáo test coverage cùng thông tin lớp liên quan
Đáp án đúng: C

Câu 2: Vì sao build thường cần biên dịch trước khi chạy SpotBugs?
A. Vì bộ phân tích cần các file .class làm đầu vào
B. Vì bộ phân tích cần kết quả benchmark để so sánh
C. Vì bộ phân tích cần log HTTP từ máy chủ đang chạy
D. Vì bộ phân tích cần thống kê commit từ Git
Đáp án đúng: A

Câu 3: Trong Gradle, lệnh nào thường quét code production với plugin SpotBugs?
A. ./gradlew spotbugsTest
B. ./gradlew checkstyleMain
C. ./gradlew spotbugsMain
D. ./gradlew spotlessCheck
Đáp án đúng: C

Câu 4: Cảnh báo null dereference trong SpotBugs thể hiện nguy cơ nào?
A. Biến có thể null nhưng vẫn được dùng để gọi phương thức
B. Biến có thể đổi kiểu nhưng vẫn được ép kiểu bằng compiler
C. Biến có thể bị rò rỉ nhưng vẫn được lưu ở trường static
D. Biến có thể bị ghi đè nhưng vẫn được đánh dấu final
Đáp án đúng: A

Câu 5: Tình huống nào có thể dẫn tới cảnh báo rò rỉ tài nguyên?
A. Luồng được mở nhưng có nhánh gọi hàm quá nhiều
B. Luồng được mở nhưng có nhánh xử lý chuỗi quá dài
C. Luồng được mở nhưng có nhánh phân bổ mảng quá lớn
D. Luồng được mở nhưng có nhánh thoát trước khi đóng
Đáp án đúng: D

Câu 6: SpotBugs cảnh báo đồng bộ không nhất quán thường chỉ dấu điều gì?
A. Trường dùng chung được truy cập mà tên biến không đồng nhất
B. Trường dùng chung được bảo vệ bằng khóa không nhất quán
C. Trường dùng chung được truy cập mà thứ tự import không đồng nhất
D. Trường dùng chung được truy cập mà kiểu generic không đồng nhất
Đáp án đúng: B

Câu 7: Tình huống nào có thể làm lộ trạng thái nội bộ của object?
A. Getter trả bản sao của collection trước khi gửi đi
B. Getter trả đối tượng bất biến thay cho dữ liệu gốc
C. Getter trả giá trị nguyên thủy qua biểu thức tính toán
D. Getter trả collection nội bộ cho bên ngoài chỉnh sửa
Đáp án đúng: D

Câu 8: Khi SpotBugs phát hiện nguy cơ bảo mật, nên hiểu kết quả thế nào?
A. Cần kiểm tra luồng dữ liệu và ngữ cảnh khai thác thực tế
B. Có thể khẳng định lỗ hổng đã bị khai thác trên production
C. Có thể khẳng định mọi request đều dẫn đến cùng lỗ hổng
D. Có thể bỏ qua thử nghiệm vì bộ phân tích đã xác nhận lỗi
Đáp án đúng: A

Câu 9: Với bug rank của SpotBugs, nhận định nào thường đúng?
A. Rank số nhỏ thường biểu thị cảnh báo đáng ưu tiên hơn
B. Rank số lớn thường biểu thị cảnh báo đáng ưu tiên hơn
C. Rank số nhỏ thường biểu thị cảnh báo chỉ có ở test
D. Rank số lớn thường biểu thị cảnh báo chỉ có ở CI
Đáp án đúng: A

Câu 10: Muốn lọc finding theo class và bug pattern, nên cấu hình gì?
A. Filter XML với matcher cho coverage và test case
B. Filter XML với matcher cho commit và branch Git
C. Filter XML với matcher cho JVM heap và log level
D. Filter XML với matcher cho class và bug pattern
Đáp án đúng: D

Câu 11: Vì sao một cảnh báo SpotBugs có thể là false positive?
A. Bộ phân tích luôn thực thi mọi nhánh trước khi kết luận
B. Bộ phân tích luôn chạy đồng thời với ứng dụng thực tế
C. Bộ phân tích không biết mọi bất biến chỉ đảm bảo lúc chạy
D. Bộ phân tích tự thay đổi bytecode khi gặp đường lỗi
Đáp án đúng: C

Câu 12: Áp dụng baseline cho dự án có nhiều cảnh báo cũ nhằm mục tiêu gì?
A. Xóa cảnh báo khỏi mã nguồn và tắt kiểm tra mỗi lần build
B. Chuyển cảnh báo thành lỗi runtime để test dễ phát hiện
C. Ghi nhận vi phạm tồn tại và kiểm soát cảnh báo phát sinh mới
D. Cho phép build bỏ qua mọi cảnh báo kể cả loại nghiêm trọng
Đáp án đúng: C

Câu 13: Khi nâng effort của SpotBugs, đánh đổi chính thường là gì?
A. Phân tích ít nhánh hơn nhưng dùng thêm bộ nhớ JVM
B. Phân tích nhiều file test hơn nhưng bỏ qua mã production
C. Phân tích ít bytecode hơn nhưng tạo báo cáo XML lớn hơn
D. Phân tích kỹ hơn nhưng dùng thêm thời gian và tài nguyên
Đáp án đúng: D

Câu 14: Cảnh báo đổi sau khi nâng JDK, bước kiểm tra nào hợp lý?
A. Đối chiếu báo cáo unit test và độ bao phủ của mã mới
B. Đối chiếu phiên bản SpotBugs và khả năng đọc bytecode mới
C. Đối chiếu cấu hình profiler và chu kỳ đo thời gian chạy mới
D. Đối chiếu quy tắc lint và các quy ước đặt tên mới
Đáp án đúng: B

Câu 15: Muốn suppress một finding đã xác minh tại phương thức Java, cách nào hợp lý?
A. Dùng SuppressFBWarnings cho toàn bộ bug pattern của dự án
B. Dùng Override để bỏ qua mọi finding của phương thức
C. Dùng SuppressFBWarnings đúng bug pattern có giải trình
D. Dùng Deprecated để bỏ qua mọi finding của phương thức
Đáp án đúng: C

Câu 16: Vai trò của exclude filter XML trong SpotBugs là gì?
A. Ngừng biên dịch class khớp điều kiện lọc trong Maven
B. Ẩn finding khớp điều kiện lọc khỏi kết quả được báo
C. Thay thế class khớp điều kiện lọc bằng mock runtime
D. Xóa các dependency khớp điều kiện lọc khỏi Gradle
Đáp án đúng: B

Câu 17: Vì sao nên cung cấp dependency classes khi SpotBugs phân tích?
A. Giúp phân giải kiểu và lời gọi xuyên thư viện đầy đủ hơn
B. Giúp tự tạo test case từ kiểu và lời gọi của thư viện
C. Giúp chạy benchmark các kiểu và lời gọi của thư viện
D. Giúp bỏ qua lỗi cú pháp của kiểu và lời gọi thư viện
Đáp án đúng: A

Câu 18: Với cảnh báo stream có thể không được đóng, cách sửa nào tốt?
A. Chỉ đóng stream khi đọc xong và không có ngoại lệ
B. Đảm bảo stream được đóng trên cả đường xử lý ngoại lệ
C. Để finalizer đóng stream khi đối tượng không còn được dùng
D. Chỉ đóng stream tại nhánh return thông thường của hàm
Đáp án đúng: B

Câu 19: Khi nhiều luồng cập nhật chung một trường mutable, cách nào phù hợp?
A. Bỏ từ khóa volatile và giữ nguyên mọi truy cập hiện tại
B. Bảo vệ các truy cập bằng đồng bộ nhất quán hoặc atomics
C. Đổi tên trường thành local nhưng vẫn chia sẻ tham chiếu
D. Đặt mọi thao tác trong một hàm mà không dùng khóa
Đáp án đúng: B

Câu 20: Vì sao báo cáo SpotBugs dạng XML hữu ích cho pipeline CI?
A. CI có thể tổng hợp độ bao phủ test chỉ từ báo cáo XML
B. CI có thể đo độ trễ từng hàm chỉ từ báo cáo XML
C. CI có thể đọc bug pattern, class và vị trí cảnh báo
D. CI có thể xác minh lỗ hổng thật chỉ từ báo cáo XML
Đáp án đúng: C

Câu 21: Khi nhận cảnh báo SpotBugs về hiệu năng, nên ưu tiên điều gì?
A. Xem tổng số warning và tăng ưu tiên trước khi quyết định sửa
B. Xem độ phức tạp hàm rồi tối ưu ngay trước khi quyết định sửa
C. Xem phiên bản JVM rồi bỏ qua profiling trước khi quyết định sửa
D. Xem tần suất xảy ra và chi phí trước khi quyết định sửa
Đáp án đúng: D

Câu 22: Trong Maven, goal nào dùng để kiểm tra và làm fail build khi có vi phạm?
A. spotbugs:check
B. spotbugs:spotbugs
C. spotbugs:help
D. spotbugs:gui
Đáp án đúng: A

Câu 23: Nếu SpotBugs không báo lỗi thì có chứng minh chương trình an toàn không?
A. Có, công cụ chứng minh mọi nhánh mã đã chạy đều an toàn
B. Có, công cụ chứng minh tất cả đầu vào đều được kiểm thử
C. Có, công cụ chứng minh dữ liệu production luôn đúng kiểu
D. Không, công cụ chỉ nhận ra một số mẫu lỗi trên bytecode
Đáp án đúng: D

Câu 24: Chiến lược tích hợp SpotBugs vào CI nào dễ duy trì dài hạn?
A. Thay phiên bản tùy ngày, bỏ mọi filter và tắt gate lỗi mới
B. Cố định phiên bản, có filter giải trình và gate lỗi mới
C. Cố định phiên bản, ẩn mọi bug pattern và không review
D. Thay phiên bản tùy nhánh, bỏ phân loại và chỉ chạy local
Đáp án đúng: B
