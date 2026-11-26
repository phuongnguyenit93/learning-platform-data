Câu 1. Trong quá trình JVM loading một class, kết quả cốt lõi của bước này là gì?
A. Nạp biểu diễn nhị phân và tạo đối tượng `Class` tương ứng.
B. Chạy toàn bộ static initializer trước khi xác minh bytecode.
C. Chạy constructor của class để chuẩn bị instance đầu tiên.
D. Biên dịch mọi method sang mã máy và ghi vào code cache.
Đáp án đúng: A

Câu 2. Theo đặc tả JVM, linking một class bao gồm các hoạt động nào?
A. Linking gồm code compilation, GC và giải phóng metadata.
B. Linking gồm loading, chạy `<clinit>` và xóa constant pool.
C. Linking gồm verification, preparation và resolution.
D. Linking gồm initialization, chạy constructor và resolve.
Đáp án đúng: C

Câu 3. Trong linking, giai đoạn preparation tác động thế nào lên static field?
A. Preparation gán mặc định hoặc hằng `ConstantValue` cho static field.
B. Preparation cấp phát toàn bộ instance của class sắp được gọi.
C. Preparation chạy code trong static initializer của class.
D. Preparation gọi constructor lớp cha trước constructor lớp con.
Đáp án đúng: A

Câu 4. Khi khởi tạo class con lần đầu, class cha chưa được khởi tạo sẽ ra sao?
A. Class cha đợi đến lúc tạo object thứ hai mới khởi tạo.
B. Class cha được khởi tạo trước khi class con khởi tạo.
C. Class cha chỉ khởi tạo nếu constructor con gọi `super()` rõ.
D. Class cha khởi tạo sau khi class con chạy hết `<clinit>`.
Đáp án đúng: B

Câu 5. Với `Class.forName("demo.Plugin")`, hành vi mặc định nào phù hợp?
A. Chạy constructor không tham số để tạo một plugin instance.
B. Yêu cầu nạp và khởi tạo class được tìm thấy theo quy tắc API.
C. Chỉ tìm resource bytecode, không liên kết và không khởi tạo.
D. Khởi tạo mọi class trong package `demo` trước khi trả kết quả.
Đáp án đúng: B

Câu 6. Với `Class.forName(name, false, loader)`, tham số `false` có ý nghĩa gì?
A. Không yêu cầu khởi tạo class trong lần gọi `forName` này.
B. Không cho class loader áp dụng parent-first delegation.
C. Không cho JVM tạo đối tượng `Class` trong lúc loading.
D. Không cho verifier kiểm tra tính hợp lệ bytecode của class.
Đáp án đúng: A

Câu 7. Khi gọi `loader.loadClass("demo.Tool")` thành công, điều gì chưa được bảo đảm?
A. Class loader đã tìm thấy định nghĩa phù hợp với tên được hỏi.
B. Lời gọi có thể trả về Class object được loader cha nạp.
C. Đối tượng `Class<?>` tương ứng đã được trả cho caller.
D. Static initializer có thể chưa chạy sau lời gọi `loadClass`.
Đáp án đúng: D

Câu 8. Khi dùng `java -cp lib/a.jar:app/classes Main` trên Linux, `-cp` xác định gì?
A. Dùng classpath để tra cứu class/resource của ứng dụng.
B. Xác định đường dẫn chứa named module cho module-path.
C. Xác định đường dẫn thay thế boot module của JDK khi chạy.
D. Xác định thư mục mà JVM sẽ xuất heap dump nếu xảy ra OOM.
Đáp án đúng: A

Câu 9. Với `ClassLoader.loadClass` mặc định, parent delegation thường được thực hiện ra sao?
A. Luôn bỏ qua parent khi lớp thuộc một package của ứng dụng.
B. Hỏi parent trước rồi mới gọi `findClass` ở loader hiện tại.
C. Gọi `findClass` trước rồi hỏi parent khi đã định nghĩa class.
D. Nạp mỗi class hai lần: một ở parent rồi một ở loader con.
Đáp án đúng: B

Câu 10. Khi kiểm tra `String.class.getClassLoader()` trên HotSpot/JDK phổ biến, thường thấy gì?
A. Instance của thread context loader khi gọi `getClassLoader`.
B. Thường là `null`, đại diện cho bootstrap loader của JVM.
C. Instance của application class loader hiện đang sử dụng.
D. Instance của platform class loader do app tự đăng ký.
Đáp án đúng: B

Câu 11. Trong JDK hiện đại, platform class loader thường phụ trách loại lớp nào?
A. Các lớp Java được JIT biên dịch thành mã máy trong code cache.
B. Chỉ các class do plugin custom loader định nghĩa bằng bytecode.
C. Toàn bộ lớp từ JAR riêng của ứng dụng trong classpath.
D. Các lớp thuộc một số module nền tảng ngoài bootstrap loader.
Đáp án đúng: D

