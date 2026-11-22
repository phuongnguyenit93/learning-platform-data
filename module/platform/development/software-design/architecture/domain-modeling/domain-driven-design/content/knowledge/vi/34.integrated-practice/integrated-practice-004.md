# Thiết kế Aggregate đơn hàng cùng các Value Object và bất biến

Một bài thực hành DDD cần đi từ hiểu biết nghiệp vụ đến mô hình có thể thực thi: xác định Bounded Context, thống nhất ngôn ngữ, chọn Aggregate boundary, tạo Value Object, diễn đạt invariant bằng behavior, rồi kiểm chứng bằng test. Bài này xây dựng một Order Aggregate cho một hệ thống bán hàng trực tuyến.

Mục tiêu không phải tạo một class Order có thật nhiều field. Mục tiêu là xác định rõ đơn hàng chịu trách nhiệm bảo vệ điều gì, những giá trị nào phải hợp lệ ngay khi được tạo, hành vi nào được phép ở từng trạng thái và những quyết định nào thuộc context khác.

Ví dụ xuyên suốt dùng Java record và class để minh họa. Các import và một số kiểu hạ tầng được lược bỏ để tập trung vào mô hình miền. Tên lớp và chính sách cụ thể cần được điều chỉnh theo ngôn ngữ và quy tắc của doanh nghiệp thực tế.

## 1. Bối cảnh nghiệp vụ và phạm vi bài toán

Giả sử doanh nghiệp bán sản phẩm trực tuyến. Khách hàng tạo đơn, chọn sản phẩm và số lượng, cung cấp địa chỉ giao hàng, sau đó xác nhận đơn.

Một đơn hàng cần ghi nhận:

- Khách hàng đặt đơn.
- Các dòng sản phẩm và số lượng.
- Giá từng sản phẩm tại thời điểm đặt.
- Địa chỉ nhận hàng tại thời điểm đặt.
- Phí giao hàng.
- Tổng tiền.
- Trạng thái và thời điểm xác nhận.

Hệ thống có thể có các context khác:

- Product Catalog quản lý danh mục, tên và giá chào bán hiện tại.
- Customer Management quản lý hồ sơ và thông tin liên hệ hiện tại.
- Inventory quản lý tồn kho và reservation.
- Payment quản lý authorize, capture và refund.
- Shipping quản lý vận chuyển và tracking.

Order không nên hấp thụ toàn bộ các mô hình đó. Order cần biết những dữ kiện cần thiết để biểu diễn giao dịch đã đặt và bảo vệ quy tắc của chính đơn hàng.

### Phạm vi thực hành

Bài này tập trung vào việc tạo và xác nhận đơn hàng. Quy trình giữ hàng, thanh toán và giao vận được xem là các capability của context khác. Nếu chính sách doanh nghiệp yêu cầu những bước đó phải hoàn tất trước khi đơn được xác nhận, chúng sẽ được điều phối bằng workflow hoặc Process Manager.

## 2. Xác định Bounded Context và quyền sở hữu

Trước khi thiết kế class, cần xác định Order thuộc context nào và context đó có quyền quyết định điều gì.

Trong ví dụ này, Order Management sở hữu:

- Order identity và lifecycle.
- Các dòng hàng của đơn.
- Giá và thông tin sản phẩm được chụp tại thời điểm đặt.
- Địa chỉ giao hàng snapshot.
- Phí giao hàng đã áp dụng cho đơn.
- Tổng tiền được tính từ các thành phần của đơn.
- Quy tắc đơn nào được phép xác nhận.

Order Management không sở hữu:

- Giá sản phẩm hiện tại trong catalog.
- Hồ sơ khách hàng hiện tại.
- Tồn kho thực tế của kho.
- Trạng thái giao dịch của payment provider.
- Trạng thái giao hàng từ đơn vị vận chuyển.

| Context | Dữ liệu/quyết định sở hữu | Order sử dụng như thế nào |
|---|---|---|
| Product Catalog | Product identity, mô tả và offer hiện tại | Nhận product snapshot hoặc quote |
| Customer Management | Hồ sơ và thông tin liên hệ hiện tại | Nhận CustomerId và địa chỉ được chọn |
| Order Management | Order, line, giá snapshot, địa chỉ snapshot, lifecycle | Nơi sở hữu Order Aggregate |
| Inventory | On-hand, reserved và reservation lifecycle | Gửi command yêu cầu reserve |
| Payment | Authorization, capture, refund | Gửi payment command và nhận kết quả |
| Shipping | Shipment, carrier và tracking | Nhận sự kiện đơn đã sẵn sàng fulfillment |

Một từ như Customer hoặc Product có thể có mô hình khác nhau ở các context. Order chỉ cần CustomerId và snapshot cần thiết cho giao dịch, không cần giữ toàn bộ Customer Aggregate.

### Reference và snapshot

Order giữ CustomerId để truy vết khách hàng. Nhưng địa chỉ giao hàng phải được lưu thành snapshot. Nếu khách hàng đổi địa chỉ sau khi đặt, đơn đã xác nhận vẫn phải giữ địa chỉ tại thời điểm đặt.

Tương tự, OrderLine giữ ProductId để truy vết sản phẩm và snapshot tên, SKU, đơn giá đã dùng. Không truy vấn tên và giá hiện tại mỗi lần hiển thị đơn lịch sử, vì chúng có thể đã thay đổi.

## 3. Xây dựng ngôn ngữ chung

Trước khi chọn kiểu dữ liệu, hãy thống nhất thuật ngữ với chuyên gia nghiệp vụ.

| Thuật ngữ | Ý nghĩa trong bài thực hành |
|---|---|
| Order | Đơn hàng do một khách hàng tạo |
| Order Line | Một dòng sản phẩm trong đơn |
| Product Snapshot | Thông tin sản phẩm và đơn giá được chụp khi thêm vào đơn |
| Quantity | Số lượng sản phẩm trong một dòng |
| Unit Price | Đơn giá tại thời điểm đưa sản phẩm vào đơn |
| Subtotal | Tổng tiền các dòng hàng |
| Delivery Fee | Phí giao hàng của đơn |
| Total | Subtotal cộng Delivery Fee trong phạm vi ví dụ |
| Draft | Đơn đang được chỉnh sửa |
| Confirmed | Đơn đã được xác nhận |
| Shipping Address Snapshot | Địa chỉ nhận hàng được lưu tại thời điểm đặt |

