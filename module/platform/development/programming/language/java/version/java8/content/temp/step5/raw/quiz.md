Câu 1: Điều kiện cốt lõi để một interface là functional interface trong Java là gì?
A. Có một abstract method theo hợp đồng SAM.
B. Có một public method bất kỳ.
C. Có một default method hợp lệ.
D. Có một static method hợp lệ.
Đáp án đúng: A

Câu 2: Interface có một abstract method và hai default method được dùng làm kiểu đích của lambda không?
A. Có, nhưng phải xóa mọi default method khi biên dịch.
B. Có, vì default method không tính là abstract method.
C. Không, vì lambda chỉ nhận interface không có default.
D. Không, vì có nhiều hơn một method trong interface.
Đáp án đúng: B

Câu 3: Một lambda tham chiếu biến cục bộ rồi biến đó bị gán lại trong phương thức thì sao?
A. Hợp lệ vì lambda tự lấy giá trị ở lần gán cuối.
B. Hợp lệ vì mọi biến trong lambda đều tự động volatile.
C. Lỗi runtime khi lambda đọc một biến từng được đổi.
D. Lỗi biên dịch: biến bắt giữ cần effectively final.
Đáp án đúng: D

Câu 4: Trong lambda đặt bên trong một phương thức instance, từ khóa `this` trỏ đến đâu?
A. Đối tượng bao quanh nơi khai báo lambda.
B. Đối tượng tham số đầu tiên của biểu thức lambda.
C. Một đối tượng lambda được tạo độc lập lúc gọi.
D. Đối tượng functional interface do compiler sinh ra.
Đáp án đúng: A

Câu 5: Khi viết `Runnable task = () -> work();`, kiểu đích của lambda được quyết định bằng gì?
A. Kiểu trả về của phương thức `work()`.
B. Ngữ cảnh gán vào biến có kiểu `Runnable`.
C. Kiểu lớp của đối tượng ở lệnh trước đó.
D. Kiểu tham số mặc định do JVM chọn khi chạy.
Đáp án đúng: B

Câu 6: Phương thức trừu tượng của `Predicate<T>` có chữ ký trả về kiểu gì?
A. `boolean` qua phương thức `test(T)`.
B. `int` qua phương thức `compare(T)`.
C. `T` qua phương thức `apply(T)`.
D. `void` qua phương thức `accept(T)`.
Đáp án đúng: A

Câu 7: Với hàm `f` và `g`, `f.compose(g)` áp dụng theo trình tự nào?
A. Chạy `g` trước rồi đưa kết quả cho `f`.
B. Chạy `f` trước rồi đưa kết quả cho `g`.
C. Chỉ chạy `f` khi `g` trả giá trị `null`.
D. Chạy hai hàm song song rồi ghép kết quả.
Đáp án đúng: A

Câu 8: Với hàm `f` và `g`, `f.andThen(g)` áp dụng theo trình tự nào?
A. Chạy đồng thời `f` và `g` trên đầu vào.
B. Chỉ chạy `g` khi `f` ném ngoại lệ.
C. Chạy `f`, rồi chạy `g` trên kết quả.
D. Chạy `g` trước rồi đưa kết quả cho `f`.
Đáp án đúng: C

Câu 9: Với `p.and(q)` là hai `Predicate`, khi `p.test(x)` trả `false` thì sao?
A. `q.test(x)` không được gọi do short-circuit.
B. `q.test(x)` chạy nhưng kết quả bị bỏ qua.
C. `q.test(x)` được gọi trên `null` thay vì `x`.
D. `q.test(x)` vẫn chạy để hoàn tất biểu thức.
Đáp án đúng: A

Câu 10: Khi xây callback cung cấp cấu hình, hợp đồng `Supplier<T>` mô tả chức năng nào?
A. Nhận một đối số `T` và không trả giá trị.
B. Không nhận đối số, trả về giá trị `T`.
C. Nhận một đối số `T` và trả về `boolean`.
D. Nhận hai đối số `T` và trả một giá trị `T`.
Đáp án đúng: B

Câu 11: `UnaryOperator<String>` tương ứng với ánh xạ đầu vào và đầu ra nào?
A. Nhận `String` rồi trả về một `String`.
B. Nhận `String` rồi trả một `Integer`.
C. Nhận hai `String` rồi trả một `String`.
D. Nhận `String` rồi trả một `Boolean`.
Đáp án đúng: A

