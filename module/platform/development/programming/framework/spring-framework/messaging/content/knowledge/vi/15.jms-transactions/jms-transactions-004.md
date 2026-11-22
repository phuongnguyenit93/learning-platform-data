# sessionTransacted và giao dịch cục bộ trên Session

JMS cho phép nhóm thao tác gửi và nhận message thành một giao dịch. Khi một Session được tạo ở chế độ transacted, ứng dụng quyết định thời điểm hoàn tất nhóm thao tác bằng commit() hoặc hủy nhóm thao tác bằng rollback(). Spring JMS hỗ trợ quản lý giao dịch này qua JmsTemplate, JmsTransactionManager và message listener container.

Ranh giới của giao dịch local là một JMS Session. Các message đã nhận và các message đã gửi trên cùng Session được xác nhận hoặc hoàn tác cùng nhau. Giao dịch này không tự bao trùm thao tác database, HTTP hoặc một JMS ConnectionFactory khác.

Bài này giải thích cách hoạt động của giao dịch Session, so sánh với acknowledgment mode, cách cấu hình Spring, cách xử lý redelivery và cách kiểm thử bằng một chương trình Java 17 kết nối tới Apache ActiveMQ Artemis.

## 1. Giao dịch local trên JMS Session là gì?

Một JMS Session là ngữ cảnh làm việc nơi ứng dụng tạo Message, MessageProducer và MessageConsumer. Khi Session được tạo ở chế độ transacted, các thao tác gửi và nhận message được gom vào một giao dịch cục bộ.

Tạo Session transacted bằng Jakarta Messaging:

~~~java
Session session = connection.createSession(true, Session.SESSION_TRANSACTED);
~~~

Với một Session transacted:

- Message được gửi trong giao dịch chưa commit chưa được xác nhận là đã gửi thành công tới luồng nhận.
- Message được nhận trong giao dịch chưa commit vẫn thuộc giao dịch đang mở.
- commit() hoàn tất giao dịch: message gửi được commit và message nhận được acknowledge.
- rollback() hủy giao dịch: message gửi bị hủy (discarded) và message nhận được đưa trở lại trạng thái có thể giao lại.

Ví dụ một lượt xử lý:

~~~text
Consumer nhận Order #1024
          |
          v
Kiểm tra và xử lý đơn hàng
          |
          +---- Thành công ----> session.commit()
          |                         |
          |                         +--> Message được xác nhận
          |
          +---- Có lỗi --------> session.rollback()
                                    |
                                    +--> Message có thể được giao lại
~~~

Giao dịch được quản lý bởi provider/broker theo hợp đồng JMS. Ứng dụng không tự ghi trạng thái message vào database để giả lập commit.

## 2. commit() và rollback() ảnh hưởng đến những gì?

Một giao dịch JMS trên Session có thể bao gồm cả message gửi và message nhận. Đây là lợi ích quan trọng của Session transacted.

| Thao tác trong cùng Session | commit() | rollback() |
|---|---|---|
| Gửi một message | Message được commit và có thể được giao | Message gửi bị hủy, không được giao từ giao dịch này |
| Nhận một message | Message được acknowledge | Message có thể được giao lại |
| Nhận rồi gửi reply | Nhận và gửi được hoàn tất cùng giao dịch | Nhận bị hoàn tác và reply gửi bị hủy |
| Nhiều message gửi/nhận | Cùng được hoàn tất | Cùng bị hoàn tác |

Ví dụ consumer nhận một đơn hàng, sau đó gửi sự kiện OrderProcessed. Nếu cả nhận và gửi diễn ra trên cùng Session transacted, một commit sẽ xác nhận việc nhận đơn hàng và gửi sự kiện phản hồi trong cùng giao dịch JMS.

Nếu xử lý thất bại và rollback, broker có thể giao lại đơn hàng và không phát sự kiện OrderProcessed đã gửi trong giao dịch bị hủy.

