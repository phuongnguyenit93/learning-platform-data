# Specification: biểu diễn tiêu chí và kiểm tra điều kiện nghiệp vụ

Trong Domain-Driven Design (DDD), nhiều quyết định nghiệp vụ được diễn đạt dưới dạng tiêu chí: khách hàng nào đủ điều kiện nhận ưu đãi, sản phẩm nào được phép bán ở một thị trường, đơn hàng nào có thể xác nhận, hay khoản thanh toán nào cần được rà soát. Những tiêu chí này thường xuất hiện ở nhiều use case và có thể thay đổi theo chính sách của doanh nghiệp.

**Specification (đặc tả)** là một mẫu thiết kế dùng để đóng gói một tiêu chí nghiệp vụ thành một đối tượng có thể kiểm tra. Thay vì rải cùng một nhóm điều kiện trong nhiều application service hoặc controller, đội ngũ biểu diễn tiêu chí tại một nơi có tên gọi rõ ràng, có thể kiểm thử, tái sử dụng và kết hợp với các tiêu chí khác.

Specification giúp domain model diễn đạt những câu hỏi như “khách hàng này có đủ điều kiện không?” hoặc “đơn hàng này có đáp ứng chính sách giao nhanh không?”. Nó đặc biệt hữu ích khi điều kiện có ý nghĩa nghiệp vụ độc lập, có thể được đặt tên và cần kết hợp với nhau. Tuy nhiên, Specification không thay thế mọi câu lệnh if, không thay thế invariant của Aggregate và cũng không mặc nhiên là một query builder cho database.

## 1. Specification là gì?

Specification biểu diễn một tiêu chí có thể đánh giá trên một đối tượng hoặc một tập dữ liệu. Cách dùng cơ bản là đưa một candidate vào và nhận kết quả cho biết candidate có thỏa tiêu chí hay không.

Ví dụ:

- Khách hàng có đủ điều kiện tham gia chương trình thành viên không?
- Sản phẩm có được phép bán tại thị trường đang xét không?
- Đơn hàng có đủ điều kiện giao miễn phí không?
- Hợp đồng có đang trong thời hạn hiệu lực không?
- Khoản thanh toán có cần kiểm tra thủ công không?

Một Specification thường có tên diễn đạt ngôn ngữ nghiệp vụ và một phép đánh giá:

    isSatisfiedBy(candidate)

Tên của specification nên trả lời được tiêu chí đang mô tả. Ví dụ, EligibleForFreeShippingSpecification rõ nghĩa hơn một hàm chung chung như checkCondition.

### Ví dụ đơn giản

Giả sử doanh nghiệp có chính sách miễn phí giao hàng khi tổng giá trị hàng hóa đạt ngưỡng và địa chỉ giao thuộc khu vực được hỗ trợ.

    FreeShippingSpecification
        = order total >= minimum amount
          AND destination is supported

Application có thể hỏi specification:

    if (freeShippingSpecification.isSatisfiedBy(order)) {
        // Áp dụng phương án giao hàng miễn phí
    }

Điều kiện được đóng gói và đặt tên theo nghiệp vụ. Khi ngưỡng giá trị hoặc danh sách khu vực thay đổi, nhóm có một nơi rõ ràng để điều chỉnh và kiểm thử.

## 2. Khi nào nên dùng Specification?

Không phải mọi điều kiện đều cần một class riêng. Một điều kiện đơn giản, chỉ xuất hiện một lần và không mang ý nghĩa nghiệp vụ độc lập có thể nằm ngay trong phương thức đang sử dụng nó.

Specification đáng cân nhắc khi có một hoặc nhiều dấu hiệu:

- Tiêu chí có tên nghiệp vụ rõ ràng và chuyên gia thường nhắc đến nó.
- Cùng một điều kiện được dùng ở nhiều use case.
- Tiêu chí gồm nhiều điều kiện nhỏ cần kết hợp.
- Quy tắc có khả năng thay đổi theo thời gian hoặc theo chính sách.
- Cần kiểm thử riêng tiêu chí mà không phải chạy toàn bộ use case.
- Cần dùng cùng tiêu chí để đánh giá một đối tượng hoặc tìm các đối tượng thỏa điều kiện.
- Muốn diễn đạt điều kiện phức tạp thành những thành phần có thể đọc và trao đổi.

