# Java 10 — Xây dựng quy ước sử dụng `var` dựa trên khả năng đọc và bảo trì

## Mục tiêu và phạm vi

`var` được giới thiệu trong **Java 10** (JEP 286) để suy luận **kiểu của biến cục bộ** từ biểu thức khởi tạo. Nó có thể loại bỏ kiểu khai báo bị lặp lại và giúp tên biến nổi bật hơn, nhưng nếu lạm dụng sẽ che giấu thông tin cần thiết để hiểu hoặc bảo trì mã nguồn.

Bài này đề xuất một **quy ước thực hành có thể đưa vào tài liệu coding convention của nhóm**, dựa trên các nguyên tắc vẫn áp dụng cho Java hiện đại. Đây là **quy ước gợi ý**, không phải một yêu cầu bắt buộc của Java Language Specification hay lời khẳng định rằng có một tỷ lệ `var` “đúng” cho mọi dự án.

**Nguyên tắc cốt lõi:** dùng `var` khi người đọc có thể hiểu vai trò của biến và kiểu cần thiết từ **tên biến, initializer và vài dòng ngữ cảnh gần đó**, ngay cả khi xem code review ngoài IDE. Giữ kiểu tường minh khi nó truyền đạt thông tin mà initializer chưa thể hiện rõ, hoặc khi kiểu là một phần quan trọng của thiết kế.

Sau khi học, bạn có thể:
1. Thiết lập tiêu chí thống nhất để chọn `var` hoặc kiểu khai báo tường minh.
2. Nhận diện vấn đề về tên biến, phạm vi sử dụng, kiểu generic, numeric literal và phụ thuộc implementation.
3. Đánh giá thay đổi khi refactor initializer để không làm sai ý nghĩa kiểu hoặc hành vi.
4. Xem xét các trường hợp đặc biệt: vòng lặp, `try-with-resources`, stream, factory, lambda và method reference.
5. Áp dụng checklist thực tế trong pull request và giải thích quyết định cho đồng đội.

## 1. Cơ sở kỹ thuật: `var` làm gì và không làm gì?

Ví dụ:

```java
var name = "An";                          // String
var count = 3;                            // int
var names = java.util.List.of("An", "Lan"); // List<String>
```

Đây là **các dòng minh họa đặt trong phương thức**. Trình biên dịch suy ra kiểu **tại compile time**, rồi kiểm tra các phép gọi phương thức và phép gán theo kiểu tĩnh đó. `var` không biến Java thành ngôn ngữ dynamic typing; khai báo `var count = 3;` không cho phép sau đó viết `count = "ba";`.

`var` dùng được trong các ngữ cảnh biến cục bộ phù hợp, bao gồm khối lệnh, phần khai báo biến của vòng `for`, biến của enhanced `for` và khai báo tài nguyên trong `try-with-resources`. Trong Java 10, nó **không** thay kiểu của field, tham số phương thức thông thường hoặc kiểu trả về của phương thức. Cú pháp `var` trong **tham số lambda** được mở rộng ở Java 11, vẫn có quy tắc riêng và không thay đổi tiêu chí chọn kiểu cho biến cục bộ ở bài này.

Một số dạng không hợp lệ:

```java
var missing;            // Không có initializer
var nothing = null;     // Không suy ra được kiểu từ null
var transform = x -> x; // Lambda đứng riêng thiếu functional-interface target type
var method = String::trim; // Method reference đứng riêng thiếu target type
```

**Quy ước số 0:** chỉ cân nhắc `var` sau khi câu lệnh hợp lệ về mặt ngôn ngữ. Các ví dụ không hợp lệ không thể được “sửa” bằng một quy tắc style.

## 2. Quy ước đề xuất — sáu nguyên tắc ưu tiên

### Q1. Ưu tiên khả năng đọc của người bảo trì

Một dòng dùng `var` đạt yêu cầu khi người đọc trả lời được nhanh:

- Biến biểu diễn **dữ liệu hoặc vai trò** gì?
- Loại thao tác hợp lệ kế tiếp là gì?
- Có thông tin kiểu nào quan trọng đang bị giấu đi không?
- Người đọc có cần mở định nghĩa phương thức hoặc hover IDE **chỉ để biết biến là gì** không?

So sánh:

```java
var x = service.fetch(id);          // Khó đoán x là gì, fetch trả gì

OrderSummary summary = service.fetch(id); // Ý nghĩa kiểu rõ hơn
```

Đây là mảnh mã minh họa; `service`, `id` và `OrderSummary` giả định đã khai báo. Với một API có tên tốt hơn, `var summary = service.fetchSummary(id);` **có thể** đã đủ rõ. Quy ước nên đánh giá cả tên biến lẫn thiết kế API, không chỉ đếm `var`.

