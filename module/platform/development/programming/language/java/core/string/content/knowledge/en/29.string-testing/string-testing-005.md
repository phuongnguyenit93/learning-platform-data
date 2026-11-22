# Kiểm thử `==`, `equals`, `intern` và biểu thức hằng trong Java String

Hai biến `String` có thể **chứa cùng văn bản** nhưng **trỏ tới hai đối tượng khác nhau**. Ngược lại, nhiều biến có thể cùng trỏ tới một đối tượng nhờ quy tắc chia sẻ string literal và cơ chế `intern()`. Khi kiểm thử, cần phân biệt đúng **nội dung chuỗi**, **định danh đối tượng**, **biểu thức hằng lúc biên dịch** và **kết quả được tạo ở runtime**.

Ví dụ cốt lõi:

```java
String literal = "java";
String anotherLiteral = "java";
String fresh = new String("java");

System.out.println(literal == anotherLiteral); // true
System.out.println(literal == fresh);          // false
System.out.println(literal.equals(fresh));     // true
System.out.println(literal == fresh.intern());  // true
```

Cả bốn kết quả đều có lý do cụ thể. Một bộ kiểm thử tốt phải xác nhận **đúng điều mà API cam kết**, thay vì đoán kết quả `==` chỉ dựa trên việc văn bản giống nhau.

## 1. Bốn khái niệm cần phân biệt

| Cách kiểm tra | Thực chất kiểm tra | Nên dùng khi |
| --- | --- | --- |
| `a == b` | Hai biến tham chiếu có trỏ tới **cùng một đối tượng** (hoặc cùng `null`) không | Kiểm tra định danh hoặc quy tắc pooling một cách có chủ đích |
| `a.equals(b)` | `a` và `b` có **cùng nội dung** theo `String.equals` không | Hầu hết bài toán so sánh giá trị văn bản |
| `a.intern()` | Trả về chuỗi **canonical** đại diện cho nội dung của `a` | Khi thực sự cần chuẩn hóa tham chiếu chuỗi |
| Biểu thức hằng `"ab" + "cd"` | Kết quả được tính ở **compile time**; chuỗi tương ứng được intern như literal | Kiểm thử quy tắc hằng của ngôn ngữ |

Với `String`:

- `equals` so sánh chuỗi ký tự theo đúng thứ tự và giá trị (phân biệt chữ hoa/chữ thường); không dựa trên tham chiếu.
- `==` trên hai biến kiểu `String` so sánh tham chiếu; không đọc từng ký tự.
- `intern()` không thay đổi nội dung hay “biến đổi” đối tượng gốc; nó trả về một **tham chiếu** đến đại diện canonical có cùng nội dung.
- Không phải mọi chuỗi có nội dung giống literal đều **tự động** được intern khi được tạo ở runtime.

`String` là immutable, nhưng **immutable không có nghĩa mọi instance cùng nội dung đều là một instance**.

## 2. Tại sao hai string literal thường có `==` bằng `true`?

Theo Java Language Specification, string literal có cùng nội dung biểu diễn cùng một instance `String`. Vì vậy:

```java
String first = "coffee";
String second = "coffee";
System.out.println(first == second); // true
```

Đây là hành vi **được đặc tả**, phù hợp để viết một bài kiểm thử giải thích cơ chế literal.

Một biểu thức gồm các hằng `String`, toán tử `+` và các thành phần là *constant expression* cũng được tính ở **compile time**. Kết quả chuỗi của biểu thức hằng được intern:

```java
String word = "coffee";
String folded = "co" + "ffee";
System.out.println(word == folded); // true
```

Trình biên dịch có thể lưu literal `"coffee"` dùng chung trong class file; không cần tạo một đối tượng mới chỉ để ghép hai đoạn `"co"` và `"ffee"` khi chương trình chạy.

**Điểm quan trọng:** `==` bằng `true` ở đây không chứng minh rằng **mọi** phép nối chuỗi đều dùng chung đối tượng. Ta phải kiểm tra xem biểu thức có thật sự là **biểu thức hằng theo ngôn ngữ Java** hay không.

## 3. Biểu thức hằng, biến `final` và phép nối runtime

### Trường hợp A — tất cả phần của phép nối là hằng

```java
String a = "coffee";
String b = "co" + "ffee";

System.out.println(a == b); // true
```

`"co" + "ffee"` là biểu thức hằng kiểu `String`. Trình biên dịch gộp nội dung thành `"coffee"`; `b` dùng tham chiếu canonical.

