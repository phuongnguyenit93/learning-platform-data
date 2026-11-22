# JTA, XA và phối hợp JMS với cơ sở dữ liệu

Một ứng dụng thường cần thực hiện hai việc trong cùng một nghiệp vụ: cập nhật dữ liệu trong cơ sở dữ liệu và gửi một message JMS. Ví dụ, khi tạo đơn hàng, ứng dụng ghi đơn hàng vào database rồi phát event OrderCreated để các service khác xử lý.

Nếu hai thao tác dùng hai transaction cục bộ độc lập, có thể xảy ra trạng thái không nhất quán: database đã commit nhưng message chưa được gửi, hoặc message đã được gửi nhưng database rollback. **JTA và XA** cung cấp cơ chế phối hợp nhiều tài nguyên trong một global transaction để quyết định commit hoặc rollback thống nhất.

Trong Spring, **JtaTransactionManager** kết nối mô hình transaction của Spring với JTA. Khi JMS provider và database đều hỗ trợ XA, đồng thời được đăng ký đúng với cùng transaction manager, ứng dụng có thể đưa thao tác gửi/nhận JMS và thao tác database vào một transaction chung.

## 1. Bài toán dual-write giữa JMS và database

Giả sử service tạo đơn hàng thực hiện:

~~~text
1. INSERT đơn hàng vào database
2. Gửi OrderCreated vào JMS queue
~~~

Nếu database và JMS dùng transaction riêng, có hai cửa sổ lỗi:

| Thứ tự | Sự cố | Trạng thái có thể xảy ra |
|---|---|---|
| Database commit trước, JMS send sau | Broker mất kết nối sau khi database commit | Đơn hàng tồn tại nhưng không có event. |
| JMS send trước, database commit sau | Database rollback sau khi broker đã nhận message | Consumer nhận event cho đơn hàng không được lưu. |

Một local transaction chỉ bảo vệ tài nguyên thuộc transaction đó. Ví dụ:

- Transaction của JDBC bảo vệ thao tác trên một database connection.
- Transaction của JMS Session bảo vệ các thao tác gửi/nhận trong Session đó.
- Hai transaction riêng không tự động trở thành một transaction nguyên tử chỉ vì chúng nằm trong cùng một method Java.

Nếu ứng dụng cần database và JMS cùng thành công hoặc cùng thất bại, phải dùng một cơ chế phối hợp phù hợp. XA/JTA là một lựa chọn; transactional outbox là lựa chọn khác khi không thể hoặc không muốn triển khai XA.

## 2. JTA và XA là gì?

Hai khái niệm liên quan nhưng có trách nhiệm khác nhau.

### JTA: API và mô hình điều phối transaction

**Jakarta Transactions (JTA)** định nghĩa API chuẩn để ứng dụng và transaction manager làm việc với transaction toàn cục. Các thành phần quan trọng gồm:

- **UserTransaction:** API bắt đầu, commit hoặc rollback transaction trong các mô hình cho phép ứng dụng điều khiển ranh giới transaction.
- **TransactionManager:** thành phần quản lý transaction context, enlist resource và điều phối transaction.
- **Transaction:** đại diện cho một transaction context; các resource có thể được enlist vào context này.

Trong Spring, **org.springframework.transaction.jta.JtaTransactionManager** là implementation của Spring PlatformTransactionManager, ủy quyền việc điều phối cho JTA transaction manager của application server hoặc transaction coordinator được cấu hình.

JTA cho ứng dụng một cách làm việc thống nhất với transaction manager. JTA không tự biến một JMS ConnectionFactory hoặc DataSource thông thường thành XA resource.

### XA: hợp đồng phối hợp giữa transaction manager và resource manager

**XA** là giao thức/hợp đồng để transaction manager điều phối nhiều resource manager trong một global transaction. Một resource tham gia XA cung cấp đối tượng **XAResource** để transaction manager:

- Gắn resource vào transaction bằng start.
- Kết thúc phần công việc trên resource bằng end.
- Yêu cầu resource chuẩn bị commit bằng prepare.
- Ra lệnh commit hoặc rollback.
- Khôi phục transaction còn dang dở sau sự cố.

Trong bài toán JMS và database:

| Thành phần | Vai trò trong global transaction |
|---|---|
| JTA transaction manager | Tạo transaction toàn cục, enlist các resource và điều phối commit/rollback. |
| JMS provider XA | Enlist việc gửi hoặc nhận message qua XA resource của provider. |
| Database XA | Enlist các thay đổi JDBC qua XADataSource/XA resource. |
| Spring JtaTransactionManager | Kết nối annotation và API transaction của Spring với JTA manager. |

**JTA là tầng API/điều phối; XA là hợp đồng resource tham gia transaction phân tán.** Muốn có transaction JMS + database, cả hai resource phải hỗ trợ XA và được đăng ký với cùng transaction manager.

## 3. Two-phase commit (2PC) hoạt động thế nào?

XA thường dùng giao thức two-phase commit để điều phối nhiều resource manager.

~~~text
Ứng dụng
   |
   | begin global transaction
   v
JTA Transaction Manager
   |
   +------ enlist ------> JMS XA Resource
   |
   +------ enlist ------> Database XA Resource
   |
   | Phase 1: PREPARE
   |----------------------------->
   | hỏi từng resource có thể commit không?
   |
   | Phase 2: COMMIT hoặc ROLLBACK
   |----------------------------->
   v
Transaction hoàn tất
~~~

### Giai đoạn 1: Prepare

1. Transaction manager bắt đầu global transaction và tạo transaction identifier.
2. Ứng dụng thực hiện các thao tác database và JMS. Mỗi resource được enlist vào transaction.
3. Khi ứng dụng yêu cầu commit, transaction manager yêu cầu từng XA resource prepare.
4. Mỗi resource ghi trạng thái cần thiết vào log bền vững và trả lời kết quả:
   - **XA_OK:** resource đã chuẩn bị và có thể commit khi được yêu cầu.
   - **XA_RDONLY:** resource không có thay đổi cần commit; không cần tham gia phase commit tiếp theo.
   - Một kết quả rollback hoặc lỗi cho biết transaction không thể commit như dự định.

### Giai đoạn 2: Commit hoặc rollback

- Nếu tất cả resource có thay đổi đều đồng ý prepare, transaction manager ghi quyết định commit vào transaction log rồi yêu cầu các resource commit.
- Nếu một resource từ chối hoặc transaction bị đánh dấu rollback, transaction manager yêu cầu các resource rollback.
- Sau khi hoàn tất, transaction manager giải phóng trạng thái transaction.

Điểm quan trọng là resource đã trả lời prepare có thể giữ trạng thái transaction ở dạng in-doubt và chờ quyết định cuối cùng. Vì vậy, transaction manager phải lưu log đủ bền vững để khôi phục quyết định sau khi process hoặc máy chủ gặp sự cố.

### Khi transaction manager hoặc broker gặp sự cố

Nếu máy chủ dừng sau prepare nhưng trước khi mọi resource nhận được lệnh commit, transaction có thể ở trạng thái in-doubt. Khi hệ thống khởi động lại:

1. Transaction manager đọc transaction log đã lưu.
2. Nó thực hiện recovery scan với các XA resource đã đăng ký.
3. Resource trả về các Xid còn cần được xử lý.
4. Transaction manager đối chiếu log và tiếp tục commit hoặc rollback theo quyết định đã ghi.

Không xóa transaction log khi vẫn còn transaction cần recovery. Cần cấu hình recovery credentials, định danh resource ổn định và kết nối lại được tới đúng JMS provider/database.

### Heuristic outcome

Trong các tình huống lỗi nghiêm trọng, resource manager có thể tự đưa ra quyết định heuristic, ví dụ commit hoặc rollback ngoài quyết định mà transaction manager dự kiến. Khi đó có thể xuất hiện kết quả mixed: một resource đã commit trong khi resource khác rollback.

XA giảm rủi ro không nhất quán bằng điều phối và recovery, nhưng không loại bỏ nhu cầu giám sát transaction in-doubt, heuristic error và log recovery.

## 4. Điều kiện để JMS và database cùng tham gia XA

Chỉ cấu hình JtaTransactionManager là chưa đủ. Mỗi tài nguyên phải được cung cấp theo dạng XA và được transaction coordinator quản lý.

### JMS resource

JMS provider phải cung cấp XA support. Theo Jakarta Messaging, các API liên quan gồm XAConnectionFactory, XAConnection và XASession; provider dùng XAResource để tham gia global transaction.

