# Các loại pattern trong Java 21

## 1. Pattern matching là gì?

Trong Java, **pattern** mô tả cách kiểm tra một giá trị có phù hợp với một cấu trúc hoặc kiểu dữ liệu hay không. Khi khớp, pattern có thể khai báo và gán giá trị cho các **pattern variable** để dùng trực tiếp trong nhánh xử lý. Pattern matching giúp thay thế nhiều đoạn kiểm tra kiểu, ép kiểu và truy cập từng thành phần thủ công.

Ví dụ với kiểu dữ liệu:

```java
Object value = "Java 21";

if (value instanceof String text) {
    System.out.println(text.length()); // 7
}
```

Ở đây `String text` là **type pattern**: Java kiểm tra `value` có phải `String` hay không và, nếu đúng, khai báo `text` có kiểu `String`. Không cần ép kiểu lại bằng `(String) value`.

**Pattern của ngôn ngữ Java không phải regular expression** (biểu thức chính quy): `String.matches(...)` tìm mẫu ký tự; `String text` là mẫu về kiểu đối tượng.

## 2. Java 21 có những loại pattern nào?

Theo Java Language Specification của **Java SE 21**, hai loại pattern chính thức là **type pattern** và **record pattern**. Các cách dùng như pattern lồng nhau, guard trong `switch`, hoặc kiểm tra `null` cần được phân biệt với hai loại cú pháp gốc ấy.

| Cú pháp / kỹ thuật | Ví dụ ngắn | Ý nghĩa | Trạng thái trong Java 21 |
| --- | --- | --- | --- |
| **Type pattern** | `obj instanceof String s` | Kiểm tra kiểu và liên kết biến `s` | Chính thức; pattern cho `instanceof` ổn định từ Java 16 |
| **Record pattern** | `obj instanceof Point(int x, int y)` | Kiểm tra record và lấy các component | Chính thức trong Java 21 (JEP 440) |
| **Nested pattern** | `Box(Point(var x, var y))` | Kết hợp nhiều pattern, giải cấu trúc nhiều tầng | Cách kết hợp type/record pattern, chính thức |
| **Pattern trong `switch`** | `case String s -> ...` | Chọn nhánh bằng pattern, thay vì chỉ hằng số | Chính thức trong Java 21 (JEP 441) |
| **Guard của `case`** | `case String s when s.isBlank() -> ...` | Thêm điều kiện sau khi pattern khớp | Cú pháp của `switch`, **không phải loại pattern độc lập** |
| **Unnamed pattern `_`** | `Point(var x, _)` | Bỏ qua component không cần dùng | **Preview trong Java 21** (JEP 443); cần bật preview |
| **`case null`** | `case null -> ...` | Xử lý riêng giá trị `null` | Nhãn `switch`, **không phải pattern** |

Lưu ý: `var` bên trong `Point(var x, var y)` cho trình biên dịch suy luận kiểu của các component; nó không tạo ra một loại pattern riêng. Với **mã Java 21 thông thường**, bạn chỉ cần JDK 21, không cần `--enable-preview` để dùng type pattern, record pattern và pattern `switch`.

## 3. Type pattern: kiểm tra kiểu rồi sử dụng biến đã được kiểm tra

### 3.1. Dùng với `instanceof`

Cách cũ phải kiểm tra kiểu rồi ép kiểu:

```java
if (obj instanceof String) {
    String s = (String) obj;
    System.out.println(s.length());
}
```

Type pattern thực hiện cả kiểm tra lẫn liên kết biến:

```java
if (obj instanceof String s) {
    System.out.println(s.length());
}
```

Biến `s` chỉ ở trong **phạm vi mà Java biết pattern đã khớp** (flow scoping). Ví dụ sau hợp lệ:

```java
if (obj instanceof String s && !s.isBlank()) {
    System.out.println(s.toUpperCase());
}
```

Vế phải của `&&` chỉ được đánh giá khi vế trái đúng, nên `s` đã được gán. Không thể dùng `s` theo cách tương tự ở vế phải của `||`: khi vế trái sai, `s` chưa được gán.

Ví dụ về phạm vi sau kiểm tra phủ định:

```java
static int textLength(Object obj) {
    if (!(obj instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Sau nhánh `return`, phần còn lại chỉ chạy khi `obj instanceof String text` đúng. Đây là một lợi ích của flow scoping.

### 3.2. Dùng type pattern trong `switch`

Khi có nhiều kiểu cần phân nhánh, `switch` dễ đọc hơn chuỗi `if / else if`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case Integer n -> "Số nguyên: " + n;
        case String s -> "Chuỗi dài " + s.length();
        default -> "Kiểu khác";
    };
}
```

