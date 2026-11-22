# Giữ đồ thị phụ thuộc có hướng rõ ràng và xử lý vòng từ thiết kế

Một ứng dụng Spring Boot thường có hàng chục hoặc hàng trăm bean, package và module. Mỗi thành phần sử dụng một số thành phần khác để hoàn thành công việc. Khi những quan hệ này được tổ chức hợp lý, ta có thể hiểu module nào sở hữu nghiệp vụ, module nào cung cấp hạ tầng và thay đổi ở một khu vực sẽ ảnh hưởng tới đâu.

Ngược lại, khi các thành phần phụ thuộc lẫn nhau theo nhiều hướng, đặc biệt tạo thành **vòng phụ thuộc**, code trở nên khó khởi tạo, khó kiểm thử và khó thay đổi. Spring có thể báo `BeanCurrentlyInCreationException` khi không thể tạo bean theo dependency graph; build tool cũng có thể từ chối một đồ thị module có chu trình. Ngay cả khi framework có một cách trì hoãn hoặc giải quyết một số vòng bean, kiến trúc vẫn có thể bị ràng buộc chặt.

Cách bền vững là thiết kế các quan hệ phụ thuộc có hướng rõ ràng, giữ chúng thành đồ thị không chu trình (DAG) ở những ranh giới kiến trúc quan trọng và xử lý vòng bằng cách thay đổi trách nhiệm, hướng phụ thuộc hoặc cách phối hợp giữa các thành phần.

## 1. Dependency graph là gì?

Một **dependency graph** là đồ thị mô tả thành phần nào cần thành phần nào. Có thể biểu diễn:

- Mỗi node là một class, bean, package hoặc module.
- Mỗi directed edge là một quan hệ phụ thuộc.
- Nếu A cần B để thực hiện công việc, ta vẽ cạnh `A → B`.

Ví dụ:

~~~text
OrderController → PlaceOrderService
PlaceOrderService → OrderRepository
PlaceOrderService → PaymentPort
PaymentAdapter → PaymentPort
PaymentAdapter → PaymentClient
~~~

Cần thống nhất chiều mũi tên: trong bài này, `A → B` có nghĩa **A phụ thuộc vào B**. Mũi tên chỉ hướng phụ thuộc trong source code hoặc contract, không nhất thiết là thứ tự request đi qua các component tại runtime.

Một graph có hướng giúp trả lời:

- Thành phần nào đang sở hữu trách nhiệm?
- Khi thay đổi interface B, những thành phần nào có thể bị ảnh hưởng?
- Có module nào phụ thuộc vào module cấp thấp hơn theo chiều ngược kiến trúc không?
- Có đường đi nào quay trở lại node ban đầu không?
- Một dependency có thực sự cần thiết hay chỉ xuất hiện do thiết kế chưa tách trách nhiệm?

### Direct và transitive dependency

Nếu `A → B` và `B → C`, thì A phụ thuộc trực tiếp vào B và phụ thuộc gián tiếp (transitively) vào C:

~~~text
A → B → C
~~~

A không nhất thiết phải import hoặc gọi C trực tiếp. Tuy nhiên, thay đổi C có thể ảnh hưởng A thông qua B, tùy contract và cách triển khai.

Đừng nhầm dependency graph ở cấp source với dependency graph của build tool. Maven/Gradle thể hiện artifact và module được resolve; Spring container quản lý quan hệ giữa bean runtime; còn package/class architecture mô tả các quan hệ trong source code. Chúng liên quan nhưng không đồng nhất.

## 2. Đồ thị không chu trình (DAG)

Một directed graph được gọi là **acyclic** khi không tồn tại đường đi có hướng bắt đầu ở một node và quay lại chính node đó. Đồ thị có hướng không chu trình thường được gọi là DAG (*Directed Acyclic Graph*).

Ví dụ DAG:

~~~text
Web layer
    |
    v
Application layer
    |
    v
Domain layer
~~~

Một dependency graph có chu trình:

~~~text
OrderService → InventoryService
      ^                |
      |________________|
~~~

Ở đây:

- OrderService cần InventoryService.
- InventoryService lại cần OrderService.
- Đường đi quay về node ban đầu, tạo thành cycle.

### Vì sao DAG hữu ích?

DAG giúp tổ chức kiến trúc theo các tầng hoặc module có thứ tự rõ ràng:

- Dependency có thể được khởi tạo theo thứ tự phù hợp.
- Module thấp hơn không phải biết module cao hơn.
- Build tool có thể xác định thứ tự build module.
- Thay đổi contract có phạm vi ảnh hưởng dễ dự đoán hơn.
- Unit test có thể thay dependency ở một ranh giới rõ ràng.
- Việc chia module và tái sử dụng code dễ quản lý hơn.

Với một DAG, luôn có thể tìm được ít nhất một thứ tự topo (*topological ordering*) sao cho dependency được xử lý trước thành phần phụ thuộc vào nó. Nếu graph có cycle, không tồn tại thứ tự topo bao phủ tất cả node.

Đây là một lý do constructor injection có thể phát hiện circular dependency sớm: Spring phải tạo dependency trước khi truyền nó vào constructor của bean cần dependency đó.

## 3. Dependency direction quan trọng hơn số lượng dependency

Một class có nhiều dependency chưa chắc đã tạo ra cycle. Ví dụ, một use case có thể phụ thuộc vào repository, clock và payment port:

~~~text
PlaceOrderUseCase
    ├──→ OrderRepository
    ├──→ InventoryPort
    ├──→ PaymentPort
    └──→ Clock
~~~

Graph này vẫn có thể là DAG nếu các dependency không quay ngược lại gọi use case.

Ngược lại, chỉ hai class cũng có thể tạo ra cycle:

~~~text
OrderService → InventoryService
      ↑               |
      └───────────────┘
~~~

Vì vậy, không nên đánh giá kiến trúc chỉ bằng số lượng field trong constructor hoặc số module. Cần xem **chiều phụ thuộc** và trách nhiệm của từng node.

Một quy tắc thực dụng: thành phần điều phối một use case có thể gọi các collaborator chuyên trách; các collaborator không nên gọi ngược lại thành phần điều phối chỉ để yêu cầu nó hoàn tất bước tiếp theo.

## 4. Tổ chức dependency theo layer

Một cấu trúc Spring Boot phổ biến chia ứng dụng thành các layer:

~~~text
┌──────────────────────────┐
│       Web / API          │
└────────────┬─────────────┘
             |
             v
┌──────────────────────────┐
│     Application          │
│  Use cases / Services    │
└────────────┬─────────────┘
             |
             v
┌──────────────────────────┐
│        Domain            │
│ Entities / Value Objects │
└──────────────────────────┘

