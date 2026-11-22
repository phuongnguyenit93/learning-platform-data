# Phụ thuộc bắt buộc, kiểm tra null và điều kiện bất biến

## 1. Constructor là ranh giới bảo vệ trạng thái hợp lệ

Trong thiết kế **Dependency Injection (DI)**, lớp sử dụng phụ thuộc nhận các đối tượng cần thiết qua bên ngoài thay vì tự khởi tạo chúng. Với **constructor injection**, những phụ thuộc cần thiết để đối tượng hoạt động được truyền vào ngay khi khởi tạo. Điều này đưa ra một cam kết quan trọng:

> **Một đối tượng được tạo thành công phải có đủ phụ thuộc bắt buộc và đáp ứng các điều kiện bất biến mà constructor có trách nhiệm bảo vệ.**

**Điều kiện bất biến (invariant)** là quy tắc luôn phải đúng đối với trạng thái hợp lệ của đối tượng, từ khi constructor hoàn thành đến khi đối tượng được sử dụng. Trong một `CheckoutService`, chẳng hạn:

- Cổng thanh toán (`PaymentGateway`) phải tồn tại.
- Bộ gửi biên nhận (`ReceiptSender`) phải tồn tại nếu chức năng của service luôn đòi hỏi gửi biên nhận.
- Mã cửa hàng phải có nội dung, không chỉ là chuỗi khoảng trắng.
- Số tiền tối thiểu phải dương, và số tiền tối đa không được nhỏ hơn tối thiểu.

DI và invariant giải quyết hai khía cạnh bổ trợ nhau: **bên ngoài quyết định cấp phụ thuộc nào**, còn **constructor quyết định cấu hình nhận được có đủ điều kiện để tạo một đối tượng hợp lệ hay không**. Một DI container, nếu có, cũng không thay thế trách nhiệm này.

### Vì sao phải phát hiện lỗi từ sớm?

Đoạn mã sau nhận phụ thuộc qua constructor nhưng chưa bảo vệ trạng thái:

```java
final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    void checkout(long amountVnd) {
        gateway.charge(amountVnd); // NullPointerException có thể xảy ra muộn.
    }
}
```

`new CheckoutService(null)` vẫn thành công. Lỗi chỉ xuất hiện khi `checkout` được gọi, có thể sau nhiều phút hoặc trong một request production. Khi lỗi xảy ra xa điểm khởi tạo, quá trình truy tìm cấu hình sai khó hơn.

Với phụ thuộc bắt buộc, kiểm tra ngay tại constructor giúp **fail fast**: việc tạo đối tượng thất bại tại điểm lắp ghép, trước khi đối tượng không hợp lệ đi vào hệ thống.

## 2. Phân loại đầu vào: phụ thuộc bắt buộc, cấu hình và dữ liệu mỗi lần gọi

Không phải mọi giá trị truyền vào một phương thức đều có vai trò như nhau.

| Loại giá trị | Ví dụ | Kiểm tra ở đâu? | Lý do |
| --- | --- | --- | --- |
| Phụ thuộc bắt buộc | `PaymentGateway`, `ReceiptSender` | Constructor | Đối tượng không thể hoàn thành trách nhiệm nếu thiếu |
| Cấu hình gắn với một instance | Mã cửa hàng, số tiền tối thiểu/tối đa | Constructor | Cấu hình phải nhất quán suốt vòng đời instance |
| Dữ liệu của một thao tác | Mã đơn hàng, email người nhận, số tiền giao dịch | Phương thức nghiệp vụ | Thay đổi theo mỗi lời gọi và cần xác thực theo thao tác |
| Phụ thuộc tùy chọn thực sự | Bộ ghi thống kê không bắt buộc theo yêu cầu thiết kế | Thể hiện rõ trong API | Không nên để một tham số `null` làm mờ ý nghĩa |

Ví dụ: số tiền **tối đa được phép** là cấu hình của `CheckoutService`, được kiểm tra khi khởi tạo. Số tiền **của từng giao dịch** được kiểm tra khi gọi `checkout`.

Điều kiện bất biến khác với **tiền điều kiện của phương thức** (precondition): invariant bảo vệ trạng thái của một instance; precondition yêu cầu đầu vào của một lời gọi cụ thể hợp lệ. Trong trường hợp có trạng thái thay đổi được, mỗi phương thức còn phải duy trì invariant sau khi thực hiện.

