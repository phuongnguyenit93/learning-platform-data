# Definite matching và flow analysis trong Java Pattern Matching

Trong Java, **pattern variable** chỉ được sử dụng tại những vị trí mà trình biên dịch có thể chứng minh phép khớp pattern đã thành công. Quy tắc đó gọi là **definite matching**; việc suy luận từ điều kiện và luồng điều khiển để quyết định phạm vi của biến gọi là **flow analysis** hoặc **flow scoping**.

Ví dụ đơn giản nhất:

```java
Object input = "Java";

if (input instanceof String s) {
    System.out.println(s.length()); // 4: s chắc chắn đã được ràng buộc.
}
// Ở đây không được tự ý dùng s vì nhánh if có thể không chạy.
```

Khi `input` không phải `String`, pattern `String s` không khớp, nên `s` không được khởi tạo cho nhánh đó. Java ngăn lập trình viên dùng một biến pattern tại điểm mà không có bảo đảm nó đã được ràng buộc. Cơ chế này kiểm tra được ngay lúc **biên dịch**, giúp tránh ép kiểu không an toàn và tránh tham chiếu biến chưa có giá trị.

Bài dựa trên quy tắc trong **Java Language Specification (JLS) 21**, đặc biệt mục **`6.3 Scope of a Declaration**, **`14.30 Patterns** và **`16 Definite Assignment**. Type patterns trong `instanceof` là tính năng chuẩn từ Java 16 (JEP 394); record patterns là tính năng chuẩn từ Java 21 (JEP 440). Ví dụ đầy đủ dùng **Java 21+** và không cần `--enable-preview`.

## 1. Ba khái niệm cần phân biệt

### Pattern matching

**Pattern matching** là việc kiểm tra một giá trị có khớp với pattern hay không. Nếu thành công, các biến do pattern khai báo được khởi tạo.

```java
Object value = "hello";
boolean isText = value instanceof String s;
```

Ở đây `isText` là `true`, nhưng biến `s` không vì vậy mà có thể được dùng ở mọi vị trí sau câu lệnh. Trình biên dịch chỉ cho sử dụng `s` khi luồng điều khiển xác nhận rõ kết quả khớp. Do đó biểu thức `instanceof` thường được đưa trực tiếp vào `if`, `while` hoặc toán tử điều kiện.

### Definite matching

Một pattern variable được coi là **definitely matched** tại một điểm chương trình nếu **mọi đường đi có thể tới điểm đó** đều bảo đảm phép khớp đã thành công và biến đã nhận giá trị.

```java
if (value instanceof String s) {
    System.out.println(s.toUpperCase()); // Hợp lệ.
} else {
    System.out.println("Không phải String");
    // Không có bảo đảm cho s trong else.
}
```

Trình biên dịch phân tích cấu trúc biểu thức, nhánh `if`, phủ định, các lệnh kết thúc nhánh và một số cấu trúc khác. Nó không cần chạy chương trình để xác nhận `s` có tồn tại ở một nhánh cụ thể.

### Flow scoping và definite assignment

- **Flow scoping**: phạm vi tên `s` phụ thuộc vào vị trí chương trình mà phép khớp chắc chắn thành công; không đơn thuần là toàn bộ khối bao quanh khai báo.
- **Definite matching**: thuộc tính chứng minh pattern đã khớp ở một điểm trong luồng điều khiển, từ đó quyết định nơi biến pattern có thể được tham chiếu.
- **Definite assignment (DA)**: quy tắc chung của Java yêu cầu một biến cục bộ đã chắc chắn được gán giá trị trước khi đọc. Pattern variables có quy tắc đặc thù về *matching* và phạm vi, được thiết kế tương tự tinh thần DA.

Ví dụ DA thông thường:

```java
int count;
if (Math.random() > 0.5) {
    count = 1;
}
// System.out.println(count); // Lỗi: count might not have been initialized.
```

Đây là vấn đề **definite assignment** vì `count` được khai báo thông thường. Còn đọc `s` sau một `if (value instanceof String s)` độc lập thường là lỗi **không có biến pattern trong phạm vi tại điểm đó**. Hai quy tắc liên quan về phân tích luồng nhưng không hoàn toàn đồng nghĩa.

## 2. Quy tắc cơ bản khi instanceof thành công hoặc thất bại

Với:

```java
Object obj = "abc";
if (obj instanceof String s) {
    System.out.println(s.length());
}
```

Biểu thức `obj instanceof String s` **giới thiệu** (*introduce*) biến `s` trên đường mà kết quả là `true`. JLS phân biệt:

- **Introduced when true:** khi toàn biểu thức đúng, pattern chắc chắn đã khớp, nên biến `s` có thể dùng ở những vị trí mà nhánh đúng cho phép.
- **Introduced when false:** có thể xảy ra với những biểu thức chứa phủ định `!`; khi toàn biểu thức sai thì pattern bên trong mới chắc chắn đã khớp.

`instanceof` đơn lẻ giới thiệu biến pattern **khi true**, không giới thiệu nó khi false. Đây là cơ sở cho những quy tắc kết hợp bên dưới.

**Không suy luận chỉ từ tên biến:** compiler kiểm tra các nhánh thực tế, không tin rằng vì ta viết `String s` ở một vị trí thì tất cả lệnh phía sau đều có `s`.

## 3. Toán tử &&: dùng biến ở vế phải khi vế trái khớp

`&&` tính giá trị theo cơ chế *short-circuit*: chỉ tính vế phải khi vế trái là `true`. Nếu vế trái giới thiệu pattern variable khi đúng, biến đó được **definitely matched tại vế phải**.

```java
Object input = "  Java  ";

