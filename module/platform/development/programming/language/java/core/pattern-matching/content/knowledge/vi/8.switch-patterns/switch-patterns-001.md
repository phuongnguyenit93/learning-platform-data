# Pattern matching trong `switch statement` (Java 21+)

## 1. Tổng quan: `switch` không còn chỉ so sánh hằng số

Trong các phiên bản Java truyền thống, `switch` thường chọn nhánh theo hằng số `int`, `String` hoặc `enum`. **Pattern matching for switch**, chính thức từ **Java 21 (JEP 441)**, mở rộng cơ chế này: nhãn `case` có thể kiểm tra **kiểu và cấu trúc** của giá trị tại runtime, đồng thời khai báo các **pattern variable** có kiểu rõ ràng.

Ví dụ tối giản:

```java
static void describe(Object value) {
    switch (value) {
        case null -> System.out.println("No value");
        case String text -> System.out.println("Text: " + text.toUpperCase());
        case Integer number -> System.out.println("Integer: " + number);
        default -> System.out.println("Another type");
    }
}
```

Khi nhận `"java"`, nhãn `case String text` khớp, Java tạo biến `text` có kiểu `String`, và in `Text: JAVA` **mà không cần cast**. Khi nhận `42`, nhánh `Integer number` chạy. `null` có nhánh riêng.

Trong đoạn này:

- `switch (value)` là **switch statement**: thực thi lệnh, không trực tiếp tạo ra một giá trị để gán hoặc `return`.
- `case String text` là **type pattern**: kiểm tra kiểu runtime và ràng buộc đối tượng vào biến `text` nếu khớp.
- `->` xác định một **switch rule**: khi rule được chọn, chạy đúng nhánh đó rồi rời khỏi `switch` theo luồng điều khiển bình thường, **không tự động fall through** sang nhánh kế tiếp.
- `default` xử lý các giá trị **không phải null** không khớp các nhánh trước. `null` không tự động khớp `default`.

Cú pháp pattern matching cho `instanceof` đã ổn định từ Java 16; **pattern matching trong `switch`** chỉ chính thức từ **Java 21**. Các ví dụ chạy độc lập bên dưới dùng JDK 21 trở lên, không cần bật preview.

## 2. Hai cú pháp `switch statement`: `->` và `:`

Java hỗ trợ hai cách tổ chức phần thân `switch`.

### 2.1. Switch rule dùng mũi tên `->` (nên ưu tiên)

```java
switch (value) {
    case String s -> System.out.println("Length = " + s.length());
    case Integer n -> System.out.println("Number = " + n);
    default -> System.out.println("Other");
}
```

Nhánh `String` chỉ chạy khi đối tượng khớp kiểu `String`; sau khi in xong, không thực thi nội dung của nhánh `Integer`. Vì vậy không cần `break` sau mỗi nhánh.

Phía bên phải `->` trong một **switch statement** có thể là:

1. **Statement expression** hợp lệ, ví dụ lời gọi `System.out.println(s)`, phép gán hoặc thao tác tăng biến;
2. **Block** `{ ... }` khi cần nhiều câu lệnh;
3. **`throw` statement**.

Ví dụ block:

```java
case String s -> {
    String normalized = s.trim();
    System.out.println("Normalized: " + normalized);
    System.out.println("Length: " + normalized.length());
}
```

Đây là **mảnh mã bên trong một switch**, không phải chương trình độc lập. Biến `s` khớp từ nhãn `case` dùng được trong toàn bộ block của chính rule ấy.

### 2.2. Switch-labeled statement group dùng dấu hai chấm `:`

```java
switch (value) {
    case String s:
        System.out.println("Text: " + s);
        break;
    case Integer n:
        System.out.println("Integer: " + n);
        break;
    default:
        System.out.println("Other");
}
```

Đây là cú pháp các **nhóm lệnh** theo nhãn `case`. Khác với `->`, nhóm dùng `:` có thể tiếp tục thực thi lệnh ở nhóm sau nếu không gặp lệnh kết thúc phù hợp (*fall-through*). Với **pattern variable**, Java áp dụng quy tắc để **không cho fall through vào một nhãn khai báo pattern variable chưa được khởi tạo**.

