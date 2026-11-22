# Transaction với QueueChannel

## 1. Mục tiêu và bối cảnh

Trong chương **Transaction support** của module **SPRING_INTEGRATION_CORE**, bài này giải thích cách thiết kế một luồng nhận message từ `QueueChannel`, xử lý bằng endpoint và quyết định commit hoặc rollback. Trọng tâm là mối quan hệ giữa channel, poller, transaction manager và tài nguyên lưu trữ; Java DSL được dùng để thể hiện cấu hình.

Sau bài học, bạn có thể:

- Phân biệt queue trong bộ nhớ với queue dùng message store có khả năng tham gia transaction.
- Đặt transaction trước thao tác `receive()` để bảo vệ cả việc lấy message lẫn thay đổi dữ liệu nghiệp vụ.
- Xác định phạm vi transaction khi đi qua `DirectChannel`, queue tiếp theo, gateway hoặc executor.
- Giải thích tác động của exception, filter, retry và xử lý lỗi đến việc message còn được đọc lại hay không.
- Thiết kế kiểm thử quan sát đồng thời trạng thái queue và trạng thái cơ sở dữ liệu.

Tình huống xuyên suốt: ứng dụng nhận lệnh xử lý đơn hàng, đưa lệnh vào queue rồi để một consumer ghi kết quả vào bảng `PROCESSED_ORDER`. Nếu consumer ghi dữ liệu xong nhưng gặp lỗi trước commit, ta muốn **dữ liệu vừa ghi được rollback và lệnh vẫn còn trong queue để xử lý lại**.

## 2. QueueChannel cung cấp điều gì?

`QueueChannel` là một `PollableChannel`: producer gọi `send()`, consumer chủ động gọi `receive()`, thường thông qua một polling endpoint. Nó tạo vùng đệm giữa tốc độ gửi và tốc độ xử lý.

```java
QueueChannel orders = new QueueChannel(100);

boolean accepted = orders.send(
        MessageBuilder.withPayload("ORDER-101").build(), 0);
Message<?> received = orders.receive(0);
```

Trong đoạn mã này, `100` là capacity của queue trong bộ nhớ; `0` yêu cầu trả về ngay thay vì chờ. Cần kiểm tra giá trị `accepted` và trường hợp `received == null`. Việc `send()` trả về `true` chỉ xác nhận channel đã nhận message, không xác nhận nghiệp vụ của consumer thành công. Xem [API QueueChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html).

### 2.1. Queue trong bộ nhớ không tự rollback

Với `new QueueChannel(100)`, thao tác lấy message ra khỏi queue là thay đổi trên cấu trúc dữ liệu Java. Một JDBC transaction manager không thể khôi phục cấu trúc đó khi rollback cơ sở dữ liệu.

Ví dụ minh họa, giả sử `tx` là `TransactionTemplate` quản lý JDBC:

```java
QueueChannel memoryQueue = new QueueChannel(100);
memoryQueue.send(MessageBuilder.withPayload("ORDER-101").build());

try {
    tx.executeWithoutResult(status -> {
        Message<?> message = memoryQueue.receive(0);
        if (message == null) {
            throw new IllegalStateException("Không có message để xử lý");
        }
        jdbcTemplate.update(
                "insert into PROCESSED_ORDER (ORDER_ID) values (?)",
                message.getPayload());
        throw new IllegalStateException("Lỗi sau khi ghi dữ liệu");
    });
}
catch (IllegalStateException expected) {
    // JDBC rollback; queue trong bộ nhớ vẫn đã bị lấy mất message.
}
```

Gọi lại `memoryQueue.receive(0)` sẽ không nhận lại message vừa lấy. Thêm `@Transactional` vào service hoặc thêm `.transactional(...)` vào poller không tự biến queue trong bộ nhớ thành tài nguyên có khả năng rollback.

### 2.2. Lưu bền và tham gia transaction là hai thuộc tính khác nhau

| Đặc tính | Câu hỏi cần trả lời |
| --- | --- |
| Vùng đệm | Producer có thể gửi trước khi consumer sẵn sàng không? |
| Lưu bền | Message đã commit có tồn tại qua lần dừng hoặc sự cố tiến trình không? |
| Transaction | Thao tác thêm/lấy message có cùng commit hoặc rollback với tài nguyên nghiệp vụ không? |
| Xử lý lặp an toàn | Nếu cùng lệnh được thực hiện lại, kết quả nghiệp vụ có bị nhân đôi không? |

Một store lưu bền vẫn có thể bị dùng sai: nếu việc lấy message đã commit trước khi transaction nghiệp vụ bắt đầu, lỗi nghiệp vụ không khôi phục được message. Ngược lại, database H2 trong bộ nhớ dùng ở ví dụ sau hỗ trợ rollback nhưng không giữ dữ liệu qua lần chết tiến trình.

