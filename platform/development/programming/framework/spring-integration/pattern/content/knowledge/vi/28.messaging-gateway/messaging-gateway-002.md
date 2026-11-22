# Gateway gửi one-way message

## 1. Tình huống: gọi một phương thức Java để phát thông điệp, không chờ kết quả nghiệp vụ

Ứng dụng đặt hàng cần thông báo rằng một đơn đã được tiếp nhận. Mã application service muốn gọi một API Java dễ hiểu:

~~~java
orderSubmissionGateway.submit(command);
~~~

Phần còn lại của hệ thống có thể xử lý sự kiện bằng Spring Integration: validate, Filter, Router, chuyển đổi payload, đưa vào broker, cập nhật audit hoặc gửi thông báo. Tuy nhiên, phía gọi **không cần nhận đối tượng phản hồi nghiệp vụ** ngay ở lần gọi này.

Đó là một trường hợp điển hình của **Messaging Gateway gửi one-way message**: một giao diện Java được Spring Integration biến thành điểm đưa message vào integration flow, với phương thức **không yêu cầu reply payload**.

~~~mermaid
flowchart LR
    CALL["Application Service"] --> G["One-way Messaging Gateway"]
    G --> C["Request Channel"]
    C --> V["Filter / Transformer / Router"]
    V --> H["Consumer / Outbound Adapter"]
    H --> S["Side effect or durable handoff"]
~~~

Ví dụ một command:

~~~text
SubmitOrder(
  operationId = "SUBMIT-901",
  orderId     = "ORD-901",
  tenantId    = "TENANT-A",
  amountVnd   = 850000
)
~~~

Service gọi phương thức trả về `void`. Nhưng **`void` không có nghĩa message chắc chắn được lưu bền, xử lý thành công, không thể thất bại, hoặc luôn chạy bất đồng bộ**. Những bảo đảm đó phụ thuộc channel, consumer, adapter, transaction và error-handling contract.

Bài thuộc chương **Messaging gateway** của module `SPRING_INTEGRATION_PATTERN`. Module tập trung học Enterprise Integration Patterns với Spring Integration để tạo message flow ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý.

### Mục tiêu

Sau bài này, bạn sẽ:

1. Hiểu **one-way message**, sự khác biệt giữa `void` Gateway và request–reply Gateway.
2. Phân biệt **one-way**, **asynchronous**, **fire-and-forget**, **durable enqueue**, **broker acknowledgment** và **business completion**.
3. Tạo `@MessagingGateway` với phương thức `void` và request channel bằng Spring Integration 6.x.
4. So sánh `DirectChannel`, `ExecutorChannel` và `QueueChannel` về thread, latency, failure và persistence.
5. Thiết kế đường xử lý lỗi khi caller không nhận một reply nghiệp vụ.
6. Bảo vệ side effect bằng idempotency, retry/backoff, transport acknowledgment và audit.
7. Viết unit/integration tests xác minh command đi đúng channel và không ngộ nhận việc return `void` là hoàn tất nghiệp vụ.

## 2. Một chiều là gì?

Trong Enterprise Integration Patterns, **one-way** nói về **kiểu trao đổi message**: bên gửi phát một message và không yêu cầu một message trả lời tương ứng theo giao thức nghiệp vụ của lần gửi đó.

~~~text
Sender -------- Command/Event --------> Receiver
       (không yêu cầu business reply ngay)
~~~

Nó khác **request–reply**:

~~~text
Sender -------- Request -------------> Receiver
Sender <-------- Reply ---------------- Receiver
~~~

Một one-way request vẫn có thể kích hoạt hàng loạt hành động về sau, bao gồm các sự kiện mới hoặc thông báo kết quả qua một kênh khác. Chúng là **những message độc lập hoặc một workflow bất đồng bộ được liên kết bằng identity/correlation**, không phải “reply bắt buộc” của phương thức Java ban đầu.

### 2.1. Những khái niệm hay bị đánh đồng

| Khái niệm | Ý nghĩa | Không tự đảm bảo |
|---|---|---|
| **One-way** | Không yêu cầu business reply cho lần gửi. | Không đồng nghĩa asynchronous. |
| **Gateway method `void`** | Java caller không nhận return value nghiệp vụ. | Không đồng nghĩa mọi exception bị nuốt. |
| **Synchronous dispatch** | Consumer chạy trong lời gọi/cùng thread theo semantics channel. | Không cần phải có reply. |
| **Asynchronous dispatch** | Handoff qua executor/queue/broker, caller và consumer có thể chạy khác thread. | Không tự durable. |
| **Fire-and-forget** | Cách gọi thân mật khi caller không chờ kết quả. | Không chứng minh message không mất. |
| **Durable enqueue** | Hạ tầng lưu message bền theo contract. | Chưa chứng minh consumer hoàn tất. |
| **Broker ack/confirm** | Broker/transport xác nhận một mốc. | Chưa chứng minh business effect đã commit. |
| **Business completion** | Có authoritative business receipt/state. | Không suy ra chỉ từ gateway return. |

### 2.2. Hai đoạn code trông giống nhau, nhưng semantics khác

~~~java
// Cả hai đều là Java API trả void.
gateway.submit(command);

// Bên dưới có thể là DirectChannel đồng bộ,
// hoặc ExecutorChannel, broker adapter, queue...
~~~

**Chữ ký Java chỉ xác định caller không nhận reply payload**. Channel và endpoint mới xác định cách dispatch, thời điểm return, error propagation và mốc thông điệp được chấp nhận.

### 2.3. One-way không cấm theo dõi kết quả

Với tác vụ dài, thiết kế một kênh theo dõi riêng:

~~~text
Command SUBMIT-901
  -> Gateway one-way
  -> Accepted / queued
  -> Background order processing
  -> OrderProcessed event (operationId=SUBMIT-901)
  -> Status projection / notification
~~~

Caller có thể kiểm tra kết quả bằng query/status API hoặc nhận event callback sau này. Khi đó phải phân biệt **operation ID**, **delivery attempt**, **correlation ID** và **business receipt**.

## 3. Vì sao dùng Messaging Gateway thay vì gọi thẳng một MessageChannel?

Với Spring Integration, một application service có thể thao tác trực tiếp:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

boolean acceptedByChannel = channel.send(
        MessageBuilder.withPayload(command).build());
~~~

Cách này làm application service biết tới Spring Messaging API và phải tự tạo message/header. Một **Messaging Gateway interface** che lớp messaging, giúp application service chỉ biết Java method có ý nghĩa nghiệp vụ:

~~~java
interface OrderSubmissionGateway {
    void submit(OrderSubmission command);
}
~~~

Ở runtime, Spring Integration tạo **gateway proxy**, chuyển method invocation thành một message gửi qua request channel.

### 3.1. Lợi ích

- **Tách coupling:** application service ít phụ thuộc API `MessageBuilder`/`MessageChannel`.
- **Ý nghĩa rõ:** phương thức `submit(...)` thể hiện intent tốt hơn một lệnh `send(...)` trừu tượng.
- **Tập trung metadata:** cấu hình routing, header mapping, validation tại ingress boundary.
- **Dễ kiểm thử:** có thể fake interface ở unit test, chạy Spring flow ở integration test.
- **Có thể thay channel/adapters:** nhiều thay đổi hạ tầng không cần sửa application caller.

### 3.2. Giới hạn

- Không tự đảm bảo DB + broker atomicity.
- Không tự tạo durable queue.
- Không tự biến tác vụ thành async vì return type là `void`.
- Không tự chống duplicate.
- Không tự có retry, error channel hoặc observability đúng hợp đồng.
- Không tự tạo business reply nếu sender không yêu cầu.

Gateway là **một ranh giới API**, không phải tất cả tính chất của hệ thống truyền message.

## 4. Thiết kế hợp đồng một chiều

### 4.1. Command và event không giống nhau

Một Gateway có thể phát:

- **Command:** yêu cầu một consumer thực hiện tác vụ, ví dụ `SubmitOrder`, `SendNotification`. Thường cần một bên có trách nhiệm xử lý.
- **Event:** thông báo điều đã xảy ra, ví dụ `OrderPlaced`. Có thể có nhiều subscribers và không có người nhận duy nhất.

Nếu phương thức là `sendOrderNotification(...)`, nên xác định nó đang tạo **command yêu cầu gửi thông báo** hay **event đơn hàng đã xảy ra**. Một tên API mơ hồ có thể làm sai logic retry, idempotency và ownership.

### 4.2. Một contract mẫu

~~~text
Operation: SubmitOrder
  operationId: stable logical command ID
  orderId: business order ID
  amountVnd: positive integer in VND
  authenticatedTenant: derived at trusted boundary

Gateway:
  Java method: void submit(OrderSubmission command)
  request channel: orders.submit.input

Handoff semantics:
  Demo: synchronous DirectChannel dispatch
  Production: choose explicit durability/ack contract

Failures:
  Invalid command -> reject/quarantine with reason
  Technical failures -> bounded retry/error handling
  Business completion -> separate status/receipt/event
~~~

**Quan trọng:** Nếu caller muốn biết lệnh đã được **durably accepted**, thiết kế API chỉ có `void` có thể chưa đủ rõ; có thể cần một outcome `AcceptedReceipt` hoặc mô hình transactional outbox. Trả `void` sau khi gửi vào channel memory không phải lời hứa dữ liệu được ghi bền.

### 4.3. Operation identity khác Spring Message ID

~~~text
Business operationId = SUBMIT-901
Spring MessageHeaders.ID, attempt #1 = UUID-A
Spring MessageHeaders.ID, retry #2   = UUID-B
~~~

Cùng một logical command có thể đi qua nhiều Spring message instances. Với tác vụ gây side effect như tính phí hoặc ghi đơn, downstream cần **stable operationId/business idempotency key**, không dedupe bằng runtime UUID.

### 4.4. Không lấy tenant được tự khai làm quyền

Một command có field `tenantId=TENANT-A` không tự chứng minh caller được phép thực hiện với tenant A. Ở trusted ingress, phải bind identity với principal/adapter context rồi kiểm tra request. Trong demo có thể đưa tenant field vào command để minh họa nhưng **không được coi đó là authorization**.

## 5. Java: một one-way Gateway cơ bản

Ví dụ dùng Java 17+, Spring Framework/Spring Integration 6.x và Spring Test/JUnit 5. Các class/record/interface được hiểu là ở cùng một package và tách file riêng khi đưa vào dự án thực tế.

### 5.1. Payload command

~~~java
import java.math.BigDecimal;

record OrderSubmission(
        String operationId,
        String orderId,
        BigDecimal amountVnd) {

    OrderSubmission {
        if (operationId == null || operationId.isBlank()
                || orderId == null || orderId.isBlank()
                || amountVnd == null
                || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException(
                    "INVALID_ORDER_SUBMISSION");
        }
    }
}
~~~

Không có Spring Messaging import trong `OrderSubmission`: đây là business/application command. DTO validator ở constructor chỉ đảm bảo **invariants đơn giản**; ở raw ingress cần kiểm tra authentication, schema và malformed payload trước khi tạo typed command.

### 5.2. Gateway interface với `void`

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
interface OrderSubmissionGateway {

    @Gateway(requestChannel = "orders.submit.input")
    void submit(OrderSubmission command);
}
~~~

**Điểm chính:** `@MessagingGateway` khai báo integration gateway interface; `@Gateway(requestChannel=...)` ánh xạ method call tới channel. Chữ ký `void submit(...)` biểu thị **không có business return value cần đọc**.

Không cần để application service tự tạo `Message<OrderSubmission>` chỉ để gọi API này. Nhưng nó vẫn cần xử lý lỗi và xác định một operation ID ổn định ở nguồn thích hợp.

### 5.3. Service gọi Gateway

~~~java
import java.math.BigDecimal;

final class CheckoutApplicationService {
    private final OrderSubmissionGateway gateway;

    CheckoutApplicationService(OrderSubmissionGateway gateway) {
        this.gateway = gateway;
    }

    void submitOrder(String orderId, String operationId) {
        gateway.submit(new OrderSubmission(
                operationId,
                orderId,
                new BigDecimal("850000")));

        // Không được từ đó khẳng định Payment/Inventory hoàn tất.
        // Tùy channel, dispatch có thể đồng bộ hoặc đã handoff.
    }
}
~~~

Một command `submit(...)` bị gọi lại do HTTP retry phải được cấp **cùng operationId** nếu là cùng logical operation. Đừng sinh UUID mới bên trong handler mỗi lần nhận rồi coi đó là đơn mới.

## 6. Spring Integration Java DSL: xử lý one-way qua DirectChannel

### 6.1. Sơ đồ thực thi đồng bộ

