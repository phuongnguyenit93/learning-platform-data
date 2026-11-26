Câu 01. Với `Class.forName("com.acme.Task")`, điều gì xảy ra nếu lớp chưa được khởi tạo?
A. Tạo instance bằng constructor mặc định ngay khi thấy class
B. Class được nạp và khởi tạo, có thể chạy static initializer
C. Đọc file `.class` nhưng bỏ qua cả liên kết và khởi tạo
D. Chỉ trả metadata của lớp mà không thực thi class initializer
Đáp án đúng: B

Câu 02. API reflection nào liệt kê method khai báo trực tiếp trong class kể cả non-public?
A. `getMethods()` lấy cả các method non-public của superclass
B. `getDeclaredMethods()` trả method do chính type khai báo
C. `getDeclaredFields()` trả về các method có field tương ứng
D. `getConstructors()` lấy method instance và static của class
Đáp án đúng: B

Câu 03. Khi gọi `Class.getMethods()`, tập method được trả về có đặc điểm nào?
A. Chỉ gồm các method static và loại bỏ instance methods
B. Bao gồm private methods của các lớp cha theo hierarchy
C. Gồm public methods của type và các superclass được kế thừa
D. Chỉ gồm method khai báo trong chính class đang được hỏi
Đáp án đúng: C

Câu 04. Trong ứng dụng dùng JPMS, `AccessibleObject.trySetAccessible()` có thể trả về gì?
A. Giá trị `true` khi caller bất kỳ truy cập private member
B. Một `SecurityContext` mô tả quyền reflection của package
C. `false` nếu module từ chối mở quyền reflection cho caller
D. Một `MethodHandle` nếu package đã export cho module gọi
Đáp án đúng: C

Câu 05. Nếu method được gọi qua `Method.invoke()` ném lỗi nghiệp vụ, reflection thường báo gì?
A. `InvocationTargetException` chứa ngoại lệ từ method được gọi
B. `NoSuchMethodException` khi body của method ném runtime error
C. `IllegalAccessException` cho lỗi do code của target method ném
D. `ClassNotFoundException` khi method có exception checked
Đáp án đúng: A

Câu 06. Muốn lấy constructor private do chính class khai báo, lời gọi nào phù hợp?
A. `getConstructors()` tìm constructor private của superclass
B. `getDeclaredConstructor(...)` tìm cả constructor non-public
C. `getConstructor(...)` tìm cả constructor private được kế thừa
D. `getDeclaredMethod(...)` trả một constructor theo tham số
Đáp án đúng: B

Câu 07. Trong `module-info.java`, directive nào hỗ trợ deep reflection vào package được mở?
A. `requires` tự mở các member non-public của module phụ thuộc
B. `uses` cấp private reflection cho service provider được chọn
C. `exports` cấp quyền đọc private fields qua reflection mặc định
D. `opens` cho phép truy cập phản chiếu sâu theo phạm vi module
Đáp án đúng: D

Câu 08. Với `MethodHandles.lookup()` trong một class, quyền tra cứu của Lookup dựa vào đâu?
A. `MethodHandles.lookup()` dùng quyền của class thực hiện lời gọi
B. Quyền truy cập root của toàn JVM khi phương thức được gọi
C. Class loader đầu tiên đã từng load `java.lang.invoke`
D. Tên module được truyền từ biến môi trường `JAVA_HOME`
Đáp án đúng: A

Câu 09. Khi cần private MethodHandle của class thuộc module khác, `privateLookupIn` cần điều kiện nào?
A. Export package cấp quyền private lookup vào member non-public
B. Caller đủ quyền và package đích đã mở cho module caller
C. Chỉ cần tên class, không cần mở package qua directive `opens`
D. Caller có quyền public lookup để truy cập private member đích
Đáp án đúng: B

Câu 10. Khi `Lookup.findVirtual` tìm instance method, cách gọi handle thường yêu cầu gì?
A. Handle nhận receiver trước, rồi mới đến method arguments
B. Truyền object `Class` làm đối số cuối để xác định receiver
C. Truyền tên class như String thay cho receiver runtime
D. Chỉ truyền method arguments vì receiver đã được JVM tự suy luận
Đáp án đúng: A

