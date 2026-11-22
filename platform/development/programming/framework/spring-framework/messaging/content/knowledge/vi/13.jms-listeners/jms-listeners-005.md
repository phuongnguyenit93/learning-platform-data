# destination, selector, subscription, concurrency và containerFactory trong Spring JMS Listener

## 1. Vai trò của các thuộc tính trong @JmsListener

Spring JMS cho phép một method Java nhận message bằng annotation `@JmsListener`. Annotation mô tả nơi nhận message và một số tùy chọn của consumer; Spring tạo listener endpoint rồi dùng listener container để quản lý connection, session, consumer và lifecycle.

Năm thuộc tính cần hiểu cùng nhau:

- **destination:** tên queue hoặc topic mà listener nhận message.
- **selector:** biểu thức lọc message theo JMS header và properties.
- **subscription:** tên subscription, thường dùng để nhận diện durable topic subscription.
- **concurrency:** số consumer hoặc phạm vi consumer mà listener container được phép chạy.
- **containerFactory:** tên bean factory tạo listener container với cấu hình kết nối và vận hành tương ứng.

Một listener thường có dạng:

~~~java
@JmsListener(
        destination = "orders.queue",
        selector = "priority >= 5",
        concurrency = "2-6",
        containerFactory = "ordersQueueFactory")
public void receive(OrderCommand command) {
    // Xử lý message.
}
~~~

Các thuộc tính này thuộc Spring JMS. Chúng không phải thuộc tính của Spring Messaging channel hoặc STOMP. Spring JMS dùng JMS provider và ConnectionFactory để kết nối tới broker.

Sau bài học, bạn cần có thể:

- Chọn đúng queue hoặc topic cho destination.
- Viết selector theo cú pháp JMS và phân biệt selector với điều kiện Java.
- Cấu hình durable subscription và tên subscription ổn định.
- Chọn concurrency phù hợp với queue, topic và loại subscription.
- Tạo nhiều listener container factory cho các nhóm listener khác nhau.
- Hiểu cách Spring tạo và quản lý listener container.
- Kiểm thử routing, filtering, subscription identity và tải consumer.

## 2. destination: listener nhận message ở đâu?

### 2.1 Queue và topic

Destination là queue hoặc topic do JMS provider quản lý. Cùng một tên destination có thể được phân giải thành queue hay topic tùy resolver và cấu hình listener container.

Với cấu hình Spring JMS phổ biến:

- `pubSubDomain = false`: dùng queue domain.
- `pubSubDomain = true`: dùng topic domain.

Queue thường phù hợp với công việc cần một consumer trong nhóm xử lý mỗi message. Topic phù hợp với publication mà nhiều subscription độc lập có thể cùng nhận bản sao.

Tên destination không phải broker URL, clientID hay subscription name. Broker URL xác định nơi kết nối; destination xác định nơi gửi/nhận bên trong broker.

### 2.2 Destination dạng String

`@JmsListener(destination = "orders.queue")` nhận tên destination dưới dạng chuỗi. Listener container dùng `DestinationResolver` để phân giải tên đó thành JMS Destination.

Spring JMS thường dùng `DynamicDestinationResolver` mặc định. Resolver này tạo hoặc tra cứu queue/topic theo chế độ domain của container. Nếu ứng dụng dùng JNDI hoặc cần quy tắc phân giải riêng, có thể cấu hình resolver tương ứng trên listener container factory.

Tên destination có thể được externalize qua property của ứng dụng. Khi dùng placeholder trong annotation, hãy bảo đảm property được khai báo cho từng môi trường và được Spring resolve khi xử lý annotation. Tên queue/topic nên được quản lý nhất quán giữa publisher, listener và broker provisioning.

### 2.3 Destination phải tồn tại và có quyền truy cập

Một số broker tự tạo destination khi ứng dụng tham chiếu tên chưa tồn tại; broker khác yêu cầu quản trị viên tạo trước. Không giả định hành vi auto-create giống nhau giữa các provider.

