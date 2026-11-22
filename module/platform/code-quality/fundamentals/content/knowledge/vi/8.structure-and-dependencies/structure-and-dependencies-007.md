# Tổ hợp đối tượng và kế thừa theo hợp đồng

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **tổ hợp đối tượng (object composition)**, **kế thừa lớp (class inheritance)** và **quan hệ kiểu con theo hợp đồng (behavioral subtyping)** trong Java.
2. Giải thích vì sao quan hệ **“có một” (has-a)** thường phù hợp với việc lắp ghép hành vi, còn quan hệ **“là một” (is-a)** chỉ có ý nghĩa khi đối tượng con đáp ứng đầy đủ hợp đồng của kiểu cha.
3. Nhận diện vi phạm **nguyên tắc thay thế Liskov (Liskov Substitution Principle – LSP)** thông qua điều kiện đầu vào, kết quả, bất biến, lỗi và tác dụng phụ.
4. Thiết kế thành phần có thể thay thế bằng **interface và constructor injection**, đồng thời tránh lớp cha chứa quá nhiều trách nhiệm.
5. Chọn giữa composition và inheritance theo nhu cầu thay đổi, khả năng kiểm thử, mức phụ thuộc và tính dễ hiểu của hệ thống.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã nguồn được đánh giá qua khả năng **đáng tin cậy, dễ hiểu và dễ thay đổi**. Khi thiết kế cấu trúc và phụ thuộc, một quyết định quan trọng là: *một đối tượng nên sử dụng đối tượng khác để hoàn thành công việc, hay nên kế thừa từ nó?* Câu trả lời ảnh hưởng trực tiếp đến phạm vi sửa mã, khả năng thay thế triển khai và rủi ro hành vi bất ngờ.

**Thông điệp chính:** Ưu tiên **tổ hợp** khi cần ghép những trách nhiệm độc lập; sử dụng **kế thừa** khi thật sự tồn tại quan hệ kiểu con và có thể giữ vững **hợp đồng hành vi**. Không nên chọn chỉ vì cú pháp tái sử dụng được vài dòng mã.

## 1. Ba khái niệm cần phân biệt

### 1.1. Tổ hợp đối tượng: một đối tượng sử dụng đối tượng khác

**Composition** là cách tạo hành vi của một đối tượng bằng cách giữ hoặc nhận các đối tượng cộng tác và ủy quyền một phần công việc cho chúng.

Ví dụ, **CheckoutService** có thể sử dụng **ShippingFeePolicy** để tính phí vận chuyển:

~~~text
CheckoutService
    ├── ShippingFeePolicy
    ├── OrderRepository
    └── PaymentGateway
~~~

Ở đây, CheckoutService **có** các cộng tác viên, nhưng không **là** một ShippingFeePolicy hay PaymentGateway. Nó chịu trách nhiệm điều phối quy trình, trong khi từng cộng tác viên chịu trách nhiệm cho một khả năng cụ thể.

Composition thường được triển khai bằng **trường (field)**, **tham số constructor** hoặc **tham số phương thức**:

~~~java
final class GreetingService {
    private final MessageFormatter formatter;

    GreetingService(MessageFormatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }

    String greet(String name) {
        return formatter.format(name);
    }
}

interface MessageFormatter {
    String format(String name);
}
~~~

**GreetingService** sử dụng giao diện **MessageFormatter**. Khi cần thay định dạng lời chào, không nhất thiết phải thay cách GreetingService tổ chức công việc. Tuy nhiên, tạo interface cho mọi phép nối chuỗi đơn giản chưa chắc có lợi; ví dụ chỉ minh họa quan hệ giữa hai thành phần.

**Lợi ích thường gặp:** phụ thuộc rõ ràng, có thể thay một cộng tác viên mà không sửa toàn bộ lớp, dễ cô lập logic khi kiểm thử. **Chi phí:** thêm điểm điều hướng và thêm hợp đồng cần hiểu nếu chia quá nhỏ.

### 1.2. Kế thừa lớp: lớp con kế thừa cấu trúc và hành vi

Với **extends**, lớp con kế thừa những thành phần được phép truy cập từ lớp cha và có thể ghi đè những phương thức được phép ghi đè:

~~~java
class Report {
    String title() {
        return "Báo cáo";
    }
}

class SalesReport extends Report {
    @Override
    String title() {
        return "Báo cáo bán hàng";
    }
}
~~~

Java hỗ trợ một lớp kế thừa trực tiếp tối đa **một lớp cha**, nhưng có thể triển khai nhiều interface. **extends** có thể giúp chia sẻ mã và cung cấp điểm mở rộng, song nó tạo mối ràng buộc giữa lớp con và các quyết định của lớp cha, đặc biệt khi lớp cha cung cấp trạng thái thay đổi được hoặc gọi phương thức có thể override.

Cú pháp cho phép viết **SalesReport extends Report** không chứng minh quan hệ “là một” đã đúng về hành vi. Lớp con phải hoạt động đúng ở mọi ngữ cảnh vốn chấp nhận lớp cha.

### 1.3. Kế thừa theo hợp đồng: đối tượng con có thể thay thế kiểu cha

**Behavioral subtyping** đề cập đến mối quan hệ **hợp đồng hành vi**, không chỉ quan hệ cú pháp.

Giả sử một API nhận đối tượng kiểu **FeePolicy**, có hợp đồng: “Với mọi đơn hàng hợp lệ, trả về phí không âm, không gây tác dụng phụ và không trả null”. Một triển khai chỉ hỗ trợ đơn từ 100.000 đồng trở lên sẽ phá hợp đồng nếu hợp đồng chung cho phép đơn 50.000 đồng.

Trong Java, quan hệ kiểu con có thể được khai báo qua **extends** hoặc **implements**. Cả hai đều cho phép đa hình, nhưng không tự chứng minh lớp triển khai đáp ứng đúng ngữ nghĩa.

| Khía cạnh | Composition | Class inheritance | Subtyping theo hợp đồng |
| --- | --- | --- | --- |
| Quan hệ chính | **Có / sử dụng** cộng tác viên | **Là lớp con của** lớp khác | **Có thể dùng thay** kiểu cha |
| Cú pháp Java thường gặp | Field, constructor, method parameter | **extends** | **extends** hoặc **implements** |
| Tái sử dụng hành vi | Ủy quyền cho đối tượng cộng tác | Kế thừa phương thức/trạng thái được phép | Đa hình qua hợp đồng chung |
| Ràng buộc | Phụ thuộc vào giao diện cộng tác viên | Phụ thuộc vào API và thiết kế của lớp cha | Phải giữ cam kết hành vi với người gọi |
| Rủi ro | Quá nhiều lớp chuyển tiếp hoặc cấu hình | Kế thừa chặt, lớp cha thay đổi làm vỡ lớp con | Triển khai có cùng chữ ký nhưng cư xử khác hợp đồng |

