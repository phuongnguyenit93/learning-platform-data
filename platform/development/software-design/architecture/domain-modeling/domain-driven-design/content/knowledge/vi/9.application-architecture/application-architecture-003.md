# Kiến trúc lục giác: cổng, bộ chuyển đổi và ranh giới với hệ thống bên ngoài

Một mô hình miền có thể được thiết kế rất rõ ràng nhưng vẫn nhanh chóng trở nên phụ thuộc vào framework web, cơ sở dữ liệu, message broker hoặc dịch vụ của nhà cung cấp nếu các công nghệ đó đi thẳng vào phần lõi. Khi giao diện thay đổi, nhóm phải sửa logic nghiệp vụ; khi đổi database, các quy tắc miền bị ảnh hưởng; khi kiểm thử, nhóm phải khởi động nhiều hệ thống bên ngoài chỉ để gọi một hành vi đơn giản.

**Kiến trúc lục giác (Hexagonal Architecture)**, còn được gọi là **Ports and Adapters (Cổng và Bộ chuyển đổi)**, là cách tổ chức ứng dụng để phần lõi giữ được tính độc lập trước các tác nhân và công nghệ bên ngoài. Phần lõi định nghĩa những cổng thể hiện cách nó nhận yêu cầu và những khả năng nó cần từ bên ngoài. Các bộ chuyển đổi ở ranh giới triển khai những cổng đó bằng giao thức và công nghệ cụ thể.

Trong Domain-Driven Design (DDD), cách tổ chức này hỗ trợ bảo vệ domain model và ngôn ngữ của bounded context. Nó giúp nhóm thay đổi cách giao tiếp, lưu trữ hoặc tích hợp mà không phải viết lại các quy tắc nghiệp vụ cốt lõi. Bài học này trình bày ý tưởng, cấu phần, luồng phụ thuộc, ví dụ Java, kiểm thử và những quyết định cần cân nhắc khi áp dụng.

## 1. Vấn đề kiến trúc lục giác giải quyết

Hãy hình dung một ứng dụng đặt hàng ban đầu được xây dựng với một framework web và một cơ sở dữ liệu quan hệ. Controller nhận HTTP request, kiểm tra dữ liệu, tính tổng tiền, kiểm tra tồn kho, lưu đơn và gọi cổng thanh toán. Theo thời gian, nhóm bổ sung giao diện quản trị, xử lý đơn qua message queue và tác vụ tự động hết hạn đơn hàng.

Nếu mọi đường đi đều gọi trực tiếp controller, ORM, SDK và API của nhà cung cấp, logic nghiệp vụ sẽ phân tán ở nhiều nơi. Một số vấn đề có thể xuất hiện:

- Quy tắc xác nhận đơn bị lặp lại trong REST controller, consumer và tác vụ nền.
- Entity miền kế thừa lớp của ORM hoặc mang annotation của framework persistence.
- Domain service gọi trực tiếp HTTP client hoặc SDK thanh toán.
- Muốn kiểm thử một quy tắc phải dựng database, message broker và dịch vụ bên ngoài.
- Đổi giao thức từ REST sang message hoặc đổi nhà cung cấp buộc phải sửa phần lõi.
- Một lỗi của framework hoặc hệ thống ngoài lan vào logic nghiệp vụ.

Vấn đề cốt lõi là hướng phụ thuộc bị đảo ngược: phần nghiệp vụ cần phục vụ tổ chức lại phụ thuộc vào cách một công nghệ cụ thể hoạt động. Kiến trúc lục giác đưa phần lõi về vị trí trung tâm và yêu cầu các chi tiết bên ngoài thích nghi với nó.

## 2. Ý tưởng trung tâm: phần lõi và ranh giới

Trong kiến trúc lục giác, hình lục giác chỉ là cách minh họa. Nó nhấn mạnh rằng ứng dụng có thể có nhiều loại giao tiếp và nhiều adapter xung quanh, không phải chỉ có sáu thành phần hay sáu cổng.

Phần lõi chứa năng lực ứng dụng và các quy tắc nghiệp vụ cần được bảo vệ. Bên ngoài là các tác nhân và công nghệ có thể tương tác với lõi, ví dụ:

- Người dùng thông qua giao diện web hoặc ứng dụng di động.
- Hệ thống khác gọi REST API hoặc GraphQL.
- Message broker chuyển sự kiện hoặc command.
- Scheduler kích hoạt tác vụ theo thời gian.
- Cơ sở dữ liệu lưu và truy xuất trạng thái.
- Dịch vụ thanh toán, vận chuyển hoặc định danh do bên ngoài cung cấp.
- Công cụ dòng lệnh hoặc bộ kiểm thử gọi trực tiếp use case.

