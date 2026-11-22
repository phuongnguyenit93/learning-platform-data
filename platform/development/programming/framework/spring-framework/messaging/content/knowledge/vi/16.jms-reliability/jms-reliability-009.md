# Expiration, delivery delay và sự khác biệt giữa các nhà cung cấp JMS

## 1. Hai cơ chế thời gian với hai mục đích khác nhau

Trong JMS, một message có thể được giữ lại trong broker một khoảng thời gian giới hạn hoặc được trì hoãn trước khi consumer có thể nhận. Hai cơ chế này thường bị nhầm lẫn:

- **Expiration / Time-to-live (TTL):** xác định thời điểm message hết hiệu lực. Sau thời điểm đó, provider không được tiếp tục giao message cho consumer.
- **Delivery delay:** xác định khoảng thời gian tối thiểu phải trôi qua sau khi gửi trước khi provider được phép giao message.

TTL trả lời câu hỏi **message còn giá trị đến khi nào?** Delivery delay trả lời câu hỏi **message sớm nhất được phép xuất hiện với consumer khi nào?**

Hai giá trị độc lập và có thể được dùng cùng nhau. Nếu TTL ngắn hơn delivery delay, message có thể hết hạn trước khi đến thời điểm đủ điều kiện giao.

JMS chuẩn hóa API và một phần semantics, nhưng cách broker lưu message chờ, quét message hết hạn, chuyển message sang expiry destination và hỗ trợ lịch giao nâng cao có thể khác giữa các nhà cung cấp.

Sau bài học, bạn cần có thể:

- Giải thích TTL, JMSExpiration và message expiration.
- Giải thích delivery delay và JMSDeliveryTime.
- Tính được khoảng thời gian một message có thể được giao.
- Cấu hình TTL và delivery delay bằng Jakarta Messaging API.
- Cấu hình hai giá trị này bằng Spring JmsTemplate.
- Phân biệt delivery delay với redelivery delay, timeout và scheduled job.
- Hiểu sự khác nhau giữa ActiveMQ Classic, ActiveMQ Artemis và IBM MQ.
- Thiết kế expiry queue/address, đồng bộ đồng hồ và kiểm thử theo broker thực tế.

## 2. Expiration và Time-to-live

### 2.1 TTL là gì?

Time-to-live là thời gian tính bằng milliseconds mà message được phép tồn tại trong hệ thống messaging kể từ lúc gửi. Producer đặt TTL khi gửi message. Provider tính thời điểm hết hạn và biểu diễn qua header chuẩn `JMSExpiration`.

Ví dụ:

- TTL 60.000 ms: message hết hạn khoảng 60 giây sau khi gửi.
- TTL 300.000 ms: message có hiệu lực khoảng 5 phút.
- TTL 0: message không có thời điểm hết hạn theo JMS.

TTL thường dùng cho dữ liệu chỉ còn giá trị trong một khoảng thời gian, chẳng hạn:

- Giá hoặc báo giá chỉ hợp lệ trong một phút.
- Lệnh cập nhật trạng thái cũ không còn cần thiết sau một thời hạn.
- Cache invalidation event có thể bị bỏ qua sau khi dữ liệu đã được đồng bộ lại.
- Thông báo tạm thời không cần xử lý nếu consumer nhận quá muộn.

TTL không bảo đảm message sẽ được xử lý trong khoảng thời gian đó. Nó chỉ giới hạn thời gian message còn đủ điều kiện được giao. Nếu consumer không hoạt động, message có thể hết hạn trước khi được nhận.

### 2.2 JMSExpiration

`JMSExpiration` là thời điểm hết hạn tuyệt đối do provider tính khi gửi. Giá trị được biểu diễn bằng milliseconds kể từ epoch UTC.

Với TTL bằng 0, `JMSExpiration` bằng 0, nghĩa là không hết hạn theo TTL. Với TTL dương, provider tính expiration dựa trên thời điểm gửi cộng TTL.

JMS quy định với giao dịch transacted, mốc tính TTL là lúc client gọi send, không phải lúc transaction commit. Vì vậy, transaction bị giữ lâu có thể làm giảm thời gian hiệu lực còn lại của message ngay khi message được commit.

