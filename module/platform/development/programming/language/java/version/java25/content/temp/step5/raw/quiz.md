Câu 1. Trong Java 25, tệp nguồn đơn giản chỉ chứa `void main() { ... }` mà không viết khai báo class tường minh có thể làm gì?
A. Được chạy bằng source-file launcher nhờ implicit class của Java 25.
B. Chỉ biên dịch nếu viết `public class Main` bao ngoài hàm.
C. Được JVM xem là script JavaScript rồi thông dịch từng dòng.
D. Chỉ chạy khi đổi tên main thành `static void main(String[])`.
Đáp án đúng: A

Câu 2. Với một class thường trong Java 25, khai báo nào có thể làm entry point mà không cần `static`?
A. `void main()` là instance main method được launcher hỗ trợ.
B. `static String main()` là entry point in chuỗi trả về.
C. `private void run()` là entry point nếu class có constructor.
D. `int main(String[] args)` là entry point trả về status code.
Đáp án đúng: A

Câu 3. Trong simple source file Java 25, cách nào in thông điệp với tiện ích IO được hỗ trợ?
A. `IO.trace("Hello");` ghi nội dung ra standard output.
B. `IO.println("Hello");` in ra standard output.
C. `IO.log("Hello");` ghi nội dung ra standard output.
D. `IO.writeFile("Hello");` in ra standard output.
Đáp án đúng: B

Câu 4. Tệp `Hello.java` chỉ có `void main() { IO.println("Hi"); }`; cách chạy trực tiếp phù hợp trên JDK 25 là gì?
A. `java Hello.java` chạy chương trình từ tệp nguồn.
B. `javac Hello.java` tự chạy hàm main ngay khi compile.
C. `jlink Hello.java` chạy tệp nguồn bằng custom runtime.
D. `java -jar Hello.java` chạy tệp nguồn như executable JAR.
Đáp án đúng: A

Câu 5. Trong Java 25, cú pháp nào nhập các public type của package được module `java.base` export?
A. `requires module java.base;` dùng trực tiếp trong source file.
B. `import package java.base;` là package import declaration.
C. `using module java.base;` là cú pháp module import.
D. `import module java.base;` là module import declaration.
Đáp án đúng: D

Câu 6. Module import `import module java.sql;` có tác dụng nào ở cấp source?
A. Cho phép dùng tên ngắn của public type từ package được export.
B. Mở các private field của module java.sql cho deep reflection.
C. Đưa toàn bộ package Java SQL lên runtime classpath mặc định.
D. Thay `requires java.sql` trong descriptor của mọi named module.
Đáp án đúng: A

Câu 7. Nếu mã thuộc named module và đã viết `import module java.sql;`, điều gì vẫn phải kiểm tra?
A. Module descriptor vẫn cần khai báo dependency cần đọc.
B. Module import tự tạo requires trong `module-info.java`.
C. Module import tự cấp quyền opens cho reflection runtime.
D. Module import tự chuyển project thành unnamed module.
Đáp án đúng: A

Câu 8. Khi hai module import đưa vào scope hai public type cùng tên đơn giản, cách giải quyết rõ ràng là gì?
A. Compiler luôn chọn type trong module import xuất hiện trước.
B. Viết qualified name hoặc import đơn kiểu để làm rõ.
C. Chỉ cần thêm `opens` cho module có package bị trùng tên.
D. JVM tự chọn class có bytecode được tải sau cùng.
Đáp án đúng: B

Câu 9. Tính năng flexible constructor bodies đã chuẩn hóa ở Java 25 cho phép làm gì?
A. Bỏ toàn bộ constructor invocation nếu superclass cần tham số.
B. Gọi instance method trên `this` trước mọi bước khởi tạo.
C. Chạy một số lệnh trước lời gọi tường minh `super(...)`.
D. Gọi constructor cha nhiều lần trong một constructor con.
Đáp án đúng: C

Câu 10. Trong constructor con Java 25, đoạn nào phù hợp để từ chối tham số âm trước khi gọi cha?
A. `if (n < 0) throw new IllegalArgumentException(); super(n);`.
B. `this.check(n); super(n);` với check là instance method.
C. `return; super(n);` để bỏ bước tạo object lúc tham số sai.
D. `super(n); if (n < 0) throw new IllegalArgumentException();`.
Đáp án đúng: A

Câu 11. Với flexible constructor bodies, việc nào vẫn không được phép ở prologue trước `super(...)`?
A. Gọi static helper để chuẩn hóa constructor argument.
B. Tính một biến local dựa trên đối số constructor.
C. Gọi một instance method của object đang được tạo.
D. Kiểm tra một constructor parameter rồi ném exception.
Đáp án đúng: C

