# Phân biệt adapter với gateway và service activator

## 1. Bài toán: ba endpoint trông giống nhau nhưng khác hợp đồng

Một hệ thống đơn hàng cần kết nối ứng dụng với Kafka, HTTP API, cơ sở dữ liệu và một service nghiệp vụ. Khi nhìn vào Java DSL, bạn có thể thấy đều là các phương thức `from(...)` hoặc `handle(...)`:

~~~java
// Chỉ là ý tưởng, ba lựa chọn này KHÔNG có cùng ngữ nghĩa.
IntegrationFlow.from(inboundSource);
IntegrationFlow.from("orders.commands").handle(someHandler);
IntegrationFlow.from("orders.requests").handle(remoteEndpoint);
~~~

Vì hình thức tương tự, một nhóm có thể chọn nhầm:

- Dùng **outbound channel adapter** trong luồng cần **nhận business reply** từ HTTP.
- Dùng **inbound channel adapter** ở nơi external client **đang chờ response**.
- Gọi một **Service Activator** là gateway, rồi cho rằng nó tự cung cấp transport protocol, timeout và reply correlation.
- Thấy broker ACK hoặc HTTP 202 và mặc định nghiệp vụ **đã hoàn tất**.
- Đặt logic truy cập HTTP/Kafka trực tiếp trong business method khiến khó kiểm soát retry, security và quan sát lỗi.

Ba thành phần liên quan nhưng giải quyết **ba câu hỏi khác nhau**:

1. **Channel Adapter:** message **đi vào hoặc đi ra** hệ thống messaging thế nào, thường theo hợp đồng **one-way**?
2. **Gateway:** hệ thống có cần **request–reply** và trả kết quả/error về đúng caller không?
3. **Service Activator:** message đi tới **phương thức xử lý của ứng dụng** nào, và method có thể trả reply ra sao?

~~~mermaid
flowchart LR
    EXT["External event source"] --> IN["Inbound Channel Adapter"]
    IN --> CH["Spring MessageChannel"]
    CH --> SA["Service Activator"]
    SA --> OUT["Outbound Channel Adapter"]
    OUT --> SYS["External sink"]
    REQ["External caller"] --> IG["Inbound Gateway"]
    IG --> CH
    SA --> IG
    CH --> OG["Outbound Gateway"]
    OG <--> API["Remote request–reply API"]
~~~

Bài thuộc chương **Channel adapter** của module **SPRING_INTEGRATION_PATTERN**. Module này hướng tới học triển khai Enterprise Integration Patterns với **Spring Integration** để xây dựng message flow ít phụ thuộc, dễ mở rộng; thực hành **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và theo dõi các nhánh xử lý. Chủ đề trực tiếp của bài là **“Phân biệt adapter với gateway và service activator”**.

**Kết quả học tập:** bạn sẽ chọn đúng endpoint theo chiều luồng và nhu cầu reply; phân biệt transport ACK với business result, hiểu xử lý lỗi đồng bộ/bất đồng bộ, giữ correlation và idempotency, và kiểm thử đường inbound/outbound trong Spring Integration.

## 2. Định nghĩa Channel Adapter

Theo Enterprise Integration Patterns, **Channel Adapter** kết nối một hệ thống/ứng dụng với một **message channel**, giúp chuyển giữa giao tiếp của nguồn/đích bên ngoài và hạ tầng messages.

Có hai hướng:

~~~text
Inbound Channel Adapter:
  External source → Adapter → MessageChannel → IntegrationFlow

Outbound Channel Adapter:
  IntegrationFlow → MessageChannel → Adapter → External target
~~~

Adapter thường có hợp đồng **one-way messaging**: gửi hoặc nhận message, **không tạo một reply nghiệp vụ bắt buộc** trên chính endpoint đó.

Ví dụ: đọc file CSV mới, nhận record từ Kafka, gửi sự kiện sang queue, ghi một file export, đưa message vào một remote sink. Một thao tác outbound có thể nhận **transport-level acknowledgement** hoặc ném exception, nhưng đó **không phải tự động là một application reply message**.

**Nhớ:** Adapter không có nghĩa luôn async. File polling có poller, HTTP outbound adapter có thể block trong lúc gửi, Kafka producer có thể dùng async callback. **One-way** nói về *hợp đồng reply*, không phải tuyệt đối về thread hay thời gian xử lý.

## 3. Định nghĩa Gateway

**Messaging Gateway** cung cấp cách đi từ thế giới lời gọi request/response sang message flow, hoặc gọi một endpoint ngoài và nhận kết quả:

~~~text
Inbound Gateway:
  External request → Gateway → Request channel
                               ↓
                           Flow handler
                               ↓
  External reply ← Gateway ← Reply message

Outbound Gateway:
  Internal request message → Gateway → Remote request
  Internal reply message   ← Gateway ← Remote reply
~~~

Khác Adapter one-way, một Gateway request–reply phải quản lý **hợp đồng kết quả**: reply address, correlation, timeout và error mapping, tùy giao thức và cấu hình.

Còn có **Java interface `@MessagingGateway`**: Spring Integration tạo proxy để application code gọi một method có kiểu, rồi đưa request vào flow và nhận reply. Nó là **application-facing gateway proxy**, không nhất thiết là cùng một HTTP inbound/outbound transport gateway.

**Nhớ:** Gateway không có nghĩa mọi call đều synchronous end-to-end hoặc mọi lỗi tự thành business response. Một request có thể timeout, đến muộn hoặc bị drop trong một Filter; xử lý các trường hợp đó là phần của contract.

## 4. Định nghĩa Service Activator

**Service Activator** đưa một message tới **một phương thức ứng dụng**:

~~~text
MessageChannel → Service Activator → businessService.method(payload)
                                        ↓
                                    return value
                                        ↓
                                reply Message (nếu có)
~~~

Một method `void` có thể nhận event và ghi trạng thái; một method trả DTO có thể tạo reply cho request–reply flow. Service Activator **không tự định nghĩa giao thức external transport** và không phải khái niệm dùng để poll file hay consume Kafka partition.

Spring Integration có thể cấu hình bằng `@ServiceActivator` hoặc DSL `.handle(bean, "method")`/typed handler. Một service method có thể có side effect, vì vậy phải quản lý **authorization, transaction, idempotency, retry và error handling** tùy nghiệp vụ.

**Nhớ:** Service Activator nối **messaging → application method**, Gateway cung cấp **request–reply boundary**, Channel Adapter nối **external endpoint ↔ messaging** theo **one-way** semantics.

## 5. Bảng so sánh tổng quan

| Đặc điểm | Channel Adapter | Gateway | Service Activator |
|---|---|---|---|
| Mục tiêu | Kết nối message với nguồn/đích ngoài | Nối request với reply | Gọi method xử lý của ứng dụng |
| Hướng | Inbound hoặc outbound | Inbound hoặc outbound; Java proxy cũng là một dạng | Từ MessageChannel tới handler |
| Message reply bắt buộc | **Không** theo hợp đồng one-way | **Có** khi hoạt động request–reply | **Có thể có**, tùy method |
| Ví dụ | Kafka inbound, file inbound, file/HTTP outbound adapter | HTTP inbound/outbound gateway, `@MessagingGateway` | `@ServiceActivator`, DSL `.handle(orderService, "place")` |
| Ai quản lý transport? | Adapter + client/container | Gateway + client/container | Không mặc định, do flow/adapter |
| Ai xử lý business? | Thông thường không | Thông thường ủy quyền cho flow | Business service method |
| Timeout | Poll/send/transport policy | Thêm request/reply timeout và correlation | Handler timeout/dependency policy |
| Một endpoint có thể tạo side effect? | Có, khi gửi ra target | Có, remote/service có thể commit | Có, nếu business method ghi |
| Error boundary | Adapter/poller/container | Caller/error reply/transport/container | Caller thread/error channel tùy channel |

**Cột reply không phải lời hứa về độ tin cậy.** Một Gateway không nhận reply có thể timeout; Adapter one-way gửi thành công không đồng nghĩa remote hoàn tất nghiệp vụ; Service Activator return xong vẫn có thể chưa thực hiện side effect async được khởi tạo bên trong.

## 6. Chọn nhanh qua một câu hỏi

~~~mermaid
flowchart TD
    A["Cần kết nối message flow với nguồn/đích ngoài?"] -->|"Có"| B{"Caller cần application reply?"}
    B -->|"Không"| C["Inbound/Outbound Channel Adapter"]
    B -->|"Có"| D["Inbound/Outbound Gateway"]
    A -->|"Không, cần gọi method ứng dụng"| E["Service Activator"]
    A -->|"Java application gọi flow"| F["@MessagingGateway interface"]
~~~

Đây là **cây quyết định khởi đầu**, không thay thế phân tích nghiệp vụ:

- Nếu external source tự đẩy event một chiều → inbound adapter thường hợp lý.
- Nếu external HTTP client gửi request và cần response → inbound gateway.
- Nếu flow publish event mà không cần business reply → outbound adapter.
- Nếu flow gọi remote HTTP và cần response → outbound gateway.
- Nếu flow cần gọi `OrderService.place()` → Service Activator.
- Nếu Java controller muốn gọi flow qua typed method → `@MessagingGateway` proxy.

