# Kiểm thử rollback, redelivery, selector và durable subscription

## Mục tiêu

Sau bài này, bạn có thể thiết kế integration test cho các luồng JMS trong Spring để chứng minh rằng:

- Listener chạy trong giao dịch JMS và message được rollback khi xử lý thất bại.
- Broker redeliver message sau rollback; ứng dụng nhận diện được lần giao lại.
- Message selector chỉ lọc theo JMS header/property, không đọc nội dung body.
- Durable topic subscription vẫn nhận được message được gửi trong lúc consumer offline.
- Các test không nhầm lẫn rollback của JMS với rollback của database và không phụ thuộc vào thời gian chờ tùy tiện.

Các ví dụ dùng Spring Framework 6+/Spring Boot 3+ và Jakarta Messaging (`jakarta.jms`). Với Spring Framework 5 / Spring Boot 2, API JMS thường dùng package `javax.jms`; không trộn hai hệ package trong cùng ứng dụng.

## 1. Kiểm thử messaging cần một broker thật

JMS là một giao thức và API giao tiếp với messaging provider. `JmsTemplate`, `@JmsListener` và listener container của Spring là lớp tích hợp; chúng không thay thế broker. Vì vậy, unit test chỉ mock `JmsTemplate` hoặc gọi trực tiếp listener không thể chứng minh hành vi rollback, redelivery, selector hay durable subscription của broker.

Nên chia test thành ba lớp:

1. **Unit test cho business handler:** kiểm tra logic xử lý payload, validation, idempotency và kết quả nghiệp vụ mà không cần broker.
2. **Spring integration test:** khởi tạo Spring context, listener container và JMS provider thật; gửi message và quan sát kết quả qua broker.
3. **Broker-specific test:** xác minh retry delay, maximum delivery attempts, dead-letter queue, persistence sau restart và các đặc tính riêng của ActiveMQ Artemis, IBM MQ, Azure Service Bus hoặc provider đang dùng.

Test nên dùng cùng loại provider với môi trường production nếu cần chứng minh hành vi broker cụ thể. Spring Boot có thể chạy embedded ActiveMQ Artemis bằng dependency server phù hợp và cấu hình `spring.artemis.mode=embedded`; cách này hữu ích cho test nhanh. Để xác minh persistence qua broker restart, failover hoặc cấu hình cluster, cần một broker có storage và topology tương đương production.

## 2. Rollback và redelivery hoạt động như thế nào?

Với một JMS session được cấu hình transaction, quá trình nhận message có thể được mô tả như sau:

1. Broker giao message cho consumer.
2. Listener thực hiện xử lý trong một JMS transaction.
3. Nếu listener kết thúc bình thường, container commit transaction và message được acknowledge.
4. Nếu listener ném exception ra ngoài, container rollback transaction.
5. Broker có thể giao lại message; lần giao lại được đánh dấu bằng metadata redelivery.

Trong Jakarta Messaging, với session transacted, commit xử lý acknowledgement; rollback phục hồi các message đã nhận trong transaction. Provider đặt header `JMSRedelivered` và tăng `JMSXDeliveryCount` khi giao lại message.

### Bật transaction cho listener container

Cấu hình `sessionTransacted=true` trên factory dùng bởi `@JmsListener`:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory transactedFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
~~~

`DefaultJmsListenerContainerFactory` tạo `DefaultMessageListenerContainer`, phù hợp cho phần lớn listener Spring. `sessionTransacted=true` yêu cầu mỗi lần xử lý message dùng local JMS transaction. Đặt concurrency bằng 1 trong test giúp thứ tự và số lần gọi dễ quan sát hơn; production có thể dùng concurrency cao hơn nếu logic và thứ tự message cho phép.

Ví dụ listener chủ động thất bại ở lần đầu:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.jms.JMSException;
import jakarta.jms.Message;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class RedeliveryProbe {

    final AtomicInteger attempts = new AtomicInteger();
    final AtomicReference<Boolean> redelivered = new AtomicReference<>();
    final AtomicInteger deliveryCount = new AtomicInteger(-1);
    final CountDownLatch completed = new CountDownLatch(1);

    @JmsListener(
        destination = "qa.rollback",
        containerFactory = "transactedFactory"
    )
    public void receive(Message message) throws JMSException {
        int attempt = attempts.incrementAndGet();

        if (attempt == 1) {
            throw new IllegalStateException("Simulated processing failure");
        }

        redelivered.set(message.getJMSRedelivered());

        if (message.propertyExists("JMSXDeliveryCount")) {
            deliveryCount.set(message.getIntProperty("JMSXDeliveryCount"));
        }

        completed.countDown();
    }
}
~~~

