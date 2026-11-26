Câu 1. Tính năng nào được chuẩn hóa ở Java 22 và tiếp tục dùng để tương tác với thư viện native?
A. API incubator `jdk.incubator.foreign` giữ nguyên dạng chuẩn.
B. FFM API `java.lang.foreign` đã là API chuẩn ở Java 22.
C. JNI bị loại bỏ để thay hoàn toàn bằng API NIO.
D. Native code phải được biên dịch vào Java class file.
Đáp án đúng: B

Câu 2. Khi nâng cấp mã dùng FFM incubator cũ lên Java 22+, namespace nào phù hợp?
A. Chuyển sang `java.nio.channels` cho mọi native symbol.
B. Dùng các kiểu API ổn định thuộc `java.lang.foreign`.
C. Chuyển sang `sun.misc.Unsafe` để tương thích module.
D. Giữ `jdk.incubator.foreign` để không đổi mã import.
Đáp án đúng: B

Câu 3. Với `Arena.ofConfined()` và segment cấp phát từ arena, điều gì xảy ra sau khi arena được đóng?
A. Segment vẫn được phép đọc cho tới khi JVM chạy GC.
B. Segment tự đổi thành heap array giữ lại toàn bộ dữ liệu.
C. Segment được JVM tự chuyển sang một arena khác.
D. Segment không còn truy cập được vì lifetime đã hết.
Đáp án đúng: D

Câu 4. Khi `Arena.ofConfined()` cấp phát native memory, thao tác nào truy cập giá trị int tại offset 0?
A. `segment.get(ValueLayout.JAVA_BYTE, 0)` đọc kiểu int.
B. `segment.get(ValueLayout.JAVA_INT, 0)` đọc kiểu int.
C. `segment.get(ValueLayout.JAVA_LONG, 0)` đọc kiểu int.
D. `segment.get(ValueLayout.JAVA_FLOAT, 0)` đọc kiểu int.
Đáp án đúng: B

Câu 5. Nếu segment có kích thước bốn byte, đọc `ValueLayout.JAVA_LONG` tại offset 0 gây gì?
A. Tự cấp phát thêm bốn byte trước khi thực hiện đọc.
B. Trả về số 0 vì long lớn hơn segment đã cấp phát.
C. Báo lỗi bounds khi đọc tám byte từ vùng bốn byte.
D. Đọc được bốn byte rồi tự mở rộng thành số long.
Đáp án đúng: C

Câu 6. Nếu thread khác truy cập segment được cấp từ `Arena.ofConfined()`, điều gì phù hợp?
A. Truy cập được nếu không có writer nào chạy đồng thời.
B. Truy cập được nếu thread khác dùng cùng Java module.
C. Truy cập tự chuyển segment thành shared khi có contention.
D. Truy cập bị chặn do ràng buộc owner thread của arena.
Đáp án đúng: D

Câu 7. Khi cần nhiều thread cùng truy cập một vùng native memory hợp lệ, cách nào phù hợp?
A. Dùng `Arena.ofConfined()` và bỏ qua kiểm tra thread.
B. Dùng `Arena.ofAuto()` vì nó đồng bộ mọi thao tác.
C. Dùng `Arena.ofShared()` rồi tự đồng bộ khi ghi.
D. Dùng `Arena.global()` để tự khóa từng địa chỉ native.
Đáp án đúng: C

Câu 8. `MemorySegment.ofArray(bytes)` với `bytes` kiểu `byte[]` tạo loại segment nào?
A. Segment backed by heap array của chương trình Java.
B. Segment trỏ tới file memory-mapped trên hệ điều hành.
C. Segment trỏ tới metadata của class byte[] trong JDK.
D. Segment native mới và sao chép toàn bộ array sang RAM.
Đáp án đúng: A

Câu 9. Khi mô tả cấu trúc dữ liệu native gồm nhiều field, API FFM nào hữu ích?
A. `Linker.nativeLinker()` tự phát sinh mọi field offset.
B. `MemorySegment.ofArray(...)` suy ra C struct từ source.
C. `MemoryLayout.structLayout(...)` mô tả các field.
D. `FunctionDescriptor.ofVoid(...)` cấp phát vùng struct.
Đáp án đúng: C

Câu 10. Trong FFM, thành phần nào cung cấp method handle gọi hàm native từ Java?
A. `MemorySegment.ofArray(...)` để thực thi native function.
B. `Linker.nativeLinker().upcallStub(...)` để gọi hàm C từ Java.
C. `MethodHandles.lookup().findVirtual(...)` để giải mã C symbol.
D. `Linker.nativeLinker().downcallHandle(...)` cho native call.
Đáp án đúng: D