Điều kiện quan trọng là các thao tác phải thực sự dùng cùng Session. Nếu producer và consumer dùng hai Session khác nhau, mỗi Session có giao dịch riêng, kể cả khi chúng cùng thuộc một Connection.

## 3. Phạm vi của giao dịch là một Session

JMS Connection có thể tạo nhiều Session. Mỗi Session transacted quản lý giao dịch riêng.

~~~text
JMS Connection
    |
    +---- Session A (transaction A)
    |         |
    |         +---- Producer A
    |         +---- Consumer A
    |
    +---- Session B (transaction B)
              |
              +---- Producer B
              +---- Consumer B
~~~

Nếu Session A commit, giao dịch của Session B không tự động commit theo. Tương tự, rollback Session A không hoàn tác message đã commit trên Session B.

Điều này cũng áp dụng khi hai Session dùng chung một Connection vật lý. Chia sẻ Connection không đồng nghĩa chia sẻ transaction.

Trong thực tế, một luồng xử lý thường sử dụng Session do Spring hoặc JMS provider quản lý. Không chia sẻ một Session transacted giữa nhiều thread. Session và các producer/consumer được tạo từ nó phải được sử dụng tuần tự theo quy tắc Jakarta Messaging.

## 4. Giao dịch Session khác acknowledgment mode như thế nào?

Khi tạo Session không transacted, ứng dụng chọn acknowledgment mode:

| Chế độ | Hành vi |
|---|---|
| AUTO_ACKNOWLEDGE | Provider tự xác nhận message theo quy tắc của chế độ |
| CLIENT_ACKNOWLEDGE | Client chủ động gọi acknowledge() |
| DUPS_OK_ACKNOWLEDGE | Cho phép provider xác nhận theo nhóm và có thể giao trùng |
| SESSION_TRANSACTED | Session dùng giao dịch local; commit/rollback điều khiển xác nhận và phục hồi |

Với Session transacted, acknowledgment mode không còn điều khiển việc xác nhận message. commit() thực hiện acknowledgment; rollback() thực hiện recovery. Không cần gọi message.acknowledge() trong một giao dịch transacted.

Với CLIENT_ACKNOWLEDGE, một lời gọi acknowledge() trên message có thể xác nhận tất cả message đã được Session tiêu thụ trước đó. Đây không phải cơ chế transaction bao gồm cả message gửi.

Nếu cần một nhóm thao tác nhận và gửi có tính nguyên tử trong phạm vi JMS, Session transacted là lựa chọn rõ ràng hơn.

### Vì sao AUTO_ACKNOWLEDGE có thể không đủ tin cậy?

Trong một số kiểu listener container, message có thể được acknowledge trước khi listener hoàn tất nghiệp vụ. Nếu listener ném exception sau đó, broker không nhất thiết giao lại message.

Spring khuyến nghị dùng transacted Session khi cần độ tin cậy cho việc nhận message. Với listener container, cấu hình sessionTransacted=true giúp việc nhận và xử lý listener nằm trong giao dịch JMS local.

## 5. Tạo và sử dụng Session transacted bằng Jakarta Messaging

Để bắt đầu một giao dịch local, ứng dụng tạo Session ở chế độ SESSION_TRANSACTED:

~~~java
Session session = connection.createSession(true, Session.SESSION_TRANSACTED);
~~~

Sau đó, mọi thao tác gửi và nhận qua Session này tham gia giao dịch đang mở.

Gửi message và commit:

~~~java
TextMessage message = session.createTextMessage("Order #1024");
producer.send(message);
session.commit();
~~~

Nhận message và commit:

~~~java
Message received = consumer.receive(5000);

if (received != null) {
    // Xử lý nghiệp vụ thành công.
    session.commit();
}
~~~

Nếu xử lý thất bại:

~~~java
try {
    Message received = consumer.receive(5000);

    if (received != null) {
        process(received);
        session.commit();
    }
}
catch (Exception ex) {
    session.rollback();
    throw ex;
}
~~~

