# Pattern matching trong switch expression (Java 21)

## 1. Vì sao kết hợp pattern matching với switch expression?

Khi một biến kiểu tham chiếu có thể chứa nhiều loại đối tượng, cách xử lý truyền thống thường là chuỗi `if / else if` kết hợp `instanceof`. Mỗi nhánh kiểm tra kiểu, ép kiểu (nếu dùng cú pháp cũ), rồi trả về kết quả tương ứng. Khi nhánh tăng lên, code dễ dài và khó nhận ra liệu đã xử lý đủ trường hợp hay chưa.

**Pattern matching trong `switch expression`** cho phép đặt các *type pattern* ngay trong nhãn `case`. Mỗi nhánh vừa kiểm tra kiểu, vừa có thể ràng buộc một biến đã đúng kiểu và **sản sinh một giá trị** cho toàn bộ `switch`. Kết hợp với `when`, `case null`, record pattern và kiểu `sealed`, cách viết này đặc biệt hữu ích cho các bài toán phân loại và chuyển đổi dữ liệu có nhiều biến thể.

Ví dụ, một đầu vào có thể là `String`, `Integer` hoặc kiểu khác:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

Đây là **phương thức minh họa đặt bên trong một lớp**, dùng cú pháp chính thức của **Java 21 trở lên**. Giá trị của nhánh được chọn chính là giá trị của `switch expression`; từ khóa `return` trả kết quả đó ra khỏi phương thức.

Mục tiêu của bài: viết được `switch expression` có pattern đúng cú pháp, hiểu thứ tự chọn case và phạm vi pattern variable, xử lý guard/null, chứng minh tính đầy đủ (*exhaustiveness*), phân biệt `->` với `yield`, và biết khi nào cách viết này thích hợp hơn `if/else` hoặc đa hình.

## 2. Điều kiện tiên quyết và phiên bản Java

Trước khi học, nên nắm `instanceof`, cách hoạt động của kiểu tham chiếu, `null`, `switch` truyền thống và **switch expression** cơ bản. `switch expression` đã chính thức từ Java 14; **pattern matching cho `switch`** (type pattern, `when`, xử lý `null` trong ngữ cảnh pattern matching) chính thức từ Java 21. **Record pattern** cũng chính thức từ Java 21.

| Tính năng | Java 17 | Java 21 |
| --- | --- | --- |
| `switch expression` với nhãn hằng/enum và toán tử `->` | Có | Có |
| `instanceof String text` | Có | Có |
| `case String text -> ...` trong `switch` | Chưa chính thức | Có |
| `case String s when ...` | Chưa chính thức | Có |
| `case null` trong pattern `switch` | Chưa chính thức | Có |
| `case Point(int x, int y)` | Chưa chính thức | Có |
| `sealed` interface/class | Có | Có |

Các ví dụ chính trong bài dùng **Java 21** và không cần `--enable-preview`. Nếu dùng JDK mới hơn nhưng dự án đặt mục tiêu Java 17, `--release 17` vẫn không cho biên dịch cú pháp pattern `switch` của Java 21. Tránh lấy một ví dụ sử dụng tính năng preview ở phiên bản khác rồi giả định nó là cú pháp Java 21 ổn định.

Kiểm tra môi trường:

```bash
java -version
javac -version
```

Với ví dụ độc lập, dùng `javac --release 21 TenFile.java` để bảo đảm không vô tình phụ thuộc tính năng ngôn ngữ mới hơn.

## 3. Cú pháp và ý nghĩa của switch expression

Cấu trúc thông dụng:

```java
ResultType result = switch (selector) {
    case TypeA a -> expressionA;
    case TypeB b when conditionUsingB -> expressionB;
    case TypeB b -> expressionC;
    case null -> expressionForNull;
    default -> fallbackExpression;
};
```

Đoạn này là **mẫu cú pháp**, không phải Java biên dịch độc lập: `ResultType`, `TypeA`, `TypeB` và các biểu thức chỉ tượng trưng cho kiểu và logic thực tế.

