# JmsTemplate và ConnectionFactory

## 1. Vì sao cần hiểu cả hai thành phần?

Một dịch vụ quản lý đơn hàng dùng Spring Integration để gửi sự kiện sang JMS queue `orders.events` và nhận yêu cầu đồng bộ từ queue `orders.import`. Để làm việc với broker, ứng dụng phải có một cách **lấy kết nối JMS** và một thành phần **gửi/nhận JMS message** mà không phải tự mở, đóng `Connection`, `Session`, `MessageProducer` hay `MessageConsumer` cho từng thao tác.

Trong hệ sinh thái Spring, hai khái niệm cốt lõi là:

- **`jakarta.jms.ConnectionFactory`:** giao diện tiêu chuẩn JMS do provider triển khai. Nó cung cấp khả năng tạo kết nối tới broker; các lớp Spring có thể bọc (decorate) nó để cache hoặc dùng pool tài nguyên.
- **`org.springframework.jms.core.JmsTemplate`:** lớp của Spring JMS giúp gửi, nhận và chuyển đổi message **đồng bộ**, sử dụng `ConnectionFactory` được cung cấp. Nó xử lý phần lớn boilerplate mở/đóng tài nguyên và chuyển `JMSException` thành hệ exception nhất quán của Spring.

Trong module **SPRING_INTEGRATION_ADAPTERS**, outbound adapter, inbound adapter, gateway, poller và `MessageChannel` cùng giúp kết nối hệ thống ngoài với integration flow. Phần **JMS** dùng cơ sở hạ tầng Spring JMS bên dưới; hiểu `JmsTemplate` và `ConnectionFactory` giúp giải thích vì sao JMS inbound polling lấy message theo lịch, outbound adapter gửi khi message đi vào channel, và vì sao message-driven endpoint lại dùng listener container.

**Kết quả học tập:** sau bài này, bạn có thể cấu hình `ConnectionFactory` và `JmsTemplate`, gửi/nhận một message JMS, chọn receive timeout, hiểu converter/header, phân biệt queue/topic, lựa chọn cache/pool và đặt ranh giới transaction đúng cho một flow Spring Integration.

## 2. Quan hệ giữa ConnectionFactory, JmsTemplate và broker

~~~mermaid
flowchart LR
    A["Service / Spring Integration flow"] --> B["JmsTemplate"]
    B --> C["ConnectionFactory"]
    C --> D["JMS Connection + Session"]
    D --> E["MessageProducer / MessageConsumer"]
    E <--> F[("JMS Broker")]
    B -. "MessageConverter + DestinationResolver" .-> G["Payload / Destination"]
~~~

Nếu gọi API JMS trực tiếp, một lần gửi cơ bản cần thực hiện các bước: lấy connection từ factory, tạo session, tạo producer, tạo `TextMessage`, gửi message, rồi đóng tài nguyên đúng cách. `JmsTemplate` gói các thao tác này trong `send(...)` và `convertAndSend(...)`.

| Thành phần | API/khái niệm | Chức năng chính | Điều nó **không** tự làm |
|---|---|---|---|
| `ConnectionFactory` | Jakarta JMS | Tạo kết nối đến provider/broker | Không định nghĩa hợp đồng JSON hoặc routing nghiệp vụ |
| `CachingConnectionFactory` | Spring JMS | Bọc factory và cache connection, session, producer/consumer theo cấu hình | Không phải broker, không thay thế mọi connection pool chuyên dụng |
| `JmsTemplate` | Spring JMS | Gửi/nhận đồng bộ, resolve destination, convert JMS message | Không tự chạy một JMS listener container cho luồng message-driven |
| `MessageConverter` | Spring JMS | Chuyển Java object ↔ JMS body | Không tự validate JSON schema hoặc business rules |
| `DestinationResolver` | Spring JMS | Biến tên destination thành đối tượng queue/topic | Không tự đảm bảo destination tồn tại hoặc ACL đúng |
| `DefaultMessageListenerContainer` | Spring JMS | Quản lý consumer nhận message theo kiểu listener, recovery, concurrency | Không thay `JmsTemplate` trong mọi endpoint |
| `JmsTransactionManager` | Spring | Điều phối transaction JMS cục bộ trên `ConnectionFactory` | Không tự tạo transaction nguyên tử với một database khác |

Một `JmsTemplate` có thể sử dụng nhiều destination khác nhau; nó **không** sở hữu một queue duy nhất. Tên queue mặc định chỉ là lựa chọn khi lời gọi không truyền destination cụ thể.

## 3. Chuẩn bị môi trường và phiên bản API