Infrastructure adapters implement
các port mà Application/Domain định nghĩa.
~~~

Một hướng phụ thuộc thường gặp:

- Web phụ thuộc Application để gọi use case.
- Application phụ thuộc Domain và các port mà nó cần.
- Infrastructure phụ thuộc vào contract/port để triển khai persistence, messaging hoặc remote API.
- Domain không phụ thuộc Web, database framework hoặc client cụ thể.

Ví dụ package:

~~~text
com.example.orders
├── web
│   └── OrderController.java
├── application
│   ├── PlaceOrderUseCase.java
│   └── port
│       └── out
│           ├── OrderRepository.java
│           └── PaymentPort.java
├── domain
│   ├── Order.java
│   └── OrderPolicy.java
└── infrastructure
    ├── persistence
    │   └── JpaOrderRepository.java
    └── payment
        └── HttpPaymentAdapter.java
~~~

Đây là một cách tổ chức minh họa; dự án có thể dùng package theo feature hoặc module riêng. Điều quan trọng là giữ quy tắc phụ thuộc rõ ràng.

### Runtime call flow có thể ngược compile-time dependency

Một điểm dễ nhầm trong kiến trúc ports-and-adapters:

- Application gọi một interface `PaymentPort`.
- Adapter bên ngoài implement interface đó.
- Application không import class `HttpPaymentAdapter`.

Quan hệ compile-time:

~~~text
Application → PaymentPort
HttpPaymentAdapter → PaymentPort
HttpPaymentAdapter → HTTP client
~~~

Luồng thực thi runtime:

~~~text
PlaceOrderUseCase
        |
        v
     PaymentPort
        |
        v
HttpPaymentAdapter
        |
        v
   Payment API
~~~

Spring inject implementation của port vào use case. Runtime control flow đi qua adapter, nhưng source dependency vẫn hướng vào contract được định nghĩa ở phía trong.

Đây là Dependency Inversion Principle (DIP): module cấp cao phụ thuộc abstraction; implementation chi tiết cũng phụ thuộc abstraction đó.

## 5. Vòng phụ thuộc trong Spring bean graph

Spring container tạo và quản lý bean dựa trên dependency được khai báo qua constructor, setter, field, factory method và các cơ chế khác.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;

    public OrderService(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    public void placeOrder() {
        inventoryService.reserveStock();
    }
}
~~~

~~~java
@Service
public class InventoryService {

    private final OrderService orderService;

    public InventoryService(OrderService orderService) {
        this.orderService = orderService;
    }

    public void reserveStock() {
        // Kiểm tra và giữ hàng.
        orderService.markInventoryReserved();
    }
}
~~~

Graph:

~~~text
OrderService → InventoryService
      ^                |
      |                v
      └────────────────┘
~~~

Để tạo `OrderService`, Spring cần `InventoryService`. Để tạo `InventoryService`, Spring lại cần `OrderService`. Hai constructor không thể hoàn thành theo thứ tự thông thường.

Trong trường hợp constructor circular dependency, ứng dụng thường thất bại khi tạo ApplicationContext với lỗi dạng `BeanCurrentlyInCreationException`, thường được bọc trong một exception khởi tạo bean khác.

### Vì sao constructor injection làm lộ cycle?

Với constructor injection, object chỉ được tạo khi mọi tham số constructor đã sẵn sàng:

~~~text
Create OrderService
       |
       v
Need InventoryService
       |
       v
Create InventoryService
       |
       v
Need OrderService
       |
       v
OrderService is not created yet
       |
       v
Circular creation failure
~~~

Đây là tín hiệu hữu ích. Nó cho thấy hai object yêu cầu nhau ngay trong quá trình xây dựng, thường là một dấu hiệu thiết kế cần xem lại.

Constructor injection cũng giúp dependency trở nên tường minh, hỗ trợ field `final` và ngăn bean được tạo ở trạng thái thiếu dependency.

## 6. Vì sao field hoặc setter injection đôi khi che được cycle?

Spring có cơ chế hỗ trợ một số circular reference giữa singleton bean bằng cách expose một tham chiếu sớm tới bean đang được tạo. Với field/setter injection, trong một số trường hợp container có thể tạo instance trước rồi mới inject dependency còn lại.

Ví dụ:

~~~java
@Service
public class OrderService {

    @Autowired
    private InventoryService inventoryService;
}
~~~

~~~java
@Service
public class InventoryService {

    @Autowired
    private OrderService orderService;
}
~~~

Cơ chế này có giới hạn và phụ thuộc vào loại bean, vòng đời, proxy và cách tạo bean. Nó không phải giải pháp tổng quát cho mọi vòng phụ thuộc.

Trong các phiên bản Spring Boot hiện đại, circular references bị từ chối theo mặc định. Từ Spring Boot 2.6, property `spring.main.allow-circular-references` mặc định là `false`. Nếu bật lại, một số vòng singleton có thể được xử lý bằng early references, nhưng constructor cycle vẫn không thể được giải quyết theo cách đó.

Không nên đổi từ constructor injection sang field injection chỉ để làm startup pass. Điều này có thể che dấu cycle và làm dependency graph khó hiểu hơn.

### Cấu hình cho phép circular references

Có thể gặp cấu hình:

~~~yaml
spring:
  main:
    allow-circular-references: true
~~~

Đây là một cơ chế tương thích cho một số ứng dụng cũ đang có vòng singleton có thể xử lý bằng early reference. Nó không làm kiến trúc hết phụ thuộc vòng và không đảm bảo mọi loại cycle sẽ khởi tạo được.

Nếu phải bật property tạm thời để nâng cấp ứng dụng cũ, nên ghi nhận vòng cụ thể, tạo kế hoạch refactor và kiểm tra lại sau khi loại bỏ dependency cycle. Không nên dùng nó như một quy ước thiết kế mới.

## 7. Phân biệt cycle ở các cấp độ khác nhau

Từ “circular dependency” có thể chỉ nhiều vấn đề:

| Cấp độ | Ví dụ | Công cụ/biểu hiện |
|---|---|---|
| Class/package | Package A import B, B import A | Code review, ArchUnit |
| Spring bean | Bean A inject B, B inject A | ApplicationContext startup, BeanCurrentlyInCreationException |
| Module/build | Gradle project A phụ thuộc B, B phụ thuộc A | Build graph hoặc Maven reactor lỗi |
| Runtime service | Service A gọi B, B gọi lại A qua HTTP | Trace, network flow, integration behavior |
| Event/workflow | Event A kích hoạt B rồi B phát event kích hoạt lại A | Event trace, retry loop, business workflow |

