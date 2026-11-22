# Pattern variable trong `switch rule` (Java 21+)

## 1. `switch rule` và pattern variable là gì?

Từ **Java 21**, pattern matching cho `switch` là tính năng chính thức (JEP 441). Một `case` có thể kiểm tra kiểu của đối tượng và khai báo ngay một **pattern variable**; khi nhãn `case` khớp, biến được khởi tạo và có thể được dùng trong phần xử lý tương ứng.

```java
Object value = "hello";
switch (value) {
    case String text -> System.out.println(text.length());
    default -> System.out.println("Not a string");
}
```

Đoạn này in `5`. Cụm `String text` là **type pattern**: `String` là kiểu cần khớp, còn `text` là biến mới được khai báo. Nếu `value` thực sự tham chiếu tới một `String`, `text` giữ chính tham chiếu ấy với kiểu tĩnh `String`. Không cần ép kiểu `(String) value` trong thân nhánh.

Một dòng `case String text -> ...` là một **switch rule**: nhãn `case` cộng dấu mũi tên `->` và phần thân ở bên phải. Khi đã chọn được một rule, Java chạy đúng phần tương ứng rồi kết thúc nhánh; không có cơ chế *fall-through* tự động từ rule này sang rule tiếp theo như trong dạng `case ...:` cổ điển.

`switch` dùng rule mũi tên có thể là **switch statement** (thực hiện lệnh, chẳng hạn in thông tin) hoặc **switch expression** (tạo một giá trị). Cả hai có thể dùng pattern variable trong `case`.

**Phân biệt phiên bản:** pattern matching cho `instanceof` chính thức từ Java 16, nhưng pattern matching cho `switch` chỉ chính thức từ **Java 21**. Trên Java 17, tính năng `switch` pattern còn ở chế độ *preview* với yêu cầu bật preview; các ví dụ trong bài này là cú pháp Java 21+ và không biên dịch mặc định bằng JDK 17.

## 2. Pattern variable được tạo và khởi tạo khi nào?

Xét một switch expression có đối số kiểu `Object`:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "String length = " + s.length();
        case Integer n -> "Integer value = " + n;
        default -> "Other";
    };
}
```

Ở `case String s`, Java kiểm tra xem giá trị tại thời điểm chạy có khớp kiểu `String` hay không. Nếu khớp, Java khởi tạo biến `s` có kiểu `String` trước khi thực thi biểu thức ở bên phải `->`. Với `case Integer n`, biến `n` có kiểu `Integer` chỉ được khởi tạo cho rule đó. `String` và `Integer` là hai đường khớp khác nhau; chương trình không phải tự cast biến `value`.

Nhãn `case` được xét theo thứ tự và Java chọn nhãn phù hợp đầu tiên, có xét cả điều kiện `when` nếu nhãn đó có guard. Vì vậy thứ tự giữa các kiểu có quan hệ cha–con hoặc giữa guarded và unguarded pattern cần được thiết kế cẩn thận.

**`null` cần xử lý riêng.** Với selector là `Object`, có thể viết:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "text: " + s;
        default -> "other";
    };
}
```

`case String s` không tự bắt `null`. Nếu selector là `null` mà không có nhãn xử lý `null`, switch thông thường ném `NullPointerException`, kể cả khi có `default`. Không được hiểu `default` là một phép thử `instanceof` hoặc là nhánh tự động khớp `null`.

## 3. Phạm vi của pattern variable trong một switch rule

Theo **JLS 21**, phạm vi (*scope*) của biến khai báo trong nhãn `case` bao gồm:

1. **Biểu thức `when` (guard) của chính nhãn ấy**, khi có guard.
2. **Biểu thức, khối lệnh hoặc `throw` statement bên phải `->`** của chính rule ấy.

Biến này **không** có phạm vi trong rule khác, trong `default`, hoặc ở sau toàn bộ `switch` chỉ vì cùng nằm trong phương thức. Đây là điểm cốt lõi của bài.

### 3.1. Bên phải `->` là một biểu thức

```java
static String label(Object value) {
    return switch (value) {
        case String text -> "Length " + text.length();
        case Integer number -> "Number " + number;
        default -> "Unknown";
    };
}
```

