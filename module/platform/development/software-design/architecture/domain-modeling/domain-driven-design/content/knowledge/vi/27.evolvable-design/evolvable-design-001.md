# Giao diện thể hiện rõ ý định sử dụng theo ngôn ngữ nghiệp vụ

Trong Domain-Driven Design (DDD), thiết kế dễ thay đổi bắt đầu từ khả năng diễn đạt đúng nghiệp vụ. Một class có thể gọn và chạy nhanh, nhưng nếu người đọc phải lần theo nhiều hàm phụ mới hiểu một thao tác có ý nghĩa gì, giao diện của nó chưa truyền đạt tốt ý định sử dụng.

Giao diện ở đây là phần API mà một thành phần công khai cho thành phần khác: phương thức public của Entity và Aggregate, interface của Repository, Domain Service, Application Service, Command và kiểu dữ liệu đi kèm. Tên và cách tổ chức các thành phần này nên dùng ngôn ngữ mà chuyên gia nghiệp vụ và đội phát triển cùng hiểu.

Ví dụ, Order có thể cung cấp phương thức `setStatus(PLACED)`. Phương thức này cho biết field nào bị thay đổi, nhưng không nói rõ hành động nghiệp vụ, điều kiện hợp lệ hoặc hệ quả của việc đặt đơn. Phương thức `place()` diễn đạt ý định rõ hơn: người gọi yêu cầu đặt đơn; Aggregate tự kiểm tra đơn có được đặt hay không và thực hiện chuyển trạng thái hợp lệ.

Một giao diện thể hiện ý định tốt giúp người đọc hiểu cách dùng mà không cần biết chi tiết nội bộ. Nó cũng tạo điểm tập trung để thay đổi quy tắc nghiệp vụ, giảm việc sửa nhiều nơi khi mô hình phát triển và giúp kiểm thử tập trung vào hành vi có ý nghĩa.

## 1. Giao diện trong mô hình domain là gì?

Một giao diện không chỉ là từ khóa `interface` của Java. Trong thiết kế hướng đối tượng, nó là tập hợp thao tác và dữ liệu mà một đối tượng hoặc module cho phép bên ngoài sử dụng.

Ví dụ:

```java
public class Order {
    public void place() { ... }
    public void cancel(CancellationReason reason) { ... }
    public void changeShippingAddress(ShippingAddress address) { ... }
}
```

Ba phương thức public trên tạo thành một phần giao diện của Order. Người gọi biết có thể đặt, hủy và đổi địa chỉ giao hàng. Họ không cần truy cập trực tiếp các field trạng thái hoặc biết Aggregate lưu dữ liệu bằng cách nào.

Trong DDD, giao diện này nên phản ánh mô hình nghiệp vụ và Ubiquitous Language. Nếu chuyên gia nghiệp vụ nói đặt đơn, giữ hàng, xác nhận thanh toán, tên API nên phản ánh đúng các khái niệm đó khi chúng thuộc trách nhiệm của đối tượng tương ứng.

### 1.1. Giao diện tốt nói rõ người gọi đang yêu cầu điều gì

| Giao diện thiên về kỹ thuật | Giao diện thể hiện ý định |
|---|---|
| `setStatus(PLACED)` | `place()` |
| `setStatus(CANCELLED)` | `cancel(reason)` |
| `updateAddress(address)` | `changeShippingAddress(address)` |
| `setQuantity(lineId, quantity)` | `changeLineQuantity(lineId, quantity)` |
| `process()` | `authorizePayment()` hoặc `capturePayment()` |
| `validate()` | `confirmEligibility()` nếu đó là thuật ngữ nghiệp vụ thực |

Tên ở cột phải không tự động tốt trong mọi ngữ cảnh. Chọn tên mà doanh nghiệp thực sự sử dụng và phản ánh đúng kết quả của thao tác. Ví dụ, authorize payment và capture payment là hai hành động thanh toán khác nhau; không nên dùng lẫn chỉ vì chúng đều là xử lý thanh toán.

### 1.2. Giao diện không phải nơi phô bày cấu trúc dữ liệu

Một Aggregate có thể chứa nhiều field, collection và object con. Điều đó không có nghĩa người gọi cần được quyền đọc hoặc sửa tất cả chúng.

```java
public class Order {
    private OrderStatus status;
    private List<OrderLine> lines;
    private ShippingAddress shippingAddress;
    private Money total;
}
```

Nếu class cung cấp hàng loạt setter công khai, mọi caller có thể tự tổ hợp trạng thái. Aggregate khó bảo vệ invariant vì quy tắc bị phân tán ở các nơi gọi.

Giao diện có chủ đích chỉ công khai những hành vi cần thiết. Dữ liệu nội bộ được giữ kín hoặc chỉ cung cấp qua các giá trị đọc phù hợp.

## 2. Bắt đầu từ ngôn ngữ nghiệp vụ

Tên phương thức không nên được chọn chỉ vì nó thuận tay khi viết code. Nó cần xuất phát từ cách nghiệp vụ mô tả công việc, quyết định và kết quả.

