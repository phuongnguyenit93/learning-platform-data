# SessionCallback, ProducerCallback và thao tác JMS nâng cao

Spring JMS cung cấp **JmsTemplate** để ứng dụng gửi và nhận message mà không phải tự lặp lại việc tạo, giải phóng Connection, Session, MessageProducer và MessageConsumer. Với các thao tác thông thường, những phương thức như send, convertAndSend, receive và sendAndReceive thường đã đủ.

Khi cần kiểm soát sâu hơn API Jakarta Messaging, JmsTemplate cung cấp hai callback quan trọng:

- **SessionCallback<T>** cho phép thực hiện một hoặc nhiều thao tác trên một JMS Session do template cung cấp.
- **ProducerCallback<T>** cho phép làm việc đồng thời với một JMS Session và một MessageProducer do template tạo.

Hai callback phù hợp khi một thao tác nghiệp vụ cần nhiều bước JMS trong cùng một lần gọi, cần thiết lập Quality of Service (QoS) riêng cho từng message, cần dùng API Session đặc thù hoặc cần xây dựng request/reply tùy chỉnh.

## 1. JmsTemplate quản lý tài nguyên như thế nào?

Luồng gửi JMS cơ bản thường cần các đối tượng:

~~~text
ConnectionFactory
      |
      v
Connection
      |
      v
Session
      |
      v
MessageProducer
      |
      v
Destination
~~~

Nếu tự gọi Jakarta Messaging API ở mọi nơi, ứng dụng phải quản lý việc tạo và đóng các đối tượng trung gian, chuyển JMSException, cấu hình transaction và bảo đảm không dùng lại tài nguyên sai vòng đời.

JmsTemplate gom phần hạ tầng này vào một template dùng chung. Ứng dụng truyền một callback để thực hiện phần nghiệp vụ cần thiết. Khi callback hoàn tất hoặc ném exception, template giải phóng những tài nguyên do chính template tạo và sở hữu.

**JmsTemplate thread-safe sau khi đã cấu hình.** Có thể dùng một instance dùng chung trong nhiều service. Tuy nhiên, Session, MessageProducer và MessageConsumer là các tài nguyên gắn với một lần thực thi; không lưu chúng vào field dùng chung hoặc chia sẻ chúng giữa các thread.

### So sánh các callback

| Callback | Đối tượng được cung cấp | Dùng khi |
|---|---|---|
| **MessageCreator** | Session | Chỉ cần tạo một message để gửi qua các phương thức send thông thường. |
| **SessionCallback<T>** | Session | Cần nhiều thao tác JMS trên cùng một Session, tạo consumer, temporary destination hoặc dùng API Session trực tiếp. |
| **ProducerCallback<T>** | Session và MessageProducer | Cần gửi nhiều message qua cùng một producer hoặc điều chỉnh QoS ở từng lần send. |
| **BrowserCallback<T>** | Session và QueueBrowser | Cần duyệt message trong queue mà không lấy message ra khỏi queue. |
| **MessagePostProcessor** | Message sau khi converter tạo | Cần bổ sung property hoặc JMS header sau convertAndSend. |

SessionCallback và ProducerCallback đều trả về kiểu T do ứng dụng chọn. Có thể trả về số message đã gửi, kết quả truy vấn, message nhận được hoặc null nếu không cần kết quả.

## 2. SessionCallback<T>: làm việc trực tiếp với Session

Interface **org.springframework.jms.core.SessionCallback<T>** có một phương thức:

~~~java
T doInJms(Session session) throws JMSException;
~~~

JmsTemplate gọi phương thức này với Session đã được chuẩn bị theo cấu hình ConnectionFactory và transaction hiện hành. Sau khi callback kết thúc, template xử lý vòng đời Session và Connection mà nó quản lý.

Ví dụ gọi callback:

~~~java
Integer result = jmsTemplate.execute(session -> {
    TextMessage message = session.createTextMessage("Order created");
    message.setStringProperty("eventType", "OrderCreated");
    return message.getText().length();
});
~~~

