# Gateway default request channel

> **Chương:** Messaging gateway  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này tập trung vào **`defaultRequestChannel` của Messaging Gateway: nơi lời gọi Java được chuyển thành request message và bắt đầu đi qua integration flow**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Messaging Gateway là cầu nối giữa **lời gọi phương thức Java** và **hệ thống message**, không phải một HTTP API Gateway hay một MessageChannel thông thường.
2. Phân biệt `defaultRequestChannel` với `defaultReplyChannel`, `replyChannel` của request, outbound adapter và channel được cấu hình trong Java DSL.
3. Khai báo `@MessagingGateway(defaultRequestChannel = "...")`, định nghĩa bean channel tương ứng và nối tới Spring Integration flow.
4. Biết khi nào phương thức có `@Gateway(requestChannel = "...")` **ghi đè** request channel mặc định của interface.
5. Thiết kế luồng **request–reply** có `Service Activator` trả kết quả về Gateway, không vô tình định tuyến reply vào một channel không ai trả về.
6. Phân tích tác động của `DirectChannel`, `ExecutorChannel` và `QueueChannel` tới threading, send timeout, reply timeout, poller và throughput.
7. Xử lý method `void`, typed business rejection, lỗi kỹ thuật, error channel, retry, idempotency và redelivery mà không suy đoán sai trạng thái commit.
8. Viết kiểm thử JUnit cho default routing, method-level override, no-subscriber/missing-poller, reply destination và nguy cơ xử lý trùng.

## 2. Tình huống: một service Java gọi hai loại luồng đặt hàng

Một ứng dụng có hai nhu cầu: xử lý lệnh giữ hàng thông thường và gửi lệnh ưu tiên. Lớp gọi chỉ muốn một API Java:

~~~java
ReserveReceipt normal = reservationGateway.reserve(command);
ReserveReceipt priority = reservationGateway.reservePriority(command);
~~~

Ứng dụng **không muốn** controller/business caller phải biết cách tạo `Message`, chọn Spring `MessageChannel`, hoặc tự thao tác với `replyChannel`.

Messaging Gateway giải quyết phần chuyển đổi này:

~~~mermaid
flowchart LR
    CALL["Java caller"] --> GW["ReservationGateway proxy"]
    GW --> D{"Method-level requestChannel?"}
    D -->|"Không"| DEF["reservations.commands (default)"]
    D -->|"Có: priority"| PRI["reservations.priority"]
    DEF --> H1["Service Activator: reserve"]
    PRI --> H2["Service Activator: reservePriority"]
    H1 --> REP["Reply to caller"]
    H2 --> REP
~~~

Cấu hình cốt lõi:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "reservations.commands",
    defaultReplyTimeout = "3000")
interface ReservationGateway {

    // Kế thừa defaultRequestChannel của interface.
    ReserveReceipt reserve(ReserveCommand command);

    // Method cụ thể có request channel riêng.
    @Gateway(requestChannel = "reservations.priority")
    ReserveReceipt reservePriority(ReserveCommand command);
}
~~~

**Điểm quan trọng:** `defaultRequestChannel` không quyết định cách **reply** quay về. Nó chỉ xác định **request được gửi vào đâu** khi method không chỉ định request channel riêng.

## 3. Messaging Gateway khác một service thông thường thế nào?

Trong mã Java, Gateway trông giống interface. Ở runtime, Spring Integration tạo một **proxy** nhận method invocation, chuyển arguments thành message, gửi tới request channel và (nếu method cần giá trị trả về) chờ reply theo cấu hình.

~~~text
gateway.reserve(command)
    |
    v
Gateway proxy
    |  creates Message<ReserveCommand>
    |  selects request channel
    v
reservations.commands
    |
    v
IntegrationFlow / Service Activator
    |  returns ReserveReceipt
    v
reply routing
    |
    v
Gateway maps reply payload to ReserveReceipt
    |
    v
Java caller resumes
~~~

### 3.1. Phân biệt bốn khái niệm

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| **Gateway interface** | API Java cho application code | `ReservationGateway.reserve(...)` |
| **Default request channel** | Đích gửi **request** của method nếu không override | `reservations.commands` |
| **IntegrationFlow input** | Channel/endpoint **nhận** và xử lý message | `IntegrationFlow.from("reservations.commands")` |
| **Reply destination** | Nơi **response** quay lại Gateway | Temporary `replyChannel` hoặc cấu hình hợp lệ khác |

Một chương trình có thể cấu hình đúng `defaultRequestChannel` mà vẫn **timeout khi chờ reply** nếu flow không tạo kết quả hoặc định tuyến sai.

### 3.2. Gateway không phải Spring MVC controller

`@MessagingGateway` là **Messaging Gateway** trong Spring Integration, khác với:

- HTTP API Gateway hoặc reverse proxy nằm trước các microservices.
- Spring MVC `@RestController` nhận HTTP request.
- Outbound Gateway gọi HTTP/JMS/AMQP một dịch vụ ngoài.
- `Service Activator` trực tiếp gọi phương thức nghiệp vụ.

Có thể nối các thành phần này thành một chuỗi, nhưng `defaultRequestChannel` nói về **MessageChannel trong Spring application context**, không phải URL.

### 3.3. Không nhầm `@MessagingGateway` và `IntegrationFlow.gateway(...)`

Spring Integration còn có khái niệm gateway endpoint trong Java DSL để làm **request–reply subflow** bên trong một IntegrationFlow. Bài này tập trung vào **interface-level Messaging Gateway** và thuộc tính `defaultRequestChannel` của annotation.

Hai cách có liên hệ về ý tưởng request–reply nhưng **không thay thế cú pháp trực tiếp cho nhau**. Khi xem tài liệu framework, cần xác định đang đọc phần interface Gateway hay gateway endpoint trong DSL.

## 4. `defaultRequestChannel` là gì?

`@MessagingGateway(defaultRequestChannel = "reservations.commands")` đặt **request channel mặc định cho các gateway methods trong interface**.

Nếu một method không có khai báo request channel riêng, Gateway dùng channel này làm nơi gửi message đã tạo từ lời gọi.

### 4.1. Sơ đồ phân giải request channel

~~~mermaid
flowchart TD
    INV["Invoke gateway method"] --> M{"Method có @Gateway(requestChannel)?"}
    M -->|"Có"| O["Sử dụng method requestChannel"]
    M -->|"Không"| D{"Interface defaultRequestChannel?"}
    D -->|"Có"| DEF["Sử dụng defaultRequestChannel"]
    D -->|"Không"| MISS["Cần cấu hình request destination hợp lệ"]
    O --> SEND["Send request message"]
    DEF --> SEND
    MISS --> ERR["Configuration / invocation failure"]
~~~

**Quy tắc ưu tiên thực hành:** request channel được chỉ định tại **method** có tác dụng cho method đó; methods khác vẫn kế thừa default của interface. Không tự suy rằng override ở một method thay đổi toàn bộ Gateway.

### 4.2. Thuộc tính không làm channel tự xuất hiện

Khai báo tên `"reservations.commands"` không thay thế việc có **một destination hợp lệ**. Trong ví dụ, ta chủ động khai báo bean channel:

~~~java
@Bean("reservations.commands")
DirectChannel reservationCommands() {
    return new DirectChannel();
}
~~~

Và nối flow:

~~~java
@Bean
IntegrationFlow reserveFlow(ReservationOperations service) {
    return IntegrationFlow.from("reservations.commands")
        .handle(service, "reserve")
        .get();
}
~~~

Trong một số trường hợp, Spring Integration có thể tự tạo channel theo convention/cấu hình. Tuy nhiên, để **hợp đồng bài học rõ ràng**, ta khai báo bean đích, xác định consumer và kiểm thử, thay vì dựa vào implicit channel creation.

### 4.3. Default channel không phải business router

`defaultRequestChannel` không tự xem payload để chọn giữa kho A/B, tenant A/B hay thị trường nội địa/quốc tế. Nó là **request destination chung**. Nếu cần routing theo nội dung, đặt **Router** trong flow sau channel hoặc dùng method-level override cho những use cases thực sự khác nhau.

~~~text
Gateway defaultRequestChannel
       |
       v
orders.commands
       |
       v
Validate/Authorize
       |
       v
Content-Based Router
   /       |        \
