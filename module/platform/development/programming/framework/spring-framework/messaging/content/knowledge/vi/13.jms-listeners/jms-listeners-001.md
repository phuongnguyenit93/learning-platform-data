# Nhận bất đồng bộ bằng MessageListener và Message-Driven POJO

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách JMS chuyển thông điệp tới một listener mà producer không phải gọi trực tiếp consumer.
- Phân biệt Jakarta JMS MessageListener với Message-Driven POJO (MDP) trong Spring.
- Cấu hình listener container để quản lý Connection, Session, Consumer, thread và vòng đời nhận thông điệp.
- Chọn giữa listener triển khai trực tiếp, MessageListenerAdapter và annotation @JmsListener.
- Hiểu cách chuyển đổi JMS Message thành payload Java và cách gửi reply.
- Cấu hình concurrency, selector, Queue/Topic và durable subscription.
- Chọn acknowledgement hoặc transaction phù hợp, xử lý lỗi, redelivery và duplicate.
- Viết consumer thread-safe và đóng container đúng cách.

## 1. Nhận JMS bất đồng bộ là gì?

Trong mô hình JMS, producer gửi Message tới một Queue hoặc Topic. Consumer có thể chủ động gọi receive để chờ Message, hoặc đăng ký một listener để được gọi khi provider chuyển Message tới.

**Nhận bất đồng bộ** nghĩa là ứng dụng đăng ký logic xử lý trước; khi Message đến, listener container hoặc JMS provider gọi callback trên thread nhận thông điệp. Producer không cần chờ consumer xử lý xong trong lời gọi gửi.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as JMS Broker
    participant C as Spring Listener Container
    participant L as MessageListener / POJO

    P->>B: Gửi Message
    Note over P: Producer tiếp tục công việc
    B-->>C: Message đến consumer
    C->>L: Gọi listener trên thread nhận
    L->>L: Xử lý nghiệp vụ
    L-->>C: Kết thúc callback
    C->>B: Commit hoặc acknowledge theo cấu hình
~~~

JMS cung cấp callback chuẩn jakarta.jms.MessageListener với phương thức onMessage(Message). Spring bổ sung hạ tầng để biến một object Java thông thường thành nơi nhận thông điệp, đồng thời quản lý kết nối, session, consumer, thread, transaction và recovery.

Một listener không tự tạo thread hoặc tự polling. Trong ứng dụng Spring, listener container chịu trách nhiệm đăng ký và điều phối việc nhận. Container nhận Message từ provider rồi gọi listener được cấu hình.

## 2. MessageListener của Jakarta JMS

Interface chuẩn nằm trong package jakarta.jms:

~~~java
public interface MessageListener {
    void onMessage(Message message);
}
~~~

Một class triển khai MessageListener có thể nhận nhiều loại JMS Message. Listener cần kiểm tra loại Message và đọc payload tương ứng.

Ví dụ nhận TextMessage:

~~~java
public final class RawOrderListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected a TextMessage"
            );
        }

        try {
            System.out.println("orderId=" + textMessage.getText());
        }
        catch (JMSException ex) {
            throw new IllegalStateException(
                    "Cannot read order message", ex
            );
        }
    }
}
~~~

Phương thức onMessage không khai báo throws JMSException. Nếu thao tác đọc Message gặp JMSException, ứng dụng cần xử lý hoặc chuyển thành unchecked exception theo chính sách của listener container.

Listener nên xử lý nhanh và có giới hạn. Nếu công việc tốn thời gian, hãy xem xét đưa phần xử lý nặng sang worker pool có kiểm soát, nhưng phải thiết kế acknowledgement và transaction sao cho Message chỉ được xác nhận khi công việc thực sự đạt trạng thái mong muốn.

## 3. Message-Driven POJO trong Spring

Message-Driven POJO (MDP) là một object Java thông thường được dùng làm nơi xử lý JMS Message. Ý tưởng tương tự Message-Driven Bean trong EJB, nhưng class nghiệp vụ không cần phụ thuộc EJB container.

Spring hỗ trợ MDP theo ba cách phổ biến:

1. POJO trực tiếp triển khai jakarta.jms.MessageListener.
2. POJO không phụ thuộc JMS API và được bọc bằng MessageListenerAdapter.
3. POJO khai báo phương thức nhận bằng @JmsListener; Spring đăng ký endpoint và tạo listener container.

