# Không giả định hai tác vụ trên hai luồng có thể rollback cùng nhau

Trong Spring Framework, `@Transactional` giúp quản lý ranh giới giao dịch, còn `@Async` và `TaskExecutor` giúp chuyển công việc sang một luồng khác. Kết hợp hai cơ chế này **không tự tạo ra một giao dịch duy nhất bao trùm nhiều luồng**.

Với mô hình giao dịch imperative thông thường của Spring (`PlatformTransactionManager`, JDBC/JPA), transaction được gắn với **luồng thực thi hiện tại**. Khi method A đang trong transaction và gửi method B tới một worker của thread pool, worker **không tự thừa hưởng transaction của A**. Nếu B có một transaction riêng, B có thể commit độc lập trước khi A rollback; ngược lại, A có thể commit khi B thất bại.

**Quy tắc cốt lõi: rollback của một transaction không phải lệnh “hoàn tác mọi công việc đồng thời”**. Muốn hai thao tác thật sự có tính nguyên tử, chúng cần nằm trong một ranh giới giao dịch được transaction manager và tài nguyên hỗ trợ. Muốn xử lý bất đồng bộ bền vững và nhất quán giữa nhiều bước, cần thiết kế giao thức rõ như event sau commit, transactional outbox hoặc saga, không chỉ gắn `@Transactional` lên hai method.

Bài Knowledge thuộc nhóm **Giao dịch và sự kiện** trong **Spring Framework - concurrency**. Ví dụ dựa trên Java 17+, Spring Framework 6.x / Spring Boot 3.x; phần Java thuần có thể biên dịch độc lập, còn code Spring yêu cầu database và Spring dependencies.

## 1. Giao dịch thực sự là gì trong trường hợp này?

Một database transaction thường có những thao tác: bắt đầu, đọc/ghi, commit hoặc rollback. Với JDBC, các câu lệnh nằm trên cùng connection và cùng transaction có thể được commit hoặc rollback **như một đơn vị** theo khả năng của database.

Trong Spring imperative, `@Transactional` được triển khai thường qua Spring AOP proxy và `TransactionInterceptor`. Transaction manager quản lý connection, session và trạng thái giao dịch gắn với thread. Các thao tác truy cập dữ liệu **tham gia cùng ranh giới transaction khi chúng dùng transaction manager/tài nguyên thích hợp và được thực thi trong context đó**.

Ví dụ cùng thread:

~~~text
Thread HTTP #1
    |
    | --> Transaction T1 bắt đầu
    |     INSERT orders
    |     INSERT audit_events
    |     throw RuntimeException
    | --> T1 rollback
    |
    +--> cả hai INSERT của T1 được rollback
         (nếu cùng tài nguyên transactional và không có commit độc lập)
~~~

Trường hợp này khác hẳn hai worker:

~~~text
Thread HTTP #1 / Transaction T1             Worker #2 / Transaction T2
    |                                               |
    | BEGIN T1                                      |
    | INSERT orders                                 |
    |---- submit async audit ---------------------->|
    |                                               | BEGIN T2
    |                                               | INSERT audit_events
    |                                               | COMMIT T2
    | throw RuntimeException                        |
    | ROLLBACK T1                                   |
    |                                               |
    v                                               v
  orders bị rollback                        audit_events của T2
                                            vẫn đã commit
~~~

Đây là **một kết quả có thể xảy ra**, không khẳng định mọi lần chạy đều theo đúng lịch đó. Nếu worker được xếp queue lâu, nó có thể bắt đầu sau khi T1 rollback. Nếu worker cần đọc dữ liệu chưa commit của T1, nó còn có thể bị chặn, không nhìn thấy dữ liệu, hoặc vướng foreign-key constraint. Điều quan trọng là **hai giao dịch không được đồng bộ commit/rollback chỉ vì được gọi từ cùng một request**.

### 1.1. Phạm vi của nhận định

Bài này nói về transaction imperative do `PlatformTransactionManager` quản lý trong cấu hình Spring thông dụng, chẳng hạn `DataSourceTransactionManager` / `JdbcTransactionManager` hoặc `JpaTransactionManager`. Các transaction này thường **thread-bound**, không tự lan sang luồng khác.

Mô hình reactive của Spring có thể dùng `ReactiveTransactionManager` và Reactor Context thay vì ThreadLocal. Đây là một kiến trúc truyền context khác, **không phải bằng chứng rằng @Transactional tự động rollback đồng bộ mọi task trên nhiều thread**. Không trộn ngữ nghĩa reactive với JDBC/JPA imperative khi đánh giá bài toán này.

## 2. Tại sao @Transactional không tự “đi theo” @Async?

Cơ chế phổ biến:

1. Caller đi qua Spring proxy của method `@Transactional`; interceptor mở/đăng ký transaction **cho thread caller**.
2. Bên trong method, code gọi bean có `@Async` qua một Spring proxy khác.
3. Interceptor `@Async` submit callback vào `TaskExecutor`. Với thread pool bất đồng bộ, worker khác sẽ thực thi callback.
4. Transaction context đang gắn với thread caller **không tự chuyển qua worker**.
5. Nếu worker gọi một method transactional qua proxy, Spring có thể mở **một transaction riêng** trên worker; nếu không có transactional advice ở worker, các câu lệnh có thể chạy autocommit hoặc theo cấu hình khác.
6. Caller kết thúc hoặc ném exception; transaction của caller commit/rollback theo quy tắc riêng. Trạng thái đó không tự undo transaction worker đã commit.

