# Cải thiện thiết kế từng bước với kiểm thử bảo vệ — Java OOP

## 1. Mục tiêu của bài học

**Refactoring (tái cấu trúc)** là thay đổi cách tổ chức bên trong của mã nguồn để code dễ hiểu, dễ mở rộng, dễ kiểm thử hơn, trong khi **giữ nguyên hành vi quan sát được đã cam kết**. Nó có thể bao gồm tách phương thức, chuyển trách nhiệm sang lớp phù hợp, làm rõ tên, xóa lặp và giảm phụ thuộc.

Đổi nhiều thứ cùng lúc khiến ta khó biết lỗi bắt đầu ở đâu. Cách an toàn hơn là áp dụng chu trình ngắn:

**Xác định hành vi → viết kiểm thử bảo vệ → thay đổi thiết kế nhỏ → chạy kiểm thử → xem lại code → lặp tiếp.**

Một **kiểm thử bảo vệ** (safety-net test) là bài test giúp phát hiện thay đổi ngoài ý muốn trong hành vi hiện có. Nó không chứng minh toàn bộ hệ thống hoàn toàn đúng, nhưng tạo một hàng rào hồi quy khi ta sửa cấu trúc.

Đừng nhầm ba loại thay đổi:

| Loại thay đổi | Ý định | Cần kiểm chứng |
|---|---|---|
| Refactoring | Đổi cấu trúc, giữ hợp đồng | Các test hành vi trước/sau vẫn đạt |
| Bug fix | Sửa hành vi sai thành đúng | Test tái hiện bug thất bại trước khi sửa, đạt sau khi sửa |
| Thay đổi tính năng | Thay hoặc mở rộng hợp đồng | Test mới cho yêu cầu mới và test hồi quy cũ |

**Quy tắc thực tế:** Khi một bước refactor bất ngờ làm test đỏ, cần tìm nguyên nhân và xử lý trước khi chuyển sang bước khác. Không xóa assertion chỉ để test xanh trở lại.

## 2. Kiểm thử bảo vệ điều gì?

Hợp đồng của một lớp OOP có thể gồm:

- Giá trị trả về: tổng tiền, trạng thái xử lý, kết quả sắp xếp.
- Dữ liệu bị thay đổi: tồn kho, trạng thái đơn hàng, bộ đếm đã công bố.
- Exception hoặc tín hiệu lỗi được quy định: input rỗng, số lượng âm, dữ liệu trùng.
- Tác dụng phụ có ý nghĩa: gửi thông báo, ghi repository, gọi hệ thống thanh toán.
- Quy tắc biên: đúng ngưỡng giảm giá, thời hạn, 0, 1, rỗng, giới hạn số.

Ngược lại, một test ràng buộc số lần gọi private helper, tên private field, cấu trúc vòng lặp hoặc loại collection tùy ý thường **quá phụ thuộc implementation**. Những chi tiết ấy có thể thay đổi hợp lệ khi refactor.

**Một câu hỏi để review test:** Nếu đổi hoàn toàn thuật toán nhưng client vẫn nhận cùng kết quả và hiệu ứng đã cam kết, bài test có nên tiếp tục PASS không? Với unit test nghiệp vụ thông thường, câu trả lời thường là có.

## 3. Khi code cũ chưa có test: characterization test

Đôi khi ta cần cải thiện lớp cũ nhưng không có tài liệu đầy đủ. **Characterization test** ghi lại hành vi đang thực sự diễn ra, kể cả chi tiết bất ngờ, để nhận biết thay đổi vô tình.

Ví dụ một phương thức tính phí giao hàng hiện dùng điều kiện **từ 700.000 VND trở lên** để miễn phí. Trước khi tách phương thức, ghi lại các case 699.999 và 700.000 VND. Nếu refactor biến dấu >= thành >, test sẽ báo lỗi ở đúng ngưỡng.

Lưu ý: hành vi hiện tại không phải lúc nào cũng là hành vi **mong muốn**. Nếu phát hiện bug cũ, ghi nhận nó, làm rõ yêu cầu, rồi sửa bug trong một bước riêng có test biểu diễn kỳ vọng đúng. Không đóng băng bug chỉ vì characterization test đang xanh.

