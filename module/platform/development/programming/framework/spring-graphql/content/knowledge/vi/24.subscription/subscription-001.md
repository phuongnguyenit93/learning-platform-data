# Subscription operation trong Spring for GraphQL

GraphQL subscription cho phép client đăng ký nhận những kết quả mới khi một sự kiện xảy ra, thay vì gửi query lặp đi lặp lại để kiểm tra dữ liệu đã thay đổi hay chưa. Trong Spring for GraphQL, một subscription field thường được triển khai bằng `@SubscriptionMapping` và trả về một reactive publisher như `Flux<T>`. Mỗi phần tử publisher phát ra trở thành một kết quả GraphQL riêng theo selection set mà client đã đăng ký.

Subscription phù hợp với thông báo trực tiếp, trạng thái đơn hàng, cập nhật bảng điều khiển, tiến trình xử lý hoặc sự kiện nghiệp vụ. Để thiết kế đúng, cần hiểu subscription root trong SDL, cách Spring kết nối resolver với publisher, transport streaming, vòng đời đăng ký, xử lý lỗi, bảo mật và kiểm thử.

## 1. Phân biệt Query, Mutation và Subscription

Ba operation root có mục đích khác nhau:

| Operation | Mục đích | Hành vi |
|---|---|---|
| `Query` | Đọc dữ liệu hiện tại | Client gửi request và nhận một response. |
| `Mutation` | Thay đổi dữ liệu | Client gửi request, server thực hiện thao tác và trả kết quả. |
| `Subscription` | Nhận dữ liệu thay đổi theo thời gian | Client mở một operation dài hạn và nhận nhiều response khi publisher phát sự kiện. |

Ví dụ trong hệ thống quản lý đơn hàng:

- `order(id)` trả trạng thái hiện tại của đơn hàng.
- `cancelOrder(id)` yêu cầu hủy đơn hàng.
- `orderStatusChanged(orderId)` gửi các thay đổi trạng thái mới cho client đang theo dõi.

Subscription không thay thế query. Client thường dùng query để tải trạng thái ban đầu, sau đó dùng subscription để nhận các thay đổi tiếp theo.

## 2. Khai báo Subscription root trong SDL

GraphQL schema cần khai báo root type `Subscription` và các field mà client có thể đăng ký:

```graphql
type Query {
    order(id: ID!): Order
}

type Mutation {
    updateOrderStatus(id: ID!, status: OrderStatus!): Order!
}

type Subscription {
    orderStatusChanged(orderId: ID!): OrderEvent!
}

type Order {
    id: ID!
    status: OrderStatus!
}

type OrderEvent {
    orderId: ID!
    previousStatus: OrderStatus
    currentStatus: OrderStatus!
    occurredAt: String!
}

enum OrderStatus {
    CREATED
    CONFIRMED
    SHIPPING
    DELIVERED
    CANCELLED
}
```

`Subscription` là root type dành cho các field subscription. Trong một subscription operation, selection set ở root phải chọn đúng một field subscription. Các field con của event vẫn có thể được chọn bình thường.

Ví dụ operation:

```graphql
subscription WatchOrder($orderId: ID!) {
    orderStatusChanged(orderId: $orderId) {
        orderId
        previousStatus
        currentStatus
        occurredAt
    }
}
```

Client gửi operation này một lần. Server giữ subscription hoạt động và gửi kết quả mới mỗi khi có event tương ứng. Kiểu trả về `OrderEvent!` mô tả payload của mỗi lần phát, không có nghĩa toàn bộ subscription chỉ trả đúng một object.

## 3. Ánh xạ field bằng `@SubscriptionMapping`

Spring for GraphQL cung cấp `@SubscriptionMapping` để kết nối một phương thức controller với field thuộc root `Subscription`. Annotation này là dạng rút gọn của `@SchemaMapping(typeName = "Subscription")`.

Ví dụ resolver:

```java
@Controller
class OrderSubscriptionController {

    private final OrderEventPublisher eventPublisher;

    OrderSubscriptionController(OrderEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @SubscriptionMapping
    Flux<OrderEvent> orderStatusChanged(@Argument("orderId") String orderId) {
        return eventPublisher.eventsForOrder(orderId);
    }
}
```

Spring mặc định lấy tên phương thức `orderStatusChanged` làm tên field GraphQL. Nếu tên Java khác tên field trong SDL, có thể chỉ định rõ:

```java
@SubscriptionMapping(name = "orderStatusChanged")
Flux<OrderEvent> watchOrder(@Argument("orderId") String orderId) {
    return eventPublisher.eventsForOrder(orderId);
}
```

