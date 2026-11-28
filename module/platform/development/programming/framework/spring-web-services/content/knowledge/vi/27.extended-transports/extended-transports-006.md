# Xác nhận JMS, giao dịch cục bộ và giới hạn đối với nghiệp vụ từ xa

## 1. Vì sao JMS acknowledgement không đồng nghĩa nghiệp vụ đã hoàn tất?

Trong module **SPRING_WEB_SERVICES**, các dịch vụ SOAP được xây dựng theo hướng contract-first với XSD/WSDL, JAXB/OXM, Spring-WS endpoint/client, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Khi xử lý cần chạy nền hoặc kết nối nhiều hệ thống, ứng dụng có thể dùng **JMS (Java Message Service)** làm transport bất đồng bộ.

Cần phân biệt năm loại xác nhận:

- **JMS acknowledgement**: consumer acknowledge message cho provider theo acknowledgement mode/session.
- **JMS transaction commit**: commit các send/receive operations thuộc JMS session transaction.
- **Database commit**: transaction cục bộ của database đã commit.
- **SOAP/HTTP response**: caller nhận phản hồi protocol/transport.
- **Business confirmation**: hệ thống nghiệp vụ ghi nhận hành động đã hoàn tất theo hợp đồng.

JMS ACK không tự chứng minh database transaction đã commit; DB commit không tự chứng minh message đã được acknowledge. HTTP 200/202 hoặc SOAP response cũng có thể chỉ xác nhận tiếp nhận, chưa phải kết quả nghiệp vụ cuối cùng.

Bài thuộc chương **Truyền tải mở rộng**, tập trung vào **“Xác nhận JMS, giao dịch cục bộ và giới hạn đối với nghiệp vụ từ xa”**.

### Mục tiêu học tập

1. Phân biệt JMS acknowledgement, JMS transaction, database commit và business confirmation.
2. Hiểu acknowledgement modes và tác động khi consumer lỗi.
3. Phân biệt local JMS transaction với local DB transaction.
4. Đánh giá XA/JTA và giới hạn distributed transaction.
5. Thiết kế Outbox/Inbox, idempotency, retry và reconciliation.
6. Phân biệt at-most-once, at-least-once và exactly-once.
7. Phân biệt SOAP over HTTP, SOAP over JMS và business callback.
8. Kiểm thử rollback, duplicate, crash window và partner failures.

## 2. Các tầng xác nhận trong workflow SOAP/JMS

Giả sử ứng dụng A nhận lệnh SubmitOrder, lưu đơn vào database và phát JMS event cho hệ thống B xử lý.

~~~mermaid
sequenceDiagram
    participant C as SOAP Caller
    participant A as Order Service
    participant DB as Database
    participant MQ as JMS Broker
    participant B as Consumer
    C->>A: SubmitOrder SOAP
    A->>DB: Save Order and Outbox
    DB-->>A: DB commit
    A->>MQ: Publish event
    MQ-->>A: Broker accepts send
    A-->>C: Accepted response
    MQ->>B: Deliver event
    B->>B: Process business action
    B->>DB: Commit local result
    B-->>MQ: JMS commit / ACK
    B-->>A: Business completion event
~~~

Sơ đồ mô tả các transaction boundaries độc lập; không hàm ý DB và broker tự động cùng transaction.

| Sự kiện | Điều được xác nhận | Chưa chứng minh |
|---|---|---|
| Producer send thành công | Provider nhận send operation | Consumer đã xử lý |
| Consumer ACK/commit | Message được acknowledge theo JMS semantics | Business effect từ xa đã hoàn tất |
| DB commit | DB transaction đã commit | JMS transaction đã commit |
| HTTP 202 | Request được chấp nhận xử lý | Job đã thành công |
| SOAP Accepted | Service xác nhận tiếp nhận | Partner workflow đã hoàn tất |
| Completion event | Producer tuyên bố business completion | Mọi downstream đã hoàn tất |

### 2.1. Đặt tên trạng thái chính xác

Không gộp mọi thứ vào một cờ success. Một lifecycle có thể gồm:

~~~text
RECEIVED -> VALIDATED -> PERSISTED -> PUBLISHED
         -> ACCEPTED_BY_PARTNER -> PROCESSING
         -> COMPLETED / FAILED / UNKNOWN
~~~

Contract cần định nghĩa ý nghĩa từng state. PUBLISHED không đồng nghĩa COMPLETED.

## 3. JMS acknowledgement modes

