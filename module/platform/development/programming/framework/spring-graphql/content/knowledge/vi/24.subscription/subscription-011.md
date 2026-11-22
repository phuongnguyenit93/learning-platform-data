# Subscription với WebSocket

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao Subscription cần một transport hỗ trợ streaming.
- Cấu hình endpoint GraphQL WebSocket trong Spring Boot.
- Khai báo root Subscription và viết resolver bằng @SubscriptionMapping.
- Phát sự kiện bằng Flux và kết nối với nguồn event trong ứng dụng.
- Hiểu vòng đời connection và operation theo giao thức graphql-transport-ws.
- Tạo client bằng WebSocketGraphQlClient và hủy subscription đúng cách.
- Xác thực connection, giới hạn tài nguyên và xử lý mất kết nối.
- Kiểm thử resolver stream và WebSocket transport.

## Subscription và WebSocket

Query và Mutation thường tạo một response cho mỗi lần thực thi. Subscription có semantics khác: client đăng ký nhận các kết quả được phát ra theo thời gian khi sự kiện xảy ra.

Ví dụ, một ứng dụng thư viện có thể thông báo khi sách mới được thêm:

~~~graphql
type Subscription {
  bookCreated: BookCreatedEvent!
}

type BookCreatedEvent {
  eventId: ID!
  occurredAt: String!
  book: Book!
}
~~~

Client gửi operation một lần, sau đó server gửi nhiều kết quả cho cùng subscription. WebSocket giữ một kết nối hai chiều mở để server có thể chủ động gửi dữ liệu tới client mà không cần client polling liên tục.

Spring for GraphQL hỗ trợ WebSocket transport cho subscription. Transport này cũng có thể xử lý query và mutation một kết quả, nhưng use case chính là streaming. Với Spring MVC và Spring WebFlux, Spring cung cấp handler WebSocket riêng; WebFlux sử dụng non-blocking I/O và Reactive Streams để truyền dữ liệu.

WebSocket là một kết nối sống lâu. Một connection có thể mang nhiều operation subscription đồng thời. Mỗi operation có ID riêng để client và server ghép đúng message.

## Khai báo root Subscription trong SDL

GraphQL schema cần khai báo root type Subscription và các field mà client có thể đăng ký:

~~~graphql
type Subscription {
  bookCreated: BookCreatedEvent!
}

type BookCreatedEvent {
  eventId: ID!
  occurredAt: String!
  book: Book!
}

enum BookCategory {
  FICTION
  TECHNOLOGY
  HISTORY
}

type Book {
  id: ID!
  title: String!
  category: BookCategory!
  author: Author
}
~~~

bookCreated phát ra một BookCreatedEvent mỗi khi có sự kiện tạo sách. eventId giúp client nhận diện sự kiện; occurredAt mô tả thời điểm phát; book chứa dữ liệu sách mà client cần.

Subscription field có thể nhận arguments giống các field GraphQL khác. Ví dụ, client có thể đăng ký sự kiện theo category hoặc tenant scope. Những điều kiện lọc phụ thuộc quyền truy cập phải được xác minh ở server; không tin giá trị client gửi chỉ vì nó nằm trong argument.

Mỗi subscription operation phải chọn một root field. Nếu client cần theo dõi hai loại sự kiện, có thể mở hai operation subscription riêng trên cùng một WebSocket connection.

## Bật WebSocket endpoint trong Spring Boot

Spring Boot không bật GraphQL WebSocket endpoint mặc định. Cần chọn transport phù hợp với ứng dụng:

| Ứng dụng | Dependency cho WebSocket |
| --- | --- |
| Spring MVC / Servlet | spring-boot-starter-websocket |
| Spring WebFlux | spring-boot-starter-webflux đã cung cấp WebSocket transport |

Ứng dụng cũng cần spring-boot-starter-graphql. Ví dụ Gradle cho Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
~~~

Với ứng dụng WebFlux, dùng spring-boot-starter-webflux thay cho starter MVC và không cần thêm WebSocket starter riêng.

Đặt endpoint path trong application.yml:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
      connection-init-timeout: 60s
      keep-alive: 25s
~~~

