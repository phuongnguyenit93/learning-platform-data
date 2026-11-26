Câu 1. Cho `record Point(int x, int y) {}` và `Object o = new Point(2, 3);`, mẫu `o instanceof Point(int a, int b)` có kết quả nào?
A. Không hợp lệ vì record pattern chỉ dùng trong switch.
B. Không khớp vì biến `o` có kiểu compile-time Object.
C. Khớp và có `a = 2`, `b = 3` theo thành phần record.
D. Khớp và bind `a = 3`, `b = 2` theo thứ tự đảo.
Đáp án đúng: C

Câu 2. Với `record Point(int x,int y){}` và `record Pair(Point a,Point b){}`, nested record pattern nào bóc tách hai Point?
A. `case Pair(Point(var x,var y),Point(var z,var t)) -> x + t;`.
B. `case Pair(Point.getX(),Point.getY()) -> x + t;` để lấy dữ liệu.
C. `case Pair[Point(var x,var y),Point(var z,var t)] -> x + t;`.
D. `case Pair(Point(x,y),Point(z,t)) -> x + t;` khi chưa khai báo biến.
Đáp án đúng: A

Câu 3. Với `record Point(int x, int y){}`, khi viết `if (obj instanceof Point(var x,var y))`, `var` mang vai trò gì?
A. Đổi kiểu record component sang Object ở thời điểm chạy.
B. Tạo hai field mới x và y bên trong class Point.
C. Yêu cầu Point phải được khai báo dưới dạng generic.
D. Suy ra kiểu biến x và y từ kiểu các record component.
Đáp án đúng: D

Câu 4. Với `record Box(String value) {}`, `Box(null)` được xét bằng `case Box(String s)` thì điều gì đúng?
A. Pattern ném ClassCastException do value bị null.
B. Pattern khớp và s trở thành chuỗi ký tự `null`.
C. Pattern khớp và s được bind bằng một String null.
D. Pattern không khớp vì thành phần value là null.
Đáp án đúng: D

Câu 5. Trong Java 21, guard hợp lệ nào kiểm tra chuỗi không rỗng ở nhánh pattern switch?
A. `case String s where !s.isEmpty() -> use(s);`.
B. `case String s when !s.isEmpty() -> use(s);`.
C. `case String s && !s.isEmpty() -> use(s);`.
D. `case String s if !s.isEmpty() -> use(s);`.
Đáp án đúng: B

Câu 6. Với switch trên Object, vì sao đặt `case Object o` trước `case String s` không hợp lệ?
A. Case String bắt buộc dùng default thay vì type pattern.
B. Object không thể xuất hiện làm type pattern trong switch.
C. Case String ưu tiên chạy trước bất kể thứ tự nhãn case.
D. Case Object bao phủ String nên nhánh sau bị dominance.
Đáp án đúng: D

Câu 7. Trong pattern switch Java 21, cách nào xử lý trực tiếp selector có giá trị null?
A. Thêm `case Void v -> ...` để nhận selector null.
B. Chỉ dùng `default -> ...` vì default cũng bắt null.
C. Dùng `case Object x -> ...` để tự bind x bằng null.
D. `case null -> ...` nhận trực tiếp selector bằng null.
Đáp án đúng: D

Câu 8. Với sealed interface chỉ có hai subtype trực tiếp A và B, switch pattern khi nào có thể bỏ default?
A. Khi A và B có constructor không tham số giống nhau.
B. Khi các case phủ đủ A và B để switch exhaustive.
C. Khi switch dùng arrow rule thay vì nhãn colon.
D. Khi A và B đều là class public bất kể nhãn case.
Đáp án đúng: B

Câu 9. Với `case Integer n when n > 0 -> "P"; case Integer n -> "N";`, số -2 đi nhánh nào?
A. Không có nhánh nào vì mọi Integer phải là số dương.
B. Nhánh thứ nhất vì Integer đã khớp kiểu trước guard.
C. Nhánh Integer thứ hai vì guard trên -2 không thỏa.
D. Cả hai nhánh và kết quả sau được nối vào trước.
Đáp án đúng: C

Câu 10. Trong switch expression, block `case Integer n -> { ... }` trả giá trị bằng gì?
A. Dùng `yield value;` bên trong block để cấp kết quả.
B. Dùng `case value;` bên trong block để cấp kết quả.
C. Dùng `break value;` bên trong block để cấp kết quả.
D. Dùng `continue value;` bên trong block để cấp kết quả.
Đáp án đúng: A

Câu 11. Với `if (obj instanceof String s && s.length() > 2)`, vì sao `s` được dùng ở vế phải?
A. Biến s có phạm vi toàn method ngay khi compiler gặp if.
B. Vế phải tự ép obj thành String mà không cần xét instanceof.
C. Vì `&&` xét vế phải khi pattern bên trái khớp.
D. Toán tử && chạy hai vế song song và đồng bộ biến s.
Đáp án đúng: C