Các thành phần cần hiểu:

- `selector` là biểu thức được đánh giá để chọn nhánh; ở Java 21, kiểu của nó phải thuộc các kiểu hợp lệ cho `switch`. Với ví dụ phân loại nhiều loại đối tượng, `Object` hoặc một interface là lựa chọn tự nhiên.
- `case String text` là **type pattern**: nếu selector khớp `String`, nó ràng buộc pattern variable `text` có kiểu `String`.
- `when` là **guard**: biểu thức boolean được kiểm tra sau khi pattern đã khớp; guard sai khiến quá trình tìm nhánh tiếp tục.
- `->` đánh dấu thân nhánh. Với một biểu thức bên phải, kết quả biểu thức đó trở thành kết quả của `switch expression`.
- `case null` xử lý đầu vào `null` một cách rõ ràng.
- `default` xử lý các đầu vào còn lại trong ngữ cảnh tương ứng.
- Dấu chấm phẩy `;` sau dấu `}` thuộc về câu lệnh chứa `switch expression` (ví dụ phép gán hoặc `return`).

**Switch expression khác switch statement:** expression luôn biểu diễn **một kết quả** và phải có đường đi hợp lệ sản sinh kết quả hoặc ném ngoại lệ; statement thường dùng để thực hiện tác vụ và không nhất thiết trả một giá trị. Đừng nhầm hai dạng chỉ vì đều viết `switch (...)`.

### So sánh với chuỗi if/else

```java
static String withoutSwitch(Object input) {
    if (input == null) {
        return "missing";
    } else if (input instanceof String text) {
        return "text: " + text;
    } else if (input instanceof Integer number) {
        return "integer: " + number;
    }
    return "other";
}
```

Kết quả tương đương với ví dụ `switch` đầu bài trong các trường hợp đã liệt kê. `if/else` vẫn tốt nếu chỉ cần một đến hai nhánh hoặc có điều kiện không gắn với kiểu dữ liệu. `switch expression` rõ hơn khi cùng một selector được phân loại theo nhiều mẫu để tạo một kết quả.

## 4. Ví dụ chạy đầy đủ: nhiều type pattern, guard, null và default

Lưu **toàn bộ** mã sau vào `SwitchExpressionPatterns21.java`:

```java
import java.util.List;

public class SwitchExpressionPatterns21 {

    static String describe(Object value) {
        return switch (value) {
            case null -> "missing";

            case String text when text.isBlank() -> "blank";

            case String text -> "text: " + text.strip();

            case Integer number when number < 0 -> "negative: " + number;

            case Integer number -> "integer: " + number;

            case List<?> list -> "list: " + list.size();

            default -> "other: " + value.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("   "));
        System.out.println(describe("  Java  "));
        System.out.println(describe(-2));
        System.out.println(describe(5));
        System.out.println(describe(List.of("A", "B")));
        System.out.println(describe(1.5));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac -encoding UTF-8 --release 21 SwitchExpressionPatterns21.java
java SwitchExpressionPatterns21
```

Kết quả chính xác:

```text
missing
blank
text: Java
negative: -2
integer: 5
list: 2
other: Double
```

**Điều gì xảy ra tại mỗi lời gọi?**

1. `describe(null)` đi vào `case null`, không nhờ đến `default`.
2. `"   "` là `String` và thỏa `text.isBlank()`, nên trả `blank`.
3. `"  Java  "` là `String` nhưng guard `isBlank()` sai; nhánh `String` tiếp theo trả chuỗi đã `strip()`.
4. `-2` được autobox thành `Integer`; guard `number < 0` đúng.
5. `5` là `Integer` không âm; rơi vào nhánh `Integer` không guard.
6. `List.of("A", "B")` khớp `List<?>`; đoạn mã chỉ kiểm tra **đối tượng là List**, không cố đối sánh từng phần tử.
7. `1.5` được autobox thành `Double` và khớp nhánh `default`. Vì nhánh `null` đã đứng riêng, gọi `value.getClass()` trong `default` của ví dụ này an toàn.

