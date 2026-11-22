# Phân chia giao thức, ca sử dụng, miền và tích hợp bên ngoài

## Mục tiêu bài học

Trong thiết kế Microservices, một dịch vụ tốt cần làm rõ đâu là phần tiếp nhận yêu cầu qua HTTP, gRPC hoặc message; đâu là phần điều phối một ca sử dụng; đâu là quy tắc nghiệp vụ cốt lõi; và đâu là mã giao tiếp với database, hệ thống thanh toán, email hoặc dịch vụ khác.

Nếu tất cả trộn vào controller, handler hoặc một lớp Service quá lớn, mỗi lần thay giao thức, nhà cung cấp, cấu trúc lưu trữ hay quy tắc nghiệp vụ đều dễ kéo theo sửa nhiều phần không liên quan. Điều đó làm code khó kiểm thử và gây phụ thuộc vào hạ tầng. Ngược lại, chia nhiều lớp nhưng để domain phụ thuộc trực tiếp vào HTTP, ORM hoặc SDK bên thứ ba cũng không giải quyết được vấn đề.

Bài này tập trung vào bốn nhóm trách nhiệm:

1. **Giao thức (protocol / inbound adapter):** giao tiếp với bên ngoài và chuyển dữ liệu giữa giao thức với lệnh truy cập ứng dụng.
2. **Ca sử dụng (application / use case):** điều phối quy trình để thực hiện một mục tiêu của người dùng hoặc hệ thống.
3. **Miền nghiệp vụ (domain):** biểu diễn khái niệm, hành vi và các bất biến phải luôn đúng.
4. **Tích hợp bên ngoài (outbound adapter / infrastructure):** hiện thực truy cập database, broker, dịch vụ khác, nhà cung cấp bên thứ ba và hạ tầng.

Sau bài này, bạn có thể:
- Phân biệt trách nhiệm từng lớp trong một service Spring Boot.
- Thiết kế luồng phụ thuộc một chiều qua port và adapter.
- Nhận diện chỗ nên đặt validation, authorization, transaction, idempotency, retry, mapping DTO và xử lý lỗi.
- Thiết kế use case dùng được từ REST, message consumer hoặc scheduler mà không nhân đôi nghiệp vụ.
- Giải thích ranh giới của một Microservice khác với ranh giới lớp bên trong Microservice.
- Vận dụng ví dụ đặt hàng và tích hợp thanh toán để tổ chức mã có thể kiểm thử và thay đổi.

## 1. Câu hỏi gốc: mỗi phần chịu trách nhiệm gì?

Hãy xét thao tác “khách hàng tạo đơn mua hàng”.

Một request HTTP gửi đến API:

~~~http
POST /orders
Content-Type: application/json
Idempotency-Key: request-123

{
  "customerId": "cus-17",
  "items": [
    {"sku": "SKU-01", "quantity": 2}
  ]
}
~~~

Hệ thống cần kiểm tra cấu trúc request, xác định người dùng có quyền tạo đơn, đánh giá điều kiện đặt hàng, chốt giá và tồn theo chính sách, lưu trạng thái và khởi tạo tác vụ tiếp theo. Một số việc có thể xảy ra đồng bộ, một số cần giao tiếp với dịch vụ ngoài hoặc xử lý bất đồng bộ.

Không nên biến controller thành nơi chứa toàn bộ quy tắc. Cũng không nên đưa tất cả vào một lớp OrderService vừa đọc JSON, gọi SDK, lưu JPA entity, vừa trả ResponseEntity. Một cách phân chia rõ ràng:

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Giao thức đầu vào | Yêu cầu đến bằng cách nào và trả kết quả theo giao thức nào? | REST controller, Kafka listener, gRPC handler |
| Ca sử dụng | Để hoàn thành thao tác, các bước nghiệp vụ và phụ thuộc cần được điều phối ra sao? | PlaceOrderUseCase, CancelOrderUseCase |
| Miền nghiệp vụ | Quy tắc nào phải đúng bất kể ai gọi và dữ liệu lưu ở đâu? | Order, OrderLine, chuyển trạng thái hợp lệ |
| Tích hợp đầu ra | Tương tác với thế giới bên ngoài được thực thi bằng công nghệ nào? | Postgres repository, Payment HTTP client, Kafka producer |

Sự phân chia này nói về **trách nhiệm bên trong một dịch vụ logic**. Nó không bắt buộc mỗi lớp chạy trong một process hoặc thành một Microservice riêng.

## 2. Sơ đồ luồng xử lý và hướng phụ thuộc

Mô hình Port and Adapter / Hexagonal có thể được diễn đạt như sau:

~~~text
           TÁC NHÂN / GIAO THỨC ĐẦU VÀO
       +-----------+-----------+-----------+
       | REST API  | gRPC      | Message   |
       | Controller| Handler   | Listener  |
       +-----+-----+-----+-----+-----+-----+
             |           |           |
             v           v           v
       +-----------------------------------+
       |         Application layer         |
       | PlaceOrder / CancelOrder use case |
       | Input command / Output result     |
       +--------------+--------------------+
                      |
               gọi domain
                      v
       +-----------------------------------+
       |             Domain                |
       | Order, invariants, domain rules   |
       +-----------------------------------+

       Application cần năng lực bên ngoài qua PORT
              /             |             \
             v              v              v
      OrderRepository  PaymentPort     EventPublisher
             ^              ^              ^
             | implements   | implements   | implements
      +------+-----+  +-----+--------+  +---+-----------+
      | Postgres    |  | PSP/HTTP     |  | Outbox/Kafka  |
      | adapter     |  | adapter      |  | adapter       |
      +-------------+  +--------------+  +---------------+
                 TÍCH HỢP ĐẦU RA
~~~

**Luồng chạy lúc runtime** có thể đi từ controller tới use case, tiếp tục đến domain và adapter database. Nhưng **hướng phụ thuộc mã nguồn** cần được quản lý khác: domain không phải import Spring MVC hay database driver; use case phụ thuộc hợp đồng trừu tượng của năng lực bên ngoài; adapter hạ tầng phụ thuộc port để hiện thực giao tiếp.

Thực tế có nhiều biến thể package và vị trí đặt interface. Điều quan trọng là các phụ thuộc được chọn có chủ đích, giữ quy tắc nghiệp vụ đủ độc lập với transport và công nghệ.

### 2.1. Phân biệt call flow với source dependency

Ví dụ:

~~~text
Runtime call:
OrderController → PlaceOrderUseCase → OrderRepositoryAdapter → Database

Compile-time dependency:
OrderController → Application API
PlaceOrderUseCase → OrderRepository port
OrderRepositoryAdapter → OrderRepository port + JPA
Domain → chỉ các dependency thuần cần thiết
~~~

Use case gọi phương thức save() của port. Adapter thực thi truy vấn SQL, nhưng ứng dụng không cần import EntityManager hay JdbcTemplate để thể hiện mục tiêu nghiệp vụ.

## 3. Lớp giao thức đầu vào: chuyển yêu cầu thành ý định ứng dụng

Giao thức là nơi hệ thống gặp những quy tắc của HTTP, gRPC, message broker, WebSocket hoặc scheduler. Nó cần hiểu **cơ chế truyền nhận** nhưng không nên sở hữu toàn bộ hành vi nghiệp vụ.

