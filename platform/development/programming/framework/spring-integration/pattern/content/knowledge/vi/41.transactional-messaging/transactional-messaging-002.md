# Message send trong transaction với Spring Integration

## 1. Vì sao thời điểm gửi thông điệp quan trọng?

Trong **Spring Integration**, hệ thống được ghép từ những **Enterprise Integration Patterns (EIP)**: Gateway tiếp nhận yêu cầu, Filter kiểm tra điều kiện, Transformer chuyển đổi payload, Router chọn nhánh, Splitter chia công việc, Aggregator gom kết quả. Mỗi bước có thể trao đổi qua `MessageChannel` và hoạt động đồng bộ hoặc bất đồng bộ.

Hãy xét trường hợp xử lý đơn hàng:

1. Ghi đơn hàng vào bảng `orders`.
2. Gửi message `OrderCreated` cho dịch vụ kho.
3. Commit transaction của cơ sở dữ liệu.

Nếu ở bước 2, broker hoặc worker nhận được `OrderCreated` **trước khi bước 3 commit**, kho có thể xử lý một đơn hàng mà transaction tạo đơn cuối cùng lại rollback. Ngược lại, nếu chỉ gửi **sau khi commit**, ứng dụng có thể sập giữa hai thao tác: đơn hàng đã tồn tại, nhưng sự kiện chưa bao giờ được gửi.

Đó là lý do cần phân biệt:

- **Message send**: một lời gọi đưa thông điệp vào một channel hoặc adapter cụ thể.
- **Database commit**: thời điểm các thay đổi của transaction trên database trở thành bền vững.
- **Delivery/acknowledgement**: thời điểm hệ thống nhận chấp nhận hoặc xác nhận đã xử lý message theo giao thức của nó.

Ba sự kiện này **không tự động là một thao tác nguyên tử**. Bài học tập trung vào *Message send trong transaction*: khi nào gửi, lệnh gửi tham gia transaction nào, rủi ro xảy ra khi rollback, và cách tổ chức flow để giảm mất mát hoặc gửi trùng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của `MessageChannel.send()` khi gọi bên trong phương thức `@Transactional`.
- Nhận diện ranh giới giao dịch khi message đi qua `DirectChannel`, `ExecutorChannel`, `QueueChannel`, message store hay outbound adapter.
- Chọn giữa gửi ngay trong transaction, gửi sau commit và **transactional outbox**.
- Xử lý đúng exception, retry, error channel, idempotency, correlation và acknowledgement.
- Viết kiểm thử chứng minh dữ liệu rollback trong flow đồng bộ và phát hiện các tình huống dual write.

## 2. `send()` thành công có nghĩa là gì?

Spring Integration trao đổi thông điệp bằng `Message<?>`, trong đó có `payload` và `headers`. `MessageChannel` có phương thức:

~~~java
boolean accepted = channel.send(message);
// Hoặc channel.send(message, timeoutInMillis) nếu channel hỗ trợ timeout.
~~~

Kết quả `true` có nghĩa channel đã **chấp nhận lời gửi theo hợp đồng triển khai của nó**; điều đó không phải một cam kết chung rằng mọi handler downstream đã hoàn tất, mọi dữ liệu đã commit hay consumer từ xa đã ACK.

Ví dụ:

| Channel hoặc adapter | Điều có thể xảy ra lúc gửi | Điều `send()` không tự bảo đảm |
| --- | --- | --- |
| `DirectChannel` | Dispatch handler đồng bộ trong thread của người gửi. | Database đã commit nếu transaction bên ngoài còn mở; tác dụng phụ ở hệ thống xa có thể không rollback. |
| `PublishSubscribeChannel` không dùng executor | Gọi các subscriber đồng bộ trong luồng phát thông điệp. | Mọi subscriber có cơ chế rollback cho external side effect hoặc các nhánh bất đồng bộ phía sau. |
| `ExecutorChannel` | Bàn giao tác vụ cho `TaskExecutor`, thường sang thread khác. | Handler phía worker đã xử lý xong hoặc tham gia transaction của người gửi. |
| `QueueChannel` trong bộ nhớ | Đưa message vào queue để poller xử lý sau. | Message bền vững khi process sập; dequeue được rollback cùng database. |
| Channel dùng **persistent message store** | Lưu message vào store có thể hỗ trợ transaction. | Store và dữ liệu nghiệp vụ nhất định đã cùng transaction; phải kiểm tra datasource/manager. |
| Outbound adapter tới HTTP/JMS/AMQP/Kafka | Gọi API hoặc producer theo đặc tính adapter. | Remote operation tham gia JDBC transaction của caller; ACK từ broker là commit DB. |

Một channel có thể chấp nhận message rồi downstream thất bại **vào lúc khác**, đặc biệt với executor hoặc queue. Đồng thời, một handler đồng bộ có thể ném exception trong chính lời gọi `send()`. Vì vậy cần quan sát **đường đi của lỗi** cùng **transaction boundary**, thay vì chỉ log `"send success"`.