Trong môi trường Jakarta EE, ứng dụng thường lấy một **JTA-aware, XA-capable ConnectionFactory** đã được application server cấu hình và đăng ký qua JNDI. Không nên tự tạo một ConnectionFactory client thông thường rồi giả định nó có thể enlist vào JTA.

### Database resource

Database driver/provider phải hỗ trợ XA, thường thông qua **XADataSource**. Application server hoặc XA connection pool tạo một DataSource được quản lý transaction để ứng dụng dùng qua JDBC.

Không nên tạo connection trực tiếp từ XADataSource trong từng method nghiệp vụ rồi tự gọi XAResource. Transaction manager và resource integration chịu trách nhiệm enlist, prepare, commit, rollback và recovery.

### Transaction manager và recovery

Transaction coordinator phải hỗ trợ XA và được cấu hình với cả JMS resource lẫn database resource. Cần kiểm tra:

- JMS ConnectionFactory có được đăng ký là XA resource không?
- DataSource có thực sự là XA/JTA-managed DataSource không?
- Cả hai resource có cùng tham gia một JTA transaction manager không?
- Transaction log được lưu bền vững ở đâu?
- Recovery có thể kết nối lại với broker và database sau restart không?
- Timeout của transaction, broker và database có tương thích không?

Một DataSource hoặc ConnectionFactory chỉ mang tên “XA” trong cấu hình chưa đủ; cần xác nhận integration thực tế và kiểm thử rollback/commit qua sự cố.

## 5. Phân biệt local transaction, JmsTransactionManager và JTA/XA

Spring có nhiều transaction manager, mỗi loại bảo vệ một phạm vi tài nguyên.

| Cơ chế | Phạm vi | Có phối hợp JMS và database nguyên tử không? |
|---|---|---|
| JMS Session transacted | Các thao tác JMS trong một Session | Không tự phối hợp database. |
| **JmsTransactionManager** | Một JMS ConnectionFactory | Không. |
| **DataSourceTransactionManager** | Một JDBC DataSource | Không tự phối hợp JMS. |
| **JpaTransactionManager** | Một EntityManagerFactory/database trong phạm vi hỗ trợ | Không tự phối hợp JMS. |
| **JtaTransactionManager + XA resources** | Nhiều XA resource manager trong một global transaction | Có, nếu tất cả resource được enlist đúng. |

Ví dụ, nếu một method gọi JmsTemplate và JdbcTemplate nhưng Spring chỉ dùng DataSourceTransactionManager, transaction đó không tự bao gồm việc gửi JMS. Nếu dùng JmsTransactionManager, database cũng không tự được đưa vào cùng transaction.

Kết hợp hai local transaction manager theo thứ tự gọi không tạo ra two-phase commit. Khi một bên commit thành công và bên kia thất bại, vẫn có cửa sổ không nhất quán.

Spring JmsTemplate có thể tham gia JTA transaction khi dùng JTA transaction manager cùng một JMS ConnectionFactory được cấu hình XA đúng cách. JmsTransactionManager phù hợp với transaction JMS cục bộ khi chỉ cần bảo vệ một ConnectionFactory.

## 6. Dùng JtaTransactionManager với JmsTemplate và JdbcTemplate

Trong Spring, code nghiệp vụ vẫn có thể dùng các abstraction quen thuộc:

- **@Transactional** đánh dấu ranh giới transaction.
- **JdbcTemplate** thực hiện database operation.
- **JmsTemplate** gửi JMS message.
- **JtaTransactionManager** điều phối transaction toàn cục.

Khi cả JdbcTemplate và JmsTemplate dùng các resource được quản lý XA bởi cùng transaction manager, hai thao tác có thể tham gia cùng một global transaction.

### Cấu hình resource

Ví dụ cấu hình dưới đây giả định application server đã cung cấp:

- Bean **xaDataSource**: DataSource được quản lý bởi JTA và backed bởi XADataSource.
- Bean **xaJmsConnectionFactory**: JMS ConnectionFactory có XA support và đã đăng ký với JTA transaction coordinator.

Tên bean chỉ là tên tham chiếu trong ví dụ. Cách khai báo JNDI và cấu hình pool phụ thuộc application server hoặc JMS/database provider.

