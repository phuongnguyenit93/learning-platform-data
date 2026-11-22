# Pattern trong if statement (Java 21+)

Trong Java, câu lệnh `if` không chỉ kiểm tra biểu thức Boolean thông thường. Ta có thể đặt một **pattern** trong phép kiểm tra `instanceof` để vừa xác nhận hình dạng/kiểu dữ liệu, vừa tạo các biến đã được ràng buộc kiểu. Nhờ vậy, nhánh `if` có thể làm việc với đối tượng hoặc thành phần của record mà không phải ép kiểu thủ công.

**Phạm vi phiên bản:** type pattern với `instanceof` là tính năng chuẩn từ **Java 16** (JEP 394). **Record pattern** dùng với `instanceof` được chuẩn hóa trong **Java 21** (JEP 440). Các ví dụ chương trình đầy đủ của bài được biên dịch bằng `javac --release 21`, không cần `--enable-preview`.

## 1. Vì sao cần pattern trong if?

Giả sử dữ liệu đầu vào có kiểu `Object` nhưng thực tế có thể chứa `String`, `Integer` hoặc một đối tượng khác. Trước Java 16, cách thường thấy là kiểm tra kiểu rồi ép kiểu:

```java
Object input = "Java";

if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.length()); // 4
}
```

Với **type pattern**, phép kiểm tra và khai báo biến gộp trong một biểu thức:

```java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Trong `input instanceof String text`, phần `String text` là **type pattern**. Nếu `input` có kiểu thực tế phù hợp với `String` và khác `null`, điều kiện đúng; biến `text` có kiểu tĩnh `String` và được sử dụng an toàn trong nhánh đúng. Không cần viết lại ép kiểu `(String) input`.

Dạng thường gặp:

```text
if (expression instanceof Type variable) {
    // variable dùng được khi pattern đã khớp.
}
```

Đây vẫn là câu lệnh `if` bình thường: điều kiện cần có kiểu `boolean`. Pattern xuất hiện bên trong **biểu thức `instanceof`**, không đứng độc lập thay cho điều kiện.

## 2. Type pattern trong nhánh if / else if

Ta có thể xử lý nhiều kiểu dữ liệu khác nhau theo thứ tự:

```java
static String label(Object input) {
    if (input instanceof String s) {
        return "Chuỗi dài " + s.length();
    } else if (input instanceof Integer n) {
        return "Số nguyên " + n;
    } else {
        return "Kiểu khác";
    }
}
```

Đây là **một phương thức minh họa** và cần đặt trong một lớp Java. Với `label("abc")` kết quả là `Chuỗi dài 3`; với `label(10)` là `Số nguyên 10`; với `label(null)` là `Kiểu khác`.

Điểm cần nhớ:

- Chỉ nhánh có điều kiện đúng được thực hiện. `s` thuộc phạm vi mà phép khớp `String` đã thành công; `n` thuộc phạm vi khớp `Integer`.
- `if`/`else if` được xét lần lượt. Các nhánh sau không được chạy nếu một nhánh trước đã chọn.
- `null instanceof String s` và `null instanceof Integer n` đều là `false`; không xảy ra việc gán `null` cho biến type pattern ngoài cùng.
- Dùng kiểu phù hợp với bài toán; khi đối tượng đã có kiểu cụ thể, không nhất thiết phải dùng pattern thay cho việc gọi phương thức trực tiếp.

## 3. Flow scoping: phạm vi biến dựa trên kết quả khớp

Khác một số khai báo biến thông thường, phạm vi của **pattern variable** được xác định bằng *flow scoping*: compiler phân tích luồng điều khiển để biết ở vị trí nào pattern chắc chắn đã khớp (*definitely matched*).

```java
Object input = "Hello";

if (input instanceof String s) {
    System.out.println(s.toUpperCase()); // HELLO
} else {
    System.out.println("Not a String");
}

// Không thể tùy ý dùng s tại đây: compiler không bảo đảm đã khớp.
```

Với điều kiện không phủ định `input instanceof String s`, `s` chắc chắn tồn tại bên trong nhánh `if` đúng; nhánh `else` không được bảo đảm có `s`.

### Kết hợp với toán tử &&

`&&` thực hiện **short-circuit** từ trái sang phải. Nhờ vậy, có thể dùng biến vừa được ràng buộc ở vế phải:

```java
Object input = "  Java  ";

