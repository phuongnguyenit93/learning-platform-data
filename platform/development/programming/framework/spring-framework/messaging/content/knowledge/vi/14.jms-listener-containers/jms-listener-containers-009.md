# ExceptionListener và ErrorHandler ở các tầng lỗi khác nhau

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt lỗi kết nối do JMS provider phát hiện với lỗi xảy ra khi xử lý một message.
- Giải thích hợp đồng của `jakarta.jms.ExceptionListener` và callback `onException(JMSException)`.
- Cấu hình `ExceptionListener` và `org.springframework.util.ErrorHandler` trên Spring JMS listener container.
- Hiểu vì sao một `JMSException` trong listener có thể được chuyển tới cả hai callback, theo thứ tự xác định.
- Nhận biết trường hợp chỉ gọi `ErrorHandler`, trường hợp chỉ gọi `ExceptionListener` và trường hợp gọi cả hai.
- Phân biệt callback báo lỗi với cơ chế rollback, acknowledgement, redelivery và recovery.
- Chọn cấu hình phù hợp cho `SimpleMessageListenerContainer`, `DefaultMessageListenerContainer` và `@JmsListener`.

## 1. Có nhiều tầng lỗi trong một luồng JMS

Một ứng dụng Spring JMS có thể gặp lỗi ở nhiều ranh giới:

~~~text
Ứng dụng
   |
   v
Spring MessageListenerContainer
   |
   +---- nhận message và gọi listener
   |          |
   |          +---- listener ném RuntimeException
   |          |          |
   |          |          v
   |          |      Spring ErrorHandler
   |          |
   |          +---- listener / invocation infrastructure ném JMSException
   |                     |
   |                     v
   |               Spring ExceptionListener
   |                     |
   |                     v
   |               Spring ErrorHandler
   |
   v
JMS Connection
   |
   +---- provider phát hiện lỗi kết nối nghiêm trọng
                |
                v
        jakarta.jms.ExceptionListener
                |
                v
        container/provider recovery
~~~

Hai tên callback dễ bị nhầm:

- **`ExceptionListener`** thuộc Jakarta Messaging, nhận `JMSException` và thường dùng để báo vấn đề ở cấp connection. Spring listener container cũng dùng cùng interface này để thông báo một `JMSException` phát sinh trong quá trình gọi listener hoặc infrastructure.
- **`ErrorHandler`** thuộc Spring Framework, nhận `Throwable` khi một exception không được xử lý thoát ra khỏi quá trình xử lý message.

Chúng có thể cùng được gọi cho một lỗi, nhưng trách nhiệm khác nhau. `ExceptionListener` không phải bộ bắt mọi lỗi nghiệp vụ; `ErrorHandler` không phải callback chuyên theo dõi tình trạng connection của JMS provider.

## 2. Jakarta ExceptionListener: lỗi ở cấp Connection

Interface:

~~~java
package jakarta.jms;

public interface ExceptionListener {
    void onException(JMSException exception);
}
~~~

Một JMS provider gọi `onException` khi provider phát hiện một vấn đề nghiêm trọng với `Connection` và ứng dụng đã đăng ký listener:

~~~java
Connection connection = connectionFactory.createConnection();

connection.setExceptionListener(exception -> {
    System.err.println(
            "JMS connection problem: "
                    + exception.getErrorCode()
                    + " - "
                    + exception.getMessage()
    );
});

connection.start();
~~~

Đây là thông báo bất đồng bộ. Nó hữu ích với consumer chỉ nhận message, vì thread ứng dụng có thể đang chờ message và không có một lời gọi JMS đồng bộ nào để trả lỗi kết nối cho caller.

### Những gì ExceptionListener cấp Connection báo

Ví dụ tùy provider:

- Connection bị mất do broker restart hoặc network disconnect.
- Broker đóng connection do lỗi giao thức hoặc lỗi phía server.
- Connection không còn khả dụng và provider cần thông báo cho client.
- Lỗi nghiêm trọng khác mà provider không có lời gọi đồng bộ phù hợp để trả về.