Giải pháp phải đúng cấp độ. Bật CGLIB không sửa cycle giữa Gradle modules. Tách Maven dependency không tự giải quyết hai Spring bean đang inject nhau trong cùng module. Đổi event không nhất thiết loại bỏ cycle nếu event handler vẫn gọi ngược theo vòng lặp runtime.

## 8. Giải pháp thứ nhất: đưa orchestration vào một use case riêng

Một nguyên nhân phổ biến của cycle là hai service nghiệp vụ gọi ngược nhau để điều phối một quy trình.

Ví dụ, `OrderService` cần reserve stock và `InventoryService` lại gọi ngược `OrderService` để cập nhật trạng thái. Thay vì để hai service điều phối lẫn nhau, tạo một use case đứng phía trên:

~~~text
             PlaceOrderUseCase
                /       \
               v         v
        OrderService  InventoryService
               |         |
               v         v
          OrderRepository
                    InventoryRepository
~~~

Code minh họa:

~~~java
@Service
public class PlaceOrderUseCase {

    private final OrderService orderService;
    private final InventoryService inventoryService;

    public PlaceOrderUseCase(
            OrderService orderService,
            InventoryService inventoryService) {
        this.orderService = orderService;
        this.inventoryService = inventoryService;
    }

    public void place(PlaceOrderCommand command) {
        Order order = orderService.createPending(command);

        inventoryService.reserve(
                order.getId(),
                order.getItems()
        );

        orderService.confirm(order.getId());
    }
}
~~~

`OrderService` chỉ quản lý quy tắc và trạng thái đơn hàng:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order createPending(PlaceOrderCommand command) {
        Order order = Order.pending(command);
        return repository.save(order);
    }

    public void confirm(OrderId id) {
        Order order = repository.getRequired(id);
        order.confirm();
        repository.save(order);
    }
}
~~~

`InventoryService` chỉ quản lý tồn kho:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public void reserve(OrderId orderId, List<OrderItem> items) {
        // Kiểm tra và giữ hàng theo chính sách tồn kho.
    }
}
~~~

Hai service không còn inject lẫn nhau. `PlaceOrderUseCase` sở hữu trình tự phối hợp của use case.

Nếu hai bước dùng chung một database và yêu cầu atomicity, có thể đặt transaction boundary phù hợp ở application service. Nếu inventory nằm ở hệ thống khác, một transaction local không thể bảo đảm rollback xuyên hệ thống; khi đó cần thiết kế workflow phân tán như saga hoặc outbox.

## 9. Giải pháp thứ hai: trích xuất logic dùng chung thành abstraction riêng

Đôi khi cycle xuất hiện vì hai service cùng cần một quy tắc hoặc dữ liệu, nhưng một service lại giữ logic mà service kia cần.

Ví dụ:

~~~text
PricingService → CustomerService
      ^                 |
      |_________________|
~~~

Thay vì để hai service gọi nhau, hãy tìm ra khái niệm thực sự dùng chung, rồi đưa nó vào một thành phần có trách nhiệm riêng.

Nếu cả hai cần kiểm tra khách hàng có đủ điều kiện nhận ưu đãi, có thể tạo `CustomerEligibilityPolicy`:

~~~java
public interface CustomerEligibilityPolicy {
    boolean isEligible(CustomerId customerId);
}
~~~

Implementation có thể phụ thuộc vào repository hoặc dữ liệu domain cần thiết:

~~~java
@Service
public class DefaultCustomerEligibilityPolicy
        implements CustomerEligibilityPolicy {

    private final CustomerRepository repository;

    public DefaultCustomerEligibilityPolicy(
            CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean isEligible(CustomerId customerId) {
        Customer customer = repository.getRequired(customerId);
        return customer.isEligibleForPromotion();
    }
}
~~~

Các service sử dụng abstraction:

~~~java
@Service
public class PricingService {

    private final CustomerEligibilityPolicy eligibility;

    public PricingService(CustomerEligibilityPolicy eligibility) {
        this.eligibility = eligibility;
    }
}
~~~

~~~java
@Service
public class CustomerService {

    private final CustomerEligibilityPolicy eligibility;

    public CustomerService(CustomerEligibilityPolicy eligibility) {
        this.eligibility = eligibility;
    }
}
~~~

Graph mới:

~~~text
PricingService ────────┐
                       v
          CustomerEligibilityPolicy
                       ^
CustomerService ───────┘
                       |
                       v
              CustomerRepository
~~~

Cần chú ý vị trí đặt abstraction. Nếu policy thuộc nghiệp vụ khách hàng, nên đặt ở module/domain sở hữu khái niệm đó hoặc ở một contract layer phù hợp. Không nên đưa mọi thứ vào một package `common` chỉ để phá cycle; module dùng chung cần có trách nhiệm và chủ sở hữu rõ ràng.

## 10. Giải pháp thứ ba: đảo chiều phụ thuộc bằng Dependency Inversion

Một cycle thường xuất hiện khi module cấp cao phụ thuộc trực tiếp implementation ở module cấp thấp, trong khi implementation lại cần gọi ngược module cấp cao.

Ví dụ chưa tốt:

~~~text
OrderApplicationService → HttpPaymentAdapter
HttpPaymentAdapter → OrderApplicationService
~~~

Thay vì application phụ thuộc adapter, hãy định nghĩa port ở phía application:

~~~java
package com.example.orders.application.port.out;

public interface PaymentPort {
    PaymentResult authorize(PaymentRequest request);
}
~~~

Use case phụ thuộc vào port:

~~~java
package com.example.orders.application;

import com.example.orders.application.port.out.PaymentPort;

@Service
public class PlaceOrderService {

    private final PaymentPort paymentPort;

    public PlaceOrderService(PaymentPort paymentPort) {
        this.paymentPort = paymentPort;
    }

    public PaymentResult pay(PaymentRequest request) {
        return paymentPort.authorize(request);
    }
}
~~~

Adapter phụ thuộc vào port và cung cấp implementation:

~~~java
package com.example.orders.infrastructure.payment;

import com.example.orders.application.port.out.PaymentPort;

@Component
public class HttpPaymentAdapter implements PaymentPort {

    private final PaymentHttpClient client;

    public HttpPaymentAdapter(PaymentHttpClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        return client.authorize(request);
    }
}
~~~

Graph compile-time:

~~~text
PlaceOrderService → PaymentPort
HttpPaymentAdapter → PaymentPort
HttpPaymentAdapter → PaymentHttpClient
~~~

Không còn cạnh `PlaceOrderService → HttpPaymentAdapter`. Spring có thể inject adapter vào port khi khởi tạo context, nhưng application chỉ biết abstraction.

Đây là một ứng dụng của DIP và kiến trúc ports-and-adapters (hexagonal architecture).

### Đừng đặt port ở sai phía chỉ để đổi chiều mũi tên

Nếu port được định nghĩa trong module infrastructure nhưng application phải import nó, application vẫn phụ thuộc vào module chi tiết. Abstraction cần thuộc về phía module sở hữu nhu cầu, hoặc một contract module ổn định được cả hai phía cùng phụ thuộc.

## 11. Giải pháp thứ tư: dùng event khi hai thành phần không cần gọi đồng bộ nhau

Nếu một service cần thông báo “đã hoàn tất” để thành phần khác phản ứng, có thể dùng event thay vì gọi trực tiếp ngược lại.

Ví dụ:

~~~text
OrderService
    |
    | publish OrderPlaced
    v
Application event bus
    |
    +------> Inventory handler
    |
    +------> Notification handler
    |
    +------> Analytics handler
~~~

Định nghĩa event:

~~~java
public record OrderPlaced(
        OrderId orderId,
        List<OrderItem> items
) {
}
~~~

Publisher:

~~~java
@Service
public class PlaceOrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    public PlaceOrderService(
            OrderRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    public Order place(PlaceOrderCommand command) {
        Order order = repository.save(Order.create(command));

        events.publishEvent(
                new OrderPlaced(order.getId(), order.getItems())
        );

        return order;
    }
}
~~~

Listener:

~~~java
@Component
public class InventoryOrderListener {

    private final InventoryService inventoryService;

    public InventoryOrderListener(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @EventListener
    public void on(OrderPlaced event) {
        inventoryService.reserve(
                event.orderId(),
                event.items()
        );
    }
}
~~~

`PlaceOrderService` không cần biết `InventoryService`. Nó chỉ phát ra một sự kiện biểu đạt điều đã xảy ra.

### Event không tự động giải quyết mọi coupling

Event tạo ra một contract mới và có thể làm giảm direct dependency, nhưng cần cân nhắc:

- Ai sở hữu schema và ý nghĩa của event?
- Listener có chạy đồng bộ hay bất đồng bộ?
- Nếu listener lỗi, event có được retry không?
- Có chấp nhận eventual consistency không?
- Event có thể được xử lý nhiều lần không?
- Có cần idempotency không?
- Event có phải được phát sau khi database commit không?

Với Spring application event, listener thông thường có thể chạy trong cùng luồng publish. Dùng `@Async` làm thay đổi thời điểm và thread; không được giả định sự kiện sẽ tự được lưu bền vững.

Nếu cần xử lý sau commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    // Xử lý sau khi transaction chứa event đã commit.
}
~~~

`@TransactionalEventListener` cần transaction đang hoạt động và có thể được cấu hình fallback behavior theo yêu cầu. Nếu ứng dụng phải bảo đảm event không bị mất giữa database commit và việc gửi message, hãy xem xét transactional outbox thay vì chỉ dựa vào in-memory event publisher.

### Tránh event tạo vòng lặp nghiệp vụ

Một chuỗi event vẫn có thể tạo vòng runtime:

~~~text
OrderPlaced
   → InventoryReserved
      → OrderUpdated
         → OrderPlaced
            → ...
~~~

Đổi direct method call thành event không đủ nếu workflow phát lại event cũ hoặc listener không phân biệt trạng thái chuyển tiếp. Hãy thiết kế event theo sự kiện đã xảy ra, trạng thái trước/sau và quy tắc idempotency.

## 12. Tách query khỏi command và tránh gọi ngược để lấy dữ liệu

Một số cycle xuất hiện vì service vừa cập nhật trạng thái vừa hỏi service khác lấy dữ liệu mà nó thực sự cần cho quyết định.

Ví dụ, `InventoryService` gọi `OrderService.getOrder()` để đọc các dòng hàng, trong khi `OrderService` lại gọi `InventoryService.reserve()`.

Nếu inventory chỉ cần danh sách item và order ID, hãy truyền dữ liệu cần thiết qua command:

~~~java
public record ReserveInventoryCommand(
        OrderId orderId,
        List<InventoryItemRequest> items
) {
}
~~~

Use case chuẩn bị command:

~~~java
inventoryService.reserve(
        new ReserveInventoryCommand(order.getId(), toRequests(order))
);
~~~

Inventory không cần biết `OrderService` hoặc truy vấn ngược lại order. Nó chỉ xử lý contract mô tả dữ liệu cần cho nghiệp vụ tồn kho.

Không nên truyền cả một object entity lớn xuyên module nếu module kia chỉ cần vài giá trị. Dùng command/query DTO hoặc value object giúp ranh giới phụ thuộc rõ và tránh module chi tiết truy cập quá sâu vào aggregate của module khác.

## 13. Giữ Domain không phụ thuộc Spring hoặc Infrastructure

Trong kiến trúc phân lớp hoặc hexagonal, domain nên tập trung vào quy tắc nghiệp vụ:

~~~java
public class Order {

    private final OrderId id;
    private OrderStatus status;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                    "Only pending orders can be confirmed"
            );
        }

        status = OrderStatus.CONFIRMED;
    }
}
~~~

Domain không cần biết:

- `@RestController`.
- `JpaRepository`.
- `WebClient` hoặc `RestClient`.
- `ApplicationContext`.
- `@Autowired`.
- Cấu hình datasource.
- Cách triển khai cache hoặc message broker.

Các adapter ở ngoài chuyển dữ liệu và lời gọi qua các port.

~~~text
         Web Adapter
              |
              v
      Application Use Case
              |
              v
            Domain
              ^
              |
    Repository / API Ports
              ^
              |
       Infrastructure
~~~

Trong source code, infrastructure có thể import contract được định nghĩa trong application/domain. Nhưng domain không import infrastructure.

Đây là cách tránh cycle kiểu:

~~~text
Order domain → JPA entity adapter → Order domain
~~~

Nếu domain cần interface repository, hãy xác định vị trí interface theo ranh giới kiến trúc; implementation persistence nằm ở infrastructure.

## 14. Không tạo module common để che giấu cycle

Khi phát hiện hai module A và B phụ thuộc nhau, một phản ứng thường thấy là chuyển một số class vào module `common`:

~~~text
Module A → Common ← Module B
~~~

Cách này có thể hợp lý nếu Common thực sự chứa contract hoặc value object ổn định được nhiều module dùng. Nhưng nếu Common trở thành nơi tập hợp mọi class không biết đặt ở đâu, nó sẽ dần trở thành một module trung tâm với coupling rất lớn.

Trước khi tạo module dùng chung, hãy hỏi:

1. Khái niệm này thuộc nghiệp vụ/module nào?
2. Có thực sự là contract được nhiều module sở hữu chung không?
3. Module nào có quyền thay đổi nó?
4. Có thể truyền value object hoặc command nhỏ thay vì chia sẻ toàn bộ implementation không?
5. Có thể để một use case điều phối hai module mà không cần module nào gọi ngược không?

