# Ném NullPointerException khi thiếu null case trong Java Pattern Matching

Khi dùng `switch` với pattern matching, một trường hợp rất dễ gây nhầm lẫn là **giá trị đem vào `switch` bằng `null`**. Nhiều người cho rằng nhánh `default` sẽ nhận mọi giá trị không khớp pattern, kể cả `null`. Trong Java, suy luận đó **không đúng**: nếu selector của `switch` là `null` và khối `switch` không có nhãn `case null`, `switch` sẽ ném **`NullPointerException` (NPE)** trước khi chọn một nhánh xử lý thông thường.

Từ **Java 21**, tính năng pattern matching cho `switch` đã chính thức hỗ trợ `case null`, giúp xử lý `null` ngay trong `switch`. Điểm quan trọng cần nhớ:

- `null instanceof String text` trả về **`false`**; type pattern của `instanceof` không khớp `null`.
- `switch (value)` với `value == null` **ném `NullPointerException`** nếu không có `case null`, kể cả khi có `default` hay các type pattern khác.
- `case null` xử lý riêng giá trị `null`. Nó không phải type pattern và không khai báo pattern variable.
- `default` xử lý các giá trị **khác `null`** mà không khớp nhánh nào trước đó, theo cách xử lý `null` mặc định của `switch`.

Bài này tập trung vào lý do NPE xảy ra, vai trò của `case null` và cách chọn giải pháp phù hợp trong Java 17 và Java 21+.

## 1. Hiện tượng: có `default` mà vẫn ném NPE

Xét một `switch expression` sử dụng type pattern, hợp lệ trong **Java 21+**:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
```

Các lệnh gọi cho kết quả:

| Đầu vào | Kết quả |
| --- | --- |
| `describe("Java")` | `"String: Java"` |
| `describe(42)` | `"Integer: 42"` |
| `describe(3.14)` | `"Other"` |
| `describe(null)` | **Ném `NullPointerException`** |

`default` nhận `3.14` vì `Double` không khớp các pattern `String` hoặc `Integer`. Nhưng `null` được xử lý theo **quy tắc riêng của selector `switch`**. Nếu thiếu `case null`, Java ném NPE; nó không tự chuyển `null` sang `default`.

Đây là hành vi của cả **`switch statement`** lẫn **`switch expression`**. Không nên hiểu NPE là lỗi đặc biệt do nhánh `default` hoặc một pattern variable gây ra. Nó bắt nguồn từ việc selector của `switch` có giá trị `null` mà không có nhánh dành cho giá trị ấy.

## 2. Cơ chế: selector, pattern và `case null`

Cú pháp chung:

```java
switch (selectorExpression) {
    case SomeType variable -> ...;
    case null -> ...;
    default -> ...;
}
```

Các bước logic:

1. Java **đánh giá `selectorExpression`** để lấy giá trị cần chuyển nhánh. Đây có thể là biến, lời gọi phương thức hoặc biểu thức trả về kiểu được `switch` hỗ trợ.
2. Nếu việc đánh giá selector tự nó ném exception, `switch` dừng theo exception đó. Ví dụ, `lookup().getName()` có thể gây NPE ngay trong lúc tính selector nếu `lookup()` là `null`.
3. Nếu selector được đánh giá bình thường thành **`null`**, Java chỉ xử lý nó bằng một nhãn `case null` nếu khối `switch` có nhãn này. **Khi thiếu nhãn `case null`, NPE được ném**.
4. Nếu selector là **giá trị khác `null`**, Java xác định nhánh phù hợp: kiểm tra các hằng số/pattern/guard được khai báo hợp lệ rồi chạy nhánh được chọn; `default` là phương án còn lại nếu áp dụng.
5. Với `case SomeType variable`, **pattern variable** chỉ được binding khi type pattern khớp. Một giá trị `null` không khớp type pattern và không được binding vào biến ấy.

Mô hình:

```text
Đánh giá selectorExpression
         |
         +-- Phép đánh giá ném exception --------> Truyền exception
         |
         v
      Giá trị
         |
         +-- null ---- có case null? -- có -----> Chạy case null
         |                          |
         |                          +-- không --> NullPointerException
         |
         +-- khác null -------------------------> Kiểm tra case/pattern/guard
                                                     |
                                                     +--> Nhánh phù hợp
                                                     +--> default nếu cần
