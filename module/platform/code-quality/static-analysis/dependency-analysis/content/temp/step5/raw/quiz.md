1. Cần xem phụ thuộc lớp từ những file `.class` đã biên dịch, nên dùng công cụ nào?
A. Chạy `javadoc` trên thư mục chứa Java source
B. Chạy `jar --list` trên JAR đã biên dịch
C. Chạy `javap -c` trên một lớp riêng lẻ
D. Dùng `jdeps` với JAR hoặc thư mục bytecode
Đáp án đúng: D

2. Tùy chọn nào của `jdeps` giúp theo dõi cả phụ thuộc bắc cầu?
A. Dùng `--summary` để chỉ in quan hệ tổng quan
B. Bật `--recursive` để đi qua phụ thuộc bắc cầu
C. Dùng `--api-only` để chỉ lấy public API
D. Dùng `--verbose:class` để tăng chi tiết mỗi lớp
Đáp án đúng: B

3. Muốn xuất dữ liệu phụ thuộc dưới dạng đồ thị DOT bằng `jdeps`, chọn cách nào?
A. Dùng `--list-deps` và đường dẫn đến ảnh
B. Dùng `--print-module-deps` và tệp kết quả
C. Dùng `--dot-output` xuất ra đồ thị dạng DOT
D. Dùng `--generate-module-info` và tên đồ thị
Đáp án đúng: C

4. Cờ nào của `jdeps` hỗ trợ phát hiện mã gọi API nội bộ của JDK?
A. Dùng `--check` để rà soát API nội bộ
B. Dùng `--jdk-internals` để xem API nội bộ
C. Dùng `--list-deps` để rà soát API nội bộ
D. Dùng `--api-only` để rà soát API nội bộ
Đáp án đúng: B

5. Kết quả chính của `jdeps --print-module-deps` là gì?
A. Danh sách thư viện Maven bị trùng group và artifact
B. Danh sách class Java chưa được trình biên dịch dùng
C. Các module Java cần trong cấu hình runtime ứng dụng
D. Danh sách package Java đang tạo chu kỳ phụ thuộc
Đáp án đúng: C

6. Phụ thuộc nào dễ bị `jdeps` bỏ sót khi phân tích bytecode tĩnh?
A. Lớp được tham chiếu trực tiếp trong chữ ký phương thức
B. Lớp là kiểu trường được khai báo trong bytecode
C. Lớp được gọi trực tiếp bằng lệnh `new` trong bytecode
D. Lớp chỉ nạp từ chuỗi tên qua `Class.forName`
Đáp án đúng: D

7. Trong JPMS, câu lệnh `exports` của `module-info.java` có vai trò gì?
A. Công khai public type của package cho module khác
B. Thêm module bên ngoài vào đường dẫn khi biên dịch
C. Cho phép phản chiếu sâu vào mọi thành phần của package
D. Kích hoạt tự động tải mọi service provider lúc chạy
Đáp án đúng: A

8. Trong JPMS, khai báo `requires` diễn tả quan hệ nào?
A. Module hiện tại cần đọc module được chỉ định
B. Module hiện tại mở package cho phản chiếu sâu
C. Module hiện tại cung cấp triển khai cho service
D. Module hiện tại công khai mọi package đang sở hữu
Đáp án đúng: A

9. Lệnh Maven nào hiển thị cây phụ thuộc kể cả các nhánh bắc cầu?
A. `mvn dependency:analyze` để tìm khai báo thừa
B. Dùng `mvn dependency:tree` để xem nhánh bắc cầu
C. `mvn help:effective-pom` để xem POM sau kế thừa
D. `mvn versions:display-dependency-updates` để xem nâng cấp
Đáp án đúng: B

10. Khi hai phiên bản Maven xung đột ở hai độ sâu khác nhau, quy tắc mặc định là gì?
A. Ưu tiên phiên bản có số phiên bản cao hơn
B. Ưu tiên phiên bản có thời điểm phát hành mới hơn
C. Ưu tiên phiên bản ở nhánh gần dự án hơn
D. Ưu tiên phiên bản có phạm vi `runtime` rõ hơn
Đáp án đúng: C

11. Nếu hai nhánh Maven đòi phiên bản khác nhau ở cùng độ sâu, yếu tố nào thường quyết định?
A. Nhánh phụ thuộc được khai báo trước trong POM
B. Thời điểm kho Maven cập nhật metadata
C. Số lượng class được sử dụng từ mỗi artifact
D. Thứ tự chữ cái của tên artifact trong POM
Đáp án đúng: A

12. Maven Enforcer `dependencyConvergence` kiểm tra vấn đề gì?
A. Nhiều plugin Maven cùng khai báo một giai đoạn build
B. Nhiều class có tên giống nhau trong một package Java
C. Nhiều module có cùng tên sau khi tạo module descriptor
D. Các nhánh yêu cầu nhiều phiên bản của cùng artifact
Đáp án đúng: D