Trong ứng dụng thật, cần quyết định rõ xử lý exception nào phải rollback. Không nên nuốt exception rồi commit, vì như vậy message vẫn được xác nhận dù nghiệp vụ chưa hoàn tất.

Các phương thức commit() và rollback() chỉ dành cho Session transacted do ứng dụng quản lý. Gọi chúng trên Session không transacted sẽ gây lỗi IllegalStateException.

Khi đóng một Session còn giao dịch chưa commit, Jakarta Messaging quy định giao dịch đang mở sẽ bị rollback. Vì vậy, try-with-resources giúp giải phóng tài nguyên nhưng không thay thế việc commit tường minh khi nghiệp vụ thành công.

## 6. Giao dịch local không tự bao gồm database

Giả sử listener nhận một message và cập nhật database:

~~~text
JMS Broker
    |
    | nhận OrderCreated
    v
JMS Session transaction
    |
    +----> Database transaction
    |         |
    |         +---- UPDATE orders
    |         +---- COMMIT database
    |
    +----> JMS commit
~~~

Nếu database commit thành công nhưng JMS commit thất bại, broker có thể giao lại message. Listener sẽ nhận lại cùng sự kiện và có nguy cơ cập nhật dữ liệu lần thứ hai.

Nếu JMS commit thành công nhưng database transaction thất bại, message đã được xác nhận trong khi dữ liệu nghiệp vụ chưa được lưu.

Một JMS local transaction chỉ quản lý tài nguyên JMS trên Session/ConnectionFactory tương ứng. Nó không tự tạo giao dịch phân tán với database.

Có ba hướng thiết kế thường gặp:

**Idempotency và duplicate detection:** lưu một event ID hoặc business operation ID trong database. Trước khi thực hiện cập nhật, kiểm tra sự kiện đã được xử lý chưa. Nếu broker giao lại message, thao tác đã hoàn tất trước đó không bị lặp.

**Outbox/inbox pattern:** ghi thay đổi nghiệp vụ và bản ghi sự kiện vào cùng database transaction. Một tiến trình khác phát sự kiện từ outbox. Phía nhận có thể lưu event ID vào inbox để chống xử lý trùng. Cách này thường dễ vận hành hơn XA trong nhiều hệ thống dịch vụ.

**XA/JTA transaction:** dùng transaction coordinator và các resource XA-capable để đưa JMS và database vào cùng giao dịch phân tán. Cách này yêu cầu cấu hình phức tạp hơn, transaction log và sự hỗ trợ của provider lẫn database.

Không nên tuyên bố exactly-once chỉ vì đã bật sessionTransacted. Redelivery và duplicate vẫn có thể xuất hiện ở ranh giới lỗi hoặc khi kết quả commit không rõ ràng.

## 7. Giao dịch local với JmsTemplate

JmsTemplate hỗ trợ thuộc tính sessionTransacted. Khi bật, template tạo Session transacted cho thao tác nếu không có transaction đang được quản lý bên ngoài.

Cấu hình:

~~~java
@Bean
public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setSessionTransacted(true);
    return template;
}
~~~

Khi gọi:

~~~java
jmsTemplate.convertAndSend("orders.queue", "Order #1024 created");
~~~

Spring thực hiện thao tác gửi trên Session transacted và hoàn tất giao dịch theo vòng đời thao tác của template. Nếu có lỗi trong thao tác, giao dịch local được rollback.

Nếu cần nhiều lệnh JMS cùng tham gia một giao dịch, có thể dùng JmsTransactionManager.

### JmsTransactionManager

JmsTransactionManager quản lý giao dịch local cho một ConnectionFactory. Nó gắn cặp Connection/Session đang tham gia giao dịch vào thread hiện tại. JmsTemplate nhận biết tài nguyên đã được bind và sử dụng Session đó.

Khai báo transaction manager:

~~~java
@Bean
public JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {

    return new JmsTransactionManager(connectionFactory);
}
~~~

Một service có thể gửi nhiều message trong cùng một giao dịch:

~~~java
@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publishOrder(String orderId) {
        jmsTemplate.convertAndSend(
                "orders.events",
                "OrderCreated:" + orderId
        );

        jmsTemplate.convertAndSend(
                "audit.events",
                "OrderCreated:" + orderId
        );
    }
}
~~~

Khi phương thức hoàn tất bình thường, transaction manager commit giao dịch JMS. Nếu phương thức ném RuntimeException, giao dịch được rollback theo quy tắc rollback mặc định của Spring. Với checked exception, cấu hình rollbackFor nếu nghiệp vụ yêu cầu rollback.

Hai lệnh gửi sử dụng cùng tài nguyên JMS được bind vào thread, do đó chúng thuộc cùng giao dịch local nếu cùng ConnectionFactory và cùng transaction manager.

JmsTransactionManager chỉ quản lý một ConnectionFactory. Nó không tự biến các lệnh database hoặc HTTP trong cùng phương thức thành một phần của giao dịch JMS.

## 8. Giao dịch local trong listener container

Với message listener, Spring có thể mở một giao dịch JMS local cho mỗi lần gọi listener bằng sessionTransacted=true.

Cấu hình factory:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-6");

    return factory;
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(String payload) {
        processOrder(payload);
    }

    private void processOrder(String payload) {
        System.out.println("Processing " + payload);
    }
}
~~~

Với cấu hình này, mỗi lần listener invocation chạy trong một JMS Session transaction:

1. Container nhận message.
2. Spring gọi phương thức listener.
3. Nếu listener hoàn tất bình thường, container commit.
4. Nếu listener ném exception, container rollback.
5. Broker có thể giao lại message theo redelivery policy.

Cơ chế rollback và redelivery còn phụ thuộc cấu hình broker, giới hạn số lần giao lại và dead-letter address/queue. Sau số lần thử tối đa, broker thường chuyển message sang dead-letter destination theo chính sách đã cấu hình.

Nếu listener cần gửi reply bằng SessionAwareMessageListener, thao tác gửi trên Session được cung cấp cho listener có thể thuộc cùng giao dịch local. Các thao tác database vẫn độc lập trừ khi có transaction manager phù hợp.

### DMLC và SMLC

Cả DefaultMessageListenerContainer và SimpleMessageListenerContainer đều hỗ trợ native JMS transaction thông qua sessionTransacted.

DefaultMessageListenerContainer thường được dùng khi cần recovery, concurrency linh hoạt hoặc external transaction manager. SimpleMessageListenerContainer giữ số consumer cố định và dựa vào callback của JMS provider.

Khi yêu cầu redelivery đáng tin cậy, hãy bật sessionTransacted=true hoặc cấu hình external transaction manager phù hợp. AUTO_ACKNOWLEDGE mặc định không cung cấp cùng bảo đảm rollback khi listener thất bại.

## 9. Phân biệt sessionTransacted, JmsTransactionManager và XA/JTA

Ba cách cấu hình này có liên quan nhưng ranh giới khác nhau:

| Cơ chế | Phạm vi | Ai quyết định commit/rollback? |
|---|---|---|
| Session transacted | Một JMS Session | Ứng dụng hoặc Spring quản lý Session |
| JmsTransactionManager | Một JMS ConnectionFactory, giao dịch local bind vào thread | Spring PlatformTransactionManager |
| XA/JTA | Nhiều XA resource như JMS và database | JTA transaction coordinator |

### sessionTransacted=true

Dùng khi cần giao dịch local cho một thao tác template hoặc một listener invocation. Không cần transaction coordinator bên ngoài.

### JmsTransactionManager

Dùng khi một service cần nhiều thao tác JMS tham gia cùng một giao dịch Spring. JmsTemplate tự tham gia tài nguyên JMS đã được bind vào thread.

### XA/JTA

Dùng khi cần một kết quả commit/rollback thống nhất giữa JMS và tài nguyên khác, ví dụ database, và tất cả resource manager đều hỗ trợ XA.

Ví dụ cấu hình listener container với transaction manager:

~~~java
factory.setTransactionManager(jtaTransactionManager);
~~~

Trong trường hợp XA, ConnectionFactory phải là XA-capable và được đăng ký đúng với transaction coordinator. Không chỉ tạo JtaTransactionManager là đủ.

Khi Session tham gia một JTA transaction được quản lý bởi application server, ứng dụng không tự gọi Session.commit() hoặc Session.rollback(). Transaction coordinator quyết định kết quả cuối cùng.

## 10. Ví dụ hoàn chỉnh: commit, rollback và redelivery

Ví dụ này dùng Java 17, Jakarta Messaging 3.1 và Apache ActiveMQ Artemis Jakarta client 2.40.0. Chương trình kết nối tới một Artemis broker đang chạy, tạo hai Session transacted riêng biệt, rồi quan sát ba tình huống:

1. Producer gửi message và commit.
2. Consumer nhận message rồi rollback, sau đó nhận lại message với JMSRedelivered=true và commit.
3. Producer gửi message rồi rollback; consumer không nhận được message đó.

Cấu trúc dự án:

~~~text
local-jms-transaction-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── LocalSessionTransactionDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>local-jms-transaction-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
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

### src/main/java/demo/LocalSessionTransactionDemo.java

~~~java
package demo;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public class LocalSessionTransactionDemo {

    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getenv().getOrDefault(
                "JMS_BROKER_URL", "tcp://localhost:61616");

        ConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(brokerUrl);

        try (Connection connection = connectionFactory.createConnection()) {
            Session producerSession =
                    connection.createSession(true, Session.SESSION_TRANSACTED);
            Session consumerSession =
                    connection.createSession(true, Session.SESSION_TRANSACTED);

            try {
                Queue producerQueue =
                        producerSession.createQueue("orders.local.tx.demo");
                Queue consumerQueue =
                        consumerSession.createQueue("orders.local.tx.demo");

                MessageProducer producer =
                        producerSession.createProducer(producerQueue);
                MessageConsumer consumer =
                        consumerSession.createConsumer(consumerQueue);

                try {
                    connection.start();

                    producer.send(
                            producerSession.createTextMessage("Order #1024"));
                    producerSession.commit();
                    System.out.println("[send] committed: Order #1024");

                    Message first = consumer.receive(5000);
                    if (!(first instanceof TextMessage firstText)) {
                        throw new IllegalStateException(
                                "Expected the first order message");
                    }

                    System.out.println(
                            "[receive] first delivery: " + firstText.getText());

                    consumerSession.rollback();
                    System.out.println("[transaction] receive rollback");

                    Message second = consumer.receive(5000);
                    if (!(second instanceof TextMessage secondText)) {
                        throw new IllegalStateException(
                                "Expected the rolled-back message again");
                    }

                    System.out.println(
                            "[receive] redelivered: " + secondText.getText());
                    System.out.println(
                            "[receive] JMSRedelivered: "
                                    + second.getJMSRedelivered());

                    consumerSession.commit();
                    System.out.println("[transaction] receive commit");

                    producer.send(
                            producerSession.createTextMessage("Order #discard"));
                    producerSession.rollback();
                    System.out.println(
                            "[send] rolled back: Order #discard");

                    Message discarded = consumer.receive(500);
                    if (discarded != null) {
                        throw new IllegalStateException(
                                "A rolled-back send must not be delivered");
                    }

                    System.out.println(
                            "[receive] after send rollback: none");
                }
                finally {
                    consumer.close();
                    producer.close();
                }
            }
            finally {
                consumerSession.close();
                producerSession.close();
            }
        }
    }
}
~~~

Chạy tại thư mục chứa pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.LocalSessionTransactionDemo
~~~

Broker mặc định được tìm tại tcp://localhost:61616. Queue orders.local.tx.demo cần tồn tại hoặc broker phải cho phép tự tạo queue. Nếu broker dùng địa chỉ khác, đặt biến môi trường JMS_BROKER_URL trước khi chạy.

