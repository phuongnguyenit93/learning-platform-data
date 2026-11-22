# Tạo ranh giới giao dịch mới trong bean xử lý khi nghiệp vụ yêu cầu

## Mục tiêu

Trong Spring Framework, một giao dịch được quản lý theo mô hình imperative với `PlatformTransactionManager` thường gắn với **thread đang thực thi**. Khi nghiệp vụ gửi công việc sang một executor bằng `@Async`, **giao dịch của caller không tự theo sang worker**. Nếu worker cần ghi dữ liệu một cách nguyên tử, phải thiết kế **ranh giới giao dịch của chính phần xử lý**.

Vấn đề không chỉ là thêm annotation `@Transactional` ở bất kỳ đâu. Cần quyết định **nghiệp vụ có thật sự cho phép một transaction độc lập hay không**, đặt transaction quanh đúng logic, gọi thông qua Spring proxy, chọn propagation phù hợp và hiểu tác động khi caller commit/rollback, worker thành công/thất bại, hoặc sự kiện được xử lý sau commit.

Bài học giúp bạn:

1. Hiểu transaction gắn thread và vì sao `@Async` không tự kế thừa transaction của caller.
2. Biết cách tách bean nhận việc async và bean xử lý `@Transactional` để mở transaction ở worker.
3. Phân biệt `Propagation.REQUIRED`, `REQUIRES_NEW` và `NESTED`; không mặc định `REQUIRES_NEW` luôn cần thiết khi chuyển thread.
4. Nhận diện các trường hợp **nên** và **không nên** cho worker commit độc lập với caller.
5. Dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` và transactional outbox đúng mục đích khi công việc phụ thuộc commit của giao dịch nguồn.
6. Chạy ví dụ Java 17+ và Spring Framework với H2: caller rollback nhưng giao dịch do worker tự mở vẫn commit.
7. Xử lý self-invocation, failure, timeout, connection-pool contention, retry và idempotency.

**Thông điệp cốt lõi:** `@Async` quyết định **nơi chạy công việc**; `@Transactional` quyết định **ranh giới nguyên tử của thao tác dữ liệu**. Đó là hai hợp đồng khác nhau. Một transaction mới ở worker chỉ đúng khi nghiệp vụ thực sự cần và chấp nhận tính độc lập này.

## 1. Một giao dịch Spring imperative sống trên thread nào?

Với JDBC/JPA thông thường, `@Transactional` được thực thi bởi Spring transaction advice/proxy. Một `PlatformTransactionManager` phù hợp liên kết connection, synchronization và trạng thái transaction với **thread hiện tại** thông qua cơ chế như `TransactionSynchronizationManager`.

```text
HTTP / caller thread
    |
    +-- @Transactional method
    |      Spring mở transaction A
    |      bind tài nguyên giao dịch vào caller thread
    |      thao tác SQL trong transaction A
    |
    +-- gọi @Async("workExecutor") ----> worker thread
    |                                    |
    |                                    +-- không tự có transaction A
    |                                    +-- nếu cần, mở transaction B riêng
    |                                    +-- commit/rollback transaction B
    |
    +-- caller commit/rollback A
```

Khi method `@Transactional` trên caller gọi `@Async`, worker không thể “nhìn thấy” transaction A chỉ vì caller vẫn đang mở transaction. Đây là đặc điểm của **thread-bound imperative transactions**; trong lập trình reactive, Spring dùng Reactor context và hợp đồng riêng, không nên áp dụng nguyên xi logic thread-bound.

Ba điều cần phân biệt:

- **Giao dịch được mở:** Transaction advice có bắt đầu hoặc tham gia một transaction ở thread đang chạy hay không?
- **Tác vụ được gửi đi:** Async proxy đã submit lời gọi vào executor hay chưa? Task có thể còn nằm trong queue.
- **Dữ liệu đã commit:** Người khác/worker có thấy bản ghi hay chưa? Điều này còn phụ thuộc isolation level, khóa và thời điểm commit.

Nếu caller vừa `INSERT order` nhưng chưa commit, worker dùng connection riêng thông thường không nhìn thấy order ấy ở mức isolation như `READ_COMMITTED`. Một số database có thể cho worker đợi lock; việc submit async **không bảo đảm** dữ liệu caller đã sẵn sàng.

## 2. Khi nào nên mở transaction mới tại bean xử lý?

Ví dụ **hợp lý** khi có một unit of work cần nguyên tử trong worker:

- Lưu kết quả của một job nền **đã được phép chạy độc lập**, gồm cập nhật trạng thái job và ghi các bản ghi liên quan trong cùng transaction của worker.
- Ghi nhận một nỗ lực xử lý (attempt log) độc lập, nếu nghiệp vụ cố tình muốn lưu cả khi caller thất bại.
- Xử lý một message đã được lấy từ broker; transaction dữ liệu của consumer phải bao phủ các thao tác cập nhật trong chính handler.
- Sau khi transaction tạo đơn hàng **đã commit**, thực hiện cập nhật một projection hay notification status trong một transaction mới.
- Chia một pipeline thành nhiều bước có trạng thái rõ, mỗi bước là transaction riêng và được phối hợp qua job record/event, không giả vờ tất cả là một transaction xuyên thread.

Ví dụ **không nên** cho worker commit độc lập chỉ vì có `@Async`:

- Caller tạo order trong transaction A, worker lập tức ghi shipment/payment rồi commit B; sau đó A rollback. Khi đó shipment/payment có thể còn tồn tại dù order chưa từng được commit.
- Nghiệp vụ đòi **tất cả hoặc không có gì** giữa thao tác caller và worker; transaction riêng phá tính nguyên tử toàn cục.
- Worker cần đọc dữ liệu vừa tạo nhưng caller chưa commit; việc worker chạy sớm có thể thấy thiếu dữ liệu, bị lock hoặc retry sai.
- Không có hệ thống lưu công việc bền vững nhưng vẫn yêu cầu mọi task phải sống qua crash/restart.

**Hỏi trước khi viết annotation:** Nếu transaction của caller rollback, bản ghi worker có được phép tồn tại không? Nếu câu trả lời là “không”, đừng chọn giao dịch độc lập và hy vọng việc dùng `@Transactional` trên cả hai phía sẽ tự phối hợp commit.

## 3. Tách trách nhiệm thành hai Spring bean

Một cấu trúc dễ hiểu và giảm nhầm lẫn AOP:

```text
Caller bean / controller
  |
  +-- gọi asyncGateway.dispatch(...)
                 |
                 v
       Spring async proxy
                 |
                 v
            workExecutor
                 |
                 v
          worker thread
                 |
                 +-- asyncGateway target method
                              |
                              +-- transactionalWorker.save(...)
                                        |
                                        v
                                  Spring tx proxy
                                        |
                                  BEGIN transaction B
                                        |
                                  JDBC / JPA writes
                                        |
                                  COMMIT / ROLLBACK B