13. Trong Gradle, `dependencies --configuration runtimeClasspath` dùng để làm gì?
A. Hiển thị các class cần được load bằng reflection
B. Hiển thị cây phụ thuộc của `runtimeClasspath`
C. Hiển thị biểu đồ gọi hàm trong mỗi file Java
D. Hiển thị thống kê cảnh báo của trình phân tích AST
Đáp án đúng: B

14. Khi Gradle chọn một phiên bản thư viện bất ngờ, lệnh nào giúp tìm nguyên nhân?
A. `dependencyInsight` truy ra nhánh yêu cầu và lý do chọn
B. `dependencies` chỉ đưa ra danh sách task có thể chạy
C. `properties` mô tả các lệnh gọi constructor
D. `test` liệt kê các đường dẫn phụ thuộc giữa JAR
Đáp án đúng: A

15. Với xung đột hai phiên bản của cùng module, Gradle mặc định thường xử lý ra sao?
A. Chọn phiên bản khai báo đầu tiên ở file build
B. Chọn phiên bản có nhánh phụ thuộc ngắn nhất
C. Chọn phiên bản cao hơn khi không có ghi đè
D. Chọn phiên bản được tải vào cache sớm nhất
Đáp án đúng: C

16. Dependency locking của Gradle giải quyết mục tiêu nào?
A. Chốt phiên bản đã resolve để build có thể tái lập
B. Bỏ qua phụ thuộc bắc cầu để rút ngắn thời gian build
C. Chuyển phụ thuộc runtime sang phụ thuộc compile
D. Tự phát hiện mọi chu kỳ giữa các lớp trong ứng dụng
Đáp án đúng: A

17. Với plugin `java-library` của Gradle, khác biệt chính giữa `api` và `implementation` là gì?
A. `api` chỉ cho phép phụ thuộc xuất hiện ở runtime
B. `implementation` buộc consumer khai báo lại mọi class
C. `implementation` tự loại các phụ thuộc bắc cầu khỏi JAR
D. `api` đưa thư viện vào compile classpath consumer
Đáp án đúng: D

18. Khai báo `runtimeOnly` trong Gradle ảnh hưởng classpath thế nào?
A. Thêm thư viện lúc biên dịch nhưng không thêm lúc chạy
B. Thêm thư viện vào cả compile và annotation processor
C. Thêm thư viện vào source set test mà bỏ runtime
D. Có lúc chạy nhưng không có trên compile classpath
Đáp án đúng: D

19. Trong đồ thị phụ thuộc, một thành phần liên thông mạnh có nhiều đỉnh cho biết gì?
A. Các đỉnh trong nhóm đều có cùng phiên bản thư viện
B. Các đỉnh trong nhóm chỉ được gọi từ module gốc
C. Nhóm đỉnh có đường đi qua lại và chứa chu kỳ
D. Các đỉnh trong nhóm đều không có đường đi đến nhau
Đáp án đúng: C

20. Quy tắc `slices().should().beFreeOfCycles()` của ArchUnit nhằm tìm gì?
A. Thư viện Gradle có phiên bản cao hơn mức cho phép
B. Package Java chứa class không được dùng trong build
C. Phương thức Java có số tham số vượt ngưỡng đặt ra
D. Tìm chu kỳ giữa các lát cắt package đã định nghĩa
Đáp án đúng: D

21. Muốn cấm class tầng domain phụ thuộc tầng web bằng ArchUnit, cần loại kiểm tra nào?
A. Quy tắc `classes` kết hợp điều kiện `haveSimpleNameEndingWith`
B. Dùng `noClasses` với `dependOnClassesThat` để cấm quan hệ
C. Quy tắc `methods` kết hợp điều kiện `bePublic`
D. Quy tắc `fields` kết hợp điều kiện `beStatic`
Đáp án đúng: B

22. Trong bài test ArchUnit, `@AnalyzeClasses(packages=...)` chỉ định điều gì?
A. Các package được xuất bản thành module Java mới
B. Các package phải có thư viện khớp phiên bản Maven
C. Chọn các package được quét làm nguồn lớp cho rule
D. Các package được loại khỏi classpath lúc test chạy
Đáp án đúng: C

23. Nếu cạnh A → B nghĩa là A phụ thuộc B, trước khi sửa public API của B nên xem cạnh nào?
A. Các cạnh đi vào thư viện từ module đang sử dụng
B. Các cạnh đi ra thư viện để nhận diện thư viện được dùng
C. Các cạnh giữa các test để nhận diện thời gian chạy
D. Các cạnh không có trọng số để nhận diện nhóm thư viện
Đáp án đúng: A

24. Muốn ngăn tái xuất hiện vi phạm ranh giới kiến trúc trong CI, nên làm gì?
A. Chạy `jdeps` rồi chỉ lưu bản xuất DOT vào artifact
B. Chạy test ArchUnit và fail build khi có vi phạm
C. Chạy `dependency:tree` rồi chỉ gửi báo cáo định kỳ
D. Chạy formatter rồi chỉ sửa bố cục source Java
Đáp án đúng: B
