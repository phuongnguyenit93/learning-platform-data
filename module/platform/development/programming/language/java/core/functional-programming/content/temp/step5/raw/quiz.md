Câu 1. Với functional interface trong Java, phương thức nào được tính để xác định SAM?
A. Tất cả default method cùng mọi static method của interface
B. Mọi method public kể cả method thừa kế từ Object
C. Chỉ phương thức không có annotation @Override trong interface
D. Một abstract method chức năng, trừ chữ ký thuộc Object
Đáp án đúng: D

Câu 2. Annotation @FunctionalInterface giúp trình biên dịch kiểm tra điều gì?
A. Interface có đúng một default method và không có static method
B. Interface không thể extends interface khác với phương thức abstract
C. Interface sẽ được chuyển thành class sau khi biên dịch lambda
D. Interface vẫn thỏa điều kiện chỉ có một abstract method chức năng
Đáp án đúng: D

Câu 3. Một functional interface có thể khai báo thêm gì mà vẫn hợp lệ?
A. Một abstract method thứ hai có chữ ký khác hoàn toàn
B. Nhiều abstract method rồi chọn một khi lambda được gọi
C. Default và static method ngoài abstract method chức năng duy nhất
D. Constructor public để tạo instance interface khi dùng lambda
Đáp án đúng: C

Câu 4. Vì sao cùng biểu thức lambda x -> x + 1 có thể dùng với các kiểu đích khác nhau?
A. Lambda luôn tự suy ra runtime class mới trước khi biết ngữ cảnh
B. Compiler dùng target type để kiểm tra tham số và kiểu trả về
C. Kiểu x được quyết định chỉ bằng bytecode của biểu thức x + 1
D. Lambda không cần functional interface khi gán cho biến Object
Đáp án đúng: B

Câu 5. Biến cục bộ được lambda capture phải đáp ứng điều kiện nào?
A. Phải khai volatile để các lambda có thể sửa trực tiếp
B. Phải khai static trước khi lambda có thể tham chiếu
C. Được gán lại tùy ý nếu chỉ dùng trong một thread
D. Là final hoặc effectively final tại vị trí dùng trong lambda
Đáp án đúng: D

Câu 6. Trong lambda là instance context, từ khóa this thường chỉ gì?
A. Một instance mới được sinh riêng cho chính lambda
B. Instance của class bao quanh nơi lambda được khai báo
C. Functional interface object nhận biến lambda khi gọi
D. Instance của Runnable tạo mặc định khi compile lambda
Đáp án đúng: B

Câu 7. Method reference String::trim tương đương lambda nào nếu target là Function<String,String>?
A. (String s) -> String.trim(s) như gọi static method của String
B. (String s) -> s.toString() rồi không xử lý khoảng trắng
C. (String s) -> s.trim() để gọi method trên đối số nhận được
D. (String s) -> new String(s) rồi giữ nguyên nội dung ban đầu
Đáp án đúng: C

Câu 8. Trong Java, StringBuilder::new có thể làm method reference cho kiểu nào?
A. Supplier<StringBuilder> để tạo đối tượng không tham số
B. Consumer<StringBuilder> để nhận rồi khởi tạo một object
C. Predicate<StringBuilder> để trả boolean từ constructor
D. Comparator<StringBuilder> để so sánh hai constructor
Đáp án đúng: A

Câu 9. Cho Function f và g tương thích, f.andThen(g) thực thi theo thứ tự nào?
A. Áp dụng g trước, sau đó dùng kết quả làm đầu vào f
B. Áp dụng f và g đồng thời rồi chọn kết quả tới trước
C. Áp dụng f trước, sau đó đưa kết quả cho g xử lý
D. Tự bỏ qua f nếu g trả về một Optional.empty()
Đáp án đúng: C

Câu 10. Cho Function f và g tương thích, f.compose(g) có nghĩa nào?
A. Áp dụng f vào đầu vào, rồi đưa kết quả cho g
B. Áp dụng f hai lần trước khi chuyển sang hàm g
C. Áp dụng g vào đầu vào, rồi đưa kết quả cho f
D. Ghép hai Predicate để trả kết quả boolean
Đáp án đúng: C

