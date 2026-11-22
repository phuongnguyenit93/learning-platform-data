# Giữ lớp ứng dụng gọn mà vẫn thể hiện rõ trình tự điều phối

Trong Domain-Driven Design (DDD), **Application Layer (lớp ứng dụng)** thể hiện các ca sử dụng mà hệ thống cung cấp và điều phối những bước cần thiết để hoàn thành chúng. Lớp này kết nối đầu vào từ người dùng hoặc hệ thống khác với mô hình miền, Repository và các cổng tích hợp. Nó quyết định gọi thành phần nào và theo trình tự nào, nhưng không nên trở thành nơi chứa các quy tắc nghiệp vụ cốt lõi.

Một Application Service tốt thường có thể đọc như một kịch bản: tải Aggregate cần thiết, gọi hành vi miền, lưu thay đổi và trả kết quả. Gọn không có nghĩa là xóa hết các bước hoặc dồn mọi thứ vào một dòng gọi; rõ ràng cũng không có nghĩa tạo một lớp cho từng thao tác nhỏ. Mục tiêu là để trình tự use case hiện ra trực tiếp, trong khi mỗi quyết định nghiệp vụ vẫn nằm ở đúng nơi sở hữu nó.

## 1. Vai trò của Application Layer

Application Layer mô tả hệ thống làm gì để đáp ứng một yêu cầu. Nó đứng giữa các adapter đầu vào như REST Controller, giao diện dòng lệnh hoặc message consumer với mô hình miền và các cổng ra như Repository, Payment Gateway hay Notification Port.

Các trách nhiệm thường thuộc Application Layer:

- Tiếp nhận một yêu cầu đã được chuyển thành Command hoặc Query.
- Tải Aggregate hoặc dữ liệu cần thiết thông qua Repository/query port.
- Gọi hành vi của Entity, Aggregate Root, Value Object hoặc Domain Service.
- Điều phối thứ tự các bước trong use case.
- Quản lý ranh giới transaction phù hợp.
- Gọi các cổng tích hợp khi use case cần phối hợp với hệ thống ngoài.
- Thu thập kết quả, Domain Event hoặc thông tin phản hồi.
- Trả kết quả ở dạng phù hợp cho adapter gọi nó.

Application Layer không nên tự tính toán chính sách giá, tự quyết định một đơn hàng có được hủy hay không, hoặc tự sửa thuộc tính nội bộ của Aggregate. Những quyết định đó thuộc mô hình miền hoặc chính sách miền.

### 1.1. Use case là đơn vị tổ chức

Một use case mô tả một mục tiêu mà actor muốn đạt được thông qua hệ thống. Ví dụ:

- Đặt hàng.
- Xác nhận đơn hàng.
- Hủy đăng ký.
- Phê duyệt yêu cầu tín dụng.
- Chuyển tiền giữa hai tài khoản.
- Ghi nhận thanh toán.

Mỗi use case có thể được biểu diễn bằng một Application Service, command handler hoặc một phương thức có tên rõ. Không bắt buộc mỗi use case phải là một class riêng trong mọi dự án; điều quan trọng là ranh giới và trách nhiệm của nó dễ nhận biết.

### 1.2. Application Layer không phải nơi chứa toàn bộ logic

Một Application Service có thể điều phối nhiều bước mà vẫn gọn nếu mỗi bước gọi đúng thành phần chịu trách nhiệm. Nó trở nên quá nặng khi tự thực hiện những việc như:

- Tự kiểm tra và thay đổi trạng thái nội bộ của Aggregate.
- Tính toán chính sách nghiệp vụ thay vì gọi Domain Service.
- Lặp lại cùng quy tắc trong nhiều use case.
- Viết SQL hoặc phụ thuộc trực tiếp vào ORM.
- Tự gọi HTTP client cụ thể hoặc message broker.
- Chứa nhiều nhánh nghiệp vụ phức tạp mà mô hình miền đáng lẽ phải bảo vệ.

## 2. “Gọn” nghĩa là giữ đúng trách nhiệm

Một Application Service không cần ít dòng code bằng mọi giá. Nó cần ít trách nhiệm và có trình tự rõ ràng. Nếu một use case có năm bước nghiệp vụ, việc thể hiện năm bước đó trong phương thức có thể là thiết kế tốt.

