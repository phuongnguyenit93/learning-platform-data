# Queue, Topic và mô hình nhận thông điệp

## Mục tiêu

Jakarta Messaging (trước đây thường gọi là JMS) cung cấp hai kiểu destination chính: Queue cho point-to-point và Topic cho publish/subscribe. Khi dùng Spring JMS, ứng dụng có thể nhận message bằng cách gọi đồng bộ các phương thức của `JmsTemplate` hoặc để listener container nhận bất đồng bộ thông qua `@JmsListener`.

Sau bài này, bạn có thể:

- Phân biệt Queue và Topic theo cách message được phân phối.
- Hiểu subscription thường, durable subscription và shared subscription.
- Chọn synchronous receive hay asynchronous listener.
- Dùng `JmsTemplate`, `@JmsListener` và listener container trong Spring.
- Cấu hình destination, selector, concurrency và transaction phù hợp.
- Tránh các lỗi phổ biến về loại destination, acknowledgement và xử lý trùng.

## 1. JMS nằm ở đâu trong kiến trúc?

JMS là API messaging chuẩn của Java. Từ Jakarta EE 9, namespace API chuyển từ `javax.jms` sang `jakarta.jms`; Spring Framework 6 trở lên dùng Jakarta Messaging. Một số thư viện cũ vẫn dùng namespace `javax.jms`, vì vậy cần kiểm tra phiên bản khi tích hợp.

Một ứng dụng JMS thường có các thành phần:

| Thành phần | Vai trò |
|---|---|
| ConnectionFactory | Tạo kết nối tới JMS provider/broker |
| Connection hoặc JMSContext | Đại diện kết nối đang hoạt động tới provider |
| Session | Ngữ cảnh tạo producer, consumer và message; quản lý acknowledgement/transaction |
| Destination | Đích gửi/nhận, thường là Queue hoặc Topic |
| MessageProducer | Gửi message tới destination |
| MessageConsumer | Nhận message từ destination hoặc subscription |
| Message | Envelope chứa body, headers và properties |

Spring bổ sung các lớp hỗ trợ như `JmsTemplate`, `DefaultMessageListenerContainer`, `@JmsListener` và `MessageConverter`, giúp ứng dụng không phải tự quản lý vòng đời Connection, Session và consumer trong từng thao tác.

Queue và Topic đều là các loại `jakarta.jms.Destination`. Chúng định nghĩa cách message được phân phối; chúng không quyết định ứng dụng phải nhận đồng bộ hay bất đồng bộ. Đây là hai lựa chọn độc lập.

## 2. Queue: point-to-point

Queue biểu diễn mô hình point-to-point (PTP). Producer gửi message vào một queue; một hoặc nhiều consumer có thể lắng nghe queue đó. Với mỗi lần giao, một message chỉ được phân phối cho một consumer trên queue.

Ví dụ: hệ thống đặt hàng gửi các công việc vào `orders.queue`. Có ba worker cùng nghe queue. Broker phân phối từng message cho một worker để xử lý. Ba worker chia sẻ tải thay vì mỗi worker nhận một bản sao của mọi đơn hàng.

~~~text
                 +------------------+
Producer ------> |   orders.queue   |
                 +------------------+
                    |      |      |
                    v      v      v
                 Worker  Worker  Worker
                    1      2      3

Mỗi message được giao cho một worker trong nhóm consumer.
~~~

Đặc điểm:

- Nhiều consumer trên cùng queue có thể cùng xử lý để tăng throughput.
- Mỗi message được giao cho một consumer tại một thời điểm giao.
- Nếu message chưa được xác nhận hoặc transaction bị rollback, broker có thể giao lại message.
- Consumer có thể dùng message selector để chỉ nhận các message có properties phù hợp; message không khớp vẫn có thể được consumer khác nhận hoặc tiếp tục nằm trong queue.
- Jakarta Messaging không quy định thuật toán chia message giữa nhiều consumer trên cùng queue.