## 3. Viết constructor injection bảo vệ các bất biến bằng Java thuần

Ví dụ sau dùng Java 11 trở lên, không cần Spring hay DI container. Lưu toàn bộ thành tệp `ConstructorInjectionDemo.java`.

```java
import java.util.Objects;

public final class ConstructorInjectionDemo {
    public interface PaymentGateway {
        void charge(String shopCode, String orderId, long amountVnd);
    }

    public interface ReceiptSender {
        void send(String email, String orderId);
    }

    public static final class CheckoutService {
        private final PaymentGateway gateway;
        private final ReceiptSender receipts;
        private final String shopCode;
        private final long minChargeVnd;
        private final long maxChargeVnd;

        public CheckoutService(
                PaymentGateway gateway,
                ReceiptSender receipts,
                String shopCode,
                long minChargeVnd,
                long maxChargeVnd) {

            // 1. Kiểm tra phụ thuộc bắt buộc.
            this.gateway = Objects.requireNonNull(gateway, "gateway");
            this.receipts = Objects.requireNonNull(receipts, "receipts");

            // 2. Kiểm tra cấu hình: không được null/rỗng/toàn khoảng trắng.
            if (shopCode == null || shopCode.isBlank()) {
                throw new IllegalArgumentException("shopCode không được để trống");
            }

            // 3. Kiểm tra ràng buộc chéo giữa các tham số.
            if (minChargeVnd <= 0) {
                throw new IllegalArgumentException("minChargeVnd phải > 0");
            }
            if (maxChargeVnd < minChargeVnd) {
                throw new IllegalArgumentException(
                        "maxChargeVnd phải >= minChargeVnd");
            }

            // 4. Lưu trạng thái hợp lệ để sử dụng trong suốt vòng đời.
            this.shopCode = shopCode.strip();
            this.minChargeVnd = minChargeVnd;
            this.maxChargeVnd = maxChargeVnd;
        }

        public void checkout(String orderId, String email, long amountVnd) {
            // Tiền điều kiện của từng lời gọi, không phải cấu hình constructor.
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
            if (email == null || email.isBlank()) {
                throw new IllegalArgumentException("email không hợp lệ");
            }
            if (amountVnd < minChargeVnd || amountVnd > maxChargeVnd) {
                throw new IllegalArgumentException("Số tiền ngoài hạn mức");
            }

            // Chỉ thực hiện tác dụng phụ sau khi đã xác thực đầu vào.
            gateway.charge(shopCode, orderId, amountVnd);
            receipts.send(email, orderId);
        }
    }

    public static final class LoggingGateway implements PaymentGateway {
        @Override
        public void charge(String shopCode, String orderId, long amountVnd) {
            System.out.println(
                    "Thu " + amountVnd + " VND cho " + orderId
                            + " tại " + shopCode);
        }
    }

    public static final class LoggingReceiptSender implements ReceiptSender {
        @Override
        public void send(String email, String orderId) {
            System.out.println("Gửi biên nhận " + orderId + " tới " + email);
        }
    }

    public static void main(String[] args) {
        // Composition root: tạo, chọn và lắp ghép đối tượng.
        PaymentGateway gateway = new LoggingGateway();
        ReceiptSender sender = new LoggingReceiptSender();

        CheckoutService service = new CheckoutService(
                gateway, sender, "SHOP-01", 1_000, 10_000_000);

        service.checkout("ORDER-01", "an@example.com", 150_000);
    }
}
```

Chạy:

```bash
javac ConstructorInjectionDemo.java
java ConstructorInjectionDemo
```

Ở đây, `CheckoutService` chỉ dùng các hợp đồng `PaymentGateway` và `ReceiptSender`. `main` đóng vai trò **composition root**: quyết định hiện thực nào được tạo, rồi truyền chúng vào constructor. Tất cả diễn ra bằng Java thuần.

**Điều kiện được constructor đảm bảo:** Nếu `new CheckoutService(...)` trả về một đối tượng thành công, các field `gateway` và `receipts` khác `null`, `shopCode` có nội dung, `minChargeVnd > 0` và `maxChargeVnd >= minChargeVnd`. Điều này không có nghĩa gateway luôn kết nối mạng thành công hoặc biên nhận chắc chắn được gửi: đó là điều kiện bên ngoài, không thể được bảo đảm chỉ bằng constructor.

