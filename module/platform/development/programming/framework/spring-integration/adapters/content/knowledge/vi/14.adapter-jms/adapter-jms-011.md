# Temporary reply destination trong JMS

## 1. Bài toán: nhận phản hồi mà không phải tạo sẵn một reply queue

Ứng dụng bán hàng muốn kiểm tra tồn kho trước khi xác nhận đơn `ORD-1101`. Dịch vụ kho chỉ cung cấp JMS: nhận yêu cầu trên queue `inventory.check.requests` và trả kết quả bằng JMS message. Ứng dụng bán hàng phải biết **phản hồi được gửi về đâu**, **phản hồi thuộc request nào**, và **đợi tối đa bao lâu**.

Một cách đơn giản là tạo **temporary reply destination**. Ứng dụng gọi tạo một JMS destination tạm, đặt destination đó vào header `JMSReplyTo` của request, đợi reply trên destination tạm rồi giải phóng tài nguyên khi hoàn tất. Không cần tạo sẵn một queue reply dùng chung cho mọi client.

Trong module **SPRING_INTEGRATION_ADAPTERS**, outbound adapter, inbound adapter, gateway, poller và `MessageChannel` kết nối hệ thống ngoài với các flow của Spring Integration. Với JMS, temporary reply destination là cơ chế nền tảng của **request-reply gateway**, liên quan trực tiếp tới hợp đồng payload/header, xử lý timeout, lỗi, quản lý kết nối và vòng đời consumer. Khác với file, SFTP, HTTP, AMQP, Kafka hay database, JMS có khái niệm `JMSReplyTo` trỏ tới chính một đối tượng `Destination` do client cấp.

**Sau bài học, bạn cần có thể:**

1. Giải thích `TemporaryQueue`/`TemporaryTopic`, phạm vi sở hữu theo JMS `Connection` và hạn chế về consumer.
2. Phân biệt request queue, temporary reply queue, fixed reply queue và Spring `replyChannel`.
3. Cấu hình `JmsTemplate.sendAndReceive(...)` và Spring Integration `Jms.outboundGateway(...)` với destination tạm.
4. So sánh **mỗi request một temporary destination** với **reply listener dùng chung một temporary destination cho mỗi gateway**.
5. Giải thích correlation ID, timeout, late reply, broker reconnect, retry/idempotency và rủi ro cache consumer.
6. Kiểm chứng hành vi bằng một JMS broker thật, không suy diễn từ mock service.

## 2. `TemporaryQueue`, `TemporaryTopic` và `JMSReplyTo` là gì?

JMS có giao diện `jakarta.jms.Destination`; `Queue` và `Topic` là hai kiểu destination phổ biến. Jakarta Messaging còn có:

- `jakarta.jms.TemporaryQueue`: queue được hệ thống sinh riêng cho một JMS connection, thường được dùng làm địa chỉ nhận reply.
- `jakarta.jms.TemporaryTopic`: topic tạm có phạm vi kết nối tương tự, chỉ nên dùng khi provider và kiểu giao thức trả lời thực sự yêu cầu.
- `Message.getJMSReplyTo()` / `Message.setJMSReplyTo(Destination)`: header JMS cho phía server biết destination mà **client mong muốn nhận phản hồi**.

### Các quy tắc vòng đời chuẩn Jakarta Messaging

| Thuộc tính | Quy tắc |
|---|---|
| Ai tạo? | Một JMS `Session` hoặc `JMSContext` tạo temporary destination trên JMS provider |
| Ai có quyền **nhận**? | Chỉ những consumer thuộc **cùng connection đã tạo** temporary destination mới được nhận |
| Ai có thể **gửi**? | Producer từ connection khác có thể gửi tới temporary destination khi có reference và quyền broker phù hợp |
| Tồn tại bao lâu? | Phạm vi sống là **connection sở hữu**, hoặc đến khi destination bị xóa chủ động |
| Khi connection bị đóng? | Temporary destination không còn; nội dung chờ có thể bị mất |
| Có phải queue bền vững để khôi phục sau restart? | **Không**; không dựa vào temporary destination để giữ reply qua mất connection |
| Có phải mỗi `Session` có reply queue riêng? | Không nhất thiết; session tạo chỉ là nơi gọi API, **phạm vi sở hữu là connection** |

Temporary destination không phải một tên queue cấu hình sẵn trong hệ thống. Broker thường phát sinh định danh nội bộ duy nhất; giá trị đó phụ thuộc provider. Không hard-code hoặc lưu tên temporary queue vừa quan sát được làm tên cấu hình cho lần khởi động tiếp theo.

**Điểm dễ nhầm:** chỉ connection sở hữu mới được tạo consumer nhận từ temporary destination; **server vẫn có thể gửi reply từ connection khác**. Nếu cả hai phía đều bắt buộc dùng cùng connection thì request-reply giữa hai dịch vụ sẽ không hoạt động; JMS không có yêu cầu đó.

### Request queue và reply destination là hai đích khác nhau

| Thành phần | Ví dụ | Ai sử dụng? | Mục đích |
|---|---|---|---|
| JMS request destination | `inventory.check.requests` | Client gửi, server nhận | Giao một request cho consumer xử lý |
| Temporary reply destination | `TemporaryQueue` do broker tạo | Server gửi, client sở hữu connection nhận | Trả kết quả cho client đang đợi |
| Fixed reply destination | `inventory.check.replies` | Được quản trị và các client có quyền truy cập | Thay thế temporary reply khi cần địa chỉ cố định |
| Spring `replyChannel` | `inventoryResponses` hoặc reply channel tạm | Spring Integration nội bộ | Trả **Spring Message**, không phải JMS message |

`JMSReplyTo` là **JMS header**, còn `replyChannel` là **Spring Message header/channel**. Một JMS outbound gateway nối hai thế giới này; chúng không được hoán đổi cho nhau.

## 3. Vòng đời request-reply với một temporary queue

~~~mermaid
sequenceDiagram
    participant App as Spring caller
    participant Gateway as JMS outbound gateway
    participant Broker as JMS broker
    participant Server as Inventory service

    App->>Gateway: Spring request (req-1101)
    Gateway->>Broker: Tạo TemporaryQueue trên client connection
    Gateway->>Broker: Gửi JMS request vào inventory.check.requests
    Note over Gateway,Broker: JMSReplyTo trỏ đến TemporaryQueue
    Broker->>Server: Deliver request
    Server->>Server: Validate và xử lý
    Server->>Broker: JMS reply tới request.JMSReplyTo
    Broker-->>Gateway: Reply trên TemporaryQueue
    Gateway-->>App: Spring reply
    Gateway->>Broker: Giải phóng temporary destination theo chế độ gateway