Mỗi biến `n`, `s` chỉ dùng trong nhánh tương ứng. `switch` expression phải trả về giá trị cho mọi trường hợp có thể xảy ra; `default` ở đây bao phủ các kiểu khác. `case null` xử lý `null` rõ ràng.

## 4. Record pattern: kiểm tra và giải cấu trúc record

Một `record` định nghĩa dữ liệu theo các **record component**. Record pattern cho phép lấy các component ngay lúc kiểm tra, không cần gọi từng accessor thủ công.

Giả sử:

```java
record Point(int x, int y) {}
```

Trước Java 21, cách thường dùng là:

```java
if (obj instanceof Point p) {
    int x = p.x();
    int y = p.y();
    System.out.println(x + ", " + y);
}
```

Với record pattern trong Java 21:

```java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + ", " + y);
}
```

**Đọc cú pháp:** `Point(int x, int y)` yêu cầu giá trị là một `Point` và khớp lần lượt hai component `x`, `y`; đồng thời khai báo hai biến cục bộ `x` và `y`.

Các quy tắc cần nhớ:

- Pattern phải tham chiếu tới **kiểu record**, không thể dùng cú pháp này để tự động giải cấu trúc một class thông thường.
- Số lượng pattern con phải **đúng bằng số record component** và thứ tự phải tương ứng với thứ tự khai báo record.
- Các component phải tương thích kiểu với pattern con. `var` có thể giúp tránh lặp tên kiểu khi kiểu đã rõ.
- Record pattern **không tự gọi lại constructor** hay tạo bản sao record; nó kiểm tra giá trị và truy xuất component để đối chiếu.
- Không được viết `Point(int x)` nếu `Point` có hai component, và không thể dùng `...` để bỏ qua số component còn lại.

### 4.1. `var` trong record pattern

```java
if (obj instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Trình biên dịch suy luận `x` và `y` đều là `int` từ khai báo `Point`. Tương tự, với `record Pair<T>(T first, T second) {}`, thông tin kiểu của giá trị ở vị trí dùng pattern có thể giúp Java suy luận các tham số kiểu và kiểu của component.

`var` trong thành phần record không có nghĩa là bạn có thể viết `obj instanceof var x` để khớp mọi giá trị.

## 5. Nested pattern: kết hợp record pattern nhiều tầng

Nested pattern là **cách lồng các pattern**, không phải loại thứ ba độc lập trong Java 21.

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}

static String endpoints(Object obj) {
    if (obj instanceof Segment(
            Point(var x1, var y1),
            Point(var x2, var y2))) {
        return "(" + x1 + "," + y1 + ") -> (" + x2 + "," + y2 + ")";
    }
    return "Không phải đoạn thẳng hợp lệ";
}
```

Giải thích từng tầng:

1. `Segment(...)` kiểm tra đối tượng bên ngoài và giải cấu trúc `start`, `end`.
2. Hai `Point(...)` kiểm tra tiếp các component `Point` bên trong.
3. `var x1`, `var y1`, `var x2`, `var y2` liên kết trực tiếp bốn tọa độ.
4. Chỉ khi **toàn bộ** pattern khớp thì nhánh `if` được thực hiện.

Ví dụ `new Segment(new Point(1, 2), new Point(4, 6))` sẽ cho chuỗi `(1,2) -> (4,6)`.

Với component cần được giải cấu trúc tiếp, giá trị `null` ở tầng đó làm nested record pattern không khớp. Đừng giả định một component kiểu record luôn khác `null`. Hãy kiểm tra dữ liệu đầu vào nếu mô hình cho phép `null`.

## 6. Pattern `switch`, guard `when` và thứ tự nhánh

Java 21 cho phép nhánh `case` chứa type pattern hoặc record pattern. Bạn có thể thêm **guard** bằng `when` để lọc sâu hơn:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "Chuỗi trống/trắng";
        case String s -> "Chuỗi thường";
        case Integer n when n > 0 -> "Số nguyên dương";
        case Integer n -> "Số nguyên không dương";
        default -> "Loại khác";
    };
}
```

Quy trình khớp một nhánh có guard:

1. Đánh giá giá trị chọn của `switch`.
2. Kiểm tra pattern của nhánh `case`.
3. Nếu pattern khớp, đánh giá điều kiện sau `when`; nếu đúng thì chạy nhánh đó.
4. Nếu pattern hoặc guard không khớp, xét các nhánh tiếp theo.

**Thứ tự rất quan trọng.** Nhánh cụ thể nên đi trước nhánh tổng quát. Chẳng hạn:

```java
// Sai: CharSequence đã bao phủ mọi String.
switch (value) {
    case CharSequence cs -> System.out.println(cs.length());
    case String s -> System.out.println(s); // Lỗi biên dịch: dominated case
    default -> {}
}
```

Trình biên dịch phát hiện `case String s` không thể được chọn vì mọi `String` đều là `CharSequence`, và nhánh tổng quát đứng trước đã bao phủ nó. Đây là quy tắc **dominance**.

Guard `when` không phải cú pháp đứng độc lập sau `instanceof`. Với `instanceof`, dùng toán tử logic:

```java
if (value instanceof String s && s.length() > 5) {
    System.out.println(s);
}
```

Trong `switch`, `case null` giúp xử lý `null`. Nếu không có nhánh `case null` phù hợp, một pattern `switch` nhận giá trị `null` thường ném `NullPointerException` trước khi vào `default`. Đừng coi `default` là cách thay thế `case null`.

### 6.1. Exhaustiveness với `sealed` type

Khi phân nhánh trên một hệ phân cấp `sealed`, trình biên dịch có thể biết đầy đủ các nhánh con:

```java
sealed interface Result permits Success, Failure {}
record Success(String value) implements Result {}
record Failure(String message) implements Result {}