**Không chọn endpoint chỉ theo nhãn “HTTP”, “Kafka” hay “JMS”.** Trước tiên xác định one-way hay request–reply, sau đó chọn adapter hỗ trợ transport tương ứng.

## 7. Hai hướng Adapter không đồng nghĩa hai hướng Gateway

Các mũi tên dưới đây biểu diễn **direction tương đối với Spring Integration flow**:

~~~text
INBOUND ADAPTER:
External (event producer) ──▶ MessageChannel

OUTBOUND ADAPTER:
MessageChannel ──▶ External (event sink)

INBOUND GATEWAY:
External caller ──▶ MessageChannel
External caller ◀── Reply from MessageChannel

OUTBOUND GATEWAY:
MessageChannel ──▶ External service
MessageChannel ◀── External reply
~~~

**Inbound/outbound** là hướng đi vào/ra integration application, **không** tự có nghĩa request/response. Cả Adapter và Gateway đều có thể là inbound/outbound.

Ví dụ **HTTP inbound channel adapter** có thể nhận HTTP rồi trả một transport response/ACK theo cách adapter được cấu hình nhưng **không chờ reply message nghiệp vụ của flow**. **HTTP inbound gateway** được dùng khi HTTP response phải dựa trên reply từ flow.

## 8. Ví dụ xuyên suốt: đơn hàng, Inventory và Audit

Thiết kế bốn đường:

~~~text
1. Broker event:
   Kafka orders.events
     → Kafka inbound adapter
     → OrderEvent handler

2. Query:
   HTTP GET /orders/{id}
     → HTTP inbound gateway
     → OrderQuery Service Activator
     → HTTP reply

3. Remote reservation:
   Internal command
     → HTTP outbound gateway
     → Inventory API
     ← Reservation reply

4. Audit event:
   Order processing event
     → outbound channel adapter
     → audit topic/file
~~~

Từng đường có contract:

| Đường | Ý nghĩa | Reply nghiệp vụ |
|---|---|---|
| Kafka event ingress | Tiếp nhận một event để xử lý sau | Không phải reply tới original producer |
| HTTP order query | Caller hỏi và chờ dữ liệu | Có |
| Remote inventory reservation | Flow cần biết đã giữ hàng chưa | Có |
| Audit sink | Phát audit event one-way | Không |

Một Service Activator có thể xuất hiện **bên trong cả bốn flow** nếu cần gọi business method. Nó là bước xử lý, không cạnh tranh vai trò với transport boundary.

## 9. Message flow và application code nên tách lớp

Một tổ chức dễ duy trì:

~~~text
Transport layer:
  Kafka inbound adapter / HTTP inbound gateway
          ↓
Integration layer:
  MessageChannel → Filter → Router → Transformer
          ↓
Application layer:
  Service Activator → OrderService
          ↓
Integration layer:
  Outbound adapter / outbound gateway
~~~

Định nghĩa boundaries giúp:

- Thay Kafka bằng một nguồn event khác mà không sửa domain logic nếu message contract giữ nguyên.
- Chuyển remote HTTP API thành broker request–reply mà application port không cần biết chi tiết.
- Test business service độc lập Spring Integration context.
- Test transport serialization/header mapping ở adapter/gateway riêng.
- Đặt retry và error handling đúng boundary thay vì catch mọi exception trong một method tổng quát.

**Tách lớp không có nghĩa luôn phải tạo một endpoint cho mỗi thao tác nhỏ.** Điều cần đạt là mỗi endpoint có trách nhiệm và hợp đồng message rõ.

## 10. Inbound adapter: polling source và event-driven source

Một inbound adapter có thể **poll** nguồn:

~~~text
Poller fixedDelay
  → kiểm tra thư mục
  → tìm file mới
  → phát Message<File> vào channel
~~~

Hoặc **message-driven**:

~~~text
Kafka/AMQP listener
  → nhận record/delivery qua callback/container
  → phát Message<Payload> vào channel
~~~

**Polling** quyết định thời điểm lấy dữ liệu từ nguồn. **Event-driven** cho phép nguồn/container gọi adapter khi event xuất hiện; Kafka consumer phía dưới vẫn dùng mô hình poll loop của Kafka client, nên từ “message-driven adapter” ở Spring Integration nói về *cách kết nối adapter với flow*, không chứng minh broker không sử dụng poll.

Không chọn poller chỉ vì cần “đảm bảo giao hàng”: delivery guarantees còn phụ thuộc source state, transaction, duplicate detection, error handling và recovery.

## 11. Outbound adapter: one-way không có nghĩa gửi xong là đã commit

Một outbound adapter gửi event:

~~~text
Message<OrderPlaced>
  → outbound Kafka/AMQP/file/HTTP adapter
  → external destination
~~~

Thao tác gửi có thể:

- Return sau khi local API nhận request.
- Đợi một transport acknowledgement.
- Bị timeout hoặc lỗi network.
- Có callback async thành công/thất bại.

Nhưng **application reply như ReservationResult hay PaymentStatus** không tự xuất hiện trong downstream message flow. Nếu cần response đó, dùng **outbound gateway** hoặc workflow gồm command event và completion event được correlate, không mặc định một outbound adapter sẽ trả typed result.

Không đánh đồng **broker publish confirmed**, **consumer ACK**, **downstream database COMMIT** và **final business outcome**.

## 12. Service Activator cũng có thể là request–reply handler

Một method:

~~~java
@MessageEndpoint
class OrderQueryEndpoint {
    private final OrderQueryService queries;

    OrderQueryEndpoint(OrderQueryService queries) {
        this.queries = queries;
    }

    @ServiceActivator(
        inputChannel = "orders.query")
    public OrderView get(FindOrderQuery query) {
        return queries.get(query);
    }
}
~~~

Method trả `OrderView` nên **Service Activator có thể phát reply message**; khi endpoint không chỉ định một output channel cố định, nó có thể sử dụng return address/reply channel từ request theo cơ chế message handling của Spring Integration. Điều này **không biến endpoint thành một transport Gateway**: Gateway vẫn chịu trách nhiệm đưa request vào từ caller và trả reply ra boundary phù hợp.

Không thêm một `outputChannel` cố định cho Gateway mà không xem topology: trong request–reply flow, Gateway có thể đặt temporary `replyChannel`; cấu hình reply channel riêng cần nối đúng lại tới caller, tránh gửi result vào queue không có người trả lời.

## 13. Java records cho ví dụ xuyên suốt

Để minh họa bốn loại boundary, định nghĩa một số kiểu dữ liệu Java 17:

~~~java
record FindOrderQuery(
    String tenantId,
    String orderId
) {}

record OrderView(
    String orderId,
    String status
) {}

record PlaceOrderCommand(
    String tenantId,
    String commandId,
    String orderId
) {}

record ReserveStockCommand(
    String tenantId,
    String commandId,
    String orderId,
    String sku,
    int quantity
) {}

record ReservationResult(
    String commandId,
    String reservationId,
    String status
) {}

record ReservationHttpResponse(
    String requestId,
    String reservationId,
    String state
) {}

record AuditEvent(
    String eventId,
    String operation,
    String outcome
) {}
~~~

Những records là **application contracts**, không phải DTO được Spring Integration cung cấp. Trong triển khai thực tế:

- Validate `quantity > 0`, IDs không null/blank và schema versions.
- Xác thực `tenantId` từ principal/context đáng tin, không chỉ từ body do caller tự khai.
- Bảo vệ `commandId` như logical idempotency key ổn định giữa các retries.
- Phân biệt `status=ACCEPTED` và `status=COMMITTED` theo contract.
- Dùng error type hoặc reason code, không coi mọi `null` là success.

Các ví dụ độc lập bên dưới dùng chính các kiểu này nhưng không giả định chạy cùng nhau trên mọi input channel.

## 14. Ví dụ inbound Channel Adapter: đọc file theo poller

Một cách cấu hình annotation-based:

~~~java
@Configuration
@EnableIntegration
class FileIntakeConfiguration {

    @Bean
    @InboundChannelAdapter(
        channel = "files.incoming",
        poller = @Poller(fixedDelay = "1000"))
    MessageSource<File> orderFiles() {
        FileReadingMessageSource source =
            new FileReadingMessageSource();
        source.setDirectory(new File("/var/app/orders/incoming"));
        return source;
    }
}
~~~

**Luồng:**

~~~text
Directory /var/app/orders/incoming
  → FileReadingMessageSource
  → @InboundChannelAdapter + Poller
  → Message<File> trên files.incoming
  → Transformer parser/Validator
  → downstream business flow
~~~

Adapter **poll nguồn và phát message**. Nó không biết application có tạo đơn thành công hay không; không có external caller nào đợi một reply từ chính `FileReadingMessageSource`.