if (input instanceof String s && !s.isBlank()) {
    System.out.println(s.trim()); // Java
}
```

Đường đi của compiler:

1. Kiểm tra `input instanceof String s`.
2. Nếu sai, bỏ qua `!s.isBlank()` và nhánh `if`; không có chỗ nào đọc `s` khi chưa khớp.
3. Nếu đúng, `s` đã nhận một `String` khác `null`, nên được phép dùng trong `!s.isBlank()`.
4. Nếu cả hai vế đúng, nhánh `if` chạy và `s` vẫn được dùng hợp lệ.

Có thể nối nhiều phép kiểm tra:

```java
if (input instanceof String s
        && s.length() >= 4
        && s.startsWith("J")) {
    System.out.println(s);
}
```

Lưu ý: `&&` có quy tắc *definite matching* riêng. Đừng suy ra rằng toán tử Boolean không short-circuit như `&` luôn cho phép đọc cùng một biến pattern ở vế phải.

## 4. Toán tử || và sự khác nhau giữa đúng/sai

Trái với `&&`, `||` chỉ đánh giá vế phải khi **vế trái sai**. Vì vậy, theo JLS, biến pattern được giới thiệu bởi vế trái **khi false** mới chắc chắn được khớp tại vế phải.

### Ví dụ không hợp lệ

```java
// ĐOẠN SAI — chỉ dùng để nhận diện lỗi compiler.
//
// if (input instanceof String s || s.isBlank()) {
//     System.out.println(s);
// }
```

Vế trái `input instanceof String s` có thể sai. Khi đó `||` mới kiểm tra `s.isBlank()`, nhưng `s` chưa được ràng buộc. Đây là lỗi ngay lúc biên dịch. Kể cả khi điều kiện tổng thể đúng, nó có thể đúng từ một nhánh không tạo `s`, nên không thể tự ý dùng `s` trong nhánh `if`.

### Cách dùng || hợp lệ với phủ định

```java
static String requireText(Object input) {
    if (!(input instanceof String s) || s.isBlank()) {
        return "missing text";
    }
    return "trimmed=" + s.trim();
}
```

Đây là mẫu quan trọng:

1. `!(input instanceof String s)` đúng khi giá trị **không** khớp `String`.
2. Nếu vế trái đúng, `||` bỏ qua `s.isBlank()` và nhánh `if` trả về ngay.
3. Nếu vế trái sai, `input instanceof String s` đã đúng, vì thế `s` được dùng an toàn ở vế phải.
4. Nếu điều kiện toàn `if` sai, nghĩa là `s` là một `String` hợp lệ **và không blank**. Vì nhánh `if` có `return`, khi chạy tiếp tới lệnh cuối `s` chắc chắn đã được khớp.

Kết quả: `requireText("  hello  ")` trả `trimmed=hello`, còn `requireText("  ")` và `requireText(null)` đều trả `missing text`.

**Quy tắc ghi nhớ:** với `a && b`, compiler cho dùng biến được giới thiệu bởi `a` *khi true* trong `b`; với `a || b`, compiler cho dùng biến được giới thiệu bởi `a` *khi false* trong `b`.

## 5. Toán tử ! đảo nhánh definite matching

Phủ định Boolean `!` đảo điều kiện “đúng” và “sai”:

```java
Object input = "Java";