Điểm chung là logic nghiệp vụ được gọi khi Message đến. Điểm khác nhau nằm ở mức độ phụ thuộc JMS API, cách chuyển đổi payload và cách cấu hình endpoint.

### 3.1. POJO triển khai MessageListener

Cách này phù hợp khi cần làm việc trực tiếp với JMS Message, properties, headers hoặc kiểu message đặc thù:

~~~java
public class OrderMessageListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        // Đọc JMS Message và gọi nghiệp vụ.
    }
}
~~~

Ưu điểm là toàn quyền truy cập đối tượng JMS Message. Đổi lại, class phụ thuộc Jakarta JMS và phải tự xử lý việc kiểm tra kiểu, đọc payload và các JMSException phát sinh.

### 3.2. POJO dùng MessageListenerAdapter

MessageListenerAdapter cho phép bọc một POJO không triển khai MessageListener. Adapter chuyển nội dung JMS Message thành kiểu Java phù hợp rồi gọi phương thức trên delegate.

Ví dụ POJO:

~~~java
public class OrderDelegate {

    public void handleMessage(String orderId) {
        System.out.println("orderId=" + orderId);
    }
}
~~~

Cấu hình adapter:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new OrderDelegate());

adapter.setDefaultListenerMethod("handleMessage");
~~~

Tên phương thức mặc định đã là handleMessage, nên dòng setDefaultListenerMethod chỉ cần khi muốn thể hiện rõ hoặc thay bằng tên khác, ví dụ processOrder.

Theo mặc định, adapter dùng SimpleMessageConverter để trích payload khỏi JMS Message. Các ánh xạ phổ biến gồm:

| JMS Message | Payload Java thường nhận |
|---|---|
| TextMessage | String |
| BytesMessage | byte[] |
| MapMessage | Map |
| ObjectMessage | Serializable object |

Nếu muốn POJO nhận nguyên JMS Message, có thể đặt MessageConverter của adapter thành null và khai báo tham số phương thức là kiểu Message phù hợp.

Adapter cũng hỗ trợ response: nếu phương thức delegate trả về một object khác null, adapter có thể chuyển object đó thành JMS Message và gửi tới JMSReplyTo của request hoặc destination phản hồi mặc định đã cấu hình. Cơ chế này dùng entry point SessionAwareMessageListener do adapter triển khai khi được listener container gọi. Nếu phương thức trả void, không có response tự động.

## 4. Listener container quản lý những gì?

MessageListenerContainer là thành phần trung gian giữa JMS provider và listener. Nó quản lý:

- Tạo và đăng ký JMS Connection, Session và MessageConsumer.
- Nhận Message rồi gọi listener trên thread phù hợp.
- Số consumer đồng thời và lifecycle của các consumer.
- Acknowledgement hoặc transaction của từng lần xử lý.
- Giải phóng tài nguyên khi dừng ứng dụng.
- Phục hồi khi broker hoặc kết nối gặp lỗi, tùy implementation và cấu hình.

Ứng dụng thường không nên tự tạo một Session dùng chung cho nhiều thread. JMS Session không được thiết kế để nhiều thread đồng thời thao tác. Listener container quản lý session riêng cho từng consumer/invoker theo implementation.

Khi tăng concurrency, cùng một instance listener hoặc POJO có thể được gọi đồng thời từ nhiều thread. Vì vậy, field mutable trong listener phải được bảo vệ bằng cơ chế thread-safe, hoặc tốt hơn là giữ listener stateless và đưa trạng thái riêng của mỗi lần xử lý vào biến cục bộ.

## 5. Hai listener container chuẩn của Spring

Spring Framework cung cấp hai implementation phổ biến.

### 5.1. SimpleMessageListenerContainer

SimpleMessageListenerContainer tạo số lượng Session và Consumer cố định khi khởi động, sau đó đăng ký listener qua JMS MessageConsumer.setMessageListener. JMS provider thực hiện callback listener.

Đặc điểm:

- Cấu hình đơn giản, gần với cơ chế listener chuẩn của JMS.
- Số consumer được tạo cố định lúc startup.
- Không tự điều chỉnh concurrency theo nhu cầu runtime.
- Hỗ trợ JMS transaction nội bộ khi bật sessionTransacted.
- Không hỗ trợ tham gia transaction được quản lý bên ngoài theo cách của DefaultMessageListenerContainer.
- Có những giới hạn tương thích trong một số môi trường Jakarta EE.