```

Nên tách:

- **`AsyncGateway`** nhận yêu cầu, chứa phương thức `@Async` hoặc chủ động submit vào executor. Nó quyết định ranh giới thread và có thể trả `CompletableFuture<T>` để caller theo dõi.
- **`TransactionalWorker`** chứa thao tác dữ liệu nhất quán cần commit/rollback cùng nhau, được gắn `@Transactional` và **được gọi qua proxy Spring**.
- **Repository/JdbcTemplate** dùng đúng `DataSource`/`EntityManagerFactory` do `PlatformTransactionManager` của worker quản lý. Nếu dùng hai DataSource khác nhau, phải chọn đúng transaction manager; một transaction manager không tự bao phủ tất cả database.

Ví dụ cấu trúc:

```java
@Service
class AsyncGateway {
    private final TransactionalWorker worker;

    AsyncGateway(TransactionalWorker worker) {
        this.worker = worker;
    }

    @Async("workExecutor")
    public CompletableFuture<String> dispatch(long id) {
        String result = worker.save(id); // gọi bean giao dịch khác
        return CompletableFuture.completedFuture(result);
    }
}

@Service
class TransactionalWorker {
    @Transactional(propagation = Propagation.REQUIRED)
    public String save(long id) {
        // Những thao tác JDBC/JPA cùng ranh giới commit/rollback.
        return "saved:" + id;
    }
}
```

**Đây là snippet minh họa**, cần import annotation, cấu hình `@EnableAsync`, `@EnableTransactionManagement`, executor và các dependency phù hợp; phần `save` phải có thao tác dữ liệu thật mới có ý nghĩa transaction. Chương trình đầy đủ ở phần 6 có tất cả thành phần cần thiết.

Ưu điểm của hai bean: method `AsyncGateway.dispatch` thực thi trên worker, còn lời gọi `worker.save` đi qua **một transaction proxy khác** và transaction bắt đầu ngay trong worker. Không phải dựa vào phỏng đoán thứ tự advice khi gắn cả `@Async` và `@Transactional` lên một method duy nhất.

## 4. `REQUIRED` hay `REQUIRES_NEW`?

Đây là điểm quan trọng nhất của chủ đề. Hai propagation thường bị hiểu nhầm là “mặc định” và “có thread mới”, nhưng **cả hai đều là quy tắc transaction, không phải chính sách tạo thread**.

| Tình huống trên thread gọi method `@Transactional` | `REQUIRED` | `REQUIRES_NEW` |
| --- | --- | --- |
| **Chưa có transaction** trên thread đó | **Bắt đầu một transaction mới**. | Cũng bắt đầu một transaction mới. |
| **Đã có transaction** trên cùng thread, cùng manager/tài nguyên | **Tham gia transaction hiện có**; logic scope khác nhau có thể chia một physical transaction. | **Tạm đình chỉ** transaction đang có và tạo một physical transaction **độc lập**. |
| Khi method nội bộ rollback | Nếu tham gia physical transaction ngoài, rollback-only có thể khiến toàn transaction không commit. | Transaction mới rollback riêng; transaction ngoài có thể tiếp tục nếu nghiệp vụ và exception handling cho phép. |
| Tài nguyên | Có thể chia sẻ connection đang bound trên thread. | Thường cần connection/resource riêng trong khi resource ngoài vẫn bị giữ. |
| Có tạo thread mới không? | **Không**. | **Không**. |
| Khi dùng trong một `@Async` worker **chưa có transaction riêng** | Mở transaction mới độc lập với caller thread. | Cũng mở transaction mới; không cần thiết chỉ để khác caller transaction. |

Nếu caller đang có transaction A trên thread 1, còn `@Async` thực sự chạy trên thread 2 **không có transaction nào**, `@Transactional(propagation = REQUIRED)` ở `TransactionalWorker` sẽ mở B. Không cần cố gắng dùng `REQUIRES_NEW` chỉ để “thoát khỏi transaction caller”; transaction A vốn **không được truyền qua thread**.

Nhưng nếu trên **cùng worker thread** đã có transaction B và một bean khác cần luôn commit audit record độc lập với B, `REQUIRES_NEW` có thể được cân nhắc:

```java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(AuditRecord record) {
        auditRepository.insert(record);
    }
}
```

Đây là **snippet cấu trúc**, cần `AuditRecord`, `auditRepository` và import. Phải gọi từ **bean/proxy khác**; `this.recordAttempt(...)` trong cùng class không kích hoạt transaction advice ở proxy mode.

### Cẩn thận với connection pool và deadlock

`REQUIRES_NEW` trên cùng thread đang giữ một transaction khác có thể cần **connection bổ sung**, trong khi connection của outer transaction vẫn được giữ. Nếu có N thread đều giữ N connection ngoài rồi mỗi thread chờ thêm connection cho `REQUIRES_NEW`, một pool chỉ có N connection có thể dẫn tới starvation hoặc deadlock. Spring khuyến cáo sizing connection pool phù hợp, thường lớn hơn số thread transaction đồng thời ít nhất một connection cho kịch bản này.

Đối với async, còn một cạm bẫy tương tự: caller giữ một connection mở, **chặn bằng `future.get()`**, trong khi worker cần connection nhưng pool đã hết chỗ. Không chọn “đợi async trong một transaction còn mở” làm mô hình mặc định production.

### `NESTED` không phải transaction độc lập

`Propagation.NESTED` thường dùng **savepoint** bên trong cùng physical transaction (khi transaction manager và resource hỗ trợ, điển hình là JDBC savepoints). Một phần có thể rollback về savepoint, nhưng việc commit thật phụ thuộc transaction ngoài. Nó không có nghĩa inner transaction commit độc lập như `REQUIRES_NEW`, và cũng không chuyển transaction sang worker thread.

## 5. Các đặc điểm của transaction mới ở worker

Một phương thức:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void process(JobId id) {
    repository.markRunning(id);
    repository.writeResult(id);
    repository.markSucceeded(id);
}
```