Câu 11. Handle trả từ `Lookup.findStatic` đối với static method khác `findVirtual` thế nào?
A. Nhận receiver instance trước các tham số của static method
B. Trả về `Field` thay vì `MethodHandle` do static binding
C. Không thể sử dụng `invokeExact` dù method type đã khớp
D. Handle không cần receiver instance trong danh sách argument
Đáp án đúng: D

Câu 12. Điểm chính của `MethodHandle.invokeExact(...)` là gì?
A. Call site có thể bỏ qua kiểu return khi handle trả giá trị
B. JVM tự chuyển String thành int nếu method đích nhận số
C. MethodHandle tự tìm overload phù hợp theo đối tượng runtime
D. Call site phải khớp chính xác kiểu tham số và return type
Đáp án đúng: D

Câu 13. Với `MethodHandle.invoke(...)`, điều nào đúng so với `invokeExact(...)`?
A. Chỉ có thể gọi các method trả về `void` trong cùng module
B. Tự ánh xạ method name thành tên overload tại runtime
C. `invoke` hỗ trợ conversion kiểu tương thích qua `asType`
D. Bỏ kiểm tra kiểu return và argument cho các call site
Đáp án đúng: C

Câu 14. API nào tạo chữ ký method type với return `String` và argument `int`?
A. `MethodType.methodType(String.class, int.class)` tạo kiểu hàm
B. `MethodType.methodType(int.class, String.class)` đảo thứ tự kiểu
C. `MethodHandles.lookup(String.class, int.class)` tạo method type
D. `MethodHandle.type(String.class, int.class)` tạo chữ ký mới
Đáp án đúng: A

Câu 15. Sau khi `bindTo(receiver)` trên handle có tham số tham chiếu đầu, kết quả là gì?
A. Cố định argument tham chiếu đầu và giảm một tham số khi gọi
B. Handle mới chỉ đổi return type mà không ràng buộc argument
C. Handle mới đã gắn argument cuối và cần thêm receiver lúc gọi
D. Handle cũ bị thay đổi trực tiếp và không thể tái sử dụng
Đáp án đúng: A

Câu 16. Khi gọi `Lookup.findConstructor`, `MethodType` truyền vào mô tả return type nào?
A. Return type là chính class mới bất kể kiểu trong descriptor
B. Return type là `Class<?>` để biểu diễn metadata constructor
C. Descriptor dùng return `void`; handle tạo instance khi gọi
D. Return type là `Object` dù constructor thuộc lớp cụ thể
Đáp án đúng: C

Câu 17. Khi gọi lặp đi lặp lại cùng method động, cách giảm chi phí tra cứu nào hợp lý?
A. Lặp `getDeclaredMethods()` trước từng invoke để JVM tối ưu
B. Dùng `Method.invoke()` mỗi lần với `setAccessible` mới
C. Cache MethodHandle và benchmark, tránh lookup lặp trong hot path
D. Tắt JIT để các lời gọi dynamic chạy qua interpreter
Đáp án đúng: C

Câu 18. Để truy cập một instance field `int count` theo VarHandle, API lookup nào đúng?
A. `findVarHandle(Owner.class,"count",int.class)` tạo field handle
B. `findVirtual(Owner.class,"count",methodType(int.class))` trả VarHandle
C. `findStaticVarHandle(Owner.class,"count",int.class)` tạo instance handle
D. `findGetter(Owner.class,"count",int.class)` trả về một VarHandle
Đáp án đúng: A

Câu 19. Với `VarHandle.compareAndSet`, kết quả trả về thể hiện điều gì?
A. Giá trị mới sau khi thực hiện đổi bất kể so sánh đúng sai
B. Số lần thread khác cập nhật biến trong lúc CAS chạy
C. Boolean báo việc cập nhật CAS nguyên tử có thành công không
D. Giá trị cũ đọc được trước phép đổi theo kiểu witness value
Đáp án đúng: C

Câu 20. Điểm khác biệt của `VarHandle.compareAndExchange` so với `compareAndSet` là gì?
A. Trả về boolean phản ánh việc so sánh expected thành công
B. Trả giá trị được đọc trước CAS thay vì boolean thành công
C. Chỉ hoạt động với static field còn compareAndSet dùng instance
D. Chỉ đảm bảo plain access nên không có tính atomic
Đáp án đúng: B