Ví dụ, điều kiện “số lượng lớn hơn 0” thường có thể được kiểm tra trực tiếp trong Quantity Value Object. Nhưng “khách hàng đủ điều kiện tham gia chương trình khách hàng thân thiết” có thể gồm hạng thành viên, thời gian hoạt động, số điểm và trạng thái tài khoản; đây là một khái niệm phù hợp hơn với Specification.

### Không tạo Specification cho mọi phép so sánh

Nếu mỗi biểu thức như age > 18 hoặc quantity > 0 đều được biến thành một class riêng, mô hình sẽ có quá nhiều abstraction và khó theo dõi. Hãy ưu tiên tiêu chí có ý nghĩa nghiệp vụ, có thể tái sử dụng hoặc có độ phức tạp đủ để cần được đặt tên.

## 3. Cấu trúc cơ bản của Specification

Một abstraction đơn giản trong Java có thể như sau:

```java
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);

    default Specification<T> and(Specification<T> other) {
        return candidate ->
                this.isSatisfiedBy(candidate)
                        && other.isSatisfiedBy(candidate);
    }

    default Specification<T> or(Specification<T> other) {
        return candidate ->
                this.isSatisfiedBy(candidate)
                        || other.isSatisfiedBy(candidate);
    }

    default Specification<T> not() {
        return candidate -> !this.isSatisfiedBy(candidate);
    }
}
```

Interface trên thể hiện ba khả năng cơ bản:

- Đánh giá một candidate bằng isSatisfiedBy.
- Kết hợp hai tiêu chí bằng AND hoặc OR.
- Phủ định một tiêu chí bằng NOT.

Đây là một cách triển khai nhỏ của Specification Pattern. Trong hệ thống thực tế, có thể cần thêm cách trả lý do không đạt, hỗ trợ query translation hoặc xử lý lỗi dữ liệu. Không nên bổ sung các khả năng đó nếu bài toán chưa cần.

### Kết hợp tiêu chí

Giả sử khách hàng được nhận ưu đãi nếu tài khoản đang hoạt động, có hạng Gold hoặc Platinum và không bị khóa.

    ActiveCustomerSpecification
        AND
    (GoldOrPlatinumSpecification)
        AND
    NotBlockedCustomerSpecification

Cách kết hợp này cho thấy một tiêu chí lớn được tạo từ các tiêu chí nhỏ, có tên riêng và có thể kiểm thử độc lập.

Cần chú ý thứ tự và short-circuit của AND/OR. Với phép AND, nếu điều kiện đầu sai thì điều kiện sau có thể không được đánh giá. Vì vậy, Specification nên tránh side effect và không nên phụ thuộc vào việc một tiêu chí khác đã chạy trước.

## 4. Ví dụ: khách hàng đủ điều kiện nhận ưu đãi

Giả sử chương trình ưu đãi dành cho khách hàng có tài khoản hoạt động, thuộc hạng Gold hoặc Platinum, và không có trạng thái bị khóa.

Một domain model đơn giản:

```java
public enum MembershipTier {
    BASIC,
    SILVER,
    GOLD,
    PLATINUM
}

public final class Customer {
    private final CustomerId id;
    private final MembershipTier tier;
    private final boolean active;
    private final boolean blocked;

    public Customer(
            CustomerId id,
            MembershipTier tier,
            boolean active,
            boolean blocked
    ) {
        this.id = Objects.requireNonNull(id);
        this.tier = Objects.requireNonNull(tier);
        this.active = active;
        this.blocked = blocked;
    }

    public MembershipTier tier() {
        return tier;
    }

    public CustomerId id() {
        return id;
    }

    public boolean isActive() {
        return active;
    }

    public boolean isBlocked() {
        return blocked;
    }
}
```

Các specification có thể được biểu diễn riêng:

```java
public final class ActiveCustomer
        implements Specification<Customer> {

    @Override
    public boolean isSatisfiedBy(Customer customer) {
        return customer.isActive();
    }
}

public final class PremiumMember
        implements Specification<Customer> {

    @Override
    public boolean isSatisfiedBy(Customer customer) {
        return customer.tier() == MembershipTier.GOLD
                || customer.tier() == MembershipTier.PLATINUM;
    }
}

public final class NotBlockedCustomer
        implements Specification<Customer> {

    @Override
    public boolean isSatisfiedBy(Customer customer) {
        return !customer.isBlocked();
    }
}
```

Application hoặc domain service có thể kết hợp:

```java
Specification<Customer> eligibleForCampaign =
        new ActiveCustomer()
                .and(new PremiumMember())
                .and(new NotBlockedCustomer());

boolean eligible =
        eligibleForCampaign.isSatisfiedBy(customer);
```

Tên specification tổng hợp có thể được tạo thành một class riêng nếu chương trình ưu đãi là một khái niệm nghiệp vụ quan trọng:

```java
public final class EligibleForPremiumCampaign
        implements Specification<Customer> {

    private final Specification<Customer> delegate =
            new ActiveCustomer()
                    .and(new PremiumMember())
                    .and(new NotBlockedCustomer());

    @Override
    public boolean isSatisfiedBy(Customer customer) {
        return delegate.isSatisfiedBy(customer);
    }
}
```

Cách làm này giúp use case diễn đạt trực tiếp ý định nghiệp vụ:

    if (eligibleForPremiumCampaign.isSatisfiedBy(customer)) {
        campaign.applyTo(customer);
    }

Nếu chương trình thay đổi để bổ sung điều kiện về ngày tham gia hoặc giới hạn khu vực, nhóm có thể thay đổi specification tổng hợp và các thành phần liên quan mà không phải tìm kiếm nhiều biểu thức điều kiện rải rác.

## 5. Specification và Invariant của Aggregate

Specification và invariant đều liên quan đến điều kiện, nhưng chúng có vai trò khác nhau.

**Invariant** là quy tắc phải luôn đúng trong phạm vi một Entity hoặc Aggregate. Aggregate Root chịu trách nhiệm bảo vệ invariant khi trạng thái thay đổi.

**Specification** đóng gói một tiêu chí có thể đánh giá. Nó có thể mô tả điều kiện đủ tư cách, điều kiện tìm kiếm hoặc một quy tắc có tên. Specification không tự động trở thành nơi duy nhất bảo vệ invariant.

Ví dụ:

- Invariant: số lượng của OrderLine luôn lớn hơn 0.
- Specification: đơn hàng đủ điều kiện giao miễn phí.
- Invariant: đơn đã đóng không thể thêm dòng hàng.
- Specification: đơn hàng thuộc nhóm cần kiểm tra thủ công.

Nếu một quy tắc phải đúng sau mọi hành vi làm thay đổi Aggregate, hãy bảo vệ nó trong Aggregate hoặc Value Object. Không nên chỉ gọi một Specification ở một controller rồi cho rằng invariant đã được bảo đảm.

| Câu hỏi | Invariant | Specification |
|---|---|---|
| Mục tiêu | Bảo vệ tính hợp lệ của state | Đánh giá một tiêu chí có tên |
| Phạm vi | Entity/Aggregate và các thay đổi của nó | Candidate hoặc tập đối tượng được đánh giá |
| Khi nào chạy | Mỗi khi có hành vi có thể ảnh hưởng invariant | Khi use case cần hỏi tiêu chí |
| Kết quả | State không hợp lệ bị ngăn chặn | Đạt/không đạt, hoặc kết quả đánh giá chi tiết |
| Ví dụ | Tổng số lượng trong Order không âm | Order đủ điều kiện giao nhanh |

Một Specification có thể hỗ trợ kiểm tra invariant, nhưng Aggregate vẫn cần kiểm soát các đường thay đổi để không ai bỏ qua bước đánh giá.

## 6. Specification và Policy khác nhau thế nào?

Specification thường trả lời một câu hỏi điều kiện: “đối tượng này có thỏa tiêu chí không?”. Policy thường mô tả cách quyết định hoặc hành động khi có một bối cảnh cụ thể.

Ví dụ trong chương trình khuyến mại:

- Specification: khách hàng có đủ điều kiện tham gia chiến dịch không?
- Policy: nếu đủ điều kiện, mức giảm giá được tính như thế nào?
- Strategy: thuật toán tính ưu đãi nào được chọn theo loại chiến dịch?

Một policy có thể dùng một hoặc nhiều specification làm đầu vào, nhưng hai khái niệm không đồng nhất.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Specification | Đánh giá một tiêu chí | Khách hàng có đủ điều kiện nhận ưu đãi không? |
| Policy | Quy định cách xử lý hoặc ra quyết định | Khách hàng đủ điều kiện được giảm 10% hay 15%? |
| Strategy | Cung cấp một thuật toán có thể thay thế | Tính phí vận chuyển theo khoảng cách hay theo trọng lượng? |
| Invariant | Bảo vệ state luôn hợp lệ | Tổng tiền không âm; đơn đã đóng không thể sửa |

