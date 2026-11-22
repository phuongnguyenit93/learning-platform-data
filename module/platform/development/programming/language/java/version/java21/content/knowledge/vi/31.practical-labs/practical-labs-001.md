# Mô hình hóa miền dữ liệu bằng record và sealed interface

Trong Java 21, `record` và `sealed interface` kết hợp tốt để mô hình hóa dữ liệu miền nghiệp vụ có cấu trúc rõ ràng và tập biến thể được kiểm soát. Record phù hợp với các giá trị dữ liệu như mã đơn hàng, tiền, dòng hàng và kết quả thanh toán; sealed interface mô tả một tập trạng thái hoặc kết quả hữu hạn như thanh toán thành công, bị từ chối hoặc cần kiểm tra thủ công.

Bài thực hành này xây dựng mô hình đơn hàng nhỏ. Dữ liệu được bảo vệ bằng constructor validation và defensive copy; các trạng thái được biểu diễn thành record riêng; `switch` pattern matching xử lý đầy đủ từng biến thể. Các tính năng sử dụng đều đã ổn định trong Java 21, không cần bật preview.

## 1. Mục tiêu và bài toán

Giả sử một cửa hàng cần mô hình hóa quy trình thanh toán đơn hàng. Mỗi đơn hàng có mã, các dòng hàng, tổng tiền và trạng thái. Kết quả từ cổng thanh toán có thể là:

- Thanh toán được chấp thuận.
- Thanh toán bị từ chối.
- Giao dịch cần kiểm tra thủ công.

Mô hình cần bảo đảm:

1. Dữ liệu không hợp lệ bị từ chối ngay khi tạo đối tượng.
2. Danh sách dòng hàng không bị thay đổi gián tiếp sau khi tạo đơn.
3. Các loại tiền khác nhau không bị cộng lẫn.
4. Trạng thái thanh toán chỉ chuyển từ trạng thái đang chờ sang một kết quả cuối/nhánh xử lý phù hợp.
5. Khi thêm một loại kết quả mới, compiler có thể giúp phát hiện các `switch` chưa xử lý biến thể đó.

## 2. Phân chia trách nhiệm giữa record và sealed interface

`record` là kiểu dữ liệu mang các component được khai báo trong header. Compiler sinh constructor canonical, accessor, `equals`, `hashCode` và `toString`. Các component được lưu trong field `private final`; bản thân record là `final`, không thể kế thừa.

`sealed interface` giới hạn những kiểu trực tiếp được phép triển khai bằng danh sách `permits`. Các kiểu được cho phép phải tiếp tục khai báo là `final`, `sealed` hoặc `non-sealed`. Record là `final` một cách ngầm định nên có thể triển khai sealed interface mà không cần ghi thêm từ khóa `final`.

| Thành phần miền | Kiểu phù hợp | Lý do |
|---|---|---|
| Mã đơn hàng, mã thanh toán | `record` | Giá trị nhỏ, có equality theo dữ liệu |
| Tiền và dòng hàng | `record` | Dữ liệu có cấu trúc, cần invariant tại constructor |
| Bản nháp đơn hàng | `record` | Gom mã đơn và danh sách dòng hàng bất biến |
| Kết quả thanh toán | `sealed interface` + các record | Tập kết quả hữu hạn, mỗi biến thể có dữ liệu riêng |
| Trạng thái đơn hàng | `sealed interface` + các record | Mô hình hóa trạng thái rõ ràng và kiểm tra exhaustive |
| Đơn hàng | `record` | Gom dữ liệu hiện tại và cung cấp phép chuyển trạng thái tạo đối tượng mới |

Không nên dùng sealed interface cho một extension point vốn được thiết kế để plugin bên ngoài tự do triển khai. Sealed phù hợp khi miền nghiệp vụ chủ động kiểm soát các biến thể hợp lệ.

## 3. Thiết kế value object cho mã và tiền

Trước tiên, tạo các value object. Ví dụ dưới đây đặt toàn bộ kiểu lồng nhau trong một class để có thể biên dịch thành một file thực hành. Trong ứng dụng nhiều module, có thể tách từng kiểu thành file riêng theo cấu trúc package.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.time.Instant;