~~~mermaid
sequenceDiagram
    participant A as Application Service
    participant G as One-way Gateway Proxy
    participant C as DirectChannel
    participant H as Message Handler
    A->>G: submit(command): void
    G->>C: Message(command)
    C->>H: invoke handler in caller thread
    H-->>C: return normally
    C-->>G: send completed
    G-->>A: return void
    Note over A,H: Không có business reply payload
~~~

Ở ví dụ này, handler chạy **đồng bộ** với lời gọi vào `DirectChannel`. Vì vậy caller có thể bị giữ đến khi handler kết thúc. Không trả dữ liệu nghiệp vụ **khác** với không chờ công việc.

### 6.2. Probe ghi lại command để quan sát

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class SubmissionProbe {
    private final List<OrderSubmission> received =
            new CopyOnWriteArrayList<>();

    void record(OrderSubmission command) {
        received.add(command);
    }

    List<OrderSubmission> snapshot() {
        return List.copyOf(received);
    }
}
~~~

`SubmissionProbe` dùng để kiểm thử, **không phải database hoặc broker**. Nó không bảo đảm durability khi JVM restart, không phân quyền tenant và không bảo vệ idempotency.

### 6.3. Cấu hình Gateway, channel và terminal handler

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OneWayGatewayConfiguration {

    @Bean(name = "orders.submit.input")
    MessageChannel orderSubmitInput() {
        return new DirectChannel();
    }

    @Bean
    SubmissionProbe submissionProbe() {
        return new SubmissionProbe();
    }

    @Bean
    IntegrationFlow processSubmittedOrders(SubmissionProbe probe) {
        return IntegrationFlow.from("orders.submit.input")
                .handle(
                        OrderSubmission.class,
                        (command, headers) -> {
                            probe.record(command);
                            return null; // Terminal one-way handler.
                        })
                .get();
    }
}
~~~

Đặt `OrderSubmissionGateway` và configuration trong **một package demo được scan** hoặc cấu hình phạm vi scan rõ. `@IntegrationComponentScan` tìm những interface có `@MessagingGateway` và đăng ký proxy; `@EnableIntegration` bật infrastructure cần thiết.

**Lưu ý:** Handler trên trả `null` để biểu thị **terminal side-effect endpoint** (không tạo reply payload). Đây là lựa chọn có chủ đích của demo. Không coi giá trị `null` là business receipt “đã xử lý xong” của hệ thống ngoài.

### 6.4. Điều gì xảy ra khi gọi Gateway?

~~~java
OrderSubmission command = new OrderSubmission(
        "SUBMIT-901",
        "ORD-901",
        new java.math.BigDecimal("850000"));

gateway.submit(command);
~~~

Một lời gọi thành công qua `DirectChannel` ở ví dụ sẽ đi qua các mốc:

1. Java method trên gateway proxy được gọi.
2. Gateway xây message mang payload `OrderSubmission`.
3. Message được đưa đến `orders.submit.input`.
4. `DirectChannel` dispatch đến handler đã subscribe.
5. Handler ghi `SubmissionProbe` rồi trả `null`.
6. Gateway method trả `void`.

Không có bước trả `OrderResult` hay `PaymentReceipt`. Nếu handler thật là một tác vụ lâu, caller sẽ **đợi thao tác đó ở đường đồng bộ**, trừ khi chèn ranh giới asynchronous.

### 6.5. Khi downstream ném exception trong DirectChannel

Nếu handler ném `IllegalStateException` hoặc một Spring Messaging exception, việc gọi `void submit(...)` vẫn có thể **ném lỗi về phía caller** qua gateway/synchronous dispatch, có thể được framework bọc trong `MessagingException`.

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Gateway
    participant C as DirectChannel
    participant H as Handler
    A->>G: submit(command)
    G->>C: send
    C->>H: invoke
    H--xC: exception
    C--xG: propagate
    G--xA: exception (possibly wrapped)
~~~

**Vì vậy câu “gateway one-way không có reply nên không có lỗi” là sai.** `void` chỉ loại bỏ business return value; exception propagation phụ thuộc synchronous/asynchronous boundary và cấu hình endpoint.

## 7. Integration test cho one-way Gateway đồng bộ

