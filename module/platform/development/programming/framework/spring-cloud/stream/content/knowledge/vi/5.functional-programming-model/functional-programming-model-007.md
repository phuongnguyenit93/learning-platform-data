# Gọi service nghiệp vụ từ hàm và quản lý phụ thuộc

Trong ứng dụng Spring Cloud Stream, một hàm `Supplier`, `Function` hoặc `Consumer` là điểm tiếp nhận hoặc phát message của ứng dụng. Hàm nên tập trung vào việc chuyển dữ liệu message sang lời gọi nghiệp vụ và chuyển kết quả nghiệp vụ thành message đầu ra. Các quy tắc như xác thực đơn hàng, tính phí, cập nhật tồn kho và lưu dữ liệu nên nằm trong service nghiệp vụ do Spring quản lý.

Cách tổ chức này giúp mã xử lý sự kiện dễ kiểm thử và ít phụ thuộc vào Kafka, RabbitMQ hoặc Pulsar. Spring Dependency Injection cung cấp các service cần thiết cho function bean; Spring Cloud Stream quản lý binding và binder để đưa message tới hàm. Khi giữ rõ ranh giới giữa adapter message và service nghiệp vụ, có thể thay đổi broker hoặc cách kiểm thử mà ít ảnh hưởng tới logic cốt lõi.

## 1. Phân chia trách nhiệm giữa function và service

Một luồng xử lý sự kiện thường có các bước:

1. Binder nhận message từ destination và chuyển payload sang kiểu Java mà function khai báo.
2. Spring Cloud Stream gọi function đã được cấu hình.
3. Function đọc payload và metadata cần thiết, sau đó gọi service nghiệp vụ.
4. Service thực hiện quy tắc nghiệp vụ, truy cập repository hoặc gọi các port phụ thuộc.
5. Nếu là `Function`, kết quả được trả về để framework phát message đầu ra; nếu là `Consumer`, hàm hoàn thành sau tác vụ xử lý.
6. Binder thực hiện việc gửi/ghi nhận message theo cấu hình broker.

Function là adapter ở biên hệ thống. Service là nơi diễn đạt hành động nghiệp vụ. Ví dụ, function `acceptOrder` có thể nhận `OrderCreated` và gọi `OrderApplicationService.accept()`. Service quyết định đơn hàng có hợp lệ hay không, lưu trạng thái và tạo kết quả nghiệp vụ.

Không nên đặt toàn bộ truy vấn database, tính toán nghiệp vụ, gọi nhiều API và xử lý transaction trong lambda của function. Lambda càng ngắn thì càng dễ đọc, kiểm thử và tái sử dụng từ REST controller, scheduler hoặc một luồng xử lý khác.

## 2. Khai báo service nghiệp vụ bằng Spring

Spring quản lý các thành phần như service và repository thông qua ApplicationContext. Có thể dùng `@Service` cho lớp nghiệp vụ và constructor injection để khai báo các phụ thuộc bắt buộc.

Ví dụ service tiếp nhận một đơn hàng:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;

    public OrderApplicationService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderAccepted accept(OrderCreated event) {
        return accept(event, null, null);
    }

    @Transactional
    public OrderAccepted accept(
            OrderCreated event, String eventId, String correlationId) {
        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        Order order = Order.create(
            event.orderId(),
            event.customerId(),
            event.items()
        );

        // Có thể dùng eventId/correlationId cho audit và idempotency.
        orderRepository.save(order);

        return new OrderAccepted(order.id(), "ACCEPTED");
    }
}
```

Ví dụ giả định dự án đã có các kiểu `OrderCreated`, `OrderAccepted`, `Order`, `OrderRepository` và `InvalidOrderException`. Service nhận một đối tượng sự kiện đã được chuyển đổi thành kiểu Java; nó không cần biết message đến từ Kafka topic hay RabbitMQ queue.

Constructor injection có một số lợi ích:

- Các dependency bắt buộc được thể hiện ngay trong constructor.
- Có thể khai báo field là `final`, tránh việc đối tượng ở trạng thái thiếu dependency.
- Unit test dễ tạo service với mock hoặc fake repository.
- Spring có thể kiểm tra và giải quyết dependency khi tạo bean.

Với một constructor duy nhất, Spring có thể tự sử dụng constructor đó để inject dependency mà không cần đặt `@Autowired`. Khi có nhiều constructor, cần chỉ rõ constructor hoặc factory method mà Spring sẽ dùng.

Không nên gọi `new OrderApplicationService(...)` bên trong function nếu service cần transaction, cache, security hoặc các Spring proxy khác. Việc tự tạo object sẽ bỏ qua vòng đời và các cơ chế quản lý bean của Spring.

## 3. Inject service vào function bằng tham số của @Bean

Một cách phổ biến để khai báo function là tạo bean trong lớp `@Configuration`. Spring có thể inject service trực tiếp vào tham số của phương thức `@Bean`.

```java
@Configuration
public class OrderFunctions {

