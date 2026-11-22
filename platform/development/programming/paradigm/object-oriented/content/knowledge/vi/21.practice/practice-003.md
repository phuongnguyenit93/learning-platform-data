# Bài tập giao diện và đa hình thanh toán trong Java OOP

## Mục tiêu

Xây dựng chức năng thanh toán cho cửa hàng với ba lựa chọn: **thẻ**, **chuyển khoản** và **ví điện tử**. Mỗi cách có quy tắc riêng nhưng bộ xử lý đơn hàng không cần biết chi tiết của từng loại.

Qua bài này, bạn luyện tập được:

- **Interface:** định nghĩa hợp đồng chung PaymentMethod.
- **Đa hình lúc chạy:** gọi cùng phương thức pay trên những đối tượng có kiểu thực tế khác nhau.
- **Đóng gói:** trạng thái của thẻ, ngân hàng, ví được quản lý bên trong từng lớp.
- **Composition và constructor injection:** PaymentProcessor nhận một PaymentMethod từ bên ngoài.
- **Kiểm thử:** xác minh phí, số tiền thanh toán, giao dịch bị từ chối và trạng thái số dư.

Đây là **bài mô phỏng** hoàn toàn trong bộ nhớ, không thực hiện giao dịch tài chính thật, không dùng thông tin thẻ thật và không kết nối ngân hàng.

## 1. Yêu cầu bài tập

Mỗi giao dịch có mã đơn hàng không rỗng và số tiền nguyên dương, tính bằng VND. Các mức phí chỉ là quy ước của bài tập.

| Phương thức | Điều kiện thành công | Phí | Tình huống từ chối |
|---|---|---|---|
| CardPayment | Thẻ hoạt động, tiền không vượt hạn mức mỗi giao dịch | 2% số tiền, làm tròn xuống VND | Thẻ khóa hoặc vượt hạn mức |
| BankTransferPayment | Tiền không vượt hạn mức mỗi giao dịch | 5.000 VND | Vượt hạn mức |
| EWalletPayment | Số dư ví ít nhất bằng tiền đơn hàng | 0 VND | Ví thiếu tiền |

Một PaymentResult gồm mã đơn hàng, tên phương thức, trạng thái SUCCESS/DECLINED, số tiền gốc, phí, số tiền đã trả và thông báo.

**Bất biến cần bảo vệ:**

1. Giao dịch bị từ chối không được ghi nhận là thành công; phí và tổng đã trả bằng 0.
2. Ví chỉ giảm số dư khi thanh toán thành công, đúng số tiền đã trả.
3. Dữ liệu đầu vào sai được phát hiện trước khi thực hiện hành vi thanh toán.
4. PaymentProcessor không dùng if, switch, instanceof để phân biệt ba lớp thanh toán.

## 2. Phân rã đối tượng

~~~mermaid
classDiagram
    class PaymentMethod {
        <<interface>>
        +label() String
        +pay(request) PaymentResult
    }
    class CardPayment {
        -active boolean
        -limit long
        +pay(request) PaymentResult
    }
    class BankTransferPayment {
        -bankName String
        -limit long
        +pay(request) PaymentResult
    }
    class EWalletPayment {
        -balance long
        +pay(request) PaymentResult
        +balanceVnd() long
    }
    class PaymentProcessor {
        -method PaymentMethod
        +process(request) PaymentResult
    }
    PaymentMethod <|.. CardPayment
    PaymentMethod <|.. BankTransferPayment
    PaymentMethod <|.. EWalletPayment
    PaymentProcessor --> PaymentMethod
~~~

**PaymentMethod** mô tả hành vi chung, không buộc các lớp triển khai phải có những field giống nhau. PaymentProcessor điều phối lời gọi; mỗi implementation tự quyết định điều kiện phê duyệt, tính phí và thay đổi trạng thái.

## 3. Lời giải Java 11 hoàn chỉnh

Tạo file **PaymentPolymorphismDemo.java**. Chương trình tự chạy bằng JDK 11 trở lên, không cần Spring, Maven hay thư viện bên ngoài.

