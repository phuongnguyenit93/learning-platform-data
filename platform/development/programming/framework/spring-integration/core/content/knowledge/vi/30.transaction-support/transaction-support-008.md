# Transaction với MessageStore

Trong Spring Integration Core, một luồng thường đi qua `Message`, `MessageChannel` và các endpoint xử lý. Khi channel hoặc endpoint phải giữ message để xử lý sau, trạng thái đó trở thành một phần của tính đúng đắn nghiệp vụ. Bài này thuộc chương **Transaction support**, tập trung vào cách phối hợp MessageStore với transaction để việc nhận, giữ và xử lý message có kết quả nhất quán.

Tình huống xuyên suốt là tiếp nhận đơn hàng: ứng dụng ghi đơn vào database, đưa yêu cầu xử lý vào một channel lưu bằng JDBC, rồi để poller xử lý sau. Mục tiêu là tránh hai trạng thái: có đơn nhưng thiếu yêu cầu xử lý, hoặc yêu cầu đã biến mất trong khi đơn chưa được xử lý thành công.

Sau bài học, bạn cần giải thích được:

- Store nào phù hợp với queue, store nào phù hợp với aggregator.
- Transaction bắt đầu ở đâu để bao phủ thao tác `receive()`.
- Vì sao producer và consumer có hai transaction độc lập.
- Giới hạn của rollback khi flow đổi thread hoặc gọi hệ thống bên ngoài.
- Cách kiểm chứng rollback, restart và xử lý lặp bằng database thật.

## 1. Lưu bền và transaction giải quyết hai vấn đề khác nhau

**Lưu bền — durability** trả lời câu hỏi: message đã được lưu thành công có còn sau khi tiến trình khởi động lại hay không?

**Tính nguyên tử — atomicity** trả lời câu hỏi: thao tác trên message và các thay đổi nghiệp vụ có cùng commit hoặc cùng rollback hay không?

Một queue lưu trong database vẫn có thể mất cơ hội xử lý nghiệp vụ nếu ứng dụng lấy message bằng một transaction đã commit, rồi xử lý nghiệp vụ bằng một transaction khác bị rollback. Ngược lại, đặt transaction quanh một queue trong bộ nhớ không làm nội dung bộ nhớ trở thành dữ liệu bền sau khi JVM dừng.

| Cách thiết kế | Sau khi tiến trình dừng | Khi handler thất bại |
| --- | --- | --- |
| `QueueChannel` mặc định trong bộ nhớ | Message đang chờ có thể mất | Không có cơ chế JDBC rollback để tự khôi phục message đã lấy |
| Queue dùng JDBC nhưng nhận ngoài transaction của poller | Message đã commit trong queue có thể phục hồi | Việc nhận có thể đã hoàn tất trước khi nghiệp vụ lỗi |
| Queue dùng JDBC, nhận và xử lý trong cùng transaction phù hợp | Message đã commit được giữ trong database | Việc xóa message và cập nhật nghiệp vụ có thể cùng rollback |
| Queue JDBC có transaction nhưng handler gọi HTTP | Database vẫn có transaction | HTTP đã thực hiện ở hệ thống khác không tự bị hoàn tác |