Provider nên cố gắng xử lý expiration chính xác, nhưng JMS không quy định một độ chính xác thời gian tuyệt đối. Việc broker phát hiện và loại bỏ message hết hạn phụ thuộc implementation.

### 2.3 Message hết hạn thì chuyện gì xảy ra?

Khi expiration đã đến, provider không nên giao message đó cho consumer như một message còn hiệu lực. Broker có thể loại bỏ message khi:

- Message vừa đến broker.
- Message đang chờ trong queue.
- Broker chuẩn bị dispatch message tới consumer.
- Tác vụ quét expiration định kỳ chạy.

JMS không chuẩn hóa một destination chung để lưu message hết hạn và cũng không bảo đảm producer nhận thông báo rằng message đã expired. Nhiều broker có cấu hình expiry queue hoặc expiry address riêng để chuyển message hết hạn sang nơi kiểm tra.

Do đó, cần phân biệt:

- **Expired message:** message vượt quá TTL.
- **Undeliverable / poison message:** message không xử lý được sau một số lần giao lại hoặc theo policy của broker.
- **Dead-letter message:** message được chuyển tới DLQ theo dead-letter policy.

Expiry destination và DLQ có thể là hai nơi khác nhau với quy trình vận hành khác nhau.

## 3. Delivery delay và JMSDeliveryTime

### 3.1 Delivery delay là gì?

Delivery delay là khoảng thời gian tối thiểu tính từ lúc gửi trước khi provider được phép giao message cho consumer. API chuẩn có từ JMS 2.0.

Các API chính:

~~~java
MessageProducer producer = session.createProducer(destination);
producer.setDeliveryDelay(30_000L);
~~~

Hoặc với API đơn giản `JMSContext`:

~~~java
context.createProducer()
        .setDeliveryDelay(30_000L)
        .send(destination, "remind customer");
~~~

Thời gian được tính bằng milliseconds. Giá trị mặc định là 0, nghĩa là không trì hoãn.

Delivery delay đặt ra **thời điểm sớm nhất** provider có thể giao message. Nó không bảo đảm consumer nhận chính xác tại thời điểm đó. Broker đang tải cao, consumer chưa hoạt động hoặc queue đang có message khác có thể khiến việc nhận xảy ra muộn hơn.

### 3.2 JMSDeliveryTime

`JMSDeliveryTime` là header chuẩn của JMS 2.0, biểu diễn thời điểm message sớm nhất có thể được giao, dưới dạng milliseconds kể từ epoch UTC.

Provider tính delivery time bằng cách cộng delivery delay với thời điểm client gửi message. Với transacted send, mốc tính vẫn là lúc client gọi send, không phải lúc commit transaction.

Client không được nhận message trước delivery time. Sau thời điểm đó, provider có thể giao message khi các điều kiện khác cho phép.

Có thể đọc header trên message đã nhận:

~~~java
long deliveryTime = message.getJMSDeliveryTime();
long expiration = message.getJMSExpiration();
~~~

Các giá trị này hữu ích để quan sát message đã được trì hoãn bao lâu và còn hiệu lực đến khi nào. Chúng không phải bộ đếm thời gian thực thi handler.

### 3.3 Delivery delay không phải lịch lặp

JMS delivery delay chuẩn chỉ trì hoãn lần giao ban đầu. Nó không tự tạo lịch chạy lặp, cron, hoặc tự gửi lại message mỗi giờ.

Nếu cần lịch giao lặp hoặc cron, cần dùng scheduler extension của broker, một scheduler service riêng hoặc một ứng dụng lập lịch bền vững. Các tính năng mở rộng này thường không portable giữa các provider.

## 4. TTL và delivery delay khi dùng cùng nhau

Hai giá trị cùng bắt đầu từ thời điểm gửi, nhưng có ý nghĩa khác nhau:

- Delivery time là thời điểm sớm nhất message được phép giao.
- Expiration time là thời điểm message không còn được phép giao.

Ví dụ message được gửi lúc 12:00:00:

| Thiết lập | Giá trị | Thời điểm |
|---|---:|---|
| Send time | — | 12:00:00 |
| Delivery delay | 30 giây | Sớm nhất 12:00:30 |
| TTL | 120 giây | Hết hạn lúc 12:02:00 |
| Khoảng có thể giao | 90 giây | Từ 12:00:30 đến trước khi hết hạn |

Nếu TTL chỉ là 20 giây nhưng delivery delay là 30 giây:

- Message hết hạn lúc 12:00:20.
- Message chỉ đủ điều kiện giao từ 12:00:30.
- Message đã hết hạn trước khi đủ điều kiện giao.

Vì vậy, khi dùng đồng thời hai giá trị, phải bảo đảm TTL dài hơn delivery delay cộng với khoảng thời gian consumer có thể cần để xử lý backlog.

Một công thức thiết kế đơn giản:

~~~text
TTL > delivery delay + thời gian chờ backlog dự kiến
~~~

Đây chỉ là ngân sách thiết kế; broker vẫn có thể giao muộn hơn do tải, outage hoặc consumer không hoạt động. Nếu nghiệp vụ cần thời hạn tuyệt đối, hãy xác minh deadline ở tầng xử lý chứ không chỉ dựa vào TTL.

## 5. Cấu hình bằng Jakarta Messaging API

### 5.1 MessageProducer

Với API cổ điển, TTL và delivery delay là thuộc tính của producer:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public class DelayedPublisher {

    public void publish(
            ConnectionFactory connectionFactory,
            Queue queue) {

        try (JMSContext context =
                     connectionFactory.createContext(Session.AUTO_ACKNOWLEDGE)) {

            context.createProducer()
                    .setDeliveryDelay(5_000L)
                    .setTimeToLive(60_000L)
                    .send(queue, "order.reminder");
        }
    }
}
~~~

Ví dụ dùng Jakarta Messaging 2.0+ và cần provider ConnectionFactory tương thích. Producer được cấu hình delivery delay 5 giây và TTL 60 giây. Message sớm nhất được giao sau 5 giây và hết hạn khoảng 60 giây sau lúc gửi.

### 5.2 API MessageProducer

Với API Session/MessageProducer, có thể cấu hình producer trước khi gửi:

~~~java
MessageProducer producer = session.createProducer(queue);

try {
    producer.setDeliveryDelay(5_000L);
    producer.setTimeToLive(60_000L);

    TextMessage message = session.createTextMessage("order.reminder");
    producer.send(message);
}
finally {
    producer.close();
}
~~~

`MessageProducer.setDeliveryDelay` có từ JMS 2.0. Các giá trị này áp dụng cho những message được gửi qua producer đó cho tới khi thay đổi cấu hình producer.

Trong API cổ điển, overload `send(message, deliveryMode, priority, timeToLive)` cho phép chỉ định TTL cho một lần gửi. Delivery delay vẫn là thuộc tính producer; không có tham số delivery delay tương ứng trong overload send này.

### 5.3 Thời điểm bắt đầu trong transaction

Nếu Session là transacted, TTL và delivery delay được tính từ thời điểm gọi send. Ví dụ:

1. Transaction bắt đầu lúc 12:00:00.
2. Ứng dụng gọi send với TTL 60 giây và delay 10 giây lúc 12:00:05.
3. Transaction commit lúc 12:00:50.
4. Thời điểm hết hạn vẫn xấp xỉ 12:01:05, không phải 12:01:50.
5. Thời điểm đủ điều kiện giao sớm nhất vẫn xấp xỉ 12:00:15.

Transaction commit muộn có thể khiến message chỉ còn một khoảng thời gian ngắn để được giao sau khi nó xuất hiện trong broker.

## 6. Cấu hình bằng Spring JmsTemplate

### 6.1 TTL cần bật explicit QoS

`JmsTemplate` hỗ trợ cấu hình delivery mode, priority, TTL và delivery delay.

Khi muốn các giá trị delivery mode, priority và TTL do ứng dụng cấu hình được truyền vào lời gọi send, cần bật `explicitQosEnabled`:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);

        template.setExplicitQosEnabled(true);
        template.setTimeToLive(60_000L);
        template.setDeliveryDelay(5_000L);

        return template;
    }
}
~~~

Sau đó gửi message:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "order.reminder");
~~~