### 2.1. Tìm động từ và danh từ trong trao đổi nghiệp vụ

Khi phân tích một use case, hãy lắng nghe những câu như:

- Nhân viên đặt đơn sau khi kiểm tra thông tin.
- Khách hàng yêu cầu hủy đơn.
- Kho giữ số lượng hàng cho đơn.
- Bộ phận tài chính xác nhận khoản thanh toán.
- Nhân viên giao nhận bàn giao kiện hàng cho đơn vị vận chuyển.

Các động từ đặt, yêu cầu hủy, giữ, xác nhận và bàn giao thường gợi ý hành vi hoặc sự kiện. Các danh từ đơn, số lượng giữ, khoản thanh toán và kiện hàng gợi ý khái niệm domain.

Tuy nhiên, không phải động từ nào cũng trở thành phương thức của một Entity. Hãy xác định đối tượng có trách nhiệm và ranh giới Aggregate trước khi đặt API.

### 2.2. Dùng cùng một thuật ngữ cho cùng một ý nghĩa

Nếu nghiệp vụ gọi một hành động là đặt đơn, code không nên lúc gọi `submit()`, lúc gọi `confirm()`, lúc gọi `activate()` nếu cả ba đều chỉ cùng một việc. Các tên khác nhau khiến người đọc tưởng có ba trạng thái hoặc quy trình khác nhau.

Ngược lại, nếu gửi yêu cầu đặt hàng và xác nhận đơn là hai bước khác nhau, đừng gộp chúng vào một phương thức chung chỉ để giảm số API. Ngôn ngữ cần phản ánh khác biệt có ý nghĩa.

### 2.3. Tránh biệt ngữ kỹ thuật làm tên nghiệp vụ

Tên như `persistOrder()`, `executeOperation()`, `handleFlag()` mô tả cách triển khai hoặc quá chung chung. Chúng không giúp người đọc hiểu mục tiêu nghiệp vụ.

Repository có thể có `save(order)` vì trách nhiệm của nó là lưu trữ. Nhưng Aggregate nên có `place()` vì trách nhiệm của nó là thực hiện hành vi đặt đơn. Mỗi lớp cần tên phù hợp với vai trò của nó.

### 2.4. Xác nhận thuật ngữ với chuyên gia nghiệp vụ

Một tên có vẻ tự nhiên với lập trình viên chưa chắc có cùng ý nghĩa với doanh nghiệp. Hãy hỏi chuyên gia:

- Hành động này có đúng là đặt đơn không?
- Sau hành động, đơn ở trạng thái nào?
- Có khác xác nhận đơn không?
- Ai có quyền thực hiện?
- Điều kiện nào khiến thao tác bị từ chối?
- Có phát sinh thông báo hoặc nghĩa vụ tiếp theo không?

Câu trả lời giúp giao diện phản ánh đúng mô hình, thay vì chỉ thay tên phương thức cho đẹp.

## 3. Thay setter tổng quát bằng hành vi có ý nghĩa

Setter thường làm lộ cấu trúc nội bộ và cho phép thay đổi trạng thái mà không đi qua quy tắc domain. Không phải mọi setter đều sai: Value Object đơn giản hoặc DTO có thể cần thao tác gán dữ liệu. Nhưng với Aggregate Root, thay đổi trạng thái nghiệp vụ nên đi qua hành vi có ý nghĩa.

### 3.1. Ví dụ API khó hiểu

```java
public class Order {
    private OrderStatus status;
    private String cancellationReason;

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public void setCancellationReason(String reason) {
        this.cancellationReason = reason;
    }
}
```

Caller phải tự biết cần gọi hai setter theo thứ tự nào. Nó cũng có thể đặt trạng thái thành CANCELLED mà không cung cấp lý do, hoặc đặt lại trạng thái thành DRAFT sau khi đơn đã giao.

Quy tắc đang nằm trong đầu người gọi thay vì được bảo vệ tại Aggregate.

### 3.2. Đưa quy tắc vào hành vi domain

```java
public class Order {
    private OrderStatus status;
    private CancellationReason cancellationReason;

    public void cancel(CancellationReason reason) {
        if (status == OrderStatus.SHIPPED ||
            status == OrderStatus.DELIVERED) {
            throw new OrderCannotBeCancelledException(id);
        }

        if (status == OrderStatus.CANCELLED) {
            throw new OrderAlreadyCancelledException(id);
        }

        this.cancellationReason = Objects.requireNonNull(reason);
        this.status = OrderStatus.CANCELLED;
    }
}
```

Giờ đây, thao tác hủy đơn là một hành vi nguyên vẹn. Aggregate kiểm tra trạng thái hiện tại, yêu cầu lý do và thay đổi các field liên quan như một quyết định nghiệp vụ.

Tên phương thức cũng giúp caller hiểu mục tiêu mà không phải biết có hai field được cập nhật.

### 3.3. Không tạo phương thức chỉ để bọc setter

Một phương thức có tên nghiệp vụ nhưng chỉ gán field mà không bảo vệ quy tắc có thể tạo cảm giác an toàn giả:

```java
public void cancel() {
    this.status = OrderStatus.CANCELLED;
}
```

Nếu hủy đơn cần kiểm tra trạng thái, lý do, hoàn tiền hoặc quyền hạn, phương thức này chưa thể hiện đầy đủ hành vi. Giao diện tốt phải dẫn đến hành vi đúng, không chỉ có tên đẹp.

### 3.4. Giữ API nhỏ nhưng đủ diễn đạt

Không cần tạo phương thức cho từng field. Hãy cung cấp các thao tác nghiệp vụ mà caller thực sự cần.

Ví dụ, thay vì công khai `setRecipientName`, `setStreet`, `setCity` và `setPostalCode`, Aggregate có thể cung cấp `changeShippingAddress(address)` nếu nghiệp vụ xem địa chỉ giao hàng là một đơn vị thay đổi.

## 4. Chọn tên phương thức rõ ràng và nhất quán

Một tên tốt giúp trả lời nhanh: ai đang làm gì, với đối tượng nào và mục đích nào?

### 4.1. Ưu tiên động từ cụ thể

Những động từ chung như `process`, `handle`, `manage`, `update` và `do` thường che khuất ý nghĩa. Chỉ dùng khi ngữ cảnh thực sự đã làm rõ đối tượng và mục tiêu.

Ví dụ:
- `payment.process()` không cho biết đang xác thực, ủy quyền hay thu tiền.
- `payment.authorize()` nêu rõ bước ủy quyền thanh toán.
- `payment.capture()` nêu rõ bước thu tiền đã được ủy quyền.
- `shipment.dispatch()` diễn đạt việc xuất hoặc bàn giao hàng để vận chuyển nếu đó là thuật ngữ của doanh nghiệp.

### 4.2. Dùng cặp tên nhất quán cho các chuyển đổi có quan hệ

```java
order.place();
order.confirm();
order.cancel(reason);
order.refund(refundAmount);
```

Chỉ giữ những hành vi thực sự tồn tại trong quy trình. Không thêm phương thức chỉ để tạo một bộ tên đối xứng.

### 4.3. Tránh boolean làm mơ hồ ý định

Một phương thức nhận boolean thường khiến lời gọi khó đọc:

```java
order.changeAddress(address, true);
```

Người đọc không biết true nghĩa là địa chỉ ưu tiên, địa chỉ thanh toán hay bỏ qua xác thực.

Có thể thay bằng phương thức riêng:

```java
order.changeShippingAddress(address);
order.changeBillingAddress(address);
```

Nếu boolean thực sự là một lựa chọn của nghiệp vụ, dùng enum hoặc Value Object có tên rõ:

```java
order.changeDeliveryPreference(
    DeliveryPreference.LEAVE_AT_RECEPTION
);
```

Không phải mọi boolean đều cần được thay thế. Câu hỏi là caller có thể hiểu lời gọi mà không phải tra định nghĩa tham số hay không.

### 4.4. Tránh overload gây hiểu nhầm

Hai phương thức cùng tên nhưng khác tham số có thể hợp lý, nhưng đừng khiến chúng có semantics khác nhau đáng kể:

```java
order.cancel();
order.cancel(true);
order.cancel("duplicate");
```

Nếu các dạng hủy có quy tắc khác nhau, hãy dùng tên hoặc kiểu tham số biểu đạt rõ ý nghĩa:

```java
order.cancelByCustomer(reason);
order.cancelByOperations(reason, operatorId);
```

Chỉ tách như vậy nếu hai hành động thực sự khác nhau về nghiệp vụ. Nếu chỉ khác dữ liệu bổ sung, một phương thức với kiểu tham số có tên có thể đủ.

## 5. Dùng kiểu dữ liệu diễn đạt ý nghĩa tham số

Giao diện có thể có tên phương thức tốt nhưng vẫn khó hiểu nếu mọi tham số đều là String, int hoặc boolean. Primitive obsession khiến caller truyền nhầm giá trị và làm mất ngữ nghĩa của domain.

### 5.1. Vấn đề nhiều tham số cùng kiểu

```java
order.changeAddress(
    "Nguyen Van A",
    "12 Nguyen Hue",
    "District 1",
    "Ho Chi Minh City",
    "700000"
);
```

Nếu thứ tự tham số bị đảo, compiler vẫn có thể chấp nhận vì tất cả đều là String. Caller cũng khó biết field nào bắt buộc hoặc có quy tắc chuẩn hóa nào.

### 5.2. Gom dữ liệu thành Value Object

```java
public record ShippingAddress(
    RecipientName recipient,
    StreetAddress street,
    District district,
    City city,
    PostalCode postalCode
) {
    public ShippingAddress {
        Objects.requireNonNull(recipient);
        Objects.requireNonNull(street);
        Objects.requireNonNull(city);
        Objects.requireNonNull(postalCode);
    }
}
```

Lời gọi trở nên rõ:

```java
order.changeShippingAddress(newAddress);
```