Đây là **mã cấu trúc**, cần các kiểu/repository cụ thể. Nếu phương thức được gọi qua transaction proxy trên worker thread chưa có transaction, cả ba thao tác dùng cùng transaction; nếu bước 2 ném `RuntimeException` chưa được xử lý thì transaction thường rollback, kể cả bước 1 đã chạy SQL.

Một số nguyên tắc:

- Transaction bắt đầu **khi transaction interceptor thực sự được gọi** trên worker, không bắt đầu lúc caller submit công việc vào queue.
- Nếu worker còn chờ trong executor queue, caller transaction có thể đã commit, rollback hoặc kết thúc trước khi worker bắt đầu.
- Transaction commit sau khi target method `@Transactional` return bình thường qua transaction proxy. Nếu exception khiến rollback theo rule, các write cùng transaction không được commit.
- Mặc định Spring rollback với `RuntimeException` và `Error`, không tự rollback với mọi checked exception. Có thể dùng `rollbackFor` (hoặc quy tắc dự án tương ứng) khi nghiệp vụ yêu cầu.
- Nếu method catch exception rồi **nuốt** lỗi và return bình thường, transaction advice có thể commit vì không thấy exception. Nếu cần rollback, ném lại lỗi hoặc đánh dấu rollback-only đúng ranh giới.
- Một async result `CompletableFuture` hoàn tất thành công không tự chứng minh các hệ thống khác đã xử lý message/email; nó chỉ biểu diễn completion theo hợp đồng method.
- Giữ transaction nhỏ, tránh remote HTTP call dài hoặc CPU dài không cần thiết **bên trong transaction**, vì connection và lock có thể bị giữ quá lâu.

Các nguyên tắc này áp dụng cho Spring imperative transactions. Với R2DBC/reactive programming, hãy học riêng `ReactiveTransactionManager` và Reactor context; không copy transaction-bound `ThreadLocal` sang thread khác như một workaround.

## 6. Ví dụ chạy được: caller rollback, worker vẫn commit transaction riêng

Ví dụ dùng **Java 17+**, Maven, **Spring Framework 6.2.12**, Spring JDBC và H2 in-memory. Nó chứng minh sự độc lập trong trường hợp có chủ đích:

1. Main tạo transaction A qua `TransactionTemplate`, ghi một bản ghi vào `caller_records`.
2. Khi transaction A **chưa commit**, main gọi `AsyncGateway.enqueue(...)` qua Spring proxy.
3. Trên thread của `workExecutor`, gateway xác nhận **không có transaction A bound**.
4. Gateway gọi bean `TransactionalWorker.save(...)`, nơi `@Transactional(REQUIRED)` tự mở transaction B và ghi vào **bảng khác** `worker_records`.
5. Main chờ worker hoàn tất B, sau đó đánh dấu transaction A rollback.
6. Khi đọc database từ ngoài cả hai transaction, `caller_records` không còn bản ghi, còn `worker_records` có một bản ghi đã commit.

**Vì sao hai bảng?** Demo muốn chỉ ra **ranh giới transaction**, không tạo thêm tình huống khóa row do hai thread cùng sửa một bản ghi. Chọn hai bảng làm ví dụ ít phụ thuộc vào chiến lược lock của H2; trong production vẫn cần đánh giá lock, isolation và connection pool.

### Cấu trúc thư mục

```text
async-worker-transaction-demo/
├── pom.xml
└── src/main/java/example/AsyncWorkerTransactionDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>async-worker-transaction-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <configuration>
                    <mainClass>example.AsyncWorkerTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/example/AsyncWorkerTransactionDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class AsyncWorkerTransactionDemo {

    public record Receipt(
        boolean txAtAsyncStart,
        boolean txInsideWriter,
        String writerThread
    ) {
    }

    public static class TransactionalWorker {
        private final JdbcTemplate jdbc;

        public TransactionalWorker(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public Receipt save(String value, boolean txAtAsyncStart) {
            boolean active =
                TransactionSynchronizationManager.isActualTransactionActive();

            jdbc.update(
                "INSERT INTO worker_records(id, payload) VALUES (?, ?)",
                2, value
            );

            return new Receipt(
                txAtAsyncStart,
                active,
                Thread.currentThread().getName()
            );
        }
    }

    public static class AsyncGateway {
        private final TransactionalWorker writer;

        public AsyncGateway(TransactionalWorker writer) {
            this.writer = writer;
        }

        @Async("workExecutor")
        public CompletableFuture<Receipt> enqueue(String payload) {
            // Trước khi gọi writer, worker này chưa có transaction.
            boolean activeBeforeWriter =
                TransactionSynchronizationManager.isActualTransactionActive();

            // Lời gọi tới bean/proxy khác để @Transactional có hiệu lực.
            Receipt saved = writer.save(payload, activeBeforeWriter);

            return CompletableFuture.completedFuture(saved);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_boundary_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("workExecutor")
        public ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("worker-");
            return pool;
        }

        @Bean
        public TransactionalWorker transactionalWorker(JdbcTemplate jdbc) {
            return new TransactionalWorker(jdbc);
        }

        @Bean
        public AsyncGateway asyncGateway(TransactionalWorker writer) {
            return new AsyncGateway(writer);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            // Khởi tạo schema ngoài transaction thử nghiệm.
            jdbc.execute(
                "CREATE TABLE caller_records(" +
                "id INT PRIMARY KEY, payload VARCHAR(100))"
            );
            jdbc.execute(
                "CREATE TABLE worker_records(" +
                "id INT PRIMARY KEY, payload VARCHAR(100))"
            );

            PlatformTransactionManager manager =
                context.getBean(PlatformTransactionManager.class);
            TransactionTemplate tx = new TransactionTemplate(manager);
            AsyncGateway gateway = context.getBean(AsyncGateway.class);

            AtomicBoolean callerTransactionActive = new AtomicBoolean();
            AtomicReference<Receipt> receipt = new AtomicReference<>();

            tx.executeWithoutResult(status -> {
                callerTransactionActive.set(
                    TransactionSynchronizationManager
                        .isActualTransactionActive()
                );

                jdbc.update(
                    "INSERT INTO caller_records(id, payload) VALUES (?, ?)",
                    1, "will-rollback"
                );

                try {
                    // Chờ worker chỉ để chứng minh B commit trước A rollback.
                    receipt.set(
                        gateway.enqueue("worker-committed")
                            .get(10, TimeUnit.SECONDS)
                    );
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Interrupted while waiting for worker", ex
                    );
                } catch (ExecutionException | TimeoutException ex) {
                    throw new IllegalStateException(
                        "Worker failed or timed out", ex
                    );
                }

                // Rollback A một cách có chủ đích.
                status.setRollbackOnly();
            });

            Receipt saved = receipt.get();
            int callerRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM caller_records", Integer.class
            );
            int workerRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM worker_records", Integer.class
            );

            System.out.println("callerTransactionActive="
                + callerTransactionActive.get());
            System.out.println("txAtAsyncStart=" + saved.txAtAsyncStart());
            System.out.println("txInsideWriter=" + saved.txInsideWriter());
            System.out.println("ranOnWorkerThread="
                + saved.writerThread().startsWith("worker-"));
            System.out.println("callerRowsAfterRollback=" + callerRows);
            System.out.println("workerRowsAfterCallerRollback=" + workerRows);
        }
    }
}
```

