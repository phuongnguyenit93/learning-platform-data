Câu 1: Trong Java 10+, `var count = 10;` suy luận kiểu tĩnh nào cho `count`?
A. `long` (kiểu nguyên thủy).
B. `int` (kiểu nguyên thủy).
C. `Number` (kiểu tham chiếu).
D. `Integer` (kiểu tham chiếu).
Đáp án đúng: B

Câu 2: Điều gì xảy ra khi viết `var token = null;` trong phương thức?
A. Lỗi biên dịch vì `null` không cung cấp kiểu.
B. Biên dịch và suy luận `String` cho biến.
C. Biên dịch và suy luận `Object` cho biến.
D. Biên dịch với kiểu của lần gán kế tiếp vào biến.
Đáp án đúng: A

Câu 3: Vị trí nào cho phép dùng `var` trực tiếp kể từ Java 10?
A. Tham số phương thức nhận giá trị khi được gọi.
B. Kiểu trả về của phương thức có thân triển khai.
C. Biến cục bộ có biểu thức khởi tạo trong hàm.
D. Trường đối tượng có biểu thức khởi tạo trong lớp.
Đáp án đúng: C

Câu 4: Với `var items = new ArrayList<String>();`, kiểu tĩnh của `items` là gì?
A. `ArrayList<Object>` (generic Object).
B. `Collection<String>` (interface cha).
C. `ArrayList<String>` (lớp cụ thể).
D. `List<String>` (interface chung).
Đáp án đúng: C

Câu 5: Với `var names = new ArrayList<>();`, kiểu tĩnh nào được suy luận?
A. `ArrayList<Object>` (đối số Object).
B. `ArrayList<String>` (đối số String).
C. `ArrayList<?>` (ký tự đại diện).
D. `List<Object>` (kiểu interface List).
Đáp án đúng: A

Câu 6: Khai báo `var letters = List.of("a", "b");` có kiểu tĩnh nào?
A. `List<Object>` (phần tử Object).
B. `List<String>` (interface List).
C. `Collection<String>` (interface Collection).
D. `ArrayList<String>` (lớp ArrayList).
Đáp án đúng: B

Câu 7: Trong `for (var item : List.of("a", "b"))`, kiểu tĩnh của `item` là gì?
A. `CharSequence` (kiểu phần tử).
B. `Object` (kiểu phần tử).
C. `Character` (kiểu phần tử).
D. `String` (kiểu phần tử).
Đáp án đúng: D

Câu 8: Trong `for (var i = 0; i < 5; i++)`, trình biên dịch suy luận `i` là gì?
A. `Integer` (tham chiếu).
B. `short` (nguyên thủy).
C. `int` (nguyên thủy).
D. `long` (nguyên thủy).
Đáp án đúng: C

Câu 9: Với `try (var input = new StringReader("abc")) { ... }`, điều gì đúng?
A. `input` có kiểu `StringReader` và tự đóng sau `try`.
B. `input` có kiểu `Reader` và phải đóng trong `finally`.
C. `input` có kiểu `StringReader` nhưng không tự đóng.
D. `input` có kiểu `Reader` và tự đóng sau `try`.
Đáp án đúng: A

Câu 10: Trong phương thức có `final var requestId = "A";`, `final` bảo đảm điều gì?
A. Mọi đối tượng được gán bằng `var` đều bất biến.
B. Không thể gọi bất kỳ phương thức nào trên `requestId`.
C. Không thể so sánh `requestId` bằng `equals()`.
D. Không thể gán một giá trị khác cho `requestId`.
Đáp án đúng: D

Câu 11: Hai lệnh `var n = 1; n = null;` có kết quả gì?
A. Lỗi biên dịch vì `n` mang kiểu nguyên thủy `int`.
B. Hợp lệ vì compiler boxing `n` từ `int` thành `Integer` khi gán.
C. Lỗi ở khai báo đầu vì `var` không nhận số.
D. Hợp lệ vì `var` đổi kiểu theo từng lần gán.
Đáp án đúng: A