Ví dụ sử dụng **Spring Framework 6+, Spring Integration 6+ và Java 17+**, với JMS API thuộc package `jakarta.jms`. Các dự án Spring 5 có thể sử dụng `javax.jms`; đừng trộn hai package trong cùng cấu hình.

Trong dự án Spring Boot có BOM quản lý version, các dependency ứng dụng có thể bao gồm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Thêm JMS starter/client phù hợp provider, ví dụ Artemis hoặc IBM MQ. -->
~~~

Phần JMS API/driver thường được cung cấp bởi dependency JMS provider. `spring-integration-jms` **không tự chạy broker**. Cần có broker thật hoặc test container, địa chỉ kết nối, credentials, TLS/ACL nếu được yêu cầu và queue/topic tương ứng. Không có một bộ tham số kết nối áp dụng cho mọi JMS provider.

Với Spring Boot, một starter JMS tương thích có thể tự tạo bean `ConnectionFactory` và `JmsTemplate`. Trước khi định nghĩa thêm bean thủ công, hãy kiểm tra auto-configuration để tránh cấu hình hai template/factory không chủ ý. Những ví dụ phía dưới minh họa cách tạo bean khi ứng dụng muốn kiểm soát tùy chọn riêng.

### 3.1. Tạo một JmsTemplate từ ConnectionFactory

Giả sử Spring đã có đúng một bean `ConnectionFactory` đã cấu hình đến broker:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class OrderJmsTemplateConfiguration {

    @Bean("orderJmsTemplate")
    public JmsTemplate orderJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDefaultDestinationName("orders.events");
        template.setPubSubDomain(false); // false: queue; true: topic khi resolve theo tên
        template.setReceiveTimeout(500); // ms; chỉ ảnh hưởng thao tác receive()
        return template;
    }
}
~~~

Ở đây:

- `new JmsTemplate(connectionFactory)` tạo template gắn với cùng JMS provider mà factory cung cấp.
- `setDefaultDestinationName(...)` đặt destination mặc định, nhưng `send("queue.name", ...)` hoặc `convertAndSend("queue.name", ...)` có thể chỉ định destination khác.
- `setPubSubDomain(false)` yêu cầu việc resolve tên theo ngữ nghĩa **queue**. Nếu chuyển sang topic, cần thống nhất semantics publish-subscribe với consumer; không chỉ đổi tên string.
- `setReceiveTimeout(500)` giới hạn **một lần nhận đồng bộ** tối đa 500 mili giây khi không có message; nó không quyết định tần suất polling của một Spring Integration endpoint.

Không đặt `setSessionTransacted(true)` chỉ để "an toàn hơn" mà chưa xác định ranh giới transaction. Mục 8 giải thích tại sao commit thời điểm nào quan trọng hơn một cờ cấu hình.

## 4. Gửi JMS message với JmsTemplate

`JmsTemplate` cung cấp hai hướng phổ biến:

1. **`send(...)`:** tự tạo đối tượng JMS `Message` qua `MessageCreator`, cho phép kiểm soát `TextMessage`, `BytesMessage` và headers/properties trực tiếp.
2. **`convertAndSend(...)`:** truyền một Java object/payload, để `MessageConverter` tạo JMS Message; có thể dùng `MessagePostProcessor` bổ sung metadata sau conversion.

### 4.1. Ví dụ gửi JSON bằng convertAndSend

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderEventPublisher(
            @Qualifier("orderJmsTemplate") JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishOrderPaid(String jsonBody, String eventId) {
        jmsTemplate.convertAndSend("orders.events", jsonBody, message -> {
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("eventType", "OrderPaid");
            message.setIntProperty("schemaVersion", 1);
            return message;
        });
    }
}
~~~

Payload JSON:

~~~json
{
  "eventId": "evt-6001",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-600",
  "amount": 320000
}
~~~

Với `SimpleMessageConverter` mặc định, `String` thường được tạo thành JMS `TextMessage`. `MessagePostProcessor` thêm các **JMS properties**; giá trị phải thuộc những kiểu được JMS hỗ trợ. Event ID trong payload nên là khóa nghiệp vụ ổn định; JMS `JMSMessageID` do provider tạo cho mỗi lần gửi có thể khác khi ứng dụng retry.

**Không nhầm "method trả về không có exception" với "consumer đã xử lý thành công".** `convertAndSend` hoàn tất khi provider chấp nhận thao tác gửi theo session, transaction và QoS đang áp dụng. Consumer có thể chưa nhận hoặc chưa commit nghiệp vụ.

### 4.2. Ví dụ tự tạo TextMessage bằng send

