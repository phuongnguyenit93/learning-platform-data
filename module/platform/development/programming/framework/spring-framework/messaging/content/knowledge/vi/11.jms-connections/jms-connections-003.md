# SingleConnectionFactory và tái sử dụng kết nối trong Spring JMS

## 1. Vấn đề tạo và đóng tài nguyên JMS liên tục

JMS dùng một chuỗi đối tượng để gửi message:

~~~text
ConnectionFactory
    -> Connection
        -> Session
            -> MessageProducer
                -> send(...)
~~~

ConnectionFactory tạo kết nối tới JMS provider/broker. Connection đại diện cho kết nối đang hoạt động. Từ Connection, ứng dụng tạo Session; Session tạo MessageProducer, MessageConsumer và Message.

Nếu mỗi lần gửi đều tạo rồi đóng Connection, chi phí thiết lập kết nối có thể lớn, đặc biệt khi ứng dụng gửi nhiều message trong thời gian ngắn. Spring cung cấp các ConnectionFactory adapter để tái sử dụng tài nguyên. Một lựa chọn đơn giản là **SingleConnectionFactory**.

Class nằm trong package **org.springframework.jms.connection** và triển khai **jakarta.jms.ConnectionFactory**. Nó bọc một ConnectionFactory thật, sau đó cung cấp một Connection dùng chung cho nhiều lần gọi createConnection().

## 2. SingleConnectionFactory hoạt động như thế nào?

SingleConnectionFactory giữ một **physical JMS Connection** được tạo từ target ConnectionFactory. Mọi lời gọi createConnection() tiếp theo đều sử dụng connection vật lý đã được giữ lại, thay vì yêu cầu provider tạo một kết nối mới.

Các điểm chính:

- Có thể truyền target ConnectionFactory qua constructor hoặc cấu hình bằng **setTargetConnectionFactory(...)**.
- Connection vật lý thường được tạo lười ở lần sử dụng đầu tiên; có thể gọi **start()** để khởi tạo trước.
- Connection proxy trả về cho client bỏ qua lệnh **close()**. Vì vậy, khi JmsTemplate đóng connection sau một thao tác, connection vật lý vẫn được giữ để lần gửi tiếp theo sử dụng.
- Khi factory bị hủy, **destroy()** đóng connection vật lý đang được chia sẻ.
- **resetConnection()** đóng connection hiện tại; lần truy cập tiếp theo sẽ tạo lại connection.
- **setReconnectOnException(true)** cho phép factory đăng ký ExceptionListener để reset connection khi JMS provider thông báo JMSException.

Cần hiểu đúng phạm vi tái sử dụng: **SingleConnectionFactory chia sẻ Connection; nó không cache Session, MessageProducer hoặc MessageConsumer.**

### 2.1. Vì sao close() của client không đóng connection vật lý?

JmsTemplate quản lý vòng đời tài nguyên trong một thao tác gửi hoặc nhận. Sau khi hoàn tất, template đóng các tài nguyên mà nó đã lấy.

Nếu ConnectionFactory trả trực tiếp cùng một connection vật lý cho mọi client, lệnh close() từ một lần gọi có thể đóng kết nối mà các lần gọi khác đang cần. SingleConnectionFactory giải quyết việc này bằng một proxy connection có hành vi close() rỗng.

~~~java
Connection connection = singleConnectionFactory.createConnection();

try {
    // Dùng connection trong thao tác JMS.
}
finally {
    connection.close(); // Chỉ đóng proxy; connection dùng chung vẫn còn.
}
~~~

Khi ứng dụng kết thúc, factory mới đóng connection vật lý thông qua destroy() hoặc lifecycle của Spring container.

Điều này không có nghĩa mọi tài nguyên JMS đều được giữ mở. Session được tạo cho thao tác vẫn cần được đóng đúng cách. SingleConnectionFactory không bỏ qua Session.close().