### Thứ tự kiểm tra và tác dụng phụ

Hãy ưu tiên **kiểm tra các giá trị đầu vào trước khi thực hiện tác dụng phụ bên ngoài**. Constructor thường nên tránh kết nối mạng, gửi thông báo, ghi dữ liệu hoặc đăng ký callback làm rò rỉ `this` khi trạng thái chưa hoàn thành. Khi phụ thuộc thực sự cần kết nối hay đóng tài nguyên, composition root hoặc thành phần quản lý vòng đời có thể nhận trách nhiệm đó.

Trong ví dụ, `checkout` xác thực dữ liệu trước khi thu tiền. Tuy nhiên, nếu `charge` thành công mà `send` thất bại, ứng dụng vẫn cần chính sách nghiệp vụ như retry hoặc cơ chế outbox. **DI không tự tạo transaction giữa các hệ thống.**

## 4. Chọn cách kiểm tra null và kiểu ngoại lệ

### `Objects.requireNonNull`

```java
this.gateway = Objects.requireNonNull(gateway, "gateway");
```

Nếu `gateway` là `null`, Java ném `NullPointerException` ngay lúc tạo service. Tham số tên `"gateway"` giúp thông báo lỗi xác định trường nào thiếu.

Cách kiểm tra thủ công cũng hợp lệ:

```java
if (gateway == null) {
    throw new IllegalArgumentException("gateway là bắt buộc");
}
this.gateway = gateway;
```

Điều quan trọng là **lựa chọn quy ước nhất quán và báo lỗi sớm, rõ ràng**, không phải bắt buộc một loại ngoại lệ duy nhất.

| Tình huống | Ngoại lệ Java thường dùng | Ví dụ |
| --- | --- | --- |
| Tham chiếu bắt buộc bị `null` | `NullPointerException` với `Objects.requireNonNull`, hoặc `IllegalArgumentException` theo quy ước API | Thiếu `PaymentGateway` |
| Giá trị truyền vào không hợp lệ | `IllegalArgumentException` | `minChargeVnd <= 0`, mã cửa hàng chỉ có dấu cách |
| Một thao tác không thể thực hiện do trạng thái hiện tại của đối tượng | `IllegalStateException` khi phù hợp | Gọi phương thức sau khi đối tượng đã được đóng |
| Lỗi đến từ dịch vụ ngoài | Ngoại lệ do adapter hoặc API miền xác định | Cổng thanh toán không phản hồi |

`Objects.requireNonNull` **chỉ kiểm tra khác `null`**. Nó không đảm bảo chuỗi không rỗng, số dương, danh sách có phần tử, tệp tồn tại hoặc kết nối khỏe mạnh. Những quy tắc ấy phải được kiểm tra riêng khi thực sự là ràng buộc của API.

Với chuỗi, `isBlank()` nhận diện chuỗi rỗng hoặc chỉ có khoảng trắng Unicode theo cách Java định nghĩa; `strip()` loại bỏ khoảng trắng ở đầu và cuối. Với Java 8, có thể dùng phương thức tương ứng hoặc xây dựng quy tắc kiểm tra phù hợp khác vì `isBlank()` và `strip()` có từ Java 11.

### Nullability annotation có thay thế kiểm tra runtime không?

Những annotation như `@NonNull` và `@NotNull` có thể hỗ trợ IDE, công cụ phân tích tĩnh hoặc thư viện validation. Nhưng **ý nghĩa và cơ chế thực thi tùy theo annotation và hệ sinh thái**; chỉ viết annotation không mặc nhiên bảo đảm Java sẽ ném lỗi tại constructor. Nếu ràng buộc bắt buộc là một phần hợp đồng runtime, nên xác nhận cơ chế validation hoạt động hoặc kiểm tra rõ ràng trong mã.

## 5. Invariant mạnh hơn việc chỉ gắn field với `final`

`private final PaymentGateway gateway;` ngăn gán lại **tham chiếu** `gateway` sau khi khởi tạo, nhưng bản thân đối tượng gateway vẫn có thể mang trạng thái thay đổi. Tương tự, `final List<String>` không ngăn nơi khác sửa nội dung danh sách đó.

