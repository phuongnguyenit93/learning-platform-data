# Dịch vụ miền (Domain Service) và hành vi không thuộc tự nhiên về một đối tượng

Trong Domain-Driven Design (DDD), **Domain Service** là thành phần biểu diễn một quy tắc hoặc hành vi nghiệp vụ quan trọng nhưng không thuộc tự nhiên về một Entity hay Value Object cụ thể. Nó giúp mô hình diễn đạt những quyết định nghiệp vụ liên quan đến nhiều khái niệm hoặc cần một góc nhìn độc lập, thay vì ép hành vi vào một đối tượng không phù hợp hoặc để logic rải rác trong Application Service.

Domain Service thuộc mô hình miền: tên gọi và đầu vào/đầu ra của nó nên sử dụng ngôn ngữ chung của Bounded Context, còn logic bên trong phải phản ánh quy tắc nghiệp vụ. Nó thường không giữ trạng thái giao dịch riêng và không nên trở thành nơi truy cập cơ sở dữ liệu, gọi HTTP hay điều phối toàn bộ ca sử dụng.

Ví dụ, chính sách tính chiết khấu có thể phụ thuộc đồng thời vào hạng khách hàng và giá trị đơn hàng. Không có lý do tự nhiên để Customer sở hữu toàn bộ phép tính vì nó còn phụ thuộc vào đơn hàng; Order cũng không nên tự quyết định hạng thành viên của khách. Một Domain Service như DiscountCalculator có thể biểu diễn quy tắc kết hợp này, sau đó Order áp dụng kết quả thông qua hành vi của chính nó.

## 1. Domain Service là gì?

Domain Service là một đối tượng hoặc thành phần trong Domain Layer, có tên theo ngôn ngữ nghiệp vụ và chứa logic miền không phù hợp để đặt trong một Entity hay Value Object cụ thể.

Một Domain Service thường có các đặc điểm:

- **Logic thuộc nghiệp vụ:** nó biểu diễn chính sách, phép tính, quyết định hoặc hành vi mà chuyên gia nghiệp vụ quan tâm.
- **Không có chủ sở hữu tự nhiên là một Entity:** quy tắc có thể liên quan đến nhiều đối tượng hoặc không thuộc riêng đối tượng nào.
- **Có giao diện theo ngôn ngữ miền:** tên và tham số diễn đạt khái niệm nghiệp vụ, không phơi bày giao thức hoặc chi tiết hạ tầng.
- **Thường không giữ trạng thái riêng:** nhiều Domain Service là stateless; kết quả được xác định từ các đối tượng và giá trị đầu vào.
- **Không thay thế Aggregate:** bất biến của Aggregate vẫn phải được bảo vệ qua Aggregate Root.

Ví dụ về các Domain Service có thể có:

| Dịch vụ miền | Quy tắc hoặc hành vi |
| --- | --- |
| DiscountCalculator | Tính chiết khấu dựa trên hạng khách hàng, giá trị đơn và chính sách khuyến mãi. |
| FundsTransferPolicy | Đánh giá điều kiện chuyển tiền giữa tài khoản nguồn và tài khoản đích. |
| ShippingCostCalculator | Tính phí vận chuyển dựa trên kiện hàng, địa chỉ và phương thức giao. |
| CreditEligibilityPolicy | Đánh giá điều kiện cấp tín dụng dựa trên hồ sơ và chính sách. |
| TaxCalculator | Tính nghĩa vụ thuế theo loại giao dịch và quy định áp dụng trong miền. |

Tên dịch vụ phải phản ánh một khái niệm hoặc quy tắc thật sự của Bounded Context. Không phải mọi lớp có hậu tố Service đều là Domain Service.

## 2. Khi nào một hành vi cần Domain Service?

Trước khi tạo Domain Service, hãy thử xác định hành vi có thuộc tự nhiên về một đối tượng hiện có không.

### 2.1. Hành vi thuộc về một Entity

Nếu hành vi thay đổi trạng thái hoặc bảo vệ bất biến của một Entity, nên đặt hành vi đó trên Entity hoặc Aggregate Root.