Câu 11. Trong Predicate<T>, p.and(q).test(value) xử lý điều kiện q thế nào?
A. Chỉ chạy q khi p trả true, theo quy tắc short-circuit
B. Chỉ chạy q khi p trả false, theo quy tắc short-circuit
C. Chạy p và q song song trước khi kết hợp boolean
D. Không chạy q vì and chỉ kiểm tra p trên value
Đáp án đúng: A

Câu 12. Predicate.negate() tạo ra kết quả kiểu nào khi gọi?
A. Một Function chuyển boolean sang Integer tương ứng
B. Một Consumer bỏ qua giá trị nếu predicate trả false
C. Một UnaryOperator sửa trực tiếp trạng thái của dữ liệu
D. Một Predicate đảo kết quả boolean của predicate ban đầu
Đáp án đúng: D

Câu 13. Khi c1.andThen(c2).accept(x) trên hai Consumer, thứ tự tác dụng nào đúng?
A. Thực hiện c1 trước rồi mới gọi c2 với cùng giá trị x
B. Thực hiện c2 trước rồi mới gọi c1 với giá trị c2 trả về
C. Gọi song song hai Consumer và tự đồng bộ tác dụng phụ
D. Chỉ gọi c2 khi c1 trả về true trên đối số x
Đáp án đúng: A

Câu 14. Supplier<T> đại diện cho hợp đồng phương thức nào trong java.util.function?
A. get() không nhận đối số và cung cấp giá trị kiểu T
B. accept(T) nhận giá trị T mà không có kết quả trả về
C. test(T) nhận giá trị T và luôn trả về boolean
D. apply(T) nhận một T rồi trả về một giá trị khác
Đáp án đúng: A

Câu 15. UnaryOperator<String> có khác biệt kiểu dữ liệu nào so với Function<String,Integer>?
A. Nhận hai String rồi hợp chúng thành một Integer
B. Chỉ trả về void và sửa String tại chỗ qua accept
C. Đầu vào và đầu ra đều là String, cùng một kiểu T
D. Trả về boolean từ phép kiểm tra dữ liệu String
Đáp án đúng: C

Câu 16. BinaryOperator<Integer> phù hợp với kiểu thao tác nào?
A. Nhận một Integer rồi trả String để định dạng kết quả
B. Nhận hai Integer nhưng trả boolean cho phép kiểm tra
C. Nhận hai Integer và trả lại một Integer làm kết quả
D. Không nhận đối số và tạo một Integer bằng supplier
Đáp án đúng: C

Câu 17. BiFunction<A,B,R> được sử dụng trong trường hợp nào?
A. Hàm nhận một kiểu A và trả hai kết quả B và R
B. Hàm nhận hai tham số A và B rồi trả kết quả kiểu R
C. Hàm kiểm tra hai tham số nhưng bắt buộc trả boolean
D. Hàm chỉ nhận tham số A, B là kiểu exception
Đáp án đúng: B

Câu 18. Comparator.comparing(Person::age) thường sắp xếp theo tiêu chí nào?
A. Giá trị age trích từ mỗi Person theo key extractor
B. Thứ tự tạo object Person trong heap của JVM
C. Giá trị identityHashCode của mọi Person khi so sánh
D. Số lần age() được gọi trước khi comparator được tạo
Đáp án đúng: A

Câu 19. Khi dùng cmp.thenComparing(Person::name), so sánh thứ hai được dùng lúc nào?
A. Ngay trước cmp cho mọi cặp phần tử được so sánh
B. Chỉ khi cmp đầu tiên phát sinh exception runtime
C. Khi cmp đầu tiên trả âm và Person bên trái nhỏ hơn
D. Khi tiêu chí cmp đầu tiên trả kết quả bằng 0
Đáp án đúng: D

