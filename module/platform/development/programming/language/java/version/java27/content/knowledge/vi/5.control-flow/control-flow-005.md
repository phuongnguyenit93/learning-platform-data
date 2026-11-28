# Yield, nhãn mũi tên và tính đầy đủ của switch

Trong Java, `switch` có thể điều khiển luồng thực thi hoặc tạo ra một giá trị để dùng trong biểu thức lớn hơn. Các nhãn mũi tên `->` giúp mỗi nhánh thực hiện độc lập, còn `yield` trả giá trị từ một nhánh có nhiều câu lệnh của `switch` expression. Tính đầy đủ (exhaustiveness) bảo đảm các giá trị mà chương trình có thể nhận được đều được xử lý theo thiết kế.

Bài viết trình bày cú pháp đã trở thành tính năng chính thức và áp dụng trong Java 27: switch expressions và arrow rules (Java 14), pattern matching for switch (Java 21), cùng `case null` và các quy tắc exhaustiveness hiện hành. Các ví dụ không dựa vào tính năng preview.

## 1. Phân biệt switch statement và switch expression

`switch` có hai cách sử dụng:

- **Switch statement:** một câu lệnh điều khiển luồng. Nó chọn nhánh để thực thi, thường dùng khi cần gọi method, cập nhật trạng thái hoặc thực hiện một nhóm thao tác.
- **Switch expression:** một biểu thức đánh giá thành một giá trị. Giá trị đó có thể được gán cho biến, trả về từ method hoặc truyền làm đối số cho một method khác.

Ví dụ dùng switch expression để ánh xạ enum thành điểm:

```java
enum Priority {
    LOW, NORMAL, HIGH
}

static int priorityScore(Priority priority) {
    return switch (priority) {
        case LOW -> 1;
        case NORMAL -> 2;
        case HIGH -> 3;
    };
}
```

Biểu thức `switch` ở đây tạo ra một giá trị `int`. Mỗi nhánh phải cho ra giá trị tương thích với kiểu kết quả của biểu thức. Vì đã liệt kê tất cả hằng số của `Priority`, switch expression này là exhaustive và không cần `default`.

Switch statement thường được dùng khi mục tiêu chính là tác động phụ:

```java
enum OrderStatus {
    CREATED, PENDING, PAID, CANCELLED
}

static void process(OrderStatus status) {
    switch (status) {
        case CREATED, PENDING -> notifyCustomer();
        case PAID -> issueReceipt();
        case CANCELLED -> releaseReservation();
    }
}
```

Các method trong ví dụ được gọi để thực hiện công việc. Switch statement không tạo ra một giá trị kết quả để gán cho biến.

## 2. Nhãn mũi tên `->`

Một switch rule dùng nhãn `case` hoặc `default`, tiếp theo là mũi tên và phần xử lý:

```java
case label1, label2 -> expression;
case label3 -> {
    // Một hoặc nhiều câu lệnh
}
case label4 -> throw new IllegalArgumentException();
```

Có thể gộp nhiều nhãn có cùng cách xử lý bằng dấu phẩy, ví dụ `case CREATED, PENDING -> ...`. Khi một nhãn mũi tên khớp, chỉ rule tương ứng được thực hiện; luồng không tự chạy tiếp sang rule kế tiếp. Vì vậy, arrow rule không cần `break` để ngăn fall-through.

### 2.1. Dùng arrow rule trong switch statement

Phần sau `->` của switch statement có thể là:

- Một statement expression, ví dụ lời gọi method, phép gán, phép tăng/giảm hoặc biểu thức tạo object.
- Một block `{ ... }` chứa nhiều câu lệnh.
- Một câu lệnh `throw`.

Ví dụ hợp lệ:

```java
switch (status) {
    case CREATED -> log("Order created");
    case PAID -> receiptIssued = true;
    case CANCELLED -> {
        releaseReservation();
        log("Reservation released");
    }
    default -> throw new IllegalStateException("Unsupported status");
}
```

Trong switch statement, phần bên phải mũi tên không thể là một biểu thức tùy ý chỉ tạo ra giá trị rồi bỏ đó. Ví dụ `case CREATED -> 10;` không hợp lệ vì `10` không phải statement expression. Nếu muốn tính ra một giá trị, hãy dùng switch expression; nếu muốn thực hiện phép tính và lưu kết quả, có thể viết phép gán như `case CREATED -> result = 10;`.

