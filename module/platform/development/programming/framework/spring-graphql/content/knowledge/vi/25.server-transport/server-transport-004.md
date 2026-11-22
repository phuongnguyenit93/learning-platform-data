# WebSocket transport

GraphQL thường được gọi qua HTTP request và trả về một response. Cách này phù hợp với Query và Mutation, nhưng Subscription cần một kết nối có thể duy trì lâu dài để server gửi nhiều kết quả theo thời gian. **WebSocket transport** cung cấp kênh hai chiều giữa client và server, cho phép client đăng ký operation, nhận event và hủy đăng ký trên cùng một kết nối.

Spring for GraphQL hỗ trợ GraphQL over WebSocket bên cạnh HTTP và RSocket. WebSocket handler sử dụng GraphQL over WebSocket Protocol, chuyển từng operation tới GraphQL execution chain và gửi kết quả về client. Một WebSocket session có thể mang nhiều operation đồng thời, vì vậy ứng dụng cần quản lý xác thực, tài nguyên, timeout và vòng đời kết nối.

## Khi nào nên dùng WebSocket transport?

WebSocket phù hợp khi client cần nhận dữ liệu liên tục hoặc cần một kết nối hai chiều:

- Theo dõi trạng thái đơn hàng hoặc giao dịch.
- Nhận cập nhật tồn kho, giá hoặc trạng thái đấu giá.
- Nhận thông báo trực tiếp trong dashboard.
- Cập nhật dữ liệu cộng tác theo thời gian thực.
- Chạy nhiều GraphQL subscription trên một kết nối.

So sánh các transport:

| Transport | Cách trao đổi | Trường hợp thường dùng |
| --- | --- | --- |
| HTTP | Request và response riêng | Query, Mutation |
| Server-Sent Events (SSE) | Client gửi HTTP request, server stream event một chiều | Subscription khi client chỉ cần nhận dữ liệu |
| WebSocket | Kết nối hai chiều, nhiều message trong cùng session | Subscription, multiplex nhiều operation và tương tác hai chiều |
| RSocket | Giao thức message với request-response và request-stream | Hệ thống reactive hoặc giao tiếp service-to-service |

WebSocket không bắt buộc cho mọi Subscription. Nếu client chỉ cần nhận stream từ server và không cần giao tiếp hai chiều sau khi mở stream, SSE có thể đơn giản hơn. WebSocket hữu ích khi cần nhiều operation trên cùng connection, message điều khiển và cơ chế multiplex.

## Cấu hình WebSocket endpoint trong Spring Boot

Spring Boot không bật GraphQL WebSocket endpoint mặc định. Ứng dụng cần cấu hình path bằng thuộc tính spring.graphql.websocket.path.

Với ứng dụng Servlet/Spring MVC, thêm starter WebSocket:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-websocket")
}
~~~

Với ứng dụng Spring WebFlux, dùng WebFlux starter; không cần thêm spring-boot-starter-websocket riêng:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

Cấu hình endpoint và các giới hạn thời gian:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
      connection-init-timeout: 10s
      keep-alive: 25s
~~~

Ý nghĩa:

- path: đường dẫn WebSocket endpoint.
- connection-init-timeout: khoảng thời gian chờ message khởi tạo connection từ client. Spring Boot hiện dùng mặc định 60 giây nếu không cấu hình.
- keep-alive: khoảng thời gian tối đa không hoạt động trước khi server gửi ping để giữ kết nối.

Path WebSocket có thể trùng path HTTP nếu ứng dụng cấu hình như vậy. Client vẫn phải dùng scheme đúng: ws:// khi không mã hóa và wss:// khi dùng TLS. Trong môi trường production, ưu tiên WSS.

Không trộn starter MVC và WebFlux tùy tiện. Hãy chọn web stack theo kiến trúc ứng dụng để Spring Boot tạo đúng WebSocket handler và I/O model.

## GraphQL over WebSocket Protocol

Spring for GraphQL dùng giao thức GraphQL over WebSocket từ thư viện graphql-ws, với WebSocket subprotocol có tên **graphql-transport-ws**. Đây là giao thức mới thay thế giao thức cũ subscriptions-transport-ws; hai giao thức không tương thích với nhau.

