# MatchException khi hierarchy thay đổi nhưng mã sử dụng chưa được biên dịch lại

Trong Java 21, pattern switch có thể được kiểm tra tính đầy đủ dựa trên sealed class hoặc sealed interface. Trình biên dịch xác nhận rằng các kiểu con được phép đã được xử lý tại thời điểm biên dịch. Tuy nhiên, một ứng dụng có thể vẫn chạy bytecode được biên dịch từ phiên bản hierarchy cũ trong khi thư viện cung cấp hierarchy đã được cập nhật. Nếu một đối tượng thuộc kiểu con mới đi vào switch cũ và không nhãn nào khớp, Java có thể ném `MatchException` lúc chạy.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), cần hiểu đây là vấn đề lệch phiên bản giữa mã sử dụng và thư viện kiểu dữ liệu. `MatchException` không có nghĩa compiler đã bỏ sót lỗi trong lần biên dịch ban đầu; nó báo rằng giả định về tập hợp kiểu đã thay đổi sau khi bytecode của switch được tạo ra.

## Vì sao sealed hierarchy có thể thay đổi sau khi biên dịch?

Sealed type giới hạn các kiểu con trực tiếp được phép bằng `permits`. Khi biên dịch một switch trên sealed type, compiler biết tập hợp kiểu con được khai báo tại thời điểm đó và có thể xác nhận các nhánh đã bao phủ những trường hợp hợp lệ.

Ví dụ, phiên bản đầu của thư viện thanh toán khai báo hai kết quả:

```java
// File: PaymentResult.java — API phiên bản 1
package example.payment;

public sealed interface PaymentResult permits Paid, Rejected {}
```

```java
// File: Paid.java — API phiên bản 1
package example.payment;

public record Paid(String transactionId) implements PaymentResult {}
```

```java
// File: Rejected.java — API phiên bản 1
package example.payment;

public record Rejected(String reason) implements PaymentResult {}
```

Ứng dụng biên dịch một switch expression dựa trên phiên bản API này:

```java
// Ứng dụng được biên dịch với API phiên bản 1
package example.app;

import example.payment.Paid;
import example.payment.PaymentResult;
import example.payment.Rejected;

public final class PaymentMessages {
    public static String describe(PaymentResult result) {
        return switch (result) {
            case Paid(var transactionId) -> "Đã thanh toán: " + transactionId;
            case Rejected(var reason) -> "Bị từ chối: " + reason;
        };
    }
}
```

Switch expression không cần `default`, vì `PaymentResult` chỉ cho phép `Paid` và `Rejected` tại thời điểm biên dịch. Compiler đã kiểm tra cả hai kiểu con được bao phủ.

## Điều gì xảy ra khi thư viện thêm kiểu con mới?

Sau đó, thư viện phát hành phiên bản 2 và bổ sung kết quả cần kiểm tra thủ công:

```java
// File: PaymentResult.java — API phiên bản 2
package example.payment;

public sealed interface PaymentResult
        permits Paid, Rejected, NeedsReview {}
```

```java
// File: Paid.java — API phiên bản 2
package example.payment;

public record Paid(String transactionId) implements PaymentResult {}
```

```java
// File: Rejected.java — API phiên bản 2
package example.payment;

public record Rejected(String reason) implements PaymentResult {}
```

```java
// File: NeedsReview.java — API phiên bản 2
package example.payment;

public record NeedsReview(String caseId) implements PaymentResult {}
```

Giả sử ứng dụng vẫn dùng class `PaymentMessages` đã biên dịch với API phiên bản 1, nhưng runtime đã nạp API phiên bản 2. Khi một phần khác của ứng dụng tạo `new NeedsReview("CASE-42")` rồi truyền vào `PaymentMessages.describe(...)`, bytecode cũ không có nhánh dành cho `NeedsReview`.