static String render(Result result) {
    return switch (result) {
        case Success(var value) -> "OK: " + value;
        case Failure(var message) -> "ERR: " + message;
    };
}
```

Đây là **đoạn mã minh họa** cần đặt trong một đơn vị biên dịch Java hợp lệ cùng các khai báo đi kèm. Cả hai kiểu được `permits` đều đã được xử lý, nên `switch` expression không cần `default` cho các giá trị khác `null`. Nếu thêm một subtype được phép mới, trình biên dịch buộc bạn xem lại tính bao phủ. `null` vẫn cần xử lý nếu có thể xuất hiện.

Với pattern `switch` statement (enhanced `switch`), Java 21 cũng yêu cầu tính bao phủ; còn `switch` expression vốn luôn phải đầy đủ. Điều này giúp phát hiện nhánh xử lý còn thiếu ngay ở thời điểm biên dịch.

## 7. Ví dụ Java 21 hoàn chỉnh, không dùng preview

Lưu toàn bộ mã dưới đây vào **`PatternKindsDemo.java`**:

```java
public class PatternKindsDemo {
    record Point(int x, int y) {}
    record ColoredPoint(Point point, String color) {}

    static String inspect(Object value) {
        if (value instanceof String s) {
            return "String length = " + s.length();
        }
        if (value instanceof ColoredPoint(
                Point(int x, int y), String color)) {
            return "Point = (" + x + ", " + y + "), color = " + color;
        }
        return "Other";
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank string";
            case String s -> "text";
            case Integer n when n > 0 -> "positive integer";
            case Integer n -> "other integer";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect("Java"));
        System.out.println(inspect(
                new ColoredPoint(new Point(2, 3), "red")));
        System.out.println(classify(null));
        System.out.println(classify("   "));
        System.out.println(classify("ok"));
        System.out.println(classify(7));
        System.out.println(classify(-2));
    }
}
```

Biên dịch và chạy bằng **JDK 21**:

```bash
javac --release 21 PatternKindsDemo.java
java PatternKindsDemo
```

Kết quả chuẩn:

```text
String length = 4
Point = (2, 3), color = red
null
blank string
text
positive integer
other integer
```

Trong một chương trình, ví dụ kết hợp được bốn kỹ thuật: **type pattern** với `String`, **record pattern** với `ColoredPoint`, **nested pattern** với `Point`, và **guard** `when` trong pattern `switch`. Toàn bộ thuộc các tính năng chính thức của Java 21.

## 8. Unnamed pattern `_`: tính năng preview riêng trong Java 21

JEP 443 cho phép dùng dấu gạch dưới `_` để **bỏ qua component của record** mà chương trình không cần sử dụng. Đây là **preview trong Java 21**, khác trạng thái với record pattern chuẩn.

Ví dụ: lấy tọa độ `x` nhưng bỏ qua `y` và nhãn màu. Lưu vào **`PreviewPatternDemo.java`**:

```java
public class PreviewPatternDemo {
    record Point(int x, int y) {}
    record LabeledPoint(Point point, String label) {}

