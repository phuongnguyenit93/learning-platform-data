# Thiết kế phương án HTTP, SSE hoặc broker khi RSocket không phù hợp

## Mục tiêu dự án

RSocket phù hợp với giao tiếp bất đồng bộ, hai chiều và reactive khi ứng dụng cần multiplex nhiều tương tác trên một kết nối, hỗ trợ request-response, fire-and-forget, request-stream hoặc request-channel, đồng thời cần backpressure ở cấp giao thức. Tuy nhiên, không phải hệ thống nào cũng cần các khả năng đó. Một số môi trường có API gateway chỉ chuẩn hóa HTTP, client không hỗ trợ thư viện RSocket, luồng nghiệp vụ chỉ cần request-response đơn giản, hoặc yêu cầu tích hợp cần hàng đợi bền vững và khả năng phát lại sự kiện.

Trong dự án này, bạn thiết kế một phương án thay thế bằng HTTP, Server-Sent Events (SSE), message broker hoặc cách kết hợp các lựa chọn đó. Bạn sẽ đưa ra quyết định dựa trên hướng truyền dữ liệu, độ trễ, độ bền, khả năng phát lại, mô hình tiêu thụ và giới hạn vận hành. Kết quả cần là một thiết kế có thể triển khai bằng Java/Spring Boot, có hợp đồng API rõ ràng, kiểm soát lỗi, bảo mật và kiểm thử tải.

## 1. Bối cảnh bài toán

Một nền tảng bán hàng xử lý đơn hàng theo chuỗi bước: tiếp nhận đơn, kiểm tra tồn kho, thanh toán, chuẩn bị giao hàng và cập nhật trạng thái cho người mua. Các thành phần có nhu cầu giao tiếp khác nhau:

- Ứng dụng web gửi lệnh tạo đơn, xem chi tiết và truy vấn trạng thái.
- Người mua muốn nhìn thấy trạng thái mới mà không phải tải lại trang liên tục.
- Dịch vụ kho, thanh toán và giao hàng cần trao đổi sự kiện bất đồng bộ.
- Một số tác vụ có thể được xử lý chậm hoặc phải thử lại sau khi dịch vụ phụ thuộc phục hồi.
- Hệ thống chạy sau ingress/API gateway và có nhiều replica Spring Boot.

Giả sử hạ tầng hiện tại ưu tiên HTTP chuẩn. Một số client không thể dùng RSocket; đội vận hành cũng cần quan sát request bằng công cụ HTTP hiện có. Đồng thời, các sự kiện nghiệp vụ quan trọng phải được giữ lại đủ lâu để consumer có thể phục hồi sau gián đoạn.

Thiết kế phải đáp ứng các yêu cầu sau:

1. Client gửi lệnh tạo đơn và nhận phản hồi xác nhận nhanh, có mã đơn để tra cứu tiếp.
2. Client xem được trạng thái hiện tại của đơn hàng.
3. Trình duyệt có thể nhận cập nhật một chiều khi trạng thái thay đổi.
4. Dịch vụ nội bộ nhận sự kiện theo cách giảm phụ thuộc trực tiếp giữa các service.
5. Lỗi mạng, client ngắt kết nối hoặc consumer khởi động lại không làm mất dữ liệu nghiệp vụ đã xác nhận.
6. Một client chậm hoặc một tenant có lưu lượng lớn không làm cạn bộ nhớ của server.
7. Có thể triển khai sau load balancer, xác thực và giới hạn tài nguyên của môi trường thực tế.

## 2. Chọn đúng công cụ cho từng luồng

Không nên chọn giao thức chỉ vì nó hỗ trợ realtime. Hãy xác định ai gửi dữ liệu, ai nhận, dữ liệu có cần lưu bền vững hay không và điều gì xảy ra khi bên nhận offline.

