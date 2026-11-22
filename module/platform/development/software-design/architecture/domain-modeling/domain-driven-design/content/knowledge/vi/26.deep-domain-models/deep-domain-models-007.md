# Đối chiếu mô hình sâu với việc chỉ thêm nhiều lớp kỹ thuật

Trong Domain-Driven Design (DDD), một mô hình sâu (Deep Domain Model) diễn đạt được những khái niệm, quyết định và quy tắc quan trọng của nghiệp vụ bằng một ngôn ngữ rõ ràng. Mô hình giúp đội phát triển và chuyên gia nghiệp vụ cùng hiểu vì sao một hành động được phép, trạng thái nào hợp lệ và điều gì phải xảy ra khi điều kiện thay đổi.

Một hệ thống có nhiều tầng như Controller, Application Service, Repository, ORM, Adapter và Database chưa chắc có mô hình miền sâu. Những tầng đó tổ chức trách nhiệm kỹ thuật: nhận request, điều phối, truy cập dữ liệu, giao tiếp và triển khai. Chúng cần thiết trong nhiều kiến trúc, nhưng số lượng tầng không đo được mức độ hiểu biết nghiệp vụ đã được đưa vào mô hình.

Ngược lại, một mô hình có thể khá nhỏ nhưng sâu nếu nó đặt tên đúng các khái niệm, giữ invariant ở đúng nơi và làm cho các quy tắc phức tạp trở nên dễ diễn đạt. Bài học này đối chiếu hai chiều đó, trình bày cách khám phá mô hình qua trao đổi với chuyên gia, và dùng ví dụ đặt hàng/chiết khấu để nhận diện sự khác biệt.

## 1. Mô hình sâu là gì?

Mô hình miền là cách đội phát triển biểu diễn một phần thực tế nghiệp vụ để giải quyết một nhóm vấn đề cụ thể. Nó không phải bản sao đầy đủ của thế giới thực, cũng không chỉ là sơ đồ class. Một mô hình hữu ích chọn ra những khái niệm, quan hệ, trạng thái và quy tắc có ý nghĩa đối với bounded context đang xét.

Mô hình được xem là sâu khi nó diễn đạt được logic cốt lõi thay vì chỉ giữ dữ liệu. Người đọc có thể nhìn vào tên và hành vi của các đối tượng để hiểu các quyết định nghiệp vụ quan trọng. Những quy tắc trước đây nằm rải rác trong ghi chú, câu lệnh if, controller hoặc các service chung được tập hợp thành khái niệm có tên và có chủ sở hữu rõ.

Ví dụ, thay vì chỉ có một trường status và một service cập nhật giá trị đó, mô hình có thể biểu diễn các hành vi:

- **place()**: đặt đơn sau khi kiểm tra các điều kiện cần thiết.
- **confirm()**: xác nhận đơn khi các điều kiện xác nhận đã được đáp ứng.
- **cancel()**: hủy đơn nếu đơn vẫn ở giai đoạn cho phép hủy.
- **calculateDiscount()**: tính chiết khấu theo chính sách và điều kiện áp dụng.
- **reserveStock()**: yêu cầu giữ hàng theo một quy tắc tồn kho có thẩm quyền.

Tên phương thức không tự làm mô hình sâu. Điều quan trọng là mỗi hành vi có ý nghĩa nghiệp vụ, có quy tắc được bảo vệ và không chỉ là một cách viết khác của setter.

### 1.1. Chiều sâu nằm ở ngữ nghĩa và quy tắc

Một mô hình sâu thường có các đặc điểm:

1. **Ngôn ngữ chính xác:** phân biệt những khái niệm mà nghiệp vụ xem là khác nhau, kể cả khi chúng có cùng kiểu dữ liệu.
2. **Hành vi có ý nghĩa:** đối tượng miền thực hiện quyết định thuộc trách nhiệm của nó.
3. **Invariant rõ ràng:** trạng thái không hợp lệ bị ngăn tại nơi sở hữu dữ liệu và quy tắc.
4. **Abstraction có sức giải thích:** một khái niệm hoặc policy gom được nhiều trường hợp có cùng ý nghĩa.
5. **Ranh giới đúng:** mỗi quy tắc nằm trong bounded context và Aggregate phù hợp.
6. **Có thể kiểm chứng:** ví dụ nghiệp vụ và test thể hiện được điều kiện, kết quả và ngoại lệ.

### 1.2. Mô hình sâu không đồng nghĩa với mô hình lớn

Một mô hình sâu không nhất thiết có nhiều class, interface hoặc pattern. Đôi khi việc tìm đúng một Value Object hoặc một Policy làm mô hình đơn giản hơn vì loại bỏ nhiều điều kiện lặp.

Ngược lại, một mô hình có hàng trăm class có thể vẫn nông nếu các class chỉ chứa getter/setter, dữ liệu được chuyển qua nhiều DTO và toàn bộ quyết định nằm trong một service tổng quát.

Mục tiêu là tăng sức diễn đạt và khả năng bảo vệ quy tắc, không phải tăng số lượng thành phần.

## 2. Nhiều lớp kỹ thuật giải quyết vấn đề khác với mô hình sâu

Một kiến trúc phân lớp thường có đường đi như sau:

~~~mermaid
flowchart TD
    A[HTTP Controller] --> B[Application Service]
    B --> C[Repository Interface]
    C --> D[ORM / Persistence Adapter]
    D --> E[(Database)]
    B --> F[Domain Model]
~~~

Mỗi lớp có thể giải quyết một mối quan tâm hợp lý:

- Controller chuyển giao thức HTTP thành lời gọi use case.
- Application Service điều phối các bước của use case và transaction.
- Repository che giấu cách tải/lưu Aggregate.
- Adapter và ORM xử lý chi tiết tích hợp hoặc persistence.
- Domain Model biểu diễn khái niệm và quy tắc nghiệp vụ.

Việc có các tầng này giúp kiểm soát phụ thuộc và thay đổi kỹ thuật. Tuy nhiên, chúng không tự trả lời những câu hỏi như: khách hàng nào được hưởng ưu đãi, đơn nào đủ điều kiện đặt, chiết khấu nào được cộng dồn, hoặc khi nào đơn không còn được hủy.

