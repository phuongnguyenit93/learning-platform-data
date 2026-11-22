# Giao dịch thông thường gắn với luồng không tự truyền vào tác vụ @Async

## 1. Hiện tượng: caller có @Transactional nhưng worker không cùng transaction

Trong một ứng dụng Spring, ta có thể tạo dữ liệu trong một phương thức `@Transactional` rồi gửi một công việc khác bằng `@Async`:

```java
@Transactional
public void registerOrder(long orderId) {
    orderRepository.save(new Order(orderId));
    mailWorker.sendConfirmation(orderId); // Method có @Async ở bean khác.
}
```

Đây là **fragment minh họa**: `Order`, `orderRepository` và `mailWorker` là thành phần giả định của ứng dụng. Nhiều người nghĩ rằng vì `sendConfirmation()` được gọi *bên trong* một method `@Transactional`, nó sẽ tham gia vào transaction đang mở của `registerOrder()`. Trong mô hình giao dịch imperative thường gặp của Spring, suy luận đó **sai**.

Khi gọi qua Spring async proxy, `@Async` chuyển công việc sang một worker thread. Transaction của caller được gắn với **thread thực thi lời gọi giao dịch**; nó không được sao chép nguyên vẹn sang worker mới. Kết quả có thể là:

- Caller đang có transaction, nhưng trong worker `TransactionSynchronizationManager.isActualTransactionActive()` trả `false` nếu worker không tự mở transaction.
- Worker dùng một kết nối JDBC khác, không nhìn thấy bản ghi caller vừa insert nhưng **chưa commit**, ở mức isolation như `READ_COMMITTED`.
- Nếu worker có `@Transactional` riêng, nó có thể mở **một transaction độc lập** trên worker; đó **không phải** transaction của caller.
- Worker có thể gửi email hoặc ghi dữ liệu của chính nó thành công trong khi transaction caller **sau đó rollback**.
- Nếu caller đợi Future của worker trước khi commit, có thể tạo phụ thuộc thời điểm hoặc thậm chí bế tắc nghiệp vụ khi worker cố chờ dữ liệu chưa được commit.

**Quy tắc nền tảng:** `@Transactional` trong imperative Spring là ngữ cảnh giao dịch **thread-bound**. `@Async` thường đổi execution thread. Việc đổi thread **không tự mang theo transaction** của caller.

## 2. Giao dịch imperative của Spring gắn với thread như thế nào?

### 2.1. Transaction manager và resource binding

Trong JDBC, Spring thường dùng `PlatformTransactionManager` như `DataSourceTransactionManager`. Khi một lời gọi đi qua transactional interceptor:

1. Transaction manager lấy/bắt đầu transaction theo propagation và tình trạng hiện tại.
2. Spring gắn thông tin giao dịch và tài nguyên phù hợp — thường gồm `ConnectionHolder` cho `DataSource` — vào thread hiện tại thông qua cơ chế của `TransactionSynchronizationManager`.
3. Các lời gọi `JdbcTemplate`/DAO tham gia transaction khi chạy trên thread đó và dùng đúng resource/transaction manager.
4. Khi lời gọi transactional hoàn tất, Spring commit hoặc rollback theo quy tắc, sau đó dọn những resource bindings tương ứng.

Tính chất thread-bound giúp các repository/DAO khác nhau tham gia cùng một transaction mà không phải truyền `Connection` qua mọi tham số Java. Nhưng nó cũng tạo ra **ranh giới thread**: một task chạy ở thread khác không có các binding đó theo mặc định.

```text
Thread HTTP / caller                         Worker thread (executor)
--------------------                         ------------------------
@Transactional proxy begins T1
  |
  +-- bind T1 connection to caller thread
  |
  +-- JDBC INSERT row #1 (uncommitted)
  |
  +-- invoke @Async proxy ----------------> submit task to executor
  |                                         |
  |                                         +-- worker begins
  |                                         +-- no caller T1 binding
  |                                         +-- JDBC query via own connection
  |                                         +-- might NOT see uncommitted #1
  |
  +-- continue and commit/rollback T1
  |
  +-- unbind caller transaction
```

Quan sát chính xác: worker có thể nhận được các giá trị thông thường như `orderId` vì chúng được truyền như arguments, nhưng **không nhận được quyền sở hữu transaction/connection đang mở** chỉ nhờ việc truyền arguments.

### 2.2. TransactionSynchronizationManager kiểm tra được gì?

Hai method chẩn đoán thường gặp:

- `TransactionSynchronizationManager.isActualTransactionActive()`: báo một actual transaction đã được đánh dấu active trên thread hiện tại.
- `TransactionSynchronizationManager.isSynchronizationActive()`: báo transaction synchronization đang được bật cho thread; không hoàn toàn đồng nghĩa với một transaction vật lý đang active.

Trong ví dụ, dùng `isActualTransactionActive()` vì muốn so sánh **caller đang trong transaction** với **worker không kế thừa transaction**. Đây là tín hiệu hữu ích, nhưng không thay thế kiểm tra transaction manager, connection, isolation và dữ liệu thực tế.

**Đừng truyền hoặc ép gắn trực tiếp Connection/TransactionSynchronizationManager state từ caller vào worker** để “chia sẻ transaction”. Một JDBC `Connection`/Hibernate `Session` thường không được thiết kế để hai thread thao tác đồng thời; việc cưỡng ép chia sẻ tài nguyên có thể gây race, vi phạm lifecycle và consistency.

### 2.3. Ngoại lệ: reactive transaction không dùng cùng cơ chế

Với `ReactiveTransactionManager`, Spring quản lý transaction bằng **Reactor Context**, không theo `ThreadLocal` của mô hình imperative `PlatformTransactionManager`. Cách suy luận và propagation khi đó theo reactive pipeline/context, không thể lấy quy tắc “mọi giao dịch trong Spring đều thread-bound” để áp cho reactive.