### 3.1. Những trách nhiệm phù hợp

- Khai báo HTTP route, method, status code, content type và response headers.
- Deserialization, schema validation và kiểm tra định dạng ở biên.
- Đọc identity, correlation ID, trace context, idempotency key và metadata kỹ thuật của request.
- Chuyển request DTO thành command/query cho application.
- Gọi use case phù hợp.
- Chuyển kết quả ứng dụng và lỗi thành response theo chuẩn giao thức.
- Với message consumer: decode event, xử lý envelope/header, acknowledgement hoặc negative acknowledgement theo chính sách transport.
- Với gRPC: ánh xạ request, response, metadata và status.
- Với scheduler: phát lệnh ứng dụng theo lịch, không nhân bản luật nghiệp vụ.

### 3.2. Việc không nên chứa trong controller/listener

- Tính toán giá, chiết khấu và quy tắc giữ tồn kho.
- Tự quyết định trạng thái đơn hàng có được chuyển từ PAID sang CANCELLED hay không.
- Thực hiện trực tiếp query JPA cho một chuỗi quy trình phức tạp nếu query đó là chi tiết persistence.
- Gọi Payment SDK và cài retry nghiệp vụ tùy tiện ngay trong endpoint.
- Để tên lỗi từ REST quyết định bản chất của domain exception.
- Copy/paste cùng quy tắc vào REST controller và Kafka listener.

Một dấu hiệu tốt: bạn có thể thêm một gRPC handler mà gần như chỉ viết mapping và gọi lại cùng use case; nghiệp vụ không cần viết lại.

### 3.3. Hai loại validation khác nhau

Ví dụ quantity gửi từ client:

- **Validation giao thức:** trường quantity có mặt không; JSON có đúng kiểu số nguyên không; payload có vượt giới hạn kích thước không?
- **Validation nghiệp vụ:** quantity có được phép lớn hơn 0; có vượt giới hạn mua theo chính sách; trạng thái khách hàng có được đặt hàng không?

Quy tắc nghiệp vụ quan trọng phải được **bảo vệ ở domain hoặc application theo ownership**, không chỉ dựa vào Bean Validation ở REST DTO. Lý do: cùng use case có thể được gọi qua message, CLI, test hoặc một adapter khác.

Bean Validation vẫn hữu ích để chặn request sai định dạng sớm. Có thể lặp lại ràng buộc cơ bản ở value object để bảo vệ bất biến tại điểm tạo domain model.

### 3.4. Authentication và authorization

- **Authentication:** xác định người gọi là ai; thường được thực hiện ở security filter/gateway hoặc protocol adapter.
- **Authorization ở lớp ứng dụng:** xác định người gọi có quyền thực hiện use case hay không; có thể dựa vào chính sách role, tenant, ownership hoặc trạng thái nghiệp vụ.
- **Domain rule:** quy tắc như “chỉ đơn ở trạng thái DRAFT được xác nhận” không nên biến thành rule riêng của HTTP.

Thông tin nhận dạng được chuyển vào use case dưới một abstraction phù hợp, chẳng hạn ActorContext hoặc PrincipalId. Tránh để domain import HttpServletRequest hoặc SecurityContextHolder nếu không thực sự cần.

## 4. Lớp application: ca sử dụng điều phối công việc

Use case trả lời “hệ thống sẽ làm gì để đạt mục tiêu này?”. Ví dụ:

- PlaceOrder: tiếp nhận lệnh tạo đơn.
- ConfirmPayment: áp dụng một kết quả thanh toán đã được xác thực.
- CancelOrder: đánh giá quyền hủy và ra lệnh chuyển trạng thái.
- ReserveStock: yêu cầu giữ lượng hàng theo hợp đồng nghiệp vụ.
- GetOrderDetails: kết hợp dữ liệu thành view cho người dùng.

### 4.1. Một use case thường có cấu trúc

~~~text
Input command / Query
          |
          v
Kiểm tra identity và điều kiện cấp ca sử dụng
          |
          v
Load dữ liệu qua port hoặc repository
          |
          v
Gọi domain model để đánh giá luật và chuyển trạng thái
          |
          v
Persist và tạo integration intent/event
          |
          v
Trả application result hoặc lỗi nghiệp vụ đã phân loại
~~~

Use case nên đủ cụ thể, có đầu vào/đầu ra rõ ràng. Việc đặt tên theo mục tiêu giúp tránh “God Service” chứa hàng trăm phương thức không liên quan.

### 4.2. Use case sở hữu điều phối, domain sở hữu bất biến

Ví dụ:
- Use case chọn phải load đơn hàng hiện tại, kiểm tra quyền, gọi Order.cancel() và save.
- Domain Order.cancel() kiểm tra trạng thái nào được chuyển sang CANCELLED, ghi lý do hủy, bảo vệ bất biến.

Nếu cùng một quy tắc chuyển trạng thái xuất hiện ở ba use case, hãy xem xét đưa nó vào domain entity/policy phù hợp. Nếu logic chỉ liên quan tới thứ tự gọi các cổng, transaction hoặc quyền của tác nhân trong luồng, nó thường thuộc application.

### 4.3. Có cần một use case cho mỗi endpoint?

Không nhất thiết. Một use case là **hành động có ý nghĩa nghiệp vụ**, không phải chỉ một URL hoặc một message topic. Hai endpoint khác giao thức có thể gọi chung một use case; một endpoint lớn có thể cần điều phối nhiều bước bằng một use case. Nhưng đừng tạo một use case tổng quát kiểu executeEverything() làm mất ý nghĩa hành động.

### 4.4. Application service có phụ thuộc Spring không?

Một số dự án dùng @Service, @Transactional và DI trực tiếp ở application để tối ưu tính thực dụng. Một số dự án giữ application thuần Java và đặt transaction ở decorator/adapter. Cả hai có thể phù hợp nếu dependency rules được định nghĩa rõ.

Điều cần tránh là application bị buộc biết HTTP response, cách bind JPA entity hoặc tên class từ SDK thanh toán bên ngoài. Annotation framework không tự động là vấn đề; **coupling khiến việc thay đổi khó khăn** mới cần kiểm soát.

## 5. Lớp domain: diễn đạt mô hình và bảo vệ bất biến

Domain chứa khái niệm và quy tắc đặc thù của nghiệp vụ:

- Entity có identity và hành vi.
- Value object bất biến biểu diễn giá trị như Money, Address, Quantity.
- Aggregate và aggregate root bảo vệ các invariant trong transaction boundary phù hợp.
- Domain service/policy cho quy tắc nghiệp vụ không thuộc tự nhiên vào một entity.
- Domain event mô tả sự kiện đã xảy ra về mặt nghiệp vụ.

Ví dụ một đơn hàng đang ở trạng thái PAID không được chuyển ngược về DRAFT. Đây là quy tắc của miền Ordering và cần được áp dụng cho mọi đường truy cập, không phụ thuộc request đến từ REST hay Kafka.

### 5.1. Ví dụ entity tập trung vào hành vi

~~~java
public enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}

public final class Order {
    private final String id;
    private OrderStatus status;

