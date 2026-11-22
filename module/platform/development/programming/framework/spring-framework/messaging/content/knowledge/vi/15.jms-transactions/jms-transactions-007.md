# Nhận và gửi phản hồi trong cùng giao dịch JMS với Spring

Trong một luồng request-reply bằng JMS, listener nhận request, xử lý dữ liệu rồi gửi response về destination mà request chỉ định. Nếu request đã được acknowledge nhưng response chưa gửi thành công, caller có thể không bao giờ nhận được kết quả dù nghiệp vụ đã chạy. Spring JMS giải quyết vấn đề này bằng cách cho listener container thực hiện thao tác nhận và gửi response trong cùng một giao dịch JMS.

Với local JMS transaction, điều kiện cốt lõi là **nhận request và gửi response phải dùng cùng một JMS Session đang được transacted**. Khi listener hoàn tất bình thường, container commit session: request được acknowledge và response được gửi. Nếu listener hoặc thao tác gửi response thất bại, container rollback: request được redeliver và response đã gửi trong session đó cũng bị rollback.

## 1. Vì sao cần giao dịch cho cả receive và reply?

Giả sử producer gửi một request đến queue `orders` và yêu cầu phản hồi qua `JMSReplyTo=order-replies`.

Luồng không có transaction có thể gặp tình huống:

1. Listener nhận request.
2. Provider acknowledge request.
3. Listener tạo response nhưng gửi response thất bại.
4. Request đã bị acknowledge nên không được redeliver.
5. Caller chờ response nhưng không nhận được.

Nếu listener dùng một transacted session cho cả receive và reply, provider xử lý hai thao tác trong cùng transaction:

- Commit: request được xác nhận và response trở nên khả dụng.
- Rollback: request quay lại queue để xử lý lại; response chưa được commit sẽ không xuất hiện ở queue reply.

Đây là cách giữ tính nhất quán giữa việc tiêu thụ request và phát response trong phạm vi một JMS resource.

## 2. Bật local JMS transaction bằng sessionTransacted

Với `DefaultMessageListenerContainer`, bật:

```java
container.setSessionTransacted(true);
```

Mỗi lần listener được gọi sẽ chạy trong một JMS Session có transaction. Container chịu trách nhiệm commit khi listener hoàn tất thành công và rollback khi listener ném exception.

Ví dụ cấu hình:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConnectionFactory(connectionFactory);
container.setDestinationName("orders");
container.setMessageListener(orderListener);
container.setSessionTransacted(true);
container.setConcurrency("2-8");
```

Khi bật local transaction:

- Listener không cần tự gọi `session.commit()` hoặc `session.rollback()`.
- Không đóng Session do container cấp.
- Nếu xử lý thất bại, hãy để exception thoát khỏi listener để container nhận biết và rollback.
- Nếu bắt exception rồi trả về bình thường, container có thể hiểu listener đã thành công và commit request cùng response.

Mỗi listener invoker có session riêng. Khi tăng concurrency, mỗi lần xử lý vẫn có transaction độc lập trên session tương ứng.

### Luồng commit và rollback

```text
Nhận request trên transacted Session
                 |
                 v
          Xử lý nghiệp vụ
                 |
                 v
          Gửi response
                 |
           Listener kết thúc
             /       \
            /         \
       Thành công     Có exception
           |               |
           v               v
        COMMIT           ROLLBACK
           |               |
           v               v
   Ack request +       Redeliver request
   publish response    + hủy response chưa commit