Các tác nhân này không cần biết cách phần lõi được tổ chức. Chúng giao tiếp qua những cổng được định nghĩa rõ. Phần lõi cũng không cần biết chi tiết HTTP, SQL, JSON, Kafka hay SDK của nhà cung cấp.

```text
        REST / Web UI        Message Consumer       Scheduler
              \                    |                   /
               \                   |                  /
                v                  v                 v
          +------------------------------------------------+
          |          Primary / Driving Adapters            |
          +--------------------------+---------------------+
                                     |
                                     v
          +------------------------------------------------+
          |              INPUT PORTS                       |
          |       Use cases / Application API              |
          +--------------------------+---------------------+
                                     |
                                     v
          +------------------------------------------------+
          |               APPLICATION CORE                 |
          |     Application services + Domain Model        |
          +--------------------------+---------------------+
                                     |
                                     v
          +------------------------------------------------+
          |              OUTPUT PORTS                      |
          |       Repository / Payment / Event API         |
          +--------------------------+---------------------+
                                     |
                                     v
          +------------------------------------------------+
          |          Secondary / Driven Adapters           |
          +--------------------------+---------------------+
                    |                 |                 |
                    v                 v                 v
                Database         Payment API        Message Broker
```

Sơ đồ mô tả luồng giao tiếp khái quát. Một ứng dụng có thể có nhiều input port và output port, và một port có thể có nhiều adapter triển khai hoặc sử dụng tùy mục tiêu.

## 3. Port là gì?

**Port (cổng)** là một điểm giao tiếp được định nghĩa theo nhu cầu hoặc khả năng của ứng dụng. Port thể hiện một hợp đồng: ai có thể yêu cầu điều gì từ ứng dụng, hoặc ứng dụng cần điều gì từ một thành phần bên ngoài.

Port nên được đặt tên theo ngôn ngữ và mục đích của phần lõi, không theo công nghệ đang dùng. Ví dụ:

- `PlaceOrderUseCase`: ứng dụng cung cấp khả năng đặt hàng.
- `CancelOrderUseCase`: ứng dụng cung cấp khả năng hủy đơn.
- `OrderRepository`: ứng dụng cần khả năng tải và lưu đơn hàng.
- `PaymentPort`: ứng dụng cần khả năng thu tiền hoặc hoàn tiền.
- `NotificationPort`: ứng dụng cần khả năng gửi thông báo.

Một port thường được biểu diễn bằng interface hoặc hợp đồng tương đương, nhưng không phải mọi interface trong codebase đều là port. Một interface chỉ trở thành port theo nghĩa kiến trúc khi nó xác định ranh giới giao tiếp giữa phần lõi và một tác nhân hoặc hệ thống bên ngoài.

### 3.1. Input port: ứng dụng cung cấp khả năng gì?

**Input port** (còn gọi là primary port hoặc driving port) định nghĩa những hành vi mà ứng dụng cho phép tác nhân bên ngoài yêu cầu. Nó thể hiện API của ứng dụng ở mức use case.

Ví dụ:

```java
public interface PlaceOrderUseCase {
    PlaceOrderResult placeOrder(PlaceOrderCommand command);
}
```

Hợp đồng này không nói request đến từ HTTP, giao diện di động, message hay dòng lệnh. Nó chỉ mô tả khả năng nghiệp vụ mà ứng dụng cung cấp.

### 3.2. Output port: ứng dụng cần khả năng gì từ bên ngoài?

**Output port** (còn gọi là secondary port hoặc driven port) định nghĩa những khả năng mà phần lõi cần một thành phần bên ngoài cung cấp. Ví dụ, ứng dụng cần lưu aggregate, gọi dịch vụ thanh toán hoặc công bố một thông báo.

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}