`text` dùng được trong biểu thức `"Length " + text.length()` vì rule này chỉ được chọn sau khi pattern `String text` khớp. Ở rule `case Integer number`, chỉ có `number` được khai báo bởi nhãn đó; không thể tham chiếu biến `text` của nhánh trước.

### 3.2. Bên phải `->` là một khối lệnh `{ ... }`

Nếu cần nhiều lệnh, dùng block và truy cập biến pattern xuyên suốt phần block thuộc rule:

```java
static void printStringInfo(Object value) {
    switch (value) {
        case String s -> {
            int length = s.length();
            String upper = s.toUpperCase();
            System.out.println(upper + " / " + length);
        }
        default -> System.out.println("Not a String");
    }
}
```

Ở ví dụ này, `s` được dùng hợp lệ bởi cả `s.length()` lẫn `s.toUpperCase()` trong cùng block. Biến cục bộ `length`, `upper` cũng có phạm vi theo block của Java bình thường. Không thể dùng `s`, `length` hay `upper` ở rule `default` hoặc sau block của rule.

Dấu `{}` tạo khối lệnh, nhưng bản chất điều kiện để dùng `s` vẫn là rule tương ứng **chắc chắn đã khớp pattern**.

### 3.3. Bên phải `->` là một `throw` statement

Một rule có thể ném ngoại lệ trực tiếp và vẫn dùng biến pattern trong biểu thức tạo ngoại lệ:

```java
static int nonEmptyLength(Object value) {
    return switch (value) {
        case String s when s.isEmpty() ->
                throw new IllegalArgumentException("Empty String: " + s);
        case String s -> s.length();
        case null -> 0;
        default -> -1;
    };
}
```

Ở rule đầu, `s` dùng được cả trong `when s.isEmpty()` lẫn thông điệp ngoại lệ `"Empty String: " + s`. Rule tiếp theo có **khai báo riêng** cũng tên `s` và xử lý các chuỗi khác. Nếu giá trị không phải `String`, không rule nào khai báo `s` được sử dụng.

Trong switch expression, phần bên phải rule có thể là một biểu thức trả giá trị, một block kết thúc bằng `yield`, hoặc một lệnh `throw` như ví dụ. `throw` không tạo ra giá trị bình thường; nó kết thúc đột ngột bằng ngoại lệ.

## 4. Pattern variable trong `when` guard

Một **guarded case label** có dạng:

```java
case String s when s.length() >= 5 -> "Long text"
```

Thứ tự xử lý là:

1. Kiểm tra giá trị có khớp type pattern `String s` không.
2. Nếu khớp, khởi tạo `s` rồi đánh giá điều kiện `when s.length() >= 5`.
3. Chỉ khi guard trả `true` mới chạy phần bên phải mũi tên.
4. Nếu không khớp pattern hoặc guard sai, thử nhãn `case` tiếp theo.

Vì guard được đánh giá **sau khi khớp**, có thể gọi phương thức trên `s` mà không cast.

```java
static String sizeLabel(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "Blank";
        case String s when s.length() >= 5 -> "Long: " + s;
        case String s -> "Short: " + s;
        case null -> "Null";
        default -> "Not text";
    };
}
```

Ba nhãn `case String s` **có thể dùng cùng tên `s`** vì mỗi biến chỉ thuộc phạm vi của rule chứa khai báo của nó; biến ở rule thứ nhất không truyền sang rule thứ hai. Đây không phải một biến được gán lại trong nhiều nhánh.

Trong ví dụ, `case String s -> ...` **phải nằm sau** các nhãn `case String s when ...`: nhãn `String` không guard bắt tất cả chuỗi còn lại và sẽ *dominate* một nhãn `String` xuất hiện ở phía sau. Khi đó một nhãn bị che hoàn toàn có thể gây lỗi biên dịch.

**Lưu ý về `when`:** đây là cú pháp guard của Java 21, không phải `if` bên trong thân rule. Dùng `when` nếu điều kiện phụ quyết định có chọn nhãn `case` hay không; dùng `if` trong block khi điều kiện chỉ quyết định cách xử lý sau khi nhãn đã được chọn.

## 5. Chương trình Java 21+ hoàn chỉnh, biên dịch và chạy được

Lưu đúng tên tệp **`SwitchRulePatternDemo.java`**:

```java
public class SwitchRulePatternDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank text";
            case String s -> "text(" + s.length() + "): " + s.toUpperCase();
            case Integer n when n >= 0 -> "nonnegative int: " + n;
            case Integer n -> "negative int: " + n;
            default -> "other: " + value.getClass().getSimpleName();
        };
    }

    static int measure(Object value) {
        return switch (value) {
            case null -> 0;
            case String s -> {
                String trimmed = s.trim();
                yield trimmed.length();
            }
            case Number n -> n.intValue();
            default -> throw new IllegalArgumentException(
                    "Unsupported: " + value.getClass().getSimpleName());
        };
    }

    static void printType(Object value) {
        switch (value) {
            case null -> System.out.println("NULL");
            case String s -> System.out.println("STRING: " + s);
            case Number n -> {
                double twice = 2 * n.doubleValue();
                System.out.println("NUMBER x2: " + twice);
            }
            default -> System.out.println("OTHER");
        }
    }

    public static void main(String[] args) {
        System.out.println(describe(""));
        System.out.println(describe("Java"));
        System.out.println(describe(-3));
        System.out.println(describe(5));
        System.out.println(describe(true));

        System.out.println("measure(\" ab \"): " + measure(" ab "));
        System.out.println("measure(12.8): " + measure(12.8));
        System.out.println("measure(null): " + measure(null));

        printType("Hi");
        printType(2.5);
        printType(false);
    }
}
```

Dùng **JDK 21 trở lên**, từ thư mục chứa tệp:

```bash
javac SwitchRulePatternDemo.java
java SwitchRulePatternDemo
```

Đầu ra:

```text
blank text
text(4): JAVA
negative int: -3
nonnegative int: 5
other: Boolean
measure(" ab "): 2
measure(12.8): 12
measure(null): 0
STRING: Hi
NUMBER x2: 5.0
OTHER
```

**Phân tích từng nhóm:**

- `describe("")`: đối tượng khớp `String s`, guard `s.isBlank()` đúng, nên chọn `blank text`. `describe("Java")` không qua guard trống, chuyển sang rule `String s` tiếp theo; biến `s` của rule thứ hai là một biến khác và `s.length()` bằng 4.
- `describe(-3)` và `describe(5)`: cả hai là `Integer`, nhưng guard `n >= 0` quyết định chọn nhánh không âm hay nhánh `Integer` còn lại. Biến `n` thuộc phạm vi rule tương ứng.
- `describe(true)`: giá trị runtime là `Boolean`, không khớp `String` hay `Integer`; `default` dùng `value.getClass().getSimpleName()`, nhận `Boolean`. Nhánh `null` được xử lý trước nên tại đây `value` không phải `null`.
- `measure(" ab ")`: rule `String s` tạo biến cục bộ `trimmed` trong block rồi dùng **`yield`** để tạo kết quả 2 cho switch expression. `measure(12.8)` khớp `Number n` (giá trị runtime là `Double`), `n.intValue()` trả 12. `measure(null)` trả 0. Nếu kiểu khác không hỗ trợ, nhánh `default -> throw ...` ném ngoại lệ.
- `printType("Hi")`: switch **statement**, bên phải `->` chỉ thực hiện `println`; không cần `yield`. `printType(2.5)` vào block của `Number n`, nhân đôi được `5.0`; `false` vào `default`. Mỗi pattern variable chỉ tồn tại trong rule mà nó được khai báo.

Một nguyên tắc quan trọng: trong **switch expression**, khi RHS là block, dùng `yield` để cung cấp giá trị cho toàn bộ biểu thức `switch` (hoặc kết thúc bằng một ngoại lệ); không dùng `break` để trả giá trị. Trong **switch statement**, RHS có thể là một lệnh hoặc một block thông thường và không cần trả giá trị.

## 6. So sánh switch rule với nhóm nhãn dùng dấu `:`

Java có hai cách tổ chức phần thân switch:

**Switch rule (arrow):**

```java
switch (value) {
    case String s -> System.out.println("Text: " + s);
    case Integer i -> System.out.println("Int: " + i);
    default -> System.out.println("Other");
}
```

Mỗi rule có ranh giới xử lý riêng, **không tự rơi xuống** (*fall through*) rule tiếp theo. Biến `s` chỉ có ở phần xử lý của nhãn `String`; biến `i` chỉ có ở phần xử lý của nhãn `Integer`.