Trong ví dụ:

- `setTimeToLive(60_000L)` đặt TTL 60 giây.
- `setDeliveryDelay(5_000L)` đặt delivery delay 5 giây.
- `setExplicitQosEnabled(true)` yêu cầu JmsTemplate sử dụng QoS values được cấu hình cho delivery mode, priority và TTL.
- Delivery delay được áp dụng riêng qua JMS producer nếu giá trị không âm.

Nếu chỉ gọi `setTimeToLive` mà không bật explicit QoS, JmsTemplate có thể dùng giá trị mặc định hoặc giá trị do provider quản trị cấu hình thay vì TTL đã đặt trên template.

### 6.2 Delivery delay có thiết lập riêng

`JmsTemplate.setDeliveryDelay(long)` yêu cầu JMS 2.0. Giá trị mặc định là -1, nghĩa là template không truyền delivery delay vào producer.

- -1: không áp dụng delivery delay qua template.
- 0: gửi không trì hoãn.
- Số dương: số milliseconds cần trì hoãn tối thiểu.

Khác với TTL, delivery delay không nằm trong nhóm QoS values được điều khiển bởi `explicitQosEnabled`. Hãy cấu hình nó riêng và xác minh JMS provider hỗ trợ JMS 2.0.

### 6.3 JmsTemplate và phạm vi áp dụng

Các thiết lập trên JmsTemplate là cấu hình của template, vì vậy tất cả send operation sử dụng instance đó sẽ chịu cùng chính sách TTL/delivery delay.

Nếu mỗi message cần một thời gian trì hoãn khác nhau, không nên thay đổi một thuộc tính của JmsTemplate dùng chung giữa nhiều thread theo từng request. Có thể dùng một producer riêng cho thao tác đó, hoặc dùng `JmsTemplate.execute` với Session/Producer callback để cấu hình MessageProducer cho lần gửi cụ thể.

`MessagePostProcessor` thao tác trên JMS Message trước khi gửi. Nó có thể đặt JMS properties hoặc correlation ID, nhưng delivery delay chuẩn là thuộc tính của MessageProducer, không phải một property tùy ý trên Message.

### 6.4 QosSettings

`QosSettings` của Spring JMS gom delivery mode, priority và TTL. Nó không thay thế thiết lập delivery delay.

Ví dụ:

~~~java
import jakarta.jms.DeliveryMode;

import org.springframework.jms.support.QosSettings;

QosSettings qos = new QosSettings(
        DeliveryMode.PERSISTENT,
        4,
        60_000L);

jmsTemplate.setQosSettings(qos);
jmsTemplate.setDeliveryDelay(5_000L);
~~~

`setQosSettings` bật explicit QoS cho các giá trị delivery mode, priority và TTL. Delivery delay vẫn được cấu hình bằng `setDeliveryDelay`.

## 7. Per-message delivery delay với Spring

Khi mỗi message có delay khác nhau, hãy cấu hình producer cho đúng lần gửi. Ví dụ dưới đây dùng Session callback để JmsTemplate quản lý Connection/Session, còn ứng dụng tạo producer với delay riêng:

~~~java
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.springframework.jms.core.JmsTemplate;

public void sendDelayed(
        JmsTemplate jmsTemplate,
        String payload,
        long delayMillis,
        long ttlMillis) {

    jmsTemplate.execute(session -> {
        Queue queue = session.createQueue("orders.queue");
        MessageProducer producer = session.createProducer(queue);

        try {
            producer.setDeliveryDelay(delayMillis);
            producer.setTimeToLive(ttlMillis);

            TextMessage message = session.createTextMessage(payload);
            producer.send(message);
        }
        finally {
            producer.close();
        }

        return null;
    });
}
~~~

Đây là method minh họa trong một service đã được inject JmsTemplate; nó cần JMS 2.0 và provider hỗ trợ delivery delay. Session được quản lý bởi template, producer được đóng sau khi gửi.

Nếu ứng dụng dùng transaction, hãy cấu hình transaction trên JmsTemplate hoặc transaction manager theo đúng yêu cầu. Không tự commit hoặc đóng Session mà template đang quản lý.