public interface PaymentPort {
    PaymentResult authorize(PaymentRequest request);
}
```

Application service sử dụng các hợp đồng này mà không cần biết adapter nào sẽ thực hiện. Một adapter có thể dùng JPA, JDBC, REST client hoặc một fake trong kiểm thử.

### 3.3. Port được định nghĩa ở đâu?

Port thường được định nghĩa ở phía trong ranh giới mà nó phục vụ, vì hợp đồng cần phản ánh nhu cầu của phần lõi. Input port mô tả use case mà ứng dụng cung cấp. Output port mô tả điều ứng dụng cần từ bên ngoài.

Vị trí package cụ thể tùy cách tổ chức dự án. Output port truy xuất aggregate có thể thuộc application layer hoặc domain layer tùy hợp đồng và quy tắc của repository. Điều quan trọng là interface không phụ thuộc vào kiểu dữ liệu hoặc framework của adapter.

## 4. Adapter là gì?

**Adapter (bộ chuyển đổi)** là thành phần ở bên ngoài port, chịu trách nhiệm kết nối một công nghệ hoặc tác nhân cụ thể với hợp đồng mà phần lõi hiểu.

Adapter chuyển đổi giữa giao thức bên ngoài và mô hình của ứng dụng. Nó có thể ánh xạ HTTP request thành command, chuyển dữ liệu từ database thành aggregate, hoặc biến yêu cầu nội bộ thành request của dịch vụ thanh toán.

Có hai nhóm adapter chính.

### 4.1. Primary adapter: đưa yêu cầu vào ứng dụng

Primary adapter còn được gọi là driving adapter hoặc inbound adapter. Nó nhận kích hoạt từ bên ngoài, chuyển đổi dữ liệu sang hợp đồng của input port và gọi use case.

Ví dụ:

- REST controller nhận HTTP request.
- GraphQL resolver nhận truy vấn hoặc mutation.
- Message consumer nhận message từ broker.
- CLI command nhận tham số từ terminal.
- Scheduler kích hoạt use case theo lịch.

Primary adapter không nên chứa quy tắc nghiệp vụ cốt lõi. Nó có thể thực hiện xác thực giao thức, kiểm tra cấu trúc đầu vào, ánh xạ kiểu dữ liệu và chuyển lỗi ứng dụng thành phản hồi phù hợp.

### 4.2. Secondary adapter: thực hiện điều mà ứng dụng cần

Secondary adapter còn được gọi là driven adapter hoặc outbound adapter. Nó triển khai output port bằng một công nghệ cụ thể.

Ví dụ:

- JPA adapter triển khai `OrderRepository` bằng ORM.
- JDBC adapter lưu aggregate vào cơ sở dữ liệu quan hệ.
- HTTP adapter gọi dịch vụ thanh toán.
- Message publisher gửi integration event đến broker.
- File adapter đọc hoặc ghi dữ liệu theo định dạng của đối tác.

Secondary adapter không quyết định quy tắc nghiệp vụ. Nó thực hiện hợp đồng mà phần lõi yêu cầu và chuyển kết quả trở lại kiểu dữ liệu mà phần lõi hiểu.

## 5. Driving và driven: hiểu hướng giao tiếp

Hai từ driving và driven mô tả vai trò trong một tương tác:

- **Driving side:** tác nhân khởi tạo tương tác và yêu cầu ứng dụng thực hiện một use case. Primary adapter nằm ở phía này.
- **Driven side:** thành phần được ứng dụng gọi để đáp ứng nhu cầu của use case. Secondary adapter nằm ở phía này.

Ví dụ khi khách đặt hàng qua web:

1. Trình duyệt gửi HTTP request.
2. REST controller là primary adapter, chuyển request thành `PlaceOrderCommand`.
3. Controller gọi input port `PlaceOrderUseCase`.
4. Application service thực thi use case và gọi `OrderRepository` cùng `PaymentPort`.
5. JPA adapter và payment adapter triển khai các output port.
6. Kết quả được trả về application service, rồi controller chuyển thành HTTP response.

Khi một message consumer kích hoạt cùng use case, nó là một primary adapter khác. Phần lõi không cần tạo một phiên bản logic đặt hàng riêng cho message.

## 6. Hướng phụ thuộc: chi tiết hướng vào phần lõi

Một nguyên tắc quan trọng của kiến trúc lục giác là **hướng phụ thuộc mã nguồn hướng vào phần lõi**. Adapter có thể phụ thuộc vào port và kiểu dữ liệu của phần lõi. Phần lõi không nên phụ thuộc vào implementation của adapter.

```text
Primary adapter  ----->  Input port  ----->  Application core

