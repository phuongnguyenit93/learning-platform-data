Câu 1. Tính năng cú pháp nào trở thành tính năng chính thức trong Java 14 và vẫn dùng trên Java hiện đại?
A. Switch expression chính thức hỗ trợ arrow và trả giá trị.
B. Primitive pattern trong instanceof với value type mới.
C. String template nhúng biểu thức bằng cú pháp `STR`.
D. Record pattern trong switch với phép bóc tách nested record.
Đáp án đúng: A

Câu 2. Với `int n = switch (day) { case MONDAY -> 1; default -> 0; };`, ý nghĩa chính của `switch` là gì?
A. Biến ngày được chọn thành chuỗi để in ra màn hình.
B. Tạo một enum mới từ ngày được đưa vào switch.
C. Chạy các nhánh rồi bỏ đi giá trị của từng nhánh.
D. Tính ra một giá trị int để gán cho biến n.
Đáp án đúng: D

Câu 3. Trong switch expression, cú pháp nào ghép hai nhãn enum vào cùng một arrow rule?
A. `case MONDAY, FRIDAY -> 6;` là cú pháp nhiều nhãn.
B. `case MONDAY; FRIDAY -> 6;` ghép bằng dấu chấm phẩy.
C. `case MONDAY & FRIDAY -> 6;` nối bằng toán tử AND.
D. `case MONDAY || FRIDAY -> 6;` nối các nhãn bằng OR.
Đáp án đúng: A

Câu 4. Điều nào đúng về arrow rule `case A -> expr;` trong switch expression?
A. Chạy tiếp case sau trừ khi expr kết thúc bằng break.
B. Đánh giá các case tiếp theo rồi gộp mọi kết quả.
C. Không tự chạy tiếp phần xử lý của case phía sau.
D. Chỉ hoạt động khi case cuối cùng là nhánh default.
Đáp án đúng: C

Câu 5. Khi viết switch expression theo nhãn colon và nhóm statement, từ khóa nào trả kết quả nhánh?
A. Dùng `yield result;` để trả giá trị từ switch expression.
B. Dùng `continue result;` để chuyển kết quả sang nhánh kế.
C. Dùng `return result;` để trả về từ switch expression.
D. Dùng `break result;` để trả giá trị giống cú pháp Java 12.
Đáp án đúng: A

Câu 6. Trong `case X -> { ... }` của switch expression, cách trả giá trị hợp lệ là gì?
A. Đặt `continue value;` trong khối lệnh của arrow rule.
B. Đặt `case value;` trong khối lệnh của arrow rule.
C. Đặt `break value;` trong khối lệnh của arrow rule.
D. Đặt `yield value;` trong khối lệnh của arrow rule.
Đáp án đúng: D

Câu 7. Phân biệt `yield` và `return` khi dùng trong một switch expression nằm trong method như thế nào?
A. `yield` trả giá trị switch; `return` thoát khỏi method.
B. Hai từ khóa đều đưa điều khiển về case kế tiếp.
C. `yield` thoát method; `return` chỉ thoát switch.
D. Hai từ khóa đều kết thúc method và trả cùng kết quả.
Đáp án đúng: A

Câu 8. Vì sao switch expression trên một biến kiểu String thường cần nhánh default?
A. Switch expression tự chuyển String lạ thành giá trị đầu.
B. Vì compiler cần xử lý cả các String chưa khớp case nào.
C. Compiler coi String là enum với tập giá trị hữu hạn.
D. Switch expression trả null khi không có case nào phù hợp.
Đáp án đúng: B

Câu 9. Với switch expression trên enum và đã liệt kê đầy đủ các enum constant, nhận định nào đúng?
A. Cần thêm case cho mỗi String trùng tên enum constant.
B. Phải có default vì enum không dùng được làm switch selector.
C. Có thể bỏ default khi đã liệt kê đủ các enum constant.
D. Cần thêm case null để biểu thức được xem là exhaustive.
Đáp án đúng: C

Câu 10. Trong switch expression, nhánh nào hợp lệ khi tình huống cần báo lỗi thay vì trả giá trị?
A. `case INVALID -> break new IllegalArgumentException();`.
B. `case INVALID -> throw new IllegalArgumentException();`.
C. `case INVALID -> return new IllegalArgumentException();`.
D. `case INVALID -> yield new IllegalArgumentException();`.
Đáp án đúng: B

Câu 11. Muốn biên dịch trên JDK mới nhưng ràng buộc ngôn ngữ và API chuẩn ở Java 14, lựa chọn nào phù hợp?
A. `java --release 14 App.java` tạo class file theo chuẩn Java 14.
B. `javac --release 14 App.java` kiểm tra source, API và bytecode đích.
C. `javac --target 14 App.java` giới hạn cả cú pháp và API JDK.
D. `javac --source 14 App.java` giới hạn cả API của JDK hiện tại.
Đáp án đúng: B

