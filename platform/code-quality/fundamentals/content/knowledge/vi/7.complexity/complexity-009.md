# Tách phần tính toán khỏi phần điều phối và tác dụng phụ

Một phương thức vừa tính giá đơn hàng, vừa truy vấn dữ liệu, thu tiền, ghi cơ sở dữ liệu và gửi email thường khó hiểu hơn nhiều so với một phương thức chỉ thực hiện phép tính. Mỗi thao tác riêng lẻ có thể đơn giản, nhưng khi nằm trong cùng một khối mã, chúng tạo ra nhiều nhánh lỗi, phụ thuộc và thứ tự thực thi cần ghi nhớ.

Trong chương **Độ phức tạp** của module **CODE_QUALITY_FUNDAMENTALS**, tách phần tính toán khỏi phần điều phối và tác dụng phụ là một cách kiểm soát độ phức tạp để mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Mục tiêu không phải loại bỏ mọi tác dụng phụ: ứng dụng thực tế vẫn phải đọc và ghi dữ liệu, gửi yêu cầu và tương tác với thế giới bên ngoài. Mục tiêu là **đặt quy tắc tính toán và các tương tác bên ngoài ở những nơi có trách nhiệm rõ ràng**.

## 1. Ba thành phần trong một luồng nghiệp vụ

### 1.1. Tính toán: quyết định từ dữ liệu đầu vào

**Phần tính toán** (*computation*) nhận dữ liệu đã biết, áp dụng quy tắc và tạo ra kết quả. Ví dụ:

- Tính tổng tiền, chiết khấu hoặc phí vận chuyển.
- Phân loại một giao dịch theo mức rủi ro từ các dữ kiện đầu vào.
- Xác định một hạn thanh toán đã quá hạn hay chưa từ hạn và thời điểm được cung cấp.
- Tạo danh sách các dòng đơn hàng đủ điều kiện dựa trên trạng thái đầu vào.

Một **hàm thuần** (*pure function*) có hai đặc điểm chính:

1. Với cùng đầu vào và cùng quy tắc, hàm tạo cùng kết quả hoặc cùng lỗi được xác định bởi đầu vào.
2. Hàm không làm thay đổi trạng thái bên ngoài có thể quan sát được và không sửa dữ liệu thuộc sở hữu của bên gọi.

Ví dụ:

~~~java
public static long totalVnd(long unitPriceVnd, int quantity) {
    if (unitPriceVnd < 0 || quantity <= 0) {
        throw new IllegalArgumentException("Invalid price or quantity");
    }
    return Math.multiplyExact(unitPriceVnd, quantity);
}
~~~

Hàm trên chỉ phụ thuộc hai tham số, không đọc đồng hồ, cơ sở dữ liệu hoặc trạng thái toàn cục, và không ghi dữ liệu. Với đầu vào quá lớn, **Math.multiplyExact** ném ngoại lệ tràn số một cách xác định; việc kiểm tra lỗi không biến phép tính thành thao tác I/O.

Không phải mọi phần tính toán đều bắt buộc dùng hàm thuần. Tuy vậy, càng nhiều quy tắc nghiệp vụ có thể biểu diễn bằng dữ liệu đầu vào và kết quả rõ ràng, càng dễ kiểm thử và phân tích độc lập.

### 1.2. Điều phối: xác định trình tự các bước

**Phần điều phối** (*orchestration*) quyết định những bước nào cần chạy, chạy theo thứ tự nào, kết quả của bước trước được chuyển cho bước sau ra sao, và xử lý tình huống thất bại như thế nào.

Ví dụ một quy trình thanh toán:

~~~text
Nhận yêu cầu
     |
     v
Lấy giá sản phẩm và trạng thái khách hàng
     |
     v
Tính báo giá từ dữ kiện đã lấy
     |
     v
Gửi yêu cầu thu tiền
     |
     v
Lưu kết quả và phát thông báo
     |
     v
Trả phản hồi
~~~

Điều phối biết **lúc nào** cần gọi các thành phần. Nó không nhất thiết phải tự chứa **cách tính** mọi quy tắc giá, thuế, hạn mức hoặc trạng thái.

### 1.3. Tác dụng phụ: tương tác và thay đổi thế giới bên ngoài

**Tác dụng phụ** (*side effect*) là tương tác hoặc thay đổi trạng thái có thể quan sát ngoài kết quả trả về thuần túy của hàm. Một số ví dụ:

| Hoạt động | Vì sao là tác dụng phụ hoặc phụ thuộc ngoại cảnh? |
| --- | --- |
| Ghi cơ sở dữ liệu, tệp hoặc cache dùng chung | Thay đổi trạng thái mà lời gọi khác có thể quan sát |
| Gửi email hoặc gọi API thanh toán | Tạo tác động bên ngoài tiến trình |
| Ghi log, phát metric | Gửi thông tin tới hệ thống quan sát |
| Đọc cơ sở dữ liệu hoặc tệp | Kết quả phụ thuộc trạng thái bên ngoài, nên không phải phép tính thuần |
| Đọc thời gian hiện tại | Cùng tham số vẫn có thể cho kết quả khác theo thời điểm |
| Sinh số ngẫu nhiên, UUID | Kết quả phụ thuộc nguồn ngẫu nhiên hoặc trạng thái nội bộ |
| Sửa đối tượng truyền vào hoặc biến toàn cục | Thay đổi trạng thái mà bên khác có thể thấy |

Cần phân biệt: **đọc dữ liệu bên ngoài** có thể không làm thay đổi nguồn dữ liệu, nhưng vẫn khiến kết quả phụ thuộc môi trường. Vì vậy nó cũng cần được đưa ra khỏi phần tính toán thuần khi muốn có hành vi xác định.

## 2. Vì sao trộn cả ba làm tăng độ phức tạp?

Xét một phương thức vừa lấy giá từ kho dữ liệu, tính khuyến mại, gọi cổng thanh toán, lưu đơn hàng và gửi email xác nhận. Để hiểu một phép tính sai, người đọc phải lần theo cả các phụ thuộc mạng và cơ sở dữ liệu; để kiểm thử quy tắc giảm giá, có thể phải dựng nhiều đối tượng giả cho những việc không liên quan.

| Kiểu kết hợp | Độ phức tạp phát sinh |
| --- | --- |
| Tính toán phụ thuộc truy vấn | Khó tạo đầu vào cố định và tái hiện lỗi |
| Quy tắc nghiệp vụ nằm giữa các lời gọi I/O | Khó nhận diện điều kiện và kiểm thử giá trị biên |
| Ghi trạng thái nằm trong phép tính | Gọi lại để kiểm tra có thể gây tác động ngoài ý muốn |
| Đọc thời gian hoặc ngẫu nhiên ở sâu trong hàm | Kiểm thử lúc đúng ngưỡng thời gian trở nên không ổn định |
| Xử lý lỗi mạng trộn với công thức | Một phương thức phải quản lý nhiều loại thất bại khác nhau |
| Nhiều hiệu ứng bên ngoài không có trình tự rõ | Khó lý giải tình trạng cập nhật một phần hoặc retry |

Số dòng không đo hết sự phức tạp. Một phương thức ngắn với nhiều lời gọi ẩn tác dụng phụ có thể khó hiểu hơn một luồng tuần tự dài hơn nhưng phân tách trách nhiệm tốt.

Mô hình thường được gọi là **functional core, imperative shell** có thể minh họa như sau:

~~~text
          Thế giới bên ngoài
       (DB, mạng, đồng hồ, tệp)
                  |
                  v
      +------------------------+
      | Lớp điều phối / I/O    |
      | lấy dữ kiện, gọi dịch vụ|
      +------------------------+
                  |
         đầu vào rõ nghĩa
                  |
                  v
      +------------------------+
      | Lõi tính toán          |
      | quy tắc xác định       |
      +------------------------+
                  |
        kết quả / quyết định
                  |
                  v
      +------------------------+
      | Lớp điều phối / I/O    |
      | lưu, gửi, phản hồi     |
      +------------------------+
~~~

Đây là một **nguyên tắc tổ chức trách nhiệm**, không bắt buộc phải tạo nhiều tầng kiến trúc, nhiều service hay áp dụng một framework cụ thể.

## 3. Ví dụ Java: tính giá và điều phối thanh toán

Giả sử một ứng dụng bán hàng có hợp đồng:

1. Số lượng mua phải dương và đơn giá không âm.
2. Thành viên được giảm **10% tổng tiền hàng**, làm tròn xuống đến đơn vị VND.
3. Phí vận chuyển là **30.000 VND** nếu tổng sau giảm giá **nhỏ hơn 500.000 VND**; ngược lại miễn phí.
4. Tổng thanh toán bằng tiền hàng sau giảm giá cộng phí vận chuyển.
5. Sau khi có báo giá, quy trình mới gọi cổng thanh toán và ghi nhận đơn.

Ở ví dụ này dùng số nguyên **long** biểu diễn VND, thay vì **double**, để tránh sai lệch do biểu diễn số thực nhị phân. Phần xử lý tràn số dùng **Math.multiplyExact**, **Math.subtractExact** và **Math.addExact**.

### 3.1. Cách viết trộn quy tắc và I/O

~~~java
public final class MixedCheckoutService {
    private final Catalog catalog;
    private final Customers customers;
    private final PaymentGateway payments;
    private final OrderStore orders;
    private final Notifier notifier;