### Trường hợp B — biến hằng `final String`

```java
final String PREFIX = "co";
String a = "coffee";
String b = PREFIX + "ffee";

System.out.println(a == b); // true
```

Một biến `final` kiểu nguyên thủy hoặc kiểu `String` được khởi tạo bằng **constant expression** là *constant variable*. `PREFIX` trong ví dụ là constant variable, vì vậy `PREFIX + "ffee"` vẫn là constant expression và có thể gộp khi biên dịch.

### Trường hợp C — biến không phải hằng

```java
String prefix = "co";
String a = "coffee";
String b = prefix + "ffee";

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

`prefix` không phải constant variable vì nó không khai báo `final`. Phép nối là thao tác runtime, tạo kết quả với cùng nội dung nhưng khác tham chiếu với literal. Trình biên dịch và JVM có thể chọn kỹ thuật nối chuỗi khác nhau, song **không nên viết chương trình dựa vào `==` để kiểm tra nội dung của phép nối runtime**.

### Trường hợp D — `final` nhưng giá trị khởi tạo không phải biểu thức hằng

```java
final String prefix = new String("co");
String a = "coffee";
String b = prefix + "ffee";

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

Từ khóa `final` chỉ cấm gán lại biến `prefix`. Nó **không khiến `new String("co")` trở thành compile-time constant**. Bởi vậy `prefix + "ffee"` vẫn được đánh giá ở runtime.

| Biểu thức tạo `b` | Là compile-time constant expression? | `"coffee" == b` |
| --- | --- | --- |
| `"co" + "ffee"` | Có | `true` |
| `final String p = "co"; b = p + "ffee";` | Có | `true` |
| `String p = "co"; b = p + "ffee";` | Không | `false` |
| `final String p = new String("co"); b = p + "ffee";` | Không | `false` |
| `new String("coffee")` | Không | `false` |
| `new StringBuilder().append("co").append("ffee").toString()` | Không | `false` |

Bảng này nói về những **đoạn mã cụ thể** có giá trị bằng `"coffee"` và cách tạo đối tượng được mô tả. Đối với dữ liệu thực tế, hãy xác nhận nội dung bằng `equals`.

## 4. `new String(...)` và `StringBuilder.toString()`: cùng nội dung, khác đối tượng

`new String("coffee")` biểu thị yêu cầu tạo một đối tượng `String` mới; dù nó nhận giá trị từ literal đã intern, kết quả vẫn là một instance riêng:

```java
String literal = "coffee";
String fresh = new String("coffee");

System.out.println(literal == fresh);      // false
System.out.println(literal.equals(fresh)); // true
```

Tương tự, chuyển nội dung từ một `StringBuilder` thành `String` cho kết quả văn bản hợp lệ; không nên giả định rằng chuỗi này được intern:

```java
String literal = "coffee";
String built = new StringBuilder()
        .append("co")
        .append("ffee")
        .toString();

System.out.println(literal == built);      // false
System.out.println(literal.equals(built)); // true
```

**Quy tắc kiểm thử:** nếu chức năng của hệ thống chỉ yêu cầu cùng văn bản, một test như `assertEquals("coffee", actual)` có giá trị; một test như `assertSame("coffee", actual)` có thể áp đặt thêm ràng buộc **về định danh đối tượng** mà chức năng không hề yêu cầu.

## 5. `intern()` bảo đảm điều gì?

`String.intern()` trả về tham chiếu đến **đối tượng chuỗi canonical** có nội dung bằng chuỗi được gọi. Nếu một chuỗi có nội dung tương đương đã ở trong bảng intern, tham chiếu tương ứng được trả về; nếu chưa có, cơ chế intern thiết lập một đại diện canonical theo hợp đồng của API.

Bảo đảm hữu ích nhất:

```java
String x = new String("coffee");
String y = new StringBuilder()
        .append("co")
        .append("ffee")
        .toString();

System.out.println(x == y);                 // false
System.out.println(x.equals(y));            // true
System.out.println(x.intern() == y.intern()); // true
```

Vì `x` và `y` có cùng nội dung, kết quả `intern()` của chúng là **cùng tham chiếu**. Với literal đã biết:

```java
String literal = "coffee";
String fresh = new String("coffee");

System.out.println(fresh == literal);          // false
System.out.println(fresh.intern() == literal); // true
System.out.println(fresh == literal);          // false
```