Ngôn ngữ này giúp code, API, event và trao đổi với nghiệp vụ dùng cùng ý nghĩa. Nếu doanh nghiệp phân biệt “đơn được tiếp nhận”, “đơn đã xác nhận”, “đơn đã thanh toán” và “đơn đã sẵn sàng giao”, không gộp chúng vào một trạng thái PAID hoặc COMPLETED mơ hồ.

## 4. Xác định các use case trước khi thiết kế Aggregate

Các hành vi cần hỗ trợ trong phạm vi bài:

1. Tạo một Order Draft cho Customer.
2. Thêm sản phẩm vào đơn.
3. Thay đổi số lượng một dòng.
4. Xóa một dòng.
5. Cập nhật địa chỉ giao hàng.
6. Cập nhật phí giao hàng khi đơn còn Draft.
7. Xác nhận đơn.
8. Xem chi tiết và tổng tiền của đơn.

Mỗi use case là một ý định nghiệp vụ. Không thiết kế một endpoint generic update cho phép client gửi toàn bộ object rồi thay thế state.

Các command có thể là:

    CreateOrderDraft
    AddOrderLine
    ChangeOrderLineQuantity
    RemoveOrderLine
    SetShippingAddress
    SetDeliveryFee
    ConfirmOrder

Application Layer điều phối việc tải dữ liệu và gọi behavior tương ứng trên Aggregate.

## 5. Chọn Aggregate Root và Aggregate boundary

Trong bài này, Order là Aggregate Root. OrderLine là entity con nằm bên trong Aggregate.

    Order Aggregate
    +------------------------------------------------+
    | Order                                          |
    |  - OrderId                                     |
    |  - CustomerId                                  |
    |  - Currency                                    |
    |  - Status                                      |
    |  - ShippingAddressSnapshot                     |
    |  - DeliveryFee                                 |
    |                                                |
    |  OrderLine                                     |
    |   - OrderLineId                                |
    |   - ProductSnapshot                            |
    |   - Quantity                                   |
    |                                                |
    |  OrderLine                                     |
    |   - OrderLineId                                |
    |   - ProductSnapshot                            |
    |   - Quantity                                   |
    |                                                |
    |  Behaviors: add/change/remove/confirm          |
    +------------------------------------------------+

OrderLine không được cập nhật trực tiếp từ bên ngoài. Mọi thay đổi đi qua Order để Aggregate Root có thể kiểm tra trạng thái và invariant.

### Vì sao OrderLine là Entity con?

Trong ví dụ này, mỗi dòng có OrderLineId riêng và có thể được nhắm tới bởi command thay đổi số lượng hoặc xóa dòng. Một đơn cũng có thể chứa nhiều dòng cho cùng ProductId nếu nghiệp vụ cho phép tách theo lô hoặc điều kiện giá. Vì vậy OrderLine có identity trong phạm vi Order.

Nếu nghiệp vụ không cần identity hoặc lifecycle riêng cho dòng, OrderLine có thể được mô hình hóa như Value Object. Đây là quyết định theo semantics, không phải quy tắc rằng mọi dòng đơn hàng đều phải là Entity.

### Vì sao không gom Inventory và Payment vào Order Aggregate?

Chúng có lifecycle và invariant riêng, có thể được cập nhật độc lập và có thể thuộc context khác. Đưa chúng vào cùng Aggregate sẽ tạo một ranh giới nhất quán quá lớn, khó mở rộng và không thể bảo vệ bằng một local transaction khi triển khai phân tán.

## 6. Liệt kê invariant trước khi viết code

Invariant là điều kiện phải đúng tại các ranh giới công khai của Aggregate. Viết chúng bằng ngôn ngữ nghiệp vụ trước khi triển khai.

Order Aggregate trong ví dụ có các invariant:

1. OrderId và CustomerId luôn tồn tại.
2. Mọi OrderLine có OrderLineId duy nhất trong Order.
3. Quantity của mỗi dòng luôn lớn hơn 0.
4. Unit Price và Delivery Fee không âm.
5. Mọi khoản tiền trong Order dùng cùng Currency.
6. Order chỉ được sửa khi ở trạng thái Draft.
7. Order chỉ được Confirm khi có ít nhất một dòng.
8. Order chỉ được Confirm khi đã có Shipping Address.
9. Total luôn bằng tổng tiền các dòng cộng Delivery Fee.
10. Khi Confirm thành công, trạng thái chuyển sang Confirmed và có ConfirmedAt.
11. Order đã Confirmed không thể quay lại Draft hoặc bị sửa qua các lệnh chỉnh sửa Draft.

### Phân loại theo phạm vi bảo vệ

| Quy tắc | Phạm vi | Nơi bảo vệ |
|---|---|---|
| Quantity dương | Giá trị | Quantity Value Object |
| Money có Currency | Giá trị | Money Value Object |
| Price không âm | Giá trị | Price Value Object |
| Line ID duy nhất | Aggregate | Order Root |
| Tất cả tiền cùng Currency | Aggregate | Order Root |
| Không sửa đơn đã Confirm | Aggregate | Order behavior |
| Đơn Confirm phải có line | Aggregate | Order.confirm() |
| OrderId duy nhất trong database | Persistence | Unique constraint |
| Không ghi đè phiên bản Order mới hơn | Persistence/concurrency | Optimistic locking |
| Tồn kho đủ | Inventory context | Inventory Aggregate |
| Payment được authorize | Payment context | Payment Aggregate |

Phân loại giúp tránh đặt một quy tắc ở sai layer. Order không thể tự bảo đảm tồn kho nếu Inventory là context có thẩm quyền.

## 7. Thiết kế các Value Object định danh

Không nên dùng String cho mọi loại ID. Những kiểu riêng giúp compiler và API nội bộ phân biệt CustomerId, ProductId và OrderId.

~~~java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "value");
    }
}

public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value, "value");
    }
}