Application core ----->  Output port <-----  Secondary adapter
```

Ở nhánh output, application core gọi interface do nó định nghĩa; secondary adapter triển khai interface đó. Mặc dù tại runtime lời gọi đi từ core ra adapter, dependency trong mã nguồn vẫn hướng vào abstraction ở phía trong.

Điều này giúp:

- Thay REST bằng message hoặc CLI mà không thay use case.
- Thay JPA bằng JDBC hoặc một kho lưu trữ khác mà không sửa domain model.
- Thay nhà cung cấp thanh toán bằng adapter mới nếu hợp đồng nghiệp vụ vẫn phù hợp.
- Kiểm thử use case bằng fake hoặc stub thay cho hệ thống thật.
- Giữ domain model không bị phụ thuộc vào annotation, exception và kiểu dữ liệu của framework.

Dependency Injection thường được dùng để nối các interface với implementation tại composition root. Framework có thể khởi tạo controller, application service và adapter, nhưng nó chỉ là cơ chế lắp ráp. Quy tắc phụ thuộc của kiến trúc vẫn cần được giữ trong mã nguồn.

## 7. Ví dụ Java: use case đặt hàng qua các port

Giả sử một ứng dụng cho phép khách đặt hàng. Khi nhận yêu cầu, hệ thống cần kiểm tra dữ liệu, tạo đơn, yêu cầu thanh toán và lưu trạng thái đơn. Ta muốn use case không phụ thuộc vào HTTP, JPA hoặc SDK của cổng thanh toán.

### 7.1. Cấu trúc package gợi ý

```text
com.example.order
├── application
│   ├── port
│   │   ├── in
│   │   │   ├── PlaceOrderUseCase.java
│   │   │   ├── PlaceOrderCommand.java
│   │   │   └── PlaceOrderResult.java
│   │   └── out
│   │       ├── OrderRepository.java
│   │       └── PaymentPort.java
│   └── service
│       └── PlaceOrderService.java
├── domain
│   ├── model
│   │   ├── Order.java
│   │   └── OrderId.java
│   └── value
│       └── Money.java
└── adapter
    ├── in
    │   └── web
    │       └── OrderController.java
    └── out
        ├── persistence
        │   └── JpaOrderRepositoryAdapter.java
        └── payment
            └── HttpPaymentAdapter.java
```

Đây là một cách tổ chức tham khảo. Dự án có thể chia module hoặc package khác, miễn là ranh giới phụ thuộc vẫn rõ.

### 7.2. Định nghĩa input port

```java
public interface PlaceOrderUseCase {
    PlaceOrderResult placeOrder(PlaceOrderCommand command);
}

public record PlaceOrderCommand(
        String customerId,
        List<PlaceOrderLine> lines,
        String paymentToken
) {}

public record PlaceOrderLine(
        String productId,
        int quantity
) {}

public record PlaceOrderResult(
        String orderId,
        String status
) {}
```

Command là dữ liệu đầu vào của use case. Nó không nên mang `HttpServletRequest`, `ResponseEntity` hoặc kiểu đặc thù của framework web. Kết quả cũng nên được định nghĩa theo ứng dụng để nhiều primary adapter có thể sử dụng.

### 7.3. Định nghĩa output port

```java
public interface OrderRepository {
    void save(Order order);
}

public interface PaymentPort {
    PaymentResult authorize(PaymentRequest request);
}

public record PaymentRequest(
        String paymentToken,
        Money amount
) {}

public record PaymentResult(
        boolean approved,
        String reference
) {}
```

Các hợp đồng này thể hiện nhu cầu của use case. `PaymentPort` không nói ứng dụng đang dùng nhà cung cấp nào hoặc giao thức nào. Adapter sẽ đảm nhiệm chi tiết đó.

### 7.4. Triển khai application service

```java
public final class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orderRepository;
    private final PaymentPort paymentPort;

    public PlaceOrderService(
            OrderRepository orderRepository,
            PaymentPort paymentPort
    ) {
        this.orderRepository = orderRepository;
        this.paymentPort = paymentPort;
    }

    @Override
    public PlaceOrderResult placeOrder(PlaceOrderCommand command) {
        Order order = Order.create(command.customerId(), command.lines());

        PaymentResult payment = paymentPort.authorize(
                new PaymentRequest(command.paymentToken(), order.total())
        );

        if (!payment.approved()) {
            order.markPaymentRejected();
            orderRepository.save(order);
            return new PlaceOrderResult(
                    order.id().value(),
                    "PAYMENT_REJECTED"
            );
        }

        order.markPaymentAuthorized(payment.reference());
        orderRepository.save(order);

        return new PlaceOrderResult(order.id().value(), "CONFIRMED");
    }
}
```

Đây là mã minh họa luồng phụ thuộc, không phải một chính sách thanh toán hoàn chỉnh. Trong ứng dụng thật, cần xác định rõ thời điểm xác nhận đơn, giữ hàng, ghi nhận giao dịch, xử lý lỗi mạng và bù trừ khi một bước thành công còn bước khác thất bại. Không nên giả định một transaction database có thể bao trùm giao dịch với cổng thanh toán bên ngoài.

### 7.5. Primary adapter: REST controller

```java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final PlaceOrderUseCase placeOrderUseCase;

    public OrderController(PlaceOrderUseCase placeOrderUseCase) {
        this.placeOrderUseCase = placeOrderUseCase;
    }

    @PostMapping
    public ResponseEntity<PlaceOrderResponse> placeOrder(
            @RequestBody PlaceOrderRequest request
    ) {
        PlaceOrderCommand command = new PlaceOrderCommand(
                request.customerId(),
                request.lines().stream()
                        .map(line -> new PlaceOrderLine(
                                line.productId(), line.quantity()))
                        .toList(),
                request.paymentToken()
        );

        PlaceOrderResult result = placeOrderUseCase.placeOrder(command);
        return ResponseEntity.ok(new PlaceOrderResponse(
                result.orderId(), result.status()
        ));
    }
}
```

Controller chỉ chuyển đổi HTTP request thành command, gọi input port và ánh xạ kết quả thành HTTP response. Các kiểu `PlaceOrderRequest` và `PlaceOrderResponse` thuộc adapter web; chúng không cần xuất hiện trong domain model.

### 7.6. Secondary adapter: persistence và payment

Một JPA adapter triển khai `OrderRepository`:

```java
@Repository
public class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderRepository repository;
    private final OrderPersistenceMapper mapper;

    public JpaOrderRepositoryAdapter(
            SpringDataOrderRepository repository,
            OrderPersistenceMapper mapper
    ) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }
}
```

Một payment adapter triển khai `PaymentPort` bằng HTTP client hoặc SDK:

```java
@Component
public class HttpPaymentAdapter implements PaymentPort {
    private final PaymentApiClient client;