## 8. Expiry destination và xử lý message hết hạn

JMS chuẩn không quy định một expiry queue chung. Broker có thể cung cấp cấu hình riêng để chuyển message hết hạn sang destination khác.

Expiry destination hữu ích để:

- Kiểm tra message có TTL quá ngắn.
- Phát hiện consumer xử lý backlog chậm.
- Phân tích clock skew giữa producer và broker.
- Đối soát các thông báo đã hết hiệu lực.
- Phân biệt message hết hạn với message lỗi do listener.

Một số broker gọi đây là expiry address, expiry queue hoặc message expiry policy. Cần cấu hình destination đích, quyền truy cập và retention của chính destination đó.

Không nên replay message hết hạn một cách tự động nếu nghiệp vụ đã qua deadline. Trước khi gửi lại, phải kiểm tra dữ liệu còn hiệu lực hay không và có cần tạo một command mới với deadline mới hay không.

## 9. Sự khác nhau giữa các nhà cung cấp

JMS chuẩn định nghĩa API TTL và delivery delay, nhưng broker có thể khác nhau về cách lưu scheduled message, quét expiration, chuyển message hết hạn và hỗ trợ tính năng mở rộng.

### 9.1 Apache ActiveMQ Classic

ActiveMQ Classic hỗ trợ message expiration. Producer đặt TTL; client tính thời điểm expiration khi gửi và broker kiểm tra message khi đến, khi chờ dispatch hoặc trong quá trình quét destination. Đồng hồ của producer và broker cần được đồng bộ để tránh message hết hạn sớm hoặc muộn.

ActiveMQ Classic cũng có scheduler extension. Scheduler cần được bật bằng cấu hình broker `schedulerSupport=true`. Ứng dụng có thể dùng các property đặc thù:

| Property | Ý nghĩa |
|---|---|
| `AMQ_SCHEDULED_DELAY` | Trì hoãn lần giao đầu, milliseconds |
| `AMQ_SCHEDULED_PERIOD` | Khoảng cách giữa các lần giao lặp |
| `AMQ_SCHEDULED_REPEAT` | Số lần lặp |
| `AMQ_SCHEDULED_CRON` | Lịch cron |

Ví dụ đặt lịch giao sau 60 giây:

~~~java
import org.apache.activemq.ScheduledMessage;

message.setLongProperty(
        ScheduledMessage.AMQ_SCHEDULED_DELAY,
        60_000L);

producer.send(message);
~~~

Các property scheduler này là extension của ActiveMQ Classic, không phải JMS portable API. Cần bật scheduler ở broker và kiểm tra phiên bản đang dùng. Không dùng chúng nếu mục tiêu là chuyển đổi broker mà không sửa code.

### 9.2 Apache ActiveMQ Artemis

Artemis hỗ trợ TTL theo JMS và có expiry address để chuyển message hết hạn sang địa chỉ khác. Quản trị viên có thể cấu hình expiry address theo address/queue policy.

Artemis hỗ trợ scheduled delivery bằng property riêng `_AMQ_SCHED_DELIVERY`, còn có hằng số `Message.HDR_SCHEDULED_DELIVERY_TIME` trong API tương ứng. Giá trị là thời điểm tuyệt đối tính bằng milliseconds từ epoch, không phải khoảng delay:

~~~java
long scheduledTime = System.currentTimeMillis() + 5_000L;

message.setLongProperty(
        "_AMQ_SCHED_DELIVERY",
        scheduledTime);

producer.send(message);
~~~

Đây là extension của Artemis. Khi dùng JMS 2.0 chuẩn, ưu tiên `MessageProducer.setDeliveryDelay` hoặc `JMSProducer.setDeliveryDelay` nếu provider/client version hỗ trợ. Khi dùng property đặc thù, cần thống nhất clock và API với broker.

### 9.3 IBM MQ

IBM MQ hỗ trợ delivery delay qua JMS 2.0. Khi ứng dụng đặt delivery delay, queue manager sử dụng staging queue nội bộ và delivery delay processor để giữ message cho tới khi hết thời gian trì hoãn, sau đó chuyển tới destination đích.