~~~text
HTTP thread                     @Async interceptor                Pool worker
    |                                  |                               |
    | BEGIN parent TX                  |                               |
    | INSERT parent                    |                               |
    |---- asyncMethod() -------------->|-- queue task ---------------->|
    |<--- return Future ---------------|                               |
    |                                  |                         BEGIN worker TX?
    |                                  |                         INSERT child
    |                                  |                         COMMIT/ROLLBACK
    | ROLLBACK parent TX               |                               |
    |                                  |                               |
    | Không có implicit shared transaction giữa hai thread             |
~~~

Ký hiệu dấu hỏi ở `BEGIN worker TX?` có chủ đích: worker chỉ nhận một transaction riêng khi cấu hình, annotation/proxy và resource manager thực sự tạo nó; **không phải mọi @Async task đều mặc nhiên có transaction**.

### 2.1. REQUIRED, REQUIRES_NEW và sự nhầm lẫn thường gặp

- `Propagation.REQUIRED`: trong cùng thread và cùng transaction manager, method transactional có thể tham gia transaction đang có; nếu không có transaction tương ứng, Spring tạo mới.
- Khi B chạy trên **một worker khác**, B thường không thấy transaction A trên caller. `REQUIRED` ở B do đó có thể mở một transaction mới **cho worker**, không nối vào A.
- `Propagation.REQUIRES_NEW` tạo một physical transaction độc lập khi có transaction đang chạy trong context đó; nó **không phải công cụ gộp hai thread**. Transaction mới có thể commit/rollback độc lập.
- `Propagation.NESTED` dùng savepoint của một physical transaction theo khả năng transaction manager/database; không biến hai database connection khác luồng thành một unit rollback chung.
- Nếu dùng cùng một `DataSource` thì vẫn **không đồng nghĩa** cùng một JDBC connection/transaction. Mỗi thread thường có tài nguyên riêng được transaction manager bind.

Trong code imperative Spring, propagation mô tả cách xử lý **các lời gọi trong context transaction đang thấy**, không phải cơ chế tự truyền một transaction qua `ExecutorService.submit`.

## 3. Java 17: mô phỏng hai transaction theo ThreadLocal

Chương trình này mô phỏng đơn giản **việc transaction context gắn với thread** và việc commit/rollback riêng. Nó **không kết nối database và không phải implementation giao dịch JDBC**; mục đích là làm rõ tại sao một worker không tự thừa hưởng trạng thái từ caller.

