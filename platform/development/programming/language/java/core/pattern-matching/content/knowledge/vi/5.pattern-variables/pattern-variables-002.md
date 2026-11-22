# Kiểu của biến được suy ra từ pattern trong Java

## 1. Câu hỏi cốt lõi: biến pattern có kiểu gì?

Khi dùng **pattern matching**, Java vừa kiểm tra một giá trị có khớp pattern hay không, vừa có thể **khai báo biến pattern** (pattern variable) để sử dụng tại các vị trí chắc chắn khớp. Một trong các lợi ích quan trọng là compiler đã biết **kiểu tĩnh** của biến đó, nên lập trình viên không phải tự ép kiểu.

Ví dụ Java 17:

```java
Object data = "Java";
if (data instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

Có hai loại kiểu cần phân biệt:

- **Kiểu tĩnh của biểu thức gốc**: biến `data` vẫn được khai báo là `Object`.
- **Kiểu tĩnh của biến pattern**: `text` có kiểu `String` vì pattern ghi rõ `String text`.
- **Kiểu thực tế lúc chạy (runtime class)**: đối tượng được `data` tham chiếu đang là `String`; `instanceof` kiểm tra quan hệ kiểu này để quyết định có khớp hay không.

Compiler cho gọi `text.toUpperCase()` vì **kiểu tĩnh của `text` là `String`**, không phải vì sau khi kiểm tra, biến `data` đã tự đổi thành `String`. Chẳng hạn, `data.toUpperCase()` vẫn không hợp lệ tại thời điểm biên dịch vì `Object` không khai báo phương thức đó.

Cần hiểu đúng từ “suy ra”: trong **type pattern** `String text`, kiểu `String` đã được viết tường minh và compiler lấy trực tiếp từ pattern. Với **record pattern** có `var` (Java 21+), compiler mới thực hiện suy luận kiểu component cụ thể dựa trên khai báo record và ngữ cảnh kiểu. Hai trường hợp liên quan nhau nhưng không đồng nghĩa hoàn toàn.

## 2. Type pattern: kiểu của biến được xác định trực tiếp từ tên kiểu trong pattern

Cú pháp phổ biến trong `instanceof` từ Java 16, dùng ổn định trên Java 17+:

```text
biểu_thức instanceof ReferenceType tên_biến
```

Ví dụ:

```java
Object input = "Hello";

if (input instanceof String text) {
    int length = text.length(); // text có kiểu String
    System.out.println(length);
}
```

Khi `input` khác `null` và đối tượng của nó khớp `String`, biến `text` được đưa vào phạm vi hợp lệ. Kiểu của biến là **đúng kiểu nêu trong pattern**; Java không tự biến biến đó thành một subtype cụ thể hơn chỉ vì instance runtime có subtype đó.

| Type pattern | Kiểu tĩnh của biến được khai báo | Có thể gọi trực tiếp |
| --- | --- | --- |
| `String name` | `String` | `name.toUpperCase()`, `name.length()` |
| `CharSequence chars` | `CharSequence` | `chars.length()`, `chars.charAt(0)` nếu còn ký tự |
| `Number number` | `Number` | `number.intValue()`, `number.doubleValue()` |
| `Runnable job` | `Runnable` | `job.run()` |
| `java.util.List<?> items` | `List<?>` | `items.size()`; phần tử đọc ra chưa có kiểu cụ thể |
| `Integer count` | `Integer` | `count.intValue()` |

Ví dụ sau minh họa giới hạn của kiểu tĩnh:

```java
Object value = "pattern";