Domestic Priority International
~~~

Như vậy caller không tự biết địa chỉ các downstream handlers, giảm coupling, nhưng vẫn cần kiểm soát **source identity, authorization và policy** trước Router.

## 5. Method-level `@Gateway(requestChannel)` ghi đè mặc định

Gateway có thể có nhiều methods với các loại message khác nhau. Ví dụ:

~~~java
@MessagingGateway(
    defaultRequestChannel = "reservations.commands")
interface ReservationGateway {

    // Dùng default.
    ReserveReceipt reserve(ReserveCommand command);

    // Override riêng method này.
    @Gateway(requestChannel = "reservations.priority")
    ReserveReceipt reservePriority(ReserveCommand command);

    // Vẫn dùng default, trừ khi có override cụ thể.
    ReserveReceipt retryExisting(ReserveCommand command);
}
~~~

| Method | Request channel sẽ dùng | Lý do |
| --- | --- | --- |
| `reserve` | `reservations.commands` | Kế thừa interface default |
| `reservePriority` | `reservations.priority` | Có override trên method |
| `retryExisting` | `reservations.commands` | Không có override |
| Method ở gateway interface khác | Theo annotation/config của interface đó | Không tự kế thừa cấu hình từ interface này |

**Không xem defaultRequestChannel là “fallback nếu channel override đang lỗi”.** Một khi method được cấu hình request channel riêng, channel đó phải tồn tại và xử lý đúng; framework không tự bỏ qua lỗi của nhánh priority để chạy normal.

### 5.1. Khi nào dùng method-level override?

Phù hợp khi các methods có **semantics khác nhau rõ ràng**, ví dụ:

- `reserve(...)` và `reservePriority(...)` có policy/lane khác nhau.
- `submit(...)` nhận command, còn `cancel(...)` cần handler hủy.
- `query(...)` cần một request channel cho read path khác write path.

Không nên tạo hàng trăm methods chỉ để gắn mỗi tenant vào một channel. Với dynamic tenant/domain routing, thường hợp lý hơn là Gateway gửi vào **một trusted input** rồi để Router/authorization chọn route.

### 5.2. Override không phải quyền truy cập

Việc ai đó gọi `reservePriority` không chứng minh họ có quyền ưu tiên. Flow của `reservations.priority` vẫn phải xác thực principal, quota, tenant và policy. Đừng dùng tên method hay tên channel làm security boundary duy nhất.

## 6. Request channel khác Reply channel

Cấu hình interface có thể có:

~~~java
@MessagingGateway(
    defaultRequestChannel = "reservations.commands",
    defaultReplyTimeout = "3000")
interface ReservationGateway {
    ReserveReceipt reserve(ReserveCommand command);
}
~~~

**Ở đây không cấu hình `defaultReplyChannel`**: trong request–reply nội bộ, Gateway có thể tạo reply destination tạm thời cho lời gọi đang chờ. Service Activator trả một `ReserveReceipt`; nó phải được chuyển về đúng route đó.

~~~mermaid
sequenceDiagram
    participant J as Java caller
    participant G as Gateway proxy
    participant I as reservations.commands
    participant S as Service Activator
    participant R as Gateway temporary reply channel
    J->>G: reserve(command)
    G->>I: Message<ReserveCommand> + replyChannel
    I->>S: Invoke reserve
    S-->>R: Message<ReserveReceipt>
    R-->>G: Reply
    G-->>J: ReserveReceipt
~~~

### 6.1. Vì sao không tự gắn fixed reply output khi đang dùng Gateway?

Nếu flow cấu hình:

~~~java
IntegrationFlow.from("reservations.commands")
    .handle(service, "reserve")
    .channel("reservations.replies.audit")
    .get();
~~~

Kết quả có thể đi vào `reservations.replies.audit` thay vì reply destination mà Gateway đang chờ. Nếu không có bridge/consumer trả về caller, Gateway sẽ timeout.

**Cách làm đúng tùy mục tiêu:**

- Nếu mục tiêu là **Gateway trả object**: để flow phát reply về request `replyChannel`, kiểm thử end-to-end.
- Nếu mục tiêu là **gửi kết quả sang một flow khác**: cần bridge/route có chủ đích và vẫn xử lý reply của Gateway theo contract.
- Nếu mục tiêu là **ghi log/metric song song**: cân nhắc wire tap/observability, không chuyển reply sang queue riêng làm caller mất phản hồi.

### 6.2. `defaultReplyChannel` không phải tên khác của `defaultRequestChannel`

| Thuộc tính/metadata | Ý nghĩa |
| --- | --- |
| `defaultRequestChannel` | Gateway **gửi request vào đâu** khi method không override |
| `@Gateway(requestChannel = "...")` | Ghi đè đích request cho một method |
| `defaultReplyChannel` | Cấu hình reply channel mặc định theo cơ chế Gateway khi cần |
| `@Gateway(replyChannel = "...")` | Reply channel ở phạm vi method theo cấu hình hỗ trợ |
| `replyChannel` header của request | Đường reply có thể do Gateway/framework cấp cho request hiện tại |
| `errorChannel` header / Gateway error policy | Xử lý lỗi, không phải ordinary business reply |

Một **shared reply channel** có thể phức tạp với concurrent requests; nếu dùng, phải chắc chắn routing/correlation không trộn replies. Với request–reply đồng bộ nội bộ, temporary reply channels do Gateway quản lý thường đơn giản hơn.


## 7. Java 17: mô hình lệnh và kết quả có kiểu

Ví dụ mô phỏng hai luồng giữ hàng để nhìn rõ **request channel nào đã nhận message**. Chưa kết nối cơ sở dữ liệu; một kết quả `RESERVED` trong demo không có nghĩa inventory thực đã commit.

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
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(operationId, "operationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(sku, "sku");
    }
}

record ReserveReceipt(
    String operationId,
    String orderId,
    String status,
    String processedBy,
    String reasonCode
) {
    ReserveReceipt {
        Objects.requireNonNull(operationId, "operationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(processedBy, "processedBy");
    }
}
~~~

Trường `processedBy` chỉ giúp kiểm nhánh NORMAL hoặc PRIORITY trong ví dụ. Trong ứng dụng thật, chọn response schema theo business contract, không nhất thiết công khai tên handler nội bộ.

### 7.1. Service giả lập hai loại handler

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class ReservationOperations {

    private final AtomicInteger normalCalls = new AtomicInteger();
    private final AtomicInteger priorityCalls = new AtomicInteger();

    public ReserveReceipt reserve(ReserveCommand command) {
        normalCalls.incrementAndGet();
        return decide(command, "NORMAL");
    }

    public ReserveReceipt reservePriority(ReserveCommand command) {
        priorityCalls.incrementAndGet();
        return decide(command, "PRIORITY");
    }

    private static ReserveReceipt decide(
            ReserveCommand command, String lane) {
        if (command.tenantId().isBlank()
                || command.operationId().isBlank()
                || command.orderId().isBlank()
                || command.sku().isBlank()) {
            return new ReserveReceipt(
                command.operationId(), command.orderId(),
                "REJECTED", lane, "REQUIRED_FIELD_MISSING");
        }

        if (command.quantity() < 1
                || command.quantity() > 500) {
            return new ReserveReceipt(
                command.operationId(), command.orderId(),
                "REJECTED", lane, "QUANTITY_OUT_OF_RANGE");
        }

        return new ReserveReceipt(
            command.operationId(), command.orderId(),
            "RESERVED", lane, null);
    }

    int normalCalls() {
        return normalCalls.get();
    }

    int priorityCalls() {
        return priorityCalls.get();
    }
}
~~~

**Ý nghĩa:** `ReserveReceipt(status="REJECTED")` vẫn là một **reply hợp lệ** cho request được định tuyến đúng. Đừng trả `null` hoặc ném lỗi kỹ thuật để biểu thị validation failure chỉ vì ngại tạo DTO kết quả.

Các kiểm tra tenant trong demo chỉ là cú pháp. Production phải xác thực principal/tenant ở ingress và kiểm lại quyền, tồn kho, quota tại business boundary.

## 8. Định nghĩa Gateway interface với default và override

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "reservations.commands",
    defaultRequestTimeout = "500",
    defaultReplyTimeout = "3000")