Đoạn mã minh họa việc dùng Session để tạo message và trả kết quả. Nếu chỉ cần gửi một message, MessageCreator hoặc jmsTemplate.send(...) thường ngắn gọn hơn. SessionCallback có giá trị khi cần phối hợp nhiều thao tác JMS trong cùng một callback.

### Các thao tác thường cần SessionCallback

- Tạo Message với kiểu JMS cụ thể như TextMessage, BytesMessage hoặc MapMessage.
- Tạo MessageProducer hoặc MessageConsumer cho nhiều destination.
- Tạo TemporaryQueue hoặc TemporaryTopic để thực hiện một giao thức request/reply riêng.
- Tạo consumer có selector hoặc cấu hình noLocal.
- Truy cập API Session mà các phương thức tiện ích cấp cao không bộc lộ.
- Kết hợp nhiều thao tác trên cùng Session khi cần một ranh giới transaction phù hợp.

### Ví dụ: request/reply với temporary queue

JmsTemplate có sẵn sendAndReceive(...) để gửi request và chờ reply trên temporary queue do template tạo. Chỉ nên tự viết bằng SessionCallback khi cần kiểm soát giao thức chi tiết hơn, chẳng hạn tự quản lý temporary destination, selector hoặc nhiều bước nhận/gửi.

Ví dụ dưới đây giả định một service phía nhận đọc JMSReplyTo, xử lý request và gửi một TextMessage trả lời về destination đó. Callback tạo temporary queue, đăng ký consumer trước khi gửi request, chờ tối đa ba giây và dọn tài nguyên do chính callback tạo.

~~~java
public String requestReply(Destination requestDestination, String body) {
    return jmsTemplate.execute(session -> {
        TemporaryQueue replyQueue = session.createTemporaryQueue();
        MessageProducer producer = null;
        MessageConsumer consumer = null;

        try {
            producer = session.createProducer(requestDestination);
            consumer = session.createConsumer(replyQueue);

            String correlationId = UUID.randomUUID().toString();

            TextMessage request = session.createTextMessage(body);
            request.setJMSReplyTo(replyQueue);
            request.setJMSCorrelationID(correlationId);

            producer.send(request);

            Message reply = consumer.receive(3_000L);
            if (reply == null) {
                return null;
            }

            if (!(reply instanceof TextMessage textReply)) {
                throw new JMSException("Expected a TextMessage reply");
            }

            if (!correlationId.equals(reply.getJMSCorrelationID())) {
                throw new JMSException("Reply correlation ID does not match");
            }

            return textReply.getText();
        }
        finally {
            try {
                if (consumer != null) {
                    consumer.close();
                }
            }
            finally {
                try {
                    if (producer != null) {
                        producer.close();
                    }
                }
                finally {
                    replyQueue.delete();
                }
            }
        }
    }, true);
}
~~~

Tham số true yêu cầu JmsTemplate khởi động Connection trước khi callback thực hiện thao tác nhận message. Điều này quan trọng vì consumer cần nhận được message từ provider. Callback tự đóng producer, consumer và temporary queue do nó tạo; template quản lý Session và Connection của nó.

Request/reply chỉ hoàn tất nếu service nhận request thực sự gửi reply đến JMSReplyTo và giữ lại JMSCorrelationID. Nếu hết ba giây mà chưa có reply, phương thức trả về null. Trong hệ thống thực tế, cần xử lý timeout, reply đến muộn và lỗi từ service phía nhận.

## 3. ProducerCallback<T>: làm việc với Session và MessageProducer

Interface **org.springframework.jms.core.ProducerCallback<T>** có phương thức:

~~~java
T doInJms(Session session, MessageProducer producer)
        throws JMSException;
~~~

ProducerCallback phù hợp khi cần gửi nhiều message trong một lần gọi hoặc cần dùng các overload send của JMS để chỉ định QoS cho từng message.

