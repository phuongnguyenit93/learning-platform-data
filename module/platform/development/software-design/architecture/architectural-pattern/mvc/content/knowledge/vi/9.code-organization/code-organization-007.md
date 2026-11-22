# Tái sử dụng thành phần mà không tạo phụ thuộc vòng

Trong module **MODEL_VIEW_CONTROLLER**, ứng dụng được tổ chức để Model quản lý trạng thái và quy tắc nghiệp vụ, View trình bày thông tin, còn Controller tiếp nhận tương tác và điều phối xử lý. Khi nhiều chức năng cần dùng chung một khả năng, ta thường tách khả năng đó thành thành phần có thể tái sử dụng. Tuy nhiên, nếu các thành phần gọi ngược và phụ thuộc lẫn nhau, mã nguồn dễ hình thành **phụ thuộc vòng** (circular dependency).

Phụ thuộc vòng làm ranh giới trách nhiệm khó hiểu, gây khó khăn khi kiểm thử và có thể khiến ứng dụng không khởi tạo được khi dùng dependency injection. Muốn tái sử dụng tốt, cần xác định ai sở hữu một khả năng, thành phần nào cần nó và hợp đồng nào cho phép trao đổi mà không buộc hai bên phụ thuộc trực tiếp vào nhau.

## 1. Phụ thuộc giữa các thành phần là gì?

Một thành phần phụ thuộc vào thành phần khác khi nó cần biết hoặc sử dụng kiểu dữ liệu, giao diện hay hành vi do thành phần kia cung cấp. Trong Java, một lớp có thể phụ thuộc vào lớp khác qua:

- Khai báo field hoặc constructor parameter có kiểu của lớp kia.
- Gọi phương thức hoặc tạo đối tượng của lớp kia.
- Kế thừa lớp hoặc triển khai interface do lớp kia định nghĩa.
- Sử dụng kiểu dữ liệu, annotation hoặc API được công bố từ package/module khác.

Ví dụ, **OrderController** nhận **OrderService** qua constructor:

~~~java
public final class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

Controller phụ thuộc vào dịch vụ xử lý đơn hàng vì nó cần gọi khả năng đó. Đây là một hướng phụ thuộc rõ ràng. Phụ thuộc không tự động là xấu; ứng dụng cần các thành phần phối hợp. Vấn đề xuất hiện khi hướng phụ thuộc tạo thành chu trình hoặc khi một thành phần biết quá nhiều về nội bộ của thành phần khác.

## 2. Phụ thuộc vòng hình thành như thế nào?

Phụ thuộc vòng xảy ra khi ta có thể đi theo các quan hệ phụ thuộc từ một thành phần và quay lại chính thành phần đó. Ví dụ, A phụ thuộc B, B phụ thuộc C và C lại phụ thuộc A.

~~~mermaid
flowchart LR
    A[OrderService] --> B[NotificationService]
    B --> C[CustomerService]
    C --> A
~~~

Một trường hợp thường gặp là hai dịch vụ gọi trực tiếp lẫn nhau:

~~~java
public final class OrderService {
    private final OrderRepository orders;
    private final NotificationService notifications;

    public OrderService(
            OrderRepository orders,
            NotificationService notifications) {
        this.orders = orders;
        this.notifications = notifications;
    }

    public void placeOrder(Order order) {
        // Lưu đơn hàng
        orders.save(order);
        notifications.sendOrderPlaced(order.id());
    }

    public Order findById(OrderId id) {
        return orders.findById(id).orElseThrow();
    }
}

public final class NotificationService {
    private final OrderService orders;

    public NotificationService(OrderService orders) {
        this.orders = orders;
    }

    public void sendOrderPlaced(OrderId id) {
        Order order = orders.findById(id);
        // Gửi thông báo
    }
}
~~~

Ở ví dụ này, **OrderService** cần **NotificationService** để gửi thông báo; **NotificationService** lại cần **OrderService** để lấy đơn hàng. Hai lớp tạo thành chu trình phụ thuộc. Với constructor injection, container không thể tạo một đối tượng trước vì mỗi đối tượng đều cần đối tượng còn lại đã được tạo.