IBM MQ duy trì semantics expiration trong thời gian message nằm trên staging queue. Do đó message vẫn có thể hết hạn trước khi được chuyển sang queue đích nếu TTL đã hết.

Tài liệu IBM MQ nêu một số giới hạn theo tính năng, phiên bản và topology. Ví dụ, delivery delay không hỗ trợ kết hợp với retained publications hoặc message grouping trong các trường hợp được tài liệu mô tả. Nếu ứng dụng dùng retained publication hoặc grouping, cần kiểm tra đúng phiên bản IBM MQ trước khi bật delivery delay.

### 9.4 Bảng so sánh

| Chủ đề | ActiveMQ Classic | ActiveMQ Artemis | IBM MQ |
|---|---|---|---|
| TTL / expiration | Hỗ trợ; broker kiểm tra expiration | Hỗ trợ; có expiry address | Ánh xạ expiration theo JMS/MQMD |
| Expired message routing | Cấu hình broker-specific | Expiry address | Policy/queue manager phù hợp |
| Scheduled delivery extension | AMQ_SCHEDULED_DELAY và scheduler | _AMQ_SCHED_DELIVERY, timestamp tuyệt đối | JMS 2.0 delivery delay qua staging queue |
| Scheduler enablement | Cần bật schedulerSupport cho scheduler extension | Có hỗ trợ scheduled delivery | Queue manager xử lý qua staging queue |
| Khả năng portable | JMS TTL chuẩn; scheduler properties riêng | JMS TTL chuẩn; property scheduled riêng | JMS TTL và JMS 2.0 delivery delay |
| Điểm cần kiểm tra | Đồng hồ client/broker và scheduler persistence | Expiry address, scheduled property, clock | Retained publication, message grouping và staging queue |

Bảng trên mô tả các cơ chế được tài liệu provider công bố; khả năng thực tế còn phụ thuộc phiên bản broker, client library, cấu hình destination và transport. Không suy luận mọi tính năng của một phiên bản sẽ có trong mọi phiên bản khác.

## 10. Những yếu tố ảnh hưởng tới expiration và delivery delay

### 10.1 Đồng bộ đồng hồ

JMSExpiration và JMSDeliveryTime là các thời điểm tuyệt đối. Producer tính thời gian dựa trên đồng hồ máy gửi; broker có thể so sánh với đồng hồ của nó.

Nếu đồng hồ lệch nhau:

- Message có thể bị xem là hết hạn sớm.
- Message có thể tồn tại lâu hơn TTL dự kiến.
- Scheduled delivery có thể chạy sớm hoặc muộn so với kỳ vọng.

Dùng NTP hoặc cơ chế đồng bộ thời gian của hạ tầng. Theo dõi clock drift giữa ứng dụng, broker và các node trong cluster.

### 10.2 Broker outage

Nếu broker dừng trong lúc có message đang chờ scheduled delivery, khả năng message còn lại sau restart phụ thuộc persistence và scheduler implementation của provider.

Không giả định scheduled message luôn bền vững chỉ vì message có delivery mode persistent. Hãy kiểm thử broker restart với đúng storage configuration và loại scheduler đang dùng.

### 10.3 Consumer backlog

Delivery delay chỉ đặt thời điểm sớm nhất. Nếu queue có backlog, consumer không đủ capacity hoặc broker đang phục hồi, message có thể được nhận muộn hơn nhiều.

TTL cần đủ dài cho cả delay và khoảng chờ backlog thực tế. Nếu message hết hạn trong backlog, broker có thể loại bỏ nó trước khi consumer xử lý.

### 10.4 Delivery mode và TTL là hai khái niệm riêng

- **Persistent delivery mode:** yêu cầu provider lưu message theo semantics bền vững của broker.
- **TTL:** giới hạn thời gian message còn hiệu lực.
- **Delivery delay:** trì hoãn thời điểm sớm nhất được phép giao.

Một message persistent vẫn có thể hết hạn. Một message không hết hạn không tự động được bảo đảm tồn tại qua broker restart nếu delivery mode hoặc broker persistence không phù hợp.

### 10.5 Chính sách quản trị broker

JMS cho phép provider hoặc quản trị viên cấu hình override một số giá trị delivery mode, priority, TTL và delivery delay. Khả năng này không bắt buộc ở mọi provider.