| Dấu hiệu | Thêm lớp kỹ thuật | Mô hình miền sâu |
|---|---|---|
| Câu hỏi chính | Code được chia module và phụ thuộc thế nào? | Nghiệp vụ hoạt động và quyết định thế nào? |
| Thành phần | Controller, Service, Repository, Adapter, Mapper | Entity, Value Object, Aggregate, Policy, Specification, Domain Event |
| Giá trị | Cô lập framework, giao thức, database và điều phối | Diễn đạt thuật ngữ, hành vi, invariant và quy tắc |
| Dấu hiệu thành công | Thay đổi hạ tầng ít lan sang nơi khác | Thay đổi quy tắc có nơi sở hữu rõ và test được |
| Rủi ro nếu lạm dụng | Quá nhiều abstraction và chuyển tiếp không cần thiết | Mô hình quá phức tạp hoặc trừu tượng hóa sớm |

Hai chiều này bổ trợ nhau. Một hệ thống có thể có kiến trúc phân lớp tốt và mô hình miền sâu. Cũng có thể có ít tầng nhưng domain logic rõ. Không nên dùng “nhiều lớp” như bằng chứng duy nhất rằng hệ thống đã áp dụng DDD.

## 3. Mô hình nông thường biểu hiện như thế nào?

Một mô hình nông (shallow model) thường lưu dữ liệu trong các class đơn giản, còn quy tắc được thực hiện ở service hoặc script bên ngoài. Cách này không phải lúc nào cũng sai; với CRUD đơn giản, nó có thể phù hợp. Vấn đề xuất hiện khi nghiệp vụ có nhiều trạng thái, chính sách và ngoại lệ nhưng mô hình vẫn chỉ là túi dữ liệu.

Ví dụ:

~~~java
public class OrderData {
    private String status;
    private BigDecimal subtotal;
    private BigDecimal discount;
    private BigDecimal total;

    // getters và setters
}

public class OrderService {
    public void place(OrderData order, CustomerData customer) {
        if (order.getStatus().equals("DRAFT")
                && order.getSubtotal().compareTo(BigDecimal.ZERO) > 0) {
            if (customer.getTier().equals("GOLD")) {
                order.setDiscount(order.getSubtotal()
                    .multiply(new BigDecimal("0.10")));
            }
            order.setTotal(order.getSubtotal().subtract(order.getDiscount()));
            order.setStatus("PLACED");
        }
    }
}
~~~

Đoạn code có thể chạy, nhưng có một số vấn đề khi nghiệp vụ mở rộng:

- Quy tắc đặt đơn và chiết khấu bị trộn trong một service.
- Trạng thái là chuỗi nên có thể gán giá trị không được hỗ trợ.
- Không rõ chiết khấu áp dụng cho mọi khách Gold hay còn phụ thuộc ngày, kênh bán, ngưỡng tiền và mã khuyến mãi.
- Một đường code khác có thể thay đổi status hoặc total mà không qua quy tắc trên.
- Service phải biết cấu trúc dữ liệu nội bộ của Order và Customer.
- Khó đặt tên cho các khái niệm như điều kiện đủ tư cách, chính sách cộng dồn hay mức giảm tối đa.

Khi thêm quy tắc, service có thể dài hơn, nhiều nhánh hơn và khó kiểm thử. Việc chuyển code sang một lớp OrderDomainService mới chỉ thay đổi vị trí file nếu logic vẫn là một khối điều kiện không có ngôn ngữ miền rõ ràng.

### 3.1. Anemic Domain Model

Anemic Domain Model là cách tổ chức trong đó các Entity chủ yếu chứa dữ liệu và accessor, còn hành vi nghiệp vụ nằm bên ngoài. Nó có thể phù hợp với ứng dụng thiên về CRUD hoặc nghiệp vụ ít quy tắc. Nhưng với miền phức tạp, cách này làm cho trạng thái và quy tắc bị phân tán.

Không nên coi mọi logic trong Application Service là sai. Application Service phù hợp để điều phối: bắt đầu transaction, tải Aggregate, gọi hành vi, lưu và phát kết quả. Những quy tắc quyết định tính hợp lệ của trạng thái nên được bảo vệ trong Aggregate, Value Object, Policy hoặc Domain Service có ý nghĩa.

## 4. Khám phá chiều sâu bằng cách hiểu quyết định nghiệp vụ

Mô hình sâu không xuất hiện chỉ bằng cách chuyển danh từ trong tài liệu thành class. Nó được phát triển qua quá trình trao đổi, thử nghiệm và tinh chỉnh hiểu biết về miền.

Một cuộc trao đổi hiệu quả với chuyên gia nghiệp vụ nên tìm hiểu:

- Người dùng đang cố đạt được kết quả gì?
- Họ phải đưa ra quyết định nào?
- Điều kiện nào làm quyết định được chấp nhận hoặc từ chối?
- Có ngoại lệ nào và vì sao?
- Hai từ tưởng như đồng nghĩa có thực sự cùng ý nghĩa không?
- Khi trạng thái thay đổi, ai được phép thực hiện hành động tiếp theo?
- Sự kiện nào đánh dấu một sự thật đã xảy ra?
- Quy tắc có khác giữa các sản phẩm, kênh, vùng hoặc loại khách hàng không?

### 4.1. Bắt đầu bằng ví dụ cụ thể

Thay vì hỏi “Hệ thống có cần class Promotion không?”, hãy hỏi:

- Một khách hàng có thể dùng hai khuyến mãi trong cùng đơn không?
- Nếu cả hai khuyến mãi đều hợp lệ nhưng không được cộng dồn, hệ thống chọn khuyến mãi nào?
- Chiết khấu tính trước hay sau phí vận chuyển?
- Khi đơn bị hủy, điểm thưởng hoặc quyền lợi đã dùng được hoàn lại không?
- Giá được khóa tại lúc thêm vào giỏ hay lúc đặt đơn?
- Đơn đang chờ thanh toán có còn giữ ưu đãi không?

Những câu trả lời có thể làm lộ các khái niệm như DiscountEligibility, PromotionStackingPolicy, PriceSnapshot hoặc OrderPlacement. Chỉ tạo abstraction khi nó giúp diễn đạt một quy tắc thật sự.

### 4.2. Tìm các phân biệt ẩn trong ngôn ngữ