JmsTemplate có các overload:

~~~java
jmsTemplate.execute(destination, producerCallback);
jmsTemplate.execute(destinationName, producerCallback);
jmsTemplate.execute(producerCallback); // cần default destination
~~~

Khi truyền destination, template tạo producer gắn với destination đó, gọi callback rồi đóng producer do template tạo. Không tự đóng producer được truyền vào callback.

### Ví dụ: gửi một batch với QoS riêng

~~~java
public int sendBatch(Destination destination, List<String> payloads) {
    return jmsTemplate.execute(destination, (session, producer) -> {
        for (int i = 0; i < payloads.size(); i++) {
            TextMessage message = session.createTextMessage(payloads.get(i));
            message.setIntProperty("batchIndex", i);
            message.setStringProperty("eventType", "OrderEvent");

            producer.send(
                    message,
                    DeliveryMode.PERSISTENT,
                    4,
                    60_000L
            );
        }

        return payloads.size();
    });
}
~~~

Mỗi message được gửi với:

- **DeliveryMode.PERSISTENT:** yêu cầu provider lưu message theo delivery mode persistent.
- **priority = 4:** mức ưu tiên JMS trong khoảng 0 đến 9; số lớn hơn biểu thị mức ưu tiên cao hơn.
- **timeToLive = 60_000L:** thời gian sống 60 giây tính bằng milliseconds.

Giá trị trả về là số message callback đã gửi. Nếu một lần send ném JMSException, callback dừng và JmsTemplate chuyển lỗi thành hệ thống exception không checked thuộc Spring JMS. Việc các message trước đó có được giữ lại hay rollback phụ thuộc session transaction và provider.

### Khi nào chọn ProducerCallback thay vì send thông thường?

Dùng send(...) hoặc convertAndSend(...) khi chỉ gửi một message với cấu hình chung. Chọn ProducerCallback khi:

- Một lần gọi cần gửi nhiều message đến cùng destination.
- Mỗi message cần delivery mode, priority hoặc time-to-live riêng.
- Cần dùng API MessageProducer trực tiếp.
- Cần tạo và gửi nhiều kiểu JMS Message từ cùng Session.
- Muốn giảm số lần tạo producer cho một batch gửi.

ProducerCallback chỉ cung cấp một producer. Nếu cần gửi tới nhiều destination trong cùng Session, cân nhắc SessionCallback và tự tạo các producer cần thiết, sau đó đóng chúng trong callback.

## 4. QoS: delivery mode, priority và time-to-live

JMS định nghĩa các tham số QoS quan trọng cho thao tác send:

| Thuộc tính | Ý nghĩa | Giá trị thường gặp |
|---|---|---|
| Delivery mode | Yêu cầu persistent hoặc non-persistent delivery. | **DeliveryMode.PERSISTENT**, **DeliveryMode.NON_PERSISTENT**. |
| Priority | Mức ưu tiên của message. | 0 đến 9; mặc định thường là 4. |
| Time-to-live | Thời gian message còn hiệu lực trước khi hết hạn. | Milliseconds; 0 nghĩa là không đặt thời hạn hết hạn. |

### Cấu hình QoS chung trên JmsTemplate

Có thể cấu hình QoS mặc định cho các thao tác gửi của template:

~~~java
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setPriority(4);
jmsTemplate.setTimeToLive(60_000L);
jmsTemplate.setExplicitQosEnabled(true);
~~~

Phải bật explicitQosEnabled để JmsTemplate áp dụng các giá trị delivery mode, priority và time-to-live do template cấu hình. Một số provider có thể thiết lập default QoS riêng ở ConnectionFactory; bật cờ này giúp template truyền rõ các giá trị đã cấu hình.

Nếu dùng ProducerCallback, có thể truyền QoS riêng ngay trong producer.send(message, deliveryMode, priority, timeToLive) mà không phải thay đổi cấu hình chung của template.

### Delivery delay