Chạy từ thư mục `async-worker-transaction-demo` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Khi ứng dụng chạy thành công, **sáu dòng do chương trình in ra** theo thứ tự:

```text
callerTransactionActive=true
txAtAsyncStart=false
txInsideWriter=true
ranOnWorkerThread=true
callerRowsAfterRollback=0
workerRowsAfterCallerRollback=1
```

### Giải thích từng phép kiểm tra

1. `TransactionTemplate` mở transaction A trên main thread; `TransactionSynchronizationManager.isActualTransactionActive()` trả `true`.
2. Main ghi một dòng `caller_records` nhưng chưa commit. `gateway.enqueue(...)` đi qua Spring async proxy tới `workExecutor` tên worker.
3. Trong `AsyncGateway` **trước** khi gọi `TransactionalWorker`, không có transaction A gắn với worker; `txAtAsyncStart=false`.
4. `writer.save(...)` được gọi qua **transaction proxy khác**. Vì worker chưa có transaction, `Propagation.REQUIRED` bắt đầu B, nên `txInsideWriter=true`.
5. `writer.save` ghi một dòng trong `worker_records`. Khi method kết thúc bình thường qua proxy, transaction B commit; sau đó `AsyncGateway` hoàn tất future.
6. Main đã chờ future bằng `get(10, SECONDS)` (chỉ cho thí nghiệm), nên biết B hoàn tất trước khi đánh dấu A rollback.
7. `status.setRollbackOnly()` khiến transaction A rollback khi `TransactionTemplate` kết thúc. Dòng trong `caller_records` biến mất; dòng do B commit vẫn tồn tại.
8. Vì tên pool được đặt `worker-`, `ranOnWorkerThread=true` và worker thực sự khác main thread theo cấu hình này.

**Cảnh báo:** Ví dụ cố ý cho worker commit trước khi caller rollback để chứng minh tính độc lập. Đây là điều **không nên** làm nếu dữ liệu worker phải phụ thuộc vào một đơn hàng mà transaction caller chưa commit. Việc chờ `Future.get()` khi đang giữ transaction trên caller cũng có thể gây hết connection hoặc deadlock ở hệ thống thật; ví dụ dùng hai bảng và `DriverManagerDataSource` (mỗi lần lấy connection là connection mới) để cô lập bài học khỏi giới hạn pool.

`DriverManagerDataSource` phù hợp để minh họa đơn giản, **không phải connection pool production**. Ứng dụng thật thường dùng một pool có giới hạn, cần sizing theo số caller transaction đang mở và số worker đồng thời. Với nhiều service, phải xác định transaction manager nào điều khiển từng DataSource.

## 7. Điều gì xảy ra nếu worker lỗi?

Khi `TransactionalWorker.save(...)` ném `RuntimeException` chưa được nuốt:

```text
AsyncGateway worker thread
     |
     +-- call TransactionalWorker proxy
               |
               +-- BEGIN B
               +-- update SQL
               +-- RuntimeException
               +-- ROLLBACK B
     |
     +-- future caller completed exceptionally
```

Một method có thể dùng:

```java
@Transactional
public void writeTwoRows() {
    repository.insertFirst();
    repository.insertSecond(); // có thể ném exception
}
```

Đây là snippet, cần repository thật. Nếu second insert ném unchecked exception, Spring transaction advice thường rollback cả hai thao tác trong cùng physical transaction. Nếu exception được **bắt và nuốt** trong method, transaction advice thấy return bình thường và có thể commit; không vì log lỗi mà rollback tự động.

Mặc định `@Transactional` rollback với unchecked exception (`RuntimeException`) và `Error`, không mặc định với mọi checked exception. Nếu chính sách cần rollback cả checked exception nghiệp vụ, có thể cấu hình:

```java
@Transactional(rollbackFor = Exception.class)
public void process(...) throws Exception {
    // ...
}
```

Mẫu này là **minh họa chữ ký** cần thay tham số và thân method theo nghiệp vụ; không phải code độc lập. Quy tắc rollback cần đủ hẹp để không biến mọi lỗi điều kiện thành rollback ngoài ý muốn.

Với `@Async` trả `CompletableFuture<T>`, caller có thể quan sát lỗi bằng `get()` (thường `ExecutionException`), `join()` (thường `CompletionException`) hoặc `whenComplete`/`handle`. Đừng bỏ Future nếu công việc cần theo dõi hoàn tất.