Một module common tốt thường nhỏ, ổn định và có API rõ. Nó không nên phụ thuộc vào các module nghiệp vụ đang sử dụng nó.

## 15. Vòng phụ thuộc giữa Maven modules và Gradle projects

Circular dependency không chỉ tồn tại giữa Spring bean. Nó có thể xuất hiện ở build graph.

Ví dụ Gradle multi-project:

~~~text
:orders → :inventory
:inventory → :orders
~~~

Nếu hai Gradle project cần nhau theo kiểu project dependency trực tiếp, build graph có cycle và Gradle không thể lập thứ tự thực thi task theo cách thông thường.

Maven multi-module cũng cần reactor graph có thứ tự. Nếu module A khai báo dependency vào B và B lại khai báo dependency vào A trong cùng reactor, Maven không thể xác định thứ tự build hợp lệ và thường báo cycle giữa projects.

### Cách phá module cycle

- Tách contract ổn định thành module riêng nếu thật sự được nhiều module sở hữu chung.
- Chuyển một chiều phụ thuộc thành interface/port ở module phía trong.
- Hợp nhất hai module nếu chúng không có ranh giới độc lập có ý nghĩa.
- Tách adapter triển khai sang module ngoài.
- Dùng event hoặc message contract nếu hai module cần giao tiếp lỏng hơn.

Ví dụ:

~~~text
Trước:
orders → inventory
inventory → orders

Sau:
orders → inventory-contract
inventory → inventory-contract
~~~

Hoặc nếu module inventory cần phát sự kiện cho orders:

~~~text
orders → order-contract
inventory → order-contract
~~~

Contract module nên chứa API/schema ổn định, không chứa service implementation hoặc Spring configuration của cả hai phía.

### Phân biệt build graph với dependency tree

`mvn dependency:tree` và `gradle dependencies` hiển thị các dependency artifact đã resolve. Chúng hữu ích để thấy thư viện nào kéo module nào vào, nhưng không phải công cụ đầy đủ để phát hiện mọi cycle trong source package hoặc Spring bean graph.

Hãy dùng đúng công cụ theo cấp độ:
- Maven/Gradle project graph cho quan hệ module build.
- ArchUnit hoặc công cụ architecture test cho package/class dependency.
- Startup stack trace và Spring context test cho bean dependency.
- Distributed tracing/log correlation cho lời gọi giữa service runtime.

## 16. Chẩn đoán vòng phụ thuộc trong Spring Boot

Khi ứng dụng không khởi động, hãy tìm các dấu hiệu như:

~~~text
The dependencies of some of the beans in the application context form a cycle
~~~

Hoặc:

~~~text
BeanCurrentlyInCreationException:
Requested bean is currently in creation
~~~

Thông báo cụ thể phụ thuộc phiên bản Spring và đường tạo bean. Một vòng có thể đi qua nhiều bean:

~~~text
AService
  → BService
      → CService
          → AService
~~~

Không nhất thiết chỉ có hai class.

### Bước 1 — Đọc đường dẫn cycle

Startup failure analysis có thể hiển thị chuỗi bean. Ghi lại từng cạnh theo dạng:

~~~text
AService → BService
BService → CService
CService → AService
~~~

Đừng chỉ xóa một injection ở cuối stack trace mà chưa xác định trách nhiệm của mỗi bean.

### Bước 2 — Xác định dependency có thực sự cần không

Có thể một bean gọi bean khác chỉ để:
- Đọc một field hoặc trạng thái nhỏ.
- Gửi notification.
- Ghi audit.
- Cập nhật một trạng thái thuộc module khác.
- Lấy dữ liệu mà caller có thể truyền qua command.

Nếu vậy, có thể tách port, value object, event hoặc use case điều phối.

### Bước 3 — Xem bean được tạo từ đâu

Tìm:
- `@Component`, `@Service`, `@Repository`.
- `@Bean` factory method.
- `@Import` và component scanning.
- `@Profile` và `@ConditionalOnProperty`.
- `@Lazy`, scoped proxy hoặc FactoryBean.
- Test configuration thay thế bean.

Một bean có thể được đăng ký từ cấu hình khác mà không nằm trong class đang xem.

### Bước 4 — Kiểm tra constructor graph

Constructor injection làm dependency hiển thị rõ. Có thể lập bảng:

| Bean | Constructor dependency |
|---|---|
| OrderService | OrderRepository, InventoryService |
| InventoryService | InventoryRepository, PricingService |
| PricingService | CustomerService |
| CustomerService | OrderService |

Đường cycle: `OrderService → InventoryService → PricingService → CustomerService → OrderService`.

Bảng này giúp xác định một use case hoặc abstraction bị đặt sai trách nhiệm.

### Bước 5 — Viết test context nhỏ

Có thể dùng `ApplicationContextRunner` hoặc context test phù hợp để tái hiện bean graph cần thiết. Test nhỏ giúp xác nhận cycle được loại bỏ mà không phải khởi động toàn bộ ứng dụng và mọi dịch vụ ngoài.

Nếu cycle chỉ xảy ra trong một profile, hãy cung cấp đúng property/profile trong test. Không nên tắt một nửa ứng dụng rồi kết luận graph production đã hợp lệ.

## 17. @Lazy và ObjectProvider: khi nào nên dùng?

Có những tình huống một dependency thực sự cần được resolve trễ, chẳng hạn một integration optional chỉ được gọi trong một nhánh hiếm hoặc một thành phần có lifecycle khác.

### Dùng @Lazy ở injection point

~~~java
@Service
public class ReportService {

    private final ExportService exportService;

    public ReportService(@Lazy ExportService exportService) {
        this.exportService = exportService;
    }
}
~~~

`@Lazy` ở injection point có thể cung cấp một proxy trì hoãn việc resolve target cho tới khi được sử dụng. Điều này có thể phá một số vòng khởi tạo vì hai bean không cần tạo target của nhau ngay lập tức.

Tuy nhiên, nếu hai service phụ thuộc chặt chẽ vào nhau để thực hiện mọi nghiệp vụ, cycle vẫn còn ở mức thiết kế. Lỗi có thể chỉ chuyển từ startup sang thời điểm method được gọi, hoặc phát sinh vấn đề khác về lifecycle.

### Dùng ObjectProvider

~~~java
@Service
public class AuditCoordinator {

    private final ObjectProvider<AuditService> auditServiceProvider;

    public AuditCoordinator(
            ObjectProvider<AuditService> auditServiceProvider) {
        this.auditServiceProvider = auditServiceProvider;
    }