| Công việc | Nơi phù hợp |
| --- | --- |
| Chuyển HTTP request thành command | Presentation |
| Tải Order theo OrderId | Application qua OrderRepository |
| Kiểm tra đơn có thể xác nhận không | Order Aggregate |
| Tính chính sách chiết khấu liên quan nhiều khái niệm | Domain Service hoặc Policy |
| Lưu Order | Application gọi Repository |
| Chuyển Aggregate thành bản ghi SQL/JPA | Infrastructure |
| Gửi message qua broker | Infrastructure qua dispatcher/adapter |
| Quyết định use case cần gọi các bước nào | Application |

### 2.1. Không lặp quy tắc miền trong Application

Ví dụ không nên:

~~~java
public void confirm(OrderId id) {
    Order order = orders.findById(id).orElseThrow();

    if (order.status() != OrderStatus.DRAFT) {
        throw new IllegalStateException("Invalid status");
    }
    if (order.lines().isEmpty()) {
        throw new IllegalStateException("Order is empty");
    }

    order.setStatus(OrderStatus.CONFIRMED);
    orders.save(order);
}
~~~

Đoạn code này khiến Application vừa điều phối vừa tự bảo vệ bất biến. Một use case khác có thể quên một trong hai điều kiện, hoặc cập nhật trạng thái theo cách khác.

Nên để Aggregate sở hữu quy tắc:

~~~java
public void confirm() {
    requireStatus(OrderStatus.DRAFT);
    if (lines.isEmpty()) {
        throw new IllegalStateException("An empty order cannot be confirmed");
    }
    status = OrderStatus.CONFIRMED;
}
~~~

Application chỉ cần gọi **order.confirm()**. Khi quy tắc thay đổi, nhóm sửa ở một nơi có trách nhiệm.

### 2.2. Không đẩy mọi dòng code ra khỏi Application

Application vẫn có thể:

- Kiểm tra dữ liệu đầu vào ở mức use case.
- Xác định actor và kiểm tra quyền thông qua một port phù hợp.
- Chọn một nhánh quy trình theo kết quả của bước trước.
- Chuyển đổi kết quả miền thành kết quả use case.
- Quyết định transaction boundary.

Đó là điều phối, không phải logic miền bị đặt sai chỗ. Một phương thức Application có vài câu if để quyết định bước tiếp theo của workflow là bình thường; vấn đề xuất hiện khi nó tự định nghĩa chính sách hoặc bất biến.

## 3. Trình tự use case nên đọc được trực tiếp

Một use case thường có trình tự dễ nhận biết:

1. Nhận Command hoặc Query.
2. Tải dữ liệu cần thiết.
3. Kiểm tra quyền hoặc điều kiện ở mức ứng dụng nếu có.
4. Gọi hành vi miền hoặc Domain Service.
5. Lưu thay đổi và ghi nhận sự kiện theo chiến lược nhất quán.
6. Trả kết quả.

~~~mermaid
sequenceDiagram
    actor User as Actor
    participant P as Presentation
    participant A as Application Service
    participant R as Repository
    participant D as Domain Model
    participant I as Infrastructure
    User->>P: Gửi yêu cầu
    P->>A: Command
    A->>R: Tải Aggregate
    R-->>A: Aggregate
    A->>D: Gọi hành vi nghiệp vụ
    D-->>A: Kết quả / Domain Event
    A->>R: Lưu Aggregate
    R->>I: Thực hiện persistence
    I-->>R: Kết quả lưu
    A-->>P: Use case result
    P-->>User: Response
~~~

Đây là luồng tổng quát. Không phải use case nào cũng cần tất cả bước; một query có thể chỉ đọc dữ liệu, còn một quy trình dài có thể cần nhiều lần tương tác với các Aggregate và hệ thống ngoài.

## 4. Ví dụ: xác nhận một đơn hàng

Giả sử use case xác nhận đơn hàng có yêu cầu:

- Tải đơn theo mã.
- Chỉ xác nhận đơn nháp.
- Đơn phải có ít nhất một dòng hàng.
- Lưu trạng thái mới.
- Trả mã đơn và trạng thái sau xử lý.

Hai điều kiện đầu về trạng thái và dòng hàng thuộc Order Aggregate. Application điều phối việc tải, gọi hành vi và lưu.

### 4.1. Command và kết quả

~~~java
public record ConfirmOrderCommand(OrderId orderId) {}

public record ConfirmOrderResult(
        OrderId orderId,
        OrderStatus status
) {}
~~~

Command biểu diễn yêu cầu của use case. Nó không nên chứa những trường chỉ phục vụ giao thức HTTP như header, cookie hoặc đối tượng request của framework.

### 4.2. Aggregate Root bảo vệ quy tắc

~~~java
import java.util.List;