Câu 12: `BinaryOperator<Integer>` thích hợp cho hợp đồng thao tác nào?
A. Nhận một `Integer` và trả về một `Integer`.
B. Nhận ba `Integer` và trả về một `Integer`.
C. Nhận hai `Integer` và trả về một `Boolean`.
D. Nhận hai `Integer` và trả `Integer`.
Đáp án đúng: D

Câu 13: Lambda được gán cho `Function<Path, String>` gọi API ném IOException chưa xử lý sẽ thế nào?
A. Biên dịch vì compiler tự thêm IOException vào `apply`.
B. Chạy được vì lambda mặc định bỏ qua checked exception.
C. Biên dịch vì IOException tự chuyển thành RuntimeException.
D. Lỗi biên dịch do `apply` không khai báo IOException.
Đáp án đúng: D

Câu 14: Với `Comparator.comparing(Person::getName).thenComparingInt(Person::getAge)`, khi nào so sánh tuổi?
A. Sau mọi lần so sánh, bất kể hai tên có trùng.
B. Trước khi so sánh tên để xác định khóa chính.
C. Khi hai tên trả kết quả so sánh bằng nhau.
D. Khi kết quả so sánh tên của hai đối tượng khác nhau.
Đáp án đúng: C

Câu 15: Biểu thức `Integer::parseInt` dùng trực tiếp được với kiểu đích nào?
A. `Supplier<Integer>` tạo số không có đầu vào.
B. `Consumer<Integer>` tiêu thụ một số nguyên.
C. `Function<String, Integer>` nhận chuỗi và trả số.
D. `Predicate<String>` kiểm tra chuỗi boolean.
Đáp án đúng: C

Câu 16: Method reference `String::length` phù hợp với functional interface nào?
A. `Consumer<String>` nhận chuỗi mà không trả gì.
B. `Predicate<String>` nhận chuỗi trả kết quả đúng sai.
C. `Supplier<Integer>` trả độ dài không nhận chuỗi.
D. `Function<String, Integer>` nhận chuỗi trả độ dài.
Đáp án đúng: D

Câu 17: Cho `String s = "abc";`, `s::length` phù hợp với kiểu đích nào?
A. `Consumer<String>` thay chuỗi được gắn lúc tạo.
B. `Supplier<Integer>` trả độ dài của chuỗi đã gắn.
C. `Function<String, Integer>` nhận chuỗi mới để đo.
D. `Predicate<String>` kiểm tra chuỗi truyền lúc gọi.
Đáp án đúng: B

Câu 18: Constructor reference `ArrayList::new` có thể gán cho biến kiểu nào?
A. `Consumer<List<String>>` cập nhật list được truyền.
B. `Predicate<List<String>>` kiểm tra list đầu vào.
C. `Supplier<List<String>>` tạo list khi được gọi.
D. `Function<String, List<String>>` phân tích chuỗi.
Đáp án đúng: C

Câu 19: Array constructor reference `String[]::new` hợp với kiểu đích nào?
A. `IntFunction<String[]>` nhận kích thước mảng.
B. `Function<String, String[]>` nhận chuỗi bất kỳ.
C. `Supplier<String[]>` không nhận kích thước.
D. `Consumer<Integer>` chỉ nhận kích thước mảng.
Đáp án đúng: A

Câu 20: Unbound reference `String::startsWith` phù hợp với kiểu nào?
A. `Consumer<String>` thay đổi tiền tố của một chuỗi.
B. `Predicate<String>` chỉ nhận một chuỗi bất kỳ.
C. `BiPredicate<String, String>` nhận chuỗi và tiền tố.
D. `BiFunction<String, String, String>` trả ra chuỗi.
Đáp án đúng: C

Câu 21: Với `String s = null; Supplier<Integer> x = s::length;`, lỗi xảy ra lúc nào?
A. Biên dịch lỗi vì method reference không nhận biến `s`.
B. Không lỗi vì method reference chuyển `null` thành rỗng.
C. Ném `NullPointerException` khi tạo method reference.
D. Ném `NullPointerException` chỉ khi gọi `x.get()`.
Đáp án đúng: C