Thuộc tính spring.graphql.websocket.path bật endpoint và chỉ định đường dẫn WebSocket. Nếu HTTP GraphQL cũng dùng /graphql, client có thể gửi HTTP POST cho query/mutation và mở WebSocket tới cùng path cho subscription; server phân biệt transport qua HTTP request và WebSocket handshake.

connection-init-timeout giới hạn thời gian server chờ message khởi tạo connection. keep-alive cho phép server gửi ping khi connection không hoạt động. Giá trị thực tế nên được chọn dựa trên timeout của proxy, load balancer và mạng giữa client với server.

Nếu dùng phiên bản Spring Boot cũ hơn, hãy kiểm tra property và dependency theo BOM của dự án. Không trộn tùy tiện các phiên bản Spring for GraphQL, Spring Boot và Spring Framework.

## Viết resolver bằng @SubscriptionMapping

Trong annotated controller, dùng @SubscriptionMapping để ánh xạ method với field ở root Subscription. Method thường trả về Flux<T> hoặc một Reactive Streams Publisher.

~~~java
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class BookSubscriptionController {

    private final BookEventPublisher eventPublisher;

    public BookSubscriptionController(BookEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @SubscriptionMapping
    public Flux<BookCreatedEvent> bookCreated() {
        return eventPublisher.bookCreatedEvents();
    }
}
~~~

Method không trả về một event ngay lập tức. Nó trả về một publisher đại diện cho luồng event. Mỗi phần tử publisher phát ra trở thành một kết quả của field bookCreated.

Không dùng @QueryMapping cho field root Subscription. Annotation @SubscriptionMapping cho Spring biết method này tạo một nguồn streaming cho subscription operation.

Nếu cần lọc theo argument, có thể nhận @Argument:

~~~java
@SubscriptionMapping
public Flux<BookCreatedEvent> bookCreated(
        @Argument("category") BookCategory category) {

    return eventPublisher.bookCreatedEvents()
            .filter(event -> event.book().category() == category);
}
~~~

Đây chỉ là ví dụ lọc theo category. Với dữ liệu riêng tư, cần áp dụng authorization và tenant filtering ở service hoặc event source để không phát sự kiện ngoài phạm vi người đăng ký.

## Tạo nguồn event trong ứng dụng

Resolver cần một nguồn phát sự kiện. Trong ví dụ nhỏ chạy một instance, có thể dùng Reactor Sinks để chuyển event từ luồng xử lý nghiệp vụ sang Flux:

~~~java
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class BookEventPublisher {

    private final Sinks.Many<BookCreatedEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer(256, false);

    public Flux<BookCreatedEvent> bookCreatedEvents() {
        return sink.asFlux();
    }

    public void publish(BookCreatedEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            // Ghi log/metric và xử lý theo chính sách phát event của ứng dụng.
        }
    }
}
~~~

Khi service tạo sách thành công, nó có thể phát event:

~~~java
public Book create(CreateBookInput input) {
    Book saved = bookRepository.save(mapToBook(input));

    BookCreatedEvent event = new BookCreatedEvent(
            UUID.randomUUID().toString(),
            Instant.now().toString(),
            saved);

    bookEventPublisher.publish(event);
    return saved;
}
~~~

Đoạn code trên minh họa cách nối một sự kiện nghiệp vụ với publisher. Trong ứng dụng có transaction, cần xác định thời điểm phát event để tránh thông báo cho client về dữ liệu chưa commit. Nếu cần bảo đảm event không bị mất giữa database commit và bước publish, hãy cân nhắc transactional outbox hoặc message broker.

Sinks.Many ở ví dụ này chỉ tồn tại trong bộ nhớ của một process và multicast mỗi event tới các subscriber hiện đang hoạt động. Buffer được giới hạn ở 256 phần tử; tham số autoCancel=false giữ sink hoạt động khi subscriber cuối cùng hủy đăng ký để client mới vẫn có thể đăng ký sau đó. Nếu consumer chậm hơn producer và buffer đầy, tryEmitNext có thể trả kết quả FAIL_OVERFLOW. Ứng dụng cần ghi nhận metric/log và quyết định có retry, bỏ event hay chuyển sang broker. Đây là lựa chọn cho ví dụ đơn giản, không phải event store bền vững. Sink multicast không replay các event đã phát tới những subscriber đang hoạt động cho subscriber mới; buffer khởi động trước subscriber đầu tiên cũng chỉ giữ số phần tử giới hạn. Khi server restart, event trong bộ nhớ mất.