public class OrderDomainLab {
    public record OrderId(UUID value) {
        public OrderId {
            Objects.requireNonNull(value, "value");
        }
    }

    public record PaymentId(String value) {
        public PaymentId {
            value = requireText(value, "value");
        }
    }

    public record Money(BigDecimal amount, Currency currency) {
        public Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");

            if (amount.signum() < 0) {
                throw new IllegalArgumentException("amount must not be negative");
            }

            int fractionDigits = currency.getDefaultFractionDigits();
            if (fractionDigits < 0) {
                throw new IllegalArgumentException("Unsupported currency precision");
            }

            try {
                amount = amount.setScale(fractionDigits, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException e) {
                throw new IllegalArgumentException(
                        "amount has too many fractional digits for " + currency, e);
            }
        }

        public Money add(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("Currencies must match");
            }
            return new Money(amount.add(other.amount), currency);
        }

        public Money multiply(int quantity) {
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity must not be negative");
            }
            return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
        }

        @Override
        public String toString() {
            return currency.getCurrencyCode() + " " + amount.toPlainString();
        }
    }

    private static String requireText(String value, String fieldName) {
        Objects.requireNonNull(value, fieldName);
        String normalized = value.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(fieldName + " must not be blank");
        }
        return normalized;
    }
```

Đây là phần mở đầu của file `OrderDomainLab.java`. Giữ class `OrderDomainLab` mở khi ghép các khai báo tiếp theo: các record và sealed interface ở phần 4–7 là nested types đặt bên trong class này. Đóng class bằng dấu `}` sau phương thức `main` ở phần 8.

`Money` chuẩn hóa scale theo số chữ số thập phân mặc định của `Currency`. Ví dụ USD thường có hai chữ số thập phân, còn JPY thường không có chữ số thập phân. `RoundingMode.UNNECESSARY` khiến constructor từ chối giá trị cần làm tròn thay vì âm thầm thay đổi số tiền.

Đây là quy tắc đơn giản cho bài thực hành; hệ thống tài chính thực tế cần xác định chính sách làm tròn, loại tiền được hỗ trợ, thuế, tỷ giá và độ chính xác theo nghiệp vụ. Không dùng `double` để lưu số tiền cần tính toán chính xác.

## 4. Mô hình hóa dòng hàng và bản nháp đơn hàng

Một dòng hàng có SKU, số lượng và đơn giá. Bản nháp đơn hàng giữ danh sách dòng hàng và tính tổng tiền:

```java
public record OrderLine(String sku, int quantity, Money unitPrice) {
    public OrderLine {
        sku = requireText(sku, "sku");
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        Objects.requireNonNull(unitPrice, "unitPrice");
    }
}

public record OrderDraft(OrderId orderId, List<OrderLine> lines) {
    public OrderDraft {
        Objects.requireNonNull(orderId, "orderId");
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));

        if (lines.isEmpty()) {
            throw new IllegalArgumentException("An order must contain at least one line");
        }

        Currency expectedCurrency = lines.get(0).unitPrice().currency();
        boolean mixedCurrencies = lines.stream()
                .anyMatch(line -> !expectedCurrency.equals(line.unitPrice().currency()));
        if (mixedCurrencies) {
            throw new IllegalArgumentException("All order lines must use the same currency");
        }
    }

    public Money total() {
        Currency currency = lines.get(0).unitPrice().currency();
        Money zero = new Money(BigDecimal.ZERO, currency);

        return lines.stream()
                .map(line -> line.unitPrice().multiply(line.quantity()))
                .reduce(zero, Money::add);
    }

    public Order create(Instant createdAt) {
        return new Order(orderId, total(), new AwaitingPayment(createdAt));
    }
}
```

Trong compact constructor của record, có thể gán lại tên component như `lines = List.copyOf(...)`. Giá trị sau khi gán sẽ được lưu vào field tương ứng khi constructor kết thúc.

`List.copyOf` tạo snapshot không thể sửa đổi của danh sách đầu vào và từ chối phần tử `null`. Đây là defensive copy cần thiết vì record chỉ bảo đảm field là `final`; nếu field trỏ đến một collection mutable bên ngoài, dữ liệu bên trong vẫn có thể thay đổi.

Các phần tử `OrderLine` và `Money` trong ví dụ cũng là record chứa dữ liệu bất biến. Nếu component của record là một object mutable khác như `Date`, array hoặc collection lồng nhau, cần sao chép/bao bọc phù hợp cả ở constructor lẫn accessor khi cần bảo đảm immutability sâu.

## 5. Dùng sealed interface cho kết quả thanh toán

Kết quả thanh toán có ba biến thể. Mỗi biến thể mang đúng dữ liệu cần cho trường hợp đó:

```java
public sealed interface PaymentOutcome
        permits PaymentApproved, PaymentDeclined, PaymentNeedsReview {
}