~~~

Trình tự về mặt logic:

1. Caller phát Spring Message tới outbound gateway hoặc gọi một Spring messaging gateway interface.
2. Gateway chọn request queue và chuẩn bị reply destination tạm. Gateway gắn đối tượng đó vào `JMSReplyTo` khi gửi request.
3. Hệ thống kho nhận request, đọc `JMSReplyTo`, tạo JMS reply và gửi **tới đúng destination được cung cấp**.
4. Gateway nhận reply, ánh xạ JMS body/headers thành Spring Message, ghép với lời gọi đang đợi rồi đưa về Spring reply channel.
5. Reply consumer và temporary destination được đóng/xóa theo **chế độ receive của gateway**, không nhất thiết cùng lúc với việc đóng toàn bộ connection.

### Phân biệt ba định danh

- `JMSMessageID`: ID do provider cấp cho **mỗi lần gửi JMS message**.
- `JMSCorrelationID`: ID mà client/server thống nhất để nối một reply với một request trong giao thức JMS.
- `requestId`: khóa **nghiệp vụ** trong payload JSON, cần ổn định nếu phải retry cùng lệnh.

Với một **temporary queue riêng cho từng request**, bản thân queue đã cô lập reply của request đó; không nhất thiết cần selector dựa vào `JMSCorrelationID` để tìm reply. Tuy nhiên, server **nên thực hiện hợp đồng correlation rõ ràng**, chẳng hạn đặt `JMSCorrelationID` của reply bằng `JMSMessageID` của request. Đặc biệt khi chuyển sang fixed reply queue, correlation trở thành yếu tố bắt buộc để tránh ghép nhầm.

### Contract JSON minh họa

Request:

~~~json
{
  "requestId": "req-1101",
  "schemaVersion": 1,
  "operation": "checkStock",
  "orderId": "ORD-1101"
}
~~~

Reply:

~~~json
{
  "requestId": "req-1101",
  "schemaVersion": 1,
  "resultCode": "OK",
  "orderId": "ORD-1101",
  "availability": "AVAILABLE"
}
~~~

Đây chỉ là hợp đồng nghiệp vụ. `requestId` trong JSON không tự chuyển thành `JMSCorrelationID`. JMS header được gateway/provider đặt theo cấu hình, còn payload cần được validate độc lập tại mỗi phía.

## 4. Ví dụ với `JmsTemplate.sendAndReceive(...)`

Spring Framework cung cấp cách request-reply JMS đơn giản bằng `JmsTemplate.sendAndReceive(...)`. Phương thức này **tạo temporary queue như một phần của mỗi operation**, gắn nó vào `JMSReplyTo` của request, gửi request và đợi JMS reply trên queue vừa tạo.

Với Spring Framework 6+ và Jakarta JMS:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

public class InventoryJmsClient {
    private final JmsTemplate template;

    public InventoryJmsClient(JmsTemplate template) {
        this.template = template;
    }

    public String checkStock(String requestJson) throws JMSException {
        // Nên cấu hình giá trị này trên bean lúc khởi tạo, không thay đổi lúc chạy đa luồng.
        Message reply = template.sendAndReceive(
                "inventory.check.requests",
                session -> session.createTextMessage(requestJson));

        if (reply == null) {
            throw new IllegalStateException("Không nhận được reply trước timeout");
        }
        if (!(reply instanceof TextMessage textReply)) {
            throw new IllegalStateException("Reply không phải TextMessage");
        }
        return textReply.getText();
    }
}
~~~

Để cấu hình thời gian chờ trên bean:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@Bean("inventoryJmsTemplate")
public JmsTemplate inventoryJmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setReceiveTimeout(5000); // Đợi reply tối đa 5 giây.
    return template;
}
~~~

Các đoạn code giả định bean `ConnectionFactory` đã trỏ tới JMS broker và request queue được tạo/quyền truy cập hợp lệ. `JmsTemplate` là bean có thể dùng lại sau cấu hình; **không gọi `setReceiveTimeout(...)` luân phiên giữa các request đang chạy trên nhiều thread**.

**Phân biệt:** `JmsTemplate.sendAndReceive(...)` là API của **Spring JMS**. Nó không tự tạo IntegrationFlow, `MessageChannel` hoặc Spring Integration gateway. Khi ứng dụng đã xây dựng một flow với transformer, router, filter và error channel, thường nên dùng **JMS outbound gateway**; `sendAndReceive` hữu ích để hiểu cơ chế hoặc viết một client JMS nhỏ.

### Server xử lý `JMSReplyTo`

Đối với server JMS tự triển khai, phần gửi reply quan trọng có dạng sau:

~~~java
// Đây là fragment bên trong callback JMS server có "request" và "session".
jakarta.jms.Destination replyTo = request.getJMSReplyTo();
if (replyTo == null) {
    throw new jakarta.jms.JMSException("Request không có JMSReplyTo");
}

jakarta.jms.TextMessage response =
        session.createTextMessage(resultJson);
response.setJMSCorrelationID(request.getJMSMessageID());

jakarta.jms.MessageProducer producer = session.createProducer(replyTo);
try {
    producer.send(response);
} finally {
    producer.close();
}
~~~

`resultJson` là chuỗi JSON đã được business service tạo và validate. Fragment minh họa trách nhiệm của server; trong production cần xem cách listener container cung cấp `Session` và quản lý transaction, tránh tự can thiệp session lifecycle sai thời điểm.

**Sai lầm điển hình:** server luôn gửi reply vào `inventory.check.replies` cố định dù request có `JMSReplyTo` tạm. Client tạo temporary queue sẽ đợi mãi trên queue đó; hai phía đều có thể log “gửi thành công” nhưng reply không đến đúng nơi.

## 5. Java DSL của Spring Integration: temporary reply mặc định

Spring Integration có `Jms.outboundGateway(connectionFactory)`. Khi không cấu hình `replyDestination(...)`, **outbound gateway dùng temporary reply destination**, mặc định là `TemporaryQueue`.

