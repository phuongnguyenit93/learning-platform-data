# JmsTemplate tham gia tài nguyên giao dịch của Spring

## 1. Vai trò của JmsTemplate trong Spring transaction

`JmsTemplate` là API cấp cao của Spring JMS để gửi message và nhận message đồng bộ. Template quản lý việc tạo, sử dụng và giải phóng Connection, Session, MessageProducer và MessageConsumer cho từng thao tác.

Khi một thao tác JMS chạy bên trong Spring transaction, `JmsTemplate` có thể dùng lại Session mà transaction manager đã gắn với thread hiện tại. Nhiều lần gọi template trong cùng transaction vì thế có thể cùng commit hoặc rollback.

`JmsTransactionManager` quản lý transaction cục bộ cho một `ConnectionFactory`. Khi transaction bắt đầu, manager lấy một JMS Connection và Session transacted, sau đó bind tài nguyên với thread hiện tại. `JmsTemplate` tự phát hiện và sử dụng Session đó.

~~~text
Spring transaction bắt đầu
        |
        v
JmsTransactionManager bind Connection + Session vào thread
        |
        +---- JmsTemplate.convertAndSend("orders", eventA)
        |
        +---- JmsTemplate.convertAndSend("audit", eventB)
        |
        v
Transaction commit hoặc rollback
~~~

Nếu transaction rollback, các thao tác gửi thuộc Session đó bị rollback theo transaction của JMS provider. `JmsTemplate` không commit riêng từng lần gửi khi đang dùng Session do Spring transaction quản lý.

## 2. Cơ chế tài nguyên transaction-bound

`JmsTransactionManager` bind cặp Connection/Session cho một ConnectionFactory cụ thể. Khi `JmsTemplate` thực hiện send hoặc receive, template dùng `ConnectionFactoryUtils` để lấy tài nguyên. Nếu thread đã có Session được bind cho đúng ConnectionFactory, template dùng lại Session đó. Nếu không có transaction, template tự quản lý tài nguyên theo cấu hình thông thường.

Khi transaction kết thúc:

- **Commit:** transaction manager commit JMS Session.
- **Rollback:** transaction manager rollback JMS Session.
- **Cleanup:** Connection/Session được giải phóng hoặc trả về cache/pool sau khi transaction kết thúc.

Tài nguyên được bind theo thread. Nếu method trong transaction gọi `@Async`, executor hoặc worker thread khác, task mới không tự dùng chung Session của thread gọi. Task nền cần transaction riêng thì phải tạo transaction boundary riêng. Không truyền Session qua thread.

### 2.1. Template và transaction manager phải dùng cùng ConnectionFactory

`JmsTemplate` và `JmsTransactionManager` phải nhận cùng một ConnectionFactory bean. Spring dùng ConnectionFactory làm resource key để tìm Session đã bind.

~~~java
@Bean
CachingConnectionFactory jmsConnectionFactory(
        @Qualifier("nativeConnectionFactory")
        ConnectionFactory nativeConnectionFactory) {

    CachingConnectionFactory factory =
        new CachingConnectionFactory(nativeConnectionFactory);
    factory.setSessionCacheSize(10);
    return factory;
}

@Bean
JmsTransactionManager jmsTransactionManager(
        CachingConnectionFactory jmsConnectionFactory) {
    return new JmsTransactionManager(jmsConnectionFactory);
}

@Bean
JmsTemplate jmsTemplate(
        CachingConnectionFactory jmsConnectionFactory) {
    return new JmsTemplate(jmsConnectionFactory);
}
~~~

Không tạo hai wrapper `CachingConnectionFactory` riêng quanh cùng một native factory cho template và manager. Hai wrapper là hai resource key khác nhau; template có thể không tìm thấy Session mà manager đã bind.

Spring khuyến nghị dùng `CachingConnectionFactory` với `JmsTransactionManager` để tái sử dụng Connection, Session và producer hiệu quả. `SingleConnectionFactory` cũng chia sẻ Connection, nhưng không cache Session như CachingConnectionFactory.

## 3. Cấu hình JmsTransactionManager

Trong cấu hình Spring thuần, bật transaction annotation và khai báo manager cùng template:

~~~java
@Configuration
@EnableTransactionManagement
public class JmsConfiguration {

    @Bean
    CachingConnectionFactory jmsConnectionFactory(
            @Qualifier("nativeConnectionFactory")
            ConnectionFactory nativeConnectionFactory) {

        CachingConnectionFactory factory =
            new CachingConnectionFactory(nativeConnectionFactory);
        factory.setSessionCacheSize(10);
        return factory;
    }

