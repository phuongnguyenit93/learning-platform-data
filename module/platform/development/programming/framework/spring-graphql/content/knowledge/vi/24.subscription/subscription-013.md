# Subscription với RSocket trong Spring for GraphQL

RSocket là một giao thức truyền thông điệp bất đồng bộ, hỗ trợ nhiều kiểu tương tác trên cùng một kết nối. Spring for GraphQL có thể dùng RSocket làm transport cho GraphQL: query và mutation được gửi theo kiểu `request-response`, còn subscription được gửi theo kiểu `request-stream`. Nhờ đó, client có thể nhận nhiều kết quả GraphQL trên một luồng mà không cần tự xây dựng cơ chế polling.

RSocket có thể chạy trên TCP hoặc WebSocket. Khi dùng WebSocket làm lớp truyền tải, payload vẫn là RSocket frame và tuân theo RSocket protocol; đây không phải GraphQL over WebSocket protocol `graphql-transport-ws`. Điểm quan trọng của bài này là cách ánh xạ subscription GraphQL sang RSocket stream, cấu hình server và client trong Spring, quản lý vòng đời, bảo mật, backpressure và kiểm thử.

## 1. RSocket phù hợp với subscription như thế nào?

RSocket định nghĩa các interaction model để hai phía trao đổi dữ liệu bất đồng bộ:

| Interaction model | Mô tả | Cách GraphQL thường sử dụng |
|---|---|---|
| Request-response | Một request nhận tối đa một response | Query và mutation. |
| Request-stream | Một request mở luồng có thể phát nhiều response | Subscription. |
| Fire-and-forget | Gửi payload mà không chờ response | Không phải cách thực thi GraphQL operation thông thường. |
| Request-channel | Hai phía trao đổi một luồng payload | Không phải mapping mặc định của GraphQL operation. |

Ví dụ hệ thống quản lý đơn hàng:

- Query `order(id)` lấy trạng thái đơn hàng tại thời điểm gọi.
- Mutation `updateOrderStatus(id, status)` thay đổi trạng thái và trả kết quả sau khi xử lý.
- Subscription `orderStatusChanged(orderId)` mở một request-stream và nhận các event trạng thái mới.

Với RSocket, query/mutation và subscription có thể dùng cùng route GraphQL nhưng được phân biệt bằng kiểu operation và interaction model. Server xử lý query/mutation như một response đơn, còn subscription trả về một `Flux` kết quả.

## 2. Phân biệt RSocket qua TCP và RSocket qua WebSocket

RSocket là giao thức, còn TCP và WebSocket là các lựa chọn transport để mang RSocket frame.

| Lựa chọn | Endpoint ví dụ | Đặc điểm |
|---|---|---|
| RSocket qua TCP | `localhost:9898` | Kết nối TCP trực tiếp, thường phù hợp giao tiếp service-to-service hoặc client native. |
| RSocket qua WebSocket | `ws://localhost:8080/rsocket` | RSocket frame đi qua WebSocket, hữu ích khi hạ tầng hoặc môi trường client cần WebSocket. |

RSocket qua WebSocket không đồng nghĩa với GraphQL over WebSocket. Với GraphQL over WebSocket, hai bên trao đổi message như `connection_init`, `subscribe`, `next` theo protocol GraphQL. Với RSocket qua WebSocket, hai bên trao đổi RSocket frame; GraphQL request được đóng gói trong payload của RSocket.

RSocket cũng khác HTTP polling. Một session có thể tồn tại lâu dài, multiplex nhiều request/stream trên cùng kết nối và hỗ trợ flow control. Client không cần mở một HTTP connection mới cho từng event.

## 3. Dependencies cho Spring Boot

Một ứng dụng GraphQL cần starter GraphQL và starter cung cấp RSocket server/client infrastructure:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
}
```

`spring-boot-starter-rsocket` cung cấp hạ tầng RSocket dựa trên Spring Messaging và Reactor Netty. Spring Boot có thể chạy RSocket server độc lập qua TCP/WebSocket hoặc tích hợp RSocket WebSocket vào ứng dụng WebFlux.

Nếu chỉ xây dựng client gọi tới một RSocket server bên ngoài, cần các dependency client tương ứng trong ứng dụng; không nhất thiết phải bật RSocket server trong chính ứng dụng client.

## 4. Cấu hình RSocket server và route GraphQL

Spring Boot cần biết hai thông tin:

1. RSocket server lắng nghe ở transport/địa chỉ nào.
2. GraphQL handler được gắn với route RSocket nào.

### RSocket server độc lập qua TCP

Ví dụ chạy server trên port `9898`, route GraphQL là `graphql`:

```yaml
spring:
  rsocket:
    server:
      port: 9898
  graphql:
    rsocket:
      mapping: graphql
