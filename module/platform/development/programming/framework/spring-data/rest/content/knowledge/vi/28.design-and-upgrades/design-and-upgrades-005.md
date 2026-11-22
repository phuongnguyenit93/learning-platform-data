# Giới hạn REST exporter với nghiệp vụ nhiều bước và transaction xuyên tài nguyên trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể nhận biết khi Spring Data REST repository exporter không còn phù hợp với một use case; phân biệt CRUD resource với business command; tổ chức workflow nhiều bước trong application service; xác định transaction boundary khi nhiều aggregate hoặc resource cùng thay đổi; xử lý side effect và transaction xuyên database bằng outbox/saga; và thiết kế API có thể nâng cấp mà không làm lộ persistence model.

## 1. Spring Data REST exporter giải quyết tốt điều gì?

Spring Data REST tự động tạo REST resources từ Spring Data repositories. Với repository được export, framework có thể cung cấp:

- Collection resource để đọc danh sách và tạo entity.
- Item resource để đọc, cập nhật hoặc xóa entity.
- Association resources để truy cập hoặc thay đổi liên kết giữa entity.
- Search resource cho query methods được công bố.
- HAL links, profile metadata, pagination và conditional request support.

Cách tiếp cận này giúp triển khai nhanh API CRUD cho domain model tương đối đơn giản. Client có thể khám phá resource qua hypermedia mà ứng dụng không cần viết controller cho từng repository.

Ví dụ:

```java
@RepositoryRestResource(path = "products")
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Spring Data REST có thể export collection `/products` và item resource `/products/{id}`. Đây là lựa chọn phù hợp khi thao tác HTTP gần với thao tác CRUD trên một aggregate và không cần một quy trình nghiệp vụ phức tạp.

## 2. Khi nào CRUD exporter không đủ?

Một nghiệp vụ nhiều bước thường không tương đương với một lệnh save đơn giản. Ví dụ xác nhận đơn hàng có thể cần:

1. Kiểm tra trạng thái Order.
2. Kiểm tra Customer còn hoạt động.
3. Kiểm tra và giữ tồn kho từ nhiều Product.
4. Tính phí vận chuyển và thuế.
5. Ghi nhận PaymentIntent.
6. Chuyển trạng thái Order sang CONFIRMED.
7. Phát event để hệ thống vận chuyển và thông báo tiếp tục xử lý.

Nếu chỉ expose `PUT /orders/{id}` để client đổi field `status` thành `CONFIRMED`, client có thể bỏ qua kiểm tra tồn kho, thanh toán hoặc authorization. API cho phép thay đổi persistence state mà không thể hiện đúng business operation.

Các dấu hiệu exporter không còn đủ:

- Một thao tác cần gọi nhiều repository hoặc aggregate.
- Thứ tự bước có ý nghĩa nghiệp vụ.
- Có điều kiện chuyển trạng thái và invariant cần bảo vệ.
- Cần transaction bao trùm nhiều lần ghi.
- Có side effect tới message broker hoặc hệ thống ngoài.
- Input/output của use case khác shape entity.
- Cần idempotency, retry, compensation hoặc workflow state.
- Quyền thực hiện phụ thuộc trạng thái hoặc vai trò cụ thể.

Trong trường hợp đó, tạo một command endpoint gọi application service sẽ thể hiện nghiệp vụ rõ hơn.

## 3. Phân biệt resource operation và business command

Resource operation thao tác trên representation của một resource, ví dụ GET một Order hoặc PATCH địa chỉ giao hàng. Business command yêu cầu hệ thống thực hiện một hành động có ý nghĩa, ví dụ:

- `POST /orders/{id}/confirm`
- `POST /orders/{id}/cancel`
- `POST /payments/{id}/capture`
- `POST /shipments/{id}/dispatch`

Command thường có input riêng và kết quả riêng. Nó không nhất thiết cho phép client tự đặt các field trạng thái nội bộ.

Ví dụ request:

```http
POST /api/orders/42/confirm
Content-Type: application/json
Idempotency-Key: 7f4f2b1c-...

