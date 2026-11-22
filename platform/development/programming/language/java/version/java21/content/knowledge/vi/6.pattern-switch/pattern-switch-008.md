# Khai báo case null và case null, default

Trong Java 21, switch có thể xử lý rõ ràng giá trị `null` bằng nhãn `case null`. Khi muốn dùng chung một nhánh cho `null` và mọi giá trị chưa được các nhánh trước xử lý, có thể viết `case null, default`. Hai cách khai báo này giúp kiểm soát hành vi của pattern switch với đầu vào có thể rỗng, đồng thời tránh nhầm lẫn phổ biến rằng `default` tự động bắt cả `null`.

Các ví dụ trong bài dùng cú pháp switch và pattern matching đã được hoàn thiện trong Java 21. Không cần bật preview hoặc dùng `--enable-preview`.

## 1. Vì sao cần khai báo case null?

Với selector là một biểu thức kiểu tham chiếu, Java 21 không tự chuyển `null` thành một trường hợp của `default`. Nếu selector có giá trị `null` và switch không có nhãn `case null`, việc thực thi switch kết thúc bằng `NullPointerException`.

Điều này vẫn đúng khi switch có type pattern. Type pattern như `String text` chỉ khớp một đối tượng không null có kiểu phù hợp; nó không khớp `null`.

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Text: " + text;
        default -> "A different value";
    };
}
```

Với `describe("Java")`, nhánh `String text` được chọn. Với một số nguyên, nhánh `default` được chọn. Nhưng nếu gọi `describe(null)`, switch ném `NullPointerException`; nhánh `default` không được chạy.

Để xử lý đầu vào null, cần thêm nhãn `case null` hoặc kết hợp `null` với `default`. Quy tắc này áp dụng cho switch expression và switch statement có selector kiểu tham chiếu.

## 2. Dùng case null để xử lý riêng giá trị null

`case null` là nhãn dành riêng cho selector có giá trị `null`. Nó không khai báo pattern variable và không khớp các giá trị khác.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "No value was supplied";
        case String text -> "Text: " + text;
        case Integer number -> "Number: " + number;
        default -> "Unsupported type";
    };
}
```

Kết quả của các lời gọi:

```java
describe(null);       // No value was supplied
describe("Java 21");  // Text: Java 21
describe(21);         // Number: 21
describe(3.14);       // Unsupported type
```

Nhờ có `case null`, chương trình có thể phân biệt rõ ba tình huống: đầu vào không tồn tại, đầu vào thuộc kiểu được hỗ trợ và đầu vào thuộc kiểu khác. Điều này hữu ích khi `null` mang ý nghĩa nghiệp vụ riêng, chẳng hạn người dùng chưa nhập giá trị hoặc một trường dữ liệu chưa được thiết lập.

### Case null trong switch statement

`case null` cũng dùng được trong switch statement khi cần thực hiện hành động thay vì trả về giá trị:

```java
static void printValue(Object value) {
    switch (value) {
        case null -> System.out.println("Input is missing");
        case String text -> System.out.println("Text: " + text);
        default -> System.out.println("Other value");
    }
}
```

Mỗi nhánh dùng switch rule `->`, nên chỉ thực hiện phần thân của nhánh đã khớp. Nếu dùng switch statement với pattern label, switch phải bao phủ các trường hợp không-null theo quy tắc exhaustiveness của enhanced switch.

## 3. Dùng case null, default để gom null và các trường hợp còn lại