### 5.1. Flow phía client

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class InventoryClientConfiguration {

    @Bean
    public IntegrationFlow inventoryRequestFlow(
            ConnectionFactory connectionFactory) {

        return IntegrationFlow
                .from("inventoryRequestChannel")
                .handle(Jms.outboundGateway(connectionFactory)
                        .requestDestination("inventory.check.requests")
                        .receiveTimeout(5000))
                .get();
    }
}
~~~

Không có `replyDestination(...)` là **một lựa chọn có chủ đích**, không phải thiếu cấu hình. Gateway dùng JMS reply destination tạm và đưa kết quả vào reply path của Spring Integration. `receiveTimeout(5000)` quy định thời gian JMS outbound gateway chờ reply, tính bằng mili giây.

### 5.2. Interface nghiệp vụ gọi gateway

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface InventoryQueryPort {

    @Gateway(
            requestChannel = "inventoryRequestChannel",
            replyTimeout = 7000)
    String checkStock(String requestJson);
}
~~~

`@IntegrationComponentScan` trong cấu hình mục 5.1 giúp phát hiện interface `@MessagingGateway`. Service gọi `inventoryQueryPort.checkStock(json)` mà không biết JMS `Session` hay `TemporaryQueue`.

**Có hai lớp timeout:** `receiveTimeout(5000)` của JMS gateway là thời gian chờ JMS reply; `@Gateway(replyTimeout=7000)` của Spring messaging gateway là thời gian chờ Spring reply. Không nên đặt hai giá trị tùy tiện bằng nhau rồi giả định đó là một bộ đếm duy nhất.

### 5.3. Server Spring Integration dùng JMS inbound gateway

Ở **ứng dụng server riêng biệt**, có thể dùng inbound gateway:

~~~java
@Bean
public IntegrationFlow inventoryServerFlow(
        ConnectionFactory connectionFactory,
        InventoryStockService inventoryStockService) {

    return IntegrationFlow
            .from(Jms.inboundGateway(connectionFactory)
                    .requestDestination("inventory.check.requests"))
            .handle(String.class, (requestJson, headers) ->
                    inventoryStockService.createReplyJson(requestJson))
            .get();
}
~~~

`InventoryStockService` là interface/service tự triển khai, có method `String createReplyJson(String requestJson)`. Nó cần parse/validate request và trả `String` JSON. JMS inbound gateway sử dụng `JMSReplyTo` trên request để gửi JMS reply, nếu contract và hạ tầng cho phép; không cần hard-code một queue reply tạm được đặt tên bởi client.

Hai flow phía client và server là **hai ứng dụng hoặc hai role khác nhau**. Không triển khai cả hai trong một ứng dụng rồi hiểu nhầm đó là yêu cầu kiến trúc thực tế; chúng được đặt cạnh nhau để minh họa đường đi.

## 6. Hai chế độ temporary reply queue của outbound gateway

**Spring Integration outbound gateway có hai cách nhận reply quan trọng.** Chọn chế độ nào ảnh hưởng trực tiếp đến số temporary destination/consumer được tạo, cách correlation và chi phí hoạt động.

### 6.1. Không dùng reply listener: mỗi request một temporary queue

Đây là cách hoạt động mặc định khi không cấu hình reply listener và cũng không chỉ định reply destination:

~~~text
Request A -> TemporaryQueue A -> Reply A -> xóa TemporaryQueue A
Request B -> TemporaryQueue B -> Reply B -> xóa TemporaryQueue B
Request C -> TemporaryQueue C -> Reply C -> xóa TemporaryQueue C
~~~

Theo tài liệu Spring Integration, một `TemporaryQueue` được tạo cho **mỗi request** và xóa khi request kết thúc, dù thành công hay hết thời gian chờ/lỗi. Mỗi lần nhận reply sử dụng consumer gắn với reply destination của request đó. Vì mỗi request có một destination riêng, không cần một JMS selector chung để tách reply A và B.

**Ưu điểm:** cơ chế cô lập reply dễ hiểu; không cần queue reply vật lý hoặc listener dùng chung được định cấu hình trước.

**Giới hạn:** tạo/xóa temporary destinations và consumers liên tục có thể tốn tài nguyên broker/provider ở lưu lượng cao. Nếu mỗi giây có nhiều request, phải đo số destination/consumer đang tồn tại và chi phí thiết lập, thay vì mặc định cách này là miễn phí.

### 6.2. Có reply listener: một temporary queue cho mỗi gateway

Từ Spring Integration 2.2, outbound gateway có thể sử dụng một **`MessageListenerContainer` dành cho reply** thay vì tạo consumer mới để nhận từng reply. Khi không cấu hình `replyDestination`, reply listener sử dụng **một temporary queue cho mỗi instance gateway**; gateway tạo lại temporary queue khi cần phục hồi sau mất connection.

~~~mermaid
flowchart LR
    subgraph G["Một JMS outbound gateway instance"]
        A["Request A"]
        B["Request B"]
        C["Request C"]
        Map["Bảng request đang chờ / correlation"]
        Listener["Reply listener container"]
    end
    A --> R[("inventory.check.requests")]
    B --> R
    C --> R
    R --> S["Inventory service"]
    S --> T[("Một TemporaryQueue của gateway")]
    T --> Listener
    Listener --> Map
    Map --> A
    Map --> B
    Map --> C
~~~

Mỗi request vẫn mang `JMSReplyTo` tới **cùng temporary queue của gateway**. Gateway dựa trên thông tin request/message ID để đưa reply về đúng lời gọi đang đợi. Server cần bảo toàn hợp đồng tương quan phản hồi; một cách phổ biến là trả `JMSCorrelationID` bằng `JMSMessageID` của request. Với chế độ temporary reply listener này, **không phải cấu hình thêm một `correlationKey` tùy biến** như trường hợp reply queue cố định dùng chung.

**Ưu điểm:** giảm việc tạo/xóa temporary destination và reply consumer trên mỗi request; thích hợp khi gateway xử lý nhiều request đồng thời hoặc lưu lượng cao.

**Giới hạn:** reply listener/connection là tài nguyên chạy theo lifecycle gateway; phải theo dõi số request đang đợi, listener health, timeout và mất connection. Có nhiều gateway bean thì vẫn có thể có nhiều temporary queues, không phải một temporary queue chung cho toàn ứng dụng hoặc toàn cluster.

### 6.3. Java DSL: bật reply container

Thay cấu hình outbound gateway ở mục 5 bằng:

~~~java
@Bean
public IntegrationFlow inventoryRequestWithReplyListener(
        ConnectionFactory connectionFactory) {

    return IntegrationFlow
            .from("inventoryRequestsWithListener")
            .handle(Jms.outboundGateway(connectionFactory)
                    .requestDestination("inventory.check.requests")
                    .receiveTimeout(5000)
                    .replyContainer())
            .get();
}
~~~

`.replyContainer()` tạo cấu hình reply listener mặc định. Nếu muốn cấu hình listener cụ thể (theo Java DSL 6.x+), có thể dùng:

~~~java
.handle(Jms.outboundGateway(connectionFactory)
        .requestDestination("inventory.check.requests")
        .receiveTimeout(5000)
        .replyContainer(listener ->
                listener.concurrentConsumers(1)
                        .recoveryInterval(5000L)))
~~~

Đây là fragment để đặt trong `IntegrationFlow`, không phải một method Java độc lập. Thông thường một consumer reply listener có thể xử lý nhiều reply nhanh vì nhiệm vụ chính của nó là dispatch kết quả tới các request đang chờ; chỉ tăng concurrency sau khi đo tải.

**Không tạo đồng thời hai flow ở mục 5 và 6 trên cùng request channel rồi kỳ vọng chỉ gửi một request.** Chúng là các **phương án cấu hình thay thế** để so sánh. Nếu cần chạy cùng ứng dụng để A/B test, đặt tên channel khác nhau và định tuyến caller có chủ đích.

### 6.4. XML namespace có reply listener

~~~xml
<int:channel id="inventoryRequests"/>
<int:channel id="inventoryResults"/>

<int-jms:outbound-gateway
        id="inventoryOutboundGateway"
        connection-factory="jmsConnectionFactory"
        request-destination-name="inventory.check.requests"
        request-channel="inventoryRequests"
        reply-channel="inventoryResults"
        receive-timeout="5000">
    <int-jms:reply-listener
            concurrent-consumers="1"/>
</int-jms:outbound-gateway>
~~~

Đây là **fragment XML** cần namespace `int`, `int-jms`, bean `jmsConnectionFactory` và consumer của `inventoryResults`. Không có `reply-destination-name` nên reply listener dùng temporary destination do gateway tạo. Nếu dùng Java DSL ở trên, không đăng ký thêm XML gateway cùng mục đích ngoài chủ ý.

### 6.5. Bảng so sánh

| Tiêu chí | Temporary queue mỗi request | Temporary queue với reply listener |
|---|---|---|
| Cấu hình Spring Integration | Không có `replyDestination`, không có reply listener | Không có `replyDestination`, **có `replyContainer()`** |
| Số temporary queues | Một queue cho request đang chờ | Một queue cho mỗi gateway đang hoạt động |
| Reply consumer | Gắn với từng request | Container nhận reply dùng chung |
| Correlation | Destination riêng cô lập reply | Gateway dispatch reply tới request tương ứng |
| Khi mất connection | Temporary queues hiện có mất hiệu lực | Listener/container recovery và tạo temporary queue mới khi cần |
| Tải cao | Có thể tạo/xóa nhiều destination, consumer | Giảm churn, nhưng vẫn cần theo dõi số request in-flight |
| Phạm vi reply | Lời gọi đang chờ; không có phục hồi bền vững | Các lời gọi đang chờ của một gateway; không lưu bền qua restart |

## 7. Fixed reply queue: khi nào không dùng temporary destination?

Một số JMS provider hoặc môi trường enterprise yêu cầu:

- Destination được provision trước và được quản trị bằng ACL/JNDI.
- Client không có quyền tạo temporary destination.
- Hệ thống có yêu cầu phân tích/giám sát riêng trên một reply queue tồn tại lâu dài.
- Gateway và hệ thống nhận cần một **reply queue cố định** vì hạn chế routing/broker liên thông.

Khi đó, thay temporary queue bằng `replyDestination("inventory.check.replies")` hoặc bean `Destination` tương ứng. Nhưng **một reply queue cố định có thể phục vụ nhiều request và nhiều gateway**; correlation phải được cấu hình đúng.

### 7.1. Ví dụ fixed reply queue có reply listener và correlation key

~~~java
.handle(Jms.outboundGateway(connectionFactory)
        .requestDestination("inventory.check.requests")
        .replyDestination("inventory.check.replies")
        .correlationKey("JMSCorrelationID")
        .receiveTimeout(5000)
        .replyContainer())
~~~

Đoạn này là fragment Java DSL. `correlationKey("JMSCorrelationID")` cho phép gateway tạo và sử dụng correlation ID mà server cần echo trên JMS reply. Với reply listener, Spring Integration có cơ chế selector/correlation riêng cho từng gateway instance khi cấu hình phù hợp.

**Cảnh báo:** cấu hình **fixed reply destination + reply listener nhưng không có correlation key** không được dùng như một mode hợp lệ với một reply listener chia sẻ queue. Spring Integration có thể ghi warning và quay về cơ chế tạo consumer/selector theo từng request, gây rủi ro hiệu năng và caching. Đừng chỉ thêm `.replyContainer()` vào một fixed reply queue mà bỏ qua hợp đồng correlation.

### 7.2. Rủi ro `CachingConnectionFactory.cacheConsumers=true`

Với một **fixed reply queue** nhưng không dùng reply listener, gateway thường tạo consumer có **selector riêng cho từng request** dựa trên `JMSCorrelationID` hoặc message ID. Nếu `CachingConnectionFactory` cache consumers, mỗi selector khác nhau có thể để lại một consumer không còn dùng trong cache, dẫn tới tăng bộ nhớ/tài nguyên.

Vì vậy khi dùng fixed reply queue:

1. Ưu tiên reply listener với correlation key đã cấu hình và kiểm chứng.
2. Nếu dùng per-request consumer, tránh `cacheConsumers=true` trong connection factory áp dụng cho gateway.
3. Đo số consumer/session, broker connections và heap trên thử nghiệm tải, đặc biệt sau hàng chục nghìn requests.

| Cách nhận reply | Destination | Correlation | Hệ quả vận hành |
|---|---|---|---|
| Temporary riêng từng request | Broker sinh cho mỗi request | Không cần selector chung; vẫn nên echo chuẩn JMS correlation | Tạo/xóa destination liên tục |
| Temporary chung theo gateway | Broker sinh cho một gateway có reply listener | Gateway ghép message về lời gọi đang đợi | Dùng listener chung; mất connection sẽ phải tạo lại |
| Fixed queue, consumer riêng mỗi request | Queue đã provision | Selector theo ID request | Cẩn trọng consumer caching |
| Fixed queue, reply listener | Queue đã provision | **Correlation key bắt buộc cấu hình phù hợp** | Có thể share queue giữa nhiều gateway, phải kiểm thử selector |