JMS consumer nhận message qua MessageConsumer, listener hoặc Spring listener container. Provider coi message đã consume/acknowledged dựa trên acknowledgement mode, session transaction và provider/container behavior.

| Mode | Hành vi tổng quát | Ghi chú |
|---|---|---|
| AUTO_ACKNOWLEDGE | Session tự acknowledge theo JMS API ở ranh giới receive/listener tương ứng | Không đồng nghĩa DB commit |
| CLIENT_ACKNOWLEDGE | Client gọi Message.acknowledge(); semantics thường áp dụng các messages đã nhận trong session | Có thể ACK nhiều messages |
| DUPS_OK_ACKNOWLEDGE | Provider được phép trì hoãn ACK, chấp nhận duplicate | Consumer phải idempotent |
| Transacted session | ACK consume gắn với Session.commit(); rollback bằng Session.rollback() | Local JMS transaction |

### 3.1. AUTO_ACKNOWLEDGE

Với synchronous receive, ACK gắn với việc receive trả message theo JMS API. Với listener, provider/container xử lý ACK theo semantics listener/session. Không suy rằng ACK chỉ diễn ra sau DB commit nếu database sử dụng transaction manager độc lập.

### 3.2. CLIENT_ACKNOWLEDGE

~~~java
message.acknowledge();
~~~

Trong CLIENT_ACKNOWLEDGE, acknowledgement thường áp dụng cho **tất cả messages đã consume bởi session hiện tại**, không chỉ message đang gọi. Điều này có thể gây bất ngờ khi session được chia sẻ hoặc listener xử lý batch. Không ACK ngay sau deserialize nếu business work chưa qua điểm an toàn.

### 3.3. DUPS_OK_ACKNOWLEDGE

Provider có thể batch hoặc trì hoãn ACK. Message có thể được redeliver khi lỗi. Consumer phải chấp nhận xử lý lặp, không giả định mỗi event chỉ tới đúng một lần.

### 3.4. Transacted JMS Session

~~~java
Session session = connection.createSession(
    true,
    Session.SESSION_TRANSACTED
);

// receive, process, send reply/event...
session.commit();
~~~

Commit/rollback tác động các JMS operations thuộc session transaction. DB transaction không tự tham gia vì cùng method gọi repository. Trong Spring, container thường quản lý session transaction; không trộn commit thủ công với quản lý session của container.

## 4. JMS ACK không phải database transaction

~~~java
@JmsListener(destination = "orders.in")
public void consume(OrderMessage message) {
    Order order = repository.findById(message.orderId())
        .orElseThrow();

    order.markProcessed();
    repository.save(order);
}
~~~

Nếu acknowledgement độc lập với DB commit, process có thể crash sau ACK nhưng trước DB commit. Message có thể không được redeliver dù business state chưa được ghi. Thứ tự thực tế phụ thuộc container/transaction wiring; không suy atomicity chỉ vì dùng @JmsListener.

### 4.1. Transaction managers trong Spring

- JmsTransactionManager: local transaction cho JMS ConnectionFactory.
- DataSourceTransactionManager/JdbcTransactionManager: local transaction cho DataSource.
- JpaTransactionManager: transaction cho persistence unit.
- JtaTransactionManager: phối hợp global transaction khi resources hỗ trợ enlistment.

Một method có @Transactional phải xác định manager nào được chọn, resources nào được enlist và listener container có tham gia cùng transaction không. Annotation không tự biến hai local resources thành distributed transaction.

### 4.2. Một @Transactional vẫn có thể không atomic

~~~java
@Transactional
@JmsListener(destination = "orders.in")
public void consume(OrderMessage message) {
    repository.save(toEntity(message));
    partnerSoapClient.submit(toPartnerRequest(message));
}
~~~

Đây là anti-pattern nếu cho rằng annotation tự bao trùm database, broker và remote SOAP call. Transaction manager có thể chỉ quản lý DB; listener container có session riêng; remote SOAP call không tự là XA resource; partner có thể đã commit side effect dù DB local rollback.

## 5. Local JMS transaction và local DB transaction

~~~mermaid
flowchart TD
    A["Receive JMS message"] --> B["Local JMS transaction"]
    A --> C["Local DB transaction"]
    B --> D["Broker ACK at JMS commit"]
    C --> E["Database rows commit"]
    D -. "Không atomic với" .- E
~~~

Hai transaction managers có thể cùng hoạt động trong một call stack nhưng vẫn commit/rollback độc lập nếu không có distributed transaction coordination.

### 5.1. JMS commit trước DB commit

~~~text
Receive -> JMS commit / ACK -> DB write -> DB commit fails
~~~