Khi ứng dụng không cần phân biệt `null` với những giá trị không khớp các nhánh đã khai báo, Java 21 cho phép kết hợp hai nhãn thành một nhánh:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Text: " + text;
        case null, default -> "Null or unsupported value";
    };
}
```

Nhãn `case null, default` khớp trong hai tình huống:

- Selector có giá trị `null`.
- Selector không phải `null` nhưng không khớp bất kỳ nhãn `case` nào đứng trước.

Ví dụ:

```java
describe("Java"); // Text: Java
describe(null);    // Null or unsupported value
describe(21);      // Null or unsupported value
```

Trong ví dụ, `String text` được ưu tiên xử lý trước. Các giá trị null và mọi giá trị còn lại đi vào cùng nhánh cuối. Đây là cách viết ngắn gọn khi hai tình huống có cùng cách xử lý, chẳng hạn trả về thông báo dự phòng, ghi log hoặc chọn một giá trị mặc định.

`case null, default` là một nhãn kết hợp, không phải hai nhánh riêng. Vì thế, phần thân của nó không thể biết selector là null hay chỉ đơn giản không khớp các nhánh trước. Nếu cần phân biệt hai tình huống, hãy khai báo `case null` riêng và thêm `default` riêng.

## 4. So sánh hai cách khai báo

| Tiêu chí | `case null` | `case null, default` |
|---|---|---|
| Khớp selector null | Có | Có |
| Khớp giá trị không-null chưa được xử lý | Không | Có |
| Có thể phân biệt null với giá trị khác | Có, khi đi cùng các nhánh khác | Không, vì dùng chung một thân nhánh |
| Phù hợp khi | Null cần cách xử lý riêng | Null và trường hợp còn lại có cùng cách xử lý |

Nếu cần ba cách xử lý khác nhau cho null, kiểu hợp lệ và kiểu không hỗ trợ, hãy viết:

```java
return switch (value) {
    case null -> "Missing";
    case String text -> "Text: " + text;
    default -> "Unsupported";
};
```

Nếu chỉ cần xử lý kiểu hợp lệ và gom phần còn lại vào cùng một nhánh, hãy viết:

```java
return switch (value) {
    case String text -> "Text: " + text;
    case null, default -> "Missing or unsupported";
};
```

## 5. Quy tắc cú pháp khi kết hợp null và default

Java 21 cho phép kết hợp `null` với `default` trong cùng một nhãn `case`:

```java
case null, default -> handleFallback();
```

Trong nhãn kết hợp này, `null` và `default` là hai phần duy nhất được phép đi cùng nhau. Không thể ghép `null` với một pattern hoặc hằng số case tùy ý:

```java
// Không hợp lệ trong Java 21:
case null, String text -> "Null or text";
case null, 0 -> "Null or zero";
```

Nếu cần xử lý null và một kiểu cụ thể bằng hai hành vi khác nhau, hãy tách chúng thành hai nhãn:

```java
return switch (value) {
    case null -> "Missing";
    case String text -> "Text: " + text;
    default -> "Other";
};
```

`default` là nhánh dự phòng cho các giá trị không-null chưa khớp nhãn trước. Vì nó bao phủ mọi trường hợp còn lại, hãy đặt `default` hoặc `case null, default` sau các nhánh cụ thể. Đặt nhãn bao phủ toàn bộ ở trước sẽ làm những nhãn sau không thể được chọn và có thể gây lỗi dominance khi biên dịch.

## 6. Case null và yêu cầu exhaustive của switch

Switch expression phải exhaustive, nghĩa là phải bao phủ các giá trị không-null có thể có theo kiểu selector. Enhanced switch statement, bao gồm switch statement có pattern label hoặc nhãn `null`, cũng phải exhaustive. Tuy nhiên, exhaustiveness không tự bao gồm giá trị null: việc bao phủ các giá trị không-null và việc xử lý null là hai vấn đề riêng.

Ví dụ sau chưa exhaustive nếu selector có kiểu `Object`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Missing";
        case String text -> "Text: " + text;
        // Thiếu nhánh cho các giá trị không-null khác.
    };
}
```

Có thể hoàn thiện bằng `default`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Missing";
        case String text -> "Text: " + text;
        default -> "Other";
    };
}
```

Hoặc dùng nhãn kết hợp nếu null và các giá trị không hỗ trợ cùng một kết quả:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Text: " + text;
        case null, default -> "Missing or other";
    };
}
```