Tạo tệp **`CrossThreadTransactionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CrossThreadTransactionDemo {
    record Tx(String name, List<String> staged) {}

    private static final ThreadLocal<Tx> CURRENT = new ThreadLocal<>();
    private static final List<String> COMMITTED = new CopyOnWriteArrayList<>();

    static void begin(String name) {
        CURRENT.set(new Tx(name, new ArrayList<>()));
    }

    static void stage(String change) {
        Tx tx = CURRENT.get();
        if (tx == null) {
            throw new IllegalStateException("No local transaction");
        }
        tx.staged().add(change);
    }

    static void commit() {
        Tx tx = CURRENT.get();
        if (tx == null) {
            throw new IllegalStateException("No local transaction");
        }
        COMMITTED.addAll(tx.staged());
        CURRENT.remove();
    }

    static void rollback() {
        CURRENT.remove();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        begin("caller");
        try {
            stage("order");
            Future<?> child = executor.submit(() -> {
                System.out.println("1. Child inherited transaction: "
                        + (CURRENT.get() != null));
                begin("child");
                try {
                    stage("audit");
                    commit();
                    System.out.println("2. Child committed audit");
                } finally {
                    CURRENT.remove();
                }
            });
            child.get();
            rollback();
            System.out.println("3. Caller rolled back order");
            System.out.println("4. Committed changes: " + COMMITTED);
        } finally {
            CURRENT.remove();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 CrossThreadTransactionDemo.java
java CrossThreadTransactionDemo
~~~

Stdout đã được xác minh khi chạy với JDK biên dịch ở mức `--release 17`:

~~~text
1. Child inherited transaction: false
2. Child committed audit
3. Caller rolled back order
4. Committed changes: [audit]
~~~

Giải thích:

1. `ThreadLocal<Tx>` thông thường không được copy sang worker thread. `CURRENT.get()` trên worker là `null`, nên in `false`.
2. Worker tự gọi `begin("child")`, stage thay đổi `audit` rồi `commit()`. Danh sách mô phỏng dữ liệu đã commit nhận `audit`.
3. `Future.get()` khiến caller **đợi worker hoàn tất**, nhưng **không nhập transaction của worker vào transaction của caller**.
4. Caller rollback thao tác `order` đã stage trong context riêng; thay đổi `audit` đã commit vẫn ở danh sách.
5. Thứ tự output xác định nhờ `Future.get()` và việc worker không in từ nhiều luồng không đồng bộ cùng lúc trong các bước cần kiểm tra.

Điểm mấu chốt: **chờ worker chạy xong không đồng nghĩa có chung transaction**. `CompletableFuture.allOf(...).join()` cũng chỉ là cơ chế đợi hoàn tất nhiều future; không có tính chất tự rollback mọi transaction đã commit.

### 3.1. Điều mô phỏng này không chứng minh

- Không thực hiện JDBC commit hoặc rollback thực.
- Không kiểm tra isolation level, lock, deadlock hay constraint.
- Không chứng minh rằng cứ dùng Spring là kết quả luôn giống đúng thứ tự stdout trên.
- Không có distributed transaction coordinator.

Để đánh giá chính xác ứng dụng, cần integration test với database và transaction manager thật ở các mục sau.

## 4. Một anti-pattern Spring: parent rollback nhưng worker commit riêng

Giả sử ứng dụng quản lý đơn hàng và audit bằng Spring JDBC. Sơ đồ dữ liệu chỉ nhằm học: bảng `audit_events` trong ví dụ **không có foreign key** đến bảng `orders` để quan sát trường hợp audit độc lập vẫn commit dù order bị rollback.

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(32) NOT NULL
);

CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(48) NOT NULL
);
~~~

DDL trên là ví dụ cho database hỗ trợ cú pháp identity tương ứng (ví dụ H2); trong PostgreSQL hoặc hệ quản trị khác cần kiểm tra dialect và migration phù hợp. **Không bỏ foreign key trong thiết kế thật chỉ để tránh lỗi**; ở đây việc không có FK cố ý để làm lộ rủi ro ghi “audit mồ côi”.

### 4.1. Bean executor và quản lý transaction

Tệp `ConcurrentTxConfig.java`:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableAsync
@EnableTransactionManagement
public class ConcurrentTxConfig {

    @Bean("auditExecutor")
    public ThreadPoolTaskExecutor auditExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("audit-");
        return executor;
    }
}
~~~

Đây là **mã tích hợp Spring Framework 6.x / Java 17+**, không phải chương trình có thể chạy bằng `javac` thiếu Spring dependencies. Cần một `PlatformTransactionManager` được cấu hình đúng cho JDBC/JPA, datasource, schema và component scanning. Trong Spring Boot tương thích, những thành phần này thường do cấu hình/data-access starter cung cấp; với Spring Framework thuần phải đăng ký phù hợp.

### 4.2. AuditWriter mở transaction riêng khi được worker gọi

Tệp `AuditWriter.java`:

~~~java
package example.concurrency;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriter {
    private final JdbcTemplate jdbc;

    public AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void saveRequested(long orderId) {
        jdbc.update(
                "INSERT INTO audit_events(order_id, event_type) VALUES (?, ?)",
                orderId, "ORDER_REQUESTED");
    }
}
~~~

Tệp `AsyncAuditDispatcher.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncAuditDispatcher {
    private final AuditWriter writer;

    public AsyncAuditDispatcher(AuditWriter writer) {
        this.writer = writer;
    }

    @Async("auditExecutor")
    public CompletableFuture<Void> dispatch(long orderId) {
        writer.saveRequested(orderId);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Lời gọi đi qua **hai bean/proxy khác nhau**: Spring gửi `AsyncAuditDispatcher.dispatch(...)` tới worker; trên worker, lời gọi `AuditWriter.saveRequested(...)` đi qua transactional proxy và mở giao dịch của worker. Việc tách này giúp tránh nhầm lẫn về thứ tự các advice khi đặt `@Async` và `@Transactional` trên cùng một method và tránh self-invocation.

### 4.3. Parent transaction gửi công việc rồi rollback

Tệp `OrderCreationService.java`:

~~~java
package example.concurrency;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCreationService {
    private final JdbcTemplate jdbc;
    private final AsyncAuditDispatcher audit;

    public OrderCreationService(
            JdbcTemplate jdbc, AsyncAuditDispatcher audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    @Transactional
    public void createThenFail(long orderId) {
        jdbc.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                orderId, "PENDING");

        audit.dispatch(orderId);

        throw new IllegalStateException("rollback order transaction");
    }
}
~~~

Ví dụ trên cố ý minh họa **thiết kế không an toàn**:

- Parent insert `orders` trong transaction T1 chưa commit.
- Parent submit audit; caller **không đợi** worker và cũng không xử lý future trả về.
- Worker có thể bắt đầu T2, insert `audit_events` và commit.
- Parent ném `IllegalStateException`, dẫn tới T1 rollback theo quy tắc mặc định của `@Transactional` cho `RuntimeException`.
- Nếu T2 đã commit, hàng audit có thể vẫn tồn tại dù order đã rollback. Hoặc T2 có thể chạy sau khi T1 rollback và vẫn insert audit.

Không có stdout xác định cho ví dụ tích hợp Spring vì thứ tự scheduler, database, queue và cấu hình connection pool thay đổi kết quả quan sát. Nếu thêm foreign key từ audit đến order, worker có thể bị chặn hoặc gặp lỗi ràng buộc do order chưa commit/đã rollback; đó là **một dạng hỏng khác**, không phải cách sửa ranh giới giao dịch.

Với `@Async` trả `CompletableFuture`, exception phát sinh trong worker có thể làm Future hoàn tất thất bại. Nhưng vì parent không giữ/quan sát Future, lỗi dễ bị bỏ sót; cho dù parent gọi `get()` rồi throw để rollback T1, T2 **đã commit sẽ không tự rollback**.

### 4.4. Bốn kết cục khác nhau cần phân biệt

| Thứ tự thực tế | Kết quả có thể xảy ra |
| --- | --- |
| T2 commit, sau đó T1 rollback | Audit tồn tại, order không tồn tại |
| T1 rollback trước, T2 chạy và commit | Audit vẫn có thể tồn tại nếu không có constraint |
| T1 commit, T2 lỗi/rollback | Order tồn tại nhưng audit thiếu |
| T1 commit, T2 commit | Cả hai tồn tại, nhưng vẫn **không phải một atomic transaction** |

Cơ chế chạy song song tạo ra nhiều interleaving, không có cam kết all-or-nothing. Nếu cùng cần DB connection và pool hết chỗ, còn có thể phát sinh blocking hoặc deadlock khi caller giữ transaction trong lúc đợi worker.

## 5. Khi cần atomic rollback: giữ các ghi liên quan trong một transaction

Nếu hai thao tác là các bản ghi cùng một database và nghiệp vụ đòi hỏi **cùng thành công hoặc cùng thất bại**, giải pháp đơn giản thường là thực hiện chúng **trong một method transaction cùng thread**.

Tệp `AtomicOrderService.java` (một phương án **thay thế**, không dùng cùng lúc với anti-pattern):

~~~java
package example.concurrency;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AtomicOrderService {
    private final JdbcTemplate jdbc;

    public AtomicOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrderWithAudit(long orderId) {
        jdbc.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                orderId, "PENDING");
        jdbc.update(
                "INSERT INTO audit_events(order_id, event_type) VALUES (?, ?)",
                orderId, "ORDER_CREATED");
    }
}
~~~

Khi `@Transactional` thật sự hoạt động và cả hai câu SQL cùng tham gia transaction của cùng datasource/transaction manager, nếu một thao tác ném `RuntimeException` không bị xử lý nuốt, transaction có thể rollback cả hai. Nếu method commit thành công, cả hai ghi cùng được xác nhận theo hợp đồng của database.

Lưu ý: không tự động mở rộng khẳng định này sang HTTP request gửi cho dịch vụ ngoài, gửi email, message broker không tham gia cùng transaction hay các tài nguyên không được enlist. Một giao dịch DB **không có nút Undo cho side effect bên ngoài**.

### 5.1. Nếu vẫn muốn xử lý song song?

Đặt câu hỏi trước: liệu yêu cầu thật sự là xử lý parallel và atomic? Một local DB transaction dựa vào một connection không được thiết kế để chia cho nhiều worker tùy ý. Không chuyển cùng một `Connection` hoặc JPA `EntityManager` cho các thread rồi cố dùng chung: các đối tượng truy cập dữ liệu này thường không được thiết kế thread-safe, và Spring không cung cấp cơ chế tự động làm điều đó an toàn.

Nếu cần throughput, có thể chuẩn bị/tính toán dữ liệu song song **không thực hiện side effect**, sau đó tập hợp kết quả và thực hiện các ghi cần atomic trong một transaction trên một thread. Mô hình này vẫn phải xem xét bộ nhớ, timeout và lỗi của các phép tính song song, nhưng tránh chia sẻ transaction DB xuyên thread.

## 6. Sau commit mới phát sự kiện: @TransactionalEventListener

Một vấn đề riêng là **không nên chạy task phụ nếu transaction chính rollback**. Với sự kiện chỉ có ý nghĩa sau khi dữ liệu đã commit, Spring hỗ trợ `@TransactionalEventListener`, mặc định liên kết listener với phase `AFTER_COMMIT`.

Ví dụ, service phát event bên trong transaction:

~~~java
package example.concurrency;

public record OrderCreatedEvent(long orderId) {}
~~~

Tệp `OrderRegistrationService.java`:

~~~java
package example.concurrency;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderRegistrationService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher events;

    public OrderRegistrationService(
            JdbcTemplate jdbc, ApplicationEventPublisher events) {
        this.jdbc = jdbc;
        this.events = events;
    }

    @Transactional
    public void create(long orderId) {
        jdbc.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                orderId, "CREATED");
        events.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

Tệp `OrderCreatedListener.java`:

~~~java
package example.concurrency;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCreatedListener {
    private final AuditWriter writer;

    public OrderCreatedListener(AuditWriter writer) {
        this.writer = writer;
    }

    @Async("auditExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        writer.saveRequested(event.orderId());
    }
}
~~~

Các đoạn trên là **mẫu tích hợp thay thế** cho anti-pattern, dùng `ConcurrentTxConfig`, `AuditWriter`, schema và transaction manager đã nêu. Không có output cố định. Ý nghĩa:

- Event được publish trong transaction T1.
- Nếu T1 rollback, listener `AFTER_COMMIT` **không thực hiện logic ứng với commit thành công**.
- Sau khi T1 commit, callback của listener mới được kích hoạt; `@Async` chuyển phần xử lý sang executor đã chọn.
- `AuditWriter.saveRequested(...)` chạy trên worker qua proxy transactional của mình, vì vậy có transaction ghi audit **riêng**, không phải một phần của T1.

**Giới hạn quan trọng:** `AFTER_COMMIT` chỉ xác định **thời điểm bắt đầu xử lý event liên quan đến commit**, không bảo đảm audit chắc chắn được xử lý. Ứng dụng có thể crash ngay sau DB commit nhưng trước khi async job được lưu/chạy; executor có thể từ chối, worker có thể fail, event in-memory có thể mất. Và nếu audit thất bại sau commit, **không rollback lại order đã commit**.

`@TransactionalEventListener` mặc định **không chạy khi không có transaction** để gắn phase, trừ khi chủ động dùng `fallbackExecution=true`. Đừng bật fallback chỉ để “cho chạy bằng mọi giá” nếu nghiệp vụ yêu cầu chỉ phát sau commit.

### 6.1. Các phase sự kiện không có nghĩa rollback xuyên thread

| Phase | Khi nào listener được kích hoạt? | Điều không được suy ra |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction chuẩn bị commit | Không có bảo đảm callback async là một phần của commit DB |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Không biến tác vụ chạy sau đó thành atomic với transaction trước |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Không tự rollback mọi side effect đã xảy ra ở worker khác |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc dù commit hoặc rollback | Không cung cấp durable retry hoặc sự kiện đúng một lần |

Nếu xử lý **đồng bộ ngay trong AFTER_COMMIT** và tiếp tục ghi DB bằng tài nguyên transactional cũ, cần cẩn trọng: tài nguyên có thể còn bound trong giai đoạn callback nhưng transaction chính đã hoàn tất; những ghi mới có thể không được commit theo cách bạn mong đợi. Có thể dùng transaction mới (ví dụ `REQUIRES_NEW` theo trường hợp) hoặc chuyển sang worker có transaction riêng. Điều này vẫn không làm hai transaction atomic.

## 7. Khi cần phát việc chắc chắn sau commit: transactional outbox

Nếu yêu cầu là **order commit thì chắc chắn có bản ghi để về sau phát event**, một listener in-memory `AFTER_COMMIT` chưa đủ độ bền. Mẫu **transactional outbox** lưu **domain data và bản ghi sự kiện** trong cùng một local DB transaction.

~~~text
Transaction T1 (một DB)
     |
     +-- INSERT orders
     +-- INSERT outbox_events
     +-- COMMIT cả hai
             |
             v
      Worker / relay độc lập
             |
             +-- đọc bản ghi outbox đã commit
             +-- publish event / gửi broker
             +-- ghi nhận đã gửi hoặc retry
             |
             v
      Consumer xử lý idempotent
~~~

Nếu T1 rollback, cả `orders` và `outbox_events` cùng rollback. Nếu T1 commit, ít nhất có bản ghi outbox bền vững để relay tiếp tục sau restart. **Đây là ranh giới atomic thật cần thiết** giữa dữ liệu đơn hàng và *ý định phát sự kiện*, không phải giữa transaction của DB và quá trình xử lý remote.

Ví dụ schema bổ sung (SQL minh họa; cần điều chỉnh dialect):

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload VARCHAR(2048) NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Tệp `OutboxOrderService.java`:

~~~java
package example.concurrency;

import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxOrderService {
    private final JdbcTemplate jdbc;

    public OutboxOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrder(long orderId) {
        jdbc.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                orderId, "CREATED");

        String eventId = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO outbox_events(" +
                "event_id, aggregate_id, event_type, payload, published) " +
                "VALUES (?, ?, ?, ?, ?)",
                eventId, orderId, "ORDER_CREATED",
                "{\"orderId\":" + orderId + "}", false);
    }
}
~~~