Message có thể đã bị tiêu thụ trong khi DB chưa ghi business state.

### 5.2. DB commit trước JMS commit

~~~text
Receive -> DB write -> DB commit -> JMS commit fails
~~~

Broker có thể redeliver message dù DB effect đã tồn tại. Consumer cần deduplication và idempotency.

### 5.3. Crash windows

| Failure point | DB | JMS | Rủi ro |
|---|---|---|---|
| Trước DB write | Chưa commit | Chưa commit | Redelivery retry |
| Sau DB commit, trước JMS commit | Đã commit | Rollback/unknown | Duplicate |
| Sau JMS commit, trước DB commit | Tùy wiring | Đã commit | Message mất khi DB chưa đổi |
| Sau cả hai commit | Đã commit | Đã commit | Remote workflow vẫn có thể pending |

Không thể khắc phục crash windows bằng cách gọi hai lệnh commit sát nhau.

## 6. Spring JMS listener và transaction configuration

Behavior phụ thuộc DefaultMessageListenerContainer/SimpleMessageListenerContainer, session transaction/ack mode, transaction manager, provider và Spring version.

Ví dụ local JMS manager:

~~~java
@Bean
public JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Khi dùng @Transactional("jmsTransactionManager"), hãy xác minh listener invocation thực sự tham gia transaction đó. Annotation không tự cấu hình transacted session nếu listener factory chưa đặt đúng.

- Local JMS transaction: broker có thể rollback consume khi listener ném exception; DB changes không tự rollback nếu dùng manager khác.
- Local DB transaction: DB commit SQL atomically trong phạm vi DB, nhưng không tự rollback broker ACK.
- Hai @Transactional methods dùng DB và JMS managers vẫn là hai local scopes nếu không có global coordinator.

## 7. XA/JTA: khi nào dùng distributed transaction?

XA là protocol để coordinator điều phối resource managers hỗ trợ XA. JTA cung cấp Java transaction APIs; JTA manager có thể phối hợp database và JMS provider nếu resource adapters hỗ trợ và được cấu hình đúng.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant TM as JTA Coordinator
    participant DB as XA Database
    participant MQ as XA JMS Broker
    App->>TM: Begin global transaction
    TM->>DB: Enlist
    TM->>MQ: Enlist
    App->>DB: Update database
    App->>MQ: Send or consume
    App->>TM: Commit
    TM->>DB: Prepare
    TM->>MQ: Prepare
    TM->>DB: Commit
    TM->>MQ: Commit
~~~

Đây là two-phase commit ở mức khái niệm; coordinator/providers quản lý protocol, recovery, in-doubt và heuristic outcomes.

### 7.1. XA giúp gì?

Nếu DB và broker cùng tham gia global transaction, coordinator phối hợp commit/rollback các enlisted resources. Điều này giảm crash window giữa DB state và broker delivery trong phạm vi đó.

### 7.2. XA không bao trùm SOAP server từ xa

HTTP SOAP call thông thường không phải XA resource của JTA transaction local. Coordinator không thể tự rollback business action B đã commit khi DB A thất bại.

### 7.3. Chi phí và giới hạn

Cần đánh giá XA support, resource adapters, JTA coordinator, recovery logs, timeout, lock duration, in-doubt transactions, heuristic outcomes, throughput và vận hành. XA chỉ phù hợp khi atomicity giữa các enlisted resources thực sự cần thiết.

### 7.4. XA không đồng nghĩa exactly-once business

XA chỉ phối hợp resources đã enlist; external APIs, consumer side effects và callback retries vẫn cần idempotency.

## 8. Giới hạn khi gọi SOAP business operation từ xa

Giả sử A mở DB transaction và gọi ChargePayment trên B:

~~~text
A: BEGIN DB transaction
A: reserve order
A: POST SOAP ChargePayment to B
B: charge payment and commit
A: DB commit fails
A: local rollback
~~~

A rollback database của mình nhưng không thể rollback payment B đã commit bằng local JDBC transaction. Gửi lại request có thể charge lần hai; response mất khiến caller không rõ outcome.

### 8.1. Timeout không chứng minh partner chưa thực hiện

Request có thể chưa rời client, đã tới B nhưng chưa xử lý, đã commit nhưng response mất, hoặc được B queue. Không suy timeout là business failure. Dùng correlation/idempotency key và status query/reconciliation.

### 8.2. HTTP status không thay business status

