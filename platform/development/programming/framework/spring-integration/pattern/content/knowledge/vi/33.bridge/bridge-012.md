# Kiểm thử bridge không làm mất message

## 1. Bài toán: thêm Bridge để nối hai channel nhưng một số sự kiện biến mất

Ứng dụng nhận event từ đơn hàng, chuyển qua một kênh đệm, rồi gọi handler cập nhật trạng thái:

~~~text
Producer
  → orders.in
  → Bridge
  → orders.process
  → OrderEventHandler
  → Database
~~~

Trong môi trường phát triển, một test đơn giản gửi một message và thấy handler được gọi:

~~~java
assertTrue(inputChannel.send(message));
~~~

Nhưng trên production có những câu hỏi khó hơn:

- Nếu downstream channel không có subscriber, message có bị mất hay lỗi được báo về upstream?
- Nếu Bridge đang poll một `QueueChannel`, message đã bị lấy ra nhưng handler lỗi thì ai giữ trách nhiệm retry?
- Nếu nối sang `ExecutorChannel`, `send()` trả về trước khi business method chạy: một crash ở giữa có làm mất event?
- Khi xử lý lại sau broker redelivery, làm thế nào phân biệt **message mất**, **message xử lý chậm** và **message được thực hiện hai lần**?
- Nếu output có nhiều subscribers hoặc bị đổi loại channel, giả định one-to-one forwarding còn đúng không?
- Nếu upstream ACK trước khi downstream lưu bền vững, Bridge có cứu được event sau restart không?

**Bài này hướng dẫn kiểm thử đúng hợp đồng của Bridge và cả khoảng cách giữa message forwarding với bảo đảm delivery bền vững.** Đây là hai mức độ khác nhau, không nên gọi một integration test happy-path là bằng chứng “không bao giờ mất message”.

~~~mermaid
flowchart LR
    PUB["Producer"] --> IN["Input channel"]
    IN --> BR["Bridge endpoint"]
    BR --> OUT["Output channel"]
    OUT --> H["Business handler"]
    H --> DB["Durable business state"]
    BR -. "Forwarding success" .-> OBS["Metrics / assertions"]
    DB -. "Completion proof" .-> OBS
~~~

Bài thuộc chương **Bridge** của module **SPRING_INTEGRATION_PATTERN**: học triển khai Enterprise Integration Patterns bằng **Spring Integration**, xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng, thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý.

**Kết quả học tập:** hiểu vai trò của `BridgeHandler`/DSL `.bridge()`, viết test forwarding và nội dung message, kiểm tra đường lỗi ở `DirectChannel`/`QueueChannel`/`ExecutorChannel`, xác định khoảng mất dữ liệu quanh ACK/transaction, thiết kế retry/idempotency và xây bộ kiểm thử fault injection có thể lặp lại.

## 2. Bridge trong Spring Integration làm gì?

Một **Bridge** nối một message channel ở phía nguồn với một channel khác ở phía đích. Nó phù hợp khi **không cần biến đổi payload**, không cần quyết định route dựa trên nội dung và không cần chạy business method.

~~~text
inputChannel → Bridge → outputChannel
~~~

Trong Spring Integration, có thể cấu hình một Bridge endpoint bằng Java DSL `.bridge()` hoặc bằng `BridgeHandler` với input/output channel phù hợp.

Bridge **không tự**:

1. Biến một in-memory channel thành persistent queue.
2. Tạo một distributed transaction giữa broker và database.
3. Retry vô hạn một message khi downstream lỗi.
4. Giữ thứ tự hoàn tất nếu đích dùng executor song song.
5. Xác minh quyền truy cập, business idempotency hay payload schema.
6. Chứng minh bên nhận external đã commit chỉ vì việc gửi tới channel hoàn tất.

**Nó chuyển tiếp message theo semantics của endpoint và các channel được nối.** Bảo đảm không mất message phụ thuộc đặc biệt vào nguồn, đích, acknowledgment, error path và độ bền của việc bàn giao.

## 3. Bridge khác Router, Transformer, Service Activator và Channel Adapter

| Thành phần | Câu hỏi chính | Output thường thấy |
|---|---|---|
| **Bridge** | Làm sao nối hai channels mà không cần xử lý nội dung? | Chuyển tiếp message |
| **Transformer** | Cần đổi payload hoặc message representation ra sao? | Payload/message đã chuyển |
| **Filter** | Message này có được đi tiếp không? | Cho qua hoặc reject/discard |
| **Router** | Message cần đi sang nhánh nào? | Chọn một/nhiều channels theo policy |
| **Service Activator** | Method nghiệp vụ nào được gọi? | Kết quả method, có thể có side effect |
| **Channel Adapter** | Kết nối một transport/nguồn/đích bên ngoài thế nào? | One-way inbound/outbound integration |
| **Gateway** | Caller cần request–reply và response correlation không? | Request và reply theo contract |

Ví dụ:

~~~text
Kafka inbound adapter
  → orders.in
  → Bridge
  → orders.process
  → Service Activator
  → DB commit
~~~

Kafka adapter nhận từ broker; Bridge nối channels; Service Activator thực hiện nghiệp vụ. **Không gọi Bridge là consumer của Kafka** nếu nó chỉ nhận message do adapter đã tạo; việc commit Kafka offset thuộc listener/container policy.

Tên **Messaging Bridge** trong Enterprise Integration Patterns đôi khi còn nói tới **kết nối hai messaging systems**. Trong bài này, trọng tâm là **Spring Integration Bridge endpoint chuyển message giữa các Spring channels**. Muốn kết nối hai brokers/processes, còn cần inbound/outbound adapters, protocol, ACK/retry và durable handoff.

## 4. “Không mất message” phải có định nghĩa kiểm chứng được

Ta cần ít nhất bốn bất biến, tùy business contract:

| Bất biến | Ý nghĩa | Chứng cứ phù hợp |
|---|---|---|
| **Integrity** | Payload và business headers cần thiết không bị đổi sai | Compare message fields |
| **No unintended drop** | Message hợp lệ không biến mất im lặng trong một đường đi không có failure được xử lý | Received IDs, error/recovery IDs |
| **Durable responsibility** | Khi ACK nguồn, work đã hoàn tất hoặc đã được bàn giao bền vững | DB commit, durable store/queue và crash tests |
| **No duplicate effect** | Retry/redelivery không tạo side effect nghiệp vụ trùng | Unique constraints, inbox, committed result |

Với một cửa sổ đo có N logical messages được chấp nhận bền vững:

\[
N_{\text{accepted}} =
N_{\text{completed}} + N_{\text{durable pending}}
+ N_{\text{durable terminal failures}}
\]

Đây là **một phương trình kiểm kê theo trạng thái loại trừ nhau**, không phải metric tự có của Spring Integration. Cần đảm bảo một logical message không bị đếm hai lần, và chỉ gọi `accepted` sau mốc được định nghĩa rõ.

**Không đặt `receivedCount == successCount` làm bất biến chung cho các hệ thống có retries, quarantine hoặc đang xử lý hợp lệ.** Cần theo dõi trạng thái của **từng business message ID**.

## 5. Đặt phạm vi kiểm thử: forwarding khác hoàn tất nghiệp vụ

Hai lời khẳng định thường bị lẫn:

1. **Bridge forwarding correctness:** message đi từ input channel đến output channel, mang payload và headers mong đợi.
2. **End-to-end delivery correctness:** message vẫn có đường xử lý hoặc recovery bền vững qua crash/timeout và tạo đúng business outcome.

Một unit/integration test đơn giản có thể chứng minh (1) trong topology có sẵn. Để chứng minh (2), phải kiểm thử **source ACK, store durability, transaction boundaries, downstream failures, restart và retry**.

~~~text
Input DirectChannel
  → Bridge
  → Output QueueChannel in memory

Test: send() → receive() == original payload
  ✔ Chứng minh forwarding bình thường.
  ✘ Chưa chứng minh message sống sót khi process restart.
~~~

**Đừng gắn nhãn “exactly-once” cho Bridge.** Nó không tự kiểm soát remote broker, database và retry outcomes.

## 6. Bridge và ngữ nghĩa payload, headers, message identity

Khi một Bridge được dùng đúng vai trò, nên kiểm tra:

- Payload đến đích có giá trị/kiểu tương thích.
- Các **business headers cần thiết** như `eventId`, `correlationId`, `tenantScope` còn nguyên.
- Destination nhận đúng số **logical messages**.
- Không tự thêm một bước serialize/deserialize gây mất field hoặc chuyển sai kiểu.
- Nếu flow có reply/error metadata, nó còn hợp lệ ở phạm vi được hỗ trợ.

