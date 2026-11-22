# Tránh tạo trạng thái không hợp lệ rồi sửa dần bằng setter

Trong Domain-Driven Design (DDD), đối tượng miền cần bảo vệ các quy tắc nghiệp vụ trong suốt vòng đời. Nếu một Order chỉ hợp lệ khi có người mua, ít nhất một dòng hàng, địa chỉ giao hàng và tổng tiền nhất quán, thì hệ thống không nên tạo một Order thiếu các thông tin bắt buộc rồi gọi nhiều setter để hoàn thiện dần.

Cách làm đó tạo ra một khoảng thời gian mà đối tượng tồn tại nhưng không thể được sử dụng an toàn. Một đoạn mã khác có thể đọc nó quá sớm, lưu nó vào database, phát sự kiện hoặc thực hiện quyết định dựa trên dữ liệu chưa hoàn chỉnh. Lỗi có thể xuất hiện xa nơi đối tượng được tạo, khiến việc tìm nguyên nhân khó hơn.

Nguyên tắc cần hướng tới là **đối tượng phải hợp lệ theo trạng thái nghiệp vụ mà nó tuyên bố đang có**. Hãy đưa các điều kiện bắt buộc vào constructor hoặc factory, dùng hành vi có tên để chuyển trạng thái, và biểu diễn rõ những giai đoạn chưa hoàn tất nếu nghiệp vụ thực sự cho phép chúng.

## 1. Vì sao không nên tạo đối tượng không hợp lệ?

### 1.1. Đối tượng có thể bị sử dụng trước khi hoàn thiện

Một cách triển khai dễ gặp:

~~~java
Order order = new Order();
order.setBuyerId(buyerId);
order.setLines(lines);
order.setDeliveryAddress(address);
order.setStatus(OrderStatus.SUBMITTED);
repository.save(order);
~~~

Đoạn mã phụ thuộc vào việc mọi setter được gọi đúng thứ tự và không bị bỏ sót. Nếu một nhánh xử lý quên set địa chỉ hoặc đặt trạng thái trước khi gán dòng hàng, Order có thể được lưu trong trạng thái không đúng.

Rủi ro còn lớn hơn khi đối tượng được truyền qua nhiều hàm:

- Một hàm có thể đọc status khi nó vẫn mang giá trị mặc định.
- Một callback có thể được gọi giữa hai lần set.
- Một luồng khác có thể nhìn thấy đối tượng khi dữ liệu chưa hoàn tất.
- Một entity có thể được lưu dù thiếu thông tin bắt buộc.
- Một domain event có thể được phát ra dựa trên trạng thái chưa hợp lệ.

Việc kiểm tra dữ liệu ở cuối quy trình không xóa được những khoảng thời gian đối tượng đã tồn tại trong trạng thái sai.

### 1.2. Setter công khai làm yếu quyền kiểm soát quy tắc

Setter tổng quát cho phép nơi gọi thay đổi dữ liệu mà không thể hiện lý do nghiệp vụ:

~~~java
order.setStatus(OrderStatus.CONFIRMED);
order.setTotal(Money.zero());
order.setBuyerId(otherBuyerId);
~~~

Những lệnh này có thể bỏ qua các điều kiện như phải giữ chỗ tồn kho trước khi xác nhận, tổng tiền phải được tính từ các dòng hàng hoặc người mua không được thay đổi sau khi đơn đã gửi.

Mô hình miền nên cung cấp hành vi diễn đạt ý định:

~~~java
order.confirm(reservationConfirmation);
order.changeDeliveryAddress(newAddress);
order.cancel(cancellationReason);
~~~

Mỗi hành vi có thể kiểm tra trạng thái hiện tại, dữ liệu đầu vào, quyền thực hiện và invariant liên quan. Đối tượng tự quyết định thay đổi nào hợp lệ.

### 1.3. Invariant cần đúng tại ranh giới thích hợp

Invariant là điều kiện phải luôn đúng đối với một đối tượng hoặc một nhóm đối tượng trong phạm vi nghiệp vụ được xác định.

Ví dụ:

- Order đã gửi phải có ít nhất một dòng hàng.
- Quantity của OrderLine phải lớn hơn 0.
- Money phải có số tiền và loại tiền hợp lệ.
- Shipment đã giao không thể quay lại trạng thái đang chuẩn bị.
- Tổng tiền đơn phải nhất quán với các dòng hàng và quy tắc giá đã áp dụng.

Không phải mọi quy tắc đều thuộc một object. Một số invariant thuộc aggregate; một số điều kiện phụ thuộc vào dịch vụ bên ngoài hoặc chính sách của context khác. Cần xác định đúng nơi sở hữu quy tắc để không nhồi mọi kiểm tra vào một constructor.

## 2. Phân biệt dữ liệu đầu vào với đối tượng miền

Một form trên giao diện có thể được gửi từng phần. Khách hàng có thể nhập tên trước, chọn địa chỉ sau, thêm sản phẩm rồi mới gửi đơn. Điều đó không có nghĩa Order trong miền phải là một object thiếu dữ liệu.