public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines;
    private OrderStatus status;

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can be confirmed");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException("An empty order cannot be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    public OrderId id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }
}
~~~

Đây là đoạn minh họa rút gọn; constructor, kiểu OrderId, OrderLine và OrderStatus được giả định đã được định nghĩa. Quy tắc thực tế có thể cần kiểm tra thanh toán, giữ hàng hoặc quyền xác nhận, tùy chính sách đã thống nhất.

### 4.3. Application Service điều phối

~~~java
import java.util.Objects;

public final class ConfirmOrderService {
    private final OrderRepository orders;

    public ConfirmOrderService(OrderRepository orders) {
        this.orders = Objects.requireNonNull(orders);
    }

    public ConfirmOrderResult handle(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFound(command.orderId()));

        order.confirm();
        orders.save(order);

        return new ConfirmOrderResult(order.id(), order.status());
    }
}
~~~

Phương thức trên ngắn nhưng thể hiện đầy đủ trình tự: tải đơn, gọi hành vi, lưu và trả kết quả. Nó không cần một lớp riêng cho từng dòng như LoadOrderStep, ConfirmOrderStep và SaveOrderStep vì các bước này chưa có logic hoặc vòng đời độc lập.

### 4.4. Repository là cổng truy xuất

~~~java
import java.util.Optional;

public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Infrastructure triển khai interface bằng JPA, JDBC hoặc cơ chế lưu trữ khác. Application chỉ phụ thuộc vào hợp đồng, không biết cấu trúc bảng.

### 4.5. Presentation chỉ chuyển đổi giao thức

Một REST Controller có thể nhận request, chuyển thành ConfirmOrderCommand, gọi ConfirmOrderService và chuyển kết quả thành response. Controller không tự kiểm tra trạng thái đơn hoặc sửa Aggregate.

Việc phân chia này cho phép cùng use case được gọi từ REST API, message consumer hoặc một giao diện khác mà không phải sao chép quy tắc nghiệp vụ.

## 5. Giữ trình tự rõ khi use case có nhiều bước

Không phải use case nào cũng chỉ tải một Aggregate và gọi một phương thức. Application có thể điều phối nhiều bước, miễn là mỗi bước có mục đích rõ và trách nhiệm được đặt đúng nơi.

Ví dụ, áp dụng chiết khấu cho đơn:

1. Tải Order.
2. Lấy Customer liên quan.
3. Gọi DiscountCalculator để tính mức chiết khấu.
4. Gọi order.applyDiscount(discount) để Aggregate kiểm tra và áp dụng.
5. Lưu Order.
6. Trả kết quả.

~~~java
public final class ApplyDiscountService {
    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final DiscountCalculator discounts;

    public ApplyDiscountService(
            OrderRepository orders,
            CustomerRepository customers,
            DiscountCalculator discounts
    ) {
        this.orders = orders;
        this.customers = customers;
        this.discounts = discounts;
    }

    public ApplyDiscountResult handle(ApplyDiscountCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFound(command.orderId()));
        Customer customer = customers.findById(order.customerId())
                .orElseThrow(() -> new CustomerNotFound(order.customerId()));

        Money discount = discounts.calculate(customer.tier(), order.subtotal());
        order.applyDiscount(discount);
        orders.save(order);

        return new ApplyDiscountResult(order.id(), discount);
    }
}
~~~

Ví dụ giả định Order lưu CustomerId và các kiểu miền đã được định nghĩa. Application Service điều phối hai Aggregate và gọi Domain Service; DiscountCalculator giữ chính sách tính chiết khấu; Order bảo vệ bất biến khi áp dụng kết quả.

### 5.1. Dùng phương thức private khi nó đặt tên cho một bước có ý nghĩa

Nếu use case dài, có thể tách một số đoạn thành phương thức private:

~~~java
public ConfirmOrderResult handle(ConfirmOrderCommand command) {
    Order order = loadOrder(command.orderId());
    confirm(order);
    save(order);
    return resultOf(order);
}
~~~

Các phương thức private hữu ích khi:

- Tên của chúng làm rõ một khái niệm trong workflow.
- Một bước có nhiều dòng và cần được gom lại để người đọc thấy cấu trúc lớn.
- Một đoạn có thể được dùng lại trong cùng use case.
- Cần tách xử lý lỗi hoặc chuyển đổi kết quả có ý nghĩa riêng.

Không nên tách mỗi lời gọi một dòng thành một phương thức chỉ để phương thức chính trông ngắn. Nếu người đọc phải nhảy qua nhiều file để hiểu một luồng tuyến tính, độ rõ ràng có thể giảm.