Câu 20. Optional.of(null) trong Java có hành vi nào?
A. Trả về Optional.empty() để biểu diễn giá trị thiếu
B. Ném NullPointerException vì of không chấp nhận null
C. Trả về Optional chứa chính null như một giá trị
D. Chuyển null thành chuỗi rỗng trước khi lưu vào Optional
Đáp án đúng: B

Câu 21. Optional.ofNullable(null) tạo kết quả nào?
A. Optional.of("null") bằng cách chuyển thành String
B. Một Optional có isPresent() bằng true nhưng get null
C. Ném IllegalStateException để từ chối tham số null
D. Optional.empty() thay vì Optional chứa null
Đáp án đúng: D

Câu 22. Với Optional có giá trị, map(fn) trả về null từ mapper sẽ tạo gì?
A. Optional chứa null và vẫn báo isPresent true
B. NullPointerException giống Optional.of(null)
C. Optional.empty() sau khi mapper trả kết quả null
D. Optional hiện tại không thay đổi và giữ giá trị đầu
Đáp án đúng: C

Câu 23. Với fn trả Optional<U>, gọi Optional<T>.flatMap(fn) có điểm gì chính?
A. Trả Optional<U> mà không lồng thành Optional<Optional<U>>
B. Bắt buộc bọc Optional<U> thành Optional<Optional<U>>
C. Tự chuyển Optional<U> thành Stream<U> để gộp kết quả
D. Chỉ chạy fn khi Optional<T> đang rỗng, không có giá trị
Đáp án đúng: A

Câu 24. Khi gọi opt.orElse(createFallback()), createFallback() có được thực thi nếu opt có giá trị không?
A. Không; orElse chỉ tính đối số khi Optional đang rỗng
B. Có; biểu thức đối số được tính trước khi gọi orElse
C. Không; compiler tự biến mọi lời gọi sang Supplier lazy
D. Có; nhưng chỉ khi giá trị Optional là một kiểu primitive
Đáp án đúng: B

Câu 25. Với opt.orElseGet(() -> createFallback()), supplier được gọi khi nào?
A. Khi Optional có giá trị để xác minh giá trị hiện tại
B. Khi Optional được tạo bằng Optional.ofNullable
C. Khi Optional rỗng và cần tạo giá trị thay thế
D. Khi JVM nạp class khai báo Supplier cho lần đầu
Đáp án đúng: C

Câu 26. Với opt.orElseThrow(() -> new MissingException()), kết quả khi rỗng là gì?
A. Tạo Optional mới chứa đối tượng MissingException
B. Ném exception do supplier tạo ra thay vì trả fallback
C. Trả null mặc định nếu supplier không tạo được giá trị
D. Tự gọi Optional.get() rồi bỏ qua exception gốc
Đáp án đúng: B

Câu 27. Optional.ifPresentOrElse(action, emptyAction) chọn nhánh nào?
A. Rỗng thì chạy action; có giá trị thì chạy emptyAction
B. Chạy cả hai nhánh rồi chọn kết quả theo isPresent()
C. Chỉ gọi emptyAction nếu action trả boolean false
D. Có giá trị thì chạy action; rỗng thì chạy emptyAction
Đáp án đúng: D

Câu 28. Optional.stream() tạo kết quả nào khi Optional đang rỗng?
A. Stream không có phần tử, thay vì một phần tử null
B. Stream chứa một Optional.empty() như phần tử duy nhất
C. Stream một phần tử null cho các toán tử map và filter
D. Stream không hữu hạn và chờ Optional có giá trị sau
Đáp án đúng: A

Câu 29. Trong Stream API, pipeline chỉ có filter() và map() nhưng chưa terminal operation sẽ thế nào?
A. filter và map lập tức duyệt hết nguồn ngay khi khai báo
B. Stream tự gọi collect ở cuối biểu thức và lưu list
C. Intermediate operations chạy nền bằng ForkJoinPool mặc định
D. Intermediate operations được trì hoãn đến khi có terminal operation
Đáp án đúng: D

