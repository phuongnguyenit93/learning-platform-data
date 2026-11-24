# Redelivery và dead-letter queue trong JMS

## 1. Bài toán: message lỗi không được làm tắc cả hệ thống

Một dịch vụ Spring Integration nhận các sự kiện `OrderPaid` từ JMS queue `orders.paid.in` và cập nhật PostgreSQL. Lúc 10 giờ, database mất kết nối trong 30 giây: consumer cần **thử lại** những message chưa xử lý được. Nhưng nếu một message có JSON hỏng vĩnh viễn, việc liên tục rollback rồi nhận lại nó sẽ tạo **poison-message loop**, tiêu tốn CPU, làm đầy log và có thể ngăn các sự kiện hợp lệ tiến lên.

Hai cơ chế phải phối hợp là:

- **Redelivery:** JMS provider/broker **giao lại** message chưa được xác nhận thành công, chẳng hạn vì transaction nhận bị rollback.
- **Dead-letter queue (DLQ):** destination giữ những message mà chính sách broker quyết định không nên tiếp tục giao từ queue/subscription ban đầu, thường sau nhiều lần xử lý thất bại.

Trong module **SPRING_INTEGRATION_ADAPTERS**, inbound/outbound adapter, gateway, poller và `MessageChannel` đưa dữ liệu giữa Spring Integration và file, SFTP, HTTP, JMS, AMQP, Kafka hoặc database. Với **Adapter JMS**, chủ đề *Redelivery và dead-letter queue* giúp thiết kế hợp đồng message, đường lỗi, transaction và vòng đời consumer sao cho lỗi tạm thời được phục hồi mà lỗi vĩnh viễn được cô lập.

**Sau bài học, bạn cần có thể:**

1. Giải thích lúc nào JMS redelivery xảy ra và phân biệt nó với việc producer gửi lại một message mới.
2. Đọc `JMSRedelivered` và `JMSXDeliveryCount` đúng giới hạn của chúng.
3. Cấu hình một **JMS message-driven inbound adapter** với session transacted và exception propagation.
4. Thiết lập retry delay, số lần giao tối đa và dead-letter address/queue trên broker tương ứng.
5. Phân biệt `errorChannel`, broker DLQ, quarantine trong ứng dụng và expiry queue.
6. Thiết kế idempotent consumer, điều tra, replay an toàn và các phép thử lỗi.

## 2. Sơ đồ vòng đời: nhận, xử lý, commit, rollback, DLQ

~~~mermaid
flowchart TD
    A["Producer gửi JMS message"] --> B[("Broker: orders.paid.in")]
    B --> C["JMS listener nhận message"]
    C --> D["Spring Integration: parse + xử lý"]
    D --> E{"Hoàn thành?"}
    E -->|"Có"| F["JMS commit/acknowledge"]
    E -->|"Lỗi và exception lan ra"| G["JMS rollback / recover"]
    G --> H{"Đã đạt giới hạn giao lại theo broker?"}
    H -->|"Chưa"| I["Chờ redelivery delay"]
    I --> B
    H -->|"Rồi"| J[("Dead-letter destination")]
    J --> K["Điều tra, sửa lỗi, replay có kiểm soát"]
~~~

Đây là **mô hình điển hình** với transacted listener và broker được cấu hình DLQ. Nếu listener dùng `AUTO_ACKNOWLEDGE` hoặc error flow đã hấp thụ exception, broker có thể **không nhận được tín hiệu rollback**; khi đó đường từ lỗi sang redelivery trong sơ đồ sẽ **không xảy ra**.

### Ba kết quả không được đánh đồng

| Kết quả | Ý nghĩa | Lưu ý |
|---|---|---|
| Handler hoàn thành | Một nhánh nghiệp vụ đã chạy xong | Có thể vẫn chưa JMS commit |
| JMS commit/acknowledge thành công | Broker coi thao tác nhận đã hoàn tất theo protocol | Không chứng minh DB, HTTP hoặc Kafka được commit nguyên tử cùng JMS |
| Message vào DLQ | Broker hoặc ứng dụng đã cách ly message theo một chính sách | Không đồng nghĩa dữ liệu đã được sửa hoặc nghiệp vụ được hoàn tất |

DLQ là **cơ chế cách ly**, không phải dấu hiệu xử lý thành công. Message trong DLQ vẫn cần người hoặc workflow chuyên trách giải quyết.

## 3. Khi nào JMS redelivery xảy ra?

Theo Jakarta Messaging, consumer có thể gặp lại một message khi việc nhận trước đó **không được xác nhận**. Một số tình huống điển hình:

1. Session **transacted** nhận message nhưng `rollback()` được gọi sau lỗi handler.
2. Connection/session kết thúc trước khi transaction nhận được commit thành công.
3. Với `CLIENT_ACKNOWLEDGE`, consumer gọi `Session.recover()` hoặc gặp failure trước acknowledgment.
4. Consumer/broker gặp sự cố khiến trạng thái xác nhận của lần giao trước không chắc chắn; provider có thể giao lại khi phục hồi.

**Redelivery không phải producer retry.**

~~~text
Redelivery:
  Producer gửi JMS message ID:101
    -> Consumer nhận ID:101 -> rollback
    -> Broker giao lại ID:101

Producer retry:
  Producer gửi eventId=evt-101 -> JMS message ID:101
  Producer không chắc kết quả gửi, gửi lại cùng eventId=evt-101
    -> JMS message mới ID:205
~~~

Trong ví dụ, `eventId` là **khóa nghiệp vụ ổn định**, còn `JMSMessageID` nhận từ provider có thể khác khi producer gửi lại cùng event. Vì thế **không dùng mỗi `JMSRedelivered` hay `JMSMessageID` để chống trùng nghiệp vụ**.

### At-least-once và giới hạn của transaction

Với JMS broker, persistence, transaction và cấu hình phù hợp, một luồng có thể hướng tới mô hình **at-least-once**: khi lỗi tạm thời xảy ra, message chưa được commit có thể đến lại. Điều đó **không phải** exactly-once business processing.

Ví dụ handler đã commit DB rồi JVM crash trước JMS commit. Broker redeliver message; nếu handler chỉ thực thi lại `UPDATE balance=balance+amount` mà không có idempotency, doanh nghiệp có thể trừ hoặc cộng tiền hai lần dù broker hành xử đúng.

## 4. Các JMS header/property dùng để nhận diện redelivery

JMS chuẩn định nghĩa một số metadata quan trọng:

| Metadata | Nguồn | Ý nghĩa | Có được dùng làm business key? |
|---|---|---|---|
| `JMSMessageID` | JMS provider tạo khi send | Định danh một JMS message do provider quản lý | **Không**: producer có thể gửi lại cùng event dưới message ID mới |
| `JMSRedelivered` | JMS provider gán khi giao | Gợi ý message đã từng được giao nhưng có thể chưa được ack | **Không** |
| `JMSXDeliveryCount` | JMS provider đặt khi receive | Số lần provider đã giao message, lần đầu thông thường là **1** | **Không**: chỉ giúp quan sát/retry theo protocol |
| `JMSCorrelationID` | Theo contract request-reply | Ghép phản hồi JMS với yêu cầu | Không thay thế `eventId` |
| `eventId` trong JSON | Ứng dụng producer tạo | Định danh một sự kiện nghiệp vụ xuyên retries | **Có**, nếu được thiết kế ổn định và kiểm soát unique |

**Chi tiết Jakarta Messaging 3.1:** `JMSXDeliveryCount` là property bắt buộc trên message được nhận; `JMSRedelivered=true` gắn với delivery count từ 2 trở lên. Tuy nhiên specification cũng nêu **delivery count có thể không hoàn toàn chính xác sau failure**, vì provider không bị buộc persist mọi lần tăng count trước khi giao. Do đó không dùng một ngưỡng count phía ứng dụng làm nguồn sự thật tuyệt đối cho quy trình nghiệp vụ.

### Đọc trực tiếp JMS metadata khi kiểm thử

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;

public static void logDeliveryMetadata(Message message) throws JMSException {
    String jmsMessageId = message.getJMSMessageID();
    boolean redelivered = message.getJMSRedelivered();
    int deliveryCount = message.propertyExists("JMSXDeliveryCount")
            ? message.getIntProperty("JMSXDeliveryCount")
            : -1;

    System.out.printf(
            "jmsMessageId=%s, redelivered=%s, deliveryCount=%d%n",
            jmsMessageId, redelivered, deliveryCount);
}
~~~

Đây là một **helper JMS API** dành cho môi trường test hoặc callback có quyền truy cập nguyên JMS message. Trong Spring Integration, nếu inbound adapter trích payload, handler thường nhận Spring Message chứ không còn `jakarta.jms.Message`; metadata có thể được header mapper đưa sang Spring headers tùy cấu hình/version. **Không ép Spring payload `String` sang JMS Message** để đọc metadata nếu endpoint đã convert nó. Cần cấu hình mapper hoặc instrumentation tại biên.

### Vì sao không nên đặt `JMSRedelivered` từ phía ứng dụng?

`JMSRedelivered` là metadata về quá trình giao nhận mà **provider** quyết định. Producer không nên tự đặt cờ này để “đánh dấu” việc gửi lại. Nếu cần thể hiện một **business retry**, hãy dùng `eventId` và một trường nghiệp vụ riêng như `attemptReason` trong contract hoặc metadata phù hợp.

## 5. Acknowledgment, transaction và thời điểm được redeliver

| Chế độ nhận | Khi handler ném exception | Kỳ vọng thực tế |
|---|---|---|
| `DefaultMessageListenerContainer` với `AUTO_ACKNOWLEDGE` | Container có thể đã xác nhận trước khi handler chạy | **Không bảo đảm** broker redelivery |
| `CLIENT_ACKNOWLEDGE` | Có thể recover/redeliver theo container/provider | Best effort; không thay thế JMS transaction |
| `sessionTransacted=true` | Exception thoát tới container có thể làm rollback | Broker có cơ sở để redeliver theo chính sách |
| `JmsTemplate.receive()` với local transaction riêng | Transaction có thể commit khi `receive()` kết thúc | Lỗi ở downstream Spring flow sau đó **không rollback được** |
| **Transactional poller** dùng `JmsTransactionManager` | Poll/dispatch đồng bộ ở cùng transaction | Exception downstream đồng bộ có thể khiến JMS rollback |

### Message-driven adapter và polling adapter khác nhau

**Message-driven** có listener container luôn sẵn sàng nhận JMS message; **không cần Spring Integration poller**. **Polling inbound** gọi `JmsTemplate.receive()` theo lịch poller. Việc bật `sessionTransacted=true` trong template polling **không đủ** để bảo vệ handler downstream nếu transaction đã commit ngay sau receive.

Từ **Spring Integration 4.2**, khi JMS message-driven adapter **tự tạo listener container**, chế độ acknowledge mặc định là `transacted`. Nếu truyền một `DefaultMessageListenerContainer` **bên ngoài**, bạn phải cấu hình `sessionTransacted` hoặc transaction manager trên container đó; không mặc định suy ra nó được bảo vệ.

### Ranh giới đồng bộ là điều kiện quan trọng

~~~mermaid
flowchart TD
    A["JMS listener, session transacted"] --> B["Inbound adapter"]
    B --> C{"Spring MessageChannel"}
    C -->|"DirectChannel"| D["Handler đồng bộ"]
    D --> E["Exception lan ra -> JMS rollback"]
    C -->|"ExecutorChannel / QueueChannel"| F["Bàn giao message thành công"]
    F --> G["Listener kết thúc -> JMS có thể commit"]
    G --> H["Handler ở thread khác thất bại: không rollback được JMS gốc"]
~~~

**`errorChannel` cũng thay đổi đường đi exception.** Nếu error flow bắt lỗi rồi kết thúc bình thường, listener có thể commit message dù handler hoặc converter thất bại. Phần 7 phân tích chi tiết.

## 6. Java DSL: JMS inbound channel adapter có thể rollback

Ví dụ dùng Spring Integration 6+, Spring Framework 6+ và Java 17+ với `jakarta.jms`. Ứng dụng cần `spring-integration-jms`, JMS driver cho broker, `ConnectionFactory` hợp lệ và queue `orders.paid.in` đã được tạo/có quyền truy cập.

~~~xml
<!-- Phiên bản do Spring Boot BOM quản lý nếu dự án dùng Spring Boot. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Bổ sung JMS provider/starter và broker phù hợp môi trường. -->
~~~

### 6.1. Inbound flow đồng bộ, session transacted

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class PaidOrderJmsConfig {

    @Bean
    public IntegrationFlow paidOrderInbound(
            ConnectionFactory connectionFactory,
            PaidOrderConsumer paidOrderConsumer) {

        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                        .destination("orders.paid.in")
                        .configureListenerContainer(listener ->
                                listener.sessionTransacted(true)
                                        .concurrentConsumers(2)
                                        .maxConcurrentConsumers(4)))
                .handle(String.class, (json, headers) -> {
                    paidOrderConsumer.consume(json);
                    return null;
                })
                .get();
    }
}
~~~

Đây là cấu hình server-side: một JMS `TextMessage` thường được converter mặc định biến thành Spring payload `String`. Service ví dụ:

~~~java
public interface PaidOrderConsumer {
    // Parse/validate và xử lý trong cùng listener thread;
    // ném unchecked exception nếu cần rollback JMS.
    void consume(String json);
}
~~~