    public Order(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("order id is required");
        }
        this.id = id;
        this.status = OrderStatus.DRAFT;
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only draft orders may be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status == OrderStatus.CANCELLED) {
            return; // idempotent theo quy tắc minh họa
        }
        if (status == OrderStatus.CONFIRMED) {
            throw new IllegalStateException(
                    "Confirmed orders require a separate cancellation flow");
        }
        status = OrderStatus.CANCELLED;
    }

    public String id() { return id; }
    public OrderStatus status() { return status; }
}
~~~

Ví dụ chỉ minh họa bất biến trạng thái. Trong hệ thống thật, lựa chọn transition, versioning và rollback phải đến từ domain expert; việc gọi cancel() nhiều lần có nên idempotent hay báo lỗi cũng là quyết định nghiệp vụ.

### 5.2. Domain không nên biết công nghệ truyền nhận

Những biểu hiện coupling cần hạn chế:
- Order.confirm(HttpServletRequest request).
- PricingPolicy.apply(StripePaymentIntent paymentIntent).
- Order.onEvent(KafkaConsumerRecord record).
- Inventory.reserve(JpaRepository entityRepository).
- Domain entity ném ResponseStatusException để tự gán HTTP 409.

Thay vì vậy, use case/adapter chuyển dữ liệu transport và SDK sang value object, command hoặc domain type. Domain có thể ném exception/return result mang ý nghĩa nghiệp vụ; adapter giao thức quyết định ánh xạ sang HTTP/gRPC status.

### 5.3. Domain event khác integration event

Một domain event như OrderConfirmed có thể được phát sinh từ mô hình để mô tả kết quả nghiệp vụ. Integration event như order.confirmed.v1 là **hợp đồng công khai giữa các dịch vụ**, cần version, schema, khả năng tương thích và dữ liệu tối thiểu.

Không nên mặc định serialize nguyên domain event/entity ra Kafka. Một mapper/publisher trong application hoặc adapter sẽ chuyển mô hình nội bộ sang external contract có chủ đích.

## 6. Lớp tích hợp bên ngoài: thực thi các hợp đồng kỹ thuật

Bất cứ khi nào use case cần gọi thứ gì nằm ngoài logic cốt lõi, hãy cân nhắc mô tả năng lực đó bằng port:

- OrderStore / OrderRepository: tải và lưu aggregate.
- InventoryReservationPort: giữ hoặc giải phóng tồn.
- PaymentProviderPort: yêu cầu tạo giao dịch thanh toán.
- NotificationPort: gửi email hoặc push notification.
- EventPublisher / OutboxPort: ghi hoặc phát sự kiện.
- Clock, IdGenerator, FraudCheckPort khi thời gian, ID hoặc dịch vụ kiểm tra rủi ro cần kiểm soát.

**Outbound adapter** hiện thực port bằng công nghệ cụ thể:
- JpaOrderRepositoryAdapter, JdbcOrderRepositoryAdapter.
- PaymentHttpAdapter.
- KafkaEventPublisher hoặc OutboxRepository.
- S3ObjectStorageAdapter.
- SmtpNotificationAdapter.

### 6.1. Vì sao interface thuộc phía cần năng lực?

Application có thể nói “tôi cần lưu Order” mà không cần biết PostgreSQL, MongoDB hay API nội bộ thực hiện việc đó. Vì vậy interface OrderRepository thường được đặt trong domain/application module thích hợp, rồi adapter hạ tầng hiện thực nó.

Không nên ép interface mô phỏng CRUD/SDK của vendor nếu use case chỉ cần một thao tác có nghĩa nghiệp vụ như reserveInventory(). Một port tốt phản ánh **nhu cầu bên trong**, không rò rỉ thiết kế của công cụ ngoài.

### 6.2. Anti-Corruption Layer cho tích hợp bên ngoài

Giả sử đối tác thanh toán trả trạng thái:
- Succeeded
- RequiresAction
- Processing
- Failed

Domain Payments của hệ thống có thể dùng các trạng thái:
- PAYMENT_PENDING
- PAYMENT_AUTHORIZED
- PAYMENT_REJECTED

Không nên để entity nội bộ lưu thẳng vendor enum nếu những trạng thái đó không khớp ngữ nghĩa. Adapter có nhiệm vụ dịch:

~~~text
Payment provider response
    |
    v
Vendor DTO / SDK model
    |
    v
Translation / Anti-Corruption Layer
    |
    v
PaymentAuthorizationResult (internal contract)
    |
    v
Application use case / Domain
~~~

Nếu chuyển từ nhà cung cấp A sang B, nhiều khác biệt có thể được cách ly trong adapter. Nhưng adapter không thể che giấu mọi khác biệt: nếu B có mô hình giữ tiền và quyết toán khác căn bản, có thể cần thay đổi contract và quy trình nghiệp vụ một cách tường minh.

### 6.3. Chính sách timeout, retry và circuit breaker đặt ở đâu?

- Adapter biết lỗi kỹ thuật như connection timeout, HTTP 503, gRPC unavailable và cách tương tác với API đối tác.
- Application quyết định thao tác có thể thử lại theo nghiệp vụ không, trạng thái trung gian và cách phục hồi.
- Domain quyết định invariant phải giữ dù retry hoặc nhận thông điệp trùng.
- Hạ tầng hỗ trợ deadline, retry có giới hạn, jitter, circuit breaker, rate limit và observability.

Ví dụ retry một GET idempotent thường an toàn hơn retry một POST thanh toán không có idempotency key. Adapter không nên âm thầm retry thao tác tạo giao dịch nếu không rõ đối tác có thể thực hiện hai lần.

## 7. Gói mã nguồn một Spring Boot Microservice theo trách nhiệm

Một cách tổ chức package:

~~~text
order-service/
  src/main/java/com/example/orders/
    domain/
      model/
        Order.java
        OrderLine.java
        OrderStatus.java
      policy/
      event/
    application/
      port/in/
        PlaceOrderUseCase.java
        GetOrderUseCase.java
      port/out/
        OrderRepository.java
        InventoryReservationPort.java
        OutboxPort.java
      command/
        PlaceOrderCommand.java
      result/
        PlaceOrderResult.java
      service/
        PlaceOrderService.java
    adapter/
      in/
        rest/
          OrderController.java
          PlaceOrderRequest.java
          OrderResponse.java
          RestExceptionHandler.java
        messaging/
          InventoryEventListener.java
      out/
        persistence/
          JpaOrderRepositoryAdapter.java
          OrderJpaEntity.java
          SpringDataOrderRepository.java
        inventory/
          InventoryHttpAdapter.java
          InventoryApiDto.java
        messaging/
          OutboxJpaAdapter.java
    config/
      BeanConfiguration.java
      SecurityConfiguration.java
~~~

Đây là ví dụ một **dịch vụ Ordering**; tên package hay phân nhóm có thể khác. Có thể tổ chức theo feature trước, sau đó tách domain/application/adapter bên trong feature. Vấn đề không nằm ở một template thư mục duy nhất mà ở ranh giới phụ thuộc được bảo vệ.

### 7.1. Khi nào dùng multi-module build?