Không phải mọi lời gọi qua lại trong lúc chạy đều là phụ thuộc vòng ở mức mã nguồn. Một callback hoặc luồng xử lý có thể quay lại thành phần trước đó mà không tạo chu trình trong đồ thị phụ thuộc tĩnh. Khi phân tích kiến trúc, cần xem các quan hệ kiểu, module và cấu hình tạo đối tượng, đồng thời phân biệt chúng với thứ tự gọi trong một request.

## 3. Vì sao phụ thuộc vòng gây khó khăn?

| Hệ quả | Biểu hiện trong dự án |
| --- | --- |
| Khó hiểu trách nhiệm | Không rõ thành phần nào sở hữu quy tắc và thành phần nào chỉ đang hỗ trợ |
| Khó kiểm thử độc lập | Muốn kiểm thử A phải tạo B, nhưng B lại cần A hoặc cần nhiều thành phần liên quan |
| Khởi tạo phức tạp | Dependency injection báo circular reference hoặc cần cơ chế trì hoãn để né chu trình |
| Khó tái sử dụng | Thành phần chỉ dùng được khi mang theo cả nhóm phụ thuộc liên kết |
| Khó thay đổi | Một thay đổi nhỏ ở A có thể kéo theo B và C |
| Ranh giới module yếu | Các package hoặc module không thể được biên dịch, triển khai hay quản lý độc lập như dự kiến |

Một số framework có cách xử lý tham chiếu trì hoãn hoặc proxy để ứng dụng vẫn khởi động. Cách đó có thể hữu ích trong một số tình huống, nhưng nó không tự giải quyết nguyên nhân kiến trúc. Nếu hai thành phần thực sự cần biết lẫn nhau, trách nhiệm hoặc hợp đồng giữa chúng vẫn cần được xem xét.

## 4. Hướng phụ thuộc nên được tổ chức ra sao?

Một cách hữu ích là biểu diễn các thành phần như đồ thị có hướng. Mỗi mũi tên A → B có nghĩa là A phụ thuộc vào B. Với các module cần được xây dựng và kiểm thử độc lập, ta thường muốn đồ thị phụ thuộc không có chu trình (DAG).

Ví dụ một cách chia lớp cho ứng dụng web MVC:

~~~mermaid
flowchart TD
    W[Web: Controller và binding] --> A[Application: use case]
    A --> D[Domain: Model và quy tắc nghiệp vụ]
    I[Infrastructure: database và dịch vụ ngoài] --> A
    C[Composition root: cấu hình ứng dụng] --> W
    C --> A
    C --> I
~~~

Sơ đồ minh họa một hướng tổ chức thường dùng:

- **Web** nhận HTTP request, binding dữ liệu và chọn response. Nó gọi use case ở tầng ứng dụng.
- **Application** điều phối hành động của người dùng, sử dụng các quy tắc và kiểu miền cần thiết.
- **Domain** chứa khái niệm và quy tắc nghiệp vụ cốt lõi, không cần biết Controller hoặc template.
- **Infrastructure** cung cấp triển khai cụ thể cho các cổng truy cập dữ liệu hoặc dịch vụ bên ngoài được khai báo ở ranh giới phù hợp.
- **Composition root** là nơi lắp ráp các triển khai cụ thể với các hợp đồng mà thành phần cần.

Mũi tên từ Infrastructure về Application trong sơ đồ có nghĩa adapter hạ tầng triển khai hoặc sử dụng hợp đồng do tầng ứng dụng công bố. Khi tổ chức module theo quy tắc dependency inversion, mã nghiệp vụ không cần import lớp triển khai JPA hoặc email client.

Đây là một cách tổ chức tham khảo, không phải yêu cầu mọi dự án MVC phải có đúng năm module. Ứng dụng nhỏ có thể dùng ít package hơn; điều quan trọng là giữ được hướng phụ thuộc dễ giải thích và tránh để tầng nghiệp vụ phụ thuộc ngược vào chi tiết giao diện hoặc hạ tầng.

## 5. Cách 1: Tách hợp đồng mà bên sử dụng cần

Khi một dịch vụ cần gửi thông báo, nó chỉ cần biết khả năng gửi thông báo, không cần biết lớp email cụ thể hoặc dịch vụ thông báo có thể gọi lại OrderService.

Ta định nghĩa một cổng (port) mô tả nhu cầu:

~~~java
public interface OrderNotification {
    void sendOrderPlaced(OrderPlacedMessage message);
}