    @Bean
    public Function<OrderCreated, OrderAccepted> acceptOrder(
            OrderApplicationService orderService) {

        return orderService::accept;
    }
}
```

Phương thức `acceptOrder` trả về một `Function<OrderCreated, OrderAccepted>`. Spring giải quyết `OrderApplicationService` từ ApplicationContext rồi truyền vào phương thức factory. Function nhận sự kiện và ủy quyền xử lý cho service.

Nếu cần chuyển đổi dữ liệu hoặc bổ sung bước ở adapter, có thể thay thân phương thức trên bằng lambda:

```java
@Bean
public Function<OrderCreated, OrderAccepted> acceptOrder(
        OrderApplicationService orderService) {

    return event -> {
        // Chỉ thực hiện chuyển đổi ở biên nếu cần.
        return orderService.accept(event);
    };
}
```

Hai cách trên có cùng mục tiêu. Method reference ngắn gọn khi function chỉ chuyển tiếp lời gọi; lambda hữu ích khi cần kiểm tra dữ liệu ở lớp giao tiếp, ánh xạ kiểu hoặc bổ sung metadata. Quy tắc nghiệp vụ vẫn nên nằm trong service.

Khi Spring Cloud Stream phát hiện function bean, tên bean có thể được chọn qua cấu hình:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: order-service
        acceptOrder-out-0:
          destination: orders.accepted
```

Binding đầu vào `acceptOrder-in-0` kết nối với destination `orders.created`; binding đầu ra `acceptOrder-out-0` kết nối với `orders.accepted`. Binder đang dùng sẽ ánh xạ destination và group sang tài nguyên của broker. Function không cần tự tạo consumer hoặc producer của Kafka/RabbitMQ.

Với một `Consumer<OrderCreated>`, chỉ có binding đầu vào. Với `Supplier<OrderCreated>`, function tạo dữ liệu đầu ra và thường được framework gọi theo poller đã cấu hình. Cách inject service vào tham số `@Bean` cũng áp dụng cho các loại hàm này:

```java
@Bean
public Consumer<PaymentReceived> recordPayment(
        PaymentApplicationService paymentService) {
    return paymentService::record;
}
```

Ví dụ trên minh họa một function khác; trong ứng dụng thực tế, cần chọn function definition tương ứng và cấu hình binding cho đúng bean được triển khai.

## 4. Inject service qua constructor của function component

Ngoài factory method, có thể khai báo một lớp triển khai trực tiếp `Consumer` hoặc `Function` và inject service qua constructor. Cách này hữu ích khi adapter có nhiều bước xử lý hoặc cần cấu trúc lớp riêng.

```java
@Component("recordPayment")
public class RecordPaymentFunction
        implements Consumer<PaymentReceived> {

    private final PaymentApplicationService paymentService;

    public RecordPaymentFunction(
            PaymentApplicationService paymentService) {
        this.paymentService = paymentService;
    }

    @Override
    public void accept(PaymentReceived event) {
        paymentService.record(event);
    }
}
```

Spring tạo bean `recordPayment` và inject `PaymentApplicationService`. Spring Cloud Function nhận diện bean theo kiểu functional interface; Spring Cloud Stream có thể chọn function theo tên:

```yaml
spring:
  cloud:
    function:
      definition: recordPayment
    stream:
      bindings:
        recordPayment-in-0:
          destination: payments.received
          group: payment-service
```

Không cần đồng thời khai báo một `@Bean Consumer` khác có cùng chức năng và cùng tên. Hãy chọn một cách đăng ký function cho mỗi bean để tránh xung đột tên hoặc cấu hình khó hiểu.