### 7.3. Vì sao không chuyển một cách tùy tiện sang Topic?

Với reply queue cố định, reply thường cần tới **một client/request**. Nếu dùng topic, việc subscriber không sẵn sàng đúng lúc publish, non-durable subscription hoặc cạnh tranh nhiều subscription có thể làm reply bị mất/nhân bản không mong muốn. Spring Integration khuyến nghị không dùng topic cho một số chiến lược fixed reply không có reply listener.

**Mặc định nên dùng queue cho reply**, trừ khi protocol và khả năng provider đã được kiểm chứng cho topic.

## 8. `TemporaryTopic` trong Spring Integration 6+

Từ **Spring Integration 6.0**, khi outbound gateway không có reply destination cố định và được cấu hình `replyPubSubDomain(true)`, gateway sử dụng **`TemporaryTopic` thay cho `TemporaryQueue`**.

~~~java
.handle(Jms.outboundGateway(connectionFactory)
        .requestDestination("inventory.check.requests")
        .replyPubSubDomain(true)
        .receiveTimeout(5000))
~~~

Đoạn DSL trên là **một lựa chọn tùy biến**, không phải khuyến nghị mặc định. Request destination vẫn là queue nếu không cấu hình `requestPubSubDomain(true)`; cờ `replyPubSubDomain` chỉ liên quan reply domain.

Các điểm phải xem xét:

- Temporary topic cũng thuộc vòng đời JMS connection; chỉ connection sở hữu được tạo consumer cho nó.
- Temporary topic **không phải durable topic subscription** dành cho client offline. Khi connection đóng, destination không còn.
- Một số JMS provider xử lý temporary queue và temporary topic khác nhau; phải thử khả năng tạo, ACL, reconnect và resource cleanup.
- Với request-reply thông thường, `TemporaryQueue` dễ hiểu và phổ biến hơn. Không bật `replyPubSubDomain(true)` chỉ vì nghĩ topic luôn nhanh hơn.

## 9. Correlation: destination riêng không loại bỏ nhu cầu hợp đồng rõ ràng

### 9.1. Mẫu correlation dựa trên `JMSMessageID`

~~~text
Client gửi request:
    JMSMessageID      = ID:request-1101
    JMSReplyTo        = TemporaryQueue:client-xyz
    payload.requestId = req-1101

Server gửi reply:
    JMSCorrelationID  = ID:request-1101
    Destination       = TemporaryQueue:client-xyz
    payload.requestId = req-1101
~~~

Đây là một **mẫu hợp đồng phổ biến**: server lấy `request.getJMSMessageID()` gán vào `reply.setJMSCorrelationID(...)`. Gateway có thể dựa trên correlation để dispatch reply trong các chế độ dùng shared destination; riêng temporary destination mỗi request còn cô lập về địa chỉ.

### 9.2. Mẫu correlation do client cấp

Trong một hệ thống dùng fixed reply queue, client có thể tạo `JMSCorrelationID` và yêu cầu server **echo chính giá trị đó**:

~~~text
Client: JMSCorrelationID=corr-1101; JMSReplyTo=inventory.check.replies
Server: JMSCorrelationID=corr-1101; gửi tới inventory.check.replies
~~~

Hai kiểu hợp đồng không phải cùng một mode của gateway. Nếu server luôn echo `JMSMessageID` nhưng client dùng selector chờ `JMSCorrelationID=corr-1101`, client sẽ timeout dù reply đã đến queue. Cần thống nhất và kiểm thử cả hai phía.

### 9.3. Business request ID không thay thế JMS correlation

`requestId` là định danh **hành động nghiệp vụ**. Một request có thể được gửi lại dưới JMS message ID khác sau timeout, nhưng **nên giữ cùng requestId** để server phát hiện lặp. Khi dùng temporary queue mỗi request, JMS correlation không phải cơ chế idempotency. Khi dùng fixed shared reply queue, requestId trong JSON cũng không thay thế selector trên JMS metadata nếu không có routing đã định nghĩa.

## 10. Timeout và late reply: điều gì xảy ra khi server quá chậm?

Giả sử client đợi tối đa 5 giây nhưng server mất 8 giây:

~~~mermaid
sequenceDiagram
    participant Client as Client gateway
    participant Broker as Broker
    participant Server as Inventory service
    Client->>Broker: Request req-1101 / JMSReplyTo=temp-1
    Broker->>Server: Deliver request
    Note over Client: Hết receiveTimeout 5 giây
    Client-->>Client: Timeout / giải phóng wait
    Note over Broker: Per-request temp queue có thể đã bị xóa
    Server->>Broker: Reply req-1101 sau 8 giây
    Broker-->>Server: Có thể từ chối/loại reply nếu destination hết hiệu lực
~~~

Với **temporary queue riêng cho từng request**, Spring Integration xóa temporary queue khi request kết thúc, kể cả trường hợp timeout. Khi server gửi reply muộn, provider có thể báo destination không tồn tại hoặc không còn nhận reply; không có cơ chế chung để “trả lại reply” cho lần request đã hết hạn.

Với **temporary queue có reply listener**, queue có thể còn tồn tại vì các request khác đang dùng gateway, nhưng lời gọi req-1101 đã hết thời gian chờ. Gateway cần xử lý reply muộn/không còn in-flight mapping; **đừng mặc định nó sẽ được trả cho một request mới**.

### Các loại timeout không thể thay thế nhau

| Timeout/TTL | Nằm ở đâu? | Điều khiển |
|---|---|---|
| `JmsTemplate.receiveTimeout` | Spring JMS client | Một lần `sendAndReceive` chờ reply tối đa bao lâu |
| `JmsOutboundGateway.receiveTimeout` | Spring Integration outbound JMS gateway | Thời hạn nhận JMS reply |
| `@Gateway(replyTimeout=...)` | Spring messaging gateway interface | Thời gian chờ Spring reply qua message channel |
| Downstream DB/API timeout | Service nhận JMS request | Thời gian xử lý nghiệp vụ |
| JMS `timeToLive` | Message gửi qua broker | Thời hạn hợp lệ của JMS message trước khi expiry |
| Reply-listener idle timeout | Spring Integration reply listener | Khi nào listener được dừng khi rỗi; không phải deadline của một request |