### Ba câu hỏi luôn cần trả lời

1. **Ai đang giữ transaction?** Application service, poller, listener container hay transaction interceptor?
2. **Message được xử lý ở đâu?** Cùng thread, trong một queue nội bộ, ở một worker hay một broker/process khác?
3. **Tài nguyên nào tham gia transaction?** Cùng JDBC datasource, persistent message store, JMS session hoặc một transaction riêng phía broker?

Các transaction thông thường trong ứng dụng Spring imperative được liên kết với thread. `correlationId`, `messageId` và các header nghiệp vụ **không truyền JDBC transaction** từ thread này sang thread khác.

## 3. Nhìn bằng timeline: send trước commit, send sau commit

### Trường hợp A — gửi thông điệp ra ngoài **trước** commit DB

~~~mermaid
sequenceDiagram
    participant App as Order service
    participant DB as Orders DB
    participant Broker as Broker / external service
    App->>DB: BEGIN + INSERT order
    App->>Broker: send OrderCreated
    Broker-->>App: Accepted
    Note over App,DB: Sau đó có lỗi nghiệp vụ
    App->>DB: ROLLBACK
    Note over Broker: Message có thể đã được thấy/xử lý
~~~

Một message đã đến broker, gọi HTTP thành công hoặc tạo tác dụng phụ ngoài database sẽ **không tự biến mất** khi DB rollback. Consumer có thể đọc thấy sự kiện nhưng chưa thấy dữ liệu vì transaction tạo đơn vẫn chưa commit.

### Trường hợp B — chỉ gửi **sau** commit DB

~~~mermaid
sequenceDiagram
    participant App as Order service
    participant DB as Orders DB
    participant Broker as Broker
    App->>DB: BEGIN + INSERT order
    App->>DB: COMMIT
    Note over App: Có thể crash tại đây
    App->>Broker: send OrderCreated
    Broker-->>App: Accepted
~~~

Gửi sau commit tránh việc chủ động phát sự kiện của transaction đã rollback, nhưng tạo ra một **khoảng trống mất sự kiện** nếu process ngừng trước lúc gửi. Nếu broker nhận thành công nhưng process không ghi nhận được kết quả gửi, retry có thể phát ra **bản sao**.

### Trường hợp C — lưu message **trong cùng** transaction với dữ liệu nghiệp vụ

~~~mermaid
flowchart LR
  subgraph TX["TX database: nguyên tử trong một DB"]
    A["INSERT orders"] --> B["INSERT outbox_events"]
  end
  B --> C[("Committed outbox")]
  C --> D["Publisher sau commit"]
  D --> E["Broker / consumer"]
~~~

Ở đây, transaction bảo đảm *đơn hàng và bản ghi cần gửi* cùng commit hoặc cùng rollback. Publisher chạy độc lập, đọc outbox đã commit rồi gửi. Đây là **transactional outbox**. Nó giảm nguy cơ bỏ quên sự kiện, nhưng cần retry và idempotency vì publisher có thể gửi lặp.

## 4. Khi `send()` nằm trong phương thức `@Transactional`

Ví dụ dưới đây mô phỏng việc gửi message đến một **handler đồng bộ cũng ghi vào cùng database**. Đó là trường hợp có thể đạt atomicity trong một JDBC transaction mà không cần giao dịch phân tán.

Giả sử schema:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(20) NOT NULL
);

CREATE TABLE order_audit (
    event_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(40) NOT NULL
);
~~~

Khai báo message và integration flow, với các import thông thường được lược bỏ:

~~~java
record OrderCreated(String eventId, String orderId) {}

@Configuration
@EnableIntegration
class OrderMessageConfig {
    @Bean("auditEvents")
    MessageChannel auditEvents() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow auditFlow(OrderAuditWriter writer) {
        return IntegrationFlow.from("auditEvents")
                .handle(writer, "record")
                .get();
    }
}

@Component
class OrderAuditWriter {
    private final JdbcTemplate jdbc;

    OrderAuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void record(OrderCreated event) {
        jdbc.update("""
                INSERT INTO order_audit(event_id, order_id, event_type)
                VALUES (?, ?, ?)
                """, event.eventId(), event.orderId(), "OrderCreated");
    }
}
~~~

Application service mở transaction rồi dùng `MessageChannel.send()`:

~~~java
@Service
class CheckoutService {
    private final JdbcTemplate jdbc;
    private final MessageChannel auditEvents;

    CheckoutService(
            JdbcTemplate jdbc,
            @Qualifier("auditEvents") MessageChannel auditEvents) {
        this.jdbc = jdbc;
        this.auditEvents = auditEvents;
    }

    @Transactional
    public void createOrder(String orderId) {
        writeAndSend(orderId);
    }

    @Transactional
    public void createOrderThenFail(String orderId) {
        writeAndSend(orderId);
        throw new IllegalStateException("Simulated failure before commit");
    }

    private void writeAndSend(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "CREATED");

