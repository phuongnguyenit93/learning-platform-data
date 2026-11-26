Câu 1. Điểm khác biệt chính giữa đặc tả JVM và HotSpot là gì?
A. Đặc tả quản lý native heap; HotSpot định nghĩa cú pháp Java.
B. Đặc tả yêu cầu dùng JIT; HotSpot định nghĩa tập bytecode hợp lệ.
C. Đặc tả định nghĩa hành vi JVM; HotSpot là một hiện thực.
D. Đặc tả yêu cầu dùng G1; HotSpot quy định bộ mã lệnh của JVM.
Đáp án đúng: C

Câu 2. Trong định dạng class file, bốn byte magic đầu tệp mang giá trị nào?
A. Giá trị `0xDEADBEEF` nhận diện định dạng Java class file.
B. Giá trị `0xFEEDFACE` nhận diện định dạng Java class file.
C. Giá trị `0x504B0304` nhận diện định dạng Java class file.
D. Giá trị `0xCAFEBABE` nhận diện định dạng Java class file.
Đáp án đúng: D

Câu 3. Vai trò của constant pool trong class file là gì?
A. Lưu danh sách Java thread và trạng thái monitor của JVM.
B. Lưu địa chỉ native của object đã cấp phát trong heap.
C. Lưu hằng số và symbolic references phục vụ liên kết class.
D. Lưu những vùng heap vừa được garbage collector đánh dấu.
Đáp án đúng: C

Câu 4. Muốn xem bytecode và metadata của một class đã biên dịch, lệnh nào phù hợp?
A. Dùng `jdeps -c -v Example` để xem bytecode và metadata.
B. Dùng `javap -c -v Example` để xem bytecode và metadata.
C. Dùng `jcmd -c -v Example` để xem bytecode và metadata.
D. Dùng `jlink -c -v Example` để xem bytecode và metadata.
Đáp án đúng: B

Câu 5. Với class loader áp dụng parent-first delegation, bước tìm class thường diễn ra thế nào?
A. Loader tìm class ở local path trước, rồi mới hỏi parent.
B. Loader thử parent trước, sau đó mới tự tìm và nạp class.
C. Loader tìm ngược từ cuối classpath mà không hỏi parent.
D. Loader chuyển việc nạp mọi class cho bootstrap loader.
Đáp án đúng: B

Câu 6. Trong vòng đời class, giai đoạn preparation khác initialization ở điểm nào?
A. Preparation gán mặc định static field; initialization chạy `<clinit>`.
B. Preparation xử lý `StackMapTable`; initialization gọi verifier.
C. Preparation thực thi `<clinit>`; initialization kiểm tra bytecode.
D. Preparation chạy constructor; initialization cấp phát constant pool.
Đáp án đúng: A

Câu 7. Lần đầu gọi static method bằng `invokestatic` trên class chưa khởi tạo, JVM phải làm gì?
A. Phải tạo một instance trước khi method static được chạy.
B. Static method chạy xong rồi class mới được khởi tạo.
C. Class được khởi tạo khi GC đầu tiên diễn ra sau lời gọi.
D. Class được khởi tạo trước khi static method thực thi.
Đáp án đúng: D

Câu 8. Bytecode verifier chủ yếu kiểm tra điều gì trong quá trình liên kết class?
A. Kiểm tra logic nhánh có đáp ứng yêu cầu nghiệp vụ.
B. Kiểm tra mọi public method đã có đầy đủ unit test.
C. Kiểm tra method có đạt mức latency trên CPU hiện tại.
D. Kiểm tra tính hợp lệ kiểu và stack trong bytecode.
Đáp án đúng: D

Câu 9. Một JVM frame được tạo cho mỗi lần gọi method để giữ dữ liệu nào?
A. Frame chứa local variables, operand stack và trạng thái method.
B. Frame chứa native memory của tất cả Java thread đang chạy.
C. Frame chứa object graph, vùng heap và GC roots toàn JVM.
D. Frame chứa class metadata của mọi class trong Metaspace.
Đáp án đúng: A

Câu 10. Đối với bytecode `iadd`, operand stack biến đổi thế nào?
A. Lấy hai giá trị long trên stack và đẩy kết quả cộng lên.
B. Lấy hai giá trị int trên stack và đẩy kết quả cộng lên.
C. Lấy hai tham chiếu object trên stack và nối chúng lại.
D. Lấy một giá trị int và một float rồi đẩy số double lên.
Đáp án đúng: B