public record ProductId(UUID value) {
    public ProductId {
        Objects.requireNonNull(value, "value");
    }
}

public record OrderLineId(UUID value) {
    public OrderLineId {
        Objects.requireNonNull(value, "value");
    }
}
~~~

Các record này có equality và hashCode theo value. Hai OrderId cùng UUID bằng nhau dù được tạo thành hai instance khác nhau.

Test nên xác nhận:

- Không tạo ID với null.
- Cùng UUID thì hai ID cùng loại bằng nhau.
- OrderId và CustomerId là hai kiểu khác nhau ngay cả khi cùng chứa một UUID.
- HashSet/HashMap xử lý identity value đúng.

ID không nên mang logic parse phức tạp trong Aggregate. Boundary hoặc factory có thể chuyển UUID từ request thành Value Object.

## 8. Thiết kế Quantity

Quantity biểu diễn số lượng sản phẩm trong một dòng. Với nghiệp vụ bán theo đơn vị nguyên chiếc, Quantity phải là số nguyên dương.

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new InvalidQuantity(value);
        }
    }
}
~~~

Quantity bảo vệ invariant nội tại ngay khi được tạo. OrderLine không cần lặp lại điều kiện quantity phải dương ở mọi method.

Nếu domain bán hàng theo trọng lượng hoặc thể tích, Quantity có thể cần decimal và UnitOfMeasure. Không nên đổi int thành BigDecimal mà không mô hình hóa đơn vị đo, precision và quy tắc làm tròn.

Test:

~~~java
class QuantityTest {
    @Test
    void acceptsPositiveValue() {
        assertEquals(3, new Quantity(3).value());
    }

    @ParameterizedTest
    @ValueSource(ints = {-2, -1, 0})
    void rejectsNonPositiveValue(int value) {
        assertThrows(
                InvalidQuantity.class,
                () -> new Quantity(value)
        );
    }
}
~~~

## 9. Thiết kế Money và Price

Money biểu diễn số tiền cùng Currency. Price biểu diễn một khoản tiền dùng làm giá bán và không âm.

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        amount = amount.stripTrailingZeros();
    }

    public static Money zero(Currency currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    public Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money times(Quantity quantity) {
        return new Money(
                amount.multiply(BigDecimal.valueOf(quantity.value())),
                currency
        );
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IncompatibleCurrency(currency, other.currency);
        }
    }
}
~~~

Price giới hạn cách sử dụng Money trong ngữ cảnh giá bán:

~~~java
public record Price(Money money) {
    public Price {
        Objects.requireNonNull(money, "money");

        if (money.amount().signum() < 0) {
            throw new InvalidPrice(money.amount());
        }
    }

    public Currency currency() {
        return money.currency();
    }
}
~~~

Trong ví dụ này Money cho phép biểu diễn số âm để dùng ở những phép tính hoặc domain khác; Price không cho phép giá bán âm. Nếu Order Management chỉ dùng các khoản thu không âm, có thể giới hạn thêm ở các Value Object chuyên biệt.

### Quy tắc precision và rounding

Ví dụ trên chuẩn hóa scale dư bằng stripTrailingZeros nhưng chưa áp dụng quy tắc scale theo currency. Trong hệ thống thật, cần một CurrencyPolicy hoặc MoneyFactory quy định:

- Số chữ số thập phân được phép.
- Làm tròn ở bước nào.
- Mode làm tròn.
- Precision của phép tính trung gian.
- Cách xử lý currency không có minor unit chuẩn.

Không tự làm tròn trong mọi phép cộng hoặc nhân. Hãy áp dụng rounding ở ranh giới nghiệp vụ đã thống nhất, ví dụ khi tính thuế hoặc phát hành chứng từ.

### Kiểm thử Money

- Cộng hai Money cùng currency.
- Từ chối phép cộng khác currency.
- Nhân Money với Quantity.
- Hai Money cùng giá trị số và currency có equality đúng theo normalization.
- Money khác currency không bằng nhau.
- Price từ chối amount âm.
- Zero giữ đúng currency.

## 10. Thiết kế Product Snapshot

Order cần biết sản phẩm nào đã được đặt và giá nào đã được dùng. Thông tin này là snapshot tại thời điểm tạo dòng, không phải bản sao đầy đủ Product Aggregate.

~~~java
public record ProductSnapshot(
        ProductId productId,
        String sku,
        String name,
        Price unitPrice
) {
    public ProductSnapshot {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(unitPrice);

        sku = requireText(sku, "sku");
        name = requireText(name, "name");
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value.trim();
    }
}
~~~

Snapshot giúp đơn lịch sử giữ được tên và giá tại thời điểm đặt ngay cả khi Catalog đổi tên hoặc giá sản phẩm.

Order không nên gọi Product Catalog trong constructor hoặc method của Aggregate. Application Layer lấy offer từ Catalog rồi truyền ProductSnapshot vào Order behavior.

Nếu giá có thời hạn, snapshot có thể lưu QuoteId và ValidUntil. Application phải xác minh quote còn hiệu lực trước khi xác nhận theo policy. Không để Aggregate tự gọi HTTP để kiểm tra quote.

## 11. Thiết kế Shipping Address Snapshot

Địa chỉ giao hàng là dữ liệu lịch sử của đơn. Không nên chỉ giữ CustomerId rồi mỗi lần đọc đơn lại lấy địa chỉ hiện tại của khách hàng.

~~~java
public record AddressSnapshot(
        String recipient,
        String line1,
        String ward,
        String city,
        String postalCode,
        String countryCode
) {
    public AddressSnapshot {
        recipient = required(recipient, "recipient");
        line1 = required(line1, "line1");
        ward = required(ward, "ward");
        city = required(city, "city");
        postalCode = required(postalCode, "postalCode");
        countryCode = required(countryCode, "countryCode")
                .toUpperCase(Locale.ROOT);
    }

    private static String required(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new InvalidAddressField(field);
        }
        return value.trim();
    }
}
~~~

Đây là mô hình tối thiểu cho ví dụ. Domain thực tế có thể cần ProvinceCode, DistrictCode, delivery instruction hoặc quy tắc địa chỉ theo quốc gia.

Test cần xác nhận:

- Field bắt buộc không null hoặc blank.
- Normalization được áp dụng đúng policy.
- Equality dựa trên các thành phần có ý nghĩa.
- AddressSnapshot không thay đổi khi hồ sơ Customer thay đổi.
- Không expose mutable collection hoặc object bên ngoài.

## 12. Thiết kế OrderLine

OrderLine là entity con của Order. Nó có identity riêng trong phạm vi đơn và giữ ProductSnapshot cùng Quantity.

~~~java
public final class OrderLine {
    private final OrderLineId id;
    private final ProductSnapshot product;
    private Quantity quantity;

    OrderLine(
            OrderLineId id,
            ProductSnapshot product,
            Quantity quantity
    ) {
        this.id = Objects.requireNonNull(id);
        this.product = Objects.requireNonNull(product);
        this.quantity = Objects.requireNonNull(quantity);
    }

    boolean idEquals(OrderLineId candidate) {
        return id.equals(candidate);
    }

    void changeQuantity(Quantity newQuantity) {
        this.quantity = Objects.requireNonNull(newQuantity);
    }

    Money lineTotal() {
        return product.unitPrice().money().times(quantity);
    }

    OrderLineView view() {
        return new OrderLineView(
                id,
                product,
                quantity,
                lineTotal()
        );
    }
}
~~~

Constructor và method thay đổi package-private trong ví dụ để caller bên ngoài không tự tạo hoặc sửa child entity tùy ý. Trong implementation thực tế có thể đặt OrderLine là nested class private của Order để giới hạn truy cập chặt hơn.

OrderLine không tự phát event hoặc lưu repository riêng. Lifecycle của nó nằm trong Order Aggregate.

### Khi nào OrderLine nên là Value Object?

Nếu dòng hàng không có identity riêng, không được tham chiếu độc lập và mọi thay đổi đều thay thế toàn bộ giá trị dòng, có thể dùng record bất biến. Khi đó Order thay dòng cũ bằng một OrderLine Value Object mới. Chọn dựa trên nhu cầu domain.

## 13. Thiết kế Order Aggregate Root

Order là nơi bảo vệ invariant giữa các dòng, currency, địa chỉ, phí giao hàng và lifecycle.

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED
}
~~~

Một phần triển khai Order:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final Currency currency;
    private final List<OrderLine> lines = new ArrayList<>();

    private AddressSnapshot shippingAddress;
    private Price deliveryFee;
    private OrderStatus status = OrderStatus.DRAFT;
    private Instant confirmedAt;
    private final List<DomainEvent> domainEvents = new ArrayList<>();

    private Order(
            OrderId id,
            CustomerId customerId,
            Currency currency
    ) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.currency = Objects.requireNonNull(currency);
        this.deliveryFee = new Price(Money.zero(currency));
    }

    public static Order draft(
            OrderId id,
            CustomerId customerId,
            Currency currency
    ) {
        return new Order(id, customerId, currency);
    }

    public void addLine(
            OrderLineId lineId,
            ProductSnapshot product,
            Quantity quantity
    ) {
        ensureDraft();
        Objects.requireNonNull(lineId);
        Objects.requireNonNull(product);
        Objects.requireNonNull(quantity);
        requireCurrency(product.unitPrice().currency());

        boolean duplicateId = lines.stream()
                .anyMatch(line -> line.idEquals(lineId));

        if (duplicateId) {
            throw new DuplicateOrderLineId(lineId);
        }

        lines.add(new OrderLine(lineId, product, quantity));
    }

    public void changeLineQuantity(
            OrderLineId lineId,
            Quantity quantity
    ) {
        ensureDraft();
        Objects.requireNonNull(quantity);
        findLine(lineId).changeQuantity(quantity);
    }

    public void removeLine(OrderLineId lineId) {
        ensureDraft();

        boolean removed = lines.removeIf(line -> line.idEquals(lineId));
        if (!removed) {
            throw new OrderLineNotFound(lineId);
        }
    }

    public void setShippingAddress(AddressSnapshot address) {
        ensureDraft();
        this.shippingAddress = Objects.requireNonNull(address);
    }

    public void setDeliveryFee(Price fee) {
        ensureDraft();
        Objects.requireNonNull(fee);
        requireCurrency(fee.currency());
        this.deliveryFee = fee;
    }

    public Money subtotal() {
        return lines.stream()
                .map(OrderLine::lineTotal)
                .reduce(Money.zero(currency), Money::plus);
    }

    public Money total() {
        return subtotal().plus(deliveryFee.money());
    }

    public void confirm(Instant now) {
        ensureDraft();

        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBeConfirmed();
        }

        if (shippingAddress == null) {
            throw new ShippingAddressRequired();
        }

        confirmedAt = Objects.requireNonNull(now);
        status = OrderStatus.CONFIRMED;

        domainEvents.add(
                new OrderConfirmed(id, confirmedAt, total())
        );
    }

    public List<OrderLineView> lines() {
        return lines.stream()
                .map(OrderLine::view)
                .toList();
    }

    public OrderStatus status() {
        return status;
    }

    public Optional<Instant> confirmedAt() {
        return Optional.ofNullable(confirmedAt);
    }

    public List<DomainEvent> domainEvents() {
        return List.copyOf(domainEvents);
    }

    void clearDomainEvents() {
        domainEvents.clear();
    }

    private OrderLine findLine(OrderLineId lineId) {
        return lines.stream()
                .filter(line -> line.idEquals(lineId))
                .findFirst()
                .orElseThrow(() -> new OrderLineNotFound(lineId));
    }

    private void requireCurrency(Currency candidate) {
        if (!currency.equals(candidate)) {
            throw new IncompatibleCurrency(currency, candidate);
        }
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderNotEditable(status);
        }
    }
}
~~~

Đoạn code là bản phác thảo domain behavior. Trong cùng class cần có accessor identity phù hợp và method idEquals trên OrderLine, hoặc triển khai so sánh trực tiếp line.id() với lineId. Có thể đặt OrderLine private static nested class để không cần public accessor.

Điểm quan trọng là caller chỉ gọi behavior trên Order. Không có setter public cho status, total hoặc collection lines.