Câu 30. Điều gì thường xảy ra khi sử dụng lại cùng một Stream sau terminal operation?
A. Pipeline sẽ khởi động lại nguồn và tự tính kết quả mới
B. Có thể ném IllegalStateException vì Stream đã được tiêu thụ
C. Stream reset con trỏ rồi tự lặp lại dữ liệu đã đọc
D. Terminal operation lần hai trả Optional.empty() bắt buộc
Đáp án đúng: B

Câu 31. Với Stream<T>, map(f) có tác dụng chính gì?
A. Loại những phần tử mà f trả false như Predicate.test
B. Tự dàn phẳng nhiều Stream con và sắp xếp kết quả
C. Biến đổi từng phần tử thông qua f thành phần tử của Stream mới
D. Chỉ biến đổi phần tử đầu tiên, những phần tử sau giữ nguyên
Đáp án đúng: C

Câu 32. Với Stream<List<T>>, flatMap(List::stream) có kết quả thông thường nào?
A. Tạo Stream<Stream<T>> nhưng giữ nguyên mức lồng
B. Dàn phẳng các list con thành một luồng phần tử T
C. Nhóm tất cả phần tử theo List::size bằng groupingBy
D. Đổi mỗi List<T> thành đúng một Optional<List<T>>
Đáp án đúng: B

Câu 33. Đối với stream.filter(predicate), phần tử nào được giữ lại?
A. Những phần tử mà predicate.test(element) trả true
B. Những phần tử mà predicate.test(element) trả false
C. Những phần tử mà predicate.apply(element) trả null
D. Những phần tử có hashCode khác 0 theo JVM
Đáp án đúng: A

Câu 34. Stream.distinct() thường xác định phần tử trùng dựa trên gì?
A. Tham chiếu object theo == bất kể equals được override
B. Thứ tự tự nhiên do Comparable<T> khai báo
C. Quy tắc equals của phần tử và hashCode nhất quán
D. Kết quả toString mà không xét hashCode phần tử
Đáp án đúng: C

Câu 35. Stream.sorted(comparator) là thao tác có đặc điểm nào?
A. Là terminal operation trả thẳng một List đã sắp xếp
B. Intermediate operation có trạng thái để sắp xếp theo comparator
C. Là phép lọc loại phần tử không thỏa Predicate
D. Là toán tử giảm dữ liệu bằng accumulator không có thứ tự
Đáp án đúng: B

Câu 36. IntStream.iterate(0, n -> n + 1).limit(5).sum() trả kết quả nào?
A. 15, tổng các số từ 1 đến 5 sau khi limit
B. 10, tổng các số 0 đến 4 trong năm phần tử đầu
C. 0, vì stream từ iterate không có phần tử hữu hạn
D. Không kết thúc, vì limit không tác động lên infinite stream
Đáp án đúng: B

Câu 37. Với ordered stream, takeWhile(predicate) xử lý thế nào?
A. Lấy prefix liên tiếp và dừng khi gặp phần tử đầu tiên không thỏa
B. Giữ mọi phần tử thỏa predicate kể cả sau phần tử không thỏa
C. Sắp lại dữ liệu để những phần tử thỏa predicate lên đầu
D. Chỉ chọn phần tử cuối cùng thỏa điều kiện trên luồng
Đáp án đúng: A

Câu 38. Vì sao không nên dựa vào peek(action) để thực thi nghiệp vụ bắt buộc?
A. Peek luôn thực thi trước khi có terminal operation trên Stream
B. Peek tự bảo đảm transaction và thứ tự cho parallel stream
C. Peek chỉ có thể đọc phần tử và compiler cấm side effect
D. Peek có thể bị bỏ qua do tối ưu hoặc terminal short-circuit
Đáp án đúng: D

