1. Error Prone thường phát hiện bug pattern Java ở giai đoạn nào?
A. Khi `javac` chạy checker lúc biên dịch mã nguồn
B. Khi JVM tải class rồi bắt đầu chạy ứng dụng
C. Khi API nhận request đầu tiên từ trình duyệt
D. Khi trình phân tích heap đọc một bản dump bộ nhớ
Đáp án đúng: A

2. Checker của Error Prone thường sử dụng thông tin nào từ trình biên dịch?
A. Chỉ log runtime thu thập từ các ca kiểm thử
B. Chỉ danh sách phiên bản JAR trong pom.xml
C. AST và thông tin kiểu được `javac` phân giải
D. Chỉ thống kê dòng code theo biểu thức regex
Đáp án đúng: C

3. So với Checkstyle, Error Prone tập trung hơn vào loại vấn đề nào?
A. Quy định khoảng trắng và vị trí ngoặc nhọn
B. Bug pattern có thể làm chương trình Java sai
C. Chuẩn thứ tự import và cách viết Javadoc
D. Bố cục thụt lề và độ dài dòng source
Đáp án đúng: B

4. Tùy chọn nào có thể kích hoạt Error Prone dưới dạng plugin của `javac`?
A. `-Xlint:all` khi không cài thư viện plugin
B. `-parameters` khi đã bật annotation processing
C. `-Xplugin:ErrorProne` dùng khi javac có plugin
D. `-g` khi cần thêm thông tin debug bytecode
Đáp án đúng: C

5. Trong Maven, cần tích hợp Error Prone vào bước nào để bắt lỗi lúc biên dịch?
A. Cấu hình Surefire để chỉ chạy checker sau unit test
B. Dùng compiler plugin để bật checker lúc compile
C. Cấu hình Javadoc để phân tích comment lúc publish
D. Cấu hình Shade để chỉ phân tích JAR sau đóng gói
Đáp án đúng: B

6. Plugin Gradle nào thường được dùng để tích hợp Error Prone với `JavaCompile`?
A. `maven-publish` xuất bản metadata của thư viện
B. `checkstyle` áp bộ quy tắc bố cục mã nguồn
C. `jacoco` ghi dữ liệu coverage của unit test
D. `net.ltgt.errorprone` tích hợp vào `JavaCompile`
Đáp án đúng: D

7. Muốn tắt checker có tên `CheckName`, nên truyền tùy chọn nào?
A. `-Xep:CheckName:OFF` vô hiệu hóa checker đó
B. `-Xep:CheckName:ERROR` nâng mức độ thành error
C. `-XepPatchChecks:CheckName` chọn bản sửa tự động
D. `-Xep:CheckName:WARN` giảm mức độ thành warning
Đáp án đúng: A

8. Muốn checker `CheckName` chỉ phát sinh cảnh báo, tùy chọn nào phù hợp?
A. `-Xep:CheckName:ERROR` để dùng mức error
B. `-Xep:CheckName:WARN` để dùng mức warning
C. `-Xep:CheckName:OFF` để tắt hoàn toàn rule
D. `-XepPatchLocation:IN_PLACE` để ghi bản vá
Đáp án đúng: B

9. Muốn vi phạm checker cụ thể làm biên dịch thất bại, chọn cấu hình nào?
A. `-Xep:CheckName:WARN` để in cảnh báo compile
B. `-Xep:CheckName:OFF` để loại checker khỏi build
C. `-XepPatchChecks:CheckName` để chọn auto-fix
D. `-Xep:CheckName:ERROR` để báo lỗi compile
Đáp án đúng: D

10. Nếu một vị trí đã được review và cần suppress checker cụ thể, nên dùng gì?
A. Tắt toàn bộ Error Prone cho mọi module trong build
B. Xóa cấu hình compiler plugin khỏi mọi môi trường
C. `@SuppressWarnings("CheckName")` ở phạm vi phù hợp
D. Đổi tên phương thức để checker bỏ qua mọi đường gọi
Đáp án đúng: C

11. Khi triage cảnh báo Error Prone, bước nào giúp quyết định suppress hợp lý?
A. Chỉ dựa vào số lượng dấu gạch chân trong IDE
B. Xóa các kiểm thử liên quan để tránh lặp cảnh báo
C. Đổi mức severity cho toàn bộ checker ngay lập tức
D. Rà luồng code và giả định của rule cảnh báo
Đáp án đúng: D