Queue phù hợp khi mỗi công việc cần được một worker xử lý, chẳng hạn tạo hóa đơn, gửi email, xử lý ảnh hoặc cập nhật một bản ghi. Việc có nhiều worker không có nghĩa mọi worker đều nhận cùng một message.

**Lưu ý:** “Một message chỉ tới một consumer” mô tả phân phối của một lần giao, không phải cam kết exactly-once. Nếu consumer xử lý xong nhưng acknowledgement không được ghi nhận, message vẫn có thể được redeliver. Nghiệp vụ quan trọng nên có idempotency hoặc cơ chế phát hiện message đã xử lý.

## 3. Topic: publish/subscribe

Topic biểu diễn mô hình publish/subscribe (pub/sub). Producer publish message lên Topic; các subscriber đăng ký nhận message từ Topic thông qua các subscription.

Mỗi subscription độc lập nhận một bản sao của message. Vì thế, nếu ba hệ thống có ba subscription riêng, cả ba hệ thống đều có thể nhận cùng một event.

Ví dụ: khi đơn hàng được thanh toán, producer publish event lên `orders.events`. Billing, Analytics và Notification có các subscription riêng:

~~~text
                         +----------------------+
Publisher --------------> |    orders.events    |
                         +----------------------+
                           |          |         |
                           v          v         v
                       Billing    Analytics  Notification
                     subscription subscription subscription
                         A          B          C

Mỗi subscription nhận một bản sao của message.
~~~

Đặc điểm:

- Publisher không cần biết có bao nhiêu subscriber đang quan tâm.
- Mỗi subscription có luồng message riêng.
- Acknowledgement của một subscription không xác nhận message cho các subscription khác.
- Consumer có thể lọc message bằng selector.
- Một subscription có thể là durable hoặc non-durable; có thể là shared hoặc unshared.

Topic phù hợp cho event cần được nhiều hệ thống độc lập quan sát, ví dụ `OrderPaid`, `CustomerUpdated` hoặc `InventoryChanged`.

## 4. Subscription: durable, non-durable và shared

Cần phân biệt Topic với subscription. Topic là nơi publisher gửi message; subscription là trạng thái đăng ký mà JMS provider quản lý. Consumer là đối tượng trong ứng dụng dùng để nhận message từ subscription.

### 4.1. Non-durable subscription

Non-durable subscription chỉ tồn tại khi consumer còn hoạt động. Nếu ứng dụng chưa chạy hoặc đã đóng consumer khi message được publish, subscription không giữ lại message cho lần chạy sau.

Dùng non-durable subscription khi ứng dụng chỉ quan tâm message phát sinh trong thời gian nó đang hoạt động và chấp nhận bỏ lỡ message khi offline, ví dụ một dashboard cập nhật dữ liệu trực tiếp.

### 4.2. Durable subscription

Durable subscription được provider lưu lại ngay cả khi consumer tạm thời không hoạt động. Khi consumer kết nối lại với đúng subscription, nó có thể nhận những message đã được giữ trong thời gian offline.

Ví dụ: dịch vụ Billing phải xử lý mọi event thanh toán. Dịch vụ có thể tạm dừng để bảo trì nhưng vẫn cần nhận các event phát sinh trong lúc đó. Durable subscription phù hợp với yêu cầu này.

Các điểm cần nhớ:

- Subscription phải được tạo trước thời điểm publish để nhận những message tiếp theo.
- Subscription được nhận diện bằng tên; durable subscription không phải một consumer tạm thời.
- Provider giữ message theo chính sách cho đến khi giao/acknowledge hoặc message hết hạn.
- Durable không có nghĩa lưu vô thời hạn: TTL, dung lượng, retention và chính sách của broker vẫn có thể ảnh hưởng.
- Với unshared durable subscription, Jakarta Messaging yêu cầu client identifier; shared durable subscription có quy tắc nhận diện khác.

