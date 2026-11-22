# Return value thành reply message

> **Chương:** Service activator  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này tập trung vào **cách giá trị trả về của phương thức nghiệp vụ được chuyển thành reply message và được định tuyến đúng trong Spring Integration**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **Service Activator** trong EIP: đưa thông điệp từ hệ thống tích hợp vào một phương thức nghiệp vụ và, nếu có kết quả, đưa kết quả đó trở lại luồng message.
2. Mô tả đầy đủ vòng đời **request → handler invocation → return value → reply message → reply destination**.
3. Phân biệt phương thức trả **POJO/record**, trả **`Message<?>`**, trả **`null`**, trả **`void`**, hoặc ném exception; hiểu vì sao chúng không giống nhau.
4. Phân biệt **output channel được cấu hình** với **`replyChannel` của request**, đồng thời biết khi nào Gateway đang chờ sẽ nhận được reply hoặc bị timeout.
5. Viết Service Activator bằng Spring Integration **Java DSL** và minh họa Gateway request–reply, metadata propagation, typed business rejection và error handling.
6. Biết giữ hoặc loại metadata như `businessCorrelationId`, `operationId`, `replyChannel`, `errorChannel` khi dựng response, đặc biệt trước external transport boundary.
7. Phân tích tác động của local retry, broker redelivery, thread/ExecutorChannel, Splitter/Aggregator, duplicate reply và idempotency đến một luồng trả kết quả.
8. Viết kiểm thử JUnit 5 cho service và integration flow, bao gồm kết quả thành công, từ chối nghiệp vụ, reply routing, thiếu reply và các nhánh không được phép xuất dữ liệu.

## 2. Bài toán: đã giữ hàng nhưng Gateway không nhận được kết quả

Một ứng dụng thương mại điện tử gửi lệnh giữ hàng:

~~~json
{
  "tenantId": "shop-a",
  "operationId": "RSV-901",
  "orderId": "ORD-901",
  "sku": "BOOK-42",
  "quantity": 2
}
~~~

Phương thức nghiệp vụ có thể trả một đối tượng kết quả:

~~~json
{
  "operationId": "RSV-901",
  "orderId": "ORD-901",
  "status": "RESERVED",
  "reason": null
}
~~~

Khi dùng Spring Integration, chuyện **phương thức Java trả `ReserveReceipt`** khác chuyện **caller nhận được message reply**. Handler cần chuyển return value thành message, biết gửi message tới channel nào, xử lý trường hợp không có kết quả, và bảo toàn metadata thiết yếu.

~~~mermaid
sequenceDiagram
    participant G as Gateway / Producer
    participant C as Request channel
    participant A as Service Activator
    participant S as ReservationService
    participant R as Reply channel
    G->>C: Message<ReserveCommand> + replyChannel
    C->>A: Deliver request
    A->>S: reserve(ReserveCommand)
    S-->>A: ReserveReceipt
    A-->>R: Message<ReserveReceipt>
    R-->>G: Reply correlated to request
~~~

Một flow có thể **xử lý nghiệp vụ thành công** nhưng caller vẫn đợi đến timeout nếu reply bị gửi nhầm channel, bị drop, hoặc không được tạo vì handler trả `null`.

### 2.1. Kết quả trả về không phải transport ACK

Một broker ACK, HTTP status, Java return value và business commit là **bốn sự kiện khác nhau**:

~~~text
Business service returns ReserveReceipt
    != Warehouse DB definitely committed
    != Broker ACK already sent
    != Gateway caller already received reply
    != Exactly-once business side effect
~~~

Trong demo không gọi DB thật nên chỉ có thể khẳng định service đã **tính ra kết quả**. Trong production, chỉ công bố `RESERVED` sau khi có bằng chứng commit hoặc outcome được lưu bền theo hợp đồng.

## 3. Service Activator trong Enterprise Integration Patterns

**Service Activator** kết nối một messaging system với **phương thức của một service object**. Nó nhận message, lựa chọn/invoke method tương ứng và có thể gửi kết quả trở lại messaging infrastructure.

~~~text
Message<ReserveCommand>
   |
   v
[inputChannel]
   |
   v
Service Activator
   |
   +-- invoke reservationService.reserve(command)
   |
   +-- return ReserveReceipt / Message<ReserveReceipt>
   |
   v
[reply destination]
~~~

Trong Spring Integration, service activator có thể được cấu hình bằng:

- Java DSL `IntegrationFlow...handle(service, "method")`.
- Annotation `@ServiceActivator(inputChannel = "...", outputChannel = "...")` trên method/bean phù hợp.
- Handler chuyên dụng `ServiceActivatingHandler` trong các trường hợp cần cấu hình nâng cao.
- Gateway dùng request channel và nhận lại reply do flow phát ra.

### 3.1. Service Activator khác Transformer

| Đối tượng | Mục đích chính | Ví dụ |
| --- | --- | --- |
| **Transformer** | Chuyển biểu diễn payload/message | JSON đối tác → `ReserveCommand` |
| **Service Activator** | Gọi phương thức nghiệp vụ từ message | `reservationService.reserve(command)` |
| **Gateway** | Đưa lời gọi application API vào/ra message flow | `gateway.reserve(command)` trả receipt |
| **Router** | Chọn channel theo điều kiện | `status=REJECTED` → rejection channel |
| **Filter** | Chấp nhận hoặc loại message | Chặn request invalid |
| **Outbound Adapter** | Đẩy message sang hệ thống khác | Publish Kafka / gọi HTTP |
| **Aggregator** | Gom nhiều child replies thành kết quả nhóm | Gom kết quả ba dòng hàng |

**Transformer cũng có thể trả một payload mới**, nhưng về ý nghĩa thiết kế, Service Activator thường là nơi gọi **business service** hoặc nối với chức năng xử lý cụ thể. Không nên vì endpoint có thể trả reply mà nhầm rằng nó luôn được phép tạo side effect ngay trong bước map dữ liệu.

### 3.2. Không phải tất cả Service Activator đều có reply

- **One-way:** nhận event, thực hiện tác vụ, không tạo reply theo contract.
- **Request–reply:** nhận command, trả kết quả nghiệp vụ.
- **Event-to-event:** nhận event, tạo event mới cho bước tiếp theo.
- **Async:** xử lý ngoài thread gọi; reply có thể đến sau theo cơ chế endpoint/transport riêng.

Điều quan trọng là **hợp đồng luồng**: caller có đang chờ phản hồi hay chỉ mong request được chấp nhận giao vào queue?

## 4. Từ return value thành reply message: sáu bước

Một luồng request–reply tiêu biểu:

1. **Nhận request message**: xác định payload, headers, metadata nguồn.
2. **Method invocation**: Spring Integration gọi phương thức nghiệp vụ đã chọn từ message.
3. **Lấy return value**: có thể là POJO, `Message<?>` hoặc không có kết quả.
4. **Tạo/chuẩn bị reply**: khi trả POJO, framework có thể tạo `Message<POJO>` và áp quy tắc header propagation; khi trả `Message<?>`, message đó là một phần của kết quả.
5. **Chọn reply destination**: output channel cấu hình hoặc channel được mang trong request, tùy topology/endpoint.
6. **Gửi reply**: qua channel hoặc Gateway/adapter, có thể chịu timeout/lỗi/transaction riêng.

~~~mermaid
flowchart TD
    IN["Request Message"] --> INV["Invoke service method"]
    INV --> RT{"Return shape?"}
    RT -->|"POJO / record"| WRAP["Build reply Message"]
    RT -->|"Message<?> "| MSG["Use returned message, apply endpoint rules"]
    RT -->|"null / void"| NO["No normal reply; policy may fail"]
    RT -->|"throws"| ERR["Exception / error handling"]
    WRAP --> DEST{"Reply destination available?"}
    MSG --> DEST
    DEST -->|"Configured output channel"| OUT["Send to outputChannel"]
    DEST -->|"Request replyChannel"| RP["Send to request replyChannel"]
    DEST -->|"None or send fails"| FAIL["No-reply / delivery error handling"]
~~~

Đây là **sơ đồ khái niệm**. Quy tắc chọn channel, yêu cầu có reply và header behavior còn phụ thuộc handler, endpoint, phiên bản Spring Integration và cấu hình flow. Không xem reply là “tự động về đúng nơi” nếu topology chưa có đường đi rõ ràng.

