# Subscription với SSE

GraphQL Subscription cho phép server gửi kết quả mới tới client khi một sự kiện xảy ra, chẳng hạn sách được cập nhật hoặc đơn hàng đổi trạng thái. **Server-Sent Events (SSE)** là một transport chạy trên HTTP, giữ một response stream mở và gửi nhiều event từ server về client.

Spring for GraphQL hỗ trợ GraphQL Subscription qua SSE bằng **GraphQlSseHandler**. Client gửi một GraphQL request qua HTTP và yêu cầu response có media type **text/event-stream**. Server trả về một chuỗi Server-Sent Event; mỗi event mang một GraphQL execution result. Đây là lựa chọn phù hợp khi luồng dữ liệu chủ yếu đi từ server tới client và ứng dụng muốn dùng HTTP thay vì giữ kết nối WebSocket.

Bài này trình bày cách Subscription hoạt động với SSE, cách cấu hình endpoint, cách viết resolver bằng **@SubscriptionMapping**, định dạng event, cách gọi từ Spring GraphQL client và trình duyệt, vòng đời/cancellation, bảo mật, giới hạn kết nối và kiểm thử.

## 1. SSE là gì?

**Server-Sent Events** là cơ chế streaming chuẩn của trình duyệt và HTTP. Client mở một HTTP request, server giữ response mở rồi gửi event theo thời gian. Client nhận event liên tục mà không phải polling liên tục.

SSE có các đặc điểm:

- Giao tiếp một chiều: server gửi event về client trên response stream.
- Dựa trên HTTP và có thể đi qua hạ tầng HTTP thông thường.
- Dữ liệu event là text, thường được gửi dưới dạng JSON.
- Event được phân tách bằng dòng trống.
- Client có thể đóng request để dừng nhận dữ liệu.
- Native browser API có tên EventSource hỗ trợ SSE qua HTTP GET.

Ví dụ một SSE stream:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: update
data: {"status":"PROCESSING"}

event: update
data: {"status":"COMPLETED"}
~~~

Mỗi event có thể chứa tên event và một hoặc nhiều dòng data. Dòng trống kết thúc một event. Với GraphQL over SSE, event type và payload được quy định theo protocol GraphQL over SSE.

## 2. Vì sao dùng SSE cho GraphQL Subscription?

GraphQL Subscription tạo một luồng GraphQL response theo thời gian. SSE cung cấp transport để chuyển các response đó từ server về client.

Ví dụ nghiệp vụ:

- Theo dõi trạng thái xử lý đơn hàng.
- Nhận thông báo khi một quyển sách được cập nhật.
- Theo dõi tiến độ import hoặc export.
- Nhận cảnh báo hệ thống.
- Theo dõi trạng thái build hoặc deployment.

Nếu client chỉ cần nhận thông báo từ server, SSE thường dễ triển khai hơn WebSocket vì dùng HTTP request/response và không yêu cầu giao thức hai chiều.

### So sánh SSE, WebSocket và RSocket

| Tiêu chí | SSE | WebSocket | RSocket |
|---|---|---|---|
| Hướng dữ liệu | Server → client | Hai chiều | Hai chiều, tùy interaction |
| Nền tảng transport | HTTP response stream | WebSocket connection | TCP hoặc WebSocket |
| GraphQL Subscription | Có | Có | Có |
| Client-to-server message trên cùng stream | Không | Có | Có |
| Browser API | EventSource hoặc streaming fetch | WebSocket | Cần client/library |
| Phù hợp | Feed và notification một chiều | Realtime tương tác hai chiều | Streaming và interaction theo mô hình RSocket |
| Kết nối | Một HTTP connection cho mỗi operation trong chế độ Spring hỗ trợ | Có thể chia sẻ connection cho nhiều operation | Có thể multiplex nhiều interaction trong session |

SSE không thay thế mọi trường hợp của WebSocket. Nếu client cần gửi nhiều message trên cùng một kết nối realtime, WebSocket hoặc RSocket có thể phù hợp hơn.