Tên field phải tồn tại trong SDL. `@SubscriptionMapping` không tự thêm field vào schema. Argument được bind bằng `@Argument` giống query và mutation.

## 4. Vì sao subscription thường trả về `Flux<T>`?

`Flux<T>` của Project Reactor biểu diễn một chuỗi bất đồng bộ có thể phát ra không, một hoặc nhiều phần tử rồi hoàn tất hoặc phát sinh lỗi. Đây là mô hình phù hợp với subscription:

```java
@SubscriptionMapping
Flux<OrderEvent> orderStatusChanged(@Argument("orderId") String orderId) {
    return eventPublisher.eventsForOrder(orderId);
}
```

Mỗi phần tử `OrderEvent` mà `Flux` phát ra được GraphQL xử lý theo selection set của subscription. Ví dụ client chọn `currentStatus` và `occurredAt`, response của mỗi event chỉ chứa các field đó.

Không nên gọi `subscribe()` bên trong resolver. Spring for GraphQL quản lý việc subscribe publisher và chuyển các phần tử thành kết quả GraphQL. Cũng không nên gọi `block()` vì sẽ chặn thread và phá vỡ reactive flow.

Một publisher có thể phát ra các tín hiệu:

| Tín hiệu | Ý nghĩa với subscription |
|---|---|
| `onNext(value)` | Có một event mới; GraphQL tạo một response cho event đó. |
| `onComplete()` | Luồng event kết thúc bình thường; subscription hoàn tất. |
| `onError(error)` | Luồng gặp lỗi; subscription kết thúc với lỗi theo cơ chế thực thi GraphQL. |
| Cancellation | Client hoặc server hủy đăng ký; upstream nhận tín hiệu hủy. |

## 5. Tạo nguồn event cho subscription

Resolver chỉ nên chuyển tiếp publisher từ một thành phần chịu trách nhiệm cung cấp event. Nguồn event có thể là message broker, reactive database change stream, event bus hoặc một publisher trong ứng dụng.

Ví dụ đơn giản dùng Reactor `Sinks.Many` để minh họa event bus trong một instance:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
class OrderEventPublisher {

    private static final Logger log = LoggerFactory.getLogger(OrderEventPublisher.class);

    private final Sinks.Many<OrderEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer();

    Flux<OrderEvent> eventsForOrder(String orderId) {
        return sink.asFlux()
            .filter(event -> event.orderId().equals(orderId));
    }

    void publish(OrderEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            // Ghi log hoặc chuyển sang cơ chế xử lý event phù hợp.
            log.warn("Cannot emit order event: {}", result);
        }
    }
}
```

Đây là nguồn event trong bộ nhớ để học và thử nghiệm. Với multicast sink, event được phân phối cho subscriber đang hoạt động; nếu không có subscriber hoặc sink không thể nhận event, `tryEmitNext` có thể trả kết quả thất bại. Ứng dụng cần quyết định rõ cách xử lý, không nên bỏ qua `EmitResult`.

Trong production nhiều instance, sink trong bộ nhớ chỉ nhìn thấy event được phát trong cùng instance. Nếu client kết nối vào instance A nhưng event được tạo tại instance B, client có thể không nhận được. Hệ thống thực tế thường dùng broker hoặc event platform dùng chung như Kafka, RabbitMQ, Redis Pub/Sub/Streams hay nền tảng messaging phù hợp.

## 6. Kết nối mutation với subscription event

Một luồng thường gặp là mutation thay đổi trạng thái, service lưu dữ liệu rồi phát event để các subscription nhận được:

Các kiểu dữ liệu dùng trong ví dụ:

```java
public enum OrderStatus {
    CREATED, CONFIRMED, SHIPPING, DELIVERED, CANCELLED
}

public record Order(String id, OrderStatus status) {
    public Order withStatus(OrderStatus newStatus) {
        return new Order(id, newStatus);
    }
}

public record OrderEvent(
    String orderId,
    OrderStatus previousStatus,
    OrderStatus currentStatus,
    String occurredAt
) {}
```

```java
@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final OrderEventPublisher eventPublisher;

    OrderService(
            OrderRepository orderRepository,
            OrderEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    Mono<Order> updateStatus(String id, OrderStatus newStatus) {
        return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
            .flatMap(order -> {
                OrderStatus previous = order.status();
                Order updated = order.withStatus(newStatus);

                return orderRepository.save(updated)
                    .doOnNext(saved -> eventPublisher.publish(
                        new OrderEvent(
                            saved.id(),
                            previous,
                            saved.status(),
                            Instant.now().toString()
                        )
                    ));
            });
    }
}
```

Mutation controller:

```java
@Controller
class OrderMutationController {