ShippingAddress có thể kiểm tra định dạng, chuẩn hóa và bảo vệ các quy tắc liên quan đến địa chỉ. Aggregate nhận một khái niệm nghiệp vụ hoàn chỉnh.

### 5.3. Dùng Value Object cho các giá trị có quy tắc

| Kiểu nguyên thủy | Kiểu domain có ý nghĩa |
|---|---|
| String | OrderId, CustomerId, ProductCode |
| BigDecimal | Money, Percentage |
| int | Quantity, RetryLimit |
| String | EmailAddress, PostalCode |
| Instant | DeliveryWindow hoặc BookingTime khi có semantics phù hợp |

Không cần tạo Value Object cho mọi biến. Chỉ tạo khi kiểu đó có ngữ nghĩa, quy tắc xác thực, phép so sánh hoặc hành vi riêng có ích cho mô hình.

### 5.4. Dùng kiểu tham số để làm lời gọi dễ đọc

Java không có named argument cho lời gọi phương thức. Record hoặc class tham số có thể làm rõ một nhóm tùy chọn:

```java
public record RefundRequest(
    Money amount,
    RefundReason reason,
    RefundMethod method
) {}

payment.refund(new RefundRequest(
    amount,
    RefundReason.DUPLICATE_CHARGE,
    RefundMethod.ORIGINAL_PAYMENT_METHOD
));
```

Với một hoặc hai tham số đơn giản, không cần tạo wrapper class chỉ để tăng số lượng kiểu. Cân bằng giữa khả năng diễn đạt và độ phức tạp.

## 6. Đặt hành vi đúng đối tượng và đúng Aggregate

Tên rõ ràng không thể bù cho việc đặt hành vi sai nơi. Một giao diện dễ thay đổi cần phản ánh trách nhiệm của đối tượng và ranh giới Aggregate.

### 6.1. Hành vi thuộc Aggregate Root

Nếu quy tắc cần bảo vệ trạng thái nhất quán của Order, thao tác nên đi qua Order Root:

```java
order.addLine(productId, quantity, agreedPrice);
order.changeLineQuantity(lineId, newQuantity);
order.removeLine(lineId);
```

Nếu OrderLine nằm bên trong Aggregate Order, caller không nên tải OrderLine riêng rồi sửa nó qua một repository riêng. Order Root kiểm soát việc thêm, đổi hoặc xóa dòng hàng để giữ invariant như số lượng hợp lệ, tổng tiền và trạng thái đơn.

### 6.2. Hành vi thuộc Entity con

Entity con có thể có hành vi riêng nếu hành vi đó không phá vỡ invariant của Aggregate và chỉ được gọi qua quyền truy cập phù hợp.

```java
public void changeLineQuantity(
        OrderLineId lineId,
        Quantity quantity) {
    ensureEditable();
    OrderLine line = findLine(lineId);
    line.changeQuantity(quantity);
    recalculateTotal();
}
```

Caller chỉ cần biết hành động thay đổi số lượng của dòng hàng trong Order. Nó không cần tự tìm line, sửa line rồi gọi một phương thức tính lại tổng.

### 6.3. Dùng Domain Service khi hành vi không thuộc tự nhiên về một Entity

Một số quy tắc cần nhiều đối tượng nhưng không thuộc rõ về một Entity cụ thể. Ví dụ, tính giá cuối cùng có thể phụ thuộc sản phẩm, số lượng, hạng khách hàng và chính sách khuyến mãi.

```java
public interface PricingPolicy {
    PriceQuote quote(
        Product product,
        Quantity quantity,
        CustomerTier customerTier
    );
}
```

Tên quote và PriceQuote diễn đạt mục tiêu nghiệp vụ. Domain Service không nên trở thành lớp tiện ích chứa mọi phương thức không biết đặt ở đâu. Hãy đặt nó ở nơi có một quy tắc domain thực sự và một trách nhiệm rõ ràng.

### 6.4. Application Service điều phối, không thay Aggregate quyết định

```java
public final class PlaceOrderUseCase {
    private final OrderRepository orders;

    public void handle(PlaceOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.place();
        orders.save(order);
    }
}
```

Tên use case thể hiện mục tiêu của ứng dụng. Nó điều phối việc nạp và lưu; Aggregate quyết định hành vi đặt đơn có hợp lệ không. Giao diện của mỗi lớp nói rõ trách nhiệm riêng.

## 7. Thiết kế Repository bằng ngôn ngữ nghiệp vụ

Repository là một giao diện khác cần thể hiện đúng mục đích. Tên phương thức nên nói rõ Aggregate được tìm hoặc lưu theo tiêu chí nào.

### 7.1. Tránh API repository quá tổng quát

```java
public interface OrderRepository {
    Object get(String key);
    void save(Object value);
    List<Object> search(Map<String, Object> filters);
}
```

API này không thể hiện kiểu Aggregate, tiêu chí tìm kiếm hay kết quả. Caller phải biết quy ước ẩn bên trong và dễ truyền sai dữ liệu.