**TTL không phải receive timeout.** Request hết hạn trên broker không tự báo cho client qua một JMS reply; client vẫn cần timeout và chiến lược xử lý request chưa rõ kết quả.

### Retry sau timeout

Trạng thái của request **có thể không xác định**: timeout không chứng minh server chưa commit nghiệp vụ. Nếu `checkStock` chỉ đọc, retry có giới hạn có thể tương đối an toàn. Nếu chuyển thành `reserveStock` hay `chargePayment`, client phải gửi lại **cùng `requestId`** để server phát hiện duplicate.

Server nên giữ bảng idempotency có unique constraint theo `requestId` và lưu kết quả trong cùng transaction với nghiệp vụ. Khi nhận lại cùng ID, server trả kết quả đã có thay vì tạo tác động lần thứ hai. `JMSMessageID` không đủ vì mỗi lần retry có thể sinh message ID khác.

## 11. Connection lifecycle, reconnect, transaction và caching

Temporary destination thuộc **JMS connection**, không thuộc logic của một đơn hàng hay một lời gọi Spring. Điều này dẫn tới ba tình huống vận hành khác nhau:

1. **Một request hoàn thành:** với chế độ temporary-per-request, gateway xóa temporary queue của request; connection dùng chung có thể vẫn tồn tại.
2. **Một gateway bị stop hoặc ứng dụng restart:** reply listener và các temporary destinations do gateway quản lý được giải phóng theo lifecycle. Không thể khôi phục in-flight request chỉ bằng cách tái sử dụng tên temporary queue cũ.
3. **JMS connection bị mất:** temporary destinations gắn với connection cũ trở nên không hợp lệ. Hạ tầng có thể reconnect/tạo lại consumer/temporary destination, nhưng **reply của request đang chờ tại thời điểm lỗi có thể bị mất**.

### 11.1. Reconnect không phải tiếp tục một cuộc trao đổi cũ

`CachingConnectionFactory`, JMS provider hoặc listener container có thể khôi phục connection; điều đó **không tự trả lại các JMS replies đã thất lạc**. Nếu bên nhận đã commit nghiệp vụ, client vẫn có thể thấy timeout và phải quyết định truy vấn trạng thái hoặc retry bằng business request ID.

Không lưu reference `TemporaryQueue` trong database để tái sử dụng sau khi restart. Giá trị reference do connection cũ sinh ra không còn là một reply channel hợp lệ cho connection mới.

### 11.2. Cache consumer và tài nguyên broker

Với temporary queue mỗi request, theo dõi tốc độ tạo/xóa temporary destinations và consumers; với reply listener dùng chung, theo dõi số listener task và số request in-flight. Một `CachingConnectionFactory` có thể giúp giảm chi phí tạo JMS session trong một số đường sử dụng `JmsTemplate`, nhưng:

- Không tự giả định mọi loại JMS consumer phù hợp để cache.
- **Đặc biệt tránh cache consumer theo selector riêng từng request trên fixed reply queue** vì số consumer không còn dùng có thể tích lũy.
- Kiểm tra số connection/session/consumer trên broker và heap của producer; nhiều Spring bean/gateway trên nhiều replica sẽ nhân tổng nhu cầu tài nguyên.
- Thử broker restart và failover theo đặc tính JMS provider, vì khả năng recovery có thể khác giữa temporary queue và fixed reply queue.

### 11.3. Transaction: đừng chờ reply trước khi request được commit/hiển thị

Một lỗi thiết kế điển hình:

~~~text
BEGIN JMS transaction ở client
  -> gửi request (chưa commit)
  -> chờ reply trong cùng transaction
  -> server chưa thể nhận request chưa được commit
  -> client timeout
~~~

Trong mô hình có **JMS transaction cho thao tác gửi**, broker có thể chỉ cho consumer khác nhìn thấy request **sau commit**. Nếu client giữ transaction chưa commit trong khi đồng bộ chờ reply, luồng có thể bị kẹt hoặc timeout. Cần xác định rõ ranh giới transaction gửi request và cách gateway thực hiện send/receive; không bọc tùy ý toàn bộ request-reply trong một JMS transaction ngoài chỉ vì muốn “atomic”.

Ở phía server, **JMS inbound gateway** có thể nhận request trong transaction JMS và gửi reply trước khi commit, theo thiết lập listener. Transaction JMS có thể bảo vệ các JMS operation liên quan, nhưng không tự commit database. Nếu server đã commit DB mà reply không tới client, retry vẫn phải có idempotency.

### 11.4. Bảng failure modes

| Điểm xảy ra lỗi | Trạng thái có thể xảy ra | Hướng xử lý |
|---|---|---|
| Không có quyền tạo temporary queue | Client lỗi trước khi gửi/chờ reply | Kiểm tra broker ACL, connection role và cấu hình gateway |
| Server không có quyền **send** đến temp destination | Server xử lý nhưng không gửi reply được | Cấp quyền phù hợp; kiểm tra provider policy |
| Client đóng connection khi request còn chạy | Temporary queue mất hiệu lực | Caller nhận lỗi/timeout; requestId để kiểm tra trạng thái và retry |
| Broker failover giữa request và reply | Connection/destination cũ có thể mất | Thử reconnect, metric in-flight và idempotent retry |
| Server bỏ qua `JMSReplyTo` | Reply được gửi sai nơi | Sửa JMS contract hoặc cấu hình gateway/fixed reply phù hợp |
| Reply body không convert được | JMS reply đến nhưng Spring handler không nhận dữ liệu hợp lệ | Đồng bộ schema, converter và error flow |
| Correlation ID không khớp | Reply có thể không tìm đúng caller | Ghi request/reply headers và sửa quy tắc echo correlation |
| `replyContainer()` dùng fixed reply không có key | Gateway cảnh báo/fallback sang consumer riêng | Cấu hình `correlationKey` hoặc thay đổi chiến lược |
| Request timeout nhưng server vẫn tiếp tục | Late reply và khả năng side effect đã commit | Truy vấn trạng thái theo requestId, retry an toàn |

## 12. Bảo mật và giới hạn quyền đối với temporary destination