### Q2. Chỉ bỏ kiểu khi initializer đã mang thông tin đủ mạnh

Trường hợp rất phù hợp:

```java
var buffer = new StringBuilder();
var nameCounts = new java.util.HashMap<String, Integer>();
var names = java.util.List.of("An", "Lan");
```

Kiểu xuất hiện trong `new ...` hoặc có thể suy ra dễ dàng từ factory `List.of(...)` và dữ liệu đầu vào. Việc viết lại `StringBuilder buffer = new StringBuilder();` thường chỉ lặp thông tin.

Trường hợp cần cân nhắc:

```java
var result = repository.find(id);
var value = processor.execute(command);
var data = parse(input);
```

Nếu không đọc hợp đồng phương thức, người xem khó biết `result` là `Optional<Order>`, `Order`, `Map` hay một kiểu khác. Có thể thay bằng kiểu tường minh hoặc cải thiện tên phương thức/tên biến; lựa chọn phụ thuộc ngữ cảnh thực tế.

### Q3. Tên biến phải truyền đạt ý nghĩa nghiệp vụ

Tránh tên chung chung như `x`, `data`, `obj`, `tmp`, `res`, nhất là khi dùng `var`. Chọn tên phản ánh **vai trò**: `activeCustomers`, `priceBySku`, `unpaidInvoices`, `timeoutMillis`, `validatedToken`.

Ví dụ:

```java
var data = fetchOrders(customerId);              // Ít thông tin
var pendingOrders = fetchPendingOrders(customerId); // Tốt hơn nếu đúng hợp đồng
```

Chỉ đổi tên đủ để `var` có ích **khi hàm trả về và ngữ cảnh thực sự rõ**. Không nên nhét toàn bộ tên kiểu vào tên biến theo kiểu `arrayListOfOrderEntities` chỉ để bù cho thiếu kiểu.

### Q4. Giữ phạm vi biến ngắn, khai báo gần lúc sử dụng

Một biến khai báo ở đầu phương thức rồi dùng cách hàng chục dòng khiến việc lần theo initializer khó khăn. Nên đặt khai báo gần lần sử dụng đầu tiên; tách phương thức dài thành những bước có trách nhiệm rõ.

Ví dụ:

```java
for (var customer : customers) {
    var normalizedName = customer.name().strip();
    System.out.println(normalizedName);
}
```

Đây là mảnh minh họa giả định `customers` chứa các đối tượng có `name()` trả `String`. Vòng lặp ngắn giúp người đọc nắm loại phần tử và mục đích dùng biến.

Ngược lại, nếu một biến mang trạng thái qua nhiều nhánh, qua nhiều biến đổi hoặc nhiều trang code, việc giữ kiểu tường minh đôi khi có lợi. Dù vậy, cách sửa tốt hơn có thể là **giảm phạm vi và độ phức tạp** trước khi quyết định thay `var` bằng kiểu tường minh.

### Q5. Giữ kiểu tường minh khi đó là thông tin thiết kế

Các thông tin đáng thể hiện trực tiếp ở vế trái có thể gồm:
- Interface hoặc abstraction mà đoạn code chủ đích phụ thuộc (`List` thay vì `ArrayList`, `Map` thay vì `HashMap`).
- Generic type quan trọng khi một initializer mơ hồ hoặc bị suy luận quá rộng.
- Kiểu số bắt buộc theo giao thức/đơn vị (`long`, `byte`, `BigDecimal`) nếu literal không nói rõ.
- Một kiểu domain quan trọng với business logic (`Money`, `OrderId`, `Optional<Customer>`), nhất là khi tên phương thức trả về chưa rõ.

Ví dụ:

```java
List<String> names = new ArrayList<>();    // Nhấn mạnh hợp đồng List<String>
var names2 = new ArrayList<String>();     // Kiểu suy ra: ArrayList<String>
```

Cả hai đều hợp lệ nếu có import `List` và `ArrayList`. Chọn cách nào tùy mục tiêu đọc hiểu và mức độ cần phụ thuộc vào interface. **Không có luật Java nào buộc biến cục bộ luôn dùng kiểu interface**; vấn đề là mức phụ thuộc vào implementation có đáng lo trong phạm vi đó không.

### Q6. Chấp nhận kết hợp `var` và kiểu tường minh trong một phương thức

Đừng đưa ra luật “mọi biến cục bộ đều phải dùng `var`” hoặc “không biến nào được dùng `var`”. Tính nhất quán có giá trị khi cùng tiêu chí cho cùng loại tình huống, **không** đòi mọi dòng trông giống nhau.

