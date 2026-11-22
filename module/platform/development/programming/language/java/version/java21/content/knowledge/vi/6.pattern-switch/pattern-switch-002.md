# Switch statement và switch expression khi dùng pattern

Trong Java 21, Pattern Matching for `switch` đã trở thành tính năng ổn định (JEP 441). Một nhánh `case` có thể kiểm tra kiểu của giá trị bằng type pattern hoặc phân rã record bằng record pattern, sau đó dùng các biến được bind ngay trong nhánh đó. Cùng một khả năng có thể dùng trong `switch statement` để thực hiện hành động hoặc trong `switch expression` để tạo ra một giá trị.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), mục tiêu là chọn đúng dạng switch cho luồng xử lý, viết các nhánh dễ đọc và bảo đảm các trường hợp cần thiết được bao phủ. Các ví dụ dưới đây dùng cú pháp đã ổn định trong Java 21; không cần bật preview.

## Pattern trong switch hoạt động như thế nào?

Switch truyền thống thường chọn nhánh theo hằng số như số nguyên, chuỗi hoặc enum. Pattern matching mở rộng cách chọn nhánh: mỗi nhãn `case` có thể kiểm tra kiểu của selector và bind giá trị đó vào một biến có kiểu phù hợp.

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Chuỗi có " + text.length() + " ký tự";
        case Integer number -> "Số nguyên: " + number;
        case null -> "Không có giá trị";
        default -> "Kiểu dữ liệu khác";
    };
}
```

`case String text` chỉ khớp khi giá trị là một `String`; bên trong nhánh, biến `text` đã có kiểu `String`. Tương tự, `number` có kiểu `Integer`. Nếu một nhánh không khớp, switch xét các nhánh tiếp theo. `default` xử lý những giá trị không khớp với các nhãn trước đó.

Pattern có thể là record pattern. Ví dụ, với `record Point(int x, int y) {}`, nhãn `case Point(var x, var y)` vừa kiểm tra kiểu `Point`, vừa lấy hai component vào biến `x` và `y`. Các nested record pattern cũng có thể được dùng trong nhãn `case` để phân rã cấu trúc nhiều tầng.

## Chọn switch statement hay switch expression

Hai dạng switch có thể dùng cùng pattern, nhưng mục đích của chúng khác nhau:

| Tiêu chí | Switch statement | Switch expression |
| --- | --- | --- |
| Mục đích | Thực hiện hành động hoặc thay đổi trạng thái | Tính ra một giá trị từ selector |
| Cách viết nhánh | Thường dùng `->` với một câu lệnh hoặc một block | Dùng `->` với biểu thức hoặc block tạo ra giá trị |
| Giá trị trả về | Không tạo giá trị cho biểu thức bao quanh | Mọi nhánh phải tạo ra giá trị tương thích |
| Block nhiều câu lệnh | Viết các hành động trong block | Dùng `yield` để cung cấp giá trị cho switch expression |
| Khi phù hợp | Ghi log, cập nhật trạng thái, gọi dịch vụ hoặc điều phối hành động | Chuyển đổi dữ liệu, tạo thông điệp, tính kết quả hoặc chọn giá trị |

### Dùng switch statement để thực hiện hành động

Giả sử một hệ thống nhận kết quả thanh toán và cần cập nhật các thành phần khác nhau tùy theo kiểu kết quả:

Các tên `ledger`, `notification`, `reviewQueue` và `auditLog` dưới đây đại diện cho các dịch vụ mà ứng dụng đã cung cấp.

```java
sealed interface PaymentResult
        permits Paid, Rejected, NeedsReview {}

record Paid(String transactionId) implements PaymentResult {}
record Rejected(String reason) implements PaymentResult {}
record NeedsReview(String caseId) implements PaymentResult {}

