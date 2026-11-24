# Message-driven container và concurrency

## 1. Bài toán: nhận JMS liên tục và xử lý nhiều message cùng lúc

Một hệ thống bán hàng chuyển đơn hàng từ ERP vào JMS queue `orders.in`. Lúc bình thường chỉ có vài message mỗi giây, nhưng vào giờ cao điểm có hàng nghìn đơn cùng đến. Nếu chỉ một consumer xử lý từng message, queue có thể tồn đọng; nếu tăng số consumer thiếu kiểm soát, database và các dịch vụ downstream lại bị quá tải hoặc sự kiện cùng đơn bị xử lý sai thứ tự.

Trong **Spring Integration**, một **JMS message-driven inbound channel adapter** dùng **message listener container** của Spring JMS để nhận từ broker và đẩy vào `MessageChannel`. **Concurrency** là số consumer/listener có thể nhận và xử lý message đồng thời. Hai khái niệm này quyết định độ trễ, throughput, sử dụng thread/connection, thứ tự xử lý và khả năng rollback.

Module **SPRING_INTEGRATION_ADAPTERS** hướng đến kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, đồng thời xử lý hợp đồng message, lỗi và vòng đời kết nối cho JMS cùng các công nghệ như file, SFTP, HTTP, AMQP, Kafka, database. Bài này tập trung vào **message-driven container và concurrency trong JMS**; các nguyên lý giao nhận, backpressure và idempotency cũng hữu ích khi thiết kế các adapter khác.

Mục tiêu học tập:

1. Giải thích listener container nhận message và kích hoạt integration flow thế nào.
2. Phân biệt `DefaultMessageListenerContainer`, `SimpleMessageListenerContainer` và polling inbound adapter.
3. Cấu hình `concurrentConsumers`, `maxConcurrentConsumers`, task executor và transaction.
4. Hiểu tác động của concurrency với queue, topic, ordering, broker prefetch và downstream.
5. Thiết kế phép đo throughput/backlog, khôi phục kết nối và xử lý lỗi khi chạy production.

## 2. Container nằm ở đâu trong luồng Spring Integration?

~~~mermaid
flowchart LR
    P["ERP / Producer"] -->|"JMS TextMessage"| Q[("Broker queue orders.in")]
    subgraph C["Spring JMS Listener Container"]
        C1["Consumer 1"]
        C2["Consumer 2"]
        C3["Consumer N"]
    end
    Q --> C1
    Q --> C2
    Q --> C3
    C1 --> A["JMS message-driven inbound adapter"]
    C2 --> A
    C3 --> A
    A -->|"Spring Message"| M["MessageChannel"]
    M --> H["Validate + nhập đơn"]
    H --> DB[("Database")]
~~~

Các bước với một JMS request/event:

1. Listener container lấy `ConnectionFactory`, mở JMS connection/session/consumer và quản lý các tài nguyên đó.
2. Broker giao JMS message cho một consumer trên queue. `DefaultMessageListenerContainer` (DMLC) thực hiện vòng lặp nhận JMS ở các listener task; khi có message, nó gọi listener đã đăng ký.
3. Adapter chuyển JMS message thành Spring Message theo converter/header mapper, sau đó gửi vào `MessageChannel`.
4. Handler xử lý nghiệp vụ. Khi dùng `DirectChannel`, handler thường chạy **trên cùng thread** với lần gọi listener.
5. Listener container thực hiện acknowledge hoặc commit/rollback JMS session theo cấu hình, rồi tiếp tục nhận message.

**Message-driven ở đây nói về cách kích hoạt Spring Integration endpoint:** hạ tầng listener luôn sẵn sàng, không cần một `PollerMetadata` của integration flow gọi `JmsTemplate.receive()` theo `fixedDelay`. Bản thân DMLC có thể dùng các lệnh JMS `MessageConsumer.receive()` trong một vòng lặp nội bộ; điều đó **không biến endpoint thành Spring Integration polling inbound adapter**.

### Trách nhiệm của các thành phần

| Thành phần | Việc đảm nhiệm | Điểm cần kiểm tra |
|---|---|---|
| `ConnectionFactory` | Cấp JMS connection/session qua provider | Broker URL, quyền truy cập, cache/pool, recovery |
| `DefaultMessageListenerContainer` | Nhận message, giữ consumer, scale số listener task, transaction/recovery | Concurrency, TaskExecutor, timeout nhận, cache level |
| `ChannelPublishingJmsMessageListener` | Chuyển JMS message thành Spring Message và gửi vào channel | Payload converter, header mapper, error handling |
| `JmsMessageDrivenEndpoint` | Gắn listener và container vào lifecycle của Spring Integration | Start/stop, shutdown container |
| `MessageChannel` | Chuyển message cho consumer của integration flow | Đồng bộ (`DirectChannel`) hay bất đồng bộ (`ExecutorChannel`/`QueueChannel`) |
| Handler/service | Thực hiện nghiệp vụ và báo lỗi | Timeout, idempotency, transaction DB |
| Broker | Phân phối, redelivery, giữ backlog | Queue depth, prefetch, DLQ, TTL, ACL |