## 5. Các kiểu return value và ý nghĩa

| Method return | Reply message thông thường | Cần kiểm chứng |
| --- | --- | --- |
| `ReserveReceipt` / POJO / `record` | Framework tạo reply có payload kiểu đó | Header propagation và destination |
| `String` / `Integer` | Payload chính là giá trị trả về | Có đúng schema downstream không? |
| `Message<ReserveReceipt>` | Reply là message do method dựng, subject to endpoint rules | Header/metadata, internal channels, security |
| `null` | Không có ordinary reply payload | `requiresReply` / Gateway timeout |
| `void` | Không có ordinary reply từ method | Có phải one-way contract không? |
| Ném exception | Không có success reply thông thường | Error channel, exception mapping, retry |
| `Optional<T>` | **Không mặc định** coi `Optional.empty()` là `null` theo business contract | Chuyển thành typed outcome rõ |
| `CompletableFuture<T>`/reactive type | Tùy endpoint hỗ trợ async/reactive | Completion, timeout, error và reply semantics |

**Không nhầm:** `null` không có nghĩa business rejection. Nếu từ chối nghiệp vụ, nên trả một đối tượng như `ReserveReceipt(status=REJECTED)` để caller nhận kết quả có nghĩa.

### 5.1. Vì sao `Optional.empty()` cần thận trọng?

Một `Optional.empty()` là **một object** trong Java, không phải giá trị `null`. Tùy handler/method invocation và converter, nó có thể được xử lý khác mong đợi. Hợp đồng cần định nghĩa rõ:

~~~java
record LookupResult(
    String key,
    String status,
    String value
) {}
~~~

Thay vì trả `Optional.empty()` rồi hy vọng framework hiểu “not found”, service có thể trả `LookupResult(status="NOT_FOUND")` hoặc một typed rejection phù hợp. Điều này giúp Gateway, API và tests diễn giải nhất quán.

### 5.2. Service Activator có thể tạo reply nhưng caller không nhận

Nếu endpoint có **fixed output channel** đang nhận kết quả, nhưng Gateway chờ trên temporary `replyChannel` của request, output đó **không tự chuyển về Gateway**. Cần thiết kế bridge/flow phản hồi hoặc để reply được gửi vào reply channel đúng.

## 6. Đích nhận reply: outputChannel và replyChannel

Hai đường đi phổ biến:

| Cơ chế | Nguồn xác định | Khi dùng |
| --- | --- | --- |
| **Configured output channel** | Endpoint/IntegrationFlow gán kênh đích | Pipeline bước tiếp theo cố định |
| **Request `replyChannel`** | Header của request đã được framework/Gateway cấp | Request–reply với caller động |
| **No reply path** | Không cấu hình và request không có địa chỉ trả lời | One-way; hoặc lỗi contract nếu yêu cầu reply |

Ví dụ hai topology:

~~~text
A. Explicit output:
  input -> Service Activator -> orders.processed -> next step

B. Gateway request/reply:
  gateway.reserve() -> requests -> Service Activator
                                  -> temporary replyChannel
                                  -> Gateway receives receipt
~~~

**Lưu ý:** Trong message flow, output channel cố định của handler/endpoint thường là đường reply được chọn khi nó đã được cấu hình, thay vì dùng địa chỉ trả về của request. Vì vậy, khi viết Gateway flow, **đừng vô tình thêm `.channel("monitoring.queue")` cuối flow** rồi cho rằng Gateway vẫn luôn nhận được receipt. Nếu cần cả logging và response, có thể dùng wire tap, publish-subscribe hoặc bridge có chủ đích và kiểm thử.

### 6.1. `replyChannel` là control metadata

Trong cùng JVM, header `replyChannel` có thể chứa `MessageChannel` hoặc định danh được framework phân giải. Nó không phải địa chỉ HTTP/AMQP/Kafka được phép gửi tùy ý, và không nên được chép qua broker dưới dạng Java object.

Nếu caller bên ngoài được phép tự đặt reply destination, hệ thống cần kiểm soát ACL/allowlist để tránh gửi thông tin nội bộ sang đích không được phép.

### 6.2. `errorChannel` không phải `replyChannel`

- `replyChannel` định tuyến **kết quả xử lý thông thường**.
- `errorChannel` có vai trò trong **đường xử lý lỗi**, phụ thuộc kiểu endpoint, poller, executor, adapter và cấu hình.
- Một `ErrorMessage` không đồng nghĩa một `ReserveReceipt(REJECTED)`.
- Một exception từ `DirectChannel` đồng bộ có thể lan về caller thay vì tự động đi qua error channel bất đồng bộ.

Không được dựa vào một header `errorChannel` như bằng chứng Spring Integration luôn gửi exception vào đúng channel trong mọi topology.

## 7. Java 17: command và typed reply

Dùng records để biểu diễn request/reply. Ví dụ tiếp theo không gọi inventory thật để tập trung vào semantics return value.

~~~java
import java.util.Objects;