Câu 11. Với một method instance được override, `invokevirtual` thường cho phép cơ chế nào?
A. Dispatch method dựa theo lớp runtime của receiver.
B. Dispatch method theo kiểu khai báo trong source code.
C. Dispatch constructor theo loại của return type.
D. Dispatch method tĩnh theo thứ tự các class loader.
Đáp án đúng: A

Câu 12. Trong local variables của JVM frame, kiểu nào chiếm hai slot theo đặc tả?
A. `int` và `float` dùng hai slot local variable.
B. `boolean` và `byte` dùng hai slot local variable.
C. `char` và object reference dùng hai slot local variable.
D. `long` và `double` dùng hai slot local variable.
Đáp án đúng: D

Câu 13. Lời gọi đệ quy không có điểm dừng có thể gây lỗi JVM nào?
A. `ClassCircularityError` khi method tự gọi qua invoke.
B. `VerifyError` khi bytecode có lời gọi đệ quy.
C. `StackOverflowError` khi không thể cấp thêm JVM stack frame.
D. `OutOfMemoryError: Metaspace` khi stack frame bị lặp.
Đáp án đúng: C

Câu 14. Trong mô hình bộ nhớ JVM, quan hệ nào đúng giữa heap và stack của Java thread?
A. Heap được chia sẻ; mỗi thread có JVM stack riêng.
B. Heap nằm riêng ở từng thread; JVM stack được chia sẻ.
C. Heap lưu operand stack; mỗi thread dùng chung call frame.
D. Heap và JVM stack đều là vùng nhớ chung của mọi thread.
Đáp án đúng: A

Câu 15. Trong HotSpot, Metaspace chủ yếu lưu loại thông tin nào?
A. Metadata của class trong native memory, khác Java heap.
B. Đối tượng business được tạo bởi lệnh `new` trên heap.
C. Local variables của các frame tại Java heap hiện tại.
D. Array data của object còn sống trong vùng young generation.
Đáp án đúng: A

Câu 16. Program counter (PC) register của mỗi Java thread dùng để làm gì?
A. Lưu toàn bộ local variables của method đang chạy.
B. Lưu kích thước heap đã cấp cho thread theo `-Xmx`.
C. Chứa các object reference dùng bởi garbage collector.
D. Theo dõi vị trí instruction JVM đang được thực thi.
Đáp án đúng: D

Câu 17. Trong HotSpot, Thread Local Allocation Buffer (TLAB) giúp ích điều gì?
A. Giảm số reference cần ghi vào local variable của frame.
B. Giảm tranh chấp khi nhiều thread cấp phát object mới.
C. Giảm số bytecode cần verifier kiểm tra khi load class.
D. Giảm kích thước class metadata giữ trong Metaspace.
Đáp án đúng: B

Câu 18. Khi phân tích khả năng thu gom object, nguồn nào thường được xem là GC root?
A. Object không được tham chiếu bởi stack và static field.
B. Tham chiếu từ stack đang hoạt động hoặc static field.
C. Giá trị primitive tạm thời trong operand stack.
D. Object đã trở thành unreachable sau lần GC gần nhất.
Đáp án đúng: B

Câu 19. Khi một object chỉ còn được tham chiếu qua `WeakReference`, điều gì có thể xảy ra?
A. Object thành strongly reachable vì WeakReference giữ địa chỉ.
B. GC giữ object sống tới khi gọi `System.gc()` thành công.
C. GC có thể xóa tham chiếu yếu khi object weakly reachable.
D. Object được chuyển sang Metaspace khi tạo weak reference.
Đáp án đúng: C

Câu 20. Ý tưởng cơ bản của generational garbage collection dựa vào điều gì?
A. GC chỉ quét static field và bỏ qua các object trong heap.
B. Object có tuổi cao được xóa ngay khi thread tạo nó kết thúc.
C. Nhiều object chết sớm, nên thu gom theo thế hệ có lợi.
D. Object được nhóm theo class loader thay vì theo tuổi đời.
Đáp án đúng: C

Câu 21. Trong HotSpot, G1 GC tổ chức heap để chọn khu vực thu gom theo cách nào?
A. G1 chia code cache thành young và old cho object.
B. G1 chia heap thành các stack riêng biệt cho từng Java thread.
C. G1 chia Metaspace thành vùng để giữ object sống lâu.
D. G1 chia heap thành region để chọn vùng thu gom phù hợp.
Đáp án đúng: D