Câu 22: `Comparator.comparingInt(Person::getAge)` mặc định sắp xếp theo quy tắc nào?
A. Thứ tự hashCode của từng đối tượng `Person`.
B. Tuổi tăng dần theo thứ tự của `int`.
C. Tuổi giảm dần theo thứ tự tự nhiên của `int`.
D. Tên tăng dần rồi mới so sánh theo tuổi.
Đáp án đúng: B

Câu 23: Với `Stream.of(1, 2).map(this::logAndMap)` mà không có terminal operation, điều gì đúng?
A. Hàm trong `map` chỉ chạy sau khi gọi `close()`.
B. Hàm trong `map` chạy ngay khi tạo stream.
C. Hàm trong `map` chạy khi tạo nguồn `Stream.of`.
D. `map` chưa xử lý vì chưa có thao tác terminal.
Đáp án đúng: D

Câu 24: Sau khi gọi `count()` trên một Stream, sử dụng lại cùng Stream để `filter` sẽ thế nào?
A. Hợp lệ vì `count()` không thay đổi stream nguồn.
B. Gặp `IllegalStateException` vì stream đã tiêu thụ.
C. Gặp `UnsupportedOperationException` khi filter.
D. Hợp lệ nếu thao tác tiếp theo chỉ là intermediate.
Đáp án đúng: B

Câu 25: Trong Stream, thao tác `filter(predicate)` có nhiệm vụ gì?
A. Nhóm phần tử theo giá trị của một khóa phân loại.
B. Giữ những phần tử làm `predicate` trả `false`.
C. Giữ những phần tử làm `predicate` trả `true`.
D. Biến từng phần tử thành một đối tượng kiểu mới.
Đáp án đúng: C

Câu 26: Khác biệt cơ bản giữa `map` và `flatMap` trong Stream là gì?
A. `flatMap` chỉ biến mỗi phần tử thành một phần tử.
B. `flatMap` gom mỗi stream con thành một phần tử list.
C. `flatMap` làm phẳng các stream con thành stream chung.
D. `flatMap` sắp xếp các stream con theo thứ tự tăng.
Đáp án đúng: C

Câu 27: `distinct()` xác định các phần tử trùng trong Stream object dựa vào gì?
A. Quan hệ bằng nhau theo `Object.equals`.
B. Quan hệ sắp thứ tự theo `Comparator`.
C. Quan hệ đồng nhất theo toán tử tham chiếu `==`.
D. Quan hệ cùng kiểu runtime của hai đối tượng.
Đáp án đúng: A

Câu 28: Khi gọi `sorted()` không đối số trên Stream các phần tử object, điều kiện cần là gì?
A. Các phần tử phải có phương thức `hashCode()` riêng.
B. Các phần tử phải so sánh được theo natural order.
C. Các phần tử phải giữ cùng một identity trong stream.
D. Các phần tử phải triển khai interface `Serializable`.
Đáp án đúng: B

Câu 29: Với stream tuần tự có encounter order `"a", "b"`, `findFirst()` trả gì?
A. `List` chứa cả hai phần tử `"a"`, `"b"`.
B. `boolean` cho biết stream có phần tử hay không.
C. `Optional` chứa phần tử `"b"` cuối cùng.
D. `Optional` chứa phần tử `"a"` đầu tiên.
Đáp án đúng: D

Câu 30: Khi stream còn phần tử chưa duyệt, điều kiện nào đủ để `anyMatch(predicate)` trả `true`?
A. Phát hiện một phần tử không thỏa điều kiện.
B. Phát hiện một phần tử thỏa điều kiện kiểm tra.
C. Tất cả phần tử đều thỏa điều kiện kiểm tra.
D. Không còn phần tử trong source để kiểm tra.
Đáp án đúng: B

Câu 31: `Stream.<Integer>empty().allMatch(n -> n > 0)` trả về gì?
A. `false`, do không có phần tử thỏa điều kiện.
B. `null`, do biểu thức predicate chưa từng chạy.
C. `true`, do không có phần tử vi phạm điều kiện.
D. `Optional.empty()`, do không có dữ liệu đầu vào.
Đáp án đúng: C

Câu 32: `Stream.<Integer>empty().noneMatch(n -> n < 0)` trả về gì?
A. `Optional.empty()`, do không có kết quả khớp.
B. `null`, do biểu thức predicate chưa được gọi.
C. `false`, do không có phần tử trong nguồn.
D. `true`, do không có phần tử thỏa điều kiện.
Đáp án đúng: D