~~~java
@Configuration
@EnableJms
@EnableTransactionManagement
public class XaMessagingConfiguration {

    @Bean
    public JtaTransactionManager jtaTransactionManager() {
        // Trong Jakarta EE, Spring tự dò JTA transaction manager của container.
        return new JtaTransactionManager();
    }

    @Bean
    public JdbcTemplate jdbcTemplate(
            @Qualifier("xaDataSource") DataSource dataSource
    ) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public JmsTemplate jmsTemplate(
            @Qualifier("xaJmsConnectionFactory")
            ConnectionFactory connectionFactory
    ) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jtaJmsListenerContainerFactory(
            @Qualifier("xaJmsConnectionFactory")
            ConnectionFactory connectionFactory,
            JtaTransactionManager jtaTransactionManager
    ) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setTransactionManager(jtaTransactionManager);

        return factory;
    }
}
~~~

Ở cấu hình này:

- JtaTransactionManager là transaction manager chung.
- JdbcTemplate dùng DataSource đã được quản lý bởi JTA.
- JmsTemplate dùng ConnectionFactory XA/JTA-aware.
- Listener container dùng cùng JtaTransactionManager để đưa cả thao tác nhận message và xử lý listener vào transaction.

**Không đặt sessionTransacted=true như một transaction cục bộ thay cho JTA.** Khi dùng external transaction manager, hãy cấu hình transactionManager trên DefaultJmsListenerContainerFactory và để JTA điều phối transaction.

Trong Jakarta EE, JtaTransactionManager mặc định có thể dò transaction infrastructure của container. Với ứng dụng standalone, cần cài đặt và cấu hình một JTA provider phù hợp, ví dụ một transaction manager nhúng có hỗ trợ XA và recovery. Spring không tự cung cấp transaction coordinator XA chỉ bằng cách thêm annotation.

## 7. Ví dụ producer: ghi database và gửi JMS trong cùng transaction

Giả sử service tạo một đơn hàng. Nó cần insert bản ghi và phát event. Nếu bất kỳ thao tác nào thất bại trước commit, cả hai resource phải rollback.

~~~java
package com.example.messaging;

import java.math.BigDecimal;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPublisher {

    private final JdbcTemplate jdbcTemplate;
    private final JmsTemplate jmsTemplate;

    public OrderPublisher(
            JdbcTemplate jdbcTemplate,
            JmsTemplate jmsTemplate
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jtaTransactionManager")
    public void createOrder(String orderId, BigDecimal total) {
        jdbcTemplate.update(
                "insert into orders(order_id, total, status) values (?, ?, ?)",
                orderId,
                total,
                "CREATED"
        );

        // String được Spring JMS SimpleMessageConverter chuyển thành TextMessage.
        jmsTemplate.convertAndSend(
                "orders.created",
                "OrderCreated:" + orderId
        );
    }
}
~~~

Nếu insert database thành công nhưng JMS send thất bại, exception làm transaction rollback; database insert không được commit. Nếu JMS send đã được resource chấp nhận nhưng database operation sau đó thất bại, quyết định rollback của global transaction cũng áp dụng cho JMS resource.

Khi method kết thúc bình thường, Spring yêu cầu JTA commit global transaction. Transaction manager điều phối các XA resource theo quy trình commit của nó.

Đoạn code là phần nghiệp vụ tích hợp. Để chạy thực tế cần bảng orders, XA DataSource, XA JMS ConnectionFactory, JTA transaction manager và destination orders.created đã được cấu hình.

## 8. Ví dụ consumer: nhận JMS và cập nhật database trong cùng transaction

Với message listener, cần đưa **cả thao tác nhận message và listener execution** vào transaction chung. Nếu chỉ đặt @Transactional trên một service được gọi từ listener nhưng listener container không tham gia JTA, việc acknowledge/consume JMS có thể vẫn nằm ngoài transaction database.

Spring **DefaultMessageListenerContainer** hỗ trợ external transaction manager. Khi được cấu hình với JtaTransactionManager và XA-aware ConnectionFactory, việc nhận message và thao tác database trong listener có thể thuộc cùng global transaction.

~~~java
package com.example.messaging;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final JdbcTemplate jdbcTemplate;

    public OrderCreatedListener(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @JmsListener(
            destination = "orders.created",
            containerFactory = "jtaJmsListenerContainerFactory"
    )
    public void handle(String body) {
        String prefix = "OrderCreated:";

        if (body == null || !body.startsWith(prefix)) {
            throw new IllegalArgumentException("Invalid order event");
        }

        String orderId = body.substring(prefix.length());

        int updated = jdbcTemplate.update(
                "update orders set status = ? where order_id = ?",
                "PROCESSED",
                orderId
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected one order row for " + orderId
            );
        }
    }
}
~~~