JMS 2.0 bổ sung delivery delay cho message producer. JmsTemplate ở các phiên bản hỗ trợ có thể cấu hình delivery delay chung bằng setDeliveryDelay(...); nếu cần delay riêng cho từng producer, có thể dùng API tương ứng của MessageProducer.

Delivery delay không phải time-to-live:

- Delivery delay: provider chưa giao message cho consumer trước khi hết khoảng trì hoãn.
- Time-to-live: message hết hiệu lực sau một khoảng thời gian kể từ lúc gửi.

Cần kiểm tra provider có hỗ trợ đầy đủ các tính năng QoS hay không. Broker có thể áp dụng giới hạn hoặc chính sách riêng.

## 5. Session transaction và ranh giới commit/rollback

JmsTemplate mặc định tạo Session không transacted và dùng AUTO_ACKNOWLEDGE nếu không có transaction đang hoạt động. Có thể cấu hình sessionTransacted hoặc dùng transaction manager của Spring để thay đổi hành vi.

Cần phân biệt ba trường hợp:

1. **Session không transacted:** không có ranh giới commit/rollback JMS do Session quản lý.
2. **Session transacted cục bộ:** ứng dụng hoặc thành phần quản lý Session phải quyết định commit/rollback.
3. **Session được transaction manager quản lý:** Spring transaction infrastructure điều phối commit/rollback; code callback không tự commit Session đang được quản lý.

### Callback cấp thấp không tự commit thay ứng dụng

execute(SessionCallback) và execute(ProducerCallback) là API cấp thấp. Callback được gọi để thực hiện thao tác trên Session/Producer; không nên giả định rằng chỉ cần callback trả về bình thường thì mọi thay đổi trong một Session transacted đều tự động được commit.

Nếu callback đang dùng một Session transacted cục bộ do ứng dụng quản lý, phải xác định rõ nơi gọi commit() hoặc rollback(). Nếu Session tham gia Spring-managed transaction hoặc JTA transaction, để transaction manager điều phối; không gọi commit/rollback thủ công trên Session đó.

Ví dụ cấu hình JmsTemplate cho local transacted Session:

~~~java
@Bean
JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setSessionTransacted(true);
    return template;
}
~~~

Với giao dịch cần phối hợp nhiều thao tác JMS trong một transaction Spring, có thể dùng JmsTransactionManager cho một ConnectionFactory:

~~~java
@Bean
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory
) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Sau đó một phương thức nghiệp vụ có thể chạy trong transaction do Spring quản lý:

~~~java
@Transactional(transactionManager = "jmsTransactionManager")
public void publishOrderEvents() {
    // Các thao tác qua JmsTemplate tham gia transaction JMS hiện hành.
}
~~~

JmsTransactionManager quản lý transaction JMS cho một ConnectionFactory. Nếu cần transaction phân tán phối hợp JMS với database hoặc nhiều resource khác, cần hạ tầng JTA/XA tương thích; một local JMS transaction không tự làm cho thao tác database trở thành một phần của cùng transaction.

### Lưu ý khi dùng SessionCallback

Không gọi session.commit() hoặc session.rollback() tùy tiện trong callback. Trước tiên phải biết Session là local hay đang được transaction manager quản lý. Gọi commit thủ công trên Session được quản lý có thể phá vỡ ranh giới transaction của Spring.

## 6. Nhận message đồng bộ, selector và timeout

JmsTemplate hỗ trợ nhận message đồng bộ qua receive(...), receiveSelected(...) và các biến thể receiveAndConvert(...).

Ví dụ:

~~~java
jmsTemplate.setReceiveTimeout(2_000L);

Message message = jmsTemplate.receiveSelected(
        queue,
        "eventType = 'OrderCreated' AND schemaVersion >= 2"
);

if (message == null) {
    // Không có message phù hợp trong thời gian chờ.
}
else {
    // Xử lý message đã nhận.
}
~~~

