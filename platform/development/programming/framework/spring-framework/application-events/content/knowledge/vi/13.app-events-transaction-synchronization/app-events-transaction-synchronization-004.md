# Event được phát trước hay sau thay đổi dữ liệu?

Trong Spring Framework Application Events, **vị trí gọi `publishEvent()`**, **thời điểm thực hiện thay đổi dữ liệu** và **thời điểm transaction commit** là ba mốc khác nhau. Nhầm chúng với nhau dễ tạo lỗi “đã gửi thông báo nhưng dữ liệu vẫn rollback”, hoặc “listener đọc thấy giá trị cũ dù service vừa gọi `save()`”.

Bài này xét việc phát application event trong một tiến trình Spring, đặc biệt khi cập nhật dữ liệu nằm trong transaction. Mục tiêu là chọn đúng thời điểm xử lý, hiểu cơ chế `@EventListener` và `@TransactionalEventListener`, rồi kiểm thử bằng kết quả quan sát được.

## 1. Ba mốc thời gian cần tách biệt

Giả sử service thay đổi trạng thái đơn hàng từ `NEW` sang `PAID`:

1. **Thay đổi trong bộ nhớ hoặc ghi SQL:** `order.setStatus(PAID)`, `repository.save(order)`, `jdbc.update(...)`. Với ORM, `save()` có thể chỉ cập nhật persistence context; SQL thật có thể được flush sau.
2. **Phát sự kiện:** `publisher.publishEvent(new OrderPaid(id))`. Đây là thời điểm gửi thông báo đến cơ chế multicaster; Spring không tự liên kết lời gọi này với việc lưu dữ liệu trước/sau.
3. **Kết thúc transaction:** commit làm thay đổi hợp lệ được chốt; rollback hủy những thay đổi thuộc transaction.

Hai cách viết dưới đây có ý nghĩa khác nhau:

~~~java
// Minh họa bên trong một method nghiệp vụ có transaction:
publisher.publishEvent(new OrderPaid(orderId));
repository.markPaid(orderId); // Event được phát TRƯỚC thay đổi.

// So với:
repository.markPaid(orderId);
publisher.publishEvent(new OrderPaid(orderId)); // Event phát SAU thay đổi,
// nhưng vẫn có thể TRƯỚC commit transaction.
~~~

Đây là các trích đoạn, không phải lớp Java độc lập. Ở ví dụ thứ hai, **“sau khi gọi thao tác ghi” không đồng nghĩa “sau commit”**. Nếu transaction rollback ở bước sau, event đã được publish vẫn từng xảy ra.

### Nhìn theo dòng thời gian

