# Biểu diễn trường hợp sử dụng bằng chuỗi xử lý có ranh giới rõ

Trong module REACTIVE_PROGRAMMING, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành Mono, Flux, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi thiết kế một ứng dụng reactive, thách thức quan trọng là chuyển yêu cầu nghiệp vụ thành một chuỗi xử lý có thể đọc, kiểm thử và vận hành. Chuỗi đó cần có ranh giới rõ giữa nhận request, kiểm tra đầu vào, điều phối nghiệp vụ, quy tắc miền, truy cập dữ liệu, side effect và tạo response.

Một use case không nên trở thành một đoạn callback lồng nhau hoặc một chuỗi toán tử dài mà không rõ trách nhiệm. Mỗi đoạn cần có một mục đích, kiểu dữ liệu đầu vào/đầu ra và chính sách lỗi riêng. Reactor cung cấp Mono và Flux để mô tả luồng dữ liệu; kiến trúc ứng dụng xác định đoạn nào được phép truy cập database, đoạn nào chứa quy tắc miền và đoạn nào chịu trách nhiệm giao tiếp HTTP.

Bài này dùng use case đăng ký đơn hàng làm ví dụ. Request được xác thực và kiểm tra, dữ liệu khách hàng và sản phẩm được đọc độc lập, quy tắc miền tạo đơn hàng, sau đó thay đổi đơn hàng và outbox event được lưu trong cùng transaction database. Một worker khác có thể chuyển outbox event đến hệ thống tồn kho hoặc thông báo. Cách tổ chức này giúp phân biệt transaction cục bộ với side effect bên ngoài.

## 1. Bắt đầu từ use case và kết quả nghiệp vụ

Trước khi viết pipeline, hãy mô tả use case bằng ngôn ngữ nghiệp vụ. Ví dụ:

> Khi khách hàng đăng ký đơn hàng, hệ thống xác nhận khách hàng và sản phẩm có thể bán, tính tổng tiền từ giá do server quản lý, tạo đơn hàng ở trạng thái chờ xử lý, lưu đơn hàng cùng sự kiện OrderRegistered, rồi trả mã đơn hàng cho client.

Mô tả này xác định các điều kiện và kết quả:

- Đầu vào: mã khách hàng, SKU và số lượng.
- Dữ liệu cần đọc: khách hàng đang hoạt động và sản phẩm đang được bán.
- Quy tắc miền: số lượng phải dương, giá lấy từ catalog, tổng tiền được tính ở server.
- Thay đổi cục bộ: lưu đơn hàng và outbox event trong một transaction.
- Kết quả: mã đơn hàng và trạng thái ban đầu.
- Xử lý tiếp theo: worker đọc outbox và phát sự kiện đến các hệ thống liên quan.

Use case có một điểm bắt đầu và một kết quả rõ. Nó không cần biết HTTP status code, JSON serialization, tên bảng database hoặc cách gửi message qua broker. Những chi tiết đó thuộc adapter ở các ranh giới bên ngoài.

## 2. Chia pipeline thành các ranh giới có trách nhiệm

Một thiết kế có thể chia thành năm vùng:

| Ranh giới | Trách nhiệm | Thành phần thường gặp |
|---|---|---|
| Inbound adapter | Nhận giao thức, parse request, xác thực cơ bản và gọi use case | WebFlux controller, router, message listener |
| Application/use case | Điều phối các bước nghiệp vụ và xác định thứ tự thực hiện | RegisterOrderHandler |
| Domain | Bảo vệ invariant và tính toán nghiệp vụ thuần | Order, Money, domain policy |
| Outbound ports | Khai báo nhu cầu với hệ thống bên ngoài | CustomerQuery, ProductQuery, OrderStore, Outbox |
| Outbound adapters | Thực hiện port bằng công nghệ cụ thể | R2DBC repository, WebClient, broker client |