interface ReservationGateway {

    // Sử dụng reservations.commands theo defaultRequestChannel.
    ReserveReceipt reserve(ReserveCommand command);

    // Ghi đè request channel chỉ cho method này.
    @Gateway(requestChannel = "reservations.priority")
    ReserveReceipt reservePriority(ReserveCommand command);
}
~~~

Các timeout strings minh họa **milliseconds** trong annotation Spring Integration, không phải khuyến nghị SLA production.

- `defaultRequestTimeout` liên quan đến thời gian gửi vào channel khi thao tác send có thể block.
- `defaultReplyTimeout` liên quan đến thời gian chờ reply theo Gateway semantics.
- Chúng không hứa database rollback hoặc tự hủy một thread nghiệp vụ đang chạy.
- Với `DirectChannel` đồng bộ, handler có thể chạy bên trong lời gọi send; reply timeout **không nhất thiết cắt ngang method đang block**.

Tên `reservations.commands` và `reservations.priority` là **chi tiết integration infrastructure**. Caller chỉ cần biết `ReservationGateway`; nếu client gọi thẳng MessageChannel để “bypass” contract, các kiểm tra chung có thể bị bỏ qua.

## 9. Spring Integration Java DSL: hai channels, hai flows

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
class GatewayDefaultChannelConfiguration {

    @Bean("reservations.commands")
    DirectChannel normalChannel() {
        return new DirectChannel();
    }

    @Bean("reservations.priority")
    DirectChannel priorityChannel() {
        return new DirectChannel();
    }

    @Bean
    ReservationOperations reservationOperations() {
        return new ReservationOperations();
    }

    @Bean
    IntegrationFlow normalReservationFlow(
            ReservationOperations service) {
        return IntegrationFlow.from("reservations.commands")
            .handle(service, "reserve")
            .get();
    }

    @Bean
    IntegrationFlow priorityReservationFlow(
            ReservationOperations service) {
        return IntegrationFlow.from("reservations.priority")
            .handle(service, "reservePriority")
            .get();
    }
}
~~~

`@IntegrationComponentScan` phải tìm thấy interface `@MessagingGateway`. Nếu dự án đặt Gateway ở package khác, chỉ rõ scan base packages; đừng dựa vào cấu hình scan mặc định khi chưa kiểm chứng.

### 9.1. Luồng xử lý bình thường

~~~text
Java caller
  -> ReservationGateway.reserve(command)
  -> request channel "reservations.commands"
  -> ReservationOperations.reserve()
  -> ReserveReceipt(processedBy=NORMAL)
  -> Gateway reply channel
  -> caller receives ReserveReceipt
~~~

### 9.2. Luồng override ưu tiên

~~~text
Java caller
  -> ReservationGateway.reservePriority(command)
  -> @Gateway requestChannel="reservations.priority"
  -> ReservationOperations.reservePriority()
  -> ReserveReceipt(processedBy=PRIORITY)
  -> Gateway reply channel
  -> caller receives ReserveReceipt
~~~

Hai flows không cần dùng cùng Service Activator method. Việc dùng chung class service là tùy thiết kế. Một method-level override không khiến method `reserve` chuyển sang priority channel.

### 9.3. Argument mapping khi method có nhiều parameters

Với một parameter `ReserveCommand`, Gateway có thể lấy chính object đó làm payload. Nếu có nhiều parameters, cần quyết định trường nào là payload, trường nào là headers/metadata.

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

// Fragment minh họa; không thuộc interface hoàn chỉnh ở trên:
@Gateway(requestChannel = "reservations.commands")
ReserveReceipt reserveWithTag(
    @Payload ReserveCommand command,
    @Header("clientRequestTag") String tag);
~~~

Đừng dùng header `clientRequestTag` làm bằng chứng quyền tenant. Nó có thể đến từ client và không đáng tin; operation identity phải theo hợp đồng nghiệp vụ.

### 9.4. Default channel không phải Content-Based Router

Nếu cần chọn warehouse dựa trên SKU, tenant hay quota, có thể làm:

~~~text
Gateway default request channel
   -> Validate/authorize
   -> Content-Based Router
       -> Domestic handler
       -> International handler
       -> Priority handler
~~~

Router chọn route theo dữ liệu đã xác minh; `defaultRequestChannel` chỉ chọn **điểm ingress vào flow**.

## 10. One-way Gateway với phương thức void

Một API Java có thể không mong reply:

~~~java
record AuditEvent(String operationId, String eventType) {}

@MessagingGateway(defaultRequestChannel = "audit.events")
interface AuditGateway {
    void record(AuditEvent event);
}
~~~

Flow minh họa:

~~~java
final class AuditRecorder {
    public void record(AuditEvent event) {
        // Demo: lưu sự kiện, không return business reply.
    }
}

@Bean("audit.events")
DirectChannel auditChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow auditFlow(AuditRecorder recorder) {
    return IntegrationFlow.from("audit.events")
        .handle(recorder, "record")
        .get();
}
~~~

Các `@Bean` là fragments cần đặt vào một `@Configuration` thích hợp và tạo bean `AuditRecorder`. Chúng không thuộc cấu hình hai channels ở phần 9.

**Không suy ra “`void` là async fire-and-forget”.** Với DirectChannel, handler có thể chạy đồng bộ trước khi method `void` trở về. Với QueueChannel hoặc broker, Gateway có thể trả khi request được chấp nhận vào queue mà chưa xử lý business.

Nếu caller cần outcome commit, hãy trả typed reply hoặc operation ID với API tra trạng thái; `void` không tự thể hiện success/rejected/unknown.

## 11. Loại channel ảnh hưởng như thế nào?

| Channel | Dispatch | Điểm mạnh | Lưu ý về Gateway |
| --- | --- | --- | --- |
| `DirectChannel` | Thường đồng bộ, cùng thread | Đơn giản, dễ debug | Business call chậm giữ caller thread |
| `ExecutorChannel` | Worker thread do executor quản lý | Tách thread/có concurrency | Timeout, tracing, security context, shutdown |
| `QueueChannel` | Message đợi được poll | Buffer và backpressure | **Phải có poller**; request accepted khác processed |
| `PublishSubscribeChannel` | Fan-out tới subscribers | Broadcast/notifications | Nhiều replies cần Scatter-Gather/Aggregator |
| `PriorityChannel` | Queue ưu tiên | Điều khiển dequeue order | Starvation, poller và capacity |

### 11.1. DirectChannel không bị replyTimeout “cắt ngang” tự động

~~~text
Caller thread
  -> Gateway.send()
    -> DirectChannel
      -> slow business method (10 seconds)
        -> produce reply
    -> send returns
  -> Gateway returns
~~~

Nếu chính `send()` thực hiện handler đồng bộ, `defaultReplyTimeout="3000"` không phải một hard deadline 3 giây áp lên toàn bộ method. Với I/O thật cần timeout ở JDBC/HTTP client, circuit breaker, thread budgets và SLA end-to-end.

### 11.2. ExecutorChannel: reply đến trên thread khác

~~~text
Gateway caller ----send---> ExecutorChannel
                        worker thread ---> handler ---> reply
Gateway caller <-------------- response on reply route
~~~

Đừng dựa hoàn toàn vào `ThreadLocal` chứa tenant/principal trong async flow. Ngữ cảnh xác thực/correlation cần được truyền qua cơ chế có kiểm soát; không copy security token thô vào message đi qua boundary ngoài.

### 11.3. QueueChannel: không có poller sẽ không có reply

~~~text
Gateway -> QueueChannel.send(request) = accepted
                   |
                   v
             waiting in queue
                   |
             no consumer/poller
                   |
           Gateway waits / times out
~~~

Nếu queue có capacity, request timeout có thể ảnh hưởng việc send khi queue đầy. Dù enqueue thành công, không có nghĩa service đã thực thi.

Một poller demo (cấu hình riêng, không trùng tên với DirectChannel ở phần 9):

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Bean("reservations.queued")
QueueChannel queuedReservations() {
    return new QueueChannel(1000);
}

@Bean
IntegrationFlow queuedFlow(ReservationOperations service) {
    return IntegrationFlow
        .from("reservations.queued",
              endpoint -> endpoint.poller(
                  Pollers.fixedDelay(100)))
        .handle(service, "reserve")
        .get();
}
~~~