Cả hai dạng đều có thể dùng pattern matching từ Java 21, nhưng **không trộn switch rules `->` và các labeled statement groups `:` trong cùng switch block**.

### 2.3. Phân biệt switch statement và switch expression

**Switch statement** dùng để thực thi hành động:

```java
switch (value) {
    case String s -> System.out.println(s);
    default -> System.out.println("Other");
}
```

**Switch expression** tạo ra giá trị:

```java
String result = switch (value) {
    case String s -> "Text: " + s;
    case null -> "(null)";
    default -> "(other)";
};
System.out.println(result);
```

Ở switch expression, RHS có thể là một biểu thức tạo giá trị, hoặc block dùng `yield` để trả giá trị của toàn bộ switch expression. Ở switch statement, RHS là **lệnh**, không phải mọi biểu thức Java đều hợp lệ làm một câu lệnh. Ví dụ sau **không biên dịch** khi được đặt trong switch statement:

```java
// KHÔNG HỢP LỆ trong switch statement:
// case String s -> "Text: " + s;
```

Phép nối chuỗi `"Text: " + s` không phải một *statement expression*. Muốn dùng nó làm kết quả, hãy đặt trong switch expression hoặc truyền nó cho một lời gọi như `System.out.println(...)`.

**Không dùng `yield` để “trả kết quả” từ switch statement**: đây là nhiệm vụ của switch expression. Trong switch statement, có thể gán vào biến bên ngoài, gọi phương thức, `return` khỏi phương thức bao quanh, hoặc `throw` ngoại lệ.

## 3. Type patterns: xử lý các kiểu runtime khác nhau

Một `switch` có selector kiểu `Object` có thể phân nhánh theo kiểu thực của giá trị:

```java
static void printKind(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case String s -> System.out.println("String length: " + s.length());
        case Integer n -> System.out.println("Integer: " + n);
        case Number n -> System.out.println("Number: " + n.doubleValue());
        default -> System.out.println("Other");
    }
}
```

Ví dụ `new Integer` không cần dùng trực tiếp; nếu gọi `printKind(7)`, Java *autobox* đối số thành `Integer`. Nhánh `Integer n` khớp. Nếu gọi `printKind(2.5)`, đối số được boxing thành `Double`; nó không khớp `Integer` nhưng khớp `Number`.

Các pattern variables `s`, `n` có **kiểu tĩnh đúng kiểu pattern**, nên có thể gọi trực tiếp `s.length()` hoặc `n.doubleValue()`. Biến `n` ở hai nhánh `Integer` và `Number` là **hai khai báo độc lập**, không phải một biến được gán chung.

### 3.1. Thứ tự lớp con/lớp cha rất quan trọng

`Integer` là lớp con của `Number`. Nếu đặt:

```java
// KHÔNG HỢP LỆ khi đặt trong cùng một switch:
case Number n -> System.out.println(n);
case Integer i -> System.out.println(i); // Bị nhánh Number che hoàn toàn.
```

`case Number n` đã khớp mọi giá trị thuộc `Integer`; nhãn `case Integer i` ở sau không còn cơ hội được chọn, nên Java báo **dominated case label** khi biên dịch.

Thứ tự hợp lệ:

```java
case Integer i -> System.out.println("Integer " + i);
case Number n -> System.out.println("Other Number " + n);
```

Đây là **hai mảnh case label bên trong một switch**, không phải chương trình độc lập. Tương tự, `case CharSequence cs` phải đứng **sau** `case String s` nếu muốn xử lý `String` chuyên biệt, vì `String` triển khai `CharSequence`.

### 3.2. Generic và kiểu mảng

Có thể kiểm tra một generic container ở mức **reifiable type**:

```java
case java.util.List<?> items ->
        System.out.println("List size = " + items.size());
case int[] numbers ->
        System.out.println("Array size = " + numbers.length);
```