```

### RSocket qua WebSocket trong WebFlux

Với ứng dụng WebFlux chạy trên Reactor Netty, có thể gắn RSocket vào web server:

```yaml
spring:
  rsocket:
    server:
      mapping-path: /rsocket
      transport: websocket
  graphql:
    rsocket:
      mapping: graphql
```

Client kết nối WebSocket tới `/rsocket` và gửi request tới route `graphql`. Cấu hình `mapping-path` là đường dẫn WebSocket transport; `spring.graphql.rsocket.mapping` là route GraphQL bên trong RSocket. Hai giá trị này phục vụ hai lớp khác nhau.

Việc gắn RSocket WebSocket vào web server được hỗ trợ với WebFlux và Reactor Netty. Nếu dùng RSocket TCP độc lập, cấu hình `spring.rsocket.server.port` là đủ cho transport server.

## 5. Server xử lý GraphQL RSocket bằng `GraphQlRSocketHandler`

Spring for GraphQL cung cấp `GraphQlRSocketHandler` để chuyển payload RSocket thành GraphQL request và gọi GraphQL execution. Khi tự khai báo route bằng Spring Messaging, có thể dùng một controller làm delegate:

```java
import java.util.Map;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.graphql.server.GraphQlRSocketHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
class GraphQlRSocketController {

    private final GraphQlRSocketHandler handler;

    GraphQlRSocketController(GraphQlRSocketHandler handler) {
        this.handler = handler;
    }

    @MessageMapping("graphql")
    Mono<Map<String, Object>> handle(Map<String, Object> payload) {
        return handler.handle(payload);
    }

    @MessageMapping("graphql")
    Flux<Map<String, Object>> handleSubscription(Map<String, Object> payload) {
        return handler.handleSubscription(payload);
    }
}
```

Hai handler dùng cùng route `graphql`:

- `handler.handle(payload)` xử lý query/mutation và trả một response map trong `Mono`.
- `handler.handleSubscription(payload)` xử lý subscription và trả nhiều response map trong `Flux`.

Đây là cách wiring tường minh bằng `GraphQlRSocketHandler`. Khi dùng Spring Boot auto-configuration cho GraphQL RSocket route, cấu hình route bằng `spring.graphql.rsocket.mapping` theo hướng dẫn của Boot và tránh đăng ký thêm một route trùng lặp ngoài ý muốn.

Payload chứa GraphQL request, thường có các thuộc tính `query`, `operationName`, `variables` và `extensions`. Client không cần tự tạo payload map nếu dùng `RSocketGraphQlClient`; client sẽ đóng gói operation theo định dạng mà Spring for GraphQL mong đợi.

## 6. Subscription resolver vẫn dùng `@SubscriptionMapping`

RSocket là transport, không làm thay đổi schema hoặc cách viết annotated controller. Subscription field vẫn được khai báo trong SDL và ánh xạ bằng `@SubscriptionMapping`.

SDL:

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

Resolver:

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

GraphQL Java thực thi subscription source và tạo một execution result cho mỗi event. `GraphQlRSocketHandler.handleSubscription` chuyển các kết quả đó thành một RSocket `request-stream` response.

## 7. Tạo event publisher cho subscription

Trong ví dụ nhỏ chạy một instance, có thể dùng Reactor `Sinks.Many` làm event source:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
class OrderEventPublisher {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventPublisher.class);

    private final Sinks.Many<OrderEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer();

    Flux<OrderEvent> eventsForOrder(String orderId) {
        return sink.asFlux()
            .filter(event -> event.orderId().equals(orderId));
    }

    void publish(OrderEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            log.warn("Cannot emit order event: {}", result);
        }
    }
}
```

Đây là event bus trong bộ nhớ để minh họa. `multicast()` phân phối event cho subscriber đang hoạt động; subscriber đến sau không tự nhận lại các event đã phát trước đó. `tryEmitNext` có thể trả `EmitResult` thất bại, vì vậy ứng dụng cần xử lý kết quả thay vì giả định event luôn được phát thành công.