```

Transaction chỉ bao phủ các thao tác tham gia cùng JMS Session. Những thao tác database hoặc HTTP độc lập không tự động nằm trong transaction này.

## 3. Dùng SessionAwareMessageListener để gửi response bằng cùng Session

`SessionAwareMessageListener` là interface riêng của Spring. Nó mở rộng khả năng của JMS `MessageListener` bằng cách truyền thêm chính `Session` đã nhận message vào callback:

```java
public interface SessionAwareMessageListener<M extends jakarta.jms.Message> {
    void onMessage(M message, jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
```

Đây là cách tường minh để gửi response trong cùng local transaction:

```java
import jakarta.jms.Destination;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.jms.listener.SessionAwareMessageListener;

public class OrderListener
        implements SessionAwareMessageListener<TextMessage> {

    @Override
    public void onMessage(TextMessage request, Session session)
            throws jakarta.jms.JMSException {

        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalStateException("Request has no JMSReplyTo");
        }

        String orderId = request.getText();
        String result = "accepted:" + orderId;

        TextMessage response = session.createTextMessage(result);
        response.setJMSCorrelationID(request.getJMSCorrelationID());

        try (MessageProducer producer = session.createProducer(replyTo)) {
            producer.send(response);
        }
    }
}
```

Container truyền Session đang dùng để nhận request. Producer được tạo từ session đó nên thao tác gửi response tham gia cùng local JMS transaction.

Có thể đóng `MessageProducer` sau khi gửi; không đóng Session hoặc Connection vì container quản lý vòng đời của chúng.

Nếu `producer.send(response)` ném exception, exception thoát khỏi callback và container rollback session. Request được provider redeliver theo chính sách của broker.

## 4. Dùng @JmsListener và @SendTo

Với endpoint annotation, Spring có thể tự gửi response từ giá trị method trả về. Cấu hình listener container factory với `sessionTransacted=true`:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");

        return factory;
    }
}
```

Bật annotation listener bằng `@EnableJms`, sau đó khai báo endpoint:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class OrderEndpoint {

    @JmsListener(destination = "orders")
    @SendTo("order-replies")
    public OrderReply processOrder(OrderRequest request) {
        // Validate and process the request.
        return new OrderReply(request.orderId(), "ACCEPTED");
    }
}
```

Spring chuyển giá trị trả về thành JMS message và gửi về destination phản hồi. Với cấu hình transacted listener container, việc nhận request, gọi method và gửi response nằm trong vòng đời xử lý của listener session.

Một số quy tắc định tuyến response:

- `JMSReplyTo` trên request chỉ định destination trả lời riêng cho request đó.
- `@SendTo` xác định destination phản hồi mặc định cho endpoint.
- Nếu cần chọn destination theo dữ liệu request, có thể trả về `JmsResponse` kèm destination.
- Method trả về `void` hoặc giá trị `null` thì không tạo response tự động.

Nếu cần tự tạo JMS header, có thể trả về Spring `Message<T>` thay cho payload thuần. Nếu cần dùng native JMS API, method `@JmsListener` cũng có thể nhận tham số `jakarta.jms.Session` và `jakarta.jms.Message`:

```java
@JmsListener(destination = "orders")
public void process(TextMessage request, Session session)
        throws JMSException {
    Destination replyTo = request.getJMSReplyTo();
    // Create and send response with this session.
}
```

Khi dùng cách này, hãy gửi response bằng Session được inject để bảo đảm nó thuộc cùng local JMS transaction.

## 5. MessageListenerAdapter cũng hỗ trợ response tự động

`MessageListenerAdapter` cho phép biến một POJO thành message-driven listener. Nếu method xử lý trả về giá trị khác `void`, adapter có thể chuyển đổi kết quả thành JMS message và gửi response.

Ví dụ method delegate:

```java
public class OrderDelegate {

    public String handleMessage(String orderId) {
        return "accepted:" + orderId;
    }
}
```

Cấu hình adapter và destination mặc định:

```java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new OrderDelegate());