## 3. Spring for GraphQL hỗ trợ SSE như thế nào?

Spring for GraphQL cung cấp **GraphQlSseHandler** cho server transport. Handler này nhận request GraphQL qua HTTP và trả response theo Server-Sent Events protocol.

Spring for GraphQL hỗ trợ SSE từ dòng **1.3.x**. Có implementation cho Spring MVC và Spring WebFlux. Khi dùng Spring Boot auto-configuration, HTTP endpoint mặc định là **/graphql** và có thể trả SSE khi request yêu cầu media type tương ứng.

Request SSE mặc định có dạng:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: text/event-stream

{
  "query": "subscription { bookUpdated { id title } }"
}
~~~

Điểm khác biệt so với HTTP GraphQL thông thường:

- Request body vẫn là GraphQL request JSON.
- Content-Type của request là application/json.
- Header Accept yêu cầu text/event-stream.
- Response là một stream gồm nhiều Server-Sent Event.

Trong Spring for GraphQL, SSE dùng **Distinct connections mode**: mỗi operation có một HTTP request và một response stream riêng. Vì vậy, mỗi subscription giữ một kết nối HTTP riêng trong suốt thời gian stream còn hoạt động.

### Subscription-only transport

SSE handler của Spring for GraphQL dành cho Subscription. Query và Mutation thông thường nên dùng HTTP JSON endpoint. Không nên gửi Query hoặc Mutation qua SSE endpoint với kỳ vọng nhận một response JSON thông thường.

Một ứng dụng có thể dùng chung đường dẫn /graphql:

- Accept application/json: HTTP GraphQL request/response.
- Accept text/event-stream: GraphQL Subscription qua SSE.

Spring Boot và phiên bản Spring for GraphQL quyết định cách auto-configure route. Cần kiểm tra cấu hình endpoint và HTTP methods của phiên bản đang dùng.

## 4. Cấu hình SSE trong Spring Boot

Ứng dụng cần Spring for GraphQL và web transport. Ví dụ dependency Gradle:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-graphql")
implementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

Nếu ứng dụng dùng Spring MVC, dùng starter web thay cho starter webflux:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-web")
~~~

Spring Boot cấu hình HTTP GraphQL endpoint mặc định tại /graphql. SSE được chọn khi client gửi Accept: text/event-stream.

Ví dụ cấu hình HTTP path và method trong các phiên bản Spring Boot có nhóm property HTTP SSE:

~~~yaml
spring:
  graphql:
    http:
      path: /graphql
      sse:
        methods: POST
~~~

POST là lựa chọn mặc định phù hợp với GraphQL request JSON vì client có thể gửi document, operation name và variables trong body.

Nếu cần hỗ trợ browser EventSource, có thể bật GET cho SSE:

~~~yaml
spring:
  graphql:
    http:
      sse:
        methods: GET,POST
~~~

Tên và cấu trúc property có thể thay đổi theo phiên bản Spring Boot. Hãy đối chiếu configuration metadata của dependency đang dùng trước khi áp dụng cấu hình này.

### Dùng GraphQlSseHandler trực tiếp

Khi không dùng auto-configuration hoặc cần tự kiểm soát route, có thể đăng ký GraphQlSseHandler làm web endpoint. Spring for GraphQL có implementation tương ứng cho MVC và WebFlux.

Ở các phiên bản mới, handler cung cấp builder để cấu hình HTTP methods được hỗ trợ; các phiên bản cũ có thể dùng constructor và route riêng. Request predicate cho SSE cần khớp với HTTP methods mà handler chấp nhận.

Không nên tạo một route SSE nhận mọi loại HTTP method nếu ứng dụng không có nhu cầu. Cần giữ route, handler và security policy nhất quán.

## 5. Định nghĩa Subscription trong schema

GraphQL schema cần có root type Subscription và field mà client muốn theo dõi.

~~~graphql
type Subscription {
  bookUpdated(bookId: ID!): BookUpdatedEvent!
}

