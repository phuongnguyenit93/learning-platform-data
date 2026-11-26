# Transaction manager theo resource trong Spring Batch

Một Spring Batch job đọc dữ liệu qua JDBC, dùng JPA cập nhật nghiệp vụ rồi gửi message qua RabbitMQ. Lập trình viên đặt `@Transactional` ở service và tin rằng cả ba thao tác sẽ cùng commit hoặc rollback. Khi database đã ghi thành công nhưng broker chưa nhận message, job có thể restart và thực hiện một số tác dụng phụ lần nữa. Nguyên nhân không chỉ do retry: **mỗi transaction manager có phạm vi resource riêng**, và một annotation không tự tạo giao dịch nguyên tử giữa database, broker và HTTP API.

Bài **“Transaction manager theo resource”** thuộc chương **Transaction boundary** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế.

Nguyên tắc của bài: **chọn transaction manager theo resource thực sự cần commit/rollback**, không dựa chỉ vào tên bean hoặc framework đang dùng. Nếu một công việc liên quan nhiều resource không nằm chung transaction, phải thiết kế idempotency, trạng thái bền vững và đối soát thay vì hứa rằng mọi side effect đều exactly-once.

Ví dụ hướng tới **Spring Batch 5.2.x, Spring Framework 6.x và Java 17+**. Các đoạn mã Java là cấu hình/khối logic có chú thích dependency; không phải ứng dụng độc lập đầy đủ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `PlatformTransactionManager` và phạm vi resource mà một implementation quản lý.
2. Phân biệt transaction của **worker chunk**, **JobRepository**, **message listener**, **broker producer** và **external API**.
3. Chọn đúng `JdbcTransactionManager`/`DataSourceTransactionManager`, `JpaTransactionManager`, `JmsTransactionManager`, `RabbitTransactionManager`, `KafkaTransactionManager` hoặc `JtaTransactionManager`.
4. Cấu hình nhiều datasource và chỉ định transaction manager tường minh cho một Spring Batch Step 5.2.
5. Phân tích khoảng lỗi giữa business DB commit và `JobRepository` checkpoint khi hai bên dùng manager khác nhau.
6. Nhận diện bẫy `@Transactional` chọn nhầm bean, `REQUIRES_NEW`, `@Async`, lỗi checked exception và self-invocation.
7. So sánh giao dịch JDBC/JMS local, transaction synchronization, JTA/XA với outbox/inbox và idempotency.
8. Thiết kế writer, listener và retry/restart không tạo duplicate business effect dù message hoặc chunk bị replay.
9. Thực hiện integration tests xác minh rollback thật ở từng resource, kiểm tra metadata sau crash.
10. Chọn concurrency, chunk size và ngân sách connection phù hợp SLA cùng các ranh giới transaction.

## 2. Transaction manager là gì, và quản lý thứ gì?

`PlatformTransactionManager` là giao diện **imperative transaction management** của Spring, cho phép tầng gọi bắt đầu, commit hoặc rollback transaction thông qua `TransactionDefinition` và `TransactionStatus`:

~~~java
// Mô tả khái niệm các method quan trọng, không phải full Javadoc:
TransactionStatus status = manager.getTransaction(definition);
try {
    performBusinessWork();
    manager.commit(status);
} catch (RuntimeException error) {
    manager.rollback(status);
    throw error;
}
~~~

Trong Spring Batch, `StepBuilder.chunk(size, transactionManager)` hoặc `StepBuilder.tasklet(tasklet, transactionManager)` thường điều phối boundary này. Với service ứng dụng, Spring AOP của `@Transactional` hoặc `TransactionTemplate` có thể thực hiện tương tự.

Nhưng **commit** chỉ có nghĩa cho những resource mà manager đang quản lý. Ví dụ:

- `JdbcTransactionManager` quản lý JDBC connection thuộc đúng `DataSource` của nó.
- `JpaTransactionManager` quản lý JPA persistence context/EntityManager thuộc đúng `EntityManagerFactory`.
- `JmsTransactionManager` quản lý local JMS Session thuộc một `ConnectionFactory`.
- `KafkaTransactionManager` quản lý transaction của transactional Kafka producer factory.
- `JtaTransactionManager` giao việc điều phối cho một global transaction coordinator nếu các resource được cấu hình XA.

Tên `transactionManager` là bean name thông thường, **không phải một lời hứa rằng manager bao mọi resource**. Để SQL, message hoặc persistence context tham gia transaction, API được sử dụng phải thực sự lấy resource qua factory/adapter tương thích.

### 2.1. Transaction domain và phạm vi thực thi

Một imperative local transaction thường ràng buộc resource state với **thread** đang chạy thông qua `TransactionSynchronizationManager`. Nếu code khởi tạo một task mới bằng `@Async` hoặc executor, task đó không tự nhận transaction hiện tại. Nếu một worker Spring Batch chạy trên JVM khác, không có transaction object Java nào được gửi theo message.

Transaction có thể bắt đầu logic trước khi JDBC connection vật lý được lấy, tùy manager, lazy proxy và database access. Vì vậy cần phân biệt **transaction lifetime** và **connection hold time**, dù cả hai đều có thể ảnh hưởng throughput và lock contention.

### 2.2. Sơ đồ các resource boundaries

~~~mermaid
flowchart TB
    B["Spring Batch Worker Step"] --> T["Step PlatformTransactionManager"]
    T --> D[("Business DB/JPA Resource")]
    B --> R["JobRepository"]
    R --> RT["Repository Transaction Manager"]
    RT --> M[("Batch metadata DB")]
    B --> MQ["Message / Kafka / HTTP"]
    MQ -.-> X["Không tự tham gia DB local transaction"]
~~~

Hai đường từ Step tới database metadata và business có thể dùng cùng datasource/manager hoặc hai domain hoàn toàn độc lập. Message/network thường là resource khác và có cơ chế ack/commit riêng.

## 3. Bảng lựa chọn transaction manager theo resource

| Resource chủ đạo | Manager thông dụng | Phạm vi | Giới hạn phải nhớ |
| --- | --- | --- | --- |
| JDBC một `DataSource` | `JdbcTransactionManager` hoặc `DataSourceTransactionManager` | SQL qua đúng datasource và transaction-aware connection access | Không tự rollback datasource thứ hai |
| JPA/Hibernate | `JpaTransactionManager` | `EntityManagerFactory`/persistence context tương ứng | Không tự giao dịch với JPA factory khác hay broker |
| JMS | `JmsTransactionManager` | Local JMS Session/ConnectionFactory | Không atomic với JDBC database riêng |
| RabbitMQ | `RabbitTransactionManager` | Rabbit channel transaction | Spring AMQP **không hỗ trợ XA** với DB |
| Kafka | `KafkaTransactionManager` | Transactional producer thuộc producer factory tương ứng | Không tự atomic với JDBC commit |
| XA JDBC và XA JMS | `JtaTransactionManager` | Resource được global coordinator enlist đúng | Cần XA-aware factories, coordinator và recovery |
| In-memory/logic không có transactional resource | `ResourcelessTransactionManager` | Không rollback JDBC/JPA data | Không dùng cho writer cần DB atomicity |
| R2DBC/reactive processing | `R2dbcTransactionManager` | Reactive transaction theo Reactor context | Không trực tiếp là imperative `PlatformTransactionManager` |

Tên class/package thường gặp:

~~~text
org.springframework.jdbc.support.JdbcTransactionManager
org.springframework.jdbc.datasource.DataSourceTransactionManager
org.springframework.orm.jpa.JpaTransactionManager
org.springframework.jms.connection.JmsTransactionManager
org.springframework.amqp.rabbit.transaction.RabbitTransactionManager
org.springframework.kafka.transaction.KafkaTransactionManager
org.springframework.transaction.jta.JtaTransactionManager
org.springframework.batch.support.transaction.ResourcelessTransactionManager
org.springframework.r2dbc.connection.R2dbcTransactionManager
~~~