| Phương án | Hướng giao tiếp | Phù hợp khi | Giới hạn cần chấp nhận |
| --- | --- | --- | --- |
| HTTP request-response | Hai chiều theo từng request | CRUD, lệnh nghiệp vụ, truy vấn trạng thái, tích hợp qua API gateway | Client phải tạo request cho mỗi lần trao đổi; không tự tạo kênh push liên tục |
| HTTP polling | Client hỏi server theo chu kỳ | Cập nhật không cần tức thời, triển khai đơn giản | Request lặp lại dù dữ liệu không đổi; độ trễ phụ thuộc chu kỳ polling |
| HTTP long polling | Client giữ request đến khi có dữ liệu hoặc timeout | Muốn giảm polling rỗng nhưng không dùng kết nối streaming | Cần xử lý timeout, request mới sau mỗi phản hồi và nhiều kết nối đang chờ |
| SSE | Server đẩy sự kiện một chiều qua HTTP | Trình duyệt cần nhận cập nhật liên tục nhưng không gửi dữ liệu qua cùng luồng | Chỉ server-to-client; phải quản lý reconnect, proxy timeout và client chậm |
| Webhook | Server gọi HTTP tới endpoint của hệ thống khác | Thông báo giữa các hệ thống có endpoint nhận được | Endpoint có thể offline; cần retry, xác thực, chống gửi trùng và quản lý callback |
| Message broker | Producer gửi sự kiện, consumer xử lý độc lập | Cần tách rời service, hàng đợi, consumer group, retry, retention hoặc replay | Cần vận hành broker, quản lý schema, lag, duplicate và thứ tự |

### HTTP request-response

HTTP phù hợp với thao tác có điểm bắt đầu và kết quả rõ ràng: tạo đơn, hủy đơn, truy vấn chi tiết, kiểm tra quyền hoặc cập nhật một tài nguyên. Với tác vụ kéo dài, API có thể trả về 202 Accepted cùng URI để client kiểm tra trạng thái thay vì giữ request mở cho đến khi toàn bộ quy trình kết thúc.

Polling là lựa chọn dễ triển khai khi trạng thái chỉ cần cập nhật mỗi vài giây hoặc vài phút. Có thể dùng exponential backoff, jitter và header Retry-After để giảm tải. Nếu polling quá dày, số request sẽ tăng theo số client dù trạng thái không đổi. Long polling giảm request rỗng bằng cách giữ request trong một khoảng thời gian, nhưng cần timeout nhất quán ở ứng dụng, proxy và load balancer.

### Server-Sent Events

SSE dùng HTTP response có kiểu nội dung text/event-stream. Server gửi các sự kiện theo thời gian trên cùng response; trình duyệt có thể tự kết nối lại khi mất mạng. Mỗi sự kiện có thể chứa các trường event, data, id và retry. Khi reconnect, trình duyệt gửi Last-Event-ID để server có thể tiếp tục từ sự kiện đã nhận cuối cùng, nếu ứng dụng lưu và tra cứu được lịch sử tương ứng.

SSE phù hợp với thông báo trạng thái, tiến độ xử lý, cảnh báo hoặc bảng điều khiển. Nó không thay thế request hai chiều: client vẫn gửi lệnh qua HTTP request riêng. Nếu client cần gửi và nhận nhiều thông điệp tương tác trong cùng một phiên, hãy xem xét WebSocket hoặc RSocket thay vì ép SSE thành kênh hai chiều.

Một số giới hạn thực tế cần tính trước:

- Kết nối SSE tồn tại lâu, nên số kết nối đồng thời và bộ nhớ cho mỗi subscriber phải được giới hạn.
- Proxy có thể buffer response hoặc đóng kết nối idle. Cần cấu hình tắt buffering phù hợp, timeout và heartbeat.
- Với HTTP/1.1, trình duyệt có giới hạn kết nối đồng thời theo origin; HTTP/2 thường giúp multiplex các request tốt hơn, nhưng vẫn cần kiểm tra cấu hình gateway.
- API EventSource nguyên bản của trình duyệt không cho tùy ý đặt header Authorization. Có thể dùng cookie bảo mật cùng chính sách CSRF phù hợp, hoặc một client streaming có hỗ trợ header; không đưa access token dài hạn vào query string.
- Khi client chậm, không được đệm vô hạn sự kiện trong heap. Cần giới hạn queue và chọn chính sách drop, gộp trạng thái hoặc ngắt kết nối để client đọc lại.

