# Lựa chọn giữa kiểm tra đầy đủ lúc biên dịch và nhánh dự phòng theo nghiệp vụ

Khi viết `switch` trong Java 21, cần quyết định rõ chương trình có nên xử lý tường minh mọi trường hợp mà kiểu dữ liệu cho phép hay có một nhánh dự phòng dành cho giá trị chưa biết. Với một miền dữ liệu đóng như `enum` hoặc `sealed` hierarchy, để compiler kiểm tra tính đầy đủ giúp phát hiện trường hợp mới ngay khi biên dịch lại. Với dữ liệu mở đến từ giao thức, cấu hình hoặc hệ thống bên ngoài, một nhánh `default` có thể là quy tắc nghiệp vụ cần thiết để từ chối, ghi nhận hoặc chuyển trường hợp chưa nhận diện sang xử lý thủ công.

Hai lựa chọn này phục vụ những mục tiêu khác nhau. Tính đầy đủ lúc biên dịch bảo vệ mô hình miền đã biết; nhánh dự phòng xác định hành vi khi gặp giá trị ngoài những trường hợp đã xử lý. Không nên thêm `default` chỉ để làm compiler hết báo lỗi nếu việc xuất hiện một trạng thái mới thực sự cần được lập trình viên xem xét.

## 1. Tính đầy đủ của `switch` trong Java 21

Một switch block được gọi là *exhaustive* (đầy đủ) khi mọi giá trị có thể thuộc phạm vi kiểu của selector đều có ít nhất một nhãn `case` phù hợp. Java 21 áp dụng yêu cầu này cho:

- Mọi `switch` expression. Biểu thức phải tạo ra một giá trị hoặc kết thúc bằng cách ném exception ở mọi nhánh có thể xảy ra.
- Enhanced `switch` statement. Đây là switch statement dùng pattern hoặc nhãn `null`, hoặc có kiểu selector nằm ngoài nhóm kiểu nguyên thủy/wrapper số nguyên, `String` và `enum` được hỗ trợ bởi switch statement truyền thống.

Switch statement truyền thống chỉ dùng các hằng `case` với selector kiểu số nguyên phù hợp, `String` hoặc `enum` vẫn được giữ hành vi không bắt buộc exhaustive để tương thích mã nguồn cũ. Nếu không có nhãn nào khớp và selector khác null, statement có thể kết thúc bình thường mà không chạy nhánh nào. Với mã mới cần kiểm tra đầy đủ, nên dùng switch expression hoặc enhanced switch statement.

Ví dụ switch expression không đầy đủ:

```java
static int classify(Object value) {
    return switch (value) {
        case String text -> text.length();
        case Integer number -> number;
        // Lỗi biên dịch: Object còn có thể là nhiều kiểu khác.
    };
}
```

Thêm một nhánh `default` làm switch expression đầy đủ:

```java
static int classify(Object value) {
    return switch (value) {
        case String text -> text.length();
        case Integer number -> number;
        default -> 0;
    };
}
```

Trong ví dụ này, `default` bao phủ mọi giá trị khác không được xử lý bởi các pattern trước đó. Tuy nhiên, giá trị `null` vẫn cần được xem xét riêng: `default` không khớp với selector null.

## 2. Khi miền dữ liệu đóng, để compiler phát hiện trường hợp mới

### Enum: liệt kê mọi hằng số, không thêm `default`

Một enum là tập hợp hữu hạn các hằng số đã khai báo. Switch expression có thể được compiler xác định là exhaustive khi tất cả hằng số enum đều được xử lý:

```java
enum OrderStatus {
    CREATED,
    PAID,
    CANCELLED
}

static String describe(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Đơn hàng mới tạo";
        case PAID -> "Đã thanh toán";
        case CANCELLED -> "Đã hủy";
    };
}
```

Không cần `default` vì compiler biết ba hằng số trên là toàn bộ các giá trị enum được khai báo trong phiên bản đang biên dịch. Nếu sau này thêm `REFUNDED` vào `OrderStatus` rồi biên dịch lại lớp `describe`, compiler báo switch expression chưa đầy đủ. Người phát triển phải quyết định `REFUNDED` có ý nghĩa gì trước khi build thành công.

