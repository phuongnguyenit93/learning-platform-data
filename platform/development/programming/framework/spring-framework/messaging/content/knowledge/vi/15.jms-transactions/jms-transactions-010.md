# Giới hạn giao dịch cục bộ khi cập nhật đồng thời broker và database

## Mục tiêu

Một nghiệp vụ có thể cần cập nhật database và gửi message lên JMS broker. Ví dụ, khi tạo đơn hàng, ứng dụng vừa lưu đơn hàng vừa publish event `OrderCreated`. Khi nhận event, consumer có thể vừa cập nhật database vừa xác nhận message đã được xử lý.

Vấn đề là database và JMS broker là hai tài nguyên độc lập. Một giao dịch cục bộ (local transaction) chỉ bảo đảm commit hoặc rollback cho tài nguyên mà transaction manager quản lý. Dùng một local transaction cho database và một local transaction cho JMS không tạo ra một giao dịch nguyên tử chung.

Sau bài này, bạn có thể:

- Phân biệt local JMS transaction, local database transaction và global transaction.
- Hiểu phạm vi của `JmsTransactionManager`, `DataSourceTransactionManager` và `JtaTransactionManager`.
- Nhận diện các cửa sổ lỗi khi ghi database và publish message.
- Xử lý redelivery khi database đã commit nhưng JMS transaction chưa commit.
- Áp dụng transactional outbox, inbox/deduplication và idempotency.
- Xác định khi nào cần XA/JTA và các chi phí vận hành của nó.

## 1. Transaction bảo vệ tài nguyên nào?

Spring cung cấp một abstraction chung là `PlatformTransactionManager`, nhưng mỗi transaction manager thường gắn với một loại tài nguyên cụ thể.

| Transaction manager | Tài nguyên được quản lý | Phạm vi |
|---|---|---|
| `JmsTransactionManager` | Một JMS `ConnectionFactory` | Local JMS transaction |
| `DataSourceTransactionManager` | Một JDBC `DataSource` | Local database transaction |
| `JdbcTransactionManager` | Một JDBC `DataSource` | Local database transaction, có tích hợp xử lý lỗi JDBC |
| `JpaTransactionManager` | Một JPA `EntityManagerFactory` | Local JPA transaction |
| `JtaTransactionManager` | Các XA resource được enlist trong JTA coordinator | Global/distributed transaction |

`JmsTransactionManager` quản lý một JMS `ConnectionFactory`. Nó bind cặp JMS Connection/Session vào thread hiện tại để các thao tác qua `JmsTemplate` có thể tham gia cùng local JMS transaction đó.

`DataSourceTransactionManager` quản lý một JDBC DataSource. Các thao tác qua `JdbcTemplate` hoặc cơ chế truy cập JDBC tương thích sẽ tham gia transaction của DataSource tương ứng.

Hai transaction manager độc lập không tự động enlist tài nguyên của nhau. Nếu method dùng `@Transactional("dbTransactionManager")`, transaction được chọn là transaction của database. Điều đó không biến thao tác gửi JMS thành một phần nguyên tử của database transaction.

## 2. JmsTransactionManager và local JMS transaction

Spring cung cấp `JmsTransactionManager` để quản lý local transaction cho một JMS `ConnectionFactory`.

Ví dụ khai báo bean:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.JmsTransactionManager;

@Configuration
public class JmsTransactionConfiguration {

    @Bean("jmsTransactionManager")
    JmsTransactionManager jmsTransactionManager(
            ConnectionFactory connectionFactory) {
        return new JmsTransactionManager(connectionFactory);
    }
}
~~~

Khi `JmsTemplate` chạy trong transaction do `JmsTransactionManager` quản lý, template tự phát hiện JMS Connection/Session đã được bind vào thread và sử dụng tài nguyên đó.

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EventPublisher {

    private final JmsTemplate jmsTemplate;

    public EventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.events", event);
    }
}
~~~

Đây là service fragment cần có `JmsTemplate`, JMS provider và bean `jmsTransactionManager` đã cấu hình. Khi method hoàn tất bình thường, JMS transaction commit; nếu transaction bị rollback, thao tác gửi trong transaction đó cũng rollback theo semantics của provider.

Phạm vi này chỉ gồm JMS resource được quản lý bởi `JmsTransactionManager`. Một câu lệnh JDBC chạy trong cùng method không tự động thuộc JMS transaction.

## 3. Local database transaction