Message selector là biểu thức JMS dựa trên headers và properties. Nó không parse tùy ý các field trong JSON body. Nếu cần lọc theo eventType hoặc schemaVersion, producer phải đặt những giá trị này thành JMS properties.

Synchronous receive chặn thread gọi cho đến khi có message hoặc hết timeout. Không nên để timeout vô hạn trong request xử lý HTTP hoặc thread pool có giới hạn nếu không có cơ chế kiểm soát tải.

### Duyệt queue bằng QueueBrowser

Nếu cần quan sát message đang nằm trong queue mà không tiêu thụ chúng, dùng browse(...) với BrowserCallback:

~~~java
public List<String> browseMessageIds(Queue queue) {
    return jmsTemplate.browse(queue, (session, browser) -> {
        List<String> ids = new ArrayList<>();
        Enumeration<?> messages = browser.getEnumeration();

        while (messages.hasMoreElements()) {
            Message message = (Message) messages.nextElement();
            ids.add(message.getJMSMessageID());
        }

        return ids;
    });
}
~~~

QueueBrowser chỉ duyệt nội dung queue; nó không remove message như một consumer nhận message. Enumeration và kết quả browse phụ thuộc trạng thái queue tại thời điểm provider thực hiện thao tác. Không dùng browse làm cơ chế khóa message hoặc thay thế consumer.

## 7. Request/reply có sẵn trong JmsTemplate

Khi chỉ cần gửi một request và nhận một reply, thường nên dùng sendAndReceive(...) thay vì tự tạo temporary queue bằng SessionCallback.

Ví dụ:

~~~java
Message reply = jmsTemplate.sendAndReceive(
        requestQueue,
        session -> {
            TextMessage request = session.createTextMessage(
                    "{\"orderId\":\"ORD-1001\"}"
            );
            request.setJMSCorrelationID("lookup-1001");
            return request;
        }
);
~~~

JmsTemplate tạo temporary queue, đặt destination đó vào JMSReplyTo, gửi request và chờ reply theo receive timeout đã cấu hình. Nếu không nhận được reply trong thời gian chờ, kết quả có thể là null.

Dùng SessionCallback khi cần điều khiển thêm các bước như tạo consumer riêng, dùng selector, quản lý temporary destination hoặc thực hiện nhiều thao tác trên cùng Session.

## 8. Vòng đời tài nguyên trong callback

Quy tắc đóng tài nguyên phụ thuộc vào đối tượng được ai tạo:

| Đối tượng | Ai tạo | Ai đóng |
|---|---|---|
| Connection do JmsTemplate mở | JmsTemplate | JmsTemplate |
| Session do JmsTemplate cung cấp | JmsTemplate | JmsTemplate |
| Producer truyền vào ProducerCallback | JmsTemplate | JmsTemplate |
| Producer do code tự tạo trong SessionCallback | Ứng dụng | Ứng dụng |
| Consumer do code tự tạo trong SessionCallback | Ứng dụng | Ứng dụng |
| TemporaryQueue/TemporaryTopic do code tạo | Ứng dụng | Ứng dụng gọi delete khi hoàn tất |

Không đóng Session hoặc Producer được JmsTemplate truyền vào callback. Nếu tự tạo producer/consumer từ SessionCallback, hãy đóng chúng trong finally, kể cả khi thao tác gửi hoặc nhận thất bại.

Không lưu Session, producer hoặc consumer vào field để tái sử dụng giữa các lần gọi. Nếu cần tối ưu tạo tài nguyên, cân nhắc CachingConnectionFactory hoặc connection pool phù hợp với provider.

## 9. Exception và xử lý lỗi

Các phương thức Jakarta JMS thường ném JMSException checked. Callback cho phép ném exception này; JmsTemplate chuyển lỗi sang hệ thống JmsException không checked của Spring.

Một số tình huống thường gặp:

- Destination không tồn tại hoặc không thể resolve.
- Producer không gửi được vì broker mất kết nối.
- Message không hợp lệ với provider.
- Consumer nhận timeout và trả về null.
- Transaction commit hoặc rollback thất bại.
- Provider từ chối QoS hoặc tính năng không được hỗ trợ.

