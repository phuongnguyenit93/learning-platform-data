Câu 1. Trong siêu lập trình, trường hợp nào minh họa việc sinh mã tại compile time?
A. Reflection truy vấn field khi ứng dụng đang thực thi.
B. Dynamic proxy định tuyến lời gọi method trong runtime.
C. Class loader tải class khi ứng dụng yêu cầu sử dụng.
D. Processor sinh source trước khi biên dịch kết thúc.
Đáp án đúng: D

Câu 2. Khi phân tích biểu thức nguồn, AST khác chuỗi token ở khả năng nào?
A. AST lưu bytecode đã được CPU thực thi từ source.
B. AST giữ cấu trúc cú pháp và thứ bậc các toán tử.
C. AST thực thi code để thu được giá trị ở runtime.
D. AST ghi lại lịch phân bổ bộ nhớ của tiến trình.
Đáp án đúng: B

Câu 3. Vì sao phép tối ưu AST thay `compute() * 0` bằng `0` có thể không tương đương?
A. Compute có thể gây side effect hoặc phát sinh exception.
B. Hằng số 0 cho phép xóa mọi phép toán trước khi đánh giá.
C. Compiler vẫn thực thi compute sau khi thay toàn biểu thức.
D. Lời gọi không tham số sẽ được compiler coi là thuần.
Đáp án đúng: A

Câu 4. Khi macro tạo biến tạm trùng tên biến của code gọi, lỗi thiết kế thường được gọi là gì?
A. Deadlock xảy ra do các đoạn code giữ cùng monitor.
B. Type erasure làm mất generic argument lúc chạy.
C. Race xảy ra do lexer và parser cùng đọc token.
D. Tên biến macro sinh có thể bắt nhầm binding của caller.
Đáp án đúng: D

Câu 5. Với macro có cơ chế hygiene, lợi ích chính khi mở rộng mã là gì?
A. Cho mọi biểu thức macro được thực thi trên một thread riêng.
B. Giảm va chạm binding giữa tên sinh ra và tên tại nơi dùng.
C. Bỏ qua bước kiểm tra cú pháp sau khi mở rộng biểu thức.
D. Chuyển kết quả macro thành bytecode bất kể ngôn ngữ nguồn.
Đáp án đúng: B

Câu 6. Trong Java reflection, `Class.getDeclaredMethods()` trả về nhóm method nào?
A. Method khai báo ngay tại class, gồm cả non-public.
B. Các method của interface được nạp cùng với class.
C. Các public method của class và của superclass.
D. Các public static method tại class đang được đọc.
Đáp án đúng: A

Câu 7. Khi cần tra cứu public method kế thừa từ superclass, thao tác reflection nào phù hợp?
A. Dùng `Constructor.newInstance` để tìm tên method kế thừa.
B. Dùng `Class.getDeclaredMethod` trên subclass để tìm method kế thừa.
C. Dùng `Class.getMethod(name, parameterTypes)` để tìm method.
D. Dùng `Field.get` trên đối tượng để truy cập public method.
Đáp án đúng: C

Câu 8. Khi package của module khác không `opens` cho caller, `setAccessible(true)` trên private member có thể thế nào?
A. setAccessible đổi private thành protected trong bytecode.
B. Có thể bị từ chối vì package chưa mở cho caller.
C. setAccessible tự mở package sau khi gọi thành công.
D. setAccessible tạo public member mới để truy cập.
Đáp án đúng: B

Câu 9. Muốn annotation Java xuất hiện khi kiểm tra bằng reflection tại runtime, khai báo retention nào?
A. `@Retention(RetentionPolicy.RUNTIME)` giữ metadata khi chạy.
B. `@Retention(RetentionPolicy.CLASS)` bật runtime reflection.
C. `@Retention(RetentionPolicy.SOURCE)` giữ metadata khi chạy.
D. `@Retention(RetentionPolicy.DEFAULT)` bật runtime reflection.
Đáp án đúng: A

Câu 10. Muốn giới hạn annotation áp dụng lên khai báo method, meta-annotation nào phù hợp?
A. `@Target(ElementType.PARAMETER)` quy định nơi dùng annotation.
B. `@Target(ElementType.FIELD)` quy định nơi dùng annotation.
C. `@Target(ElementType.TYPE)` quy định nơi dùng annotation.
D. `@Target(ElementType.METHOD)` quy định nơi dùng annotation.
Đáp án đúng: D