    public void recordIfEnabled(AuditRecord record) {
        AuditService auditService =
                auditServiceProvider.getIfAvailable();

        if (auditService != null) {
            auditService.record(record);
        }
    }
}
~~~

`ObjectProvider<T>` cho phép resolve dependency khi cần, kiểm tra có bean hay không và chọn một số cách truy cập linh hoạt.

Cách này phù hợp khi dependency thực sự optional hoặc cần lazy lookup theo lifecycle. Không nên dùng nó để giấu một dependency bắt buộc trong constructor chỉ nhằm làm cho ApplicationContext khởi động được.

### Khi nào không nên dùng?

Không nên thêm `@Lazy` hoặc `ObjectProvider` nếu mục tiêu duy nhất là tránh sửa hai service đang gọi lẫn nhau. Hãy xem lại use case, ownership của dữ liệu và chiều điều phối trước.

## 18. Event, callback và vòng lặp runtime

Một đồ thị bean có thể không có cycle nhưng runtime workflow vẫn có thể tạo vòng lặp vô hạn.

Ví dụ:

~~~text
OrderPlaced event
    → Inventory handler
        → StockReserved event
            → Order handler
                → OrderUpdated event
                    → Inventory handler
                        → ...
~~~

Điều này có thể xảy ra dù từng listener không inject ngược nhau. Vì vậy, cần phân biệt:

- **Bean dependency cycle:** Spring không thể tạo graph bean theo dependency.
- **Compile-time dependency cycle:** module/package phụ thuộc vòng.
- **Runtime call cycle:** các component gọi qua lại trong quá trình xử lý.
- **Event feedback loop:** event được phát sinh lại theo chuỗi không có điều kiện dừng.

Để xử lý runtime loop:

- Định nghĩa event biểu đạt sự kiện đã xảy ra, không chỉ là lệnh mơ hồ.
- Phân biệt event type và command type.
- Theo dõi correlation ID và causation ID.
- Thiết kế handler idempotent.
- Xác định trạng thái nào được phép phát event tiếp theo.
- Có retry limit và dead-letter strategy cho message broker.
- Tránh listener phát lại cùng event mà không có thay đổi nghiệp vụ mới.

Event-driven architecture làm giảm direct coupling nhưng đòi hỏi quản lý workflow và eventual consistency có chủ đích.

## 19. Kiểm soát dependency direction bằng ArchUnit

Quy tắc kiến trúc không nên chỉ nằm trong tài liệu. Có thể dùng ArchUnit để kiểm tra dependency giữa package hoặc module trong test.

Ví dụ dependency Gradle:

~~~groovy
dependencies {
    testImplementation 'com.tngtech.archunit:archunit-junit5:<version>'
}
~~~

Thay `<version>` bằng phiên bản ArchUnit được dự án quản lý.

### Ngăn domain phụ thuộc infrastructure

~~~java
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class DomainDependencyTest {

    @Test
    void domainMustNotDependOnInfrastructure() {
        JavaClasses classes = new ClassFileImporter()
                .importPackages("com.example");

        ArchRule rule = noClasses()
                .that().resideInAPackage("..domain..")
                .should().dependOnClassesThat()
                .resideInAPackage("..infrastructure..");

        rule.check(classes);
    }
}
~~~

Test này kiểm tra source-level dependency: class trong package domain không được phụ thuộc class trong package infrastructure.

Nó không kiểm tra mọi quan hệ runtime hoặc remote service; cần xem phạm vi import và các loại dependency mà ArchUnit phân tích.

### Phát hiện cycle giữa các package slice

Có thể kiểm tra các slice cấp module:

~~~java
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

@AnalyzeClasses(packages = "com.example")
class ModuleCycleTest {

    @ArchTest
    static final ArchRule modulesShouldBeFreeOfCycles =
            slices()
                    .matching("com.example.(*)..")
                    .should()
                    .beFreeOfCycles();
}
~~~

Pattern `com.example.(*)..` nhóm package con theo slice. Ví dụ `orders`, `inventory` và `payments` có thể trở thành các slice được kiểm tra.

Nếu một module con phụ thuộc module khác và module kia phụ thuộc ngược, ArchUnit có thể báo cycle. Hãy điều chỉnh pattern theo package layout thực tế; nếu cấu trúc package không phản ánh module boundary, rule có thể nhóm sai hoặc không kiểm tra đúng phạm vi.

### Kiến trúc layer rõ ràng

Ngoài cycle, có thể kiểm tra layer dependency:

~~~java
@ArchTest
static final ArchRule layersAreRespected =
        layeredArchitecture()
                .consideringAllDependencies()
                .layer("Web").definedBy("..web..")
                .layer("Application").definedBy("..application..")
                .layer("Domain").definedBy("..domain..")
                .layer("Infrastructure").definedBy("..infrastructure..")
                .whereLayer("Web").mayNotBeAccessedByAnyLayer()
                .whereLayer("Application").mayOnlyBeAccessedByLayers("Web",
                        "Infrastructure")
                .whereLayer("Domain").mayOnlyBeAccessedByLayers("Application",
                        "Web", "Infrastructure");
~~~

Đây là ví dụ minh họa DSL và quy tắc; các ràng buộc cụ thể phải phù hợp với dependency direction mà dự án lựa chọn. Với hexagonal architecture, infrastructure thường phụ thuộc vào port/application contract, còn domain không được phụ thuộc vào infrastructure. Hãy thiết kế layer rule sao cho phản ánh đúng mô hình, tránh copy một bộ rule không khớp kiến trúc thực tế.

ArchUnit có thể chạy trong CI như test thông thường. Khi một pull request tạo dependency ngược hoặc cycle mới, build sẽ báo lỗi trước khi thay đổi được hợp nhất.

## 20. Kiểm soát module bằng Spring Modulith

Với ứng dụng Spring Boot được tổ chức thành các application module, Spring Modulith có thể giúp xác định module boundary, kiểm tra quan hệ giữa module và kiểm thử một số quy tắc cấu trúc.

Một module có thể expose API được phép sử dụng; các package nội bộ còn lại được giữ encapsulated. Điều này giúp tránh tình trạng mọi module import trực tiếp mọi class implementation của nhau.

Ví dụ test verification ở mức ý tưởng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Cần thêm dependency Spring Modulith tương ứng và cấu hình module boundary theo phiên bản đang dùng. `Application` trong ví dụ là lớp main của ứng dụng.

Spring Modulith không thay thế thiết kế kiến trúc. Nó giúp biến các quy tắc module thành kiểm tra có thể chạy tự động, đặc biệt khi ứng dụng có nhiều module trong cùng một Spring Boot deployment.

## 21. Tổ chức package theo feature để giảm coupling