`List<?>` là lựa chọn hợp lệ để đối sánh một danh sách có tham số kiểu chưa biết. Với biến `Object`, cách viết `case List<String> list` không hợp lệ vì thông tin generic `String` không được kiểm tra đầy đủ ở runtime. Muốn xử lý phần tử `String`, cần kiểm tra từng phần tử hoặc dùng một kiểu dữ liệu có hợp đồng mạnh hơn.

## 5. Pattern variable và phạm vi trong từng nhánh

Trong `case String text -> ...`, biến `text` chỉ có nghĩa ở nơi mà pattern đã khớp. Với guard `when`, biến cũng dùng được trong điều kiện đó:

```java
static String classify(Object value) {
    return switch (value) {
        case String text when text.length() >= 5 -> "long: " + text;
        case String text -> "short: " + text;
        case Integer number -> "integer: " + number;
        case null -> "null";
        default -> "other";
    };
}
```

Đây là phương thức minh họa Java 21. `text` ở guard của case đầu tiên đã là `String` khi `length()` được gọi. Tên `text` xuất hiện lại ở case thứ hai là một pattern variable của **case khác**, không phải giá trị được giữ lại từ nhánh đầu. Một biến pattern trong case `Integer` không tự xuất hiện ở case `String`.

Vì mỗi nhánh `->` có luồng điều khiển riêng, kiểu viết này không có tình huống rơi xuyên (*fall-through*) sang thân case tiếp theo như `switch` statement kiểu dấu hai chấm truyền thống. Sau khi một nhánh `->` được chọn và hoàn thành, `switch expression` hoàn thành với giá trị của nhánh đó.

Lưu ý: `when` không phải một `if` luôn chạy trước tất cả pattern. **Pattern phải khớp trước**, rồi guard mới được tính. Nếu guard có tác dụng phụ, việc chọn nhánh sẽ khó hiểu và khó kiểm thử; nên dùng điều kiện thuần, nhanh và không làm thay đổi trạng thái.

## 6. Thứ tự case và lỗi dominance

Java kiểm tra xem case đứng trước có **bao phủ toàn bộ** những giá trị mà case đứng sau định nhận không. Khi đó case phía sau bị *dominated* (che khuất) và thường là lỗi biên dịch.

### Ví dụ sai: nhánh tổng quát đứng trước nhánh cụ thể

```java
// CỐ Ý SAI: case String đã bị case CharSequence che khuất.
return switch (value) {
    case CharSequence sequence -> sequence.toString();
    case String text -> text; // Bị dominance.
    default -> "other";
};
```

Đây là mảnh mã minh họa, yêu cầu biến `value` trong một phương thức. Vì `String` triển khai `CharSequence`, nhánh trước có thể khớp mọi đối tượng `String` khác null, nên nhánh sau không còn cơ hội được chọn.

Sửa theo thứ tự **cụ thể trước, tổng quát sau**:

```java
return switch (value) {
    case String text -> "String: " + text;
    case CharSequence sequence -> "Other text: " + sequence;
    default -> "other";
};
```

Đây cũng là biểu thức minh họa trong phương thức và giả định selector có kiểu thích hợp, ví dụ `Object value` không-null. Với đầu vào có thể `null`, thiết kế thêm `case null` riêng như những ví dụ đầy đủ.

### Ví dụ sai: guard đặt sau case cùng kiểu không guard

```java
// CỐ Ý SAI: case đầu đã khớp mọi String khác null.
return switch (value) {
    case String text -> "any text";
    case String text when text.isBlank() -> "blank"; // Bị dominance.
    default -> "other";
};
```

Sửa bằng cách đưa nhánh guard trước:

```java
return switch (value) {
    case String text when text.isBlank() -> "blank";
    case String text -> "any text";
    default -> "other";
};
```