Compiler đã biết switch là exhaustive với tập kiểu ở phiên bản 1. Để xử lý tình huống tập hợp kiểu thay đổi sau biên dịch, bytecode của switch exhaustive có nhánh dự phòng do compiler sinh ra. Nếu lúc chạy không nhãn nào khớp và nhánh dự phòng này được kích hoạt, Java ném `java.lang.MatchException`.

**Trình tự dẫn đến MatchException:**

1. API phiên bản 1 chỉ cho phép `Paid` và `Rejected`.
2. Ứng dụng biên dịch switch và compiler xác nhận hai trường hợp đã đầy đủ.
3. API phiên bản 2 bổ sung `NeedsReview` vào `permits`.
4. Ứng dụng cũ vẫn chạy cùng bytecode đã biên dịch từ phiên bản 1.
5. Đối tượng `NeedsReview` đi vào switch cũ nhưng không nhãn nào khớp.
6. Nhánh dự phòng do compiler tạo ra ném `MatchException`.

Điểm quan trọng là compiler không thể cập nhật bytecode của ứng dụng chỉ vì thư viện đã được thay thế. Muốn switch nhận biết `NeedsReview`, mã sử dụng phải được biên dịch lại với API mới và bổ sung nhánh tương ứng.

## MatchException là gì?

`MatchException` là exception thuộc package `java.lang`, được bổ sung trong Java 21. Nó kế thừa `RuntimeException` và biểu thị rằng một cấu trúc pattern matching, chẳng hạn switch expression, không khớp với giá trị selector như giả định tại thời điểm biên dịch.

Trong tình huống sealed hierarchy thay đổi:

- Lỗi xuất hiện lúc chạy khi giá trị mới đi vào switch cũ.
- Mã nguồn cũ có thể đã biên dịch thành công và không có `default`.
- Nhánh dự phòng do compiler sinh ra bảo đảm switch expression không âm thầm thiếu kết quả.
- Biên dịch lại mã sử dụng với hierarchy mới sẽ khiến compiler yêu cầu xử lý kiểu con mới nếu switch vẫn cần exhaustive.

Đây là lỗi về sự không đồng bộ giữa phiên bản API và bytecode consumer. Nó khác với lỗi biên dịch do thiếu nhánh: lỗi biên dịch xuất hiện khi compiler nhìn thấy hierarchy mới, còn `MatchException` có thể xuất hiện khi runtime đã có hierarchy mới nhưng consumer vẫn là binary cũ.

## Vì sao compiler không tự chọn một kết quả mặc định?

Switch expression phải tạo ra một giá trị. Nếu một kiểu mới không khớp nhánh nào, tự chọn một kết quả mặc định có thể che giấu việc nghiệp vụ chưa định nghĩa cách xử lý kiểu mới. Ví dụ, coi `NeedsReview` là `Rejected` có thể làm sai trạng thái đơn hàng hoặc gửi thông báo không phù hợp.

Vì vậy, nhánh dự phòng do compiler sinh ra ném exception để lỗi được nhìn thấy tại điểm xử lý. Đây là cơ chế an toàn khi giả định exhaustiveness không còn đúng trong môi trường chạy.

Không nhầm nhánh dự phòng này với `default` do lập trình viên viết trong mã nguồn. `default` là quyết định nghiệp vụ rõ ràng của ứng dụng; nhánh dự phòng do compiler tạo ra là bảo vệ cho trường hợp bytecode cũ gặp một giá trị không được dự kiến.

## Cách xử lý khi hierarchy được mở rộng

### Biên dịch lại consumer với API mới

Đây là cách phù hợp khi ứng dụng cần xử lý đầy đủ các biến thể của sealed hierarchy. Sau khi nâng cấp thư viện, biên dịch lại mã sử dụng. Compiler sẽ phát hiện switch cũ chưa bao phủ `NeedsReview`:

```java
public static String describe(PaymentResult result) {
    return switch (result) {
        case Paid(var transactionId) -> "Đã thanh toán: " + transactionId;
        case Rejected(var reason) -> "Bị từ chối: " + reason;
        case NeedsReview(var caseId) -> "Đang chờ kiểm tra: " + caseId;
    };
}
```

Khi đã bổ sung nhánh mới và biên dịch thành công, ứng dụng có thể xử lý biến thể mới theo đúng quy tắc nghiệp vụ. Cần triển khai đồng bộ artifact thư viện và artifact ứng dụng đã được biên dịch lại.

### Dùng default khi cần chấp nhận biến thể chưa biết

Nếu ứng dụng là consumer của một API có chủ đích mở rộng theo thời gian và có thể xử lý an toàn những biến thể chưa biết, có thể thêm `default`:

```java
static String describe(PaymentResult result) {
    return switch (result) {
        case Paid(var transactionId) -> "Đã thanh toán: " + transactionId;
        case Rejected(var reason) -> "Bị từ chối: " + reason;
        default -> "Kết quả thanh toán chưa được hỗ trợ";
    };
}
```

`default` làm switch bao phủ các kiểu không được liệt kê, do đó giá trị thuộc kiểu con mới không kích hoạt nhánh dự phòng của compiler. Ứng dụng có thể tiếp tục chạy và trả về kết quả dự phòng đã định nghĩa.

Tuy nhiên, `default` cũng làm mất một phần lợi ích của exhaustiveness theo từng kiểu con: khi thêm `NeedsReview`, compiler không bắt buộc consumer phải bổ sung nhánh riêng. Chỉ dùng cách này khi fallback thực sự đúng với hợp đồng sản phẩm, chẳng hạn ghi nhận một sự kiện chưa hỗ trợ hoặc đưa nó vào luồng xử lý chung. Không dùng một thông báo chung để giả vờ rằng nghiệp vụ đã được xử lý.

### Đồng bộ phiên bản khi triển khai

Trong hệ thống nhiều module hoặc dịch vụ, việc nâng cấp thư viện và consumer có thể diễn ra ở các thời điểm khác nhau. Cần quản lý tương thích phiên bản trong quá trình phát hành:

- Xác định các module và ứng dụng biên dịch dựa trên sealed API.
- Khi thay đổi `permits`, biên dịch lại các consumer cần xử lý đầy đủ kiểu con.
- Kiểm soát dependency version để tránh runtime nạp thư viện mới cùng consumer binary cũ ngoài dự kiến.
- Với triển khai rolling hoặc nhiều instance, xác định rõ khoảng thời gian các phiên bản cùng tồn tại và hành vi khi dữ liệu mới tới instance cũ.
- Chỉ phát hành kiểu con mới khi các consumer bắt buộc đã sẵn sàng hoặc có fallback tương thích được thiết kế trước.

Nếu các thành phần không thể nâng cấp cùng lúc, hãy thiết kế hợp đồng mở rộng và chiến lược fallback ngay từ đầu thay vì giả định mọi instance đều chạy cùng một binary.

## Có nên bắt MatchException để tiếp tục chạy?

`MatchException` là runtime exception. Có thể bắt nó ở một ranh giới xử lý lỗi nếu ứng dụng có chính sách phục hồi cụ thể, nhưng không nên bắt rồi bỏ qua hoặc chuyển mọi trường hợp thành kết quả thành công.

Ví dụ, ở ranh giới tiếp nhận một sự kiện, ứng dụng có thể ghi log đầy đủ và đưa thông điệp vào dead-letter queue để điều tra sau:

```java
try {
    String message = PaymentMessages.describe(result);
    publisher.publish(message);
} catch (MatchException exception) {
    logger.error("Consumer chưa xử lý được biến thể PaymentResult: {}",
            result.getClass().getName(), exception);
    deadLetterQueue.enqueue(result);
}
```