Câu 11. Muốn tìm địa chỉ một symbol trong thư viện native để tạo downcall, API nào phù hợp?
A. `SymbolLookup` tra cứu vị trí native symbol theo tên.
B. `ValueLayout` ánh xạ tên hàm C sang method Java.
C. `Arena` tự tìm tên hàm trong từng native library.
D. `MemoryLayout` phân giải mọi symbol từ classpath.
Đáp án đúng: A

Câu 12. `FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_LONG)` mô tả chữ ký native nào?
A. Hàm trả `int` và nhận một tham số `long`.
B. Hàm trả `int` nhưng không nhận tham số nào.
C. Hàm trả `long` và nhận một tham số `int`.
D. Hàm không trả giá trị và nhận tham số `int`.
Đáp án đúng: A

Câu 13. Để native code gọi ngược vào Java MethodHandle qua FFM, cơ chế nào phù hợp?
A. Dùng `MemoryLayout.structLayout(...)` để gọi callback.
B. Dùng `Linker.nativeLinker().downcallHandle(...)` gọi Java.
C. Dùng `Linker.nativeLinker().upcallStub(...)` tạo callback.
D. Dùng `SymbolLookup.find(...)` để tạo Java callback.
Đáp án đúng: C

Câu 14. Trong `try (Arena arena = Arena.ofConfined()) { ... }`, lợi ích chính của try-with-resources là gì?
A. Cho phép mọi thread truy cập segment ngay khi khối kết thúc.
B. Arena tự đóng sau khối try và giải phóng tài nguyên.
C. Giữ arena tồn tại tới lúc garbage collector dọn heap.
D. Tự chuyển dữ liệu trong arena thành Java String lúc đóng.
Đáp án đúng: B

Câu 15. Trong Java 22+, câu lệnh `var _ = compute();` có ý nghĩa nào?
A. Biến `_` trở thành static field của enclosing class.
B. Compiler bỏ lời gọi compute vì kết quả không được dùng.
C. Vẫn gọi `compute()`, nhưng không đặt tên cho kết quả.
D. Biến `_` có thể được tham chiếu trong các câu lệnh sau.
Đáp án đúng: C

Câu 16. Sau khai báo `var _ = load();`, câu `System.out.println(_)` có hợp lệ không?
A. Không, dấu `_` không thể được dùng để đọc kết quả.
B. Không, vì `var` chỉ dùng trong parameter của lambda.
C. Có, vì println tự suy ra giá trị unnamed variable gần nhất.
D. Có, dấu `_` là identifier bình thường từ Java 22.
Đáp án đúng: A

Câu 17. Trong Java 22+, cách bắt IOException khi không cần dùng exception object là gì?
A. `catch (IOException _) { handle(); }` với biến không tên.
B. `catch (_ IOException) { handle(); }` với biến không tên.
C. `catch (IOException var) { handle(); }` với biến không tên.
D. `catch (IOException ?) { handle(); }` với biến không tên.
Đáp án đúng: A

Câu 18. Với `BiFunction<Integer, String, String> f`, lambda nào bỏ qua đối số đầu và trả đối số thứ hai?
A. `(text, _) -> text` trả về đối số thứ hai.
B. `(unused, text) -> unused` bỏ qua đối số đầu.
C. `(var _, var text) -> _` trả lại đối số không tên.
D. `(_, text) -> text` bỏ qua đối số đầu tiên.
Đáp án đúng: D

Câu 19. Với danh sách `items`, vòng lặp nào duyệt đủ phần tử mà không dùng biến mỗi lượt?
A. `for (Object ? : items) { count++; }` có biến bỏ qua.
B. `for (var : items) { count++; }` có biến kiểu suy luận.
C. `for (_ : items) { count++; }` là enhanced-for hợp lệ.
D. `for (var _ : items) { count++; }` là hợp lệ.
Đáp án đúng: D

Câu 20. Với `record Point(int x, int y) {}`, case nào lấy x nhưng không dùng y trong record pattern?
A. `case Point(int x, ?) -> x;` dùng wildcard pattern.
B. `case Point(int x, ...) -> x;` bỏ qua phần còn lại.
C. `case Point(int x, _) -> x;` dùng unnamed pattern.
D. `case Point(int x, y) -> x;` tự khai báo biến y.
Đáp án đúng: C

Câu 21. Với `Object value`, cú pháp nào kiểm tra String mà không tạo tên biến để sử dụng?
A. `value instanceof String ?` dùng wildcard type pattern.
B. `value instanceof String ...` dùng varargs pattern.
C. `value instanceof String _` kiểm tra kiểu mà không bind tên.
D. `value instanceof _ String` dùng unnamed type.
Đáp án đúng: C