### 2.2. Tái sử dụng không đồng nghĩa chia sẻ mọi đối tượng JMS

Jakarta Messaging cho phép nhiều thread sử dụng đồng thời một Connection. Tuy nhiên, Session được thiết kế để chỉ một thread sử dụng tại một thời điểm; MessageProducer và MessageConsumer cũng không được dùng đồng thời từ nhiều thread.

Vì vậy, một mô hình phù hợp là:

~~~text
                 SingleConnectionFactory
                           |
                  1 physical Connection
                    /      |      \
                   /       |       \
             Session A  Session B  Session C
             Thread A   Thread B   Thread C
~~~

Nhiều thao tác có thể chia sẻ Connection, nhưng mỗi thao tác hoặc luồng xử lý đồng thời cần Session phù hợp với vòng đời và transaction của nó. Không tự tạo một Session dùng chung cho nhiều thread chỉ vì Connection có thể chia sẻ.

## 3. Dùng với JmsTemplate

JmsTemplate là API gửi/nhận JMS cấp cao của Spring. Nó quản lý việc tạo và giải phóng tài nguyên trong mỗi thao tác. Sau khi được cấu hình, JmsTemplate thread-safe và có thể được inject vào nhiều bean.

Có thể bọc ConnectionFactory của JMS provider bằng SingleConnectionFactory:

~~~java
@Configuration
class JmsConfiguration {

    @Bean
    SingleConnectionFactory sharedJmsConnectionFactory(
            @Qualifier("nativeConnectionFactory")
            ConnectionFactory targetConnectionFactory) {

        SingleConnectionFactory factory =
            new SingleConnectionFactory(targetConnectionFactory);

        factory.setReconnectOnException(true);
        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(
            SingleConnectionFactory sharedJmsConnectionFactory) {

        return new JmsTemplate(sharedJmsConnectionFactory);
    }
}
~~~

nativeConnectionFactory là ConnectionFactory do JMS provider, JNDI hoặc cấu hình hạ tầng cung cấp. Đặt tên qualifier phù hợp với bean thật trong ứng dụng.

Khi gửi:

~~~java
@Service
class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.queue", event);
    }
}
~~~

Luồng tài nguyên có thể hiểu như sau:

1. JmsTemplate yêu cầu Connection từ SingleConnectionFactory.
2. Factory trả proxy trỏ tới connection vật lý dùng chung.
3. JmsTemplate tạo Session và producer phù hợp cho thao tác.
4. Message được gửi tới destination.
5. JmsTemplate đóng Session và các tài nguyên thuộc thao tác.
6. Lệnh đóng Connection trên proxy không đóng connection vật lý; lần gọi tiếp theo tiếp tục dùng connection đó.

Ví dụ trên giả định ứng dụng đã cấu hình JMS provider, destination và MessageConverter tương ứng. SingleConnectionFactory không tự tạo broker, queue hay converter.

## 4. Cấu hình và vòng đời connection

### 4.1. Các constructor và cách cấu hình

Có thể khởi tạo trực tiếp với target factory:

~~~java
SingleConnectionFactory factory =
    new SingleConnectionFactory(targetConnectionFactory);
~~~

Hoặc dùng bean-style:

~~~java
SingleConnectionFactory factory = new SingleConnectionFactory();
factory.setTargetConnectionFactory(targetConnectionFactory);
factory.afterPropertiesSet();
~~~

Target ConnectionFactory phải được cấu hình trước khi sử dụng. Với Spring container, khai báo factory dưới dạng bean để container quản lý vòng đời và gọi callback hủy khi context đóng.

### 4.2. Khởi tạo lười và khởi tạo trước

Mặc định, factory có thể tạo connection khi lần đầu cần dùng. Nếu muốn phát hiện lỗi kết nối sớm trong giai đoạn khởi động, có thể gọi start() hoặc initConnection():

~~~java
factory.start();
~~~

