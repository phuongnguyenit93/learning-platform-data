# Đặt logic điều phối ứng dụng vào đối tượng miền

Trong Domain-Driven Design (DDD), một lỗi thiết kế thường gặp là đưa toàn bộ quy trình của một use case vào Aggregate hoặc Entity. Đối tượng miền ban đầu chỉ nên bảo vệ trạng thái và quy tắc của chính nó, nhưng dần dần lại phải tải Repository, gọi cổng thanh toán, yêu cầu kho giữ hàng, gửi email, ghi log và điều phối nhiều hệ thống. Kết quả là domain model phụ thuộc vào hạ tầng, khó kiểm thử, khó tái sử dụng và khó thay đổi khi quy trình ứng dụng phát triển.

Lỗi ngược lại cũng phổ biến: mọi quy tắc nghiệp vụ đều bị đặt trong Application Service. Aggregate chỉ còn các field và getter/setter; service tự kiểm tra trạng thái, tính toán và cập nhật dữ liệu. Đây là mô hình domain nghèo nàn (Anemic Domain Model), khiến invariant bị phân tán giữa nhiều use case và caller có thể thay đổi trạng thái theo những cách không hợp lệ.

Thiết kế đúng cần phân biệt hai trách nhiệm. **Domain Model quyết định điều gì hợp lệ trong nghiệp vụ và bảo vệ invariant. Application Layer điều phối một use case bằng cách nạp đối tượng, gọi hành vi domain, phối hợp các port và quản lý ranh giới giao dịch.** Domain Service diễn đạt quy tắc nghiệp vụ không thuộc tự nhiên về một Entity hoặc Aggregate cụ thể. Application Service không thay thế quy tắc domain, và Aggregate không nên trở thành nơi điều khiển toàn bộ hệ thống.

Bài viết dùng quy trình hủy đơn hàng để giải thích ranh giới này. Aggregate Order quyết định đơn có được hủy và ghi nhận sự kiện OrderCancelled. Application Service điều phối việc nạp/lưu Order và gọi use case cần thiết. Những bước kéo dài qua Inventory, Payment và Shipping có thể được phối hợp bằng Saga hoặc Process Manager. Qua đó, ta sẽ nhận diện dấu hiệu đặt sai logic, refactor theo trách nhiệm và kiểm thử đúng từng lớp.

## 1. Phân biệt Domain Logic và Application Orchestration

Hai loại logic có thể cùng xuất hiện trong một use case nhưng trả lời những câu hỏi khác nhau.

- **Domain Logic:** Quy tắc nào đúng trong nghiệp vụ? Trạng thái nào được phép? Một hành động làm thay đổi ý nghĩa hoặc trạng thái của Aggregate ra sao?
- **Application Orchestration:** Để hoàn thành yêu cầu của người dùng, cần gọi những thành phần nào, theo thứ tự nào, trong transaction hoặc workflow nào?

Ví dụ với việc hủy đơn:

| Câu hỏi | Trách nhiệm phù hợp |
|---|---|
| Đơn đã giao có được hủy không? | Domain Model |
| Lý do hủy có bắt buộc không? | Domain Model nếu đó là quy tắc nghiệp vụ |
| Phí hủy được tính theo chính sách nào? | Domain Policy hoặc Domain Service |
| Lấy Order từ đâu? | Application Service + Repository |
| Ai gọi cổng hoàn tiền? | Application/Integration Adapter hoặc Payment use case |
| Ghi Order và Outbox trong transaction nào? | Application/Infrastructure |
| Gửi thông báo cho khách qua email nào? | Application/Infrastructure |
| Khi hoàn tiền thất bại thì workflow tiếp tục ra sao? | Saga/Process Manager cùng chính sách nghiệp vụ |

Ranh giới không dựa trên việc một đoạn code có vẻ “quan trọng” hay “phức tạp”. Nó dựa trên ý nghĩa của quyết định và trách nhiệm của thành phần.

### 1.1. Domain Model bảo vệ quy tắc

Aggregate Root là cổng vào để thay đổi trạng thái thuộc Aggregate. Các hành vi như đặt đơn, hủy đơn, thay đổi số lượng hoặc xác nhận điều kiện phải bảo vệ invariant mà mọi caller đều cần tuân thủ.

Ví dụ:

~~~java
public class Order {
    private OrderStatus status;
    private CancellationReason cancellationReason;

    public void cancel(CancellationReason reason) {
        if (!status.canBeCancelled()) {
            throw new OrderCannotBeCancelledException(id, status);
        }

        this.cancellationReason =
            Objects.requireNonNull(reason);
        this.status = OrderStatus.CANCELLED;
    }
}
~~~

Order không cần biết dữ liệu đang nằm trong PostgreSQL hay database khác. Nó chỉ biết quy tắc nào cho phép hủy đơn.

### 1.2. Application Layer điều phối use case

Application Service nhận yêu cầu, tải Aggregate, gọi hành vi domain và lưu kết quả:

~~~java
public class CancelOrderUseCase {
    private final OrderRepository orders;

    public CancelOrderUseCase(OrderRepository orders) {
        this.orders = orders;
    }

    public void handle(CancelOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() ->
                new OrderNotFoundException(command.orderId())
            );

        order.cancel(command.reason());

        orders.save(order);
    }
}
~~~

Application Service biết Repository và trình tự thao tác của use case. Nó không tự quyết định trạng thái nào được hủy; quyết định đó thuộc Order.

### 1.3. Không phải mọi câu lệnh đều phải nằm trong Domain Model

