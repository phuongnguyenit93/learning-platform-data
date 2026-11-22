# Các tên pattern cần nhận diện trong mã nguồn Java 21

## 1. Mục tiêu: đọc mã nguồn và gọi đúng tên cú pháp

Khi đọc một đoạn Java sử dụng **pattern matching**, bạn cần trả lời được ba câu hỏi:

1. **Đoạn nào thực sự là pattern?** Không phải mọi chỗ có `instanceof`, `case`, dấu ngoặc `()` hoặc từ `var` đều là pattern.
2. **Pattern đó tên gì?** Java 21 có hai loại pattern chính thức: **type pattern** và **record pattern**. Những cụm như *nested pattern* hoặc *guarded case label* mô tả cách đặt/kết hợp pattern, không tự động trở thành loại pattern thứ ba.
3. **Nó liên kết những biến nào, khi nào biến có hiệu lực?** Tên trong pattern là biến cục bộ được khai báo khi khớp; tên đó không nhất thiết trùng với tên trường hay component của dữ liệu.

Trong bài này, “pattern” là cú pháp **Java language pattern matching**, khác với *design pattern* (Strategy, Factory, Observer...) và lớp `java.util.regex.Pattern` dùng cho biểu thức chính quy.

Ví dụ đầu tiên:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

- `instanceof`: toán tử kiểm tra kiểu và có thể nhận pattern ở vế phải.
- `String text`: **type pattern**; `String` là kiểu cần kiểm tra, `text` là **pattern variable**.
- `text.length()`: lệnh sử dụng biến đã được liên kết, **không phải** một pattern khác.

## 2. Từ điển các tên sẽ thấy khi đọc Java 21

| Tên thuật ngữ | Dấu hiệu nhận diện trong mã | Đọc đúng nghĩa | Trạng thái trong Java 21 |
| --- | --- | --- | --- |
| **Type pattern** (*mẫu kiểu*) | `String s`, `Number n` trong `instanceof` hoặc `case` | Kiểm tra kiểu, liên kết một biến có tên | Chính thức |
| **Record pattern** (*mẫu record*) | `Point(int x, int y)`, `Box(var v)` ở vị trí pattern | Kiểm tra record và lần lượt khớp các component | Chính thức; JEP 440 |
| **Nested pattern** (*mẫu lồng nhau*) | `Segment(Point(var x, var y), Point(var a, var b))` | Pattern nằm trong danh sách component của record pattern khác | Cách kết hợp pattern chính thức |
| **Inferred type pattern** (*type pattern dùng `var`*) | `Point(var x, var y)` | Kiểu của biến được suy luận từ component của record | Chính thức khi nằm đúng vị trí lồng |
| **Pattern variable** (*biến pattern*) | `s` trong `String s`, `x` trong `int x` | Tên biến được khai báo/gán khi pattern khớp | Khái niệm ngôn ngữ; không phải loại pattern |
| **Pattern case label** | `case String s ->`, `case Point(var x, var y) ->` | Nhãn của một `switch` dùng pattern | Chính thức; JEP 441 |
| **Guarded case label** (*nhãn có điều kiện*) | `case String s when s.isBlank() ->` | Pattern `String s` kèm điều kiện `when` | Chính thức; guard không là loại pattern riêng |
| **Unnamed pattern** (*mẫu không tên*) | `Point(var x, _)` | Bỏ qua một component; không khai báo biến cho chỗ `_` | **Preview** trong Java 21; JEP 443 |
| **Unnamed pattern variable** | `case String _ ->` | Type pattern có biến không có tên sử dụng được | **Preview** trong Java 21; JEP 443 |
| **Unconditional pattern** | Thuật ngữ trong JLS; ví dụ `case Object o` khi selector là `Object` | Một tính chất về mức độ bao phủ kiểu, không phải cú pháp mới | Khái niệm phân tích pattern |

**Tên pháp lý trong ngữ pháp Java SE 21:** `TypePattern` và `RecordPattern` là hai nhánh của `Pattern` tại JLS §14.30.1. Những tên khác trong bảng rất hữu ích khi đọc code, viết tài liệu hoặc review, nhưng phải phân biệt **loại pattern**, **vị trí sử dụng**, **tính chất** và **tính năng preview**.