Nếu ứng dụng đặt TTL 10 phút nhưng broker policy ghi đè TTL, header sau khi gửi có thể phản ánh giá trị đã bị override. Hãy kiểm tra cả cấu hình client lẫn broker khi quan sát kết quả.

## 11. Phân biệt với các cơ chế thời gian khác

| Cơ chế | Điều khiển điều gì? | Bên quản lý chính |
|---|---|---|
| TTL / expiration | Message còn hiệu lực đến khi nào | Producer và broker |
| Delivery delay | Thời điểm sớm nhất được giao | Producer và broker |
| Redelivery delay | Chờ bao lâu trước khi giao lại sau rollback/nack | Broker policy |
| Receive timeout | Consumer chờ message bao lâu | Consumer/API |
| Connection timeout | Chờ thiết lập kết nối bao lâu | JMS client/provider |
| Listener recovery interval | Chờ trước khi Spring thử tạo lại listener resources | Spring container |
| Scheduled job / cron | Thời điểm chạy một tác vụ hoặc lịch lặp | Scheduler/application |

Delivery delay không thay thế redelivery delay. Nếu listener ném exception và transaction rollback, broker dùng redelivery policy để quyết định lần giao lại. Delivery delay chủ yếu áp dụng cho lần giao ban đầu.

TTL cũng không phải timeout xử lý handler. Message có thể được giao trước expiration rồi listener tiếp tục xử lý sau khi TTL đã qua. Nếu nghiệp vụ cần hủy xử lý khi deadline hết, phải kiểm tra deadline ở tầng ứng dụng và thiết kế cancellation/compensation riêng.

## 12. Kiểm thử expiration và delivery delay

Nên có integration test với broker mục tiêu thay vì chỉ mock MessageProducer. Các test cần xác minh semantics provider thực tế.

### 12.1 TTL

- Gửi message TTL ngắn và nhận trước khi hết hạn.
- Để message nằm trong queue quá TTL rồi xác minh consumer không nhận được.
- Xác minh JMSExpiration trên message đã gửi/nhận nếu API/provider cho phép quan sát.
- Kiểm tra message hết hạn có được chuyển tới expiry destination hay bị loại bỏ.
- Kiểm tra TTL bằng 0 không đặt expiration theo TTL.
- Kiểm tra clock synchronization và thời gian xử lý expiration của broker.

### 12.2 Delivery delay

- Gửi message với delay 5 giây.
- Xác minh consumer không nhận trước thời điểm delivery time.
- Xác minh message có thể được nhận sau thời điểm đó.
- Đọc JMSDeliveryTime và so sánh với thời điểm gửi.
- Kiểm tra delay 0 và giá trị mặc định.
- Kiểm tra provider khi broker restart trong lúc message đang chờ.
- Kiểm tra topic subscription tồn tại tại thời điểm gửi.

Không kiểm tra bằng cách yêu cầu message phải xuất hiện đúng chính xác millisecond. Dùng khoảng thời gian chấp nhận được và timeout đủ rộng để tránh test flaky do scheduler, CI hoặc broker load.

### 12.3 TTL kết hợp delivery delay

Kiểm tra hai trường hợp:

1. TTL dài hơn delay: message có một khoảng thời gian để được giao sau khi delay kết thúc.
2. TTL ngắn hơn delay: message hết hạn trước khi đủ điều kiện giao.

Đây là test quan trọng để phát hiện cấu hình không hợp lý trong production.

### 12.4 Test khác biệt provider

Nếu ứng dụng hỗ trợ nhiều broker, chạy cùng bộ integration test trên từng provider/version. Đặc biệt kiểm tra:

- Expiry address/queue.
- Scheduler persistence sau restart.
- Delivery delay extension.
- Message grouping và retained publication.
- Admin override.
- Clock skew và độ chính xác expiration.

## 13. Lỗi thường gặp