**Switch labeled statement group (colon):**

```java
switch (value) {
    case String s:
        System.out.println("Text: " + s);
        break;
    case Integer i:
        System.out.println("Int: " + i);
        break;
    default:
        System.out.println("Other");
}
```

Kiểu dùng `:` hình thành các nhóm lệnh nhãn `case`. Pattern variable có phạm vi trong nhóm lệnh tương ứng, và cấu trúc này có các quy định nghiêm ngặt nhằm tránh *fall through* vào một nhãn pattern khi biến chưa được khởi tạo. Để bài tập và code mới dễ kiểm soát, **ưu tiên rule `->`** khi không cần cú pháp nhóm lệnh cổ điển. Hai hình thức không nên trộn trong cùng một switch block.

## 7. `case` bị che (dominance) và quy tắc đặt thứ tự

Pattern thường có quan hệ kiểu cha–con. Nếu một nhãn xuất hiện trước khớp mọi giá trị mà nhãn sau có thể khớp, nhãn sau bị **dominated** và Java báo lỗi biên dịch.

Ví dụ **không biên dịch**:

```java
// Trong một switch(value), với value có kiểu Object:
// case CharSequence text -> System.out.println(text.length());
// case String s -> System.out.println(s.toUpperCase()); // Bị che
// default -> System.out.println("Other");
```

Vì mọi `String` đều là `CharSequence`, nhãn đầu đã bắt toàn bộ các chuỗi. Đổi thứ tự:

```java
// Hợp lệ trong switch(value):
// case String s -> System.out.println(s.toUpperCase());
// case CharSequence text -> System.out.println(text.length());
// default -> System.out.println("Other");
```

Một pattern không có guard (`case String s`) cũng có thể che các guarded case cùng kiểu đặt sau nó. Do đó thứ tự thường hợp lý là:

1. Kiểu con hoặc trường hợp chuyên biệt, các case hằng số nếu cần;
2. Các pattern cùng kiểu có guard `when`;
3. Pattern tổng quát hơn, không có guard;
4. `default` khi cần làm nhánh dự phòng.

Không được dựa vào việc “đến rule sau thì biến của rule trước vẫn còn” để viết logic: **mỗi rule độc lập về scope**, và switch rule không fall through.

## 8. Những lỗi phổ biến liên quan đến scope

### 8.1. Truy cập biến từ rule khác hoặc từ `default`

Đoạn sau là **minh họa lỗi**, không phải chương trình độc lập:

```java
switch (value) {
    case String s -> System.out.println(s.length());
    case Integer n -> {
        // System.out.println(s); // LỖI: s thuộc rule String
        System.out.println(n);
    }
    default -> {
        // System.out.println(s); // LỖI: s không có ở default
        System.out.println("Other");
    }
}
// System.out.println(s); // LỖI: biến của case không ra ngoài switch
```

Sau `switch`, nếu cần dùng một giá trị từ nhánh đã chọn, hãy **trả kết quả từ switch expression** rồi lưu vào một biến được khai báo bên ngoài:

```java
String result = switch (value) {
    case String s -> s.toUpperCase();
    case Integer n -> Integer.toString(n);
    case null -> "(null)";
    default -> "(other)";
};
System.out.println(result); // Hợp lệ; result là biến bên ngoài switch.
```

`result` không phải pattern variable; đó là một biến cục bộ nhận kết quả của toàn bộ switch expression.

### 8.2. Gộp `null` với pattern có biến trong cùng nhãn

Đây là mã **không biên dịch** trên Java 21:

```java
// KHÔNG HỢP LỆ:
// case null, String s -> System.out.println(s);
```

Không phải mọi nhãn gộp đều khởi tạo `s`; ở trường hợp `null` không có chuỗi để gán. Viết thành các rule riêng:

```java
case null -> System.out.println("null");
case String s -> System.out.println(s);
```

Đây là hai **nhãn trong một switch block**; hai dòng chỉ minh họa cú pháp nhãn, không phải một chương trình Java độc lập.

### 8.3. Dùng biến sai phía `when`

```java
case String s when s.length() > 3 -> s.toUpperCase();
```

Hợp lệ vì `s` đã được khai báo bởi pattern đứng trước `when`. Nhưng `when` không phải nơi để sử dụng một pattern variable khai báo ở **case khác**; không có phạm vi xuyên giữa các rule.