JMS specification yêu cầu provider nên thử tự khắc phục vấn đề kết nối trước khi thông báo cho client.

### Những gì nó không báo

`Connection.ExceptionListener` không phải nơi nhận mọi `JMSException`:

- Nếu một lời gọi như `connection.createSession()`, `session.createConsumer()` hoặc `producer.send()` ném `JMSException` trực tiếp, exception đó được trả về cho caller của lời gọi.
- Theo Jakarta Messaging specification, exception đã được ném từ một lời gọi API không được gửi thêm tới `Connection.ExceptionListener`.
- Lỗi validate dữ liệu nghiệp vụ như `IllegalArgumentException` không phải sự kiện connection failure.
- Callback không nhận payload hoặc business message bị lỗi; nó nhận một `JMSException` mô tả sự cố connection.

Một Connection tuần tự hóa việc gọi listener của chính nó: cùng một connection không chạy đồng thời nhiều lần `onException`. Tuy nhiên, nếu cùng một instance listener được đăng ký trên nhiều connection, các connection có thể gọi listener đồng thời trên nhiều thread.

### Việc cần làm trong callback

Nên giữ callback ngắn gọn:

~~~java
connection.setExceptionListener(exception -> {
    connectionHealth.markUnavailable(exception);
    metrics.increment("jms.connection.failure");
    alertPublisher.publishConnectionFailure(exception);
});
~~~

Không nên thực hiện vòng lặp reconnect hoặc công việc blocking kéo dài ngay trong callback. Hãy để provider hoặc listener container thực hiện recovery theo cơ chế đã cấu hình; callback chủ yếu ghi nhận trạng thái, log, metrics và kích hoạt cảnh báo.

## 3. Spring ErrorHandler: lỗi trong lúc xử lý Message

Spring dùng interface:

~~~java
package org.springframework.util;

@FunctionalInterface
public interface ErrorHandler {
    void handleError(Throwable t);
}
~~~

`ErrorHandler` nhận mọi `Throwable` không được listener xử lý và thoát ra khỏi quá trình xử lý một message. Vì nhận `Throwable`, nó có thể nhận:

- `IllegalArgumentException`, `IllegalStateException` hoặc exception nghiệp vụ.
- `MessageConversionException` hoặc lỗi từ code chuyển đổi.
- `JMSException` được ném từ listener hoặc invocation infrastructure.
- Runtime exception được bọc quanh một exception khác.

Spring JMS listener container cung cấp:

~~~java
container.setErrorHandler(error -> {
    logger.error("Uncaught error while processing a JMS message", error);
});
~~~

Mục đích thường gặp:

- Ghi log có stack trace.
- Đếm số lần listener thất bại.
- Gửi alert hoặc phát event vận hành.
- Phân loại lỗi để hỗ trợ điều tra.
- Ghi nhận metric theo loại exception.

`ErrorHandler` không tự động retry message, acknowledge message, rollback transaction hoặc đưa message vào dead-letter queue. Các quyết định đó thuộc transaction/acknowledgement của container và chính sách redelivery của broker.

### Mặc định nếu không đăng ký ErrorHandler

Nếu không cấu hình `ErrorHandler`, Spring listener container tự log lỗi ở mức cảnh báo khi listener thất bại. Theo mặc định, container không đẩy exception từ listener ngược lên JMS provider để provider coi listener đã thất bại.

Điều này rất quan trọng: provider có thể không biết listener đã ném exception. Nếu cần redelivery, hãy cấu hình transaction/acknowledgement phù hợp thay vì trông chờ provider nhìn thấy exception từ listener.

## 4. Khi nào gọi ExceptionListener, khi nào gọi ErrorHandler?

Với `AbstractMessageListenerContainer`, Spring quy định:

- `setExceptionListener(...)`: callback JMS `ExceptionListener` được gọi khi listener đã đăng ký hoặc invocation infrastructure ném `JMSException`.
- `setErrorHandler(...)`: callback Spring `ErrorHandler` được gọi cho mọi exception không được xử lý thoát ra trong quá trình xử lý một `Message`.
- Nếu exception đó là `JMSException`, Spring gọi `ExceptionListener` trước, rồi gọi `ErrorHandler`.