Một message-driven inbound **channel adapter** là đầu vào **một chiều**; nó không trả reply cho producer. Khi client JMS yêu cầu request-reply, dùng **JMS inbound gateway**. Cả hai có thể dùng listener container, nhưng hợp đồng phản hồi khác nhau.

## 3. Chọn loại listener container

Spring JMS có hai lựa chọn thông dụng:

| Tiêu chí | `SimpleMessageListenerContainer` | `DefaultMessageListenerContainer` |
|---|---|---|
| Cơ chế | Đăng ký callback với JMS provider qua `MessageConsumer.setMessageListener()` | Các listener task nhận bằng vòng `receive()` rồi gọi listener |
| Số consumer | Thường cố định theo cấu hình khi start | Có `concurrentConsumers` tối thiểu và `maxConcurrentConsumers` để mở rộng/thu hẹp động |
| Recovery, stop/start | Đơn giản, phụ thuộc provider và tính năng container | Linh hoạt hơn cho khôi phục, quản trị lifecycle |
| Transaction JMS cục bộ | Có thể dùng `sessionTransacted` | Có thể dùng `sessionTransacted` |
| Transaction do manager ngoài điều phối | Không hỗ trợ cơ chế dynamic/external transaction như DMLC | Có thể phối hợp với `PlatformTransactionManager`, kể cả JTA khi đủ điều kiện |
| Trường hợp điển hình | Nhu cầu cố định và đơn giản | Phần lớn ứng dụng JMS của Spring cần concurrency/recovery/transaction rõ ràng |

Spring Integration có thể tạo `DefaultMessageListenerContainer` từ `ConnectionFactory`, destination và các tham số cấu hình. Nếu cần container riêng, có thể truyền một instance `AbstractMessageListenerContainer` đã cấu hình sẵn. **Các thuộc tính dành cho container tự tạo có thể không còn tác dụng khi bạn truyền container ngoài**; lúc đó phải chỉnh trực tiếp container được cung cấp.

Không nên chọn SimpleContainer chỉ vì tên “simple” nếu hệ thống có tải thay đổi lớn, yêu cầu thay đổi concurrency hoặc tham gia transaction được điều phối bởi một manager bên ngoài.

## 4. Concurrency: consumer tối thiểu, tối đa và mở rộng động

Với DMLC:

- `concurrentConsumers` là **số consumer cơ sở** mà container duy trì. Mặc định thông thường là **1**.
- `maxConcurrentConsumers` là **giới hạn trên** số consumer có thể hoạt động. Mặc định là **1**; khi lớn hơn `concurrentConsumers`, DMLC có thể bổ sung consumer khi liên tục có message.
- `setConcurrency("2-6")` là cách cấu hình rút gọn: tối thiểu 2, tối đa 6. `setConcurrency("3")` tương ứng một mức cố định là 3 trong cách dùng thông thường.

Việc tăng từ 2 lên 6 **không phải ngay lập tức tạo 6 consumer**: nó phụ thuộc tải thực tế, trạng thái task, các ngưỡng idle, JMS provider và tài nguyên executor. Khi queue hết backlog, DMLC có thể thu hẹp số consumer động về mức cơ sở.

~~~mermaid
flowchart TD
    A["Queue ít message"] --> B["Duy trì 2 consumer cơ sở"]
    B --> C{"Backlog và các lần nhận có dữ liệu tăng?"}
    C -->|"Có"| D["Tạo thêm listener task / consumer"]
    D --> E["Tối đa 6 consumer"]
    E --> F{"Tải giảm và task đủ thời gian idle?"}
    F -->|"Có"| G["Thu hẹp về 2 consumer"]
    F -->|"Không"| E
    C -->|"Không"| B
~~~

### Ước lượng throughput để chọn điểm bắt đầu

Nếu **thời gian xử lý trung bình đồng bộ của một message** là 200 ms và không có nghẽn mạng/DB, một consumer có năng lực lý tưởng khoảng 5 message/giây.

| Consumer hoạt động | Năng lực lý tưởng với 200 ms/message | Hạn chế thực tế |
|---:|---:|---|
| 1 | Khoảng 5 msg/s | Một message chậm sẽ cản những message phía sau |
| 2 | Khoảng 10 msg/s | Tăng số kết nối/session, tranh chấp database |
| 4 | Khoảng 20 msg/s | Thứ tự hoàn tất có thể khác thứ tự gửi |
| 6 | Khoảng 30 msg/s | Pool DB, broker, CPU hoặc API downstream có thể bão hòa |

Các con số chỉ là **mô hình lý tưởng** `throughput ≈ consumerCount / secondsPerMessage`, không phải SLA. Nếu mỗi handler cần 500 ms vì DB chậm, 6 consumer chỉ còn năng lực lý tưởng 12 msg/s. Nếu tất cả consumer chờ một resource có khóa duy nhất, tăng consumer có thể không cải thiện throughput.

Do đó, nên tăng concurrency theo phép đo thực tế: incoming rate, queue backlog, p95 processing latency, pool DB và số connection/session broker. Không tăng không giới hạn chỉ vì queue đang dài.