Câu 22. Với `record Pair(Point left, Point right) {}`, ví dụ nào bỏ qua trọn vẹn thành phần right?
A. `case Pair(Point(var x, var y), ...) -> x + y;`.
B. `case Pair(Point(var x, var y), _) -> x + y;`.
C. `case Pair(Point(var x, var y), ?) -> x + y;`.
D. `case Pair(Point[var x, var y], _) -> x + y;`.
Đáp án đúng: B

Câu 23. Java 22 cải tiến source-file launcher theo hướng nào vẫn dùng được ngày nay?
A. `java Main.java` bắt buộc có file JAR đã build sẵn.
B. `java Main.java` có thể tìm thêm source cùng thư mục.
C. `java Main.java` tạo module-info cho tất cả package.
D. `java Main.java` tự tải dependency Maven từ repository.
Đáp án đúng: B

Câu 24. Với `Main.java` gọi class `Helper` trong `Helper.java` cùng thư mục, cách chạy tiện lợi trên Java 22+ là gì?
A. Gọi `java Helper.java Main.java` để ghép hai main method.
B. Gọi `java -jar Main.java` vì source luôn là executable JAR.
C. Gọi `java Main.java` để launcher biên dịch source khi cần.
D. Gọi `jlink Main.java Helper.java` để chạy trực tiếp source.
Đáp án đúng: C

Câu 25. Với chế độ chạy source Java bằng `java Main.java`, điều nào đúng về kết quả biên dịch tạm?
A. Biên dịch trong bộ nhớ, không ghi .class như javac.
B. Launcher bắt buộc ghi các .class vào cùng thư mục source.
C. Launcher thay đổi các file .java thành .class trên đĩa.
D. Launcher đóng gói các class thành JAR trước khi chạy.
Đáp án đúng: A

Câu 26. Stream Gatherers được giới thiệu dạng preview ở Java 22; trên JDK 24+ API nào đã thành chính thức?
A. `Stream.reduce(Gatherer)` trả về luồng kết quả sau xử lý.
B. `Stream.flatMap(Gatherer)` nhận trực tiếp object Gatherer.
C. `Stream.collect(Gatherer)` là cách duy nhất xử lý từng phần tử.
D. `Stream.gather(Gatherer)` dùng các gatherer đã được chuẩn hóa.
Đáp án đúng: D

Câu 27. Trên JDK 24+, `Gatherers.windowFixed(3)` được dùng vào mục đích gì?
A. Chỉ giữ ba phần tử đầu tiên rồi đóng toàn bộ stream.
B. `Gatherers.windowFixed(3)` tạo cửa sổ tối đa ba phần tử.
C. Đảm bảo mọi window có đúng ba phần tử, kể cả cuối.
D. Chia dữ liệu thành ba stream song song độc lập.
Đáp án đúng: B

Câu 28. Với Gatherers API chính thức, `Gatherers.mapConcurrent(4, mapper)` thể hiện gì?
A. Chia stream thành bốn phần tử output cho mỗi input.
B. `mapConcurrent(4, mapper)` giới hạn bốn tác vụ đồng thời.
C. Ánh xạ chính xác bốn phần tử rồi kết thúc stream.
D. Ánh xạ trên bốn CPU core vật lý theo thứ tự cố định.
Đáp án đúng: B

Câu 29. Class-File API xuất hiện ở Java 22 dạng preview; trên JDK 24+ package chính thức nào chứa API này?
A. `java.lang.classfile` cung cấp API Class-File chuẩn.
B. `java.lang.reflect.classfile` chứa API ghi class file.
C. `java.nio.classfile` chứa parser và encoder class file.
D. `jdk.incubator.classfile` là package chính thức cuối cùng.
Đáp án đúng: A

Câu 30. Với Class-File API hiện đại, lời gọi `ClassFile.of().parse(bytes)` dùng để làm gì?
A. Parse bytes và trả về model đại diện cho class file.
B. Biên dịch đoạn Java source string thành Java bytecode.
C. Chạy method main trong bytes bằng class loader mặc định.
D. Nạp file vào JVM để tự ghi đè class đang hoạt động.
Đáp án đúng: A

Câu 31. G1 region pinning đưa vào Java 22 hữu ích nhất khi JNI sử dụng loại thao tác nào?
A. JNI gọi method static mà không có tham số hoặc return.
B. JNI đọc classpath rồi nạp module-info trước khi GC.
C. JNI tạo Java String literal và đưa vào string pool.
D. Các JNI critical regions có thể pin mảng primitive.
Đáp án đúng: D

Câu 32. Mục tiêu thực tế của G1 region pinning là gì trong các JNI critical section?
A. Vô hiệu hóa G1 để chương trình chuyển sang Serial GC.
B. Giữ toàn bộ heap bất động kể cả các region không bị pin.
C. Chuyển mọi Java object sang native memory trước khi thu gom.
D. Giảm GC pause khi có region bị pin bởi JNI critical section.
Đáp án đúng: D