    public MixedCheckoutService(
            Catalog catalog, Customers customers,
            PaymentGateway payments, OrderStore orders,
            Notifier notifier) {
        this.catalog = catalog;
        this.customers = customers;
        this.payments = payments;
        this.orders = orders;
        this.notifier = notifier;
    }

    public CheckoutReceipt checkout(
            String customerId, String sku, int quantity) {
        long unitPriceVnd = catalog.unitPriceVnd(sku);
        boolean member = customers.isMember(customerId);

        if (quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid order");
        }

        long subtotalVnd = Math.multiplyExact(unitPriceVnd, quantity);
        long discountVnd = member ? subtotalVnd / 10 : 0L;
        long afterDiscountVnd =
                Math.subtractExact(subtotalVnd, discountVnd);
        long shippingFeeVnd =
                afterDiscountVnd >= 500_000L ? 0L : 30_000L;
        long totalVnd =
                Math.addExact(afterDiscountVnd, shippingFeeVnd);

        String paymentId = payments.charge(customerId, totalVnd);
        orders.save(customerId, sku, quantity, totalVnd, paymentId);
        notifier.sendConfirmation(customerId, paymentId);
        return new CheckoutReceipt(paymentId, totalVnd);
    }
}
~~~

Các giao diện **Catalog**, **Customers**, **PaymentGateway**, **OrderStore**, **Notifier** và kiểu **CheckoutReceipt** là các thành phần ứng dụng giả định, được nêu ở đây để làm rõ vai trò. Phương thức trên không sai chỉ vì dài; vấn đề là **hai lý do thay đổi khác nhau** cùng nằm một chỗ:

- Thay đổi chính sách giảm giá hoặc vận chuyển.
- Thay đổi quy trình thanh toán, lưu đơn hoặc gửi thông báo.

Muốn kiểm thử điều kiện đúng 500.000 VND, người viết kiểm thử phải quan tâm cả việc lấy giá, xác định thành viên, thanh toán và lưu đơn. Khi xử lý một lỗi thanh toán, người đọc lại phải đi qua những phép tính không liên quan.

### 3.2. Tách chính sách tính giá thành hàm thuần

~~~java
public record PriceQuote(
        long subtotalVnd,
        long discountVnd,
        long shippingFeeVnd,
        long totalVnd) {}

public final class PricingPolicy {
    private static final long FREE_SHIPPING_FROM_VND = 500_000L;
    private static final long STANDARD_SHIPPING_FEE_VND = 30_000L;

    private PricingPolicy() {}

    public static PriceQuote quote(
            long unitPriceVnd, int quantity, boolean member) {
        if (quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid order");
        }

        long subtotalVnd = Math.multiplyExact(unitPriceVnd, quantity);
        long discountVnd = member ? subtotalVnd / 10 : 0L;
        long afterDiscountVnd =
                Math.subtractExact(subtotalVnd, discountVnd);
        long shippingFeeVnd =
                afterDiscountVnd >= FREE_SHIPPING_FROM_VND
                        ? 0L : STANDARD_SHIPPING_FEE_VND;
        long totalVnd =
                Math.addExact(afterDiscountVnd, shippingFeeVnd);

        return new PriceQuote(
                subtotalVnd, discountVnd, shippingFeeVnd, totalVnd);
    }
}
~~~

Đây là ví dụ Java hiện đại sử dụng **record**, có từ Java 16. Trong dự án Java thực tế, **PriceQuote** và **PricingPolicy** được đặt trong các tệp nguồn thích hợp; hai khai báo **public** ở trên được trình bày chung để tiện đọc bài.

Những đặc điểm đáng chú ý:

- Tất cả dữ kiện tính toán đều được truyền vào dưới dạng tham số. Không có truy vấn DB, gửi email, đọc đồng hồ hoặc biến toàn cục thay đổi.
- Hàm không sửa tham số và trả về một **kết quả có tên trường rõ nghĩa**.
- Cùng đơn giá, số lượng và trạng thái thành viên sẽ cho cùng báo giá hoặc cùng lỗi.
- Trường hợp tràn số được phát hiện trước khi có thao tác thu tiền.
- Có thể kiểm tra quy tắc ở giá trị biên mà không cần dựng cổng thanh toán hoặc kết nối cơ sở dữ liệu.

Phần giảm giá dùng phép chia số nguyên theo chính sách **làm tròn xuống VND**. Đổi thứ tự áp giảm giá và phí vận chuyển, hoặc đổi cách làm tròn, sẽ là **thay đổi hành vi**, cần có yêu cầu nghiệp vụ và kiểm thử tương ứng.

### 3.3. Để phần điều phối tập trung vào trình tự và kết quả

~~~java
public final class CheckoutService {
    private final Catalog catalog;
    private final Customers customers;
    private final PaymentGateway payments;
    private final OrderStore orders;
    private final Notifier notifier;

