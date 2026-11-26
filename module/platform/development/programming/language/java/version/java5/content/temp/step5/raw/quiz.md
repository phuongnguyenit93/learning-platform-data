Câu 1. Với `List<String> tags = new ArrayList<>();`, lệnh nào hợp lệ theo kiểm tra kiểu của compiler?
A. `tags.add(2.5)` vì double được ép ngầm sang String.
B. `tags.add("java")` thêm phần tử đúng kiểu String.
C. `tags.add(42)` vì Integer được autobox sang String.
D. `tags.add(new Object())` vì List nhận mọi Object.
Đáp án đúng: B

Câu 2. Vì sao `List<Integer>` không gán trực tiếp được cho biến kiểu `List<Number>`?
A. Generics của Java tự mở rộng List<Integer> thành List<Number>.
B. Integer không phải subtype của Number trong Java hiện đại.
C. List<Number> chỉ lưu Number, không lưu các subtype của Number.
D. Generics của Java bất biến theo tham số kiểu phần tử.
Đáp án đúng: D

Câu 3. Với `List<? extends Number> xs` chứa phần tử, thao tác nào an toàn về kiểu?
A. Đọc phần tử dưới kiểu `Number` mà không ép kiểu.
B. Thêm `Integer` mới vì nó kế thừa từ Number.
C. Thêm `Double` mới vì nó kế thừa từ Number.
D. Đọc phần tử thành `Integer` không cần ép kiểu.
Đáp án đúng: A

Câu 4. Với `List<? super Integer> xs`, nhận định nào đúng về thao tác đọc và ghi?
A. Có thể thêm Object; đọc phần tử an toàn dưới kiểu Integer.
B. Có thể thêm Number; đọc phần tử an toàn dưới kiểu Integer.
C. Có thể thêm Integer; đọc lại an toàn dưới kiểu Object.
D. Có thể thêm Double; đọc phần tử an toàn dưới kiểu Number.
Đáp án đúng: C

Câu 5. Với biến `Object obj`, biểu thức `instanceof` nào hợp lệ với generics ở Java hiện đại?
A. `obj instanceof List<String>` vì JVM giữ type argument String.
B. `obj instanceof List<Number>` vì generic type được reified.
C. Kiểm tra `obj instanceof List<?>` vì kiểu này reifiable.
D. `obj instanceof List<Integer>` vì JVM kiểm tra kiểu phần tử.
Đáp án đúng: C

Câu 6. Cú pháp nào khai báo một generic method hợp lệ trong Java?
A. `static <T> T id(T x) { return x; }` với tham số kiểu T.
B. `static T id<T>(T x) { return x; }` với tham số kiểu T.
C. `static T <T> id(T x) { return x; }` với tham số kiểu T.
D. `static <T> id(T x) { return x; }` với tham số kiểu T.
Đáp án đúng: A

Câu 7. Với `enum State { NEW, DONE }`, biểu thức nào lấy đúng hằng enum DONE?
A. `State.valueOf(1)` trả về `State.DONE`.
B. `State.valueOf("State.DONE")` trả về `State.DONE`.
C. `State.valueOf("DONE")` trả về `State.DONE`.
D. `State.values()[0]` trả về `State.DONE`.
Đáp án đúng: C

Câu 8. Với `enum Stage { START, RUN, END }`, `Stage.values()` trả thứ tự nào?
A. `END, RUN, START` theo thứ tự đảo của enum.
B. `RUN, START, END` vì giá trị giữa được ưu tiên.
C. Nhận `START, RUN, END` theo thứ tự khai báo.
D. `START, END, RUN` vì JVM sắp xếp theo chữ cái.
Đáp án đúng: C

Câu 9. Để tạo tập `EnumSet<Permission>` rỗng, cách nào phù hợp?
A. `EnumSet.none(Permission.class)` tạo tập enum rỗng.
B. `EnumSet.empty(Permission.class)` tạo tập enum rỗng.
C. `EnumSet.of(Permission.class)` tạo tập enum rỗng.
D. Dùng `EnumSet.noneOf(Permission.class)` tạo tập rỗng.
Đáp án đúng: D

Câu 10. Với `enum Status { NEW, DONE }`, cách nào tạo map dùng khóa Status?
A. `new EnumMap<Status, String>(String.class)` tạo enum map.
B. `new EnumMap<Status, String>(Status.values())` tạo enum map.
C. `new EnumMap<Status, String>(Status.DONE)` tạo enum map.
D. `new EnumMap<Status, String>(Status.class)` tạo enum map.
Đáp án đúng: D