**Composition và subtyping có thể phối hợp:** một lớp nhận **interface** vào constructor rồi ủy quyền cho một trong nhiều triển khai. Đây là cách thường dùng để giảm phụ thuộc vào chi tiết.

## 2. Hợp đồng hành vi là gì?

Một **hợp đồng** diễn tả điều người gọi có thể tin tưởng về một thành phần. Nó rộng hơn tên phương thức và kiểu dữ liệu.

| Thành phần hợp đồng | Câu hỏi cần trả lời | Ví dụ với chính sách phí vận chuyển |
| --- | --- | --- |
| **Tiền điều kiện (precondition)** | Đầu vào nào được phép? | Đơn hàng có tạm tính không âm và số lượng hàng dương |
| **Hậu điều kiện (postcondition)** | Với đầu vào hợp lệ, kết quả nào được bảo đảm? | Phí được trả về, không null, không âm |
| **Bất biến (invariant)** | Những điều gì luôn đúng trong trạng thái đối tượng? | Cấu hình ngưỡng và mức phí không âm |
| **Lỗi được phép** | Khi nào có thể thất bại và được báo như thế nào? | Từ chối dữ liệu không hợp lệ theo hợp đồng |
| **Tác dụng phụ** | Có đọc/ghi dữ liệu ngoài, phát sự kiện hoặc thay đổi trạng thái không? | Phép tính phí thuần không ghi đơn hàng |
| **Đơn vị và ý nghĩa** | Giá trị đang biểu diễn điều gì? | Số tiền theo một đơn vị tiền tệ đã xác định |
| **Điều kiện phi chức năng cần cam kết** | Có giới hạn thời gian, thứ tự, đồng thời hay idempotency không? | Nếu hợp đồng cam kết thread-safe, mọi triển khai phải tôn trọng |

Hợp đồng có thể được ghi bằng Javadoc, kiểu dữ liệu, kiểm tra đầu vào và test; những điều quan trọng nên có nhiều hơn một bằng chứng. Tránh đưa ra cam kết ngầm mà người dùng API phải tự suy luận từ một triển khai hiện có.

### Nguyên tắc thay thế Liskov

Một kiểu con có thể thay cho kiểu cha nếu **những thuộc tính đúng đắn mà người gọi đang dựa vào vẫn tiếp tục được bảo vệ**. Khi xét tiền điều kiện, hậu điều kiện và bất biến, quy tắc thực dụng là:

- **Không tăng yêu cầu đầu vào:** lớp con không được đòi hỏi điều kiện mạnh hơn hợp đồng cha. Nếu cha chấp nhận mọi đơn có tạm tính không âm, con không được từ chối một phần đơn hợp lệ chỉ vì “chỉ hỗ trợ đơn lớn”.
- **Không làm yếu cam kết đầu ra:** nếu cha bảo đảm phí không âm và không null, con không thể trả phí âm hoặc null cho đầu vào hợp lệ.
- **Giữ các bất biến chung:** không làm xuất hiện trạng thái khiến người gọi của kiểu cha bị sai kỳ vọng.
- **Không thêm hành vi bất ngờ làm hỏng người gọi:** ví dụ ghi dữ liệu ngoài hoặc ném lỗi vì một điều kiện đầu vào vốn được cho phép. Những ngoại lệ được phép cần xuất phát từ hợp đồng đã công bố.

**LSP không yêu cầu mọi triển khai trả cùng một giá trị.** Hai chính sách vận chuyển có thể trả mức phí khác nhau cho cùng đơn hàng. Chúng vẫn thay thế được nhau khi cả hai đáp ứng hợp đồng chung và việc thay chính sách là quyết định được nghiệp vụ cho phép.

### Ví dụ về vi phạm: siết tiền điều kiện ở lớp con

~~~java
import java.math.BigDecimal;
import java.util.Objects;

// Hợp đồng của lớp cha:
// subtotal không âm => trả về phí không âm, không null.
abstract class FeeCalculator {
    abstract BigDecimal fee(BigDecimal subtotal);
}

// Minh họa THIẾT KẾ SAI: không đáp ứng hợp đồng trên.
final class MinimumOrderFeeCalculator extends FeeCalculator {
    @Override
    BigDecimal fee(BigDecimal subtotal) {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.compareTo(new BigDecimal("100000")) < 0) {
            throw new IllegalArgumentException(
                    "Only orders >= 100000 are supported");
        }
        return new BigDecimal("20000");
    }
}
~~~

Giả sử ứng dụng đã kiểm tra **subtotal = 50000** là dữ liệu hợp lệ theo hợp đồng của FeeCalculator. Thay một triển khai khác bằng MinimumOrderFeeCalculator khiến ứng dụng bất ngờ nhận lỗi. Lỗi nằm ở **hợp đồng kiểu con**, không nằm ở chỗ phương thức **fee(...)** có đúng chữ ký Java hay không.

Nếu nghiệp vụ thực sự có yêu cầu “không tiếp nhận đơn dưới 100.000”, cần diễn đạt quy tắc này ở đúng **ranh giới nghiệp vụ** hoặc định nghĩa hợp đồng khác phù hợp. Không nên ẩn nó trong một kiểu con của hợp đồng vốn chấp nhận tất cả đơn không âm.

## 3. Ví dụ Java: ghép hành vi bằng composition và interface

Ta sẽ xây dựng một mô hình nhỏ cho giá trị thanh toán:

- **Basket** giữ tạm tính và số lượng mặt hàng hợp lệ.
- **ShippingFeePolicy** xác định hợp đồng tính phí.
- **FixedShippingFeePolicy** luôn tính mức phí cố định.
- **FreeAboveThresholdPolicy** miễn phí khi tạm tính từ ngưỡng cho trước.
- **CheckoutCalculator** ghép một chính sách với phép tính tổng.

Đây là ví dụ học tập, với số tiền giả định theo cùng một đơn vị tiền tệ; chưa bao gồm thuế, giảm giá, cách làm tròn hay giao tiếp dịch vụ ngoài.

### 3.1. Xác định dữ liệu và hợp đồng trước khi viết thuật toán

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record Basket(BigDecimal subtotal, int itemCount) {
    Basket {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
        if (itemCount <= 0) {
            throw new IllegalArgumentException("itemCount must be > 0");
        }
    }
}

/**
 * Một chính sách tính phí:
 * - Nhận Basket hợp lệ, không null;
 * - Trả về BigDecimal không null, không âm;
 * - Không sửa Basket và không gây tác dụng phụ.
 */
interface ShippingFeePolicy {
    BigDecimal fee(Basket basket);
}