Temporary destination được broker sinh tự động **không có nghĩa là không cần phân quyền**. Một ứng dụng có thể cần các quyền riêng cho:

- **Create temporary destination** trên connection của client.
- **Consume** reply từ destination do connection đó sở hữu.
- **Send** request vào queue cố định `inventory.check.requests`.
- **Send** reply tới destination tạm do client cấp từ connection của server.

JMS cho phép producer khác connection gửi tới temporary destination; nhưng provider/broker vẫn có thể áp dụng authentication, authorization và các giới hạn tài nguyên. Hãy kiểm tra ACL thực tế thay vì mặc định mọi producer đều được gửi đến mọi temporary destination.

### Kiểm soát `JMSReplyTo` ở phía server

`JMSReplyTo` là dữ liệu thuộc message do client đưa vào. Nếu server chấp nhận request từ nguồn không đáng tin cậy, phải áp dụng quyền broker và chính sách ứng dụng để tránh trở thành **relay gửi reply tới destination tùy ý**. Hạn chế thông tin nhạy cảm trong reply, validate payload và đảm bảo chỉ các client hợp lệ được gọi nghiệp vụ.

**Không làm hai việc sau trong production:**

- Log nguyên credentials, token, PII hoặc serialized body có dữ liệu nhạy cảm chỉ vì muốn debug reply mất.
- Dùng destination name do HTTP client truyền tự do để làm `JMSReplyTo`/reply queue mà không có quyền và validation.

Đối với broker nhiều tenant, temporary destination phải được kiểm chứng trong mô hình ACL, namespace, quota, connection limits và monitoring của từng provider.

## 13. Chọn temporary reply hay fixed reply?

| Yêu cầu kiến trúc | Lựa chọn thường phù hợp | Cần lưu ý |
|---|---|---|
| Request ngắn, client chỉ cần reply trong lời gọi hiện tại | **TemporaryQueue mỗi request** | Đơn giản nhưng có chi phí tạo/xóa |
| Một outbound gateway có nhiều request song song | **TemporaryQueue chung với reply listener** | Theo dõi in-flight mapping, listener và reconnect |
| Broker không cho tạo temporary destination | **Fixed reply queue** | Provision/ACL và correlation rõ ràng |
| Nhiều gateway/instance phải dùng chung queue reply đã quản trị | **Fixed reply queue + reply listener + correlationKey** | Kiểm tra selector unique và tránh cache consumer theo request |
| Muốn nhận reply sau khi client restart | Không dựa vào temporary destination | Chuyển sang giao thức async command/result và lưu kết quả bền vững |
| Server mất vài phút để xử lý | Cân nhắc request-acknowledgement + result event/status query | Không giữ vô hạn hàng nghìn request chờ reply |
| Hệ thống có giới hạn temporary destination nghiêm ngặt | Kiểm tra reply listener/fixed reply queue | Đo quota và khả năng failover |

**Câu hỏi quyết định:** reply có cần tồn tại **sau khi connection của caller đóng** không? Nếu có, temporary destination **không đáp ứng** yêu cầu đó, dù JMS delivery mode đặt persistent. Cần thay đổi giao thức thay vì chỉ nâng số lần retry.

## 14. Quan sát vận hành và capacity planning

Temporary reply queue thường ngắn hạn nên khó debug bằng tên queue cố định. Mỗi request cần được theo dõi bằng **business ID**, metadata JMS và thời gian:

| Chỉ số | Ý nghĩa |
|---|---|
| Requests sent/second | Tốc độ gọi hệ thống JMS |
| Replies received/second | Số request có reply tương ứng |
| In-flight requests | Số lời gọi đang chờ reply tại gateway |
| Reply latency p50/p95/p99 | Độ trễ end-to-end của request-reply |
| Timeout rate | Tỷ lệ request không có reply trong hạn |
| Late/unmatched replies | Dấu hiệu reply đến muộn hoặc correlation sai |
| Temporary destination count | Số queue/topic tạm đang tồn tại tại broker |
| Reply consumer count | Số consumer chờ reply của gateway |
| Reconnect/recovery events | Khả năng mất connection và tạo lại temporary destination |
| Request queue depth/oldest age | Server có backlog hay xử lý chậm |
| Conversion/business errors | Không nhầm dữ liệu sai với timeout kết nối |

Ví dụ tổng số request đang chờ của cluster là 200, mỗi request có thể tồn tại 5 giây. Với cách mỗi request tạo một temporary queue, **có thể có hàng trăm temporary destinations cùng lúc**. Với reply listener dùng chung một queue cho mỗi gateway, số temporary queues thường gắn với **số gateway instance đang hoạt động**, không trực tiếp bằng số request; nhưng ứng dụng vẫn phải giữ thông tin in-flight và tiêu thụ tài nguyên cho mỗi request.

Khi benchmark cần ghi cả **broker metrics lẫn JVM metrics**, vì một phương án có thể giảm số temporary queues nhưng làm tăng bộ nhớ chờ ở gateway hoặc áp lực lên hệ thống xử lý request.

## 15. Thực hành: quan sát temporary reply destination trên broker thật

**Môi trường:** Spring Integration 6+ hoặc phiên bản được dự án dùng, Java 17+, một JMS broker thử nghiệm, một ứng dụng client và một server có JMS inbound gateway. Request queue là `inventory.check.requests`. Không cần tạo queue reply tạm bằng cấu hình broker; nó được tạo theo JMS operation. Bài thử phải có quyền create/consume temporary destinations và send reply.

### Bài A — `JmsTemplate.sendAndReceive`

1. Tạo bean `JmsTemplate` với `receiveTimeout(5000)`.
2. Server đọc `JMSReplyTo` của request, gửi JMS `TextMessage` reply tới destination này.
3. Gửi ba request có `requestId` khác nhau; so sánh `JMSReplyTo` trên từng JMS request bằng log metadata/broker console.
4. Kiểm tra reply body và correlation ID, không suy luận hoàn tất chỉ từ `sendAndReceive` trả về `Message`.
5. Quan sát temporary queues/consumers được tạo và giải phóng; xác nhận với provider thực, không chỉ mock.

### Bài B — Outbound gateway không có reply listener

1. Chạy client flow ở mục 5 với `receiveTimeout(5000)`.
2. Gửi 20 request đồng thời, mỗi request có `requestId` riêng.
3. Ghi nhận số temporary queues đang tồn tại khi request chờ; theo dõi số consumer.
4. Cho server trả reply theo thứ tự đảo; xác minh mỗi caller nhận đúng JSON của mình.
5. Đo thời gian, số session/consumers và chi phí tạo/xóa destination.