Câu 12. Helpful NullPointerException được bổ sung ở Java 14 giúp điều tra lỗi theo cách nào?
A. JVM thay null bằng object mặc định để method chạy tiếp.
B. Compiler chuyển mọi lần dereference null thành Optional.
C. Thông báo có thể nêu biểu thức con gây dereference null.
D. Runtime tự khôi phục object bị null rồi chạy lại method.
Đáp án đúng: C

Câu 13. Nếu `order.customer().getName()` gây NPE vì `customer()` trả null, helpful NPE hỗ trợ gì?
A. Giúp nhận diện lời gọi `customer()` có kết quả null.
B. Tự đưa đối tượng Customer mặc định vào Order hiện tại.
C. Xác nhận phương thức `getName()` ném lỗi vì giá trị trả về.
D. Tự thêm kiểm tra null vào mọi caller của `customer()`.
Đáp án đúng: A

Câu 14. Helpful NPE có thay đổi loại ngoại lệ khi JVM dereference một tham chiếu null không?
A. Có; ngoại lệ được đổi thành `ClassCastException`.
B. Có; ngoại lệ được đổi thành `IllegalStateException`.
C. Không; JVM vẫn ném `NullPointerException` như trước.
D. Có; ngoại lệ được đổi thành `NoSuchElementException`.
Đáp án đúng: C

Câu 15. Để tạo thông báo rõ ràng khi tham số bắt buộc không được null, cách nào thích hợp?
A. Dùng `Optional.ofNullable(value)` rồi bỏ qua kết quả.
B. Dùng `String.valueOf(value)` để phát ra NPE có ngữ cảnh.
C. Dùng `Objects.toString(value)` để phát hiện lỗi null.
D. Dùng `Objects.requireNonNull(value, "value required")`.
Đáp án đúng: D

Câu 16. Trên HotSpot hiện đại, tùy chọn nào có thể tắt nội dung chẩn đoán chi tiết của helpful NPE?
A. `-XX:-UseCompressedOops` khi khởi chạy Java process.
B. `-XX:-OmitStackTraceInFastThrow` khi khởi chạy.
C. `-XX:-UseStringDeduplication` khi khởi chạy.
D. `-XX:-ShowCodeDetailsInExceptionMessages` khi khởi chạy.
Đáp án đúng: D

Câu 17. Khi trực tiếp `throw new NullPointerException("bad input")`, nên hiểu thế nào về helpful NPE?
A. JVM thay thế message bằng tên biến vừa bị truy cập null.
B. JVM tự tìm dòng cuối dereference null trong method.
C. NPE ném tường minh không có phân tích dereference từ JVM.
D. Exception được đổi thành lỗi kiểm tra kiểu lúc compile.
Đáp án đúng: C

Câu 18. Khả năng mới nào liên quan Java Flight Recorder (JFR) xuất hiện trong Java 14?
A. JFR thay thế hoàn toàn Java Management Extensions ở runtime.
B. JFR Event Streaming chuyển sự kiện tới consumer ngay khi ghi.
C. JFR bắt đầu yêu cầu chuyển toàn bộ ứng dụng sang native image.
D. JFR lần đầu xuất hiện và chỉ chạy được trên máy Windows.
Đáp án đúng: B

Câu 19. API nào của JDK hiện đại thích hợp để đăng ký nhận luồng sự kiện JFR khi ứng dụng đang chạy?
A. `java.lang.management.ThreadInfo` để tạo stream sự kiện.
B. `jdk.jfr.consumer.RecordingFile` để stream mạng theo URL.
C. `java.util.logging.LogRecord` để mở một phiên JFR mới.
D. `jdk.jfr.consumer.RecordingStream` để nghe sự kiện trực tiếp.
Đáp án đúng: D

Câu 20. Trong ứng dụng JPMS cần trực tiếp sử dụng các JFR API, module JDK nào cung cấp chúng?
A. Module `jdk.management` cung cấp RecordingStream API.
B. Module `java.logging` cung cấp toàn bộ API JFR.
C. Module `jdk.jfr` cung cấp API JFR recorder và consumer.
D. Module `java.instrument` cung cấp RecordingFile API.
Đáp án đúng: C

Câu 21. Với đối tượng `RecordingStream stream`, lời gọi nào đăng ký callback xử lý event theo tên?
A. `stream.onThread("jdk.CPULoad", event -> use(event));`.
B. `stream.onEvent("jdk.CPULoad", event -> use(event));`.
C. `stream.onFile("jdk.CPULoad", event -> use(event));`.
D. `stream.onMethod("jdk.CPULoad", event -> use(event));`.
Đáp án đúng: B

Câu 22. Khi muốn bật thu thập sự kiện CPU load trong RecordingStream, API nào phù hợp?
A. Chọn `stream.enable("jdk.CPULoad")` trước khi bắt đầu.
B. Chọn `stream.disable("jdk.CPULoad")` trước khi bắt đầu.
C. Chọn `stream.clear("jdk.CPULoad")` trước khi bắt đầu.
D. Chọn `stream.remove("jdk.CPULoad")` trước khi bắt đầu.
Đáp án đúng: A