Ví dụ:

- Order xác nhận hoặc hủy đơn.
- Account ghi nhận nạp tiền hoặc rút tiền.
- Shipment đánh dấu đã bàn giao.
- Subscription gia hạn hoặc chấm dứt.

Những hành vi này làm thay đổi vòng đời của đối tượng và cần được chính đối tượng bảo vệ.

### 2.2. Hành vi thuộc về một Value Object

Nếu hành vi là phép tính hoặc phép kiểm tra tự nhiên trên các giá trị cấu thành một Value Object, hãy đặt nó trong Value Object.

Ví dụ:

- Money cộng hai khoản tiền cùng đơn vị tiền tệ.
- DateRange kiểm tra hai khoảng thời gian có giao nhau không.
- Quantity kiểm tra hoặc nhân số lượng theo quy tắc của kiểu giá trị.
- Address chuẩn hóa hoặc so sánh các thành phần địa chỉ theo chính sách phù hợp.

Không cần tạo Domain Service chỉ để gọi một phương thức mà Value Object có thể tự thực hiện.

### 2.3. Hành vi không thuộc tự nhiên về một đối tượng

Domain Service phù hợp khi quy tắc:

- Phụ thuộc vào nhiều Entity hoặc Value Object nhưng không có đối tượng nào sở hữu tự nhiên toàn bộ quy tắc.
- Thể hiện một chính sách nghiệp vụ độc lập, được gọi từ nhiều luồng.
- Cần đánh giá một mối quan hệ giữa các đối tượng.
- Tạo ra kết quả nghiệp vụ mà không nhất thiết thay đổi một đối tượng cụ thể.

Ví dụ, tính chiết khấu dựa trên hạng thành viên của Customer và tổng tiền của Order. Nếu đặt phép tính trong Customer, Customer phải biết cấu trúc đơn hàng; nếu đặt trong Order, Order phải tự biết chính sách thành viên. Một Domain Service có thể nhận các khái niệm cần thiết và áp dụng chính sách chung.

### 2.4. Không tạo Domain Service chỉ để tránh một lớp có nhiều phương thức

Việc một Entity có nhiều phương thức không tự động có nghĩa cần tách Domain Service. Nếu các phương thức đều diễn đạt hành vi và bất biến của Entity, chúng vẫn thuộc Entity. Chỉ tách khi trách nhiệm nghiệp vụ thực sự không thuộc về đối tượng đó hoặc có một chính sách độc lập cần mô hình hóa.

## 3. Domain Service khác Application Service như thế nào?

Đây là điểm phân biệt quan trọng. Cả hai đều có thể mang tên Service và đều có thể được gọi từ một use case, nhưng chúng giải quyết hai loại vấn đề khác nhau.

| Tiêu chí | Domain Service | Application Service |
| --- | --- | --- |
| Mục đích | Biểu diễn quy tắc hoặc hành vi nghiệp vụ. | Điều phối một ca sử dụng của ứng dụng. |
| Ngôn ngữ | Dùng khái niệm và thuật ngữ của miền. | Dùng khái niệm ca sử dụng, command, query và luồng xử lý. |
| Logic chính | Chính sách, quyết định, phép tính nghiệp vụ. | Tải Aggregate, gọi hành vi, quản lý giao dịch, phối hợp cổng và lưu kết quả. |
| Phụ thuộc | Chủ yếu vào mô hình miền và các abstraction phù hợp. | Có thể phụ thuộc Repository, Domain Service và các port cần cho use case. |
| I/O và hạ tầng | Không trực tiếp gọi cơ sở dữ liệu, HTTP hoặc message broker. | Điều phối I/O thông qua các cổng hoặc adapter. |
| Ví dụ | DiscountCalculator, ShippingCostCalculator. | PlaceOrderService, CancelSubscriptionHandler. |

Ví dụ với việc áp dụng chiết khấu:

1. Application Service tải Order và Customer từ các Repository.
2. Application Service gọi Domain Service để tính mức chiết khấu theo chính sách.
3. Order kiểm tra và áp dụng khoản chiết khấu qua hành vi của Aggregate.
4. Application Service lưu Order và hoàn tất ca sử dụng.