Cần ưu tiên vài kịch bản có giá trị cao trước: luồng thường dùng, ngưỡng quan trọng, lỗi input, tác dụng phụ, số tiền hoặc tài nguyên có nguy cơ lớn. Không cần viết hàng trăm test trước khi thay một dòng, nhưng cũng không nên refactor vùng rủi ro mà không có kiểm chứng.

## 4. Ví dụ xuyên suốt: cải thiện lớp thanh toán qua nhiều bước

Ta dùng cùng một bài toán để quan sát cấu trúc **trước và sau**:

- Một đơn hàng có danh sách dòng hàng. Mỗi dòng có mã sản phẩm, số lượng dương và đơn giá không âm, tính bằng **VND nguyên**.
- **Subtotal** là tổng của số lượng × đơn giá; một đơn phải có ít nhất một dòng.
- Khách VIP được giảm **10% subtotal**, làm tròn xuống theo chia số nguyên, nếu subtotal **từ 500.000 VND**.
- **Payable** = subtotal − discount.
- **Shipping** = 0 VND nếu payable **từ 700.000 VND**; nếu thấp hơn thì 30.000 VND.
- **Total** = payable + shipping.
- Biên nhận dùng một định dạng văn bản ổn định trong phạm vi bài học.

Phiên bản ban đầu gom toàn bộ validation, tính tiền và format receipt vào một phương thức. Phiên bản sau refactor tách tính giá thành **PricingPolicy**, tạo **ReceiptFormatter** để định dạng, và để **CheckoutService** điều phối hai collaborator.

~~~mermaid
flowchart LR
    subgraph Before["Trước"]
        L["LegacyCheckout: validate + calculate + format"]
    end
    subgraph After["Sau"]
        C["CheckoutService"] --> P["PricingPolicy: validate + calculate"]
        C --> F["ReceiptFormatter: format"]
    end
    T["Bộ kiểm thử hợp đồng"] --> L
    T --> C
~~~

Các bước cải thiện được thực hiện theo thứ tự:
1. Khóa lại các kết quả đầu ra và trường hợp lỗi bằng test.
2. Tách phần tính giá ra phương thức có tên rõ ràng.
3. Nhóm các phương thức tính giá liên quan vào một đối tượng PricingPolicy.
4. Tách trách nhiệm định dạng sang ReceiptFormatter.
5. Cho CheckoutService nhận collaborator qua constructor để luồng chính dễ đọc và dễ thay thế.
6. Sau **mỗi bước**, chạy lại cùng test. Chỉ loại bỏ code cũ khi đã kiểm chứng tương đương.

### Chương trình Java 11 tự chạy

Lưu toàn bộ trong file **SafeRefactoringDemo.java**; ví dụ không cần thư viện bên ngoài. Bản cũ và bản mới cùng triển khai interface Checkout. Một bộ test chạy cho cả hai và so sánh với kết quả **độc lập từ yêu cầu**, tránh tình huống hai implementation cùng sai mà vẫn được coi là tương đương.

~~~java
import java.util.List;
import java.util.Objects;

public class SafeRefactoringDemo {
    static final long VIP_THRESHOLD = 500_000L;
    static final long FREE_SHIPPING_THRESHOLD = 700_000L;
    static final long SHIPPING_FEE = 30_000L;

    static final class Item {
        final String sku;
        final int quantity;
        final long unitPriceVnd;