Một cấu trúc chỉ chia theo technical layer:

~~~text
com.example
├── controller
├── service
├── repository
├── entity
└── config
~~~

có thể khiến mọi feature trộn vào cùng package. Một feature mới dễ phải sửa nhiều khu vực và tạo dependency chéo.

Cách tổ chức theo feature:

~~~text
com.example
├── orders
│   ├── web
│   ├── application
│   ├── domain
│   └── infrastructure
├── inventory
│   ├── application
│   ├── domain
│   └── infrastructure
└── payments
    ├── application
    ├── domain
    └── infrastructure
~~~

Mỗi feature sở hữu trách nhiệm riêng. Khi module khác cần chức năng, nó sử dụng API/port được công bố thay vì import repository hoặc implementation nội bộ.

Không nhất thiết mỗi feature phải có đủ mọi package. Với module nhỏ, giữ cấu trúc đơn giản; chỉ tạo layer khi nó biểu đạt một ranh giới có ý nghĩa.

### Public API và internal implementation

Ví dụ module inventory có API:

~~~java
package com.example.inventory.api;

public interface InventoryReservation {
    ReservationResult reserve(ReservationRequest request);
}
~~~

Implementation nội bộ:

~~~java
package com.example.inventory.internal;

@Service
class InventoryReservationService implements InventoryReservation {
    // ...
}
~~~

Module khác phụ thuộc package API. Implementation được giữ package-private hoặc được kiểm soát qua module boundary phù hợp.

Cách này giúp thay đổi persistence hoặc thuật toán tồn kho mà không buộc module orders biết chi tiết nội bộ.

## 22. Một ví dụ refactor hoàn chỉnh từ cycle sang DAG

Giả sử code ban đầu:

~~~java
@Service
public class OrderService {

    private final InventoryService inventory;

    public OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    public void place(Order order) {
        inventory.reserve(order);
    }

    public void markReserved(OrderId id) {
        // Cập nhật trạng thái order.
    }
}
~~~

~~~java
@Service
public class InventoryService {

    private final OrderService orders;

    public InventoryService(OrderService orders) {
        this.orders = orders;
    }

    public void reserve(Order order) {
        // Kiểm tra stock...
        orders.markReserved(order.getId());
    }
}
~~~

Cycle xảy ra vì inventory gọi ngược order để hoàn tất workflow.

### Bước 1 — Xác định ai sở hữu trình tự

Đặt trình tự đặt hàng ở application use case:

~~~java
@Service
public class PlaceOrderUseCase {

    private final OrderService orders;
    private final InventoryService inventory;

    public PlaceOrderUseCase(
            OrderService orders,
            InventoryService inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    public void place(PlaceOrderCommand command) {
        Order order = orders.createPending(command);

        inventory.reserve(
                order.getId(),
                order.getItems()
        );

        orders.markReserved(order.getId());
    }
}
~~~

### Bước 2 — Giữ OrderService sở hữu trạng thái order

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order createPending(PlaceOrderCommand command) {
        return repository.save(Order.pending(command));
    }

    public void markReserved(OrderId id) {
        Order order = repository.getRequired(id);
        order.markReserved();
        repository.save(order);
    }
}
~~~

### Bước 3 — Giữ InventoryService sở hữu tồn kho

~~~java
@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public void reserve(
            OrderId orderId,
            List<OrderItem> items) {
        // Kiểm tra availability và reserve stock.
    }
}
~~~

### Bước 4 — Kiểm tra graph mới

~~~text
PlaceOrderUseCase
       |       |
       v       v
 OrderService  InventoryService
       |       |
       v       v
 OrderRepository
           InventoryRepository
~~~

Hai service chuyên trách không gọi nhau. Application use case là node điều phối. Dependency graph không còn vòng.

### Bước 5 — Xác định tính nhất quán

Nếu order và inventory cùng database, có thể xem xét một transaction boundary chung tùy mô hình persistence.

Nếu inventory là dịch vụ độc lập, việc reserve có thể thất bại sau khi order đã được tạo. Khi đó, cần trạng thái trung gian như `PENDING_INVENTORY`, compensation hoặc saga. Không nên giả định một `@Transactional` local có thể rollback dữ liệu của remote service.

### Bước 6 — Viết test cho trách nhiệm mới

- Unit test `PlaceOrderUseCase` kiểm tra trình tự gọi các collaborator.
- Unit test `OrderService` kiểm tra quy tắc trạng thái order.
- Unit test `InventoryService` kiểm tra chính sách tồn kho.
- Integration test kiểm tra adapter persistence hoặc API nếu cần.

Mỗi test tập trung vào một contract và không cần khởi tạo cả ba service thật nếu không phải mục tiêu của test.

## 23. Các anti-pattern thường tạo dependency cycle

### Hai service gọi nhau để điều phối

Nếu A gọi B rồi B gọi A để hoàn tất cùng một use case, có thể thiếu một application service đứng phía trên.

### Service nghiệp vụ gọi ngược controller

Controller là adapter nhận request. Domain/application service không nên phụ thuộc web controller để gọi ngược response hoặc lấy request data. Truyền dữ liệu cần thiết qua command/context.

### Repository phụ thuộc service

Repository nên tập trung persistence. Nếu repository inject service nghiệp vụ, thường là ranh giới trách nhiệm bị đảo ngược. Hãy để service gọi repository, không để repository điều phối service.

### Module thấp phụ thuộc module cao

Ví dụ domain import controller hoặc infrastructure import use case implementation cụ thể. Đưa contract về phía module sở hữu nhu cầu và để adapter implement contract đó.

### Shared utility chứa logic nghiệp vụ

Một package `common` hoặc `util` có thể dần phụ thuộc nhiều module. Hãy đặt logic ở module sở hữu khái niệm; utility chỉ nên chứa chức năng thực sự chung, ổn định và ít phụ thuộc.

### Dùng @Lazy cho mọi cycle

`@Lazy` có thể trì hoãn khởi tạo nhưng không làm hai trách nhiệm tách biệt hơn. Nếu mỗi service cần service kia trong hầu hết hoạt động, hãy refactor thay vì trì hoãn lỗi.

### Bật allow-circular-references toàn ứng dụng

Điều này làm những vòng singleton có thể xử lý bằng early reference tiếp tục tồn tại. Nó giảm tín hiệu phát hiện vấn đề và có thể khiến ứng dụng phụ thuộc vào hành vi khởi tạo mong manh.

### Dùng event cho mọi method call

Event phù hợp khi cần tách producer khỏi consumer hoặc thể hiện sự kiện nghiệp vụ. Nếu caller cần kết quả đồng bộ ngay lập tức, một interface call rõ ràng có thể đơn giản và dễ hiểu hơn.