Listener cần quyền consume trên destination. Publisher cần quyền send. Connection thành công không đồng nghĩa ứng dụng có quyền đọc mọi queue hoặc subscribe mọi topic.

## 3. selector: lọc message tại broker

### 3.1 Selector hoạt động thế nào?

`selector` của `@JmsListener` là JMS message selector. Đây là biểu thức theo cú pháp selector của JMS, dựa trên JMS-defined headers và application properties có kiểu được hỗ trợ.

Ví dụ:

~~~java
@JmsListener(
        destination = "orders.queue",
        selector = "priority >= 5 AND eventType = 'OrderCreated'")
public void receive(OrderCommand command) {
    // Chỉ nhận message thỏa selector.
}
~~~

Broker chỉ giao cho consumer những message có selector đánh giá thành TRUE. Message không thỏa điều kiện vẫn có thể nằm trong queue hoặc được giao cho consumer khác có selector phù hợp, tùy topology và provider.

Selector không phải Java expression, SpEL hay SQL truy vấn database. Không gọi method, truy cập field của DTO hoặc dùng cú pháp lambda trong selector.

### 3.2 Selector đọc JMS headers và properties

Một số header JMS thường có thể dùng trong selector gồm:

- `JMSPriority`: mức ưu tiên.
- `JMSMessageID`: định danh message.
- `JMSCorrelationID`: correlation ID.
- `JMSType`: loại message.
- `JMSDeliveryMode`: delivery mode theo quy ước JMS.
- `JMSRedelivered`: trạng thái redelivery.

Ngoài ra, selector có thể đọc các JMS properties do publisher đặt, ví dụ `eventType`, `tenantCode` hoặc `priority` nếu các giá trị được thiết lập thành property hợp lệ.

**Selector không đọc trực tiếp body của message.** Nếu muốn lọc theo một thuộc tính nghiệp vụ, publisher phải đặt giá trị đó thành JMS property phù hợp. Ví dụ, trường `priority` nằm trong JSON body không tự động trở thành JMS property `priority`.

### 3.3 Cú pháp selector thường dùng

JMS selector hỗ trợ một tập biểu thức kiểu SQL có giới hạn, thường gồm:

| Cú pháp | Ví dụ |
|---|---|
| So sánh | `priority >= 5` |
| AND / OR / NOT | `eventType = 'Created' AND priority > 2` |
| IS NULL | `region IS NULL` |
| IN | `eventType IN ('Created', 'Updated')` |
| BETWEEN | `priority BETWEEN 3 AND 8` |
| LIKE | `tenantCode LIKE 'vn-%'` |

String literal dùng dấu nháy đơn. Tên property và kiểu dữ liệu phải phù hợp với JMS selector rules. Selector có thể có kết quả UNKNOWN khi property không tồn tại hoặc giá trị null; chỉ message có kết quả TRUE mới được chọn.

Hãy kiểm tra cú pháp và khả năng hỗ trợ của broker mục tiêu. Selector phức tạp có thể làm tăng chi phí lọc ở broker.

### 3.4 Đặt property để selector sử dụng

Publisher có thể đặt JMS property bằng `MessagePostProcessor`:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        orderCommand,
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setIntProperty("priority", 7);
            return message;
        }
);
~~~

Listener dùng selector:

~~~java
@JmsListener(
        destination = "orders.queue",
        selector = "eventType = 'OrderCreated' AND priority >= 5")
public void receive(OrderCommand command) {
    // Xử lý đơn hàng được chọn.
}
~~~

Body vẫn chứa payload theo converter đã cấu hình. Hai property được đặt riêng để broker có thể đánh giá selector trước khi giao message.

Không đưa dữ liệu nhạy cảm như token hoặc password vào JMS properties. Property có thể xuất hiện trong công cụ quản trị broker, log hoặc hệ thống giám sát.

## 4. subscription: danh tính của topic subscriber

### 4.1 Subscription name khác destination