Câu 21. Khi đọc shared field bằng `VarHandle.getVolatile`, bảo đảm nào được nhắm tới?
A. Tự biến đổi field thường thành `final` khi trả về giá trị
B. Thực hiện volatile read với quy tắc visibility và ordering
C. Thực hiện plain read mà không có quy tắc ordering với threads
D. Tự áp dụng monitor lock cho object được đọc trong Java code
Đáp án đúng: B

Câu 22. `setRelease` và `getAcquire` của VarHandle thường dùng để xây dựng quan hệ gì?
A. Khóa monitor trên object receiver cho toàn bộ read/write
B. Xóa dữ liệu của các thread khác trước khi đọc biến chung
C. Đọc và ghi không đồng bộ theo kiểu plain field access
D. Thiết lập ordering theo hướng publish với release và acquire
Đáp án đúng: D

Câu 23. Muốn thao tác phần tử mảng `long[]` qua VarHandle, factory nào phù hợp?
A. `MethodHandles.lookup().findVarHandle(long[].class,"0",long.class)`
B. `MethodHandles.arrayElementVarHandle(long[].class)` tạo array handle
C. `MethodHandles.byteArrayViewVarHandle(long[].class,ByteOrder.BIG_ENDIAN)`
D. `MethodHandles.lookup().findStaticVarHandle(long[].class,"length",int.class)`
Đáp án đúng: B

Câu 24. So với `getVolatile`, chế độ đọc `VarHandle.getOpaque` có đặc điểm nào?
A. Ordering yếu hơn volatile read trong Java Memory Model
B. Cấm compiler giữ kết quả đọc ở các phép gọi liên tiếp
C. Có ordering mạnh hơn volatile read khi dùng với giá trị primitive
D. Khóa độc quyền các thread cùng đọc để bảo đảm linearization
Đáp án đúng: A

Câu 25. `Proxy.newProxyInstance` của JDK nhận những thành phần chính nào?
A. Một constructor class, một `Lookup` và target `CallSite`
B. `Class<?>`, `VarHandle` và dynamic method descriptor
C. ClassLoader, concrete superclass và `MethodHandle`
D. ClassLoader, danh sách interface và `InvocationHandler`
Đáp án đúng: D

Câu 26. Phương thức `InvocationHandler.invoke` nhận thông tin nào khi proxy có lời gọi?
A. Proxy object, đối tượng `Method` và mảng arguments
B. Tên method, đối tượng `CallSite` và `MethodType`
C. Một `MethodHandle`, `Lookup` và caller `ClassLoader`
D. `VarHandle`, class metadata và thread đang thực thi
Đáp án đúng: A

Câu 27. Với JDK dynamic proxy, lời gọi `equals`, `hashCode` và `toString` thường được xử lý ra sao?
A. Các lời gọi Object này được chuyển tới `InvocationHandler`
B. Được compiler chuyển thành bytecode `invokedynamic` riêng
C. Chuyển thẳng tới Object implementation mà không qua handler
D. Bị JVM cấm vì ba method thuộc class `java.lang.Object`
Đáp án đúng: A

Câu 28. Giới hạn cấu trúc quan trọng của `java.lang.reflect.Proxy` là gì?
A. Tạo instance cho class có private constructor không cần interface
B. Được dùng để bổ sung field mới trực tiếp vào class gốc
C. Tạo class triển khai interfaces, không subclass concrete class tùy ý
D. Tạo subclass của concrete class kể cả khi class đã final
Đáp án đúng: C

Câu 29. Khi handler muốn thực thi default method của interface trong proxy trên JDK hiện đại, API nào phù hợp?
A. `InvocationHandler.invoke(proxy, method, args)` tự bypass handler
B. `MethodHandles.publicLookup().findStatic(...)` gọi default method
C. `Proxy.getInvocationHandler(proxy).toString()` gọi default method
D. `InvocationHandler.invokeDefault(...)` gọi default method trực tiếp
Đáp án đúng: D

Câu 30. Vai trò của bootstrap method với instruction `invokedynamic` là gì?
A. Chuyển JVM bytecode sang Java source trước lúc JIT compile
B. Phát hành object proxy ở mỗi lần gọi không cần call site
C. Liên kết call site động và trả về một `CallSite` cho JVM
D. Đổi class loader mặc định để JVM tìm constructor public
Đáp án đúng: C