Câu 39. Khi gọi findFirst() trên stream có encounter order, giá trị nào được chọn?
A. Một phần tử bất kỳ do worker thread chọn ngẫu nhiên
B. Phần tử đầu tiên theo encounter order nếu có
C. Phần tử có giá trị nhỏ nhất theo Comparator.naturalOrder
D. Phần tử cuối cùng được xử lý trong terminal operation
Đáp án đúng: B

Câu 40. Đối với parallel stream, findAny() có đặc tính nào cần nhớ?
A. Luôn trả phần tử đầu theo encounter order như findFirst
B. Có thể trả một phần tử bất kỳ phù hợp, không cần phần tử đầu
C. Bắt buộc gom hết phần tử vào List trước khi trả giá trị
D. Luôn chọn phần tử xử lý cuối cùng trên main thread
Đáp án đúng: B

Câu 41. Vì sao accumulator của reduce trên parallel stream nên có tính kết hợp?
A. Parallel stream chỉ cho phép reducer là method static không state
B. reduce tự ghi đè phần tử không cùng hashCode khi gộp
C. Để accumulator thay đổi shared List có thể tránh đồng bộ
D. Các cách phân nhóm khác nhau phải cho kết quả tương thích
Đáp án đúng: D

Câu 42. Stream.collect(supplier, accumulator, combiner) khác reduce ở mục đích nào?
A. Hỗ trợ mutable reduction với container do supplier tạo
B. Bắt buộc dùng phép cộng số học trên primitive stream
C. Tự chuyển mọi container thành immutable object sau collect
D. Chỉ chạy combiner một lần cho mọi stream sequential
Đáp án đúng: A

Câu 43. Collectors.groupingBy(Person::city) thường trả cấu trúc nào?
A. Map từ city tới danh sách Person trong từng nhóm
B. List các city duy nhất nhưng bỏ dữ liệu Person
C. Map chỉ chứa một Person đầu tiên cho mỗi city
D. Stream các cặp city và Person chưa terminal operation
Đáp án đúng: A

Câu 44. Collectors.partitioningBy(predicate) phân vùng dữ liệu theo cách nào?
A. Tạo Map với khóa là mỗi giá trị unique của phần tử
B. Tạo List gồm các phần tử true, bỏ nhóm false
C. Tạo Stream<Optional<T>> cho từng kiểm tra Predicate
D. Map<Boolean,List<T>> với hai nhóm true và false
Đáp án đúng: D

Câu 45. Khi Collectors.toMap(keyMapper, valueMapper) gặp hai phần tử cùng key và không có merge function, điều gì xảy ra?
A. Có thể ném IllegalStateException do khóa bị trùng
B. Tự gộp hai value vào List mà không cần cấu hình
C. Giữ value cuối cùng theo thứ tự encounter bất kể stream
D. Bỏ phần tử đầu tiên và mặc định giữ phần tử thứ hai
Đáp án đúng: A

Câu 46. Stream.toList() trên Java 16+ trả List có tính chất nào?
A. ArrayList mutable và được phép thêm phần tử
B. List đồng bộ hóa mọi thao tác ghi từ các thread
C. List không cho thao tác thêm hoặc xóa phần tử
D. Danh sách live view có thể sửa nguồn Stream ban đầu
Đáp án đúng: C

Câu 47. Khi dùng Files.lines(path) để tạo stream dữ liệu từ file, cách quản lý tài nguyên nào phù hợp?
A. Chỉ gọi map là đã tự đóng file descriptor ngay lập tức
B. Để Stream sống trong static field tới khi JVM shutdown
C. Dùng parallel() để file tự đóng khi mọi thread hoàn tất
D. Dùng try-with-resources để đóng stream sau khi xử lý
Đáp án đúng: D

Câu 48. Khi lambda được gán cho Function<T,R> cần gọi API ném checked exception, cần làm gì?
A. Để lambda ném checked exception trực tiếp, compiler tự bỏ qua
B. Thêm throws vào method apply của Function từ source JDK
C. Xử lý hoặc bọc checked exception vì apply không khai throws đó
D. Dùng @FunctionalInterface để biến checked exception thành runtime
Đáp án đúng: C