type BookUpdatedEvent {
  bookId: ID!
  title: String!
  changedAt: String!
}
~~~

Field bookUpdated nhận bookId để giới hạn stream theo quyển sách. Mỗi event chứa dữ liệu mới mà client được phép nhận.

Subscription operation:

~~~graphql
subscription BookUpdated($bookId: ID!) {
  bookUpdated(bookId: $bookId) {
    bookId
    title
    changedAt
  }
}
~~~

Mỗi khi source event stream phát ra một event, GraphQL thực thi selection set của Subscription trên event đó và tạo một GraphQL execution result.

## 6. Viết resolver bằng @SubscriptionMapping

Trong annotated controller, dùng **@SubscriptionMapping** để ánh xạ method vào root Subscription field.

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService bookEventService;

    public BookSubscriptionController(BookEventService bookEventService) {
        this.bookEventService = bookEventService;
    }

    @SubscriptionMapping
    public Flux<BookUpdatedEvent> bookUpdated(
            @Argument String bookId) {

        return bookEventService.eventsFor(bookId);
    }
}
~~~

Method trả về **Flux<BookUpdatedEvent>**, một Reactive Streams Publisher phát ra nhiều event theo thời gian.

Các thành phần:

- @SubscriptionMapping ánh xạ method vào field ở root Subscription.
- @Argument lấy giá trị bookId từ GraphQL operation.
- BookEventService cung cấp source event stream.
- Mỗi BookUpdatedEvent được GraphQL dùng làm source value để resolve các field được client chọn.

SSE là transport. Nó không tạo ra event nghiệp vụ và cũng không thay thế source Publisher. Ứng dụng vẫn cần một event source như Reactor, message broker hoặc service phát sự kiện.

### Phân biệt source stream và response stream

Subscription có hai giai đoạn:

1. Source stream phát ra event nghiệp vụ, ví dụ BookUpdatedEvent.
2. GraphQL thực thi selection set cho mỗi event và phát ra GraphQL ExecutionResult tương ứng.

Transport SSE chuyển các ExecutionResult đó thành các event trên HTTP response stream.

~~~mermaid
flowchart TD
    A[Event source / Publisher] --> B[BookUpdatedEvent]
    B --> C[GraphQL subscription execution]
    C --> D[Resolve selection set]
    D --> E[GraphQL ExecutionResult]
    E --> F[SSE transport]
    F --> G[event: next]
    G --> H[Client nhận response]
~~~

Nhờ vậy, client có thể chọn các field cần thiết trong schema. Server chạy lại selection set cho từng source event thay vì gửi nguyên object nội bộ.

## 7. Tạo source event stream bằng Reactor

Một ví dụ đơn giản dùng Reactor Sinks để phát sự kiện:

~~~java
@Component
public class BookEventService {

    private final Sinks.Many<BookUpdatedEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    public Flux<BookUpdatedEvent> eventsFor(String bookId) {
        return sink.asFlux()
                .filter(event -> event.bookId().equals(bookId));
    }

    public void publish(BookUpdatedEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            throw new IllegalStateException(
                    "Không thể phát book update event: " + result);
        }
    }
}
~~~

Đây là ví dụ minh họa cho một event source trong một ứng dụng đơn giản. Với production, cần chọn sink phù hợp với semantics và lifecycle của event, kiểm soát dung lượng buffer, xử lý emit failure và cân nhắc việc ứng dụng chạy trên nhiều instance.

Nếu nhiều server instance cùng phục vụ subscription, một Sinks.Many trong bộ nhớ chỉ phát event trên instance chứa sink đó. Để phát event xuyên nhiều instance, thường cần message broker hoặc event infrastructure dùng chung.

### Phát event sau khi cập nhật dữ liệu

Khi một mutation cập nhật sách thành công, application service có thể phát event:

~~~java
public Book updateBook(String bookId, UpdateBookInput input) {
    Book updated = bookRepository.update(bookId, input);

    bookEventService.publish(new BookUpdatedEvent(
            updated.id(),
            updated.title(),
            Instant.now().toString()));

    return updated;
}
~~~