```

Lưu ý phân biệt **lỗi khi đánh giá selector** với **NPE do selector là `null` và thiếu `case null`**. Hai lỗi có thể cùng mang tên `NullPointerException` nhưng phát sinh ở những vị trí khác nhau.

## 3. Cách sửa trực tiếp: thêm `case null` (Java 21+)

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Null input";
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
```

Lúc này:

- `describe(null)` trả về `"Null input"`, không ném NPE.
- `describe("Java")` trả về `"String: Java"`.
- `describe(42)` trả về `"Integer: 42"`.
- `describe(3.14)` trả về `"Other"`.

`case null` là một **null case label**, không phải `case Null` hay một kiểu class tên `Null`. Không có cú pháp `case null n` để khai báo một biến pattern cho `null`.

### Ví dụ Java 21+ chạy đầy đủ

Lưu thành **`NullCaseDemo.java`**:

```java
public class NullCaseDemo {
    static String withoutNull(Object value) {
        return switch (value) {
            case String text -> "text: " + text;
            case Integer number -> "integer: " + number;
            default -> "other";
        };
    }

    static String withNull(Object value) {
        return switch (value) {
            case null -> "null input";
            case String text when text.isBlank() -> "blank string";
            case String text -> "text: " + text;
            case Integer number -> "integer: " + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(withoutNull("Java"));
        System.out.println(withoutNull(42));
        System.out.println(withoutNull(3.14));

        try {
            System.out.println(withoutNull(null));
        } catch (NullPointerException ex) {
            System.out.println("withoutNull(null): NullPointerException");
        }

        System.out.println(withNull(null));
        System.out.println(withNull(" "));
        System.out.println(withNull("Java"));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac NullCaseDemo.java
java NullCaseDemo
```

Kết quả chính xác:

```text
text: Java
integer: 42
other
withoutNull(null): NullPointerException
null input
blank string
text: Java
```

Trong `withoutNull`, `default` vẫn tồn tại nhưng `null` gây NPE. Khối `try/catch` bắt NPE để ví dụ có thể chạy hết; trong ứng dụng thực tế nên quyết định rõ `null` là đầu vào hợp lệ hay là lỗi. Trong `withNull`, `case null` tiếp nhận `null`; các pattern và guard dành cho `String` không phải chạy với `null`.

Nếu loại bỏ `try/catch` rồi gọi `withoutNull(null)`, chương trình sẽ kết thúc bất thường tại lời gọi đó và in stack trace (nội dung stack trace phụ thuộc môi trường thực thi). NPE không phải giá trị `String` trả về từ phương thức.

## 4. Vì sao `default` không thay thế `case null`?

Có hai khái niệm khác nhau:

- **Không khớp các nhãn thông thường:** selector là một giá trị không phải `null`, chẳng hạn `Double`, không phù hợp với những nhánh `String` hay `Integer`. `default` có thể nhận trường hợp này.
- **Selector là `null`:** Java áp dụng xử lý `null` đặc biệt cho `switch`. Thiếu `case null` là NPE, dù về mặt suy luận thông thường có thể nghĩ `null` “không phải String và cũng không phải Integer”.

Điều này duy trì hành vi quen thuộc của `switch` từ trước Java 21. Việc bổ sung pattern matching không có nghĩa Java tự động thay đổi `default` để nhận `null`.

Ngay cả một type pattern rất rộng cũng không thay thế được `case null`:

```java
static String broad(Object value) {
    return switch (value) {
        case Object object -> "non-null object";
    };
}
```

Trong Java 21+, đây là ví dụ `switch expression` dùng pattern bao trùm kiểu `Object` cho các đối tượng khác `null`. **`broad(null)` vẫn ném NPE** vì không có `case null`. Type pattern `Object object` không match `null`, và `Object` không biến `null` thành một đối tượng có thể gắn vào biến `object`.

Vì vậy, khi review `switch` nhận đầu vào kiểu tham chiếu, hãy kiểm tra **`case null`** một cách tường minh nếu `null` là giá trị có thể tới đó.

## 5. Đối chiếu với `instanceof`: `null` thường chỉ cho `false`

`instanceof` hoạt động khác `switch` đối với `null`:

```java
Object value = null;
boolean matched = value instanceof String text; // false
```