Domain Service không cần biết request đến từ REST API hay message consumer. Application Service không nên tự viết lại công thức chiết khấu nếu đó là quy tắc nghiệp vụ cần dùng thống nhất.

## 4. Domain Service khác Utility Service và Infrastructure Service

Một lớp tiện ích có thể chứa hàm dùng chung nhưng không nhất thiết là một phần của mô hình miền.

| Loại | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Domain Service | Quy tắc có ý nghĩa nghiệp vụ. | Tính phí giao hàng theo chính sách vận chuyển. |
| Application Service | Điều phối ca sử dụng. | Tạo đơn, tải dữ liệu, gọi tính phí, lưu kết quả. |
| Utility | Hàm kỹ thuật hoặc thao tác tổng quát, không mang chính sách riêng của miền. | Chuẩn hóa chuỗi, định dạng ngày, chuyển đổi byte. |
| Infrastructure Service | Tích hợp hoặc cung cấp cơ chế kỹ thuật. | Gửi email qua SMTP, gọi API hãng vận chuyển, lưu file. |

Tên gọi không quyết định bản chất. Một lớp tên PricingService có thể là Domain Service nếu nó chứa chính sách định giá nghiệp vụ; nó có thể là Application Service nếu chỉ điều phối tải dữ liệu và lưu báo giá; hoặc là Infrastructure nếu chỉ gọi một nhà cung cấp định giá bên ngoài.

## 5. Nguyên tắc thiết kế Domain Service

### 5.1. Đặt tên theo ngôn ngữ nghiệp vụ

Tên nên diễn đạt quy tắc hoặc hành vi mà chuyên gia nghiệp vụ nhận ra. Ví dụ:

- DiscountCalculator: tính khoản chiết khấu.
- ShippingCostCalculator: tính phí vận chuyển.
- CreditEligibilityPolicy: đánh giá điều kiện tín dụng.
- ExchangeRatePolicy: xác định quy tắc quy đổi tiền tệ.

Tránh các tên quá chung như CommonService, DataManager hoặc BusinessHelper. Những tên này không cho biết lớp chịu trách nhiệm về quy tắc nào.

### 5.2. Dùng kiểu miền làm đầu vào và đầu ra

Tham số và kết quả nên sử dụng Entity, Value Object hoặc kiểu miền phù hợp thay vì truyền các primitive không có ý nghĩa.

Ví dụ, dùng Money thay vì một BigDecimal đơn lẻ nếu đơn vị tiền tệ có ý nghĩa. Dùng CustomerTier thay vì một số nguyên 1, 2, 3. Điều này làm hợp đồng dễ hiểu và giúp kiểm tra quy tắc ở đúng nơi.

### 5.3. Giữ logic miền độc lập với hạ tầng

Domain Service không nên phụ thuộc trực tiếp vào:

- Controller hoặc HTTP request/response.
- JPA Entity Manager, JDBC Connection hoặc SQL cụ thể.
- Message broker hoặc SDK của nhà cung cấp.
- Email, SMS hoặc dịch vụ thông báo.
- Framework web hoặc container triển khai.

Nếu một quy tắc cần thông tin từ bên ngoài, Application có thể tải dữ liệu trước rồi truyền vào Domain Service. Trong trường hợp đặc biệt, Domain Service có thể dùng một abstraction thuộc mô hình miền, nhưng cần cân nhắc để không biến nó thành lớp điều phối I/O.

### 5.4. Không giữ trạng thái giao dịch không cần thiết

Domain Service thường không lưu trạng thái của một yêu cầu qua nhiều lần gọi. Nếu dịch vụ giữ dữ liệu mutable như khách hàng hiện tại, đơn hàng hiện tại hoặc kết quả của lần gọi trước, các request đồng thời có thể ảnh hưởng lẫn nhau.

Chính sách có cấu hình bất biến hoặc tham số được truyền vào có thể phù hợp. Còn trạng thái vòng đời cần được sở hữu bởi Entity hoặc Aggregate.