Chỉ phát event sau khi cập nhật nghiệp vụ thành công. Nếu cần bảo đảm event không bị mất khi database commit nhưng process dừng trước khi publish, hãy cân nhắc transactional outbox hoặc cơ chế event delivery bền vững.

## 8. Định dạng GraphQL over SSE

Với GraphQL over SSE trong Distinct connections mode, các event quan trọng gồm:

- **next**: mang một GraphQL ExecutionResult.
- **complete**: báo stream đã hoàn tất và không còn kết quả tiếp theo.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: next
data: {"data":{"bookUpdated":{"bookId":"book-01","title":"Spring GraphQL","changedAt":"2026-11-20T10:00:00Z"}}}

event: next
data: {"data":{"bookUpdated":{"bookId":"book-01","title":"Spring GraphQL in Practice","changedAt":"2026-11-20T10:01:00Z"}}}

event: complete
data:
~~~

Mỗi next event chứa một GraphQL response, thường có data và có thể có errors. Khi Publisher hoàn tất, transport gửi complete và kết thúc stream.

Nếu Publisher không hoàn tất, stream có thể mở trong thời gian dài cho đến khi client hủy, server đóng kết nối hoặc có lỗi kết thúc stream.

Không nhầm event SSE với event nghiệp vụ. Một event SSE next chứa kết quả GraphQL; payload data bên trong mới chứa field và object nghiệp vụ.

## 9. Gửi request SSE bằng HTTP client

Client cần gửi GraphQL document và variables trong body, đồng thời yêu cầu SSE:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: text/event-stream

{
  "operationName": "BookUpdated",
  "query": "subscription BookUpdated($bookId: ID!) { bookUpdated(bookId: $bookId) { bookId title changedAt } }",
  "variables": {
    "bookId": "book-01"
  }
}
~~~

Một số điểm cần kiểm tra:

- Content-Type mô tả request body là JSON.
- Accept yêu cầu server trả SSE.
- Document phải là Subscription operation.
- Variables phải khớp kiểu input trong schema.
- Response được đọc như một stream, không chờ toàn bộ body hoàn tất.

Nếu client gửi Accept: application/json, server sẽ xử lý theo HTTP JSON transport thông thường và không trả subscription stream theo cách SSE.

## 10. Dùng HttpGraphQlClient để nhận Subscription qua SSE

Spring for GraphQL client hỗ trợ Subscription qua **HttpGraphQlClient** với SSE. Client có thể dùng cùng workflow GraphQlClient và gọi retrieveSubscription để nhận Flux kết quả.

~~~java
WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .build();

HttpGraphQlClient client =
        HttpGraphQlClient.builder(webClient).build();

Flux<BookUpdatedEvent> events = client.document("""
        subscription BookUpdated($bookId: ID!) {
            bookUpdated(bookId: $bookId) {
                bookId
                title
                changedAt
            }
        }
        """)
    .variable("bookId", "book-01")
    .retrieveSubscription("bookUpdated")
    .toEntity(BookUpdatedEvent.class);
~~~

Flux phát ra một BookUpdatedEvent cho mỗi GraphQL response event được giải mã. Client có thể xử lý bằng các Reactor operator:

~~~java
events
    .doOnNext(event -> log.info(
            "Book {} changed to {}",
            event.bookId(),
            event.title()))
    .subscribe();
~~~

Trong ứng dụng thực tế, cần quản lý Disposable hoặc Subscription handle để có thể hủy stream khi component không còn cần nhận event.

### Xử lý lỗi ở client

Client nên phân biệt:

- GraphQL execution error được trả trong GraphQL response.
- Subscription error có thể làm stream kết thúc với SubscriptionErrorException.
- Lỗi transport như mất kết nối có thể làm stream kết thúc với GraphQlTransportException.

Nếu cần đọc cả data và errors của từng event, dùng executeSubscription thay vì chỉ retrieveSubscription một field.