Đây là **mã tích hợp Spring/JDBC**, không có relay trong đoạn code. Relay riêng phải đọc các hàng chưa publish, quản lý concurrency/claim/lease, gửi broker, retry/backoff và cập nhật trạng thái với cơ chế chống mất/đúp phù hợp.

### 7.1. Tại sao outbox không có nghĩa exactly-once toàn hệ thống?

Một relay có thể gửi event thành công tới broker rồi crash **trước khi** đánh dấu outbox đã publish. Sau restart, event được gửi lại. Vì vậy cách triển khai thực tế thường có **at-least-once delivery** và người nhận phải xử lý **idempotent** theo `event_id` hoặc idempotency key.

Outbox giải quyết khoảng trống giữa commit domain data và **đảm bảo lưu ý định gửi event**, không khiến toàn bộ hệ thống từ DB đến email/payment có một transaction rollback chung. Cần thiết kế ordering, deduplication, poison-message handling và quan sát backlog theo yêu cầu.

## 8. Saga và compensation khi nhiều giao dịch độc lập

Khi một nghiệp vụ trải qua nhiều service/database, thường không thể gom mọi bước thành một local transaction. **Saga** xem mỗi bước là một local transaction riêng, đồng thời định nghĩa **hành động bù trừ** nếu các bước sau thất bại.