~~~mermaid
flowchart TD
    A[HTTP request] --> B[WebFlux Controller]
    B --> C[RegisterOrder use case]
    C --> D[Customer and Product ports]
    D --> E[Domain decision]
    E --> F[OrderStore and Outbox ports]
    F --> G[R2DBC adapters in one transaction]
    G --> H[Order result]
    H --> I[HTTP response]
    G --> J[Outbox relay]
    J --> K[Inventory / Notification services]
~~~

Inbound adapter chuyển giao thức thành command. Use case điều phối luồng. Domain quyết định trạng thái hợp lệ. Outbound port mô tả điều mà use case cần; adapter triển khai bằng database hoặc client cụ thể. Khi một dependency thay đổi từ HTTP sang message broker hoặc từ một database sang R2DBC, use case không cần biết chi tiết triển khai nếu port giữ nguyên hợp đồng.

## 3. Xác định kiểu dữ liệu ở ranh giới use case

Dùng command để mô tả ý định của caller, không dùng trực tiếp DTO HTTP hoặc entity database trong toàn bộ pipeline:

~~~java
record RegisterOrderCommand(
    String customerId,
    String sku,
    int quantity
) {}

record RegisterOrderResult(
    UUID orderId,
    String status,
    BigDecimal total
) {}

record Customer(String id, boolean active) {}

record Product(String sku, BigDecimal unitPrice, boolean sellable) {}
~~~

Command biểu diễn dữ liệu cần thiết để thực hiện use case. Kết quả biểu diễn điều caller được phép biết. DTO HTTP có thể có field khác để đáp ứng API; entity persistence có thể có field kỹ thuật như version hoặc audit columns. Giữ các kiểu này tách biệt giúp thay đổi schema hoặc API không lan vào quy tắc miền.

Port là interface thuộc về nhu cầu của ứng dụng:

~~~java
interface CustomerQuery {
    Mono<Customer> findById(String customerId);
}

interface ProductQuery {
    Mono<Product> findBySku(String sku);
}

interface OrderStore {
    Mono<Void> save(Order order);
}

interface OutboxStore {
    Mono<Void> append(OrderRegistered event);
}
~~~

Các port trả về Publisher để use case có thể ghép chúng vào pipeline. Port không nên tự gọi subscribe hoặc block. Adapter chịu trách nhiệm chuyển lời gọi sang R2DBC, WebClient hoặc broker client và trả về Publisher lạnh/đúng hợp đồng mà use case có thể tiêu thụ.

## 4. Giữ quy tắc miền thuần và dễ kiểm thử

Quy tắc miền không cần biết Reactor nếu bản thân phép tính là đồng bộ và thuần. Ví dụ:

~~~java
enum OrderStatus {
    PENDING_FULFILLMENT
}

record Order(
    UUID id,
    String customerId,
    String sku,
    int quantity,
    BigDecimal unitPrice,
    BigDecimal total,
    OrderStatus status,
    Instant createdAt
) {
    static Order register(
            Customer customer,
            Product product,
            int quantity,
            UUID id,
            Instant now) {

        if (!customer.active()) {
            throw new CustomerNotActiveException(customer.id());
        }
        if (!product.sellable()) {
            throw new ProductUnavailableException(product.sku());
        }
        if (quantity <= 0) {
            throw new InvalidOrderQuantityException(quantity);
        }

        BigDecimal total = product.unitPrice()
            .multiply(BigDecimal.valueOf(quantity));

        return new Order(
            id,
            customer.id(),
            product.sku(),
            quantity,
            product.unitPrice(),
            total,
            OrderStatus.PENDING_FULFILLMENT,
            now
        );
    }
}
~~~

Phương thức register nhận dữ liệu đã được lấy từ các port và tạo một Order hợp lệ. Giá sản phẩm đến từ catalog, không lấy từ request client. Hàm không ghi database, không gửi message và không đọc đồng hồ hệ thống trực tiếp. ID và thời điểm được truyền vào để test có thể kiểm soát.

