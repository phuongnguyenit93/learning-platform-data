# Đóng gói lời gọi từ xa thành message

## 1. Bài toán: code ứng dụng gọi một dịch vụ ở xa

Trong hệ thống thương mại điện tử, Checkout cần yêu cầu Inventory **giữ tồn kho** cho một đơn hàng. Nếu Checkout gọi trực tiếp một HTTP client, code nghiệp vụ có thể phải biết URL, headers, timeout, format request/response và cách xử lý retry:

~~~java
// Ví dụ cố tình gắn kết application code với transport.
StockReservationResult reserve(ReserveStockCommand command) {
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("Idempotency-Key", command.operationId());

    ResponseEntity<StockReservationHttpResponse> response =
        restTemplate.exchange(
            inventoryUrl + "/reservations",
            HttpMethod.POST,
            new HttpEntity<>(toHttpRequest(command), headers),
            StockReservationHttpResponse.class);

    return toDomainResult(response.getBody());
}
~~~

Vấn đề không phải HTTP client là xấu. Vấn đề là **business use case bị buộc phụ thuộc vào cách gọi từ xa**: endpoint nào, header nào, khi mất kết nối phải retry thế nào, trả lỗi ra sao. Nếu sau này Inventory chuyển sang broker request–reply, ta phải thay đổi nhiều lớp nếu không có boundary.

**Đóng gói lời gọi từ xa thành message** là dùng **message request**, một **request–reply contract** (khi cần kết quả), và các endpoint/adapter để che chi tiết gọi xa khỏi application code:

~~~mermaid
flowchart LR
    A["Checkout use case"] --> PORT["Inventory port / Gateway"]
    PORT --> REQ["Command message"]
    REQ --> OUT["Outbound gateway/adapter"]
    OUT --> REM["Remote Inventory service"]
    REM --> OUT
    OUT --> RESP["Reply message"]
    RESP --> PORT
    PORT --> A
~~~

Application gọi:

~~~java
StockReservationResult result = inventoryPort.reserve(command);
~~~

Ở bên trong, một integration flow có thể tạo message, route, transform, gửi đến remote service, nhận response, phân loại lỗi và trả về kiểu dữ liệu ứng dụng. **Gateway biến RPC-style call thành messaging boundary, không biến remote call thành local call thực sự.** Latency, availability, timeout, duplicate delivery và partial failures vẫn tồn tại.

Bài thuộc chương **Remote procedure invocation** của module **SPRING_INTEGRATION_PATTERN**. Module học triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và theo dõi các nhánh xử lý.

Sau bài, bạn sẽ thiết kế API gọi từ xa có kiểu, chuyển command thành request message, cấu hình Spring Integration Gateway + HTTP outbound gateway, giữ correlation qua transport, phân loại timeout/retry/error channel và kiểm thử để remote side effect không bị thực hiện trùng khi mạng lỗi.

## 2. Remote Procedure Invocation và Messaging là hai cách nhìn khác nhau

**Remote Procedure Invocation (RPI/RPC)** làm người gọi sử dụng một thao tác như gọi method:

~~~text
reserveStock(orderId, sku, quantity) → reservationResult
~~~

**Messaging** diễn đạt việc trao đổi bằng một message độc lập, có payload và metadata:

~~~text
Request message:
  operation = RESERVE_STOCK
  operationId = RES-901
  orderId = O-901
  sku = SKU-7
  quantity = 2

Reply message:
  operationId = RES-901
  status = RESERVED
  reservationId = RSV-555
~~~

Spring Integration cho phép đặt **một Gateway tại application boundary** để code gọi method nhưng phần tích hợp dùng messages và các endpoint.

**Điểm phải giữ trong tư duy:** một lời gọi remote có thể thất bại ở nhiều chỗ mà lời gọi local không có: request chưa gửi, đã gửi nhưng server chưa xử lý, server đã commit nhưng reply mất, reply đến muộn hoặc client timeout. Không thể suy ra kết quả remote chỉ từ một Java exception.

## 3. Lời gọi local và remote khác nhau ở những rủi ro nào?

| Khía cạnh | Method cùng process | Remote call |
|---|---|---|
| Thời gian | Thường rất thấp | Có network, queueing, service latency |
| Process failure | Thường trong cùng JVM/process | Caller và receiver hỏng độc lập |
| Transaction | Có thể cùng transaction manager | Thường khác transaction boundary |
| Return value | Nhận trực tiếp | Có thể mất reply dù server đã commit |
| Exception | Thường từ code đang chạy | Có transport, protocol, timeouts, remote errors |
| Identity | Object/method context | Cần serialized business IDs và correlation |
| Retry | Có thể gọi lại method | Có nguy cơ duplicate side effect |
| Security | Internal invocation context | Cần authentication, authorization, TLS, credentials |
| Versioning | Cùng binary/deployment có thể đồng bộ | Caller/receiver phát hành độc lập |

**Không tạo “distributed object” giả định remote endpoint luôn rẻ, nhanh và chắc chắn như method local.** API đẹp đến đâu cũng phải công bố timeout, failure classification và idempotency semantics.

## 4. Message hóa một lời gọi: từ method signature đến hợp đồng

Với thao tác giữ tồn kho, định nghĩa Java contract:

~~~java
record ReserveStockCommand(
    String tenantId,
    String operationId,
    String orderId,
    String sku,
    int quantity
) {}

record StockReservationResult(
    String operationId,
    String orderId,
    String reservationId,
    ReservationStatus status
) {}

enum ReservationStatus {
    RESERVED,
    REJECTED_OUT_OF_STOCK,
    PENDING
}
~~~

**Điểm thiết kế:**

- `operationId` nhận diện **một yêu cầu giữ tồn kho logical** qua retry/redelivery, không phải ID của một attempt HTTP.
- `tenantId` là thông tin business scope cần xác minh bằng identity đáng tin; không mặc nhiên tin client tự khai.
- `orderId`, `sku` và `quantity` mô tả thao tác.
- `ReservationStatus` thể hiện **kết quả nghiệp vụ**, khác HTTP status 200/409/503.
- `PENDING` chỉ hợp lệ khi backend đã nhận durable intent hoặc có status lookup/reconciliation, không phải nhãn để che network failure.

Nếu một đơn hàng có nhiều dòng cùng SKU, operation ID cần đủ scope để phân biệt **từng reservation member**. Ví dụ `tenant + orderId + operation + lineId` có thể là business key; không dùng một ID chung cho tất cả child khi receiver dedupe theo key.

## 5. Application port: method có kiểu nhưng không phụ thuộc HTTP

Một interface thuần Java:

~~~java
public interface InventoryReservationPort {
    StockReservationResult reserve(ReserveStockCommand command);
}
~~~

Checkout chỉ phụ thuộc port:

~~~java
@Service
class CheckoutUseCase {
    private final InventoryReservationPort inventory;

    CheckoutUseCase(InventoryReservationPort inventory) {
        this.inventory = inventory;
    }

    StockReservationResult reserveForOrder(
            ReserveStockCommand command) {
        validateUseCase(command);
        return inventory.reserve(command);
    }

    private void validateUseCase(ReserveStockCommand command) {
        // Validation & authorization theo contract ứng dụng.
    }
}
~~~

Khi dùng Spring Integration, ta có thể tạo **Gateway proxy** sau interface này hoặc để một adapter Java implement port rồi delegate cho Gateway. Nhờ vậy application code không cần biết `Message<?>`, `MessageChannel`, HTTP status hay broker record.

Đây là **Ports and Adapters**, không phải yêu cầu bắt buộc thêm nhiều interface trong mọi dự án. Lợi ích lớn nhất xuất hiện khi muốn thay transport/flow, unit test use case độc lập hoặc có nhiều callers dùng cùng business contract.

## 6. Messaging Gateway interface nhận DTO từ application code

Một Spring Integration Gateway:

~~~java
@MessagingGateway(
    defaultRequestChannel = "inventory.reserve.requests")
interface InventoryReservationGateway {
    StockReservationResult reserve(ReserveStockCommand command);
}
~~~

Có thể khai báo một adapter:

~~~java
@Component
class MessagingInventoryAdapter
        implements InventoryReservationPort {
    private final InventoryReservationGateway gateway;

    MessagingInventoryAdapter(InventoryReservationGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public StockReservationResult reserve(
            ReserveStockCommand command) {
        return gateway.reserve(command);
    }
}
~~~

Đăng ký cơ chế component scan/bean cho annotated gateway theo dự án, ví dụ:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class IntegrationConfiguration {
}
~~~

`@MessagingGateway` tạo **proxy chuyển lời gọi Java thành message gửi tới request channel**. Nó không tự gọi Inventory ở xa; flow phía sau phải có một endpoint/adapter thật. Spring Integration hỗ trợ nhiều cách đăng ký Gateway; kiểm tra phiên bản và component scanning cụ thể trong ứng dụng.

## 7. Những thành phần cần có cho một request–reply từ xa

~~~text
Application
  → Gateway interface
  → request channel
  → Validate/Transform internal command
  → HTTP outbound gateway (or broker request–reply)
  → Remote receiver
  ← response from receiver
  → Transform remote response into domain result
  → Gateway reply
  → Application
~~~

| Thành phần | Chức năng |
|---|---|
| **Gateway interface** | Boundary typed Java |
| **Request channel** | Đưa lời gọi vào integration flow |
| **Request Transformer** | Convert domain DTO → remote/wire DTO |
| **Outbound gateway** | Thực hiện call remote và nhận response |
| **Reply Transformer** | Convert response → application result |
| **Reply channel/address** | Trả kết quả đúng lời gọi đang chờ |
| **Error handler** | Phân loại lỗi input/transport/remote/business |
| **Correlation + idempotency IDs** | Gắn reply đúng request; chống side effect trùng |

**Gateway và Message Translator không trùng vai trò.** Gateway giúp caller gọi flow dưới dạng method, còn Translator/Transformer quyết định kiểu dữ liệu và semantics của payload. Outbound gateway chịu trách nhiệm transport request–reply.

## 8. Internal DTO khác wire DTO của remote API

Một remote Inventory API có thể nhận JSON:

~~~json
{
  "requestId": "RES-901",
  "orderRef": "O-901",
  "productCode": "SKU-7",
  "units": 2
}
~~~

và trả:

~~~json
{
  "requestId": "RES-901",
  "orderRef": "O-901",
  "result": "RESERVED",
  "reservationRef": "RSV-555"
}
~~~

Không bắt `CheckoutUseCase` dùng trực tiếp `productCode`, `units` hay `reservationRef` nếu domain đã thống nhất `sku`, `quantity` và `reservationId`. Tạo DTO ở integration adapter:

~~~java
record StockReservationHttpRequest(
    String requestId,
    String orderRef,
    String productCode,
    int units
) {}

record StockReservationHttpResponse(
    String requestId,
    String orderRef,
    String result,
    String reservationRef
) {}
~~~

**Wire DTO là contract với dịch vụ ở xa**, có thể thay độc lập domain DTO. Transformer phải validate field required, enum, numeric range, conversion và response correlation; không chỉ cast JSON thành object rồi trả thẳng.

## 9. Request Transformer: đóng gói lời gọi thành wire payload

Một mapper thuần:

~~~java
@Component
class ReservationRequestMapper {

    StockReservationHttpRequest toHttpRequest(
            ReserveStockCommand command) {
        if (command == null
                || command.operationId() == null
                || command.operationId().isBlank()
                || command.orderId() == null
                || command.orderId().isBlank()
                || command.sku() == null
                || command.sku().isBlank()
                || command.quantity() <= 0) {
            throw new InvalidReservationCommandException(
                "INVALID_RESERVATION_COMMAND");
        }

        return new StockReservationHttpRequest(
            command.operationId(),
            command.orderId(),
            command.sku(),
            command.quantity());
    }
}
~~~

`InvalidReservationCommandException` là một exception ứng dụng do ta định nghĩa; không phải Spring Integration class mặc định. Mapper này **không gọi HTTP, không ghi DB và không tạo side effect**. Nhờ vậy retry/validation có thể chạy lại nó mà không gây thay đổi nghiệp vụ.

Trong thực tế còn phải validate `tenantId` với trusted principal, giới hạn payload size, đảm bảo uniqueness của operation ID và canonical fingerprint khi cùng key được gửi với nội dung khác.

## 10. Header contract: metadata nào đi cùng request?

Một message Spring có payload và headers:

~~~text
payload = StockReservationHttpRequest
headers:
  operationId = RES-901
  businessCorrelationId = tenant-a|O-901|inventory
  verifiedTenantId = tenant-a
  traceparent = <trace context>
  replyChannel = <temporary return address>
~~~

Các nhóm metadata khác nhau:

- **Business IDs:** `operationId`, `orderId`, correlation key; cần ổn định qua retry.
- **Trust/security context:** tenant đã xác minh, credential/tracing; có nguồn gốc và lifetime rõ.
- **Transport headers:** HTTP `Content-Type`, `Idempotency-Key`, reply-to/Correlation ID khi broker yêu cầu.
- **Framework headers:** Spring `replyChannel`, `errorChannel` và `MessageHeaders.ID`; không mặc nhiên gửi nguyên ra bên ngoài.

Không sao chép **mọi HTTP header từ client** thành Spring headers rồi để Router/Gateway dùng tùy ý. Chỉ mang những trường được whitelist, đã validate và hợp lý theo contract.

## 11. Idempotency-Key không phải là correlationId

Một request cần ít nhất hai loại nhận diện khi remote operation có side effect:

~~~text
operationId = RES-901
    → remote idempotency key để xử lý lại một logical reservation.

requestCorrelationId = INVOKE-ATTEMPT-3
    → gắn một request transport/attempt với reply tương ứng.
~~~

Một retry có thể dùng **request correlation khác** nhưng phải giữ **same operationId**. Nếu receiver nhận cùng idempotency key + cùng canonical payload, nó có thể trả **cached result** hoặc trạng thái đang xử lý, không tạo reservation thứ hai.

Nếu same key nhưng payload khác:

~~~text
RES-901, sku=SKU-7, quantity=2
RES-901, sku=SKU-7, quantity=200
~~~

receiver phải có **fingerprint conflict policy**; không âm thầm dùng kết quả cũ hay tạo một reservation mới. Transport correlation giúp nối đúng reply, không thay thế kiểm soát idempotency của business operation.

## 12. Synchronous Gateway giúp gọi remote, nhưng không làm remote thành local

Trong flow đồng bộ:

~~~mermaid
sequenceDiagram
    participant App as Checkout
    participant G as Messaging Gateway
    participant Flow as IntegrationFlow
    participant Rem as Remote Inventory
    App->>G: reserve(RES-901)
    G->>Flow: ReserveStockCommand message
    Flow->>Flow: Validate + toHttpRequest
    Flow->>Rem: HTTP POST /reservations
    Rem-->>Flow: RESERVED / RSV-555
    Flow->>Flow: toDomainResult
    Flow-->>G: StockReservationResult
    G-->>App: RESERVED
~~~

Ở caller, syntax có vẻ đơn giản:

~~~java
StockReservationResult result = gateway.reserve(command);
~~~

Nhưng method có thể:

- Block trong network.
- Timeout ở request/send/reply.
- Nhận 4xx/5xx hoặc remote business rejection.
- Không nhận reply dù receiver đã commit.
- Bị fail bởi circuit breaker hoặc quota.

**Thiết kế API phải nói rõ độ trễ, exception, retry semantics và possible unknown outcome.** Không truyền `null` như một kết quả “không chắc” nếu caller đang chờ một result có nghĩa.

## 13. HTTP outbound gateway: adapter request–reply của Spring Integration

Spring Integration có HTTP outbound gateway để đưa một message từ flow thành HTTP request và nhận HTTP response như reply. Hình thức Java DSL minh họa:

~~~java
@Bean
IntegrationFlow inventoryHttpFlow() {
    return IntegrationFlow
        .from("inventory.http.requests")
        .handle(
            Http.outboundGateway(
                    "https://inventory.internal.example/reservations")
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(
                    StockReservationHttpResponse.class))
        .channel("inventory.http.replies")
        .get();
}
~~~

Đây là **cấu trúc minh họa**, không phải một ứng dụng hoàn chỉnh. Cần cấu hình HTTP client, serialization/conversion (JSON), timeout, authentication, TLS, header mapping và error handling theo phiên bản Spring Integration. Địa chỉ `inventory.internal.example` là placeholder, **không phải dịch vụ thật**.

**Quan trọng:** HTTP outbound gateway có contract request–reply; HTTP outbound channel adapter one-way có contract khác. Một HTTP POST trả 202 chỉ cho biết **request được chấp nhận theo remote API semantics**, không chứng minh Inventory đã giữ tồn kho xong nếu server xử lý async.

## 14. Ghép Gateway, Transformer và HTTP outbound gateway thành một flow

Một flow hoàn chỉnh ở mức khái niệm:

~~~mermaid
flowchart LR
    P["InventoryReservationPort"] --> G["@MessagingGateway"]
    G --> V["Validate command"]
    V --> T1["Request Transformer"]
    T1 --> H["HTTP outbound gateway"]
    H --> R["Remote Inventory API"]
    R --> H
    H --> T2["Reply Transformer"]
    T2 --> G
~~~

Java DSL cho **đường thành công**:

~~~java
@Configuration
@EnableIntegration
class InventoryRemoteFlowConfiguration {

    @Bean
    IntegrationFlow reserveRemoteInventory(
            ReservationRequestMapper requestMapper,
            ReservationReplyMapper replyMapper) {
        return IntegrationFlow
            .from("inventory.reserve.requests")
            .transform(
                ReserveStockCommand.class,
                requestMapper::toHttpRequest)
            .handle(
                Http.outboundGateway(
                        "https://inventory.internal.example/reservations")
                    .httpMethod(HttpMethod.POST)
                    .expectedResponseType(
                        StockReservationHttpResponse.class))
            .transform(
                StockReservationHttpResponse.class,
                replyMapper::toResult)
            .get();
    }
}
~~~

`ReservationReplyMapper` là service của ứng dụng, sẽ được minh họa ở mục 15. Flow làm ba việc: **chuyển domain command sang remote DTO → gửi request/nhận response → chuyển reply thành domain result**.

Để chạy production, cần bổ sung **REST client và JSON converter tương thích, authentication, HTTP timeout, mapping idempotency header, status/error mapping, rate limit, circuit breaker và tracing**. Ví dụ không khai báo chúng để tách bạch mạch EIP khỏi chi tiết cấu hình version/adapter.

**Không đăng ký đồng thời flow này và flow ở mục 13 cùng tiêu thụ một input channel** nếu không chủ đích phân phối cạnh tranh. Mục 13 là outbound gateway riêng; mục 14 là cấu trúc ghép nó vào flow end-to-end.

## 15. Reply Transformer không được xem mọi HTTP 2xx là thành công nghiệp vụ

Một response:

~~~json
{
  "requestId": "RES-901",
  "result": "REJECTED_OUT_OF_STOCK",
  "reservationRef": null
}
~~~

HTTP 200 ở đây có thể mang một **business rejection hợp lệ**. Ngược lại, response HTTP 202 có thể chỉ biểu thị **PENDING**.

Mapper:

~~~java
@Component
class ReservationReplyMapper {

    StockReservationResult toResult(
            StockReservationHttpResponse reply) {
        if (reply == null
                || reply.requestId() == null
                || reply.requestId().isBlank()
                || reply.orderRef() == null
                || reply.orderRef().isBlank()
                || reply.result() == null) {
            throw new RemoteProtocolException(
                "INVALID_REMOTE_RESPONSE");
        }

        ReservationStatus status;
        try {
            status = ReservationStatus.valueOf(reply.result());
        } catch (IllegalArgumentException invalidStatus) {
            throw new RemoteProtocolException(
                "UNKNOWN_REMOTE_STATUS");
        }

        if (status == ReservationStatus.RESERVED
                && (reply.reservationRef() == null
                    || reply.reservationRef().isBlank())) {
            throw new RemoteProtocolException(
                "MISSING_RESERVATION_ID");
        }

        return new StockReservationResult(
            reply.requestId(),
            reply.orderRef(),
            reply.reservationRef(),
            status);
    }
}
~~~

`RemoteProtocolException` là exception ứng dụng, không có sẵn trong Spring Integration. Ví dụ remote reply có `orderRef` để dựng domain result đầy đủ; nếu API thực không echo `orderRef`, phải lấy thông tin ấy từ request context đáng tin, không được tự đoán.

**Trong triển khai thực:** giữ `orderId`/`operationId` từ request trong một message envelope/header đã xác minh hoặc yêu cầu remote echo các trường cần thiết, rồi **kiểm tra response.requestId khớp operationId của request**. Nếu không khớp, đó là **correlation/protocol failure**, không trả dữ liệu của request khác.

## 16. Giữ request context để tạo reply domain hoàn chỉnh

Một kiểu application context:

~~~java
record ReservationCallContext(
    String tenantId,
    String operationId,
    String orderId
) {}
~~~

Có thể giữ `ReservationCallContext` trong internal headers ở phần trước outbound gateway, hoặc lưu một correlation state theo request ID nếu request–reply vượt broker/process boundary.

Một mapper kiểm tra correlation:

~~~java
StockReservationResult mapCheckedReply(
        StockReservationHttpResponse reply,
        ReservationCallContext expected) {
    if (reply == null || expected == null
            || !expected.operationId().equals(reply.requestId())
            || !expected.orderId().equals(reply.orderRef())) {
        throw new RemoteProtocolException(
            "REMOTE_CORRELATION_MISMATCH");
    }

    ReservationStatus status;
    try {
        status = ReservationStatus.valueOf(reply.result());
    } catch (RuntimeException invalidStatus) {
        throw new RemoteProtocolException(
            "UNKNOWN_REMOTE_STATUS");
    }
    if (status == ReservationStatus.RESERVED
            && (reply.reservationRef() == null
                || reply.reservationRef().isBlank())) {
        throw new RemoteProtocolException(
            "MISSING_RESERVATION_ID");
    }

    return new StockReservationResult(
        expected.operationId(),
        expected.orderId(),
        reply.reservationRef(),
        status);
}
~~~

Đây là helper minh họa **quy tắc correlation**. Khi dùng Spring Integration, bạn phải chọn chỗ gắn/persist context phù hợp; một local header có thể không tồn tại sau khi message vượt external transport hoặc được adapter xây lại. Với one-way fire-and-forget, không có reply nên không dùng cùng mapping.

Không tự lấy `orderId` từ field remote khác rồi tin tuyệt đối, vì response có thể bị lệch request, server trả nhầm hoặc bị thay đổi qua một intermediary.

## 17. Ánh xạ Idempotency-Key từ business operation

Remote Inventory API nên hỗ trợ một key ổn định:

~~~http
POST /reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: RES-901

{"requestId":"RES-901","orderRef":"O-901","productCode":"SKU-7","units":2}
~~~

**Không có tiêu chuẩn HTTP chung buộc mọi service phải hiểu `Idempotency-Key`**. Đây là một giao ước với remote API: key scope, retention, response replay, concurrent requests và conflict behavior phải được tài liệu hóa.

Một ý tưởng enrich header **trước khi transform payload**:

~~~java
.enrichHeaders(h -> h.headerFunction(
    "remoteIdempotencyKey",
    m -> ((ReserveStockCommand) m.getPayload()).operationId()))
.transform(
    ReserveStockCommand.class,
    requestMapper::toHttpRequest)
~~~

Đây là fragment Java DSL, không phải flow độc lập. Sau đó HTTP outbound gateway cần **mapper thích hợp** để chuyển internal header `remoteIdempotencyKey` thành wire header `Idempotency-Key`. Không giả định mọi custom Spring header được HTTP outbound adapter forward tự động.

**Luôn giữ key khi retry cùng logical operation.** Nếu gửi lại với key mới sau timeout, remote service có thể tạo reservation thứ hai. Cũng không nên dùng một key chung cho các line items độc lập.

## 18. Bảng phân loại kết quả của một lời gọi từ xa

| Quan sát tại caller | Điều thực sự biết | Hành động có thể phù hợp |
|---|---|---|
| HTTP 200 + `RESERVED` hợp lệ | Remote báo thành công | Kiểm tra correlation, lưu outcome |
| HTTP 200 + `REJECTED_OUT_OF_STOCK` | Business rejection terminal | Không retry cùng input chỉ vì là rejection |
| HTTP 202 + accepted reference | Remote đã tiếp nhận theo contract | Theo dõi pending/status |
| HTTP 400/422 | Remote coi input invalid | Validate, báo caller, không retry nóng |
| HTTP 401/403 | Authn/authz không được chấp nhận | Sửa credentials/permissions, audit |
| HTTP 409 | Có thể conflict hoặc duplicate tùy remote API | Kiểm tra documented reason |
| HTTP 429 | Rate limit | Retry theo budget/Retry-After khi hợp lệ |
| HTTP 500/503 | Remote gặp lỗi | Retry bounded nếu operation idempotent |
| Connect refused trước khi gửi | Có khả năng server chưa thấy request | Có thể retry nhưng cần classifier đúng |
| Read timeout sau khi gửi | **Outcome chưa biết** | Dùng same key, status lookup/reconciliation |
| Reply body sai schema | Remote protocol incompatibility | Alert/quarantine, không giả success |
| Correlation mismatch | Reply không khớp request | Reject/safe recovery; không đưa sang caller khác |

**Không map mọi non-2xx về `ReservationStatus.REJECTED_OUT_OF_STOCK`.** Lỗi permission, lỗi mạng, contract mismatch và business insufficient-stock khác nhau về owner, retry và trách nhiệm phục hồi.

HTTP status không phải business truth độc lập; hãy tuân theo **contract cụ thể của remote API**. Ví dụ HTTP 409 có thể là idempotency conflict, not-found trong một workflow hoặc trạng thái đang xử lý; không phỏng đoán chỉ từ status.

## 19. Timeout không chứng minh remote operation đã rollback

Một failure window kinh điển:

~~~mermaid
sequenceDiagram
    participant C as Checkout/Gateway
    participant N as Network
    participant I as Remote Inventory
    C->>N: POST reserve(RES-901)
    N->>I: Request delivered
    I->>I: COMMIT reservation RSV-555
    I--xC: Reply lost / read timeout
    Note over C: UNKNOWN_OUTCOME
    C->>I: GET status by RES-901
    I-->>C: RESERVED, RSV-555
~~~

Gateway timeout chỉ nói rằng **caller không nhận reply trong thời hạn**, không nói rằng remote chưa xử lý. Nếu Checkout lập tức POST lại với **operationId mới**, có nguy cơ giữ stock hai lần.

Hướng xử lý:

1. Giữ original `operationId`.
2. Nếu remote hỗ trợ idempotency, retry theo API contract bằng **same key**.
3. Nếu không chắc response, thử **status lookup theo operationId** khi có.
4. Lưu một state `UNKNOWN_OUTCOME/PENDING_RECONCILIATION` bền vững.
5. Không phát `RESERVED` hay `REJECTED` chắc chắn chỉ từ timeout.

**Cấm tư duy “timeout = failure nên có thể gọi lại như mới”.** Điều này đặc biệt nguy hiểm với thanh toán, hoàn tiền, huỷ tài nguyên hoặc gửi thông báo.

## 20. Send timeout, remote timeout và reply timeout phải được phân biệt

Một flow có nhiều mốc:

~~~text
T0 Application gọi Gateway.reserve()
T1 Gateway gửi Message vào request channel
T2 Worker bắt đầu xử lý
T3 HTTP client connect/send
T4 Remote handler ghi reservation
T5 HTTP response được đọc
T6 Reply Transformer trả domain result
T7 Gateway nhận reply
~~~

Các timeout:

- **Request-channel/send timeout**: không đưa request vào channel được trong giới hạn cấu hình.
- **Connection timeout**: chưa thiết lập được kết nối tới remote.
- **Read/response timeout**: remote không trả response kịp, outcome có thể không rõ.
- **Reply timeout của Gateway**: caller chờ kết quả qua message flow quá lâu.
- **Business deadline**: caller/domain không còn chấp nhận kết quả sau thời điểm xác định.

Một `DirectChannel` đồng bộ có thể chặn trong handler dù cấu hình request-channel send timeout; deadline của nó không mặc nhiên giới hạn toàn bộ execution. Khi dùng `ExecutorChannel`, broker hoặc gateway request–reply, hành vi timeout phải được **kiểm thử theo topology và Spring Integration version**.

**Tránh cộng dồn timeout vô thức:** HTTP connect+read, retry attempts và queue time có thể vượt Gateway reply timeout rất xa, tạo hàng loạt late responses và pending operations.

## 21. Lập deadline end-to-end và retry budget

Giả sử:

~~~text
Business deadline  = 8 seconds
Gateway reply wait = 3 seconds
Remote call budget = 2 seconds / attempt
Retry budget       = at most 2 attempts
Backoff            = bounded with jitter
~~~

Một thiết kế:

- Caller nhận **PENDING/UNKNOWN_OUTCOME** nếu request đã được durable accepted mà chưa hoàn tất.
- Worker chỉ retry khi còn deadline, còn budget và operation idempotent.
- Sau khi hết budget, lưu failure/unknown state và chuyển recovery path.
- Remote call mang deadline/cancellation hint nếu remote contract hỗ trợ.
- Không cho late reply tạo result thứ hai hoặc side effect mới.

Đừng tuyên bố một timeout tự hủy mọi request downstream. Network packet có thể đã đến và remote commit đã xảy ra. Cancellation là **một protocol riêng**, không phải hậu quả chắc chắn của Java thread interrupt hoặc caller timeout.

## 22. Gateway đồng bộ và broker request–reply không có cùng đặc tính

**HTTP outbound gateway**:

~~~text
Message → HTTP POST → HTTP response → Message reply
~~~

**Broker request–reply**:

~~~text
Gateway
  → request topic/queue
  → remote consumer
  → reply topic/queue
  → correlation to pending request
  → Gateway
~~~

Với broker cần thêm:

- Request destination và reply destination/reply-to.
- Correlation ID cho từng in-flight invocation.
- Reply listener/container chạy và có quyền đọc.
- TTL/expiry, pending-reply registry hoặc durable tracking.
- Consumer ACK/DLQ semantics độc lập với reply.
- Handling late reply khi caller đã timeout.
- Idempotency ở receiver vì broker thường hỗ trợ redelivery.

**Một broker ACK không phải domain response.** Nó có thể chỉ xác nhận transport đã nhận/consume message. Nếu business operation cần xác nhận, phải có **reply message hoặc status event** mang kết quả.

## 23. Request–reply correlation qua broker

Một request:

~~~text
headers:
  transportCorrelationId = rpc-try-0042
  replyTo = inventory.replies.client-a
payload:
  operationId = RES-901
  orderId = O-901
  quantity = 2
~~~

Một reply:

~~~text
headers:
  transportCorrelationId = rpc-try-0042
payload:
  operationId = RES-901
  result = RESERVED
  reservationId = RSV-555
~~~

Trước khi trả kết quả:

1. Tìm pending request theo **transport correlation**.
2. Kiểm tra reply type/schema có hợp lệ không.
3. Đối chiếu **business operationId** với request context.
4. Đảm bảo reply đúng tenant/authorized client.
5. Deduplicate hoặc bỏ qua reply trễ/đến lặp theo policy.
6. Chỉ hoàn tất **đúng một** caller invocation.

Không dùng chỉ `sku` hoặc `orderId` làm return correlation key khi nhiều requests concurrent; hai attempts cùng orderId có thể trả khác kết quả. Và không dùng temporary Spring `replyChannel` JVM object làm wire header bắt buộc cho một receiver ở process khác.

## 24. Reply đến muộn hoặc đến hai lần

Timeline:

~~~text
T0 Caller A gửi rpc-try-0042, operation RES-901.
T1 Remote giữ stock xong, reply được publish.
T2 Caller A hết reply timeout, pending request hết hạn.
T3 Reply của rpc-try-0042 mới đến.
T4 Caller A retry RES-901 bằng rpc-try-0043.
T5 Reply của rpc-try-0043 đến.
~~~

Recovery đúng:

- Reply trễ không được trả cho **một caller khác** chỉ vì cùng orderId.
- Reply trễ không được kích hoạt lệnh giữ stock lần nữa.
- Business result theo `RES-901` có thể được lưu/cập nhật cho status lookup.
- Duplicate replies không tạo hai completion events.
- Pending-reply mappings có TTL/cleanup để tránh memory leak.
- Với request đã timeout nhưng remote commit, caller nhận **unknown/pending** chứ không tự kết luận failed.

Một workflow async với durable status thường dễ vận hành hơn RPC-style blocking khi remote service latency dài hoặc fan-out nhiều nhánh.

## 25. Error channel và remote exception mapping

Spring Integration có thể xuất hiện:

~~~text
Remote 503
  → HTTP outbound gateway raises exception
  → MessagingException / MessageHandlingException wrapper
  → caller exception (synchronous DirectChannel)

Hoặc:

Remote 503
  → asynchronous worker / poller
  → ErrorMessage(Throwable)
  → errorChannel / recoverer
~~~

Đường xử lý tùy **sync vs async boundary** và cấu hình endpoint/adapter. Không khẳng định mọi lỗi mặc nhiên vào global `errorChannel`; một lỗi JSON deserialization có thể xảy ra tại converter hoặc container trước khi Spring Message được phát.

Application nên phân loại các lỗi thành:

~~~java
enum RemoteFailureKind {
    INVALID_REQUEST,
    UNAUTHORIZED,
    BUSINESS_REJECTED,
    RATE_LIMITED,
    TEMPORARILY_UNAVAILABLE,
    UNKNOWN_OUTCOME,
    PROTOCOL_MISMATCH,
    INTERNAL_CLIENT_ERROR
}
~~~

Đừng biến exception raw thành domain `REJECTED_OUT_OF_STOCK` nếu remote chưa trả một business result đáng tin. Giữ `reasonCode`, remote operation, endpoint alias và correlation; tránh trả raw HTTP body/token/stack trace ra public API.

## 26. Recovery boundary phải phân biệt permanent và transient

| Failure | Có sửa bằng retry cùng payload không? | Recovery |
|---|---|---|
| Local invalid quantity | Không | Reject trước remote call |
| Remote HTTP 400/schema invalid | Không khi contract không đổi | Báo caller/correct producer |
| Authentication/authorization fail | Không bằng retry nóng | Fix credential/quyền, audit |
| Remote 503 | Có thể | Retry bounded + backoff/circuit breaker |
| HTTP 429 | Có thể | Respect retry hints + quota |
| Remote 409 duplicate key | Theo API | Query existing result/conflict |
| Read timeout | **Không biết operation outcome** | Reconcile/same idempotency key |
| Response correlation mismatch | Không phải retry thường | Protocol alert/quarantine |
| Deserializer failure | Không nếu response schema sai | Contract compatibility fix |
| Worker process crash | Có thể redelivery | Durable inbox/idempotency |

**Không retry mọi exception bằng một chính sách duy nhất.** Ngay cả HTTP 503 khi remote request có side effect cũng cần idempotency key và logic xử lý outcome unknown nếu request đã tới server.

Một circuit breaker có thể **ngăn gửi thêm request** khi downstream đang quá tải, nhưng không tự hoàn tác những request đã gửi hoặc đảm bảo success. Khi circuit open, caller nhận failure/pending theo application contract.

## 27. RetryAdvice và retry tại HTTP/broker không được nhân attempts vô hạn

Các tầng có thể cùng retry:

~~~text
Application retry:       3 attempts
Spring handler advice:   3 attempts
HTTP client retry:       2 attempts
Broker redelivery:       5 attempts

Worst-case potential: 3 × 3 × 2 × 5 = 90 remote requests
~~~

Đây là **ước lượng khuếch đại tối đa trong ví dụ** khi các tầng thực sự lồng nhau, không phải hành vi mặc định của Spring Integration. Nó cho thấy vì sao cần **một retry budget end-to-end**, không chỉ cấu hình từng thư viện độc lập.

Hướng xử lý:

- Chọn tầng chịu trách nhiệm retry cho loại lỗi cụ thể.
- Dùng deadline, max attempts và backoff có jitter.
- Phân biệt request chưa gửi với read timeout sau khi gửi.
- Giữ cùng business operation ID cho mọi attempts.
- Dùng circuit breaker/rate limit để bảo vệ remote service.
- Sau exhaustion, đưa vào durable recovery/status, không báo success giả.

**RequestHandlerRetryAdvice** chỉ bao quanh handler được gắn advice. Nếu một message chuyển sang `ExecutorChannel` rồi handler sau đó lỗi, retry advice gắn ở endpoint phía trước không tự bao trùm worker phía sau.

## 28. Transaction boundary: local database không kiểm soát remote side effect

Một flow nguy hiểm:

~~~text
BEGIN local transaction
  INSERT order
  HTTP POST /inventory/reservations (remote COMMIT)
  UPDATE local order with reservation ID
COMMIT
~~~

Nếu remote đã giữ stock nhưng local DB rollback, hệ thống có một **reservation ở remote không tương ứng với local state**. Rollback JDBC không tự gửi cancellation về Inventory.

Những lựa chọn kiến trúc:

1. **Synchronous remote call** với stable idempotency key + reconcile + failure state; phù hợp khi latency nhỏ và remote protocol đủ mạnh.
2. **Transactional Outbox:** local transaction lưu order intent và outbox command; publisher gửi remote asynchronously.
3. **Saga/process manager:** lưu trạng thái các bước, retry, compensate nếu domain cho phép.
4. **Reservation with expiry:** Inventory giữ stock có TTL; workflow có thể release/cancel nếu order không hoàn tất.

**Outbox không tạo transaction phân tán giữa hai DB/services**; nó làm intent được lưu bền tại sender và cho phép retry. Receiver vẫn cần inbox/idempotency để xử lý delivery trùng.

## 29. Receiver cũng cần hiểu request message như một command

Một remote service có thể nhận HTTP rồi xử lý:

~~~text
HTTP inbound gateway/controller
  → Deserialize + authenticate
  → Validate schema/operationId/tenant
  → Convert wire DTO to ReserveStockCommand
  → Service Activator: reserve()
  → Database transaction + inbox
  → Reservation result
  → Serialize HTTP reply
~~~

Ở sender, request được đóng gói thành message. Ở receiver, quá trình đối xứng biến message thành **một lời gọi vào service nội bộ**. Đây là nơi EIP **Service Activator** kết nối messaging với domain logic.

Một receiver có thể dùng:

- HTTP controller + Spring Integration inbound channel/Gateway; hoặc
- Spring Integration HTTP inbound gateway trực tiếp; hoặc
- Kafka/AMQP inbound adapter và reply publisher.

**Không để HTTP deserializer tự gọi repository trước validation.** Ingress phải chặn raw malformed bytes, unsupported schema và unauthenticated requests trước side effects. Nếu request đã đi tới transactional handler, receiver vẫn cần kiểm tra business rule và quyền tenant.

## 30. Receiver idempotency: ACK/HTTP reply không thay durable dedupe

Một service nhận `RES-901` lần đầu và lại lần nữa sau client timeout:

~~~text
First request:
  operationId=RES-901 → reserve stock → COMMIT RSV-555

Retry:
  operationId=RES-901 → load committed result RSV-555
  (không giảm tồn kho thêm lần nữa)
~~~

Một thiết kế dữ liệu:

~~~sql
CREATE TABLE processed_reservation (
    tenant_id VARCHAR(80) NOT NULL,
    operation_id VARCHAR(100) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    state VARCHAR(24) NOT NULL,
    reservation_id VARCHAR(100),
    result_json TEXT,
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

**Đây là bảng ví dụ**, chưa bao gồm transaction logic, indexes phụ, retention, state transitions hoặc migration. Khi nhận request:

1. Validate/authorize tenant và command trước side effect.
2. Claim `(tenantId, operationId)` với **unique constraint**.
3. So fingerprint chuẩn của command với record đã có.
4. Nếu kết quả đã COMMITTED và fingerprint giống, trả cached result.
5. Nếu đang PROCESSING, trả pending/conflict theo contract thay vì chạy song song mù.
6. Nếu same key but different payload, trả idempotency conflict.
7. Nếu lần đầu, ghi reservation và trạng thái hoàn tất **trong một transaction local**.

Một `ConcurrentHashMap` trong process không đủ vì nó mất khi restart, không chia sẻ giữa replicas và không atomic với database. “Đã nhận HTTP request” cũng chưa đủ bằng chứng stock đã được giữ thành công.

## 31. Sự cố giữa commit và reply: tại sao dedupe cần cached result?

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant R as Receiver
    participant DB as Receiver DB
    S->>R: Reserve RES-901
    R->>DB: INSERT operation + reserve stock
    DB-->>R: COMMIT RSV-555
    R--xS: Response lost
    S->>R: Retry RES-901 (same payload/key)
    R->>DB: Lookup committed operation
    DB-->>R: RSV-555
    R-->>S: RESERVED RSV-555
~~~

Nếu receiver chỉ ghi một `seen=true` marker rồi return null cho duplicate, sender có thể không biết remote result và Gateway tiếp tục timeout. Dedupe hữu ích hơn khi lưu **terminal outcome hoặc status reference**, để repeated invocation có thể được trả kết quả có nghĩa.

Nếu handler fail **sau marker insert nhưng trước business commit**, marker cần rollback hoặc state phải cho phép retry an toàn. Tách marker vào Redis không cùng transaction với inventory DB dễ tạo trạng thái **“seen nhưng chưa reserve”**.

**Không gắn idempotency semantics vào một HTTP header mà receiver không xử lý.** Header chỉ là yêu cầu của protocol; cơ chế bảo đảm nằm ở receiver transaction/state machine.

## 32. Cancellation và compensation là một lời gọi khác, không phải timeout

Khi Checkout không còn cần reservation:

~~~text
Reserve:
  operationId=RES-901 → reservationId=RSV-555

Cancel:
  operationId=CANCEL-901 → reservationId=RSV-555
~~~

Lệnh cancel phải có **operation identity** và quyền riêng. Không gửi lại `RES-901` với một header `"cancel": true` tùy tiện nếu remote contract không định nghĩa như vậy.

Nếu receiver đã capture payment hoặc giữ tài nguyên, “cancel” có thể là **compensating action**, không phải rollback nguyên tử. Cần biết domain có cho phép reverse hay không, cách xử lý cancel trùng, cancel tới trước reserve reply, và timeout của chính cancel operation.

Một số domain cần **reservation TTL** tự giải phóng nếu không xác nhận, nhưng TTL không thay việc lưu trạng thái để reconcile. Nếu hết hạn trước lúc order commit, business flow phải xử lý `RESERVATION_EXPIRED` rõ ràng.

## 33. Security của lời gọi xa: trust boundary thay đổi

Một Java Gateway interface ở application layer **không tự bảo mật** remote call. Khi request rời process:

- Dùng **TLS** và xác minh certificate/hostname.
- Xác thực service identity (mTLS, OAuth2 client credentials hoặc cơ chế được triển khai).
- Authorize operation **tại receiver**, không chỉ tin sender.
- Whitelist headers và Content-Type được phép.
- Không tin raw `tenantId` hoặc `sourceSystem` do bên ngoài tự khai.
- Không cho client tự chọn URL/hostname từ message để biến outbound gateway thành SSRF proxy.
- Không cho input tự truyền bean name, SpEL expression hoặc replyChannel nội bộ tới receiver.
- Giới hạn payload size, nesting depth, số items, header length và request rate.

Trong multi-tenant, operationId có thể trùng giữa các tenant; **idempotency key scope** phải bao gồm identity/tenant đã xác minh. Correlation IDs không phải access tokens, không dùng chúng làm bằng chứng được phép đọc reservation.

**Secrets không thuộc domain payload**. Đừng để authorization bearer token được log, đưa vào broker DLQ hoặc serialize sang child messages qua wildcard header mapping.

## 34. Serialization và schema evolution của request/reply

Một Java record đổi tên field không tự đảm bảo tương thích với wire schema:

~~~text
Client v1: productCode, units
Server v2: sku, quantity
~~~

Nếu server deploy riêng, cần schema/version contract rõ:

| Thay đổi | Rủi ro | Cách xử lý |
|---|---|---|
| Thêm field optional | Có thể tương thích | Default/unknown behavior phải được định nghĩa |
| Đổi tên field required | Thường breaking | Versioned mapper/schema |
| Đổi units từ integer sang decimal | Breaking semantics | Convert có validation |
| Thay meaning của operationId | Breaking idempotency | Migration protocol |
| HTTP 200 đổi từ final sang accepted | Breaking outcome contract | Client update hoặc versioning |
| Remote trả enum mới | Có thể breaking | Unknown enum policy rõ |
| Null ở field trước non-null | Có thể breaking | Reject/tri-state theo contract |
| Đổi currency/number precision | Rủi ro data corruption | BigDecimal/scale tests |

Đừng chấp nhận mọi unknown field rồi coi như đã tương thích: thay đổi meaning có thể không làm deserializer lỗi, nhưng downstream xử lý sai. Nếu cùng API path phục vụ nhiều versions, Router/Transformer chọn theo **contract đáng tin**, không dựa vào type inference tình cờ.

Schema registry hoặc JSON Schema giúp kiểm tra cấu trúc; **không tự đảm bảo business meaning**. Hãy version cả mapping policy khi replay event từ DLQ sau một lần nâng cấp.

## 35. Kết hợp Filter, Router và Transformer trước remote call

Một flow có kiểm soát:

~~~text
Inbound Java Gateway
  → Filter / schema validation
  → Router by allowed operation
  → Transformer to remote DTO
  → Remote outbound gateway
  → Transformer to domain result
  → Gateway reply
~~~

| Endpoint | Trách nhiệm | Sai lầm thường gặp |
|---|---|---|
| **Filter** | Chặn payload sai trước I/O | Gọi remote side effect trong predicate |
| **Router** | Chọn một remote operation/endpoint đã whitelist | Route theo arbitrary URL/method header |
| **Transformer** | Convert DTO/units/headers có kiểm tra | Tự gọi remote API trong mapper không có error policy |
| **Outbound gateway** | Thực hiện request–reply transport | Giả định HTTP 202 là business success |
| **Service Activator** | Chạy một method nghiệp vụ | Gộp query/command mơ hồ |
| **Error handler** | Phân loại failure và recovery | Catch mọi lỗi thành input invalid |

**Không nhất thiết tách thành từng endpoint riêng cho một flow nhỏ.** Có thể đóng gói nhiều bước trong một adapter có test đầy đủ. Điều quan trọng là **trách nhiệm và side effect boundary rõ ràng**.

## 36. RPC-style call không phù hợp với mọi workflow

Một Gateway chờ reply là lựa chọn hợp lý khi:

- Remote API có latency dự đoán được và SLA ngắn.
- Caller thực sự cần kết quả ngay.
- Có retry/idempotency và error contract đủ mạnh.
- Concurrency/connection limits được kiểm soát.

Nên cân nhắc asynchronous messaging khi:

- Operation kéo dài hàng phút/giờ.
- Có nhiều steps và compensations.
- Workflow cần chịu được downtime của một service.
- Có fan-out lớn hoặc xử lý batch.
- Caller có thể nhận `PENDING` rồi query status/callback.

~~~text
Synchronous RPC-style:
  Checkout.reserve() → wait → RESERVED

Asynchronous workflow:
  Checkout.submitReserve() → durable ACCEPTED
  → worker → remote Inventory
  → eventual completion event/status
~~~

**Không gọi `ACCEPTED` là `SUCCEEDED`** nếu remote chưa commit. Cũng không xây một blocking Gateway với reply timeout 60 phút chỉ để che một process manager thực sự cần có durability và progress tracking.

## 37. Async request–reply với durable status và outbox

Một mẫu:

~~~mermaid
flowchart TD
    C["Checkout"] --> IN["Durable command intake"]
    IN -->|"Persist accepted"| P["Return PENDING + operationId"]
    IN --> OUT["Outbox / work queue"]
    OUT --> W["Worker"]
    W --> REM["Inventory remote API"]
    REM --> W
    W --> STATE["Durable operation result"]
    STATE --> Q["GET status / completion event"]
~~~

Các nguyên tắc:

1. Sender ghi **command intent và status reference** durable trước khi trả pending.
2. Worker claim work có lease/visibility timeout và retry budget.
3. OperationId giữ nguyên qua retry và remote calls.
4. Receiver dedupe bằng unique key + fingerprint.
5. Worker lưu final result hoặc unknown outcome state.
6. Caller nhận final outcome qua status endpoint/event; không chỉ chờ một JVM-local replyChannel.
7. Có expiry/reconciliation/cleanup cho work lâu không hoàn tất.

Một message broker không tự đồng nghĩa durable ở mọi cấu hình; cần kiểm tra persistence, publisher confirms, retention, ordering, consumer ACK và failure recovery của transport cụ thể.

## 38. Remote invocation trong Scatter-Gather hoặc Splitter/Aggregator

Một order có ba warehouses:

~~~text
ReserveStockCommand parent=O-901
  → Splitter:
      Warehouse A, member A
      Warehouse B, member B
      Warehouse C, member C
  → three remote reservations
  → Aggregator
  → OrderReservationSummary
~~~

Với mỗi child:

- Có `parentCorrelationId` cùng một logical group.
- Có **memberId** khác nhau (warehouse/line ID).
- Có **child operationId** khác nhau để remote dedupe đúng từng reservation.
- Có deadline/retry budget riêng nhưng không vượt parent deadline.
- Có `StockReservationResult` **hoặc một terminal error outcome** rõ khi không thể hoàn tất.

**Không dùng cùng một idempotency key cho cả ba warehouses nếu receiver coi key đó đại diện cho một reservation duy nhất.** Và không thả một exception vào global error channel rồi quên trả member B: Aggregator có thể chờ vô hạn.

Nếu một warehouse đã reserve thành công nhưng warehouse khác từ chối, cần domain policy: partial accept, release/compensate, hoặc retry member bị lỗi. Sự kiện “có đủ ba replies” không đồng nghĩa “đã giữ được tất cả stock”.

## 39. Một member thất bại: trả failure outcome có correlation

Một result type:

~~~java
record ReservationMemberOutcome(
    String parentGroupId,
    String memberId,
    String operationId,
    boolean successful,
    String reservationId,
    String reasonCode
) {}
~~~

Khi warehouse B trả out-of-stock:

~~~java
ReservationMemberOutcome rejected =
    new ReservationMemberOutcome(
        "tenant-a|O-901|reservation-v2",
        "warehouse-B",
        "RES-901-B",
        false,
        null,
        "OUT_OF_STOCK");
~~~

Aggregator cần:

- So kết quả với **expected member manifest** (A, B, C).
- Không tính duplicate B là một member mới.
- Không trộn group của hai tenants/revisions có `orderId` trùng.
- Phân biệt **business rejection** với timeout/unknown remote outcome.
- Release/expire theo policy có chủ đích; không bỏ member lỗi rồi báo success.
- Nếu cần compensation, trigger cancel đúng reservation IDs đã được commit.

Một `UNKNOWN_OUTCOME` không nên bị biến thành `OUT_OF_STOCK` chỉ để Aggregator đủ count; nó cần reconciliation hoặc một terminal workflow status phù hợp.

## 40. Giới hạn tài nguyên ở boundary gọi từ xa

Một RPC-style request có thể block threads, chiếm HTTP connections và dồn lưu lượng lên remote service:

~~~text
100 concurrent checkout calls
  × 3 warehouses each
  × 2 retry attempts
  = up to 600 remote calls
~~~

Đây là một ước lượng trong ví dụ nếu mọi request đều fan-out và retry; thực tế còn bị giới hạn bởi pool/rate limit/deadline.

Biện pháp:

- Connection pool có max total/per-route hợp lý.
- Bounded executor/queue và backpressure; không phát không giới hạn.
- Per-tenant/per-service concurrency quota.
- Circuit breaker, rate limit và bulkhead để cách ly remote dependencies.
- Timeout và retry deadline thống nhất.
- Max payload/header sizes trước serialization.
- Pending reply/group store có TTL/expiry và cleanup.
- Quarantine/DLQ có retention/capacity để producer lỗi không làm đầy storage.

**Không giải quyết quá tải bằng cách tăng timeout vô hạn.** Timeout lớn giữ threads/connection lâu và có thể làm đứt toàn bộ Checkout khi Inventory chậm.

## 41. Unit test application port mà không cần Spring Integration context

Vì Checkout chỉ phụ thuộc `InventoryReservationPort`, có thể test bằng fake:

~~~java
@Test
void checkoutUsesTypedInventoryPort() {
    InventoryReservationPort fake = cmd ->
        new StockReservationResult(
            cmd.operationId(),
            cmd.orderId(),
            "RSV-555",
            ReservationStatus.RESERVED);

    CheckoutUseCase checkout = new CheckoutUseCase(fake);
    ReserveStockCommand command = new ReserveStockCommand(
        "tenant-a", "RES-901", "O-901", "SKU-7", 2);

    StockReservationResult result =
        checkout.reserveForOrder(command);

    assertEquals("RES-901", result.operationId());
    assertEquals("O-901", result.orderId());
    assertEquals("RSV-555", result.reservationId());
    assertEquals(ReservationStatus.RESERVED, result.status());
}
~~~

**Test này chỉ xác nhận application boundary**, không chứng minh HTTP request, authentication, reply correlation hay Spring configuration chính xác. Nhưng nó cho thấy domain use case không biết `MessageChannel`, URL hoặc HTTP status.

Một test khác có thể cho fake port ném `RemoteOperationUnknownException` (exception ứng dụng) để kiểm tra Checkout **không** gán `RESERVED` hay `FAILED` chắc chắn khi remote outcome chưa rõ.

## 42. Unit test mapper: input sai không đi đến remote I/O

Exception ứng dụng tối thiểu:

~~~java
final class InvalidReservationCommandException
        extends RuntimeException {
    InvalidReservationCommandException(String reasonCode) {
        super(reasonCode);
    }
}

final class RemoteProtocolException extends RuntimeException {
    RemoteProtocolException(String reasonCode) {
        super(reasonCode);
    }
}
~~~

Unit test request mapping:

~~~java
@Test
void mapperKeepsLogicalOperationIdentity() {
    ReservationRequestMapper mapper =
        new ReservationRequestMapper();
    ReserveStockCommand command = new ReserveStockCommand(
        "tenant-a", "RES-901", "O-901", "SKU-7", 2);

    StockReservationHttpRequest wire =
        mapper.toHttpRequest(command);

    assertEquals("RES-901", wire.requestId());
    assertEquals("O-901", wire.orderRef());
    assertEquals("SKU-7", wire.productCode());
    assertEquals(2, wire.units());
}

@Test
void invalidQuantityIsRejectedBeforeRemoteCall() {
    ReservationRequestMapper mapper =
        new ReservationRequestMapper();
    ReserveStockCommand invalid = new ReserveStockCommand(
        "tenant-a", "RES-901", "O-901", "SKU-7", -3);

    InvalidReservationCommandException failure =
        assertThrows(
            InvalidReservationCommandException.class,
            () -> mapper.toHttpRequest(invalid));

    assertEquals(
        "INVALID_RESERVATION_COMMAND",
        failure.getMessage());
}
~~~

Việc mapper ném exception **không tự chứng minh outbound gateway chưa gọi remote** nếu flow chạy các side effects **trước** mapper. Integration test cần đặt mapper **trước** outbound gateway, dùng fake remote server/spy để assert số requests = 0 khi input invalid.

Đừng mặc định `quantity=0` luôn invalid trong mọi domain; ví dụ này chọn contract reservation yêu cầu số đơn vị dương. Các operation trả hàng/hủy giữ kho có thể có rule khác, cần command type riêng.

## 43. Unit test reply: enum, required fields và correlation

Kiểm tra mapping của response:

~~~java
@Test
void validRemoteReplyMapsToDomain() {
    ReservationReplyMapper mapper =
        new ReservationReplyMapper();
    StockReservationHttpResponse raw =
        new StockReservationHttpResponse(
            "RES-901", "O-901", "RESERVED", "RSV-555");

    StockReservationResult result = mapper.toResult(raw);

    assertEquals(ReservationStatus.RESERVED, result.status());
    assertEquals("O-901", result.orderId());
    assertEquals("RES-901", result.operationId());
}

@Test
void unknownStatusIsProtocolFailure() {
    ReservationReplyMapper mapper =
        new ReservationReplyMapper();
    StockReservationHttpResponse raw =
        new StockReservationHttpResponse(
            "RES-901", "O-901", "SOMETHING_NEW", "RSV-555");

    assertThrows(
        RemoteProtocolException.class,
        () -> mapper.toResult(raw));
}
~~~

Với helper `mapCheckedReply()` ở mục 16, cần test thêm:

~~~text
Expected operationId=RES-901, orderId=O-901
Reply requestId=RES-902, orderRef=O-901
  → REMOTE_CORRELATION_MISMATCH

Expected operationId=RES-901, orderId=O-901
Reply requestId=RES-901, orderRef=O-902
  → REMOTE_CORRELATION_MISMATCH
~~~

**Không chỉ assert response có type đúng.** Nếu remote reply bị ghép nhầm request, việc có một `StockReservationHttpResponse` hợp lệ về cấu trúc vẫn có thể gây rò dữ liệu và sai trạng thái nghiệp vụ.

## 44. Integration test cho Gateway proxy với handler giả

Trước khi test HTTP thật, xác minh Spring Integration tạo đúng typed Gateway và reply:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class ReservationGatewayTestConfig {

    @Bean
    IntegrationFlow reservationTestFlow() {
        return IntegrationFlow
            .from("inventory.reserve.requests")
            .handle(
                ReserveStockCommand.class,
                (command, headers) ->
                    new StockReservationResult(
                        command.operationId(),
                        command.orderId(),
                        "RSV-TEST",
                        ReservationStatus.RESERVED))
            .get();
    }
}
~~~

Test:

~~~java
@Autowired
InventoryReservationGateway gateway;

@Test
void javaGatewayGetsReplyWithoutManualMessageBuilder() {
    StockReservationResult reply = gateway.reserve(
        new ReserveStockCommand(
            "tenant-a", "RES-901", "O-901", "SKU-7", 2));

    assertEquals("RES-901", reply.operationId());
    assertEquals("RSV-TEST", reply.reservationId());
    assertEquals(ReservationStatus.RESERVED, reply.status());
}
~~~

Chạy trong **Spring test context riêng**, bảo đảm annotated Gateway interface được scan. Đừng đăng ký đồng thời flow HTTP production và fake handler này cùng consume `inventory.reserve.requests`; nếu có nhiều subscribers cạnh tranh, một request có thể đi tới endpoint không dự kiến.

Test này chứng minh Gateway **đóng gói lời gọi method thành message và nhận reply**, nhưng không kiểm tra HTTP wire format, connection timeout hoặc remote idempotency; những thứ đó cần integration test với server giả.

## 45. Integration test với fake HTTP server và contract thật

Có thể dùng WireMock, MockWebServer hoặc một local HTTP test server có lifecycle do test kiểm soát. Những điều cần giả lập:

~~~text
POST /reservations
Request Content-Type: application/json
Request Idempotency-Key: RES-901
Body requestId=RES-901, orderRef=O-901, units=2

HTTP 200
{
  "requestId":"RES-901",
  "orderRef":"O-901",
  "result":"RESERVED",
  "reservationRef":"RSV-555"
}
~~~

Test assertions:

1. Gateway gửi đúng method POST/path và Content-Type.
2. Wire payload đúng field names/types và quantity.
3. Header idempotency **thực sự có trên HTTP request**, không chỉ ở Spring message.
4. Authentication/TLS hoặc fake auth interceptor được gọi theo cấu hình.
5. Response body được converter decode thành `StockReservationHttpResponse`.
6. Reply Transformer trả `StockReservationResult` đúng.
7. Response requestId/orderRef phải khớp **request context**.
8. Nếu remote trả business rejection, Gateway không map thành reserved.
9. Nếu server trả 503/timeout, error classifier hoạt động như contract.
10. Không gọi production Inventory thật trong test.

**Không chỉ mock `InventoryReservationPort`** rồi tuyên bố outbound gateway đã được kiểm thử. Mock port sẽ bỏ qua integration adapter, HTTP serializer, headers, timeout và error mapping—những lỗi chính của bài học.

Vì bài tập này phụ thuộc Spring Integration/HTTP client version, hãy cấu hình test server URL bằng một property/URI template được inject. **Không hardcode production endpoint** vào code unit/integration test.

## 46. Fault injection: request chưa gửi, server commit và reply mất

Ba failure windows khác nhau:

~~~text
A. DNS/connect refused:
   Không có connection; có thể request chưa đến remote.

B. Remote receives request, throws before commit:
   Receiver xử lý thất bại; caller có thể nhận 500.

C. Remote commits reservation, reply dropped:
   Caller read timeout; remote effect đã tồn tại.
~~~

Test C là quan trọng nhất đối với command có side effect. Một fake server lưu:

~~~text
operation RES-901 → RESERVED RSV-555
~~~

rồi cố ý **không trả response** lần đầu. Caller nhận timeout, sau đó gửi lại bằng **RES-901**. Receiver trả cùng `RSV-555` mà không cấp reservation mới.

Assertions:

- Remote committed reservations count = 1.
- Sender không đổi operationId khi retry.
- Local workflow không ghi `FAILED_PERMANENT` chỉ vì read timeout.
- Nếu không có reply hoặc status lookup, state là `UNKNOWN_OUTCOME`.
- Retry hoặc reconciliation tạo một terminal outcome đúng.
- Không rò socket/thread/pending requests sau timeout.

**HTTP 503 không chắc chắn nói remote chưa có side effect** trong mọi API. Một server có thể commit rồi lỗi khi dựng response; với mutation request, luôn xét idempotency/reconciliation theo contract.

## 47. Concurrency test: cùng operationId đến hai receiver threads

Một test tuần tự:

~~~text
reserve(RES-901)
reserve(RES-901)
assert one reservation
~~~

chưa phát hiện race khi hai requests đồng thời.

Test concurrency cần dùng real transaction/unique constraint:

~~~mermaid
sequenceDiagram
    participant A as Receiver A
    participant B as Receiver B
    participant DB as Inventory DB
    A->>DB: Claim RES-901
    B->>DB: Claim RES-901 concurrently
    DB-->>B: Wait/conflict by unique key
    A->>DB: Reserve stock + COMMIT
    B->>DB: Lookup committed result
    DB-->>B: RESERVED RSV-555
    Note over A,B: one business reservation committed
~~~

Các case:

- Hai cùng key/cùng fingerprint → **một** business side effect.
- Cùng key/khác fingerprint → conflict, không silently overwrite.
- Worker A rollback trước commit → worker B có thể retry an toàn.
- Worker A commit rồi crash trước reply → worker B nhận cached result.
- Hai tenant có same operation ID → dedupe scope **không trộn tenant**.
- Restart/đa instance → dedupe vẫn hoạt động.

Sử dụng `CountDownLatch` hoặc transaction test barriers, timeout cho test và kiểm tra final DB row counts. `synchronized` trên singleton bean hoặc `ConcurrentHashMap` chỉ trong JVM không thay unique constraint/durable state.

## 48. Test broker request–reply, ACK và late replies

Khi thay HTTP outbound gateway bằng Kafka/AMQP/JMS request–reply, cần test ở **transport boundary thật**, không chỉ dùng `DirectChannel`:

~~~text
Request rpc-try-0042 → queue "inventory.requests"
  payload.operationId = RES-901
  header.replyTo = "inventory.replies.client-a"

Remote consumer → reserve stock
  → reply rpc-try-0042 on reply destination

Gateway reply listener → correlate → StockReservationResult
~~~

Kiểm tra:

1. **Request publish/ACK** theo broker contract không bị nhầm với business completion.
2. `replyTo` và `transportCorrelationId` được map đúng giữa protocol headers.
3. Two concurrent requests có replies **đảo thứ tự** vẫn trả đúng caller.
4. Duplicate request không tạo duplicate reservation.
5. Duplicate reply không tạo second completion event.
6. Reply đến sau timeout được cleanup/quarantine/ghi durable status theo policy.
7. Message malformed đi đến rejection/DLQ có reasonCode, không retry vô tận.
8. DLQ publish failure không làm source message bị ACK mất nếu chưa có recovery khác.
9. Receiver crash sau commit trước ACK: redelivery nhận cached result.
10. Sender restart khi còn pending request: durable workflow cần recover; temporary JVM-only reply address sẽ không tự sống lại.

**Broker reply-to/correlation features và transaction semantics khác nhau theo adapter**. Hãy cấu hình/test bằng protocol cụ thể; không tái sử dụng nguyên Java `replyChannel` object từ Spring như một broker wire value.

## 49. Ma trận kiểm thử end-to-end

| Case | Input/fault | Kỳ vọng |
|---|---|---|
| Valid reservation | `RES-901`, quantity 2 | Reply RESERVED khớp request |
| Invalid quantity | `quantity=-1` | Reject trước I/O |
| Missing operationId | Empty/null ID | Reject, không gọi remote |
| Wrong wire shape | JSON array thay object | Decode/schema reject |
| Unsupported schema | Reply/version mới không hỗ trợ | Protocol error, không fake success |
| Remote out-of-stock | Business rejection | `REJECTED_OUT_OF_STOCK`, không retry nóng |
| HTTP 202 | Remote accepted async | PENDING + status reference |
| HTTP 400 | Invalid request | Permanent error |
| HTTP 401/403 | Credentials/rights | Security error + audit |
| HTTP 409 | Conflict/duplicate | Xử lý theo documented API |
| HTTP 429 | Rate limit | Retry budget/Retry-After |
| HTTP 503 | Transient outage | Bounded retry + circuit breaker |
| Connect refused | Chưa có connection | Classifier đúng, không bịa result |
| Read timeout after commit | Remote đã reserve | UNKNOWN/reconcile, không double reserve |
| Malformed reply body | Missing reservationRef | Protocol failure |
| Wrong reply requestId | Correlation mismatch | Không giao nhầm reply |
| Wrong reply orderRef | Một order khác | Protocol error + audit |
| Two concurrent callers | Responses đảo thứ tự | Không lẫn caller |
| Same ID, same payload | Redelivery | Cached reply, one effect |
| Same ID, different payload | Key conflict | Không silently overwrite |
| Two tenants same key | Cross-tenant collision | Dedupe scoped theo tenant |
| Duplicate broker reply | Hai reply cùng correlation | Một completion |
| Late broker reply | Caller đã timeout | Không kích hoạt reservation mới |
| Outbox publisher crash | Send xong, chưa mark sent | Receiver idempotent |
| Sender worker restart | In-flight command | Durable status/recovery |
| Receiver DB rollback | Claim tồn tại trước commit | Retry hợp lệ, không poisoned marker |
| DLQ unavailable | Quarantine publish fail | Không ACK mất trách nhiệm |
| Splitter child failure | Warehouse B reject | Final group FAILED/PARTIAL theo policy |
| Aggregator duplicate | Warehouse A reply hai lần | Không tính thành member C |
| Large payload | Quá limit | Reject trước deserialize/fan-out |
| Header spoofing | Fake tenant/auth | Security rejection |
| Contract v1→v2 | Rename required field | Mapper/versioned contract |
| Gateway timeout | Worker tiếp tục commit | Không nhầm timeout với rollback |

**Test ba lớp:** (1) mapper Java, (2) IntegrationFlow/Gateway proxy, (3) HTTP/broker adapter + remote receiver/DB. Một lớp test không thay thế hai lớp còn lại. Với side effect, assert **database row counts, idempotency records, remote call counts** và tình trạng outbox/reply, không chỉ assert exception.

## 50. Observability: đo remote attempts khác business completions

Các metric **gợi ý**, không phải meter mặc định của Spring Integration:

| Metric | Điều cần quan sát |
|---|---|
| `remote.invoke.request.count` | Số logical requests |
| `remote.invoke.attempt.count` | Số transport attempts (kể cả retries) |
| `remote.invoke.reply.count` | Replies nhận được |
| `remote.invoke.reply.timeout.count` | Caller chờ quá hạn |
| `remote.invoke.connect.failure.count` | Không kết nối được |
| `remote.invoke.read.timeout.count` | Network read timeout |
| `remote.invoke.correlation.mismatch.count` | Reply không khớp request |
| `remote.invoke.protocol.failure.count` | Remote schema/status bất thường |
| `remote.invoke.business.rejected.count` | Remote từ chối theo domain |
| `remote.invoke.unknown.outcome.count` | Operation chưa có final result |
| `remote.invoke.reconciliation.pending.count` | Lệnh cần xác minh remote state |
| `remote.invoke.retry.exhausted.count` | Dùng hết retry budget |
| `remote.invoke.circuit.open.count` | Calls bị chặn bởi circuit |
| `remote.receiver.duplicate.completed.count` | Receiver trả cached result |
| `remote.receiver.idempotency.conflict.count` | Same key, changed payload |
| `remote.receiver.side_effect.committed.count` | Số reservations thực sự được tạo |
| `remote.invoke.duration` | Latency theo endpoint/operation |
| `remote.invoke.pending.reply.count` | Pending request map đang giữ |

**Logical requests và attempts khác nhau**: một operation `RES-901` có thể được gửi ba lần nhưng receiver chỉ commit một reservation. Không báo hiệu hệ thống đã tạo ba reservations chỉ vì HTTP requests count bằng 3.

Tags nên có cardinality thấp như `remoteServiceAlias`, `operation`, `outcome`, `reasonCode`, `schemaVersion`; không đặt `operationId`, `tenantId` nhạy cảm, full URL có query string, `eventId` hoặc email thành metric labels.

Structured log/tracing có kiểm soát:

~~~text
operation=RESERVE_STOCK
remoteService=inventory
operationId=RES-901
transportAttempt=2
transportCorrelationId=rpc-try-0043
remoteStatus=RESERVED
businessOutcome=SUCCEEDED
idempotentReplay=true
sideEffectCommittedCount=0
~~~

Khi timeout:

~~~text
operationId=RES-901
transportAttempt=1
failureKind=UNKNOWN_OUTCOME
reconciliationStatus=PENDING
businessOutcome=UNKNOWN
~~~

ID cụ thể có thể có trong logs/traces được phân quyền, retention đúng; đừng copy toàn bộ payload/authorization headers hoặc raw HTTP response vào logs mặc định.

## 51. Runbook: Gateway báo timeout, Inventory đã reserve hay chưa?

Quy trình điều tra:

1. **Tìm logical operationId** từ Checkout, tenant scope và orderId.
2. **Kiểm tra local validation:** command có bị reject trước outbound gateway không?
3. **Kiểm tra request channel:** đã gửi thành công, có queue backlog/executor saturation không?
4. **Kiểm tra transform/header mapping:** wire DTO và Idempotency-Key đúng contract chưa?
5. **Kiểm tra network:** connect refused, read timeout, HTTP 503 hay 429?
6. **Phân biệt timeout:** request send, HTTP response, Gateway reply hay business deadline?
7. **Kiểm tra remote idempotency record:** receiver có record `RES-901` không, fingerprint/state gì?
8. **Kiểm tra remote reservation:** stock đã được giữ/commit chưa, reservationId nào?
9. **Kiểm tra local outbox/state:** sender đã lưu durable intent và outcome gì?
10. **Kiểm tra correlation/reply-to:** có reply trễ, duplicate hoặc mismatch không?
11. **Kiểm tra retries:** cùng operationId hay vô tình tạo key mới cho mỗi attempt?
12. **Kiểm tra side effects khác:** payment, email hoặc cancellation đã chạy chưa?
13. **Reconcile:** query remote status theo key; nếu không có API, xử lý unknown outcome theo manual/recovery policy.
14. **Khắc phục:** sửa mapper/timeout/bulkhead/circuit/idempotency, thêm test tái hiện crash window.
15. **Kết thúc:** cập nhật final business outcome, không chỉ đóng một network alert khi local/remote states vẫn mâu thuẫn.

**Không tự hủy rồi tạo lại reservation** khi chỉ biết caller timeout. Một request cũ có thể hoàn tất sau khi cancellation gửi đi, dẫn tới state chuyển qua lại nếu workflow không kiểm soát ordering và idempotency.

## 52. Bài thực hành: thay HTTP client trực tiếp bằng message-driven invocation

Xây mini project **InventoryRemoteInvocation**:

1. Định nghĩa `ReserveStockCommand` và `StockReservationResult` ở application layer.
2. Định nghĩa `InventoryReservationPort` và dùng fake implementation để unit test Checkout.
3. Tạo interface `InventoryReservationGateway` với `@MessagingGateway`.
4. Viết `ReservationRequestMapper` và `ReservationReplyMapper`.
5. Tạo `IntegrationFlow.from("inventory.reserve.requests")` với request Transformer, HTTP outbound gateway, reply Transformer.
6. Dùng fake HTTP server cung cấp `/reservations` nhận JSON wire contract.
7. Cấu hình HTTP Content-Type, TLS/auth trong môi trường test thích hợp và Idempotency-Key header mapper.
8. Kiểm thử payload/headers/response result/correlation; không gọi production Inventory.
9. Thử input invalid trước HTTP call: fake server phải thấy request count = 0.
10. Fake server trả `REJECTED_OUT_OF_STOCK`; Gateway trả business rejection.
11. Fake server trả 503; thiết kế bounded retries, assert attempts và backoff policy.
12. Fake server commit rồi làm mất reply; caller phải ghi unknown outcome/reconcile bằng **same operationId**.
13. Viết receiver-side inbox DB có unique constraint và fingerprint.
14. Test hai concurrent requests cùng key; chỉ một reservation thực sự commit.
15. Thay HTTP bằng một broker request–reply test flow có reply-to/correlation, không đổi Checkout application port nếu semantics được giữ.
16. Thêm Splitter cho ba warehouses, mỗi child có operationId riêng; Aggregator không đếm duplicate.
17. Inject một child failure và một late reply, xác minh summary đúng.
18. Thêm outbox/saga hoặc durable pending status cho operation chậm.
19. Giới hạn concurrent remote calls và theo dõi retry amplification.
20. Viết runbook debug remote call timeout theo `operationId`, không dựa riêng vào HTTP exception text.

**Tiêu chí hoàn thành:** caller chỉ gọi typed port, wire request được tạo đúng; remote reply được correlate và validate; timeout không bị gắn nhầm thành business failure; retry không tạo side effect trùng; error channel, DLQ/reconciliation và status đồng bộ giữa sender–receiver; tests kiểm tra cả message flow và HTTP/broker boundaries.

## 53. Những hiểu lầm thường gặp

**“RPC qua Gateway giống method local, chỉ cần try/catch.”** Sai. Remote có timeout, partial failure và unknown outcome.

**“Đóng gói thành message nghĩa là không còn coupling.”** Không. Vẫn có wire schema, latency, security và remote service semantics.

**“`@MessagingGateway` tự gọi HTTP remote.”** Không. Nó gửi request vào IntegrationFlow; outbound gateway/adapter thực hiện transport.

**“HTTP outbound channel adapter luôn trả reply.”** Không. Phân biệt one-way adapter và request–reply gateway.

**“HTTP 200 luôn là business success.”** Không. Body có thể là domain rejection.

**“HTTP 202 nghĩa là giữ stock thành công.”** Không, thường là accepted theo API contract; phải kiểm tra status.

**“HTTP 503 chứng minh server chưa commit.”** Không nhất thiết, nhất là khi lỗi dựng response sau side effect.

**“Timeout tức là operation bị hủy/rollback.”** Không. Remote có thể tiếp tục và commit.

**“Một retry dùng requestId mới để tránh conflict.”** Nguy hiểm: có thể tạo một business operation mới và double reservation.

**“Transport correlation ID và idempotency key là một.”** Không. Correlation ghép request–reply; idempotency bảo vệ logical effect.

**“Spring Message ID bền qua broker replay.”** Không được mặc định.

**“Header Idempotency-Key tự có nghĩa ngay cả khi receiver bỏ qua.”** Không. Receiver phải có dedupe/transaction contract.

**“Local @Transactional rollback remote inventory DB.”** Không. Hai services có transaction boundaries khác nhau.

**“Một seen marker trong Redis đồng nghĩa remote đã commit.”** Không nếu marker không atomic với reservation write.

**“Có một ErrorMessage trong errorChannel nghĩa caller đã được trả lỗi.”** Không. Async error recovery không tự là reply.

**“ACK broker bằng kết quả nghiệp vụ.”** Sai. Transport ACK và business outcome khác nhau.

**“Cần reply thì cứ block Gateway hàng phút.”** Thường khó vận hành; durable async workflow/status có thể phù hợp hơn.

**“Lỗi child remote có thể drop mà Aggregator vẫn thành công.”** Sai. Group cần failure outcome/release/compensation policy.

**“Mọi custom header từ Spring tự đi qua HTTP/broker.”** Không. Cần mapper/whitelist/test.

**“Chỉ cần unit test mapper là đủ.”** Không. Phải test outbound transport, receiver dedupe, retries và crash windows.

## 54. Ghi nhớ

**Đóng gói lời gọi từ xa thành message** giúp application code dùng **một method có kiểu** trong khi Spring Integration tổ chức request channel, Transformer, outbound gateway, reply message, Router/Filter và error handling. Hướng đi thường là **application port → `@MessagingGateway` → request message → outbound transport gateway → remote receiver → reply message → typed result**.

Giá trị của pattern không phải khiến remote service **trông như local và chắc chắn thành công**, mà là **tách việc gọi từ xa khỏi business code** để quản lý transport/versioning, validation, correlation và recovery ở một integration boundary rõ ràng.

Với command có side effect, giữ **logical operationId/idempotency key** xuyên retry, dùng **correlation ID** riêng cho từng request/reply attempt, phân biệt **HTTP/broker ACK với business completion**, và không suy ra operation đã rollback từ timeout. Nếu có remote unknown outcome, cần **status lookup/reconciliation**; nếu workflow kéo dài hoặc fan-out, ưu tiên durable messaging, inbox/outbox và process manager khi phù hợp. Kiểm thử cả **happy path, malformed input, lỗi kết nối, remote commit trước khi reply mất, duplicate/concurrent requests và late replies** để một Gateway thuận tiện không che khuất rủi ro phân tán.

### Tài liệu tham khảo

- Enterprise Integration Patterns, **Messaging Gateway**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Enterprise Integration Patterns, **Request-Reply**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/RequestReply.html
- Enterprise Integration Patterns, **Correlation Identifier**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html
- Spring Integration Reference, **Messaging Gateways**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **HTTP Support**: https://docs.spring.io/spring-integration/reference/http.html
- Spring Integration Reference, **Transformer**: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference, **Router**: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Service Activator**: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Framework Reference, **Declarative Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