Ví dụ luồng đặt hàng:

~~~text
T1: tạo order PENDING        -> commit
T2: reserve inventory       -> commit
T3: charge payment          -> fail

Compensation C2: release inventory (transaction mới)
Compensation C1: mark order FAILED (transaction mới)
~~~

Điều quan trọng:

- Compensation **không phải rollback vật lý**. Nó là hành động nghiệp vụ mới, có thể thất bại, retry, hoặc để lại dấu vết lịch sử.
- Nếu email đã gửi hoặc dịch vụ thứ ba đã thấy sự kiện, không có “undo” hoàn hảo.
- Cần state machine, correlation id, idempotency, timeout, retry có giới hạn, cơ chế phát hiện thao tác bị kẹt và người vận hành có thể xử lý ngoại lệ.
- Nếu compensation không thành công, workflow phải giữ trạng thái cần xử lý chứ không báo sai “đã rollback toàn bộ”.
- Saga không được thực hiện bằng cách đơn giản catch exception từ `CompletableFuture.allOf` rồi gọi rollback cho mọi database khác nếu các transaction đã commit.

### 8.1. Distributed transaction / XA có tồn tại không?

Có những hệ thống có thể triển khai distributed transaction bằng cơ chế JTA/XA và transaction coordinator với các resource hỗ trợ. Tuy nhiên **đây là một kiến trúc được cấu hình chuyên biệt**, có chi phí, giới hạn và yêu cầu resource enlistment; không tự xuất hiện khi ta gắn `@Transactional` lên các method trên nhiều worker.