Khi retry, cần phân biệt lỗi tạm thời với lỗi không thể phục hồi. Chỉ retry lỗi phù hợp, giới hạn số lần và dùng backoff. Với thao tác gửi có thể bị gửi trùng sau khi kết nối đứt ở thời điểm không rõ broker đã nhận hay chưa, consumer nên có cơ chế idempotency dựa trên business event ID hoặc khóa nghiệp vụ ổn định.

Không bắt rồi bỏ qua JMSException. Nếu callback không thể hoàn thành thao tác, hãy để exception đi qua JmsTemplate hoặc chuyển thành lỗi nghiệp vụ có nguyên nhân rõ ràng.

## 10. Ví dụ project Java 17 với Spring JMS 6.2

Các đoạn code ở trên là các phương thức tích hợp dùng trong service đã được cấu hình JmsTemplate và Destination. Chúng không tự khởi động broker. Để biên dịch các ví dụ, project cần Spring JMS và Jakarta Messaging API.

### Maven dependencies

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-jms</artifactId>
        <version>6.2.19</version>
    </dependency>

    <dependency>
        <groupId>jakarta.jms</groupId>
        <artifactId>jakarta.jms-api</artifactId>
        <version>3.1.0</version>
    </dependency>
</dependencies>
~~~

### Service minh họa

Đặt các phương thức sendBatch, requestReply và browseMessageIds trong một class service có constructor nhận JmsTemplate. Cần cấu hình ConnectionFactory và các Destination phù hợp với broker. Ví dụ này dùng Jakarta namespace jakarta.jms, phù hợp với Spring Framework 6.x.

Một service tối thiểu có thể khai báo:

~~~java
package com.example.messaging;

import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.UUID;

import jakarta.jms.DeliveryMode;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

import org.springframework.jms.core.JmsTemplate;

public class JmsCallbackOperations {

    private final JmsTemplate jmsTemplate;