final class FixedShippingFeePolicy implements ShippingFeePolicy {
    private final BigDecimal fixedFee;

    FixedShippingFeePolicy(BigDecimal fixedFee) {
        this.fixedFee = Objects.requireNonNull(fixedFee, "fixedFee");
        if (fixedFee.signum() < 0) {
            throw new IllegalArgumentException("fixedFee must be >= 0");
        }
    }

    @Override
    public BigDecimal fee(Basket basket) {
        Objects.requireNonNull(basket, "basket");
        return fixedFee;
    }
}

final class FreeAboveThresholdPolicy implements ShippingFeePolicy {
    private final BigDecimal threshold;
    private final BigDecimal standardFee;

    FreeAboveThresholdPolicy(
            BigDecimal threshold, BigDecimal standardFee) {
        this.threshold = Objects.requireNonNull(threshold, "threshold");
        this.standardFee = Objects.requireNonNull(
                standardFee, "standardFee");
        if (threshold.signum() < 0 || standardFee.signum() < 0) {
            throw new IllegalArgumentException(
                    "threshold and standardFee must be >= 0");
        }
    }

    @Override
    public BigDecimal fee(Basket basket) {
        Objects.requireNonNull(basket, "basket");

        return basket.subtotal().compareTo(threshold) >= 0
                ? BigDecimal.ZERO
                : standardFee;
    }
}

final class CheckoutCalculator {
    private final ShippingFeePolicy shippingFeePolicy;

    CheckoutCalculator(ShippingFeePolicy shippingFeePolicy) {
        this.shippingFeePolicy = Objects.requireNonNull(
                shippingFeePolicy, "shippingFeePolicy");
    }

    BigDecimal total(Basket basket) {
        Objects.requireNonNull(basket, "basket");
        BigDecimal shippingFee = shippingFeePolicy.fee(basket);
        return basket.subtotal().add(shippingFee);
    }
}
~~~

Ví dụ có thể đặt các kiểu **package-private** này vào một file Java để minh họa. Khi phát triển ứng dụng thật, các kiểu thường được tổ chức thành tệp và package phù hợp. **record** yêu cầu Java 16 trở lên và có thể dùng ổn định trong Java 17.

### 3.2. Phân tích phụ thuộc

~~~mermaid
flowchart TD
    C[CheckoutCalculator] --> I[ShippingFeePolicy]
    F[FixedShippingFeePolicy] -. implements .-> I
    T[FreeAboveThresholdPolicy] -. implements .-> I
    C --> B[Basket]
    F --> B
    T --> B
~~~

Điểm cần chú ý:

1. **CheckoutCalculator chỉ biết hợp đồng ShippingFeePolicy**, không phụ thuộc trực tiếp vào tên lớp phí cố định hay chính sách ngưỡng.
2. **Constructor injection** làm rõ chính sách được chọn khi tạo đối tượng; không cần tìm chính sách trong biến toàn cục.
3. Hai triển khai **không kế thừa mã triển khai của nhau**. Chúng cùng tuân thủ hợp đồng chung và có thể phát triển quy tắc nội bộ độc lập.
4. **Basket** chặn trạng thái đầu vào không hợp lệ gần nơi dữ liệu được tạo. Các policy vẫn kiểm tra basket không null tại biên phương thức.
5. Giá trị cấu hình bất biến trong ví dụ giúp dễ suy luận hơn khi nhiều yêu cầu sử dụng cùng đối tượng.

Không nên suy ra rằng cứ có hơn một lớp là nhất thiết phải tạo interface. **ShippingFeePolicy** có ích trong bối cảnh này vì hai chính sách được yêu cầu thay thế theo cấu hình hoặc điều kiện kinh doanh đã biết.

### 3.3. Thay chính sách mà không đổi mã điều phối

~~~java
import java.math.BigDecimal;

final class ExampleUsage {
    public static void main(String[] args) {
        Basket basket = new Basket(
                new BigDecimal("500000"), 2);

        CheckoutCalculator regularCheckout =
                new CheckoutCalculator(
                        new FixedShippingFeePolicy(
                                new BigDecimal("30000")));

        CheckoutCalculator promotionalCheckout =
                new CheckoutCalculator(
                        new FreeAboveThresholdPolicy(
                                new BigDecimal("500000"),
                                new BigDecimal("30000")));

        System.out.println(regularCheckout.total(basket));     // 530000
        System.out.println(promotionalCheckout.total(basket)); // 500000
    }
}
~~~

Chúng ta **tổ hợp** CheckoutCalculator với các đối tượng policy khác nhau. Trong cả hai trường hợp, thuật toán của CheckoutCalculator vẫn là: lấy tạm tính, yêu cầu policy tính phí và cộng vào tổng.

Nếu dùng kế thừa theo kiểu **PromotionalCheckoutCalculator extends CheckoutCalculator**, về sau có thể xuất hiện thêm **PremiumCheckoutCalculator**, **InternationalCheckoutCalculator**, **ExpressCheckoutCalculator** và các tổ hợp khác. Khi mỗi biến thể chỉ khác chính sách phí, tạo lớp con cho mọi tổ hợp có nguy cơ làm cấu trúc phình to. Composition thể hiện trực tiếp trục thay đổi này.

### 3.4. Kiểm thử hợp đồng chung và quy tắc riêng

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {

    @Test
    void everyPolicyHonorsTheCommonContract() {
        Basket basket = new Basket(new BigDecimal("100000"), 2);

        List<ShippingFeePolicy> policies = List.of(
                new FixedShippingFeePolicy(new BigDecimal("30000")),
                new FreeAboveThresholdPolicy(
                        new BigDecimal("500000"),
                        new BigDecimal("30000")));

        for (ShippingFeePolicy policy : policies) {
            BigDecimal fee = policy.fee(basket);
            assertNotNull(fee);
            assertTrue(fee.signum() >= 0);
        }
    }

    @Test
    void thresholdIsInclusive() {
        ShippingFeePolicy policy = new FreeAboveThresholdPolicy(
                new BigDecimal("500000"),
                new BigDecimal("30000"));

        Basket atThreshold =
                new Basket(new BigDecimal("500000"), 1);
        Basket belowThreshold =
                new Basket(new BigDecimal("499999"), 1);

        assertEquals(BigDecimal.ZERO, policy.fee(atThreshold));
        assertEquals(
                new BigDecimal("30000"),
                policy.fee(belowThreshold));
    }

    @Test
    void checkoutUsesAnyConformingPolicy() {
        Basket basket = new Basket(new BigDecimal("500000"), 2);

        CheckoutCalculator regular = new CheckoutCalculator(
                new FixedShippingFeePolicy(new BigDecimal("30000")));
        CheckoutCalculator promotional = new CheckoutCalculator(
                new FreeAboveThresholdPolicy(
                        new BigDecimal("500000"),
                        new BigDecimal("30000")));

        assertEquals(
                new BigDecimal("530000"), regular.total(basket));
        assertEquals(
                new BigDecimal("500000"), promotional.total(basket));
    }
}
~~~