Với hệ thống nhiều instance, mỗi process có sink riêng. Nếu mutation được xử lý ở instance A nhưng subscription của client nằm ở instance B, event trong bộ nhớ của A không tự truyền sang B. Production thường cần broker hoặc event platform dùng chung như Kafka, RabbitMQ hoặc Redis Streams/Pub/Sub, tùy yêu cầu replay, ordering và delivery guarantee.

## 8. Phát event sau khi mutation thay đổi dữ liệu

Mutation thường lưu trạng thái mới trước rồi phát event. Ví dụ service reactive:

Các kiểu dữ liệu minh họa:

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

Repository trong ví dụ có thể là reactive repository:

```java
interface OrderRepository extends ReactiveCrudRepository<Order, String> {}
```

```java
@Service
class OrderService {

    private final OrderRepository repository;
    private final OrderEventPublisher eventPublisher;

    OrderService(OrderRepository repository, OrderEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    Mono<Order> updateStatus(String id, OrderStatus newStatus) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
            .flatMap(order -> {
                OrderStatus previous = order.status();
                Order updated = order.withStatus(newStatus);

                return repository.save(updated)
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

Các kiểu `Order`, `OrderEvent`, `OrderStatus` và repository cần được định nghĩa theo domain của ứng dụng. Trong hệ thống có transaction database và broker, tránh phát event trước khi transaction commit nếu subscriber có thể nhìn thấy event cho thay đổi sau đó bị rollback. Outbox pattern hoặc transaction-aware event publishing giúp giảm nguy cơ dữ liệu và event không nhất quán.

## 9. Tạo RSocket GraphQL client

Spring for GraphQL cung cấp `RSocketGraphQlClient`, một implementation của `GraphQlClient`. Client này dùng `RSocketRequester` để gửi GraphQL request qua RSocket.

### Kết nối qua TCP

```java
RSocketGraphQlClient client = RSocketGraphQlClient.builder()
    .tcp("localhost", 9898)
    .route("graphql")
    .build();
```

### Kết nối qua WebSocket

```java
RSocketGraphQlClient client = RSocketGraphQlClient.builder()
    .webSocket(URI.create("ws://localhost:8080/rsocket"))
    .route("graphql")
    .build();
```

Khi dùng Spring Boot, có thể inject `RSocketGraphQlClient.Builder<?>` đã được auto-configure rồi gọi `tcp(...)` hoặc `webSocket(...)` và `route(...)` để tạo client.

RSocket client là connection-oriented và multiplexed. Một client instance duy trì một session dùng chung cho nhiều request. Nên tái sử dụng một `RSocketGraphQlClient` cho mỗi server thay vì tạo một instance mới cho từng operation, nếu mục tiêu là chia sẻ session.

## 10. Gửi query và mutation qua request-response

API của `RSocketGraphQlClient` dùng cùng workflow `GraphQlClient` như các transport khác.

Query:

```java
Mono<Order> order = client.document("""
        query {
            order(id: "order-01") {
                id
                status
            }
        }
        """)
    .retrieve("order")
    .toEntity(Order.class);
```

Mutation:

```java
Mono<Order> updated = client.document("""
        mutation {
            updateOrderStatus(id: "order-01", status: SHIPPING) {
                id
                status
            }
        }
        """)
    .retrieve("updateOrderStatus")
    .toEntity(Order.class);
```

Hai operation này được gửi như RSocket `request-response`, vì mỗi operation tạo một GraphQL response đơn. Với mutation có side effect, vẫn cần tuân thủ quy tắc idempotency và xử lý timeout/retry cẩn thận: client không phải lúc nào cũng biết server đã thực hiện mutation hay chưa khi kết nối bị ngắt trước khi response về.

## 11. Đăng ký subscription qua RSocket request-stream

Để nhận nhiều event, dùng `retrieveSubscription(...)` thay vì `retrieve(...)`:

```java
Flux<OrderEvent> events = client.document("""
        subscription WatchOrder($orderId: ID!) {
            orderStatusChanged(orderId: $orderId) {
                orderId
                previousStatus
                currentStatus
                occurredAt
            }
        }
        """)
    .variable("orderId", "order-01")
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class);
```

`retrieveSubscription` trả về `Flux<OrderEvent>`. Mỗi event từ server được giải mã thành một object. Ở tầng RSocket, operation này dùng interaction model `request-stream`, cho phép server phát nhiều response trên cùng request.

Nếu cần xử lý toàn bộ GraphQL response, bao gồm errors và các field khác, có thể dùng `executeSubscription()` thay cho shortcut `retrieveSubscription()`:

```java
Flux<ClientGraphQlResponse> responses = client.document("""
        subscription {
            orderStatusChanged(orderId: "order-01") {
                currentStatus
            }
        }
        """)
    .executeSubscription();
