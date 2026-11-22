# Chuyển chuỗi instanceof hoặc if-else sang pattern switch có kiểm soát

Khi một phương thức kiểm tra cùng một giá trị qua nhiều nhánh `instanceof`, mã nguồn thường lặp lại điều kiện kiểu và các phép ép kiểu. Pattern switch của Java 21 cho phép gom những nhánh này vào một `switch`, đồng thời khai báo pattern variable ngay tại từng nhánh.

Việc chuyển đổi cần giữ nguyên thứ tự ưu tiên, điều kiện phụ, cách xử lý `null` và số lần đánh giá biểu thức. Một chuỗi `if-else` bất kỳ không phải lúc nào cũng có thể thay bằng `switch` một cách cơ học. Bài này tập trung vào cách nhận diện trường hợp phù hợp, chuyển từng nhánh và kiểm tra lại ngữ nghĩa sau chuyển đổi.

Pattern matching for `switch` là tính năng chính thức từ Java 21. Các ví dụ sử dụng cú pháp `when` của Java 21 và không cần bật preview feature.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện chuỗi `instanceof` phù hợp để chuyển sang pattern switch.
- Chuyển điều kiện kết hợp `instanceof` và `&&` thành guarded pattern bằng `when`.
- Giữ nguyên thứ tự nhánh và tránh lỗi dominance.
- Bảo toàn hành vi khi selector là `null` và khi guard không thỏa mãn.
- Chọn switch statement hoặc switch expression tùy theo mục đích của đoạn mã.
- Kiểm tra tính exhaustive và các thay đổi ngữ nghĩa trước khi hoàn tất refactor.

## 1. Khi nào nên chuyển sang pattern switch?

Pattern switch phù hợp khi nhiều nhánh cùng phân loại một giá trị theo kiểu và thực hiện hành động tương ứng. Ví dụ, một phương thức nhận `Object` và xử lý `String`, `Integer` hoặc các kiểu khác.

Một chuỗi điều kiện thường gặp:

```java
static String describe(Object value) {
    if (value == null) {
        return "null";
    } else if (value instanceof String text && !text.isBlank()) {
        return "text: " + text;
    } else if (value instanceof String text) {
        return "blank text";
    } else if (value instanceof Integer number && number >= 0) {
        return "non-negative: " + number;
    } else if (value instanceof Integer number) {
        return "negative: " + number;
    } else {
        return "other";
    }
}
```

Các nhánh trên có cùng selector là `value`, chủ yếu phân loại theo kiểu, và các điều kiện bổ sung chỉ phụ thuộc vào pattern variable vừa được tạo. Đây là cấu trúc phù hợp để chuyển thành pattern switch.

Không nên chuyển máy móc khi các nhánh:

- Kiểm tra những biểu thức hoặc đối tượng khác nhau, không có một selector chung.
- Thay đổi giá trị được kiểm tra trước khi chạy các nhánh tiếp theo.
- Dựa vào thứ tự đánh giá hoặc side effect của nhiều lời gọi phương thức.
- Có điều kiện boolean phức tạp không thể biểu diễn tương đương bằng một guard.
- Dùng các nhánh `if` để thực hiện nhiều bước nghiệp vụ độc lập thay vì phân loại một giá trị.

Trong các trường hợp đó, hãy giữ cấu trúc điều kiện hoặc tách phần phân loại thành một phương thức riêng trước khi cân nhắc switch.

## 2. Chuyển `instanceof` kết hợp điều kiện thành guarded pattern

Trong Java 21, guarded pattern dùng từ khóa `when` sau type pattern:

```java
case String text when !text.isBlank() -> "non-blank";
```

Phần trước `when` xác định kiểu và tạo pattern variable. Biểu thức guard được đánh giá khi pattern phù hợp; nó có thể sử dụng pattern variable đó. Nếu guard cho kết quả `false`, case label này không được chọn và quá trình xét switch tiếp tục với các label sau.

Đây là cách chuyển trực tiếp điều kiện `instanceof` kết hợp `&&`:

```java
if (value instanceof String text && !text.isBlank()) {
    // xử lý text không rỗng
}
```

thành:

```java
case String text when !text.isBlank() -> {
    // xử lý text không rỗng
}
```

Không dùng cú pháp `case String text && ...`. Trong pattern switch Java 21, điều kiện bảo vệ được viết bằng `when`.

### 2.1. Ví dụ chuyển đổi hoàn chỉnh

Phương thức ở phần trước có thể viết lại bằng switch expression:

```java
static String describe(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> "text: " + text;
        case String text -> "blank text";
        case Integer number when number >= 0 -> "non-negative: " + number;
        case Integer number -> "negative: " + number;
        case null -> "null";
        default -> "other";
    };
}
```