## 11. Dùng browser EventSource

Browser cung cấp API **EventSource** để nhận SSE:

~~~javascript
const query = "subscription { bookUpdated(bookId: \"book-01\") { bookId title } }";
const url = "/graphql?query=" + encodeURIComponent(query);
const source = new EventSource(url);

source.addEventListener("next", (event) => {
  const result = JSON.parse(event.data);
  console.log(result.data);
});

source.addEventListener("complete", () => {
  source.close();
});
~~~

Ví dụ trên chỉ minh họa cách browser nhận event. Để hoạt động với Spring GraphQL, cần cấu hình SSE endpoint chấp nhận HTTP GET. GraphQL request phải được encode theo quy tắc GET của GraphQL over HTTP.

### Giới hạn của EventSource

Native EventSource:

- Chỉ mở kết nối GET.
- Không cho tùy chỉnh request body.
- Không hỗ trợ tùy ý thiết lập Authorization header.
- Có thể gửi cookie theo cấu hình credentials.
- Có cơ chế tự reconnect theo hành vi SSE của trình duyệt.

Trong khi đó, GraphQlSseHandler mặc định dùng POST. Vì vậy, browser EventSource chỉ phù hợp nếu server bật GET và operation có thể truyền an toàn qua query parameters.

Không nên đặt bearer token hoặc dữ liệu bí mật trong URL query string vì URL có thể xuất hiện trong access log, proxy log, browser history hoặc telemetry. Nếu cần POST body và Authorization header, dùng HttpGraphQlClient hoặc một fetch-based SSE client hỗ trợ request body/header thay vì native EventSource.

## 12. GET và POST cho SSE

POST thường là lựa chọn phù hợp cho GraphQL Subscription vì:

- Document nằm trong body.
- Variables được gửi dưới dạng JSON.
- Không bị giới hạn thực tế của độ dài URL như GET.
- Có thể gửi Authorization header qua HTTP client.

GET hữu ích khi cần tương thích với EventSource:

- Cần bật GET trên SSE handler.
- Query và variables được mã hóa vào URL.
- Không nên đưa dữ liệu nhạy cảm vào URL.
- Cần xem xét giới hạn URL của browser, proxy và server.

Nếu operation có nhiều variables hoặc dữ liệu đầu vào phức tạp, POST với streaming fetch/client library thường phù hợp hơn.

## 13. Cancellation và vòng đời Subscription

Một Subscription có thể tồn tại lâu. Khi client không còn cần event, nó cần hủy stream bằng cách đóng SSE connection hoặc cancel Publisher phía client.

Khi request bị hủy, server nên truyền cancellation xuống source Publisher để giải phóng:

- Listener đăng ký với event bus.
- Consumer/subscription ở message broker.
- Tài nguyên database hoặc network.
- Buffer và state theo subscriber.
- Metric hoặc registry đang theo dõi subscription.

Ví dụ thêm cleanup:

~~~java
@SubscriptionMapping
public Flux<BookUpdatedEvent> bookUpdated(
        @Argument String bookId) {

    return bookEventService.eventsFor(bookId)
            .doFinally(signalType ->
                    log.debug(
                            "Book subscription closed: {}, reason={}",
                            bookId,
                            signalType));
}
~~~

doFinally được gọi khi stream hoàn tất, lỗi hoặc bị cancel. Với resource cần mở/đóng theo subscriber, nên dùng cơ chế resource lifecycle phù hợp thay vì chỉ log.

Không nên tạo listener hoặc message broker consumer toàn cục mới cho mỗi event. Hãy đăng ký một lần theo subscription và hủy đúng lúc.

## 14. Reconnect và khả năng nhận lại event

SSE chuẩn có hành vi reconnect ở client. Tuy nhiên, reconnect ở tầng HTTP không tự bảo đảm GraphQL Subscription tiếp tục đúng vị trí cũ.