Không nên xây tính đúng đắn chỉ dựa vào **Spring `MessageHeaders.ID` giữ nguyên byte-for-byte**. Một số endpoints, transformations, header enrichers hoặc adapter boundaries có thể tái tạo message và đổi framework-level ID/timestamp. **Business event ID trong payload/header** mới là nhận diện ổn định qua retry, transport và replay.

Ví dụ message:

~~~java
Message<String> event = MessageBuilder
    .withPayload("ORDER_CREATED:O-501")
    .setHeader("eventId", "EV-501")
    .setHeader("businessCorrelationId", "tenant-a|O-501")
    .setHeader("schemaVersion", 1)
    .build();
~~~

Test cần khẳng định `EV-501`, correlation và schema version đúng ở output, không nhất thiết lấy hai framework IDs làm key so sánh.

## 7. Ví dụ Java DSL: nối input và output bằng Bridge

Một cấu hình cô lập, dễ test:

~~~java
@Configuration
@EnableIntegration
class BridgeFlowConfiguration {

    @Bean("orders.bridge.input")
    MessageChannel bridgeInput() {
        return new DirectChannel();
    }

    @Bean("orders.bridge.output")
    PollableChannel bridgeOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow ordersBridgeFlow() {
        return IntegrationFlow
            .from("orders.bridge.input")
            .bridge()
            .channel("orders.bridge.output")
            .get();
    }
}
~~~

Ở đây:

- Input là `DirectChannel`, dispatch đồng bộ tới Bridge handler.
- Bridge forward tới output channel.
- Output `QueueChannel` cho phép integration test gọi `receive(timeout)` để đọc kết quả.

Đây là **test topology có chủ đích**, không phải gợi ý dùng `QueueChannel` in-memory làm durable production queue. Cần dependency Spring Integration, imports và Spring test context tương ứng; API DSL cần được đối chiếu với phiên bản thực tế khi compile.

## 8. Test happy path: một message đến đúng output channel

Ví dụ JUnit 5 với Spring test context:

~~~java
@SpringJUnitConfig(BridgeFlowConfiguration.class)
class BridgeFlowTest {

    @Autowired
    @Qualifier("orders.bridge.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.bridge.output")
    PollableChannel output;

    @Test
    void forwardsPayloadAndBusinessHeaders() {
        Message<String> sent = MessageBuilder
            .withPayload("ORDER_CREATED:O-501")
            .setHeader("eventId", "EV-501")
            .setHeader("businessCorrelationId", "tenant-a|O-501")
            .setHeader("schemaVersion", 1)
            .build();

        assertTrue(input.send(sent));

        Message<?> received = output.receive(1_000);
        assertNotNull(received);
        assertEquals("ORDER_CREATED:O-501",
            received.getPayload());
        assertEquals("EV-501",
            received.getHeaders().get("eventId"));
        assertEquals("tenant-a|O-501",
            received.getHeaders().get("businessCorrelationId"));
        assertEquals(1,
            received.getHeaders().get("schemaVersion"));
    }
}
~~~

**Mẫu test cần các imports JUnit/Spring tương ứng.** Nó xác nhận input → Bridge → output **trong một JVM đang hoạt động**. Chưa có broker, database, retry hay process crash nên **không được tuyên bố đã chứng minh durability**.

## 9. Test không phát thêm message: zero duplicate trên đường bình thường

Sau khi đã receive một message, cần xác nhận output queue không chứa bản sao ngoài ý muốn:

~~~java
@Test
void oneInputHasOneOutputWithoutRetry() {
    Message<String> sent = MessageBuilder
        .withPayload("ORDER_CREATED:O-501")
        .setHeader("eventId", "EV-501")
        .build();

    assertTrue(input.send(sent));

    Message<?> first = output.receive(1_000);
    assertNotNull(first);
    assertEquals("EV-501",
        first.getHeaders().get("eventId"));

    Message<?> unexpected = output.receive(100);
    assertNull(unexpected);
}
~~~

Test trên nên dùng **một Spring test instance/context có queue được làm sạch** trước mỗi case, hoặc có chiến lược isolation; nếu test trước để lại messages, assertion về duplicate có thể sai. `receive(100)` chỉ chứng minh **không có message thứ hai trong khoảng quan sát đó**, không chứng minh không thể có late duplicate sau 10 phút hoặc sau restart.

## 10. Test N messages: so set IDs, không chỉ so count

Kiểm tra 200 events độc lập:

~~~java
@Test
void allLogicalMessagesArriveExactlyOnceInHealthyFlow() {
    int total = 200;
    Set<String> expected = new HashSet<>();

    for (int i = 0; i < total; i++) {
        String id = "EV-" + i;
        expected.add(id);
        assertTrue(input.send(
            MessageBuilder.withPayload("event:" + i)
                .setHeader("eventId", id)
                .build()));
    }

    Map<String, Integer> observedCounts = new HashMap<>();
    for (int i = 0; i < total; i++) {
        Message<?> received = output.receive(1_000);
        assertNotNull(received);
        String id = (String)
            received.getHeaders().get("eventId");
        observedCounts.merge(id, 1, Integer::sum);
    }

    assertEquals(expected, observedCounts.keySet());
    assertTrue(observedCounts.values().stream()
        .allMatch(count -> count == 1));
    assertNull(output.receive(100));
}
~~~

Chỉ dùng `receivedCount == 200` là chưa đủ: có thể mất `EV-19` và nhận lặp `EV-20`, tổng vẫn là 200. **So tập ID + multiplicity** giúp nhận ra cả mất và trùng.

Đây vẫn chỉ là test **healthy in-memory forwarding**, không phải exactly-once guarantee khi producer/broker redeliver. Nên đặt timeouts hợp lý để test không chờ vô hạn nếu message bị mất.

## 11. Test loại payload và giữ header cần thiết

Một Bridge không phải Transformer. Nếu nguồn gửi:

~~~java
record OrderEvent(
    String eventId,
    String orderId,
    int version,
    String type
) {}
~~~

Output nên giữ nội dung event theo hợp đồng:

~~~java
OrderEvent original =
    new OrderEvent("EV-501", "O-501", 3, "CREATED");

assertTrue(input.send(MessageBuilder
    .withPayload(original)
    .setHeader("tenantScope", "tenant-a")
    .build()));

Message<?> received = output.receive(1_000);
assertNotNull(received);
assertInstanceOf(OrderEvent.class, received.getPayload());
assertEquals(original, received.getPayload());
assertEquals("tenant-a",
    received.getHeaders().get("tenantScope"));
~~~

Với record bất biến, `equals()` so theo giá trị các components. Nếu một payload là mutable POJO, việc output chứa cùng object tham chiếu **không chứng minh không bị thay đổi sau khi send**. Dùng immutable DTO hoặc snapshot fields khi kiểm thử; các transport serialization boundaries có thể tạo bản sao và biến đổi biểu diễn.

## 12. Test message ordering: xác định phạm vi đúng

Với đường **DirectChannel → Bridge → QueueChannel**, một test gửi tuần tự trên một thread và nhận queue tuần tự có thể kiểm tra output order:

~~~java
@Test
void sequentialBridgePreservesArrivalOrderInTestTopology() {
    for (int i = 0; i < 20; i++) {
        assertTrue(input.send(MessageBuilder
            .withPayload(i)
            .setHeader("eventId", "EV-" + i)
            .build()));
    }

    for (int i = 0; i < 20; i++) {
        Message<?> item = output.receive(1_000);
        assertNotNull(item);
        assertEquals(i, item.getPayload());
    }
}
~~~

**Không mở rộng kết luận sang mọi channel types.** Nếu output sau Bridge là `ExecutorChannel` với nhiều threads, việc handler hoàn tất có thể lệch thứ tự; Kafka chỉ cung cấp log order theo partition, không cung cấp global business ordering.

Ordering cần được test ở **vị trí side effect thực sự commit**, không chỉ tại lúc Bridge forward.

## 13. Bảng rủi ro theo loại input/output channel

| Topology | Điều xảy ra bình thường | Rủi ro khi lỗi |
|---|---|---|
| `DirectChannel → Bridge → DirectChannel` | Dispatch đồng bộ qua call stack | Không có durability mặc định; lỗi có thể lan về sender |
| `DirectChannel → Bridge → QueueChannel (memory)` | Gửi vào bộ đệm, consumer đọc sau | Queue mất khi process chết; send success chưa là business success |
| `QueueChannel → poller → Bridge → DirectChannel` | Poller lấy message khỏi queue rồi chuyển | Khoảng trống giữa remove và handler completion |
| `QueueChannel (persistent) → poller → Bridge → handler` | Nội dung có thể nằm trong durable store | Cần transaction/recovery khi receive/remove và downstream thất bại |
| `DirectChannel → Bridge → ExecutorChannel` | Enqueue vào executor rồi trả quyền điều khiển | Task in-memory mất khi crash; completion có thể lệch thứ tự |
| `Broker adapter → Bridge → business handler` | Transport message vào IntegrationFlow | ACK/offset phải khớp durable processing |
| `Bridge → outbound broker adapter` | Gửi sang broker ngoài | Publish confirm và upstream ACK không mặc nhiên atomic |