`List<?>` chỉ cho biết đối tượng là `List`, không xác nhận tất cả phần tử đều là `String` hoặc kiểu khác. Nếu cần, duyệt từng phần tử và kiểm tra `item instanceof String text`. Với selector kiểu `Object`, không thể thay `List<?>` bằng `List<String>` rồi kỳ vọng JVM kiểm tra mọi đối số generic: Java generics dùng *type erasure*.

Mảng `int[]` có kiểu mảng xác định ở runtime, nên có thể dùng type pattern cho mảng đó.

## 4. `when` guard: chọn nhánh theo điều kiện bổ sung

Một **guarded case label** có cú pháp:

```java
case String text when text.isBlank() -> System.out.println("Blank");
```

Phép thử thực hiện theo thứ tự:

1. Java kiểm tra selector có khớp `String text` hay không;
2. Nếu khớp, biến `text` được khởi tạo với kiểu `String`;
3. Java mới đánh giá biểu thức boolean sau `when`;
4. Nếu guard trả `true`, thực thi RHS; nếu sai, tiếp tục thử các nhãn phù hợp tiếp theo.

Nhờ đó biến `text` dùng được **ngay trong `when`**:

```java
switch (value) {
    case null -> System.out.println("null");
    case String s when s.isBlank() ->
            System.out.println("Blank string");
    case String s when s.length() >= 5 ->
            System.out.println("Long text: " + s);
    case String s ->
            System.out.println("Short text: " + s);
    default -> System.out.println("Not text");
}
```

Chú ý **thứ tự**: rule `case String s` không guard phải **sau** các nhánh `String` có guard. Nếu đặt `case String s` ở trên, nó khớp toàn bộ `String` và che các nhánh đặc biệt phía dưới.

Có thể khai báo cùng tên `s` ở nhiều rule bởi **mỗi rule có phạm vi pattern variable riêng**. Java không “tái sử dụng” biến `s` đã khai báo trong rule trước.

Dùng `when` khi điều kiện bổ sung là một phần của **tiêu chí chọn case**, chẳng hạn chuỗi trắng, tuổi dương hoặc một record có giá trị đặc biệt. Dùng `if` bên trong RHS khi chỉ muốn rẽ nhánh **sau khi case đã được chọn**.

**Lưu ý:** Guard được đánh giá sau khi pattern khớp. Nó có thể gọi phương thức của pattern variable, nhưng nếu bản thân guard ném ngoại lệ thì ngoại lệ không có nghĩa là “guard sai”; câu lệnh switch sẽ hoàn tất đột ngột theo ngoại lệ ấy.

## 5. `null`: không tự khớp `default` hoặc type pattern

Đây là quy tắc quan trọng trong Java 21:

```java
static void showNull(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case String s -> System.out.println(s);
        default -> System.out.println("Other");
    }
}
```

- Nếu `value == null`, nhánh `case null` được chọn.
- `case String s` **không khớp `null`**.
- Nếu không có nhãn xử lý `null` và selector là `null`, `switch` ném `NullPointerException` **kể cả khi có `default`**.
- Nếu không cần tách `null` và các kiểu không khớp, Java 21 cho phép nhãn đặc biệt `case null, default -> ...`.

Không viết:

```java
// KHÔNG BIÊN DỊCH:
// case null, String s -> System.out.println(s);
```

Java không cho kết hợp nhãn `null` với một type pattern như vậy. Hãy tách thành `case null` và `case String s`, hoặc dùng tổ hợp `case null, default` khi thực sự muốn chung xử lý cho `null` và mọi giá trị khác.

## 6. `switch statement` có pattern phải bao phủ đủ trường hợp

Theo **JLS 21 §14.11.2**, một **enhanced switch statement** phải *exhaustive* (bao phủ mọi giá trị thuộc các kiểu có thể xét).

Một switch statement được coi là enhanced khi:

- Selector có kiểu không thuộc các kiểu truyền thống `char`, `byte`, `short`, `int` (và các wrapper tương ứng), `String` hoặc `enum`; **hoặc**
- Có nhãn `case` là **pattern** hoặc `null`.

Vì vậy ví dụ này **không biên dịch** trên Java 21:

```java
static void incomplete(Object value) {
    switch (value) {
        case String s -> System.out.println(s);
        // LỖI: thiếu khả năng bao phủ các kiểu Object còn lại.
    }
}
```

Sửa đơn giản bằng:

```java
static void complete(Object value) {
    switch (value) {
        case String s -> System.out.println(s);
        default -> System.out.println("Other");
    }
}
```

`default` cung cấp nhánh còn thiếu cho các giá trị không `null`. Nếu giá trị thực sự là `null`, đoạn `complete(null)` vẫn ném `NullPointerException` do không có `case null`. **Exhaustiveness về kiểu không có nghĩa tự động xử lý `null`**.

### 6.1. Trường hợp không cần `default`: sealed hierarchy

Khi selector có kiểu `sealed`, trình biên dịch có thể biết tất cả subtype được phép và xác nhận đủ các nhánh:

```java
sealed interface Shape permits Circle, Square {}

record Circle(double radius) implements Shape {}

record Square(double side) implements Shape {}

static void printShape(Shape shape) {
    switch (shape) {
        case Circle c -> System.out.println("Circle: " + c.radius());
        case Square s -> System.out.println("Square: " + s.side());
    }
}
```

Đây là **mảnh mã minh họa**: đặt các khai báo vào một tệp Java hợp lệ với chỉ định truy cập phù hợp. `Circle` và `Square` là hai subtype được phép của `Shape`, nên switch statement được xem là bao phủ đủ các giá trị không `null` của selector `Shape`. Nếu `shape == null`, không có `case null` nên vẫn có `NullPointerException`.

Khác với enhanced switch statement, **switch statement truyền thống** chỉ dùng constant labels và các selector type cũ có thể không exhaustive vì lý do tương thích ngược. Đừng suy ra mọi switch statement của mọi phiên bản Java đều buộc có `default`.

## 7. Phạm vi (*scope*) của pattern variable

Phạm vi biến pattern không giống một biến cục bộ được khai báo ở đầu phương thức. Theo JLS 21, với một nhãn `case String s`, biến `s` có thể dùng tại:

- Biểu thức guard `when` **của chính nhãn `case` đó**.
- Biểu thức/lệnh, block, hoặc `throw` nằm **bên phải `->`** trong chính switch rule.
- Nhóm lệnh **được gắn với nhãn `case String s:`** nếu dùng cú pháp dấu hai chấm.

Nó **không** có mặt trong rule khác, trong `default`, hoặc sau toàn bộ switch chỉ vì đã được khai báo trong một nhánh.

Ví dụ:

```java
static void scopeExample(Object value) {
    switch (value) {
        case String text when !text.isEmpty() -> {
            System.out.println(text.toUpperCase()); // Hợp lệ.
        }
        case Integer number -> {
            System.out.println(number + 1);
            // System.out.println(text); // LỖI: text ngoài scope.
        }
        default -> {
            // System.out.println(number); // LỖI: number ngoài scope.
            System.out.println("Other");
        }
    }
    // System.out.println(text); // LỖI: ngoài switch.
}
```

Ở nhánh `Integer number`, `text` của nhánh String không sẵn có. `number` cũng không được dùng tại `default`. Không thể dùng biến pattern của một nhánh như nơi lưu trữ kết quả dùng chung sau switch.

Nếu cần một giá trị sử dụng **sau** switch statement, có thể:

- Khai báo một biến ngoài switch và gán trong các nhánh, bảo đảm được khởi tạo trước khi đọc;
- Hoặc dùng **switch expression** để tạo giá trị và gán vào biến kết quả.

Ví dụ:

```java
static String result(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "String(" + s.length() + ")";
        default -> "Other";
    };
}
```

`String s` chỉ dùng bên trong nhánh; phương thức trả kết quả, **không đưa `s` ra ngoài scope**.

## 8. `case ...:` và lỗi fall-through vào pattern chưa khởi tạo

Dấu `:` vốn cho phép một nhóm lệnh chạy tiếp xuống nhóm sau nếu thiếu `break`. Nhưng khi nhãn sau có biến pattern, một đường *fall through* có thể đi tới nhóm sau mà **không hề khớp nhãn sau**. Java phát hiện và từ chối tình huống này lúc biên dịch.