```

Với `executeSubscription`, client tự đọc field và kiểm tra error theo nhu cầu. Với `retrieveSubscription`, client thuận tiện lấy một response path duy nhất.

## 12. Session lifecycle: `start()`, `stop()` và reconnect

`RSocketGraphQlClient` có lifecycle riêng:

- `start()` chủ động mở session trước khi gửi request đầu tiên.
- Nếu chưa gọi `start()`, session được thiết lập tự động khi client bắt đầu gửi request.
- `stop()` đóng session, hủy các request đang chạy và từ chối request mới qua client đó.
- Nếu session mất, request tiếp theo hoặc lần gọi `start()` có thể thiết lập lại session.

Ví dụ:

```java
Mono<Void> started = client.start();

// Sau khi start hoàn tất, có thể gửi query hoặc subscription.

Mono<Void> stopped = client.stop();
```

Không nên gọi `stop()` ngay sau khi tạo một subscription cần tiếp tục chạy, vì thao tác này hủy các request đang hoạt động và đóng session. Trong ứng dụng, quản lý client như một bean có vòng đời rõ ràng và dừng nó khi component/application shutdown.

Session reconnect không đồng nghĩa subscription cũ tự được resume từ đúng event đã nhận cuối cùng. Khi kết nối mất, stream có thể kết thúc bằng transport error. Nếu nghiệp vụ cần tiếp tục từ một vị trí xác định, event source cần hỗ trợ cursor, offset hoặc resume token; client phải tạo subscription mới từ vị trí đó.

## 13. Cancellation và backpressure

RSocket `request-stream` hỗ trợ flow control. Client yêu cầu số lượng phần tử theo nhu cầu; server phát dữ liệu theo cơ chế request-n của RSocket và Reactive Streams. Điều này giúp điều tiết luồng event khi consumer xử lý chậm.

Khi client hủy `Flux` subscription, cancellation được truyền về RSocket stream. Server có thể hủy publisher GraphQL và upstream event source nếu các thành phần đó hỗ trợ cancellation.

Ví dụ client chỉ nhận tối đa 10 event:

```java
Flux<OrderEvent> firstTenEvents = client.document("""
        subscription {
            orderStatusChanged(orderId: "order-01") {
                orderId
                currentStatus
            }
        }
        """)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .take(10);
```

`take(10)` hoàn tất sau 10 phần tử và hủy upstream. Với subscription vô hạn, ứng dụng cần quản lý buffer, tốc độ phát và số stream đang hoạt động; không nên dùng unbounded buffer nếu nguồn event có thể phát nhanh hơn client trong thời gian dài.

## 14. Xử lý lỗi và mất kết nối

Cần phân biệt lỗi GraphQL với lỗi transport RSocket:

| Loại lỗi | Ví dụ | Phản ứng phía client |
|---|---|---|
| GraphQL request/execution error | Query sai schema, resolver ném exception | Đọc `errors`, `path`, `extensions` trong GraphQL response. |
| Subscription error từ server | Publisher kết thúc bằng lỗi được gửi như lỗi operation | `Flux` có thể kết thúc bằng `SubscriptionErrorException`; đọc GraphQL errors đi kèm. |
| Transport error | RSocket session bị đóng, server không thể truy cập | Xử lý `GraphQlTransportException`, reconnect hoặc tạo lại subscription nếu an toàn. |
| Timeout/cancellation | Client timeout hoặc chủ động hủy | Xác định operation đã hoàn tất chưa; không tự retry mutation nếu chưa có idempotency. |

Ví dụ xử lý lỗi stream:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .doOnError(error -> log.warn("Order subscription ended", error));
```

Không nên retry mọi lỗi một cách vô điều kiện. Nếu reconnect sau transport failure, server có thể đã phát một số event mà client chưa xử lý xong. Cần có event ID hoặc cursor nếu yêu cầu không mất/không trùng event. Retry mutation còn nhạy cảm hơn vì có thể thực hiện side effect lần thứ hai.

## 15. Bảo mật RSocket GraphQL

