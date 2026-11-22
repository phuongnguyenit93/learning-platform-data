# Pattern Matching cho switch đã hoàn thiện trong Java 21

## 1. Pattern Matching for switch là gì?

Trong Java 21, `switch` có thể kiểm tra kiểu của giá trị bằng **type pattern**, lấy biến có kiểu tương ứng và thực thi nhánh phù hợp. Tính năng Pattern Matching for switch đã trở thành tính năng chính thức trong Java 21 theo JEP 441. Khi biên dịch và chạy ở mức Java 21, không cần bật preview feature.

Khi selector có kiểu tổng quát như `Object`, pattern switch gom việc kiểm tra kiểu và xử lý vào một cấu trúc duy nhất:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Text: " + text;
        case Integer number -> "Integer: " + number;
        case null -> "No value";
        default -> "Other type";
    };
}
```

Ở mỗi nhánh, Java kiểm tra giá trị selector có khớp pattern hay không. Nếu khớp, pattern variable như `text` hoặc `number` được tạo với kiểu đã khai báo và chỉ có thể dùng trong phạm vi nhánh tương ứng.

Pattern switch có thể dùng trong cả `switch` expression và `switch` statement. Switch expression tạo ra một giá trị; switch statement thực hiện các hành động. Cả hai đều hỗ trợ pattern labels, guarded patterns và cách xử lý `null` được trình bày trong bài này.

## 2. Type pattern trong case label

Type pattern có dạng `Type variableName`. Trong một case label, Java kiểm tra giá trị có khác `null` và có thể được chuyển sang kiểu pattern hay không. Khi khớp, biến được khai báo có kiểu đó.

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "String length: " + text.length();
        case Integer integer -> "Integer value: " + integer;
        case Number number -> "Other number: " + number;
        default -> "Unsupported value";
    };
}
```

Trong ví dụ này:

- `String text` chỉ khớp khi selector là một `String` khác `null`.
- `Integer integer` khớp với `Integer`.
- `Number number` khớp với các giá trị thuộc `Number` mà chưa được một nhánh đứng trước xử lý, chẳng hạn `Double` hoặc `Long`.
- `default` xử lý những giá trị khác chưa khớp pattern nào.

Type pattern loại bỏ nhu cầu ép kiểu thủ công trong thân nhánh. Bên trong nhánh `case String text`, compiler đã biết `text` là `String`, nên có thể gọi trực tiếp `length()`.

### 2.1. Chọn kiểu pattern phù hợp

Kiểu pattern phải tương thích với kiểu selector. Ví dụ, khi selector có kiểu `Object`, các pattern `String`, `Integer` và `Number` đều có thể được kiểm tra. Nếu selector đã có kiểu quá hẹp để không thể là kiểu pattern được khai báo, compiler sẽ báo lỗi không tương thích.

Pattern switch trong Java 21 chủ yếu áp dụng cho selector có kiểu tham chiếu. Java 21 chưa có primitive type patterns như `case int number`; không suy rộng tính năng này sang việc kiểm tra trực tiếp giá trị primitive. Các kiểu primitive vẫn có thể được xử lý bằng các case constant phù hợp với cú pháp switch của Java.

Với generic, chỉ dùng kiểu pattern có thể kiểm tra an toàn tại runtime. Ví dụ `List<?>` là kiểu phù hợp để kiểm tra, còn `List<String>` không thể được kiểm tra trực tiếp theo cách thông thường vì type argument `String` đã bị xóa ở runtime và kiểu đó không reifiable:

```java
static String describeCollection(Object value) {
    return switch (value) {
        case java.util.List<?> items -> "List with " + items.size() + " items";
        default -> "Not a list";
    };
}
```

## 3. Guarded pattern với `when`

Đôi khi chỉ kiểm tra kiểu là chưa đủ. Ta cần kiểm tra thêm một điều kiện trên giá trị đã khớp pattern, ví dụ chuỗi rỗng, số dương hoặc một trạng thái cụ thể. Java 21 dùng từ khóa `when` để thêm **guard** vào pattern label.

```java
static String describeText(String value) {
    return switch (value) {
        case null -> "No text";
        case String text when text.isBlank() -> "Blank text";
        case String text when text.length() > 20 -> "Long text";
        case String text -> "Text: " + text;
    };
}
```

Một guarded pattern gồm pattern và điều kiện guard:

```java
case String text when text.isBlank() -> "Blank text";
```

Trình tự xử lý là:

1. Kiểm tra selector có khớp `String text` hay không.
2. Nếu pattern khớp, đánh giá biểu thức guard `text.isBlank()`.
3. Nếu guard trả về `true`, chọn nhánh đó.
4. Nếu guard trả về `false`, tiếp tục xét các case label tiếp theo.

Pattern variable được khai báo trong pattern có thể được sử dụng trong guard. Guard phải có kiểu kết quả `boolean`; nên giữ guard ngắn, dễ đọc và tránh side effect để việc chọn nhánh có thể dự đoán được.