### 5.2. DefaultMessageListenerContainer

DefaultMessageListenerContainer thường phù hợp hơn cho ứng dụng Spring cần khả năng phục hồi và điều chỉnh tải.

Đặc điểm:

- Quản lý thread và vòng nhận thông điệp của container.
- Hỗ trợ concurrency và dynamic scaling.
- Hỗ trợ JMS transaction nội bộ và transaction được quản lý bên ngoài.
- Có cơ chế recovery khi broker hoặc kết nối bị gián đoạn.
- Có thể cấu hình BackOff để điều chỉnh khoảng chờ giữa các lần thử kết nối lại.
- Có thể cache Connection, Session và Consumer theo cache level.

Dù tên hai container khác nhau, cả hai đều đưa Message tới listener theo cách bất đồng bộ so với producer. Khác biệt nằm ở cách container đăng ký/nhận Message và các khả năng vận hành.

Trong đa số trường hợp, DefaultMessageListenerContainer là lựa chọn linh hoạt hơn. SimpleMessageListenerContainer phù hợp khi muốn cấu hình cố định và chấp nhận giới hạn transaction/concurrency của nó.

## 6. Cấu hình DefaultMessageListenerContainer bằng Java

Ví dụ cấu hình một listener cho Queue:

~~~java
@Bean
DefaultMessageListenerContainer orderListenerContainer(
        ConnectionFactory connectionFactory,
        OrderMessageListener listener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.in");
    container.setMessageListener(listener);
    container.setSessionTransacted(true);
    container.setConcurrentConsumers(1);

    return container;
}
~~~

Spring quản lý bean container và tự gọi lifecycle callback. Container khởi động cùng application context và dừng khi context đóng.

setDestinationName dùng DestinationResolver của container để phân giải tên destination. Mặc định, tên được phân giải động thành Queue khi pubSubDomain=false. Nếu cần Topic, cấu hình pubSubDomain=true hoặc truyền một Destination object phù hợp.

Có thể dùng setDestination(destination) khi đã có đối tượng Queue hoặc Topic.

## 7. Dùng @JmsListener

Annotation @JmsListener là cách thuận tiện để khai báo endpoint nhận JMS. Spring tạo và quản lý listener container cho từng endpoint.

Bật annotation support bằng @EnableJms:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("3-10");

        return factory;
    }
}
~~~

POJO nhận thông điệp:

~~~java
@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.in",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void handleOrder(String orderId) {
        System.out.println("orderId=" + orderId);
    }
}
~~~

Nếu không chỉ định containerFactory, Spring mặc định tìm bean tên jmsListenerContainerFactory. Có thể cấu hình concurrency ngay trên annotation; giá trị tại endpoint sẽ ghi đè cấu hình tương ứng của factory.

Phương thức listener có thể nhận payload đã chuyển đổi, raw jakarta.jms.Message, hoặc các tham số được Spring hỗ trợ như header và thông tin JMS. Việc chuyển đổi phụ thuộc MessageConverter được cấu hình cho listener container.

### 7.1. Chọn destination, selector và subscription

@JmsListener hỗ trợ các thuộc tính thường dùng:

- destination: tên Queue hoặc Topic.
- selector: biểu thức JMS message selector để lọc Message.
- concurrency: giới hạn consumer/session đồng thời.
- subscription: tên durable subscription cho Topic.
- containerFactory: bean factory tạo listener container.

Ví dụ:

~~~java
@JmsListener(
        destination = "orders.events",
        selector = "eventType = 'order.created'",
        subscription = "order-projection",
        containerFactory = "topicListenerContainerFactory"
)
public void onOrderCreated(String payload) {
    // Cập nhật projection.
}
~~~

Với Topic durable subscription, cần cấu hình đúng pubSubDomain, client ID, subscription name và loại subscription mà provider hỗ trợ. Một durable subscription lưu thông điệp cho subscriber theo chính sách của broker khi subscriber tạm thời offline; nó không tự bảo đảm xử lý nghiệp vụ đúng một lần.

## 8. MessageListener, MessageListenerAdapter và @JmsListener khác nhau thế nào?