Câu 12. Tại sao Java 25 cho phép validation trước `super(...)` trong constructor?
A. Để superclass constructor đọc được field con đã hoàn chỉnh.
B. Để JVM bỏ qua lời gọi superclass constructor khi không lỗi.
C. Để constructor con có thể chạy lần thứ hai sau khi tạo object.
D. Để phát hiện input sai trước khi khởi tạo superclass.
Đáp án đúng: D

Câu 13. Với hai constructor cùng class, `this(...)` vẫn có vai trò nào trong Java 25?
A. Thay thế superclass constructor bằng một static factory.
B. Ủy quyền khởi tạo cho constructor khác của cùng class.
C. Đưa đối số sang class loader để tạo instance mới.
D. Chuyển control tới method main khi khởi tạo xong.
Đáp án đúng: B

Câu 14. Nếu kiểm tra điều kiện trong prologue và ném exception trước `super(...)`, nhận định nào đúng?
A. Khởi tạo superclass bằng lời gọi đó chưa được thực hiện.
B. Đối tượng đã hoàn tất khởi tạo và được trả cho caller.
C. Superclass đã chạy xong vì JVM bắt buộc gọi trước prologue.
D. Java tự bắt exception để constructor có thể chạy tiếp.
Đáp án đúng: A

Câu 15. Trong Java 25, API nào tạo một key mới để truyền dữ liệu bất biến theo phạm vi gọi?
A. `ScopedValue.ofNullable()` tạo khóa scoped value.
B. `ScopedValue.openArena()` tạo khóa scoped value.
C. `ScopedValue.createThreadLocal()` tạo khóa scoped value.
D. `ScopedValue.newInstance()` tạo khóa scoped value.
Đáp án đúng: D

Câu 16. Với `ScopedValue<String> USER`, cách nào bind `USER` thành `"mai"` trong một scope?
A. `ScopedValue.where(USER, "mai").run(() -> use());`.
B. `USER.bind("mai"); use();` rồi gọi USER.unbind().
C. `ScopedValue.put(USER, "mai"); use();` trên mọi thread.
D. `USER.set("mai"); use();` rồi xóa với USER.remove().
Đáp án đúng: A

Câu 17. Khi gọi `USER.get()` trong dynamic scope đã bind `USER`, kết quả kỳ vọng là gì?
A. Giá trị mặc định null dù scope có binding hợp lệ.
B. Giá trị cuối cùng từng ghi bởi bất kỳ JVM thread nào.
C. Giá trị đã bind cho scope thực thi hiện tại.
D. Trực tiếp trả về đối tượng ScopedValue thay vì value.
Đáp án đúng: C

Câu 18. Với scoped value được bind lồng nhau, giá trị nào được thấy trong inner scope?
A. Binding cũ ở outer scope vì inner scope không được override.
B. Giá trị trong global map được đồng bộ giữa các thread.
C. Binding gần nhất của cùng khóa trong phạm vi đang chạy.
D. Giá trị null vì hai binding cùng khóa bị xem là xung đột.
Đáp án đúng: C

Câu 19. Sau khi `ScopedValue.where(KEY, x).run(action)` kết thúc, binding vừa tạo có trạng thái nào?
A. Trở thành field static được giữ cho các lần gọi tiếp theo.
B. Không còn hiệu lực ngoài dynamic scope đã kết thúc.
C. Vẫn tồn tại tới khi gọi KEY.remove() theo cách thủ công.
D. Chuyển thành ThreadLocal để mọi task kế tiếp dùng lại.
Đáp án đúng: B

Câu 20. Nếu cần kiểm tra khóa ScopedValue có binding trong scope hiện tại hay chưa, dùng API nào?
A. `KEY.isPresent()` trả về một Optional chứa binding.
B. `KEY.isBound()` cho biết có binding hiện hành.
C. `KEY.hasValue()` kiểm tra một field mutable của KEY.
D. `KEY.isRegistered()` kiểm tra khóa trong global registry.
Đáp án đúng: B

Câu 21. So với ThreadLocal, mô hình sử dụng ScopedValue được thiết kế cho tình huống nào?
A. Lưu trạng thái mutable dùng chung giữa mọi request độc lập.
B. Bảo đảm mọi thread tự nhận binding mà không xét cấu trúc task.
C. Thay thế cấu hình JVM property có hiệu lực toàn tiến trình.
D. Truyền context theo scope với binding không bị gán lại tại chỗ.
Đáp án đúng: D

Câu 22. API nào được chuẩn hóa ở Java 25 để dẫn xuất khóa mật mã từ dữ liệu khóa đầu vào?
A. `javax.crypto.Cipher` là API mới cho key derivation.
B. `java.util.random.RandomGenerator` là API tạo derived keys.
C. `javax.crypto.KDF` là API key derivation function.
D. `java.security.MessageDigest` là API quản lý key exchange.
Đáp án đúng: C