Đây là ví dụ với **JUnit Jupiter (JUnit 5)**. Test hợp đồng chung bảo vệ tính chất “kết quả không null, không âm”; test riêng xác nhận tính chất của chính sách cụ thể. Trong hệ thống thực, hợp đồng còn có thể bao gồm giới hạn số tiền, đơn vị, khả năng chạy đồng thời và các điều kiện lỗi cần kiểm thử tương ứng.

Việc dùng **BigDecimal** tránh những sai số biểu diễn nhị phân phổ biến của **double** trong phép tính tiền, nhưng **không tự đặt chính sách làm tròn**. Nếu nhiều tiền tệ hoặc đơn vị khác nhau cùng xuất hiện, cần thể hiện chúng rõ ràng trong mô hình và hợp đồng.

## 4. Vì sao composition thường giúp cấu trúc dễ thay đổi?

### 4.1. Cô lập các lý do thay đổi

Giả sử chính sách miễn phí vận chuyển chuyển từ 500.000 sang 700.000 đồng. Với thiết kế trên, nhóm chỉ cần điều chỉnh nơi khởi tạo **FreeAboveThresholdPolicy** hoặc nguồn cấu hình, cùng các test liên quan. **CheckoutCalculator** không cần biết chính sách miễn phí có những ngưỡng nào.

Nếu về sau xuất hiện chính sách theo khu vực và khối lượng, có thể thêm triển khai **ShippingFeePolicy** phù hợp mà không sửa luồng tính tổng, miễn là hợp đồng chung đủ diễn đạt.

### 4.2. Điều khiển phụ thuộc ở ranh giới thích hợp

Composition khuyến khích một thành phần phụ thuộc vào **khả năng cần sử dụng** thay vì toàn bộ lớp hiện thực.

Ví dụ, CheckoutCalculator cần **fee(Basket)**, không cần biết cách policy tải cấu hình hoặc truy cập hệ thống khác. Việc giữ API nhỏ giúp giảm số chi tiết mỗi bên cần hiểu. Tuy nhiên, nếu một chính sách thực sự cần I/O, cần thay đổi hợp đồng hoặc tách tầng phù hợp: không nên lén biến phép tính được cam kết thuần thành lời gọi mạng không được kiểm soát.

### 4.3. Dễ thay cộng tác viên trong kiểm thử

Khi một lớp làm việc qua interface, test có thể cấp một triển khai đơn giản có hành vi xác định. Chẳng hạn, với CheckoutCalculator, ta đã kiểm thử bằng FixedShippingFeePolicy mà không cần database hay server.

Nhưng không nên coi mọi interface đều phải được tạo chỉ vì muốn mock. Nếu một đối tượng bất biến và tính toán thuần đã dễ kiểm thử, việc thêm interface và fake riêng có thể không đem lại lợi ích đủ lớn.

### 4.4. Ghép hành vi theo từng trục thay đổi

Hãy tưởng tượng có các trục: **phí vận chuyển**, **thuế**, **chiết khấu** và **hình thức xuất hóa đơn**. Nếu tạo lớp con cho từng tổ hợp, số lớp có thể tăng nhanh cùng số lựa chọn. Composition cho phép ghép những chiến lược độc lập với nhau.

Tuy nhiên, tổ hợp quá tự do có thể tạo cấu hình không hợp lệ. Ví dụ, một số loại thuế chỉ áp dụng cho một quốc gia. Khi đó cần một **bước kiểm tra cấu hình** hoặc một lớp điều phối bảo vệ bất biến nghiệp vụ, chứ không đơn giản lắp tùy ý mọi policy.

## 5. Khi nào kế thừa lớp là hợp lý?

Không phải mọi kế thừa đều xấu. Kế thừa có giá trị nếu:

- Có quan hệ kiểu con thực sự, có thể giải thích bằng hợp đồng và ví dụ sử dụng.
- Lớp cha cung cấp **bất biến hoặc thuật toán khung ổn định** mà mọi lớp con đều cần giữ.
- Điểm được phép thay đổi (**extension point**) nhỏ, rõ ràng và được tài liệu hóa.
- Lớp con không phải kiểm tra loại lớp cha, không phải vô hiệu hóa nhiều phương thức và không cần gọi những hàm không liên quan.
- Có test kiểm tra lớp con tiếp tục đáp ứng hợp đồng chung.
- Chi phí phụ thuộc vào lớp cha thấp hơn giá trị tái sử dụng hoặc mô hình hóa nhận được.

Một mẫu thường được dùng là **Template Method**: lớp cha giữ cố định trình tự công việc và cung cấp một số bước cho lớp con triển khai.

### Ví dụ: thuật toán khung ổn định

Giả sử một ứng dụng tạo nội dung báo cáo theo các định dạng khác nhau. Mọi báo cáo phải có tiêu đề hợp lệ, còn phần thân được xây dựng riêng.

~~~java
import java.util.Objects;

abstract class ReportRenderer {

    public final String render(String title) {
        Objects.requireNonNull(title, "title");
        if (title.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }

        String body = Objects.requireNonNull(
                renderBody(), "renderBody must not return null");

        return title + System.lineSeparator() + body;
    }

    protected abstract String renderBody();
}

final class SalesSummaryRenderer extends ReportRenderer {
    @Override
    protected String renderBody() {
        return "Doanh thu: 100";
    }
}
~~~

Phương thức **render(...)** là **final**, nên lớp con không thể bỏ qua bước kiểm tra tiêu đề hoặc thay thứ tự các bước trong thuật toán khung. Lớp con chỉ triển khai **renderBody()** và phải tuân thủ cam kết không trả null. Đây là một tình huống kế thừa có thể hợp lý nếu các báo cáo thật sự chia sẻ vòng đời như vậy.

Tuy nhiên, mẫu này vẫn tạo **hợp đồng mở rộng**. Nếu người viết lớp con cần quyền truy cập trạng thái bên trong lớp cha hoặc phải override nhiều phương thức để làm một biến thể, thiết kế đã có dấu hiệu căng thẳng. Trong trường hợp đó, có thể dùng **composition** với một thành phần sinh phần thân và một thành phần tạo vỏ báo cáo.

**Lưu ý:** Không được xem kế thừa lớp như cách duy nhất để tái sử dụng thuật toán. Một đối tượng khác hoàn toàn có thể nhận callback hoặc strategy và thực hiện trình tự tương tự. Chọn phương án nào dễ giải thích và đáp ứng nhu cầu mở rộng đã xác nhận.