| Cách triển khai | Listener phụ thuộc JMS API? | Cách nhận dữ liệu | Khi phù hợp |
|---|---|---|---|
| MessageListener | Có | Nhận raw Message trong onMessage | Cần kiểm soát JMS Message và properties |
| MessageListenerAdapter + POJO | POJO không cần phụ thuộc JMS | Adapter chuyển Message thành payload Java | Muốn tách logic nghiệp vụ khỏi JMS API |
| @JmsListener | Phương thức POJO được Spring đăng ký | Spring chuyển đổi và bind tham số | Muốn khai báo endpoint gọn và quản lý bằng container factory |

Cả ba cách đều cần hạ tầng nhận. MessageListenerAdapter không tự kết nối broker; @JmsListener cũng không tự tạo ConnectionFactory. Listener container và JMS provider vẫn phải được cấu hình đúng.

## 9. Concurrency và thread safety

Concurrency quyết định có bao nhiêu consumer/session có thể nhận Message cùng lúc.

Với DefaultMessageListenerContainer:

~~~java
container.setConcurrentConsumers(3);
container.setMaxConcurrentConsumers(10);
~~~

Hoặc qua factory:

~~~java
factory.setConcurrency("3-10");
~~~

Với Queue, nhiều consumer thường cạnh tranh lấy các Message khác nhau từ cùng queue. Tăng consumer có thể tăng throughput nếu handler và hệ thống phía sau đủ năng lực.

Tuy nhiên, khi có nhiều consumer:

- Thứ tự hoàn tất xử lý không còn bảo đảm theo thứ tự gửi.
- Hai Message của cùng một đơn hàng có thể được xử lý đồng thời.
- Database hoặc service downstream có thể trở thành nút thắt.
- Một listener object có thể được gọi đồng thời, nên không an toàn nếu giữ state mutable không đồng bộ.

Với Topic, không nên tăng consumer một cách máy móc. Tùy kiểu subscription và provider, nhiều consumer có thể khiến một publication được giao cho nhiều consumer. Chỉ cấu hình concurrency cho Topic khi đã hiểu shared subscription và semantics cụ thể của broker.

Nếu thứ tự theo khóa nghiệp vụ quan trọng, hãy phân vùng hoặc tuần tự hóa xử lý theo khóa đó, thay vì dựa vào số consumer.

## 10. Acknowledgement và transaction

Sau khi listener xử lý Message, JMS provider cần biết Message đã được xác nhận hay cần giao lại. Hành vi này phụ thuộc acknowledgement mode và transaction.

### 10.1. AUTO_ACKNOWLEDGE

Đây là chế độ mặc định phổ biến. Với listener container, AUTO_ACKNOWLEDGE không phải lựa chọn đáng tin cậy cho mọi tình huống. Nếu listener gặp lỗi, provider có thể đã acknowledge Message theo hành vi callback và Message có nguy cơ bị mất thay vì redelivery.

Nếu nghiệp vụ cần độ tin cậy, hãy cấu hình transaction hoặc acknowledgement phù hợp.

### 10.2. sessionTransacted=true

Cấu hình:

~~~java
container.setSessionTransacted(true);
~~~

Mỗi lần listener xử lý Message nằm trong một JMS local transaction. Khi listener hoàn tất bình thường, container commit. Khi listener ném exception, transaction rollback và provider có thể giao lại Message theo redelivery policy.

Đây là lựa chọn thường phù hợp cho queue consumer cần xử lý đáng tin cậy. Hãy xác định số lần redelivery, backoff và dead-letter policy ở broker.

### 10.3. JMS transaction không tự bao gồm database

Nếu listener cập nhật database rồi JMS transaction rollback, database transaction có thể đã commit trong khi Message được giao lại. Điều này tạo ra khả năng xử lý trùng.

Cần thiết kế idempotency hoặc duplicate detection, ví dụ lưu message ID/event ID đã xử lý trong cùng database transaction với cập nhật nghiệp vụ.

Nếu phải commit JMS và database như một giao dịch phân tán duy nhất, có thể dùng JTA/XA với XA-capable ConnectionFactory và transaction coordinator phù hợp. XA có chi phí và yêu cầu vận hành cao hơn; chỉ dùng khi semantics nghiệp vụ thực sự cần.

## 11. Xử lý lỗi, redelivery và poison message