Trong Spring for GraphQL, mỗi operation dùng một kết nối riêng trong Distinct connections mode. Khi connection bị mất và client gửi lại operation, server tạo một subscription mới. Ứng dụng không nên mặc định event đã phát trong khoảng mất kết nối sẽ được gửi lại.

Nếu nghiệp vụ yêu cầu không mất event, cần thiết kế khả năng resume ở tầng application:

- Mỗi event có sequence number hoặc event ID ổn định.
- Client lưu cursor cuối cùng đã xử lý.
- Subscription nhận cursor hoặc timestamp làm argument.
- Event source có khả năng đọc lại từ broker/log hoặc database.
- Server xác thực quyền truy cập đối với cả cursor và dữ liệu được replay.

Ví dụ schema:

~~~graphql
type Subscription {
  orderEvents(orderId: ID!, afterSequence: Long): OrderEvent!
}
~~~

Đây là contract nghiệp vụ do ứng dụng thiết kế, không phải tính năng replay tự động của SSE transport.

## 15. Backpressure, buffering và slow consumers

Một client có thể nhận event chậm hơn tốc độ source Publisher phát event. Nếu server giữ buffer không giới hạn, memory có thể tăng liên tục.

Khi thiết kế source stream:

- Chọn chiến lược buffer có giới hạn.
- Xác định event nào có thể gộp hoặc bỏ qua.
- Không drop event nếu nghiệp vụ yêu cầu xử lý đầy đủ.
- Có thể dùng latest-state event nếu client chỉ cần trạng thái mới nhất.
- Theo dõi số subscriber, queue size và thời gian xử lý.
- Hủy stream nếu client đã disconnect hoặc vượt quá giới hạn được đặt ra.

Spring for GraphQL sử dụng Reactive Streams Publisher cho subscription. Với WebFlux, streaming có thể tận dụng reactive/non-blocking I/O; với Spring MVC, cách ghi response dựa trên async Servlet. Hành vi buffering và giới hạn thực tế còn phụ thuộc event source, server và proxy.

Không nên xem SSE là giải pháp vô hạn cho mọi số lượng subscriber. Cần đo tải với số kết nối đồng thời và tốc độ phát event gần production.

## 16. Distinct connections mode và khả năng mở rộng

Spring for GraphQL hiện triển khai GraphQL over SSE ở **Distinct connections mode**. Mỗi Subscription có một HTTP request/response stream riêng.

Điều này có hệ quả:

- Một người dùng mở nhiều subscription sẽ giữ nhiều HTTP stream.
- Nhiều tab trình duyệt có thể tạo nhiều kết nối tới cùng origin.
- HTTP/1.1 có giới hạn số kết nối đồng thời trên mỗi origin ở một số browser.
- HTTP/2 multiplex nhiều stream trên một kết nối TCP, giúp giảm áp lực số kết nối vật lý.
- Proxy và load balancer cần hỗ trợ response streaming lâu dài.

Spring khuyến nghị cân nhắc scalability và HTTP/2 khi áp dụng SSE ở quy mô lớn. Hãy kiểm tra idle timeout, maximum connection, response buffering và giới hạn tài nguyên của hạ tầng.

### Không nhầm hai chế độ của GraphQL over SSE

GraphQL over SSE protocol mô tả Distinct connections mode và Single connection mode. Spring for GraphQL triển khai Distinct connections mode.

| Đặc điểm | Distinct connections | Single connection |
|---|---|---|
| Kết nối SSE | Một cho mỗi operation | Một kết nối có thể mang nhiều operation |
| Gửi operation | HTTP request riêng | HTTP request riêng kèm token/operation ID |
| Quản lý operation | Theo connection | Cần reservation token và operation ID |
| Spring for GraphQL | Được hỗ trợ | Không được triển khai |

Không thiết kế client dựa trên multiplexing nhiều Subscription trên một SSE connection khi dùng GraphQlSseHandler của Spring.

## 17. Bảo mật Subscription qua SSE