Khi listener hoàn tất bình thường, transaction manager commit database update và JMS receive theo cùng global transaction. Nếu listener ném exception, transaction rollback; database update bị hoàn tác và việc nhận message được rollback theo semantics của provider. Broker có thể giao lại message theo chính sách redelivery.

Không cần tự gọi acknowledge hoặc commit Session trong listener này. Listener container và JTA transaction manager điều phối vòng đời giao nhận.

### Vì sao phải cấu hình transaction manager trên listener container?

Một listener có thể được gọi trong một transaction database do annotation tạo, nhưng thao tác lấy message từ broker đã xảy ra trước transaction đó. Nếu muốn atomicity giữa consume và database update, container phải mở transaction trước khi nhận message và giữ transaction trong suốt listener execution.

Với Spring, **DefaultMessageListenerContainer** hỗ trợ transaction manager bên ngoài. **SimpleMessageListenerContainer** không hỗ trợ cùng cơ chế external transaction này. Hãy chọn đúng container factory và dùng ConnectionFactory XA/JTA-aware.

## 9. Điều gì được bảo vệ và điều gì nằm ngoài XA?

JTA/XA chỉ điều phối những resource thực sự được enlist trong global transaction.

| Thao tác | Có nằm trong XA transaction không? |
|---|---|
| JDBC update qua XA DataSource đã enlist | Có. |
| JMS send qua XA ConnectionFactory đã enlist | Có. |
| JMS receive qua listener container tham gia JTA | Có. |
| Ghi file trực tiếp vào filesystem | Không tự động. |
| Gọi HTTP API hoặc gửi email | Không tự động. |
| Ghi vào Redis hoặc một cache không hỗ trợ XA | Không tự động. |
| Gọi một database qua connection không được enlist | Không. |

Ví dụ, nếu transaction cập nhật database và gửi JMS rồi gọi thêm HTTP API, JTA không thể rollback tác động HTTP đã xảy ra. Không nên giữ transaction XA mở trong lúc chờ các dịch vụ mạng lâu hoặc không hỗ trợ XA.

Nếu có side effect ngoài XA, cần thiết kế idempotency, compensation hoặc workflow/Saga phù hợp.

## 10. Timeout, recovery và vận hành XA

XA giúp phối hợp transaction, nhưng làm tăng yêu cầu vận hành. Một transaction phân tán có thể giữ lock database và trạng thái message trong thời gian dài hơn local transaction.

### Cấu hình timeout

Cần đặt timeout hợp lý cho:

- JTA transaction manager.
- JDBC/database transaction và lock timeout.
- JMS provider/broker timeout.
- Pool connection và thời gian chờ lấy resource.

Transaction timeout quá ngắn có thể khiến công việc hợp lệ bị rollback. Timeout quá dài có thể giữ lock, giữ message và tiêu thụ connection trong thời gian lâu.

Tránh gọi HTTP, chờ người dùng, xử lý file lớn hoặc thực hiện công việc không giới hạn bên trong XA transaction.

### Recovery log

Transaction manager cần lưu log bền vững để biết transaction nào đã prepare và quyết định cuối cùng là gì. Vận hành phải bảo đảm:

- Log nằm trên storage bền vững, không bị xóa khi deploy hoặc restart.
- Mỗi transaction manager instance có định danh recovery ổn định.
- JMS provider và database vẫn có thể truy cập khi recovery chạy.
- Tài khoản recovery có quyền cần thiết.
- Các transaction in-doubt và heuristic outcome được giám sát.

Nếu khởi động hai transaction manager với cùng recovery identity trên cùng một tập resource mà không có cấu hình clustering phù hợp, recovery có thể gây xung đột. Tuân theo hướng dẫn của transaction manager và provider.

### Kiểm thử sự cố