## 6. Những kiểu kế thừa dễ vi phạm hợp đồng

### 6.1. Kế thừa chỉ vì muốn dùng lại một vài dòng mã

Ví dụ, một lớp **InvoiceService** kế thừa **EmailSender** chỉ để tái sử dụng hàm gửi email. Về ngữ nghĩa, InvoiceService **có sử dụng** chức năng gửi email chứ không **là một** EmailSender.

Hướng hợp lý thường là nhận **EmailSender** như một cộng tác viên. Khi cần đổi từ email sang queue hoặc dịch vụ thông báo khác, không phải thay quan hệ kiểu cha/con của InvoiceService.

### 6.2. Lớp con phải từ chối phương thức hợp lệ của lớp cha

Một lớp cha có phương thức **delete()** được hợp đồng cho phép, nhưng lớp con **ReadOnlyRepository** ghi đè để luôn ném **UnsupportedOperationException**. Nếu người gọi của kiểu cha có quyền xóa, thay bằng lớp con làm hỏng kỳ vọng.

Cách cải thiện có thể là tách interface **ReadRepository** và **WriteRepository**, hoặc cung cấp các hợp đồng phân biệt quyền đọc/ghi. Đây là ứng dụng của việc thiết kế **giao diện theo khả năng thật**.

Không phải mọi **UnsupportedOperationException** trong Java đều đương nhiên vi phạm LSP; một số API chuẩn công khai rằng thao tác là **tùy chọn**. Cần xét hợp đồng chính thức, không chỉ nhìn tên ngoại lệ. Vấn đề xuất hiện khi lớp con loại bỏ khả năng mà kiểu cha **đã cam kết**.

### 6.3. Thay ý nghĩa hoặc đơn vị kết quả

Giả sử phương thức cha **totalAmount()** trả về số tiền theo đơn vị đồng. Lớp con trả số tiền theo đơn vị nghìn đồng mà không đổi hợp đồng. Chữ ký và kiểu **BigDecimal** vẫn hợp lệ nhưng người gọi có thể tính sai.

Hợp đồng phải thể hiện **ngữ nghĩa và đơn vị**, không dừng ở kiểu dữ liệu. Tương tự, trả **null** thay vì giá trị được cam kết, hay thay đổi thứ tự trả dữ liệu khi thứ tự là một phần hợp đồng, cũng có thể gây lỗi.

### 6.4. Tăng tác dụng phụ không được báo trước

Một lớp cha có phương thức **calculate()** được cam kết chỉ tính toán, nhưng lớp con ghi vào database mỗi lần gọi. Người gọi thay đối tượng mà không biết, có thể ghi trùng dữ liệu hoặc gặp lỗi I/O ngoài dự kiến.

Nếu tác dụng phụ là cần thiết cho biến thể mới, hợp đồng và ranh giới cần được xem lại. Không nên giấu thay đổi quan trọng phía sau cơ chế override.

### 6.5. Kế thừa trạng thái mutable và phụ thuộc chi tiết nội bộ

Nếu lớp cha có các trường **protected** có thể sửa, lớp con có thể thay đổi chúng theo thứ tự khó kiểm soát. Một thay đổi nhỏ trong lớp cha làm hỏng giả định của lớp con dù mã vẫn biên dịch.

Lớp cha cung cấp quá nhiều hook khiến người bảo trì phải hiểu tương tác giữa các phương thức override, thứ tự constructor và các callback. Khi điều này xảy ra, nên cân nhắc **giảm khả năng override**, làm rõ API mở rộng hoặc chuyển sang composition.

## 7. Phân biệt interface với lớp cơ sở trừu tượng

Trong Java, **interface** và **abstract class** đều có thể tham gia vào đa hình, nhưng phạm vi trách nhiệm khác nhau.

| Tiêu chí | Interface | Abstract class |
| --- | --- | --- |
| Diễn đạt chính | Một **khả năng hoặc hợp đồng** được nhiều loại đối tượng đáp ứng | Một **họ lớp có cấu trúc hoặc thuật toán chung** |
| Kế thừa/triển khai | Một lớp có thể triển khai nhiều interface | Một lớp chỉ có một lớp cha trực tiếp |
| Trạng thái instance | Không có trường instance như lớp thông thường; trường khai báo trong interface là hằng số **public static final** | Có thể chứa trạng thái instance và constructor |
| Phương thức | Có phương thức trừu tượng, **default**, **static**, và **private** theo phiên bản Java | Có phương thức trừu tượng và phương thức có triển khai |
| Mức phụ thuộc | Thường ít buộc người dùng vào chi tiết triển khai | Có thể tạo ràng buộc sâu hơn với lớp cha |
| Đánh đổi | Hợp đồng quá lớn vẫn gây khó thay thế; default method cũng có ngữ nghĩa cần giữ | Đổi lớp cha có thể ảnh hưởng nhiều lớp con; hook và trạng thái dễ gây tương tác khó hiểu |

**Không phải cứ có interface thì thiết kế đã tốt.** Interface với hai mươi phương thức không liên quan có thể buộc từng triển khai phải hỗ trợ khả năng không cần thiết. Nên nhóm theo **vai trò và hợp đồng mà người dùng thật sự cần**, đồng thời tránh tách vụn thành hàng trăm interface chỉ có một phương thức nếu không có lý do.

Ở chiều ngược lại, **abstract class** không đồng nghĩa thiết kế xấu. Nó có thể biểu diễn một thuật toán chung ổn định hoặc chia sẻ bất biến khó giữ nhất quán nếu mọi lớp con tự làm. Quan trọng là lớp con được phép thay thế theo hợp đồng.

### Interface vẫn cần hợp đồng rõ ràng

Một giao diện có thể viết rất ngắn:

~~~java
interface PriceProvider {
    java.math.BigDecimal priceFor(String productId);
}
~~~

Nhưng người gọi cần biết thêm: **productId** rỗng có hợp lệ không, sản phẩm không tồn tại xử lý ra sao, giá trị trả về có thể âm không, có bao gồm thuế không, có I/O hay không và có thể cache không. Nếu không định nghĩa, mỗi triển khai có thể hiểu một cách; việc phụ thuộc qua interface cũng không ngăn được lỗi tương thích hành vi.

## 8. Tổ hợp và kế thừa không loại trừ nhau

Một thiết kế có thể đồng thời sử dụng:

- **Interface** để biểu diễn hợp đồng của các thành phần.
- **Composition** để lắp ghép thành phần theo nhu cầu.
- **Một số lớp cơ sở** trong khu vực hẹp, khi thuật toán chung thực sự ổn định.
- **sealed interface hoặc sealed class** (Java 17) để giới hạn tập kiểu con trong một miền nghiệp vụ khép kín.

