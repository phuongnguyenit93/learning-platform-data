Câu 01. Trong Java, khai báo `native` trên một method có ý nghĩa gì?
A. Phần triển khai nằm ở mã native được liên kết lúc chạy
B. Method chạy trong process riêng rồi truyền kết quả qua socket
C. Method được Java compiler triển khai bằng class bytecode ẩn
D. Method được JIT dịch sang mã máy mà không cần thư viện ngoài
Đáp án đúng: A

Câu 02. Khi tạo JNI headers cho Java class chứa native method bằng JDK hiện đại, lệnh nào phù hợp?
A. `javac -h out` tạo header C cho các native declarations
B. `javap -c out` tạo C binding bằng cách dịch bytecode
C. `java -h out` biên dịch source thành thư viện native liên kết
D. `jar --create` sinh header C khi đóng gói application JAR
Đáp án đúng: A

Câu 03. Để nạp native library bằng một đường dẫn file tuyệt đối, API Java nào đúng?
A. `System.loadLibrary(path)` nhận một absolute filename đầy đủ
B. `ClassLoader.loadClass(path)` nạp file `.so` hoặc `.dll`
C. `Runtime.exec(path)` nạp thư viện vào không gian JNI JVM
D. `System.load(path)` nhận absolute path tới native library
Đáp án đúng: D

Câu 04. Khi dùng `System.loadLibrary("codec")`, tham số `codec` đại diện cho điều gì?
A. Tên Java class chứa method `native` đầu tiên cần gọi
B. Tên Java module khai báo FFM `opens` để link library
C. Tên library logic để JVM tra cứu bằng cơ chế native loader
D. Đường dẫn tuyệt đối tới file JNI dùng trong container
Đáp án đúng: C

Câu 05. Nếu native method không có implementation được liên kết phù hợp, JVM có thể báo lỗi nào?
A. `UnsatisfiedLinkError` khi không resolve được native symbol
B. `IllegalStateException` khi JavaGC thu hồi object đang dùng
C. `NoSuchMethodException` khi Java reflection thiếu Method
D. `ClassCastException` do C type không cast được sang Java
Đáp án đúng: A

Câu 06. Với JNI implementation của instance native method, tham số ẩn đầu thường gồm gì?
A. `JNIEnv*` rồi `jobject` đại diện receiver của instance
B. `JavaVM*` rồi `jclass` ngay cả với instance methods
C. `JNIEnv*` rồi `jclass` cho receiver của instance
D. `jobject` rồi `JNIEnv*` theo thứ tự của Java method
Đáp án đúng: A

Câu 07. JNI implementation của static native method thường nhận đối tượng nào ở vị trí sau `JNIEnv*`?
A. `jmethodID` đại diện metadata của method được gọi
B. `jclass` đại diện class khai báo method static
C. `jarray` đại diện Java arguments sau khi đóng gói
D. `jobject` đại diện receiver instance của static method
Đáp án đúng: B

Câu 08. Vì sao không được chia sẻ trực tiếp `JNIEnv*` để gọi JNI từ thread khác?
A. `JNIEnv*` nằm trên native stack của thread khởi tạo JVM
B. `JNIEnv*` gắn với Java object nên các thread cùng object dùng chung
C. `JNIEnv*` gắn theo thread; cần environment của thread hiện tại
D. `JNIEnv*` chỉ hợp lệ trong constructor, không dùng được ở method
Đáp án đúng: C

Câu 09. Một native thread do C tạo muốn gọi JNI vào JVM đã chạy cần bước nào?
A. Gọi `JNIEnv.NewGlobalRef` để tự đăng ký thread mới với JVM
B. Gọi `System.loadLibrary` trong C để thay việc attach vào JVM
C. Gọi `Class.forName` từ C mà không cần JNI environment
D. Gọi `AttachCurrentThread` từ `JavaVM*` trước khi dùng JNI
Đáp án đúng: D

Câu 10. Native thread đã attach vào JVM và không còn dùng JNI thì nên làm gì?
A. Gọi `DestroyJavaVM` khi thread hoàn thành một callback
B. Gọi `ReleaseStringUTFChars` để JVM tự detach thread
C. Gọi `DetachCurrentThread` sau khi xong các JNI callbacks
D. Gọi `DeleteLocalRef` trên `JNIEnv*` để giải phóng thread
Đáp án đúng: C

Câu 11. Khi giữ Java object reference qua nhiều JNI native calls, loại reference nào phù hợp?
A. Giữ `jobject` local mà không cần gia hạn reference scope
B. Lưu local reference từ JNI frame cũ vào biến C tĩnh
C. Dùng `NewGlobalRef` tạo reference có lifetime ngoài JNI frame
D. Lưu địa chỉ raw của jobject sau khi kết thúc JNI call
Đáp án đúng: C