Nếu executor **từ chối submit** vì queue đầy hoặc đã shutdown, lỗi có thể xuất hiện trước khi có future hợp lệ; điều đó không tương đương rollback của transaction B, vì B có thể chưa từng được mở.

## 8. Cạm bẫy của proxy: cùng bean tự gọi không mở transaction mới

`@Transactional` và `@Async` đều dựa vào AOP proxy ở mode thông thường. Nếu trong một bean có:

```java
@Service
class SameBean {
    public void outer() {
        this.inner(); // self-invocation: không qua transaction proxy
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Dự định mở transaction độc lập.
    }
}
```

Đây là đoạn minh họa class, không có đầy đủ import/implementation. Trong proxy mode, lời gọi `this.inner()` là **lời gọi Java trực tiếp trên target object**, không qua proxy; `REQUIRES_NEW` không tự được áp dụng cho invocation ấy. Nếu đang có transaction ngoài, code bên trong có thể vẫn chạy trong transaction cũ; nếu không có transaction, nó có thể không được giao dịch nào bao phủ.

Giải pháp rõ ràng: tách `inner` vào một Spring bean khác và inject reference của bean đó; gọi qua reference do container cung cấp. Với code rất nhỏ, có thể dùng `TransactionTemplate` trong method để kiểm soát phạm vi bằng API tường minh.

Không tự gọi một method `@Async` qua `this` rồi kỳ vọng nó chuyển thread; nếu nó chạy đồng bộ trên caller thì cả nhận định “transaction không được truyền” lẫn số liệu latency đều bị sai bối cảnh.

### Gắn cả `@Async` và `@Transactional` lên một method thì sao?

Có thể hoạt động tùy advice/proxy order và cấu hình ứng dụng. Nhưng **khó quan sát** đoạn nào đã chuyển sang worker, transaction mở ở thread nào và kết quả commit khi nào, đặc biệt khi có `@Retryable`, security, `@Cacheable` hoặc proxy nhiều tầng.

Khi mục tiêu là làm rõ transaction mới ở worker, hai bean như `AsyncGateway` và `TransactionalWorker` khiến trách nhiệm rõ hơn: async advice thuộc gateway, transaction advice thuộc worker. Đây là khuyến nghị thiết kế để kiểm chứng dễ, không phải tuyên bố Spring cấm hoàn toàn hai annotation trên cùng method.

## 9. Giao dịch và sự kiện: đừng xử lý trước khi caller commit

Một lỗi phổ biến:

```java
@Transactional
public void createOrder(Command command) {
    repository.insertOrder(command);
    asyncGateway.startShipping(command.orderId());
}
```

Snippet giả định repository, command và gateway phù hợp. `startShipping` có thể chạy **trước khi transaction tạo order commit**. Nếu caller rollback, worker vẫn có thể tạo shipping record; nếu worker đọc database trên connection riêng, nó có thể không thấy order chưa commit.

**Giải pháp khi chỉ muốn xử lý sau commit:** phát sự kiện nghiệp vụ trong transaction caller và dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để chỉ kích hoạt sau commit thành công.

Ví dụ kiến trúc với các bean riêng:

```java
public record OrderCreated(long orderId) {
}

@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;
    private final OrderRepository repository;

    public OrderService(ApplicationEventPublisher publisher,
                        OrderRepository repository) {
        this.publisher = publisher;
        this.repository = repository;
    }

    @Transactional
    public void createOrder(long id) {
        repository.insert(id);
        publisher.publishEvent(new OrderCreated(id));
    }
}

@Component
public class OrderCommittedListener {
    private final AsyncOrderProcessor asyncProcessor;

    public OrderCommittedListener(AsyncOrderProcessor asyncProcessor) {
        this.asyncProcessor = asyncProcessor;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreated event) {
        asyncProcessor.processAsync(event.orderId());
    }
}

@Service
public class AsyncOrderProcessor {
    private final OrderWorker worker;

    public AsyncOrderProcessor(OrderWorker worker) {
        this.worker = worker;
    }

    @Async("orderExecutor")
    public CompletableFuture<Void> processAsync(long orderId) {
        worker.processCommittedOrder(orderId);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class OrderWorker {
    @Transactional(propagation = Propagation.REQUIRED)
    public void processCommittedOrder(long orderId) {
        // Đọc đơn hàng đã commit và cập nhật dữ liệu worker.
    }
}
```

**Đây là sơ đồ code cho ứng dụng**, không phải một file Java độc lập. Cần khai báo đầy đủ repository, import, executor, bật `@EnableAsync` và `@EnableTransactionManagement`. Mục đích chính: listener sau commit **giao task sang bean async khác**, còn method dữ liệu trong worker **mở transaction riêng** khi chạy.

`@TransactionalEventListener` mặc định ở phase `AFTER_COMMIT`. Khi phát event **không có transaction** đang hoạt động, listener mặc định không được gọi (trừ khi cấu hình `fallbackExecution = true`); điều này cần kiểm chứng nếu có những đường phát event ngoài transaction.

### Vì sao cần chú ý giao dịch ở listener AFTER_COMMIT?

Spring lưu ý rằng sau khi transaction đã hoàn tất, một số tài nguyên transactional có thể **vẫn còn bound/accessible** trong giai đoạn callback. Nếu một listener chạy đồng bộ trên cùng thread **tự thao tác database trực tiếp** sau commit, thao tác đó có thể tham gia ngữ cảnh resource cũ nhưng không có một commit tiếp theo như mong đợi. Với write cần chắc chắn được commit ở listener đồng bộ, thường cần chuyển sang một bean `@Transactional(REQUIRES_NEW)` được gọi qua proxy.

Trong mẫu ở trên, listener **không** làm database write trực tiếp: nó giao việc qua executor sang một worker thread khác, nơi `@Transactional(REQUIRED)` mở transaction mới. Vẫn phải hiểu async dispatch có thể thất bại và không đồng nghĩa work chắc chắn được xử lý.

### AFTER_COMMIT không tự bảo đảm độ bền