static void process(PaymentResult result) {
    switch (result) {
        case null -> System.out.println("Thiếu kết quả thanh toán");
        case Paid(var transactionId) ->
                ledger.recordSuccess(transactionId);
        case Rejected(var reason) ->
                notification.sendFailure(reason);
        case NeedsReview(var caseId) -> {
            reviewQueue.enqueue(caseId);
            auditLog.record("Payment needs review: " + caseId);
        }
    }
}
```

Đây là switch statement vì mỗi nhánh thực hiện hành động và không cần tạo ra một giá trị cho biểu thức bên ngoài. Nhánh `NeedsReview` có nhiều câu lệnh nên được đặt trong block. Với arrow rule (`->`), mỗi nhánh là một đơn vị độc lập và không tự động rơi xuống nhánh kế tiếp; không cần viết `break` ở cuối nhánh.

Vì `PaymentResult` là sealed và switch đã liệt kê đủ các kiểu con được phép, switch này bao phủ các giá trị khác `null`. `case null` xử lý riêng giá trị rỗng. Nếu sau này thêm một kiểu con mới vào hierarchy mà không cập nhật switch, trình biên dịch sẽ báo switch không còn exhaustive khi biên dịch lại.

### Dùng switch expression để tạo ra giá trị

Nếu cùng kết quả thanh toán cần được chuyển thành một thông điệp, switch expression thể hiện trực tiếp mối quan hệ giữa kiểu kết quả và giá trị đầu ra:

```java
static String message(PaymentResult result) {
    return switch (result) {
        case null -> "Chưa có kết quả thanh toán";
        case Paid(var transactionId) ->
                "Thanh toán thành công: " + transactionId;
        case Rejected(var reason) ->
                "Thanh toán bị từ chối: " + reason;
        case NeedsReview(var caseId) ->
                "Thanh toán cần kiểm tra: " + caseId;
    };
}
```

Switch expression là một biểu thức, nên kết quả của nó có thể được `return`, gán vào biến hoặc truyền làm đối số. Mỗi nhánh phải cung cấp một giá trị tương thích với kiểu kết quả của switch expression. Khi các nhánh cần nhiều thao tác trước khi tạo giá trị, dùng block và `yield`:

```java
static String message(PaymentResult result) {
    return switch (result) {
        case null -> "Chưa có kết quả thanh toán";
        case Paid(var transactionId) ->
                "Thanh toán thành công: " + transactionId;
        case Rejected(var reason) -> {
            String normalized = reason.strip();
            yield "Thanh toán bị từ chối: " + normalized;
        }
        case NeedsReview(var caseId) ->
                "Thanh toán cần kiểm tra: " + caseId;
    };
}
```

`yield` cung cấp giá trị của block cho switch expression. Nó không tương đương `return`: `return` thoát khỏi phương thức, còn `yield` chỉ kết thúc nhánh block của switch expression và trả kết quả cho biểu thức đó.

## Dùng type pattern và record pattern trong cùng switch

Switch có thể phối hợp nhiều dạng nhãn, bao gồm hằng số, type pattern và record pattern. Điều này hữu ích khi một API nhận đầu vào tổng quát nhưng ứng dụng cần xử lý theo cấu trúc cụ thể.

```java
record User(String name, String email) {}
record Order(String code, User customer, long totalInCents) {}

static String summary(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case Order(String code, User(var name, var email), var total) ->
                "Đơn " + code + " của " + name
                        + " (" + email + "), tổng " + total;
        case User(var name, var email) ->
                "Người dùng " + name + " (" + email + ")";
        case String text -> "Văn bản: " + text;
        case Integer number -> "Số: " + number;
        default -> "Dữ liệu chưa được hỗ trợ";
    };
}
```

Nhãn `Order(...)` phân rã cả record khách hàng bên trong. Các biến được bind chỉ có phạm vi trong nhánh tương ứng. Nhờ vậy, không cần ép kiểu thủ công hoặc gọi accessor lặp lại sau khi đã kiểm tra kiểu.

Trong thực tế, nếu selector đã có kiểu cụ thể và các trường hợp chỉ khác nhau bởi trạng thái, có thể dùng enum hoặc điều kiện đơn giản. Pattern switch phát huy tác dụng khi các nhánh phụ thuộc vào kiểu thực tế hoặc cấu trúc dữ liệu của giá trị.

## Thêm điều kiện bằng guard when

Đôi khi kiểu dữ liệu chưa đủ để quyết định nhánh. Guard `when` bổ sung một điều kiện sau khi pattern đã khớp:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String text when text.isBlank() -> "Chuỗi rỗng hoặc chỉ có khoảng trắng";
        case String text -> "Chuỗi: " + text;
        case Integer number when number >= 0 -> "Số không âm: " + number;
        case Integer number -> "Số âm: " + number;
        default -> "Kiểu khác";
    };
}
```