### Concurrency không đồng nhất với số instance hay số thread downstream

Giả sử triển khai **3 instance**, mỗi instance `concurrency="2-6"`. Tổng số consumer của **cùng queue** có thể dao động từ 6 đến 18, chưa kể consumer của dịch vụ khác. Phải tính **tổng across replicas**, tránh cấu hình riêng mỗi pod rồi làm cạn connection hoặc DB pool ở cấp cluster.

Nếu downstream dùng `ExecutorChannel` với pool 20 threads, 20 thread đó **không phải** 20 JMS consumer. Số JMS consumer vẫn do listener container kiểm soát; khi tách bất đồng bộ, JMS transaction có thể kết thúc trước khi work trong executor hoàn thành.

## 5. Cấu hình Java DSL: message-driven với concurrency 2–6

Ví dụ dùng **Spring Integration 6+ / Spring Framework 6+**, Jakarta JMS (`jakarta.jms`) và Java 17+. Dự án cần `spring-integration-jms` cùng provider JMS và một bean `ConnectionFactory` đã kết nối được broker.

Dependency minh họa khi dùng Spring Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Thêm JMS client/starter tương ứng với broker được sử dụng. -->
~~~

Ứng dụng có queue `orders.in`; consumer của nó đọc `TextMessage` chứa JSON đơn hàng. Flow:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrdersJmsMessageDrivenConfig {

    @Bean
    public IntegrationFlow ordersInboundFlow(
            ConnectionFactory connectionFactory,
            OrderImportService orderImportService) {

        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                        .destination("orders.in")
                        .configureListenerContainer(container ->
                                container.concurrentConsumers(2)
                                        .maxConcurrentConsumers(6)
                                        .sessionTransacted(true)
                                        .recoveryInterval(5000)))
                .handle(String.class, (json, headers) -> {
                    orderImportService.importOrder(json);
                    return null; // Handler một chiều.
                })
                .get();
    }
}
~~~

Service nghiệp vụ để người học triển khai:

~~~java
public interface OrderImportService {
    void importOrder(String orderJson);
}
~~~

**Ý nghĩa cấu hình:**

- `.destination("orders.in")` chọn JMS queue. Queue phải có sẵn hoặc được broker phép tự tạo; tên và ACL phải đúng.
- `.configureListenerContainer(...)` cấu hình `DefaultMessageListenerContainer` được Java DSL tạo từ `ConnectionFactory`.
- `.concurrentConsumers(2)` duy trì hai consumer nền; `.maxConcurrentConsumers(6)` cho phép mở rộng tối đa sáu khi có tải.
- `.sessionTransacted(true)` yêu cầu JMS transaction cục bộ: khi listener xử lý thành công, transaction được commit; khi lỗi thích hợp truyền ra ngoài, transaction có thể rollback.
- `.recoveryInterval(5000)` cấu hình khoảng chờ thử phục hồi kết nối khi container gặp lỗi, đơn vị mili giây.
- `.handle(String.class, ...)` yêu cầu converter đưa JMS `TextMessage` thành payload `String`; service thực tế phải parse/validate JSON và xử lý idempotency.

Ví dụ này **không cần poller**. Để demo gửi dữ liệu thử, một JMS producer có thể gọi:

~~~java
// jmsTemplate là bean của ứng dụng test, dùng JMS provider tương thích.
jmsTemplate.convertAndSend(
        "orders.in",
        "{\"eventId\":\"evt-801\",\"orderId\":\"ORD-801\",\"version\":1}");
~~~

Khi broker và flow đang chạy, listener sẽ nhận message qua một trong các consumer đang hoạt động. Concurrency quyết định có thể xử lý bao nhiêu message **khác nhau** cùng lúc trên queue, không khiến cùng một message tự động nhân thành sáu bản.

### Cấu hình XML tương đương

~~~xml
<int:channel id="ordersInput"/>

<int-jms:message-driven-channel-adapter
        id="ordersMessageDriven"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.in"
        channel="ordersInput"
        concurrent-consumers="2"
        max-concurrent-consumers="6"
        acknowledge="transacted"/>

<int:service-activator
        input-channel="ordersInput"
        ref="orderImportHandler"
        method="handle"/>
~~~

XML trên là **fragment**: ứng dụng cần namespace `int`/`int-jms`, bean `jmsConnectionFactory` và bean `orderImportHandler`. Khi Spring Integration tạo container nội bộ, các thuộc tính concurrency/acknowledge trên adapter được áp dụng cho container đó. Nếu cấu hình bằng `container="beanId"`, hãy thiết lập chính các thuộc tính này **trên bean container ngoài**.

## 6. Khi cần tự quản lý DefaultMessageListenerContainer

Nếu phải kiểm soát cache level, executor, subscription hoặc cấu hình recovery chi tiết, ứng dụng có thể tạo container riêng rồi truyền vào adapter.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Bean
public DefaultMessageListenerContainer ordersListenerContainer(
        ConnectionFactory connectionFactory) {
    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.in");
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(6);
    container.setSessionTransacted(true);
    container.setRecoveryInterval(5000L);
    return container;
}

