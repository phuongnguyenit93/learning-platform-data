# Chính sách nghiệp vụ được tiêm qua giao diện khi cần thay đổi cách tính

Trong Domain-Driven Design (DDD), có những phép tính hoặc quyết định nghiệp vụ không thuộc tự nhiên về một Entity hay Value Object cụ thể. Khi quy tắc đó cần phối hợp dữ liệu từ nhiều đối tượng, ta có thể đặt nó trong **Domain Service**. Nếu cách tính có nhiều biến thể theo hợp đồng, phân khúc khách hàng, thị trường hoặc thời điểm, Domain Service có thể phụ thuộc vào một **giao diện chính sách nghiệp vụ (Policy interface)** và nhận implementation phù hợp thông qua dependency injection.

Cách thiết kế này giúp mô hình diễn đạt rõ điều cần tính, trong khi từng chính sách cung cấp cách tính cụ thể. Ví dụ, cùng một yêu cầu tính chiết khấu có thể áp dụng chính sách theo sản lượng, theo hạng khách hàng hoặc theo hợp đồng. Domain Service sử dụng hợp đồng `DiscountPolicy`; implementation có thể thay đổi theo ngữ cảnh mà không phải viết lại toàn bộ quy trình định giá.

Không phải phép tính nào cũng cần interface hay Domain Service. Nếu quy tắc đơn giản, ổn định và thuộc rõ về một Entity hoặc Value Object, hãy đặt hành vi ngay tại đó. Chỉ tách policy khi có sự thay đổi thực sự trong quy tắc hoặc khi việc tách giúp mô hình rõ trách nhiệm hơn.

## 1. Vì sao chính sách nghiệp vụ có thể cần thay đổi?

Một doanh nghiệp có thể áp dụng nhiều cách tính cho cùng một loại quyết định:

- Khách hàng mua theo hợp đồng được hưởng mức chiết khấu riêng.
- Khách hàng mua số lượng lớn được giảm giá theo bậc.
- Thị trường khác nhau có cách tính phí vận chuyển khác nhau.
- Một chương trình khuyến mại chỉ có hiệu lực trong một khoảng thời gian.
- Hạn mức tín dụng được đánh giá theo chính sách khác nhau cho từng nhóm khách hàng.

Nếu viết tất cả điều kiện vào một phương thức lớn, mã nguồn có thể dần trở thành chuỗi `if/else` dựa trên loại khách hàng, mã thị trường, ngày áp dụng và loại hợp đồng. Mỗi thay đổi chính sách buộc nhóm phải sửa cùng một đoạn mã, làm tăng nguy cơ ảnh hưởng nhầm đến những trường hợp khác.

Ví dụ, một phương thức định giá có thể bắt đầu như sau:

```java
if (customer.isEnterprise()) {
    discount = subtotal.multiply(new BigDecimal("0.12"));
} else if (quantity >= 10) {
    discount = subtotal.multiply(new BigDecimal("0.08"));
} else if (isPromotionActive(date)) {
    discount = subtotal.multiply(new BigDecimal("0.05"));
}
```

Đoạn mã nhỏ này chưa thể hiện thứ tự ưu tiên, khả năng kết hợp chính sách, thời hạn hợp đồng hoặc trường hợp một khách hàng vừa thuộc nhóm doanh nghiệp vừa đủ điều kiện mua số lượng lớn. Khi số lượng quy tắc tăng lên, trách nhiệm tính giá và trách nhiệm chọn chính sách dễ bị trộn lẫn.

Tách chính sách qua giao diện giúp biểu diễn rõ hai câu hỏi khác nhau:

1. **Cần tính điều gì?** Ví dụ, tính số tiền chiết khấu hợp lệ cho đơn hàng.
2. **Dùng quy tắc nào để tính?** Ví dụ, chính sách theo sản lượng hay chính sách theo hợp đồng.

## 2. Policy là khái niệm nghiệp vụ, không chỉ là một mẫu thiết kế

Policy mô tả một quy tắc hoặc cách ra quyết định trong miền nghiệp vụ. Nó có thể quyết định một hành động được phép hay không, chọn phương án nào hoặc tính ra một giá trị.