Với hệ thống lớn hoặc muốn giới hạn import ở compile-time, có thể dùng nhiều Gradle module:
- orders-domain: không phụ thuộc Spring Web/driver/SDK.
- orders-application: phụ thuộc domain và các port.
- orders-adapters: phụ thuộc application/domain và công nghệ tương ứng.
- orders-bootstrap: khởi tạo cấu hình, wiring và executable.

Nhưng không cần tách thành nhiều Gradle module chỉ để đạt “sạch” trên sơ đồ. Với service nhỏ, package boundaries và architecture tests có thể đủ. Quan trọng là người phát triển không thể vô tình dùng lớp hạ tầng từ domain hoặc rò rỉ transport vào ca sử dụng.

### 7.2. Service boundary bên ngoài vẫn là một câu chuyện khác

Order-service có thể chứa cả bốn tầng bên trong một JAR. Không phải REST controller là một Microservice, OrderUseCase là Microservice thứ hai, và database adapter là Microservice thứ ba. Việc tách ứng dụng thành nhiều process cần căn cứ nghiệp vụ, ownership, dữ liệu và triển khai riêng.

## 8. Ví dụ Java: từ REST tới application và domain

Xây dựng ví dụ nhỏ về việc tạo Order ở trạng thái DRAFT, lưu lại và trả ID.

### 8.1. Command và result của ca sử dụng

~~~java
package com.example.orders.application;

public record PlaceOrderCommand(
        String customerId,
        String productId,
        int quantity) {}

public record PlaceOrderResult(
        String orderId,
        String status) {}

public interface PlaceOrderUseCase {
    PlaceOrderResult place(PlaceOrderCommand command);
}
~~~

Command mô tả đầu vào của mục tiêu nghiệp vụ; không chứa HttpServletRequest, ResponseEntity hoặc annotation của transport. Domain sẽ thực thi bất biến quantity và trạng thái ở điểm phù hợp.

### 8.2. Port lưu trữ và sinh ID

~~~java
package com.example.orders.application.port;

import com.example.orders.domain.Order;
import java.util.Optional;

public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(String id);
}

public interface IdGenerator {
    String newOrderId();
}
~~~

Ứng dụng không nói sẽ ghi MySQL, PostgreSQL hay document store; adapter thực thi chi tiết đó.

### 8.3. Use case điều phối

~~~java
package com.example.orders.application;

import com.example.orders.application.port.IdGenerator;
import com.example.orders.application.port.OrderRepository;
import com.example.orders.domain.Order;

public final class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orders;
    private final IdGenerator ids;

    public PlaceOrderService(OrderRepository orders, IdGenerator ids) {
        this.orders = orders;
        this.ids = ids;
    }

    @Override
    public PlaceOrderResult place(PlaceOrderCommand command) {
        if (command.customerId() == null ||
                command.customerId().isBlank()) {
            throw new IllegalArgumentException(
                    "customerId is required");
        }

        Order order = Order.draft(
                ids.newOrderId(),
                command.customerId(),
                command.productId(),
                command.quantity());

        orders.save(order);
        return new PlaceOrderResult(order.id(), order.status().name());
    }
}
~~~

Trong ví dụ này, Order.draft(...) là **factory thuộc domain** cần hiện thực validate quantity, product và bất biến của một đơn nháp. Ví dụ tập trung vào đường phụ thuộc; không phải toàn bộ code của một ứng dụng production.

### 8.4. REST controller chỉ ánh xạ transport

~~~java
package com.example.orders.adapter.in.rest;

import com.example.orders.application.PlaceOrderCommand;
import com.example.orders.application.PlaceOrderResult;
import com.example.orders.application.PlaceOrderUseCase;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

record PlaceOrderRequest(
        @NotBlank String customerId,
        @NotBlank String productId,
        @Min(1) int quantity) {}

@RestController
@RequestMapping("/orders")
public final class OrderController {
    private final PlaceOrderUseCase placeOrder;

    public OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public PlaceOrderResult place(@Valid @RequestBody PlaceOrderRequest r) {
        return placeOrder.place(new PlaceOrderCommand(
                r.customerId(), r.productId(), r.quantity()));
    }
}
~~~

Controller biết REST route, validation đầu vào và response status. Controller không biết bảng orders, loại database hoặc logic chuyển trạng thái. Trong hệ thống thực, nên có response DTO của protocol riêng với application result khi hợp đồng bên ngoài cần versioning độc lập.

### 8.5. Persistence adapter ánh xạ giữa model và database

~~~java
package com.example.orders.adapter.out.persistence;

import com.example.orders.application.port.OrderRepository;
import com.example.orders.domain.Order;
import java.util.Optional;

public final class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;

    public JpaOrderRepositoryAdapter(SpringDataOrderJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public void save(Order order) {
        OrderJpaEntity row = OrderJpaMapper.toEntity(order);
        jpa.save(row);
    }

    @Override
    public Optional<Order> findById(String id) {
        return jpa.findById(id).map(OrderJpaMapper::toDomain);
    }
}
~~~

OrderJpaEntity là lớp ánh xạ lưu trữ, không bắt buộc chính là domain entity. Adapter chịu trách nhiệm mapping và chi tiết ORM. Nếu chọn domain entity kiêm JPA entity, cần hiểu coupling được chấp nhận và ảnh hưởng đến mô hình/kiểm thử.

### 8.6. Wiring các thành phần

~~~java
@Configuration
public class OrderApplicationConfiguration {
    @Bean
    PlaceOrderUseCase placeOrderUseCase(
            OrderRepository repository,
            IdGenerator idGenerator) {
        return new PlaceOrderService(repository, idGenerator);
    }
}
~~~

Adapter dùng Spring DI để cấu hình đối tượng. Điều kiện là mỗi port có implementation phù hợp, cấu hình persistence được bật và transaction boundaries được định nghĩa. Annotation @Configuration chỉ là ví dụ về nơi lắp ráp, không phải yêu cầu duy nhất của kiến trúc.

## 9. Một use case được gọi từ nhiều giao thức

Giả sử cùng hành vi tạo đơn có thể bắt nguồn từ:
- REST request của ứng dụng web.
- Message từ kênh đặt hàng offline.
- Scheduler xử lý đơn nhập trước.

Cả ba adapter đầu vào có thể gọi PlaceOrderUseCase, sau khi xác định identity, quyền và chuyển dữ liệu về command chung.

~~~text
POST /orders -----------------------+
                                    |
Kafka order.requested --------------+----> PlaceOrderUseCase
                                    |           |
Scheduled import job ---------------+           v
                                              Domain
                                                 |
                                                 v
                                          OrderRepository
~~~

Những adapter này **không nên** copy logic tạo Order riêng. Tuy nhiên, chúng có ngữ nghĩa delivery khác nhau:
- REST có timeout và trả response đồng bộ.
- Kafka có thể gửi lặp (at-least-once), gửi muộn hoặc thứ tự nhận khác kỳ vọng.
- Scheduler có thể được chạy lại sau khi lỗi.

Vì vậy use case hoặc tầng nghiệp vụ cần có **idempotency contract** phù hợp, thay vì tin rằng mọi adapter chỉ gọi đúng một lần. Transport adapter xử lý cơ chế nhận/ACK; application và persistence bảo vệ hiệu ứng nghiệp vụ khỏi trùng lặp.