## 24. Checklist thiết kế trước khi thêm dependency mới

Trước khi inject một bean vào service, hãy tự hỏi:

1. Bean này thuộc module nào và module đó có phải chủ sở hữu contract cần dùng không?
2. Caller cần API ổn định hay đang phụ thuộc implementation cụ thể?
3. Có đường phụ thuộc ngược từ module được inject trở lại caller không?
4. Có thể truyền dữ liệu cần thiết qua command/value object thay vì gọi ngược để đọc?
5. Có một use case/application service đang cần điều phối hai collaborator?
6. Logic dùng chung có thể được tách thành policy hoặc abstraction có chủ sở hữu rõ?
7. Đây là giao tiếp đồng bộ hay một sự kiện độc lập về thời gian?
8. Nếu dùng event, có cần retry, idempotency, outbox hoặc eventual consistency không?
9. Dependency có làm domain phụ thuộc framework hoặc infrastructure không?
10. Có thể viết architecture test để ngăn cycle tương tự xuất hiện lại không?

Một dependency mới không nhất thiết xấu. Nhưng nếu nó khiến module biết thêm quá nhiều chi tiết nội bộ hoặc cần gọi ngược, hãy xem lại ranh giới trước khi thêm constructor parameter.

## 25. Quy trình refactor khi đã có circular dependency

Khi phát hiện cycle trong code hiện hữu:

**1. Chụp lại graph hiện tại.** Liệt kê node và cạnh theo một chiều thống nhất `A → B` có nghĩa A phụ thuộc B.

**2. Xác định cycle ngắn nhất.** Tìm đường đi từ node quay lại chính nó. Nếu graph lớn, phân tích theo package/module trước, rồi xuống bean.

**3. Xác định trách nhiệm thực tế.** Tìm xem service nào đang điều phối workflow, service nào sở hữu quy tắc nghiệp vụ và service nào chỉ cung cấp hạ tầng.

**4. Chọn cách phá cycle theo bản chất.**
- Orchestration nằm sai chỗ: tạo application use case.
- Hai bên cần cùng một quy tắc: tách policy/contract.
- Dependency hướng vào implementation: đảo chiều bằng port.
- Giao tiếp không cần đồng bộ: cân nhắc event.
- Module không có boundary độc lập: hợp nhất hoặc phân chia lại module.

**5. Thay dependency theo từng bước.** Giữ API công khai ổn định nếu có thể, refactor implementation và cập nhật test cùng thay đổi.

**6. Kiểm tra lifecycle và transaction.** Đặc biệt nếu chuyển direct call sang event hoặc remote service, đánh giá commit, rollback, retry và consistency.

**7. Chạy test ở đúng tầng.** Unit test cho logic, context test cho bean graph, integration test cho adapter và architecture test cho dependency direction.

**8. Gỡ workaround.** Sau khi cycle được loại bỏ, bỏ `@Lazy` hoặc `allow-circular-references` nếu trước đó chỉ được dùng để né lỗi.

**9. Đưa quy tắc vào CI.** Dùng ArchUnit hoặc module verification để phát hiện dependency cycle mới.

## 26. Phân biệt lỗi tạo bean với lỗi gọi method

Một ứng dụng có thể khởi động thành công nhưng runtime vẫn có dependency loop theo nghĩa lời gọi qua lại. Ví dụ A gọi B, B gọi A theo một điều kiện không có điểm dừng. Đây không phải Spring bean circular creation.

Ngược lại, hai bean có thể tạo thành circular dependency ngay lúc startup dù các method không bao giờ gọi lẫn nhau. Chỉ cần constructor dependency tạo vòng là đủ.

| Tình huống | Khi phát hiện | Dấu hiệu |
|---|---|---|
| Constructor bean cycle | ApplicationContext startup | BeanCurrentlyInCreationException |
| Field/setter singleton cycle | Startup, tùy cấu hình | Có thể được xử lý hoặc bị từ chối |
| Runtime method recursion | Khi method được gọi | StackOverflowError hoặc call chain lặp |
| Event feedback loop | Khi event được xử lý | Event lặp, retry, message volume tăng |
| Module dependency cycle | Build configuration/build graph | Maven/Gradle không lập được build order |

Chẩn đoán đúng loại cycle giúp chọn đúng giải pháp. Không nên thay Spring bean scope hoặc proxy strategy khi vấn đề thực chất là runtime recursion.

## 27. Đo lường chất lượng dependency graph

Ngoài việc kiểm tra “có cycle hay không”, có thể xem thêm các dấu hiệu:

- Một module có quá nhiều module khác phụ thuộc vào nó.
- Một module phụ thuộc vào rất nhiều module không liên quan.
- Có package `common` thay đổi thường xuyên và được mọi feature import.
- Thay đổi nhỏ ở một module buộc nhiều module khác phải build/test lại.
- Các interface công khai lộ quá nhiều class infrastructure.
- Module domain phụ thuộc Spring/JPA/HTTP chỉ để dùng một vài annotation.
- Test cần load nhiều integration vì component boundary không rõ.

Không cần tối ưu mọi chỉ số thành một con số cố định. Hãy dùng dependency graph để hiểu coupling và tìm khu vực có thay đổi lan rộng hoặc ownership chưa rõ.

Một module ổn định, có contract nhỏ và ít phụ thuộc thường dễ tái sử dụng hơn module trung tâm chứa nhiều implementation.

## 28. Tóm tắt nguyên tắc thiết kế

Một dependency graph dễ hiểu thường có các đặc điểm:

- Mỗi cạnh có hướng và lý do rõ ràng.
- Module cấp cao phụ thuộc abstraction, không phụ thuộc implementation chi tiết.
- Domain giữ độc lập với web, persistence và framework.
- Application service điều phối use case; collaborator chuyên trách không gọi ngược để điều phối nhau.
- Event được dùng khi giao tiếp thực sự phù hợp với mô hình sự kiện và chấp nhận semantics tương ứng.
- Dependency giữa package/module được kiểm soát bằng architecture tests.
- Workaround như `@Lazy` hoặc cho phép circular references chỉ được dùng khi có lý do lifecycle cụ thể, không thay thế refactor.

**Hãy giữ quan hệ phụ thuộc có hướng rõ ràng và ưu tiên DAG ở các ranh giới kiến trúc.** Khi phát hiện vòng, xác định ai sở hữu use case, ai sở hữu quy tắc nghiệp vụ và abstraction nào cần được đặt đúng phía. Tách orchestration, đảo chiều dependency, truyền dữ liệu qua contract hoặc dùng event có chủ đích sẽ tạo ra graph dễ khởi tạo, dễ kiểm thử và dễ thay đổi hơn.