```java
var names = List.of("Lan", "An");       // Factory + dữ liệu đủ rõ
Map<String, Integer> agesByName = loadAges(); // Hợp đồng generic quan trọng
var adults = names.stream()
        .filter(name -> agesByName.getOrDefault(name, 0) >= 18)
        .toList();
```

Đây là **mảnh code minh họa**, giả định có `import java.util.List;`, `java.util.Map;` và `loadAges()` hợp lệ. `Stream.toList()` là API từ Java 16, phù hợp khi dự án target Java 17+. Nó không xuất hiện ở Java 10; khi cần target Java 10, dùng collector thích hợp hoặc API sẵn có ở bản đó.

## 3. Bảng quyết định dùng trong code review

| Tình huống | Quy ước khuyến nghị | Lý do |
|---|---|---|
| `new StringBuilder()` hoặc constructor chỉ rõ kiểu | Thường dùng `var` | Vế phải đủ thông tin, bỏ được lặp từ |
| `List.of("A", "B")`, `Map.of(...)` với phần tử rõ | Thường dùng `var` | Dễ đoán interface và generic |
| Enhanced `for` duyệt collection đã biết kiểu | Thường dùng `var` nếu tên biến rõ | Kiểu phần tử có sẵn từ tập hợp, phạm vi ngắn |
| `try (var reader = Files.newBufferedReader(path))` | Có thể dùng `var` | Initializer nói rõ kiểu resource |
| `service.execute(request)` trả kiểu ít hiển thị | Ưu tiên kiểu tường minh hoặc tên API rõ hơn | Tránh yêu cầu người đọc nhảy sang định nghĩa |
| `new ArrayList<>()` thiếu ngữ cảnh generic | Không dùng `var` đơn giản như vậy | Có thể suy ra `ArrayList<Object>` |
| Số nguyên literal `1` nhưng cần `long` hoặc `byte` | Khai báo tường minh hoặc dùng literal có suffix | `var` có thể suy ra sai kiểu mong muốn |
| Code cần bộc lộ interface/contract | Cân nhắc kiểu tường minh | Tránh phụ thuộc vô tình vào implementation |
| Biến chỉ dùng trong vài dòng kế tiếp | `var` thường phù hợp hơn | Dễ hiểu qua ngữ cảnh cục bộ |
| Biến nhiều nhánh, thời gian sống dài | Xem lại thiết kế, thường nên rõ kiểu | Khó theo dõi initializer và kiểu |
| Lambda/method reference đứng độc lập sau dấu `=` | Cần kiểu functional interface tường minh | Lambda/reference không có target type từ `var` |
| Field, tham số phương thức và kiểu trả về | Dùng kiểu khai báo hợp lệ | `var` cục bộ không áp dụng ở đây |

Các hàng mô tả **khuyến nghị style**, ngoại trừ những hàng bị giới hạn bởi cú pháp Java. Trường hợp đặc biệt cần có lý do, không buộc sửa máy móc.

## 4. Bẫy kiểu generic: `var` kết hợp diamond và factory rỗng

Đây là một trong những điểm có ảnh hưởng bảo trì lớn nhất.

```java
// Dễ lệch ý định: không có target type cho diamond.
var items = new ArrayList<>();       // Thường suy ra ArrayList<Object>
items.add("An");
items.add(123);                      // Vẫn hợp lệ vì phần tử là Object

// Cách thể hiện ý định lưu String:
var names = new ArrayList<String>(); // ArrayList<String>
List<String> moreNames = new ArrayList<>(); // List<String>

// Factory rỗng cũng cần lưu ý về target type:
var empty = List.of();               // List<Object>
List<String> typedEmpty = List.of(); // List<String>
```

Đây là các mảnh mã cần import `java.util.ArrayList` và `java.util.List`. Trong `var items = new ArrayList<>();`, nếu constructor không cung cấp đủ ngữ cảnh, generic có thể suy luận thành `Object`. Sau đó, việc thêm phần tử `String` **không** khiến type parameter thay đổi thành `String`.

**Quy ước:** khi dùng `var` với constructor generic, hãy ghi type argument ở vế phải nếu không thể suy ra chính xác từ đối số. Với generic factory rỗng, cân nhắc khai báo kiểu bên trái hoặc type witness (`List.<String>of()`). Đừng sửa chỉ bằng việc thêm một cast không cần thiết.

Một tình huống khác: `var copy = new ArrayList<>(existingNames);` **có thể** suy luận `String` khi `existingNames` đã có kiểu `Collection<String>` và constructor có ngữ cảnh phù hợp. Luôn kiểm tra kiểu thực tế, không kết luận mọi dấu `<>` đều sai.

## 5. Số, boxing và đơn vị: đừng che mất kiểu quan trọng

`var` suy luận theo **kiểu của biểu thức khởi tạo**, không theo kiểu người viết định dùng sau này.