public record PaymentApproved(
        PaymentId paymentId,
        Money amount,
        Instant approvedAt) implements PaymentOutcome {
    public PaymentApproved {
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(approvedAt, "approvedAt");
    }
}

public record PaymentDeclined(
        String code,
        String reason,
        Instant declinedAt) implements PaymentOutcome {
    public PaymentDeclined {
        code = requireText(code, "code");
        reason = requireText(reason, "reason");
        Objects.requireNonNull(declinedAt, "declinedAt");
    }
}

public record PaymentNeedsReview(
        String caseId,
        Instant requestedAt) implements PaymentOutcome {
    public PaymentNeedsReview {
        caseId = requireText(caseId, "caseId");
        Objects.requireNonNull(requestedAt, "requestedAt");
    }
}
```

Không cần một record duy nhất chứa nhiều field nullable như `paymentId`, `declineReason`, `reviewCaseId`. Cách đó cho phép tạo ra nhiều tổ hợp không hợp lệ, ví dụ vừa có payment ID vừa có decline reason. Sealed hierarchy thể hiện mỗi kết quả là một kiểu riêng và constructor của từng record kiểm tra invariant của biến thể đó.

## 6. Dùng sealed interface để mô hình hóa trạng thái đơn hàng

Trạng thái đơn hàng cũng có thể biểu diễn bằng các record riêng:

```java
public sealed interface OrderStatus
        permits AwaitingPayment, Paid, PaymentRejected, ManualReview {
}

public record AwaitingPayment(Instant since) implements OrderStatus {
    public AwaitingPayment {
        Objects.requireNonNull(since, "since");
    }
}

public record Paid(PaymentId paymentId, Instant paidAt) implements OrderStatus {
    public Paid {
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(paidAt, "paidAt");
    }
}

public record PaymentRejected(String code, String reason, Instant rejectedAt)
        implements OrderStatus {
    public PaymentRejected {
        code = requireText(code, "code");
        reason = requireText(reason, "reason");
        Objects.requireNonNull(rejectedAt, "rejectedAt");
    }
}