~~~java
// jmsTemplate là bean đã inject; đây là đoạn code trong method của service.
jmsTemplate.send("orders.events", session -> {
    jakarta.jms.TextMessage message =
            session.createTextMessage("{\"eventId\":\"evt-6002\"}");
    message.setStringProperty("eventType", "OrderPaid");
    return message;
});
~~~

`send` phù hợp khi cần dùng một JMS message type cụ thể hoặc đặt metadata mà converter không thể tự suy ra. Trong phần lớn hợp đồng JSON đơn giản, `convertAndSend` giúp code ngắn hơn.

### 4.3. QoS khi gửi: persistence, priority, TTL

JMS hỗ trợ các thuộc tính gửi như delivery mode, priority (0–9) và time-to-live (TTL). `JmsTemplate` có thể cấu hình QoS:

~~~java
JmsTemplate notificationTemplate = new JmsTemplate(connectionFactory);
notificationTemplate.setExplicitQosEnabled(true);
notificationTemplate.setDeliveryPersistent(false);
notificationTemplate.setPriority(3);
notificationTemplate.setTimeToLive(60_000L); // 60 giây
~~~

Đây là **ví dụ cho thông báo hết hạn được**, không phải gợi ý áp dụng cho sự kiện thanh toán hoặc dữ liệu cần lưu bền vững. Mặc định JMS thường gửi persistent, priority 4, TTL không giới hạn; provider và cấu hình ứng dụng có thể thay đổi cách áp dụng. `setExplicitQosEnabled(true)` yêu cầu template thực sự truyền các giá trị QoS đã cấu hình vào thao tác gửi.

Không thay đổi những thuộc tính cấu hình của `JmsTemplate` singleton mỗi lần service được gọi từ nhiều thread. Nếu cần QoS khác nhau giữa các loại message, hãy thiết kế bean/template riêng hoặc dùng cơ chế QoS động được endpoint hỗ trợ.

## 5. Nhận JMS message với JmsTemplate

`JmsTemplate.receive(...)` thực hiện **nhận đồng bộ**: thread đang gọi chờ broker trả message hoặc hết timeout. Trong ứng dụng Spring Integration, cơ chế này là nền tảng cho **JMS polling inbound channel adapter**.

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

// Một lần nhận, không phải listener liên tục.
Message message = orderJmsTemplate.receive("orders.import");

if (message == null) {
    // Không có JMS message trước khi receive timeout kết thúc.
} else if (message instanceof TextMessage textMessage) {
    String json = textMessage.getText();
    // Parse JSON và xử lý theo hợp đồng nghiệp vụ.
} else {
    throw new IllegalArgumentException("JMS message type không được hỗ trợ");
}
~~~

`receiveAndConvert("orders.import")` là lựa chọn gọn hơn nếu muốn converter trả về Java payload:

~~~java
Object payload = orderJmsTemplate.receiveAndConvert("orders.import");
if (payload instanceof String json) {
    // TextMessage -> String với SimpleMessageConverter mặc định.
}
~~~

Đối tượng trả về có thể là `null` nếu không nhận được message trong khoảng chờ; loại Java object phụ thuộc `MessageConverter`.

### 5.1. Các giá trị receiveTimeout

| `receiveTimeout` | Hành vi của `JmsTemplate` | Trường hợp dùng |
|---|---|---|
| `-1` | Không chờ, dùng JMS `receiveNoWait()` | Poller cần kết thúc nhanh khi queue rỗng |
| `0` | Chờ không giới hạn đến khi có message (mặc định của `JmsTemplate` thuần) | Chỉ khi chủ đích chấp nhận thread chờ lâu |
| `500` | Chờ tối đa 500 ms cho một lần nhận | Công cụ/worker nhận đồng bộ cần timeout rõ ràng |

**Phân biệt timeout và lịch poll:** `receiveTimeout` là thời gian chờ tối đa của **mỗi lời gọi JMS receive**. `fixedDelay(5000)` của Spring Integration poller là khoảng cách giữa các **lượt lấy message**. Nếu receive timeout 10 giây, một lượt poll có thể mất tới 10 giây trước khi về mà không có message, ngay cả khi fixed delay chỉ 5 giây.

Khi broker có message liên tục, nhiều lần `receive()` và xử lý có thể kéo dài trong một lượt nếu `maxMessagesPerPoll` lớn. Vì vậy cần tính tổng thời gian timeout, batch size và số thread scheduler.

### 5.2. Đưa JmsTemplate vào Spring Integration inbound polling