Không chỉ kiểm thử đường đi thành công. Nên kiểm thử:

1. JMS broker không khả dụng khi producer gửi.
2. Database lỗi sau khi JMS resource đã tham gia transaction.
3. Listener ném exception sau khi đã update database.
4. Process dừng trong lúc transaction đang prepare/commit.
5. Transaction manager khởi động lại và thực hiện recovery.
6. Message bị redeliver và consumer xử lý lại cùng một business event.

Kiểm thử phải xác nhận dữ liệu database và trạng thái message nhất quán sau rollback, commit và recovery.

## 11. Chi phí và giới hạn của XA

XA mang lại atomic commit giữa các resource hỗ trợ XA, nhưng có chi phí:

- Thêm một vòng prepare và một vòng commit/rollback cho transaction nhiều resource.
- Transaction manager phải ghi log và thực hiện recovery.
- Resource có thể giữ lock hoặc trạng thái in-doubt trong thời gian dài.
- Phụ thuộc vào khả năng XA của broker, JDBC driver, pool và application server.
- Debug và vận hành phức tạp hơn local transaction.
- Một resource chậm có thể làm chậm toàn bộ global transaction.

Spring Framework cũng khuyến nghị cân nhắc local JMS transaction kết hợp phát hiện duplicate trong business logic nếu chấp nhận được, vì thường hiệu quả hơn việc bọc toàn bộ xử lý bằng XA. Chọn XA khi atomicity giữa các resource thực sự là yêu cầu bắt buộc và hạ tầng hỗ trợ đầy đủ.

## 12. Khi nào dùng Transactional Outbox thay cho XA?

Nếu database không hỗ trợ XA, JMS provider không có XA, hoặc tổ chức muốn tránh chi phí vận hành 2PC, có thể dùng **Transactional Outbox**.

Luồng:

~~~text
Application
    |
    | local DB transaction
    v
+-------------------------+
| orders table            |
| outbox_event table      |
+-------------------------+
    |
    | commit cùng một lần
    v
Outbox Publisher
    |
    | đọc event chưa gửi
    | publish qua JMS
    v
JMS Broker
    |
    v
Consumer (idempotent)
~~~

Trong một local database transaction, ứng dụng:

1. Ghi đơn hàng vào bảng orders.
2. Ghi event cần phát vào bảng outbox_event.
3. Commit cả hai cùng nhau.

Một publisher riêng đọc các outbox event chưa gửi, gửi chúng đến JMS rồi đánh dấu đã gửi. Nếu publisher crash sau khi broker nhận message nhưng trước khi đánh dấu sent, event có thể được gửi lại. Vì vậy consumer cần idempotency dựa trên event ID hoặc khóa nghiệp vụ ổn định.

Transactional Outbox cung cấp tính nhất quán giữa dữ liệu nghiệp vụ và ý định phát event trong database. Nó không tạo một transaction nguyên tử trực tiếp giữa database và JMS; thay vào đó, nó bảo đảm event được lưu bền vững để phát lại cho đến khi hoàn tất theo chính sách retry.

### So sánh XA và Outbox

| Tiêu chí | JTA/XA | Transactional Outbox |
|---|---|---|
| Cơ chế | Global transaction và 2PC. | Local DB transaction + publisher bất đồng bộ. |
| Atomicity DB + JMS | Có khi cả hai resource XA và enlist đúng. | Không commit nguyên tử cùng JMS; bảo toàn ý định gửi trong DB. |
| Hạ tầng | JTA manager, XA database và XA JMS provider. | Database transaction thông thường, outbox publisher và JMS. |
| Độ trễ | Gửi/nhận nằm trong transaction đồng bộ. | Event được phát sau khi transaction DB commit. |
| Vận hành | Recovery log, XA resource, transaction timeout. | Outbox cleanup, retry, publisher monitoring và idempotency. |
| Duplicate | Vẫn cần nghĩ đến recovery và side effect ngoài XA. | Publisher có thể gửi trùng; consumer phải idempotent. |
| Phù hợp | Cần atomic commit giữa các resource XA. | Hệ thống phân tán, broker/database không hỗ trợ XA hoặc muốn giảm coupling. |