Exception phải được ném ra khỏi listener để transaction rollback. Nếu code bắt exception rồi chỉ log mà không ném lại, container có thể xem lần xử lý là thành công và commit message.

### Integration test xác nhận redelivery

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jms.core.JmsTemplate;

@SpringBootTest
class JmsRedeliveryIT {

    @Autowired
    JmsTemplate jmsTemplate;

    @Autowired
    RedeliveryProbe probe;

    @Test
    void rollsBackAndReceivesMessageAgain() throws Exception {
        jmsTemplate.convertAndSend("qa.rollback", "message-1");

        assertTrue(probe.completed.await(10, TimeUnit.SECONDS));
        assertEquals(2, probe.attempts.get());
        assertEquals(Boolean.TRUE, probe.redelivered.get());
        assertTrue(probe.deliveryCount.get() >= 2);
    }
}
~~~

Đây là test integration cần có broker đang chạy và các bean cấu hình ở trên. Hãy reset probe trước mỗi test nếu test class chạy nhiều lần hoặc dùng chung Spring context. Timeout 10 giây chỉ là giới hạn chờ của test; chọn giá trị theo môi trường CI, không dùng `Thread.sleep` để đoán thời điểm message được giao lại.

`JMSRedelivered=true` cho biết message đã từng được giao trước đó. `JMSXDeliveryCount` cho biết số lần giao theo provider. Test nên kiểm tra count tối thiểu phù hợp, không giả định mọi broker đều có cùng lịch retry hoặc delay.

## 3. Rollback không đồng nghĩa với retry vô hạn

Rollback trả message về trạng thái chưa được xác nhận trong transaction; việc giao lại tiếp theo do broker điều phối. Broker có thể áp dụng:

- Redelivery delay để tránh listener nhận lại ngay lập tức.
- Backoff tăng dần giữa các lần giao lại.
- Maximum delivery attempts.
- Dead-letter address/queue sau khi vượt số lần thử.
- Expiry hoặc chính sách loại bỏ message.

JMS specification không quy định một lịch retry chung cho mọi provider. Vì vậy, cần kiểm thử cấu hình broker riêng. Với ActiveMQ Artemis, các tùy chọn thường được đặt trong `address-setting`, ví dụ:

~~~xml
<address-setting match="orders">
    <redelivery-delay>1000</redelivery-delay>
    <max-delivery-attempts>5</max-delivery-attempts>
    <dead-letter-address>DLQ</dead-letter-address>
</address-setting>
~~~

Đây là cấu hình riêng của ActiveMQ Artemis, không phải cấu hình JMS portable. Cần khai báo address/queue cho DLQ và xác minh broker đang áp dụng address-setting đúng địa chỉ. Sau khi quá số lần giao thất bại, message được chuyển tới dead-letter address theo chính sách của broker.

Một message luôn thất bại được gọi là poison message. Nếu không giới hạn số lần giao lại, nó có thể chiếm consumer liên tục, tạo log/error storm và làm giảm thông lượng của các message khác. Hãy kiểm tra cả hai luồng: message được xử lý thành công sau một lần redelivery và message bị đưa vào DLQ sau khi vượt giới hạn.

### Duplicate delivery và tính idempotent

Redelivery là một phần của mô hình giao nhận ít nhất một lần (at-least-once). Ứng dụng phải chấp nhận khả năng cùng một nghiệp vụ được quan sát nhiều lần.

Ví dụ: listener ghi một bản ghi vào database rồi tiến trình dừng trước khi JMS transaction commit. Broker giao lại message; lần thứ hai có thể tạo bản ghi trùng nếu ứng dụng không chống lặp.

Các cách bảo vệ thường dùng:

- Dùng business key hoặc event ID ổn định để nhận diện message.
- Lưu inbox/processed-message record với unique constraint trong cùng database transaction với nghiệp vụ.
- Nếu event đã được xử lý, trả về thành công để JMS transaction commit mà không lặp side effect.
- Dùng outbox để phát message sau khi database transaction commit.
- Nếu cần atomicity giữa database và JMS, cân nhắc XA/JTA cùng resource XA-capable; hiểu rõ chi phí vận hành và giới hạn của provider.