public record OrderPlacedMessage(
        OrderId orderId,
        String customerEmail,
        String customerName,
        String orderNumber
) {}
~~~

Use case phụ thuộc vào hợp đồng đó:

~~~java
public final class PlaceOrderService {
    private final OrderRepository orders;
    private final OrderNotification notification;

    public PlaceOrderService(
            OrderRepository orders,
            OrderNotification notification) {
        this.orders = orders;
        this.notification = notification;
    }

    public OrderId execute(PlaceOrderCommand command) {
        Order order = Order.place(command);
        orders.save(order);

        notification.sendOrderPlaced(
                new OrderPlacedMessage(
                        order.id(),
                        order.customerEmail(),
                        order.customerName(),
                        order.number()
                )
        );
        return order.id();
    }
}
~~~

Triển khai cụ thể có thể dùng email client:

~~~java
public final class EmailOrderNotification implements OrderNotification {
    private final EmailClient emailClient;

    public EmailOrderNotification(EmailClient emailClient) {
        this.emailClient = emailClient;
    }

    @Override
    public void sendOrderPlaced(OrderPlacedMessage message) {
        emailClient.send(
                message.customerEmail(),
                "Đơn hàng " + message.orderNumber() + " đã được tạo"
        );
    }
}
~~~

Lúc này, **PlaceOrderService** phụ thuộc vào **OrderNotification**. **EmailOrderNotification** triển khai hợp đồng và phụ thuộc vào **EmailClient**. Thành phần gửi email không cần gọi ngược về PlaceOrderService vì thông tin cần thiết đã được chuyển qua **OrderPlacedMessage**.

Hợp đồng nên được đặt tại nơi sở hữu nhu cầu. Nếu use case đặt hàng cần khả năng gửi thông báo, application có thể định nghĩa port đó; adapter email nằm ở infrastructure. Như vậy, hướng phụ thuộc mã nguồn đi từ adapter đến hợp đồng, trong khi lúc chạy use case vẫn gọi đối tượng adapter đã được tiêm vào.

## 6. Cách 2: Chuyển trách nhiệm điều phối lên use case

Đôi khi chu trình xuất hiện vì hai dịch vụ đang điều phối lẫn nhau. Hãy xem xét có một hành động cấp cao hơn đang cần phối hợp cả hai hay không. Nếu có, tạo use case hoặc orchestrator sở hữu trình tự công việc.

Ví dụ, **OrderService** vừa tạo đơn vừa gọi **CustomerService** để gửi email; **CustomerService** lại gọi **OrderService** để lấy thông tin đơn. Có thể tách thành:

- **PlaceOrderUseCase:** điều phối việc tạo đơn và yêu cầu gửi thông báo.
- **OrderRepository:** cung cấp khả năng lưu hoặc truy vấn đơn hàng.
- **NotificationPort:** cung cấp khả năng gửi thông báo.
- **EmailNotificationAdapter:** triển khai NotificationPort bằng email client.

Use case nhận dữ liệu cần thiết từ quá trình tạo đơn và gửi nó qua port. Dịch vụ gửi thông báo không cần truy vấn ngược dịch vụ đặt hàng.

Không nên tạo một **Manager** hoặc **Coordinator** chung chung chỉ để chuyển lời gọi giữa các lớp. Tên và trách nhiệm của orchestrator cần thể hiện một use case cụ thể, ví dụ **PlaceOrderService** hoặc **CancelBookingUseCase**.

## 7. Cách 3: Dùng sự kiện khi các chức năng cần biết một việc đã xảy ra

Nếu một hành động có thể kích hoạt nhiều chức năng độc lập, sự kiện nghiệp vụ hoặc application event có thể giảm phụ thuộc trực tiếp. Ví dụ, khi đơn hàng được tạo, các bên quan tâm có thể cập nhật báo cáo, gửi email hoặc phát thông báo.

~~~mermaid
flowchart TD
    A[PlaceOrderUseCase] --> B[Phát OrderPlaced]
    B --> C[Email listener]
    B --> D[Analytics listener]
    B --> E[Customer notification listener]
~~~

Sự kiện **OrderPlaced** diễn tả một điều đã xảy ra. Các listener đăng ký quan tâm đến sự kiện và thực hiện công việc riêng. Use case phát sự kiện không cần biết tất cả listener cụ thể.

~~~java
public record OrderPlaced(
        OrderId orderId,
        String orderNumber,
        String customerEmail
) {}