Trong ứng dụng thực tế, có thể dùng kiểu Money thay cho BigDecimal trực tiếp, áp dụng quy tắc làm tròn và currency rõ ràng. Ví dụ trên tập trung vào ranh giới giữa dữ liệu đầu vào và quyết định miền.

## 5. Điều phối use case bằng Mono

Use case có thể được triển khai như một application service. Hai truy vấn khách hàng và sản phẩm độc lập nên có thể thực hiện bằng Mono.zip. Sau khi có đủ dữ liệu, domain tạo Order. Cuối cùng, transaction chỉ bao quanh các thay đổi cục bộ cần commit cùng nhau:

~~~java
@Service
class RegisterOrderHandler {
    private final CustomerQuery customerQuery;
    private final ProductQuery productQuery;
    private final OrderStore orderStore;
    private final OutboxStore outboxStore;
    private final TransactionalOperator transaction;
    private final Clock clock;
    private final Supplier<UUID> idGenerator;

    RegisterOrderHandler(
            CustomerQuery customerQuery,
            ProductQuery productQuery,
            OrderStore orderStore,
            OutboxStore outboxStore,
            TransactionalOperator transaction,
            Clock clock,
            Supplier<UUID> idGenerator) {
        this.customerQuery = customerQuery;
        this.productQuery = productQuery;
        this.orderStore = orderStore;
        this.outboxStore = outboxStore;
        this.transaction = transaction;
        this.clock = clock;
        this.idGenerator = idGenerator;
    }

    Mono<RegisterOrderResult> handle(RegisterOrderCommand command) {
        return Mono.defer(() -> {
            if (command.quantity() <= 0) {
                return Mono.error(
                    new InvalidOrderQuantityException(command.quantity())
                );
            }

            Mono<Customer> customer = customerQuery
                .findById(command.customerId())
                .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(command.customerId())
                ));

            Mono<Product> product = productQuery
                .findBySku(command.sku())
                .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(command.sku())
                ));

            return Mono.zip(customer, product)
                .map(tuple -> Order.register(
                    tuple.getT1(),
                    tuple.getT2(),
                    command.quantity(),
                    idGenerator.get(),
                    clock.instant()
                ))
                .flatMap(order -> transaction.transactional(
                    orderStore.save(order)
                        .then(outboxStore.append(
                            OrderRegistered.from(order)
                        ))
                        .thenReturn(order)
                ))
                .map(RegisterOrderResult::from);
        });
    }
}
~~~

Ranh giới trong đoạn code:

1. Mono.defer trì hoãn validation và việc tạo Publisher con đến lúc subscription.
2. Validation số lượng chạy trước khi gọi port, nên input sai không tạo truy vấn không cần thiết.
3. Mono.zip kết hợp hai truy vấn độc lập. Nếu một truy vấn lỗi hoặc hoàn tất rỗng sau khi đã được ánh xạ thành lỗi miền, pipeline không tạo Order.
4. Order.register thực hiện quyết định miền đồng bộ và thuần.
5. TransactionalOperator bao quanh việc lưu Order và outbox event. Hai thao tác phải dùng cùng reactive transaction manager và cùng tài nguyên database.
6. Kết quả chỉ được chuyển thành RegisterOrderResult sau khi Publisher transaction hoàn tất thành công.

Đây là ví dụ minh họa các kiểu và exception cần được định nghĩa trong ứng dụng. Điều quan trọng là luồng phụ thuộc được thể hiện rõ và transaction không bao trùm các lời gọi mạng không thuộc database cục bộ.

## 6. Chọn toán tử theo quan hệ phụ thuộc

Toán tử nên phản ánh quan hệ giữa các bước nghiệp vụ:

| Toán tử | Khi dùng | Ví dụ |
|---|---|---|
| map | Biến đổi đồng bộ, thuần từ một giá trị sang giá trị khác | Command thành domain value |
| flatMap | Bước tiếp theo phụ thuộc vào kết quả bất đồng bộ trước đó | Tìm Order rồi tải chi tiết |
| zip | Nhiều nguồn độc lập cần đủ kết quả để tính bước tiếp theo | Đọc Customer và Product |
| concatMap | Xử lý các phần tử tuần tự, giữ thứ tự | Ghi các bản ghi theo thứ tự |
| flatMap với concurrency | Xử lý độc lập nhiều nhánh đồng thời có giới hạn | Gọi API cho nhiều SKU |
| switchIfEmpty | Nguồn hoàn tất rỗng và cần một nhánh thay thế | Cache miss sang repository |
| onErrorMap | Chuyển lỗi kỹ thuật thành lỗi có ý nghĩa ở ranh giới | R2DBC exception thành PersistenceFailure |

Không dùng flatMap cho mọi bước theo thói quen. Nếu bước sau cần kết quả bước trước, flatMap làm quan hệ phụ thuộc rõ. Nếu hai truy vấn độc lập, zip thể hiện tính độc lập. Nếu ghi theo thứ tự, concatMap dễ suy luận hơn flatMap đồng thời.

Với một Flux nhiều phần tử, hãy đặt concurrency có giới hạn khi dùng flatMap. Không để một request tạo hàng nghìn lời gọi đồng thời đến database hoặc dịch vụ ngoài chỉ vì nguồn phát nhanh.

## 7. Đặt transaction đúng ranh giới

Transaction database nên bao quanh các thao tác database cần nguyên tử. Không nên mở transaction rồi chờ một HTTP call dài nếu side effect đó không được cùng transaction manager quản lý.

Trong ví dụ, Order và Outbox event được ghi trong cùng transaction:

~~~java
transaction.transactional(
    orderStore.save(order)
        .then(outboxStore.append(OrderRegistered.from(order)))
);
~~~

Nếu ghi Order thành công nhưng ghi Outbox thất bại, transaction rollback cả hai. Nếu commit thành công, worker có thể đọc outbox và phát event sau đó.

Gửi message trực tiếp trong transaction database không làm message broker và database trở thành một transaction nguyên tử. Nếu message đã được broker nhận nhưng transaction database rollback, hai hệ thống có thể lệch trạng thái. Outbox giảm rủi ro bằng cách lưu ý định phát event cùng thay đổi nghiệp vụ; relay có thể giao ít nhất một lần và consumer cần idempotency để xử lý trùng.

Không bọc toàn bộ request trong transaction nếu trước đó còn các truy vấn mạng chậm hoặc bước tính toán không cần giữ connection. Hãy xác định chính xác phần dữ liệu cần commit cùng nhau.

## 8. Side effect bên ngoài và quy trình nhiều bước

Use case thực tế có thể cần giữ chỗ tồn kho, gọi thanh toán hoặc gửi thông báo. Những thao tác này nằm ngoài transaction database cục bộ. Có ba cách thường gặp:

- Ghi outbox event và để worker xử lý bất đồng bộ sau commit.
- Dùng saga/process manager khi nhiều service cần phối hợp và có bước bù trừ.
- Gọi dịch vụ ngoài trước khi commit chỉ khi hợp đồng và khả năng rollback/compensation đã được thiết kế rõ.

Với đăng ký đơn hàng, hệ thống có thể lưu Order ở trạng thái PENDING_FULFILLMENT cùng event OrderRegistered. Worker đọc outbox, gửi yêu cầu giữ hàng. Khi có kết quả, một use case khác cập nhật trạng thái đơn hàng. Nếu event được gửi lại, consumer nhận diện event ID để tránh thực hiện side effect trùng.

Không nên gọi payment hoặc inventory bên trong transaction R2DBC rồi giả định rollback database sẽ thu hồi thao tác ở service ngoài. Nếu cần bảo đảm nghiệp vụ xuyên nhiều hệ thống, phải mô hình hóa trạng thái trung gian, timeout, retry, idempotency và compensation.