Câu 33: `Stream.of(1, 2, 3, 4).limit(2).count()` trả về bao nhiêu?
A. `1`, vì `limit()` giữ phần tử cuối cùng.
B. `3`, vì `limit()` bỏ phần tử đầu tiên.
C. `2`, vì giới hạn nhận hai phần tử đầu tiên.
D. `4`, vì `count()` đếm toàn bộ nguồn ban đầu.
Đáp án đúng: C

Câu 34: `Stream.of(1, 2, 3, 4).skip(2).count()` trả về bao nhiêu?
A. `2`, do bỏ qua hai phần tử đầu của nguồn.
B. `1`, vì chỉ lấy phần tử sau vị trí thứ ba.
C. `4`, vì `skip()` không tác động tới `count()`.
D. `3`, vì chỉ bỏ qua phần tử đầu tiên.
Đáp án đúng: A

Câu 35: `Stream.of("ab", "cd").collect(Collectors.toMap(String::length, Function.identity()))` sẽ ra sao?
A. Tạo Map có hai entry độc lập mang khóa `2`.
B. Tạo Map giữ phần tử đầu tiên với khóa `2`.
C. Tạo Map giữ phần tử cuối cùng với khóa `2`.
D. Ném `IllegalStateException` vì hai khóa trùng nhau.
Đáp án đúng: D

Câu 36: Kết quả `collect(Collectors.groupingBy(String::length))` trên Stream chuỗi có dạng nào?
A. `Map<String, Integer>` theo giá trị chuỗi.
B. `Map<Integer, List<String>>` theo nhóm độ dài.
C. `Set<String>` đã loại những chuỗi cùng độ dài.
D. `List<Map<Integer, String>>` theo độ dài.
Đáp án đúng: B

Câu 37: Khi thu thập `Stream<Integer>`, `Collectors.partitioningBy(n -> n % 2 == 0)` cho kết quả dạng nào?
A. `Set<Integer>` chỉ giữ số chẵn từ stream.
B. `List<Boolean>` lưu kết quả kiểm tra phần tử.
C. `Map<Boolean, List<Integer>>` chia đúng và sai.
D. `Map<Integer, Boolean>` gắn cờ cho từng số.
Đáp án đúng: C

Câu 38: `Stream.of("a", "b").collect(Collectors.joining(","))` trả về chuỗi nào?
A. `"b,a"`, đảo thứ tự rồi chèn dấu phẩy.
B. `"a,b"`, nối theo thứ tự phần tử có sẵn.
C. `"[a,b]"`, thêm dấu ngoặc như danh sách.
D. `"a b"`, thay dấu phân cách thành khoảng trắng.
Đáp án đúng: B

Câu 39: Tại sao `mapToInt(String::length).sum()` hữu ích với Stream chuỗi?
A. Chuyển các chuỗi thành `Stream<Integer>` boxed.
B. Đổi mọi chuỗi thành số nguyên bằng parseInt.
C. Lấy độ dài lớn nhất bằng comparator mặc định.
D. Tính tổng độ dài bằng `IntStream` nguyên thủy.
Đáp án đúng: D

Câu 40: `Stream.of(1, 2, 3).reduce(0, Integer::sum)` cho kết quả nào?
A. `0`, vì reduce luôn trả về identity ban đầu.
B. `Optional[6]`, vì có lời gọi hàm khởi tạo.
C. `6`, vì cộng từ phần tử `0` ban đầu.
D. `3`, vì reduce chỉ giữ phần tử cuối cùng.
Đáp án đúng: C

Câu 41: Với stream song song có encounter order, terminal operation nào giữ thứ tự khi thực hiện hành động?
A. `findAny` để thực hiện hành động theo thứ tự.
B. `forEach` để tuân thủ thứ tự gặp phần tử.
C. `forEachOrdered` bảo toàn encounter order.
D. `unordered` để duy trì thứ tự lúc lấy dữ liệu.
Đáp án đúng: C

Câu 42: Đặc tính nào được bảo đảm bởi `Collectors.toList()` trong Java 8+?
A. Trả List; không bảo đảm loại cụ thể hoặc sửa được.
B. Luôn trả về LinkedList có tính an toàn luồng.
C. Luôn trả về danh sách immutable giữ thứ tự.
D. Luôn trả về ArrayList và có thể thêm phần tử.
Đáp án đúng: A

