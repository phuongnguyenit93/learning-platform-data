1. Checkstyle được dùng chủ yếu để kiểm soát vấn đề nào trong mã Java?
A. Phiên bản thư viện được Maven chọn ở runtime
B. Lỗi heap khi JVM thực thi nhiều luồng đồng thời
C. Hiệu năng API khi dịch vụ chạy dưới tải cao
D. Quy ước source Java theo bộ rule đã cấu hình
Đáp án đúng: D

2. Module gốc thường gặp trong file cấu hình XML của Checkstyle là gì?
A. `TreeWalker` chứa toàn bộ nội dung XML mà không có cha
B. `FileTabCharacter` làm nơi khai báo mọi module con
C. `Checker` chứa các module kiểm tra được cấu hình
D. `SuppressionFilter` bắt buộc làm root cho các check
Đáp án đúng: C

3. `TreeWalker` trong Checkstyle phù hợp nhất với loại check nào?
A. Các rule đi qua AST của source Java theo token
B. Các rule quyết định phiên bản bắc cầu của Maven
C. Các rule kiểm tra thay đổi file nhị phân trong Git
D. Các rule đo CPU và heap khi chương trình đang chạy
Đáp án đúng: A

4. Vì sao `FileTabCharacter` thường được đặt trực tiếp dưới `Checker`?
A. Nó là kiểm tra ở mức file, không duyệt AST token
B. Nó phải gọi `javac` để lấy thông tin runtime
C. Nó chỉ kiểm tra module descriptor đã biên dịch
D. Nó tự phát hiện và sửa toàn bộ ký tự tab trong IDE
Đáp án đúng: A

5. Cần bắt tên phương thức Java sai quy tắc regex, nên bật check nào?
A. `JavadocMethod` với thuộc tính `scope` phù hợp
B. `ImportOrder` với thuộc tính `groups` phù hợp
C. `EmptyBlock` với thuộc tính `option` phù hợp
D. `MethodName` với thuộc tính `format` phù hợp
Đáp án đúng: D

6. Để kiểm soát cách đặt tên class, interface và enum, nên chọn check nào?
A. `TypeName` và cấu hình biểu thức `format`
B. `MemberName` và cấu hình thứ tự visibility
C. `MethodLength` và cấu hình số dòng tối đa
D. `VisibilityModifier` và cấu hình quyền truy cập
Đáp án đúng: A

7. Rule nào trực tiếp phát hiện lệnh import dùng ký tự đại diện `*`?
A. `UnusedImports` để kiểm tra import không dùng
B. `CustomImportOrder` để kiểm tra nhóm import
C. `AvoidStarImport` để kiểm tra wildcard import
D. `RedundantImport` để kiểm tra import thừa
Đáp án đúng: C

8. Muốn phát hiện import không còn được dùng trong source, nên chọn gì?
A. `ImportOrder` phát hiện thứ tự import chưa đúng
B. `UnusedImports` phát hiện khai báo import không dùng
C. `AvoidStarImport` phát hiện import ký tự đại diện
D. `RedundantImport` phát hiện import trùng ngữ cảnh
Đáp án đúng: B

9. Check nào hỗ trợ đặt thứ tự nhóm import theo quy tắc riêng của nhóm?
A. `UnusedImports` với cấu hình biến không sử dụng
B. `CustomImportOrder` với cấu hình nhóm import
C. `MethodName` với cấu hình biểu thức tên method
D. `LineLength` với cấu hình chiều dài dòng mã
Đáp án đúng: B

10. Một nhóm muốn giới hạn số ký tự trên mỗi dòng source, nên dùng check nào?
A. `FileLength` với thuộc tính số dòng `max`
B. `MethodLength` với thuộc tính số dòng `max`
C. `LineLength` với thuộc tính số ký tự `max`
D. `ParameterNumber` với thuộc tính tham số `max`
Đáp án đúng: C

11. Muốn phát hiện khoảng thụt lề sai trong khối lệnh Java, rule nào thích hợp?
A. `TrailingComment` kiểm tra comment cuối dòng
B. `WhitespaceAfter` kiểm tra dấu cách sau token
C. `Indentation` kiểm tra thụt lề theo cấu trúc AST
D. `OperatorWrap` kiểm tra vị trí xuống dòng toán tử
Đáp án đúng: C

12. Để phát hiện thiếu khoảng trắng quanh toán tử như `a+b`, nên dùng check nào?
A. `WhitespaceAfter` kiểm tra cách sau dấu phẩy
B. `WhitespaceAround` kiểm tra cách quanh toán tử
C. `ParenPad` kiểm tra cách trong dấu ngoặc tròn
D. `NoWhitespaceBefore` kiểm tra cách trước dấu chấm
Đáp án đúng: B