## 9. Đưa lỗi về đúng ranh giới

Các lỗi nên được phân loại theo nơi có thể xử lý:

| Loại lỗi | Ví dụ | Xử lý phù hợp |
|---|---|---|
| Validation | Số lượng âm, SKU rỗng | Trả lỗi đầu vào trước side effect |
| Domain | Khách hàng không hoạt động, sản phẩm không bán | Trả lỗi nghiệp vụ có mã rõ |
| Not found | Không có khách hàng hoặc sản phẩm | Ánh xạ thành kết quả 404 hoặc lỗi miền |
| Transient infrastructure | Timeout, connection reset | Retry có giới hạn nếu thao tác an toàn |
| Persistence | Constraint violation, database unavailable | Ánh xạ thành lỗi lưu trữ và để transaction rollback |
| Unexpected | Lỗi lập trình hoặc invariant bị phá vỡ | Ghi nhận, trả lỗi 5xx và điều tra |

Không nên đặt một onErrorResume rộng ở giữa use case để biến mọi lỗi thành kết quả mặc định. Điều đó có thể làm mất tín hiệu rollback hoặc che giấu lỗi nghiệp vụ. Chuyển đổi lỗi kỹ thuật thành lỗi ứng dụng tại adapter hoặc ranh giới use case; ánh xạ lỗi ứng dụng thành HTTP status ở inbound adapter.

Ví dụ, nếu repository phát lỗi kỹ thuật, adapter có thể dùng onErrorMap để tạo PersistenceFailure. Controller advice ánh xạ CustomerNotFound thành 404, InvalidOrderQuantity thành 400 và lỗi ngoài dự kiến thành 500. Không để controller biết chi tiết exception của R2DBC.

## 10. Inbound adapter chỉ chuyển đổi giao thức

WebFlux controller nhận request, chuyển DTO thành command và gọi use case. Nó không nên tự truy vấn repository hoặc thực hiện quy tắc miền:

~~~java
@RestController
@RequestMapping("/api/orders")
class RegisterOrderController {
    private final RegisterOrderHandler handler;

    RegisterOrderController(RegisterOrderHandler handler) {
        this.handler = handler;
    }

    @PostMapping
    Mono<ResponseEntity<RegisterOrderResponse>> register(
            @Valid @RequestBody Mono<RegisterOrderRequest> request) {

        return request
            .map(RegisterOrderRequest::toCommand)
            .flatMap(handler::handle)
            .map(RegisterOrderResponse::from)
            .map(response -> ResponseEntity.accepted().body(response));
    }
}
~~~

Controller không gọi subscribe hoặc block. WebFlux quản lý subscription và chuyển kết quả thành HTTP response. Validation ở DTO có thể kiểm tra cấu trúc request; use case và domain vẫn phải bảo vệ invariant nghiệp vụ vì chúng có thể được gọi từ message listener hoặc adapter khác, không chỉ HTTP.

HTTP status phụ thuộc hợp đồng API. Ví dụ trên trả 202 Accepted vì đơn hàng mới ở trạng thái chờ xử lý bất đồng bộ. Nếu use case tạo tài nguyên đã hoàn tất đồng bộ và tài nguyên có URI, 201 Created có thể phù hợp hơn.

## 11. Context và metadata xuyên suốt use case

Thông tin như trace ID, tenant ID, locale hoặc deadline có thể được truyền qua Reactor Context nếu nó thuộc toàn subscription. Dữ liệu nghiệp vụ như SKU, quantity và order ID vẫn nên nằm trong command hoặc payload.

~~~java
Mono<RegisterOrderResult> handle(RegisterOrderCommand command) {
    return Mono.deferContextual(context -> {
        String traceId = context.getOrDefault("traceId", "no-trace");
        log.debug("Register order trace={}", traceId);
        return handleCommand(command);
    });
}
~~~