### Message broker

Broker phù hợp khi producer và consumer cần hoạt động độc lập, có thể khác thời điểm, hoặc cần giữ sự kiện khi consumer tạm thời offline. Producer phát sự kiện vào broker; consumer nhận và xử lý theo subscription hoặc consumer group. Broker giúp tách thời gian sống của hai service và hỗ trợ mở rộng consumer theo tải.

Một số mô hình thường gặp:

- **Log/stream phân vùng:** phù hợp với throughput cao, retention và replay; thứ tự thường được bảo đảm trong phạm vi partition, không phải toàn bộ topic.
- **Work queue:** phù hợp phân phối tác vụ cho một worker trong nhóm, acknowledgment, retry và dead-letter queue.
- **Pub/sub:** phù hợp phát một sự kiện tới nhiều nhóm subscriber độc lập. Cần phân biệt broadcast tới từng nhóm với phân phối cạnh tranh trong cùng một consumer group.

Lựa chọn Kafka, RabbitMQ, NATS JetStream hoặc sản phẩm khác cần dựa trên semantics, retention, routing, throughput, độ trễ, khả năng vận hành và năng lực đội ngũ. Tên broker không tự bảo đảm exactly-once cho toàn bộ nghiệp vụ. Thiết kế consumer idempotent vẫn cần thiết vì message có thể được giao lại.

## 3. Quyết định kiến trúc cho bài toán đơn hàng

Một phương án cân bằng là dùng từng cơ chế cho đúng vai trò:

- REST/HTTP nhận lệnh và truy vấn tài nguyên.
- SSE cập nhật tiến độ cho trình duyệt.
- Broker truyền sự kiện nghiệp vụ giữa các service.
- Outbox bảo đảm thay đổi dữ liệu và ý định phát sự kiện được ghi cùng giao dịch cơ sở dữ liệu.

~~~mermaid
flowchart LR
    B[Trình duyệt] -->|POST /orders| API[Order API - HTTP]
    API --> DB[(Order DB + Outbox)]
    API -->|202 + order URI| B
    DB --> RELAY[Outbox relay]
    RELAY --> BROKER[(Message broker)]
    BROKER --> INV[Inventory service]
    BROKER --> PAY[Payment service]
    BROKER --> SHIP[Shipping service]
    BROKER --> PROJ[Order event projection]
    PROJ --> STORE[(Event history)]
    PROJ --> PUSH[SSE gateway]
    PUSH -->|text/event-stream| B
    B -->|GET /orders/{id}| API
~~~

Sơ đồ mô tả vai trò logic; trong triển khai, SSE gateway có thể nằm trong Order API hoặc là service riêng. Nếu gateway có nhiều replica, cần cơ chế phân phối sự kiện đến replica đang giữ kết nối của người dùng, hoặc lưu sự kiện ở nơi dùng chung để mỗi replica có thể đọc lại. Không giả định một subscription consumer group thông thường sẽ broadcast cùng một message tới mọi replica: trong cùng group, message thường được phân phối cho một consumer.

### Luồng tạo đơn và cập nhật

1. Trình duyệt gửi POST /api/orders.
2. Order API xác thực người dùng, kiểm tra dữ liệu và ghi đơn ở trạng thái PENDING.
3. Trong cùng transaction database, API ghi một bản ghi outbox mô tả sự kiện OrderCreated.
4. API trả 202 Accepted, mã đơn và URI truy vấn trạng thái.
5. Outbox relay đọc các bản ghi chưa gửi, publish lên broker và chỉ đánh dấu đã gửi sau khi nhận xác nhận phù hợp từ broker.
6. Inventory, Payment và các consumer khác xử lý sự kiện; kết quả được ghi thành sự kiện hoặc cập nhật trạng thái.
7. Projection cập nhật trạng thái hiện tại và lịch sử sự kiện. SSE gateway phát thông báo tới các trình duyệt đang theo dõi đơn.
8. Nếu trình duyệt mất mạng, nó kết nối lại với Last-Event-ID; server phát tiếp phần lịch sử còn lưu. Client cũng có thể gọi REST để lấy snapshot trạng thái mới nhất.