Câu 11. Annotation `@Override` giúp compiler phát hiện tình huống nào?
A. Method được đánh dấu nhưng không override hợp lệ.
B. Method được đánh dấu nhưng thiếu phương thức main.
C. Method được đánh dấu nhưng chưa có access modifier.
D. Method được đánh dấu nhưng chưa khai báo synchronized.
Đáp án đúng: A

Câu 12. Để annotation có thể truy vấn bằng reflection lúc runtime, dùng meta-annotation nào?
A. Dùng `@Retention(RetentionPolicy.RUNTIME)` để đọc runtime.
B. `@Retention(RetentionPolicy.DEFAULT)` bật reflection runtime.
C. `@Retention(RetentionPolicy.CLASS)` cho phép query runtime.
D. `@Retention(RetentionPolicy.SOURCE)` giữ annotation khi chạy.
Đáp án đúng: A

Câu 13. Muốn giới hạn annotation chỉ được áp dụng lên khai báo phương thức, dùng khai báo nào?
A. `@Target(ElementType.TYPE)` giới hạn nơi sử dụng annotation.
B. `@Target(ElementType.FIELD)` giới hạn nơi sử dụng annotation.
C. `@Target(ElementType.METHOD)` giới hạn nơi sử dụng annotation.
D. `@Target(ElementType.PARAMETER)` giới hạn nơi sử dụng annotation.
Đáp án đúng: C

Câu 14. Tác dụng phù hợp của `@SuppressWarnings("unchecked")` là gì?
A. Đổi unchecked cast thành kiểm tra kiểu khi runtime.
B. Ẩn cảnh báo unchecked, không đổi an toàn kiểu.
C. Tự thêm kiểm tra runtime cho từng generic cast.
D. Buộc compiler chuyển cảnh báo raw type thành lỗi.
Đáp án đúng: B

Câu 15. Enhanced for-each `for (T item : source)` hỗ trợ nguồn thuộc nhóm nào?
A. Đối tượng có `get(int)` và `size()` dù thiếu Iterable.
B. Mảng hoặc instance của kiểu `Iterable`.
C. Mảng hoặc đối tượng có `iterator()`, dù thiếu Iterable.
D. Các `Collection` nhưng không hỗ trợ array.
Đáp án đúng: B

Câu 16. Với `Integer value = null; int n = value;`, kết quả tại thời điểm gán cho n là gì?
A. Gán `0` cho n vì wrapper Integer mang null.
B. Bỏ qua phép gán và giữ giá trị mặc định của n.
C. Đổi n thành kiểu Integer để chứa được null.
D. Ném `NullPointerException` khi unboxing giá trị null.
Đáp án đúng: D

Câu 17. Khi cần so giá trị hai biến `Integer a` và `Integer b` không null, cách nào đáng tin cậy?
A. Dùng `a.equals(b)` để so giá trị số được bao gói.
B. Dùng `System.identityHashCode(a) == System.identityHashCode(b)`.
C. Dùng `a == b` vì wrapper luôn so giá trị số.
D. Dùng `a.getClass() == b.getClass()` để so giá trị số.
Đáp án đúng: A

Câu 18. Khai báo nào hợp lệ cho method nhận tên nhóm và số lượng phần tử int biến đổi?
A. `void log(String name, ...int nums)` khai báo varargs.
B. `void log(int... nums, String name)` đặt varargs đầu.
C. `void log(String name, int.. nums)` khai báo varargs.
D. `void log(String name, int... nums)` có varargs cuối.
Đáp án đúng: D

Câu 19. Với `ExecutorService pool` và `Callable<Integer> task`, `pool.submit(task)` trả về kiểu gì?
A. `RunnableFuture<Void>` cho mọi callable có kết quả.
B. `Integer` là kết quả đã chờ tới khi task chạy xong.
C. `Future<Integer>` chứa kết quả task trả về sau này.
D. `Thread` đại diện cho thread chạy Callable task.
Đáp án đúng: C

Câu 20. Khác biệt thực tế nào giữa `Callable<T>` và `Runnable` khi triển khai task?
A. `Runnable.run()` bắt buộc khai báo throws Exception.
B. `Callable.call()` không thể trả về giá trị từ task.
C. `Callable.call()` trả T và có thể ném checked exception.
D. `Runnable.run()` trả T và có thể ném checked exception.
Đáp án đúng: C

Câu 21. Với `Future<Integer> f` của task đang chạy, `f.get()` có hành vi nào?
A. Trả về Integer ngay cả khi task chưa bắt đầu thực thi.
B. Có thể chờ và báo `ExecutionException` khi task lỗi.
C. Chạy lại Callable trên chính thread đang gọi get.
D. Luôn trả null khi task kết thúc bằng exception.
Đáp án đúng: B