~~~java
import java.util.List;
import java.util.Objects;

public class PaymentPolymorphismDemo {
    enum Status {
        SUCCESS, DECLINED
    }

    static final class PaymentRequest {
        final String orderId;
        final long amountVnd;

        PaymentRequest(String orderId, long amountVnd) {
            if (orderId == null || orderId.isBlank()
                    || amountVnd <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            this.orderId = orderId;
            this.amountVnd = amountVnd;
        }
    }

    static final class PaymentResult {
        final String orderId;
        final String method;
        final Status status;
        final long originalAmountVnd;
        final long feeVnd;
        final long totalPaidVnd;
        final String message;

        private PaymentResult(String orderId, String method,
                Status status, long originalAmountVnd, long feeVnd,
                long totalPaidVnd, String message) {
            this.orderId = orderId;
            this.method = method;
            this.status = status;
            this.originalAmountVnd = originalAmountVnd;
            this.feeVnd = feeVnd;
            this.totalPaidVnd = totalPaidVnd;
            this.message = message;
        }

        static PaymentResult success(
                PaymentRequest request, String method, long fee) {
            if (fee < 0) {
                throw new IllegalArgumentException("Negative fee");
            }
            long total = Math.addExact(request.amountVnd, fee);
            return new PaymentResult(
                    request.orderId, method, Status.SUCCESS,
                    request.amountVnd, fee, total, "Approved");
        }

        static PaymentResult declined(
                PaymentRequest request, String method, String reason) {
            return new PaymentResult(
                    request.orderId, method, Status.DECLINED,
                    request.amountVnd, 0L, 0L, reason);
        }

        @Override
        public String toString() {
            return orderId + " | " + method + " | " + status
                    + " | fee=" + feeVnd
                    + " | paid=" + totalPaidVnd
                    + " | " + message;
        }
    }

    // Hợp đồng chung để thay thế đa hình.
    interface PaymentMethod {
        String label();
        PaymentResult pay(PaymentRequest request);
    }

    // Trả 2% làm tròn xuống; tránh nhân trực tiếp số lớn * 2.
    private static long cardFee(long amount) {
        long base = Math.multiplyExact(amount / 100L, 2L);
        long fraction = (amount % 100L) * 2L / 100L;
        return Math.addExact(base, fraction);
    }

    static final class CardPayment implements PaymentMethod {
        private final boolean active;
        private final long limit;

        CardPayment(boolean active, long limit) {
            if (limit <= 0) {
                throw new IllegalArgumentException("Invalid card limit");
            }
            this.active = active;
            this.limit = limit;
        }

        @Override
        public String label() {
            return "CARD";
        }

        @Override
        public PaymentResult pay(PaymentRequest request) {
            Objects.requireNonNull(request, "request");
            if (!active) {
                return PaymentResult.declined(
                        request, label(), "Inactive card");
            }
            if (request.amountVnd > limit) {
                return PaymentResult.declined(
                        request, label(), "Card limit exceeded");
            }
            return PaymentResult.success(
                    request, label(), cardFee(request.amountVnd));
        }
    }

    static final class BankTransferPayment implements PaymentMethod {
        private final String bankName;
        private final long limit;

        BankTransferPayment(String bankName, long limit) {
            if (bankName == null || bankName.isBlank() || limit <= 0) {
                throw new IllegalArgumentException("Invalid bank");
            }
            this.bankName = bankName;
            this.limit = limit;
        }

        @Override
        public String label() {
            return "BANK(" + bankName + ")";
        }

        @Override
        public PaymentResult pay(PaymentRequest request) {
            Objects.requireNonNull(request, "request");
            if (request.amountVnd > limit) {
                return PaymentResult.declined(
                        request, label(), "Transfer limit exceeded");
            }
            return PaymentResult.success(request, label(), 5_000L);
        }
    }

    static final class EWalletPayment implements PaymentMethod {
        private long balance;

        EWalletPayment(long initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Negative balance");
            }
            this.balance = initialBalance;
        }

        long balanceVnd() {
            return balance;
        }