`@TransactionalEventListener(AFTER_COMMIT)` là cách chọn **thời điểm tương đối với transaction hiện tại**, không phải một hàng đợi bền vững. Process có thể crash **sau khi order commit nhưng trước khi task được submit**, hoặc task đã ở RAM queue nhưng crash trước khi chạy xong. Nếu bắt buộc “mỗi order đã commit cuối cùng sẽ được xử lý”, cần transactional outbox/queue durable hoặc cơ chế lưu job có retry và idempotency.

## 10. Transactional outbox khi cần cả atomicity nguồn và xử lý nền

Với nghiệp vụ quan trọng, transaction của caller nên ghi cả dữ liệu chính và một **outbox record** trong cùng physical transaction:

```text
Caller transaction A
   |
   +-- INSERT order
   +-- INSERT outbox_event(order-created, orderId, eventId)
   |
   +-- COMMIT A
         |
         v
Outbox dispatcher (quy trình độc lập)
   |
   +-- đọc outbox record đã commit
   +-- publish hoặc giao xử lý
   +-- retry/ack theo chính sách
         |
         v
Worker nhận event
   |
   +-- BEGIN transaction B
   +-- xử lý idempotent theo eventId
   +-- update worker state
   +-- COMMIT B
```

Nếu A rollback, cả order và outbox event đều rollback. Nếu A commit, outbox event còn trong database để dispatcher phục hồi sau crash. Hệ thống có thể phát trùng khi retry, vì vậy worker cần idempotency theo `eventId`/unique constraint hoặc protocol tương đương.

Outbox **không** tạo distributed ACID transaction giữa database và broker; nó chuyển bài toán sang delivery có thể retry và xử lý trùng. Đây thường là đánh đổi hợp lý hơn việc giữ một transaction qua nhiều thread, remote systems hoặc hàng chờ trong RAM.

## 11. Chờ Future trong transaction: dễ hết connection và khóa

Trong ví dụ chính, caller cố ý gọi `future.get(...)` **khi transaction A còn mở** để làm rõ B commit rồi A rollback. Đừng chuyển nguyên mẫu ấy thành production pattern.

Tình huống nguy hiểm:

```text
Caller thread 1..N:
  BEGIN A; giữ DB connection 1..N
  submit @Async work
  Future.get() đợi worker kết thúc

Worker thread:
  @Transactional cần connection mới
  DB pool chỉ có N connection, tất cả đang bị caller giữ
  -> worker chờ connection
  -> caller chờ worker
  -> starvation / deadlock
```

Ngay cả với pool có đủ connection, worker có thể chờ **row lock** mà caller giữ; caller lại chờ worker, tạo deadlock ở mức giao dịch. Tách thread không tách contention dữ liệu.

Các cách giảm rủi ro:

- Không chờ `Future` bên trong transaction nếu không bắt buộc; nên commit trước khi giao việc phụ thuộc vào dữ liệu đó.
- Với việc sau commit, dùng listener `AFTER_COMMIT` hoặc outbox bền vững tùy yêu cầu.
- Giới hạn executor concurrency/queue, timeout DB/HTTP, lock timeout và ngân sách retry.
- Theo dõi số DB connections đang bận/chờ, số worker, queue length, thời gian transaction và lock waits.
- Với `REQUIRES_NEW`, dự trù connection dư khi outer transaction giữ một connection; không coi việc tăng max pool thread là giải pháp nếu DB đã bão hòa.

## 12. Timeout, cancellation và rollback không phải một thứ

Nếu caller nhận một `CompletableFuture<Result>` từ async gateway:

```java
Result value = gateway.runAsync(id).get(2, TimeUnit.SECONDS);
```

Đây là snippet trong method có xử lý checked exceptions. `get(timeout)` chỉ giới hạn **thời gian caller đợi kết quả**. Nếu nó ném `TimeoutException`, worker có thể vẫn đang chạy, transaction B có thể chưa bắt đầu, đang mở hoặc đã commit.

Các kết luận **không được suy ra** sau timeout:

- “Worker chắc chắn đã rollback”: sai, worker có thể đang chạy bình thường.
- “Caller rollback thì worker cũng rollback”: sai, nếu B độc lập.
- “`Future.cancel(true)` chắc chắn ngắt JDBC và rollback”: sai, cancellation/interruption phụ thuộc future, JDBC driver và code hợp tác.
- “Retry an toàn”: sai, task cũ có thể đã commit nhưng result đến trễ.

Với operation tạo side effect, phải có **idempotency key** hoặc dữ liệu trạng thái kiểm chứng được. Nếu caller timeout rồi retry `INSERT` không có unique constraint, worker có thể tạo bản ghi trùng. Một `CompletableFuture` chỉ là handle completion, không phải bằng chứng exactly-once.

Đặt timeout ở nơi chờ thật sự: connection acquisition timeout, query timeout, HTTP connect/read timeout, lock timeout, deadline job. Hạn chế transaction dài và đừng giữ lock khi thực hiện network I/O ngoài ý muốn.

## 13. Exception và rollback giữa nhiều transaction

| Tình huống | Transaction A ở caller | Transaction B ở worker |
| --- | --- | --- |
| A rollback **trước** khi worker bắt đầu | A rollback | B vẫn có thể bắt đầu sau đó nếu task đã được submit, trừ khi có cơ chế không cho chạy. |
| A rollback **sau** khi B commit | A rollback | B giữ commit nếu nghiệp vụ và database không có ràng buộc phá vỡ. |
| B rollback do exception, A vẫn đang chạy | A có thể commit hoặc rollback theo logic riêng. | B rollback các write trong B. |
| A commit, B thất bại | A vẫn đã commit. | B rollback; cần retry/compensation nếu nghiệp vụ yêu cầu. |
| Task bị từ chối trước khi worker chạy | Tùy code caller có ném lỗi/rollback hay xử lý tiếp. | B chưa được mở. |
| Caller timeout khi đang chờ | A có thể tiếp tục hoặc rollback theo handler. | B có thể đang chạy và sau đó commit/rollback. |

Trong cùng một thread khi **REQUIRED tham gia transaction A**, rollback-only của inner logical scope có thể làm A rollback và dẫn tới `UnexpectedRollbackException` nếu caller tưởng sẽ commit. Nhưng với hai thread độc lập như ví dụ, không có quan hệ rollback-only tự động xuyên transaction; cần phối hợp bằng domain workflow chứ không coi hai proxy là một global transaction.