Ví dụ, nếu constructor nhận danh sách loại tiền được hỗ trợ, việc giữ nguyên tham chiếu có thể làm invariant bị phá vỡ từ bên ngoài:

```java
// Không an toàn nếu caller giữ tham chiếu và sửa danh sách:
this.supportedCurrencies = supportedCurrencies;
```

Khi danh sách là một phần trạng thái cần ổn định, hãy sao chép bảo vệ:

```java
import java.util.List;
import java.util.Objects;

final class PaymentPolicy {
    private final List<String> supportedCurrencies;

    PaymentPolicy(List<String> supportedCurrencies) {
        Objects.requireNonNull(supportedCurrencies, "supportedCurrencies");
        if (supportedCurrencies.isEmpty()
                || supportedCurrencies.stream().anyMatch(
                        value -> value == null || value.isBlank())) {
            throw new IllegalArgumentException(
                    "Phải có ít nhất một mã tiền tệ hợp lệ");
        }
        this.supportedCurrencies = List.copyOf(supportedCurrencies);
    }

    List<String> supportedCurrencies() {
        return supportedCurrencies;
    }
}
```

`List.copyOf` (Java 10+) tạo danh sách không thể sửa qua API danh sách và từ chối phần tử `null`. Việc kiểm tra trước đó đưa ra thông báo cụ thể hơn cho dữ liệu không hợp lệ. Với các phần tử là đối tượng **mutable**, sao chép danh sách chưa phải **deep copy**: vẫn cần quyết định có sao chép từng phần tử hay không.

**Invariant cần được duy trì sau constructor.** Nếu lớp cho phép thay đổi cấu hình qua setter hoặc phương thức cập nhật, các phương thức ấy phải kiểm tra và bảo toàn ràng buộc tương ứng. Việc ưu tiên field `final` và cấu hình bất biến giúp giảm số đường đi cần kiểm soát.

## 6. Phụ thuộc thực sự tùy chọn nên được mô hình hóa rõ

Đừng mặc định mọi tham số có thể nhận `null`. Nếu việc gửi biên nhận là yêu cầu nghiệp vụ bắt buộc, đây là cấu hình sai:

```java
CheckoutService service = new CheckoutService(
        paymentGateway, null, "SHOP-01", 1_000, 10_000_000);
```

Nếu nghiệp vụ **thật sự cho phép không gửi biên nhận**, có thể chọn một trong những API rõ nghĩa:

- Thiết kế hai trường hợp sử dụng riêng, nếu hành vi và trách nhiệm khác nhau đáng kể.
- Cung cấp `NoOpReceiptSender` có chủ đích khi việc bỏ qua là chính sách được chấp nhận. Với cách này, interface vẫn bắt buộc, nhưng caller chọn hiện thực “không làm gì” một cách minh bạch.
- Dùng một lựa chọn được thể hiện rõ trong cấu hình hoặc constructor, nếu hành vi tùy chọn có ý nghĩa với miền nghiệp vụ.

`null` không phải công cụ diễn đạt chính sách tốt vì caller khó phân biệt “cố ý tắt chức năng” và “quên truyền phụ thuộc”. Cũng không nên dùng `Objects.requireNonNullElse(...)` để âm thầm thay thế một phụ thuộc **bắt buộc**: điều đó có thể che giấu lỗi cấu hình.

## 7. Kiểm thử constructor và invariant bằng Java thuần

Không cần DI container để kiểm tra tính hợp lệ của đối tượng. Tạo `ConstructorInjectionDemoTest.java` bên cạnh tệp ví dụ:

```java
public final class ConstructorInjectionDemoTest {
    static final class RecordingGateway
            implements ConstructorInjectionDemo.PaymentGateway {
        int calls;
        long lastAmount;

        @Override
        public void charge(String shopCode, String orderId, long amountVnd) {
            calls++;
            lastAmount = amountVnd;
        }
    }

    static final class RecordingSender
            implements ConstructorInjectionDemo.ReceiptSender {
        int calls;

        @Override
        public void send(String email, String orderId) {
            calls++;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expect(
            Class<? extends RuntimeException> expected, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException exception) {
            if (expected.isInstance(exception)) {
                return;
            }
            throw new AssertionError(
                    "Sai loại ngoại lệ: " + exception.getClass(), exception);
        }
        throw new AssertionError("Thiếu ngoại lệ " + expected.getName());
    }

    public static void main(String[] args) {
        RecordingGateway gateway = new RecordingGateway();
        RecordingSender sender = new RecordingSender();

        // Phụ thuộc bắt buộc: không nhận null.
        expect(NullPointerException.class,
                () -> new ConstructorInjectionDemo.CheckoutService(
                        null, sender, "SHOP-01", 1_000, 10_000));
        expect(NullPointerException.class,
                () -> new ConstructorInjectionDemo.CheckoutService(
                        gateway, null, "SHOP-01", 1_000, 10_000));

        // Cấu hình phải đáp ứng invariant.
        expect(IllegalArgumentException.class,
                () -> new ConstructorInjectionDemo.CheckoutService(
                        gateway, sender, "   ", 1_000, 10_000));
        expect(IllegalArgumentException.class,
                () -> new ConstructorInjectionDemo.CheckoutService(
                        gateway, sender, "SHOP-01", 0, 10_000));
        expect(IllegalArgumentException.class,
                () -> new ConstructorInjectionDemo.CheckoutService(
                        gateway, sender, "SHOP-01", 10_000, 1_000));

        // Đối tượng hợp lệ được tạo thành công.
        ConstructorInjectionDemo.CheckoutService service =
                new ConstructorInjectionDemo.CheckoutService(
                        gateway, sender, "SHOP-01", 1_000, 10_000);

        // Dữ liệu sai phải bị từ chối trước tác dụng phụ.
        expect(IllegalArgumentException.class,
                () -> service.checkout("ORDER-01", "an@example.com", 500));
        check(gateway.calls == 0, "Không được thu tiền");
        check(sender.calls == 0, "Không được gửi biên nhận");

        service.checkout("ORDER-02", "an@example.com", 5_000);
        check(gateway.calls == 1, "Phải thu đúng một lần");
        check(gateway.lastAmount == 5_000, "Sai số tiền");
        check(sender.calls == 1, "Phải gửi đúng một biên nhận");

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
```

Chạy:

```bash
javac ConstructorInjectionDemo.java ConstructorInjectionDemoTest.java
java ConstructorInjectionDemoTest
```

Mỗi kiểm thử constructor dùng một tổ hợp đầu vào có chủ đích; test double ghi nhận lời gọi và giúp chứng minh rằng yêu cầu không hợp lệ không gây tác dụng phụ. Trong dự án thật, có thể chuyển các tình huống này thành test tham số với JUnit, nhưng tính chất cần kiểm tra không thay đổi.

Bổ sung các trường hợp biên khi có ý nghĩa nghiệp vụ: hạn mức bằng tối thiểu/tối đa, chuỗi chỉ chứa khoảng trắng, dữ liệu `null`, danh sách bị thay đổi từ ngoài, hoặc phụ thuộc ném lỗi.

## 8. Những quyết định thiết kế dễ sai

| Dấu hiệu | Rủi ro | Điều chỉnh |
| --- | --- | --- |
| Constructor chỉ gán field mà không kiểm tra `null` | Đối tượng thiếu phụ thuộc vẫn được tạo | Kiểm tra phụ thuộc bắt buộc ngay trong constructor |
| Kiểm tra `null` nhưng bỏ qua giá trị rỗng hoặc ràng buộc chéo | Trạng thái vô nghĩa hoặc mâu thuẫn | Thêm các điều kiện miền nghiệp vụ vào constructor |
| Dùng setter cho phụ thuộc luôn bắt buộc | Có khoảng thời gian đối tượng chưa sử dụng được | Chuyển sang constructor injection |
| Để `null` ngầm biểu diễn “tùy chọn” | Khó biết chủ ý của caller | Thiết kế API thể hiện chính sách tùy chọn |
| Constructor tự tạo client, gọi mạng hoặc đọc cấu hình toàn cục | Trộn kiểm tra bất biến với khởi tạo hạ tầng | Lắp ghép tại composition root; để adapter đảm nhận hạ tầng |
| `final` nhưng giữ tham chiếu collection mutable từ caller | Caller vẫn có thể phá invariant | Defensive copy, hạn chế trạng thái mutable |
| Constructor nhận quá nhiều phụ thuộc không liên quan | Lớp có thể đang gánh nhiều trách nhiệm | Xem lại phạm vi service, tách use case hoặc policy phù hợp |
| Kiểm tra trạng thái của phụ thuộc chỉ tại constructor | Không bảo đảm dịch vụ ngoài luôn sẵn sàng | Xử lý thất bại khi gọi, retry/timeout/circuit breaker nếu cần |
| Kiểm tra số tiền bằng `double` | Sai số biểu diễn số thực có thể tác động đến tính toán tiền | Dùng đơn vị nhỏ nhất kiểu `long` hoặc `BigDecimal` theo quy ước miền |