        OrderCreated event = new OrderCreated(
                UUID.randomUUID().toString(), orderId);
        Message<OrderCreated> message =
                MessageBuilder.withPayload(event).build();

        boolean accepted = auditEvents.send(message);
        if (!accepted) {
            throw new IllegalStateException("auditEvents rejected message");
        }
    }
}
~~~

**Đường đi khi `createOrder()` được gọi qua Spring transaction proxy:**

~~~mermaid
flowchart LR
  subgraph TX["Một JDBC transaction — cùng thread"]
    A["CheckoutService @Transactional"] --> B["INSERT orders"]
    B --> C["auditEvents.send()"]
    C --> D["DirectChannel"]
    D --> E["OrderAuditWriter.record()"]
    E --> F["INSERT order_audit"]
  end
  F --> G{"Trả về service"}
  G -->|"Thành công"| H["COMMIT cả 2 bảng"]
  G -->|"RuntimeException"| I["ROLLBACK cả 2 bảng"]
~~~

Vì `DirectChannel` chạy handler trên thread đang gửi, các lệnh JDBC trong `CheckoutService` và `OrderAuditWriter` có thể dùng cùng transaction do `@Transactional` mở ra. Khi `createOrderThenFail` ném `IllegalStateException`, transaction thường rollback **cả hai** câu `INSERT`, dù `send()` đã trả về thành công trước đó.

Điều kiện để kết luận này đúng:

- Lời gọi đi qua Spring proxy để `@Transactional` có hiệu lực.
- Handler xử lý **đồng bộ** và không chuyển sang executor/broker giữa chừng.
- Hai JDBC operation dùng các tài nguyên tham gia cùng transaction manager thích hợp.
- Exception được truyền tới interceptor, không bị nuốt và không bị cấu hình để commit.

Mặc định `@Transactional` rollback khi `RuntimeException` hoặc `Error` thoát ra ngoài. Với checked exception, cần xem rollback rules hoặc cấu hình `rollbackFor`. **`DirectChannel` không tự mở transaction**; transaction ở đây do application service sở hữu.

### Tình huống dễ nhầm: gọi API ngoài từ handler

Nếu thay `OrderAuditWriter.record()` bằng một handler gọi HTTP để gửi email, việc email đã được gửi **không thể rollback** cùng JDBC. Dù email được gọi đồng bộ trong `DirectChannel`, chỉ những hoạt động trên tài nguyên có tham gia transaction mới có thể được hoàn tác. Đồng bộ về thread **khác** với atomicity giữa tài nguyên.

## 5. Chuyển channel sẽ thay đổi ý nghĩa của send

Giữ nguyên `CheckoutService` nhưng thay `auditEvents` bằng channel sử dụng executor:

~~~java
@Bean("auditEvents")
MessageChannel auditEvents(TaskExecutor taskExecutor) {
    return new ExecutorChannel(taskExecutor);
}
~~~

Một `TaskExecutor` bất đồng bộ thường giao xử lý cho thread khác. Khi đó:

1. `CheckoutService` mở transaction A và ghi vào `orders`.
2. `auditEvents.send()` bàn giao message cho worker, sau đó phía gửi có thể tiếp tục.
3. Worker thực thi `OrderAuditWriter`, nhưng transaction A **không được truyền tự động** sang worker.
4. `CheckoutService` commit hoặc rollback A độc lập với việc worker xử lý thành công hay thất bại.

Nếu handler worker cần transaction DB, đặt `@Transactional` ở service được worker gọi hoặc cấu hình transaction advice thích hợp tại consumer. Transaction đó là **B**, không phải transaction A. Một số executor có thể thực thi trực tiếp trên thread gọi; luôn xem cấu hình `TaskExecutor` thực tế trước khi suy đoán.

### So sánh ba nơi gửi message

| Cấu hình | Lúc lời gọi gửi kết thúc | Rollback DB của sender có hoàn tác message không? |
| --- | --- | --- |
| `DirectChannel` → JDBC handler dùng cùng DB transaction | Handler đồng bộ đã chạy xong nếu không lỗi. | Có thể rollback **những ghi DB cùng transaction**; không rollback external side effect. |
| `ExecutorChannel` → worker riêng | Thường đã bàn giao task cho executor. | Không tự hoàn tác công việc worker đã làm; cần transaction của worker. |
| `QueueChannel` in-memory → poller | Message thường đã vào queue. | Không tự hoàn tác enqueue trong bộ nhớ hoặc bảo đảm tồn tại sau process crash. |

Với `PublishSubscribeChannel` không cấu hình executor, subscriber được gọi đồng bộ. Tuy nhiên, việc một subscriber gửi tiếp sang `ExecutorChannel` hoặc adapter bên ngoài sẽ lại tạo điểm chuyển giao mới. Muốn đánh giá đúng, cần lần theo **toàn bộ đường đi**.

## 6. Trì hoãn gửi đến sau khi commit