**Lưu ý production:** source/file filter nên xử lý file locking, marker hoặc move-to-processed, retry/quarantine, quyền đọc thư mục, giới hạn dung lượng và duplicate detection. Một file có thể được nhìn thấy hoặc xử lý lại sau crash; chỉ có `@Poller` không chứng minh exactly-once.

Đoạn code cần imports Spring Integration File và annotation phù hợp phiên bản; đường dẫn thư mục chỉ là minh họa. Không đọc file khác trong workspace để thực hiện bài này.

## 15. Ví dụ inbound adapter message-driven: nhận từ broker

Với Kafka, dạng luồng thường gặp:

~~~text
Kafka topic orders.events
  → Kafka consumer group/container
  → Kafka message-driven inbound adapter
  → Message<OrderEvent> trên orders.events.in
  → IntegrationFlow
~~~

Một consumer container quản lý:

- Consumer group và partition assignment.
- Polling, offset commits và rebalance.
- Deserialization/container error handling.
- Transport retry/DLT khi được cấu hình.

Inbound adapter biến record thành Spring message. **Không nhầm broker offset commit/consumer ACK với business reply cho producer**; Kafka producer không mặc nhiên nhận `OrderReceipt` khi record được consumer đọc.

Đối với RabbitMQ/JMS, listener adapter có ACK/redelivery semantics khác Kafka. Một inbound adapter được gọi là message-driven không bảo đảm subscriber chạy trên caller thread hoặc không thể xử lý trùng.

## 16. Ví dụ outbound Channel Adapter: phát audit event

Nếu flow chỉ cần gửi audit event tới một HTTP endpoint bên ngoài, không cần đọc business result:

~~~java
@Bean
IntegrationFlow auditOutboundFlow() {
    return IntegrationFlow.from("audit.out")
        .handle(
            Http.outboundChannelAdapter(
                    "https://audit.example.invalid/events")
                .httpMethod(HttpMethod.POST))
        .get();
}
~~~

Đây là **outbound channel adapter**. Nó gửi payload ra một remote sink nhưng không biến HTTP response body thành một `AuditResult` reply message tiếp tục đi trong flow.

Địa chỉ `audit.example.invalid` là placeholder, không phải địa chỉ thật. Với production cần cấu hình serializer, request factory/HTTP client, TLS/authentication, timeout, response status/error classifier, quota và retry. Đừng truyền secrets hay PII chưa cần thiết trong audit payload.

**Nguyên tắc:** nếu caller cần xác nhận chính xác audit đã được **persist ở remote**, việc gửi HTTP và nhận transport status có thể chưa đủ; cần remote API contract rõ, callback/status hoặc request–reply gateway nếu có response nghiệp vụ.

## 17. Outbound adapter ghi file khác business commit

Một adapter xuất dữ liệu:

~~~text
Business service → Message<OrderExport>
  → Transformer to CSV
  → File outbound adapter
  → /exports/orders-501.csv
~~~

File outbound adapter có thể thực hiện I/O, nhưng **file đã ghi không đồng nghĩa consumer bên ngoài đã nhập dữ liệu vào hệ thống của họ**.

Các câu hỏi:

- File được ghi atomic hay đang dở khi process crash?
- Nếu retry cùng message, overwrite/append/duplicate file thế nào?
- Có marker hoặc tên file idempotent không?
- Nếu file đã ghi nhưng broker offset chưa commit, redelivery có tạo file thứ hai không?
- Downstream partner cần acknowledgement **sau khi ingest** hay chỉ cần file xuất hiện?

Nếu partner phải gửi kết quả nhập liệu, đó là **workflow hai chiều**, không còn là một outbound adapter one-way tự giải quyết. Có thể dùng hai adapters cho command/completion messages cùng correlation, hoặc một gateway nếu giao thức thực sự request–reply.

## 18. Ví dụ HTTP inbound Gateway: client chờ kết quả

Một HTTP endpoint dạng request–reply:

~~~java
@Bean
IntegrationFlow orderHttpQueryFlow(
        OrderQueryService queries) {
    return IntegrationFlow
        .from(
            Http.inboundGateway("/orders/query")
                .requestMapping(m -> m.methods(HttpMethod.POST))
                .requestPayloadType(FindOrderQuery.class))
        .handle(
            FindOrderQuery.class,
            (query, headers) -> queries.get(query))
        .get();
}
~~~

Hợp đồng:

~~~text
HTTP request
  → Inbound Gateway
  → Message<FindOrderQuery>
  → Service handler returns OrderView
  → Reply message
  → Gateway maps response to HTTP
~~~

**Không dùng inbound channel adapter** khi HTTP client cần chính `OrderView` làm response. Inbound adapter one-way có thể trả response transport theo cấu hình mà **không đợi dữ liệu nghiệp vụ từ flow**.

Đoạn DSL là ví dụ cấu trúc; để chạy phải có HTTP message converters, method/status mapping, authentication và error mapping phù hợp Spring Integration version. Nếu content negotiation/response serialization sai, một `OrderView` hợp lệ bên trong JVM vẫn có thể không thành HTTP response đúng.

## 19. Ví dụ HTTP outbound Gateway: phải dùng response body

Đặt tồn kho qua remote API:

~~~java
@Bean
IntegrationFlow reserveStockRemoteFlow() {
    return IntegrationFlow.from("stock.reserve.remote")
        .handle(
            Http.outboundGateway(
                    "https://inventory.example.invalid/reservations")
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(
                    ReservationHttpResponse.class))
        .get();
}
~~~

Hợp đồng:

~~~text
Message<ReserveStockCommand>
  → HTTP outbound gateway
  → remote Inventory API
  ← HTTP response body
  ← Message<ReservationHttpResponse> in flow
~~~

Gateway cho phép flow **nhận response message để chuyển tiếp xử lý**. Một Transformer cần kiểm tra `requestId`/`commandId`, `reservationId`, `state`, schema và tenant trước khi tạo `ReservationResult`. Nếu remote trả 202 Accepted, có thể chỉ có pending reference thay vì reservation đã commit.

Để phù hợp API thật, cần request mapper/JSON converter, authentication và mapping HTTP response statuses; snippet chỉ thể hiện lựa chọn loại endpoint. **Không chuyển 503 hoặc network timeout thành `OUT_OF_STOCK`**.

## 20. Ví dụ `@MessagingGateway`: application gọi flow như một method

Một Gateway interface:

~~~java
@MessagingGateway
interface StockApplicationGateway {

    @Gateway(requestChannel = "stock.reserve.remote")
    ReservationHttpResponse reserve(
        ReserveStockCommand command);
}
~~~

Caller:

~~~java
@Service
class CheckoutUseCase {
    private final StockApplicationGateway stock;

    CheckoutUseCase(StockApplicationGateway stock) {
        this.stock = stock;
    }

    ReservationHttpResponse reserve(ReserveStockCommand command) {
        return stock.reserve(command);
    }
}
~~~

Khác biệt:

- **`@MessagingGateway`:** Java application method → request message → chờ reply (theo method signature/contract).
- **HTTP outbound Gateway:** message trong flow → HTTP remote call → reply message.
- **Service Activator:** message trong flow → local service method → optional reply.

Ba lớp này **có thể nằm trong một chuỗi**. Chúng không thay thế 1:1 cho nhau.

~~~text
CheckoutUseCase
  → StockApplicationGateway [Java proxy]
  → stock.reserve.remote [request channel]
  → HTTP outbound Gateway [transport request–reply]
  → Inventory API
  ← ReservationHttpResponse
  ← StockApplicationGateway
  ← CheckoutUseCase
~~~

Spring Integration cần kích hoạt scanning/registration của Gateway interface, ví dụ `@IntegrationComponentScan` trong cấu hình thích hợp. Production nên để application port trả **domain result**, không bắt toàn bộ business layer phụ thuộc remote HTTP DTO.

## 21. Ví dụ Service Activator: xử lý lệnh nội bộ

Một command service:

~~~java
@Service
class OrderCommandService {
    private final OrderRepository orders;

    OrderCommandService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public OrderView place(PlaceOrderCommand command) {
        validateAndAuthorize(command);
        return orders.createIdempotently(command);
    }

    private void validateAndAuthorize(PlaceOrderCommand command) {
        // Ứng dụng tự triển khai validation/authorization.
    }
}
~~~

Một endpoint:

~~~java
@MessageEndpoint
class PlaceOrderActivator {
    private final OrderCommandService orders;

    PlaceOrderActivator(OrderCommandService orders) {
        this.orders = orders;
    }

    @ServiceActivator(inputChannel = "orders.place")
    public OrderView place(PlaceOrderCommand command) {
        return orders.place(command);
    }
}
~~~

Ở đây `PlaceOrderCommand`, `OrderRepository` và `createIdempotently()` là **application abstractions** cần hiện thực. Service Activator chọn đúng method; `@Transactional` ở business service chịu trách nhiệm transaction khi được Spring proxy invoke đúng. **Không đặt giả định Service Activator tự bật transaction hay idempotency**.

Nếu external request cần trả `OrderView` qua HTTP, **HTTP inbound Gateway** (hoặc Controller gọi `@MessagingGateway`) sẽ là nơi đảm nhiệm transport và reply. Service Activator chỉ biết gọi `orders.place()`.