Trong Java DSL, có thể cấu hình một inbound polling adapter bằng `ConnectionFactory` và điều chỉnh template nội bộ:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow inboundOrdersPolling(ConnectionFactory connectionFactory) {
    return IntegrationFlow.from(
            Jms.inboundAdapter(connectionFactory)
                    .destination("orders.import")
                    .configureJmsTemplate(template ->
                            template.receiveTimeout(-1)),
            endpoint -> endpoint.poller(poller ->
                    poller.fixedDelay(5000)
                          .maxMessagesPerPoll(10)))
            .handle(String.class, (json, headers) -> {
                // Minh họa: thay bằng service validate + import có idempotency.
                System.out.println("JMS incoming: " + json);
                return null;
            })
            .get();
}
~~~

Trong ví dụ, `.configureJmsTemplate(...)` cấu hình template cho **adapter này**, không nhất thiết thay đổi bean `orderJmsTemplate` định nghĩa ở mục 3. `receiveTimeout(-1)` giúp trả về nhanh khi queue rỗng. Từ Spring Integration 5.0.8, một số cấu hình mặc định liên quan `CachingConnectionFactory` và `cacheConsumers` có thể đã dùng no-wait; đặt rõ ràng trong ví dụ giúp tránh hiểu nhầm khi thay provider/cấu hình.

Giới hạn `maxMessagesPerPoll(10)` là tối đa 10 message mỗi lượt, **không phải** bảo đảm throughput 10 message mỗi 5 giây; thời gian xử lý handler, network và transaction đều ảnh hưởng. Adapter polling là **một chiều**: không gửi JMS reply cho producer.

## 6. MessageConverter, DestinationResolver và queue/topic

`JmsTemplate` sử dụng các chiến lược mặc định là `SimpleMessageConverter` và `DynamicDestinationResolver`, nhưng ứng dụng có thể thay bằng cấu hình phù hợp hợp đồng đối tác.

### 6.1. MessageConverter

| Dữ liệu Java khi gửi | JMS body thường được tạo | Khi nhận lại thường có |
|---|---|---|
| `String` | `TextMessage` | `String` |
| `byte[]` | `BytesMessage` | `byte[]` |
| `Map` với kiểu dữ liệu phù hợp JMS | `MapMessage` | `Map` |
| `Serializable` | `ObjectMessage` | Java object |

**Không giả định DTO tự biến thành JSON.** Nếu producer và consumer giao tiếp giữa Java, .NET hay Node.js, nên dùng `TextMessage` JSON có `schemaVersion` hoặc định dạng binary có schema thống nhất, rồi serialize/deserialize có kiểm tra. `ObjectMessage` mang rủi ro tương thích class và deserialization, thường không lý tưởng cho hợp đồng liên dịch vụ.

Ví dụ tạo payload JSON trước `convertAndSend`:

~~~java
// orderPaid là DTO nghiệp vụ; objectMapper là Jackson ObjectMapper.
try {
    String json = objectMapper.writeValueAsString(orderPaid);
    jmsTemplate.convertAndSend("orders.events", json);
} catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
    throw new IllegalStateException("Không thể serialize OrderPaid", ex);
}
~~~

Ở phía nhận, parse và validate schema trước khi ghi dữ liệu. Nếu contract thay đổi, nên có `schemaVersion` và chiến lược backward compatibility.

### 6.2. Queue, topic và DestinationResolver

| JMS destination | Mô hình | Cách quan tâm |
|---|---|---|
| **Queue** (`pubSubDomain=false`) | Competing consumers; một JMS message được một consumer của queue xử lý | Phân phối công việc, xử lý nghiệp vụ, retry và DLQ |
| **Topic** (`pubSubDomain=true`) | Publish-subscribe; nhiều subscription có thể nhận bản sao | Durable/shared subscription và hành vi khi subscriber offline |

`setPubSubDomain(true)` ảnh hưởng cách `DynamicDestinationResolver` tạo/tra destination **theo tên**; nếu sử dụng một đối tượng `Destination` cụ thể, bản thân đối tượng đó quyết định loại destination. Không mặc định gọi queue `orders.events` sẽ tự trở thành topic chỉ vì đặt tên khác.

Các môi trường production có thể cần `DestinationResolver` chuyên biệt hoặc lookup qua JNDI. Cấu hình quyền tạo destination và naming policy thuộc broker; không sử dụng tên destination trực tiếp từ dữ liệu người dùng chưa validate.

## 7. ConnectionFactory: caching, pooling và quản lý vòng đời

`ConnectionFactory` là entry point để mở JMS connection. Một số JMS provider cung cấp factory với connection pool của riêng mình; Spring cung cấp các decorator để tái sử dụng tài nguyên và giảm chi phí khởi tạo.