Câu 12. Trong vòng lặp JNI tạo hàng nghìn local references, cách hạn chế đầy bảng tham chiếu nào phù hợp?
A. Dùng `DeleteGlobalRef` cho từng local reference từ JNI frame
B. Dùng `DeleteLocalRef` cho refs không dùng nữa trong vòng lặp
C. Gọi `System.gc()` trong C trước khi tạo mỗi local reference
D. Giữ local references cho đến khi vòng lặp native kết thúc
Đáp án đúng: B

Câu 13. Điểm khác của JNI weak global reference so với global reference thông thường là gì?
A. Weak global là con trỏ C không cần JVM quản lý lifetime
B. Weak global không giữ object sống khi hết strong references
C. Weak global chỉ được tạo cho Java class mà không được cho object
D. Weak global ngăn GC thu hồi object cho tới khi DestroyJavaVM
Đáp án đúng: B

Câu 14. `GetStringUTFChars` của JNI cung cấp mã hóa nào cho dữ liệu chuỗi Java?
A. ISO-8859-1 theo encoding mặc định của host JVM process
B. UTF-16LE byte sequence vì `jchar` chứa code unit UTF-16
C. UTF-32 native endian cho C library nhận wchar_t pointer
D. Modified UTF-8 theo JNI, có khác biệt so với UTF-8 chuẩn
Đáp án đúng: D

Câu 15. Sau `GetStringUTFChars`, API nào phải dùng để trả tài nguyên về JVM đúng cách?
A. `DeleteGlobalRef` với pointer do GetStringUTFChars trả về
B. `free()` trực tiếp trên pointer từ GetStringUTFChars
C. `ReleasePrimitiveArrayCritical` với object kiểu jstring
D. Dùng `ReleaseStringUTFChars` với jstring và pointer đã lấy
Đáp án đúng: D

Câu 16. Vì sao phải giữ vùng `GetPrimitiveArrayCritical` càng ngắn càng tốt?
A. Critical region tự chuyển primitive array thành off-heap native buffer
B. Critical region đảm bảo mảng sẽ tồn tại sau khi JavaVM bị hủy
C. Critical region có thể cản GC; tránh blocking và JNI calls
D. Critical region cho phép GC di chuyển mảng giữa các lệnh
Đáp án đúng: C

Câu 17. Với `GetIntArrayElements`, giả định nào an toàn khi làm việc với JNI primitive array?
A. JVM có thể pin hoặc copy mảng; cần release sau khi dùng
B. API trả một `MemorySegment` Java với lifetime tự đóng
C. JVM trả raw pointer trực tiếp vào heap nên không cần release
D. JVM trả copy heap được C `free()` thay cho JNI release
Đáp án đúng: A

Câu 18. Nếu JNI gọi một Java method và phát sinh exception đang pending, bước xử lý nào hợp lý?
A. Tiếp tục gọi tùy ý các JNI APIs vì pending exception sẽ tự hết
B. Kiểm `ExceptionCheck`, rồi return hoặc clear có chủ đích
C. Dùng `free()` cho jobject bị lỗi để JVM tự bỏ pending exception
D. Bọc `JNIEnv*` trong synchronized C block để auto-clear exception
Đáp án đúng: B

Câu 19. Khi native code cần gọi instance Java method đã biết trên một jobject, nhóm API nào phù hợp?
A. Dùng `Get<Type>Field` và đọc bytecode của target method
B. Lấy `jmethodID` rồi gọi `Call<Type>Method` phù hợp
C. Dùng `NewGlobalRef` để thay việc gọi Java instance method
D. Dùng `CallStatic<Type>Method` để gọi instance không cần receiver
Đáp án đúng: B

Câu 20. Khi JNI làm việc với Java direct ByteBuffer, hàm nào lấy địa chỉ vùng native buffer?
A. `GetDirectBufferAddress` lấy con trỏ cho direct ByteBuffer
B. `GetObjectClass` trả địa chỉ data pointer của direct ByteBuffer
C. `GetStringUTFChars` trả pointer buffer dù ByteBuffer không phải String
D. `GetPrimitiveArrayCritical` trả pointer của direct ByteBuffer
Đáp án đúng: A

Câu 21. Hook nào JVM gọi khi native library có symbol phù hợp và được load qua JNI?
A. `JNI_OnAttach` được gọi mỗi khi Java thread bước vào JNI
B. `JNI_OnStart` được gọi trước static initializer của Java class
C. `JNI_OnLoad` hỗ trợ init và đăng ký native implementations
D. `JNI_OnClass` chạy mỗi khi có Java instance tạo trong JVM
Đáp án đúng: C