    @Bean
    JmsTransactionManager jmsTransactionManager(
            CachingConnectionFactory jmsConnectionFactory) {
        return new JmsTransactionManager(jmsConnectionFactory);
    }

    @Bean
    JmsTemplate jmsTemplate(
            CachingConnectionFactory jmsConnectionFactory) {
        return new JmsTemplate(jmsConnectionFactory);
    }
}
~~~

`nativeConnectionFactory` là ConnectionFactory do JMS provider, JNDI hoặc Spring Boot cung cấp. Cả `JmsTemplate` và `JmsTransactionManager` đều nhận bean `jmsConnectionFactory`.

Nếu ứng dụng có nhiều transaction manager, ví dụ một manager cho JDBC và một manager cho JMS, hãy đặt tên riêng và chỉ rõ manager ở transaction boundary. Spring Boot có thể tự cấu hình transaction infrastructure, nhưng cần xác nhận manager nào được chọn cho từng method.

## 4. Dùng TransactionTemplate

`TransactionTemplate` tạo ranh giới transaction tường minh trong code:

~~~java
@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;
    private final TransactionTemplate transactionTemplate;

    public OrderPublisher(
            JmsTemplate jmsTemplate,
            JmsTransactionManager jmsTransactionManager) {
        this.jmsTemplate = jmsTemplate;
        this.transactionTemplate =
            new TransactionTemplate(jmsTransactionManager);
    }

    public void publish(OrderCreated event) {
        transactionTemplate.execute(status -> {
            jmsTemplate.convertAndSend("orders.queue", event);
            jmsTemplate.convertAndSend("audit.queue", event);
            return null;
        });
    }
}
~~~

Hai lần `convertAndSend` dùng cùng Session của transaction. Khi callback kết thúc bình thường, template yêu cầu commit. Nếu callback ném RuntimeException hoặc đánh dấu rollback-only, manager rollback. Ví dụ giả định MessageConverter của ứng dụng hỗ trợ DTO OrderCreated.

Có thể đánh dấu rollback rõ ràng:

~~~java
transactionTemplate.execute(status -> {
    jmsTemplate.convertAndSend("orders.queue", event);
    if (event.isInvalid()) {
        status.setRollbackOnly();
    }
    return null;
});
~~~

Nếu callback bắt exception rồi chỉ ghi log, transaction manager có thể thấy callback kết thúc bình thường và commit. Khi nghiệp vụ thất bại, hãy để exception thoát ra hoặc gọi `status.setRollbackOnly()`.

## 5. Dùng @Transactional

Có thể dùng transaction khai báo:

~~~java
@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.queue", event);
        jmsTemplate.convertAndSend("audit.queue", event);
    }
}
~~~

Tên `jmsTransactionManager` phải khớp tên bean. Khi method được gọi qua Spring proxy, transaction interceptor bắt đầu transaction trước khi chạy method và commit khi method hoàn tất bình thường.

Mặc định, Spring rollback với `RuntimeException` và `Error`. Checked exception không tự gây rollback theo quy tắc mặc định. Dùng `rollbackFor` nếu cần:

~~~java
@Transactional(
    transactionManager = "jmsTransactionManager",
    rollbackFor = BusinessException.class
)
public void publish(OrderCreated event) throws BusinessException {
    jmsTemplate.convertAndSend("orders.queue", event);
    validateOrThrow(event);
}
~~~

Lưu ý:

- Method phải được gọi qua Spring-managed proxy.
- Self-invocation không đi qua proxy trong chế độ proxy mặc định.
- Không tự tạo service bằng `new` nếu muốn Spring áp dụng transaction advice.
- Khi có nhiều manager, chỉ rõ `transactionManager` để tránh chạy nhầm resource.

## 6. JmsTemplate dùng Session nào?

Khi một `PlatformTransactionManager` đang quản lý template, `JmsTemplate` luôn được cấp một transactional JMS Session. Các thuộc tính `sessionTransacted` và `sessionAcknowledgeMode` của template chủ yếu áp dụng khi template hoạt động ngoài Spring transaction.

| Trường hợp | Session và commit |
|---|---|
| Có JmsTransactionManager quản lý thread | Template dùng Session đã bind; manager commit/rollback |
| Không có Spring transaction, template mặc định | Session không transacted với AUTO_ACKNOWLEDGE |
| Không có Spring transaction, sessionTransacted=true | Mỗi thao tác template có local transacted Session riêng và commit/rollback theo thao tác |