**Tại sao ví dụ đặt `sessionTransacted(true)` rõ ràng?** Để không dựa vào default và để người đọc biết exception ở handler đồng bộ có thể được chuyển về listener container. Hai consumer cơ sở và tối đa bốn consumer cho phép xử lý nhiều message **khác nhau**; mỗi consumer/session có transaction riêng.

Nếu service ném unchecked exception và lỗi **không bị error flow xử lý rồi nuốt**, callback thất bại, transaction JMS có thể rollback. **Sau rollback, broker quyết định khi nào giao lại hoặc đưa DLQ**. Spring Integration adapter không tự tạo một DLQ chỉ nhờ `sessionTransacted(true)`.

### 6.2. XML namespace tương đương

~~~xml
<int:channel id="paidOrdersInput"/>

<int-jms:message-driven-channel-adapter
        id="paidOrdersInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.in"
        channel="paidOrdersInput"
        acknowledge="transacted"
        concurrent-consumers="2"
        max-concurrent-consumers="4"/>

<int:service-activator
        input-channel="paidOrdersInput"
        ref="paidOrderConsumer"
        method="consume"/>
~~~

Đây là **fragment** cần khai báo namespace `int`/`int-jms`, các bean `jmsConnectionFactory` và `paidOrderConsumer`. Nếu dùng một container được tạo bên ngoài qua thuộc tính `container`, phải đặt transaction trên chính container đó.

### 6.3. Trường hợp source là polling adapter

Nếu có yêu cầu nhận JMS theo lịch, nên dùng transactional poller khi mong muốn downstream đồng bộ tham gia transaction:

~~~java
import org.springframework.jms.connection.JmsTransactionManager;

@Bean
public IntegrationFlow paidOrderPolling(
        ConnectionFactory connectionFactory,
        JmsTransactionManager jmsTransactionManager,
        PaidOrderConsumer paidOrderConsumer) {

    return IntegrationFlow.from(
            Jms.inboundAdapter(connectionFactory)
                    .destination("orders.paid.in")
                    .configureJmsTemplate(template ->
                            template.receiveTimeout(-1)),
            endpoint -> endpoint.poller(poller ->
                    poller.fixedDelay(5000)
                            .maxMessagesPerPoll(5)
                            .transactional(jmsTransactionManager)))
            .handle(String.class, (json, headers) -> {
                paidOrderConsumer.consume(json);
                return null;
            })
            .get();
}
~~~

`JmsTransactionManager` phải được khai báo là bean dùng cùng `ConnectionFactory`:

~~~java
@Bean
public JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

**Hai inbound flow ở mục 6.1 và 6.3 là phương án thay thế**, không cần đăng ký đồng thời cùng queue cho một nghiệp vụ. `receiveTimeout(-1)` giới hạn một lần receive thành không chờ, còn `fixedDelay(5000)` là nhịp poll, không liên quan chính sách redelivery của broker.

## 7. `errorChannel`: xử lý lỗi hay yêu cầu broker thử lại?

JMS message-driven inbound adapter của Spring Integration hỗ trợ `errorChannel`. Khi handler hoặc bước chuyển đổi message có exception, lỗi có thể được biểu diễn bằng một Spring `ErrorMessage` rồi gửi tới kênh lỗi.

**Điểm mấu chốt:** lỗi đã được nhận bởi error flow **không đồng nghĩa** transaction JMS bị rollback. Nếu error flow xử lý xong rồi trả về bình thường, listener có thể coi callback thành công và commit JMS transaction. Muốn redelivery dựa trên rollback, lỗi phải **truyền ngược đến container**, thường bằng việc ném lại exception từ error flow.

~~~mermaid
flowchart TD
    A["JMS listener nhận message, transacted"] --> B["Convert + send vào Spring channel"]
    B --> C{"Có lỗi?"}
    C -->|"Không"| D["Callback thành công -> JMS commit"]
    C -->|"Có"| E["ErrorMessage -> errorChannel"]
    E --> F{"Error flow ném lại exception?"}
    F -->|"Có"| G["Container rollback -> broker redelivery"]
    F -->|"Không"| H["Listener có thể commit -> không redelivery"]
~~~

Từ Spring Integration 4.2, **lỗi JMS inbound conversion** cũng có thể được gửi qua `errorChannel`. Không chỉ kiểm tra `try/catch` trong business handler: nếu `TextMessage` không convert được thì business handler có thể **chưa từng được gọi**.

### 7.1. Cấu hình kênh lỗi (fragment XML)

~~~xml
<int:channel id="paidOrdersErrors"/>

<int-jms:message-driven-channel-adapter
        id="paidOrdersInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.in"
        channel="paidOrdersInput"
        error-channel="paidOrdersErrors"
        acknowledge="transacted"/>

<int:service-activator
        input-channel="paidOrdersErrors"
        ref="jmsErrorHandler"
        method="handle"/>
~~~

Đây là fragment bổ sung/thay thế endpoint XML ở mục 6; cần khai báo `paidOrdersInput` và các bean tương ứng. Handler này chỉ có nhiệm vụ **xác định** lỗi nên rollback hay được ghi nhận/quarantine; nó không tự biến thành một DLQ của broker.

### 7.2. Ví dụ error handler chủ động ném lại

~~~java
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component("jmsErrorHandler")
public class JmsErrorHandler {

    public void handle(ErrorMessage error) {
        Throwable cause = error.getPayload();
        // Ghi metric/log đã lược bỏ payload nhạy cảm nếu cần.
        throw new IllegalStateException(
                "JMS processing failed; propagate for transaction rollback",
                cause);
    }
}
~~~

Khi handler này được gọi **đồng bộ** trên đường lỗi của listener, exception có thể đi ngược tới container, gây rollback và redelivery theo broker policy. Đây là ví dụ **rollback mọi lỗi** để quan sát cơ chế trong lab; với production, không nên retry vô hạn lỗi vĩnh viễn.

**Một chiến lược khác:** khi xác định một event không thể xử lý, ứng dụng có thể lưu trạng thái từ chối/quarantine bền vững rồi để listener commit. Nhưng không được coi việc gửi một log/error message thông thường là đã quarantine an toàn. Nếu ghi quarantine và commit JMS là hai resource khác nhau, vẫn cần xử lý cửa sổ lỗi giữa hai commit và idempotency.

### 7.3. Điều gì xảy ra khi không cấu hình error channel?

Trong message-driven adapter, nếu không có error channel, lỗi conversion/handler thường được ném về listener container; khi container transacted, rollback có thể xảy ra. Tuy nhiên nếu code handler tự bắt exception rồi không ném lại, không có error channel nào giúp cứu tình huống đó:

~~~java
try {
    paidOrderConsumer.consume(json);
} catch (Exception ex) {
    log.error("Order failed", ex);
    // Nuốt lỗi: listener có thể commit dù nghiệp vụ thất bại.
}
~~~

Ngược lại, khi lỗi tạm thời nên thử lại:

~~~java
try {
    paidOrderConsumer.consume(json);
} catch (org.springframework.dao.TransientDataAccessException ex) {
    log.warn("Temporary DB issue; let JMS listener roll back", ex);
    throw ex;
}
~~~

Hai đoạn trên là fragment bên trong service đã có `log`, không phải class độc lập. Cần phân loại exception và giới hạn retry; không mặc định mọi `RuntimeException` đều nên được giao lại nhiều lần.

## 8. Phân loại lỗi trước khi thiết kế retry

| Loại lỗi | Ví dụ | Retry nguyên JMS message có thể giúp? | Cách xử lý thường phù hợp |
|---|---|---|---|
| **Transient infrastructure** | DB mất kết nối, network timeout ngắn | Có thể | Rollback, exponential backoff có giới hạn |
| **Overload/throttling** | Pool connection cạn, HTTP 429 | Có thể sau khi giảm tải | Backoff, giới hạn concurrency, circuit breaker |
| **Permanent contract** | JSON sai cú pháp, schemaVersion không hỗ trợ | Không, nếu dữ liệu không thay đổi | Retry rất ít hoặc đưa DLQ sớm; sửa dữ liệu rồi replay |
| **Business rejection** | `orderId` không tồn tại, rule từ chối | Thường không nếu kết quả đã xác định | Ghi trạng thái từ chối; commit có chủ đích hoặc quarantine |
| **Duplicate event** | `eventId` đã xử lý | Không cần làm lại | Idempotent handler trả thành công để JMS commit |
| **Unknown outcome** | DB có thể đã commit nhưng JMS ack lỗi | Retry có thể xảy ra, gây lặp | Idempotency và tra cứu kết quả bền vững |

Một business rejection được xử lý có chủ đích **không nhất thiết là lỗi hạ tầng**. Ví dụ event `OrderPaid` đã được xử lý ở DB không nên rollback để broker gửi lại vô hạn; một handler idempotent nên nhận ra duplicate và kết thúc bình thường.

### Retry ở tầng Spring hay broker?

Có ít nhất ba cơ chế dễ bị nhầm:

1. **Retry trong method/service hoặc Spring Retry advice:** thử lại **ngay trong cùng một JMS delivery/callback**, trước khi quyết định throw về listener. Cần giới hạn số lần và thời gian tổng; giữ consumer bận quá lâu có thể làm queue nghẽn.
2. **Broker redelivery:** handler ném lỗi, JMS session rollback, broker quyết định **giao lại message** sau một khoảng delay và theo số lần giao tối đa.
3. **Replay từ DLQ:** khi điều kiện đã được sửa hoặc dữ liệu đã được thay đổi có kiểm soát, một operator/workflow **gửi lại** message tới luồng xử lý. Đây là một hoạt động vận hành có quản trị, không phải lần delivery tự động bình thường.

Từ Spring Integration 6.3, một số JMS message-driven endpoint hỗ trợ `RetryTemplate` và `RecoveryCallback` ở tầng listener/dispatch. Chức năng này phụ thuộc **version** và không thay thế broker redelivery/DLQ. Nếu bật cả Spring Retry và broker retries, **tổng số business attempts có thể là tích của hai mức**, ví dụ 3 lần thử trong callback × 5 broker deliveries = tối đa 15 lần gọi handler cho cùng event. Hãy đặt ngân sách thời gian, backoff và metric chung.

## 9. Broker DLQ: ví dụ Apache ActiveMQ Artemis

**Jakarta Messaging không chuẩn hóa một thuộc tính `deadLetterQueue` chung** cho mọi JMS provider. Phần lớn **DLQ là cấu hình của broker**, không được tạo bởi `JmsTemplate` hoặc Spring Integration khi một handler ném exception.

Ví dụ với **Apache ActiveMQ Artemis**, một `address-setting` có thể thiết lập:

~~~xml
<!-- Fragment trong phần <address-settings> của broker.xml Artemis. -->
<address-setting match="orders.paid.in">
    <dead-letter-address>DLA</dead-letter-address>
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
    <redelivery-delay-multiplier>2.0</redelivery-delay-multiplier>
    <max-redelivery-delay>15000</max-redelivery-delay>
    <auto-create-dead-letter-resources>true</auto-create-dead-letter-resources>
</address-setting>
~~~

**Đây là cấu hình broker Artemis, KHÔNG phải Spring Boot `application.yml` và KHÔNG phải Spring Integration XML.** Quản trị viên đặt nó trong cấu hình broker phù hợp, xác định address/queue mapping và cấp quyền truy cập. Tên `DLA` chỉ là ví dụ; khi bật tự tạo DLQ resources, Artemis có thể tạo địa chỉ/queue DLQ với quy ước prefix/suffix và bộ lọc theo original address.

Các thuộc tính:

- `redelivery-delay=1000`: lần redelivery đầu có thể chờ khoảng 1 giây thay vì quay lại ngay lập tức.
- `redelivery-delay-multiplier=2`: tăng thời gian đợi sau các lần thất bại tiếp theo.
- `max-redelivery-delay=15000`: chặn thời gian delay tăng quá trần cấu hình.
- `max-delivery-attempts=5`: Artemis áp dụng giới hạn số **delivery attempts** theo broker policy; khi vượt ngưỡng, message được chuyển sang **dead-letter-address** đã chỉ định.
- `auto-create-dead-letter-resources=true`: cho Artemis tạo các resource DLQ thích hợp khi cấu hình cho phép; không suy ra cùng tính năng ở broker khác.

**Nếu không đặt `dead-letter-address` trên Artemis mà message đạt ngưỡng delivery attempts, broker có thể loại bỏ message thay vì giữ nó ở DLQ.** Hãy xác minh address setting thực tế; một policy "thử 5 lần" nhưng không có nơi lưu message thất bại có thể gây mất dữ liệu cần điều tra.

### Backoff minh họa

| Delivery attempt | Giả sử handler vẫn lỗi | Delay trước attempt tiếp theo |
|---:|---|---:|
| 1 | Lỗi lần đầu | 1 giây |
| 2 | Vẫn lỗi | 2 giây |
| 3 | Vẫn lỗi | 4 giây |
| 4 | Vẫn lỗi | 8 giây |
| 5 | Vẫn lỗi | Chuyển theo DLQ policy, không tiếp tục retry trên source queue |

Các con số minh họa khi không có jitter/collision avoidance và broker tuân theo policy đã cấu hình. Trong thực tế, số lần giao đếm bởi broker, cách tính delay, khả năng failover và concurrency có thể ảnh hưởng thời điểm quan sát.

