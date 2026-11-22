# Khi nào phụ thuộc vào lớp cụ thể vẫn là lựa chọn hợp lý

## 1. Phụ thuộc vào lớp cụ thể không đồng nghĩa với thiếu Dependency Injection

Khi học **Dependency Injection (DI)** và **Inversion of Control (IoC)**, một lời khuyên thường gặp là “hãy phụ thuộc vào interface”. Lời khuyên này có ích ở những ranh giới cần thay thế hiện thực, nhưng nếu áp dụng như quy tắc tuyệt đối, dự án có thể xuất hiện hàng loạt interface chỉ có một phương thức, một hiện thực và không có lý do thay đổi độc lập.

**DI giải quyết cách một đối tượng nhận phụ thuộc**, còn việc dùng interface hay lớp cụ thể là **quyết định về mức độ trừu tượng và hướng phụ thuộc**.

~~~java
// Có DI: service nhận một lớp cụ thể đã được tạo từ bên ngoài.
final class ReportService {
    private final PdfFormatter formatter;

    ReportService(PdfFormatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }
}
~~~

Ở ví dụ này, `ReportService` nhận `PdfFormatter` qua constructor. Đó là **constructor injection**, dù `PdfFormatter` không phải interface. Nơi lắp ghép có thể khởi tạo `PdfFormatter` và cung cấp cho `ReportService`.

Ngược lại, nếu `ReportService` tự gọi `new PdfFormatter(...)` trong constructor, lớp nghiệp vụ đã giành lấy trách nhiệm tạo và cấu hình phụ thuộc. Điều đó có thể làm việc thử nghiệm, thay cấu hình và quản lý vòng đời khó hơn.

Một lớp cụ thể vẫn cung cấp **hợp đồng sử dụng**: kiểu dữ liệu, phương thức công khai, tiền điều kiện, kết quả và các ngoại lệ có thể xuất hiện. Interface Java là một công cụ để thể hiện hợp đồng đó độc lập với hiện thực; nó không phải điều kiện tiên quyết để một hợp đồng tồn tại.

## 2. Bốn câu hỏi trước khi thêm một abstraction

Không nên quyết định chỉ dựa trên số lượng implementation hiện tại. Một interface có một implementation vẫn có thể có giá trị lớn nếu nó bảo vệ một ranh giới kiến trúc. Ngược lại, một lớp cụ thể được dùng ở nhiều nơi vẫn có thể là lựa chọn hợp lý khi nó là một thành phần ổn định, dễ hiểu.

Hãy trả lời bốn câu hỏi:

1. **Phụ thuộc nằm cùng tầng và cùng quyền sở hữu thay đổi không?** Một bộ tính toán thuần túy của cùng module thường có thể được sử dụng trực tiếp. Nếu nó là adapter của database, HTTP, email, thanh toán hay dịch vụ ngoài, nên cân nhắc hợp đồng đứng về phía nghiệp vụ.
2. **Có nhu cầu thay thế về mặt hành vi hay chỉ khác dữ liệu cấu hình?** Nếu hai cách hoạt động thực sự cần hoán đổi, abstraction có thể giúp. Nếu chỉ thay tham số như thuế suất, ngưỡng miễn phí vận chuyển hoặc locale, một lớp cụ thể có cấu hình rõ ràng đôi khi đủ.
3. **Có cần cô lập tác dụng phụ hoặc chi phí thiết lập trong kiểm thử?** Phụ thuộc thuần túy, tất định và chạy trong bộ nhớ thường có thể dùng trực tiếp trong test. Thành phần phụ thuộc mạng, đồng hồ hệ thống hoặc môi trường ngoài có thể cần seam để thay thế.
4. **Ai chịu trách nhiệm tạo và quản lý vòng đời đối tượng?** Dù kiểu tham số là interface hay class, service nên nhận phụ thuộc từ composition root khi việc tạo, cấu hình và sử dụng thuộc những trách nhiệm khác nhau.

Sơ đồ quyết định rút gọn:

~~~mermaid
flowchart TD
    A["Cần một phụ thuộc mới"] --> B{"Có ranh giới hạ tầng, tác dụng phụ hay nhiều chiến lược?"}
    B -->|Có| C["Xác định hợp đồng theo nhu cầu của bên sử dụng"]
    B -->|Không rõ| D{"Lớp cụ thể ổn định, gọn và kiểm thử trực tiếp được?"}
    D -->|Có| E["Tiêm lớp cụ thể qua constructor"]
    D -->|Không| C
    C --> F["Tiêm abstraction và lắp hiện thực ở composition root"]
    E --> G["Theo dõi yêu cầu thay đổi thực tế"]
    F --> G
