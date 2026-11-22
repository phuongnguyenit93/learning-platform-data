# Fake, stub, mock và đối tượng cộng tác trong kiểm thử OOP (Java)

## 1. Bối cảnh: vì sao cần đối tượng thay thế?

Một đối tượng trong OOP thường không làm việc một mình. Ví dụ **CheckoutService** xử lý đơn hàng bằng cách cộng tác với:
- **Inventory**: kiểm tra và trừ tồn kho.
- **PaymentGateway**: yêu cầu thanh toán.
- **ReceiptSender**: gửi biên nhận cho khách.

Ba thành phần này là **đối tượng cộng tác (collaborators)** của CheckoutService. Trong môi trường thật, chúng có thể dùng cơ sở dữ liệu, cổng thanh toán hoặc dịch vụ email. Nếu bài kiểm thử logic của CheckoutService trực tiếp gọi các dịch vụ đó, kết quả dễ phụ thuộc mạng, dữ liệu, phí giao dịch và cấu hình môi trường.

Một **test double** là đối tượng thay thế collaborator trong bài kiểm thử. Ta truyền nó vào đối tượng cần kiểm thử (**SUT — System Under Test**) thông qua constructor hoặc phương thức, nhờ đó có thể chủ động tạo tình huống và quan sát hành vi.

~~~mermaid
flowchart LR
    T["Bài kiểm thử"] --> S["CheckoutService (SUT)"]
    S --> I["Inventory interface"]
    S --> P["PaymentGateway interface"]
    S --> R["ReceiptSender interface"]
    I -. "trong test" .-> F["FakeInventory"]
    P -. "trong test" .-> ST["StubPaymentGateway"]
    R -. "trong test" .-> M["MockReceiptSender"]
~~~

Điểm mấu chốt: **collaborator** chỉ vai trò phụ thuộc trong thiết kế; **fake/stub/mock** chỉ cách đối tượng thay thế phục vụ mục đích kiểm thử. Một collaborator có thể được thay bằng đối tượng thật trong integration test, fake trong unit test hoặc mock khi cần kiểm tra tương tác.

## 2. Phân biệt fake, stub, mock, spy, dummy

| Loại | Đặc trưng | Dùng khi nào? | Ví dụ |
|---|---|---|---|
| **Dummy** | Chỉ truyền vào để thỏa tham số, bài test không dùng đến | Tham số bắt buộc nhưng không liên quan tình huống | Đối tượng Logger rỗng khi nhánh test không ghi log |
| **Stub** | Trả dữ liệu/kết quả đã lập trình trước cho lời gọi | Muốn chủ động điều khiển đầu vào gián tiếp của SUT | PaymentGateway luôn trả **true** hoặc **false** |
| **Fake** | Có logic hoạt động đơn giản nhưng thực sự dùng được, thường lưu trong bộ nhớ | Muốn kiểm tra trạng thái mà không dùng hạ tầng thật | Kho hàng Map trong RAM hỗ trợ đọc/trừ số lượng |
| **Mock** | Ghi nhận và/hoặc xác minh SUT đã gọi collaborator đúng cách | Cần khẳng định hiệu ứng bên ngoài đã được yêu cầu | Xác minh ReceiptSender được gọi đúng **một lần**, đúng người và số tiền |
| **Spy** | Quan sát lời gọi tới đối tượng thật hoặc đối tượng được bọc, có thể giữ hành vi thật | Muốn theo dõi tương tác mà vẫn chạy triển khai gốc | Spy bọc một repository in-memory và đếm lần gọi |

**Phân biệt theo mục đích, không theo tên class hay framework.** Chẳng hạn đối tượng tạo bằng Mockito.mock(...) có thể vừa trả giá trị đã cấu hình (**stubbing**), vừa được kiểm tra bằng verify(...) (**mock-style verification**). Một fake cũng có thể ghi lịch sử gọi và đảm nhiệm vai trò spy. Trong thuật ngữ kinh điển, **stub giúp định hình trạng thái/đầu ra**, còn **mock giúp khẳng định tương tác mong đợi**.

Hai cách khẳng định kết quả thường gặp:
- **State verification:** sau khi checkout thành công, tồn kho từ 3 còn 1.
- **Interaction verification:** biên nhận được yêu cầu gửi chính xác một lần với orderId, email và tổng tiền đúng.