Ví dụ **không hợp lệ** (chỉ minh họa):

```java
switch (value) {
    case String s:
        System.out.println("String: " + s);
        // Không có break hay lệnh kết thúc ở đây.
    case Integer n: // LỖI: có thể fall through vào case Integer n.
        System.out.println("Integer: " + n);
        break;
    default:
        System.out.println("Other");
}
```

Nếu `value` là `String`, luồng chạy có thể đi tiếp sang nhánh `Integer n` mà `n` **chưa từng được khởi tạo**. Compiler vì thế không cho tình huống đó.

Cách sửa: chèn `break` ở nơi cần thiết, hoặc tốt hơn, dùng `->`:

```java
switch (value) {
    case String s -> System.out.println("String: " + s);
    case Integer n -> System.out.println("Integer: " + n);
    default -> System.out.println("Other");
}
```

Trong `switch` dùng `:` có pattern, **phạm vi của biến** chỉ ở nhóm tương ứng; đừng dựa vào fall-through để truyền biến sang nhánh khác. Khi `case` chỉ chứa hằng số truyền thống, Java vẫn có thể cho phép fall-through theo quy tắc cũ.

## 9. Chương trình Java 21 hoàn chỉnh: switch statement với rule và group

Lưu tệp đúng tên **`SwitchStatementPatternDemo.java`**:

```java
import java.util.List;

public class SwitchStatementPatternDemo {
    record Point(int x, int y) {}

    static void inspect(Object value) {
        switch (value) {
            case null -> System.out.println("NULL");

            case String s when s.isBlank() ->
                    System.out.println("BLANK TEXT");

            case String s when s.length() > 5 -> {
                System.out.println("LONG TEXT: " + s
                        + " (" + s.length() + ")");
            }

            case String s -> System.out.println("TEXT: " + s);

            case Integer n when n >= 0 ->
                    System.out.println("NONNEGATIVE INTEGER: " + n);

            case Integer n -> System.out.println("NEGATIVE INTEGER: " + n);

            case Number n -> System.out.println("OTHER NUMBER: " + n);

            case Point(int x, int y) when x == y ->
                    System.out.println("DIAGONAL POINT: " + x);

            case Point(int x, int y) ->
                    System.out.println("POINT: " + x + "," + y);

            case List<?> items -> {
                int strings = 0;
                for (Object item : items) {
                    if (item instanceof String text) {
                        strings++;
                    }
                }
                System.out.println("LIST: " + items.size()
                        + " items, " + strings + " strings");
            }

            default -> System.out.println(
                    "OTHER: " + value.getClass().getSimpleName());
        }
    }

    static void inspectColon(Object value) {
        switch (value) {
            case String s:
                System.out.println("COLON STRING: " + s.toUpperCase());
                break;
            case Integer n:
                System.out.println("COLON INTEGER: " + n);
                break;
            case null:
                System.out.println("COLON NULL");
                break;
            default:
                System.out.println("COLON OTHER");
        }
    }

    public static void main(String[] args) {
        inspect(null);
        inspect("  ");
        inspect("pattern");
        inspect("Java");
        inspect(0);
        inspect(-2);
        inspect(2.5);
        inspect(new Point(3, 3));
        inspect(new Point(2, 5));
        inspect(List.of("A", 5, "B"));
        inspect(true);

        inspectColon("java");
        inspectColon(7);
        inspectColon(null);
        inspectColon(false);
    }
}
```

Chạy với **JDK 21 trở lên**, không cần tham số preview:

```bash
javac SwitchStatementPatternDemo.java
java SwitchStatementPatternDemo
```

**Standard output:**

```text
NULL
BLANK TEXT
LONG TEXT: pattern (7)
TEXT: Java
NONNEGATIVE INTEGER: 0
NEGATIVE INTEGER: -2
OTHER NUMBER: 2.5
DIAGONAL POINT: 3
POINT: 2,5
LIST: 3 items, 2 strings
OTHER: Boolean
COLON STRING: JAVA
COLON INTEGER: 7
COLON NULL
COLON OTHER
```