Database có transaction manager riêng. Ví dụ dùng JDBC:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
public class DatabaseTransactionConfiguration {

    @Bean("dbTransactionManager")
    DataSourceTransactionManager dbTransactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Một service cập nhật database:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void updateOrder(Order order) {
        orderRepository.save(order);
    }
}
~~~

Các thao tác database tham gia transaction của `dbTransactionManager`. Nếu method ném unchecked exception và transaction bị rollback, thay đổi database trong transaction đó được rollback.

Khi ứng dụng có nhiều transaction manager, cần chỉ rõ manager phù hợp trên `@Transactional` hoặc cấu hình manager mặc định có chủ đích. Chỉ dùng một annotation `@Transactional` không có nghĩa Spring tự động phối hợp mọi tài nguyên đang được inject vào service.

## 4. Vì sao hai local transaction không tạo thành một transaction nguyên tử?

Giả sử một nghiệp vụ cần thực hiện hai thao tác:

1. Lưu thay đổi vào database.
2. Gửi event tới broker.

Mỗi hệ thống có trạng thái commit riêng. Nếu ứng dụng commit một bên rồi lỗi trước khi bên còn lại commit, hai hệ thống có thể không đồng bộ.

~~~text
Ứng dụng
   |                         |
   v                         v
Database transaction     JMS transaction
   |                         |
   v                         v
DB commit/rollback        Broker commit/rollback

Hai transaction có kết quả độc lập nếu không có coordinator chung.
~~~

Ngay cả khi hai thao tác nằm trong cùng một method Java, ranh giới transaction vẫn do transaction manager quyết định. Thứ tự gọi hàm không tạo ra atomic commit giữa hai hệ thống.

## 5. Cửa sổ lỗi khi publish event sau khi cập nhật database

Có hai cách sắp xếp phổ biến, và mỗi cách có một cửa sổ lỗi riêng.

### 5.1. Gửi JMS trước khi database commit

Ví dụ method đang chạy trong database transaction:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void createOrder(Order order) {
    orderRepository.save(order);
    jmsTemplate.convertAndSend("orders.events", toEvent(order));
}
~~~

Nếu thao tác gửi JMS được broker chấp nhận nhưng database commit thất bại sau đó, consumer có thể nhận event cho một thay đổi database đã rollback.

Trình tự:

~~~text
1. DB ghi đơn hàng trong transaction chưa commit
2. JMS broker nhận OrderCreated
3. DB commit thất bại
4. DB rollback
5. Consumer vẫn có thể xử lý OrderCreated
~~~

Event đã ra khỏi broker không tự bị thu hồi khi database rollback.

### 5.2. Gửi JMS sau khi database commit