Ví dụ, các trạng thái hoặc sự kiện nghiệp vụ có số biến thể hữu hạn có thể được mô hình hóa bằng **sealed interface**. Điều này khác mục tiêu của ShippingFeePolicy: số chiến lược phí có thể tăng theo nhu cầu, còn tập loại sự kiện có thể được kiểm soát chặt để xử lý đầy đủ.

~~~java
sealed interface PaymentOutcome
        permits PaymentAccepted, PaymentDeclined {
}

record PaymentAccepted(String transactionId)
        implements PaymentOutcome {
}

record PaymentDeclined(String reason)
        implements PaymentOutcome {
}
~~~

Kiểu **PaymentOutcome** diễn đạt hai kết quả khác loại, tránh dùng nhiều cờ boolean mơ hồ. Đối tượng sử dụng vẫn cần kiểm tra dữ liệu của từng kết quả và đảm bảo xử lý đủ biến thể. Việc **sealed** giới hạn tập kiểu con được phép không tự bảo đảm mọi triển khai đúng hợp đồng nghiệp vụ.

Một ví dụ khác là **Decorator**: một đối tượng triển khai cùng interface với đối tượng được bọc, nhưng **chứa** đối tượng đó và bổ sung một hành vi hợp lệ. Ví dụ, một repository decorator ghi metric có thể ủy quyền cho repository gốc trong khi vẫn bảo toàn hợp đồng truy vấn. Đây là sự kết hợp giữa **subtyping** và **composition**, không phải một lựa chọn chỉ có một trong hai.

## 9. Phát hiện cấu trúc phụ thuộc khó thay đổi

Các dấu hiệu cần điều tra:

| Dấu hiệu | Rủi ro | Hướng xem xét |
| --- | --- | --- |
| Lớp con phải override nhiều phương thức chỉ để ném lỗi hoặc không làm gì | Lớp con không thực sự đáp ứng hợp đồng lớp cha | Tách khả năng thành hợp đồng nhỏ hơn; xem lại quan hệ kiểu con |
| Chỉnh lớp cha làm hỏng nhiều lớp con ở các khu vực không liên quan | Coupling vào chi tiết chung quá cao | Thu hẹp API mở rộng, bảo vệ bất biến, cân nhắc composition |
| Tạo một lớp con cho mỗi tổ hợp cấu hình | Số lớp tăng theo số cách ghép lựa chọn | Tách các trục thay đổi thành policy và dùng composition |
| Một lớp chỉ kế thừa để gọi một tiện ích | Quan hệ “is-a” sai mục đích | Chuyển tiện ích thành cộng tác viên hoặc hàm phù hợp |
| Interface có nhiều phương thức không liên quan | Các triển khai phải giả vờ hỗ trợ khả năng không có | Phân chia interface theo nhu cầu người gọi |
| Mã sử dụng thường xuyên kiểm tra **instanceof** để phân nhánh theo kiểu con | Đa hình chưa diễn đạt đúng hành vi hoặc miền kiểu cần mô hình rõ hơn | Xem lại hợp đồng, dùng hành vi đa hình hoặc xử lý tổng loại có kiểm soát |
| Constructor có hàng chục cộng tác viên | Lớp có thể gánh quá nhiều trách nhiệm | Phân tích lý do thay đổi và ranh giới nghiệp vụ |
| Test phải tạo cả database/network để kiểm tra một phép tính thuần | Logic gắn vào chi tiết I/O | Cô lập phép tính và truyền phụ thuộc qua ranh giới rõ ràng |

Không phải mọi **instanceof**, constructor nhiều tham số hoặc lớp có kế thừa đều sai. Cần xem **lý do tồn tại** và hậu quả khi yêu cầu thay đổi. Một refactor chỉ giảm số lớp nhưng đẩy logic sang cấu hình động khó kiểm thử chưa chắc là cải thiện.

## 10. Lựa chọn trong từng tình huống

### Tình huống A: Hỗ trợ thêm nhà cung cấp thanh toán

Một hệ thống đã có hai cổng thanh toán, mỗi cổng dùng API riêng nhưng cùng cần thao tác tạo yêu cầu thanh toán và kiểm tra trạng thái.

Hướng thường phù hợp là xác định **PaymentGateway** với hợp đồng cụ thể, sau đó dùng **composition** để PaymentService nhận gateway. Tuy nhiên, cần làm rõ cách xử lý lỗi, timeout, idempotency, sự không chắc chắn khi mất phản hồi và trạng thái giao dịch. Hai gateway có thể có chữ ký giống nhau nhưng không thể thay thế nếu một bên tự tạo giao dịch mới khi retry còn bên kia bảo đảm idempotency.

### Tình huống B: Một thuật toán chung có ít bước tùy biến

Các dạng báo cáo có quy trình tạo vỏ ổn định nhưng khác nhau ở phần thân. Một **abstract class với final template method** có thể làm rõ bất biến và điểm tùy biến. Nếu về sau phải kết hợp nhiều định dạng, nhiều loại nguồn dữ liệu và nhiều bộ lọc, composition có thể giảm số cấp kế thừa.

### Tình huống C: Một lần cần dùng lại hàm xử lý chuỗi

Hai lớp cùng muốn chuẩn hóa mã bưu điện, nhưng không cùng thuộc một loại đối tượng. Kế thừa một lớp tiện ích để gọi phương thức xử lý chuỗi là quan hệ “is-a” không hợp lý. Có thể dùng một hàm thuần hoặc đối tượng chuyên trách có hợp đồng rõ ràng.

### Tình huống D: Mô hình hóa một tập sự kiện khép kín

Hệ thống có các sự kiện **CREATED**, **PAID**, **CANCELLED** với dữ liệu riêng từng loại. Một **sealed interface** hoặc mô hình trạng thái rõ ràng có thể thể hiện tập biến thể. Ở đây, mục tiêu là làm các trường hợp nghiệp vụ hiện diện trong hệ kiểu, không phải tái sử dụng mã giữa các lớp con bằng mọi giá.

### Tình huống E: Một lớp có nhiều “kiểu” sản phẩm bằng cờ boolean

Ví dụ một lớp chứa các cờ **express**, **international**, **fragile** và hàng loạt nhánh kiểm tra. Trước khi tạo lớp con cho mọi tổ hợp, cần xác định xem chúng là **những chiều cấu hình độc lập** hay **những phân loại loại trừ nhau**. Nếu có thể ghép độc lập, composition giữa các policy thường phù hợp; nếu loại trừ nhau và có hợp đồng riêng, mô hình kiểu hoặc enum có thể rõ hơn.

## 11. Refactor từ kế thừa khó bảo trì sang composition