Câu 12. Nếu `switch (obj)` theo pattern không có `case null` và obj là null, kết quả thường là gì?
A. Đi vào default như mọi giá trị không khớp case.
B. Chọn nhánh Object vì null là một instance của Object.
C. Ném NullPointerException khi selector là null.
D. Trả null tự động khi switch dùng kiểu biểu thức.
Đáp án đúng: C

Câu 13. Với `List<String> xs = new ArrayList<>(List.of("a","b"));`, cặp `xs.getFirst(), xs.getLast()` là gì?
A. `"a", "b"` theo thứ tự đầu và cuối danh sách.
B. `"b", "b"` vì getFirst trả phần tử cuối cùng.
C. `"a", "a"` vì getLast trả phần tử đầu tiên.
D. `"b", "a"` vì List mặc định đảo encounter order.
Đáp án đúng: A

Câu 14. Với ArrayList `xs = ["a","b","c"]`, gọi `xs.reversed().set(0,"x")` làm gì?
A. Ném lỗi vì reversed view luôn không cho phép sửa.
B. Thay `"c"` ở cuối xs bởi `"x"` qua reversed view.
C. Không thay xs vì reversed tạo một List độc lập.
D. Thay phần tử đầu của xs bằng `"x"` qua reversed copy.
Đáp án đúng: B

Câu 15. Với LinkedHashSet có thứ tự `a,b,c`, gọi `addFirst("c")` dẫn tới thứ tự nào?
A. `a,c,b` vì c được chuyển lên vị trí đứng giữa.
B. `a,b,c` vì giá trị c đã tồn tại nên không thay đổi.
C. `c,a,b` do c được chuyển về đầu encounter order.
D. `c,b,a` vì toàn bộ Set được đảo ngay khi thêm.
Đáp án đúng: C

Câu 16. Với LinkedHashMap có các khóa `a,b,c`, gọi `putFirst("c", 3)` làm thay đổi thứ tự khóa thế nào?
A. `a,b,c` vì ghi lại khóa c không thể thay đổi thứ tự.
B. `c,a,b` vì khóa c được đưa lên đầu thứ tự duyệt.
C. `a,c,b` vì putFirst chèn c sau khóa đầu tiên.
D. `c,b,a` vì putFirst đảo toàn bộ thứ tự của map.
Đáp án đúng: B

Câu 17. Trên `SequencedMap<K,V> map`, phương thức nào lấy entry ở đầu encounter order?
A. `map.firstEntry()` lấy entry đầu theo encounter order.
B. `map.entrySet().getFirst()` trả entry đầu của HashSet.
C. `map.peekFirst()` trả entry đầu mà không thay đổi map.
D. `map.getFirst()` trả entry đầu dưới kiểu Map.Entry.
Đáp án đúng: A

Câu 18. Nếu `SequencedMap` có thứ tự khóa `a,b,c`, `map.reversed().firstEntry()` chọn gì?
A. Entry của khóa `b`, phần tử giữa trong map gốc.
B. Entry của khóa `a`, phần tử đầu trong map gốc.
C. Giá trị null vì reversed không hỗ trợ firstEntry.
D. Entry của khóa `c`, phần tử cuối trong map gốc.
Đáp án đúng: D

Câu 19. Kết quả của `List.of("p","q").reversed().getFirst()` trên JDK 21+ là gì?
A. `null` vì reversed chỉ áp dụng cho mutable List.
B. `"p"` vì reversed vẫn đọc từ đầu List gốc.
C. `"q"` vì reversed view có encounter order đảo.
D. Ném lỗi vì List.of không hỗ trợ SequencedCollection.
Đáp án đúng: C

Câu 20. Gọi `getFirst()` trên một `ArrayList` rỗng sẽ thế nào?
A. Ném NoSuchElementException khi danh sách rỗng.
B. Trả null vì không có phần tử đầu trong danh sách.
C. Trả Optional.empty để tránh trường hợp danh sách rỗng.
D. Tạo một phần tử mặc định và trả về phần tử đó.
Đáp án đúng: A

Câu 21. Trong Java 21, cách nào tạo và bắt đầu chạy một virtual thread?
A. `Thread.ofPlatform().start(() -> work());` tạo virtual thread.
B. `new Thread(() -> work()).setVirtual(true);` tạo và chạy task.
C. `Thread.startVirtualThread(() -> work());` tạo và chạy task.
D. `Executors.newSingleThreadExecutor().submit(() -> work());` tạo virtual thread.
Đáp án đúng: C