SSE dùng HTTP nên có thể tích hợp với Spring Security, CORS và WebGraphQlInterceptor như các web request khác. Tuy nhiên, thời gian sống của subscription dài hơn một HTTP response thông thường.

### Authentication

Xác thực request trước khi mở stream. Với POST, HTTP client có thể gửi Authorization header. Native EventSource không cho thiết lập tùy ý header; nếu dùng EventSource, cần cân nhắc cookie an toàn hoặc một client khác hỗ trợ header.

Không đưa bearer token vào query string. Nếu dùng cookie, cần cấu hình SameSite, Secure, HttpOnly và CSRF/CORS theo mô hình ứng dụng.

### Authorization

Không chỉ kiểm tra quyền mở Subscription. Cần bảo đảm người dùng chỉ subscribe tới topic/resource mà họ được phép xem.

Ví dụ:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderEvents(@Argument String orderId) {
    authorizationService.checkCanReadOrder(orderId);
    return orderEventService.eventsFor(orderId);
}
~~~

Nếu quyền có thể bị thu hồi trong lúc stream đang mở, cân nhắc kiểm tra quyền theo event hoặc kết thúc stream khi principal mất quyền. Chỉ kiểm tra lúc subscribe có thể không đủ cho dữ liệu nhạy cảm.

### Tenant isolation

Tenant ID nên lấy từ principal hoặc request context đã xác minh. Không tin trực tiếp tenant ID từ GraphQL argument nếu không kiểm tra user có quyền truy cập tenant đó.

### CORS và proxy

Nếu browser gọi khác origin, cấu hình CORS cho đúng origin, method và header cần thiết. Đảm bảo proxy không buffer toàn bộ response SSE và không tự đóng kết nối quá sớm.

## 18. Kiểm thử Subscription với SSE

Subscription là stream nên kiểm thử bằng **HttpGraphQlClient** và **StepVerifier** thường phù hợp hơn GraphQlTester thông thường, vốn tập trung vào response đơn.

Ví dụ:

~~~java
@Test
void shouldReceiveBookUpdates() {
    Flux<BookUpdatedEvent> events = graphQlClient.document("""
            subscription BookUpdated($bookId: ID!) {
                bookUpdated(bookId: $bookId) {
                    bookId
                    title
                    changedAt
                }
            }
            """)
        .variable("bookId", "book-01")
        .retrieveSubscription("bookUpdated")
        .toEntity(BookUpdatedEvent.class);

    StepVerifier.create(events)
            .then(() -> bookEventService.publish(
                    new BookUpdatedEvent(
                            "book-01",
                            "Updated title",
                            Instant.now().toString())))
            .expectNextMatches(event ->
                    event.bookId().equals("book-01")
                            && event.title().equals("Updated title"))
            .thenCancel()
            .verify();
}
~~~

Test cần bảo đảm subscription đã được đăng ký trước khi publish event. Trong integration test, có thể dùng latch, sink test hook hoặc tín hiệu đồng bộ phù hợp để tránh race condition.

Nên kiểm tra:

1. Request gửi Accept: text/event-stream.
2. Response có Content-Type text/event-stream.
3. Mỗi source event tạo một GraphQL response event.
4. Variables lọc đúng stream.
5. Field selection chỉ trả các field client yêu cầu.
6. GraphQL error trong event được xử lý đúng.
7. Publisher complete làm stream kết thúc.
8. Client cancellation làm source subscription được hủy.
9. Disconnect và reconnect không tạo listener cũ bị rò rỉ.
10. Authorization và tenant isolation được giữ trong toàn bộ stream.
11. Nhiều subscriber cùng nhận event theo semantics mong muốn.
12. Slow consumer không làm buffer tăng không giới hạn.

Nếu cần kiểm thử wire format hoặc HTTP headers, có thể dùng WebTestClient gửi POST với Accept text/event-stream và đọc response body theo stream. Kiểm tra cả status, content type và event payload.