Vì vậy, `jmsTemplate.setSessionTransacted(true)` không thay thế `JmsTransactionManager` khi cần gom nhiều lần gửi trong một transaction nghiệp vụ. Không tự gọi `commit()` hoặc `rollback()` trên Session do Spring quản lý.

## 7. Nhiều message trong một transaction

Nếu nhiều lần gửi dùng cùng ConnectionFactory và cùng transaction, chúng có thể commit hoặc rollback cùng nhau:

~~~java
@Transactional(transactionManager = "jmsTransactionManager")
public void publishOrder(OrderCreated order) {
    jmsTemplate.convertAndSend("orders.queue", order);
    jmsTemplate.convertAndSend("billing.queue", order);
    jmsTemplate.convertAndSend("audit.queue", order);
}
~~~

Nếu lần gửi thứ ba ném exception không được xử lý, các lần gửi trước trong cùng JMS transaction cũng rollback. Consumer không thấy một phần các message đó sau khi rollback thành công.

Cơ chế này chỉ áp dụng cho các thao tác JMS cùng transaction resource. Gửi qua ConnectionFactory khác không tự động tham gia transaction. Transaction cũng không bảo đảm consumer xử lý message đúng một lần; redelivery hoặc duplicate vẫn có thể xảy ra ở các ranh giới khác. Consumer nên idempotent khi nghiệp vụ yêu cầu.

## 8. Nhận message đồng bộ trong transaction

`JmsTemplate` cũng hỗ trợ receive đồng bộ. Nếu receive nằm trong transaction do `JmsTransactionManager` quản lý, thao tác nhận dùng Session transacted đó:

~~~java
transactionTemplate.execute(status -> {
    OrderCommand command =
        (OrderCommand) jmsTemplate.receiveAndConvert("orders.commands");

    if (command == null) {
        return null;
    }

    orderService.process(command);
    return null;
});
~~~

Khi commit, thao tác nhận được commit. Khi rollback, broker có thể giao lại message theo chính sách provider. Cấu hình receive timeout phù hợp để tránh chờ vô hạn khi queue không có message.

`JmsTemplate.receive()` là nhận đồng bộ; với xử lý message nền, dùng listener container như `DefaultMessageListenerContainer` phù hợp hơn.

## 9. Local JMS transaction và database

`JmsTransactionManager` quản lý local transaction cho một JMS ConnectionFactory. Nó không tự phối hợp transaction của JMS với transaction của database.

~~~text
JmsTransactionManager
    -> JMS Session transaction

DataSourceTransactionManager
    -> JDBC Connection transaction
~~~

Dùng hai local transaction manager riêng không tạo ra một transaction atomic bao trùm cả JMS và database. Một resource có thể commit trong khi resource còn lại thất bại.

Các lựa chọn:

- **JTA/XA:** dùng `JtaTransactionManager` cùng XA-capable JMS ConnectionFactory và XA datasource đã đăng ký với cùng transaction coordinator.
- **Outbox pattern:** ghi dữ liệu nghiệp vụ và outbox record trong cùng database transaction; publisher riêng đọc outbox rồi gửi message.
- **Eventual consistency:** thiết kế retry, idempotency và đối soát khi nghiệp vụ chấp nhận nhất quán cuối cùng.

Không gọi `JmsTransactionManager` là XA. Local JMS transaction chỉ quản lý resource JMS do manager phụ trách.

### 9.1. JTA/XA với JmsTemplate

Khi cần transaction phân tán, cấu hình `JtaTransactionManager` và ConnectionFactory hỗ trợ XA:

~~~java
@Bean
JtaTransactionManager transactionManager() {
    return new JtaTransactionManager();
}

@Transactional(transactionManager = "transactionManager")
public void createOrder(Order order) {
    orderRepository.save(order);
    jmsTemplate.convertAndSend("orders.queue", toEvent(order));
}
~~~

Ví dụ chỉ có ý nghĩa atomic khi datasource và JMS ConnectionFactory đều được cấu hình XA, đăng ký với cùng transaction coordinator và provider hỗ trợ thao tác cần thiết. Chỉ đổi tên transaction manager thành JTA là chưa đủ. XA có chi phí điều phối và transaction log; nếu không cần atomic commit đa resource, Outbox thường dễ vận hành hơn.

## 10. Dùng JMS API trực tiếp