Hai case `String` tương ứng với hai nhánh kiểm tra `String` trong chuỗi điều kiện ban đầu. Nếu guard `!text.isBlank()` là `false`, switch tiếp tục đến case `String` không có guard. Tương tự, `Integer` âm không khớp guard `number >= 0` và được xử lý bởi case `Integer` tiếp theo.

`default` xử lý các kiểu còn lại. `case null` giữ nhánh kiểm tra null tường minh ở đầu chuỗi `if-else` ban đầu.

## 3. Giữ đúng thứ tự nhánh và tránh dominance

Chuỗi `if-else` thực thi nhánh đầu tiên có điều kiện đúng. Pattern switch cũng xét các case label theo thứ tự, nhưng compiler áp dụng quy tắc dominance để ngăn một case không thể được chọn vì đã bị case trước bao phủ hoàn toàn.

Ví dụ sau không hợp lệ:

```java
static String describe(Object value) {
    return switch (value) {
        case CharSequence text -> "sequence";
        case String text -> "string"; // compile error: dominated
        default -> "other";
    };
}
```

`String` triển khai `CharSequence`. Vì case `CharSequence` không có guard nên mọi giá trị `String` đã khớp ở case trước; case `String` phía sau không thể được chọn.

Đổi thứ tự để kiểu cụ thể hơn xuất hiện trước:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence text -> "other sequence";
        default -> "other";
    };
}
```

Khi chuyển một chuỗi điều kiện, hãy lập lại thứ tự theo quan hệ bao hàm kiểu:

- Đặt kiểu con hoặc kiểu cụ thể trước kiểu cha hoặc kiểu tổng quát.
- Đặt các case có guard cụ thể trước case không có guard của cùng kiểu.
- Đặt case fallback sau các trường hợp cần xử lý riêng.
- Giữ thứ tự giữa các guard nếu nhiều điều kiện có thể cùng đúng.

Ví dụ, các guard sau cần được giữ theo thứ tự ưu tiên ban đầu:

```java
return switch (value) {
    case String text when text.length() > 20 -> "long";
    case String text when text.length() > 5 -> "medium";
    case String text -> "short";
    default -> "other";
};
```

Nếu chuyển case `text.length() > 5` lên trước, các chuỗi dài hơn 20 ký tự cũng khớp case đó và không bao giờ đến case `long`. Guard `false` cho phép switch xét tiếp case sau, vì vậy case không có guard cùng kiểu thường đặt sau các case có guard.

## 4. Xử lý `null` đúng với chuỗi điều kiện cũ

Đây là điểm dễ gây lỗi nhất khi refactor. Với pattern switch trên một selector tham chiếu, `null` không khớp type pattern và cũng không được xử lý bởi `default`. Nếu không có `case null`, switch ném `NullPointerException` khi selector là null.

Trong khi đó, biểu thức `null instanceof String` trả về `false`. Vì vậy, một chuỗi `if-else` không kiểm tra null riêng thường đi đến nhánh `else` cuối cùng.

Ví dụ cũ:

```java
static String classify(Object value) {
    if (value instanceof String text) {
        return "text";
    }
    return "not text";
}
```

Với `value == null`, phương thức trả về `"not text"`. Khi chuyển sang switch, cần giữ hành vi đó:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "text";
        case null -> "not text";
        default -> "not text";
    };
}
```

Nếu chuỗi cũ có nhánh null riêng, hãy chuyển nhánh đó thành `case null`:

```java
if (value == null) {
    return "missing";
} else if (value instanceof String text) {
    return text;
}
return "other";
```

```java
return switch (value) {
    case null -> "missing";
    case String text -> text;
    default -> "other";
};
```

Không giả định `default` thay thế được `case null`. Nếu nghiệp vụ muốn null làm phát sinh lỗi, có thể giữ hành vi đó một cách tường minh bằng kiểm tra trước switch hoặc chủ động để switch ném `NullPointerException`; điều quan trọng là phải có quyết định dựa trên hành vi cũ và hợp đồng của phương thức.

## 5. Chọn switch expression hay switch statement

Nếu chuỗi `if-else` trả về một giá trị từ mỗi nhánh, switch expression thường thể hiện ý định rõ ràng hơn:

```java
static int lengthOf(Object value) {
    return switch (value) {
        case String text -> text.length();
        case java.util.Collection<?> items -> items.size();
        case null -> 0;
        default -> -1;
    };
}
```

Nếu mỗi nhánh thực hiện hành động và không tạo ra một giá trị chung, dùng switch statement:

```java
static void logValue(Object value) {
    switch (value) {
        case String text -> System.out.println("text: " + text);
        case Integer number when number >= 0 ->
            System.out.println("positive: " + number);
        case Integer number -> System.out.println("negative: " + number);
        case null -> System.out.println("null");
        default -> System.out.println("other");
    }
}
```

Arrow rule (`->`) không có fall-through như nhóm nhãn kiểu dấu hai chấm truyền thống. Đây là lựa chọn phù hợp khi mỗi pattern đại diện cho một nhánh độc lập và giúp tránh vô tình chạy tiếp sang nhánh khác.

Nếu một nhánh của switch expression cần nhiều câu lệnh, dùng block và `yield` để trả về kết quả:

```java
static String normalize(Object value) {
    return switch (value) {
        case String text -> {
            String normalized = text.strip();
            yield normalized.toLowerCase(java.util.Locale.ROOT);
        }
        case null -> "";
        default -> "unsupported";
    };
}
```

## 6. Bảo toàn thứ tự đánh giá và side effect

Một chuỗi `if-else` có thể đánh giá biểu thức ở nhiều vị trí:

```java
if (readCurrentValue() instanceof String text) {
    use(text);
} else if (readCurrentValue() instanceof Integer number) {
    use(number);
} else {
    handleOther();
}
```

`readCurrentValue()` có thể được gọi hai lần nếu nhánh đầu không khớp. Switch chỉ đánh giá selector một lần:

```java
switch (readCurrentValue()) {
    case String text -> use(text);
    case Integer number -> use(number);
    case null -> handleOther();
    default -> handleOther();
}
```

Hai đoạn mã chỉ tương đương nếu việc gọi `readCurrentValue()` lặp lại không tạo ra khác biệt quan sát được hoặc giá trị trả về không thay đổi. `case null` và `default` cùng gọi `handleOther()` để giữ nhánh cuối của chuỗi cũ. Nếu lời gọi có side effect, đọc trạng thái có thể thay đổi hoặc trả về giá trị khác nhau theo thời điểm, việc chuyển đổi sẽ thay đổi hành vi.

Trước khi refactor, hãy quyết định rõ giá trị nào cần phân loại. Nếu nghiệp vụ yêu cầu chỉ đọc một lần, lưu kết quả vào biến cục bộ rồi dùng biến đó trong chuỗi điều kiện hoặc switch:

```java
Object current = readCurrentValue();

return switch (current) {
    case String text -> handleText(text);
    case Integer number -> handleNumber(number);
    case null -> handleMissing();
    default -> handleOther();
};
```

Pattern switch cũng gọi accessor khi gặp record pattern. Nếu accessor có side effect hoặc ném ngoại lệ, việc deconstruction có thể tạo ra hành vi quan sát được. Hãy giữ accessor đơn giản, ổn định và tránh I/O hoặc thay đổi trạng thái trong quá trình matching.

## 7. Kiểm tra tính exhaustive của switch expression

Switch expression phải exhaustive: compiler cần xác định rằng mọi giá trị có thể thuộc selector type đều được xử lý bởi một case label. Với kiểu mở như `Object`, thường cần `default` để xử lý các trường hợp còn lại.