Client và server cần thống nhất cùng subprotocol khi thiết lập WebSocket handshake. Nếu client chỉ hỗ trợ giao thức cũ, connection có thể được thiết lập ở tầng WebSocket nhưng không trao đổi được message GraphQL theo định dạng mà server mong đợi.

Các message chính:

| Message | Hướng | Ý nghĩa |
| --- | --- | --- |
| connection_init | Client → Server | Khởi tạo GraphQL session và có thể gửi payload xác thực |
| connection_ack | Server → Client | Server chấp nhận khởi tạo connection |
| subscribe | Client → Server | Gửi một GraphQL operation có ID |
| next | Server → Client | Gửi một kết quả của operation |
| error | Server → Client | Báo lỗi kết thúc operation |
| complete | Hai chiều | Báo operation hoàn tất hoặc client hủy operation |
| ping / pong | Hai chiều | Kiểm tra kết nối và giữ session hoạt động |

## Vòng đời một WebSocket connection

Một connection GraphQL thường trải qua các bước:

~~~mermaid
sequenceDiagram
    participant C as GraphQL Client
    participant W as WebSocket Endpoint
    participant G as GraphQL Engine
    participant S as Subscription Source

    C->>W: WebSocket handshake
    Note over C,W: Subprotocol graphql-transport-ws
    C->>W: connection_init
    W-->>C: connection_ack
    C->>W: subscribe (id, payload)
    W->>G: Execute GraphQL operation
    G->>S: Subscribe to event publisher
    S-->>G: Event
    G-->>C: next (id, result)
    S-->>G: Event
    G-->>C: next (id, result)
    C->>W: complete (id)
    W->>S: Cancel publisher
    W-->>C: Connection remains open
~~~

Chi tiết:

1. Client mở WebSocket connection và thương lượng subprotocol.
2. Client gửi connection_init, có thể kèm payload chứa thông tin xác thực.
3. Server xác nhận bằng connection_ack.
4. Client gửi subscribe với operation ID và payload GraphQL.
5. Server thực thi operation; với Subscription, mỗi event tạo một next message.
6. Khi stream kết thúc, server gửi complete hoặc error.
7. Client có thể gửi complete để hủy một operation mà vẫn giữ connection cho operation khác.

Server có thể yêu cầu connection_init trong thời gian giới hạn. Nếu client không gửi message này kịp thời, connection có thể bị đóng. Không nên xem WebSocket handshake thành công là GraphQL session đã sẵn sàng; hãy chờ connection_ack trước khi gửi operation.

## Một connection có thể multiplex nhiều operation

WebSocket session không tương đương một Subscription duy nhất. Client có thể gửi nhiều message subscribe với ID khác nhau trên cùng connection:

~~~json
{
  "id": "stock-1",
  "type": "subscribe",
  "payload": {
    "query": "subscription { stockChanged(productId: \"p-1\") { availableQuantity } }"
  }
}
~~~

Một operation khác có ID riêng:

~~~json
{
  "id": "order-1",
  "type": "subscribe",
  "payload": {
    "query": "subscription { orderChanged(orderId: \"o-10\") { status } }"
  }
}
~~~

Server phân biệt kết quả bằng operation ID:

~~~json
{
  "id": "stock-1",
  "type": "next",
  "payload": {
    "data": {
      "stockChanged": {
        "availableQuantity": 18
      }
    }
  }
}
~~~

Mỗi ID phải duy nhất trong connection tại cùng thời điểm. Client dùng complete với đúng ID để hủy operation tương ứng. Các subscription còn lại tiếp tục chạy cho tới khi hoàn tất, bị hủy hoặc connection đóng.

Multiplex giúp giảm số lượng socket mà client cần mở. Tuy nhiên, nó cũng khiến một connection có thể tiêu thụ nhiều tài nguyên server hơn; cần giới hạn số operation đồng thời và đo tải theo session.

## Message subscribe chứa GraphQL operation

Payload của subscribe chứa nội dung tương tự GraphQL request thông thường:

~~~json
{
  "id": "order-watch-1",
  "type": "subscribe",
  "payload": {
    "operationName": "WatchOrder",
    "query": "subscription WatchOrder($id: ID!) { orderChanged(orderId: $id) { id status updatedAt } }",
    "variables": {
      "id": "order-100"
    }
  }
}
~~~

Server xử lý query document, operation name và variables theo GraphQL semantics. WebSocket chỉ là transport; nó không thay đổi cách GraphQL kiểm tra schema, argument, selection set, resolver hay authorization.

WebSocket cũng có thể dùng cho Query hoặc Mutation trả một kết quả. Tuy nhiên, trong ứng dụng thông thường, HTTP vẫn là lựa chọn đơn giản cho request-response; WebSocket thường được bật để hỗ trợ Subscription hoặc nhiều operation trên cùng session.

## Ánh xạ Subscription vẫn dùng @SubscriptionMapping

Transport không làm thay đổi cách khai báo resolver. Subscription field vẫn được ánh xạ bằng @SubscriptionMapping và thường trả Flux<T>:

~~~graphql
type Subscription {
  orderChanged(orderId: ID!): OrderEvent!
}

type OrderEvent {
  id: ID!
  orderId: ID!
  status: String!
  updatedAt: String!
}
~~~

DTO Java có thể biểu diễn cùng các field:

~~~java
public record OrderEvent(
        String id,
        String orderId,
        String status,
        String updatedAt) {
}
~~~

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class OrderSubscriptionController {

    private final OrderEventService eventService;

    public OrderSubscriptionController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<OrderEvent> orderChanged(@Argument String orderId) {
        return eventService.eventsFor(orderId);
    }
}
~~~

Khi client gửi operation qua WebSocket, Spring GraphQL gọi cùng annotated controller và service như khi thực thi subscription qua transport hỗ trợ streaming khác. Mỗi phần tử Flux được GraphQL runtime phân giải thành một payload theo selection set.

## Xác thực qua HTTP handshake hoặc connection_init

WebSocket có hai thời điểm thường dùng để xác thực:

**HTTP handshake**

WebSocket bắt đầu bằng HTTP upgrade request. Ứng dụng có thể xác thực cookie hoặc HTTP header ở tầng Spring Security trước khi chấp nhận handshake. Principal đã xác thực có thể được dùng trong các GraphQL request sau đó trên connection.

**GraphQL connection_init payload**

Client có thể gửi thông tin xác thực trong message connection_init:

~~~json
{
  "type": "connection_init",
  "payload": {
    "Authorization": "Bearer <access-token>"
  }
}
~~~

Spring for GraphQL cung cấp AuthenticationWebSocketInterceptor tích hợp cho cả MVC và WebFlux để đọc thông tin xác thực từ payload connection_init, xác thực và truyền SecurityContext tới các request tiếp theo trên connection. Chọn cơ chế phù hợp với cách client cấp credential và cấu hình Spring Security của ứng dụng.

Không đưa token vào query string vì URL có thể xuất hiện trong access log, browser history, proxy log hoặc telemetry. Payload và header xác thực cũng không được ghi nguyên văn vào log.

## WebSocketGraphQlInterceptor và WebGraphQlInterceptor

Spring for GraphQL có hai cấp interception:

| Interceptor | Phạm vi | Công việc |
| --- | --- | --- |
| WebGraphQlInterceptor | Từng GraphQL request trên HTTP hoặc WebSocket | Đọc request, bổ sung GraphQLContext, thay đổi ExecutionInput hoặc response |
| WebSocketGraphQlInterceptor | Vòng đời WebSocket connection và request trên connection | Xử lý bắt đầu/kết thúc connection, cancellation và các callback WebSocket |

WebSocketGraphQlInterceptor mở rộng WebGraphQlInterceptor. Nó bổ sung callback cho vòng đời kết nối và client cancellation. Trong một interceptor chain chỉ được có tối đa một WebSocketGraphQlInterceptor; các WebGraphQlInterceptor thông thường vẫn có thể xử lý từng GraphQL operation.