`sessionTransacted=true` chỉ quản lý local JMS transaction. Nó không tự rollback transaction JDBC/JPA độc lập. Spring `JmsTransactionManager` quản lý một `ConnectionFactory`; nó không biến hai resource JMS và database thành một transaction phân tán. Đừng viết test chỉ xác nhận listener rollback rồi kết luận database cũng rollback.

## 4. Kiểm thử message selector

Message selector là biểu thức lọc dựa trên JMS headers và message properties. Cú pháp là một tập con của SQL-92 conditional expression. Selector không thể truy cập payload/body của message.

Ví dụ selector:

~~~sql
eventType = 'PAYMENT' AND priority >= 5
~~~

Consumer chỉ nhận message có property `eventType` là chuỗi `PAYMENT` và property số `priority` lớn hơn hoặc bằng 5.

### Gắn selector vào @JmsListener

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    @JmsListener(
        destination = "qa.events",
        selector = "eventType = 'PAYMENT' AND priority >= 5"
    )
    public void receive(String payload) {
        // Xử lý payload đã được converter chuyển đổi.
    }
}
~~~

Selector được gửi tới JMS provider khi consumer được tạo. Provider lọc message trước khi giao cho listener; Spring không tải toàn bộ message rồi tự lọc body.

### Gửi message có properties

~~~java
import org.springframework.jms.core.JmsTemplate;

public class EventPublisher {

    private final JmsTemplate jmsTemplate;

    public EventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishPayment(String payload) {
        jmsTemplate.convertAndSend("qa.events", payload, message -> {
            message.setStringProperty("eventType", "PAYMENT");
            message.setIntProperty("priority", 7);
            return message;
        });
    }
}
~~~

Đoạn code dùng `MessagePostProcessor` để gắn properties vào JMS message trước khi gửi. Selector chỉ nhìn thấy các property được set ở đây, không nhìn thấy field bên trong chuỗi JSON payload.

### Test selector phải có cả message khớp và không khớp

Một test có giá trị cần gửi tối thiểu ba trường hợp:

| Message | eventType | priority | Kết quả mong đợi |
|---|---|---:|---|
| M1 | PAYMENT | 7 | Listener nhận |
| M2 | PAYMENT | 2 | Listener bỏ qua |
| M3 | ORDER | 9 | Listener bỏ qua |

Với queue, message không khớp selector vẫn nằm trong queue và có thể được consumer khác có selector phù hợp nhận. Với topic, selector là một phần của subscription; chỉ message khớp được thêm vào subscription đó. Một subscriber có selector không nhận được toàn bộ message của topic.

### Các lỗi selector thường gặp

- Đặt filter vào body JSON rồi mong selector đọc được: selector không truy cập message body.
- Gửi property dạng String nhưng so sánh như numeric: selector không tự chuyển kiểu property sang kiểu mong muốn.
- Sai tên property hoặc khác chữ hoa/thường: identifier của property phân biệt chữ hoa/thường.
- So sánh property không tồn tại: giá trị được xem là NULL; biểu thức có thể trả UNKNOWN chứ không phải TRUE.
- Dùng dấu nháy kép cho string literal: selector dùng dấu nháy đơn, ví dụ `eventType = 'PAYMENT'`.
- Thay selector trong khi durable subscription cũ vẫn tồn tại: có thể làm subscription bị từ chối hoặc bị thay thế tùy trạng thái và provider.

Để test selector đúng, hãy assert cả số lần listener được gọi và nội dung message đã nhận. Không chỉ kiểm tra rằng một message phù hợp được nhận, vì điều đó không phát hiện trường hợp message không phù hợp cũng bị giao.

## 5. Durable subscription cho topic

JMS có hai mô hình chính:

- **Queue (point-to-point):** message được lưu trên queue và được phân phối cho một consumer phù hợp. Queue không dùng durable subscription.
- **Topic (publish/subscribe):** message được phân phối theo subscription. Mỗi subscription có bản sao logic riêng.