Việc kiểm tra input HTTP, chuyển DTO thành Command, mở transaction, gọi Repository, ghi Outbox, gửi message hoặc chuyển exception thành HTTP response không phải hành vi của Aggregate.

Một số thao tác có thể chứa quy tắc nghiệp vụ nhưng vẫn cần được đặt ở Domain Policy hoặc Domain Service. Hãy hỏi: “Đây là quyết định về ý nghĩa nghiệp vụ, hay là bước kỹ thuật để hoàn thành một use case?”

## 2. Khi Aggregate trở thành nơi điều phối toàn bộ ứng dụng

Một Aggregate có thể bắt đầu rất nhỏ, nhưng dần được bổ sung các dependency vì mỗi yêu cầu mới đều được triển khai bằng cách thêm một bước vào phương thức của nó.

### 2.1. Ví dụ thiết kế sai

Giả sử Order được viết như sau:

~~~java
public class Order {
    private OrderRepository orders;
    private InventoryGateway inventory;
    private PaymentGateway payments;
    private ShippingGateway shipping;
    private EmailSender emailSender;

    public void cancel(
            CancellationReason reason,
            UserId actorId) {

        if (status == OrderStatus.DELIVERED) {
            throw new IllegalStateException(
                "Cannot cancel delivered order"
            );
        }

        inventory.releaseReservation(id);
        payments.refund(paymentId);
        shipping.cancelShipment(id);
        status = OrderStatus.CANCELLED;
        orders.save(this);
        emailSender.sendCancellationNotice(id);
    }
}
~~~

Phương thức này trộn lẫn nhiều trách nhiệm:

- Kiểm tra quy tắc hủy đơn.
- Gọi hệ thống kho.
- Gọi cổng thanh toán.
- Gọi hệ thống giao vận.
- Lưu Aggregate.
- Gửi email.

Order đã trở thành một Application Service thu nhỏ. Nó còn giữ dependency tới hạ tầng và biết quá nhiều về các Bounded Context khác.

### 2.2. Những vấn đề phát sinh

**Domain phụ thuộc hạ tầng.** Để kiểm thử Order, phải dựng hoặc mock nhiều gateway. Một thay đổi ở SDK thanh toán có thể ảnh hưởng class domain.

**Không có ranh giới transaction rõ.** Database có thể rollback sau khi hàng đã được giải phóng hoặc tiền đã hoàn. Giao dịch bên ngoài không tự rollback cùng transaction database.

**Khó tái sử dụng hành vi.** Một use case khác muốn hủy đơn nhưng có quy trình hoàn tiền khác sẽ phải truyền thêm cờ hoặc tạo overload.

**Khó xử lý lỗi từng bước.** Nếu Inventory giải phóng thành công nhưng Payment timeout, Aggregate đang ở trạng thái nào? Gọi lại phương thức có giải phóng reservation lần nữa không?

**Aggregate có quá nhiều lý do để thay đổi.** Quy tắc hủy đơn, cách gọi gateway, mẫu email và cơ chế persistence có vòng đời khác nhau nhưng bị gom vào một class.

**Khó quan sát và vận hành.** Retry, timeout, idempotency và trạng thái workflow bị ẩn bên trong một phương thức đồng bộ.

### 2.3. Dấu hiệu nhận biết

Hãy xem xét thiết kế khi Aggregate hoặc Entity:

- Có constructor nhận Repository, HTTP client, message publisher hoặc email sender.
- Tự mở transaction hoặc gọi trực tiếp ORM.
- Gọi nhiều hệ thống bên ngoài trong một hành vi.
- Tự tìm Aggregate khác bằng Repository.
- Có các phương thức như processAll, executeWorkflow hoặc synchronizeEverything.
- Chứa logic retry, timeout hoặc cấu hình endpoint.
- Chỉ có thể kiểm thử bằng cách mock rất nhiều dependency.
- Có nhiều trạng thái trung gian liên quan tới tiến trình của hệ thống khác.

Một Aggregate có thể phát Domain Event hoặc nhận một Value Object chứa dữ liệu từ context khác. Điều đó không có nghĩa nó nên gọi trực tiếp hệ thống khác.

## 3. Lỗi ngược lại: Application Service chứa mọi quy tắc nghiệp vụ

Để tránh Aggregate quá lớn, một số đội chuyển toàn bộ logic sang Application Service. Cách này cũng gây vấn đề.

### 3.1. Ví dụ Anemic Domain Model

~~~java
public class Order {
    private OrderStatus status;
    private List<OrderLine> lines;
    private Money total;

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void setTotal(Money total) {
        this.total = total;
    }
}
~~~

Application Service phải tự kiểm tra và thay đổi trạng thái:

~~~java
public void cancelOrder(OrderId id) {
    Order order = orders.findById(id).orElseThrow();

    if (order.getStatus() == OrderStatus.DELIVERED) {
        throw new OrderCannotBeCancelledException(id);
    }

    if (order.getStatus() == OrderStatus.CANCELLED) {
        throw new OrderAlreadyCancelledException(id);
    }

    order.setStatus(OrderStatus.CANCELLED);
    order.setTotal(calculateRefund(order));

    orders.save(order);
}
~~~

Một use case có thể hoạt động, nhưng quy tắc hủy đơn đang nằm trong Application Service. Nếu một message handler, batch job hoặc use case khác cũng cần hủy đơn, logic có thể bị sao chép hoặc bỏ sót.

### 3.2. Vì sao đây là vấn đề?