Nếu triển khai nhiều instance, client kết nối vào instance A chỉ nhận được event mà instance A biết. Dùng broker dùng chung như Kafka, RabbitMQ hoặc Redis Pub/Sub để phân phối event tới các instance đang giữ WebSocket connection. Nếu yêu cầu replay, xác nhận xử lý hoặc resume sau mất kết nối, cần event ID/cursor và nguồn lưu trữ có khả năng replay; WebSocket tự nó không cung cấp bảo đảm đó.

## Luồng giao thức GraphQL over WebSocket

Spring for GraphQL sử dụng GraphQL over WebSocket protocol từ dự án graphql-ws, với WebSocket subprotocol graphql-transport-ws. Một vòng đời cơ bản:

Protocol này không tương thích với protocol cũ subscriptions-transport-ws. Hãy dùng client và server hỗ trợ cùng graphql-transport-ws.

~~~mermaid
sequenceDiagram
    participant C as GraphQL Client
    participant W as WebSocket Handler
    participant G as GraphQL Engine
    participant E as Event Publisher
    C->>W: WebSocket handshake
    C->>W: connection_init
    W-->>C: connection_ack
    C->>W: subscribe (operation ID + document)
    W->>G: Execute subscription
    G->>E: Subscribe to event Flux
    E-->>G: Event 1
    G-->>C: next (data)
    E-->>G: Event 2
    G-->>C: next (data)
    C->>W: complete (cancel operation)
    W->>G: Cancel subscription
    G-->>E: Cancel source subscription
~~~

Các message chính:

| Message | Hướng | Vai trò |
| --- | --- | --- |
| connection_init | Client → Server | Bắt đầu GraphQL connection và có thể gửi authentication payload |
| connection_ack | Server → Client | Xác nhận connection đã được chấp nhận |
| subscribe | Client → Server | Gửi GraphQL operation cùng ID duy nhất |
| next | Server → Client | Gửi một execution result của operation |
| error | Server → Client | Kết thúc operation bằng lỗi |
| complete | Hai chiều | Server báo stream hoàn tất hoặc client yêu cầu hủy operation |
| ping / pong | Hai chiều | Kiểm tra kết nối và giữ connection hoạt động |

Ví dụ message khởi tạo:

~~~json
{
  "type": "connection_init",
  "payload": {
    "Authorization": "Bearer <access-token>"
  }
}
~~~

Sau khi server xác thực và chấp nhận:

~~~json
{
  "type": "connection_ack"
}
~~~

Client đăng ký operation:

~~~json
{
  "id": "subscription-1",
  "type": "subscribe",
  "payload": {
    "query": "subscription { bookCreated { eventId book { id title } } }"
  }
}
~~~

Mỗi event được gửi bằng message next có cùng operation ID. Khi stream hoàn tất, server gửi complete. Nếu client không muốn nhận tiếp, nó gửi complete cho operation ID tương ứng; server hủy subscription nguồn để giải phóng tài nguyên.

Một WebSocket connection có thể có nhiều operation đang hoạt động. Operation ID phải duy nhất trong số các operation đang chạy trên connection đó. Không dùng lại ID khi operation cũ vẫn chưa hoàn tất.

## GraphQL client với WebSocketGraphQlClient

Spring for GraphQL cung cấp WebSocketGraphQlClient để gửi operation qua một WebSocket connection dùng chung:

~~~java
import java.time.Duration;
import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

String url = "ws://localhost:8080/graphql";
WebSocketClient transport = new ReactorNettyWebSocketClient();

WebSocketGraphQlClient client =
        WebSocketGraphQlClient.builder(url, transport)
                .keepAlive(Duration.ofSeconds(30))
                .build();
~~~

Client tạo connection khi cần hoặc có thể gọi start() để mở connection trước. WebSocketGraphQlClient có tính multiplexed: nhiều request và subscription có thể dùng chung một connection. Nên tái sử dụng một client cho mỗi server thay vì tạo client mới cho từng subscription.

Đăng ký stream:

~~~java
Flux<BookCreatedEvent> events = client.document("""
        subscription BookCreated {
            bookCreated {
                eventId
                occurredAt
                book {
                    id
                    title
                }
            }
        }
        """)
    .retrieveSubscription("bookCreated")
    .toEntity(BookCreatedEvent.class);
~~~

retrieveSubscription trả về Flux với mỗi phần tử tương ứng một response của subscription. Nếu cần xử lý toàn bộ response, bao gồm GraphQL errors và nhiều field, có thể dùng executeSubscription.

Để dừng nhận event, hủy subscription reactive:

~~~java
Disposable disposable = events.subscribe(
        event -> System.out.println("New book: " + event.book().title()),
        error -> log.error("Subscription failed", error));

// Khi màn hình hoặc use case kết thúc:
disposable.dispose();
~~~

Việc cancel Flux khiến WebSocket transport gửi message complete cho operation tương ứng. Khi client gọi client.stop(), các request đang chạy bị hủy, connection đóng và client không nhận request mới cho đến khi được khởi động lại.

## Xác thực WebSocket connection

WebSocket handshake và GraphQL connection initialization là hai bước khác nhau:

1. Handshake tạo WebSocket connection ở tầng transport.
2. connection_init khởi tạo GraphQL connection ở tầng protocol.

Client có thể gửi access token trong payload của connection_init. Spring for GraphQL có WebSocketGraphQlClientInterceptor để tạo payload:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;

WebSocketGraphQlClientInterceptor authenticationInterceptor =
        new WebSocketGraphQlClientInterceptor() {

            @Override
            public Mono<Object> connectionInitPayload() {
                return Mono.just(Map.of(
                        "Authorization",
                        "Bearer " + accessToken));
            }
        };
~~~

Đăng ký interceptor với builder của client:

~~~java
WebSocketGraphQlClient client =
        WebSocketGraphQlClient.builder(url, transport)
                .interceptor(authenticationInterceptor)
                .build();
~~~

Ở phía server, WebSocketGraphQlInterceptor bổ sung callback cho vòng đời connection, ngoài việc intercept từng GraphQL request. Spring for GraphQL có AuthenticationWebSocketInterceptor cho cả WebMVC và WebFlux để lấy thông tin xác thực từ payload connection_init, xác thực và truyền SecurityContext tới các request tiếp theo trên connection.

Nếu cần custom authentication, hãy xác minh token trong callback connection initialization và gắn identity đã xác thực vào security context hoặc request context. Không tin userId, tenantId hay role do client tự khai trong payload nếu chưa được xác minh từ token hoặc nguồn server-side.

Một WebSocketGraphQlInterceptor có thể xử lý lifecycle và cancellation; trong một chain chỉ có thể có tối đa một interceptor thuộc loại này. Có thể kết hợp các WebGraphQlInterceptor thông thường cho xử lý request, nhưng cần thiết kế thứ tự và phạm vi rõ ràng.

### Connection tồn tại lâu và token hết hạn

Authentication của WebSocket thường gắn với connection, trong khi connection có thể sống lâu hơn thời hạn access token. Ứng dụng cần quyết định cách xử lý token hết hạn:

- Đóng connection và yêu cầu client xác thực lại.
- Client tạo connection mới với token đã refresh.
- Giới hạn thời gian sống tối đa của connection.
- Kiểm tra authorization ở từng operation và khi cần ở từng event phát ra.

Không cho rằng xác thực một lần khi connection_init đồng nghĩa mọi subscription về sau luôn được phép. Quyền của người dùng có thể thay đổi; event có thể chứa dữ liệu riêng tư; mỗi nguồn stream cần giữ đúng tenant và security scope.

Trong production, dùng wss:// để mã hóa dữ liệu trên mạng. Kiểm tra origin của WebSocket handshake, xác thực và phân quyền ở server. CORS cho HTTP không thay thế việc kiểm soát origin và xác thực của WebSocket.

## Hủy subscription và giải phóng tài nguyên

Một subscription có thể giữ lại nhiều tài nguyên:

- Đăng ký với event publisher hoặc message broker.
- Database cursor hoặc stream từ hệ thống bên ngoài.
- Bộ đệm và hàng đợi event.
- Context, tracing span và security metadata.