Câu 12: Với `var text = (String) null;`, nhận định nào chính xác?
A. Biên dịch được; `text` có kiểu tĩnh `String`.
B. Lỗi vì mọi biến dùng `var` đều cấm giá trị null.
C. Có `NullPointerException` ngay lúc khởi tạo.
D. Biên dịch được; `text` được suy luận là `Object`.
Đáp án đúng: A

Câu 13: Vì sao `var op = (String s) -> s.trim();` không biên dịch?
A. Lambda này tự suy luận `UnaryOperator<String>`.
B. Lambda này tự suy luận `Predicate<String>`.
C. Biểu thức lambda cần kiểu đích để xác định kiểu.
D. Lambda này tự suy luận `Function<String,String>`.
Đáp án đúng: C

Câu 14: Vì sao `var op = String::trim;` không phải khai báo hợp lệ?
A. Nó tự suy luận kiểu `UnaryOperator<String>`.
B. Method reference cần kiểu đích từ ngữ cảnh.
C. Nó tự suy luận kiểu `Function<String,String>`.
D. Nó tự suy luận kiểu `Supplier<String>`.
Đáp án đúng: B

Câu 15: `var values = new int[]{2, 3};` suy luận kiểu của `values` là gì?
A. `List<Integer>` (kiểu danh sách).
B. `Integer[]` (mảng kiểu wrapper).
C. `Object[]` (mảng kiểu tham chiếu).
D. `int[]` (mảng số nguyên thủy).
Đáp án đúng: D

Câu 16: Tại sao `var values = {2, 3};` bị lỗi biên dịch?
A. Trình biên dịch tự suy luận mảng `Object[]`.
B. Trình biên dịch tự suy luận `List<Integer>`.
C. Cú pháp khởi tạo mảng cần một kiểu đích.
D. Trình biên dịch tự suy luận mảng `int[]`.
Đáp án đúng: C

Câu 17: Khi viết `var first = 1, second = 2;`, điều gì xảy ra?
A. Hợp lệ vì cú pháp cho nhiều biến cùng suy luận kiểu `int`.
B. Lỗi biên dịch vì `var` chỉ khai báo một biến mỗi lần.
C. Hợp lệ; hai biến đều suy luận thành `Integer`.
D. Chương trình ném lỗi khi truy cập biến thứ hai.
Đáp án đúng: B

Câu 18: Trong một lớp, `private var cache = new HashMap<>();` có hợp lệ không?
A. Có; trường được suy luận là `Object` mặc định.
B. Có; trường được suy luận `Map<Object,Object>`.
C. Có; trường được suy luận `HashMap<Object,Object>`.
D. Không; `var` không thể khai báo trường của lớp.
Đáp án đúng: D

Câu 19: Phương thức `var parse() { return 42; }` có hợp lệ trong Java 10+ không?
A. Không; `var` không dùng làm kiểu trả về phương thức.
B. Có; Java suy luận `Integer` sau khi boxing giá trị trả về.
C. Có; kiểu trả về tự suy luận thành `int`.
D. Có; kiểu trả về tự suy luận thành `Object`.
Đáp án đúng: A

Câu 20: Chữ ký `void handle(var arg) {}` có hợp lệ cho phương thức thường không?
A. Có; kiểu `arg` mặc định thành `Object`.
B. Không; tham số phương thức cần khai báo kiểu rõ ràng.
C. Có; kiểu `arg` suy luận từ đối số khi gọi hàm.
D. Có; chỉ bị cấm khi phương thức là `static`.
Đáp án đúng: B

Câu 21: Với `var list = List.of("a"); list.add("b");`, kết quả là gì?
A. Lệnh `add` trả về `false` và giữ danh sách nguyên trạng.
B. Không biên dịch vì `var` làm biến chỉ đọc.
C. Thêm phần tử `"b"` thành công vào `list`.
D. `add` ném `UnsupportedOperationException` khi chạy.
Đáp án đúng: D