{
  "paymentReference": "pay_123",
  "shippingMethod": "EXPRESS"
}
```

Response có thể trả representation của Order sau khi xác nhận hoặc một resource mô tả operation đã được chấp nhận. HTTP status phụ thuộc tính đồng bộ của use case: `200 OK` nếu hoàn tất và trả kết quả, `202 Accepted` nếu workflow tiếp tục bất đồng bộ, hoặc `409 Conflict` nếu trạng thái hiện tại không cho phép xác nhận.

Command endpoint giúp API thể hiện ý định và kiểm soát quy tắc nghiệp vụ. Resource CRUD vẫn có thể được dùng song song cho những thao tác đơn giản và an toàn.

## 4. Đưa workflow vào application service

Controller nhận HTTP request, chuyển thành command và gọi service. Service điều phối repository, domain operation và transaction.

Ví dụ:

```java
public record ConfirmOrderCommand(
    Long orderId,
    String paymentReference,
    ShippingMethod shippingMethod) {
}
```

Service:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;
    private final PaymentRepository payments;

    public OrderApplicationService(
            OrderRepository orders,
            InventoryRepository inventory,
            PaymentRepository payments) {
        this.orders = orders;
        this.inventory = inventory;
        this.payments = payments;
    }

    @Transactional
    public Order confirm(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFoundException(
                command.orderId()));

        order.requireConfirmable();

        inventory.reserve(order.getLines());
        payments.recordAuthorization(
            order.getId(),
            command.paymentReference());

        order.confirm(command.shippingMethod());

        return orders.save(order);
    }
}
```

Ví dụ rút gọn để thể hiện điều phối. Trong ứng dụng thực tế, Payment có thể là hệ thống ngoài; khi đó không gọi payment provider và giả định nó rollback cùng database transaction. Hãy xem phần outbox/saga.

Service là điểm dùng chung cho REST controller, scheduled job, message consumer hoặc workflow khác. Nhờ vậy, cùng một business operation không bị triển khai khác nhau ở nhiều adapter.

## 5. Tạo custom endpoint bên cạnh repository exporter

Với Spring Data REST, có thể dùng `@BasePathAwareController` cho controller nằm dưới base path cấu hình của Spring Data REST:

```java
@BasePathAwareController
@RequestMapping("/orders")
public class OrderCommandController {

    private final OrderApplicationService orderService;

    public OrderCommandController(
            OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{id}/confirm")
    public ResponseEntity<OrderResponse> confirm(
            @PathVariable Long id,
            @RequestBody ConfirmOrderRequest request) {

        Order order = orderService.confirm(
            new ConfirmOrderCommand(
                id,
                request.paymentReference(),
                request.shippingMethod()));

        return ResponseEntity.ok(OrderResponse.from(order));
    }
}
```

Nếu dùng `@RestController` thông thường, cần định nghĩa base path và route để tránh xung đột với repository resources. Chọn một URL command rõ ràng, ví dụ `/api/orders/{id}/confirm`, và xác định endpoint đó thuộc Spring MVC hay Spring Data REST base path.

Không để controller gọi nhiều repository trực tiếp. Controller chỉ xử lý giao thức HTTP, binding, validation ở mức request và response. Quy tắc nghiệp vụ, transaction và điều phối thuộc application service/domain layer.

## 6. Hạn chế thao tác CRUD có thể bỏ qua workflow

Nếu repository exporter vẫn cho phép client sửa trực tiếp các field nhạy cảm, custom command endpoint không bảo đảm client phải đi qua workflow. Cần giới hạn exposure của repository methods hoặc field.

Ví dụ ẩn repository method:

```java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Override
    @RestResource(exported = false)
    <S extends Order> S save(S entity);
}
```

Đây chỉ là ví dụ minh họa. Việc ẩn `save` có thể ảnh hưởng các thao tác create/update do Spring Data REST cung cấp và cần kiểm tra behavior theo phiên bản. Có thể ẩn toàn bộ repository bằng `@RepositoryRestResource(exported = false)` nếu muốn chỉ công bố custom API, hoặc dùng event/authorization/custom repository design để kiểm soát phù hợp.

Một lựa chọn khác là dùng `@RestResource(exported = false)` cho method hoặc association không nên công bố. Với property, dùng projection/input model phù hợp để không cho client sửa field nội bộ như `status`, `approvedBy`, `paymentState` hoặc audit metadata.

Ẩn endpoint không thay thế authorization. Service vẫn phải xác minh actor có quyền thực hiện command trên resource cụ thể.

## 7. Transaction boundary khi nhiều aggregate cùng thay đổi

Nếu nhiều repository cùng dùng một relational database và cùng transaction manager, một `@Transactional` ở service entry point có thể bao trùm toàn bộ thao tác.