### 7.1. Ba lựa chọn thường thấy

| Kiểu factory | Hành vi | Tình huống phù hợp |
|---|---|---|
| Factory của JMS provider | Tạo connection/session theo khả năng provider | Mọi ứng dụng cần driver kết nối broker |
| `SingleConnectionFactory` | Chia sẻ một `Connection` và che thao tác đóng logic | Standalone/test hoặc trường hợp chỉ cần reuse connection |
| `CachingConnectionFactory` | Kế thừa `SingleConnectionFactory`, thêm cache session, producer và tùy chọn consumer | Các thao tác `JmsTemplate` lặp lại, cần giảm overhead |
| Provider pooled factory/JNDI managed factory | Pool/lifecycle do provider hoặc application server quản lý | Tải cao hoặc hệ thống vận hành tập trung |

Một cấu hình cache minh họa khi **target ConnectionFactory chưa được pool/cache**:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.connection.CachingConnectionFactory;

// vendorConnectionFactory là factory do JMS provider tạo.
CachingConnectionFactory caching =
        new CachingConnectionFactory(vendorConnectionFactory);
caching.setSessionCacheSize(10);
caching.setCacheProducers(true);
caching.setCacheConsumers(true);
~~~

Đây là **fragment cấu hình**, không tạo thêm bean trong ứng dụng đã được Spring Boot auto-configure sẵn. `sessionCacheSize` là số session cache theo từng acknowledge/session mode; tổng số session có thể lớn hơn con số này khi dùng nhiều mode. Giá trị hợp lý phụ thuộc concurrency thực tế, không có một con số đúng cho mọi ứng dụng.

`CachingConnectionFactory` có thể tự reconnect connection sau exception. Tuy nhiên **reconnect không chứng minh việc gửi trước đó đã thành công hay thất bại**, và không giải quyết replay, transaction hoặc idempotency ở tầng nghiệp vụ.

### 7.2. Lưu ý riêng cho listener container

`DefaultMessageListenerContainer` thường có **cơ chế caching/recovery của chính nó**. Spring Framework lưu ý rằng bọc container bằng `CachingConnectionFactory` bên ngoài có thể gây vấn đề khi stop/start, scaling consumer hoặc dùng durable subscription. Với message-driven inbound adapter hoặc inbound gateway, hãy kiểm tra cấu hình listener container trước khi áp dụng chung một cache factory cho mọi thành phần.

Tránh "double caching" nếu provider đã có pool và Spring Boot cũng tạo `CachingConnectionFactory`. Dấu hiệu cấu hình không hợp lý: quá nhiều JMS session, consumer giữ message ngoài ý muốn, recovery chậm, broker báo quota connection hoặc khả năng dừng listener không như dự kiến.

### 7.3. Bean singleton và thread safety

`JmsTemplate` được thiết kế để dùng lại như một bean sau khi cấu hình xong. Nhiều service có thể đồng thời gọi `convertAndSend` qua một instance; mỗi lời gọi sử dụng tài nguyên JMS phù hợp từ factory. **Không thay đổi `defaultDestination`, `receiveTimeout`, QoS, converter hoặc transaction flags của cùng một template trong lúc nhiều thread đang sử dụng.**

Không lưu `Session` hay `MessageProducer` của một lần thao tác `JmsTemplate` để tái sử dụng trực tiếp giữa các thread. JMS `Session` vốn không phải đối tượng dành cho truy cập đồng thời từ nhiều thread; lifecycle nên để Spring/provider quản lý.

## 8. Transaction, acknowledge và thời điểm commit

### 8.1. Mặc định của JmsTemplate

`JmsTemplate` thuần mặc định dùng session **không transacted** và acknowledge mode **AUTO_ACKNOWLEDGE**. Nếu thực hiện `receive()` rồi sau đó ghi database thất bại, JMS message có thể đã được broker xem là đã nhận. Đó là lý do cấu hình receipt/transaction phải xét tới **toàn bộ luồng**, không chỉ một lời gọi template.

| Tình huống | Điều gì được giao dịch bảo vệ? | Hệ quả |
|---|---|---|
| `convertAndSend` thông thường | Gửi theo session/QoS mặc định; không bao trùm database | Send thành công không chứng minh DB và consumer đồng bộ |
| `receive` không có transaction | Việc nhận/ack theo session mode | Handler về sau lỗi có thể không được broker redeliver |
| `JmsTemplate.sessionTransacted=true` cho một lệnh receive | Giao dịch JMS cục bộ trong lệnh template | Commit thường xảy ra trước khi flow downstream xử lý |
| `JmsTransactionManager` bao quanh chuỗi đồng bộ | JMS receive/send tham gia transaction trên cùng resource | Lỗi truyền ra khỏi boundary có thể rollback JMS |
| DB transaction riêng + JMS transaction riêng | Mỗi tài nguyên có commit riêng | Không atomic giữa DB và JMS nếu không có cơ chế phối hợp |