12. `@CheckReturnValue` giúp diễn đạt hợp đồng nào của phương thức?
A. Phương thức luôn gọi setter trước khi trả kết quả
B. Kết quả trả về chỉ được đọc trong cùng package
C. Phương thức phải trả về null khi gặp lỗi runtime
D. Kết quả trả về quan trọng và không nên bị bỏ qua
Đáp án đúng: D

13. Annotation `@CanIgnoreReturnValue` được dùng khi nào?
A. Cho phép bên gọi bỏ qua kết quả trả về của method
B. Phương thức phải trả về một `Future` hoàn thành
C. Phương thức bị cấm sử dụng trong mọi class test
D. Phương thức chỉ được phép gọi từ một module khác
Đáp án đúng: A

14. Checker `EqualsHashCode` thường báo vấn đề nào?
A. Một class override `equals` nhưng thiếu `hashCode`
B. Class khai báo getter trùng tên với field static
C. Class override `toString` nhưng không có constructor
D. Class implement interface nhưng thiếu annotation
Đáp án đúng: A

15. `CollectionIncompatibleType` phát hiện trường hợp nào?
A. Đọc phần tử đầu tiên từ một `List` rỗng
B. Trả về collection có kích thước vượt ngưỡng
C. Lặp qua collection mà không dùng `Iterator`
D. Gọi `contains` với kiểu phần tử không tương thích
Đáp án đúng: D

16. Checker `BoxedPrimitiveConstructor` nhắm đến kiểu code nào?
A. Dùng `new Integer(...)` tạo boxed primitive
B. So sánh hai biến primitive bằng toán tử `==`
C. Gọi `parseInt` với chuỗi có định dạng số hợp lệ
D. Dùng `int` làm tham số của phương thức overload
Đáp án đúng: A

17. Với checker `MissingOverride`, đoạn code nào thường bị cảnh báo?
A. Method khai báo `@Override` trên lớp interface
B. Override method nhưng thiếu `@Override`
C. Method static có cùng tên với trường thuộc lớp
D. Method private được gọi từ constructor của lớp
Đáp án đúng: B

18. Checker `FutureReturnValueIgnored` nhắc tới nguy cơ nào?
A. Chờ `Future.get()` quá lâu trong luồng chính
B. Lưu `Future` vào trường nhưng không có getter
C. Bỏ qua `Future` từ tác vụ chạy bất đồng bộ
D. Trả về `Future` từ phương thức Java public
Đáp án đúng: C

19. Khi xây checker Error Prone riêng, lớp cơ sở phù hợp là gì?
A. Kế thừa `AbstractCheck` để đọc token của Checkstyle
B. Kế thừa `BugChecker` và triển khai matcher phù hợp
C. Kế thừa `AbstractList` để lưu các cảnh báo build
D. Kế thừa `Thread` để quan sát từng lệnh runtime
Đáp án đúng: B

20. `MethodInvocationTreeMatcher` được gọi ở dạng nút AST nào?
A. Nút khai báo package của một file source Java
B. Nút phép gán khai báo một trường thành viên
C. Nút AST biểu diễn lời gọi phương thức Java
D. Nút khai báo module trong manifest của JAR
Đáp án đúng: C

21. Một matcher Error Prone dùng `Description` chủ yếu để làm gì?
A. Trả về danh sách test có thời gian chạy lâu nhất
B. Trả về cấu hình Maven đã được resolve đầy đủ
C. Trả về chẩn đoán rule và gợi ý sửa tùy chọn
D. Trả về bytecode của class sau quá trình optimize
Đáp án đúng: C

22. Trong Error Prone, `SuggestedFix` mô tả nội dung nào?
A. Giá trị heap ghi lại từ thời điểm ứng dụng lỗi
B. Thay đổi source có thể được áp dụng tự động
C. Danh sách các plugin Gradle cần cài thêm
D. Sơ đồ phụ thuộc Maven được xuất dưới dạng DOT
Đáp án đúng: B

23. Cặp tùy chọn nào liên quan trực tiếp tới áp dụng bản sửa tự động?
A. `-Xep` chọn warning và `-Xlint` chọn cảnh báo compiler
B. `-g` chọn debug và `-parameters` chọn metadata
C. `-source` chọn Java và `-target` chọn bytecode
D. Dùng `-XepPatchChecks` kèm `-XepPatchLocation`
Đáp án đúng: D

24. Muốn ngăn bug pattern mới lọt vào CI, cách vận hành nào phù hợp?
A. Chạy compile có Error Prone và chặn CI khi báo ERROR
B. Chỉ xem cảnh báo trên IDE ở một máy phát triển
C. Chỉ xuất danh sách dependency vào artifact CI
D. Chỉ chạy formatter trước khi phát hành production
Đáp án đúng: A