**Giải thích theo thứ tự thực thi:**

1. `inspect(null)` chọn `case null`. Không ném `NullPointerException` vì đã xử lý riêng.
2. `"  "` là `String` toàn dấu cách nên guard `isBlank()` đúng; in `BLANK TEXT`. `"pattern"` có độ dài 7, chọn guard `length() > 5`, còn `"Java"` đi vào `case String s` tổng quát.
3. `0` và `-2` đều được boxing thành `Integer`; guard `n >= 0` phân biệt không âm và âm. `2.5` là `Double`, khớp `Number n` nên in `OTHER NUMBER: 2.5`.
4. `Point` là `record` có hai thành phần `x` và `y`. **Record patterns** ở Java 21 phân rã hai thành phần thành biến pattern `int x`, `int y`. `Point(3,3)` khớp guard `x == y`; `Point(2,5)` đi vào nhánh `Point` còn lại.
5. `List.of("A", 5, "B")` khớp `List<?> items`; danh sách có ba phần tử, trong đó hai phần tử khớp `instanceof String text`.
6. `true` được boxing thành `Boolean`, không khớp các pattern trước; `default` in `OTHER: Boolean`.
7. `inspectColon` dùng cách viết `case ...:` và đặt `break` để không fall through: lần lượt xử lý chuỗi `"java"`, số `7`, `null` và kiểu không thuộc hai nhóm trên.

**Chương trình cho thấy rõ:** pattern variable được sinh theo nhánh đã khớp; guard được kiểm tra sau pattern; arrow rule không fall through; `case null` là trường hợp đặc biệt; và một switch statement có thể sử dụng cả type patterns lẫn record patterns.

## 10. Bảng so sánh nhanh

| Tình huống | Quy tắc trong Java 21 |
| --- | --- |
| `case String s -> ...` | Kiểm tra kiểu `String`, khai báo `s` cho rule |
| `case String s when ... -> ...` | Đánh giá guard sau khi `String s` khớp; `s` dùng được trong guard |
| `case Point(int x, int y) -> ...` | Deconstruct record và khai báo biến `x`, `y` |
| `case List<?> list -> ...` | Khớp `List`, không tự xác nhận kiểu từng phần tử |
| Nhiều `case` có chung tên `s` | Hợp lệ nếu là các khai báo pattern độc lập trong những rule riêng |
| `->` trong switch statement | Không fall through; RHS phải là statement expression, block hoặc `throw` |
| `:` trong switch statement | Có thể fall through, nhưng không được fall through **vào** pattern variable chưa khởi tạo |
| `case null -> ...` | Bắt `null` rõ ràng; nếu thiếu thì selector `null` ném `NullPointerException` |
| `default` | Bắt các giá trị không được nhãn trước chọn; không tự thay `case null` |
| Enhanced switch statement | Phải exhaustive; dùng `default` khi các patterns chưa bao phủ hết |
| `case Number n` trước `case Integer i` | `Integer` bị che (*dominated*) nên không hợp lệ |
| Pattern variable sau `switch` | Không có phạm vi ngoài nhánh đã khai báo |
| Switch expression | Sinh giá trị; block dùng `yield` để tạo kết quả, khác switch statement |

## 11. Lỗi thường gặp

### 11.1. Dùng pattern matching cho switch với JDK 17 mà không bật preview

`case String s -> ...` trong `switch` là tính năng ổn định từ Java 21. JDK 17 không hỗ trợ nó như tính năng mặc định. **Khuyến nghị dùng JDK 21+** cho mã mới theo bài này; đừng nhầm với pattern matching cho `instanceof` đã ổn định trên Java 17.

### 11.2. Nhầm `default` sẽ xử lý luôn `null`

Dù `default` có mặt, selector `null` vẫn ném `NullPointerException` nếu không có `case null` (hoặc nhãn kết hợp hợp lệ `case null, default`). Khi API cho phép `null`, hãy biểu diễn rõ chính sách null.

### 11.3. Đặt lớp cha trước lớp con

