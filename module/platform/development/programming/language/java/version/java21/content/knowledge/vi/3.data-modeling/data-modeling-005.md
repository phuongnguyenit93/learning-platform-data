# Sealed class, sealed interface và tập hợp kiểu con được phép

Trong Java 21, `sealed class` và `sealed interface` giúp mô hình hóa một hệ phân cấp kiểu có tập hợp kiểu con được kiểm soát. Chúng phù hợp khi miền nghiệp vụ có một số biến thể đã biết và ứng dụng cần thể hiện rõ những biến thể hợp lệ đó. Thay vì cho phép bất kỳ mã nào cũng có thể triển khai interface hoặc kế thừa class, kiểu sealed khai báo những kiểu nào được phép kế thừa hoặc triển khai trực tiếp.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), đây là công cụ thiết kế mô hình dữ liệu và hợp đồng API. Hãy dùng nó khi tập hợp biến thể thực sự có giới hạn và cần được kiểm tra ở thời điểm biên dịch. Với một extension point dành cho plugin hoặc bên thứ ba, interface thông thường vẫn có thể là lựa chọn phù hợp hơn.

## Sealed type giải quyết vấn đề gì?

Một interface thông thường có thể được triển khai bởi những lớp mà tác giả API chưa biết trước. Điều đó hữu ích với API mở, nhưng đôi khi khiến mã gọi phải dự phòng cho những kiểu ngoài dự kiến. Ví dụ, một kết quả xử lý đơn hàng chỉ có thể là thành công, bị từ chối hoặc cần xác minh thêm. Nếu mô hình chỉ dùng một interface mở, trình biên dịch không thể biết chắc ba trường hợp đó đã bao phủ toàn bộ các biến thể hợp lệ.

Sealed type biến giới hạn của mô hình thành một phần của khai báo kiểu. Trình biên dịch biết các kiểu con trực tiếp được phép, có thể kiểm tra cấu trúc phân cấp và hỗ trợ kiểm tra tính đầy đủ của `switch` expression khi dùng pattern matching.

```java
sealed interface OrderResult
        permits Accepted, Rejected, NeedsReview {}

record Accepted(String orderId) implements OrderResult {}
record Rejected(String reason) implements OrderResult {}
record NeedsReview(String orderId, String note) implements OrderResult {}
```

Trong ví dụ, `OrderResult` chỉ cho phép ba kiểu triển khai trực tiếp đã liệt kê. Các record là `final` một cách ngầm định, nên chúng không thể được kế thừa tiếp.

## Ba cách xác định khả năng kế thừa

Mỗi kiểu con trực tiếp được phép của một sealed class hoặc sealed interface phải xác định rõ hệ phân cấp sẽ tiếp tục được kiểm soát hay được mở rộng:

| Khai báo | Ý nghĩa | Cách dùng thường gặp |
| --- | --- | --- |
| `final` | Không cho phép có lớp con tiếp theo | Một biến thể cụ thể đã hoàn chỉnh |
| `sealed` | Tiếp tục giới hạn các kiểu con trực tiếp bằng danh sách `permits` riêng | Một nhánh có các biến thể con đã biết |
| `non-sealed` | Mở nhánh đó cho phép kế thừa hoặc triển khai tiếp theo quy tắc truy cập thông thường | Một nhánh cần cho phép mở rộng |

Record vốn là kiểu `final`, vì vậy record có thể là kiểu con được phép mà không cần ghi thêm từ khóa `final`. Với class thông thường, hãy khai báo rõ một trong ba trạng thái trên.

Ví dụ về sealed class có một nhánh đóng và một nhánh mở:

```java
sealed abstract class Document permits Invoice, DraftDocument {}

final class Invoice extends Document {}

non-sealed class DraftDocument extends Document {}

// Được phép vì DraftDocument đã mở nhánh kế thừa.
final class InternalDraft extends DraftDocument {}
```