Các dependency JMS/AMQP/Kafka/JPA/R2DBC là **tùy chọn**: không phải cứ có Spring Batch là mọi class ở bảng trên đã nằm trên classpath.

### 3.1. Local transaction, global transaction và eventual consistency

**Local transaction** thường chỉ bảo vệ một transactional resource hoặc transaction domain. Hai local managers commit lần lượt vẫn có khoảng lỗi giữa hai commit.

**Global transaction/JTA XA** có thể điều phối nhiều resource hỗ trợ XA theo **two-phase commit**, nếu được cấu hình XA và enlist thực sự. Không thể mặc định đưa HTTP API, RabbitMQ hoặc Kafka vào XA chung chỉ vì gọi chúng trong một method.

**Eventual consistency** dùng outbox/inbox, durable state, replay và idempotency để mỗi resource commit riêng nhưng có đường phục hồi. Đây thường là lựa chọn thực tế khi service phải giao tiếp qua HTTP hoặc publish message tới broker không cùng XA domain.

## 4. JobRepository transaction khác Step transaction ở điểm nào?

Spring Batch chunk-oriented step có hai dependency quan trọng:

~~~java
@Bean
public Step processStep(
        JobRepository jobRepository,
        @Qualifier("businessTxManager") PlatformTransactionManager businessTx,
        ItemReader<OrderRow> reader,
        ItemWriter<OrderRow> writer) {

    return new StepBuilder("processStep", jobRepository)
            .<OrderRow, OrderRow>chunk(200, businessTx)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

- `JobRepository` quản lý `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext`.
- `businessTx` điều phối transaction **chunk processing**: read/process/write và cập nhật metadata theo lifecycle của step.

Trong Spring Batch 5.2, transaction manager của Step **có thể khác** manager mà `JobRepository` sử dụng. Tài liệu chính thức cảnh báo chính trường hợp này: database nghiệp vụ và batch metadata sẽ **không tự nằm trong cùng một transaction**, nên một lỗi sau khi xử lý có thể dẫn đến item được xử lý lại khi restart.

### 4.1. Chunk transaction và checkpoint

~~~mermaid
sequenceDiagram
    participant S as Chunk Step
    participant T as Step TX Manager
    participant D as Business DB
    participant R as JobRepository
    S->>T: BEGIN
    S->>D: Read / Process / Write chunk
    S->>R: Persist StepExecution + ExecutionContext
    S->>T: COMMIT (hoặc ROLLBACK)
    Note over D,R: Atomic chỉ khi metadata và business thực sự cùng transaction
~~~

Trong chunk-oriented step mặc định, framework cập nhật checkpoint/status trước khi commit chunk theo lifecycle của `TaskletStep`. Nếu repository và writer cùng dùng **một datasource và một transaction manager**, repository operations có thể tham gia cùng local transaction đúng cấu hình.

Nếu repository nằm trên datasource khác, có thể có tình huống:

~~~text
Business database A: chunk data đã COMMIT
Metadata database B: checkpoint vẫn là trạng thái cũ
Process: JVM crash / metadata update failure
Restart: reader có thể xử lý lại item đã có ở A
~~~

Ngược lại, khi metadata tiến trước nhưng business write rollback, có rủi ro bỏ sót. Thứ tự và trạng thái cụ thể tùy propagation, point of failure và configuration; **không thiết kế dựa trên một thứ tự commit ngầm định**.

### 4.2. Vì sao checkpoint cần bền vững?

`ExecutionContext` giữ vị trí reader/step state phục vụ restart. Nếu metadata bị mất hoặc không tương ứng với business commits, thuật toán restart không thể tự đoán dữ liệu nào đã xử lý ở resource khác.

Bảo vệ bằng **source snapshot bất biến, business key idempotent, transaction boundaries được kiểm thử và reconciliation**. Không sửa thủ công trạng thái `BATCH_STEP_EXECUTION` thành `COMPLETED` để che discrepancy.

## 5. JDBC: chọn transaction manager theo DataSource

Với business writer sử dụng `JdbcTemplate`/`JdbcBatchItemWriter` trên một datasource, cấu hình điển hình:

~~~java
@Bean("ordersTxManager")
public PlatformTransactionManager ordersTxManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

`JdbcTransactionManager` là biến thể của `DataSourceTransactionManager` có thêm dịch exception tại commit/rollback. Cả hai quản lý JDBC local transaction trên datasource được cung cấp.

Để resource thực sự tham gia:

- `JdbcTemplate`/`NamedParameterJdbcTemplate` dùng đúng datasource đó.
- Code truy cập connection qua cơ chế Spring-aware, chẳng hạn `DataSourceUtils`, thay vì tạo connection độc lập qua `DriverManager`.
- Nếu dùng routing datasource, cần kiểm tra datasource đang được chọn theo thread/context và read/write routing.
- Một driver, reader cursor hoặc transaction manager khác có thể giữ connection riêng; đo lifetime thực.
- Cùng JDBC URL nhưng hai pools/connections khác nhau **không có nghĩa cùng local transaction**.

### 5.1. TransactionTemplate: ranh giới có chủ đích

~~~java
@Service
public class OrderOrchestrator {
    private final TransactionTemplate tx;
    private final OrderDao orders;
    private final RemoteService remote;

    public OrderOrchestrator(
            @Qualifier("ordersTxManager") PlatformTransactionManager tm,
            OrderDao orders,
            RemoteService remote) {
        this.tx = new TransactionTemplate(tm);
        this.orders = orders;
        this.remote = remote;
    }

    public void process(long orderId) {
        tx.executeWithoutResult(s -> orders.markPending(orderId));

        // Đã COMMIT transaction thứ nhất, miễn là caller
        // không giữ outer transaction qua method này.
        remote.callWithIdempotencyKey(orderId, "op-" + orderId);

        tx.executeWithoutResult(s -> orders.markReady(orderId));
    }
}
~~~

`OrderDao` và `RemoteService` là kiểu minh họa của ứng dụng. Mẫu này phải được chạy **ngoài outer chunk/tasklet transaction**; nếu đã có một transaction `REQUIRED` của cùng manager bao quanh, các `TransactionTemplate` mặc định có thể tham gia outer transaction và call mạng lại nằm trong transaction dài. Cần durable work state, retry, fencing và reconciliation để phục hồi crash giữa ba bước, không chỉ ba dòng code.

### 5.2. Reader DB A và writer DB B

Một Step có thể đọc datasource A và ghi datasource B. Nếu manager chunk quản lý B, việc đọc A **không tự tham gia transaction B**. Không mặc định rollback B làm cursor/snapshot của A “quay lại” chính xác.

Đối với data migration lớn, thường có thể dùng **immutable snapshot ở A + upsert idempotent ở B + JobRepository checkpoint**, thay vì yêu cầu XA qua hai database khi không thật sự cần atomic consistency thời điểm.

## 6. JPA/Hibernate: dùng manager đúng EntityManagerFactory

Khi Step ghi entity bằng JPA, transaction manager thường nên là `JpaTransactionManager` của đúng `EntityManagerFactory`:

~~~java
@Bean("billingJpaTxManager")
public PlatformTransactionManager billingJpaTxManager(
        @Qualifier("billingEntityManagerFactory") EntityManagerFactory emf) {
    return new JpaTransactionManager(emf);
}

@Bean
public Step billingJpaStep(
        JobRepository repository,
        @Qualifier("billingJpaTxManager") PlatformTransactionManager tm,
        ItemReader<BillingEntity> reader,
        JpaItemWriter<BillingEntity> writer) {

    return new StepBuilder("billingJpaStep", repository)
            .<BillingEntity, BillingEntity>chunk(100, tm)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

`BillingEntity`/`JpaItemWriter` và factory được cấu hình nơi khác. `JpaTransactionManager` hiểu JPA persistence context/flush; chọn nhầm `JdbcTransactionManager` cho JPA writer có thể làm JPA operations không tham gia transaction mong muốn, gặp `TransactionRequiredException` hoặc commit không đúng ranh giới.

Một `JpaTransactionManager` có thể phối hợp `JdbcTemplate` dùng **cùng datasource JDBC** trong các cấu hình provider/dialect phù hợp; điều này không tự gom nhiều persistence units khác nhau thành một atomic transaction.

### 6.1. Flush và memory trong chunk

- `persist/merge` có thể giữ entities trong persistence context đến khi flush.
- Lỗi constraint đôi khi xuất hiện ở flush/commit, không phải ngay sau `save()`.
- Nếu persistence context giữ nhiều entities, heap/GC tăng theo chunk.
- JPA `EntityManager` không an toàn khi được dùng chung từ nhiều chunk threads; cần scoped/transaction-bound EntityManager đúng.
- Tối ưu chunk size, batching/flush/clear theo writer implementation và benchmark thật, không chỉ tăng threads.

## 7. Hai DataSource: metadata và business dùng hai transaction managers

Nhiều ứng dụng tách batch metadata và business data:

~~~text
batchDataSource:
  BATCH_JOB_INSTANCE
  BATCH_JOB_EXECUTION
  BATCH_STEP_EXECUTION
  BATCH_STEP_EXECUTION_CONTEXT

businessDataSource:
  source_orders
  normalized_orders
  business_outbox
~~~

Nếu hai datasource/transaction managers khác nhau, **không có transaction coordinator chung** theo mặc định.

### 7.1. Cấu hình Spring Batch 5.2 với qualifier rõ ràng

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTxManager")
public class BatchResourceConfig {

    // batchDataSource/businessDataSource phải được định nghĩa ở
    // datasource configuration riêng với driver, credentials và pools.

    @Bean("batchTxManager")
    public PlatformTransactionManager batchTxManager(
            @Qualifier("batchDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean("businessTxManager")
    public PlatformTransactionManager businessTxManager(
            @Qualifier("businessDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    public Step ordersStep(
            JobRepository repository,
            @Qualifier("businessTxManager") PlatformTransactionManager tm,
            ItemReader<OrderRow> reader,
            ItemWriter<OrderRow> writer) {
        return new StepBuilder("ordersStep", repository)
                .<OrderRow, OrderRow>chunk(250, tm)
                .reader(reader)
                .writer(writer)
                .build();
    }
}
~~~

`OrderRow` và datasource beans là thành phần ứng dụng cung cấp, không phải chương trình copy-run nguyên vẹn. Nếu dùng Spring Boot, `@EnableBatchProcessing` có thể tương tác với auto-configuration của Boot; cần kiểm tra bean nào thực sự được tạo và transaction manager của repository. `@Qualifier` giúp tránh inject nhầm bean khi có nhiều `PlatformTransactionManager`.

### 7.2. Failure window giữa hai commit

| Trạng thái khi crash | Business data | JobRepository checkpoint | Hậu quả |
| --- | --- | --- | --- |
| Cả hai chưa commit | Không có chunk mới | Cũ | Retry bình thường nếu input ổn định |
| Business commit, checkpoint cũ | Đã ghi | Chưa tiến | **Replay/duplicate** nếu writer không idempotent |
| Checkpoint tiến trước, business rollback | Chưa ghi | Có vẻ đã tiến | **Bỏ sót** dữ liệu nếu không phục hồi đặc biệt |
| Cả hai commit | Đã ghi | Đã tiến | Trạng thái mong đợi |
| Không chắc chắn | Không rõ | Không rõ | Dùng audit/reconciliation, không sửa metadata mù |

Tài liệu chính thức Spring Batch 5.2 nêu rõ: Step manager khác repository manager hợp lệ, nhưng hai DB không còn cùng transaction. Không thiết kế “chắc chắn business commit trước metadata” hay ngược lại; đường lỗi thực phụ thuộc transaction participation và thời điểm flush/commit.

### 7.3. Khi metadata và business cùng datasource

Có thể cấu hình cùng datasource **và cùng transaction manager** cho Step và JobRepository để metadata updates trong chunk tham gia cùng local transaction. Kiểm tra resource binding, repository advice, propagation và writer transaction tham gia thực sự.

Cùng server/URL/username **không đủ** nếu dùng hai pools/connections/manager độc lập. Ngoài ra, message/file/HTTP side effects vẫn nằm ngoài phạm vi JDBC transaction.

## 8. Nhiều manager và @Transactional

Với nhiều manager trong Spring context, hãy chỉ định rõ trên các service:

~~~java
@Service
public class DomainServices {

    private final OrdersDao orders;
    private final AuditDao audit;

    public DomainServices(OrdersDao orders, AuditDao audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional("businessTxManager")
    public void updateBusiness(long id) {
        orders.update(id);
    }

    @Transactional("auditTxManager")
    public void appendAudit(long id) {
        audit.insert(id);
    }
}
~~~

Hai method commit độc lập; nếu gọi `updateBusiness` rồi `appendAudit`, lỗi trong audit không tự rollback business đã commit. Không thêm annotation ngoài rồi tuyên bố atomic nếu outer manager chỉ quản lý một resource.

### 8.1. Propagation khác transaction domain

- `REQUIRED`: tham gia transaction hiện hành của **manager tương ứng**, nếu có.
- `REQUIRES_NEW`: mở transaction độc lập; có thể giữ/suspend outer resources và cần thêm connection.
- `NESTED`: phụ thuộc savepoint support của resource; không mặc định có ở JPA/JTA.
- `NOT_SUPPORTED`: suspend một transaction phù hợp; không nhất thiết commit hoặc giải phóng locks/connection trước đó.

Nếu method bên trong chunk chọn **manager khác**, có thể có hai transaction domains đồng thời trên cùng thread. Đó không phải một global transaction.

### 8.2. Spring proxy và self-invocation

`@Transactional` ở proxy mode mặc định chỉ được kích hoạt khi lời gọi **đi qua Spring proxy**. Gọi `this.appendAudit(...)` trong cùng bean có thể bỏ qua annotation của method được gọi. Integration test phải lấy bean từ context và kiểm tra rollback thật, không chỉ gọi trực tiếp instance mới tạo bằng `new`.

### 8.3. @Async/Executor không kế thừa local transaction

~~~java
@Transactional("businessTxManager")
public void updateThenDispatch() {
    orders.update(...);
    executor.execute(() -> publishEvent(...));
    // Thread mới có thể chạy trước khi DB commit,
    // không tự mang transaction hiện tại.
}
~~~

Đây là pseudocode cho anti-pattern. Ngay cả `@TransactionalEventListener(phase=AFTER_COMMIT)` cũng không làm sự kiện bền vững nếu JVM chết ngay sau DB commit; với dữ liệu quan trọng, cần transactional outbox.

## 9. Transaction attributes và rollback rules

Spring Batch có thể cấu hình timeout, isolation và propagation trên transaction chunk:

~~~java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.interceptor.DefaultTransactionAttribute;

DefaultTransactionAttribute txAttributes =
        new DefaultTransactionAttribute();
txAttributes.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
txAttributes.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
txAttributes.setTimeout(30);

Step step = new StepBuilder("updateStep", jobRepository)
        .<OrderRow, OrderRow>chunk(200, businessTxManager)
        .reader(reader)
        .writer(writer)
        .transactionAttribute(txAttributes)
        .build();
~~~

Code là fragment cấu hình, không tự khai báo `JobRepository`, `businessTxManager`, reader/writer. Timeout transaction **không** tự hủy mọi HTTP call bị block; cần request deadline của client mạng.

### 9.1. Exception không phải lúc nào cũng tự rollback

Với Spring `@Transactional`, mặc định exception kiểu `RuntimeException` hoặc `Error` kích hoạt rollback; checked exception có thể cần `rollbackFor`. Spring Batch cũng có logic rollback/retry/skip theo chính sách Step, nên phải kiểm thử hành vi cuối cùng thay vì suy từ annotation đơn lẻ.

~~~java
@Transactional(
        transactionManager = "businessTxManager",
        rollbackFor = ExternalValidationException.class)
public void writeValidated(OrderRow row)
        throws ExternalValidationException {
    validate(row);
    repository.save(row);
}
~~~

Nếu code nuốt exception và trả thành công, interceptor có thể commit. Với `REQUIRES_NEW`, inner transaction có thể commit trước khi outer chunk rollback; hãy tránh “commit per item” độc lập trong một chunk nếu mục tiêu là atomic chunk write.

## 10. Resource transactions trong messaging: JMS, RabbitMQ và Kafka

Cần phân biệt **message transport transaction/ack** với **database transaction**.

### 10.1. JMS: local JMS Session

`JmsTransactionManager` quản lý local Session transaction của một JMS `ConnectionFactory`:

~~~java
@Bean("jmsTxManager")
public PlatformTransactionManager jmsTxManager(
        jakarta.jms.ConnectionFactory cf) {
    return new JmsTransactionManager(cf);
}
~~~

Listener/container/template phải cấu hình để dùng đúng transactional session. JMS message có thể redeliver khi session rollback, nhưng SQL của một JDBC datasource riêng **không tự rollback** khi JMS transaction rollback.

Nếu yêu cầu atomic giữa JMS và database, có thể xem xét `JtaTransactionManager` với **XA-capable JMS ConnectionFactory và XA JDBC datasource** được coordinator enlist. Nếu không, dùng at-least-once delivery, idempotent JDBC writes và durable inbox/outbox.

### 10.2. RabbitMQ: local channel, không XA

`RabbitTransactionManager` quản lý local transaction của Rabbit connection/channel:

~~~java
@Bean("rabbitTxManager")
public PlatformTransactionManager rabbitTxManager(
        org.springframework.amqp.rabbit.connection.ConnectionFactory cf) {
    return new RabbitTransactionManager(cf);
}
~~~

Spring AMQP nêu rõ manager này **không hỗ trợ XA** để chia sẻ atomic transaction giữa Rabbit và JDBC. Queue durable, message persistence, publisher confirms, acknowledgements và local channel transaction giải quyết các loại lỗi khác nhau. Không coi chúng như một nút “exactly-once nghiệp vụ”.

### 10.3. Kafka: producer transaction không phải JDBC transaction

`KafkaTransactionManager` quản lý Kafka producer transaction của một `ProducerFactory` đã cấu hình transactional:

~~~java
@Bean("kafkaTxManager")
public KafkaTransactionManager<String, String> kafkaTxManager(
        ProducerFactory<String, String> pf) {
    return new KafkaTransactionManager<>(pf);
}
~~~

Producer cần `transactionIdPrefix` phù hợp và mỗi application instance phải tuân thủ yêu cầu uniqueness/fencing của Kafka. `KafkaTemplate` phải dùng factory tương ứng để tham gia transaction.

Spring Kafka hỗ trợ **transaction synchronization** khi một JDBC transaction manager đang active. Trong một số flow, DB commit trước rồi Kafka transaction commit sau. Nếu Kafka commit lỗi **sau khi DB đã commit**, không thể hoàn tác DB bằng synchronization. Có thể điều chỉnh thứ tự commit qua các transaction boundaries trong một số trường hợp, nhưng **hai local commits vẫn có failure window**.

~~~text
DB:     BEGIN -> UPDATE -> COMMIT OK
Kafka:  BEGIN -> SEND   -> COMMIT FAIL

Kết quả: DB đã commit, Kafka chưa commit.
Không thể gọi rollback của Kafka để đảo ngược DB.
~~~

Nếu cần “DB commit thì message cuối cùng sẽ được phát”, hãy ưu tiên **transactional outbox** cùng database với business write, rồi publish qua Kafka với retry/dedupe.

### 10.4. Kafka consumer offsets không phải checkpoint Spring Batch

Kafka offsets, `JobRepository` checkpoint và business DB rows thuộc các state systems khác nhau. JDBC rollback không tự rollback offset đã commit, trừ khi pipeline có cơ chế phối hợp phù hợp. Với Kafka reader trong batch, cần định nghĩa source cutoff, end offsets, redelivery và idempotent writer; không giả định đọc topic sống tương đương snapshot bất biến.

## 11. Khi nào cần JTA/XA cho nhiều resource?

`JtaTransactionManager` là Spring adapter tới một **global transaction coordinator**. Muốn một transaction atomic qua hai XA-capable databases hoặc một XA JDBC resource và XA JMS, phải đáp ứng đồng thời:

1. Có một JTA transaction coordinator hoạt động, với transaction log và recovery phù hợp.
2. Cả hai resource factories được cấu hình **XA-capable**; không dùng JDBC pool hoặc JMS factory không XA rồi suy diễn có XA.
3. Các operations thực sự enlist vào cùng global transaction; kiểm tra bằng integration test.
4. Driver/provider và isolation/timeout hỗ trợ cấu hình cần thiết.
5. Có runbook cho coordinator crash, heuristic outcomes và in-doubt transactions.
6. Chi phí two-phase commit (2PC) còn chấp nhận được so với SLA và lock budget.

~~~mermaid
flowchart TB
    C["JTA Coordinator"] --> XA["XA JDBC Resource A"]
    C --> XB["XA JDBC Resource B"]
    C --> JM["XA JMS Resource (nếu có)"]
    XA --> P["Prepare / vote"]
    XB --> P
    JM --> P
    P --> F["Commit / rollback / recovery"]
~~~

Hai phase ở mức khái niệm:

- **Prepare:** coordinator hỏi các resource có sẵn sàng commit không, lưu trạng thái recovery.
- **Commit/rollback:** coordinator ra quyết định cuối cùng và phải có khả năng phục hồi các transaction dang dở sau crash.

### 11.1. XA không phải miễn phí

- Tăng round trips, transaction log, khả năng giữ lock lâu và độ phức tạp vận hành.
- Có trạng thái **in-doubt** hoặc heuristic mixed outcome khi resource/coordinator hỏng.
- Không mọi driver/pool hoặc infrastructure có cấu hình XA đúng.
- HTTP API bên ngoài và nhiều broker không hỗ trợ XA.
- Rollback ở database không nhất thiết hoàn tác một email hoặc charge đã gửi.
- Cần kiểm thử failover/recovery của **coordinator**, không chỉ Step restart.

**JTA/XA đáng xem xét** khi yêu cầu atomicity qua nhiều XA-capable resource thực sự bắt buộc và đội vận hành đủ năng lực quản lý. Nếu không, staging + outbox/inbox + idempotency thường ít phụ thuộc vào distributed locks hơn.

### 11.2. ChainedTransactionManager không tạo atomicity

Một “chained transaction manager” gọi commit lần lượt trên local manager A rồi local manager B không có prepare/commit coordination thật. Nếu A đã commit nhưng B lỗi, A không thể rollback chỉ bằng cách gọi thêm `rollback()`.

Một số chained manager trong hệ sinh thái Spring đã deprecated. **Không coi chain hoặc transaction synchronization là phép thay thế XA** nếu nghiệp vụ đòi “cả hai cùng commit hoặc không nơi nào commit”.

## 12. Transactional outbox: dùng một JDBC transaction để tránh dual write

Khi Spring Batch cần cập nhật business DB **và** publish Kafka/Rabbit event, một giải pháp mạnh là viết **business state + outbox event trong cùng transaction DB**. Sau commit, dispatcher riêng gửi message ở ngoài database transaction.

~~~mermaid
sequenceDiagram
    participant W as Spring Batch Writer
    participant D as Business DB
    participant X as Outbox Dispatcher
    participant B as Broker / Downstream
    W->>D: BEGIN business JDBC TX
    W->>D: UPSERT business data
    W->>D: INSERT outbox event
    W->>D: COMMIT
    X->>D: Claim pending event, COMMIT
    X->>B: Publish event (ngoài DB TX)
    B-->>X: Confirm / response
    X->>D: Mark SENT trong TX ngắn
    Note over X,B: Crash sau publish trước SENT có thể phát lại event
~~~

**Điều kiện tiên quyết:** business rows và outbox rows phải nằm trong cùng transactional resource mà Step writer manager đang quản lý. Nếu outbox table ở datasource khác hoặc publish message trong transaction callback trước commit, vấn đề atomicity vẫn tồn tại.

### 12.1. Schema ví dụ PostgreSQL

~~~sql
CREATE TABLE order_projection (
    order_id BIGINT PRIMARY KEY,
    source_version BIGINT NOT NULL,
    normalized_amount NUMERIC(18,2) NOT NULL
);

CREATE TABLE order_outbox (
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    PRIMARY KEY (order_id, source_version, event_type)
);
~~~

Khóa `(order_id,source_version,event_type)` là một **idempotency key** khả thi cho ví dụ. Nếu cùng version mà payload khác nhau, phải báo conflict; `ON CONFLICT DO NOTHING` không tự xác nhận hai payload có nội dung giống nhau.

### 12.2. ItemWriter ghi hai bảng trong một transaction

~~~java
import java.math.BigDecimal;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

record ProjectedOrder(
        long orderId, long sourceVersion, BigDecimal amount) {}

@Component
public class ProjectionAndOutboxWriter
        implements ItemWriter<ProjectedOrder> {

    private final NamedParameterJdbcTemplate jdbc;

    public ProjectionAndOutboxWriter(
            @Qualifier("businessJdbcTemplate")
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends ProjectedOrder> chunk) {
        for (ProjectedOrder row : chunk) {
            MapSqlParameterSource p = new MapSqlParameterSource()
                    .addValue("id", row.orderId())
                    .addValue("ver", row.sourceVersion())
                    .addValue("amount", row.amount())
                    .addValue("payload", makePayload(row));

            jdbc.update("""
                INSERT INTO order_projection(
                    order_id, source_version, normalized_amount)
                VALUES (:id, :ver, :amount)
                ON CONFLICT (order_id)
                DO UPDATE SET
                    source_version = EXCLUDED.source_version,
                    normalized_amount = EXCLUDED.normalized_amount
                WHERE order_projection.source_version
                       < EXCLUDED.source_version
                """, p);

            jdbc.update("""
                INSERT INTO order_outbox(
                    order_id, source_version, event_type, payload)
                VALUES (
                    :id, :ver, 'ORDER_PROJECTED', CAST(:payload AS jsonb))
                ON CONFLICT (order_id, source_version, event_type)
                DO NOTHING
                """, p);
        }
    }

    private String makePayload(ProjectedOrder row) {
        // Ví dụ minh họa JSON; production dùng serializer/schema version.
        return "{\"orderId\":" + row.orderId()
                + ",\"version\":" + row.sourceVersion() + "}";
    }
}
~~~

Writer không tự mở transaction: Spring Batch Step phải truyền **`businessTxManager` dùng cùng datasource với `businessJdbcTemplate`**.

~~~java
@Bean
public Step projectAndNotifyStep(
        JobRepository repository,
        @Qualifier("businessTxManager") PlatformTransactionManager tm,
        ItemReader<ProjectedOrder> reader,
        ProjectionAndOutboxWriter writer) {

    return new StepBuilder("projectAndNotifyStep", repository)
            .<ProjectedOrder, ProjectedOrder>chunk(250, tm)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Với đúng resource và local transaction, nếu writer ném exception giữa projection upsert và outbox insert, **cả hai thay đổi của chunk rollback**. Nếu một update là no-op do replay same/older version, outbox uniqueness vẫn bảo vệ event ID logic; cần thêm quy tắc detect version conflict.

### 12.3. Dispatcher phát message sau commit

Dispatcher đọc các outbox rows chưa gửi, claim theo lease/`SKIP LOCKED` bằng **DB transaction ngắn**, commit, publish ra broker, rồi đánh dấu SENT trong một transaction khác.

Nếu publish thành công nhưng process chết **trước khi đánh dấu SENT**, message có thể được gửi lại. Vì vậy:

- Dùng event identity ổn định từ business key/version.
- Consumer phải hỗ trợ dedupe hoặc idempotency.
- Outbox retention/cleanup không được xóa row trước khi có evidence xử lý phù hợp.
- Theo dõi tuổi pending events, số lần retry, DLQ, lỗi publisher confirm và ETA.
- Không giữ DB connection/row lock trong lúc đợi broker lâu.

### 12.4. Inbox/dedupe ở phía nhận

~~~sql
CREATE TABLE consumed_event (
    consumer_name VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        consumer_name, order_id, source_version, event_type)
);
~~~

Consumer cần ghi marker dedupe **trong cùng transaction với DB side effect mà marker bảo vệ**. Nếu marker commit trước nhưng business write rollback, hệ thống có thể đánh dấu đã xử lý trong khi kết quả còn thiếu. Nếu business write commit nhưng marker chưa commit, redelivery có thể nhân đôi effect. Trong cùng database transaction, unique key và business write có thể commit/rollback cùng nhau.

Với email, HTTP thanh toán, object storage hoặc database khác, local inbox table **không tự mang atomicity tới hệ thống đích**: vẫn cần idempotency key hoặc reconciliation phù hợp.

## 13. Resource không rollback theo JDBC: file, object storage, HTTP

Không phải mọi `ItemWriter` đều có transaction participation kiểu JDBC:

- File writer có thể append bytes nhưng không tự xóa bytes khi JDBC transaction rollback.
- Object storage upload thành công không bị rollback bằng `JdbcTransactionManager.rollback()`.
- HTTP POST có thể đã tạo charge ngay cả khi worker nhận timeout và chunk rollback.
- Kafka/Rabbit publish có thể đã đến broker dù DB writer thất bại.
- Một datasource thứ hai có thể đã commit riêng khi Step dùng một local manager khác.

### 13.1. Mẫu xử lý với file/object storage

- Ghi vào **temporary object/path** có tên gắn JobExecution/partition hoặc run version.
- Kiểm tra số lượng, checksum, schema/manifest và business invariants.
- Publish bằng **commit marker/manifest version** sau khi toàn bộ output đã hợp lệ.
- Retry/idempotency dựa trên stable object key hoặc source version.
- Dọn temporary output thất bại bằng runbook có retention, không nhầm rác tạm với dữ liệu đã publish.

Không suy rằng `@Transactional` bao một method ghi file làm file system tự rollback.

### 13.2. Không giữ transaction qua network call

Nếu `ItemProcessor` hoặc `ItemWriter` gọi API bên ngoài **trong transaction chunk**, transaction DB có thể kéo dài theo HTTP p99, giữ connection/locks và tăng contention khi tăng concurrency.

Một thiết kế tốt hơn trong nhiều trường hợp:

~~~text
TX ngắn #1: Claim + persist operation key -> COMMIT
No DB TX:   Call HTTP/gRPC với deadline và idempotency key
TX ngắn #2: Persist result / check lease token -> COMMIT
Batch step: Process immutable staged data + DB chunk TX
~~~

Đây là eventual-consistency state machine, không phải một transaction toàn hệ thống. Nếu gọi network ở bên trong một outer chunk transaction dù helper dùng `NOT_SUPPORTED`, outer transaction có thể vẫn giữ resource/lock; cần tách **thực sự** ra khỏi transaction đang mở.

## 14. ResourcelessTransactionManager và R2DBC: chọn đúng mô hình

### 14.1. ResourcelessTransactionManager

`ResourcelessTransactionManager` không cung cấp DB transaction rollback thực cho JDBC, JPA hoặc message broker. Nó có thể hữu ích cho các bước thuần logic, file task hoặc resource không transactional khi kiến trúc đã chấp nhận restart semantics tương ứng.

**Không** thay `JdbcTransactionManager` bằng resourceless manager chỉ để giảm overhead rồi kỳ vọng chunk writer rollback khi thất bại. Một số bước không transactional cần business compensation/idempotent output và checkpoint cẩn thận.

### 14.2. ReactiveTransactionManager và R2DBC

`R2dbcTransactionManager` là `ReactiveTransactionManager`, hoạt động theo Reactor context và resource binding khác mô hình imperative thread-bound. Nó **không phải** `PlatformTransactionManager` được truyền trực tiếp cho `StepBuilder.chunk(size, txManager)` của Spring Batch 5.2.

Nếu ứng dụng kết hợp Spring Batch imperative và reactive service, phải xác định boundary/cancellation/retry rõ ràng. Đừng giả định `Mono`/`Flux` được tạo trong `@Transactional` imperative sẽ tự tham gia JDBC transaction hoặc ngược lại.

## 15. Resource transaction trong multi-threading và phân tán

Một Step chạy trên nhiều threads/pods không có nghĩa mọi worker dùng một transaction vật lý.

| Mô hình | Đơn vị đồng thời | Bảo đảm transaction cần kiểm chứng |
| --- | --- | --- |
| Single chunk step | Một chuỗi chunk | Mỗi chunk transaction theo manager được chọn |
| Multi-threaded step | Nhiều chunk threads cùng StepExecution | Transaction thường thread-bound; shared reader/writer thread safety |
| Parallel steps | Nhiều StepExecutions độc lập | Mỗi Step có thể chọn manager khác; resource pools cộng dồn |
| Local partitioning | Worker StepExecutions theo partition | StepScope reader, transaction riêng từng worker chunk |
| Remote partitioning | Worker StepExecutions trên nhiều JVM | Mỗi JVM cấu hình manager/resource riêng, shared JobRepository |
| Remote chunking | Chunk messages tới worker | Worker DB transaction tách broker ACK/reply; replay/idempotency |

### 15.1. StepScope không thay transaction manager

`@StepScope` tạo bean reader/writer theo `StepExecution`, không phải một transaction manager mới. Trong multi-threaded step, nhiều chunk threads có thể cùng StepExecution và dùng chung reader state. Trong partitioning, mỗi partition có context riêng, giúp checkpoint theo shard; nhưng singleton service/DB pool vẫn có thể dùng chung giữa nhiều worker.

### 15.2. Pool size và transaction duration

Giả sử 8 worker pods, mỗi pod có Hikari pool tối đa 10 connections; manager pool tối đa 6:

\[
C_{\mathrm{configured}}=8\times10+6=86.
\]

Đây là tổng **trần cấu hình** từ các pool minh họa, chưa tính ứng dụng online hoặc repository riêng. Nếu mỗi worker giữ JDBC connection trong lúc chờ HTTP, Hikari pending có thể tăng dù database CPU thấp. Tăng connection pool có thể giảm wait ngắn hạn nhưng làm DB lock/IO contention xấu hơn.

Cần đo **transaction duration, connection hold time, p95/p99 chunk latency, rollback rate và committed throughput**, không chỉ active thread count.

### 15.3. Concurrency không tạo atomicity mới

Nếu một Step update database A và database B mà không có XA, cho chạy 32 partition chỉ tạo thêm nhiều cơ hội xảy ra partial commit. Trước khi scale, phải chứng minh writer có idempotent business key/version và recovery path cho hai resource.

## 16. Retry và restart khi hai resource commit độc lập

Một chunk có thể được xử lý lại do exception, restart, broker redelivery hoặc thiếu checkpoint, dù một external effect đã hoàn tất.

### 16.1. Các khoảng lỗi tiêu biểu

~~~text
Case A: DB commit, metadata cũ
  businessDB COMMIT
  JobRepository chưa ghi checkpoint bền
  JVM crash
  restart -> chunk replay -> writer phải idempotent

Case B: DB rollback, event đã publish
  broker nhận event
  businessDB transaction rollback
  consumer thấy dữ liệu chưa tồn tại

Case C: Outbox event đã publish, chưa mark SENT
  broker nhận event
  dispatcher crash
  restart dispatcher -> publish lại
  consumer dùng inbox/dedupe
~~~

| Điểm crash | Dữ liệu nghiệp vụ | Metadata / broker | Hành động |
| --- | --- | --- | --- |
| Trước DB commit | Rollback nếu đúng manager | Checkpoint cũ | Retry chunk khi input ổn định |
| Sau business commit, trước checkpoint | Đã ghi | Metadata chưa phản ánh | Upsert/dedupe và reconciliation |
| Sau DB + outbox commit, trước publish | Đã ghi | Outbox NEW | Dispatcher phục hồi để publish |
| Sau publish, trước mark SENT | Đã ghi | Broker có thể đã nhận | Consumer dedupe, dispatcher retry |
| Sau JMS ACK, trước DB commit | Có thể còn thiếu | Message có thể không redeliver | Thiết kế ACK/transaction/recovery chính xác |
| Worker remote còn STARTED sau manager fail | Có thể vẫn ghi | Metadata stale | Liveness/fencing trước restart |
| Checked exception bị nuốt | Có thể commit ngoài ý muốn | Batch status đánh lừa | Error handling/rollback rules |

### 16.2. Fault-tolerant Step chỉ rollback các resource thực sự tham gia

~~~java
return new StepBuilder("retryStep", repository)
        .<OrderRow, OrderRow>chunk(100, businessTxManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Đây là snippet: `TransientDataAccessException` là nhóm lỗi Spring JDBC; cần cấu hình exact reader/writer và chính sách skip/retry phù hợp. Một external API call hoặc broker publish đã hoàn tất trước lỗi **không bị rollback bởi JDBC transaction manager**.

### 16.3. Restart đúng JobInstance

- Giữ identifying `JobParameters`, snapshot version, partition names và `ExecutionContext`.
- Không đổi `run.id` để tạo JobInstance khác rồi gọi đó là restart.
- Không chia lại range/file partition trong cùng JobInstance khi checkpoint cũ còn.
- Với remote worker, xác minh worker đời cũ đã dừng trước khi phát lại StepExecution.
- Không sửa thủ công metadata `BATCH_STEP_EXECUTION` để “cho xanh”.
- Sau failure/restart, so output theo business keys, versions và checksums, không chỉ dựa `BatchStatus.COMPLETED`.

## 17. Tính toán transaction và connection budget theo SLA

Giả sử cần xử lý **1.200.000 items** trong **30 phút xử lý**, còn 10 phút khác dành chuẩn bị và đối soát. Throughput commit cần:

\[
R_{\mathrm{required}}
=\frac{1{,}200{,}000}{30\times60}
\approx667\ \text{items/s}.
\]

Nếu một worker thực nghiệm đạt 140 committed items/s trong môi trường chưa tranh chấp, mức lý tưởng:

\[
N_{\mathrm{ideal}}
=\left\lceil\frac{667}{140}\right\rceil=5.
\]

Nhưng tăng workers làm tăng connection, DB lock, broker requests và JPA persistence contexts. Nếu transaction giữ connection 250 ms cho mỗi chunk và cần hoàn tất 30 chunks/s, Little's law cho khoảng:

\[
L_{\mathrm{DB}}\approx30\times0,25=7,5
\]

connections **đang bận trung bình** cho phần có cùng ranh giới đo, chưa tính metadata/reader cursors/pool contention. Đây là **ước lượng giả định**, không phải cấu hình Hikari chính xác.

### 17.1. Vì sao chọn manager đúng chưa đủ?

- Manager JDBC đúng nhưng writer gọi HTTP trong transaction: connection hold kéo dài.
- JPA manager đúng nhưng chunk quá lớn: persistence context/locks tăng.
- JMS manager đúng nhưng DB write độc lập: redelivery gây trùng nếu không idempotent.
- Kafka producer transactional đúng nhưng DB commit đã xong: partial failure vẫn tồn tại.
- JTA XA đúng nhưng concurrency/lock/2PC overhead vượt SLA: job có thể chậm và khó vận hành.

Tối ưu tài nguyên phải bắt đầu từ **transaction boundaries đúng**, sau đó mới tune chunk size, worker concurrency, DB pool và broker consumers.

## 18. Ma trận chọn thiết kế theo resource

| Nhu cầu của Step | Gợi ý | Điều kiểm chứng |
| --- | --- | --- |
| Ghi một JDBC datasource | `JdbcTransactionManager`/`DataSourceTransactionManager` | SQL cùng datasource, rollback thật |
| Ghi entity JPA | `JpaTransactionManager` đúng factory | EntityManager/flush/rollback |
| Đọc từ DB A, ghi DB B | Manager cho B; A snapshot ổn định | Reader restart, writer idempotent |
| Metadata DB riêng | Repository manager riêng | Business–metadata crash window |
| JMS receive + DB write | JMS transaction + idempotent DB hoặc JTA XA nếu đủ điều kiện | ACK/rollback/redelivery |
| RabbitMQ + DB | Business DB TX + outbox | Rabbit manager không XA, replay an toàn |
| Kafka + DB | DB TX + outbox/inbox | Synchronized commits vẫn có failure window |
| Hai XA databases cần atomicity | JTA XA | XA factories, coordinator, recovery |
| File/object storage output | Temp/immutable output + commit marker | JDBC rollback không xóa file |
| HTTP tạo business effect | Durable work state + idempotency key | Timeout sau remote success và replay |
| Reactive R2DBC pipeline | ReactiveTransactionManager riêng | Không đưa vào imperative chunk builder |
| Pure nontransactional work | Resourceless manager nếu phù hợp | Đã chấp nhận rollback/restart semantics |

Một quyết định đúng bắt đầu từ câu hỏi **resource nào thực sự cần commit cùng nhau và có khả năng tham gia transaction nào?** Không chọn manager chỉ dựa vào loại application.

## 19. Monitoring và cách phát hiện chọn sai transaction manager

| Tầng | Metric hữu ích | Điều cần chẩn đoán |
| --- | --- | --- |
| Spring Batch | read/write/commit/rollback/skip counts | Chunk có tiến triển bền vững? |
| Transaction manager | Begin/commit/rollback, duration, timeout | Transaction dài/nested sai? |
| JDBC/Hikari | Active/idle/pending, connection hold/acquire, timeout | Writer có ở đúng pool/transaction? |
| JPA | Flush failures, entity counts, dirty checking, SQL volume | Context phình, commit lỗi muộn? |
| JMS/Rabbit | Unacked, redelivery, DLQ, publish confirm | ACK và business DB có lệch? |
| Kafka | Transaction abort, producer fencing, offset lag | Transaction/offset semantics đúng? |
| JobRepository | Update latency, stale STARTED, checkpoint mismatch | Metadata có còn phục hồi được? |
| Outbox/inbox | Pending age, retry count, dedupe hits | Có mất/bị phát lại message? |
| Output | Unique business keys, source versions, totals | Đúng dữ liệu sau crash/restart? |
| SLA | Committed items/s, p99 chunk latency, ETA | Đạt deadline còn headroom? |

### 19.1. Quy trình điều tra thực tế

1. Xác định transaction manager bean được truyền vào `StepBuilder.chunk(...)`.
2. Kiểm tra bean đó được tạo từ `DataSource`/`EntityManagerFactory`/`ConnectionFactory` nào.
3. Kiểm tra reader/writer/template thực sự sử dụng factory **nào**, có cùng resource với manager hay không.
4. Tạo lỗi cố ý **sau một DB update nhưng trước commit** và kiểm tra rollback thật.
5. Kiểm tra transaction propagation, nested manager, self-invocation và exception bị nuốt.
6. Xác định JobRepository dùng datasource/manager nào; thử lỗi business commit–metadata update.
7. Với broker, gây mất response/ACK và kiểm chứng idempotency/outbox/dedupe.
8. Đối soát output theo key/version, không chỉ metadata Batch.

Nếu `@Transactional` “có vẻ hoạt động” nhưng rollback không xảy ra, chưa chắc lỗi ở framework. Thường cần xem bean selection, resource participation, transaction context, proxy boundary và exception rules.

## 20. Kiểm thử tích hợp và fault injection

Tránh chỉ mock transaction manager rồi assert “rollback() đã được gọi”; mock không chứng minh database hay broker đã rollback thật.

| Kịch bản | Cách thử | Kết quả mong đợi |
| --- | --- | --- |
| JDBC rollback | Update rồi ném RuntimeException trong writer | Đúng datasource rollback |
| Sai manager | Step dùng manager A, writer dùng datasource B | Test phát hiện không rollback như kỳ vọng |
| JPA flush failure | Vi phạm unique key tại flush/commit | Chunk failure, metadata/restart đúng |
| Checked exception | Ném checked exception qua service | Rollback theo rule, không commit nhầm |
| Self-invocation | Gọi method cùng bean có @Transactional | Test phát hiện interceptor bị bỏ qua |
| Hai DB | Business commit rồi lỗi metadata | Writer replay idempotent, không mất/trùng |
| JMS redelivery | Kill worker trước JMS session commit | Message được giao lại theo policy |
| Rabbit publish outage | DB commit nhưng broker không nhận | Outbox còn pending và retry |
| Kafka commit fail | DB đã commit, Kafka commit lỗi | Outbox/reconciliation giữ eventual delivery |
| Outbox dispatcher crash | Kill sau publish trước SENT | Consumer dedupe đúng |
| Kafka/JMS duplicate | Giao lại same message ID | Không tạo duplicate effect |
| Multi-threaded step | Tăng executor 1/4/8 | Reader/writer thread-safe, output tương đương |
| Local partitioning | Fail một partition rồi restart | Chỉ phần cần phục hồi chạy; context đúng |
| Remote partitioning | Kill worker sau commit | Metadata và output được đối soát |
| HTTP timeout sau success | Làm mất response từ đối tác | Stable idempotency key chống double charge |
| Pool saturation | Giảm Hikari limit, tăng workers | Backpressure, không retry storm |

### 20.1. Bất biến nghiệm thu

~~~text
1. Rollback của resource manager đã chọn thật sự undo uncommitted writes.
2. Metadata checkpoint và business commits tuân thủ recovery contract.
3. Business output sau crash/restart == clean-run reference.
4. Không có duplicate external business effects.
5. Mọi expected business key của snapshot xuất hiện đúng theo policy.
6. Outbox/inbox entries không bị silently lost.
7. Message redelivery không làm tăng số giao dịch nghiệp vụ.
8. Job chỉ publish kết quả khi reconciliation đã đạt.
~~~

Một JobExecution `COMPLETED` vẫn có thể có lỗi nghiệp vụ nếu database và broker không được điều phối đúng. Với nhiều resource, phải dựa vào **bằng chứng dữ liệu cuối**, không chỉ trạng thái batch.

## 21. Những hiểu nhầm phổ biến

| Nhận định | Điều cần sửa |
| --- | --- |
| “`@Transactional` làm DB và broker cùng rollback.” | Nó chọn một transaction manager; resource khác không tự enlist. |
| “Bean tên `transactionManager` kiểm soát mọi datasource.” | Manager gắn với factory/resource cụ thể. |
| “Step manager luôn là repository manager.” | Hai dependency có thể khác, gây non-atomic checkpoint. |
| “Hai JDBC pools cùng URL là cùng transaction.” | Connection/manager khác nhau không tự chia sẻ transaction. |
| “JDBC manager là đủ cho `JpaItemWriter`.” | JPA thường cần manager đúng `EntityManagerFactory`. |
| “JMS transaction tự rollback DB.” | Local JMS manager chỉ quản lý JMS Session. |
| “RabbitTransactionManager hỗ trợ XA.” | Spring AMQP không hỗ trợ XA qua manager này. |
| “Kafka transaction sync với JDBC là atomic.” | Vẫn có failure window giữa commit. |
| “ChainedTransactionManager thay thế XA.” | Sequential commits không có atomic coordination. |
| “REQUIRES_NEW commit sẽ bị outer rollback hoàn tác.” | Inner commit độc lập vẫn có thể tồn tại. |
| “@Async kế thừa local transaction.” | Imperative transaction gắn với thread. |
| “Resourceless manager rollback được JDBC.” | Không có JDBC rollback thực. |
| “Chunk size 1000 là một transaction cho toàn job.” | Mỗi chunk có transaction riêng. |
| “Outbox đảm bảo broker deliver exactly once.” | Có thể redeliver, consumer phải dedupe. |
| “Transaction timeout tự hủy HTTP call.” | Không tự quản lý network deadline. |
| “Batch COMPLETED chứng minh side effects exactly-once.” | Phải đối soát data/versions/messages. |

## 22. Checklist trước production

- [ ] Đã lập bản đồ mọi resource: metadata DB, business DB/JPA, broker, file, object storage, HTTP.
- [ ] Mỗi Step đã chọn `PlatformTransactionManager` đúng resource của writer.
- [ ] `JobRepository` dùng datasource/manager rõ ràng và có metadata bền vững.
- [ ] Không chọn manager ngầm khi có nhiều bean cùng type.
- [ ] Reader/writer/template dùng đúng datasource/entity manager/connection factory.
- [ ] Đã kiểm tra rollback thật trên database/broker bằng integration test.
- [ ] Checked exceptions, propagation, self-invocation và timeout được xử lý phù hợp.
- [ ] Đã đánh giá khoảng lỗi business commit–JobRepository checkpoint nếu hai managers khác nhau.
- [ ] Không tuyên bố atomic hai DB nếu chỉ có hai local managers.
- [ ] Nếu dùng JTA/XA, resources đã XA-capable, coordinator và recovery được thử nghiệm.
- [ ] Với JMS/Rabbit/Kafka, đã thiết kế ACK/transaction/redelivery/retry/DLQ đúng.
- [ ] Với DB + broker, có outbox/inbox hoặc chiến lược idempotency/reconciliation tương đương.
- [ ] External API có deadline/idempotency key, không giữ DB transaction chờ network.
- [ ] Data snapshot/partition plan bất biến qua restart.
- [ ] Writer chống replay theo business key/version.
- [ ] Tổng JDBC pool, locks và broker quotas được tính trên toàn bộ worker cluster.
- [ ] Chunk size/transaction duration được benchmark với peak volume và skew.
- [ ] Đã thử crash tại nhiều điểm trước/sau commit và message publish.
- [ ] Theo dõi commit/rollback, Hikari pending, outbox age, redeliveries và business output.
- [ ] Có runbook khi JobRepository status UNKNOWN/STARTED và cần reconciliation.

## 23. Câu hỏi tự kiểm tra

1. Vì sao một bean `JdbcTransactionManager` không thể tự rollback message Rabbit?
2. Spring Batch StepBuilder dùng hai dependency nào để điều phối chunk và lưu checkpoint?
3. Khi JobRepository và business DB dùng hai local transaction managers khác nhau, crash giữa commit có thể gây gì?
4. Hai datasource trỏ cùng JDBC URL có được coi là một local transaction không?
5. `JpaItemWriter` thường nên dùng manager của resource nào?
6. `JmsTransactionManager` bảo vệ resource gì? Muốn atomic với JDBC cần điều kiện nào?
7. Vì sao `RabbitTransactionManager` không phải XA manager?
8. Kafka transaction synchronization có hoàn toàn xóa failure window với JDBC không?
9. Outbox cần ghi những gì trong cùng DB transaction?
10. Tại sao dispatcher/consumer outbox cần event ID và dedupe?
11. `REQUIRES_NEW` commit rồi outer chunk rollback: inner changes sẽ thế nào?
12. Vì sao `@Async` không tự mang transaction từ chunk thread sang task mới?
13. Với 8 worker pods, pool max 10 connections/pod và manager pool max 6, trần pool là bao nhiêu?
14. Transaction timeout của Step có mặc định ngắt HTTP call không?
15. R2DBC transaction manager có dùng trực tiếp trong `chunk(size, PlatformTransactionManager)` không?
16. Test nào chứng minh writer tham gia đúng transaction manager?
17. Khi hai XA-capable databases thật sự cần atomic commit, phải chuẩn bị gì ngoài tạo `JtaTransactionManager`?
18. Vì sao `BatchStatus.COMPLETED` chưa đủ chứng minh broker message không bị gửi hai lần?

**Gợi ý:** (1) Manager chỉ biết JDBC resource. (2) `JobRepository` và `PlatformTransactionManager`. (3) Duplicate replay hoặc missing item nếu checkpoint và business commit lệch. (4) Không nếu khác connection/pool/manager. (5) `JpaTransactionManager` đúng EntityManagerFactory. (6) Local JMS Session; XA cần XA JDBC/JMS và coordinator. (7) Rabbit local transaction không XA. (8) Không, vẫn có partial commit. (9) Business state và outbox event. (10) Publish/reply có thể lặp sau crash. (11) Inner changes có thể tồn tại. (12) Transaction thread-bound. (13) `8×10+6=86`. (14) Không, cần HTTP deadline. (15) Không, reactive manager khác imperative PlatformTransactionManager. (16) Inject lỗi sau write, kiểm tra dữ liệu rollback trên đúng resource. (17) XA factories, coordinator, recovery, fault tests và chi phí 2PC. (18) Cần consumer dedupe và reconciliation.

## Tài liệu tham khảo

- [Spring Batch 5.2 — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html): Step manager có thể khác repository manager và cảnh báo non-atomic checkpoint.
- [Spring Batch 5.2 — Commit Interval](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/commit-interval.html): transaction theo chunk.
- [Spring Batch 5.2 — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): metadata transaction và `@EnableBatchProcessing`.
- [Spring Batch 5.2 — Transaction Attributes](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/transaction-attributes.html): propagation, isolation, timeout.
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `ExecutionContext`, restart.
- [Spring Framework — Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): manager theo resource và JTA.
- [Spring Framework — @Transactional / Multiple Transaction Managers](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): chọn manager theo bean name/qualifier.
- [Spring Framework — JDBC Connection Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `JdbcTransactionManager`, resource binding.
- [Spring Framework — JPA Integration](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html): `JpaTransactionManager`, JTA.
- [Spring Framework — JMS Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTransactionManager` và JMS XA.
- [Spring AMQP — Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): Rabbit local manager không XA.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): `KafkaTransactionManager` và DB commit synchronization.

**Điểm cốt lõi:** Trong Spring Batch, **transaction manager phải phù hợp resource thực sự cần commit/rollback**. Manager của chunk có thể khác manager của `JobRepository`, nhưng business data và checkpoint không tự atomic nếu hai database tách biệt. Dùng JDBC manager cho đúng DataSource, JPA manager cho đúng EntityManagerFactory, message manager cho broker resource của nó; chỉ dùng JTA khi các resources thực sự XA-capable với coordinator và recovery. Khi không có transaction chung, **idempotency, transactional outbox/inbox, snapshot bất biến, checkpoint và reconciliation** là nền tảng để scale nhiều worker mà vẫn restart an toàn.