Chuyên gia có thể dùng những từ gần nhau nhưng có ý nghĩa khác:

| Từ dễ bị gộp | Câu hỏi cần làm rõ |
|---|---|
| Giá niêm yết và giá bán | Giá nào hiển thị, giá nào dùng để tính tiền? |
| Giảm giá và hoàn tiền | Một khoản giảm trước thanh toán khác gì khoản trả lại sau giao dịch? |
| Đơn đã đặt và đơn đã xác nhận | Sự kiện hoặc điều kiện nào phân biệt hai trạng thái? |
| Hủy và từ chối | Ai khởi tạo và đơn đang ở giai đoạn nào? |
| Tồn kho vật lý và tồn kho khả dụng | Có trừ lượng đã giữ, hư hỏng hoặc hàng đang kiểm kê không? |
| Khách hàng và người nhận hàng | Hai vai trò có thể là hai người khác nhau không? |

Nếu mô hình chỉ có một trường status hoặc một kiểu BigDecimal cho mọi khái niệm, những phân biệt này dễ bị mất. Mô hình sâu đưa sự khác biệt có ý nghĩa vào kiểu, tên và hành vi.

### 4.3. Dùng Event Storming và Example Mapping

Event Storming giúp nhóm khám phá sự kiện miền, command, actor, policy và câu hỏi chưa rõ. Example Mapping giúp làm rõ một user story qua các quy tắc và ví dụ cụ thể.

Ví dụ một luồng đặt hàng:

~~~mermaid
flowchart LR
    A[Customer requests placement] --> B{Order has valid lines?}
    B -->|No| C[Placement rejected]
    B -->|Yes| D[Calculate eligible discount]
    D --> E[OrderPlaced]
    E --> F[Reserve inventory]
    F --> G[Payment authorization]
    G --> H[OrderConfirmed]
~~~

Sơ đồ là điểm bắt đầu thảo luận. Nhóm cần xác nhận điều gì xảy ra khi giữ hàng thất bại, thanh toán bị từ chối, ưu đãi hết hạn hoặc giá thay đổi giữa lúc thêm hàng và lúc đặt.

## 5. Ubiquitous Language là nền tảng của mô hình sâu

Ubiquitous Language (ngôn ngữ chung) là ngôn ngữ được chuyên gia nghiệp vụ và đội phát triển cùng sử dụng trong một Bounded Context. Nó xuất hiện trong cuộc trao đổi, tài liệu, tên class, phương thức, event, API và test.

Ngôn ngữ chung không phải danh sách từ vựng để trang trí code. Mỗi thuật ngữ cần có định nghĩa và ví dụ đủ rõ để nhóm phân biệt cách dùng đúng.

Ví dụ trong Ordering:

- **Draft Order:** đơn đang được chỉnh sửa.
- **Placed Order:** đơn đã được khách gửi đi và vượt qua điều kiện đặt.
- **Confirmed Order:** đơn đã thỏa các điều kiện xác nhận theo chính sách.
- **Unit Price:** giá của một đơn vị tại thời điểm được chốt.
- **Discount Eligibility:** điều kiện một đơn hoặc khách hàng được hưởng ưu đãi.
- **Discount Stacking:** quy tắc có cho phép cộng dồn nhiều ưu đãi hay không.

Nếu Catalog cũng dùng từ “Product” nhưng mang ý nghĩa danh mục sản phẩm, Ordering có thể dùng ProductSnapshot để diễn đạt dữ liệu sản phẩm được chụp tại thời điểm đặt. Cùng một từ có thể mang ý nghĩa khác trong context khác; không nên ép một mô hình toàn cục nếu nghiệp vụ không cần.

### 5.1. Đưa ngôn ngữ vào code

Tên như calculate(), process(), handleData() quá chung nếu không chỉ rõ hành vi. Tên như placeOrder(), applyEligiblePromotion(), releaseReservedStock() cho biết ý định nghiệp vụ.

Tên chính xác giúp người đọc dự đoán điều gì được phép thay đổi và nơi cần tìm quy tắc. Nếu tên phương thức không thể giải thích bằng ngôn ngữ của chuyên gia, hãy kiểm tra xem mô hình có đang phản ánh chi tiết kỹ thuật thay vì khái niệm miền hay không.

### 5.2. Ngôn ngữ chung có phạm vi

Ubiquitous Language được xác định trong từng Bounded Context. “Customer” ở Sales có thể là người mua tiềm năng; ở Billing có thể là pháp nhân chịu trách nhiệm thanh toán; ở Support có thể là người liên hệ. Cần dùng context map và ACL để dịch giữa các mô hình khi tích hợp, thay vì ép mọi context dùng chung một class.

## 6. Từ dữ liệu sang khái niệm miền

Một cách nhận diện mô hình nông là nhìn vào các kiểu nguyên thủy và field chung. Kiểu dữ liệu có thể đúng về mặt lưu trữ nhưng không thể hiện quy tắc.

| Biểu diễn nông | Khái niệm có ngữ nghĩa hơn | Giá trị bổ sung |
|---|---|---|
| String sku | Sku | Chuẩn hóa và kiểm tra định dạng SKU |
| BigDecimal amount | Money | Gắn số tiền với tiền tệ và phép toán hợp lệ |
| int quantity | Quantity | Bảo vệ số lượng dương và quy tắc đơn vị |
| String status | OrderStatus hoặc state transition | Giới hạn trạng thái và chuyển đổi hợp lệ |
| LocalDate start/end | DateRange | Bảo vệ khoảng ngày và cách tính biên |
| boolean eligible | DiscountEligibility | Diễn đạt lý do đủ/không đủ điều kiện |

Không phải mọi primitive đều cần bọc thành class. Nếu một giá trị không có quy tắc, không có ngữ nghĩa riêng và không giúp code rõ hơn, giữ kiểu đơn giản có thể tốt hơn. Value Object có ích khi nó bảo vệ một ý nghĩa hoặc invariant cụ thể.

## 7. Ví dụ xuyên suốt: mô hình đặt hàng có chính sách chiết khấu

Giả sử chuyên gia nghiệp vụ mô tả quy tắc ban đầu:

1. Chỉ đơn nháp mới được thêm dòng hàng.
2. Một SKU chỉ xuất hiện một lần trong đơn; thêm lại SKU sẽ bị từ chối hoặc phải dùng hành vi tăng số lượng riêng.
3. Số lượng phải lớn hơn 0.
4. Chỉ khách Gold có đơn đạt ngưỡng tối thiểu mới được giảm 10%.
5. Chiết khấu không được vượt quá subtotal.
6. Khi đặt đơn, giá và chiết khấu được chốt vào đơn.
7. Đơn đã đặt không được sửa dòng hàng.

Những quy tắc này tạo ra các khái niệm có tên: Order, OrderLine, Sku, Quantity, Money, CustomerTier, DiscountPolicy và OrderPlaced.

### 7.1. Value Object diễn đạt ràng buộc

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

record Sku(String value) {
    Sku {
        Objects.requireNonNull(value);
        value = value.trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("SKU không được để trống");
        }
    }
}

record Quantity(int value) {
    Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
    }
}

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        amount = amount.stripTrailingZeros();
    }

    static Money zero(Currency currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    Money multiply(BigDecimal factor) {
        int scale = Math.max(currency.getDefaultFractionDigits(), 0);
        BigDecimal result = amount.multiply(factor)
            .setScale(scale, RoundingMode.HALF_UP);
        return new Money(result, currency);
    }

    int compareTo(Money other) {
        requireSameCurrency(other);
        return amount.compareTo(other.amount);
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Không thể tính toán khác loại tiền");
        }
    }
}

record OrderLine(Sku sku, Quantity quantity, Money unitPrice) {
    OrderLine {
        Objects.requireNonNull(sku);
        Objects.requireNonNull(quantity);
        Objects.requireNonNull(unitPrice);
        if (unitPrice.amount().signum() < 0) {
            throw new IllegalArgumentException("Đơn giá không được âm");
        }
    }

    Money lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity.value()));
    }
}
~~~

Các kiểu này không chỉ đổi tên primitive. Chúng gom quy tắc về giá trị vào nơi có ý nghĩa: SKU không rỗng, Quantity dương, Money không cộng khác tiền tệ và OrderLine không có đơn giá âm.

Quy tắc làm tròn trong ví dụ chỉ minh họa. Hệ thống thật cần thống nhất độ chính xác, cách làm tròn, đơn vị tiền tệ và thời điểm làm tròn với chính sách tài chính của bounded context.

### 7.2. Policy diễn đạt quy tắc chiết khấu

Nếu quy tắc chiết khấu là một khái niệm nghiệp vụ được gọi tên, hãy biểu diễn nó thành Policy hoặc Domain Service thay vì để một khối if lặp lại ở nhiều use case.

~~~java
import java.math.BigDecimal;

enum CustomerTier {
    REGULAR,
    SILVER,
    GOLD
}

interface DiscountPolicy {
    Money discountFor(CustomerTier tier, Money subtotal);
}

final class LoyaltyDiscountPolicy implements DiscountPolicy {
    private final Money goldMinimumSpend;

    LoyaltyDiscountPolicy(Money goldMinimumSpend) {
        this.goldMinimumSpend = goldMinimumSpend;
    }

    @Override
    public Money discountFor(CustomerTier tier, Money subtotal) {
        if (tier != CustomerTier.GOLD
                || subtotal.compareTo(goldMinimumSpend) < 0) {
            return Money.zero(subtotal.currency());
        }

        return subtotal.multiply(new BigDecimal("0.10"));
    }
}
~~~

Policy có tên, đầu vào và kết quả rõ. Khi nghiệp vụ thay đổi, nhóm có thể thảo luận trực tiếp về Loyalty Discount Policy, ngưỡng tối thiểu và mức giảm. Nếu sau này có thêm ưu đãi theo chiến dịch, mã coupon hoặc quy tắc không cộng dồn, có thể mở rộng mô hình dựa trên yêu cầu đã được xác nhận.

### 7.3. Aggregate bảo vệ chuyển trạng thái

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record OrderId(String value) {}

enum OrderStatus {
    DRAFT,
    PLACED
}

record OrderPlaced(
    OrderId orderId,
    Money subtotal,
    Money discount,
    Money total
) {}

final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    Order(OrderId id) {
        this.id = Objects.requireNonNull(id);
    }

    public void addLine(OrderLine line) {
        ensureDraft();
        Objects.requireNonNull(line);

        boolean duplicateSku = lines.stream()
            .anyMatch(existing -> existing.sku().equals(line.sku()));
        if (duplicateSku) {
            throw new IllegalArgumentException("SKU đã tồn tại trong đơn");
        }
        lines.add(line);
    }

    public OrderPlaced place(
            CustomerTier tier,
            DiscountPolicy discountPolicy) {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Không thể đặt đơn rỗng");
        }

        Money subtotal = lines.stream()
            .map(OrderLine::lineTotal)
            .reduce(Money::add)
            .orElseThrow();

        Money discount = discountPolicy.discountFor(tier, subtotal);
        Money zero = Money.zero(subtotal.currency());
        if (discount.compareTo(zero) < 0
                || discount.compareTo(subtotal) > 0) {
            throw new IllegalStateException("Chính sách trả về chiết khấu không hợp lệ");
        }

        Money total = subtotal.subtract(discount);
        status = OrderStatus.PLACED;
        return new OrderPlaced(id, subtotal, discount, total);
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public OrderStatus status() {
        return status;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Chỉ đơn nháp mới được thay đổi");
        }
    }
}
~~~

Aggregate Root kiểm soát thêm dòng và đặt đơn. Nó không cung cấp collection mutable cho caller. Khi đặt đơn, nó kiểm tra trạng thái, kiểm tra có dòng hàng, tính subtotal, gọi policy, xác thực kết quả chiết khấu rồi mới chuyển sang trạng thái PLACED.

Event OrderPlaced mang các giá trị đã chốt. Application Service có thể lưu Aggregate và công bố domain event sau khi transaction commit. Ví dụ chưa trình bày Repository và transaction implementation vì trọng tâm ở đây là nơi sở hữu quy tắc.

### 7.4. Tầng ứng dụng vẫn cần thiết

Application Service không biến mất khi domain model sâu. Nó điều phối use case:

~~~java
public final class PlaceOrderHandler {
    private final OrderRepository orders;
    private final DiscountPolicy discountPolicy;
    private final UnitOfWork unitOfWork;

    public void handle(PlaceOrder command) {
        unitOfWork.inTransaction(() -> {
            Order order = orders.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFound(command.orderId()));

            OrderPlaced event = order.place(
                command.customerTier(),
                discountPolicy
            );
            orders.save(order);
            unitOfWork.addDomainEvent(event);
        });
    }
}
~~~

Handler điều phối transaction, tải Aggregate và lưu kết quả. Quy tắc đơn rỗng, SKU trùng, trạng thái đơn và giới hạn chiết khấu vẫn được bảo vệ trong mô hình miền. Việc phân lớp kỹ thuật và mô hình sâu cùng tồn tại, mỗi phần giải quyết đúng loại vấn đề của nó.

## 8. Từ một quy tắc đến một abstraction có sức giải thích

Một abstraction tốt gom các trường hợp có cùng ý nghĩa và làm cho code diễn đạt được quy tắc. Nó không chỉ là interface để có thể mock.

Ví dụ, nếu nhiều loại khuyến mãi cùng có điều kiện về ngày hiệu lực, phân khúc khách hàng, giá trị đơn và giới hạn giảm, mô hình có thể cần một khái niệm PromotionEligibility. Nếu có nhiều chính sách cộng dồn, DiscountStackingPolicy có thể mô tả ưu tiên và cách kết hợp.

Nhưng không nên tạo ngay các class này nếu nghiệp vụ hiện chỉ có một quy tắc đơn giản. Hãy chờ đến khi nhóm xác nhận có nhiều trường hợp thực sự cùng một khái niệm.

### 8.1. Dấu hiệu một abstraction có giá trị

- Chuyên gia nghiệp vụ có thể gọi tên nó trong cuộc trao đổi.
- Nó giải thích được nhiều ví dụ hoặc quy tắc liên quan.
- Nó loại bỏ sự lặp lại có ý nghĩa, không chỉ gom code giống cú pháp.
- Nó có ranh giới trách nhiệm và dữ liệu đầu vào rõ.
- Nó giúp một thay đổi nghiệp vụ được thực hiện ở một nơi có chủ đích.
- Nó làm test mô tả quy tắc thay vì kiểm tra chi tiết implementation.

### 8.2. Dấu hiệu abstraction giả

- Tên như Manager, Processor, Helper, CommonService không cho biết khái niệm miền.
- Interface chỉ có một implementation và không đại diện cho policy hoặc port có ý nghĩa.
- Class chuyển tiếp nguyên xi lời gọi mà không thêm ngữ nghĩa hoặc ranh giới.
- Một base class chứa nhiều hook chung nhưng các lớp con không chia sẻ cùng một quy tắc nghiệp vụ.
- Abstraction được tạo chỉ vì “DDD cần nhiều class”.

## 9. Vai trò của Entity, Value Object, Aggregate, Domain Service và Policy

Các building block của DDD giúp đặt trách nhiệm vào đúng nơi. Chúng không phải danh sách class phải có trong mọi module.

| Building block | Câu hỏi nó trả lời | Khi phù hợp |
|---|---|---|
| Entity | Đối tượng được nhận diện xuyên suốt thay đổi bằng điều gì? | Có identity và vòng đời riêng |
| Value Object | Giá trị này được xác định và kiểm tra bằng những thành phần nào? | Không cần identity; equality theo giá trị |
| Aggregate | Những trạng thái nào cần được bảo vệ như một đơn vị nhất quán? | Có invariant cần kiểm soát qua một root |
| Domain Service | Hành vi nghiệp vụ nào không tự nhiên thuộc một Entity/VO cụ thể? | Một phép quyết định miền có ý nghĩa nhưng không có chủ sở hữu tự nhiên |
| Policy | Quy tắc hoặc chiến lược nào quyết định kết quả? | Có chính sách được gọi tên, có thể thay đổi theo điều kiện |
| Specification | Một đối tượng hoặc tình huống có thỏa một tiêu chí nghiệp vụ không? | Tiêu chí có thể tái sử dụng hoặc kết hợp |
| Domain Event | Sự thật nghiệp vụ nào đã xảy ra? | Cần ghi nhận hoặc phối hợp phản ứng sau sự kiện |

### 9.1. Đặt hành vi vào Aggregate khi nó bảo vệ invariant

Nếu thay đổi một dòng hàng ảnh hưởng tới tổng tiền hoặc trạng thái của Order, Aggregate Root nên kiểm soát thay đổi. Nếu chỉ đưa logic đó vào Application Service, mọi caller phải nhớ thứ tự gọi và tự bảo vệ cùng một quy tắc.

### 9.2. Dùng Domain Service khi hành vi không thuộc riêng một Entity

Một phép tính giá có thể cần nhiều dữ liệu từ Order, Customer và Promotion. Nếu nó là một quyết định nghiệp vụ có tên nhưng không tự nhiên thuộc một đối tượng cụ thể, Domain Service hoặc Policy có thể phù hợp. Đừng tạo Domain Service chỉ để chuyển logic từ một class sang class khác.

### 9.3. Dùng Specification khi tiêu chí là một khái niệm

Ví dụ EligibleForFreeShipping có thể diễn đạt điều kiện miễn phí vận chuyển. Nếu chỉ có một câu điều kiện đơn giản, một phương thức boolean có thể đủ. Khi tiêu chí được tái sử dụng, kết hợp hoặc cần giải thích rõ, Specification có thể tăng sức diễn đạt.

## 10. Strategic Design giúp mô hình sâu nằm đúng chỗ

Mô hình sâu không nên được xây như một mô hình chung cho toàn doanh nghiệp. Strategic Design xác định subdomain và bounded context để biết nơi nào cần đầu tư chiều sâu và ngôn ngữ nào có hiệu lực.

- **Core Domain:** phần tạo khác biệt cạnh tranh; thường đáng đầu tư nhiều công sức khám phá và làm sâu mô hình.
- **Supporting Subdomain:** hỗ trợ năng lực chính; có thể cần mô hình phù hợp nhưng mức đầu tư tùy giá trị.
- **Generic Subdomain:** năng lực phổ biến; có thể dùng giải pháp tiêu chuẩn nếu phù hợp.
- **Bounded Context:** ranh giới nơi một mô hình và Ubiquitous Language có ý nghĩa nhất quán.
- **Context Map:** mô tả quan hệ và cách tích hợp giữa các context.