public final class OrderEventHandler {
    private final EmailClient emailClient;

    public OrderEventHandler(EmailClient emailClient) {
        this.emailClient = emailClient;
    }

    public void on(OrderPlaced event) {
        emailClient.send(
                event.customerEmail(),
                "Đơn hàng " + event.orderNumber() + " đã được tạo"
        );
    }
}
~~~

Ví dụ chỉ minh họa cấu trúc sự kiện; framework có thể dùng event publisher và listener để kết nối chúng. Với sự kiện đồng bộ trong cùng tiến trình, listener có thể chạy ngay trong luồng xử lý request. Với sự kiện bất đồng bộ hoặc message broker, cần xác định rõ độ tin cậy, retry, thứ tự, xử lý trùng lặp và tính nhất quán dữ liệu. Không nên dùng event chỉ để thay mọi lời gọi phương thức trực tiếp.

Sự kiện cũng không tự động loại bỏ mọi chu trình. Nếu listener gọi ngược use case đã phát sự kiện và phát lại cùng sự kiện, hệ thống có thể tạo vòng lặp xử lý ở runtime. Hợp đồng sự kiện và trách nhiệm của listener vẫn phải được thiết kế rõ.

## 8. Cách 4: Tách mã dùng chung thành module có trách nhiệm rõ

Khi nhiều chức năng cần dùng cùng một kiểu hoặc quy tắc nhỏ, có thể đưa nó vào module dùng chung. Tuy nhiên, package **common** hoặc **shared** không nên trở thành nơi gom mọi thứ.

Một module dùng chung phù hợp thường có các đặc điểm:

- Có khái niệm hoặc tiện ích thực sự được nhiều thành phần sử dụng.
- Có API nhỏ, ổn định và không phụ thuộc ngược vào các module tính năng.
- Không chứa quy tắc chỉ thuộc một chức năng cụ thể.
- Có chủ sở hữu và mục đích đủ rõ để quyết định thay đổi.

Ví dụ, kiểu **Money** có thể là một khái niệm miền được dùng bởi đơn hàng, thanh toán và hoàn tiền. Nhưng một hàm **calculateOrderDiscountForCampaignX** chỉ thuộc một quy tắc khuyến mãi cụ thể; đưa nó vào **common** sẽ làm module chung phụ thuộc vào một tính năng.

Nếu một module shared import các lớp của Order, Customer và Payment, trong khi cả ba module cũng import shared, shared không còn là tầng nền ổn định. Hãy tìm khái niệm thực sự chung, hoặc đặt hợp đồng ở module sở hữu nhu cầu thay vì gom tất cả vào một package tiện dụng.

## 9. Tái sử dụng trong ứng dụng MVC

Trong MVC, không nên để Controller của chức năng này gọi trực tiếp Controller của chức năng khác để tái sử dụng nghiệp vụ. Controller là adapter của giao thức HTTP; gọi Controller khác dễ kéo theo request context, response type và quy tắc web không cần thiết.

Ví dụ, trang chi tiết đơn hàng cần thông tin khách hàng. Một cách tổ chức dễ bảo trì là:

- **OrderController** gọi **OrderDetailQuery** để lấy dữ liệu cho trang.
- **OrderDetailQuery** gọi các hợp đồng truy vấn phù hợp và tạo **OrderDetailViewModel**.
- **CustomerQuery** hoặc một cổng truy vấn cung cấp thông tin khách hàng mà use case được phép xem.
- View chỉ nhận view model đã được chuẩn bị.

Không cần gọi **CustomerController** từ **OrderController**. Nếu nhiều màn hình cần cùng một khả năng truy vấn khách hàng, hãy tái sử dụng query service hoặc hợp đồng ứng dụng phù hợp.

Tương tự, các Controller có thể dùng chung validation hoặc mapper nếu thành phần đó có trách nhiệm ổn định. Nhưng validation nghiệp vụ phải được thực thi tại use case hoặc Model để các đường gọi khác như API, tác vụ nền cũng tuân thủ quy tắc.

## 10. Dependency injection có giải quyết phụ thuộc vòng không?

Dependency injection giúp một thành phần nhận phụ thuộc từ bên ngoài, thường qua constructor. Nó làm rõ những gì lớp cần và cho phép thay triển khai trong kiểm thử. Tuy nhiên, DI không tự phá vỡ chu trình.

