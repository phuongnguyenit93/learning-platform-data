# Phạm vi hợp lệ của dấu gạch dưới, khai báo lặp lại và lỗi khi cố đọc biến không tên

Từ Java 22, ký tự gạch dưới đơn (`_`) có thể đại diện cho một biến hoặc tham số không tên trong một số vị trí được Java quy định. Giá trị vẫn được tính toán và khởi tạo, nhưng chương trình không thể tham chiếu giá trị đó bằng tên. Điều này hữu ích khi cú pháp yêu cầu khai báo một biến, nhưng phần thân chương trình chỉ cần tác dụng phụ hoặc chỉ cần kiểm tra kiểu của giá trị.

Quy tắc này thuộc JEP 456, *Unnamed Variables & Patterns*. Tính năng đã trở thành một phần chính thức của Java SE 22, vì vậy code dùng `_` theo các ngữ cảnh hợp lệ không cần bật preview. Các quy tắc về vị trí khai báo và khả năng tham chiếu vẫn được giữ trong Java hiện đại.

## 1. `_` là từ khóa có ngữ cảnh sử dụng giới hạn

Trong Java, `_` là từ khóa dành riêng, không phải tên biến thông thường. Java cho phép dùng nó trong một số dạng khai báo để thể hiện rõ rằng giá trị không cần được đặt tên.

```java
String _ = loadConfiguration(); // Hợp lệ: biến cục bộ không tên

String _cache = loadConfiguration(); // Hợp lệ: đây là identifier có nhiều ký tự
```

Chỉ dấu gạch dưới đơn mới là từ khóa. Các identifier như `_cache`, `user_name` hoặc `value_` vẫn là tên thông thường theo quy tắc identifier của Java.

Một khai báo dùng `_` vẫn có kiểu và vẫn được khởi tạo. Điểm khác biệt là nó không đưa một tên có thể tra cứu vào phạm vi tên của chương trình. Vì vậy, không thể dùng `_` để đọc giá trị, gán lại giá trị hoặc truyền giá trị đó sang một lời gọi khác.

## 2. Những vị trí được phép khai báo biến không tên

Java cho phép dùng `_` trong các nhóm khai báo sau:

| Vị trí | Ví dụ | Quy tắc cần nhớ |
| --- | --- | --- |
| Khai báo biến cục bộ trong block | `int _ = calculate();` | Phải có initializer. |
| Phần khởi tạo của vòng lặp `for` thường | `for (int i = 0, _ = start(); ...)` | Biến không tên phải được khởi tạo. |
| Biến lặp của enhanced `for` | `for (Order _ : orders)` | Mỗi phần tử được gán cho biến không tên ở mỗi lượt. |
| Khai báo resource của `try-with-resources` | `try (var _ = openFile())` | Resource phải được khởi tạo và phải triển khai `AutoCloseable`. |
| Tham số của `catch` | `catch (IOException _)` | Ngoại lệ được bắt nhưng không thể đọc qua tên. |
| Tham số lambda | `(_, _) -> ...` | Có thể có nhiều tham số không tên. |
| Pattern | `instanceof String _`, `Point(_, _)` | Phải tuân theo quy tắc riêng của type pattern và record pattern. |

Các ví dụ dưới đây minh họa cách sử dụng ở từng vị trí.

### 2.1. Biến cục bộ trong block

Khi cần thực hiện một lời gọi và cố ý bỏ qua giá trị trả về, có thể khai báo một biến không tên:

```java
static void removeNext(Queue<String> queue) {
    String _ = queue.remove();
    auditRemoval();
}
```

`queue.remove()` vẫn được thực thi. Nếu hàng đợi rỗng, ngoại lệ của `remove()` vẫn xảy ra như bình thường. Biến `_` không làm mất tác dụng phụ và cũng không thay đổi cách biểu thức khởi tạo hoạt động.

Với biến cục bộ không tên trong block, initializer là bắt buộc:

```java
int _ = calculate(); // Hợp lệ
int _;                // Lỗi biên dịch: thiếu initializer
```