adapter.setDefaultResponseDestination(orderReplyQueue);
```

Adapter gửi response đến destination trong header `JMSReplyTo` của request nếu có; nếu không, nó dùng default response destination đã cấu hình. Nếu không tìm thấy destination phù hợp, thao tác gửi response thất bại và exception có thể được truyền về listener container.

Để receive và response cùng nằm trong local transaction, hãy đặt adapter làm listener của container có `sessionTransacted=true`. Container gọi adapter trong transaction của listener session.

## 6. Correlation ID và reply destination

Request-reply cần một cách ghép response với request tương ứng, đặc biệt khi nhiều request đang chờ cùng lúc.

### JMSReplyTo

`JMSReplyTo` là header chứa destination mà caller muốn nhận response. Request có thể dùng queue reply riêng, queue dùng chung hoặc temporary queue.

Ví dụ:

```java
client.send("orders", session -> {
    TextMessage request = session.createTextMessage("order-42");
    request.setJMSReplyTo(session.createQueue("order-replies"));
    request.setJMSCorrelationID("corr-42");
    return request;
});
```

Nếu listener không tìm được reply destination và không có default destination như `@SendTo`, việc tạo response sẽ thất bại.

Temporary queue hữu ích cho request-reply ngắn hạn vì caller tạo queue để nhận response rồi đóng khi không cần nữa. Tuy nhiên, caller phải giữ connection/destination tồn tại trong thời gian chờ và bảo đảm provider cho phép listener gửi đến temporary destination đó.

### JMSCorrelationID

`JMSCorrelationID` giúp caller ghép response với request. Có hai quy ước thường dùng:

- Caller đặt correlation ID riêng trên request; listener sao chép giá trị đó vào response.
- Caller không đặt correlation ID; listener dùng `JMSMessageID` của request làm correlation ID trên response.

Ví dụ:

```java
response.setJMSCorrelationID(request.getJMSCorrelationID());
```

Không nên dựa vào thứ tự nhận response để ghép request khi có nhiều request đồng thời. Dùng correlation ID và kiểm tra nó ở phía caller.

## 7. Local JMS transaction và JTA/XA

### Local JMS transaction

`sessionTransacted=true` tạo transaction cục bộ trên JMS Session. Nó phù hợp khi cần nguyên tử giữa:

- Nhận request từ queue/topic subscription.
- Gửi một hoặc nhiều response bằng cùng session.
- Các thao tác JMS khác trên cùng session.

Local JMS transaction không tự bao gồm database, filesystem hoặc HTTP service.

Ví dụ listener cập nhật database thành công, sau đó gửi response thất bại: database có thể đã commit trong khi JMS session rollback. Request được redeliver và database operation có thể chạy lại. Hãy thiết kế idempotency hoặc duplicate detection để tránh ghi dữ liệu hai lần.

### External transaction và XA

Nếu cần nhận request, cập nhật database và gửi response trong cùng một transaction phân tán, cần transaction manager và các resource có hỗ trợ XA.

Với Spring, cấu hình `JtaTransactionManager` cho listener container và dùng JMS `ConnectionFactory` có XA được đăng ký với transaction coordinator:

```java
factory.setConnectionFactory(xaConnectionFactory);
factory.setTransactionManager(jtaTransactionManager);
```

Database cũng phải tham gia XA nếu cần cùng commit với JMS. Khi đó transaction coordinator quyết định commit hoặc rollback các resource đã enlist.

XA cung cấp tính nguyên tử xuyên resource nhưng tăng chi phí và độ phức tạp vận hành, bao gồm transaction log, recovery và cấu hình provider. Chỉ dùng khi yêu cầu nhất quán thực sự cần atomic commit giữa nhiều resource.

### JmsTransactionManager

`JmsTransactionManager` quản lý local transaction cho một JMS `ConnectionFactory`. Nó có thể ràng buộc Connection/Session vào thread để các thao tác Spring JMS phù hợp tham gia cùng transaction đó. Nó không biến một database transaction độc lập thành XA transaction.

Khi listener cần gửi response, cách dễ kiểm soát nhất là dùng Session được container truyền vào. Nếu dùng `JmsTemplate` trong listener, cần xác định rõ template có tham gia cùng transaction manager/resource đang hoạt động hay không; một Session độc lập không tự động thuộc transaction của listener.

## 8. Điều gì xảy ra khi listener hoặc gửi response thất bại?

Với local transacted session, lỗi trước khi commit dẫn đến rollback:

| Thời điểm lỗi | Kết quả |
| --- | --- |
| Validate request thất bại | Request rollback và có thể redeliver |
| Xử lý nghiệp vụ ném exception | Request rollback |
| Gửi response ném exception | Request rollback; response chưa commit bị loại khỏi transaction |
| Gửi response thành công, sau đó listener ném exception | Cả receive và reply rollback |
| Listener kết thúc bình thường | Request và response commit cùng transaction |

Để transaction rollback, lỗi phải được truyền đến container. Nếu listener bắt exception rồi bỏ qua và kết thúc bình thường, container có thể commit. Với lỗi cần rollback nhưng không muốn ném ra ngoài, cần đánh dấu transaction rollback-only qua cơ chế transaction manager phù hợp.

### Redelivery và poison message

Rollback khiến provider có thể giao lại request. JMS đặt cờ `JMSRedelivered` khi message được giao lại; nhiều provider còn cung cấp thuộc tính `JMSXDeliveryCount`.

Redelivery có thể lặp nhiều lần nếu lỗi luôn xảy ra. Hãy cấu hình:

- Số lần giao lại tối đa.
- Khoảng nghỉ hoặc backoff giữa các lần retry.
- Dead-letter queue cho message đã vượt số lần thử.
- Logging có request ID, correlation ID và delivery count.
- Idempotency để xử lý an toàn khi request được giao lại.

Không retry vô hạn với lỗi dữ liệu không thể phục hồi. Message sai schema hoặc thiếu trường bắt buộc nên được chuyển sang error/DLQ flow theo chính sách của broker.

## 9. Ví dụ Java 17+: kiểm chứng rollback cả request và response bằng Artemis

Ví dụ sau dùng embedded ActiveMQ Artemis và Spring JMS. Listener gửi response bằng chính Session mà container cấp, sau đó cố ý ném exception ở lần xử lý đầu tiên. Broker rollback cả request và response. Request được redeliver; lần xử lý thứ hai thành công và caller chỉ nhận được một response.

Tạo file `src/main/java/TransactionalJmsReplyDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.Destination;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.api.core.QueueConfiguration;
import org.apache.activemq.artemis.api.core.RoutingType;
import org.apache.activemq.artemis.core.config.impl.ConfigurationImpl;
import org.apache.activemq.artemis.core.server.embedded.EmbeddedActiveMQ;
import org.apache.activemq.artemis.core.remoting.impl.invm.InVMConnector;
import org.apache.activemq.artemis.core.remoting.impl.invm.InVMRegistry;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.SessionAwareMessageListener;