Khi listener dùng topic, destination xác định topic được subscribe. Với durable subscription, tên subscription xác định luồng nhận cần được broker duy trì qua các lần consumer offline.

Ví dụ:

~~~java
@JmsListener(
        destination = "orders.events",
        subscription = "billing-projection-v1",
        containerFactory = "durableTopicFactory")
public void receive(OrderEvent event) {
    // Cập nhật projection.
}
~~~

Ở đây:

- `orders.events` là topic.
- `billing-projection-v1` là tên durable subscription.
- `durableTopicFactory` phải cấu hình topic domain và durable subscription.

Thuộc tính `subscription` không tự biến listener thành durable. Listener container factory phải bật durable subscription và cấu hình identity cần thiết.

### 4.2 Cấu hình durable subscription

Với unshared durable subscription theo JMS cổ điển, container cần clientID ổn định cùng subscription name ổn định. ClientID thuộc JMS connection; subscription name thuộc durable topic subscription.

Ví dụ factory:

~~~java
@Bean
public DefaultJmsListenerContainerFactory durableTopicFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("billing-projection-client");
    factory.setConcurrency("1");

    return factory;
}
~~~

Listener dùng tên subscription:

~~~java
@JmsListener(
        destination = "orders.events",
        subscription = "billing-projection-v1",
        containerFactory = "durableTopicFactory")
public void receive(OrderEvent event) {
    // Xử lý publication.
}
~~~

Factory và listener phải cùng dùng đúng topic, client identity và subscription name qua các lần restart. Nếu đổi tên subscription, broker có thể xem đó là subscription mới và để lại subscription cũ cùng backlog.

### 4.3 Durable và non-durable

- **Non-durable subscription:** tồn tại trong thời gian subscriber hoạt động; publication khi subscriber offline thường không được giữ cho subscriber đó.
- **Durable subscription:** broker giữ trạng thái subscription và có thể lưu message phù hợp trong thời gian consumer offline, theo persistence, expiration, quota và policy của provider.

Stop hoặc đóng listener container không đồng nghĩa xóa durable subscription. Xóa subscription là thao tác unsubscribe có chủ đích; không thực hiện mỗi lần shutdown nếu muốn giữ backlog.

### 4.4 Shared durable subscription

JMS 2.0 hỗ trợ shared durable subscription để nhiều consumer cùng tham gia một subscription. Khi đó, các consumer cạnh tranh nhận message trong cùng subscription; mỗi message được giao cho một consumer phù hợp trong nhóm.

Khả năng cấu hình shared subscription phụ thuộc phiên bản Spring, JMS provider và broker. Spring JMS có hỗ trợ cấu hình shared subscription trên các listener container phiên bản tương ứng. Hãy xác minh API như `setSubscriptionShared(true)` và semantics provider đang dùng trước khi tăng concurrency.

Phân biệt hai mô hình:

- Nhiều durable subscription riêng: mỗi subscription có thể nhận một bản sao của publication.
- Nhiều consumer cùng shared durable subscription: các consumer chia nhau message trong cùng subscription.

Không dùng nhiều subscription riêng để mong đạt competing consumers.

## 5. concurrency: số consumer đồng thời

### 5.1 Cấu hình tại factory hoặc annotation

`concurrency` quy định số consumer mà listener container có thể chạy. Với `DefaultMessageListenerContainer`, có thể dùng số cố định hoặc khoảng min-max.

Ví dụ:

~~~java
factory.setConcurrency("2-8");
~~~

Hoặc override tại listener:

~~~java
@JmsListener(
        destination = "orders.queue",
        concurrency = "3-6",
        containerFactory = "ordersQueueFactory")
public void receive(OrderCommand command) {
    // Xử lý message.
}
~~~

Concurrency trên annotation cho phép listener cụ thể override cấu hình concurrency của factory. Nếu không đặt ở annotation, container dùng giá trị từ factory hoặc mặc định của implementation.

### 5.2 Queue concurrency