Đây là lựa chọn phù hợp khi mọi trạng thái đều thuộc trách nhiệm nghiệp vụ của ứng dụng và trạng thái mới cần được xem xét trong code review. Một `default` như `default -> "Không xác định"` sẽ làm mất tín hiệu compile-time này.

### Sealed hierarchy: bao phủ mọi subtype được phép

`sealed` class hoặc interface giới hạn những lớp con được phép triển khai hoặc kế thừa. Compiler có thể dùng danh sách permitted subtype để xác định switch đã xử lý hết miền kiểu hay chưa.

```java
sealed interface Payment permits CardPayment, CashPayment { }

record CardPayment(String transactionId) implements Payment { }
record CashPayment(long receivedAmount) implements Payment { }

static String describe(Payment payment) {
    return switch (payment) {
        case CardPayment card -> "Thẻ: " + card.transactionId();
        case CashPayment cash -> "Tiền mặt: " + cash.receivedAmount();
    };
}
```

Switch expression trên exhaustive vì `CardPayment` và `CashPayment` là toàn bộ các subtype được phép của `Payment`. Nếu bổ sung `BankTransfer` vào mệnh đề `permits`, sau khi biên dịch lại, compiler yêu cầu bổ sung cách xử lý `BankTransfer`.

Enhanced switch statement cũng có thể tận dụng tính đầy đủ của sealed hierarchy:

```java
static void audit(Payment payment) {
    switch (payment) {
        case CardPayment card ->
            System.out.println("Giao dịch thẻ: " + card.transactionId());
        case CashPayment cash ->
            System.out.println("Tiền mặt: " + cash.receivedAmount());
    }
}
```

Vì các nhãn là type pattern, đây là enhanced switch statement và phải exhaustive. Nếu thêm subtype mới mà không thêm nhánh tương ứng, mã nguồn sẽ không biên dịch.

### Có thể kiểm tra đầy đủ mà không cần `default`

Compiler có thể xác định tính đầy đủ từ các trường hợp đã biết, thường gặp nhất là:

| Kiểu selector | Cách chứng minh exhaustive |
|---|---|
| `enum` | Có nhãn cho tất cả hằng số enum |
| `sealed` class/interface | Các pattern bao phủ tất cả permitted subtype có thể thuộc kiểu selector |
| Record | Record pattern bao phủ kiểu của record và các component tương ứng |
| Kiểu mở như `Object` hoặc `String` | Thường cần `default` vì không có tập subtype/hằng số hữu hạn để liệt kê hết |

Với sealed generic hierarchy, compiler còn xét tham số kiểu của selector. Một permitted subtype không thể có kiểu tham số tương thích với selector có thể không cần một nhánh riêng. Do đó, không nên tự suy luận danh sách nhánh chỉ từ tên các lớp trong `permits`; hãy dựa vào kết quả kiểm tra của compiler và quy tắc type coverage trong JLS.

## 3. Khi nào nên có nhánh dự phòng theo nghiệp vụ?

Một nhánh dự phòng hợp lý khi miền đầu vào có thể mở rộng độc lập với mã đang biên dịch, hoặc khi nghiệp vụ định nghĩa rõ cách xử lý dữ liệu chưa nhận diện. Ví dụ:

- Đọc mã trạng thái từ API hoặc message broker do hệ thống khác quản lý.
- Đọc cấu hình có thể được triển khai mới trước khi ứng dụng được nâng cấp.
- Xử lý sự kiện có thể được bổ sung bởi phiên bản dịch vụ khác.
- Chuyển trường hợp không hỗ trợ sang hàng đợi review, ghi log/metric hoặc trả lỗi có chủ đích.

Trong các trường hợp này, `default` là một chính sách xử lý, không đơn thuần là cách làm cho switch biên dịch được. Nhánh dự phòng cần có hành vi rõ ràng và an toàn.

Ví dụ một ứng dụng nhận mã trạng thái thanh toán từ giao thức bên ngoài:

```java
enum PaymentStatus {
    CREATED,
    PAID,
    DECLINED
}

enum Decision {
    CONTINUE,
    COMPLETE,
    RETRY,
    MANUAL_REVIEW
}

static Decision decide(PaymentStatus status) {
    return switch (status) {
        case CREATED -> Decision.CONTINUE;
        case PAID -> Decision.COMPLETE;
        case DECLINED -> Decision.RETRY;
        default -> Decision.MANUAL_REVIEW;
    };
}
```

