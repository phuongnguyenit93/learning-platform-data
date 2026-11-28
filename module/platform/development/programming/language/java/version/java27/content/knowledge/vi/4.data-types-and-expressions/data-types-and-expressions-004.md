# Suy luận kiểu biến cục bộ bằng var

Java là ngôn ngữ định kiểu tĩnh: kiểu của biến được xác định tại thời điểm biên dịch và không tự thay đổi trong lúc chương trình chạy. Từ Java 10, bạn có thể dùng `var` trong những khai báo biến cục bộ phù hợp để trình biên dịch suy luận kiểu từ biểu thức khởi tạo. Tính năng này có tên *Local-Variable Type Inference* và được chuẩn hóa qua JEP 286.

Với Java 27, `var` vẫn là một phần của ngôn ngữ Java hiện hành. Nó giúp giảm phần khai báo kiểu bị lặp lại, đặc biệt khi kiểu đã thể hiện rõ ở vế phải. `var` không biến Java thành ngôn ngữ định kiểu động, không bỏ qua kiểm tra kiểu và cũng không làm cho biến có thể nhận tùy ý mọi loại giá trị.

## 1. Cú pháp và nguyên tắc hoạt động

Cú pháp cơ bản:

```java
var variableName = initializer;
```

Trình biên dịch xác định kiểu của biến từ kiểu của biểu thức khởi tạo. Sau khi suy luận, biến được xử lý như thể bạn đã viết kiểu đó một cách tường minh.

```java
var quantity = 12;              // int
var unitPrice = 19.95;          // double
var enabled = true;             // boolean
var language = "Java";          // String
var names = java.util.List.of("An", "Binh"); // List<String>
```

Các kiểu trên được xác định ngay khi biên dịch. Ví dụ, `quantity` có kiểu `int`, còn `language` có kiểu `String`. Có thể gán lại một giá trị tương thích với kiểu đã suy luận, nhưng không thể gán một giá trị có kiểu không tương thích:

```java
var message = "Hello";
message = "Hello, Java 27"; // Hợp lệ: vẫn là String

// message = 27;             // Lỗi biên dịch: int không phải String
```

Điểm cần nhớ là kiểu được suy luận một lần từ biểu thức khởi tạo. Trình biên dịch không chờ các phép gán phía sau để tìm một kiểu chung cho biến.

### `var` không phải kiểu dữ liệu mới

`var` không phải tên của một kiểu dữ liệu như `int`, `String` hay `List`. Đây là một contextual keyword: trình biên dịch nhận diện nó như dấu hiệu yêu cầu suy luận kiểu trong những vị trí khai báo được ngôn ngữ quy định. Nó yêu cầu trình biên dịch xác định kiểu thực tế từ biểu thức khởi tạo hoặc từ ngữ cảnh pattern tương ứng.

Vì vậy, các cách viết sau có ý nghĩa khác nhau:

```java
int count = 5;
var anotherCount = 5; // anotherCount cũng có kiểu int
```

Cả hai biến đều có kiểu tĩnh `int`. Không có đối tượng kiểu `var` được tạo ra ở runtime.

## 2. Những nơi có thể sử dụng var

Trong Java 27, `var` được phép ở các vị trí khai báo biến cục bộ do ngôn ngữ quy định. Những trường hợp thường gặp gồm:

| Vị trí | Ví dụ |
|---|---|
| Biến cục bộ trong block | `var name = "Java"; ` |
| Biến khởi tạo trong vòng lặp `for` thông thường | `for (var i = 0; i < 3; i++) {}` |
| Biến phần tử trong enhanced `for` | `for (var item : items) {}` |
| Biến tài nguyên trong try-with-resources | `try (var reader = Files.newBufferedReader(path)) {}` |
| Thành phần của record pattern | `candidate instanceof User(var name)` |

Ví dụ đầy đủ:

```java
import java.util.List;

var languages = List.of("Java", "Kotlin", "Scala");

for (var language : languages) {
    System.out.println(language);
}

for (var index = 0; index < languages.size(); index++) {
    System.out.println(index + ": " + languages.get(index));
}
```

Trong vòng lặp đầu tiên, `language` được suy luận là `String`. Trong vòng lặp thứ hai, `index` được suy luận là `int`.

Với try-with-resources, kiểu của biến được suy luận từ đối tượng tài nguyên:

```java
import java.nio.file.Files;
import java.nio.file.Path;

var path = Path.of("notes.txt");

try (var reader = Files.newBufferedReader(path)) {
    var firstLine = reader.readLine();
    System.out.println(firstLine);
}
```

Ở đây, `path` có kiểu `Path`, `reader` có kiểu `BufferedReader`, còn `firstLine` có kiểu `String`. Quy tắc tự động đóng tài nguyên của try-with-resources vẫn được áp dụng như bình thường.

Java 27 cũng cho phép `var` trong type pattern lồng trực tiếp ở danh sách thành phần của record pattern. Kiểu của biến pattern được suy luận từ kiểu thành phần record tương ứng:

```java
record User(String name) {}

Object candidate = new User("Lan");
if (candidate instanceof User(var name)) {
    System.out.println(name.toUpperCase()); // name có kiểu String
}
```

Đây là trường hợp riêng của pattern thành phần record. `var` không được dùng trong type pattern ở cấp cao nhất, chẳng hạn `candidate instanceof var user`.

## 3. Những nơi không thể dùng var

`var` không thay thế kiểu khai báo trong mọi vị trí của Java. Không dùng nó để khai báo field, tham số phương thức, tham số constructor hoặc kiểu trả về phương thức.

```java
class Account {
    // var balance = 0; // Không hợp lệ: field cần kiểu tường minh

    private int balance = 0;

    // void deposit(var amount) {} // Không hợp lệ: tham số phương thức
    void deposit(int amount) {
        var updatedBalance = balance + amount; // Hợp lệ: biến cục bộ
        balance = updatedBalance;
    }

    // var getBalance() { return balance; } // Không hợp lệ
    int getBalance() {
        return balance;
    }
}
```

Tham số của lambda có một quy tắc riêng: từ Java 11, bạn có thể viết `var` cho các tham số của một lambda có kiểu được suy luận. Đây là tính năng *Local-Variable Syntax for Lambda Parameters* (JEP 323), không có nghĩa là mọi tham số phương thức đều được phép dùng `var`.

```java
import java.util.function.BiFunction;

BiFunction<String, String, String> join =
    (var left, var right) -> left + right;
```

Kiểu của `left` và `right` được suy luận từ kiểu hàm đích `BiFunction<String, String, String>`. Trong cùng một danh sách tham số lambda, phải dùng nhất quán một kiểu cú pháp: tất cả tham số không ghi kiểu, tất cả ghi `var`, hoặc tất cả ghi kiểu tường minh. Không trộn các dạng này.

## 4. Quy tắc suy luận kiểu từ biểu thức khởi tạo

Kiểu của biến `var` được xác định từ biểu thức khởi tạo khi biểu thức được xét độc lập, không có kiểu đích từ phép gán bao quanh. Quy tắc này giải thích một số trường hợp dễ gây nhầm lẫn.

### Kiểu nguyên thủy và kiểu tham chiếu

```java
var count = 10;                   // int
var largeCount = 10L;             // long
var ratio = 0.75;                 // double
var preciseRatio = 0.75f;         // float
var active = false;               // boolean
var title = "Java";               // String
var createdAt = java.time.Instant.now(); // Instant
```

Kiểu của literal và kiểu trả về của biểu thức ảnh hưởng trực tiếp đến kết quả suy luận. Chẳng hạn, `10` là literal kiểu `int`, còn `10L` là literal kiểu `long`.

```java
var integerDivision = 1 / 2;       // int, giá trị 0
var floatingDivision = 1.0 / 2;    // double, giá trị 0.5
```

`var` không tự chuyển phép chia số nguyên thành phép chia số thực. Nếu cần kết quả thập phân, hãy dùng toán hạng có kiểu dấu phẩy động hoặc chuyển kiểu một cách chủ động.

### Suy luận kiểu generic

Trình biên dịch kết hợp suy luận kiểu của lời gọi generic với suy luận kiểu biến cục bộ:

```java
import java.util.ArrayList;
import java.util.List;

var names = List.of("An", "Binh");
// Kiểu suy luận: List<String>

var scores = new ArrayList<Integer>();
// Kiểu suy luận: ArrayList<Integer>

var empty = new ArrayList<>();
// Kiểu suy luận: ArrayList<Object>
```