### 5.5. Không biến Domain Service thành nơi chứa mọi logic

Nếu một Domain Service có hàng chục phương thức không liên quan, có thể nhóm đang dùng nó như một lớp tiện ích tổng hợp. Hãy chia theo các chính sách và khái niệm nghiệp vụ thực sự, đồng thời giữ hành vi thuộc Entity ở chính Entity.

### 5.6. Không biến Domain Service thành Application Service trá hình

Một Domain Service mà phương thức chính là tải Repository, gọi API, gửi email, mở transaction và cập nhật nhiều Aggregate có thể đang làm nhiệm vụ điều phối. Hãy chuyển luồng đó về Application Layer và giữ phần quyết định nghiệp vụ trong Domain.

## 6. Ví dụ: Domain Service tính chiết khấu

Giả sử chính sách bán hàng quy định mức chiết khấu dựa trên hai yếu tố:

- Hạng thành viên của khách hàng.
- Giá trị trước chiết khấu của đơn hàng.

Ví dụ chính sách minh họa:

| Hạng thành viên | Mức cơ bản |
| --- | ---: |
| STANDARD | 0% |
| SILVER | 3% |
| GOLD | 7% |

Nếu giá trị đơn từ 5.000.000 VND trở lên, khách hàng được cộng thêm 2 điểm phần trăm. Tổng chiết khấu không vượt quá 10%. Đây là chính sách giả định để minh họa; dự án thực tế cần xác nhận quy tắc với chuyên gia nghiệp vụ.

### 6.1. Vì sao không đặt toàn bộ quy tắc trong Customer hoặc Order?

Customer sở hữu hạng thành viên, nhưng không sở hữu giá trị đơn hàng. Order sở hữu các dòng hàng và tổng tiền, nhưng không nhất thiết sở hữu chính sách thành viên. Đặt toàn bộ quy tắc ở một trong hai đối tượng sẽ làm đối tượng đó biết quá nhiều về trách nhiệm của đối tượng kia.

Domain Service có thể nhận hạng thành viên và giá trị đơn, sau đó tính khoản chiết khấu. Nó không cần thay đổi Customer hoặc Order.

### 6.2. Mô hình các kiểu miền

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal amount, String currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        if (amount.signum() < 0 || currency.isBlank()) {
            throw new IllegalArgumentException("Invalid money");
        }
    }

    public Money multiply(BigDecimal rate) {
        return new Money(amount.multiply(rate), currency);
    }

    public boolean isAtLeast(Money other) {
        requireSameCurrency(other);
        return amount.compareTo(other.amount) >= 0;
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
    }
}

public enum CustomerTier {
    STANDARD, SILVER, GOLD
}
~~~

Trong dự án thật, Money và CustomerTier thường được đặt ở các file riêng. Ví dụ giả định toàn bộ phép tính sử dụng cùng đơn vị tiền tệ và chưa trình bày quy tắc làm tròn.

### 6.3. Domain Service thực hiện chính sách

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class DiscountCalculator {
    private static final Money LARGE_ORDER_THRESHOLD =
            new Money(new BigDecimal("5000000"), "VND");
    private static final BigDecimal LARGE_ORDER_BONUS =
            new BigDecimal("0.02");
    private static final BigDecimal MAX_DISCOUNT_RATE =
            new BigDecimal("0.10");

    public Money calculate(CustomerTier tier, Money subtotal) {
        Objects.requireNonNull(tier);
        Objects.requireNonNull(subtotal);

        BigDecimal rate = baseRate(tier);
        if (subtotal.isAtLeast(LARGE_ORDER_THRESHOLD)) {
            rate = rate.add(LARGE_ORDER_BONUS);
        }
        rate = rate.min(MAX_DISCOUNT_RATE);

        return subtotal.multiply(rate);
    }

    private BigDecimal baseRate(CustomerTier tier) {
        return switch (tier) {
            case STANDARD -> BigDecimal.ZERO;
            case SILVER -> new BigDecimal("0.03");
            case GOLD -> new BigDecimal("0.07");
        };
    }
}
~~~