Ưu tiên `JmsTemplate` vì template tự lấy transactional Session. Code gọi trực tiếp `ConnectionFactory.createConnection()` và `Connection.createSession()` không tự tìm Session mà `JmsTransactionManager` đã bind.

Có thể:

1. Dùng `ConnectionFactoryUtils.getTransactionalSession(...)` để lấy Session tham gia transaction.
2. Bọc target factory bằng `TransactionAwareConnectionFactoryProxy` nếu legacy code cần gọi ConnectionFactory/Connection/Session theo kiểu JMS thông thường.

`TransactionAwareConnectionFactoryProxy` nên là adapter ngoài cùng của chuỗi proxy. Với code mới, template thường giúp giảm lỗi vòng đời tài nguyên.

## 11. Tái sử dụng Connection và Session

`JmsTransactionManager` giữ một cặp Connection/Session trong suốt transaction. Session thuộc về thread và transaction hiện tại; không chia sẻ Session cho thread khác.

`CachingConnectionFactory` có thể dùng chung physical Connection, cache Session theo acknowledgment/transaction mode và cache producer/consumer theo cấu hình. Mỗi transaction vẫn có Session riêng. Chia sẻ Connection không có nghĩa các transaction dùng chung Session hoặc cùng commit.

Khi dùng cache, đóng proxy Session đúng vòng đời để Session được trả về cache. Không giữ Session trong singleton bean hoặc dùng chung một Session cho nhiều thread.

## 12. Kiểm thử transaction của JmsTemplate

Kiểm thử nên xác nhận commit và rollback với JMS provider thật hoặc broker nhúng:

1. Bắt đầu Spring JMS transaction.
2. Gửi message rồi đánh dấu rollback-only.
3. Kết thúc transaction.
4. Nhận thử message; kết quả phải là null nếu rollback thành công.
5. Gửi message trong transaction commit.
6. Nhận lại message và xác nhận payload đúng.

Mock `JmsTemplate` không chứng minh broker thực sự rollback hoặc commit message. Nên bổ sung kiểm thử exception, nhiều lần gửi trong cùng transaction và cấu hình provider thực tế.

## 13. Ví dụ Java 17+ chạy với embedded Artemis broker

Ví dụ dùng broker Artemis nhúng, `JmsTransactionManager`, `TransactionTemplate` và `JmsTemplate`. Chương trình gửi một message trong transaction rollback-only, sau đó gửi một message được commit và đọc kết quả.

**Cấu trúc dự án**

~~~text
jmstemplate-tx-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          JmsTemplateTransactionDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jmstemplate-tx-demo</artifactId>
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

**src/main/java/demo/JmsTemplateTransactionDemo.java**

~~~java
package demo;

import org.apache.activemq.artemis.core.config.impl.ConfigurationImpl;
import org.apache.activemq.artemis.core.server.embedded.EmbeddedActiveMQ;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class JmsTemplateTransactionDemo {

    public static void main(String[] args) throws Exception {
        EmbeddedActiveMQ broker = new EmbeddedActiveMQ();
        broker.setConfiguration(new ConfigurationImpl()
            .setPersistenceEnabled(false)
            .setSecurityEnabled(false)
            .addAcceptorConfiguration("netty", "tcp://127.0.0.1:61617"));
        broker.start();

        ActiveMQConnectionFactory connectionFactory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61617");

        try {
            JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
            jmsTemplate.setReceiveTimeout(500);

            JmsTransactionManager transactionManager =
                new JmsTransactionManager(connectionFactory);
            TransactionTemplate transactionTemplate =
                new TransactionTemplate(transactionManager);

            boolean[] resourceBound = new boolean[1];

            transactionTemplate.execute(status -> {
                resourceBound[0] =
                    TransactionSynchronizationManager.hasResource(connectionFactory);
                jmsTemplate.convertAndSend("tx.queue", "rolled-back");
                status.setRollbackOnly();
                return null;
            });

            String afterRollback =
                (String) jmsTemplate.receiveAndConvert("tx.queue");

            jmsTemplate.convertAndSend("tx.queue", "committed");

            String afterCommit =
                (String) jmsTemplate.receiveAndConvert("tx.queue");

            System.out.println("resourceBoundInsideTransaction=" + resourceBound[0]);
            System.out.println("messageAfterRollback=" + afterRollback);
            System.out.println("messageAfterCommit=" + afterCommit);
        }
        finally {
            connectionFactory.close();
            broker.stop();
        }
    }
}
~~~