Khi không muốn phát event của một đơn hàng đã rollback, có thể phát **application event bên trong transaction** rồi dùng listener theo pha `AFTER_COMMIT` để gửi message. Ví dụ:

~~~java
record OrderStored(String eventId, String orderId) {}

@Service
class OrderApplicationService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            JdbcTemplate jdbc,
            ApplicationEventPublisher events) {
        this.jdbc = jdbc;
        this.events = events;
    }

    @Transactional
    public void create(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "CREATED");

        events.publishEvent(
                new OrderStored(UUID.randomUUID().toString(), orderId));
    }
}

@Component
class SendAfterCommit {
    private final MessageChannel outboundEvents;

    SendAfterCommit(
            @Qualifier("outboundEvents") MessageChannel outboundEvents) {
        this.outboundEvents = outboundEvents;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderStored(OrderStored event) {
        boolean accepted = outboundEvents.send(
                MessageBuilder.withPayload(event).build());
        if (!accepted) {
            throw new IllegalStateException("Event send rejected");
        }
    }
}
~~~

Giả sử `outboundEvents` đã được nối với outbound flow phù hợp. Spring sẽ gọi listener sau khi transaction có event `OrderStored` **commit thành công**. Theo mặc định, `@TransactionalEventListener` không xử lý event được publish ngoài transaction nếu không bật `fallbackExecution`.

**Ý nghĩa thật sự của `AFTER_COMMIT`:**

- Không gửi từ listener khi transaction nguồn rollback.
- Khi listener chạy, transaction nguồn **đã commit**; exception của send **không rollback** được dữ liệu đã commit.
- Ứng dụng có thể sập sau commit nhưng trước khi listener gửi, làm mất event.
- Nếu caller bên ngoài retry sau một lỗi không rõ kết quả, event có thể bị gửi lặp; phía nhận cần idempotency.
- Nếu listener cần **ghi thêm DB** sau commit, đừng mặc định nó còn một transaction có thể commit mới; thường phải mở transaction mới riêng, ví dụ bằng service có `@Transactional(propagation = REQUIRES_NEW)`.

Vì vậy, `AFTER_COMMIT` phù hợp với một số thông báo không mang yêu cầu giao tin bền vững. Với message nghiệp vụ quan trọng cần có khả năng khôi phục sau crash, **transactional outbox** là lựa chọn mạnh hơn.

### `BEFORE_COMMIT` có giải quyết triệt để không?

Không. Callback `BEFORE_COMMIT` có thể ném exception khiến transaction nguồn không commit, nhưng nếu message đã được broker/API bên ngoài chấp nhận trước khi lỗi xảy ra, rollback DB vẫn không tự thu hồi message đó. Việc đổi thời điểm callback **không tạo giao dịch nguyên tử liên tài nguyên**.

## 7. Transactional outbox: lưu ý định gửi cùng dữ liệu nghiệp vụ

Mục tiêu của outbox là bảo đảm **mỗi transaction tạo đơn commit thì có một bản ghi sự kiện bền vững để hệ thống phát đi**, và khi transaction rollback thì cả đơn lẫn sự kiện chưa gửi đều rollback.

### Schema tối thiểu

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL,
    delivery_status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Một transaction JDBC thực hiện hai lệnh SQL cùng datasource:

~~~java
@Service
class OrderCommandService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    OrderCommandService(JdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Transactional
    public void placeOrder(String orderId) throws JsonProcessingException {
        String eventId = UUID.randomUUID().toString();
        String payload = json.writeValueAsString(
                new OrderStored(eventId, orderId));

        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "CREATED");

        jdbc.update("""
                INSERT INTO outbox_events
                  (event_id, aggregate_id, event_type, payload_json, delivery_status)
                VALUES (?, ?, ?, ?, ?)
                """, eventId, orderId, "OrderCreated", payload, "PENDING");
    }
}
~~~

**Chú ý rollback rules:** `JsonProcessingException` là checked exception. Đoạn code tính payload trước khi ghi DB, nhưng nếu có lỗi checked exception từ bước khác *sau khi ghi*, cần định nghĩa rollback rules phù hợp, ví dụ `@Transactional(rollbackFor = Exception.class)` khi nghiệp vụ cần rollback tất cả checked exception.

Sau khi transaction DB commit, một relay/publisher đọc `outbox_events` và gửi các bản ghi `PENDING`. Relay có thể được kích hoạt bằng polling flow trong Spring Integration. Trong triển khai thực tế cần:

1. **Claim/lock** những bản ghi cần gửi để nhiều worker không cùng xử lý không kiểm soát; có thể dùng khóa/lease hoặc chiến lược phù hợp database.
2. **Publish** với `eventId` cố định, correlation header và thông tin version/schema cần thiết.
3. Chỉ đánh dấu `SENT` sau khi đã nhận tín hiệu thành công theo cơ chế broker/adapter tương ứng.
4. Khi timeout, crash hoặc kết quả không chắc chắn, cho phép retry. Không tự cho rằng việc gửi trước đó chắc chắn thất bại.
5. Consumer lưu `eventId` đã xử lý hoặc áp dụng thao tác nghiệp vụ idempotent, chống thực hiện side effect hai lần.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as DB + Outbox
    participant Relay as Outbox relay
    participant Broker as Broker
    participant Consumer as Consumer
    API->>DB: BEGIN; INSERT order + outbox
    API->>DB: COMMIT cả hai
    Relay->>DB: Claim pending event
    Relay->>Broker: Publish(eventId)
    Broker-->>Relay: Publish confirmation
    Note over Relay: Có thể crash trước khi mark SENT
    Relay->>DB: Mark SENT
    Broker->>Consumer: Deliver(eventId)
    Consumer->>Consumer: Check idempotency, apply once
~~~

**Giới hạn cần nhớ:** outbox **không** tạo một transaction bao phủ database và broker. Nếu relay publish thành công rồi sập trước khi đánh dấu đã gửi, nó sẽ publish lại. Vì vậy delivery thường được tổ chức theo hướng **at least once**, còn nghiệp vụ phải chống duplicate.

### Idempotent consumer khi message bị phát lại

Một cách phổ biến là lưu khóa sự kiện đã xử lý trong transaction **cùng** thao tác cập nhật nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Pseudocode:

~~~text
onMessage(event):
  begin DB transaction
    if processed_events already contains event.eventId:
      commit; acknowledge; return

    insert processed_events(event.eventId)
    apply business update (e.g., reserve inventory)
  commit DB transaction
  acknowledge delivery
~~~

Việc kiểm tra rồi thêm khóa phải xử lý **race condition** khi nhiều worker nhận cùng event đồng thời: cần unique constraint và logic xử lý conflict/duplicate phù hợp, trong cùng transaction với nghiệp vụ. Nếu DB commit nhưng consumer sập trước ACK, broker có thể gửi lại; lần sau consumer phát hiện `eventId` đã xử lý và bỏ qua side effect. Trong thực tế, thời điểm ACK/offset commit phụ thuộc listener container, broker và cấu hình adapter.

## 8. Khi nào một lần send thật sự tham gia transaction?

Không nên áp dụng một kết luận cho mọi loại channel. Điều kiện tối thiểu để hai thao tác có thể commit/rollback cùng nhau là **cùng tài nguyên giao dịch hoặc có cơ chế phối hợp transaction đã cấu hình**.

| Trường hợp | Phạm vi atomicity có thể đạt | Điểm cần xác minh |
| --- | --- | --- |
| `DirectChannel` tới hai handler JDBC trên cùng datasource | Các thao tác JDBC cùng transaction nếu đều tham gia transaction của caller. | Cùng thread, proxy `@Transactional`, transaction manager, exception propagation. |
| Persistent channel dùng transactional JDBC message store cùng DB nghiệp vụ | Ghi message vào store và ghi business row có thể cùng transaction DB. | Loại store/channel, datasource, transaction manager, thao tác enqueue/dequeue thực tế. |
| `QueueChannel` in-memory | Không có transaction database cho chính phần queue trong bộ nhớ. | Mất message khi restart, xử lý sau rollback, retry và độ bền. |
| Send tới broker có local transaction | Những thao tác broker được hỗ trợ trong broker transaction. | Session/container/producer transaction, commit và ACK; DB có tham gia hay không. |
| JDBC DB + JMS/Kafka/AMQP | Thường là **hai phạm vi transaction** trừ khi cấu hình cơ chế phối hợp được nền tảng hỗ trợ. | XA/JTA nếu được hỗ trợ, giới hạn transaction synchronization, thứ tự commit và failure window. |
| Send HTTP hoặc email | Side effect ở hệ thống bên ngoài. | Idempotency key, timeout, khả năng truy vấn trạng thái và compensation. |

**Transaction synchronization** (ví dụ callback sau commit) chỉ xác định *thời điểm thực hiện công việc* so với transaction đang có. Nó không đồng nghĩa mọi hệ thống nhận đều trở thành tài nguyên của transaction đó. Một số adapter hỗ trợ tích hợp transaction riêng; cần đọc tài liệu và kiểm thử theo version/driver/broker thực tế trước khi cam kết atomicity.

### Transaction tại polling endpoint

Với một polling flow, transaction thường bắt đầu tại **consumer**, không ở nơi ban đầu gọi `send()`. Ví dụ về vị trí boundary:

~~~java
@Bean
IntegrationFlow pollingFlow(
        PlatformTransactionManager txManager,
        OrderAuditWriter auditWriter) {
    return IntegrationFlow.from(
                    "workQueue",
                    e -> e.poller(
                            Pollers.fixedDelay(1000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(txManager)))
            .handle(auditWriter, "record")
            .get();
}
~~~

Giả sử bean `workQueue` đã được cấu hình với đúng loại `PollableChannel`. Transactional poller có thể bao quanh việc poll và xử lý downstream đồng bộ. Nhưng nếu `workQueue` là queue in-memory, JDBC rollback **không tự đưa message trở lại queue**. Muốn redelivery bền vững cần nguồn message và cơ chế lấy/ACK/transaction tương ứng.

## 9. Send thất bại: exception, retry và error channel

### Lỗi trong lời gọi đồng bộ

Với `DirectChannel`, exception từ handler thường truyền ngược qua `send()`. Nếu lỗi là `RuntimeException` thoát khỏi phương thức `@Transactional`, interceptor có thể rollback. Nếu ứng dụng bắt lỗi chỉ để ghi log rồi trả về bình thường, transaction có thể commit dù bước gửi không hoàn tất.

Ví dụ cần tránh:

~~~java
@Transactional
public void createWithHiddenFailure(String orderId) {
    repository.insert(orderId);
    try {
        outboundChannel.send(createMessage(orderId));
    } catch (Exception ex) {
        log.warn("Unable to send event", ex);
        // Method vẫn return bình thường: transaction có thể COMMIT.
    }
}
~~~

Nếu nghiệp vụ yêu cầu tất cả hoặc không gì cả **trong một transaction DB**, cần ném lại lỗi và xác minh chính sách rollback. Nếu bên ngoài là broker/API, ném lỗi rồi rollback DB **cũng không thu hồi được** những message đã gửi thành công trước đó; chọn outbox hoặc phương án bù trừ thích hợp.

### Lỗi bất đồng bộ

Với `ExecutorChannel`, polling endpoint hoặc adapter gửi xa, exception có thể xảy ra **sau khi phương thức gửi ban đầu đã trả về**. Lỗi có thể được đưa vào `errorChannel` dưới dạng `ErrorMessage`, được listener container xử lý, hoặc kích hoạt retry advice tùy endpoint.

Không coi “error flow đã nhận lỗi” là bằng chứng DB đã rollback. Transaction interceptor chỉ quyết định dựa trên kết quả và ngoại lệ mà nó quan sát, cùng các rollback rules. Khi error handler tiêu thụ lỗi và không ném lại, nhiều cấu hình coi quá trình xử lý là hoàn tất.

### Chọn nơi đặt retry

| Retry tại đâu? | Hợp lý khi | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Retry lời gọi `send()` của sender | Channel tạm không nhận và thao tác gửi có kết quả rõ ràng. | Đợt trước có thể đã được nhận dù caller timeout; cần ID cố định. |
| Retry toàn bộ business operation | Muốn chạy lại một đơn vị xử lý có transaction mới. | Mỗi lần thử phải có boundary phù hợp, tránh reuse transaction đã rollback-only. |
| Retry của outbox relay | Sự kiện đã được ghi bền vững; broker/API tạm lỗi. | Publish lặp nếu ACK không rõ; consumer idempotent. |
| Broker redelivery hoặc listener retry | Consumer lỗi hoặc chưa ACK. | Cấu hình retry/backoff, poison message, DLQ và deduplication. |

Không retry vô hạn thông điệp sai schema hoặc vi phạm quy tắc nghiệp vụ. Với message không thể xử lý, nên lưu lỗi và payload tham chiếu vào **dead-letter queue (DLQ)** hoặc kho lỗi bền vững có quy trình khắc phục/phát lại.

## 10. Phối hợp Router, Splitter, Aggregator và Gateway

Một lời gửi có thể lan sang nhiều nhánh. Cần phân tích boundary của **từng nhánh**:

~~~mermaid
flowchart LR
  G["Gateway"] --> T["Transformer"]
  T --> R{"Router"}
  R --> F["Filter: nhánh A"]
  R --> S["Splitter: nhánh B"]
  F --> DC["DirectChannel"]
  S --> EC["ExecutorChannel"]
  DC --> A["Handler A: JDBC"]
  EC --> B["Workers B"]
  B --> AG["Aggregator theo orderId"]
  A --> AG
~~~

- **Gateway** là điểm vào có kiểu dữ liệu rõ ràng. Nếu flow rẽ sang async, việc Gateway trả về không mặc nhiên có nghĩa mọi nhánh đã commit.
- **Filter** loại bỏ message hợp lệ theo điều kiện thường kết thúc nhánh bình thường. Không tự kích hoạt rollback chỉ vì message bị loại.
- **Transformer** thay đổi payload; việc giữ `eventId` và các header cần thiết giúp chống trùng, nhưng không làm transaction di chuyển.
- **Router** chọn channel; nhánh qua `DirectChannel` đồng bộ có thể ở transaction của caller, nhánh qua executor/broker có boundary riêng.
- **Splitter** tạo message con. Các message được xử lý ở nhiều thread hoặc process thường cần transaction riêng và kế hoạch retry riêng.
- **Aggregator** dùng `correlationId`, sequence/release strategy và message store để gom kết quả; phải xác định persistence, timeout, duplicate và khi nào kết quả đủ để commit. Aggregator không thể tự rollback các side effect đã commit ở nhánh khác.

**Phân biệt định danh:** `messageId` thường xác định một message cụ thể, `correlationId` nhóm các message cùng công việc, còn `eventId` nghiệp vụ dùng để chống xử lý lặp. Nên định nghĩa `eventId` ổn định qua các lần gửi lại của **cùng một sự kiện**, thay vì sinh ID mới ở mỗi retry.

## 11. Kiểm thử đúng tình huống của send và commit

### Kiểm thử tích hợp cho `DirectChannel`

Với `CheckoutService` và hai bảng ở phần 4:

~~~java
@SpringBootTest
class TransactionalSendIT {
    @Autowired CheckoutService checkoutService;
    @Autowired JdbcTemplate jdbc;

    @Test
    void successCommitsBothOrderAndAudit() {
        String orderId = UUID.randomUUID().toString();

        checkoutService.createOrder(orderId);

        assertEquals(1, count("orders", orderId));
        assertEquals(1, count("order_audit", orderId));
    }

    @Test
    void rollbackRemovesBothOrderAndAudit() {
        String orderId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> checkoutService.createOrderThenFail(orderId));

        assertEquals(0, count("orders", orderId));
        assertEquals(0, count("order_audit", orderId));
    }

    private int count(String table, String orderId) {
        String query = switch (table) {
            case "orders" ->
                    "SELECT COUNT(*) FROM orders WHERE order_id = ?";
            case "order_audit" ->
                    "SELECT COUNT(*) FROM order_audit WHERE order_id = ?";
            default -> throw new IllegalArgumentException(table);
        };
        return jdbc.queryForObject(query, Integer.class, orderId);
    }
}
~~~