- Invariant không được bảo vệ tại Aggregate Root.
- Caller có thể thay đổi trạng thái bằng setter mà không kiểm tra quy tắc.
- Quy tắc dễ bị sao chép giữa REST, message consumer và batch job.
- Unit Test của domain không thể chứng minh hành vi vì domain gần như không có hành vi.
- Application Service trở thành nơi chứa nhiều điều kiện nghiệp vụ và khó bảo trì.

### 3.3. Cách sửa

Đưa quyết định nghiệp vụ về đối tượng chịu trách nhiệm:

~~~java
public class Order {
    public void cancel(CancellationReason reason) {
        ensureCancellationAllowed();
        this.cancellationReason = reason;
        this.status = OrderStatus.CANCELLED;
    }

    private void ensureCancellationAllowed() {
        if (status == OrderStatus.DELIVERED) {
            throw new OrderCannotBeCancelledException(id);
        }
        if (status == OrderStatus.CANCELLED) {
            throw new OrderAlreadyCancelledException(id);
        }
    }
}
~~~

Application Service vẫn điều phối nạp và lưu Aggregate, nhưng không tự thực hiện invariant. Đây là cách cân bằng giữa Domain Model có hành vi và Application Layer có trách nhiệm điều phối.

## 4. Phân loại logic theo trách nhiệm

Khi một phương thức có nhiều bước, hãy phân loại từng bước trước khi quyết định nơi đặt code.

### 4.1. Quy tắc và invariant thuộc Domain Model

Ví dụ:

- Đơn đã giao không thể bị hủy.
- Số lượng của một dòng hàng phải lớn hơn không.
- Không thể thêm dòng hàng sau khi đơn đã được đặt.
- Giá trị hoàn tiền không được vượt số tiền có thể hoàn theo chính sách.
- Một Reservation không thể giải phóng sau khi đã tiêu thụ.

Các quy tắc này phải được bảo vệ bởi Aggregate, Entity, Value Object hoặc Domain Service phù hợp.

### 4.2. Điều phối thuộc Application Layer

Ví dụ:

- Tải Order theo ID.
- Kiểm tra caller đã xác thực và được phép gọi use case.
- Gọi hành vi Order.cancel.
- Lưu Aggregate trong transaction.
- Ghi Outbox.
- Trả kết quả cho Controller.
- Gọi hoặc gửi command tới một use case khác theo workflow.

Application Service có thể biết thứ tự bước thực hiện, nhưng không nên trở thành nơi tự diễn giải và thay đổi trạng thái nội bộ của Aggregate.

### 4.3. Quy tắc domain không thuộc một Entity cụ thể

Khi một quyết định nghiệp vụ cần nhiều đối tượng và không thuộc tự nhiên về một Aggregate, dùng Domain Service hoặc Domain Policy.

Ví dụ, chính sách xác định phí hủy có thể phụ thuộc thời điểm hủy, loại dịch vụ và trạng thái giao vận:

~~~java
public interface CancellationPolicy {
    CancellationDecision evaluate(
        Order order,
        CancellationTime requestedAt,
        FulfillmentStatus fulfillmentStatus
    );
}
~~~

Tên CancellationPolicy và CancellationDecision diễn đạt một khái niệm domain. Service này có thể là logic thuần domain; nếu cần dữ liệu từ nhiều context, Application Layer có thể thu thập dữ liệu rồi truyền vào policy.

Không biến Domain Service thành lớp chứa mọi thao tác kỹ thuật. Nó cần biểu đạt một quy tắc nghiệp vụ thực sự.

### 4.4. Chi tiết kỹ thuật thuộc Infrastructure

Các thành phần như JPA Repository adapter, HTTP client, message broker publisher, email sender và database transaction manager thuộc Infrastructure hoặc adapter ở ranh giới.

Domain và Application phụ thuộc vào abstraction phù hợp; Infrastructure triển khai các abstraction đó. Việc gọi API bên ngoài phải được đặt ở adapter hoặc use case phù hợp, không đưa SDK của nhà cung cấp vào Aggregate.

## 5. Ví dụ refactor: từ Order điều phối sang use case điều phối

Ta sẽ tách quy trình hủy đơn thành ba phần: hành vi của Order, use case hủy đơn và workflow xử lý các context liên quan.

### 5.1. Aggregate chỉ thay đổi trạng thái thuộc phạm vi của nó

~~~java
public class Order {
    private final OrderId id;
    private OrderStatus status;
    private CancellationReason cancellationReason;

    public void cancel(CancellationReason reason) {
        Objects.requireNonNull(reason, "reason");

        if (!status.canBeCancelled()) {
            throw new OrderCannotBeCancelledException(id, status);
        }

        this.status = OrderStatus.CANCELLED;
        this.cancellationReason = reason;
        registerEvent(new OrderCancelled(id, reason));
    }
}
~~~

Order biết quy tắc hủy đơn và ghi nhận Domain Event. Nó không gửi email, gọi Payment Gateway hoặc cập nhật Inventory.

### 5.2. Application Service điều phối use case

~~~java
public final class CancelOrderUseCase {
    private final OrderRepository orders;
    private final CurrentActor currentActor;

    public CancelOrderUseCase(
            OrderRepository orders,
            CurrentActor currentActor) {
        this.orders = orders;
        this.currentActor = currentActor;
    }

    public CancelOrderResult handle(CancelOrderCommand command) {
        Actor actor = currentActor.requireActor();

        Order order = orders.findById(command.orderId())
            .orElseThrow(() ->
                new OrderNotFoundException(command.orderId())
            );

        order.cancel(command.reason());

        orders.save(order);

        return new CancelOrderResult(
            order.id(),
            order.status()
        );
    }
}
~~~