### 5.2. Giữ nhánh điều phối ở Application

Một số nhánh thuộc trình tự use case chứ không phải bất biến của một Entity:

~~~java
if (reservation.accepted()) {
    paymentGateway.requestPayment(order.paymentRequest());
} else {
    order.reject(reservation.reason());
}
~~~

Application có thể quyết định bước tiếp theo dựa trên kết quả của một cổng hoặc một use case trước đó. Tuy nhiên, điều kiện như “đơn đã giao không thể hủy” vẫn phải được Aggregate bảo vệ, kể cả khi Application đã kiểm tra trước.

## 6. Phân biệt điều phối với quyết định nghiệp vụ

Một cách thực tế để giữ Application Service gọn là phân biệt hai câu hỏi:

- **Trình tự nào cần diễn ra?** Thường thuộc Application.
- **Hành động có hợp lệ theo nghiệp vụ không và kết quả miền là gì?** Thuộc Domain.

| Tình huống | Application | Domain |
| --- | --- | --- |
| Xác nhận đơn | Tải Order, gọi confirm(), lưu. | Kiểm tra trạng thái và bất biến của Order. |
| Chuyển tiền | Tải hai Account, gọi hành vi phù hợp, quản lý use case. | Bảo vệ số dư và quy tắc của từng Account; Domain Service đánh giá quy tắc liên tài khoản nếu cần. |
| Tính phí giao hàng | Tải dữ liệu cần thiết, gọi chính sách, lưu kết quả. | ShippingCostPolicy tính phí theo quy tắc miền. |
| Hủy đăng ký | Tải Subscription, gọi cancel(), điều phối thông báo. | Subscription quyết định điều kiện hủy thuộc vòng đời của nó. |
| Phê duyệt tín dụng | Tải hồ sơ, gọi CreditAssessment, lưu kết quả. | Chính sách tín dụng đánh giá điều kiện và giải thích quyết định. |

### 6.1. Application không cần biết mọi chi tiết bên trong Domain

Application cần biết hành vi nào để gọi và kết quả nào để quyết định bước tiếp theo. Nó không cần biết Aggregate cập nhật những trường nào, tính tổng ra sao hoặc kiểm tra từng bất biến bằng biểu thức gì.

### 6.2. Domain không nên biết trình tự giao diện

Order không cần biết người dùng bấm nút nào, endpoint nào gọi nó hoặc response HTTP nào sẽ được trả về. Domain chỉ cần diễn đạt hành vi và quy tắc của Order.

## 7. Command và Query trong Application Layer

Application Layer thường có hai loại use case:

- **Command:** yêu cầu thay đổi trạng thái hoặc tạo ra một kết quả nghiệp vụ.
- **Query:** yêu cầu đọc dữ liệu để hiển thị hoặc hỗ trợ quyết định.

Command thường tải Aggregate, gọi hành vi và lưu. Query có thể dùng query service hoặc read model để trả dữ liệu mà không cần tải Aggregate đầy đủ.

| Loại | Ví dụ | Cách xử lý thường gặp |
| --- | --- | --- |
| Command | ConfirmOrder, CancelOrder, ReserveInventory | Tải Aggregate, gọi hành vi, lưu thay đổi. |
| Query | GetOrderDetails, SearchOrders, GetMonthlyRevenue | Truy vấn dữ liệu hoặc projection, trả DTO/read model. |

Không nên tạo một Application Service khổng lồ vừa xử lý mọi command vừa phục vụ mọi màn hình. Tách use case theo mục tiêu giúp trách nhiệm và quyền truy cập dữ liệu rõ hơn.

### 7.1. Query không cần Repository Aggregate trong mọi trường hợp

Nếu màn hình chỉ cần mã đơn, tên khách, trạng thái và tổng tiền, query service có thể trả một projection trực tiếp. Không cần khôi phục hàng trăm Aggregate chỉ để hiển thị danh sách.

Điều này không làm mất vai trò Repository. Repository phục vụ nhu cầu tải/lưu Aggregate cho hành vi miền; query service phục vụ cách đọc tối ưu cho use case.

## 8. Transaction boundary thuộc use case

Application Layer thường xác định phạm vi transaction cho một use case. Transaction đảm bảo các thao tác lưu trữ cần thiết trong một đơn vị công việc được commit hoặc rollback theo cơ chế persistence.

Ví dụ, xác nhận đơn:

1. Bắt đầu transaction.
2. Tải Order.
3. Gọi order.confirm().
4. Lưu Order.
5. Commit.

Với Spring, có thể dùng annotation ở Application Service:

~~~java
@Transactional
public ConfirmOrderResult handle(ConfirmOrderCommand command) {
    // load, invoke domain behavior, save, return
}
~~~

Annotation là chi tiết framework; có thể dùng Transaction Manager hoặc Unit of Work khác. Không đưa annotation hoặc API transaction vào Entity chỉ để điều khiển persistence.

### 8.1. Không giữ transaction mở khi gọi hệ thống ngoài lâu

Nếu use case gọi cổng thanh toán hoặc đối tác qua mạng trong khi database transaction đang mở, transaction có thể bị kéo dài bởi độ trễ hoặc timeout bên ngoài. Điều này làm tăng khóa và cạnh tranh dữ liệu.

Với quy trình đơn giản, có thể chia bước lưu trạng thái chờ, gọi hệ thống ngoài và cập nhật kết quả. Với quy trình dài hoặc phân tán, dùng sự kiện, Outbox hoặc Saga/Process Manager phù hợp.

### 8.2. Domain Event được phát sau commit

Application có thể thu thập Domain Event từ Aggregate và phối hợp phát sau khi dữ liệu đã commit. Nếu cần tránh mất sự kiện giữa commit và publish, hãy dùng Transactional Outbox. Aggregate chỉ ghi nhận sự kiện; Application/Infrastructure quản lý lưu trữ và vận chuyển.

## 9. Điều phối nhiều Aggregate và quy trình dài

Một use case có thể liên quan đến nhiều Aggregate. Application có trách nhiệm điều phối, nhưng không có nghĩa tất cả phải nằm trong cùng một Aggregate hoặc một transaction lớn.

Ví dụ quy trình đặt hàng có giữ tồn kho và thanh toán:

1. Tạo Order ở trạng thái chờ giữ hàng.
2. Ghi nhận OrderPlaced.
3. Inventory nhận yêu cầu giữ hàng và quyết định chấp nhận hay từ chối.
4. Nếu giữ hàng thành công, quy trình yêu cầu thanh toán.
5. Nếu thanh toán thành công, Order chuyển sang trạng thái phù hợp.
6. Nếu một bước thất bại, quy trình thực hiện hành động bù trừ như giải phóng giữ hàng hoặc hoàn tiền theo chính sách.

~~~mermaid
sequenceDiagram
    participant A as PlaceOrder Use Case
    participant O as Order
    participant I as Inventory
    participant P as Payment
    A->>O: create pending order
    O-->>A: OrderPlaced
    A->>I: request reservation
    alt Inventory reserved
        I-->>A: InventoryReserved
        A->>P: request payment
        alt Payment accepted
            P-->>A: PaymentReceived
            A->>O: confirm()
        else Payment rejected
            P-->>A: PaymentRejected
            A->>I: release reservation
            A->>O: reject(reason)
        end
    else Inventory rejected
        I-->>A: ReservationRejected
        A->>O: reject(reason)
    end
~~~

Sơ đồ là ví dụ khái niệm. Khi các bước diễn ra bất đồng bộ và kéo dài, một Process Manager hoặc Saga có thể sở hữu trạng thái tiến trình và phản ứng với sự kiện. Không nên để một phương thức Application đồng bộ giữ toàn bộ luồng qua nhiều hệ thống nếu thời gian xử lý và lỗi mạng không thể kiểm soát trong một request.

### 9.1. Khi nào một use case nên trở thành Process Manager?

Cân nhắc Process Manager khi:

- Quy trình kéo dài qua nhiều message hoặc nhiều thời điểm.
- Có nhiều bước chờ phản hồi từ hệ thống khác.
- Cần lưu trạng thái tiến trình để tiếp tục sau khi process khởi động lại.
- Có timeout, retry và hành động bù trừ.
- Nhiều sự kiện khác nhau có thể đến theo thứ tự khác nhau.

Một use case ngắn với vài lời gọi tuần tự không cần Process Manager. Hãy dùng cấu trúc đơn giản nhất đáp ứng vòng đời thực tế của quy trình.

## 10. Xử lý lỗi và kết quả use case

Application Service cần chuyển các kết quả miền và lỗi kỹ thuật thành kết quả use case có thể hiểu được bởi adapter.

Một số nhóm kết quả:

- Không tìm thấy Aggregate.
- Hành động không hợp lệ theo trạng thái miền.
- Actor không có quyền thực hiện.
- Dữ liệu đầu vào không hợp lệ.
- Hệ thống ngoài từ chối hoặc không phản hồi.
- Xung đột cập nhật đồng thời.

Không nên bắt mọi exception rồi trả về một kết quả thành công chung. Cũng không nên để controller phải hiểu chi tiết exception persistence hoặc domain invariant. Application có thể dùng exception có ý nghĩa hoặc kiểu Result để phân biệt lỗi nghiệp vụ và lỗi kỹ thuật.

Ví dụ:

~~~java
public sealed interface ConfirmOrderOutcome {
    record Confirmed(OrderId orderId) implements ConfirmOrderOutcome {}
    record NotFound(OrderId orderId) implements ConfirmOrderOutcome {}
    record Rejected(String reasonCode) implements ConfirmOrderOutcome {}
}
~~~

Lựa chọn exception hay Result phụ thuộc quy ước codebase và cách adapter cần xử lý. Điều quan trọng là hợp đồng use case rõ ràng và không làm mất ý nghĩa của kết quả.

## 11. Idempotency và retry ở cấp use case

Một số command có thể được gửi lặp do client retry, message broker giao lại hoặc timeout khiến caller không biết thao tác trước đã thành công chưa.

Application Layer thường phối hợp cơ chế idempotency:

- Nhận một idempotency key hoặc command ID.
- Kiểm tra yêu cầu đã được xử lý chưa.
- Nếu đã xử lý, trả lại kết quả đã ghi nhận.
- Nếu chưa, thực hiện use case và lưu kết quả cùng dấu nhận diện theo transaction phù hợp.

Không nên đặt cơ chế này vào Entity nếu nó là chi tiết của giao thức gọi hoặc xử lý message. Tuy nhiên, Domain vẫn phải bảo vệ bất biến để một lệnh lặp không tạo trạng thái sai.

Với message consumer, handler cũng cần xử lý duplicate event an toàn. Outbox và at-least-once delivery không tự bảo đảm consumer chỉ chạy một lần.

## 12. Cách giữ Application Service dễ đọc

Một số nguyên tắc thực tế:

### 12.1. Một public entry point cho một mục tiêu use case

Tên phương thức nên diễn đạt hành động như confirm(), cancel() hoặc place(). Tránh một phương thức execute(String action, Map data) xử lý nhiều mục tiêu không liên quan.

### 12.2. Đặt tên bước theo nghiệp vụ

Tên như loadOrder(), calculateDiscount() hoặc requestReservation() cho biết ý nghĩa của bước. Tránh tên quá kỹ thuật như doStep1(), processData() hoặc handleEverything().

### 12.3. Giữ luồng chính ở gần đầu phương thức

Người đọc nên nhìn thấy các bước quan trọng trước. Chi tiết ít quan trọng như chuyển đổi mã lỗi có thể đặt trong helper có tên rõ hoặc adapter.

### 12.4. Tránh abstraction một lần không có ý nghĩa

Không tạo interface cho mọi collaborator hoặc class riêng cho từng dòng code. Một abstraction hữu ích khi nó biểu diễn một ranh giới, hợp đồng, chính sách hoặc khả năng thay thế thực sự.

### 12.5. Không tạo lớp BaseService tổng quát quá sớm

Một BaseService với nhiều hook, callback và generic type có thể che giấu trình tự use case. Các use case có thể chia sẻ một vài helper, nhưng không nên ép chúng vào một pipeline chung nếu luồng nghiệp vụ khác nhau.

### 12.6. Dùng Command và Result khi hợp đồng đủ phức tạp

Nếu use case có nhiều tham số hoặc kết quả, Command/Result object giúp hợp đồng rõ và dễ mở rộng. Với một thao tác rất đơn giản, một tham số có kiểu có thể đủ; không cần tạo object chỉ để tuân theo một quy ước máy móc.

### 12.7. Dùng dependency injection ở ranh giới

Repository, Domain Service và các port được truyền vào qua constructor. Không để Application Service tự khởi tạo JPA repository, HTTP client hoặc message producer cụ thể.

## 13. Kiểm thử Application Service

Application Service nên được kiểm thử để xác nhận use case điều phối đúng các bước và trả kết quả phù hợp. Domain được kiểm thử riêng cho các bất biến và quy tắc của nó.

Có thể dùng fake Repository và fake port trong unit test:

~~~java
class ConfirmOrderServiceTest {
    @Test
    void confirmsAndSavesTheRequestedOrder() {
        InMemoryOrderRepository repository = new InMemoryOrderRepository();
        Order order = Order.draft(new OrderId("ORD-1"));
        order.addLine(new OrderLine(new ProductId("SKU-1"), 1));
        repository.save(order);

        ConfirmOrderService service = new ConfirmOrderService(repository);
        ConfirmOrderResult result =
                service.handle(new ConfirmOrderCommand(order.id()));

        assertEquals(OrderStatus.CONFIRMED, result.status());
        assertEquals(OrderStatus.CONFIRMED,
                repository.findById(order.id()).orElseThrow().status());
    }

    @Test
    void reportsNotFoundWhenOrderDoesNotExist() {
        InMemoryOrderRepository repository = new InMemoryOrderRepository();
        ConfirmOrderService service = new ConfirmOrderService(repository);

        assertThrows(
                OrderNotFound.class,
                () -> service.handle(
                        new ConfirmOrderCommand(new OrderId("MISSING"))
                )
        );
    }
}
~~~

Các kiểu Order, OrderId, OrderLine, OrderStatus, InMemoryOrderRepository và OrderNotFound được giả định đã có. Ví dụ minh họa kiểm tra kết quả use case và việc lưu trạng thái. Domain test riêng cần kiểm tra đơn rỗng không thể xác nhận và trạng thái không đổi khi hành vi bị từ chối.

### 13.1. Kiểm thử hành vi quan sát được

Ưu tiên kiểm tra:

- Kết quả use case khi thành công.
- Kết quả khi Aggregate không tồn tại.
- Hành vi miền được gọi với dữ liệu đúng thông qua kết quả có thể quan sát.
- Thay đổi được lưu hoặc không lưu theo kết quả.
- Cổng ngoài được gọi khi use case yêu cầu và không gọi khi điều kiện trước đó thất bại.
- Transaction và event flow ở mức integration test khi cần.

Không nên kiểm tra quá chi tiết số lần gọi mọi helper private hoặc thứ tự những lời gọi không có ý nghĩa nghiệp vụ. Kiểm thử cần bảo vệ hành vi, không đóng băng cấu trúc nội bộ.

## 14. Những sai lầm thường gặp

### 14.1. Application Service trở thành Transaction Script chứa mọi quy tắc

Một service dài tự kiểm tra mọi trạng thái, tính tiền, sửa thuộc tính và gọi database trực tiếp làm mô hình miền trở nên thụ động. Hãy chuyển quy tắc về Aggregate, Value Object hoặc Domain Service.

### 14.2. Application Service chỉ chuyển tiếp một lời gọi vô nghĩa

Một lớp chỉ gọi repository rồi gọi một setter mà không có ranh giới use case hoặc trách nhiệm điều phối có thể không cần tồn tại. Hãy cân nhắc liệu nó có tạo ra một entry point hữu ích hay chỉ tăng lớp trung gian.

### 14.3. Tách từng dòng thành một class

Tạo LoadOrderStep, ValidateOrderStep, ConfirmOrderStep, SaveOrderStep và ResultBuilder chỉ để xử lý một luồng tuyến tính nhỏ khiến người đọc phải di chuyển giữa nhiều file. Hãy giữ các bước đơn giản trong một use case.

### 14.4. Gộp nhiều use case vào một service khổng lồ

Một OrderService chứa place, confirm, cancel, refund, ship, return và report có thể tập hợp các lý do thay đổi không liên quan. Tổ chức theo mục tiêu use case hoặc nhóm hành vi có liên hệ.

### 14.5. Lặp lại quy tắc miền trong nhiều use case

Nếu confirm và adminConfirm đều tự kiểm tra trạng thái, các quy tắc có thể lệch nhau. Hãy để Aggregate bảo vệ bất biến chung; Application chỉ điều phối điểm khác nhau của từng use case.

### 14.6. Đưa chi tiết HTTP vào Command

Command không nên chứa HttpServletRequest, header hoặc response object. Adapter chuyển đổi giao thức thành dữ liệu use case có ý nghĩa.

### 14.7. Để Application phụ thuộc trực tiếp vào hạ tầng cụ thể

Nếu use case tự tạo RestTemplate, KafkaTemplate hoặc EntityManager, nó khó kiểm thử và thay thế. Dùng port/interface và implementation ở Infrastructure.

### 14.8. Giữ transaction mở trong suốt quy trình mạng dài

Gọi nhiều dịch vụ ngoài trong một transaction database kéo dài có thể gây khóa và timeout. Tách quy trình thành bước, trạng thái chờ và sự kiện khi phù hợp.