~~~

Đây là công cụ đặt câu hỏi, không phải thuật toán bắt buộc. Chẳng hạn một API thương mại chỉ có một hiện thực hôm nay vẫn có thể cần interface do phụ thuộc vào hệ thống bên ngoài, còn một bộ xử lý thuật toán có nhiều cấu hình vẫn có thể giữ chung một class.

## 3. Tình huống phù hợp: thành phần nội bộ ổn định, thuần túy và dễ kiểm thử

Xét một ứng dụng đặt hàng. Quy tắc phí vận chuyển hiện tại đơn giản: đơn hàng đạt ngưỡng được miễn phí, đơn hàng còn lại chịu mức phí cố định.

`ShippingFeeCalculator`:

- Thực hiện tính toán xác định từ dữ liệu đầu vào và cấu hình.
- Không gọi mạng, đọc database hoặc thay đổi trạng thái bên ngoài.
- Có thể dùng trực tiếp trong bài kiểm thử.
- Là quy tắc thuộc module đặt hàng và hiện không có nhiều chiến lược vận chuyển cần hoán đổi.

Trong trường hợp này, tạo `ShippingFeeCalculatorInterface` chỉ để “đúng DI” chưa đem lại lợi ích rõ ràng. Dùng chính lớp `ShippingFeeCalculator` làm kiểu constructor là quyết định hợp lý.

Cùng ứng dụng lại cần cổng thanh toán. Phần này có tác dụng phụ, phụ thuộc hệ thống bên ngoài, có hiện thực production và sandbox, và phải được cô lập khi kiểm thử. Interface `PaymentGateway` phù hợp hơn.

| Phụ thuộc | Nhu cầu hiện tại | Chọn kiểu tiêm | Lý do |
| --- | --- | --- | --- |
| `ShippingFeeCalculator` | Tính toán thuần túy, một chính sách ổn định | Lớp cụ thể | Dễ dùng và kiểm thử thật; chưa có ranh giới thay thế cần thiết |
| `PaymentGateway` | Gọi dịch vụ thanh toán ngoài | Interface hoặc port | Cô lập hạ tầng, cho phép adapter và test double |
| `Clock` của Java | Thời gian hiện tại cần cố định trong kiểm thử | Kiểu trừu tượng sẵn có của JDK | `Clock` là **abstract class**, minh họa seam không nhất thiết là interface |
| `String`, `BigDecimal` hoặc value object bất biến | Biểu diễn giá trị | Lớp cụ thể | Độ trừu tượng bổ sung thường không phục vụ nhu cầu thay thế |

Lưu ý: việc một class đang có một implementation chưa đủ để kết luận phải dùng lớp cụ thể. Điều quyết định là **tính chất của ranh giới**, mức biến động dự kiến có cơ sở và chi phí thay đổi.

## 4. Ví dụ chạy được bằng Java thuần: kết hợp concrete dependency và interface

Ví dụ sau minh họa hai kiểu phụ thuộc cùng tồn tại trong một service, không cần DI container. Dùng JDK 11 trở lên. Lưu toàn bộ thành `App.java`:

~~~java
import java.util.Objects;

public final class App {
    // Thành phần nội bộ ổn định: không cần interface chỉ để có DI.
    public static final class ShippingFeeCalculator {
        private final long flatFeeVnd;
        private final long freeShippingFromVnd;

        public ShippingFeeCalculator(long flatFeeVnd, long freeShippingFromVnd) {
            if (flatFeeVnd < 0) {
                throw new IllegalArgumentException("Phí vận chuyển không được âm");
            }
            if (freeShippingFromVnd <= 0) {
                throw new IllegalArgumentException("Ngưỡng miễn phí phải dương");
            }
            this.flatFeeVnd = flatFeeVnd;
            this.freeShippingFromVnd = freeShippingFromVnd;
        }

        public long feeFor(long subtotalVnd) {
            if (subtotalVnd <= 0) {
                throw new IllegalArgumentException("Giá trị đơn hàng phải dương");
            }
            return subtotalVnd >= freeShippingFromVnd ? 0 : flatFeeVnd;
        }
    }

    // Port ở ranh giới với hệ thống thanh toán bên ngoài.
    public interface PaymentGateway {
        void charge(String orderId, long totalVnd);
    }

