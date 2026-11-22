# Guard bằng when để bổ sung điều kiện nghiệp vụ

Trong pattern switch, một pattern xác định cấu trúc hoặc kiểu dữ liệu mà một giá trị cần khớp. Tuy nhiên, đôi khi chỉ khớp kiểu là chưa đủ: chương trình còn cần kiểm tra một điều kiện nghiệp vụ, chẳng hạn chuỗi phải không rỗng, số tiền phải vượt ngưỡng hoặc trạng thái đơn hàng phải là `PAID`.

Java 21 cho phép bổ sung điều kiện đó bằng guard sử dụng từ khóa `when` ngay sau pattern trong nhãn `case`. Một nhãn guarded pattern chỉ khớp khi cả pattern và guard đều thành công. Nhờ vậy, nhiều nhánh xử lý có thể được mô tả trực tiếp trong `switch`, với điều kiện rõ ràng và biến pattern đã có kiểu an toàn.

## 1. Cú pháp guard với when

Cấu trúc cơ bản:

```java
case Pattern patternVariable when booleanExpression -> result;
```

Trong đó:

- `Pattern` xác định kiểu hoặc cấu trúc mà giá trị selector phải khớp.
- `patternVariable` là biến được binding khi pattern thành công; tên và dạng khai báo phụ thuộc pattern.
- `when` mở đầu guard, tức biểu thức điều kiện bổ sung.
- `booleanExpression` quyết định nhãn `case` có được chọn sau khi pattern khớp hay không.

Ví dụ:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case String text when text.isBlank() ->
            "Chuỗi rỗng hoặc chỉ chứa khoảng trắng";
        case String text when text.length() >= 20 ->
            "Chuỗi dài";
        case String text ->
            "Chuỗi thông thường";
        default ->
            "Kiểu dữ liệu khác";
    };
}
```

Khi selector là một String:

1. Java thử pattern `String text`.
2. Nếu pattern khớp, biến `text` được binding và guard `text.isBlank()` được đánh giá.
3. Nếu guard đúng, nhánh đầu tiên được chọn.
4. Nếu guard sai, Java tiếp tục xét nhãn `case` tiếp theo.
5. Nhãn `case String text` không có guard sẽ xử lý những chuỗi còn lại.

Guard không thay thế pattern. Pattern xác nhận kiểu; guard bổ sung điều kiện để quyết định nhánh xử lý.

## 2. Trình tự đánh giá pattern và guard

Các nhãn `case` được xét theo thứ tự xuất hiện trong khối `switch`. Với một guarded pattern label, quá trình đánh giá có thể hiểu như sau:

1. Đánh giá pattern với giá trị selector.
2. Nếu pattern không khớp, bỏ qua guard và xét nhãn tiếp theo.
3. Nếu pattern khớp, binding các biến pattern và đánh giá guard.
4. Nếu guard đúng, chọn nhánh hiện tại.
5. Nếu guard sai, tiếp tục xét các nhãn phía sau.

Ví dụ với kiểu số nguyên:

```java
static String classify(Integer value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case 0 -> "Bằng không";
        case Integer number when number < 0 -> "Số âm";
        case Integer number -> "Số dương";
    };
}
```

Các trường hợp được xử lý lần lượt:

| Giá trị | Nhãn được chọn |
|---:|---|
| `null` | `case null` |
| `0` | `case 0` |
| `-5` | `case Integer number when number < 0` |
| `12` | `case Integer number` |

Guard `number < 0` chỉ được đánh giá sau khi selector đã khớp kiểu `Integer`. Với số âm, guard đúng và nhánh tương ứng được chọn. Với số dương, guard sai nên Java tiếp tục đến pattern `Integer number` không có guard.

Ví dụ này cũng cho thấy nhãn hằng như `case 0` nên được đặt trước pattern tổng quát `case Integer number`. Nếu pattern tổng quát xuất hiện trước, nó có thể bao phủ giá trị mà nhãn hằng muốn xử lý.

## 3. Biến pattern trong guard

Biến được khai báo bởi pattern có thể được sử dụng ngay trong guard và trong phần thân của nhánh `case` tương ứng.

```java
static String validate(Object value) {
    return switch (value) {
        case null -> "Giá trị null";
        case String text when !text.isBlank()
                && text.length() <= 40 ->
            "Hợp lệ: " + text.strip();
        case String text when text.isBlank() ->
            "Không được để trống";
        case String text ->
            "Chuỗi vượt quá độ dài cho phép";
        default ->
            "Giá trị phải là String";
    };
}
```

Trong guard đầu tiên, `text` đã có kiểu `String`, vì vậy có thể gọi `isBlank()`, `length()` và các method khác của String mà không cần ép kiểu.

Toán tử `&&` trong ví dụ là toán tử logic bên trong biểu thức guard. Nó tận dụng short-circuit evaluation: nếu `!text.isBlank()` là `false`, Java không cần đánh giá tiếp điều kiện độ dài.

Phạm vi của biến pattern chỉ bao gồm guard và phần xử lý của nhãn tương ứng. Không thể sử dụng biến `text` từ một nhãn `case` trong nhãn khác hoặc sau toàn bộ câu lệnh `switch`.

## 4. Dùng guard để diễn đạt điều kiện nghiệp vụ

Guard hữu ích khi một kiểu dữ liệu có thể được chia thành nhiều nhóm theo điều kiện nghiệp vụ. Thay vì tạo nhiều lớp con chỉ để phân biệt các trạng thái, chương trình có thể giữ nguyên kiểu dữ liệu và thể hiện điều kiện ngay tại nhãn `case`.

Ví dụ phân loại yêu cầu:

```java
record Request(String type, int payloadSize) {}