        Item(String sku, int quantity, long unitPriceVnd) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPriceVnd = unitPriceVnd;
        }
    }

    static final class Order {
        final List<Item> items;
        final boolean vip;

        Order(List<Item> items, boolean vip) {
            this.items = items;
            this.vip = vip;
        }
    }

    static final class Quote {
        final long subtotal;
        final long discount;
        final long shipping;
        final long total;
        final String receipt;

        Quote(long subtotal, long discount,
              long shipping, long total, String receipt) {
            this.subtotal = subtotal;
            this.discount = discount;
            this.shipping = shipping;
            this.total = total;
            this.receipt = receipt;
        }
    }

    interface Checkout {
        Quote quote(Order order);
    }

    // TRƯỚC: một method phải kiểm tra, tính toán, định dạng.
    static final class LegacyCheckout implements Checkout {
        @Override
        public Quote quote(Order order) {
            if (order == null || order.items == null
                    || order.items.isEmpty()) {
                throw new IllegalArgumentException("Empty order");
            }

            long subtotal = 0L;
            for (Item item : order.items) {
                if (item == null || item.sku == null
                        || item.sku.isBlank()
                        || item.quantity <= 0
                        || item.unitPriceVnd < 0) {
                    throw new IllegalArgumentException("Invalid item");
                }

                long lineAmount = Math.multiplyExact(
                        item.unitPriceVnd, (long) item.quantity);
                subtotal = Math.addExact(subtotal, lineAmount);
            }

            long discount = order.vip && subtotal >= VIP_THRESHOLD
                    ? subtotal / 10L : 0L;
            long payable = Math.subtractExact(subtotal, discount);
            long shipping = payable >= FREE_SHIPPING_THRESHOLD
                    ? 0L : SHIPPING_FEE;
            long total = Math.addExact(payable, shipping);

            String receipt = "subtotal=" + subtotal
                    + ";discount=" + discount
                    + ";shipping=" + shipping
                    + ";total=" + total;

            return new Quote(
                    subtotal, discount, shipping, total, receipt);
        }
    }

    // Đối tượng giá trị trung gian: kết quả tính tiền đã hoàn tất.
    static final class Pricing {
        final long subtotal;
        final long discount;
        final long shipping;
        final long total;

        Pricing(long subtotal, long discount,
                long shipping, long total) {
            this.subtotal = subtotal;
            this.discount = discount;
            this.shipping = shipping;
            this.total = total;
        }
    }

    // SAU bước tách: quy tắc giá được gom vào một lớp.
    static final class PricingPolicy {
        Pricing calculate(Order order) {
            long subtotal = calculateSubtotal(order);
            long discount = calculateDiscount(subtotal, order.vip);
            long payable = Math.subtractExact(subtotal, discount);
            long shipping = calculateShipping(payable);
            long total = Math.addExact(payable, shipping);

            return new Pricing(subtotal, discount, shipping, total);
        }

        private long calculateSubtotal(Order order) {
            if (order == null || order.items == null
                    || order.items.isEmpty()) {
                throw new IllegalArgumentException("Empty order");
            }

            long subtotal = 0L;
            for (Item item : order.items) {
                if (item == null || item.sku == null
                        || item.sku.isBlank()
                        || item.quantity <= 0
                        || item.unitPriceVnd < 0) {
                    throw new IllegalArgumentException("Invalid item");
                }

                long lineAmount = Math.multiplyExact(
                        item.unitPriceVnd, (long) item.quantity);
                subtotal = Math.addExact(subtotal, lineAmount);
            }
            return subtotal;
        }

        private long calculateDiscount(long subtotal, boolean vip) {
            return vip && subtotal >= VIP_THRESHOLD
                    ? subtotal / 10L : 0L;
        }

        private long calculateShipping(long payable) {
            return payable >= FREE_SHIPPING_THRESHOLD
                    ? 0L : SHIPPING_FEE;
        }
    }

    // SAU bước tách: định dạng là một trách nhiệm độc lập.
    static final class ReceiptFormatter {
        String format(Pricing pricing) {
            return "subtotal=" + pricing.subtotal
                    + ";discount=" + pricing.discount
                    + ";shipping=" + pricing.shipping
                    + ";total=" + pricing.total;
        }
    }

    // SAU: class điều phối sử dụng composition và constructor injection.
    static final class CheckoutService implements Checkout {
        private final PricingPolicy pricing;
        private final ReceiptFormatter formatter;

        CheckoutService(PricingPolicy pricing,
                        ReceiptFormatter formatter) {
            this.pricing = Objects.requireNonNull(pricing);
            this.formatter = Objects.requireNonNull(formatter);
        }

        @Override
        public Quote quote(Order order) {
            Pricing result = pricing.calculate(order);
            return new Quote(
                    result.subtotal,
                    result.discount,
                    result.shipping,
                    result.total,
                    formatter.format(result));
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    // Kỳ vọng nghiệp vụ độc lập với cả hai implementation.
    private static void expectQuote(
            Checkout checkout, Order order,
            long subtotal, long discount,
            long shipping, long total) {
        Quote actual = checkout.quote(order);
        String expectedReceipt = "subtotal=" + subtotal
                + ";discount=" + discount
                + ";shipping=" + shipping
                + ";total=" + total;

        check(actual.subtotal == subtotal, "Unexpected subtotal");
        check(actual.discount == discount, "Unexpected discount");
        check(actual.shipping == shipping, "Unexpected shipping");
        check(actual.total == total, "Unexpected total");
        check(expectedReceipt.equals(actual.receipt),
                "Unexpected receipt text");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    private static void expectOverflow(Runnable action) {
        try {
            action.run();
        } catch (ArithmeticException expected) {
            return;
        }
        throw new AssertionError("Expected ArithmeticException");
    }

    // CÙNG bộ test bảo vệ được chạy cho cả code cũ và code mới.
    private static void contractTests(Checkout checkout) {
        // Khách thường: 100.000 + 30.000 shipping = 130.000.
        expectQuote(checkout,
                new Order(List.of(new Item("PEN", 1, 100_000L)), false),
                100_000L, 0L, 30_000L, 130_000L);

        // VIP đúng ngưỡng giảm giá:
        // subtotal 500.000, discount 50.000,
        // payable 450.000, shipping 30.000 -> total 480.000.
        expectQuote(checkout,
                new Order(List.of(new Item("BOOK", 2, 250_000L)), true),
                500_000L, 50_000L, 30_000L, 480_000L);

        // VIP subtotal 800.000, discount 80.000,
        // payable 720.000 nên miễn phí shipping.
        expectQuote(checkout,
                new Order(List.of(new Item("BOOK", 2, 400_000L)), true),
                800_000L, 80_000L, 0L, 720_000L);

        // Khách thường, payable 699.999 vẫn chịu phí.
        expectQuote(checkout,
                new Order(List.of(new Item("A", 1, 699_999L)), false),
                699_999L, 0L, 30_000L, 729_999L);

        // Đúng ngưỡng 700.000: miễn phí, bắt lỗi đổi >= thành >.
        expectQuote(checkout,
                new Order(List.of(new Item("A", 1, 700_000L)), false),
                700_000L, 0L, 0L, 700_000L);

        expectInvalid(() -> checkout.quote(null));
        expectInvalid(() -> checkout.quote(new Order(List.of(), false)));
        expectInvalid(() -> checkout.quote(new Order(
                List.of(new Item("A", 0, 100L)), false)));
        expectInvalid(() -> checkout.quote(new Order(
                List.of(new Item("A", 1, -10L)), false)));

        // Math.addExact phải phát hiện tổng vượt phạm vi long.
        expectOverflow(() -> checkout.quote(new Order(List.of(
                new Item("A", 1, Long.MAX_VALUE),
                new Item("B", 1, 1L)), false)));
    }

    public static void main(String[] args) {
        Checkout legacy = new LegacyCheckout();
        Checkout refactored = new CheckoutService(
                new PricingPolicy(), new ReceiptFormatter());

        contractTests(legacy);
        contractTests(refactored);

        System.out.println(
                "PASS: same 5 business cases and 5 error cases in both versions");
    }
}
~~~

Chạy bằng terminal trong thư mục chứa file:

~~~bash
javac SafeRefactoringDemo.java
java SafeRefactoringDemo
~~~

Kết quả nếu các assertion đều đạt:

~~~text
PASS: same 4 business cases and 5 error cases in both versions
~~~

Chương trình có **5 kịch bản tính tiền và 5 kịch bản lỗi** cho mỗi implementation: 4 trường hợp dữ liệu sai và 1 trường hợp tràn số. Kỳ vọng được ghi trực tiếp trong test chứ không được lấy từ code cũ; nhờ vậy test không chỉ xác nhận hai phiên bản tương đương mà còn bảo vệ những quy tắc đã nêu.

Trong code này, Math.multiplyExact, Math.addExact và Math.subtractExact giúp lỗi tràn số được phát hiện rõ. Với tiền tệ có phần thập phân, hãy dùng kiểu biểu diễn phù hợp như BigDecimal và chính sách làm tròn được công bố; ví dụ cố tình dùng VND nguyên để đơn giản và nhất quán.

## 5. Trình tự cải thiện cụ thể

| Vòng | Thay đổi nhỏ | Điều nên kiểm tra ngay |
|---|---|---|
| 0 | Chạy lại code cũ với bộ test bảo vệ | Test pass ổn định, các case quan trọng có kỳ vọng xác định |
| 1 | Đặt tên rõ cho biến subtotal, discount, payable | Kết quả/exception không đổi |
| 2 | Tách calculateSubtotal từ phương thức lớn | Case dữ liệu sai, phép cộng tiền, overflow giữ nguyên |
| 3 | Tách calculateDiscount và calculateShipping | Các ngưỡng 500.000 và 700.000 giữ nguyên |
| 4 | Gom các method giá liên quan vào PricingPolicy | Không thay đổi giá trị và thứ tự lỗi đã cam kết |
| 5 | Tách ReceiptFormatter | Định dạng receipt không bị thay đổi ngoài ý muốn |
| 6 | Cho CheckoutService nhận dependency qua constructor | Caller vẫn nhận cùng Quote theo hợp đồng |
| 7 | Xóa implementation dư, tối giản tên/visibility | Chạy lại kiểm thử, review diff và integration nếu có |

~~~mermaid
flowchart TD
    A["Xác định hợp đồng và rủi ro"] --> B["Viết hoặc cập nhật test bảo vệ"]
    B --> C["Chọn một cải thiện thiết kế nhỏ"]
    C --> D["Biên dịch và chạy test"]
    D --> E{"Mọi test liên quan đều đạt?"}
    E -- "Không" --> F["Điều tra thay đổi hành vi hoặc test quá chặt"]
    F --> C
    E -- "Có" --> G["Review diff, đặt tên và trách nhiệm"]
    G --> H{"Còn cải thiện có ích?"}
    H -- "Có" --> C
    H -- "Không" --> I["Kết thúc refactor và kiểm thử tích hợp phù hợp"]
~~~

Chú ý: vòng kiểm thử có thể không bảo vệ mọi nhánh chưa được đưa vào test. Coverage giúp nhận biết chỗ chưa chạy, nhưng **100% line coverage không bảo đảm mọi assertion đúng hoặc tất cả quy tắc nghiệp vụ được kiểm tra**.

## 6. Cách thiết kế test để refactor không làm test vỡ vô lý

**Kiểm tra kết quả và hiệu ứng công khai.** Với lớp định giá, ưu tiên kiểm tra số tiền. Với lớp gửi biên nhận, kiểm tra rằng yêu cầu gửi đến đúng người, đúng nội dung, đúng thời điểm theo hợp đồng.

**Đặt tên test theo hành vi.** Ví dụ vipDiscountStartsAtThreshold hoặc failedPaymentDoesNotSendReceipt dễ hiểu hơn testCallsCalculateDiscountTwice.

**Không đóng băng thứ tự helper không liên quan.** Việc đổi từ for sang Stream hoặc thay HashMap bằng cấu trúc khác không nên làm test nghiệp vụ thất bại, nếu các kết quả và cam kết không thay đổi.

**Dùng test double đúng vai trò.** Fake repository giúp kiểm tra logic với dữ liệu trong bộ nhớ; stub điều khiển kết quả cổng thanh toán; mock phù hợp khi chính lời gọi bên ngoài là một phần yêu cầu. Chúng không thay thế hoàn toàn integration test với DB, queue hoặc API thật.

**Giữ test dễ đọc, độc lập, lặp lại được.** Tránh dùng đồng hồ hệ thống, randomness hoặc network thực cho unit test nếu các yếu tố ấy không phải mục tiêu. Có thể inject java.time.Clock, random generator và collaborator để kiểm soát input.

**Đừng chỉ so output của bản cũ với bản mới.** Nếu bản cũ chứa bug, cả hai có thể trả cùng kết quả sai. Kết hợp phép so sánh trước/sau với **expected values độc lập** lấy từ yêu cầu và ví dụ kiểm chứng.

## 7. Refactor có side effect cần cẩn thận hơn

Ví dụ tính giá ở trên gần như thuần chức năng. Nhưng nhiều phương thức ngoài thực tế còn mở transaction, ghi DB, gửi email hoặc gọi payment gateway.

Nếu trước đây thứ tự là:
1. Xác thực và kiểm tra tồn kho.
2. Thu tiền.
3. Ghi đơn hàng.
4. Yêu cầu gửi email xác nhận.

Việc tách method/class **không được vô tình** thay đổi quy tắc như "giao dịch thất bại thì không gửi email", hoặc đổi ranh giới transaction. Khi đó cần kiểm thử:
- Trạng thái lưu trữ và tính nhất quán sau thành công/thất bại.
- Những lời gọi ngoài hệ thống mà nghiệp vụ quy định phải xảy ra hoặc không xảy ra.
- Thứ tự thực sự mang ý nghĩa, idempotency và việc thử lại khi cần.
- Hợp đồng giữa application service với adapter thật qua integration test.

Ví dụ ý tưởng với Mockito + JUnit 5, giả định lớp CheckoutService và các interface này đã được định nghĩa trong một ứng dụng thực:

~~~java
when(gateway.charge(orderId, amountVnd)).thenReturn(false);

CheckoutResult result = checkoutService.checkout(orderId);

assertEquals(CheckoutResult.PAYMENT_DECLINED, result);
verifyNoInteractions(receiptSender);
~~~

Đây là **interaction verification có ý nghĩa** vì "không gửi biên nhận khi thanh toán lỗi" là hợp đồng. Nó khác với việc xác minh chính xác số lần private helper chạy trong code.

## 8. Sai lầm phổ biến khi cải thiện thiết kế

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Đổi công thức nghiệp vụ trong cùng bước tách lớp | Khó tách regression khỏi thay đổi tính năng | Chia thành hai thay đổi riêng, mỗi thay đổi có test |
| Di chuyển hàng trăm dòng một lần | Khó khoanh vùng lỗi | Thực hiện từng phép biến đổi nhỏ có kiểm chứng |
| Xóa test đỏ mà không điều tra | Có thể bỏ lỡ regression | Xác định test bảo vệ hợp đồng hay chỉ bám implementation |
| Chỉ đo line coverage | Dễ tưởng đã kiểm tra đủ | Thêm test biên, test lỗi, assertion cụ thể |
| Tạo quá nhiều class/method một dòng | Tăng phân mảnh và coupling | Tách theo trách nhiệm và lý do thay đổi thực tế |
| Biến private field thành public để refactor cho nhanh | Phá encapsulation | Truyền dữ liệu qua constructor, method, value object phù hợp |
| Thay đổi thứ tự validation | Thay đổi loại exception hoặc tác dụng phụ | Ghi nhận và kiểm tra thứ tự quan sát được nếu là hợp đồng |
| Tin rằng fake mô phỏng hoàn hảo DB | Thiếu phát hiện lỗi constraint, transaction, concurrency | Bổ sung integration test |
| Test phụ thuộc ngày hiện tại hoặc ID ngẫu nhiên | Test không ổn định | Inject Clock/ID generator, dùng giá trị cố định |

**Lưu ý về thứ tự và lỗi:** Nếu dữ liệu chứa hai lỗi khác nhau, đổi thứ tự validation có thể đổi exception xuất hiện đầu tiên. Điều này có thể là thay đổi quan sát được; hãy xác định yêu cầu trước khi kết luận việc đổi thứ tự là an toàn.

## 9. Cách tổ chức công việc khi refactor code thật

Với một phần hệ thống đang chạy, có thể thực hiện theo quy trình sau:

**Bước A — Khoanh phạm vi và lập baseline.** Chọn một trách nhiệm rõ ràng, kiểm tra caller, ghi nhận test hiện có và xác nhận hành vi cần giữ. Nếu code quá cũ, viết characterization tests dựa trên input/output hoặc side effect hiện tại. Xác nhận các test chạy ổn định trước khi sửa.

**Bước B — Phân tích điểm thay đổi.** Một lớp phình to vì validation, pricing, persistence và presentation thường có nhiều lý do thay đổi. Xác định đường dữ liệu, vòng đời đối tượng và ranh giới transaction. Chọn điểm tách nhỏ nhất có tác dụng làm code rõ hơn.

**Bước C — Thay đổi từng lần.** Rename biến, extract method, move method hoặc extract class. Thực hiện một phép biến đổi hoàn chỉnh, biên dịch/test, rồi mới tiếp tục. Dùng công cụ refactor của IDE khi thuận tiện, nhưng vẫn đọc diff vì IDE không thể xác nhận mọi quy tắc nghiệp vụ.

**Bước D — Tối ưu kiểm thử khi kiến trúc đã rõ.** Test theo hành vi công khai, không khóa quá chặt vào helper mới. Chia unit/integration test theo ranh giới chịu trách nhiệm. Không nhân bản toàn bộ bộ test chỉ để test từng class sau khi tách.

**Bước E — Kiểm chứng cuối.** Kiểm tra rằng không còn đường code cũ được sử dụng ngầm, public API không đổi ngoài chủ đích, test pass, và các tác dụng phụ đã được xác minh. Nếu cần thay đổi hành vi, lập một thay đổi riêng có test kỳ vọng mới.

Không cần chờ toàn bộ hệ thống "sạch" mới tiếp tục phát triển. Refactor hiệu quả là những **bước nhỏ, có mục đích, có chứng cứ** được thực hiện gần phần code đang cần thay đổi.

## 10. Bài thực hành

**Bài 1 — Bắt lỗi tại ngưỡng:** Trong PricingPolicy, đổi điều kiện miễn phí shipping từ lớn hơn hoặc bằng 700.000 thành lớn hơn 700.000. Viết thêm case khách thường subtotal bằng đúng 700.000; kỳ vọng shipping = 0. Test phải phát hiện lỗi.

**Bài 2 — Bắt lỗi giảm giá:** Đổi ngưỡng VIP từ lớn hơn hoặc bằng 500.000 thành lớn hơn 500.000. Case VIP subtotal 500.000 trong bộ test phải FAIL.

**Bài 3 — Extract Method:** Từ LegacyCheckout, tự tách validate, subtotal, discount, shipping, rồi chạy lại contractTests sau mỗi phép tách. Ghi lại việc các lỗi và kết quả giữ nguyên.

**Bài 4 — Extract Class:** Chuyển phần format receipt sang class riêng. Thử đổi riêng yêu cầu định dạng biên nhận và giải thích tại sao PricingPolicy không cần sửa. Đây là thay đổi tính năng riêng, không còn là refactor bảo toàn hành vi.

**Bài 5 — Characterization test cho lỗi cũ:** Giả sử hệ thống cũ tính sai phí của một trường hợp đặc biệt. Viết test tái hiện hành vi hiện tại để bảo vệ quá trình tách, sau đó viết test kỳ vọng mới cho bug fix và sửa ở bước riêng.

**Bài 6 — Ranh giới tích hợp:** Phác thảo fake PaymentGateway và mock ReceiptSender; chứng minh thanh toán bị từ chối thì không gửi biên nhận. Nêu thêm integration test cần có để biết adapter thanh toán thật xử lý mã lỗi đúng.

## 11. Tự kiểm tra kiến thức

1. Tại sao kiểm thử so sánh bản cũ với bản mới chưa đủ nếu bản cũ có bug?
2. Tại sao test về số lần gọi private helper có thể ngăn refactor đúng?
3. Khi nào thứ tự tương tác với collaborator là một phần hợp đồng?
4. Sau khi tách PricingPolicy và ReceiptFormatter, vì sao CheckoutService nên giữ vai trò điều phối?
5. Nếu một thay đổi khiến test đỏ, làm thế nào phân biệt lỗi nghiệp vụ với test quá phụ thuộc implementation?

**Điều cần ghi nhớ:** Kiểm thử bảo vệ giúp bạn cải thiện cấu trúc với phản hồi nhanh, nhưng chất lượng của hàng rào phụ thuộc vào **những hành vi nó thực sự xác minh**. Refactor từng bước nhỏ, giữ rõ ranh giới trách nhiệm OOP, kiểm tra ngay sau mỗi bước và bảo vệ cả trường hợp bình thường, ca biên, lỗi và side effect có ý nghĩa.