### 4.3. Shared subscription

Shared subscription cho phép nhiều consumer cùng đọc một subscription để chia sẻ tải. Mỗi message thuộc subscription đó được giao cho một trong các consumer đang chia sẻ subscription.

Cần phân biệt hai trường hợp:

- Hai subscription độc lập trên cùng Topic: mỗi subscription nhận một bản sao của message.
- Nhiều consumer cùng một shared subscription: các consumer chia nhau message của bản sao thuộc subscription đó.

Shared subscription có thể là durable hoặc non-durable. Đây là tính năng của Jakarta Messaging 2.0 trở lên; khả năng cụ thể cần được kiểm tra với JMS provider và phiên bản đang dùng.

| Kiểu subscription | Consumer offline | Cách phân phối trong subscription |
|---|---|---|
| Unshared non-durable | Message gửi khi không có consumer có thể bị bỏ lỡ | Một consumer |
| Shared non-durable | Không giữ subscription sau khi mọi consumer đóng | Nhiều consumer chia sẻ; mỗi message tới một consumer |
| Unshared durable | Message được giữ khi subscription không có consumer, theo chính sách provider | Một consumer tại một thời điểm |
| Shared durable | Subscription tồn tại khi consumer offline | Nhiều consumer chia sẻ; mỗi message tới một consumer |

## 5. Queue và Topic khác nhau thế nào?

| Tiêu chí | Queue | Topic |
|---|---|---|
| Mô hình | Point-to-point | Publish/subscribe |
| Phân phối message | Một consumer trong nhóm nhận mỗi lần giao | Mỗi subscription nhận một bản sao |
| Nhiều consumer | Chia tải trên cùng queue | Các consumer cùng shared subscription chia tải; subscription độc lập nhận bản sao riêng |
| Consumer offline | Message thường tiếp tục nằm trong queue theo chính sách broker | Non-durable subscription có thể bỏ lỡ; durable subscription giữ message theo chính sách provider |
| Use case | Work queue, job processing, command | Domain event, broadcast, fan-out |
| Ví dụ | `orders.queue` | `orders.events` |

Một cách chọn nhanh:

- Nếu một công việc cần được một worker xử lý, chọn Queue.
- Nếu nhiều hệ thống cần nhận độc lập cùng một event, chọn Topic với subscription riêng cho từng hệ thống.
- Nếu một subscription cần nhiều instance cùng chia tải, xem xét shared subscription.
- Nếu subscriber phải nhận event cả khi offline, dùng durable subscription và cấu hình retention/TTL phù hợp.

Không nên chọn Topic chỉ vì có nhiều instance của cùng một service. Nếu các instance cần chia tải và chỉ một instance nên xử lý mỗi message, hãy dùng Queue hoặc shared subscription. Ngược lại, không nên dùng một Queue duy nhất nếu mọi hệ thống độc lập đều phải nhận một bản sao của event.

## 6. Message selector

Message selector là biểu thức lọc dựa trên JMS message properties. Consumer chỉ nhận message có properties thỏa điều kiện selector.

Ví dụ publisher đặt property:

~~~java
jmsTemplate.convertAndSend("orders.queue", "order-42", message -> {
    message.setStringProperty("region", "APAC");
    message.setStringProperty("eventType", "OrderCreated");
    return message;
});
~~~

Consumer có thể chỉ nhận message cho khu vực APAC:

~~~java
@JmsListener(
    destination = "orders.queue",
    selector = "region = 'APAC'"
)
public void receiveApacOrder(String orderId) {
    // Xử lý đơn hàng khu vực APAC.
}
~~~

Selector đọc properties và các trường header được JMS cho phép trong biểu thức. Nó không phải câu truy vấn trên body JSON hay object payload. Nếu muốn lọc theo trường trong payload, hãy đưa trường đó thành JMS property khi publish hoặc xử lý điều kiện trong consumer.