@Bean
public IntegrationFlow ordersFlowWithExternalContainer(
        DefaultMessageListenerContainer ordersListenerContainer,
        OrderImportService orderImportService) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(ordersListenerContainer))
            .handle(String.class, (json, headers) -> {
                orderImportService.importOrder(json);
                return null;
            })
            .get();
}
~~~

**Lưu ý:** đây là **phương án thay thế toàn bộ flow ở mục 5**, không nên đăng ký đồng thời cả hai flow trên cùng queue nếu mục tiêu chỉ là một endpoint. Khi container do ứng dụng tạo, cần phối hợp lifecycle của bean và endpoint để listener được gắn trước khi khởi động; hãy kiểm tra trong integration test. `DefaultMessageListenerContainer` có thể tham gia vào cơ chế lifecycle của Spring, còn `JmsMessageDrivenEndpoint` quyết định việc shutdown container khi stop.

Với các hệ thống cần manager ngoài (ví dụ `JtaTransactionManager`), DMLC hỗ trợ cấu hình `setTransactionManager(...)`, nhưng **không tự suy ra** có XA transaction khi chỉ đặt `setSessionTransacted(true)`.

## 7. Các tham số sâu hơn: executor, receive timeout và scaling

### 7.1. TaskExecutor của DMLC

DMLC dùng `TaskExecutor` để chạy listener invoker tasks. Một task có thể giữ một session/consumer và lặp nhận message; không nên nghĩ rằng cứ **mỗi message** sẽ tạo một thread mới. Mặc định thường có số invoker ban đầu bằng `concurrentConsumers`.

Nếu cung cấp executor tùy chỉnh, cần bảo đảm nó đủ năng lực chạy **số task listener dự kiến**, kể cả mức `maxConcurrentConsumers`, và hiểu cách DMLC quản lý task lâu dài. Executor pool quá nhỏ có thể khiến số consumer thực tế không đạt cấu hình. Executor lớn không đồng nghĩa downstream có thêm kết nối DB.

Ví dụ cho một môi trường có queue nhưng nhu cầu thread tách biệt:

~~~java
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.context.annotation.Bean;

@Bean("jmsListenerExecutor")
public ThreadPoolTaskExecutor jmsListenerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("jms-orders-");
    return executor;
}
~~~

Đây chỉ là ví dụ tạo executor; Spring tự gọi bước khởi tạo lifecycle của bean. Để sử dụng, inject bean vào container bằng `setTaskExecutor(executor)` hoặc DSL `taskExecutor(...)`, đồng thời đo hoạt động thực tế. Giá trị `queueCapacity(0)` nhằm hạn chế tích lũy listener task chưa chạy trong executor, nhưng cần kiểm tra khả năng xử lý task rejection và chiến lược scale trước khi dùng production. **Không tùy tiện dùng chung executor bị nghẽn bởi HTTP/DB tasks** với listener JMS.

### 7.2. Receive timeout của DMLC khác poller

`DefaultMessageListenerContainer` có thuộc tính `receiveTimeout` điều khiển thời gian chờ **một lượt JMS receive bên trong listener task**. Nó ảnh hưởng độ nhạy stop/reconfigure/scaling và cách task ghi nhận trạng thái idle, chứ không tạo lịch `fixedDelay` của Spring Integration.

| Cấu hình | Ý nghĩa | Tác động cần quan sát |
|---|---|---|
| `concurrentConsumers` | Số consumer nền | Tải cơ sở lên broker/session pool |
| `maxConcurrentConsumers` | Trần consumer động | Throughput tiềm năng và rủi ro quá tải downstream |
| `receiveTimeout` | Thời gian chờ một lần nhận JMS ở DMLC | Độ nhạy khi dừng và xác định idle |
| `maxMessagesPerTask` | Số lần thử nhận tối đa cho một invoker task, tính cả lần receive không có message | Vòng đời task và chiến lược executor; không phải hạn mức message mỗi lần poll ở Spring Integration |
| `idleTaskExecutionLimit` | Số lần task idle trước khi kết thúc invoker động | Tránh scale lên/xuống quá thường xuyên |
| `idleConsumerLimit` | Giới hạn consumer thêm được duy trì idle | Cân bằng mức mở rộng và tài nguyên |
| `recoveryInterval` / `BackOff` | Nhịp thử recovery khi JMS có lỗi | Thời gian phục hồi và tải reconnect lên broker |
| `cacheLevel` | Mức cache connection/session/consumer của DMLC | Hiệu năng, đặc tính transaction, resource lifecycle |

**Đừng nhầm `maxMessagesPerTask` với `maxMessagesPerPoll`.** `maxMessagesPerPoll` thuộc polling consumer của Spring Integration, giới hạn số message nguồn được hỏi trong một lượt poll. `maxMessagesPerTask` thuộc hạ tầng DMLC, giới hạn số lần thử nhận mà listener invoker task thực hiện trước khi nhường/tái lập task theo cấu hình.