Poller 100 ms chỉ là ví dụ; production cần cấu hình concurrency, capacity, retry/error policy và persistence nếu yêu cầu durability.

### 11.4. Publish-subscribe và nhiều replies

Một `PublishSubscribeChannel` có thể chuyển request cho nhiều subscribers. Gateway chờ **một** reply không đồng nghĩa tự tổng hợp mọi kết quả từ subscribers. Nếu cần kết quả từ nhiều bên, áp **Scatter-Gather/Aggregator** có release strategy, timeout và unique-reply handling.


## 12. Request timeout và reply timeout là hai giai đoạn khác nhau

Hãy theo dõi đường đi của một Gateway method:

~~~text
T0  Java caller invokes gateway method
T1  Gateway builds Message<ReserveCommand>
T2  Gateway attempts to send to request channel
T3  Request channel accepts/dispatches
T4  Handler computes business outcome
T5  Handler sends reply message
T6  Gateway obtains reply and returns Java value
~~~

Ở đây có hai loại chờ dễ nhầm:

- **Request timeout** liên quan tới việc send tới request channel (ví dụ bounded queue đầy khiến send không thể hoàn tất).
- **Reply timeout** liên quan tới chờ kết quả từ luồng request–reply sau khi gửi.

Nếu xử lý request đồng bộ ngay trong lời gọi send, một Gateway-level reply timeout không nhất thiết ngắt được handler đang block, như đã giải thích ở phần 11.

### 12.1. Timeline: QueueChannel thiếu poller

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant Q as QueueChannel
    participant H as Handler
    C->>G: reserve(command)
    G->>Q: Send request
    Q-->>G: Accepted into queue
    Note over Q,H: No poller, handler never invoked
    Note over G: Wait reply timeout
    G-->>C: Timeout / no reply outcome
~~~

Đây không phải lỗi Mapper hoặc `ReservationOperations`; **nó chưa từng được gọi**. Cần kiểm wiring của channel, poller, lifecycle và queue backlog.

### 12.2. Timeline: DB commit nhưng reply mất

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant W as Worker
    participant DB as DB
    C->>G: reserve(op=RSV-901)
    G->>W: request via channel
    W->>DB: Commit business operation
    DB-->>W: COMMITTED
    W--xG: Reply lost / worker crash
    Note over G: Reply timeout
    G-->>C: Timeout
    C->>G: Retry with same operationId
    G->>W: Same operation again
    W->>DB: Find stored outcome
    DB-->>W: RESERVED (no new mutation)
    W-->>G: Reply
    G-->>C: RESERVED
~~~

**Timeout không nói rằng operation chưa commit**. Một retry đúng giữ **cùng business operation ID** và dựa vào idempotency tại nơi commit effect.

### 12.3. Đừng chọn timeout bằng cách đoán

Với một API có SLA, tính đến:

- Chi phí serialization và dispatch.
- Thời gian queue chờ/poller delay.
- Thời gian service/DB/HTTP clients.
- Backoff khi retry nội bộ.
- Network latency và timeout của caller bên ngoài.
- Deadline tổng của workflow và khả năng late reply.

Giá trị `defaultReplyTimeout="3000"` là demo. Production có thể cần budget phân tầng và hướng xử lý `UNKNOWN/PROCESSING` nếu caller hết thời gian chờ trước khi outcome xác định.

### 12.4. Method-level timeout override

Annotation `@Gateway` có thể được dùng để cấu hình riêng method theo khả năng của phiên bản Spring Integration, chẳng hạn reply timeout khác nhau cho lệnh ưu tiên hay query. Nhưng **đừng đánh đồng** việc override `requestChannel` với việc tự động tăng timeout. Mỗi tham số có trách nhiệm riêng và phải có test khi thay.

## 13. Các lỗi cấu hình liên quan đến defaultRequestChannel

| Sai sót | Dấu hiệu | Hướng kiểm tra |
| --- | --- | --- |
| Tên channel sai/chưa resolve | Gateway không gửi được request, lỗi cấu hình/invocation | Bean names, application context, channel resolution |
| DirectChannel không có subscriber | Send thất bại vì không có handler | IntegrationFlow có thực sự đăng ký consumer? |
| Hai subscribers trên DirectChannel | Một handler không được chọn theo kỳ vọng | Dispatch semantics/load-balancing, không coi là broadcast |
| Method override trỏ sai channel | Chỉ `reservePriority` lỗi | `@Gateway(requestChannel)` và priority flow |
| QueueChannel không có poller | Gửi thành công nhưng timeout | Consumer/poller và queue depth |
| Fixed output channel hút reply | Handler chạy nhưng Gateway timeout | Reply channel topology/bridge |
| Service method trả `null` | No ordinary reply | `requiresReply`/typed outcome |
| Handler ném exception | Caller nhận exception hoặc error route | Type/wrapping/error channel policy |
| Async executor nghẽn | Reply chậm hoặc bị từ chối task | Pool saturation/rejected execution |
| Transport reply headers bị xóa | Remote caller không được trả kết quả | Header mapper/correlation |
| Gateway interface không được đăng ký | Không inject được bean interface | `@IntegrationComponentScan` / config |
| Output type mismatch | Mapping reply sang Java return type lỗi | Payload converter, return type contract |

### 13.1. DirectChannel có hai subscribers không phải hai bản sao request

`DirectChannel` là point-to-point dispatch; khi có nhiều handlers/subscribers, nó có thể áp dụng dispatch/failover semantics thay vì gửi bản sao cho mọi subscriber. Do đó, đừng nối **normal + priority** cùng một DirectChannel rồi mong cả hai xử lý.

Nếu cần multi-recipient/broadcast, hãy dùng pattern phù hợp như Publish-Subscribe/Recipient List/Scatter-Gather và đặt release strategy cho replies.

### 13.2. Channel name không phải API contract của caller

Caller không nên cần biết `"reservations.commands"` để gọi `reserve(...)`. Channel name phục vụ wiring và monitoring nội bộ; public business API nên là phương thức interface có input/output rõ.

Khi rename channel, cập nhật Gateway annotation, bean declarations và flow cùng lúc. Có thể dùng constants/configuration properties, nhưng cần tránh các biến tên trỏ tới bean đã bị xóa. Test sẽ bắt lỗi wiring sớm.

### 13.3. Service Activator trả payload nào?

Nếu handler trả `ReserveReceipt`, Gateway method cũng khai báo `ReserveReceipt`. Nếu handler trả `Message<ReserveReceipt>`, Spring Integration có thể dùng payload hoặc message theo message-handling rules. Test **return type thực** thay vì suy đoán.

Một `ReserveReceipt(status="REJECTED")` là business reply; không thể tự coi nó là exception. Nếu cần controller trả HTTP 422, đó là quyết định **ở HTTP boundary**, không phải semantics của `defaultRequestChannel`.

## 14. Lỗi kỹ thuật, business rejection và Error Channel

Một flow có thể gặp ba nhóm outcome:

| Nhóm | Ví dụ | Gateway cần biểu diễn |
| --- | --- | --- |
| **Success** | Inventory reservation đã commit | Typed `ReserveReceipt(RESERVED)` |
| **Business rejection** | Quantity sai, hết hàng theo policy terminal | Typed `ReserveReceipt(REJECTED)` với reason |
| **Technical failure** | DB timeout, broker unavailable, serialization error | Exception / error flow / bounded retry |

### 14.1. Error channel không phải request channel

`defaultRequestChannel` trả lời câu hỏi **request đi vào đâu**. Error channel trả lời câu hỏi **lỗi sẽ được xử lý như thế nào**, thường phụ thuộc endpoint, poller, executor và adapter.

Với `DirectChannel` đồng bộ, exception từ handler thường có thể lan về Gateway caller dưới dạng exception/wrapper thích hợp. Trong async flow, lỗi có thể được phát thành `ErrorMessage` theo cấu hình. **Không** mặc định mọi exception đều sẽ đi vào một global error channel rồi tự sinh `ReserveReceipt`.

### 14.2. Rejection nghiệp vụ nên có reply rõ

~~~java
return new ReserveReceipt(
    command.operationId(),
    command.orderId(),
    "REJECTED",
    "NORMAL",
    "QUANTITY_OUT_OF_RANGE");