Tài liệu channel xác nhận cơ chế quan trọng: với persistent store có transaction, việc loại bỏ message chỉ trở thành vĩnh viễn khi transaction bao quanh poller commit thành công. [Tham khảo cấu hình MessageChannel](https://docs.spring.io/spring-integration/reference/6.5/channel/configuration.html).

Từ đó, hợp đồng cần thiết cho ví dụ đơn hàng là:

```text
TX tiếp nhận:
    INSERT đơn hàng
    INSERT message vào queue JDBC
    COMMIT cả hai hoặc ROLLBACK cả hai

TX xử lý:
    RECEIVE message từ queue JDBC
    UPDATE đơn hàng
    COMMIT cả hai hoặc ROLLBACK cả hai
```

Hai khối này diễn ra ở thời điểm khác nhau. Tính nguyên tử được bảo đảm bên trong từng khối khi cấu hình tài nguyên và transaction đúng.

## 2. Chọn đúng loại MessageStore

Tên “MessageStore” thường được dùng để nói chung về nơi lưu message. Khi cấu hình thực tế, cần nhìn vào interface và mục đích của implementation.

| Thành phần | Trách nhiệm | Ví dụ sử dụng |
| --- | --- | --- |
| `MessageStore` | Lưu và truy xuất message riêng lẻ | Claim check: giữ message, truyền khóa tham chiếu |
| `MessageGroupStore` | Quản lý nhóm message và trạng thái nhóm | Aggregator, resequencer |
| `ChannelMessageStore` | Hợp đồng phục vụ lưu và lấy message cho channel | Queue lưu ngoài bộ nhớ |
| `JdbcMessageStore` | Store JDBC tổng quát, hỗ trợ message và nhóm | Aggregator, claim check |
| `JdbcChannelMessageStore` | Store JDBC chuyên cho channel | `QueueChannel` lưu bằng JDBC |
| `SimpleMessageStore` | Store trong bộ nhớ | Thử nghiệm hoặc trạng thái không cần lưu bền |

`JdbcMessageStore` phù hợp với trạng thái nhóm; `JdbcChannelMessageStore` dành cho channel và không phải lựa chọn thay thế cho store của aggregator. [Tham khảo JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html), [API JdbcMessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/store/JdbcMessageStore.html).

Trong ví dụ chính:

```text
orderInbox (QueueChannel)
    └── MessageGroupQueue
          └── JdbcChannelMessageStore
                └── PostgreSQL
```

`MessageGroupQueue` nối API queue với store. Khi dùng lại queue sau restart, phải giữ nguyên định danh nhóm của queue. Nếu mỗi lần khởi động đều sinh `UUID` mới cho `groupId`, ứng dụng có thể nhìn thấy một queue rỗng trong khi message cũ vẫn nằm trong database. [Tham khảo API MessageGroupQueue](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupQueue.html).

## 3. Ranh giới transaction của producer và consumer

Sơ đồ sau thể hiện một lần tiếp nhận và một lần xử lý thất bại.

```mermaid
sequenceDiagram
    participant Client as Bên gọi
    participant Producer as Service tiếp nhận
    participant DB as Database
    participant Poller as Poller
    participant Handler as Handler nghiệp vụ

    Client->>Producer: submit(orderId)
    Producer->>DB: BEGIN TX-P
    Producer->>DB: INSERT app_order
    Producer->>DB: INSERT message vào queue
    Producer->>DB: COMMIT TX-P
    Producer-->>Client: Đã tiếp nhận

    Poller->>DB: BEGIN TX-C1
    Poller->>DB: RECEIVE message
    Poller->>Handler: handle(orderId)
    Handler->>DB: UPDATE app_order
    Handler--xPoller: RuntimeException
    Poller->>DB: ROLLBACK TX-C1
    Note over DB: Message còn để nhận lại; UPDATE bị hoàn tác

    Poller->>DB: BEGIN TX-C2
    Poller->>DB: RECEIVE lại message
    Poller->>Handler: handle(orderId)
    Handler->>DB: UPDATE app_order
    Handler-->>Poller: Hoàn tất
    Poller->>DB: COMMIT TX-C2
```

Việc client nhận được kết quả “đã tiếp nhận” chỉ có nghĩa transaction producer đã hoàn tất. Nó không xác nhận consumer đã xử lý xong.

Khi flow được khởi động bởi poller, transaction phải được thiết lập quanh hoạt động polling để bao gồm cả `receive()`. Đặt `@Transactional` riêng trên handler chỉ bắt đầu transaction tại lời gọi handler; điều đó có thể quá muộn để bảo vệ việc lấy message khỏi queue. [Tham khảo Poller Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

## 4. Ví dụ Java DSL: queue JDBC và dữ liệu nghiệp vụ cùng tài nguyên

### 4.1. Điều kiện chạy ví dụ

Ví dụ dùng API theo dòng Spring Integration 6.5, Java 17 và PostgreSQL. Khi áp dụng vào dự án, sử dụng các phiên bản Spring tương thích được quản lý bởi BOM hoặc Spring Boot của dự án.

Cần có:

- `spring-integration-core` để định nghĩa channel, endpoint và Java DSL.
- `spring-integration-jdbc` để sử dụng JDBC MessageStore.
- `spring-jdbc` và `spring-tx`; có thể đã được kéo vào qua dependency khác.
- JDBC driver PostgreSQL và một bean `DataSource`.
- Khi chạy kiểm thử: JUnit Jupiter, `spring-test` và `spring-integration-test`.

Giả định chỉ có một `DataSource` trong application context của ví dụ. Database chứa cả bảng nghiệp vụ và các bảng của store. `JdbcTemplate`, store và `DataSourceTransactionManager` đều dùng đúng bean `DataSource` này.

Cùng trỏ tới một URL database chưa đủ nếu code lại tạo connection riêng không tham gia transaction. `DataSourceTransactionManager` quản lý connection gắn với thread cho một `DataSource`; `JdbcTemplate` phối hợp với cơ chế đó. [Tham khảo DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

### 4.2. Chuẩn bị schema trước khi khởi động flow

Tạo các bảng Spring Integration bằng script PostgreSQL đi kèm đúng phiên bản `spring-integration-jdbc` đang dùng. Với dòng minh họa, resource nằm tại:

```text
org/springframework/integration/jdbc/schema-postgresql.sql
```

Script này có bảng `INT_CHANNEL_MESSAGE`, sequence liên quan và các bảng phục vụ store tổng quát. Không tự rút gọn schema chỉ còn cột payload; store còn cần định danh, region và thông tin thứ tự. [Xem schema PostgreSQL trong mã nguồn Spring Integration 6.5](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-jdbc/src/main/resources/org/springframework/integration/jdbc/schema-postgresql.sql).

Tạo thêm bảng nghiệp vụ:

```sql
CREATE TABLE app_order (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(16) NOT NULL,
    CONSTRAINT app_order_state_ck
        CHECK (state IN ('NEW', 'PROCESSED'))
);
```

Áp dụng schema bằng migration trước khi context khởi động. Không chạy lại lệnh `CREATE TABLE` mỗi lần poller nhận message. Trong môi trường thật, migration cũng phải giữ được message đang chờ khi nâng cấp ứng dụng.

### 4.3. Cấu hình đầy đủ phần flow và service

Lưu lớp sau trong package của ứng dụng và import hoặc scan cấu hình này. Bean `DataSource` được môi trường chạy cung cấp như mô tả ở trên.

Payload là `String` chứa mã đơn. Cách chọn payload này giúp ví dụ tập trung vào transaction; không mang entity JPA hoặc object channel vào dữ liệu lưu bền.

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel
        .PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

@Configuration
@EnableIntegration
@EnableTransactionManagement
public class OrderIntegrationConfig {

    @Bean("integrationTxManager")
    public PlatformTransactionManager integrationTxManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public JdbcChannelMessageStore channelMessageStore(
            DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        store.setRegion("orders-v1");
        return store;
    }

    @Bean
    public QueueChannel orderInbox(
            JdbcChannelMessageStore channelMessageStore) {
        return new QueueChannel(
                new MessageGroupQueue(
                        channelMessageStore, "order-inbox"));
    }

    @Bean
    public OrderSubmissionService orderSubmissionService(
            JdbcTemplate jdbcTemplate,
            @Qualifier("orderInbox") QueueChannel orderInbox) {
        return new OrderSubmissionService(jdbcTemplate, orderInbox);
    }

    @Bean
    public OrderHandler orderHandler(JdbcTemplate jdbcTemplate) {
        return new OrderHandler(jdbcTemplate);
    }

    @Bean
    public IntegrationFlow consumeOrders(
            @Qualifier("orderInbox") QueueChannel orderInbox,
            OrderHandler orderHandler,
            @Qualifier("integrationTxManager")
                    PlatformTransactionManager txManager) {

        return IntegrationFlow.from(orderInbox)
                .handle(orderHandler, "handle",
                        endpoint -> endpoint
                                .id("orderConsumer")
                                .poller(Pollers.fixedDelay(500)
                                        .maxMessagesPerPoll(1)
                                        .transactional(txManager)))
                .get();
    }

    public static class OrderSubmissionService {

        private final JdbcTemplate jdbc;
        private final QueueChannel inbox;

        public OrderSubmissionService(
                JdbcTemplate jdbc, QueueChannel inbox) {
            this.jdbc = jdbc;
            this.inbox = inbox;
        }

        @Transactional(transactionManager = "integrationTxManager")
        public void submit(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "orderId không được trống");
            }

            jdbc.update(
                    "INSERT INTO app_order(order_id, state) "
                            + "VALUES (?, 'NEW')",
                    orderId);

            boolean accepted = inbox.send(
                    MessageBuilder.withPayload(orderId)
                            .setHeader("eventType", "OrderAccepted")
                            .build());

            if (!accepted) {
                throw new IllegalStateException(
                        "Không đưa được yêu cầu vào orderInbox");
            }
        }
    }

    public static class OrderHandler {

        private final JdbcTemplate jdbc;

        public OrderHandler(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void handle(String orderId) {
            int changed = jdbc.update(
                    "UPDATE app_order SET state = 'PROCESSED' "
                            + "WHERE order_id = ? AND state = 'NEW'",
                    orderId);

            if (changed == 0) {
                Integer alreadyProcessed = jdbc.queryForObject(
                        "SELECT COUNT(*) FROM app_order "
                                + "WHERE order_id = ? "
                                + "AND state = 'PROCESSED'",
                        Integer.class, orderId);

                if (alreadyProcessed == null
                        || alreadyProcessed != 1) {
                    throw new IllegalStateException(
                            "Đơn hàng không hợp lệ: " + orderId);
                }
            }
        }
    }
}
```

Một transaction manager được truyền rõ ràng vào `Pollers.transactional(...)`. Cách viết này tránh dựa vào việc ứng dụng tình cờ có một bean mang tên `transactionManager`. API của poller hỗ trợ cấu hình transaction advice quanh polling task. [Tham khảo PollerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html).

Gọi service do Spring quản lý:

```java
// Bean được inject từ application context.
orderSubmissionService.submit("ORD-2026-001");
```

Không tự `new OrderSubmissionService(...)` rồi kỳ vọng annotation hoạt động. Với cơ chế proxy thông thường, lời gọi từ bên ngoài phải đi qua bean proxy; self-invocation cũng không tự kích hoạt transaction mới.

### 4.4. Diễn giải hành vi của ví dụ

Ở producer, `INSERT app_order` và thao tác lưu message chạy trong transaction của `submit()`. Nếu lưu message thất bại hoặc `send()` trả về `false`, exception làm transaction thất bại. Đơn hàng không được phép commit một mình.

Ở consumer, poller mở transaction trước khi nhận message. Handler cập nhật đơn trong chính transaction đó vì dùng `JdbcTemplate` và cùng `DataSource` trên thread đang xử lý. Khi handler kết thúc bình thường, transaction commit và message không còn trong queue.

Handler cho phép yêu cầu xử lý lặp đối với đơn đã ở trạng thái `PROCESSED`. Điều này chỉ bảo vệ chuyển trạng thái trong database của ví dụ. Nó không biến việc tiếp nhận qua `submit()` thành API idempotent: gọi lại `submit()` với cùng mã đơn sẽ gặp ràng buộc khóa chính và cần được xử lý theo hợp đồng API riêng.

`maxMessagesPerPoll(1)` giúp quan sát từng message khi học và kiểm thử. Tham số này giới hạn số message mỗi lần poll; không nên dùng nó như một lời khẳng định rằng mọi message trong một đợt bất kỳ sẽ cùng thuộc một transaction dạng batch.

Không đặt transaction của consumer ở chế độ `readOnly`: thao tác nhận từ queue JDBC cần thay đổi trạng thái lưu trữ, và handler còn thực hiện `UPDATE`.

## 5. Gateway, channel và endpoint ảnh hưởng thế nào đến transaction?

Một messaging gateway giúp mã nghiệp vụ gửi yêu cầu qua interface thay vì gọi trực tiếp `MessageChannel.send()`. Nó không tự làm cho toàn bộ quá trình xử lý bất đồng bộ trở thành một transaction.

Ví dụ interface thay cho thao tác gửi trực tiếp:

```java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orderInbox")
public interface OrderIngress {
    void accept(String orderId);
}
```

Nếu dùng biến thể này, cần đăng ký gateway bằng `@IntegrationComponentScan` ở package phù hợp, inject `OrderIngress` vào service tiếp nhận rồi gọi `accept(orderId)` ngay bên trong transaction producer. Đây là một cách gửi thay thế; không vừa gọi gateway vừa giữ lệnh `inbox.send(...)` vì sẽ tạo hai yêu cầu.

Phương thức gateway trả `void` phù hợp với việc tiếp nhận rồi xử lý sau. Không kỳ vọng một `replyChannel` tạm thời của request còn là địa chỉ dùng được sau khi ứng dụng restart.

Cần vẽ ranh giới theo hành vi thực tế của channel:

| Đường đi | Transaction hiện tại có thể tiếp tục ở đâu? |
| --- | --- |
| Handler gọi tiếp qua `DirectChannel` cùng thread | Các thao tác tham gia đúng tài nguyên có thể nằm trong transaction hiện tại |
| Gửi vào queue JDBC | Thao tác lưu message có thể tham gia transaction gửi; consumer nhận sau bằng transaction khác |
| Gửi qua `ExecutorChannel` | Thread xử lý tiếp không tự nhận transaction JDBC của thread gửi |
| Handler gọi `@Async` hoặc tạo thread | Công việc trên thread mới cần ranh giới transaction riêng |
| Gọi HTTP từ handler | Transaction database không bao phủ commit của hệ thống HTTP từ xa |

Khi thêm một đoạn bất đồng bộ, cần xác định điểm bàn giao đã được lưu bền hay chỉ đang nằm trong bộ nhớ. Nếu poller đã bàn giao thành công cho executor trong bộ nhớ, transaction của poller có thể commit trước khi xử lý trên executor thất bại.

Spring Integration mô tả transaction imperative theo thread; các ranh giới channel làm đổi thread phải được thiết kế như điểm bàn giao giữa các transaction. [Tham khảo Transaction Boundaries](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-boundaries).

## 6. Propagation và nhiều tài nguyên

### 6.1. `REQUIRED` thường phù hợp với xử lý đồng bộ trong poller

Khi poller đã có transaction, service nghiệp vụ dùng `REQUIRED` với transaction manager tương ứng có thể tham gia transaction đó. Việc nhận message và cập nhật nghiệp vụ vì vậy vẫn thuộc cùng đơn vị commit.

### 6.2. `REQUIRES_NEW` tạo kết quả độc lập

Giả sử handler gọi service với `REQUIRES_NEW`:

```text
TX ngoài:
    RECEIVE message
    TX trong (REQUIRES_NEW):
        UPDATE đơn
        COMMIT
    Xử lý tiếp bị lỗi
    ROLLBACK TX ngoài
```

Message có thể quay lại queue, nhưng thay đổi của transaction trong đã commit. Nếu nghiệp vụ có cộng tiền, trừ kho hoặc tạo bản ghi mới, lần nhận lại có thể tạo tác động lặp.

`REQUIRES_NEW` cũng cần connection độc lập trong khi transaction ngoài đang giữ tài nguyên; phải cân nhắc dung lượng connection pool. [Tham khảo Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

### 6.3. Hai database hoặc hai transaction manager không tự thành một transaction chung

Nếu store dùng database A còn nghiệp vụ dùng database B, một `DataSourceTransactionManager` chỉ quản lý A sẽ không tự rollback B.

Các lựa chọn thiết kế gồm:

- Đưa phần trạng thái cần commit nguyên tử về cùng một tài nguyên nếu yêu cầu cho phép.
- Dùng cơ chế transaction phân tán khi toàn bộ tài nguyên và hạ tầng có hỗ trợ phù hợp.
- Dùng outbox và consumer idempotent để điều phối qua nhiều lần commit.

Với JPA, cần chọn transaction manager và cách phối hợp JDBC theo tài nguyên thực tế. Không thêm một JDBC transaction manager thứ hai rồi mặc định rằng nó sẽ tự đồng bộ nguyên tử với transaction JPA đã có.

## 7. Transaction với aggregator và MessageGroupStore

Aggregator cần giữ nhiều message cho đến khi đủ điều kiện gộp. Có hai tầng trạng thái khác nhau:

1. Message đang chờ trong channel đầu vào.
2. Message cùng metadata đã nằm trong nhóm của aggregator.

Nếu channel đầu vào dùng JDBC nhưng nhóm aggregator chỉ nằm trong bộ nhớ, việc dừng JVM sau khi đã nhận các message vẫn có thể làm mất nhóm đang chờ hoàn tất.

Dùng `JdbcMessageStore` cho nhóm. Đoạn cấu hình sau là phần mở rộng độc lập của ví dụ, thêm vào một lớp `@Configuration`; vẫn sử dụng `DataSource`, `channelMessageStore` và `integrationTxManager` ở trên.

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.transaction.PlatformTransactionManager;

// Các phương thức @Bean nằm trong lớp @Configuration của ứng dụng.

@Bean
public JdbcMessageStore shipmentGroupStore(DataSource dataSource) {
    JdbcMessageStore store = new JdbcMessageStore(dataSource);
    store.setRegion("shipment-groups-v1");
    return store;
}

@Bean
public QueueChannel shipmentInbox(JdbcChannelMessageStore store) {
    return new QueueChannel(
            new MessageGroupQueue(store, "shipment-inbox"));
}

@Bean
public QueueChannel shipmentResults(JdbcChannelMessageStore store) {
    return new QueueChannel(
            new MessageGroupQueue(store, "shipment-results"));
}

@Bean
public IntegrationFlow aggregateShipments(
        @Qualifier("shipmentInbox") QueueChannel inbox,
        @Qualifier("shipmentResults") QueueChannel results,
        JdbcMessageStore shipmentGroupStore,
        @Qualifier("integrationTxManager")
                PlatformTransactionManager txManager) {

    return IntegrationFlow.from(inbox)
            .aggregate(aggregator -> aggregator
                            .messageStore(shipmentGroupStore)
                            .expireGroupsUponCompletion(false),
                    endpoint -> endpoint
                            .id("shipmentAggregator")
                            .poller(Pollers.fixedDelay(500)
                                    .maxMessagesPerPoll(1)
                                    .transactional(txManager)))
            .channel(results)
            .get();
}
```

Flow dùng chiến lược correlation và release mặc định. Đầu vào phải có các header `CORRELATION_ID`, `SEQUENCE_NUMBER` và `SEQUENCE_SIZE` phù hợp, chẳng hạn từ splitter có sequence. Không gửi hai message tùy ý rồi mặc định chúng tự thành một nhóm.

Giả sử nhóm `SHIP-42` có hai phần:

```text
Lần nhận phần 1:
    nhận khỏi shipmentInbox
    thêm phần 1 vào nhóm SHIP-42
    chưa đủ phần → commit trạng thái nhóm

Lần nhận phần 2:
    nhận khỏi shipmentInbox
    thêm phần 2 vào nhóm SHIP-42
    đủ phần → tạo kết quả và lưu vào shipmentResults
    cập nhật trạng thái nhóm
    commit
```

Trong cấu hình cùng thread và cùng tài nguyên, lỗi khi lưu kết quả có thể rollback thay đổi của lần nhận phần 2. Phần 1 đã commit từ trước vẫn là trạng thái đã lưu; transaction hiện tại không quay ngược lịch sử của mọi message trong nhóm.

Việc giữ nhóm completed với `expireGroupsUponCompletion(false)` giúp xử lý message tới muộn theo trạng thái nhóm. Cần có chính sách dọn metadata về sau. Nếu nhiều node cùng cập nhật nhóm, phải dùng `LockRegistry` dùng chung phù hợp; khóa trong bộ nhớ của một JVM không đồng bộ được các JVM khác. Timeout hoặc reaper chạy bằng tác vụ riêng cũng cần ranh giới transaction riêng nếu thao tác hết hạn phải nguyên tử. [Tham khảo Aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

## 8. Exception, errorChannel, retry và message lỗi kéo dài

### 8.1. Exception phải đi đến đúng ranh giới transaction

Theo cấu hình rollback mặc định của Spring, `RuntimeException` và `Error` gây rollback; checked exception cần quy tắc thích hợp nếu muốn rollback. Khi đi qua endpoint, exception có thể được bọc thành exception messaging; hãy kiểm tra loại exception đến transaction advice. [Tham khảo quy tắc rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

Một lỗi thường gặp:

```java
public void handle(String orderId) {
    try {
        updateOrder(orderId);
    }
    catch (RuntimeException ex) {
        logFailure(orderId, ex);
        // Trả về bình thường: transaction advice có thể thấy thành công.
    }
}
```

Nếu transaction chưa bị đánh dấu rollback-only, việc bắt lỗi rồi trả về có thể dẫn tới commit và message bị loại khỏi queue. Nếu lỗi phải làm nhận lại message, cần để exception lan tới transaction advice hoặc chủ động đánh dấu rollback theo hợp đồng xử lý.

### 8.2. Thông báo lỗi không thay thế rollback

`errorChannel` phục vụ truyền thông tin lỗi dưới dạng `ErrorMessage`. Đối với lỗi của scheduled poller, cơ chế xử lý lỗi có thể phát thông báo sau khi exception đã thoát khỏi phần được transaction advice bảo vệ.

Vì vậy, cần phân biệt:

- Recovery nằm bên trong phạm vi transaction đã bắt exception và trả thành công.
- Bộ xử lý lỗi chỉ ghi nhận một lần poll đã rollback.
- Bộ xử lý lỗi tự thực hiện một transaction mới để ghi dữ liệu vận hành.

Việc thấy log trên `errorChannel` không đủ chứng minh message đã commit hay rollback. Phải quan sát trạng thái queue và dữ liệu nghiệp vụ. [Tham khảo Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### 8.3. Rollback rồi nhận lại và retry handler có phạm vi khác nhau

Rollback toàn bộ lần nhận giúp message có thể được lấy lại trong một transaction mới. Retry advice trên handler có thể chỉ gọi lại handler trong transaction đang tồn tại, tùy thứ tự advice.

Nếu transaction đã bị đánh dấu rollback-only hoặc database đã đưa transaction vào trạng thái lỗi, retry câu SQL ngay trong transaction đó không tự tạo một phiên làm việc sạch. Nên xác định retry có bao phủ cả ranh giới transaction hay chỉ một lời gọi handler. [Tham khảo Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html#retry-advice).

Với message luôn gây lỗi, rollback vô hạn có thể làm message đó được nhận lặp và cản trở các message sau. Thiết kế cần có số lần thử, giãn cách và đích giữ message không thể xử lý.

Một cách bàn giao có chủ đích là:

```text
TX xử lý cuối:
    RECEIVE message từ queue chính
    lưu thông tin thất bại vào queue cách ly cùng database
    COMMIT
```

Queue cách ly phải lưu bền và tham gia cùng transaction nếu muốn thao tác chuyển queue nguyên tử. Nếu việc lưu vào queue cách ly thất bại, phải để transaction rollback. Không gửi vào một channel trong bộ nhớ rồi coi đó là bằng chứng đã giữ an toàn message lỗi.

Bộ đếm số lần thử cũng cần thiết kế riêng: tăng bộ đếm trong cùng transaction rồi rollback sẽ làm mất lần tăng đó. Bộ đếm chỉ ở RAM lại mất sau restart. Không mặc định JDBC MessageStore tự cung cấp một chính sách dead-letter đầy đủ.

### 8.4. Filter và router có thể kết thúc xử lý hợp lệ

Filter loại bỏ message mà không ném exception có thể khiến transaction commit. Router không tạo đầu ra theo cấu hình cho phép cũng có thể kết thúc flow mà không có nghiệp vụ tiếp theo.

Nếu nghiệp vụ yêu cầu “message không hợp lệ phải được giữ để kiểm tra”, hãy cấu hình discard channel lưu bền hoặc nhánh xử lý phù hợp. Nếu yêu cầu là “lỗi này phải nhận lại”, cần tạo tín hiệu thất bại đến ranh giới transaction. Không suy ra rollback chỉ từ việc flow không sinh output.

## 9. Vì sao vẫn cần idempotency và outbox?

Giả sử consumer nhận message, gọi API thanh toán thành công rồi mất kết nối trước khi transaction database commit. Database có thể rollback việc nhận, làm message xuất hiện lại. Lần xử lý tiếp theo có thể gọi thanh toán lần nữa.

Transaction của MessageStore không thể tự thu hồi một giao dịch thanh toán đã được hệ thống khác chấp nhận. Một định danh nghiệp vụ ổn định, chẳng hạn `paymentRequestId`, phải được dùng làm idempotency key tại phía có khả năng tạo tác động lặp.

Trong ví dụ đơn hàng, thao tác `NEW → PROCESSED` có tính idempotent cho một mã đơn. Nếu thay thành `balance = balance - amount`, một lần thực thi lặp sẽ mang ý nghĩa khác; cần khóa nghiệp vụ, ràng buộc duy nhất hoặc bảng ghi nhận event đã xử lý cùng transaction với cập nhật.

Outbox giúp tách việc lưu ý định khỏi việc gọi hệ thống ngoài:

```text
TX database:
    nhận message
    cập nhật nghiệp vụ
    INSERT outbox(event_id, payload)
    commit

Publisher:
    đọc outbox
    gửi sang hệ thống ngoài
    ghi nhận đã gửi
```

Publisher vẫn có thể gửi lại sau sự cố ở khoảng giữa “đã gửi” và “đã ghi nhận”. Vì vậy, outbox phải đi cùng hợp đồng idempotency ở nơi nhận. Không gọi đây là bảo đảm exactly-once cho toàn bộ hệ thống chỉ vì queue nằm trong database.

Callback `afterCommit` cũng không loại bỏ cửa sổ sự cố: tiến trình có thể dừng sau commit nhưng trước callback hoặc trước khi gửi xong. `PseudoTransactionManager` chỉ hỗ trợ điều phối callback thành công/thất bại; nó không thực hiện commit/rollback tài nguyên như một transaction manager JDBC thật. [Tham khảo Transaction Synchronization và Pseudo Transactions](https://docs.spring.io/spring-integration/reference/transactions.html#pseudo-transactions).

## 10. Serialization, định danh và khôi phục sau restart

Message đã được lưu còn phải đọc lại được. Cần xem payload và header là một hợp đồng dữ liệu lưu bền.

Đối với ví dụ:

- Payload `String` và header `eventType` kiểu `String` không phụ thuộc entity đang gắn với persistence context.
- `region = orders-v1` và `groupId = order-inbox` phải giữ ổn định qua restart của cùng queue.
- Dữ liệu của môi trường khác không được vô tình dùng cùng namespace.
- Thay đổi class payload hoặc serializer phải tính đến message cũ đang chờ.

Với store dùng Java serialization mặc định, payload và những dữ liệu được lưu phải đáp ứng yêu cầu serialization của implementation. Không dựa vào việc một header không thể serialize sẽ luôn được giữ nguyên; channel object, stream, connection hoặc bean reference không phải hợp đồng lưu bền đáng tin cậy. Một số phiên bản còn có giới hạn class được deserialize; DTO của ứng dụng phải được cấu hình phù hợp theo API phiên bản đang dùng. [Tham khảo Message Store và các lưu ý serialization](https://docs.spring.io/spring-integration/reference/message-store.html).

Nếu cần trả kết quả sau một khoảng thời gian dài hoặc qua restart, hãy lưu correlation ID nghiệp vụ và phát kết quả đến một địa chỉ ổn định. Một reply channel tạm thời được tạo cho lời gọi đồng bộ không phải cơ chế khôi phục phản hồi sau restart.

Khi triển khai phiên bản mới, phải giữ khả năng đọc message tồn đọng hoặc có bước chuyển đổi rõ ràng. Việc đổi `region` hay `groupId` để “làm sạch queue” chỉ làm ứng dụng nhìn sang vùng khác; message cũ chưa được xử lý vẫn cần được quản lý.

## 11. Kiểm chứng bằng database thật

Mock store phù hợp để kiểm tra lời gọi. Nó không chứng minh rằng lệnh lấy message và lệnh SQL nghiệp vụ dùng chung transaction.

Với PostgreSQL query provider, nên có kiểm thử trên PostgreSQL. Không dùng H2 rồi kết luận mọi hành vi SQL và khóa trên PostgreSQL đều tương đương.

### 11.1. Các trường hợp cần quan sát

| Trường hợp | Cách tạo tình huống | Trạng thái cần xác nhận |
| --- | --- | --- |
| Producer commit | Gọi `submit()`, giữ consumer dừng | Đơn `NEW` và một message đã được lưu |
| Producer rollback | Lưu đơn, gửi message, rồi tạo lỗi trong cùng transaction | Cả đơn và message của lần thử đều không được commit |
| Consumer commit | Nhận và cập nhật đơn thành công | Đơn `PROCESSED`, message đã hết |
| Consumer rollback | Tạo lỗi sau `UPDATE` nhưng trước commit | Đơn còn `NEW`, cùng message có thể nhận lại |
| Restart | Lưu message rồi tạo application context mới với cùng database và định danh | Context mới nhận được message cũ |
| Yêu cầu xử lý lặp | Gửi lại yêu cầu cho đơn đã xử lý | Không tạo thêm tác động nghiệp vụ |
| Sai ranh giới thread | Bàn giao sang executor rồi tạo lỗi ở thread mới | Kiểm thử phát hiện phần nào đã commit trước lỗi |
| Aggregator chưa đủ phần | Lưu một phần, restart rồi gửi phần còn lại | Nhóm được tiếp tục thay vì mất phần đã lưu |

Dùng `@SpringIntegrationTest(noAutoStartup = "orderConsumer")` để giữ endpoint dừng trong các kiểm thử cần điều khiển trực tiếp queue. Tên này trùng với `.id("orderConsumer")` trong cấu hình. [Tham khảo Spring Integration Test Context](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

### 11.2. Minh họa kiểm thử receive và nghiệp vụ cùng rollback

Đoạn kiểm thử sau đặt trong test class đã nạp `OrderIntegrationConfig`, cung cấp `DataSource` PostgreSQL đã có schema và dùng annotation giữ consumer dừng như trên.

Các import dùng thêm: `Autowired`, `Test`, `Message`, `UUID`, `TransactionTemplate` và các static assertion của JUnit Jupiter. `QueueChannel`, `JdbcTemplate`, `PlatformTransactionManager`, `Qualifier` dùng như cấu hình trước.

```java
@Autowired
private OrderIntegrationConfig.OrderSubmissionService submissionService;

@Autowired
private OrderIntegrationConfig.OrderHandler orderHandler;

@Autowired
@Qualifier("orderInbox")
private QueueChannel orderInbox;

@Autowired
private JdbcTemplate jdbcTemplate;

@Autowired
@Qualifier("integrationTxManager")
private PlatformTransactionManager txManager;

@Test
void receiveAndBusinessUpdateRollBackTogether() {
    // Không đặt test này trong một transaction @Transactional bên ngoài.
    // Queue và database test phải được cô lập với test khác.
    String orderId = "ORD-" + UUID.randomUUID();
    TransactionTemplate tx = new TransactionTemplate(txManager);

    // Transaction producer commit trước khi bắt đầu transaction consumer.
    submissionService.submit(orderId);

    Message<?>[] firstAttempt = new Message<?>[1];

    try {
        assertThrows(IllegalStateException.class, () ->
                tx.executeWithoutResult(status -> {
                    Message<?> message = orderInbox.receive(0);
                    assertNotNull(message);
                    assertEquals(orderId, message.getPayload());
                    firstAttempt[0] = message;

                    orderHandler.handle((String) message.getPayload());

                    // Tạo lỗi sau UPDATE để quan sát rollback cả hai phần.
                    throw new IllegalStateException("Lỗi mô phỏng");
                }));

        assertEquals("NEW", jdbcTemplate.queryForObject(
                "SELECT state FROM app_order WHERE order_id = ?",
                String.class, orderId));

        tx.executeWithoutResult(status -> {
            Message<?> redelivered = orderInbox.receive(0);
            assertNotNull(redelivered);
            assertEquals(orderId, redelivered.getPayload());
            assertEquals(firstAttempt[0].getHeaders().getId(),
                    redelivered.getHeaders().getId());

            orderHandler.handle((String) redelivered.getPayload());
        });

        assertEquals("PROCESSED", jdbcTemplate.queryForObject(
                "SELECT state FROM app_order WHERE order_id = ?",
                String.class, orderId));

        // Không còn message. Thao tác quan sát cũng nằm trong transaction.
        tx.executeWithoutResult(status ->
                assertNull(orderInbox.receive(0)));
    }
    finally {
        jdbcTemplate.update(
                "DELETE FROM app_order WHERE order_id = ?", orderId);
        // Fixture test chịu trách nhiệm dọn store trong database test
        // nếu một assertion thất bại trước khi consume thành công.
    }
}
```

Kiểm thử này xác nhận tính chất của tài nguyên và phạm vi transaction khi gọi `receive()` trực tiếp. Nó chưa xác nhận poller production đã được gắn advice đúng.

Cần thêm một kiểm thử bật endpoint `orderConsumer` thật: tạo message, gây lỗi handler có kiểm soát, quan sát rollback rồi cho lần sau thành công. Khi chạy bất đồng bộ, chờ một điều kiện có timeout thay vì dùng một khoảng `sleep` cố định và hy vọng poller đã chạy.

Kiểm thử restart phải đóng context cũ, giữ nguyên database rồi tạo context mới. Chỉ `stop()` và `start()` endpoint trong cùng context không chứng minh khả năng khôi phục sau khi mất toàn bộ bộ nhớ của tiến trình.

## 12. Chẩn đoán sự cố thường gặp

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| Handler lỗi nhưng message không quay lại | Poller có transaction bao quanh `receive()` không; có recovery bắt lỗi bên trong không |
| SQL nghiệp vụ rollback nhưng queue vẫn mất message | Store và nghiệp vụ có thật sự dùng cùng tài nguyên, connection và phạm vi transaction không |
| Message quay lại nhưng dữ liệu nghiệp vụ đã đổi | Có `REQUIRES_NEW`, transaction manager khác hoặc cập nhật ngoài transaction không |
| Restart thấy queue rỗng dù database còn dữ liệu | `region`, `groupId`, schema và table prefix có thay đổi không |
| Gọi service nhưng không có transaction | Có gọi bean proxy không; có tự `new` hoặc self-invocation không |
| Không đọc lại được message cũ | Serializer, class payload, version dữ liệu và giới hạn deserialize |
| Nhiều node tạo kết quả aggregator sai | Có shared store nhưng thiếu shared `LockRegistry` hoặc correlation ID bị trùng không |
| Một message lỗi bị nhận mãi | Có chính sách thử lại, giãn cách, bộ đếm bền và queue cách ly không |
| Throughput giảm khi tăng thread | Kiểm tra row lock, transaction kéo dài, query plan và connection pool |

Đối với consumer cạnh tranh nhau, phải xem xét khả năng khóa của database và query provider. Nếu cần `usingIdCache`, cấu hình callback dọn cache cho cả commit và rollback theo tài liệu; cache trong JVM không thay thế cơ chế phối hợp giữa các node. Không bật một tùy chọn concurrency chỉ vì thấy trong ví dụ dành cho database khác. [Tham khảo API JdbcChannelMessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/store/JdbcChannelMessageStore.html).

Các chỉ số vận hành hữu ích gồm số message chờ, tuổi message cũ nhất, số rollback, số lần nhận lại theo định danh nghiệp vụ, thời gian xử lý, thời gian chờ khóa và số message cách ly. Một queue tăng đều có thể do consumer chậm, transaction giữ khóa quá lâu hoặc message lỗi làm nghẽn xử lý; chỉ nhìn số lượng queue chưa phân biệt được các nguyên nhân đó.

Khi đọc lại một thiết kế, hãy xác định cụ thể ba điều: **trạng thái nào được lưu bền, thao tác nào cùng một transaction, và tác động nào có thể bị lặp**. Với MessageStore, câu trả lời phải xuất phát từ store, transaction manager, channel và đường đi thực tế của message.