| Tình huống | Spring ExceptionListener | Spring ErrorHandler |
|---|---|---|
| Listener ném `IllegalArgumentException` | Không | Có |
| Listener ném `IllegalStateException` | Không | Có |
| Listener hoặc invocation infrastructure ném `JMSException` | Có, trước | Có, sau |
| JMS provider báo connection failure qua Connection callback | Có thể được container delegate | Không trực tiếp |
| Lời gọi JMS đồng bộ bên ngoài listener ném `JMSException` | Không tự động | Không tự động; caller phải xử lý |

Điểm dễ nhầm: Spring listener container có thuộc tính `setExceptionListener` mang cùng kiểu `jakarta.jms.ExceptionListener` với `Connection.setExceptionListener`, nhưng Spring còn chủ động gọi callback này cho lỗi `JMSException` từ listener/invocation infrastructure. Không suy luận rằng mọi lần `onException` đều do broker gọi.

### Runtime exception: chỉ ErrorHandler

~~~java
container.setExceptionListener(exception ->
        logger.error("JMSException callback: {}", exception.getMessage())
);

container.setErrorHandler(error ->
        logger.error("Message processing failed", error)
);

container.setMessageListener(message -> {
    throw new IllegalArgumentException("Invalid order payload");
});
~~~

Với lỗi `IllegalArgumentException`, Spring gọi `ErrorHandler`. Không có `JMSException` nên `ExceptionListener` không được gọi.

### JMSException: ExceptionListener trước, ErrorHandler sau

`SessionAwareMessageListener` là interface riêng của Spring cho phép listener nhận thêm JMS `Session` và khai báo `throws JMSException`:

~~~java
container.setMessageListener((SessionAwareMessageListener) (message, session) -> {
    throw new JMSException("Cannot process JMS message");
});
~~~

Với listener như trên, Spring gọi theo thứ tự:

~~~text
listener ném JMSException
          |
          v
ExceptionListener.onException(jmsException)
          |
          v
ErrorHandler.handleError(jmsException)
~~~

Nếu không cấu hình `ExceptionListener`, Spring bỏ qua bước callback này và vẫn gọi `ErrorHandler` nếu có. Nếu không cấu hình `ErrorHandler`, container tự log lỗi.

## 5. Cấu hình cả hai callback trên listener container

Có thể cấu hình trực tiếp với `DefaultMessageListenerContainer`:

~~~java
@Bean
public DefaultMessageListenerContainer ordersContainer(
        ConnectionFactory connectionFactory,
        MessageListener ordersListener,
        ErrorHandler jmsErrorHandler,
        ExceptionListener jmsExceptionListener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(ordersListener);

    container.setExceptionListener(jmsExceptionListener);
    container.setErrorHandler(jmsErrorHandler);

    // Transaction cục bộ cho việc nhận và xử lý message.
    container.setSessionTransacted(true);

    return container;
}
~~~

Hai bean callback có thể được định nghĩa như sau:

~~~java
@Bean
public ErrorHandler jmsErrorHandler() {
    return error -> {
        log.error("JMS listener processing failed", error);
        metrics.counter(
                "jms.listener.processing.errors",
                "exception",
                error.getClass().getSimpleName()
        ).increment();
    };
}

@Bean
public ExceptionListener jmsExceptionListener() {
    return exception -> {
        log.error(
                "JMS exception reported by listener/container: code={}, message={}",
                exception.getErrorCode(),
                exception.getMessage(),
                exception
        );
    };
}
~~~

Đặt `sessionTransacted=true` nếu cần rollback và redelivery khi listener thất bại. Việc cấu hình callback không thay thế transaction.

### Dùng với @JmsListener

Nếu ứng dụng dùng annotation-driven listener, có thể đặt hai callback trên `DefaultJmsListenerContainerFactory`. Các endpoint được tạo từ factory sẽ nhận cấu hình này:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            ErrorHandler jmsErrorHandler,
            ExceptionListener jmsExceptionListener) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setErrorHandler(jmsErrorHandler);
        factory.setExceptionListener(jmsExceptionListener);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        orderService.process(orderId);
    }
}
~~~