HTTP 200 biểu thị trao đổi protocol; business semantics nằm trong SOAP response. HTTP 202 thường xác nhận tiếp nhận, không bảo đảm job hoàn tất. SOAP body có thể công bố Accepted, Processing, Completed, Rejected theo contract.

## 9. Transactional Outbox

Khi command cần cập nhật DB và phát message, **Transactional Outbox** ghi business state và publish intent trong cùng DB transaction.

~~~mermaid
flowchart TD
    A["SOAP SubmitOrder"] --> B["DB transaction"]
    B --> C["Insert Order"]
    B --> D["Insert Outbox event"]
    C --> E["Commit together"]
    D --> E
    E --> F["Outbox relay reads pending rows"]
    F --> G["Publish JMS"]
    G --> H["Mark row published"]
    H --> I["Consumer idempotently processes"]
~~~

### 9.1. Producer transaction

~~~java
@Transactional("dbTransactionManager")
public SubmitOrderResult submit(SubmitOrderRequest request) {
    Order order = orderRepository.save(
        Order.pending(request.orderId(), request.customerId())
    );

    outboxRepository.save(
        OutboxEvent.pending(
            UUID.randomUUID(),
            "OrderSubmitted",
            order.getId(),
            serializeEvent(order)
        )
    );

    return SubmitOrderResult.accepted(order.getId());
}
~~~

Đây là skeleton; serialization/schema versioning/validation cần hoàn thiện. Order và OutboxEvent cùng commit/rollback trong **một DB transaction**.

### 9.2. Outbox relay

~~~text
read pending row -> send JMS -> broker accepts -> mark published
~~~

Relay có thể crash sau khi broker nhận message nhưng trước khi đánh dấu row. Lần sau có thể publish duplicate; event cần stable ID và consumer idempotent.

### 9.3. Outbox không phải XA

Outbox dùng một DB local transaction cho business state và publish intent, rồi relay sang broker. Nó không tạo atomic commit DB/JMS; nó cung cấp recovery/retry và chấp nhận duplicate có kiểm soát.

## 10. Inbox và idempotent consumer

**Inbox** ghi nhận event identity cùng business effect trong DB transaction:

~~~mermaid
flowchart TD
    A["Receive JMS message"] --> B["Begin DB transaction"]
    B --> C{"Inbox event ID exists?"}
    C -->|"Yes"| D["Skip duplicate effect"]
    C -->|"No"| E["Insert inbox identity"]
    E --> F["Apply business changes"]
    F --> G["Commit DB"]
    D --> G
    G --> H["Commit JMS receive / ACK"]
~~~

~~~java
@Transactional("dbTransactionManager")
public void apply(OrderSubmitted event) {
    if (inboxRepository.existsByEventId(event.eventId())) {
        return;
    }

    inboxRepository.insert(event.eventId(), event.aggregateId());
    orderProjectionRepository.apply(event);
}
~~~

Đây chỉ là DB logic. Listener container/transaction boundary phải bảo đảm message không ACK trước DB commit; có thể dùng XA hoặc phối hợp local JMS rollback với DB idempotency.

Inbox cần unique constraint trên event ID để tránh race khi nhiều consumers đồng thời. JMSMessageID không luôn là business idempotency key: caller retry có thể tạo message ID khác cho cùng command.

## 11. Delivery semantics

| Semantics | Ý nghĩa | Hệ quả |
|---|---|---|
| At-most-once | Giao tối đa một lần; có thể mất khi lỗi | Không redelivery |
| At-least-once | Retry/redelivery theo policy | Có thể duplicate |
| Exactly-once | Chỉ có nghĩa trong phạm vi resources/side effects được định nghĩa | Không mặc định áp dụng toàn hệ thống |

At-least-once cùng idempotent consumer là mô hình phổ biến:

~~~text
Event E-100 delivered
  -> DB transaction commits E-100
  -> consumer crashes before JMS ACK
  -> E-100 redelivered
  -> Inbox detects E-100
  -> skip duplicate effect
  -> acknowledge again
~~~

JMSMessageID/JMSRedelivered hữu ích cho monitoring nhưng không thay business idempotency store. Broker có thể hỗ trợ transactions/duplicate detection, song side effects ngoài broker vẫn có thể lặp.

## 12. Retry, redelivery và dead-letter queue

| Lỗi | Cách xử lý |
|---|---|
| DB transient outage | Rollback/retry có backoff |
| Partner timeout, outcome chưa rõ | Reconcile bằng idempotency/status; không retry side effect mù |
| SOAP validation Fault | Không retry payload sai |
| WS-Security trust failure | Quarantine/alert, sửa trust |
| Business rejection | Ghi rejected, không retry nếu permanent |
| Schema không hỗ trợ | Manual intervention hoặc upgrade contract |
| Serialization bug | DLQ, sửa consumer/payload mapping |