Khi target `value` là `null`, type pattern `String text` không khớp, biểu thức `instanceof` trả về `false`. Không có binding cho `text`; không thể dùng `text` trong nhánh thất bại. Tuy nhiên, phép thử `instanceof` này **không tự ném NPE**.

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("no String match");
}
```

Với `value == null`, đầu ra là `no String match`. Trái lại, thay điều kiện bằng `switch (value)` mà không thêm `case null` có thể khiến chương trình ném NPE trước khi vào `default`.

### Ví dụ Java 17+ chạy đầy đủ

Lưu thành **`NullComparisonDemo.java`**:

```java
public class NullComparisonDemo {
    static String byIf(Object value) {
        if (value instanceof String text) {
            return "length=" + text.length();
        }
        return "no String match";
    }

    static String byOldSwitch(String value) {
        return switch (value) {
            case "yes" -> "accepted";
            default -> "different";
        };
    }

    public static void main(String[] args) {
        System.out.println(byIf(null));
        System.out.println(byIf("Hi"));

        try {
            System.out.println(byOldSwitch(null));
        } catch (NullPointerException ex) {
            System.out.println("old switch: NullPointerException");
        }
    }
}
```

Chạy trên **Java 17 trở lên**:

```bash
javac NullComparisonDemo.java
java NullComparisonDemo
```

Đầu ra chính xác:

```text
no String match
length=2
old switch: NullPointerException
```

`byOldSwitch` chỉ dùng hằng chuỗi và `default`, nên ví dụ này chạy được trên Java 17. Khi selector là `null`, `default` vẫn không cứu được: NPE là hành vi có từ `switch` trước Java 21, không chỉ xảy ra với pattern matching.

## 6. `when` guard không có tác dụng xử lý `null` thay `case null`

Java 21 hỗ trợ **guard** cho pattern trong `switch`:

```java
return switch (value) {
    case String text when text.isBlank() -> "blank";
    case String text -> "not blank";
    default -> "other";
};
```

`when text.isBlank()` chỉ được xét **sau khi** type pattern `String text` khớp. Nếu selector là `null` và không có `case null`, cả pattern lẫn guard không trở thành một phép kiểm tra mặc định cho `null`: `switch` ném NPE theo quy tắc đã nêu.

Cách đúng khi muốn cả xử lý null lẫn kiểm tra chuỗi:

```java
return switch (value) {
    case null -> "null";
    case String text when text.isBlank() -> "blank";
    case String text -> "not blank";
    default -> "other";
};
```

Dù `text.isBlank()` không dùng được nếu `text` chưa được binding, ví dụ đã đặt nó ở vị trí an toàn: guard chỉ được đánh giá khi pattern `String text` khớp với một chuỗi khác `null`. Không cần viết guard `text != null && text.isBlank()` chỉ để phòng null trong trường hợp này.

Cũng không nên viết `case String text when text == null -> ...` với kỳ vọng bắt `null`: type pattern không match `null` ngay từ đầu, nên guard đó không phải cách xử lý selector `null`.

## 7. `case null, default` khi muốn gom hai tình huống (Java 21+)

Nếu chính sách xử lý của ứng dụng **giống nhau** cho `null` và các giá trị không khớp các nhánh khác, Java 21 cho phép ghép nhãn:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "string: " + text;
        case null, default -> "null or other";
    };
}
```

- `classify("ok")` → `"string: ok"`.
- `classify(null)` → `"null or other"`.
- `classify(12)` → `"null or other"`.

`case null, default` là trường hợp ghép nhãn hợp lệ và nên đặt cuối khối. Đây là cách diễn đạt ngắn gọn khi null và kiểu không hỗ trợ có cùng ý nghĩa nghiệp vụ.

Không thể ghép `null` tùy tiện với một type pattern khác:

```java
// KHÔNG HỢP LỆ (Java 21):
// case null, String text -> "string or null";
```

Lý do: một type pattern khai báo biến `text` chỉ khi match; `null` không tạo ra binding đó. Cú pháp cho phép ghép `null` với `default`, không ghép với `String text`. Nếu hai trường hợp cần xử lý khác nhau, hãy viết các nhánh riêng.

## 8. Phải phân biệt lỗi `null` ở selector và lỗi trong thân nhánh

Không phải NPE nào xuất hiện gần `switch` cũng bắt nguồn từ việc thiếu `case null`.

### Trường hợp A — Selector `null`, thiếu `case null`

```java
Object input = null;
String output = switch (input) {
    case String text -> text;
    default -> "other";
};
// Ném NullPointerException trước khi chọn default.
```

Đây là đúng lỗi đang xét.

### Trường hợp B — Selector expression tự ném NPE