## 3. Nhận diện type pattern và pattern variable

### 3.1. Một kiểu theo sau bởi tên biến

Nhìn các đoạn sau:

```java
value instanceof String name
value instanceof Number number
case CharSequence text -> ...
case Integer count when count > 0 -> ...
```

Các phần `String name`, `Number number`, `CharSequence text` và `Integer count` là **type pattern**. Trong đó `name`, `number`, `text`, `count` là **pattern variable**.

Cách nhận diện nhanh: hãy tìm **vị trí pattern** (sau `instanceof` hoặc sau `case`) rồi xác định “kiểu + tên biến”. Chỉ nhìn riêng chuỗi `String name` là chưa đủ, bởi cùng chuỗi có thể là khai báo thông thường ở nơi khác.

So sánh:

```java
String name = "Java";               // Khai báo biến cục bộ, không phải pattern
void print(String name) { ... }     // Tham số phương thức, không phải pattern
if (obj instanceof String name) {}  // Type pattern
switch (obj) {
    case String name -> use(name);   // Type pattern trong case label
    default -> {}
}
```

Đoạn trên là các **mảnh cú pháp minh họa riêng**, không phải chương trình hoàn chỉnh để chép nguyên một khối và biên dịch; `use` và `obj` cần được định nghĩa nếu đặt trong chương trình.

### 3.2. `instanceof Type` và `instanceof Type variable` không giống nhau

```java
obj instanceof String    // Phép kiểm tra kiểu truyền thống
obj instanceof String s  // Type pattern, đồng thời tạo biến s
```

Cả hai đều dùng `instanceof`, nhưng dạng đầu không khai báo pattern variable. Dạng sau cho phép dùng `s` trong nhánh mà Java biết phép match thành công.

### 3.3. Flow scoping: tên biến chỉ tồn tại tại nơi đã khớp

```java
if (obj instanceof String s && !s.isBlank()) {
    System.out.println(s.toUpperCase());
}
```

Vế phải `&&` chỉ được đánh giá khi `obj instanceof String s` là `true`, nên `s` đã được gán. Ngược lại, không thể tùy tiện dùng `s` sau `||` vì vế trái có thể không khớp. Java gọi cách xác định phạm vi theo luồng điều khiển này là **flow scoping**.

Ví dụ hợp lệ khác:

```java
static int lengthOrMinusOne(Object obj) {
    if (!(obj instanceof String s)) {
        return -1;
    }
    return s.length();
}
```

Sau nhánh `return -1`, Java biết `s` đã được liên kết. Pattern variable **không tự trở thành field** của class hay thuộc tính của đối tượng.

## 4. Nhận diện record pattern qua dấu ngoặc chứa các pattern con

Xét khai báo dữ liệu:

```java
record Point(int x, int y) {}
record Marker(Point point, String label) {}
```

Tại một vị trí pattern, biểu thức sau là **record pattern**:

```java
obj instanceof Point(int a, int b)
```

Phân tích cú pháp:

- `Point`: tên **kiểu record** cần khớp.
- `(int a, int b)`: danh sách hai **component patterns**; cả `int a` và `int b` là type pattern nằm trong record pattern.
- `a` và `b`: hai pattern variable mới. Chúng **không phải** tên record component được khai báo trong `record Point(int x, int y)`.
- Số phần tử bên trong dấu ngoặc phải bằng số component của record và đúng thứ tự.

Do đó, cách đọc `Point(int a, int b)` không phải “gọi constructor `Point`”, mà là “giải cấu trúc một `Point` thành hai giá trị”.

### 4.1. Ba dòng giống nhau nhưng có ý nghĩa khác nhau

```java
record Point(int x, int y) {}         // Khai báo kiểu record
Point p = new Point(1, 2);           // Khởi tạo đối tượng
if (obj instanceof Point(int a, int b)) { // Record pattern
    System.out.println(a + b);
}
```

Dấu `()` trong khai báo `record`, lời gọi `new`, và record pattern có vai trò khác nhau; **ngữ cảnh cú pháp** mới cho biết đâu là pattern.