Trình tự xử lý của một nhánh có guard là:

1. Kiểm tra giá trị có khớp pattern hay không.
2. Nếu pattern khớp, bind các biến như `text` hoặc `number`.
3. Đánh giá điều kiện `when` bằng các biến vừa bind.
4. Nếu guard đúng, thực hiện nhánh; nếu sai, tiếp tục xét nhánh tiếp theo.

Guard nên thể hiện điều kiện nghiệp vụ ngắn gọn. Nếu điều kiện dài, có nhiều phép kiểm tra hoặc được dùng ở nhiều nơi, hãy tách thành phương thức có tên rõ ràng.

Một guard không mặc nhiên bao phủ toàn bộ giá trị của kiểu đó. Ví dụ, `case String text when text.length() > 5` chỉ khớp một phần các giá trị `String`. Nếu switch cần exhaustive, phải có thêm nhánh bao phủ các chuỗi còn lại, chẳng hạn `case String text`, hoặc một nhánh tổng quát phù hợp.

## Xử lý null và default

Pattern switch có quy tắc riêng cho `null`:

- Type pattern như `case String text` không khớp với `null`.
- `default` không xử lý `null`.
- Nếu selector là `null` và switch không có nhãn `case null`, switch ném `NullPointerException` khi thực thi.
- Có thể dùng `case null` để xử lý rõ đầu vào rỗng, hoặc chủ động bảo đảm selector không null trước khi vào switch.

Ví dụ:

```java
static String safeLabel(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case String text -> text;
        default -> "Không phải chuỗi";
    };
}
```

Ở đây, `default` bao phủ mọi giá trị khác `null` không khớp với `String`; `case null` là nhánh riêng. Nếu hợp đồng đầu vào yêu cầu không null, có thể dùng `Objects.requireNonNull(value)` trước switch để báo lỗi ngay tại ranh giới phù hợp.

## Exhaustiveness: bảo đảm các trường hợp đã được bao phủ

Switch expression luôn phải exhaustive: trình biên dịch phải xác định được rằng mọi giá trị có thể có của selector đều được xử lý. Switch statement sử dụng pattern label cũng phải exhaustive. Đây là điểm quan trọng khi thiết kế pattern switch, đặc biệt với các hierarchy sealed.

Với một sealed hierarchy, trình biên dịch biết những kiểu con trực tiếp được phép. Nếu các nhánh đã bao phủ tất cả kiểu con đó, không cần thêm `default`:

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

Khi thêm một kiểu con mới được phép, ví dụ `Triangle`, trình biên dịch có thể phát hiện switch trên chưa xử lý kiểu mới. Không thêm `default` một cách máy móc nếu mục tiêu là để compiler nhắc cập nhật logic khi mô hình sealed thay đổi.

Với kiểu mở như `Object` hoặc interface thông thường mà tập hợp triển khai không đóng, hãy dùng `default` để bao phủ những kiểu chưa biết:

```java
static String typeName(Object value) {
    return switch (value) {
        case String text -> "String";
        case Integer number -> "Integer";
        default -> "Kiểu khác";
    };
}
```

Exhaustiveness ở thời điểm biên dịch không đồng nghĩa với xử lý `null`. Một switch có `default` vẫn có thể ném `NullPointerException` nếu selector là `null` và không có `case null`.

## Thứ tự nhánh và quy tắc dominance

Các pattern rộng có thể bao phủ pattern hẹp hơn. Nếu đặt nhánh rộng trước, nhánh hẹp phía sau có thể không bao giờ được chạy và bị trình biên dịch báo lỗi do bị *dominated*.