```java
var retries = 3;          // int
var timeoutMillis = 1500L; // long
var ratio = 1.5;          // double
var probability = 0.5f;   // float
```

Mặc định, literal số nguyên không có suffix là `int` khi trong phạm vi của nó; literal có `L` là `long`. Nếu một API, đơn vị đo hoặc phép tính cần kiểu cụ thể, nên viết sao cho kiểu đó được thể hiện rõ.

```java
long durationMillis = 1000;  // Rõ hợp đồng long
var durationNanos = 1000L;   // Cũng là long, rõ qua suffix
byte flags = 0;              // byte, không phải int
```

**Quy ước:** ưu tiên thông tin về **đơn vị** trong tên biến (`timeoutMillis`, `sizeBytes`) và kiểu phù hợp với hợp đồng. Không chuyển `long durationMillis = 1000;` thành `var durationMillis = 1000;` nếu sẽ vô tình làm kiểu thành `int`. Với số tiền, cân nhắc `BigDecimal` và cách khởi tạo thích hợp thay vì mặc định `double`.

## 6. Tính trừu tượng và rủi ro khi refactor initializer

Trong Java, `var` có thể suy ra kiểu concrete implementation:

```java
var queue = new ArrayDeque<String>(); // ArrayDeque<String>
Deque<String> abstraction = new ArrayDeque<>(); // Deque<String>
```

Cả hai hợp lệ với import `java.util.ArrayDeque` và `Deque`. Biến `queue` có thể nhìn thấy thành viên riêng của `ArrayDeque`; biến `abstraction` chỉ dùng API của `Deque`. Nếu đoạn code cần thể hiện rõ việc không phụ thuộc implementation, nên cân nhắc kiểu `Deque<String>`. Trong block ngắn, `var` thường vẫn ổn nếu các thao tác đều phổ biến và sự phụ thuộc cụ thể không gây rủi ro.

**Điểm cần kiểm tra trong pull request:** một sửa đổi initializer có thể thay luôn **kiểu được suy ra**, dù dòng khai báo `var` không đổi.

Ví dụ minh họa về thay đổi ngữ nghĩa:

```java
var userIds = new ArrayList<String>();
userIds.add("u2");
userIds.add("u1");
for (var userId : userIds) {
    // Thứ tự duyệt theo thứ tự thêm phần tử.
}
```

Nếu sau này thay `new ArrayList<String>()` bằng một loại `Set` không bảo đảm thứ tự duyệt, kết quả thuật toán có thể đổi dù các method mà code gọi vẫn biên dịch được. Lỗi ở đây là **thay đổi hợp đồng về thứ tự**, không phải `var` gây mất an toàn kiểu.

**Quy ước:** khi refactor initializer của biến `var`, reviewer cần so sánh:
1. Kiểu tĩnh cũ và mới;
2. Generic type, mutability, khả năng chứa `null`, thứ tự duyệt;
3. Những lời gọi method ở các dòng sau;
4. Test cho hành vi phụ thuộc vào collection hoặc implementation.

Nếu kiểu là một quyết định kiến trúc, hãy nêu nó rõ bằng interface/class hoặc phương thức có kiểu trả về có tên.

## 7. Dùng `var` để giúp đọc stream hoặc chuỗi lệnh dài

Một pipeline khó đọc không tự trở nên rõ hơn chỉ nhờ thay kiểu bằng `var`. Nhưng việc đặt tên cho các kết quả trung gian thường tăng khả năng bảo trì.

Ví dụ (mảnh code trong một phương thức, `orders` là danh sách đối tượng có `isPaid()` và `total()`):