### DLQ trong Artemis và các metadata đi kèm

Artemis có thể ghi metadata về **original address/queue** và lý do di chuyển khi message được gửi sang dead-letter address; ví dụ property provider-specific như `_AMQ_ORIG_ADDRESS`. Các property này **không phải tiêu chuẩn di động Jakarta JMS**; chỉ đọc chúng sau khi kiểm tra tài liệu phiên bản Artemis đang chạy.

Không chỉ nhìn `JMSDestination` của message khi đã ở DLQ rồi suy ra queue ban đầu. Sau khi chuyển, destination hiện tại có thể là DLQ; nên lưu original destination và contract metadata trong hệ thống giám sát/quarantine.

## 10. So sánh với ActiveMQ Classic: cùng khái niệm, khác cấu hình

**Apache ActiveMQ Classic** có cách cấu hình redelivery/DLQ khác Artemis. Theo tài liệu của Classic:

- Redelivery policy có thể được điều khiển từ `ActiveMQConnectionFactory`/connection; tùy broker/client mà policy mặc định được truyền xuống hoặc override.
- Khi vượt `maximumRedeliveries`, client có thể gửi **Poison ACK** để broker chuyển message vào DLQ.
- Default DLQ của ActiveMQ Classic có tên `ActiveMQ.DLQ`; có thể thay bằng `individualDeadLetterStrategy` để phân tách theo source destination.

| Khía cạnh | Artemis | ActiveMQ Classic |
|---|---|---|
| Cấu hình chính | `address-setting` trong broker | Broker destination policy và client redelivery policy |
| Giới hạn lần thử | `max-delivery-attempts` | `maximumRedeliveries` theo redelivery policy |
| Điểm đến message thất bại | `dead-letter-address` và queue binding liên quan | `ActiveMQ.DLQ` mặc định hoặc individual DLQ |
| Backoff | `redelivery-delay`, multiplier, max delay... | `initialRedeliveryDelay`, multiplier và các tùy chọn client/broker |
| Thay cấu hình qua Spring Integration | Không tự đặt broker policy | Không tự đặt broker/client policy chỉ bằng error channel |

**Đừng sao chép cùng một số "5" từ `max-delivery-attempts` của Artemis sang `maximumRedeliveries` của Classic rồi khẳng định số callback giống nhau.** Thuộc tính của Classic tính số lần *redelivery*, còn Artemis nói về *delivery attempts*; cần thử với broker đang dùng để xác nhận tổng số lần consumer thực sự nhìn thấy message.

## 11. Broker DLQ khác `errorChannel`, retry queue và expiry address

Các hệ thống message-driven có nhiều “nơi chứa message lỗi”, nhưng chúng phục vụ mục đích khác nhau.

| Cơ chế | Ai điều khiển? | Khi nào dùng? | Có tự làm lại nghiệp vụ? |
|---|---|---|---|
| **Broker redelivery** | JMS provider/broker và trạng thái ack/transaction | Xử lý lại sau rollback | Có, nếu broker giao message lại |
| **Broker DLQ** | Redelivery/DLQ policy của broker | Message không thể giao/ xử lý thành công sau giới hạn | **Không**: cần operator/workflow replay |
| **Spring `errorChannel`** | IntegrationFlow và `ErrorMessage` | Quan sát, phân loại, xử lý exception | Không tự tạo broker redelivery |
| **Application quarantine** | Service/bảng DB/queue chuyên biệt | Giữ message lỗi có metadata, trạng thái xử lý | Chỉ khi có workflow tương ứng |
| **Retry queue/delayed queue** | Kiến trúc ứng dụng hoặc broker | Dời thời điểm thử lại, tách khỏi source queue | Có khi consumer/forwarder được cấu hình |
| **Expiry address/queue** | TTL/expiry policy của broker | JMS message hết hạn sử dụng | Thường không; không đồng nghĩa processing failure |

### Vì sao DLQ không phải `errorChannel`?

`ErrorMessage` là một **Spring Message** trong JVM, có thể chứa exception và failed input context. Trong khi đó, DLQ là **JMS destination** tại broker. Kênh `errorChannel` không tự cấu hình max delivery attempts hoặc chuyển JMS message sang broker DLQ. Broker thường chỉ biết message chưa được commit/ack và cần giao lại; khi vượt chính sách giới hạn, nó mới dead-letter.

Nếu muốn ứng dụng chủ động publish một message sang quarantine queue từ `errorChannel` rồi commit source message, cần thiết kế **bàn giao bền vững**. Gửi quarantine bằng kết nối/transaction khác và sau đó commit source JMS có thể tạo cửa sổ lỗi (gửi được quarantine nhưng source rollback → duplicate; source commit trước khi quarantine lưu → mất dấu). Không xem thao tác gửi error message bình thường là atomic với JMS receive.

### DLQ không phải expiry queue

Message có `timeToLive` hết hạn vì server quá chậm hoặc consumer offline lâu có thể được broker chuyển tới **expiry address** hoặc bị loại, tùy provider. Nó không nhất thiết đã từng được consumer thử xử lý và thất bại. Trên Artemis, `expiry-address` là một thuộc tính riêng với `dead-letter-address`.

Ví dụ TTL của `OrderPaid` chỉ 60 giây trong khi kế toán dừng 4 giờ: message có thể expire **dù converter/handler chưa từng được gọi**. Đặt durable subscription hoặc DLQ sẽ không tự làm TTL biến mất. Phải thống nhất thời gian lưu trữ với SLA nghiệp vụ.

## 12. Idempotency: xử lý an toàn khi message đến lại

### 12.1. Ranh giới giữa JMS transaction và DB transaction

~~~mermaid
sequenceDiagram
    participant Broker as JMS broker
    participant Listener as JMS listener
    participant DB as PostgreSQL

    Broker->>Listener: Deliver evt-1201
    Listener->>DB: BEGIN; insert eventId; update order
    DB-->>Listener: COMMIT thành công
    Note over Listener: Sự cố trước khi JMS commit
    Broker-->>Listener: Redelivery evt-1201
    Listener->>DB: Kiểm tra eventId đã xử lý
    DB-->>Listener: Đã có, bỏ qua tác động lặp
    Listener->>Broker: JMS commit
~~~

Một local JMS transaction có thể bao trùm nhận/gửi JMS trên cùng resource/session, nhưng **không tự atomic với PostgreSQL transaction**. Vì vậy xử lý theo kiểu **at-least-once delivery + idempotent consumer** là thiết kế quan trọng.