Outbox relay có thể publish thành công rồi gặp sự cố trước khi đánh dấu bản ghi đã gửi. Khi khởi động lại, relay có thể gửi lại cùng sự kiện. Vì vậy consumer phải nhận diện event ID và xử lý idempotent. Không xóa lịch sử chỉ vì một SSE client đã nhận sự kiện; vòng đời lưu trữ sự kiện cần độc lập với kết nối của từng người dùng.

## 4. Thiết kế hợp đồng HTTP

Hãy xác định API trước khi triển khai. Một hợp đồng tối thiểu có thể gồm:

| Method và đường dẫn | Mục đích | Kết quả chính |
| --- | --- | --- |
| POST /api/orders | Tạo đơn | 202 Accepted, order ID và URI trạng thái |
| GET /api/orders/{id} | Lấy snapshot trạng thái | 200 OK hoặc 404 Not Found |
| GET /api/orders/{id}/events | Theo dõi thay đổi qua SSE | 200 OK, text/event-stream |
| POST /api/orders/{id}/cancel | Yêu cầu hủy đơn | 202 Accepted hoặc lỗi nghiệp vụ phù hợp |

Ví dụ response tạo đơn:

~~~json
{
  "orderId": "7b8f4a1e-5a7a-4f0d-a7d5-1e2a0a8c1001",
  "status": "PENDING",
  "statusUrl": "/api/orders/7b8f4a1e-5a7a-4f0d-a7d5-1e2a0a8c1001"
}
~~~

Với lệnh tạo đơn, cân nhắc hỗ trợ Idempotency-Key. Nếu client timeout rồi gửi lại cùng một lệnh, server có thể trả lại kết quả đã tạo thay vì tạo đơn trùng. Khóa idempotency cần gắn với danh tính người gọi, có thời hạn lưu và quy tắc xử lý khi cùng khóa nhưng payload khác nhau.

Ví dụ controller Spring WebFlux cho request-response:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderCommandController {
    private final OrderApplicationService orders;

    OrderCommandController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PostMapping
    Mono<ResponseEntity<OrderAccepted>> create(
            @Valid @RequestBody CreateOrderRequest request) {
        return orders.create(request)
                .map(order -> ResponseEntity.accepted()
                        .location(URI.create("/api/orders/" + order.id()))
                        .body(new OrderAccepted(order.id(), "PENDING")));
    }

    @GetMapping("/{id}")
    Mono<OrderView> get(@PathVariable UUID id) {
        return orders.get(id);
    }
}
~~~

Đoạn mã minh họa cấu trúc controller; các kiểu DTO, xác thực, xử lý lỗi và transaction được triển khai trong ứng dụng. Với WebFlux, giữ các thao tác I/O ở dạng reactive hoặc chuyển tác vụ blocking sang scheduler có giới hạn. Không gọi JDBC blocking trực tiếp trên event loop.

## 5. Thiết kế luồng SSE có thể phục hồi

Mỗi sự kiện gửi tới client nên có ID ổn định, loại sự kiện và payload tối thiểu. Ví dụ:

~~~text
id: evt-000184
event: order-status
data: {"orderId":"7b8f4a1e-5a7a-4f0d-a7d5-1e2a0a8c1001","status":"PAID"}

~~~

Khi reconnect, client gửi Last-Event-ID: evt-000184. Server phải xác minh người dùng vẫn có quyền xem đơn, tra cứu sự kiện sau ID đó và phát tiếp. Nếu ID đã hết thời hạn lưu hoặc không còn tồn tại, server cần có quy ước rõ ràng: gửi sự kiện báo cần tải snapshot, hoặc trả hướng dẫn để client gọi API trạng thái rồi đăng ký lại.

Ví dụ endpoint SSE với Spring WebFlux:

~~~java
@GetMapping(value = "/{id}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<OrderStatusEvent>> events(
        @PathVariable UUID id,
        @RequestHeader(name = "Last-Event-ID", required = false) String lastEventId) {

    return orderEvents.streamAfter(id, lastEventId)
            .map(event -> ServerSentEvent.<OrderStatusEvent>builder(event.payload())
                    .id(event.eventId())
                    .event("order-status")
                    .build());
}
~~~

Service streamAfter cần kiểm tra quyền truy cập, xác định vị trí tiếp tục và kết hợp lịch sử với sự kiện mới. Cần xử lý race condition giữa lúc đọc lịch sử và lúc đăng ký nhận sự kiện mới; nếu không, sự kiện phát sinh ở khoảng giữa hai thao tác có thể bị bỏ sót. Một cách tiếp cận là đọc từ một offset có thứ tự trong event store/log, hoặc đăng ký live feed trước rồi hợp nhất với lịch sử theo event ID và loại bỏ bản trùng.

Các điểm vận hành cho SSE:

- Gửi heartbeat định kỳ để phát hiện kết nối chết và giữ đường truyền hoạt động qua proxy. Heartbeat có thể là comment SSE, không nhất thiết là sự kiện nghiệp vụ.
- Cấu hình gateway không buffer response và đặt idle timeout lớn hơn chu kỳ heartbeat.
- Giới hạn số kết nối và số byte queue theo người dùng/tenant.
- Nếu client đọc chậm, áp dụng chính sách đã chọn: gộp nhiều cập nhật trạng thái thành snapshot mới nhất, drop sự kiện không quan trọng, hoặc đóng kết nối để client replay.
- Không gửi payload nhạy cảm; mỗi lần đăng ký và mỗi lần đọc replay đều phải kiểm tra quyền.
- Khi người dùng mở nhiều tab, cân nhắc chia sẻ một kết nối hoặc giới hạn số subscription để tránh nhân số kết nối.

SSE không tự lưu lịch sử. Header Last-Event-ID chỉ cung cấp điểm tiếp tục; server cần event store, broker retention hoặc cơ chế replay khác để thực hiện yêu cầu đó. Nếu chỉ phát từ bộ nhớ của một replica, reconnect sang replica khác có thể không tìm được sự kiện.

## 6. Thiết kế sự kiện qua broker

Định nghĩa schema sự kiện có phiên bản và metadata cần thiết:

~~~json
{
  "eventId": "evt-000184",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "occurredAt": "2026-11-22T10:15:30Z",
  "aggregateId": "7b8f4a1e-5a7a-4f0d-a7d5-1e2a0a8c1001",
  "tenantId": "tenant-42",
  "correlationId": "req-91a2",
  "payload": {
    "customerId": "customer-100",
    "total": 125000
  }
}
~~~

Không đưa access token, thông tin thẻ thanh toán hoặc dữ liệu cá nhân không cần thiết vào event. Metadata tenant, correlation ID và event ID phải được tạo hoặc xác minh ở phía server. Định nghĩa schema cần nêu quy tắc tương thích khi thêm field, đổi kiểu dữ liệu hoặc thay đổi ý nghĩa trạng thái.

### Transactional outbox

Nếu ghi đơn vào database rồi publish trực tiếp lên broker, hai thao tác không cùng một transaction mặc định. Có thể xảy ra hai lỗi: đơn đã lưu nhưng event không được gửi, hoặc event đã gửi nhưng transaction lưu đơn rollback. Outbox giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và bản ghi cần publish trong cùng transaction database.

~~~java
@Transactional
public OrderAccepted create(CreateOrderRequest request) {
    Order order = orderRepository.save(Order.pending(request));

    OutboxMessage message = OutboxMessage.pending(
            UUID.randomUUID(),
            "OrderCreated",
            order.id(),
            eventSerializer.serialize(OrderCreated.from(order)));
    outboxRepository.save(message);

    return new OrderAccepted(order.id(), "PENDING");
}
~~~

Một relay riêng đọc outbox theo lô, publish sự kiện và đợi xác nhận của broker trước khi đánh dấu bản ghi đã gửi. Cần có retry có backoff, lease/locking để nhiều relay không xử lý cùng bản ghi ngoài ý muốn, metric cho số bản ghi chờ và tuổi bản ghi cũ nhất. Nếu relay publish xong nhưng chưa cập nhật trạng thái gửi, sự kiện có thể được publish lại; consumer phải idempotent.

