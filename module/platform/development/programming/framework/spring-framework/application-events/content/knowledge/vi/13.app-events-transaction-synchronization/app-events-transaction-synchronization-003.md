# Thời điểm đăng ký synchronization trong Spring Framework Application Events

## 1. Transaction synchronization là gì và “đăng ký” diễn ra lúc nào?

**Transaction synchronization** là cơ chế để một callback tham gia vòng đời của giao dịch do Spring quản lý. Callback có thể được gọi ở những mốc như trước commit, sau commit, sau rollback hoặc sau khi transaction hoàn tất. Trong Spring Application Events, **@TransactionalEventListener** dựa trên cơ chế này để liên kết **một lần phát event** với **transaction đang hoạt động tại thời điểm event được publish**.

Điểm cốt lõi: **callback của event được đăng ký khi publishEvent(...) phân phối event trong transaction thích hợp; nó được thực thi sau đó tại pha giao dịch đã chọn**. Việc khai báo annotation không đăng ký sẵn callback cho tất cả giao dịch tương lai; việc bắt đầu transaction cũng chưa tạo callback cho một event chưa được phát.

Ví dụ: Service bắt đầu transaction, lưu đơn, gọi **publisher.publishEvent(new OrderCreated(...))**, rồi return. Listener **@TransactionalEventListener(phase = AFTER_COMMIT)** được đăng ký trong transaction khi publish; method listener chỉ chạy khi transaction commit thành công. Nếu transaction rollback, method AFTER_COMMIT không chạy.

Khi hiểu sai thời điểm đăng ký, hệ thống dễ gặp các lỗi: phát event trước khi mở transaction; phát từ thread **@Async** không mang context của transaction; phát sau commit và tưởng vẫn có callback; hoặc bật **fallbackExecution** mà không biết listener có thể chạy ngay ngoài transaction.

## 2. Phân biệt ba thời điểm thường bị gọi chung là “đăng ký”