`IllegalArgumentException` trong ví dụ được gửi tới `ErrorHandler`. Nếu một listener dùng `SessionAwareMessageListener` hoặc invocation infrastructure ném `JMSException`, Spring còn gọi `ExceptionListener` trước ErrorHandler.

## 6. Connection ExceptionListener và Spring container ExceptionListener

Một ứng dụng có thể tự quản lý JMS Connection:

~~~java
Connection connection = connectionFactory.createConnection();

try {
    connection.setExceptionListener(exception -> {
        logger.error("Provider reported a connection failure", exception);
    });

    connection.start();

    // Tạo Session / Consumer và thực hiện công việc ở đây.
}
finally {
    connection.close();
}
~~~

Khi ứng dụng dùng listener container, container thường sở hữu connection, session và consumer. Không nên lấy connection nội bộ rồi tự thay `Connection.ExceptionListener` vì có thể ghi đè listener phục vụ recovery của container.

### SimpleMessageListenerContainer

`SimpleMessageListenerContainer`:

- Đăng ký container làm `ExceptionListener` trên shared JMS Connection.
- Khi provider báo connection failure, container gọi callback `ExceptionListener` do ứng dụng cấu hình.
- Mặc định, container cố gắng refresh shared connection và khởi tạo lại session/consumer thông qua `recoverOnException`.
- Có thể đặt `setRecoverOnException(false)` nếu muốn dựa vào cơ chế recovery của provider.

Ngoài đường connection callback này, khi listener/invocation infrastructure ném `JMSException`, lớp cha `AbstractMessageListenerContainer` cũng gọi user-configured `ExceptionListener` rồi `ErrorHandler`.

### DefaultMessageListenerContainer

`DefaultMessageListenerContainer` sử dụng mô hình polling bằng `MessageConsumer.receive(...)`, kết hợp TaskExecutor, concurrency và cơ chế recovery riêng. Nó vẫn cung cấp `setExceptionListener` để nhận `JMSException` từ listener/invocation infrastructure và `setErrorHandler` để nhận uncaught processing exception.

Cơ chế khôi phục connection của hai container có chi tiết triển khai khác nhau. Nếu dùng container do Spring quản lý, hãy để container sở hữu connection và cấu hình callback thông qua container hoặc factory.

## 7. ErrorHandler không quyết định acknowledgement và redelivery

Callback báo lỗi và transaction là hai cơ chế riêng.

Spring JMS listener container hỗ trợ các chế độ acknowledgement chính:

| Cấu hình | Ý nghĩa khi listener thất bại |
|---|---|
| `AUTO_ACKNOWLEDGE` | Hành vi phụ thuộc container; với DefaultMessageListenerContainer, message được acknowledge trước listener và không redelivery khi listener ném exception |
| `DUPS_OK_ACKNOWLEDGE` | Acknowledge lười; user exception không tự bảo đảm redelivery |
| `CLIENT_ACKNOWLEDGE` | Container acknowledge sau xử lý thành công; redelivery là best-effort khi listener lỗi |
| `sessionTransacted=true` | Acknowledge theo transaction; listener thất bại làm rollback và bảo đảm redelivery theo JMS transaction |

Với `DefaultMessageListenerContainer`, mặc định `AUTO_ACKNOWLEDGE` acknowledge trước khi listener thực thi. Vì vậy, message có thể đã được acknowledge dù listener ném exception. Với `SimpleMessageListenerContainer`, mặc định acknowledge sau listener nhưng user exception cũng không bảo đảm redelivery.

Khi cần xử lý tin cậy, Spring khuyến nghị dùng `sessionTransacted=true` nếu không cần transaction coordinator bên ngoài:

~~~java
container.setSessionTransacted(true);
~~~

Khi listener ném exception:

1. Container rollback JMS transaction.
2. Exception được chuyển tới callback phù hợp.
3. Broker có thể giao lại message theo transaction và redelivery policy.
4. Consumer có thể nhận cùng message thêm lần nữa.

Vì message có thể được giao lại, listener nên idempotent. Dùng `eventId` hoặc business key để phát hiện một event đã được xử lý; cấu hình giới hạn redelivery, backoff và dead-letter queue ở broker.

`ErrorHandler.handleError()` chỉ quan sát exception. Việc callback trả về bình thường không có nghĩa message đã thành công hoặc được commit. Container đã quyết định rollback/acknowledgement theo session và transaction.

### JMS và database không tự thành một transaction

`sessionTransacted=true` tạo local JMS transaction. Nếu listener đã commit database nhưng JMS rollback, message có thể được giao lại và thao tác database có thể lặp.

Muốn nhất quán giữa JMS và database, cần XA/JTA với provider hỗ trợ hoặc thiết kế Outbox/inbox và idempotency. Không giả định ErrorHandler có thể đồng bộ commit/rollback hai hệ thống.

## 8. Ví dụ Java 17 hoàn chỉnh: JMSException, hai callback và redelivery

Ví dụ dùng Java 17, Spring Framework 6.2.19 và ActiveMQ Classic 6.2.6. Broker chạy embedded trong cùng JVM. Listener cố ý ném `JMSException` ở lần nhận đầu tiên; transaction rollback khiến broker giao lại message. Ở lần tiếp theo, listener xử lý thành công.

Cấu trúc thư mục:

~~~text
jms-error-layer-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JmsErrorLayerDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-error-layer-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.19</spring-framework.version>
        <activemq.version>6.2.6</activemq.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>${activemq.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>${activemq.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
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

Tệp `src/main/java/demo/JmsErrorLayerDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.SessionAwareMessageListener;
import org.springframework.jms.listener.SimpleMessageListenerContainer;

public class JmsErrorLayerDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("jms-error-layer-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(
                        "vm://jms-error-layer-demo?create=false"
                );

        SimpleMessageListenerContainer container =
                new SimpleMessageListenerContainer();

        CountDownLatch errorHandled = new CountDownLatch(1);
        CountDownLatch messageProcessed = new CountDownLatch(1);
        AtomicBoolean failFirstAttempt = new AtomicBoolean(true);

        try {
            container.setConnectionFactory(connectionFactory);
            container.setDestinationName("orders.error.demo");
            container.setConcurrentConsumers(1);
            container.setSessionTransacted(true);

            container.setExceptionListener(exception ->
                    System.out.println(
                            "exceptionListener="
                                    + exception.getClass().getSimpleName()
                                    + ":" + exception.getMessage()
                    )
            );

            container.setErrorHandler(error -> {
                System.out.println(
                        "errorHandler="
                                + error.getClass().getSimpleName()
                                + ":" + error.getMessage()
                );
                errorHandled.countDown();
            });

            container.setMessageListener(
                    (SessionAwareMessageListener) (Message message, Session session) -> {
                        String orderId = ((TextMessage) message).getText();

                        if (failFirstAttempt.compareAndSet(true, false)) {
                            throw new JMSException(
                                    "simulated listener failure"
                            );
                        }

                        System.out.println("processed=" + orderId);
                        messageProcessed.countDown();
                    }
            );

            container.afterPropertiesSet();
            container.start();

            JmsTemplate sender = new JmsTemplate(connectionFactory);
            sender.convertAndSend("orders.error.demo", "ORD-1001");

            if (!errorHandled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "The error callbacks were not invoked"
                );
            }

            if (!messageProcessed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "The message was not processed after redelivery"
                );
            }
        }
        finally {
            container.stop();
            container.destroy();
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.JmsErrorLayerDemo
~~~

Kết quả stdout do chương trình tạo:

~~~text
exceptionListener=JMSException:simulated listener failure
errorHandler=JMSException:simulated listener failure
processed=ORD-1001
~~~

Giải thích:

1. `SimpleMessageListenerContainer` đăng ký listener trên queue và dùng local JMS transaction.
2. `SessionAwareMessageListener` ném `JMSException` ở lần giao đầu tiên.
3. Spring gọi `ExceptionListener.onException()` trước.
4. Spring gọi `ErrorHandler.handleError()` sau đó với cùng exception.
5. JMS transaction rollback; broker giao lại message.
6. Lần giao tiếp theo listener xử lý thành công và in `processed=ORD-1001`.

Ví dụ này minh họa nhánh `JMSException` phát sinh trong listener. Nó không mô phỏng broker mất kết nối. Nếu provider phát hiện connection failure, callback connection-level được gọi bất đồng bộ và `SimpleMessageListenerContainer` thực hiện recovery theo `recoverOnException`.

## 9. Cách quan sát và xử lý lỗi trong production

### Ghi log đủ ngữ cảnh

`ErrorHandler` chỉ nhận `Throwable`, không nhận trực tiếp JMS Message. Vì vậy nên ghi log correlation/event ID ở listener trước khi exception thoát ra:

~~~java
public void handle(Order order) {
    try {
        orderService.process(order);
    }
    catch (RuntimeException ex) {
        log.error(
                "Order processing failed: orderId={}, eventId={}",
                order.orderId(),
                order.eventId(),
                ex
        );
        throw ex;
    }
}
~~~

Trong ErrorHandler, log stack trace và loại exception. Tránh log toàn bộ payload nếu message chứa dữ liệu nhạy cảm.

### Phân loại lỗi

- Connection failure: cập nhật health/metrics, quan sát recovery và kiểm tra broker/network.
- Lỗi nghiệp vụ tạm thời: cân nhắc retry có giới hạn, backoff và idempotency.
- Lỗi dữ liệu vĩnh viễn: đưa vào DLQ/quarantine theo chính sách; tránh redelivery vô hạn.
- Lỗi cấu hình hoặc authentication: cảnh báo vận hành, sửa cấu hình/secret và kiểm tra reconnect.
- Lỗi từ ErrorHandler hoặc ExceptionListener: giữ callback an toàn; callback ném thêm exception có thể làm khó việc xử lý ban đầu.

### Không reconnect tùy tiện

Provider có thể đang tự phục hồi. `SimpleMessageListenerContainer` mặc định cố gắng refresh shared connection và consumer khi provider báo lỗi. Nếu dùng wrapper như `SingleConnectionFactory`, kiểm tra chính sách `reconnectOnException` và listener aggregation trước khi tự gắn thêm listener lên connection.

### Metrics nên theo dõi

- Số lần connection exception.
- Số listener processing error theo exception type.
- Số lần redelivery và message đã bị dead-letter.
- Queue depth và tuổi message lâu nhất.
- Thời gian xử lý message.
- Tần suất reconnect và thời gian phục hồi connection.

## 10. Lỗi thường gặp

1. **Dùng ExceptionListener để bắt lỗi validate nghiệp vụ.** Runtime exception từ listener thuộc ErrorHandler.
2. **Cho rằng Connection.ExceptionListener nhận mọi JMSException.** JMSException ném trực tiếp từ một lời gọi API được trả cho caller; provider listener chỉ báo sự cố connection bất đồng bộ theo contract.
3. **Cho rằng Spring container ExceptionListener chỉ nhận lỗi connection.** Spring còn gọi callback này cho JMSException từ listener/invocation infrastructure.
4. **Cho rằng ErrorHandler chỉ nhận JMSException.** Nó nhận Throwable từ mọi uncaught processing exception.
5. **Cho rằng JMSException chỉ gọi một callback.** Spring gọi ExceptionListener trước rồi ErrorHandler.
6. **Cho rằng ErrorHandler tự retry message.** Callback không điều khiển acknowledgement, rollback hoặc redelivery.
7. **Cho rằng callback trả về nghĩa là xử lý thành công.** Transaction có thể đã rollback trước khi callback được gọi.
8. **Dùng AUTO_ACKNOWLEDGE rồi mong redelivery khi listener lỗi.** Với DefaultMessageListenerContainer, mặc định acknowledge xảy ra trước listener; dùng sessionTransacted khi cần bảo đảm redelivery.
9. **Nuốt exception trong listener.** Container có thể coi listener đã hoàn tất bình thường và commit/ack message.
10. **Tự setExceptionListener lên connection do container quản lý.** Có thể ghi đè listener nội bộ phục vụ recovery. Cấu hình qua container hoặc factory.
11. **Làm việc nặng trong onException.** Callback connection failure là bất đồng bộ; giữ xử lý ngắn và tránh gọi lại connection đang lỗi.
12. **Bỏ qua idempotency.** Redelivery có thể khiến cùng message được xử lý nhiều lần; bảo vệ thao tác nghiệp vụ bằng event ID hoặc business key.
13. **Không cấu hình redelivery limit/DLQ.** Retry vô hạn có thể giữ message lỗi trong queue và làm giảm khả năng xử lý message khác.
14. **Cho rằng mọi container phục hồi giống nhau.** SimpleMessageListenerContainer và DefaultMessageListenerContainer có mô hình nhận và recovery khác nhau.

## 11. Checklist triển khai

- [ ] Xác định lỗi thuộc connection/provider hay listener/message processing.
- [ ] Dùng `jakarta.jms.ExceptionListener` cho thông báo JMSException ở cấp connection.
- [ ] Cấu hình `setExceptionListener` trên Spring listener container khi cần nhận JMSException từ listener/invocation infrastructure.
- [ ] Cấu hình `org.springframework.util.ErrorHandler` cho mọi uncaught processing exception.
- [ ] Nhớ JMSException đi qua ExceptionListener trước rồi ErrorHandler.
- [ ] Giữ callback ngắn gọn, không blocking và không ném exception mới.
- [ ] Không thay listener nội bộ trên connection do container quản lý.
- [ ] Chọn `sessionTransacted=true` nếu cần rollback/redelivery nhất quán.
- [ ] Cấu hình broker redelivery, backoff, giới hạn thử lại và DLQ.
- [ ] Thiết kế listener idempotent và lưu dấu event đã xử lý.
- [ ] Theo dõi connection health, listener errors, queue depth và redelivery.
- [ ] Kiểm thử riêng connection failure, RuntimeException, JMSException, rollback và redelivery.

## 12. Kết luận

`ExceptionListener` và `ErrorHandler` quan sát hai loại sự cố khác nhau. Jakarta `Connection.ExceptionListener` nhận thông báo bất đồng bộ khi JMS provider phát hiện vấn đề nghiêm trọng ở connection. Spring listener container dùng `setExceptionListener` để báo `JMSException` phát sinh từ listener hoặc invocation infrastructure; với lỗi này, Spring gọi ExceptionListener trước rồi ErrorHandler. `ErrorHandler` nhận mọi uncaught exception trong lúc xử lý message. Cả hai callback chỉ là điểm quan sát/xử lý lỗi; rollback, acknowledgement, redelivery và recovery vẫn phụ thuộc container, transaction và broker policy.

## Tài liệu tham khảo chính thức

- [Jakarta Messaging 3.1 Specification, §6.1.7 ExceptionListener](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf) — connection-level callback, tính bất đồng bộ, provider recovery và giới hạn không nhận exception đã được ném từ API call.
- [Spring Framework 6.2.19 Javadoc: AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html) — setExceptionListener, setErrorHandler, callback order và acknowledgement behavior.
- [Spring Framework 6.2.19 Javadoc: ErrorHandler](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/util/ErrorHandler.html) — functional interface `handleError(Throwable)`.
- [Spring Framework 6.2.19 Javadoc: SimpleMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html) — đăng ký container làm Connection ExceptionListener và recovery.
- [Spring Framework 6.2 Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html) — lựa chọn SimpleMessageListenerContainer và DefaultMessageListenerContainer.
- [Spring Framework 6.2 Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html) — MessageListener, SessionAwareMessageListener và listener container.
- [Spring Framework 6.2.19 Javadoc: AbstractJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html) — cấu hình ErrorHandler và ExceptionListener cho @JmsListener endpoints.