Ứng dụng có thể đăng ký callback sau commit hoặc dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` để chỉ publish khi database transaction đã commit.

Cách này tránh publish event khi database rollback, nhưng vẫn có một khoảng trống:

~~~text
1. DB commit thành công
2. Process dừng hoặc broker gặp lỗi
3. JMS send chưa hoàn tất
4. DB đã có dữ liệu nhưng event chưa được publish
~~~

Callback `AFTER_COMMIT` không phải một hàng đợi bền vững. Nếu process chết sau DB commit nhưng trước khi publish, event có thể bị mất. Cơ chế retry trong memory cũng không giải quyết được crash window này.

## 6. Cửa sổ lỗi khi nhận message rồi cập nhật database

Khi listener nhận message, Spring có thể dùng local JMS transaction bằng cách bật `sessionTransacted` trên listener container.

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Mỗi lần listener được gọi nằm trong một JMS transaction. Nếu listener ném exception, việc nhận message được rollback và broker có thể giao lại message. Việc gửi reply qua cùng JMS Session với `SessionAwareMessageListener` cũng thuộc JMS transaction đó.

Các thao tác database trong listener vẫn dùng database transaction riêng.

Một tình huống quan trọng:

~~~text
1. JMS broker giao message cho listener trong JMS transaction
2. Listener cập nhật database
3. Database commit thành công
4. JMS commit/acknowledgement thất bại
5. Broker redeliver message
6. Listener nhận lại message và có nguy cơ cập nhật database lần nữa
~~~

Đây là lý do Spring khuyến nghị phát hiện message trùng trong logic listener khi database đã commit nhưng JMS transaction chưa commit.

Nếu dùng chế độ acknowledgement không bảo đảm rollback khi listener lỗi, message có thể bị xác nhận trước khi database hoàn tất. Với yêu cầu reliability, hãy cấu hình transacted session và để exception cần retry truyền tới container; không nuốt exception sau khi database rollback.

## 7. Bảng tổng hợp các tình huống lỗi

| Luồng | Điểm lỗi | Kết quả có thể xảy ra | Cách bảo vệ |
|---|---|---|---|
| Outbound: gửi rồi DB commit | DB rollback sau khi broker nhận event | Event tồn tại nhưng thay đổi DB không tồn tại | Outbox |
| Outbound: DB commit rồi gửi | Broker lỗi hoặc process dừng trước send | DB đã đổi nhưng event chưa phát ra | Outbox |
| Inbound: DB commit rồi JMS commit | JMS commit thất bại sau DB commit | Message redelivery, nghiệp vụ có thể chạy lặp | Inbox/deduplication và idempotency |
| Inbound: JMS ack trước DB commit | DB rollback sau khi message đã ack | Message có thể mất khỏi luồng xử lý | JMS transacted session hoặc XA |
| Inbound: cả hai local tx | Process chết giữa hai lần commit | Một tài nguyên có thể commit, tài nguyên kia chưa commit | Inbox hoặc XA |
| Publish retry sau timeout | Broker đã nhận message nhưng producer không biết kết quả | Message có thể được gửi trùng | Event ID ổn định và consumer idempotent |

## 8. Giải pháp outbound: transactional outbox

Transactional outbox giải quyết dual-write khi database update cần phát event.

Thay vì ghi database rồi gửi JMS trực tiếp trong cùng luồng, ứng dụng ghi thay đổi nghiệp vụ và một bản ghi outbox trong **cùng một database transaction**.

~~~text
Business service
      |
      v
Một DB transaction
   |              |
   v              v
Business table   Outbox table
   |              |
   +------ commit-+
                  |
                  v
          Outbox relay / poller
                  |
                  v
              JMS broker
                  |
                  v
              Consumers
~~~

Nếu database transaction rollback, cả business row và outbox row đều rollback. Nếu commit thành công, event vẫn nằm bền vững trong outbox cho tới khi relay publish.

Ví dụ service:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void createOrder(CreateOrder command) {
        Order order = Order.create(command);
        orders.save(order);

        String eventId = UUID.randomUUID().toString();
        OrderCreated event = new OrderCreated(
            eventId,
            order.id(),
            Instant.now()
        );

        outbox.insertPending(eventId, "OrderCreated", event);
    }
}
~~~

Đây là service fragment; `Order`, `CreateOrder`, `OrderCreated`, `OrderRepository` và `OutboxRepository` là các kiểu của ứng dụng. Điều quan trọng là hai lệnh ghi phải dùng cùng database transaction.

Relay đọc các outbox record đã commit, gửi payload lên JMS, rồi đánh dấu record đã publish:

~~~java
public void publishPendingEvents() {
    for (OutboxRecord event : outbox.claimBatch()) {
        jmsTemplate.convertAndSend("orders.events", event.payload());
        outbox.markPublished(event.id());
    }
}
~~~

Đây là pseudocode mô tả luồng relay. Trong triển khai thực tế, `claimBatch()` cần cơ chế lease/locking để nhiều relay không tranh cùng record; `markPublished()` cần cập nhật trạng thái sau khi broker xác nhận send theo hợp đồng của provider.

Nếu broker đã nhận event nhưng process dừng trước khi `markPublished`, relay sẽ gửi lại event khi chạy tiếp. Vì vậy outbox thường cung cấp khả năng publish ít nhất một lần (at-least-once); consumer vẫn cần idempotency.

Không đánh dấu record published trước khi send. Nếu process dừng sau khi đánh dấu nhưng trước send, event sẽ bị mất khỏi hàng đợi outbox mà broker chưa nhận được.

### 8.1. Những trường nên có trong outbox

Một bảng outbox thường có:

| Trường | Mục đích |
|---|---|
| `event_id` | ID ổn định, duy nhất cho event |
| `aggregate_id` | ID entity hoặc aggregate phát sinh event |
| `event_type` | Loại event |
| `payload` | Nội dung event đã serialize |
| `created_at` | Thời điểm tạo event |
| `status` | Pending, claimed, published hoặc trạng thái tương đương |
| `attempt_count` | Số lần relay thử gửi |
| `next_attempt_at` | Thời điểm được phép thử lại |
| `published_at` | Thời điểm publish thành công |

Nếu cần giữ thứ tự event của một aggregate, hãy lưu sequence/version và thiết kế relay để phát đúng thứ tự trong phạm vi aggregate. Thứ tự giữa nhiều aggregate thường không cần được bảo đảm toàn cục.

## 9. Giải pháp inbound: inbox và deduplication

Với message đầu vào, consumer có thể lưu ID message đã xử lý vào bảng inbox cùng transaction với cập nhật nghiệp vụ.

Bảng inbox thường có unique constraint trên `event_id`. Thao tác ghi inbox phải có tính nguyên tử để hai lần xử lý đồng thời cùng một event không cùng vượt qua bước kiểm tra trùng.

~~~text
JMS listener nhận event
        |
        v
DB transaction
   |                 |
   v                 v
Insert event_id     Update business data
   |                 |
   +------- commit --+
        |
        v
Listener method trả về
        |
        v
JMS local transaction commit
~~~

Ví dụ listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class OrderEventListener {

    private final InboxRepository inbox;
    private final OrderProjection orders;

    public OrderEventListener(
            InboxRepository inbox,
            OrderProjection orders) {
        this.inbox = inbox;
        this.orders = orders;
    }

    @JmsListener(destination = "orders.events")
    @Transactional(transactionManager = "dbTransactionManager")
    public void handle(OrderCreated event) {
        boolean firstDelivery = inbox.tryInsert(event.eventId());

        if (!firstDelivery) {
            return;
        }

        orders.apply(event);
    }
}
~~~

Đây là listener fragment cần có repository và database transaction manager. `tryInsert` phải dựa trên unique constraint hoặc câu lệnh insert-if-absent có tính nguyên tử; cách kiểm tra `exists` rồi insert riêng rẽ có thể gặp race condition.

Kết hợp listener với factory bật `sessionTransacted=true`. Khi DB transaction commit nhưng JMS commit thất bại, broker có thể redeliver. Lần nhận lại, inbox phát hiện `event_id` đã tồn tại nên không áp dụng nghiệp vụ lần nữa.

Nếu DB transaction thất bại, exception cần được truyền ra để transaction rollback và JMS container rollback việc nhận message. Với checked exception, cấu hình `rollbackFor` hoặc chuyển thành unchecked exception khi phù hợp với chính sách xử lý.

Inbox bảo vệ các thay đổi nằm trong cùng DB transaction. Nếu listener còn gọi API HTTP, gửi email hoặc tạo side effect ở hệ thống khác, các side effect đó cần idempotency hoặc một outbox riêng.

### 9.1. Chọn message ID ổn định

Có thể dùng application event ID trong payload hoặc JMS property. Nên dùng ID do producer tạo và giữ nguyên qua các lần retry.

Không nên mặc định chỉ dùng `JMSMessageID` nếu producer retry có thể tạo message mới với JMSMessageID khác nhau cho cùng một nghiệp vụ. Một event ID ổn định giúp consumer nhận diện cùng một sự kiện qua nhiều lần gửi.

Cần có chính sách lưu và dọn inbox record. Không xóa ID trước khi hết thời gian có thể redeliver hoặc replay message.

## 10. XA/JTA: một global transaction cho nhiều resource

Khi yêu cầu nghiệp vụ bắt buộc database update và JMS receipt/send phải commit hoặc rollback cùng nhau, có thể dùng XA với JTA.

JTA transaction coordinator điều phối các XA resource tham gia transaction, ví dụ:

- XA-capable JMS ConnectionFactory.
- XA-capable JDBC DataSource.
- `JtaTransactionManager` của Spring kết nối với transaction coordinator.

Quy trình two-phase commit ở mức khái quát:

~~~text
Application
    |
    v
JTA transaction coordinator
    |
    +---- XA resource: Database
    |
    +---- XA resource: JMS broker

Phase 1: PREPARE
    Coordinator hỏi mỗi resource có thể commit không.
    Các resource ghi trạng thái prepared vào transaction log.

Phase 2: COMMIT hoặc ROLLBACK
    Coordinator quyết định kết quả chung và gửi lệnh tới các resource.
~~~

Cấu hình Spring khái quát:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.jta.JtaTransactionManager;

@Configuration
public class GlobalTransactionConfiguration {

    @Bean
    JtaTransactionManager transactionManager() {
        return new JtaTransactionManager();
    }
}
~~~

Ví dụ listener container tham gia transaction do JTA quản lý:

~~~java
@Bean
DefaultJmsListenerContainerFactory xaListenerFactory(
        ConnectionFactory xaConnectionFactory,
        JtaTransactionManager transactionManager) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(xaConnectionFactory);
    factory.setTransactionManager(transactionManager);
    return factory;
}
~~~

Với `JmsTemplate`, dùng `JtaTransactionManager` cùng XA-capable `ConnectionFactory`. Database cũng phải dùng XA DataSource và được đăng ký với cùng transaction coordinator. Trong một method `@Transactional` dùng JTA manager, các resource đã enlist có thể tham gia global transaction.

**XA không tự hoạt động chỉ vì khai báo `JtaTransactionManager`.** Cần cấu hình broker, JDBC driver, XA ConnectionFactory, XA DataSource, transaction coordinator và recovery log đúng cách. Nếu một resource chỉ hỗ trợ local transaction, resource đó không tự động trở thành XA participant.

### 10.1. Ưu và nhược điểm của XA

| Khía cạnh | Đặc điểm |
|---|---|
| Atomicity | Các XA resource đã enlist được điều phối commit/rollback chung |
| Tính nhất quán | Giảm cửa sổ lệch trạng thái giữa database và broker |
| Chi phí | Có thêm prepare/commit round trip, transaction log và recovery |
| Khóa tài nguyên | Resource có thể giữ trạng thái prepared trong lúc chờ quyết định |
| Vận hành | Cần giám sát transaction coordinator và xử lý in-doubt transaction |
| Khả năng tương thích | Broker, driver và datasource phải hỗ trợ XA và được cấu hình đúng |

Spring cũng khuyến nghị cân nhắc local JMS transaction cộng với duplicate detection khi có thể chấp nhận duplicate trong một số sự cố process. Cách đó thường nhẹ hơn XA. Chọn XA khi yêu cầu atomicity thực sự cần thiết và hạ tầng có thể vận hành transaction phân tán.

## 11. AFTER_COMMIT có thay thế được outbox không?

Spring cung cấp `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` và transaction synchronization callback để chạy code sau khi database transaction commit.

Ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void publishAfterCommit(OrderCreated event) {
    jmsTemplate.convertAndSend("orders.events", event);
}
~~~

Cách này bảo đảm callback chỉ chạy sau khi transaction gốc commit thành công. Nó hữu ích cho side effect best-effort hoặc khi hệ thống chấp nhận có thể phải xử lý thủ công nếu publish thất bại.

Tuy nhiên, callback không lưu event bền vững. Nếu process dừng sau database commit nhưng trước callback hoặc trong lúc send, không có outbox record để relay thử lại sau khi khởi động. Vì vậy AFTER_COMMIT không cung cấp cùng mức bảo đảm với transactional outbox.

Nếu dùng callback, cần xác định rõ cách retry, ghi nhận lỗi và phục hồi event chưa publish. Với event quan trọng, outbox thường dễ kiểm soát hơn.

## 12. Saga và các nghiệp vụ đi qua nhiều service

XA có thể phối hợp các XA resource trong một transaction coordinator. Nhưng một quy trình nghiệp vụ có thể đi qua nhiều service, mỗi service sở hữu database và broker riêng, hoặc gọi API HTTP bên ngoài. Những hệ thống đó thường không cùng tham gia một XA transaction.

Saga chia quy trình dài thành nhiều transaction cục bộ. Mỗi bước commit trong service sở hữu dữ liệu; nếu bước sau thất bại, hệ thống chạy hành động bù (compensating action) để đưa nghiệp vụ về trạng thái chấp nhận được.

Ví dụ đặt hàng:

1. Order Service tạo đơn hàng ở trạng thái `PENDING` và phát `OrderCreated`.
2. Payment Service thử thu tiền và phát `PaymentSucceeded` hoặc `PaymentFailed`.
3. Nếu thanh toán thành công, Order Service chuyển đơn sang `CONFIRMED`.
4. Nếu thanh toán thất bại, Order Service hủy đơn hoặc chuyển sang `CANCELLED`; nếu đã giữ kho, Inventory Service thực hiện hoàn trả reservation.

Saga cung cấp eventual consistency và xử lý bù theo nghiệp vụ. Nó không phải một global database/JMS transaction và hành động bù cũng có thể thất bại, nên cần retry, idempotency và trạng thái theo dõi.

## 13. Chọn giải pháp theo yêu cầu

| Yêu cầu | Giải pháp phù hợp |
|---|---|
| Chỉ cần transaction cho thao tác gửi JMS | `JmsTransactionManager` hoặc transacted JMS Session |
| Chỉ cần transaction cho cập nhật DB | `DataSourceTransactionManager`, `JdbcTransactionManager` hoặc `JpaTransactionManager` |
| DB update phải luôn có event outbound bền vững | Transactional outbox |
| Listener cập nhật DB và có thể nhận lại cùng message | Transacted JMS session + inbox/deduplication |
| DB và JMS receipt/send phải atomic trong một transaction | JTA/XA với tất cả resource XA-capable |
| Quy trình nghiệp vụ đi qua nhiều service | Saga với local transaction và compensating action |
| Side effect không quan trọng, chấp nhận best-effort | AFTER_COMMIT callback kèm logging/retry phù hợp |

Không có một lựa chọn đúng cho mọi hệ thống. Hãy xác định điều gì phải atomic, duplicate có thể chấp nhận không, broker/provider có hỗ trợ XA không và đội vận hành có thể quản lý transaction coordinator hay không.

## 14. Lỗi thường gặp

- **Cho rằng một `@Transactional` tự bao gồm DB và JMS:** annotation dùng một transaction manager cụ thể. Các resource khác không tự động được enlist.
- **Dùng `JmsTransactionManager` để rollback JDBC:** manager này chỉ quản lý một JMS ConnectionFactory.
- **Dùng `DataSourceTransactionManager` để rollback JMS send:** database transaction không điều khiển commit của broker.
- **Bật `sessionTransacted=true` rồi cho rằng DB cũng rollback:** flag chỉ tạo local JMS transaction cho listener invocation.
- **Gửi event trong DB transaction và cho rằng send rollback theo DB:** hai resource có commit riêng nếu không dùng XA.
- **Dùng AFTER_COMMIT như một outbox:** callback không lưu bền vững event khi process crash.
- **Không xử lý duplicate sau redelivery:** DB có thể đã commit trong khi JMS commit thất bại.
- **Dùng `exists` rồi insert inbox trong hai thao tác riêng:** hai consumer đồng thời có thể cùng vượt qua bước kiểm tra; cần unique constraint và insert nguyên tử.
- **Nuốt exception trong listener:** container có thể commit JMS transaction dù xử lý nghiệp vụ không thành công.
- **Dùng XA với resource không XA:** transaction manager không thể bảo đảm atomicity cho resource không enlist được.
- **Đánh dấu outbox published trước khi broker nhận message:** crash ở giữa có thể làm mất event.
- **Cho rằng outbox bảo đảm exactly-once:** relay có thể gửi trùng nếu broker nhận message nhưng trạng thái published chưa được lưu.

## 15. Checklist thiết kế

- [ ] Đã xác định transaction manager đang quản lý từng resource.
- [ ] Đã phân biệt local JMS transaction với local DB transaction.
- [ ] Đã xác định thứ tự commit và các failure window cho cả outbound và inbound.
- [ ] Với outbound event quan trọng, đã cân nhắc transactional outbox.
- [ ] Outbox row và business update dùng cùng DB transaction.
- [ ] Relay gửi trước rồi mới đánh dấu published, có retry và cơ chế lease/locking.
- [ ] Event có ID ổn định và consumer xử lý idempotent.
- [ ] Với inbound listener, đã bật transacted JMS session khi cần reliability.
- [ ] Inbox insert và business update dùng cùng DB transaction.
- [ ] Inbox có unique constraint hoặc thao tác insert nguyên tử.
- [ ] Exception cần rollback được truyền tới listener container.
- [ ] Nếu dùng XA, cả JMS ConnectionFactory và DataSource đều XA-capable và được enlist.
- [ ] Đã cấu hình transaction coordinator, timeout, log và recovery.
- [ ] Đã cân nhắc Saga khi quy trình đi qua nhiều service.
- [ ] Đã kiểm thử broker outage, DB outage, process crash giữa hai lần commit, redelivery và duplicate event.

## 16. Tài liệu tham khảo

- [Spring Framework — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — JmsTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Spring Framework — JtaTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/jta/JtaTransactionManager.html)
- [Spring Framework — DataSourceTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Boot — Distributed Transactions With JTA](https://docs.spring.io/spring-boot/reference/io/jta.html)
- [AWS Prescriptive Guidance — Transactional Outbox Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