Nếu muốn nhiều bước có trạng thái có thể hoàn tác, hãy cân nhắc saga/compensation ở cấp nghiệp vụ. Compensation là **một hành động mới** để sửa tác dụng đã commit, không phải rollback vật lý của transaction cũ.

## 14. Cấu hình và điều cần nhớ với JPA

Ví dụ dùng `JdbcTemplate` để thấy transaction manager rõ. Với JPA, có thể dùng `JpaTransactionManager`, repository hoặc `EntityManager` được container quản lý. Tuy nhiên:

- `EntityManager` gắn với persistence context/transaction thường **không thread-safe** để chuyển nguyên instance sang async worker.
- Lazy-loaded entity từ caller có thể không còn session hợp lệ khi worker truy cập; đừng gửi entity object chưa được materialize như một transport payload tự do.
- Truyền ID hoặc DTO bất biến sang worker, rồi **load lại** entity trong transaction B của worker. Có thể cần kiểm tra record đã commit và xử lý optimistic locking/version conflicts.
- `@Transactional(readOnly = true)` là hint/configuration cho framework, không phải cơ chế bảo đảm không có write ở mọi database.
- Nếu có nhiều transaction managers (JDBC/JPA/đa DataSource), chọn đúng manager, ví dụ `@Transactional(transactionManager = "ordersTransactionManager")`, và đảm bảo repository thực sự tham gia manager đó.
- Không mở transaction kéo dài xuyên HTTP calls chỉ vì JPA lazy loading: xác định rõ ranh giới truy cập dữ liệu và thiết kế fetch graph/DTO phù hợp.

Một method worker xử lý entity sau commit có thể cần `@Transactional(REQUIRED)` để load và update trạng thái. Chỉ khi **trong cùng worker thread đã có transaction khác** và nghiệp vụ yêu cầu commit độc lập, mới cân nhắc `REQUIRES_NEW` với toàn bộ hệ quả về connection và lỗi.

## 15. Một phương án dùng TransactionTemplate

Không phải mọi ranh giới phải được khai báo bằng annotation. Khi logic bắt đầu/kết thúc transaction cần điều khiển tại một block code trong worker, `TransactionTemplate` có thể diễn đạt tường minh:

```java
public class TransactionalJobRunner {
    private final TransactionTemplate txTemplate;
    private final JdbcTemplate jdbc;

    public TransactionalJobRunner(PlatformTransactionManager txManager,
                                  JdbcTemplate jdbc) {
        this.txTemplate = new TransactionTemplate(txManager);
        this.jdbc = jdbc;
    }

    public String runJob(long jobId) {
        return txTemplate.execute(status -> {
            jdbc.update("UPDATE jobs SET status = ? WHERE id = ?",
                        "DONE", jobId);
            return "done:" + jobId;
        });
    }
}
```

Đây là **mẫu lớp minh họa**, không phải chương trình độc lập vì cần schema `jobs`, imports và integration vào Spring bean/executor. Khi gọi nó từ worker thread, block `txTemplate.execute(...)` tạo/tham gia transaction theo propagation mặc định của `TransactionTemplate` (REQUIRED). Nó không cần `@Transactional` proxy ở method `runJob`, vì chính template quản lý transaction.

Tuy vậy, `TransactionTemplate` **không** làm cho code tự chạy async. Bạn vẫn cần executor/`@Async` nếu muốn chuyển thread. Việc chọn programmatic hay declarative transaction tùy nhu cầu rõ ràng và quy ước dự án, không phải cơ chế “sửa” transaction tự truyền giữa thread.

## 16. Các sai lầm thường gặp

| Nhận định sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Transaction của caller tự theo `@Async` worker.” | Imperative transaction gắn với caller thread. | Mở transaction của worker nếu cần và được phép độc lập. |
| “Cứ có `@Async` là worker tự có transaction.” | Executor chỉ chạy task; không tự tạo JDBC transaction. | Gọi bean `@Transactional` qua proxy hoặc dùng template. |
| “Phải dùng `REQUIRES_NEW` vì worker là thread khác.” | Worker không có transaction A để suspend; REQUIRED cũng mở transaction mới. | Chọn propagation theo transaction **hiện có trên worker**. |
| “`REQUIRES_NEW` mở thread mới.” | Nó thay physical transaction, không thay executor. | Tách khái niệm transaction boundary và execution thread. |
| “Có `@Transactional` trên `this.inner()` là đã mở tx mới.” | Self-invocation bỏ qua proxy mode. | Gọi bean khác hoặc dùng TransactionTemplate. |
| “Caller rollback thì mọi worker write cũng rollback.” | Independent transaction B có commit riêng. | Chỉ chọn độc lập khi nghiệp vụ cho phép; cân nhắc after-commit/outbox. |
| “Submit worker ngay sau insert thì worker thấy bản ghi.” | Caller có thể chưa commit; isolation và lock quyết định. | Dispatch sau commit hoặc dùng outbox. |
| “Chờ Future ngay trong transaction là an toàn.” | Có thể giữ connection/lock rồi chờ worker cần chính resource. | Tránh block; commit trước, sizing/timeout đúng. |
| “`REQUIRES_NEW` không có chi phí tài nguyên.” | Outer transaction thường giữ connection khi inner cần connection khác. | Sizing pool và đánh giá contention/deadlock. |
| “`NESTED` commit độc lập.” | Thường là savepoint trong cùng physical transaction. | Dùng REQUIRES_NEW chỉ khi cần physical transaction độc lập. |
| “`AFTER_COMMIT` event tự bền vững qua crash.” | Listener/queue trong RAM có thể mất việc. | Transactional outbox/broker durable khi cần. |
| “Bắt exception và return bình thường vẫn tự rollback.” | Transaction advice có thể thấy success và commit. | Rethrow hoặc setRollbackOnly theo rule. |
| “Timeout/cancel future là rollback DB.” | Completion/cancellation không tự chứng minh transaction dừng. | Timeout I/O thật, idempotency và trạng thái job. |
| “Có thể share EntityManager từ caller sang worker.” | Persistence context không an toàn khi chia thread. | Truyền ID/DTO rồi load trong transaction worker. |