~~~

Nếu chuyển lỗi này thành exception retryable, broker/client có thể thử lại mãi cùng quantity không hợp lệ. Typed result giúp Gateway caller phân biệt **đã từ chối hợp lệ** với **không biết outcome**.

### 14.3. Lỗi kỹ thuật không được sửa thành thành công giả

~~~java
// KHÔNG NÊN:
try {
    externalWarehouse.reserve(command);
} catch (Exception ignored) {
    return new ReserveReceipt(
        command.operationId(), command.orderId(),
        "RESERVED", "NORMAL", null);
}
~~~

Lỗi remote API không chứng minh side effect đã thành công. Cần status lookup/reconciliation nếu response có thể mất sau commit; không thể dùng catch-all rồi phát `RESERVED`.

### 14.4. Gateway error mapping phải là policy có chủ đích

Với method Java trả `ReserveReceipt`, một exception kỹ thuật có thể cần được propagate hoặc được ánh xạ thành một DTO `PROCESSING/UNKNOWN` ở boundary. Chọn cách nào tùy business contract. Đừng đặt toàn bộ lỗi vào `REJECTED` và làm mất khả năng retry/reconcile.

## 15. Metadata quan trọng khi qua Gateway

Gateway tạo message từ method arguments. Một số metadata thuộc integration, một số thuộc business. Cần phân biệt:

| Metadata | Vai trò | Quy tắc qua flow |
| --- | --- | --- |
| `operationId` | Idempotency của business effect | Giữ nguyên qua retry/redelivery |
| `tenantId` | Scope dữ liệu và quyền | Xác minh principal, không tin body tự khai |
| `businessCorrelationId` | Trace một business request | Truyền theo hợp đồng |
| `executionId` | Correlation của một workflow run | Chỉ dùng cho đúng execution |
| `replyChannel` | Reply destination của Gateway | Bảo toàn theo topology nội bộ cần thiết |
| `errorChannel` | Error routing metadata | Không thay thế normal reply |
| `MessageHeaders.ID` | Envelope ID do framework cấp | Không làm operation key |
| `sequenceNumber/sequenceSize` | Splitter/Aggregator metadata | Chỉ giữ nếu group semantics phù hợp |
| `traceId/spanId` | Observability | Không làm security/idempotency identity |
| HTTP/JMS/AMQP/Kafka delivery metadata | Transport-specific | Không coi là business identity |

### 15.1. Correlation khác idempotency

~~~text
businessCorrelationId = ORD-901
executionId           = RUN-901-A
operationId           = RSV-901-LINE-1
Spring Message ID     = UUID-of-envelope
~~~

Một đơn có thể có nhiều operations. Nếu chỉ dùng `businessCorrelationId=ORD-901` để dedup, lệnh RELEASE có thể bị chặn nhầm bởi RESERVE trước đó. Nếu dùng envelope ID, redelivery có thể sinh ID mới và effect bị lặp.

### 15.2. Gateway proxy không xác thực tenant chỉ vì parameter có tenantId

Method `reserve(new ReserveCommand("shop-b", ...))` là lời gọi Java chứ không phải bằng chứng quyền. Ở kiến trúc nhiều tenant, cần identity đã xác thực ở ingress hoặc service boundary, kiểm tra caller có quyền thao tác với order/tenant trước khi commit.

Một Channel internal chỉ là đường truyền. Nếu nó chứa request do dữ liệu bên ngoài điều khiển, downstream vẫn phải kiểm AuthN/AuthZ và giới hạn dữ liệu.

### 15.3. Thread context qua ExecutorChannel

Khi flow chạy trên worker thread, security/tracing context dựa trên ThreadLocal có thể không tự truyền đi. Dùng context propagation do framework hỗ trợ và/hoặc business identity được truyền trong message theo hợp đồng, **không copy raw bearer tokens vào payload/headers** để “cho khỏi mất quyền”.

### 15.4. ReplyChannel là object nội bộ, không phải external address

Qua HTTP/Kafka/JMS/AMQP, `replyChannel` chứa Java `MessageChannel` object không nên bị serialize nguyên. Remote request–reply cần một **transport reply destination** có correlation ID, ACL, timeout và conversion đúng.

## 16. Retry/redelivery không được đổi request channel một cách ngẫu nhiên

Khi client hoặc consumer retry cùng business operation, câu hỏi lớn không phải chỉ nó đi qua normal hay priority channel, mà là **tác dụng phụ có bị thực hiện lặp không**.

~~~text
First attempt:
  operationId=RSV-901, routed NORMAL, stock reserved
  reply lost

Redelivery:
  operationId=RSV-901, perhaps routed PRIORITY
  lookup existing operation result
  do NOT reserve stock again
~~~

Nếu cùng operation key có thể đi qua hai lanes khác nhau, **cả hai lanes phải dùng chung idempotency boundary ở business owner**. Một local `HashSet` riêng trên mỗi worker/handler không đủ.

### 16.1. Cửa sổ lỗi commit xong rồi mất reply

~~~mermaid
sequenceDiagram
    participant C as Client/Gateway
    participant A as Handler A
    participant DB as Shared inventory DB
    participant B as Handler B
    C->>A: RSV-901
    A->>DB: Atomic claim + reserve
    DB-->>A: COMMITTED
    A--xC: Reply lost
    C->>B: Retry RSV-901
    B->>DB: Read unique operation key
    DB-->>B: Stored RESERVED result
    B-->>C: RESERVED reply
~~~

**Cần bảo đảm:** A và B không cùng commit thêm hàng cho một operation. Với một database chung, dùng unique operation key + transaction cùng mutation; với external API, dùng idempotency token ở **đích** hoặc reconciliation.

### 16.2. Đổi route không được tạo command mới

Nếu một timeout làm caller gọi `reservePriority(...)` thay vì `reserve(...)`, đó có thể chỉ là **retry cùng command** với lane khác, hoặc là một business command mới. Contract phải quyết định; đừng tự phát `UUID.randomUUID()` mới để “chạy nhanh hơn”. Nếu nghiệp vụ cho phép **escalate priority**, có thể lưu policy về operation hiện có thay vì thay identity.

### 16.3. Gateway không tự cung cấp exactly-once

Messaging Gateway chỉ chuyển lời gọi thành message/request–reply và hỗ trợ routing; **nó không tự làm business side effect idempotent**. Kafka/JMS transaction và broker ACK có consistency boundary riêng, không tự tạo DB+HTTP atomic transaction trên mọi thành phần.

### 16.4. Retry storm và timeout budget

Một client retry hai lần, Gateway retries ba lần, consumer redeliver hai lần có thể tạo nhiều attempts cho cùng key. Những retries lồng nhau cần budget/backoff/jitter; nếu tất cả instances cùng retry vào DB chậm, queue backlog và lock contention tăng mạnh.

Phân loại **terminal input errors** không retry, **transient transport errors** retry hữu hạn, **unknown business outcome** reconcile thay vì tạo side effect mới.

## 17. Gateway trong luồng Splitter–Aggregator và Scatter-Gather

Một method Gateway có thể đại diện cho **một batch command**, trong khi flow phía sau xử lý nhiều child messages:

~~~mermaid
flowchart TD
    G["Gateway: reserveBatch(batch)"] --> IN["defaultRequestChannel"]
    IN --> S["Splitter"]
    S --> A["Reserve LINE-1"]
    S --> B["Reserve LINE-2"]
    S --> C["Reserve LINE-3"]
    A --> AG["Aggregator by executionId"]
    B --> AG
    C --> AG
    AG --> R["BatchReserveReceipt"]
    R --> G
~~~

Gateway chờ **một reply tổng** nếu method khai báo trả `BatchReserveReceipt`. Một child trả kết quả không mặc nhiên đủ để Gateway hoàn tất đúng batch.

### 17.1. Mất một child thì Gateway có thể timeout

Nếu LINE-2 bị Filter bỏ âm thầm:

~~~text
Expected: LINE-1, LINE-2, LINE-3
Received: LINE-1, LINE-3
Aggregator waiting: 2/3
Gateway: reply timeout
~~~

Nếu rejection là outcome có nghĩa, hãy trả `LineOutcome(lineId, status=REJECTED)` cho child đó thay vì im lặng drop. Aggregator có thể gom ba **unique outcomes** và trả batch `PARTIAL/FAILED`.