Câu 12. Hàm `ClassLoader.getSystemClassLoader()` thường trả về loader nào?
A. Bootstrap loader dưới dạng đối tượng Java truy cập công khai.
B. Loader đã định nghĩa `java.lang.String` trong Java heap.
C. Loader mới được tạo cho từng lệnh gọi để tránh cache.
D. System/application class loader được dùng theo cấu hình JVM.
Đáp án đúng: D

Câu 13. Theo JVM, hai class có cùng binary name được xem là cùng runtime type khi nào?
A. Chúng được load trong cùng tiến trình JVM dù loader khác.
B. Chúng có cùng binary name và cùng defining class loader.
C. Chúng có cùng package và cùng superclass trong source.
D. Chúng có cùng tên và nguồn bytecode dù loader khác nhau.
Đáp án đúng: B

Câu 14. Hai plugin tự nạp `com.demo.Model` từ hai defining loader khác nhau; ép kiểu trực tiếp giữa chúng có thể gây gì?
A. `StackOverflowError` vì tên binary class được dùng hai lần.
B. `IllegalMonitorStateException` do kiểm tra cast qua loader.
C. `ClassCastException` vì hai defining loader tạo type khác nhau.
D. `NoSuchFieldException` vì bytecode của hai JAR không giống.
Đáp án đúng: C

Câu 15. Khi viết custom `ClassLoader` theo mô hình parent-first chuẩn, hook nào thường được override để tìm bytecode?
A. Override `getParent()` để đổi tên class đang được hỏi.
B. Override `resolveClass(Class)` để thay bytecode bằng resource.
C. Override `findClass(String)` để tìm bytecode khi parent không có.
D. Override `findLoadedClass(String)` để xóa class đã nạp.
Đáp án đúng: C

Câu 16. Sau khi custom loader đọc được mảng byte của class hợp lệ, API nào dùng để định nghĩa class?
A. Dùng `resolveClass(...)` để tạo Class từ một byte array.
B. Dùng `getResource(...)` để biến class bytes thành runtime type.
C. Dùng `Class.forName(...)` với mảng byte như một đối số.
D. Dùng `defineClass(...)` để định nghĩa class từ byte hợp lệ.
Đáp án đúng: D

Câu 17. Trong `loadClass` tùy biến, `findLoadedClass(name)` giúp giải quyết nhu cầu nào?
A. `findLoadedClass` chuyển quyền định nghĩa class sang parent.
B. `findLoadedClass` xoá class để ép loader nạp lại phiên bản mới.
C. `findLoadedClass` chạy `<clinit>` để cập nhật state của class.
D. `findLoadedClass` tra class được gắn với initiating loader.
Đáp án đúng: D

Câu 18. Gọi `resolveClass(clazz)` trên class đã load nhằm mục đích chính nào?
A. `resolveClass` unload class khỏi Metaspace sau khi liên kết.
B. `resolveClass` chạy static initializer mỗi lần được gọi.
C. `resolveClass` phục vụ linking, không tạo object của class.
D. `resolveClass` tạo instance qua constructor mặc định.
Đáp án đúng: C

Câu 19. Thiết kế plugin có loader riêng nhưng cùng interface `PluginApi`; cách tổ chức nào tránh lỗi type identity?
A. Đặt API ở parent loader, implementation ở plugin child.
B. Đổi toàn bộ API chung sang child-first cho từng plugin.
C. Định nghĩa mỗi `PluginApi` riêng rồi gộp Class object lại.
D. Sao chép `PluginApi` vào mỗi child rồi cast dựa trên tên.
Đáp án đúng: A

Câu 20. Với `loader.getResourceAsStream("config/app.properties")`, cách hiểu đường dẫn nào đúng?
A. Tên resource được hiểu thành đường dẫn file tuyệt đối trên OS.
B. Tên resource được tìm từ gốc classpath, không cần dấu `/` đầu.
C. Tên resource tự tính tương đối theo package của class đang gọi.
D. Tên resource phải dùng `./` trước đường dẫn trong JAR.
Đáp án đúng: B

Câu 21. Với `MyClass.class.getResource("/config/app.properties")`, dấu `/` mở đầu biểu thị gì?
A. Tìm resource tuyệt đối từ gốc classpath/module của class.
B. Tìm resource trên HTTP server root của ứng dụng Spring.
C. Tìm resource tương đối với package chứa `MyClass`.
D. Tìm file tuyệt đối `/config/app.properties` trong hệ điều hành.
Đáp án đúng: A