### 12.1. Exponential backoff

~~~text
delay = min(maxDelay, baseDelay * 2^attempt) + jitter
~~~

Đặt max attempts, retry window và concurrency limits để tránh retry storm. Không giữ JMS transaction lâu trong vòng lặp retry vô hạn.

### 12.2. Provider-specific behavior

Số lần thử, delay, delivery count và DLQ routing khác giữa providers. Kiểm tra broker thật thay vì suy defaults từ JMS API chung.

### 12.3. DLQ phải có quy trình

1. Alert khi DLQ có message.
2. Phân loại lỗi kỹ thuật/nghiệp vụ/contract/security.
3. Kiểm tra payload theo quyền.
4. Sửa nguyên nhân trước replay.
5. Replay có audit và idempotency.
6. Giữ event/correlation identity cần thiết.

Poison message không nên bị rollback vô hạn làm nghẽn consumer.

## 13. SOAP over JMS và JMS event payload

**SOAP over JMS** giữ SOAP Envelope/Header/Body và dùng JMS làm transport theo binding phù hợp. **JMS event payload** có thể là JSON/Avro/DTO được publish sau khi SOAP ingress chuyển thành domain event; payload đó không nhất thiết là SOAP Envelope.

JMS acknowledgement vẫn xác nhận delivery semantics, không phải business confirmation. Một SOAP/JMS response có thể chỉ xác nhận protocol exchange; event Completed chỉ có ý nghĩa nếu được phát sau khi business result được commit theo contract.

### 13.1. SOAP over HTTP kết hợp JMS async

~~~mermaid
flowchart LR
    A["SOAP client"] -->|"HTTPS request"| B["Spring-WS endpoint"]
    B --> C["DB + Outbox"]
    C --> D["JMS broker"]
    D --> E["Worker"]
    E --> F["Partner SOAP service"]
    F --> E
    E --> G["Completion event/status"]
    G --> B
    B -->|"202 Accepted + correlationId"| A
    A -->|"Status query / callback"| B
~~~

HTTP 202 chỉ xác nhận tiếp nhận; caller cần status endpoint/callback để nhận kết quả cuối.

## 14. Business confirmation cho asynchronous SOAP

Contract nên tách acceptance response khỏi completion notification.

~~~xml
<ord:SubmitOrderResponse xmlns:ord="urn:example:orders:v1">
    <ord:requestId>REQ-10042</ord:requestId>
    <ord:status>ACCEPTED</ord:status>
</ord:SubmitOrderResponse>
~~~

requestId cần duy nhất trong phạm vi contract; status query cần authorization và retention policy.

### 14.1. Các pattern trả kết quả

| Pattern | Mô tả | Trade-off |
|---|---|---|
| Status polling | Client hỏi theo request ID | Dễ triển khai, tạo polling load |
| SOAP callback | Service gọi endpoint client | Cần listener, security, correlation, retries |
| Completion event | Publish JMS/event | Decoupled, cần Inbox/dedup |
| Long polling | Giữ request chờ | Connection/thread/timeouts |
| Synchronous response | Chờ business hoàn tất | Phù hợp operation ngắn |

### 14.2. Business states

- RECEIVED: application nhận request.
- ACCEPTED: validate/authorize và persist xong.
- QUEUED: event đã publish theo policy.
- PROCESSING: worker đang xử lý.
- COMPLETED: business outcome commit và được ghi nhận.
- REJECTED/FAILED: kết thúc thất bại.
- UNKNOWN: chưa xác định outcome, cần reconciliation.

Giữ correlation ID qua SOAP ingress, DB, Outbox, JMS properties/payload, partner SOAP call và completion event. Không dùng JMSMessageID làm correlation nghiệp vụ duy nhất.

## 15. Saga và compensating transaction

Khi workflow gồm nhiều service độc lập, local transactions không thể rollback toàn hệ thống. **Saga** chia workflow thành local transactions và compensation actions:

~~~mermaid
flowchart TD
    A["Order accepted"] --> B["Reserve inventory"]
    B --> C{"Inventory reserved?"}
    C -->|"No"| X["Reject order"]
    C -->|"Yes"| D["Charge payment"]
    D --> E{"Payment succeeded?"}
    E -->|"Yes"| F["Confirm order"]
    E -->|"No"| G["Release inventory"]
    G --> H["Mark order failed"]