Khi client gửi complete, đóng connection hoặc hủy Flux, nguồn publisher nên nhận cancellation và giải phóng các tài nguyên tương ứng. Khi tạo stream từ API bên ngoài, hãy dùng operator/callback cleanup phù hợp và không để một subscription đã hủy tiếp tục tiêu thụ tài nguyên.

WebSocket connection có thể chứa nhiều subscription đồng thời. Spring cho phép cấu hình maxSubscriptionsPerSession trên GraphQlWebSocketHandler; mặc định không có giới hạn. Cần cân nhắc giới hạn số connection mở ở server, kích thước message buffer và số operation trên mỗi session.

Với WebFlux, tận dụng Reactive Streams và backpressure. Tránh .block() trong pipeline và tránh buffer không giới hạn khi producer có thể phát nhanh hơn consumer. Theo dõi số connection, số subscription đang chạy, tốc độ event, queue size, cancellation và lỗi transport.

## Xử lý lỗi và mất kết nối

Có hai nhóm lỗi cần phân biệt:

- GraphQL operation error: document không hợp lệ, không có quyền đăng ký hoặc resolver không tạo được stream. Server có thể gửi error cho operation.
- Transport error: WebSocket bị đóng, proxy timeout, mạng gián đoạn hoặc server restart. Client nhận lỗi kết nối và cần quyết định có kết nối lại hay không.

WebSocketGraphQlClient có thể tự tái lập connection khi request tiếp theo được gửi hoặc khi gọi start() sau khi connection bị mất. Một Flux subscription bị ngắt có thể kết thúc bằng GraphQlTransportException, ví dụ WebSocketDisconnectedException.

Nếu server gửi message error để kết thúc một subscription operation, Flux phía client có thể kết thúc bằng SubscriptionErrorException; exception này cung cấp các GraphQL errors liên quan. Nếu connection bị đóng, client nhận lỗi transport như WebSocketDisconnectedException. Hãy xử lý hai loại lỗi theo chính sách khác nhau.

Client có thể dùng retry để đăng ký lại, nhưng phải hiểu hệ quả:

- Event phát trong khoảng thời gian mất kết nối có thể bị bỏ lỡ.
- Nếu nguồn replay event, client có thể nhận lại event đã xử lý.
- Retry không tự bảo đảm exactly-once delivery.

Để xử lý tin cậy hơn, event nên có ID duy nhất hoặc sequence/cursor. Client lưu checkpoint cuối cùng đã xử lý và gửi cursor khi đăng ký lại; server dùng nguồn event có khả năng replay để tiếp tục từ vị trí phù hợp. Cần thiết kế idempotency để client không xử lý trùng event.

## Kiểm thử Subscription

Nên tách kiểm thử nguồn stream/resolver khỏi kiểm thử WebSocket transport.

### Kiểm thử publisher và resolver

StepVerifier kiểm tra một Flux và cancellation mà không cần mở WebSocket:

~~~java
StepVerifier.create(bookEventPublisher.bookCreatedEvents().take(1))
        .then(() -> bookEventPublisher.publish(expectedEvent))
        .expectNext(expectedEvent)
        .verifyComplete();
~~~

Test này xác minh publisher phát event và consumer nhận được phần tử. Có thể kiểm tra thêm rằng cancellation giải phóng listener hoặc đăng ký với nguồn event.

### Kiểm thử qua WebSocket

Integration test nên khởi động ứng dụng với WebSocket endpoint thật, tạo WebSocketGraphQlClient, đăng ký subscription và phát event từ test fixture. Xác minh:

1. Handshake thành công và client nhận được connection acknowledgement.
2. Operation subscription hợp lệ nhận đúng event payload.
3. Variables và arguments được truyền đúng.
4. Nhiều operation trên một connection được ghép đúng theo ID.
5. Client hủy Flux thì server ngừng nguồn stream tương ứng.
6. Connection không xác thực bị từ chối.
7. Tenant A không nhận event của tenant B.
8. Lỗi resolver được chuyển thành GraphQL error.
9. Khi connection đóng, tài nguyên stream được giải phóng.
10. Reconnect có hành vi replay/resume đúng contract nếu ứng dụng hỗ trợ.