Trường hợp cuối thường gây bất ngờ. Khi dùng toán tử kim cương `<>` mà không có kiểu đích, trình biên dịch không thể suy ra `String`, `Integer` hay một kiểu phần tử khác từ biến `var`; kiểu phần tử được suy luận là `Object`.

Nếu đã biết kiểu phần tử mong muốn, hãy chỉ rõ nó:

```java
var emptyNames = new ArrayList<String>();
emptyNames.add("An");
```

Hoặc khai báo kiểu giao diện một cách tường minh khi đó là hợp đồng mà đoạn mã cần thể hiện:

```java
List<String> names = new ArrayList<>();
```

### Biểu thức trả về kiểu giao nhau hoặc kiểu không thể viết trực tiếp

Một số biểu thức có thể tạo ra kiểu suy luận phức tạp mà bạn không thể biểu diễn ngắn gọn bằng một tên kiểu thông thường. Ví dụ, lớp ẩn danh có thể khai báo thêm phương thức riêng:

```java
var worker = new Object() {
    void execute() {
        System.out.println("Working");
    }
};

worker.execute();
```

Kiểu của `worker` là kiểu lớp ẩn danh được suy luận từ biểu thức khởi tạo. Nếu khai báo biến bằng `Object` tường minh, bạn chỉ có thể gọi các thành viên của `Object` qua biến đó. Trường hợp này cho thấy `var` đôi khi giữ được thông tin kiểu cụ thể mà một kiểu tường minh rộng hơn sẽ làm mất.

Không nên dùng kỹ thuật này chỉ để truy cập các chi tiết triển khai không cần thiết. Hãy ưu tiên kiểu API công khai và hợp đồng rõ ràng khi thiết kế mã ứng dụng.

## 5. Các trường hợp khởi tạo không hợp lệ

Với khai báo biến cục bộ theo cú pháp `var name = expression`, biểu thức khởi tạo phải cung cấp đủ thông tin để trình biên dịch xác định kiểu. Những trường hợp sau không hợp lệ:

| Cách viết | Lý do |
|---|---|
| `var count;` | Không có biểu thức khởi tạo để suy luận kiểu |
| `var value = null;` | `null` không cung cấp kiểu cụ thể |
| `var a = 1, b = 2;` | Một khai báo `var` không được có nhiều declarator |
| `var values[] = new int[3];` | Không được đặt cặp ngoặc mảng ở tên biến |
| `var values = {1, 2, 3};` | Array initializer không có kiểu mảng đích |
| `var result = () -> "ok";` | Lambda cần kiểu hàm đích |
| `var length = String::length;` | Method reference cần kiểu hàm đích |
| `var self = (self = 1);` | Biểu thức khởi tạo không được tham chiếu chính biến đó |

Hãy viết lại bằng những dạng có kiểu xác định:

```java
String value = null;

var values = new int[] {1, 2, 3};

var result = (java.util.function.Supplier<String>) () -> "ok";

var length = (java.util.function.ToIntFunction<String>) String::length;
```

Đối với lambda và method reference, một cách thường dễ đọc hơn là khai báo kiểu hàm đích tường minh:

```java
java.util.function.Supplier<String> result = () -> "ok";
java.util.function.ToIntFunction<String> length = String::length;
```

Khi biểu thức khởi tạo là `null`, bạn cũng có thể ép kiểu để cung cấp kiểu tham chiếu:

```java
var nullableName = (String) null; // Kiểu String
```

Tuy nhiên, nếu biến có thể không có giá trị, hãy cân nhắc biểu diễn trạng thái đó bằng một API phù hợp như `Optional<T>`, thay vì khởi tạo null chỉ để dùng được `var`.

## 6. var kết hợp với final

Có thể kết hợp `var` và `final` để yêu cầu biến không được gán lại sau khi khởi tạo:

```java
final var maximumAttempts = 3;
// maximumAttempts = 4; // Lỗi biên dịch
```

`final` chỉ giới hạn việc gán lại biến. Nếu biến tham chiếu đến một đối tượng có thể thay đổi trạng thái, đối tượng đó vẫn có thể được cập nhật:

```java
final var names = new ArrayList<String>();
names.add("An"); // Hợp lệ: thay đổi trạng thái đối tượng

// names = new ArrayList<>(); // Lỗi: gán lại biến final
```