Output dự kiến khi broker nhận kết nối và hỗ trợ queue:

~~~text
[send] committed: Order #1024
[receive] first delivery: Order #1024
[transaction] receive rollback
[receive] redelivered: Order #1024
[receive] JMSRedelivered: true
[transaction] receive commit
[send] rolled back: Order #discard
[receive] after send rollback: none
~~~

### Phân tích ví dụ

**Hai Session độc lập:** producerSession và consumerSession đều transacted. Chúng dùng cùng một Connection và destination nhưng mỗi Session có giao dịch riêng.

**Commit phía producer:** producer gửi Order #1024 rồi gọi producerSession.commit(). Message được commit và có thể được consumer nhận.

**Rollback phía consumer:** consumer nhận message trong consumerSession rồi rollback. Broker giao lại message; header JMSRedelivered của lần nhận tiếp theo là true.

**Commit phía consumer:** consumer nhận lại message và commit. Message được xác nhận trong giao dịch nhận.

**Rollback phía producer:** producer gửi Order #discard nhưng rollback trước khi commit. Message gửi bị hủy và consumer không nhận được.

Ví dụ chứng minh phạm vi transaction của từng Session. Việc producerSession commit không commit consumerSession; mỗi Session có ranh giới độc lập.

Đây là ví dụ tích hợp với broker thật, không phải mock. Nếu chỉ chạy compile mà không có broker, chương trình có thể biên dịch nhưng không thể xác nhận redelivery hoặc transaction behavior thực tế.

## 11. Cấu hình broker cho redelivery và dead-letter

Rollback làm message có thể được giao lại. Nếu listener luôn thất bại với cùng message, broker có thể giao lại liên tục và tạo vòng lặp lỗi.

Trong môi trường thật, cấu hình chính sách redelivery:

- Số lần giao lại tối đa.
- Khoảng trễ giữa các lần thử.
- Backoff tăng dần nếu provider hỗ trợ.
- Dead-letter address/queue sau khi vượt giới hạn.
- Theo dõi message age và số lần redelivery.

JMS có thuộc tính JMSRedelivered để báo message đã được giao trước đó và bị giao lại. Một số provider còn cung cấp JMSXDeliveryCount để biết số lần giao.

Không nên dùng số lần redelivery làm khóa idempotency duy nhất. Hãy dùng event ID hoặc business operation ID ổn định để nhận diện thao tác nghiệp vụ.

## 12. Giao dịch và độ bền message là hai khái niệm khác nhau

Giao dịch Session quyết định nhóm thao tác gửi/nhận có được commit hay rollback. Delivery mode quyết định provider có lưu message bền vững qua sự cố hay không.

| Khái niệm | Câu hỏi được giải quyết |
|---|---|
| Session transaction | Các thao tác gửi/nhận trong nhóm có hoàn tất cùng nhau không? |
| PERSISTENT delivery mode | Provider có lưu message bền vững theo chính sách của nó không? |
| Durable Topic subscription | Subscription có tiếp tục tồn tại khi không có consumer không? |
| Acknowledgment | Khi nào provider xem message nhận đã được xác nhận? |

Một message được gửi trong transaction đã commit nhưng dùng NON_PERSISTENT vẫn không có cùng bảo đảm lưu trữ như message PERSISTENT khi provider gặp sự cố.

Ngược lại, PERSISTENT không thay thế transaction. Nếu một giao dịch bị rollback, message gửi trong giao dịch vẫn bị hủy theo quy tắc transaction.

## 13. Những lỗi thường gặp

**Quên commit:** message gửi trong Session transacted chưa được commit. Khi Session đóng, giao dịch đang mở bị rollback.

**Gọi rollback sau khi đã commit:** commit đã kết thúc giao dịch trước đó. rollback sau đó áp dụng cho giao dịch mới nếu có, không thể hoàn tác commit đã hoàn tất.

**Dùng commit() trên Session không transacted:** thao tác này không hợp lệ và có thể phát sinh IllegalStateException.