### 12.2. Lưu khóa đã xử lý trong cùng DB transaction

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sales_order (
    order_id VARCHAR(100) PRIMARY KEY,
    paid BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Service Java:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaidOrderService {
    private final JdbcTemplate jdbc;

    public PaidOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "orderDbTxManager")
    public void applyPayment(String eventId, String orderId) {
        int inserted = jdbc.update(
                "INSERT INTO processed_event(event_id) VALUES (?) "
                + "ON CONFLICT DO NOTHING", eventId);

        if (inserted == 0) {
            return; // Duplicate đã xử lý: không cập nhật thêm.
        }

        int updated = jdbc.update(
                "UPDATE sales_order SET paid = TRUE WHERE order_id = ?",
                orderId);
        if (updated != 1) {
            throw new IllegalStateException("Unknown order: " + orderId);
        }
    }
}
~~~

Giả sử `orderDbTxManager` là transaction manager PostgreSQL có sẵn và method được gọi qua Spring proxy. Bản ghi `processed_event` và cập nhật đơn nằm trong **cùng DB transaction**; nếu update fail, cả hai rollback. Khi broker redeliver cùng event, insert bị bỏ qua an toàn theo unique constraint.

Code minh họa cần được mở rộng ở production: validate `eventId`/`orderId` và schema trước khi gọi, xử lý race/transaction isolation, phân biệt duplicate hợp lệ với dữ liệu khác nhưng cùng event ID, và quy định thời hạn giữ deduplication record. **Không dùng `JMSXDeliveryCount` để quyết định đã ghi DB hay chưa.**

### 12.3. Từ DB sang JMS: transactional outbox

Khi nghiệp vụ cần **ghi database rồi phát một event JMS**, không nên giả định `@Transactional` trên DB khiến JMS send cùng commit. Ghi event vào **outbox table** trong cùng DB transaction với thay đổi nghiệp vụ; một publisher riêng gửi ra JMS và đánh dấu đã gửi. Nếu publisher crash sau khi gửi nhưng trước khi đánh dấu, event có thể xuất hiện hai lần, nên consumer vẫn phải idempotent.

### 12.4. Đếm delivery không giải quyết duplicate do producer

Một event có thể vào queue theo hai đường:

1. **Broker redelivery:** source message chưa JMS commit nên được nhận lại.
2. **Producer duplicate:** producer bị timeout/không rõ broker đã nhận hay chưa rồi gửi lại **một JMS message mới** với cùng business `eventId`.

Hai tình huống đều cần idempotency. Do đó DLQ/replay workflow cũng phải giữ hoặc ghi lại `eventId` ổn định khi gửi lại.

## 13. Topic subscription, concurrency và thứ tự sau redelivery

DLQ không chỉ áp dụng cho queue. Topic có thể có nhiều subscription độc lập; mỗi subscription có trạng thái nhận/ack/redelivery riêng theo provider. Một message `OrderPaid` có thể được kho xử lý thành công nhưng fail liên tục ở kế toán. Không suy ra sự thành công của một subscription đã làm message được xử lý ở mọi subscription.

| Tình huống | Rủi ro | Cách xem xét |
|---|---|---|
| Queue có 4 competing consumers | Redelivered event có thể đến consumer khác; hoàn tất không đúng thứ tự | Idempotency, version, message grouping nếu broker hỗ trợ |
| Topic có 3 subscription độc lập | Có 3 bản logic, kết quả thất bại khác nhau | Theo dõi backlog/DLQ theo subscription |
| Shared durable subscription | Nhiều consumer chia nhau event trong cùng subscription | Tính đúng đắn khi retry, ordering và client ID |
| Non-durable topic subscriber offline | Event publish lúc offline có thể không được lưu cho subscriber | Cân nhắc durable subscription và TTL |
| Broker delay redelivery một message | Event đến sau có thể được xử lý trước | Kiểm tra `aggregateVersion` hoặc ordering strategy |

Nếu một aggregate đòi hỏi xử lý đúng thứ tự, **rollback và redelivery trễ có thể làm thay đổi thứ tự quan sát**, đặc biệt khi nhiều consumer cùng queue. Có thể dùng message group/partition theo `orderId` nếu provider hỗ trợ, hoặc optimistic locking/version check ở database.

**Concurrency làm tăng số transaction JMS đồng thời**, không khiến bốn message thuộc một transaction chung. Rollback event A không rollback B đã được consumer khác commit.

## 14. Quy trình điều tra và replay DLQ an toàn

Đưa message vào DLQ chỉ là **bắt đầu** quy trình xử lý sự cố. Replay tất cả message trong DLQ ngay khi ứng dụng khởi động lại có thể phát tán dữ liệu lỗi, làm quá tải downstream và tạo tác động nghiệp vụ lặp.

### 14.1. Runbook đề xuất

1. **Tạm cô lập sự cố:** xác nhận queue/subscription nguồn, số message DLQ, tốc độ tăng và lỗi hiện tại. Không replay khi nguyên nhân vẫn đang lặp.
2. **Phân loại lỗi:** kết nối DB tạm thời, schema không tương thích, dữ liệu thiếu, business rejection hoặc bug mới sau deploy. Ghi `firstSeen`/`lastError`/`failureReason` ở hệ thống theo dõi.
3. **Xác định nguồn gốc:** đọc metadata original destination do broker cung cấp, `eventId`, `JMSMessageID`, thời gian publish và producer version. Không tin tuyệt đối vào property provider-specific của môi trường khác.
4. **Kiểm tra tính an toàn:** event đã tạo tác động DB chưa? `eventId` còn trong inbox không? TTL và hợp đồng dữ liệu có còn hiệu lực?
5. **Sửa trước khi replay:** deploy code hỗ trợ schema mới, khôi phục DB, hoặc tạo message đã được sửa trong quy trình có phê duyệt/audit. Không tự sửa payload tiền/tài chính mà không có kiểm soát nghiệp vụ.
6. **Replay từng lô nhỏ:** giới hạn số message/giây, giữ business `eventId` ổn định, theo dõi lỗi và chặn nguồn replay tự lặp lại.
7. **Xác nhận kết quả:** đối chiếu số message replay, số thành công, số còn lỗi, trạng thái DB và số DLQ mới phát sinh.
8. **Đóng sự cố:** lưu bằng chứng, cập nhật dashboard/alert, bảo đảm quy trình không làm mất hoặc lộ dữ liệu nhạy cảm.

~~~mermaid
flowchart TD
    A[("DLQ chứa message lỗi")] --> B["Phân loại + tra metadata"]
    B --> C{"Nguyên nhân đã khắc phục?"}
    C -->|"Chưa"| D["Giữ cách ly, cảnh báo"]
    C -->|"Rồi"| E{"Event đã xử lý theo eventId?"}
    E -->|"Có"| F["Đánh dấu duplicate, không phát lại nghiệp vụ"]
    E -->|"Chưa"| G["Replay có kiểm soát vào source destination"]
    G --> H["Theo dõi status + throughput + DLQ mới"]
    H --> I{"Thành công?"}
    I -->|"Có"| J["Audit kết quả"]
    I -->|"Không"| D