Một listener có thể lỗi do payload không hợp lệ, dependency ngoài bị gián đoạn, database timeout hoặc bug nghiệp vụ.

Cần phân loại lỗi:

- **Lỗi tạm thời:** có thể retry sau một khoảng chờ.
- **Lỗi dữ liệu:** retry không giúp ích; cần đưa vào dead-letter queue hoặc luồng xử lý lỗi.
- **Lỗi hạ tầng:** container cần recovery/reconnect và theo dõi trạng thái broker.
- **Lỗi lập trình:** cần log đầy đủ message ID, destination, exception và correlation ID.

Không retry vô hạn một Message chắc chắn không thể xử lý. Broker thường cung cấp redelivery counter, delay, maximum attempts và dead-letter address/queue; cấu hình cụ thể phụ thuộc provider.

Listener nên ghi log đủ ngữ cảnh nhưng không log bí mật hoặc toàn bộ payload nhạy cảm. Khi bắt exception, đừng nuốt lỗi nếu cần transaction rollback và redelivery.

DefaultMessageListenerContainer có cơ chế recovery khi broker ngừng hoạt động. Có thể tùy chỉnh BackOff để tránh retry quá dồn dập khi broker chưa sẵn sàng.

## 12. Message conversion và response

JMS listener có thể nhận raw Message hoặc payload Java đã chuyển đổi.

SimpleMessageConverter mặc định hỗ trợ các kiểu JMS phổ biến như TextMessage, BytesMessage, MapMessage và ObjectMessage. Nếu ứng dụng trao đổi DTO phức tạp, hãy cấu hình MessageConverter phù hợp, thường là JSON converter với schema và type mapping rõ ràng.

Không nên bật deserialization Java tùy ý cho ObjectMessage từ nguồn không tin cậy. Hãy kiểm soát type được phép và ưu tiên định dạng dữ liệu có schema rõ ràng.

### 12.1. Trả lời request qua MessageListenerAdapter

Nếu delegate trả về một giá trị khác null, MessageListenerAdapter có thể chuyển giá trị đó thành JMS Message rồi gửi về:

1. Destination được chỉ định trong JMSReplyTo của request.
2. Destination phản hồi mặc định đã cấu hình trên adapter nếu request không có JMSReplyTo.

Ví dụ:

~~~java
public class InventoryDelegate {

    public String handleMessage(String sku) {
        return "available:" + sku;
    }
}
~~~

Khi adapter nhận request và delegate trả về String, adapter có thể gửi TextMessage phản hồi. Cần có reply destination hợp lệ; nếu không có nơi gửi reply, thao tác phản hồi có thể thất bại.

Cơ chế này phù hợp với request-reply. Với event một chiều, delegate nên trả void và producer không chờ reply.

## 13. Vòng đời và shutdown

Listener container thường được Spring quản lý theo lifecycle. Khi application context khởi động, container đăng ký consumer. Khi ứng dụng dừng, container ngừng nhận Message và giải phóng các resource mà nó sở hữu.

Với container tự tạo ngoài Spring context, ứng dụng cần chủ động:

1. Khởi tạo container.
2. Start container sau khi cấu hình đầy đủ.
3. Dừng container trong shutdown path.
4. Destroy container để giải phóng connection/session/consumer.

Không đóng Connection hoặc Session đang được listener khác sử dụng. Để container quản lý resource mà nó tạo.

Nếu shutdown xảy ra khi listener đang xử lý, hãy xác định thời gian chờ graceful shutdown và chính sách với Message chưa commit. Với transacted session, việc đóng hoặc rollback có thể khiến Message được giao lại.

## 14. Ví dụ Java 17 chạy được: MessageListenerAdapter và DefaultMessageListenerContainer

Ví dụ dưới đây dùng Apache ActiveMQ Classic 6.1.6 làm JMS provider, Spring Framework 6.2.19 và Java 17. Cần có broker ActiveMQ Classic đang chạy tại tcp://localhost:61616 và queue orders.in đã được tạo hoặc broker cho phép auto-create queue.

Chương trình dùng MessageListenerAdapter để gọi một POJO nhận String. DefaultMessageListenerContainer quản lý thread nhận và session transacted.

### 14.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-message-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>6.1.6</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