Hãy phân biệt:

- **Input DTO / Request:** biểu diễn dữ liệu nhận từ bên ngoài. Nó có thể thiếu trường, chứa chuỗi chưa chuẩn hóa hoặc có lỗi định dạng.
- **Command:** diễn đạt yêu cầu thực hiện một hành động, ví dụ SubmitOrder.
- **Value Object:** biểu diễn một giá trị đã được xác thực theo quy tắc miền, ví dụ Money hoặc ShippingAddress.
- **Entity / Aggregate:** biểu diễn đối tượng nghiệp vụ có identity, invariant và vòng đời.

Luồng xử lý thường có dạng:

1. Nhận request và kiểm tra cấu trúc cơ bản.
2. Chuyển đổi dữ liệu sang command hoặc Value Object.
3. Tải các dữ liệu miền cần thiết.
4. Gọi factory hoặc hành vi trên aggregate.
5. Lưu thay đổi trong transaction phù hợp.
6. Công bố sự kiện sau khi transaction được commit.

Không nên để request object trở thành Entity chỉ vì các trường dữ liệu giống nhau. Ranh giới giữa dữ liệu chưa tin cậy và mô hình đã được bảo vệ cần rõ ràng.

## 3. Bảo đảm hợp lệ ngay khi tạo

### 3.1. Constructor nhận các thông tin bắt buộc

Constructor nên yêu cầu những dữ liệu cần thiết để object có thể tồn tại hợp lệ ở trạng thái khởi đầu.

~~~java
public final class OrderLine {
    private final ProductId productId;
    private final Quantity quantity;
    private final Money unitPrice;

    public OrderLine(
            ProductId productId,
            Quantity quantity,
            Money unitPrice) {
        this.productId = Objects.requireNonNull(productId);
        this.quantity = Objects.requireNonNull(quantity);
        this.unitPrice = Objects.requireNonNull(unitPrice);
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity.value());
    }
}
~~~

Quantity và Money nên tự bảo vệ invariant của chúng. OrderLine vì vậy không phải lặp lại mọi kiểm tra của các Value Object mà nó sử dụng.

Constructor không nên chấp nhận giá trị mặc định giả tạo như ID rỗng, số lượng 0 hoặc trạng thái UNKNOWN chỉ để tạo được object. Nếu nghiệp vụ không cho phép những giá trị đó, hãy từ chối ngay tại điểm tạo.

### 3.2. Dùng factory để diễn đạt ý định tạo

Factory method giúp đặt tên cho cách tạo đối tượng và có thể ẩn constructor:

~~~java
public final class Order {
    private final OrderId id;
    private final BuyerId buyerId;
    private final List<OrderLine> lines;
    private final ShippingAddress deliveryAddress;
    private OrderStatus status;

    private Order(
            OrderId id,
            BuyerId buyerId,
            List<OrderLine> lines,
            ShippingAddress deliveryAddress) {
        this.id = Objects.requireNonNull(id);
        this.buyerId = Objects.requireNonNull(buyerId);
        this.lines = List.copyOf(lines);
        this.deliveryAddress =
            Objects.requireNonNull(deliveryAddress);

        if (this.lines.isEmpty()) {
            throw new IllegalArgumentException(
                "An order must contain at least one line"
            );
        }

        this.status = OrderStatus.SUBMITTED;
    }

    public static Order submit(
            OrderId id,
            BuyerId buyerId,
            List<OrderLine> lines,
            ShippingAddress deliveryAddress) {
        return new Order(id, buyerId, lines, deliveryAddress);
    }
}
~~~

Tên submit cho biết object được tạo ở trạng thái đã gửi. Factory có thể thực hiện thêm việc chuẩn hóa, kiểm tra hoặc tạo các giá trị cần thiết trước khi gọi constructor.

Trong ví dụ, constructor vẫn kiểm tra invariant để không phụ thuộc vào việc mọi caller đều nhớ gọi factory đúng cách. Khi constructor private, factory là cổng tạo duy nhất của class.

### 3.3. Dùng factory khi cần nhiều cách tạo hợp lệ

Một khái niệm có thể có nhiều cách tạo, nhưng mỗi cách phải tạo ra một trạng thái hợp lệ:

Các chữ ký sau minh họa những cổng tạo có tên; phần thân được lược bỏ vì phụ thuộc vào quy tắc chuyển đổi và xác minh của từng hệ thống:

~~~text
public static Order importFromLegacy(
        LegacyOrderData data,
        OrderId newId) {
    // Chuyển đổi và xác minh dữ liệu cũ.
    // Chỉ tạo Order sau khi các invariant được đáp ứng.
}

public static Order submit(
        SubmitOrder command,
        PricingQuote quote,
        ReservationConfirmation reservation) {
    // Tạo Order từ dữ liệu đã được xác nhận.
}
~~~

Hai factory có thể có logic khác nhau nhưng phải tuân thủ cùng các invariant của Order. Nếu dữ liệu legacy không đáp ứng quy tắc hiện tại, cần có chính sách chuyển đổi, cách ly hoặc xử lý ngoại lệ rõ ràng; không nên tạo object giả vờ hợp lệ.