## 19. Các lỗi thường gặp khi dùng Subscription với SSE

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Response trả JSON thay vì stream | Accept không có text/event-stream | Kiểm tra Accept header |
| SSE endpoint từ chối GET | Handler mặc định chỉ nhận POST | Bật GET nếu thực sự cần EventSource |
| Client nhận một response rồi dừng | Resolver trả object/Mono thay vì Publisher stream | Trả Flux/Publisher cho Subscription |
| Query hoặc Mutation không chạy qua SSE | SSE handler dành cho Subscription | Dùng HTTP JSON transport |
| Event không xuất hiện | Source Publisher không phát hoặc filter sai | Kiểm tra event source và argument |
| Browser EventSource không gửi token | API không hỗ trợ custom Authorization header | Dùng cookie an toàn hoặc fetch-based SSE client |
| Mất event sau reconnect | Không có replay/cursor ở application layer | Thiết kế sequence ID và resume |
| Server giữ listener sau khi client rời đi | Không xử lý cancellation | Cleanup bằng doFinally/resource lifecycle |
| Nhiều subscriber làm tăng memory | Buffer không giới hạn hoặc event quá nhanh | Giới hạn buffer và đặt overload policy |
| Một instance nhận event, instance khác không | Event source chỉ nằm trong memory cục bộ | Dùng broker/event infrastructure dùng chung |
| Connection bị đóng sau thời gian ngắn | Proxy/load balancer idle timeout | Cấu hình timeout phù hợp và kiểm thử hạ tầng |
| Nhiều tab không mở được stream | Giới hạn HTTP/1.1 connection | Cân nhắc HTTP/2 và số lượng subscription |

## 20. Quy trình triển khai Subscription với SSE

Khi triển khai GraphQL Subscription qua SSE:

1. Xác định use case thực sự cần server stream event một chiều.
2. Khai báo root Subscription field và payload type trong SDL.
3. Tạo source event Publisher bằng Reactor hoặc event infrastructure.
4. Viết resolver @SubscriptionMapping trả Flux/Publisher.
5. Cấu hình Spring for GraphQL SSE handler hoặc dùng Boot auto-configuration.
6. Gửi request HTTP với Content-Type application/json và Accept text/event-stream.
7. Dùng HTTP POST mặc định; chỉ bật GET khi cần tương thích EventSource.
8. Dùng HttpGraphQlClient.retrieveSubscription hoặc SSE client phù hợp để nhận stream.
9. Xử lý next event, GraphQL errors và complete event.
10. Thiết kế cancellation để giải phóng listener, consumer và resource.
11. Xác thực request, kiểm tra authorization theo resource và tenant.
12. Quyết định chiến lược reconnect/replay nếu nghiệp vụ không được mất event.
13. Giới hạn buffer, theo dõi subscriber và kiểm tra HTTP/2/proxy timeout.
14. Kiểm thử event delivery, cancellation, error, reconnect và tải đồng thời.

SSE là transport HTTP phù hợp cho GraphQL Subscription khi client chủ yếu nhận dữ liệu từ server. Spring for GraphQL cung cấp GraphQlSseHandler và hỗ trợ Distinct connections mode, trong đó mỗi operation có một response stream riêng. Resolver @SubscriptionMapping trả Publisher của event nghiệp vụ; GraphQL tạo ExecutionResult cho từng event và SSE gửi các kết quả đó qua next event cho tới khi stream complete hoặc bị hủy. Hãy cấu hình đúng Accept header, quản lý cancellation, bảo vệ authorization và tenant, đồng thời thiết kế reconnect/replay cùng giới hạn tài nguyên theo yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- Spring for GraphQL — Server Transports: https://docs.spring.io/spring-graphql/reference/transports.html
- Spring for GraphQL — Client và Subscription Requests: https://docs.spring.io/spring-graphql/reference/client.html
- Spring Boot — Spring for GraphQL và HTTP/SSE endpoint: https://docs.spring.io/spring-boot/reference/web/spring-graphql.html
- GraphQL over SSE protocol: https://github.com/enisdenjo/graphql-sse/blob/master/PROTOCOL.md