Một non-durable subscription chỉ tồn tại khi consumer hoạt động; khi consumer đóng, subscription và các message đang chờ của nó có thể bị xóa. Durable subscription được broker lưu lại và tiếp tục tích lũy message trong khi không có consumer đang kết nối, cho đến khi message được nhận/acknowledge, hết hạn hoặc subscription bị xóa theo quy định.

Durable subscription không có nghĩa là mọi message sẽ được lưu vô hạn. Cần xét delivery mode, message expiration, broker persistence, giới hạn dung lượng, quota và chính sách quản trị subscription.

### Cấu hình durable topic listener trong Spring

Với một durable subscription không chia sẻ, cần cấu hình topic domain, client ID ổn định và subscription name ổn định:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class DurableTopicConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setClientId("billing-consumer");
        factory.setSubscriptionDurable(true);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
~~~

Listener khai báo tên subscription và selector:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class BillingEventsListener {

    @JmsListener(
        id = "billingEventsSubscription",
        destination = "billing.events",
        subscription = "billing-events-v1",
        selector = "eventType = 'BILLING'",
        containerFactory = "durableTopicFactory"
    )
    public void receive(String payload) {
        // Xử lý sự kiện billing.
    }
}
~~~

Trong ví dụ:

- `setPubSubDomain(true)` chọn topic thay vì queue.
- `setClientId(...)` đặt client identifier của JMS connection. Giá trị phải ổn định khi khởi động lại cùng subscription và duy nhất theo quy tắc của broker.
- `setSubscriptionDurable(true)` bật durable subscription.
- `subscription = "billing-events-v1"` xác định tên subscription.
- `selector` lọc message theo JMS properties.
- `concurrency = "1"` phù hợp với unshared durable subscription, chỉ cho phép một consumer hoạt động cùng lúc.

Tên topic, client ID, subscription name và selector phải được giữ nhất quán khi kết nối lại subscription cũ. Nếu triển khai nhiều instance cùng tiêu thụ một subscription, cần dùng shared durable subscription và kiểm tra broker hỗ trợ JMS 2.0/Jakarta Messaging tương ứng. Trong Spring factory có thể cấu hình `setSubscriptionShared(true)`; khi đó mỗi message của subscription được giao cho một consumer trong nhóm, không phải broadcast tới tất cả consumer.

### Selector là một phần của durable subscription

Với durable subscription, selector không chỉ là filter tạm thời của một lần chạy listener. Provider lưu selector cùng subscription. Khi tạo consumer mới trên subscription cũ, client phải dùng cùng topic, subscription name, client ID (nếu đã đặt) và selector.

Jakarta Messaging quy định nếu một unshared durable subscription đang không có active consumer mà ứng dụng tạo lại với cùng tên/client ID nhưng khác topic, selector hoặc noLocal, thao tác đó tương đương unsubscribe subscription cũ và tạo subscription mới. Điều này có thể làm mất backlog đang chờ. Nếu cần thay đổi selector mà vẫn bảo toàn message cũ, hãy thiết kế migration riêng, ví dụ tạo subscription mới có tên versioned, chuyển consumer và xử lý backlog trước khi xóa subscription cũ.

## 6. Kiểm thử durable subscription khi consumer offline

Một test đúng cần chứng minh message được publish trong khoảng thời gian không có consumer vẫn được nhận sau khi consumer quay lại.

Luồng kiểm thử:

1. Khởi động broker và durable listener với client ID, subscription name, topic và selector đã định trước.
2. Xác minh broker đã tạo subscription. Chỉ kiểm tra Spring context khởi động hoặc bean tồn tại là chưa đủ; nên kiểm tra trạng thái subscription qua broker management API/JMX hoặc một tín hiệu readiness có ý nghĩa.
3. Dừng listener container để consumer ngừng hoạt động, nhưng giữ broker chạy và không unsubscribe durable subscription.
4. Publish một message có property khớp selector vào topic, dùng delivery mode PERSISTENT nếu muốn kiểm tra cả khả năng lưu message bền vững.
5. Publish thêm một message không khớp selector.
6. Khởi động lại listener bằng cùng client ID, subscription name, topic và selector.
7. Chờ bằng latch/queue có timeout và xác nhận chỉ message khớp được nhận.
8. Xác nhận backlog đã được acknowledge; nếu listener lỗi, xác minh message được redeliver theo transaction/policy.

Có thể điều khiển container bằng `JmsListenerEndpointRegistry`:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;

MessageListenerContainer container =
    registry.getListenerContainer("billingEventsSubscription");