Đây là minh họa cách đọc metadata. Nếu tenant ảnh hưởng đến truy vấn hoặc quyền truy cập, use case phải đưa tenant vào port/query hoặc kiểm tra quyền rõ ràng; chỉ có mặt trong Context không tự bảo đảm an toàn. Không lưu secret vào Context rồi log toàn bộ context.

Khi pipeline chuyển scheduler bằng publishOn hoặc subscribeOn, Reactor Context vẫn đi theo subscription. ThreadLocal không có cùng bảo đảm vì nó gắn với thread; thư viện legacy cần cơ chế context propagation riêng nếu không thể đọc Reactor Context trực tiếp.

## 12. Cancellation và deadline là một phần của hợp đồng use case

Trong WebFlux, client có thể ngắt kết nối trước khi use case hoàn tất. Cancellation truyền ngược qua subscription và các Publisher có thể dừng công việc nếu API bên dưới hỗ trợ. Tuy nhiên, cancellation không phải rollback phổ quát: một lệnh blocking đang chạy hoặc side effect đã commit có thể tiếp tục.

Use case có thể áp dụng timeout cho dependency và deadline tổng. Timeout cần được tính trong cùng ngân sách request, không khởi tạo lại toàn bộ thời gian cho từng hop. Với thao tác ghi, dùng idempotency key nếu caller có thể retry sau khi không nhận được response.

Không nên bắt đầu một side effect không thể đảo ngược chỉ vì controller vẫn còn subscription. Hãy xác định điểm commit, điểm phát event và trạng thái nghiệp vụ khi caller hủy hoặc timeout.

## 13. Kiểm thử theo từng ranh giới

Một thiết kế có ranh giới rõ cho phép kiểm thử từng phần:

1. Domain test kiểm tra Order.register với dữ liệu hợp lệ và không hợp lệ.
2. Use case unit test dùng fake/mock cho các port, kiểm tra thứ tự và kết quả điều phối.
3. Transaction integration test dùng R2DBC database để xác nhận Order và Outbox cùng commit hoặc rollback.
4. Adapter test kiểm tra mapping giữa HTTP/SQL/message và kiểu ứng dụng.
5. WebTestClient test kiểm tra status, body, validation và ánh xạ lỗi.
6. StepVerifier test kiểm tra tín hiệu, empty/error, demand và cancellation.

Ví dụ kiểm thử use case bằng StepVerifier:

~~~java
@Test
void registersOrderAndWritesOutbox() {
    when(customerQuery.findById("customer-1"))
        .thenReturn(Mono.just(activeCustomer));
    when(productQuery.findBySku("sku-1"))
        .thenReturn(Mono.just(product));
    when(orderStore.save(any(Order.class)))
        .thenReturn(Mono.empty());
    when(outboxStore.append(any(OrderRegistered.class)))
        .thenReturn(Mono.empty());

    StepVerifier.create(handler.handle(
            new RegisterOrderCommand("customer-1", "sku-1", 2)
        ))
        .assertNext(result -> {
            assertNotNull(result.orderId());
            assertEquals("PENDING_FULFILLMENT", result.status());
            assertEquals(
                product.unitPrice().multiply(BigDecimal.valueOf(2)),
                result.total()
            );
        })
        .verifyComplete();

    verify(orderStore).save(any(Order.class));
    verify(outboxStore).append(any(OrderRegistered.class));
}
~~~

Ví dụ giả định test fixture đã cung cấp handler, transaction operator, clock, ID generator và các mock cần thiết. Unit test có thể dùng transaction operator phù hợp hoặc thay bằng cấu hình test; tính rollback thật phải được kiểm tra bằng integration test với database, không thể suy ra chỉ từ mock.

Một test validation nên xác nhận các port không được gọi:

~~~java
StepVerifier.create(handler.handle(
        new RegisterOrderCommand("customer-1", "sku-1", 0)
    ))
    .expectError(InvalidOrderQuantityException.class)
    .verify();