static String route(Object input) {
    return switch (input) {
        case null -> "Đầu vào null";
        case Request request
                when "PAYMENT".equals(request.type())
                && request.payloadSize() > 100_000 ->
            "Chuyển đến bộ xử lý thanh toán lớn";

        case Request request
                when "PAYMENT".equals(request.type()) ->
            "Chuyển đến bộ xử lý thanh toán thông thường";

        case Request request
                when request.payloadSize() == 0 ->
            "Yêu cầu không có dữ liệu";

        case Request request ->
            "Bộ xử lý yêu cầu chung";

        default ->
            "Đầu vào không phải Request";
    };
}
```

Các nhánh đều bắt đầu từ cùng kiểu `Request`, nhưng guard tách các trường hợp theo loại yêu cầu và kích thước payload. Nhánh tổng quát cuối cùng đóng vai trò xử lý những Request không thỏa mãn các điều kiện trước đó.

Trong ứng dụng thực tế, điều kiện guard nên thể hiện một phép phân loại rõ ràng. Nếu biểu thức trở nên dài hoặc chứa nhiều quy tắc nghiệp vụ, có thể chuyển phần kiểm tra thành method có tên dễ hiểu, ví dụ `isLargePayment(request)`, rồi gọi method đó trong guard.

## 5. Guard kết hợp với record pattern

Guard có thể đi sau record pattern. Các biến được binding từ component pattern có thể được dùng trực tiếp trong guard để kiểm tra các trường của record.

```java
record Order(String status, long total) {}