### 3.4. Kiểm tra đầu vào ở nhiều lớp với mục đích khác nhau

Kiểm tra ở API và kiểm tra trong miền không thay thế nhau:

- API validation phát hiện dữ liệu sai định dạng, thiếu trường hoặc vượt giới hạn giao thức.
- Value Object validation bảo đảm giá trị được tạo đúng ngữ nghĩa.
- Aggregate validation bảo vệ invariant liên quan đến nhiều thành phần.
- Application layer kiểm tra quyền truy cập, tải dữ liệu và điều phối use case.
- Context sở hữu dữ liệu bên ngoài chịu trách nhiệm xác nhận các quy tắc thuộc về nó.

Ví dụ, API có thể kiểm tra quantity là số nguyên dương. Value Object Quantity tiếp tục bảo vệ điều kiện dương trong mọi đường tạo, kể cả khi dữ liệu đến từ message consumer hoặc batch import.

## 4. Trạng thái khởi đầu phải là trạng thái nghiệp vụ có nghĩa

Không phải mọi object đều phải hoàn tất toàn bộ vòng đời ngay khi được tạo. Một số nghiệp vụ thực sự có giai đoạn Draft, Pending hoặc Incomplete. Điều cần tránh là nhầm trạng thái nghiệp vụ hợp lệ với object bị khởi tạo dở dang do thiết kế kỹ thuật.

### 4.1. Draft có thể là trạng thái hợp lệ

Ví dụ, khách hàng có thể tạo một bản nháp đơn hàng trước khi chọn địa chỉ giao:

- Draft có thể chưa có dòng hàng.
- Draft có thể chưa có địa chỉ giao.
- Draft không được thanh toán hoặc đưa vào thực hiện.
- Khi gửi, hệ thống phải kiểm tra các điều kiện bắt buộc.

Nếu những quy tắc này được nghiệp vụ chấp nhận, Draft là một trạng thái hợp lệ với invariant riêng. Không nên gọi nó là một Order đã gửi nhưng thiếu dữ liệu.

Có thể mô hình hóa rõ bằng một aggregate có state:

~~~java
public final class Order {
    private final OrderId id;
    private final BuyerId buyerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private ShippingAddress deliveryAddress;
    private OrderStatus status;

    private Order(OrderId id, BuyerId buyerId) {
        this.id = Objects.requireNonNull(id);
        this.buyerId = Objects.requireNonNull(buyerId);
        this.status = OrderStatus.DRAFT;
    }

    public static Order startDraft(
            OrderId id,
            BuyerId buyerId) {
        return new Order(id, buyerId);
    }

    public void addLine(OrderLine line) {
        requireDraft();
        lines.add(Objects.requireNonNull(line));
    }

    public void chooseDeliveryAddress(
            ShippingAddress address) {
        requireDraft();
        this.deliveryAddress = Objects.requireNonNull(address);
    }

    public void submit() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "A draft needs at least one line before submission"
            );
        }
        if (deliveryAddress == null) {
            throw new IllegalStateException(
                "A delivery address is required before submission"
            );
        }
        status = OrderStatus.SUBMITTED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "This operation is only allowed for a draft"
            );
        }
    }
}
~~~

Đây là một lựa chọn mô hình: Draft được phép thiếu một số thông tin vì nghiệp vụ xác định rõ các thao tác được phép ở giai đoạn đó. Những phương thức addLine và chooseDeliveryAddress là hành vi nghiệp vụ có điều kiện, không phải setter công khai cho mọi trường.

Nếu một Draft chưa có ID, chưa có chủ sở hữu và chưa có bất kỳ quy tắc hay hành vi nghiệp vụ nào, có thể nó chỉ là dữ liệu form ở application layer chứ chưa cần trở thành domain object.

### 4.2. Mỗi trạng thái có invariant riêng

| Trạng thái | Điều kiện có thể áp dụng |
|---|---|
| Draft | Có người tạo; có thể chưa có dòng hàng hoặc địa chỉ |
| Submitted | Có ít nhất một dòng hàng và địa chỉ giao hợp lệ |
| Confirmed | Đã đáp ứng điều kiện giữ chỗ và thanh toán |
| Cancelled | Có lý do hủy phù hợp với chính sách |
| Completed | Đã hoàn tất các nghĩa vụ của đơn |

Các điều kiện trong bảng chỉ là ví dụ. Mỗi domain cần định nghĩa trạng thái và quy tắc cụ thể. Một trạng thái không nên được đặt tên chỉ để che giấu dữ liệu còn thiếu.

### 4.3. Có thể dùng type riêng cho từng giai đoạn

Khi các giai đoạn có cấu trúc và hành vi khác nhau rõ rệt, có thể biểu diễn bằng các kiểu riêng như OrderDraft và SubmittedOrder. Phương thức submit() trên Draft trả về một đối tượng SubmittedOrder sau khi kiểm tra đầy đủ.