Trong Java 21, viết điều kiện bổ sung bằng `when` ngay sau pattern. Biến được khai báo trong pattern có thể được dùng trực tiếp trong biểu thức guard.

## 4. Thứ tự case và quy tắc dominance

Thứ tự case có ý nghĩa vì một pattern tổng quát có thể bao phủ mọi giá trị mà pattern cụ thể phía sau muốn khớp. Java gọi trường hợp đó là **dominated pattern**. Compiler từ chối case bị một case đứng trước bao phủ hoàn toàn vì nhánh phía sau sẽ không thể được chọn.

Ví dụ không hợp lệ:

```java
static String classify(Number value) {
    return switch (value) {
        case Number number -> "Number";
        case Integer integer -> "Integer"; // Lỗi: bị case Number bao phủ
    };
}
```

`Integer` là lớp con của `Number`. Nếu giá trị là `Integer`, case `Number number` đứng trước đã khớp, nên case `Integer integer` không bao giờ được chạy.

Hãy đặt pattern cụ thể trước pattern tổng quát:

```java
static String classify(Number value) {
    return switch (value) {
        case Integer integer -> "Integer";
        case Number number -> "Other number";
    };
}
```

Guard cũng ảnh hưởng đến việc xét dominance. Một guarded pattern có điều kiện không hằng `true` không bao phủ mọi giá trị của kiểu pattern, vì vậy có thể đặt một case tổng quát hơn phía sau:

```java
static String describe(Object value) {
    return switch (value) {
        case String text when text.length() > 10 -> "Long string";
        case String text -> "Other string";
        default -> "Other value";
    };
}
```

Nếu đảo thứ tự và đặt `case String text` trước guarded pattern, nhánh tổng quát sẽ bao phủ mọi `String`, khiến guarded pattern phía sau bị dominated. Vì vậy, hãy xếp các trường hợp hẹp hoặc có điều kiện trước trường hợp rộng.

## 5. Xử lý `null` trong pattern switch

Một điểm cần nhớ là **`default` không khớp với `null`**. Khi selector là `null` và switch không có `case null`, Java ném `NullPointerException` trước khi thực hiện nhánh thông thường, kể cả khi có `default`.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Null value";
        case String text -> "Text: " + text;
        default -> "Other value";
    };
}
```

Nếu API cho phép đầu vào `null`, hãy quyết định rõ cách xử lý bằng `case null`, chẳng hạn trả về kết quả mặc định, ghi nhận trạng thái thiếu dữ liệu hoặc ném exception nghiệp vụ phù hợp. Nếu `null` là đầu vào không hợp lệ, có thể chủ động ném exception trong nhánh này:

```java
static int lengthOf(Object value) {
    return switch (value) {
        case null -> throw new IllegalArgumentException("value is required");
        case String text -> text.length();
        default -> throw new IllegalArgumentException("value must be a String");
    };
}
```

Record pattern cũng không khớp nếu chính record selector là `null`. Việc component bên trong record có thể là `null` là vấn đề riêng, phụ thuộc vào component pattern tương ứng.

## 6. Exhaustiveness: đảm bảo mọi trường hợp đều được xử lý

Switch expression phải **exhaustive**, nghĩa là compiler phải xác định được mọi giá trị có thể của selector đều được xử lý bởi một case label. Switch statement sử dụng pattern labels cũng là enhanced switch statement và phải exhaustive.

Với selector có kiểu mở như `Object`, thường cần `default` để bao phủ các giá trị chưa được liệt kê:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String";
        case Integer number -> "Integer";
        default -> "Other";
    };
}
```

Với một kiểu `sealed`, compiler có thể xác định các kiểu con được phép và kiểm tra tính exhaustive mà không cần `default`.

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static double area(Shape shape) {
    return switch (shape) {
        case Circle(var radius) -> Math.PI * radius * radius;
        case Rectangle(var width, var height) -> width * height;
    };
}
```

Ở đây, `Shape` chỉ cho phép `Circle` và `Rectangle`; cả hai đều được xử lý nên switch expression exhaustive. Record pattern còn cho phép lấy trực tiếp component của từng kiểu con.

Nếu sau này hierarchy được mở rộng bằng một kiểu con mới và mã nguồn được biên dịch lại, compiler có thể chỉ ra switch nào chưa xử lý kiểu mới. Đây là lợi ích lớn của exhaustive switch khi làm việc với sealed hierarchy.

`default` hữu ích với kiểu mở hoặc khi cần một nhánh dự phòng. Tuy nhiên, nếu đang xử lý sealed hierarchy và muốn compiler phát hiện kiểu con mới, hãy cân nhắc liệt kê từng kiểu con thay vì dùng `default` bao phủ tất cả.

Exhaustiveness không đồng nghĩa với xử lý `null`. Nếu cần hỗ trợ selector `null`, hãy thêm `case null`; nếu không, selector `null` vẫn gây `NullPointerException`.

## 7. Kết hợp type pattern, guard và record pattern

Pattern switch có thể kết hợp nhiều loại pattern để diễn đạt quy tắc nghiệp vụ theo cấu trúc dữ liệu. Ví dụ, một hệ thống tính phí có thể nhận nhiều loại yêu cầu:

```java
sealed interface Payment permits CardPayment, CashPayment {}