### 8.2. JmsTransactionManager

Spring cung cấp `JmsTransactionManager` để liên kết một JMS session với thread đang thực thi transaction. Ví dụ bean:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.JmsTransactionManager;

@Bean("orderJmsTransactionManager")
public JmsTransactionManager orderJmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Khi có một transaction phù hợp đang hoạt động, `JmsTemplate` có thể lấy session được Spring gắn với thread và tham gia transaction đó. Nếu ứng dụng có cả `DataSourceTransactionManager` và `JmsTransactionManager`, cần chỉ rõ manager mong muốn tại nơi bắt đầu transaction; không giả định một annotation `@Transactional` mặc định bao trùm cả hai tài nguyên.

### 8.3. Transaction trong Spring Integration polling

Đặt `sessionTransacted=true` cho template nhận **không đủ** để rollback khi handler downstream thất bại: nếu transaction chỉ bao quanh `receive()`, commit đã hoàn thành trước khi Spring Message được gửi vào `MessageChannel`.

Đối với **JMS inbound polling channel adapter**, cần transaction advice ở **poller**, ví dụ phần cấu hình endpoint:

~~~java
endpoint -> endpoint.poller(poller ->
        poller.fixedDelay(5000)
              .maxMessagesPerPoll(10)
              .transactional(orderJmsTransactionManager))
~~~

Đây là fragment thay cho poller ở mục 5; `orderJmsTransactionManager` là bean đã inject vào phương thức định nghĩa flow. Handler và chuỗi channel cần **đồng bộ** (thường dùng `DirectChannel`) để exception lan ra tới transaction advice. Nếu chuyển qua `ExecutorChannel` hoặc `QueueChannel`, công việc downstream có thể chạy sau khi transaction JMS đã commit.

Đối với **message-driven inbound adapter**, hãy xét transaction trên `MessageListenerContainer`; nó nhận message và điều khiển transaction ngay tại callback của listener. `JmsTemplate` chỉ còn được dùng ở các thao tác gửi phù hợp, không phải thứ thay thế listener container.

### 8.4. Vì sao vẫn phải dùng idempotency?

Giả sử dịch vụ nhận request JMS, commit trạng thái đơn hàng vào PostgreSQL, nhưng transaction JMS rollback do lỗi mạng trước khi xác nhận receive. Broker có thể redeliver cùng message; nếu handler ghi lần nữa, dữ liệu bị trùng.

Một quy trình bền vững thường:

1. Đặt `eventId` hoặc `requestId` ổn định trong payload.
2. Trong cùng DB transaction, ghi khóa idempotency có unique constraint và thực hiện thay đổi nghiệp vụ.
3. Nếu nhận lại cùng ID, đọc kết quả đã lưu hoặc bỏ qua an toàn.
4. Cho lỗi tạm thời truyền tới ranh giới transaction để broker redeliver theo policy.
5. Dùng outbox khi cần **ghi DB và phát JMS event** mà vẫn có khả năng phục hồi sau crash.

`JmsTransactionManager` **không** tự cung cấp atomic commit giữa JMS và DB. XA/distributed transactions chỉ có ý nghĩa khi broker, database và transaction manager hỗ trợ, và phải tính đến độ phức tạp vận hành.

## 9. Spring Integration sử dụng JmsTemplate ở đâu?

Đây là mối quan hệ cần nhớ trong module `SPRING_INTEGRATION_ADAPTERS`:

| Endpoint Spring Integration | Cách JMS hoạt động bên dưới | Có dùng poller? |
|---|---|---|
| JMS **polling inbound channel adapter** | `JmsTemplate.receive()` qua `JmsDestinationPollingSource` | **Có**, cấu hình trên adapter |
| JMS **message-driven inbound channel adapter** | JMS `MessageListenerContainer` callback khi có message | **Không** |
| JMS **outbound channel adapter** | `JmsTemplate` chuyển và gửi message theo yêu cầu | **Không** |
| JMS **inbound gateway** | Listener container nhận request, xử lý Spring reply rồi gửi JMS reply | Không dùng poller ở điểm nhận |
| JMS **outbound gateway** | Gửi JMS request và đợi JMS reply, quản lý reply destination/correlation | Không cần poller cho nguồn Spring request |