if (!(input instanceof String s)) {
    System.out.println("Not text");
} else {
    System.out.println(s.length()); // 4
}
```

Biểu thức `input instanceof String s` giới thiệu `s` khi **true**. Sau khi phủ định bằng `!`, toàn biểu thức phủ định giới thiệu `s` khi **false**, vì chỉ lúc đó phép khớp bên trong mới chắc chắn thành công.

Do vậy:

- Nhánh `if` đúng của `!(...)`: **không** thể giả định `s` tồn tại.
- Nhánh `else` của `!(...)`: `s` được bảo đảm đã khớp.
- Phép phủ định kép `!!(input instanceof String s)` giữ hướng khớp như điều kiện ban đầu; tuy nhiên nên ưu tiên cú pháp rõ ràng hơn.

Quy tắc này là suy luận từ biểu thức, không phải đặc tính riêng của biến có tên `s`.

## 6. Early return và phạm vi sau if

Một trong những ứng dụng mạnh nhất là **guard clause**: loại bỏ trường hợp không hợp lệ từ đầu, sau đó dùng biến pattern cho phần còn lại của phương thức.

```java
static String describeString(Object input) {
    if (!(input instanceof String s)) {
        return "not a string";
    }
    return "length=" + s.length();
}
```

Tại câu lệnh `return "length=" + s.length();`, mọi đường đi còn tiếp tục đều phải đi qua trường hợp `!(...) == false`. Vì thế `s` chắc chắn đã khớp. JLS cho phép một `if` giới thiệu pattern variable vào các câu lệnh kế tiếp khi nhánh ngược lại **không thể hoàn thành bình thường** (*cannot complete normally*), chẳng hạn nhánh này kết thúc bằng `return` hoặc `throw`.

Có thể dùng `throw` thay cho `return`:

```java
static int lengthOrThrow(Object input) {
    if (!(input instanceof String s)) {
        throw new IllegalArgumentException("String required");
    }
    return s.length();
}
```

**So sánh với mẫu sai:**

```java
static void wrongIdea(Object input) {
    if (input instanceof String s) {
        System.out.println(s);
    }
    // System.out.println(s); // KHÔNG hợp lệ: input có thể không phải String.
}
```

Ở đây `if` có thể hoàn thành bình thường dù condition sai; compiler không thể bảo đảm `s` tại lệnh tiếp theo.

## 7. Toán tử điều kiện ? : và phạm vi biến

Trong biểu thức `condition ? whenTrue : whenFalse`, compiler cho phép đọc biến pattern trong nhánh tương ứng với giá trị của điều kiện:

```java
Object value = "JDK";
int length = value instanceof String s ? s.length() : 0;
System.out.println(length); // 3
```

Nhánh `s.length()` chỉ được đánh giá khi pattern `String s` khớp. Trái lại, nhánh `0` chạy khi không khớp.

Phủ định vẫn có hiệu lực:

```java
String result = !(value instanceof String s)
        ? "not text"
        : "length=" + s.length();