Lời gọi `fresh.intern()` **không làm biến `fresh` tự đổi sang tham chiếu canonical**. Nếu muốn sử dụng kết quả intern về sau, phải gán hoặc dùng trực tiếp tham chiếu trả về:

```java
String canonical = fresh.intern();
```

### Không kiểm tra chi tiết triển khai bằng `==`

Một số ví dụ ngoài thực tế dựa trên giả định “lần đầu gọi `intern()` trên một chuỗi tạo ở runtime sẽ luôn trả về chính instance đó”. Bảo đảm mà code ứng dụng nên dùng là **những chuỗi bằng nội dung sẽ có kết quả `intern()` trùng tham chiếu**; không xây dựng logic quanh chi tiết đối tượng nào được lưu trước hay thời điểm JVM khởi tạo pool.

Việc interning còn có chi phí quản lý tài nguyên. Không cần gọi `intern()` chỉ để so sánh nội dung: `equals` thường trực tiếp, dễ hiểu và đúng mục đích hơn.

## 6. Bài kiểm thử Java 17+ chạy độc lập

Tạo file `StringComparisonDemo.java`. Chương trình tự kiểm tra 16 điều kiện và **ném `AssertionError` khi bất kỳ điều kiện nào sai**; vì vậy nó có thể chạy như một test độc lập mà không cần JUnit hoặc bật JVM assertion.

```java
import java.util.Objects;

public class StringComparisonDemo {
    private static int checks;

    private static void check(
            String name, boolean actual, boolean expected) {
        if (actual != expected) {
            throw new AssertionError(name + " expected "
                    + expected + " but got " + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        String literal = "coffee";
        String repeated = "coffee";
        String folded = "co" + "ffee";

        final String constantPrefix = "co";
        String viaConstant = constantPrefix + "ffee";

        String variablePrefix = "co";
        String viaVariable = variablePrefix + "ffee";

        final String nonconstantPrefix = new String("co");
        String viaFinalObject = nonconstantPrefix + "ffee";

        String fresh = new String("coffee");
        String built = new StringBuilder()
                .append("co")
                .append("ffee")
                .toString();

        String nullable = null;

        check("repeated literals", literal == repeated, true);
        check("literal folding", literal == folded, true);
        check("constant variable folding", literal == viaConstant, true);
        check("runtime variable concatenation",
                literal == viaVariable, false);
        check("final reference is not always constant",
                literal == viaFinalObject, false);
        check("new String identity", literal == fresh, false);
        check("new String content", literal.equals(fresh), true);
        check("Objects.equals content",
                Objects.equals(literal, fresh), true);
        check("StringBuilder identity", literal == built, false);
        check("StringBuilder content", literal.equals(built), true);
        check("intern canonical result", literal == fresh.intern(), true);
        check("intern both strings",
                fresh.intern() == built.intern(), true);
        check("intern does not change fresh identity",
                literal == fresh, false);
        check("null-safe one null",
                Objects.equals(nullable, literal), false);
        check("null-safe two nulls",
                Objects.equals(nullable, null), true);
        check("non-null equals(null)",
                literal.equals(nullable), false);

        System.out.println("PASS: " + checks + " checks");
    }
}
```

Biên dịch và chạy:

```bash
javac StringComparisonDemo.java
java StringComparisonDemo
```

Kết quả chính xác:

```text
PASS: 16 checks
```

Đây là test tự kiểm tra hành vi thực, không chỉ in giá trị rồi yêu cầu người đọc tự so sánh. Mỗi lời gọi `check` có một kỳ vọng minh bạch; thất bại sẽ cho biết trường hợp kiểm thử nào sai. Chương trình **không dùng câu lệnh `assert` của Java**, vì `assert` bị tắt mặc định nếu không bật tùy chọn `-ea`.

Nếu muốn kiểm tra nhanh một trường hợp, có thể in biểu thức như ở các mục trước; khi tự động hóa, nên dùng điều kiện kiểm thử gây thất bại thật nếu kết quả khác kỳ vọng.

## 7. Viết kiểm thử bằng JUnit 5

Trong dự án đã có JUnit Jupiter, có thể dùng các assertion diễn đạt rõ mục đích:

- `assertEquals(expected, actual)`: kiểm tra **giá trị/nội dung** bằng logic `equals`.
- `assertSame(expected, actual)`: kiểm tra **cùng một tham chiếu**.
- `assertNotSame(unexpected, actual)`: kiểm tra **khác tham chiếu**.
- `assertTrue`, `assertFalse`: kiểm tra một điều kiện có mục đích rõ ràng.
- `assertNull` và `assertNotNull`: kiểm tra tham chiếu null.