Không gắn `@Transactional` lên test nếu điều đó khiến transaction kiểm thử bọc ngoài service và che mất hành vi commit/rollback thực tế. Nên dùng ID riêng cho mỗi case và quan sát dữ liệu **sau khi** method trả về.

### Ma trận failure injection cho hệ thống gửi message

| Điểm gây lỗi | Cần quan sát | Kết quả thiết kế mong muốn |
| --- | --- | --- |
| Handler JDBC đồng bộ ném lỗi | Hai bảng có cùng rollback không? | Không còn dữ liệu commit nếu cùng DB transaction. |
| DB rollback **sau** khi outbound API đã nhận message | Consumer có nhìn thấy sự kiện của đơn không tồn tại không? | Bộc lộ rủi ro send trước commit; chuyển sang outbox nếu cần bảo đảm. |
| Process sập sau DB commit, trước `AFTER_COMMIT` send | Có cơ chế phát lại event không? | Nếu cần bền vững, outbox record vẫn còn để relay xử lý. |
| Broker nhận event, relay sập trước `mark SENT` | Event có bị gửi lại không? | Có thể lặp; consumer idempotent giữ business effect đúng một lần. |
| `ExecutorChannel` handler ném lỗi | Sender có thể đã trả về chưa; lỗi đến đâu? | Worker transaction và error handling độc lập; có log/metric/truy vết. |
| Queue in-memory mất message sau restart | Message có thể phục hồi không? | Không dựa vào queue in-memory cho delivery bền vững. |
| Consumer commit DB rồi mất kết nối trước ACK | Redelivery có tạo side effect lặp không? | Deduplicate bằng eventId và ràng buộc unique. |
| Filter loại message hoặc Router chọn nhánh không có handler | Flow xử lý lỗi hoặc kết thúc như thế nào? | Có chính sách nghiệp vụ rõ, không suy rằng mọi "không gửi tiếp" là rollback. |

Ghi log và metric ít nhất với `orderId`, `eventId`, `correlationId`, endpoint/channel, trạng thái gửi, số lần retry, thời điểm commit và trạng thái ACK khi có thể. Tránh log payload chứa dữ liệu nhạy cảm. Đặc biệt, **một log "send accepted" không thay cho phép đo end-to-end** từ tạo đơn đến consumer xử lý.

## 12. Chọn phương án gửi phù hợp

| Nhu cầu | Cách thực hiện phù hợp | Giới hạn cần chấp nhận |
| --- | --- | --- |
| Gọi handler đồng bộ ghi cùng database trong một use case | Mở `@Transactional` ở service, send qua `DirectChannel`, handler dùng cùng DB transaction. | Chỉ atomic cho tài nguyên tham gia; không bao gồm API bên ngoài. |
| Chỉ muốn gửi thông báo nhẹ sau khi DB commit | Application event + `@TransactionalEventListener(AFTER_COMMIT)`. | Có thể mất thông báo khi process sập; không phù hợp yêu cầu delivery bền vững. |
| Sự kiện quan trọng phải được gửi sau khi business data commit | Ghi outbox cùng transaction DB, relay gửi sau commit, consumer idempotent. | Cần vận hành poller, retry, claim/locking, deduplication và theo dõi backlog. |
| Xử lý message bất đồng bộ từ broker | Consumer transaction độc lập + ACK/redelivery thích hợp. | Có thể xử lý lại sau timeout/crash; cần idempotency và DLQ. |
| Gửi tới nhiều hệ thống không chia sẻ tài nguyên giao dịch | Event-driven workflow và compensation/Saga nếu cần. | Không có rollback JDBC chung mặc định; cần quản lý tiến độ từng bước. |