if (input instanceof String s && !s.isBlank()) {
    System.out.println(s.trim()); // Java
}
```

Khi vế phải `!s.isBlank()` được đánh giá, vế trái đã đúng, nghĩa là `s` có kiểu `String` và khác `null`. Có thể kết hợp nhiều phép kiểm tra bổ sung:

```java
if (input instanceof String s && s.length() >= 3 && s.startsWith("J")) {
    System.out.println("Chuỗi bắt đầu bằng J");
}
```

Lưu ý: Java không có cú pháp `if (input instanceof String s when ...)`. **`when` là guard dùng với nhánh `case` trong `switch` có pattern**; ở `if`, hãy sử dụng các toán tử Boolean như `&&`.

### Tại sao phải cẩn trọng với ||

Xét ý định “cho phép String hoặc một điều kiện khác”:

```java
// Ví dụ SAI nếu cần dùng s trong nhánh đúng:
// if (input instanceof String s || allowOther) {
//     System.out.println(s.length()); // Không chắc s đã khớp!
// }
```

`||` có thể đúng nhờ vế phải khi pattern bên trái **không** khớp. Vì vậy, không thể giả định `s` luôn có giá trị trong nhánh `if` này. Đây là khác biệt quan trọng giữa `&&` và `||` khi sử dụng pattern variables. Hãy tách điều kiện hoặc thiết kế nhánh kiểm tra riêng nếu cần sử dụng `s`.

## 4. Phủ định !, nhánh else và early return

Khi kiểm tra phủ định, ý nghĩa của phạm vi biến thay đổi:

```java
Object input = "Hello";

if (!(input instanceof String s)) {
    System.out.println("Not a String");
} else {
    System.out.println(s.length()); // 5
}
```

Biểu thức `!(input instanceof String s)` đúng khi pattern không khớp. Bởi vậy `s` chỉ được bảo đảm trong nhánh `else`, nơi điều kiện phủ định là sai, tức pattern ban đầu đã khớp.

Một cách viết rất hữu ích là **early return** (thoát sớm):

```java
static String firstCharacter(Object input) {
    if (!(input instanceof String s)) {
        return "Không phải chuỗi";
    }
    if (s.isEmpty()) {
        return "Chuỗi rỗng";
    }
    return s.substring(0, 1);
}
```

Khi đã đi qua `if` đầu tiên mà chưa `return`, compiler biết `input` nhất định đã khớp `String s`. Vì thế `s` có thể dùng ở phần còn lại của phương thức. Với `firstCharacter("Java")` kết quả là `J`, còn `firstCharacter(42)` là `Không phải chuỗi`.

**Không suy diễn phạm vi bằng mắt thường:** biến pattern được phép dùng ở đâu phụ thuộc vào cấu trúc điều kiện và các nhánh thực sự kết thúc. Một nhánh phủ định không thoát sớm thì không đảm bảo biến có thể dùng ngay sau `if`.

## 5. Record pattern trong if từ Java 21

Với record, `if` có thể kiểm tra kiểu record và **tách các thành phần** trực tiếp.

```java
record Point(int x, int y) {}
```

Nếu chỉ cần giữ cả đối tượng, dùng **type pattern**:

```java
Object input = new Point(2, 3);

if (input instanceof Point p) {
    System.out.println(p.x() + p.y()); // 5
}
```

Nếu cần dùng các thành phần ngay trong nhánh, dùng **record pattern**:

```java
Object input = new Point(2, 3);

