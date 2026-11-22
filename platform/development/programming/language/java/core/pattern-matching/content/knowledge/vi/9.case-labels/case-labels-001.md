# Cú pháp `case` với type pattern trong Java

**Chủ đề:** Java Core Pattern Matching → Case label  
**Nền tảng:** Java 21 trở lên cho pattern matching trong `switch` (JEP 441). Cú pháp `instanceof Type variable` đã chính thức từ Java 16, nhưng không đồng nghĩa với việc `switch` hỗ trợ type pattern trong Java 17.

## 1. Type pattern trong `case` dùng để làm gì?

Khi một biến được khai báo với kiểu rộng như `Object`, interface hoặc lớp cha, giá trị runtime có thể thuộc nhiều kiểu cụ thể. Trước Java 21, người học thường dùng chuỗi `if / else if` với `instanceof` để phân biệt từng kiểu. Pattern matching cho `switch` cho phép viết những nhánh phân loại trực tiếp bằng **type pattern** trong nhãn `case`.

Một type pattern có dạng **`Type variable`**, ví dụ `String text`, `Integer number` hoặc `CharSequence chars`. Khi selector khớp kiểu, Java gắn giá trị đã được kiểm tra cho *pattern variable* và thực thi nhánh thích hợp.

Ví dụ ngắn trên Java 21:

```java
static String kind(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Khác";
    };
}
```

Điểm cốt lõi: `case String text` đồng thời là một **điều kiện kiểm tra kiểu** và một **khai báo biến pattern**. Khi nhánh này chạy, `text` có kiểu tĩnh `String`; không cần ép kiểu lại. Nếu đối tượng là `Integer`, nhánh `String` không khớp và Java xét nhánh tương ứng tiếp theo.

## 2. Cú pháp chuẩn trong Java 21

Trong `switch` expression hoặc `switch` statement, một nhãn type pattern thường dùng cú pháp:

```java
case Type variable -> expression
case Type variable -> { /* statement(s) */ }
case Type variable when condition -> expression
```

Ví dụ các nhãn độc lập (đặt trong một `switch` phù hợp):

```java
case String text -> text.length();
case Integer number -> number.intValue();
case Number number when number.doubleValue() > 0 -> 1;
```

Ở ví dụ này, `Type` là kiểu tham chiếu được phép dùng tại vị trí pattern; `variable` là tên biến có thể sử dụng trong phần điều kiện `when` và phần thân nhánh được chọn. **Đây là những đoạn mã minh họa riêng lẻ**, không ghép cả ba nhãn thành một `switch` độc lập vì các kiểu kết quả, thứ tự nhánh và trường hợp còn thiếu cần được thiết kế theo một phương thức cụ thể.

Có hai hình thức phổ biến để viết phần thân:

**Arrow rule `->`** (nên ưu tiên với ví dụ mới):

```java
case String text -> "Text:" + text;
case Integer number -> {
    System.out.println("Đã nhận số nguyên");
    yield "Number:" + number;
}
```

Với `switch` **expression**, một block ở bên phải `->` phải dùng `yield` để trả giá trị từ block cho biểu thức `switch` (trừ khi block không thể hoàn tất bình thường). Đây không phải `return` của phương thức chứa `switch`.

**Colon `:` trong `switch` statement**:

```java
case String text:
    result = "Text:" + text;
    break;
```

Dạng colon hỗ trợ các câu lệnh quen thuộc; `break` thường dùng để chấm dứt nhánh trong `switch` statement, tránh rơi qua (*fall-through*) các nhánh sau. Khi sử dụng pattern variables, luật phạm vi và definite assignment khiến fall-through giữa các nhãn có pattern dễ sinh lỗi; dùng `->` giúp ý định rõ ràng.

### 2.1. `Type variable` khác `case` hằng số

`case String text` kiểm tra một nhóm giá trị theo **kiểu runtime**; `case "hello"` kiểm tra một **hằng chuỗi cụ thể**. Tương tự, `case Integer number` kiểm tra đối tượng `Integer`, còn `case 10` là nhãn hằng số nguyên (phải hợp lệ theo kiểu selector và luật nhãn của `switch`).

Không được viết `case String ->` rồi mong compiler tự tạo biến: type pattern gồm **kiểu và tên biến**. Nếu muốn sử dụng `String text`, phải khai báo đầy đủ pattern.

## 3. Type pattern hoạt động trong `switch` expression