~~~

### 14.2. Replay và transaction boundary

Nếu một tool tiêu thụ message từ DLQ rồi gửi lại về original queue, hãy kiểm tra:

- Hai destination có cùng JMS broker/resource và có thể tham gia **cùng local JMS transaction** không?
- Việc nhận từ DLQ và gửi tới source được commit chung hay tách riêng? Nếu tách, cần chịu được duplicate/lost handoff.
- Message sau replay có `JMSMessageID`, `JMSXDeliveryCount` và `JMSRedelivered` giống trước không? **Không được giả định** chúng được giữ nguyên; business `eventId` nên là khóa liên kết ổn định.
- Có bảo tồn original payload, `contentType`, `schemaVersion`, event timestamp, correlation và authorization context theo hợp đồng không?
- DLQ message có thể chứa PII hoặc bí mật; ai được quyền đọc, sửa và replay?

Trong bài thực hành, **chỉ xem và replay trên broker thử nghiệm**. Trên production, replay phải có giới hạn tốc độ, xác nhận quyền và audit theo quy trình của tổ chức.

## 15. Observability: đo đúng nơi xảy ra thất bại

| Metric/sự kiện | Nguồn | Dấu hiệu bất thường |
|---|---|---|
| `source queue depth` | Broker | Backlog tăng liên tục |
| `oldest message age` | Broker | SLA đang bị vượt |
| `redelivery rate` | Broker/client metrics | Lỗi lặp lại hoặc downstream bất ổn |
| `JMSXDeliveryCount` phân phối | Message metadata | Nhiều message có count cao |
| `DLQ depth` và tốc độ tăng | Broker | Poison messages hoặc code mới lỗi |
| `DLQ age` | Broker | Có message chưa được điều tra quá lâu |
| `listener error count` theo exception | Spring Integration | Phân biệt conversion/DB timeout/business rule |
| `consumer count` / concurrency | Container và broker | Container chưa phục hồi hoặc DB bão hòa |
| `DB deduplication hits` | Business DB | Nhiều duplicate do replay, producer retry, JMS redelivery |
| `retry total duration` | App + broker | Một message giữ tài nguyên lâu, gây timeout chuỗi |
| `replay success/failure` | Re-drive workflow | Replay không giảm backlog hoặc tự gây DLQ mới |

**Logging khuyến nghị:** `eventId`, source destination, JMS message ID, correlation ID, redelivery flag/count khi có, error class, application version, tenant key đã được bảo vệ và processing time. Không log nguyên body có token, thông tin cá nhân hoặc số tài khoản. Khi cần giữ payload điều tra, sử dụng kho bảo mật/retention thích hợp và kiểm soát truy cập.

### Những cảnh báo nên có

- DLQ có message mới thuộc các event tài chính/đơn hàng quan trọng.
- `oldest message age` vượt SLA hoặc queue depth tăng dù consumer đang chạy.
- Tỷ lệ redelivery và DB timeout tăng đồng thời (dấu hiệu lỗi downstream).
- Một message gặp lỗi conversion lặp trên mọi instance (poison-message loop).
- Sau replay, DLQ mới lại tăng nhanh hoặc `eventId` duplicate vượt ngưỡng.

**Một dashboard đẹp không thay thế được điều tra tính đúng đắn của business state.** Với event quan trọng, phải đối soát dữ liệu ở DB/business system bên cạnh broker metrics.

## 16. Thực hành: cố ý tạo lỗi để hiểu redelivery và DLQ

**Môi trường:** Java 17+, Spring Integration/JMS, một JMS broker **ActiveMQ Artemis** thử nghiệm, queue `orders.paid.in`, PostgreSQL hoặc database thử nghiệm, và một JMS producer riêng. Dùng cấu hình listener `sessionTransacted(true)` ở mục 6 cùng broker redelivery/DLQ policy ở mục 9.

Ví dụ message hợp lệ:

~~~json
{
  "eventId": "evt-1201",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-1201",
  "amountMinor": 250000,
  "currency": "VND"
}
~~~

Ví dụ message lỗi vĩnh viễn:

~~~json
{
  "eventId": "evt-1202",
  "schemaVersion": 999,
  "eventType": "OrderPaid",
  "orderId": "ORD-1202"
}
~~~

Trong consumer, quy định `schemaVersion=999` chưa được hỗ trợ và **ném exception chưa được xử lý**. Đừng chỉ log rồi trả thành công nếu đang kiểm thử redelivery. Producer test có thể gửi:

~~~java
// Bean JmsTemplate của producer đã kết nối Artemis.
jmsTemplate.convertAndSend(
        "orders.paid.in",
        "{\"eventId\":\"evt-1202\",\"schemaVersion\":999,"
        + "\"eventType\":\"OrderPaid\",\"orderId\":\"ORD-1202\"}");
~~~

### Bài A — Happy path và JMS commit

1. Gửi `evt-1201` với `schemaVersion=1` và service xử lý bình thường.
2. Xác nhận handler được gọi, database cập nhật thành công và queue giảm.
3. Kiểm tra `JMSXDeliveryCount` lần nhận đầu thông thường là 1.
4. Xác minh event không tự vào DLQ chỉ vì có JMS header `JMSReplyTo` hoặc `JMSCorrelationID`; DLQ phụ thuộc thất bại giao/xử lý, không phụ thuộc header request-reply.

### Bài B — Lỗi hạ tầng tạm thời và redelivery

1. Cho handler ném exception mô phỏng mất database trong một khoảng thời gian ngắn.
2. Quan sát JMS rollback và `JMSRedelivered`/`JMSXDeliveryCount` trong các lần thử kế tiếp.
3. Đo khoảng delay, so sánh với `redelivery-delay` và multiplier của Artemis.
4. Phục hồi database trước khi vượt ngưỡng; xác minh message được xử lý thành công và không vào DLQ.
5. Đối chiếu DB để chắc chắn chỉ có một tác động nghiệp vụ.

### Bài C — Poison message và dead-letter address

1. Gửi `evt-1202` chứa `schemaVersion=999` không được hỗ trợ.
2. Đảm bảo lỗi conversion/validation được propagate về listener transacted.
3. Quan sát các lần giao lại; xác minh broker dừng giao message từ source sau giới hạn `max-delivery-attempts`.
4. Mở queue DLQ được Artemis tạo/cấu hình, xác minh có message cùng `eventId` và metadata nguồn.
5. Đặt một event hợp lệ `evt-1203` sau message lỗi rồi xác minh consumer vẫn có thể xử lý công việc hợp lệ theo broker queue/ordering policy.

### Bài D — Sự khác biệt giữa error channel và DLQ

