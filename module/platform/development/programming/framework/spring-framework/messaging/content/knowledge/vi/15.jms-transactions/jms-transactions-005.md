# JmsTransactionManager và một ConnectionFactory trong Spring JMS

## 1. JmsTransactionManager giải quyết vấn đề gì?

JMS có thể gửi message qua nhiều thao tác trong cùng một nghiệp vụ. Ví dụ, khi tạo đơn hàng, ứng dụng có thể gửi sự kiện đến orders.queue và đồng thời gửi một bản ghi thông báo đến audit.queue. Nếu lần gửi thứ hai thất bại, ứng dụng thường muốn hủy cả hai thao tác gửi.

Spring cung cấp JmsTransactionManager để quản lý local transaction cho một JMS ConnectionFactory. Khi transaction bắt đầu, manager lấy một JMS Connection và một Session có giao dịch, sau đó gắn cặp tài nguyên này vào thread hiện tại. Các thao tác JMS dùng cùng ConnectionFactory trong thread đó có thể tham gia vào cùng transaction.

JmsTemplate tự phát hiện Session được Spring gắn với thread và sử dụng lại Session đó. Vì vậy, ứng dụng có thể viết nhiều lệnh convertAndSend hoặc send trong một phương thức nghiệp vụ mà không phải tự tạo Connection, Session hay gọi commit.

Một điều cần hiểu rõ: JmsTransactionManager quản lý transaction cho một ConnectionFactory. Nó không tự phối hợp nhiều broker hoặc nhiều resource khác nhau thành một transaction phân tán.

## 2. Connection, Session và transaction được liên kết như thế nào?

Trong JMS, Connection đại diện cho kết nối tới provider. Session là ngữ cảnh làm việc chứa các thao tác gửi, nhận và transaction. Với một JMS transaction, các message được gửi hoặc nhận trên cùng Session sẽ được commit hoặc rollback cùng nhau.

JmsTransactionManager thực hiện các bước chính:

1. Bắt đầu transaction theo cấu hình Spring.
2. Tạo hoặc lấy Connection từ ConnectionFactory được quản lý.
3. Tạo Session có giao dịch.
4. Gắn Connection và Session vào thread hiện tại theo khóa ConnectionFactory.
5. Cho JmsTemplate hoặc code tích hợp Spring lấy lại Session đang được gắn.
6. Khi phương thức nghiệp vụ kết thúc, commit nếu thành công hoặc rollback nếu transaction bị đánh dấu rollback.
7. Giải phóng tài nguyên và bỏ liên kết thread sau khi transaction hoàn tất.

Có thể hình dung luồng như sau:

~~~mermaid
sequenceDiagram
    participant S as Service
    participant TM as JmsTransactionManager
    participant CF as ConnectionFactory
    participant JT as JmsTemplate
    participant JMS as JMS Provider

    S->>TM: begin transaction
    TM->>CF: create Connection
    CF-->>TM: Connection
    TM->>CF: create transacted Session
    CF-->>TM: Session
    TM->>TM: bind Session to current thread
    S->>JT: convertAndSend orders.queue
    JT->>TM: find transactional Session
    TM-->>JT: bound Session
    JT->>JMS: send message
    S->>JT: convertAndSend audit.queue
    JT->>JMS: send message using same Session
    S->>TM: method completes
    TM->>JMS: commit or rollback
    TM->>TM: unbind and release resources
~~~

Hai message có thể được gửi đến hai destination khác nhau nhưng vẫn thuộc cùng transaction nếu cả hai thao tác sử dụng cùng ConnectionFactory và cùng transaction-bound Session.

## 3. Vì sao phải dùng cùng một ConnectionFactory?

ConnectionFactory là khóa để Spring tìm tài nguyên JMS đang gắn với transaction. JmsTransactionManager đăng ký Connection và Session theo ConnectionFactory mà nó quản lý. Khi JmsTemplate cần Session, nó cũng tra cứu tài nguyên theo ConnectionFactory mà template đang sử dụng.

Vì vậy, cấu hình đúng cần bảo đảm:

- JmsTransactionManager nhận một ConnectionFactory.
- JmsTemplate nhận chính bean ConnectionFactory đó.
- Các thao tác JMS cần tham gia transaction chạy trong cùng thread và trong phạm vi transaction đang hoạt động.

Ví dụ, manager dùng bean jmsConnectionFactory nhưng JmsTemplate lại dùng một wrapper khác hoặc dùng trực tiếp providerConnectionFactory. Khi đó Spring có thể không tìm thấy Session được gắn cho khóa ConnectionFactory của manager. Lệnh gửi có thể tạo Session riêng và không nằm trong transaction mong muốn.

Dùng cùng broker hoặc cùng địa chỉ máy chủ chưa đủ. Hãy chia sẻ cùng Spring ConnectionFactory bean đã cấu hình cho transaction.

## 4. CachingConnectionFactory trong cấu hình standalone

Tài liệu JmsTransactionManager khuyến nghị mạnh mẽ dùng CachingConnectionFactory làm ConnectionFactory mục tiêu của manager. CachingConnectionFactory giữ một JMS Connection dùng chung và cache các Session, MessageProducer cùng MessageConsumer. Mỗi transaction vẫn có Session riêng; Session được trả về cache sau khi transaction hoàn tất.

Cách này giảm chi phí tạo Connection lặp lại và giúp quản lý vòng đời producer/consumer hiệu quả hơn. Giá trị sessionCacheSize mặc định là 1 cho mỗi loại Session acknowledgement. Khi ứng dụng có nhiều transaction đồng thời, có thể tăng cache size sau khi đo tải thực tế.

Cần phân biệt hai ý:

- Dùng chung một ConnectionFactory bean không có nghĩa mọi transaction dùng chung một Session.
- Các transaction đồng thời phải có Session riêng vì JMS Session không được dùng đồng thời từ nhiều thread.

Trong môi trường Jakarta EE đã có ConnectionFactory được container quản lý và pooling Connection/Session, hãy dùng resource do container cung cấp theo hướng dẫn của provider. Trong ứng dụng standalone, CachingConnectionFactory là lựa chọn Spring được JmsTransactionManager khuyến nghị làm target.

## 5. Cấu hình một ConnectionFactory dùng chung

Ví dụ sau giả định JMS provider đã cung cấp bean providerConnectionFactory. Bean này chứa cấu hình broker cụ thể như địa chỉ kết nối, credentials, TLS và các tùy chọn riêng của provider.