public record ManualReview(String caseId, Instant requestedAt) implements OrderStatus {
    public ManualReview {
        caseId = requireText(caseId, "caseId");
        Objects.requireNonNull(requestedAt, "requestedAt");
    }
}
```

Một `enum` cũng phù hợp nếu trạng thái chỉ là các nhãn cố định và không cần dữ liệu riêng. Ở đây `Paid` cần payment ID/thời điểm, `PaymentRejected` cần mã và lý do từ chối, còn `ManualReview` cần mã hồ sơ. Sealed interface cho phép mỗi trạng thái giữ đúng dữ liệu của nó.

## 7. Xây dựng Order và chuyển trạng thái bằng pattern switch

`Order` là record gom định danh, tổng tiền và trạng thái. Phương thức `apply` nhận kết quả thanh toán rồi trả về một `Order` mới:

```java
public record Order(OrderId id, Money total, OrderStatus status) {
    public Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(total, "total");
        Objects.requireNonNull(status, "status");
    }

    public Order apply(PaymentOutcome outcome) {
        Objects.requireNonNull(outcome, "outcome");

        if (!(status instanceof AwaitingPayment)) {
            throw new IllegalStateException("Payment result can only be applied once");
        }

        return switch (outcome) {
            case PaymentApproved approved -> {
                if (!total.equals(approved.amount())) {
                    throw new IllegalArgumentException("Approved amount does not match order total");
                }
                yield new Order(id, total,
                        new Paid(approved.paymentId(), approved.approvedAt()));
            }
            case PaymentDeclined declined -> new Order(id, total,
                    new PaymentRejected(
                            declined.code(), declined.reason(), declined.declinedAt()));
            case PaymentNeedsReview review -> new Order(id, total,
                    new ManualReview(review.caseId(), review.requestedAt()));
        };
    }

    public String statusLabel() {
        return switch (status) {
            case AwaitingPayment pending -> "Awaiting payment";
            case Paid paid -> "Paid: " + paid.paymentId().value();
            case PaymentRejected rejected -> "Rejected: " + rejected.code();
            case ManualReview review -> "Review: " + review.caseId();
        };
    }
}
```

Điểm đáng chú ý:

- `switch` pattern matching nhận biết kiểu cụ thể và đặt biến pattern tương ứng.
- Vì `PaymentOutcome` và `OrderStatus` là sealed hierarchy, compiler biết tập biến thể hợp lệ và có thể kiểm tra switch expression đã exhaustive.
- `yield` trả giá trị từ block của một nhánh switch expression.
- `apply` tạo record mới thay vì sửa trạng thái trên object hiện tại.
- Kiểm tra `AwaitingPayment` ngăn kết quả thanh toán thứ hai ghi đè trạng thái đã xử lý.

Pattern matching for switch đã là tính năng chính thức trong Java 21, không cần `--enable-preview`. Nếu thêm một subtype mới vào danh sách `permits`, các switch exhaustive có thể báo lỗi biên dịch cho đến khi xử lý subtype mới.

## 8. Chương trình chạy thử hoàn chỉnh

Thêm `main` vào cuối class `OrderDomainLab` đã khai báo ở phần 3. Các record và interface trong các phần trước là nested type của class đó, nên có thể dùng trực tiếp:

```java
public static void main(String[] args) {
    Currency usd = Currency.getInstance("USD");

    OrderDraft draft = new OrderDraft(
            new OrderId(UUID.fromString("11111111-1111-1111-1111-111111111111")),
            List.of(
                    new OrderLine("BOOK-001", 2,
                            new Money(new BigDecimal("12.50"), usd)),
                    new OrderLine("PEN-002", 1,
                            new Money(new BigDecimal("5.00"), usd))));

    Order order = draft.create(Instant.parse("2026-01-10T10:00:00Z"));
    System.out.println("Order total: " + order.total());
    System.out.println("Initial status: " + order.statusLabel());

    PaymentOutcome payment = new PaymentApproved(
            new PaymentId("pay-001"),
            draft.total(),
            Instant.parse("2026-01-10T10:00:05Z"));

    Order paidOrder = order.apply(payment);
    System.out.println("Updated status: " + paidOrder.statusLabel());
    System.out.println("Original status: " + order.statusLabel());
}
}
```

Kết quả mong đợi:

```text
Order total: USD 30.00
Initial status: Awaiting payment
Updated status: Paid: pay-001
Original status: Awaiting payment
```

`order` ban đầu vẫn có trạng thái `AwaitingPayment`; `paidOrder` là một giá trị mới. Đây là cách mô hình hóa chuyển trạng thái bằng immutable data, giúp giảm thay đổi ngoài ý muốn và thuận lợi khi kiểm thử.

## 9. Biên dịch và chạy trên JDK 21

Lưu toàn bộ ví dụ vào file `OrderDomainLab.java`, đặt tất cả nested record/interface và phương thức `main` bên trong class `OrderDomainLab`, sau đó chạy:

```shell
javac --release 21 OrderDomainLab.java
java OrderDomainLab
```

Không cần cờ preview. `--release 21` giúp xác nhận source dùng cú pháp/API trong phạm vi Java 21. Nếu IDE hoặc build tool sử dụng JDK khác, kiểm tra toolchain và runtime thực tế trước khi kết luận về tính tương thích.

## 10. Viết test cho invariant và chuyển trạng thái

Ngoài kiểm tra kết quả happy path, nên test các invariant ở constructor và các trường hợp chuyển trạng thái sai. Ví dụ dưới đây dùng JUnit Jupiter; thêm dependency JUnit 5 vào test scope theo build tool của dự án.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNotSame;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;

class OrderDomainLabTest {
    private final Currency usd = Currency.getInstance("USD");

    @Test
    void draftMakesDefensiveCopyOfLines() {
        var source = new ArrayList<>(List.of(
                new OrderDomainLab.OrderLine("BOOK-001", 1,
                        new OrderDomainLab.Money(new BigDecimal("10.00"), usd))));

        var draft = new OrderDomainLab.OrderDraft(
                new OrderDomainLab.OrderId(UUID.randomUUID()), source);

        source.clear();

        assertEquals(1, draft.lines().size());
        assertThrows(UnsupportedOperationException.class,
                () -> draft.lines().clear());
    }

    @Test
    void draftRejectsMixedCurrencies() {
        var usdLine = new OrderDomainLab.OrderLine("BOOK", 1,
                new OrderDomainLab.Money(new BigDecimal("10.00"), usd));
        var jpyLine = new OrderDomainLab.OrderLine("PEN", 1,
                new OrderDomainLab.Money(new BigDecimal("100"), Currency.getInstance("JPY")));

        assertThrows(IllegalArgumentException.class,
                () -> new OrderDomainLab.OrderDraft(
                        new OrderDomainLab.OrderId(UUID.randomUUID()),
                        List.of(usdLine, jpyLine)));
    }

    @Test
    void approvedPaymentCreatesNewPaidOrder() {
        var draft = new OrderDomainLab.OrderDraft(
                new OrderDomainLab.OrderId(UUID.randomUUID()),
                List.of(new OrderDomainLab.OrderLine("BOOK", 1,
                        new OrderDomainLab.Money(new BigDecimal("12.00"), usd))));
        var original = draft.create(Instant.parse("2026-01-10T10:00:00Z"));
        var outcome = new OrderDomainLab.PaymentApproved(
                new OrderDomainLab.PaymentId("pay-001"), draft.total(),
                Instant.parse("2026-01-10T10:00:05Z"));

        var updated = original.apply(outcome);

        assertNotSame(original, updated);
        assertEquals("Awaiting payment", original.statusLabel());
        assertEquals("Paid: pay-001", updated.statusLabel());
    }

    @Test
    void orderRejectsSecondPaymentResult() {
        var draft = new OrderDomainLab.OrderDraft(
                new OrderDomainLab.OrderId(UUID.randomUUID()),
                List.of(new OrderDomainLab.OrderLine("BOOK", 1,
                        new OrderDomainLab.Money(new BigDecimal("12.00"), usd))));
        var order = draft.create(Instant.parse("2026-01-10T10:00:00Z"));
        var approved = new OrderDomainLab.PaymentApproved(
                new OrderDomainLab.PaymentId("pay-001"), draft.total(),
                Instant.parse("2026-01-10T10:00:05Z"));
        var paid = order.apply(approved);

        assertThrows(IllegalStateException.class,
                () -> paid.apply(approved));
    }
}
```