start() là lifecycle method được bổ sung từ Spring Framework 6.1. Nó khởi tạo shared connection. isRunning() cho biết hiện factory có underlying connection hay không.

stop() reset connection hiện tại; lần sử dụng sau có thể khởi tạo lại. Khi factory bị hủy, destroy() đóng underlying connection.

Không nên đóng physical connection bằng cách gọi close trên connection proxy nhận từ createConnection(). Việc đóng tài nguyên dùng chung thuộc trách nhiệm của factory.

### 4.3. Phục hồi khi có JMSException

Thuộc tính reconnectOnException điều khiển việc factory có reset connection khi nhận được thông báo lỗi từ provider hay không.

~~~java
factory.setReconnectOnException(true);
~~~

Mặc định của SingleConnectionFactory là false. Khi bật, factory đăng ký ExceptionListener của nó trên connection vật lý. Nếu provider gọi listener với JMSException, factory reset shared connection để có thể tạo lại khi cần.

Đây là cơ chế phục hồi connection theo thông báo của JMS provider. Nó không tự retry message, không xác nhận message đã được broker xử lý và không thay thế retry policy, transaction hoặc dead-letter flow của ứng dụng.

Khả năng phục hồi còn phụ thuộc provider có phát exception notification phù hợp hay không. Cần kiểm tra hành vi của broker/driver được triển khai và giám sát lỗi kết nối trong môi trường thật.

### 4.4. Client ID và ExceptionListener

SingleConnectionFactory cũng cho phép cấu hình client ID và ExceptionListener cho connection dùng chung:

~~~java
factory.setClientId("orders-publisher");
factory.setExceptionListener(applicationExceptionListener);
~~~

Nếu cần đặt client ID, hãy cấu hình trước khi connection được khởi tạo và tuân thủ yêu cầu của provider về thời điểm đặt client ID. Client ID thường liên quan tới durable subscription và phải duy nhất theo phạm vi mà broker quy định.

Khi bật reconnectOnException, Spring cần đăng ký listener nội bộ để phát hiện lỗi và có thể kết hợp listener do ứng dụng cung cấp. Hãy kiểm tra cách provider xử lý listener và durable subscription trước khi triển khai.

## 5. SingleConnectionFactory và CachingConnectionFactory

Spring có class **CachingConnectionFactory** kế thừa SingleConnectionFactory. Nó mở rộng việc tái sử dụng sang Session, MessageProducer và MessageConsumer.

| Khả năng | SingleConnectionFactory | CachingConnectionFactory |
|---|---|---|
| Chia sẻ physical Connection | Có | Có |
| Bỏ qua close() trên connection proxy | Có | Có |
| Cache Session | Không | Có |
| Cache MessageProducer | Không | Có, mặc định bật |
| Cache MessageConsumer | Không | Có, mặc định bật |
| Điều chỉnh session cache size | Không | Có |
| Tự bật reconnectOnException | Không, mặc định false | Có, mặc định true |

### 5.1. Session cache

CachingConnectionFactory mặc định cache một Session cho mỗi loại acknowledgment mode. Có thể tăng số lượng bằng setSessionCacheSize(...):

~~~java
CachingConnectionFactory factory =
    new CachingConnectionFactory(targetConnectionFactory);

factory.setSessionCacheSize(10);
factory.setCacheProducers(true);
factory.setCacheConsumers(true);
~~~

Giá trị sessionCacheSize là giới hạn cache cho từng loại Session: AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE, DUPS_OK_ACKNOWLEDGE và TRANSACTED. Vì cache tách theo acknowledgment mode, số Session thực tế có thể lên tới bốn lần giá trị cấu hình nếu ứng dụng sử dụng đủ các mode.

Khi cache đã đầy, Session được yêu cầu thêm có thể được tạo và giải phóng theo nhu cầu thay vì được giữ trong cache. Hãy đo tải đồng thời và số Session thực tế trước khi chọn kích thước cache.