record ReserveCommand(
    String tenantId,
    String operationId,
    String orderId,
    String sku,
    int quantity
) {
    ReserveCommand {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(operationId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(sku);
    }
}

record ReserveReceipt(
    String operationId,
    String orderId,
    String status,
    String reasonCode
) {
    ReserveReceipt {
        Objects.requireNonNull(operationId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(status);
    }

    boolean accepted() {
        return "RESERVED".equals(status);
    }
}
~~~

### 7.1. Tách validation và business outcome

Không cho rằng method trả một receipt nghĩa là đã commit. Trong demo, `RESERVED` chỉ là quyết định giả lập. Khi kết nối database thực, response `RESERVED` chỉ được công bố sau khi transaction/operation outcome đã được chốt và có cơ chế khôi phục sau crash.

### 7.2. Service method trả POJO

~~~java
final class ReservationService {

    public ReserveReceipt reserve(ReserveCommand command) {
        if (command.tenantId().isBlank()
                || command.operationId().isBlank()
                || command.orderId().isBlank()
                || command.sku().isBlank()) {
            return new ReserveReceipt(
                command.operationId(),
                command.orderId(),
                "REJECTED",
                "REQUIRED_FIELD_MISSING");
        }

        if (command.quantity() < 1
                || command.quantity() > 500) {
            return new ReserveReceipt(
                command.operationId(),
                command.orderId(),
                "REJECTED",
                "QUANTITY_OUT_OF_RANGE");
        }

        // Demo: chưa thực thi mutation kho thật.
        return new ReserveReceipt(
            command.operationId(),
            command.orderId(),
            "RESERVED",
            null);
    }
}
~~~

Điểm chính: phương thức nhận `ReserveCommand` (chính là payload) và trả `ReserveReceipt` (một POJO). Khi được gọi qua Service Activator có khả năng tạo reply, **framework xây một message reply cho giá trị ấy** và chuyển đến reply destination phù hợp.

Trong production, kiểm tra tenant bằng **nguồn đáng tin/authentication**, không dựa vào việc `tenantId` là chuỗi không rỗng. Khi kết quả phụ thuộc tồn kho thực tế, kiểm tại transaction boundary.

## 8. Java DSL: tạo reply có payload trả từ service

Một flow dùng `DirectChannel` để nhận request và `QueueChannel` để xem reply:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ReservationReplyFlowConfiguration {

    @Bean("reservations.requests")
    DirectChannel requests() {
        return new DirectChannel();
    }

    @Bean("reservations.replies")
    QueueChannel replies() {
        return new QueueChannel();
    }

    @Bean
    ReservationService reservationService() {
        return new ReservationService();
    }

    @Bean
    IntegrationFlow reserveWithExplicitReplyChannel(
            ReservationService reservationService) {
        return IntegrationFlow.from("reservations.requests")
            .handle(reservationService, "reserve")
            .channel("reservations.replies")
            .get();
    }
}
~~~

Luồng chạy:

~~~text
request message payload ReserveCommand
  -> reservations.requests (DirectChannel)
  -> service activator calls ReservationService.reserve
  -> reserve returns ReserveReceipt
  -> framework emits reply message
  -> reservations.replies (QueueChannel)
  -> receive() can inspect reply
~~~

### 8.1. `.handle(...)` khác `.channel(...)`

- `.handle(reservationService, "reserve")` gọi phương thức.
- `.channel("reservations.replies")` xác định kênh output được dùng trong flow.
- `QueueChannel` nhận/giữ một message để consumer poll; nó **không** tự động hiểu đó là response cho một Gateway ở channel khác.

### 8.2. Method selection và type conversion

Khi service có nhiều overload hoặc payload không đúng kiểu, method resolution có thể bị lỗi hoặc chọn sai nếu thiết kế thiếu rõ. Ưu tiên:

- Interface/phương thức handler có **kiểu input cụ thể**.
- Chuẩn hóa payload bằng Transformer trước Service Activator.
- Không dùng `Object`/map chung cho mọi command nếu có thể.
- Kiểm thử method invocation, converter và lỗi type mismatch.

Ví dụ `reserve(ReserveCommand)` rõ ràng hơn `reserve(Object)` khi một service chứa nhiều phương thức xử lý.

### 8.3. Một reply không đồng nghĩa một kết quả cuối

Một `QueueChannel` có thể chứa `Message<ReserveReceipt>` chưa được downstream xử lý. Nếu bước tiếp theo là outbound HTTP/Kafka adapter, vẫn có khả năng send failure, duplicate, timeout hoặc consumer crash. Cần phân biệt **return**, **message created**, **message sent** và **business acknowledged**.

## 9. Gateway request–reply: không gán output channel tùy tiện

Trong một ứng dụng Java, người gọi có thể muốn viết:

~~~java
ReserveReceipt receipt = gateway.reserve(command);
~~~

Trong khi thực thi bên dưới là một chuỗi message. **Messaging Gateway** đóng vai trò bridge giữa lời gọi method và request–reply flow.

### 9.1. Định nghĩa gateway interface

~~~java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "reserve.gateway.in")
interface ReservationGateway {

    ReserveReceipt reserve(ReserveCommand command);
}
~~~

Interface có `@MessagingGateway`; Spring Integration cần cơ chế đăng ký/scanning gateway tương ứng trong application context (ví dụ cấu hình có `@IntegrationComponentScan`).

### 9.2. Flow dùng replyChannel từ Gateway

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class ReservationGatewayFlowConfiguration {

    @Bean("reserve.gateway.in")
    DirectChannel inputChannel() {
        return new DirectChannel();
    }

    @Bean
    ReservationService gatewayReservationService() {
        return new ReservationService();
    }

    @Bean
    IntegrationFlow reserveGatewayRequestReply(
            ReservationService service) {
        return IntegrationFlow.from("reserve.gateway.in")
            .handle(service, "reserve")
            // Không chặn đầu ra ở một QueueChannel khác.
            // Endpoint có thể gửi reply về replyChannel của Gateway.
            .get();
    }
}
~~~

Khi gọi `gateway.reserve(...)`, Gateway tạo request message có đường trở về phù hợp. Handler trả `ReserveReceipt`; flow có thể phát reply tới temporary reply channel của Gateway để lời gọi Java nhận kết quả.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as Messaging Gateway
    participant S as Service Activator
    participant R as Temporary replyChannel
    C->>G: reserve(command)
    G->>S: Message<ReserveCommand> + replyChannel
    S-->>R: Message<ReserveReceipt>
    R-->>G: Reply
    G-->>C: ReserveReceipt
~~~

### 9.3. Khi nào caller bị timeout?

- Handler trả `null` hoặc `void` trong luồng kỳ vọng reply.
- Handler gửi reply sang output channel khác mà không bridge trở lại Gateway.
- Một Filter drop request hoặc reply nhưng không tạo rejection result.
- Broker/worker xử lý chậm hơn reply timeout của Gateway.
- Metadata `replyChannel` hoặc correlation bị mất khi đi qua các ranh giới.
- Handler ném exception được xử lý ở một error flow nhưng không có response tương ứng.
- Async reply đến sau khi Gateway đã hết thời gian chờ.

**Timeout không chứng minh business operation thất bại.** Kho có thể đã commit, còn response bị mất. Caller phải giữ **cùng operation ID** khi retry và backend phải hỗ trợ idempotency/reconciliation.

### 9.4. Phân biệt Gateway với output channel tĩnh

| Luồng | Cách lấy kết quả | Ưu tiên thiết kế |
| --- | --- | --- |
| `requests → .handle(service) → replies.queue` | Consumer poll `replies.queue` | Pipeline một chiều có channel output cố định |
| `Gateway → requests → .handle(service)` | Gateway chờ `replyChannel` | Đồng bộ request–reply |
| `Gateway → requests → handler → transform reply` | Gateway nhận DTO đã chuyển | Cần reply Translator sau business service |
| `requests → handler → outbound adapter` | Hệ thống ngoài nhận message/event | Không giả định caller chờ local reply |

Trong một hệ thống, cả bốn topology đều có thể tồn tại. **Chọn theo contract của caller** thay vì luôn gắn một QueueChannel cho mọi return value.

## 10. Khi handler trả `Message<?>` thay vì POJO

Trả POJO thường đơn giản và giúp service ít phụ thuộc vào Spring Messaging. Tuy nhiên, có trường hợp response cần chứa **metadata mới được tính hoặc kiểm soát trực tiếp**.

Ví dụ một Service Activator xử lý `Message<ReserveCommand>` và trả một reply message có các headers business được chọn:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class ReservationReplyMessageService {
    private final ReservationService delegate;

    ReservationReplyMessageService(ReservationService delegate) {
        this.delegate = delegate;
    }

    public Message<ReserveReceipt> reserveWithMetadata(
            Message<ReserveCommand> request) {
        ReserveCommand command = request.getPayload();
        ReserveReceipt receipt = delegate.reserve(command);

        Object correlation = request.getHeaders()
            .get("businessCorrelationId");

        if (!(correlation instanceof String id)
                || id.isBlank()) {
            throw new IllegalArgumentException(
                "BUSINESS_CORRELATION_ID_MISSING");
        }

        return MessageBuilder.withPayload(receipt)
            .setHeader("businessCorrelationId", id)
            .setHeader("operationId", command.operationId())
            .setHeader("targetSchemaVersion", "reserve-receipt-v1")
            .build();
    }
}
~~~

**Lưu ý:** Đây là một return value mang **message rõ ràng**, không còn chỉ là `ReserveReceipt`. Cần kiểm tra behavior thực của endpoint về **request-header propagation, replyChannel và errorChannel**. Đừng chỉ đọc headers của message vừa tạo rồi kết luận **message cuối cùng trên wire** đã được lọc đúng.

### 10.1. Return `Message<?>` có tự bảo toàn replyChannel không?

Không nên đưa ra cam kết tuyệt đối. Tùy handler/endpoint, các headers liên quan reply có thể được framework xử lý/propagate theo rules cụ thể. Nếu **đã cấu hình output channel tĩnh**, response được gửi qua channel đó; nếu muốn Gateway nhận reply, hãy kiểm tra **đường reply của request** ở integration test.

Có thể dùng cách sau cho một pipeline tĩnh:

~~~java
@Bean
IntegrationFlow explicitReplyMessageFlow(
        ReservationReplyMessageService service) {
    return IntegrationFlow.from("reservations.typed.in")
        .handle(service, "reserveWithMetadata")
        .channel("reservations.typed.out")
        .get();
}
~~~

Đây là một **fragment**; cần khai báo `reservations.typed.in/out` và service bean phù hợp khi triển khai. Trong Gateway flow, cần xác minh rằng reply destination cuối cùng vẫn đúng.

### 10.2. Dùng `copyHeaders(...)` có rủi ro

~~~java
// Cần thận trọng: dễ kéo theo metadata không thuộc reply contract.
return MessageBuilder.withPayload(receipt)
    .copyHeaders(request.getHeaders())
    .build();
~~~

Request có thể mang `authorization`, `rawPayload`, tenant header chưa xác thực, `replyChannel` nội bộ hoặc transport delivery metadata. Một reply gửi sang partner khác không nên tự động chứa những thứ này.

Ưu tiên **allowlist**:

~~~text
Business reply headers allowed:
  businessCorrelationId
  operationId
  targetSchemaVersion

Forbidden at external boundary:
  authorization
  cookie
  rawPayload
  internalPrincipal
  MessageChannel object
  broker deliveryTag / internal retry state
~~~

**Mấu chốt:** Không chỉ lọc ở Service Activator. Outbound adapter/header mapper cũng cần chặn headers không được phép rời hệ thống, bởi framework hoặc các endpoint trung gian có thể bổ sung/propagate metadata.

### 10.3. Không lạm dụng `Message<?>` trong domain service

Một domain service có thể trả:

~~~java
ReserveReceipt reserve(ReserveCommand command);
~~~

Sau đó integration layer phụ trách định tuyến và enrich headers. Phân tách này dễ unit test và ít coupling hơn so với bắt mọi domain service phải nhập `org.springframework.messaging.Message`.

Dùng `Message<?>` khi thực sự cần đọc/đặt message metadata ở một điểm tích hợp rõ ràng, chẳng hạn trả reply cho một kênh khác hoặc tạo correlation metadata không nằm trong payload.

## 11. `null`, `void` và requiresReply

Một phương thức Java hoàn toàn có thể trả `null`:

~~~java
final class ReservationLookupService {

    public ReserveReceipt lookup(ReserveCommand command) {
        // Minh họa một kết quả không tìm thấy:
        return null;
    }
}
~~~

Nhưng một caller đang đợi `ReserveReceipt` sẽ không có một business reply thông thường. Nếu flow không có policy rõ, Gateway có thể chờ rồi timeout.

### 11.1. Tránh dùng `null` cho business outcome có nghĩa

Thay vì:

~~~text
lookup returns null
Gateway waits
Gateway times out
Caller guesses reservation does not exist
~~~

Nên trả một kết quả typed:

~~~java
record LookupOutcome(
    String operationId,
    String status,
    String reasonCode
) {}

LookupOutcome lookup(ReserveCommand command) {
    return new LookupOutcome(
        command.operationId(),
        "NOT_FOUND",
        "RESERVATION_NOT_FOUND");
}
~~~

Kết quả có trạng thái `NOT_FOUND` khác hẳn “không có reply vì lỗi tích hợp”. Điều này quan trọng với retry và error reporting.

### 11.2. `requiresReply`: policy khi không có kết quả

Một reply-producing handler có thể hỗ trợ cấu hình **requiresReply** để quy định việc trả `null` được chấp nhận hay không. Khi yêu cầu reply mà không có, handler có thể phát sinh lỗi phù hợp, thay vì để flow im lặng.

Ví dụ **định hướng cấu hình** với `ServiceActivatingHandler`:

~~~java
import org.springframework.integration.handler.ServiceActivatingHandler;

// Service/method lookup() có thể trả null.
ServiceActivatingHandler handler =
    new ServiceActivatingHandler(lookupService, "lookup");

// Bật yêu cầu reply theo handler semantics/version đang dùng.
handler.setRequiresReply(true);

// Gắn handler vào IntegrationFlow hay endpoint phù hợp,
// và kiểm thử error path của phiên bản Spring Integration thực tế.
~~~

Đây là fragment minh họa ranh giới policy, không phải cấu hình chạy độc lập. Khi tích hợp, cần đối chiếu API theo Spring Integration version của dự án và test actual exception/error-channel behavior. **Không tự động retry vô hạn** lỗi “không có reply” nếu service đã trả `null` theo logic cố định.

### 11.3. `void` phù hợp với one-way endpoint

~~~java
final class AuditEventService {

    public void record(AuditEvent event) {
        // Ghi audit, không trả business reply.
    }
}

record AuditEvent(
    String operationId,
    String eventType
) {}
~~~

Một flow có input event và Service Activator trả `void` hợp lý nếu caller **không chờ reply**. Nhưng nếu gọi qua Gateway method trả `ReserveReceipt`, việc dùng cùng one-way handler có thể khiến Gateway timeout.

### 11.4. Dùng `Optional.empty()` để biểu thị no-reply?

Tránh suy luận. `Optional.empty()` không phải `null` trong Java. Tùy converter/handler nó có thể đi qua như payload hoặc được giải mã riêng. Contract nên trả `LookupOutcome(status=NOT_FOUND)`, hoặc quy định rõ cách biểu diễn “không có kết quả” và viết integration test.

## 12. Business rejection nên là reply, không phải ngoại lệ kỹ thuật

Một lệnh giữ hàng có quantity không hợp lệ là một **business/validation rejection**; không có lý do retry cùng payload vô hạn. Service có thể trả:

~~~java
return new ReserveReceipt(
    command.operationId(),
    command.orderId(),
    "REJECTED",
    "QUANTITY_OUT_OF_RANGE");
~~~

Gateway nhận được một reply bình thường và ánh xạ nó sang API response tương ứng. Điều này khác với:

~~~java
throw new IllegalStateException("DATABASE_UNAVAILABLE");
~~~

Lỗi `DATABASE_UNAVAILABLE` là technical/transient; policy có thể retry bounded hoặc gửi sang error channel/DLQ tùy topology.

### 12.1. Ma trận response và failure

| Tình huống | Handler làm gì? | Caller/downstream nhận gì? |
| --- | --- | --- |
| Reserve thành công | Trả `ReserveReceipt(RESERVED)` | Normal reply |
| Quantity không hợp lệ | Trả `ReserveReceipt(REJECTED)` | Typed business rejection |
| Không tìm thấy reservation | Trả `LookupOutcome(NOT_FOUND)` | Typed not-found reply |
| DB timeout | Ném technical exception | Exception/error flow, bounded retry |
| Handler trả null ngoài dự kiến | Không có ordinary reply | Timeout hoặc requiresReply error |
| Handler `void` one-way | Không có ordinary reply | Đúng nếu không chờ response |
| Broker ACK thất bại sau commit | Có thể redelivery | Idempotency/reconciliation, không tạo command mới |

### 12.2. Error channel phụ thuộc topology

Với `DirectChannel` đồng bộ, exception từ service có thể lan về người gửi dưới dạng `MessagingException` hoặc nguyên nhân được bọc. Với poller, executor hoặc inbound broker adapter, lỗi có thể được chuyển thành `ErrorMessage` theo cấu hình endpoint/error channel tương ứng.

**Không** mặc định exception luôn tự chuyển thành một business `ReserveReceipt(REJECTED)`. Muốn caller nhận lỗi có kiểu, cần error mapping/exception translation ở Gateway/boundary.

### 12.3. Đừng swallow exceptions rồi trả success

~~~java
// Anti-pattern: external service có thể chưa commit.
try {
    warehouseApi.reserve(command);
} catch (Exception ignored) {
    return new ReserveReceipt(
        command.operationId(),
        command.orderId(),
        "RESERVED",
        null);
}
~~~

Nếu downstream gọi thất bại, một reply `RESERVED` giả có thể che mất công việc, làm sai saga hoặc thanh toán. Thay vào đó, phân biệt `FAILED_FINAL`, `UNKNOWN` và `RETRYABLE_FAILURE` theo hợp đồng/khả năng reconciliation của hệ thống.

## 13. Threading, timeout và reply đến muộn

`DirectChannel` thường gọi handler trong cùng thread gửi; `ExecutorChannel` và các adapter bất đồng bộ có thể chuyển công việc sang thread/process khác.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant E as Executor/Broker
    participant S as Service
    G->>E: request + reply correlation
    E->>S: async dispatch
    Note over G: Waiting up to reply timeout
    S-->>E: ReserveReceipt
    E-->>G: late/normal reply
~~~

Nếu Gateway hết timeout lúc 5 giây nhưng business service hoàn thành ở giây thứ 7, **timeout của caller không rollback side effect**.

### 13.1. Phải có deadline và late-reply policy

- Gateway send/reply timeout phải theo SLA và topology.
- Một request bất đồng bộ dài có thể trả `ACCEPTED + operationId` trước, sau đó caller poll/webhook thay vì giữ một lời gọi chờ lâu.
- Retry sau timeout phải dùng cùng operation ID để backend không double commit.
- Late reply cần được ghi nhận, đưa vào reconciliation hoặc discard theo policy, không gửi sang request mới.
- Tracing phải nối attempts theo business operation thay vì giả định span ID giữ nguyên.

### 13.2. `replyChannel` chỉ còn có nghĩa nếu có người nhận

Một temporary reply channel có thể không còn hữu dụng sau Gateway timeout. Nếu dùng broker/worker dài, nên có **durable reply destination và correlation registry** phù hợp, không dựa vào Java channel object sống vô hạn.

### 13.3. Async return types phải test trên đúng version

Nếu service method trả `CompletableFuture<ReserveReceipt>`, Reactor type hoặc một callback, Spring Integration version/endpoint phải hỗ trợ cách **chờ hoặc phát reply khi completion xảy ra**. Không mặc định có thể cast một Future thành receipt.

Ví dụ ý tưởng:

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<ReserveReceipt> reserveAsync(
        ReserveCommand request) {
    return CompletableFuture.supplyAsync(
        () -> reservationService.reserve(request));
}
~~~

Đoạn code này minh họa type async, **không** phải lời khuyên tạo unbounded thread pools bằng `supplyAsync` trong production. Cần executor quản lý, cancellation, timeouts, exception mapping và integration tests theo phiên bản framework.

## 14. Retry, broker redelivery và idempotent reply

Service Activator có thể được gọi lại khi:

- `RequestHandlerRetryAdvice` retry handler trong cùng process.
- Gateway/client resend vì response timeout.
- JMS/AMQP/Kafka redeliver record sau crash, rollback, rebalance hoặc ACK/offset thất bại.
- Retry topic, DLQ hay operator phát lại message.
- Một business workflow mới khởi chạy lại với cùng command đã tồn tại.

Trong mọi trường hợp, **cùng business operation** cần giữ `operationId`. Reply có thể xuất hiện nhiều lần nhưng business effect không được commit nhiều lần nếu contract yêu cầu idempotency.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant A as Activator A
    participant W as Warehouse
    participant C as Activator B
    B->>A: ReserveCommand(operationId=RSV-901)
    A->>W: Reserve with stable operation key
    W-->>A: Committed result
    A--xB: ACK/reply lost
    B->>C: Redelivery same operationId
    C->>W: Lookup / reuse outcome
    W-->>C: Existing RESERVED
    C-->>B: Reply + ACK
~~~

### 14.1. Nhiều invocation, một business outcome

~~~text
Number of handler invocations >= Number of committed operations
~~~

Điều cần bảo vệ là **at most one committed business effect per operation key** trong consistency boundary đã định, không phải lời hứa handler chỉ chạy một lần trong mọi failure scenario.

### 14.2. Persisted result để reply lại an toàn

Một business owner có thể lưu:

~~~text
reservation_operation(
  tenant_id,
  operation_id,
  request_fingerprint,
  status,
  stored_result,
  updated_at
)
UNIQUE(tenant_id, operation_id)
~~~

Khi request đến lại:

1. Nếu `COMPLETED`, trả **persisted result**, không reserve thêm.
2. Nếu `IN_PROGRESS`, defer/wait/reconcile theo policy.
3. Nếu cùng key nhưng payload có ý nghĩa khác, trả `IDEMPOTENCY_CONFLICT`.
4. Nếu chưa có, claim một operation nguyên tử tại nơi commit mutation.
5. Nếu external service có thể đã commit nhưng response mất, phải có idempotency **ở đích** hoặc status lookup/reconciliation.

Một duplicate request có thể nhận **một reply message mới** chứa kết quả đã lưu. Đó không phải là một side effect mới.

### 14.3. Transaction và thời điểm phát reply

Một service `@Transactional` có thể trả object trước khi transaction proxy commit; nếu commit thất bại, caller phải được báo lỗi chứ không nhận success giả. Đảm bảo response `RESERVED` phản ánh outcome đã chốt, không chỉ nghĩa “đã đưa request vào queue”.

### 14.4. Outbox sau business commit

~~~text
BEGIN TRANSACTION
  claim operation key
  reserve stock
  persist ReserveReceipt
  insert outbox event StockReserved
COMMIT

Outbox publisher:
  publish event; retry after send failure
  event may be delivered more than once
~~~

Outbox giúp không mất thông báo sau commit nhưng **không bảo đảm broker chỉ giao một lần**. Subscriber của event và Aggregator cần idempotency của riêng chúng.

## 15. Reply và correlation trong Splitter–Aggregator

Một batch có ba child messages:

~~~text
executionId = RUN-901-A
expected childIds = LINE-1, LINE-2, LINE-3

LINE-1 -> Service Activator -> RESERVED reply
LINE-2 -> Service Activator -> REJECTED reply
LINE-3 -> Service Activator -> RESERVED reply
~~~

Aggregator cần biết những replies **thuộc nhóm nào**, **child nào đã có kết quả** và **khi nào được release**.

| Key | Mục đích | Ví dụ |
| --- | --- | --- |
| `executionId` | Group correlation cho một workflow run | `RUN-901-A` |
| `lineId` / `childId` | Nhận diện một phần duy nhất | `LINE-2` |
| `operationId` | Chặn side effect trùng | `RSV-901-LINE-2` |
| `businessCorrelationId` | Trace các bước của cùng đơn | `ORD-901` |
| Spring Message ID | Nhận diện một envelope | UUID |

### 15.1. Handler trả `null` có thể khiến group thiếu phần

~~~text
LINE-1 -> ReserveReceipt
LINE-2 -> null (no ordinary reply)
LINE-3 -> ReserveReceipt
Aggregator -> receives 2/3; may wait until timeout
~~~

Nếu LINE-2 bị business rejection, phát một **typed child outcome**:

~~~java
record LineOutcome(
    String executionId,
    String lineId,
    String operationId,
    String status,
    String reasonCode
) {}
~~~

Như vậy Aggregator có thể nhận đủ ba **unique child outcomes** rồi trả batch status `PARTIAL/FAILED` theo policy. Đủ replies không đồng nghĩa tất cả thành công.

### 15.2. Duplicate và late replies

Nếu LINE-1 bị giao lại:

~~~text
LINE-1 RESERVED
LINE-1 RESERVED (duplicate)
LINE-3 RESERVED
~~~

`group.size() == 3` không chứng minh LINE-2 đã có kết quả. Release strategy cần kiểm tập `lineId` duy nhất tương ứng expected IDs.

Nếu group đã hoàn thành mà reply đến trễ, không nên tạo group mới rồi phát kết quả cuối thứ hai khi contract chỉ cho phép một finalization. Cần closed-execution state/tombstone và finalizer idempotent.

### 15.3. Header correlation không tự sinh đúng bằng business field

Khi handler trả POJO, đừng giả định framework tự lấy `executionId` trong payload và tạo group key header phù hợp. Nếu downstream Aggregator dựa vào header, hãy truyền/derive metadata đã kiểm ở bước thích hợp và test output. Nếu reply qua broker, header mappers có thể đổi kiểu hoặc loại trường.

## 16. Khi service trả một danh sách hoặc async type

Một Service Activator trả `List<ReserveReceipt>` **không tự động đồng nghĩa** phát N reply messages. Collection có thể là payload của **một** message, tùy handler.

### 16.1. Một reply chứa cả batch

~~~java
record BatchReserveResult(
    String executionId,
    java.util.List<ReserveReceipt> results
) {}
~~~

Một Gateway gọi batch và nhận `BatchReserveResult` là contract rõ.

### 16.2. Muốn từng child được xử lý độc lập

~~~text
BatchReserveCommand
  -> Splitter: N child commands
  -> Service Activator per child: ReserveReceipt
  -> Aggregator: BatchReserveResult
~~~

Không trông chờ một return type `List<?>` tự kích hoạt Splitter nếu topology chưa cấu hình.

### 16.3. Reactive/stream return type

Một method trả `Stream<T>`, `Flux<T>` hoặc `Publisher<T>` có thể có behavior đặc biệt theo endpoint và version. Phải quyết định **một batch reply** hay **N child replies** rồi kiểm thử trên framework version thực, thay vì suy đoán tự động.

## 17. Request–reply qua HTTP, JMS, AMQP và Kafka

Trong JVM, `replyChannel` có thể là object hoặc routing metadata nội bộ. Qua transport, reply destination phải có biểu diễn và quyền truy cập theo giao thức.

| Transport | Ranh giới cần thiết kế | Lưu ý |
| --- | --- | --- |
| HTTP | Response status/body, request timeout | HTTP 200 không chứng minh async downstream đã commit |
| AMQP/RabbitMQ | Reply queue, correlation, ACK/NACK, DLQ | Header mapper và redelivery |
| JMS | `JMSReplyTo`, `JMSCorrelationID`, session TX/ACK | Không serialize Java channel object |
| Kafka | Request/reply topics, record key, correlation headers | Offset/rebalance không thay business ID |
| Internal DirectChannel | Dispatch đồng bộ ở caller thread | Exception có thể propagate |
| ExecutorChannel | Thread khác, local reply routing | Deadline và late reply policy |

### 17.1. JMSCorrelationID không tự đồng nghĩa operationId

JMS hỗ trợ `JMSMessageID/JMSCorrelationID` để định tuyến request–reply. `operationId` là business ID. Chúng chỉ có thể trùng khi **hợp đồng đã chủ động chọn**, không mặc định tương đương.

### 17.2. Kafka offset không phải reply identity

Một record có topic/partition/offset; republish sang retry topic làm offset đổi. Request và reply cần correlation contract ổn định và registry/timeout phù hợp. Idempotency ở business owner vẫn dùng operation key, không dựa vào offset.

### 17.3. Không gửi Java channel object qua broker

Outbound adapter cần loại hoặc chuyển `replyChannel`/`errorChannel` có kiểu không serializable. Reply address ở broker phải nằm trong ACL/allowlist, không để bên ngoài chỉ định tùy ý nơi nhận dữ liệu nội bộ.

## 18. Unit test: business method trả typed reply

Kiểm method Java trước để tách bug nghiệp vụ khỏi bug messaging.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ReservationServiceTest {

    private final ReservationService service =
        new ReservationService();

    private static ReserveCommand command(int quantity) {
        return new ReserveCommand(
            "shop-a", "RSV-901", "ORD-901",
            "BOOK-42", quantity);
    }

    @Test
    void acceptedCommandReturnsReceipt() {
        ReserveReceipt receipt = service.reserve(command(2));

        assertEquals("RSV-901", receipt.operationId());
        assertEquals("ORD-901", receipt.orderId());
        assertEquals("RESERVED", receipt.status());
        assertNull(receipt.reasonCode());
        assertTrue(receipt.accepted());
    }

    @Test
    void invalidQuantityIsTypedBusinessRejection() {
        ReserveReceipt receipt = service.reserve(command(-3));

        assertEquals("REJECTED", receipt.status());
        assertEquals(
            "QUANTITY_OUT_OF_RANGE",
            receipt.reasonCode());
        assertFalse(receipt.accepted());
    }
}
~~~

Những tests này **chưa chứng minh** Spring Integration tạo reply message hoặc trả đúng channel. Chúng chỉ kiểm nội dung mà Service Activator sẽ nhận làm return value.

## 19. Integration test: return value thành message reply

Sử dụng `ReservationReplyFlowConfiguration` ở phần 8; `DirectChannel` chuyển message tới handler đồng bộ, còn `QueueChannel` giúp test nhận output.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ReservationReplyFlowConfiguration.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReservationReplyFlowTest {

    @Autowired @Qualifier("reservations.requests")
    MessageChannel input;

    @Autowired @Qualifier("reservations.replies")
    PollableChannel output;

    private static ReserveCommand command(int quantity) {
        return new ReserveCommand(
            "shop-a", "RSV-901", "ORD-901",
            "BOOK-42", quantity);
    }

    @Test
    void returnValueBecomesReplyPayload() {
        Message<ReserveCommand> request =
            MessageBuilder.withPayload(command(2))
                .setHeader("businessCorrelationId", "ORD-901")
                .build();

        assertTrue(input.send(request));

        Message<?> response = output.receive(1000);
        assertNotNull(response);
        assertInstanceOf(
            ReserveReceipt.class, response.getPayload());

        ReserveReceipt receipt =
            (ReserveReceipt) response.getPayload();

        assertEquals("RSV-901", receipt.operationId());
        assertEquals("RESERVED", receipt.status());
        assertNull(output.receive(0),
            "A request should yield one normal reply in this demo");
    }

    @Test
    void businessRejectionStillProducesReply() {
        assertTrue(input.send(MessageBuilder
            .withPayload(command(0))
            .build()));

        Message<?> response = output.receive(1000);
        assertNotNull(response);
        assertInstanceOf(
            ReserveReceipt.class, response.getPayload());

        ReserveReceipt receipt =
            (ReserveReceipt) response.getPayload();

        assertEquals("REJECTED", receipt.status());
        assertEquals(
            "QUANTITY_OUT_OF_RANGE",
            receipt.reasonCode());
        assertNull(output.receive(0));
    }
}
~~~

Điều test chứng minh:

- `.handle(service, "reserve")` gọi đúng method từ request payload.
- Return value kiểu `ReserveReceipt` được chuyển thành **payload của reply message**.
- Reply tới **kênh output được cấu hình**.
- Lỗi nghiệp vụ terminal được biểu diễn bằng reply typed, không phải `null`.
- Một request demo sinh đúng một output ở thời điểm quan sát.

**Giới hạn:** `receive(0)` kiểm queue ở thời điểm test. Nếu có ExecutorChannel, broker hoặc retry bất đồng bộ, cần bounded await, đồng bộ hóa và kiểm số business commits. Test này cũng không chứng minh Warehouse DB đã commit.

## 20. Test Gateway: caller nhận object trả về

Dùng `ReservationGatewayFlowConfiguration` và `ReservationGateway` ở phần 9.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ReservationGatewayFlowConfiguration.class)
class ReservationGatewayFlowTest {