### 9.1. Ví dụ message listener

~~~java
@Component
public final class OrderRequestListener {
    private final PlaceOrderUseCase placeOrder;

    public OrderRequestListener(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @KafkaListener(topics = "order.requests.v1")
    public void onMessage(OrderRequestedEvent event) {
        placeOrder.place(new PlaceOrderCommand(
                event.customerId(),
                event.productId(),
                event.quantity()));
    }
}
~~~

Ví dụ chỉ diễn tả mapping. Ứng dụng thật cần:
- Dựa trên eventId/commandId hoặc business key để chống xử lý lặp.
- Xác định schema/version của OrderRequestedEvent.
- Phân biệt lỗi có thể retry và lỗi không thể retry.
- Chỉ xác nhận message sau khi hiệu ứng xử lý đạt cam kết tương ứng.
- Định nghĩa dead-letter, backoff và thứ tự event nếu business cần.

Thiết kế application contract để xử lý duplicate command phải tính cả thao tác lưu database; thêm một Map lưu eventId trong bộ nhớ không đủ cho nhiều instance hoặc sau restart.

## 10. Phân định transaction, side effect và tích hợp phân tán

Trong một Microservice, database transaction cục bộ bảo vệ các thay đổi dữ liệu trong phạm vi mà DB hỗ trợ. Nhưng transaction này không tự bao gồm request HTTP tới Inventory, một PSP thanh toán hoặc publish Kafka.

### 10.1. Tránh nhầm một transaction với quy trình nghiệp vụ xuyên dịch vụ

Ví dụ flow đặt hàng gồm:
1. Tạo Order ở trạng thái PENDING.
2. Yêu cầu Inventory giữ hàng.
3. Yêu cầu Payments khởi tạo thanh toán.
4. Chuyển trạng thái sau khi nhận kết quả.

Nếu thực hiện tất cả trong một HTTP controller với @Transactional bao trùm việc chờ hai dịch vụ ngoài, DB transaction có thể mở lâu, giữ lock và vẫn không rollback được tác dụng đã xảy ra ở PSP. Annotation transaction nội bộ không biến mạng thành giao dịch ACID phân tán.

Tùy nghiệp vụ, một thiết kế có thể dùng:
- State machine hoặc saga điều phối các trạng thái và hành động bù trừ.
- Transactional outbox để gắn thay đổi state và ghi ý định phát event trong cùng giao dịch cục bộ.
- Idempotency key cho lệnh có thể nhận lại.
- Correlation ID để nối sự kiện nhiều hệ thống.
- Timeout, retry có giới hạn và trạng thái UNKNOWN/PENDING khi chưa biết kết quả của phụ thuộc ngoài.

### 10.2. Ví dụ outbox

~~~text
POST /orders
     |
     v
PlaceOrderUseCase
     |
     +-- trong cùng local DB transaction:
     |      save Order(PENDING)
     |      save OutboxEvent(OrderPlaced)
     |
     v
HTTP 202 / 201 theo hợp đồng tạo đơn
     |
     v
Outbox relay → Broker → Inventory/Payments consumers
                                |
                                v
                         phát kết quả
                                |
                                v
                        Order workflow update
~~~

Outbox tăng cơ hội phát event bền vững sau khi transaction commit, nhưng relay có thể gửi lặp; consumer phải idempotent. Việc báo 201 hay 202 tùy ý nghĩa resource đã tạo và thời điểm hệ thống xác nhận hành vi; không nên gọi “đã thanh toán” khi mới ghi PENDING.

### 10.3. Chỗ đặt transaction boundary

- Application use case hoặc decorator quanh use case có thể xác định transaction cho lưu Order + OutboxEvent.
- Domain thực thi luật và đổi trạng thái bên trong transaction đó, nhưng không cần tự bắt đầu một database transaction.
- Repository adapter thực thi lệnh lưu.
- Message publisher/relay tương tác broker sau transaction.
- Inbound adapter diễn đạt kết quả qua giao thức.

Có thể sử dụng @Transactional ở application service trong ứng dụng Spring Boot. Quy tắc thuộc về **biên giao dịch nghiệp vụ**, không nhất thiết phải tách kỹ thuật vào một lớp cho mọi dự án.

## 11. Ánh xạ lỗi giữa bốn tầng

Mỗi tầng cần sử dụng **ngôn ngữ lỗi phù hợp với trách nhiệm của nó**.

Ví dụ khi hủy đơn đã giao:

~~~text
Domain:
  OrderAlreadyShipped / CancellationNotAllowed

Application:
  Trả use-case failure có nghĩa "không thể hủy vì trạng thái"

REST adapter:
  Ánh xạ theo API contract → 409 Conflict hoặc status phù hợp

gRPC adapter:
  Ánh xạ → FAILED_PRECONDITION chẳng hạn

Message adapter:
  Ghi nhận business rejection, đưa vào luồng xử lý thích hợp
~~~

Cùng một business error không nên bị ràng buộc với ResponseStatusException từ domain. Mỗi adapter đầu vào diễn đạt lỗi theo contract của mình.

Với lỗi tích hợp:

~~~text
HTTP client adapter:
  Connection timeout / vendor 503

Outbound port:
  ExternalServiceUnavailable hoặc kết quả "chưa xác định"

Application:
  Quyết định retry có an toàn không, ghi trạng thái PENDING,
  hoặc trả kết quả chưa hoàn tất

Inbound adapter:
  Trả HTTP/gRPC/message outcome tương ứng
~~~

Cần phân biệt **lỗi nghiệp vụ có tính quyết định** (không đủ tồn, đơn không thể hủy) và **lỗi kỹ thuật có thể tạm thời** (timeout, broker chưa phản hồi). Một timeout thanh toán không tự động có nghĩa giao dịch bị từ chối; có thể PSP đã thực hiện thành công nhưng phản hồi bị mất.

### Bảng gợi ý ownership của lỗi

| Tình huống | Nơi phát hiện chính | Quyết định xử lý |
| --- | --- | --- |
| JSON không hợp lệ | Inbound adapter | Trả lỗi định dạng theo protocol |
| Người gọi thiếu quyền | Security/application | Từ chối use case theo chính sách |
| Quantity <= 0 | Domain value object / rule | Bảo vệ invariant |
| Order đã shipped | Domain | Không cho transition sai |
| Database connection timeout | Persistence adapter | Đưa lỗi kỹ thuật có phân loại ra application |
| PSP trả mã từ chối | Payment adapter dịch trạng thái | Application/domain áp dụng trạng thái thanh toán |
| Message gửi lặp | Inbox/idempotency mechanism | Bảo vệ hiệu ứng nghiệp vụ theo delivery contract |
| Lỗi mapping DTO | Inbound/outbound adapter | Xác định dữ liệu/hợp đồng không hợp lệ |

## 12. Contract bên ngoài khác model nội bộ

Trong Microservices, contract giữa các dịch vụ là ranh giới thay đổi quan trọng. Tránh phơi domain entity/JPA entity nguyên dạng ra API hoặc event.

### 12.1. Phân loại rõ các model

| Loại | Ai dùng? | Ví dụ |
| --- | --- | --- |
| Transport request DTO | REST/gRPC/message adapter | PlaceOrderRequest |
| Application command/query | Use case | PlaceOrderCommand |
| Domain model | Luật và trạng thái nghiệp vụ | Order, OrderLine |
| Persistence model | Database adapter | OrderJpaEntity |
| External API DTO | Adapter gọi dịch vụ khác | InventoryReserveRequest |
| Integration event | Consumer của hệ thống khác | order.placed.v1 |

Một số model có thể trùng cấu trúc và được gộp có chủ đích ở hệ thống nhỏ. Nhưng về ngữ nghĩa chúng có lý do thay đổi khác nhau: đổi trường database không nhất thiết làm thay đổi public API; đổi phiên bản API không được âm thầm sửa invariant của Order.

### 12.2. Versioning hợp đồng

Nếu REST API, gRPC schema hoặc event có nhiều consumer, cần áp dụng nguyên tắc tương thích:
- Bổ sung trường optional có default/semantics rõ.
- Tránh đổi ý nghĩa trường hiện có mà giữ nguyên tên.
- Hỗ trợ consumers cũ trong giai đoạn triển khai lệch phiên bản.
- Định nghĩa cách xử lý unknown enum và missing field.
- Có contract tests cho tương tác quan trọng.
- Khi phá tương thích, dùng version mới và kế hoạch di chuyển.

Đây là trách nhiệm của ranh giới tích hợp và quản trị hợp đồng, không nên bắt domain chứa các annotation chỉ để phục vụ serializer của một transport cụ thể.

## 13. Tích hợp giữa Microservices và ranh giới domain

Bốn tầng trong một dịch vụ **không giải quyết thay** vấn đề tìm bounded context, ownership dữ liệu và ranh giới triển khai.

Ví dụ:
- Ordering có domain Order và use cases đặt/hủy đơn.
- Inventory có domain StockItem và use cases giữ/giải phóng hàng.
- Payments có domain PaymentAttempt và use cases xác nhận thanh toán.

Nếu Ordering cần giữ hàng, nó gọi outbound port InventoryReservationPort; adapter hiện thực port bằng contract công khai của Inventory service.

~~~text
Ordering service
+-----------------------------------------------+
| REST → PlaceOrderUseCase → Order domain       |
|                       |                       |
|                       v                       |
|             InventoryReservationPort          |
|                       ^                       |
|                       |                       |
|              InventoryHttpAdapter             |
+-----------------------+-----------------------+
                        |
                    Network
                        |
                        v
Inventory service
+-----------------------------------------------+
| Inventory REST/gRPC adapter                   |
|           ↓                                   |
| ReserveInventoryUseCase → StockItem domain    |
|           ↓                                   |
|        InventoryRepository                    |
+-----------------------------------------------+
~~~

Mỗi service tự có giao thức, ca sử dụng, domain và adapter. **Outbound adapter của Ordering không được đọc thẳng database riêng của Inventory** nếu mục tiêu là tự chủ sở hữu dữ liệu và triển khai độc lập.

Khi cả hai context còn chung modular monolith, adapter có thể là lời gọi module interface nội bộ. Khi tách deploy, adapter chuyển sang HTTP/gRPC hoặc messaging mà use case không cần học cú pháp transport. Tuy vậy, semantics lỗi và consistency thay đổi do xuất hiện network boundary; application phải cập nhật hợp đồng xử lý phù hợp, không chỉ thay URL.

## 14. Phân chia sync và async cho đúng nghiệp vụ

### 14.1. Đồng bộ khi cần câu trả lời ngay

HTTP/gRPC phù hợp với truy vấn hoặc command cần phản hồi ngay trong một latency budget có giới hạn.

Ví dụ:
- Người dùng xem chi tiết đơn.
- Hệ thống hỏi chính sách báo giá cần để chốt checkout.
- Người dùng yêu cầu hủy và cần biết có chấp nhận ngay hay không.

Cần xác định timeout, retry safety, fallback và cách xử lý khi downstream không chắc chắn đã thực hiện thao tác.

### 14.2. Bất đồng bộ khi có thể hoàn thành sau

Message broker hoặc queue phù hợp cho:
- Gửi email khi đơn được xác nhận.
- Tạo tài liệu hoặc báo cáo.
- Đồng bộ projection tìm kiếm.
- Điều phối nhiều bước xử lý lâu hoặc có lỗi tạm thời.

Nhưng async có thể đưa vào eventual consistency và trạng thái trung gian. Cần event contract, consumer idempotency, DLQ, observability và cách truy vấn tiến độ.

### 14.3. Protocol choice không thay domain model

Cùng một use case ConfirmPayment có thể được gọi khi một webhook hợp lệ đến qua HTTP hoặc khi một event đã được xác thực tới broker. Adapter chuyển transport payload thành một application command thống nhất. Domain vẫn quyết định chuyển trạng thái thanh toán nào là hợp lệ.

Chú ý: webhook có thể giả mạo; xác minh chữ ký và replay window thuộc lớp giao tiếp/bảo mật. Xác minh event đến hợp lệ chưa thay thế được idempotency nghiệp vụ của thao tác xác nhận.

## 15. Đặt những concern xuyên suốt vào đúng chỗ

Có những chức năng xuất hiện nhiều tầng nhưng không nên rải code tùy tiện.

| Concern | Trách nhiệm thường phù hợp | Điều cần tránh |
| --- | --- | --- |
| Authentication | Gateway/security filter/inbound adapter | Domain tự parse JWT |
| Authorization use case | Application/domain policy khi cần | Chỉ kiểm ở REST và bỏ qua consumer |
| Logging, tracing | Middleware/interceptor/adapter và use case theo ngữ cảnh | Đưa trace SDK vào entity nghiệp vụ |
| Metrics | Protocol/service/infra instrumentation | Gắn logic quyết định nghiệp vụ vào tên metric |
| Transaction | Application boundary hoặc decorator | Giữ DB transaction mở qua network dài |
| Retry / timeout | Outbound adapter + app policy | Retry command không idempotent không giới hạn |
| Cache | Query adapter hoặc application policy | Cache làm sai invariant nghiệp vụ |
| Serialization | Inbound/outbound adapters | Domain bị buộc phụ thuộc JSON/Avro vendor |
| Config, secrets | Runtime/bootstrap/infra | Hardcode token trong domain hoặc controller |
| Feature flags | Application decision / configuration | Rải condition ngẫu nhiên khắp entity và adapter |
| Audit | Use case/domain event + persistence adapter | Chỉ log HTTP rồi coi là audit đáng tin |

Không có “một chỗ” duy nhất cho mọi concern. Ví dụ xác thực danh tính ở giao thức, nhưng quyền truy cập tài nguyên phải được bảo vệ khi application được gọi bởi các entry point khác nhau.

## 16. Chiến lược kiểm thử theo ranh giới

Cách chia trách nhiệm tốt làm kiểm thử sát hành vi hơn.

### 16.1. Domain tests: kiểm tra quy tắc

Không cần dựng HTTP server hay database nếu chỉ xác minh Order.confirm() từ DRAFT chuyển sang CONFIRMED, còn từ CANCELLED thì bị từ chối. Đây là kiểm thử nhanh cho bất biến.

### 16.2. Application use-case tests: giả lập port

Dùng fake/in-memory OrderRepository và fake IdGenerator để kiểm chứng:
- Use case gọi đúng quy tắc.
- Không lưu khi điều kiện nghiệp vụ không đạt.
- Ghi kết quả và trạng thái phù hợp.
- Xử lý lỗi đã phân loại theo chính sách.

~~~java
// Minh họa kiểm thử use case (pseudo-fixture).
OrderRepository fakeOrders = new InMemoryOrderRepository();
IdGenerator fixedIds = () -> "ord-test-1";

PlaceOrderUseCase useCase =
        new PlaceOrderService(fakeOrders, fixedIds);

PlaceOrderResult result =
        useCase.place(new PlaceOrderCommand("cus-1", "sku-1", 2));

assertEquals("ord-test-1", result.orderId());
assertTrue(fakeOrders.findById(result.orderId()).isPresent());
~~~

Nếu các thao tác dữ liệu cần concurrency hoặc transaction semantics, fake không thể thay thế integration test với database thật.

### 16.3. Protocol adapter tests: kiểm tra hợp đồng đầu vào/ra

Với REST:
- Route, validation, status code, headers, mapping lỗi.
- Security và quyền theo actor.
- Serialization, tên trường và lỗi payload.
- Version compatibility nếu có.

Các test MVC/WebTestClient có thể thay use case bằng stub để tập trung vào giao thức, rồi thêm integration test cho các tuyến quan trọng.

### 16.4. Outbound adapter tests: kiểm tra tích hợp thật

- Persistence adapter: mapping và transaction với database thích hợp.
- HTTP client: timeout, status, schema và cách dịch lỗi.
- Kafka producer/consumer: format event, headers, ACK, duplicate behavior.
- Outbox relay: có retry, ordering và cơ chế at-least-once như contract.

Một fake payment gateway cho unit test không chứng minh PSP thật xử lý timeout đúng. Nên có integration/contract tests ở ranh giới thực; phạm vi môi trường staging/sandbox phụ thuộc nhà cung cấp.

### 16.5. End-to-end tests có chọn lọc

Kiểm thử những hành trình quan trọng như đặt hàng và xác nhận thanh toán, đặc biệt các trạng thái bất đồng bộ và lỗi liên dịch vụ. Tránh đặt toàn bộ logic nghiệp vụ vào E2E test chậm và khó cô lập; domain/application tests nên bao phủ quy tắc chi tiết.

## 17. Những lỗi thiết kế thường gặp

### 17.1. Fat controller

Controller đọc database, tính tiền, gọi PSP, publish event và trực tiếp trả domain entity.

**Hệ quả:** đổi REST sang gRPC phải viết lại nghiệp vụ; kiểm thử cần cả network và database; lỗi khó phân biệt.

**Hướng xử lý:** controller chỉ map transport → command; use case điều phối; domain bảo vệ rule; adapter giao tiếp ngoài.

### 17.2. Anemic domain cực đoan

Mọi quy tắc nằm trong ApplicationService; domain chỉ có getter/setter.

**Hệ quả:** một invariant phải lặp ở nhiều use case; không có điểm bảo vệ trạng thái tập trung.

**Hướng xử lý:** đưa quy tắc trạng thái và invariant vào aggregate/value object hoặc domain policy, nơi chúng có ý nghĩa rõ.

Không phải mọi ứng dụng CRUD đơn giản đều cần mô hình domain phức tạp. Chỉ nên tăng cấu trúc theo độ phức tạp nghiệp vụ.

### 17.3. Domain phụ thuộc hạ tầng

Domain tự khởi tạo KafkaTemplate, lấy EntityManager hoặc import PSP SDK.

**Hệ quả:** thay vendor và chạy unit test kéo theo cấu hình kỹ thuật không liên quan.

**Hướng xử lý:** đẩy chi tiết kết nối vào outbound adapter, domain mô tả dữ liệu và quy tắc dưới dạng thuần.

### 17.4. Use case trả ResponseEntity

Application bị khóa với HTTP status và header, khó tái sử dụng từ message consumer.

**Hướng xử lý:** trả result hoặc lỗi application mang ngữ nghĩa nghiệp vụ; REST adapter ánh xạ sang ResponseEntity phù hợp.

### 17.5. Mỗi endpoint tự viết nghiệp vụ

REST, Kafka và scheduler đều cài lại quy tắc xác nhận đơn.

**Hệ quả:** cùng hành động có kết quả khác nhau theo đường truy cập.

**Hướng xử lý:** cùng use case và domain; adapter xử lý khác biệt delivery.

### 17.6. Port mô phỏng nguyên vendor API

PaymentPort chứa hàng loạt method với vendor-specific DTO, khiến application phụ thuộc cấu trúc PSP.

**Hướng xử lý:** thiết kế port theo mục tiêu như authorizePayment() hoặc capturePayment(); adapter dịch SDK sang domain/application result.

### 17.7. Tách quá nhiều lớp vô nghĩa

Một CRUD cực nhỏ có Controller → Facade → Manager → Service → Handler → Repository nhưng mỗi lớp chỉ forward lời gọi.

**Hệ quả:** tăng điều hướng mà không tạo ranh giới trách nhiệm.

**Hướng xử lý:** chỉ tạo abstraction bảo vệ quy tắc thay đổi có thật. Không cần một interface cho mọi class nếu không có hợp đồng hoặc lý do kiểm thử/architecture rõ.

### 17.8. Gọi network trong transaction quá dài

Đang giữ database lock thì chờ PSP hoặc Inventory; timeout gây backlog và trạng thái không thể rollback toàn cục.

**Hướng xử lý:** xác định ranh giới giao dịch cục bộ, trạng thái nghiệp vụ, idempotency và outbox/saga khi phù hợp.

### 17.9. Cho mọi service dùng chung database entity

Nhiều dịch vụ chia một thư viện JPA entity và cùng ghi một bảng.

**Hệ quả:** đổi schema đòi deploy nhiều nơi; ownership dữ liệu không rõ.

**Hướng xử lý:** tách domain model, contract và quyền sở hữu dữ liệu; tích hợp thông qua API/event có ý nghĩa.

### 17.10. Mặc định lỗi HTTP 500 là lỗi nghiệp vụ

Khi Inventory trả timeout, application lập tức đánh dấu “không đủ hàng”.

**Hệ quả:** trạng thái nghiệp vụ sai, retry không an toàn.

**Hướng xử lý:** phân biệt unavailable/unknown với rejected; giữ state machine và cách hòa giải có chủ đích.

## 18. Quy trình refactor một service đang bị trộn trách nhiệm

Giả sử hiện trạng có OrderController 600 dòng: parse request, gọi JPA repository, kiểm tra trạng thái, gọi REST Inventory, xử lý thanh toán, publish Kafka.

Có thể cải thiện theo thứ tự sau:

1. **Lập bản đồ hành vi:** xác định các use case cụ thể, quy tắc cần bảo vệ, bên ngoài được gọi, dữ liệu nào có thẩm quyền.
2. **Tạo input command/result:** chuyển dữ liệu giao thức thành contract nội bộ; xác định response/error mapping rõ.
3. **Rút quy tắc về domain:** tạo aggregate/value object/domain policy tại những nơi có invariant thật.
4. **Tạo application use case:** đưa thứ tự bước và quyết định workflow vào đó.
5. **Tạo outbound ports:** mô tả năng lực cần thiết, rồi bọc DAO/SDK/HTTP client vào adapters.
6. **Chuyển logic controller:** giữ route, validation giao thức và mapping kết quả; kiểm chứng các hành vi đã có.
7. **Xác định transaction và side effects:** không đưa việc gọi network dài vào DB transaction; dùng trạng thái và outbox nếu phù hợp.
8. **Kiểm thử ranh giới:** domain tests, use-case tests, contract/integration tests, rồi E2E cho tuyến trọng yếu.
9. **Đo trước/sau:** thay đổi có giữ latency, tỷ lệ lỗi và hiệu ứng nghiệp vụ không; việc sửa transport hoặc vendor có dễ hơn không.

Có thể thực hiện từng use case; không bắt buộc viết lại service toàn bộ. Bảo toàn API contract và dữ liệu hiện có trong lúc chuyển đổi là điều kiện quan trọng.

## 19. Checklist thiết kế một Microservice

Dùng các câu hỏi sau khi viết mới hoặc review cấu trúc:

- [ ] Mỗi endpoint/message có thể ánh xạ tới một use case rõ ràng không?
- [ ] Controller/listener có tập trung vào transport, mapping và response/ACK không?
- [ ] Application use case có điều phối việc thực hiện mục tiêu nhưng không phụ thuộc transport hay vendor SDK không?
- [ ] Domain có bảo vệ các invariant quan trọng ở đúng vị trí không?
- [ ] DTO giao thức, application command, domain model và persistence model có được phân biệt về ngữ nghĩa không?
- [ ] Phụ thuộc bên ngoài được biểu diễn bằng port phù hợp với nhu cầu ứng dụng không?
- [ ] Outbound adapter có trách nhiệm mapping, timeout, retry và chuyển lỗi kỹ thuật không?
- [ ] Lỗi nghiệp vụ có thể được trình bày qua REST, gRPC và message mà không nhân bản quy tắc không?
- [ ] Transaction boundary có tránh bao trùm lời gọi mạng không cần thiết không?
- [ ] Idempotency, duplicate events, outbox và trạng thái bất đồng bộ đã được xét cho luồng phân tán chưa?
- [ ] Database và contract liên dịch vụ có ownership cụ thể không?
- [ ] Có thể test domain/use case mà không cần bật HTTP server hoặc PSP thật không?
- [ ] Sơ đồ module/lớp có bị hiểu nhầm thành sơ đồ số lượng Microservices không?

## 20. Bài tập tình huống

### Bài 1 — Chia trách nhiệm

Một endpoint POST /orders đang:
1. Kiểm tra JSON có thiếu quantity.
2. Kiểm tra Order có đang bị khóa theo chính sách nghiệp vụ.
3. Lưu đơn vào PostgreSQL.
4. Gọi PSP HTTP với một idempotency key.
5. Trả 201 Created cùng orderId.

Hãy xác định mỗi bước chủ yếu thuộc lớp nào.

**Gợi ý:** bước 1 là inbound protocol; bước 2 là domain/application tùy vị trí quy tắc; bước 3 qua repository port và persistence adapter; bước 4 qua payment port và HTTP adapter với workflow do application kiểm soát; bước 5 là inbound protocol mapping. Cần tiếp tục thiết kế transaction và trạng thái thanh toán, vì ví dụ tuyến tính chưa xử lý mọi lỗi phân tán.

### Bài 2 — Thêm Kafka consumer

Trước đây tạo đơn chỉ qua REST, giờ cần nhận order.requested.v1 từ Kafka. Đội phát triển định sao chép toàn bộ logic của OrderController vào listener.

**Câu hỏi:** Vì sao không nên? Cấu trúc nào cho phép dùng lại đúng nghiệp vụ?

**Gợi ý:** listener map schema/event → command chung → PlaceOrderUseCase; domain bảo vệ rule. Thêm inbox/idempotency theo message delivery thay vì nhân bản nghiệp vụ.

### Bài 3 — Thay nhà cung cấp thanh toán

Hệ thống chuyển từ PSP A sang PSP B. PSP A trả SUCCESS/ERROR, PSP B trả AUTHORIZED/CAPTURED/REJECTED/PENDING.

**Câu hỏi:** Phần nào nên thay và phần nào có thể cần đổi có chủ đích?

**Gợi ý:** adapter và ACL dịch hợp đồng PSP; application/domain có thể cần đổi nếu vòng đời thanh toán thực sự khác. Không cố ép các trạng thái khác nghĩa thành một boolean success.

### Bài 4 — Transaction xuyên dịch vụ

PlaceOrderService mở @Transactional, giữ DB lock rồi gọi Inventory và Payment HTTP; Payment timeout nhưng sau đó gửi webhook báo thành công.

**Câu hỏi:** Vì sao một local transaction không thể rollback PSP? Bạn sẽ dùng trạng thái nào và cách xác minh nào để tránh ghi nhận sai?

**Gợi ý:** local ACID chỉ bảo vệ dữ liệu trong cùng tài nguyên transactional. Có thể dùng PENDING/UNKNOWN, idempotency key, webhook xác thực, đối soát, outbox và orchestration/saga phù hợp.

### Bài 5 — Phân biệt lớp và dịch vụ

Một Spring Boot JAR chứa REST controller, PlaceOrderUseCase, Order domain và adapter Postgres. Đội ngũ muốn tách bốn phần thành bốn container để “đúng Microservices”.

**Câu hỏi:** Những rủi ro và thông tin nào còn thiếu trước khi quyết định?

**Gợi ý:** phân rã lớp nội bộ không tương đương phân rã bounded context và đơn vị deploy. Cần xem nghiệp vụ, dữ liệu, transaction, ownership, release cadence, workload, fault isolation và chi phí mạng/vận hành. Có thể giữ cả bốn trách nhiệm trong một service với code boundaries rõ.

## 21. Kết luận

Bên trong một Microservice, **giao thức** chịu trách nhiệm nói chuyện với tác nhân bên ngoài; **ca sử dụng** điều phối việc hoàn thành mục tiêu; **miền nghiệp vụ** nắm mô hình và bất biến; **tích hợp bên ngoài** thực thi truy cập database, broker và hệ thống khác. Port và adapter giúp những trách nhiệm này tương tác mà không khóa logic cốt lõi vào HTTP, JPA hoặc SDK của một nhà cung cấp.

Sự phân chia này giúp một hành vi nghiệp vụ được tái sử dụng từ nhiều kênh, dễ kiểm thử, dễ thay transport/storage, và làm rõ vị trí xử lý timeout, idempotency, transaction và lỗi phân tán. Độ phức tạp nên tương xứng nhu cầu thực tế: một dịch vụ nhỏ không cần nhiều lớp chỉ để đẹp sơ đồ, nhưng các ranh giới quan trọng vẫn phải được bảo vệ. **Một Microservice có thể chứa đầy đủ cả bốn nhóm trách nhiệm trong cùng một đơn vị triển khai.**