if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
```

Ở đây:

- `Point(...)` là record pattern: nó khớp đối tượng `Point` khác `null` và tách hai thành phần theo thứ tự khai báo.
- `int x` và `int y` là component type patterns, tạo biến `x` và `y` tương ứng.
- Có thể dùng `Point(var x, var y)` để compiler tự suy ra hai biến đều có kiểu `int`. `var` không khiến kiểu trở nên động.
- Số component patterns phải bằng số thành phần trong record. `Point(int x)` không hợp lệ với `record Point(int x, int y)`.
- Việc deconstruct đọc thành phần của record; nó không thay đổi đối tượng `Point`.

Record pattern được đặt trong `instanceof` nên có thể kết hợp điều kiện bổ sung như type pattern:

```java
if (input instanceof Point(var x, var y) && x >= 0 && y >= 0) {
    System.out.println("Tọa độ không âm: " + x + ", " + y);
}
```

Nếu một trong hai tọa độ âm, pattern `Point(var x, var y)` vẫn **khớp** nhưng **toàn bộ điều kiện `if` sai** do điều kiện bổ sung. Phân biệt thất bại của *pattern* với thất bại của *toàn biểu thức Boolean* sẽ giúp viết `else if` chính xác.

## 6. Kết hợp if / else if với nhiều record patterns

Một record pattern có thể được dùng để phân loại trường hợp cụ thể, rồi nhánh khác xử lý phần còn lại:

```java
static String describePoint(Object value) {
    if (value instanceof Point(int x, int y) && x >= 0 && y >= 0) {
        return "Non-negative point: (" + x + "," + y + ")";
    } else if (value instanceof Point(var x, var y)) {
        return "Other point: (" + x + "," + y + ")";
    }
    return "Not a point";
}
```

`describePoint(new Point(2, 3))` trả `Non-negative point: (2,3)`, còn `describePoint(new Point(-2, 3))` trả `Other point: (-2,3)`. Trong nhánh đầu, các biến `x`, `y` thuộc pattern thứ nhất; trong nhánh `else if`, các biến tên `x`, `y` là ràng buộc của pattern thứ hai. Những phép ràng buộc này không được dùng ngoài phạm vi hợp lệ của từng nhánh.

Việc dùng record pattern cũng tránh đoạn ép kiểu và truy cập accessor lặp lại khi thực sự cần nhiều thành phần của record.

## 7. Pattern lồng nhau trong điều kiện if

Record có thể chứa một record khác:

```java
record Shipment(String code, Point destination) {}
```

Giả sử `Shipment` có mã hàng và một điểm đến. Ta có thể khớp và tách cấu trúc hai cấp ngay trong `if`:

```java
Object input = new Shipment("S1", new Point(7, 8));

if (input instanceof Shipment(var code, Point(var x, var y))) {
    System.out.println(code + " to (" + x + "," + y + ")");
    // S1 to (7,8)
}
```

Thứ tự kiểm tra là: đối tượng ngoài phải là `Shipment` khác `null`; thành phần `destination` phải là `Point` khác `null`; sau đó hai thành phần `x`, `y` được lấy ra.

Nếu `destination == null`, pattern `Point(var x, var y)` không khớp, nên `if` không chạy. Để xử lý riêng trường hợp thiếu điểm đến, hãy **dừng deconstruct** ở mức `var destination`:

```java
if (input instanceof Shipment(var code, var destination)
        && destination == null) {
    System.out.println(code + " missing destination");
}
```

Ở đây `var destination` nhận thành phần kiểu `Point`, kể cả khi thành phần đó là `null`. Record pattern ngoài vẫn phải khớp một đối tượng `Shipment` khác `null`.

## 8. Hiểu đúng null trong if có pattern

Có hai cấp `null` cần phân biệt:

| Giá trị đầu vào | Điều kiện kiểm tra | Kết quả |
| --- | --- | --- |
| `null` | `value instanceof String s` | `false` |
| `null` | `value instanceof Point p` | `false` |
| `null` | `value instanceof Point(var x, var y)` | `false` |
| `new Shipment("S1", null)` | `value instanceof Shipment(var c, Point(var x, var y))` | `false` |
| `new Shipment("S1", null)` | `value instanceof Shipment(var c, var destination)` | `true` |
| `new Box(null)` với `record Box(String label) {}` | `value instanceof Box(var label)` | `true`; `label == null` |

Lý do: type pattern hoặc record pattern ở cấp ngoài của phép `instanceof` không khớp đối tượng `null`. Tuy nhiên, một **component type pattern không điều kiện** đối với kiểu khai báo của thành phần record có thể nhận thành phần `null`; `var label` là ví dụ. Trường hợp `Box(var label)` khớp không đảm bảo `label` khác `null`.

Do đó, trong một nhánh thành công của `if`, hãy kiểm tra các giá trị tham chiếu tách được trước khi gọi phương thức:

```java
Object value = new Box(null);