    @Autowired
    ReservationGateway gateway;

    @Test
    void gatewayMethodGetsReplyFromServiceActivator() {
        ReserveReceipt receipt = gateway.reserve(
            new ReserveCommand(
                "shop-a", "RSV-901", "ORD-901",
                "BOOK-42", 2));

        assertNotNull(receipt);
        assertEquals("RESERVED", receipt.status());
        assertEquals("RSV-901", receipt.operationId());
    }
}
~~~

Đoạn test dùng `@SpringJUnitConfig` để dựng context và Gateway interface được component-scan. Trong dự án thật, cấu hình component scan phải thấy interface `@MessagingGateway`. Nếu Gateway không được khởi tạo, đó là lỗi wiring, không phải “business service trả null”.

### 20.1. Negative test: output channel bắt reply của Gateway

Một cấu hình sai thường gặp:

~~~text
Gateway -> request channel -> Service Activator
    |
    +-- handler output configured to audit.queue
         (Gateway temporary replyChannel never gets the receipt)
~~~

Một test nên:

1. Gọi Gateway có reply timeout hữu hạn.
2. Giả lập flow gửi reply vào sai output channel.
3. Assert Gateway **không** nhận business receipt như mong muốn.
4. Sau khi sửa flow/bridge, assert Gateway nhận đúng receipt.

