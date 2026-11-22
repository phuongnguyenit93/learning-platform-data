# Transactional poller

Trong chương **Poller transaction** của module **SPRING_INTEGRATION_CORE**, transactional poller giúp xác định khi nào việc nhận message và xử lý nghiệp vụ được xem là một đơn vị công việc thành công. Bài học nối Message, MessageChannel, endpoint và Java DSL với cơ chế quản lý transaction của Spring.

Ví dụ chính sử dụng hàng đợi JDBC chứa mã đơn hàng. Poller lấy message, gọi handler và ghi kết quả vào cùng cơ sở dữ liệu. Từ đó, ta phân tích commit, rollback, xử lý lỗi, xử lý lại và kiểm thử. Các đoạn Java dùng API của Spring Integration 6.5 và Java 17; dependency cần được quản lý đồng bộ bằng BOM phù hợp của ứng dụng.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích vì sao transaction phải bắt đầu trước thao tác nhận message.
- Đặt poller vào đúng endpoint trong Java DSL.
- Phân biệt tài nguyên hỗ trợ rollback với tài nguyên chỉ được gọi trong thời gian transaction đang mở.
- Xác định ranh giới transaction khi flow đi qua DirectChannel, QueueChannel hoặc ExecutorChannel.
- Kiểm chứng đồng thời trạng thái hàng đợi và dữ liệu nghiệp vụ.

Bạn nên biết Message gồm payload và headers, QueueChannel cần consumer chủ động nhận message, còn DirectChannel gọi subscriber đồng bộ.

## 2. Poller xuất hiện ở đâu?

| Tình huống | Thành phần polling | Thao tác nhận |
| --- | --- | --- |
| Endpoint đọc từ PollableChannel, chẳng hạn QueueChannel | PollingConsumer | Nhận message từ channel |
| Inbound adapter đọc nguồn bên ngoài | SourcePollingChannelAdapter | Gọi MessageSource để tạo hoặc lấy message |