```

Phần sau dấu `:` ở ví dụ thứ hai chạy khi phủ định là sai, tức pattern đã khớp. Không thể tùy ý dùng `s` ở cả hai nhánh hoặc sau toàn biểu thức vì luồng chạy tới đó có thể chưa khớp.

## 8. Record patterns cũng tuân theo definite matching

Từ Java 21, `instanceof` có thể chứa **record pattern**, trong đó nhiều biến được khai báo cùng lúc.

```java
record Point(int x, int y) {}
Object value = new Point(2, 4);

if (value instanceof Point(var x, var y)
        && x >= 0 && y >= 0) {
    System.out.println(x + y); // 6
}
```

- `Point(var x, var y)` kiểm tra `value` là `Point` khác `null`, rồi lấy hai thành phần `int` vào `x`, `y`.
- Nếu record pattern khớp, **cả `x` và `y`** được ràng buộc và có phạm vi hợp lệ ở vế phải của `&&` và nhánh `if` đúng.
- Nếu `value` là kiểu khác hoặc `null`, pattern thất bại; không có đường chạy nào đọc `x`, `y`.
- Nếu pattern khớp nhưng `x < 0`, toàn điều kiện `if` vẫn sai do guard Boolean; không đồng nghĩa bản thân record pattern không khớp.

Kiểu `var` được suy ra tại lúc biên dịch từ định nghĩa record; `x`, `y` có kiểu `int`. Đây không phải dữ liệu động.

### Record pattern lồng nhau

```java
record Wrapper(Point point, String label) {}

Object value = new Wrapper(new Point(3, 3), "ok");
if (value instanceof Wrapper(Point(var x, var y), var label)
        && x == y) {
    System.out.println("diagonal=" + x + ", label=" + label);
}
```

Ở đây phép khớp thành công ràng buộc `x`, `y`, `label`. Vế phải `x == y` chỉ được đánh giá sau khi cả record pattern ngoài `Wrapper(...)` và record pattern con `Point(...)` khớp.

Nếu `Wrapper.point() == null`, phần `Point(var x, var y)` không khớp, toàn `instanceof` trả `false`. Điều này tránh gọi accessor `x()` trên một đối tượng `Point` không tồn tại.

**Tuy nhiên, `label` có thể là `null`**, vì `var label` ở vị trí component là pattern không điều kiện đối với kiểu `String` của thành phần. Definite matching bảo đảm biến `label` đã **được ràng buộc**, chứ không bảo đảm mọi giá trị tham chiếu đã tách đều khác `null`. Hãy kiểm tra `label != null` trước khi gọi `label.length()`.

## 9. Definite matching trong while và các vòng lặp

Flow analysis cũng áp dụng cho điều kiện `while`. Bên trong thân vòng lặp, nếu điều kiện khớp, biến pattern được dùng hợp lệ.

```java
Object value = "abcd";