Ví dụ rút gọn này giả định quyền truy cập đã được xác thực ở Application boundary. Nếu quyền hủy phụ thuộc quy tắc domain như vai trò của người yêu cầu hoặc điều kiện hợp đồng, hãy truyền thông tin có ý nghĩa vào domain policy và để policy quyết định. Không nên để Aggregate tự đọc security context hoặc HTTP request.

### 5.3. Lưu Aggregate và Outbox trong cùng transaction

Nếu OrderCancelled cần kích hoạt các xử lý khác, event nên được lưu bền vững cùng transaction cập nhật Order. Transactional Outbox giúp tránh trường hợp database commit nhưng message không được publish.

~~~java
@Transactional
public CancelOrderResult handle(CancelOrderCommand command) {
    Order order = orders.findById(command.orderId())
        .orElseThrow(() ->
            new OrderNotFoundException(command.orderId())
        );

    order.cancel(command.reason());

    orders.save(order);
    outbox.appendAll(order.pullDomainEvents());

    return new CancelOrderResult(order.id(), order.status());
}
~~~

Đây là phác thảo. Cách lấy và xóa Domain Event phụ thuộc thiết kế Aggregate và Unit of Work. Điều quan trọng là thay đổi Order và bản ghi Outbox được commit nguyên tử trong cùng database transaction. Publisher đọc Outbox sau commit và gửi message; consumer cần idempotent vì message có thể được giao lại.

### 5.4. Workflow bên ngoài được điều phối riêng

Khi OrderCancelled được công bố, các bước có thể gồm:

- Inventory giải phóng Reservation nếu còn hiệu lực.
- Payment kiểm tra điều kiện và thực hiện Refund.
- Shipping yêu cầu dừng Shipment nếu chưa bàn giao.
- Notification gửi thông báo phù hợp cho khách hàng.

Các hành động này thuộc những capability hoặc Bounded Context khác nhau. Chúng không nên được gọi trực tiếp từ Order Aggregate.

## 6. Domain Event, Saga và Process Manager

Khi một use case chỉ thay đổi một Aggregate trong một transaction, Application Service có thể điều phối đơn giản. Khi quy trình đi qua nhiều Aggregate hoặc Bounded Context và kéo dài theo thời gian, cần mô hình hóa workflow rõ ràng.

### 6.1. Domain Event ghi nhận điều đã xảy ra

OrderCancelled diễn đạt một sự việc đã xảy ra trong Ordering. Event không nên mang ý nghĩa “hãy hủy đơn” vì đó là command.

Phân biệt:

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| Command | CancelOrder | Yêu cầu thực hiện hành động |
| Domain Event | OrderCancelled | Đơn đã được hủy trong domain |
| Integration Event | OrderCancellationAccepted | Contract công bố cho context khác |
| Process State | CancellationWorkflow | Trạng thái tiến trình nhiều bước |

Tên event cần ở dạng sự việc đã xảy ra. Một event được phát ra sau khi Aggregate đã quyết định và transaction ghi nhận thay đổi thành công.

### 6.2. Saga điều phối quy trình nhiều bước

Một quy trình hủy đơn có thể cần:

1. Ghi nhận yêu cầu hủy.
2. Giải phóng reservation.
3. Hoàn tiền nếu có khoản đã capture.
4. Hủy shipment nếu có thể.
5. Hoàn tất hoặc ghi nhận phần việc cần xử lý thủ công.

Các bước có thể chạy bất đồng bộ và không nằm trong cùng một transaction. Saga/Process Manager lưu trạng thái workflow, gửi command tới context tương ứng, nhận event kết quả và quyết định bước tiếp theo.

~~~mermaid
flowchart TD
    A["CancelOrder Command"] --> B["Ordering: Order.cancel()"]
    B --> C["Commit Order + Outbox"]
    C --> D["Cancellation Saga"]
    D --> E["Inventory: ReleaseReservation"]
    D --> F["Payment: RefundPayment"]
    D --> G["Shipping: CancelShipment"]
    E --> H["Receive results"]
    F --> H
    G --> H
    H --> I{"All required steps complete?"}
    I -->|Yes| J["Cancellation workflow completed"]
    I -->|No| K["Retry, compensate or manual review"]
~~~

Sơ đồ thể hiện một workflow khái niệm. Thứ tự thực tế phụ thuộc chính sách: có thể phải xác nhận khả năng hủy shipment trước khi hoàn tiền, hoặc thực hiện song song các bước độc lập.

### 6.3. Xử lý thất bại bằng retry và hành động bù

Trong distributed workflow, không có rollback tự động cho một API bên ngoài đã thành công. Nếu Inventory đã giải phóng hàng nhưng Payment không hoàn tiền được, hệ thống cần ghi nhận trạng thái tiến trình và quyết định:

- Retry khi lỗi có tính tạm thời.
- Chờ phản hồi từ nhà cung cấp.
- Gửi command bù nếu một bước trước cần được đảo ngược.
- Chuyển sang xử lý thủ công nếu cần quyết định nghiệp vụ.
- Thông báo cho người dùng trạng thái phù hợp.

Hành động bù không nhất thiết là đảo ngược chính xác hành động trước. Ví dụ, nếu shipment đã bàn giao cho hãng vận chuyển, không thể chỉ “undo dispatch”; có thể cần yêu cầu return hoặc intercept.