Ví dụ:

| Policy | Đầu vào | Kết quả |
| --- | --- | --- |
| `DiscountPolicy` | Tổng tiền, số lượng, thông tin hợp đồng | Mức chiết khấu |
| `ShippingFeePolicy` | Khối lượng, khu vực giao, phương thức vận chuyển | Phí vận chuyển |
| `CreditApprovalPolicy` | Hạn mức, dư nợ, số tiền yêu cầu | Chấp thuận hoặc từ chối |
| `ReturnEligibilityPolicy` | Ngày mua, trạng thái giao, loại sản phẩm | Có đủ điều kiện trả hàng hay không |

Giao diện policy nên dùng ngôn ngữ nghiệp vụ và mô tả rõ hợp đồng đầu vào/đầu ra. `DiscountPolicy` có ý nghĩa hơn một interface kỹ thuật chung như `Calculator` hoặc `Strategy`, vì người đọc hiểu ngay chính sách nào đang được áp dụng.

Policy có thể được hiện thực bằng một lớp, một hàm thuần hoặc một thành phần cấu hình. Điều quan trọng là trách nhiệm và quy tắc của nó được xác định rõ. Không nên tạo interface chỉ để đổi tên một phép toán đơn giản mà không có khả năng biến thể hoặc nhu cầu thay thế.

## 3. Khi nào nên tách Domain Service và Policy?

Một hành vi phù hợp với Entity khi nó chủ yếu thay đổi hoặc bảo vệ trạng thái của chính Entity đó. Một phép toán phù hợp với Value Object khi nó thuộc ý nghĩa của giá trị, như cộng hai `Money` cùng loại tiền hoặc kiểm tra hai `DateRange` có giao nhau không.

Domain Service phù hợp khi quy tắc nghiệp vụ:

- Phối hợp nhiều Entity hoặc Value Object.
- Không có một đối tượng nào tự nhiên sở hữu toàn bộ hành vi.
- Cần diễn đạt một quyết định hoặc phép tính ở cấp miền.
- Có thể giữ trạng thái không cần thiết ở mức tối thiểu, thường là stateless.

Policy interface hữu ích khi phần quy tắc cụ thể có thể thay đổi độc lập với Domain Service. Ví dụ, `OrderPricingService` điều phối việc tính tổng tiền, còn `DiscountPolicy` xác định khoản giảm giá theo chính sách đang áp dụng.

Không nên đưa mọi logic vào Domain Service. Nếu `Order` có quy tắc “không thể thêm dòng hàng sau khi xác nhận”, đó là hành vi của `Order`, không cần một `OrderPolicyService` chỉ để gọi lại một điều kiện đơn giản.

## 4. Thiết kế giao diện Policy bằng ngôn ngữ miền

Giả sử hệ thống cần tính chiết khấu cho một đơn hàng. Ta xác định rõ dữ liệu cần thiết để áp dụng chính sách:

```java
public record PricingFacts(
    Money subtotal,
    int totalQuantity,
    CustomerTier customerTier,
    LocalDate pricingDate
) {
    public PricingFacts {
        Objects.requireNonNull(subtotal);
        Objects.requireNonNull(customerTier);
        Objects.requireNonNull(pricingDate);
        if (totalQuantity < 0) {
            throw new IllegalArgumentException("totalQuantity cannot be negative");
        }
    }
}
```

`PricingFacts` là dữ kiện miền được chuẩn bị từ đơn hàng và thông tin khách hàng. Giao diện policy có thể được định nghĩa như sau:

```java
public interface DiscountPolicy {
    Money calculateDiscount(PricingFacts facts);
}
```

Giao diện thể hiện một hợp đồng đơn giản: nhận dữ kiện định giá và trả về khoản chiết khấu. Các implementation cần tuân thủ cùng quy tắc về loại tiền, miền giá trị và cách làm tròn đã thống nhất.

Một hợp đồng tốt cần trả lời:

- Đầu vào nào bắt buộc và được hiểu theo đơn vị nào?
- Kết quả có thể âm hoặc lớn hơn tổng tiền không?
- Nếu không đủ điều kiện, trả về 0 hay từ chối phép tính?
- Loại tiền tệ của kết quả được xác định thế nào?
- Ngày áp dụng là ngày tạo đơn, ngày xác nhận hay ngày giao dịch?
- Có cần biết phiên bản chính sách để giải thích kết quả về sau không?

Các câu hỏi này là một phần của thiết kế nghiệp vụ. Nếu hợp đồng mơ hồ, các implementation có thể trả về kết quả khác nhau dù cùng triển khai một interface.

## 5. Các implementation cho cùng một Policy

Ta có thể tạo nhiều chính sách chiết khấu với cùng hợp đồng.

**Chính sách theo sản lượng:**

```java
public final class VolumeDiscountPolicy implements DiscountPolicy {
    private final int minimumQuantity;
    private final BigDecimal discountRate;

    public VolumeDiscountPolicy(int minimumQuantity, BigDecimal discountRate) {
        if (minimumQuantity <= 0) {
            throw new IllegalArgumentException("minimumQuantity must be positive");
        }
        if (discountRate.signum() < 0 || discountRate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("discountRate must be between 0 and 1");
        }
        this.minimumQuantity = minimumQuantity;
        this.discountRate = discountRate;
    }

    @Override
    public Money calculateDiscount(PricingFacts facts) {
        if (facts.totalQuantity() < minimumQuantity) {
            return Money.zero(facts.subtotal().currency());
        }
        return facts.subtotal().multiply(discountRate);
    }
}
```

**Chính sách theo hạng khách hàng:**

```java
public final class CustomerTierDiscountPolicy implements DiscountPolicy {
    @Override
    public Money calculateDiscount(PricingFacts facts) {
        BigDecimal rate = switch (facts.customerTier()) {
            case STANDARD -> new BigDecimal("0.00");
            case SILVER -> new BigDecimal("0.03");
            case GOLD -> new BigDecimal("0.07");
            case PLATINUM -> new BigDecimal("0.10");
        };
        return facts.subtotal().multiply(rate);
    }
}
```

Hai implementation cùng nhận `PricingFacts` và trả về `Money`, nhưng cách tính khác nhau. Các con số trong ví dụ chỉ minh họa; mức giảm thực tế phải lấy từ chính sách doanh nghiệp đã được xác nhận.

Các lớp trên nên giữ tính bất biến: tham số chính sách được truyền vào constructor và không thay đổi trong lúc tính. Nếu mức chiết khấu có thể thay đổi theo thời gian, cần xác định chính sách nào có hiệu lực cho giao dịch và lưu thông tin cần thiết để giải thích hoặc tái hiện kết quả.

## 6. Tiêm Policy vào Domain Service

Domain Service có thể nhận interface policy qua constructor. Nó phối hợp dữ kiện và kiểm tra kết quả theo hợp đồng miền:

```java
public record PricingResult(
    Money subtotal,
    Money discount,
    Money total
) {}

public final class OrderPricingService {
    private final DiscountPolicy discountPolicy;

    public OrderPricingService(DiscountPolicy discountPolicy) {
        this.discountPolicy = Objects.requireNonNull(discountPolicy);
    }

    public PricingResult calculate(PricingFacts facts) {
        Money discount = discountPolicy.calculateDiscount(facts);

        if (!discount.currency().equals(facts.subtotal().currency())) {
            throw new InvalidDiscountCurrency();
        }
        if (discount.isNegative() || discount.compareTo(facts.subtotal()) > 0) {
            throw new InvalidDiscountAmount();
        }

        Money total = facts.subtotal().subtract(discount);
        return new PricingResult(facts.subtotal(), discount, total);
    }
}
```

Trong ví dụ, `Money` là Value Object đã có các phép toán và so sánh phù hợp. `OrderPricingService` không cần biết công thức cụ thể của từng loại chiết khấu. Nó chỉ phụ thuộc vào hợp đồng `DiscountPolicy` và bảo đảm kết quả phù hợp với tổng tiền của đơn.

Việc kiểm tra kết quả tại Domain Service là cần thiết nếu giới hạn “chiết khấu phải nằm trong khoảng từ 0 đến tổng tiền” là bất biến chung cho mọi policy. Nếu một implementation trả kết quả sai, dịch vụ có thể từ chối trước khi kết quả được sử dụng.