if (value instanceof Box(var label)) {
    String printable = label == null ? "(missing)" : label.trim();
    System.out.println(printable); // (missing)
}
```

Đây là cú pháp Java 21 hợp lệ khi record `Box` được khai báo như trên. Java không tự đưa quy tắc “cấm null” vào constructor record thông thường; nếu nghiệp vụ yêu cầu, có thể kiểm tra bằng `Objects.requireNonNull` trong constructor.

## 9. Ví dụ Java hoàn chỉnh: if với type và record patterns

Lưu nội dung sau vào **`IfPatternDemo.java`**:

```java
public class IfPatternDemo {
    record Point(int x, int y) {}
    record Shipment(String code, Point destination) {}
    record Box(String label) {}

    static String describe(Object value) {
        if (value instanceof Point(int x, int y) && x >= 0 && y >= 0) {
            return "Non-negative point: (" + x + "," + y + ")";
        } else if (value instanceof Point(var x, var y)) {
            return "Other point: (" + x + "," + y + ")";
        }
        return "Not a point";
    }

    static String shipmentTarget(Object value) {
        if (value instanceof Shipment(var code, Point(var x, var y))) {
            return code + " to (" + x + "," + y + ")";
        }
        if (value instanceof Shipment(var code, var destination)
                && destination == null) {
            return code + " missing destination";
        }
        return "Not a shipment with usable destination";
    }

    static String afterGuard(Object value) {
        if (!(value instanceof Point p)) {
            return "Missing point";
        }
        return "Point x=" + p.x();
    }