### 14.9. Dùng một framework pipeline cho mọi use case

Một pipeline chung có thể hữu ích cho cross-cutting concern như logging hoặc authorization, nhưng không nên che khuất các bước nghiệp vụ khác nhau. Hãy giữ workflow đặc thù có thể đọc được.

## 15. Quy trình thiết kế một Application Service

Khi xây dựng một use case, có thể làm theo các bước:

1. **Viết mục tiêu use case:** actor muốn đạt kết quả gì?
2. **Xác định đầu vào và kết quả:** command/query cần những dữ liệu nào, trả kết quả gì?
3. **Vẽ trình tự nghiệp vụ:** tải gì, gọi hành vi nào, cần cổng nào và lưu ở đâu?
4. **Gán quyền sở hữu quy tắc:** bất biến thuộc Aggregate nào, chính sách thuộc Domain Service nào?
5. **Xác định transaction boundary:** thay đổi nào cần commit cùng nhau?
6. **Viết luồng chính tuyến tính:** để người đọc nhìn thấy thứ tự điều phối trong một phương thức.
7. **Tách helper có ý nghĩa:** chỉ tách khi tên giúp diễn đạt một bước hoặc gom chi tiết đáng kể.
8. **Xử lý lỗi và nhánh thay thế:** làm rõ not found, rejected, timeout, retry và compensation.
9. **Kiểm thử use case:** kiểm tra kết quả và các tương tác quan trọng, đồng thời kiểm thử Domain riêng.
10. **Đánh giá lại khi quy trình kéo dài:** cân nhắc Process Manager/Saga nếu cần lưu trạng thái qua nhiều message hoặc thời điểm.

~~~mermaid
flowchart TD
    A[Xác định mục tiêu use case] --> B[Thiết kế Command/Query và Result]
    B --> C[Vẽ trình tự các bước]
    C --> D[Đặt quy tắc vào Domain]
    D --> E[Xác định Repository và port]
    E --> F[Chọn transaction boundary]
    F --> G[Viết Application Service theo luồng chính]
    G --> H[Kiểm thử use case và Domain]
    H --> I{Quy trình dài hoặc bất đồng bộ?}
    I -->|Không| J[Giữ use case trực tiếp]
    I -->|Có| K[Đánh giá Process Manager/Saga]
~~~

## 16. Checklist giữ lớp ứng dụng gọn và rõ

- [ ] Mỗi entry point có mục tiêu use case dễ gọi tên.
- [ ] Trình tự tải dữ liệu, gọi hành vi và lưu được thể hiện rõ.
- [ ] Application điều phối, không tự bảo vệ bất biến của Aggregate.
- [ ] Quy tắc miền nằm trong Entity, Value Object, Aggregate hoặc Domain Service phù hợp.
- [ ] Repository và hệ thống ngoài được truy cập qua abstraction.
- [ ] Presentation chỉ chuyển đổi giao thức và gọi use case.
- [ ] Command/Query và Result có hợp đồng rõ ràng.
- [ ] Transaction boundary phù hợp với phạm vi thay đổi.
- [ ] Không giữ transaction mở không cần thiết khi gọi dịch vụ ngoài.
- [ ] Domain Event được phát theo chiến lược sau commit/Outbox phù hợp.
- [ ] Quy trình nhiều bước dài có cơ chế lưu trạng thái và phục hồi phù hợp.
- [ ] Helper và abstraction chỉ được tạo khi chúng làm rõ trách nhiệm.
- [ ] Kiểm thử tập trung vào kết quả use case và tương tác có ý nghĩa.

## 17. Kết luận

Application Layer trong DDD cần thể hiện rõ hệ thống thực hiện một use case theo trình tự nào. Một Application Service gọn thường tải Aggregate, gọi hành vi miền, phối hợp các port cần thiết, lưu thay đổi và trả kết quả. Nó không cần chứa lại các quy tắc mà Aggregate hoặc Domain Service đã sở hữu, cũng không cần tạo thêm lớp cho từng dòng thao tác đơn giản.

Khi use case có nhiều bước, hãy giữ luồng chính dễ đọc và dùng tên bước có ý nghĩa. Với quy trình dài hoặc phân tán, chuyển sang Process Manager hoặc Saga khi cần lưu trạng thái, retry và bù trừ. Thiết kế tốt không được đo bằng số dòng code hay số lớp, mà bằng việc người đọc có thể hiểu trình tự điều phối, tìm đúng nơi chứa quy tắc và thay đổi một bước mà không làm rối các trách nhiệm khác.