## 7. Dependency Injection và nơi cấu hình implementation

Dependency Injection (DI) cung cấp implementation cụ thể cho nơi cần dùng interface. Domain Service không tự tạo implementation bằng `new` và không phụ thuộc trực tiếp vào một lớp cụ thể.

Ví dụ với Spring:

```java
@Configuration
public class PricingConfiguration {
    @Bean
    DiscountPolicy discountPolicy() {
        return new VolumeDiscountPolicy(
            10,
            new BigDecimal("0.08")
        );
    }

    @Bean
    OrderPricingService orderPricingService(DiscountPolicy policy) {
        return new OrderPricingService(policy);
    }
}
```

Khi doanh nghiệp thay đổi cách tính mặc định, composition root có thể cung cấp implementation khác hoặc tham số cấu hình mới. Domain Service vẫn giữ nguyên hợp đồng và luồng tính toán.

DI không bắt buộc phải dùng Spring. Có thể tạo object graph thủ công ở composition root:

```java
DiscountPolicy policy = new VolumeDiscountPolicy(
    10,
    new BigDecimal("0.08")
);
OrderPricingService pricingService = new OrderPricingService(policy);
```

Điểm cốt lõi là dependency được cung cấp từ bên ngoài và được khai báo rõ qua constructor. Không nên để Entity hoặc Value Object tự gọi Spring container để lấy bean; cách đó làm mô hình miền phụ thuộc vào framework và che giấu các dependency.

## 8. Khi policy thay đổi theo từng giao dịch

Tiêm một implementation trực tiếp vào Domain Service phù hợp khi một ứng dụng, một tenant hoặc một phạm vi triển khai sử dụng một chính sách trong một khoảng thời gian. Nhưng có trường hợp mỗi đơn hàng cần một policy khác nhau theo hợp đồng, thị trường hoặc ngày áp dụng.

Khi đó, cần tách hai quyết định:

1. **Chọn policy nào cho giao dịch?** Dựa trên hợp đồng, phân khúc, thị trường và thời hạn hiệu lực.
2. **Policy đó tính ra kết quả gì?** Áp dụng thuật toán cụ thể lên dữ kiện định giá.

Có thể định nghĩa một cổng lựa chọn policy:

```java
public interface DiscountPolicyResolver {
    DiscountPolicy resolve(PricingFacts facts);
}
```

Domain Service có thể nhận resolver thay vì một policy cố định:

```java
public final class OrderPricingService {
    private final DiscountPolicyResolver policyResolver;

    public OrderPricingService(DiscountPolicyResolver policyResolver) {
        this.policyResolver = Objects.requireNonNull(policyResolver);
    }

    public PricingResult calculate(PricingFacts facts) {
        DiscountPolicy policy = policyResolver.resolve(facts);
        Money discount = policy.calculateDiscount(facts);
        // Kiểm tra kết quả chung và tính tổng tiền như ví dụ trước.
        return buildResult(facts.subtotal(), discount);
    }
}
```

`DiscountPolicyResolver` là một hợp đồng miền nếu việc lựa chọn policy là một quyết định nghiệp vụ. Implementation có thể sử dụng cấu hình hoặc dữ liệu đã được nạp để xác định policy. Nếu việc chọn chỉ là wiring kỹ thuật cho từng môi trường, có thể thực hiện tại composition root hoặc application layer mà không cần thêm một abstraction miền.

Tránh để resolver trở thành một service locator tổng quát. Nó nên có một trách nhiệm rõ: chọn chính sách chiết khấu có hiệu lực cho dữ kiện định giá cụ thể. Nếu cần truy cập repository, nên tách phần nạp dữ liệu khỏi phần tính toán để các quy tắc miền vẫn dễ kiểm thử.

## 9. Chính sách có hiệu lực theo thời gian

Một chính sách có thể thay đổi nhưng kết quả của giao dịch cũ vẫn cần giải thích được. Ví dụ, đơn tạo ngày 10 tháng 3 được áp dụng chiết khấu 8%; đến ngày 1 tháng 4 doanh nghiệp thay đổi mức giảm thành 6%. Nếu hệ thống chỉ lưu tổng tiền mà không lưu chính sách hoặc phiên bản đã áp dụng, việc đối soát có thể khó khăn.