Bài này tập trung vào **Spring imperative transaction + @Async + JDBC/JPA**. Khi đọc tài liệu reactive, cần phân biệt hai mô hình giao dịch.

## 3. @Async thực sự tạo ra ranh giới nào?

Spring hỗ trợ `@Async` thông qua async advice và executor. Ở cấu hình proxy mặc định:

- Có `@EnableAsync` (hoặc `<task:annotation-driven>`) thì Spring đăng ký hạ tầng xử lý annotation.
- Phương thức phải nằm trên bean do Spring quản lý, với lời gọi phù hợp đi **qua proxy**.
- Async advice submit invocation vào executor, chẳng hạn `ThreadPoolTaskExecutor`.
- Phần thân method đích chạy trên worker được executor cung cấp. Khi đó, transaction binding của **thread gọi ban đầu không tự xuất hiện** trên worker.

Cần đặc biệt phân biệt ba tình huống:

| Tình huống | Có đổi thread không? | Transaction của caller có tự được kế thừa không? |
| --- | --- | --- |
| Caller gọi method `@Async` trên **bean khác qua proxy** và executor thực sự bất đồng bộ | Có | Không |
| Caller tự gọi `this.asyncMethod()` trong cùng target ở proxy mode | Thường không: bypass async advice | Code chạy đồng bộ trên chính caller, nên có thể *thấy transaction caller*; không chứng minh propagation hoạt động |
| Executor thực tế là `SyncTaskExecutor`, thực thi ngay tại thread gọi | Không | Có thể nhìn thấy thread-bound transaction đang tồn tại, vì không có thread switch; đó không phải async worker độc lập |

Đây là lý do không nên chẩn đoán transaction propagation chỉ từ việc có hay không có annotation `@Async`. Phải xác nhận **call path**, **executor thực tế**, **thread name** và **transaction state**.

## 4. Thời điểm commit là phần quyết định dữ liệu worker nhìn thấy

Giả sử caller đang làm:

```text
T1 begins
  INSERT order id=1  (chưa commit)
  call worker.inspect(1) via @Async
  worker queries by id=1
  T1 commits after @Transactional method returns
```

Nếu DB dùng isolation `READ_COMMITTED`, worker đọc qua một transaction/connection độc lập thường **không nhìn thấy** row vừa được insert bởi T1 trước commit.

Hai điều cần hiểu:

1. `@Async` không tạo một lời hứa “chạy **sau commit**”. Worker có thể bắt đầu trước commit, sau commit hoặc khi caller đang chuẩn bị rollback — tùy scheduling.
2. Kết quả đọc dữ liệu chưa commit phụ thuộc isolation, DB engine và loại operation. Không suy rằng **mọi cơ sở dữ liệu, mọi isolation** đều cho cùng kết quả; ví dụ này cố ý dùng H2 `READ_COMMITTED` mặc định để minh họa không thấy row chưa commit.

Một race rất hay gặp: công việc async dựa vào bản ghi vừa được lưu trong caller. Trên máy phát triển, worker thỉnh thoảng chạy sau commit và mọi thứ “có vẻ đúng”; ở production, worker nhanh hơn và query trả rỗng. Việc thêm `Thread.sleep(100)` trong worker chỉ che race, không làm giao dịch có ràng buộc chính xác.

### 4.1. Thời gian chạy không đồng nghĩa thứ tự commit

Ngay cả khi method caller gọi `asyncService.run()` *sau* `repository.save()` trong cùng mã nguồn, transaction của caller có thể vẫn chưa commit cho tới khi method transactional **trả về qua proxy**. Bởi vậy thứ tự câu lệnh Java không bảo đảm worker nhìn được dữ liệu từ transaction đó.

### 4.2. Wait Future trong transaction có thể làm tình huống tệ hơn

Nếu caller đang giữ transaction mở và lập tức gọi `future.get()` để đợi worker mà worker lại chờ dữ liệu caller commit, hệ thống có thể tiến triển rất chậm hoặc bế tắc:

```text
Caller: holds T1 -> waits worker Future -> only after method returns can T1 commit
Worker: waits for data/lock held by T1 -> cannot finish Future
```

Không nên xử lý vấn đề này bằng cách tăng thread pool vô hạn. Cần sửa **ranh giới transaction**, thứ tự phát sự kiện/đẩy việc và cách task nhận dữ liệu.

## 5. Worker không có transaction khác với worker có transaction riêng

Có hai khả năng hoàn toàn khác:

### 5.1. Worker @Async không khai báo @Transactional

```java
@Async("workerExecutor")
public CompletableFuture<Integer> countRows(int id) {
    int count = jdbc.queryForObject(
            "select count(*) from items where id = ?",
            Integer.class, id);
    return CompletableFuture.completedFuture(count);
}
```

Đây là fragment trên Spring-managed bean, đã có `JdbcTemplate jdbc` và executor. Trong worker, `isActualTransactionActive()` có thể là false. JDBC query vẫn thực thi được bằng connection riêng, thường ở auto-commit behavior của JDBC/driver. Không có nghĩa mọi thao tác đều tự động “an toàn” hoặc đang cùng transaction caller.

### 5.2. Worker @Async cũng có @Transactional

```java
@Async("workerExecutor")
@Transactional(readOnly = true)
public CompletableFuture<Integer> countRowsInOwnTransaction(int id) {
    int count = jdbc.queryForObject(
            "select count(*) from items where id = ?",
            Integer.class, id);
    return CompletableFuture.completedFuture(count);
}
```

Khi lời gọi đi qua advice đúng cách, task chạy trên worker và transaction advice có thể mở **transaction mới trên worker đó**. Nó có transaction state active, nhưng **vẫn không tham gia transaction chưa commit của caller**.

Đừng diễn giải `Propagation.REQUIRED` là “tìm đến transaction của bất kỳ thread nào gọi mình”. `REQUIRED` chỉ tham gia một transaction phù hợp **đang tồn tại trong ngữ cảnh thực thi hiện tại**; nếu worker không có transaction thread-bound, nó sẽ bắt đầu transaction mới.