### 7.2. Dùng kiểu và tên có ngữ nghĩa

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId orderId);
    Optional<Order> findByOrderNumber(OrderNumber orderNumber);
    void save(Order order);
}
```

Hợp đồng cho biết repository quản lý Order và hỗ trợ hai cách tìm có ý nghĩa. Việc lưu trữ cụ thể có thể đổi mà Application không cần biết.

### 7.3. Đừng đưa hành vi domain vào Repository

```java
// Không phù hợp với repository contract
orders.placeOrder(orderId);
orders.cancelOrder(orderId);
orders.applyDiscount(orderId, discount);
```

Repository nên cung cấp Aggregate, không thay Aggregate thực hiện nghiệp vụ. Thay vào đó, tải Aggregate rồi gọi hành vi tương ứng:

```java
Order order = orders.findById(orderId)
    .orElseThrow(OrderNotFoundException::new);

order.applyDiscount(discount);
orders.save(order);
```

Cách này giúp invariant nằm trong Aggregate và tên hành vi được dùng thống nhất ở mọi caller.

### 7.4. Truy vấn đọc có thể có giao diện riêng

Nếu cần tìm kiếm, thống kê hoặc màn hình danh sách, Query Service có thể dùng tên truy vấn theo ngôn ngữ nghiệp vụ:

```java
public interface OrderQueries {
    Page<OrderSummary> findOrdersForCustomer(
        CustomerId customerId,
        OrderSearchCriteria criteria,
        Pageable page
    );
}
```

Không cần ép mọi truy vấn vào Repository của Aggregate. Read model có thể có cấu trúc khác write model và được truy vấn qua một abstraction riêng.

## 8. Giao diện Command và Query cũng cần thể hiện ý định

CQRS phân biệt yêu cầu thay đổi trạng thái với yêu cầu đọc dữ liệu. Tên và kiểu của chúng nên thể hiện rõ hai mục tiêu này.

### 8.1. Command biểu đạt ý định thay đổi

```java
public record CancelOrderCommand(
    OrderId orderId,
    CancellationReason reason
) {}
```

Tên Command là một yêu cầu cụ thể. Nó không nên là một túi field chung kiểu UpdateOrderCommand có thể thay đổi bất kỳ thuộc tính nào.

### 8.2. Query biểu đạt thông tin cần tìm

```java
public record FindCustomerOrdersQuery(
    CustomerId customerId,
    OrderStatus status,
    DateRange createdDuring
) {}
```

Tên Query nói rõ dữ liệu cần lấy và tiêu chí. Query không nên thay đổi trạng thái nghiệp vụ. Nếu một thao tác vừa đọc vừa thay đổi, hãy tách mục tiêu hoặc giải thích rõ semantics.

### 8.3. Tránh một phương thức làm quá nhiều việc

```java
orderService.process(orderId, "CANCEL", true);
```

Caller không biết chuỗi CANCEL và boolean có ý nghĩa gì. Phương thức cũng có thể mở rộng thành một bộ xử lý mọi hành động, làm API khó hiểu.

Thay bằng một use case có mục tiêu rõ:

```java
cancelOrder.handle(
    new CancelOrderCommand(orderId, reason)
);
```

Nếu các hành động có chung một quy trình kỹ thuật, có thể tái sử dụng nội bộ. Giao diện công khai vẫn nên phản ánh mục tiêu mà caller cần thực hiện.

## 9. Biểu diễn kết quả và lỗi bằng ngôn ngữ domain

Giao diện không chỉ gồm tên thao tác; kiểu trả về và lỗi cũng cần giúp caller hiểu điều gì đã xảy ra.

### 9.1. Tránh trả boolean cho kết quả có nhiều ý nghĩa

```java
boolean result = order.place();
```

Nếu false có thể nghĩa là đã đặt rồi, thiếu hàng, đơn bị khóa hoặc không đủ điều kiện, caller phải đoán nguyên nhân.

Có thể dùng exception domain cụ thể cho trường hợp vi phạm hoặc một kiểu kết quả có phân loại rõ:

```java
public sealed interface PlaceOrderResult {
    record Placed(OrderId orderId) implements PlaceOrderResult {}
    record AlreadyPlaced(OrderId orderId) implements PlaceOrderResult {}
    record Rejected(PlacementRejectionReason reason)
        implements PlaceOrderResult {}
}
```

Chọn exception hay result type tùy semantics. Exception phù hợp với tình huống bất thường hoặc luồng từ chối theo quy ước của dự án; result type phù hợp khi nhiều kết quả là nhánh nghiệp vụ bình thường mà caller cần xử lý.

### 9.2. Tên exception nên nói rõ điều kiện nghiệp vụ

Các lỗi như IllegalStateException hoặc RuntimeException chung chung không giúp người gọi biết quy tắc nào bị vi phạm.

Ví dụ:
- OrderCannotBeCancelledException.
- InsufficientAvailableQuantityException.
- PaymentAlreadyCapturedException.
- ShippingAddressNotServiceableException.

Không cần tạo một exception class cho mọi câu thông báo. Tạo kiểu riêng khi caller hoặc lớp xử lý cần phân biệt loại lỗi đó.

### 9.3. Không để lỗi kỹ thuật trở thành ngôn ngữ domain

SQLException, OptimisticLockingFailureException hoặc lỗi timeout là lỗi ở hạ tầng. Adapter hoặc Application boundary có thể chuyển chúng thành lỗi phù hợp với use case, nhưng không nên đổi tên tùy tiện thành một lỗi nghiệp vụ không đúng bản chất.

Ví dụ, database timeout không đồng nghĩa Order không hợp lệ. Giữ phân biệt giúp hệ thống phản hồi và retry đúng cách.

## 10. Giao diện rõ ý định giúp mô hình tiến hóa ra sao?

Khi quy tắc nghiệp vụ thay đổi, giao diện thể hiện ý định giúp xác định nơi cần sửa và những caller nào bị ảnh hưởng.

### 10.1. Thay đổi quy tắc bên trong một hành vi

Giả sử trước đây Order có thể được hủy đến khi giao cho đơn vị vận chuyển. Sau này doanh nghiệp quyết định chỉ cho phép hủy trước khi đóng gói.

Nếu mọi nơi tự gán status, nhóm phát triển phải tìm tất cả caller và sửa logic. Nếu caller đều gọi `order.cancel(reason)`, quy tắc có thể được cập nhật tại một điểm trong Aggregate.

### 10.2. Thêm một bước nghiệp vụ mà không làm lộ chi tiết

Có thể sau khi đặt đơn, hệ thống cần kiểm tra hạn mức hoặc ghi nhận sự kiện. Caller vẫn gọi `place()`. Aggregate hoặc Application Service phối hợp phần thay đổi theo đúng trách nhiệm; API công khai không cần thêm những thao tác kỹ thuật mà caller không nên tự điều khiển.

Tuy nhiên, không nên giấu một quy trình dài và bất đồng bộ bên trong một phương thức đồng bộ nếu điều đó làm sai kỳ vọng của caller. Khi kết quả chỉ là yêu cầu đã được tiếp nhận, tên và kiểu trả về cần diễn đạt rõ trạng thái đó.

### 10.3. Tách giao diện công khai khỏi implementation

Java interface cho phép thay implementation mà giữ hợp đồng:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Một implementation dùng JPA có thể được thay bằng JDBC hoặc adapter khác. Application phụ thuộc vào ngôn ngữ và kiểu domain của hợp đồng, không phụ thuộc chi tiết lưu trữ.

Abstraction chỉ hữu ích khi nó diễn đạt một nhu cầu thật. Không cần tạo interface cho mọi class nếu không có ranh giới thay thế, kiểm thử hoặc module cần bảo vệ.

### 10.4. Đổi tên cũng là thay đổi hợp đồng

Tên phương thức public có thể được dùng bởi nhiều module. Đổi tên một API nội bộ có thể làm hỏng caller khi compile; đổi tên một endpoint hoặc message contract có thể ảnh hưởng client độc lập.

Trước khi thay đổi, hãy xác định:
- Ai đang sử dụng giao diện?
- Nó là API nội bộ hay hợp đồng công khai?
- Có thể giữ phương thức cũ và đánh dấu deprecated trong một giai đoạn không?
- Có cần adapter chuyển tên hoặc semantics cũ sang mới không?
- Test nào xác nhận hành vi trước và sau thay đổi?

Không nên giữ alias cũ mãi mãi nếu nó làm mô hình khó hiểu, nhưng việc loại bỏ cần theo lộ trình phù hợp với phạm vi người dùng.

## 11. Từ giao diện domain đến API bên ngoài

Giao diện của Aggregate và API HTTP có liên quan nhưng không nhất thiết giống nhau.

### 11.1. Domain API nói ngôn ngữ nội bộ của Bounded Context

```java
order.changeShippingAddress(address);
order.place();
order.cancel(reason);
```

Đây là API dành cho code nội bộ trong context Ordering. Nó dùng Value Object và khái niệm domain.

### 11.2. HTTP API nói ngôn ngữ của hợp đồng client

Client có thể gọi:

```http
POST /api/orders/ORD-2048/place
```

hoặc gửi request chứa dữ liệu cần thiết. Controller chuyển đổi dữ liệu giao thức thành Command và gọi use case. Không nên serialize Aggregate trực tiếp chỉ để tái sử dụng class.

### 11.3. Integration API cần contract ổn định

Khi context Ordering thông báo cho Shipping, nó có thể phát Integration Event:

```java
public record OrderReadyForFulfillment(
    UUID eventId,
    String orderNumber,
    List<FulfillmentLine> lines,
    ShippingAddressData destination,
    Instant occurredAt,
    int schemaVersion
) {}
```

Contract tích hợp dùng kiểu dữ liệu và semantics đã công bố. Shipping chuyển nó thành mô hình nội bộ của mình. Nó không cần tham chiếu class Order hoặc Value Object nội bộ của Ordering.

Ba giao diện có thể dùng từ ngữ liên quan nhưng phục vụ ba ranh giới khác nhau. Giữ ranh giới giúp domain thay đổi mà không buộc mọi client hoặc context khác thay đổi cùng lúc.

## 12. Kiểm thử giao diện thể hiện ý định

Một giao diện tốt cần được kiểm tra về hành vi và khả năng sử dụng, không chỉ kiểm tra phương thức có tồn tại.

### 12.1. Unit test tập trung vào hành vi nghiệp vụ

```java
@Test
void cannotCancelAnOrderAfterShipment() {
    Order order = TestOrders.shipped();

    assertThrows(
        OrderCannotBeCancelledException.class,
        () -> order.cancel(CancellationReason.customerRequest())
    );
}
```

Test thể hiện quy tắc theo ngôn ngữ nghiệp vụ: đơn đã gửi đi không thể hủy. Nó không cần biết Order lưu status trong enum hay một cấu trúc khác.

### 12.2. Kiểm tra caller không phải thao tác field

Application test nên gọi use case và quan sát kết quả qua hành vi hoặc read model. Nếu caller phải gọi một chuỗi setter theo thứ tự để hoàn thành một mục tiêu, đó là dấu hiệu giao diện Aggregate có thể chưa đủ diễn đạt.

### 12.3. Kiểm tra hợp đồng Repository và Service

Có thể dùng contract test để bảo đảm các implementation Repository có cùng semantics. Với service hoặc API công khai, kiểm thử compatibility giúp phát hiện việc đổi kiểu trả về, tên field hoặc ý nghĩa kết quả.

### 12.4. Đọc code như một câu nghiệp vụ

```java
Order order = orders.findById(command.orderId())
    .orElseThrow(OrderNotFoundException::new);