while (value instanceof String s && s.length() > 3) {
    System.out.println(s.length()); // 4
    break;
}
```

`s` là `String` trong thân vòng lặp và ở vế phải `&&`. Vòng lặp có `break` để không lặp mãi khi `value` giữ nguyên; chương trình thực tế có thể thay đổi đầu vào sau mỗi lần lặp. Không được giả định `s` luôn tồn tại ngoài vòng lặp vì có thể vòng lặp chưa chạy lần nào.

Quy tắc JLS cũng phân tích một số dạng `for` và `do`, nhưng chi tiết phạm vi còn phụ thuộc cách điều kiện được đánh giá và cách thoát vòng lặp. Với người học, nên hiểu vững mẫu `while` trước và để compiler xác nhận những biến pattern nào có thể dùng sau khi vòng lặp kết thúc.

## 10. Trong switch, guard và case body

Pattern matching trong `switch` Java 21 cũng dựa trên definite matching. Khi một nhãn `case` khớp, các pattern variables trong nhãn được đảm bảo có giá trị tại **guard `when`** và phần thân nhánh đó.

```java
static String inspect(Object value) {
    return switch (value) {
        case null -> "switch=null";
        case Point(var x, var y) when x == y -> "same=" + x;
        case Point(var x, var y) -> "different=" + (x - y);
        default -> "switch=other";
    };
}
```

Nhánh đầu có `Point(var x, var y)` khớp rồi mới kiểm tra `x == y`. Nhánh tiếp theo có **một khai báo pattern variables mới** với cùng tên nhưng phạm vi là nhánh của chính nó. Mỗi case sử dụng biến của mình; không thể tự ý lấy `x`, `y` ở phần sau toàn `switch`.

Việc đặt nhánh có `when` trước nhánh `Point(...)` tổng quát cũng tránh để nhánh rộng che nhánh chuyên biệt (*dominance*). `case null` xử lý selector `null`; `default` không được coi là nhánh bắt `null` chung trong ví dụ này.

Mặc dù chủ đề ở đây tập trung vào *definite matching*, cần nhớ compiler còn kiểm tra độc lập các quy tắc khác của `switch`, như **exhaustiveness**, **dominance** và kiểu dữ liệu của các nhánh.

## 11. Bảng tóm tắt flow analysis

| Biểu thức hoặc cấu trúc | Khi nào biến `s` chắc chắn được khớp? | Nơi có thể dùng `s` |
| --- | --- | --- |
| `obj instanceof String s` | Khi biểu thức là `true` | Nhánh đúng của `if` |
| `obj instanceof String s && s.length() > 0` | Vế trái đúng | Vế phải `&&`, nhánh `if` đúng |
| `obj instanceof String s || other` | Không đảm bảo khi toàn biểu thức đúng | Không dùng `s` trong nhánh đúng chỉ dựa vào biểu thức này |
| `!(obj instanceof String s)` | Khi biểu thức phủ định là `false` | Nhánh `else` tương ứng |
| `!(obj instanceof String s) || s.isBlank()` | Khi vế trái phủ định sai | Vế phải `||`; sau guard có `return` nếu flow bảo đảm |
| `if (!(obj instanceof String s)) return;` | Khi luồng chạy tiếp sau `if` | Các câu lệnh tiếp theo trong phạm vi được JLS xác định |
| `obj instanceof String s ? s.length() : 0` | Khi điều kiện tam phân đúng | Nhánh `?` phía sau điều kiện |
| `while (obj instanceof String s && ...)` | Khi điều kiện vòng lặp đúng | Vế phải `&&` và thân vòng lặp |
| `case Point(var x, var y) when x == y -> ...` | Khi record pattern của case khớp | Guard và thân case tương ứng |

Bảng nói về việc **được phép tham chiếu biến pattern**. Nó không tự bảo đảm giá trị tham chiếu bên trong một record khác `null`, cũng không thay thế các kiểm tra kiểu hoặc kiểm tra cú pháp khác của Java.

## 12. Chương trình Java 21 hoàn chỉnh và stdout đã kiểm chứng

Lưu toàn bộ mã sau vào tệp **`DefiniteMatchingDemo.java`**:

```java
public class DefiniteMatchingDemo {
    record Point(int x, int y) {}
    record Wrapper(Point point, String label) {}

    static String describe(Object value) {
        if (value instanceof String s && !s.isBlank()) {
            return "text=" + s.trim();
        }
        if (value instanceof Point(var x, var y) && x >= 0 && y >= 0) {
            return "point=(" + x + "," + y + ")";
        }
        if (value instanceof Wrapper(Point(var x, var y), var label)
                && x == y) {
            return "diagonal=" + x + ", label=" + label;
        }
        return "other";
    }