### 2.2. Dùng arrow rule trong switch expression

Switch expression cho phép dùng một biểu thức bất kỳ ở bên phải mũi tên. Giá trị của biểu thức đó trở thành kết quả của nhánh:

```java
static String monthLength(int month, int year) {
    return switch (month) {
        case 2 -> java.time.Year.isLeap(year) ? "29 days" : "28 days";
        case 4, 6, 9, 11 -> "30 days";
        case 1, 3, 5, 7, 8, 10, 12 -> "31 days";
        default -> throw new IllegalArgumentException("Invalid month: " + month);
    };
}
```

Các nhánh có thể trả về biểu thức điều kiện, lời gọi method, phép toán hoặc một giá trị khác. Kiểu kết quả của switch expression được xác định từ các result expression và ngữ cảnh sử dụng.

### 2.3. Block trong arrow rule

Khi một nhánh cần nhiều câu lệnh trước khi tạo kết quả, đặt chúng trong block. Với switch expression, block phải kết thúc bằng `yield` hoặc một cách hoàn tất đột ngột như `throw`; block không được kết thúc bình thường mà không cung cấp kết quả.

```java
static String monthLengthWithLog(int month, int year) {
    return switch (month) {
        case 2 -> {
            boolean leapYear = java.time.Year.isLeap(year);
            int days = leapYear ? 29 : 28;
            System.out.println("February has " + days + " days");
            yield days + " days";
        }
        case 4, 6, 9, 11 -> "30 days";
        case 1, 3, 5, 7, 8, 10, 12 -> "31 days";
        default -> throw new IllegalArgumentException("Invalid month: " + month);
    };
}
```

Trong thực tế, có thể dùng `java.time.Month` thay cho số tháng và tách phần tính số ngày thành method riêng. Mục đích ở đây là minh họa block có nhiều thao tác và dùng `yield` để trả kết quả.

## 3. Câu lệnh `yield`

`yield` chuyển quyền điều khiển tới switch expression bao quanh gần nhất và cung cấp giá trị cho biểu thức đó. Cú pháp là:

```java
yield expression;
```

Ví dụ:

```java
int score = switch (grade) {
    case 'A' -> {
        log("Excellent");
        yield 4;
    }
    case 'B' -> {
        log("Good");
        yield 3;
    }
    default -> 0;
};
```

Nhánh `A` và `B` thực hiện thêm thao tác ghi log, sau đó `yield` trả `4` hoặc `3` làm giá trị của switch expression. Nhánh `default` dùng biểu thức `0` trực tiếp nên không cần `yield`.

Các quy tắc cần nhớ:

1. `yield` chỉ cung cấp giá trị cho một switch expression; switch statement không phải là đích của `yield`.
2. Phải có một switch expression bao quanh để nhận giá trị. Dùng `yield` bên ngoài switch expression là lỗi biên dịch.
3. Biểu thức sau `yield` phải tạo ra giá trị, không thể là lời gọi method trả về `void`.
4. Đích của `yield` là switch expression gần nhất. Việc chuyển điều khiển không được vượt qua method, constructor, initializer hoặc lambda expression.
5. Kiểu của giá trị được yield phải tương thích với kiểu kết quả mà switch expression yêu cầu.

`yield` khác `break` và `return`:

| Câu lệnh | Tác dụng |
| --- | --- |
| `yield value;` | Kết thúc nhánh và cung cấp `value` cho switch expression bao quanh. |
| `break;` | Thoát khỏi switch statement hoặc vòng lặp mà nó nhắm tới; không cung cấp giá trị cho switch expression. |
| `return value;` | Trả kết quả từ method hoặc lambda phù hợp; không phải cách trả giá trị của một nhánh switch expression. |
| `throw exception;` | Kết thúc luồng bằng cách ném exception; nhánh không cần tạo giá trị nếu nó luôn ném exception. |

### 3.1. `yield` với nhãn hai chấm

Switch expression vẫn cho phép nhóm nhãn theo cú pháp dấu hai chấm `case L:`. Mỗi nhánh cần yield giá trị hoặc kết thúc bằng `throw` hay một cách hoàn tất đột ngột hợp lệ:

```java
int points = switch (grade) {
    case 'A':
        yield 4;
    case 'B':
        yield 3;
    case 'C':
        yield 2;
    default:
        yield 0;
};
```