Thông thường, trình biên dịch **không chứng minh quan hệ bao hàm giữa mọi biểu thức guard tùy ý**; đừng dựa vào thứ tự guard phức tạp mà không viết kiểm thử. Quy tắc dễ bảo trì là: các trường hợp đặc biệt có guard trước, nhánh bao quát cùng kiểu sau cùng.

## 7. Xử lý null chính xác trong switch expression

Một hiểu lầm nguy hiểm là cho rằng `default` bao gồm `null`. Với kiểu `switch` có pattern thông thường ở Java 21, nếu selector là `null` mà không có nhánh xử lý `null` thích hợp, Java ném `NullPointerException`; `default` không tự động nhận `null`.

```java
static String unsafe(Object value) {
    return switch (value) {
        case String text -> "text";
        default -> "other";
    };
}
```

Đây là phương thức minh họa Java 21: `unsafe(null)` ném `NullPointerException`, không trả `other`. Dùng nhánh cụ thể khi null là đầu vào hợp lệ:

```java
static String safe(Object value) {
    return switch (value) {
        case null -> "no input";
        case String text -> "text: " + text;
        default -> "other";
    };
}
```

Nếu null **vi phạm hợp đồng đầu vào**, có thể từ chối rõ ràng:

```java
static String requireInput(Object value) {
    return switch (value) {
        case null -> throw new IllegalArgumentException("value is required");
        case String text -> text;
        default -> "unsupported";
    };
}
```

Ba ví dụ trên là các phương thức độc lập có thể đặt vào một lớp Java 21. `throw` hợp lệ ở nhánh `->` và thể hiện rõ rằng đường đi này **không trả một giá trị kết quả** vì cố ý báo lỗi.

Nên phân biệt `null` với chuỗi rỗng và kiểu không được hỗ trợ: `null` là thiếu đối tượng, `"  "` vẫn là đối tượng `String`, và `Double` là đối tượng hiện hữu thuộc kiểu khác. Các trường hợp này không nhất thiết có cùng cách xử lý nghiệp vụ.

## 8. Các nhánh trả giá trị: ->, block và yield

Trong một `switch expression`, nhánh dạng `->` có thể là:

- **Một biểu thức**, khi đó giá trị biểu thức trở thành kết quả của `switch`.
- **Một khối lệnh** `{ ... }`, trong đó dùng `yield value;` để trả giá trị cho `switch expression`.
- **Một câu lệnh `throw`**, khi nhánh này cần ném ngoại lệ.

Ví dụ dùng một khối lệnh:

```java
static String summary(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> {
            String normalized = text.strip();
            int length = normalized.length();
            yield "length: " + length;
        }
        default -> "other";
    };
}
```

Đây là phương thức hoàn chỉnh về cú pháp và có thể đặt trong lớp Java 21. Gọi `summary("  Java  ")` trả `"length: 4"`.

**Vì sao không dùng `return` trong block?** Với `switch expression`, `yield` cung cấp giá trị cho biểu thức `switch` đang bao quanh. `return` là thao tác trả về từ **phương thức**, không phải cách thay thế `yield` ở đây. Nếu một block có đường đi hoàn thành bình thường mà không cung cấp giá trị thích hợp, trình biên dịch sẽ từ chối.

`yield` không phải cách dùng để trả giá trị từ `switch statement` thông thường. Khi muốn sinh giá trị rồi gán cho biến hoặc trả từ phương thức, ưu tiên `switch expression` và `yield` đúng chỗ.

### So sánh với dạng dấu hai chấm

Java cũng cho phép `switch expression` theo cú pháp nhóm câu lệnh kiểu `case ...:`, dùng `yield` để tạo giá trị. Tuy nhiên, với pattern matching và các nhánh độc lập, dạng `->` thường dễ đọc và ít rủi ro do fall-through hơn. Đừng trộn các kiểu nhãn case khác nhau trong cùng một khối `switch`.