Nếu Specification bắt đầu tính toán kết quả phức tạp, gọi nhiều dịch vụ và thay đổi state, có thể nó đang gánh trách nhiệm của policy hoặc application service.

## 7. Specification dùng để kiểm tra hay dùng để truy vấn?

Có hai tình huống thường gặp:

1. Đã có một đối tượng và cần hỏi nó có thỏa điều kiện không.
2. Cần tìm các đối tượng trong kho dữ liệu thỏa điều kiện.

Cả hai có thể dùng cùng một khái niệm nghiệp vụ, nhưng cách thực thi khác nhau.

### Kiểm tra một candidate

Khi candidate đã có trong bộ nhớ, Specification có thể đánh giá trực tiếp:

    boolean eligible =
            specification.isSatisfiedBy(customer);

Đây là cách dùng đơn giản và phù hợp cho logic domain có dữ liệu cần thiết sẵn có.

### Tìm nhiều candidate

Nếu cần tìm tất cả khách hàng đủ điều kiện trong database, không nên tải hàng triệu khách hàng về bộ nhớ rồi gọi isSatisfiedBy từng object.

Thay vào đó, query layer cần chuyển tiêu chí sang SQL, Criteria API, query DSL hoặc cơ chế truy vấn tương ứng.

Ví dụ:

    SELECT *
    FROM customer
    WHERE active = true
      AND blocked = false
      AND tier IN ('GOLD', 'PLATINUM');

Một số hệ thống xây dựng Query Specification hoặc Criteria Object để biểu diễn điều kiện có thể dịch sang database. Đây là phần query/persistence, không nên tự động đồng nhất với Domain Specification chỉ có isSatisfiedBy.

### Hai abstraction có thể cùng tồn tại

Một thiết kế có thể có:

    Domain Specification
        -> isSatisfiedBy(Customer)

    Query Specification
        -> toPredicate(CriteriaBuilder, Root<Customer>)

Domain Specification diễn đạt ý nghĩa nghiệp vụ. Query Specification biểu diễn cách truy vấn dữ liệu trong công nghệ cụ thể. Nếu hai phần cùng phản ánh một tiêu chí, cần có kiểm thử để bảo đảm chúng không lệch nhau khi chính sách thay đổi.

Không nên đưa CriteriaBuilder, SQL string hoặc ORM entity vào domain specification nếu mục tiêu là giữ domain độc lập với persistence.

## 8. Tránh truy vấn repository bên trong Specification

Một Specification lý tưởng đánh giá dữ liệu đã được cung cấp, thay vì âm thầm gọi repository hoặc HTTP service.

Ví dụ thiết kế khó kiểm soát:

```java
public final class EligibleCustomer
        implements Specification<Customer> {

    private final CustomerRepository customers;
    private final PaymentGateway payments;

    @Override
    public boolean isSatisfiedBy(Customer customer) {
        boolean active = customers.isActive(customer.id());
        boolean paid = payments.hasNoOverdueDebt(customer.id());

        return active && paid;
    }
}
```

Vấn đề:

- Mỗi lần đánh giá có thể phát sinh nhiều truy vấn.
- Khó dự đoán độ trễ và số lần gọi.
- Specification không còn là phép đánh giá thuần.
- Unit test cần mock nhiều phụ thuộc.
- Kết quả có thể thay đổi giữa các lần đánh giá do dữ liệu bên ngoài thay đổi.
- Khi kết hợp AND/OR, short-circuit có thể làm số lần gọi dịch vụ khó đoán.

Có thể tách việc thu thập dữ liệu khỏi việc đánh giá:

1. Application service lấy các dữ kiện cần thiết qua repository hoặc port.
2. Application tạo một candidate hoặc context chứa dữ liệu.
3. Specification đánh giá candidate đó.
4. Application quyết định bước tiếp theo.

Ví dụ:

    public record CustomerEligibilityContext(
            Customer customer,
            boolean hasOverdueDebt,
            Instant evaluatedAt
    ) {}

    public final class EligibleForCampaign
            implements Specification<CustomerEligibilityContext> {

        @Override
        public boolean isSatisfiedBy(
                CustomerEligibilityContext context
        ) {
            return context.customer().isActive()
                    && !context.customer().isBlocked()
                    && !context.hasOverdueDebt();
        }
    }