Vì vậy tiêu đề bài không nói “hai luồng không bao giờ có thể tham gia một protocol transaction phân tán”, mà nói **không được mặc định coi hai tác vụ trên hai luồng của Spring có thể rollback cùng nhau**.

## 9. Future, join và ngoại lệ không tạo transaction chung

Một lỗi thiết kế phổ biến:

~~~java
@Transactional
public void process() {
    CompletableFuture<Void> f1 = worker.updateA();
    CompletableFuture<Void> f2 = worker.updateB();

    CompletableFuture.allOf(f1, f2).join();
    // Nếu bất kỳ Future lỗi, ném exception để rollback parent.
}
~~~

Đây là **pseudocode Java/Spring**: cần các bean `worker` và code method khác. Nếu `worker.updateA()/updateB()` chạy trên các thread khác với transaction riêng:

- `allOf(...).join()` chỉ chờ các Future hoàn tất. Nó **không biết transaction DB nào đã commit**, không có nút Undo các commit đó.
- Nếu f1 commit T1, f2 rollback T2, rồi `join()` ném `CompletionException`, transaction của caller (nếu có) có thể rollback; **T1 đã commit vẫn độc lập**.
- Khi caller còn giữ DB connection trong transaction và đợi worker lấy connection khác, có thể gặp thiếu connection, block hoặc deadlock. Thời gian chờ kéo dài có thể khiến outer transaction giữ lock lâu.
- `Future.cancel(true)` cũng không bảo đảm ngắt task đang chạy; với `CompletableFuture.cancel()`, tín hiệu cancel của Future càng không có nghĩa rollback transaction worker đã commit.

Nếu thật sự cần một transaction atomic, không dùng `allOf` để mô phỏng transaction manager. Nếu cần concurrency, tách tính toán song song khỏi phần commit atomic, hoặc chấp nhận mô hình eventual consistency có bù trừ.

## 10. Transaction rollback mặc định cần được hiểu đúng

Trong Spring `@Transactional` với transaction manager imperative thông thường:

- `RuntimeException` hoặc `Error` không được bắt ở biên method transactional thường khiến Spring đánh dấu rollback theo quy tắc mặc định.
- Checked exception (như một số `Exception` không phải `RuntimeException`) **không tự kích hoạt rollback** mặc định; có thể dùng `rollbackFor` khi cần.
- Nếu method bắt exception rồi trả về bình thường mà không đánh dấu rollback-only, transaction có thể commit dù một bước logic đã thất bại.
- Lời gọi method cùng bean như `this.transactionalMethod()` có thể bỏ qua Spring proxy, làm `@Transactional` không có hiệu lực trong proxy mode mặc định.
- `@Async` cũng phụ thuộc interceptor/proxy. Không có bảo đảm về ranh giới nếu method không đi qua proxy như dự kiến.

Đây là lý do các ví dụ Spring trong bài dùng **nhiều bean khác nhau**, không để một method vừa submit async vừa gọi trực tiếp một method `@Transactional` trong chính cùng object.

### 10.1. Transaction của parent đã commit thì lỗi worker làm gì?

Giả sử parent gọi async worker rồi commit thành công. Vài giây sau, worker phát hiện lỗi. Parent transaction **không còn active** để có thể rollback bằng exception worker. Cần cập nhật trạng thái job, retry/idempotency hoặc compensation theo hợp đồng nghiệp vụ.

Với `@Async void`, exception chưa xử lý đi qua `AsyncUncaughtExceptionHandler`. Với `@Async CompletableFuture<T>`, exception execution được phản ánh ở Future. **Cả hai không tự rollback một transaction khác đã commit**.

## 11. Quan sát và xử lý lỗi trong hệ thống thực

Các trạng thái nên theo dõi cho mỗi workflow:

| Sự kiện / trạng thái | Thông tin quan trọng |
| --- | --- |
| `PARENT_TX_STARTED` | Correlation id, transaction/workflow id |
| `PARENT_COMMITTED` hoặc `PARENT_ROLLED_BACK` | Ranh giới kết thúc của parent |
| `CHILD_SUBMITTED` và `CHILD_REJECTED` | Executor nhận được task hay từ chối |
| `CHILD_STARTED` | Worker thực sự bắt đầu |
| `CHILD_COMMITTED` hoặc `CHILD_ROLLED_BACK` | Kết quả của transaction child |
| `EVENT_PERSISTED` | Outbox event được ghi trong local transaction |
| `EVENT_PUBLISHED` và `EVENT_RETRIED` | Relay gửi event, có thể gửi lại |
| `COMPENSATION_REQUESTED` / `COMPENSATION_DONE` | Quy trình bù trừ và kết quả |
| `FAILED_NEEDS_ATTENTION` | Workflow không thể tự phục hồi |

Tên trên là **gợi ý log/metric cho ứng dụng**, không phải state Spring tự cung cấp sẵn. Đừng ghi toàn bộ payload nhạy cảm; dùng correlation/job/event id để nối các bước và hạn chế cardinality khi đẩy vào metrics.

### 11.1. Phân biệt ba loại lỗi

**Lỗi submit:** executor bão hòa/shutdown nên không nhận task; ví dụ Spring `TaskRejectedException`. Nếu parent transaction vẫn đang chạy và exception không bị bắt, nó có thể khiến parent rollback. Điều đó **không phải rollback một child transaction đã commit**, vì child có thể chưa được nhận.

**Lỗi thực thi child:** worker đã chạy, DB operation thất bại, child transaction rollback; parent có thể đã commit hoặc đang chạy. Lỗi Future/handler chỉ giúp quan sát, không đồng bộ rollback.

**Lỗi truyền event / gửi message:** giao dịch DB đã commit nhưng relay/broker/network lỗi. Nếu dùng outbox, event còn để retry; nếu chỉ gửi async từ memory, công việc có thể mất.

Đặt chính sách retry khác nhau cho từng nhóm. Không retry vô hạn một lỗi cố định, không retry payment/side effect mà không có idempotency.

## 12. Kiểm thử ranh giới transaction bằng chứng cứ thực

Với Java demo trong mục 3, `ThreadLocal` và danh sách COMMITTED cho phép thấy cơ chế **ngữ cảnh hai thread tách nhau**. Nhưng muốn xác minh Spring/JDBC cần integration test với transaction manager và DB.

Một checklist:

1. **Kiểm tra proxy:** `@EnableTransactionManagement` / auto-configuration, `@EnableAsync`, bean injection, lời gọi từ bean khác. Không gọi `new Service()` trực tiếp.
2. **Kiểm tra connection/transaction:** trong worker, `TransactionSynchronizationManager.isActualTransactionActive()` có thể giúp quan sát có transaction đang active **trên thread hiện tại**, nhưng không chứng minh shared transaction với caller. Có thể đo tên thread/connection id theo công cụ datasource để hỗ trợ.
3. **Dùng latch thay sleep ngẫu nhiên:** chủ động giữ worker hoặc parent tại ranh giới cụ thể để ép các thứ tự commit/rollback; tránh test chập chờn do lịch OS.
4. **Test parent rollback, child commit:** nếu schema cho phép, parent insert rồi throw; child chạy riêng và commit; sau cùng truy vấn DB ngoài test transaction để thấy chỉ dữ liệu child tồn tại.
5. **Test parent commit, child fail:** parent commit rồi worker ném lỗi; xác minh dữ liệu parent còn, Future/job status ghi lỗi child.
6. **Test AFTER_COMMIT:** phát event bên trong transaction. Khi rollback, listener không phát nhiệm vụ commit; khi commit, listener được kích hoạt. Nếu dùng `@Async`, test cần đợi callback bằng latch/eventually assertion.
7. **Test outbox:** khi transaction rollback, domain và outbox đều mất; khi commit, cả hai còn. Giả lập relay gửi thành công nhưng chết trước ACK để kiểm tra deduplication.
8. **Test connection pressure:** kiểm tra trường hợp caller giữ transaction và đợi worker cũng muốn lấy connection. Tránh cấu hình pool mà không đủ connections.
9. **Test failure trong compensation:** đảm bảo state machine không tự báo workflow đã rollback thành công khi bước bù trừ thất bại.

**Cẩn trọng với test mặc định có `@Transactional` trên chính test method**: framework test có thể rollback transaction của test sau mỗi case, trong khi worker async dùng transaction khác. Điều này có thể che giấu hoặc làm khó đọc kết quả. Đối với test độ bền commit/rollback, chủ động quản lý transaction boundary và kiểm tra DB từ bên ngoài transaction test.

## 13. Những hiểu nhầm cần tránh

**“Cả A và B đều có @Transactional nên rollback của A cũng rollback B.”** Sai khi A/B có transaction riêng trên các worker khác. Annotation không tự tạo global transaction.

**“Dùng cùng một DataSource thì chắc chắn cùng transaction.”** Sai. Thread khác thường lấy connection và transaction context khác.

**“Propagation.REQUIRED tự tham gia transaction caller dù gọi @Async.”** Sai trong mô hình PlatformTransactionManager thread-bound; worker không tự thấy context của caller.

**“Dùng REQUIRES_NEW để khiến hai tác vụ rollback cùng nhau.”** Sai. `REQUIRES_NEW` cố ý tạo physical transaction độc lập.