`case Number n` đặt trước `case Integer i` có thể che toàn bộ nhánh thứ hai. Cũng vậy, nhánh `String s` không guard phải sau các nhánh `String` có guard nếu chúng cần chạy.

### 11.4. Truy cập biến pattern của case khác

`String s` trong rule này không được tham chiếu ở `default` hoặc `case Integer i`. Nếu cần kết quả sau switch, gán vào biến ngoài hoặc dùng switch expression.

### 11.5. Thiếu `default` khi selector là `Object` và các pattern chưa bao phủ hết

Enhanced switch statement phải exhaustive. Nhiều nhánh chỉ bắt `String`, `Integer` mà thiếu `default` thường là lỗi biên dịch. Trường hợp selector sealed và mọi subtype đã được bao phủ là ngoại lệ hữu ích.

### 11.6. Thiếu `break` trong nhóm dấu `:`

Một nhóm `case String s:` có thể fall through vào nhãn pattern tiếp theo và gây lỗi biên dịch nếu biến nhánh sau chưa khởi tạo. Dùng `break` hoặc chuyển sang `->` để tránh lỗi.

### 11.7. Viết biểu thức thường ở RHS của switch statement

Không phải mọi biểu thức đều hợp lệ đứng độc lập làm statement. `"Text " + s` không phải statement expression. Dùng `System.out.println(...)`, phép gán, block hoặc switch expression nếu cần lấy giá trị.

### 11.8. Dùng `yield` khi không có switch expression

`yield` dùng cho block của **switch expression**; switch statement không sinh giá trị trực tiếp. Với switch statement, nên thực hiện hành động hoặc cập nhật trạng thái một cách rõ ràng.

### 11.9. Cho rằng `List<?>` có nghĩa các phần tử đều đúng một kiểu

`case List<?> items` kiểm tra kiểu container nhưng không xác minh generic type argument. Kiểm tra từng phần tử khi cần độ an toàn về kiểu ở runtime.

## 12. Bài tập thực hành

1. Viết `static void show(Object x)` dùng switch statement có `case null`, `case String s`, `case Integer n`, `default`. Thử lần lượt `null`, `"hi"`, `6`, `3.14`.
2. Thêm nhãn `case String s when s.isBlank()` **trước** `case String s` trong câu 1. Dự đoán nhánh với `""`, `" "`, `"Java"`; giải thích biến `s` được khởi tạo ở bước nào.
3. Bổ sung `case Number n` sau `case Integer n`. Đảo thứ tự hai nhánh và ghi nhận lỗi bị che; sửa lại theo quy tắc kiểu chuyên biệt trước kiểu tổng quát.
4. Viết một chương trình Java 21 dùng `case List<?> list -> { ... }` để in số phần tử là `String` và là `Number`. Không cast nguyên danh sách thành `List<String>`.
5. Viết switch statement dùng cú pháp `case ...:` với `String` và `Integer`. Cố tình bỏ `break` trước nhãn `Integer` có pattern variable, quan sát thông báo compiler; sau đó sửa bằng `break` hoặc `->`.
6. Tạo một `record Pair(int left, int right)` và hai `case`: một `when left == right`, một không guard. In cặp bằng hai biến pattern lấy từ record.
7. Thay `System.out.println` trong một switch statement bằng các biểu thức chuỗi ở RHS, giải thích vì sao không biên dịch; chuyển sang switch expression và gán kết quả cho một biến.
8. Viết một sealed interface có hai record triển khai, tạo switch statement exhaustive không dùng `default`. Thử bổ sung subtype thứ ba và quan sát yêu cầu cập nhật switch.

**Câu hỏi tự kiểm tra:** Bạn có phân biệt được *chọn case theo kiểu runtime*, *kiểm tra thêm bằng `when`*, *phạm vi biến pattern*, *dominance*, *fall-through* và *exhaustiveness* không? Sáu điểm này quyết định phần lớn tính đúng đắn của `switch statement` có pattern trong Java 21.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — Pattern Matching for `switch` Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21, §14.11 — The `switch` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21, §6.3.3 — Scope for Pattern Variables in `case` Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