Selector giúp định tuyến logic trong cùng destination, nhưng không thay thế authorization hay validation. Producer vẫn phải tạo property đúng kiểu và consumer vẫn phải kiểm tra payload.

## 7. Hai mô hình nhận message

Queue/Topic mô tả cách message được phân phối. Synchronous/asynchronous mô tả cách ứng dụng lấy message. Có thể nhận message từ Queue hoặc Topic bằng một trong hai cách, miễn destination và subscription được cấu hình phù hợp.

### 7.1. Synchronous receive: ứng dụng chủ động lấy message

Với synchronous receive, thread ứng dụng gọi phương thức nhận và chờ message. Trong Spring, `JmsTemplate` cung cấp các phương thức như `receive` và `receiveAndConvert`.

~~~java
import org.springframework.jms.core.JmsTemplate;

public final class QueuePoller {

    private final JmsTemplate jmsTemplate;

    public QueuePoller(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void pollOnce() {
        Object payload = jmsTemplate.receiveAndConvert("orders.queue");

        if (payload == null) {
            System.out.println("No message available");
            return;
        }

        System.out.println("Received: " + payload);
    }
}
~~~

Cần cấu hình `receiveTimeout` để giới hạn thời gian chờ. Nếu không có message trong thời gian chờ, phương thức nhận có thể trả về `null`. Nếu chờ vô hạn, thread gọi có thể bị giữ lâu.

Synchronous receive phù hợp với tác vụ cần chủ động lấy message theo nhịp riêng, ví dụ một batch poller hoặc công cụ quản trị. Nó thường không phải lựa chọn tốt cho service cần liên tục nhận message với throughput cao.

### 7.2. Asynchronous receive: listener được gọi khi có message

Với asynchronous receive, ứng dụng đăng ký listener; JMS provider và Spring listener container gọi listener khi message đến. Đây là mô hình thường dùng cho service xử lý message liên tục.

Spring hỗ trợ:

- `jakarta.jms.MessageListener`: interface JMS có phương thức `onMessage(Message)`.
- `@JmsListener`: đánh dấu một method trong managed bean làm endpoint nhận message.
- `MessageListenerAdapter`: chuyển một POJO thông thường thành listener và có thể chuyển payload trước khi gọi method.
- `DefaultMessageListenerContainer` và `SimpleMessageListenerContainer`: quản lý listener, connection, session và consumer.

Trong Spring Framework, `@EnableJms` bật cơ chế đăng ký các endpoint `@JmsListener`. Mỗi endpoint được phục vụ bởi một listener container được tạo từ `JmsListenerContainerFactory`.

## 8. Sử dụng @JmsListener trong Spring

Một POJO có thể nhận payload trực tiếp mà không cần tự triển khai `MessageListener`:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumers {

    @JmsListener(destination = "orders.queue")
    public void consumeQueue(String orderId) {
        System.out.println("Queue received: " + orderId);
    }

    @JmsListener(
        destination = "orders.events",
        containerFactory = "topicListenerContainerFactory"
    )
    public void consumeTopic(String event) {
        System.out.println("Topic received: " + event);
    }
}
~~~

Listener đầu tiên nhận từ Queue qua container mặc định. Listener thứ hai dùng factory được cấu hình cho Topic. Method argument có thể là payload đã chuyển đổi, JMS `Message`, hoặc các kiểu tham số được Spring hỗ trợ.

Nếu listener bean là singleton và container có nhiều consumer/thread, method có thể được gọi đồng thời. Trạng thái mutable dùng chung trong listener phải được bảo vệ thread-safe hoặc chuyển sang service có cơ chế đồng bộ thích hợp.

## 9. Cấu hình Queue và Topic riêng biệt

Với Spring JMS, loại destination được chọn bởi cấu hình của template hoặc listener container. `JmsTemplate` mặc định dùng queue domain khi tạo destination từ tên. Nếu dùng Topic, cần cấu hình `pubSubDomain` cho template gửi và listener container nhận.

Ví dụ cấu hình hai listener factory và hai template:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false); // Queue
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        return factory;
    }

    @Bean
    DefaultJmsListenerContainerFactory topicListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true); // Topic
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    JmsTemplate queueJmsTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean
    JmsTemplate topicJmsTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        return template;
    }
}
~~~