### Consumer idempotent

Consumer có thể lưu event ID đã xử lý trong bảng inbox cùng transaction với thay đổi nghiệp vụ:

~~~java
@Transactional
public void handle(OrderCreated event) {
    if (inboxRepository.existsByEventId(event.eventId())) {
        return;
    }

    inventoryService.reserve(event.aggregateId(), event.payload());
    inboxRepository.save(InboxRecord.processed(event.eventId()));
}
~~~

Ví dụ trên giả định thao tác inventory và ghi inbox cùng một transaction quản lý được. Nếu consumer gọi hệ thống bên ngoài, cần một cơ chế idempotency hoặc state machine riêng; transaction database không thể tự rollback một HTTP call đã thành công. Chỉ acknowledge message sau khi thay đổi cần thiết đã commit. Khi lỗi tạm thời, retry có giới hạn; khi lỗi không thể xử lý, chuyển sang dead-letter queue kèm lý do và quy trình xử lý lại.

Thứ tự sự kiện chỉ được bảo đảm trong phạm vi mà broker và cấu hình hỗ trợ, thường là partition hoặc queue cụ thể. Nếu cần thứ tự theo đơn hàng, dùng order ID làm partition/routing key phù hợp. Consumer vẫn nên kiểm tra version hoặc sequence của aggregate để bỏ qua sự kiện cũ và phát hiện sự kiện đến sai thứ tự.

## 7. Bảo mật và phân quyền

Thiết kế thay thế phải giữ nguyên yêu cầu bảo mật của ứng dụng:

- REST và SSE xác thực người dùng bằng cơ chế được hệ thống chuẩn hóa, thường là OAuth2/OIDC hoặc session cookie an toàn.
- Kiểm tra quyền trên từng order ID; biết ID không đồng nghĩa được phép đọc đơn.
- Cấu hình CORS theo origin được phép. Nếu dùng cookie, đánh giá CSRF cho các request thay đổi trạng thái.
- Native EventSource không hỗ trợ tùy ý đặt Authorization header. Không chuyển bearer token dài hạn vào URL vì URL có thể xuất hiện trong log, lịch sử hoặc telemetry.
- Broker dùng TLS, authentication và ACL theo topic/queue; chỉ service được cấp quyền mới được publish hoặc consume.
- Giới hạn tenant ở API, subscription và consumer. Không tin tenant ID chỉ vì nó có trong payload do client gửi.
- Che dữ liệu nhạy cảm trong log và trace; đặt thời hạn lưu cho event store và outbox theo chính sách dữ liệu.

## 8. Độ bền, lỗi và phục hồi

Hãy viết rõ chính sách cho từng loại lỗi thay vì dùng retry chung cho mọi trường hợp:

| Tình huống | Hành vi đề xuất |
| --- | --- |
| Client timeout sau POST | Client gửi lại cùng Idempotency-Key hoặc truy vấn URI trạng thái |
| HTTP 429 hoặc 503 | Tôn trọng Retry-After, backoff và jitter |
| SSE bị ngắt mạng | Tự reconnect, gửi Last-Event-ID và đọc bù lịch sử |
| SSE client đọc chậm | Giới hạn queue; gộp snapshot, drop loại sự kiện cho phép hoặc ngắt để replay |
| Broker tạm thời không khả dụng | Outbox giữ event chưa gửi; relay retry và phát cảnh báo khi backlog tăng |
| Consumer lỗi tạm thời | Retry có giới hạn, có backoff; tránh giữ message lỗi vô hạn |
| Consumer nhận message trùng | Kiểm tra inbox/event ID và xử lý idempotent |
| Payload không hợp lệ | Cách ly vào DLQ, lưu nguyên nhân và hỗ trợ xử lý lại sau khi sửa |
| Event đến sai thứ tự | Kiểm tra aggregate version/sequence và áp dụng quy tắc đồng bộ |
| Một replica SSE bị dừng | Client reconnect tới replica khác và replay từ nguồn lịch sử dùng chung |