Câu 23. Phân biệt `RecordingStream.start()` và `startAsync()` trong JFR streaming như thế nào?
A. `start()` ghi file JAR; `startAsync()` ghi bytecode của JFR.
B. `start()` chỉ đọc file JFR cũ; `startAsync()` chỉ kiểm tra file.
C. `start()` tạo JVM khác; `startAsync()` dùng lại JVM hiện tại.
D. `start()` chặn caller; `startAsync()` chạy bất đồng bộ trên thread khác.
Đáp án đúng: D

Câu 24. Sau khi không còn cần nhận sự kiện JFR qua RecordingStream, thao tác nào phù hợp?
A. Gọi `System.exit(0)` vì stream gắn chặt với tiến trình.
B. Đóng stream để dừng nhận event và giải phóng resource.
C. Xóa file JDK trên đĩa để buộc JVM dừng ghi sự kiện.
D. Đổi class loader của stream để cắt mọi callback đã đăng ký.
Đáp án đúng: B

Câu 25. Để phân tích bản ghi `.jfr` đã lưu trên đĩa thay vì theo dõi trực tiếp, nên dùng lớp nào?
A. `jdk.jfr.consumer.RecordingStream` để tự parse text log.
B. `java.nio.file.WatchService` để giải mã các event.
C. `jdk.jfr.Event` để thay thế nội dung binary trong file.
D. `jdk.jfr.consumer.RecordingFile` dùng đọc event từ file.
Đáp án đúng: D

Câu 26. Trên HotSpot, thao tác `jcmd <pid> JFR.start` chủ yếu làm gì?
A. Thay đổi classpath của JVM đích để nạp plugin mới.
B. Khởi tạo trình biên dịch javac bên trong JVM đích.
C. Khởi động một phiên JFR recording trong JVM đích được chọn.
D. Giải nén mọi file `.jfr` từ thư mục của JVM đích.
Đáp án đúng: C

Câu 27. Khi cần lấy dữ liệu JFR đang ghi ra tệp để phân tích, lệnh `jcmd` nào phù hợp?
A. `jcmd <pid> GC.heap_dump filename=app.jfr` để ghi event.
B. `jcmd <pid> VM.version filename=app.jfr` để trích event.
C. `jcmd <pid> JFR.dump filename=app.jfr` để xuất bản ghi.
D. `jcmd <pid> JFR.stop filename=app.jfr` để bật stream mới.
Đáp án đúng: C

Câu 28. Điểm khác nhau quan trọng giữa JFR Event Streaming và chỉ đọc bản ghi đã xuất ra file là gì?
A. Streaming đưa event tới consumer trong lúc sự kiện vừa được ghi.
B. Streaming tắt mọi chi phí thu thập sự kiện trong ứng dụng.
C. Streaming tự gửi mọi event tới server bên ngoài không cần xử lý.
D. Streaming buộc ứng dụng dừng để có snapshot nhất quán.
Đáp án đúng: A

Câu 29. Record từng là tính năng preview ở Java 14; trạng thái phù hợp với Java hiện đại là gì?
A. Record bị loại bỏ và thay bằng class thông thường ở Java 17.
B. Record thành tính năng chính thức từ Java 16.
C. Record vẫn cần `--enable-preview` trên JDK 21.
D. Record được thay thế bằng enum cho mọi kiểu dữ liệu.
Đáp án đúng: B

Câu 30. Pattern matching cho `instanceof` từng ở preview Java 14; khi nào trở thành tính năng chính thức?
A. Java 16 chuẩn hóa kiểu `obj instanceof String s`.
B. Java 14 chuẩn hóa record pattern trong instanceof.
C. Java 18 loại bỏ tên biến pattern khỏi instanceof.
D. Java 21 mới giới thiệu type pattern trong instanceof.
Đáp án đúng: A

Câu 31. Text block từng ở preview trong Java 14; mốc nào phù hợp với tính năng sử dụng hiện nay?
A. Java 16 loại bỏ text block để thay bằng String.format.
B. Java 21 yêu cầu bật preview để dùng text block.
C. Java 14 chuẩn hóa string interpolation theo cú pháp STR.
D. Java 15 chuẩn hóa text block với dấu `"""`.
Đáp án đúng: D

Câu 32. Khi nâng cấp mã từng dùng API foreign-memory incubator của Java 14, hướng đi nào phù hợp trên JDK 22 trở lên?
A. Chuyển mã sang `java.nio.channels.Selector` cho native memory.
B. Dùng API `java.lang.foreign` chính thức trên JDK 22 trở lên.
C. Chuyển mã sang `sun.misc.Unsafe` để được hỗ trợ dài hạn.
D. Giữ API `jdk.incubator.foreign` vì namespace đó là chuẩn.
Đáp án đúng: B