Câu 23. Cách nào chọn implementation HKDF-SHA256 qua KDF API khi provider có hỗ trợ?
A. `Cipher.getInstance("HKDF-SHA256")` dẫn xuất khóa mới.
B. `KDF.getDefault("HKDF-SHA256")` lấy implementation.
C. `KeyGenerator.getInstance("HKDF-SHA256")` là API KDF.
D. `KDF.getInstance("HKDF-SHA256")` lấy implementation.
Đáp án đúng: D

Câu 24. HKDF áp dụng mô hình nào để tạo key material theo ngữ cảnh sử dụng?
A. Tạo random bytes bằng timestamp của JVM mà không dùng IKM.
B. Extract rồi expand với nguồn khóa, salt và thông tin ngữ cảnh.
C. Mã hóa trực tiếp plaintext bằng AES trước khi sinh secret key.
D. Chỉ băm một lần rồi sử dụng digest làm khóa cho mọi mục đích.
Đáp án đúng: B

Câu 25. Khi cần key khác nhau cho hai mục đích từ cùng input key material, nên sử dụng phần nào của HKDF?
A. Dùng cùng info và ghi đè byte đầu tiên của secret key.
B. Đưa context riêng vào tham số `info` ở bước expand.
C. Tắt salt để HKDF tự bảo đảm key khác nhau theo mục đích.
D. Gọi cùng input và cùng info rồi kỳ vọng output mới mỗi lần.
Đáp án đúng: B

Câu 26. Trong thiết kế bảo mật, KDF/HKDF không có nhiệm vụ chính nào sau đây?
A. Cung cấp output key material cho thuật toán khác.
B. Tách các khóa sử dụng theo thông tin ngữ cảnh.
C. Dẫn xuất subkey từ key material có đủ độ mạnh.
D. Thực hiện mã hóa message và tạo ciphertext trực tiếp.
Đáp án đúng: D

Câu 27. Tùy chọn Java 25 nào giúp tạo AOT cache trong một lần chạy huấn luyện ứng dụng?
A. `-Xshare:off` xuất AOT cache dưới dạng executable.
B. `-XX:AOTCacheOutput=app.aot` lưu cache tạo từ quá trình chạy.
C. `-XX:AOTCache=app.aot` tạo cache mới trong một lượt chạy.
D. `--enable-preview` tự xây AOT cache sau mọi lần khởi chạy.
Đáp án đúng: B

Câu 28. Khi một AOT cache tương thích đã có, tùy chọn nào yêu cầu JVM thử dùng cache lúc khởi động?
A. `-XX:AOTCacheOutput=app.aot` bắt buộc tải cache đã lưu.
B. `-XX:DumpLoadedClassList=app.aot` là lệnh tải AOT cache.
C. `-XX:AOTCache=app.aot` để JVM nạp cache đã tạo.
D. `-XX:+UnlockDiagnosticVMOptions` tự động tải mọi cache.
Đáp án đúng: C

Câu 29. Java 25 hỗ trợ ahead-of-time method profiling nhằm mục tiêu nào?
A. Khóa cứng quyết định JIT và chặn tối ưu hóa trong runtime.
B. Biên dịch mọi method thành native code độc lập với CPU.
C. Dùng profile thu được từ training để tối ưu method sớm hơn.
D. Bỏ hẳn thu thập profiling của JVM trong mọi lần chạy.
Đáp án đúng: C

Câu 30. Nhận định nào đúng về lợi ích của AOT cache khi nâng cấp từ Java 21 lên Java 25?
A. Cache bảo đảm không còn warmup trên mọi môi trường JVM.
B. Cache là file thực thi native có thể chạy mà không cần JDK.
C. Cache luôn dùng chung giữa các bản JDK không cần kiểm tra.
D. Cần đo startup, warmup và xác minh điều kiện tương thích cache.
Đáp án đúng: D

Câu 31. Khi muốn so sánh allocation và pause giữa hai JDK trong quá trình nâng cấp, công cụ nào phù hợp?
A. `javadoc` cung cấp thống kê allocation và GC pause.
B. `javac` cung cấp báo cáo CPU runtime của mỗi Java thread.
C. `jar` cung cấp event profile của ứng dụng đang chạy.
D. JFR recording cung cấp sự kiện để phân tích hoạt động JVM.
Đáp án đúng: D

Câu 32. Chiến lược kiểm thử nào phù hợp khi ứng dụng chuyển từ Java 21 lên Java 25?
A. Tắt cảnh báo reflective access rồi bỏ qua thử nghiệm production.
B. Chỉ so số file JAR để khẳng định hành vi ứng dụng tương đương.
C. Chạy regression, đo JFR và kiểm tra lại module/API compatibility.
D. Bỏ regression vì Java 25 bảo đảm cùng hiệu năng với Java 21.
Đáp án đúng: C