Với sealed hierarchy, compiler có thể xác định các kiểu con được phép và cho phép liệt kê đầy đủ mà không cần `default`:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static double area(Shape shape) {
    return switch (shape) {
        case Circle circle -> Math.PI * circle.radius() * circle.radius();
        case Rectangle rectangle -> rectangle.width() * rectangle.height();
    };
}
```

Nếu hierarchy được mở rộng và thêm một kiểu con được phép mới, compiler có thể yêu cầu cập nhật switch expression để xử lý kiểu đó. Đây là lợi ích khi chuyển một chuỗi điều kiện phân loại hierarchy sang switch: thiếu nhánh có thể được phát hiện khi biên dịch.

Tính exhaustive không làm thay đổi quy tắc null. Switch expression trên `Shape` ở ví dụ trên vẫn ném `NullPointerException` nếu `shape` là null. Nếu null là trạng thái hợp lệ của nghiệp vụ, thêm `case null` và trả về hoặc xử lý giá trị phù hợp.

Với switch statement, hãy chủ động quyết định cách xử lý trường hợp còn lại và null. Không nên dựa vào việc switch expression hoặc switch statement có kiểm tra exhaustive để thay thế yêu cầu nghiệp vụ về các đầu vào này.

## 8. Quy trình refactor có kiểm soát

Khi chuyển một chuỗi `instanceof` hoặc `if-else`, thực hiện theo các bước sau:

1. **Chọn selector:** xác định chính xác một giá trị được phân loại. Nếu biểu thức được đánh giá nhiều lần, xem xét lưu kết quả vào biến cục bộ và xác định liệu thay đổi số lần đánh giá có ảnh hưởng hành vi hay không.
2. **Ghi lại thứ tự nhánh:** liệt kê từng kiểu, điều kiện phụ và nhánh fallback theo đúng thứ tự của chuỗi cũ.
3. **Chuyển điều kiện thành pattern:** thay `instanceof Type variable` bằng `case Type variable`; thay điều kiện kết hợp bằng guard `when` khi biểu thức guard có thể giữ nguyên ý nghĩa.
4. **Kiểm tra quan hệ kiểu:** đưa kiểu con trước kiểu cha và đặt case có guard trước case không guard cùng kiểu để tránh dominance và giữ ưu tiên.
5. **Xử lý null:** xác định chuỗi cũ làm gì khi selector null; thêm `case null` nếu cần giữ hành vi đó.
6. **Chọn dạng switch:** dùng switch expression khi các nhánh tạo ra một giá trị; dùng switch statement khi các nhánh thực hiện hành động.
7. **Kiểm tra exhaustive:** bảo đảm switch expression bao phủ mọi kiểu có thể có, đặc biệt khi selector là sealed hierarchy.
8. **So sánh hành vi:** kiểm tra đầu vào cho từng kiểu, kiểu con, guard đúng/sai, null và kiểu không được hỗ trợ; kiểm tra thêm side effect và số lần gọi phương thức.

## 9. Checklist kiểm thử sau chuyển đổi

| Trường hợp | Điều cần xác minh |
|---|---|
| Mỗi kiểu được hỗ trợ | Chọn đúng case và trả về đúng kết quả như chuỗi cũ |
| Kiểu con và kiểu cha cùng xuất hiện | Case cụ thể không bị case tổng quát chiếm trước |
| Guard đúng | Chọn nhánh có guard tương ứng |
| Guard sai | Tiếp tục xét case sau và cuối cùng đến fallback nếu phù hợp |
| Giá trị `null` | Giữ đúng hành vi cũ; không vô tình phát sinh `NullPointerException` |
| Kiểu không được hỗ trợ | Đi vào `default` hoặc hành vi fallback đã xác định |
| Biểu thức selector có side effect | Số lần đánh giá và thứ tự thực thi không làm thay đổi nghiệp vụ ngoài dự kiến |
| Sealed hierarchy được mở rộng | Switch expression vẫn exhaustive sau khi thêm subtype |

Đặc biệt, nên có kiểm thử cho các giá trị nằm ngay ranh giới guard. Với `number >= 0`, hãy kiểm tra cả `0`, số dương và số âm. Với `text.length() > 5`, hãy kiểm tra chuỗi có độ dài 5 và 6 để phát hiện lỗi đổi toán tử hoặc đổi thứ tự nhánh.

## 10. Nguyên tắc lựa chọn

- Dùng pattern switch khi nhiều nhánh cùng phân loại một selector theo kiểu và có thể biểu diễn bằng case pattern rõ ràng.
- Dùng `when` cho điều kiện phụ gắn với pattern variable; không nhét điều kiện vào cú pháp pattern.
- Giữ thứ tự ưu tiên của chuỗi cũ, đồng thời tuân thủ dominance của case label.
- Xử lý null tường minh khi cần; `default` không nhận null.
- Chỉ đổi số lần đánh giá selector sau khi xác nhận không làm thay đổi hành vi quan sát được.
- Ưu tiên arrow rule để mỗi nhánh độc lập, không fall-through.
- Dùng switch expression và sealed hierarchy khi muốn compiler hỗ trợ kiểm tra tính exhaustive.

Pattern switch giúp gom logic phân loại vào một cấu trúc dễ đọc và giúp compiler phát hiện một số lỗi về thứ tự hoặc độ bao phủ. Chất lượng của refactor vẫn phụ thuộc vào việc giữ nguyên hợp đồng đầu vào, thứ tự điều kiện, hành vi null và các tác động phụ của chương trình.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 21 — §14.11 Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): switch statement, pattern case labels và quy tắc đánh giá.
- [Java Language Specification, Java SE 21 — §14.11.1.2 Dominance of Case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): quy tắc dominance và thứ tự case label.
- [Java Language Specification, Java SE 21 — §15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expression, tính exhaustive và kết quả của biểu thức.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): tính năng pattern switch được hoàn thiện trong Java 21, guarded pattern và xử lý null.
- [Java Language Changes for Java SE 21](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): các thay đổi ngôn ngữ chính thức trong Java 21.