## 9. Exhaustiveness: switch expression phải bao quát mọi trường hợp có thể

Một `switch expression` không được để một đầu vào hợp lệ rơi hết các nhánh mà không có kết quả. Trình biên dịch áp dụng kiểm tra **exhaustiveness**. Với selector kiểu `Object` hoặc một miền kiểu mở, cách đơn giản là có `default` xử lý phần còn lại:

```java
static String openWorld(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s -> s;
        case Integer i -> i.toString();
        default -> "unsupported";
    };
}
```

Những kiểu `Object` khác `String` và `Integer` vẫn có thể xuất hiện; `default` giúp biểu thức đầy đủ. Nhánh `null` có ý nghĩa độc lập.

Với **sealed interface/class**, Java biết tập những kiểu con được phép. Nếu liệt kê đầy đủ các biến thể, `switch expression` có thể exhaustive **mà không cần `default`**. Điều này hữu ích vì khi bổ sung biến thể mới, trình biên dịch có thể chỉ ra nơi xử lý phải cập nhật.

### Ví dụ hoàn chỉnh: sealed + record pattern + switch expression

Lưu toàn bộ nội dung sau vào `ExhaustiveSwitchExample21.java`:

```java
public class ExhaustiveSwitchExample21 {

    sealed interface Expr permits Literal, Add {}

    record Literal(int value) implements Expr {}

    record Add(Expr left, Expr right) implements Expr {}

    static int evaluate(Expr expr) {
        return switch (expr) {
            case null ->
                    throw new IllegalArgumentException("expr is required");

            case Literal(int value) ->
                    value;

            case Add(Expr left, Expr right) ->
                    evaluate(left) + evaluate(right);
        };
    }

    public static void main(String[] args) {
        Expr expression = new Add(new Literal(2), new Literal(3));
        System.out.println(evaluate(expression));
        System.out.println(evaluate(new Literal(-5)));

        try {
            evaluate(null);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 21 ExhaustiveSwitchExample21.java
java ExhaustiveSwitchExample21
```

Kết quả chính xác:

```text
5
-5
expr is required
```

**Giải thích:**

- `Expr` là interface `sealed`, chỉ cho phép hai kiểu con trực tiếp `Literal` và `Add`.
- `case Literal(int value)` là record pattern: nó đối sánh record `Literal` và khai báo biến component `value`.
- `case Add(Expr left, Expr right)` rút hai thành phần kiểu `Expr` để tính đệ quy.
- Hai case trên bao quát các biến thể mà `Expr` cho phép. `case null` minh bạch hóa hợp đồng đầu vào và cố ý ném lỗi.
- Không có `default`: nếu sau này bạn sửa mô hình để thêm `Multiply` như một kiểu con được phép, trình biên dịch có thể buộc cập nhật biểu thức `switch` cho biến thể mới.

Chương trình cho phép tạo `new Add(null, new Literal(1))` vì record chưa tự chặn component null. Khi đệ quy tới `evaluate(null)`, nhánh `case null` ném lỗi đã định nghĩa. Nếu mô hình **không chấp nhận component null**, cách tốt hơn là kiểm tra trong constructor của `Add` (ví dụ dùng `Objects.requireNonNull`) để bảo đảm bất biến khi tạo dữ liệu. Pattern matching không tự giải quyết hợp đồng nullable của mọi cấu trúc lồng.

**Guard và tính đầy đủ:** Một nhánh `case Literal(int v) when v > 0` chỉ xử lý một phần giá trị `Literal`. Nếu thiếu nhánh bao quát phần còn lại (chẳng hạn `case Literal(int v)`), compiler có thể coi `switch expression` chưa đầy đủ. Đừng dùng guard làm thay thế cho việc xử lý các trường hợp còn lại.

## 10. Khi nào switch expression thích hợp, khi nào không?