    public CheckoutService(
            Catalog catalog, Customers customers,
            PaymentGateway payments, OrderStore orders,
            Notifier notifier) {
        this.catalog = catalog;
        this.customers = customers;
        this.payments = payments;
        this.orders = orders;
        this.notifier = notifier;
    }

    public CheckoutReceipt checkout(
            String customerId, String sku, int quantity) {
        long unitPriceVnd = catalog.unitPriceVnd(sku);
        boolean member = customers.isMember(customerId);

        PriceQuote quote =
                PricingPolicy.quote(unitPriceVnd, quantity, member);

        String paymentId =
                payments.charge(customerId, quote.totalVnd());
        orders.save(customerId, sku, quantity,
                quote.totalVnd(), paymentId);
        notifier.sendConfirmation(customerId, paymentId);
        return new CheckoutReceipt(paymentId, quote.totalVnd());
    }
}
~~~

Phương thức điều phối giờ thể hiện bốn bước chính: **lấy dữ kiện → tính báo giá → thực hiện thanh toán → ghi nhận và thông báo**. Người đọc có thể tìm quy tắc giá ở **PricingPolicy**, còn trình tự I/O ở **CheckoutService**.

Hai đoạn mã **MixedCheckoutService** và **CheckoutService** mang tính so sánh kiến trúc; chúng giả định cùng các giao diện tương tác với hệ thống bên ngoài. Việc tách này không tự làm hệ thống nhanh hơn hay bảo đảm giao dịch phân tán. Nó chủ yếu làm rõ trách nhiệm, cho phép xác minh tính toán độc lập và dễ thấy các điểm có tác dụng phụ.

## 4. Kiểm thử phần tính toán không cần hạ tầng bên ngoài

Với **PricingPolicy**, kiểm thử chỉ truyền dữ liệu và so sánh kết quả:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PricingPolicyTest {
    @Test
    void calculatesMemberDiscountAndFreeShipping() {
        PriceQuote quote = PricingPolicy.quote(600_000L, 1, true);

        assertEquals(600_000L, quote.subtotalVnd());
        assertEquals(60_000L, quote.discountVnd());
        assertEquals(0L, quote.shippingFeeVnd());
        assertEquals(540_000L, quote.totalVnd());
    }

    @Test
    void checksShippingThresholdAfterDiscount() {
        PriceQuote quote = PricingPolicy.quote(500_000L, 1, true);

        assertEquals(50_000L, quote.discountVnd());
        assertEquals(30_000L, quote.shippingFeeVnd());
        assertEquals(480_000L, quote.totalVnd());
    }

    @Test
    void checksThresholdForNonMember() {
        assertEquals(529_999L,
                PricingPolicy.quote(499_999L, 1, false).totalVnd());
        assertEquals(500_000L,
                PricingPolicy.quote(500_000L, 1, false).totalVnd());
    }

    @Test
    void rejectsInvalidQuantityBeforeAnyExternalAction() {
        assertThrows(IllegalArgumentException.class,
                () -> PricingPolicy.quote(10_000L, 0, false));
    }

    @Test
    void reportsArithmeticOverflow() {
        assertThrows(ArithmeticException.class,
                () -> PricingPolicy.quote(Long.MAX_VALUE, 2, false));
    }
}
~~~

Các kiểm thử này nhanh, có tính lặp lại cao và bộc lộ quy tắc làm tròn, ngưỡng miễn phí và đầu vào không hợp lệ. Chúng chỉ kiểm tra **lõi tính toán**.

Để kiểm tra **điều phối**, vẫn cần những kiểm thử riêng với đối tượng giả hoặc môi trường tích hợp, chẳng hạn:

1. Khi việc lấy giá thất bại, cổng thanh toán không được gọi.
2. Khi tính báo giá ném lỗi, không có lần thu tiền nào được tạo.
3. Khi thanh toán thành công, đúng **tổng từ PriceQuote** được chuyển cho nơi lưu đơn.
4. Khi gửi thông báo thất bại, kết quả thanh toán và trạng thái đơn được xử lý theo hợp đồng nghiệp vụ.
5. Khi yêu cầu chạy lại hoặc chạy đồng thời, không phát sinh khoản thu tiền trùng nếu nghiệp vụ yêu cầu tính lặp an toàn.

Đối tượng giả có thể xác nhận thứ tự và tham số của lời gọi, nhưng không thay thế kiểm thử tích hợp với DB, giao dịch, timeout mạng hoặc cơ chế thử lại.

## 5. Tách phần tính toán khỏi đồng hồ và nguồn ngẫu nhiên

Một phép so sánh thời gian có vẻ thuần khiết, nhưng việc gọi **Instant.now()** ngay bên trong làm kết quả phụ thuộc môi trường:

~~~java
boolean isExpired(Instant expiresAt) {
    return !Instant.now().isBefore(expiresAt);
}
~~~