    public HttpPaymentAdapter(PaymentApiClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        ProviderPaymentResponse response = client.authorize(
                new ProviderPaymentRequest(
                        request.paymentToken(),
                        request.amount().amount(),
                        request.amount().currency().getCurrencyCode()
                )
        );

        return new PaymentResult(
                response.approved(),
                response.transactionReference()
        );
    }
}
```

`SpringDataOrderRepository`, `OrderPersistenceMapper`, `PaymentApiClient` và các kiểu `Provider...` là thành phần kỹ thuật của adapter. Chúng không nên bị kéo vào phần lõi chỉ để tiện gọi.

## 8. Composition root: lắp ráp các adapter và port

Các port và adapter cần được nối với nhau khi ứng dụng khởi động. Vị trí thực hiện việc này thường được gọi là **composition root**. Đây là nơi cấu hình Dependency Injection, tạo các implementation và cung cấp chúng cho application service.

Với Spring, framework có thể tự lắp ráp thông qua constructor injection và component scanning. Với ứng dụng nhỏ hoặc công cụ dòng lệnh, nhóm có thể tự tạo object trong một lớp bootstrap.

```java
public class ApplicationBootstrap {
    public static void main(String[] args) {
        OrderRepository orderRepository = createOrderRepository();
        PaymentPort paymentPort = createPaymentPort();

        PlaceOrderUseCase placeOrderUseCase =
                new PlaceOrderService(orderRepository, paymentPort);

        startHttpServer(new OrderController(placeOrderUseCase));
    }
}
```

Các phương thức `create...` và `startHttpServer` chỉ mang tính minh họa. Điểm cần nhớ là quyết định chọn adapter cụ thể được thực hiện ở lớp lắp ráp, không được rải trong domain model hoặc use case.

## 9. Kiểm thử nhờ các port

Một lợi ích lớn của kiến trúc lục giác là có thể kiểm thử phần lõi mà không cần khởi động toàn bộ hạ tầng. Vì application service phụ thuộc vào port, kiểm thử có thể cung cấp implementation giả để điều khiển kết quả.

### 9.1. Unit test use case với fake adapter

```java
class PlaceOrderServiceTest {
    @Test
    void savesOrderWhenPaymentIsApproved() {
        InMemoryOrderRepository orders = new InMemoryOrderRepository();
        PaymentPort approvedPayment = request ->
                new PaymentResult(true, "pay-123");

        PlaceOrderService service = new PlaceOrderService(
                orders,
                approvedPayment
        );

        PlaceOrderResult result = service.placeOrder(
                new PlaceOrderCommand(
                        "customer-1",
                        List.of(new PlaceOrderLine("product-1", 2)),
                        "token-test"
                )
        );

        assertEquals("CONFIRMED", result.status());
        assertEquals(1, orders.savedOrders().size());
    }
}
```

`InMemoryOrderRepository` là fake lưu aggregate trong bộ nhớ; `approvedPayment` là fake adapter trả kết quả đã xác định. Các object này giúp kiểm tra hành vi của use case mà không cần database hoặc cổng thanh toán thật.

### 9.2. Kiểm thử adapter riêng

Adapter cần được kiểm thử với công nghệ mà nó kết nối:

- Persistence adapter được kiểm thử với database hoặc test container để xác nhận ánh xạ, truy vấn và transaction.
- HTTP adapter được kiểm thử với mock server hoặc sandbox để xác nhận request, response, timeout và lỗi.
- Message adapter được kiểm thử với schema, serialization và hành vi broker phù hợp.
- REST adapter được kiểm thử để xác nhận HTTP status, validation, serialization và ánh xạ lỗi.

Việc tách kiểm thử giúp biết lỗi nằm ở quy tắc use case, bộ chuyển đổi hay giao thức bên ngoài.

### 9.3. Contract test và integration test

Unit test không chứng minh adapter tương thích với hệ thống thật. Khi tích hợp với một dịch vụ hoặc bounded context khác, contract test giúp xác nhận hai bên thống nhất về schema và hành vi. Integration test kiểm tra việc lắp ráp các thành phần trong một môi trường gần thực tế.

Không cần đưa mọi kiểm thử qua toàn bộ hệ thống. Hãy chọn đúng mức kiểm thử để phát hiện lỗi với chi phí phù hợp.

## 10. Giao dịch và tính nhất quán khi có hệ thống bên ngoài

Kiến trúc lục giác làm rõ ranh giới giao tiếp nhưng không tự giải quyết giao dịch phân tán. Một use case có thể cần lưu đơn vào database và đồng thời gọi cổng thanh toán. Nếu thanh toán thành công nhưng ghi database thất bại, hoặc database lưu thành công nhưng phản hồi thanh toán bị timeout, hệ thống cần một chính sách xử lý rõ ràng.

Nhóm cần xác định:

- Thứ tự các bước và thời điểm trạng thái nghiệp vụ được xác nhận.
- Request có thể gửi lại an toàn hay cần idempotency key.
- Kết quả chưa rõ do timeout được đối soát như thế nào.
- Khi một bước thất bại, có cần hủy giữ hàng, void giao dịch hoặc hoàn tiền không.
- Quy trình có cần saga/process manager hoặc outbox để phối hợp các bước bất đồng bộ không.
- Những trạng thái trung gian nào cần được mô hình hóa và hiển thị.

Ví dụ, nếu ứng dụng lưu `OrderCreated` và cần phát message, Transactional Outbox có thể giúp lưu thay đổi nghiệp vụ và thông điệp trong cùng transaction database; một tiến trình riêng gửi message sau đó. Nếu cần phối hợp thanh toán, kho và giao hàng qua nhiều bước, saga hoặc process manager có thể điều phối các hành động và bù trừ. Đây là các cơ chế bổ sung, không phải thành phần bắt buộc của mọi kiến trúc lục giác.

Không nên đặt toàn bộ quy trình phân tán vào một adapter chỉ để giữ application service ngắn. Quy tắc về trạng thái, thứ tự và bù trừ cần có chủ sở hữu rõ trong application/domain model phù hợp.

## 11. Phân biệt kiến trúc lục giác với layered architecture và Clean Architecture

Các kiến trúc này có chung mục tiêu giảm phụ thuộc vào chi tiết kỹ thuật, nhưng cách diễn đạt và trọng tâm có khác nhau.

| Cách tiếp cận | Trọng tâm | Điểm cần chú ý |
| --- | --- | --- |
| Layered Architecture | Chia hệ thống thành các tầng như presentation, application, domain, infrastructure | Nếu chỉ gọi từ tầng trên xuống tầng dưới, domain có thể vẫn phụ thuộc ngược vào hạ tầng qua kiểu dữ liệu hoặc framework |
| Hexagonal Architecture | Định nghĩa port ở ranh giới và adapter để kết nối tác nhân/hệ thống | Làm rõ ai driving, ai driven và hướng phụ thuộc vào phần lõi |
| Clean Architecture | Tổ chức các vòng phụ thuộc hướng vào business rules, thường mô tả entity, use case, interface adapter và framework | Cùng tinh thần dependency rule; nhấn mạnh các vòng và ranh giới trách nhiệm |

Các cách tiếp cận có thể kết hợp. Một ứng dụng có thể tổ chức package theo layer, định nghĩa port và adapter theo kiến trúc lục giác, đồng thời áp dụng dependency rule của Clean Architecture. Không nên tranh luận tên gọi thay cho việc kiểm tra phụ thuộc thực tế.

## 12. Cách tổ chức module và package

Có nhiều cách tổ chức code. Một cách phổ biến là gom theo bounded context hoặc feature trước, sau đó đặt port và adapter bên trong phạm vi đó.

```text
order
├── domain
│   ├── model
│   ├── value
│   └── event
├── application
│   ├── port
│   │   ├── in
│   │   └── out
│   └── service
└── adapter
    ├── in
    │   ├── web
    │   ├── messaging
    │   └── scheduler
    └── out
        ├── persistence
        ├── payment
        └── messaging