### Vì sao Total không được lưu như field mutable?

Total được tính từ các dòng và phí giao hàng. Nếu lưu cả subtotal, line totals và total rồi cập nhật từng field, có thể xuất hiện state lệch khi một đường code quên cập nhật một giá trị.

Với quy mô Aggregate phù hợp, tính toán total từ state hiện tại giúp loại bỏ một invariant đồng bộ không cần thiết. Nếu cần lưu snapshot total để tối ưu hoặc phục vụ chứng từ, phải xác định rõ thời điểm chốt và cách bảo vệ nó.

## 14. Rà soát và hoàn thiện Aggregate Root

Trước khi dùng code làm nền tảng, hãy rà các chi tiết kỹ thuật để API đúng như ý định:

- OrderLine cần cung cấp identity chỉ đọc hoặc là nested class private để Order có thể so sánh line ID.
- List trả ra phải là view bất biến; không trả trực tiếp List<OrderLine>.
- ProductSnapshot, Quantity, Price và AddressSnapshot đều bất biến.
- Không cho caller sửa OrderLine ngoài Aggregate Root.
- Tất cả method thay đổi state đều gọi ensureDraft().
- Currency được kiểm tra trước khi thêm line hoặc thay Delivery Fee.
- Domain event chỉ được ghi nhận sau khi hành vi thành công.
- Không phát event từ constructor hoặc từ thao tác migration reconstitution.

Một phiên bản hoàn thiện có thể dùng nested class private:

~~~java
private static final class OrderLine {
    private final OrderLineId id;
    private final ProductSnapshot product;
    private Quantity quantity;

    private OrderLine(
            OrderLineId id,
            ProductSnapshot product,
            Quantity quantity
    ) {
        this.id = id;
        this.product = product;
        this.quantity = quantity;
    }

    private boolean idEquals(OrderLineId candidate) {
        return id.equals(candidate);
    }

    private void changeQuantity(Quantity value) {
        quantity = value;
    }

    private Money lineTotal() {
        return product.unitPrice().money().times(quantity);
    }

    private OrderLineView view() {
        return new OrderLineView(id, product, quantity, lineTotal());
    }
}
~~~

Order có thể gọi idEquals, changeQuantity, lineTotal và view vì Order sở hữu nested class. Caller không thể truy cập implementation của OrderLine.

## 15. Tạo read-only view cho Aggregate

Không trả entity con mutable ra ngoài. Một read-only view có thể là record:

~~~java
public record OrderLineView(
        OrderLineId id,
        ProductSnapshot product,
        Quantity quantity,
        Money lineTotal
) {
}
~~~

Method lines() tạo list mới bằng stream.toList(). ProductSnapshot, Quantity và Money đều bất biến, nên caller không thể thay đổi state nội bộ qua view.

DTO API có thể được tạo từ OrderLineView. Không nhất thiết expose domain record trực tiếp ra HTTP response; Application/Presentation layer có thể map sang OrderResponse.

## 16. Xác định state transition

Trong phạm vi bài, Order có hai trạng thái:

    DRAFT
      |
      | confirm
      v
    CONFIRMED

Các hành vi chỉnh sửa chỉ được phép khi Draft:

| Hành vi | Draft | Confirmed |
|---|---|---|
| Add line | Cho phép | Từ chối |
| Change quantity | Cho phép | Từ chối |
| Remove line | Cho phép | Từ chối |
| Set address | Cho phép | Từ chối |
| Set delivery fee | Cho phép | Từ chối |
| Confirm | Cho phép nếu đủ điều kiện | Từ chối |

Không có setter status để caller nhảy trực tiếp từ Draft sang Confirmed. Chỉ method confirm() được phép thực hiện chuyển trạng thái và kiểm tra precondition.

Nếu domain có hủy đơn, cần bổ sung trạng thái và policy riêng. Ví dụ đơn đã xác nhận nhưng chưa fulfillment có thể được hủy; đơn đã giao không thể xử lý như Draft. Không nên thêm CANCELLED mà chưa xác định các điều kiện và side effect.

## 17. Kiểm tra invariant khi thêm, sửa và xóa dòng

Các method thay đổi dòng cần duy trì invariant ngay sau khi hoàn tất.

### Add line

Precondition:

- Order đang Draft.
- Line ID chưa tồn tại.
- ProductSnapshot hợp lệ.
- Unit Price dùng cùng currency.
- Quantity hợp lệ.

Postcondition:

- Có thêm đúng một line.
- Subtotal tăng bằng line total mới.
- Các line cũ không đổi.

### Change quantity

Precondition:

- Order đang Draft.
- Line ID tồn tại.
- Quantity mới dương.

Postcondition:

- Quantity của đúng line được thay đổi.
- Line total và Order total được tính lại từ state.
- Các line khác không đổi.

### Remove line

Precondition:

- Order đang Draft.
- Line ID tồn tại.

Postcondition:

- Chỉ line được chọn bị xóa.
- Total giảm theo line total đã bỏ.
- Order có thể trở thành rỗng nhưng không thể Confirm khi rỗng.

Việc cho phép Draft rỗng giúp người dùng tạo đơn trước rồi thêm sản phẩm. Nếu nghiệp vụ không cho phép Draft rỗng, có thể đặt precondition khác ở use case tạo đơn.

## 18. Xác nhận đơn hàng

Confirm là hành vi có ý nghĩa nghiệp vụ, không chỉ là cập nhật status.

Precondition:

- Order đang Draft.
- Có ít nhất một OrderLine.
- Có Shipping Address Snapshot.
- Các invariant về currency và tiền vẫn hợp lệ.
- Các dữ kiện cần chốt đã được xác nhận theo policy của Order context.

Postcondition:

- Status là Confirmed.
- ConfirmedAt được ghi nhận.
- Order không thể tiếp tục chỉnh sửa qua các Draft commands.
- Domain event OrderConfirmed được ghi nhận.

Hành vi không được tự gửi email, gọi Payment Provider hoặc trừ tồn kho. Những side effect đó thuộc application workflow hoặc consumer sau khi transaction commit.

### Failure contract