Cách này làm rõ dữ liệu nào được dùng để đánh giá và giúp kiểm thử tiêu chí độc lập. Nếu thông tin cần lấy phải nhất quán tại một thời điểm, application cũng cần xác định transaction hoặc snapshot phù hợp.

## 9. Trả lý do không đạt thay vì chỉ boolean

Boolean phù hợp khi chỉ cần biết đạt hay không. Nhưng nhiều use case cần giải thích vì sao candidate không thỏa điều kiện.

Ví dụ, khách hàng không đủ điều kiện vì:

- Tài khoản đã bị khóa.
- Hạng thành viên chưa đạt.
- Có khoản nợ quá hạn.
- Chương trình đã hết hạn.

Có thể dùng kết quả đánh giá chi tiết:

```java
public record SpecificationResult(
        boolean satisfied,
        List<String> reasons
) {
    public SpecificationResult {
        reasons = List.copyOf(reasons);
    }

    public static SpecificationResult accepted() {
        return new SpecificationResult(true, List.of());
    }

    public static SpecificationResult rejected(String reason) {
        return new SpecificationResult(false, List.of(reason));
    }
}
```

Một specification có thể trả về nhiều lỗi để hỗ trợ form hoặc quy trình kiểm tra:

```java
public interface ExplainableSpecification<T> {
    SpecificationResult evaluate(T candidate);
}
```

Cần phân biệt lý do không đạt tiêu chí với lỗi kỹ thuật. “Khách hàng không đủ hạng thành viên” là kết quả nghiệp vụ. “Database timeout” là lỗi hạ tầng và không nên được biến thành một lý do từ chối nghiệp vụ.

Cũng cần thống nhất cách kết hợp kết quả:

- Với AND, có thể dừng ở lỗi đầu tiên hoặc thu thập mọi lý do.
- Với OR, chỉ cần một nhánh đạt có thể đủ để specification tổng hợp đạt.
- Với NOT, lý do cần được diễn đạt sao cho người dùng hiểu điều kiện bị phủ định.

Không nên tạo một framework validation quá phức tạp nếu use case chỉ cần boolean.

## 10. Tiêu chí phụ thuộc thời gian

Nhiều specification phụ thuộc vào thời gian:

- Hợp đồng còn hiệu lực tại thời điểm đánh giá.
- Khuyến mại nằm trong khoảng ngày áp dụng.
- Khách hàng đã hoạt động đủ 12 tháng.
- Đơn hàng còn trong cửa sổ cho phép hủy.
- Hồ sơ đã quá hạn cần rà soát.

Không nên gọi trực tiếp system clock rải rác trong specification vì khó kiểm thử và có thể làm cùng một use case nhận các thời điểm đánh giá khác nhau.

Hãy truyền thời điểm đánh giá rõ ràng:

    public record EvaluationContext(Instant evaluatedAt) {}

    public final class ContractCurrentlyEffective
            implements Specification<ContractEvaluation> {

        @Override
        public boolean isSatisfiedBy(
                ContractEvaluation candidate
        ) {
            Instant now = candidate.evaluatedAt();

            return !now.isBefore(candidate.contract().startsAt())
                    && now.isBefore(candidate.contract().endsAt());
        }
    }

Quy tắc về biên thời gian phải được xác định rõ. Ví dụ, endsAt có được tính là thời điểm hết hiệu lực hay thời điểm cuối cùng còn hiệu lực? Nên dùng một quy ước nhất quán và kiểm thử chính xác thời điểm biên.

Nếu command mang một thời điểm hiệu lực do nghiệp vụ quy định, hãy giữ thời điểm đó xuyên suốt use case. Nếu chính sách yêu cầu đánh giá theo thời gian hiện tại, application cần cấp một giá trị thời gian nhất quán cho lần đánh giá.

## 11. Specification thay đổi theo chính sách

Một số tiêu chí phụ thuộc vào cấu hình hoặc phiên bản chính sách. Ví dụ, mức chi tiêu tối thiểu để được miễn phí giao hàng có thể khác theo thị trường hoặc thời gian.

Không nên hard-code các giá trị thay đổi thường xuyên vào nhiều specification. Có thể truyền policy data bất biến vào constructor:

    public final class MinimumOrderValue
            implements Specification<Order> {

        private final Money threshold;

        public MinimumOrderValue(Money threshold) {
            this.threshold = Objects.requireNonNull(threshold);
        }

        @Override
        public boolean isSatisfiedBy(Order order) {
            return order.total().isGreaterThanOrEqualTo(threshold);
        }
    }