## 22. Một flow có thể chứa cả ba vai trò

~~~mermaid
sequenceDiagram
    participant Client as HTTP client
    participant IG as HTTP Inbound Gateway
    participant SA as Service Activator
    participant OG as HTTP Outbound Gateway
    participant Inventory as Inventory API
    Client->>IG: POST /orders
    IG->>SA: PlaceOrderCommand message
    SA->>SA: Validate + persist intent
    SA->>OG: ReserveStockCommand message
    OG->>Inventory: POST /reservations
    Inventory-->>OG: ReservationResult
    OG-->>IG: Completion reply (after workflow)
    IG-->>Client: HTTP response
~~~

Sơ đồ mô tả **một workflow khái niệm**. Để chạy đúng, phải có Router/Transformer, transaction boundaries, reply routing, error handling và orchestration state nếu có nhiều bước. Không xem sequence diagram như một cơ chế tự động để nối `Service Activator` và `Outbound Gateway`.

Nếu business workflow dài, cần nhiều retries hoặc compensation, **đừng giữ HTTP Gateway đồng bộ hàng phút** chỉ để tạo cảm giác method call. Trả `ACCEPTED/PENDING` sau khi lưu durable intent, rồi dùng status query/completion event khi phù hợp.

## 23. Channel Adapter và Gateway khác nhau ở reply semantics

| Tình huống | Outbound Adapter | Outbound Gateway |
|---|---|---|
| Gửi một `AuditEvent`, không cần body phản hồi | Phù hợp | Thường dư thừa |
| Gửi POST và cần `ReservationResult` | Không có reply business theo pattern | Phù hợp |
| Remote trả HTTP 202 | Có thể chỉ là transport/accepted response | Có thể map thành `PENDING` theo contract |
| Remote trả lỗi 503 | Send/handler có thể lỗi | Request–reply call có thể lỗi |
| Client timeout sau server commit | Outcome vẫn không chắc | Outcome vẫn không chắc |
| Phát event ra Kafka | Phù hợp | Chỉ dùng gateway khi giao thức reply được thiết kế |

**Không nói Adapter hoàn toàn không nhận phản hồi ở cấp transport.** Client library có thể biết HTTP status hoặc broker publish acknowledgement. Sự khác nhau nằm ở **hợp đồng message reply cho downstream flow/caller**, không phải có hay không có network response bytes.

## 24. Gateway và Service Activator khác nhau ở ranh giới trách nhiệm

| Câu hỏi | Gateway | Service Activator |
|---|---|---|
| Ai gọi? | Caller external hoặc Java application/flow | Upstream message channel |
| Ai phải nhận result? | Gateway caller/request | Có thể downstream flow/Gateway |
| Giao thức remote? | Có thể trực tiếp dùng HTTP/AMQP/JMS gateway | Không tự có transport |
| Business validation? | Có thể pre-filter/map | Business service phải kiểm tra |
| Chạy side effect? | Remote call có thể tạo side effect | Method có thể tạo side effect |
| Retry? | Transport/call policy | Handler/advice/business policy |
| Reply correlation? | Thiết yếu khi request–reply, nhất là async | Không tự tạo cross-process correlation |

Gateway có thể gọi một Service Activator rồi nhận reply, vì vậy **không phải chọn Gateway hoặc Service Activator** nếu cần cả hai. Một request–reply pipeline thường cần Gateway **tại boundary** và Service Activator **ở đoạn xử lý**.

## 25. Lựa chọn endpoint dựa trên nhu cầu, không dựa trên tên method

Giả sử một phương thức tên `send()`:

~~~java
void send(AuditEvent event);
~~~

Tên `send` không đủ xác định dùng adapter hay gateway: có thể là method Java Gateway one-way, hoặc là một POJO được Service Activator gọi, còn outbound transport do một adapter thực hiện.

Tương tự một method `place()` trả `OrderView` không biến nó thành transport Gateway. Và một outbound HTTP adapter có thể block network nên **không có nghĩa** nó là Gateway request–reply.

Đọc **direction, caller, contract, return address, side effect, retry/error boundary** trước khi chọn thành phần.

## 26. Reply channel: điều gì xảy ra nếu handler không trả reply?

Ví dụ một external HTTP caller gửi request tới **inbound Gateway**, mong một `OrderView`:

~~~text
HTTP client
  → Inbound Gateway
  → Filter reject rồi discard
  → không có reply message
  → HTTP request chờ đến reply timeout
~~~

Một Filter trả `false` có thể đúng nếu đó là **one-way event ingestion** và event được phép bỏ qua. Nhưng trong **request–reply flow**, discard im lặng thường làm caller nhận **timeout không rõ lý do**.

Thiết kế rõ hơn:

- **Fail-fast:** ném typed validation exception và map nó thành HTTP 4xx/response có reason code.
- **Typed rejection:** handler trả `OrderRejected(reasonCode)` thay vì không trả gì.
- **Async accepted:** nếu công việc dài, trả `OrderPending(statusReference)` **sau khi durable intent được lưu**, không giả vờ hoàn tất.

**Discard channel không tự là error reply channel.** Nếu muốn trả rejection từ một discard flow, phải nối có chủ đích với return address, kiểm tra correlation và contract của Gateway.

## 27. Một Service Activator trả `void` có phù hợp không?

Ví dụ one-way:

~~~java
@MessageEndpoint
class AuditActivator {
    private final AuditService audit;

    AuditActivator(AuditService audit) {
        this.audit = audit;
    }

    @ServiceActivator(inputChannel = "audit.in")
    public void record(AuditEvent event) {
        audit.record(event);
    }
}
~~~

Nếu upstream chỉ phát event, `void` có thể phù hợp. Nếu **Gateway đồng bộ đang chờ business result** nhưng Service Activator `void` và không có bước nào tạo reply, caller có thể timeout.

**Một void handler chạy thành công không biến Gateway thành one-way một cách an toàn nếu caller đang chờ reply.** Phải chọn contract ngay từ application boundary:

- One-way `void` hoặc fire-and-forget khi thực sự không cần kết quả.
- Request–reply typed method khi cần success/rejection/pending.
- Async workflow với durable status nếu không thể chờ final result.

Nếu handler tạo side effect rồi return `null`, Gateway timeout không hoàn tác side effect. Caller retry phải dùng **cùng logical command ID** để tránh double write.

## 28. Error channel, reply channel và discard channel là ba thứ khác nhau

Một flow có thể có:

~~~text
Request Message
  ├── replyChannel → kết quả thành công/có nghĩa cho caller
  ├── errorChannel → lỗi ở boundary hỗ trợ error messaging
  └── discardChannel → message bị Filter loại theo policy
~~~

| Channel/context | Mang thông tin gì? | Có trả lời caller tự động không? |
|---|---|---|
| **Reply channel** | Result message của request | Có thể, nếu nối tới gateway caller |
| **Error channel** | Thường là `ErrorMessage(Throwable)` | Không mặc nhiên là business reply |
| **Discard channel** | Message bị Filter discard | Không tự là error response |
| **DLQ/DLT** | Message/recovery evidence tại broker | Không phải synchronous gateway reply |

Đừng lấy `errorChannel` làm một “success response sink”, và cũng đừng đẩy mọi business rejection vào DLQ. Một `OUT_OF_STOCK` có thể là **business result hợp lệ**, không phải transport failure.

## 29. Đồng bộ và bất đồng bộ thay đổi nơi bắt lỗi

~~~mermaid
flowchart TD
    IN["Inbound message"] --> D{"Boundary"}
    D -->|"DirectChannel"| SYNC["Handler trên sender thread"]
    D -->|"ExecutorChannel / listener / poller"| ASYNC["Worker thread"]
    SYNC -->|"Throws"| CALLER["Caller exception path"]
    ASYNC -->|"Throws"| ERROR["ErrorMessage / container recoverer"]
    SYNC -->|"Returns"| REPLY["Reply if contract expects"]
    ASYNC -->|"Returns"| STATUS["Async completion/transport policy"]
~~~

**DirectChannel đồng bộ:** exception thường lan theo caller thread; không phải mọi lỗi sẽ tự chuyển sang global `errorChannel`.

**ExecutorChannel/broker/poller:** handler có thể ném lỗi sau khi sender đã `send()` trả về; cần error handler/recoverer ở **đúng async boundary**. ACK source trước khi durable processing hoàn tất có thể gây mất việc nếu JVM crash.

**Service Activator không quyết định tính sync/async một mình**. Kiểu channel, poller, scheduler, transport adapter và handler behavior cùng quyết định.

## 30. Bốn failure windows của Adapter/Gateway/Service Activator

Giả sử inbound adapter nhận `PlaceOrderCommand`, Service Activator ghi DB, outbound adapter phát event:

~~~text
T1 Broker nhận event.
T2 Inbound adapter đưa message vào flow.
T3 Service Activator bắt đầu transaction.
T4 DB commit order.
T5 Outbound adapter publish completion event.
T6 Inbound source ACK/commit offset.
~~~