Ví dụ, `CharSequence` bao gồm `String`. Vì vậy, đặt `case CharSequence text` trước `case String text` khiến nhánh `String` bị nhánh đầu tiên bao phủ hoàn toàn. Hãy đặt nhánh cụ thể trước nhánh tổng quát:

```java
static String kind(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String";
        case CharSequence text -> "CharSequence khác String";
        default -> "Kiểu khác";
    };
}
```

Một số nguyên tắc khi sắp xếp nhánh:

- Đặt pattern cụ thể trước pattern tổng quát có thể bao phủ nó.
- Đặt nhánh có guard trước nhánh cùng pattern không có guard, để điều kiện đặc biệt có cơ hội được xét trước.
- Nếu nhánh không có guard đã bao phủ một pattern, nhánh pattern tương tự ở sau có thể bị coi là unreachable.
- Đặt `default` ở cuối để dễ đọc và tránh che khuất các nhánh cụ thể.

Ví dụ, `case String text` đặt trước `case String text when text.isBlank()` sẽ làm nhánh có guard bị dominated. Đổi thứ tự để kiểm tra chuỗi trắng trước, rồi mới xử lý mọi chuỗi còn lại.

## Chọn giữa pattern switch và cách viết khác

| Bài toán | Cách tiếp cận phù hợp |
| --- | --- |
| Chọn hành động theo kiểu dữ liệu hoặc record | Pattern switch statement |
| Chuyển nhiều kiểu đầu vào thành một kết quả | Pattern switch expression |
| Phân loại theo enum hoặc một vài hằng số | Switch thông thường thường đủ rõ |
| Một điều kiện đơn giản trên một biến | `if` có thể ngắn gọn hơn |
| Mỗi kiểu có hành vi riêng và hệ phân cấp mở rộng thường xuyên | Đa hình qua phương thức có thể dễ duy trì hơn |
| Sealed hierarchy cần buộc các nơi xử lý cập nhật khi có kiểu mới | Pattern switch exhaustive, tránh `default` không cần thiết |

Không nên chuyển mọi chuỗi `if/else` thành switch chỉ vì Java 21 hỗ trợ pattern. Chọn switch khi các nhánh là những trường hợp song song của cùng một giá trị và việc đặt chúng cạnh nhau làm rõ quy tắc xử lý.

## Quy trình áp dụng trong dự án Java 21

1. **Xác định mục đích.** Nếu cần thực hiện hành động, chọn switch statement; nếu cần một giá trị kết quả, chọn switch expression.
2. **Chọn pattern theo dữ liệu.** Dùng type pattern cho kiểu đối tượng; dùng record pattern khi cần lấy component của record.
3. **Liệt kê các trường hợp hợp lệ.** Nếu dùng sealed hierarchy, kiểm tra các kiểu con được phép và quyết định có cần nhánh `default` hay không.
4. **Xử lý null rõ ràng.** Dùng `case null` nếu null là đầu vào có thể gặp; nếu không, xác thực trước switch.
5. **Bổ sung guard có chủ đích.** Dùng `when` cho điều kiện phụ thuộc vào biến đã bind và bảo đảm còn nhánh bao phủ các giá trị guard từ chối.
6. **Kiểm tra dominance.** Đặt pattern cụ thể trước pattern rộng và guard trước nhánh tổng quát cùng kiểu.
7. **Kiểm tra mọi nhánh.** Switch expression phải tạo giá trị cho mọi trường hợp; switch statement có pattern label cũng phải exhaustive. Với sealed type, biên dịch lại sau khi thay đổi danh sách kiểu con.
8. **Biên dịch đúng mục tiêu.** Dùng JDK 21 hoặc cấu hình `--release 21` để bảo đảm cú pháp và API được kiểm tra theo Java 21.

Pattern matching trong switch giúp đặt việc kiểm tra kiểu, phân rã dữ liệu và hành động tương ứng tại cùng một nơi. Switch statement phù hợp với xử lý có tác động; switch expression phù hợp với chuyển đổi thành kết quả. Khi kết hợp với sealed hierarchy, xử lý `null` rõ ràng và sắp xếp pattern đúng thứ tự, mã có thể được kiểm tra tính đầy đủ tốt hơn và dễ bảo trì hơn.