DiscountCalculator biểu diễn chính sách miền. Nó không truy vấn CustomerRepository hoặc OrderRepository, không biết HTTP và không lưu trạng thái giữa các lần gọi. Cùng một đầu vào sẽ cho cùng một kết quả theo chính sách hiện tại.

Trong ứng dụng thực tế, có thể cần bổ sung loại chương trình khuyến mãi, thời gian hiệu lực, sản phẩm không áp dụng, thứ tự cộng dồn ưu đãi, giới hạn theo khách hàng và quy tắc làm tròn. Những điều kiện này cần được mô hình hóa bằng các kiểu và chính sách miền rõ ràng.

### 6.4. Aggregate chịu trách nhiệm áp dụng kết quả

Domain Service tính khoản chiết khấu, nhưng Order vẫn phải bảo vệ bất biến của đơn hàng khi áp dụng kết quả:

~~~java
public void applyDiscount(Money discount) {
    Objects.requireNonNull(discount);
    if (!discount.currency().equals(subtotal().currency())) {
        throw new IllegalArgumentException("Currency mismatch");
    }
    if (discount.amount().compareTo(subtotal().amount()) > 0) {
        throw new IllegalArgumentException("Discount cannot exceed subtotal");
    }
    this.discount = discount;
}
~~~

Đây là phương thức minh họa nằm trong Order. Nó bảo vệ bất biến rằng khoản chiết khấu không vượt tổng tiền và dùng cùng đơn vị tiền tệ. Quy tắc về thời điểm được phép áp dụng chiết khấu cũng nên được kiểm tra trong Aggregate.

### 6.5. Application Service điều phối

~~~java
public final class ApplyDiscountService {
    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final DiscountCalculator discountCalculator;

    public ApplyDiscountService(
            OrderRepository orders,
            CustomerRepository customers,
            DiscountCalculator discountCalculator
    ) {
        this.orders = orders;
        this.customers = customers;
        this.discountCalculator = discountCalculator;
    }

    public void apply(OrderId orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFound(orderId));
        Customer customer = customers.findById(order.customerId())
                .orElseThrow(() -> new CustomerNotFound(order.customerId()));

        Money discount = discountCalculator.calculate(
                customer.tier(),
                order.subtotal()
        );

        order.applyDiscount(discount);
        orders.save(order);
    }
}
~~~

Các kiểu Repository, ID và exception được giả định đã có trong mô hình. Ví dụ cho thấy Application Service tải dữ liệu và điều phối; Domain Service tính chính sách; Order bảo vệ trạng thái của chính nó. Nếu việc tải Customer và Order cần bảo đảm cùng một snapshot hoặc có rủi ro dữ liệu thay đổi đồng thời, use case phải xác định chính sách thời điểm và cơ chế kiểm soát phù hợp.

## 7. Domain Service có thể thay đổi Entity không?

Domain Service không bắt buộc chỉ là một hàm tính toán thuần. Một số hành vi miền liên quan đến nhiều đối tượng có thể cần một dịch vụ thực hiện thao tác trên các đối tượng đó. Tuy nhiên, phải giữ rõ trách nhiệm:

- Domain Service có thể áp dụng một quy tắc liên quan nhiều đối tượng nếu đó thực sự là hành vi miền.
- Entity và Aggregate Root vẫn phải bảo vệ bất biến của chính mình.
- Domain Service không được bypass các phương thức công khai để sửa trực tiếp trạng thái nội bộ.
- Việc lưu Aggregate, quản lý transaction hoặc gọi hệ thống ngoài thường thuộc Application và Infrastructure.

Ví dụ, một dịch vụ miền có thể đánh giá khả năng chuyển tiền giữa hai tài khoản, nhưng Account vẫn cung cấp hành vi rút và nhận tiền để bảo vệ bất biến số dư. Application Service điều phối tải hai Aggregate, gọi chính sách, thực hiện các hành vi và lưu theo ranh giới giao dịch đã thiết kế.

Nếu hành động đòi hỏi một giao dịch nguyên tử xuyên nhiều Aggregate, cần cân nhắc lại mô hình hoặc dùng một quy trình phối hợp phù hợp. Không nên dùng Domain Service để che giấu một transaction lớn mà hệ thống không thể bảo đảm.