Không nên đổi hàng loạt lớp cha/con chỉ vì khẩu hiệu “favor composition over inheritance”. Với hệ thống đang hoạt động, nên làm theo thứ tự:

1. **Xác định hành vi phải giữ:** liệt kê các trường hợp người dùng dựa vào, ngoại lệ, dữ liệu và tác dụng phụ được cam kết.
2. **Vẽ đồ thị lớp và quan hệ sử dụng:** ai đang gọi phương thức của lớp cha, lớp con nào override, đâu là trạng thái dùng chung.
3. **Tìm trục thay đổi thực sự:** lớp con khác nhau ở chính sách giá, nguồn dữ liệu, cách gửi thông báo hay vòng đời xử lý?
4. **Tạo hợp đồng cộng tác viên nhỏ, có ý nghĩa:** ví dụ **ShippingFeePolicy** chỉ chịu trách nhiệm tính phí cho một Basket hợp lệ.
5. **Tách triển khai riêng từ lớp con:** chuyển logic biến thể sang một policy có test. Giữ behavior cũ được bảo vệ trong giai đoạn chuyển.
6. **Truyền policy vào đối tượng điều phối:** dùng constructor hoặc cấu hình composition root, tránh tạo dependency ẩn trong phương thức.
7. **Chuyển từng người gọi, kiểm tra tương thích:** chú ý API công khai, dữ liệu lưu trữ, serialization và nơi dùng kiểu lớp cha cũ.
8. **Gỡ bỏ lớp cha/override không còn dùng:** chỉ sau khi người gọi đã chuyển và test phù hợp đạt.

Với thay đổi có ảnh hưởng lớn, có thể duy trì adapter tạm thời để hỗ trợ API cũ. Không nên xóa ngay public type nếu client ngoài vẫn phụ thuộc. Kết quả refactor cần được đo bằng **hành vi giữ nguyên**, **phạm vi sửa khi thêm biến thể** và **mức khó đọc/kiểm thử giảm**, thay vì chỉ đếm số lớp bị xóa.

## 12. Cách kiểm chứng hợp đồng thay thế

Một **contract test** có thể được dùng lại cho nhiều triển khai, miễn là kiểm tra **cam kết chung**. Với các policy tính phí, những điều có thể kiểm tra gồm:

- Với mọi Basket hợp lệ, phương thức trả giá trị không null và không âm.
- Khi gọi cùng một Basket nhiều lần, kết quả ổn định nếu hợp đồng hứa tính toán thuần, bất biến.
- Một policy không thay đổi Basket hoặc hệ thống ngoài, nếu đó là cam kết.
- Đầu vào không hợp lệ được loại bỏ theo quy tắc đã công bố.
- Các chính sách cụ thể có test riêng cho ngưỡng, mức phí và trường hợp biên.

Không nên viết contract test buộc **mọi policy trả cùng một số tiền**; như vậy là đánh đồng tính thay thế với tính đồng nhất kết quả.

Cũng không nên xem số test xanh là bằng chứng hoàn chỉnh về LSP. Một triển khai có thể trả đúng giá trị trong test nhưng vẫn vi phạm hợp đồng ở trường hợp thời gian, tác dụng phụ, trạng thái chia sẻ hay dữ liệu chưa bao phủ. Code review và test tích hợp vẫn có vai trò, đặc biệt với dependency I/O.

### Cần xem xét cả lỗi và vận hành

Nếu một interface dùng cho dịch vụ mạng, hợp đồng có thể cần:
- Thời gian chờ hoặc cách nhận **deadline** từ phía gọi.
- Ý nghĩa của timeout: có thể thao tác phía xa đã được thực hiện hay chưa.
- Loại lỗi có thể retry, cách chống lặp tác dụng phụ.
- Cách hủy lời gọi và giải phóng tài nguyên.
- Tính an toàn khi gọi đồng thời.

Đây là những phần của **hợp đồng hành vi** có thể làm hỏng tính thay thế dù chữ ký Java tương thích. Không phải mọi interface đều cần các yêu cầu này; chỉ thêm khi bối cảnh sử dụng thực sự đòi hỏi.

## 13. Những đánh đổi cần cân nhắc

| Tiêu chí | Khi composition thường có lợi | Khi kế thừa có thể có lợi | Điều phải kiểm tra |
| --- | --- | --- | --- |
| **Khả năng thay đổi** | Nhiều trục hành vi thay thế độc lập | Một họ lớp có thuật toán khung ổn định | Phạm vi sửa khi thêm biến thể |
| **Khả năng hiểu** | Trách nhiệm của cộng tác viên được đặt tên rõ | Quan hệ phân loại rõ, không nhiều override | Người đọc phải mở bao nhiêu lớp để hiểu luồng? |
| **Tái sử dụng** | Tái sử dụng khả năng qua ủy quyền | Tái sử dụng triển khai và bất biến chung | Có đang tái sử dụng đúng cùng một tri thức không? |
| **Kiểm thử** | Có thể thay cộng tác viên bằng triển khai có kiểm soát | Có thể chạy contract test trên các lớp con | Test có kiểm tra đúng hợp đồng và trường hợp biên? |
| **Coupling** | Người dùng chỉ phụ thuộc API cộng tác viên | Lớp con có thể phụ thuộc vào cấu trúc lớp cha | Có phải sửa nhiều nơi khi lớp cha đổi? |
| **Số thành phần** | Có thể tăng lớp policy và việc cấu hình ghép | Có thể tạo nhiều lớp con qua các tổ hợp | Số lớp có tương xứng với trách nhiệm thực không? |
| **An toàn hợp đồng** | Policy khác nhau vẫn có thể phá hợp đồng interface | Lớp con cũng có thể phá hợp đồng lớp cha | Có tài liệu và test thay thế hay không? |

**Không có chiến lược luôn tốt hơn trong mọi hoàn cảnh.** Composition giảm phụ thuộc kế thừa, nhưng nếu tạo quá nhiều lớp nhỏ chỉ chuyển tiếp, mã sẽ khó theo dõi. Kế thừa giảm một số lặp triển khai, nhưng nếu lớp cha không ổn định hoặc điểm mở rộng không rõ, lớp con dễ hỏng theo. Quyết định cần dựa trên **hợp đồng, lý do thay đổi và rủi ro thực tế**.

## 14. Tình huống thực hành: hệ thống thông báo

Một ứng dụng có các yêu cầu sau:

- Gửi thông báo bằng email hoặc SMS.
- Trước khi gửi, kiểm tra nội dung không rỗng.
- Một số kênh có quota và cơ chế retry riêng.
- Hệ thống có thể bổ sung push notification sau này.
- Đội ngũ hiện đề xuất cho **EmailNotificationService** và **SmsNotificationService** cùng kế thừa **AbstractNotificationService**, lớp cha vừa kiểm tra nội dung, vừa truy cập database và tự retry mọi lỗi.