Chạy từ thư mục `jmstemplate-tx-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JmsTemplateTransactionDemo
~~~

**Kết quả từ chương trình**

~~~text
resourceBoundInsideTransaction=true
messageAfterRollback=null
messageAfterCommit=committed
~~~

Giải thích:

- `resourceBoundInsideTransaction=true` cho thấy Spring đã bind resource của ConnectionFactory vào thread trong transaction.
- `messageAfterRollback=null` cho thấy message gửi trong transaction rollback-only không xuất hiện trong queue.
- `messageAfterCommit=committed` cho thấy message được commit thành công có thể nhận lại.

Ví dụ dùng Artemis nhúng với auto-create queue mặc định. Broker production cần cấu hình ConnectionFactory, credentials, TLS, destination và transaction policy riêng. Cảnh báo logging/native library có thể xuất hiện tùy môi trường; ba dòng trên là output do chương trình in ra.

## 14. Lỗi thường gặp

1. **Hai ConnectionFactory wrapper khác nhau:** template không tìm thấy Session mà transaction manager đã bind.
2. **Nghĩ JmsTemplate tự mở transaction nghiệp vụ:** không có manager thì mỗi thao tác theo cấu hình Session của template.
3. **Dùng sessionTransacted=true thay manager:** mỗi lần gọi có thể là transaction riêng, không gom nhiều lần gửi trong method.
4. **Gọi raw ConnectionFactory:** tạo Session trực tiếp không tự tham gia transaction-bound resource; dùng ConnectionFactoryUtils hoặc TransactionAwareConnectionFactoryProxy.
5. **Bắt và nuốt exception:** transaction có thể commit nếu callback kết thúc bình thường.
6. **Cho rằng checked exception luôn rollback:** dùng rollbackFor nếu cần rollback checked exception.
7. **Cho rằng JmsTransactionManager phối hợp database:** đây là local transaction cho một JMS ConnectionFactory; cần JTA/XA cho distributed atomic commit.
8. **Tự gọi commit/rollback trên Session của Spring:** để transaction manager điều khiển.
9. **Dùng Session chung giữa thread:** mỗi transaction cần Session riêng.
10. **Quên proxy @Transactional:** self-invocation hoặc object tạo bằng new có thể bỏ qua transaction advice.
11. **Không chỉ định manager khi có nhiều manager:** method có thể chạy nhầm resource.
12. **Nhầm send commit với consumer đã xử lý:** consumer có transaction và kết quả riêng.
13. **Chỉ dùng mock để test:** mock không chứng minh broker thực sự rollback/commit.
14. **Bỏ qua idempotency:** retry/redelivery có thể tạo message trùng.

## 15. Checklist cấu hình

1. Có `JmsTransactionManager` hoặc JTA transaction manager phù hợp chưa?
2. Template và manager có dùng cùng một ConnectionFactory bean không?
3. Có transaction boundary rõ ràng qua `TransactionTemplate` hoặc `@Transactional` không?
4. Method transactional có được gọi qua Spring proxy không?
5. Quy tắc rollback với RuntimeException và checked exception đã đúng yêu cầu chưa?
6. Có phân biệt local JMS transaction với database/XA transaction không?
7. ConnectionFactory có caching/pooling phù hợp với tải không?
8. Có tránh dùng Session đồng thời từ nhiều thread không?
9. Có kiểm thử cả commit và rollback với broker không?
10. Consumer có idempotent và giám sát redelivery/dead-letter không?

## 16. Kết luận

`JmsTransactionManager` bind một cặp Connection/Session của JMS ConnectionFactory vào thread. `JmsTemplate` tự phát hiện và sử dụng Session đó, nên nhiều thao tác gửi/nhận có thể commit hoặc rollback cùng một JMS transaction.

Để cơ chế hoạt động đúng, template và transaction manager phải dùng cùng ConnectionFactory bean, transaction boundary phải được Spring quản lý và exception phải được xử lý theo quy tắc rollback đã định. `JmsTransactionManager` chỉ quản lý local JMS transaction; muốn atomic giữa JMS và database cần JTA/XA hoặc một thiết kế như Outbox.

## 17. Tài liệu tham khảo

- [Spring Framework 6.2 — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [JmsTransactionManager — Spring Framework 6.2.18 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [JmsTemplate — Spring Framework 6.2.18 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [ConnectionFactoryUtils — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/ConnectionFactoryUtils.html)
- [TransactionAwareConnectionFactoryProxy — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/TransactionAwareConnectionFactoryProxy.html)
- [Spring Framework 6.2 — Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html)
- [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html)