**Nghĩ mọi Session trên cùng Connection chung một transaction:** mỗi Session có giao dịch riêng. Commit một Session không tác động tới Session khác.

**Dùng CLIENT_ACKNOWLEDGE cùng SESSION_TRANSACTED:** hai chế độ loại trừ nhau. Với Session transacted, commit/rollback điều khiển acknowledgment và recovery.

**Nuốt exception rồi để listener hoàn tất:** container có thể commit message dù nghiệp vụ thất bại. Hãy để exception phù hợp truyền ra listener hoặc chủ động rollback theo thiết kế.

**Cho rằng rollback luôn tạo exactly-once:** rollback có thể làm message được giao lại. Listener cần idempotent để tránh tác động lặp.

**Cho rằng JMS transaction bao gồm database:** local JMS transaction chỉ quản lý Session. Dùng XA/JTA hoặc outbox/inbox khi cần phối hợp nhiều tài nguyên.

**Dùng JmsTransactionManager như transaction manager cho mọi tài nguyên:** JmsTransactionManager quản lý một JMS ConnectionFactory. Nó không thay thế transaction manager của database.

**Gọi Session.commit() bên trong JTA transaction:** khi Session do container/JTA quản lý, transaction coordinator chịu trách nhiệm commit/rollback. Không tự quản lý Session như một local transaction.

**Chỉ bật sessionTransacted mà không cấu hình redelivery:** broker vẫn cần chính sách giao lại và dead-letter để tránh poison message lặp vô hạn.

**Nhầm PERSISTENT với transacted:** delivery mode và transaction là hai cơ chế độc lập.

## 14. Thực hành tốt

1. Dùng Session transacted khi cần nhóm việc nhận và gửi message trong cùng một giao dịch JMS.
2. Commit sau khi nghiệp vụ trong phạm vi JMS hoàn tất.
3. Rollback khi xử lý thất bại và muốn broker giao lại message.
4. Không chia sẻ Session giữa nhiều thread.
5. Dùng JmsTransactionManager khi nhiều thao tác JmsTemplate cần cùng một local transaction.
6. Dùng sessionTransacted=true trên listener container khi cần rollback nếu listener thất bại.
7. Thiết lập redelivery limit và dead-letter policy ở broker.
8. Thiết kế listener idempotent vì message có thể được giao lại.
9. Tách rõ transaction JMS và transaction database.
10. Chọn XA/JTA khi thật sự cần atomic commit giữa nhiều XA resource.
11. Cân nhắc outbox/inbox khi muốn giảm độ phức tạp của distributed transaction.
12. Theo dõi transaction rollback, redelivery count, message age, dead-letter volume và lỗi commit.

## 15. Ghi nhớ

- sessionTransacted tạo giao dịch local trên một JMS Session.
- commit() xác nhận message đã nhận và hoàn tất message đã gửi trong cùng Session.
- rollback() hoàn tác message đã gửi và khiến message đã nhận có thể được giao lại.
- Các Session khác nhau có giao dịch độc lập, kể cả khi cùng dùng một Connection.
- Trong Session transacted, acknowledgment mode được quản lý bằng commit/rollback.
- JmsTemplate có thể dùng Session transacted qua setSessionTransacted(true).
- JmsTransactionManager quản lý giao dịch local cho một ConnectionFactory và bind Session vào thread.
- Listener container với sessionTransacted=true commit khi listener thành công và rollback khi listener ném exception.
- Giao dịch JMS local không tự bao gồm database hoặc HTTP.
- XA/JTA cần XA-capable resource và transaction coordinator; outbox/inbox là lựa chọn khác cho nhiều kiến trúc.
- Rollback có thể dẫn đến redelivery; cần idempotency và dead-letter policy.
- Transaction và persistent delivery mode giải quyết hai vấn đề khác nhau.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — JmsTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Spring Framework 6.2 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Jakarta Messaging 3.1 Specification — Transactions and message acknowledgment](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging 3.1 — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session)