Nhãn hai chấm giữ quy tắc fall-through của switch labeled statement groups. Có thể gom nhiều nhãn liên tiếp vào cùng một nhóm, nhưng nếu thiếu `yield`, luồng có thể chạy sang nhóm sau hoặc khiến switch expression không tạo được kết quả. Với code mới, arrow rule thường dễ đọc và ít có nguy cơ bỏ sót `yield` hơn.

## 4. Tính đầy đủ (exhaustiveness) của switch

Một switch block là exhaustive đối với selector expression khi các nhãn của nó bao phủ toàn bộ các trường hợp mà kiểu selector có thể nhận theo quy tắc của Java. Trình biên dịch kiểm tra tính đầy đủ ở thời điểm biên dịch.

### 4.1. Switch expression luôn phải exhaustive

Mọi switch expression đều phải exhaustive. Nếu có một giá trị hợp lệ của selector không khớp nhãn nào, chương trình bị lỗi biên dịch.

Với kiểu `int`, tập các nhãn số hữu hạn không thể bao phủ mọi giá trị `int`; vì vậy thường cần `default`:

```java
static String httpCategory(int statusCode) {
    return switch (statusCode) {
        case 200, 201, 204 -> "Success";
        case 400, 401, 403, 404 -> "Client error";
        case 500, 502, 503 -> "Server error";
        default -> "Other status";
    };
}
```

Với enum, nếu các nhánh liệt kê tất cả hằng số hiện có, switch expression không cần `default`:

```java
enum PaymentStatus {
    NEW, AUTHORIZED, SETTLED, DECLINED
}

static String paymentMessage(PaymentStatus status) {
    return switch (status) {
        case NEW -> "Waiting for authorization";
        case AUTHORIZED -> "Ready to settle";
        case SETTLED -> "Payment completed";
        case DECLINED -> "Payment was declined";
    };
}
```

Việc liệt kê enum như vậy giúp compiler phát hiện khi source enum được cập nhật thêm hằng số mà switch expression chưa xử lý. Nếu code đã biên dịch được chạy cùng một phiên bản enum mới hơn có hằng số chưa được xử lý, switch có thể ném `MatchException` tại runtime.

### 4.2. Khi nào switch statement phải exhaustive?

Switch statement không phải lúc nào cũng bị yêu cầu exhaustive. Java phân biệt switch statement thông thường với *enhanced switch statement*:

| Dạng switch statement | Yêu cầu exhaustive |
| --- | --- |
| Selector thuộc nhóm kiểu truyền thống `char`, `byte`, `short`, `int`, kiểu wrapper tương ứng, `String` hoặc enum; chỉ dùng case constants | Không bắt buộc vì lý do tương thích ngôn ngữ. Nên tự xử lý các trường hợp nghiệp vụ cần thiết. |
| Có case pattern, ví dụ `case String text -> ...` | Bắt buộc. |
| Có nhãn `case null` | Bắt buộc. |
| Selector có kiểu tham chiếu khác `String` hoặc enum, ví dụ `Object`, `Number`, interface hoặc class thông thường | Bắt buộc. |

Ví dụ switch statement với selector `Object` phải có nhánh bao phủ các kiểu còn lại:

```java
static void printValue(Object value) {
    switch (value) {
        case String text -> System.out.println("Text: " + text);
        case Integer number -> System.out.println("Number: " + number);
        default -> System.out.println("Other value");
    }
}
```

Nếu bỏ `default`, switch statement này không exhaustive và không biên dịch. `Object` có thể chứa nhiều kiểu khác ngoài `String` và `Integer`.

Với switch statement thông thường chỉ dùng case constants, nếu selector không khớp nhãn nào và không phải `null`, statement có thể hoàn tất bình thường mà không chạy nhánh nào. Switch expression và enhanced switch statement được yêu cầu exhaustive; nếu code đã biên dịch gặp một giá trị mới mà không nhãn nào xử lý được, runtime ném `MatchException`. Riêng selector `null` vẫn ném `NullPointerException` khi không có `case null`.

### 4.3. Exhaustiveness với sealed hierarchy

Với một `abstract sealed class` hoặc `sealed interface`, compiler biết tập các kiểu con trực tiếp được phép khai báo qua `permits`. Nếu các nhánh pattern bao phủ hết những kiểu con có thể xuất hiện, switch expression có thể exhaustive mà không cần `default`.