Với `Propagation.REQUIRES_NEW` trong worker, nó cũng bắt đầu transaction độc lập; không cần dùng `REQUIRES_NEW` chỉ để ép tạo transaction cho mọi phương thức async trong trường hợp worker không có transaction từ trước. Ý nghĩa suspend một transaction hiện hữu chỉ liên quan khi **thread hiện tại** thực sự có transaction mà propagation sẽ xử lý.

### 5.3. Hai transaction độc lập có thể cho kết quả khác nhau

Nếu worker tự lưu một row và commit transaction của worker, còn caller sau đó rollback, row của worker có thể **vẫn tồn tại**. Ngược lại, worker đọc dữ liệu caller chưa commit vẫn có thể không thấy dù chính worker đang ở trong transaction mới.

Vì vậy, thêm `@Transactional` vào worker không phải cách “truyền” transaction ban đầu. Nó chỉ quyết định ranh giới transaction cho công việc của worker.

## 6. Ví dụ runnable: Spring @Transactional + @Async + H2 kiểm chứng sự khác nhau

Ví dụ dùng **Java 21, Spring Framework 6.2.1, Spring JDBC, H2 2.3.232 và Maven**. Không cần Spring Boot.

Nó minh họa đồng thời:

1. Method caller `@Transactional` insert một hàng rồi **chưa commit**.
2. `@Async` worker không khai báo transaction đọc hàng đó: worker không có transaction của caller và không nhìn thấy dữ liệu chưa commit.
3. Worker `@Async @Transactional(readOnly = true)` có **transaction riêng**, nhưng cũng không thấy row chưa commit.
4. Sau khi caller commit, một listener `@TransactionalEventListener(phase=AFTER_COMMIT)` kết hợp `@Async` chạy và nhìn thấy row đã commit.
5. Khi caller ném exception và rollback, row đó không tồn tại, listener `AFTER_COMMIT` cho sự kiện trong transaction rollback không được gọi.

Để tránh đoán bằng `Thread.sleep()`, chương trình gọi `Future.get(timeout)` cho hai truy vấn của worker và dùng `CountDownLatch` để đợi listener sau commit.

### 6.1. Cấu trúc

```text
tx-async-demo/
├── pom.xml
└── src/main/java/demo/TxAsyncDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>tx-async-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jdbc</artifactId>
      <version>6.2.1</version>
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
        <version>3.5.0</version>
        <configuration>
          <mainClass>demo.TxAsyncDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Tệp `src/main/java/demo/TxAsyncDemo.java`:**

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
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
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TxAsyncDemo {
    public record Observation(boolean txActive, int visibleRows, String thread) {}
    public record Comparison(boolean callerTxActive, Observation asyncNoTx,
                             Observation asyncOwnTx) {}
    public record ItemCreated(int id) {}

    public static class Reader {
        private final JdbcTemplate jdbc;

        public Reader(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Async("workerExecutor")
        public CompletableFuture<Observation> withoutTransaction(int id) {
            return CompletableFuture.completedFuture(sample(id));
        }

        @Async("workerExecutor")
        @Transactional(readOnly = true)
        public CompletableFuture<Observation> withOwnTransaction(int id) {
            return CompletableFuture.completedFuture(sample(id));
        }

        private Observation sample(int id) {
            int count = jdbc.queryForObject(
                    "select count(*) from items where id = ?",
                    Integer.class, id);
            return new Observation(
                    TransactionSynchronizationManager.isActualTransactionActive(),
                    count,
                    Thread.currentThread().getName());
        }
    }

    public static class Writer {
        private final JdbcTemplate jdbc;
        private final Reader reader;
        private final ApplicationEventPublisher publisher;

        public Writer(JdbcTemplate jdbc, Reader reader,
                      ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.reader = reader;
            this.publisher = publisher;
        }

        @Transactional
        public Comparison insertAndObserve() throws Exception {
            jdbc.update("insert into items(id, label) values (?, ?)", 1, "one");
            boolean callerTx =
                    TransactionSynchronizationManager.isActualTransactionActive();

            Observation noTx = reader.withoutTransaction(1)
                    .get(5, TimeUnit.SECONDS);
            Observation ownTx = reader.withOwnTransaction(1)
                    .get(5, TimeUnit.SECONDS);

            publisher.publishEvent(new ItemCreated(1));
            return new Comparison(callerTx, noTx, ownTx);
        }

        @Transactional
        public void insertAndRollback() {
            jdbc.update("insert into items(id, label) values (?, ?)", 2, "two");
            publisher.publishEvent(new ItemCreated(2));
            throw new IllegalStateException("demo rollback");
        }
    }

    public static class AfterCommitListener {
        private final JdbcTemplate jdbc;
        private final CountDownLatch committedEvent = new CountDownLatch(1);
        private final AtomicInteger observedAfterCommit = new AtomicInteger(-1);
        private final AtomicInteger unexpectedRollbackEvent = new AtomicInteger();
        private final AtomicReference<String> listenerThread =
                new AtomicReference<>("");

        public AfterCommitListener(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Async("workerExecutor")
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onCreated(ItemCreated event) {
            if (event.id() == 1) {
                observedAfterCommit.set(jdbc.queryForObject(
                        "select count(*) from items where id = ?",
                        Integer.class, event.id()));
                listenerThread.set(Thread.currentThread().getName());
                committedEvent.countDown();
            } else if (event.id() == 2) {
                unexpectedRollbackEvent.incrementAndGet();
            }
        }

        public boolean awaitCommitted() throws InterruptedException {
            return committedEvent.await(5, TimeUnit.SECONDS);
        }

        public int observedCount() {
            return observedAfterCommit.get();
        }

        public int rollbackEventCount() {
            return unexpectedRollbackEvent.get();
        }

        public String listenerThread() {
            return listenerThread.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:tx_async_demo;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean("workerExecutor")
        public ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(2);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("tx-worker-");
            return pool;
        }

        @Bean
        public Reader reader(JdbcTemplate jdbc) {
            return new Reader(jdbc);
        }

        @Bean
        public Writer writer(JdbcTemplate jdbc, Reader reader,
                             ApplicationEventPublisher publisher) {
            return new Writer(jdbc, reader, publisher);
        }

        @Bean
        public AfterCommitListener afterCommitListener(JdbcTemplate jdbc) {
            return new AfterCommitListener(jdbc);
        }
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Transaction/thread behavior not as expected");
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            Writer writer = context.getBean(Writer.class);
            AfterCommitListener listener =
                    context.getBean(AfterCommitListener.class);

            jdbc.execute("create table items(id int primary key, label varchar(50))");
            Comparison c = writer.insertAndObserve();

            int committed = jdbc.queryForObject(
                    "select count(*) from items where id = 1", Integer.class);
            require(listener.awaitCommitted());

            boolean rolledBack = false;
            try {
                writer.insertAndRollback();
            } catch (IllegalStateException expected) {
                rolledBack = true;
            }

            int afterRollback = jdbc.queryForObject(
                    "select count(*) from items where id = 2", Integer.class);

            boolean onWorker = c.asyncNoTx().thread().startsWith("tx-worker-")
                    && c.asyncOwnTx().thread().startsWith("tx-worker-");
            boolean eventOnWorker = listener.listenerThread().startsWith("tx-worker-");

            require(c.callerTxActive());
            require(!c.asyncNoTx().txActive());
            require(c.asyncNoTx().visibleRows() == 0);
            require(c.asyncOwnTx().txActive());
            require(c.asyncOwnTx().visibleRows() == 0);
            require(committed == 1 && listener.observedCount() == 1);
            require(rolledBack && afterRollback == 0);
            require(listener.rollbackEventCount() == 0);
            require(onWorker && eventOnWorker);

            System.out.println("callerTxActive=" + c.callerTxActive());
            System.out.println("asyncTxActive=" + c.asyncNoTx().txActive());
            System.out.println("asyncSeesUncommitted=" +
                    (c.asyncNoTx().visibleRows() > 0));
            System.out.println("ownAsyncTxActive=" + c.asyncOwnTx().txActive());
            System.out.println("ownAsyncSeesUncommitted=" +
                    (c.asyncOwnTx().visibleRows() > 0));
            System.out.println("committedRowVisible=" + (committed == 1));
            System.out.println("afterCommitEventVisible=" +
                    (listener.observedCount() == 1));
            System.out.println("rollbackRowVisible=" + (afterRollback > 0));
            System.out.println("rollbackEventDelivered=" +
                    (listener.rollbackEventCount() > 0));
            System.out.println("workerThreadUsed=" + onWorker);
            System.out.println("listenerWorkerThreadUsed=" + eventOnWorker);
        }
    }
}
```