Ưu điểm là một số sai sót được ngăn ngay từ kiểu dữ liệu: hàm cần SubmittedOrder không thể nhận OrderDraft. Đổi lại, cần quản lý identity, chuyển trạng thái, persistence và mapping giữa các kiểu. Chỉ dùng cách này khi lợi ích về tính rõ ràng lớn hơn độ phức tạp.

## 5. Chuyển trạng thái bằng hành vi có tên

### 5.1. Mô hình trạng thái như một quy trình nghiệp vụ

Một Entity thường có vòng đời gồm nhiều trạng thái và chuyển trạng thái. Không nên để caller tự gán trạng thái tùy ý.

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Submitted: submit
    Submitted --> Confirmed: confirm
    Submitted --> Rejected: reject
    Confirmed --> Cancelled: cancel when policy allows
    Confirmed --> Completed: complete
    Draft --> Cancelled: discard
    Rejected --> [*]
    Cancelled --> [*]
    Completed --> [*]
~~~

Sơ đồ chỉ minh họa một vòng đời. Thực tế có thể cần trạng thái PaymentPending, PartiallyFulfilled hoặc ReturnRequested. Hãy thêm trạng thái khi nó mang ý nghĩa và kéo theo quy tắc hoặc hành vi riêng.

### 5.2. Hành vi kiểm tra trạng thái trước khi thay đổi

~~~java
public void confirm(ReservationConfirmation reservation) {
    if (status != OrderStatus.SUBMITTED) {
        throw new IllegalStateException(
            "Only submitted orders can be confirmed"
        );
    }
    Objects.requireNonNull(reservation);
    if (!reservation.belongsTo(id)) {
        throw new IllegalArgumentException(
            "Reservation belongs to another order"
        );
    }

    status = OrderStatus.CONFIRMED;
}
~~~

Hành vi confirm diễn đạt ý định và bảo vệ điều kiện chuyển trạng thái. Caller không cần biết phải gán trường nào hoặc kiểm tra những điều kiện nào trước đó.

Trong hệ thống thực tế, xác nhận tồn kho có thể do Inventory Context sở hữu. Order chỉ nên nhận một kết quả hoặc bằng chứng đã được xác minh qua hợp đồng phù hợp; không nên tự truy cập database của Inventory để kiểm tra.

### 5.3. Phân biệt lệnh lặp và chuyển trạng thái không hợp lệ

Một request có thể được gửi lại do timeout hoặc người dùng bấm nhiều lần. Nghiệp vụ cần quyết định hành vi:

- Lệnh lặp có được xem là thành công nếu trạng thái đã đạt mục tiêu không?
- Có cần trả về kết quả trước đó không?
- Lệnh có cần idempotency key không?
- Lặp lại một lệnh có tạo domain event hoặc giao dịch thứ hai không?

Không nên tùy tiện bỏ qua mọi lệnh sai trạng thái. Có thể thiết kế confirm idempotent nếu đó là hợp đồng nghiệp vụ, nhưng phải phân biệt trường hợp cùng yêu cầu được gửi lại với một yêu cầu mới có dữ liệu khác.

## 6. Aggregate root chịu trách nhiệm bảo vệ invariant

Trong DDD, Aggregate là ranh giới nhất quán của một nhóm đối tượng. Aggregate Root là điểm truy cập bên ngoài để thay đổi trạng thái bên trong.

Nếu Order là Aggregate Root:

- Caller yêu cầu thay đổi thông qua Order.
- Order kiểm tra quy tắc của chính nó và các thành phần thuộc aggregate.
- OrderLine không nên được lấy ra rồi sửa trực tiếp từ bên ngoài.
- Repository tải và lưu aggregate root.
- Các invariant phải được bảo vệ tại ranh giới aggregate.

Ví dụ, nếu thêm dòng hàng có thể làm thay đổi tổng tiền, Order nên điều phối việc thêm dòng và tính lại tổng theo chính sách. Một phương thức công khai kiểu getLines() trả về collection mutable sẽ cho phép caller phá vỡ invariant.

~~~java
public List<OrderLine> lines() {
    return List.copyOf(lines);
}
~~~

Trả về bản sao hoặc view không sửa được giúp caller không thay đổi trực tiếp collection nội bộ. Việc cập nhật vẫn đi qua hành vi của aggregate.

Không nên gom mọi khái niệm liên quan vào một aggregate lớn. Chỉ giữ trong cùng aggregate những gì cần bảo đảm invariant nhất quán trong một ranh giới giao dịch. Những dữ liệu thuộc context khác nên được tham chiếu hoặc trao đổi qua hợp đồng.

## 7. Khi nào dùng constructor, factory hoặc builder?

### Constructor

Dùng constructor khi:

- Có một cách tạo chính và rõ ràng.
- Danh sách dữ liệu bắt buộc tương đối ổn định.
- Validation có thể thực hiện trực tiếp.
- Không cần tên factory để phân biệt ý nghĩa tạo.