Nếu Order rỗng hoặc thiếu địa chỉ, confirm bị từ chối và state giữ nguyên Draft. Không được ghi ConfirmedAt hoặc phát OrderConfirmed.

Test cần xác nhận cả lỗi và việc state không thay đổi.

## 19. Tính tổng tiền và rounding policy

Trong ví dụ:

\[
LineTotal = UnitPrice \times Quantity
\]

\[
Subtotal = \sum LineTotal
\]

\[
Total = Subtotal + DeliveryFee
\]

Tất cả khoản tiền phải cùng currency. Không cộng 100 USD với 100 EUR chỉ vì chúng cùng là BigDecimal.

Nếu doanh nghiệp có thuế hoặc discount, mở rộng mô hình theo policy:

\[
Total = Subtotal - Discount + Tax + DeliveryFee
\]

Nhưng cần xác định:

- Discount áp dụng theo line hay toàn đơn?
- Thuế tính trước hay sau discount?
- Rounding ở từng line hay tổng đơn?
- Phí giao hàng có chịu thuế không?
- Currency và tỷ giá được chốt tại thời điểm nào?

Không thêm công thức thuế tùy ý vào Order. Có thể cần Pricing/Tax domain service hoặc một context sở hữu policy tương ứng. Order lưu kết quả snapshot đã được chấp thuận.

## 20. Domain Event từ Aggregate

Khi confirm thành công, Order ghi nhận một fact:

~~~java
public interface DomainEvent {
    Instant occurredAt();
}

public record OrderConfirmed(
        OrderId orderId,
        Instant occurredAt,
        Money total
) implements DomainEvent {
}
~~~

Event diễn đạt điều đã xảy ra, không phải yêu cầu thực hiện hành động. OrderConfirmed có thể được consumer dùng để bắt đầu fulfillment, tạo invoice hoặc gửi notification theo policy.

Event nên có:

- Event identity.
- Aggregate identity.
- Thời điểm xảy ra.
- Version hoặc sequence nếu cần.
- Correlation/causation ID ở integration boundary.
- Payload tối thiểu đủ cho consumer.

Không đưa toàn bộ Order Aggregate vào event. Consumer không nên phụ thuộc implementation nội bộ của Order.

### Domain Event và Integration Event

Domain Event có thể là kiểu nội bộ của Order Management. Khi publish ra context khác, Application/Integration layer có thể chuyển nó thành integration event với schema/version ổn định.

Điều này cho phép domain model thay đổi mà không buộc mọi consumer phải dùng cùng Java class.

## 21. Repository cho Aggregate Root

Repository làm việc với Aggregate Root. Không tạo OrderLineRepository riêng nếu OrderLine chỉ có lifecycle bên trong Order.

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);

    void save(Order order);
}
~~~

Repository contract cần rõ:

- Load một Order hoàn chỉnh trong phạm vi Aggregate.
- Save state của Order.
- Dùng optimistic locking nếu nhiều request có thể cập nhật cùng Order.
- Không âm thầm ghi đè version mới hơn.
- Transaction commit thuộc Unit of Work hoặc Application transaction boundary.

Không nên để controller tự gọi nhiều DAO để sửa Order, OrderLine và total riêng lẻ. Điều đó bỏ qua Aggregate Root và làm invariant bị phân tán.

## 22. Application Layer điều phối use case

Application Layer nhận command, tải Aggregate, lấy dữ liệu cần thiết từ context khác qua port, gọi behavior và lưu kết quả.

Ví dụ thêm dòng hàng:

~~~java
public final class AddOrderLineHandler {
    private final OrderRepository orders;
    private final ProductCatalog products;
    private final OrderLineIdGenerator lineIds;

    public void handle(AddOrderLineCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(OrderNotFound::new);

        ProductSnapshot product = products.getOffer(
                command.productId()
        );

        order.addLine(
                lineIds.next(),
                product,
                command.quantity()
        );

        orders.save(order);
    }
}
~~~

ProductCatalog là port của application. Adapter có thể gọi module Catalog trong cùng process hoặc gọi service qua HTTP. Order Aggregate chỉ nhận ProductSnapshot và không biết giao thức bên ngoài.

### Xác định ai sở hữu việc lấy dữ liệu

Application tải Product Offer vì use case cần giá và tên sản phẩm. Aggregate kiểm tra currency và quy tắc nội tại. Catalog vẫn sở hữu giá hiện tại và tính hợp lệ của offer.

Nếu quote có expiry, handler xác minh quote còn hiệu lực theo contract. Nếu xác minh cần diễn ra đồng thời với confirm, cần cơ chế quote/version hoặc reservation phù hợp; chỉ kiểm tra một lần trước đó có thể bị stale.

## 23. Transaction và Domain Event Outbox

Một use case lưu Order và ghi outbox event trong cùng local database transaction:

    Begin transaction
       |
       v
    Load Order
       |
       v
    Order.confirm()
       |
       v
    Save Order
       |
       v
    Insert OrderConfirmed into Outbox
       |
       v
    Commit transaction
       |
       v
    Outbox Publisher sends event

Nếu transaction rollback, cả thay đổi Order và outbox record đều không được commit. Publisher đọc outbox sau commit và gửi event. Consumer phải idempotent vì message có thể được giao nhiều lần.

Không publish event trước khi database commit nếu không muốn consumer nhìn thấy một OrderConfirmed mà dữ liệu Order chưa được lưu bền vững.

## 24. Những quy tắc thuộc Inventory và Payment

Một Order có thể cần giữ hàng và thanh toán. Nhưng những invariant này không thuộc Order Aggregate nếu Inventory và Payment là owner riêng.

Inventory bảo vệ:

- On-hand không âm.
- Reserved không vượt On-hand.
- Một reservation không được release hoặc consume hai lần.

Payment bảo vệ:

- Capture không vượt authorized amount.
- Refund không vượt captured amount.
- Idempotency cho external payment request.

Order không được đọc bảng Inventory hoặc Payment để tự sửa số dư. Nó gửi command đến context sở hữu và xử lý kết quả.

### Khi xác nhận phụ thuộc nhiều context