| Mốc | Dữ liệu trong transaction | Listener `@EventListener` đồng bộ | Listener `@TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- | --- |
| `publishEvent()` trước lệnh ghi | Chưa có thay đổi của bước ghi đó | Chạy ngay, có thể thấy trạng thái cũ | Chưa chạy; đăng ký xử lý sau commit |
| Lệnh ghi xong rồi `publishEvent()`, transaction còn mở | Thay đổi có thể đã ghi SQL hoặc còn trong ORM context | Chạy ngay; nếu đọc qua cùng transaction có thể thấy thay đổi | Chưa chạy |
| Transaction commit thành công | Dữ liệu được chốt theo quy tắc database | Không tự được gọi lần nữa bởi event cũ | Được gọi ở pha `AFTER_COMMIT` |
| Transaction rollback | Thay đổi thuộc transaction bị hủy | Listener đồng bộ đã chạy **không bị “hoàn tác” tự động** | Không chạy; pha `AFTER_ROLLBACK` có thể chạy |

Một listener chạy trong cùng transaction có thể đọc dữ liệu chưa commit của chính transaction đó. Ngược lại, một listener chạy ở thread khác hoặc dùng transaction/connection khác thường không nhìn thấy dữ liệu chưa commit, tùy isolation level và công nghệ truy cập dữ liệu. Vì vậy cần xác định **listener chạy ở đâu, lúc nào, qua transaction nào**.

## 2. `@EventListener` chạy lúc nào?

Với `ApplicationEventMulticaster` mặc định của Spring (không cấu hình executor bất đồng bộ), listener `@EventListener` được gọi **đồng bộ trên thread phát event**. Do đó:

~~~java
@Transactional
public void pay(String orderId) {
    orderRepository.markPaid(orderId);           // Thay đổi dữ liệu.
    publisher.publishEvent(new OrderPaid(orderId)); // Listener thường chạy ở đây.
    validateFinalState(orderId);                  // Có thể ném exception.
} // Nếu transaction còn hợp lệ, commit diễn ra khi interceptor kết thúc method.
~~~

Đây là **trích đoạn một method**: `OrderPaid`, repository, publisher và `validateFinalState` phải được định nghĩa trong ứng dụng; `@Transactional` chỉ hoạt động khi lời gọi đi qua cơ chế quản lý transaction của Spring, chẳng hạn qua proxy. Nếu `validateFinalState()` ném lỗi gây rollback theo quy tắc transaction, listener thường đã có thể gửi email hoặc gọi API bên ngoài trước đó. Những hiệu ứng ngoài database **không được rollback cùng JDBC/JPA transaction**.

Tương tự, nếu listener đồng bộ ghi thêm dữ liệu qua cùng transaction, thay đổi của listener có thể commit hoặc rollback cùng transaction gốc. Nhưng gửi HTTP/email ngay từ listener là một hiệu ứng bên ngoài không có chung tính nguyên tử.

Nếu cấu hình `@Async` hoặc gắn executor cho multicaster, listener có thể chạy trên thread khác; vị trí `publishEvent()` không còn bảo đảm listener hoàn thành trước dòng code tiếp theo. Transaction gắn với thread thông thường cũng không tự truyền sang thread bất đồng bộ.

## 3. `@TransactionalEventListener` gắn event với pha transaction

`@TransactionalEventListener` cho phép listener đăng ký xử lý event theo kết cục transaction. Khi phát event trong thread có transaction phù hợp, Spring giữ sự kiện để thực thi tại pha cấu hình:

| Pha | Thời điểm và ý nghĩa | Phù hợp khi |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước bước commit thực tế; commit vẫn có thể thất bại | Cần kiểm tra/chuẩn bị dữ liệu trong cùng transaction; không được xem là đã chốt |
| `AFTER_COMMIT` (**mặc định**) | Sau commit thành công | Phát tín hiệu/notification chỉ khi dữ liệu đã commit |
| `AFTER_ROLLBACK` | Sau rollback | Ghi nhận/cảnh báo việc transaction thất bại |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, dù commit hay rollback | Dọn dẹp theo kết quả cuối; muốn biết kết cục cụ thể thì dùng pha thích hợp |

Ví dụ nhận event sau commit:

~~~java
@Component
class ReceiptListener {
    private final ReceiptGateway gateway;

    ReceiptListener(ReceiptGateway gateway) {
        this.gateway = gateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPaid(OrderPaid event) {
        gateway.sendReceipt(event.orderId());
    }
}
~~~

Đây là **trích đoạn listener trong ứng dụng**, cần định nghĩa `ReceiptGateway`, `OrderPaid` và import `org.springframework.stereotype.Component`, `org.springframework.transaction.event.TransactionalEventListener`, `org.springframework.transaction.event.TransactionPhase`. Nó mô tả mong muốn không gửi receipt nếu transaction rollback, nhưng **không tự cung cấp retry, idempotency hoặc giao nhận chắc chắn** nếu tiến trình chết sau commit hoặc gateway lỗi.

Mặc định, khi `publishEvent()` xảy ra **ngoài transaction hoạt động**, listener `@TransactionalEventListener` **không được gọi**. `fallbackExecution = true` cho phép chạy khi không có transaction; nếu nghiệp vụ bắt buộc chỉ xử lý khi commit, tránh bật tùy tiện vì lúc đó không còn ràng buộc “sau commit”.

### Chú ý về truy cập database trong `AFTER_COMMIT`

Tại các pha sau khi transaction kết thúc, tài nguyên transaction có thể còn được gắn với thread. Một thao tác ghi DB bên trong listener `AFTER_COMMIT` có thể vẫn “tham gia” tài nguyên của transaction cũ nhưng **không có commit tiếp theo** cho phần ghi đó. Nếu cần lưu thêm bản ghi riêng sau commit, hãy khởi tạo một transaction mới tường minh, ví dụ thông qua service khác có `@Transactional(propagation = Propagation.REQUIRES_NEW)` (được gọi qua proxy Spring), hoặc một `TransactionTemplate` được cấu hình `PROPAGATION_REQUIRES_NEW`. Không dựa vào transaction cũ để bảo đảm bản ghi mới được commit.

## 4. Ví dụ kiểm thử: trước ghi, sau ghi nhưng trước commit, commit và rollback

Ví dụ sau là một bài test Java 17+ hoàn chỉnh sử dụng **Spring Context + Spring JDBC + Spring Test + H2 + JUnit 5**. Để làm rõ thời điểm, code dùng `TransactionTemplate` và `JdbcTemplate`, tránh khác biệt flush của ORM. Không dùng `@Transactional` trên chính method test, nhờ vậy có thể khẳng định giá trị ngay **sau khi** `TransactionTemplate` trả về.

### 4.1. Tạo Gradle project tối thiểu

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-jdbc:6.1.14'
    implementation 'org.springframework:spring-tx:6.1.14'
    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'com.h2database:h2:2.2.224'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các phiên bản trên là một bộ ví dụ tương thích Java 17; trong dự án Spring Boot đang sử dụng BOM, nên dùng phiên bản Spring do BOM quản lý để tránh xung đột. Nếu dùng Gradle wrapper trong dự án, không cần cài Gradle toàn cục.

### 4.2. File `src/test/java/example/events/OrderEventTimingTest.java`

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(OrderEventTimingTest.Config.class)
class OrderEventTimingTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired JdbcTemplate jdbc;
    @Autowired TransactionTemplate tx;
    @Autowired Timeline timeline;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM purchase_order");
        timeline.clear();
    }

    @Test
    void publishBeforeInsert_observesOldStateUntilCommit() {
        tx.executeWithoutResult(status -> {
            publisher.publishEvent(new OrderChanged("A"));
            assertEquals(
                List.of("immediate:A:0"),
                timeline.snapshot()
            );

            jdbc.update(
                "INSERT INTO purchase_order(id) VALUES (?)", "A"
            );
            // Listener AFTER_COMMIT chưa chạy dù INSERT đã xong.
            assertEquals(
                List.of("immediate:A:0"),
                timeline.snapshot()
            );
        });

        assertEquals(
            List.of("immediate:A:0", "afterCommit:A"),
            timeline.snapshot()
        );
        assertEquals(1, rowCount("A"));
    }

    @Test
    void publishAfterInsert_seesOwnUncommittedWrite() {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "INSERT INTO purchase_order(id) VALUES (?)", "B"
            );
            publisher.publishEvent(new OrderChanged("B"));

            // Cùng thread và cùng JDBC transaction: nhìn thấy INSERT.
            assertEquals(
                List.of("immediate:B:1"),
                timeline.snapshot()
            );
        });

        assertEquals(
            List.of("immediate:B:1", "afterCommit:B"),
            timeline.snapshot()
        );
        assertEquals(1, rowCount("B"));
    }

    @Test
    void rollbackDoesNotTriggerAfterCommit() {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "INSERT INTO purchase_order(id) VALUES (?)", "C"
            );
            publisher.publishEvent(new OrderChanged("C"));
            status.setRollbackOnly();
        });

        assertEquals(
            List.of("immediate:C:1", "afterRollback:C"),
            timeline.snapshot()
        );
        assertEquals(0, rowCount("C"));
    }

    @Test
    void withoutTransactionTransactionalListenersDoNotRun() {
        publisher.publishEvent(new OrderChanged("D"));

        assertEquals(
            List.of("immediate:D:0"),
            timeline.snapshot()
        );
    }

    private int rowCount(String id) {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM purchase_order WHERE id = ?",
            Integer.class, id
        );
        return count.intValue();
    }

    record OrderChanged(String id) { }

    static class Timeline {
        private final List<String> entries = new ArrayList<>();

        void record(String entry) {
            entries.add(entry);
        }

        List<String> snapshot() {
            return List.copyOf(entries);
        }

        void clear() {
            entries.clear();
        }
    }

    static class TimingListeners {
        private final JdbcTemplate jdbc;
        private final Timeline timeline;

        TimingListeners(JdbcTemplate jdbc, Timeline timeline) {
            this.jdbc = jdbc;
            this.timeline = timeline;
        }

        @EventListener
        public void immediate(OrderChanged event) {
            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_order WHERE id = ?",
                Integer.class, event.id()
            );
            timeline.record("immediate:" + event.id() + ":" + count);
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void afterCommit(OrderChanged event) {
            timeline.record("afterCommit:" + event.id());
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void afterRollback(OrderChanged event) {
            timeline.record("afterRollback:" + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:event_timing;DB_CLOSE_DELAY=-1",
                "sa",
                ""
            );
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            JdbcTemplate jdbc = new JdbcTemplate(dataSource);
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS purchase_order (" +
                "id VARCHAR(50) PRIMARY KEY)"
            );
            return jdbc;
        }

        @Bean
        DataSourceTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        Timeline timeline() {
            return new Timeline();
        }

        @Bean
        TimingListeners timingListeners(
                JdbcTemplate jdbc, Timeline timeline) {
            return new TimingListeners(jdbc, timeline);
        }
    }
}
~~~

Chạy test từ thư mục project có Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.OrderEventTimingTest"
~~~

Windows PowerShell dùng `./gradlew.bat test --tests "example.events.OrderEventTimingTest"`. Các test **không in dữ liệu nghiệp vụ ra stdout**; kết quả quan sát được là các assertion trên `timeline` và database. Nếu test pass, có thể diễn giải kết quả:

- `A`: publish **trước INSERT** → listener đồng bộ đếm `0`; sau commit mới có `afterCommit:A`; database cuối có 1 bản ghi.
- `B`: INSERT xong rồi publish **trước commit** → listener đồng bộ dùng cùng JDBC transaction đếm `1`; `afterCommit:B` vẫn đợi commit.
- `C`: INSERT và publish rồi **rollback** → listener thường từng chạy (`immediate:C:1`); `afterRollback:C` chạy; **không có `afterCommit:C`**, database không còn bản ghi.
- `D`: publish **ngoài transaction** → listener thường vẫn nhận event, còn hai transactional listener không chạy theo mặc định.

**Vì sao đây là integration test phù hợp?** Event đi qua `ApplicationEventPublisher` trong Spring context thực; `DataSourceTransactionManager` và `JdbcTemplate` dùng cùng `DataSource`, nên việc đọc trong listener đồng bộ đi cùng JDBC transaction đã mở. `TransactionTemplate` chủ động commit/rollback để assertion sau đó quan sát được callback giao dịch. `Timeline` là danh sách đơn giản dùng được vì cấu hình ví dụ chạy đồng bộ; nếu bật async/concurrent execution cần cơ chế đồng bộ và vùng dữ liệu an toàn luồng riêng.

## 5. Nếu dùng JPA/Hibernate, `save()` và `flush()` có ý nghĩa gì?

Trong JPA, thao tác `repository.save(entity)` không luôn khiến SQL `INSERT`/`UPDATE` được thực thi ngay. Persistence context có thể giữ entity đã đổi trạng thái và chỉ flush khi cần hoặc gần commit.

Xét chuỗi:

~~~java
@Transactional
public void updateStatus(String id) {
    Order order = orderRepository.findById(id).orElseThrow();
    order.setStatus(OrderStatus.PAID);
    orderRepository.save(order);
    publisher.publishEvent(new OrderPaid(id));
}
~~~

Đây là đoạn service minh họa, không phải file độc lập. Lúc `publishEvent()`:

- Một `@EventListener` đồng bộ truy cập **cùng managed entity** có thể thấy trạng thái `PAID`, dù SQL chưa flush hoặc transaction chưa commit.
- Truy vấn JPA có thể kích hoạt flush tùy flush mode và loại truy vấn; không nên suy từ “listener query được giá trị mới” rằng transaction đã được commit.
- Một listener đọc bằng **connection/transaction độc lập** thường chỉ thấy dữ liệu đã commit theo isolation level phù hợp.
- `saveAndFlush()` hoặc `entityManager.flush()` có thể đẩy SQL xuống database và làm lộ các lỗi constraint sớm hơn, nhưng **flush không phải commit**. Transaction vẫn có thể rollback.

Vì thế nên thiết kế event theo **sự kiện nghiệp vụ đã xảy ra trong transaction** (ví dụ quyết định chuyển trạng thái), còn listener nào bắt buộc đợi dữ liệu được chốt thì dùng `AFTER_COMMIT` hoặc cơ chế giao nhận sau commit. Đừng dùng việc đổi chỗ `save()` và `publishEvent()` để thay thế một hợp đồng commit rõ ràng.

## 6. Chọn thiết kế theo yêu cầu tính nhất quán

**Trường hợp A — listener chỉ cập nhật dữ liệu cần nằm trong cùng transaction.** Nếu dùng listener đồng bộ và cùng transaction/thread, tác dụng phụ lên DB có thể cùng commit/rollback với nghiệp vụ chính. Tuy nhiên, nếu đó là một bước bắt buộc để hoàn tất nghiệp vụ, gọi service trực tiếp có thể dễ hiểu và dễ kiểm thử hơn một listener ngầm.

**Trường hợp B — gửi email hoặc thông báo chỉ sau commit thành công.** Dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` để tránh gửi khi rollback. Phải chấp nhận rằng lỗi gateway sau commit không làm dữ liệu đã commit tự rollback; cần xử lý lỗi, retry và idempotency theo mức độ quan trọng.