Câu 22. Khi nhiều JAR chứa resource cùng tên `META-INF/service.cfg`, API nào hỗ trợ liệt kê các bản tìm được?
A. Dùng `Class.forName(name)` để tìm mọi resource URL.
B. Dùng `getResource(name)` để liệt kê nhiều resource URL.
C. Dùng `getResources(name)` để liệt kê nhiều resource URL.
D. Dùng `Package.getPackage(name)` để liệt kê JAR resource.
Đáp án đúng: C

Câu 23. Với `ServiceLoader.load(MyService.class)`, class loader nào thường được dùng mặc định để tìm provider?
A. Mặc định tự tạo một `URLClassLoader` riêng cho mỗi lần.
B. Mặc định dùng bootstrap loader cho mọi service ở ứng dụng.
C. Mặc định dùng defining loader của `ServiceLoader` class.
D. Mặc định dùng thread context class loader của caller.
Đáp án đúng: D

Câu 24. Với service provider trên classpath, tệp nào thường khai báo tên implementation để `ServiceLoader` tìm thấy?
A. Đặt chữ ký provider trong `META-INF/MANIFEST.MF`.
B. Đặt danh sách provider trong `module-info.class` ở classpath.
C. Đặt tên provider trong `META-INF/services/<fqcn-service>`.
D. Đặt constructor provider vào `META-INF/versions/9`.
Đáp án đúng: C

Câu 25. Khi đã dùng xong một `URLClassLoader` mở JAR, tác dụng của `close()` là gì?
A. `close()` buộc JVM unload các class mà loader đã định nghĩa.
B. `close()` đóng parent loader cùng các static field của plugin.
C. `close()` giải phóng JAR handles, không bảo đảm class unload.
D. `close()` gọi GC và dọn object còn được giữ bởi ứng dụng.
Đáp án đúng: C

Câu 26. Một class compile được nhưng runtime xuất hiện `ClassNotFoundException`; nguyên nhân nào phù hợp?
A. Static initializer thành công rồi bị JVM gọi lặp lại.
B. Object đã tạo nhưng constructor ném checked exception.
C. Method không chạy vì thiếu quyền ghi file tạm.
D. Loader không tìm thấy tên class trên classpath hiện có.
Đáp án đúng: D

Câu 27. Một class từng lỗi trong static initialization, lần sử dụng tiếp theo có thể gặp gì?
A. `NoClassDefFoundError` vì class đã bị đánh dấu erroneous.
B. `IllegalArgumentException` do constructor chưa được gọi.
C. `ClassNotFoundException` mỗi lần vì JVM luôn xóa bytecode.
D. `UnsupportedClassVersionError` vì bytecode tự tăng version.
Đáp án đúng: A

Câu 28. Khi chạy class file biên dịch với phiên bản Java mới hơn runtime hỗ trợ, lỗi liên kết thường là gì?
A. `ClassCircularityError` vì class file chứa abstract method.
B. `IllegalAccessException` vì constant pool thay đổi cấu trúc.
C. Class file quá mới gây `UnsupportedClassVersionError`.
D. `ExceptionInInitializerError` vì JIT thiếu compiler mới.
Đáp án đúng: C

Câu 29. App biên dịch với thư viện có method `pay()` nhưng chạy với JAR cũ không có method đó; lỗi nào phù hợp?
A. `ClassNotFoundException` dù class trong JAR vẫn tải được.
B. Thiếu method ở runtime gây lỗi `NoSuchMethodError`.
C. `StackOverflowError` vì method bị thiếu tạo vòng lặp gọi.
D. `SecurityException` khi runtime thiếu member của thư viện.
Đáp án đúng: B

Câu 30. Trong Java module system, `ModuleLayer` hữu ích với kiến trúc plugin như thế nào?
A. Layer mới chuyển named module vào classpath của JVM.
B. Layer mới dùng bootstrap loader cho toàn bộ plugin.
C. Layer mới đổi tên package đã định nghĩa trước đó.
D. Layer dùng module configuration và class loader riêng.
Đáp án đúng: D

Câu 31. Để class từ plugin loader có thể được unload, điều kiện GC quan trọng nào cần có?
A. `close()` làm class unload ngay khi resource được đóng.
B. Cần loader hết reachable để class có thể được unload.
C. Sửa string classpath là đủ sau khi plugin kết thúc.
D. `System.gc()` unload class dù cache còn giữ loader.
Đáp án đúng: B

Câu 32. Khi redeploy plugin liên tục và thấy class loader cũ còn sống, điều tra nào phù hợp?
A. Kiểm tra ThreadLocal, thread và cache giữ class loader.
B. Đổi tên package sau deploy để cắt toàn bộ reference.
C. Xóa file JAR trên disk để làm các class cũ biến mất.
D. Tăng `-Xmx` để GC đủ bộ nhớ và dọn loader cũ.
Đáp án đúng: A