Đừng triển khai test timeout vô hạn; đặt bounded timeout để build không treo.

### 20.2. Negative test: handler trả null

Một method trả `null` trong flow request–reply cần được kiểm như contract riêng:

~~~text
request: known operation
handler: returns null
requiresReply=false -> no ordinary reply; Gateway may time out
requiresReply=true  -> missing-reply error according to handler config
~~~

Test trên Spring Integration version của dự án phải xác minh exception/wrapping và đường error. Không đồng nhất một Java `null` với `ReserveReceipt(status=NOT_FOUND)`.

## 21. Test explicit `Message<?>` và metadata

Dùng `ReservationReplyMessageService` ở phần 10 để xác minh reply chỉ có metadata được chủ động chọn ở lớp integration.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class ReservationReplyMessageServiceTest {

    private final ReservationReplyMessageService service =
        new ReservationReplyMessageService(
            new ReservationService());

    @Test
    void createsBusinessReplyMessageWithAllowedHeaders() {
        ReserveCommand command = new ReserveCommand(
            "shop-a", "RSV-901", "ORD-901",
            "BOOK-42", 2);

        Message<ReserveCommand> input =
            MessageBuilder.withPayload(command)
                .setHeader(
                    "businessCorrelationId", "ORD-901")
                .setHeader("authorization", "Bearer not-for-output")
                .setHeader("rawPayload", "confidential")
                .build();

        Message<ReserveReceipt> reply =
            service.reserveWithMetadata(input);

        assertEquals("RESERVED", reply.getPayload().status());
        assertEquals("ORD-901",
            reply.getHeaders().get("businessCorrelationId"));
        assertEquals("RSV-901",
            reply.getHeaders().get("operationId"));
        assertEquals("reserve-receipt-v1",
            reply.getHeaders().get("targetSchemaVersion"));
        assertNull(reply.getHeaders().get("authorization"));
        assertNull(reply.getHeaders().get("rawPayload"));
    }

    @Test
    void missingBusinessCorrelationFailsClearly() {
        ReserveCommand command = new ReserveCommand(
            "shop-a", "RSV-902", "ORD-902",
            "BOOK-42", 2);

        Message<ReserveCommand> input =
            MessageBuilder.withPayload(command).build();

        IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> service.reserveWithMetadata(input));

        assertEquals(
            "BUSINESS_CORRELATION_ID_MISSING",
            error.getMessage());
    }
}
~~~