Constructor nên bảo đảm object hợp lệ trước khi trả về. Tránh để constructor gọi phương thức có thể bị override hoặc công bố this ra ngoài khi object chưa hoàn tất.

### Static factory method

Dùng factory khi:

- Có nhiều cách tạo với ý nghĩa khác nhau.
- Cần đặt tên như openAccount, submitOrder, restoreFromSnapshot.
- Cần chuẩn hóa hoặc phối hợp tạo nhiều Value Object.
- Muốn ẩn constructor và kiểm soát cổng tạo.
- Cần trả về kiểu cụ thể hoặc kết quả tạo có điều kiện.

Factory không nên trở thành một nơi chứa toàn bộ nghiệp vụ. Nó có trách nhiệm tạo object ở trạng thái hợp lệ; các hành vi vòng đời tiếp theo vẫn thuộc object hoặc dịch vụ miền thích hợp.

### Builder

Builder có thể hữu ích khi object có nhiều tham số tùy chọn, cấu hình phức tạp hoặc cần API tạo dễ đọc. Tuy nhiên, builder không được phép tạo ra một domain object không hợp lệ.

Ví dụ:

~~~java
Order order = Order.builder()
    .id(orderId)
    .buyerId(buyerId)
    .line(firstLine)
    .deliveryAddress(address)
    .build();
~~~

Phương thức build() phải kiểm tra toàn bộ điều kiện bắt buộc và chỉ trả về object sau khi hợp lệ. Nếu thiếu địa chỉ hoặc không có dòng hàng, build phải thất bại bằng lỗi có ý nghĩa.

Builder có thể mang trạng thái từng bước, nhưng trạng thái dở dang của builder không đồng nghĩa với trạng thái dở dang của domain object. Builder là công cụ xây dựng; object chỉ được tạo khi các điều kiện của trạng thái khởi đầu được đáp ứng.

Không nên dùng builder cho mọi class. Một constructor hoặc factory ngắn thường dễ đọc hơn.

## 8. Xử lý quy trình nhập liệu nhiều bước

Một số quy trình nghiệp vụ cho phép người dùng nhập dữ liệu qua nhiều màn hình hoặc nhiều phiên làm việc. Có ba cách mô hình hóa thường gặp:

### Chỉ giữ dữ liệu tạm ở application layer

Nếu dữ liệu chưa có identity nghiệp vụ và chỉ phục vụ giao diện, có thể giữ trong form state, session hoặc request DTO. Chỉ tạo domain object khi người dùng xác nhận và dữ liệu đã đủ.

### Tạo một Draft có ý nghĩa nghiệp vụ

Nếu bản nháp cần lưu lại, có chủ sở hữu, có thời hạn, có quyền truy cập hoặc có quy tắc riêng, hãy mô hình hóa Draft như một trạng thái nghiệp vụ thực sự. Định nghĩa rõ thông tin nào bắt buộc cho Draft và hành vi nào được phép.

### Dùng một quy trình hoặc aggregate chuyên biệt

Nếu việc thu thập dữ liệu có nhiều bước, nhiều người tham gia, thời hạn và nhánh xử lý, có thể cần một aggregate như Application, OnboardingCase hoặc OrderDraft. Khi hoàn tất, nó có thể tạo ra một aggregate khác như Account hoặc Order.

Đừng tạo một đối tượng chính thức với các trường null rồi dùng cờ isComplete để quyết định mọi hành vi. Hãy mô tả giai đoạn đó bằng tên và quy tắc phù hợp.

## 9. Khởi tạo lại object từ database

Tạo mới một đối tượng từ yêu cầu nghiệp vụ và khôi phục đối tượng đã lưu là hai thao tác khác nhau.

- **Creation:** áp dụng quy tắc tạo mới, cấp identity, xác định trạng thái ban đầu và có thể phát sinh sự kiện nghiệp vụ.
- **Reconstitution / Hydration:** khôi phục trạng thái đã tồn tại từ persistence, giữ nguyên identity, trạng thái và dữ liệu lịch sử.

Khi tải một Order đã lưu, không được chạy lại hành vi submit() như thể khách vừa gửi đơn. Điều đó có thể tạo event trùng, tính lại giá theo chính sách mới hoặc thay đổi trạng thái đã lưu.

### 9.1. Không dùng setter công khai chỉ để ORM có thể hydrate

Một số ORM yêu cầu constructor không tham số, proxy hoặc field access. Nếu vì lý do đó mà mở setter công khai cho toàn bộ trạng thái, mọi caller trong ứng dụng có thể thay đổi dữ liệu tùy ý.

Các lựa chọn cần cân nhắc:

- Dùng cơ chế field access và constructor phù hợp với ORM/provider.
- Giữ constructor phục vụ persistence ở mức visibility cần thiết theo yêu cầu framework.
- Dùng persistence model riêng rồi chuyển đổi sang domain model hợp lệ.
- Dùng mapper hoặc factory reconstitution có kiểm soát.

Với JPA, yêu cầu cụ thể phụ thuộc phiên bản và cách mapping; entity class truyền thống thường cần constructor không tham số với visibility phù hợp và không nên là final. Hãy kiểm tra provider đang dùng trước khi chọn cách triển khai.