Gửi message:

~~~java
queueJmsTemplate.convertAndSend("orders.queue", "order-42");
topicJmsTemplate.convertAndSend("orders.events", "OrderCreated:order-42");
~~~

Đây là cấu hình tích hợp Spring, không phải chương trình độc lập có thể chạy chỉ bằng `javac`. Ứng dụng cần dependency Spring JMS, một Jakarta Messaging provider, ConnectionFactory và destination được provider hỗ trợ hoặc được cấu hình qua DestinationResolver.

Nếu dùng Spring Boot, hãy kiểm tra cấu hình auto-configuration của cả `JmsTemplate` và listener container. Property `spring.jms.pub-sub-domain=true` chuyển cấu hình mặc định sang Topic; sender và receiver phải dùng cùng destination domain. Nếu ứng dụng có cả Queue và Topic, tạo các template/factory riêng sẽ rõ ràng hơn.

## 10. Durable Topic subscription với Spring

Đối với một subscriber cần nhận message khi ứng dụng tạm offline, cấu hình durable subscription. Spring listener endpoint có thuộc tính `subscription`; listener container factory cần bật durable subscription. Với unshared durable subscription, cấu hình client ID ổn định.

Ví dụ phần factory:

~~~java
@Bean
DefaultJmsListenerContainerFactory durableTopicListenerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("billing-service");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Listener:

~~~java
@JmsListener(
    destination = "orders.events",
    subscription = "billing-subscription",
    containerFactory = "durableTopicListenerFactory"
)
public void consumeBillingEvent(String event) {
    // Xử lý event đã được giữ cho billing-subscription.
}
~~~

Tên subscription và client ID phải ổn định qua các lần khởi động. Không chạy nhiều consumer độc lập cùng một unshared durable subscription; nếu cần chia tải, kiểm tra shared durable subscription và mức hỗ trợ của provider. Cần quản lý vòng đời subscription: subscription cũ có thể tiếp tục tích lũy message cho tới khi bị hủy hoặc message hết hạn.

Persistent delivery mode và durable subscription giải quyết hai việc khác nhau. Persistent message yêu cầu provider lưu message theo delivery mode; durable subscription giữ bản sao cho một subscriber đã đăng ký kể cả khi subscriber offline. Đặt message persistent không tự tạo durable subscription.

## 11. Listener container, concurrency và thread safety

Listener container là lớp Spring đứng giữa JMS provider và method xử lý. Nó quản lý kết nối, session, consumer, vòng đời listener, concurrency và một số chính sách transaction/recovery.

Hai container phổ biến:

- `DefaultMessageListenerContainer`: thường dùng cho đa số trường hợp; hỗ trợ điều chỉnh runtime, recovery khi broker gián đoạn và tham gia transaction được quản lý bên ngoài.
- `SimpleMessageListenerContainer`: cấu trúc đơn giản hơn, phù hợp một số trường hợp ít yêu cầu điều chỉnh động.

Factory có thể cấu hình concurrency:

~~~java
factory.setConcurrency("2-6");
~~~

Giá trị này yêu cầu container duy trì số consumer/session trong phạm vi cấu hình mà container hỗ trợ. Với Queue, nhiều consumer thường chia tải. Với Topic, nếu là các subscription riêng thì mỗi subscription nhận bản sao; muốn nhiều consumer chia tải một bản sao phải dùng shared subscription.

JMS Session không phải đối tượng dùng đồng thời tùy ý từ nhiều thread. Listener container quản lý session/consumer cho từng luồng xử lý. Không tự chia sẻ một Session hoặc MessageConsumer giữa các thread của ứng dụng.