1. Cấu hình `errorChannel`, error handler chỉ log rồi **trả bình thường**. Gửi lại event lỗi bằng một JMS message mới; quan sát listener có thể commit và source queue giảm mà DLQ không tăng.
2. Sửa handler để **ném lại exception**, chạy thử với một event ID mới; quan sát redelivery rồi DLQ theo broker policy.
3. Giải thích vì sao Spring `ErrorMessage` không tự biến thành JMS DLQ message.
4. Bổ sung metric phân loại exception để không đánh đồng schema error với DB timeout.

### Bài E — Transaction, duplicate và idempotency

1. Sử dụng `PaidOrderService.applyPayment` và bảng `processed_event`.
2. Cho DB commit thành công, sau đó mô phỏng một lỗi khiến JMS commit không hoàn tất (trong môi trường test có kiểm soát).
3. Khi event đến lại, kiểm tra unique `eventId` làm handler kết thúc bình thường mà không update lần hai.
4. Cho producer gửi lại **cùng `eventId` trong một JMS message mới**; xác minh idempotency vẫn hoạt động dù `JMSRedelivered` không phản ánh business duplicate.
5. Chèn `ExecutorChannel` trước DB handler và giải thích tại sao lỗi async không tự rollback JMS receive ban đầu.

### Bài F — Replay từ DLQ

1. Sửa code để hỗ trợ `schemaVersion=999` trong môi trường test, hoặc tạo một payload hợp lệ theo quy trình có kiểm soát.
2. Chọn một message từ DLQ, ghi lại original destination, `eventId`, nội dung cần thiết và lý do lỗi.
3. Replay một message rồi xác minh source consumer xử lý thành công.
4. Replay cùng event lần thứ hai; `processed_event` phải ngăn tác động nghiệp vụ trùng.
5. Tăng tốc độ replay từ 1 lên 10 msg/s trên môi trường test, quan sát pool DB, queue age và DLQ mới; dừng lại nếu error rate tăng.

### Ma trận kiểm thử tối thiểu

| Tình huống | Kết quả cần quan sát |
|---|---|
| Handler thành công | Source message được commit; không vào DLQ |
| Handler transacted ném exception tạm thời | Rollback, redelivery, sau phục hồi có thể thành công |
| Converter lỗi vĩnh viễn và error không bị nuốt | Retry giới hạn rồi DLQ theo broker policy |
| Error flow xử lý rồi không ném lại | Message có thể được commit, **không** có broker retry |
| Hai JMS consumers cùng queue | Duplicate/redelivery có thể đến consumer khác, không giả định giữ nguyên ordering |
| DB commit nhưng JMS rollback | Event đến lại nhưng business side effect không lặp |
| Producer retry bằng message ID mới | `eventId` vẫn phát hiện duplicate |
| Message hết TTL | Kiểm tra expiry policy, không mặc định vào processing DLQ |
| Replay một DLQ message | Giữ business ID, có audit, không gây DLQ loop |
| Broker restart/failover | Khả năng recovery và delivery count phù hợp provider/version |

**Phải dùng broker thật hoặc test container tương ứng để xác minh transaction, rollback, redelivery, DLQ và metadata.** Mock `JmsTemplate`, `MessageChannel` hoặc service chỉ chứng minh logic cục bộ, không mô phỏng đầy đủ broker delivery policy.

## 17. Câu hỏi tự đánh giá

1. Redelivery khác gì với việc producer gửi lại cùng một sự kiện bằng một JMS message mới?
2. Vì sao `JMSRedelivered=false` không chứng minh business event chưa từng được xử lý?
3. `JMSXDeliveryCount` bắt đầu từ giá trị nào? Vì sao không nên dùng nó làm khóa idempotency?
4. Điều kiện nào để exception trong handler dẫn tới rollback của JMS message-driven listener?
5. Nếu `errorChannel` nuốt exception, việc xử lý của broker có thể thay đổi thế nào?
6. Vì sao `JmsTemplate.sessionTransacted=true` trên polling source không tự bảo vệ handler downstream?
7. Khác biệt giữa **Spring Retry trong cùng callback**, **broker redelivery** và **DLQ replay** là gì?
8. `dead-letter-address` và `max-delivery-attempts` của Artemis được đặt ở đâu?
9. Nếu Artemis không có dead-letter address nhưng message đã vượt giới hạn, rủi ro là gì?
10. Tại sao không thể lấy `maximumRedeliveries=5` của ActiveMQ Classic suy ra cùng số callback như `max-delivery-attempts=5` của Artemis?
11. DLQ khác expiry address ở nguyên nhân và mục đích như thế nào?
12. Vì sao DLQ không nên được replay hàng loạt ngay khi ứng dụng vừa deploy bản sửa lỗi?
13. Khi DB commit nhưng JMS commit thất bại, làm thế nào để không ghi dữ liệu trùng?
14. Chuyển từ `DirectChannel` sang `ExecutorChannel` ảnh hưởng thế nào đến rollback và redelivery?
15. Nếu có nhiều subscription cùng topic, một subscription lỗi có làm các subscription khác đều phải redeliver không?
16. Những metric nào giúp phân biệt broker backlog, downstream transient failure và poison-message loop?

## 18. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): mặc định transacted cho message-driven adapter, transaction của polling adapter, `errorChannel` và conversion error.
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): `DefaultMessageListenerContainer`, `sessionTransacted`, transaction với JMS và giới hạn với DB.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, listener containers, acknowledgment và transaction.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `JMSRedelivered`, `JMSXDeliveryCount`, redelivery và acknowledgment semantics.
- [Apache ActiveMQ Artemis — Message Redelivery and Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages): `redelivery-delay`, `max-delivery-attempts`, `dead-letter-address` và delivery count persistence.
- [Apache ActiveMQ Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): cấu hình broker DLQ, auto-create dead-letter resources và expiry address.
- [ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling): redelivery policy, Poison ACK, `ActiveMQ.DLQ` và individual DLQ.
- [ActiveMQ Classic — Redelivery Policy](https://activemq.apache.org/components/classic/documentation/redelivery-policy): các thuộc tính `maximumRedeliveries`, initial delay và backoff.

**Ghi nhớ:** redelivery là khả năng broker giao lại một JMS message chưa được xác nhận, còn DLQ là nơi cách ly message sau khi chính sách xử lý thất bại được áp dụng. Trong Spring Integration, muốn broker redeliver phải đặt đúng **JMS transaction/acknowledge boundary** và không vô tình nuốt exception bằng `errorChannel`. Retry delay, max attempts, DLQ và expiry là cấu hình **broker/provider-specific**; idempotency theo `eventId`, monitoring và replay có kiểm soát mới bảo vệ được tính đúng đắn của nghiệp vụ khi gặp lỗi và xử lý lặp.