Câu 43: Trong phép tính `IntStream.range(2, 5).sum()`, giá trị trả về là gì?
A. `14`, vì nguồn chứa cả các số từ `2` tới `5`.
B. `5`, vì `range` chỉ trả giới hạn trên.
C. `7`, vì nguồn chỉ chứa hai số đầu và cuối.
D. `9`, vì nguồn chứa các số `2`, `3`, `4`.
Đáp án đúng: D

Câu 44: `Optional.of(null)` có hành vi gì khi tạo đối tượng?
A. Ném `NoSuchElementException` khi gọi `of`.
B. Ném `NullPointerException` khi gọi `of`.
C. Trả `Optional.empty()` giống `ofNullable`.
D. Tạo Optional chứa nguyên giá trị `null`.
Đáp án đúng: B

Câu 45: Khi dữ liệu đầu vào là `null`, `Optional.ofNullable(null)` trả về kết quả nào?
A. `null` để bên gọi tự xử lý trường hợp rỗng.
B. `Optional` có phần tử nhưng giá trị là `null`.
C. `Optional` chứa chuỗi mặc định `"null"`.
D. `Optional.empty()` biểu thị thiếu giá trị đầu vào.
Đáp án đúng: D

Câu 46: Với Optional đã có giá trị, `orElse(expensiveFallback())` có hành vi nào?
A. Fallback được trì hoãn tới lúc gọi `get()`.
B. Fallback chỉ được đánh giá nếu Optional đang rỗng.
C. Fallback được chuyển tự động sang một `Supplier`.
D. `orElse` đánh giá fallback dù Optional có dữ liệu.
Đáp án đúng: D

Câu 47: Với Optional đã có giá trị, `orElseGet(() -> expensiveFallback())` làm gì?
A. Không gọi supplier vì giá trị đã hiện diện.
B. Gọi supplier rồi trả về kết quả của supplier.
C. Gọi supplier khi Optional có giá trị khác null.
D. Vẫn gọi supplier để so sánh giá trị dự phòng.
Đáp án đúng: A

Câu 48: Với hàm `f` hợp lệ và `Optional.empty().map(f)`, thao tác nào xảy ra?
A. Ném `NoSuchElementException` do thiếu dữ liệu.
B. Gọi `f` một lần với tham số là `null`.
C. Gọi `f` một lần với tham số `Optional`.
D. Không gọi `f` và nhận lại Optional rỗng.
Đáp án đúng: D

Câu 49: Với `Optional.of("x").map(s -> null)`, kết quả nhận được là gì?
A. Ném `NullPointerException` do mapper trả `null`.
B. `Optional.empty()` do mapper trả về `null`.
C. `Optional.of("x")` vì null bị bỏ qua.
D. `Optional` có phần tử là giá trị `null`.
Đáp án đúng: B

Câu 50: Khác nhau chính giữa `Optional.flatMap` và `Optional.map` là gì?
A. `flatMap` chạy mapper khi Optional đang rỗng.
B. `flatMap` chỉ nhận mapper trả kiểu nguyên thủy `int`.
C. `flatMap` nhận mapper trả giá trị thường rồi bọc hai lớp.
D. `flatMap` nhận Optional và tránh Optional lồng nhau.
Đáp án đúng: D

Câu 51: `Optional.of(10).filter(n -> n > 20)` tạo kết quả nào?
A. `Optional.empty()` khi predicate trả `false`.
B. `Optional.of(10)` vì vẫn giữ giá trị gốc.
C. `Optional.of(20)` vì filter nâng lên ngưỡng.
D. Ném `IllegalArgumentException` vì không khớp.
Đáp án đúng: A

Câu 52: `Optional.empty().ifPresent(consumer)` dẫn tới hành vi nào?
A. Không gọi consumer khi Optional không có giá trị.
B. Gọi consumer một lần với tham số là `null`.
C. Gọi consumer một lần với `Optional.empty()`.
D. Ném `NoSuchElementException` trước khi gọi.
Đáp án đúng: A