### 6.4. Không nhầm Saga với Domain Service

Domain Service diễn đạt quy tắc nghiệp vụ thuần hoặc quyết định domain. Saga/Process Manager quản lý tiến trình nhiều bước, trạng thái chờ, retry và phản ứng với event theo thời gian.

Saga có thể cần áp dụng chính sách domain, nhưng không nên trở thành Aggregate Order hoặc Domain Service chỉ vì nó có tên nghiệp vụ.

## 7. Phân biệt Application Service, Domain Service và Domain Event Handler

Ba thành phần này thường bị nhầm lẫn khi thiết kế.

| Thành phần | Trách nhiệm chính | Có thể phụ thuộc Repository/port? |
|---|---|---|
| Aggregate / Entity | Bảo vệ invariant và hành vi thuộc đối tượng | Không gọi hạ tầng trực tiếp |
| Domain Service | Quy tắc domain không thuộc tự nhiên về một Entity | Có thể dùng abstraction domain khi cần, nhưng không phụ thuộc framework |
| Application Service | Điều phối một use case | Có, qua port/repository |
| Domain Event Handler | Phản ứng với event trong phạm vi context | Tùy handler; thường điều phối use case hoặc xử lý domain |
| Saga / Process Manager | Theo dõi workflow nhiều bước | Có, cần lưu trạng thái và gửi command |
| Infrastructure Adapter | Giao tiếp database, broker, HTTP, email | Có phụ thuộc công nghệ |

### 7.1. Application Service không phải nơi chứa mọi quyết định

Application Service có thể kiểm tra điều kiện kỹ thuật như caller đã xác thực, request có đủ dữ liệu và dependency có sẵn. Nhưng nếu điều kiện mang ý nghĩa nghiệp vụ, chẳng hạn đơn có thể hủy trước khi đóng gói, quyết định phải được bảo vệ ở domain.

### 7.2. Domain Service không phải Application Service đổi tên

Một class tên OrderDomainService nhưng chứa logic sau đây vẫn là điều phối ứng dụng:

~~~java
public void cancel(OrderId id) {
    Order order = orders.findById(id).orElseThrow();
    paymentGateway.refund(order.paymentId());
    inventory.release(order.id());
    emailSender.send(order.customerEmail());
    order.setStatus(CANCELLED);
    orders.save(order);
}
~~~

Tên class không thay đổi trách nhiệm. Hãy phân loại theo việc nó đang làm.

### 7.3. Event handler cũng cần ranh giới rõ

Một handler nhận OrderCancelled có thể gọi một Application Use Case hoặc gửi command sang context khác. Nó không nên tự viết lại quy tắc hủy đơn. Nếu handler cần thay đổi Aggregate khác, hãy nạp Aggregate đó và gọi hành vi của nó.

## 8. Quyền truy cập và dữ liệu từ bên ngoài

Một số đoạn điều phối thường bị đưa vào Aggregate vì người viết muốn “gom logic vào domain”. Tuy nhiên, có những thông tin thuộc ranh giới ứng dụng hoặc bảo mật.

### 8.1. Không để Aggregate đọc security context

Không nên viết:

~~~java
public void cancel(CancellationReason reason) {
    UserId actor = SecurityContextHolder.getContext()...;
    // ...
}
~~~

Aggregate không nên phụ thuộc Spring Security, HTTP session hoặc thread-local. Application Layer lấy danh tính đã xác thực và truyền vào dưới dạng ActorId hoặc một dữ liệu domain có ý nghĩa nếu quy tắc cần nó.

### 8.2. Phân biệt authorization kỹ thuật và quy tắc nghiệp vụ

- “Người dùng có quyền gọi endpoint này không?” thường thuộc Application/Security boundary.
- “Chỉ người tạo yêu cầu mới được hủy trước khi xử lý?” có thể là quy tắc domain.
- “Nhân viên quản lý có thể hủy khi đơn chưa đóng gói?” là chính sách nghiệp vụ cần được mô hình hóa rõ.

Một policy có thể nhận Actor và Order để quyết định. Không để Aggregate tự truy vấn hệ thống quyền hoặc đọc token.

### 8.3. Không để Aggregate gọi dịch vụ bên ngoài để lấy dữ liệu

Nếu hành vi cần dữ liệu từ context khác, Application Service có thể lấy dữ liệu qua port và truyền vào hành vi hoặc Domain Policy. Hãy xác định thời điểm dữ liệu được đọc và liệu nó có thể thay đổi trước khi transaction commit hay không.

Nếu quyết định cần bảo đảm nguyên tử xuyên context, một lời gọi HTTP đồng bộ không tạo ra transaction phân tán an toàn. Cần thiết kế reservation, version, idempotency hoặc workflow phù hợp.

## 9. Transaction boundary và consistency

Application Layer thường xác định ranh giới transaction cho một use case. Aggregate bảo vệ invariant trong ranh giới nhất quán của nó; Application Service không nên giả định mọi hệ thống ngoài có thể rollback cùng database.

### 9.1. Transaction cho một Aggregate

Một use case có thể:

1. Mở transaction.
2. Nạp Order.
3. Gọi Order.cancel().
4. Lưu Order và Outbox.
5. Commit.

Đây là ranh giới phù hợp khi các thay đổi cần nhất quán cùng nhau nằm trong một database transaction.

### 9.2. Không giữ transaction database trong lúc chờ HTTP lâu