**Trường hợp C — không được mất thông báo, ngay cả khi tiến trình dừng ngay sau commit.** `AFTER_COMMIT` riêng lẻ chưa bảo đảm tính bền vững. Mẫu **transactional outbox** lưu trạng thái nghiệp vụ và bản ghi outbox trong *cùng một database transaction*. Một worker/broker publisher độc lập đọc bản ghi đã commit, gửi với retry, đánh dấu đã gửi và xử lý trùng lặp bằng idempotency.

~~~text
BEGIN TRANSACTION
  UPDATE purchase_order SET status = 'PAID' WHERE id = ...
  INSERT INTO outbox(event_id, type, payload, status)
    VALUES (..., 'OrderPaid', ..., 'PENDING')
COMMIT

Worker đọc outbox đã commit -> publish -> ghi nhận kết quả/retry
Consumer xử lý event_id theo hướng idempotent
~~~

Đây là **pseudocode**, không phải SQL chạy độc lập. Outbox bảo vệ khoảng trống giữa “DB đã commit” và “chưa kịp gửi event”, nhưng vẫn cần thiết kế retry và chống xử lý trùng; không tự biến hệ thống thành exactly-once end-to-end.

**Trường hợp D — nhiều consumer/threads.** `@Async`, executor, reactive pipelines hoặc message brokers có ranh giới transaction khác nhau. Với reactive transaction từ Spring 6.1, ngữ cảnh giao dịch nằm trong Reactor Context; khi dùng transactional events phải tuân theo cách chuyển transaction context của `TransactionalEventPublisher`. Không áp dụng máy móc giả định thread-bound của ví dụ JDBC cho pipeline reactive.