RSocket có cơ chế security riêng trong Spring Security. Có thể dùng `@EnableRSocketSecurity` để bật hỗ trợ xác thực và phân quyền payload. Hạ tầng security kết nối với RSocket server qua `SecuritySocketAcceptorInterceptor`.

Khi dùng Spring Boot với dependency RSocket Security phù hợp, Boot có thể tự đăng ký `SecuritySocketAcceptorInterceptor` vào RSocket server. Nếu tự cấu hình server ngoài Boot auto-configuration, cần gắn interceptor này vào socket acceptor theo hướng dẫn Spring Security.

Spring Security hỗ trợ authentication tại thời điểm setup, tại từng request hoặc cả hai. Lựa chọn phụ thuộc cách dùng session:

- Kết nối chỉ thuộc về một người dùng, chẳng hạn ứng dụng mobile: có thể xác thực lúc setup và gắn danh tính với session.
- Một kết nối được chia sẻ bởi nhiều người dùng, chẳng hạn gateway/service downstream: credentials cần được gửi và xác thực theo từng request để tránh dùng nhầm danh tính giữa người dùng.
- Hệ thống có cả identity của service và identity end-user: có thể xác thực ở setup cho service rồi truyền thông tin người dùng được xác minh theo từng request.

RSocket route `graphql` là route chung cho nhiều query, mutation và subscription. Vì vậy, route authorization chỉ là lớp bảo vệ đầu tiên. Quyền truy cập theo field và tài nguyên vẫn cần được kiểm tra trong service bằng method security hoặc logic nghiệp vụ. Không dựa vào GraphQL argument do client gửi làm bằng chứng danh tính.

Với subscription dài hạn, cần quy định hành vi khi token hết hạn, quyền bị thu hồi hoặc tenant membership thay đổi. Có thể đóng stream, yêu cầu client xác thực lại hoặc kiểm tra quyền khi phát event tùy yêu cầu bảo mật.

## 16. Interception và GraphQL context trên RSocket

`WebGraphQlInterceptor` dành cho HTTP/WebSocket. Với RSocket, Spring for GraphQL cung cấp `RSocketQlInterceptor` để can thiệp request trước và sau khi GraphQL Java thực thi.

`RSocketQlInterceptor` có thể được dùng để:

- Đọc metadata từ RSocket request khi metadata được cấu hình và có thể truy cập qua transport integration.
- Bổ sung thông tin vào `ExecutionInput` hoặc `GraphQLContext`.
- Quan sát hoặc biến đổi `ExecutionResult`.
- Ghi nhận metrics/correlation information cho request.

Không dùng `WebGraphQlInterceptor` với mục đích xử lý RSocket route. Hãy chọn interceptor đúng transport. Với authentication/authorization, ưu tiên Spring Security RSocket integration; interceptor GraphQL không thay thế xác minh credentials.

## 17. Kiểm thử subscription qua RSocket

Spring for GraphQL có `RSocketGraphQlTester` để gửi GraphQL request qua RSocket. Test dependency:

```groovy
testImplementation 'org.springframework.graphql:spring-graphql-test'
```

Ví dụ tạo tester dùng RSocket WebSocket transport:

```java
URI uri = URI.create("ws://localhost:8080/rsocket");
WebsocketClientTransport transport = WebsocketClientTransport.create(uri);

RSocketGraphQlTester tester = RSocketGraphQlTester.builder()
    .clientTransport(transport)
    .build();
```

`RSocketGraphQlTester` phù hợp để kiểm tra request-response qua RSocket. Với kiểm thử subscription stream end-to-end, có thể dùng `RSocketGraphQlClient` và `StepVerifier`:

```java
Flux<OrderEvent> events = client.document("""
        subscription {
            orderStatusChanged(orderId: "order-01") {
                currentStatus
            }
        }
        """)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class);

StepVerifier.create(events)
    .expectNextMatches(event -> event.currentStatus() == OrderStatus.CONFIRMED)
    .thenCancel()
    .verify();
```

Ví dụ minh họa; server, RSocket route, client session và event publisher cần được khởi chạy trong test context. Nên phát event từ test fixture sau khi subscription được đăng ký để tránh race condition. Có thể dùng `Sinks.Many` được điều khiển bởi test để quyết định chính xác event nào được phát.

Tài liệu kiểm thử Spring for GraphQL có `RSocketGraphQlTester`, nhưng hướng dẫn subscription test hiện mô tả hỗ trợ `WebSocketGraphQlTester` và các server-side tester. Vì vậy, khi cần xác minh stream RSocket thực tế, kiểm thử bằng `RSocketGraphQlClient` cùng `StepVerifier` là cách rõ ràng; không giả định mọi API tester đều có cùng hỗ trợ subscription.