Nhánh `default` thể hiện chính sách: trạng thái chưa được ứng dụng nhận diện phải được đưa sang review. Nếu phiên bản thư viện enum ở runtime có thêm hằng số, nhánh dự phòng vẫn có thể nhận giá trị đó. Đổi lại, nếu enum được bổ sung hằng số rồi mã nguồn được biên dịch lại, compiler sẽ không yêu cầu lập trình viên viết một nhánh riêng cho hằng số mới.

Nếu muốn phân biệt dữ liệu không hợp lệ với một trạng thái hợp lệ nhưng chưa được hỗ trợ, có thể từ chối rõ ràng:

```java
static Decision decide(PaymentStatus status) {
    return switch (status) {
        case CREATED -> Decision.CONTINUE;
        case PAID -> Decision.COMPLETE;
        case DECLINED -> Decision.RETRY;
        default -> throw new IllegalArgumentException(
                "Trạng thái thanh toán chưa được hỗ trợ: " + status);
    };
}
```

Nhánh `default` này không phải nhánh im lặng bỏ qua dữ liệu. Nó tạo ra hành vi từ chối có thể quan sát và kiểm thử. Nếu `PaymentStatus` là miền đóng do chính ứng dụng quản lý, hãy cân nhắc bỏ `default` để lần thêm trạng thái tiếp theo trở thành yêu cầu cập nhật code tại compile-time.

### Dữ liệu giao thức dạng chuỗi

Nếu đầu vào đến từ JSON, HTTP hoặc message bên ngoài, có thể giữ mã wire format ở dạng `String` và ánh xạ sang mô hình nội bộ. Vì `String` có vô số giá trị, switch expression cần nhánh dự phòng:

```java
static Decision fromWireStatus(String code) {
    return switch (code) {
        case "created" -> Decision.CONTINUE;
        case "paid" -> Decision.COMPLETE;
        case "declined" -> Decision.RETRY;
        case null -> throw new IllegalArgumentException("Thiếu status");
        default -> Decision.MANUAL_REVIEW;
    };
}
```

Ở đây, mã trạng thái chưa biết là một tình huống có thể xảy ra theo hợp đồng tích hợp, nên `default` là một phần của logic nghiệp vụ. Nhánh `null` được tách riêng để không nhầm dữ liệu bị thiếu với một mã mới chưa được hỗ trợ.

Nếu cả null và mọi giá trị chưa biết đều phải có cùng hành vi, Java 21 cho phép viết `case null, default`:

```java
static Decision fromWireStatus(String code) {
    return switch (code) {
        case "created" -> Decision.CONTINUE;
        case "paid" -> Decision.COMPLETE;
        case "declined" -> Decision.RETRY;
        case null, default -> Decision.MANUAL_REVIEW;
    };
}
```

Chỉ gộp hai trường hợp khi nghiệp vụ thật sự muốn xử lý chúng giống nhau. Trong nhiều hệ thống, null là lỗi dữ liệu còn mã mới là tình huống tương thích phiên bản; tách chúng ra giúp log, metric và phản hồi chính xác hơn.

## 4. `default` làm thay đổi khả năng phát hiện thay đổi miền kiểu

Hãy so sánh hai cách viết với enum:

```java
// A. Không có default: compiler buộc xử lý từng hằng số đã biết.
static String label(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case CANCELLED -> "Cancelled";
    };
}
```

```java
// B. Có default: chấp nhận mọi hằng số khác theo chính sách fallback.
static String label(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case CANCELLED -> "Cancelled";
        default -> "Other status";
    };
}
```