Ngoài ra, `obj instanceof Point p` là **type pattern** vì sau `Point` là một tên biến. `obj instanceof Point(var x, var y)` là **record pattern** vì sau `Point` là danh sách pattern con.

### 4.2. `var` trong record pattern

```java
if (obj instanceof Point(var a, var b)) {
    System.out.println(a + b);
}
```

Từ `record Point(int x, int y)`, trình biên dịch biết `a` và `b` là `int`. Khi nhìn `var a` hoặc `var b` **bên trong record pattern**, hãy gọi đó là **type pattern với kiểu được suy luận**.

Không thể suy ra rằng `obj instanceof var anything` cũng hợp lệ: **type pattern đứng đầu** (top-level) của `instanceof` trong Java 21 phải chỉ rõ kiểu tham chiếu, không dùng `var`.

### 4.3. Record pattern không nhất thiết tạo biến

```java
record Done() {}

static boolean completed(Object obj) {
    return obj instanceof Done();
}
```

`Done()` là record pattern với danh sách component rỗng; nó kiểm tra một record không có component nào. Không phải pattern nào cũng phải sinh ra pattern variable. Đặc biệt, record pattern **tự nó** không khai báo một biến đại diện cho toàn record; các biến đến từ pattern con.

## 5. Nhận diện nested pattern và tên từng biến

Nested pattern xuất hiện khi một pattern đứng trong danh sách component của **record pattern khác**. Ví dụ:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}

static String describe(Object obj) {
    if (obj instanceof Segment(
            Point(var startX, var startY),
            Point(var endX, var endY))) {
        return startX + "," + startY + " -> " + endX + "," + endY;
    }
    return "not a segment";
}
```

Đọc từ ngoài vào trong:

1. `Segment(...)` là **record pattern ngoài**.
2. Hai `Point(...)` là **record pattern lồng bên trong**.
3. `var startX`, `var startY`, `var endX`, `var endY` là **type pattern suy luận kiểu**, được khai báo trực tiếp ở các vị trí component `Point`.
4. `startX`, `startY`, `endX`, `endY` là bốn **pattern variable** có thể dùng khi toàn bộ match thành công.

Với `new Segment(new Point(1, 2), new Point(7, 8))`, phương thức trả về `"1,2 -> 7,8"`.

Có thể trộn type pattern rõ kiểu và `var` trong cùng một record pattern:

```java
obj instanceof Marker(Point(int x, int y), String color)
obj instanceof Marker(Point(var x, var y), var color)
```

Cả hai đều có **record pattern** ngoài `Marker(...)`, **record pattern** trong `Point(...)`, và các **type pattern** tại vị trí component. `String color` hoặc `var color` liên kết giá trị component `label`, dù biến được đặt tên là `color`.

**Phân biệt lỗi hay gặp:** khi component `point` của một `Marker` là `null`, record pattern lồng `Point(...)` **không khớp**. Một type pattern lồng có thể có quy tắc khớp `null` riêng khi nó là **unconditional** cho kiểu component; đừng tổng quát rằng mọi pattern con đều xử lý `null` giống nhau. Khi logic yêu cầu dữ liệu không được `null`, hãy bảo đảm điều đó bằng kiểm tra hoặc ràng buộc dữ liệu.

## 6. Nhận diện pattern trong `switch` và điều kiện `when`

Ví dụ:

```java
static String classify(Object obj) {
    return switch (obj) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s -> "string";
        case Integer n when n > 0 -> "positive integer";
        case Integer n -> "other integer";
        default -> "other type";
    };
}
```

Gọi tên đúng trong từng nhánh:

- `case String s`: **pattern case label** có **type pattern** `String s`.
- `case String s when s.isBlank()`: **guarded case label**; pattern vẫn là `String s`, còn `s.isBlank()` là điều kiện **guard**.
- `case Integer n`: **type pattern**, biến pattern tên `n`.
- `case null`: **null case label**, **không phải** một loại pattern.
- `default`: **default label**, **không phải** pattern.

Guard `when` chỉ được xét sau khi pattern đã khớp. `when` trong `switch` không thay thế `&&` sau `instanceof`:

```java
if (obj instanceof String s && s.length() > 3) { /* ... */ }
```

### 6.1. Thứ tự nhánh và dominance

Trong `switch`, nhánh rộng có thể làm nhánh hẹp không bao giờ chạy:

```java
// Mã minh họa lỗi biên dịch:
switch (obj) {
    case CharSequence sequence -> System.out.println(sequence.length());
    case String text -> System.out.println(text); // Bị nhánh trên bao phủ
    default -> {}
}
```

`String` triển khai `CharSequence`. Vì thế `case String text` đứng sau `case CharSequence sequence` bị **dominated**. Hãy sắp xếp nhánh cụ thể trước nhánh tổng quát.

Với guard, thường đặt nhánh hằng cụ thể trước, nhánh `when` kế tiếp và nhánh không có guard cuối cùng để các trường hợp đặc biệt được ưu tiên. Tránh đoán rằng compiler có thể suy luận mọi điều kiện `when`; điều kiện tùy ý có thể phức tạp và không được dùng như một cơ chế thay thế thứ tự nhánh rõ ràng.

### 6.2. Exhaustiveness: hiểu nhãn nào bao phủ những giá trị nào

Với `switch` expression, các nhánh phải đủ để trả về kết quả trong mọi trường hợp hợp lệ. Khi selector mang kiểu `sealed`, có thể liệt kê các subtype được phép:

```java
sealed interface Event permits Started, Stopped {}
record Started(long id) implements Event {}
record Stopped(String reason) implements Event {}