### 9.2. Khôi phục cũng phải phát hiện dữ liệu sai

Database có thể chứa dữ liệu lỗi do migration, phiên bản phần mềm cũ hoặc thao tác ngoài hệ thống. Reconstitution không nên âm thầm tạo object vi phạm invariant.

Có thể:

- Xác thực dữ liệu khi đọc và báo lỗi có ngữ cảnh.
- Dùng migration để sửa dữ liệu cũ trước khi nâng phiên bản.
- Cách ly bản ghi lỗi để xử lý.
- Có quy trình chuyển đổi rõ ràng cho trạng thái lịch sử không còn được tạo mới.

Nếu chính sách nghiệp vụ đã thay đổi, cần phân biệt dữ liệu hợp lệ theo quy tắc cũ với dữ liệu hỏng. Không nên áp dụng máy móc quy tắc mới để khiến mọi bản ghi lịch sử không thể tải.

### 9.3. Không phát lại domain event khi hydrate

Khôi phục một Order đã Confirmed không có nghĩa sự kiện OrderConfirmed vừa xảy ra. Domain event chỉ được tạo khi hành vi nghiệp vụ thực sự làm phát sinh sự kiện.

Nếu hệ thống dùng Event Sourcing, việc replay sự kiện là một cơ chế riêng để dựng lại trạng thái; nó cần tránh thực thi lại side effect như gửi email hoặc gọi thanh toán.

## 10. Domain Event và thời điểm công bố

Một hành vi như submit() hoặc confirm() có thể ghi nhận domain event sau khi invariant được bảo đảm:

~~~java
public void submit() {
    requireDraft();
    ensureHasLines();
    ensureDeliveryAddressSelected();

    status = OrderStatus.SUBMITTED;
    domainEvents.add(new OrderSubmitted(id));
}
~~~

Event được ghi nhận sau khi trạng thái hợp lệ đã được cập nhật trong bộ nhớ. Tuy nhiên, không nên gửi message ra bên ngoài ngay giữa transaction trước khi dữ liệu được commit.

Một quy trình phổ biến:

1. Aggregate thực hiện hành vi và ghi nhận domain event.
2. Application layer lưu aggregate trong transaction.
3. Sau khi commit thành công, event được chuyển đến handler hoặc message publisher.
4. Nếu cần bảo đảm không mất event giữa database và broker, cân nhắc Transactional Outbox.

Nếu transaction thất bại, event chưa được công bố. Điều này tránh tình huống consumer nhận OrderSubmitted trong khi bản ghi đơn hàng không tồn tại hoặc vẫn ở trạng thái cũ.

## 11. Ví dụ xuyên suốt: tạo và xác nhận đơn hàng

Giả sử nghiệp vụ có các quy tắc:

- Đơn phải thuộc về một người mua.
- Đơn gửi đi phải có ít nhất một dòng hàng.
- Mỗi dòng hàng có số lượng dương và đơn giá hợp lệ.
- Đơn gửi đi phải có địa chỉ giao.
- Chỉ đơn đã gửi mới được xác nhận.
- Đơn chỉ được xác nhận khi có bằng chứng giữ chỗ hợp lệ.

### 11.1. Value Object tự bảo vệ giá trị

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
    }
}

public record OrderLine(
    ProductId productId,
    Quantity quantity,
    Money unitPrice
) {
    public OrderLine {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(quantity);
        Objects.requireNonNull(unitPrice);
    }
}
~~~

### 11.2. Aggregate tạo ở trạng thái hợp lệ

~~~java
public final class Order {
    private final OrderId id;
    private final BuyerId buyerId;
    private final List<OrderLine> lines;
    private final ShippingAddress address;
    private OrderStatus status;
    private final List<DomainEvent> events = new ArrayList<>();

    private Order(
            OrderId id,
            BuyerId buyerId,
            List<OrderLine> lines,
            ShippingAddress address) {
        this.id = Objects.requireNonNull(id);
        this.buyerId = Objects.requireNonNull(buyerId);
        this.lines = List.copyOf(lines);
        this.address = Objects.requireNonNull(address);

        if (this.lines.isEmpty()) {
            throw new IllegalArgumentException(
                "An order must contain at least one line"
            );
        }

        this.status = OrderStatus.SUBMITTED;
    }

    public static Order submit(
            OrderId id,
            BuyerId buyerId,
            List<OrderLine> lines,
            ShippingAddress address) {
        Order order = new Order(id, buyerId, lines, address);
        order.events.add(new OrderSubmitted(id));
        return order;
    }

    public void confirm(ReservationConfirmation reservation) {
        if (status != OrderStatus.SUBMITTED) {
            throw new IllegalStateException(
                "Only submitted orders can be confirmed"
            );
        }
        Objects.requireNonNull(reservation);
        if (!reservation.belongsTo(id)) {
            throw new IllegalArgumentException(
                "Reservation does not belong to this order"
            );
        }

        status = OrderStatus.CONFIRMED;
        events.add(new OrderConfirmed(id));
    }