| Crash ở đâu? | Nguy cơ | Biện pháp |
|---|---|---|
| Trước T2 | Message có thể được giao lại | Transport durability/ACK policy |
| Sau T2, trước T4 | Xử lý chưa commit | Retry nếu transaction rollback sạch |
| Sau T4, trước T6 | Redelivery làm double write | Durable idempotency/inbox |
| Sau publish T5, trước mark sent | Completion event có thể được phát lại | Outbox + consumer dedupe |

Nếu dùng Gateway request–reply, còn thêm cửa sổ **business COMMIT thành công nhưng reply đến muộn/mất**. Gateway timeout chỉ là kết quả quan sát của caller, **không chứng minh transaction rollback**.

## 31. Transport acknowledgement không phải business outcome

Một Kafka producer nhận publish acknowledgement:

~~~text
Producer → Broker ACK
Broker → Consumer group xử lý sau
Consumer → Service Activator commit business DB
~~~

Mốc ACK của producer có thể đến **trước** consumer xử lý. Tương tự RabbitMQ consumer ACK hoặc Kafka offset commit phản ánh transport progress; không mặc nhiên bảo đảm external business system đã hoàn tất mọi downstream effects.

Với HTTP outbound channel adapter, một HTTP 202 Accepted có thể nghĩa là remote **đã nhận request để xử lý sau**, không có nghĩa đã gửi email/thanh toán/đặt hàng thành công.

Nếu application cần biết remote **đã hoàn tất**, hãy thiết kế reply/callback/status workflow, không biến transport ACK thành một typed business result giả.

## 32. Retry: Adapter và Gateway cần chiến lược khác nhau

| Endpoint | Lỗi hay gặp | Retry cần chú ý |
|---|---|---|
| File inbound adapter | File bị khóa, đọc dở, parse sai | Retry/quarantine, file identity, rename atomic |
| Kafka inbound adapter | Deserializer error, rebalance, handler failure | Offset commit/DLT/recovery, domain dedupe |
| HTTP outbound adapter | Connect/read timeout, 429/503 | Side effect remote có thể đã xảy ra |
| HTTP outbound gateway | Remote timeout, invalid reply/correlation | Unknown outcome; same idempotency key |
| Service Activator | DB deadlock, validation failure, conflict | Transaction rollback, permanent vs transient |
| Java `@MessagingGateway` | Send timeout, reply timeout, caller retry | Không tạo commandId mới cho cùng logical command |

**Không retry nóng mọi exception**. Malformed payload, unauthorized operation hoặc same-id/different-payload conflict thường không thể trở thành hợp lệ khi retry cùng dữ liệu. Network timeouts sau request có side effect cần **reconciliation**.

Nếu `RequestHandlerRetryAdvice` được gắn vào một endpoint, nó chỉ bao quanh **handler đó**. Lỗi xảy ra ở worker async phía sau có thể nằm ngoài phạm vi advice; không suy rằng một retry policy đã bao trọn flow.

## 33. Gateway timeout và trạng thái “không biết kết quả”

Timeline:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant G as Gateway
    participant W as Worker
    participant DB as Database
    A->>G: place(commandId=C-701)
    G->>W: Request message
    W->>DB: Create order
    DB-->>W: COMMIT
    Note over G: Reply timeout
    G-->>A: Timeout / unknown outcome
    W--xG: Late reply
    A->>G: Retry same commandId C-701
    G->>W: Same logical command
    W-->>G: Cached committed result
    G-->>A: OrderPlaced once
~~~

Gateway không biến remote invocation thành local method call có atomic cancellation. Nếu caller timeout, worker có thể đã commit hoặc còn tiếp tục.

**Chống trùng:**

1. Giữ `commandId` trong domain contract.
2. DB inbox/processed record có unique constraint theo tenant/operation/commandId.
3. Lưu fingerprint để phát hiện same key/different command.
4. Nếu đã commit, trả kết quả bền vững đã lưu.
5. Nếu remote effect chưa rõ, dùng remote idempotency/reconcile.

Đổi `replyChannel`/Gateway call identity qua mỗi attempt là bình thường; **đổi business command ID** cho cùng một ý định retry mới là nguy hiểm.

## 34. Correlation giữa Gateway và Aggregator

Một request có thể tách ba nhánh:

~~~text
Gateway quote(Q-701)
  → Splitter
     → price task (member A)
     → tax task (member B)
     → discount task (member C)
  → Aggregator
  → QuoteResult
  → Gateway reply
~~~

**Gateway reply address** trả lời **lời gọi đang chờ**. **Aggregator correlation ID** gom ba members cùng logical workflow; hai ID có thể liên quan nhưng không phải cùng một khái niệm.

Một thiết kế tốt:

- Parent group ID theo tenant/request/revision, không dùng trace ID làm business group.
- Members A/B/C có unique identity, expected manifest.
- Child failure tạo typed failure outcome hoặc whole-group failure policy, không drop rồi chờ vô hạn.
- Duplicate child không được tính thành member mới.
- Release/expiry có chính sách cho partial/failed group.
- Return address được giữ/được map đúng qua transport hoặc có durable result lookup nếu caller đã timeout.

**Inbound Channel Adapter** nhận event không cần reply thì không tự trở thành Aggregator caller. Nếu một workflow cần final status gửi về external system, hãy thiết kế outbound result event/notification hoặc Gateway phù hợp.

## 35. Service Activator method có side effect và ranh giới transaction

Ví dụ unsafe:

~~~java
@ServiceActivator(inputChannel = "orders.preview")
public OrderView preview(FindOrderQuery query) {
    orders.createOrder(query.orderId()); // Sai business intent.
    return orders.getOrder(query.orderId());
}
~~~

Method có tên `preview` vẫn có thể ghi DB. Không có annotation nào tự chứng minh handler read-only.

Ví dụ an toàn hơn:

~~~java
@ServiceActivator(inputChannel = "orders.preview")
public OrderView preview(FindOrderQuery query) {
    return orderQueries.get(query);
}
~~~

Phân tách read-only query method và command method, validate/authorize theo nghiệp vụ, đặt transaction trong Spring-managed business service và dùng idempotency cho command có side effect.

**Không đặt `@Transactional` ở caller rồi tin transaction chạy qua ExecutorChannel/broker.** Transaction context gắn với thread/manager; worker phải có transaction boundary phù hợp.

## 36. Adapter không nên tự mang toàn bộ nghiệp vụ

Một inbound adapter có thể có logic kỹ thuật cần thiết: parse metadata, chuyển bytes thành message, mapping transport headers, ack/retry. Nhưng nếu bạn nhồi business processing vào adapter callback:

~~~java
void onKafkaRecord(ConsumerRecord<String, String> record) {
    Order order = parse(record.value());
    inventory.reserve(order);
    payment.charge(order);
    email.sendReceipt(order);
    acknowledgment.acknowledge();
}
~~~

thì **transport, business rules, side effects và ACK logic bị trộn**; khó test từng lớp, khó thay broker và khó kiểm soát một side effect đã commit khi các bước sau lỗi.

Tách trách nhiệm:

~~~text
Kafka inbound adapter
  → decode/validate
  → route
  → Service Activator: domain command handler
  → transactional inbox/outbox
  → Outbound adapter: publish completion event
~~~

Không nhất thiết phải tạo một lớp riêng cho mọi dòng code; mục đích là làm ranh giới và failure semantics **có thể review, kiểm thử và vận hành**.

## 37. Gateway không nên trở thành “business God Object”

Một Gateway interface:

~~~java
@MessagingGateway
interface DangerousGateway {
    Object execute(String methodName, Object payload);
}
~~~

Nếu flow dùng tên method hoặc bean name do caller tự cung cấp để invoke tùy ý, có thể có **arbitrary method invocation** hoặc đi nhầm vào handler có quyền ghi/hủy.

Thay bằng typed API:

~~~java
@MessagingGateway
interface OrderApplicationGateway {
    @Gateway(requestChannel = "orders.preview")
    OrderView preview(FindOrderQuery query);

    @Gateway(requestChannel = "orders.place")
    OrderView place(PlaceOrderCommand command);
}
~~~

Đây là hai **operations khác nhau**, có thể có authorization và retry policy khác nhau. **Gateway interface không tự kiểm tra quyền**; adapter ingress/business service phải xác thực tenant, principal và operation.

Không gộp mọi outbound HTTP calls vào một endpoint nhận arbitrary URL từ payload nếu caller bên ngoài có thể kiểm soát địa chỉ: đây có thể tạo SSRF hoặc truy cập service nội bộ không được phép.

## 38. Transformer và Router đứng đâu giữa ba thành phần?

Một IntegrationFlow:

~~~text
Inbound Adapter/Gateway
  → Transformer: wire DTO → canonical payload
  → Filter: schema/business preconditions
  → Router: choose operation/workflow branch
  → Service Activator: invoke business method
  → Transformer: domain result → external DTO
  → Outbound Adapter/Gateway
~~~