`Invoice` là một kiểu lá của hệ phân cấp. `DraftDocument` là kiểu con trực tiếp được phép của `Document`, nhưng vì khai báo `non-sealed`, các kiểu khác có thể kế thừa nó theo quy tắc truy cập thông thường. Điều đó không làm `Document` trở thành kiểu mở hoàn toàn: tập hợp kiểu con trực tiếp của `Document` vẫn được kiểm soát.

Một nhánh cũng có thể tiếp tục sealed:

```java
sealed abstract class Message permits UserMessage, SystemMessage {}

sealed abstract class UserMessage extends Message
        permits TextMessage, ImageMessage {}

final class SystemMessage extends Message {}
final class TextMessage extends UserMessage {}
final class ImageMessage extends UserMessage {}
```

Ở đây, `Message` cho phép hai kiểu con trực tiếp. `UserMessage` tiếp tục giới hạn nhánh của nó thành `TextMessage` và `ImageMessage`. Một hệ phân cấp như vậy biểu diễn được cấu trúc nhiều tầng mà mỗi tầng vẫn xác định rõ những biến thể hợp lệ.

## Khai báo permits và quy tắc vị trí kiểu con

Danh sách sau `permits` phải chứa các kiểu con trực tiếp của sealed type. Một kiểu được liệt kê không thể chỉ là kiểu cháu ở sâu hơn trong hệ phân cấp; nó phải trực tiếp `extends` sealed class hoặc trực tiếp `implements` sealed interface.

Các kiểu được phép phải tuân thủ quy tắc vị trí:

- Nếu sealed type nằm trong một named module, các kiểu con được phép phải nằm trong cùng module. Chúng có thể thuộc package khác nhau trong module đó.
- Nếu sealed type nằm trong unnamed module, các kiểu con được phép phải nằm trong cùng package.
- Mỗi kiểu con trực tiếp phải xác định trạng thái `final`, `sealed` hoặc `non-sealed`; record đã là `final` ngầm định.

Thông thường, hãy viết rõ danh sách `permits` để người đọc thấy hợp đồng của hệ phân cấp ngay tại khai báo sealed type. Java cho phép bỏ `permits` khi tất cả kiểu con trực tiếp được khai báo trong cùng compilation unit; khi đó trình biên dịch suy ra danh sách từ các khai báo trong compilation unit đó. Nếu các kiểu nằm ở các file nguồn riêng, hãy khai báo `permits` tường minh.

Ví dụ interface và các record triển khai nó có thể được đặt trong cùng file nguồn:

```java
sealed interface Payment
        permits CardPayment, CashPayment, BankTransfer {}

record CardPayment(String lastFour, long amountInCents)
        implements Payment {}

record CashPayment(long amountInCents) implements Payment {}

final class BankTransfer implements Payment {
    private final String reference;

    BankTransfer(String reference) {
        this.reference = reference;
    }

    String reference() {
        return reference;
    }
}
```

Nếu đặt các kiểu này trong những file riêng của một dự án chạy trên classpath (unnamed module), chúng vẫn phải ở cùng package. Với named module, chúng phải thuộc cùng module, dù có thể ở package khác.

## Kết hợp với pattern matching trong switch của Java 21

Pattern Matching for `switch` và Record Patterns đã là tính năng ổn định trong Java 21. Khi kết hợp với sealed type, switch expression có thể xử lý từng biến thể và để trình biên dịch kiểm tra tính đầy đủ của các nhánh.

```java
sealed interface Payment
        permits CardPayment, CashPayment, BankTransfer {}

record CardPayment(String lastFour, long amountInCents)
        implements Payment {}

record CashPayment(long amountInCents) implements Payment {}

final class BankTransfer implements Payment {
    private final String reference;

    BankTransfer(String reference) {
        this.reference = reference;
    }

    String reference() {
        return reference;
    }
}

final class PaymentDescription {
    static String describe(Payment payment) {
        return switch (payment) {
            case null -> "Chưa chọn phương thức thanh toán";
            case CardPayment(var lastFour, var amount) ->
                    "Thẻ kết thúc bằng " + lastFour + ", số tiền " + amount;
            case CashPayment(var amount) -> "Tiền mặt, số tiền " + amount;
            case BankTransfer transfer -> "Chuyển khoản: " + transfer.reference();
        };
    }
}
```