Gọi Payment Gateway hoặc Shipping API trong khi giữ transaction mở có thể làm connection bị chiếm lâu, tăng lock duration và tạo rủi ro timeout. Thường nên commit trạng thái workflow hoặc Outbox rồi xử lý tích hợp bất đồng bộ.

Nếu nghiệp vụ cần một quyết định đồng bộ trước khi chấp nhận hành động, hãy thiết kế timeout, idempotency, retry và trạng thái không chắc chắn rõ ràng. Không nên coi timeout là bằng chứng rằng hệ thống ngoài chưa thực hiện hành động.

### 9.3. Eventual consistency cần được thể hiện trong mô hình

Nếu hủy đơn được ghi nhận ngay nhưng refund hoàn tất sau đó, UI và API cần phân biệt trạng thái đơn với trạng thái hoàn tiền. Ví dụ:

- OrderStatus: CANCELLED.
- RefundStatus: PENDING.
- CancellationWorkflowStatus: IN_PROGRESS.

Không nên ép tất cả thành một enum OrderStatus có hàng chục giá trị kết hợp. Các context và quy trình có vòng đời khác nhau cần mô hình riêng.

## 10. Refactor từng bước khi logic điều phối đang nằm trong Aggregate

Không cần viết lại toàn bộ hệ thống. Có thể tách trách nhiệm theo từng hành vi và giữ tương thích trong quá trình chuyển đổi.

### Bước 1: Ghi lại hành vi hiện tại

Chọn một phương thức có nhiều dependency, ví dụ Order.cancel. Ghi lại:

- Quy tắc nghiệp vụ đang được kiểm tra.
- Các hệ thống được gọi.
- Thứ tự thao tác.
- Những thay đổi database.
- Các lỗi và cách retry.
- Các caller đang sử dụng phương thức.

Tạo characterization test để bảo vệ hành vi hiện tại trước khi refactor.

### Bước 2: Phân loại từng đoạn logic

Đánh dấu từng đoạn là:

- Invariant hoặc quyết định domain.
- Điều phối use case.
- Tích hợp hạ tầng.
- Xử lý giao dịch.
- Trình bày hoặc thông báo.

Đừng di chuyển code chỉ dựa vào tên class. Xác định ý nghĩa và nguồn dữ liệu của mỗi quyết định.

### Bước 3: Đưa hành vi về Aggregate

Tạo phương thức domain có tên rõ, ví dụ Order.cancel(reason). Chuyển các điều kiện trạng thái và thay đổi dữ liệu thuộc Order vào phương thức đó.

Giữ các dependency hạ tầng bên ngoài Aggregate.

### Bước 4: Tạo hoặc chỉnh Application Use Case

Application Service nạp Aggregate, lấy dữ liệu cần thiết từ các port, gọi hành vi domain, lưu thay đổi và ghi Outbox nếu cần.

Không để Application Service tự sửa private state qua setter hoặc reflection.

### Bước 5: Tách workflow nhiều context

Nếu use case gọi Inventory, Payment và Shipping, xác định bước nào đồng bộ, bước nào bất đồng bộ, bước nào có thể retry hoặc cần hành động bù. Dùng Saga/Process Manager khi workflow có trạng thái kéo dài và nhiều phản hồi.

### Bước 6: Bảo vệ compatibility

Nếu caller cũ đang gọi phương thức điều phối trên Aggregate, có thể giữ một façade tạm thời trong giai đoạn chuyển đổi nhưng chuyển trách nhiệm sang Application Service. Lập kế hoạch loại bỏ API cũ sau khi caller được cập nhật.

Không giữ façade lâu dài nếu nó tiếp tục khiến domain phụ thuộc vào Application Layer hoặc tạo hai cách thực hiện không nhất quán.

### Bước 7: Xóa đường đi cũ và kiểm tra lại

Khi caller đã chuyển:

- Xóa dependency hạ tầng khỏi Aggregate.
- Loại bỏ setter chỉ phục vụ quy trình cũ.
- Kiểm tra không còn caller tự thực hiện invariant.
- Chạy Unit Test domain, Application Test và Integration Test adapter.
- Kiểm tra log, metric và retry của workflow mới.

## 11. Kiểm thử theo đúng ranh giới

Khi logic được đặt đúng nơi, test có thể nhỏ hơn và tập trung vào trách nhiệm cụ thể.

### 11.1. Unit Test cho Aggregate

Kiểm tra các quy tắc:

~~~java
@Test
void deliveredOrderCannotBeCancelled() {
    Order order = TestOrders.delivered();

    assertThrows(
        OrderCannotBeCancelledException.class,
        () -> order.cancel(CancellationReason.customerRequest())
    );
}
~~~

Test không cần mock Payment Gateway hoặc Inventory vì Aggregate không gọi các thành phần đó.

### 11.2. Unit Test cho Domain Service hoặc Policy

Nếu CancellationPolicy quyết định phí hủy, kiểm tra các điều kiện nghiệp vụ:

- Hủy trước khi đóng gói.
- Hủy sau khi bàn giao.
- Loại sản phẩm không được hủy.
- Yêu cầu hủy do doanh nghiệp khởi tạo.
- Mốc thời gian và chính sách có hiệu lực.

Dùng dữ liệu domain rõ ràng thay vì mock mọi đối tượng.

### 11.3. Application Test cho điều phối

Test Application Service với fake Repository và fake port có thể xác minh:

- Aggregate được nạp theo ID đúng.
- Hành vi domain được gọi.
- Aggregate được lưu khi thao tác thành công.
- Không lưu nếu domain từ chối.
- Outbox hoặc command được tạo đúng theo contract.
- Quyền truy cập được kiểm tra ở boundary phù hợp.