Không retry lỗi nghiệp vụ vĩnh viễn như đơn không hợp lệ hoặc người dùng không có quyền. Retry chỉ dành cho lỗi có khả năng phục hồi. Đặt timeout cho mọi lời gọi phụ thuộc và giới hạn tổng thời gian retry để không kéo dài tài nguyên vô hạn.

## 9. Kiểm thử và quan sát

### Bộ kiểm thử chức năng

- Tạo đơn trả 202 Accepted, URI trạng thái và mã đơn ổn định.
- Gửi lại cùng Idempotency-Key không tạo đơn trùng.
- Người dùng không có quyền không đọc được snapshot hoặc stream của đơn khác.
- SSE phát đúng event ID, loại sự kiện và payload; reconnect từ Last-Event-ID không bỏ sót hoặc xử lý trùng ngoài chính sách.
- Client reconnect sang replica khác vẫn đọc được lịch sử sự kiện.
- Outbox không mất event khi relay hoặc broker khởi động lại.
- Consumer nhận message trùng nhưng không lặp tác dụng nghiệp vụ.
- Message lỗi đi vào retry/DLQ theo chính sách; có thể điều tra và xử lý lại.
- Tenant A không thể subscribe hoặc consume dữ liệu của tenant B.

### Bộ kiểm thử tải và sự cố

1. Tăng dần số HTTP request để đo throughput và p95/p99 latency.
2. Tăng số SSE connection đồng thời, giữ trong steady state và theo dõi heap, direct memory, file descriptor cùng số byte queue.
3. Mô phỏng client SSE đọc chậm, mất mạng và reconnect đồng loạt.
4. Tăng tốc độ publish, sau đó làm chậm consumer để quan sát broker lag và tuổi message cũ nhất.
5. Tắt broker trong một khoảng thời gian, xác minh outbox tích lũy rồi relay gửi tiếp sau phục hồi.
6. Kill consumer sau khi xử lý nhưng trước acknowledgment để kiểm tra duplicate và idempotency.
7. Dừng một replica API/SSE để xác minh load balancer, drain và replay hoạt động đúng.
8. Tạo tải lệch giữa tenant để kiểm tra quota và mức dịch vụ của tenant nhỏ.

Theo dõi các chỉ số:

| Thành phần | Chỉ số |
| --- | --- |
| HTTP API | Request rate, status code, timeout, p95/p99 latency, 429/5xx |
| SSE | Kết nối active, reconnect rate, event lag, số event/giây, queue byte, disconnect reason |
| Outbox | Số bản ghi pending, tuổi bản ghi cũ nhất, publish retry, thời gian từ commit đến publish |
| Broker | Publish confirm, throughput, consumer lag, retry, DLQ depth, message age |
| Consumer | Thời gian xử lý, duplicate count, lỗi theo loại, số message đang xử lý |
| JVM/OS | Heap, GC pause, direct memory, RSS, thread, file descriptor, CPU throttling |

Một thiết kế đạt yêu cầu khi tải mục tiêu giữ được SLO, queue và backlog không tăng vô hạn, sự kiện nghiệp vụ không mất khi có lỗi tạm thời, consumer chịu được message giao lại, và tenant khác vẫn được phục vụ khi một tenant tăng tải.

## 10. Các bước thực hiện dự án

### Bước 1 — Viết ADR lựa chọn giao thức

Ghi rõ yêu cầu, giả định, giới hạn của hạ tầng và lý do chọn HTTP, SSE, broker hoặc kết hợp. So sánh ít nhất ba phương án:

- HTTP polling cho cả truy vấn trạng thái.
- HTTP command/query kết hợp SSE cho cập nhật trình duyệt.
- HTTP command kết hợp broker cho xử lý liên dịch vụ, có hoặc không có SSE gateway.

Nêu rõ vì sao RSocket không phải lựa chọn phù hợp trong bối cảnh này và điều kiện nào sẽ khiến bạn xem xét lại.

### Bước 2 — Xây dựng API đồng bộ