## 7. Kiểm thử thời điểm chính xác và các sai lầm phổ biến

| Lỗi thường gặp | Vì sao sai | Cách kiểm chứng đúng |
| --- | --- | --- |
| “Đã gọi `save()` rồi nên event chắc chắn sau commit” | `save()` ở trong transaction chưa kết thúc | Test commit/rollback thật và quan sát effect sau transaction |
| “Listener đã đọc thấy dữ liệu mới nên dữ liệu đã commit” | Có thể đọc trạng thái trong cùng persistence context/transaction | Kiểm tra từ kết nối/transaction độc lập sau commit nếu cần chứng minh visibility |
| “Dùng `@Order` để chạy listener sau commit” | `@Order` chỉ điều khiển ưu tiên listener, không phải pha transaction | Dùng `@TransactionalEventListener(AFTER_COMMIT)` |
| “Gửi HTTP trong `@EventListener` sẽ rollback được” | HTTP/email nằm ngoài DB transaction | Dời side effect sang after-commit hoặc outbox |
| “Test `@Transactional` mặc định đã kiểm chứng AFTER_COMMIT” | Spring TestContext mặc định rollback transaction ở cuối test | Test chủ động commit bằng `TransactionTemplate` hoặc `TestTransaction` |
| “`AFTER_COMMIT` ghi DB qua repository là chắc chắn được lưu” | Tài nguyên cũ có thể còn gắn thread nhưng không có commit mới | Mở transaction mới, ví dụ `REQUIRES_NEW`, và kiểm tra DB readback |
| “Không có transaction thì listener mặc định sẽ chạy như thường” | Transactional listener bỏ qua event khi không có transaction | Kiểm tra nhánh ngoài transaction; chỉ bật `fallbackExecution` khi có chủ đích |
| “Bật async vẫn nhìn thấy transaction gốc” | Thread-bound context không tự truyền qua executor | Thiết kế lại ranh giới dữ liệu, chờ kết quả và test riêng |