    private final OrderService orderService;

    OrderMutationController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    Mono<Order> updateOrderStatus(
            @Argument("id") String id,
            @Argument("status") OrderStatus status) {
        return orderService.updateStatus(id, status);
    }
}
```

Trong ví dụ, event được phát sau khi repository lưu thành công. Với hệ thống dùng transaction database và message broker, cần cân nhắc transaction boundary: nếu phát event trước khi transaction commit, subscriber có thể nhìn thấy sự kiện cho thay đổi sau đó bị rollback. Outbox pattern hoặc transaction-aware event publishing giúp đồng bộ dữ liệu và event đáng tin cậy hơn.

## 7. Subscription transport: WebSocket và GraphQL protocol

Subscription cần transport hỗ trợ truyền nhiều kết quả theo thời gian. HTTP request/response thông thường chỉ trả một response rồi đóng, nên không phù hợp để duy trì một luồng subscription lâu dài.

Spring for GraphQL hỗ trợ WebSocket transport cho subscription. WebSocket endpoint có thể được cấu hình trong Spring Boot, ví dụ:

```yaml
spring:
  graphql:
    websocket:
      path: /graphql
```

Client và server trao đổi theo GraphQL over WebSocket protocol `graphql-transport-ws`. Client gửi subprotocol này trong WebSocket handshake; server và client cần hỗ trợ cùng protocol. Các message quan trọng gồm:

| Message | Hướng | Mục đích |
|---|---|---|
| `connection_init` | Client → Server | Khởi tạo kết nối, có thể mang payload xác thực. |
| `connection_ack` | Server → Client | Xác nhận kết nối đã sẵn sàng. |
| `subscribe` | Client → Server | Bắt đầu một GraphQL operation, thường là subscription. |
| `next` | Server → Client | Gửi một execution result/event. |
| `error` | Server → Client | Báo lỗi operation theo protocol. |
| `complete` | Hai chiều | Kết thúc operation hoặc xác nhận stream đã hoàn tất. |
| `ping` / `pong` | Hai chiều | Kiểm tra trạng thái kết nối. |

Mỗi subscription operation có ID để client và server liên kết các event với operation tương ứng. Client có thể gửi `complete` để hủy một subscription mà không cần đóng toàn bộ WebSocket connection.

WebSocket connection có thể mang nhiều operation đồng thời. Vì vậy, cần quản lý giới hạn số subscription trên một kết nối và tài nguyên mà mỗi subscription tiêu thụ.

## 8. Lifecycle: bắt đầu, hoàn tất và hủy subscription

Subscription thường sống lâu hơn một HTTP request thông thường. Cần xử lý đầy đủ vòng đời:

1. Client mở WebSocket connection.
2. Client gửi `connection_init`; server xác thực hoặc chuẩn bị context nếu có cấu hình.
3. Server gửi `connection_ack`.
4. Client gửi `subscribe` với GraphQL subscription document.
5. Spring gọi `@SubscriptionMapping` và subscribe vào publisher trả về.
6. Mỗi event tạo một `next` response.
7. Publisher hoàn tất hoặc lỗi thì operation kết thúc.
8. Client gửi `complete` để hủy; server hủy subscription upstream và giải phóng tài nguyên.

Publisher cần phản ứng đúng với cancellation. Ví dụ, khi client ngừng theo dõi, ứng dụng nên hủy consumer hoặc subscription tới broker nếu không còn subscriber nào cần nó. Các toán tử Reactor như `doOnCancel` và `doFinally` có thể hỗ trợ cleanup, nhưng việc giải phóng tài nguyên phải được thiết kế theo lifecycle thực tế của nguồn event.

Không nên giữ một subscription vô hạn nếu client đã ngắt kết nối. Nếu upstream không hỗ trợ cancellation hoặc không giải phóng tài nguyên, hệ thống có thể tích lũy consumer, cursor, buffer hoặc listener không còn được sử dụng.

## 9. Truyền argument và lọc event

Subscription field có thể nhận argument để giới hạn tập event mà client muốn theo dõi:

```graphql
type Subscription {
    orderStatusChanged(orderId: ID!): OrderEvent!
}
```

Resolver:

```java
@SubscriptionMapping
Flux<OrderEvent> orderStatusChanged(@Argument("orderId") String orderId) {
    return eventPublisher.eventsForOrder(orderId);
}
```

Argument giúp lọc event theo order ID. Có thể thêm filter như loại sự kiện hoặc trạng thái, nhưng cần giới hạn độ rộng subscription để một client không đăng ký luồng quá lớn ngoài nhu cầu.

Không nên dùng argument do client gửi làm căn cứ duy nhất để quyết định người dùng có quyền theo dõi tài nguyên đó hay không. Service cần kiểm tra quyền đọc order trước khi tạo publisher, và có thể cần kiểm tra lại quyền khi event được phát nếu quyền truy cập thay đổi trong thời gian subscription tồn tại.

## 10. Authentication và authorization cho subscription

Subscription có thể tồn tại trong nhiều phút hoặc nhiều giờ. Việc xác thực một lần khi mở kết nối không đồng nghĩa người dùng được phép nhận mọi event vô thời hạn.

Với WebSocket, Spring for GraphQL có thể kết hợp `AuthenticationWebSocketInterceptor` để lấy credentials từ `connection_init`, xác thực bằng `AuthenticationManager` hoặc `ReactiveAuthenticationManager` và truyền `SecurityContext` cho các request tiếp theo.

Resolver có thể nhận principal:

```java
@SubscriptionMapping
Flux<OrderEvent> orderStatusChanged(
        @Argument("orderId") String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    String subject = jwt.getSubject();
    return orderService.eventsVisibleTo(subject, orderId);
}
```

`eventsVisibleTo` cần xác minh người dùng có quyền đọc đơn hàng và chỉ phát event thuộc phạm vi được phép. Không dùng `userId` do client tự gửi để thay thế principal đã xác thực.

Với subscription dài hạn, cần chính sách cho token hết hạn, thu hồi quyền hoặc người dùng bị xóa khỏi tenant. Có thể đóng stream, yêu cầu client kết nối lại hoặc áp dụng kiểm tra quyền định kỳ/theo từng event. Lựa chọn phụ thuộc yêu cầu bảo mật và độ trễ của hệ thống.

## 11. Xử lý lỗi trong subscription stream

Cần phân biệt lỗi trước khi stream bắt đầu và lỗi xảy ra trong khi stream đang chạy:

- Lỗi parse, validation, argument coercion hoặc authentication khi đăng ký khiến operation không thể bắt đầu.
- Exception trong lúc tạo publisher hoặc kiểm tra quyền ban đầu có thể được ánh xạ thành GraphQL error.
- `onError` phát ra sau một thời gian stream hoạt động làm publisher kết thúc với lỗi; subscription không tự tiếp tục trừ khi pipeline có chính sách retry/fallback.

Ví dụ chuyển lỗi hạ tầng thành exception có ý nghĩa:

```java
@SubscriptionMapping
Flux<OrderEvent> orderStatusChanged(@Argument("orderId") String orderId) {
    return eventPublisher.eventsForOrder(orderId)
        .onErrorMap(
            BrokerUnavailableException.class,
            ex -> new OrderEventStreamException("Order event stream unavailable", ex)
        );
}
```

Exception handler có thể ánh xạ lỗi lúc khởi tạo hoặc lỗi được GraphQL quan sát thành GraphQL error phù hợp. Với lỗi xảy ra sau khi stream đã phát một số event, cần hiểu hành vi của transport và GraphQL execution: lỗi kết thúc publisher và client nhận thông báo lỗi operation, các event trước đó vẫn đã được gửi.

Chỉ retry khi nguồn event có thể reconnect an toàn và có cơ chế resume/offset để tránh mất hoặc lặp event. Retry mù có thể tạo khoảng trống dữ liệu hoặc gửi trùng thông báo. Không nên đổi mọi lỗi thành `Flux.empty()` vì client sẽ tưởng stream kết thúc bình thường.

## 12. Backpressure và giới hạn tài nguyên

`Flux` hỗ trợ Reactive Streams backpressure: subscriber có thể điều tiết số phần tử mà nó yêu cầu. Tuy nhiên, nguồn event bên ngoài có thể phát nhanh hơn tốc độ client nhận dữ liệu. Khi đó cần chính sách buffer hoặc giới hạn rõ ràng.

Một số lựa chọn:

| Chính sách | Khi phù hợp | Rủi ro cần cân nhắc |
|---|---|---|
| Buffer có giới hạn | Cần giữ event trong khoảng tải tăng ngắn | Khi đầy phải có cách xử lý overflow. |
| Drop event mới | Chỉ cần trạng thái gần nhất hoặc dữ liệu có thể lấy lại | Client có thể bỏ lỡ event. |
| Drop event cũ | Ưu tiên event mới nhất | Mất lịch sử chưa được gửi. |
| Latest value | Dashboard chỉ cần trạng thái mới nhất | Không phù hợp với audit/event cần đầy đủ. |
| Disconnect chậm | Không thể chấp nhận backlog hoặc memory tăng | Client cần reconnect và resume. |

Không dùng unbounded buffer cho subscription có thể tồn tại lâu. Một client chậm có thể làm bộ nhớ tăng liên tục. Hãy giới hạn số subscription, tốc độ phát, kích thước event và số event được buffer.

## 13. Kiểm thử subscription bằng `GraphQlTester`

Với subscription, dùng `executeSubscription()` để nhận một `Flux` các response thay vì gọi `execute()` như query thông thường. Có thể kết hợp `StepVerifier` để kiểm tra các event theo thứ tự:

```java
Flux<String> statuses = graphQlTester.document("""
        subscription {
            orderStatusChanged(orderId: "order-01") {
                currentStatus
            }
        }
        """)
    .executeSubscription()
    .toFlux("orderStatusChanged.currentStatus", String.class);