```java
@Transactional
public Order cancel(Long orderId) {
    Order order = orders.findById(orderId)
        .orElseThrow();

    order.requireCancelable();

    inventory.release(order.getLines());
    order.cancel();

    return orders.save(order);
}
```

Khi phương thức kết thúc bình thường, transaction commit. Nếu unchecked exception thoát khỏi phương thức, Spring mặc định rollback transaction. Checked exception không tự động rollback theo mặc định; cấu hình `rollbackFor` nếu cần.

```java
@Transactional(rollbackFor = Exception.class)
public Order cancel(Long orderId) throws Exception {
    // Các bước nghiệp vụ
}
```

Transaction bảo đảm các thay đổi thuộc cùng transaction resource commit hoặc rollback cùng nhau. Nó không tự biến nhiều database hoặc HTTP service thành một transaction nguyên tử.

Đừng đặt transaction riêng cho từng repository operation nếu use case yêu cầu tính nguyên tử xuyên suốt. Các repository tham gia transaction hiện hành khi được quản lý bởi transaction manager tương ứng.

## 8. Nhiều datasource và transaction xuyên tài nguyên

Một ứng dụng có thể dùng nhiều database, ví dụ Order ở PostgreSQL, Inventory ở một database khác và Payment ở dịch vụ bên ngoài. `@Transactional` mặc định chỉ quản lý transaction của transaction manager được chọn; nó không tự phối hợp mọi datasource.

Cần xác định:

- Repository nào dùng datasource và transaction manager nào?
- Các thao tác có cùng database transaction resource hay không?
- Có yêu cầu atomic commit thật sự giữa các resource không?
- Nếu một bước thành công còn bước khác thất bại, hệ thống sẽ phục hồi thế nào?

Với nhiều datasource độc lập, có thể dùng XA/JTA nếu môi trường và driver hỗ trợ, nhưng distributed transaction làm tăng độ phức tạp vận hành và coupling. Nhiều hệ thống chọn eventual consistency với outbox/saga và hành động bù trừ.

Không ghi rằng “toàn bộ workflow rollback” nếu một HTTP payment request hoặc message publish đã hoàn tất bên ngoài database transaction. Database rollback không thể tự hoàn tác side effect đó.

## 9. Transactional Outbox cho event sau khi commit

Giả sử sau khi tạo Order cần publish `OrderCreated` đến message broker. Nếu ghi Order rồi publish message trong cùng method, có hai lỗi có thể xảy ra:

- Database commit thành công nhưng broker publish thất bại.
- Broker nhận message nhưng database transaction sau đó rollback.

Transactional Outbox giải quyết khoảng trống này bằng cách lưu Order và event record trong cùng database transaction:

```java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orders.save(Order.create(command));

    outbox.save(OutboxEvent.orderCreated(order.getId()));

    return order;
}
```

Một publisher nền đọc outbox record chưa gửi, publish đến broker rồi đánh dấu đã gửi. Nếu publisher crash sau khi broker nhận message nhưng trước khi cập nhật trạng thái, message có thể được gửi lại. Consumer cần idempotency hoặc deduplication.

Outbox bảo đảm database commit đồng thời với ý định phát event; nó không tự bảo đảm exactly-once delivery.

Có thể dùng CDC (Change Data Capture) đọc outbox table thay vì polling. Chọn cách phù hợp với hạ tầng, throughput và yêu cầu vận hành.

## 10. Saga cho workflow nhiều service

Saga mô hình hóa workflow phân tán thành chuỗi local transaction. Mỗi bước commit tại service sở hữu dữ liệu; sau đó phát command/event cho bước tiếp theo.

Ví dụ đặt hàng:

1. Order service tạo Order ở trạng thái PENDING.
2. Inventory service giữ hàng.
3. Payment service authorize thanh toán.
4. Order service xác nhận Order.
5. Shipping service tạo shipment.

Nếu Payment thất bại sau khi Inventory đã giữ hàng, saga phát lệnh bù trừ để giải phóng hàng và chuyển Order sang trạng thái PAYMENT_FAILED.

Saga có thể điều phối theo hai cách:

- **Choreography:** các service phản ứng với event của nhau; ít central coordinator nhưng luồng tổng thể khó quan sát khi có nhiều bước.
- **Orchestration:** một saga orchestrator điều phối command, lưu trạng thái workflow và quyết định bước tiếp theo; dễ theo dõi hơn nhưng thêm một thành phần điều phối.