Ví dụ file kiểm thử trong dự án dùng JUnit 5 (đoạn này **không chạy độc lập nếu chưa có dependency JUnit Jupiter**):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Objects;

class StringComparisonTest {

    @Test
    void literalAndConstantExpressionShareReference() {
        String literal = "coffee";
        final String constantPrefix = "co";

        assertSame(literal, "co" + "ffee");
        assertSame(literal, constantPrefix + "ffee");
    }

    @Test
    void runtimeStringHasSameContentButDifferentReference() {
        String literal = "coffee";
        String generated = new String("coffee");

        assertNotSame(literal, generated);
        assertEquals(literal, generated);
    }

    @Test
    void internReturnsCanonicalReference() {
        String literal = "coffee";
        String generated = new String("coffee");

        assertSame(literal, generated.intern());
        assertNotSame(literal, generated);
    }

    @Test
    void nullComparisonIsSafeWhenRequested() {
        String absent = null;
        String present = "coffee";

        assertFalse(Objects.equals(absent, present));
        assertTrue(Objects.equals(absent, null));
        assertFalse(present.equals(absent));
    }
}
```

Những assertion dùng `assertSame` trong ví dụ chỉ kiểm tra **hành vi được đặc tả**: literal/constant expression được intern và kết quả từ `intern()` có cùng tham chiếu canonical. Khi kiểm thử một hàm chỉ có hợp đồng “trả văn bản chính xác”, hãy dùng `assertEquals`.

**Tránh:** dùng `assertSame("OK", service.getStatus())` nếu service không hứa trả về instance interned; dù giá trị đúng, test có thể thất bại do một instance mới hoàn toàn hợp lệ.

## 8. Kiểm thử với `null`: `equals` không tự bảo vệ biến nhận lời gọi

`==` so sánh tham chiếu và không ném `NullPointerException` chỉ vì một hoặc cả hai toán hạng là `null`:

```java
String a = null;
String b = null;

System.out.println(a == b); // true
```

Nhưng gọi phương thức instance qua tham chiếu `null` sẽ gây lỗi:

```java
String value = null;