container.stop();
// Publish message trong khi consumer offline, broker vẫn hoạt động.
container.start();
~~~

Đây là mảnh test điều khiển listener container, cần inject `JmsListenerEndpointRegistry` và `JmsTemplate` trong test. Trước khi publish, hãy xác minh subscription đã được tạo và consumer đã dừng hẳn. Sau khi start, dùng một `CountDownLatch`, `BlockingQueue` hoặc Awaitility để chờ message, không dùng `Thread.sleep` cố định.

Để kiểm tra durable subscription tồn tại qua broker restart, cần broker persistence thực sự được bật và message có delivery mode phù hợp. Test chỉ dừng listener container rồi bật lại trong cùng tiến trình broker chứng minh consumer offline recovery; nó chưa chứng minh khả năng phục hồi sau khi broker process hoặc máy chủ bị dừng.

### Những điều cần xác minh khi test durable

- Message publish trước khi subscription được tạo không tự động được phát lại cho subscription vừa tạo.
- Message được gửi khi durable subscription đang inactive mới được tích lũy cho subscription đó.
- Message không khớp selector không được thêm vào subscription.
- Message persistent và broker storage phải được cấu hình nếu yêu cầu sống sót qua broker restart.
- Message có expiration có thể hết hạn trước khi consumer quay lại.
- Broker quota hoặc policy có thể giới hạn backlog.
- Unsubscribe sẽ xóa durable subscription; không gọi unsubscribe trong cleanup thông thường nếu test cần giữ subscription để kiểm tra lần chạy sau.
- Cùng một unshared durable subscription không được có hai consumer active đồng thời.

## 7. Kết hợp rollback, selector và durable subscription trong một test plan

Các hành vi này độc lập nhưng có thể cùng xuất hiện trên một listener. Hãy tách test để dễ xác định nguyên nhân khi thất bại:

| Test | Setup | Thao tác | Assertion |
|---|---|---|---|
| Rollback | Listener factory transacted | Listener ném exception lần đầu | Lần sau nhận lại cùng message; `JMSRedelivered=true` |
| Redelivery limit | Broker có max attempts và DLQ | Listener luôn ném exception | Message cuối cùng xuất hiện ở DLQ |
| Selector match | Consumer có selector | Gửi property khớp selector | Listener nhận message |
| Selector mismatch | Consumer có selector | Gửi property không khớp | Listener không nhận message |
| Durable offline | Subscription đã được tạo | Dừng consumer, publish topic message, start lại | Consumer nhận backlog |
| Durable selector | Durable subscription có selector | Publish một message khớp và một message không khớp khi offline | Chỉ message khớp được lưu cho subscription |
| Durable identity | Subscription đã tồn tại | Kết nối lại bằng cùng identity | Consumer tiếp tục backlog |
| Selector migration | Durable subscription cũ đã inactive | Tạo consumer cùng identity nhưng selector khác | Test xác minh hành vi provider; migration dùng subscription name mới nếu cần giữ backlog |

Mỗi test nên dùng destination và subscription name riêng để tránh message từ test trước ảnh hưởng kết quả test sau. Nếu dùng chung broker/context, cleanup cần xóa queue tạm và kiểm soát durable subscription một cách có chủ đích.

## 8. Quan sát và chẩn đoán khi test thất bại

Khi một test redelivery timeout, hãy kiểm tra theo thứ tự:

1. Factory của listener có thực sự dùng `sessionTransacted=true` không?
2. Annotation có tham chiếu đúng `containerFactory` không?
3. Listener có ném exception ra khỏi method không?
4. Broker có nhận rollback và tăng delivery count không?
5. Broker có đặt redelivery delay dài hơn timeout test không?
6. Message có hết hạn hoặc bị đưa vào DLQ trước khi test nhận lại không?
7. Test có đang dùng cùng broker, destination và transaction configuration với listener không?

Khi selector test nhận sai message:

1. Xác minh property được set trên JMS message, không chỉ trong JSON body.
2. Xác minh property type (String, integer, boolean) đúng với biểu thức.
3. Kiểm tra tên property và dấu nháy của string literal.
4. Kiểm tra selector thực tế trên listener container, không chỉ trong source annotation.
5. Xác định destination là queue hay topic để hiểu nơi message không khớp sẽ nằm lại.