public class TransactionalJmsReplyDemo {

    public static void main(String[] args) throws Exception {
        EmbeddedActiveMQ broker = new EmbeddedActiveMQ();
        ActiveMQConnectionFactory connectionFactory = null;
        DefaultMessageListenerContainer container = null;

        try {
            ConfigurationImpl configuration = new ConfigurationImpl()
                    .setPersistenceEnabled(false)
                    .setSecurityEnabled(false)
                    .setJMXManagementEnabled(false)
                    .addAcceptorConfiguration("invm", "vm://0");

            broker.setConfiguration(configuration).start();

            broker.getActiveMQServer().createQueue(
                    QueueConfiguration.of("requests")
                            .setAddress("requests")
                            .setRoutingType(RoutingType.ANYCAST)
                            .setDurable(false));

            broker.getActiveMQServer().createQueue(
                    QueueConfiguration.of("replies")
                            .setAddress("replies")
                            .setRoutingType(RoutingType.ANYCAST)
                            .setDurable(false));

            connectionFactory = new ActiveMQConnectionFactory("vm://0");

            JmsTemplate client = new JmsTemplate(connectionFactory);
            client.setReceiveTimeout(5_000);

            AtomicInteger attempts = new AtomicInteger();

            SessionAwareMessageListener<TextMessage> listener =
                    (request, session) -> {
                int attempt = attempts.incrementAndGet();

                System.out.println("listener attempt=" + attempt
                        + ", redelivered=" + request.getJMSRedelivered());

                Destination replyTo = request.getJMSReplyTo();
                if (replyTo == null) {
                    throw new IllegalStateException("Request has no JMSReplyTo");
                }

                TextMessage response = session.createTextMessage(
                        "processed:" + request.getText());

                response.setJMSCorrelationID(
                        request.getJMSCorrelationID());

                try (MessageProducer producer =
                             session.createProducer(replyTo)) {
                    producer.send(response);
                }

                // First attempt sends a reply, then forces the whole session to roll back.
                if (attempt == 1) {
                    throw new IllegalStateException(
                            "Simulated failure after reply send");
                }
            };

            container = new DefaultMessageListenerContainer();
            container.setConnectionFactory(connectionFactory);
            container.setDestinationName("requests");
            container.setMessageListener(listener);
            container.setSessionTransacted(true);
            container.setCacheLevel(
                    DefaultMessageListenerContainer.CACHE_CONSUMER);
            container.setRecoveryInterval(200);
            container.afterPropertiesSet();
            container.start();

            client.send("requests", session -> {
                TextMessage request = session.createTextMessage("order-42");
                request.setJMSReplyTo(session.createQueue("replies"));
                request.setJMSCorrelationID("corr-42");
                return request;
            });

            Message reply = client.receive("replies");
            if (!(reply instanceof TextMessage textReply)) {
                throw new IllegalStateException("No text reply received");
            }

            client.setReceiveTimeout(300);
            Message duplicateReply = client.receive("replies");

            System.out.println("reply payload=" + textReply.getText());
            System.out.println("reply correlationId="
                    + textReply.getJMSCorrelationID());
            System.out.println("listener attempts=" + attempts.get());
            System.out.println("duplicate reply absent="
                    + (duplicateReply == null));

            if (attempts.get() != 2 || duplicateReply != null) {
                throw new IllegalStateException(
                        "Unexpected transactional reply behavior");
            }
        }
        finally {
            if (container != null) {
                container.stop();
                container.destroy();
            }

            if (connectionFactory != null) {
                connectionFactory.close();
            }

            broker.stop();

            // Clean up the embedded Artemis in-VM transport threads.
            InVMRegistry.instance.clear();
            InVMConnector.resetThreadPool();
        }
    }
}
```

Tạo `pom.xml` ở thư mục gốc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>transactional-jms-reply-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>7.0.10</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.10</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <version>2.37.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.37.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>TransactionalJmsReplyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Kết quả stdout:

```text
listener attempt=1, redelivered=false
listener attempt=2, redelivered=true
reply payload=processed:order-42
reply correlationId=corr-42
listener attempts=2
duplicate reply absent=true
```

Lần đầu listener đã gửi response nhưng sau đó ném exception. Vì response được gửi bằng cùng transacted Session, broker rollback cả response và thao tác nhận request. Broker redeliver request; lần thứ hai listener hoàn tất bình thường, nên request được acknowledge và chỉ một response được commit.

Ví dụ dùng Artemis embedded với persistence tắt để kiểm thử transaction behavior. Nó không cần broker bên ngoài; khi triển khai production, thay embedded broker bằng ConnectionFactory của provider đang dùng.

## 10. Những giới hạn cần nhớ

### Request và reply không phải một transaction xuyên suốt caller

Transaction ở listener bảo vệ receive request và send response phía server. Việc caller gửi request và việc caller nhận response thường diễn ra ở các session/transaction khác nhau. Nếu caller gửi request thành công nhưng timeout khi chờ reply, server vẫn có thể đã xử lý và commit response.

Caller cần timeout, correlation ID và chính sách retry phù hợp. Không giả định timeout có nghĩa request chưa được xử lý.

### JMS transaction không tự bao gồm database

Nếu listener ghi database rồi gửi response, local JMS transaction chỉ rollback thao tác JMS. Database có thể đã commit. Dùng idempotency key, inbox/deduplication hoặc transactional outbox tùy kiến trúc.

Nếu bắt buộc database update, request acknowledgement và reply send phải commit nguyên tử, cần JTA/XA với tất cả resource được cấu hình và enlist đúng cách.

### AUTO_ACKNOWLEDGE không thay thế transacted session

Acknowledgement mode mặc định không bảo đảm rollback receive cùng send. Với yêu cầu tin cậy, bật `sessionTransacted=true` hoặc dùng transaction manager phù hợp.

`CLIENT_ACKNOWLEDGE` cũng không biến thao tác gửi response thành một phần của transaction nhận. Muốn atomic receive/reply, dùng cùng transacted Session.

### Không để response thất lạc vì thiếu destination

Nếu request không có `JMSReplyTo`, listener phải có default response destination như `@SendTo` hoặc `MessageListenerAdapter.setDefaultResponseDestination`. Nếu không có destination, Spring không thể gửi response và listener sẽ thất bại.

### Không dùng Session đồng thời trên nhiều thread

JMS Session không thread-safe. Tạo response bằng Session được truyền vào callback và gửi trong cùng thread xử lý. Không lưu Session vào field hoặc chuyển nó sang executor khác.

## 11. Lỗi thường gặp

1. **Bật listener nhưng quên `sessionTransacted=true`.** Listener có thể nhận request và gửi response mà không có rollback nguyên tử.
2. **Gửi response bằng một Session độc lập.** Response có thể commit dù request bị rollback, tạo response trùng khi request redeliver.
3. **Dùng `JmsTemplate` mà nghĩ nó tự dùng Session của listener.** Một template có thể lấy Session khác; hãy dùng Session được inject hoặc cấu hình transaction manager để chia sẻ resource đúng cách.
4. **Bắt exception rồi bỏ qua.** Container thấy listener kết thúc bình thường và có thể commit request.
5. **Dùng `CLIENT_ACKNOWLEDGE` thay cho transacted session.** Acknowledge không nhóm thao tác send response vào cùng transaction.
6. **Không đặt `JMSReplyTo` hoặc default destination.** Adapter không có nơi gửi response.
7. **Không đặt correlation ID.** Caller khó ghép response khi có nhiều request đồng thời.
8. **Không xử lý redelivery.** Một request có thể được thực thi nhiều lần sau rollback hoặc lỗi kết nối.
9. **Retry vô hạn message lỗi dữ liệu.** Poison message có thể lặp liên tục; cần giới hạn retry và DLQ.
10. **Cho rằng local JMS transaction bao gồm database.** Nó chỉ bao gồm thao tác JMS trên resource/session tương ứng.
11. **Dùng XA mà ConnectionFactory không hỗ trợ XA.** JTA không thể enlist một JMS resource không có XA capability.
12. **Để listener chạy lâu trong request-reply.** Caller giữ tài nguyên trong thời gian chờ; công việc dài nên dùng command + job ID/status event.

## 12. Checklist triển khai

- Chọn `DefaultMessageListenerContainer` hoặc listener factory hỗ trợ transaction.
- Bật `sessionTransacted=true` nếu receive và reply phải atomic trên một JMS resource.
- Gửi reply qua cùng Session được container truyền vào, hoặc dùng cơ chế reply adapter của Spring.
- Chọn destination từ `JMSReplyTo`, `@SendTo` hoặc default response destination.
- Đặt correlation ID và kiểm tra nó ở caller.
- Để exception thoát khỏi listener khi cần rollback.
- Cấu hình redelivery, retry limit và dead-letter queue.
- Làm listener idempotent để xử lý request redeliver an toàn.
- Dùng JTA/XA nếu cần atomic commit giữa JMS và database/resource khác.
- Kiểm thử tình huống lỗi sau khi gửi response nhưng trước khi listener hoàn tất.
- Theo dõi redelivery count, rollback, reply timeout và message vào DLQ.

## 13. Tài liệu tham khảo

- [Spring Framework – Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework – SessionAwareMessageListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/SessionAwareMessageListener.html)
- [Spring Framework – DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework – Annotation-driven Listener Endpoints and @SendTo](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework – MessageListenerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/adapter/MessageListenerAdapter.html)
- [Spring Framework – JmsTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf)