Spring Boot tự đăng ký bean WebGraphQlInterceptor với web transport. Nếu cần xử lý lifecycle riêng của WebSocket, hãy cấu hình WebSocketGraphQlInterceptor trong chain của WebGraphQlHandler theo cơ chế tương ứng với phiên bản Spring for GraphQL đang dùng.

Không dùng interceptor connection-level để thay thế authorization của từng field. Một người dùng có thể đăng ký nhiều operation với resource khác nhau trên cùng connection; mỗi operation vẫn cần kiểm tra quyền truy cập phù hợp.

## Bảo mật subscription lâu dài

Xác thực connection chỉ xác định danh tính tại thời điểm thiết lập session. Một subscription có thể tồn tại lâu hơn access token hoặc phiên đăng nhập. Ứng dụng cần quyết định cách xử lý khi:

- Token hết hạn trong lúc connection còn mở.
- Người dùng đăng xuất hoặc bị khóa tài khoản.
- Quyền truy cập một order hoặc tenant bị thu hồi.
- Một operation mới yêu cầu resource khác trên cùng connection.
- Client gửi quá nhiều operation hoặc payload quá lớn.

Hãy kiểm tra quyền tại thời điểm đăng ký operation và cân nhắc kiểm tra lại trong lúc stream hoạt động nếu quyền có thể thay đổi. Khi credential hết hạn hoặc principal bị thu hồi, có thể hủy operation hoặc đóng connection theo chính sách bảo mật.

Với cookie authentication, cần xem xét Cross-Site WebSocket Hijacking. Kiểm tra Origin của handshake, cấu hình allowed origins cụ thể, bảo vệ cookie bằng thuộc tính phù hợp và áp dụng chính sách xác thực/CSRF tương ứng. CORS cho HTTP endpoint không tự động thay thế kiểm tra Origin và xác thực WebSocket handshake.

## Keep-alive, timeout và connection lifecycle

WebSocket có thể tồn tại lâu mà không gửi message. Proxy, load balancer hoặc NAT có thể đóng kết nối idle. GraphQL over WebSocket hỗ trợ ping và pong; Spring Boot có thuộc tính spring.graphql.websocket.keep-alive để cấu hình server gửi ping khi connection không hoạt động.

Client cũng có thể gửi ping để kiểm tra kết nối. Cần phân biệt:

- **WebSocket ping/pong:** kiểm tra tầng kết nối.
- **GraphQL connection_init/connection_ack:** khởi tạo GraphQL session.
- **Operation subscribe/next/complete:** vòng đời từng GraphQL operation.

connection-init-timeout giới hạn thời gian chờ message khởi tạo session. Nó không phải timeout cho mỗi Subscription. Timeout operation hoặc thời gian sống subscription cần được thiết kế riêng theo nghiệp vụ.

Khi client đóng connection, server phải hủy các operation còn hoạt động và giải phóng đăng ký event source. Nếu client reconnect, đó là một connection mới; ứng dụng không nên giả định subscription cũ tự tiếp tục. Muốn resume, cần cursor hoặc event ID và nguồn dữ liệu hỗ trợ đọc tiếp từ vị trí trước đó.

## Quản lý tài nguyên và giới hạn session

Một WebSocket connection có thể chứa nhiều Subscription đồng thời. Spring for GraphQL khuyến nghị cấu hình giới hạn tài nguyên phù hợp:

- Số lượng connection mở tối đa ở web server hoặc connector.
- Kích thước message buffer tối đa của WebSocket container.
- Số subscription đồng thời trên một session.
- Timeout kết nối và khoảng thời gian keep-alive.
- Kích thước payload và giới hạn độ sâu/độ phức tạp GraphQL operation.
- Số subscription trên mỗi user, tenant hoặc client.

GraphQlWebSocketHandler có tùy chọn maxSubscriptionsPerSession khi tự cấu hình handler. Mặc định không giới hạn; khi đạt giới hạn được cấu hình, session có thể bị đóng. Với Spring MVC, giới hạn message buffer được cấu hình qua Jakarta WebSocket ServerContainer; với WebFlux, cấu hình tương ứng phụ thuộc reactive server đang sử dụng.