Câu 22. Điều nào mô tả đúng `Executors.newVirtualThreadPerTaskExecutor()`?
A. Mỗi task chạy trực tiếp trên carrier thread cố định.
B. Chỉ task đầu tiên dùng virtual thread; task sau dùng platform.
C. Mọi task chạy trên đúng một virtual thread dùng chung.
D. Mỗi task được thực thi trong một virtual thread mới.
Đáp án đúng: D

Câu 23. Virtual threads thường mang lại lợi ích rõ nhất cho loại workload nào?
A. I/O blocking nhiều task, không phải CPU-bound thuần.
B. Một vòng lặp mã hóa cần tối đa hóa vector instructions.
C. Một phép nhân ma trận đơn luồng chiếm CPU liên tục.
D. Một kernel số học cần khóa một core cho mỗi request.
Đáp án đúng: A

Câu 24. Khi cần giới hạn số truy vấn DB đồng thời trong ứng dụng dùng virtual threads, cách nào phù hợp?
A. Tạo pool virtual thread kích thước bằng số kết nối DB.
B. Dùng semaphore hoặc giới hạn connection pool.
C. Đặt một carrier thread riêng cho mỗi kết nối DB.
D. Dùng Thread.stop để hủy task vượt giới hạn kết nối.
Đáp án đúng: B

Câu 25. Khi virtual thread chờ `Thread.sleep` ngoài vùng bị pin, carrier thread có thể được dùng ra sao?
A. Carrier được giải phóng để chạy virtual thread khác.
B. Carrier được chuyển thành thread con của virtual thread.
C. Carrier bị giữ riêng suốt thời gian sleep của task.
D. Carrier tự bị hủy sau lời gọi sleep đầu tiên.
Đáp án đúng: A

Câu 26. Phát biểu nào đúng về quan hệ virtual thread và OS thread khi nhiều request blocking?
A. Virtual thread không dùng carrier OS thread để chạy code.
B. Mỗi virtual thread luôn cần một OS thread dành riêng.
C. Virtual thread chỉ chạy được khi toàn bộ CPU đang rảnh.
D. Nhiều virtual thread dùng chung carrier OS threads.
Đáp án đúng: D

Câu 27. Với hàng nghìn virtual threads, vì sao nên cân nhắc số lượng ThreadLocal lớn?
A. Dữ liệu ThreadLocal trên mỗi thread có thể tăng áp lực bộ nhớ.
B. ThreadLocal tự biến mất ngay sau lần gọi đầu trên thread.
C. ThreadLocal được chia sẻ giữa các virtual threads theo mặc định.
D. Virtual thread không hỗ trợ ThreadLocal trên JDK 21.
Đáp án đúng: A

Câu 28. Khi nâng từ JDK 21 lên JDK 24+, nhận định nào phù hợp về pinning bởi `synchronized`?
A. JDK 24 không còn chạy synchronized trên virtual thread.
B. Từ JDK 24, synchronized không pin virtual threads.
C. JDK 24 bắt buộc đổi mọi synchronized thành ReentrantLock.
D. JDK 24 buộc mỗi virtual thread sở hữu một carrier riêng.
Đáp án đúng: B

Câu 29. Với `Thread.ofVirtual().name("job-", 0).factory()`, kết quả là gì?
A. Platform thread pool có tên cố định là job-0.
B. ThreadFactory tạo virtual threads có tên theo bộ đếm.
C. ThreadGroup chứa các task có prefix giống nhau.
D. ExecutorService tự chạy task ngay sau khi tạo factory.
Đáp án đúng: B

Câu 30. Generational ZGC được giới thiệu ở Java 21 nhằm khai thác đặc điểm nào của heap?
A. Thu gom mọi object bằng một lần stop-the-world dài.
B. Thay thế GC thành cơ chế reference counting thuần túy.
C. Chuyển toàn bộ object lên native memory thay cho heap.
D. Phân thế hệ trẻ/già để xử lý tốt hơn vòng đời object.
Đáp án đúng: D

Câu 31. Khi chọn ZGC trên JDK hiện đại và muốn đo tác động GC, cách nào phù hợp?
A. Giả định mọi workload đều có GC pause bằng không.
B. Giữ mọi cờ ZGC đời Java 21 mà không kiểm tra hỗ trợ.
C. Dùng ZGC được hỗ trợ và phân tích log `-Xlog:gc*`.
D. Đo mỗi thời gian biên dịch để suy ra GC runtime.
Đáp án đúng: C

Câu 32. Khi biên dịch trên JDK mới nhưng cần mã và API tương thích Java 21, tùy chọn nào phù hợp?
A. `java --release 21` tự biên dịch toàn bộ ứng dụng.
B. `javac --release 21` kiểm tra source, API và bytecode.
C. `javac --target 21` giới hạn cú pháp và Java API.
D. `javac --source 21` giới hạn cả API của JDK hiện tại.
Đáp án đúng: B