Application hoặc domain policy provider chọn threshold phù hợp với thị trường và thời điểm áp dụng rồi tạo specification.

Nếu tiêu chí phụ thuộc vào một policy version, cần ghi lại version hoặc thông tin chính sách đã dùng khi ra quyết định quan trọng. Ví dụ, đơn hàng được miễn phí vận chuyển theo chính sách tháng 11 cần có khả năng giải thích tại sao nó được miễn ở thời điểm đó, ngay cả khi ngưỡng hiện tại đã thay đổi.

## 12. Kết hợp Specification có kiểm soát

AND, OR và NOT cho phép tạo tiêu chí tổng hợp. Tuy nhiên, việc kết hợp cần giữ ý nghĩa nghiệp vụ rõ ràng.

Ví dụ:

    EligibleForExpressDelivery
        = OrderIsConfirmed
          AND DestinationSupportsExpress
          AND OrderMeetsExpressValue
          AND NOT ContainsRestrictedItem

Một số lưu ý:

- Dùng tên tổng hợp phản ánh mục tiêu nghiệp vụ.
- Không để một biểu thức ghép dài đến mức không ai hiểu được.
- Các tiêu chí nhỏ cần có trách nhiệm và ngữ nghĩa rõ.
- Tránh tạo specification có side effect vì thứ tự đánh giá có thể thay đổi.
- Xác định cách thu thập lý do khi một hoặc nhiều tiêu chí không đạt.
- Cẩn thận với NOT trên dữ liệu thiếu hoặc không xác định; không phải mọi giá trị null đều tương đương false.

### Tính chất logic

Với các specification thuần, các phép kết hợp có những tính chất quen thuộc:

- A AND B chỉ đúng khi cả A và B đúng.
- A OR B đúng khi ít nhất một trong hai đúng.
- NOT A đúng khi A sai.
- A AND A tương đương A.
- A OR A tương đương A.

Những tính chất này hữu ích khi viết test cho composition. Nhưng nếu specification có side effect hoặc phụ thuộc trạng thái bên ngoài, việc biến đổi thứ tự có thể làm thay đổi hành vi. Đó là một lý do khác để giữ phép đánh giá thuần và xác định rõ input.

## 13. Specification trong luồng application

Application layer thường điều phối dữ liệu và use case, còn specification mô tả tiêu chí nghiệp vụ.

Một luồng điển hình:

1. Nhận command hoặc yêu cầu đánh giá.
2. Tải các dữ liệu cần thiết qua repository/port.
3. Tạo evaluation context nếu tiêu chí cần thời gian, thị trường hoặc thông tin bên ngoài.
4. Gọi specification.
5. Nếu đạt, tiếp tục use case hoặc gọi hành vi Aggregate.
6. Nếu không đạt, trả kết quả nghiệp vụ phù hợp.
7. Lưu thay đổi và phát event sau commit nếu use case có thay đổi state.

Ví dụ:

```java
public final class ApplyCampaignHandler {
    private final CustomerRepository customers;
    private final CampaignRepository campaigns;
    private final Specification<CampaignEligibility> eligibility;

    public ApplyCampaignHandler(
            CustomerRepository customers,
            CampaignRepository campaigns,
            Specification<CampaignEligibility> eligibility
    ) {
        this.customers = customers;
        this.campaigns = campaigns;
        this.eligibility = eligibility;
    }

    public CampaignResult handle(ApplyCampaignCommand command) {
        Customer customer = customers.findById(command.customerId())
                .orElseThrow(CustomerNotFoundException::new);

        Campaign campaign = campaigns.findById(command.campaignId())
                .orElseThrow(CampaignNotFoundException::new);

        CampaignEligibility candidate =
                CampaignEligibility.from(customer, campaign);

        if (!eligibility.isSatisfiedBy(candidate)) {
            return CampaignResult.notEligible();
        }

        campaign.applyTo(customer.id());
        campaigns.save(campaign);

        return CampaignResult.applied();
    }
}
```

Đây là ví dụ rút gọn. Nếu việc áp dụng chiến dịch cần bảo vệ invariant của một Aggregate khác, hành vi ghi phải đi qua Aggregate Root tương ứng. Specification chỉ đánh giá tiêu chí; nó không tự cấp quyền sửa mọi đối tượng.

## 14. Specification và concurrency