**Vì sao dùng `DriverManagerDataSource`?** Đây là lựa chọn **chỉ phục vụ demo**: mỗi lần `getConnection()` có thể tạo một connection mới. Production thường dùng connection pool như HikariCP và cấu hình timeout/size phù hợp. H2 in-memory trong ví dụ dùng URL `DB_CLOSE_DELAY=-1` để giữ database khi các connection lần lượt được đóng trong lifetime của JVM.

### 6.2. Lệnh chạy và stdout đã kiểm chứng

Cần Maven và JDK 21 trở lên. Từ thư mục `tx-async-demo`:

```bash
mvn -q -DskipTests compile exec:java
```

**Stdout đã biên dịch/chạy thực tế:**

```text
callerTxActive=true
asyncTxActive=false
asyncSeesUncommitted=false
ownAsyncTxActive=true
ownAsyncSeesUncommitted=false
committedRowVisible=true
afterCommitEventVisible=true
rollbackRowVisible=false
rollbackEventDelivered=false
workerThreadUsed=true
listenerWorkerThreadUsed=true
```

Chương trình in các boolean thay vì in thứ tự tên thread cố định; thứ tự thực tế của worker có thể thay đổi theo scheduling. Test có các assertions; nếu hành vi lệch khỏi kỳ vọng, chương trình báo lỗi thay vì chỉ in kết quả gây hiểu nhầm.

### 6.3. Diễn giải từng phần của output

| Dòng output | Ý nghĩa |
| --- | --- |
| `callerTxActive=true` | Method `Writer.insertAndObserve()` thực sự chạy trong transaction caller. |
| `asyncTxActive=false` | Method `Reader.withoutTransaction()` chạy trên worker, không có transaction của caller. |
| `asyncSeesUncommitted=false` | Query của worker chưa thấy row 1 do transaction caller chưa commit ở isolation demo. |
| `ownAsyncTxActive=true` | Method `Reader.withOwnTransaction()` đã mở transaction trên worker. |
| `ownAsyncSeesUncommitted=false` | Transaction riêng vẫn không nhìn thấy bản ghi chưa commit của transaction caller. |
| `committedRowVisible=true` | Sau khi method transactional hoàn tất và commit, row 1 thấy được từ query mới. |
| `afterCommitEventVisible=true` | Listener phase AFTER_COMMIT, chạy async trên pool, quan sát được row đã commit. |
| `rollbackRowVisible=false` | Transaction insert row 2 ném exception và rollback nên row 2 không tồn tại. |
| `rollbackEventDelivered=false` | Event row 2 gắn với transaction đã rollback không kích hoạt listener AFTER_COMMIT. |
| `workerThreadUsed=true` | Hai lần đọc worker đều chạy trên thread pool prefix `tx-worker-`. |
| `listenerWorkerThreadUsed=true` | Listener phase AFTER_COMMIT cũng được xử lý trên worker thread. |

**Giới hạn của ví dụ:** H2 default transaction isolation trong kịch bản là `READ_COMMITTED`; các truy vấn được điều phối để chạy trước caller commit, nên hai dòng về “không thấy uncommitted” là kết quả ổn định của demo, không phải lời khẳng định độc lập với mọi database/isolation.