Câu 53: `Optional.empty().orElseThrow(IllegalStateException::new)` sẽ làm gì?
A. Trả về `null` do Optional không có giá trị.
B. Ném `NoSuchElementException` như lời gọi `get`.
C. Ném `IllegalStateException` lấy từ supplier.
D. Trả về một đối tượng `IllegalStateException`.
Đáp án đúng: C

Câu 54: Kiểu Optional chuyên biệt nào chứa số `int` mà không cần boxing `Integer`?
A. `Optional<Integer>` giữ trực tiếp `int` nguyên thủy.
B. `OptionalInt` đại diện giá trị nguyên thủy `int`.
C. `IntSupplier` luôn đại diện Optional của `int`.
D. `IntStream` luôn đại diện một số `int` tùy chọn.
Đáp án đúng: B

Câu 55: Kiểu nào biểu diễn ngày lịch mà không kèm giờ hay múi giờ?
A. `LocalDateTime` biểu diễn cả ngày và giờ.
B. `ZonedDateTime` mang quy tắc múi giờ cụ thể.
C. `LocalDate` biểu diễn ngày không có giờ hay múi.
D. `Instant` biểu diễn thời điểm trên timeline UTC.
Đáp án đúng: C

Câu 56: Vì sao `LocalDateTime` đơn lẻ chưa đủ xác định duy nhất một instant toàn cầu?
A. Nó không mang vùng giờ hoặc offset cụ thể.
B. Nó không thể biểu diễn ngày nằm sau năm 2000.
C. Nó luôn chuyển ngày thành UTC khi khởi tạo.
D. Nó chỉ có độ chính xác tới đơn vị ngày.
Đáp án đúng: A

Câu 57: Loại nào phù hợp để lưu một thời điểm tuyệt đối cho audit log đa khu vực?
A. `LocalDate` biểu diễn ngày không có thời gian.
B. `Period` biểu diễn khoảng cách theo lịch.
C. `LocalTime` biểu diễn giờ không mang ngày.
D. `Instant` biểu diễn điểm trên dòng thời gian.
Đáp án đúng: D

Câu 58: Khi tính lịch họp lặp tại một thành phố có DST, kiểu thời gian nào gắn quy tắc vùng?
A. `ZonedDateTime` gắn với `ZoneId` của khu vực.
B. `Instant` chỉ chứa điểm thời gian tuyệt đối.
C. `OffsetDateTime` chỉ chứa offset cố định.
D. `LocalDateTime` chỉ chứa ngày và giờ địa phương.
Đáp án đúng: A

Câu 59: Khác biệt cốt lõi giữa `OffsetDateTime` và `ZonedDateTime` là gì?
A. OffsetDateTime không có ngày; ZonedDateTime có ngày.
B. `OffsetDateTime` mang offset; `ZonedDateTime` mang zone.
C. OffsetDateTime luôn dùng UTC; ZonedDateTime luôn dùng GMT.
D. OffsetDateTime chỉ có giờ; ZonedDateTime có ngày và giờ.
Đáp án đúng: B

Câu 60: Với chênh lệch hai `LocalDate` theo năm, tháng, ngày lịch, kiểu nào hợp lý?
A. `LocalTime` diễn tả giờ trong một ngày.
B. `Duration` diễn tả lượng giây và nano.
C. `Period` mô tả số năm, tháng và ngày.
D. `Instant` diễn tả một điểm thời gian UTC.
Đáp án đúng: C

Câu 61: Để đo thời lượng thực giữa hai `Instant`, nên dùng API nào?
A. `Duration.between(start, end)` để tính elapsed time.
B. `ZoneId.between(start, end)` để tính elapsed time.
C. `Period.between(start, end)` để tính elapsed time.
D. `LocalDate.between(start, end)` để tính elapsed time.
Đáp án đúng: A

Câu 62: Với `LocalDate d`, lời gọi `d.plusDays(1)` thay đổi đối tượng như thế nào?
A. Sửa tại chỗ giá trị của đối tượng `d` ban đầu.
B. Chỉ thay đổi trạng thái nếu `d` là biến `final`.
C. Trả một view dùng chung có thể cập nhật vào `d`.
D. Trả LocalDate mới; `d` ban đầu không thay đổi.
Đáp án đúng: D