Đây chỉ là ví dụ về vị trí có thể áp dụng chính sách lỗi; `logger`, `publisher` và `deadLetterQueue` là các thành phần do ứng dụng cung cấp. Trong hệ thống thực tế, cần xem xét khả năng tuần tự hóa sự kiện, retry, giới hạn retry và cảnh báo vận hành. Nếu không có phương án phục hồi an toàn, hãy để lỗi được truyền lên cơ chế xử lý lỗi chung thay vì che giấu.

## Kiểm thử và phòng ngừa version skew

Để tránh phát hiện vấn đề lần đầu ở production, quy trình CI/CD nên kiểm tra cả mã nguồn và cách các artifact phối hợp:

1. **Biên dịch consumer với phiên bản API được hỗ trợ.** Việc này phát hiện switch không exhaustive khi hierarchy đã được cập nhật.
2. **Chạy kiểm thử tích hợp với đúng dependency runtime.** Đảm bảo ứng dụng thực tế nạp đúng phiên bản thư viện mà nó đã được kiểm tra.
3. **Kiểm tra các thay đổi sealed hierarchy trong review.** Thêm hoặc bỏ kiểu con được phép có thể ảnh hưởng tới mọi consumer dùng exhaustive switch.
4. **Kiểm thử triển khai nhiều phiên bản nếu có rolling deployment.** Xác nhận instance cũ không nhận dữ liệu chứa biến thể mà nó không thể xử lý, hoặc có fallback tương thích.
5. **Theo dõi MatchException.** Log stack trace, loại runtime của selector và phiên bản artifact giúp xác định nhanh consumer nào chưa được cập nhật.

## Phân biệt các tình huống lỗi thường gặp

| Tình huống | Thời điểm | Kết quả thường thấy |
| --- | --- | --- |
| Biên dịch switch với hierarchy mới nhưng thiếu nhánh | Compile time | Compiler báo switch không exhaustive |
| Consumer cũ gặp kiểu con mới ở runtime | Runtime | `MatchException` từ nhánh dự phòng của switch exhaustive |
| Selector là `null` và switch không có `case null` | Runtime | `NullPointerException` |
| Có `default` xử lý kiểu con mới | Runtime | Chạy nhánh `default` theo logic ứng dụng |
| Consumer được biên dịch lại và bổ sung nhánh mới | Runtime | Kiểu con mới được xử lý bởi nhánh đã khai báo |

## Quy trình khi thay đổi sealed hierarchy

1. **Xem thay đổi kiểu con là thay đổi hợp đồng.** Kiểm tra danh sách `permits` và xác định các consumer có switch dựa trên hierarchy này.
2. **Quyết định mức tương thích mong muốn.** Nếu cần xử lý từng biến thể rõ ràng, giữ exhaustive switch không có `default`; nếu cần chấp nhận kiểu mới, định nghĩa fallback có ý nghĩa.
3. **Cập nhật mã nguồn consumer.** Thêm nhánh xử lý cho kiểu con mới hoặc fallback đã thống nhất.
4. **Biên dịch lại và kiểm thử với API mới.** Không chỉ thay thư viện trong runtime mà bỏ qua bytecode consumer cũ.
5. **Triển khai theo kế hoạch tương thích.** Đồng bộ các artifact hoặc bảo đảm dữ liệu mới không đi tới instance cũ chưa sẵn sàng.
6. **Theo dõi lỗi lúc chạy.** Dùng `MatchException` như tín hiệu cho thấy giả định về hierarchy và phiên bản binary không còn đồng bộ.

`MatchException` giúp Java phát hiện một switch exhaustive đã gặp giá trị nằm ngoài tập hợp kiểu mà consumer từng biết. Khi sealed hierarchy thay đổi, hãy biên dịch lại consumer và cập nhật logic theo biến thể mới. Chỉ dùng `default` khi fallback là một phần có chủ đích của hợp đồng; việc đồng bộ phiên bản và kiểm thử tích hợp sẽ giúp tránh lỗi này khi triển khai.