Hãy phân tích:

1. **Thành phần hợp đồng chung** của hành động “gửi thông báo” là gì? Thành công có ý nghĩa “đã bàn giao cho nhà cung cấp” hay “người dùng đã nhận được”?
2. Những bước nào thuộc **nghiệp vụ điều phối chung**, những bước nào phụ thuộc **kênh gửi**?
3. Vì sao để lớp cha retry mọi lỗi có thể gây sai, nhất là khi gửi lại tạo tác dụng phụ?
4. Thành phần nào nên làm việc qua interface; phần nào có thể dùng composition?
5. Khi nào một lớp cơ sở **Template Method** vẫn có thể hợp lý?
6. Bạn cần những test nào để xác nhận hai kênh đáp ứng hợp đồng chung?

### Hướng giải quyết

Có thể có một **NotificationService** điều phối xác thực đầu vào và chính sách nghiệp vụ, nhận một **NotificationSender** tương ứng với kênh. Các implementation **EmailSender** và **SmsSender** chịu trách nhiệm tích hợp nhà cung cấp; cấu hình timeout, quota và retry được xét theo từng kênh, đồng thời tuân thủ yêu cầu chung về trạng thái, chống lặp và quan sát hệ thống.

Nếu một luồng gửi chung thật sự ổn định và các kênh chỉ cần triển khai một bước gửi nhỏ, lớp cơ sở có phương thức **final** cũng có thể hợp lý. Nhưng việc bắt buộc mọi kênh chia sẻ một cơ chế retry không đúng với hợp đồng sẽ tạo rủi ro. Ví dụ, sau timeout phía nhà cung cấp có thể đã nhận tin; gửi lại không kiểm soát có thể gây thông báo trùng.

Contract test có thể xác nhận dữ liệu không hợp lệ bị từ chối, trạng thái gửi có ngữ nghĩa thống nhất, các lỗi được biểu diễn rõ và không có bí mật xuất hiện trong log. Integration test kiểm tra cách chuyển dữ liệu, timeout và phản hồi từ từng nhà cung cấp.

## 15. Bài tập tự luyện

### Bài tập 1 — Nhận diện quan hệ

Với từng quan hệ sau, hãy chọn **composition**, **inheritance** hoặc **interface + composition**, và giải thích vì sao:

1. **OrderService** sử dụng **OrderRepository**.
2. **PdfReport** là một dạng **Report** nhưng cần hành vi xuất file riêng.
3. **PaymentService** cần thay đổi nhà cung cấp thanh toán theo cấu hình.
4. **EmailService** muốn tái sử dụng một hàm chuẩn hóa địa chỉ email.
5. **CacheRepository** bọc một repository khác để đọc từ cache trước.

*Gợi ý:* (1) thường là composition; (3) và (5) thường dùng interface kết hợp composition; (4) không phải quan hệ “is-a”. (2) chỉ nên chọn kế thừa khi lớp Report có hợp đồng chung ổn định và PdfReport đáp ứng được, nếu không có thể dùng một report renderer.

### Bài tập 2 — Phát hiện vi phạm hợp đồng

Một interface có hợp đồng: “Hàm **findById(id)** trả **Optional.empty()** nếu không tìm thấy; không bao giờ trả null; mọi ID hợp lệ đều được tra cứu”. Một triển khai mới trả **null** khi không tìm thấy, và từ chối mọi ID bắt đầu bằng ký tự **X** dù đó là ID hợp lệ.

Hãy chỉ ra:
- Vi phạm hậu điều kiện nào?
- Vi phạm tiền điều kiện nào?
- Vì sao người gọi đang hoạt động đúng với kiểu cha có thể bị lỗi?
- Cần viết test nào bảo vệ hợp đồng chung?

*Gợi ý:* Trả null làm yếu bảo đảm kết quả; từ chối ID hợp lệ là siết tiền điều kiện. Test nên bao phủ một ID tồn tại, một ID không tồn tại và một ID bắt đầu bằng X theo hợp đồng.

### Bài tập 3 — Chọn thiết kế có thể mở rộng

Một ứng dụng có 3 loại khách hàng, 4 loại phí vận chuyển và 2 cách gửi thông báo. Có đề xuất tạo lớp con của **OrderProcessor** cho từng tổ hợp.

Hãy tính số tổ hợp lý thuyết nếu các trục độc lập và không có ràng buộc bổ sung. Sau đó mô tả cách composition có thể tách những trục biến đổi. Bạn sẽ đặt bước kiểm tra ở đâu nếu có tổ hợp bị nghiệp vụ cấm?

*Gợi ý:* Có thể có **3 × 4 × 2 = 24** tổ hợp. Composition cho phép phối hợp chính sách theo vai trò thay vì tạo một lớp con cho mỗi tổ hợp. Nếu một số tổ hợp không hợp lệ, cần nơi kiểm tra cấu hình và quy tắc nghiệp vụ rõ ràng.

### Bài tập 4 — Review một lớp cơ sở

Bạn thấy **AbstractPaymentProcessor** có 25 phương thức **protected**, 15 trường thay đổi được và được kế thừa bởi 12 lớp. Đổi thứ tự gọi một phương thức trong lớp cha làm hỏng ba lớp con.

Hãy viết nhận xét review cụ thể về:
- Các bất biến và điểm mở rộng cần xác định.
- Cách kiểm tra các lớp con có phụ thuộc vào chi tiết nội bộ hay không.
- Phần nào có thể trích xuất thành đối tượng cộng tác.
- Cách thử chuyển đổi từng bước mà không làm hỏng hành vi thanh toán.

*Gợi ý:* Bắt đầu bằng hợp đồng và test trước khi sửa cây kế thừa. Xem mối phụ thuộc nào xuất phát từ trạng thái mutable và thứ tự callback; thay đổi theo các bước nhỏ, giữ tương thích ở ranh giới công khai.

## Ghi nhớ

**Composition** ghép hành vi bằng các đối tượng cộng tác, giúp các trách nhiệm thay đổi độc lập và phụ thuộc rõ ràng. **Inheritance** phù hợp khi tồn tại quan hệ kiểu con thật và lớp cha cung cấp hợp đồng hoặc thuật toán chung ổn định. Dù dùng **extends** hay **implements**, một triển khai chỉ có thể thay thế kiểu cha khi **giữ đúng hợp đồng hành vi** về đầu vào, kết quả, bất biến, lỗi và tác dụng phụ. Chọn cấu trúc tốt nghĩa là làm giảm sự phụ thuộc không cần thiết, giúp người đọc dự đoán được hành vi và cho phép thay đổi một phần hệ thống mà ít làm hỏng những phần còn lại.