Ví dụ:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text -> "String dài " + text.length();
        case Number number -> "Number: " + number;
        default -> "Other";
    };
}
```

Trình tự xử lý:

1. `switch` đánh giá selector `value` **một lần** để lựa chọn nhánh.
2. Nếu `value == null`, nhánh `case null` được chọn.
3. Nếu không null và là `String`, `case String text` khớp; `text` mang giá trị đó và có kiểu tĩnh `String`.
4. Nếu là `Number` như `Integer` hoặc `Double`, nhánh `case Number number` có thể khớp.
5. Những giá trị chưa được bao phủ đi vào `default`.

Vì đây là `switch` **expression**, mỗi nhánh thực thi phải tạo ra một giá trị `String`, và toàn bộ các trường hợp phải được xử lý đủ theo quy tắc *exhaustiveness* của compiler. Trong ví dụ này, `default` giúp bao phủ các kiểu chưa được liệt kê.

## 4. Guard `when`: điều kiện sau khi type pattern đã khớp

Từ Java 21, có thể bổ sung điều kiện bằng **`when`**:

```java
case String text when text.isBlank() -> "Blank String";
case String text -> "String: " + text;
```

Compiler chỉ đánh giá `text.isBlank()` **sau khi** type pattern `String text` khớp. Do đó, ở điều kiện guard, `text` có kiểu `String` và có thể gọi các phương thức của `String`. Nếu guard trả `false`, `switch` tiếp tục xét nhãn phù hợp khác; ví dụ thứ hai nhận các chuỗi không blank.

Cần đặt nhánh có guard **trước** nhánh `String` tổng quát. Nếu viết:

```java
// KHÔNG BIÊN DỊCH: nhánh sau bị dominance.
case String text -> "String";
case String text when text.isBlank() -> "Blank";
```

Nhánh `case String text` đầu đã nhận mọi chuỗi không null, làm nhánh đặc biệt phía sau không thể được chọn. Cú pháp `case String text && text.isBlank()` từng xuất hiện trong các giai đoạn preview cũ; với Java 21 chính thức, dùng `when`.

Guard phù hợp cho các điều kiện nhỏ, rõ ý nghĩa (độ dài, trạng thái, khoảng giá trị). Nếu điều kiện phức tạp hoặc có tác dụng phụ, nên cân nhắc chuyển logic vào phương thức riêng để dễ thử nghiệm và bảo trì.

## 5. Thứ tự nhãn và quy tắc dominance

Các type pattern có thể bao phủ nhau theo quan hệ kế thừa/interface. Ví dụ, mọi `Integer` là `Number`, nên nhãn `Number` tổng quát sẽ che nhãn `Integer` đặt sau:

```java
// KHÔNG BIÊN DỊCH: case Integer bị case Number chi phối.
case Number number -> "Number";
case Integer integer -> "Integer";
```

Hãy đảo thứ tự:

```java
case Integer integer -> "Integer";
case Number number -> "Number";
```

Nguyên tắc cho các mẫu có quan hệ bao phủ: **ưu tiên trường hợp cụ thể, rồi mới đến trường hợp tổng quát**. Tương tự, `case CharSequence chars` đặt trước `case String text` khiến `String` bị che, vì `String` triển khai `CharSequence`.

Một nhánh `default` không tạo ra pattern variable. Đặt `default` sau các nhánh muốn phân loại sẽ dễ đọc hơn.

Sự chi phối của guard được xét theo quy tắc của ngôn ngữ: không nên giả định compiler có thể chứng minh mọi mệnh đề tùy ý. Thứ tự rõ ràng và kiểm thử với đầu vào đại diện giúp mã tránh nhầm lẫn.

## 6. `null` không khớp type pattern cấp ngoài

**`null` không phải instance của `String`, `Number`, `Object` hay một kiểu tham chiếu khác.** Vì vậy, khi selector là `null`, `case String text` không phải nhãn xử lý nó.

Đối với `switch` có pattern trên Java 21:

```java
return switch (value) {
    case null -> "NULL";
    case String s -> "String";
    default -> "Other";
};
```

Nếu selector có thể là `null` nhưng `switch` không có `case null` (hoặc nhãn tương đương `case null, default`), việc đánh giá selector `null` thông thường dẫn đến `NullPointerException`. **`default` đứng một mình không tự xử lý `null`.**

Khi muốn ghép `null` và các trường hợp khác vào cùng một nhánh, Java 21 cho phép cú pháp:

```java
case null, default -> "Unknown";
```

Đây là quy tắc chọn nhánh dành cho `null`, không phải một type pattern mới. Một pattern tổng quát như `case Object object` vẫn không phải cách mặc định để bắt `null`.

## 7. Pattern variable nằm trong phạm vi nào?

Với:

```java
switch (value) {
    case String text -> System.out.println(text.length());
    case Integer number -> System.out.println(number + 1);
    default -> System.out.println("Other");
}
```

- `text` được dùng trong nhánh `String`, và trong `when` của chính pattern nếu có.
- `number` chỉ được dùng tại vị trí mà pattern `Integer number` đã khớp.
- `text` và `number` không tự trở thành biến dùng được **sau** `switch` hoặc trong nhánh `default`.
- Khai báo pattern variable không làm thay đổi kiểu khai báo ban đầu của `value` trong toàn bộ phương thức.

Điều này tương đồng với *flow scoping* của `instanceof`: compiler chỉ cho dùng biến khi có thể chứng minh mẫu đã khớp. Không nên ép lại selector khi đã có pattern variable hợp lệ.

## 8. Type pattern và generics

Trong `switch (Object input)`, cú pháp `case java.util.List<?> items` có thể kiểm tra giá trị là một `List` rồi cung cấp biến có kiểu `List<?>`:

```java
static int sizeIfList(Object input) {
    return switch (input) {
        case java.util.List<?> items -> items.size();
        case null, default -> -1;
    };
}
```

Dấu `?` có nghĩa kiểu phần tử chưa biết; `List<?>` là dạng có thể được kiểm tra phù hợp ở runtime (*reifiable*). Ngược lại:

```java
// KHÔNG BIÊN DỊCH khi selector chỉ có kiểu Object:
// case java.util.List<String> items -> items.size();
```

Vì **type erasure**, runtime không thể chứng minh toàn bộ phần tử của một đối tượng `List` đều là `String` chỉ bằng type pattern `List<String>`. Hãy kiểm tra từng phần tử khi nghiệp vụ yêu cầu hoặc giữ hợp đồng kiểu ở API đầu vào.

Trong Java 21, type pattern ở `case` của bài học này áp dụng cho **kiểu tham chiếu**. Đừng sao chép cú pháp pattern cho `int`, `double` hay `boolean` rồi giả định Java 21 đã hỗ trợ mọi primitive pattern như những bản Java mới hơn hoặc các đề xuất preview.

## 9. Ví dụ hoàn chỉnh Java 21

Tạo tệp **`CaseTypePatternDemo.java`**:

```java
public class CaseTypePatternDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "Blank String";
            case String s -> "String(" + s.length() + "):" + s;
            case Integer n when n >= 0 -> "Nonnegative Integer:" + n;
            case Integer n -> "Negative Integer:" + n;
            case Number n -> "Other Number:" + n;
            default -> "Other:" + value.getClass().getSimpleName();
        };
    }

    static String describeStatement(Object value) {
        String result;
        switch (value) {
            case null:
                result = "NULL";
                break;
            case String text:
                result = "TEXT:" + text;
                break;
            default:
                result = "OTHER";
                break;
        }
        return result;
    }

    public static void main(String[] args) {
        Object[] samples = {null, "   ", "Java", 0, -2, 3.5, true};
        for (Object sample : samples) {
            System.out.println(describe(sample));
        }
        System.out.println(describeStatement("Hi"));
        System.out.println(describeStatement(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 CaseTypePatternDemo.java
java CaseTypePatternDemo
```

Kết quả:

```text
NULL
Blank String
String(4):Java
Nonnegative Integer:0
Negative Integer:-2
Other Number:3.5
Other:Boolean
TEXT:Hi
NULL
```

Giải thích theo từng nhóm:

1. `null` khớp `case null`, trả `NULL`; không được chuyển sang `case String s`.
2. Chuỗi ba dấu cách khớp `String s` và guard `s.isBlank()` trả `true`, nên in `Blank String`.
3. `"Java"` không blank, đi tới type pattern `String s` chung và in `String(4):Java`.
4. Giá trị `0` là `Integer` không âm, khớp nhánh có guard `n >= 0`; `-2` vào nhánh `Integer n` còn lại.
5. `3.5` được boxing thành `Double`; không phải `Integer`, nhưng là `Number`, nên in `Other Number:3.5`.
6. `true` là `Boolean`, không thuộc các nhánh trước, nên vào `default` và in `Other:Boolean`.
7. Phương thức `describeStatement` cho thấy cú pháp colon cần `break` để kết thúc nhánh; `"Hi"` in `TEXT:Hi` và `null` in `NULL`.

Ví dụ dùng `when`, type pattern và `switch` expression chính thức từ Java 21; không cần cờ preview. Khi chạy, hãy bảo đảm compiler dự án thực sự dùng JDK 21+ và mức `--release` thích hợp.

## 10. Exhaustiveness và sealed hierarchy

Không phải mọi `switch` expression đều phải viết `default` nếu compiler có thể chứng minh các case đã đủ. Khi selector có một **sealed hierarchy**, các type pattern có thể bao phủ toàn bộ các subtype được phép:

```java
sealed interface Result permits Success, Failure {}
record Success(String message) implements Result {}
record Failure(int code) implements Result {}

static String summarize(Result result) {
    return switch (result) {
        case Success success -> success.message();
        case Failure failure -> "Error:" + failure.code();
    };
}
```

Đây là **đoạn minh họa** cần đặt cùng các khai báo kiểu phù hợp trong một tệp Java 21. Compiler biết `Result` chỉ có những subtype trực tiếp được cho phép, vì thế có thể kiểm tra tính đầy đủ của `switch`. Tuy nhiên, nếu selector thực sự là `null`, `switch` không có `case null` vẫn không coi `null` là đã được xử lý. Với dữ liệu đầu vào cần chấp nhận `null`, hãy thêm nhánh tường minh.

Type pattern trong `case` chỉ là một phần của hệ thống pattern matching; record pattern như `case Point(int x, int y)` còn cho phép bóc tách component, nhưng đó là một dạng pattern khác và cần được phân biệt khi đọc code.

## 11. Các lỗi phổ biến

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Viết `case String ->` | Thiếu biến của type pattern | Dùng `case String text ->` |
| Dùng `case String s && guard` trên Java 21 | Cú pháp preview cũ, không phải cú pháp chính thức | Dùng `case String s when guard ->` |
| Đặt `case Number n` trước `case Integer i` | Pattern rộng chi phối pattern hẹp | Sắp xếp nhánh cụ thể trước |
| Đặt nhánh `case String s` trước `case String s when ...` | Nhánh `String` có guard bị chi phối | Đặt guard trước pattern tổng quát |
| Tin rằng `default` bắt `null` | Quy tắc `null` của `switch` là riêng | Dùng `case null` hoặc kiểm tra trước `switch` |
| Dùng biến pattern ngoài nhánh khớp | Không bảo đảm pattern đã thành công | Chỉ sử dụng biến trong `when` và nhánh của nó |
| Lạm dụng `case List<String> list` với `Object` | Không xác minh được type argument bị xóa | Dùng `List<?>`, rồi kiểm tra phần tử khi cần |
| Thiếu nhánh trong `switch` expression | Compiler không chứng minh được exhaustiveness | Bổ sung pattern còn thiếu hoặc `default` hợp lệ |
| Viết `case ...:` nhưng quên `break` | Có thể fall-through hoặc gặp lỗi liên quan đến scope của pattern variable | Ưu tiên `->`; nếu dùng colon, kiểm soát luồng rõ ràng |
| Chạy trên Java 17 | Type pattern cho `switch` chưa là tính năng ổn định của Java 17 | Dùng JDK 21+ cho bài này |

## 12. Tự luyện tập và tiêu chí hoàn thành

1. Viết `switch (Object value)` trả chuỗi mô tả riêng cho `String`, `Integer`, `Double`, `null` và các kiểu khác. Dùng pattern variable để lấy dữ liệu trong từng nhánh.
2. Bổ sung guard `when` cho `String` rỗng hoặc chỉ có khoảng trắng; bảo đảm nhánh có guard đứng trước nhánh `String` chung.
3. Cố ý đổi thứ tự `case Number n` và `case Integer i`, biên dịch, đọc lỗi dominance và sửa lại.
4. Viết cùng một phương thức bằng `switch` expression dùng `->` và `switch` statement dùng `case ...:` với `break`. So sánh phạm vi biến và hành vi return/yield.
5. Thử truyền `null` vào `switch` chỉ có `default` rồi bổ sung `case null` để quan sát sự khác nhau.
6. Viết `case java.util.List<?> list` để lấy `list.size()`; giải thích vì sao không thể khẳng định phần tử của list có kiểu `String` khi chỉ biết `Object` từ đầu.
7. Dự đoán output của chương trình `CaseTypePatternDemo`, biên dịch và đối chiếu cả 9 dòng kết quả.

**Đạt yêu cầu khi:** viết đúng cú pháp `case Type variable`, phân biệt arrow rule và colon statement, dùng được guard `when`, giải thích được dominance, exhaustiveness, phạm vi pattern variable, việc xử lý `null` và các giới hạn với generic types.

**Tài liệu chính thức:**

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — Switch Statements (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