**Chỉ dùng tên lớp Bridge không đủ suy ra delivery guarantee.** Test phải chỉ rõ channel types, thread boundary, message store, source ownership và điểm hoàn tất được cam kết.

## 14. DirectChannel: xử lý đồng bộ nhưng không bền qua crash

Với:

~~~text
Producer thread
  → DirectChannel(input)
  → Bridge
  → DirectChannel(output)
  → Handler
~~~

Trong topology đồng bộ thông thường, nếu output handler ném exception, exception có thể lan về caller của `send()`. Đây là **cơ hội để caller/inbound adapter thực hiện recovery**, không tự là bảo đảm retry.

Nếu producer:

~~~java
try {
    input.send(message);
} catch (Exception failure) {
    logger.warn("event dropped");
}
~~~

thì **caller đã có thể làm mất trách nhiệm xử lý** vì nuốt exception mà không có durable retry. DirectChannel không cứu message chưa persist và không được gửi lại.

**Test cần xem failure propagation và recovery policy**, không chỉ happy-path send.

## 15. Test output channel không có subscriber

Một cấu hình test tách biệt:

~~~java
@Configuration
@EnableIntegration
class BrokenBridgeConfiguration {

    @Bean("broken.input")
    MessageChannel brokenInput() {
        return new DirectChannel();
    }

    @Bean("broken.output")
    MessageChannel brokenOutput() {
        // Cố ý không đăng ký subscriber.
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow brokenBridge() {
        return IntegrationFlow.from("broken.input")
            .bridge()
            .channel("broken.output")
            .get();
    }
}
~~~

Test:

~~~java
@SpringJUnitConfig(BrokenBridgeConfiguration.class)
class BrokenBridgeTest {

    @Autowired
    @Qualifier("broken.input")
    MessageChannel input;