| Trường hợp | Lựa chọn hợp lý |
| --- | --- |
| Một giá trị đầu vào được phân loại theo nhiều kiểu và cần trả một kết quả | Pattern matching trong `switch expression` |
| Chỉ có một điều kiện kiểu ngắn | `if (value instanceof Type x)` có thể đơn giản hơn |
| Một nhánh có quy tắc con (trống, âm, quá hạn...) | Type pattern + `when`; đặt case đặc biệt trước case tổng quát |
| Tập biến thể đóng, muốn compiler phát hiện thiếu nhánh khi mở rộng | `sealed` + exhaustive `switch expression` |
| Dữ liệu là record, cần lấy component để tính toán | Record pattern trong `case` |
| Nhiều vị trí trong dự án lặp cùng một `switch` theo kiểu để gọi hành vi của đối tượng | Cân nhắc chuyển hành vi sang interface/phương thức đa hình |
| Nhiệm vụ chính là thực hiện nhiều side effect, không có kết quả thống nhất | `switch statement` hoặc phân tách hàm có thể thích hợp hơn |

Đừng ép mọi logic sang `switch expression` chỉ vì ngắn. Nếu nhiều case dài, lặp tính toán hoặc có nhiều tác dụng phụ, cân nhắc tách phần xử lý thành phương thức có tên. Giá trị mang về từ mỗi nhánh nên có cùng ý nghĩa trong miền nghiệp vụ.

## 11. Những lỗi thường gặp

### Lỗi 1: dùng pattern switch khi target còn Java 17

`case String s -> ...` trong ví dụ bài là cú pháp chính thức Java 21. Dự án Java 17 có thể dùng `instanceof String s` hoặc `switch expression` trên hằng số/enum nhưng chưa dùng ổn định các case pattern này.

### Lỗi 2: case tổng quát che khuất case đặc biệt

Đặt `case CharSequence cs` trước `case String s` hoặc đặt `case String s` không guard trước nhánh `case String s when ...` dẫn đến lỗi dominance. Xếp case có phạm vi hẹp trước.

### Lỗi 3: nghĩ default tự xử lý null

Với switch pattern thông thường, selector `null` không đi vào `default` như một kiểu dữ liệu khác. Hãy viết `case null` nếu null được chấp nhận; hoặc chủ động ném lỗi ở ranh giới.

### Lỗi 4: quên tính đầy đủ của expression

Một `switch expression` trên `Object` không thể chỉ có case cho `String` nếu những loại khác vẫn có thể xuất hiện. Cần `default` hoặc cách bao quát hợp lệ. Với kiểu `sealed`, trình biên dịch có thể chứng minh đủ các kiểu con.

### Lỗi 5: block không yield giá trị

`case String s -> { System.out.println(s); }` không thể là nhánh hoàn thành bình thường của một `switch expression` trả giá trị vì block thiếu `yield`. Nếu mục đích là in log và trả chuỗi, dùng `yield s;` sau lệnh in hoặc tách tác dụng phụ ra trước.

### Lỗi 6: nhầm biến trong guard với biến đã được khai báo ngoài

Trong `case String s when s.isBlank()`, `s` có mặt vì type pattern đã khớp. Nó không tồn tại tự động trong mọi case hay sau toàn bộ biểu thức.

### Lỗi 7: sai cách đối sánh generic

`case List<String> xs` trên selector `Object` không thể kiểm tra kiểu tham số trong runtime; thay bằng `case List<?> xs`, rồi kiểm tra các phần tử theo hợp đồng.

### Lỗi 8: nghĩ pattern matching luôn thay thế được đa hình

Với các đối tượng sở hữu hành vi độc lập, một interface có phương thức chung thường giúp thêm biến thể mà không phải sửa nhiều `switch` rải rác. Pattern `switch` mạnh khi **tập nhánh xử lý ở một nơi là điều bạn chủ đích muốn biểu diễn**.

### Lỗi 9: guard gây tác dụng phụ

`when` có thể được xét trong quá trình tìm case phù hợp. Điều kiện có tác dụng phụ hoặc phụ thuộc trạng thái thay đổi dễ khiến logic khó kiểm chứng; ưu tiên guard thuần và dễ đọc.