### 5.2. Producer và consumer cache

CachingConnectionFactory cache producer theo Session và destination. Consumer được cache theo Session cùng các thuộc tính như destination, selector, noLocal và durable subscription name.

Muốn tái sử dụng Session, code truy cập JMS native phải đóng Session đúng cách. Với CachingConnectionFactory, Session.close() trên proxy có ý nghĩa trả Session về cache. Nếu không đóng Session, cache không thể tái sử dụng tài nguyên như dự kiến.

Consumer lấy từ Session cache có thể vẫn còn tồn tại ở provider cho tới khi Session bị loại khỏi cache. Điều này có thể ảnh hưởng tới selector hoặc durable subscription. Đặc biệt, việc đăng ký lại durable consumer cho cùng subscription trên cùng cached Session handle không được hỗ trợ; cần đóng và lấy lại Session phù hợp.

Producer và consumer cho TemporaryQueue hoặc TemporaryTopic không được cache.

## 6. So sánh với connection pool của provider và container

SingleConnectionFactory chỉ giữ một physical connection. Nó phù hợp khi muốn giảm việc tạo connection lặp lại trong test hoặc ứng dụng standalone có tải vừa phải và một kết nối dùng chung là đủ.

Nếu cần nhiều physical connection hoặc pool tài nguyên lớn hơn, cân nhắc:

- **CachingConnectionFactory:** cache thêm Session, producer và consumer ở tầng Spring.
- **Provider-specific pool:** dùng connection pool do JMS provider cung cấp, ví dụ PooledConnectionFactory của ActiveMQ.
- **Container-managed ConnectionFactory:** trong Jakarta EE/application server, dùng factory do container quản lý để nhận pooling và transaction integration của môi trường.

Không nên dùng một SingleConnectionFactory làm giải pháp pooling cho hệ thống cần nhiều connection vật lý song song. Một connection duy nhất có thể trở thành giới hạn throughput, số lượng session hoặc năng lực của broker.

Spring JMS listener container cũng có cơ chế dùng shared Connection bên trong mỗi container instance. Dùng SingleConnectionFactory kết hợp listener container thường có ý nghĩa khi muốn chia sẻ một connection giữa nhiều listener container, thay vì chỉ để một container chia sẻ connection nội bộ của nó.

## 7. Transaction và concurrency

### 7.1. Mỗi transaction vẫn có Session riêng

Spring JmsTransactionManager quản lý transaction cho một ConnectionFactory. Nó bind một cặp Connection/Session vào thread trong transaction. Khi dùng SingleConnectionFactory, Connection có thể là connection vật lý dùng chung, còn mỗi transaction có Session độc lập.

Điều này cho phép nhiều transaction sử dụng cùng một physical connection mà không phải chia sẻ một Session đang được thread khác sử dụng.

Không nhầm việc tái sử dụng connection với việc gộp transaction. SingleConnectionFactory không tự tạo transaction, không tự commit và không cung cấp XA.

### 7.2. Local transaction và XA

JmsTransactionManager thực hiện local JMS transaction cho một ConnectionFactory. Nếu cần transaction phân tán phối hợp JMS với nhiều resource, phải dùng JTA transaction manager cùng ConnectionFactory có hỗ trợ XA và cấu hình provider tương ứng.

SingleConnectionFactory không biến một connection thường thành XA connection. Hãy kiểm tra transaction manager, XA capability và cấu hình broker riêng.

### 7.3. Không chia sẻ Session giữa nhiều thread

Theo Jakarta Messaging specification:

- ConnectionFactory và Connection hỗ trợ concurrent use.
- Session, MessageProducer và MessageConsumer được thiết kế cho một thread sử dụng tại một thời điểm.