Các test này kiểm tra defensive copy, quy tắc tiền tệ, chuyển trạng thái tạo object mới và ngăn áp dụng kết quả thanh toán lần hai. Có thể mở rộng thêm test cho số tiền sai, quantity không hợp lệ, chuỗi rỗng và từng biến thể bị từ chối/cần review.

## 11. Mở rộng mô hình và giữ invariant

Khi phát triển tiếp, hãy xác định invariant ở đúng ranh giới:

- `Money` kiểm tra amount và currency; không để phép cộng khác currency lọt vào.
- `OrderLine` kiểm tra SKU và quantity.
- `OrderDraft` kiểm tra danh sách không rỗng, sao chép danh sách và bảo đảm một currency thống nhất.
- `PaymentOutcome` kiểm tra dữ liệu bắt buộc theo từng biến thể.
- `Order.apply` kiểm tra trạng thái hiện tại và số tiền được duyệt.
- Các hàm chuyển trạng thái trả object mới để người gọi có thể lưu phiên bản mới một cách tường minh.

Nếu nghiệp vụ có thêm trạng thái như `Cancelled`, `Refunded` hoặc `PartiallyPaid`, hãy quyết định nó thuộc `OrderStatus` hay là một domain event riêng. Không thêm subtype chỉ để biểu diễn một giá trị nullable hoặc một cờ boolean; mỗi subtype nên đại diện cho một trạng thái có ý nghĩa nghiệp vụ và invariant rõ ràng.