Ứng dụng tạo một CachingConnectionFactory duy nhất tên jmsConnectionFactory. Cả JmsTransactionManager và JmsTemplate đều inject bean đó.

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.CachingConnectionFactory;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class JmsTransactionConfiguration {

    @Bean
    public CachingConnectionFactory jmsConnectionFactory(
            @Qualifier("providerConnectionFactory")
            ConnectionFactory providerConnectionFactory) {

        CachingConnectionFactory connectionFactory =
            new CachingConnectionFactory(providerConnectionFactory);

        connectionFactory.setSessionCacheSize(10);
        return connectionFactory;
    }

    @Bean
    public JmsTransactionManager jmsTransactionManager(
            @Qualifier("jmsConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new JmsTransactionManager(connectionFactory);
    }

    @Bean
    public JmsTemplate jmsTemplate(
            @Qualifier("jmsConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new JmsTemplate(connectionFactory);
    }
}
~~~

Trong cấu hình này, jmsConnectionFactory là một bean Spring duy nhất. Manager và template cùng nhận bean đó thông qua Qualifier. Cấu hình sessionCacheSize bằng 10 chỉ là ví dụ cho tải đồng thời; hãy điều chỉnh theo số transaction và giới hạn tài nguyên của broker.

Không tạo hai CachingConnectionFactory riêng biệt, một cho manager và một cho template, dù cả hai cùng bọc một providerConnectionFactory. Hai wrapper là hai ConnectionFactory khác nhau đối với việc tra cứu tài nguyên transaction của Spring.

## 6. Gửi nhiều message trong một transaction

Sau khi cấu hình manager và template, có thể dùng transaction declarative qua @Transactional.

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publish(String orderId, boolean forceRollback) {
        jmsTemplate.convertAndSend("orders.queue", orderId);

        jmsTemplate.convertAndSend(
            "audit.queue",
            "created:" + orderId
        );

        if (forceRollback) {
            throw new IllegalStateException("Demo rollback");
        }
    }
}
~~~

Khi phương thức publish kết thúc bình thường, Spring commit JMS transaction. Cả hai message được commit trên cùng Session.

Nếu forceRollback là true, phương thức ném IllegalStateException. Đây là RuntimeException nên mặc định Spring đánh dấu transaction rollback. Hai thao tác gửi trong Session được rollback cùng nhau theo hợp đồng transaction của JMS provider.

Nếu phương thức ném checked exception, mặc định @Transactional không rollback chỉ vì checked exception. Hãy khai báo rollbackFor phù hợp nếu nghiệp vụ cần rollback trong trường hợp đó:

~~~java
@Transactional(
    transactionManager = "jmsTransactionManager",
    rollbackFor = Exception.class
)
public void publishWithCheckedFailure(String orderId) throws Exception {
    jmsTemplate.convertAndSend("orders.queue", orderId);
    throw new Exception("Rollback the JMS transaction");
}
~~~

Phương thức được gọi qua Spring proxy mới được áp dụng transaction interceptor. Tự gọi một phương thức @Transactional khác trong cùng object thường không đi qua proxy nên không mở transaction như mong đợi.

## 7. Transaction propagation và thread binding

Mặc định @Transactional dùng propagation REQUIRED. Nếu đã có transaction do chính JmsTransactionManager quản lý, lời gọi tiếp theo tham gia transaction hiện tại. Nếu chưa có, Spring mở transaction mới.

Tài nguyên JMS được gắn vào thread. Do đó, các lệnh JmsTemplate trong cùng thread và cùng phạm vi transaction có thể dùng lại Session. Nếu chuyển công việc sang @Async, executor, CompletableFuture hoặc tạo thread mới, transaction context không tự động đi theo thread mới.

Ví dụ:

~~~java
@Transactional(transactionManager = "jmsTransactionManager")
public void publish(String orderId) {
    jmsTemplate.convertAndSend("orders.queue", orderId);

    // Nếu gọi một tác vụ trên thread khác, tác vụ đó không tự động
    // tham gia Session transaction đang gắn với thread hiện tại.
}
~~~

Nếu một tác vụ bất đồng bộ cần transaction riêng, hãy mở transaction mới trong chính tác vụ đó bằng transaction manager phù hợp. Không truyền một JMS Session đang được transaction khác sử dụng sang thread khác.

## 8. Dùng JmsTransactionManager với API JMS thuần

JmsTemplate đã tự phát hiện Session gắn với thread. Với code cũ gọi trực tiếp ConnectionFactory.createConnection() rồi tạo Session, cách sử dụng đó không tự động tham gia transaction Spring.

Có hai lựa chọn:

1. Lấy transactional Session thông qua ConnectionFactoryUtils.getTransactionalSession.
2. Bọc ConnectionFactory bằng TransactionAwareConnectionFactoryProxy để code cũ tiếp tục dùng kiểu gọi JMS tiêu chuẩn nhưng có thể tham gia Spring-managed transaction.

Ví dụ khai báo proxy cho legacy code:

~~~java
@Bean
public TransactionAwareConnectionFactoryProxy transactionAwareConnectionFactory(
        @Qualifier("jmsConnectionFactory")
        ConnectionFactory connectionFactory) {

    return new TransactionAwareConnectionFactoryProxy(connectionFactory);
}
~~~

Proxy này dùng target là cùng jmsConnectionFactory mà JmsTransactionManager quản lý. Khi legacy code đóng Connection hoặc Session, proxy điều chỉnh thao tác close để không đóng tài nguyên transaction trước khi transaction hoàn tất.

Với code mới, nên ưu tiên JmsTemplate hoặc ConnectionFactoryUtils để Spring quản lý vòng đời Session rõ ràng.

## 9. JmsTransactionManager quản lý phạm vi nào?

JmsTransactionManager là local transaction manager cho một ConnectionFactory. Các destination khác nhau vẫn có thể nằm trong cùng transaction nếu chúng được truy cập qua cùng ConnectionFactory và cùng Session.

| Tình huống | Có thể nằm trong cùng local JMS transaction? |
| --- | --- |
| Gửi đến orders.queue và audit.queue qua cùng JmsTemplate | Có |
| Hai JmsTemplate cùng dùng một jmsConnectionFactory bean | Có |
| Manager dùng CachingConnectionFactory A, template dùng CachingConnectionFactory B | Không được bảo đảm; tài nguyên Spring được tra cứu theo ConnectionFactory |
| Gửi qua hai broker với hai ConnectionFactory khác nhau | Không |
| Gửi JMS và cập nhật database bằng JDBC trong cùng phương thức @Transactional của JmsTransactionManager | Database không tự động thuộc JMS transaction |
| Dùng JTA/XA với XA-capable JMS ConnectionFactory và XA database resource | Có thể phối hợp trong distributed transaction nếu hạ tầng được cấu hình đúng |

Nếu một phương thức gửi message qua hai ConnectionFactory khác nhau, JmsTransactionManager không thể commit hoặc rollback cả hai như một đơn vị nguyên tử. Mỗi factory cần transaction manager và transaction riêng, hoặc ứng dụng cần một giải pháp phân tán phù hợp.

## 10. Ranh giới giữa local JMS transaction và database transaction

Một JMS local transaction chỉ quản lý thao tác trên JMS Session. Nó không tự động bao gồm JDBC, JPA, filesystem hoặc một broker khác.

Ví dụ, nếu service cập nhật database rồi gửi JMS:

1. Database transaction có thể commit thành công.
2. JMS commit có thể thất bại sau đó.
3. Database đã lưu trạng thái nhưng message chưa được gửi.

Trường hợp ngược lại cũng có thể xảy ra nếu hai resource được commit theo thứ tự khác nhau. Việc đặt hai thao tác trong cùng một phương thức Java hoặc cùng một annotation @Transactional không biến chúng thành một transaction phân tán.

Nếu cần commit nguyên tử giữa JMS và database, dùng JtaTransactionManager cùng XA-capable ConnectionFactory và XA-aware database resource, đồng thời cấu hình transaction coordinator và broker đúng cách. XA có chi phí vận hành, transaction log và recovery cao hơn local transaction.

Với nhiều hệ thống, transactional outbox là lựa chọn phù hợp: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng database transaction, sau đó một publisher riêng gửi outbox sang broker. Consumer vẫn nên idempotent để xử lý duplicate.

## 11. JmsTransactionManager và listener container

JmsTransactionManager thường được dùng cho transaction do service mở qua @Transactional hoặc TransactionTemplate. Transaction nhận message trong listener container có cấu hình riêng.

Với DefaultMessageListenerContainer, nếu chỉ cần local JMS transaction cho mỗi lần listener xử lý message, có thể bật sessionTransacted. Khi listener ném exception, việc nhận message có thể rollback và broker redeliver theo chính sách của provider.

~~~java
@Bean
public DefaultMessageListenerContainer ordersListenerContainer(
        ConnectionFactory jmsConnectionFactory,
        Destination ordersQueue,
        MessageListener orderListener) {

    DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

    container.setConnectionFactory(jmsConnectionFactory);
    container.setDestination(ordersQueue);
    container.setMessageListener(orderListener);
    container.setSessionTransacted(true);
    return container;
}
~~~

Cấu hình sessionTransacted tạo local JMS transaction trong Session của container. Nó không tự phối hợp database transaction. Nếu cần message receipt, xử lý listener và database cùng commit theo XA, cấu hình container với JtaTransactionManager và XA-capable resources theo hướng dẫn Spring.

Đừng nhầm transaction do JmsTransactionManager mở cho service với transaction nội bộ do listener container quản lý. Chọn một chiến lược rõ ràng cho từng luồng nhận và gửi.

## 12. Transaction synchronization

JmsTransactionManager tắt transaction synchronization theo mặc định. Lý do là ứng dụng có thể dùng manager này cùng một transaction manager cho datastore, chẳng hạn DataSourceTransactionManager, và chỉ một manager được phép điều khiển Spring transaction synchronization tại một thời điểm.

Spring có cơ chế cho phép một local JMS transaction được đồng bộ với một Spring-managed transaction khác trong một số trường hợp. Tuy nhiên, JMS transaction sẽ commit sau transaction chính; đó không phải XA và không bảo đảm hai resource commit nguyên tử.

Khi cần tính nhất quán giữa nhiều resource, hãy xác định rõ cơ chế commit, rollback và recovery. Không dựa vào việc hai manager cùng chạy trong một call stack để suy ra chúng đang quản lý một transaction chung.

## 13. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Message vẫn được gửi dù service rollback | JmsTemplate dùng ConnectionFactory khác với manager | Inject cùng jmsConnectionFactory bean vào cả hai |
| Hai message chỉ có một message được rollback | Một lệnh gửi dùng Session hoặc ConnectionFactory riêng | Kiểm tra tất cả template và code JMS thuần |
| JmsTemplate không tìm thấy transaction | Không có transaction đang hoạt động, hoặc lệnh chạy trên thread khác | Kiểm tra @Transactional proxy, manager được chọn và thread thực thi |
| @Transactional không có tác dụng | Gọi nội bộ trong cùng object nên không qua proxy | Gọi qua Spring bean khác hoặc dùng TransactionTemplate |
| Database commit nhưng JMS rollback | Dùng local JMS transaction cùng JDBC transaction | Dùng outbox hoặc JTA/XA nếu cần atomic commit |
| JMS commit nhưng database rollback | Hai resource được quản lý độc lập | Thiết kế outbox/idempotency hoặc transaction phân tán |
| JMS provider lỗi khi commit | Driver có hành vi close producer/consumer không tương thích hoặc tài nguyên không được cache phù hợp | Dùng CachingConnectionFactory làm target theo khuyến nghị Spring và kiểm tra provider |
| Tài nguyên Session không được tái sử dụng | Session cache quá nhỏ hoặc code không đóng Session đúng cách | Điều chỉnh sessionCacheSize và đóng resource qua API đúng |
| Duplicate message sau sự cố JVM | Broker có thể redeliver khi commit chưa hoàn tất hoặc trạng thái xác nhận không rõ | Dùng event ID và xử lý idempotent |
| Nhiều transaction dùng chung Session | Code tự giữ và chia sẻ Session giữa thread | Để manager quản lý Session riêng cho mỗi transaction |

## 14. Checklist cấu hình production

- [ ] Chọn một ConnectionFactory bean làm tài nguyên JMS mà manager quản lý.
- [ ] Inject đúng cùng bean đó vào JmsTransactionManager và mọi JmsTemplate cần tham gia transaction.
- [ ] Với ứng dụng standalone, cân nhắc CachingConnectionFactory làm target theo khuyến nghị Spring.
- [ ] Chọn sessionCacheSize dựa trên concurrency và đo tải thực tế.
- [ ] Bật @EnableTransactionManagement nếu dùng @Transactional trong Spring Framework thuần.
- [ ] Chỉ định rõ transactionManager khi ứng dụng có nhiều PlatformTransactionManager.
- [ ] Giữ các thao tác cần chung transaction trong cùng thread.
- [ ] Xác định rõ rollback rules cho checked exception.
- [ ] Không dùng JmsTransactionManager để giả định JDBC hoặc broker khác cùng commit nguyên tử.
- [ ] Dùng JtaTransactionManager và XA resources khi thực sự cần distributed transaction.
- [ ] Cân nhắc transactional outbox và consumer idempotent để xử lý duplicate.
- [ ] Kiểm thử commit, rollback, broker restart, lỗi khi commit và giới hạn tài nguyên.
- [ ] Theo dõi transaction duration, commit/rollback failures, active sessions, connection pool và redelivery count.

## 15. Tài liệu tham khảo

- [Spring Framework 7.0.10 API — JmsTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Spring Framework 7.0.10 API — CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html)
- [Spring Framework 7.0.10 API — ConnectionFactoryUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/ConnectionFactoryUtils.html)
- [Spring Framework — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