Các nhánh đã bao phủ cả ba kiểu con được phép, nên switch expression không cần nhánh `default`. `case null` được viết riêng vì `null` không tự khớp với type pattern; nhánh này cũng làm rõ cách xử lý dữ liệu thiếu. Nếu hợp đồng của hàm không chấp nhận `null`, có thể kiểm tra và từ chối đầu vào ở ranh giới phù hợp thay vì trả về thông báo.

Khi thêm một kiểu con mới vào `permits`, các switch expression đang xử lý đầy đủ những biến thể cũ có thể cần được cập nhật. Trình biên dịch sẽ chỉ ra những switch expression không còn đầy đủ khi biên dịch lại cùng định nghĩa kiểu mới. Đây là lợi ích lớn khi mô hình thực sự có tập hợp biến thể đóng: thay đổi mô hình có thể làm lộ ra những nơi xử lý còn thiếu.

Nếu một kiểu con trực tiếp được khai báo `non-sealed`, nhánh đó có thể có các kiểu con chưa biết trước. Một type pattern cho chính kiểu `non-sealed` đó có thể bao phủ cả các lớp kế thừa nó; nếu nghiệp vụ cần phân biệt sâu hơn, hãy thiết kế nhánh xử lý tương ứng hoặc dùng một mô hình kiểu khác.

## Chọn sealed class hay sealed interface?

Hai dạng này phục vụ cùng mục tiêu giới hạn hệ phân cấp, nhưng có vai trò thiết kế khác nhau:

| Tiêu chí | Sealed interface | Sealed class |
| --- | --- | --- |
| Quan hệ kiểu | Các kiểu con trực tiếp `implements` interface | Các kiểu con trực tiếp `extends` class |
| Kế thừa trạng thái và triển khai | Không cung cấp trạng thái instance hoặc constructor dùng chung | Có thể chứa state, constructor và phương thức dùng chung |
| Khả năng kết hợp | Một class có thể triển khai nhiều interface | Một class chỉ có một superclass trực tiếp |
| Khi nên chọn | Các biến thể có thể khác nhau về nền tảng nhưng cùng tuân theo một hợp đồng | Các biến thể có chung trạng thái hoặc hành vi nền tảng phù hợp để kế thừa |

Ví dụ, `Payment` thường hợp với sealed interface vì thẻ, tiền mặt và chuyển khoản là các dạng thanh toán có thể có dữ liệu và cách xử lý khác nhau. Một hệ thống tài liệu có các loại tài liệu dùng chung mã định danh, trạng thái và quy tắc vòng đời có thể cân nhắc sealed abstract class làm lớp cơ sở.

## Sealed type khác enum và interface thông thường thế nào?

- **Chọn enum** khi mô hình là một tập hằng số cố định, mỗi giá trị thường là một instance duy nhất và không cần các kiểu dữ liệu riêng biệt. Ví dụ: `OrderStatus.NEW`, `OrderStatus.PAID`, `OrderStatus.CANCELLED`.
- **Chọn sealed interface hoặc class** khi mỗi biến thể cần kiểu riêng, có thể mang cấu trúc dữ liệu khác nhau hoặc có hành vi riêng. Ví dụ: `Accepted(orderId)`, `Rejected(reason)` và `NeedsReview(orderId, note)`.
- **Chọn interface hoặc class mở** khi thư viện chủ đích cho phép module, plugin hoặc bên tích hợp bên ngoài cung cấp kiểu triển khai mới mà tác giả API không cần cập nhật danh sách cho phép.

Sealed không đồng nghĩa với immutable. Nó kiểm soát ai có thể mở rộng hệ phân cấp kiểu; trạng thái bên trong từng đối tượng vẫn phụ thuộc vào cách thiết kế class, record và các trường dữ liệu.