static String describeEvent(Event event) {
    return switch (event) {
        case Started(var id) -> "start " + id;
        case Stopped(var reason) -> "stop " + reason;
    };
}
```

Đây là **đoạn minh họa** đặt các khai báo vào cùng đơn vị biên dịch phù hợp. Hai nhánh chứa **record pattern**, mỗi nhánh giải cấu trúc một subtype. Với kiểu `Event`, trình biên dịch thấy toàn bộ các subtype được phép đã được xử lý; nếu có thể nhận `null`, hãy thêm nhánh `case null` hoặc kiểm tra trước. Nhớ rằng `default` tự nó không bảo đảm bắt `null`.

## 7. Phân biệt những thứ trông giống pattern nhưng không phải pattern

| Đoạn mã gặp khi đọc | Tên chính xác | Có phải pattern không? |
| --- | --- | --- |
| `obj instanceof String` | Phép kiểm tra kiểu `instanceof` | **Không** |
| `obj instanceof String s` | `instanceof` dùng **type pattern** | **Có**: `String s` |
| `case Point p ->` | `case` chứa **type pattern** | **Có**: `Point p` |
| `case Point(var x, var y) ->` | `case` chứa **record pattern** | **Có** |
| `record Point(int x, int y) {}` | Khai báo record và các component | **Không** |
| `new Point(3, 5)` | Tạo đối tượng bằng constructor | **Không** |
| `Point p = new Point(3, 5)` | Khai báo biến và tạo đối tượng | **Không** |
| `case 100 ->` | Nhãn hằng số của `switch` | **Không** |
| `case RED ->` | Nhãn hằng `enum` | **Không** |
| `case null ->` | Nhãn dành cho `null` | **Không** |
| `default ->` | Nhãn mặc định | **Không** |
| `String pattern = ".*";` | Biến thông thường tên `pattern` | **Không** |
| `Pattern.compile(".*")` | API regular expression | **Không** |
| `case String s when s.isEmpty() ->` | Type pattern + guard | **Có**: `String s`; **không**: `when` |

**Không có “constant pattern” tổng quát như một loại pattern độc lập trong ngữ pháp Java 21.** Các hằng `case` là **constant case labels**, còn `case null` là trường hợp nhãn riêng. Cũng không có cú pháp Java 21 thông thường để giải cấu trúc list/array bằng một list pattern như một số ngôn ngữ khác.

## 8. Những tên xuất hiện trong ví dụ preview cũ hoặc mới

Khi đọc blog hoặc mã của các bản preview Java 17–21, cần đối chiếu phiên bản.

### 8.1. Unnamed pattern `_` trong Java 21: preview

```java
record Point(int x, int y) {}