Câu 22: Với `var list = new ArrayList<String>(); list = new LinkedList<String>();`, kết quả là gì?
A. Hợp lệ vì `var` thay đổi kiểu khi gán lại.
B. Lỗi biên dịch vì `list` có kiểu `ArrayList<String>`.
C. Hợp lệ vì hai đối tượng đều thuộc interface `List<String>`.
D. Lỗi chạy vì hai lớp dùng chung kiểu generic.
Đáp án đúng: B

Câu 23: Cho `var obj = new Object() { int code = 7; };`. Phát biểu nào đúng về `obj.code`?
A. Lỗi biên dịch vì `var` cấm các lớp vô danh.
B. Truy cập hợp lệ vì suy luận được kiểu lớp vô danh.
C. Ném `ClassCastException` khi truy cập trường.
D. Lỗi biên dịch vì `Object` không có trường `code`.
Đáp án đúng: B

Câu 24: Nếu biên dịch mã có khai báo `var x = 1;` bằng `javac --release 9`, kết quả nào đúng?
A. Chạy được nhưng trình biên dịch cảnh báo về `var`.
B. Hợp lệ vì Java 9 cũng suy luận kiểu từ initializer.
C. Bị từ chối vì cú pháp suy luận `var` bắt đầu từ Java 10.
D. Hợp lệ nếu thêm lệnh `import java.lang.var`.
Đáp án đúng: C

Câu 25: Tạo `snap = List.copyOf(source)` từ `ArrayList` rồi thêm phần tử vào `source`. Điều gì đúng?
A. `snap` sẽ tự xóa phần tử cũ khi nguồn đổi.
B. `snap` sẽ chặn mọi thay đổi trên `source`.
C. `snap` giữ các phần tử tại thời điểm gọi `copyOf`.
D. `snap` sẽ tự phản ánh phần tử vừa thêm vào `source`.
Đáp án đúng: C

Câu 26: Tạo `view = Collections.unmodifiableList(source)` rồi thêm phần tử vào `source`. Điều gì đúng?
A. `view` phản ánh phần tử mới trong `source`.
B. `view` tự tách khỏi nguồn sau lần chỉnh sửa.
C. `view` tự biến thành bản sao qua `List.copyOf`.
D. `view` luôn giữ đúng ảnh chụp của lúc tạo.
Đáp án đúng: A

Câu 27: `List.copyOf(Arrays.asList("a", null))` có kết quả nào?
A. Bỏ qua `null` và chỉ lưu phần tử `"a"`.
B. Trả về danh sách bất biến chứa cả `null`.
C. Ném `IllegalArgumentException` vì có `null`.
D. Ném `NullPointerException` vì có `null`.
Đáp án đúng: D

Câu 28: Với `List.copyOf(List.of("x", "x"))`, điều gì đúng?
A. Tự bỏ một phần tử `"x"` vì chúng trùng nhau.
B. Ném `IllegalArgumentException` do trùng phần tử.
C. Giữ hai phần tử `"x"` theo đúng thứ tự ban đầu.
D. Đảo thứ tự vì danh sách kết quả bất biến.
Đáp án đúng: C

Câu 29: `Set.copyOf(List.of("x", "x"))` trả về kết quả nào?
A. Ném `IllegalArgumentException` do phần tử trùng.
B. Một `Set` chỉ chứa một phần tử `"x"`.
C. Một `Set` chứa hai bản sao phần tử `"x"`.
D. Ném `UnsupportedOperationException` lúc khởi tạo.
Đáp án đúng: B