## 18. Khi nào chọn RSocket thay cho WebSocket hoặc SSE?

| Tiêu chí | RSocket | GraphQL WebSocket | GraphQL SSE |
|---|---|---|---|
| Transport | TCP hoặc WebSocket | WebSocket | HTTP streaming |
| Query/mutation | Request-response | Có thể dùng một response | Không phải use case chính; SSE handler dành cho subscription. |
| Subscription | Request-stream | GraphQL WebSocket protocol | Server-Sent Events stream |
| Multiplexing | Nhiều interaction trên một session | Nhiều operation trên một connection | SSE handler dùng distinct connections mode. |
| Flow control | RSocket request-n và Reactive Streams | Phụ thuộc WebSocket transport và implementation | Phụ thuộc HTTP streaming/server. |
| Hệ sinh thái client | RSocketRequester, RSocketGraphQlClient | GraphQL WebSocket clients | HTTP/EventSource clients. |

RSocket phù hợp khi ứng dụng cần giao tiếp message-based, request-stream, multiplexing và flow control giữa các service hoặc client có hỗ trợ RSocket. WebSocket GraphQL thường dễ tích hợp hơn với browser và hệ sinh thái GraphQL subscription phổ biến. SSE có thể đơn giản cho client chỉ cần nhận event qua HTTP và không cần hai chiều.

Không chọn RSocket chỉ vì subscription. Hãy cân nhắc môi trường client, proxy/firewall, vận hành kết nối, bảo mật, quan sát hệ thống và khả năng hỗ trợ của hạ tầng.

## 19. Lỗi thường gặp

**Nhầm RSocket WebSocket với GraphQL over WebSocket.** RSocket dùng RSocket frame trên WebSocket; nó không trao đổi message `connection_init`/`subscribe` của `graphql-transport-ws`.

**Sai route giữa server và client.** `spring.graphql.rsocket.mapping` phải khớp với route client gọi, ví dụ `graphql`.

**Chỉ cấu hình GraphQL route mà chưa bật RSocket server.** Cần starter và cấu hình `spring.rsocket.server.*` phù hợp với TCP hoặc WebSocket.

**Dùng `request-response` cho subscription.** Subscription cần `request-stream`; server handler phải trả `Flux` qua `handleSubscription`.

**Tạo một `RSocketGraphQlClient` cho mỗi operation.** Mỗi client instance tạo session riêng. Tái sử dụng một client cho mỗi server khi cần chia sẻ session.

**Gọi `block()` hoặc `subscribe()` trong resolver.** Trả `Flux` để GraphQL và RSocket quản lý publisher, cancellation và backpressure.

**Giả định session reconnect sẽ resume event tự động.** Khi mất kết nối, subscription có thể kết thúc. Muốn resume cần cursor/offset và logic đăng ký lại.

**Bỏ qua authentication theo request trên kết nối chia sẻ.** Setup authentication một lần không đủ nếu nhiều người dùng chia sẻ cùng session; credentials end-user cần được ràng buộc đúng request.

**Dùng sink trong bộ nhớ cho nhiều instance.** Sink cục bộ không truyền event giữa các process. Dùng broker khi cần phân phối liên instance hoặc replay.

**Không kiểm soát backpressure và số stream.** Subscription lâu dài có thể tiêu thụ nhiều bộ nhớ, CPU và tài nguyên broker. Đặt giới hạn và chính sách cancellation/overflow.

## Kết luận

Spring for GraphQL ánh xạ query và mutation sang RSocket `request-response`, còn subscription sang `request-stream`. Ở server, `GraphQlRSocketHandler` thực thi payload GraphQL và trả `Mono` hoặc `Flux`; ở client, `RSocketGraphQlClient` dùng cùng API GraphQL nhưng hỗ trợ subscription qua `retrieveSubscription`. Cấu hình đúng RSocket server, route GraphQL và TCP/WebSocket transport; tái sử dụng client session, xử lý cancellation/backpressure, bảo mật theo setup hoặc từng request và thiết kế resume khi cần. Dùng `RSocketGraphQlClient` cùng `StepVerifier` để kiểm thử stream thực tế.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports: RSocket](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Boot — Spring for GraphQL: RSocket](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL — Client: RSocket and Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