Với test bất đồng bộ, cần đồng bộ thời điểm subscription đã được đăng ký trước khi phát event. Nếu phát event trước khi server hoàn tất bước subscribe, test có thể bị race và bỏ lỡ event.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| WebSocket handshake trả 404 | Chưa cấu hình spring.graphql.websocket.path | Bật endpoint và kiểm tra path |
| Không mở được WebSocket trên MVC | Thiếu spring-boot-starter-websocket | Thêm starter tương ứng với Servlet stack |
| @SubscriptionMapping không được gọi | Sai root type hoặc dùng nhầm @QueryMapping | Kiểm tra SDL và annotation |
| Client kết nối được nhưng không nhận event | Publisher chưa phát hoặc event đã phát trước khi subscribe | Kiểm tra nguồn event và lifecycle đăng ký |
| Client và server không hiểu message | Hai phía dùng protocol khác nhau | Dùng graphql-transport-ws ở cả client và server |
| Token có trong handshake nhưng server không xác thực | Server đọc token từ connection_init payload theo cấu hình khác | Đồng bộ nơi gửi và nơi đọc credentials |
| Subscription tiếp tục chạy sau khi client rời trang | Flux không được cancel hoặc source không cleanup | Hủy Disposable/Flux và kiểm tra cancellation |
| Một client chiếm nhiều tài nguyên | Không giới hạn connection hoặc subscription | Đặt giới hạn session, buffer và timeout |
| Client bỏ lỡ event khi reconnect | WebSocket không lưu lịch sử event | Dùng broker/event store và cursor nếu cần replay |
| Event bị phát trùng sau retry | Client không có idempotency hoặc event ID | Dùng event ID/sequence và lưu checkpoint |
| Chỉ một instance nhận event | Dùng in-memory publisher trong deployment nhiều node | Dùng broker chung để fanout tới các instance |

## Thực hành tổng hợp

Xây dựng tính năng thông báo sách mới:

1. Khai báo Subscription.bookCreated trả về BookCreatedEvent.
2. Tạo BookCreatedEvent gồm eventId, occurredAt và book.
3. Tạo BookEventPublisher trả Flux<BookCreatedEvent>.
4. Phát event sau khi thao tác tạo sách hoàn tất theo chính sách transaction của ứng dụng.
5. Viết controller dùng @SubscriptionMapping trả stream.
6. Bật WebSocket endpoint bằng spring.graphql.websocket.path.
7. Tạo client bằng WebSocketGraphQlClient và đăng ký subscription.
8. Dùng Disposable.dispose() để hủy subscription khi use case kết thúc.
9. Thêm authentication qua connection init payload và xác minh quyền trên server.
10. Viết test cho event stream, WebSocket transport, cancellation và lỗi xác thực.
11. Thử ngắt connection rồi kết nối lại; ghi nhận event bị bỏ lỡ và thiết kế cursor nếu cần replay.

Sau khi hoàn thành, hãy giải thích sự khác nhau giữa WebSocket connection và subscription operation, vì sao connection_init không phải message gửi GraphQL query, và vì sao một Flux trong bộ nhớ không đủ cho hệ thống nhiều instance cần phát event tin cậy.

## Ghi nhớ

Subscription cho phép server phát nhiều kết quả theo thời gian. Trong Spring for GraphQL, khai báo root field trong SDL, viết resolver bằng @SubscriptionMapping và trả Flux hoặc Publisher. Bật WebSocket endpoint bằng spring.graphql.websocket.path và dùng protocol graphql-transport-ws. Client có thể dùng WebSocketGraphQlClient để chia sẻ connection, đăng ký stream và hủy bằng cancellation. Xác thực connection qua connection_init, nhưng vẫn kiểm tra authorization và tenant scope cho từng operation/event. Connection sống lâu cần giới hạn tài nguyên, heartbeat và cleanup. WebSocket không tự lưu lịch sử hoặc bảo đảm event delivery; nếu cần replay và xử lý tin cậy, dùng event ID/cursor cùng broker hoặc event store phù hợp.

## Tài liệu tham khảo

- [Spring for GraphQL – Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL – Client, WebSocket and Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring Boot – Spring for GraphQL, WebSocket endpoint](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