Nếu policy yêu cầu phải reserve stock và authorize payment trước khi Confirmed, có thể dùng Process Manager:

    CheckoutRequested
          |
          v
    Reserve Inventory
          |
          +---- rejected ---> Order Rejected / Needs Attention
          |
          v
    Authorize Payment
          |
          +---- rejected ---> Release Reservation
          |
          v
    Confirm Order
          |
          v
    Checkout Completed

Trong workflow này, Order có thể có trạng thái trung gian như PendingConfirmation. Các trạng thái đó phải được mô hình hóa theo semantics thực tế. Không kéo Reservation và Payment vào Order Aggregate chỉ để tránh eventual consistency.

## 25. Kiểm thử Value Object

Value Object test chạy nhanh và không cần database.

### Quantity

~~~java
@Test
void quantityMustBePositive() {
    assertThrows(
            InvalidQuantity.class,
            () -> new Quantity(0)
    );
}
~~~

### Money

~~~java
@Test
void moneyAdditionRequiresSameCurrency() {
    Money usd = new Money(
            new BigDecimal("10.00"),
            Currency.getInstance("USD")
    );
    Money eur = new Money(
            new BigDecimal("5.00"),
            Currency.getInstance("EUR")
    );

    assertThrows(
            IncompatibleCurrency.class,
            () -> usd.plus(eur)
    );
}
~~~

### Address immutability

Vì AddressSnapshot chỉ chứa String bất biến, caller không thể sửa các field sau khi tạo. Nếu sau này thêm collection hoặc array, cần defensive copy và test aliasing cả đầu vào lẫn đầu ra.

### Money equality

Do Money chuẩn hóa BigDecimal bằng stripTrailingZeros, hai giá trị 10.0 USD và 10.00 USD có representation tương đương và equality đúng. Hai giá trị khác currency không bằng nhau.

## 26. Kiểm thử Aggregate invariant

Test Aggregate phải xác nhận cả hành vi thành công lẫn thất bại.

~~~java
class OrderTest {
    @Test
    void cannotConfirmEmptyOrder() {
        Order order = draftOrder();

        assertThrows(
                EmptyOrderCannotBeConfirmed.class,
                () -> order.confirm(Instant.parse("2026-01-01T10:00:00Z"))
        );

        assertEquals(OrderStatus.DRAFT, order.status());
        assertTrue(order.confirmedAt().isEmpty());
        assertTrue(order.domainEvents().isEmpty());
    }

    @Test
    void confirmRequiresShippingAddress() {
        Order order = draftOrder();
        order.addLine(
                lineId("L-1"),
                product("P-1", "Keyboard", "50.00", "USD"),
                new Quantity(1)
        );

        assertThrows(
                ShippingAddressRequired.class,
                () -> order.confirm(Instant.parse("2026-01-01T10:00:00Z"))
        );

        assertEquals(OrderStatus.DRAFT, order.status());
    }

    @Test
    void confirmedOrderCannotBeEdited() {
        Order order = completeDraftOrder();
        order.confirm(Instant.parse("2026-01-01T10:00:00Z"));

        assertThrows(
                OrderNotEditable.class,
                () -> order.addLine(
                        lineId("L-2"),
                        product("P-2", "Mouse", "20.00", "USD"),
                        new Quantity(1)
                )
        );
    }
}
~~~

Các helper draftOrder(), lineId(), product() và completeDraftOrder() là test fixture tạo dữ liệu hợp lệ, không phải API production.

### Kiểm tra tổng tiền

Với một line giá 50.00 USD, quantity 2 và phí giao hàng 5.00 USD:

- Line total = 100.00 USD.
- Subtotal = 100.00 USD.
- Total = 105.00 USD.

Test nên xác nhận total được tính từ state hiện tại. Sau khi đổi quantity trong Draft, total thay đổi đúng. Sau khi Confirmed, thay đổi quantity bị từ chối.

### Kiểm tra currency mismatch

Thử thêm ProductSnapshot bằng EUR vào Order dùng USD. Hành vi phải bị từ chối và danh sách line cùng total phải giữ nguyên.

## 27. Kiểm thử property và state transition

Property-based test có thể kiểm tra những tính chất tổng quát:

- Với mọi Quantity dương, line total không âm nếu Price không âm.
- Với mọi danh sách line hợp lệ cùng currency, subtotal bằng tổng line total.
- Total bằng subtotal cộng delivery fee.
- Sau khi Confirm, mọi Draft mutation đều bị từ chối.
- Quantity của mọi line luôn dương.

State transition test kiểm tra chuỗi hành vi:

    Create Draft
       |
       +--> Add Line
       |
       +--> Set Address
       |
       +--> Confirm
                 |
                 +--> Add Line rejected
                 +--> Change Quantity rejected
                 +--> Set Address rejected

Có thể sinh chuỗi command để tìm đường đi làm Aggregate rơi vào state không hợp lệ. Property phải xuất phát từ invariant nghiệp vụ, không chỉ lặp lại logic implementation.

## 28. Kiểm thử Repository và concurrency

Repository contract test nên xác nhận:

- Save rồi load trả lại Order tương đương.
- Order không tồn tại trả Optional.empty.
- OrderLine được lưu cùng Aggregate Root.
- Optimistic version conflict không ghi đè dữ liệu mới.
- Rollback không lưu một phần Aggregate.
- Event/outbox được ghi cùng transaction nếu dùng transactional outbox.

Ví dụ hai request cùng đọc version 7. Request A cập nhật quantity và commit version 8. Request B vẫn cố save dựa trên version 7. Persistence adapter phải phát hiện conflict thay vì ghi đè version 8.

Aggregate behavior bảo vệ invariant trong một lần xử lý; optimistic locking bảo vệ trước thay đổi cạnh tranh giữa các transaction.

## 29. API DTO không phải Domain Model

HTTP request nên được map sang command:

~~~java
public record AddOrderLineRequest(
        String productId,
        int quantity
) {
}
~~~

Application adapter xác thực cấu trúc, parse ProductId, tạo Quantity và gửi command. Domain model không cần biết JSON, HTTP status code hoặc annotation của framework.

Response có thể là:

~~~java
public record OrderResponse(
        String orderId,
        String status,
        List<OrderLineResponse> lines,
        String currency,
        String total
) {
}
~~~