static String summarize(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case Order(String status, long total)
                when status.equals("PAID") && total >= 1_000_000 ->
            "Đơn hàng giá trị lớn đã thanh toán";

        case Order(String status, long total)
                when status.equals("PAID") ->
            "Đơn hàng đã thanh toán";

        case Order(String status, long total) ->
            "Đơn hàng chưa thanh toán";

        default ->
            "Dữ liệu không phải Order";
    };
}
```

Trong nhãn đầu tiên:

- `Order(String status, long total)` khớp một record `Order` và binding hai thành phần.
- `status` có kiểu `String`, `total` có kiểu `long`.
- Guard kiểm tra đồng thời trạng thái thanh toán và tổng giá trị.
- Khi guard đúng, nhánh xử lý đơn hàng giá trị lớn đã thanh toán được chọn.

Nếu guard đầu tiên sai nhưng record pattern vẫn khớp, Java xét nhãn Order tiếp theo. Nhờ vậy, cùng một cấu trúc record có thể được phân loại theo nhiều quy tắc mà không cần viết lại các câu lệnh kiểm tra kiểu ở bên ngoài `switch`.

Lưu ý: component pattern `String status` chỉ khớp khi thành phần có giá trị là String. Nếu thành phần `status` là `null`, record pattern này không khớp; guard `status.equals(...)` sẽ không được đánh giá. Nếu mô hình cho phép trạng thái null, cần xác định rõ cách xử lý bằng component pattern phù hợp hoặc một nhánh dự phòng.

## 6. Thứ tự nhãn case, dominance và guard

Thứ tự nhãn ảnh hưởng trực tiếp đến nhánh được chọn. Java cũng có quy tắc dominance để phát hiện nhãn không bao giờ được chọn vì đã bị nhãn đứng trước bao phủ.

Có ba nguyên tắc thực hành quan trọng:

1. Đặt các nhãn hằng cụ thể trước pattern tổng quát có thể bao phủ chúng.
2. Đặt guarded pattern trước pattern không có guard cùng kiểu hoặc pattern rộng hơn có thể xử lý phần còn lại.
3. Đặt pattern tổng quát không có guard sau các trường hợp cụ thể.

Ví dụ thứ tự hợp lý:

```java
static String describe(Integer value) {
    return switch (value) {
        case null -> "null";
        case 1 -> "một";
        case Integer number when number > 0 -> "số dương khác một";
        case Integer number -> "số không dương";
    };
}
```

Nếu viết `case Integer number` trước `case 1`, nhãn `case 1` bị pattern tổng quát phía trước bao phủ và compiler báo lỗi dominance. Pattern không guard này khớp mọi giá trị Integer khác null, bao gồm cả giá trị 1.

Guarded pattern có thể đứng trước pattern tổng quát vì guard có thể sai, cho phép các giá trị còn lại tiếp tục được xét:

```java
static String describeText(Object value) {
    return switch (value) {
        case null -> "null";
        case String text when text.isBlank() -> "Chuỗi trống";
        case CharSequence sequence -> "Dữ liệu dạng chuỗi";
        default -> "Kiểu khác";
    };
}
```

Nếu giá trị là String trống, nhãn đầu tiên khớp. Nếu là String không trống, guard sai và nhãn `CharSequence` xử lý giá trị đó. Các kiểu khác triển khai `CharSequence` cũng được xử lý ở nhánh thứ hai.

Ngược lại, nếu đặt `case CharSequence sequence` không guard trước `case String text`, nhãn String phía sau bị dominance vì mọi String đều là CharSequence.

### 6.1. Vì sao nên đặt nhãn hằng trước guarded pattern?

Guard thường chứa biểu thức runtime mà compiler không thể chứng minh đầy đủ kết quả cho mọi giá trị. Do đó, compiler không nhất thiết báo lỗi khi một nhãn hằng xuất hiện sau một guarded pattern có thể khớp giá trị đó.

Ví dụ, cách viết sau có thể khiến nhãn `case 1` không bao giờ được chạy khi guard đầu tiên đúng:

```java
static String describeNumber(Integer value) {
    return switch (value) {
        case null -> "null";
        case Integer number when number > 0 -> "số dương";
        case 1 -> "một";
        case Integer number -> "số khác";
    };
}
```

Với giá trị 1, guard `number > 0` đúng và nhánh đầu tiên được chọn. Nhãn `case 1` phía sau không có cơ hội xử lý giá trị này. Đặt nhãn hằng cụ thể trước guard sẽ làm ý định rõ ràng hơn:

```java
static String describeNumber(Integer value) {
    return switch (value) {
        case null -> "null";
        case 1 -> "một";
        case Integer number when number > 0 -> "số dương khác một";
        case Integer number -> "số khác";
    };
}
```

Đây là quy tắc sắp xếp để mã dễ dự đoán và bảo trì, kể cả khi compiler không phát hiện được mọi trường hợp guard làm nhãn phía sau không thể xảy ra.

## 7. Guard false và tính exhaustive của switch

Guard chỉ bổ sung điều kiện cho một pattern. Nếu pattern khớp nhưng guard trả về `false`, nhãn đó không xử lý giá trị; Java tiếp tục tìm nhãn khác.

Vì vậy, một guarded pattern không tự động bao phủ mọi giá trị thuộc kiểu của nó. Trong Java 21, khối pattern switch dùng nhãn pattern hoặc nhãn null phải exhaustive; với switch expression, nhánh được chọn còn phải tạo ra giá trị hoặc kết thúc bằng một thao tác như `throw`.

Ví dụ:

```java
sealed interface Payment permits CardPayment, CashPayment {}