Khi policy có hiệu lực theo thời gian, cần xác định:

- Ngày nào quyết định hiệu lực: ngày báo giá, ngày đặt hàng, ngày xác nhận hay ngày thanh toán?
- Khoảng hiệu lực có bao gồm ngày bắt đầu và ngày kết thúc không?
- Khi hợp đồng thay đổi giữa quy trình, giao dịch đang xử lý có giữ policy cũ không?
- Có cần lưu `policyId`, phiên bản, mức áp dụng hoặc kết quả chi tiết không?
- Giao dịch đã xác nhận có được tính lại theo chính sách mới không?

Đây là quy tắc nghiệp vụ, không chỉ là chi tiết cấu hình. Policy cần nhận ngày áp dụng rõ ràng thay vì tự gọi đồng hồ hệ thống ở nhiều nơi. Truyền `pricingDate` vào `PricingFacts` giúp phép tính xác định và có thể kiểm thử.

Nếu cần tái hiện kết quả cũ, có thể lưu snapshot các dữ kiện và phiên bản policy đã dùng. Không nên chỉ lưu tên lớp Java vì tên implementation có thể thay đổi khi refactor hoặc triển khai phiên bản mới.

## 10. Giữ Policy độc lập với hạ tầng

Implementation của policy thường là logic miền thuần túy: nhận dữ kiện và trả quyết định hoặc giá trị. Nó không nên tự mở kết nối database, gọi HTTP, đọc biến môi trường hay lấy thời gian hiện tại nếu những dependency đó có thể được truyền vào một cách rõ ràng.

Ví dụ, nếu chính sách chiết khấu cần tỷ giá, application service hoặc một domain service phù hợp có thể lấy `ExchangeRate` từ cổng tỷ giá rồi đưa vào dữ kiện. Policy tính toán dựa trên tỷ giá đã xác định. Như vậy, cùng một đầu vào tạo ra cùng một kết quả và kiểm thử không cần phụ thuộc mạng.

Nếu chính sách cần một quyết định từ bên ngoài như kết quả thẩm định tín dụng của đối tác, hãy phân biệt:

- Quy tắc nghiệp vụ nội bộ do Domain Service hoặc Policy thực hiện.
- Giao tiếp với đối tác do adapter/hạ tầng thực hiện.
- Quyết định hoặc dữ kiện nhận được được chuyển thành kiểu miền trước khi tiếp tục xử lý.

Không để một lớp policy vừa tính chiết khấu, vừa truy vấn khách hàng, vừa gọi dịch vụ vận chuyển và vừa ghi database. Điều đó làm khó xác định trách nhiệm và khó kiểm thử từng quy tắc.

## 11. Kiểm thử Policy và Domain Service

Vì policy được tách qua interface, có thể kiểm thử từng implementation độc lập và kiểm thử Domain Service bằng một policy giả (stub hoặc fake).

Ví dụ kiểm thử chính sách theo sản lượng:

```java
class VolumeDiscountPolicyTest {
    private final DiscountPolicy policy = new VolumeDiscountPolicy(
        10,
        new BigDecimal("0.08")
    );

    @Test
    void appliesDiscountWhenQuantityReachesThreshold() {
        PricingFacts facts = new PricingFacts(
            Money.usd("1000.00"),
            10,
            CustomerTier.STANDARD,
            LocalDate.parse("2026-03-10")
        );

        Money discount = policy.calculateDiscount(facts);

        assertEquals(Money.usd("80.00"), discount);
    }

    @Test
    void returnsZeroBelowThreshold() {
        PricingFacts facts = new PricingFacts(
            Money.usd("1000.00"),
            9,
            CustomerTier.STANDARD,
            LocalDate.parse("2026-03-10")
        );

        Money discount = policy.calculateDiscount(facts);

        assertEquals(Money.usd("0.00"), discount);
    }
}
```