        @Override
        public String label() {
            return "E_WALLET";
        }

        @Override
        public PaymentResult pay(PaymentRequest request) {
            Objects.requireNonNull(request, "request");
            if (balance < request.amountVnd) {
                return PaymentResult.declined(
                        request, label(), "Insufficient balance");
            }
            // Chỉ thay đổi trạng thái sau khi kết quả hợp lệ.
            PaymentResult result =
                    PaymentResult.success(request, label(), 0L);
            balance -= request.amountVnd;
            return result;
        }
    }

    // Không kiểm tra kiểu cụ thể: dynamic dispatch ở method.pay.
    static final class PaymentProcessor {
        private final PaymentMethod method;

        PaymentProcessor(PaymentMethod method) {
            this.method = Objects.requireNonNull(method, "method");
        }

        PaymentResult process(PaymentRequest request) {
            Objects.requireNonNull(request, "request");
            return method.pay(request);
        }
    }

    private static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    private static void expectSuccess(PaymentResult result,
                                      long fee, long paid) {
        check(result.status == Status.SUCCESS, "Must succeed");
        check(result.feeVnd == fee, "Wrong fee");
        check(result.totalPaidVnd == paid, "Wrong total");
    }

    private static void expectDeclined(PaymentResult result) {
        check(result.status == Status.DECLINED, "Must decline");
        check(result.feeVnd == 0L, "Declined fee must be zero");
        check(result.totalPaidVnd == 0L,
                "Declined paid amount must be zero");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected invalid argument");
    }