Câu 31. Khi bootstrap thiết lập target cho một `invokedynamic`, kiểu của target cần gì?
A. Một `VarHandle` có coordinate types khớp local variables
B. `MethodHandle` có method type khớp invokedynamic descriptor
C. Một `Method` reflection không cần cấu trúc CallSite riêng
D. `MethodHandle` có return type `Object` không cần xét parameters
Đáp án đúng: B

Câu 32. Điểm khác biệt của `ConstantCallSite` trong java.lang.invoke là gì?
A. Target có thể đổi giữa threads sau khi gọi `syncAll`
B. Target được đọc với volatile semantics sau mỗi update
C. Target bị vô hiệu hóa qua `SwitchPoint.invalidateAll`
D. Target không thể đổi sau khi CallSite được tạo
Đáp án đúng: D

Câu 33. Khi thay target của `MutableCallSite`, API nào hỗ trợ đồng bộ hóa visibility giữa threads?
A. `SwitchPoint.syncAll(...)` xóa target của các call sites
B. `VolatileCallSite.syncAll(...)` cần gọi để hợp thức hóa volatile set
C. `MutableCallSite.syncAll(...)` publish target update cho threads
D. `ConstantCallSite.syncAll(...)` đồng bộ target bất biến
Đáp án đúng: C

Câu 34. So với `MutableCallSite`, `VolatileCallSite.setTarget` có ý nghĩa memory nào?
A. Đóng băng target thành hằng sau lần thay đổi đầu tiên
B. Việc thay target có volatile semantics khi threads quan sát
C. Xóa permanent bootstrap method khi target vừa cập nhật
D. Thay target chỉ có plain memory semantics, cần syncAll mới thấy
Đáp án đúng: B

Câu 35. Khi một `SwitchPoint` bị invalidate, guard tạo từ nó thường chọn nhánh nào?
A. Chọn original target và bỏ qua kết quả invalidateAll
B. Khởi chạy lại bootstrap method để tạo một call site mới
C. Chọn fallback target thay vì nhánh hợp lệ ban đầu
D. Xóa MethodHandle để next invoke báo NoSuchMethodError
Đáp án đúng: C

Câu 36. `MethodHandles.guardWithTest(test,target,fallback)` quyết định nhánh chạy bằng gì?
A. Giá trị return type của handle được chạy ở lần trước
B. Kiểu runtime class loader quyết định giữa target và fallback
C. Thứ tự mô tả trong BootstrapMethods attribute của JAR
D. Kết quả boolean từ `test` để chọn target hoặc fallback
Đáp án đúng: D

Câu 37. Thông thường `ClassLoader.loadClass(name)` khác `Class.forName(name)` về initialization thế nào?
A. `loadClass` chưa chạy static initializer; `Class.forName` có chạy
B. Cả hai tạo instance qua constructor mặc định trước khi trả Class
C. Cả hai thực thi class initializer với mỗi lần class được tìm
D. `loadClass` gọi static initializer; `Class.forName(String)` thì không
Đáp án đúng: A

Câu 38. Hai ClassLoader khác nhau định nghĩa class có cùng binary name; điều gì đúng về type identity?
A. JVM hợp nhất class chỉ dựa vào binary name giống nhau
B. Identity gồm binary name và defining loader nên type có thể khác nhau
C. JVM tự chọn instance mới nhất rồi gỡ type của loader trước
D. Hai class khác nhau chỉ khi source checksum của chúng khác
Đáp án đúng: B

Câu 39. Để định nghĩa class sinh động nhưng không muốn tra cứu theo binary name thông thường, API nào phù hợp?
A. `Class.forName` tạo hidden class dựa trên tên nội bộ
B. `ClassLoader.loadClass` sinh hidden class rồi tự gỡ khỏi package
C. `Proxy.newProxyInstance` định nghĩa concrete class ẩn độc lập
D. `Lookup.defineHiddenClass` tạo hidden class không tìm qua `Class.forName`
Đáp án đúng: D

Câu 40. Khi JVM verifier phát hiện bytecode class được định nghĩa có nội dung không hợp lệ, lỗi nào điển hình?
A. `NoSuchMethodError` vì bytecode chưa có BootstrapMethods attribute
B. `ClassNotFoundException` vì class đã được loader tìm thấy
C. `InvocationTargetException` do code chưa được invoke bằng reflection
D. `VerifyError` khi bytecode vi phạm ràng buộc kiểm chứng JVM
Đáp án đúng: D