if (obj instanceof Point(var x, _)) {
    System.out.println(x);
}
```

Dấu `_` là **unnamed pattern** tại vị trí component thứ hai: khớp và bỏ qua thành phần đó, không sinh tên biến để sử dụng. Cú pháp này được **preview** tại Java 21 (JEP 443), nên không biên dịch mặc định ở chế độ Java 21 chuẩn.

Còn `case String _ ->` được gọi là **type pattern với unnamed pattern variable**, cũng thuộc tính năng preview; nó khác với dấu `_` đứng một mình trong danh sách component. Bạn không thể dùng `_` như một biến có tên sau đó.

Lưu **`PreviewNames.java`** để chạy ví dụ preview hoàn chỉnh:

```java
public class PreviewNames {
    record Point(int x, int y) {}
    record Tagged(Point point, String label) {}

    static String firstX(Object obj) {
        return switch (obj) {
            case Tagged(Point(var x, _), _) -> "x = " + x;
            default -> "not tagged";
        };
    }

    public static void main(String[] args) {
        System.out.println(firstX(
                new Tagged(new Point(5, 9), "demo")));
    }
}
```

Dùng **JDK 21** và bật preview ở cả lúc biên dịch lẫn khi chạy:

```bash
javac --enable-preview --release 21 PreviewNames.java
java --enable-preview PreviewNames
```

Kết quả:

```text
x = 5
```

Nếu dự án không bật preview, dùng một tên biến thông thường mà không cần sử dụng: `Point(var x, var ignoredY)`. Unnamed patterns/variables chỉ trở thành tính năng chính thức ở Java 22 (JEP 456); trạng thái đó không áp dụng ngược cho Java 21.

### 8.2. Parenthesized pattern đã bị loại khỏi Java 21

Các ví dụ preview cũ có thể viết `case (String s) ->` và gọi là *parenthesized pattern*. **Java 21 đã loại cú pháp parenthesized pattern.** Viết `case String s ->` trong mã Java 21 hiện hành. Tương tự, các cú pháp preview cũ sử dụng `case String s && condition` đã được thay bằng `case String s when condition`.

### 8.3. “Deconstruction” là thuật ngữ, không phải phép khởi tạo

Bạn có thể gặp tên *record deconstruction* hoặc *deconstruction pattern* khi đọc tài liệu về record. Trong ngữ cảnh Java 21, hãy đối chiếu với **record pattern** đang giải cấu trúc component. Dạng `Point(var x, var y)` chỉ là pattern tại vị trí được phép; khi tạo đối tượng thì cú pháp là `new Point(...)`.

## 9. Một chương trình Java 21 để luyện nhận diện

Tệp **`PatternReader.java`** dưới đây sử dụng Java 21 chuẩn, **không cần preview**:

```java
public class PatternReader {
    record Point(int x, int y) {}
    record Marker(Point point, String label) {}

    static String inspect(Object obj) {
        if (obj instanceof Marker(Point(var x, var y), String name)) {
            return "marker " + name + " at " + x + "," + y;
        }

        return switch (obj) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text -> "text(" + text.length() + ")";
            case Integer number when number > 0 -> "positive " + number;
            case Integer number -> "integer " + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] samples = {
            new Marker(new Point(2, 5), "A"),
            " ", "hi", 7, -2, null, 3.14
        };
        for (Object value : samples) {
            System.out.println(inspect(value));
        }
    }
}
```

Biên dịch bằng JDK 21 hoặc JDK mới hơn có hỗ trợ đích Java 21, rồi chạy:

```bash
javac --release 21 PatternReader.java
java PatternReader
```

Stdout:

```text
marker A at 2,5
blank
text(2)
positive 7
integer -2
null
other
```

**Đánh dấu ngay trên mã để ghi nhớ tên pattern:**

- `Marker(Point(var x, var y), String name)` → **record pattern ngoài** `Marker`, **nested record pattern** `Point`, ba **type pattern con** `var x`, `var y`, `String name`; chúng khai báo các biến `x`, `y`, `name`.
- `case String text when text.isBlank()` → **type pattern** `String text` trong một **guarded case label**.
- `case String text`, `case Integer number` → các **type pattern** khác; tên biến chỉ tồn tại trong nhánh hoặc vùng được flow scoping cho phép.
- `case null` và `default` → nhãn đặc biệt, không có pattern variable.
- `record Point(...)`, `record Marker(...)` → khai báo kiểu; `new Marker(new Point(...), "A")` → tạo dữ liệu; **không phải** pattern.

## 10. Bài tập đọc mã nguồn và đáp án

**Bài 1.** Trong những dòng sau, hãy khoanh vùng chính xác phần là pattern và đặt tên:

```java
Object data = "abc";
boolean a = data instanceof String;
boolean b = data instanceof String value;
```

**Đáp án:** Dòng khai báo `a` chỉ kiểm tra kiểu, không dùng pattern; dòng `b` có **type pattern** `String value`; tên biến pattern là `value`, không phải `data`. Dùng `value` ngoài phạm vi Java biết pattern khớp là lỗi.

**Bài 2.** Trong đoạn mã sau có bao nhiêu record pattern, bao nhiêu type pattern?

```java
record Pair(int first, int second) {}
record Packet(Pair pair, String tag) {}