Không dùng một con số giới hạn chung cho mọi hệ thống. Hãy dựa trên kích thước payload, tần suất event, memory, CPU và khả năng của event source. Theo dõi số connection đang mở, số operation đang chạy, tốc độ event, lỗi và cancellation để điều chỉnh.

## Reverse proxy và triển khai nhiều instance

Khi WebSocket đi qua reverse proxy hoặc load balancer, cần hỗ trợ HTTP Upgrade và giữ kết nối sau khi handshake:

- Cho phép header Upgrade và Connection được chuyển tiếp.
- Dùng timeout idle đủ dài cho kết nối WebSocket.
- Bảo đảm proxy không buffer hoặc đóng stream theo timeout HTTP ngắn.
- Dùng TLS/WSS ở public endpoint.
- Kiểm tra health, giới hạn connection và giới hạn message ở server.

Sau khi handshake thành công, connection gắn với instance đã nhận nó. Nếu client reconnect, load balancer có thể chuyển sang instance khác. Vì vậy, event source và trạng thái cần dùng chung giữa các instance nên dựa vào broker hoặc hệ thống phân phối bên ngoài; không phụ thuộc một Sinks hoặc collection trong bộ nhớ của một process.

Sticky session có thể hữu ích với một số hạ tầng, nhưng không thay thế event infrastructure dùng chung và không giải quyết việc phục hồi subscription sau khi connection bị mất.

## CORS và Origin của WebSocket

HTTP CORS điều khiển việc trình duyệt đọc response từ origin khác và xử lý preflight. WebSocket handshake có header Origin nhưng không dùng CORS preflight theo cách HTTP request thông thường. Vì vậy, cần cấu hình kiểm tra allowed origins tại tầng WebSocket endpoint hoặc security/proxy tương ứng.

Chỉ cho phép origin frontend đáng tin cậy. Không chấp nhận mọi origin khi endpoint dùng cookie hoặc thông tin xác thực của người dùng. Origin validation là một lớp bảo vệ chống truy cập cross-site; nó không thay thế authentication và authorization.

## Kiểm thử bằng WebSocketGraphQlTester

Spring for GraphQL cung cấp WebSocketGraphQlTester để kiểm thử GraphQL qua WebSocket. Tester dùng một WebSocketClient và giữ một kết nối dùng chung cho các request; có thể gọi stop() để đóng kết nối sau test.

Dependency test:

~~~kotlin
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

Tạo tester:

~~~java
import java.net.URI;

import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

URI url = URI.create("ws://localhost:8080/graphql");
WebSocketClient client = new ReactorNettyWebSocketClient();

WebSocketGraphQlTester tester =
        WebSocketGraphQlTester.builder(url, client).build();
~~~

Thực thi subscription:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<OrderEvent> events = tester.document("""
        subscription WatchOrder($id: ID!) {
            orderChanged(orderId: $id) {
                id
                orderId
                status
                updatedAt
            }
        }
        """)
        .variable("id", "order-100")
        .executeSubscription()
        .toFlux("orderChanged", OrderEvent.class);

StepVerifier.create(events.take(2))
        .expectNextMatches(event ->
                event.orderId().equals("order-100"))
        .expectNextMatches(event ->
                event.orderId().equals("order-100"))
        .verifyComplete();

tester.stop();
~~~

executeSubscription() trả về stream response. toFlux() trích dữ liệu từ path trong mỗi payload để StepVerifier kiểm tra event. Khi dùng take(2), Flux test hủy subscription sau hai phần tử; transport gửi message complete để server hủy operation tương ứng.

Nên kiểm thử:

- Client và server thương lượng đúng subprotocol.
- connection_init được xử lý và connection_ack được nhận.
- Subscription nhận nhiều payload theo đúng operation ID.
- Hai subscription trên cùng connection không trộn dữ liệu.
- Client cancel một operation nhưng operation khác vẫn hoạt động.
- Connection close làm hủy các publisher đang chạy.
- Credential không hợp lệ bị từ chối.
- Connection-init timeout, keep-alive và reconnect được xử lý đúng.
- Giới hạn số operation và kích thước message có hiệu lực.
- Proxy hoặc môi trường production không đóng connection quá sớm.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| HTTP GraphQL hoạt động nhưng WebSocket không kết nối | Endpoint WebSocket chưa bật | Cấu hình spring.graphql.websocket.path |
| Servlet app không có WebSocket handler | Thiếu WebSocket starter | Thêm spring-boot-starter-websocket |
| Client không nhận connection_ack | Thiếu connection_init, sai protocol hoặc lỗi xác thực | Kiểm tra subprotocol, payload và init timeout |
| Server không nhận operation | Client dùng protocol cũ | Dùng graphql-transport-ws |
| Nhiều subscription bị trộn kết quả | Client dùng ID trùng hoặc xử lý multiplex sai | Dùng ID duy nhất và route message theo ID |
| Unsubscribe nhưng publisher vẫn chạy | Cancellation không truyền tới nguồn | Kiểm tra callback cancellation và cleanup |
| Kết nối bị đóng khi idle | Proxy timeout hoặc keep-alive chưa phù hợp | Cấu hình ping/pong và timeout proxy |
| WebSocket hoạt động trong local nhưng lỗi sau proxy | Không chuyển tiếp Upgrade hoặc Origin bị chặn | Kiểm tra proxy headers và allowed origins |
| Người dùng nhận dữ liệu ngoài quyền | Chỉ xác thực lúc handshake, không kiểm tra từng operation | Áp dụng authorization theo resource |
| Server hết bộ nhớ | Quá nhiều connection, subscription hoặc message buffer | Đặt giới hạn và theo dõi metric |
| Reconnect nhưng mất event | Connection mới không tự khôi phục subscription cũ | Thiết kế cursor/replay và resubscribe |

## Nguyên tắc thiết kế WebSocket transport

Khi triển khai WebSocket transport cho Spring for GraphQL, hãy nhớ:

1. **Bật endpoint tường minh.** Cấu hình spring.graphql.websocket.path; chọn starter theo MVC hoặc WebFlux.
2. **Dùng đúng protocol.** Client và server phải hỗ trợ graphql-transport-ws, không dùng giao thức cũ subscriptions-transport-ws.
3. **Chờ connection acknowledgement.** Gửi connection_init và đợi connection_ack trước khi subscribe.
4. **Multiplex bằng operation ID riêng.** Một connection có thể mang nhiều operation nhưng mỗi ID phải duy nhất.
5. **Tách connection lifecycle khỏi operation lifecycle.** WebSocketGraphQlInterceptor xử lý connection; WebGraphQlInterceptor xử lý từng GraphQL request.
6. **Xác thực và phân quyền đúng phạm vi.** Kiểm tra handshake hoặc connection payload, sau đó vẫn kiểm tra quyền cho từng operation và resource.
7. **Cấu hình keep-alive và timeout.** Đồng bộ server, client, reverse proxy và load balancer.
8. **Giới hạn tài nguyên.** Kiểm soát connection, concurrent subscriptions, message buffer và payload size.
9. **Thiết kế reconnect có cursor.** Connection mới không tự tiếp tục các operation cũ.
10. **Kiểm thử bằng WebSocketGraphQlTester.** Xác minh protocol, multiplex, cancellation và cleanup trên transport thực.

WebSocket transport cung cấp kết nối hai chiều và multiplex nhiều GraphQL operation trong một session. Spring for GraphQL sử dụng GraphQL over WebSocket Protocol graphql-transport-ws, hỗ trợ connection_init, subscribe, next, complete và các message quản lý kết nối. Khi cấu hình đúng endpoint, xác thực, interceptor, keep-alive, giới hạn tài nguyên và kiểm thử reconnect/cancellation, ứng dụng có thể vận hành Subscription ổn định qua WebSocket.

## Tài liệu tham khảo

- [Spring Boot - Spring for GraphQL: WebSocket endpoint và starter](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL - Server Transports: WebSocket và Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - Testing: WebSocketGraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws)