record CardPayment(long amount) implements Payment {}
record CashPayment(long amount) implements Payment {}

static String describePayment(Payment payment) {
    return switch (payment) {
        case null -> "Không có thông tin thanh toán";
        case CardPayment card when card.amount() > 0 ->
            "Thanh toán thẻ có giá trị dương";
        case CardPayment card ->
            "Thanh toán thẻ không dương";
        case CashPayment cash ->
            "Thanh toán tiền mặt";
    };
}
```

Hai pattern `CardPayment` xử lý cả trường hợp guard đúng và sai. `CashPayment` xử lý loại còn lại trong sealed hierarchy. Vì các kiểu được phép triển khai `Payment` đã được khai báo đầy đủ, switch expression có thể exhaustive mà không cần `default`.

Nếu bỏ nhãn `case CardPayment card` không guard, switch sẽ thiếu trường hợp CardPayment có số tiền không lớn hơn 0. Guard có thể sai tại runtime, nên compiler không thể coi guarded pattern là đã bao phủ toàn bộ CardPayment.

Nếu selector có thể là `null`, cần thêm nhãn `case null` khi muốn xử lý trường hợp đó. Nhãn `default` không khớp với null; nếu không có `case null`, switch trên giá trị null sẽ ném `NullPointerException`.

## 8. Guard trong switch statement và switch expression

Guard dùng cùng một cách trong cả switch statement và switch expression.

Switch expression trả về một giá trị:

```java
static String category(Object value) {
    return switch (value) {
        case null -> "null";
        case String text when text.length() > 10 -> "long text";
        case String text -> "short text";
        default -> "other";
    };
}
```

Switch statement thực hiện hành động:

```java
static void logValue(Object value) {
    switch (value) {
        case null ->
            System.out.println("Không có giá trị");

        case String text when text.startsWith("ERR") ->
            System.out.println("Lỗi: " + text);

        case String text ->
            System.out.println("Thông tin: " + text);

        default ->
            System.out.println("Kiểu dữ liệu khác");
    }
}
```

Với pattern switch, nên ưu tiên cú pháp arrow rule (`->`) để mỗi nhãn có phạm vi xử lý riêng và tránh nhầm lẫn do fall-through của nhóm câu lệnh dùng dấu hai chấm.

## 9. Guard nên đơn giản và không có side effect

Guard được đánh giá trong quá trình tìm nhãn phù hợp. Một guard có thể không được chạy nếu pattern không khớp hoặc một nhãn trước đó đã được chọn. Vì vậy, guard nên là phép kiểm tra điều kiện, không nên thực hiện hành động làm thay đổi trạng thái chương trình.

Nên viết:

```java
case Order(String status, long total)
        when status.equals("PAID") && total >= 1_000_000 ->
    processLargePaidOrder();