**Transformer** chuyển kiểu/biểu diễn payload, không tự là outbound transport. **Router** chọn channel, không tự gửi HTTP nếu không có outbound endpoint sau nó. **Filter** loại/cho phép messages, không nên tạo business side effects trong predicate.

Chọn **Gateway** nếu phải trả result; chọn **Adapter** nếu one-way. **Service Activator** ở vị trí gọi application method và có thể tạo reply cho Gateway.

**Không coi Filter discard là rejection reply**. Một Gateway có request bị discard im lặng sẽ có nguy cơ timeout.

## 39. Bảo toàn headers và phân biệt các loại identity

Một message có:

~~~text
payload.commandId = C-701
payload.orderId = O-701
headers.businessCorrelationId = tenant-a|O-701|revision-1
headers.traceId = trace-abc
headers.replyChannel = <temporary channel object>
headers.errorChannel = <configured error return address>
headers.kafka_receivedPartitionId = 2
headers.kafka_offset = 71
~~~

| Trường | Mục đích | Không nên dùng thay cho |
|---|---|---|
| `commandId` | Durable idempotency/business operation | Spring Message ID |
| `businessCorrelationId` | Gom logical workflow | Return address, trace ID |
| `traceId` | Theo dõi call chain | Business group hoặc authorization |
| `replyChannel` | Reply tới caller của invocation | Business ID xuyên broker |
| `errorChannel` | Error routing ở topology hỗ trợ | Guaranteed terminal outcome |
| Kafka partition/offset | Source position/replay | Domain idempotency toàn hệ thống |

Qua external transport, **Spring JVM channel objects không phải wire contract portable**. Các adapters/gateways phải map headers theo allowlist và giao thức (HTTP headers, AMQP reply-to, Kafka correlation). Nếu domain identity cần tồn tại qua retry/restart, đưa nó vào wire DTO hoặc durable mapping.

## 40. Chọn end-to-end delivery contract trước khi chọn adapter/gateway

| Nhu cầu | Thiết kế đáng cân nhắc |
|---|---|
| Nhận event, xử lý khi có tài nguyên | Inbound adapter + durable source ACK/retry/DLT |
| Đẩy event cho hệ thống khác, không cần result | Outbound adapter + delivery confirmation/Outbox |
| Client HTTP cần dữ liệu ngay | Inbound gateway + reply result/exception mapper |
| Flow cần remote response ngay | Outbound gateway + correlation/timeout |
| Java service cần gọi flow như method | `@MessagingGateway` interface |
| Xử lý một domain command sau khi đã có message | Service Activator + transaction/idempotency |
| Nghiệp vụ dài, cần trạng thái eventual | Durable command/event workflow + callback/status, có thể dùng các adapters |

Hai câu hỏi bổ sung:

1. **Ai chịu trách nhiệm retry nếu request được xử lý dở?** External caller, inbound container, handler advice, workflow manager hay một tầng duy nhất có budget?
2. **Khi nào được ACK?** Khi source đã được nhận, khi intent được lưu durable, hay khi full business completion thành công?

Không có câu trả lời chung cho Kafka, HTTP, JMS, file và AMQP. Chọn theo API contract và khả năng chịu được crash/duplicate của domain.

## 41. Unit test: Service Activator gọi đúng business method

Để xác nhận một message không làm gọi nhầm method có side effect, dùng mock business service:

~~~java
@Test
void queryActivatorDoesNotInvokeWriteService() {
    OrderQueryService queries = mock(OrderQueryService.class);
    OrderCommandService writes = mock(OrderCommandService.class);

    FindOrderQuery query =
        new FindOrderQuery("tenant-a", "O-701");
    OrderView expected = new OrderView("O-701", "CREATED");
    when(queries.get(query)).thenReturn(expected);

    OrderQueryEndpoint activator =
        new OrderQueryEndpoint(queries);
    OrderView result = activator.get(query);

    assertEquals(expected, result);
    verify(queries).get(query);
    verifyNoInteractions(writes);
}
~~~

**Test này chỉ xác nhận business adapter Java**, chưa kiểm tra Spring Integration dispatch tới đúng `@ServiceActivator`. Để kiểm chứng channel/method binding, cần một integration test gửi message qua channel thật và assert writes không được gọi.

Các classes `OrderQueryService`, `OrderCommandService` là abstractions của ứng dụng; đoạn test dùng JUnit 5/Mockito và cần imports/config phù hợp.

## 42. Integration test: request–reply Gateway gọi Service Activator

Trong một Spring test context riêng:

~~~java
@MessagingGateway(
    defaultRequestChannel = "test.orders.query")
interface TestOrderGateway {
    OrderView query(FindOrderQuery input);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class GatewayTestConfiguration {

    @Bean
    IntegrationFlow testOrderQueryFlow() {
        return IntegrationFlow.from("test.orders.query")
            .handle(
                FindOrderQuery.class,
                (query, headers) ->
                    new OrderView(query.orderId(), "CREATED"))
            .get();
    }
}
~~~

Kiểm thử khi `TestOrderGateway` đã được scan/register:

~~~java
@Autowired
TestOrderGateway gateway;

@Test
void gatewayReturnsTypedReply() {
    OrderView reply = gateway.query(
        new FindOrderQuery("tenant-a", "O-701"));

    assertEquals("O-701", reply.orderId());
    assertEquals("CREATED", reply.status());
}
~~~

Một message reply từ typed handler đủ cho Java gateway trả typed result theo flow đồng bộ. **Không cần caller tự tạo `MessageBuilder`, `replyChannel` hoặc cast payload**. Đó là tác dụng của `@MessagingGateway`.

Để test thực thi, dự án cần JUnit Spring test annotations và imports, gateway scanning đúng package và không đăng ký competing consumers từ production config vào cùng channel.

## 43. Integration test: one-way outbound adapter không trả business reply

Giả sử một fake HTTP server ghi nhận POST audit events nhưng trả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"receiptId":"A-701","state":"PENDING"}
~~~

Với outbound **channel adapter**:

- Assert fake server nhận đúng URL/method/body/headers.
- Assert endpoint không phát một `AuditReceipt` reply message vào downstream channel **chỉ vì server trả body**.
- Nếu server trả HTTP 500, assert error path được xử lý đúng.
- Nếu send timeout sau remote commit, không mặc định event chưa được nhận.
- Test replay cùng eventId không nhân đôi remote side effects theo remote policy.

Nếu ứng dụng cần dùng `receiptId` làm dữ liệu cho bước tiếp theo, **đổi sang outbound HTTP Gateway** và map response type; không dựa vào HTTP 202 của adapter one-way để tạo result không được định nghĩa.

**Không áp dụng test “không reply” bằng cách chỉ gọi một mock sender:** mock có thể bỏ qua actual HTTP adapter. Dùng fake HTTP server và IntegrationFlow/adapter thực.

## 44. Integration test: outbound Gateway trả typed remote reply

Một fake Inventory API:

~~~http
POST /reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: C-701

{"commandId":"C-701","sku":"SKU-5","quantity":2}
~~~

trả:

~~~json
{
  "requestId": "C-701",
  "reservationId": "RSV-701",
  "state": "RESERVED"
}
~~~

Test cần kiểm chứng:

1. Gateway gửi **đúng wire JSON/headers**.
2. Correlation `requestId == commandId`.
3. HTTP client converter giải mã đúng `ReservationHttpResponse`.
4. Transformer kiểm tra trạng thái và tạo `ReservationResult` phù hợp.
5. HTTP 409/422/503 được phân loại đúng, không trở thành `RESERVED`.
6. Network timeout sau remote commit trở thành **unknown outcome/reconciliation**, không báo business failure chắc chắn.

**Thử đồng thời hai request** và trả replies đảo thứ tự; mỗi caller phải nhận đúng reservation của mình. Với một synchronous HTTP client per invocation, mỗi response thuộc request cụ thể; khi chuyển sang broker request–reply, cần reply-to/correlation protocol thực sự thay vì dựa vào thứ tự queue.

## 45. Integration test: inbound adapter phát message mà không có caller reply

Với một file source hoặc fake broker adapter:

~~~text
External source → Inbound adapter
  → files.incoming / orders.events.in
  → TestChannel / capture handler
~~~

Assertions:

- Mỗi **source item** tạo đúng payload/header contract khi adapter tiếp nhận.
- Nếu source item không hợp lệ, có rejection/quarantine theo policy.
- Poller không chạy quá nhanh gây CPU/broker pressure.
- Một source item có thể được xử lý lại sau crash; test idempotency.
- Không có giả định external sender nhận một typed `OrderView` chỉ vì message đã đi vào channel.
- Dừng/start adapter có recovery behavior phù hợp.

**Test message count đơn thuần chưa đủ chứng minh delivery semantics**. Với file adapter, kiểm tra file vẫn còn/được chuyển vùng processed đúng; với broker adapter, kiểm tra ACK/offset commit và failure injection.

## 46. Failure injection: đã commit nhưng caller không nhận reply

Kịch bản:

~~~text
1. HTTP Inbound Gateway nhận PlaceOrderCommand C-701.
2. Service Activator ghi order + inbox, COMMIT.
3. HTTP client mất kết nối trước khi nhận response.
4. Client gửi lại C-701.
5. Business service trả cached receipt; không tạo order mới.
~~~