13. Rule nào dùng để quy định vị trí dấu `{` mở một khối Java?
A. `RightCurly` kiểm tra vị trí ngoặc nhọn đóng
B. `EmptyBlock` kiểm tra thân khối lệnh rỗng
C. `NeedBraces` buộc câu lệnh dùng ngoặc nhọn
D. `LeftCurly` kiểm tra vị trí ngoặc nhọn mở
Đáp án đúng: D

14. Nếu muốn yêu cầu một phương thức phù hợp phạm vi phải có Javadoc, dùng gì?
A. `JavadocMethod` kiểm tra nội dung tag Javadoc
B. `JavadocStyle` kiểm tra định dạng phần comment
C. `MissingJavadocMethod` bắt buộc hiện diện Javadoc
D. `JavadocParagraph` kiểm tra đoạn trong comment
Đáp án đúng: C

15. `JavadocMethod` khác `MissingJavadocMethod` chủ yếu ở điểm nào?
A. Nó kiểm tra từng phương thức có khai báo public hay không
B. Nó kiểm tra phương thức có vượt giới hạn số dòng
C. Nó kiểm tra tên phương thức theo biểu thức chính quy
D. Nó kiểm tra tag Javadoc của phương thức đã có mô tả
Đáp án đúng: D

16. `CyclomaticComplexity` trong Checkstyle đo khía cạnh nào?
A. Độ phức tạp dựa trên các điểm quyết định luồng
B. Độ phức tạp từ tổng kích thước bytecode JAR
C. Độ phức tạp từ tổng số annotation của class
D. Độ phức tạp từ số package trong classpath
Đáp án đúng: A

17. `NPathComplexity` đánh giá điều gì ở một phương thức Java?
A. Số phiên bản JAR nằm trên đường phụ thuộc
B. Số đường đi thực thi phi chu trình có thể có
C. Số lần lặp thực tế của vòng lặp khi chạy
D. Số lớp con kế thừa trực tiếp từ một kiểu
Đáp án đúng: B

18. Muốn loại trừ check theo tên file và tên rule bằng XML riêng, dùng cơ chế gì?
A. `TreeWalker` tự tắt mọi rule sau lần chạy đầu
B. `SuppressionFilter` nạp các quy tắc suppress XML
C. `MethodName` tự bỏ qua lớp chứa warning đã sửa
D. `SeverityMatchFilter` tự sửa nội dung warning
Đáp án đúng: B

19. Để Checkstyle hiểu `@SuppressWarnings` cho một số rule, cần cấu hình gì?
A. `SuppressionFilter` cùng plugin JaCoCo của Maven
B. `TreeWalker` cùng trình formatter của IDE
C. `SuppressWarningsHolder` cùng `SuppressWarningsFilter`
D. `FileContentsHolder` cùng plugin compiler của Gradle
Đáp án đúng: C

20. Khi chỉ muốn suppress lỗi tại các nút AST khớp XPath, chọn cơ chế nào?
A. `SuppressionFilter` với biểu thức path của Git
B. `SeverityMatchFilter` với ngưỡng severity
C. `ImportOrder` với danh sách nhóm import
D. `SuppressionXpathFilter` với truy vấn vị trí AST
Đáp án đúng: D

21. Muốn viết rule Checkstyle riêng đọc token cú pháp Java, thường kế thừa lớp nào?
A. `AbstractCheck` để xử lý các nút `DetailAST`
B. `AbstractProcessor` để sinh annotation runtime
C. `AbstractList` để lưu mọi cảnh báo vào bộ nhớ
D. `AbstractValidator` để kiểm tra schema XML
Đáp án đúng: A

22. Trong custom AST check, phương thức `getDefaultTokens()` dùng làm gì?
A. Khai báo loại token AST mà check sẽ quan sát
B. Trả về danh sách đường dẫn source cần xóa
C. Tạo danh sách test Java cần chạy trong CI
D. Trả về toàn bộ rule bị suppress bởi annotation
Đáp án đúng: A

23. Trong Maven, goal nào của `maven-checkstyle-plugin` thường làm build thất bại khi vi phạm?
A. `checkstyle:checkstyle` chỉ xuất báo cáo HTML
B. `checkstyle:check` thực thi kiểm tra và chặn lỗi
C. `checkstyle:help` chỉ in hướng dẫn plugin
D. `checkstyle:effective-pom` chỉ xem cấu hình kế thừa
Đáp án đúng: B

24. Với plugin Checkstyle của Gradle, cách tích hợp CI hợp lý là gì?
A. Chạy `gradle clean` để kiểm tra mọi quy ước mã
B. Chạy `gradle dependencies` để phân tích AST Java
C. Chạy `gradle assemble` để tự sửa mọi lỗi style
D. Chạy `gradle check` để thực thi các task Checkstyle
Đáp án đúng: D