Transaction càng kéo dài qua các cuộc gọi mạng càng dễ giữ lock và connection lâu. Với nghiệp vụ phân tán, ưu tiên transaction cục bộ ngắn, message bền vững và cơ chế hồi phục có thể kiểm thử được.

## 13. Bài tập thực hành

**Bài 1 — phân tích `send()` trong transaction.** Vẽ timeline cho `@Transactional service → INSERT orders → DirectChannel → handler JDBC → COMMIT`. Đổi channel sang `ExecutorChannel` và chỉ rõ transaction nào quản lý câu lệnh SQL trong worker. Giải thích kết quả nếu caller rollback sau khi worker đã ghi thành công.

**Bài 2 — sau commit nhưng chưa đủ an toàn.** Dùng `@TransactionalEventListener(AFTER_COMMIT)` để phát message. Giả lập lỗi gửi hoặc process crash ngay sau commit. Xác định vì sao chỉ có callback không đủ đáp ứng yêu cầu “mỗi đơn đã commit đều có event phát được lại”.

**Bài 3 — outbox và xử lý trùng.** Viết chức năng tạo đơn lưu `orders` và `outbox_events` cùng transaction. Tạo relay đọc bản ghi `PENDING`, giả lập broker nhận thành công nhưng relay không đánh dấu `SENT`. Cho relay chạy lại và chứng minh consumer với `processed_events(event_id)` không trừ tồn kho hai lần.

**Bài 4 — flow nhiều nhánh.** Thiết kế `Gateway → Router → Splitter → hai ExecutorChannel → Aggregator`. Mỗi nhánh chọn transaction boundary, retry và idempotency key; đưa ra phương án khi một nhánh không trả kết quả trước timeout.

### Câu hỏi tự đánh giá

**1. `channel.send(message)` trả về `true` có chứng minh dữ liệu DB đã commit không?** Không. Nó phản ánh thao tác channel chấp nhận message theo cơ chế riêng; transaction của caller có thể vẫn đang mở.

**2. `DirectChannel` có làm external API tham gia transaction JDBC không?** Không. Nó giúp xử lý đồng bộ trên cùng thread nhưng không biến side effect bên ngoài thành tài nguyên JDBC transaction.

**3. Vì sao `AFTER_COMMIT` vẫn có thể làm mất sự kiện?** Vì DB đã commit trước khi callback gửi; ứng dụng có thể sập trong khoảng giữa và chưa có bản ghi bền vững để phục hồi.

**4. Outbox giải quyết điều gì, chưa giải quyết điều gì?** Nó commit cùng lúc business data và ý định gửi event trong một DB; không bảo đảm broker và DB commit nguyên tử, nên phải chấp nhận khả năng publish lặp và làm consumer idempotent.

**5. Khi nhận một message lặp sau khi consumer đã commit nhưng chưa ACK, làm gì?** Dùng định danh sự kiện ổn định, kiểm tra/lưu unique key trong cùng transaction với cập nhật nghiệp vụ, sau đó ACK theo cơ chế adapter.

## 14. Checklist trước khi vận hành

- [ ] Vẽ rõ transaction bắt đầu và kết thúc tại service, poller, listener hoặc handler nào.
- [ ] Xác nhận channel chạy đồng bộ hay có chuyển thread/process và tác động của điều đó lên lỗi/commit.
- [ ] Kiểm tra `send()` trả về gì, khi nào ném exception và khi nào chỉ bàn giao message cho bước xử lý sau.
- [ ] Tách biệt trạng thái send accepted, broker confirmed, consumer processed và DB committed.
- [ ] Không coi outbound send trong `@Transactional` là bảo đảm atomicity giữa DB và broker/API.
- [ ] Đối với sự kiện nghiệp vụ quan trọng, ghi outbox trong cùng transaction với dữ liệu nguồn.
- [ ] Thiết kế relay có claim/locking, retry, backoff, khả năng khôi phục và giám sát backlog.
- [ ] Sử dụng `eventId` ổn định và consumer idempotent để tránh side effect lặp.
- [ ] Kiểm thử crash trước/sau commit, trước/sau publish, trước/sau ACK, và lỗi trong nhánh bất đồng bộ.
- [ ] Có error channel/DLQ và quy trình xử lý, phát lại message lỗi không thể tự phục hồi.

**Ghi nhớ:** Khi nói “send message trong transaction”, hãy xác định **transaction bảo vệ tài nguyên nào** và **message thực sự được giao đến đâu trước khi commit**. Spring Integration giúp tổ chức và quan sát luồng EIP ít phụ thuộc, dễ mở rộng; tính đúng đắn trước lỗi được quyết định bởi transaction boundary, độ bền của message và chiến lược retry/idempotency.