Ví dụ, cùng một công ty có thể có:

| Bounded Context | Cách hiểu về Product |
|---|---|
| Catalog | Sản phẩm có mô tả, hình ảnh và thuộc tính hiển thị |
| Ordering | Thông tin sản phẩm được chụp vào dòng hàng khi đặt |
| Inventory | SKU và đơn vị tồn kho có thể cấp phát |
| Billing | Mặt hàng, thuế suất và cách ghi nhận trên chứng từ |

Không nên tạo một class Product toàn cục với mọi field và hành vi. Mỗi context nên mô hình hóa phần cần thiết cho quy tắc của mình, rồi dịch qua contract/ACL khi tích hợp.

### 10.1. Không làm sâu mọi subdomain như nhau

Đầu tư mô hình cần cân nhắc giá trị nghiệp vụ và độ phức tạp. Core Domain có thể cần nhiều vòng khám phá, policy và abstraction chuyên biệt. Generic Subdomain có thể dùng thư viện hoặc dịch vụ sẵn có. DDD không yêu cầu tự xây mọi thứ.

### 10.2. Một mô hình sâu nhưng sai context vẫn gây hại

Một abstraction tinh vi không có nghĩa là đúng nếu nó trộn ngôn ngữ của nhiều context. Ví dụ, dùng cùng một CustomerStatus cho Sales, Billing và Support có thể che giấu các chính sách khác nhau. Mô hình sâu phải sâu trong phạm vi vấn đề mà nó giải quyết.

## 11. Mô hình sâu được phát triển qua nhiều vòng học hỏi

Mô hình miền không được thiết kế hoàn hảo ngay từ đầu. Nó phát triển khi nhóm phát hiện các trường hợp trước đây chưa hiểu, thử cách diễn đạt mới và kiểm tra lại bằng ví dụ thực tế.

Một vòng lặp thực hành:

1. Chọn một use case có giá trị và một chuyên gia nghiệp vụ hiểu rõ nó.
2. Ghi lại thuật ngữ, quyết định, sự kiện và các trường hợp ngoại lệ.
3. Xác định các khái niệm ứng viên và mối quan hệ giữa chúng.
4. Tạo một mô hình nhỏ đủ để diễn đạt quy tắc.
5. Viết ví dụ và test cho trường hợp bình thường, biên và thất bại.
6. Đưa mô hình vào code và quan sát nơi ngôn ngữ còn mơ hồ.
7. Thảo luận lại với chuyên gia, chỉnh tên hoặc ranh giới.
8. Loại bỏ abstraction không còn cần thiết.

### 11.1. Dùng test như ví dụ sống của ngôn ngữ nghiệp vụ

Test có thể diễn đạt trực tiếp:

~~~java
@Test
void goldCustomerReceivesDiscountWhenOrderMeetsMinimumSpend() {
    Order order = orderWithSubtotal(money("2_000_000", "VND"));
    Money threshold = money("1_000_000", "VND");
    DiscountPolicy policy = new LoyaltyDiscountPolicy(threshold);

    OrderPlaced placed = order.place(CustomerTier.GOLD, policy);

    assertEquals(money("200_000", "VND"), placed.discount());
    assertEquals(money("1_800_000", "VND"), placed.total());
}

@Test
void regularCustomerDoesNotReceiveGoldDiscount() {
    Order order = orderWithSubtotal(money("2_000_000", "VND"));
    DiscountPolicy policy =
        new LoyaltyDiscountPolicy(money("1_000_000", "VND"));

    OrderPlaced placed = order.place(CustomerTier.REGULAR, policy);

    assertEquals(money("0", "VND"), placed.discount());
}
~~~

Các hàm orderWithSubtotal() và money() là test fixture. Test mô tả quy tắc và kết quả mong đợi, không phụ thuộc controller, ORM hoặc cách repository triển khai.

### 11.2. Ví dụ giúp tìm ra quy tắc chưa rõ

Nếu chuyên gia nói “khách Gold được giảm 10%”, nhóm cần hỏi:

- Giảm 10% trên subtotal trước hay sau thuế?
- Có giới hạn số tiền giảm tối đa không?
- Đơn bị trả lại có hoàn lại phần chiết khấu không?
- Hạng Gold được xác định ở thời điểm tạo giỏ hay lúc đặt đơn?
- Nếu khách bị hạ hạng sau khi đặt, đơn cũ có thay đổi không?

Các câu hỏi này không phải yêu cầu thêm lớp kỹ thuật. Chúng làm rõ chính sách và có thể dẫn tới các Value Object hoặc event cần thiết như CustomerTierSnapshot, DiscountApplied hoặc OrderPlaced.

## 12. Phân biệt mô hình sâu với workflow dài

Một workflow có nhiều bước không tự động là mô hình sâu. Workflow mô tả thứ tự phối hợp; mô hình miền diễn đạt ý nghĩa và quy tắc của từng quyết định.

Ví dụ, một quy trình đặt hàng có thể gồm:

1. Xác thực khách.
2. Kiểm tra sản phẩm.
3. Tính giá.
4. Giữ tồn kho.
5. Ủy quyền thanh toán.
6. Xác nhận đơn.
7. Gửi thông báo.

Application Service hoặc Saga có thể điều phối các bước. Nhưng các quy tắc như “không giữ vượt tồn kho”, “không xác nhận đơn rỗng”, “không áp dụng đồng thời hai ưu đãi loại trừ nhau” vẫn cần được bảo vệ ở Aggregate hoặc Policy sở hữu chúng.

Nếu workflow chỉ chứa chuỗi gọi service và mọi quy tắc đều nằm trong các nhánh if chung, thêm một process manager chưa làm mô hình miền sâu hơn. Chiều sâu đến từ việc mô hình hóa các quyết định và trạng thái mà workflow phối hợp.

## 13. Mô hình sâu và các tầng kỹ thuật phối hợp thế nào?

Một kiến trúc có thể tách thành các vùng:

~~~mermaid
flowchart TB
    subgraph Inbound[Inbound / Delivery]
        A[REST Controller]
        B[Message Consumer]
    end
    subgraph Application[Application Layer]
        C[Use Case Handler]
        D[Transaction / Unit of Work]
    end
    subgraph Domain[Domain Model]
        E[Aggregate Root]
        F[Value Objects]
        G[Policies / Domain Services]
        H[Domain Events]
    end
    subgraph Outbound[Outbound / Infrastructure]
        I[Repository Adapter]
        J[External API Adapter]
        K[(Database / Event Store)]
    end
    A --> C
    B --> C
    C --> E
    C --> D
    E --> F
    E --> G
    E --> H
    D --> I
    I --> K
    C --> J
~~~

Domain Model không cần biết HTTP, SQL hoặc cấu trúc message broker. Application Layer điều phối use case. Infrastructure triển khai các port và chi tiết kỹ thuật. Sự phân tách này hỗ trợ mô hình miền; bản thân nó không thay thế việc khám phá nghiệp vụ.

### 13.1. Application Service không nên trở thành “domain god service”

Nếu một Application Service chứa mọi quy tắc giá, chiết khấu, tồn kho, trạng thái và quyền hủy, nó trở thành nơi sở hữu giả tạo nhiều khái niệm. Hãy chuyển từng quy tắc về Aggregate, Value Object, Policy hoặc Domain Service phù hợp.

### 13.2. Repository không phải nơi chứa mọi query nghiệp vụ

Repository thường tải và lưu Aggregate Root. Truy vấn phục vụ màn hình hoặc báo cáo có thể dùng Query Service và projection. Đưa mọi điều kiện nghiệp vụ vào Repository implementation khiến domain model khó nhìn thấy và làm lộ chi tiết persistence.

### 13.3. Mapper không phải mô hình miền

Mapper chuyển đổi giữa DTO, persistence model hoặc contract ngoài. Nó cần thiết ở ranh giới, nhưng việc chuyển OrderRequest thành OrderEntity không tự tạo ra một mô hình Order có hành vi.

## 14. Khi nào chưa cần mô hình miền sâu?

DDD không phải lý do để biến mọi ứng dụng thành domain model nhiều lớp. Với một chức năng CRUD đơn giản, ít quy tắc, ít trạng thái và không có logic cạnh tranh, mô hình dữ liệu cùng service đơn giản có thể phù hợp.

Một số dấu hiệu có thể chưa cần đầu tư nhiều:

- Dữ liệu chủ yếu được tạo, đọc, sửa và xóa theo form.
- Không có invariant đáng kể ngoài validation field.
- Không có nhiều trạng thái hoặc chính sách thay đổi theo ngữ cảnh.
- Không có thuật ngữ chuyên biệt hoặc quyết định nghiệp vụ phức tạp.
- Quy tắc ổn định, phổ biến và có thể dùng giải pháp tiêu chuẩn.

Nếu độ phức tạp tăng, mô hình có thể được làm sâu dần. Không cần dự đoán mọi yêu cầu tương lai và tạo abstraction trước khi có hiểu biết.

## 15. Các dấu hiệu mô hình cần được làm sâu hơn

Hãy xem xét cải thiện domain model khi:

- Cùng một quy tắc được lặp lại ở nhiều controller hoặc service.
- Một thay đổi nghiệp vụ buộc sửa nhiều nơi không liên quan.
- Người phát triển phải đọc nhiều file mới hiểu một quyết định.
- Trạng thái được biểu diễn bằng chuỗi hoặc boolean khó kiểm soát.
- Các kiểu primitive mang nhiều ý nghĩa khác nhau nhưng bị dùng thay thế cho nhau.
- Chuyên gia nghiệp vụ dùng thuật ngữ mà code không có khái niệm tương ứng.
- Nhiều ngoại lệ được xử lý bằng điều kiện lồng nhau.
- Không rõ Aggregate hoặc context nào sở hữu một invariant.
- Test kiểm tra implementation thay vì quy tắc nghiệp vụ.

Không phải mọi dấu hiệu đều cần tạo thêm class. Có thể chỉ cần đổi tên, gom một hàm, đưa invariant vào Aggregate hoặc làm rõ một trạng thái.

## 16. Những sai lầm thường gặp

- **Đồng nhất nhiều tầng với mô hình sâu:** layering giải quyết cấu trúc kỹ thuật, không tự diễn đạt nghiệp vụ.
- **Chuyển mọi danh từ thành class:** tạo object không có identity, quy tắc hoặc ý nghĩa riêng.
- **Tạo interface cho mọi class:** abstraction không có ngữ nghĩa chỉ làm tăng số file.
- **Đổi tên Service nhưng giữ nguyên logic if/else:** vị trí code thay đổi, mô hình không sâu hơn.
- **Để Entity chỉ có getter/setter:** trạng thái có thể bị thay đổi từ nhiều nơi.
- **Đưa mọi logic vào Aggregate Root:** Aggregate phình to và trở thành god object; cần xác định đúng boundary.
- **Đưa mọi logic vào Domain Service:** service chung trở thành nơi chứa quy tắc không có chủ sở hữu.
- **Dùng một mô hình toàn cục cho mọi Bounded Context:** các thuật ngữ có nghĩa khác nhau bị ép vào cùng cấu trúc.
- **Tạo Value Object cho mọi primitive:** tăng boilerplate nếu không có ngữ nghĩa hoặc invariant bổ sung.
- **Mô hình hóa theo cấu trúc database:** bảng và cột quyết định domain concept thay vì quy tắc nghiệp vụ.
- **Mô hình hóa theo API nhà cung cấp:** DTO bên ngoài xâm nhập ngôn ngữ nội bộ.
- **Thiết kế quá sớm:** abstraction dựa trên giả định thay vì ví dụ và hiểu biết đã xác nhận.
- **Bỏ qua ví dụ ngoại lệ:** mô hình chỉ xử lý happy path và thất bại khi quy tắc thực tế xuất hiện.
- **Không cập nhật Ubiquitous Language:** code và cách chuyên gia gọi tên nghiệp vụ dần lệch nhau.
- **Làm sâu mọi subdomain như nhau:** đầu tư không tương xứng với giá trị và độ phức tạp.

## 17. Quy trình đánh giá một mô hình có thực sự sâu