Không phải test nào cũng cần mock. Kiểm tra kết quả hoặc trạng thái quan sát được thường ít gắn với chi tiết cài đặt hơn kiểm tra mọi lời gọi nội bộ.

## 3. Ví dụ Java hoàn chỉnh, chạy không cần thư viện kiểm thử

Ví dụ sau dùng Java 11 trở lên, một file duy nhất **CheckoutDemo.java**. Các interface mô tả hợp đồng collaborator; CheckoutService chỉ biết interface. Ba test double minh họa ba mục tiêu riêng: fake lưu kho trong RAM, stub quyết định thanh toán, mock ghi nhận yêu cầu gửi biên nhận.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class CheckoutDemo {
    // Hợp đồng của các collaborator
    interface Inventory {
        int available(String sku);
        void decrease(String sku, int quantity);
    }

    interface PaymentGateway {
        boolean charge(String orderId, long amountVnd);
    }

    interface ReceiptSender {
        void send(String email, String orderId, long amountVnd);
    }

    enum Result {
        SUCCESS, OUT_OF_STOCK, PAYMENT_DECLINED
    }

    // SUT: code nghiệp vụ, không biết test double đang được dùng
    static final class CheckoutService {
        private final Inventory inventory;
        private final PaymentGateway payments;
        private final ReceiptSender receipts;

        CheckoutService(Inventory inventory,
                        PaymentGateway payments,
                        ReceiptSender receipts) {
            this.inventory = Objects.requireNonNull(inventory);
            this.payments = Objects.requireNonNull(payments);
            this.receipts = Objects.requireNonNull(receipts);
        }

        Result checkout(String orderId, String sku, int quantity,
                        long unitPriceVnd, String email) {
            if (orderId == null || orderId.isBlank()
                    || sku == null || sku.isBlank()
                    || email == null || email.isBlank()
                    || quantity <= 0 || unitPriceVnd <= 0) {
                throw new IllegalArgumentException("Invalid checkout data");
            }

            if (inventory.available(sku) < quantity) {
                return Result.OUT_OF_STOCK;
            }

            long total = Math.multiplyExact(unitPriceVnd, (long) quantity);
            if (!payments.charge(orderId, total)) {
                return Result.PAYMENT_DECLINED;
            }

            inventory.decrease(sku, quantity);
            receipts.send(email, orderId, total);
            return Result.SUCCESS;
        }
    }

    // FAKE: có trạng thái và hành vi đọc/trừ tồn kho thực tế trong RAM
    static final class FakeInventory implements Inventory {
        private final Map<String, Integer> stock = new HashMap<>();

        void put(String sku, int quantity) {
            if (quantity < 0) {
                throw new IllegalArgumentException("Negative stock");
            }
            stock.put(sku, quantity);
        }

        @Override
        public int available(String sku) {
            return stock.getOrDefault(sku, 0);
        }

        @Override
        public void decrease(String sku, int quantity) {
            if (quantity <= 0 || available(sku) < quantity) {
                throw new IllegalStateException("Insufficient stock");
            }
            stock.put(sku, available(sku) - quantity);
        }
    }

    // STUB: điều khiển trước kết quả của cổng thanh toán
    static final class StubPaymentGateway implements PaymentGateway {
        private final boolean approved;

        StubPaymentGateway(boolean approved) {
            this.approved = approved;
        }

        @Override
        public boolean charge(String orderId, long amountVnd) {
            return approved;
        }
    }

    // MOCK thủ công: ghi nhận tương tác và cung cấp phương thức verify
    static final class MockReceiptSender implements ReceiptSender {
        private static final class Call {
            final String email;
            final String orderId;
            final long amountVnd;

            Call(String email, String orderId, long amountVnd) {
                this.email = email;
                this.orderId = orderId;
                this.amountVnd = amountVnd;
            }
        }

        private final List<Call> calls = new ArrayList<>();

        @Override
        public void send(String email, String orderId, long amountVnd) {
            calls.add(new Call(email, orderId, amountVnd));
        }

        void verifySentExactlyOnce(String email, String orderId,
                                   long amountVnd) {
            check(calls.size() == 1,
                    "Expected one receipt, got " + calls.size());

            Call actual = calls.get(0);
            check(Objects.equals(actual.email, email),
                    "Wrong receipt email");
            check(Objects.equals(actual.orderId, orderId),
                    "Wrong receipt orderId");
            check(actual.amountVnd == amountVnd,
                    "Wrong receipt amount");
        }

        void verifyNoCalls() {
            check(calls.isEmpty(), "No receipt should be sent");
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void successfulCheckout() {
        FakeInventory inventory = new FakeInventory();
        inventory.put("BOOK", 3);
        StubPaymentGateway payments = new StubPaymentGateway(true);
        MockReceiptSender receipts = new MockReceiptSender();

        CheckoutService service =
                new CheckoutService(inventory, payments, receipts);
        Result actual = service.checkout(
                "ORD-01", "BOOK", 2, 250_000L, "buyer@example.test");

        check(actual == Result.SUCCESS, "Checkout should succeed");
        check(inventory.available("BOOK") == 1,
                "Inventory should decrease from 3 to 1"); // state
        receipts.verifySentExactlyOnce(
                "buyer@example.test", "ORD-01", 500_000L); // interaction
    }

    private static void declinedPayment() {
        FakeInventory inventory = new FakeInventory();
        inventory.put("BOOK", 3);
        StubPaymentGateway payments = new StubPaymentGateway(false);
        MockReceiptSender receipts = new MockReceiptSender();

        CheckoutService service =
                new CheckoutService(inventory, payments, receipts);
        Result actual = service.checkout(
                "ORD-02", "BOOK", 2, 250_000L, "buyer@example.test");

        check(actual == Result.PAYMENT_DECLINED,
                "Payment should be declined");
        check(inventory.available("BOOK") == 3,
                "Declined payment must not reduce inventory");
        receipts.verifyNoCalls();
    }

    private static void insufficientStock() {
        FakeInventory inventory = new FakeInventory();
        inventory.put("BOOK", 1);
        StubPaymentGateway payments = new StubPaymentGateway(true);
        MockReceiptSender receipts = new MockReceiptSender();

        CheckoutService service =
                new CheckoutService(inventory, payments, receipts);
        Result actual = service.checkout(
                "ORD-03", "BOOK", 2, 250_000L, "buyer@example.test");

        check(actual == Result.OUT_OF_STOCK,
                "Insufficient stock should block checkout");
        check(inventory.available("BOOK") == 1,
                "Stock must remain unchanged");
        receipts.verifyNoCalls();
    }

    public static void main(String[] args) {
        successfulCheckout();
        declinedPayment();
        insufficientStock();
        System.out.println("3 scenarios PASS");
    }
}
~~~

Chạy tại thư mục chứa file:

~~~bash
javac CheckoutDemo.java
java CheckoutDemo
~~~

Kết quả khi cả ba tình huống đạt yêu cầu:

~~~text
3 scenarios PASS
~~~

Chỉ cần sửa sai một điều kiện, ví dụ gửi email trước khi thanh toán được chấp thuận, bài test **declinedPayment** sẽ ném AssertionError. Không có email thật, giao dịch thật hay database thật nào được gọi.

### Điều đang được kiểm chứng

| Tình huống | Stub thanh toán | Trạng thái fake sau gọi | Mock gửi biên nhận | Kết quả |
|---|---|---|---|---|
| Còn 3 sản phẩm, mua 2 | Chấp thuận | Còn 1 | Đúng 1 lần, 500.000 VND | SUCCESS |
| Còn 3 sản phẩm, mua 2 | Từ chối | Vẫn 3 | Không gọi | PAYMENT_DECLINED |
| Chỉ còn 1, mua 2 | Không quyết định kết quả | Vẫn 1 | Không gọi | OUT_OF_STOCK |

Ở tình huống hết hàng, checkout trả về trước khi yêu cầu thanh toán; bài test hiện tại chỉ kiểm tra trạng thái kho và email. Nếu yêu cầu nghiệp vụ cần **chứng minh gateway tuyệt đối không được gọi**, hãy dùng một test double ghi số lần gọi hoặc Mockito.verifyNoInteractions(...), rồi xác minh riêng điều đó.

## 4. Cùng ý tưởng với JUnit 5 và Mockito

Khi dự án đã dùng **JUnit Jupiter** và **Mockito**, không nhất thiết phải tự viết MockReceiptSender. Ví dụ dưới đây giả định class CheckoutDemo ở phần trên có mặt trong cùng package và project đã khai báo dependency test của JUnit Jupiter + Mockito.

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class CheckoutServiceTest {
    @Test
    void successfulCheckoutReducesStockAndSendsReceipt() {
        CheckoutDemo.Inventory inventory =
                mock(CheckoutDemo.Inventory.class);
        CheckoutDemo.PaymentGateway gateway =
                mock(CheckoutDemo.PaymentGateway.class);
        CheckoutDemo.ReceiptSender sender =
                mock(CheckoutDemo.ReceiptSender.class);

        // STUBBING: thiết lập kết quả collaborator trả về
        when(inventory.available("BOOK")).thenReturn(3);
        when(gateway.charge("ORD-01", 500_000L)).thenReturn(true);

        var service = new CheckoutDemo.CheckoutService(
                inventory, gateway, sender);

        var result = service.checkout(
                "ORD-01", "BOOK", 2, 250_000L, "buyer@example.test");

        // Kiểm tra giá trị trả về của SUT
        assertEquals(CheckoutDemo.Result.SUCCESS, result);

        // MOCK-STYLE VERIFICATION: xác minh hiệu ứng cộng tác
        verify(inventory).decrease("BOOK", 2);
        verify(gateway).charge("ORD-01", 500_000L);
        verify(sender, times(1)).send(
                "buyer@example.test", "ORD-01", 500_000L);
        verifyNoMoreInteractions(sender);
    }

    @Test
    void outOfStockDoesNotChargeOrSendReceipt() {
        CheckoutDemo.Inventory inventory =
                mock(CheckoutDemo.Inventory.class);
        CheckoutDemo.PaymentGateway gateway =
                mock(CheckoutDemo.PaymentGateway.class);
        CheckoutDemo.ReceiptSender sender =
                mock(CheckoutDemo.ReceiptSender.class);

        when(inventory.available("BOOK")).thenReturn(1);

        var service = new CheckoutDemo.CheckoutService(
                inventory, gateway, sender);

        var result = service.checkout(
                "ORD-03", "BOOK", 2, 250_000L, "buyer@example.test");

        assertEquals(CheckoutDemo.Result.OUT_OF_STOCK, result);
        verify(inventory, never()).decrease(anyString(), anyInt());
        verifyNoInteractions(gateway, sender);
    }
}
~~~

Chú ý: **verify(inventory).decrease(...) không chứng minh dữ liệu trong kho đã thực sự thay đổi**, vì Mockito mock mặc định không lưu trạng thái của Inventory. Muốn kiểm chứng số lượng thực còn lại, dùng FakeInventory hoặc bài integration test với repository thật. Đây là điểm khác nhau quan trọng giữa **tương tác** và **kết quả quan sát được**.

Các thao tác phổ biến trong Mockito:
- **when(...).thenReturn(...)**: định nghĩa đầu ra của stub.
- **verify(mock).method(...)**: xác minh có lời gọi phù hợp, mặc định đúng 1 lần.
- **times(n)**, **never()**, **verifyNoInteractions(...)**: kiểm tra số lần/không gọi.
- **ArgumentCaptor**: bắt tham số để kiểm tra nội dung khi cần.
- **spy(realObject)**: quan sát đối tượng có hành vi thật; cân nhắc tác dụng phụ và không mặc định coi spy an toàn.

## 5. Thiết kế đối tượng cộng tác để dễ kiểm thử

### Phụ thuộc vào hợp đồng, đưa dependency từ bên ngoài vào

~~~java
// Khó cô lập: tự tạo phụ thuộc trong hàm nghiệp vụ
// PaymentGateway gateway = new RealPaymentGateway(...);

// Dễ kiểm thử: nhận đối tượng thực thi interface từ constructor
CheckoutDemo.CheckoutService service =
        new CheckoutDemo.CheckoutService(inventory, gateway, sender);
~~~

Đây là **dependency injection** kết hợp **programming to an interface**. Mục đích không phải tạo interface cho mọi class, mà là tách những ranh giới có hành vi cần hoán đổi hoặc kiểm soát: dữ liệu, thời gian, mạng, hàng đợi thông điệp và dịch vụ bên ngoài.

### Nên kiểm thử điều gì?

1. **Quy tắc nghiệp vụ:** kết quả trả về, tồn kho, số tiền, tính hợp lệ của dữ liệu.
2. **Tương tác mang ý nghĩa nghiệp vụ:** khi thanh toán thành công, yêu cầu gửi biên nhận đúng thông tin; khi thất bại không gửi.
3. **Đường lỗi:** hết hàng, từ chối thanh toán, dữ liệu sai, lỗi ngoại vi.
4. **Hợp đồng giữa các thành phần:** fake có tuân thủ giả định của repository thật? Chữ ký phương thức và trường hợp lỗi có nhất quán?

Không nên xác minh mọi lời gọi getter, thứ tự các bước nội bộ hay cấu trúc private chỉ vì Mockito cho phép. Nếu refactor giữ nguyên hành vi mà hàng loạt unit test vô cớ thất bại, nhiều khả năng test đã phụ thuộc quá sâu vào implementation.

## 6. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách làm phù hợp |
|---|---|---|
| Dùng mock cho mọi object, kể cả value object thuần | Test dài, khó đọc, giòn khi refactor | Dùng object thật cho DTO/value object đơn giản |
| Stub trả kết quả mặc định nhưng quên nhánh lỗi | Thiếu coverage cho từ chối, timeout, hết hàng | Viết test riêng cho nhánh lỗi quan trọng |
| Chỉ verify lời gọi repository rồi kết luận trạng thái đã lưu đúng | Nhầm interaction với state | Dùng fake có lưu trạng thái hoặc integration test |
| Fake không giống ràng buộc của storage thật | Unit test xanh nhưng production lỗi | Contract/integration test các quy tắc: trùng khóa, transaction, concurrency |
| Mock chi tiết nội bộ như số lần gọi từng helper | Test gắn chặt cách triển khai | Verify đầu ra và hiệu ứng ngoài hệ thống |
| Dùng spy cho dịch vụ thật có side effect | Có thể thực thi thanh toán, gửi mail, ghi DB ngoài ý muốn | Chỉ spy đối tượng an toàn, không có side effect bất ngờ |
| Dùng unit test double thay cho toàn bộ kiểm thử tích hợp | Không phát hiện lỗi cấu hình, mạng, schema, giao thức | Bổ sung integration test cho adapter và luồng quan trọng |

**Giới hạn cố ý của ví dụ:** CheckoutService minh họa logic tuần tự. Hệ thống thật phải xử lý tính nguyên tử giữa thanh toán, tồn kho và gửi biên nhận (transaction, idempotency, outbox/saga, retry), đồng thời kiểm tra tranh chấp tồn kho khi có nhiều yêu cầu. FakeInventory trong RAM không tự mô phỏng những tính chất đó. Test double giúp cô lập trách nhiệm của SUT, không thay thế kiểm thử tích hợp/end-to-end.

## 7. Bài luyện tập

- Bổ sung tình huống **quantity = 0**: kỳ vọng IllegalArgumentException, không có biên nhận; cân nhắc cách chứng minh không gọi cổng thanh toán.
- Tạo **SpyPaymentGateway** bọc một StubPaymentGateway, đếm số lần charge và lưu orderId/amountVnd. Xác minh tình huống OUT_OF_STOCK có **0 lần charge**.
- Cố tình thay **inventory.decrease(sku, quantity)** bằng trừ 1 và kiểm tra test thành công phát hiện lỗi qua state verification.
- Bổ sung một bài integration test của Inventory thật (nếu dự án có database) để so sánh hợp đồng với FakeInventory.

**Ghi nhớ:** Fake trả lời “trạng thái thay đổi thế nào?”, Stub trả lời “collaborator sẽ trả gì?”, Mock trả lời “collaborator đã được gọi ra sao?”. Chọn test double theo điều thực sự cần chứng minh, giữ SUT phụ thuộc vào hợp đồng rõ ràng, và dùng integration test để xác nhận phần mà đối tượng thay thế không mô phỏng.