### Chọn giữa @Bean và component

| Tiêu chí | Function từ phương thức @Bean | Lớp @Component triển khai Function/Consumer |
|---|---|---|
| Cách khai báo | Factory method trả về functional interface | Class triển khai trực tiếp interface |
| Inject service | Tham số phương thức @Bean | Constructor |
| Phù hợp | Adapter ngắn, chuyển tiếp tới service | Adapter có cấu trúc hoặc nhiều bước riêng |
| Kiểm thử | Gọi phương thức factory và thực thi function | Tạo component với service mock hoặc lấy bean từ context |
| Tên function | Tên phương thức @Bean | Tên component/bean |

Cả hai đều dùng Spring Dependency Injection và đều có thể được Spring Cloud Function nhận diện. Chọn cách nào phụ thuộc vào độ phức tạp của adapter và quy ước của dự án.

## 5. Quản lý nhiều service phụ thuộc

Một function đôi khi cần phối hợp nhiều thao tác: kiểm tra khách hàng, giữ hàng, tính phí và ghi nhận đơn hàng. Có thể inject nhiều service trực tiếp vào phương thức `@Bean`, nhưng nếu function bắt đầu điều phối nhiều bước nghiệp vụ, nên tạo một application service hoặc use case chuyên trách.

Ví dụ:

```java
@Service
public class CheckoutService {

    private final CustomerService customerService;
    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    public CheckoutService(
            CustomerService customerService,
            InventoryService inventoryService,
            OrderRepository orderRepository) {
        this.customerService = customerService;
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    public OrderAccepted checkout(OrderCreated event) {
        customerService.assertCanOrder(event.customerId());
        inventoryService.reserve(event.items());

        Order order = Order.create(
            event.orderId(),
            event.customerId(),
            event.items()
        );

        orderRepository.save(order);
        return new OrderAccepted(order.id(), "ACCEPTED");
    }
}
```

Function chỉ cần một dependency điều phối:

```java
@Bean
Function<OrderCreated, OrderAccepted> checkout(
        CheckoutService checkoutService) {
    return checkoutService::checkout;
}
```

Cấu trúc này giúp function giữ vai trò adapter và service thể hiện use case. Các service con có thể được tái sử dụng từ những luồng khác. Khi use case cần phối hợp nhiều hệ thống, cần xác định rõ ranh giới transaction và cách bù trừ nếu một bước thành công còn bước sau thất bại.

Không nên tạo một service tổng hợp chỉ để gom mọi dependency mà không có trách nhiệm nghiệp vụ rõ ràng. Hãy nhóm các thao tác theo một use case có tên và mục tiêu cụ thể.

## 6. Truyền payload và metadata tới service

Function có thể nhận trực tiếp payload:

```java
@Bean
Consumer<OrderCreated> recordOrder(OrderApplicationService service) {
    return event -> service.accept(event);
}
```

Nếu adapter cần đọc header như event ID hoặc correlation ID, khai báo đầu vào là `Message<T>`:

```java
@Bean
Consumer<Message<OrderCreated>> recordOrder(
        OrderApplicationService service) {

    return message -> {
        OrderCreated event = message.getPayload();
        String eventId = (String) message.getHeaders().get("eventId");
        String correlationId =
            (String) message.getHeaders().get("correlationId");

        service.accept(event, eventId, correlationId);
    };
}
```

Ở ví dụ này, adapter chuyển thông tin từ message envelope sang tham số của use case. Service nhận dữ liệu cần cho nghiệp vụ mà không phải phụ thuộc vào `MessageHeaders`, `MessageChannel` hoặc API của binder.

Nên phân biệt metadata kỹ thuật với dữ liệu nghiệp vụ. Correlation ID có thể dùng để theo dõi một luồng xử lý; event ID có thể dùng để chống xử lý trùng. Nếu event ID là một phần của quy tắc idempotency, hãy truyền nó tới service hoặc một thành phần chuyên trách. Không nên đưa toàn bộ map header vào service chỉ vì có sẵn.