Câu 22. Khi ánh xạ Java `int` tới chữ ký JNI C, kiểu JNI nào phù hợp?
A. `jshort` biểu diễn số nguyên 32-bit tương ứng Java `int`
B. `jbyte` biểu diễn số nguyên 32-bit tương ứng Java `int`
C. `jint` là loại số nguyên 32-bit tương ứng Java `int`
D. `jlong` biểu diễn số nguyên 32-bit tương ứng Java `int`
Đáp án đúng: C

Câu 23. Khi Java 22+ gọi hàm C có tham số `long` trên Windows 64-bit và Linux 64-bit, điều gì cần lưu ý?
A. ABI LLP64/LP64 làm độ rộng C `long` khác trên hai hệ
B. FFM tự sửa ABI của thư viện C khi compiled library dùng kiểu khác
C. Java `long` tự thay đổi độ rộng từ 32 sang 64 bit theo hệ điều hành
D. C ABI 64-bit có cùng độ rộng `long` trên Windows và Linux
Đáp án đúng: A

Câu 24. Khi cần gọi một function export từ C++ library qua tên symbol C ổn định, kỹ thuật nào thường dùng?
A. Bật Java `--enable-preview` để JVM giải mã các C++ symbols
B. Dùng wrapper `extern "C"` để xuất entry point không bị name mangling
C. Đổi Java package name để khớp chữ ký mangled của C++ compiler
D. Dùng JNI `jclass` thay `extern "C"` để xuất C++ instance methods
Đáp án đúng: B

Câu 25. Khi đóng gói ứng dụng có thư viện JNI cho Windows và Linux, yêu cầu nào đúng?
A. Native binary cần khớp OS, CPU architecture và dependency ABI
B. Chỉ cần JAR của Java vì `System.loadLibrary` tự biên dịch C source
C. Đổi file extension `.so` sang `.dll` là đủ chuyển đổi binary
D. Dùng một file `.dll` cho cả Windows và Linux nếu Java bytecode giống
Đáp án đúng: A

Câu 26. Sau native crash dạng segmentation fault của JVM, nguồn chẩn đoán nào hữu ích?
A. Thêm `try/catch(Exception)` ở Java để lấy native memory dump
B. Dựa vào Java checked exception vì segfault có Java stack trace
C. Chạy `javap -verbose` để phát hiện lỗi truy cập con trỏ C
D. Xem `hs_err_pid`, native stack và core dump hoặc sanitizer
Đáp án đúng: D

Câu 27. Trong JDK 22, Foreign Function & Memory API được chuẩn hóa ở package nào?
A. `jdk.incubator.foreign` là package API chuẩn của Java 22
B. `java.lang.foreign` cung cấp MemorySegment, Arena và Linker
C. `java.lang.invoke.foreign` chứa bản API chuẩn hóa cho Java 22
D. `javax.foreign.memory` chứa `Arena` và `Linker` đã finalized
Đáp án đúng: B

Câu 28. Trong FFM, đối tượng nào mô tả vùng bộ nhớ kèm phạm vi truy cập và lifetime?
A. `SymbolLookup` chứa dữ liệu bytes trong C heap allocation
B. `MemorySegment` quản lý view vùng nhớ với bounds và lifetime
C. `FunctionDescriptor` sở hữu bộ nhớ cho native function pointer
D. `MethodHandle` biểu diễn raw native allocation với byte size
Đáp án đúng: B

Câu 29. `Arena.ofConfined()` có đặc điểm truy cập/lifetime nào đúng trong FFM?
A. Arena cho phép dùng segment sau close nếu giữ MemorySegment handle
B. Arena truy cập được từ nhiều thread và tự đóng ở lần GC tiếp theo
C. Arena tồn tại toàn JVM và không cho ứng dụng gọi close()
D. Segment của confined arena dùng ở owner thread và arena có thể close
Đáp án đúng: D

Câu 30. Khi nhiều Java threads cần truy cập cùng native segment có scope quản lý tường minh, chọn arena nào?
A. `Arena.ofConfined()` cho phép các threads đọc/ghi cùng lúc
B. `Arena.ofAuto()` đảm bảo close đồng bộ tại cuối try block
C. `Arena.global()` tạo shared arena đóng được qua try-with-resources
D. `Arena.ofShared()` cho phép nhiều thread truy cập và close
Đáp án đúng: D