Cùng tham số **expiresAt**, kết quả có thể đổi từ **false** sang **true** giữa hai lần gọi. Điều đó làm kiểm thử thời điểm sát hạn khó tái lập.

Đưa thời gian hiện tại vào dữ liệu:

~~~java
import java.time.Instant;

public final class ExpirationPolicy {
    private ExpirationPolicy() {}

    public static boolean isExpired(Instant expiresAt, Instant now) {
        return !now.isBefore(expiresAt);
    }
}
~~~

Ở ranh giới điều phối, ta quyết định nguồn thời gian:

~~~java
import java.time.Clock;
import java.time.Instant;

public boolean checkExpiration(Instant expiresAt, Clock clock) {
    Instant now = Instant.now(clock);
    return ExpirationPolicy.isExpired(expiresAt, now);
}
~~~

Có thể dùng **Clock.fixed(...)** trong kiểm thử điều phối để kiểm soát thời gian. Còn kiểm thử chính sách chỉ cần truyền hai **Instant** cụ thể.

Đối với ngẫu nhiên cũng tương tự: lớp điều phối có thể yêu cầu sinh một mã hoặc chọn giá trị ngẫu nhiên, rồi truyền giá trị được tạo vào phần tính toán. Nếu chính sách thực sự yêu cầu tính ngẫu nhiên, cần mô tả rõ nguồn ngẫu nhiên và khả năng tái lập trong kiểm thử, thay vì giả vờ đây là phép tính xác định.

## 6. Tách phần quyết định khỏi phần thực hiện

Không phải mọi quyết định đều là phép tính số học. Ví dụ, một hệ thống có thể quyết định **nên gửi lời nhắc thanh toán hay không** dựa trên ngày đến hạn, số dư và trạng thái của hóa đơn.

~~~java
import java.time.LocalDate;

public record InvoiceSnapshot(
        long outstandingVnd,
        LocalDate dueDate,
        boolean cancelled) {}

public enum ReminderDecision {
    SEND_REMINDER,
    SKIP
}

public final class ReminderPolicy {
    private ReminderPolicy() {}

    public static ReminderDecision decide(
            InvoiceSnapshot invoice, LocalDate today) {
        if (invoice.cancelled() || invoice.outstandingVnd() <= 0) {
            return ReminderDecision.SKIP;
        }

        return today.isAfter(invoice.dueDate())
                ? ReminderDecision.SEND_REMINDER
                : ReminderDecision.SKIP;
    }
}
~~~

Những kiểu **InvoiceSnapshot**, **ReminderDecision** và **ReminderPolicy** được trình bày chung để minh họa; khi dùng trong Java, mỗi khai báo public có tệp nguồn tương ứng.

**ReminderPolicy** không gửi email và không đánh dấu hóa đơn đã được nhắc. Nó chỉ trả lời câu hỏi “theo dữ kiện này, có nên gửi lời nhắc không?”. Phần điều phối mới là nơi tải dữ liệu, xác định ngày hiện tại và quyết định thực hiện tác dụng phụ:

~~~java
InvoiceSnapshot invoice = invoiceRepository.findSnapshot(invoiceId);
LocalDate today = LocalDate.now(clock);

ReminderDecision decision = ReminderPolicy.decide(invoice, today);
if (decision == ReminderDecision.SEND_REMINDER) {
    reminderSender.send(invoiceId);
    reminderHistory.recordSent(invoiceId, today);
}
~~~

Các thành phần **invoiceRepository**, **clock**, **reminderSender** và **reminderHistory** là phụ thuộc giả định của lớp điều phối.

**Lưu ý về độ tin cậy:** ví dụ thứ tự gửi và ghi lịch sử vẫn có một khoảng lỗi. Nếu gửi thành công nhưng ghi lịch sử thất bại, lần chạy sau có thể gửi trùng. Phân tách quyết định khỏi tác dụng phụ làm nguy cơ **dễ nhận diện hơn**, nhưng không tự giải quyết vấn đề. Hệ thống thực có thể cần idempotency key, hàng đợi với consumer lặp an toàn, transactional outbox hoặc cơ chế đối soát phù hợp.

## 7. Kiểm soát dữ liệu đầu vào và ranh giới trạng thái

Tính thuần có thể bị phá vỡ ngay cả khi không có I/O:

~~~java
public static long sumAndSort(List<Long> amounts) {
    amounts.sort(Long::compareTo); // Sửa danh sách của bên gọi.

    long sum = 0L;
    for (long amount : amounts) {
        sum = Math.addExact(sum, amount);
    }
    return sum;
}
~~~

Vì phương thức sắp xếp trực tiếp danh sách truyền vào, bên gọi quan sát được thứ tự phần tử đã thay đổi. Nếu việc sắp xếp không liên quan đến yêu cầu, cách đơn giản hơn là **không sắp xếp**:

~~~java
public static long sum(List<Long> amounts) {
    long sum = 0L;
    for (long amount : amounts) {
        sum = Math.addExact(sum, amount);
    }
    return sum;
}
~~~

Trong ví dụ thứ hai, giả định danh sách và các phần tử không null, không bị thread khác sửa đồng thời trong lúc tính. Hàm không chủ động thay đổi dữ liệu đầu vào, nhưng để có tính xác định đáng tin cậy, **đầu vào phải ổn định trong suốt thời gian tính**.

Với đối tượng có thể thay đổi (*mutable*), có thể dùng:

- Bản chụp dữ liệu (*snapshot*) hoặc các giá trị bất biến làm đầu vào phần tính toán.
- Record và các lớp giá trị với trường được thiết kế bất biến.
- Sao chép phòng vệ (*defensive copy*) khi cần tách quyền sở hữu.
- Hợp đồng rõ về việc phần nào được phép thay đổi dữ liệu đầu vào.

Lưu ý: **record không tự tạo bất biến sâu**. Nếu một record chứa **List** có thể sửa được, nội dung danh sách vẫn có thể đổi trừ khi có cơ chế sao chép hoặc bảo vệ thích hợp.

## 8. Tính đúng đắn và xử lý lỗi vẫn là trách nhiệm của hệ thống

Phân tách phần tính toán làm giảm độ phức tạp trong kiểm thử quy tắc, nhưng một luồng nghiệp vụ còn phải duy trì tính đúng đắn qua nhiều tác dụng phụ.

Trong ví dụ thanh toán, hãy xét các điểm thất bại:

| Điểm lỗi | Kết quả phần tính toán | Vấn đề điều phối cần giải quyết |
| --- | --- | --- |
| Không lấy được giá sản phẩm | Chưa có dữ kiện để tính | Trả lỗi phù hợp, không thu tiền |
| Số lượng không hợp lệ | Hàm tính ném IllegalArgumentException | Không thực hiện các tác dụng phụ tiếp theo |
| Thanh toán bị từ chối | Báo giá đã có | Không xác nhận đơn là đã thanh toán |
| Thanh toán thành công, ghi đơn thất bại | Báo giá vẫn đúng | Cần đối soát hoặc phục hồi trạng thái thu tiền |
| Ghi đơn thành công, gửi email thất bại | Báo giá vẫn đúng | Cần cơ chế phát thông báo lại hoặc theo dõi lỗi |
| Bên gọi timeout và thử lại | Báo giá có thể tính lại | Cần xác định có được thu tiền lại hay không |

Những tình huống này cho thấy **tính đúng của phép tính** và **tính đúng của toàn bộ quy trình** là hai phạm vi kiểm chứng khác nhau.

Một số giải pháp phụ thuộc vào hệ thống:

- Sử dụng **giao dịch DB** khi nhiều thay đổi có thể nằm trong một ranh giới commit.
- Dùng **idempotency key** đối với tác dụng phụ có nguy cơ bị lặp khi retry.
- Dùng **transactional outbox** khi muốn lưu ý định phát sự kiện cùng giao dịch dữ liệu.
- Thiết kế **trạng thái trung gian** và thao tác bù trừ cho quy trình có nhiều hệ thống độc lập.
- Giữ log/trace/metric ở lớp điều phối hoặc cổng tương tác để chẩn đoán luồng ngoài đời thực.

Những cơ chế này bổ sung cho cách tổ chức mã, không phải lý do để đưa lại mọi quy tắc nghiệp vụ và thao tác I/O vào một phương thức lớn.

## 9. Tách tới mức nào là vừa đủ?

**Không cần biến mọi phép cộng, biểu thức Boolean hoặc phương thức một dòng thành một service riêng.** Sự phân tách chỉ có ích khi ranh giới đó giúp người đọc hiểu, kiểm thử hoặc thay đổi một trách nhiệm độc lập.

| Tình huống | Phân tách thường có ích | Khi nào có thể quá mức |
| --- | --- | --- |
| Công thức giá thay đổi theo nghiệp vụ | Đặt chính sách tính giá độc lập với cổng thanh toán | Tạo lớp riêng cho từng phép cộng và phép so sánh nhỏ |
| Kiểm tra hạn từ thời điểm hiện tại | Truyền thời điểm vào quy tắc, đọc đồng hồ ở ranh giới | Dựng nhiều tầng chỉ để bọc một lời gọi Instant.now |
| Xử lý API với nhiều phụ thuộc | Gom quy tắc vào phần tính toán, cho điều phối thấy trình tự I/O | Bắt người đọc đi qua hàng loạt interface không có mục đích rõ |
| Tạo quyết định từ dữ liệu | Trả một kiểu kết quả có ý nghĩa nghiệp vụ | Trả đối tượng chứa quá nhiều cờ không có hợp đồng rõ |
| Tác dụng phụ có retry và trạng thái | Làm rõ cổng I/O, các bước commit và cách phục hồi | Che thứ tự tác dụng phụ sau một tên chung như executeEverything |