    static String xOf(Object obj) {
        return switch (obj) {
            case LabeledPoint(Point(int x, _), _) -> "x = " + x;
            default -> "unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(
                xOf(new LabeledPoint(new Point(3, 9), "red")));
    }
}
```

Biên dịch và chạy bằng **JDK 21**, có bật preview ở **cả hai bước**:

```bash
javac --enable-preview --release 21 PreviewPatternDemo.java
java --enable-preview PreviewPatternDemo
```

Kết quả:

```text
x = 3
```

Phân biệt các cú pháp dễ nhầm:

- `Point(var x, var y)`: cả `x` và `y` đều có tên để tham chiếu; dùng được không cần preview.
- `Point(var x, _)`: chỉ liên kết `x`; dấu `_` là **unnamed pattern** ở vị trí component, cần preview trên JDK 21.
- `case String _ -> ...`: biến pattern không có tên, cũng thuộc tính năng preview trên JDK 21.
- `case _ -> ...` hoặc `obj instanceof _`: **không phải** cách viết wildcard pattern tự do hợp lệ trong Java 21.
- Unnamed **variable** ở khai báo biến, `catch` hoặc lambda cũng được JEP 443 đề cập, nhưng đó là phạm vi dùng dấu `_` khác với unnamed pattern bên trong record.

Khi không muốn phụ thuộc preview, hãy viết `Point(var x, var ignoredY)` và đơn giản không sử dụng `ignoredY`. Dấu `_` và unnamed variables/patterns trở thành tính năng chính thức từ **Java 22 (JEP 456)**; đừng áp dụng trạng thái Java 22 ngược lại cho bài Java 21.

## 9. Lỗi thường gặp và cách sửa

| Tình huống | Vì sao sai hoặc dễ gây lỗi | Cách xử lý |
| --- | --- | --- |
| `obj instanceof String s` rồi dùng `s` trong đường đi mà pattern có thể không khớp | Biến pattern chỉ có scope khi đã được gán | Sử dụng `s` trong nhánh đúng, sau guard `return`, hoặc vế phải `&&` hợp lệ |
| Đặt `case Object o` / `case CharSequence cs` trước pattern cụ thể | Nhánh cụ thể có thể bị **dominated** | Đặt pattern cụ thể trước tổng quát |
| Viết `case String s when ...` rồi tưởng `when` dùng được cho `instanceof` | `when` là guard của nhánh pattern trong `switch` | Dùng `&&` sau `instanceof` |
| Dùng `case null` không có, kỳ vọng `default` xử lý `null` | `switch` có thể ném `NullPointerException` | Thêm `case null` hoặc kiểm tra `null` trước |
| Dùng `Point(var x)` khi record có hai component | Số component pattern không khớp record | Viết đủ vị trí, chẳng hạn `Point(var x, var y)` |
| Dùng record pattern cho class thường | Cú pháp deconstruction này chỉ áp dụng cho `record` | Dùng type pattern và gọi getter/accessor bình thường |
| Dùng `_` trên JDK 21 mà không bật preview | Unnamed pattern chưa chính thức ở Java 21 | Bật `--enable-preview` hoặc dùng biến đặt tên |
| Viết `instanceof int n` để match số nguyên boxed | Java 21 không có type pattern primitive tự do theo cách đó | Dùng `instanceof Integer n`; với record component `int` có thể dùng `Point(int x, int y)` |
| Coi record pattern là kiểm tra các field riêng lẻ không theo thứ tự | Nó giải cấu trúc theo **component được khai báo** | Kiểm tra đúng thứ tự và kiểu của từng component |

## 10. Chọn pattern phù hợp với bài toán

Nếu chỉ cần biết đối tượng thuộc kiểu nào và dùng một biến đã kiểm tra, hãy dùng **type pattern**. Nếu dữ liệu được thiết kế bằng `record` và cần truy cập component, dùng **record pattern**. Nếu dữ liệu có các `record` lồng nhau, lồng **record pattern** để biểu đạt cấu trúc trực tiếp. Nếu nhiều kiểu phải đi vào các nhánh hành động khác nhau, dùng **pattern `switch`**; thêm `when` khi một nhánh cần điều kiện bổ sung. Chỉ dùng **unnamed pattern `_`** nếu dự án Java 21 cho phép preview và bạn thực sự cần bỏ qua thành phần.

**Tự kiểm tra nhanh:**

1. `String s` trong `case String s` thuộc loại nào? → **Type pattern**, đặt trong nhánh `switch`.
2. `Point(int x, int y)` là gì? → **Record pattern**, lấy hai component.
3. `Segment(Point(var x1, var y1), Point(var x2, var y2))` là gì? → **Record pattern lồng record pattern**.
4. `when x > 0` có phải pattern riêng? → **Không**; đó là guard của nhánh pattern `switch`.
5. `Point(var x, _)` chạy mặc định trên JDK 21? → **Không**; cần `--enable-preview`.

## 11. Tài liệu chuẩn để tra cứu

- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): định nghĩa và phân loại type/record patterns.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns là tính năng chính thức của Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern labels, guards, dominance, exhaustiveness và `null`.
- [JEP 443 — Unnamed Patterns and Variables (Preview)](https://openjdk.org/jeps/443): cú pháp `_` dưới chế độ preview trong Java 21.
- [Oracle Java SE 21 — Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): bảng trạng thái chính thức của các tính năng Java 21.