Map từ Order view sang DTO ở Application/Presentation layer. Không trả entity mutable hoặc persistence entity trực tiếp.

## 30. Những sai lầm thiết kế thường gặp

### Aggregate chỉ là data container

Nếu Order có setter cho mọi field và không bảo vệ behavior, invariant sẽ nằm rải rác trong controller và service.

### Aggregate quá lớn

Đưa Customer, Inventory, Payment và Shipment vào Order làm tăng transaction boundary và coupling. Chỉ giữ những gì cần nhất quán cùng nhau.

### Dùng primitive cho mọi giá trị

String customerId, String productId, BigDecimal total và int quantity dễ bị truyền nhầm hoặc bỏ qua semantics. Value Object làm contract rõ hơn.

### Lưu total và cập nhật thủ công ở nhiều nơi

Nếu total được tính từ line và fee, lưu thêm field mutable có thể tạo state không nhất quán. Chỉ materialize khi có lý do và policy rõ.

### Expose collection mutable

Trả trực tiếp list nội bộ cho phép caller thêm/xóa line mà bỏ qua Order Root.

### Aggregate tự gọi service khác

Network call trong Order behavior làm domain phụ thuộc hạ tầng và kéo latency/failure vào Aggregate.

### Phát event trước khi commit

Consumer có thể xử lý event của một thay đổi sau đó bị rollback.

### Dùng một status cho nhiều khái niệm

Confirmed, Paid, Fulfilled và Delivered là các facts khác nhau. Không gộp chúng thành Completed nếu nghiệp vụ cần phân biệt.

### Dùng test chỉ kiểm tra implementation

Test private field hoặc gọi setter nội bộ không chứng minh public behavior giữ invariant. Kiểm thử qua command và kết quả quan sát được.

## 31. Quy trình thiết kế Aggregate từ nghiệp vụ

Khi gặp một bài toán domain tương tự, có thể đi theo trình tự:

1. **Discovery:** hỏi chuyên gia về lifecycle, quy tắc và ngoại lệ của đơn hàng.
2. **Ubiquitous Language:** thống nhất Order, Line, Draft, Confirmed, Price Snapshot.
3. **Bounded Context:** xác định context nào sở hữu Order và context nào sở hữu dữ liệu tham chiếu.
4. **Use Cases:** liệt kê command/query cần hỗ trợ.
5. **Aggregate Boundary:** chọn root và entity con dựa trên invariant cần bảo vệ.
6. **Invariant:** viết điều kiện phải đúng trước và sau mỗi behavior.
7. **Value Objects:** mô hình hóa ID, Money, Price, Quantity và Address Snapshot.
8. **Behavior:** triển khai add, change, remove và confirm.
9. **State Transition:** xác định trạng thái nguồn, đích và hành vi bị cấm.
10. **Domain Events:** ghi nhận facts sau hành vi thành công.
11. **Repository:** lưu và tải Aggregate Root.
12. **Application Layer:** điều phối catalog, transaction và use case.
13. **Testing:** kiểm tra VO, Aggregate, repository, concurrency và workflow.
14. **Evolution:** xem xét thay đổi policy và compatibility của event/API.

Đừng bắt đầu bằng việc tạo entity cho từng bảng. Bắt đầu bằng hành vi và invariant mà doanh nghiệp cần bảo vệ.

## 32. Checklist thiết kế Order Aggregate

Trước khi hoàn thiện mô hình, hãy kiểm tra:

- Bounded Context sở hữu Order đã được xác định chưa?
- Customer và Product được tham chiếu hay snapshot theo đúng mục đích chưa?
- OrderLine là Entity hay Value Object đã có lý do nghiệp vụ chưa?
- Order Root có kiểm soát mọi thay đổi của child không?
- OrderId, CustomerId, ProductId và OrderLineId có kiểu riêng không?
- Quantity có ngăn giá trị không hợp lệ không?
- Money có Currency và phép toán kiểm tra cùng currency không?
- Price có ngăn giá âm không?
- Precision và rounding policy đã được xác định chưa?
- Address Snapshot có bất biến và giữ lịch sử không?
- Các dòng có cùng currency với Order không?
- Line ID có duy nhất trong Aggregate không?
- Total có được tính từ nguồn dữ liệu nhất quán không?
- Confirm có kiểm tra line và address không?
- Order đã Confirmed có bị khóa chỉnh sửa không?
- Failure có giữ nguyên state không?
- Domain Event có được ghi nhận sau hành vi thành công không?
- Event có được publish sau commit không?
- Repository chỉ quản lý Aggregate Root không?
- Optimistic locking có xử lý concurrent update không?
- Inventory và Payment có giữ ownership riêng không?
- API DTO có tách khỏi Domain Model không?
- Test có bao phủ validation, equality, invariant, transition và concurrency không?

## 33. Kết luận

Thiết kế Order Aggregate bắt đầu từ trách nhiệm và invariant của Order Management, không bắt đầu từ bảng hoặc framework. Order Root kiểm soát các dòng hàng, currency, địa chỉ snapshot, phí giao hàng và lifecycle. Value Object như OrderId, CustomerId, ProductId, Quantity, Money, Price và AddressSnapshot làm rõ ý nghĩa của dữ liệu và bảo vệ tính hợp lệ ngay khi tạo.

Aggregate giữ những quy tắc cần nhất quán trong cùng một transaction: không xác nhận đơn rỗng, phải có địa chỉ giao hàng, các khoản tiền cùng currency và đơn đã xác nhận không thể bị chỉnh sửa như Draft. Tổng tiền được tính từ các thành phần có thẩm quyền. OrderLine được thay đổi thông qua Order Root; Repository lưu Aggregate Root; Application Layer điều phối dữ liệu từ context khác; Domain Event thông báo fact sau commit.

Inventory, Payment, Customer và Product Catalog vẫn giữ ownership riêng. Khi một use case cần phối hợp nhiều context, hãy dùng command, integration event hoặc Process Manager theo đúng semantics. Cách thiết kế này tạo ra một mô hình miền dễ hiểu, có thể kiểm thử và có ranh giới đủ rõ để tiến hóa cùng nghiệp vụ.