Một tiêu chí có thể đúng tại thời điểm kiểm tra nhưng không còn đúng khi ghi dữ liệu.

Ví dụ, một khách hàng còn đủ hạn mức khi application đánh giá, nhưng một transaction khác tiêu thụ hạn mức trước khi use case commit.

Vì vậy:

- Specification hỗ trợ đánh giá eligibility tại một thời điểm.
- Aggregate invariant bảo vệ state khi thay đổi.
- Transaction và optimistic concurrency phát hiện cập nhật cạnh tranh.
- Khi có conflict, application có thể cần nạp lại state và đánh giá lại tiêu chí.
- Side effect chỉ được thực hiện theo một quy trình an toàn sau khi thay đổi được commit.

Không nên xem kết quả Specification như một giấy phép vĩnh viễn. Nếu tiêu chí phụ thuộc state có thể thay đổi đồng thời, cần xác định cách bảo đảm tính đúng tại thời điểm commit.

Ví dụ, specification xác định đơn đủ điều kiện sử dụng coupon có thể trả true khi kiểm tra. Nhưng Aggregate Coupon hoặc Promotion vẫn cần bảo vệ giới hạn số lượt sử dụng khi ghi nhận việc áp dụng. Nếu nhiều request cùng dùng lượt cuối, chỉ kiểm tra trước đó là chưa đủ.

## 15. Specification trong kiểm thử

Specification có thể được kiểm thử độc lập bằng các candidate đại diện cho trường hợp đạt, không đạt và biên.

Ví dụ bảng test cho miễn phí giao hàng:

| Candidate | Tổng tiền | Khu vực | Kết quả |
|---|---:|---|---|
| A | 500.000 | Được hỗ trợ | Đạt nếu ngưỡng là 500.000 |
| B | 499.999 | Được hỗ trợ | Không đạt |
| C | 600.000 | Không hỗ trợ | Không đạt |
| D | 600.000 | Được hỗ trợ | Đạt |
| E | 0 | Được hỗ trợ | Không đạt |

Cần kiểm thử cả điều kiện biên, đặc biệt là dấu lớn hơn hay lớn hơn hoặc bằng.

Ví dụ:

```java
class MinimumOrderValueTest {

    private final Specification<Order> specification =
            new MinimumOrderValue(Money.of(500_000, "VND"));

    @Test
    void acceptsOrderAtThreshold() {
        Order order = orderWithTotal(Money.of(500_000, "VND"));

        assertTrue(specification.isSatisfiedBy(order));
    }

    @Test
    void rejectsOrderBelowThreshold() {
        Order order = orderWithTotal(Money.of(499_999, "VND"));

        assertFalse(specification.isSatisfiedBy(order));
    }
}
```

Ngoài test từng specification, nên kiểm thử phép kết hợp:

- AND phải từ chối khi một nhánh không đạt.
- OR phải đạt khi có ít nhất một nhánh đạt.
- NOT đảo kết quả.
- Specification tổng hợp phản ánh đúng chính sách nghiệp vụ.
- Các giá trị null hoặc thiếu được xử lý theo hợp đồng rõ ràng.

Nếu cùng tiêu chí có cả Domain Specification và Query Specification, nên có integration test hoặc contract test xác nhận kết quả truy vấn tương đương với phép đánh giá trên candidate trong các trường hợp đại diện.

## 16. Những sai lầm thường gặp

### Biến mọi điều kiện thành Specification

Tạo class cho mọi phép so sánh nhỏ làm code phân mảnh và tăng chi phí điều hướng. Chỉ tách khi điều kiện có tên, có ý nghĩa nghiệp vụ, được dùng lại hoặc đủ phức tạp.

### Dùng Specification để thay thế invariant

Một use case gọi specification trước khi sửa Aggregate không đảm bảo mọi đường thay đổi đều tuân thủ quy tắc. Invariant cần được bảo vệ tại Aggregate hoặc Value Object.

### Specification truy cập repository và dịch vụ ngoài

Điều này làm phép đánh giá khó đoán, khó kiểm thử và có thể gây nhiều truy vấn. Hãy thu thập dữ liệu trước rồi truyền candidate/context vào specification.

### Trộn domain criteria với SQL/ORM

Đưa CriteriaBuilder, EntityManager hoặc SQL vào domain specification làm domain phụ thuộc persistence. Hãy tách query translation ở Infrastructure hoặc query layer.