~~~

Saga không phải DB rollback toàn cục. Compensation là business action mới (refund/release/cancel) và chính nó cũng có thể fail/retry.

Nếu A không biết B đã charge hay chưa, không tự động charge lại hoặc refund trước khi reconcile. Query partner theo idempotency key/reference.

Saga phù hợp workflow qua SOAP services không tham gia transaction chung hoặc chấp nhận intermediate states. XA phù hợp hơn cho enlisted resources có coordinator/recovery.

## 16. Ordering, duplicate và concurrency

Ordering phụ thuộc broker, grouping, consumer concurrency và redelivery. Nếu events cùng aggregate phải theo thứ tự, route/group theo aggregate key nếu provider hỗ trợ hoặc serialize xử lý theo key.

~~~json
{
  "eventId": "evt-100",
  "aggregateId": "order-2048",
  "aggregateVersion": 7,
  "eventType": "OrderPaid"
}
~~~

Consumer kiểm tra aggregate version để phát hiện gap/out-of-order. JSON trên là payload event minh họa, không phải SOAP Envelope.

Unique inbox constraints, optimistic locking và idempotent commands giúp xử lý duplicate/concurrency. Không chỉ giữ trạng thái dedup trong memory vì restart sẽ làm mất.

## 17. Spring-WS và Spring JMS: ranh giới thành phần

Một ứng dụng có thể gồm MessageDispatcherServlet/@Endpoint nhận SOAP, WebServiceTemplate gọi partner SOAP, JmsTemplate publish, @JmsListener consume, DB/JMS/JTA transaction managers, Outbox relay, Inbox repository và status/callback endpoints.

### 17.1. Listener factory với local JMS manager

~~~java
@Bean
public DefaultJmsListenerContainerFactory ordersListenerFactory(
        ConnectionFactory connectionFactory,
        JmsTransactionManager jmsTransactionManager) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setTransactionManager(jmsTransactionManager);
    factory.setConcurrency("2-8");

    return factory;
}
~~~

Đây là cấu hình minh họa local JMS transaction. Provider/version có thể cần acknowledgement/session/exception settings cụ thể. Nó chưa làm DB transaction atomic với JMS.

### 17.2. Listener method

~~~java
@JmsListener(
    destination = "orders.in",
    containerFactory = "ordersListenerFactory"
)
public void receive(OrderSubmitted event) {
    orderApplicationService.applyIdempotently(event);
}
~~~

Với container-managed transacted session, exception propagation quyết định commit/rollback. Không gọi acknowledge hoặc tự commit session nếu container quản lý session.

### 17.3. SOAP endpoint trả trạng thái đã persist

~~~java
@Endpoint
public class SubmitOrderEndpoint {

    private final OrderApplicationService service;

    public SubmitOrderEndpoint(OrderApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "SubmitOrderRequest"
    )
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {
        return service.accept(request);
    }
}
~~~

service.accept() nên validate, authorize, lưu business state và outbox trong DB transaction. Relay publish sau commit. Response nói ACCEPTED/request ID, không nói COMPLETED khi worker chưa xong.

## 18. SOAP Fault và lỗi bất đồng bộ

Lỗi trước acceptance có thể trả SOAP Fault đồng bộ: XML/XSD invalid, WS-Security failure, authorization denied, request ID conflict hoặc DB không persist được.

Sau acceptance, business failure thường không thể trả bằng HTTP response ban đầu vì response đã kết thúc. Cần status update, callback Fault/event hoặc status query.

Callback SOAP phải được bảo vệ bằng TLS/WS-Security theo policy, xác minh signer, Action, QName, correlation và idempotency. Callback gửi lại phải an toàn; HTTP callback ACK không thay business completion record.

## 19. Monitoring và vận hành

| Metric | Ý nghĩa |
|---|---|
| Queue depth/oldest message age | Backlog và độ trễ |
| Consumer delivery/ACK rate | Throughput |
| Redelivery count | Mức retry/lỗi |
| DLQ count | Messages không xử lý bình thường |
| Outbox pending age | Event chờ publish |
| Inbox duplicate count | Tần suất duplicate |
| Business completion latency | Acceptance đến kết quả |
| UNKNOWN/reconciliation count | Outcome chưa xác định |
| Partner SOAP timeout/Fault | Tình trạng partner |

Tách transport success khỏi business success:

~~~text
jms_publish_result = accepted
jms_consumer_result = acknowledged
business_operation_state = processing
~~~