```java
sealed interface Payment permits CardPayment, BankTransfer {
}

record CardPayment(String lastFourDigits) implements Payment {
}

record BankTransfer(String reference) implements Payment {
}

static String paymentDescription(Payment payment) {
    return switch (payment) {
        case CardPayment card -> "Card ending " + card.lastFourDigits();
        case BankTransfer transfer -> "Bank transfer " + transfer.reference();
        case null -> "No payment provided";
    };
}
```

Hai pattern bao phủ toàn bộ kiểu con được phép của `Payment`; `case null` xử lý riêng giá trị null. Nếu sau này sealed hierarchy được thay đổi để cho phép một kiểu con mới, cần cập nhật các switch phụ thuộc vào tập kiểu đó. Code cũ gặp một subtype chưa có nhánh phù hợp có thể ném `MatchException` tại runtime.

### 4.4. Guarded pattern và độ bao phủ

Pattern label có thể kèm điều kiện `when`. Điều kiện này chỉ cho nhánh khớp khi pattern khớp và guard trả về `true`:

```java
static String describe(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "Blank text";
        case String text -> "Text: " + text;
        case Integer number -> "Integer: " + number;
        case null -> "Null value";
        default -> "Other value";
    };
}
```

Nhánh `case String text when text.isBlank()` chỉ bao phủ các chuỗi rỗng hoặc toàn khoảng trắng. Guard có thể trả `false`, vì vậy riêng pattern có guard không được coi là đã bao phủ toàn bộ kiểu `String`. Nhánh `case String text` không có guard phía sau xử lý những chuỗi còn lại.

Một pattern tổng quát có thể khiến các pattern cụ thể phía sau không bao giờ được xét. Ví dụ, `case CharSequence sequence` đặt trước `case String text` sẽ làm nhánh `String` bị dominated vì mọi `String` đều là `CharSequence`. Compiler báo lỗi cho nhãn bị dominated.

## 5. Xử lý giá trị `null`

Với switch trên kiểu tham chiếu, `null` là trường hợp cần quyết định rõ. Nếu selector có giá trị null và không có nhãn `case null` áp dụng, Java ném `NullPointerException`. Nhãn `default` thông thường không bắt giá trị null.

Có thể xử lý null bằng nhãn riêng:

```java
static String displayName(String name) {
    return switch (name) {
        case null -> "(no name)";
        case "" -> "(empty name)";
        default -> name;
    };
}
```

Hoặc gộp `null` và `default` nếu chúng dùng cùng cách xử lý:

```java
static String safeLabel(Object value) {
    return switch (value) {
        case String text -> text;
        case null, default -> "Unavailable";
    };
}
```

`case null, default` bao phủ cả null lẫn các giá trị không khớp những nhánh cụ thể trước đó. Nếu cần phân biệt null với kiểu khác, dùng hai nhánh riêng `case null -> ...` và `default -> ...`.

Lưu ý: tính exhaustive ở thời điểm biên dịch và xử lý null là hai việc riêng. Một switch có `default` có thể đáp ứng kiểm tra exhaustive nhưng vẫn ném `NullPointerException` nếu selector là null và không có `case null`.

## 6. Chọn nhãn phù hợp và tránh lỗi thường gặp

| Tình huống | Vì sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| Dùng `case A -> value;` trong switch statement | Switch statement chỉ cho phép statement expression sau mũi tên; biểu thức giá trị đơn thuần không phải statement expression | Dùng switch expression hoặc gán giá trị trong statement expression như `case A -> result = value;` |
| Dùng block trong switch expression nhưng không có `yield` | Block có thể kết thúc bình thường mà không tạo giá trị | Thêm `yield value;` trên mọi đường đi bình thường hoặc ném exception |
| Cho rằng `default` bắt được null | `default` không áp dụng cho null | Thêm `case null` hoặc `case null, default` |
| Switch expression thiếu nhánh | Switch expression bắt buộc exhaustive | Bổ sung các enum constant, pattern còn thiếu hoặc `default` |
| Enhanced switch statement thiếu `default`/pattern bao phủ | Pattern switch, switch có null hoặc selector kiểu tham chiếu mở phải exhaustive | Bổ sung pattern bao phủ hoặc `default` phù hợp |
| Dùng guard cho mọi nhánh của một kiểu | Guard có thể trả `false`, do đó kiểu chưa được bao phủ hoàn toàn | Thêm pattern không guard hoặc `default` |
| Đặt pattern tổng quát trước pattern cụ thể | Pattern cụ thể có thể bị dominated | Sắp xếp nhánh cụ thể trước nhánh tổng quát |
| Trộn nhãn `:` và `->` trong cùng switch block | Một switch block chỉ dùng một trong hai dạng rule hoặc statement group | Chọn một kiểu nhãn nhất quán cho toàn switch block |
| Dùng `break` để trả giá trị từ switch expression | `break` không cung cấp kết quả cho switch expression | Dùng `yield value;` trong block |