**Quan trọng:** Test này kiểm **method trả Message**. Nó chưa chứng minh Service Activator endpoint hoặc outbound adapter không propagate thêm một header lạ. Nên có integration test kiểm message **sau endpoint**, và contract test kiểm **serialized headers trên wire** khi publish sang bên ngoài.

## 22. Ma trận kiểm thử tổng hợp

| Kịch bản | Điều cần assert |
| --- | --- |
| Handler trả `ReserveReceipt` | Output là `Message<ReserveReceipt>`, payload đúng |
| Handler trả `String` | Reply chứa string theo contract |
| Handler trả `Message<Receipt>` | Metadata được phép, không leak secret |
| Handler trả `null` | No-reply hoặc missing-reply error đúng cấu hình |
| Handler trả `void` | One-way flow không đợi reply |
| Gateway gọi sync, có reply | Java method nhận đúng receipt |
| Gateway output bị route sai | Test phát hiện timeout/misrouting |
| Business rejection | Có typed `REJECTED` reply, không retry vô hạn |
| Handler ném transient exception | Bounded retry/backoff/error path |
| Handler ném authorization error | Không retry nhằm bypass quyền |
| ReplyChannel bị mất qua Transformer | Test bắt được reply không tới caller |
| Content type cũ sau translate | Adapter serialize target type đúng |
| Async service vượt deadline | Late reply được reconcile/discard đúng |
| Multiple child replies | Group theo execution, đếm unique child |
| Duplicate child reply | Không release sớm hoặc phát hai final outcomes |
| Null child reply | Không để Aggregator chờ không kiểm soát |
| Commit thành công, ACK mất | Redelivery cùng operationId, không double mutation |
| Outbox publisher retry | Consumer idempotent với event/result |
| External broker reply-to | Address được allowlist/ACL |
| Header nhạy cảm trong request | Không lọt vào external reply |
| Schema v1/v2 reply | Response Translator/contract mapping đúng |
| Operation ID bị đổi khi retry | Test báo lỗi, không sinh command mới |
| Rate limit/timeout | Không tạo retry storm hoặc thread leak |