Câu 30: Khi collection đầu vào của `Set.copyOf` chứa `null`, kết quả nào đúng?
A. Bỏ qua phần tử `null` và tiếp tục tạo.
B. Ném `NullPointerException` lúc tạo `Set`.
C. Ném `ClassCastException` vì phần tử `null`.
D. Giữ lại một phần tử `null` trong `Set`.
Đáp án đúng: B

Câu 31: Điều gì xảy ra nếu `Map.copyOf(source)` nhận Map có khóa `null`?
A. Ném `NullPointerException` khi sao chép.
B. Giữ nguyên khóa `null` trong Map bất biến.
C. Đổi khóa `null` thành chuỗi `"null"`.
D. Bỏ khóa `null` và giữ các entry còn lại.
Đáp án đúng: A

Câu 32: Nếu Map nguồn có `a -> 1` và `b -> 1`, `Map.copyOf` xử lý ra sao?
A. Ném `IllegalStateException` vì giá trị trùng.
B. Loại một entry do hai giá trị trùng nhau.
C. Giữ cả hai entry vì các khóa vẫn khác nhau.
D. Gộp hai khóa thành một entry chung.
Đáp án đúng: C

Câu 33: Với kết quả `Map.copyOf(linkedMap)`, có thể dựa vào thứ tự duyệt nào?
A. Thứ tự duyệt entry không được bảo đảm.
B. Luôn theo thứ tự tự nhiên của các khóa.
C. Luôn theo thứ tự đã chèn vào `linkedMap`.
D. Luôn theo thứ tự tăng của `hashCode`.
Đáp án đúng: A

Câu 34: `List.copyOf` chứa một `StringBuilder` rồi đối tượng đó được `append`. Điều gì đúng?
A. `copyOf` đã tạo bản sao sâu của `StringBuilder`.
B. Bản sao ngăn mọi lệnh `append` trên phần tử.
C. Lệnh `append` ném `UnsupportedOperationException`.
D. Nội dung phần tử vẫn có thể thay đổi.
Đáp án đúng: D

Câu 35: `Map.copyOf` nhận Map có giá trị là một `ArrayList` mutable. Sau đó sửa `ArrayList` thì sao?
A. Map kết quả tự sao chép sâu mọi phần tử của list.
B. Sửa list bị cấm vì Map kết quả là unmodifiable.
C. Map kết quả tự xóa entry chứa list bị sửa.
D. List làm giá trị trong Map kết quả vẫn có thể đổi.
Đáp án đúng: D

Câu 36: Nên dựa vào điều gì về danh tính đối tượng trả về từ `List.copyOf(input)`?
A. Luôn tạo một đối tượng khác với `input`.
B. Kết quả luôn là instance của một `ArrayList`.
C. Không có bảo đảm về identity của kết quả.
D. Luôn trả về chính đối tượng `input`.
Đáp án đúng: C

Câu 37: Với `var fixed = Map.copyOf(source); fixed.put("k", 1);`, điều gì xảy ra?
A. `put` làm Map tự chuyển thành `HashMap`.
B. `put` ném `UnsupportedOperationException`.
C. `put` thêm entry vào `source` thông qua view.
D. `put` trả `null` và bỏ qua yêu cầu thay đổi.
Đáp án đúng: B

Câu 38: `Stream.of("a", "b").collect(Collectors.toUnmodifiableList())` bảo đảm điều gì?
A. Không bảo đảm thứ tự nhưng cho phép thêm phần tử.
B. Giữ thứ tự gặp và không cho sửa danh sách.
C. Sắp xếp tăng dần và cho phép sửa danh sách.
D. Đảo thứ tự gặp phần tử và không cho sửa.
Đáp án đúng: B

Câu 39: `Stream.of("a", null).collect(Collectors.toUnmodifiableList())` có kết quả gì?
A. Bỏ `null` và trả về danh sách chỉ có `"a"`.
B. Ném `IllegalStateException` vì có giá trị rỗng.
C. Tạo danh sách bất biến chứa nguyên giá trị `null`.
D. Ném `NullPointerException` do gặp `null`.
Đáp án đúng: D