Câu 22. Các option JVM `-Xms` và `-Xmx` điều chỉnh những giá trị nào?
A. Kích thước Metaspace ban đầu và Metaspace tối đa.
B. Kích thước code cache ban đầu và code cache tối đa.
C. Kích thước thread stack ban đầu và thread stack tối đa.
D. Kích thước heap ban đầu và heap tối đa tương ứng.
Đáp án đúng: D

Câu 23. Một cache static map giữ tham chiếu đến dữ liệu không còn cần thiết; GC sẽ thế nào?
A. Object còn reachable nếu static map vẫn tham chiếu nó.
B. Object được chuyển từ heap vào Metaspace để lưu trữ.
C. Object bị giải phóng ở mọi lần young GC diễn ra.
D. Object được dọn khi logic nghiệp vụ không còn dùng đến.
Đáp án đúng: A

Câu 24. Thông báo `OutOfMemoryError: Metaspace` trong HotSpot gợi ý nên kiểm tra gì?
A. Số class loader, class metadata và giới hạn Metaspace.
B. Số local variable slot dùng bởi thread đang chạy.
C. Số object nằm trong Eden và thời gian young GC.
D. Số record JDBC trong database và giới hạn connection pool.
Đáp án đúng: A

Câu 25. Vì sao HotSpot JIT thường biên dịch một method sau khi nó được gọi nhiều?
A. GC chọn method cần tối ưu theo số object đang còn sống.
B. Interpreter chỉ chạy bytecode không chứa branch instruction.
C. Profiling nhận diện mã nóng để tối ưu thực thi máy.
D. JVM buộc biên dịch native toàn bộ method ngay khi load.
Đáp án đúng: C

Câu 26. Với tiered compilation của HotSpot, C1 và C2 có vai trò gì?
A. Phối hợp các thế hệ heap trong quá trình thu gom G1.
B. Phối hợp các mức compile và tối ưu dựa vào profiling.
C. Phối hợp class loader bootstrap với class loader ứng dụng.
D. Phối hợp monitor enter với monitor exit khi cấp phát lock.
Đáp án đúng: B

Câu 27. JIT inlining có thể giúp một đoạn code Java chạy nhanh hơn nhờ điều gì?
A. Inlining đưa thân method vào caller, mở rộng cơ hội tối ưu.
B. Inlining thực thi method ở một thread CPU khác caller.
C. Inlining chuyển mọi object reference sang static final constant.
D. Inlining yêu cầu garbage collector xóa object vừa tạo.
Đáp án đúng: A

Câu 28. HotSpot deoptimization có thể xảy ra trong tình huống nào?
A. Thread đang chạy Java bytecode gọi một synchronized method.
B. Giả định tối ưu JIT không còn đúng khi runtime thay đổi.
C. GC tìm thấy object unreachable trong old generation.
D. Class file chứa giá trị `0xCAFEBABE` được verifier đọc.
Đáp án đúng: B

Câu 29. Khái niệm safepoint của HotSpot quan trọng với tác vụ nào?
A. Safepoint quyết định class nào có thể nạp từ constant pool.
B. Safepoint cho phép VM operation cần trạng thái thread ổn định.
C. Safepoint dùng để bắt đầu biên dịch native mọi method nóng.
D. Safepoint giữ monitor để chạy bytecode theo thứ tự toàn cục.
Đáp án đúng: B

Câu 30. Trong Java Memory Model, trường hợp nào tạo happens-before giữa hai thread?
A. Hai thread ghi field thông thường theo thứ tự thời gian.
B. Hai thread dùng cùng CPU core sẽ có happens-before.
C. Hai thread đọc cùng object là đủ để tạo happens-before.
D. Unlock monitor happens-before lần lock sau trên monitor đó.
Đáp án đúng: D

Câu 31. Với biến `volatile int counter`, nhận định nào đúng về câu lệnh `counter++`?
A. Phép tăng được bảo đảm atomicity vì trường là volatile.
B. Phép tăng không cho thread khác thấy thay đổi mới nhất.
C. Phép tăng gồm nhiều bước, nên chưa bảo đảm atomicity.
D. Phép tăng được JVM thay thành monitor lock ở mọi lần.
Đáp án đúng: C

Câu 32. Khi so sánh hiệu năng JVM sau thay đổi GC hoặc JIT, cách đo nào đáng tin cậy hơn?
A. Chỉ đo thời gian `javac` rồi suy ra latency khi chạy JVM.
B. Chỉ so kích thước class file trước và sau lần biên dịch.
C. Dùng benchmark có warm-up, nhiều lượt và quan sát GC/CPU.
D. Chạy một request đầu tiên rồi kết luận về throughput ổn định.
Đáp án đúng: C