Ví dụ giả định `Money.usd()` là factory method của Value Object `Money`. Trong dự án thực tế, hãy dùng API tạo tiền đang có và thống nhất scale/rounding trong equality.

Đối với `OrderPricingService`, có thể dùng một fake policy để xác nhận dịch vụ sử dụng đúng kết quả và từ chối khoản chiết khấu sai loại tiền hoặc vượt tổng tiền. Với resolver, kiểm thử các trường hợp chọn policy theo hạng khách hàng, hợp đồng và ngày hiệu lực.

Nên kiểm thử cả ranh giới:

- Ngay dưới, đúng tại và ngay trên ngưỡng sản lượng.
- Ngày bắt đầu và kết thúc hiệu lực.
- Khách hàng thuộc nhiều điều kiện cùng lúc và thứ tự ưu tiên.
- Chiết khấu bằng 0 hoặc bằng toàn bộ tổng tiền nếu nghiệp vụ cho phép.
- Policy trả về loại tiền không phù hợp.
- Không tìm thấy policy áp dụng cho giao dịch.
- Hai phiên bản policy không làm thay đổi kết quả của giao dịch đã được chốt.

## 12. Những lỗi thường gặp khi tiêm Policy

**Tạo interface cho mọi phép tính.** Một công thức ổn định và đơn giản có thể nằm trực tiếp trong Value Object hoặc Domain Service. Abstraction không có lợi ích rõ ràng sẽ làm tăng số lớp và điểm điều hướng.

**Để Domain Service phụ thuộc implementation cụ thể.** Khi gọi `new VolumeDiscountPolicy()` bên trong service, việc thay đổi hoặc kiểm thử policy trở nên khó hơn. Hãy nhận interface qua constructor khi cần biến thể.

**Dùng tên kỹ thuật thay cho ngôn ngữ miền.** `CalculatorStrategy` không cho biết quy tắc nào đang được áp dụng. Hãy đặt tên như `DiscountPolicy`, `CreditApprovalPolicy` hoặc `ShippingFeePolicy`.

**Đưa quá nhiều nhánh vào một implementation.** Nếu một policy lại chứa nhiều điều kiện không liên quan, việc tách interface chưa giải quyết được sự phức tạp. Hãy xác định các quy tắc thực sự độc lập và cách chúng kết hợp.

**Để policy tự truy cập hạ tầng.** Repository, HTTP client hoặc đồng hồ hệ thống ẩn bên trong policy làm cho phép tính khó lặp lại. Hãy truyền dữ kiện cần thiết hoặc tách cổng tích hợp.

**Chọn policy ở sai tầng.** Nếu lựa chọn policy là quy tắc nghiệp vụ, đừng giấu nó trong cấu hình Spring hoặc controller. Nếu lựa chọn chỉ là cấu hình triển khai, không cần biến nó thành một Domain Service phức tạp.

**Không xác định phiên bản và thời điểm hiệu lực.** Kết quả định giá có thể không tái hiện được sau khi chính sách thay đổi. Hãy lưu thông tin cần thiết theo yêu cầu nghiệp vụ và kiểm toán.

**Cho policy thay đổi trạng thái của Entity.** Một policy tính toán hoặc ra quyết định nên trả kết quả rõ ràng. Việc cập nhật Aggregate nên được thực hiện qua hành vi của Root hoặc quy trình ứng dụng phù hợp.

## 13. Khi nào nên dùng, khi nào chưa cần?

| Tình huống | Cách tiếp cận phù hợp |
| --- | --- |
| Công thức ổn định, thuộc một Value Object | Đặt phép toán trong Value Object |
| Quy tắc chỉ liên quan đến trạng thái của một Entity | Đặt hành vi trong Entity/Aggregate Root |
| Phép tính phối hợp nhiều đối tượng, không có chủ sở hữu tự nhiên | Dùng Domain Service |
| Cùng một quyết định có nhiều cách tính thay thế | Tách Policy interface và inject implementation |
| Policy thay đổi theo hợp đồng, thị trường hoặc thời gian | Dùng resolver/provider nếu việc lựa chọn là quy tắc nghiệp vụ |
| Khác biệt chỉ là tham số như tỷ lệ hoặc ngưỡng | Có thể dùng cấu hình có kiểu và phiên bản thay vì tạo nhiều class |
| Logic chỉ là định dạng hoặc chuyển đổi kỹ thuật | Đặt ở adapter/application/infrastructure phù hợp |