record CardPayment(String cardToken, double amount) implements Payment {}
record CashPayment(double amount) implements Payment {}

static String validatePayment(Payment payment) {
    return switch (payment) {
        case null -> "Payment is required";
        case CardPayment(var token, var amount) when token != null && !token.isBlank()
                && amount > 0 -> "Card payment accepted";
        case CardPayment card -> "Invalid card payment";
        case CashPayment(var amount) when amount > 0 -> "Cash payment accepted";
        case CashPayment cash -> "Invalid cash payment";
    };
}
```

Ví dụ sử dụng record pattern để tách component và `when` để kiểm tra điều kiện nghiệp vụ. Các case tổng quát `CardPayment card` và `CashPayment cash` xử lý những đối tượng cùng loại không vượt qua guard ở case trước. Hai kiểu con của sealed interface đều được bao phủ; `case null` xử lý selector null.

Trong code thực tế, kiểu dữ liệu tiền tệ nên dùng biểu diễn số thập phân phù hợp với nghiệp vụ, chẳng hạn `BigDecimal`, và cần quy định rõ đơn vị tiền. Ví dụ trên tập trung minh họa cú pháp pattern switch, không phải mô hình tính toán tiền hoàn chỉnh.

## 8. Pattern switch trong statement và expression

Switch expression trả về giá trị và có thể được gán, trả về trực tiếp hoặc truyền vào một biểu thức khác:

```java
static String category(Object value) {
    return switch (value) {
        case String text -> "text";
        case Number number -> "number";
        case null -> "null";
        default -> "other";
    };
}
```

Switch statement phù hợp khi mỗi nhánh thực hiện một hành động:

```java
static void logValue(Object value) {
    switch (value) {
        case null -> System.out.println("value is null");
        case String text -> System.out.println("text=" + text);
        case Number number -> System.out.println("number=" + number);
        default -> System.out.println("other value");
    }
}
```

Với arrow rule (`->`), mỗi nhánh có phạm vi rõ ràng và không tự động rơi xuống nhánh kế tiếp. Đây là cách viết dễ đọc cho pattern switch và tránh lỗi fall-through thường gặp trong switch dùng statement group kiểu dấu hai chấm.

## 9. Những lưu ý khi đưa pattern switch vào ứng dụng

- **Giữ guard đơn giản**: guard nên là điều kiện kiểm tra nhanh, dễ đọc và không làm thay đổi trạng thái hệ thống.
- **Sắp xếp pattern cụ thể trước pattern tổng quát**: tránh case bị dominance và giúp người đọc thấy rõ thứ tự ưu tiên.
- **Quyết định chính sách `null`**: `default` không xử lý `null`; hãy dùng `case null` khi cần hành vi rõ ràng.
- **Tận dụng sealed hierarchy**: liệt kê các kiểu con để compiler kiểm tra exhaustiveness và hỗ trợ thay đổi mô hình dữ liệu an toàn hơn.
- **Không lạm dụng `default`**: với hierarchy đóng, default có thể che mất việc một kiểu con mới chưa được xử lý.
- **Chọn pattern có thể kiểm tra tại runtime**: với generic, ưu tiên kiểu reifiable như `List<?>`; không giả định JVM có thể kiểm tra type argument đã bị xóa.
- **Không nhầm pattern switch với primitive patterns**: Java 21 hỗ trợ pattern matching trên kiểu tham chiếu; primitive type patterns nằm ngoài phạm vi ngôn ngữ Java 21.
- **Dùng đúng mức ngôn ngữ**: cấu hình compiler và runtime ở Java 21 để sử dụng tính năng đã finalized mà không bật preview.

## 10. Tài liệu tham khảo chính thức

- [Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): cách dùng pattern switch, guard, `null` và ví dụ.
- [Java Language Specification, Java SE 21 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): quy tắc switch statement, pattern labels, dominance và exhaustiveness.
- [Java Language Specification, Java SE 21 — The switch Expression](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): quy tắc switch expression.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): phạm vi và trạng thái chính thức của tính năng trong Java 21.

Pattern Matching for switch giúp biểu diễn việc phân nhánh theo kiểu và cấu trúc dữ liệu rõ ràng hơn. Khi sử dụng, hãy chú ý bốn điểm: kiểu pattern phải tương thích với selector, guard phải diễn đạt điều kiện bổ sung, case không được bị dominated và switch phải exhaustive. Đồng thời, xử lý `null` như một trường hợp riêng để hành vi của chương trình luôn rõ ràng.