    public static final class ConsolePaymentGateway implements PaymentGateway {
        @Override
        public void charge(String orderId, long totalVnd) {
            System.out.println("Thanh toán " + orderId + ": " + totalVnd + " VND");
        }
    }

    public static final class CheckoutService {
        private final ShippingFeeCalculator shipping;
        private final PaymentGateway payments;

        // Cả hai đều được injection; chỉ một trong hai là interface.
        public CheckoutService(
                ShippingFeeCalculator shipping,
                PaymentGateway payments) {
            this.shipping = Objects.requireNonNull(shipping, "shipping");
            this.payments = Objects.requireNonNull(payments, "payments");
        }

        public long checkout(String orderId, long subtotalVnd) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }

            long shippingFeeVnd = shipping.feeFor(subtotalVnd);
            long totalVnd = Math.addExact(subtotalVnd, shippingFeeVnd);

            // Chỉ thực hiện tác dụng phụ sau khi dữ liệu được kiểm tra.
            payments.charge(orderId, totalVnd);
            return totalVnd;
        }
    }

    public static void main(String[] args) {
        // Composition root: quyết định cách tạo và lắp ghép.
        ShippingFeeCalculator shipping = new ShippingFeeCalculator(
                25_000, 200_000);
        PaymentGateway gateway = new ConsolePaymentGateway();

        CheckoutService checkout = new CheckoutService(shipping, gateway);
        checkout.checkout("ORDER-001", 150_000);
        checkout.checkout("ORDER-002", 250_000);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac App.java
java App
~~~

Kết quả mong đợi:

~~~text
Thanh toán ORDER-001: 175000 VND
Thanh toán ORDER-002: 250000 VND
~~~

Ở đây, `ShippingFeeCalculator` là **concrete dependency** và được tiêm qua constructor. `CheckoutService` không khởi tạo hoặc biết các tham số cấu hình của calculator. `PaymentGateway` là **abstraction** bảo vệ ranh giới thanh toán.

Sơ đồ phụ thuộc:

~~~mermaid
flowchart TB
    Root["App.main() — composition root"]
    Service["CheckoutService"]
    Calc["ShippingFeeCalculator (concrete)"]
    Port["PaymentGateway (interface)"]
    Adapter["ConsolePaymentGateway (adapter)"]

    Root -->|"tạo và lắp ghép"| Service
    Root -->|"tạo"| Calc
    Root -->|"tạo"| Adapter
    Service -->|"tham chiếu lớp cụ thể"| Calc
    Service -->|"tham chiếu hợp đồng"| Port
    Adapter -.->|"implements"| Port
~~~

**Phân biệt hai quyết định:**

- **Tiêm hay tự tạo?** `CheckoutService` nhận cả hai phụ thuộc từ ngoài; đó là DI.
- **Dùng kiểu cụ thể hay trừu tượng?** Calculator hiện được biết qua lớp cụ thể, gateway được biết qua interface; đó là quyết định thiết kế hợp đồng phụ thuộc.

`Math.addExact` được dùng để không âm thầm tràn số `long` khi cộng phí. Đây là ví dụ minh họa với số tiền nguyên VND; hệ thống thực tế phải thống nhất đơn vị tiền tệ và kiểu biểu diễn tiền phù hợp với miền nghiệp vụ.

## 5. Kiểm thử với lớp cụ thể: chưa cần mock mọi phụ thuộc

Một lý do khiến người học tạo interface cho mọi class là “để có thể mock”. Nhưng khi một phụ thuộc thuần túy, chạy nhanh và có kết quả tất định, **dùng hiện thực thật trong unit test** thường vừa đơn giản vừa kiểm tra được nhiều hành vi hữu ích.

Trong ví dụ, ta dùng `ShippingFeeCalculator` thật và chỉ thay `PaymentGateway` bằng test double ghi nhận lời gọi.

Lưu thành `AppTest.java` bên cạnh `App.java`:

~~~java
public final class AppTest {
    static final class RecordingPaymentGateway implements App.PaymentGateway {
        int calls;
        String lastOrderId;
        long lastAmountVnd;

        @Override
        public void charge(String orderId, long totalVnd) {
            calls++;
            lastOrderId = orderId;
            lastAmountVnd = totalVnd;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // Sử dụng calculator cụ thể thật, không cần mock nó.
        App.ShippingFeeCalculator shipping =
                new App.ShippingFeeCalculator(25_000, 200_000);
        RecordingPaymentGateway gateway = new RecordingPaymentGateway();
        App.CheckoutService checkout = new App.CheckoutService(
                shipping, gateway);

        long firstTotal = checkout.checkout("ORDER-001", 150_000);
        check(firstTotal == 175_000, "Sai tổng đơn đầu tiên");
        check(gateway.calls == 1, "Phải thanh toán một lần");
        check(gateway.lastAmountVnd == 175_000, "Sai tiền thanh toán");
        check("ORDER-001".equals(gateway.lastOrderId), "Sai mã đơn");

        long secondTotal = checkout.checkout("ORDER-002", 250_000);
        check(secondTotal == 250_000, "Đơn đủ ngưỡng phải miễn phí");
        check(gateway.calls == 2, "Phải thanh toán tổng cộng hai lần");

        // Request không hợp lệ phải bị từ chối trước khi gọi gateway.
        try {
            checkout.checkout("   ", 150_000);
            throw new AssertionError("Phải từ chối mã đơn trống");
        } catch (IllegalArgumentException expected) {
            check(gateway.calls == 2, "Không được thanh toán khi mã đơn sai");
        }

        // Constructor không chấp nhận thiếu phụ thuộc bắt buộc.
        try {
            new App.CheckoutService(null, gateway);
            throw new AssertionError("Phải từ chối shipping null");
        } catch (NullPointerException expected) {
            // Pass.
        }

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac App.java AppTest.java
java AppTest
~~~

Bài test xác nhận kết quả tính phí, tổng thanh toán, số lần gọi gateway, dữ liệu gửi vào cổng thanh toán và một số đầu vào sai. Không cần framework mocking, container hay kết nối thật. **Khả năng kiểm thử nên xét từ hành vi và tác dụng phụ thực tế**, không chỉ từ việc type có phải interface hay không.

Nếu một concrete class khó dựng trong test vì nó tự gọi mạng, đọc cấu hình môi trường, dùng singleton global hoặc yêu cầu nhiều tài nguyên, đó là dấu hiệu xem lại trách nhiệm và ranh giới phụ thuộc. Không nên tạo interface theo phản xạ nếu vấn đề gốc là class đang ôm quá nhiều việc.

## 6. Khi nào nên chuyển sang interface hoặc abstraction khác?

Giả sử về sau ứng dụng có nhiều chính sách vận chuyển: đơn nội địa, giao hỏa tốc, giao quốc tế hoặc chính sách riêng theo kênh bán. Nếu `CheckoutService` cần sử dụng nhiều chiến lược có hành vi khác nhau tùy cấu hình, một abstraction có thể bảo vệ nó khỏi việc biết chi tiết từng chiến lược.

Ví dụ định nghĩa port theo nhu cầu của phía sử dụng:

~~~java
interface ShippingPolicy {
    long feeFor(long subtotalVnd);
}

final class FlatShippingPolicy implements ShippingPolicy {
    private final long feeVnd;
    private final long freeFromVnd;

    FlatShippingPolicy(long feeVnd, long freeFromVnd) {
        if (feeVnd < 0 || freeFromVnd <= 0) {
            throw new IllegalArgumentException("Cấu hình phí không hợp lệ");
        }
        this.feeVnd = feeVnd;
        this.freeFromVnd = freeFromVnd;
    }

    @Override
    public long feeFor(long subtotalVnd) {
        if (subtotalVnd <= 0) {
            throw new IllegalArgumentException("Đơn hàng phải dương");
        }
        return subtotalVnd >= freeFromVnd ? 0 : feeVnd;
    }
}
~~~

Khi chuyển sang thiết kế này, `CheckoutService` có thể nhận `ShippingPolicy` thay cho `ShippingFeeCalculator`; composition root chọn và tiêm một hiện thực. Đoạn mã trên minh họa hướng refactor **khi yêu cầu biến thể xuất hiện**, không phải định nghĩa buộc phải dùng ngay từ đầu.

Cũng có tình huống chọn abstraction từ đầu là hợp lý: cổng thanh toán luôn là điểm tích hợp, một API nghiệp vụ thuộc module khác do nhóm khác quản lý, hoặc chiến lược thay đổi đã được xác nhận trong yêu cầu. Việc chờ đủ hai implementation mới tạo interface có thể khiến chính sách nghiệp vụ bị ràng buộc với adapter hạ tầng.

Một quyết định thay thế là dùng **abstract class** khi cần một phần mã và trạng thái dùng chung, nhưng nên cân nhắc giới hạn kế thừa đơn của Java và rủi ro tạo quan hệ kế thừa chỉ để chia sẻ mã. Các abstraction nhỏ theo khả năng dùng thường phù hợp hơn các lớp cơ sở đồ sộ.

## 7. Liên hệ với Dependency Inversion Principle và hướng kiến trúc

**Dependency Inversion Principle (DIP)** khuyến khích các chính sách cấp cao không phụ thuộc trực tiếp vào chi tiết cấp thấp; cả hai nên dựa trên abstraction phù hợp. Điều này không thể được kiểm tra chỉ bằng cách đếm số interface.

Trong ví dụ:

- `CheckoutService` quyết định luồng nghiệp vụ; hệ thống thanh toán là **chi tiết hạ tầng**. Việc để service phụ thuộc `PaymentGateway` giúp hướng phụ thuộc hợp lý: adapter thanh toán hiện thực hợp đồng mà nghiệp vụ cần.
- `ShippingFeeCalculator` là **thành phần quy tắc nội bộ**, không phải adapter DB/HTTP. Nếu nó ổn định, cùng module và có trách nhiệm nhỏ, tham chiếu lớp cụ thể có thể chấp nhận được.
- Nếu calculator bắt đầu tự truy vấn phí từ API bên thứ ba, đọc trạng thái toàn cục, hoặc thay đổi vì chính sách của module khác, quan hệ phụ thuộc cần được đánh giá lại.

Một interface được đặt ở module hạ tầng rồi để nghiệp vụ import ngược vào đó có thể vẫn giữ hướng phụ thuộc không mong muốn. **Vị trí sở hữu abstraction và cách phân chia module quan trọng hơn cú pháp `interface`.**

Cũng cần phân biệt **Inversion of Control** với **Dependency Inversion Principle**: IoC là khái niệm rộng về việc chuyển quyền điều khiển; DI là kỹ thuật bên ngoài cung cấp phụ thuộc; DIP là nguyên lý xác định quan hệ giữa chính sách và chi tiết. Một constructor có tham số lớp cụ thể vẫn là DI; việc nó có phù hợp DIP hay không phụ thuộc kiến trúc và vai trò lớp ấy.

## 8. Scope, vòng đời và lựa chọn kiểu phụ thuộc

Phụ thuộc vào lớp cụ thể không tự quyết định scope của nó. Composition root vẫn phải xác định instance được tạo khi nào, chia sẻ cho ai và giải phóng bởi ai.

| Đặc điểm concrete dependency | Cách quản lý nên cân nhắc |
| --- | --- |
| Bất biến, thuần túy, không giữ trạng thái theo request | Có thể tạo một instance và chia sẻ nếu API thực sự thread-safe |
| Có trạng thái mutable theo request | Tạo theo request/tác vụ hoặc cô lập trạng thái; tránh dùng chung tùy tiện |
| Sở hữu socket, file, connection hoặc thread | Phải có nơi quản lý mở/đóng rõ ràng, kể cả khi tiêm bằng lớp cụ thể |
| Tốn chi phí khởi tạo | Cân nhắc tái sử dụng an toàn, factory hoặc scope phù hợp; không chỉ dựa vào số lượng interface |

`ShippingFeeCalculator` trong ví dụ dùng các field `final` kiểu số nguyên, không thay đổi trạng thái sau constructor và không gọi tác dụng phụ. Nó là ứng viên hợp lý để tái sử dụng. Nhưng `final` chỉ cấm gán lại tham chiếu field; với một class chứa collection hoặc dependency mutable, nó không tự bảo đảm thread safety.

Dùng container sau này có thể giúp đăng ký và quản lý scope, nhưng container không biến một class có trạng thái dùng chung thành thread-safe. Việc chọn tiêm concrete class cũng không cản trở constructor injection hay quản lý vòng đời.

## 9. Các ngộ nhận và dấu hiệu cần xem lại thiết kế

| Ngộ nhận hoặc cách làm | Vấn đề | Hướng đánh giá |
| --- | --- | --- |
| “Muốn DI thì constructor bắt buộc nhận interface” | Đánh đồng cơ chế tiêm với kiểu khai báo | Concrete class vẫn có thể được tiêm |
| “Một implementation thì không bao giờ cần interface” | Bỏ qua ranh giới với DB, HTTP, API ngoài và sở hữu module | Xem xét vai trò kiến trúc, không chỉ số lượng hiện thực |
| “Cứ tạo interface trước sẽ dễ mở rộng hơn” | Tăng loại và chi phí điều hướng khi chưa có biến thể có ý nghĩa | Trì hoãn abstraction khi chi phí thay đổi tương lai thấp |
| “Concrete class không thể unit test” | Bỏ qua khả năng kiểm thử với đối tượng thật thuần túy | Dùng concrete thật cho logic tất định; test double cho I/O |
| “Có interface thì hệ thống tự lỏng ghép” | Interface có thể vẫn đặt sai module hoặc phơi bày chi tiết hạ tầng | Thiết kế port từ nhu cầu của phía nghiệp vụ |
| “Nếu dùng concrete thì nên `new` ngay trong service” | Trộn sử dụng với tạo/cấu hình phụ thuộc | Tiêm qua constructor khi có trách nhiệm lắp ghép riêng |
| “`final` làm mọi đối tượng an toàn khi dùng chung” | Không bảo vệ trạng thái mutable bên trong phụ thuộc | Đánh giá thread safety và lifecycle thật |
| “Mọi biến thể cần một class riêng” | Có khi chỉ là thay đổi dữ liệu, không thay hành vi | Thử cấu hình rõ ràng trước khi thêm chiến lược phức tạp |

Lựa chọn tốt phải xét cả hai chiều: **chi phí của việc tạo abstraction hôm nay** và **chi phí thay đổi khi yêu cầu mới xuất hiện**. Khi mã nằm trong cùng module và có thể refactor đồng bộ, bắt đầu bằng lớp cụ thể thường tiết kiệm hơn. Khi nhiều module hoặc nhóm triển khai phụ thuộc vào một hợp đồng, một abstraction ổn định có thể rẻ hơn về lâu dài.

## 10. Checklist quyết định và bài tập thực hành

Trước khi quyết định tham số constructor là interface hay class, hãy tự trả lời:

1. Hành vi này là một chính sách nội bộ hay một chi tiết tích hợp bên ngoài?
2. Có bằng chứng cụ thể về các hiện thực cần thay thế hoặc ranh giới module phải giữ ổn định?
3. Tôi có kiểm thử hành vi này dễ dàng bằng hiện thực thật chạy trong bộ nhớ không?
4. Việc khởi tạo và vòng đời có nên được chuyển ra composition root dù tôi giữ kiểu cụ thể không?
5. Nếu chuyển thành interface về sau, phạm vi sửa đổi có nhỏ và kiểm soát được không?
6. Abstraction đề xuất có thể được mô tả bằng nhu cầu của phía sử dụng, thay vì sao chép toàn bộ API của lớp triển khai không?

**Bài tập 1 — Không thêm interface theo thói quen.** Thiết kế `InvoiceService` dùng `MoneyRounding` (tính toán thuần túy, không có trạng thái). Viết constructor nhận trực tiếp `MoneyRounding`, tạo instance tại `main`, rồi kiểm thử cả service bằng đối tượng thật.

**Bài tập 2 — Tìm đúng ranh giới.** Bổ sung `InvoiceRepository` lưu hóa đơn qua database và một hiện thực trong bộ nhớ. Giải thích vì sao nên cân nhắc một port ở đây, ai nên sở hữu port và composition root sẽ chọn hiện thực nào cho production/test.

**Bài tập 3 — Xuất hiện biến thể thật.** Giả sử miễn phí vận chuyển còn tùy hạng thành viên và khu vực. Hãy so sánh hai cách: thêm thông số cấu hình cho `ShippingFeeCalculator` hoặc tạo `ShippingPolicy` với nhiều hiện thực. Xác định dấu hiệu nào khiến cách thứ hai đáng giá.

**Bài tập 4 — Vòng đời.** Một `CurrencyFormatter` bất biến được chia sẻ giữa nhiều request, trong khi `CartSession` ghi trạng thái từng giỏ hàng. Giải thích vì sao có thể dùng scope khác nhau dù cả hai đều là concrete class.

Điểm cần nhớ: **Dependency Injection là khả năng cung cấp phụ thuộc từ bên ngoài; abstraction là công cụ chọn lọc để quản lý biến động và ranh giới.** Dùng lớp cụ thể khi trách nhiệm, tính ổn định và khả năng kiểm thử cho phép; đưa ra interface hoặc abstraction khác khi có nhu cầu tách chính sách khỏi chi tiết, thay thế hành vi hoặc bảo vệ hợp đồng giữa các module.
