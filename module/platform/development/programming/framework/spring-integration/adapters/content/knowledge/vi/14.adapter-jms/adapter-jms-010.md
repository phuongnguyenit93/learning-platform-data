# Session acknowledgment và transaction trong JMS

## 1. Tại sao việc xác nhận message lại quan trọng?

Một hệ thống ERP gửi đơn hàng vào JMS queue `orders.in`. Ứng dụng Spring Integration nhận message, kiểm tra JSON rồi lưu đơn vào PostgreSQL. Nếu database đang lỗi, điều gì xảy ra với message vừa được nhận?

- Nếu **broker đã coi message được xác nhận (acknowledged)**, message có thể bị loại khỏi queue dù đơn hàng chưa được lưu.
- Nếu **JMS session bị rollback**, broker có thể giao lại message khi consumer thử nhận tiếp.
- Nếu database đã commit nhưng JMS session chưa commit và ứng dụng gặp sự cố, cùng message có thể đến lại, dẫn tới nguy cơ **ghi trùng**.

Do đó phải phân biệt ba mốc: **nhận JMS message**, **hoàn thành nghiệp vụ** và **acknowledge/commit tại broker**. Chỉ khi hiểu thứ tự và ranh giới của chúng, ta mới cấu hình được một luồng đáng tin cậy.

Trong module **SPRING_INTEGRATION_ADAPTERS**, các inbound/outbound adapter, gateway, poller và `MessageChannel` kết nối hệ thống ngoài qua file, SFTP, HTTP, JMS, AMQP, Kafka và database. Với JMS, chủ đề **Session acknowledgment và transaction** quyết định khi nào một lần nhận/gửi được coi là hoàn tất, khi nào rollback, và lỗi của integration flow có đi ngược về broker hay không.

Sau bài học, bạn cần có thể:

1. Phân biệt JMS acknowledgment với commit/rollback của một JMS transaction.
2. Lựa chọn `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, `DUPS_OK_ACKNOWLEDGE` hoặc session transacted theo yêu cầu.
3. Cấu hình message-driven listener và transactional poller trong Spring Integration.
4. Hiểu `JmsTransactionManager`, xử lý exception xuyên `DirectChannel` và ranh giới của `ExecutorChannel`.
5. Thiết kế idempotency, retry, DLQ và outbox khi JMS phối hợp với database.

## 2. Đường đi của một JMS message và ba mức thành công

~~~mermaid
sequenceDiagram
    participant Broker as JMS broker
    participant Container as Listener container
    participant Adapter as JMS inbound adapter
    participant Handler as Spring Integration handler
    participant DB as PostgreSQL

    Broker->>Container: JMS message
    Container->>Adapter: Callback nhận message
    Adapter->>Handler: Spring Message qua DirectChannel
    Handler->>DB: Ghi dữ liệu trong DB transaction
    DB-->>Handler: DB commit hoặc exception
    Handler-->>Adapter: Thành công hoặc exception
    Adapter-->>Container: Callback kết thúc / ném lỗi
    Container->>Broker: JMS acknowledge, commit hoặc rollback
~~~

Sơ đồ mô tả đường **xử lý đồng bộ**. Với một số acknowledgment mode, broker có thể được xác nhận **trước** khi handler thực thi; chi tiết tùy listener container và cấu hình.

| Mốc | Điều đã xảy ra | Điều chưa được bảo đảm |
|---|---|---|
| **Delivered/received** | Broker giao message tới consumer | Handler chưa chắc xử lý thành công |
| **Business completed** | Handler có thể đã hoàn thành và DB commit | Broker chưa chắc commit thao tác JMS |
| **Acknowledged/committed** | Provider đánh dấu nhận thành công theo session | Không chứng minh một DB/HTTP/Kafka downstream khác đã hoàn thành |

**Ack và commit không đồng nghĩa.** Trong session **không transacted**, acknowledgment mode quy định cách xác nhận message đã nhận. Trong session **transacted**, `Session.commit()` hoặc `Session.rollback()` điều khiển các JMS operation thuộc transaction; không sử dụng `Message.acknowledge()` thay cho commit.

### JMS Session và trách nhiệm quản lý tài nguyên

`jakarta.jms.Session` là ngữ cảnh làm việc với JMS message, producer và consumer. Session thường **không an toàn để nhiều thread dùng đồng thời**. Spring quản lý tài nguyên thay ứng dụng:

- `JmsTemplate` lấy/tạo session cho `send()`, `receive()` hoặc tham gia một JMS transaction đang hoạt động.
- `DefaultMessageListenerContainer` tạo listener task và JMS consumer/session để nhận liên tục từ broker.
- `ConnectionFactory` cung cấp kết nối theo JMS provider; có thể được bọc bằng caching/pooling nhưng không tự quyết định business commit.
- `MessageChannel` vận chuyển Spring Message trong ứng dụng, **không phải** JMS session hay transaction manager.

Khi một listener container có bốn consumer, mỗi listener task hoạt động với tài nguyên JMS phù hợp; **không có một session/transaction duy nhất bao trùm mọi message đang xử lý trên cả bốn consumer**.

## 3. Các JMS acknowledgment mode

JMS định nghĩa các mode dùng cho **session không transacted**. Cần phân biệt semantics API JMS với cách Spring listener container thực thi callback.

| Chế độ | Mục tiêu | Lưu ý về độ tin cậy |
|---|---|---|
| `Session.AUTO_ACKNOWLEDGE` | Provider/container tự xác nhận | Với `DefaultMessageListenerContainer`, acknowledgement có thể xảy ra trước khi listener chạy; exception handler không bảo đảm redelivery |
| `Session.CLIENT_ACKNOWLEDGE` | Xác nhận thông qua `Message.acknowledge()` hoặc container quản lý | Khi dùng Spring listener, có thể có **best-effort redelivery** sau lỗi; không tương đương transaction JMS |
| `Session.DUPS_OK_ACKNOWLEDGE` | Cho phép provider trì hoãn/gộp xác nhận | Có thể phát lại message; phải chịu được duplicate |
| **Session transacted** | JMS `commit()` / `rollback()` quyết định kết quả | Rollback có thể dẫn đến redelivery; chỉ bao trùm các thao tác của transaction JMS |

Một số JMS provider có mode mở rộng như **INDIVIDUAL_ACKNOWLEDGE**; đây không phải tính năng di động chung của Jakarta JMS. Không viết bài toán phụ thuộc mode này nếu chưa kiểm tra provider và version.

### 3.1. `AUTO_ACKNOWLEDGE`: vì sao dễ mất message khi handler lỗi?

Với `DefaultMessageListenerContainer` (DMLC), Spring Framework lưu ý việc xác nhận có thể diễn ra **trước khi listener thực thi**. Vì vậy:

~~~text
Broker giao message
    -> DMLC xác nhận theo AUTO_ACKNOWLEDGE
    -> Handler gọi database
    -> Database timeout, handler ném exception
    -> JMS message có thể KHÔNG được redeliver
~~~

`SimpleMessageListenerContainer` dùng callback do JMS provider kích hoạt và có những chi tiết khác với DMLC, nhưng AUTO_ACK không phải lựa chọn đáng tin cậy khi yêu cầu xử lý queue nghiệp vụ quan trọng. Đừng giả định JMS provider tự biết rằng handler downstream thất bại nếu container không đưa lỗi tới ranh giới xác nhận.

### 3.2. `CLIENT_ACKNOWLEDGE` và phạm vi của `acknowledge()`

Trong JMS thuần, callback có thể chủ động:

~~~java
// Minh họa trong JMS listener tự quản lý session.
void onMessage(jakarta.jms.Message message) throws jakarta.jms.JMSException {
    processBusiness(message);
    message.acknowledge();
}
~~~

Với `CLIENT_ACKNOWLEDGE` chuẩn, `Message.acknowledge()` xác nhận **các message đã được session tiêu thụ**, không nhất thiết chỉ riêng message hiện tại. Vì vậy không lưu JMS Message rồi gọi `acknowledge()` từ thread khác khi session/container đã quản lý vòng đời xử lý.

Spring listener container có thể chủ động acknowledge sau callback thành công, thay vì yêu cầu handler của Spring Integration gọi `acknowledge()`. Với DMLC, mode này có thể hỗ trợ redelivery theo kiểu **best effort** khi callback ném exception; tuy nhiên độ tin cậy vẫn phụ thuộc provider và thời điểm lỗi.

### 3.3. `DUPS_OK_ACKNOWLEDGE`

Provider được phép trì hoãn acknowledgment để tối ưu thông lượng. Đổi lại, việc nhận lặp là tình huống phải được chấp nhận. Đây không phải giải pháp bảo đảm xử lý chính xác một lần cho đơn hàng, thanh toán hoặc dữ liệu có tác động bên ngoài.

### 3.4. `sessionTransacted=true`: không dùng acknowledge mode để thay commit

Khi session transacted, các thao tác gửi/nhận JMS được quyết định bởi **commit** hoặc **rollback**. Cờ `sessionTransacted` và transaction manager mới là điểm chính cần cấu hình, không phải chọn `CLIENT_ACKNOWLEDGE` song song rồi giả định callback sẽ commit đúng lúc.

Lưu ý: **redelivery không tự bảo đảm business effect exactly-once**. Transaction JMS chỉ quản lý tài nguyên JMS, không tự commit nguyên tử với PostgreSQL.

## 4. Mặc định của message-driven adapter và listener container

Một nguồn nhầm lẫn quan trọng: **DMLC thuần** và **message-driven channel adapter do Spring Integration tự tạo container** có thể có **default transaction khác nhau**.

Từ **Spring Integration 4.2**, message-driven channel adapter mặc định dùng `acknowledge="transacted"` **khi adapter tự tạo container**. Nếu đưa **container bên ngoài** vào, người viết ứng dụng phải tự cấu hình transaction/acknowledgment trên chính container đó. Với DMLC, Spring Integration khuyến nghị dùng transacted để hạn chế mất message.

| Kiểu endpoint | Nơi đặt cấu hình | Điểm cần nhớ |
|---|---|---|
| `Jms.messageDrivenChannelAdapter(connectionFactory)` | DSL `configureListenerContainer(...)` hoặc XML adapter | Adapter tạo listener container và có default transacted |
| `Jms.messageDrivenChannelAdapter(externalContainer)` | Bean `DefaultMessageListenerContainer` | Không suy ra default transacted từ adapter |
| `DefaultMessageListenerContainer` độc lập | `setSessionTransacted(true)`/transaction manager trực tiếp | Phải kiểm tra default của Spring JMS |
| `SimpleMessageListenerContainer` | Session mode/transaction của chính container | Không hỗ trợ external transaction theo cách DMLC hỗ trợ |

### 4.1. Java DSL dùng listener container transacted

Ví dụ với Spring Integration 6+, Java 17+ và Jakarta JMS; giả định broker có queue `orders.in` và ứng dụng có bean `ConnectionFactory` kết nối được:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
@EnableIntegration
public class OrderInboundJmsConfiguration {

    @Bean
    public DefaultMessageListenerContainer orderListenerContainer(
            ConnectionFactory connectionFactory) {
        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.in");
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setSessionTransacted(true);
        return container;
    }

    @Bean
    public IntegrationFlow orderInboundFlow(
            DefaultMessageListenerContainer orderListenerContainer,
            OrderImportService orderImportService) {
        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(orderListenerContainer))
                .handle(String.class, (json, headers) -> {
                    orderImportService.importOrder(json);
                    return null;
                })
                .get();
    }
}
~~~

`OrderImportService` là service nghiệp vụ do ứng dụng triển khai. Handler giữ **đường đồng bộ**, trả `null` vì inbound channel adapter là một chiều. Với `TextMessage`, `SimpleMessageConverter` thông thường tạo payload `String`; nếu producer gửi dữ liệu khác, cần converter/handler tương thích.

Khi handler ném exception và không có error flow hấp thụ lỗi, listener container có thể rollback JMS session. Khi callback hoàn thành bình thường, container có thể commit. **Nếu nhiều bean listener container cùng kiểu**, nên dùng `@Qualifier` để tránh injection mơ hồ.

Container được khai báo riêng có lifecycle Spring riêng; hãy kiểm tra việc gắn listener, start/stop và không sử dụng cùng một container cho hai endpoint khác nhau ngoài chủ ý.

### 4.2. Java DSL để adapter tự tạo container

~~~java
IntegrationFlow.from(
        Jms.messageDrivenChannelAdapter(connectionFactory)
                .destination("orders.in")
                .configureListenerContainer(container ->
                        container.sessionTransacted(true)
                                .concurrentConsumers(2)
                                .maxConcurrentConsumers(4)))
        .handle(String.class, (json, headers) -> {
            orderImportService.importOrder(json);
            return null;
        })
        .get();
~~~

Đây là fragment trong `@Bean` method đã có `connectionFactory` và `orderImportService`. Đây là **phương án thay thế** cho mục 4.1, không nên đăng ký cả hai cùng nhận `orders.in` chỉ để xử lý một tập công việc logic.

### 4.3. XML namespace

~~~xml
<int:channel id="ordersInput"/>

<int-jms:message-driven-channel-adapter
        id="ordersInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.in"
        channel="ordersInput"
        acknowledge="transacted"
        concurrent-consumers="2"
        max-concurrent-consumers="4"/>

<int:service-activator
        input-channel="ordersInput"
        ref="orderImportService"
        method="importOrder"/>
~~~

Fragment XML cần khai báo namespace `int`/`int-jms`, các bean và handler tương ứng. Nếu cung cấp `container="..."` thì phải cấu hình transaction trên container được tham chiếu; đừng dựa vào các thuộc tính của adapter vốn chỉ áp dụng khi nó tạo container.

## 5. Tại sao polling inbound cần **transactional poller**?

Polling inbound adapter khác message-driven ở cách kích hoạt:

~~~text
Poller kích hoạt
    -> JmsTemplate.receive("orders.in")
    -> Lời gọi receive hoàn tất
    -> Adapter phát Spring Message lên channel
    -> Handler downstream xử lý
~~~

Nếu chỉ đặt `sessionTransacted=true` trên `JmsTemplate` khi **không có transaction bao quanh poll**, template có thể commit JMS ngay sau `receive()`, **trước khi** Spring Message được dispatch. Exception của handler lúc này **không rollback được** lần nhận JMS đã commit.

Muốn bao trùm phần lấy message và dispatch/handler đồng bộ, cần **transactional poller** với `JmsTransactionManager`.

### 5.1. Khai báo manager cho JMS resource

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.JmsTransactionManager;

@Bean("orderJmsTxManager")
public JmsTransactionManager orderJmsTxManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

`JmsTransactionManager` quản lý **local JMS transactions** cho một `ConnectionFactory`, gắn session tài nguyên với thread trong transaction; nó không tự mở transaction ở PostgreSQL.

### 5.2. Java DSL polling flow có transaction

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.connection.JmsTransactionManager;

@Bean
public IntegrationFlow orderPollingFlow(
        ConnectionFactory connectionFactory,
        JmsTransactionManager orderJmsTxManager,
        OrderImportService orderImportService) {

    return IntegrationFlow.from(
            Jms.inboundAdapter(connectionFactory)
                    .destination("orders.in")
                    .configureJmsTemplate(template ->
                            template.receiveTimeout(-1)),
            endpoint -> endpoint.poller(poller ->
                    poller.fixedDelay(5000)
                            .maxMessagesPerPoll(5)
                            .transactional(orderJmsTxManager)))
            .handle(String.class, (json, headers) -> {
                orderImportService.importOrder(json);
                return null;
            })
            .get();
}
~~~

- `fixedDelay(5000)` đặt lịch poll, **không phải** receive timeout.
- `receiveTimeout(-1)` khiến lần JMS receive không chờ khi queue rỗng.
- `maxMessagesPerPoll(5)` là giới hạn message lấy trong một lượt poll, **không phải** số consumer.
- `transactional(orderJmsTxManager)` tạo transaction advice bao quanh quá trình polling, cho phép lấy và dispatch **đồng bộ** nằm trong cùng JMS transaction.

Nếu flow đưa message vào `ExecutorChannel` hoặc `QueueChannel` trước handler, lỗi trong thread/consumer tiếp theo thường xảy ra **sau ranh giới transaction của poller** và không thể tự rollback JMS đã nhận.

Với JMS event liên tục và cần độ trễ thấp, message-driven inbound adapter là lựa chọn thường dùng; polling vẫn hữu ích khi có yêu cầu nghiệp vụ nhận theo lịch/batch.

## 6. `JmsTemplate` và transaction của outbound adapter

Transaction cũng áp dụng cho gửi JMS. Nếu muốn gửi hai message cùng commit/rollback trong một **JMS local transaction**, có thể dùng `JmsTransactionManager` cùng `JmsTemplate`:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JmsEventPublisher {
    private final JmsTemplate jmsTemplate;

    public JmsEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "orderJmsTxManager")
    public void publishPair(String firstEvent, String secondEvent) {
        jmsTemplate.convertAndSend("orders.events", firstEvent);
        jmsTemplate.convertAndSend("audit.events", secondEvent);
    }
}
~~~

Khi `@Transactional` thực sự có hiệu lực (method được gọi qua **Spring proxy**), và template/manager dùng cùng JMS `ConnectionFactory`, các send có thể tham gia cùng local transaction. Nếu lần gửi thứ hai ném exception và exception đi ra transaction boundary, manager có thể rollback các lần gửi thuộc transaction đó.

Những giới hạn quan trọng:

- **Self-invocation** trong cùng bean thường không kích hoạt proxy `@Transactional`.
- Dùng **ConnectionFactory khác** ở template và manager có thể khiến send không tham gia transaction mong muốn.
- Nếu không có transaction bên ngoài, bật `JmsTemplate.sessionTransacted=true` thường chỉ tạo local transaction cho **từng lệnh send/receive**; nó không tự gom hai lời gọi thành một transaction.
- JMS local transaction không tự commit đồng thời database, Kafka hoặc HTTP.

### Chuyển tiếp JMS → JMS trong cùng transaction

Trong luồng nhận `orders.in`, validate đồng bộ rồi gửi sang `orders.validated`, việc receive và send có thể thuộc cùng JMS transaction **nếu dùng chung tài nguyên và thread/session transaction tương thích**:

~~~text
Receive orders.in (transaction JMS)
    -> validate đồng bộ
    -> Send orders.validated (cùng transaction nếu cấu hình đúng)
    -> commit

Nếu handler ném exception trước commit:
    -> rollback thao tác nhận/gửi JMS
    -> broker có thể redeliver request ban đầu
~~~

Không suy ra hai endpoint chung `ConnectionFactory` đã tự chung transaction khi chúng chạy trên các thread khác nhau, connection/session tách biệt hoặc broker khác nhau. Cần thử thực tế trên provider được chọn.

## 7. Phân biệt JMS transaction và database transaction

Một flow nhận `OrderPaid` rồi cập nhật PostgreSQL có ít nhất **hai tài nguyên**:

1. **JMS transaction:** quyết định broker có coi message đã nhận hay còn khả năng redelivery.
2. **Database transaction:** quyết định dữ liệu trong PostgreSQL đã commit hay rollback.

~~~mermaid
flowchart TD
    A["Nhận JMS message evt-1001"] --> B["DB transaction BEGIN"]
    B --> C["Insert inbox key + cập nhật đơn hàng"]
    C --> D["DB COMMIT"]
    D --> E{"JMS COMMIT thành công?"}
    E -->|"Có"| F["Hoàn tất"]
    E -->|"Không"| G["Broker có thể redeliver"]
    G --> H["Nhận lại evt-1001"]
    H --> I["Idempotency ngăn tác động lặp"]
~~~

`JmsTransactionManager` quản lý transaction của `ConnectionFactory`. `DataSourceTransactionManager` quản lý database transaction. Chỉ thêm `@Transactional` hoặc `sessionTransacted(true)` **không tự tạo atomic commit giữa hai resource**. Nếu cần giao dịch phân tán, phải đánh giá JTA/XA và hỗ trợ thật của broker/database; hầu hết hệ thống chọn **at-least-once + inbox/outbox + idempotency**.

### 7.1. Idempotent consumer bằng unique key ở database

Giả sử handler nhận `OrderPaid(eventId=evt-1001, orderId=ORD-1001)`. Có thể tạo bảng `processed_event` để đánh dấu đã xử lý và ghi nó **trong cùng DB transaction** với tác động nghiệp vụ:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customer_order (
    order_id VARCHAR(100) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

Ví dụ service dùng PostgreSQL và Spring JDBC:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaidProcessor {
    private final JdbcTemplate jdbc;

    public OrderPaidProcessor(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "orderDbTxManager")
    public void markPaid(String eventId, String orderId) {
        int inserted = jdbc.update(
                "INSERT INTO processed_event(event_id) VALUES (?) "
                + "ON CONFLICT DO NOTHING", eventId);

        if (inserted == 0) {
            return; // Event đã xử lý; không ghi trùng.
        }

        int updated = jdbc.update(
                "UPDATE customer_order SET status = 'PAID' "
                + "WHERE order_id = ?", orderId);

        if (updated != 1) {
            throw new IllegalStateException("Order không tồn tại: " + orderId);
        }
    }
}
~~~

`orderDbTxManager` phải là bean transaction manager cho database được cấu hình trước, và code này **chỉ minh họa PostgreSQL** (`ON CONFLICT DO NOTHING`); database khác có cú pháp tương đương. Nếu update ném exception, **cả bản ghi `processed_event` lẫn cập nhật đơn** được rollback trong cùng transaction DB. Nếu một JMS message được broker redeliver sau khi DB đã commit, `inserted == 0` giúp bỏ qua tác động lặp.

Service cần được gọi qua Spring proxy để `@Transactional` có hiệu lực. Trước khi gọi, phải parse và validate JSON: `eventId` không rỗng, `orderId` hợp lệ, `schemaVersion` được hỗ trợ. Dùng `eventId` ổn định, không dùng `JMSMessageID` làm business idempotency key vì một sự kiện có thể được producer gửi lại dưới JMS message ID mới.

### 7.2. Hai cửa sổ lỗi quan trọng

| Trình tự | Điều có thể xảy ra | Cách xử lý |
|---|---|---|
| **DB commit → JVM crash → JMS commit chưa xảy ra** | Broker có thể redeliver event đã ghi DB | Unique `eventId`/inbox để bảo đảm không ghi lặp |
| **JMS ack/commit → handler async ghi DB thất bại** | Broker có thể không redeliver vì message đã được xác nhận | Không tách async nếu cần JMS bảo vệ; hoặc dùng durable handoff/retry riêng |
| **DB commit → gửi JMS event mới thất bại** | Hệ thống khác không biết dữ liệu đã đổi | Transactional outbox |
| **JMS send thành công → chưa đánh dấu outbox đã gửi** | Publisher có thể gửi lại cùng event | Consumer idempotent và event ID ổn định |

### 7.3. Transactional outbox cho chiều DB → JMS

~~~mermaid
flowchart LR
    A["Business service"] --> B["DB transaction: update order + insert outbox"]
    B --> C[("DB COMMIT")]
    C --> D["Outbox publisher"]
    D -->|"JMS outbound adapter"| E[("JMS broker")]
    D --> F["Đánh dấu SENT"]
~~~

Ghi trạng thái nghiệp vụ và event vào bảng outbox trong **cùng DB transaction**. Publisher riêng đọc outbox chưa gửi và chuyển qua JMS với retry/backoff. Việc đánh dấu outbox đã gửi **không atomic với broker commit** nếu chỉ dùng hai resource transactions thông thường, nên event có thể được gửi nhiều lần; consumer vẫn phải idempotent.

## 8. `errorChannel` và đường truyền exception

Spring Integration JMS message-driven adapter có thể chuyển exception vào `ErrorMessage` thông qua `errorChannel`. Điều đó hữu ích để log, cảnh báo và phân loại lỗi, nhưng **lỗi đã được một error flow xử lý bình thường có thể làm listener thấy callback thành công**.

~~~mermaid
flowchart TD
    A["JMS session transacted nhận message"] --> B["Converter / handler"]
    B --> C{"Có exception?"}
    C -->|"Không"| D["Listener kết thúc -> JMS COMMIT"]
    C -->|"Có"| E{"Lỗi có thoát về container?"}
    E -->|"Có"| F["JMS ROLLBACK -> broker redelivery"]
    E -->|"Không; error flow hấp thụ"| G["Listener có thể COMMIT"]
~~~

Từ Spring Integration 4.2, lỗi **conversion** ở JMS message-driven adapter/gateway cũng có thể đi vào error channel. Vì vậy chỉ đặt `try/catch` trong handler nghiệp vụ **không bắt được mọi lỗi**: lỗi có thể xảy ra trước khi Spring Message đến handler.

| Loại lỗi | Xử lý đề xuất | Muốn rollback JMS? |
|---|---|---|
| DB timeout, broker phụ thuộc tạm thời lỗi | Ném lại exception, backoff/retry có giới hạn | Thường có |
| JSON sai vĩnh viễn, schemaVersion lạ | Quarantine/DLQ, cảnh báo và quy trình sửa dữ liệu | Theo chính sách; tránh retry vô hạn |
| Business rule từ chối nhưng đã lưu kết quả từ chối an toàn | Kết thúc handler với trạng thái nghiệp vụ rõ ràng | Có thể không |
| Duplicate event đã commit trước đó | Idempotent handler bỏ qua và trả thành công | Không cần rollback |
| Lỗi ở thread async sau khi JMS đã commit | Retry/durable handoff độc lập | Không thể rollback JMS gốc |

**`errorChannel` không phải DLQ và không tự retry JMS.** Nếu muốn rollback, exception phải truyền tới **JMS transaction boundary**. Nếu muốn xác nhận một message không xử lý được, cần chủ động bảo đảm kết quả quarantine/ghi lỗi đã bền vững trước khi để callback kết thúc bình thường.

### Không nuốt exception tạm thời

~~~java
// Không nên làm nếu muốn broker redeliver khi DB thất bại:
try {
    orderImportService.importOrder(json);
} catch (Exception ex) {
    log.error("Import failed", ex);
    // Callback kết thúc bình thường: listener có thể commit JMS.
}
~~~

Trong đường xử lý đồng bộ, nếu cần rollback, hãy để exception truyền ra:

~~~java
try {
    orderImportService.importOrder(json);
} catch (org.springframework.dao.TransientDataAccessException ex) {
    log.warn("Temporary DB failure; allow JMS rollback", ex);
    throw ex;
}
~~~

Các đoạn code là ví dụ trong handler đã có `log` và service; error flow thực tế cũng phải xử lý exception đúng cách. Không nhất thiết mọi lỗi đều nên redeliver; chính sách cần dựa trên tính tạm thời hay vĩnh viễn của lỗi.

## 9. Redelivery, poison message và dead-letter queue

Khi một JMS transaction rollback, broker có thể **phát lại message** theo policy. JMS metadata có `JMSRedelivered`; property `JMSXDeliveryCount` có thể giúp quan sát số lần giao khi provider cung cấp. Nhưng đừng phụ thuộc vào việc mọi broker đánh số, delay và DLQ theo cùng cách.

~~~text
JMS receive -> exception -> rollback
                |
          broker redelivery
                |
       +--------+--------+
       |                 |
    Lỗi tạm thời     Lỗi vĩnh viễn
    (DB timeout)     (JSON sai schema)
       |                 |
    Retry/backoff     Retry giới hạn
       |                 |
    Thành công        DLQ/quarantine
~~~

### 9.1. At-least-once không phải exactly-once

Khi broker/provider, persistence và transaction được cấu hình phù hợp, ứng dụng có thể đạt mục tiêu **không mất message do lỗi tạm thời**, nhưng **cùng message có thể được nhận lại**. Đây là tinh thần **at-least-once delivery/processing attempt**. Cần inbox/idempotency để đạt **tác động nghiệp vụ không trùng**.

Không kết luận `JMSRedelivered=false` nghĩa là sự kiện nghiệp vụ chưa từng đến: producer có thể gửi lại cùng `eventId` dưới một JMS Message mới.

### 9.2. Poison message

Message sai schema vĩnh viễn có thể khiến listener rollback liên tục, làm queue nghẽn và log đầy. Hãy cấu hình:

1. **Max delivery attempts** hoặc ngưỡng retry.
2. **Redelivery delay/backoff** để giảm vòng lặp nóng.
3. **Dead-letter destination** khi vượt ngưỡng.
4. Quy trình sửa/replay có kiểm soát sau khi xác minh schema và idempotency.

Tên DLQ, policy retry và expiry phụ thuộc JMS broker. `orders.in.dlq` chỉ là tên minh họa; broker không tự sinh destination này hoặc tự biết thời điểm chuyển nếu chưa cấu hình.

### 9.3. Logging và quan sát

Nên log/metric khi có: `eventId`, JMS message ID, correlation ID, `JMSRedelivered`, số lần giao nếu provider cung cấp, queue name, loại exception, thời gian xử lý và trạng thái transaction. Không log thông tin mật hoặc nguyên payload chứa dữ liệu nhạy cảm.

## 10. Concurrency và ranh giới bất đồng bộ

### 10.1. Mỗi consumer có session/transaction riêng

`DefaultMessageListenerContainer` có thể chạy nhiều consumer cho queue. Ví dụ `concurrentConsumers=4` cho phép bốn listener task xử lý bốn message đồng thời. Một task rollback **không tự rollback transaction của các task khác**.

Khi nhiều message của cùng đơn phải xử lý theo thứ tự, tăng concurrency có thể làm `OrderUpdated(v2)` hoàn thành trước `OrderCreated(v1)`. Cần có chiến lược ordering/grouping hoặc `aggregateVersion` và optimistic locking trong DB.

### 10.2. `DirectChannel` giữ ranh giới đồng bộ

~~~text
JMS receive (transacted)
    -> inbound adapter
    -> DirectChannel
    -> validate + DB service
    -> return / exception
    -> JMS commit / rollback
~~~

Trong đường đồng bộ, exception còn có cơ hội đi ngược về listener container để điều khiển JMS rollback.

### 10.3. `ExecutorChannel`/`QueueChannel` tách transaction boundary

~~~text
JMS receive (transacted)
    -> inbound adapter
    -> ExecutorChannel / QueueChannel
    -> listener callback kết thúc -> JMS commit

        [thread khác]
             |
         DB handler
             |
         exception (sau JMS commit)
~~~

Việc chuyển Spring Message thành công sang channel bất đồng bộ **không có nghĩa** handler đã ghi DB thành công. Lỗi sau callback thường không thể rollback JMS request ban đầu. Nếu cần xử lý async, phải có **durable handoff** (queue/bảng công việc/inbox/outbox) và retry riêng; không chỉ thêm executor rồi mặc định message vẫn được bảo vệ bởi transaction của listener.

## 11. JMS gateway request-reply và transaction

JMS inbound gateway nhận một JMS request, đưa Spring request vào flow, chờ Spring reply rồi gửi JMS reply về `JMSReplyTo` hoặc reply destination dự phòng. Với listener transacted và xử lý đồng bộ, việc nhận và gửi reply có thể cùng JMS transaction khi dùng resource/session phù hợp.

~~~mermaid
sequenceDiagram
    participant Client as JMS client
    participant Broker as Broker
    participant Server as Inbound gateway
    participant Handler as Spring handler
    Client->>Broker: Request + JMSReplyTo
    Broker->>Server: JMS request trong listener session
    Server->>Handler: Spring request
    Handler-->>Server: Spring reply
    Server->>Broker: JMS reply
    Server->>Broker: JMS commit
    Broker-->>Client: Reply
~~~

**Business error reply** như `NOT_FOUND` có thể là một JMS reply hợp lệ khiến transaction commit. **Infrastructure exception** khi DB lỗi hoặc khi gửi reply có thể dẫn đến rollback, còn client có thể gặp timeout. Nếu `errorChannel` biến exception thành một Spring reply lỗi rồi kết thúc bình thường, listener có thể coi callback thành công; đây là lựa chọn nghiệp vụ cần xác định rõ.

JMS outbound gateway là phía **gửi request và chờ reply**. Nếu caller timeout, không có bằng chứng server chưa xử lý request. Với lệnh ghi dữ liệu, retry phải giữ `requestId` ổn định và server phải idempotent.

## 12. Checklist thiết kế và bảng khắc phục sự cố

| Triệu chứng | Nguyên nhân cần xem | Cách xử lý |
|---|---|---|
| DB lỗi nhưng broker không redeliver | AUTO_ACK, lỗi bị nuốt hoặc async boundary | Dùng transacted listener/transactional poller và propagate exception |
| Đã ghi DB nhưng message đến lần nữa | JMS rollback/crash trước commit; producer gửi lại | Inbox/unique `eventId` |
| Polling adapter mất message dù template transacted | Transaction commit ngay sau `receive()` | Dùng `JmsTransactionManager` trên poller |
| ErrorMessage được log nhưng queue giảm | Error flow hấp thụ exception | Ném lại nếu muốn rollback; xác nhận có chủ đích sau quarantine |
| Một message sai schema lặp mãi | Thiếu max attempts/DLQ | Backoff, retry giới hạn, DLQ và xử lý poison message |
| Bật 4 consumer rồi thứ tự sai | Multiple sessions xử lý cùng aggregate | Group/partition, version hoặc optimistic lock |
| JMS transaction đúng nhưng DB trùng | Hai resource commit riêng | Idempotent consumer/inbox |
| `@Transactional` không có tác dụng | Self-invocation hoặc sai manager | Gọi qua Spring proxy, chỉ rõ transaction manager |
| Hai JMS send không commit cùng nhau | Không dùng cùng local JMS transaction | Kiểm tra manager, factory và thread |
| Listener không redeliver như dự kiến | Container và acknowledge mode khác tưởng tượng | Xác định DMLC/SMLC, `sessionTransacted`, provider policy |

Những câu hỏi phải có câu trả lời trước khi đưa vào production: destination nào, producer/consumer có chung schema và `eventId` không; ai sở hữu JMS session; transaction kết thúc tại đâu; có channel async không; lỗi tạm thời/vĩnh viễn đi về đâu; redelivery/DLQ được cấu hình ở broker hay ứng dụng; số consumer/instance ảnh hưởng thứ tự thế nào; DB và JMS đồng bộ bằng chiến lược nào.

## 13. Bài thực hành: từ mất message đến xử lý an toàn

**Môi trường:** broker JMS thử nghiệm, queue `orders.in`, Spring Integration và PostgreSQL. Producer gửi `TextMessage` JSON:

~~~json
{
  "eventId": "evt-1001",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-1001"
}
~~~

Những bài về acknowledgment/redelivery phải thực hiện với JMS provider thật hoặc test container phù hợp. Mock `JmsTemplate` không chứng minh được broker đã persist, rollback hay chuyển DLQ.

### Bài A — So sánh các acknowledge mode

1. Tạo DMLC dùng `AUTO_ACKNOWLEDGE`, `sessionTransacted=false`. Cho handler ném exception sau khi nhận.
2. Quan sát queue depth và xem broker có redeliver không; không dự đoán từ việc handler ném lỗi đơn thuần.
3. Chuyển sang `CLIENT_ACKNOWLEDGE` và so sánh best-effort redelivery khi listener lỗi.
4. Bật `sessionTransacted=true`; ném exception đồng bộ và quan sát rollback/redelivery theo broker.
5. Gửi lại một JMS message mới cùng `eventId`; kiểm tra sự khác biệt giữa JMS redelivery và producer duplicate.

### Bài B — Transactional poller

1. Tạo polling adapter, chỉ bật `sessionTransacted=true` trên template nhận, cho handler ném exception.
2. Giải thích vì sao `receive()` có thể đã commit trước khi handler thất bại.
3. Chuyển sang transactional poller với `JmsTransactionManager`, giữ `DirectChannel`.
4. Lặp lại lỗi và quan sát broker redelivery.
5. Chèn `ExecutorChannel`, kiểm tra lỗi downstream có còn khiến poller rollback được không.

### Bài C — JMS + DB và idempotency

1. Tạo bảng `processed_event` và `customer_order`.
2. Cho handler cập nhật order và ghi `eventId` trong cùng DB transaction.
3. Mô phỏng DB đã commit nhưng lỗi xảy ra trước JMS commit.
4. Khi broker redeliver, xác nhận không có tác động nghiệp vụ lặp.
5. Gửi lại sự kiện bằng một JMS Message mới cùng `eventId` và lặp xác minh.

### Bài D — Poison message và DLQ

1. Gửi JSON không hợp lệ hoặc `schemaVersion` chưa hỗ trợ.
2. Với listener transacted, quan sát rollback và redelivery.
3. Cấu hình error channel chỉ log rồi không ném lại; đối chiếu trường hợp listener commit.
4. Thử cơ chế propagate exception, retry giới hạn/backoff và chuyển DLQ theo policy broker.
5. Sửa payload và replay có kiểm soát; đảm bảo idempotency vẫn có hiệu lực.

### Bài E — Transaction của JMS outbound

1. Cấu hình `JmsEventPublisher.publishPair(...)` với `@Transactional(transactionManager="orderJmsTxManager")`.
2. Cho lần send thứ hai ném exception, kiểm tra rollback cùng JMS transaction.
3. Thử gọi service qua Spring proxy và self-invocation để thấy sự khác biệt.
4. Bổ sung một DB update trong method khác và giải thích vì sao local JMS transaction không atomic với DB.
5. Thiết kế outbox để có thể retry event sau khi DB đã commit.

### Câu hỏi tự đánh giá

1. Phân biệt **JMS acknowledge** với **database commit**.
2. Vì sao AUTO_ACK trên DMLC không bảo đảm redelivery khi handler lỗi?
3. `Message.acknowledge()` ở CLIENT_ACK chỉ xác nhận message hiện tại hay có thể xác nhận nhiều message đã nhận trên session?
4. Khi session transacted, thao tác nào quyết định JMS commit/rollback?
5. Vì sao Spring Integration message-driven adapter và DMLC tự tạo có thể có default khác nhau?
6. Vì sao chỉ đặt `sessionTransacted=true` cho `JmsTemplate` trong polling adapter không bảo vệ handler downstream?
7. Điều kiện nào để `JmsTransactionManager` bao trùm hai JMS send?
8. Khi DB commit thành công nhưng JMS rollback, cơ chế nào giúp không ghi trùng?
9. Error flow nuốt exception có thể ảnh hưởng transaction như thế nào?
10. `ExecutorChannel` thay đổi transaction boundary của JMS inbound ở điểm nào?
11. Vì sao `JMSRedelivered` không thay thế `eventId`?
12. Message sai schema vĩnh viễn nên được xử lý thế nào để không gây bão retry?

## 14. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): transaction của polling inbound, default transacted của message-driven adapter, error channel và conversion errors.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): các listener containers, acknowledge modes, transaction management và `JmsTemplate`.
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): lifecycle, acknowledge mode, concurrency và `sessionTransacted`.
- [Spring Framework API — JmsTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html): JMS local transaction gắn với `ConnectionFactory`.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transaction advice, poller và transaction boundary trong integration flow.

**Ghi nhớ:** acknowledgment quyết định **broker có coi lần nhận đã hoàn tất hay không**, còn JMS transaction cho phép commit/rollback các thao tác của session liên quan. Trong Spring Integration, hãy đặt transaction **đúng endpoint và đúng ranh giới đồng bộ**: transacted listener cho message-driven, transactional poller cho polling, và `JmsTransactionManager` cho các JMS operation cần chung transaction. Vì JMS transaction không tự atomic với database, tính tin cậy thực tế còn phụ thuộc idempotency, inbox/outbox, retry có giới hạn và DLQ.