Giữ correlation ID end-to-end và propagate trace context theo policy. Không log raw SOAP/JMS payload, WS-Security tokens, credentials hoặc dữ liệu cá nhân.

## 20. Kiểm thử transaction boundaries và crash windows

Integration tests nên dùng broker/DB thật hoặc Testcontainers/provider phù hợp. Các ca:

1. Listener xử lý thành công, DB và JMS commit.
2. DB fail trước commit → JMS rollback/redelivery theo policy.
3. DB commit thành công nhưng JMS commit fail → Inbox nhận diện duplicate.
4. Relay publish thành công nhưng crash trước mark-published → duplicate không lặp side effect.
5. Broker unavailable → relay retry.
6. Partner commit nhưng SOAP response timeout → UNKNOWN/reconciliation, không charge lại mù.
7. Consumer crash sau DB commit trước ACK → redelivery idempotent.
8. Poison message vượt retry limit → DLQ/alert.
9. Duplicate event ID → không áp business effect lần hai.
10. Cùng business idempotency key nhưng JMS ID khác → không chạy command lần hai.
11. Event sai thứ tự → version/gap policy phát hiện.
12. Callback/completion event gửi hai lần → Inbox xử lý.
13. XA coordinator restart với prepared transaction → recovery đúng.
14. SOAP Fault trước acceptance khác async failure sau acceptance.
15. Status API trả đúng state sau restart/reconciliation.

### 20.1. DB failure test

Assert DB/Inbox rows rollback, JMS receive transaction rollback nếu transacted, message được redeliver theo broker policy và không có side effect ngoài transaction.

### 20.2. DB commit nhưng ACK thất bại

Redelivery không được tạo side effect lần hai. Kiểm unique constraint, Inbox và business state cuối.

### 20.3. Partner timeout sau commit

Fake partner commit side effect nhưng không trả response. Consumer giữ UNKNOWN/reconciliation, query bằng idempotency key và không gửi command tạo side effect lần hai.

## 21. Chọn transaction pattern

| Pattern | Atomicity | Duplicate/loss handling | Khi phù hợp |
|---|---|---|---|
| Local JMS transaction | JMS session resources | Redelivery theo broker | JMS send/receive |
| Local DB transaction | DB resources | Không tự phối hợp broker | Persist business state |
| XA/JTA | XA resources được enlist | Coordinator/recovery; vẫn cần business idempotency | Atomicity DB + JMS |
| Outbox + relay | Business state + publish intent atomic trong DB | Relay có thể duplicate | Async integration |
| Inbox + idempotent consumer | Inbox identity + DB effect atomic trong DB | JMS ACK riêng theo wiring | At-least-once consumers |
| Saga | Không atomic toàn workflow; compensation | Retry/reconciliation từng bước | Nhiều remote services |
| Synchronous SOAP | Request/response trong timeout window | Timeout ambiguity | Operation ngắn |

Chọn theo consistency, throughput, partner capability, failure handling và vận hành.

## 22. Bài thực hành: SubmitOrder qua SOAP, JMS và partner SOAP

~~~text
SOAP client
  -> Spring-WS SubmitOrderEndpoint
  -> DB Order + Outbox
  -> Outbox relay
  -> JMS orders.in
  -> Order worker
  -> Partner WebServiceTemplate
  -> Partner SOAP service
  -> Completion event/status
~~~

### Nhiệm vụ

1. Thiết kế XSD/WSDL cho SubmitOrder request và acceptance response.
2. Acceptance response có request ID và status ACCEPTED.
3. Tạo Order và Outbox event trong cùng DB transaction.
4. Relay publish JMS event có stable event ID/correlation ID.
5. Cấu hình listener container và transaction semantics rõ ràng.
6. Tạo Inbox table với unique constraint theo event ID.
7. Xây consumer idempotent.
8. Gọi partner SOAP bằng WebServiceTemplate và idempotency key nếu partner hỗ trợ.
9. Phân biệt timeout, business rejection và completion.
10. Cung cấp status endpoint hoặc SOAP query operation.
11. Cấu hình retry/backoff/DLQ theo failure categories.
12. Mô phỏng crash tại các commit boundaries.
13. Test duplicate JMS message và duplicate business command.
14. Test partner commit nhưng response bị mất.
15. Test compensation khi một bước workflow thất bại.
16. Theo dõi queue age, outbox pending, redelivery, DLQ và completion latency.
17. Ghi API/event nào xác nhận accepted và API/event nào xác nhận completed.

**Tiêu chí đạt:** JMS ACK không bị hiểu là business completion; producer không mất command khi DB commit; duplicate không lặp side effect; remote timeout được reconcile; transaction boundaries quan sát được.