Có những thay đổi làm hàm ngắn đi nhưng **chỉ chuyển độ phức tạp sang nơi khác**. Nếu phải mở năm tệp mới hiểu một quy tắc đơn giản, việc phân tách chưa chắc cải thiện khả năng đọc. Cũng không nhất thiết chọn một thư viện lập trình hàm để xây dựng lõi tính toán thuần: phương thức static hoặc một lớp Java bình thường hoàn toàn có thể đáp ứng.

### Chi phí của việc phân tách

- Phải thiết kế kiểu đầu vào và đầu ra rõ nghĩa; đôi khi cần record hoặc đối tượng quyết định.
- Có thể phải chuyển nhiều tham số từ lớp điều phối vào lõi tính toán.
- Tăng số lớp, giao diện hoặc tệp nếu áp dụng máy móc.
- Trạng thái thay đổi liên tục hoặc quy tắc phụ thuộc nhiều dữ liệu bên ngoài có thể đòi hỏi bước chụp dữ liệu và kiểm soát nhất quán.

Đây là những đánh đổi thực tế. Cần cân nhắc **mức độ biến động của quy tắc**, **độ khó kiểm thử**, **số phụ thuộc bên ngoài**, **rủi ro cập nhật một phần** và **khả năng điều hướng của người đọc**.

## 10. Quy trình thực hành để giảm độ phức tạp

Khi gặp phương thức trộn tính toán và tác dụng phụ, có thể làm theo thứ tự:

1. **Viết hợp đồng hiện tại:** Đầu vào hợp lệ, kết quả, ngoại lệ, tác dụng phụ, thứ tự cần giữ và dữ liệu phải được cập nhật.
2. **Đánh dấu đường biên:** Phân biệt bước đọc dữ liệu, phép tính/ra quyết định và bước thay đổi thế giới bên ngoài.
3. **Tập hợp dữ kiện cần cho quy tắc:** Chọn những giá trị có thể truyền qua tham số hoặc snapshot, kể cả ngày giờ và trạng thái đã được lấy từ bên ngoài.
4. **Rút ra một quy tắc có ý nghĩa:** Đặt tên theo nghiệp vụ, chọn kiểu trả về thể hiện đầy đủ kết quả, tránh sửa đầu vào.
5. **Đặt kiểm tra đầu vào ở nơi phù hợp:** Quy tắc kiểm tra bất biến có thể ở lõi; xác thực quyền truy cập, thông tin phiên hoặc trạng thái DB mới nhất vẫn cần diễn ra ở ranh giới hệ thống phù hợp.
6. **Giữ phần điều phối dễ lần theo:** Thể hiện rõ thứ tự lấy dữ liệu, tính, thực hiện tác dụng phụ, xử lý lỗi và trả phản hồi.
7. **Kiểm thử hai cấp độ:** Kiểm thử thuần cho các bảng quyết định và giá trị biên; kiểm thử điều phối/tích hợp cho lời gọi, giao dịch, thời gian chờ và retry.
8. **So sánh trước và sau:** Xác nhận hợp đồng hành vi không đổi, đánh giá liệu người đọc có dễ xác định nơi chứa quy tắc và nơi xảy ra I/O hơn không.

Kết quả mong muốn là **giảm số điều phải suy luận cùng lúc**. Khi đọc lõi tính toán, ta tập trung vào quy tắc. Khi đọc điều phối, ta tập trung vào trình tự và các điểm thất bại bên ngoài.

## 11. Các hiểu nhầm thường gặp

**“Hàm thuần là hàm không gọi cơ sở dữ liệu, còn lại làm gì cũng được.”** Sửa một danh sách truyền vào, đọc biến toàn cục có thể thay đổi hoặc gọi đồng hồ hệ thống cũng làm mất tính thuần theo hợp đồng đang xét.

**“Tách phép tính khỏi I/O sẽ tự sửa mọi lỗi giao dịch.”** Nó làm ranh giới tác dụng phụ rõ hơn, nhưng không tự mang lại tính nguyên tử, tính cô lập hoặc bảo đảm đúng một lần.

**“Tất cả kiểm tra đầu vào phải nằm trong lớp điều phối.”** Những quy tắc thuộc miền tính toán, như số lượng dương hoặc giá không âm, có thể đặt ngay trong chính sách tính toán. Các kiểm tra phụ thuộc người dùng hiện tại, quyền hoặc trạng thái cơ sở dữ liệu cần dữ kiện từ ranh giới phù hợp.