```java
String input = null;
int length = input.length(); // Ném NPE trước khi có switch.

// Tương tự: switch (input.length()) { ... } không thể nhận được giá trị selector.
```

Thêm `case null` vào một `switch` khác không sửa được phép gọi `input.length()` khi `input` là `null`. Cần kiểm tra giá trị trước khi truy cập.

### Trường hợp C — Đã chọn nhánh, nhưng mã trong nhánh ném NPE

```java
record Person(String name) {}

Object input = new Person(null);
String result = switch (input) {
    case Person person -> person.name().toUpperCase();
    case null -> "no person";
    default -> "other";
};
// Ném NPE tại person.name().toUpperCase().
```

Đây là **đoạn minh họa Java 21+**, không phải lớp chạy độc lập. Pattern `Person person` khớp vì `input` là một `Person` khác `null`. Nhưng **thành phần `name` bên trong record** lại là `null`; gọi `toUpperCase()` trên giá trị đó gây NPE. `case null` chỉ bắt **selector `input`**, không tự xử lý mọi field `null` trong object.

### Trường hợp D — Unboxing giá trị `null`

```java
Integer boxed = null;
// int count = boxed; // Ném NPE nếu thực hiện unboxing.
```

Lỗi này là do unboxing, không phải do nhãn case. Nếu code thực tế có nhiều bước, hãy xác định NPE sinh ra ở bước nào thay vì thêm `case null` một cách máy móc.

## 9. Ba chiến lược thiết kế cho đầu vào có thể là `null`

### A. `null` là trạng thái hợp lệ → xử lý trong `switch`

Ví dụ một hàm phân loại dữ liệu đầu vào thực sự chấp nhận `null`:

```java
static String label(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text";
        case Integer number -> "number";
        default -> "unsupported";
    };
}
```

Chọn cách này khi null có **ý nghĩa nghiệp vụ riêng**, chẳng hạn “chưa có dữ liệu”.

### B. `null` không hợp lệ → kiểm tra ở ranh giới

```java
import java.util.Objects;

static String label(Object input) {
    Objects.requireNonNull(input, "input must not be null");

    return switch (input) {
        case String text -> "text";
        case Integer number -> "number";
        default -> "unsupported";
    };
}
```

`Objects.requireNonNull` cố ý ném `NullPointerException` kèm thông điệp rõ ràng khi `input` bằng `null`. Đây là cách thể hiện **hợp đồng đầu vào**: phương thức không chấp nhận null. Nó không loại bỏ NPE mà làm cho việc từ chối đầu vào rõ ràng hơn. Trong API khác, có thể dùng `IllegalArgumentException` nếu đó là quy ước hợp đồng đã chọn.

### C. Cần giữ tương thích Java 17 → kiểm tra trước `switch`

```java
static String label(String input) {
    if (input == null) {
        return "missing";
    }

    return switch (input) {
        case "yes" -> "accepted";
        case "no" -> "rejected";
        default -> "unknown";
    };
}
```

Đoạn mã chạy từ Java 17; không cần `case null` (vốn chưa là tính năng ổn định của Java 17). Nếu dự án biên dịch với `--release 17`, không thể dùng cú pháp `case null`/type pattern trong `switch` như Java 21.

Cần chọn chiến lược theo yêu cầu thực tế: cho phép null và phân loại nó, từ chối null tại ranh giới, hay xử lý trước `switch` vì phiên bản Java. Không nên bắt mọi NPE bằng một `catch (NullPointerException)` rộng để giả lập `case null`; cách đó dễ che khuất lỗi lập trình thật trong selector hoặc thân nhánh.

## 10. Tương thích kiểu và tính đầy đủ của `switch`

**Type pattern chỉ khớp các giá trị phù hợp kiểu và khác `null`.** Ví dụ `case CharSequence cs` có thể nhận `String` và `StringBuilder` vì chúng triển khai `CharSequence`, nhưng không nhận `null`. `case Object o` cũng không nhận `null`.

**`default` và exhaustive switch** là chủ đề khác. Một `switch expression` phải bao phủ các giá trị thông thường theo quy tắc tính đầy đủ của Java, nhưng tính đầy đủ ấy không có nghĩa là `null` tự nhiên được xử lý bởi `default`. Chẳng hạn:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "String";
        default -> "Other";
    };
}
```

Biểu thức này biên dịch trong Java 21+ vì có `default`, song `classify(null)` vẫn ném NPE. Muốn xử lý selector `null`, cần thêm `case null` hoặc chủ động ngăn `null` trước khi đánh giá `switch`.

Ngược lại, `case null` đơn lẻ cũng **không thay thế** việc bao phủ những trường hợp còn lại:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Null";
        case String text -> "String";
        default -> "Other";
    };
}
```