Quy tắc này khác với biến cục bộ có tên, vốn có thể được khai báo trước rồi gán giá trị sau nếu chương trình bảo đảm definite assignment trước khi đọc. Biến không tên không có trường hợp sử dụng để đọc về sau, nên Java yêu cầu khởi tạo ngay tại khai báo.

### 2.2. Phần khởi tạo của vòng lặp `for` thường

Một khai báo trong phần khởi tạo của `for` cũng có thể dùng `_`. Ví dụ, chương trình cần gọi một hàm khởi tạo trước vòng lặp nhưng không dùng giá trị hàm trả về:

```java
for (int index = 0, _ = initializeBatch(); index < 3; index++) {
    process(index);
}
```

`initializeBatch()` chạy đúng một lần khi bắt đầu vòng lặp. Biến `index` được dùng để điều khiển vòng lặp; biến `_` nhận giá trị trả về nhưng không thể được tham chiếu. Biến không tên trong phần khởi tạo của `for` cũng phải có initializer.

### 2.3. Biến lặp của enhanced `for`

Khi chỉ cần số lượt lặp hoặc cần thực hiện tác dụng phụ cho từng phần tử, không cần đặt tên cho phần tử hiện tại:

```java
static int countOrders(List<Order> orders) {
    int count = 0;

    for (Order _ : orders) {
        count++;
    }

    return count;
}
```

Ở mỗi lượt, Java lấy phần tử tiếp theo từ `orders` và khởi tạo biến lặp không tên. Phần thân vòng lặp không thể đọc phần tử hiện tại qua `_`. Cách viết này thể hiện trực tiếp rằng phần tử chỉ được duyệt qua, còn điều cần quan tâm là số lượt hoặc tác dụng phụ trong thân vòng lặp.

### 2.4. Resource trong `try-with-resources`

Resource không tên phù hợp khi cần mở tài nguyên để kích hoạt một hành động hoặc kiểm tra, nhưng không cần gọi phương thức trên resource bên trong block:

```java
static void checkFile(Path path) throws IOException {
    try (var _ = Files.newInputStream(path)) {
        // Mở được file là đủ cho thao tác kiểm tra này.
    }
}
```

Initializer vẫn được thực thi. Khi rời khỏi `try`, Java tự động đóng resource như với resource có tên. Kiểu của resource phải là subtype của `AutoCloseable`.

Một resource specification có thể khai báo nhiều resource không tên:

```java
try (var _ = openInput();
     var _ = openOutput()) {
    transferData();
}
```

Hai resource được khởi tạo và đóng theo đúng quy tắc `try-with-resources`. Việc cả hai cùng dùng ký tự `_` không tạo ra xung đột tên.

### 2.5. Tham số `catch`

Nếu chương trình chỉ cần phản ứng khi một loại ngoại lệ xảy ra mà không cần kiểm tra nội dung ngoại lệ, có thể dùng tham số `catch` không tên:

```java
static int parseOrDefault(String input) {
    try {
        return Integer.parseInt(input);
    } catch (NumberFormatException _) {
        return 0;
    }
}
```

`NumberFormatException` vẫn được bắt và luồng điều khiển vẫn đi vào block `catch`. Chương trình chỉ không có tên để đọc thông tin ngoại lệ, chẳng hạn message hoặc cause. Nếu cần log hoặc phân tích ngoại lệ, hãy đặt một tên có ý nghĩa như `exception`.

### 2.6. Tham số lambda

Lambda có thể khai báo một hoặc nhiều tham số không tên:

```java
BiFunction<String, Integer, String> ignoredArguments = (_, _) -> "processed";
```

Hai đối số vẫn được truyền vào lambda và vẫn có kiểu do target type xác định. Thân lambda chỉ không tham chiếu đến chúng.

Nếu khai báo kiểu tường minh cho tham số, tất cả tham số phải dùng kiểu tường minh:

```java
BiFunction<String, Integer, String> ignoredArguments =
        (String _, Integer _) -> "processed";
```

Không trộn tham số có kiểu tường minh với tham số suy luận kiểu trong cùng một lambda:

```java
// Lỗi biên dịch: trộn tham số khai báo kiểu và tham số suy luận kiểu
BiFunction<String, Integer, String> invalid =
        (String _, _) -> "processed";
```

## 3. Phạm vi của biến không tên và việc khai báo lặp lại

Biến cục bộ có tên đưa một identifier vào phạm vi tên. Java áp dụng các quy tắc về scope và shadowing để tránh hai khai báo có cùng tên gây mơ hồ. Khai báo không tên bằng `_` không đưa identifier vào phạm vi tên đó.

Vì không có tên để tra cứu hoặc shadow, nhiều biến không tên có thể xuất hiện trong cùng một block hoặc cùng phạm vi khai báo. Ví dụ sau hợp lệ:

```java
static List<Caller> selectEveryFifth(Queue<Caller> queue, int prizes) {
    List<Caller> winners = new ArrayList<>();

    try {
        while (prizes > 0) {
            Caller _ = queue.remove();
            Caller _ = queue.remove();
            Caller _ = queue.remove();
            Caller _ = queue.remove();
            winners.add(queue.remove());
            prizes--;
        }
    } catch (NoSuchElementException _) {
        // Hàng đợi đã hết phần tử.
    }

    return winners;
}
```

Bốn khai báo `Caller _` trong cùng block đều hợp lệ. Mỗi lần gọi `queue.remove()` vẫn lấy ra một phần tử; chương trình chỉ bỏ qua giá trị của bốn phần tử đó. Đây là một khác biệt quan trọng so với khai báo lặp lại một tên biến thông thường.

| Khai báo | Kết quả | Lý do |
| --- | --- | --- |
| `int count = 1; int count = 2;` trong cùng block | Lỗi | Hai khai báo tạo cùng identifier `count` trong một phạm vi không cho phép. |
| `int _ = first(); int _ = second();` trong cùng block | Hợp lệ | Không khai báo identifier có thể tra cứu. |
| `(_, _) -> "ok"` | Hợp lệ | Cả hai tham số lambda đều không tên. |
| `try (var _ = first(); var _ = second()) { ... }` | Hợp lệ | Resource specification cho phép nhiều resource không tên. |

Điều này không có nghĩa Java cho phép khai báo lặp mọi biến. Các quy tắc thông thường vẫn áp dụng cho identifier có tên. Ví dụ, không thể khai báo hai biến cùng tên `count` trong cùng phạm vi chỉ bằng cách đổi một trong các biến thành `_` ở biểu thức sử dụng sau đó.

## 4. Cố đọc hoặc gán biến không tên sẽ gây lỗi biên dịch

`_` là từ khóa dùng trong vị trí khai báo hoặc pattern được cho phép. Nó không phải một tên biến có thể xuất hiện trong biểu thức. Vì vậy, những cách viết sau không hợp lệ:

```java
static void invalidExamples() {
    int _ = calculate();

    System.out.println(_); // Lỗi: không thể đọc biến không tên
    _ = 10;                // Lỗi: không có biến tên _ để gán
}
```

Nếu cần sử dụng giá trị về sau, phải đặt tên cho biến:

```java
int result = calculate();
System.out.println(result);
```

Không thể dùng `_` như tham số hoặc field thông thường:

```java
class InvalidDeclarations {
    private int _;           // Lỗi: field phải có identifier

    void process(int _) {    // Lỗi: tham số method phải có identifier
    }
}

record Point(int _) { }      // Lỗi: record component phải có identifier
```

Constructor parameters cũng phải có tên. `_` không phải cách viết tắt chung để bỏ tên cho mọi biến hoặc tham số trong Java.

Một khai báo không tên ở block hoặc basic `for` không được bỏ initializer:

```java
int _;                         // Lỗi

for (int _; hasNext(); step()) { // Lỗi
    process();
}
```

Với `var`, quy tắc suy luận kiểu vẫn được áp dụng: phải có initializer và chỉ được có một declarator trong khai báo đó.

```java
var _ = calculate();       // Hợp lệ
var _ = first(), _ = next(); // Lỗi: var không cho phép nhiều declarator
```