Với queue, nhiều consumer thường hoạt động như competing consumers. Broker phân phối message cho các consumer theo cơ chế của provider, acknowledgement, prefetch và trạng thái tải.

Tăng concurrency có thể tăng throughput khi handler xử lý độc lập, nhưng cũng có thể:

- Tăng số connection/session hoặc tài nguyên broker cần dùng.
- Tăng tải database và dịch vụ downstream.
- Làm thay đổi thứ tự hoàn tất message.
- Tăng số message đang được giao nhưng chưa acknowledge.
- Làm lộ race condition nếu handler dùng shared mutable state.

Chọn concurrency theo năng lực xử lý downstream và đo thực tế. Không mặc định số consumer càng cao thì hệ thống càng nhanh.

### 5.3 Topic concurrency

Với topic non-durable, mỗi consumer thường là một subscription riêng. Tăng concurrency có thể khiến nhiều consumer cùng nhận publication, dẫn tới cùng một sự kiện được xử lý nhiều lần trong một ứng dụng.

Với unshared durable subscription, provider thường chỉ cho phép một consumer hoạt động trên subscription tại một thời điểm. Cấu hình concurrency lớn hơn một có thể gây xung đột hoặc lỗi khởi tạo consumer.

Nếu cần scale một durable subscription, hãy dùng shared durable subscription khi JMS provider và Spring listener container hỗ trợ. Kiểm tra ordering, selector, acknowledgement và phân phối tải trên broker mục tiêu.

### 5.4 Chọn khoảng min-max

Khoảng `2-8` cho phép container bắt đầu với số consumer tối thiểu và tăng lên khi cần, theo khả năng của listener container. Concurrency có thể được điều chỉnh bằng cấu hình phù hợp với workload.

Hãy bắt đầu với mức thấp, đo throughput, p95/p99 latency, queue depth, số session và tải database rồi tăng dần. Đối với listener cần giữ thứ tự xử lý, phải đánh giá kỹ trước khi tăng số consumer.

## 6. containerFactory: chọn cách tạo listener container

### 6.1 Vai trò của factory

`containerFactory` là tên bean tạo listener container cho method được đánh dấu `@JmsListener`.

Factory thường cấu hình:

- ConnectionFactory.
- Queue hay topic domain.
- Durable/shared subscription và clientID.
- Concurrency.
- Transaction và acknowledgement.
- MessageConverter.
- ErrorHandler.
- DestinationResolver.
- Recovery interval và các thiết lập container khác.

Một ứng dụng có thể có nhiều factory cho các loại listener khác nhau. Ví dụ, queue xử lý công việc có concurrency cao; durable topic projection dùng một consumer; listener audit dùng converter và transaction policy riêng.

Nếu không chỉ định `containerFactory`, Spring tìm factory mặc định theo tên `jmsListenerContainerFactory`. Tên mặc định này cần có bean tương ứng nếu ứng dụng không cung cấp một factory khác theo cơ chế cấu hình đang dùng.

### 6.2 Tạo queue factory

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory ordersQueueFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-8");
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

Factory này tạo listener container theo queue domain. Session transaction cho phép container commit hoặc rollback thao tác nhận theo cấu hình transaction. Transaction JMS không tự làm database và JMS commit nguyên tử nếu không có cơ chế phối hợp transaction phù hợp.

### 6.3 Tạo topic factory

~~~java
@Bean
public DefaultJmsListenerContainerFactory eventsTopicFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setConcurrency("1");

    return factory;
}
~~~

Factory này dùng topic domain và một consumer. Nếu cần durable subscription, bổ sung cấu hình durable và client identity theo loại subscription. Với shared durable subscription, bật tùy chọn shared tương ứng chỉ khi provider và Spring version hỗ trợ.

### 6.4 Dùng nhiều factory trong cùng ứng dụng

~~~java
@Component
public class OrderListeners {