ActiveMQ Classic 6.x sử dụng namespace jakarta.jms, tương thích với Spring Framework 6. Không trộn client JMS dùng javax.jms với Spring 6.

### 14.2. Chương trình hoàn chỉnh

Tạo file src/main/java/demo/JmsMessageListenerDemo.java:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.adapter.MessageListenerAdapter;

public class JmsMessageListenerDemo {

    public static final class OrderDelegate {
        private final CountDownLatch received;

        public OrderDelegate(CountDownLatch received) {
            this.received = received;
        }

        public void handleMessage(String orderId) {
            System.out.println("listener.payload=" + orderId);
            received.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        ConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        CountDownLatch received = new CountDownLatch(1);
        OrderDelegate delegate = new OrderDelegate(received);

        MessageListenerAdapter adapter =
                new MessageListenerAdapter(delegate);
        adapter.setDefaultListenerMethod("handleMessage");

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.in");
        container.setMessageListener(adapter);
        container.setSessionTransacted(true);
        container.setConcurrentConsumers(1);
        container.afterPropertiesSet();

        JmsTemplate producer = new JmsTemplate(connectionFactory);

        try {
            container.start();

            producer.convertAndSend("orders.in", "ORD-150");

            if (!received.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not receive the message in time"
                );
            }

            System.out.println("producer.completed=true");
        }
        finally {
            container.stop();
            container.destroy();
        }
    }
}
~~~

Chạy từ thư mục chứa pom.xml khi broker đã sẵn sàng:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.JmsMessageListenerDemo
~~~

Các dòng do chương trình in ra:

~~~text
listener.payload=ORD-150
producer.completed=true
~~~

Log nội bộ của JMS provider có thể xuất hiện tùy cấu hình logging. Thứ tự hai dòng của chương trình được bảo đảm bởi CountDownLatch: listener in payload trước khi giảm latch; producer chỉ in completed sau khi latch được mở.

### 14.3. Phân tích chương trình

Producer dùng JmsTemplate để gửi String ORD-150 tới queue orders.in. SimpleMessageConverter chuyển String thành TextMessage.

DefaultMessageListenerContainer đã đăng ký consumer trước khi producer gửi. Khi Message tới, container gọi MessageListenerAdapter. Adapter chuyển TextMessage thành String rồi gọi OrderDelegate.handleMessage.

Listener chạy trên thread nhận do container quản lý. Producer không gọi trực tiếp delegate. CountDownLatch chỉ dùng trong ví dụ để chờ kết quả kiểm thử; trong ứng dụng thật, producer thường tiếp tục công việc ngay sau khi gửi và không chờ listener.

setSessionTransacted(true) đặt mỗi lần xử lý listener trong một JMS local transaction. Khi listener hoàn tất bình thường, transaction được commit. Nếu listener ném exception, transaction có thể rollback và broker giao lại Message theo redelivery policy.

Ví dụ dùng một consumer để giữ thứ tự output dễ quan sát. Có thể tăng concurrency khi cần throughput, nhưng phải kiểm tra ordering, thread safety và tải của hệ thống phía sau.

## 15. Lựa chọn cách nhận phù hợp

| Nhu cầu | Cách triển khai phù hợp |
|---|---|
| Cần đọc raw JMS Message và kiểm tra properties/header | MessageListener |
| Muốn POJO không phụ thuộc JMS API | MessageListenerAdapter |
| Muốn khai báo listener bằng annotation | @JmsListener |
| Cần cấu hình thread, transaction, recovery và concurrency rõ ràng | DefaultMessageListenerContainer hoặc factory tương ứng |
| Cần container đơn giản với số consumer cố định | SimpleMessageListenerContainer |
| Cần trả reply từ kết quả của POJO | MessageListenerAdapter với JMSReplyTo hoặc response destination |
| Cần xử lý đáng tin cậy và redelivery khi listener lỗi | Container với sessionTransacted và broker redelivery policy |

Không có một lựa chọn phù hợp cho mọi hệ thống. Hãy bắt đầu từ kiểu Message, mức phụ thuộc JMS mong muốn, transaction, concurrency và khả năng vận hành của broker.

## 16. Lỗi thường gặp