Do đó, không giữ Session trong singleton bean rồi dùng nó từ nhiều request thread. Dùng JmsTemplate hoặc transaction infrastructure để quản lý Session theo thao tác/thread. Nếu dùng JMS API trực tiếp, tạo và đóng Session theo đúng vòng đời, acknowledgment mode và transaction.

## 8. Ví dụ Java 17+ kiểm tra việc tái sử dụng physical connection

Ví dụ sau dùng dynamic proxy làm một ConnectionFactory giả lập. Không cần broker thật; chương trình đếm số lần target factory tạo physical Connection và số lần physical connection được đóng. Ví dụ kiểm tra vòng đời của SingleConnectionFactory, không thực hiện gửi message.

**Cấu trúc dự án**

~~~text
single-connection-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          SingleConnectionDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>single-connection-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/SingleConnectionDemo.java**

~~~java
package demo;

import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.connection.SingleConnectionFactory;

public class SingleConnectionDemo {

    public static void main(String[] args) throws Exception {
        AtomicInteger physicalConnectionsCreated = new AtomicInteger();
        AtomicInteger physicalConnectionsClosed = new AtomicInteger();

        Connection physicalConnection = (Connection) Proxy.newProxyInstance(
            Connection.class.getClassLoader(),
            new Class<?>[] { Connection.class },
            (proxy, method, arguments) -> {
                return switch (method.getName()) {
                    case "close" -> {
                        physicalConnectionsClosed.incrementAndGet();
                        yield null;
                    }
                    case "getClientID" -> "physical-connection-1";
                    case "toString" -> "physical-jms-connection";
                    case "isClosed" -> false;
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> null;
                };
            }
        );

        ConnectionFactory targetFactory = (ConnectionFactory)
            Proxy.newProxyInstance(
                ConnectionFactory.class.getClassLoader(),
                new Class<?>[] { ConnectionFactory.class },
                (proxy, method, arguments) -> {
                    if ("createConnection".equals(method.getName())) {
                        physicalConnectionsCreated.incrementAndGet();
                        return physicalConnection;
                    }
                    if ("toString".equals(method.getName())) {
                        return "demo-target-connection-factory";
                    }
                    return null;
                }
            );

        SingleConnectionFactory sharedFactory =
            new SingleConnectionFactory(targetFactory);

        Connection first = sharedFactory.createConnection();
        Connection second = sharedFactory.createConnection();

        System.out.println(
            "physicalConnectionsCreated=" + physicalConnectionsCreated.get()
        );
        System.out.println("firstClientId=" + first.getClientID());
        System.out.println("secondClientId=" + second.getClientID());

        first.close();

        System.out.println(
            "physicalClosesAfterClientClose=" + physicalConnectionsClosed.get()
        );

        Connection third = sharedFactory.createConnection();
        System.out.println("thirdClientId=" + third.getClientID());

        sharedFactory.destroy();

        System.out.println(
            "physicalConnectionsClosedAtDestroy=" +
            physicalConnectionsClosed.get()
        );
    }
}
~~~

Chạy từ thư mục single-connection-demo:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SingleConnectionDemo
~~~

**stdout**

~~~text
physicalConnectionsCreated=1
firstClientId=physical-connection-1
secondClientId=physical-connection-1
physicalClosesAfterClientClose=0
thirdClientId=physical-connection-1
physicalConnectionsClosedAtDestroy=1
~~~

Kết quả cho thấy target ConnectionFactory chỉ tạo một physical connection. Nhiều lần gọi createConnection() cùng truy cập connection đó. Gọi close() trên connection proxy không đóng connection vật lý; destroy() của SingleConnectionFactory mới đóng tài nguyên dùng chung.

Trong môi trường thật, target factory sẽ là JMS provider ConnectionFactory. Hãy cấu hình broker, credentials, TLS, destination và transaction riêng cho ứng dụng.

## 9. Lỗi thường gặp