**Một bài test chỉ assert “có reply” là chưa đủ.** Cần kiểm **reply được gửi đúng caller, đúng business identity, đúng schema và không tạo thêm side effect**.

## 23. Observability: phân biệt return, reply sent và outcome

Để điều tra lỗi “service đã chạy nhưng Gateway vẫn timeout”, đừng chỉ log `handler completed`. Cần quan sát từng giai đoạn:

~~~text
request accepted
  -> handler invoked
  -> return value produced
  -> reply message constructed
  -> reply destination resolved
  -> reply send attempted
  -> caller received reply / timed out
  -> downstream business effect confirmed
~~~

### 23.1. Những metrics nên có

| Signal | Trả lời câu hỏi nào? |
| --- | --- |
| `service_activator_invocations_total` | Handler đã được gọi bao nhiêu lần? |
| `service_activator_success_total` | Có return value hợp lệ không? |
| `service_activator_null_return_total` | Bao nhiêu lời gọi không trả ordinary reply? |
| `service_activator_exception_total` | Loại lỗi nào ném ra? |
| `reply_created_total` | Bao nhiêu reply messages được chuẩn bị? |
| `reply_send_failed_total` | Gửi reply vào channel/adapter thất bại bao nhiêu? |
| `gateway_reply_timeout_total` | Bao nhiêu caller hết thời gian chờ? |
| `reply_latency` | Độ trễ từ request đến reply? |
| `late_reply_total` | Bao nhiêu reply đến sau deadline? |
| `business_rejection_total` | Bao nhiêu typed REJECTED replies? |
| `business_effect_committed_total` | Bao nhiêu mutation thực sự commit? |
| `idempotency_reused_total` | Bao nhiêu replies dùng persisted outcome? |
| `aggregator_duplicate_reply_total` | Bao nhiêu duplicate child outcomes? |
| `error_channel_messages_total` | Bao nhiêu technical errors đi error flow? |

Tên metrics là **gợi ý cho ứng dụng**, không phải tuyên bố Spring Integration tự phát tất cả những metric này. Có thể dùng Micrometer/observation instrumentation và bổ sung business metrics.

### 23.2. Log mẫu một request–reply thành công

~~~json
{
  "event": "service_activator_reply_produced",
  "flow": "reserve-stock",
  "operationId": "RSV-901",
  "businessCorrelationId": "ORD-901",
  "replyType": "ReserveReceipt",
  "replyStatus": "RESERVED",
  "delivery": "internal-reply-channel"
}
~~~

Đây là **application log schema minh họa**. Không log JWT, raw payment data, thông tin cá nhân hoặc toàn bộ message headers. `operationId`/`businessCorrelationId` có cardinality cao: không đưa chúng vào time-series metric labels tùy ý; chỉ ghi ở log/trace được phân quyền theo retention.

### 23.3. Đo đúng ranh giới

Một bộ chỉ số có thể trông như:

~~~text
handler_invocations = 1200
reply_messages_sent = 1190
gateway_timeouts    = 10
business_effects    = 970
idempotency_reused  = 220
~~~

Các con số này chỉ minh họa. Số reply có thể khác số side effects vì business rejection, retry, duplicate và no-reply one-way. Không tự suy `handler_invocations - reply_messages_sent` là số đơn bị mất nếu chưa xem topology.

### 23.4. Khi debugging reply timeout

Đi theo thứ tự:

1. **Input vào đúng channel?** Gateway có thể gửi sang channel không có consumer.
2. **Handler có được gọi?** Kiểm method binding/conversion.
3. **Return value là gì?** POJO, Message, null, Future hay exception?
4. **Có output channel cố định?** Nó có đang “nuốt” reply của Gateway không?
5. **Header `replyChannel` có tồn tại ở bước cần thiết?** Có bị Transformer/Header Filter thay đổi không?
6. **Có async boundary?** Gateway timeout trước khi handler xong không?
7. **Có lỗi send/serialization?** Reply chứa Java object không truyền được qua broker không?
8. **Business operation đã commit?** Nếu có, phải reconcile và retry bằng same operation ID.