Constructor nên **xác lập một trạng thái hợp lệ, rõ ràng và rẻ để kiểm tra**. Đừng cố xác minh mọi điều kiện của thế giới bên ngoài ngay khi khởi tạo. Ví dụ, một gateway có thể còn sống tại thời điểm tạo service nhưng mất kết nối khi giao dịch thật diễn ra.

Về vòng đời và scope, nếu cùng một `CheckoutService` được nhiều request dùng chung, các phụ thuộc mà nó giữ cũng phải được đánh giá về tính an toàn luồng. `final` ngăn gán lại field, nhưng không làm cho một gateway có trạng thái mutable tự động trở nên thread-safe. Bên tạo và lắp ghép đối tượng chịu trách nhiệm chọn phạm vi tái sử dụng thích hợp.

## 9. Từ Java thuần sang DI container

Với Java thuần, điểm lắp ghép có thể viết trực tiếp:

```java
PaymentGateway gateway = new LoggingGateway();
ReceiptSender sender = new LoggingReceiptSender();
CheckoutService service = new CheckoutService(
        gateway, sender, "SHOP-01", 1_000, 10_000_000);
```

Khi ứng dụng dùng DI container, container có thể tạo `gateway` và `sender`, sau đó gọi đúng constructor ấy. **Những bất biến trong constructor vẫn cần được bảo vệ**, kể cả khi framework tự lắp ghép phụ thuộc. Container có thể hỗ trợ phát hiện thiếu bean hoặc cấu hình sai ở giai đoạn khởi động, nhưng không mặc nhiên hiểu mọi quy tắc nghiệp vụ như “số tiền tối đa phải lớn hơn hoặc bằng tối thiểu”.

Vì vậy, hãy học constructor injection, composition root, scope và vòng đời bằng Java thuần trước. Khi mở rộng sang container, bạn vẫn có thể phân biệt hai trách nhiệm: **nơi lắp ghép cung cấp phụ thuộc; lớp nhận phụ thuộc tự bảo vệ trạng thái hợp lệ của chính nó.**

## 10. Bài tập tự luyện

**Bài 1 — Phân tích invariant:** Viết class `RetryPolicy` nhận `maxAttempts`, `initialDelayMillis` và `maxDelayMillis`. Xác định điều kiện nào phải đúng tại constructor: số lần thử phải dương, độ trễ không âm, độ trễ tối đa không nhỏ hơn độ trễ khởi tạo. Thêm ít nhất bốn kiểm thử cho dữ liệu sai.

**Bài 2 — Phân tách ranh giới:** Cho `ReportService` cần một `ReportRepository` bắt buộc, `Clock` để xác định ngày hiện tại và `reportId` thay đổi theo mỗi lần xuất. Hãy quyết định thành phần nào nên được constructor injection, giá trị nào cần truyền vào phương thức, và vị trí phù hợp để tạo `Clock.systemUTC()`.

**Bài 3 — Bất biến và mutable collection:** Tạo class `DeliveryPolicy` nhận danh sách vùng phục vụ. Hãy viết một test sửa danh sách gốc sau khi tạo policy và chứng minh rằng policy không bị ảnh hưởng. Sử dụng `List.copyOf` hoặc một chiến lược sao chép phù hợp.

**Tự kiểm tra:** Nếu một constructor chạy thành công, những điều gì bạn có thể khẳng định chắc chắn về đối tượng? Những điều gì vẫn có thể thất bại về sau vì mạng, dữ liệu request, scope hoặc phụ thuộc bên ngoài? Trả lời rõ hai câu hỏi này giúp thiết kế contract constructor đúng mức, tránh cả kiểm tra thiếu lẫn hứa hẹn quá phạm vi.