1. **Cho rằng SingleConnectionFactory cache mọi tài nguyên:** class chỉ chia sẻ Connection. Muốn cache Session/producer/consumer, xem CachingConnectionFactory.
2. **Đóng connection dùng chung sau mỗi thao tác:** close trên proxy được bỏ qua. Hãy để factory quản lý physical connection.
3. **Không đóng Session:** Session vẫn cần được đóng đúng cách. Với CachingConnectionFactory, đóng Session là bước cần thiết để trả nó về cache.
4. **Chia sẻ một Session giữa nhiều thread:** Session và producer/consumer không thread-safe theo mô hình concurrent use của JMS.
5. **Dùng một connection cho mọi nhu cầu pooling:** SingleConnectionFactory chỉ giữ một physical connection; cân nhắc provider pool hoặc container-managed factory khi cần nhiều kết nối.
6. **Cho rằng reconnectOnException mặc định bật:** mặc định của SingleConnectionFactory là false. Bật rõ ràng nếu muốn factory phản ứng với ExceptionListener của provider.
7. **Nhầm reconnect với retry message:** reset connection không tự gửi lại message và không bảo đảm nghiệp vụ đã hoàn tất.
8. **Dùng client ID trùng:** durable subscription có thể phụ thuộc client ID; đặt ID đúng phạm vi và trước khi connection khởi tạo.
9. **Dùng SingleConnectionFactory thay XA:** local transaction và XA là hai cơ chế khác nhau. XA cần JTA và XA-capable provider factory.
10. **Không để Spring quản lý shutdown:** nếu tự tạo factory ngoài container, phải đảm bảo gọi destroy hoặc đóng lifecycle đúng lúc để giải phóng physical connection.
11. **Không xem xét listener container:** listener container đã có cơ chế shared connection nội bộ. Chỉ bọc thêm SingleConnectionFactory khi có lý do chia sẻ giữa nhiều container.
12. **Hiểu nhầm proxy identity:** mỗi lời gọi có thể trả một proxy wrapper; kiểm tra số physical connection hoặc trạng thái provider thay vì so sánh first == second.

## 10. Chọn cách tái sử dụng tài nguyên nào?

| Nhu cầu | Lựa chọn |
|---|---|
| Dùng chung một physical connection cho nhiều lần gọi JmsTemplate | SingleConnectionFactory |
| Cache thêm Session, producer và consumer | CachingConnectionFactory |
| Cần pool nhiều physical connection theo provider | Provider-specific pooled ConnectionFactory |
| Ứng dụng chạy trong Jakarta EE container | Container-managed ConnectionFactory |
| Cần transaction JMS cục bộ | JmsTransactionManager cùng ConnectionFactory phù hợp |
| Cần transaction phân tán có XA | JTA transaction manager và XA-capable ConnectionFactory |

## 11. Kết luận

SingleConnectionFactory là adapter giúp nhiều thao tác JMS dùng chung một physical Connection. Nó bỏ qua close() trên connection proxy và chỉ đóng connection vật lý khi factory được reset hoặc hủy. Mỗi thao tác vẫn có thể tạo Session riêng, phù hợp với quy tắc thread-safety của Jakarta Messaging.

Dùng SingleConnectionFactory khi cần tái sử dụng một connection trong test hoặc ứng dụng standalone. Nếu cần cache Session, producer và consumer, dùng CachingConnectionFactory; nếu cần nhiều connection vật lý hoặc pooling nâng cao, dùng factory do provider hoặc container quản lý. Luôn cấu hình rõ lifecycle, phục hồi lỗi và transaction theo yêu cầu của hệ thống.

## 12. Tài liệu tham khảo

- [SingleConnectionFactory — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/SingleConnectionFactory.html)
- [CachingConnectionFactory — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html)
- [Using Spring JMS — Spring Framework 6.2 Reference](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [JmsTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [JmsTransactionManager — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Jakarta Messaging 3.1 Specification — Multi-threading and Sessions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)