order.changeShippingAddress(command.address());
order.place();
orders.save(order);
```

Nếu người đọc hiểu được trình tự và mục tiêu, giao diện đang truyền đạt khá tốt. Nếu phải mở nhiều lớp mới biết process() hoặc update() thực sự làm gì, cần xem lại tên và trách nhiệm.

## 13. Những dấu hiệu giao diện đang che giấu ý định

Hãy xem xét thiết kế khi gặp các dấu hiệu sau:

- Nhiều phương thức setter công khai trên Aggregate Root.
- Tên phương thức chung chung như process, execute hoặc update mà không có ngữ cảnh.
- Một phương thức nhận nhiều boolean hoặc chuỗi mã lệnh.
- Caller phải gọi nhiều phương thức theo đúng thứ tự nhưng thứ tự đó không được bảo vệ.
- Caller tự kiểm tra trạng thái trước khi gọi hành vi, và nhiều caller lặp cùng một điều kiện.
- Repository có các phương thức như approveOrder hoặc cancelOrder.
- Mọi truy vấn và lệnh đều đi qua một service tổng quát.
- Kiểu trả về chỉ là boolean dù nghiệp vụ có nhiều kết quả.
- Tên code không trùng với thuật ngữ mà chuyên gia sử dụng.
- Thay đổi một quy tắc đòi hỏi sửa nhiều caller.

Một dấu hiệu riêng lẻ chưa đủ kết luận thiết kế sai. Hãy kiểm tra ngữ cảnh và xem giao diện có khiến người gọi dễ sử dụng sai hay không.

## 14. Quy trình thiết kế hoặc cải tiến giao diện

Có thể dùng các bước sau khi tạo một Aggregate, Domain Service hoặc Application Service mới.

1. **Mô tả mục tiêu bằng ngôn ngữ nghiệp vụ.** Viết một câu về hành động hoặc thông tin mà caller cần.
2. **Xác định chủ thể chịu trách nhiệm.** Chọn Aggregate Root, Entity, Value Object, Domain Service, Repository hay Application Service phù hợp.
3. **Tìm thuật ngữ chung.** Xác nhận động từ, danh từ, trạng thái và kết quả với chuyên gia nghiệp vụ.
4. **Thiết kế phương thức theo ý định.** Dùng tên cụ thể và tránh lộ thao tác gán field.
5. **Chọn kiểu tham số có ý nghĩa.** Dùng Value Object hoặc parameter object khi nó giúp tránh nhầm lẫn và gom quy tắc liên quan.
6. **Định nghĩa kết quả và lỗi.** Làm rõ thành công, từ chối nghiệp vụ, dữ liệu không tồn tại và lỗi hạ tầng.
7. **Giữ invariant ở đúng ranh giới.** Aggregate Root kiểm soát thay đổi thuộc Aggregate; Application Service điều phối use case.
8. **Kiểm tra caller.** Đọc các lời gọi từ góc nhìn người sử dụng API; xem có thể hiểu mục tiêu mà không mở implementation không.
9. **Đánh giá khả năng tiến hóa.** Xác định tác động nếu quy tắc, kiểu dữ liệu hoặc contract thay đổi.
10. **Viết test theo hành vi.** Kiểm tra quy tắc nghiệp vụ và contract quan trọng, không chỉ kiểm tra setter đã gán field.

## 15. Những sai lầm thường gặp

**Đặt tên theo thao tác kỹ thuật.** Các tên như setStatus, persist hoặc process không nói rõ mục tiêu nghiệp vụ. Dùng động từ cụ thể phù hợp với vai trò của thành phần.

**Đổi tên setter nhưng không đưa quy tắc vào Aggregate.** Một phương thức place() chỉ gán status vẫn có thể cho phép trạng thái sai. Hành vi cần kiểm tra invariant và quản lý thay đổi liên quan.

**Dồn mọi hành vi vào một Domain Service.** Service tổng quát khiến Aggregate trở thành túi dữ liệu. Đặt hành vi tại đối tượng có trách nhiệm; chỉ dùng Domain Service cho quy tắc không thuộc tự nhiên về một Entity.

**Tạo Value Object cho mọi primitive.** Quá nhiều wrapper không có ngữ nghĩa làm API nặng nề. Chỉ tạo kiểu riêng khi nó biểu đạt khái niệm hoặc quy tắc hữu ích.

**Dùng boolean hoặc chuỗi mã lệnh để chọn hành vi.** Caller phải nhớ ý nghĩa của giá trị đặc biệt. Dùng phương thức riêng hoặc enum có tên khi nghiệp vụ có các lựa chọn rõ ràng.

**Để caller tự điều phối thứ tự setter.** Quy tắc bị phân tán và dễ bị bỏ sót. Gom chuỗi thay đổi thành một hành vi nghiệp vụ nguyên vẹn.

**Dùng một tên cho các hành động khác nhau.** Ví dụ, authorize và capture payment không phải một việc. Giữ thuật ngữ phân biệt đúng quy trình.

**Làm giao diện quá trừu tượng.** Một interface tổng quát cho mọi thao tác có thể che giấu kiểu và ý nghĩa. Abstraction cần xuất phát từ nhu cầu thay thế hoặc ranh giới module thật.

**Đổi API công khai mà không xem xét caller.** Tên và kiểu là một phần của contract. Có kế hoạch tương thích hoặc migration trước khi loại bỏ API cũ.

**Đưa HTTP hoặc persistence detail vào domain interface.** Aggregate không nên nhận HttpServletRequest, JPA EntityManager hay DTO của một đối tác. Adapter chuyển đổi tại ranh giới.

## 16. Checklist đánh giá giao diện

**Ngôn ngữ và ý định**
- Tên phương thức có dùng thuật ngữ nghiệp vụ đã thống nhất không?
- Người đọc có hiểu mục tiêu của lời gọi mà không mở implementation không?
- Tên có phân biệt các hành động gần giống nhau không?
- Có từ chung chung hoặc mã chuỗi khó hiểu không?

**Trách nhiệm**
- Hành vi có nằm đúng Aggregate hoặc Domain Service không?
- Repository có chỉ tập trung vào nạp và lưu không?
- Application Service có điều phối thay vì tự sửa trạng thái domain không?
- Caller có đang phải tự bảo vệ invariant không?

**Tham số và kết quả**
- Tham số có kiểu và tên thể hiện ý nghĩa không?
- Có nhiều primitive cùng kiểu dễ truyền nhầm không?
- Boolean có làm lời gọi khó hiểu không?
- Kết quả có biểu diễn đủ các nhánh nghiệp vụ cần xử lý không?
- Lỗi có phân biệt domain rule với lỗi hạ tầng không?

**Khả năng tiến hóa**
- Quy tắc thay đổi có thể được cập nhật tập trung không?
- Có thể thay implementation mà giữ contract không?
- Đã xác định các caller bị ảnh hưởng khi đổi API chưa?
- Test có bảo vệ hành vi và contract quan trọng không?
- Có tránh tạo abstraction hoặc Value Object không mang lại ý nghĩa không?

## 17. Kết luận

Giao diện thể hiện rõ ý định sử dụng giúp mô hình domain trở nên dễ đọc, dễ dùng đúng và dễ thay đổi. Tên phương thức, kiểu tham số, kết quả và lỗi nên phản ánh ngôn ngữ nghiệp vụ đã thống nhất. Aggregate cung cấp hành vi như đặt, hủy hoặc thay đổi địa chỉ; Repository diễn đạt nhu cầu nạp và lưu; Domain Service thể hiện quy tắc không thuộc tự nhiên về một Entity; Application Service điều phối use case.

Một giao diện tốt không phơi bày các bước gán field để caller tự ghép thành hành vi. Nó cung cấp thao tác có ý nghĩa, bảo vệ invariant tại đúng ranh giới và giữ chi tiết triển khai bên trong. Khi quy tắc nghiệp vụ thay đổi, đội phát triển có thể tập trung sửa nơi chịu trách nhiệm thay vì tìm và sửa mọi caller đang thao tác trực tiếp lên trạng thái.

Hãy bắt đầu từ cách doanh nghiệp nói về công việc, xác định đối tượng chịu trách nhiệm, rồi thiết kế API sao cho lời gọi đọc được như một câu nghiệp vụ. Đó là nền tảng thực tế để xây dựng phần mềm có thể tiến hóa mà không làm mất đi ý nghĩa của mô hình.