Các phép thử tối thiểu nên bao gồm **publish trước thay đổi**, **publish sau thay đổi nhưng trước commit**, **commit thành công**, **rollback**, và **publish ngoài transaction** nếu ứng dụng có nhánh đó. Khi có JPA, bổ sung test flush/constraint; khi có outbox, bổ sung tình huống worker retry và xử lý event trùng.

Trong Spring TestContext, một test được đánh dấu `@Transactional` thường **rollback tự động sau khi test kết thúc**, nên assert `AFTER_COMMIT` ngay giữa method có thể thất bại vì callback chưa có cơ hội chạy. Muốn quan sát thời điểm sau commit, có thể dùng `TransactionTemplate` trong một test không bọc transaction như ví dụ ở trên, hoặc dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` khi test có transaction do Spring TestContext quản lý.

## 8. Câu hỏi tự kiểm tra

1. Nếu gọi `publisher.publishEvent()` trước `jdbc.update()` trong cùng transaction, listener đồng bộ sẽ nhìn thấy bản ghi mới chưa? Trong ví dụ này là **chưa**, vì lệnh ghi chưa chạy.
2. Nếu `jdbc.update()` đã hoàn thành rồi mới publish, listener đồng bộ dùng cùng transaction có thấy bản ghi chưa commit không? **Có**, trong ví dụ JDBC này.
3. Nếu phát event sau `save()` nhưng sau đó rollback, `@EventListener` đồng bộ có bị Spring thu hồi các tác dụng phụ ngoài DB không? **Không**.
4. Khi nào `@TransactionalEventListener` mặc định chạy? **Sau commit thành công** của transaction phù hợp đã phát event.
5. Khi nào cần outbox? Khi phải bảo đảm event không bị mất trong khoảng từ commit dữ liệu đến giao nhận bên ngoài và cần cơ chế retry/idempotency bền vững.

**Điểm cần nhớ:** “phát sau thay đổi dữ liệu” chỉ mô tả **thứ tự câu lệnh trong service**; “xử lý sau commit” mới nói đến **kết cục transaction**. Hãy chọn listener và phép thử theo hợp đồng nghiệp vụ cần bảo vệ, nhất là khi có email, broker hoặc thao tác DB bổ sung.

## Tài liệu tham khảo

- [Spring Framework – Application Events, `@EventListener` và mặc định dispatch đồng bộ](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – Transaction-bound Events và `@TransactionalEventListener`](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – TransactionSynchronization (lưu ý transaction resource sau commit)](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework – TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