Một service activator nhận dữ liệu từ QueueChannel cần poller tại endpoint của service activator. Một JDBC inbound adapter cần poller tại adapter đọc nguồn. DirectChannel không cần poller để chuyển message cho subscriber. Xem [Poller trong Spring Integration](https://docs.spring.io/spring-integration/reference/polling-consumer.html).

Poller có hai nhóm trách nhiệm:

1. **Lập lịch:** khi nào polling và tối đa bao nhiêu lần nhận trong một lượt được lập lịch.
2. **Bao quanh công việc:** áp dụng transaction advice và các advice khác.

Chỉ đặt chu kỳ một giây chưa tạo ra tính nguyên tử cho việc nhận và xử lý message.

## 3. Vì sao chỉ đặt @Transactional trên service có thể chưa đủ?

Xét thiết kế:

~~~text
QueueChannel
    -> receive message
    -> service có @Transactional
    -> cập nhật DB
~~~

Transaction tại service bắt đầu khi service được gọi. Thao tác lấy message xảy ra trước đó. Nếu cần khôi phục việc lấy message khi nghiệp vụ thất bại, ranh giới bắt đầu ở service là quá muộn.

Transactional poller đặt transaction advice quanh công việc polling, bao gồm nhận message và xử lý tiếp theo trong cùng luồng gọi. Nguồn phải thực sự tham gia transaction thì thao tác nhận mới có thể rollback. Xem [Poller Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html).

Mô hình mong muốn cho ví dụ:

~~~text
Bắt đầu transaction JDBC
    -> lấy message khỏi hàng đợi JDBC
    -> ghi nhận đơn hàng vào DB
    -> kết thúc xử lý đồng bộ
Commit cả hai thay đổi
~~~

Nếu handler ném lỗi trước commit:

~~~text
Bắt đầu transaction JDBC
    -> lấy message khỏi hàng đợi JDBC
    -> INSERT dữ liệu nghiệp vụ
    -> handler ném IllegalStateException
Rollback:
    - INSERT không được lưu
    - việc lấy message khỏi store không được xác nhận
~~~

Mô hình này giả định **cùng một tài nguyên JDBC**. Mọi hệ thống được gọi trong handler không tự động tham gia transaction đó.

## 4. Tài nguyên nào thực sự được rollback?

| Cấu hình | Khi handler thất bại |
| --- | --- |
| QueueChannel mặc định dùng bộ nhớ, handler ghi JDBC trong transaction | Ghi JDBC có thể rollback; message đã lấy không tự được đưa lại vào queue |
| QueueChannel dùng JdbcChannelMessageStore, poller và handler dùng cùng DataSource được quản lý | Việc lấy message và ghi DB có thể rollback cùng nhau |
| Nguồn file, handler ghi JDBC | Ghi JDBC có thể rollback; thao tác filesystem không tự trở thành ACID |
| Handler gửi HTTP rồi xảy ra lỗi JDBC | Yêu cầu HTTP đã được phía nhận thực hiện không tự được thu hồi |

QueueChannel mặc định giữ message trong bộ nhớ. Muốn lưu bền vững cần cấu hình message store hoặc hạ tầng messaging thích hợp. Với persistent store hỗ trợ transaction, việc loại message khỏi store chỉ trở thành thay đổi đã xác nhận khi transaction thành công. Xem [cấu hình persistent QueueChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Cần đánh giá riêng:

- **Durability:** message có còn sau khi tiến trình dừng không?
- **Transactional receive:** việc lấy message có thể hoàn tác cùng nghiệp vụ không?

Không thể chỉ nhìn tên QueueChannel để suy ra cả hai thuộc tính. Một store có lưu dữ liệu cũng cần được sử dụng với đúng transaction manager và cơ chế truy cập tài nguyên.

## 5. Ranh giới thread

### 5.1. Luồng xử lý đồng bộ

~~~mermaid
sequenceDiagram
    participant P as Thread của poller
    participant Q as Queue JDBC
    participant H as Handler
    participant D as DB nghiệp vụ
    P->>D: BEGIN
    P->>Q: receive()
    Q-->>P: Message
    P->>H: xử lý đồng bộ
    H->>D: INSERT
    alt Handler thành công
        H-->>P: hoàn tất
        P->>D: COMMIT
    else Handler ném lỗi
        H-->>P: RuntimeException
        P->>D: ROLLBACK
    end
~~~

Queue JDBC và DB nghiệp vụ trong sơ đồ dùng cùng DataSource; hai cột thể hiện hai vai trò.

DirectChannel gọi handler trên thread gửi message. ExecutorChannel giao công việc cho executor nên không bảo đảm duy trì transaction gắn với thread gọi. QueueChannel tạo điểm đệm để consumer nhận sau. Xem [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 5.2. Giao việc sang thread khác

~~~text
Thread A:
    BEGIN T1
    lấy message
    gửi vào ExecutorChannel
    việc giao công việc được chấp nhận
    trở về poller
    COMMIT T1

Thread B:
    handler chạy sau đó
    phát sinh lỗi
~~~

Lỗi trên thread B không tự rollback T1 đã commit. Commit diễn ra khi lời gọi được transaction advice bao quanh kết thúc, không phải ngay tại câu lệnh khai báo channel.

Đây là hệ quả thiết kế cần kiểm chứng khi thêm xử lý bất đồng bộ. Nếu cần hai chặng có khả năng phục hồi, có thể dùng hàng đợi lưu bền vững giữa hai chặng và transaction riêng cho từng consumer.

### 5.3. TaskExecutor của poller khác ExecutorChannel trong flow

TaskExecutor của poller đưa công việc polling sang worker thread. Transaction advice được áp dụng khi công việc đó chạy. Nếu các handler tiếp theo vẫn được gọi đồng bộ trên cùng worker thread, chúng vẫn có thể tham gia transaction.

ExecutorChannel nằm sau thao tác nhận lại tạo thêm một lần giao việc sang thread khác. Vì vậy, vị trí bắt đầu transaction và sơ đồ thực thi quan trọng hơn việc cấu hình có xuất hiện từ “executor” hay không.

API [PollerSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/PollerSpec.html) cung cấp riêng taskExecutor, transactional, receiveTimeout và errorChannel cho các trách nhiệm này.

## 6. Java DSL: nhận message và ghi DB trong một transaction

### 6.1. Chuẩn bị

Ví dụ cần:

- Java 17 cùng các dependency Spring có phiên bản tương thích.
- spring-integration-core, spring-integration-jdbc, spring-jdbc và PostgreSQL JDBC driver.
- DataSource bean tên **integrationDataSource**.
- Schema JDBC message store được khởi tạo trước khi tạo và khởi động các thành phần liên quan.
- Bảng nghiệp vụ trong cùng cơ sở dữ liệu mà integrationDataSource truy cập.

Dùng script schema phù hợp với phiên bản thư viện và DB. Trong JAR spring-integration-jdbc, script PostgreSQL nằm ở:

~~~text
org/springframework/integration/jdbc/schema-postgresql.sql
~~~

Script gồm bảng INT_CHANNEL_MESSAGE, sequence và index liên quan. Không chỉ tạo bảng nghiệp vụ rồi cho rằng message store đã sẵn sàng. Tham khảo [schema PostgreSQL của Spring Integration 6.5](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-jdbc/src/main/resources/org/springframework/integration/jdbc/schema-postgresql.sql).

Bảng dành riêng cho nghiệp vụ minh họa:

~~~sql
CREATE TABLE processed_order (
    order_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Quy tắc được chọn là: mỗi order_id chỉ ghi nhận một lần. Nếu một đơn có nhiều loại sự kiện, khóa chống trùng cần dựa vào event_id hoặc khóa nghiệp vụ phù hợp hơn.

### 6.2. Cấu hình phần integration

~~~java
import java.time.Duration;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.integration.transaction.TransactionInterceptorBuilder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.interceptor.TransactionInterceptor;

@Configuration
@EnableIntegration
public class TransactionalOrderFlowConfig {

    @Bean
    public PlatformTransactionManager pollerTxManager(
            @Qualifier("integrationDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate orderJdbcTemplate(
            @Qualifier("integrationDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public JdbcChannelMessageStore orderMessageStore(
            @Qualifier("integrationDataSource") DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        store.setRegion("transactional-orders-v1");
        return store;
    }

    @Bean
    public QueueChannel orderQueue(
            @Qualifier("orderMessageStore") JdbcChannelMessageStore store) {
        return new QueueChannel(
                new MessageGroupQueue(store, "order-queue"));
    }

    @Bean
    public QueueChannel orderPollerErrors() {
        return new QueueChannel(100);
    }

    @Bean
    public TransactionInterceptor orderPollerTxAdvice(
            @Qualifier("pollerTxManager")
            PlatformTransactionManager transactionManager) {
        return new TransactionInterceptorBuilder()
                .transactionManager(transactionManager)
                .propagation(Propagation.REQUIRED)
                .isolation(Isolation.READ_COMMITTED)
                .timeout(10)
                .readOnly(false)
                .build();
    }

    @Bean
    public IntegrationFlow orderConsumer(
            @Qualifier("orderQueue") QueueChannel input,
            @Qualifier("orderJdbcTemplate") JdbcTemplate jdbc,
            @Qualifier("orderPollerTxAdvice")
            TransactionInterceptor transactionAdvice) {
        return IntegrationFlow.from(input)
                .handle(String.class, (orderId, headers) -> {
                    if (orderId.isBlank()) {
                        throw new IllegalArgumentException(
                                "orderId must not be blank");
                    }

                    jdbc.update("""
                            INSERT INTO processed_order(order_id)
                            VALUES (?)
                            ON CONFLICT (order_id) DO NOTHING
                            """, orderId);

                    if (Boolean.TRUE.equals(
                            headers.get("simulateFailure"))) {
                        throw new IllegalStateException(
                                "Simulated failure after INSERT");
                    }

                    return null;
                }, endpoint -> endpoint
                        .id("orderPollingEndpoint")
                        .autoStartup(false)
                        .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                                .maxMessagesPerPoll(1)
                                .receiveTimeout(0)
                                .transactional(transactionAdvice)
                                .errorChannel("orderPollerErrors")))
                .get();
    }
}
~~~

Ví dụ không định nghĩa DataSource vì URL, tài khoản và connection pool thuộc cấu hình môi trường. Cần cung cấp đúng bean integrationDataSource trước khi dùng lớp trên.

Endpoint có autoStartup(false) để chuẩn bị dữ liệu rồi kích hoạt có kiểm soát trong buổi thực hành. Với luồng chạy tự động, cần chọn chính sách khởi động sau khi đã chuẩn bị schema và cấu hình vận hành.

### 6.3. Các điều kiện tạo tính nguyên tử

Ba thành phần cùng nhận integrationDataSource:

~~~text
DataSourceTransactionManager
JdbcChannelMessageStore
JdbcTemplate
~~~

DataSourceTransactionManager quản lý connection JDBC gắn với thread. JdbcTemplate dùng cơ chế lấy connection tham gia transaction của Spring. Tự lấy connection độc lập rồi tự commit có thể đi ra ngoài phạm vi này. Xem [DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

MessageGroupQueue kết nối QueueChannel với store. Group ID “order-queue” và region “transactional-orders-v1” cần ổn định sau restart để đọc tiếp cùng hàng đợi. Xem [MessageGroupQueue](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupQueue.html).

Query provider phải phù hợp PostgreSQL. Cách chọn, khóa và lấy message khác nhau theo DB; không dùng provider của DB khác. Tham khảo [JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html).

Handler trả về null vì đây là bước tiêu thụ cuối, không tạo reply. Null không biểu thị thất bại. Lỗi giả lập được ném sau INSERT để quan sát rollback dữ liệu đã thay đổi.

### 6.4. TransactionInterceptorBuilder

Builder tạo advice với propagation, isolation, timeout và readOnly đã chọn. Ở đây dùng constructor mặc định để tạo TransactionInterceptor cho poller. Constructor có tùy chọn handleMessageAdvice phục vụ phạm vi advice khác; không cần tùy chọn đó trong ví dụ này. Xem [TransactionInterceptorBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/TransactionInterceptorBuilder.html).

Nếu chỉ cần thuộc tính mặc định, có thể dùng transactional(transactionManager). Khi cần kiểm soát thêm thuộc tính, advice bean giúp thể hiện rõ cấu hình áp dụng.

### 6.5. Gửi message và khởi động endpoint

Đoạn sau chạy trong mã có ApplicationContext tên context, sau khi schema đã sẵn sàng:

~~~java
import org.springframework.context.Lifecycle;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;

QueueChannel orders =
        context.getBean("orderQueue", QueueChannel.class);

boolean accepted = orders.send(
        MessageBuilder.withPayload("ORDER-1001")
                .setHeader("correlationId", "practice-1001")
                .build(),
        1_000);

if (!accepted) {
    throw new IllegalStateException("Cannot enqueue order");
}

Lifecycle endpoint =
        context.getBean("orderPollingEndpoint", Lifecycle.class);
endpoint.start();
~~~

Chạy producer ngoài một transaction bao quanh toàn bộ bài thực hành, hoặc commit transaction producer trước khi khởi động consumer. Thành công của send xác nhận bước đưa message vào queue; chưa xác nhận handler đã commit.

Dùng fixture riêng cho nhánh lỗi:

~~~java
orders.send(
        MessageBuilder.withPayload("ORDER-FAIL-1002")
                .setHeader("simulateFailure", true)
                .setHeader("correlationId", "practice-failure-1002")
                .build(),
        1_000);
~~~

Payload String và các header String/Boolean phù hợp việc lưu message trong ví dụ. Với ứng dụng thật, cần chọn payload, headers và serializer phù hợp store; không mặc định lưu connection, stream hoặc đối tượng runtime tùy ý.

Message lỗi giữ nguyên simulateFailure sau rollback nên sẽ tiếp tục lỗi khi nhận lại. Dùng DB/queue riêng cho fixture lỗi và dừng endpoint sau khi quan sát. Lần polling sau không tự đổi header này.

### 6.6. Kết quả mong đợi

Với fixture thành công, sau khi transaction hoàn tất:

~~~sql
SELECT order_id
FROM processed_order
WHERE order_id = 'ORDER-1001';
~~~

Truy vấn trả về một dòng; message tương ứng không còn trong group của queue.

Với fixture lỗi, sau khi có thông báo lỗi và rollback hoàn tất:

- Không có dòng processed_order cho ORDER-FAIL-1002.
- Message vẫn có thể được nhận lại từ store.
- orderPollerErrors nhận ErrorMessage chứa thông tin lỗi.

Log “đã chạy INSERT” chưa chứng minh commit. Cần kiểm tra bằng connection quan sát độc lập sau khi transaction hoàn tất.

## 7. maxMessagesPerPoll có phải số message trong một transaction?

Trong poller đồng bộ thông thường, maxMessagesPerPoll giới hạn số lần nhận tối đa trong một lượt theo lịch. Transaction advice bao quanh từng công việc nhận và xử lý, không tự bao cả vòng lặp thành một transaction chung.

~~~text
Một lượt theo lịch, maxMessagesPerPoll = 3

    T1: receive A -> handle A -> commit
    T2: receive B -> handle B -> rollback do lỗi
    C : chưa được xử lý trong lượt bị ngắt bởi lỗi
~~~

A đã commit không bị hoàn tác vì B thất bại. Polling có thể kết thúc sớm khi không có message hoặc có exception. Xem cấu trúc polling task và vòng lặp trong [AbstractPollingEndpoint nhánh 6.5](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java).

Phân biệt **một message** với **một bản ghi**. JDBC inbound adapter có thể trả về một message chứa List nhiều dòng. maxMessagesPerPoll(1) lúc đó vẫn có thể đưa nhiều dòng nghiệp vụ vào cùng đơn vị xử lý. Adapter còn có thể chạy SELECT và UPDATE đánh dấu dữ liệu trong transaction của poller. Xem [JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html).

Khi thiết kế batch, hãy xác định:

1. Một receive trả một phần tử hay danh sách?
2. Splitter xử lý trên cùng thread hay giao sang thread khác?
3. Lỗi ở phần tử sau có quay về ranh giới transaction ban đầu không?
4. Cần tính nguyên tử cho cả danh sách hay từng phần tử?

Chọn maxMessagesPerPoll theo yêu cầu lập lịch sau khi đã trả lời các điểm trên.

## 8. Chọn thuộc tính transaction

### 8.1. Propagation

REQUIRED tạo transaction khi chưa có và tham gia transaction hiện hữu khi có, theo manager áp dụng. Với poller thông thường, đây là lựa chọn khởi đầu dễ hiểu.

Service downstream dùng REQUIRES_NEW tạo transaction độc lập. Nếu service commit rồi một bước sau thất bại, dữ liệu đó không rollback theo transaction poller. Cấu hình này cũng có thể cần thêm connection trong lúc transaction ngoài giữ connection. Xem [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

Trong ví dụ, không thêm REQUIRES_NEW vào INSERT nếu mục tiêu là lấy message và ghi nhận đơn hàng cùng thành công hoặc cùng thất bại.

### 8.2. Isolation và readOnly

Ví dụ chọn READ_COMMITTED. Tăng isolation có thể thay đổi khóa và cạnh tranh; không thay thế thuật toán lấy message, query provider hoặc khóa chống trùng.

Poller đọc queue JDBC có thể thay đổi store khi lấy message. Handler cũng INSERT, nên chọn readOnly(false). Từ “poll” hoặc “receive” chưa đủ để kết luận công việc chỉ đọc.

Khi tăng số consumer, đo bằng đúng DB, schema, provider và tải dự kiến; không suy ra mọi queue có cùng hành vi.

### 8.3. Timeout và thời gian chờ

| Tham số | Ý nghĩa trong ví dụ |
| --- | --- |
| fixedDelay(Duration.ofSeconds(1)) | Khoảng trễ lập lịch lần thực thi tiếp theo |
| receiveTimeout(0) | Không chờ nếu PollableChannel chưa có message sẵn |
| timeout(10) của transaction advice | Timeout transaction tính bằng giây |
| send(message, 1_000) | Giới hạn chờ khi gửi channel, tính bằng mili giây |

Timeout transaction không phải bộ hẹn giờ tự ngắt mọi lời gọi Java. Với JDBC, khả năng áp dụng phụ thuộc cách truy cập connection, statement và driver. HTTP cần timeout client riêng.

Transaction nên đủ thời gian cho xử lý dự kiến nhưng tránh giữ connection và khóa trong lúc chờ tác vụ chậm không cần tính nguyên tử với DB.

## 9. Exception, errorChannel và rollback

### 9.1. Exception phải tới đúng ranh giới

Theo mặc định của Spring, RuntimeException và Error dẫn tới rollback; checked exception không tự có cùng quy tắc nếu chưa cấu hình bổ sung. Trong messaging, lỗi handler có thể được bọc thành MessagingException, vốn là runtime exception. Phải xét exception thực tế đi tới transaction advice. Xem [Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

Đoạn sau dễ gây kết quả ngoài ý muốn:

~~~java
try {
    jdbc.update(
            "INSERT INTO processed_order(order_id) VALUES (?)",
            orderId);
    invokeBusinessStep();
}
catch (RuntimeException ex) {
    logger.warn("Processing failed for {}", orderId, ex);
}
~~~

Nếu lỗi bị nuốt, lời gọi có thể kết thúc bình thường và transaction có thể commit. Nếu một thành phần đã đánh dấu rollback-only, bắt exception không xóa cờ đó; lúc commit có thể nhận UnexpectedRollbackException.

Khi nghiệp vụ cần thất bại kéo theo rollback, hãy để lỗi phù hợp thoát ra ranh giới transaction, hoặc dùng cơ chế đánh dấu rollback được thiết kế rõ ràng.

### 9.2. errorChannel chuyển thông tin lỗi

Với công việc polling, framework có thể chuyển exception thành ErrorMessage để xử lý qua error channel. Đường đi này hỗ trợ ghi nhận, cảnh báo hoặc điều phối lỗi; không tự cung cấp hàng đợi phát lại hay chứng minh message nguồn được khôi phục. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Trong ví dụ:

~~~text
Handler ném lỗi
    -> transaction advice xử lý rollback
    -> cơ chế xử lý lỗi của polling task
    -> orderPollerErrors
~~~

Đây là đường đi của lỗi handler trước commit. Lỗi trong afterCommit có ý nghĩa khác vì DB có thể đã commit.

orderPollerErrors là QueueChannel có dung lượng giới hạn để quan sát. Nếu không được đọc, queue có thể đầy. Ứng dụng vận hành cần flow tiêu thụ lỗi và cách lưu vết phù hợp.

### 9.3. Flow kết thúc bình thường vẫn có thể commit

Filter loại message mà không ném lỗi là quyết định xử lý bình thường. Router chuyển message sang nhánh khác thành công cũng không biểu thị rollback.

Nếu yêu cầu là cách ly message không hợp lệ, hãy mô hình hóa nhánh cách ly. Nếu yêu cầu là giữ message để thử lại, ranh giới transaction phải nhận tín hiệu thất bại phù hợp. Hai yêu cầu có kết quả queue khác nhau.

## 10. Rollback, retry và xử lý lại

| Khái niệm | Vai trò |
| --- | --- |
| Rollback | Hoàn tác thay đổi của tài nguyên tham gia transaction |
| Retry tại handler | Gọi lại một bước theo chính sách advice |
| Xử lý lại từ nguồn | Consumer nhận lại message chưa được xác nhận hoặc đã được trả lại nguồn |

RequestHandlerRetryAdvice áp dụng retry cho handler. Trong cách dùng stateless thông thường, nó có thể gọi lại handler trên cùng thread. Nếu retry nằm bên trong transaction của poller, không mặc định mỗi lần thử có transaction JDBC mới. Xem [Retry Advice trong Spring Integration 6.5](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/classes.html).

Cách quan sát rõ ràng cho bài thực hành:

~~~text
Lần nhận thứ nhất:
    T1 -> nhận message -> ghi DB -> lỗi -> rollback

Lần nhận tiếp theo:
    T2 -> nhận lại message -> xử lý lại
~~~

Nếu transaction JDBC không còn dùng được sau lỗi SQL, thử lại handler trong cùng transaction có thể không giải quyết được. Cần xác định phạm vi retry, trạng thái transaction và tác động của recovery callback.

Recovery callback kết thúc bình thường có thể làm lời gọi ngoài thấy lỗi đã được xử lý. Kiểm thử kết quả queue và DB của đúng chuỗi advice thay vì chỉ đếm số lần gọi handler.

### Message lỗi vĩnh viễn

Header simulateFailure tạo message luôn thất bại. Transaction giữ khả năng nhận lại, nhưng không sửa dữ liệu sai hoặc lỗi nghiệp vụ vĩnh viễn.

Thiết kế vận hành cần quyết định:

- Lỗi nào thử lại, lỗi nào cách ly?
- Số lần thử lưu ở đâu để không mất khi restart?
- Khi vượt giới hạn, lấy khỏi nguồn và ghi nơi cách ly có tính nguyên tử ra sao?
- Ai sửa dữ liệu và phát lại?

Nếu bộ đếm thử lại nằm trong cùng transaction luôn rollback, bộ đếm cũng có thể rollback. Biến cục bộ hoặc header mới tạo rồi mất sau rollback không đủ cho chính sách bền vững.

## 11. Idempotency khi có khả năng xử lý lại

Thiết kế cần xét message trùng, lần gửi lại từ producer và tác dụng phụ bên ngoài DB.

Unique key order_id kết hợp ON CONFLICT DO NOTHING giúp ví dụ không tạo thêm dòng khi mã đơn đã tồn tại. PostgreSQL cung cấp ON CONFLICT để chọn hành vi khi va chạm ràng buộc duy nhất. Xem [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html).

Đây là lựa chọn theo quy tắc “mỗi đơn ghi nhận một lần”. Nếu cùng order_id nhưng nội dung khác, bỏ qua va chạm có thể che lỗi dữ liệu. Ứng dụng thật cần quyết định kiểm tra payload, phiên bản hoặc event_id.

Giả sử thêm yêu cầu thu tiền HTTP:

~~~text
Nhận message
    -> cổng thanh toán xử lý thành công
    -> ghi DB
    -> DB lỗi, rollback
    -> nhận lại message
    -> có thể gọi thu tiền lần nữa
~~~

Đây là phân tích tình huống của ví dụ: transaction JDBC không đủ để khẳng định tác dụng phụ ngoài DB chỉ xảy ra một lần. Có thể cần idempotency key do cổng thanh toán hỗ trợ hoặc thiết kế lưu yêu cầu phát đi trong outbox.

Không gắn nhãn “exactly once toàn hệ thống” chỉ vì poller đã transactional.

## 12. Transaction synchronization và pseudo transaction

### 12.1. Callback theo kết quả transaction

Spring có beforeCommit, afterCommit và afterCompletion. Lỗi trước commit có thể làm rollback; công việc chạy sau commit không thu hồi được commit đã hoàn tất. Nếu callback sau commit cần ghi DB, phải xác định transaction riêng cho thao tác đó. Xem [TransactionSynchronization](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html).

Spring Integration cung cấp TransactionSynchronizationFactoryBean để cấu hình hành động theo kết quả xử lý. Ví dụ gửi payload tới các channel tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.transaction.TransactionSynchronizationFactoryBean;

@Bean
public TransactionSynchronizationFactoryBean fileCompletionSync() {
    return new TransactionSynchronizationFactoryBean()
            .afterCommit("payload", "filesCommitted")
            .afterRollback("payload", "filesRolledBack");
}
~~~

Đây là cấu hình bổ sung cho flow file riêng, không thuộc flow đơn hàng. Nó cần hai channel đã khai báo và các handler tương ứng. Truyền factory được Spring tạo vào poller của flow file:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(1))
        .transactional(fileTransactionManager)
        .transactionSynchronizationFactory(fileCompletionFactory);
~~~

fileTransactionManager và fileCompletionFactory là các bean được inject vào cấu hình flow file đó. Xem các phương thức và ý nghĩa FactoryBean trong [TransactionSynchronizationFactoryBean API](https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/TransactionSynchronizationFactoryBean.html).

Nếu handler filesCommitted di chuyển file thất bại, transaction chính đã commit. Cần cách ghi nhận và đối soát; callback không biến DB và filesystem thành transaction phân tán.

### 12.2. PseudoTransactionManager

PseudoTransactionManager hỗ trợ điều phối hành động theo vòng đời xử lý cho nguồn không có transaction thực sự; nó không biến nguồn thành tài nguyên transactional. Xem [PseudoTransactionManager](https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/PseudoTransactionManager.html).

~~~text
Flow hoàn tất -> hành động sau thành công
Flow lỗi     -> hành động sau thất bại
~~~

Không thay DataSourceTransactionManager trong ví dụ đơn hàng bằng PseudoTransactionManager rồi kỳ vọng INSERT và việc lấy message JDBC vẫn rollback. Hai manager phục vụ mục đích khác nhau.

## 13. Kiểm thử ranh giới transaction

Cần xác nhận một cặp trạng thái: **message nguồn** và **dữ liệu nghiệp vụ**. Handler được gọi chưa chứng minh commit hoặc rollback.

Spring Integration có các module hỗ trợ kiểm thử flow và thành phần. Kiểm thử transaction vẫn cần tài nguyên thực sự hỗ trợ hành vi cần quan sát. Xem [Testing support](https://docs.spring.io/spring-integration/reference/testing.html).

### 13.1. Ma trận kiểm thử đề xuất

| Kịch bản | Bằng chứng sau khi hoàn tất |
| --- | --- |
| ORDER-1001 thành công | Một dòng processed_order, message rời queue |
| Lỗi sau INSERT | Không có dòng nghiệp vụ, message nhận lại được |
| Gửi lặp order_id đã thành công | Chỉ một dòng nghiệp vụ, message mới được tiêu thụ |
| Thay bằng queue bộ nhớ trong fixture riêng | DB rollback nhưng message không tự khôi phục |
| Chèn ExecutorChannel trước handler trong fixture riêng | Giao việc thành công chưa chứng minh downstream đã commit |
| Restart sau enqueue, trước consume | Đọc được message với cùng DB, region và group |
| Nhận A rồi B, B lỗi trong cùng lượt theo lịch | A đã commit; B rollback |

Đây là kế hoạch thực hành cho người học, không phải tuyên bố các kiểm thử đã được chạy.

### 13.2. Tổ chức fixture

1. Khởi tạo schema và dùng DB hoặc vùng dữ liệu riêng cho từng kịch bản.
2. Giữ endpoint dừng khi chuẩn bị và enqueue.
3. Commit producer trước khi consumer chạy.
4. Khởi động endpoint, chờ sự kiện hoàn tất với timeout.
5. Dừng endpoint, đợi công việc đang chạy hoàn tất rồi kiểm tra queue.
6. Đọc DB bằng transaction/connection quan sát mới.
7. Dọn fixture sau khi có đủ bằng chứng.

Không dùng Thread.sleep với một khoảng cố định làm bằng chứng duy nhất. Có thể dùng latch gắn với sự kiện hoàn tất hoặc chờ điều kiện có timeout.

Không bọc cả test trong @Transactional rồi mặc định poller chia sẻ transaction của test. Nếu test chưa commit dữ liệu producer, consumer có thể chưa nhìn thấy message.

Không gọi orderQueue.receive() để “xem thử” khi poller vẫn chạy. Receive tiêu thụ message và có thể làm thay đổi kết quả.

### 13.3. Kiểm tra transaction đang hoạt động

Có thể thêm tạm vào handler của fixture:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

if (!active) {
    throw new IllegalStateException(
            "Expected an active transaction in handler");
}
~~~

Cờ active chỉ chứng minh có transaction trên thread đó. Để chứng minh đúng connection/store tham gia, vẫn cần thử rollback và kiểm tra dữ liệu.

### 13.4. Kiểm tra message có thể nhận lại

Sau khi poller dừng và không còn công việc đang chạy, dùng transaction quan sát rồi rollback thao tác nhận:

~~~java
import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

TransactionTemplate probe = new TransactionTemplate(
        context.getBean(
                "pollerTxManager",
                PlatformTransactionManager.class));

Message<?> redelivered = probe.execute(status -> {
    Message<?> candidate = orders.receive(0);
    status.setRollbackOnly();
    return candidate;
});

if (redelivered == null
        || !Objects.equals(
                redelivered.getPayload(), "ORDER-FAIL-1002")) {
    throw new AssertionError(
            "Expected the failed order to remain available");
}
~~~

Đoạn kiểm tra dành cho fixture riêng chỉ có message lỗi cần quan sát. Rollback của probe giữ lại message trong queue JDBC. Nó không chứng minh hành vi tương tự cho queue bộ nhớ.

## 14. Đọc triệu chứng để tìm sai ranh giới

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| DB rollback nhưng message biến mất | Queue bộ nhớ, receive ngoài transaction hoặc sai manager |
| Một phần dữ liệu còn sau lỗi | REQUIRES_NEW, auto-commit hoặc tài nguyên commit độc lập |
| Lỗi xuất hiện trên thread khác | ExecutorChannel, @Async hoặc tác vụ tự tạo thread |
| Message lỗi được nhận liên tục | Chưa có chính sách cách ly lỗi vĩnh viễn |
| Có log lỗi nhưng DB commit | Exception bị nuốt hoặc nhánh lỗi kết thúc bình thường |
| Test không thấy consumer xử lý | Endpoint chưa start, producer chưa commit hoặc sai group/region |
| Restart không thấy message cũ | Đổi DB, region, group ID hoặc không dùng store lưu bền vững |
| Thêm HTTP làm transaction giữ khóa lâu | Lời gọi ngoài DB nằm trong thời gian transaction mở |

Lần theo message bằng khóa nghiệp vụ và correlationId, ghi thread name, thời điểm nhận, thời điểm handler hoàn tất và kết quả transaction. Chỉ log payload cần thiết cho chẩn đoán.

## 15. Quy trình thiết kế

Viết rõ đơn vị công việc trước khi chọn cấu hình:

~~~text
Đầu vào:
    Một message chứa một mã đơn hàng

Thành công:
    Message rời hàng đợi JDBC
    Đơn hàng được ghi nhận trong cùng DB

Thất bại trước commit:
    Không lưu thay đổi nghiệp vụ
    Message còn khả năng được nhận lại

Ngoài phạm vi:
    HTTP, email và filesystem không tự rollback theo JDBC
~~~

Sau đó:

1. Chọn nguồn có ngữ nghĩa nhận và phục hồi phù hợp.
2. Đặt transaction trước receive tại poller.
3. Giữ các bước cần tính nguyên tử trên cùng thread và tài nguyên được quản lý.
4. Chọn rõ transaction manager khi có nhiều manager.
5. Chọn khóa chống trùng theo nghiệp vụ.
6. Xác định đường đi khi lỗi và vượt giới hạn thử lại.
7. Kiểm chứng thành công, lỗi sau ghi DB và thay đổi ranh giới thread.

Với flow đơn hàng trong bài, phải chứng minh được cả hai kết quả: việc nhận và ghi DB cùng commit khi thành công, hoặc các thay đổi đó cùng rollback khi handler thất bại trước commit.