**“Gọi allOf().join() trước khi method return sẽ làm mọi child atomic.”** Sai. Đợi Future không hợp nhất các commit đã thực hiện.

**“Parent rollback thì @Async đã gửi chắc chắn không chạy.”** Sai. Task có thể đã được nhận và xử lý; nó không biết parent rollback nếu không có giao thức.

**“@TransactionalEventListener(AFTER_COMMIT) bảo đảm event không mất.”** Sai. Nó tránh xử lý khi parent rollback, nhưng một callback async in-memory vẫn có thể mất sau commit; outbox giải quyết độ bền của ý định gửi.

**“Nếu audit có foreign key đến order thì hai transaction tự atomic.”** Sai. FK có thể làm worker bị chặn hoặc fail khi parent chưa commit/rollback, không tạo chung transaction.

**“Saga rollback tất cả các transaction đã commit.”** Sai. Saga chạy các **compensating actions** mới; không thực hiện DB rollback vật lý xuyên service.

**“Exception của child Future ném muộn vẫn rollback parent đã commit.”** Sai. Khi parent transaction đã kết thúc, không có ranh giới active để quay lại.

## 14. Bài tập và lời giải

**Câu 1.** Method A có `@Transactional` trên thread HTTP, gọi B có `@Async`. B có `@Transactional(propagation=REQUIRED)`. B có chắc tham gia transaction A không?

**Đáp án:** không. Với Spring imperative, transaction A gắn với thread HTTP; B trên worker thường không thấy transaction đó và có thể mở transaction riêng.

**Câu 2.** B đã commit thành công trên worker; sau đó A ném `RuntimeException`. Spring có rollback luôn commit của B không?

**Đáp án:** không. A có thể rollback giao dịch riêng, không tự hoàn tác transaction B đã commit.

**Câu 3.** Nếu A gọi `CompletableFuture.allOf(f1, f2).join()` trước khi commit, có làm hai child transaction atomic không?

**Đáp án:** không. `join()` chỉ đợi/truyền trạng thái Future, không hợp nhất ranh giới commit của nhiều database transaction.

**Câu 4.** Khi nào có thể dùng một `@Transactional` để rollback cả ghi order và ghi audit?

**Đáp án:** khi cả hai thao tác DB tham gia **cùng một transaction thật** trong mô hình/tài nguyên/manager hỗ trợ, thường cùng thread với JDBC/JPA và không mở transaction độc lập khác.

**Câu 5.** `@TransactionalEventListener(phase=AFTER_COMMIT)` giúp điều gì, và chưa giải quyết điều gì?

**Đáp án:** chỉ gọi listener ở phase sau khi parent commit thành công; chưa bảo đảm delivery bền vững, retry hoặc rollback parent nếu xử lý async sau đó thất bại.

**Câu 6.** Vì sao outbox cần consumer idempotent?

**Đáp án:** relay có thể publish thành công rồi crash trước khi xác nhận đã gửi; sau restart sẽ publish lại, dẫn đến at-least-once delivery.

**Câu 7.** Saga compensation khác rollback DB ở đâu?

**Đáp án:** compensation là một hành động nghiệp vụ mới để bù tác động, không phải đảo ngược vật lý mọi giao dịch đã commit và có thể thất bại.

**Câu 8.** Nếu A đang giữ DB connection rồi `join()` đợi B cũng cần connection, rủi ro gì?

**Đáp án:** cạn connection, lock wait, timeout hoặc deadlock tùy workload; cần tránh chờ các worker cần tài nguyên bị giữ bởi transaction parent.

**Câu 9.** Một task ở worker ném exception sau khi HTTP đã trả 202. Có thể sửa response trước đó thành 500 hoặc rollback transaction parent đã commit không?

**Đáp án:** không. Cần job status/alert/retry/compensation phù hợp; 202 phải được hiểu là accepted theo hợp đồng được thiết kế, không phải success của toàn workflow.

## 15. Ghi nhớ để thiết kế đúng

- **Thread khác không mặc định chung transaction.** Với Spring imperative, transaction context thường thread-bound.
- **@Transactional không tạo rollback toàn cục.** Cần cùng transaction manager/resource và thực tế cùng ranh giới transaction được quản lý.
- **Future/join chỉ đồng bộ kết quả, không đồng bộ commit.**
- **Nếu cùng DB và cần atomic, ghi trong một local transaction.**
- **Nếu cần xử lý sau commit nhưng chấp nhận best-effort, cân nhắc @TransactionalEventListener(AFTER_COMMIT) và quan sát lỗi.**
- **Nếu cần lưu ý định gửi event bền vững cùng domain data, dùng transactional outbox.**
- **Nếu nhiều hệ thống có side effect đã commit, cân nhắc saga với bù trừ/idempotency, không hứa rollback chung.**

## 16. Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Declarative Transaction Implementation (thread-bound transactions): https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework 6.2 — Using @Transactional và rollback settings: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 — Transaction Propagation (REQUIRED, REQUIRES_NEW, NESTED): https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html
- Spring Framework 6.2 — Transaction-bound Events (@TransactionalEventListener): https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework — Task Execution and Scheduling (@Async): https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Java SE 17 — ThreadLocal: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 17 — ExecutorService/Future: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