Spring Integration cho phép queue dựa trên message store; với store có hỗ trợ transaction và poller được cấu hình transaction, thao tác lấy message chỉ trở thành vĩnh viễn khi commit. Xem [Persistent QueueChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html#channel-configuration-queuechannel).

## 3. Ranh giới đúng: bắt đầu trước receive()

Một consumer cần bảo vệ cả thao tác lấy message khỏi store và các cập nhật nghiệp vụ:

```text
BEGIN transaction của consumer
    receive() từ QueueChannel dùng JDBC store
    validate / transform / route đồng bộ
    ghi dữ liệu nghiệp vụ bằng cùng DataSource
COMMIT nếu toàn bộ phần việc trong transaction thành công
ROLLBACK nếu transaction bị đánh dấu rollback
```

Nếu chỉ đặt `@Transactional` trên phương thức ghi dữ liệu, trình tự có thể trở thành:

```text
receive() và xóa message khỏi store ngoài transaction nghiệp vụ
    BEGIN transaction của service
        ghi dữ liệu
        gặp lỗi
    ROLLBACK transaction của service
```

Transaction thứ hai không thể hoàn tác phần việc đã hoàn tất trước khi nó bắt đầu. Vì vậy, với consumer đọc queue, poller là vị trí phù hợp để mở transaction bao quanh `receive()` và phần xử lý đồng bộ phía sau. Đây là lý do chính của [Poller Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-poller).

```mermaid
sequenceDiagram
    participant P as Producer
    participant Q as QueueChannel + JDBC store
    participant C as Transactional poller
    participant B as Business table
    P->>Q: send(command), commit enqueue
    C->>C: BEGIN consumer transaction
    C->>Q: receive()
    Q-->>C: command
    C->>B: INSERT kết quả
    alt Xử lý thành công
        C->>C: COMMIT
        Note over Q,B: Xóa message và ghi kết quả cùng commit
    else Lỗi trước commit
        C->>C: ROLLBACK
        Note over Q,B: Message vẫn còn; kết quả chưa được ghi nhận
    end
```

`receive()` không trả về một handle để ứng dụng gọi `ack()` hoặc `nack()`. Trong thiết kế này, trạng thái cuối cùng được quyết định bởi transaction của store.

### 3.1. Producer và consumer thường có hai transaction riêng

Giả sử producer chạy trên thread HTTP còn consumer chạy trên scheduler:

```text
Thread HTTP:       [Tx P: cập nhật nghiệp vụ + enqueue] -- commit
Thread scheduler:                                 [Tx C: dequeue + xử lý]
```

`Tx P` và `Tx C` độc lập. Lỗi ở consumer không làm rollback transaction HTTP đã commit. Nếu enqueue dùng cùng JDBC resource với dữ liệu producer, enqueue có thể tham gia `Tx P`; điều đó vẫn không làm `Tx C` trở thành phần tiếp nối của cùng transaction.

Trong mô hình JDBC thông thường, tài nguyên transaction được gắn với thread. Các endpoint đồng bộ có thể tiếp tục trong cùng phạm vi; khi phần xử lý chuyển sang thread khác, phạm vi đó không tự truyền sang. Xem [Transaction Boundaries](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-boundaries).

## 4. Ví dụ cấu hình: QueueChannel dùng JDBC store

Ví dụ dùng Java 17 trở lên, các API Java DSL hiện đại của Spring Integration, Spring JDBC và H2. Chọn các phiên bản Spring tương thích qua BOM của dự án hoặc dependency management của Spring Boot; không ghép tùy ý phiên bản các thư viện.

Các dependency cần có:

| Dependency | Mục đích |
| --- | --- |
| `org.springframework.integration:spring-integration-core` | Channel, endpoint, Java DSL |
| `org.springframework.integration:spring-integration-jdbc` | JDBC channel message store và schema mẫu |
| `org.springframework:spring-jdbc` | `JdbcTemplate`, JDBC transaction manager |
| `com.h2database:h2` | Database cho ví dụ và kiểm thử |
| JUnit Jupiter, Spring Test nếu dùng | Chạy kiểm thử trong dự án học tập |

Các khối Java dưới đây tương ứng với các tệp minh họa trong package `example.integration`. Chúng được trình bày trong bài để người học tự tạo trong dự án thực hành.

### 4.1. Payload có thể lưu bằng serialization mặc định

```java
package example.integration;

import java.io.Serializable;

public record OrderCommand(String orderId, boolean failAfterWrite)
        implements Serializable {

    private static final long serialVersionUID = 1L;
}
```

`failAfterWrite` chỉ là công tắc tạo lỗi xác định trong bài thực hành. Trong nghiệp vụ thật, lỗi có thể là deadlock, timeout hoặc vi phạm một ràng buộc xử lý.

JDBC channel store mặc định sử dụng Java serialization. Vì vậy payload và những giá trị header cần lưu phải phù hợp với cơ chế serialization đang dùng. Không đặt tùy tiện connection, stream hoặc service object vào message. Các tùy chọn serialization khác cần cấu hình tương ứng với phiên bản framework; xem [JDBC Channel Message Store Serialization](https://docs.spring.io/spring-integration/reference/jdbc/message-store-json.html).

### 4.2. Hạ tầng queue, store và transaction manager

```java
package example.integration;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.H2ChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class QueueStoreConfig {

    @Bean(destroyMethod = "shutdown")
    public EmbeddedDatabase dataSource() {
        EmbeddedDatabase database = new EmbeddedDatabaseBuilder()
                .generateUniqueName(true)
                .setType(EmbeddedDatabaseType.H2)
                .addScript("classpath:org/springframework/integration/jdbc/schema-h2.sql")
                .build();

        new JdbcTemplate(database).execute("""
                create table PROCESSED_ORDER (
                    ORDER_ID varchar(64) primary key,
                    STATUS varchar(32) not null
                )
                """);
        return database;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcChannelMessageStore orderMessageStore(DataSource dataSource) {
        JdbcChannelMessageStore store = new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new H2ChannelMessageStoreQueryProvider());
        store.setRegion("spring-integration-core-lab");
        return store;
    }

    @Bean
    public QueueChannel orders(JdbcChannelMessageStore orderMessageStore) {
        return new QueueChannel(
                new MessageGroupQueue(orderMessageStore, "orders-v1"));
    }
}
```

Các lựa chọn cần chú ý:

- `JdbcChannelMessageStore` được tối ưu cho channel; chọn query provider đúng hệ quản trị cơ sở dữ liệu. H2 provider ở đây chỉ dành cho database H2.
- `MessageGroupQueue` nối queue với store. `orders-v1` là group ID ổn định của queue logic; các queue độc lập cần định danh khác nhau.
- `region` tách không gian dữ liệu trong store. Khi phục hồi queue từ database lưu bền, cần dùng lại đúng region, group ID và cấu hình bảng.
- Cùng một bean `DataSource` được đưa vào store, `JdbcTemplate` và transaction manager.

Xem [JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html), [API MessageGroupQueue](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupQueue.html) và [DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

Schema mẫu thực tế nằm trong JAR tại `org/springframework/integration/jdbc/schema-h2.sql`, có bảng `INT_CHANNEL_MESSAGE` và cấu trúc liên quan. Dùng script khớp phiên bản dependency. Trong môi trường triển khai, quản lý schema bằng migration của dự án thay vì tạo lại bảng khi mỗi instance khởi động; xem [schema H2 của Spring Integration](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-jdbc/src/main/resources/org/springframework/integration/jdbc/schema-h2.sql).

H2 ở ví dụ này là database trong bộ nhớ để quan sát transaction. Muốn kiểm tra phục hồi sau khi tiến trình chết, cần một database lưu trên đĩa hoặc server database được cấu hình giữ dữ liệu.

### 4.3. Endpoint nhận message bằng transactional poller

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@Import(QueueStoreConfig.class)
public class OrderFlowConfig {

    @Bean
    public OrderWriter orderWriter(JdbcTemplate jdbcTemplate) {
        return new OrderWriter(jdbcTemplate);
    }

    @Bean
    public IntegrationFlow orderFlow(
            QueueChannel orders,
            OrderWriter orderWriter,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from(orders)
                .handle(orderWriter, "apply", endpoint -> endpoint
                        .id("orderConsumer")
                        .poller(Pollers.fixedDelay(500)
                                .receiveTimeout(0)
                                .maxMessagesPerPoll(1)
                                .transactional(transactionManager)))
                .get();
    }

    public static class OrderWriter {

        private final JdbcTemplate jdbcTemplate;

        public OrderWriter(JdbcTemplate jdbcTemplate) {
            this.jdbcTemplate = jdbcTemplate;
        }

        public void apply(OrderCommand command) {
            jdbcTemplate.update("""
                    insert into PROCESSED_ORDER (ORDER_ID, STATUS)
                    values (?, ?)
                    """, command.orderId(), "ACCEPTED");

            if (command.failAfterWrite()) {
                throw new IllegalStateException("Lỗi mô phỏng sau INSERT");
            }
        }
    }
}
```

Poller mở transaction trước khi lấy message. `OrderWriter` chạy đồng bộ trên thread thực hiện poll và dùng `JdbcTemplate` với cùng `DataSource`, nên thao tác ghi tham gia transaction đang có. Không cần thêm `@Transactional` vào `apply()` để ví dụ này có transaction.

`fixedDelay(500)` là khoảng trễ lịch poll; `receiveTimeout(0)` tránh chờ message trong ví dụ; `maxMessagesPerPoll(1)` giúp quan sát mỗi lượt xử lý. Những giá trị này không phải cấu hình tối ưu mặc định cho mọi hệ thống. API `.transactional(transactionManager)` áp dụng transaction advice lên polling task; xem [API PollerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html).

Một điểm dễ nhầm: với polling endpoint đồng bộ chuẩn, tăng `maxMessagesPerPoll` không có nghĩa tất cả message của một đợt lịch sẽ cùng nằm trong một transaction. Vòng lặp poll gọi tác vụ đã được advice cho từng lần lấy và xử lý. Nếu cần batch nguyên tử, phải thiết kế và kiểm chứng riêng; xem [mã nguồn AbstractPollingEndpoint](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java).

### 4.4. Gửi message và hiểu kết quả

Trong một bean khác, có thể inject `QueueChannel orders` và gửi:

```java
OrderCommand command = new OrderCommand("ORDER-101", false);
boolean accepted = orders.send(MessageBuilder.withPayload(command).build());
if (!accepted) {
    throw new IllegalStateException("Channel không nhận lệnh");
}
```

Với lệnh thành công, consumer commit: queue không còn message đó và bảng có dòng `ORDER-101`. Với `new OrderCommand("ORDER-102", true)`, lần xử lý ghi rồi ném lỗi; rollback làm dòng `ORDER-102` không được commit và message có thể được lấy lại ở lần poll sau.

Vì cờ gây lỗi nằm trong chính payload, `ORDER-102` sẽ tiếp tục thất bại nếu không có chính sách xử lý message lỗi. Không dùng mẫu này như cơ chế retry vô hạn trong ứng dụng thật.

Nếu producer muốn enqueue trong một transaction đã xác định, có thể dùng `TransactionTemplate`:

```java
TransactionTemplate producerTx = new TransactionTemplate(transactionManager);
producerTx.executeWithoutResult(status -> {
    // Có thể thực hiện cập nhật JDBC nghiệp vụ ở đây bằng cùng DataSource.
    boolean accepted = orders.send(MessageBuilder
            .withPayload(new OrderCommand("ORDER-103", false))
            .build());
    if (!accepted) {
        throw new IllegalStateException("Enqueue không thành công");
    }
});
```

Khi dùng JDBC store trong cấu hình trên, enqueue tham gia transaction producer. Exception trước commit có thể rollback việc thêm message. Sau commit, consumer bắt đầu transaction riêng khi đọc message; producer không chờ và không nhận trực tiếp kết quả xử lý của consumer.

## 5. Đọc đúng kết quả commit và rollback

Bảng dưới giả định không có consumer khác hoặc chính sách tự đưa lại message can thiệp:

| Cấu hình | Sau lỗi nghiệp vụ khiến transaction rollback | Trạng thái dữ liệu nghiệp vụ |
| --- | --- | --- |
| Queue trong bộ nhớ, JDBC transaction trên poller | Message đã lấy không tự trở lại queue | Phần ghi JDBC trong transaction bị rollback |
| JDBC queue, chỉ service ghi dữ liệu có transaction | Message có thể đã bị xóa ngoài transaction service | Service rollback, queue không được phục hồi bởi transaction đó |
| JDBC queue và transactional poller, dùng cùng JDBC resource | Việc lấy message bị rollback; message còn để đọc lại | Phần ghi cùng transaction bị rollback |
| JDBC queue và transactional poller, xử lý hoàn tất bình thường | Message bị xóa khi commit | Phần ghi cùng transaction được commit |
| JDBC queue và transactional poller, ghi qua database khác không được phối hợp | Chỉ tài nguyên thuộc transaction được rollback | Không bảo đảm nguyên tử giữa hai database |

Transaction không đồng nghĩa mọi thứ bên trong phương thức đều có thể hoàn tác. Một HTTP request đã được hệ thống bên ngoài chấp nhận, một email đã gửi hoặc thao tác trên file không tự được JDBC rollback.

Với nhu cầu gọi dịch vụ ngoài, một thiết kế có thể là ghi thêm công việc cần gửi vào một bảng outbox trong cùng transaction JDBC, rồi để một worker khác gửi. Worker đó vẫn cần khóa nghiệp vụ và xử lý lặp phù hợp. Đây là đề xuất thiết kế cho tình huống có tác dụng phụ bên ngoài, không phải khả năng tự động của `QueueChannel`.

## 6. Kết hợp với các thành phần cốt lõi khác

### 6.1. DirectChannel và executor

```text
JDBC queue -> transactional poller -> transformer
           -> DirectChannel -> service JDBC
```

Khi các bước đều đồng bộ, exception từ service có thể lan trở lại poller. Nếu cùng dùng tài nguyên JDBC đang được quản lý, cập nhật nghiệp vụ và dequeue có thể cùng rollback.

```text
JDBC queue -> transactional poller -> ExecutorChannel
                                    -> service trên thread khác
```

Sau khi tác vụ được bàn giao thành công cho executor, poller có thể commit mà không đợi service hoàn tất. Lỗi trên worker không tự khôi phục message ở queue đầu vào. Tương tự, thêm `@Async` hoặc tự tạo thread trong handler làm thay đổi phạm vi cần phân tích.

Đừng đồng nhất hai cấu hình: executor chạy **toàn bộ polling task** có thể vẫn cho phép transaction bắt đầu trên thread thực hiện poll; `ExecutorChannel` đặt **sau thao tác receive** tách phần xử lý phía sau ra khỏi thread đó.

### 6.2. Hai queue tạo hai chặng xử lý

```text
queue A -> poller A -> xử lý A -> queue B -> poller B -> xử lý B
```

Nếu hai queue JDBC cùng dùng resource được quản lý, transaction A có thể gộp việc lấy ở A, cập nhật dữ liệu A và thêm vào B. Transaction B xử lý việc lấy ở B và dữ liệu B. Lỗi ở B không rollback transaction A đã commit.

Vì vậy, bàn giao bền vững giữa các chặng có thể được thiết kế theo từng transaction cục bộ. Nó không tạo ra một transaction kéo dài tự động qua toàn bộ chuỗi bất đồng bộ.

### 6.3. Transformer, router, filter và aggregator

- **Transformer:** nếu chuyển đổi đồng bộ ném lỗi và lỗi lan ra poller, transaction có thể rollback. Nếu nó tạo payload mới để lưu ở queue tiếp theo, payload mới cũng phải phù hợp với serialization của store đó.
- **Router:** phạm vi thực tế phụ thuộc channel đích. Nhánh đồng bộ và nhánh executor/queue có hành vi bàn giao khác nhau; nhìn vào router riêng lẻ chưa đủ xác định transaction.
- **Filter:** message bị loại theo nhánh xử lý bình thường không mặc nhiên là lỗi transaction. Nếu luồng kết thúc bình thường, dequeue có thể commit. Cần quyết định rõ loại bỏ, chuyển discard channel hay coi trường hợp đó là thất bại.
- **Aggregator:** nhận một message và giữ nó chờ đủ nhóm là một kết quả bình thường. Queue đầu vào không giữ toàn bộ nhóm thay cho aggregator; việc lưu trạng thái nhóm cần store và chính sách phục hồi riêng. `JdbcChannelMessageStore` phục vụ channel, không thay cho generic store của aggregator.

Ví dụ với đơn hàng không hợp lệ: nếu yêu cầu là đưa vào queue `rejectedOrders`, hãy thiết kế việc chuyển đó như một kết quả xử lý có chủ đích. Nếu yêu cầu là chờ dữ liệu phụ trợ rồi thử lại, cần cơ chế retry hoặc trì hoãn rõ ràng; filter không tự cung cấp cơ chế ấy.

### 6.4. Gateway không xóa ranh giới queue

Messaging gateway giúp người gọi dùng một API phương thức thay vì thao tác message trực tiếp. Nếu gateway gửi vào queue để consumer xử lý trên thread khác, cú pháp gọi phương thức không làm transaction HTTP truyền sang consumer. Với gateway request-reply, caller timeout còn không chứng minh rằng consumer đã ngừng hoặc rollback; cần theo dõi trạng thái lệnh bằng định danh nghiệp vụ.

## 7. Exception, errorChannel và message lỗi lặp

### 7.1. Exception phải tới được ranh giới transaction

Một kiểu xử lý nguy hiểm:

```java
try {
    writeOrder(command);
}
catch (RuntimeException exception) {
    logger.warn("Ghi đơn thất bại", exception);
    // Luồng trả về bình thường dù yêu cầu nghiệp vụ chưa hoàn thành.
}
```

Nếu không có thành phần nào đánh dấu rollback, transaction có thể commit sau đoạn catch này và message bị tiêu thụ. Khi thất bại cần rollback, hãy để exception lan ra hoặc thực hiện chính sách rollback tường minh phù hợp với thiết kế.

Quy tắc mặc định của Spring rollback với `RuntimeException` và `Error`; checked exception cần xét cấu hình. Trong integration flow, lỗi gốc có thể được bọc thành một `MessagingException` thuộc nhóm runtime. Hãy kiểm tra exception thực tế mà transaction interceptor nhận, cùng rule đang áp dụng. Xem [Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

`@Transactional(rollbackFor = ...)` trên service không thay thế cấu hình của poller. Tương tự, `REQUIRES_NEW` trên một service có thể tạo transaction độc lập, khiến phần ghi đã commit của service không còn rollback cùng dequeue. Khi cần quy tắc riêng ở poller, truyền một `TransactionInterceptor` đã cấu hình vào `.transactional(interceptor)`; xem [TransactionInterceptorBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/TransactionInterceptorBuilder.html).

### 7.2. ErrorChannel là đường xử lý thông tin lỗi

Với scheduled poller dùng cơ chế xử lý lỗi chuẩn, lỗi từ tác vụ có thể được đóng gói thành `ErrorMessage` và gửi đến error channel. Đường này giúp log, phân loại và cảnh báo; xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Cần phân biệt:

- Handler tự bắt lỗi và trả về bình thường **trước khi** exception tới transaction interceptor có thể khiến transaction không rollback như mong muốn.
- Error handler ở lớp ngoài ghi nhận lỗi đã thoát khỏi transactional polling task không biến rollback trước đó thành commit.
- Gửi `ErrorMessage` để thông báo không đồng nghĩa đã di chuyển bền vững message gốc sang dead-letter queue.

Đừng mặc định viết một flow đọc `errorChannel` rồi gửi lại message gốc vào queue: message đã trở lại do rollback thì thao tác gửi lại có thể tạo thêm một bản sao.

### 7.3. Rollback không phải chính sách retry đầy đủ

Message bị rollback còn trong store nên có thể được poll lại. Hệ quả trong ví dụ là một payload luôn bật `failAfterWrite` sẽ liên tục thất bại. Ứng dụng cần phân biệt ít nhất lỗi tạm thời và lệnh không thể xử lý.

| Tình huống | Hướng thiết kế cho ví dụ đơn hàng |
| --- | --- |
| Database tạm thời không sẵn sàng | Thử lại có giãn cách, theo dõi tuổi message |
| Lệnh thiếu trường bắt buộc | Chuyển queue lỗi hoặc ghi trạng thái từ chối bền vững |
| Cùng `orderId` được gửi lần thứ hai | Kiểm tra kết quả đã tồn tại và quyết định idempotency |
| Dịch vụ ngoài trả kết quả không rõ ràng | Tra cứu theo khóa yêu cầu trước khi lặp tác dụng phụ |

Nếu dùng advice retry ngay trong transaction và bên dưới đã phát sinh lỗi JDBC, transaction có thể đã ở trạng thái không còn sử dụng được. Thứ tự transaction advice và retry advice quyết định mỗi lần thử dùng transaction mới hay dùng lại transaction cũ; không thêm retry rồi giả định dequeue đã được bảo vệ đúng.

Nếu bộ đếm lần thử được cập nhật trong chính transaction luôn rollback, số đếm cũng có thể quay lại giá trị cũ. Một chính sách giới hạn retry cần nơi lưu trạng thái và ranh giới commit phù hợp.

Việc chuyển message lỗi sang một JDBC queue khác có thể được thiết kế như kết quả thành công của một transaction: lấy khỏi queue nguồn, ghi thông tin lỗi, thêm vào queue đích rồi commit chung. Nếu transaction đó tiếp tục rollback thì thao tác thêm vào queue lỗi cũng rollback. Tránh gửi sang queue lỗi thuộc cùng transaction rồi ném exception mà vẫn mong message ở queue lỗi được giữ lại.

## 8. Kiểm thử điều gì và kiểm thử ở tầng nào?

Chỉ xác nhận rằng handler ném exception là chưa đủ. Hai quan sát quan trọng là **message có còn để đọc lại không** và **dữ liệu nghiệp vụ đã commit chưa**.

### 8.1. Kiểm thử storage transaction một cách xác định

Đoạn JUnit 5 dưới đây chỉ khởi tạo `QueueStoreConfig`, vì vậy không có consumer chạy nền tranh lấy message. Nó dùng `TransactionTemplate` để kiểm tra cùng phạm vi `receive()` + ghi dữ liệu. Đây là kiểm thử hành vi của store và transaction, chưa chứng minh cấu hình endpoint/poller hoạt động đúng.

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

class QueueTransactionTest {

    @Test
    void rollbackRestoresMessageAndUndoesBusinessInsert() {
        try (var context = new AnnotationConfigApplicationContext(
                QueueStoreConfig.class)) {
            var orders = context.getBean("orders", QueueChannel.class);
            var jdbc = context.getBean(JdbcTemplate.class);
            var tx = new TransactionTemplate(
                    context.getBean(PlatformTransactionManager.class));
            var writer = new OrderFlowConfig.OrderWriter(jdbc);

            assertTrue(orders.send(MessageBuilder
                    .withPayload(new OrderCommand("ROLLBACK-1", true))
                    .build()));

            assertThrows(IllegalStateException.class, () ->
                    tx.executeWithoutResult(status -> {
                        Message<?> message = orders.receive(0);
                        assertNotNull(message);
                        writer.apply((OrderCommand) message.getPayload());
                    }));

            assertEquals(0, count(jdbc, "ROLLBACK-1"));

            Message<?> availableAgain = orders.receive(0);
            assertNotNull(availableAgain);
            assertEquals("ROLLBACK-1",
                    ((OrderCommand) availableAgain.getPayload()).orderId());
            // Lần receive kiểm tra này tiêu thụ message của database thử nghiệm.
        }
    }

    @Test
    void commitRemovesMessageAndKeepsBusinessInsert() {
        try (var context = new AnnotationConfigApplicationContext(
                QueueStoreConfig.class)) {
            var orders = context.getBean("orders", QueueChannel.class);
            var jdbc = context.getBean(JdbcTemplate.class);
            var tx = new TransactionTemplate(
                    context.getBean(PlatformTransactionManager.class));
            var writer = new OrderFlowConfig.OrderWriter(jdbc);

            assertTrue(orders.send(MessageBuilder
                    .withPayload(new OrderCommand("COMMIT-1", false))
                    .build()));

            tx.executeWithoutResult(status -> {
                Message<?> message = orders.receive(0);
                assertNotNull(message);
                writer.apply((OrderCommand) message.getPayload());
            });

            assertEquals(1, count(jdbc, "COMMIT-1"));
            assertNull(orders.receive(0));
        }
    }

    private int count(JdbcTemplate jdbc, String orderId) {
        return jdbc.queryForObject(
                "select count(*) from PROCESSED_ORDER where ORDER_ID = ?",
                Integer.class, orderId);
    }
}
```

Mỗi test tạo database riêng nhờ `generateUniqueName(true)` và đóng database cùng application context. Không bọc toàn bộ test trong một transaction tự rollback: trạng thái cần quan sát là sau khi transaction consumer mẫu đã kết thúc.

### 8.2. Kiểm thử endpoint và poller thật

Với `OrderFlowConfig`, cần thêm kiểm thử bất đồng bộ cho cả cấu hình Java DSL. Có thể thực hiện theo trình tự:

1. Khởi tạo context có flow và chuẩn bị một handler thử nghiệm cho phép chặn ở vị trí xác định bằng latch.
2. Gửi message, đợi tín hiệu xác nhận handler thực sự đã nhận; không dùng một khoảng `sleep` tùy ý làm bằng chứng.
3. Cho handler hoàn tất hoặc ném exception theo kịch bản.
4. Đợi transaction kết thúc và tạm dừng consumer trước khi kiểm tra queue, tránh lần poll kế tiếp lấy mất message cần quan sát.
5. Kiểm tra cả bảng nghiệp vụ lẫn message trong queue, rồi giải phóng latch và tài nguyên dù test thất bại.

Các trường hợp nên có trong dự án thực hành:

| Kịch bản | Quan sát mong đợi |
| --- | --- |
| Handler thành công | Dòng nghiệp vụ có; message đã tiêu thụ |
| Lỗi sau INSERT | Dòng nghiệp vụ không có; message còn để đọc lại |
| Producer enqueue rồi rollback | Message mới không tồn tại sau rollback |
| Cùng logic nhưng đổi sang queue trong bộ nhớ | JDBC rollback nhưng message đã lấy không trở lại |
| Thêm executor sau queue | Lỗi worker không tự rollback dequeue đã commit |
| Filter loại message theo nhánh bình thường | Kết quả đúng chính sách discard đã lựa chọn |
| Khởi động lại với database lưu bền | Message đã commit nhưng chưa xử lý còn có thể được đọc |

Không mô tả kiểm thử restart bằng hai database H2 mới tạo tên khác nhau: chúng không cùng nơi lưu dữ liệu. Cần giữ nguyên database, định danh queue và cấu hình serialization để kiểm thử phục hồi có ý nghĩa.

Các khối kiểm thử ở đây là mã thực hành minh họa, không phải báo cáo rằng chúng đã được thực thi trong repository.

## 9. Tính lặp an toàn và giới hạn bảo đảm

Rollback để message được thử lại là nền tảng phục hồi, đồng thời buộc handler phải tính đến xử lý lặp. Không suy ra bảo đảm exactly-once toàn hệ thống chỉ từ việc queue dùng JDBC transaction.

Trong ví dụ, khóa chính `ORDER_ID` giúp ngăn hai dòng kết quả cùng ID. Tuy nhiên, nếu producer gửi lại cùng lệnh sau một lần xử lý đã commit, phép `INSERT` thứ hai sẽ lỗi; nếu chỉ rollback và poll lại thì lệnh trùng có thể mắc kẹt.

Một hướng mở rộng cho bài thực hành:

1. Chọn khóa nghiệp vụ biểu diễn một lệnh duy nhất, chẳng hạn `commandId`; phân biệt nó với `orderId` nếu một đơn hàng có nhiều lệnh hợp lệ.
2. Lưu kết quả thực hiện theo khóa đó trong cùng transaction với dữ liệu nghiệp vụ và dequeue.
3. Khi nhận lại lệnh đã hoàn tất, trả về kết quả đã ghi nhận hoặc kết thúc như một lần tiêu thụ thành công theo chính sách.
4. Dùng ràng buộc duy nhất và thuật toán ghi phù hợp với database để xử lý cả hai consumer chạy đồng thời; một phép kiểm tra tồn tại rồi ghi rời rạc là chưa đủ.
5. Với tác dụng phụ ngoài JDBC, truyền khóa idempotency hoặc thiết kế đối soát theo khả năng của hệ thống đích.

Đây là đề xuất nâng cấp mẫu đơn hàng. Mã `OrderWriter` ở trên cố ý chỉ thể hiện transaction và chưa triển khai chính sách idempotency hoàn chỉnh.

## 10. Lựa chọn vận hành và chẩn đoán

Giữ transaction consumer ngắn: khi một message đang được xử lý, transaction có thể giữ connection và khóa database. Chờ HTTP lâu trong cùng transaction làm tăng thời gian chiếm tài nguyên, dù lời gọi HTTP vẫn không được JDBC rollback.

Với nhiều consumer, cần kiểm chứng locking và SQL của query provider trên đúng database triển khai. Thứ tự lấy message không đồng nghĩa thứ tự hoàn tất nghiệp vụ khi xử lý đồng thời. Khi message đầu liên tục lỗi, mức độ cản các message sau còn phụ thuộc cách query và khóa; không mặc định queue nào cũng có cách vượt qua message lỗi giống nhau.

Những chỉ số hữu ích cho ví dụ đơn hàng là số message đang chờ, tuổi lệnh cũ nhất, số rollback, thời gian xử lý, số lần thất bại theo khóa lệnh và số lệnh chuyển sang hàng đợi lỗi.

| Hiện tượng | Giả thuyết cần kiểm tra trước |
| --- | --- |
| JDBC rollback nhưng lệnh biến mất | Queue trong bộ nhớ, `receive()` ở ngoài transaction, hoặc sai transaction manager |
| Queue còn lệnh nhưng dữ liệu đã ghi | Service dùng transaction độc lập, sai resource, hoặc tác dụng phụ đã xảy ra ngoài JDBC |
| Log cùng một ID liên tục | Message không xử lý được hoặc khóa trùng chưa có chính sách tiêu thụ |
| Queue lỗi trống dù đã gọi gửi | Việc thêm vào queue lỗi bị rollback cùng transaction thất bại |
| Sau restart không thấy message cũ | Database không lưu bền, đổi group ID/region hoặc trỏ sang database khác |
| Throughput thấp khi thêm consumer | Transaction dài, thiếu connection, cạnh tranh khóa hoặc SQL chưa phù hợp |

Khi chẩn đoán, ghi rõ channel implementation, store, thread, transaction manager và thời điểm commit/rollback của từng chặng. Các tên bean giống nhau hoặc các database URL trông giống nhau không đủ chứng minh các thao tác đã dùng chung tài nguyên transaction.

## 11. Tự kiểm tra kiến thức

1. **Thêm `.transactional(transactionManager)` vào poller của `new QueueChannel(100)` có giúp nhận lại message sau rollback không?** Không. JDBC transaction không hoàn tác cấu trúc queue trong bộ nhớ.
2. **Vì sao đặt transaction ở poller khác với chỉ đặt ở phương thức service?** Poller có thể đưa `receive()` vào phạm vi transaction; service bắt đầu sau đó thì không bảo vệ được dequeue đã hoàn tất.
3. **Một filter trả về kết quả loại bỏ bình thường có giữ message trong queue không?** Không mặc định. Nếu không có rollback, message có thể được tiêu thụ và transaction commit.
4. **Consumer lỗi có rollback transaction producer đã commit không?** Không. Đây là hai chặng với hai transaction riêng.
5. **Gửi message gốc lại từ error handler luôn là cách retry đúng không?** Không. Nếu dequeue đã rollback, message đã còn trong store; gửi lại có thể nhân bản lệnh.
6. **JDBC queue có tự bảo đảm email chỉ được gửi một lần không?** Không. Cần thiết kế riêng cho tác dụng phụ ngoài tài nguyên JDBC.

Khi tự thiết kế một flow, hãy đánh dấu từng vị trí `send()`, `receive()`, bàn giao thread và truy cập tài nguyên. Với mỗi transaction, xác định cụ thể thao tác nào cùng commit, thao tác nào cùng rollback và trạng thái nào giúp xử lý lặp an toàn.