Triển khai endpoint tạo đơn và truy vấn trạng thái. Thêm validation, xác thực, phân quyền, Idempotency-Key, mã lỗi nhất quán và timeout cho dịch vụ phụ thuộc. Trả 202 Accepted khi nghiệp vụ tiếp tục xử lý bất đồng bộ.

### Bước 3 — Thêm cập nhật SSE

Triển khai stream trạng thái theo order ID. Thêm event ID, Last-Event-ID, heartbeat, giới hạn subscription, xử lý client chậm và cơ chế replay từ lịch sử dùng chung. Cấu hình ingress để không buffer stream và có timeout phù hợp.

### Bước 4 — Tích hợp broker

Định nghĩa schema có version, topic/queue và routing key. Ghi outbox cùng transaction tạo đơn, triển khai relay, publisher confirm, consumer idempotent, retry và DLQ. Nêu rõ thứ tự sự kiện cần bảo đảm ở phạm vi nào.

### Bước 5 — Hoàn thiện vận hành

Thêm metrics, log có correlation ID, trace xuyên qua HTTP và message, dashboard backlog, cảnh báo queue tăng và quy trình drain khi deploy. Xác định giới hạn connection, queue, payload, concurrency và retention.

### Bước 6 — Kiểm thử và ghi nhận kết quả

Chạy bộ kiểm thử chức năng, tải và sự cố ở trên. Ghi cấu hình, tải đầu vào, SLO, số liệu quan sát, điểm bão hòa và các giới hạn còn lại. Không chọn ngưỡng production chỉ từ một lần chạy ngắn.

## 11. Tiêu chí nghiệm thu

- [ ] ADR giải thích lựa chọn HTTP, SSE và broker theo yêu cầu cụ thể.
- [ ] API tạo đơn và truy vấn trạng thái có hợp đồng rõ ràng.
- [ ] POST có cơ chế chống tạo trùng khi client retry.
- [ ] SSE hỗ trợ event ID, Last-Event-ID, heartbeat và replay.
- [ ] Nhiều replica SSE có thể phục hồi sự kiện từ nguồn dùng chung.
- [ ] Queue cho subscriber chậm có giới hạn và chính sách overflow.
- [ ] Outbox ghi cùng transaction với dữ liệu nghiệp vụ.
- [ ] Consumer idempotent và có retry/DLQ.
- [ ] Schema sự kiện có version, event ID, tenant ID và correlation ID phù hợp.
- [ ] Xác thực, phân quyền, CORS và ACL broker được kiểm thử.
- [ ] Có metric cho HTTP, SSE, outbox, broker, consumer, JVM và OS.
- [ ] Kiểm thử được reconnect, duplicate, broker outage, consumer restart và tenant skew.
- [ ] Tài liệu nêu SLO, giới hạn tài nguyên, cách triển khai và cách xử lý sự cố.

## Sản phẩm bàn giao

1. ADR nêu bối cảnh, phương án đã cân nhắc, quyết định và đánh đổi.
2. Sơ đồ kiến trúc và sequence diagram cho luồng tạo đơn, phát sự kiện và reconnect SSE.
3. API contract cho REST và định dạng sự kiện SSE/broker.
4. Mã nguồn Spring Boot cho HTTP API, SSE endpoint, outbox relay và consumer.
5. Bộ kiểm thử chức năng, tích hợp, tải và phục hồi lỗi.
6. Dashboard hoặc tài liệu chỉ số, SLO, giới hạn tài nguyên và runbook vận hành.

## Kết luận

HTTP, SSE và message broker giải quyết những nhu cầu khác nhau. HTTP là lựa chọn tự nhiên cho lệnh và truy vấn; SSE phù hợp với cập nhật một chiều tới trình duyệt; broker phù hợp với sự kiện liên dịch vụ cần tách rời, retry hoặc replay. Một kiến trúc có thể phối hợp cả ba. Điều quan trọng là xác định đúng semantics, lưu bền vững ở nơi cần thiết, xử lý duplicate và reconnect, giới hạn bộ đệm, đồng thời kiểm chứng thiết kế bằng tải và tình huống lỗi thực tế.