### 7.3. Caching và ConnectionFactory

DMLC có cache riêng cho JMS connection/session/consumer theo `cacheLevel`. Khi dùng native JMS, container thường tái sử dụng session/consumer để giảm chi phí. Với transaction manager ngoài, chính sách cache có thể khác để tương thích môi trường quản lý transaction.

Không mặc định **bọc một `DefaultMessageListenerContainer` bằng `CachingConnectionFactory`** như khi tối ưu `JmsTemplate` gửi message; việc xếp nhiều lớp cache/pool có thể gây hành vi khó đoán khi stop/restart hoặc scaling. Nếu JMS provider đã có connection/session pooling, hãy xác định chính xác lớp nào chịu trách nhiệm caching trước khi tùy chỉnh.

## 8. Queue concurrency, ordering và prefetch

### 8.1. Với queue, concurrency giúp chia việc

Nếu queue `orders.in` có 100 message và 4 consumer đang hoạt động, broker có thể giao các message khác nhau cho 4 consumer. Nhưng thứ tự **hoàn tất** phụ thuộc thời gian xử lý. Ví dụ:

~~~text
Thời điểm nhận:
  Worker 1: ORD-1 (handler mất 900 ms)
  Worker 2: ORD-2 (handler mất 100 ms)

Thời điểm commit:
  ORD-2 hoàn tất trước ORD-1.
~~~

Ngay cả khi queue ban đầu nhận theo thứ tự `ORD-1`, `ORD-2`, ứng dụng không thể dựa vào thứ tự commit khi có nhiều consumer. Nếu hai event của **cùng một đơn** yêu cầu xử lý nối tiếp, có thể dùng một consumer cho phần đó, phân vùng theo `orderId`, cơ chế message group do broker hỗ trợ, hoặc optimistic concurrency theo `aggregateVersion` trong database.

### 8.2. Prefetch ảnh hưởng phân phối, không phải số handler

Nhiều JMS broker có cơ chế **prefetch/consumer window**: broker có thể cấp trước một số message cho từng consumer. Khi một consumer đang xử lý chậm, một phần message đã được giao cho consumer đó có thể chờ trong bộ đệm của provider trong khi consumer khác thiếu việc.

Do đó:

- Queue depth thấp **không nhất thiết** nghĩa tất cả message đã được handler xử lý xong.
- Phân phối message không nhất thiết đồng đều giữa consumer nếu prefetch/window khác nhau.
- Concurrency và prefetch cần được thử trên broker thực tế, nhất là khi message có thời gian xử lý dao động lớn.

Tên property và cơ chế prefetch **khác nhau theo JMS provider**. Không sao chép cấu hình ActiveMQ Artemis sang một JMS provider khác rồi giả định semantics tương đương.

### 8.3. Khi nào scale ngang bằng instance?

Tăng `maxConcurrentConsumers` trên một instance và tăng số instance đều có thể tăng consumer cho queue. Tăng instance còn phân tán CPU và failure domain; song tổng số kết nối và áp lực lên DB cũng tăng. Nếu queue yêu cầu strict ordering cho một aggregate, cả hai cách scale đều phải giữ cùng chiến lược ordering và idempotency.

## 9. Cẩn trọng với topic và subscription concurrency

Queue và topic không có ngữ nghĩa nhiều consumer giống nhau. Với **topic thông thường**, mỗi consumer tạo một subscription độc lập có thể nhận bản sao cùng event; tăng `concurrentConsumers` từ 1 lên 4 có nguy cơ khiến một ứng dụng xử lý **bốn bản của cùng event**, thay vì chia bốn phần công việc.

Với **durable unshared subscription**, JMS/broker thường giới hạn số consumer hoạt động đồng thời trên cùng subscription identity. Nếu muốn chia việc trong **một subscription**, cần dùng **shared subscription** hoặc **shared durable subscription** theo JMS provider và container hỗ trợ, đồng thời đặt `clientId`/`subscriptionName` chính xác.

| Nhu cầu | Cấu hình đúng hướng | Không nên làm |
|---|---|---|
| Một nhóm worker xử lý các command | Queue + nhiều consumer | Dùng topic với nhiều subscription rồi mỗi worker xử lý cùng command |
| Ba dịch vụ đều nhận `OrderPaid` | Topic + ba subscription độc lập | Cho cả ba dịch vụ cạnh tranh trên cùng queue |
| Một dịch vụ topic muốn scale xử lý | Shared subscription phù hợp JMS provider, hoặc phân phối ra queue riêng | Tăng concurrency topic thường mà không kiểm tra duplicate |
| Nhận event khi subscriber offline | Durable subscription với TTL/retention phù hợp | Chỉ bật concurrency mà bỏ qua durable identity |

Ví dụ `order-paid` gửi tới topic `orders.events` phải được cả kế toán và kho xử lý. Kế toán và kho cần **hai subscription khác nhau**. Nếu kế toán có ba replica và chỉ muốn mỗi event được một replica xử lý, chúng phải chia nhau **một shared subscription** khi provider hỗ trợ hoặc dùng một queue công việc downstream riêng.