Câu 11. Với `@Inherited` trên annotation Java được giữ ở runtime, trường hợp nào kế thừa annotation theo cơ chế này?
A. Field trùng tên kế thừa annotation từ superclass.
B. Subclass có thể kế thừa annotation trên superclass.
C. Annotation của method override truyền sang method con.
D. Class implement kế thừa annotation từ interface.
Đáp án đúng: B

Câu 12. Một JSR 269 annotation processor chạy ở giai đoạn nào của vòng đời Java?
A. Processor chạy khi object annotated được tạo lúc runtime.
B. Processor chạy khi garbage collector quét heap.
C. Processor đọc element và sinh code trong lúc biên dịch.
D. Processor chạy khi class loader tạo dynamic proxy.
Đáp án đúng: C

Câu 13. Vì sao annotation processor có thể được gọi nhiều round trong một lần biên dịch?
A. JVM của compiler cần restart khi sinh tệp mới.
B. Compiler tạo một OS process cho mỗi annotated class.
C. Round sau chạy khi nguồn ban đầu có syntax error.
D. Source mới tạo thêm element ở round xử lý tiếp.
Đáp án đúng: D

Câu 14. Trong JSR 269, `Filer.createSourceFile` phục vụ việc gì?
A. Sinh tệp Java source mới trong vòng annotation processing.
B. Nạp một class compiled vào bộ nhớ ứng dụng khi chạy.
C. Ghi bytecode một class đang chạy xuống file trên đĩa.
D. Thay nội dung source gốc trên cùng đường dẫn lúc biên dịch.
Đáp án đúng: A

Câu 15. Với API chuẩn JSR 269, việc nào nằm ngoài hợp đồng xử lý annotation thông thường?
A. Phát sinh tệp source mới qua Filer trong compiler.
B. Báo lỗi tại element thông qua API Messager.
C. Đọc thông tin element compiler đưa tới processor.
D. Thay trực tiếp AST của source bằng API JSR 269.
Đáp án đúng: D

Câu 16. Khi thiết kế annotation processor sinh code, việc gì giúp bản build tái lập ổn định?
A. Duyệt HashMap theo thứ tự không ổn định để sinh tên.
B. Lấy dữ liệu ngẫu nhiên làm thứ tự các file được sinh.
C. Thêm timestamp runtime vào tên class sinh ra.
D. Sinh cùng output từ cùng input và cấu hình đã chọn.
Đáp án đúng: D

Câu 17. Trong Java, dynamic proxy chuẩn `java.lang.reflect.Proxy` có giới hạn mô hình nào?
A. Sửa bytecode class gốc trước khi class loader tải.
B. Tạo proxy cho abstract class không có interface.
C. Proxy triển khai interface mà không subclass class đích.
D. Tạo subclass cho các concrete class chưa đánh dấu final.
Đáp án đúng: C

Câu 18. Với JDK dynamic proxy, `InvocationHandler.invoke` nhận thông tin nào?
A. Nhận tên thread, stack trace và bytes của class.
B. Nhận proxy, Method được gọi và mảng arguments.
C. Nhận annotations, compiler và các processing round.
D. Nhận class loader, Constructor và tập các field.
Đáp án đúng: B

Câu 19. Nếu handler của JDK dynamic proxy ném checked exception không được interface method khai báo, hành vi nào đúng?
A. Compiler tự biên dịch lại interface để bổ sung checked exception.
B. Lời gọi proxy bỏ exception và trả giá trị mặc định.
C. Lời gọi proxy bọc lỗi trong `UndeclaredThrowableException`.
D. JVM tự thêm exception đó vào throws của interface method.
Đáp án đúng: C

Câu 20. Với `MethodHandle.invokeExact`, yêu cầu nào quan trọng khi thực hiện lời gọi?
A. invokeExact chạy processor để tìm method đích.
B. invokeExact tự ép các đối số thành String khi gọi.
C. Kiểu tại call site cần khớp MethodType của handle.
D. invokeExact tự mở quyền private của Java module.
Đáp án đúng: C

Câu 21. Khi dùng `MethodHandles.lookup()`, quyền truy cập thành viên được xác định theo nguyên tắc nào?
A. Lookup bỏ qua giới hạn truy cập từ Java module.
B. Lookup truy cập được các method thuộc Object.
C. Lookup mở package để truy cập member private.
D. Lookup dùng quyền theo ngữ cảnh của class đang gọi.
Đáp án đúng: D

Câu 22. Khi dùng reflection với field khai báo `List<String>`, phát biểu nào chính xác về generics?
A. Đọc được generic signature, không xác minh kiểu phần tử.
B. Field.getType trả kiểu List<String> reified tại runtime.
C. JVM giữ tham số generic thực tế trên từng item khi chạy.
D. Reflection kiểm tra các item trong List là String.
Đáp án đúng: A