## 12. Bài tập thực hành có kiểm thử

**Bài 1 — Bộ phân loại dữ liệu:** Tạo `describe(Object x)` dùng `switch expression`, hỗ trợ `null`, chuỗi trắng, chuỗi bình thường, số nguyên âm, số nguyên không âm, `List<?>` và kiểu khác. Dùng các đầu vào của `SwitchExpressionPatterns21`, dự đoán từng dòng trước khi chạy.

**Bài 2 — Viết nhánh block với yield:** Chuyển nhánh `String` thường thành block. Tính `normalized` một lần, thêm một phép tính như độ dài chuỗi và dùng `yield` để trả kết quả. Giải thích vì sao không dùng `return` bên trong block này.

**Bài 3 — Phát hiện dominance:** Thử đưa `case CharSequence cs` lên trước `case String s`. Ghi lại lỗi biên dịch, giải thích quan hệ kiểu, sau đó sửa thứ tự.

**Bài 4 — Phân biệt null và kiểu chưa hỗ trợ:** Bỏ `case null` khỏi một switch có `default` rồi gọi với `null`. Ghi nhận hành vi và sửa lại theo hợp đồng `MISSING_INPUT`.

**Bài 5 — Hệ kiểu đóng:** Mở rộng `Expr` trong ví dụ thành `Literal`, `Add`, `Multiply`. Bổ sung `record Multiply(Expr left, Expr right) implements Expr` và chỉnh `permits`/case cần thiết. Quan sát lỗi khi chưa bổ sung case rồi thực hiện phép nhân.

**Bài 6 — Kiểm tra component nullable:** Thử `evaluate(new Add(null, new Literal(2)))` và giải thích vì sao phương thức từ chối. Sau đó thêm kiểm tra không-null trong record constructor để ngăn tạo trạng thái sai từ đầu.

### Bảng ca kiểm thử gợi ý

| Đầu vào | Kết quả dự kiến | Nhánh xử lý |
| --- | --- | --- |
| `null` | `missing` | `case null` |
| `"   "` | `blank` | `String` với guard `isBlank` |
| `"  Java  "` | `text: Java` | `String` thường |
| `-2` | `negative: -2` | `Integer` với guard |
| `5` | `integer: 5` | `Integer` thường |
| `List.of("A", "B")` | `list: 2` | `List<?>` |
| `1.5` | `other: Double` | `default` |
| `new Add(new Literal(2), new Literal(3))` | `5` | Record pattern `Add` và `Literal` |
| `new Literal(-5)` | `-5` | Record pattern `Literal` |
| `evaluate(null)` trong ví dụ sealed | Ném `IllegalArgumentException("expr is required")` | `case null -> throw` |

**Tự đánh giá:** Bạn có thể giải thích từng case nhận những đầu vào nào, vì sao guard được kiểm tra sau khi khớp pattern, vị trí và ý nghĩa của `case null`, điều kiện để switch expression exhaustive, khi nào dùng `yield`, và vì sao sealed hierarchy giúp phát hiện nhánh thiếu.

## 13. Tài liệu chuẩn

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type patterns, guard `when`, `null`, dominance và exhaustiveness trong Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): đối sánh thành phần record, kể cả record pattern lồng nhau.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): nền tảng về type pattern và pattern variable.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): `switch` là biểu thức, mũi tên `->`, giá trị và `yield`.
- [Java Language Specification, Java SE 21 — Switch Expressions `15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): quy tắc chính thức của switch expression.
- [Java Language Specification, Java SE 21 — Switch Statements `14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): quy tắc nhãn case, matching, dominance và xử lý trong switch.

Nên thực hành trên **JDK 21 trở lên**, biên dịch lại với `--release 21`, chủ động tạo trường hợp lỗi biên dịch cho dominance/thiếu nhánh và bổ sung kiểm thử trước khi áp dụng vào dự án.