### Specification có side effect

Một phép kiểm tra không nên tự gửi email, cập nhật database hoặc phát event. Side effect thuộc hành vi/use case có điều phối rõ ràng.

### Specification quá lớn

Một specification tổng hợp chứa hàng chục điều kiện không tên khiến việc hiểu và thay đổi khó khăn. Hãy chia thành các tiêu chí có tên và kiểm thử độc lập.

### Nhầm tiêu chí với policy

Specification trả lời có thỏa điều kiện không. Policy có thể quyết định hành động, mức giá hoặc cách xử lý. Hãy giữ trách nhiệm rõ.

### Dùng kết quả cũ sau khi state thay đổi

Eligibility được đánh giá trước transaction không nhất thiết còn đúng khi commit. Cần kiểm tra lại hoặc bảo vệ invariant tại nơi ghi.

### Trả boolean khi cần lý do

Một số use case cần giải thích cho người dùng hoặc audit. Khi đó hãy cân nhắc kết quả đánh giá có danh sách lý do thay vì boolean đơn giản.

## 17. Quy trình thiết kế một Specification

Có thể áp dụng quy trình sau:

1. **Thu thập ngôn ngữ nghiệp vụ:** ghi lại câu hỏi mà chuyên gia muốn trả lời.
2. **Xác định candidate:** đối tượng hoặc context nào được đánh giá?
3. **Xác định dữ liệu cần thiết:** field, trạng thái, thời gian hoặc dữ kiện bên ngoài nào cần có?
4. **Viết tiêu chí rõ ràng:** diễn đạt điều kiện bằng ngôn ngữ nghiệp vụ, xác định cả biên và trường hợp thiếu dữ liệu.
5. **Quyết định vị trí:** domain specification, application policy hay query specification?
6. **Tách tiêu chí con:** chỉ khi chúng có ý nghĩa riêng hoặc cần tái sử dụng.
7. **Xác định kết quả:** boolean hay kết quả có lý do?
8. **Kiểm thử:** trường hợp đạt, không đạt, biên và composition.
9. **Xác định tính nhất quán:** tiêu chí có thể thay đổi đồng thời không, có cần re-evaluate khi commit không?
10. **Theo dõi thay đổi chính sách:** ghi version hoặc thời điểm hiệu lực nếu quyết định cần giải thích về sau.

## 18. Checklist sử dụng Specification

Trước khi đưa một Specification vào domain model, hãy kiểm tra:

- Tiêu chí có tên và ý nghĩa nghiệp vụ rõ ràng không?
- Candidate được đánh giá đã xác định đúng chưa?
- Dữ liệu cần thiết có được cung cấp tường minh không?
- Specification có thể đánh giá mà không gọi repository hoặc dịch vụ ngoài không?
- Nó có đang thay thế một invariant cần đặt trong Aggregate không?
- Có cần kết hợp AND, OR hoặc NOT không?
- Các tiêu chí con có tên đủ rõ và được kiểm thử riêng không?
- Kết quả boolean đã đủ hay cần lý do không đạt?
- Tiêu chí có phụ thuộc thời gian hoặc phiên bản chính sách không?
- Domain specification có bị trộn với SQL/ORM query không?
- Query layer có thể thực thi tiêu chí hiệu quả mà không tải toàn bộ dữ liệu không?
- Kết quả đánh giá có thể hết hiệu lực do concurrency không?
- Có kiểm thử trường hợp biên và phép kết hợp không?

## 19. Kết luận

Specification giúp chuyển một tiêu chí nghiệp vụ thành một thành phần có tên, có thể đánh giá, kết hợp và kiểm thử. Nó làm rõ các câu hỏi về eligibility, điều kiện áp dụng và việc chọn những đối tượng phù hợp với một chính sách.

Specification phát huy hiệu quả khi được dùng đúng phạm vi: tiêu chí được đánh giá trên dữ liệu rõ ràng, không tự thực hiện side effect và không thay thế invariant của Aggregate. Khi cần truy vấn số lượng lớn, query layer có thể chuyển tiêu chí sang database bằng một abstraction phù hợp; domain model vẫn giữ ngữ nghĩa nghiệp vụ độc lập với công nghệ lưu trữ.

Kết hợp Specification với Aggregate, Policy, Repository và Application Service đúng trách nhiệm giúp quy tắc dễ đọc, dễ kiểm thử và dễ thay đổi khi chính sách kinh doanh phát triển.