Vì vậy, `final var` không đồng nghĩa với đối tượng bất biến. Tính bất biến của đối tượng phụ thuộc vào thiết kế kiểu và API của đối tượng.

## 7. So sánh var với khai báo kiểu tường minh

Hai cách khai báo dưới đây đều hợp lệ nhưng thể hiện ý định khác nhau:

```java
List<String> names = new ArrayList<>();

var otherNames = new ArrayList<String>();
```

| Tiêu chí | Kiểu tường minh | `var` |
|---|---|---|
| Thể hiện kiểu | Ghi trực tiếp trong khai báo | Trình biên dịch suy luận từ initializer |
| Kiểm tra kiểu | Tĩnh tại thời điểm biên dịch | Tĩnh tại thời điểm biên dịch |
| Kiểu biến | Chính kiểu được khai báo | Kiểu được suy luận từ initializer |
| Mức độ thể hiện abstraction | Có thể chọn interface hoặc supertype | Thường giữ kiểu cụ thể của initializer |
| Phù hợp khi | Kiểu là một phần quan trọng của ý định thiết kế | Kiểu đã rõ từ biểu thức khởi tạo |

Trong ví dụ đầu, biến `names` được khai báo theo giao diện `List<String>`. Mã sử dụng biến chỉ phụ thuộc vào hợp đồng `List`. Trong ví dụ thứ hai, `otherNames` có kiểu `ArrayList<String>`, nên kiểu biến thể hiện trực tiếp implementation được tạo.

Nếu mục tiêu là lập trình theo interface, kiểu tường minh có thể truyền đạt ý định tốt hơn. Nếu kiểu initializer đã rõ và không cần giới hạn API qua một supertype, `var` giúp giảm lặp lại tên kiểu.

## 8. Quy tắc thực hành để mã dễ đọc

Giả sử `Customer` là kiểu miền đã được khai báo trong dự án. Sử dụng `var` khi tên biến và biểu thức khởi tạo giúp người đọc nhận ra kiểu mà không phải lần theo nhiều lớp mã:

```java
import java.nio.file.Path;
import java.util.List;

var customer = new Customer("C001", "Lan");
var filePath = Path.of("config/app.properties");
var names = List.of("An", "Binh", "Chi");
```

Cân nhắc khai báo kiểu tường minh khi biểu thức khởi tạo không cho biết rõ kiểu hoặc kiểu là thông tin quan trọng để hiểu nghiệp vụ:

```java
// Kiểu trả về của phương thức có thể không rõ với người đọc
var result = service.process(input);

// Khai báo rõ kiểu hợp đồng nếu điều đó làm mã dễ hiểu hơn
ProcessResult result = service.process(input);
```

Một số nguyên tắc hữu ích:

- Dùng `var` khi kiểu có thể nhận ra ngay từ vế phải, chẳng hạn biểu thức `new`, literal hoặc factory method có tên rõ nghĩa.
- Dùng kiểu tường minh khi cần thể hiện abstraction, chẳng hạn `List`, `Map`, interface hoặc supertype mà phần còn lại của mã nên phụ thuộc vào.
- Chọn tên biến có ý nghĩa. `var` giảm thông tin ở bên trái nên tên biến và ngữ cảnh càng quan trọng.
- Tránh dùng `var` khi biểu thức khởi tạo phức tạp, kiểu generic khó đoán hoặc kết quả phụ thuộc vào nhiều lời gọi phương thức.
- Không dùng `var` chỉ để rút ngắn một dòng nếu điều đó làm người đọc khó hiểu kiểu dữ liệu.
- Giữ kiểu phần tử generic tường minh khi toán tử kim cương có thể suy luận thành `Object` ngoài mong muốn.

Không có quy tắc buộc mọi biến cục bộ phải dùng `var` hoặc phải ghi kiểu đầy đủ. Hãy chọn cách khai báo làm rõ nhất ý định và kiểu mà phần còn lại của đoạn mã cần sử dụng.

## 9. Thực hành: suy luận kiểu trong một đoạn xử lý đơn hàng

Tạo một ví dụ xử lý đơn hàng để quan sát nhiều kiểu được suy luận khác nhau. Đoạn mã sử dụng các API Java hiện hành:

```java
import java.util.List;
import java.util.Comparator;

record Order(String code, int quantity, double unitPrice) {}

var orders = List.of(
    new Order("A001", 2, 120.0),
    new Order("A002", 1, 75.0),
    new Order("A003", 5, 40.0)
);

var availableOrders = orders.stream()
    .filter(order -> order.quantity() > 0)
    .toList();

var totalValue = availableOrders.stream()
    .mapToDouble(order -> order.quantity() * order.unitPrice())
    .sum();

var highestValueOrder = availableOrders.stream()
    .max(Comparator.comparingDouble(
        order -> order.quantity() * order.unitPrice()))
    .orElseThrow();
```

Kiểu mà trình biên dịch suy luận:

| Biến | Kiểu suy luận |
|---|---|
| `orders` | `List<Order>` |
| `availableOrders` | `List<Order>` |
| `totalValue` | `double` |
| `highestValueOrder` | `Order` |

Bạn có thể kiểm tra bằng cách gán sang biến có kiểu tường minh tương thích:

```java
List<Order> checkedOrders = orders;
double checkedTotal = totalValue;
Order checkedOrder = highestValueOrder;
```

Các phép gán trên được chấp nhận nếu kiểu đã suy luận tương thích với kiểu đích. Nếu thay đổi kiểu phần tử hoặc kiểu trả về trong đoạn mã, trình biên dịch sẽ kiểm tra lại các phép gán và lời gọi phương thức liên quan.

### Bài tập tự kiểm tra

1. Với khai báo `var count = 10;`, kiểu của `count` là gì?
2. Với khai báo `var values = new ArrayList<>();`, kiểu phần tử được suy luận là gì?
3. Vì sao `var message = null;` không biên dịch?
4. Có thể khai báo field bằng `var` trong một class không?
5. Trong biểu thức `var result = 1 / 2;`, kiểu và giá trị của `result` là gì?
6. Khi nào nên dùng kiểu giao diện tường minh thay cho `var`?

**Đáp án gợi ý:**

1. `int`, vì literal `10` có kiểu `int`.
2. `Object`, vì không có kiểu đích để suy luận đối số generic của toán tử kim cương.
3. Vì `null` không cung cấp kiểu cụ thể để trình biên dịch xác định kiểu biến.
4. Không. `var` dùng cho những khai báo biến cục bộ được ngôn ngữ cho phép.
5. `int`, giá trị `0`, vì cả hai toán hạng đều là số nguyên.
6. Khi muốn thể hiện hợp đồng API hoặc giới hạn mã phụ thuộc vào một interface/supertype thay vì kiểu triển khai cụ thể.

## 10. Tóm tắt

`var` cho phép trình biên dịch suy luận kiểu tĩnh của biến cục bộ từ biểu thức khởi tạo. Kiểu được suy luận cố định cho biến đó trong suốt phạm vi sử dụng; các quy tắc kiểm tra kiểu, chuyển đổi và gán của Java vẫn được áp dụng.

Khi sử dụng `var`, hãy kiểm tra ba điểm: biểu thức khởi tạo có cung cấp đủ thông tin kiểu hay không, kiểu được suy luận có đúng với ý định hay không, và việc lược bỏ kiểu tường minh có làm mã khó đọc hơn không. Dùng `var` có chọn lọc giúp mã ngắn gọn mà vẫn giữ được tính an toàn kiểu của Java.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §3.9 Keywords](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-3.html#jls-3.9): quy định `var` là contextual keyword và các ngữ cảnh được nhận diện.
- [Java Language Specification, Java SE 27 — §14.4 Local Variable Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.4): cú pháp khai báo biến cục bộ, giới hạn của `var` và cách xác định kiểu.
- [Java Language Specification, Java SE 27 — §14.4.1 Local Variable Declarators and Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.4.1): quy tắc suy luận kiểu từ initializer.
- [Java Language Specification, Java SE 27 — §14.30.1 Kinds of Patterns](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.30.1): giới hạn của `var` trong top-level type pattern và cách suy luận kiểu trong record pattern.
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): xác nhận lịch sử tính năng Local Variable Type Inference và cú pháp `var` trong lambda.
- [JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286): thiết kế và phạm vi của suy luận kiểu biến cục bộ, được đưa vào Java 10.
- [JEP 323: Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): cú pháp `var` cho tham số lambda, được đưa vào Java 11.