    static String afterEarlyReturn(Object value) {
        if (!(value instanceof String s)) {
            return "not a string";
        }
        return "length=" + s.length();
    }

    static String orGuard(Object value) {
        if (!(value instanceof String s) || s.isBlank()) {
            return "missing text";
        }
        return "trimmed=" + s.trim();
    }

    static String ternary(Object value) {
        int length = value instanceof String s ? s.length() : 0;
        return "ternary length=" + length;
    }

    static String whileCheck(Object value) {
        while (value instanceof String s && s.length() > 3) {
            return "long text=" + s.length();
        }
        return "not long text";
    }

    static String caseCheck(Object value) {
        return switch (value) {
            case null -> "switch=null";
            case Point(var x, var y) when x == y -> "same=" + x;
            case Point(var x, var y) -> "different=" + (x - y);
            default -> "switch=other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java  "));
        System.out.println(describe(new Point(2, 4)));
        System.out.println(describe(new Point(-2, 4)));
        System.out.println(describe(new Wrapper(new Point(3, 3), "ok")));
        System.out.println(describe(new Wrapper(null, "missing")));
        System.out.println(afterEarlyReturn("abc"));
        System.out.println(afterEarlyReturn(123));
        System.out.println(orGuard("  "));
        System.out.println(orGuard("  hello  "));
        System.out.println(orGuard(null));
        System.out.println(ternary("JDK"));
        System.out.println(ternary(null));
        System.out.println(whileCheck("abcd"));
        System.out.println(whileCheck("abc"));
        System.out.println(caseCheck(new Point(4, 4)));
        System.out.println(caseCheck(new Point(4, 2)));
        System.out.println(caseCheck(null));
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**:

```bash
javac --release 21 -encoding UTF-8 DefiniteMatchingDemo.java
java DefiniteMatchingDemo
```

**Đầu ra chính xác:**

```text
text=Java
point=(2,4)
other
diagonal=3, label=ok
other
length=3
not a string
missing text
trimmed=hello
missing text
ternary length=3
ternary length=0
long text=4
not long text
same=4
different=2
switch=null
```

Giải thích những điểm chính:

1. `describe("  Java  ")` dùng `String s` và điều kiện `!s.isBlank()`, sau đó cắt khoảng trắng thành `text=Java`.
2. `Point(2,4)` khớp record pattern và điều kiện hai tọa độ không âm. `Point(-2,4)` khớp record pattern nhưng bị loại bởi điều kiện `x >= 0`, do đó trả `other`.
3. `Wrapper(Point(3,3),"ok")` khớp cả record ngoài và record con, nên có `x=3`, `y=3` và `label="ok"`. `Wrapper(null,"missing")` không khớp record pattern `Point(...)`.
4. `afterEarlyReturn` minh họa phạm vi `s` kéo dài sau guard phủ định kết thúc bằng `return`.
5. `orGuard` minh họa phép `||` với phủ định: chỉ dùng `s` ở các điểm chắc chắn đã khớp.
6. `ternary` minh họa `s` được dùng trong nhánh `?` khi điều kiện đúng.
7. `whileCheck` dùng `s` trong thân `while` mà không phải ép kiểu.
8. `caseCheck` minh họa biến record pattern được dùng trong guard `when` và nhánh `switch`; selector `null` đi vào `case null`.

Mã đã được kiểm tra bằng `javac --release 21` và `java`, kết quả chạy gồm đúng 17 dòng như trên.

## 13. Lỗi phổ biến khi học definite matching

1. **Nhầm “có khai báo” với “được phép dùng”.** Việc xuất hiện `String s` không đồng nghĩa `s` có thể dùng ở mọi vị trí dưới nó. Xem mọi luồng có thể đến điểm đọc biến.
2. **Đọc `s` trong vế phải của `||` ngay sau `obj instanceof String s`.** Vế phải chạy khi pattern trước đó sai; compiler phải từ chối.
3. **Đọc `s` trong vế phải của `&&` sau phủ định `!(obj instanceof String s)`.** Khi phủ định đúng, pattern gốc không khớp; không có `s` để dùng.
4. **Cho rằng nhánh đúng của biểu thức phủ định có biến.** Với `if (!(obj instanceof String s))`, nhánh `else` mới là nơi pattern chắc chắn đã thành công.
5. **Dùng biến ngoài `if` không có guard thoát sớm.** Nếu trường hợp không khớp vẫn có thể chạy tiếp, compiler không thể bảo đảm biến đã được ràng buộc.
6. **Cho rằng các thành phần record luôn khác null khi match.** `Wrapper(Point(var x,var y),var label)` bảo đảm `Point` con tồn tại, nhưng `label` vẫn có thể bằng `null`.
7. **Nhầm record pattern với type pattern.** `Point p` ràng buộc cả record; `Point(var x,var y)` ràng buộc các thành phần. Cả hai đều tuân theo flow scoping.
8. **Đặt hai khai báo biến pattern trùng tên trong một biểu thức kết hợp.** Ví dụ `(a instanceof String s) && (b instanceof String s)` vi phạm quy tắc tên trùng của JLS; đặt tên riêng cho hai biến.
9. **Nghĩ rằng điều kiện runtime đã “rõ ràng” nên compiler phải chấp nhận.** Compiler suy luận theo quy tắc ngôn ngữ tĩnh; nó không chạy toàn bộ chương trình để đoán kết quả tùy ý.
10. **Lẫn definite matching với việc kiểm tra `null`.** Pattern variable đã được ràng buộc vẫn có thể giữ giá trị thành phần tham chiếu `null`; cần kiểm tra trước khi dereference.
11. **Dùng sai phiên bản Java.** Type pattern cho `instanceof` chuẩn từ Java 16, nhưng record pattern trong chương trình mẫu yêu cầu Java 21+.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao mã này biên dịch được?

```java
if (obj instanceof String s && s.length() > 3) {
    System.out.println(s);
}
```

*Đáp án:* Vế phải của `&&` chỉ chạy khi vế trái đúng. Vì vậy `s` definitely matched trong `s.length()` và trong nhánh `if` đúng.

**Câu 2.** Vì sao mã sau sai?

```java
// if (obj instanceof String s || s.isEmpty()) {
//     System.out.println(s);
// }
```

*Đáp án:* Vế phải của `||` chỉ được đánh giá khi `obj instanceof String s` là `false`. Khi đó `s` không được ràng buộc, nên compiler từ chối.

**Câu 3.** Biến `s` có thể dùng sau lệnh sau không?

```java
if (!(obj instanceof String s)) {
    throw new IllegalArgumentException();
}
System.out.println(s.length());
```

*Đáp án:* Có. Nhánh không khớp ném exception và không thể hoàn thành bình thường; tất cả đường chạy còn tiếp tục đều có `s` đã khớp.

**Câu 4.** Record `Wrapper` chứa `Point` là `null`, thì `value instanceof Wrapper(Point(var x, var y), var label)` có thể khớp không?

*Đáp án:* Không. Record pattern con `Point(...)` không khớp `null`; do đó `x`, `y`, `label` của toàn pattern không nằm trong phạm vi của nhánh thành công.

**Câu 5.** Trong `case Point(var x,var y) when x == y -> ...`, vì sao `x` được dùng ở `when`?

*Đáp án:* Guard `when` được xét sau khi pattern của case đã khớp, nên compiler xác nhận `x` và `y` được ràng buộc.

**Tài liệu chính thức:** [JLS 21, `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3), [JLS 21, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30), [JLS 21, `16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se21/html/jls-16.html), [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