| Tiêu chí | Không có `default` | Có `default` |
|---|---|---|
| Thêm enum constant rồi biên dịch lại | Compiler yêu cầu xử lý constant mới | Constant mới đi vào nhánh dự phòng |
| Thêm permitted subtype vào sealed hierarchy rồi biên dịch lại | Compiler yêu cầu bổ sung pattern | Subtype mới đi vào nhánh dự phòng |
| Dữ liệu mở/không biết trước | Cần mô hình đầu vào phù hợp và nhánh xử lý rõ ràng | Có thể xử lý giá trị chưa nhận diện |
| Khả năng phát hiện thiếu logic nghiệp vụ khi phát triển | Cao hơn với miền kiểu đóng | Thấp hơn vì nhánh dự phòng che các trường hợp mới |
| Trách nhiệm của code | Liệt kê từng trường hợp đã biết | Định nghĩa chính sách cho phần còn lại |

Đối với sealed hierarchy, hiệu ứng tương tự: thêm subtype được phép rồi biên dịch lại switch không có `default` sẽ tạo lỗi compile-time nếu subtype mới chưa được bao phủ. Có `default`, compiler xem switch đã đầy đủ và không yêu cầu nhánh riêng.

Vì vậy, hãy xem `default` như một quyết định về khả năng tiến hóa của mô hình dữ liệu. Nếu mọi subtype mới cần một thuật toán hoặc quyết định nghiệp vụ riêng, bỏ `default`. Nếu hệ thống phải tiếp tục hoạt động khi nhận giá trị mới và đã có chính sách fallback an toàn, giữ `default`.

## 5. Guard `when` không tự chứng minh tính đầy đủ

Một pattern có guard chỉ khớp khi cả pattern lẫn điều kiện `when` đều đúng. Vì guard có thể trả về false, compiler không dùng một guarded pattern thông thường để chứng minh toàn bộ kiểu đã được bao phủ.

Ví dụ sau chưa exhaustive dù `Shape` chỉ có hai permitted subtype:

```java
sealed interface Shape permits Circle, Rectangle { }
record Circle(double radius) implements Shape { }
record Rectangle(double width, double height) implements Shape { }

static double area(Shape shape) {
    return switch (shape) {
        case Circle circle when circle.radius() > 0 ->
            Math.PI * circle.radius() * circle.radius();
        case Rectangle rectangle
                when rectangle.width() > 0 && rectangle.height() > 0 ->
            rectangle.width() * rectangle.height();
        // Lỗi biên dịch: guard có thể false.
    };
}
```

Có hai cách để xử lý đầy đủ. Cách thứ nhất là đặt logic điều kiện bên trong nhánh pattern không guard:

```java
static double area(Shape shape) {
    return switch (shape) {
        case Circle circle -> circle.radius() > 0
                ? Math.PI * circle.radius() * circle.radius()
                : 0;
        case Rectangle rectangle ->
                rectangle.width() > 0 && rectangle.height() > 0
                        ? rectangle.width() * rectangle.height()
                        : 0;
    };
}
```

Cách thứ hai là giữ guard cho trường hợp chính và bổ sung pattern không guard cho cùng subtype để xử lý phần còn lại. Hãy chọn kết quả fallback theo quy tắc miền, ví dụ trả diện tích bằng 0, ném exception hoặc đánh dấu dữ liệu không hợp lệ.

## 6. Null là một trường hợp riêng

Trong Java 21, `default` không khớp với selector `null`. Nếu selector là null và switch không có nhãn `case null`, Java ném `NullPointerException`, kể cả khi switch đã có `default`.

```java
static String describe(String value) {
    return switch (value) {
        case "java" -> "Java";
        default -> "Một giá trị khác";
    };
}
```

Gọi `describe(null)` sẽ ném `NullPointerException`. Nếu null có ý nghĩa nghiệp vụ, hãy mô tả rõ:

```java
static String describe(String value) {
    return switch (value) {
        case "java" -> "Java";
        case null -> "Không có giá trị";
        default -> "Một giá trị khác";
    };
}
```

Với một switch cần bao phủ null và mọi giá trị còn lại bằng cùng một chính sách, dùng `case null, default`. Không viết `case null, String text`; Java 21 chỉ cho phép kết hợp nhãn null với `default` trong cùng một case label.

## 7. Exhaustive lúc biên dịch vẫn có thể không khớp lúc chạy

Tính đầy đủ mà compiler chứng minh dựa trên kiểu và các subtype/hằng số nhìn thấy lúc biên dịch. Khi các thành phần được biên dịch riêng và phiên bản kiểu thay đổi, runtime có thể gặp giá trị mà switch cũ chưa biết.