Test với DB/inbox thật:

~~~java
@Test
void retryWithSameCommandDoesNotCreateDuplicateOrder() {
    PlaceOrderCommand cmd =
        new PlaceOrderCommand("tenant-a", "C-701", "O-701");

    OrderView first = orderCommands.place(cmd);
    OrderView replay = orderCommands.place(cmd);

    assertEquals(first, replay);
    assertEquals(1, orders.countByOrderId("O-701"));
}
~~~

`orderCommands` và `orders` là test fixtures/repositories của ứng dụng, cần một unique constraint/inbox implementation thật. Để test **Gateway failure window**, còn phải inject crash/network drop sau commit trước reply tại HTTP boundary; gọi handler hai lần chưa thay được test transport.

**Không đưa mỗi transaction vào một test method `@Transactional` bao ngoài** khiến cả hai lời gọi dùng một transaction chưa commit; cần test ranh giới commit thật.

## 47. Test error channel và Filter discard khác nhau

Giả sử:

~~~text
Adapter one-way:
  invalid event → Filter discard allowed → metric skipped.

Gateway request–reply:
  invalid command → Filter discard → caller timeout (bad design).
  invalid command → typed rejection → caller receives useful error.

Async handler:
  unexpected failure → ErrorMessage/container recoverer.
~~~

Test assertions:

- One-way intentional skip không gây side effect.
- Gateway invalid input không bị biến thành “network timeout” nếu lý do đã biết.
- Handler exception trong `DirectChannel` được xử lý qua synchronous caller path.
- Handler exception trong `ExecutorChannel` đi tới đúng configured error path.
- Error handler không catch rồi ACK mất nguồn khi chưa lưu durable recovery.
- DLQ không nhận raw secrets/PII không cần thiết.

**Không khẳng định mọi exception tự đi vào `errorChannel`**. Lỗi deserializer có thể phát sinh **trước Spring Message**, còn lỗi runtime của async worker không mặc nhiên trả trực tiếp về caller.

## 48. Test concurrency, ordering và duplicate delivery

Một broker inbound adapter có ba consumers cùng group xử lý records độc lập. Một downstream Service Activator có thể ghi cùng order dưới hai conditions:

~~~text
EV-701  O-701 version 1
EV-702  O-701 version 2

Producer publish order key = tenant-a|O-701
→ cùng Kafka partition khi mapping ổn định
→ inbound adapter
→ ExecutorChannel thread pool
→ EV-702 có thể commit trước EV-701
~~~

Test:

1. Cùng key → producer partition assignment đúng.
2. Rebalance/replay → duplicate event không tạo side effect thứ hai.
3. Executor concurrency → version guard không chấp nhận stale state update.
4. Offset ACK/commit không đi trước durable completion nếu chưa có safe handoff.
5. Một Filter discard không làm Aggregator thiếu child hoặc báo success giả.
6. Outbound adapter publish event có idempotent/outbox policy.

**Kết quả IntegrationFlow được quyết định bởi toàn topology**, không chỉ type Adapter hay Gateway của endpoint đầu tiên.

## 49. Ma trận kiểm thử chọn endpoint

| Tình huống | Component mong đợi | Điều phải chứng minh |
|---|---|---|
| File mới xuất hiện | File inbound adapter | Phát file message, poll/recovery đúng |
| Kafka event vào flow | Kafka inbound adapter | Group/offset/error semantics đúng |
| Fire-and-forget audit | Outbound adapter | External sink nhận event; không fake business reply |
| HTTP client cần `OrderView` | HTTP inbound gateway | Caller nhận đúng reply |
| Flow cần response Inventory | HTTP outbound gateway | Reply typed, correlation đúng |
| Java service cần gọi flow | `@MessagingGateway` | Không cần tự tạo MessageChannel/headers |
| Message cần gọi `OrderService.place()` | Service Activator | Đúng method/transaction/idempotency |
| Handler `void` trong request–reply | Gateway contract mismatch | Không timeout im lặng |
| Filter reject client input | Gateway typed rejection | Không biến validation thành timeout |
| HTTP 202 từ outbound adapter | Adapter one-way | Không coi là domain completion |
| Remote reply sai request ID | Outbound gateway | Reject mismatch |
| Remote commit rồi timeout | Gateway + business policy | Reconcile/cùng idempotency key |
| Broker crash sau DB commit | Inbound adapter + handler | Redelivery không double write |
| DLT unavailable | Adapter/container recovery | Không drop nguồn |
| Multiple child replies | Splitter/Aggregator + Gateway | Parent correlation/member identity |
| Auth header giả mạo | Ingress + business handler | Reject tenant/operation |
| External URL do client truyền | Outbound adapter/gateway | Allowlist/SSRF prevention |

Mục tiêu không phải tạo thật nhiều tests không cần thiết, mà là **mỗi loại boundary có một contract observable**: đúng phía caller, đúng reply semantics, đúng transport failure behavior và đúng business effect.

## 50. Metrics: đo nhận/gửi message khác business completion

Những tên metric sau là **gợi ý ở tầng ứng dụng**, không phải toàn bộ metrics mặc định của Spring Integration:

| Metric | Lý do theo dõi |
|---|---|
| `inbound.adapter.received.count` | Số messages từ source được đưa vào flow |
| `inbound.adapter.source.read.failure.count` | Lỗi đọc file/broker source |
| `inbound.adapter.ack.failure.count` | Source ack/offset commit lỗi |
| `outbound.adapter.send.attempt.count` | Số lần gửi ra remote sink |
| `outbound.adapter.send.failure.count` | Lỗi gửi transport |
| `gateway.request.count` | Số logical calls cần reply |
| `gateway.reply.success.count` | Nhận valid reply |
| `gateway.reply.timeout.count` | Không nhận reply đúng hạn |
| `gateway.reply.late.count` | Reply đến sau deadline |
| `gateway.correlation.mismatch.count` | Reply sai request |
| `service.activator.invocation.count` | Số lần handler thực thi |
| `service.activator.business.commit.count` | Số successful durable effects |
| `service.activator.duplicate.suppressed.count` | Duplicate đã chặn |
| `error.channel.messages.count` | Errors được đưa vào error recovery |
| `quarantine.pending.count` | Terminal rejects chưa được giải quyết |
| `integration.flow.duration` | End-to-end latency theo flow |

Không đồng nhất `adapter.received.count` với `service.activator.business.commit.count`. Một event có thể bị Filter bỏ qua hợp lệ, được retry, lỗi vĩnh viễn, hoặc đang nằm trong async queue.

Metric labels cần giới hạn cardinality (flowName, endpointName, operation, outcome, reasonCode). Không đặt payload raw, email, commandId hay message ID thành metric labels; các IDs chỉ dùng trong structured logs/traces có phân quyền.

## 51. Quan sát một message đi qua cả ba thành phần

Ví dụ structured log:

~~~text
eventId=EV-701
sourceAdapter=kafka-orders-inbound
sourceTopic=orders.events
sourcePartition=2
sourceOffset=71
flowName=order-intake
handler=OrderCommandService.place
businessCommandId=C-701
transactionOutcome=COMMITTED
outboundAdapter=order-completion-publisher
publishOutcome=ACKNOWLEDGED
~~~

Với Gateway outbound:

~~~text
businessCommandId=C-701
gatewayName=inventory-reservation-http
transportAttempt=2
remoteRequestId=INV-701
replyOutcome=TIMEOUT
businessOutcome=UNKNOWN
reconciliationStatus=PENDING
~~~

**Không kết luận `businessOutcome=FAILED` chỉ vì `replyOutcome=TIMEOUT`.** Một remote service có thể đã commit trước khi response bị mất.

Nếu cùng message được đọc lại sau crash, log event ID, source position và duplicate outcome riêng; đừng chỉ đếm handler executions rồi suy ra số đơn hàng đã tạo.

## 52. Checklist chọn đúng thành phần khi thiết kế flow

Trước khi viết Spring Integration config, hãy xác nhận:

- Nguồn message đến từ **external system** hay từ **application Java method**?
- Hướng là inbound hay outbound **tương đối với integration application**?
- Có bắt buộc trả **business reply** cho caller không?
- Result cần trả ngay hay chỉ có durable `ACCEPTED/PENDING`?
- Đang nối transport, gọi business method hay đổi payload?
- Input là event có thể bỏ qua, hay command có side effect bắt buộc phản hồi?
- Thời gian tối đa được chờ và trách nhiệm khi timeout?
- Retry có nguy cơ thực hiện side effect trùng không?
- Cần business command/event IDs, correlation và reply-to nào?
- Source ACK/commit offset ở mốc nào sau durable processing?
- Lỗi xảy ra trước message creation, trong handler hay ở async worker?
- Adapter/gateway có header mapping/TLS/auth/allowlist đủ không?
- Có DLT/quarantine và replay owner cho permanent failure?
- Có tests với transport thật/fake server và fault injection không?