## 5. Phân biệt biến không tên với pattern không tên

JEP 456 bao gồm cả unnamed variables và unnamed patterns. Cả hai đều dùng `_`, nhưng chúng có vai trò khác nhau.

### 5.1. Type pattern có biến không tên

Trong type pattern, kiểu vẫn được kiểm tra nhưng chương trình không giữ giá trị dưới một tên có thể truy cập:

```java
static boolean isText(Object value) {
    if (value instanceof String _) {
        return true;
    }
    return false;
}
```

`instanceof String _` vẫn kiểm tra `value` có phải `String` hay không. Khi khớp, không có biến `String` nào để đọc trong block. Dạng tương tự cũng có thể dùng trong pattern của `switch`:

```java
static String describe(Object value) {
    return switch (value) {
        case String _ -> "text";
        case Integer _ -> "number";
        default -> "other";
    };
}
```

### 5.2. Unnamed pattern trong record pattern

Trong record pattern, `_` có thể thay cho cả type pattern của một component khi chương trình không cần kiểm tra hoặc sử dụng component đó:

```java
record Point(int x, int y) { }

static boolean isPoint(Object value) {
    return value instanceof Point(_, _);
}
```

Hai component của `Point` vẫn được lấy ra để kiểm tra record pattern, nhưng không có pattern variable nào được tạo ra. Unnamed pattern này khớp với component tương ứng, kể cả khi component có giá trị `null`.

Nếu muốn kiểm tra kiểu component nhưng không cần dùng giá trị, có thể giữ type pattern và bỏ tên:

```java
record ColoredPoint(Point point, String color) { }

static boolean hasTextColor(Object value) {
    return value instanceof ColoredPoint(_, String _);
}
```

Ở ví dụ này, component thứ nhất được bỏ qua hoàn toàn; component thứ hai phải khớp với `String`, nhưng giá trị chuỗi không được giữ lại dưới tên nào.

Không thể dùng một unnamed pattern trần làm top-level pattern:

```java
if (value instanceof _) { // Lỗi biên dịch
    // ...
}
```

Ký hiệu `_` đứng một mình chỉ được dùng làm unnamed pattern trong danh sách component của record pattern. Với top-level type pattern, phải ghi kiểu, ví dụ `value instanceof String _`.

## 6. Những điểm cần nhớ khi áp dụng

- Dùng `_` khi giá trị thực sự không cần được tham chiếu. Nếu cần log, kiểm tra, trả về hoặc truyền giá trị đi nơi khác, hãy đặt tên có ý nghĩa.
- Khai báo không tên vẫn đánh giá initializer. Các ngoại lệ, tác dụng phụ và quy tắc đóng resource vẫn hoạt động bình thường.
- Nhiều khai báo `_` có thể cùng tồn tại trong một block, lambda parameter list hoặc resource specification vì chúng không tạo identifier.
- Biến không tên không thể được đọc hoặc gán lại bằng `_`. Từ khóa này chỉ hợp lệ ở các vị trí khai báo hoặc pattern mà ngôn ngữ cho phép.
- Biến không tên trong block và basic `for` phải có initializer. Enhanced `for`, `catch`, lambda và pattern được khởi tạo theo cơ chế riêng của cấu trúc tương ứng.
- Phân biệt `String _` với `_` trong record pattern: dạng thứ nhất vẫn kiểm tra kiểu; dạng thứ hai bỏ qua component mà không tạo pattern variable.
- JEP 456 là tính năng chính thức từ Java 22. Không cần `--enable-preview` khi biên dịch chương trình Java 22 trở lên sử dụng các quy tắc này.

## Tài liệu tham khảo

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Oracle Java SE 27 — Unnamed Variables and Patterns](https://docs.oracle.com/en/java/javase/27/language/unnamed-variables-patterns.html)
- [Java Language Specification, Java SE 27 — Chapter 6: Names](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html)
- [Java Language Specification, Java SE 27 — Chapter 14: Blocks, Statements, and Patterns](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html)
- [Java Language Specification, Java SE 27 — Full specification](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/index.html)