    @Test
    void missingSubscriberMustNotBeTreatedAsSuccess() {
        Message<String> message = MessageBuilder
            .withPayload("EV-501")
            .setHeader("eventId", "EV-501")
            .build();

        assertThrows(
            MessagingException.class,
            () -> input.send(message));
    }
}
~~~

Trong `DirectChannel` đồng bộ với dispatcher mặc định, không có subscriber thường gây lỗi dispatch trong họ `MessagingException`. **Loại exception/cause cần xác minh theo Spring Integration version thực tế**.

Test này có điều kiện: caller **chưa ACK bền vững**; nếu caller đã ACK rồi mới gửi vào Bridge, exception cũng không khôi phục được record nguồn đã xác nhận sai thời điểm.

## 16. Test downstream handler ném exception

Một handler đã nhận message cũng có thể thất bại:

~~~java
@Bean
IntegrationFlow failingDownstreamFlow() {
    return IntegrationFlow.from("bridge.fail.input")
        .bridge()
        .handle(
            String.class,
            (payload, headers) -> {
                throw new IllegalStateException(
                    "SIMULATED_DB_UNAVAILABLE");
            })
        .get();
}
~~~

Với `DirectChannel` đồng bộ, caller test:

~~~java
assertThrows(MessagingException.class,
    () -> failingInput.send(
        MessageBuilder.withPayload("EV-501").build()));
~~~

**Đoạn flow cần input channel `bridge.fail.input` trong test context.** Spring có thể bọc handler exception trong messaging wrapper; không so raw exception text như contract. Khi thêm advice/error handler hoặc chuyển sang async, expected exception path phải thay theo.

Để chứng minh **không mất message**, còn phải xác minh caller/adapter **không commit progress** trước durable recovery và message có thể retry theo policy.

## 17. QueueChannel: poll/receive có thể làm mất trách nhiệm xử lý

Một `QueueChannel` in-memory:

~~~text
Producer sends EV-501 → QueueChannel (memory)
Poller receives EV-501 → removed from queue
Bridge forwards → handler throws
Process crashes
~~~

Nếu không có transactional message store, durable retry queue hoặc requeue/recovery protocol, **message không mặc nhiên xuất hiện lại**. Polling nghĩa là consumer chủ động lấy dữ liệu; **lấy ra** khác với **xử lý thành công**.

~~~mermaid
sequenceDiagram
    participant Q as QueueChannel
    participant P as Poller
    participant B as Bridge
    participant H as Handler
    P->>Q: receive()
    Q-->>P: EV-501 removed
    P->>B: forward(EV-501)
    B->>H: process(EV-501)
    H--xB: failure
    Note over P,H: Without recovery, responsibility may be lost
~~~

**Một QueueChannel không phải message broker bền vững chỉ vì có chữ queue.** Cần xác định memory-backed hay persistent store và transaction có bao gồm receive/remove cùng downstream processing không.

## 18. Pollable source nối qua Bridge cần poller

Ví dụ nguồn là `QueueChannel`:

~~~java
@Bean("bridge.pollable.source")
PollableChannel pollableSource() {
    return new QueueChannel();
}

@Bean("bridge.pollable.target")
MessageChannel pollableTarget() {
    return new DirectChannel();
}

@Bean
IntegrationFlow bridgePollableChannel() {
    return IntegrationFlow
        .from("bridge.pollable.source",
            c -> c.poller(Pollers.fixedDelay(200)
                .maxMessagesPerPoll(5)))
        .bridge()
        .channel("bridge.pollable.target")
        .get();
}
~~~

Đây là mô hình **Bridge endpoint có polling khi nguồn là pollable channel**. Không đăng ký flow khác cùng tiêu thụ `bridge.pollable.source` nếu test muốn một consumer duy nhất.

**Lưu ý API:** ký hiệu Java DSL `IntegrationFlow.from(..., c -> c.poller(...))`/`Pollers` cần đối chiếu version Spring Integration thực tế; điều kiện khái niệm là nguồn pollable cần poller/scheduler rõ.

Với nguồn in-memory này vẫn **không có durability**. Có thể cấu hình transaction advice/retry/error channel cho poller, nhưng phải xác minh với store/transaction manager, không suy ra chỉ từ `fixedDelay`.

## 19. Test poller chạy thật, không dùng `receive()` nhầm vào source

Test:

~~~text
source QueueChannel
  → bridge poller
  → target DirectChannel
  → capture handler
~~~

Các bước:

1. Gửi `EV-501` vào **source QueueChannel**.
2. Đợi **capture handler sau Bridge** thấy eventId.
3. Assert payload/business headers không đổi sai.
4. Assert không duplicate trong test window.
5. Đảm bảo test khác không cùng dùng source và poller.

**Không vừa gửi nguồn rồi gọi `source.receive()` để tự kiểm chứng**: thao tác ấy có thể **cướp message khỏi poller**. Quan sát target/durable downstream state.

Đợi bằng latch, bounded Awaitility hoặc test sink; không dùng `Thread.sleep(5000)` cố định rồi đoán poller đã chạy.

## 20. Test poller lỗi: message đã lấy ra có được phục hồi không?

Fault injection:

~~~text
Source QueueChannel holds EV-501.
Poller receives EV-501.
Bridge forwards to handler.
Handler throws SIMULATED_DB_DOWN.
Poller error path runs.
~~~

**Không mặc định EV-501 còn trong QueueChannel**. Với in-memory queue không transaction, nó có thể đã rời nguồn. Test đúng phải xác nhận failure policy:

- Durable transactional receive/rollback làm message khả dụng lại theo store semantics.
- Durable retry/DLQ recoverer ghi message tới recovery destination trước khi bỏ nguồn.
- Nếu không có cả hai, **no-loss test phải thất bại**, dù error channel đã ghi log.

Lỗi được log **không đồng nghĩa message còn được giữ trách nhiệm xử lý**.

## 21. Persistent QueueChannel không tự tạo distributed exactly-once

Một QueueChannel có persistent message group store giúp giữ dữ liệu qua restart trong những điều kiện cấu hình/kiểm thử. Nhưng:

~~~text
DB-1: MessageGroupStore stores EV-501
DB-1: Poller removes EV-501
DB-2: Business handler writes OrderCreated
~~~

Nếu remove ở DB-1 đã commit trước write ở DB-2, process chết giữa hai bước vẫn có thể làm mất công việc. Nếu write DB-2 commit nhưng remove rollback, retry có thể duplicate nếu không idempotent.

**Muốn atomic receive/remove và business write**, phải xác minh store/handler tham gia cùng transaction manager/resource hoặc dùng recovery/outbox phù hợp. Hai databases khác nhau không mặc nhiên nằm trong một JDBC transaction.

Persistent store giúp durability của buffer, **không thay thiết kế commit boundary cho toàn workflow**.

## 22. ExecutorChannel: `send()` có thể chỉ là enqueue vào bộ nhớ

~~~text
Producer
  → DirectChannel
  → Bridge
  → ExecutorChannel
  → worker executes handler later
~~~

Nếu `ExecutorChannel` nhận task, `send()` ở upstream có thể hoàn tất **trước khi handler chạy**. Crash JVM giữa enqueue và execution có thể làm biến mất task in-memory.

~~~mermaid
sequenceDiagram
    participant U as Upstream
    participant B as Bridge
    participant E as ExecutorChannel
    participant W as Worker
    U->>B: send(EV-501)
    B->>E: enqueue(EV-501)
    E-->>B: accepted to executor
    B-->>U: send returns
    Note over E,W: Process crashes before worker runs
~~~

**Không dùng `send() == true` làm bằng chứng downstream handler đã commit.** Nếu source broker ACK lúc này, message có thể mất khi worker chưa có durable ownership.

## 23. Test async handoff bằng latch thay vì sleep ngẫu nhiên

Một kế hoạch test:

1. Tạo `ExecutorChannel` với test executor có thể giữ task chưa chạy.
2. Gửi message qua Bridge.
3. Xác nhận upstream `send()` đã trả/được tiếp nhận.
4. Trước khi thả latch, assert business handler chưa chạy.
5. Thả latch rồi chờ handler chạy và commit.
6. Mô phỏng shutdown trước bước 5 ở test khác, kiểm tra có durable handoff hay không.

~~~text
send accepted != business completed
~~~

Trong in-memory ExecutorChannel không có durable queue, test crash có thể chứng minh **thiết kế không đáp ứng no-loss**, không phải bản thân Bridge bị lỗi.

## 24. Bridge không mặc định là persistent work queue

| Trường hợp | Dùng Bridge có hợp lý? | Để không mất work cần thêm |
|---|---|---|
| Chuyển DirectChannel sang DirectChannel trong request đồng bộ | Có | Propagate failure để caller retry |
| Đệm nhẹ trong JVM | Có | Chấp nhận loss hoặc thay bằng durable store |
| Broker source durable, ACK sau commit | Có | Offset/ACK boundary và idempotency |
| Async task dài hàng phút | Bridge chỉ là một hop | Durable work queue + status/retry |
| Chuyển hai external brokers | Có thể + adapters | Publish confirms, source ACK, dedupe |
| Payment/Inventory mutation | Bridge không giải quyết side effect | Stable command ID, remote idempotency, reconcile |

**Bridge không tự triển khai ACK protocol Kafka, AMQP hoặc HTTP.** Trách nhiệm thuộc adapters, containers, outbox/inbox và domain services.

## 25. Kafka inbound adapter → Bridge: offset commit là quyết định quan trọng

Một flow:

~~~text
Kafka orders.events
  → Kafka inbound adapter
  → bridge.input
  → Bridge
  → business.handler
  → Database
~~~

Giả sử handler cần ghi một projection. Có hai cửa sổ lỗi:

~~~text
Case A: source offset committed BEFORE DB commit
  Kafka record EV-501 delivered
  offset committed
  DB unavailable, handler fails
  → source cursor advanced; risk of lost business work

Case B: DB commits BEFORE source offset commit
  Kafka record EV-501 delivered
  DB commits event + projection
  process crashes before offset commit
  → record may redeliver; business idempotency required
~~~

**Một hướng thiết kế thường an toàn hơn với at-least-once:** durable business commit trước khi xác nhận source progress, kết hợp idempotent consumer. Tuy nhiên, các chế độ Kafka ACK, consumer transactions, containers và async worker boundaries cần kiểm chứng theo đúng cấu hình.

Kafka offset **không** phải business event ID bền qua republish/repartition. Đặt `eventId` hoặc logical operation ID trong payload/wire contract; ghi `topic + partition + offset` như metadata hỗ trợ audit/replay.

## 26. Test Kafka: crash trước và sau commit

Thiết kế hai bài test có broker test riêng:

| Thời điểm lỗi | Kỳ vọng sau restart | Chứng cứ |
|---|---|---|
| Trước DB commit, offset chưa commit | Event được xử lý lại | Business effect count cuối = 1 |
| Sau DB commit, offset chưa commit | Có thể redelivery | Inbox đánh dấu duplicate, không ghi lần hai |
| Sau source ACK và trước durable handoff | **Phải phát hiện cửa sổ mất** nếu topology có | Message không ở DB/queue/retry store |
| Sau durable handoff, trước ACK nguồn | Có thể nhận duplicate | Duplicate được phát hiện bằng business ID |

Thực hiện:

1. Dùng Kafka test broker với topic/consumer group riêng.
2. Gửi một eventId cố định.
3. Dùng fault-injection hook ở **trước/sau DB commit**, không chỉ cho mock method return.
4. Dừng consumer process/container ở điểm được kiểm soát.
5. Khởi động lại cùng logical group.
6. So `eventId` trong database, inbox và source progress.
7. Assert **không mất trách nhiệm xử lý** và **không double business effect**.

Test này phải có một `OrderEventHandler` với transaction/idempotency thật hoặc một fake durable store có đặc tính được mô tả rõ. Một `QueueChannel` test-only in-memory không thể chứng minh broker recovery semantics.

## 27. AMQP/JMS inbound → Bridge: khác offset nhưng cùng bài toán ACK

RabbitMQ/JMS có các cách acknowledge/redeliver khác Kafka:

~~~text
Broker delivery
  → inbound channel adapter
  → Bridge
  → Service Activator
  → durable business store
  → broker ACK according to container policy
~~~

Nếu consumer ACK trước khi worker async lưu business state, crash có thể làm mất việc. Nếu business commit rồi connection mất trước ACK, delivery có thể quay lại.

Kịch bản test:

- Chưa ACK mà worker crash → source broker có thể redeliver theo transport semantics.
- Business đã commit nhưng ACK fail → idempotency chặn hiệu ứng trùng.
- Handler ném permanent error → đi vào DLQ/quarantine sau khi recovery đã durable.
- DLQ publish fail → không âm thầm ACK/drop source.
- Message content/headers được map đúng qua inbound adapter, không dùng raw untrusted header làm authorization.

**Không copy nguyên Kafka offset model sang RabbitMQ/JMS.** Queue delivery ACK, prefetch, requeue, dead-lettering và provider transactions khác group offsets; test đúng adapter/container đang chạy.

## 28. Bridge giữa hai external brokers: cần transport adapters ở hai phía

Sơ đồ:

~~~mermaid
flowchart LR
    KA["Kafka topic A"] --> IA["Kafka inbound adapter"]
    IA --> IN["Input channel"]
    IN --> B["Bridge"]
    B --> OUT["Output channel"]
    OUT --> OA["AMQP outbound adapter"]
    OA --> RB["RabbitMQ queue B"]
~~~

Trong topology này, `Bridge` chỉ nối Spring channels. Việc **nhận Kafka record** và **publish AMQP message** do hai adapters thực hiện.

Cửa sổ lỗi:

~~~text
1. Kafka record read.
2. Bridge forwards to outbound adapter.
3. RabbitMQ stores message and confirms publish.
4. Process crashes before Kafka offset commit.
5. Kafka event redelivered; RabbitMQ message may publish twice.
~~~

Nếu đảo lại và commit Kafka trước khi RabbitMQ durable confirm, crash có thể làm **mất message tại đích**. Không có local transaction chung mặc định giữa hai brokers.

**Thiết kế thường thực tế:** at-least-once transport handoff + dedupe ở đích, hoặc persistent outbox/staging store để điều phối và phục hồi. “Message Bridge” không tự thực hiện atomic commit xuyên hai message brokers.

## 29. Kiểm thử outbound publisher confirms và source progress

Khi Bridge gửi tới một outbound broker adapter:

1. Inject lỗi **trước khi publisher gửi**.
2. Inject lỗi **sau khi outbound broker lưu**, trước confirmation.
3. Inject lỗi **sau khi confirmation**, trước source ACK.
4. Đo số distinct business IDs tại destination.
5. Xác minh source message **không bị xác nhận mất** nếu chưa có durable handoff.
6. Xác minh duplicated deliveries được nhận diện và không tạo duplicate business side effects.

Một publish API trả `Future` hoặc callback success có thể cho biết delivery tới broker theo producer configuration; nó **không chứng minh consumer đích đã hoàn tất nghiệp vụ**.

**Định nghĩa “đã bàn giao bền vững” theo đúng transport.** Ví dụ RabbitMQ publisher confirm và Kafka producer acknowledgement có mức bảo đảm do broker/producer config quyết định; khi cần strict guarantees phải kiểm tra cả durability/replication/availability settings.

## 30. Transactional Outbox: giữ message khi không có atomic cross-system commit

Một pattern:

~~~text
BEGIN local DB transaction
  update order state
  insert outbox event EV-501
COMMIT

Outbox publisher
  → Bridge / outbound adapter
  → external broker
  → mark outbox delivered after acceptable confirmation
~~~

Nếu publisher crash trước mark-sent, event có thể được gửi lại. **Outbox ưu tiên không mất việc**, nhưng vẫn cần consumer idempotency do duplicate delivery có thể xảy ra.

Điểm cần test:

- Outbox record tồn tại nếu business transaction đã commit.
- Business rollback → không có outbox event “thành công” riêng biệt.
- Outbound broker down → outbox giữ pending, không drop.
- Publish confirmed rồi crash → replay có thể duplicate, receiver dedupe.
- Đổi schema/redeploy → pending outbox vẫn decode và được gửi đúng.

Nếu Bridge chỉ nối một `QueueChannel` in-memory với outbound adapter, nó **không thay thế transactional outbox**.

## 31. Inbox/idempotency: chặn side effect trùng sau replay

Một business message:

~~~java
record OrderEvent(
    String tenantId,
    String eventId,
    String orderId,
    int aggregateVersion,
    String type
) {}
~~~

Một thiết kế inbox:

~~~sql
CREATE TABLE processed_order_event (
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
~~~

Trong một transaction local:

1. Validate/authorize event và tenant từ context đáng tin.
2. Claim event ID với unique constraint.
3. Nếu duplicate, so fingerprint của payload với bản đã commit.
4. Nếu đã completed và fingerprint khớp, return mà **không tạo business effect nữa**.
5. Nếu first processing, kiểm tra aggregate version/state transition rồi ghi business effect.
6. Commit inbox marker và business writes **cùng transaction/resource** khi có thể.

Không tạo inbox marker ở một cache không atomic với DB rồi coi đó là proof business commit. Nếu Bridge nối hai khác data stores, transaction manager/resource boundaries phải được chứng minh chứ không suy đoán.

## 32. Unit test idempotency khác integration test Bridge

Một unit test pure handler:

~~~java
@Test
void duplicateEventDoesNotInvokeWriteTwice() {
    OrderEvent event = new OrderEvent(
        "tenant-a", "EV-501", "O-501", 1, "CREATED");

    handler.applyIdempotently(event);
    handler.applyIdempotently(event);

    assertEquals(
        1, orderRepository.countByEventId("EV-501"));
}
~~~

Ở đây `handler`/`orderRepository` là test fixtures có implementation/transaction cần được dự án cung cấp. Test đúng hơn với database thật và unique constraint để xác nhận concurrency/restart.

**Test này chưa chứng minh Bridge không drop message**; nó chỉ bảo vệ downstream khỏi hiệu ứng trùng. Cần kết hợp **forwarding ID test**, **ACK/durable recovery test** và **business idempotency test**.

## 33. Error channel: ghi lỗi khác với lưu message để retry

Trong một flow asynchronous:

~~~text
Poller / executor
  → Bridge
  → handler throws
  → ErrorMessage(Throwable)
  → errorChannel
~~~

Một `ErrorMessage` có thể chứa `MessagingException` và failedMessage khi có, nhưng thông tin này có thể vắng hoặc được wrapper khác nhau theo vị trí lỗi.

**Chỉ thấy error message không có nghĩa source work còn recoverable.** Nếu poller đã lấy EV-501 khỏi in-memory queue, error handler log rồi return, event không mặc nhiên quay lại.

Test recovery phải assert một trong các outcomes:

- Message vẫn có thể **được xử lý lại từ source durable**.
- Message đã tồn tại trong **durable retry queue**.
- Message đã được ghi vào **DLQ/quarantine có owner**.
- Business operation đã hoàn tất bền vững.

Khi không có outcomes nào, test cần báo **lost responsibility**, ngay cả khi log chứa stack trace rất đầy đủ.

## 34. Đồng bộ và bất đồng bộ: error path không giống nhau

| Nguồn lỗi | Thường xảy ra ở | Cần kiểm tra |
|---|---|---|
| DirectChannel handler throw | Caller thread | Exception propagation và caller retry |
| QueueChannel poller handler throw | Poller thread | Error handler, transaction/poll recovery |
| ExecutorChannel handler throw | Worker thread | ErrorMessage/recoverer, durable handoff |
| Kafka deserializer fail | Trước Spring Message | Container error handler/DLT |
| AMQP broker connection down | Adapter/container | Reconnect/ACK policy |
| Outbound publish timeout | Outbound handler/transport | Unknown publish outcome, confirm/retry |

Đừng khẳng định mọi lỗi đi vào global `errorChannel`. Spring Integration error flow phụ thuộc loại channel, poller, adapter và cấu hình; lỗi deserialize có thể xảy ra **trước** khi Bridge được gọi.

Nếu error handler nuốt exception và ACK source, phải bảo đảm đã có durable terminal/retry outcome; không đơn thuần dùng `catch(Exception) { log(); }`.

## 35. Retry có thể gây trùng message: phải dùng logical ID

Một message có thể được thử lại nhiều lần:

~~~text
Original: eventId=EV-501; attempt=1
Retry:    eventId=EV-501; attempt=2
Retry:    eventId=EV-501; attempt=3
~~~

Tách:

| ID | Mục đích |
|---|---|
| `eventId` | Logical event identity để dedupe |
| `attemptId` | ID của lần thử/recovery |
| `businessCorrelationId` | Nhóm workflow/Splitter/Aggregator |
| `MessageHeaders.ID` | Spring message instance identity |
| Broker offset/delivery tag | Transport source position/ACK |
| `replyChannel` | Return address của request–reply nếu có |

Bridge chỉ forward message theo cấu hình; nó không sinh một **business event ID ổn định** cho producer. Nếu một retry tạo `eventId` mới, downstream có thể coi như event khác và gây duplicate business side effect.

**No-loss + no-duplicate effect không nhất thiết nghĩa mỗi handler chỉ được invoke một lần.** At-least-once delivery thường chấp nhận duplicate invocation nhưng idempotent commit.

## 36. Test một error retry rồi xử lý thành công

Một scenario có chủ đích:

~~~text
EV-501 first attempt
  → Bridge
  → handler throws transient DB error
  → message remains recoverable
  → retry same eventId
  → handler commits once
  → source progress acknowledged
~~~

Assertions:

- Message **không** bị đánh dấu completed ở lần handler throw.
- Có recovery record hoặc source retry hợp lệ.
- `eventId`/fingerprint không đổi giữa attempts.
- Sau retry, database có một committed event effect.
- Không để lại DLQ entry sai là terminal nếu retry đã hoàn tất.
- Có log/metric attempt=2 nhưng business completed count chỉ tăng một.

**Thực hiện fault injection ở đúng transaction boundary.** Nếu test luôn giả lập exception **trước** khi service bắt đầu ghi, nó không thử được cửa sổ sau business commit/trước source ACK.

## 37. Test permanent failure: no-loss không nghĩa retry vô hạn

Message malformed:

~~~text
EV-502 with unsupported schemaVersion
  → validation fails permanently
  → durable quarantine/DLQ
  → source progress advances according to recovery policy
~~~

Một failure có thể được coi là **terminal rejected** sau khi record được lưu an toàn cùng metadata đủ để điều tra/replay. No-loss ở đây không phải bắt handler chạy mãi mà là **không xóa mất bằng chứng/lệnh chưa xử lý**.

Test:

1. Gửi một message malformed.
2. Assert business handler không tạo side effect.
3. Assert recovery record chứa logical ID, source reference và reason code đã sanitize.
4. Confirm DLQ publish/store thành công **trước** ACK source theo policy.
5. Giả lập DLQ unavailable và xác minh source không âm thầm drop.
6. Thử replay sau khi sửa decoder, giữ business idempotency.

Đừng để quarantine lưu raw bearer tokens, secrets hoặc PII vượt nhu cầu; retryability còn phụ thuộc retention, access control và schema evolution.

## 38. Bridge trong request–reply: đừng làm mất return address

Một Gateway có thể đưa request vào flow chứa Bridge:

~~~text
Java @MessagingGateway
  → request channel
  → Bridge
  → Service Activator
  → reply message
  → Gateway return address
~~~

Bridge không tự là một request–reply gateway. Nó **chuyển tiếp** message để Service Activator phía sau có thể trả result theo return address mà Gateway thiết lập.

Test cần:

- Request payload/header quan trọng đến đúng handler.
- Reply cuối về **đúng caller**.
- Hai concurrent requests có replies đảo thứ tự **không bị lẫn**.
- Filter/drop hoặc `void` handler trong đường đòi reply được phát hiện, không chờ timeout không rõ nguyên nhân.
- Nếu qua broker/process khác, `replyChannel` JVM object không tự portable; cần protocol reply-to/correlation mapper.

**Business correlation ID của Aggregator khác reply address của Gateway.** Không dùng một ID để thay thế cả hai nếu contract không định nghĩa như vậy.

## 39. Test hai requests đồng thời: không được lẫn reply

Một Bridge nằm giữa nhiều callers cùng channel:

~~~text
Request A (eventId=EV-A, correlation=Q-A)
Request B (eventId=EV-B, correlation=Q-B)
  → shared DirectChannel
  → Bridge
  → downstream handler
~~~

Trong test:

1. Tạo hai requests có payload, business ID và correlation riêng.
2. Dùng barrier để hai threads gửi gần đồng thời.
3. Cho downstream hoàn tất request B trước A.
4. Assert mỗi result đi đúng caller/request.
5. Không xem shared `QueueChannel.receive()` không có correlation là reply manager an toàn.
6. Kiểm tra eventId/business entity ở đích, không chỉ count=2.

Bridge **không tự tạo request correlation**; khi cần request–reply qua `@MessagingGateway`, chính Gateway/protocol và flow phải giữ reply path đúng.

## 40. Test nhiều producers đồng thời và tính toàn vẹn tập ID

Trong load test, nhiều producers gửi IDs độc lập:

~~~text
Producer-1: EV-0 ... EV-99
Producer-2: EV-100 ... EV-199
Producer-3: EV-200 ... EV-299
Producer-4: EV-300 ... EV-399
~~~

Test harness có thể dùng `ExecutorService` và `CountDownLatch` để phát đồng thời rồi tập hợp kết quả:

~~~java
int producers = 4;
int messagesPerProducer = 100;
int expectedTotal = producers * messagesPerProducer;

Set<String> completedIds =
    ConcurrentHashMap.newKeySet();
CountDownLatch completed = new CountDownLatch(expectedTotal);

// Trong capture handler ở output:
// completedIds.add(eventId);
// completed.countDown();

assertTrue(completed.await(10, TimeUnit.SECONDS));
assertEquals(expectedTotal, completedIds.size());
~~~

**Đoạn trên là assertion/capture pattern**, chưa có setup producers, context và eventId extraction. Chỉ dùng Set không bắt được duplicate sau khi có đủ unique IDs: cần ghi thêm `Map<eventId, AtomicInteger>` và assert mỗi count = 1 trong happy path.

Không khẳng định Bridge giữ global ordering giữa bốn producers; test concurrency tập trung vào **không thiếu IDs**, ordering có scope theo producer/key và tại committed handler.

## 41. Test thứ tự theo business key, không yêu cầu global order

Hai orders:

~~~text
O-501: CREATED(v1) → PAID(v2) → CANCELLED(v3)
O-502: CREATED(v1) → PAID(v2)
~~~

Nếu Bridge nối tới `ExecutorChannel` hoặc broker có partitions:

- Thứ tự O-501 và O-502 **không cần global** nếu độc lập.
- Thứ tự các state transitions **trong O-501** có thể cần bảo đảm.
- Nếu các events cùng order dispatch song song, handler dùng version guard hoặc serial execution lane.
- Redelivery có thể đến sau version mới và không được ghi đè stale state.

Một no-loss test có thể PASS (đủ IDs) nhưng business state sai vì version 3 xử lý trước version 2. Ngoài set equality, cần assert **domain ordering/state invariants** khi có.

## 42. Test Bridge kết hợp Splitter/Aggregator

~~~text
Order O-501
  → Splitter
      → Child A: stock
      → Child B: price
      → Child C: fraud
  → Bridge trên mỗi nhánh
  → Aggregator
  → OrderDecision
~~~

“Không mất message” cần đếm **đúng đơn vị**:

- Một parent có thể sinh ba children, vì vậy `outputCount != inputCount` là bình thường.
- Child có parentCorrelationId và distinct memberId.
- Expected member manifest là A/B/C (hoặc sequence contract).
- Duplicate child A không được tính thay child C còn thiếu.
- Child B lỗi phải có failure outcome/policy rõ, không drop rồi group chờ mãi.
- Group release/expiry không tạo hoàn tất thứ hai từ late reply.

So:

~~~text
expectedChildren(parent=O-501) = {A,B,C}
observedTerminalOutcomes(parent=O-501) = {A,B,C}
~~~

và mỗi member có success/failure/terminal state; khi còn pending thì không báo whole-group success.

## 43. Test Filter trước/sau Bridge không discard ngoài ý định

Một flow:

~~~text
Source → Filter → Bridge → Handler
~~~

Tập test:

- Event hợp lệ qua Filter → Bridge forward.
- Event reject **có chủ đích** → trạng thái skipped/rejected theo contract.
- Infrastructure error trong Filter predicate **không** bị convert thành `false`.
- Với Gateway cần reply, Filter discard tạo typed rejection/error path, không timeout vô nghĩa.
- Nếu Filter ở sau Bridge, counter phải phân biệt **forwarded** và **handler accepted**.

**Không gắn “Bridge làm mất message” cho một event Filter được phép discard**, nhưng cũng không tính nó là business completed khi chưa có terminal decision.

## 44. Test header mapping qua Bridge và transport

Trong JVM:

~~~text
Message<OrderEvent>
  headers:
    eventId=EV-501
    businessCorrelationId=tenant-a|O-501
    schemaVersion=1
    traceId=trace-501
~~~

Qua external transport, adapter có thể serialize headers có chọn lọc hoặc xây lại message:

1. Assert eventId và business correlation tồn tại trong wire schema/headers đáng tin.
2. Không dựa vào `MessageHeaders.ID` là stable business identity.
3. Không truyền nguyên `replyChannel` JVM object qua Kafka/HTTP.
4. Whitelist headers, không forward bearer token/untrusted channel names.
5. Header required thiếu → rejection/recovery có chủ đích.
6. Schema version khác nhau → Transformer/parser xử lý hoặc quarantine.

**Bridge có thể chuyển tiếp headers trong JVM nhưng không tự quyết định transport serialization policy** của inbound/outbound adapters.

## 45. Backpressure: gửi được nhưng queue đang ngập

Nếu producer nhanh hơn consumer:

~~~text
Inbound rate  = 1,000 messages/s
Handler rate  =   350 messages/s
Queue growth  =   650 messages/s
~~~

Đây là **ước lượng khi rates ổn định**, không phải số đo production. Một QueueChannel tăng không giới hạn có thể làm JVM hết RAM, mất toàn bộ pending in-memory messages.

Biện pháp:

- Bounded queue/capacity và send timeout rõ.
- Giảm tốc producer hoặc pause source consumption theo adapter.
- Giới hạn executor threads và in-flight messages.
- Persistent store/broker nếu cần qua restart.
- Metrics queue depth, enqueue age, end-to-end pending latency.
- Overflow/rejection policy **không drop silently**.

**Tăng queue capacity không tự làm handler nhanh hơn.** Test cần kiểm tra caller nhận được backpressure/error khi capacity đầy.

## 46. Test output queue đầy hoặc handler bị chặn

Bounded queue trong test:

~~~java
@Bean("bridge.bounded.output")
PollableChannel boundedOutput() {
    return new QueueChannel(1);
}
~~~

Kịch bản:

1. Gửi EV-1, giữ trong queue.
2. Gửi EV-2 với send timeout/rejection policy tương ứng.
3. Xác minh producer **không nhận success giả** khi chưa đưa được EV-2 vào queue.
4. Lấy EV-1 ra, cho EV-2 retry với cùng business ID.
5. Xác minh một logical ID chỉ xuất hiện đúng một lần trong normal path.
6. Test restart riêng nếu nguồn cần durability.

**QueueChannel capacity không phải durable delivery mechanism.** Khi send timeout, caller cần nhận biết failure/unknown theo topology để xử lý lại có kiểm soát.

## 47. Graceful shutdown: drain hay bàn giao bền vững?

~~~text
T0 application begins stopping
T1 inbound adapters stop accepting new messages
T2 in-flight Bridge/poller tasks remain
T3 downstream handlers commit or durable-handoff
T4 source ACKs/offsets finalized when safe
T5 workers stop
~~~

Nếu process dừng khi in-memory queue/executor còn pending, messages có thể mất. Graceful shutdown giúp giảm nguy cơ nhưng **không bảo vệ hard crash/power loss**.

Test:

- Stop source adapter trước khi drain work theo topology.
- Chờ bounded deadline cho in-flight tasks.
- Kiểm tra queue depth/durable pending state.
- Không ACK source trước durable completion/handoff.
- Nếu hết deadline, để nguồn uncommitted hoặc ghi durable recovery.
- Restart và xác minh các IDs chưa hoàn tất được xử lý lại.

**Shutdown hook không thay durable queue hoặc source redelivery semantics.**

## 48. Restart test: memory queue so với persistent queue

| Topology | Thử nghiệm | Kết luận kỳ vọng |
|---|---|---|
| `QueueChannel` in-memory | Enqueue, kill process, restart | Pending có thể mất |
| Persistent `MessageGroupStore` backed queue | Enqueue, durable commit, kill/restart | Item còn recoverable nếu store/receive protocol đúng |
| Kafka/AMQP durable source | Nhận, chưa ACK, kill/restart | Có thể redelivery theo transport |
| Outbox store | Business+outbox commit, stop publisher, restart | Pending event được publish/retry |

**Không mô phỏng restart chỉ bằng khởi tạo lại bean trong cùng JVM mà không reopen store.** Kiểm thử durability cần external test process/container hoặc state được xác minh sau restart thật.

Một message quay lại không tự là lỗi: nếu business commit nhưng ACK chưa có, **redelivery có thể hợp lệ**, cần dedupe để không double effect.

## 49. Test trạng thái từng message thay vì một counter tổng

Một test end-to-end nên ghi cho từng ID:

~~~text
EV-501 → COMPLETED
EV-502 → DURABLE_PENDING
EV-503 → TERMINAL_QUARANTINED
EV-504 → COMPLETED
~~~

Với mỗi logical ID được accepted, phải tồn tại **một trạng thái bền vững đủ để tiếp tục hoặc kết thúc có nghĩa**. Tránh đếm duplicate attempts như logical IDs mới.

Một cấu trúc test fixture:

~~~java
enum ProcessingState {
    COMPLETED,
    DURABLE_PENDING,
    TERMINAL_QUARANTINED
}

record MessageAudit(
    String eventId,
    ProcessingState state
) {}
~~~

Những types này là **thiết kế cho test**, không phải Spring Integration API tự sinh. Khi cần phân biệt unknown external outcome, nên có state `PENDING_RECONCILIATION` được lưu durable và được tính trong loại pending, không gán success/failure tùy ý.

Test assertion:

~~~java
Set<String> acceptedIds = new HashSet<>(sourceAcceptedIds);
Map<String, ProcessingState> finalStates =
    durableAuditStore.loadStates();

assertEquals(acceptedIds, finalStates.keySet());
assertTrue(finalStates.values().stream()
    .allMatch(Objects::nonNull));
~~~

**Điều kiện:** `sourceAcceptedIds` phải đến từ một nguồn có tính durable/đã xác minh, không chỉ là một `AtomicInteger` bị mất khi JVM crash. `durableAuditStore` là fixture/implementation của ứng dụng, cần mã hóa transitions để một ID không vừa COMPLETED vừa PENDING.

## 50. Ma trận kiểm thử Bridge không mất message

| Test case | Topology/fault | Điều cần xác minh |
|---|---|---|
| One message happy path | Direct → Bridge → Queue | Payload + business headers đúng |
| Many messages happy path | 200 IDs | Tập IDs đủ, không duplicate trong window |
| Sequential order | Direct → Bridge → Queue | Thứ tự trong test topology |
| Wrong payload type | Invalid schema/type | Reject có nghĩa, không silently drop |
| Missing required header | eventId null | Validation/recovery theo contract |
| No downstream subscriber | Direct output | Error tới caller/recoverer |
| Downstream exception | Handler throws | Không ACK sai; recoverable |
| Poller async | Queue → poller → Bridge | Latch/capture ở target, không tự consume source |
| Poller crash | Sau dequeue, trước handler | Durable rollback/recovery hoặc phát hiện loss |
| In-memory queue restart | Kill process | Không tuyên bố durability |
| Persistent queue restart | Reopen message store | Pending survives nếu protocol đúng |
| Executor handoff | Enqueue rồi crash | Phát hiện loss window nếu thiếu durability |
| Output capacity full | Bounded QueueChannel | Send failure/backpressure rõ |
| Kafka offset after DB commit | Crash trước ACK | Redelivery không double effect |
| Kafka offset before DB commit | Crash | Test phát hiện incorrect ACK |
| AMQP requeue | Consumer crash | Redelivery theo adapter |
| Outbound broker confirm missing | Publish uncertain | Retry/reconcile và destination dedupe |
| Two brokers handoff | Publish rồi crash trước source ACK | Duplicate có thể xảy ra nhưng không double business effect |
| Transient failure | Retry bounded | Một committed effect |
| Permanent failure | Invalid schema | Durable quarantine/DLQ |
| DLQ unavailable | Recovery cannot persist | Không drop nguồn im lặng |
| Multiple producers | Concurrent IDs | Không thiếu logical IDs |
| Reordering | Executor pool | State machine/version guard |
| Gateway through Bridge | Two concurrent requests | Reply đúng caller |
| Splitter children | A,B,C + duplicate B | Không release sai group |
| Header mapping | Broker boundary | Business IDs/tenant scope giữ đúng |
| Graceful shutdown | Drain in-flight | Chưa durable thì không ACK |
| Hard crash/restart | Store/broker durable | Pending được replay |
| Authorization failure | Untrusted tenant header | Không ghi business effect |
| Backpressure overload | Producer rate vượt handler | Không coi enqueue/drop là completed |

**Kết luận được phép rút ra phải bằng phạm vi test.** Một test với QueueChannel in-memory có thể xác minh forwarding, nhưng không thể thay test crash/ACK với broker và durable store.

## 51. Observability: số message qua Bridge không đồng nghĩa số hoàn tất

Các metric dưới đây là **đề xuất**, không phải toàn bộ meter mặc định Spring Integration:

| Metric | Diễn giải |
|---|---|
| `bridge.input.accepted.count` | Số logical messages upstream đã accepted theo contract |
| `bridge.forward.attempt.count` | Số attempts forward (có thể gồm retry) |
| `bridge.forward.success.count` | Forward tới next channel đã hoàn tất theo channel semantics |
| `bridge.forward.failure.count` | Không forward thành công |
| `bridge.downstream.completed.count` | Business completion bền vững |
| `bridge.downstream.duplicate.count` | Business duplicate được chặn |
| `bridge.durable.pending.count` | Events còn owner/recovery bền vững |
| `bridge.terminal.quarantined.count` | Events reject terminal có record |
| `bridge.queue.depth` | Queue backlog |
| `bridge.queue.oldest.age` | Tuổi pending message lâu nhất |
| `bridge.handoff.latency` | Thời gian từ accepted tới durable handoff |
| `bridge.end_to_end.latency` | Thời gian từ accepted tới terminal outcome |
| `bridge.retry.attempt.count` | Retry amplification |
| `bridge.error.unhandled.count` | Lỗi không có durable recovery |
| `bridge.source.ack.failure.count` | ACK/commit source lỗi |
| `bridge.outbound.confirm.failure.count` | Handoff external chưa confirm |

**Một Bridge forward 10.000 messages không chứng minh 10.000 business operations đã commit.** Nếu output là ExecutorChannel, handler có thể còn pending; nếu downstream Filter intentionally skips một loại event, completed count có thể thấp hợp lệ.

Metric labels nên thuộc tập cardinality thấp như `flowName`, `channelType`, `operation`, `outcome` và `reasonCode`. **Không dùng eventId, commandId, orderId, email, raw payload hoặc traceId làm labels**. Các IDs có thể xuất hiện trong structured logs/traces có phân quyền/retention đúng.

## 52. Structured logging cho một bridge hop

Forwarded:

~~~text
eventId=EV-501
sourceChannel=orders.bridge.input
bridgeEndpoint=orders-bridge
targetChannel=orders.bridge.output
forwardAttempt=1
forwardResult=CHANNEL_ACCEPTED
durableBusinessOutcome=PENDING
~~~

Downstream commit:

~~~text
eventId=EV-501
handler=OrderEventHandler.apply
transactionOutcome=COMMITTED
businessOutcome=SUCCEEDED
idempotencyOutcome=FIRST_COMMIT
~~~

Redelivery:

~~~text
eventId=EV-501
sourceDeliveryAttempt=2
idempotencyOutcome=DUPLICATE_COMPLETED
businessSideEffectCount=0
~~~

Đừng log `businessOutcome=SUCCEEDED` ở Bridge chỉ vì output channel nhận message. **CHANNEL_ACCEPTED** và **BUSINESS_COMMITTED** là hai mốc khác nhau.

Khi error xảy ra, log logical ID, source position, reasonCode, retry count, recovery destination và deadline theo quyền truy cập; không ghi raw credentials hoặc secrets từ headers.

## 53. Runbook: “Bridge làm mất message” cần kiểm tra gì?

Khi báo động “đã send 100 events nhưng DB chỉ có 97”:

1. **Xác định 100 IDs** từ nguồn durable; không dựa vào counter volatile.
2. **Tìm ba IDs còn thiếu** và trạng thái source ACK/offset.
3. **Kiểm tra Bridge input:** messages có thực vào input channel không?
4. **Kiểm tra Bridge output:** có forward failure/timeout/capacity rejection?
5. **Xem downstream channel type:** Direct, Queue memory/persistent, Executor hay adapter?
6. **Xem poller:** nguồn PollableChannel có bị `receive()` bởi worker/test khác?
7. **Xem error path:** exception có bị catch rồi log/ACK mà không durable retry?
8. **Xem source progress:** broker ACK/offset đã commit trước business/durable handoff?
9. **Xem in-memory backlog:** queue/executor còn pending khi process restart?
10. **Xem downstream DB:** commit, rollback, deadlock, unique constraint, version guard?
11. **Xem idempotency:** ba IDs có bị nhận là duplicate vì key quá thô?
12. **Xem Filter/Router:** có intentionally discard/route tới channel khác?
13. **Xem Splitter/Aggregator:** có child thiếu hoặc duplicate được đếm nhầm?
14. **Xem outbound transport:** broker publish confirm/reply timeout có kết quả chưa biết?
15. **Xem DLQ/retry store:** messages đã vào quarantine có durable và accessible không?
16. **Reconcile:** phân loại từng ID thành COMPLETED, DURABLE_PENDING hoặc TERMINAL_QUARANTINED.
17. **Khắc phục:** sửa ACK/handoff boundary, thêm idempotency/retry/outbox và test tái hiện crash window.

Nếu phát hiện source ACK sai trước durable handoff, không thể chỉ “thêm log” là khắc phục. Cần **đổi protocol bàn giao** để message có owner sau mỗi transition, và xác định cách phục hồi những IDs đã mất trách nhiệm.

## 54. Những hiểu lầm thường gặp

**“`.bridge()` bảo đảm message không mất.”** Không. Bridge chỉ forward theo channel semantics.

**“Một `send() == true` chứng minh handler đã commit.”** Không khi downstream async hoặc chỉ accepted vào queue.

**“QueueChannel là hàng đợi durable.”** Không khi chỉ in-memory; persistent store còn cần transaction/recovery.

**“Poller lấy được message thì message đã xử lý xong.”** Không. Receive/remove và business commit là hai bước.

**“DirectChannel luôn an toàn vì chạy đồng bộ.”** Không. Caller có thể nuốt exception hoặc crash trước persist.

**“ExecutorChannel tự giữ tasks khi restart.”** Không mặc định.

**“ErrorMessage trong global errorChannel nghĩa message sẽ được retry.”** Không. Cần durable recovery policy.

**“DLQ thành công chỉ cần log nội dung message.”** Không. Cần durable destination, ownership và replay policy.

**“Thêm Bridge giữa hai brokers tạo atomic transaction.”** Không. Inbound/outbound adapters quản lý hai transport độc lập.

**“Kafka offset commit tương đương DB commit.”** Không, trừ protocol cụ thể đã được chứng minh, và external DB không tự thuộc Kafka transaction.

**“At-least-once delivery nghĩa handler luôn chạy đúng một lần.”** Không. Duplicate invocation có thể xảy ra; cần idempotency.

**“So tổng input và output count là đủ.”** Không. Mất một ID và duplicate một ID có thể triệt tiêu nhau về count.

**“So một Set IDs là đủ để phát hiện duplicate.”** Không nếu test không so multiplicity/attempt counts.

**“Một Spring Message UUID là business idempotency key tốt.”** Không khi rebuild/replay.

**“Bridge phải giữ nguyên mọi framework header và object reference qua brokers.”** Không. Adapter mapping/serialization có boundary riêng.

**“Flow có Filter thì output thấp hơn input luôn do Bridge làm mất.”** Không. Phải xét intentional rejections.

**“Một parent thành ba children mà outputCount=3 là duplicate.”** Không. Phải đếm theo manifest/membership.

**“Thêm executor threads bảo đảm không backlog.”** Không khi handler/DB là bottleneck, và có thể phá ordering.

**“Restart test trong cùng JVM đủ chứng minh durable queue.”** Không. Cần store/restart thực sự.

**“Bridge timeout nghĩa downstream chưa tạo side effect.”** Không. Remote/async effect có thể xảy ra trước khi caller nhận lỗi.

## 55. Bài thực hành: xây BridgeNoLossLab

Xây một dự án test với Spring Integration:

1. Tạo input `DirectChannel`, output `QueueChannel` và `IntegrationFlow.bridge()`.
2. Viết test một message có payload/headers `eventId` và correlation.
3. Viết test gửi 200 events, đối chiếu IDs và số lần xuất hiện.
4. Test gửi tuần tự và kiểm tra ordering trong topology đồng bộ.
5. Thay output bằng `DirectChannel` không có subscriber, assert failure propagation.
6. Thêm handler cố tình throw và xác minh source không ACK mất work.
7. Chuyển source thành `QueueChannel` với poller, test handler bằng latch.
8. Mô phỏng failure sau receive trước business commit và chứng minh cần recovery.
9. Test một in-memory queue restart: quan sát loss risk, không gọi đó là một test PASS về durability.
10. Dùng persistent store/queue hoặc broker test độc lập; test hard restart.
11. Nối Bridge tới `ExecutorChannel`, dừng worker trước execution và phân tích loss window.
12. Thêm transactional inbox/business repository với unique constraint.
13. Inject crash sau DB commit trước source ACK; assert redelivery không double effect.
14. Thêm outbox khi chuyển event sang một broker khác.
15. Test outbound broker confirm và crash trước khi mark source completed.
16. Tạo malformed message, xác minh durable quarantine.
17. Cho DLQ unavailable, assert không ACK/drop silently.
18. Gửi 400 IDs từ bốn producers, dùng concurrent-safe counts.
19. Thử output queue bounded=1 và kiểm tra backpressure.
20. Thêm Filter intentional skip và tách metric skipped khỏi lost.
21. Thử Splitter ba child members, duplicate một member, làm lỗi một member và kiểm tra Aggregator release policy.
22. Test two Gateway callers qua Bridge với replies đảo thứ tự.
23. Thử graceful shutdown và hard crash, đối chiếu trạng thái từng ID.
24. Đo queue depth, retry counts, forward failures và durable completion.
25. Viết runbook cho trường hợp 100 IDs đầu vào nhưng chỉ 97 completed.

**Tiêu chí hoàn thành:** chứng minh Bridge forward đúng trên đường bình thường, **không bỏ qua failure path**, không ACK source trước durable responsibility, phục hồi/replay sau restart và **không tạo duplicate business effects**. Cần nêu chính xác topology nào bảo đảm điều gì thay vì kết luận Bridge tự cung cấp exactly-once.

## 56. Ghi nhớ

**Bridge trong Spring Integration nối hai message channels**, giúp flow rõ ràng và tách nối các endpoints mà không cần biến đổi business payload. Kiểm thử Bridge không làm mất message gồm **hai lớp**: test forwarding (payload, headers, logical IDs, ordering trong phạm vi channel) và test delivery/recovery toàn hệ thống (ACK/transaction, durable handoff, retry, crash, idempotency, DLQ).

**DirectChannel đồng bộ không mặc nhiên durable; QueueChannel in-memory không tự tồn tại sau restart; ExecutorChannel có thể chỉ xác nhận enqueue vào RAM.** Với nguồn pollable, receive/remove trước commit tạo failure window; với broker source, ACK/offset trước durable completion có thể gây mất việc; với hai external brokers, send-confirm và source-ACK không mặc nhiên atomic.

Định nghĩa **logical message ID** ổn định, kiểm kê từng ID theo trạng thái completed/durable pending/terminal quarantined, kiểm thử crash trước/sau commit, và bảo vệ side effects bằng transaction/inbox/outbox/idempotency. **Một forward thành công chỉ là một hop thành công**, không phải bằng chứng business processing đã hoàn tất.

### Tài liệu tham khảo

- Enterprise Integration Patterns, **Messaging Bridge**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingBridge.html
- Spring Integration Reference, **Message Bridge**: https://docs.spring.io/spring-integration/reference/bridge.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference, **Poller**: https://docs.spring.io/spring-integration/reference/polling-consumer.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Message Stores**: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration Reference, **Kafka Support**: https://docs.spring.io/spring-integration/reference/kafka.html
- Spring Integration Reference, **AMQP Support**: https://docs.spring.io/spring-integration/reference/amqp.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Framework Reference, **Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