Ví dụ: một module khai báo sealed interface `Payment` với hai subtype `CardPayment` và `CashPayment`. Module khác biên dịch switch expression không có `default` dựa trên hai subtype đó. Sau này module khai báo `Payment` được bổ sung `BankTransfer`, nhưng module chứa switch vẫn dùng bytecode cũ. Nếu một `BankTransfer` đi vào switch, không có nhánh nào khớp và Java 21 có thể ném `MatchException`.

Điều này cũng có thể xảy ra khi enum thay đổi tập hằng số giữa thời điểm biên dịch switch và thời điểm chạy, hoặc khi nested record pattern được xem là đầy đủ theo kiểu nhưng component thực tế là null. Vì thế:

- Khi thay đổi enum hoặc sealed hierarchy, hãy biên dịch lại các module phụ thuộc có switch exhaustive.
- Nếu ứng dụng phải tương thích với phiên bản thư viện hoặc dịch vụ có thể tiến hóa độc lập, cân nhắc `default` với hành vi dự phòng đã được định nghĩa.
- Không xem `MatchException` là cách xử lý nghiệp vụ cho trạng thái mới. Đây là dấu hiệu switch exhaustive theo thông tin biên dịch nhưng không tìm được nhãn phù hợp lúc chạy.
- Kiểm tra null ở selector và các component lồng nhau nếu mô hình dữ liệu cho phép null.

`MatchException` là kiểu exception của Java 21, không phải API preview. Nó có thể xuất hiện khi một switch expression hoặc enhanced switch statement được xác định exhaustive lúc biên dịch nhưng không tìm thấy nhãn phù hợp ở runtime.

## 8. Chọn cách viết theo loại miền dữ liệu

| Bối cảnh | Cách viết nên cân nhắc | Lý do |
|---|---|---|
| Enum nội bộ do cùng ứng dụng quản lý | Switch expression liệt kê mọi constant, không `default` | Thêm constant sẽ tạo yêu cầu xử lý khi biên dịch lại |
| Sealed hierarchy đại diện các biến thể nghiệp vụ | Pattern switch liệt kê mọi permitted subtype, không `default` | Thêm subtype buộc cập nhật logic xử lý |
| Dữ liệu protocol có thể thêm mã mới | `default` ánh xạ sang trạng thái unknown/review hoặc từ chối | Dịch vụ vẫn có chính sách cho mã chưa nhận diện |
| Selector có thể null và null cần xử lý | `case null` riêng hoặc `case null, default` | Null không được bao phủ bởi `default` đơn lẻ |
| Guarded pattern có thể không đúng | Bổ sung pattern không guard hoặc `default` theo nghiệp vụ | Guard không chứng minh type coverage |
| Thay đổi sealed/enum giữa các module triển khai độc lập | Cân nhắc fallback và quản lý phiên bản/recompile | Tránh để bytecode cũ gặp giá trị mới mà không có chính sách |

Một số nguyên tắc thực hành:

1. Ưu tiên switch expression cho phép biến đổi một giá trị enum hoặc sealed type thành kết quả; compiler buộc mọi nhánh phải trả kết quả hoặc ném exception.
2. Với miền kiểu đóng, không thêm `default` chỉ để tránh cập nhật switch khi mô hình thay đổi.
3. Với miền đầu vào mở, viết `default` như một quy tắc nghiệp vụ: ghi log, tăng metric, chuyển review, trả trạng thái unknown hoặc từ chối rõ ràng.
4. Xử lý null riêng nếu null có thể xuất hiện và có ý nghĩa khác với giá trị chưa biết.
5. Không dựa vào guard `when` để chứng minh switch đã bao phủ một subtype.
6. Khi nâng phiên bản enum hoặc sealed hierarchy, biên dịch lại các module có switch exhaustive và chạy kiểm thử tích hợp trên phiên bản kiểu mới.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification, Java SE 21 — Exhaustive Switch Blocks (Section 14.11.1.1)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java Language Specification, Java SE 21 — The Switch Block of a switch Statement (Section 14.11.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.2)
- [Java Language Specification, Java SE 21 — Switch Expressions (Section 15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java SE 21 API — MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