Outbox thường phù hợp khi ứng dụng có thể chấp nhận độ trễ phát event và thiết kế consumer idempotent. Nếu cần điều phối nhiều bước nghiệp vụ dài qua nhiều service, cân nhắc Saga với các hành động bù trừ thay vì giữ một XA transaction lâu.

## 13. Những nhầm lẫn thường gặp

1. **“Có JtaTransactionManager là mọi resource tự động thành XA.”** Không đúng. JMS ConnectionFactory và DataSource phải có XA support, được quản lý và enlist với cùng transaction coordinator.
2. **“JmsTransactionManager phối hợp được database.”** Không đúng. Nó quản lý transaction cục bộ cho một JMS ConnectionFactory.
3. **“Gọi JdbcTemplate và JmsTemplate trong cùng method là đủ atomic.”** Không đúng nếu hai template dùng local transaction riêng hoặc chỉ một transaction manager được chọn.
4. **“@Transactional trên listener method tự bao gồm cả việc nhận message.”** Không nhất thiết. Listener container phải tham gia external JTA transaction để receive và listener execution cùng được điều phối.
5. **“sessionTransacted=true chính là XA.”** Không đúng. Đây là local JMS Session transaction. XA cần JTA manager và XA-aware ConnectionFactory.
6. **“Mọi database driver đều hỗ trợ XA.”** Không đúng. Cần kiểm tra driver, database, datasource pool và cấu hình provider.
7. **“XA bảo đảm mọi side effect bên ngoài đều rollback.”** Không đúng. HTTP, email, filesystem và resource không enlist không nằm trong global transaction.
8. **“2PC không thể gặp trạng thái in-doubt.”** Không đúng. Sự cố sau prepare có thể yêu cầu recovery; transaction log phải được bảo toàn.
9. **“XA loại bỏ hoàn toàn duplicate message.”** Không nên giả định như vậy cho toàn bộ hệ thống. Vẫn cần idempotency cho side effect ngoài XA, retry và các tình huống giao nhận thực tế.
10. **“Có thể tự gọi commit trên Session trong method @Transactional.”** Không nên. JTA transaction manager phải điều phối commit/rollback cho resource đã enlist.
11. **“Outbox và XA là cùng một cơ chế.”** Không đúng. Outbox lưu ý định phát event trong local DB transaction rồi phát bất đồng bộ; XA điều phối atomic commit trực tiếp giữa các XA resource.
12. **“Chỉ cần cấu hình transaction timeout ở Spring.”** Không đủ. Cần căn chỉnh timeout của JTA manager, broker, database, pool và recovery.

## 14. Ghi nhớ

- **JTA** cung cấp API và transaction manager cho global transaction.
- **XA** cho phép transaction manager phối hợp nhiều resource manager qua XAResource.
- **2PC** gồm prepare và commit/rollback; recovery log cần thiết khi có sự cố.
- Để phối hợp JMS với database, cả JMS ConnectionFactory và DataSource phải XA-capable/JTA-managed và enlist trong cùng transaction.
- **JtaTransactionManager** là cầu nối giữa Spring transaction abstraction và JTA.
- **JmsTransactionManager** chỉ quản lý local transaction của một JMS ConnectionFactory; nó không tự phối hợp database.
- Với consumer, dùng **DefaultMessageListenerContainer** được cấu hình external JTA transaction để receive và listener execution cùng thuộc transaction.
- XA có chi phí về latency, lock, transaction log và recovery; chỉ dùng khi yêu cầu atomicity xứng đáng với chi phí.
- **Transactional Outbox** là lựa chọn thực tế khi không triển khai XA; publisher retry và consumer idempotency là phần thiết yếu.
- Không dựa vào XA để rollback HTTP, email hoặc side effect không tham gia transaction.

Khi thiết kế giao dịch JMS với database, hãy xác định trước yêu cầu atomicity, khả năng XA của từng resource, nơi quản lý transaction và phương án recovery. Nếu hạ tầng không thể hỗ trợ XA đầy đủ, transactional outbox thường tạo ra một luồng phát event dễ vận hành hơn.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — DefaultMessageListenerContainer API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Jakarta Transactions 2.0 Specification](https://jakarta.ee/specifications/transactions/2.0/jakarta-transactions-spec-2.0.html)
- [Jakarta EE Tutorial — Jakarta Messaging Concepts and Transactions](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html)