Khi durable test không nhận backlog:

1. Xác minh subscription đã được tạo trước khi consumer dừng.
2. Xác minh destination là topic.
3. Kiểm tra client ID, subscription name, selector và noLocal có khớp subscription ban đầu.
4. Xác minh broker không tự unsubscribe khi container dừng hoặc test cleanup chạy.
5. Kiểm tra message chưa hết hạn và delivery mode/storage phù hợp.
6. Kiểm tra broker management để biết backlog có thật sự tồn tại hay không.

Log nên ghi message ID, correlation ID, delivery count, redelivered flag, destination, consumer ID và kết quả xử lý. Tránh log toàn bộ payload nhạy cảm. Metrics nên theo dõi số lần redelivery, số message vào DLQ, số selector mismatch nếu broker có metric tương ứng, số subscription inactive và độ dài backlog.

## 9. Lỗi thường gặp

- **Mock broker rồi kết luận rollback đúng:** mock không thực thi JMS transaction hoặc redelivery semantics.
- **Dùng AUTO_ACKNOWLEDGE cho listener cần độ tin cậy:** Spring cảnh báo lỗi listener có thể làm message bị acknowledge và mất.
- **Bắt exception rồi không ném lại:** container có thể commit thay vì rollback.
- **Cho rằng rollback JMS tự rollback database:** local JMS transaction và JDBC/JPA transaction là hai resource riêng.
- **Không giới hạn redelivery:** poison message có thể lặp vô hạn; cần backoff và DLQ.
- **Chỉ assert listener được gọi hai lần:** cần xác nhận message thực sự redelivered qua `JMSRedelivered` hoặc `JMSXDeliveryCount`.
- **Dùng selector đọc body JSON:** selector chỉ đọc headers/properties.
- **Gửi property sai kiểu:** biểu thức numeric không hoạt động như mong muốn nếu property được gửi dưới dạng chuỗi.
- **Dùng durable subscription cho queue:** durable subscription là tính năng của topic.
- **Đổi client ID hoặc subscription name giữa các lần chạy:** provider có thể tạo subscription khác hoặc từ chối kết nối.
- **Thay selector của durable subscription cũ:** có thể làm subscription cũ bị thay thế và backlog bị mất.
- **Kiểm tra durable bằng cách restart listener nhưng không xác minh subscription:** test có thể pass nhờ một subscription mới hoặc message vẫn nằm ở queue khác.
- **Cho rằng durable đồng nghĩa lưu vô hạn:** message expiration, quota và broker storage policy vẫn có hiệu lực.

## 10. Checklist trước khi merge

- [ ] Integration test chạy với JMS provider thật, không chỉ mock.
- [ ] Listener factory đặt `sessionTransacted=true` cho luồng cần rollback.
- [ ] Test tạo exception ở lần đầu và xác minh redelivery.
- [ ] Test xác minh `JMSRedelivered` và/hoặc `JMSXDeliveryCount`.
- [ ] Broker có redelivery delay, maximum attempts và DLQ phù hợp.
- [ ] Listener xử lý duplicate an toàn bằng idempotency/inbox.
- [ ] Selector chỉ dùng header/property; test có cả match và mismatch.
- [ ] Property type và tên được kiểm tra chính xác.
- [ ] Durable subscription dùng topic, client ID, name và selector ổn định.
- [ ] Test publish khi consumer offline sau khi subscription đã được tạo.
- [ ] Test xác nhận backlog được nhận lại và message không khớp selector bị loại khỏi subscription.
- [ ] Có test riêng cho broker restart nếu yêu cầu persistence qua restart.
- [ ] Cleanup không vô tình unsubscribe subscription cần giữ lại.
- [ ] Test dùng timeout/latch thay cho sleep tùy tiện.
- [ ] Log/metric đủ để điều tra redelivery và DLQ.

## Tài liệu tham khảo

- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): listener container, transaction và acknowledgment.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receive và message-driven POJO.
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, factory và endpoint registry.
- [Spring Framework — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): cấu hình listener container.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): transaction, acknowledgement, selector, redelivery và durable subscription.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): ví dụ tích hợp `JmsTemplate`, `@JmsListener` và embedded Artemis.
- [ActiveMQ Artemis — Documentation](https://activemq.apache.org/components/artemis/documentation/): redelivery delay, maximum delivery attempts và dead-letter address.