### 17.2. Group correlation cần đúng phạm vi

- `executionId` gom replies của một lần workflow.
- `lineId` định danh child duy nhất; duplicate replies không được đếm hai lần.
- `operationId` bảo vệ side effect của từng child.
- `businessCorrelationId` truy vết order gốc.
- `sequenceNumber/sequenceSize` cần semantics đúng nếu được dùng để release.

Nếu có hai executions chạy đồng thời cho cùng order, chỉ group theo `orderId` có thể trộn replies. Không dùng raw group size khi duplicate có thể vào; xét unique child IDs và closed-execution tombstones.

### 17.3. Zero replies: timeout của Aggregator không phải lúc nào cũng đủ

Nếu không một child nào phát reply, có thể **chưa có group để group-timeout kích hoạt**. Một execution-level deadline watcher có thể cần thiết. Gateway timeout chỉ là một tín hiệu ở caller, không tự đảm bảo cleanup các business operations đang xử lý bên dưới.

### 17.4. Gateway không tự đóng group

Nếu Aggregator đã phát `BatchReserveReceipt` rồi duplicate late reply tạo lại group, có thể phát final result lần hai. Cần persisted closed-execution state hoặc finalizer idempotent, không dựa hoàn toàn vào Gateway “chỉ lấy một reply”.


## 18. JUnit 5: kiểm tra Gateway thực sự dùng default channel