Khi tăng concurrency:

- Throughput có thể tăng nếu xử lý độc lập và broker đủ khả năng.
- Thứ tự hoàn tất xử lý có thể khác thứ tự nhận ban đầu.
- Listener bean có thể được gọi đồng thời và phải thread-safe.
- Database pool, downstream service và giới hạn broker cần đủ năng lực.
- Retry hoặc rollback có thể khiến message được giao lại.

Không nên đặt concurrency quá cao chỉ để tăng số thread. Hãy đo throughput, độ trễ, số message tồn đọng và thời gian xử lý thực tế.

## 12. Acknowledgement và transaction

Acknowledgement cho provider biết message đã được xác nhận. Các chế độ JMS thường gặp:

- `AUTO_ACKNOWLEDGE`: provider tự xác nhận sau khi listener hoàn tất theo semantics của JMS.
- `CLIENT_ACKNOWLEDGE`: client chủ động xác nhận; acknowledgement có thể áp dụng cho các message đã được session nhận trước đó.
- `DUPS_OK_ACKNOWLEDGE`: provider có thể xác nhận trễ để tăng hiệu năng; ứng dụng cần chấp nhận khả năng duplicate.
- Transacted Session: message receipt và các thao tác gửi trong cùng JMS Session được commit hoặc rollback theo transaction.

Với Spring listener container, `setSessionTransacted(true)` bật transaction cục bộ cho mỗi lần gọi listener. Nếu listener ném exception trước khi transaction commit, việc nhận message được rollback và message có thể được giao lại.

~~~java
factory.setSessionTransacted(true);
~~~

Điều này giúp xử lý lỗi an toàn hơn, nhưng JMS transaction cục bộ không tự bao gồm database transaction độc lập. Có thể xảy ra tình huống database đã commit nhưng JMS transaction rollback; message được giao lại và nghiệp vụ chạy lần nữa. Hãy dùng idempotency key, bảng inbox/deduplication hoặc XA/JTA nếu thực sự cần một transaction phân tán và chấp nhận chi phí vận hành.

Không nên mặc định rằng `AUTO_ACKNOWLEDGE` luôn đủ tin cậy cho nghiệp vụ quan trọng. Hãy đọc semantics của listener container và provider, cấu hình transacted session phù hợp, đồng thời kiểm tra redelivery và dead-letter policy của broker.

## 13. Thứ tự, redelivery và dead-letter

Queue không đồng nghĩa mọi message luôn được xử lý tuần tự khi có nhiều consumer. Mỗi session có thứ tự xử lý riêng, nhưng nhiều consumer chạy song song có thể hoàn tất theo thứ tự khác nhau. Topic cũng có thứ tự trong phạm vi subscription/consumer theo các quy tắc của provider, không tạo ra thứ tự toàn cục cho mọi subscriber.

Khi listener thất bại:

1. Nếu session được transacted và listener ném exception, transaction có thể rollback.
2. Provider có thể redeliver message.
3. Message có thể được giao nhiều lần; listener cần idempotent.
4. Sau số lần giao lại hoặc điều kiện provider cấu hình, message có thể bị chuyển vào dead-letter queue.

Dead-letter queue, giới hạn redelivery và backoff phụ thuộc JMS provider/broker; Jakarta Messaging không định nghĩa một chính sách chung duy nhất cho mọi broker. Cần cấu hình và giám sát theo broker đang dùng.

Các header/properties như `JMSRedelivered` hoặc `JMSXDeliveryCount` có thể hỗ trợ phát hiện message đã được giao lại. Không nên dựa vào chúng thay cho event ID ổn định và idempotency ở tầng nghiệp vụ.

## 14. Chọn mô hình nhận theo tình huống