Ví dụ outbound adapter dùng `ConnectionFactory`:

~~~java
@Bean
public IntegrationFlow orderEventsOutbound(ConnectionFactory connectionFactory) {
    return IntegrationFlow.from("orderEventsOutput")
            .handle(Jms.outboundAdapter(connectionFactory)
                    .destination("orders.events"))
            .get();
}
~~~

Trong Java DSL, outbound adapter tạo hoặc dùng template JMS thích hợp để gửi; handler này được kích hoạt bởi Spring Message đi vào `orderEventsOutput`. Có thể dùng `JmsTemplate` trực tiếp trong service, nhưng adapter giúp tích hợp với `MessageChannel`, transformer, filter, router và error handling của Spring Integration.

Nếu ứng dụng đã có bean `JmsTemplate` tùy biến converter, cache hoặc QoS, cần xác định adapter đang sử dụng bean đó hay tạo template mới từ `ConnectionFactory`. **Có cùng factory không đồng nghĩa có cùng mọi cấu hình template.** Hãy cấu hình ngay tại adapter qua API được phiên bản đang dùng hỗ trợ hoặc truyền đúng template vào endpoint khi cần.

## 10. Xử lý lỗi và khắc phục sự cố

Các lỗi JMS phát sinh từ provider thường được `JmsTemplate` chuyển thành hệ `org.springframework.jms.JmsException` không kiểm tra, giúp caller phân loại. Tuy nhiên một thao tác gửi bị lỗi mạng **có thể có kết quả không chắc chắn**: broker đã nhận message nhưng client chưa nhận phản hồi thành công. Retry cần chú ý gửi trùng.

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Không tạo được `ConnectionFactory` | Thiếu starter/driver, cấu hình URL/credentials sai | Kiểm tra bean, classpath, broker URL, auth/TLS |
| Gửi báo destination không tồn tại | Queue/topic chưa được tạo hoặc không có quyền auto-create | Kiểm tra name, `pubSubDomain` và policy broker |
| `receive()` treo rất lâu | `receiveTimeout=0` (chờ vô hạn) | Đặt timeout dương hoặc -1 theo nhu cầu |
| Poller chạy nhưng không nhận message | Sai destination, converter lỗi, broker offline, consumer khác đã lấy | Kiểm tra queue depth, listener/consumer, log và timeout |
| Gửi JSON nhưng consumer nhận Java `ObjectMessage` | Payload object chưa serialize JSON | Serialize rõ ràng hoặc cấu hình converter thống nhất |
| Message bị xử lý trùng | Redelivery/retry sau lỗi, producer gửi lại | Dùng `eventId` + unique constraint/idempotent handler |
| Broker hết connection/session | Factory/pool/cache không phù hợp hoặc leak tài nguyên | Kiểm tra metrics connection/session, pool size, concurrency |
| DMLC không dừng/khởi động đúng | Cache consumer bên ngoài hoặc session lifecycle sai | Kiểm tra cách dùng `CachingConnectionFactory` với listener |
| Mất message khi DB lỗi | JMS receive đã ack trước khi DB thất bại | Đặt transaction đúng ranh giới và idempotency |
| Producer gửi thành công nhưng chưa có kết quả | Consumer chậm, message chờ hoặc DLQ | Xem queue depth, message age, consumer health và DLQ |

**Ba loại thời gian khác nhau:**

- `JmsTemplate.receiveTimeout`: thời gian chờ **một lần nhận**.
- Poller `fixedDelay`/`fixedRate`: nhịp gọi nguồn trong Spring Integration.
- Timeout của broker/provider khi kết nối/gửi hoặc thời gian sống JMS `timeToLive`: điều khiển những khía cạnh khác; TTL không phải thời gian caller chờ reply.

Trong production, nên theo dõi số message gửi/nhận thành công, lỗi gửi/nhận, thời gian mỗi thao tác, queue depth, tuổi message cũ nhất, số consumer, pool/cache sessions, reconnect count, redelivery và DLQ. Log nên có `eventId`, JMS message ID, correlation ID, destination và loại lỗi khi có; tránh đưa thông tin nhạy cảm từ payload vào log.

## 11. Bài thực hành: xây dựng nền JMS cho luồng nhập/xuất đơn hàng

**Bối cảnh:** một broker thử nghiệm có queue `orders.events` (ghi sự kiện) và `orders.import` (nhận lệnh nhập). Cấu hình factory theo provider; khởi tạo `orderJmsTemplate` như mục 3, và chỉ đăng ký một consumer test cho từng queue để dễ quan sát.