| Thời điểm | Cơ chế Spring thực hiện | Kết quả |
| --- | --- | --- |
| Khởi tạo **ApplicationContext** | Spring tìm method **@EventListener**/**@TransactionalEventListener**, xây adapter/registry của application listener | Biết method nào nhận loại event nào; **chưa đăng ký synchronization cho event cụ thể** |
| Transaction manager tạo hoặc tham gia transaction | Kích hoạt transaction synchronization trong ngữ cảnh phù hợp và quản lý danh sách callback | Có khả năng nhận registration, nhưng **chưa có callback của event chưa phát** |
| **publishEvent(event)** trong transaction đang hoạt động | Transactional listener adapter nhận event, liên kết event với transaction hiện hành bằng synchronization | Callback của **lần publish cụ thể** được đăng ký để xử lý ở phase định trước |

Với listener **@EventListener** bình thường, method thường được gọi ngay khi multicaster dispatch event (trong cấu hình đồng bộ mặc định). Với **@TransactionalEventListener**, adapter nhận event lúc publish nhưng có thể **trì hoãn method xử lý** tới commit/rollback. Bởi vậy, hai cách ghi log “event đã phát” và “listener đã thực hiện” cần hai mốc riêng.

Trong một transaction có thể publish cùng loại event nhiều lần. Mỗi lần publish có thể tạo một callback riêng: annotation không tự gộp event trùng, không bảo đảm xử lý exactly-once, cũng không lưu event bền vững trên đĩa.

## 3. Dòng thời gian đăng ký và thực thi

Giả sử dùng **PlatformTransactionManager** với transaction gắn thread:

~~~text
T0  Vào @Transactional hoặc TransactionTemplate
    -> transaction manager khởi tạo/join transaction;
       mở cơ chế synchronization tương ứng
    |
T1  Service cập nhật dữ liệu
    |
T2  publisher.publishEvent(OrderCreated)
    -> adapter của @TransactionalEventListener nhận event
    -> kiểm tra transaction/synchronization phù hợp
    -> ĐĂNG KÝ callback của event vào transaction hiện tại
    |
T3  publishEvent(...) trả về
    -> AFTER_COMMIT listener chưa chạy
    |
T4  Transaction chuẩn bị commit
    -> chạy BEFORE_COMMIT listener đã đăng ký
    |
T5  Commit vật lý hoặc rollback
    |                            |
    | commit thành công           | rollback
    v                            v
T6  AFTER_COMMIT                AFTER_ROLLBACK
    |
T7  AFTER_COMPLETION (cả hai trường hợp)
    |
T8  Dọn dẹp transaction và trả kết quả về caller
~~~

Đây là sơ đồ thứ tự logic. Spring có nhiều bước nội bộ để dispatch callbacks; riêng **AFTER_COMMIT** của transactional event listener được kích hoạt trong quy trình hoàn tất transaction. Điểm cần nhớ: **T2 là đăng ký, còn T4/T6/T7 là thực thi**, và mỗi phase chỉ chạy nếu điều kiện kết thúc giao dịch tương ứng thỏa mãn.

Nếu service đã gọi **publishEvent(...)** trong transaction, rồi transaction rollback, callback **AFTER_COMMIT** sẽ không xử lý event đó. Nếu event được phát khi không có transaction thích hợp, listener mặc định không tự “chờ” một transaction phát sinh trong tương lai.

### Các phase của @TransactionalEventListener

| Phase | Khi nào method listener chạy? | Ứng dụng phù hợp |
| --- | --- | --- |
| **BEFORE_COMMIT** | Trong pha trước commit, khi chuẩn bị commit | Công việc cần xong trước commit, lỗi có thể ảnh hưởng commit |
| **AFTER_COMMIT** *(mặc định)* | Sau khi transaction commit thành công | Email/thông báo phụ thuộc dữ liệu đã commit |
| **AFTER_ROLLBACK** | Khi transaction rollback | Theo dõi thất bại, cleanup hoặc bù trừ có kiểm soát |
| **AFTER_COMPLETION** | Khi transaction hoàn tất, dù thành công hay thất bại | Logging, metric, release tài nguyên |

**BEFORE_COMMIT** chạy muộn hơn **publishEvent(...)**; không dùng nó cho một validation bắt buộc phải xong trước khi publisher trả về. Nếu một kiểm tra điều kiện quyết định ngay thao tác chính có tiếp tục không, dùng service call đồng bộ hoặc **@EventListener** đồng bộ có hợp đồng exception rõ ràng.

**AFTER_COMMIT** không làm transaction đã commit quay lui khi method listener thất bại. Hiệu ứng ngoại vi cần chính sách retry và idempotency riêng.

## 4. Điều kiện đăng ký trong transaction gắn thread

Spring cung cấp **org.springframework.transaction.support.TransactionSynchronizationManager**. Hai trạng thái hay được nhắc tới:

- **isSynchronizationActive()**: thread hiện tại có cơ chế transaction synchronization đang active hay không.
- **isActualTransactionActive()**: thread hiện tại đang liên kết với một transaction thực sự hay không.

Đối với adapter **@TransactionalEventListener** gắn với **PlatformTransactionManager**, Spring cần synchronization đang active **và** actual transaction đang active để đăng ký callback event vào transaction hiện tại.

Hai điều kiện này không đồng nghĩa. Với một số cấu hình propagation như **SUPPORTS** mà không có transaction vật lý, synchronization có thể active dù actual transaction không active. Vì vậy, điều kiện “có thể gọi registerSynchronization” không nhất thiết có nghĩa “sẽ có một commit vật lý để listener AFTER_COMMIT chờ”.

Có thể kiểm tra trạng thái trong code nghiệp vụ để chẩn đoán:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean sync = TransactionSynchronizationManager.isSynchronizationActive();
boolean actual = TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("sync=" + sync + ", actualTx=" + actual);
~~~

Đây là **đoạn mã đặt bên trong method Java**, không phải class độc lập. Với **TransactionTemplate** tạo transaction thật như ví dụ tiếp theo, kết quả trong callback giao dịch là **sync=true, actualTx=true**. Nếu chạy bên ngoài mọi transaction, các giá trị thường là **false/false**.

**Không tự gọi** **TransactionSynchronizationManager.initSynchronization()** hoặc **setActualTransactionActive(true)** trong service để cố làm listener chạy. Transaction manager phải chịu trách nhiệm bắt đầu, commit/rollback và cleanup transaction; tự gắn cờ không tạo giao dịch database.

## 5. Demo Java 17+ chạy độc lập: event ngoài transaction, commit, rollback

Ví dụ sử dụng **Spring Framework 6.2.9**, **H2 2.3.232**, **Java 17+** và **Gradle 8.x**. Dùng **DataSourceTransactionManager** để có transaction JDBC thật, **TransactionTemplate** để kiểm soát thời điểm bắt đầu/kết thúc và ba **@TransactionalEventListener** để quan sát phase.

Cấu trúc:

~~~text
tx-sync-timing/
  build.gradle
  src/main/java/demo/TransactionTimingDemo.java
~~~

Tạo file **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'org.springframework:spring-jdbc:6.2.9'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.TransactionTimingDemo'
}
~~~

Tạo file **src/main/java/demo/TransactionTimingDemo.java**:

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class TransactionTimingDemo {

    public record WorkCreated(String id) {}

    public static class PhaseListeners {
        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(WorkCreated event) {
            System.out.println("listener BEFORE_COMMIT: " + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(WorkCreated event) {
            System.out.println("listener AFTER_COMMIT: " + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(WorkCreated event) {
            System.out.println("listener AFTER_ROLLBACK: " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:sync_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactionTemplate(PlatformTransactionManager tm) {
            return new TransactionTemplate(tm);
        }

        @Bean
        PhaseListeners phaseListeners() {
            return new PhaseListeners();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            TransactionTemplate tx = context.getBean(TransactionTemplate.class);

            System.out.println("outside: publish");
            context.publishEvent(new WorkCreated("OUT"));
            System.out.println("outside: returned");

            tx.executeWithoutResult(status -> {
                System.out.println("commit: sync="
                        + TransactionSynchronizationManager.isSynchronizationActive()
                        + ", actualTx="
                        + TransactionSynchronizationManager.isActualTransactionActive());
                context.publishEvent(new WorkCreated("OK"));
                System.out.println("commit: publish returned");
            });
            System.out.println("commit: transaction returned");

            tx.executeWithoutResult(status -> {
                System.out.println("rollback: publish");
                context.publishEvent(new WorkCreated("FAIL"));
                System.out.println("rollback: publish returned");
                status.setRollbackOnly();
            });
            System.out.println("rollback: transaction returned");
        }
    }
}
~~~

Chạy từ thư mục **tx-sync-timing** sau khi cài JDK 17+ và Gradle 8.x:

~~~bash
gradle --console=plain -q run
~~~

**Stdout do chương trình in ra**:

~~~text
outside: publish
outside: returned
commit: sync=true, actualTx=true
commit: publish returned
listener BEFORE_COMMIT: OK
listener AFTER_COMMIT: OK
commit: transaction returned
rollback: publish
rollback: publish returned
listener AFTER_ROLLBACK: FAIL
rollback: transaction returned
~~~

Giải thích:

1. **OUT** được publish khi chưa có transaction; ba listener có **fallbackExecution=false** mặc định nên không có dòng listener nào mang mã **OUT**.
2. Khi **TransactionTemplate** mở transaction cho **OK**, synchronization và actual transaction đều active. Spring đăng ký callback ngay khi gọi **publishEvent(...)**, nhưng dòng **commit: publish returned** vẫn xuất hiện **trước** callback.
3. Khi lambda của **TransactionTemplate** kết thúc bình thường, Spring chạy **BEFORE_COMMIT**, commit và chạy **AFTER_COMMIT**. Sau đó lời gọi **TransactionTemplate** mới trả về và in **commit: transaction returned**.
4. Với **FAIL**, lệnh **status.setRollbackOnly()** dẫn tới rollback. **AFTER_ROLLBACK** xử lý event đó; **BEFORE_COMMIT** và **AFTER_COMMIT** không được gọi cho **FAIL**.
5. Ví dụ không tạo SQL record, không gửi email và không chứng minh message delivery bền vững; H2 chỉ cung cấp transaction manager thật để quan sát lifecycle. Nếu cần kiểm tra data commit/rollback, bổ sung JDBC operations và assertion trong integration test.

Kết quả giúp tách rõ **tại lúc publish đã đăng ký** khỏi **sau khi commit/rollback mới thực thi**.

## 6. Đặt lệnh publish ở đâu?

### 6.1. Publish trước transaction

~~~java
publisher.publishEvent(new WorkCreated("EARLY"));
tx.executeWithoutResult(status -> {
    // Transaction mới bắt đầu bên trong callback này.
});
~~~

Event **EARLY** không tự được chuyển vào transaction mở sau đó. Với **@TransactionalEventListener** mặc định, callback không được đăng ký và event bị bỏ qua đối với listener dạng transactional.

**Cách sửa:** publish trong transaction cần ràng buộc, sau khi transaction thực sự được mở.

### 6.2. Publish trong transaction

~~~java
tx.executeWithoutResult(status -> {
    // Transaction đang active.
    publisher.publishEvent(new WorkCreated("IN_TX"));
    // Callback đã đăng ký; AFTER_COMMIT chưa chạy.
});
~~~

Đây là vị trí phổ biến. Callback ràng buộc với **transaction mà publication context đang nhìn thấy**, không phải transaction được đoán từ tên method hoặc loại event.

Nếu service gọi **@Transactional** qua proxy, transaction thường được tạo trước khi vào thân method. Nhưng trong cơ chế proxy mặc định, **self-invocation** (một method của cùng bean gọi method khác trên chính instance) thường không kích hoạt interceptor **@Transactional**. Khi đó lệnh publish tưởng như “nằm trong method @Transactional” nhưng thực chất không có transaction đang hoạt động.

### 6.3. Publish sau transaction

~~~java
tx.executeWithoutResult(status -> {
    // Transaction kết thúc khi callback này return.
});
publisher.publishEvent(new WorkCreated("LATE"));
~~~

Đối với **LATE**, transaction cũ đã kết thúc; Spring không thể quay lại pha AFTER_COMMIT đã qua. Nếu muốn xử lý sự kiện này ngay mà không phụ thuộc transaction, **@EventListener** thông thường có thể phù hợp. Nếu cần AFTER_COMMIT của một transaction, phải publish **trong transaction đó**, hoặc tạo transaction mới đúng phạm vi.

### 6.4. fallbackExecution thay đổi đường thực thi

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void on(WorkCreated event) {
    // Được xử lý cả khi không có transaction phù hợp.
}
~~~

Đây là **đoạn minh họa phương thức**, cần đặt trong Spring bean và thêm import để dùng thật. Nếu không có transaction phù hợp và **fallbackExecution=true**, Spring có thể gọi listener ngay ở nhánh fallback; không có commit nào được chờ. Vì vậy không được bật fallback rồi tiếp tục tuyên bố rằng mọi lần xử lý đều “sau commit”.

## 7. Đăng ký thủ công bằng TransactionSynchronizationManager

Ngoài **@TransactionalEventListener**, code hạ tầng có thể đăng ký callback trực tiếp:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public void registerWorkAfterCommit(Runnable work) {
    if (!TransactionSynchronizationManager.isSynchronizationActive()
            || !TransactionSynchronizationManager.isActualTransactionActive()) {
        throw new IllegalStateException("Active transaction required");
    }

    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    work.run();
                }
            });
}
~~~

**registerSynchronization(...)** chỉ thực hiện đăng ký, không chạy **work.run()** ngay tại thời điểm gọi. Callback **afterCommit()** được transaction manager gọi khi transaction commit thành công. API này ném **IllegalStateException** nếu synchronization không active; ví dụ kiểm tra thêm actual transaction vì hợp đồng của method yêu cầu transaction thật.

Đặt code trong một class được gọi khi transaction đã mở; riêng đoạn trên chỉ minh họa method, không phải chương trình độc lập. Nếu transaction manager cần cleanup hay rollback, nó vẫn giữ quyền điều phối lifecycle; ứng dụng không được tự mở/đóng synchronization bằng cờ ThreadLocal.

Một **TransactionSynchronization** có các callback như **beforeCommit**, **beforeCompletion**, **afterCommit**, **afterCompletion**. Không nên đăng ký callback quá muộn, khi pha cần chạy đã qua. Đăng ký trong callback sau completion không làm transaction thực thi lại pha đó.

## 8. Các trường hợp thay đổi ngữ cảnh đăng ký

### 8.1. @Async và thread khác

Với transaction do **PlatformTransactionManager** quản lý, context thông thường được giữ trong **ThreadLocal**. Nếu method phát sự kiện chạy trên thread executor:

~~~java
@Async("executor")
public void publishLater(WorkCreated event) {
    publisher.publishEvent(event);
}
~~~

thread mới thường không có transaction của caller. **@TransactionalEventListener** mặc định không đăng ký vào transaction ở thread gốc. Không được coi việc truyền object event là đã truyền transaction context.

**Phân biệt:** đặt **@Async** lên method *publish* ảnh hưởng **mốc đăng ký**; đặt **@Async** lên method listener transactional có thể giữ việc đăng ký ở thread publish, rồi chỉ đưa xử lý nghiệp vụ sau phase sang executor. Việc chạy async sau commit vẫn không kế thừa transaction cũ; nếu cần ghi DB, hãy tạo transaction mới phù hợp.

### 8.2. REQUIRES_NEW

Nếu transaction ngoài đang chạy, service mở transaction **REQUIRES_NEW** và publish event trong transaction mới, callback gắn với **transaction mới**. Listener **AFTER_COMMIT** của event có thể chạy ngay khi transaction mới commit, **trước** khi outer transaction kết thúc. Đừng giả định nó luôn chờ outer transaction.

Ví dụ logic:

~~~text
outer transaction bắt đầu
  -> inner REQUIRES_NEW bắt đầu
       -> publishEvent(E)
       -> inner commit
       -> E.AFTER_COMMIT được gọi
  -> outer transaction tiếp tục, có thể rollback về sau
~~~

Nếu nghiệp vụ yêu cầu chỉ thông báo khi **toàn bộ** thay đổi ngoài đã commit, phát event ở transaction scope phù hợp.

### 8.3. NESTED/savepoint

**NESTED** có thể dùng savepoint trong transaction ngoài. Rollback về savepoint không nhất thiết kết thúc transaction ngoài. Không nên giả định **AFTER_ROLLBACK** của transactional event listener sẽ chạy cho từng savepoint rollback; callback thường gắn với lifecycle của transaction chính. Nếu cần xử lý savepoint một cách chính xác, cần chọn API hỗ trợ và kiểm thử riêng theo transaction manager.

### 8.4. Reactive transaction

Từ Spring Framework 6.1, **@TransactionalEventListener** hỗ trợ transaction thread-bound từ **PlatformTransactionManager** và transaction reactive từ **ReactiveTransactionManager**. Reactive transaction dùng **Reactor Context**, không dựa vào ThreadLocal giống ví dụ JDBC.

Với reactive publication, transaction context cần được đưa vào **source của event** theo cơ chế được Spring hỗ trợ; **TransactionalEventPublisher** giúp phát event theo transaction context reactive. Không dùng các phép kiểm tra ThreadLocal của ví dụ imperative để kết luận có/không có reactive transaction.

## 9. Điều xảy ra sau khi đã đăng ký

### 9.1. Callback AFTER_COMMIT không làm rollback commit trước đó

Khi listener **AFTER_COMMIT** được gọi, transaction chính đã commit. Nếu email gửi lỗi, transaction đã commit không tự quay lui. Nếu listener cần ghi bản ghi DB mới, nên gọi một service Spring-managed với **@Transactional(propagation = Propagation.REQUIRES_NEW)** để có một lần commit mới; không dựa vào tài nguyên transaction cũ có thể còn tạm gắn thread sau commit.

### 9.2. Đăng ký trong bộ nhớ không bảo đảm eventual delivery

Việc đăng ký callback không có nghĩa event được ghi bền vững. JVM có thể chết sau commit nhưng trước khi xử lý xong callback async. Nếu bắt buộc không mất thông báo, dùng **transactional outbox**: ghi một outbox record trong cùng DB transaction với nghiệp vụ, rồi có worker/queue lấy record, retry với backoff, xử lý idempotent và ghi trạng thái hoàn tất.

### 9.3. ErrorHandler/transaction manager ảnh hưởng lỗi

Đừng giả định mọi exception ở mọi phase có khả năng rollback như nhau. Lỗi **BEFORE_COMMIT** có thể làm commit thất bại nếu được lan truyền đúng cơ chế; lỗi **AFTER_COMMIT** xuất hiện sau commit, không thể đảo ngược kết quả đã commit. Tùy cơ chế callback, lỗi có thể được ghi log trong giai đoạn completion. Cần log, metric, tracing và chính sách retry riêng cho xử lý hậu giao dịch.

## 10. Checklist kiểm thử thời điểm đăng ký

1. **Ngoài transaction:** Publish với **fallbackExecution=false** và xác nhận transactional listener không được gọi.
2. **Trong transaction trước commit:** Publish rồi xác nhận method AFTER_COMMIT chưa chạy ngay trong **publishEvent(...)**; method chạy sau commit.
3. **Rollback:** Publish trong transaction rồi rollback; AFTER_COMMIT không chạy, AFTER_ROLLBACK chạy.
4. **BEFORE_COMMIT:** Xác nhận callback xảy ra trong pha trước commit; lỗi bắt buộc có thể được quan sát ở ranh giới commit.
5. **Thread khác:** Phát bằng **@Async**, quan sát transaction context tại thread đó, xác nhận policy mong muốn.
6. **REQUIRES_NEW:** Phát event trong transaction mới và kiểm tra callback gắn với transaction mới.
7. **SUPPORTS không transaction thật:** Đừng suy luận kết quả chỉ từ **isSynchronizationActive()**.
8. **fallbackExecution=true:** Xác nhận nhánh xử lý ngoài transaction và thời điểm thực thi khác với nhánh transaction.
9. **Tình huống lỗi hạ tầng:** Thử executor từ chối task hoặc listener ném exception; theo dõi thông báo lỗi và policy retry.
10. **Transaction proxy:** Kiểm tra service thật sự được gọi qua Spring proxy hoặc **TransactionTemplate**, tránh self-invocation làm **@Transactional** không hiệu lực.

Kiểm thử nên đi qua **ApplicationContext + publisher + transaction manager**. Gọi trực tiếp **listener.on(event)** chỉ kiểm tra method body và **không chứng minh** Spring đã đăng ký synchronization hoặc dispatch đúng phase.

## 11. Các lỗi tư duy và cách sửa

| Ngộ nhận | Hệ quả | Điều cần làm |
| --- | --- | --- |
| “Có annotation tức đã đăng ký cho mọi transaction” | Không phân biệt listener registry với transaction callback | Nhớ registration cho event được quyết định **tại publish** |
| “Event phát trước transaction sẽ được đợi tới commit” | Listener transactional mặc định bỏ qua event | Publish bên trong transaction đã mở |
| “publishEvent trả về nghĩa là AFTER_COMMIT đã chạy” | Side effect được quan sát quá sớm | Đợi đúng commit phase hoặc thiết kế output khác |
| “Thread @Async vẫn có transaction của request” | Callback không được gắn đúng transaction | Giữ publish trong thread/context của transaction |
| “isSynchronizationActive là đủ” | Có thể nhầm SUPPORTS không có transaction vật lý | Kiểm tra thêm actual transaction khi cần |
| “fallbackExecution vẫn chỉ chạy sau commit” | Method có thể chạy ngay ngoài transaction | Chỉ bật fallback khi nghiệp vụ chấp nhận |
| “AFTER_COMMIT lỗi có thể rollback transaction” | Commit đã xảy ra | Xử lý hậu commit bằng retry/compensation thích hợp |
| “REQUIRES_NEW chờ transaction ngoài” | Callback có thể chạy trước outer commit | Liên kết event với transaction scope đúng |
| “Đã đăng ký callback nghĩa là không mất event” | JVM/queue lỗi có thể làm mất việc | Dùng outbox/queue bền vững và idempotency |

**Quy tắc ghi nhớ:** Transaction manager thiết lập môi trường synchronization; sự kiện được publish trong môi trường đó thì callback của **@TransactionalEventListener** mới được đăng ký cho transaction tương ứng; **TransactionPhase** mới quyết định khi nào listener thực sự chạy. Ba mốc này cần được thiết kế và kiểm thử độc lập.

### Tài liệu chính thức

- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2.9 Javadoc, *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework 6.2.9 Javadoc, *TransactionSynchronizationManager*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework 6.2.9 Javadoc, *TransactionSynchronization*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework 6.2.9 Javadoc, *TransactionalApplicationListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html