StepVerifier.create(statuses)
    .expectNext("CONFIRMED", "SHIPPING")
    .thenCancel()
    .verify();
```

Ví dụ minh họa; `graphQlTester` cần được cấu hình với subscription handler và nguồn event có thể điều khiển trong test. `executeSubscription()` trả về luồng response; `toFlux(path, type)` trích giá trị từ từng response event.

Nên kiểm tra:

- Subscription trả các event đúng thứ tự và đúng selection set.
- Argument lọc chỉ nhận event phù hợp.
- Event không thuộc tài nguyên được phép không bị gửi cho người dùng.
- Publisher hoàn tất thì subscription kết thúc.
- Publisher phát lỗi thì client nhận lỗi theo hợp đồng.
- Client cancellation làm upstream cleanup được gọi.
- Slow subscriber không làm buffer tăng vô hạn.

Để kiểm tra transport thật, dùng `WebSocketGraphQlTester` kết nối tới endpoint WebSocket đang chạy. Kiểm thử này có thể xác minh `connection_init`, authentication, `subscribe`, nhiều `next` message và cancellation. Test ở tầng `GraphQlTester` giúp kiểm tra resolver/execution; test WebSocket giúp kiểm tra cả protocol và transport.

## 14. Lỗi thường gặp

**Dùng `@QueryMapping` cho subscription root.** Field thuộc `Subscription` cần được ánh xạ bằng `@SubscriptionMapping` hoặc `@SchemaMapping(typeName = "Subscription")`.

**Trả về một object thay vì publisher.** Subscription cần một nguồn phát nhiều kết quả theo thời gian. Dùng `Flux<T>` hoặc `Publisher<T>` phù hợp.

**Gọi `subscribe()` hoặc `block()` trong resolver.** Spring cần quản lý publisher. Trả `Flux` trực tiếp để framework điều khiển lifecycle.

**Không cấu hình transport streaming.** HTTP request/response thông thường không duy trì một subscription stream. Cấu hình WebSocket hoặc transport hỗ trợ streaming.

**Cho rằng mỗi client nhận được mọi event từ sink trong bộ nhớ.** Multicast sink cục bộ không thay thế message broker dùng chung giữa nhiều instance và không tự bảo đảm lưu trữ event.

**Không xử lý cancellation.** Client đã ngắt nhưng consumer vẫn chạy sẽ gây rò rỉ tài nguyên. Đảm bảo cancellation truyền tới nguồn event.

**Không giới hạn buffer và số subscription.** Client chậm hoặc đăng ký quá nhiều có thể làm hệ thống cạn tài nguyên. Đặt giới hạn và chính sách overflow.

**Chỉ xác thực khi mở kết nối mà bỏ qua thay đổi quyền.** Subscription dài hạn cần chính sách cho token hết hạn, thu hồi quyền và tenant membership thay đổi.

**Retry stream mà không có resume strategy.** Có thể mất hoặc gửi lặp event. Dùng offset/cursor hoặc cơ chế replay nếu cần đảm bảo tính liên tục.

## Kết luận

Subscription operation cho phép client nhận nhiều kết quả GraphQL theo thời gian. Trong Spring for GraphQL, khai báo field trên root `Subscription`, ánh xạ bằng `@SubscriptionMapping` và trả về `Flux<T>` hoặc `Publisher<T>`. Event source có thể là Reactor sink cho ví dụ đơn giản hoặc message broker cho hệ thống nhiều instance. Cần cấu hình transport như WebSocket, quản lý lifecycle và cancellation, xử lý lỗi trong stream, kiểm soát backpressure và xác thực/ủy quyền theo principal. Dùng `GraphQlTester` cùng `StepVerifier`, sau đó kiểm thử WebSocket thực tế để xác minh toàn bộ operation.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers: Subscription Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL Specification — Subscription](https://spec.graphql.org/October2021/#sec-Subscription)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