| Tình huống | Destination | Mô hình nhận |
|---|---|---|
| Nhiều worker xử lý các đơn hàng khác nhau | Queue | `@JmsListener` với concurrency |
| Một service cần chủ động lấy batch công việc | Queue | Synchronous `JmsTemplate.receive` |
| Billing, Analytics và Notification cùng cần biết một event | Topic với subscription riêng | Asynchronous listener cho từng subscription |
| Subscriber phải nhận event khi offline | Topic durable subscription | Asynchronous listener container |
| Một subscription có nhiều instance chia tải | Shared Topic subscription hoặc Queue | Nhiều consumer trên cùng subscription/queue |
| Công cụ quản trị cần kiểm tra message mà không lấy ra | Queue | `QueueBrowser` nếu provider hỗ trợ |

Các quyết định nên xuất phát từ semantics nghiệp vụ: một message cần một worker hay nhiều hệ thống độc lập; ứng dụng có thể bỏ lỡ message lúc offline không; có cần xử lý song song không; và cần bảo đảm gì khi listener thất bại.

## 15. Lỗi thường gặp

- **Dùng Topic nhưng mong mỗi message chỉ được một service instance nhận:** nhiều subscription độc lập sẽ nhận các bản sao. Dùng shared subscription hoặc Queue nếu mục tiêu là chia tải.
- **Dùng Queue nhưng mong nhiều hệ thống đều nhận cùng message:** các consumer cạnh tranh trên một queue không nhận mỗi người một bản sao. Dùng Topic với subscription riêng.
- **Dùng non-durable Topic cho subscriber phải nhận đủ event:** subscriber offline có thể bỏ lỡ message. Tạo durable subscription.
- **Nghĩ message persistent tự động làm Topic durable:** persistent delivery và durable subscription là hai cấu hình khác nhau.
- **Cấu hình sender là Topic nhưng listener container là Queue:** hai phía không dùng cùng destination domain. Dùng template và factory có `pubSubDomain` tương ứng.
- **Dùng synchronous receive trong thread cần phản hồi nhanh:** thread bị block trong lúc đợi message. Đặt receive timeout hoặc dùng listener container.
- **Tăng concurrency nhưng listener dùng state mutable không thread-safe:** có thể gây race condition hoặc ghi dữ liệu sai.
- **Ack message trước khi nghiệp vụ hoàn tất:** lỗi sau acknowledgement có thể làm mất cơ hội redelivery.
- **Retry nhưng không idempotent:** cùng message có thể tạo tác động nghiệp vụ lặp.
- **Cho rằng JMS bảo đảm thứ tự toàn cục:** concurrency, nhiều session, nhiều subscription và broker policy ảnh hưởng thứ tự thực tế.

## 16. Checklist triển khai

- [ ] Đã chọn Queue hay Topic theo yêu cầu một worker hoặc nhiều subscriber độc lập.
- [ ] Nếu dùng Topic, đã xác định subscription là durable hay non-durable.
- [ ] Nếu cần chia tải trên Topic, đã xác minh provider hỗ trợ shared subscription.
- [ ] Sender và listener container dùng cùng destination domain.
- [ ] Đã chọn synchronous receive hay asynchronous listener theo nhu cầu xử lý.
- [ ] Đã cấu hình receive timeout cho synchronous receive.
- [ ] Đã cấu hình listener container và concurrency phù hợp.
- [ ] Listener an toàn khi được gọi đồng thời.
- [ ] Đã cấu hình acknowledgement/transaction và kiểm tra redelivery.
- [ ] Consumer có idempotency hoặc deduplication.
- [ ] Đã cấu hình message selector trên properties nếu cần lọc.
- [ ] Có giám sát queue depth, subscription backlog, processing latency và dead-letter.
- [ ] Đã kiểm thử broker restart, consumer offline, listener exception và message redelivery.

## 17. Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification — Queue semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#queue-semantics)
- [Jakarta Messaging 3.1 Specification — Topic semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#topic-semantics)
- [Jakarta Messaging 3.1 Specification — Creating a consumer on a topic](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#creating-a-consumer-on-a-topic)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