Câu 40: `Stream.of("a", "a", "b").collect(Collectors.toUnmodifiableSet())` xử lý trùng lặp ra sao?
A. Collector ném `IllegalStateException` vì có trùng.
B. Tập kết quả vẫn giữ hai bản sao giá trị `"a"`.
C. Kết quả chỉ có hai giá trị phân biệt `"a"` và `"b"`.
D. Collector tự đổi thành `List` để giữ phần tử.
Đáp án đúng: C

Câu 41: Dùng `Collectors.toUnmodifiableMap(k, v)` với hai phần tử sinh cùng khóa thì sao?
A. Giữ entry cuối cùng và ghi đè entry trước.
B. Giữ entry đầu tiên và bỏ qua entry sau.
C. Tạo hai entry độc lập cho cùng một khóa.
D. Ném `IllegalStateException` vì khóa trùng.
Đáp án đúng: D

Câu 42: Muốn xử lý khóa trùng khi thu thập vào unmodifiable Map, dùng cách nào?
A. Dùng overload nhận thêm hàm merge cho khóa trùng.
B. Dùng `toUnmodifiableSet` để giữ mọi cặp khóa.
C. Dùng overload hai tham số rồi tự gọi `put` để merge.
D. Dùng `List.copyOf` để gộp các entry trùng.
Đáp án đúng: A

Câu 43: Với `Collectors.toUnmodifiableMap(k, v)`, nếu `v` ánh xạ thành `null` thì sao?
A. Ghi entry với giá trị `null` vào Map kết quả.
B. Tự bỏ entry có giá trị `null` khỏi Map.
C. Chuyển giá trị `null` thành chuỗi rỗng.
D. Ném `NullPointerException` khi collect.
Đáp án đúng: D

Câu 44: Sự khác biệt chắc chắn giữa `Collectors.toList()` và `Collectors.toUnmodifiableList()` là gì?
A. Cả hai đều bảo đảm trả về danh sách có thể sửa.
B. Chỉ `toUnmodifiableList()` bảo đảm không thể sửa.
C. Collector thứ hai luôn giữ nguyên list nguồn.
D. Collector thứ nhất luôn tạo một `ArrayList`.
Đáp án đúng: B

Câu 45: Gọi `Optional.empty().orElseThrow()` không truyền tham số sẽ làm gì?
A. Tạo `Optional.empty()` mới rồi trả về.
B. Ném `IllegalArgumentException` khi Optional rỗng.
C. Trả về `null` khi Optional không có giá trị.
D. Ném `NoSuchElementException` khi Optional rỗng.
Đáp án đúng: D

Câu 46: `Reader.transferTo(Writer)` trả về giá trị biểu thị điều gì?
A. Số ký tự đã chuyển, dưới dạng `long`.
B. Số byte đã chuyển, dưới dạng `long`.
C. Số lần gọi `write()` đã thực hiện trên `Writer`.
D. Số dòng đã chuyển, dưới dạng `int`.
Đáp án đúng: A

Câu 47: Về quản lý tài nguyên, `reader.transferTo(writer)` bảo đảm điều gì?
A. Không tự đóng đối tượng đọc hay ghi.
B. Tự đóng cả hai ngay cả khi bị lỗi.
C. Tự đóng `writer` sau khi chuyển xong.
D. Tự đóng `reader` sau khi chuyển xong.
Đáp án đúng: A

Câu 48: `ByteArrayOutputStream.toString(StandardCharsets.UTF_8)` dùng cách giải mã nào?
A. Giải mã các byte bằng charset mặc định của JVM.
B. Trả về chuỗi ký tự đã ghi mà không giải mã.
C. Giải mã theo `UTF_8` được truyền vào.
D. Chuyển mỗi byte thành hai chữ số thập lục phân.
Đáp án đúng: C