1. **Khởi tạo:** kiểm tra ứng dụng tạo được `ConnectionFactory` và `orderJmsTemplate`; log tên loại factory, không log credentials.
2. **Gửi JSON:** gọi `OrderEventPublisher.publishOrderPaid(...)`; dùng consumer test xác nhận nhận `TextMessage` chứa đúng `eventId` và properties cần thiết.
3. **Gửi message thủ công:** gọi `JmsTemplate.send(...)` để so sánh với `convertAndSend(...)`; xác định nơi converter hoạt động.
4. **Nhận đồng bộ:** đưa một `TextMessage` vào `orders.import`; gọi `receiveAndConvert(...)` và kiểm tra payload kiểu `String`.
5. **Queue rỗng:** thử `receiveTimeout(-1)` và `receiveTimeout(500)`; ghi nhận thời gian trả về và giá trị `null`.
6. **Polling:** chạy flow ở mục 5 với `fixedDelay(5000)` và `maxMessagesPerPoll(10)`; đưa 25 message vào queue, kiểm tra mỗi lượt không vượt giới hạn (nếu không có consumer cạnh tranh).
7. **Converter:** gửi `String`, `byte[]` và một DTO chưa serialize; giải thích vì sao DTO cần định dạng hợp đồng phù hợp.
8. **Broker offline:** ngắt kết nối trước và trong lúc gửi; kiểm tra exception, reconnect và việc retry có thể sinh message trùng.
9. **Transaction:** giả lập lỗi sau khi nhận nhưng trước khi ghi DB; so sánh nhận không transaction với transactional poller, quan sát redelivery.
10. **Caching:** đo số connection/session với factory chưa cache và factory có cache trong môi trường thử; tránh tạo hai cache layers và theo dõi hành vi listener khi restart.
11. **Đảm bảo nghiệp vụ:** dùng `eventId` làm unique key phía nhận; gửi lại cùng sự kiện để chứng minh DB không tạo bản ghi trùng.

Đối với thử nghiệm transaction, ack, redelivery và recovery, **phải dùng broker/provider thật hoặc môi trường container tương đương**. Mock `JmsTemplate` không chứng minh broker đã persist, resend hoặc rollback message.

### Câu hỏi tự đánh giá

1. `ConnectionFactory` khác `JmsTemplate` ở trách nhiệm nào? Vì sao một template cần factory?
2. `convertAndSend` khác `send` ở bước chuyển đổi nào?
3. Vì sao `receiveTimeout(-1)` phù hợp với polling inbound adapter khi queue rỗng?
4. `fixedDelay(5000)` có đồng nghĩa mỗi lần `receive()` chỉ chờ 5 giây không?
5. Vì sao không nên dùng `CachingConnectionFactory` chồng lên mọi provider pool hoặc listener container?
6. Cờ `sessionTransacted=true` trên một thao tác `receive()` có bảo vệ handler downstream không? Vì sao?
7. Điều gì xảy ra khi producer gửi lại cùng một event sau timeout không rõ kết quả? Cần khóa nào để chống trùng?
8. Khi nào dùng JMS message-driven inbound adapter thay vì polling adapter?
9. Vì sao `JmsTransactionManager` không tự bảo đảm DB transaction và JMS send cùng commit?
10. Khi message là JSON nhưng Java payload là DTO, bước nào phải được cấu hình/triển khai thêm?

## 12. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): sự phụ thuộc của các endpoint Spring Integration vào `JmsTemplate` và listener container; cấu hình polling, transaction, gateway.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, converter, ConnectionFactory và cách cache tài nguyên.
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `send`, `convertAndSend`, `receive`, `receiveAndConvert`, timeout, QoS và transaction.
- [Spring Framework API — CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html): cache session/producer/consumer, `sessionCacheSize` và vòng đời connection.
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): concurrency, recovery, acknowledge/transaction và lưu ý khi sử dụng cache bên ngoài.

**Ghi nhớ:** `ConnectionFactory` cung cấp tài nguyên kết nối JMS; `JmsTemplate` thực thi các thao tác gửi/nhận đồng bộ trên những tài nguyên đó. Trong Spring Integration, hãy chọn đúng endpoint (polling, message-driven, outbound adapter hoặc gateway), quản lý cache/timeout theo ngữ cảnh và đặt transaction quanh **toàn bộ đoạn xử lý cần bảo vệ**. Dữ liệu nghiệp vụ vẫn cần hợp đồng message và idempotency để an toàn khi gặp retry hoặc redelivery.