## 8. Domain Service và Repository

Domain Service không mặc định sở hữu Repository. Việc một quy tắc cần dữ liệu không có nghĩa Domain Service phải tự truy vấn cơ sở dữ liệu.

Một cách tổ chức thường phù hợp:

1. Application Service xác định dữ liệu cần thiết cho use case.
2. Application tải Aggregate hoặc read model qua Repository/query port.
3. Application truyền các đối tượng hoặc giá trị miền vào Domain Service.
4. Domain Service tính toán hoặc đánh giá chính sách.
5. Aggregate áp dụng kết quả qua hành vi của nó.
6. Application lưu thay đổi và hoàn tất use case.

Trong một số mô hình, Domain Service có thể cần một abstraction để truy vấn một khái niệm miền, chẳng hạn kiểm tra một mã định danh đã được sử dụng chưa. Nếu chọn cách này, abstraction phải thể hiện nhu cầu miền và không phơi bày SQL hoặc công nghệ lưu trữ. Tuy nhiên, trước tiên hãy xem liệu Application có thể tải thông tin cần thiết và truyền vào dịch vụ hay không; tránh làm Domain Service trở thành lớp điều phối truy vấn.

## 9. Domain Service và Domain Event

Domain Service mô tả một quy tắc hoặc hành vi; Domain Event mô tả một sự việc nghiệp vụ đã xảy ra. Hai khái niệm có thể phối hợp nhưng không thay thế nhau.

Ví dụ:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Domain Service | Tính khoản chiết khấu theo chính sách. | DiscountCalculator.calculate(...) |
| Entity behavior | Áp dụng kết quả vào đơn và bảo vệ bất biến. | order.applyDiscount(discount) |
| Domain Event | Ghi nhận sự việc đã xảy ra. | OrderDiscountApplied |
| Application Service | Điều phối tải, tính, áp dụng và lưu. | ApplyDiscountService |

Nếu một sự kiện có ý nghĩa với phần khác của hệ thống, Aggregate có thể ghi nhận Domain Event sau khi hành vi thành công. Application hoặc cơ chế hạ tầng phát sự kiện sau khi dữ liệu được lưu theo chiến lược nhất quán đã chọn.

## 10. Domain Service có cần interface không?

Không phải mọi Domain Service đều cần interface. Nếu dịch vụ là một chính sách thuần, ổn định và không có nhiều cách triển khai, một class cụ thể có thể đủ.

Interface hữu ích khi:

- Có nhiều chính sách hoặc cách tính cần thay thế theo Bounded Context hoặc cấu hình nghiệp vụ.
- Một module cần phụ thuộc vào hợp đồng ổn định trong khi implementation được chọn ở composition root.
- Có ranh giới miền thực sự cần được biểu diễn và kiểm soát.

Không nên tạo interface chỉ để mock mọi class trong unit test. Có thể kiểm thử một Domain Service trực tiếp vì nó thường không cần cơ sở dữ liệu hoặc network.

Ví dụ, nếu có nhiều chính sách tính phí giao hàng theo khu vực, có thể định nghĩa ShippingCostPolicy và các implementation như StandardShippingPolicy, ExpressShippingPolicy. Nhưng nếu chỉ có một công thức nhỏ, một class cụ thể sẽ đơn giản hơn.

## 11. Kiểm thử Domain Service

Domain Service nên được kiểm thử bằng các đầu vào miền và kết quả nghiệp vụ. Không cần dựng web server, cơ sở dữ liệu hoặc message broker nếu dịch vụ chỉ thực hiện logic thuần.