Câu 22. Lời gọi `future.cancel(true)` với task đang chạy có ý nghĩa nào?
A. Buộc task kết thúc tức thời bất kể mã có xử lý interrupt.
B. Khởi chạy lại task nếu nó đã hoàn thành trước đó.
C. Chờ task hoàn thành rồi mới đánh dấu đã hủy.
D. Có thể yêu cầu ngắt task nhưng không bảo đảm task dừng.
Đáp án đúng: D

Câu 23. `ExecutorService.shutdown()` có ý nghĩa nào đối với task đã và chưa submit?
A. Dừng ngay mọi task đang chạy và xóa dữ liệu Future.
B. Cho phép nhận task mới cho tới khi executor hết thread.
C. Ngừng nhận task mới, task cũ vẫn có thể tiếp tục chạy.
D. Chờ mọi task hoàn tất rồi tự gọi shutdownNow.
Đáp án đúng: C

Câu 24. Khi dùng `ReentrantLock`, mẫu quản lý lock nào giảm nguy cơ không unlock do exception?
A. Chỉ gọi `unlock()` khi khối xử lý trả về true.
B. Dùng `try`/`finally` để `unlock()` kể cả khi lỗi.
C. Đợi GC thu hồi lock thay cho lời gọi unlock.
D. Khóa rồi dùng `try`/`catch` và bỏ `unlock()`.
Đáp án đúng: B

Câu 25. Khi `ReentrantLock.tryLock()` không tham số được gọi lúc lock đang do thread khác giữ, điều gì đúng?
A. Buộc thread khác nhả lock rồi trả `true`.
B. Thường trả `false` ngay thay vì chờ lấy lock.
C. Chờ tới khi thread đang giữ lock gọi unlock.
D. Ném `IllegalMonitorStateException` để báo đang bận.
Đáp án đúng: B

Câu 26. Với `AtomicInteger counter`, kết quả của `counter.incrementAndGet()` là gì?
A. Tăng giá trị một cách atomic rồi trả số mới.
B. Trả số cũ rồi mới tăng một cách atomic.
C. Tạo AtomicInteger khác và giữ nguyên counter.
D. Tăng giá trị nhưng yêu cầu giữ ReentrantLock.
Đáp án đúng: A

Câu 27. Theo Java Memory Model, một write vào biến `volatile` và read tiếp theo của cùng biến có quan hệ nào?
A. Read luôn thấy toàn bộ biến local của thread ghi.
B. Ghi volatile happens-before lần đọc sau của cùng biến.
C. Write không có tác động visibility giữa các thread.
D. Write tự biến mọi thao tác compound thành atomic.
Đáp án đúng: B

Câu 28. Với `volatile int count`, tại sao `count++` vẫn có nguy cơ mất cập nhật khi nhiều thread?
A. Volatile chỉ làm việc với reference, không dùng được cho int.
B. Phép tăng gồm đọc, tính và ghi, không atomic như một bước.
C. JVM vô hiệu hóa phép cộng khi count mang volatile.
D. Phép tăng tự đồng bộ nhưng các thread có thể bỏ qua nhau.
Đáp án đúng: B

Câu 29. Quan hệ happens-before nào được bảo đảm qua `synchronized` trên cùng monitor?
A. Thread không vào block đồng bộ vẫn thấy dữ liệu mới.
B. Mọi thao tác đọc được sắp xếp lại giữa các block.
C. Các thread dùng monitor khác nhau có thứ tự cố định.
D. Unlock monitor happens-before lần lock tiếp theo.
Đáp án đúng: D

Câu 30. Với `CountDownLatch latch = new CountDownLatch(3);`, `latch.await()` giải phóng khi nào?
A. Sau khi số đếm giảm về 0 nhờ các lần `countDown()`.
B. Sau khi executor gọi shutdown dù count vẫn dương.
C. Sau khi có ba thread tạo mới instance của CountDownLatch.
D. Sau khi một thread gọi countDown bất kể số đếm.
Đáp án đúng: A

Câu 31. Với `BlockingQueue<String>` có dung lượng cố định đã đầy, `put("x")` thông thường làm gì?
A. `put("x")` chờ khi queue đầy cho tới lúc còn chỗ.
B. Xóa phần tử đầu rồi đưa x vào để tránh chờ.
C. Tạo queue mới có dung lượng gấp đôi rồi thêm x.
D. Trả `false` ngay khi queue không còn chỗ trống.
Đáp án đúng: A

Câu 32. Với `ConcurrentHashMap<K,V> map`, `putIfAbsent(key, val)` có hành vi nào?
A. Thay val dù key đã có giá trị khác null.
B. Chuyển map thành immutable sau lần thêm đầu.
C. Chờ mọi thread dừng rồi xóa key trước khi ghi.
D. `putIfAbsent` ghi atomic nếu key chưa có giá trị.
Đáp án đúng: D