Với sealed hierarchy, compiler có thể chứng minh switch đã bao phủ tất cả kiểu con không-null mà không cần `default`. Dù vậy, nếu selector có thể là null thì vẫn phải khai báo `case null` riêng, hoặc kết hợp null với default nếu phù hợp. Không nên dựa vào việc switch exhaustive để giả định null sẽ tự động được xử lý.

## 7. Phân biệt xử lý null trong switch và kiểm tra null trước switch

Có hai cách phổ biến để xác định hành vi khi đầu vào null.

**Xử lý ngay trong switch:** dùng `case null` hoặc `case null, default` khi null là một trường hợp mà logic switch cần phân loại.

```java
static String normalize(Object value) {
    return switch (value) {
        case null -> "";
        case String text -> text.trim();
        default -> value.toString();
    };
}
```

**Từ chối null trước switch:** dùng `Objects.requireNonNull` khi null vi phạm hợp đồng của phương thức và cần dừng xử lý ngay:

```java
import java.util.Objects;

static String normalize(Object value) {
    Objects.requireNonNull(value, "value must not be null");

    return switch (value) {
        case String text -> text.trim();
        default -> value.toString();
    };
}
```

Ở cách thứ hai, exception được ném tại điểm xác thực đầu vào với thông điệp rõ ràng. Không cần thêm `case null` vì phương thức đã chủ động từ chối giá trị này trước khi thực hiện switch.

Chọn cách nào phụ thuộc vào hợp đồng API. Nếu null là dữ liệu hợp lệ cần chuyển thành kết quả hoặc trạng thái riêng, hãy xử lý bằng `case null`. Nếu null là lỗi gọi phương thức, hãy xác thực trước switch để lỗi xuất hiện ngay tại ranh giới đầu vào.

## 8. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Switch ném `NullPointerException` dù đã có `default` | `default` không khớp selector null | Thêm `case null` hoặc dùng `case null, default` |
| Nhánh `case String text` không xử lý null | Type pattern không khớp giá trị null | Thêm nhãn null riêng nếu cần |
| Không phân biệt được null và kiểu không hỗ trợ | Đã gộp cả hai vào `case null, default` | Tách `case null` và `default` thành hai nhánh |
| Lỗi cú pháp khi viết `case null, String text` | Null chỉ được kết hợp với default trong nhãn kết hợp | Viết nhãn null riêng và nhãn pattern riêng |
| Lỗi dominance | `default` hoặc `case null, default` đứng trước nhãn cụ thể | Đưa các nhãn cụ thể lên trước nhánh dự phòng |
| Switch expression không exhaustive | Đã xử lý null nhưng chưa bao phủ giá trị không-null khác | Thêm `default` hoặc liệt kê đủ các kiểu con được phép |

## 9. Checklist khi thiết kế nhánh null

Trước khi hoàn thiện switch có selector kiểu tham chiếu, hãy tự kiểm tra:

1. Selector có thể nhận null theo hợp đồng dữ liệu hay không?
2. Null là một trường hợp nghiệp vụ cần xử lý riêng hay là đầu vào không hợp lệ?
3. Nếu null hợp lệ, nhánh null có cần kết quả khác với giá trị không khớp hay không?
4. Nếu hai trường hợp có cùng hành vi, `case null, default` có làm mã dễ đọc hơn không?
5. Các nhãn cụ thể đã đứng trước nhánh dự phòng chưa?
6. Switch expression hoặc enhanced switch statement đã exhaustive cho các giá trị không-null chưa?
7. Các kiểm thử đã bao gồm selector null, giá trị khớp từng pattern và giá trị rơi vào nhánh dự phòng chưa?

## Kết luận

Trong Java 21, `case null` xử lý riêng selector null, còn `case null, default` gom null với mọi giá trị chưa được xử lý vào cùng một nhánh. `default` đứng riêng không bao giờ thay thế cho xử lý null. Hãy chọn cách khai báo theo hợp đồng dữ liệu, đặt nhánh cụ thể trước nhánh dự phòng và kiểm tra exhaustiveness cho toàn bộ giá trị không-null.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 21 — The switch Statement (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