Ví dụ với JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class DiscountCalculatorTest {
    private final DiscountCalculator calculator = new DiscountCalculator();

    @Test
    void standardCustomerGetsNoBaseDiscountForSmallOrder() {
        Money discount = calculator.calculate(
                CustomerTier.STANDARD,
                new Money(new BigDecimal("1000000"), "VND")
        );

        assertEquals(new BigDecimal("0.00"), discount.amount().setScale(2));
    }

    @Test
    void goldCustomerGetsBaseDiscountForSmallOrder() {
        Money discount = calculator.calculate(
                CustomerTier.GOLD,
                new Money(new BigDecimal("1000000"), "VND")
        );

        assertEquals(new BigDecimal("70000.00"), discount.amount().setScale(2));
    }

    @Test
    void largeGoldOrderReceivesCappedDiscount() {
        Money discount = calculator.calculate(
                CustomerTier.GOLD,
                new Money(new BigDecimal("5000000"), "VND")
        );

        assertEquals(new BigDecimal("450000.00"), discount.amount().setScale(2));
    }
}
~~~

Ví dụ kiểm thử giả định các kiểu Money và CustomerTier ở trên được đặt trong package phù hợp. Trong dự án thật, cần thống nhất scale và rounding của BigDecimal, đồng thời bổ sung kiểm thử biên tại ngưỡng 5.000.000 VND, trường hợp tiền tệ không khớp và các chính sách ngoại lệ.

Các câu hỏi kiểm thử hữu ích:

- Mỗi hạng khách hàng nhận đúng mức cơ bản chưa?
- Đơn đạt ngưỡng có được cộng ưu đãi đúng không?
- Tổng chiết khấu có bị giới hạn theo chính sách không?
- Giá trị biên ngay dưới, đúng bằng và ngay trên ngưỡng được xử lý ra sao?
- Dữ liệu không hợp lệ có bị từ chối rõ ràng không?
- Cùng đầu vào có luôn cho cùng kết quả theo cùng phiên bản chính sách không?

## 12. Những sai lầm thường gặp

### 12.1. Đưa hành vi thuộc Entity sang Domain Service

Nếu Order có thể tự xác nhận hoặc hủy bằng cách bảo vệ trạng thái của nó, không cần tạo OrderService chỉ để gọi các setter. Hãy giữ hành vi trên Aggregate Root.

### 12.2. Domain Service chỉ là lớp chuyển tiếp

Một class có phương thức gọi thẳng một phương thức Entity mà không bổ sung chính sách hay ý nghĩa miền thường không tạo thêm giá trị. Hãy xem hành vi nên nằm trực tiếp trên Entity hay Value Object.

### 12.3. Domain Service chứa logic kỹ thuật

Gửi email, gọi REST API, đọc file hoặc ghi SQL là trách nhiệm hạ tầng. Đặt chúng trong Domain Service khiến mô hình phụ thuộc công nghệ và khó kiểm thử.

### 12.4. Domain Service chứa toàn bộ use case

Nếu một service tải nhiều Repository, kiểm tra quyền, mở transaction, gọi API và gửi thông báo, nó có thể đang là Application Service trá hình. Tách phần quyết định nghiệp vụ khỏi phần điều phối.

### 12.5. Dùng primitive và tên chung chung

Một phương thức như calculate(int type, BigDecimal amount) không cho biết type đại diện cho khái niệm nào. Hãy dùng kiểu miền và tên tham số rõ nghĩa khi điều đó giúp diễn đạt chính sách.

### 12.6. Đặt mọi lớp có hậu tố Service vào Domain Layer

Tên Service không chứng minh lớp thuộc Domain. Hãy xem logic có phải quy tắc nghiệp vụ hay chỉ điều phối hoặc tích hợp kỹ thuật.

### 12.7. Dùng Domain Service để né thiết kế Aggregate

Nếu một quy tắc là bất biến của Aggregate, không nên chuyển nó ra Domain Service rồi để caller tùy ý thay đổi trạng thái. Root vẫn phải bảo vệ bất biến bất kể có dịch vụ miền hỗ trợ tính toán hay không.

### 12.8. Tạo quá nhiều interface và abstraction

Không cần một interface, factory và strategy cho mọi phép tính nhỏ. Abstraction nên xuất hiện khi nó thể hiện một khái niệm, biến thể chính sách hoặc ranh giới thực sự.

## 13. Quy trình xác định có cần Domain Service không

Khi gặp một đoạn logic nghiệp vụ, có thể lần lượt hỏi:

1. Logic này có thuộc tự nhiên về một Entity hoặc Aggregate Root không?
2. Nó có phải phép tính hoặc hành vi trên các giá trị của một Value Object không?
3. Nó có liên quan đến nhiều đối tượng hoặc một chính sách độc lập không?
4. Chuyên gia nghiệp vụ có thể nhận ra và gọi tên quy tắc này không?
5. Logic có thể thực hiện từ dữ liệu miền mà không cần trực tiếp truy cập hạ tầng không?
6. Kết quả có cần được một Aggregate áp dụng thông qua hành vi riêng không?
7. Phần còn lại có chỉ là điều phối use case, truy vấn dữ liệu hoặc tích hợp hệ thống không?

Nếu câu trả lời cho các câu hỏi về chính sách độc lập và ý nghĩa nghiệp vụ là có, Domain Service có thể phù hợp. Nếu logic thuộc một đối tượng, hãy đặt nó trên đối tượng. Nếu chỉ điều phối luồng, hãy giữ ở Application Service.

~~~mermaid
flowchart TD
    A[Phát hiện logic nghiệp vụ] --> B{Có thuộc tự nhiên về Entity/Aggregate?}
    B -->|Có| C[Đặt hành vi trên Entity hoặc Aggregate Root]
    B -->|Không| D{Có phải phép tính trên giá trị?}
    D -->|Có| E[Đặt hành vi trên Value Object]
    D -->|Không| F{Là quy tắc nghiệp vụ độc lập hoặc liên quan nhiều đối tượng?}
    F -->|Có| G[Xem xét Domain Service]
    F -->|Không| H{Chủ yếu điều phối use case hoặc I/O?}
    H -->|Có| I[Đặt ở Application Service hoặc Infrastructure]
    H -->|Không| J[Làm rõ lại mô hình và trách nhiệm]
~~~

## 14. Checklist thiết kế Domain Service

- [ ] Dịch vụ biểu diễn một quy tắc hoặc hành vi nghiệp vụ có ý nghĩa.
- [ ] Hành vi không thuộc tự nhiên về một Entity hoặc Value Object cụ thể.
- [ ] Tên dịch vụ và phương thức dùng ngôn ngữ chung của Bounded Context.
- [ ] Đầu vào và đầu ra sử dụng kiểu miền khi phù hợp.
- [ ] Dịch vụ không chứa logic HTTP, SQL, ORM hoặc message broker.
- [ ] Dịch vụ không giữ trạng thái giao dịch mutable giữa các lần gọi.
- [ ] Aggregate Root vẫn bảo vệ các bất biến của chính nó.
- [ ] Application Service chịu trách nhiệm điều phối use case và lưu thay đổi.
- [ ] Domain Event chỉ được ghi nhận khi một sự việc nghiệp vụ thực sự xảy ra.
- [ ] Interface chỉ được tạo khi có abstraction hoặc biến thể chính sách thực sự.
- [ ] Có kiểm thử cho trường hợp phổ biến, biên và dữ liệu không hợp lệ.

## 15. Kết luận

Domain Service giúp mô hình DDD diễn đạt một quy tắc hoặc hành vi nghiệp vụ không thuộc tự nhiên về một Entity hay Value Object. Nó phù hợp với chính sách liên quan nhiều khái niệm, chẳng hạn tính chiết khấu dựa trên hạng khách hàng và giá trị đơn hàng. Dịch vụ nên có tên theo ngôn ngữ nghiệp vụ, làm việc với kiểu miền và giữ độc lập với chi tiết hạ tầng.

Domain Service không thay thế Entity, Aggregate Root hoặc Application Service. Entity vẫn bảo vệ vòng đời và bất biến của nó; Value Object xử lý hành vi thuộc giá trị; Application Service điều phối ca sử dụng, tải dữ liệu và lưu thay đổi; Infrastructure thực hiện tích hợp kỹ thuật. Đặt đúng hành vi vào đúng nơi giúp mô hình rõ ràng, tránh lớp Service phình to và giữ cho quy tắc nghiệp vụ có thể được kiểm thử độc lập.