**Quy tắc tóm tắt:** **One-way transport** → Channel Adapter; **cần request–reply transport** → Gateway; **message cần invoke application method** → Service Activator; **Java application muốn gọi flow bằng interface typed** → `@MessagingGateway`.

## 53. Runbook: hệ thống dùng sai Adapter/Gateway/Service Activator

Một nhóm báo “HTTP client nhận 202 nhưng không nhận được kết quả đặt hàng”:

1. **Xác định caller:** HTTP external client, Java application, Kafka producer hay cron job?
2. **Xác định expected contract:** chỉ cần transport ACK, cần business result ngay hay cần trạng thái sau?
3. **Xem endpoint:** đã dùng inbound/outbound Adapter hay Gateway? Service Activator có trả reply không?
4. **Xem channel topology:** Filter có discard, Router có chọn sai nhánh, Transformer có ném lỗi?
5. **Xem reply path:** `replyChannel`/return address có còn hợp lệ; có outputChannel cố định làm reply đi lạc?
6. **Xem sync/async boundary:** caller có hết timeout trước khi worker commit không?
7. **Xem error path:** exception lan về caller hay đã vào `ErrorMessage`/container recoverer?
8. **Xem business state:** DB/order/outbox/remote side effect đã commit chưa?
9. **Xem transport state:** Kafka offset/broker ACK/HTTP status có ý nghĩa gì trong contract?
10. **Xem retries:** commandId có giữ nguyên, remote idempotency có hoạt động?
11. **Xem correlation:** Gateway reply có khớp request; Aggregator có thiếu child member không?
12. **Khắc phục:** chọn đúng endpoint hoặc đổi API sang async status, bổ sung durable recovery.
13. **Hồi quy:** test timeout-after-commit, missing reply, duplicate delivery và wrong header mappings.

**Không đơn giản đổi một Channel Adapter thành Gateway mà không thay đổi toàn flow**. Khi có reply, phải thiết kế response DTO, routing, timeout, error handling, correlation và client contract.

## 54. Những hiểu lầm phổ biến

**“Adapter, Gateway và Service Activator đều là `.handle()` nên giống nhau.”** Không. Java DSL có syntax tương đồng, nhưng endpoint semantics khác.

**“Channel Adapter luôn asynchronous.”** Không. One-way không phải là thread model.

**“Outbound HTTP Adapter hoàn toàn không nhận HTTP status.”** Không; transport có thể trả status/exception, nhưng Adapter không phát business reply message theo pattern.

**“Gateway mặc định bảo đảm server đã commit.”** Không. Reply/HTTP ACK phải được hiểu theo remote contract.

**“Gateway timeout nghĩa là business operation thất bại.”** Không; outcome có thể chưa biết.

**“Inbound Gateway chỉ là Inbound Adapter đổi tên.”** Không. Gateway có request–reply contract.

**“Service Activator tự quản lý Kafka partitions và consumer group.”** Không. Đó là trách nhiệm container/adapter.

**“Có `@ServiceActivator` thì method được bảo đảm idempotent.”** Không. Cần transaction/inbox/constraints.

**“Service Activator trả DTO thì không cần Gateway cho HTTP.”** Không; external HTTP request/reply boundary vẫn cần gateway/controller tương ứng.

**“Một Gateway không cần Service Activator vì đã có business logic.”** Gateway là boundary; business service/handler vẫn cần được thực thi ở đâu đó.

**“Một `@MessagingGateway` Java interface là HTTP inbound gateway.”** Không. Đây là Java proxy gọi message flow.

**“Gateway ReplyChannel và Aggregator correlation ID giống nhau.”** Không. Return address và logical group ID khác ngữ nghĩa.

**“Filter discard tự tạo error reply cho Gateway.”** Không. Có nguy cơ timeout.

**“Global errorChannel nhận được mọi exception.”** Không. Phụ thuộc sync/async và lỗi xảy ra trước/sau message creation.

**“Publisher ACK nghĩa là consumer xử lý xong.”** Không. ACK broker và business completion khác nhau.

**“Tăng executor threads giữ nguyên ordering.”** Không; per-key completion có thể lệch.

**“Kafka offset làm idempotency ID bền vững qua mọi workflow.”** Không. Nó chỉ định source position trong một topic/partition.

**“Gửi HTTP POST retry với key mới sau timeout sẽ an toàn hơn.”** Ngược lại, có thể nhân đôi remote side effects.

**“`@Transactional` ở caller sẽ tự chạy qua ExecutorChannel.”** Không; transaction context thường gắn với thread.

**“Một Service Activator void trong Gateway request–reply sẽ tự trả OK.”** Không. Caller có thể không nhận reply.

## 55. Bài thực hành: thay đúng endpoint khi thay đổi yêu cầu reply

Xây mini project **ChannelBoundaryLab** với Spring Integration:

1. Tạo các DTO `FindOrderQuery`, `OrderView`, `ReserveStockCommand`, `ReservationResult` và `AuditEvent`.
2. Dùng `@InboundChannelAdapter` + poller nhận file JSON đơn hàng từ một thư mục test.
3. Thêm Filter/Transformer đổi file thành canonical command, reject malformed input có reasonCode.
4. Dùng Service Activator gọi một fake `OrderService.place()` với idempotency.
5. Dùng HTTP outbound channel adapter gửi `AuditEvent` tới fake server.
6. Cho fake server trả body `{"state":"PENDING"}` và chứng minh adapter **không phát một business reply** để application sử dụng.
7. Đổi sang HTTP outbound gateway khi flow phải đọc response body và tạo typed result.
8. Tạo HTTP inbound gateway nhận `FindOrderQuery` và trả `OrderView`.
9. Tạo Java `@MessagingGateway` cho một `CheckoutUseCase` để caller không tự tạo Spring Message.
10. Thử Service Activator trả `void` ở đường request–reply; phát hiện reply timeout.
11. Sửa bằng typed rejection/acceptance result và error mapper đúng.
12. Chèn `ExecutorChannel`, gây lỗi trong worker và kiểm tra error channel riêng.
13. Simulate remote HTTP timeout sau khi server đã commit; retry bằng cùng logical command ID.
14. Thêm durable inbox/outbox hoặc test fake store để bảo vệ duplicate delivery.
15. Tạo Splitter ba child tasks, Aggregator với distinct member IDs và parent correlation.
16. Cho một child bị reject; trả explicit failed outcome thay vì drop.
17. Kiểm tra broker ACK/offset không đồng nghĩa business completion.
18. Thêm metrics cho Adapter received, Gateway reply timeout, Activator commit và DLT pending.
19. Viết runbook khi external caller không nhận reply nhưng DB đã commit.
20. Thử thay file inbound bằng Kafka inbound adapter mà giữ business handler contract không đổi.

**Tiêu chí hoàn thành:** mỗi boundary được chọn đúng chiều và đúng reply semantics; business handler không phụ thuộc transport; error/retry/correlation rõ; không có duplicate side effects sau crash/retry; test chứng minh HTTP Adapter one-way khác Gateway request–reply, còn Service Activator là nơi invoke method.

## 56. Ghi nhớ

**Channel Adapter, Gateway và Service Activator không phải ba cách viết khác nhau của cùng một endpoint.** Chúng phối hợp ở **ba ranh giới**:

1. **Channel Adapter:** giao tiếp one-way giữa **external source/sink** và message channel; có chiều **inbound** hoặc **outbound**.
2. **Gateway:** chuyển đổi **request–reply**, quản lý return address/correlation/timeout; có inbound/outbound transport gateway và Java `@MessagingGateway` proxy cho application code.
3. **Service Activator:** đưa message tới **một application method** để xử lý và có thể tạo reply, nhưng không tự là external transport adapter/gateway.

Một flow thường kết hợp cả ba: **Kafka inbound Adapter → Filter/Router/Transformer → Service Activator → HTTP outbound Gateway → Outbound Adapter để phát completion event**. Không chọn loại endpoint dựa trên việc nó đều có thể được viết bằng `.handle()`.

**Khác biệt quan trọng nhất là hợp đồng:** ai gửi request, ai nhận reply, lúc nào business operation được coi là thành công và ai chịu trách nhiệm khi timeout/crash? Chọn endpoint đúng mới là bước đầu; để vận hành an toàn, vẫn cần **authorization, idempotency, transaction, error channel, retry/DLT, correlation và integration tests**.

### Tài liệu tham khảo

- Enterprise Integration Patterns, **Channel Adapter**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/ChannelAdapter.html
- Enterprise Integration Patterns, **Messaging Gateway**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Enterprise Integration Patterns, **Service Activator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingAdapter.html
- Spring Integration Reference, **Channel Adapter**: https://docs.spring.io/spring-integration/reference/channel-adapter.html
- Spring Integration Reference, **Messaging Gateways**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **Service Activator**: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Integration Reference, **HTTP Support**: https://docs.spring.io/spring-integration/reference/http.html
- Spring Integration Reference, **File Support**: https://docs.spring.io/spring-integration/reference/file.html
- Spring Integration Reference, **Kafka Support**: https://docs.spring.io/spring-integration/reference/kafka.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