if (value instanceof CharSequence chars) {
    System.out.println(chars.length()); // Hợp lệ: CharSequence có length()
    // chars.toUpperCase();             // Sai: CharSequence không có toUpperCase()
}
```

Dù đối tượng runtime có thể là `String`, **biến `chars` có kiểu `CharSequence`**. Nếu cần hành vi chỉ có trên `String`, hãy dùng `String` pattern hoặc kiểm tra thu hẹp thêm ở vị trí hợp lệ.

**Không có phép đổi kiểu cho biến gốc:** đoạn `if (value instanceof String s)` không đổi khai báo `value` từ `Object` sang `String`. Compiler dùng biến mới `s` để làm việc với kiểu đã xác định.

## 3. So sánh với ép kiểu thủ công

Trước khi dùng pattern variable, lập trình viên thường viết:

```java
static void before(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.length());
    }
}
```

Với type pattern, khai báo và chuyển tham chiếu sang biến có kiểu phù hợp được diễn đạt trực tiếp:

```java
static void after(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Hai cách cùng dựa trên phép kiểm tra runtime. Cách dùng pattern giảm thao tác ép kiểu, tránh lặp tên kiểu và thể hiện rõ quan hệ: **chỉ dùng `text` khi pattern đã khớp**. Compiler thực hiện kiểm tra kiểu và theo dõi phạm vi của biến. Pattern variable không phải một biến `Object` bị ép kiểu động ở mỗi lần gọi phương thức; nó đã có kiểu tĩnh do compiler xác định.

## 4. Ví dụ Java 17 hoàn chỉnh: cùng đầu vào `Object`, nhiều kiểu biến pattern

Lưu đoạn mã sau thành **PatternVariableTypeDemo.java** và biên dịch với Java 17 trở lên:

```java
public class PatternVariableTypeDemo {
    interface Label {
        String label();
    }

    record Ticket(String value) implements Label {
        @Override
        public String label() {
            return "T#" + value;
        }
    }

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "String:" + text.toUpperCase();
        }

        if (value instanceof Label item) {
            return "Label:" + item.label();
        }

        if (value instanceof CharSequence chars) {
            return "Chars:" + chars.length();
        }

        return "Other";
    }

    static String guard(Object value) {
        if (!(value instanceof String word)) {
            return "not String";
        }
        return "Length:" + word.length();
    }

    public static void main(String[] args) {
        System.out.println(describe("java"));
        System.out.println(describe(new Ticket("7")));
        System.out.println(describe(new StringBuilder("abc")));
        System.out.println(describe(null));
        System.out.println(guard("pattern"));
        System.out.println(guard(42));
    }
}
```

Biên dịch và chạy:

```bash
javac PatternVariableTypeDemo.java
java PatternVariableTypeDemo
```

Đầu ra chính xác:

```text
String:JAVA
Label:T#7
Chars:3
Other
Length:7
not String
```

Phân tích các biến:

1. `text` trong `String text` có kiểu `String`, do đó gọi được `toUpperCase()`.
2. `item` trong `Label item` có kiểu **interface `Label`**, mặc dù đối tượng thực tế là `Ticket`. Compiler cho gọi `label()` vì interface khai báo phương thức đó.
3. `chars` trong `CharSequence chars` có kiểu `CharSequence`. `StringBuilder` thực thi interface này, nên `chars.length()` hợp lệ. Không được giả định `chars` có mọi phương thức riêng của `StringBuilder`.
4. `word` trong `String word` có kiểu `String` và được sử dụng sau nhánh trả về sớm `if (!(...)) return ...`; compiler biết khi tiếp tục chạy thì pattern đã khớp.
5. `null` không khớp với type pattern của `instanceof`; `Integer` từ `42` cũng không khớp `String`. Vì vậy các nhánh dự phòng được sử dụng.

Ví dụ này dùng **type pattern**, đã ổn định từ Java 16 (JEP 394). Không cần bật tính năng preview khi chạy trên Java 17.

## 5. Compiler biết kiểu, nhưng còn phải biết biến có nằm trong phạm vi hợp lệ

**Kiểu tĩnh** và **phạm vi sử dụng** là hai vấn đề khác nhau. Mặc dù `String text` đã xác định kiểu `String`, compiler chỉ cho tham chiếu `text` ở những đường điều khiển được bảo đảm pattern khớp (flow scoping).

### Nhánh đúng của `if`

```java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // Hợp lệ
    }
    // text.length();                     // Sai: text không có hiệu lực tại đây
}
```

### Toán tử `&&` có đánh giá ngắn mạch

```java
static void printNonBlank(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        System.out.println(text.toUpperCase());
    }
}
```

Vế phải chỉ được đánh giá khi vế trái đúng. Compiler biết lúc đọc `text.isBlank()` thì `text` là một `String` đã khớp. Đó là lý do không cần cast.

Cẩn thận với toán tử `||`:

```java
// Không hợp lệ: ở vế phải, input có thể KHÔNG khớp String.
// if (input instanceof String text || text.isBlank()) { ... }
```

Nếu vế trái trả về `false`, `||` phải đánh giá vế phải; lúc đó `text` chưa được khai báo trong đường đi hợp lệ.

### Phủ định pattern và thoát sớm

```java
static int lengthOrMinusOne(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length(); // Hợp lệ: các đường đi còn lại đều đã match
}
```

Trong ví dụ này, sau `if`, compiler suy ra rằng biến `text` chắc chắn được gán từ pattern. Phạm vi của biến không đơn giản là “từ dấu ngoặc nhọn đầu tiên đến dấu ngoặc nhọn cuối cùng”; nó phụ thuộc phân tích luồng điều khiển.

**Kết luận cho phần phạm vi:** kiểu của biến pattern do pattern định nghĩa, còn việc một dòng code **được phép sử dụng** biến đó hay không do phân tích flow scoping quyết định.

## 6. Interface pattern: kiểu biến không tự trở thành class runtime

Một interface thường có nhiều implementation. Khi viết:

```java
interface Drawable {
    void draw();
}

class Circle implements Drawable {
    @Override
    public void draw() {
        System.out.println("circle");
    }

    public double radius() {
        return 2.5;
    }
}
```

Đoạn dưới đây có hai mức kiểu khác nhau:

```java
Object shape = new Circle();

if (shape instanceof Drawable drawable) {
    drawable.draw(); // Hợp lệ: Drawable khai báo draw()
    // drawable.radius(); // Sai: Drawable không khai báo radius()
}
```

`drawable` có kiểu `Drawable`, không phải `Circle`. Kiểu runtime có thể là `Circle` nhưng không làm compiler tự mở thêm `radius()`. Nếu cần phương thức riêng của `Circle`, có thể kiểm tra bằng `shape instanceof Circle circle` ở nhánh phù hợp.

Nguyên tắc này cũng đúng cho lớp cha: `Number n` không tự thành `Integer` dù đối tượng thực tế là `Integer`. Ngược lại, pattern kiểu interface/lớp cha là cách tốt để code chỉ phụ thuộc các hành vi đã được công bố bởi kiểu cần dùng.

## 7. Generic: compiler không suy luận được mọi đối số kiểu từ đối tượng runtime

Java generic dùng **type erasure**. Một phép kiểm tra runtime cho `java.util.List<?>` xác nhận đối tượng là `List`, nhưng không thể khẳng định các phần tử thuộc `String` hay `Integer` chỉ từ thông tin `instanceof`.

```java
import java.util.List;

static void showFirst(Object input) {
    if (input instanceof List<?> items && !items.isEmpty()) {
        Object first = items.get(0); // Kiểu tĩnh Object
        if (first instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

- `items` có kiểu tĩnh `List<?>`, đúng như pattern.
- `items.get(0)` chỉ có thể xem an toàn là `Object` trong đoạn code này.
- `text` mới có kiểu tĩnh `String` vì pattern kế tiếp là `String text`.

Không viết:

```java
// Không hợp lệ với giá trị đầu vào Object:
// if (input instanceof List<String> names) { ... }
```

Đối số kiểu `String` của `List<String>` không thể được kiểm chứng trực tiếp từ một đối tượng kiểu `Object` bằng `instanceof` trong trường hợp này. Dùng `List<?>` rồi kiểm tra phần tử theo nhu cầu.

Một đối tượng có thể mang dữ liệu generic, nhưng compiler quyết định kiểu của biến pattern dựa trên **kiểu tĩnh và quy tắc Java**, không “đọc lại” tham số generic đã bị xóa ở runtime.

## 8. Java 21+: `var` trong record pattern thực sự suy luận kiểu component

Đây là tình huống **type inference** rõ nét hơn. Record pattern được chuẩn hóa trong **Java 21 (JEP 440)**, và có thể khai báo `var` trong danh sách component pattern.

Giả sử:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
```

Khi viết:

```java
if (data instanceof Segment(Point(var x, var y), var end)) {
    int sum = x + y;
    Point last = end;
}
```

Compiler biết:

- `Segment.start()` có kiểu `Point`, nên có thể tiếp tục khớp record pattern `Point(...)`.
- Hai component `Point.x()` và `Point.y()` có kiểu `int`, do đó **`x` và `y` được suy luận là `int`**.
- Component `Segment.end()` có kiểu `Point`, do đó **`end` được suy luận là `Point`**.

Kiểu của `x`/`y`/`end` không được quyết định từ giá trị cụ thể 2, 3 hay 4 lúc chạy. Nó đến từ **khai báo component của record và ngữ cảnh kiểu lúc biên dịch**. Nếu record có component kiểu interface, biến `var` tương ứng mang kiểu interface đó.

### Ví dụ Java 21 chạy độc lập

Lưu thành **RecordPatternTypeDemo.java**:

```java
public class RecordPatternTypeDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Box<T>(T value) {}

    static void show(Object data) {
        if (data instanceof Segment(Point(var x, var y), var end)) {
            int sum = x + y;
            Point last = end;
            System.out.println("startSum:" + sum);
            System.out.println("end:" + last.x() + "," + last.y());
        }
    }

    static void showGeneric(Box<String> box) {
        if (box instanceof Box(var text)) {
            String upper = text.toUpperCase();
            System.out.println("text:" + upper);
        }
    }

    public static void main(String[] args) {
        show(new Segment(new Point(2, 3), new Point(4, 5)));
        showGeneric(new Box<>("hello"));
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên** (không bật preview):

```bash
javac RecordPatternTypeDemo.java
java RecordPatternTypeDemo
```

Đầu ra:

```text
startSum:5
end:4,5
text:HELLO
```

Trường hợp generic `Box<T>` cho thấy ý nghĩa của **ngữ cảnh kiểu**: trong `showGeneric(Box<String> box)`, compiler biết `T` là `String`; vì vậy `Box(var text)` suy luận `text` là `String` và `toUpperCase()` hợp lệ.

Nhưng nếu biểu thức gốc chỉ có kiểu `Object`:

```java
Object unknown = new Box<>("hello");

if (unknown instanceof Box(var item)) {
    Object value = item; // Hợp lệ
    // item.toUpperCase(); // Không hợp lệ: item không có kiểu tĩnh String
}
```

Ở đây compiler không có bằng chứng kiểu tĩnh rằng `Box` chứa `String`, dù đối tượng runtime thực tế được tạo bằng `new Box<>("hello")`. Trong ngữ cảnh rộng này, biến `item` không được tự nâng thành `String`. Muốn gọi phương thức đặc thù của chuỗi, hãy kiểm tra `item instanceof String text` hoặc chuyển đầu vào thành một kiểu generic được xác thực phù hợp.

**Chú ý cú pháp:** `var` không thay thế mọi type pattern. Chẳng hạn, cách viết `obj instanceof var x` không phải type pattern thông thường hợp lệ để dùng thay `obj instanceof String x` trong Java 17/21. `var` trong bài này thuộc **component pattern của record**; cú pháp này yêu cầu Java 21+.

## 9. Phân biệt `var` của biến cục bộ và `var` của record pattern

Hai ví dụ có nguồn thông tin suy luận khác nhau:

```java
Object raw = "hello";
var copy = raw; // copy có kiểu Object, lấy từ kiểu tĩnh của raw

if (raw instanceof String text) {
    // text có kiểu String do type pattern chỉ định
    System.out.println(text.length());
}
```

Với local `var` ở Java 10+, compiler suy luận kiểu của biến từ **biểu thức khởi tạo** `raw` (vốn có kiểu tĩnh `Object`). Còn `String text` lấy kiểu từ **tên kiểu ghi trong pattern**.

Với record pattern `Box(var text)`, compiler suy luận kiểu biến từ **component tương ứng của record sau khi xem ngữ cảnh generic**. Không nên nói chung chung rằng compiler “nhìn đối tượng runtime rồi đoán kiểu” cho cả ba trường hợp.

| Cú pháp | Phiên bản phù hợp | Cơ sở xác định kiểu |
| --- | --- | --- |
| `var local = expression;` | Java 10+ | Kiểu tĩnh của biểu thức khởi tạo |
| `x instanceof String text` | Java 16+ | Kiểu `String` được nêu trong type pattern |
| `x instanceof CharSequence seq` | Java 16+ | Kiểu `CharSequence` được nêu trong type pattern |
| `x instanceof Point(var px, var py)` | Java 21+ | Kiểu các component `Point.x()`, `Point.y()` |
| `box instanceof Box(var value)` | Java 21+ | Kiểu component `value`, có thể phụ thuộc ngữ cảnh generic |

Nếu bài thực hành chạy bằng Java 17, hãy dùng type pattern như `String s`, `Number n` và `List<?> items`. Ví dụ record pattern có `var` phải chuyển sang Java 21+.

## 10. `null`, kiểu nguyên thủy và điều kiện biên dịch

**Khi biểu thức là `null`:**

```java
Object input = null;
System.out.println(input instanceof String); // false
```

Type pattern `String s` không khớp `null`; biến `s` vì thế không có giá trị để sử dụng ở nhánh đúng. Không có đối tượng nào được tạo ra bởi `instanceof`.

**Đối với primitive:** type pattern của `instanceof` trong Java 17/21 hướng tới **reference type**. Không dùng `obj instanceof int n` cho bài Java 17/21; nếu một `Object` đang chứa số nguyên được boxing, dùng `obj instanceof Integer n`. Ngược lại, record pattern `Point(var x, var y)` ở Java 21 có thể suy luận `x`, `y` là `int` vì chúng đến từ primitive component của record.

**Kiểm tra có thể bị chặn lúc biên dịch:** compiler không chấp nhận mọi cặp kiểu `instanceof` nếu quan hệ chuyển kiểu là bất khả thi. Ví dụ nếu biến có kiểu một class `final` hoàn toàn không thực thi interface mục tiêu, kiểm tra đó không có khả năng thành công và có thể bị coi là lỗi kiểu. Đồng thời, Java 17 không chấp nhận một số *unconditional type patterns* khi kiểu tĩnh của biểu thức đã là subtype của kiểu pattern (ví dụ một biến `String` lại được match trực tiếp thành `String`). Khi chỉ muốn biết biến đã khai báo là `String` có khác `null` hay không, hãy dùng `s != null`.

**Phạm vi đúng không bảo đảm hành vi của method không ném lỗi:** compiler biết `text` là `String` và `text.length()` hợp lệ; với interface như `service.process()`, ngoại lệ do logic method vẫn có thể xảy ra. Pattern matching giải quyết **an toàn về kiểu**, không tự chứng minh nghiệp vụ hoặc tính không lỗi của mọi phương thức.

## 11. Lỗi thường gặp và cách sửa

1. **Nhầm runtime class với kiểu biến pattern.** `value instanceof CharSequence cs` không biến `cs` thành `String` chỉ vì lần này runtime là `String`. Dùng API của `CharSequence` hoặc match `String` nếu cần API riêng.
2. **Cho rằng biến gốc bị đổi kiểu.** `Object value` vẫn là `Object` sau phép kiểm tra; biến mới `String text` mới có các phương thức của `String`.
3. **Sử dụng biến ngoài luồng match.** Biến chỉ được compiler coi là đã gán ở đường đi được bảo đảm pattern thành công. Tránh gọi nó sau `if` mà không có cấu trúc control-flow hợp lệ.
4. **Nhầm tên biến là nguồn suy luận kiểu.** `value instanceof String number` vẫn tạo biến **String**, dù tên là `number`. Chọn tên phản ánh ý nghĩa nhưng chính kiểu trong pattern mới quyết định.
5. **Cho rằng `List<?>` suy ra `String`.** Không thể gọi `items.get(0).toUpperCase()` chỉ từ kiểu `List<?>`; cần kiểm tra phần tử hoặc thông tin kiểu mạnh hơn.
6. **Lấy giá trị runtime để suy đoán kiểu của `var`.** `Box(var x)` với biểu thức có kiểu `Object` không mặc nhiên suy luận `x` là `String`, ngay cả khi runtime đang chứa chuỗi.
7. **Dùng record pattern ở JDK 17 không bật preview.** Record pattern chuẩn hóa từ Java 21; chọn JDK 21+ cho `Point(var x, var y)`.
8. **Dùng `instanceof` primitive như Java 21 đã hỗ trợ rộng rãi.** Với Java 17/21 ổn định, `Integer n` là type pattern tương ứng cho giá trị boxed; primitive component trong record là cơ chế riêng.
9. **Giả định `instanceof` xử lý `null` như match thành công.** Với type pattern trong `instanceof`, `null` luôn trả về false; lập nhánh riêng nếu cần.

## 12. Tự kiểm tra

### Bài 1 — Dự đoán kiểu

```java
Object value = new StringBuilder("abc");
if (value instanceof CharSequence chars) {
    System.out.println(chars.length());
}
```

**Đáp án:** `chars` có kiểu tĩnh `CharSequence`, không phải `StringBuilder`; in `3`. Cú pháp `chars.length()` được interface `CharSequence` khai báo nên hợp lệ.

### Bài 2 — Xác định scope

```java
static int size(Object data) {
    if (!(data instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

**Đáp án:** hợp lệ trên Java 17+. Sau nhánh trả về `0`, mọi đường đi đến `text.length()` đều đã match `String text`. Hàm trả về độ dài nếu `data` là chuỗi, ngược lại trả `0`.

### Bài 3 — Suy luận `var` theo component

Cho Java 21:

```java
record Temperature(double celsius, String unit) {}

static void read(Object input) {
    if (input instanceof Temperature(var c, var u)) {
        double converted = c + 1.0;
        String upperUnit = u.toUpperCase();
        System.out.println(converted + " " + upperUnit);
    }
}
```

**Đáp án:** `c` có kiểu `double` và `u` có kiểu `String` vì `Temperature` khai báo component `double celsius` và `String unit`. Với `new Temperature(20, "c")`, kết quả là `21.0 C`. Nếu `unit` là `null`, `u.toUpperCase()` có thể gây `NullPointerException`; kiểu tĩnh `String` không tự bảo đảm non-null cho component `var`.

### Bài 4 — Đọc thông tin generic

Tại sao đoạn sau không chắc chắn gọi được `toUpperCase()`?

```java
Object raw = new java.util.ArrayList<String>();
if (raw instanceof java.util.List<?> items) {
    // items.get(0).toUpperCase(); // Không hợp lệ về kiểu tĩnh
}
```

**Đáp án:** `items` là `List<?>`, và `items.get(0)` chỉ có kiểu tĩnh `Object`. Compiler không suy ra phần tử là `String` từ runtime generic; thêm kiểm tra phần tử trước khi gọi phương thức riêng của `String`. Ngoài ra, với danh sách trống, gọi `get(0)` còn gây `IndexOutOfBoundsException`; kiểm tra kích thước là vấn đề độc lập với suy luận kiểu.

## 13. Tóm tắt quy tắc

**Kiểu của pattern variable do pattern và ngữ cảnh kiểu lúc biên dịch xác định.** Với `instanceof String s`, `s` là `String`; với `instanceof CharSequence s`, `s` là `CharSequence` dù runtime có thể là `String`. Compiler chỉ cho sử dụng biến tại những đường đi mà pattern khớp chắc chắn.

Với record pattern Java 21+, `var` nhận kiểu từ **component tương ứng của record**, có xét generic context. Tính năng này giúp mã ngắn gọn hơn nhưng không đọc được tham số generic đã bị erasure từ runtime. Khi muốn gọi phương thức riêng của một kiểu, hãy bảo đảm **kiểu tĩnh của biến pattern** có khai báo phương thức đó.

Tài liệu chính thức để đối chiếu:
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java SE 17 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30)