    @JmsListener(
            destination = "orders.queue",
            selector = "priority >= 5",
            concurrency = "3-6",
            containerFactory = "ordersQueueFactory")
    public void processPriorityOrder(OrderCommand command) {
        // Xử lý công việc từ queue.
    }

    @JmsListener(
            destination = "orders.events",
            subscription = "billing-projection-v1",
            containerFactory = "durableTopicFactory")
    public void updateProjection(OrderEvent event) {
        // Cập nhật read model từ topic.
    }
}
~~~

Trong ví dụ, `ordersQueueFactory` và `durableTopicFactory` là hai bean factory được cấu hình riêng. Bean durableTopicFactory cần được khai báo như ví dụ durable subscription ở phần trước.

Tách factory giúp mỗi nhóm listener có cấu hình domain, transaction, concurrency và converter phù hợp. Không cần lặp lại toàn bộ cấu hình trong từng annotation.

## 7. Các thuộc tính khác của listener container đáng chú ý

Ngoài năm thuộc tính chính, cấu hình factory thường cần xem xét:

| Thuộc tính | Ý nghĩa |
|---|---|
| `setConnectionFactory` | Factory kết nối JMS provider |
| `setPubSubDomain` | Chọn queue hay topic |
| `setSessionTransacted` | Dùng transaction cho JMS session |
| `setMessageConverter` | Chuyển JMS Message thành payload Java |
| `setErrorHandler` | Xử lý lỗi phát sinh từ listener |
| `setDestinationResolver` | Phân giải tên destination |
| `setRecoveryInterval` | Khoảng chờ recovery trong container hỗ trợ |
| `setClientId` | Đặt JMS client identifier |
| `setSubscriptionDurable` | Bật durable topic subscription |
| `setSubscriptionShared` | Bật shared subscription khi phiên bản/provider hỗ trợ |

Tên API và khả năng cấu hình phụ thuộc Spring Framework/Spring Boot và JMS provider. Hãy đối chiếu tài liệu đúng phiên bản, đặc biệt với shared durable subscription, XA và các tùy chọn provider-specific.

## 8. Selector, destination và subscription tương tác ra sao?

Một listener topic durable có thể kết hợp destination, selector và subscription:

~~~java
@JmsListener(
        destination = "orders.events",
        selector = "eventType = 'OrderCreated' AND region = 'APAC'",
        subscription = "apac-order-projection-v1",
        containerFactory = "durableTopicFactory")
public void updateProjection(OrderEvent event) {
    // Chỉ xử lý publication được selector chọn.
}
~~~

Ý nghĩa:

1. Destination chọn topic `orders.events`.
2. Selector lọc publication theo JMS properties `eventType` và `region`.
3. Subscription đặt danh tính durable subscription.
4. Factory quyết định topic domain, client identity, durable mode, concurrency và transaction.

Selector của durable subscription cần ổn định. Provider có thể từ chối khi ứng dụng reconnect với cùng subscription identity nhưng selector hoặc một số thuộc tính cố định đã thay đổi. Nếu cần đổi hợp đồng selector, hãy lập kế hoạch migration subscription theo hướng dẫn broker, thay vì âm thầm đổi cấu hình production.

## 9. Vòng đời listener container

Spring quản lý listener container theo application context:

1. Khi context khởi động, listener endpoint được phát hiện từ `@JmsListener`.
2. Endpoint registrar dùng containerFactory được chỉ định để tạo container.
3. Container tạo connection/session/consumer từ ConnectionFactory.
4. Consumer bắt đầu nhận message và gọi method listener.
5. Khi lỗi kết nối, container/provider có thể thực hiện recovery theo cấu hình.
6. Khi context dừng, container dừng nhận message và giải phóng tài nguyên theo lifecycle.

Không tự tạo một consumer mới bên trong mỗi lần gọi listener. Không đóng connection/session mà container đang quản lý. Nếu cần tạm dừng hoặc khởi động lại listener, dùng lifecycle API của container hoặc cơ chế quản lý endpoint phù hợp.