verifyNoInteractions(customerQuery, productQuery, orderStore, outboxStore);
~~~

Test này xác nhận input sai bị chặn trước khi phát sinh I/O hoặc side effect. Nên bổ sung test khi khách hàng không tồn tại, sản phẩm không bán, một port lỗi, ghi outbox thất bại và transaction rollback.

## 14. Những dấu hiệu của một use case reactive khó bảo trì

| Dấu hiệu | Vấn đề | Hướng điều chỉnh |
|---|---|---|
| Controller truy cập trực tiếp nhiều repository | HTTP adapter gánh cả orchestration và domain | Chuyển điều phối vào application use case |
| Một method chứa toàn bộ map/flatMap lồng nhau | Không rõ bước nào thuộc trách nhiệm nào | Tách hàm theo ý nghĩa nghiệp vụ và port |
| Gọi subscribe trong service | Tách pipeline khỏi caller, khó quản lý lỗi/cancel | Trả Publisher cho caller |
| Gọi block để lấy kết quả | Chặn thread và phá composition | Ghép Publisher bằng flatMap/zip |
| Domain phụ thuộc WebClient hoặc R2DBC | Quy tắc nghiệp vụ gắn với công nghệ | Dùng kiểu miền thuần và outbound ports |
| Transaction bao quanh HTTP call dài | Giữ connection/lock và không rollback được side effect ngoài | Transaction cục bộ ngắn, outbox/saga |
| onErrorResume biến mọi lỗi thành empty | Che giấu lỗi và có thể làm transaction commit | Phân loại lỗi và phục hồi tại ranh giới đúng |
| flatMap không giới hạn với nguồn lớn | Tạo quá nhiều request đồng thời | Giới hạn concurrency và backpressure |
| Dùng DTO hoặc entity database xuyên mọi tầng | Thay đổi schema/API lan rộng | Dùng command, result và domain model |

## 15. Quy trình thiết kế một use case bằng pipeline

Khi chuyển một yêu cầu nghiệp vụ thành pipeline reactive, hãy làm theo thứ tự:

1. **Viết rõ đầu vào và kết quả:** xác định command, dữ liệu cần đọc và trạng thái trả về.
2. **Xác định invariant miền:** đặt quy tắc trong domain model hoặc domain service thuần.
3. **Liệt kê các port:** chỉ khai báo những khả năng mà use case cần từ hệ thống ngoài.
4. **Vẽ quan hệ phụ thuộc:** dùng zip cho các truy vấn độc lập, flatMap cho bước phụ thuộc và concatMap cho xử lý tuần tự.
5. **Đặt ranh giới transaction:** chỉ bao quanh các thay đổi cục bộ cần nguyên tử.
6. **Tách side effect phân tán:** dùng outbox, idempotency hoặc saga khi có nhiều hệ thống.
7. **Định nghĩa lỗi và cancellation:** quyết định lỗi nào được phục hồi, lỗi nào phải rollback và timeout nào áp dụng.
8. **Giữ adapter mỏng:** chuyển đổi giao thức, gọi use case và ánh xạ kết quả.
9. **Kiểm thử từng lớp:** domain, use case, transaction, adapter và HTTP.
10. **Quan sát pipeline:** đặt metric/tracing ở ranh giới có ý nghĩa, giới hạn concurrency và queue theo capacity.

Một use case reactive tốt biểu diễn rõ điều kiện đầu vào, thứ tự phụ thuộc, quy tắc miền, ranh giới lưu trữ và kết quả. Mono/Flux giúp ghép các thao tác bất đồng bộ; kiến trúc ứng dụng quyết định trách nhiệm của từng đoạn. Khi adapter chỉ xử lý giao thức, domain giữ invariant, application service điều phối và transaction/outbox được đặt đúng ranh giới, pipeline sẽ dễ đọc, kiểm thử và thay đổi mà không làm lẫn lộn side effect giữa các hệ thống.