Đoạn code phần 7–9 có `ReservationGateway`, `ReserveCommand`, `ReserveReceipt`, `ReservationOperations` và cấu hình `GatewayDefaultChannelConfiguration`. Test này chạy trong Spring context để xác minh **routing đến đúng endpoint**, không chỉ kiểm logic của một Java method.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(GatewayDefaultChannelConfiguration.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class GatewayDefaultChannelIntegrationTest {

    @Autowired
    ReservationGateway gateway;

    @Autowired
    ReservationOperations operations;

    private static ReserveCommand command(
            String operationId, int quantity) {
        return new ReserveCommand(
            "shop-a", operationId, "ORD-901",
            "BOOK-42", quantity);
    }

    @Test
    void methodWithoutOverrideUsesDefaultRequestChannel() {
        ReserveReceipt receipt =
            gateway.reserve(command("RSV-901", 2));

        assertNotNull(receipt);
        assertEquals("RSV-901", receipt.operationId());
        assertEquals("RESERVED", receipt.status());
        assertEquals("NORMAL", receipt.processedBy());

        assertEquals(1, operations.normalCalls());
        assertEquals(0, operations.priorityCalls());
    }

    @Test
    void methodLevelGatewayOverridesRequestChannel() {
        ReserveReceipt receipt =
            gateway.reservePriority(command("RSV-902", 2));

        assertNotNull(receipt);
        assertEquals("RSV-902", receipt.operationId());
        assertEquals("RESERVED", receipt.status());
        assertEquals("PRIORITY", receipt.processedBy());

        assertEquals(0, operations.normalCalls());
        assertEquals(1, operations.priorityCalls());
    }

    @Test
    void rejectedBusinessInputStillReturnsReplyViaDefault() {
        ReserveReceipt receipt =
            gateway.reserve(command("RSV-903", -1));

        assertNotNull(receipt);
        assertEquals("REJECTED", receipt.status());
        assertEquals(
            "QUANTITY_OUT_OF_RANGE",
            receipt.reasonCode());
        assertEquals("NORMAL", receipt.processedBy());

        assertEquals(1, operations.normalCalls());
        assertEquals(0, operations.priorityCalls());
    }

    @Test
    void twoGatewayInvocationsKeepTheirOwnRoutingContracts() {
        ReserveReceipt ordinary =
            gateway.reserve(command("RSV-904", 2));
        ReserveReceipt priority =
            gateway.reservePriority(command("RSV-905", 1));

        assertEquals("NORMAL", ordinary.processedBy());
        assertEquals("PRIORITY", priority.processedBy());
        assertNotEquals(
            ordinary.operationId(), priority.operationId());

        assertEquals(1, operations.normalCalls());
        assertEquals(1, operations.priorityCalls());
    }
}
~~~

### 18.1. Vì sao cần assert counters?

Chỉ kiểm `receipt.status() == "RESERVED"` **không đủ**: cả normal và priority handlers đều có thể trả `RESERVED`, nên test vẫn pass khi request đi nhầm channel.

Cặp assertions:

~~~java
assertEquals(1, operations.normalCalls());
assertEquals(0, operations.priorityCalls());
~~~

chứng minh `reserve(...)` thực sự vào normal handler. Với `reservePriority(...)`, đổi cặp đếm. Đây là kiểm tra **routing semantics** của `defaultRequestChannel` chứ không chỉ business result.

### 18.2. Tại sao dùng `@DirtiesContext`?

Các counters của `ReservationOperations` nằm trong singleton bean của test context. `@DirtiesContext(AFTER_EACH_TEST_METHOD)` giúp những tests minh họa độc lập, không phụ thuộc thứ tự chạy. Trong test lớn hơn, có thể thay bằng fixture reset rõ ràng hoặc test containers mới theo điều kiện resource.

**Không đưa counters in-memory này vào thiết kế chống trùng ở production.** Một system nhiều replicas cần shared, durable idempotency boundary.

### 18.3. Giới hạn của test

Test trong một application context chứng minh Gateway proxy, channels và Service Activator wiring ở mức Spring Integration. Nó chưa kiểm tra:

- Database commit và rollback.
- Broker ACK/redelivery.
- Lỗi gửi reply qua remote transport.
- Security principal và tenant authorization thật.
- Gateway sử dụng QueueChannel/ExecutorChannel với delay.
- Multi-instance idempotency.
- Timeout khi handler đã commit nhưng reply bị mất.

Những trường hợp đó cần integration/contract/chaos tests ở các boundary tương ứng.

## 19. Kiểm thử cấu hình lỗi và timeout

Không chỉ test happy path; những lỗi khó nhất của Gateway thường xuất hiện khi **request đã được chấp nhận** nhưng không có reply.

### 19.1. Request channel không có subscriber

Thiết lập một `DirectChannel` không nối handler, sau đó gọi Gateway. Trong nhiều cấu hình, send có thể lỗi vì không có subscriber. Test phải chấp nhận cơ chế báo lỗi của framework/version đang dùng và assert:

1. Không có business side effect.
2. Có lỗi rõ về route/dispatcher, không trả `RESERVED` giả.
3. Không âm thầm reroute sang channel khác chỉ vì channel mặc định không hoạt động.

**Không cố khẳng định một exception class duy nhất** cho mọi version khi chưa chạy trên dependency thực.

### 19.2. QueueChannel có message nhưng không poller

Cho Gateway gửi tới `QueueChannel`, không cấu hình consumer/poller, và đặt reply timeout hữu hạn.

~~~text
Given: queue empty, no poller
When: gateway.reserve(command)
Then:
  - request may be accepted into queue
  - ReservationOperations.normalCalls() stays 0
  - Gateway does not get ReserveReceipt
  - bounded timeout/no-reply behavior is observed
~~~

Đây là test quan trọng vì **send success** có thể che thực tế request chưa bao giờ vào handler.

### 19.3. Output channel cố định khiến Gateway không nhận reply

Cố tình thêm sau handler:

~~~java
// Biến thể lỗi nếu Gateway đang chờ reply khác:
.handle(service, "reserve")
.channel("reservations.unconsumed.out")
~~~

Nếu kênh trên không trả reply về Gateway, handler có thể chạy và tạo receipt nhưng Gateway timeout. Test nên đo cả invocation count và caller outcome để phát hiện **reply routing failure**.

### 19.4. Không đánh đồng no-reply với rejected

Nếu handler trả `null` hoặc `void` trong luồng mà Gateway method yêu cầu `ReserveReceipt`, caller có thể không nhận normal reply. Kiểm tra chính sách `requiresReply` nếu handler có hỗ trợ và error flow theo version đang dùng.

Một message bị Filter chặn cũng có thể gây thiếu reply. Nếu rejection là hợp lệ, nên trả `ReserveReceipt(status=REJECTED)` hoặc một typed error mapping thay vì silent drop.

### 19.5. Bài test 100 calls concurrent

Với nhiều operations khác key:

~~~text
Given:
  100 commandIds khác nhau
  20 concurrent callers
  shared Spring Gateway proxy
  handler trả operationId tương ứng

Assert:
  every caller receives receipt for its own operationId
  no cross-request reply leak
  normalCalls == number of normal requests
  priorityCalls == number of priority requests
~~~

Khi dùng ExecutorChannel/remote broker, kiểm soát timeouts, correlation, thread-safety của service và metrics. Đừng dùng `MessageHeaders.ID` của envelope làm business ID.

### 19.6. Kiểm thử handler blocked lâu hơn reply timeout

Đừng chỉ tạo `Thread.sleep(5000)` bên trong DirectChannel và mong `defaultReplyTimeout=3000` tự cắt ngang. Vì send có thể đồng bộ, lời gọi vẫn chờ cho đến khi handler xong.

Để thực sự kiểm reply deadline, test nên dùng **async boundary được kiểm soát** hoặc một Gateway/broker có cơ chế chờ reply độc lập; thêm fake clock/latch hoặc synchronization phù hợp, không viết test thời gian may rủi.

## 20. Quan sát và khắc phục lỗi Gateway

Một log `Gateway invoked` không chứng minh request đã tới đúng handler, và một log `handler returned` không chứng minh caller đã nhận reply.

### 20.1. Các điểm đo

| Chỉ số/tín hiệu | Mục đích |
| --- | --- |
| `gateway_invocations_total` theo method | Bao nhiêu lời gọi vào API |
| `gateway_request_send_attempts_total` | Bao nhiêu lần thử gửi request |
| `gateway_request_send_failed_total` | Lỗi không gửi được vào channel |
| `gateway_reply_received_total` | Bao nhiêu replies được Gateway nhận |
| `gateway_reply_timeout_total` | Caller đợi quá hạn |
| `gateway_missing_reply_total` | Handler/flow không tạo ordinary reply |
| `gateway_route_normal_total` | Lưu lượng dùng default route |
| `gateway_route_priority_total` | Lưu lượng method override |
| `service_activator_invocations_total` | Handler thực chạy bao nhiêu lần |
| `business_rejections_total` | Typed terminal rejection |
| `business_effect_committed_total` | Side effects thực sự commit |
| `idempotency_reuse_total` | Duplicate dùng persisted outcome |
| `queue_depth` / `queue_oldest_age` | Congestion/chờ poller |
| `executor_rejected_tasks_total` | Executor saturation |
| `late_reply_total` | Replies sau deadline |
| `error_channel_messages_total` | Technical errors qua error flow |

Đây là **metrics gợi ý do application/observability layer định nghĩa**, không phải cam kết Spring Integration tự sinh mọi metric trong bảng. Có thể dùng Micrometer/observation instrumentation và bổ sung custom metrics.

### 20.2. Log mẫu khi route bình thường

~~~json
{
  "event": "gateway_request_routed",
  "gatewayMethod": "reserve",
  "requestChannel": "reservations.commands",
  "targetFlow": "normalReservationFlow",
  "outcome": "REPLIED",
  "replyType": "ReserveReceipt"
}
~~~

Chỉ nên log những trường đã qua policy bảo mật. `operationId`, `tenantId`, `businessCorrelationId`, `orderId` có cardinality cao và có thể nhạy cảm; không đặt chúng tùy ý vào metric tags. Logs/traces cần masking, retention và access control.

### 20.3. Quy trình debug một Gateway timeout

1. **Bean Gateway có được đăng ký?** Kiểm `@IntegrationComponentScan`, package, bean injection.
2. **Method nào được gọi?** Nó dùng default hay method-level override?
3. **Request channel name resolve được không?** Có bean/trùng tên/sai context?
4. **Channel có consumer không?** Với DirectChannel kiểm subscribers; với QueueChannel kiểm poller.
5. **Handler có được invoke?** Kiểm method binding, payload type, exceptions.
6. **Handler trả gì?** DTO, `Message<?>`, `null`, `void` hay Future?
7. **Reply đi đâu?** Có fixed output channel đang giữ receipt không?
8. **Có async boundary?** Reply đến muộn hoặc worker/thread pool nghẽn?
9. **Operation đã commit chưa?** Timeout có thể xảy ra sau commit; phải reconcile.
10. **Có retry với cùng operation ID không?** Đảm bảo không tạo side effect mới.

### 20.4. Cần phân biệt channel activity và business outcome

~~~text
Gateway method called:           1000
Messages accepted by channel:     998
Handlers invoked:                 995
Replies delivered to Gateway:     990
Business effects committed:       850
Idempotency results reused:       100
Business rejections:               45
~~~

Các số **minh họa**, không phải phép cân đối luôn đúng giữa các metrics. Có thể có one-way calls, async retries, duplicate deliveries, lost replies. Đừng suy “1000 - 990 = 10 orders mất” nếu chưa xem những request còn xử lý và outcome đã commit.


## 21. Anti-pattern về `defaultRequestChannel`

| Anti-pattern | Vì sao nguy hiểm? | Cách thay |
| --- | --- | --- |
| Coi `defaultRequestChannel` là reply channel | Gateway gửi request đúng nhưng không có đường trả kết quả | Vẽ tách request/reply topology |
| Khai báo tên channel mà không có consumer | Không ai xử lý hoặc dispatch lỗi | Khai báo flow handler và test |
| Đặt QueueChannel nhưng quên poller | Gửi thành công, Gateway chờ đến timeout | Polling endpoint hoặc loại channel khác |
| Tin rằng default là fallback khi override bị lỗi | Method ưu tiên hỏng nhưng không tự chạy normal | Sửa route cụ thể, error policy rõ |
| Hai DirectChannel subscribers nhưng mong fan-out | Point-to-point dispatch không broadcast | PublishSubscribe/Recipient List/Scatter-Gather |
| Đổi mọi methods sang priority bằng cấu hình chung | Phá contract và quota | Method-level override hoặc Router có policy |
| Gắn fixed output channel ở cuối Gateway flow | Reply đi khỏi temporary reply channel | Thiết kế bridge/reply path đúng |
| Dùng `void` rồi báo “đã commit” | Method có thể chỉ enqueue | Typed outcome/status API |
| Trả `null` khi hết hàng | Gateway có thể timeout | `ReserveReceipt(REJECTED)` có reason |
| Chỉ kiểm `receipt.status` trong tests | Không bắt được route nhầm | Assert marker và handler counters |
| Cho request channel gánh authorization | Người gọi có thể bypass controls | AuthN/AuthZ tại trusted boundary |
| Dùng `orderId` làm key dedup cho mọi operation | Chặn nhầm CANCEL/AMEND | Stable operation-level key |
| Dùng `MessageHeaders.ID` để retry | Redelivery có envelope ID mới | Giữ business operation ID |
| Nghĩ Gateway timeout là operation rollback | Commit có thể đã xảy ra | Reconcile và idempotent retry |
| `defaultReplyTimeout` được xem là hard limit cho DirectChannel | Handler đồng bộ có thể block lâu | Service I/O deadlines và async design |
| Xem QueueChannel in-memory là durable broker | Restart có thể mất queued requests | Durable messaging khi cần |
| Copy Java `replyChannel` qua Kafka/JMS | Lỗi serialization hoặc lộ topology | Transport reply-to + correlation |
| Dùng raw tenant header client khai để route | Cross-tenant data leakage | Trusted identity, ACL và validation |
| PublishSubscribe fan-out với một Gateway reply | Nhiều results không được tổng hợp | Aggregator/Scatter-Gather |
| Filter drop một child trước Aggregator | Batch reply không đủ | Typed child rejection outcome |
| Retry vô hạn lỗi validation | Retry storm, queue nghẽn | Terminal reject + bounded retry |
| Chỉ test một JVM rồi kết luận multi-instance idempotent | Bỏ sót crash/rebalance/race | Shared DB/transport integration tests |
| Log toàn bộ headers để debug Gateway | Lộ secrets và dữ liệu cá nhân | Safe structured logs |

## 22. Checklist trước khi triển khai

- [ ] `@MessagingGateway` đặt trên interface đúng, Gateway bean được component-scan/đăng ký.
- [ ] `defaultRequestChannel` trỏ đến một request destination có nghĩa và được khai báo/resolve đúng.
- [ ] Mọi method không override dùng default theo đúng contract.
- [ ] Mọi `@Gateway(requestChannel = "...")` override được test độc lập.
- [ ] Có consumer/IntegrationFlow thực sự nhận message trên mỗi request channel.
- [ ] Không nhầm `defaultRequestChannel`, `defaultReplyChannel` và temporary `replyChannel`.
- [ ] Nếu method trả kết quả, **reply** quay đúng caller và đúng schema.
- [ ] Không vô tình chuyển reply sang một output QueueChannel không có bridge về Gateway.
- [ ] Có chính sách cho `null`/`void`/no-reply và `requiresReply` ở handler nếu dùng.
- [ ] Business rejection trả typed outcome thay vì silent timeout.
- [ ] Request/send timeout và reply timeout có SLA/time budget riêng.
- [ ] Với DirectChannel, đã giới hạn thời gian I/O bên trong handler.
- [ ] Với ExecutorChannel, executor được quản lý, có backpressure, tracing/security context.
- [ ] Với QueueChannel/PriorityChannel, có poller, capacity, retry và durability policy.
- [ ] Với PublishSubscribeChannel, fan-out và multiple replies được xử lý rõ.
- [ ] Method arguments mapping có `@Payload`/`@Header` khi cần, không nhận nhầm dữ liệu ngoài làm trusted metadata.
- [ ] AuthN/AuthZ/tenant/priority quota được kiểm ở business boundary phù hợp.
- [ ] Business operation ID giữ nguyên qua client retry, broker redelivery và đổi lane.
- [ ] Side effects được bảo vệ bởi shared idempotency/transaction tại owner.
- [ ] Technical failures khác terminal business rejections; có retry budget và error handling.
- [ ] Late replies có policy reconcile/discard, không phát kết quả cuối lặp sai.
- [ ] Splitter/Aggregator bảo toàn group/child/operation IDs, có timeout và closed-group policy.
- [ ] Remote reply-to/correlation trên HTTP/JMS/AMQP/Kafka được mapping và bảo mật.
- [ ] Không serialize Java `replyChannel`/`errorChannel` object sang broker.
- [ ] Unit tests kiểm business service; Spring context tests kiểm default và override routes.
- [ ] Negative tests kiểm no subscriber, no poller, wrong reply output, null-return.
- [ ] Có metrics riêng cho request send, handler invoke, reply receive, timeout và business commit.
- [ ] Không dùng high-cardinality IDs hoặc PII trong metric labels; logs theo policy.

## 23. Bài tập thực hành: Gateway mặc định cho thanh toán đơn hàng

Một dịch vụ Order Processing dùng Messaging Gateway để thực hiện ba thao tác:

- `authorizePayment(command)`: kiểm và giữ hạn mức thanh toán.
- `capturePayment(command)`: chốt khoản thanh toán đã authorize.
- `refundPayment(command)`: hoàn tiền với policy kiểm tra chặt hơn.

Một interface Gateway mong muốn sử dụng **default request channel** cho authorize/capture, còn refund đi qua **kênh riêng có xác thực quyền và kiểm toán**.

### 23.1. Thiết kế giao diện

Ví dụ contract:

~~~java
record PaymentCommand(
    String tenantId,
    String operationId,
    String orderId,
    long amountMinor,
    String currency
) {}

record PaymentReceipt(
    String operationId,
    String status,
    String reasonCode
) {}
~~~

**Yêu cầu:**

1. Tạo `@MessagingGateway(defaultRequestChannel = "payments.commands")`.
2. Khai báo hai methods `authorizePayment` và `capturePayment` dùng default channel; thêm cách xác định operation type trong payload/header **có xác thực** để Router bên trong phân biệt hai lệnh.
3. Khai báo `@Gateway(requestChannel = "payments.refunds")` cho `refundPayment`.
4. Vẽ hai IntegrationFlows có input channels `payments.commands` và `payments.refunds`, Router/Service Activators tương ứng.
5. Viết Java DSL cho mỗi flow và một Gateway method trả `PaymentReceipt`.
6. Mô tả vì sao chỉ kiểm tên method `refundPayment` **không đủ** cho authorization; cần principal/quyền/limits ở handler.
7. Viết JUnit tests chứng minh authorize và capture đi default, refund đi override; assert counters của ba handlers.
8. Kiểm thử refund cùng operation ID bị gọi lại sau lost reply: payment backend không refund hai lần.
9. Giải thích vì sao không tạo operation ID mới mỗi lần Gateway retry.
10. Cấu hình một QueueChannel không có poller để quan sát Gateway chờ reply; thêm poller và chứng minh kết quả thay đổi.
11. Cố tình gắn fixed output channel không bridge về Gateway và tạo test bắt timeout, không dùng test timeout vô hạn.
12. Giải thích tại sao `defaultReplyTimeout` không tự cắt ngang một handler chạy trong DirectChannel.
13. Thiết kế typed `PaymentReceipt(status=REJECTED)` khi amount invalid, khác technical error khi payment API 503.
14. Với một batch gồm năm payment operations, dùng Splitter/Aggregator và typed child outcomes để không bỏ reply của một child invalid.
15. Đưa thêm Gateway `void audit(AuditEvent)` và giải thích vì sao `void` không đồng nghĩa async đã commit.
16. Thiết kế metrics cho Gateway route, reply timeout, idempotency hit, refund conflict và business commit.
17. Viết test bảo mật khẳng định tenant/refund headers từ client không bypass authorization hoặc lộ sang outgoing broker.
18. Đề xuất cách migrate từ DirectChannel sang ExecutorChannel mà không mất reply/correlation và không tạo retry storm.

### 23.2. Điều kiện nghiệm thu

Một bài làm đạt yêu cầu khi có thể chứng minh **ba tính chất độc lập**:

1. **Routing correctness:** mỗi Gateway method gửi vào request channel đúng default/override.
2. **Request–reply correctness:** mỗi method yêu cầu reply nhận đúng typed outcome, không bị route sang queue khác hoặc timeout vô lý.
3. **Business-effect correctness:** retry/redelivery/multiple instances không nhân đôi thao tác thanh toán, hoàn tiền hay tạo hai final decisions.

Không dùng “API trả 200” hoặc “unit test của service pass” làm bằng chứng cho cả ba tính chất cùng lúc.

## 24. Tổng kết

**Gateway default request channel** là một cấu hình quan trọng của interface-level Messaging Gateway trong Spring Integration: nó xác định **request sẽ đi vào kênh nào khi một method không chỉ định channel riêng**. Method có `@Gateway(requestChannel = "...")` có thể ghi đè lựa chọn này cho use case cụ thể. Cách tổ chức này giúp caller dùng một API Java đơn giản, còn hệ thống tích hợp chịu trách nhiệm routing, validation, handler invocation và reply.

Tuy nhiên, **request destination không phải reply destination**. Một Gateway cần trả kết quả phải có đường reply đúng về caller; `DirectChannel`, `ExecutorChannel` và `QueueChannel` quyết định threading và timeout khác nhau. Gateway có thể timeout dù business đã commit, vì vậy retry cần stable business operation ID và idempotency tại owner. Khi có Router, Filter, Splitter, Aggregator, Gateway/error channel và remote adapters, hãy bảo toàn correlation, phân biệt typed business rejection với lỗi kỹ thuật, kiểm thử cả route mặc định và override, cũng như negative/late-reply paths.

Một triển khai tốt không dừng ở dòng `@MessagingGateway(defaultRequestChannel = "reservations.commands")`. Nó có **kênh có consumer thực, hợp đồng reply rõ, timeout có ý nghĩa, bảo mật đúng boundary, idempotency và các bài kiểm thử chứng minh route đúng lẫn outcome đúng**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Messaging Gateway, Request-Reply, Service Activator, Content-Based Router, Correlation Identifier, Idempotent Receiver, Aggregator); Spring Integration Reference về Messaging Gateways, `@MessagingGateway`, `@Gateway`, Integration Component Scan, Message Channels, Java DSL, Service Activators, Retry/Error Handling và Testing; Spring Framework về application context và transaction management; Spring Messaging về `Message`/`MessageHeaders`; Java SE về records và concurrency.