    public List<OrderLine> lines() {
        return lines;
    }

    public OrderId id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }

    public List<DomainEvent> pullDomainEvents() {
        List<DomainEvent> pending = List.copyOf(events);
        events.clear();
        return pending;
    }
}
~~~

Ví dụ tập trung vào nguyên tắc thiết kế; các kiểu ID, Value Object, sự kiện và persistence adapter được giả định đã được định nghĩa. Trong hệ thống thực, ReservationConfirmation cần tự bảo vệ tính hợp lệ, confirm có thể cần kiểm tra thêm số lượng và thời hạn giữ chỗ, còn việc lấy và công bố event phải phối hợp với transaction/outbox.

### 11.3. Application layer điều phối use case

~~~java
public final class SubmitOrderHandler {
    private final OrderRepository orders;
    private final OrderIdGenerator ids;
    private final UnitOfWork unitOfWork;

    public SubmitOrderHandler(
            OrderRepository orders,
            OrderIdGenerator ids,
            UnitOfWork unitOfWork) {
        this.orders = orders;
        this.ids = ids;
        this.unitOfWork = unitOfWork;
    }

    public OrderId handle(SubmitOrder command) {
        Order order = Order.submit(
            ids.next(),
            command.buyerId(),
            command.lines(),
            command.deliveryAddress()
        );

        unitOfWork.execute(() -> orders.save(order));
        return order.id();
    }
}
~~~

Handler điều phối use case và persistence. Nó không tự tạo một Order rỗng rồi gọi setter. Các quy tắc tạo Order nằm ở aggregate/factory; việc lưu nằm ở repository.

## 12. Kiểm thử vòng đời và invariant

Kiểm thử cần xác minh cả trạng thái hợp lệ lẫn việc hệ thống từ chối trạng thái sai.

### Kiểm thử tạo mới

- Tạo Order với dữ liệu đầy đủ thành công.
- Tạo Order không có BuyerId bị từ chối.
- Tạo Order không có dòng hàng bị từ chối khi trạng thái đầu là Submitted.
- Dòng hàng có Quantity không hợp lệ không thể được tạo.
- Collection truyền vào không thể bị caller sửa để làm thay đổi Order sau khi tạo.

### Kiểm thử chuyển trạng thái

- Draft có thể nhận dòng hàng và địa chỉ theo quy tắc.
- Draft không thể submit khi thiếu dòng hàng.
- Submitted có thể confirm khi có reservation hợp lệ.
- Draft không thể confirm.
- Confirmed không thể submit lại.
- Lệnh lặp có hành vi đúng với chính sách idempotency đã định nghĩa.

### Kiểm thử persistence và event

- Tải lại Order giữ nguyên ID và trạng thái.
- Hydration không phát sinh lại OrderSubmitted hoặc OrderConfirmed.
- Transaction rollback không công bố domain event ra bên ngoài.
- Lỗi dữ liệu cũ được phát hiện hoặc xử lý theo chính sách migration.

Không chỉ kiểm tra exception được ném ra. Hãy xác minh object không bị thay đổi một phần khi hành vi thất bại:

~~~java
OrderStatus before = order.status();

assertThrows(
    IllegalStateException.class,
    () -> order.confirm(invalidReservation)
);

assertEquals(before, order.status());
~~~

Nếu một hành vi gồm nhiều bước, hãy kiểm tra tất cả điều kiện trước khi mutation hoặc dùng cách đảm bảo thay đổi nguyên tử trong aggregate. Tránh cập nhật một phần rồi ném exception khiến object ở trạng thái dở dang.

## 13. Những sai lầm thường gặp

**Tạo object rỗng rồi gọi setter hàng loạt.** Cách này tạo ra khoảng thời gian object không hợp lệ và phụ thuộc vào thứ tự gọi. Dùng constructor hoặc factory với dữ liệu bắt buộc.

**Dùng giá trị mặc định để che thông tin thiếu.** ID rỗng, số lượng 0 hoặc trạng thái UNKNOWN có thể làm lỗi đi sâu vào hệ thống. Chỉ dùng giá trị mặc định khi nó có ý nghĩa nghiệp vụ rõ ràng.

**Đặt mọi field thành public hoặc có setter.** Caller có thể phá invariant mà không qua hành vi được kiểm soát. Giữ field private và cung cấp method theo ý nghĩa nghiệp vụ.

**Nhầm Draft với object khởi tạo dở dang.** Draft là trạng thái hợp lệ nếu nghiệp vụ định nghĩa quyền, dữ liệu và hành vi của nó. Nếu chỉ là form chưa gửi, hãy giữ nó ở application layer.

**Đưa mọi kiểm tra vào Application Service.** Điều phối thuộc application layer, nhưng invariant của Entity, Value Object và Aggregate cần được bảo vệ trong mô hình miền để mọi đường gọi đều tuân thủ.