    public JmsCallbackOperations(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public int sendBatch(Destination destination, List<String> payloads) {
        return jmsTemplate.execute(destination, (session, producer) -> {
            for (int i = 0; i < payloads.size(); i++) {
                TextMessage message = session.createTextMessage(payloads.get(i));
                message.setIntProperty("batchIndex", i);
                message.setStringProperty("eventType", "OrderEvent");

                producer.send(
                        message,
                        DeliveryMode.PERSISTENT,
                        4,
                        60_000L
                );
            }
            return payloads.size();
        });
    }

    public String requestReply(Destination requestDestination, String body) {
        return jmsTemplate.execute(session -> {
            TemporaryQueue replyQueue = session.createTemporaryQueue();
            MessageProducer producer = null;
            MessageConsumer consumer = null;

            try {
                producer = session.createProducer(requestDestination);
                consumer = session.createConsumer(replyQueue);

                String correlationId = UUID.randomUUID().toString();
                TextMessage request = session.createTextMessage(body);
                request.setJMSReplyTo(replyQueue);
                request.setJMSCorrelationID(correlationId);
                producer.send(request);

                Message reply = consumer.receive(3_000L);
                if (reply == null) {
                    return null;
                }
                if (!(reply instanceof TextMessage textReply)) {
                    throw new JMSException("Expected a TextMessage reply");
                }
                if (!correlationId.equals(reply.getJMSCorrelationID())) {
                    throw new JMSException("Reply correlation ID does not match");
                }
                return textReply.getText();
            }
            finally {
                try {
                    if (consumer != null) {
                        consumer.close();
                    }
                }
                finally {
                    try {
                        if (producer != null) {
                            producer.close();
                        }
                    }
                    finally {
                        replyQueue.delete();
                    }
                }
            }
        }, true);
    }

    public List<String> browseMessageIds(Queue queue) {
        return jmsTemplate.browse(queue, (session, browser) -> {
            List<String> ids = new ArrayList<>();
            Enumeration<?> messages = browser.getEnumeration();

            while (messages.hasMoreElements()) {
                Message message = (Message) messages.nextElement();
                ids.add(message.getJMSMessageID());
            }

            return ids;
        });
    }
}
~~~

Class trên biên dịch với các dependencies đã nêu, nhưng để chạy thực tế cần một JMS provider, ConnectionFactory, queue/topic đã được cấu hình và service nhận request/reply tương ứng. Không có stdout cố định vì kết quả phụ thuộc message trong broker và phản hồi từ consumer.

## 11. Những nhầm lẫn thường gặp

1. **“SessionCallback tự động commit khi callback trả về.”** Không nên giả định điều đó. Callback là API truy cập Session cấp thấp; phải xác định transaction được quản lý bởi ai.
2. **“ProducerCallback cần tự đóng producer được truyền vào.”** Không đúng. Producer do JmsTemplate tạo và quản lý trong callback đó.
3. **“SessionCallback có thể chia sẻ Session giữa nhiều thread.”** Không đúng. Session và các resource gắn với nó không phải đối tượng dùng chung tùy ý giữa các thread.
4. **“ProducerCallback chỉ gửi được một message.”** Không đúng. Có thể gửi nhiều message qua cùng producer trong một callback.
5. **“QoS của JmsTemplate luôn tự áp dụng.”** Các giá trị delivery mode, priority và TTL cấu hình trên template cần explicitQosEnabled=true; ProducerCallback có thể truyền QoS riêng cho từng send.
6. **“Synchronous receive không có timeout.”** JmsTemplate có receiveTimeout; cần chọn giá trị phù hợp vì receive chặn thread gọi.
7. **“QueueBrowser lấy message ra khỏi queue.”** Không đúng. Browser chỉ duyệt message; consumer mới nhận và tiêu thụ message.
8. **“TemporaryQueue tồn tại vô thời hạn.”** Temporary destination gắn với vòng đời connection tạo nó; cần quản lý và xóa khi không còn sử dụng.
9. **“Local JMS transaction bao gồm cả database.”** Không đúng. Cần transaction coordinator phù hợp và XA nếu muốn phối hợp nhiều resource trong một distributed transaction.
10. **“Gửi thành công chứng minh consumer đã xử lý xong.”** Không đúng. Kết quả send chỉ phản ánh thao tác gửi theo semantics của provider; kết quả nghiệp vụ cần reply, acknowledgment hoặc event riêng.

## 12. Ghi nhớ

- **SessionCallback<T>** cung cấp Session để thực hiện nhiều thao tác JMS trong một callback.
- **ProducerCallback<T>** cung cấp Session và MessageProducer để gửi nhiều message hoặc tùy chỉnh QoS.
- JmsTemplate quản lý resource mà nó tạo; ứng dụng phải đóng producer/consumer/temporary destination do chính callback tạo.
- send(message, deliveryMode, priority, timeToLive) cho phép đặt QoS riêng cho từng message.
- execute(SessionCallback, true) khởi động Connection khi callback cần nhận message.
- receiveSelected dùng selector trên headers/properties; browse quan sát queue mà không tiêu thụ message.
- Callback cấp thấp đòi hỏi hiểu rõ transaction và vòng đời Session; không commit thủ công trên Session đang do Spring/JTA quản lý.
- Dùng sendAndReceive cho request/reply thông thường; dùng SessionCallback khi cần điều khiển JMS API chi tiết.
- Giữ idempotency, timeout, retry và xử lý lỗi rõ ràng khi làm việc với broker.

Khi chọn callback, hãy bắt đầu từ đối tượng cần kiểm soát: chỉ tạo message thì dùng MessageCreator; cần Session thì dùng SessionCallback; cần Session cùng producer thì dùng ProducerCallback. Ranh giới tài nguyên và transaction phải được xác định trước khi thêm các thao tác JMS nâng cao.