Durable subscription thường vẫn tồn tại sau khi container stop. Muốn xóa subscription phải thực hiện unsubscribe theo quy tắc JMS/provider.

## 10. Lỗi thường gặp

- **Nhầm destination với subscription:** destination là queue/topic; subscription name định danh durable topic subscriber.
- **Dùng selector đọc field trong body:** JMS selector chỉ đánh giá headers và properties được hỗ trợ.
- **Đặt property sau khi gửi:** broker đã đánh giá selector trước khi message được giao; property cần được thiết lập trước khi send.
- **Quên pubSubDomain:** listener định mở topic nhưng factory lại dùng queue domain hoặc ngược lại.
- **Cho rằng subscription tự động durable:** cần bật durable subscription ở factory/container và cấu hình identity phù hợp.
- **Đổi subscription name mỗi lần deploy:** có thể tạo subscription mới và để lại backlog cũ.
- **Tăng concurrency cho unshared durable topic:** có thể xung đột vì nhiều consumer cùng mở một subscription không chia sẻ.
- **Tăng concurrency cho topic non-durable:** nhiều consumer có thể tạo nhiều subscription riêng và xử lý trùng publication.
- **Dùng nhiều factory cùng tên hoặc sai containerFactory:** listener có thể nhận cấu hình không mong muốn hoặc không khởi động.
- **Dùng selector sai kiểu property:** selector có thể không match vì property không tồn tại hoặc có kiểu dữ liệu không tương thích.
- **Dùng concurrency quá cao:** tăng tải broker và hệ thống downstream, làm giảm ổn định.
- **Cho rằng sessionTransacted bao phủ database:** transaction JMS cục bộ không tự tạo transaction phân tán.
- **Không kiểm thử trên broker mục tiêu:** selector, shared subscription, destination provisioning và recovery có thể khác theo provider.

## 11. Kiểm thử listener configuration

Nên có integration test xác minh cấu hình thực tế:

1. Listener queue nhận message từ đúng destination.
2. Listener chỉ nhận message thỏa selector.
3. Message không thỏa selector vẫn được xử lý theo topology dự kiến.
4. Listener topic nhận publication theo pub-sub domain.
5. Durable subscription nhận lại message còn hiệu lực sau khi consumer offline rồi reconnect.
6. Subscription name và clientID được giữ ổn định.
7. Concurrency queue tạo số consumer trong phạm vi cấu hình.
8. Topic durable unshared không vô tình tạo nhiều consumer xung đột.
9. Shared durable subscription hoạt động đúng khi hệ thống sử dụng.
10. Factory được chọn đúng theo containerFactory.
11. Transaction rollback dẫn tới redelivery theo broker policy.
12. Shutdown dừng container và giải phóng tài nguyên.

Unit test có thể kiểm tra service listener bằng cách gọi method trực tiếp. Nhưng destination resolution, selector, subscription, concurrency và broker delivery semantics cần integration test với JMS provider/broker mục tiêu.

## 12. Checklist thiết kế

Trước khi triển khai @JmsListener, hãy kiểm tra:

- Destination là queue hay topic?
- Tên destination có được quản lý trong cấu hình và broker provisioning không?
- Selector chỉ dùng JMS headers/properties hợp lệ và property được đặt trước khi gửi chưa?
- Listener có cần durable subscription không?
- Nếu durable, subscription name và client identity có ổn định không?
- Có cần shared durable subscription để scale nhiều consumer không?
- Concurrency có phù hợp với queue/topic và loại subscription không?
- containerFactory có đúng bean và đúng ConnectionFactory không?
- Transaction, converter, error handler và recovery có phù hợp không?
- Quyền consume/subscribe đã được cấp trên broker chưa?
- Có integration test cho selector, durable reconnect, concurrency và shutdown không?

Khi phối hợp đúng destination, selector, subscription, concurrency và containerFactory, mỗi listener sẽ nhận đúng nhóm message với số consumer và lifecycle phù hợp, đồng thời cấu hình broker được quản lý tập trung và dễ kiểm thử.