Ở đây `case null` xử lý riêng null, `case String text` xử lý chuỗi, và `default` xử lý các đối tượng khác. Ba nhánh có mục đích tách bạch.

## 11. Các lỗi phổ biến cần nhận diện

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`default` bắt mọi đầu vào, gồm `null`.” | Thiếu `case null` thì selector `null` gây NPE; `default` không xử lý thay. |
| “`case Object object` chắc chắn nhận cả `null`.” | Type pattern chỉ match đối tượng phù hợp kiểu và khác `null`. |
| “`instanceof` và `switch` có hành vi như nhau với `null`.” | `instanceof` type pattern trả về `false`; `switch` thiếu null case ném NPE. |
| “Guard `when` kiểm tra `text == null` sẽ bắt null selector.” | Guard chỉ chạy sau khi type pattern đã khớp; nó không bắt giá trị `null` của selector. |
| “Có `case null` rồi thì không còn NPE nào.” | Selector expression, thân nhánh, dereference hoặc unboxing vẫn có thể ném NPE. |
| “Ghép `case null, String text` sẽ hợp lệ.” | Java 21 cho phép ghép `case null, default`; không ghép null với type pattern. |
| “Nếu `switch` exhaustive thì chắc chắn xử lý null.” | Exhaustiveness đối với các giá trị được xét không đồng nghĩa với xử lý selector null. |
| “`case null` là cú pháp của Java 17.” | Đây là tính năng `switch` được chuẩn hóa trong Java 21; Java 17 nên kiểm tra null trước `switch`. |

## 12. Checklist khi review hoặc debug

Khi thấy `NullPointerException` gần một `switch`:

1. **Xác định selector**: biểu thức nằm giữa `switch ( ... )` thực sự trả về gì? Nó có thể nhận `null` không?
2. **Kiểm tra chỗ phát sinh NPE**: NPE xảy ra lúc đánh giá selector, tại đầu `switch` do thiếu `case null`, hay trong mã của nhánh đã chọn?
3. **Đọc các nhãn case**: có `case null` hay chỉ có `default`? Có type pattern rộng bị nhầm là xử lý null không?
4. **Xác định Java target version**: Java 21+ có thể dùng `case null`; Java 17 nên xử lý null trước `switch`.
5. **Quyết định chính sách null**: xem null là trạng thái hợp lệ cần nhánh riêng hay là lỗi đầu vào cần thông báo rõ.
6. **Kiểm tra lại các nhánh khác**: thêm `case null` không làm thay đổi logic phân loại giá trị khác `null`; vẫn cần pattern/`default` phù hợp, tránh thứ tự case bị che khuất.
7. **Chạy ít nhất ba nhóm đầu vào**: một giá trị khớp pattern, một giá trị khác `null` không khớp, và một giá trị `null`. Khi có guard `when`, thêm đầu vào khớp type pattern nhưng guard trả về `false`.

Đặc biệt với dữ liệu lấy từ JSON, database, API hoặc những phương thức có thể trả về `null`, kiểm thử nhánh null phải là một phần của kiểm tra hành vi chứ không chỉ kiểm tra cú pháp biên dịch.

## 13. Ghi nhớ qua ba phép thử

```text
null instanceof String text
    -> false; không binding text.

switch (null) { case String s -> ...; default -> ...; }
    -> NullPointerException trong Java 21+; default không bắt null.

switch (null) { case null -> ...; case String s -> ...; default -> ...; }
    -> chọn case null trong Java 21+.
```

**Quy tắc cốt lõi:** Java duy trì hành vi `switch` ném NPE khi selector là `null` **nếu không khai báo `case null`**. Type pattern là phép thử kiểu của đối tượng khác `null`; `default` xử lý các giá trị thông thường không khớp. Muốn xử lý `null` như một trường hợp có chủ đích, hãy dùng `case null` trong Java 21+ hoặc kiểm tra ở trước `switch` khi cần hỗ trợ Java 17.

### Tài liệu tham khảo

- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), mục **Null case Labels**.
- [Oracle Java SE 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html), mốc chuẩn hóa pattern matching cho `switch` trong Java 21.