Với dữ liệu lưu trong database hoặc truyền qua API, record không tự động trở thành schema persistence hay wire format. Hãy dùng mapper/serializer và versioning rõ ràng. Sealed hierarchy cũng cần được xử lý khi deserialize dữ liệu: chỉ cho phép các subtype hợp lệ và không tin tên class do input bên ngoài cung cấp.

## 12. Những giới hạn cần nhớ

| Đặc điểm | Hệ quả thiết kế |
|---|---|
| Record là final | Không dùng record làm base class để kế thừa |
| Record chỉ bất biến nông | Component mutable cần defensive copy hoặc kiểu dữ liệu bất biến |
| Equality của record dựa trên component | Với `BigDecimal`, scale khác nhau có thể ảnh hưởng `equals`; chuẩn hóa trước nếu nghiệp vụ yêu cầu |
| Sealed hierarchy giới hạn subtype | Phù hợp với miền đóng; không phù hợp extension point mở cho plugin tùy ý |
| Pattern switch exhaustive phụ thuộc tập subtype | Thêm subtype có thể yêu cầu cập nhật các switch |
| Constructor validation chỉ bảo vệ lúc tạo object | Không thay thế kiểm tra authorization, transaction hoặc validation ở ranh giới API |
| Record không tự tạo validation/serialization policy | Cần định nghĩa rõ invariant và format truyền/lưu dữ liệu |

Trong ví dụ, `Money` chuẩn hóa scale theo currency để equality của record phù hợp hơn với dữ liệu đã chấp nhận. Với domain phức tạp, có thể cần một abstraction tiền tệ chuyên biệt hoặc thư viện domain đã được kiểm chứng.

## 13. Bài tập mở rộng

1. Thêm `PaymentRefunded` vào `OrderStatus`, chứa `PaymentId`, số tiền hoàn và thời điểm hoàn. Cập nhật `statusLabel()` và kiểm tra compiler yêu cầu xử lý subtype mới.
2. Thêm trạng thái `Cancelled` và định nghĩa rõ trạng thái nào được phép hủy.
3. Bổ sung `OrderLine` có discount nhưng bảo đảm tổng tiền không âm.
4. Viết test cho `PaymentDeclined` và `PaymentNeedsReview`.
5. Thêm mapper chuyển `Order` sang DTO response mà không để lộ các chi tiết nội bộ của domain.
6. Thử truyền danh sách mutable vào `OrderDraft`, thay đổi danh sách gốc và xác nhận object draft không đổi.
7. Tạo một record chứa array, quan sát rằng `final` reference không làm array bất biến; bổ sung defensive copy cả constructor và accessor.

## 14. Checklist hoàn thành lab

- Dùng record cho value object và cấu trúc dữ liệu có invariant rõ ràng.
- Dùng compact constructor để validate và chuẩn hóa component.
- Sao chép collection mutable bằng `List.copyOf` hoặc cơ chế phù hợp.
- Không dùng `double` cho số tiền cần độ chính xác thập phân.
- Dùng sealed interface cho tập biến thể nghiệp vụ được kiểm soát.
- Mỗi subtype mang dữ liệu cần thiết, không gom nhiều field nullable vào một record chung.
- Dùng pattern switch để xử lý tất cả biến thể và tận dụng exhaustive checking.
- Chuyển trạng thái bằng object mới thay vì thay đổi dữ liệu cũ ngoài ý muốn.
- Test invariant, defensive copy, happy path và transition không hợp lệ.
- Biên dịch bằng `--release 21`; không cần preview flags cho các tính năng trong lab.
- Xác định riêng quy tắc persistence, serialization, authorization và transaction khi đưa mô hình vào ứng dụng.

Lab đã kết hợp record để biểu diễn dữ liệu bất biến có kiểm tra và sealed interface để mô hình hóa tập kết quả/trạng thái hữu hạn. Pattern matching for switch giúp xử lý từng biến thể rõ ràng và cho compiler kiểm tra tính đầy đủ. Đây là nền tảng hữu ích để xây dựng domain model Java 21 dễ kiểm thử, ít trạng thái không hợp lệ và dễ mở rộng có kiểm soát.