Hành động bù trừ là nghiệp vụ riêng. Ví dụ hoàn tiền hoặc giải phóng hàng không phải rollback ACID của transaction trước đó. Compensation có thể thất bại và cần retry, timeout, manual intervention hoặc trạng thái chờ xử lý.

## 11. Idempotency, retry và xử lý request lặp

Client có thể retry khi timeout dù server đã hoàn tất command. Nếu command không idempotent, retry có thể tạo hai payment hoặc hai shipment.

Có thể nhận `Idempotency-Key` từ client:

```http
POST /api/orders/42/confirm
Idempotency-Key: 3a0f2f3d-...
Content-Type: application/json
```

Server lưu key cùng actor, operation, request fingerprint và kết quả. Nếu cùng key được gửi lại với cùng nội dung, trả lại kết quả đã ghi nhận. Nếu key giống nhưng payload khác, từ chối theo contract.

Idempotency record nên được lưu trong cùng transaction với thay đổi nghiệp vụ khi có thể. Với workflow bất đồng bộ, key có thể tham chiếu operation resource để client poll trạng thái.

Không dựa vào việc HTTP POST “chỉ gọi một lần”. Network retry, client refresh và message redelivery đều có thể tạo request trùng.

## 12. Validation và authorization ở command boundary

Command endpoint cần kiểm tra input và quyền thực hiện. Ví dụ:

```java
public record ConfirmOrderRequest(
    @NotBlank String paymentReference,
    @NotNull ShippingMethod shippingMethod) {
}
```

Controller dùng `@Valid`:

```java
@PostMapping("/{id}/confirm")
public ResponseEntity<OrderResponse> confirm(
        @PathVariable Long id,
        @Valid @RequestBody ConfirmOrderRequest request) {
    // Gọi application service
}
```

Service cần kiểm tra các invariant phụ thuộc trạng thái:

- Order thuộc tenant hiện tại.
- Order đang ở trạng thái cho phép xác nhận.
- Actor có quyền xác nhận.
- Payment reference thuộc Order và chưa được dùng cho operation khác.
- Inventory và các điều kiện kinh doanh vẫn hợp lệ tại thời điểm commit.

Authorization không chỉ dựa vào việc user có role `ROLE_USER`. Cần kiểm tra ownership/tenant và quyền trên resource cụ thể. Nếu command chạy qua job nền hoặc message consumer, xác định principal/service identity tương ứng.

## 13. Trả response cho command đồng bộ và bất đồng bộ

Nếu command hoàn tất trong request, có thể trả representation hiện tại:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

Nếu hệ thống chỉ nhận command và tiếp tục xử lý nền, trả `202 Accepted` cùng link tới operation/status resource:

```http
HTTP/1.1 202 Accepted
Location: /api/operations/op-123
```

Client theo link operation để kiểm tra trạng thái như PENDING, RUNNING, SUCCEEDED hoặc FAILED. Có thể dùng Retry-After hoặc polling interval theo contract.

Đừng trả `200 OK` với trạng thái CONFIRMED nếu workflow mới chỉ được enqueue. Response phải phân biệt “đã chấp nhận xử lý” với “nghiệp vụ đã hoàn tất”.

## 14. Giữ HAL và hypermedia trong custom workflow

Custom endpoint vẫn có thể trả hypermedia representation. Spring HATEOAS hỗ trợ `EntityModel`, `CollectionModel`, `RepresentationModel` và link builder để tạo link có base path/context path phù hợp.

Ví dụ response model:

```java
public EntityModel<OrderResponse> toModel(Order order) {
    OrderResponse body = OrderResponse.from(order);

    EntityModel<OrderResponse> model = EntityModel.of(body);
    model.add(linkTo(methodOn(OrderQueryController.class)
        .get(order.getId())).withSelfRel());

    if (order.canBeCancelled()) {
        model.add(linkTo(methodOn(OrderCommandController.class)
            .cancel(order.getId())).withRel("cancel"));
    }

    return model;
}
```

Ví dụ minh họa; controller method signatures và mapping cần khớp ứng dụng. Chỉ công bố command link khi thao tác có ý nghĩa ở trạng thái hiện tại. Server vẫn phải kiểm tra lại điều kiện khi nhận command vì trạng thái có thể đổi sau lúc response được tạo.