Nếu A cần B trong constructor và B cũng cần A trong constructor, container vẫn phải đối mặt với chu trình tạo đối tượng. Một số framework có thể hỗ trợ proxy, lazy provider hoặc tham chiếu trì hoãn, nhưng đó là cơ chế xử lý khởi tạo; nó không chứng minh ranh giới trách nhiệm đã hợp lý.

Constructor injection thường giúp phát hiện vấn đề sớm:

~~~java
public final class AService {
    public AService(BService b) {}
}

public final class BService {
    public BService(AService a) {}
}
~~~

Hai constructor cho thấy chu trình trực tiếp ngay trong khai báo. Khi gặp trường hợp này, hãy xem lại hợp đồng, trách nhiệm và hướng phụ thuộc trước khi dùng lazy injection để né lỗi khởi tạo.

## 11. Cách phát hiện và ngăn phụ thuộc vòng

Có thể kết hợp nhiều cách kiểm tra:

- **Đọc constructor và import:** tìm các cặp lớp hoặc package tham chiếu qua lại.
- **Vẽ đồ thị phụ thuộc:** ghi mỗi module thành một nút và mỗi quan hệ phụ thuộc thành một mũi tên; tìm chu trình.
- **Dùng công cụ kiểm tra kiến trúc:** ArchUnit có thể kiểm tra quy tắc package, chẳng hạn application không được phụ thuộc vào web.
- **Kiểm tra module build:** với dự án chia thành Gradle hoặc Maven module, xác nhận dependency graph không có vòng khiến các module không thể build độc lập.
- **Kiểm tra khởi tạo ứng dụng:** container DI có thể báo lỗi circular reference khi tạo bean.

Ví dụ một quy tắc ArchUnit minh họa:

~~~java
@AnalyzeClasses(packages = "com.example")
class ArchitectureTest {
    @ArchTest
    static final ArchRule domainDoesNotDependOnWeb =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..web..");
}
~~~

Quy tắc trên ngăn package domain phụ thuộc vào web. Dự án cần điều chỉnh package pattern theo cấu trúc thật và có thể bổ sung các quy tắc khác như web chỉ phụ thuộc application, infrastructure không bị application import trực tiếp.

## 12. Quy trình xử lý khi phát hiện một chu trình

Khi phát hiện A → B → C → A, đừng vội di chuyển lớp theo tên package. Hãy lần theo lý do mỗi cạnh tồn tại:

1. Xác định chức năng nào đang được tái sử dụng và ai thực sự sở hữu quy tắc đó.
2. Xác định dữ liệu hoặc khả năng tối thiểu mà bên gọi cần.
3. Tách hợp đồng tại ranh giới phù hợp, để bên sử dụng phụ thuộc vào hợp đồng.
4. Chuyển triển khai cụ thể sang module phù hợp và để composition root lắp ráp các thành phần.
5. Nếu các chức năng chỉ cần biết một việc đã xảy ra, cân nhắc event với semantics rõ ràng.
6. Nếu có một trình tự nghiệp vụ phối hợp nhiều thành phần, đặt trình tự đó trong một use case có tên cụ thể.
7. Kiểm tra lại đồ thị phụ thuộc và chạy các kiểm thử liên quan.

Không phải mọi chu trình đều có cùng cách sửa. Nếu hai lớp thực sự thuộc cùng một khái niệm và luôn thay đổi cùng nhau, có thể chúng đang bị tách quá nhỏ; hợp nhất chúng thành một thành phần có trách nhiệm rõ ràng có thể hợp lý hơn. Nếu chu trình xuất hiện giữa các module độc lập, cần tách hợp đồng hoặc chuyển quyền sở hữu để giữ ranh giới.

## Kết luận

Tái sử dụng thành phần hiệu quả đòi hỏi hợp đồng rõ và hướng phụ thuộc có chủ đích. Trong MVC, Controller nên gọi use case hoặc dịch vụ dùng chung thay vì gọi Controller khác; tầng nghiệp vụ nên phụ thuộc vào khả năng cần thiết qua hợp đồng; hạ tầng cung cấp triển khai cụ thể ở ranh giới. Khi đồ thị phụ thuộc không có chu trình, các thành phần dễ kiểm thử, thay thế và phát triển độc lập hơn.