Câu 63: Trong `java.time`, `LocalDate.of(2024, 2, 29)` có hành vi nào?
A. Tạo ngày hợp lệ do 2024 là năm nhuận.
B. Tự điều chỉnh kết quả sang ngày 1 tháng ba.
C. Trả về `null` vì ngày không hợp lệ.
D. Ném DateTimeException vì tháng hai có 28 ngày.
Đáp án đúng: A

Câu 64: Trong `java.time`, `LocalDate.of(2023, 2, 29)` có hành vi nào?
A. Trả về `Optional.empty()` khi không tạo được.
B. Ném `DateTimeException` vì không phải năm nhuận.
C. Tự chuyển thành ngày 28 tháng 2 năm 2023.
D. Tự chuyển thành ngày 1 tháng 3 năm 2023.
Đáp án đúng: B

Câu 65: `ZoneId.of("Asia/Ho_Chi_Minh")` mang thông tin gì?
A. Đối tượng ngày lịch hiện tại tại Thành phố Hồ Chí Minh.
B. Định danh vùng giờ cùng quy tắc thời gian của vùng.
C. Mốc thời gian UTC chính xác khi gọi phương thức.
D. Offset cố định tính bằng số giờ của Java process.
Đáp án đúng: B

Câu 66: `DateTimeFormatter.ISO_LOCAL_DATE` định dạng `LocalDate.of(2024, 3, 5)` ra sao?
A. `"2024-03-05Z"`, thêm ký hiệu múi giờ UTC.
B. `"2024-3-5"`, không đệm số tháng và ngày.
C. `"05/03/2024"`, định dạng ngày địa phương.
D. `"2024-03-05"`, định dạng ngày ISO chuẩn.
Đáp án đúng: D

Câu 67: Đặc tính nào khiến `DateTimeFormatter` dùng chung giữa các thread được?
A. Mutable nhưng tự khóa toàn bộ lần định dạng.
B. Immutable và thread-safe theo hợp đồng API.
C. Gắn riêng instance vào từng ThreadLocal ngầm.
D. Tự tạo bản sao Formatter cho mỗi lần gọi.
Đáp án đúng: B

Câu 68: Muốn bài test luôn nhận cùng một `Instant` khi truy vấn đồng hồ, nên dùng gì?
A. `Instant.now()` rồi so sánh các lần gọi tiếp.
B. `ZoneId.systemDefault()` rồi chuyển sang UTC.
C. `Clock.fixed(...)` rồi truyền clock cho mã cần test.
D. `Clock.systemDefaultZone()` rồi gọi nhiều lần.
Đáp án đúng: C

Câu 69: Cho `start = LocalDate.of(2024, 1, 1)` và `end = LocalDate.of(2024, 1, 4)`, `ChronoUnit.DAYS.between(start, end)` trả số ngày nào?
A. `2`, vì trừ ngày đầu và cả ngày cuối.
B. `1`, vì trả số tháng đã đi qua trong khoảng.
C. `3`, tính từ mốc đầu đến trước mốc cuối.
D. `4`, vì đếm cả ngày đầu và ngày cuối.
Đáp án đúng: C

Câu 70: Để chuyển `LocalDateTime` thành `Instant` một cách có ý nghĩa, cần thêm gì?
A. Một formatter để thay đổi chuỗi hiển thị ngày.
B. Một comparator để xếp thứ tự các ngày giờ.
C. Một `Period` để đo khoảng cách giữa hai ngày.
D. Cần zone hoặc offset để ánh xạ giờ địa phương.
Đáp án đúng: D

Câu 71: Với `ZonedDateTime.withZoneSameInstant(zone2)`, điều nào được giữ nguyên?
A. Giờ địa phương, còn thời điểm tuyệt đối có thể đổi.
B. Giữ instant, nhưng giờ địa phương có thể thay đổi.
C. Cả giờ địa phương và offset đều luôn giữ nguyên.
D. Chỉ ngày trong tháng, còn năm và giờ đều đổi.
Đáp án đúng: B

Câu 72: Để lấy ngày hiện tại theo đồng hồ có thể tiêm vào khi kiểm thử, dùng API nào?
A. `LocalDate.now(clock)` nhận đồng hồ được tiêm.
B. `Instant.now()` tự động trả về kiểu LocalDate.
C. `LocalDate.now()` luôn dùng một Clock cố định.
D. `LocalDate.ofEpochDay(0)` dùng như ngày hiện tại.
Đáp án đúng: A