Application Test không cần chứng minh SQL chạy đúng; việc đó thuộc Repository Integration Test.

### 11.4. Integration Test cho transaction và Outbox

Dùng database test thật để xác minh:

- Order và Outbox cùng commit.
- Nếu transaction rollback, cả hai đều không được lưu.
- Publisher chỉ xử lý bản ghi đã commit.
- Consumer xử lý message trùng an toàn.
- Retry không tạo refund hoặc release reservation lặp ngoài chính sách.

### 11.5. Test Saga bằng chuỗi event

Một test workflow có thể mô phỏng:

1. Nhận OrderCancelled.
2. Gửi ReleaseReservation và RefundPayment.
3. Nhận ReservationReleased.
4. Nhận RefundFailed.
5. Kiểm tra Saga ghi nhận trạng thái chờ retry hoặc manual review.
6. Nhận RefundCompleted sau retry.
7. Kiểm tra workflow kết thúc.

Test cần xác minh trạng thái và command phát ra, không phụ thuộc vào thời gian thực của hệ thống bên ngoài.

## 12. Những sai lầm thường gặp

**Đưa Repository vào Aggregate để Aggregate tự nạp đối tượng khác.** Điều này làm domain phụ thuộc persistence và dễ vượt ranh giới Aggregate. Application Layer nạp các dữ liệu cần thiết rồi gọi hành vi phù hợp.

**Đưa HTTP client hoặc SDK vào Entity.** Domain bị gắn với công nghệ và khó kiểm thử. Giao tiếp bên ngoài thuộc adapter hoặc use case.

**Đưa mọi quy tắc vào Application Service.** Aggregate trở thành túi dữ liệu và invariant bị phân tán. Đưa quyết định nghiệp vụ về Aggregate, Value Object hoặc Domain Service.

**Đổi tên Application Service thành Domain Service nhưng giữ nguyên trách nhiệm.** Tên không quyết định kiến trúc. Hãy xem thành phần có đang điều phối Repository, email, gateway và transaction hay đang diễn đạt một quy tắc domain.

**Cho Aggregate phát email hoặc gọi message broker.** Việc gửi có thể thất bại hoặc lặp, và không nguyên tử với transaction database. Ghi Domain Event/Outbox rồi xử lý ở adapter hoặc workflow.

**Dùng một transaction cho nhiều hệ thống độc lập.** Một database transaction không rollback được HTTP call đã thành công. Dùng Saga, idempotency và hành động bù theo quy trình.

**Đặt toàn bộ workflow dài vào một phương thức đồng bộ.** Caller khó hiểu trạng thái chờ và retry. Mô hình hóa tiến trình nếu nó kéo dài qua nhiều bước hoặc context.

**Để Domain Event làm command.** Event mô tả việc đã xảy ra; command yêu cầu hành động. Phân biệt hai loại để tránh phát thông báo thành công trước khi domain commit.

**Để event handler tự sửa field Aggregate.** Handler phải gọi hành vi của Aggregate được nạp, không bỏ qua invariant bằng setter.

**Đưa security context vào Aggregate.** Domain phụ thuộc framework và môi trường thực thi. Application Layer lấy Actor đã xác thực rồi truyền dữ liệu cần thiết.

**Chuyển logic mà không có characterization test.** Refactor có thể vô tình thay đổi semantics. Ghi nhận hành vi cũ và kiểm thử trước khi di chuyển.

## 13. Quy trình quyết định nơi đặt logic

Khi gặp một đoạn code mới, có thể dùng chuỗi câu hỏi sau:

1. Đoạn code có quyết định một quy tắc hoặc trạng thái nghiệp vụ không?
2. Quy tắc đó thuộc identity hoặc invariant của Aggregate nào?
3. Nếu không thuộc một Entity cụ thể, có phải một Domain Service/Policy không?
4. Đoạn code có nạp/lưu dữ liệu, gọi port, mở transaction hoặc phối hợp use case không?
5. Nó có kéo dài qua nhiều context hoặc chờ event từ hệ thống khác không?
6. Có cần lưu trạng thái tiến trình, retry hoặc hành động bù không?
7. Thành phần có thể được kiểm thử mà không cần khởi động toàn bộ hạ tầng không?

Gợi ý phân loại:

| Nếu đoạn code... | Nơi thường phù hợp |
|---|---|
| Bảo vệ trạng thái và invariant của Order | Order Aggregate |
| Kiểm tra địa chỉ có phục vụ được theo policy | Domain Policy/Service nếu là quy tắc nghiệp vụ |
| Nạp Order và gọi order.cancel() | Application Service |
| Lưu Order bằng JPA | Repository Adapter |
| Gửi message ra broker | Outbox Publisher/Infrastructure |
| Điều phối refund, release stock và shipment qua thời gian | Saga/Process Manager |
| Chuyển request HTTP thành Command | Controller/Adapter |

Đây là hướng dẫn, không phải công thức máy móc. Một quyết định có thể cần nhiều lớp cùng tham gia, nhưng mỗi lớp cần giữ một trách nhiệm rõ.

## 14. Ví dụ hoàn chỉnh: luồng hủy đơn có workflow bất đồng bộ

Giả sử khách hàng yêu cầu hủy đơn sau khi thanh toán. Ordering quyết định đơn có được hủy. Payment chịu trách nhiệm hoàn tiền. Inventory quản lý reservation. Shipping quản lý shipment.

### 14.1. Command đầu vào

