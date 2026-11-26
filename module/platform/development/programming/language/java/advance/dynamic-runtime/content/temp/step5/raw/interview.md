Bạn phân biệt liên kết tĩnh và liên kết động trong Java ở mức mã nguồn, bytecode và thời điểm runtime như thế nào?
Bạn sử dụng đối tượng `java.lang.Class` để khám phá cấu trúc một kiểu dữ liệu tại runtime bằng cách nào?
Bạn giải thích sự khác biệt giữa `Class.forName` và `ClassLoader.loadClass` về tải lớp và khởi tạo lớp ra sao?
Bạn thiết kế một custom class loader tuân theo cơ chế parent delegation để tránh nạp trùng các lớp nền tảng như thế nào?
Bạn phân biệt vai trò của `loadClass`, `findClass` và `defineClass` khi xây dựng cơ chế tải plugin ra sao?
Vì sao hai lớp có cùng tên đầy đủ nhưng được nạp bởi hai class loader khác nhau có thể không ép kiểu được cho nhau?
Bạn sử dụng thread context class loader để hỗ trợ `ServiceLoader` hoặc thư viện cần khám phá implementation động như thế nào?
Bạn tìm nguyên nhân một resource nằm trong JAR plugin nhưng không được class loader tìm thấy bằng cách nào?
Bạn tổ chức cơ chế nạp và cô lập phiên bản dependency cho nhiều plugin chạy chung trong một JVM ra sao?
Bạn kiểm soát tác dụng phụ của static initializer khi runtime tự động tải hoặc khởi tạo một lớp như thế nào?
Bạn xác định vì sao class loader không được thu hồi dù plugin đã ngừng hoạt động bằng cách nào?
Bạn thiết kế bộ nhớ đệm metadata theo lớp bằng `ClassValue` hoặc tham chiếu phù hợp để hạn chế rò rỉ class loader ra sao?
Bạn phân biệt `getMethods` và `getDeclaredMethods` khi truy vấn các phương thức công khai và phương thức khai báo trực tiếp như thế nào?
Bạn truy xuất một field private nằm trong lớp cha khi `getDeclaredField` trên lớp con không tìm thấy bằng cách nào?
Bạn xử lý thông tin generic type và type erasure khi đọc `Type`, `ParameterizedType` hoặc chữ ký phương thức tại runtime ra sao?
Bạn phát hiện và phân biệt phương thức bridge, synthetic với phương thức do lập trình viên khai báo trong API reflection như thế nào?
Bạn chọn chính xác một phương thức overload để gọi qua reflection dựa trên chữ ký tham số bằng cách nào?
Bạn phân biệt lỗi do thao tác reflection và ngoại lệ do phương thức đích ném ra qua `InvocationTargetException` như thế nào?
Bạn xây dựng thao tác tạo đối tượng qua `Constructor` và xử lý các trường hợp không có constructor không tham số ra sao?
Bạn xác minh annotation có thể đọc ở runtime và phân biệt ý nghĩa `@Retention` với `@Inherited` như thế nào?
Bạn giải thích vì sao `setAccessible(true)` có thể thất bại khi truy cập thành viên ở package không được mở trong JPMS ra sao?
Bạn xác định quyền truy cập mà `MethodHandles.Lookup` mang theo và cách quyền đó ảnh hưởng tới thao tác tìm handle như thế nào?
Bạn sử dụng `MethodHandles.privateLookupIn` để truy cập thành viên được cho phép giữa các module ra sao?
Bạn phân biệt `Lookup.findVirtual`, `findStatic` và `findConstructor` theo cách xác định mục tiêu và chữ ký lời gọi như thế nào?
Bạn biểu diễn kiểu trả về và danh sách kiểu tham số bằng `MethodType` cho một lời gọi động ra sao?
Bạn phân biệt `MethodHandle.invokeExact` và `invoke` về kiểm tra chữ ký và chuyển đổi kiểu tại lời gọi như thế nào?
Bạn điều tra `WrongMethodTypeException` khi gọi `MethodHandle` với chữ ký không khớp bằng cách nào?
Bạn lựa chọn `asType` hay `explicitCastArguments` khi cần điều chỉnh kiểu tham số của một method handle như thế nào?
Bạn dùng `bindTo` hoặc `insertArguments` để cố định receiver hay tham số trong một luồng xử lý động ra sao?
Bạn kết hợp `filterArguments`, `foldArguments` hoặc `guardWithTest` để tạo logic điều phối lời gọi động như thế nào?
Bạn chọn `asSpreader`, `asCollector` hoặc `asVarargsCollector` khi số lượng tham số được xác định muộn bằng cách nào?
Bạn giải thích tính bất biến của `MethodHandle` và cách thay đổi đích gọi thông qua `CallSite` như thế nào?
Bạn lấy `VarHandle` cho instance field, static field và phần tử mảng bằng những cơ chế lookup phù hợp nào?
Bạn sử dụng các chế độ `get`, `getOpaque`, `getAcquire` và `getVolatile` theo yêu cầu hiển thị bộ nhớ ra sao?
Bạn phân biệt `setRelease`, `setVolatile` và ghi thông thường qua `VarHandle` trong giao tiếp giữa các luồng như thế nào?
Bạn thiết kế cập nhật trạng thái đồng thời bằng `compareAndSet` hoặc `compareAndExchange` với `VarHandle` ra sao?
Bạn xử lý khả năng thất bại giả của các thao tác weak compare-and-set trên `VarHandle` như thế nào?
Bạn áp dụng `getAndAdd` hoặc thao tác đọc-sửa-ghi nguyên tử khác để thay thế khóa trong tình huống nào?
Bạn phát hiện và giải quyết vấn đề ABA khi thay đổi tham chiếu bằng các thao tác CAS như thế nào?
Bạn xác minh một kiểu field hoặc chế độ truy cập không được `VarHandle` hỗ trợ và xử lý lỗi gọi tương ứng ra sao?
Bạn phân biệt dynamic proxy chuẩn của JDK với cơ chế tạo subclass proxy về yêu cầu interface và khả năng chặn lời gọi như thế nào?
Bạn thiết kế `InvocationHandler` để định tuyến lời gọi và giữ đúng ngữ nghĩa của `equals`, `hashCode` và `toString` ra sao?
Bạn giải thích khi nào dynamic proxy có thể ném `UndeclaredThrowableException` và cách bảo toàn hợp đồng checked exception như thế nào?
Bạn lựa chọn class loader và các interface khi tạo proxy để tránh lỗi truy cập hoặc xung đột kiểu tại runtime ra sao?
Bạn xử lý lời gọi default method của interface thông qua `InvocationHandler.invokeDefault` trong tình huống phù hợp như thế nào?
Bạn xây dựng proxy dùng để ghi log hoặc kiểm tra phân quyền mà không làm thay đổi ngữ nghĩa trả về, ngoại lệ và thời gian sống tài nguyên ra sao?
Bạn quyết định dùng reflection, method handle hay dynamic proxy cho một cơ chế mở rộng dựa trên những ràng buộc nào?
Bạn giải thích vai trò của opcode `invokedynamic` khác với `invokevirtual` và `invokeinterface` ở quá trình liên kết lời gọi như thế nào?
Bạn mô tả trách nhiệm của bootstrap method khi JVM liên kết một vị trí gọi `invokedynamic` lần đầu ra sao?
Bạn phân biệt tham số bootstrap tĩnh, `MethodType` và `MethodHandles.Lookup` mà bootstrap nhận được như thế nào?
Bạn giải thích `CallSite` lưu đích lời gọi và mối liên hệ giữa `CallSite` với method handle như thế nào?
Bạn lựa chọn `ConstantCallSite`, `MutableCallSite` hoặc `VolatileCallSite` theo nhu cầu thay đổi đích và hiển thị giữa các luồng ra sao?
Bạn dùng `MutableCallSite.syncAll` để đồng bộ việc cập nhật các đích gọi động trong hệ thống đa luồng như thế nào?
Bạn thiết kế cơ chế vô hiệu hóa đường gọi đã tối ưu bằng `SwitchPoint` khi cấu hình runtime thay đổi ra sao?
Bạn xây dựng inline cache dựa trên kiểu của receiver để tăng tốc lời gọi động tại một call site như thế nào?
Bạn xử lý tình huống một call site trở nên megamorphic khiến cache theo kiểu không còn hiệu quả ra sao?
Bạn giải thích `LambdaMetafactory` hỗ trợ tạo lambda và method reference bằng cơ chế runtime như thế nào?
Bạn xác minh một biểu thức nối chuỗi được biên dịch sử dụng `invokedynamic` trong phiên bản JDK phù hợp bằng cách nào?
Bạn phân biệt `ConstantDynamic` trong constant pool với `invokedynamic` khi tạo giá trị và đích lời gọi theo yêu cầu như thế nào?
Bạn dùng `MethodHandles.Lookup.defineClass` hoặc `defineHiddenClass` trong các tình huống tạo lớp động khác nhau ra sao?
Bạn đánh giá vòng đời và khả năng khám phá theo tên của hidden class khi sinh implementation tại runtime như thế nào?
Bạn chuẩn bị bytecode hợp lệ về constant pool, stack và stack map frame trước khi định nghĩa lớp động bằng cách nào?
Bạn chẩn đoán `VerifyError` hoặc `ClassFormatError` phát sinh từ bytecode được tạo ở runtime ra sao?
Bạn sử dụng module layer và class loader để nạp những nhóm module mở rộng có quan hệ phụ thuộc riêng như thế nào?
Bạn phân biệt cô lập tên lớp bằng class loader với ranh giới bảo mật khi chạy mã plugin không đáng tin cậy ra sao?
Bạn hạn chế những rủi ro khi nhận tên lớp, tên phương thức hoặc tham số gọi động trực tiếp từ dữ liệu người dùng như thế nào?
Bạn đánh giá những thay đổi cần thiết khi chạy ứng dụng phụ thuộc reflection và dynamic proxy trong môi trường native image/AOT như thế nào?
Bạn đo chi phí reflection so với method handle và lời gọi trực tiếp bằng benchmark có warm-up và môi trường kiểm soát như thế nào?
Bạn thiết kế cache cho `Method`, `MethodHandle` và `CallSite` để giảm chi phí lookup mà vẫn cho phép class unloading ra sao?
Bạn đánh giá ảnh hưởng của việc thay đổi liên tục đích `CallSite` đối với khả năng tối ưu và khử tối ưu của JIT như thế nào?
Bạn sử dụng log class loading, Java Flight Recorder hoặc công cụ JVM để truy vết lớp được tải và class loader liên quan ra sao?
Bạn phân biệt `ClassNotFoundException`, `NoClassDefFoundError` và các lỗi liên kết khác trong pipeline tải lớp động như thế nào?
Bạn chẩn đoán một lời gọi hoạt động trên classpath nhưng thất bại trên module path do quyền truy cập reflection bằng cách nào?
Bạn tổ chức kiểm thử tích hợp cho cơ chế hot reload plugin nhằm phát hiện xung đột dependency, luồng còn sống và rò rỉ class loader ra sao?
Bạn xây dựng tiêu chí lựa chọn giữa tính linh hoạt runtime, độ an toàn kiểu, khả năng quan sát và chi phí bảo trì cho một framework Java như thế nào?