## 7. Cơ chế @Transactional và @Async trong ví dụ: hai proxy boundary

Bản demo khai báo:

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
@EnableTransactionManagement
public static class Config {
    // Beans: DataSource, transactionManager, workerExecutor,
    // Reader, Writer và AfterCommitListener.
}
```

Cùng một ApplicationContext đã đăng ký xử lý cả `@Transactional` và `@Async`. Nhưng **không có nghĩa** một transaction xuyên qua các threads.

- `Writer.insertAndObserve()` được gọi từ `main` qua Spring-managed bean `Writer`. Transaction interceptor mở transaction T1 trên caller thread.
- `Writer` gọi `Reader.withoutTransaction()` và `Reader.withOwnTransaction()` thông qua dependency injected từ container. Async interceptor submit task sang `workerExecutor`.
- Method `withoutTransaction()` chạy trên worker, không có T1. Nó query DB bằng connection khác.
- Method `withOwnTransaction()` chạy trên worker; transaction interceptor mở T2 riêng trong ngữ cảnh thread worker. Nó query DB theo mức isolation của T2.
- Sau khi hai Future trả về và `insertAndObserve()` kết thúc, T1 mới commit. Bởi vậy hai worker queries được bảo đảm xảy ra trước commit trong demo.

**Tách bean là quan trọng.** Nếu `Writer` tự chứa một method `@Async` và gọi bằng `this.workerMethod()`, lời gọi có thể bypass proxy ở chế độ mặc định và chạy đồng bộ trên caller. Khi đó test có thể báo transaction active=true trong “worker method” chỉ vì **không hề chuyển thread**. Đừng coi đó là transaction propagation.

## 8. Điều gì xảy ra nếu worker cần ghi dữ liệu?

Nếu một công việc bất đồng bộ cần cập nhật database, có hai mô hình khác nhau về ý nghĩa nghiệp vụ.

### 8.1. Worker tự mở transaction

Dùng một Spring-managed bean khác với method:

```java
@Async("workerExecutor")
@Transactional
public CompletableFuture<Void> updateProjection(long orderId) {
    jdbc.update("update projections set status = ? where order_id = ?",
                "READY", orderId);
    return CompletableFuture.completedFuture(null);
}
```

Đây là fragment, đòi hỏi bean thực tế có `JdbcTemplate jdbc` và schema tương ứng. `@Transactional` ở worker có thể tạo transaction riêng. Giao dịch này commit/rollback theo kết quả thực thi của worker, **không phụ thuộc một cách tự động** vào transaction đang mở của caller.

Nếu caller transaction sau đó rollback mà worker đã commit một side effect khác, database có thể tồn tại một trạng thái mà nghiệp vụ không muốn. Việc đặt cả hai annotation trên một method không làm chúng cùng chia sẻ T1.

### 8.2. Cần cùng một transaction nguyên tử

Nếu hai thao tác DB buộc phải commit/rollback **cùng nhau**, hãy thực thi chúng trên **cùng transaction boundary** theo mô hình imperative đồng bộ, ví dụ đưa chúng vào một application-service method transactional hoặc gọi service transactional khác đồng bộ trong cùng thread và resource context.

Không dùng `@Async` rồi kỳ vọng có một transaction ACID trải qua nhiều threads. Nếu cần phân phối công việc, hãy chọn semantics eventual consistency, outbox, saga hoặc cơ chế distributed coordination phù hợp — đây là thiết kế khác với một local JDBC transaction.

### 8.3. Sử dụng REQUIRES_NEW không phải “kết nối lại” T1

Một method worker có `@Transactional(propagation = Propagation.REQUIRES_NEW)` mở transaction độc lập tại **worker thread**. Nó không thể nhìn thấy dữ liệu uncommitted của caller bằng cách “đặt propagation mạnh hơn”. Nếu thread worker không có transaction đang active, `REQUIRED` cũng sẽ tạo transaction mới; `REQUIRES_NEW` không cần thiết chỉ để tránh kế thừa T1 vốn không có.

## 9. Tránh đọc trước commit bằng sự kiện gắn với transaction

Một nhu cầu phổ biến: “Sau khi tạo order thành công, gửi email/refresh cache/cập nhật search index”. Thay vì gọi worker ngay khi transaction đang mở, có thể **phát sự kiện trong transaction** rồi **đợi đến phase sau commit** mới xử lý.

Spring có `@TransactionalEventListener`. Ví dụ:

```java
@Transactional
public void createOrder(long id) {
    jdbc.update("insert into orders(id) values (?)", id);
    applicationEventPublisher.publishEvent(new OrderCreated(id));
}
```

Đây là fragment, giả sử `applicationEventPublisher` được inject và `OrderCreated` là một record/event type có thật. Khi có listener:

```java
@Async("workerExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    // Có thể tra cứu row đã commit rồi thực hiện hậu xử lý.
}
```

Đây là fragment trên Spring-managed listener bean; cần `@EnableAsync`, proper transaction management và executor. Với `AFTER_COMMIT`, listener được kích hoạt sau khi transaction phát sự kiện **commit thành công**. Khi transaction rollback, listener `AFTER_COMMIT` không xử lý event đó.

**Điểm mạnh:** tránh race “async đọc dữ liệu trước commit” và tránh phát side effect sau một transaction đã rollback trong đường thực thi bình thường.

**Điểm cần cẩn trọng:** `@TransactionalEventListener` không phải một **message broker bền vững**. Nếu JVM chết sau commit nhưng trước khi async listener xử lý xong, event trong bộ nhớ có thể bị mất.

### 9.1. phase và fallbackExecution

Các phase gồm:

- `BEFORE_COMMIT`: trước commit, thích hợp cho một số logic cần chạy khi transaction chuẩn bị hoàn tất, nhưng không dùng làm mốc dữ liệu đã commit.
- `AFTER_COMMIT`: sau commit thành công (mặc định).
- `AFTER_ROLLBACK`: khi transaction rollback.
- `AFTER_COMPLETION`: khi transaction hoàn tất, bất kể kết quả.

Nếu phát event **không nằm trong transaction đang active**, listener transactional mặc định **không được gọi**, trừ khi bật `fallbackExecution = true`. Vì vậy không giả định mọi `publishEvent(...)` đều kích hoạt một `@TransactionalEventListener` trong mọi hoàn cảnh.

### 9.2. Đừng viết DB ở afterCommit callback cũ mà không nghĩ về transaction mới

Một callback `AFTER_COMMIT` đồng bộ có thể chạy trong giai đoạn transaction completion khi resource gắn với caller thread chưa được cleanup hết. Nếu callback tự ghi DB, cần thận trọng với resource/transaction state; nếu buộc ghi một transaction mới, hãy mở ranh giới phù hợp như `REQUIRES_NEW` trong đúng execution context.

Trong demo, listener có `@Async` để chạy **trên worker khác** sau phase commit và chỉ đọc row đã commit. Nếu listener async cũng cần ghi DB, nên cấu hình transaction mới cho công việc ghi khi cần. Không dựa vào connection cũ của caller sau commit.

## 10. Khi yêu cầu là chắc chắn xử lý hậu kỳ: Transactional Outbox

`@TransactionalEventListener(AFTER_COMMIT)` giải bài toán **đúng thứ tự commit** trong một tiến trình đang sống. Nhưng nó không giải quyết yêu cầu “DB đã commit thì việc gửi email/event bắt buộc phải được giao, kể cả khi process chết ngay sau commit”.

Đối với business task quan trọng, cân nhắc **transactional outbox**:

1. Trong **cùng transaction T1**, ghi entity nghiệp vụ và một bản ghi outbox về sự kiện cần xử lý.
2. T1 commit **nguyên tử** cả hai bản ghi.
3. Một relay/worker khác đọc các outbox records đã commit và gửi đến message broker/destination.
4. Sau khi nhận acknowledgement phù hợp, đánh dấu outbox record đã xử lý; nếu thất bại, retry có kiểm soát.
5. Consumer dùng idempotency/deduplication vì hệ thống có thể gửi lại ít nhất một lần.

```text
Caller @Transactional
  |
  +-- INSERT orders
  +-- INSERT outbox_event
  +-- COMMIT (atomic)
             |
             v
       Outbox relay
             |
             +-- publish to broker / durable job system
             |
             v
       Consumer / background worker
             |
             +-- dedup + business processing + status