Một tiêu chí thực tế là khả năng thay đổi độc lập. Nếu thay đổi cách tính thường xuyên nhưng luồng điều phối vẫn ổn định, policy interface có thể tạo ranh giới tốt. Nếu cả quy tắc lẫn luồng luôn thay đổi cùng nhau, việc tách riêng có thể không đem lại nhiều lợi ích.

## 14. Quy trình áp dụng Policy qua giao diện

Có thể triển khai theo các bước:

1. **Khám phá quyết định nghiệp vụ:** hỏi chuyên gia quy tắc nào đang được dùng và những trường hợp nào có cách tính khác.
2. **Xác định phần ổn định:** tìm đầu vào, đầu ra và trách nhiệm chung của mọi biến thể.
3. **Đặt tên theo miền:** chọn tên interface thể hiện chính sách như `DiscountPolicy`.
4. **Thiết kế dữ kiện đầu vào:** dùng Entity/Value Object có kiểu rõ ràng; đưa thời điểm và đơn vị vào hợp đồng khi cần.
5. **Tạo implementation:** mỗi implementation thực hiện một quy tắc có ý nghĩa, có thể kiểm thử độc lập.
6. **Tiêm dependency:** cung cấp implementation qua constructor hoặc composition root; không để mô hình miền tự tìm bean.
7. **Xác định cách chọn:** nếu policy thay đổi theo từng giao dịch, định nghĩa cơ chế resolver có trách nhiệm rõ ràng.
8. **Kiểm tra kết quả chung:** bảo vệ các giới hạn áp dụng cho mọi policy tại Domain Service hoặc Value Object thích hợp.
9. **Quản lý hiệu lực:** xác định ngày áp dụng, phiên bản và dữ kiện cần lưu để giải thích kết quả.
10. **Kiểm thử các biến thể:** kiểm tra ngưỡng, ngoại lệ, ưu tiên, kết quả không hợp lệ và trường hợp không có policy.

## 15. Checklist thiết kế

Trước khi đưa policy vào mô hình, hãy tự hỏi:

- Đây có phải là một quy tắc nghiệp vụ mà chuyên gia có thể gọi tên không?
- Có thực sự nhiều cách tính hoặc khả năng thay đổi độc lập không?
- Hành vi có thuộc tự nhiên về Entity hay Value Object nào không?
- Domain Service có đang phối hợp các khái niệm mà không có chủ sở hữu tự nhiên không?
- Interface có đầu vào, đầu ra và đơn vị rõ ràng không?
- Implementation có thể tính từ dữ kiện được truyền vào mà không truy cập hạ tầng ẩn không?
- Policy được chọn ở đâu và việc chọn đó là quyết định nghiệp vụ hay cấu hình triển khai?
- Có xác định ngày hiệu lực và phiên bản khi quy tắc thay đổi không?
- Domain Service có kiểm tra những bất biến chung của kết quả không?
- Các implementation và trường hợp biên đã có kiểm thử chưa?

## 16. Nguyên tắc cần ghi nhớ

Khi một phép tính nghiệp vụ có nhiều biến thể, hãy mô tả phần hợp đồng ổn định bằng một Policy interface dùng ngôn ngữ miền. Domain Service có thể nhận implementation qua constructor để điều phối phép tính mà không phụ thuộc vào công thức cụ thể. Nếu policy được chọn theo từng giao dịch, cần một cơ chế lựa chọn rõ ràng dựa trên hợp đồng, khách hàng, thị trường hoặc thời điểm áp dụng.

Giữ quy tắc trong mô hình miền, truyền dữ kiện cần thiết một cách tường minh và để dependency injection thực hiện việc kết nối implementation. Chỉ tạo abstraction khi có biến thể hoặc nhu cầu thay thế thực sự; cách làm này giúp chính sách thay đổi có kiểm soát, dễ kiểm thử và không làm luồng nghiệp vụ phụ thuộc vào framework hay hạ tầng.