```java
var paidOrders = orders.stream()
        .filter(Order::isPaid)
        .toList();

var totalPaid = paidOrders.stream()
        .map(Order::total)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Mẫu này cần các khai báo/import `Order`, `BigDecimal` và môi trường Java 16+ do dùng `Stream.toList()`; nó là ví dụ về **cách tổ chức code hiện đại**, không phải API `Stream.toList()` có từ Java 10.

Nếu tên `totalPaid` vẫn quá mơ hồ về kiểu đơn vị tiền hoặc ngữ nghĩa, dùng `BigDecimal totalPaid = ...` có thể làm đoạn code dễ hiểu hơn. Nếu các bước được đặt tên tốt, viết lại toàn bộ generic type cho kết quả trung gian có thể làm rối phần quan trọng.

**Quy ước:** ưu tiên **tên biến theo kết quả nghiệp vụ** và chia pipeline ở các ranh giới có ý nghĩa; không thêm biến trung gian chỉ vì có thể dùng `var`.

## 8. Biến vòng lặp và tài nguyên

### 8.1. Enhanced `for`

```java
var names = List.of("An", "Lan");
for (var name : names) {
    System.out.println(name);
}
```

Đoạn này hợp lệ trong phương thức nếu import `List`. Kiểu phần tử được suy ra từ collection và người đọc thấy ngữ cảnh ngay trên vòng lặp. Với vòng lặp duyệt `Map.Entry` có kiểu generic dài, `var entry` cũng có thể làm code bớt nhiễu:

```java
for (var entry : counts.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

Đoạn sau giả định `counts` là một `Map` có kiểu tham số rõ. Đừng thay tên `entry` bằng `e` nếu nó gây khó đọc ở vòng lặp dài.

### 8.2. `try-with-resources`

Khi kiểu resource thể hiện rõ trên vế phải, `var` có ích:

```java
try (var reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
```

Đây là mảnh mã cần `import java.nio.file.Files;` và biến `path` kiểu `Path`, nằm trong phương thức khai báo/xử lý `IOException` phù hợp. `reader` được suy ra là `BufferedReader` và tài nguyên được đóng tự động sau block.

**Quy ước:** `var` không thay đổi trách nhiệm đóng resource. Nếu API trả `Stream` dùng tài nguyên, vẫn phải xem xét vòng đời và xử lý đóng ở nơi phù hợp. Không dùng `var` để che thông tin về ownership hoặc side effect.

## 9. Đừng nhầm `var` và lambda: hai quy tắc suy luận khác nhau

Lambda và method reference là **poly expressions** cần **target functional interface**. Không thể gán trực tiếp cho biến `var` khi hoàn toàn không có target:

```java
var operation = x -> x + 1; // Sai: lambda thiếu target type
var trim = String::trim;    // Sai: method reference thiếu target type
```

Cách rõ ràng:

```java
IntUnaryOperator increment = x -> x + 1;
UnaryOperator<String> trim = String::trim;
```

Cần import `java.util.function.IntUnaryOperator` và `UnaryOperator`. Nếu method nhận đối số functional interface, bên trong lời gọi đã có kiểu đích, nên **có thể** dùng `var` cho **kết quả lời gọi**:

```java
var cleaned = names.stream()
        .map(String::strip)
        .toList();
```

`names` giả định là `List<String>`, JDK target Java 17+. Trình biên dịch có target cho `String::strip` từ `Stream.map`, trong khi `var cleaned` suy ra kiểu từ lời gọi `toList()`.

Cú pháp `(var x) -> ...` của **Java 11** chỉ là cách khai báo tham số lambda; nó **không** có nghĩa `var operation = (var x) -> ...;` được phép khi chưa có target interface.

## 10. Ví dụ thực hành hoàn chỉnh trên Java 17+

Tệp: **`VarConventionDemo.java`**. Đoạn này chủ động phối hợp `var` với các khai báo tường minh theo quy ước. `List.of` (Java 9), `var` (Java 10), `String.strip` (Java 11) và `Stream.toList` (Java 16) là những API/cú pháp ổn định, có thể dùng với target Java 17.

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class VarConventionDemo {

    static List<String> activeNames() {
        return List.of(" Lan ", " An ", " Minh ");
    }

    static Map<String, Integer> buildLengths(List<String> source) {
        // Constructor có đủ generic type, nên dùng var hợp lý.
        var result = new LinkedHashMap<String, Integer>();

        // Tên biến và phạm vi sử dụng đều ngắn, rõ.
        for (var rawName : source) {
            var name = rawName.strip();
            result.put(name, name.length());
        }
        return result;
    }

    public static void main(String[] args) {
        var names = activeNames();

        // Nêu rõ hợp đồng Map<String, Integer> khi kết quả API quan trọng.
        Map<String, Integer> lengthByName = buildLengths(names);

        // Đặt tên cho kết quả stream; List<String> được suy luận.
        var cleanedNames = names.stream()
                .map(String::strip)
                .toList();

        // Cố ý nêu rõ long và đơn vị để tránh đổi kiểu vô tình.
        long timeoutMillis = 1500L;

        // final giữ tham chiếu không bị gán lại, không đổi kiểu suy luận.
        final var firstName = names.get(0).strip();

        // Có generic argument, tránh ArrayList<Object>.
        var mutableNames = new ArrayList<String>();
        mutableNames.add(firstName);

        System.out.println("first=" + firstName);
        System.out.println("lengths=" + lengthByName);
        System.out.println("clean=" + cleanedNames);
        System.out.println("timeoutMillis=" + timeoutMillis);
        System.out.println("mutable=" + mutableNames);
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 VarConventionDemo.java
java VarConventionDemo
```

Stdout:

```text
first=Lan
lengths={Lan=3, An=2, Minh=4}
clean=[Lan, An, Minh]
timeoutMillis=1500
mutable=[Lan]
```

Phân tích:

1. `activeNames()` trả `List<String>`; `var names` nhận kiểu tĩnh này. Tên hàm và tên biến giúp người đọc hiểu dữ liệu.
2. `buildLengths()` có kiểu trả về rõ ở API; `lengthByName` được khai báo là `Map<String, Integer>` để nhấn mạnh hợp đồng bản đồ tên-độ dài, dù cũng có thể dùng `var` nếu ngữ cảnh đủ rõ.
3. `var result = new LinkedHashMap<String, Integer>()` tránh lặp kiểu ở hai phía nhưng **không đánh mất generic type**; sử dụng `LinkedHashMap` còn giúp kết quả in theo thứ tự thêm vào.
4. `var rawName` và `var name` sống trong vòng lặp ngắn, dễ theo dõi.
5. `var cleanedNames` sử dụng API stream ổn định trên Java 17; kiểu trả về rõ từ chain `toList()` và dữ liệu nguồn.
6. `long timeoutMillis` thể hiện loại số và đơn vị quan trọng; `final var firstName` chứng minh `final` phối hợp với suy luận kiểu nhưng không biến đối tượng thành immutable.
7. `var mutableNames = new ArrayList<String>()` sử dụng type argument cụ thể, tránh bẫy `Object`.

### 10.1. Chương trình nhỏ để kiểm chứng suy luận generic

Tệp: **`TypeInferenceDemo.java`**:

```java
import java.util.ArrayList;

public class TypeInferenceDemo {
    public static void main(String[] args) {
        var broad = new ArrayList<>();
        broad.add("one");
        broad.add(2);

        var typed = new ArrayList<String>();
        typed.add("one");

        int count = typed.size();
        long total = 1L;

        System.out.println("broad=" + broad);
        System.out.println("typed=" + typed);
        System.out.println("count=" + count);
        System.out.println("total=" + total);
    }
}
```

```bash
javac --release 17 TypeInferenceDemo.java
java TypeInferenceDemo
```

```text
broad=[one, 2]
typed=[one]
count=1
total=1
```

Điểm cần hiểu: `broad` có kiểu `ArrayList<Object>` nên cả chuỗi và số đều được chấp nhận. Đây là ví dụ **biên dịch thành công nhưng dễ lệch ý định thiết kế**; dùng `typed` để giới hạn kiểu phần tử. Không phải mọi trường hợp `var` đều khiến code lỗi biên dịch ngay khi thiếu thông tin.

## 11. Đưa quy ước vào dự án: đoạn chính sách có thể áp dụng

Đây là **mẫu quy ước nhóm đề xuất**. Có thể chép phần này vào tài liệu coding standards sau khi nhóm thống nhất:

> **Local-variable type inference (`var`):** Chúng ta dùng `var` cho biến cục bộ khi initializer hoặc kiểu dữ liệu xung quanh cho phép người đọc hiểu loại giá trị và vai trò của biến ngay trong cùng một đoạn code. Tên biến phải mang ý nghĩa, phạm vi sử dụng nên ngắn. Chúng ta viết kiểu tường minh nếu kiểu là hợp đồng quan trọng, nếu initializer mơ hồ, hoặc nếu suy luận generic/numeric có thể khác ý định. Khi chuyển sang `var`, phải kiểm tra kiểu suy luận, tính khả biến, API được gọi và tác động của refactor. Không áp tỷ lệ `var`, không sửa chỉ để “đồng bộ hình thức”; thay đổi style cần phục vụ khả năng đọc và bảo trì.

Để triển khai hiệu quả, nhóm có thể thống nhất:

- **Mức 1 — Luôn kiểm tra tính hợp lệ:** `var` chỉ dùng ở ngữ cảnh Java hỗ trợ; không chấp nhận initializer `null`, lambda/method reference không có target, hoặc khai báo biến thiếu initializer.
- **Mức 2 — Kiểm tra ý nghĩa kiểu:** generic và numeric phải suy ra đúng theo yêu cầu, tránh `Object` hoặc `int` không mong muốn.
- **Mức 3 — Đánh giá khả năng đọc:** tên biến, initializer, scope và thông tin kiểu mà reviewer cần biết.
- **Mức 4 — Đánh giá rủi ro bảo trì:** implementation, contract, resource lifetime và hành vi khi thay initializer.
- **Mức 5 — Chỉ tự động hóa điều chắc chắn:** formatter/linter có thể phát hiện hoặc gợi ý kiểu, nhưng không tự thay toàn bộ khai báo bằng `var` nếu làm giảm khả năng hiểu mã.

Các mức là trình tự cân nhắc, không phải thang điểm bắt buộc. Team có thể chấp nhận các ngoại lệ có lý do.

## 12. Checklist review pull request

Dùng checklist sau với **những thay đổi có tác động thực tế đến kiểu hoặc khả năng đọc**:

- [ ] Kiểu suy ra từ initializer có đúng như ý định không (bao gồm generic, primitive, boxing)?
- [ ] Người đọc hiểu được vai trò biến và kiểu cần thiết mà không cần IDE hoặc tìm xa không?
- [ ] Tên biến diễn đạt nghiệp vụ và không chỉ là `x`, `data`, `result` vô nghĩa?
- [ ] Biến được khai báo gần nơi dùng, phạm vi đủ ngắn để truy lại initializer?
- [ ] Thông tin kiểu quan trọng (`List`, `Map`, domain value, đơn vị đo, khả năng null) có bị che khuất?
- [ ] Nếu initializer tạo concrete collection, code có phụ thuộc vào đặc tính riêng như thứ tự hoặc mutability?
- [ ] Nếu dùng diamond/generic factory không đối số, kiểu phần tử có bị suy luận thành `Object`?
- [ ] Nếu refactor initializer, toàn bộ usages và test liên quan đã được xem xét?
- [ ] Tài nguyên có được đóng đúng, và side effect vẫn rõ?
- [ ] Thay đổi mang lại lợi ích về hiểu code, thay vì chỉ giảm số ký tự hoặc chạy máy tự động?

**Ví dụ comment review hữu ích:**

> “Ở đây `var users = load()` khiến người đọc khó biết `load()` trả `List<User>` hay `Optional<List<User>>`. Mình đề xuất viết kiểu tường minh hoặc đặt tên API thể hiện rõ kết quả, vì đoạn bên dưới phân nhánh theo sự có mặt của dữ liệu.”

**Ví dụ comment review không đủ căn cứ:**

> “Cấm `var` trong mọi trường hợp vì Java phải khai báo kiểu.”

Mục tiêu của quy ước là chỉ ra **chỗ thông tin quan trọng bị mất hoặc bị suy ra sai**, không tranh luận dựa trên sở thích ngắn/dài.

## 13. Cách refactor mã hiện có mà vẫn an toàn

Nếu một nhóm bắt đầu dùng `var` trong codebase:

1. Chọn **một phương thức nhỏ** có initializer rõ ràng, ví dụ `StringBuilder builder = new StringBuilder();`; đánh giá việc bỏ kiểu có cải thiện không.
2. Khi đổi sang `var`, xác nhận **kiểu suy ra thực tế**: ví dụ thay `List<String> names = new ArrayList<>();` thành `var names = new ArrayList<String>();` nếu muốn giữ type argument; cân nhắc thay đổi từ interface sang concrete có ảnh hưởng gì.
3. Kiểm tra đặc biệt generic factory rỗng, literal số, overloaded methods, kiểu có khả năng bị upcast/cast.
4. Kiểm tra tên biến và đặt khai báo gần nơi sử dụng; chỉ thêm `var` sau khi cấu trúc code đã đủ rõ.
5. Biên dịch với mục tiêu Java thật của dự án, ví dụ `javac --release 17 ...`; chạy test liên quan tới generic, thứ tự collection và semantics.
6. Trên PR, mô tả lý do cải thiện khả năng đọc nếu thay đổi đáng kể; không tạo PR khổng lồ chỉ để chuyển tất cả khai báo sang `var`.

**Lưu ý về công cụ:** IDE có chức năng hiển thị kiểu suy ra và gợi ý chuyển `var` hữu ích, nhưng reviewer có thể chỉ thấy diff dạng văn bản. Quy ước cần khiến diff đủ hiểu mà không lệ thuộc vào tooltip.

## 14. Lỗi thường gặp và hướng sửa

| Lỗi/nhầm lẫn | Nguyên nhân | Cách sửa |
|---|---|---|
| Nghĩ `var` là dynamic type | Nhầm cơ chế suy luận với kiểu động | Nhớ kiểu được cố định khi biên dịch |
| Luôn viết `var data = service.run()` | Tên biến và phương thức quá chung | Đổi tên mang ý nghĩa, hoặc giữ kiểu tường minh |
| `var list = new ArrayList<>()` khi cần `String` | Thiếu target generic | `var list = new ArrayList<String>()` hoặc `List<String> list = new ArrayList<>()` |
| `var timeout = 1000` khi cần `long` | Literal mặc định suy ra `int` | `long timeout = 1000` hoặc `var timeout = 1000L` |
| `var x = null` | Không có kiểu suy ra | Khai báo kiểu rõ, cân nhắc thiết kế tránh null khi phù hợp |
| `var callback = x -> x + 1` | Lambda thiếu target functional interface | `IntUnaryOperator callback = x -> x + 1` |
| Quên đóng resource có `var` | Nhầm suy luận kiểu với quản lý vòng đời | Dùng `try-with-resources` theo hợp đồng API |
| Chuyển mọi biến sang `var` theo máy | Chỉ tối ưu số chữ, che kiểu quan trọng | Áp dụng tiêu chí đọc hiểu theo từng trường hợp |
| Không xem lại code khi đổi initializer | Kiểu tĩnh và hành vi có thể đổi | So sánh generic, concrete/interface, thứ tự, null, mutability và test |
| Cấm `var` tuyệt đối | Mất lợi ích loại bỏ lặp kiểu và tạo biến trung gian | Cho phép khi thông tin có sẵn ở vế phải và tên biến |

## 15. Bài tập tự đánh giá (có đáp án)

**Bài 1.** Nên giữ kiểu hay dùng `var` với `StringBuilder builder = new StringBuilder();`?

**Gợi ý:** `var builder = new StringBuilder();` thường dễ đọc vì constructor đã cho biết kiểu; đây là một ứng viên tốt cho `var`.

**Bài 2.** Vì sao `var values = new ArrayList<>();` có nguy cơ khi dự định chỉ chứa `Long`?

**Đáp án:** Khi không có dữ liệu/target generic giúp suy luận, kiểu thường là `ArrayList<Object>`. Dùng `var values = new ArrayList<Long>();` hoặc `List<Long> values = new ArrayList<>();`.

**Bài 3.** `var seconds = 5;` có kiểu `long` không? Làm sao yêu cầu `long`?

**Đáp án:** Không, nó là `int`. Dùng `long seconds = 5;` hoặc `var seconds = 5L;`.

**Bài 4.** `var customers = repository.fetch();` có nên dùng không?

**Đáp án:** Tùy hợp đồng API và ngữ cảnh. Nếu `fetch()` không thể hiện kiểu và ý nghĩa, kiểu tường minh hoặc method được đặt tên cụ thể hơn có thể dễ bảo trì. Không thể quyết định chỉ từ cú pháp `var`.

**Bài 5.** Khi dùng `var` trong vòng lặp, yếu tố nào giúp code dễ đọc?

**Đáp án:** Dữ liệu nguồn có kiểu rõ, tên phần tử mang ý nghĩa và phạm vi sử dụng ngắn. Ví dụ `for (var invoice : overdueInvoices)` rõ hơn `for (var x : data)`.

**Bài 6.** Một PR thay `var entries = new ArrayList<Entry>();` thành `var entries = new HashSet<Entry>();`. Nếu downstream dựa vào thứ tự thêm phần tử, reviewer cần lưu ý gì?

**Đáp án:** Kiểm tra thay đổi từ collection có thứ tự đến set không bảo đảm iteration order. `var` không gây sai trực tiếp, nhưng nó làm thay đổi kiểu suy ra ở cùng một dòng mà không có khai báo tường minh nhắc người đọc. Test hành vi về thứ tự cần được xem lại.

**Bài 7.** Dự án có thể quy định “ít nhất 70% biến cục bộ phải dùng `var`” không?

**Đáp án:** Có thể viết luật nội bộ tùy ý, nhưng **không nên** dùng tỷ lệ làm mục tiêu chất lượng. Nó khuyến khích code khó hiểu chỉ để đạt chỉ số; tiêu chí đúng là khả năng đọc, kiểu được suy luận và tính bảo trì.

## 16. Tài liệu chính thức để đối chiếu

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): mô tả tính năng Java 10 và cơ chế suy luận kiểu.
- [OpenJDK — Local Variable Type Inference: Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): nguyên tắc đọc code, tên biến, scope, initializer, generic và literal số. Tài liệu nhấn mạnh rằng không có một luật áp dụng máy móc cho mọi nơi.
- [OpenJDK — Local Variable Type Inference FAQ](https://openjdk.org/projects/amber/guides/lvti-faq): giải thích `var` là kiểu tĩnh, không phải dynamic typing; thảo luận tradeoff về khả năng đọc.
- [Oracle Java 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): giới hạn cú pháp và tương tác với tham số lambda.
- [Google Java Style Guide](https://google.github.io/styleguide/javaguide.html): tham khảo thêm về tên biến, phạm vi khai báo và các quy ước chung; **không** xem đây là một lệnh bắt buộc luôn hoặc không bao giờ dùng `var`.

**Ghi nhớ:** Một quy ước sử dụng `var` tốt phải **cho phép chọn kiểu tường minh khi nó giúp người khác hiểu mã**, và **cho phép dùng `var` khi kiểu đã hiển nhiên**, với quyết định dựa trên tên biến, initializer, scope, generic, ngữ nghĩa và rủi ro refactor. Không có phần trăm sử dụng `var` nào thay thế được code review có lập luận.