    public static void main(String[] args) {
        PaymentRequest order =
                new PaymentRequest("ORD-101", 200_000L);

        CardPayment card = new CardPayment(true, 500_000L);
        BankTransferPayment bank =
                new BankTransferPayment("ABC", 1_000_000L);
        EWalletPayment wallet = new EWalletPayment(250_000L);

        // Một kiểu interface, nhiều implementation thực tế.
        List<PaymentMethod> methods = List.of(card, bank, wallet);
        long[] fees = {4_000L, 5_000L, 0L};
        long[] totals = {204_000L, 205_000L, 200_000L};

        for (int i = 0; i < methods.size(); i++) {
            PaymentProcessor processor =
                    new PaymentProcessor(methods.get(i));
            PaymentResult result = processor.process(order);
            expectSuccess(result, fees[i], totals[i]);
            check(result.orderId.equals("ORD-101"), "Wrong order ID");
            check(result.originalAmountVnd == 200_000L,
                    "Wrong original amount");
            System.out.println(result);
        }

        // Đã chi 200.000 từ số dư 250.000.
        check(wallet.balanceVnd() == 50_000L, "Wrong balance");

        // Yêu cầu thêm 60.000 bị từ chối, không được trừ ví.
        PaymentResult rejected = new PaymentProcessor(wallet)
                .process(new PaymentRequest("ORD-102", 60_000L));
        expectDeclined(rejected);
        check(wallet.balanceVnd() == 50_000L,
                "Rejected transaction changed wallet balance");

        // Thẻ không hoạt động và chuyển khoản vượt hạn mức.
        expectDeclined(new PaymentProcessor(
                new CardPayment(false, 500_000L)).process(order));
        expectDeclined(new PaymentProcessor(
                new BankTransferPayment("ABC", 100_000L))
                .process(order));

        // Không được tạo đơn không hợp lệ.
        expectInvalid(() -> new PaymentRequest(" ", 10_000L));
        expectInvalid(() -> new PaymentRequest("ORD-103", 0L));
        expectInvalid(() -> new PaymentRequest(null, 1L));

        System.out.println("All payment polymorphism tests: PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PaymentPolymorphismDemo.java
java PaymentPolymorphismDemo
~~~

Đầu ra khi mọi điều kiện đạt:

~~~text
ORD-101 | CARD | SUCCESS | fee=4000 | paid=204000 | Approved
ORD-101 | BANK(ABC) | SUCCESS | fee=5000 | paid=205000 | Approved
ORD-101 | E_WALLET | SUCCESS | fee=0 | paid=200000 | Approved
All payment polymorphism tests: PASS
~~~

Bộ test sử dụng AssertionError trực tiếp nên không phụ thuộc tùy chọn bật Java assert. Trong dự án thực tế, có thể chuyển các ca kiểm thử sang JUnit 5.

## 4. Giải thích cơ chế đa hình

Xét hai đoạn:

~~~java
PaymentMethod method = new CardPayment(true, 500_000L);
PaymentResult a = new PaymentProcessor(method)
        .process(new PaymentRequest("A", 100_000L));

method = new EWalletPayment(300_000L);
PaymentResult b = new PaymentProcessor(method)
        .process(new PaymentRequest("B", 100_000L));
~~~

Kiểu **khai báo** của biến method là PaymentMethod. Nhưng đối tượng mà nó trỏ tới là CardPayment hoặc EWalletPayment. Khi PaymentProcessor gọi method.pay(request), JVM thực thi phiên bản đã override trong lớp của đối tượng thực tế. Đó là **runtime polymorphism**.

Không phải mọi implementation đều cần giống nhau bên trong. Thẻ kiểm tra active/limit, chuyển khoản kiểm tra limit, ví kiểm tra và thay đổi balance. Interface chỉ yêu cầu **một hợp đồng hành vi chung**, không ép chúng dùng chung field hoặc công thức.

Constructor injection làm PaymentProcessor phụ thuộc vào hợp đồng. Khi bổ sung một phương thức thanh toán mới, logic process không phải thay đổi.

## 5. Kiến trúc trước và sau

Trước khi áp dụng đa hình, người mới học dễ viết một phương thức chứa toàn bộ nhánh:

~~~java
// Minh họa anti-pattern, không phải đoạn chạy độc lập:
if (type.equals("CARD")) {
    // Kiểm tra hạn mức, tính 2%.
} else if (type.equals("BANK")) {
    // Kiểm tra hạn mức, cộng 5.000.
} else if (type.equals("WALLET")) {
    // Kiểm tra số dư, trừ tiền.
}
~~~

Nếu code xử lý hoàn tiền hoặc lịch sử giao dịch cũng lặp lại các nhánh, việc bổ sung loại mới càng dễ bỏ sót. Sau khi tách, PaymentProcessor chỉ gọi:

~~~java
PaymentResult process(PaymentRequest request) {
    return method.pay(request);
}
~~~

~~~mermaid
sequenceDiagram
    participant Caller
    participant Processor as PaymentProcessor
    participant Method as PaymentMethod
    Caller->>Processor: process(request)
    Processor->>Method: pay(request)
    Note over Method: Runtime dispatch theo lớp thực tế
    Method-->>Processor: PaymentResult
    Processor-->>Caller: PaymentResult
~~~

Hệ thống vẫn có thể dùng factory hoặc registry để chuyển lựa chọn từ API (chẳng hạn mã CARD) thành đối tượng cụ thể. Bước **chọn implementation ở ranh giới tạo đối tượng** khác với việc nhét các nhánh tính phí và thay đổi trạng thái vào mọi nơi gọi thanh toán.

## 6. Các test tối thiểu và mở rộng

| Trường hợp | Kỳ vọng |
|---|---|
| Thẻ active, hạn mức 500.000, đơn 200.000 | SUCCESS, phí 4.000, tổng 204.000 |
| Thẻ inactive | DECLINED, không ghi nhận tiền đã trả |
| Thẻ vượt hạn mức | DECLINED |
| Ngân hàng hạn mức 1.000.000, đơn 200.000 | SUCCESS, phí 5.000 |
| Ngân hàng hạn mức 100.000, đơn 200.000 | DECLINED |
| Ví 250.000 trả 200.000 | SUCCESS, còn 50.000 |
| Ví còn 50.000 trả thêm 60.000 | DECLINED, vẫn còn 50.000 |
| Mã đơn hàng rỗng, amount bằng 0 hoặc âm | IllegalArgumentException |
| Thẻ trả 199 VND | Phí là 3 VND (2% làm tròn xuống) |
| Giao dịch vượt miền long khi cộng phí | Phát sinh ArithmeticException, không báo thành công |

Chương trình mẫu chạy những ca chính; hai ca cuối là bài tập tăng cường. Math.addExact và công thức cardFee đã chuẩn bị để bạn kiểm tra tràn số và làm tròn một cách tường minh.

## 7. Bài tập thực hành

**Phần A — Tự cài đặt:** Chỉ dựa trên đề bài và sơ đồ, hãy tự viết PaymentMethod, ba implementation, PaymentProcessor và PaymentResult. So sánh hành vi với phần lời giải.

**Phần B — Thêm QRPayment:** Giả định QR tính phí 1% và giới hạn 2.000.000 VND mỗi lần. Tạo lớp triển khai PaymentMethod, đưa nó vào danh sách và bổ sung test; không sửa code PaymentProcessor.

**Phần C — Chính sách phí:** Nếu cùng một loại thanh toán có biểu phí khác nhau theo chương trình khuyến mãi, thử đưa FeePolicy thành một collaborator. Giải thích khi nào nên tách trách nhiệm này khỏi PaymentMethod.

**Phần D — Bảo vệ trạng thái:** Với ví có số dư 100.000 VND, thử thanh toán 100.000 rồi thử thêm 1 VND. Giao dịch đầu thành công, giao dịch sau bị từ chối, số dư cuối bằng 0.

**Phần E — Kiểm tra lỗi:** Bổ sung ca thẻ hạn mức bằng đúng số tiền; tên ngân hàng rỗng; số dư khởi tạo âm; thẻ có giới hạn âm; dữ liệu PaymentRequest null.

## 8. Những lỗi thiết kế cần tránh

- **Dùng instanceof trong processor:** làm mất lợi ích đa hình vì processor lại phụ thuộc từng lớp cụ thể.
- **Nhét switch vào một lớp tiện ích:** chỉ di chuyển điều kiện, chưa phân phối trách nhiệm cho các đối tượng.
- **Trừ ví trước khi biết thanh toán thành công:** có nguy cơ thay đổi trạng thái sai khi từ chối hoặc phát sinh ngoại lệ.
- **Dùng double cho tiền:** tránh sai số dấu phẩy động. Bài này dùng long VND nguyên và Math.addExact; với đơn vị có phần thập phân hãy cân nhắc BigDecimal.
- **Chỉ trả boolean:** không đủ giải thích trạng thái, phí và lý do thất bại nếu ứng dụng cần những thông tin đó.
- **Cho rằng interface tự bảo đảm an toàn thanh toán:** thiết kế này chưa có database transaction, idempotency, bảo mật dữ liệu nhạy cảm, đối soát hoặc xử lý webhook. Đó là những mối quan tâm riêng trong hệ thống thật.
- **Tạo interface cho mọi class:** chỉ trừu tượng hóa khi có hợp đồng chung có ý nghĩa. PaymentRequest/PaymentResult là đối tượng dữ liệu, không cần nhiều implementation chỉ để chứng minh đa hình.

## 9. Tự đánh giá

1. Vì sao cùng một biến PaymentMethod có thể gọi những thuật toán trả phí khác nhau?
2. Tại sao CardPayment có field active nhưng BankTransferPayment không cần field này?
3. Nếu phương thức mới được thêm vào, class nào cần tạo và class nào có thể giữ nguyên?
4. Vì sao một giao dịch ví bị từ chối phải giữ nguyên số dư?
5. Một switch ở bước ánh xạ chuỗi nhập vào thành PaymentMethod có nhất thiết phải xóa không?
6. Sự khác nhau giữa interface, kế thừa lớp và sử dụng composition trong ví dụ này là gì?

Khi hoàn thành, bạn phải giải thích được **interface là hợp đồng**, **đa hình là cơ chế chọn hành vi theo đối tượng thực tế**, còn **composition** cho phép PaymentProcessor sử dụng các hành vi ấy mà không gắn với implementation cụ thể.