// Mảnh biểu thức trong một nhánh kiểm tra hợp lệ:
obj instanceof Packet(Pair(var left, var right), String label)
```

**Đáp án:** Hai **record pattern**: `Packet(...)` và `Pair(...)`. Ba **type pattern**: `var left`, `var right`, `String label`. `left`, `right`, `label` là ba pattern variable. Khai báo `record Pair(...)` và `record Packet(...)` không tính là pattern.

**Bài 3.** `case Integer n when n < 0 ->` có phải là “when pattern” hay “negative number pattern” không?

**Đáp án:** Không. `Integer n` là **type pattern**; `when n < 0` là **guard**; cả nhánh được gọi là **guarded case label**. Trong Java 21 không có loại pattern riêng tên “negative number pattern”.

**Bài 4.** Vì sao hai biểu thức sau có trạng thái phiên bản khác nhau?

```java
obj instanceof Point(var x, var y)
obj instanceof Point(var x, _)
```

**Đáp án:** Dòng đầu dùng **record pattern** với hai **type pattern suy luận kiểu**, đã chính thức trong Java 21. Dòng sau có **unnamed pattern** `_`, thuộc **preview của Java 21** nên cần `--enable-preview`. Cả hai phải đặt trong ngữ cảnh có khai báo `Point` phù hợp.

## 11. Checklist khi review một đoạn Java dùng pattern

1. **Xác định vị trí:** sau `instanceof`, trong `case`, hay trong danh sách component của một record pattern?
2. **Nhận dạng lõi:** “kiểu + biến” là **type pattern**; “tên record + danh sách pattern con” là **record pattern**.
3. **Tách pattern lồng:** đếm đúng mọi record pattern và type pattern, đi từ ngoài vào trong.
4. **Tách tên biến:** tên pattern variable có thể khác tên record component; kiểm tra phạm vi sử dụng theo control flow.
5. **Tách nhãn và guard:** `case` là vị trí đặt pattern; `when` là điều kiện; `case null`, `default`, hằng số `case` không phải pattern.
6. **Kiểm tra thứ tự `switch`:** nhánh cụ thể trước nhánh tổng quát để tránh dominance; xem các nhánh có exhaustive không.
7. **Kiểm tra phiên bản:** record pattern và pattern `switch` chính thức trong Java 21; `_` cho unnamed patterns/variables vẫn là preview; parenthesized patterns đã bị loại.
8. **Đọc đúng ngữ cảnh:** `record Point(...)` khai báo dữ liệu, `new Point(...)` khởi tạo, `Point(...)` tại vị trí pattern mới là record pattern.

## 12. Tài liệu tiêu chuẩn

- [Java Language Specification, Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): định nghĩa và ngữ pháp `TypePattern`, `RecordPattern`, scope của biến pattern.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): guard, dominance và kiểu nhãn `case`.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record pattern là tính năng chính thức trong Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern `switch` là tính năng chính thức trong Java 21.
- [Oracle Java 21 — Unnamed Patterns and Variables](https://docs.oracle.com/en/java/javase/21/language/unnamed-variables-and-patterns.html) và [JEP 443](https://openjdk.org/jeps/443): phân biệt unnamed pattern với unnamed pattern variable, yêu cầu preview.
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): trạng thái chuẩn/preview và các thay đổi cú pháp theo phiên bản.