Hypermedia giúp client khám phá thao tác; nó không thay thế validation, transaction hoặc authorization.

## 15. API evolution và bảo vệ domain model

Khi repository exporter expose trực tiếp entity, thay đổi mapping có thể vô tình làm thay đổi HTTP contract:

- Thêm field có thể làm field đó xuất hiện trong representation.
- Thêm association có thể tạo link mới.
- Đổi repository path làm thay đổi URL.
- Đổi enum hoặc property name ảnh hưởng client.
- Thay fetch strategy ảnh hưởng latency và serialization.

Với API công khai hoặc cần ổn định lâu dài, cân nhắc:

- Dùng projection để kiểm soát representation đọc.
- Dùng input DTO/command để kiểm soát dữ liệu ghi.
- Ẩn repository method/association không nên export.
- Dùng custom controller cho workflow và contract cần versioning.
- Giữ backward compatibility khi đổi relation, field hoặc status code.
- Tạo contract tests cho endpoint quan trọng.

Không để persistence entity trở thành API contract ngoài ý muốn. Domain model có thể thay đổi vì database hoặc business requirement; API cần được quản lý theo consumer compatibility.

## 16. Khi nào vẫn nên dùng repository exporter?

Repository exporter vẫn phù hợp khi:

- Resource có CRUD đơn giản.
- Một operation chủ yếu đọc/ghi một aggregate.
- Association và query methods có semantics rõ ràng.
- Không cần workflow nhiều bước hoặc side effect ngoài transaction.
- Client được hưởng lợi từ hypermedia discovery và pagination.
- Repository exposure có thể được giới hạn bằng authorization/projection.

Một ứng dụng có thể kết hợp repository exporter cho đọc và CRUD cơ bản với custom command endpoint cho nghiệp vụ nhạy cảm. Không cần chuyển toàn bộ API sang controller thủ công chỉ vì một use case phức tạp.

## 17. Các lỗi thiết kế thường gặp

**Cho phép client PATCH field trạng thái nội bộ**

Client có thể bỏ qua workflow. Dùng command endpoint và giới hạn field writable.

**Controller điều phối nhiều repository**

Logic nghiệp vụ bị gắn với HTTP và khó tái sử dụng. Chuyển điều phối vào application service.

**Giả định @Transactional bao trùm nhiều database hoặc HTTP service**

Xác định transaction manager và resource thực tế. Dùng outbox/saga khi cần consistency phân tán.

**Publish event trực tiếp trong transaction rồi cho rằng atomic**

Dùng transactional outbox và consumer idempotent.

**Retry command mà không có idempotency**

Request lặp có thể tạo tác dụng nhiều lần. Dùng idempotency key và lưu kết quả.

**Ẩn repository endpoint nhưng quên custom endpoint authorization**

Kiểm tra quyền tại command/service boundary và mọi đường truy cập resource.

**Trả 200 khi workflow mới được enqueue**

Dùng 202 và operation resource để biểu diễn trạng thái xử lý bất đồng bộ.

**Entity model bị xem như API contract bất biến**

Dùng projection, DTO và contract test để kiểm soát thay đổi representation.

## Tóm tắt

- Spring Data REST exporter phù hợp với CRUD resource đơn giản; workflow nhiều bước cần business command và application service.
- Custom endpoint nên nhận command, gọi service và trả response phản ánh đúng trạng thái đồng bộ/bất đồng bộ.
- Giới hạn repository write exposure để client không bỏ qua business workflow.
- `@Transactional` chỉ quản lý resource của transaction manager tương ứng; nhiều datasource hoặc dịch vụ ngoài cần chiến lược consistency riêng.
- Transactional Outbox lưu event intent cùng database transaction; publisher/consumer cần retry và idempotency.
- Saga phối hợp local transactions qua nhiều service và dùng compensation khi bước sau thất bại.
- Dùng idempotency key cho command có thể được retry; kiểm tra validation, ownership và authorization ở service boundary.
- Custom command endpoint vẫn có thể trả HAL links; hypermedia không thay thế kiểm tra trạng thái và quyền.
- Kết hợp repository exporter cho CRUD phù hợp với custom endpoint cho nghiệp vụ phức tạp, đồng thời quản lý API evolution bằng projection, DTO và contract test.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing and extending](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring HATEOAS — Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices.io — Saga pattern](https://microservices.io/patterns/data/saga.html)