## 24. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Nghĩ method trả POJO thì Gateway chắc chắn có reply | Timeout khi sai channel | Vẽ và test reply path end-to-end |
| Gắn output channel tĩnh rồi quên temporary replyChannel | Gateway không nhận kết quả | Chọn topology/bridge rõ |
| Trả `null` để biểu thị NOT_FOUND | Caller đợi, timeout | Typed `LookupOutcome(NOT_FOUND)` |
| Dùng `void` trong flow yêu cầu reply | Không có normal reply | Tách one-way và request–reply |
| Không cấu hình/kiểm `requiresReply` | Mất reply âm thầm | Chọn policy và test no-reply |
| Trả `Optional.empty()` rồi giả định không có reply | Behavior mơ hồ theo converter | Contract typed outcome |
| Catch mọi exception và trả `RESERVED` | Báo success giả khi downstream lỗi | Error/retry/reconciliation rõ |
| Business rejection bằng exception retryable | Retry storm với input sai | Typed rejection hoặc terminal error |
| Dùng `MessageHeaders.ID` làm idempotency | Redelivery tạo operation mới | Stable business operation key |
| Gọi external API không idempotent trong retryable handler | Double charge/reserve | Backend idempotency/transaction |
| Copy toàn bộ headers vào reply gửi ra ngoài | Rò token/PII và control metadata | Header allowlist tại outbound |
| Xóa `replyChannel` không có kế hoạch | Caller không biết lấy reply ở đâu | Preserve/resolve đúng boundary |
| Serialize `MessageChannel` qua broker | Lỗi codec hoặc lộ topology | Transport reply destination |
| Đồng nhất `errorChannel` với replyChannel | Sai lỗi/response semantics | Error mapping riêng |
| Trả `List<T>` mà mong N replies | Aggregator/consumer nhận sai payload | Splitter rõ hoặc batch reply DTO |
| Trả `CompletableFuture<T>` và mong framework luôn tự unwrap | Caller nhận sai type/timeout | Kiểm async handler support theo version |
| Dùng `group.size()` để release khi có duplicate replies | Release thiếu child | Unique child IDs và expected set |
| Filter drop một child outcome | Aggregator chờ vô hạn | Typed `LineOutcome(REJECTED)` |
| Reply đến sau timeout tự động coi thất bại | Có thể side effect đã commit | Late-reply reconciliation |
| Chỉ test method Java | Không bắt lỗi wiring/channels | Spring context + Gateway/transport tests |
| Chỉ assert payload, không kiểm headers | Mất correlation hoặc rò dữ liệu | Test metadata cả chiều có/không |
| Log toàn bộ headers để debug | Lộ secrets, cardinality cao | Structured minimal logs |

## 25. Checklist triển khai

- [ ] Xác định Service Activator là **one-way** hay **request–reply**.
- [ ] Method input type và output type có contract rõ; tránh ambiguous overload.
- [ ] Payload/headers được validate ở đúng trust boundary trước handler.
- [ ] Nếu trả POJO, đã kiểm framework tạo reply message và giữ metadata cần thiết.
- [ ] Nếu trả `Message<?>`, có allowlist headers và không tự động leak secrets.
- [ ] Nếu trả `null`/`void`, policy no-reply và caller expectations được kiểm rõ.
- [ ] Có chiến lược `requiresReply`/Gateway timeout phù hợp.
- [ ] Không nhầm output channel tĩnh với dynamic request `replyChannel`.
- [ ] ReplyDestination/Gateway temporary channel được kiểm end-to-end.
- [ ] Error channel và business rejection có contract riêng.
- [ ] Async boundary có deadline, late reply handling, cancellation/reconciliation.
- [ ] Correlation ID/operation ID/execution ID không bị trộn chức năng.
- [ ] Handler có side effect được bảo vệ bởi idempotency theo business operation.
- [ ] Retryable/terminal error policy có backoff, giới hạn attempts và alert.
- [ ] Sau commit, event/reply có đường delivery/recovery phù hợp (outbox khi cần).
- [ ] Splitter/Aggregator nhận typed child outcomes, không chờ thiếu vì null/drop.
- [ ] Group release dựa trên unique child IDs; duplicate/late reply có policy.
- [ ] Header mapping qua HTTP/JMS/AMQP/Kafka được kiểm tra bằng contract tests.
- [ ] Không serialize Java replyChannel/errorChannel object ra external transport.
- [ ] Unit tests kiểm service return value, cả accepted và rejected.
- [ ] Integration tests kiểm MessageChannel và Gateway trả kết quả thật.
- [ ] Tests chứng minh những nhánh không được chọn không tạo side effects.
- [ ] Đo handler invocation, reply send, gateway timeout và committed outcome riêng.
- [ ] Mọi logs/metrics tuân thủ quyền, data minimization và retention.

## 26. Bài tập thực hành

Một hệ thống bán vé có `TicketReservationGateway` nhận `ReserveSeatCommand`. Mỗi command mang `tenantId`, `operationId`, `eventId`, `seatId`, `executionId` và `businessCorrelationId`. Nó gọi Service Activator thực hiện giữ ghế, có thể trả:

- `SeatReservationReceipt(status="RESERVED")`.
- `SeatReservationReceipt(status="SEAT_UNAVAILABLE")`.
- Technical error khi DB không khả dụng.
- Timeout sau khi DB đã commit nhưng Gateway chưa nhận reply.

**Yêu cầu:**

1. Thiết kế records `ReserveSeatCommand` và `SeatReservationReceipt`, phân biệt request identity với reply/status.
2. Tạo một method `reserve(command)` trả `SeatReservationReceipt`, không trả `null` khi ghế đã được đặt.
3. Vẽ flow `MessagingGateway → request channel → Service Activator → replyChannel → caller`.
4. Viết Java DSL cho một flow có output channel tĩnh để test qua QueueChannel.
5. Viết biến thể Gateway flow không làm mất dynamic `replyChannel`.
6. Tạo method trả `Message<SeatReservationReceipt>` có `businessCorrelationId` và `operationId` được kiểm tra.
7. Liệt kê headers phải bị loại khi reply qua HTTP/JMS/Kafka, đặc biệt Authorization và channel objects.
8. Giải thích `requiresReply` có ích thế nào nếu handler bất ngờ trả `null`.
9. Phân biệt `SEAT_UNAVAILABLE` typed reply với technical exception; chọn retry policies khác nhau.
10. Tạo JUnit test cho method return và integration test chứng minh Java return được wrap vào Spring reply message.
11. Tạo Gateway integration test khẳng định caller nhận receipt trong thời hạn chờ.
12. Cố tình cấu hình sai output channel rồi kiểm tra Gateway timeout; sửa topology.
13. Giả lập hai request cùng `operationId` do redelivery; database chỉ được giữ ghế một lần dù có hai replies.
14. Thiết kế outbox nếu cần publish `SeatReserved` sau DB commit, mô tả duplicate event handling.
15. Với batch năm ghế, một seat unavailable, dùng typed `LineOutcome` để Aggregator không treo.
16. Chọn metrics cho handler calls, reply sends, timeouts, duplicate operations và late replies.
17. Với `CompletableFuture`/async worker, nêu chính sách deadline và bảo toàn correlation qua thread/broker.
18. Giải thích vì sao không nên dùng Kafka offset hoặc Spring Message ID làm operationId.

**Gợi ý:** Test phải chứng minh ba điều **độc lập**: (1) method tạo business outcome đúng, (2) Service Activator gửi reply đúng channel/Gateway, (3) business side effect không bị lặp khi retry/redelivery.

## 27. Tổng kết

**Return value thành reply message** là một cơ chế cốt lõi của Service Activator trong Spring Integration. Khi method trả một POJO/record, reply-producing handler có thể tạo message với payload là giá trị đó; khi trả `Message<?>`, method tham gia kiểm soát metadata. Ngược lại, `null`/`void` không tạo ordinary reply và có thể làm Gateway timeout nếu không có no-reply policy. Một business rejection có ý nghĩa nên được biểu diễn bằng **typed outcome**, không bị nhầm với lỗi kỹ thuật.

Đường reply cần được thiết kế tường minh: **output channel cố định** cho pipeline hoặc **`replyChannel` của Gateway** khi caller chờ kết quả. Các headers correlation, operation, execution, reply/error routing chỉ nên đi qua những boundary cần thiết và được kiểm soát theo transport. Với retry/redelivery, handler có thể chạy lại nhiều lần, nhưng nghiệp vụ cần idempotency ở nơi commit; với Splitter/Aggregator, replies cần đúng group và unique child ID. Kết hợp Java DSL, Gateway, error handling, tests và observability để đạt mục tiêu: **return value đúng, reply đi đúng nơi, caller hiểu đúng outcome và side effect không bị nhân đôi**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Service Activator, Request-Reply, Correlation Identifier, Idempotent Receiver, Aggregator); Spring Integration Reference về Service Activator, Message Handlers, Java DSL, Gateways, Request–Reply, Error Handling, Message Channels, Retry Advice và Testing; Spring Messaging API về `Message`, `MessageHeaders`, `MessageBuilder`; Spring Framework Transaction Management; Java SE về records và `CompletableFuture`.