### 22.1. Câu hỏi tình huống

**A:** Listener ghi DB thành công nhưng process chết trước JMS commit. Message được redeliver. Inbox làm gì để không cập nhật nghiệp vụ lần hai?

**B:** A commit Outbox và trả ACCEPTED. Worker gọi B; B commit payment nhưng response timeout. A nên làm gì trước retry?

**C:** JTA transaction DB/JMS commit thành công nhưng downstream SOAP partner chưa xử lý event. Vì sao chưa thể tuyên bố business operation completed?

## 23. Checklist trước khi triển khai

- [ ] Định nghĩa riêng JMS ACK, JMS commit, DB commit và business confirmation.
- [ ] Chọn acknowledgement mode/session transaction phù hợp.
- [ ] Xác định transaction manager của listener container.
- [ ] Không giả định @Transactional bao trùm DB, JMS và remote SOAP.
- [ ] Tài liệu hóa local boundaries và crash windows.
- [ ] Chỉ dùng XA khi resources hỗ trợ/enlist và có recovery plan.
- [ ] Outbox lưu business state và publish intent trong cùng DB transaction.
- [ ] Inbox có unique constraint và consumer idempotent.
- [ ] Có stable event ID, correlation ID và business idempotency key.
- [ ] Retry có backoff/jitter, max attempts và phân loại lỗi.
- [ ] Có DLQ, alert, audit và replay process.
- [ ] Không retry side-effecting SOAP call mù quáng sau timeout.
- [ ] Có UNKNOWN/reconciliation và status query/callback.
- [ ] SOAP acceptance không tuyên bố completed sớm.
- [ ] Event schema/WSDL contracts có versioning.
- [ ] Callback/TLS/WS-Security được xác thực.
- [ ] Có integration tests cho DB failure, JMS rollback, duplicate và crash windows.
- [ ] Test partner commit nhưng response mất và compensation failure.
- [ ] Monitoring tách transport metrics khỏi business completion.
- [ ] Logs không chứa secrets/raw payload nhạy cảm.

## 24. Ghi nhớ

- **JMS ACK xác nhận message theo broker/session semantics**, không tự xác nhận DB commit hay nghiệp vụ từ xa.
- **Local JMS transaction và local DB transaction độc lập** nếu không được phối hợp.
- **XA/JTA chỉ điều phối resources được enlist**, không tự bao trùm HTTP SOAP partners.
- **Remote SOAP side effect không thể rollback bằng local transaction**; timeout tạo outcome chưa chắc chắn.
- **Outbox** làm business state và publish intent atomic trong DB; relay có thể gửi duplicate.
- **Inbox/idempotency** ngăn duplicate delivery/command gây side effect lần hai.
- **At-least-once + idempotent processing + reconciliation** thực tế hơn exactly-once toàn hệ thống.
- **Retry/DLQ** cần backoff, alert và replay có audit.
- **HTTP 202/SOAP Accepted** là acceptance; business completion cần state/event/callback.
- **Saga/compensation** xử lý workflow nhiều services; compensation là business action mới, không phải rollback toàn cục.

**Câu hỏi tự kiểm tra:** Spring-WS endpoint ghi Order và Outbox trong DB transaction rồi trả SOAP ACCEPTED. Relay gửi JMS event; consumer gọi partner SOAP ChargePayment. Partner đã charge và commit nhưng response timeout. Consumer rollback JMS session khiến event redeliver. Hãy giải thích vì sao JMS rollback không rollback charge của partner, thiết kế idempotency/reconciliation tránh charge lần hai, phân biệt ACK/DB commit/business completed và nêu vai trò Outbox/Inbox hoặc Saga.

## 25. Tài liệu tham khảo để đối chiếu

- Jakarta Messaging API/specification: acknowledgement modes, transacted sessions và delivery semantics.
- Spring Framework reference: transaction management và transaction manager selection.
- Spring Framework reference: JMS listener containers, JmsTemplate và listener transaction behavior.
- Spring Boot reference: JMS auto-configuration và listener factory.
- Spring Web Services reference: WebServiceTemplate, SOAP transports và interceptors.
- Broker/database provider documentation: XA support, JTA enlistment, redelivery, DLQ và recovery.

Defaults/property names có thể thay đổi giữa Spring, Jakarta Messaging provider và broker versions. Đối chiếu dependency đã pin và chạy integration tests trên broker/database thực tế; không suy behavior production chỉ từ in-memory mock.