## 10. Transaction và acknowledge khi có nhiều consumer

Spring Integration tạo JMS message-driven adapter với acknowledge mode **transacted** theo mặc định từ phiên bản 4.2, **trừ khi bạn cung cấp container bên ngoài**, khi đó cấu hình transaction/acknowledge của container do ứng dụng quyết định. DMLC thuần không tự có cùng default transaction như một adapter Spring Integration cấu hình nội bộ. Vì vậy trong ví dụ Java DSL phía trên ta đặt `sessionTransacted(true)` tường minh.

### 10.1. Đường xử lý đồng bộ

~~~mermaid
flowchart LR
    A["JMS Session nhận message"] --> B["Adapter tạo Spring Message"]
    B --> C["DirectChannel"]
    C --> D["Validate + ghi DB"]
    D --> E{"Handler ném exception?"}
    E -->|"Không"| F["JMS commit"]
    E -->|"Có, chưa bị nuốt"| G["JMS rollback"]
    G --> H["Broker redelivery / DLQ theo policy"]
~~~

Với `DirectChannel` và handler chạy trong listener thread, lỗi đồng bộ có cơ hội lan ra ranh giới transaction của JMS container. Nếu handler ném exception, listener container có thể rollback JMS session và broker có thể redeliver message. Nếu handler catch lỗi rồi chỉ log, transaction có thể commit dù nghiệp vụ thất bại.

**Không suy ra DB transaction đã được rollback cùng JMS transaction.** `sessionTransacted=true` chỉ quản lý JMS session cục bộ. Nếu DB commit thành công rồi JMS transaction rollback, cùng message có thể đến lại. Hãy dùng `eventId`/`commandId` làm khóa idempotency, cùng unique constraint hoặc inbox table ở DB.

### 10.2. Ranh giới bất đồng bộ

Khi chuyển từ `DirectChannel` sang `ExecutorChannel` hoặc `QueueChannel`:

~~~text
JMS listener -> Spring Message -> ExecutorChannel -> Handler ở thread khác
                |                 |
                |                 +-- lỗi có thể xảy ra sau khi JMS đã commit
                +-- callback listener có thể đã kết thúc
~~~

Listener có thể xác nhận/commit message ngay khi chuyển được vào channel, trước khi handler bất đồng bộ hoàn thành. Nếu handler thất bại, lỗi ở downstream **không tự động** rollback JMS message ban đầu. Muốn giữ độ tin cậy, phải bổ sung durable handoff, retry/error flow ở tầng async hoặc không tách thread trong đoạn cần transaction.

### 10.3. Error channel và exception propagation

Spring Integration JMS inbound adapter hỗ trợ `errorChannel`. Khi lỗi conversion hoặc dispatch được đưa vào `ErrorMessage`, người viết error flow phải xác định có **ném lại exception** hay không. Nếu error flow hấp thụ lỗi và trả về bình thường, listener có thể coi quá trình nhận là thành công và commit JMS transaction.

Không mặc định `errorChannel` là retry queue hoặc DLQ. Redelivery và DLQ do broker/provider policy kết hợp với transaction/acknowledge quyết định; retry trong ứng dụng phải có giới hạn/backoff và tránh tạo poison-message loop.

### 10.4. AUTO_ACKNOWLEDGE và sự khác nhau giữa các container

Với `DefaultMessageListenerContainer`, `AUTO_ACKNOWLEDGE` có thể xác nhận trước khi listener thực thi, nên exception trong handler **không bảo đảm redelivery**. Vì vậy, đối với queue xử lý nghiệp vụ quan trọng, session transacted thường an toàn hơn. `SimpleMessageListenerContainer` có hành vi gọi listener khác và vẫn phải kiểm tra acknowledge/provider; không nên gộp hai kiểu container thành một bảo đảm duy nhất.

## 11. Recovery, stop/start và lifecycle

Ở runtime, message-driven container phải duy trì connection/session/consumer. Khi broker gián đoạn, DMLC có cơ chế khôi phục. Theo Spring Framework, thời gian retry cơ sở thường là 5 giây; có thể đặt `recoveryInterval` hoặc một `BackOff` khi cần backoff khác.

Những điểm cần biết:

1. **Startup:** container tạo listener task/consumer ở mức `concurrentConsumers`. Nếu destination hoặc ACL sai, container có thể lặp retry và queue tiếp tục tăng.
2. **Scale up:** khi đủ message, DMLC có thể mở thêm consumer đến `maxConcurrentConsumers`. Cần broker/session pool và task executor đủ tài nguyên.
3. **Scale down:** khi idle lâu, invoker động có thể kết thúc; consumer nền vẫn được duy trì.
4. **Stop endpoint:** từ Spring Integration 5.1, `JmsMessageDrivenEndpoint` mặc định shutdown container khi endpoint dừng, giải phóng connection/consumer. Tùy chọn `shutdownContainerOnStop(false)` thay đổi hành vi này và cần được sử dụng có chủ đích.
5. **Broker reconnect:** ứng dụng còn chạy không có nghĩa consumer đã khôi phục thành công. Theo dõi listener health, số active consumers và queue age.
6. **Restart/crash:** message chưa commit có thể được broker redeliver; nếu DB đã commit trước crash, cần idempotency để không xử lý trùng.