**“Phải áp dụng kiến trúc nhiều lớp mới có tính thuần.”** Một phương thức Java nhỏ, rõ ràng, không đụng I/O đã là một phần tính toán tách biệt; không cần xây nhiều cấu trúc hình thức chỉ vì một bài toán đơn giản.

**“Mã không có tác dụng phụ nên không thể sai.”** Công thức vẫn có thể dùng nhầm ngưỡng, làm tròn sai hoặc tràn số. Tính thuần giúp lỗi dễ tái hiện và kiểm thử, không chứng minh tính đúng.

**“Một phương thức điều phối càng ngắn càng tốt.”** Một luồng rõ ràng với các bước có tên đúng thường dễ bảo trì hơn chuỗi gọi gián tiếp khiến thứ tự và lỗi bị che giấu.

**“Đọc DB là phép tính thuần vì không thay đổi dữ liệu.”** Kết quả truy vấn phụ thuộc trạng thái ngoài tham số; cùng câu lệnh có thể trả dữ liệu khác nhau ở hai thời điểm. Đưa dữ liệu đã đọc thành đầu vào mới giúp phần quyết định thuần hơn.

## 12. Tình huống luyện tập

Một dịch vụ gửi cảnh báo đơn hàng chậm có quy trình sau:

~~~java
void notifyIfLate(long orderId) {
    Order order = repository.findById(orderId);
    if (LocalDate.now().isAfter(order.expectedDeliveryDate())
            && !order.isDelivered()
            && order.delayHours() >= 24) {
        sender.sendDelayEmail(order.customerEmail());
        repository.markNotified(orderId);
    }
}
~~~

Giả sử **Order**, **repository** và **sender** là những thành phần ứng dụng hợp lệ. Hãy xác định:

1. Bước nào lấy dữ liệu bên ngoài? Bước nào tính/ra quyết định? Bước nào tạo tác dụng phụ?
2. Vì sao kiểm thử lúc sát ngày giao hàng dự kiến có thể không ổn định?
3. Có thể thiết kế một hàm quyết định với đầu vào cụ thể như thế nào?
4. Nếu email gửi thành công nhưng **markNotified** thất bại, điều gì xảy ra trong lần chạy kế tiếp?
5. Việc tách hàm quyết định có tự ngăn được email gửi trùng không?

Một cách tách trách nhiệm:

~~~java
public static boolean shouldNotify(
        LocalDate today,
        LocalDate expectedDeliveryDate,
        boolean delivered,
        long delayHours) {
    return today.isAfter(expectedDeliveryDate)
            && !delivered
            && delayHours >= 24;
}
~~~

Lớp điều phối có thể tải snapshot đơn hàng, lấy **today** từ một **Clock** đã xác định, gọi **shouldNotify**, sau đó thực hiện gửi email và ghi trạng thái khi cần. Ví dụ giữ nguyên điều kiện ban đầu với giả định các phép đọc đều ổn định và không có tác dụng phụ. Trong thiết kế thực tế còn cần quy tắc về trạng thái “đã thông báo”, xử lý email trùng, dữ liệu thay đổi đồng thời và phục hồi sau lỗi.

**Gợi ý đối chiếu:** Truy vấn repository và lấy thời gian là phụ thuộc bên ngoài; biểu thức so sánh là quyết định; gửi email và cập nhật trạng thái là tác dụng phụ. Tách quyết định giúp kiểm thử các ngày và mốc 24 giờ bằng dữ liệu cố định. Nếu gửi email xong rồi ghi trạng thái thất bại, một lần chạy sau có thể gửi trùng. Cần xử lý idempotency hoặc cơ chế ghi nhận ý định phát thông báo đáng tin cậy phù hợp, bên cạnh việc phân tách phần tính toán.

## 13. Ghi nhớ

- **Tính toán** nhận dữ kiện và tạo kết quả; **điều phối** xác định thứ tự bước; **tác dụng phụ** tương tác với hoặc thay đổi trạng thái bên ngoài.
- Tách quy tắc ra khỏi I/O giúp giảm số phụ thuộc phải nhớ khi đọc mã, tạo kiểm thử ổn định và dễ thay đổi chính sách.
- Hàm thuần cần đầu vào rõ ràng và không làm thay đổi trạng thái bên ngoài; cả đồng hồ, ngẫu nhiên, dữ liệu toàn cục và đối tượng có thể sửa đều có thể gây phụ thuộc ngầm.
- Phần điều phối vẫn chịu trách nhiệm **thứ tự thao tác, lỗi I/O, giao dịch, retry và phục hồi trạng thái**; tính thuần không thay thế các cơ chế này.
- Chọn **ranh giới đủ có ý nghĩa**, tránh tách nhỏ máy móc. Đánh giá cải thiện bằng khả năng hiểu quy tắc, kiểm thử và thay đổi an toàn, thay vì chỉ số dòng hoặc số lớp.