### 8.4. Thiếu tính bao phủ trong switch expression

Khi `switch` là **biểu thức**, mọi giá trị có thể xuất hiện phải được một nhánh xử lý (*exhaustive*). Với selector là `Object`, chỉ có `case String s` và `case Integer n` là chưa bao phủ mọi kiểu; cần `default` hoặc một tập nhãn đủ để bao phủ toàn bộ kiểu đầu vào. Một switch statement có pattern hoặc nhãn `null` cũng phải tuân thủ các quy định bao phủ của Java 21.

Một `default` trong `switch(value)` **không tự bắt `null`** như đã giải thích. Có thể dùng `case null -> ...` để xử lý riêng khi `value` có khả năng là `null`.

### 8.5. Dùng sai phiên bản JDK hoặc câu lệnh `yield`

- `case String s -> ...` và guard `when` trong `switch` là cú pháp chính thức từ **Java 21**, không phải cú pháp mặc định của JDK 17.
- Trong switch expression: block RHS muốn trả về giá trị thì dùng `yield value;`.
- Trong switch statement: rule mũi tên thực hiện hành động; không cần `yield`.
- Bên phải `->` có thể là biểu thức/lời gọi, block hoặc `throw` phù hợp ngữ cảnh; không dùng `break` để lấy giá trị của switch expression.

## 9. Bảng ghi nhớ phạm vi

| Vị trí | Có dùng được pattern variable `s` của `case String s` không? |
| --- | --- |
| Trong `when s.isBlank()` của **chính case đó** | **Có**, sau khi pattern khớp |
| Trong biểu thức sau `case String s ->` | **Có** |
| Trong block sau `case String s -> { ... }` | **Có** |
| Trong thông điệp ngoại lệ ở `case String s -> throw ...` | **Có** |
| Trong `case Integer n -> ...` khác | **Không** |
| Trong `default -> ...` | **Không** |
| Sau toàn bộ `switch` | **Không** |
| Một rule khác cũng viết `case String s` | **Có biến `s` mới của rule đó**, không phải biến cũ |

Để xác định đúng scope, hãy hỏi: **Biến được khai báo bởi nhãn nào, và vị trí đang xét có thuộc guard hoặc phần RHS của chính nhãn ấy không?**

## 10. Bài tập thực hành

1. Viết hàm `static String category(Object x)` bằng **switch expression** với các rule: `null` → `"null"`; `String s` có độ dài bằng 0 → `"empty"`; các chuỗi khác → `"text: " + s`; `Number n` → `"number: " + n`; còn lại → `"other"`. Dùng `when s.isEmpty()` cho trường hợp trống.
2. Với câu 1, thử khai báo cùng tên `s` ở hai rule `case String s`; giải thích vì sao không xung đột và tại sao mỗi `s` chỉ hợp lệ trong rule của nó.
3. Chuyển nhánh `case String s` thành block có hai lệnh: lấy `s.trim()` vào biến `trimmed`, rồi `yield trimmed.length()`. Giải thích vì sao một switch expression cần `yield` khi RHS là block.
4. Tạo một **switch statement** để in `"String length = ..."` hoặc `"Number = ..."`; dùng rule mũi tên và truy cập trực tiếp các pattern variable. Sau đó thử dùng biến ở `default` và giải thích lỗi phạm vi.
5. Viết hai nhãn `case CharSequence cs` và `case String s`. Thử đảo thứ tự để quan sát lỗi *dominated case*, rồi giải thích dựa trên quan hệ lớp/kiểu.
6. Viết `case String s when s.isBlank() -> throw new IllegalArgumentException(s);` trong một switch expression. Chỉ ra hai vị trí mà `s` hợp lệ và vì sao.

**Ghi nhớ:** Trong **switch rule**, biến pattern chỉ thuộc **guard `when` và phần bên phải `->` của chính nhãn `case` khai báo nó**. Khi chuyển sang rule khác, `default` hoặc sau `switch`, không thể tiếp tục dùng biến ấy. Java 21 kiểm tra cả phạm vi, thứ tự nhãn và tính bao phủ để tránh dùng biến chưa khớp.

## Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for `switch` Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21, §6.3.3 — Scope for Pattern Variables in `case` Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441).
- [Java Language Specification 21 — `switch` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