Khi function tạo message đầu ra, có thể xây dựng header mới:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder(
        OrderApplicationService service) {

    return input -> {
        OrderAccepted result = service.accept(input.getPayload());

        return MessageBuilder
            .withPayload(result)
            .setHeader("correlationId",
                input.getHeaders().get("correlationId"))
            .build();
    };
}
```

Chỉ chuyển tiếp những header cần thiết. Binder có thể có quy tắc mapping header riêng; cần kiểm thử với broker thật nếu header là một phần của hợp đồng tích hợp.

## 7. Quản lý transaction và lỗi khi gọi service

Service nghiệp vụ thường là nơi thích hợp để đặt transaction cho thao tác database. Ví dụ `@Transactional` trên `OrderApplicationService.accept()` xác định ranh giới transaction do Spring quản lý khi function gọi bean service qua proxy.

Để transaction hoạt động đúng:

- Service phải được Spring quản lý như một bean.
- Lời gọi phải đi qua proxy transaction được cấu hình.
- Các thao tác database cần tham gia cùng transaction manager phù hợp.
- Cần hiểu quy tắc rollback, đặc biệt với checked exception và runtime exception theo cấu hình transaction.

Tách service thành bean riêng cũng tránh một lỗi thường gặp: self-invocation. Nếu một phương thức trong cùng đối tượng gọi trực tiếp phương thức khác có `@Transactional`, lời gọi nội bộ đó có thể không đi qua proxy và không kích hoạt transaction như mong đợi.

### Để lỗi đi tới cơ chế xử lý của binder

Nếu service ném exception khi xử lý message, function thường nên để exception truyền ra ngoài để framework/binder áp dụng cơ chế xử lý lỗi đã cấu hình. Không nên bắt mọi exception rồi bỏ qua hoặc trả về một kết quả giả, vì khi đó message có thể được xem là đã xử lý thành công.

Có thể phân loại lỗi theo tính chất:

- Lỗi tạm thời, ví dụ database hoặc dịch vụ phụ thuộc mất kết nối trong thời gian ngắn, có thể phù hợp với retry.
- Lỗi dữ liệu hoặc quy tắc nghiệp vụ không thể khắc phục bằng retry thường cần được xử lý theo chính sách lỗi không retry hoặc đưa vào DLQ/DLT.
- Lỗi lập trình cần được ghi log, theo dõi và sửa ở ứng dụng.

Retry và DLQ do binder/broker cấu hình; việc gọi service không tự tạo ra chính sách retry. Nếu broker giao lại message, service có thể được gọi nhiều lần. Các thao tác ghi dữ liệu cần idempotent hoặc có cơ chế deduplication bằng event ID/khóa nghiệp vụ.

### Transaction database không tự bao trùm broker

Một transaction database do service mở không mặc nhiên bao gồm việc commit offset Kafka hoặc xác nhận message RabbitMQ. Nếu database commit thành công nhưng tiến trình lỗi trước khi broker ghi nhận việc xử lý, message có thể được giao lại. Ngược lại, nếu message được xác nhận trước khi dữ liệu nghiệp vụ được lưu, sự kiện có thể bị mất khỏi góc nhìn của consumer.

Với luồng cần bảo đảm nhất quán giữa database và broker, cân nhắc transactional outbox, inbox/deduplication hoặc transaction tích hợp được broker hỗ trợ. Cần đánh giá chính xác phạm vi bảo đảm của binder và broker đang dùng; không giả định `@Transactional` trên service tự tạo giao dịch phân tán.

## 8. Quản lý trạng thái và thread safety của function bean

Các bean Spring thường có scope singleton nếu không khai báo scope khác. Function bean được tạo một lần và có thể được gọi nhiều lần trong vòng đời ứng dụng. Tùy binder, concurrency và cấu hình consumer, nhiều message có thể được xử lý đồng thời.

Do đó, function nên tránh lưu trạng thái riêng của từng message trong field:

```java
// Không nên: dữ liệu của các lần gọi có thể ghi đè lẫn nhau.
@Component
class UnsafeOrderFunction implements Consumer<OrderCreated> {

    private OrderCreated currentOrder;

    @Override
    public void accept(OrderCreated event) {
        this.currentOrder = event;
        // Xử lý tiếp dựa trên field mutable này.
    }
}
```

Hãy dùng biến cục bộ trong mỗi lần gọi và để trạng thái nghiệp vụ trong database hoặc thành phần lưu trữ có cơ chế đồng bộ phù hợp:

```java
@Component
class SafeOrderFunction implements Consumer<OrderCreated> {