Câu 31. Khi cấp phát native memory từ confined arena, idiom nào hỗ trợ giải phóng xác định thời điểm?
A. Dùng `System.gc()` để xác nhận close của confined arena trước return
B. Đặt `Arena` trong try-with-resources để đóng khi thoát block
C. Dùng `MemorySegment.NULL` để free vùng nhớ đã cấp phát từ arena
D. Giữ `Arena.ofAuto()` trong static field để đóng khi hết một request
Đáp án đúng: B

Câu 32. Điều gì xảy ra khi truy cập MemorySegment thuộc Arena đã đóng theo cơ chế kiểm tra an toàn?
A. Arena tự mở lại khi `MemorySegment.get` gọi trên handle cũ
B. FFM tự cấp phát segment mới cùng địa chỉ và byte contents cũ
C. Truy cập segment hết lifetime dẫn tới `IllegalStateException`
D. JVM biến segment thành unbounded pointer mà không kiểm tra
Đáp án đúng: C

Câu 33. Để đọc một C `int` 32-bit từ offset 0 của segment với layout phù hợp, API nào đúng?
A. `segment.get(ValueLayout.JAVA_LONG, 0)` đọc số nguyên 32-bit
B. `segment.address(ValueLayout.JAVA_INT, 0)` đọc số từ C pointer
C. `segment.getString(0)` đọc số nguyên theo native C int layout
D. `segment.get(ValueLayout.JAVA_INT, 0)` đọc C int 32-bit
Đáp án đúng: D

Câu 34. Trong FFM, layout nào thường mô tả một tham số C pointer khi tạo FunctionDescriptor?
A. `ValueLayout.ADDRESS` biểu diễn ABI layout của C pointer
B. `ValueLayout.JAVA_BOOLEAN` mô tả C pointer có thể null
C. `MemoryLayout.sequenceLayout(1)` mô tả pointer có C ABI
D. `ValueLayout.JAVA_INT` mô tả địa chỉ native pointer 64-bit
Đáp án đúng: A

Câu 35. Khi mô tả struct C có thể chứa alignment padding, điều nào quan trọng?
A. Đảm bảo layout và byte offsets khớp ABI C, bổ sung padding khi cần
B. `ValueLayout.JAVA_INT` biểu diễn struct C có nhiều field
C. `structLayout` suy ra padding của các C compiler từ tên field
D. Java `record` tự chuyển sang packed C struct không cần layout
Đáp án đúng: A

Câu 36. Trong FFM, API nào trả về linker cho native ABI của nền tảng đang chạy?
A. `SymbolLookup.nativeLinker()` lấy linker từ danh sách symbols
B. `Arena.nativeLinker()` lấy linker theo arena lưu segments
C. `Linker.nativeLinker()` lấy linker phù hợp ABI đang chạy
D. `FunctionDescriptor.nativeLinker()` lấy linker dựa trên return type
Đáp án đúng: C

Câu 37. Muốn tìm địa chỉ function export từ native library bằng FFM, bước nào hợp lý?
A. Dùng `FunctionDescriptor.find` để tìm địa chỉ từ library name
B. Dùng `Arena.allocate` để load module ELF/PE từ bytecode JAR
C. Dùng `SymbolLookup.libraryLookup` và `find` theo tên symbol
D. Dùng `MemorySegment.ofArray` để quét dynamic symbol table
Đáp án đúng: C

Câu 38. Để mô tả hàm C nhận một `int` và trả về một `int` trên ABI phù hợp, chọn gì?
A. `FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.JAVA_INT)`
B. `FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT)` trả C int 32-bit
C. `FunctionDescriptor.of(ValueLayout.ADDRESS, ValueLayout.JAVA_INT)`
D. `FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)`
Đáp án đúng: D

Câu 39. Với symbol `MemorySegment` và FunctionDescriptor đúng, API nào tạo handle gọi C từ Java?
A. `Linker.upcallStub(symbol, descriptor, arena)` tạo handle gọi C
B. `Linker.downcallHandle(symbol, descriptor)` tạo MethodHandle gọi C
C. `Arena.allocate(symbol, descriptor)` tạo handle cho function native
D. `MethodHandles.lookup().findVirtual(symbol, descriptor)` gọi C
Đáp án đúng: B

Câu 40. Khi muốn C library gọi ngược vào Java callback qua FFM, bước nào đúng?
A. `SymbolLookup.find(targetHandle)` tạo callback function trong C
B. `MemorySegment.ofArray(targetHandle)` biến lambda thành native function
C. `Linker.downcallHandle(targetHandle, descriptor)` cấp callback pointer
D. `Linker.upcallStub(targetHandle, descriptor, arena)` tạo callback stub
Đáp án đúng: D