### Bài C — Reply listener dùng chung temporary queue

1. Thay flow ở mục 5 bằng flow `.replyContainer()` của mục 6.
2. Gửi lại 20 request; quan sát chúng dùng cùng temporary queue của **một gateway instance**.
3. Kiểm tra correlation khi reply đến không theo thứ tự.
4. So sánh throughput, số temporary destinations và số consumer với bài B.
5. Khởi động thêm một instance gateway, kiểm tra mỗi instance quản lý temporary destination riêng.

### Bài D — Timeout và reply đến muộn

1. Cho server xử lý 8 giây trong khi client chờ 5 giây.
2. Với temporary queue mỗi request, kiểm tra thời điểm queue bị xóa và hành vi khi server cố gửi reply sau đó.
3. Với reply listener chung, quan sát late/unmatched reply và bảo đảm nó không bị ghép sang request khác.
4. Gửi lại **cùng requestId**; xác minh server không thực thi hai lần nếu nghiệp vụ có side effect.
5. Thiết kế một API `getRequestStatus(requestId)` hoặc result event cho những tác vụ dài.

### Bài E — Connection failover, ACL và vận hành

1. Ngắt JMS connection khi client còn request đang chờ; ghi nhận timeout/exception.
2. Khôi phục broker, xem gateway/reply listener có tạo temporary queue mới hay không.
3. Thu hồi quyền tạo temporary destination của client (trong broker thử nghiệm); quan sát lỗi và cách cảnh báo.
4. Thu hồi quyền server gửi reply tới temporary destination; xác minh client timeout dù server có thể nhận request.
5. Thử cấu hình fixed reply queue với `correlationKey("JMSCorrelationID")` và reply listener; kiểm tra reply không bị các gateway khác nhận nhầm.
6. Tạo một thử nghiệm tải với `cacheConsumers=true` **chỉ trong môi trường test** cho fixed reply queue theo request selector; quan sát vì sao cached consumers có thể tích lũy.

### Checklist kết quả mong đợi

| Kiểm tra | Dấu hiệu PASS |
|---|---|
| Client đặt `JMSReplyTo` | JMS request chứa temporary destination hợp lệ |
| Server trả đúng nơi | Producer gửi reply tới destination từ request |
| Reply đúng request | Payload `requestId` và correlation phù hợp |
| Timeout có giới hạn | Caller không chờ vô hạn khi server im lặng |
| Late reply không bị nhận nhầm | Request khác không nhận dữ liệu của request đã timeout |
| Temporary destination được dọn | Tài nguyên broker trở về mức phù hợp sau tải |
| Mất connection được ghi nhận | Metric/log và khả năng reconnect rõ ràng |
| Retry không double effect | Server có idempotency theo `requestId` |
| Không có cached-consumer leak | Số consumer không tăng vô hạn sau nhiều request |

**Không thể xác minh vòng đời temporary destination chỉ bằng unit test mock `ConnectionFactory` hoặc mock `JmsTemplate`.** Phải dùng một JMS provider/broker thực hoặc test container tương ứng, kiểm tra cả ACL, timeout và recovery.

### Câu hỏi tự đánh giá

1. `TemporaryQueue` có thuộc vòng đời của `Session` tạo nó hay JMS `Connection`?
2. Vì sao server dùng connection khác vẫn có thể gửi reply tới temporary queue của client?
3. Tại sao chỉ connection sở hữu temporary destination mới được tạo consumer nhận từ đó?
4. Phân biệt JMS `JMSReplyTo` với Spring Integration `replyChannel`.
5. Không cấu hình `replyDestination`, outbound gateway sẽ chọn reply destination nào?
6. Khác nhau giữa **mỗi request một TemporaryQueue** và **mỗi gateway một TemporaryQueue với reply listener**?
7. Vì sao reply listener với fixed reply destination cần correlation key được cấu hình đúng?
8. Tại sao `cacheConsumers=true` có thể gây vấn đề với fixed reply queue dùng selector riêng cho từng request?
9. Điều gì xảy ra nếu server trả reply sau khi temporary queue đã bị xóa?
10. Timeout có chứng minh server chưa ghi database thành công không? Vì sao?
11. Khi nào `replyPubSubDomain(true)` tạo `TemporaryTopic`, và tại sao không nên bật mặc định?
12. Vì sao giữ JMS request trong transaction chưa commit trong lúc chờ reply có thể gây timeout?
13. Nếu kết quả phải tồn tại qua client restart, nên giữ temporary destination hay đổi giao thức?
14. Dùng metric nào để xác minh gateway dùng reply listener thực sự giảm tài nguyên?

## 16. Tài liệu tham khảo chính thức

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): **Outbound Gateway**, `TemporaryQueue`, `TemporaryTopic`, `reply-listener`, correlation và các trường hợp kết hợp reply destination.
- [Spring Integration API — JmsOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundGatewaySpec.html): `requestDestination`, `replyDestination`, `replyContainer`, `receiveTimeout`, `correlationKey`, `replyPubSubDomain`.
- [Spring Integration API — ReplyContainerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundGatewaySpec.ReplyContainerSpec.html): concurrency, recovery và idle reply listener.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate` và request-reply bằng temporary queue.
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `sendAndReceive`, `receiveTimeout` và quản lý tài nguyên JMS.
- [Jakarta Messaging Concepts — Creating Temporary Destinations](https://jakarta.ee/learn/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html): phạm vi theo connection, quyền consumer và vòng đời của temporary destinations.
- [Jakarta Messaging API — TemporaryQueue](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/TemporaryQueue.html): interface và thao tác `delete()`.

**Ghi nhớ:** Temporary reply destination là đích JMS do client tạo để nhận phản hồi trong một cuộc trao đổi request-reply, có vòng đời phụ thuộc JMS connection. Spring Integration outbound gateway mặc định dùng `TemporaryQueue`; **không có reply listener** thì tạo queue cho từng request, còn **có reply listener** có thể dùng một queue chung cho mỗi gateway. Muốn hệ thống tin cậy, phải tôn trọng `JMSReplyTo`, định nghĩa correlation, giới hạn timeout, xử lý late reply, recovery, ACL và idempotency. Temporary destination **không** thay thế một cơ chế lưu kết quả bền vững qua restart.