1. **Tưởng MessageListener tự tạo thread:** listener chỉ định nghĩa callback; listener container hoặc JMS provider mới điều phối thread nhận.
2. **Tự chia sẻ một JMS Session cho nhiều thread:** Session không được thiết kế cho truy cập đồng thời; để container quản lý session riêng.
3. **Dùng listener có field mutable khi tăng concurrency:** nhiều consumer có thể gọi cùng instance và gây race condition.
4. **Quên chuyển đổi payload:** nếu nhận raw Message, phải kiểm tra kiểu TextMessage, BytesMessage, MapMessage hoặc ObjectMessage trước khi đọc.
5. **Nhầm MessageListenerAdapter với broker:** adapter chỉ chuyển Message và gọi POJO; container vẫn phải kết nối tới provider.
6. **Không cấu hình transaction khi cần độ tin cậy:** AUTO_ACKNOWLEDGE có thể không đáp ứng yêu cầu redelivery khi listener lỗi.
7. **Cho rằng sessionTransacted bao gồm database:** local JMS transaction không tự commit/rollback database.
8. **Tăng consumer rồi kỳ vọng giữ thứ tự:** nhiều consumer có thể hoàn tất Message theo thứ tự khác thứ tự gửi.
9. **Tăng concurrency cho Topic mà không hiểu subscription:** có thể làm mỗi publication được nhiều consumer xử lý.
10. **Retry poison message vô hạn:** cấu hình maximum redelivery và dead-letter policy ở broker.
11. **Không quản lý lifecycle:** listener container cần được stop/destroy khi ứng dụng dừng.
12. **Nhầm javax.jms và jakarta.jms:** Spring Framework 6 dùng jakarta.jms; client/provider phải tương thích namespace.
13. **Không xác định Reply-To:** phương thức delegate trả về object có thể kích hoạt gửi reply; cần destination hợp lệ.
14. **Cho rằng listener hoàn tất là exactly-once:** transaction và redelivery vẫn có thể tạo duplicate trong các tình huống lỗi hoặc restart.

## 17. Câu hỏi tự kiểm tra

1. MessageListener của Jakarta JMS có phương thức callback nào?
2. Vì sao nhận bất đồng bộ không yêu cầu producer gọi trực tiếp consumer?
3. Message-Driven POJO khác MessageListener triển khai trực tiếp ở điểm nào?
4. MessageListenerAdapter dùng phương thức delegate mặc định tên gì?
5. SimpleMessageConverter ánh xạ TextMessage và BytesMessage thành kiểu Java nào?
6. Listener container quản lý những tài nguyên nào?
7. SimpleMessageListenerContainer khác DefaultMessageListenerContainer ở khả năng nào?
8. @EnableJms và @JmsListener phối hợp như thế nào?
9. concurrency 3-10 có ý nghĩa gì?
10. Vì sao nhiều consumer có thể làm mất thứ tự xử lý?
11. sessionTransacted=true thay đổi điều gì khi listener ném exception?
12. Vì sao JMS local transaction không tự bao gồm database?
13. MessageListenerAdapter gửi reply về đâu khi delegate trả về giá trị khác null?
14. Vì sao listener phải thread-safe khi container chạy nhiều consumer?
15. Cần làm gì để tránh retry vô hạn một poison message?

## 18. Kết luận

Nhận bất đồng bộ bằng MessageListener cho phép JMS provider và Spring listener container chuyển Message tới logic xử lý trên thread nhận. MessageListener cung cấp callback chuẩn; MessageListenerAdapter cho phép dùng POJO không phụ thuộc JMS API; @JmsListener giúp khai báo endpoint bằng annotation.

Listener container quản lý Connection, Session, Consumer, thread, transaction, acknowledgement, recovery và lifecycle. Khi triển khai, cần chọn container phù hợp, cấu hình concurrency theo tải, giữ listener thread-safe, bật transaction khi cần redelivery và phối hợp idempotency với database. Việc gửi được Message tới Queue hoặc Topic không đồng nghĩa nghiệp vụ đã xử lý đúng một lần.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Receiving a Message: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — Using Spring JMS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- MessageListenerAdapter API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/adapter/MessageListenerAdapter.html
- DefaultMessageListenerContainer API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- SimpleMessageListenerContainer API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html
- Jakarta Messaging specification: https://jakarta.ee/specifications/messaging/
- Apache ActiveMQ Classic 6.1.6 release: https://activemq.apache.org/components/classic/download/classic-06-01-06