~~~java
public record CancelOrderCommand(
    OrderId orderId,
    CancellationReason reason,
    ActorId requestedBy
) {}
~~~

Controller xác thực caller và chuyển request thành command. Application Service kiểm tra quyền ở boundary; nếu chính sách hủy phụ thuộc người yêu cầu, thông tin ActorId được truyền vào policy hoặc hành vi domain.

### 14.2. Aggregate bảo vệ quy tắc

~~~java
public void cancel(
        CancellationReason reason,
        ActorId actorId) {

    if (!cancellationPolicy.isAllowed(status, actorId)) {
        throw new OrderCannotBeCancelledException(id, status);
    }

    this.status = OrderStatus.CANCELLED;
    this.cancellationReason = reason;
    registerEvent(new OrderCancelled(id, reason, actorId));
}
~~~

Trong ví dụ, cancellationPolicy có thể là một policy thuần domain được truyền vào Aggregate hoặc được gọi bởi một domain service trước hành vi. Chọn cách nào phụ thuộc độ phức tạp và khả năng giữ invariant; không để policy truy cập trực tiếp HTTP hoặc database.

### 14.3. Use case ghi nhận việc hủy

~~~java
@Transactional
public CancelOrderResult handle(CancelOrderCommand command) {
    Order order = orders.findById(command.orderId())
        .orElseThrow(() ->
            new OrderNotFoundException(command.orderId())
        );

    order.cancel(command.reason(), command.requestedBy());

    orders.save(order);
    outbox.appendAll(order.pullDomainEvents());

    return new CancelOrderResult(
        order.id(),
        CancellationStatus.ACCEPTED
    );
}
~~~

Khi transaction commit, đơn đã được ghi nhận là hủy và event có thể được publish. Kết quả ACCEPTED nói rằng yêu cầu đã được tiếp nhận theo quy tắc Ordering; nó không khẳng định tiền đã hoàn hoặc shipment đã dừng.

### 14.4. Saga theo dõi phần việc còn lại

Saga nhận event và gửi command tới các context. Nó lưu trạng thái từng bước, correlation ID, retry count và kết quả. Khi mọi bước bắt buộc hoàn tất, workflow được đánh dấu Completed. Nếu có lỗi, nó retry hoặc chuyển manual review theo chính sách.

API có thể cung cấp hai thông tin riêng:

~~~json
{
  "orderStatus": "CANCELLED",
  "cancellationWorkflowStatus": "IN_PROGRESS",
  "refundStatus": "PENDING"
}
~~~

Cấu trúc này giúp client hiểu đơn đã hủy trong Ordering nhưng phần hoàn tiền vẫn đang xử lý. Không nên gộp các trạng thái khác vòng đời vào một field duy nhất.

## 15. Checklist rà soát Aggregate và Application Service

**Domain Model**

- Aggregate có bảo vệ invariant của chính nó không?
- Hành vi có tên theo ngôn ngữ nghiệp vụ không?
- Có setter công khai cho trạng thái cần bảo vệ không?
- Aggregate có phụ thuộc HTTP, ORM, message broker hoặc SDK không?
- Domain Service chỉ chứa quy tắc domain có ý nghĩa không?

**Application Layer**

- Use case có nạp đúng Aggregate và gọi hành vi domain không?
- Application Service có tự sửa field hoặc lặp lại invariant không?
- Quyền truy cập kỹ thuật có được kiểm tra ở boundary phù hợp không?
- Transaction và Outbox có được quản lý rõ không?
- Các port được gọi theo trình tự và contract dễ kiểm thử không?

**Workflow nhiều context**

- Có trạng thái tiến trình khi thao tác kéo dài không?
- Retry và idempotency có được xác định không?
- Hành động bù có phản ánh thực tế nghiệp vụ không?
- Có phân biệt trạng thái Aggregate với trạng thái workflow không?
- Người dùng có thể biết phần việc nào đang chờ hoặc thất bại không?

**Kiểm thử và vận hành**

- Aggregate có Unit Test độc lập không?
- Application Service có test điều phối không?
- Repository/Outbox có Integration Test với database phù hợp không?
- Saga có test chuỗi event, retry và lỗi không?
- Có log, metric và correlation ID để theo dõi tiến trình không?

## 16. Kết luận

Đặt logic điều phối ứng dụng vào đối tượng miền làm Aggregate trở nên phụ thuộc vào Repository, hệ thống ngoài, transaction và cơ chế vận hành. Nhưng chuyển mọi quy tắc sang Application Service cũng khiến domain model nghèo nàn và invariant bị phân tán.

DDD yêu cầu giữ rõ hai trách nhiệm: Domain Model bảo vệ quy tắc và trạng thái nghiệp vụ; Application Layer điều phối use case bằng cách nạp đối tượng, gọi hành vi, phối hợp port và quản lý transaction. Domain Service diễn đạt quy tắc không thuộc tự nhiên về một Entity. Saga hoặc Process Manager điều phối workflow kéo dài qua nhiều Aggregate hay Bounded Context.

Khi refactor, hãy bắt đầu từ một hành vi cụ thể, ghi lại semantics hiện tại, đưa invariant về Aggregate, chuyển việc nạp/lưu và tích hợp sang Application Layer, rồi mô hình hóa các bước bất đồng bộ bằng event và workflow phù hợp. Kiểm thử từng ranh giới sẽ giúp domain giữ được tính độc lập, use case dễ đọc và hệ thống có thể tiến hóa mà không biến Aggregate thành bộ điều khiển của toàn ứng dụng.