```

Trong mô hình này, worker không cần thừa hưởng T1. Nó làm việc sau khi dữ liệu và thông điệp outbox đã commit; tính nhất quán được đảm bảo bằng **điều phối nghiệp vụ và lưu trữ**, không bằng cách kéo một JDBC transaction qua thread boundary.

Không tự tuyên bố “exactly once” chỉ nhờ outbox; cần phân tích retry, dedup, idempotency và giao thức nhận/ghi nhận kết quả.

## 11. Exception, rollback và Future trong tác vụ async

### 11.1. Lỗi caller transaction

Nếu method `@Transactional` đồng bộ ném một unchecked exception và exception đi qua transactional proxy, Spring thường đánh dấu rollback/rollback theo quy tắc mặc định. Trong ví dụ `insertAndRollback()` ném `IllegalStateException`; row 2 bị rollback.

Không suy rằng **mọi exception** đều mặc định rollback: checked exceptions có quy tắc khác tùy cấu hình (ví dụ `rollbackFor`), transaction manager và chính sách ứng dụng.

### 11.2. Lỗi trong worker không tự rollback transaction caller

Nếu worker bất đồng bộ ném exception **sau khi caller đã commit**, lỗi đó không thể tự quay lại và rollback transaction T1 đã kết thúc. Kể cả khi caller còn giữ T1 mở, một lỗi được worker lưu vào `Future` không tự động bị ném trên caller nếu caller không `get()` và xử lý.

Phân biệt:

- Lỗi **lúc submit**: pool/queue đầy có thể ném `TaskRejectedException` ngay tại caller.
- Lỗi **trong worker**: với method `@Async` trả `Future`/`CompletableFuture`, caller có thể quan sát bằng `get()`/completion handler.
- Method async trả `void`: caller không có Future để lấy lỗi; cần `AsyncUncaughtExceptionHandler`/logging/monitoring phù hợp.
- Lỗi **trong listener AFTER_COMMIT**: commit caller đã xong; xử lý thất bại và retry cần cơ chế riêng.

Nếu công việc quan trọng, phải có nơi theo dõi task ID, trạng thái cuối, retry, alert và nguồn dữ liệu khôi phục khi restart; không chỉ gọi `@Async` rồi bỏ qua.

### 11.3. Không để caller chờ worker trong cùng transaction chỉ để nhận lỗi

Gọi `future.get()` trong T1 có thể giúp caller thấy lỗi task, nhưng tăng thời gian giữ connection/locks và không biến T1 với worker transaction thành một transaction chung. Đặc biệt nguy hiểm nếu worker cần nhìn thấy dữ liệu chỉ được commit **sau khi T1 kết thúc**.

Hãy xác định rõ orchestration: việc nào thuộc transaction T1 đồng bộ, việc nào được giao xử lý sau commit với trạng thái độc lập.

## 12. Thread-local, MDC, SecurityContext và JPA

Câu chuyện transaction là một ví dụ của **thread context**. Khi đổi thread, nhiều loại context khác cũng có thể không tự truyền:

- `TransactionSynchronizationManager`: transaction/resource binding của imperative Spring.
- Logging `MDC`: correlation ID/log fields dùng `ThreadLocal`.
- `SecurityContextHolder`: tùy chiến lược lưu security context; không mặc nhiên được copy an toàn sang worker.
- Request-scoped context/HTTP request attributes: có thể không còn hợp lệ khi worker chạy sau response.
- JPA `EntityManager`/Hibernate `Session`: persistence context gắn với transaction/thread; không chia sẻ mutable entity/session tùy tiện giữa threads.

Một `TaskDecorator` hoặc context-propagation library có thể sao chép **metadata phù hợp** như correlation ID hoặc một security context đã được xử lý an toàn. Tuy nhiên **không dùng TaskDecorator để copy raw transaction connection/Session sang worker**. Truyền ID/immutable DTO, mở transaction độc lập đúng cách trong worker, rồi đo trạng thái kết quả.

Khi sửa self-invocation để thực sự chạy async, một method trước đây vô tình dùng được transaction/MDC của caller sẽ không còn thấy chúng. Đây không phải bug của worker mà là sự xuất hiện của thread boundary vốn trước đó chưa có.

## 13. Kiểm thử không phụ thuộc may rủi về scheduling

Trường hợp “worker không thấy bản ghi mới” có thể không tái hiện nếu worker chạy quá muộn và caller đã commit. Vì vậy, **test phải kiểm soát thời điểm**.

Trong ví dụ hoàn chỉnh:

- `Writer.insertAndObserve()` giữ transaction caller đang active.
- Caller **đợi hai Future** của worker hoàn tất trước khi method transactional return.
- Vì commit diễn ra khi `insertAndObserve()` hoàn tất qua proxy, hai worker queries chắc chắn được thực hiện **trước T1 commit**.
- Assertions đo cả trạng thái transaction của worker và kết quả JDBC query, không chỉ xem tên thread.
- Sau khi method trả, query mới thấy row đã commit.
- Listener `AFTER_COMMIT` có `CountDownLatch` để main đợi completion thay vì ngủ với thời lượng đoán trước.
- Một method khác phát event rồi ném unchecked exception để kiểm chứng rollback: row và listener tương ứng không xuất hiện.

**Lưu ý về test harness:** Việc chờ worker bên trong T1 là thiết kế phục vụ **chứng minh isolation**, không phải lời khuyên thiết kế workflow nghiệp vụ như vậy. Production nên tránh giữ transaction mở để chờ các tác vụ async cần đọc lại dữ liệu chưa commit.

### 13.1. Integration test cần có transaction manager thực

Một unit test chỉ mock `JdbcTemplate` hoặc gọi method trực tiếp bằng `new Reader(...)` không chứng minh transaction binding qua Spring proxy. Muốn kiểm tra thread/commit/isolation, phải chạy với Spring context, transaction manager và database/driver thực phù hợp.

### 13.2. Đừng dùng test mặc định @Transactional rồi suy ra production

Nhiều test framework chạy test method trong transaction và rollback cuối test; nếu test spawn worker riêng, worker không tự tham gia test transaction. Kết quả đọc dữ liệu của worker có thể bất ngờ rỗng. Cần biết test transaction boundary, thiết lập dữ liệu đã commit khi cần và kiểm soát rollback/cleanup đúng mục đích.

### 13.3. Tính nhất quán giữa database và side effects

Hãy kiểm thử cả ba trường hợp:

1. Commit thành công rồi worker chạy.
2. Transaction rollback trước khi worker được phát.
3. Worker gặp lỗi sau commit, hệ thống có retry/alert và trạng thái durable hay không.

Ca (3) thường quan trọng hơn một demo đơn giản vì nó quyết định độ tin cậy của nghiệp vụ.

## 14. Cấu hình executor và transaction trong production

Mẫu `ThreadPoolTaskExecutor` trong ví dụ dùng:

```java
pool.setCorePoolSize(2);
pool.setMaxPoolSize(2);
pool.setQueueCapacity(8);
pool.setThreadNamePrefix("tx-worker-");
```

Đây là thông số của demo, không phải mặc định khuyến nghị. Trong production:

- Queue/burst cần được giới hạn rõ ràng, vì delay trước khi worker đọc dữ liệu sẽ ảnh hưởng timing của tác vụ.
- Connection pool phải đủ theo số DB operations có thể chạy đồng thời, nhưng không vượt quá khả năng database.
- Worker có transaction riêng cần timeout, rollback rule và isolation theo nhu cầu.
- DB transaction cần ngắn; không giữ locks/connection qua việc chờ network/mail service nếu không bắt buộc.
- Theo dõi active threads, queue depth, rejection, DB connection wait, transaction duration, deadlocks, slow queries và retry rate.
- Nếu cần việc bền vững, phải có outbox/broker/job store chứ không chỉ tăng executor capacity.

**Không đồng nhất @Async với @Transactional.** Chúng là hai loại advice: một loại quyết định **thread thực thi**, một loại quyết định **ranh giới giao dịch trên thread đang thực thi**. Cách kết hợp hai annotation phải được kiểm thử qua proxy và transaction manager thực tế.

## 15. Những lỗi phổ biến

| Hiểu sai hoặc thiết kế sai | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “@Transactional ở caller bao phủ luôn @Async worker” | Worker không nhìn thấy uncommitted data hoặc không có transaction | Xác định thread boundary; mở transaction riêng ở worker nếu cần |
| Thêm `@Transactional` vào worker để “kế thừa” T1 | Worker có T2 độc lập, không phải T1 | Thiết kế commit order/event/outbox rõ ràng |
| Dùng `REQUIRES_NEW` để mong đọc uncommitted row | T2 vẫn chịu isolation, thường không thấy row của T1 | Chờ commit đúng cách, không ép isolation bừa |
| Gửi @Async ngay sau `save()` rồi nghĩ row đã commit | Worker có thể đọc quá sớm | `@TransactionalEventListener(AFTER_COMMIT)` hoặc outbox |
| Caller đợi worker trong T1 nhưng worker chờ dữ liệu T1 | Có thể deadlock/timeout | Sửa workflow và điểm phát việc sau commit |
| Worker commit side effect, caller rollback | Trạng thái nghiệp vụ phân kỳ | Chỉ phát công việc sau commit, hoặc thiết kế saga/compensation |
| `this.asyncMethod()` lại thấy transaction caller | Self-invocation bypass proxy, chưa thực sự đổi thread | Tách async bean hoặc submit tường minh |
| Cho rằng đổi thành class-based proxy chữa self-invocation | Vẫn bypass lời gọi nội bộ | Kiểm tra proxy boundary, không chỉ proxy type |
| Dùng `TaskDecorator` copy JDBC Connection sang thread khác | Sai resource lifecycle/concurrency assumptions | Chỉ propagate metadata an toàn, không kéo transaction raw |
| Nghĩ `@TransactionalEventListener` là durable queue | Event có thể mất khi process chết | Transactional outbox nếu cần recovery |
| Phát event ngoài transaction rồi chờ listener AFTER_COMMIT | Mặc định listener không chạy | Xem `fallbackExecution` hoặc thiết kế rõ boundary |
| Bỏ qua lỗi worker vì caller không thấy exception | Task lỗi âm thầm hoặc mất outcome | Future/error handler, metrics, retry/status |
| Tin test pass vì worker chạy sau commit | Race không xuất hiện ở test nhẹ | Điều phối/kiểm tra trước commit bằng Future/latch |
| Dùng H2 demo mà kết luận cho mọi database | Isolation và locking khác nhau | Test DB engine/isolation thực tế |
| Cho rằng reactive transaction cũng gắn ThreadLocal | Sai mô hình Reactor Context | Phân biệt imperative với reactive transaction |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Method `register()` được gọi qua `@Transactional` proxy và đang insert order. Nó gọi `notificationWorker.send()` trên bean khác qua `@Async`. Worker có tự dùng T1 không?

Không. T1 là thread-bound imperative transaction. Worker chạy trên thread khác, không tự nhận tài nguyên hay connection của T1.

**Câu 2.** Đặt thêm `@Transactional` lên `send()` có làm hai method cùng transaction không?

Không. Khi @Async advice chuyển lời gọi sang worker và @Transactional advice được áp dụng ở worker, nó có thể mở **T2 độc lập**. T2 không nhìn thấy uncommitted T1 ở isolation như READ_COMMITTED.

**Câu 3.** Nếu worker truy vấn thấy row chưa commit trong test nhẹ, có thể kết luận transaction đã propagate không?

Không. Có thể caller đã commit trước khi worker query, isolation khác kỳ vọng, hoặc method `@Async` chưa thực sự chuyển thread vì self-invocation/SyncTaskExecutor. Phải đo thread name, transaction state và kiểm soát commit timing.

**Câu 4.** Listener `@TransactionalEventListener(AFTER_COMMIT)` có tự bảo đảm email được gửi sau commit ngay cả khi JVM crash?

Không. Nó giúp chọn phase xử lý trong tiến trình còn chạy, nhưng không đảm bảo durability. Với công việc không được phép mất, dùng outbox/durable queue và retry.

**Câu 5.** Vì sao listener AFTER_COMMIT trong demo thấy row 1, nhưng listener cùng loại không nhận event row 2?

Row 1 được commit thành công nên listener phase AFTER_COMMIT kích hoạt; transaction chứa row 2 rollback do exception nên không có commit phase thành công.

**Câu 6.** Khi nào nên giữ hai thao tác DB trong cùng một thread giao dịch thay vì đẩy một thao tác sang @Async?

Khi chúng phải commit/rollback nguyên tử trong **cùng local transaction**. Nếu tách async, cần chấp nhận và thiết kế semantics nhất quán cuối cùng hoặc orchestration khác.

## 17. Checklist áp dụng trước khi đưa vào production

- Có biết transaction manager thực tế là `PlatformTransactionManager` imperative hay reactive `ReactiveTransactionManager`?
- `@EnableTransactionManagement` và `@EnableAsync` có nằm đúng ApplicationContext?
- Các method `@Transactional`/`@Async` có thực sự được gọi qua Spring proxy, không phải `this.method()`?
- Executor thật có chạy ở worker thread khác không, hay đang dùng `SyncTaskExecutor`?
- Worker có cần transaction độc lập không, và propagation/isolation/rollback rule đã rõ chưa?
- Worker có phụ thuộc bản ghi caller vừa ghi nhưng chưa commit không?
- Nếu cần chạy sau commit, đã dùng phase AFTER_COMMIT hoặc transactional outbox chưa?
- Có chính sách khi transaction rollback và khi worker thất bại **sau commit**?
- Có thiết kế idempotency/deduplication và lưu trạng thái task durable khi cần?
- Có tránh giữ DB transaction mở để chờ Future/network không?
- Có đo thread, transaction state, commit visibility và DB connection pool dưới tải?
- Có test rollback/commit trên DB và isolation thực tế, thay vì chỉ dùng mock?
- Có tránh truyền raw JDBC Connection/EntityManager/transaction ThreadLocal sang worker?
- Có cơ chế timeout/retry/alert cho công việc nền quan trọng?

## 18. Kết luận

Trong Spring Framework imperative, **giao dịch thông thường gắn với thread thực thi**, thông qua transaction manager và resource binding. Khi một lời gọi `@Async` thực sự đi qua proxy và được chạy trên worker khác, **transaction của caller không tự chuyển theo**.

Worker không có `@Transactional` thường không có transaction caller. Worker có `@Transactional` có thể mở transaction **riêng**, nhưng không vì thế mà được đọc dữ liệu chưa commit hoặc cùng rollback với caller. Muốn công việc bắt đầu sau commit, hãy sử dụng ranh giới transaction/event rõ ràng; muốn không mất việc qua restart, cần một cơ chế bền vững như **transactional outbox**.

### Tài liệu tham khảo

- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Task Execution and @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework 6.2.1 — @Transactional](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework 6.2.1 — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Framework 6.2.1 — @TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)