    private final OrderApplicationService service;

    SafeOrderFunction(OrderApplicationService service) {
        this.service = service;
    }

    @Override
    public void accept(OrderCreated event) {
        service.accept(event);
    }
}
```

Service và các dependency dùng chung cũng cần an toàn khi được gọi đồng thời. Repository Spring thường được thiết kế để sử dụng qua bean proxy, nhưng object nghiệp vụ mutable, cache tự viết hoặc client tùy chỉnh vẫn cần được đánh giá. Không tạo một object dùng chung để chứa payload đang xử lý nếu không có cơ chế đồng bộ và lý do rõ ràng.

Nếu cần giới hạn số message xử lý đồng thời, hãy cấu hình concurrency hoặc giới hạn tài nguyên ở tầng binder/container theo broker. Không dùng biến instance của function để tự điều tiết số lượng message.

## 9. Kiểm thử function và dependency injection

Nên kiểm thử riêng logic service, hành vi function và việc Spring wiring dependency.

### Unit test cho function

Có thể gọi phương thức `@Bean` trực tiếp với service mock, sau đó thực thi function:

```java
class OrderFunctionsTest {

    @Test
    void delegatesOrderToApplicationService() {
        OrderApplicationService service =
            mock(OrderApplicationService.class);

        OrderFunctions functions = new OrderFunctions();

        Function<OrderCreated, OrderAccepted> function =
            functions.acceptOrder(service);

        OrderCreated event = new OrderCreated("order-42");
        OrderAccepted expected =
            new OrderAccepted("order-42", "ACCEPTED");

        when(service.accept(event)).thenReturn(expected);

        OrderAccepted actual = function.apply(event);

        assertThat(actual).isEqualTo(expected);
        verify(service).accept(event);
    }
}
```

Unit test này xác minh function chuyển đúng sự kiện cho service và trả lại kết quả. Nó không cần khởi động Spring context hoặc broker.

### Unit test cho service

Service nên được kiểm thử độc lập với binder. Mock repository hoặc dependency bên ngoài để xác minh quy tắc nghiệp vụ: dữ liệu không hợp lệ bị từ chối, đơn hàng hợp lệ được lưu và kết quả trả về chính xác. Nếu có transaction, cần thêm integration test với cấu hình persistence phù hợp để xác minh rollback và commit.

### Kiểm thử Spring context

Một bài kiểm thử với `@SpringBootTest` có thể xác minh function bean được đăng ký, service được inject và function definition được chọn đúng. Nếu kiểm tra cả binding, Spring Cloud Stream Test Binder có thể gửi message vào binding và đọc message đầu ra trong bộ nhớ.

Test Binder không xác minh transaction database, offset, acknowledgement, retry hoặc DLQ của broker thật. Với những hành vi phụ thuộc broker, cần integration test bằng Kafka, RabbitMQ hoặc Pulsar thật, thường thông qua Testcontainers.

## 10. Checklist khi thiết kế function gọi service

- Function chỉ làm nhiệm vụ adapter: nhận payload/header, gọi use case và chuyển kết quả thành đầu ra nếu có.
- Service nghiệp vụ được khai báo bằng bean Spring và inject qua constructor hoặc tham số `@Bean`.
- Không tự tạo service bằng `new`, không dùng static ApplicationContext để lấy dependency.
- Đặt transaction ở service/use case theo đúng ranh giới dữ liệu cần bảo vệ.
- Để exception phù hợp truyền tới binder; không âm thầm biến lỗi thành thành công.
- Thiết kế xử lý idempotent vì message có thể được giao lại.
- Tránh lưu dữ liệu của từng message trong field mutable của singleton function.
- Kiểm thử function và service độc lập; kiểm thử wiring, binding và broker theo từng tầng.
- Xác định rõ transaction database không tự bảo đảm giao dịch nguyên tử với broker.

Khi function gọi service thông qua Dependency Injection, mã xử lý sự kiện giữ được cấu trúc gọn và phụ thuộc rõ ràng. Spring quản lý vòng đời service, còn binder quản lý kết nối message với broker. Phân chia trách nhiệm như vậy giúp cùng một use case có thể được gọi từ Spring Cloud Stream, REST API hoặc scheduler mà không phải sao chép quy tắc nghiệp vụ.