## 17. Checklist khi thiết kế một async transactional workflow

1. **Nghiệp vụ có cho phép độc lập không?** Nếu A rollback, B có được commit không? Nếu không, không tạo B sớm.
2. **Khi nào dữ liệu nguồn có thể đọc?** Đã commit chưa? Có lock/isolation hoặc version conflict cần xử lý?
3. **Worker dùng thread/executor nào?** Gọi qua Spring proxy chưa, có self-invocation không?
4. **Bean transaction nằm đâu?** Có một `TransactionalWorker` được gọi qua proxy trên worker, hoặc `TransactionTemplate` bao đúng block dữ liệu?
5. **Propagation nào?** Worker chưa có tx thì REQUIRED tạo mới; đang có tx mới xem cần tham gia hay REQUIRES_NEW độc lập.
6. **Manager/Resource nào?** TransactionManager đang quản lý đúng DataSource/JPA context không?
7. **Timeout/retry/cancellation?** Future timeout không tự rollback; task có thể commit trễ, cần idempotency.
8. **Có chờ worker trong outer transaction không?** Kiểm tra connection pool/lock deadlock, thường nên tránh.
9. **Task có thể bị mất không?** Nếu phụ thuộc commit của A và phải xử lý cuối cùng, dùng outbox hoặc job store durable.
10. **Có theo dõi trạng thái không?** Queue wait, tx duration, DB connections, rollback rate, retry/dead-letter, domain correlation ID.
11. **Exception/rollback rule đã kiểm thử chưa?** Runtime vs checked, caught exception, rollback-only và async completion.
12. **Security/context có được mang đi an toàn không?** Không copy transaction ThreadLocal; truyền metadata immutable cần thiết và xác thực lại khi phù hợp.

## 18. Câu hỏi tự kiểm tra

**1.** Caller có transaction A rồi gọi method `@Async`. Worker có tự tham gia transaction A không?

**Đáp án:** Không đối với imperative transaction gắn với thread. Nếu worker cần transaction, transaction advice được gọi trên worker phải tạo/tham gia một transaction ở chính worker.

**2.** Trên worker chưa có transaction, `@Transactional(propagation=REQUIRED)` có mở transaction mới không?

**Đáp án:** Có. REQUIRED tạo mới khi chưa có transaction trên thread phù hợp, vì vậy không cần REQUIRES_NEW chỉ để khác caller transaction đang ở thread khác.

**3.** Khi nào `REQUIRES_NEW` khác REQUIRED rõ nhất?

**Đáp án:** Khi đã có transaction trên **cùng thread**. REQUIRED thường tham gia physical transaction hiện có; REQUIRES_NEW suspend transaction đó rồi mở một physical transaction riêng, tốn tài nguyên khác và commit/rollback độc lập.

**4.** Trong demo, tại sao `callerRowsAfterRollback=0` nhưng `workerRowsAfterCallerRollback=1`?

**Đáp án:** Caller ghi ở A nhưng đánh dấu rollback-only. Worker mở B trên thread khác, ghi bảng worker và commit trước khi A rollback; A không tự rollback B.

**5.** Tại sao demo gọi `AsyncGateway` và `TransactionalWorker` qua hai bean riêng?

**Đáp án:** Để `@Async` advice chuyển invocation sang worker trước, rồi `@Transactional` proxy của bean khác mở transaction trên worker; tránh self-invocation và giảm nhầm thứ tự advice.

**6.** Caller insert order chưa commit rồi submit worker ship order. Worker có chắc nhìn thấy order không?

**Đáp án:** Không. Worker dùng connection/transaction riêng và phụ thuộc isolation/lock; nên chỉ dispatch sau commit hoặc dùng outbox khi công việc gắn với order đã commit.

**7.** `@TransactionalEventListener(AFTER_COMMIT)` đã đủ bảo đảm task không bị mất qua crash chưa?

**Đáp án:** Chưa. Nó chọn thời điểm callback theo transaction, không phải durable broker. Để bảo đảm phục hồi sau crash, cần lưu công việc/outbox trong transaction nguồn và retry/idempotency.

**8.** Một listener đồng bộ ở phase AFTER_COMMIT tự ghi database trong method listener; có thể cần gì?

**Đáp án:** Tài nguyên của transaction vừa commit có thể vẫn bound ở callback. Nếu cần một write có commit riêng, gọi bean khác `@Transactional(REQUIRES_NEW)` qua proxy; hoặc chuyển việc sang async worker có transaction mới phù hợp.

**9.** `Future.get(2, SECONDS)` timeout. Điều đó có chứng minh worker transaction đã rollback không?

**Đáp án:** Không. Caller chỉ hết ngân sách chờ; worker có thể đang chạy và commit sau đó. Cần idempotency và timeout I/O/transaction phù hợp.

**10.** Worker có thể dùng trực tiếp `EntityManager` hoặc JDBC connection từ caller không?

**Đáp án:** Không nên. Resource gắn transaction/thread không được thiết kế để chia sẻ qua worker; truyền ID/DTO và lấy resource riêng trong transaction worker.

### Ghi nhớ

Khi **nghiệp vụ cho phép một unit of work độc lập**, hãy để bean xử lý mở transaction trên **thread thực sự chạy công việc**: `@Async` qua proxy đến worker, rồi gọi một bean khác có `@Transactional(REQUIRED)` hoặc dùng `TransactionTemplate`. Nếu trên worker đã có transaction và cần **physical transaction độc lập**, mới xét `REQUIRES_NEW` cùng chi phí connection. Nếu công việc chỉ hợp lệ sau khi caller commit, hãy dùng cơ chế **sau commit**; nếu không được mất việc qua crash, hãy cân nhắc **transactional outbox**. Đừng dùng transaction annotation như một cách “ghép” ACID qua các thread.

### Tài liệu tham khảo chính thức

- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction gắn thread trong imperative model và cơ chế proxy.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED, REQUIRES_NEW, NESTED và tài nguyên/connection.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, AFTER_COMMIT và ranh giới callback.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor, proxy mode.
- [Spring Framework — TransactionTemplate](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html): quản lý transaction bằng code.
- [Spring Framework — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): trạng thái và resource bound theo thread.