// value.equals("ready") sẽ ném NullPointerException.
boolean safe1 = "ready".equals(value);  // false
boolean safe2 = Objects.equals(value, "ready"); // false
```

`"ready".equals(value)` phù hợp khi vế trái là literal chắc chắn khác null. `Objects.equals(a, b)` phù hợp khi **cả hai biến đều có thể null**: hai null được coi là bằng nhau, một null và một giá trị khác null là không bằng.

### `equals` và `equalsIgnoreCase` không có cùng tiêu chí

`String.equals` phân biệt chữ hoa/thường:

```java
System.out.println("Java".equals("java"));           // false
System.out.println("Java".equalsIgnoreCase("java")); // true
```

Nếu yêu cầu là so sánh không phân biệt chữ hoa/thường, viết test trực tiếp cho hành vi đó. Không nên dùng `==` như một cách “tối ưu hóa” thay cho bất kỳ kiểu so sánh nội dung nào.

## 9. Các lỗi kiểm thử thường gặp

1. **Dùng `==` để kiểm tra đầu ra nghiệp vụ của một hàm xử lý chuỗi.** Kết quả có thể cùng nội dung nhưng là instance khác; dùng `equals` hoặc `assertEquals` nếu hợp đồng chỉ nói về văn bản.
2. **Cho rằng `final` luôn tạo constant expression.** `final String p = new String("co")` không phải constant variable; `p + "ffee"` vẫn tính ở runtime.
3. **Không phân biệt nối hằng và nối runtime.** `"co" + "ffee"` là biểu thức hằng; `String prefix = "co"; prefix + "ffee"` thì không.
4. **Cho rằng `new String(literal)` được intern tự động.** Constructor tạo đối tượng mới; nội dung vẫn có thể bằng literal, nhưng tham chiếu khác.
5. **Cho rằng gọi `intern()` làm thay đổi biến gốc.** Nó trả về tham chiếu; `fresh` vẫn trỏ tới instance ban đầu nếu không gán lại.
6. **Phụ thuộc vào “lần intern đầu tiên trả chính object này”.** Không nên viết test buộc JVM dùng một chiến lược intern cụ thể vượt quá hợp đồng canonical hóa.
7. **Quên `null` khi gọi `equals`.** `nullable.equals(...)` có thể ném exception; dùng literal ở vế trái hoặc `Objects.equals` khi phù hợp.
8. **Nhầm `assertEquals` với `assertSame` của JUnit.** Assertion trước kiểm tra nội dung; assertion sau kiểm tra tham chiếu.
9. **Dùng `assert` rồi chạy Java không có `-ea`.** Một chương trình in “test passed” dù `assert` bị tắt là kết quả gây hiểu nhầm; JUnit hoặc bộ kiểm tra ném `AssertionError` tường minh phù hợp hơn.
10. **Kiểm tra identity ở mọi nơi vì nghĩ rằng pool tiết kiệm bộ nhớ.** Quy tắc tối ưu bộ nhớ không tự biến thành hợp đồng chức năng của hệ thống. Chỉ kiểm tra identity khi thật sự muốn kiểm chứng literal, constant expression hoặc `intern()`.

## 10. Tự luyện tập

**Câu 1.** Dự đoán hai kết quả:

```java
String a = "cat";
String b = "c" + "at";
System.out.println(a == b);
System.out.println(a.equals(b));
```

Đáp án: `true`, `true`. Biểu thức ghép hai literal được tính lúc biên dịch.

**Câu 2.** Dự đoán với biến không `final`:

```java
String prefix = "c";
String a = "cat";
String b = prefix + "at";
System.out.println(a == b);
System.out.println(a.equals(b));
```

Đáp án: `false`, `true`. Đây là phép nối ở runtime, nhưng nội dung vẫn bằng `cat`.

**Câu 3.** `final` có đủ để phép nối trở thành constant expression không?

Không. Cần biến `final` có kiểu nguyên thủy hoặc `String` và **được khởi tạo bằng constant expression**. Ví dụ `final String p = "c";` có thể được gộp; `final String p = new String("c");` thì không.

**Câu 4.** Phân biệt hai phép thử:

```java
String x = new String("cat");
String y = new String("cat");
System.out.println(x == y);
System.out.println(x.intern() == y.intern());
```

Đáp án: `false` rồi `true`. Hai đối tượng tạo riêng, nhưng kết quả intern cùng nội dung là một tham chiếu canonical.

**Câu 5.** Một hàm trả `new String("OK")` khi thành công. Nên kiểm tra `assertEquals("OK", actual)` hay `assertSame("OK", actual)`?

Nếu hợp đồng chỉ yêu cầu giá trị `OK` thì dùng `assertEquals`. `assertSame` sẽ đòi hỏi cùng một tham chiếu và không phản ánh đúng yêu cầu.

**Câu 6.** Khi cả hai biến `String` có thể `null`, cách so sánh nội dung an toàn là gì?

`Objects.equals(a, b)`. Nó cho `true` nếu cả hai `null`, `false` nếu chỉ một bên `null`, và dùng `equals` nếu cả hai khác null.

## 11. Checklist trước khi kết luận test

- **Bạn đang kiểm tra văn bản hay identity?** Văn bản dùng `equals`/`assertEquals`; identity dùng `==`/`assertSame`.
- **Biểu thức có thực sự là hằng ở compile time?** Kiểm tra xem mỗi biến tham gia có phải constant variable hay không.
- **Có `new String`, `StringBuilder` hoặc nối runtime không?** Khi đó không tự coi kết quả là interned.
- **Có dùng `intern()` không?** So sánh **tham chiếu trả về** và đừng nhầm với biến ban đầu.
- **Có khả năng null không?** Dùng `Objects.equals` hoặc literal ở bên trái lời gọi `equals`.
- **Kiểm thử có thật sự thất bại khi sai không?** Dùng JUnit, điều kiện ném `AssertionError` hoặc chạy Java assertion với `-ea` đúng cách.

**Ghi nhớ:** `==` và `assertSame` nói về **đối tượng**; `equals` và `assertEquals` nói về **nội dung**; `intern()` chuẩn hóa tham chiếu; *constant expression* quyết định trường hợp chuỗi được tính và intern ở compile time. Viết kiểm thử theo hợp đồng hành vi, sau đó mới quan tâm đến cơ chế pool nếu đó thực sự là mục tiêu kiểm thử.

## Tài liệu chính thức

- [`String.equals`, `String.intern` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java Language Specification, 3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.5)
- [Java Language Specification, 15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29)
- [Java Language Specification, 4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4)