**Dùng constructor công khai quá đơn giản cho nhiều cách tạo.** Khi có nhiều ý nghĩa tạo khác nhau, factory có tên giúp thể hiện ý định và tập trung kiểm tra.

**Dùng Builder nhưng cho phép build object sai.** Builder chỉ trì hoãn việc tạo object; build() vẫn phải xác minh toàn bộ điều kiện của trạng thái khởi đầu.

**Để ORM buộc phải mở setter nghiệp vụ.** Persistence concern cần được xử lý qua mapping, field access hoặc persistence model riêng. Không nên làm yếu API miền chỉ để thuận tiện cho framework.

**Phát event trước khi transaction commit.** Consumer có thể xử lý sự kiện cho một thay đổi cuối cùng bị rollback. Dùng cơ chế sau commit hoặc Transactional Outbox khi cần bảo đảm.

**Chạy lại hành vi tạo khi tải dữ liệu cũ.** Hydration không phải creation. Không được vô tình phát lại event hoặc áp dụng chính sách hiện tại lên lịch sử mà không có quy tắc chuyển đổi.

**Mutation trước rồi mới kiểm tra.** Nếu validation thất bại sau khi thay đổi một vài field, aggregate có thể bị bỏ lại trong trạng thái không hợp lệ. Hãy kiểm tra điều kiện trước khi thay đổi.

## 14. Quy trình thực hành

Khi thiết kế một Entity hoặc Aggregate mới, có thể làm theo trình tự:

1. Viết định nghĩa và trách nhiệm nghiệp vụ của đối tượng.
2. Liệt kê invariant phải đúng ở trạng thái khởi đầu.
3. Xác định các trạng thái hợp lệ trong vòng đời và điều kiện của từng trạng thái.
4. Phân biệt dữ liệu bắt buộc, tùy chọn và dữ liệu chỉ có ở giai đoạn sau.
5. Chọn constructor hoặc factory để chỉ tạo ra trạng thái khởi đầu hợp lệ.
6. Thiết kế method theo hành vi nghiệp vụ thay vì setter tổng quát.
7. Xác định aggregate root và giới hạn truy cập vào các thành phần bên trong.
8. Tách request/DTO khỏi domain object; xác định cách xử lý quy trình Draft nếu cần.
9. Thiết kế persistence reconstitution mà không chạy lại hành vi tạo hoặc phát event.
10. Kiểm thử invariant, chuyển trạng thái, rollback và xử lý lệnh lặp.

~~~mermaid
flowchart TD
    A["Xác định trách nhiệm và vòng đời"] --> B["Liệt kê invariant"]
    B --> C["Xác định trạng thái khởi đầu hợp lệ"]
    C --> D["Chọn constructor hoặc factory"]
    D --> E["Thiết kế hành vi chuyển trạng thái"]
    E --> F["Bảo vệ invariant tại aggregate root"]
    F --> G["Tách input model và persistence mapping"]
    G --> H["Kiểm thử creation, transition, hydration và event"]
~~~

## 15. Checklist trước khi đưa đối tượng vào sử dụng

**Tạo mới**

- Đối tượng có identity hoặc giá trị được xác định rõ chưa?
- Các dữ liệu bắt buộc đã được cung cấp đầy đủ chưa?
- Constructor/factory có kiểm tra invariant của trạng thái khởi đầu không?
- Có giá trị mặc định nào đang che giấu dữ liệu thiếu không?
- Có đường tạo nào khác bỏ qua kiểm tra không?

**Vòng đời**

- Các trạng thái hợp lệ đã được định nghĩa chưa?
- Mỗi hành vi có kiểm tra trạng thái hiện tại không?
- Có setter công khai cho trường làm thay đổi invariant không?
- Mutation có xảy ra sau khi mọi điều kiện đã được xác minh không?
- Lệnh lặp và lỗi giữa chừng được xử lý theo chính sách nào?

**Aggregate và persistence**

- Aggregate root có kiểm soát thay đổi của thành phần bên trong không?
- Collection hoặc object mutable có được bảo vệ không?
- Hydration có giữ nguyên identity và trạng thái không?
- ORM có yêu cầu đặc biệt nào đã được xử lý mà không mở quyền sửa tùy tiện không?
- Dữ liệu cũ không hợp lệ được phát hiện hoặc chuyển đổi ra sao?

**Sự kiện**

- Domain event chỉ được tạo khi hành vi nghiệp vụ thực sự xảy ra không?
- Event có được công bố sau commit không?
- Có cần Transactional Outbox hoặc cơ chế bảo đảm tương đương không?
- Hydration có tránh phát lại event không?

Đối tượng miền đáng tin cậy khi mọi đường tạo đều đưa nó vào một trạng thái được nghiệp vụ cho phép, và mọi thay đổi sau đó đều đi qua hành vi bảo vệ quy tắc. Khi giữ được nguyên tắc này, lỗi dữ liệu thiếu hoặc trạng thái sai sẽ được phát hiện gần nơi phát sinh, mô hình dễ hiểu hơn và các use case có thể dựa vào invariant thay vì liên tục kiểm tra lại mọi trường.