```

Với hệ thống lớn, các nhóm có thể tách thành module build riêng để giới hạn dependency. Ví dụ, module `order-domain` không phụ thuộc Spring; `order-application` phụ thuộc domain và định nghĩa port; `order-adapter-web` phụ thuộc application; `order-adapter-persistence` phụ thuộc application/domain cùng framework persistence; module bootstrap lắp ráp tất cả.

Không có một cấu trúc package duy nhất phù hợp mọi dự án. Hãy chọn cách tổ chức khiến người đọc dễ nhận ra ranh giới và có thể kiểm tra dependency bằng build hoặc kiến trúc test.

## 13. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Định nghĩa port theo giao thức như `HttpOrderPort` trong phần lõi | Use case bị gắn với cách giao tiếp cụ thể | Đặt tên port theo năng lực hoặc nhu cầu nghiệp vụ |
| Để domain model import framework web hoặc ORM | Quy tắc miền phụ thuộc hạ tầng | Đưa annotation và kiểu kỹ thuật về adapter khi có thể |
| Đưa logic nghiệp vụ vào controller | Nhiều adapter có thể thực hiện quy tắc khác nhau | Đặt hành vi trong domain model hoặc use case phù hợp |
| Gọi SDK bên ngoài trực tiếp từ domain service | Nhà cung cấp chi phối mô hình và khó kiểm thử | Định nghĩa output port và triển khai adapter |
| Xem mọi interface là port | Ranh giới kiến trúc trở nên khó hiểu | Chỉ gọi là port khi nó xác định hợp đồng qua ranh giới |
| Tạo quá nhiều port và adapter không có giá trị | Tăng số lớp và chi phí điều hướng mã | Tạo abstraction khi có ranh giới hoặc lý do thay đổi thực sự |
| Đưa DTO của adapter vào use case | Phần lõi phụ thuộc cấu trúc giao tiếp | Dùng command/result hoặc kiểu nội bộ ổn định |
| Cho rằng kiến trúc lục giác tự giải quyết transaction phân tán | Có thể mất dữ liệu hoặc tạo giao dịch trùng | Thiết kế idempotency, outbox, saga và đối soát khi cần |
| Chỉ kiểm thử use case bằng mock | Không phát hiện lỗi ánh xạ hoặc hợp đồng tích hợp | Kiểm thử adapter, contract và integration ở mức phù hợp |

Một dấu hiệu cần xem lại là khi thay đổi một framework buộc nhóm sửa các quy tắc nghiệp vụ, hoặc khi thêm một cách kích hoạt use case phải sao chép logic. Khi đó, ranh giới port/adapter có thể chưa được đặt đúng.

## 14. Quy trình áp dụng kiến trúc lục giác

Có thể áp dụng theo các bước sau cho một bounded context hoặc một use case cụ thể.

### Bước 1: Xác định use case và quy tắc miền

Mô tả hành vi mà ứng dụng cần cung cấp, actor, kết quả và các bất biến. Xác định phần nào là logic nghiệp vụ cần giữ ổn định khi công nghệ thay đổi.

### Bước 2: Xác định input port

Định nghĩa hợp đồng mà ứng dụng cung cấp. Dùng command, query hoặc kiểu dữ liệu phù hợp với use case. Không đưa HTTP request, message envelope hoặc DTO của nhà cung cấp vào hợp đồng nếu chúng không thuộc ngôn ngữ của ứng dụng.

### Bước 3: Xác định output port

Liệt kê những khả năng bên ngoài mà use case cần: lưu aggregate, đọc dữ liệu, thu tiền, gửi thông báo hoặc công bố sự kiện. Định nghĩa hợp đồng tối thiểu đáp ứng nhu cầu của phần lõi.

### Bước 4: Triển khai application service và domain behavior

Application service điều phối use case qua các port. Quy tắc và bất biến thuộc domain model được đặt trong entity, value object, aggregate hoặc domain service phù hợp.

### Bước 5: Viết primary adapter

Chọn các cách kích hoạt cần thiết như REST, message consumer, CLI hoặc scheduler. Adapter chuyển dữ liệu giao tiếp thành command/query và gọi input port.

### Bước 6: Viết secondary adapter

Triển khai output port bằng database, API, broker hoặc hệ thống ngoài. Chuyển đổi dữ liệu tại ranh giới và giữ chi tiết công nghệ bên ngoài phần lõi.

### Bước 7: Lắp ráp tại composition root

Kết nối port với adapter thông qua Dependency Injection hoặc bootstrap. Tránh khởi tạo implementation cụ thể bên trong domain model hoặc use case.

### Bước 8: Kiểm thử các ranh giới

Kiểm thử use case với fake, kiểm thử adapter với công nghệ tương ứng và kiểm thử hợp đồng/integration ở những nơi cần thiết. Xác nhận hướng phụ thuộc bằng module boundary hoặc kiến trúc test nếu dự án có quy mô phù hợp.

### Bước 9: Theo dõi và điều chỉnh

Khi thêm giao thức, thay nhà cung cấp hoặc thay đổi nghiệp vụ, kiểm tra xem port còn phản ánh đúng nhu cầu của phần lõi không. Không giữ abstraction cũ chỉ vì nó đã tồn tại nếu hợp đồng không còn phù hợp.

## 15. Nguyên tắc thực hành

Khi áp dụng kiến trúc lục giác trong DDD, nhóm nên duy trì các nguyên tắc sau:

- **Để phần lõi định nghĩa hợp đồng.** Port thể hiện khả năng ứng dụng cung cấp hoặc nhu cầu ứng dụng cần, không sao chép API của framework.
- **Đặt adapter ở ranh giới.** HTTP, SQL, broker, SDK và giao thức nằm trong thành phần chuyển đổi tương ứng.
- **Giữ dependency hướng vào trong.** Adapter phụ thuộc vào port và mô hình nội bộ; domain model không phụ thuộc adapter.
- **Đặt quy tắc đúng nơi.** Controller chuyển đổi request, application service điều phối use case, domain model bảo vệ bất biến, adapter xử lý giao tiếp kỹ thuật.
- **Không tạo abstraction vô ích.** Port nên phản ánh một ranh giới hoặc lý do thay đổi thực tế.
- **Lắp ráp ở composition root.** Quyết định implementation cụ thể được tập trung tại bootstrap hoặc cấu hình DI.
- **Kiểm thử theo ranh giới.** Dùng fake cho use case và kiểm thử adapter với hệ thống mà nó kết nối.
- **Thiết kế cho tính nhất quán phân tán.** Khi có nhiều hệ thống, xử lý idempotency, outbox, retry và bù trừ theo nhu cầu nghiệp vụ.
- **Giữ ngôn ngữ bounded context.** Port và command/result nên dùng thuật ngữ mà chuyên gia nghiệp vụ và nhóm phát triển đã thống nhất.

Kiến trúc lục giác tạo ra một ranh giới rõ giữa mô hình ứng dụng và thế giới bên ngoài. Port mô tả hợp đồng, adapter chuyển đổi giữa hợp đồng và công nghệ cụ thể, còn phần lõi giữ trách nhiệm thực thi use case và bảo vệ quy tắc miền. Khi hướng phụ thuộc được giữ đúng và các ranh giới được thiết kế theo nhu cầu thật, ứng dụng có thể thay đổi cách giao tiếp và lưu trữ mà không làm mất đi mô hình nghiệp vụ.

## 16. Câu hỏi tự kiểm tra

1. Kiến trúc lục giác giải quyết vấn đề gì khi phần lõi phụ thuộc trực tiếp vào framework và hệ thống bên ngoài?
2. Port là gì? Vì sao không phải mọi interface đều là port?
3. Phân biệt input port và output port bằng ví dụ đặt hàng.
4. Primary adapter và secondary adapter khác nhau như thế nào về vai trò?
5. Vì sao dependency trong mã nguồn cần hướng vào phần lõi dù application service gọi secondary adapter tại runtime?
6. REST controller nên thực hiện những trách nhiệm nào và những quy tắc nào cần nằm trong use case hoặc domain model?
7. Vì sao output port nên được đặt tên theo nhu cầu của ứng dụng thay vì theo nhà cung cấp kỹ thuật?
8. Composition root có trách nhiệm gì trong kiến trúc lục giác?
9. Những loại kiểm thử nào phù hợp cho use case, adapter và hợp đồng tích hợp?
10. Vì sao transaction database không thể tự bảo đảm tính nguyên tử khi use case gọi một cổng thanh toán bên ngoài?
11. Phân biệt trọng tâm của Layered Architecture, Hexagonal Architecture và Clean Architecture.
12. Hãy chọn một use case trong hệ thống của bạn, xác định input port, output port, primary adapter, secondary adapter và vẽ hướng phụ thuộc giữa chúng.