Đối với code mới, arrow rule thường là lựa chọn rõ ràng vì không có fall-through ngầm. Chỉ dùng nhãn hai chấm khi cần nhóm statement theo đúng ngữ nghĩa fall-through và kiểm soát rõ điểm kết thúc từng nhóm.

## 7. Giới hạn tính năng trong Java 27

Switch pattern matching và switch expressions là các tính năng chính thức. Theo cú pháp Java 27 đã chuẩn hóa, selector có thể là `char`, `byte`, `short`, `int` hoặc kiểu tham chiếu. Phần mở rộng cho phép dùng mọi primitive type trong pattern, `instanceof` và `switch` vẫn là preview thứ năm trong JDK 27 (JEP 532). Ngày 11-11-2026, Inside Java thông báo ngừng phát triển tính năng này và cho biết nó sẽ bị loại khỏi JDK 28. Vì vậy, không xem khả năng switch trực tiếp trên `long`, `float`, `double` hoặc `boolean` qua preview đó là cú pháp Java ổn định; các ví dụ trong bài chỉ dùng dạng switch đã được chuẩn hóa.

## 8. Checklist khi viết switch

- Chọn switch statement khi cần thực thi hành động; chọn switch expression khi cần tạo ra một giá trị.
- Ưu tiên arrow rule để tránh fall-through ngoài ý muốn.
- Dùng `yield` khi block của một nhánh switch expression cần thực hiện nhiều câu lệnh rồi trả kết quả.
- Kiểm tra mọi switch expression có đầy đủ nhánh và mọi enhanced switch statement có đủ độ bao phủ.
- Với enum, cân nhắc liệt kê tất cả hằng số để compiler giúp phát hiện thay đổi của enum.
- Với sealed hierarchy, xử lý đủ các permitted subtype.
- Dùng `when` cho điều kiện phụ, đồng thời bảo đảm các guard không để hở trường hợp cần xử lý.
- Xử lý null tường minh khi selector có thể null; không dựa vào `default` để bắt null.
- Đặt pattern cụ thể trước pattern tổng quát để tránh dominance error.
- Không dựa vào tính năng preview đã bị rút hoặc chưa trở thành chuẩn trong mã production.

## Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 27 — §14.11 Switch Statement](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.11) — switch blocks, arrow rules, enhanced switch statement và exhaustive switch blocks.
- [Java Language Specification, Java SE 27 — §14.21 The `yield` Statement](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.21) — đích yield, chuyển điều khiển và giá trị kết quả.
- [Java Language Specification, Java SE 27 — §15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.28) — switch expression, result expressions, exhaustiveness và runtime evaluation.
- [Switch Expressions and Statements (Java SE 27)](https://docs.oracle.com/en/java/javase/27/language/switch-expressions-statements.html) — ví dụ arrow cases, colon cases, yield và exhaustiveness.
- [Pattern Matching with switch (Java SE 27)](https://docs.oracle.com/en/java/javase/27/language/pattern-matching-switch.html) — type patterns, `when` guards, dominance và null labels.
- [Java Language Changes by Release (Java SE 27)](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — trạng thái chính thức hoặc preview của các tính năng ngôn ngữ.
- [JEP 361: Switch Expressions](https://openjdk.org/jeps/361) — switch expressions và arrow labels được chuẩn hóa trong Java 14.
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441) — pattern matching for switch được chuẩn hóa trong Java 21.
- [Withdrawing the Primitive Patterns Preview Feature (Inside Java, 11-11-2026)](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/) — thông báo ngừng phát triển và loại bỏ preview primitive patterns khỏi JDK 28.