    static String classify(Object value) {
        if (value instanceof String s && !s.isBlank()) {
            return "Text: " + s.trim();
        } else if (value instanceof Integer n && n > 0) {
            return "Positive number: " + n;
        }
        return "Other value";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(new Point(-2, 3)));
        System.out.println(describe("x"));
        System.out.println(shipmentTarget(
                new Shipment("S1", new Point(7, 8))));
        System.out.println(shipmentTarget(new Shipment("S2", null)));
        System.out.println(shipmentTarget(null));
        System.out.println(afterGuard(new Point(4, 5)));
        System.out.println(afterGuard(null));
        System.out.println(classify("  Java  "));
        System.out.println(classify(10));
        System.out.println(classify(0));
        Object boxed = new Box(null);
        if (boxed instanceof Box(var label)) {
            System.out.println("Label is null: " + (label == null));
        }
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**:

```bash
javac --release 21 -encoding UTF-8 IfPatternDemo.java
java IfPatternDemo
```

**Kết quả chuẩn (stdout):**

```text
Non-negative point: (2,3)
Other point: (-2,3)
Not a point
S1 to (7,8)
S2 missing destination
Not a shipment with usable destination
Point x=4
Missing point
Text: Java
Positive number: 10
Other value
Label is null: true
```

Giải thích:

1. `describe` dùng record pattern và `&&` để phân biệt điểm có tọa độ không âm, điểm còn lại và dữ liệu không phải `Point`.
2. `shipmentTarget` tách hai cấp record khi điểm đến tồn tại; khi điểm đến `null`, nhánh thứ nhất không khớp và nhánh `var destination` xử lý.
3. `afterGuard` thể hiện flow scoping với phủ định `!` và early return. Sau khi qua `if` đầu tiên, `p` luôn là một `Point` hợp lệ.
4. `classify` dùng hai type patterns (`String s` và `Integer n`) với điều kiện bổ sung. Giá trị `0` không vượt qua `n > 0` nên đi vào nhánh còn lại.
5. `Box(var label)` vẫn khớp khi thành phần `label` là `null`; chương trình chủ động kiểm tra nó.

Chương trình là một tệp Java độc lập (record được khai báo lồng trong lớp) và được kiểm chứng bằng `javac --release 21`. Phần stdout ở trên phản ánh đúng kết quả chạy.

## 10. Những lỗi thường gặp

1. **Đặt kiểu kiểm tra và ép kiểu thủ công lặp lại.** Nếu đang dùng `instanceof` chỉ để ép kiểu ngay trong nhánh thành công, cân nhắc `obj instanceof Type variable`.
2. **Dùng biến pattern sai phạm vi.** `s` sau `if (obj instanceof String s)` không mặc nhiên tồn tại ở phía sau `if` hay trong `else`.
3. **Sử dụng `||` như `&&`.** Điều kiện tổng thể đúng nhờ một nhánh khác không đảm bảo type pattern đã khớp. Đừng đọc biến pattern khi compiler không thể chứng minh điều đó.
4. **Nhầm phủ định với khớp thành công.** Khi điều kiện là `!(obj instanceof String s)`, biến `s` không có trong nhánh đúng của điều kiện phủ định; nhưng có thể dùng trong `else` hoặc sau guard kết thúc sớm.
5. **Dùng `when` trong `if`.** Java 21 dùng toán tử Boolean để ghép điều kiện `if`; `when` thuộc cú pháp case guard trong pattern matching `switch`.
6. **Nhầm record pattern với type pattern.** `Point p` lấy nguyên record; `Point(int x, int y)` tách thành phần. Chọn cách nào dễ hiểu và đúng nhu cầu.
7. **Sai số lượng, kiểu hoặc thứ tự component patterns.** `Point` có hai thành phần `int` nên pattern tách trực tiếp cũng phải khớp hai vị trí có kiểu tương thích.
8. **Cho rằng record pattern khớp record `null`.** `null instanceof Point(var x, var y)` là `false`. Mặt khác, thành phần tham chiếu tách bằng `var` vẫn có thể mang `null`.
9. **Gọi phương thức trên thành phần tham chiếu mà chưa kiểm tra.** Pattern đã khớp có thể mang biến `label == null`; `label.length()` vẫn có thể gây `NullPointerException`.
10. **Cố chạy record pattern trên JDK 17 như một tính năng ổn định.** Mã dùng `Point(var x, var y)` trong bài cần JDK 21+; một số bản JDK cũ chỉ có preview hoặc không hỗ trợ cú pháp này.
11. **Nhầm `instanceof` với câu lệnh pattern độc lập.** Viết `if (obj instanceof Point p)` hoặc `if (obj instanceof Point(var x, var y))`; không viết `if (Point p)`.

## 11. Bài tập tự kiểm tra

**Bài 1.** Với `Object value = "Hello";`, điều kiện `value instanceof String s && s.length() == 5` có đúng không? Có thể đọc `s` trong nhánh `if` không?

*Đáp án:* Đúng. Pattern `String s` khớp, `s.length()` bằng `5`; biến `s` có phạm vi hợp lệ trong nhánh đúng.

**Bài 2.** Với `Object value = new Point(-1, 4);`, điều kiện `value instanceof Point(var x, var y) && x >= 0` đúng hay sai?

*Đáp án:* **Sai** do `x >= 0` sai, mặc dù record pattern `Point(var x, var y)` tự nó khớp.

**Bài 3.** Với `Object value = new Shipment("S3", null);`, pattern `Shipment(var c, Point(var x, var y))` có khớp không? Có thể viết gì để xử lý điểm đến bị thiếu?

*Đáp án:* Không; record pattern `Point(...)` không khớp `null`. Dùng `Shipment(var c, var destination) && destination == null`.

**Bài 4.** Vì sao có thể dùng `p.x()` sau đoạn `if (!(value instanceof Point p)) return "Missing point";`?

*Đáp án:* Vì mọi nhánh không khớp đã kết thúc bằng `return`. Khi luồng chạy tiếp, compiler chứng minh `Point p` chắc chắn đã khớp.

**Bài 5.** `Box(var label)` có nhận một `Box` mà `label == null` không?

*Đáp án:* Có. Record `Box` bên ngoài khác `null`; `var label` là component pattern có thể nhận thành phần `null`. Cần tự kiểm tra `label` trước khi gọi phương thức.

**Tham khảo chính thức:** [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Java Language Specification 21 – `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