```

Tránh đặt thao tác thay đổi dữ liệu hoặc gửi yêu cầu ra ngoài trong guard:

```java
// Không nên: guard có side effect và phụ thuộc thứ tự đánh giá.
case Order(String status, long total)
        when chargeCustomer(total) ->
    processOrder();
```

Nếu guard gọi method và method đó ném exception, quá trình đánh giá switch kết thúc bằng exception; Java không tự chuyển sang nhãn kế tiếp. Hãy giữ guard dễ dự đoán, nhanh và tập trung vào điều kiện. Đặt hành động như ghi log, cập nhật database hoặc gọi dịch vụ vào phần thân của nhánh sau khi pattern đã được chọn.

## 10. Cú pháp Java 21 và cú pháp preview cũ

Pattern matching for switch trở thành tính năng chính thức trong Java 21 qua JEP 441. Khi viết code cho Java 21, guard được đặt sau pattern bằng từ khóa `when`:

```java
case String text when text.length() > 5 -> "Chuỗi dài";
```

Không dùng cú pháp guard preview cũ:

```java
// Cú pháp preview cũ, không dùng cho mã nguồn Java 21 hiện hành:
// case String text && text.length() > 5 -> "Chuỗi dài";
```

Trong cú pháp Java 21, toán tử `&&` vẫn được dùng bên trong biểu thức guard nếu cần kết hợp nhiều điều kiện, nhưng từ khóa `when` là dấu phân cách giữa pattern và guard. Tính năng pattern matching for switch trong Java 21 không cần bật `--enable-preview`.

## 11. Các lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `&&` thay cho `when` ngay sau pattern | Sao chép cú pháp từ các bản preview cũ | Dùng `case Type value when condition ->` |
| Dùng biến pattern trong guard nhưng khai báo pattern không có biến phù hợp | Guard không có biến cần thiết trong scope | Khai báo biến trong pattern hoặc dùng record component pattern |
| Guard đúng nhưng nhánh mong muốn không chạy | Một nhãn phía trước đã khớp và được chọn | Kiểm tra thứ tự các nhãn `case` |
| Nhãn cụ thể bị compiler báo dominated | Pattern không guard phía trước đã bao phủ kiểu hoặc giá trị đó | Đưa nhãn cụ thể lên trước pattern tổng quát |
| Switch expression không exhaustive | Guard có thể trả về false và không có nhánh dự phòng | Thêm pattern không guard hoặc nhãn phù hợp để bao phủ trường hợp còn lại |
| Switch trên null bị `NullPointerException` | `default` không xử lý null | Thêm `case null` nếu null là đầu vào hợp lệ |
| Guard thực hiện thao tác ngoài dự kiến | Guard chứa side effect hoặc method có thể ném exception | Chuyển hành động sang thân nhánh và giữ guard là phép kiểm tra |

## 12. Cách áp dụng trong Java 21

Khi thiết kế pattern switch có guard, hãy thực hiện theo trình tự:

1. Chọn pattern thể hiện đúng kiểu hoặc cấu trúc dữ liệu cần xử lý.
2. Viết guard bằng `when` để bổ sung điều kiện nghiệp vụ.
3. Dùng biến pattern trong guard và phần thân nhánh tương ứng.
4. Sắp xếp nhãn hằng, guarded pattern và pattern tổng quát theo thứ tự dễ hiểu.
5. Bổ sung nhánh không guard hoặc nhãn khác để switch xử lý đầy đủ các trường hợp.
6. Quyết định rõ cách xử lý `null` nếu selector là kiểu tham chiếu có thể nhận null.
7. Giữ guard đơn giản, không có side effect; thực hiện hành động trong nhánh được chọn.

Guard bằng `when` giúp pattern switch diễn đạt cả cấu trúc dữ liệu và điều kiện nghiệp vụ ngay trong nhãn `case`. Khi hiểu đúng thứ tự đánh giá, dominance, null và exhaustiveness, mã Java 21 sẽ rõ ràng hơn, giảm các phép kiểm tra lồng nhau và vẫn giữ được kiểm tra kiểu ở compile time.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