Câu 23. Java instrumentation agent muốn nhận `Instrumentation` trước khi main ứng dụng chạy dùng entry point nào?
A. Khai báo `main` và gọi thủ công mỗi khi class được load.
B. Khai báo `invoke` trên InvocationHandler để nạp agent.
C. Khai báo `premain` và cấu hình agent khi khởi động JVM.
D. Khai báo `process` trong annotation processor để gắn agent.
Đáp án đúng: C

Câu 24. `ClassFileTransformer` trong Java instrumentation được dùng chủ yếu để làm gì?
A. Có thể thay bytes của class trong quá trình nạp lớp.
B. Thay instance đang chạy bằng object của class mới.
C. Thay đổi module descriptor của mọi module trong JVM.
D. Biến đổi source Java thành AST tại mỗi lần gọi hàm.
Đáp án đúng: A

Câu 25. Khi công cụ tạo bytecode làm sai stack map frame, lỗi nào thường được JVM phát hiện?
A. `TimeoutException` khi method được gọi quá nhiều lần.
B. `VerifyError` khi bytecode không vượt qua bước xác minh.
C. `IOException` khi method có nhiều local variable hơn.
D. `SQLException` khi JVM không đọc được metadata của class.
Đáp án đúng: B

Câu 26. Khi thêm lời gọi theo dõi vào giữa một method bằng biến đổi bytecode, điều gì phải được bảo toàn?
A. Giữ nguyên byte offset của từng instruction gốc.
B. Duy trì tính hợp lệ của control flow và stack map.
C. Giữ nguyên kích thước class file sau mỗi biến đổi.
D. Giữ tên biến local giống mã source ban đầu.
Đáp án đúng: B

Câu 27. Trong Java class loading mặc định, parent delegation có tác dụng chính nào?
A. Ép mọi plugin chạy trong một class loader dùng chung.
B. Bảo đảm class do child nạp luôn dùng parent làm superclass.
C. Thử nạp bằng parent trước để hạn chế định nghĩa class trùng.
D. Cho child loader được phép thay toàn bộ class thư viện chuẩn.
Đáp án đúng: C

Câu 28. Hai class có cùng fully qualified name nhưng do hai class loader độc lập định nghĩa được JVM xem thế nào?
A. Tương đương nếu cùng package dù loader thuộc hai module.
B. Tương đương nếu hai loader chạy trong một JVM version.
C. Khác kiểu vì defining class loader khác nhau.
D. Tương đương nếu class file có nội dung bytecode y hệt.
Đáp án đúng: C

Câu 29. Khi plugin được unload nhưng class loader vẫn còn reachable từ ThreadLocal, hậu quả nào có thể xảy ra?
A. Reference từ ThreadLocal có thể giữ loader sống.
B. JVM buộc dừng thread sau khi plugin được unload.
C. Loader được dọn ngay dù còn reachable từ ThreadLocal.
D. Instance chuyển sang bootstrap loader để tiếp tục.
Đáp án đúng: A

Câu 30. Với API reflection trong vòng lặp rất nóng, hướng đánh giá hiệu năng nào phù hợp?
A. Giả định reflective invocation nhanh hơn direct call trong mọi trường hợp.
B. Mỗi lần gọi lại tìm Method để tránh cache không cập nhật.
C. Dùng reflection để tránh kiểm tra quyền truy cập ở runtime.
D. Đo benchmark thực tế, cache metadata nếu có ích và an toàn.
Đáp án đúng: D

Câu 31. Khi sinh source code từ metadata không đáng tin cậy, rủi ro thiết kế nào cần kiểm soát?
A. Input có thể làm thay đổi cú pháp và chèn logic ngoài ý muốn.
B. Tạo class qua annotation processor đồng nghĩa code là đáng tin.
C. Compiler tự loại bỏ mọi biểu thức nguy hiểm trong source sinh.
D. Tên field đầu vào tự được escape như chuỗi Java hợp lệ.
Đáp án đúng: A

Câu 32. Vì sao custom class loader không đủ làm sandbox bảo mật cho plugin không đáng tin?
A. Loader sinh process riêng với quyền hệ điều hành hạn chế.
B. Class loader không cô lập quyền tài nguyên của process.
C. JVM chặn toàn bộ tài nguyên khi nạp từ custom loader.
D. Loader tách riêng file system và mạng cho từng class.
Đáp án đúng: B