Không đặt cấu hình recovery quá gắt khiến nhiều replica đồng thời reconnect dồn dập lên broker đang lỗi. Dùng backoff phù hợp và alert khi không thể nhận message trong thời gian SLA.

### Một số metric của DefaultMessageListenerContainer

DMLC hỗ trợ các phương thức như `getActiveConsumerCount()` và `getScheduledConsumerCount()`:

- **Scheduled consumer count:** số listener invoker được lên lịch, có thể khác mức đang thực sự xử lý.
- **Active consumer count:** số consumer hiện đang active theo trạng thái container; **không tương đương** số message nghiệp vụ xử lý thành công mỗi giây.

Các con số này giúp kiểm chứng scaling, nhưng cần kết hợp broker metrics, dữ liệu DB và thời gian handler. Với một listener container nằm bên trong Java DSL, muốn truy xuất trực tiếp instance để giám sát/điều chỉnh thường cần quản lý bean/endpoint hoặc xuất metrics qua instrumentation phù hợp.

## 12. Thiết kế capacity và backpressure

Một sự cố thường gặp là queue tích lũy 50.000 message. Tăng `maxConcurrentConsumers` từ 4 lên 40 có thể kéo backlog xuống tạm thời, nhưng nếu DB pool chỉ có 12 connection, nhiều thread sẽ đứng chờ; p99 latency tăng và broker session/heap bị chiếm thêm.

Quy trình lựa chọn concurrency:

1. **Đo tốc độ vào:** message/giây trung bình, giờ cao điểm, kích thước payload.
2. **Đo thời gian xử lý:** p50, p95, p99 cho handler, DB transaction, HTTP call downstream.
3. **Tính năng lực sơ bộ:** `throughput lý tưởng = activeConsumers / avgProcessingSeconds`; thử tải để xác định năng lực thực tế.
4. **Xác định bottleneck:** pool DB, connection broker, thread, CPU, network, API rate limit, lock theo aggregate.
5. **Chọn mức cơ sở và trần:** bắt đầu nhỏ, đo backlog và latency; tăng đến khi không còn cải thiện hoặc downstream bắt đầu suy giảm.
6. **Đặt retry/backoff và DLQ:** poison message và lỗi tạm thời không được chiếm vô hạn tất cả consumer.
7. **Theo dõi tổng trên mọi replica:** tránh nhân `maxConcurrentConsumers` với số instance vượt khả năng toàn hệ thống.

Spring JMS listener container tự điều chỉnh số consumer ở mức cơ bản, **không phải hệ thống kiểm soát backpressure từ đầu đến cuối**. Nếu downstream chậm hơn upstream, message vẫn tích lũy ở broker hoặc xuất hiện retry, cần cảnh báo queue depth/oldest age và các cơ chế giới hạn nguồn hoặc mở rộng hạ tầng phù hợp.

### Checklist vận hành

| Metric/sự kiện | Lý do theo dõi | Cách phản ứng |
|---|---|---|
| `queue depth` | Backlog chưa được xử lý | So sánh incoming/outgoing rate, kiểm tra consumer |
| Tuổi message cũ nhất | SLA xử lý chậm | Ưu tiên điều tra khi tăng liên tục |
| `activeConsumerCount` | Listener có scale và hoạt động không | Kiểm tra lỗi kết nối và giới hạn executor |
| `scheduledConsumerCount` | Khả năng lên lịch listener task | Kiểm tra số invoker và cấu hình scaling |
| Handler latency p95/p99 | Có bị DB/API chậm kéo dài không | Tối ưu handler, cân chỉnh timeout/pool |
| JMS redelivery count | Có lỗi lặp hoặc rollback không | Phân loại lỗi, retry/backoff, idempotency |
| DLQ/poison messages | Lỗi dữ liệu cần can thiệp | Quarantine, sửa payload/schema |
| Broker connection/session count | Hạ tầng có quá tải không | Tính tổng theo replica/container |
| Lỗi reconnect/recovery | Broker/ACL/network có vấn đề | Cảnh báo, kiểm tra recovery policy |

## 13. Bài thực hành: tăng tải với queue đơn hàng

**Bối cảnh:** triển khai broker test, queue `orders.in`, service nhập đơn giả lập thời gian xử lý 200 ms và có bảng `processed_event(event_id)` ràng buộc unique. Dùng một producer gửi JSON `eventId`/`orderId`; test trên một broker thật hoặc container tương thích provider. Những bài liên quan redelivery, transaction và prefetch không thể được kiểm chứng đầy đủ chỉ bằng mock.

### Bài A — Đo concurrency cơ sở