- **Nhầm TTL với delivery delay:** một giá trị xác định thời điểm hết hạn, giá trị kia xác định thời điểm sớm nhất được giao.
- **Đặt TTL ngắn hơn delivery delay:** message có thể hết hạn trước khi được giao.
- **Cho rằng TTL bắt đầu sau khi delay kết thúc:** TTL bắt đầu từ thời điểm send.
- **Cho rằng delivery delay bảo đảm giao đúng giờ:** đó chỉ là thời điểm sớm nhất, không phải deadline giao.
- **Nghĩ TTL 0 nghĩa là hết hạn ngay:** trong JMS, TTL 0 nghĩa là không hết hạn theo TTL.
- **Quên explicitQosEnabled trong JmsTemplate:** TTL cấu hình có thể không được truyền vào send nếu không bật explicit QoS.
- **Nghĩ MessagePostProcessor đặt được delivery delay chuẩn:** delivery delay là thuộc tính producer, không phải message property.
- **Dùng vendor property như API JMS chuẩn:** scheduler properties không portable.
- **Dùng timestamp tuyệt đối như duration:** Artemis scheduled-delivery property cần thời điểm epoch, còn JMS setDeliveryDelay nhận khoảng milliseconds.
- **Không đồng bộ clock:** producer và broker có thể tính expiration khác nhau.
- **Nhầm expiry queue với DLQ:** expiry xử lý message hết hạn; DLQ xử lý message không giao/không xử lý được theo policy.
- **Cho rằng persistent message không thể hết hạn:** persistent và TTL độc lập.
- **Nhầm delivery delay với redelivery delay:** lần giao đầu và lần giao lại là hai cơ chế khác nhau.
- **Không kiểm thử restart:** scheduled message có thể phụ thuộc storage và scheduler của provider.

## 14. Checklist thiết kế và vận hành

Trước khi cấu hình TTL hoặc delivery delay, hãy kiểm tra:

- Message còn giá trị trong bao lâu?
- TTL có được tính từ thời điểm gửi như mong muốn không?
- Delivery delay có cần thiết cho lần giao đầu hay đang cố giải quyết redelivery?
- TTL có dài hơn delay cộng thời gian backlog dự kiến không?
- JmsTemplate đã bật explicit QoS nếu cần áp dụng TTL chưa?
- Delivery delay có được cấu hình trên đúng producer/template không?
- Có dùng một template chung cho nhiều delay khác nhau không?
- Provider và JMS client có hỗ trợ JMS 2.0 delivery delay không?
- Có đang dùng vendor-specific scheduler property không?
- Đồng hồ producer, broker và consumer có đồng bộ không?
- Expired message được loại bỏ hay chuyển tới expiry destination?
- Scheduler state có tồn tại qua broker restart không?
- Broker có policy override TTL hoặc delivery delay không?
- Có phân biệt expiration, DLQ và redelivery policy không?
- Integration test đã xác minh TTL, delay, combined case và broker-specific behavior chưa?

Khi thiết kế đúng TTL, delivery delay và expiry policy, ứng dụng có thể loại bỏ message lỗi thời, trì hoãn message tới thời điểm phù hợp và giữ hành vi nhất quán khi thay đổi JMS provider. Phần API chuẩn nên được ưu tiên cho khả năng portable; extension của broker chỉ nên dùng khi ứng dụng thực sự cần tính năng riêng và chấp nhận phụ thuộc provider.

## 15. Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification — Message delivery time and delay](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
- [Spring Framework 6.2 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [ActiveMQ Classic — Message Expiry](https://activemq.apache.org/components/classic/documentation/message-expiry)
- [ActiveMQ Classic — Delay and Schedule Message Delivery](https://activemq.apache.org/components/classic/documentation/delay-and-schedule-message-delivery)
- [ActiveMQ Artemis — Message Expiry](https://artemis.apache.org/components/artemis/documentation/latest/message-expiry.html)
- [ActiveMQ Artemis — Scheduled Messages](https://artemis.apache.org/components/artemis/documentation/latest/scheduled-messages)
- [IBM MQ — Delivery delay for JMS messages](https://www.ibm.com/docs/en/ibm-mq/9.3.x?topic=applications-delivery-delay-jms-messages)
- [IBM MQ — JMSMessage and JMSExpiration](https://www.ibm.com/docs/en/ibm-mq/10.0.x?topic=messaging-jmsmessage)