## Khi nào nên dùng và những điểm cần cân nhắc

Nên dùng sealed type khi các biến thể là một phần của quy tắc nghiệp vụ có thể liệt kê, nhóm phát triển muốn kiểm soát những cách biểu diễn hợp lệ và việc xử lý đầy đủ các trường hợp mang lại lợi ích rõ ràng. Những ví dụ phù hợp gồm kết quả của một thao tác, loại thông điệp nội bộ, biểu thức trong một ngôn ngữ nhỏ hoặc các trạng thái có cấu trúc dữ liệu khác nhau.

Không nên dùng sealed chỉ để mọi interface trong dự án trông có vẻ chặt chẽ. Nếu API là extension point công khai, nếu các module độc lập cần tự bổ sung kiểu triển khai, hoặc nếu danh sách biến thể thay đổi thường xuyên do tích hợp bên ngoài, giới hạn sealed có thể làm tăng chi phí phối hợp và nâng cấp. Hãy giữ mô hình mở trong trường hợp đó.

Khi công bố sealed type trong thư viện dùng chung, hãy xem danh sách `permits` là một phần hợp đồng API. Thêm, bỏ hoặc thay đổi một kiểu con được phép có thể yêu cầu các bên sử dụng xem lại switch expression, kiểm thử và phiên bản tương thích. Khi thay đổi mô hình, biên dịch lại các module phụ thuộc để phát hiện những nơi chưa xử lý biến thể mới.

Java cũng cung cấp API reflection `Class.getPermittedSubclasses()` để xem các kiểu con được phép của một sealed class hoặc interface tại runtime:

```java
for (Class<?> permitted : Payment.class.getPermittedSubclasses()) {
    System.out.println(permitted.getName());
}
```

Chỉ dùng reflection khi framework hoặc công cụ thực sự cần khám phá mô hình lúc chạy. Với logic nghiệp vụ thông thường, khai báo kiểu và pattern matching thường dễ kiểm tra hơn.

## Quy trình thiết kế một sealed hierarchy

1. **Liệt kê các biến thể hợp lệ của miền nghiệp vụ.** Mỗi biến thể có ý nghĩa riêng hay chỉ là một giá trị trong tập hằng số?
2. **Chọn kiểu gốc.** Dùng interface nếu cần một hợp đồng chung có thể kết hợp với các hệ phân cấp khác; dùng abstract class nếu các biến thể thực sự cần chia sẻ trạng thái hoặc triển khai.
3. **Khai báo các kiểu con trực tiếp.** Liệt kê chúng trong `permits` và bảo đảm mỗi kiểu trực tiếp `extends` hoặc `implements` đúng sealed type.
4. **Chọn mức mở rộng cho từng nhánh.** Dùng `final` cho biến thể hoàn chỉnh, `sealed` cho nhánh có tập con được kiểm soát, và `non-sealed` khi cần mở rộng nhánh đó.
5. **Kiểm tra vị trí và module.** Bảo đảm các kiểu con nằm cùng named module hoặc cùng package trong unnamed module.
6. **Dùng switch expression để kiểm tra tính đầy đủ.** Xử lý rõ `null` nếu đầu vào có thể rỗng và cập nhật các nhánh khi tập hợp biến thể thay đổi.
7. **Đánh giá hợp đồng mở rộng.** Nếu bên tích hợp cần tự định nghĩa kiểu mới, cân nhắc interface hoặc class thông thường thay cho sealed type.

Sealed class và sealed interface phù hợp nhất khi giới hạn của mô hình phản ánh đúng giới hạn của nghiệp vụ. Một hierarchy rõ ràng giúp trình biên dịch hỗ trợ kiểm tra tính đầy đủ và giúp người đọc hiểu những biến thể nào được hệ thống chấp nhận. Hãy chọn sealed khi lợi ích kiểm soát đó quan trọng hơn nhu cầu mở rộng tự do.