1. Đặt `concurrentConsumers=1`, `maxConcurrentConsumers=1`, gửi 100 message.
2. Ghi thời gian bắt đầu/kết thúc từng handler và throughput thực tế. Đối chiếu con số lý tưởng 5 msg/s khi handler 200 ms.
3. Chuyển sang `concurrentConsumers=2`, `maxConcurrentConsumers=6`, gửi lại 100 message mới.
4. Quan sát active/scheduled consumer, thời gian xử lý, queue depth và CPU/DB pool.
5. Tăng `maxConcurrentConsumers` lên 10 **chỉ trong môi trường test** và xác định điểm bắt đầu bão hòa downstream.

### Bài B — Thứ tự và idempotency

1. Gửi `OrderCreated(v1)` và `OrderPaid(v2)` của cùng `orderId` khi có nhiều consumer.
2. Cho handler v1 ngủ lâu hơn v2; ghi nhận thứ tự hoàn tất có thể đảo.
3. Thêm kiểm tra `aggregateVersion` hoặc cơ chế xử lý nối tiếp theo khóa đơn hàng.
4. Cho handler ném exception sau khi ghi DB, rồi quan sát broker redeliver.
5. Dùng unique constraint trên `eventId` để bảo đảm không có tác động nghiệp vụ lặp.

### Bài C — Lỗi và ranh giới transaction

1. Với `sessionTransacted(true)`, cho handler đồng bộ ném exception; quan sát rollback/redelivery theo broker policy.
2. Cấu hình `errorChannel` hấp thụ exception, kiểm tra sự khác biệt về commit.
3. Chỉnh error flow để ném lại exception nếu muốn rollback, giới hạn retry và cấu hình DLQ phù hợp.
4. Thay `DirectChannel` bằng `ExecutorChannel`, cho handler async lỗi và giải thích vì sao transaction JMS ban đầu có thể đã commit.
5. Kiểm tra idempotency khi retry sau crash giữa DB commit và JMS commit.

### Bài D — Broker offline và recovery

1. Ngắt broker trong lúc queue có message; theo dõi log lỗi và số active consumer.
2. Bật broker trở lại; đo thời gian DMLC kết nối lại và tiếp tục nhận message.
3. Thử `recoveryInterval=5000` và backoff dài hơn khi có nhiều instance; quan sát tải reconnect.
4. Stop/start endpoint; kiểm tra connection và consumer được giải phóng/tạo lại.

### Bài E — Queue so với topic

1. Dùng queue với 3 consumer; xác nhận một command bình thường chỉ được một consumer xử lý, trừ khi redelivery.
2. Publish 10 message vào topic với nhiều non-shared subscription; kiểm tra nhiều subscriber có thể nhận cùng event.
3. Thử tăng concurrency trên topic bình thường và giải thích nguy cơ nhận trùng.
4. Nếu broker hỗ trợ, dùng shared durable subscription để chia tải **trong một subscription**; kiểm tra subscription identity và hành vi khi offline.

### Câu hỏi tự đánh giá

1. DMLC có dùng `MessageConsumer.receive()` nội bộ hay không? Vì sao endpoint Spring Integration vẫn gọi là message-driven?
2. Khác nhau giữa `concurrentConsumers=2` và `maxConcurrentConsumers=6` là gì?
3. Vì sao một pod cấu hình 6 consumer có thể khiến toàn cluster có nhiều hơn 6 consumer?
4. Khi queue có 100 message, đặt 6 consumer có bảo đảm tất cả hoàn tất đúng thứ tự gửi không?
5. Vì sao topic thường không nên tăng concurrent consumers nếu chưa cấu hình shared subscription?
6. `maxMessagesPerTask` khác `maxMessagesPerPoll` ở đâu?
7. Khi chuyển `DirectChannel` sang `ExecutorChannel`, transaction JMS bảo vệ phần nào?
8. Tại sao `sessionTransacted=true` không bảo đảm atomic commit với PostgreSQL?
9. Hai metric `getActiveConsumerCount()` và `getScheduledConsumerCount()` khác gì throughput thực tế?
10. Khi DB pool là bottleneck, tăng concurrency gấp mười có luôn giúp giảm backlog không?

## 14. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): message-driven channel adapter, container nội bộ/ngoài, `concurrent-consumers`, acknowledge, error channel và lifecycle.
- [Spring Integration API — JmsMessageDrivenChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsMessageDrivenChannelAdapterSpec.html): cấu hình endpoint Java DSL và listener container.
- [Spring Integration API — JmsDefaultListenerContainerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsDefaultListenerContainerSpec.html): `concurrentConsumers`, `maxConcurrentConsumers`, `receiveTimeout`, `recoveryInterval`, `taskExecutor`.
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): message listener container và transaction JMS.
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): dynamic scaling, idle task, caching, concurrency và recovery.

**Ghi nhớ:** message-driven container là hạ tầng liên tục nhận JMS message và chuyển vào Spring Integration mà không cần poller của flow. Concurrency giúp tăng năng lực nhận **trên queue**, nhưng phải tính tới số instance, downstream, thứ tự và prefetch; với **topic**, chỉ scale trên shared subscription khi provider/contract hỗ trợ. Transaction, error propagation, idempotency và quan sát backlog là các điều kiện để tăng tốc mà vẫn giữ tính đúng đắn.