### 7.1. Chỉ có một command đi đến handler

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(OneWayGatewayConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class OneWayGatewayIntegrationTest {

    @Autowired
    OrderSubmissionGateway gateway;

    @Autowired
    SubmissionProbe probe;

    @Test
    void voidGatewayDispatchesCommandWithoutBusinessReply() {
        OrderSubmission command = new OrderSubmission(
                "SUBMIT-901",
                "ORD-901",
                new BigDecimal("850000"));

        gateway.submit(command);

        assertEquals(1, probe.snapshot().size());
        assertEquals(command, probe.snapshot().get(0));
    }
}
~~~

Ở đây assert ngay sau method call hợp lý **vì ví dụ dùng `DirectChannel` đồng bộ**. Nếu thay bằng `ExecutorChannel` hoặc broker, test này không còn được phép giả định handler đã chạy khi `submit(...)` trở về.

### 7.2. Một gateway method có thể được unit test bằng fake

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CheckoutApplicationServiceTest {

    @Test
    void callsGatewayWithStableOperationId() {
        List<OrderSubmission> sent = new ArrayList<>();
        OrderSubmissionGateway fake = sent::add;
        CheckoutApplicationService service =
                new CheckoutApplicationService(fake);

        service.submitOrder("ORD-901", "SUBMIT-901");

        assertEquals(1, sent.size());
        assertEquals("SUBMIT-901",
                sent.get(0).operationId());
        assertEquals("ORD-901",
                sent.get(0).orderId());
        assertEquals(new BigDecimal("850000"),
                sent.get(0).amountVnd());
    }
}
~~~

Unit test này chứng minh application service gọi đúng **Java interface**, không chứng minh Spring proxy, channel subscription, broker hoặc business side effect. Phân biệt phạm vi các cấp test để không gán cho một unit test những bảo đảm mà nó chưa kiểm tra.

### 7.3. Một phương thức `void` vẫn có thể throw

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OneWayGatewayContractTest {

    @Test
    void gatewayInterfaceDoesNotPromiseNeverToThrow() {
        OrderSubmissionGateway failing = command -> {
            throw new IllegalStateException(
                    "SYNCHRONOUS_DISPATCH_FAILED");
        };

        assertThrows(IllegalStateException.class, () ->
                failing.submit(new OrderSubmission(
                        "SUBMIT-2", "ORD-2",
                        new BigDecimal("100000"))));
    }
}
~~~

Ví dụ này minh họa thuộc tính của **interface Java**. Với Spring Gateway thật, exception có thể được bọc theo framework; không nên assert tên exception cụ thể mà không kiểm tra cause chain và configuration thực tế.

### 7.4. Không trả kết quả khác với không biết trạng thái

Nếu handler trong demo chỉ ghi một probe, ta biết probe đã được gọi. Trong production, handler có thể:

- Gọi API ngoài và chờ response.
- Ghi outbox vào database.
- Gửi message đến outbound broker adapter.
- Enqueue vào một in-memory channel khác.

**Mốc thành công khác nhau**. Test phải xác nhận đúng mốc mà application contract yêu cầu, ví dụ **durable outbox persisted** hoặc **broker confirm**, không chỉ “gateway method returned”.

## 8. Khi cần asynchronous: ExecutorChannel

### 8.1. Thêm ranh giới thread

Nếu caller không muốn chờ một handler dài, có thể chọn asynchronous channel/adapter.

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Void Gateway
    participant E as ExecutorChannel
    participant W as Worker Thread
    A->>G: submit(command)
    G->>E: dispatch to executor
    E-->>G: task submitted/accepted
    G-->>A: return void
    E->>W: run message handler
    W->>W: process command
    Note over A,W: Caller may return before processing is complete
~~~

Điều mới là **ranh giới executor**. Chữ ký Java vẫn là `void`; nguyên nhân asynchronous không phải vì `void` mà vì `ExecutorChannel` dispatch qua thread pool.

### 8.2. Ví dụ executor có giới hạn

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.core.task.TaskExecutor;

import java.util.concurrent.ThreadPoolExecutor;

@Configuration
class AsyncOrderFlowConfiguration {

    @Bean(name = "orderGatewayExecutor")
    ThreadPoolTaskExecutor orderGatewayExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("orders-oneway-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean(name = "orders.async.input")
    MessageChannel asyncOrderInput(
            @Qualifier("orderGatewayExecutor")
            TaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    IntegrationFlow asyncOrderHandler(SubmissionProbe probe) {
        return IntegrationFlow.from("orders.async.input")
                .handle(OrderSubmission.class,
                        (command, headers) -> {
                            probe.record(command);
                            return null;
                        })
                .get();
    }
}
~~~

Cấu hình trên chỉ minh họa **thread-handoff**; phải ghép với bean `SubmissionProbe`, gateway interface trỏ tới `orders.async.input` và infrastructure phù hợp trong context demo riêng.

### 8.3. Gateway interface tương ứng

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.Gateway;

@MessagingGateway
interface AsyncOrderSubmissionGateway {

    @Gateway(requestChannel = "orders.async.input")
    void submit(OrderSubmission command);
}
~~~

Trên một ứng dụng có nhiều gateways, giới hạn phạm vi component scanning hoặc đặt các ví dụ trong package/context riêng. Không register hai interface cùng bean name rồi dựa vào behavior ngẫu nhiên.

### 8.4. Không phải “gửi thành công” nếu executor đã từ chối

Pool/queue có capacity hữu hạn. Khi quá tải, `ExecutorChannel` có thể không submit được task và lỗi rejection có thể xuất hiện ngay khi gọi Gateway. Do đó:

~~~text
Gateway void return
    ≠ job always queued
    ≠ job processed
    ≠ job persisted across restart
~~~

Một thread pool có capacity hữu hạn giúp quan sát overload. Nhưng **nó không durable**: khi process chết, những task đang chờ trong memory có thể mất. Production cần policy retry, fallback, backpressure và, nếu yêu cầu reliability qua restart, một durable handoff.

### 8.5. Exception của worker có còn ném về caller không?

Nếu task đã được giao cho worker và **worker ném exception sau khi caller trở về**, caller không thể nhận exception đồng bộ như với `DirectChannel`. Spring Integration có thể publish `ErrorMessage` đến error channel theo error-handling context/configuration, hoặc dùng handler riêng; **phải cấu hình và kiểm thử**, không mặc định mọi async error tự về cùng một nơi.

~~~text
Caller returns
       |
       v
Async worker fails
       |
       +-> configured error channel / failure handler
       +-> retry/recovery/DLQ according to endpoint/adapter
       +-> alert & audit unresolved operation
~~~

**Thiết kế lỗi là phần bắt buộc của one-way asynchronous flow** vì không có immediate business reply để biểu diễn thất bại.

### 8.6. Kiểm thử async đúng cách

Với async, không dùng:

~~~java
gateway.submit(command);
assertEquals(1, probe.snapshot().size()); // Có thể race.
~~~

Nên dùng `CountDownLatch`, `BlockingQueue.poll(timeout)`, hoặc cơ chế await có deadline. Nếu test dùng message handler đợi latch, hãy giải phóng latch ở `finally` để không treo các worker threads. Không dùng `Thread.sleep(...)` rồi coi là chứng minh handler đã xử lý bền vững.
## 9. QueueChannel: tách thời điểm gửi và nhận, nhưng chưa chắc durable

### 9.1. Store-and-forward trong memory

`QueueChannel` của Spring Integration có thể nhận message vào queue và để một consumer/poller lấy ra về sau.

~~~text
Caller -> Gateway (void) -> QueueChannel (in-memory queue)
                                 |
                           scheduled poller
                                 |
                                 v
                           Message handler
~~~

Khác `DirectChannel`, consumer có thể chạy sau đó trong poller thread. Khác `ExecutorChannel`, queue có semantics **polling/storage của channel**, không chỉ submit task tới executor.

**Nhưng QueueChannel thông thường không phải durable message broker.** Một queue trong memory có thể mất dữ liệu khi JVM restart; phải dùng message store/persistent channel/broker phù hợp nếu contract yêu cầu phục hồi sau crash.

### 9.2. Ví dụ QueueChannel và polling consumer

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
class QueuedOrderConfiguration {

    @Bean(name = "orders.queued.input")
    MessageChannel queuedOrderInput() {
        return new QueueChannel(100);
    }

    @ServiceActivator(
            inputChannel = "orders.queued.input",
            poller = @Poller(fixedDelay = "1000"))
    public void consumeQueuedOrder(OrderSubmission command) {
        // Giả lập side effect; production cần transaction,
        // idempotency, error/retry và monitoring.
        System.out.println("Handled order " + command.orderId());
    }
}
~~~

Đây là ví dụ rút gọn cho **pollable channel**. Khi chạy trong Spring Integration context có các infrastructure bean tương ứng, poller lấy message ra và gọi handler. Trong bài học thật, nên thay `System.out.println` bằng structured logs đã sanitize và một application handler rõ ràng.

### 9.3. Gateway trỏ vào queue

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.Gateway;

@MessagingGateway
interface QueuedOrderSubmissionGateway {

    @Gateway(requestChannel = "orders.queued.input")
    void submit(OrderSubmission command);
}
~~~

`submit(...)` có thể trở về khi message được nhận vào queue, **trước khi poller gọi consumer**. Không nên ghi `orderStatus=COMPLETED` ở caller chỉ vì lời gọi đã trở về.

### 9.4. Queue full và send timeout

Nếu queue có capacity 100 và đã đầy, một lần gửi tiếp có thể **block/timeout/thất bại theo send contract và cấu hình timeout của Gateway/channel**. Không phải mọi queue sẽ chấp nhận mãi.

Một runbook vận hành cần:

- Queue depth hiện tại và capacity.
- Consumer throughput, poller state và backlog age.
- Thời gian enqueue, failure/timeout count.
- Recovery khi poller stop hoặc consumer throw.
- Backpressure lên caller/ingress.
- Chính sách retry không làm trùng side effect.

Không biến queue thành “vùng đệm vô hạn”; nếu không kiểm soát capacity và retention, một sự cố consumer có thể làm cạn tài nguyên.

### 9.5. Channel memory và durable queue là hai hợp đồng khác

| Thiết kế | Có thể return trước handler? | Bền qua process restart? | Cần chính sách lỗi? |
|---|---|---|---|
| `DirectChannel` | Thường không nếu handler đồng bộ. | Không phải storage. | Có. |
| `ExecutorChannel` | Có thể. | Không mặc định. | Có; lỗi async khó trả caller. |
| `QueueChannel` trong memory | Có thể. | Không mặc định. | Có; polling/retry/backlog. |
| Persistent message store/queue | Có thể. | Tùy store/transaction config. | Có; ack/redelivery/idempotency. |
| External broker | Có thể. | Tùy durability, retention, confirms và consumer config. | Có; broker acknowledgment khác business commit. |

Không đưa ra lời hứa “exactly-once” chỉ vì dùng một hàng đợi có tên “persistent”.

## 10. One-way Gateway gửi qua Kafka, RabbitMQ hoặc JMS

Trong ứng dụng thực tế, Gateway thường phát command vào một Spring Integration flow có **outbound channel adapter**, chẳng hạn:

~~~mermaid
flowchart LR
    A["Application Service"] --> G["void Messaging Gateway"]
    G --> C["Request Channel"]
    C --> V["Validate + Enrich headers"]
    V --> S["Serializer / Outbound Adapter"]
    S --> B[("Kafka / RabbitMQ / JMS")]
    B --> R["Inbound Consumer"]
    R --> I["Idempotent Business Handler"]
~~~

One-way API không phụ thuộc việc kết nối tới broker nào. Tuy nhiên **message acknowledgment và error semantics do adapter/broker quyết định**, không do Java return type.

### 10.1. Mốc của outbound publish

~~~text
T0: Gateway method invoked.
T1: Spring request channel accepts/dispatches message.
T2: Outbound adapter serializes command.
T3: Network publish attempted.
T4: Broker may acknowledge/confirm receipt.
T5: Consumer receives record.
T6: Consumer commits business effect.
T7: Consumer acknowledges processed delivery.
~~~

Điều gì được bảo đảm khi `gateway.submit(...)` return phụ thuộc **điểm mà flow/adapter trả control**. Một outbound adapter đồng bộ có thể chờ điều kiện publish nhất định; một async producer có thể chỉ enqueue vào client buffer. Không được dựa vào `void` để suy ra đã đạt T4, T6 hoặc T7.

### 10.2. Broker acknowledgement không phải business acknowledgement

~~~text
Broker accepted record     -> messaging handoff milestone
Consumer processed record  -> consumer processing milestone
DB update committed        -> business persistence milestone
External payment completed -> another side-effect milestone
~~~

Một message broker confirm chỉ nói broker đáp ứng contract xác nhận; không chứng minh consumer đã cập nhật database hoặc thanh toán thành công.

### 10.3. Khi cần bảo đảm không mất command giữa DB và broker

Ứng dụng có thể ghi business state rồi gọi Gateway để publish event:

~~~text
1. DB order transaction COMMIT.
2. Process CRASH.
3. Gateway chưa kịp publish event.
~~~

Hệ thống đã thay đổi state nhưng mất event. Ngược lại, publish trước DB commit có thể đưa event tới consumer dù DB rollback. Đây là **dual-write problem**.

Một giải pháp thường gặp là **transactional outbox**:

~~~mermaid
flowchart LR
    API["Order API"] --> TX["Database Transaction"]
    TX --> ORDER[("Orders")]
    TX --> OUTBOX[("Outbox event")]
    OUTBOX --> RELAY["Publisher / One-way Gateway"]
    RELAY --> BROKER[("Durable Broker")]
    BROKER --> INBOX["Idempotent Consumer"]
~~~

Trong cùng transaction database, ứng dụng ghi business row và outbox row có stable event ID. Relay có thể retry publish mà không mất intent. Consumer phải có dedupe vì relay có thể publish trùng khi broker ack thất lạc.

**Gateway không thay thế outbox.** Nó là một cách đưa message vào transport flow; bảo đảm nguyên tử với business transaction cần thiết kế riêng.

### 10.4. Nếu yêu cầu chỉ là “tối đa một lần gửi”?

Không phải mọi thông điệp đều quan trọng như payment. Một telemetry ping hoặc noncritical cache warm-up có thể chấp nhận mất một số message, giảm chi phí bằng best-effort. Nhưng lựa chọn đó phải **được ghi trong contract/SLO**:

~~~text
Event type: CACHE_WARMUP_HINT
Reliability: best-effort
Loss tolerance: acceptable
Retry: limited or none
Business impact: cache may warm later
~~~

Ngược lại, `CHARGE_PAYMENT` hoặc `CREATE_ORDER` không nên mặc nhiên dùng same semantics. One-way là **exchange pattern**, còn độ tin cậy là **quyết định nghiệp vụ**.

## 11. Acknowledgment: được nhận, được lưu hay được xử lý?

### 11.1. Định nghĩa success cho phía gọi

Có thể chia thành các mức:

| Mức | Nội dung | API phù hợp |
|---|---|---|
| L0: Caller invoked API | Java method được gọi. | Không đáng làm business guarantee. |
| L1: Channel accepted | Gateway gửi được tới channel theo semantics. | `void` có thể đủ nếu best-effort. |
| L2: Durable enqueue committed | Có bằng chứng đã ghi vào queue/outbox/broker. | Có thể cần explicit accepted receipt/transaction. |
| L3: Consumer accepted | Consumer xác nhận sẽ xử lý theo contract. | Thường asynchronous status. |
| L4: Business completed | Có authoritative business outcome/receipt. | Status query, event/callback, request–reply nếu thật sự cần. |

Một phương thức `void` có thể thích hợp ở L1 hoặc là phần API của L2 nếu có transaction/commit rõ. Nhưng nếu caller phải biết `paymentReceiptId` hoặc `orderStatus` ngay lập tức, **one-way void Gateway không phải giao diện đủ thông tin**.

### 11.2. Không trả HTTP 200 “completed” chỉ vì Gateway return

Ví dụ REST controller:

~~~text
POST /orders/submit
   -> gateway.submit(command)
   -> return 200 "ORDER_COMPLETED"
~~~

Đây là contract nguy hiểm nếu processing thực sự diễn ra sau đó. Khi async, một lựa chọn là phản hồi **202 Accepted** với operation/status reference *nếu* server đã đáp ứng hợp đồng chấp nhận công việc, và có endpoint/status event để tra kết quả. `202` cũng không tự đảm bảo queue durable; phải khớp với thực thi.

### 11.3. Ack broker tiêu thụ

Một consumer có thể:

- Ack **sau khi** business DB transaction commit.
- Dùng transactional consumer/producer trong phạm vi broker hỗ trợ.
- Retry sau failure và redeliver.
- Đưa tới DLQ sau policy exhaustion.

Trường hợp **business commit thành công nhưng ack mất**, redelivery có thể xảy ra; đó là lý do handler cần idempotency. Không thể nói “one-way nên không có duplicate” khi transport thường hướng tới at-least-once.

## 12. Error handling cho one-way Gateway

### 12.1. Bốn vị trí lỗi

~~~mermaid
flowchart TD
    G["void Gateway"] --> C{"Request channel"}
    C -->|No subscriber / rejection / timeout| E1["Dispatch failure"]
    C -->|Accepted| T["Transformer / Validator"]
    T -->|Mapping error| E2["Validation / contract handling"]
    T -->|OK| A["Async / Broker boundary"]
    A -->|Publish / network failure| E3["Transport recovery"]
    A -->|Delivered| H["Business handler"]
    H -->|Processing failure| E4["Business retry / reconciliation"]
~~~

Mỗi lỗi có thể xảy ra **trước hoặc sau** khi `submit(...)` return. Không được dùng một catch-all handler rồi giả định caller luôn nhìn thấy lỗi.

### 12.2. DirectChannel: lỗi có thể đi ngược về caller

Với handler đồng bộ, exception từ handler có thể được propagate qua call stack. Tại application boundary:

~~~java
try {
    gateway.submit(command);
} catch (RuntimeException dispatchFailure) {
    // Quyết định retry/rejection theo loại lỗi.
    // Không kết luận side effect chưa xảy ra nếu đã có external call.
    throw dispatchFailure;
}
~~~

Đoạn này chỉ minh họa cơ chế thấy exception. Nó **không phải retry policy**, và không có nghĩa retry lại ngay là an toàn. Nếu external service đã commit trước khi exception đến caller, thao tác lặp có thể tạo side effect trùng.

### 12.3. Executor/Queue/Broker: lỗi có thể chỉ thấy ở consumer

Khi caller đã return, consumer lỗi cần một đường đi rõ:

~~~text
Async worker
  -> exception
  -> configured error handling
       -> classify retryable?
       -> bounded retry/backoff
       -> DLQ/quarantine if exhausted
       -> audit failure state + alert
~~~

Với Spring Integration, `ErrorMessage` và `errorChannel` là các cơ chế xử lý lỗi trong execution context phù hợp. **Không khẳng định global errorChannel tự nhận mọi lỗi của Kafka deserializer, HTTP mapping, ExecutorChannel hay custom callback**. Hãy kiểm tra đúng adapter/error handler và test failure ở vị trí cụ thể.

### 12.4. Error channel không phải business reply

Một `ErrorMessage` được xử lý bởi monitoring/recovery flow không có nghĩa Gateway void method sẽ tự nhận một reply kiểu `OrderFailed`. Muốn caller theo dõi outcome, cần **operation status store**, callback hoặc event dựa trên business correlation.

### 12.5. Retry advice cần biết phạm vi

| Điểm lỗi | Có nên retry? | Điều kiện |
|---|---|---|
| No subscriber/misconfiguration | Không retry vô hạn. | Sửa wiring/deployment. |
| Executor temporarily overloaded | Có thể backoff có giới hạn. | Chống queue overload; không mất intent. |
| Broker publish timeout | Có thể nhưng outcome publish chưa rõ. | Stable message ID/dedupe. |
| Validation deterministic fail | Không tự retry vô hạn. | Source correction/schema change. |
| Database temporarily unavailable | Có thể. | Idempotent transaction và retry policy. |
| Remote payment timed out | Chỉ retry an toàn nếu remote idempotency/reconciliation. | Có thể đã commit. |
| Unauthorized tenant | Không. | Security audit/reject. |
| Business final rejection | Theo business contract. | Không biến thành success giả. |

### 12.6. Đừng dựa vào retry của caller làm nền tảng phục hồi duy nhất

Nếu Gateway return sau enqueue vào queue memory rồi JVM crash, caller có thể không biết message mất. Nếu chỉ dựa vào “caller sẽ gọi lại”, có thể bỏ sót công việc; nếu gọi lại, có thể tạo duplicate. Độ tin cậy cao cần durable record ở một ranh giới có thẩm quyền (outbox/queue/inbox ledger) và reconciliation, không chỉ `try-catch` quanh một `void` method.

## 13. Idempotency: Gateway gửi một chiều vẫn có thể kích hoạt xử lý trùng

### 13.1. At-least-once khác exactly-once

Với broker hoặc outbox relay, cùng logical command/event có thể được giao nhiều lần:

~~~text
T0  SUBMIT-901 published.
T1  Consumer receives SUBMIT-901.
T2  Consumer commits order.
T3  Consumer crashes before broker ack.
T4  Broker redelivers SUBMIT-901.
T5  Consumer sees same logical operation.
~~~

Nếu handler không có idempotency, T5 có thể tạo thêm đơn hoặc charge lại. **One-way Gateway không tự chống trùng**. Stable operation ID giúp consumer nhận ra cùng logical intent, dù Spring Message ID hoặc broker offset thay đổi.

### 13.2. Chọn idempotency key ở đúng cấp

| Tình huống | Key phù hợp (minh họa) | Vì sao |
|---|---|---|
| Create order command | `tenant + CREATE_ORDER + operationId` | Cùng lệnh submit được retry. |
| Send order notification | `tenant + NOTIFY_ORDER + eventId + recipient` | Mỗi recipient cần thông báo một lần. |
| Payment charge | `merchant + CHARGE + paymentOperationId` | Chống charge lặp. |
| Audit projection | `tenant + AUDIT_CONSUMER + eventId` | Cùng event cần được xử lý ở consumer khác. |
| Split batch item | `batchId + childId + operationType` | Không chặn nhầm các child khác nhau. |

**Không dùng** mỗi `orderId` nếu một đơn có thể có nhiều operations hợp lệ (CREATE, CANCEL, ADJUST, REFUND). Cũng không dùng `traceId`/`correlationId` đơn thuần vì chúng có thể nhóm nhiều messages.

### 13.3. Demo in-memory duplicate guard chỉ để học

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

final class DemoOnceOnlyHandler {
    private final Set<String> seen =
            ConcurrentHashMap.newKeySet();
    private final AtomicInteger applied = new AtomicInteger();

    void handle(OrderSubmission command) {
        if (!seen.add(command.operationId())) {
            return; // Same key observed in this JVM.
        }
        applied.incrementAndGet(); // Simulated effect.
    }

    int appliedCount() {
        return applied.get();
    }
}
~~~

Code này chỉ chứng minh **deduplication trong một JVM khi state còn sống**. Nó **không phải implementation production**: nếu process crash sau `seen.add(...)` nhưng trước effect, retry bị bỏ lỡ; nếu effect xảy ra nhưng record chưa được lưu bền, retry có thể tạo effect lần hai.

### 13.4. Unit test ý nghĩa idempotency của cùng operation

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OneWayDuplicateCommandTest {
    @Test
    void duplicateCommandHasOneSimulatedEffectInMemory() {
        DemoOnceOnlyHandler handler = new DemoOnceOnlyHandler();
        OrderSubmission same = new OrderSubmission(
                "SUBMIT-901",
                "ORD-901",
                new BigDecimal("850000"));

        handler.handle(same);
        handler.handle(same);

        assertEquals(1, handler.appliedCount());
    }
}
~~~

Một unit test xanh như vậy **không chứng minh** multi-node, database transaction, broker ack, remote payment, crash recovery hoặc correctness của business status.

### 13.5. Durable operation ledger

Cho consumer cần xử lý bền, cân nhắc thiết kế:

~~~text
Operation key:
  (authenticatedTenant, operationType, operationId)

State:
  NEW -> IN_PROGRESS -> COMPLETED
                     -> FAILED_RETRYABLE
                     -> OUTCOME_UNKNOWN -> reconciliation

Stored information:
  payload fingerprint
  attempt/lease and fencing version
  authoritative business receipt
  createdAt/updatedAt
  policy/retention
~~~

Một bảng mẫu:

~~~sql
CREATE TABLE order_command_inbox (
    tenant_id        VARCHAR(100) NOT NULL,
    operation_type   VARCHAR(100) NOT NULL,
    operation_id     VARCHAR(120) NOT NULL,
    payload_hash     VARCHAR(128) NOT NULL,
    operation_state  VARCHAR(40) NOT NULL,
    receipt_ref      VARCHAR(160),
    updated_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_type, operation_id)
);
~~~

Đây là **schema minh họa**, chưa bao gồm lease, concurrency fencing, audit, cleanup, receipt version hay tenant authorization. Với business effect trong cùng DB, unique constraint/transaction có thể giúp atomicity. Với remote side effect qua HTTP, còn cần **remote idempotency key** hoặc reconciliation vì DB và HTTP không phải một transaction nguyên tử.

### 13.6. Same key, different payload phải được phát hiện

~~~text
Attempt A:
  operationId=SUBMIT-901
  amountVnd=850000

Attempt B:
  operationId=SUBMIT-901
  amountVnd=950000
~~~

Không nên coi B đơn giản là duplicate success của A. Cần **payload fingerprint/canonicalization** và outcome `OPERATION_CONFLICT` hoặc workflow correction có quyền. Nếu caller muốn sửa đơn sau submit, nên định nghĩa **operation mới** (ví dụ ADJUST_ORDER) thay vì lặng lẽ thay payload dưới cùng operation ID.

### 13.7. Handler đã hoàn thành nhưng caller không biết

Trong one-way, caller không có business reply; đây là lý do cần:

- Query API theo operationId.
- Completion event có correlation/causation.
- Receipt/ledger có durable status.
- Deadline và alert cho operation pending.
- Idempotent handling của late reply hoặc duplicate completion events.

Không nên viết logic “gateway method return thì mark COMPLETED” ở application service.

## 14. Filter, validation và one-way discard

### 14.1. Validation trước side effect

Một command có thể được gửi một chiều nhưng vẫn sai:

~~~text
SubmitOrder(
  operationId = SUBMIT-901,
  amountVnd   = -850000
)
~~~

Nếu DTO constructor không validate (ví dụ raw decoded DTO), cần một bước validation:

~~~mermaid
flowchart LR
    G["Void Gateway"] --> V["Validate"]
    V --> F{"Valid?"}
    F -->|Yes| B["Business handler"]
    F -->|No| Q["Quarantine / reject"]
~~~

Một `Filter` trả false có thể loại message khỏi main flow. Nếu cần audit/replay, phải cấu hình `discardChannel` và handler/queue bền; **không giả định rejected message được lưu lại tự động**.

### 14.2. Một Filter có thể tạo “thành công im lặng”

Với `DirectChannel`, một Filter loại command và không ném lỗi theo cấu hình. Gateway `void` có thể return bình thường mặc dù business handler chưa được gọi. Đó không phải lỗi của Gateway; đó là **hợp đồng one-way và Filter chưa được thiết kế đủ rõ**.

Nếu caller phải được báo ngay việc không đủ điều kiện, một synchronous validation step **trước khi gọi Gateway** hoặc một API trả typed rejection result có thể phù hợp hơn.

### 14.3. Reject khác technical error

| Case | Ví dụ | Xử lý |
|---|---|---|
| Invalid business input | Số tiền âm. | Rejection/quarantine hoặc error contract. |
| Unsupported message schema | Version lạ. | Compatibility quarantine, producer upgrade. |
| Tenant unauthorized | Caller không có quyền đặt đơn. | Security rejection/audit. |
| Channel not subscribed | Không có consumer handler. | Deployment/technical failure. |
| Database unavailable | Handler không thể commit. | Bounded retry/backoff/error path. |
| Duplicate already completed | Same operationId. | Return/use previous outcome, ack duplicate theo contract. |

Không chuyển mọi exception thành business validation failure, cũng không tự coi duplicate có ý nghĩa giống invalid.

### 14.4. Gateway và Quarantine

Nếu one-way flow nhận command không hợp lệ rồi đưa vào quarantine, cần lưu:

~~~text
quarantineId      = Q-901
operationId       = SUBMIT-901
trustedTenant     = TENANT-A
source            = order-api
reasonCodes       = [INVALID_AMOUNT]
payloadReference  = protected-ref
validationVersion = orders-v3
state             = NEW
~~~

Không log raw payment/customer payload hoặc credentials vào error text. Nếu business cần replay, người thực hiện phải được authorize theo tenant/resource, revalidate dưới policy đã xác định, giữ idempotency key và có audit đầy đủ.

### 14.5. Một flow đồng bộ có thể là lựa chọn tốt

Không cần mọi one-way operation bất đồng bộ. Nếu command là một tác vụ nhỏ, không chặn, không có network call và lỗi muốn được propagate đến caller, `DirectChannel` với terminal handler có thể đơn giản hơn executor/broker. Chỉ thêm async khi yêu cầu latency, throughput, isolation và fault tolerance **thực sự** cần.

## 15. Metadata, headers và correlation

### 15.1. One-way không có business reply nhưng vẫn cần correlation

Trong một workflow:

~~~text
Checkout CHECKOUT-88
  -> Gateway sends SubmitOrder SUBMIT-901
  -> OrderSubmitted event EVT-911
  -> InventoryReserved event EVT-912
  -> NotificationRequested event EVT-913
~~~

Các messages có thể chia sẻ `correlationId=CHECKOUT-88` và có `causationId` trỏ tới message/operation nguyên nhân. Correlation phục vụ **truy vết và ghép workflow**, không tự động là idempotency key cho mọi message.

### 15.2. Truyền metadata bằng cách nào?

Có thể dùng custom Spring headers, hoặc một typed envelope:

~~~java
record OrderCommandEnvelope(
        String eventId,
        String correlationId,
        String authenticatedTenant,
        OrderSubmission payload) {}
~~~

Tuy nhiên, `authenticatedTenant` chỉ được coi là trusted nếu do **security boundary thực sự tạo ra**, không phải vì tên field hay client tự khai.

Nếu dùng `@Header` ở method parameter:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway
interface CorrelatedOrderGateway {

    @Gateway(requestChannel = "orders.submit.input")
    void submit(
            OrderSubmission command,
            @Header("businessCorrelationId")
            String correlationId);
}
~~~

Caller được phép cung cấp correlation theo API contract, nhưng correlation **không phải quyền**. Nếu cần bảo vệ privileged headers như tenant, source hoặc route, hãy xây chúng từ authenticated context ở adapter/application boundary.

### 15.3. Spring `MessageHeaders.ID` có thể đổi khi message được tạo lại

~~~text
Gateway builds Spring message:
  headers.id = UUID-A
  businessOperationId = SUBMIT-901

Broker consumer rebuilds Spring message:
  headers.id = UUID-B
  businessOperationId = SUBMIT-901
~~~

Idempotent Receiver dựa trên operationId, không dựa vào `headers.id`. Nếu correlation/operationId bị mất qua Transformer, adapter header mapper hoặc reserialization, retry có thể gây double effects. Hãy có **adapter round-trip tests** để phát hiện metadata bị mất.

### 15.4. Đừng truyền internal reply channel qua wire

`replyChannel` và `errorChannel` trong Spring Message có thể là các channel objects của JVM. Với broker/HTTP, phải dùng **transport-specific reply destination/error routing** khi cần; không serialize hoặc tin arbitrary header class/object từ bên ngoài.

### 15.5. Correlation không biến one-way thành request–reply

Việc có `correlationId` trong message **không** tự khiến Gateway chờ reply. Một completion event phát về sau có thể dùng correlation cùng operation status; nó vẫn là message exchange riêng, không phải kết quả Java return của `void submit(...)`.

## 16. So sánh với các EIP liên quan

### 16.1. Messaging Gateway và Outbound Channel Adapter

| Thành phần | Ranh giới | Ví dụ |
|---|---|---|
| **Messaging Gateway** | Java application interface → messaging system. | `gateway.submit(command)`. |
| **Outbound Channel Adapter** | Spring Integration flow → hệ thống ngoài, theo semantics adapter. | Gửi tới Kafka/JMS/HTTP/file. |
| **Inbound Channel Adapter** | Hệ thống ngoài → Spring message flow. | Nhận broker record, poll file. |
| **Service Activator** | Channel message → business/service method. | `handle(OrderSubmission)`. |
| **Router** | Chọn channel theo điều kiện. | Theo command type, region. |
| **Transformer** | Chuyển payload/metadata. | Domain DTO → wire command schema. |

Một kiến trúc thường có **cả gateway và outbound adapter**, không phải chọn một trong hai:

~~~text
Java service
   -> Messaging Gateway
   -> Internal Channel
   -> Transformer / Filter
   -> Outbound Channel Adapter
   -> External Broker
~~~

### 16.2. Gateway và Publish–Subscribe

Một Gateway void có thể gửi **event** sang một `PublishSubscribeChannel`, nhưng semantics thay đổi theo subscribers:

~~~mermaid
flowchart TD
    G["Void Gateway publishes OrderPlaced"] --> PUB["PublishSubscribeChannel"]
    PUB --> AUDIT["Audit"]
    PUB --> NOTICE["Notification"]
    PUB --> ANALYTICS["Analytics"]
~~~

Không phải tất cả subscribers đều có cùng mức độ quan trọng. Nếu one-way event cần đến ba consumers độc lập, nên cân nhắc isolation, error propagation, retry và durable pub/sub. Một subscriber throw ở synchronous channel có thể ảnh hưởng dispatch của các subscriber khác tùy cấu hình; **không tự khẳng định một nhánh hỏng không ảnh hưởng nhánh khác**.

Mỗi consumer cần **idempotency scope riêng** nếu cùng event được giao lại. Một global dedupe marker dùng chung cho Audit và Notification có thể khiến subscriber thứ hai bị loại nhầm.

### 16.3. Gateway và Recipient List

Nếu một command phải gửi tới các recipients được chọn theo điều kiện, Recipient List có thể tạo fan-out. Việc Gateway trả `void` không có nghĩa ta đã biết **tất cả recipients nhận thành công**. Cần trạng thái per-recipient, retry/idempotency và completion policy nếu business cần mọi nhánh.

~~~text
order command
  -> Gateway
  -> Recipient List:
      Billing
      Inventory
      Notification

Gateway returns != all recipients committed
~~~

### 16.4. Gateway và Splitter

Một command batch có thể được Splitter chia thành các items:

~~~text
BatchCommand(batchId=B-1)
   -> Gateway (void)
   -> Splitter:
       Item I-1
       Item I-2
       Item I-3
~~~

Nếu caller không chờ reply, cần một cách khác để biết kết quả từng item:

- Store trạng thái batch và per-item outcome.
- Phát completion/failure event cho từng child.
- Aggregate status khi đủ các child theo contract.
- Có timeout nếu một item invalid hoặc mất.
- Giữ `batchId + itemId` làm operation identity cho mỗi side effect.

Đừng dùng cùng `batchId` làm idempotency key của mọi item, vì item thứ hai và thứ ba có thể bị xem là duplicate của item đầu.

### 16.5. Gateway và Aggregator

Aggregator thường tạo kết quả từ nhiều messages. Nếu Gateway caller dùng `void`, **không có chỗ trả kết quả aggregate qua return value của invocation ban đầu**. Có thể:

~~~text
Gateway submitBatch(B-1)
  -> async processing
  -> Aggregator creates BatchCompleted(B-1)
  -> status store / event notification
~~~

Nếu caller cần batch result ngay, có thể chọn **request–reply Gateway** với deadline và resource budget phù hợp. Không nên âm thầm đưa Aggregator bên dưới void Gateway rồi nói application đã nhận kết quả chỉ vì nó đã gửi command.

### 16.6. Gateway và Scatter–Gather

Scatter–Gather thu thập replies từ nhiều recipients, thường cần correlation, timeout và release strategy. One-way Gateway có thể **khởi động** workflow scatter–gather mà không chờ final aggregate; kết quả được xuất ở một event/status flow khác.

Nếu workflow đòi Fraud + Inventory + Pricing đều thành công, không báo `APPROVED` chỉ vì void Gateway return hoặc một trong ba nhánh đã xác nhận.

### 16.7. Gateway và Resequencer

Một Gateway có thể gửi events có `businessSequence` 1, 2, 3. Với concurrent executor hoặc broker partitions, arrival/processing có thể khác thứ tự. Resequencer và correlation metadata có thể giúp khôi phục release order, nhưng:

- Một message bị Filter drop có thể tạo **sequence gap**.
- Duplicate delivery không được coi là item còn thiếu.
- Đúng thứ tự release chưa chắc đúng thứ tự DB commit nếu downstream tiếp tục chạy song song.
- Cần partitioning/version guard nếu business đòi strict write order.

### 16.8. Gateway và Claim Check

Với command payload lớn:

~~~text
Large command
   -> protected store (Claim Check)
   -> Gateway sends reference
   -> Consumer restores payload
~~~

Gateway void return chỉ nói đã gửi **reference** theo channel contract, không nói consumer đọc được original payload. Nếu Claim Check store hết hạn trước khi xử lý, command có thể không phục hồi được. Claim ID cũng không tự thay **business operation ID**.

### 16.9. Gateway và Message Translator / Envelope Wrapper

Một Gateway có thể nhận domain command rồi Translator chuyển sang schema của đối tác:

~~~text
OrderSubmission
   -> Void Gateway
   -> Message Translator
   -> Envelope Wrapper
   -> Broker adapter
~~~

Translator có thể reject field không map được; Envelope Wrapper giữ source/type/version/correlation; broker adapter map wire headers. Không để Translator tạo operationId mới mỗi lần retry hoặc lấy `tenantId` từ untrusted header rồi gọi là trusted.

### 16.10. Gateway và Idempotent Receiver

Idempotent Receiver thường nằm ở **consumer của side effect** để dedupe redelivery. Nó có thể dùng `ConcurrentMetadataStore`/`IdempotentReceiverInterceptor` ở mức Spring Integration, nhưng **marker SEEN không bằng business COMPLETED**. Với payment/order cần durable operation state/receipt và reconciliation, không chỉ một in-memory selector.

## 17. Timeout, transaction và backpressure

### 17.1. Request timeout không phải execution timeout toàn flow

Một Gateway/Channel có thể cấu hình timeout liên quan đến **send/handoff**. Với downstream synchronous handler gọi một API ngoài trong 30 giây, một send timeout của QueueChannel không tự hủy external request sau 30 giây. Cần phân biệt:

| Timeout | Đo khoảng nào? | Cần xử lý |
|---|---|---|
| Gateway/channel send timeout | Thời gian chờ gửi/được channel nhận, tùy implementation. | Điều phối overload/backpressure. |
| Executor queue deadline | Thời gian chờ task được schedule/run. | Queue saturation và stale requests. |
| Broker publish timeout | Chờ producer send/ack theo adapter. | Outcome publish có thể UNKNOWN. |
| Consumer processing deadline | Giới hạn thao tác business. | Idempotent retry/reconcile nếu timeout sau side effect. |
| Operation SLA | Từ accepted đến authoritative completion. | Status store, alert và compensation. |

Đừng mô tả tất cả các timeout là “Gateway timeout”. Mỗi loại có **mốc bắt đầu/kết thúc và recovery khác nhau**.

### 17.2. One-way Gateway gọi trong DB transaction

Ví dụ:

~~~java
// Pseudocode, không phải một transaction bảo đảm toàn hệ thống.
@Transactional
void placeOrder(...) {
    orderRepository.save(order);
    gateway.submit(new OrderSubmission(...));
}
~~~

Nếu Gateway dẫn đến broker publish không tham gia cùng DB transaction, một lỗi sau publish có thể rollback DB nhưng record vẫn phát, hoặc DB commit còn publish thất bại. Nếu cần atomic intent, dùng **outbox/CDC/transactional architecture** có chứng cứ commit.

### 17.3. Async boundary thường tách transaction context

Với `ExecutorChannel`, handler chạy thread khác; **ThreadLocal transaction/security context** của caller không tự được chia sẻ nguyên vẹn. Không dựa vào transaction mở ở caller để bao trùm consumer async. Truyền metadata được phép và mở transaction/authorization context ở handler theo kiến trúc.

Đặc biệt, không truyền raw database session, principal object hoặc transaction manager qua message payload như một cách “giữ nguyên transaction”; đây là ranh giới thực thi và bảo mật khác.

### 17.4. Transaction commit và broker ack không nên bị đánh đồng

~~~text
Transaction DB commit OK
Broker consumer ack lost
  -> message may redeliver
  -> idempotency ledger recognizes operation COMPLETED
~~~

Nếu dùng transaction của một resource manager, nó không tự mở rộng sang HTTP payment API hoặc mọi broker/database. Phải nêu **phạm vi atomicity**, không gắn nhãn “exactly once” cho toàn workflow nếu chưa chứng minh.

### 17.5. Backpressure cho one-way sender

Một caller không chờ business reply có thể gửi nhanh hơn downstream xử lý. Cần giới hạn:

~~~text
Input rate        = 10,000 commands/s
Consumer capacity =  1,000 commands/s
Backlog growth    =  9,000 commands/s
~~~

Nếu queue không giới hạn, rủi ro OOM/disk exhaustion. Nếu queue có capacity, sender có thể block/reject. Các lựa chọn:

- Bounded executor/queue và overload status.
- Rate limit ở ingress theo tenant/priority.
- Durable buffer có retention, capacity alert và partitioning phù hợp.
- Consumer autoscaling khi side effects/idempotency cho phép.
- Deadlines: expired command có nên thực hiện sau khi queue đợi quá lâu?
- Circuit breaker cho downstream không sẵn sàng.
- Có thể trả backpressure/retry-after ở synchronous API boundary thay vì âm thầm drop.

**One-way không có nghĩa caller có thể gửi vô hạn mà không chịu trách nhiệm load.**

### 17.6. Không quên shutdown semantics

Một JVM dừng trong lúc ExecutorChannel còn task pending có thể làm mất các công việc chưa durable. Graceful shutdown có thể đợi tasks một thời gian, nhưng **không thay thế persistent queue** khi có crash, kill, node loss hoặc timeout shutdown.

Ở hạ tầng broker, cần kế hoạch pause intake, drain backlog, redelivery và resume. Một deploy “thành công” không tự chứng minh không có message bị mất trong quá trình chuyển phiên bản.

## 18. Bảo mật khi gửi one-way message

### 18.1. Không tin callback chỉ vì nó không trả reply

Một attacker có thể lợi dụng endpoint fire-and-forget để gửi rất nhiều commands, tạo backlog hoặc side effects trong nền. Hãy có:

- Authentication và authorization theo tenant/operation.
- Input schema validation, payload size limit, rate limiting.
- Quota per principal/tenant.
- Business idempotency key với scope hợp lệ.
- Audit của accepted/rejected operations.
- Không phản hồi thành công giả khi hệ thống không thể handoff.

### 18.2. Header routing không phải một authorization mechanism

Một inbound header `targetChannel=paymentProcessor` do caller khai **không nên được dùng trực tiếp** để chọn bất kỳ Spring channel hoặc bean nào. Nếu dùng Dynamic Router/Header-Based Router, cần allowlist và trusted source/policy.

### 18.3. Không đưa secrets vào message logs

One-way commands có thể chứa địa chỉ, token, email hoặc thông tin thanh toán. Logging nên tập trung:

~~~text
operationRef = opaque/stable ID
commandType  = SUBMIT_ORDER
tenantScope  = trusted, access controlled
route        = orders.submit.input
outcome      = DISPATCH_ACCEPTED
~~~

Không in nguyên payload/hệ thống credentials trong `toString()`, stack trace, error channel messages hoặc dead-letter headers. Với dữ liệu cần điều tra, dùng protected storage/reference cùng retention và quyền đọc.

### 18.4. Replay phải được authorize lại

Một command trong DLQ cách đây ba ngày không tự được phép replay hôm nay. Quyền user có thể bị revoke, tenant thay đổi policy, giá trị tiền không còn hợp lệ. Replay cần kiểm tra lại security/business rules, status/receipt và operation identity trước khi kích hoạt side effect.

### 18.5. Client-generated operation IDs không phải chứng chỉ quyền

Một operationId dễ đoán như `SUBMIT-901` chỉ là định danh. Không trả business receipt cho người biết ID mà chưa có quyền trên order/tenant. Khi dedupe same key, cũng cần fingerprint và authorization để ngăn user dùng key của người khác truy vấn hoặc chặn operation.

## 19. Quan sát và chẩn đoán one-way flow

### 19.1. Log theo mốc, không ghi một event “DONE” chung

~~~text
event=GATEWAY_INVOKED
  operationRef=SUBMIT-901
  commandType=SUBMIT_ORDER

event=CHANNEL_HANDOFF_ACCEPTED
  operationRef=SUBMIT-901
  channel=orders.submit.input

event=OUTBOX_PERSISTED
  operationRef=SUBMIT-901
  outboxRef=OUT-901

event=BROKER_PUBLISHED
  operationRef=SUBMIT-901
  brokerRef=...

event=CONSUMER_RECEIVED
  operationRef=SUBMIT-901
  deliveryAttempt=2

event=BUSINESS_OPERATION_COMPLETED
  operationRef=SUBMIT-901
  receiptRef=ORD-901

event=CONSUMER_ACKNOWLEDGED
  operationRef=SUBMIT-901
~~~

Đây là **schema structured logging được đề xuất** chứ không phải những sự kiện Spring Integration mặc định. Mỗi log chỉ nên được phát tại **mốc có bằng chứng**. Ví dụ `OUTBOX_PERSISTED` phải dựa trên database commit contract; `BUSINESS_OPERATION_COMPLETED` phải dựa trên authoritative result, không chỉ từ method return.

### 19.2. Metrics gợi ý

| Metric | Ý nghĩa |
|---|---|
| `gateway_invocations_total{method}` | Số lần caller gọi Gateway. |
| `gateway_dispatch_accepted_total{channel}` | Số handoffs được channel chấp nhận. |
| `gateway_dispatch_failed_total{reason}` | Lỗi gửi/rejection/timeout. |
| `gateway_dispatch_latency_seconds` | Độ trễ invocation đến mốc handoff. |
| `oneway_executor_queue_depth` | Task backlog trong executor. |
| `oneway_executor_rejected_total` | Số task bị từ chối khi quá tải. |
| `oneway_consumer_received_total` | Số deliveries tới consumer. |
| `oneway_business_completed_total{outcome}` | Số operations có final outcome. |
| `oneway_duplicate_delivery_total` | Số deliveries của operation cũ. |
| `oneway_business_outcome_unknown_total` | Số operations cần reconciliation. |
| `oneway_error_channel_messages_total{class}` | Số lỗi được error flow xử lý. |
| `oneway_dlq_messages_total{reason}` | Số records vào DLQ. |
| `oneway_operation_age_seconds` | Độ trễ từ accepted đến final status. |
| `oneway_outbox_pending_total` | Số outbox chưa publish/xác nhận. |

Các tên trên chỉ là đề xuất. Spring Integration hoặc Micrometer có thể cung cấp metrics khác tùy version/cấu hình; không khẳng định framework tự tạo tất cả. **Không gắn operationId/orderId/customer ID/email/traceId làm metric labels**: cardinality cao và có thể lộ PII.

### 19.3. Một ví dụ dashboard dễ hiểu sai

~~~text
Gateway invocations:        10,000
Channel handoff accepted:    9,998
Broker published:           9,990
Consumer received:         10,120  (redeliveries)
Business operations done:    9,875
Pending/unknown operations:    123
~~~

Đây là số liệu minh họa. `Consumer received` có thể cao hơn `Gateway invocations` do retry/redelivery. Không thể lấy một tổng deliveries làm tổng operations mới. Sự chênh lệch giữa handoff/publish/completed còn có **in-flight/lag/window differences**, cần join theo operation identity và time window trước khi kết luận mất message.

### 19.4. Message History hữu ích nhưng không phải receipt

Spring Integration Message History, nếu bật, giúp xem message đi qua Gateway, Transformer, Router, handler nào theo flow. Nhưng nó không tự chứng minh:

- Outbox được commit.
- Broker đã ack.
- External payment hoàn tất.
- DLQ record còn tồn tại sau retention.
- Retry dùng stable operationId.
- Caller được ủy quyền trên tenant.

Để điều tra một operation, kết hợp **trusted operation ID, structured logs, message history, broker coordinates, durable inbox/outbox và business receipts**.

### 19.5. Khi Gateway return nhưng không thấy message ở consumer

Kiểm tra theo thứ tự:

1. **Caller:** method `submit(...)` có thật được gọi không, có bị catch exception bỏ qua không?
2. **Gateway proxy:** interface đã được Spring scan/register đúng chưa?
3. **Request channel:** channel name có khớp `@Gateway(requestChannel=...)` không?
4. **Channel type:** Direct/Executor/Queue hay adapter; mỗi loại return ở mốc nào?
5. **Subscription:** có handler/subscriber đang chạy không? Consumer có stop/disabled?
6. **Overload:** executor bị reject, queue full, poller chậm?
7. **Transform/Filter:** message bị validate reject hoặc discard không có quarantine handler?
8. **Outbound adapter:** serialize error, header mapper, publish timeout?
9. **Broker:** topic/queue, partition/key, auth, retention và producer confirm?
10. **Inbound consumer:** adapter subscription, group, offset, deserialization error/DLQ?
11. **Idempotency:** consumer đã thấy same operation và bỏ duplicate hợp lệ?
12. **Business handler:** lỗi ở DB/API, đã ghi ledger/receipt chưa?
13. **Tracing:** correlation/operationId còn qua mỗi hop không?
14. **Recovery:** record đang pending, retry hoặc đã expired?

Đừng bắt đầu bằng việc tăng Gateway timeout hoặc thêm infinite retries. Tìm **điểm đầu tiên message hoặc bằng chứng xử lý bị mất**, sau đó sửa tại đúng ranh giới.

### 19.6. Runbook khi executor/queue quá tải

~~~text
Detect:
  queue_depth rises
  executor_rejected_total rises
  consumer_latency grows

Protect:
  enforce rate limit and bounded queue
  reject or backpressure new intake by contract

Recover:
  inspect downstream bottleneck
  scale consumer only if side effect supports concurrency
  drain durable pending messages

Validate:
  no silent loss
  no duplicate business effects
  operation age and error counts return to expected level
~~~

Không nên tăng số threads vô hạn nếu bottleneck là database, rate-limited API hoặc ordering constraint; điều đó có thể làm hệ thống mất ổn định hơn.

## 20. Các bài kiểm thử failure đáng ưu tiên

### 20.1. Đồng bộ: exception trong handler phải hiển thị

Một test có thể tạo dedicated handler ném exception:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.integration.channel.DirectChannel;

@Configuration
class OneWayFailingHandlerConfiguration {
    @Bean(name = "orders.failing.input")
    MessageChannel failingInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow failingFlow() {
        return IntegrationFlow.from("orders.failing.input")
                .handle(OrderSubmission.class,
                        (command, headers) -> {
                            throw new IllegalStateException(
                                    "DOWNSTREAM_UNAVAILABLE");
                        })
                .get();
    }
}
~~~

Để chạy qua Gateway, tạo một `@MessagingGateway` khác trỏ tới `orders.failing.input` trong test context; assert invocation throws một runtime/messaging exception, rồi kiểm tra cause chain theo framework version.

**Không kết luận chắc chắn side effect chưa xảy ra** nếu lỗi được ném sau một external commit. Test riêng crash window cần có authoritative business ledger hoặc remote idempotency mock.

### 20.2. Async: xác nhận worker chạy thay vì assert ngay

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class AsyncGatewayObservationPatternTest {
    @Test
    void awaitAnExplicitCompletionSignal() throws Exception {
        CountDownLatch completion = new CountDownLatch(1);
        // Trong integration test thực, inject completion vào handler,
        // handler.countDown() sau mốc cần quan sát.
        Runnable fakeWorker = completion::countDown;
        Thread worker = new Thread(fakeWorker);
        try {
            worker.start();
            assertTrue(completion.await(2, TimeUnit.SECONDS));
        } finally {
            worker.join(2000);
        }
    }
}
~~~

Test này minh họa **kỹ thuật chờ tín hiệu**, chưa phải test Spring Integration. Trong một integration test đầy đủ, thay `fakeWorker` bằng handler được kích hoạt qua `AsyncOrderSubmissionGateway`/`ExecutorChannel`. Dùng shared latch/queue assertion có deadline, dọn executor và kiểm tra cả submission rejection.

### 20.3. No subscriber

Một `DirectChannel` không có handler thường không thể dispatch thành công. Test nên xác nhận **lỗi/false handling** tương ứng với channel/gateway setup, không coi `void` là bằng chứng mọi message đều đã có người xử lý.

### 20.4. Queue full

Với `QueueChannel` capacity 1, không có poller hoặc consumer tạm dừng:

~~~text
send command A -> queue has 1 message
send command B -> may block/timeout/fail by send policy
~~~

Kiểm tra deadline, latency và số lượng message còn tồn tại. Không viết test treo vô hạn chỉ vì send không có timeout phù hợp.

### 20.5. Crash after enqueue

Một test system/chaos:

~~~text
1. Gateway returns after in-memory enqueue.
2. Kill process before consumer polls.
3. Restart process.
4. Check whether command remains.
~~~

Với QueueChannel trong memory, **không kỳ vọng durability**. Lặp test với persistent queue/broker để đo **độ bền theo contract** và không dùng cùng kết luận cho mọi channel.

### 20.6. Broker publish success, ack lost

~~~text
1. Publisher sends SUBMIT-901.
2. Broker persists, response lost.
3. Publisher retries same event.
4. Consumer sees duplicate SUBMIT-901.
5. Ledger prevents repeated business effect.
~~~

Không chỉ assert “broker có hai records”; assert **business effect chỉ một** và outcome/receipt được giữ qua restart.

### 20.7. Business commit success, consumer ack lost

~~~text
1. Consumer commits order operation.
2. Process dies before broker ack.
3. Record redelivered.
4. Consumer queries ledger and returns completed result.
5. No second order/charge created.
~~~

Đây là một tình huống quan trọng mà unit test chỉ dùng `ConcurrentHashMap` không chứng minh được.

### 20.8. Error channel receive and recovery

Với async endpoint, inject exception sau khi dispatch, xác minh:

- Có error event đúng exception class/reason.
- Error flow không lộ raw PII.
- Retry bounded và có dead-letter/fallback khi exhausted.
- Operation chuyển trạng thái `FAILED_RETRYABLE` hoặc `OUTCOME_UNKNOWN` theo chứng cứ.
- Không chạy lại business effect nếu previous attempt đã commit.

Phải kiểm thử trên **execution model thật**: error behavior khác nhau giữa DirectChannel, ExecutorChannel và transport adapter.

### 20.9. Gateway returned nhưng Filter dropped

Inject một invalid command **đã decode** vào Filter có discard channel; assert:

- Business handler **không** chạy.
- Quarantine handler nhận issue/reason.
- Durable handoff được xác minh nếu đó là yêu cầu production.
- Nếu caller cần rejection response, không dùng void one-way contract như thể nó trả được object rejection.

## 21. Ma trận kiểm thử one-way Messaging Gateway

| ID | Kịch bản | Điều phải xác minh | Điều không được xảy ra |
|---|---|---|---|
| GW-01 | Gọi `void gateway.submit(command)` qua DirectChannel | Handler nhận một command đúng payload. | Giả định phải có reply object. |
| GW-02 | Handler đồng bộ xử lý lâu | Caller chờ theo synchronous dispatch semantics. | Khẳng định `void` luôn async. |
| GW-03 | Handler DirectChannel throw | Lỗi propagate/wrapped theo contract. | Nuốt lỗi vì return type void. |
| GW-04 | DirectChannel không có subscriber | Dispatch failure được phát hiện. | Báo đã xử lý thành công. |
| GW-05 | Gateway request channel name sai | Wiring failure/test thất bại rõ. | Silent drop. |
| GW-06 | Interface không được scan/register | Spring context không có gateway bean. | Gọi một bean tưởng đã tồn tại. |
| GW-07 | Command có operationId ổn định | Payload giữ đúng identity. | Sinh ID mới mỗi attempt. |
| GW-08 | Command amount không hợp lệ | Reject/validation error hoặc quarantine theo contract. | Gọi business payment. |
| GW-09 | Filter discard invalid | Quarantine nhận reason và business không chạy. | Caller hiểu void return là business accepted. |
| GW-10 | One-way Gateway với ExecutorChannel | Có asynchronous dispatch thực. | Assert handler đã xong ngay sau return. |
| GW-11 | Executor queue accepted nhưng worker chưa chạy | Pending được quan sát. | Mark COMPLETED sớm. |
| GW-12 | Executor queue full | Rejection/backpressure có giới hạn. | Task mất âm thầm. |
| GW-13 | Worker throw sau caller return | Error flow/alert/recovery nhận lỗi. | Chờ caller bắt exception đồng bộ. |
| GW-14 | Async worker lỗi trước side effect | Retry hợp lệ theo policy. | Operation bị bỏ mãi không audit. |
| GW-15 | Async worker lỗi sau side effect | Idempotency/reconciliation. | Lặp charge. |
| GW-16 | QueueChannel capacity 1 đã đầy | Send timeout/behavior đúng cấu hình. | Block vô hạn không kiểm soát. |
| GW-17 | QueueChannel chưa có poller | Queue depth tăng, không báo done. | Coi enqueue là business completion. |
| GW-18 | QueueChannel in-memory rồi process crash | Thừa nhận mất dữ liệu theo contract. | Tuyên bố durable. |
| GW-19 | Durable queue rồi process restart | Recovery/redelivery theo store semantics. | Mất command khi restart. |
| GW-20 | Outbound adapter serialization throw | Publish error route được xử lý. | Coi gateway return là broker commit. |
| GW-21 | Kafka/RabbitMQ/JMS broker publish timeout | Outcome publish UNKNOWN, retry/dedupe. | Sinh command ID mới. |
| GW-22 | Broker confirm nhận | Xác nhận broker handoff milestone. | Mark business COMPLETED ngay. |
| GW-23 | Broker record có offset khác khi republish | Stable business operation key. | Dedupe dựa trên offset. |
| GW-24 | Consumer commit rồi ack mất | Redelivery trả previous receipt. | Gọi side effect lần hai. |
| GW-25 | Producer DB commit nhưng publish chưa kịp | Outbox/reconciliation bảo vệ intent. | Event mất vĩnh viễn. |
| GW-26 | Outbox relay publish hai lần | Consumer-side idempotency. | Double business effect. |
| GW-27 | Same operationId, different amount | Payload fingerprint conflict. | Trả success cũ không kiểm tra. |
| GW-28 | Cùng orderId có CREATE và CANCEL | Hai operation scopes. | Chặn CANCEL vì đã CREATE. |
| GW-29 | Cùng event fan-out đến Audit và Notification | Mỗi consumer xử lý một lần. | Global dedupe chặn nhánh thứ hai. |
| GW-30 | Splitter tạo ba child commands | Per-child keys và correlation. | Chặn hai child do cùng batchId. |
| GW-31 | Aggregator thiếu một child | Timeout/failure outcome. | Trả completed aggregate giả. |
| GW-32 | Scatter–Gather Fraud branch fail | Overall result không APPROVED sớm. | Chỉ dựa vào void Gateway return. |
| GW-33 | Resequencer gặp gap | Gap/release policy có giám sát. | Phát message sai thứ tự. |
| GW-34 | Gateway gửi Claim Check token | Consumer restore có quyền/TTL. | Coi token là original payload. |
| GW-35 | Unsupported outbound schema | Error/quarantine trước broker publish. | Serialize dữ liệu sai. |
| GW-36 | Transport adapter drop custom operation header | Round-trip test phát hiện. | Dedupe theo runtime MessageHeaders.ID. |
| GW-37 | Caller gửi fake tenant header | AuthN/AuthZ từ trusted principal. | Mạo danh tenant. |
| GW-38 | Caller gửi arbitrary channel selector | Route allowlist/policy. | Gửi vào privileged handler trái quyền. |
| GW-39 | Client flooding one-way endpoint | Quota/rate limit/backpressure. | Queue tăng vô hạn. |
| GW-40 | Worker cần DB transaction | Transaction mở đúng ở worker boundary. | Dùng ThreadLocal transaction của caller async. |
| GW-41 | Gateway trong DB transaction riêng broker | Detect dual-write/outbox strategy. | Giả định 2 resources tự atomic. |
| GW-42 | Gateway trả HTTP response ngay | Response phản ánh accepted milestone đúng. | Trả “ORDER_COMPLETED” giả. |
| GW-43 | Caller muốn receipt ngay | Chọn request–reply hoặc status contract. | Dùng `void` rồi chế reply ngầm. |
| GW-44 | Caller muốn kết quả qua event sau này | Correlation/causation đúng. | Dùng traceId làm identity duy nhất. |
| GW-45 | Redelivery tạo Spring Message ID khác | Dedupe vẫn dựa stable operationId. | Duplicate effect. |
| GW-46 | ErrorChannel nhận exception async | Recovery/bounded retry/alert. | Giả định caller tự nhận lỗi. |
| GW-47 | Invalid message vào quarantine | Durable case và reason codes. | Silent discard. |
| GW-48 | Quarantine DB unavailable | Retry/backpressure/no false ack. | Đẩy invalid vào business. |
| GW-49 | Replay DLQ của operation đã completed | Receipt reconciliation. | Tạo một order mới. |
| GW-50 | Payload chứa PII/secret | Redacted logs, protected store. | Raw data ra metrics/log. |
| GW-51 | Operation ID dễ đoán do caller gửi | Authorization theo principal/resource. | Lộ receipt người khác. |
| GW-52 | Executor shutdown còn tasks | Drain/recovery theo durability contract. | Giả định mọi task còn trong RAM đều bền. |
| GW-53 | Consumer chậm hơn ingress 10 lần | Queue monitoring, rate limit, capacity policy. | OOM không cảnh báo. |
| GW-54 | Gateway returned, no consumer record | Truy dấu từng mốc handoff/ack/consumer. | Kết luận chắc chắn đã mất message khi chưa kiểm chứng. |
| GW-55 | Tracking enabled | Message History giúp trace đúng phạm vi. | Xem Message History là durable receipt. |
| GW-56 | Source event schema version nâng cấp | Typed translator/adapter compatibility. | Chuyển về V1 rồi bỏ unknown fields nguy hiểm. |
| GW-57 | Một command expired khi còn trong queue | Policy deadline/expiry rõ. | Tự thực hiện giao dịch đã quá hạn. |
| GW-58 | Same command gửi lại với payload conflict | Conflict/review workflow. | Đè completed receipt. |
| GW-59 | Gateway request timeout nhưng handler đã commit | Outcome UNKNOWN + reconciliation. | Retry mù. |
| GW-60 | Meter báo received cao hơn completed | Phân biệt delivery count/unique operation count. | Suy ra số business operations bằng số deliveries. |

### 21.1. Mỗi cấp test chứng minh điều gì?

| Cấp test | Kiểm tra tốt nhất | Không chứng minh được |
|---|---|---|
| **Unit application service** | Caller gọi gateway interface với command/ID đúng. | Spring gateway proxy và channel wiring. |
| **Spring Integration synchronous test** | Proxy → DirectChannel → handler, error propagation. | Durable broker/async semantics. |
| **Spring Integration async test** | ExecutorChannel dispatch, latch, rejection/error flow. | Persistence qua process crash. |
| **Queue/adapter integration test** | Queue capacity, poller, outbound serialization/header mapping. | Business side effect trong external system nếu mock. |
| **Broker integration test** | Producer confirm, consumer ack/redelivery/DLQ. | DB + HTTP atomicity ngoài broker. |
| **Database test** | Outbox/inbox transactions, unique key, concurrent consumers. | Remote payment đã xử lý exactly-once. |
| **System/chaos test** | Restart, publish/ack lost, multi-node recovery. | Tất cả lỗi thực tế ngoài mô phỏng. |
| **Security test** | Tenant auth, header spoofing, replay rights, PII. | Những trust boundaries chưa audit. |

Một unit test xanh của `CheckoutApplicationService` không thể bảo đảm một Kafka record đã được broker ghi bền. Cần test tại **ranh giới hạ tầng mà guarantee phụ thuộc**.

### 21.2. Golden contract cho one-way Gateway

~~~text
Command:
  operationId = SUBMIT-901
  orderId = ORD-901
  amountVnd = 850000

Ingress:
  verified tenant = TENANT-A

Gateway:
  method = void submit(OrderSubmission)
  requestChannel = orders.submit.input

Transport:
  durable handoff defined separately

Consumer:
  dedupe key = (TENANT-A, CREATE_ORDER, SUBMIT-901)
  idempotency fingerprint = canonical command fields
  state = NEW -> IN_PROGRESS -> COMPLETED
  receipt = ORD-901

Failure:
  no subscriber -> dispatch error
  invalid -> rejection/quarantine
  timeout after commit -> reconciliation
~~~

Golden fixture nên được kiểm tra qua nhiều tầng: Gateway proxy, channel, adapter, consumer và ledger. Khi một version/schema/routing thay đổi, test giúp đảm bảo semantics one-way không bị biến thành “accepted nhưng không ai nhận” hoặc “duplicate order”.

## 22. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| “Method `void` nghĩa là chạy async.” | Caller vẫn block ở DirectChannel. | Hiểu channel boundary. |
| “One-way nghĩa là không thể throw.” | Không xử lý dispatch exception đồng bộ. | Test error propagation. |
| “Gateway return nghĩa là consumer đã hoàn tất.” | Báo success giả. | Tách handoff và receipt. |
| “QueueChannel mặc định durable.” | Mất message khi restart. | Persistent queue/broker/outbox. |
| “ExecutorChannel đồng nghĩa message sẽ không mất.” | Pending task trong RAM bị mất khi crash. | Durable handoff nếu cần. |
| “Broker ack là business ack.” | Không biết consumer có commit hay không. | Track operation receipt riêng. |
| “Đặt retry quanh void Gateway là enough.” | Double effects hoặc mất message. | Idempotency, state, reconciliation. |
| “Synchronous timeout nghĩa là side effect chưa xảy ra.” | Retry sau external commit. | UNKNOWN outcome + query status. |
| “Trả HTTP 200 Completed khi gateway return.” | Client hiểu sai trạng thái. | Accepted/status contract. |
| “Global errorChannel bắt mọi lỗi.” | Bỏ sót adapter/deserializer errors. | Adapter-specific error tests. |
| “Không có reply nên không cần correlation.” | Không trace được completion event. | Stable IDs/correlation/causation. |
| “Dùng `MessageHeaders.ID` để chống trùng.” | Redelivery rebuild ID khác. | Business operation ID. |
| “Dedupe bằng orderId cho mọi operation.” | Chặn CANCEL/REFUND hợp lệ. | Operation-scoped key. |
| “Dedupe bằng `SEEN` là đã COMPLETED.” | Crash trước commit gây mất xử lý. | Durable state/receipt/recovery. |
| “Retry count đưa vào payload để theo dõi.” | Thay đổi business fingerprint giữa attempts. | Delivery metadata/logs. |
| “Mọi subscribers dùng cùng global dedupe state.” | Nhánh fan-out sau bị chặn. | Consumer-specific keys. |
| “One-way không cần backpressure.” | Queue/threads/storage bùng nổ. | Bounded channels và rate limit. |
| “Không log thì không biết lỗi; log toàn payload.” | PII leak. | Structured redacted logs. |
| “Caller tự khai `trustedTenant`.” | Cross-tenant routing/security flaw. | Trusted auth context. |
| “Gateway trong @Transactional bao trùm broker.” | Dual-write inconsistency. | Outbox/transaction architecture. |
| “Không thấy consumer log = message chắc chắn mất.” | Có thể còn queue/DLQ/pending/replay. | Trace từng mốc bằng identity. |
| “DLQ replay tạo operation mới.” | Side effect nhân đôi. | Replay original operation ID, check ledger. |
| “DirectChannel luôn là thiết kế sai.” | Thêm async vô ích và khó điều tra. | Chọn theo latency/reliability contract. |
| “Publish–Subscribe là một consumer duy nhất.” | Hiểu sai fault isolation/fan-out. | Per-recipient state/metrics. |
| “Graceful shutdown thay persistence.” | Node crash vẫn làm mất pending tasks. | Durable store nếu loss không chấp nhận. |

## 23. Bài tập thực hành

1. **Gateway void cơ bản:** tạo interface `OrderSubmissionGateway` với `@MessagingGateway` và `@Gateway(requestChannel=...)`, gọi từ application service mà không import Spring `Message`.
2. **DirectChannel:** cấu hình `OneWayGatewayConfiguration`, assert một call gọi handler và không trả business reply.
3. **Fake gateway:** unit test `CheckoutApplicationService` bằng method reference/lambda, xác minh operationId được giữ nguyên.
4. **Lỗi đồng bộ:** tạo handler throw, quan sát exception qua DirectChannel và giải thích vì sao return `void` không chặn exception.
5. **No subscriber:** bỏ terminal handler khỏi DirectChannel; assert gateway invocation không được hiểu là successful processing.
6. **Async executor:** chuyển requestChannel sang ExecutorChannel, dùng bounded pool và kiểm tra caller có thể return trước handler.
7. **Async latch:** dùng CountDownLatch để xác minh handler chạy; không assert tức thì sau invocation.
8. **Executor rejection:** giữ worker bị block, lấp bounded queue, gửi thêm command và kiểm tra rejection/backpressure theo cấu hình.
9. **Async error:** làm worker throw sau gateway return; cấu hình error handler và xác nhận có structured failure event/alert.
10. **QueueChannel:** tạo capacity 2 với poller, gửi ba commands, kiểm tra queue-full/send-timeout semantics.
11. **Queue restart:** gửi command vào QueueChannel memory, restart context, chứng minh đó không phải durable queue.
12. **Durable handoff:** thay memory queue bằng broker/persistent store, kiểm tra khả năng phục hồi sau restart ở test hạ tầng.
13. **Latency contract:** đo riêng thời gian Gateway return, broker confirm và consumer completion; không gộp thành một metric.
14. **Business status:** thiết kế `OperationStatus(SUBMIT-901)` với NEW/IN_PROGRESS/COMPLETED/UNKNOWN; không đánh dấu completed ngay tại gateway.
15. **HTTP response:** dùng API 202 Accepted + operation reference khi durable acceptance đạt được; kiểm tra status endpoint sau đó.
16. **Outbox:** ghi order row và outbox event trong cùng DB transaction; relay publish với stable event ID.
17. **Producer ack lost:** giả lập publish thành công nhưng publisher không thấy ack, retry cùng event ID và kiểm tra consumer không double process.
18. **Consumer ack lost:** commit business rồi kill consumer trước ack, xác minh redelivery trả previous receipt.
19. **Same operation, two Spring messages:** rebuild message với ID runtime mới và assert consumer dedupe vẫn dựa `operationId`.
20. **Fingerprint conflict:** gửi cùng operationId với amount khác; phải ra conflict, không tạo đơn thứ hai.
21. **Filter:** thêm validation Filter trước handler, route invalid vào quarantine có reason codes thay vì silent drop.
22. **Gateway response contract:** so sánh trường hợp cần trả `OrderReceipt` ngay với case chỉ cần gửi command; chọn request–reply hay one-way có lý do.
23. **Router:** định tuyến `SubmitOrder` và `CancelOrder` tới hai handlers; không dùng client-supplied arbitrary channel name.
24. **Publish–Subscribe:** một event tới Audit, Notification, Analytics; mỗi consumer có idempotency key riêng.
25. **Splitter:** chia batch thành child commands có stable child IDs và test duplicate một child không thay child bị thiếu.
26. **Aggregator:** có một child invalid; thiết kế failure outcome/timeout và completion event của batch.
27. **Scatter–Gather:** Inventory pass nhưng Fraud timeout; không phát final approval cho toàn đơn.
28. **Resequencer:** gửi events 1,3 trước 2; xác minh ordering/gap policy và ghi business version đúng.
29. **Claim Check:** đưa payload lớn vào protected store rồi Gateway gửi reference; test claim expired, retention và quyền restore.
30. **Header mapping:** truyền businessEventId/correlationId qua outbound/inbound adapter, bảo đảm Spring Message ID có thể khác.
31. **Tenant security:** thử header tự khai `trustedTenant=TENANT-A` dưới principal tenant B; deny trước routing.
32. **Rate limit:** phát commands nhanh hơn consumer xử lý, thiết kế queue capacity và behavior khi overload.
33. **Transaction:** chứng minh một DB transaction không tự bao trùm broker publish; đưa ra kế hoạch outbox/recovery.
34. **DLQ replay:** replay một command đã completed; kiểm tra idempotency ledger không chạy lại side effect.
35. **Metric audit:** tạo dashboard phân biệt gateway invocations, channel handoff, published, received, unique business completed.
36. **Production runbook:** mô tả đầy đủ tuyến chẩn đoán “gateway return nhưng không thấy business result” ở các ranh giới.

### 23.1. Tiêu chí nghiệm thu

Một implementation one-way Gateway được xem là đạt yêu cầu bài học khi:

- Application caller gọi Java interface rõ nghĩa và không tự biết `MessageChannel` nếu không cần.
- Có request channel và subscriber/adapter được cấu hình đúng, có integration test.
- Hiểu `void` **không phải async**, không phải durable và không phải no-throw guarantee.
- Chọn Direct/Executor/Queue/broker theo latency, workload và yêu cầu lưu bền.
- Thời điểm báo accepted/published/completed có bằng chứng theo contract.
- Error path được xử lý cho cả synchronous failures và asynchronous failures.
- Retry có bounded policy, không lặp remote business effect.
- Stable operation identity và durable state/receipt chống duplicate qua redelivery/crash.
- Có security, rate limits, tenant isolation, metadata preservation, redacted logs.
- Có test đúng ranh giới adapter, broker, database và recovery cần được tin cậy.

## 24. Câu hỏi tự kiểm tra

**Câu 1: One-way Messaging Gateway là gì?**

Là một gateway interface đưa message từ Java application vào Spring Integration flow mà invocation không yêu cầu business reply payload từ receiver, ví dụ phương thức `void submit(OrderSubmission)`.

**Câu 2: `void` có tự khiến message được xử lý bất đồng bộ không?**

Không. `DirectChannel` có thể dispatch đồng bộ trong caller thread. Bất đồng bộ đến từ `ExecutorChannel`, QueueChannel/poller, broker hoặc một async boundary khác.

**Câu 3: Tại sao `void submit(...)` vẫn có thể ném exception?**

Vì việc gửi message hoặc synchronous downstream handler có thể lỗi trước khi method return. `void` chỉ nói Java method không trả một giá trị nghiệp vụ.

**Câu 4: Khi sử dụng DirectChannel, caller thường chờ đến mốc nào?**

Caller chạy theo synchronous dispatch cho tới khi channel/handler return (hoặc throw). Điều đó không nhất thiết chứng minh một external business side effect được commit bền nếu handler không có chứng cứ tương ứng.

**Câu 5: ExecutorChannel có đảm bảo message không mất khi process crash không?**

Không. ThreadPoolTaskExecutor và queue memory không phải persistent store. Cần durable handoff nếu loss không chấp nhận được.

**Câu 6: QueueChannel khác ExecutorChannel thế nào?**

QueueChannel là pollable queue với consumer thường nhận qua poller; ExecutorChannel dispatch công việc qua executor. Cả hai có thể tách caller khỏi handler, nhưng durability và failure semantics phải thiết kế riêng.

**Câu 7: Gateway return sau khi gửi vào QueueChannel có nghĩa consumer đã xử lý chưa?**

Không. Message có thể còn trong queue, poller chưa lấy, consumer đang lỗi hoặc backlog đang tăng.

**Câu 8: Broker confirm có nghĩa business hoàn tất không?**

Không. Broker confirm xác nhận mốc nhận/lưu record theo broker contract, không phải payment/order transaction của consumer.

**Câu 9: Vì sao cần transactional outbox khi cập nhật DB rồi publish event?**

Để tránh mất/nhân đôi intent do dual-write DB và broker không atomic mặc định. Outbox giữ event metadata và payload reference trong cùng DB transaction; relay phát lại theo stable identity.

**Câu 10: Outbox có làm mọi message được xử lý exactly-once không?**

Không. Relay có thể publish trùng khi ack mất; consumer vẫn phải idempotent và xử lý các crash windows.

**Câu 11: Nếu broker giao lại một command sau khi DB đã commit, xử lý thế nào?**

Tra durable operation ledger theo stable business operation ID, xác minh fingerprint và authoritative receipt, tránh side effect thứ hai.

**Câu 12: Có nên dùng Spring `MessageHeaders.ID` làm idempotency key không?**

Không mặc định. Spring Message ID có thể khác khi rebuild message hoặc adapter deserializes record. Cần stable event/operation identity của business.

**Câu 13: Cùng `orderId` nhưng CREATE và CANCEL có phải duplicate không?**

Không. Đây là các operation hợp lệ khác nhau, key cần có operation type và operation ID phù hợp.

**Câu 14: Caller không đợi reply có nên bỏ correlationId không?**

Không. Correlation/causation vẫn hữu ích để liên kết asynchronous completion events, logs, workflow và trạng thái; nhưng không thay business operation ID.

**Câu 15: Khi async worker throw sau Gateway return, caller có nhận exception ngay không?**

Không qua lời gọi đồng bộ đã kết thúc. Cần configured error channel/recovery/DLQ/status tracking và test theo channel/adapter cụ thể.

**Câu 16: Filter loại message trong one-way flow có chắc đã ghi quarantine chưa?**

Không. Filter discard và quarantine persistence là hai mốc. Cần cấu hình discardChannel + durable handler và kiểm tra ack/error path.

**Câu 17: Khi request invalid, có nên retry không giới hạn không?**

Không. Lỗi deterministic thường cần sửa input/policy, không tự hết nhờ retry. Technical failures có thể dùng bounded retry/backoff.

**Câu 18: Nếu Gateway gọi trong `@Transactional`, broker send có tự rollback cùng DB không?**

Không mặc định. Cần xác định transaction resources và thiết kế outbox/coordination khi cần consistency.

**Câu 19: Tại sao gửi one-way vẫn cần backpressure?**

Vì caller có thể phát nhanh hơn consumer xử lý. Không giới hạn queue/threads dẫn tới OOM, latency cao và failure khó phục hồi.

**Câu 20: Có thể trả HTTP “ORDER_COMPLETED” sau khi một one-way Gateway return không?**

Không nếu business processing còn chạy sau đó. Chỉ báo accepted khi có đúng bằng chứng, cung cấp status/receipt hoặc completion event cho kết quả cuối.

**Câu 21: Một event gửi tới nhiều subscribers có nên có một global dedupe marker không?**

Không nếu mỗi consumer phải xử lý một tác vụ độc lập. Nên scope key theo recipient/consumer và logical event.

**Câu 22: Tại sao Gateway không thay Outbound Channel Adapter?**

Gateway là ranh giới Java API → message flow; outbound adapter là ranh giới flow → hệ thống ngoài. Chúng thường xuất hiện cùng nhau.

**Câu 23: Nếu caller bắt exception do timeout, có chắc side effect chưa xảy ra không?**

Không. Một remote system có thể đã commit nhưng response/ack thất lạc; state là UNKNOWN và cần reconciliation hoặc remote idempotency.

**Câu 24: `replyChannel` trong Spring Message có gửi nguyên qua Kafka/HTTP được không?**

Không nên giả định. Nó có thể là object JVM nội bộ, không wire-portable và không nên nhận arbitrary object từ nguồn không đáng tin.

**Câu 25: Message History có thay authoritative business receipt được không?**

Không. Nó giúp trace các component, không chứng minh DB/remote payment commit hoặc authorization/replay state.

**Câu 26: Một command bị queue đợi quá lâu có còn hợp lệ để xử lý không?**

Tùy business deadline và policy. Nếu đã expired/cancelled, consumer phải có quy tắc xử lý rõ, không tự thực hiện một giao dịch quá hạn.

**Câu 27: Nên kiểm thử one-way Gateway ở cấp nào?**

Unit test API invocation, Spring Integration test proxy/channel, async/error test, adapter/broker test, DB/outbox/inbox test, system crash/replay test và security test cho những ranh giới liên quan.

**Câu 28: Ba câu hỏi quan trọng trước khi chọn void Gateway là gì?**

**(1)** Caller thật sự không cần business reply ngay chứ? **(2)** Lời gọi return ở mốc handoff nào và message có durable không? **(3)** Lỗi, duplicate và completion sau đó được quan sát/phục hồi ở đâu?

## 25. Quy trình lựa chọn nhanh

~~~mermaid
flowchart TD
    START["Application needs to send a command/event"] --> Q1{"Caller needs business result now?"}
    Q1 -->|Yes| REPLY["Request–Reply Gateway + bounded deadline"]
    Q1 -->|No| Q2{"Need durable handoff?"}
    Q2 -->|No| Q3{"Must caller wait for synchronous processing?"}
    Q3 -->|Yes| DIRECT["Void Gateway + DirectChannel"]
    Q3 -->|No| ASYNC["Void Gateway + bounded async/queue; accept loss contract"]
    Q2 -->|Yes| DURABLE["Void Gateway + outbox/durable broker/channel"]
    DURABLE --> INBOX["Idempotent consumer + status/receipt"]
    REPLY --> ERR["Timeout/error/unknown outcome handling"]
    DIRECT --> ERR
    ASYNC --> ERR
    INBOX --> ERR
~~~

Sơ đồ là một **hướng dẫn lựa chọn**, không phải thuật toán áp dụng cho mọi hạ tầng. Cả request–reply lẫn one-way đều có thể cần outbox/idempotency, retry, authorization và quan sát. Quyết định dựa trên **business contract, latency và độ tin cậy**, không chỉ phương thức Java trả về `void` hay một class có tên Gateway.

## 26. Kết luận

**Gateway gửi one-way message** giúp application service sử dụng một **giao diện Java đơn giản** để đưa command hoặc event vào Spring Integration flow mà không yêu cầu reply payload cho lời gọi ban đầu. Với Java DSL, `@MessagingGateway` và `@Gateway(requestChannel=...)` kết nối method `void submit(...)` vào channel; downstream có thể là Filter, Transformer, Router, Service Activator, broker adapter hoặc workflow lớn hơn.

**Nhưng một chiều không đồng nghĩa bất đồng bộ hoặc đáng tin cậy tuyệt đối.** `DirectChannel` có thể chạy đồng bộ và ném exception về caller; `ExecutorChannel`/`QueueChannel` có thể return trước khi xử lý nhưng không mặc định durable; một broker confirm không phải bằng chứng business completion. Chỉ khi thiết kế rõ mốc acceptance, acknowledgment, transaction, backpressure, error handling và replay thì one-way API mới có hợp đồng vận hành đáng tin.

Trong `SPRING_INTEGRATION_PATTERN`, kết hợp Gateway với Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, retry, error channel, correlation và Idempotent Receiver để xây flow ít phụ thuộc, có thể mở rộng và kiểm thử được. Hãy luôn phân biệt **“đã gửi vào channel”**, **“đã ghi bền ở transport”** và **“đã hoàn tất side effect”**; giữ stable operation ID, lưu authoritative outcome và kiểm thử các crash windows. Đó là nền tảng để dùng một one-way Gateway vừa đơn giản ở API, vừa đúng đắn khi hệ thống gặp lỗi.