Có thể dùng các câu hỏi sau khi review:

1. Mô hình có những khái niệm nào mà chuyên gia nghiệp vụ nhận ra và sử dụng?
2. Mỗi khái niệm có định nghĩa và ví dụ rõ không?
3. Các hành vi có tên theo ý định nghiệp vụ không?
4. Invariant được bảo vệ ở đâu và có thể bị bỏ qua qua đường gọi khác không?
5. Các trạng thái và chuyển đổi có thể diễn đạt rõ không?
6. Có sự phân biệt nào trong ngôn ngữ nghiệp vụ đang bị gộp thành cùng một primitive?
7. Policy hoặc Specification có tên có giúp loại bỏ logic lặp không?
8. Aggregate Boundary có dựa trên invariant hay chỉ dựa trên quan hệ object?
9. Bounded Context có ranh giới ngôn ngữ rõ không?
10. Tầng kỹ thuật có đang làm rò rỉ framework hoặc DTO vào domain model không?
11. Test có thể đọc như ví dụ nghiệp vụ không?
12. Có abstraction nào không có người dùng hoặc không diễn đạt quy tắc nào không?

### 17.1. Bảng đánh giá nhanh

| Khía cạnh | Mô hình còn nông | Mô hình có chiều sâu |
|---|---|---|
| Ngôn ngữ | Tên kỹ thuật hoặc tên chung | Thuật ngữ miền đã được thống nhất |
| Trạng thái | String/boolean tự do | Trạng thái và chuyển đổi hợp lệ |
| Quy tắc | If/else phân tán | Invariant, policy hoặc specification có chủ sở hữu |
| Hành vi | Setter và CRUD tổng quát | Phương thức diễn đạt ý định nghiệp vụ |
| Kiểu dữ liệu | Primitive dùng cho nhiều ý nghĩa | Value Object khi có ngữ nghĩa và quy tắc |
| Ranh giới | Theo bảng hoặc object graph | Theo invariant và quyền sở hữu |
| Kiểm thử | Mock nhiều tầng và kiểm tra implementation | Scenario kiểm tra quyết định miền |
| Thay đổi | Một quy tắc phải sửa nhiều nơi | Quy tắc có nơi được mô hình hóa rõ |

Đây là công cụ thảo luận, không phải thang điểm cứng. Một mô hình đơn giản vẫn có thể là lựa chọn tốt nếu nghiệp vụ thực sự đơn giản.

## 18. Checklist phát triển mô hình sâu

Trước khi hoàn thiện một phần domain model, hãy kiểm tra:

- [ ] Bounded Context và vấn đề nghiệp vụ đang giải quyết đã rõ.
- [ ] Thuật ngữ được xác nhận với chuyên gia nghiệp vụ.
- [ ] Những khái niệm gần nhau nhưng khác ý nghĩa đã được phân biệt.
- [ ] Quy tắc được mô tả bằng ví dụ bình thường, biên và thất bại.
- [ ] Entity, Value Object và Aggregate được chọn theo ngữ nghĩa, identity và invariant.
- [ ] Hành vi nghiệp vụ nằm ở nơi sở hữu trạng thái và quy tắc.
- [ ] Policy hoặc Domain Service có tên khi thực sự diễn đạt một quyết định miền.
- [ ] Application Service tập trung điều phối use case và transaction.
- [ ] Repository và Adapter che giấu chi tiết persistence/tích hợp.
- [ ] Không tạo abstraction chỉ để tăng số class hoặc interface.
- [ ] Không ép một mô hình chung lên nhiều Bounded Context.
- [ ] Test mô tả được quy tắc bằng ngôn ngữ nghiệp vụ.
- [ ] Mô hình được tinh chỉnh khi xuất hiện hiểu biết mới.
- [ ] Mức đầu tư tương xứng với vai trò của subdomain.

## 19. Câu hỏi tự kiểm tra

1. Mô hình sâu khác với kiến trúc có nhiều tầng kỹ thuật ở điểm nào?
2. Vì sao nhiều Controller, Service, Repository và Mapper chưa chứng minh rằng domain model sâu?
3. Anemic Domain Model là gì và khi nào nó trở thành vấn đề?
4. Ubiquitous Language giúp mô hình sâu như thế nào?
5. Vì sao không nên chuyển mọi danh từ trong tài liệu thành class?
6. Khi nào một primitive nên trở thành Value Object?
7. Invariant nên được bảo vệ ở đâu và vì sao không nên chỉ kiểm tra trong controller?
8. Domain Service, Policy và Specification khác nhau về mục đích ra sao?
9. Strategic Design giúp đặt mô hình sâu đúng Bounded Context như thế nào?
10. Vì sao cùng một thuật ngữ có thể có ý nghĩa khác nhau giữa Catalog, Ordering và Billing?
11. Event Storming và Example Mapping hỗ trợ khám phá mô hình ra sao?
12. Làm thế nào nhận ra một abstraction có sức giải thích thay vì chỉ là lớp chuyển tiếp?
13. Khi nào một ứng dụng CRUD chưa cần mô hình miền phức tạp?
14. Những dấu hiệu nào cho thấy quy tắc nghiệp vụ đang bị phân tán?

## Kết luận

Mô hình sâu thể hiện chiều sâu hiểu biết nghiệp vụ: khái niệm được gọi đúng tên, quyết định được diễn đạt rõ, invariant có nơi bảo vệ và các trường hợp ngoại lệ có thể kiểm chứng. Nhiều tầng kỹ thuật giúp tổ chức code và cô lập hạ tầng, nhưng không tự tạo ra những hiểu biết đó.

Hãy bắt đầu từ ngôn ngữ và ví dụ của chuyên gia, tìm ra các phân biệt có ý nghĩa, rồi mô hình hóa hành vi và quy tắc trong đúng Bounded Context. Dùng Entity, Value Object, Aggregate, Policy, Domain Service và Domain Event khi chúng giúp diễn đạt miền tốt hơn. Giữ Application Service, Repository và Adapter làm đúng nhiệm vụ kỹ thuật của chúng. Mô hình sâu không phải mô hình có nhiều class nhất; đó là mô hình giúp đội ngũ hiểu và thay đổi nghiệp vụ một cách chính xác hơn.
