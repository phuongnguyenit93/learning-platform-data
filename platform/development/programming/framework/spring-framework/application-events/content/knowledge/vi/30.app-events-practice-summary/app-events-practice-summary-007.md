# Kiểm thử commit và rollback với Spring Application Events

## 1. Mục tiêu của bài thực hành

Khi một ứng dụng Spring thay đổi dữ liệu và phát event, câu hỏi quan trọng không chỉ là **listener có được gọi hay không**. Ta còn phải biết listener chạy **trước commit**, **sau commit thành công**, **sau rollback** hay **sau khi giao dịch hoàn tất theo bất kỳ kết quả nào**.

Ví dụ một service tạo đơn hàng:

```java
@Transactional
public void createOrder(String orderId) {
    orderRepository.insert(orderId);
    publisher.publishEvent(new OrderPlaced(orderId));
}
```

Đây chỉ là **khung minh họa**, chưa phải chương trình chạy độc lập. Vì event được publish bên trong giao dịch, nếu listener ngay lập tức gửi email hoặc gọi hệ thống thanh toán, side effect bên ngoài có thể xảy ra **trước khi dữ liệu được commit**. Giao dịch DB có thể rollback sau đó, nhưng email hoặc HTTP request đã gửi thì transaction manager không tự thu hồi được.

Ngược lại, nếu dùng `@TransactionalEventListener(phase = AFTER_COMMIT)`, handler chỉ xử lý khi transaction commit. Nhưng một bài test có `@Transactional` trên **chính phương thức test** lại thường rollback ở cuối test; vì vậy `AFTER_COMMIT` có thể không chạy, khiến lập trình viên tưởng listener cấu hình sai.

Bài học này hướng đến khả năng **viết test xác nhận đúng phase và dữ liệu thực tế**, chứ không chỉ log hoặc mock một lời gọi:

- Phân biệt `@EventListener` với `@TransactionalEventListener`.
- Hiểu bốn phase `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.
- Tạo giao dịch commit và rollback có chủ đích bằng `@Transactional` và H2.
- Dùng JUnit 5/Spring TestContext để kiểm tra những gì được lưu vào DB.
- Dùng `TestTransaction.flagForCommit()`, `flagForRollback()` và `end()` để quan sát callback **ngay trong phương thức test**.
- Kiểm thử lỗi ở `BEFORE_COMMIT`, trường hợp publish ngoài transaction và các anti-pattern.
- Hiểu giới hạn quan trọng: `AFTER_COMMIT` **không tự đảm bảo** việc giao event bền vững sau process crash.

## 2. Phân biệt publish event với transaction commit

Trong Spring, lời gọi:

```java
publisher.publishEvent(new OrderPlaced("ORD-1"));
```

có nghĩa là **yêu cầu Spring phân phối một Java object**. Bản thân lời gọi đó không có nghĩa:

- Transaction hiện tại đã commit.
- Dữ liệu đã được flush xuống DB.
- Listener đã hoàn tất side effect.
- Event đã được lưu trong một durable queue.
- Transaction rollback có thể đảo ngược thao tác của một HTTP API khác.

Với event nội bộ, Spring thường dùng `SimpleApplicationEventMulticaster` để dispatch listener. Listener `@EventListener` bình thường chạy đồng bộ theo cấu hình mặc định; nếu listener được gọi trong transaction đang hoạt động, mã của listener có thể tham gia ngữ cảnh transaction đó nếu nó thực hiện thao tác DB cùng resource.

Còn `@TransactionalEventListener` gắn việc thực thi method với **một phase của transaction**. Khi event được publish trong giao dịch đang hoạt động, Spring đăng ký một transaction synchronization để gọi callback tại thời điểm thích hợp.

```text
OrderService @Transactional
        |
        v
BEGIN transaction
        |
        +--> INSERT orders
        |
        +--> publisher.publishEvent(OrderPlaced)
        |          |
        |          +--> @EventListener: thường gọi ngay
        |          |
        |          +--> @TransactionalEventListener:
        |                    đăng ký chờ phase
        |
        +--> service method trả về
        |
        +--> BEFORE_COMMIT callbacks (nếu chuẩn bị commit)
        |
        +--> COMMIT hoặc ROLLBACK
        |
        +--> AFTER_COMMIT / AFTER_ROLLBACK
        |
        +--> AFTER_COMPLETION
```

Sơ đồ là **mô hình khái niệm** cho transaction imperative. Đừng hiểu các mốc là các lần gọi API cố định từ code nghiệp vụ: transaction manager và các synchronization chịu trách nhiệm điều phối thực tế.

### Bốn phase cần biết

| Phase | Khi nào handler được gọi? | Có chạy nếu rollback? | Mục đích thường gặp |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction cố gắng commit | Không trong luồng rollback thông thường; có thể đã chạy rồi commit sau đó thất bại | Kiểm tra/chuẩn bị tác vụ còn ảnh hưởng commit |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Không | Hậu xử lý chỉ dành cho dữ liệu đã commit |
| `AFTER_ROLLBACK` | Khi transaction rollback | Có | Ghi nhận lỗi, bù trừ có kiểm soát |
| `AFTER_COMPLETION` | Khi transaction đã hoàn tất, dù commit hay rollback | Có | Cleanup/metrics/audit kết thúc |

Chú ý: `AFTER_COMPLETION` không tự truyền một tham số `committed=true/false` vào method `@TransactionalEventListener`. Nếu cần phân biệt kết quả trong callback này, phải thiết kế thêm nguồn trạng thái hoặc dùng phase riêng `AFTER_COMMIT`/`AFTER_ROLLBACK`.

### Mặc định là AFTER_COMMIT

```java
@TransactionalEventListener
public void on(OrderPlaced event) {
    // Tương đương phase = TransactionPhase.AFTER_COMMIT.
}
```

Nếu event được publish **khi không có transaction đang hoạt động**, listener kiểu này mặc định **không chạy** (`fallbackExecution=false`). Có thể bật `fallbackExecution=true`, nhưng khi đó handler có thể chạy ngoài ngữ cảnh giao dịch, khác với mục đích "chỉ chạy sau commit"; phải quyết định rõ hợp đồng trước khi dùng.

## 3. Ma trận hành vi cần kiểm thử

Giả định một service thực hiện `INSERT orders` rồi publish `OrderPlaced` trong cùng transaction:

| Kịch bản | Dòng DB sau giao dịch | BEFORE_COMMIT | AFTER_COMMIT | AFTER_ROLLBACK | AFTER_COMPLETION |
| --- | --- | --- | --- | --- | --- |
| Commit bình thường | Tồn tại | Có | Có | Không | Có |
| Exception gây rollback trước commit | Không tồn tại | Không | Không | Có | Có |
| Listener BEFORE_COMMIT ném lỗi khiến rollback | Không tồn tại | Đã bắt đầu, có thể ném lỗi | Không | Có | Có |
| Test-managed transaction chưa kết thúc | Có thể thấy dữ liệu **chưa commit trong cùng transaction** | Chưa | Chưa | Chưa | Chưa |
| TestTransaction commit thật | Tồn tại | Có | Có | Không | Có |
| TestTransaction rollback thật | Không tồn tại | Không | Không | Có | Có |
| Publish event ngoài transaction | Không có DB operation từ event | Không | Không | Không | Không |

Bảng giả định các listener không bị tắt bởi condition, không dùng executor bất đồng bộ và transaction manager hoạt động bình thường. Test không nên chỉ assert số lần method được gọi; cần assert **dữ liệu cuối trong DB** và **tập phase thực sự xảy ra**.

Đặc biệt, **đọc được một bản ghi bên trong transaction không có nghĩa bản ghi đã được commit**. Một transaction có thể thấy chính dữ liệu nó vừa ghi dù cuối cùng sẽ rollback.

## 4. Thiết kế bài thực hành: transaction thật, không dùng mock transaction

Để test những khác biệt trên, ta dựng một dự án nhỏ với:

- Java 17+ và Spring Boot 3.3.13.
- `spring-boot-starter-jdbc` để dùng `JdbcTemplate` và transaction manager.
- H2 in-memory để có commit/rollback thực tế, không cần cài database ngoài.
- `ApplicationEventPublisher` phát một Java record `OrderPlaced`.
- Một bean listener ghi dấu bốn phase vào `CopyOnWriteArrayList` **chỉ để quan sát trong demo**.
- JUnit Jupiter và Spring TestContext (qua starter-test) để kiểm tra kết quả.
- `TestTransaction` để kết thúc transaction của test một cách có chủ đích.

**Vì sao không chỉ mock `PlatformTransactionManager`?** Một mock tự trả kết quả do test dựng lên; nó không xác minh transaction synchronization, Spring proxy, commit/rollback DB hoặc registration của `@TransactionalEventListener`. Unit test vẫn hữu ích cho logic bên trong handler, nhưng đây là **integration test** của hành vi transaction.

### 4.1. Cấu trúc thư mục

```text
tx-event-testing/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/events/TxEventDemo.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/example/events/TxEventDemoTest.java
```

Tất cả file được trình bày đầy đủ ở phần dưới. Demo sử dụng DB memory và các mã đơn khác nhau để test không phụ thuộc vào thứ tự thực thi.

## 5. Dự án Java 17+ chạy được

### 5.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>tx-event-testing</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot quản lý phiên bản H2, Spring JDBC và JUnit thông qua dependency management. Không khai báo những phiên bản khác nhau cho các Spring Framework module trong cùng dự án.

### 5.2. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:tx_events_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.sql.init.mode=always
logging.level.root=WARN
```

Đây là DB in-memory: dữ liệu **không được dùng làm lưu trữ production** và không được bảo toàn khi toàn bộ process/DB memory bị hủy. Property `spring.sql.init.mode=always` cho Spring Boot chạy script `schema.sql` để tạo bảng.

### 5.3. src/main/resources/schema.sql

```sql
CREATE TABLE IF NOT EXISTS orders (
    id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);
```

Dùng `IF NOT EXISTS` để script phù hợp với nhiều lần tạo context trong bài thực hành. Bảng `orders` chỉ phục vụ kiểm tra commit/rollback; không phải mô hình nghiệp vụ đầy đủ.

### 5.4. src/main/java/example/events/TxEventDemo.java

```java
package example.events;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@SpringBootApplication
@EnableTransactionManagement
public class TxEventDemo {

    // Spring có thể publish record POJO này.
    public record OrderPlaced(String orderId) {
    }

    // KHÔNG final: service được Spring AOP proxy để áp dụng @Transactional.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void place(String orderId, boolean forceFailure) {
            jdbc.update(
                    "INSERT INTO orders (id, status) VALUES (?, ?)",
                    orderId, "CREATED");

            // Publish khi transaction chưa commit.
            publisher.publishEvent(new OrderPlaced(orderId));

            if (forceFailure) {
                throw new IllegalStateException(
                        "simulated business failure");
            }
        }
    }

    // Chỉ ghi dấu phase vào RAM để làm rõ hành vi callback.
    public static class PhaseProbe {
        private final List<String> observed =
                new CopyOnWriteArrayList<>();

        private void add(String phase, OrderPlaced event) {
            observed.add(phase + ":" + event.orderId());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(OrderPlaced event) {
            add("BEFORE_COMMIT", event);

            // Bài tập: exception khi chuẩn bị commit có thể
            // làm transaction rollback.
            if ("ORD-VETO".equals(event.orderId())) {
                throw new IllegalStateException(
                        "before-commit validation failed");
            }
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            add("AFTER_COMMIT", event);
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderPlaced event) {
            add("AFTER_ROLLBACK", event);
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderPlaced event) {
            add("AFTER_COMPLETION", event);
        }

        public boolean has(String phase, String orderId) {
            return observed.contains(phase + ":" + orderId);
        }

        public List<String> snapshot() {
            return List.copyOf(observed);
        }

        public void clear() {
            observed.clear();
        }
    }

    @Bean
    OrderService orderService(
            JdbcTemplate jdbc,
            ApplicationEventPublisher publisher) {
        return new OrderService(jdbc, publisher);
    }

    @Bean
    PhaseProbe phaseProbe() {
        return new PhaseProbe();
    }

    public static int count(JdbcTemplate jdbc, String orderId) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE id = ?",
                Integer.class, orderId);

        return count == null ? 0 : count;
    }

    @Bean
    CommandLineRunner scenario(
            OrderService orders,
            JdbcTemplate jdbc,
            PhaseProbe probe) {

        return args -> {
            probe.clear();
            orders.place("ORD-DEMO-C", false);

            System.out.printf(
                    "COMMIT rows=%d before=%s after=%s"
                            + " rollback=%s completion=%s%n",
                    count(jdbc, "ORD-DEMO-C"),
                    probe.has("BEFORE_COMMIT", "ORD-DEMO-C"),
                    probe.has("AFTER_COMMIT", "ORD-DEMO-C"),
                    probe.has("AFTER_ROLLBACK", "ORD-DEMO-C"),
                    probe.has("AFTER_COMPLETION", "ORD-DEMO-C"));

            probe.clear();
            try {
                orders.place("ORD-DEMO-R", true);
            } catch (IllegalStateException expected) {
                // Chỉ nuốt lỗi được cố ý tạo ra trong demo.
            }

            System.out.printf(
                    "ROLLBACK rows=%d before=%s after=%s"
                            + " rollback=%s completion=%s%n",
                    count(jdbc, "ORD-DEMO-R"),
                    probe.has("BEFORE_COMMIT", "ORD-DEMO-R"),
                    probe.has("AFTER_COMMIT", "ORD-DEMO-R"),
                    probe.has("AFTER_ROLLBACK", "ORD-DEMO-R"),
                    probe.has("AFTER_COMPLETION", "ORD-DEMO-R"));
        };
    }

    public static void main(String[] args) {
        SpringApplication.run(TxEventDemo.class, args).close();
    }
}
```

### 5.5. Vai trò của từng thành phần

**`OrderService`** được khai báo là Spring bean. Phương thức `place(...)` có `@Transactional`, được gọi qua bean do Spring quản lý, nên transaction interceptor tạo/điều phối giao dịch. Không tự `new OrderService(...)` rồi gọi `place` trong test mà kỳ vọng annotation mở transaction.

**`JdbcTemplate`** thực hiện một lệnh `INSERT` trong giao dịch hiện tại. Không có JPA persistence context hoặc buffering ở tầng ORM, nên bài dễ quan sát dữ liệu DB; các kiến thức về flush của JPA sẽ được đề cập riêng.

**`ApplicationEventPublisher`** được gọi khi transaction chưa kết thúc. Spring nhận record `OrderPlaced` qua cơ chế payload event; ta không cần bắt record kế thừa `ApplicationEvent` khi dùng method `@TransactionalEventListener` có parameter đúng kiểu.

**`PhaseProbe`** có bốn method listener riêng, từng method gắn một phase. Bean chỉ lưu string `PHASE:orderId`. Nó không thực hiện HTTP request, không ghi DB sau commit và không tự bảo đảm event bền vững.

**`ORD-VETO`** là một tình huống cố ý: khi callback `BEFORE_COMMIT` gặp mã đơn đó, nó ném exception. Bài test tương ứng sẽ xác nhận transaction **không commit** và listener rollback được kích hoạt.

**`CommandLineRunner`** chạy hai trường hợp khi ứng dụng khởi động, rồi main đóng context. Điều này giúp có stdout ngắn, dễ kiểm tra trước khi chạy test.

### 5.6. Cách chạy

Từ thư mục chứa `pom.xml`, với Java 17+ và Maven:

```bash
mvn -q package
java -jar target/tx-event-testing-1.0.0.jar
```

Hai dòng **do mã demo tự in**, không kể log của thư viện:

```text
COMMIT rows=1 before=true after=true rollback=false completion=true
ROLLBACK rows=0 before=false after=false rollback=true completion=true
```

Vì sao output xác định được?

1. `OrderService.place("ORD-DEMO-C", false)` hoàn tất bình thường nên transaction commit; bản ghi có trong H2, `BEFORE_COMMIT` và `AFTER_COMMIT` đã được gọi, `AFTER_ROLLBACK` không chạy, `AFTER_COMPLETION` chạy.
2. Với `ORD-DEMO-R`, method ném unchecked `IllegalStateException` **trước khi chuẩn bị commit**. Transaction interceptor rollback; dòng DB bị hủy, `BEFORE_COMMIT` không chạy, `AFTER_ROLLBACK` và `AFTER_COMPLETION` được gọi.
3. Bài in các giá trị boolean về việc từng phase xuất hiện thay vì dump nguyên danh sách, nên không phụ thuộc thứ tự tương đối giữa các callback thuộc cùng giai đoạn.
4. Demo sử dụng event listeners đồng bộ với transaction manager imperative; không có executor async, broker hoặc connection tới dịch vụ khác.

**Giới hạn:** Chương trình chính chỉ minh họa hai nhánh; các bài test sau kiểm tra thêm BEFORE_COMMIT failure, publish không có transaction và giao dịch do TestContext quản lý.

## 6. Integration tests: kiểm tra cả event phase và trạng thái DB

Đặt file `src/test/java/example/events/TxEventDemoTest.java`:

```java
package example.events;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = TxEventDemo.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class TxEventDemoTest {

    @Autowired
    TxEventDemo.OrderService orders;

    @Autowired
    TxEventDemo.PhaseProbe probe;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ApplicationEventPublisher publisher;

    @BeforeEach
    void resetProbe() {
        probe.clear();
    }

    private int rows(String id) {
        return TxEventDemo.count(jdbc, id);
    }

    private void assertCommitPhases(String id) {
        assertTrue(probe.has("BEFORE_COMMIT", id));
        assertTrue(probe.has("AFTER_COMMIT", id));
        assertFalse(probe.has("AFTER_ROLLBACK", id));
        assertTrue(probe.has("AFTER_COMPLETION", id));
        assertEquals(3, probe.snapshot().size());
    }

    private void assertRollbackPhases(String id, boolean hadBefore) {
        assertEquals(hadBefore,
                probe.has("BEFORE_COMMIT", id));
        assertFalse(probe.has("AFTER_COMMIT", id));
        assertTrue(probe.has("AFTER_ROLLBACK", id));
        assertTrue(probe.has("AFTER_COMPLETION", id));
        assertEquals(hadBefore ? 3 : 2,
                probe.snapshot().size());
    }

    @Test
    void serviceCommitPersistsRowAndFiresCommitPhases() {
        String id = "ORD-TEST-C";

        orders.place(id, false);

        assertEquals(1, rows(id));
        assertCommitPhases(id);
    }

    @Test
    void serviceExceptionRollsBackAndFiresRollbackPhases() {
        String id = "ORD-TEST-R";

        assertThrows(
                IllegalStateException.class,
                () -> orders.place(id, true));

        assertEquals(0, rows(id));
        assertRollbackPhases(id, false);
    }

    @Test
    void beforeCommitExceptionPreventsCommit() {
        String id = "ORD-VETO";

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> orders.place(id, false));

        assertEquals(
                "before-commit validation failed",
                error.getMessage());
        assertEquals(0, rows(id));
        assertRollbackPhases(id, true);
    }

    @Test
    void eventOutsideTransactionIsIgnoredByDefault() {
        publisher.publishEvent(
                new TxEventDemo.OrderPlaced("ORD-NO-TX"));

        assertTrue(probe.snapshot().isEmpty());
    }

    @Test
    @Transactional
    void testTransactionCanBeCommittedExplicitly() {
        String id = "ORD-TX-COMMIT";

        assertTrue(TestTransaction.isActive());

        // Service @Transactional(REQUIRED) tham gia transaction test.
        orders.place(id, false);

        // Đọc trong transaction thấy row chưa commit.
        assertEquals(1, rows(id));
        assertTrue(probe.snapshot().isEmpty());

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertEquals(1, rows(id));
        assertCommitPhases(id);
    }

    @Test
    @Transactional
    void testTransactionCanBeRolledBackExplicitly() {
        String id = "ORD-TX-ROLLBACK";

        assertTrue(TestTransaction.isActive());
        orders.place(id, false);

        assertEquals(1, rows(id));
        assertTrue(probe.snapshot().isEmpty());

        TestTransaction.flagForRollback();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertEquals(0, rows(id));
        assertRollbackPhases(id, false);
    }
}
```

### 6.1. Chạy các bài test

```bash
mvn test
```

Chỉ chạy class trên:

```bash
mvn -Dtest=TxEventDemoTest test
```

Dự án định nghĩa **6 JUnit test methods**. Khi môi trường và dependency phù hợp, cả sáu kiểm tra đều qua. Maven Surefire báo số test, lỗi và thời lượng thực tế; không cần assert nguyên văn log của framework vì startup/log phụ thuộc môi trường.

Bài test dùng **context thật + transaction manager thật + H2**. Nó khác unit test gọi trực tiếp `listener.beforeCommit(event)`: direct call không chứng minh Spring đã đăng ký transaction synchronization, không kích hoạt commit và không thay đổi DB.

### 6.2. Những điều mỗi test chứng minh

| Test | Hành động | Bằng chứng |
| --- | --- | --- |
| `serviceCommitPersistsRowAndFiresCommitPhases` | Gọi service ngoài test transaction, method trả bình thường | DB có row, BEFORE+AFTER_COMMIT+AFTER_COMPLETION |
| `serviceExceptionRollsBackAndFiresRollbackPhases` | Service ném runtime exception | DB không có row, AFTER_ROLLBACK+AFTER_COMPLETION |
| `beforeCommitExceptionPreventsCommit` | Callback BEFORE_COMMIT ném exception | Commit bị chặn, DB rollback, callback rollback được quan sát |
| `eventOutsideTransactionIsIgnoredByDefault` | Publish record khi không có transaction | Không có phase listener chạy |
| `testTransactionCanBeCommittedExplicitly` | Test-managed transaction được commit qua TestTransaction | Callback commit chỉ xuất hiện sau `end()`, DB commit |
| `testTransactionCanBeRolledBackExplicitly` | Test-managed transaction được rollback qua TestTransaction | Callback rollback chỉ xuất hiện sau `end()`, DB rollback |

Hai test có `@Transactional` ở method được Spring TestContext quản lý. `@BeforeEach` làm sạch probe mỗi test; trong trường hợp test transactional, lifecycle method cũng chạy trong ngữ cảnh test transaction. Ta không xóa toàn bảng trong `@BeforeEach` vì các ID khác nhau; điều này giúp test độc lập, không phải dựa vào test chạy theo thứ tự nào.

**Chú ý:** Boot còn chạy `CommandLineRunner` trong giai đoạn khởi tạo test context. Runner dùng ID riêng `ORD-DEMO-C/ORD-DEMO-R`; `@BeforeEach` xóa probe để không trộn dấu vết startup vào assertion, còn mỗi test dùng ID khác. Việc này được chủ động tính đến để các test có thể chạy cùng một project demo.

## 7. Bẫy lớn nhất: @Transactional trên test không có nghĩa đã commit

Một anti-pattern thường gặp:

```java
@Test
@Transactional
void wrongAssumption() {
    orderService.place("ORD-1", false);
    assertTrue(afterCommitWasCalled);
}
```

Đoạn này **không phải test độc lập**; nó chỉ minh họa lỗi về giả định.

Trong Spring TestContext, `@Transactional` trên test method thường làm Spring mở **test-managed transaction** trước khi thực thi method và **mặc định rollback khi test kết thúc**. Service dùng `Propagation.REQUIRED` tham gia transaction đó, nên lời gọi method của service **không tự commit một transaction riêng khi trở về**.

Hệ quả:

1. `orderService.place(...)` đã thực hiện `INSERT` nhưng chưa commit.
2. Spring đã đăng ký callback của `@TransactionalEventListener`.
3. Test đọc DB qua kết nối/transaction hiện tại có thể thấy row.
4. `AFTER_COMMIT` **chưa được gọi** tại thời điểm assertion.
5. Khi test hoàn tất, TestContext rollback mặc định; listener `AFTER_ROLLBACK` có thể được gọi **sau phần body của test**.

Một test có thể pass nếu chỉ kiểm tra row đã được insert trong cùng transaction, dù production sẽ gặp lỗi lúc flush/commit. Điều này đặc biệt dễ xảy ra với JPA/Hibernate vì thao tác ghi có thể bị trì hoãn đến flush.

### 7.1. Điều khiển transaction bằng TestTransaction

Với test có `@Transactional` và transaction manager phù hợp:

```java
TestTransaction.flagForCommit();
TestTransaction.end();
```

Hai lệnh có ý nghĩa khác nhau:

- `flagForCommit()` đặt cờ **kết thúc bằng commit** cho test-managed transaction hiện tại.
- `end()` **thực sự kết thúc** transaction; tại đây callback BEFORE_COMMIT/AFTER_COMMIT/AFTER_COMPLETION có thể chạy.

Tương tự:

```java
TestTransaction.flagForRollback();
TestTransaction.end();
```

đặt cờ và kết thúc bằng rollback. **Chỉ gọi `flagForCommit()` mà không gọi `end()` thì body test vẫn chưa quan sát được commit.**

Ngoài ra còn có `TestTransaction.start()` để bắt đầu lại một test transaction sau khi đã kết thúc. Đừng gọi `start()` khi một transaction test vẫn đang active; phải hiểu vòng đời và chủ động kết thúc. Trong ví dụ mục 6, ta chỉ cần một transaction rồi kết thúc ngay.

### 7.2. @Commit, @Rollback và @AfterTransaction

Các annotation này cũng hữu ích:

```java
@Test
@Transactional
@Commit
void commitAtEndOfTest() {
    // TestContext commit sau khi body test kết thúc.
}
```

```java
@Test
@Transactional
@Rollback
void rollbackAtEndOfTest() {
    // TestContext rollback sau khi body test kết thúc.
}
```

Đây là **method minh họa**, yêu cầu import `org.springframework.test.annotation.Commit` và `Rollback`. `@Commit` phù hợp khi muốn thay đổi default rollback **sau** test. Nhưng nếu phải assert ngay **sau commit trong cùng method**, `TestTransaction.end()` thuận tiện hơn.

Với `@AfterTransaction`, có thể xác minh kết quả **sau khi** test-managed transaction được hoàn tất, hoặc dùng `@BeforeTransaction` để kiểm tra trạng thái trước đó. Không đặt mọi assertion về `AFTER_COMMIT` ngay giữa body test transactional rồi nghĩ rằng handler sẽ chạy khi method service trả về.

### 7.3. Timeout của test và thread-local transaction

Spring quản lý transaction imperative dựa vào context gắn với thread. Một cơ chế timeout **preemptive** có thể đưa code test sang thread khác, khiến lệnh DB chạy ngoài test transaction, có nguy cơ commit thật dù Spring vẫn rollback một transaction gắn với thread ban đầu.

Tránh dùng kiểu timeout chạy test body trên worker riêng khi đang kỳ vọng Spring TestContext rollback tự động. Ưu tiên timeout không chuyển thread hoặc kiểm soát rõ task/transaction boundary theo tài liệu Spring.

## 8. Trường hợp service transaction không giống transaction của test

Các ví dụ trên dùng propagation mặc định `REQUIRED`: nếu có transaction, service tham gia; nếu không, nó tạo transaction mới.

Khi thay propagation, hành vi cũng khác:

| Propagation ở service | Tác động khi test đã có @Transactional |
| --- | --- |
| `REQUIRED` | Service thường tham gia transaction test; không commit khi method trả về |
| `REQUIRES_NEW` | Tạm treo transaction hiện tại và chạy transaction **mới**, có thể commit độc lập |
| `NESTED` | Có thể dùng savepoint trong cùng transaction vật lý nếu transaction manager hỗ trợ; không tương đương một commit vật lý riêng |
| `SUPPORTS` | Tham gia transaction nếu có; không nhất thiết tạo mới |
| `NOT_SUPPORTED` | Tạm dừng transaction hiện tại; hành vi DB ngoài transaction cần được đánh giá |
| `MANDATORY` | Yêu cầu đã có transaction, nếu không có thì lỗi |

**Cảnh báo:** Test có `@Transactional` và rollback cuối test **không thể chắc chắn dọn mọi thay đổi của `REQUIRES_NEW`**. Giao dịch mới có thể commit rồi tồn tại sau khi transaction ngoài rollback. Khi viết test cho service có propagation phức tạp, dùng ID cô lập, database test riêng hoặc cleanup có kiểm soát.

Đừng dùng `REQUIRES_NEW` chỉ để “làm test dễ pass”. Lý do nghiệp vụ thực tế của transaction riêng phải được giải thích rõ; nếu không, test đang che giấu khác biệt với luồng sản xuất.

## 9. BEFORE_COMMIT failure và rollback-only

Trong ví dụ, `PhaseProbe.beforeCommit(...)` ném exception cho `ORD-VETO`. Đây là tình huống có giá trị học tập:

```text
place("ORD-VETO", false)
    |
    +--> INSERT orders
    +--> publish OrderPlaced
    |
    v
@Transactional service trả về
    |
    v
BEFORE_COMMIT callback
    |
    +--> log BEFORE_COMMIT
    +--> throw IllegalStateException
    |
    v
Transaction manager rollback
    |
    +--> AFTER_ROLLBACK
    +--> AFTER_COMPLETION
    |
    v
Caller nhận exception; orders không có ORD-VETO
```

**Điểm quan trọng:** `BEFORE_COMMIT` có thể thực hiện việc ảnh hưởng quyết định commit. Nhưng không nên gắn các side effect bên ngoài **không rollback được** vào BEFORE_COMMIT mà mặc định chúng an toàn; DB commit vẫn có thể thất bại sau khi remote side effect đã diễn ra.

Một cách khác làm transaction rollback là đánh dấu rollback-only:

```java
TransactionAspectSupport.currentTransactionStatus()
        .setRollbackOnly();
```

Đây là **đoạn minh họa**, chỉ có ý nghĩa khi đang có transaction status do Spring AOP quản lý. Nếu một inner participant đánh dấu transaction chung rollback-only nhưng outer service vẫn cố commit, Spring có thể ném `UnexpectedRollbackException` tùy ranh giới và cấu hình. Khi test, phân biệt lỗi được ném ra ngoài với **trạng thái DB cuối cùng**.

Nên kiểm tra cả các lỗi đến từ flush/constraint/commit thay vì chỉ một dòng `throw new IllegalStateException(...)` trong service.

## 10. AFTER_COMMIT: có thể tin cái gì, không được suy luận cái gì?

Sau khi transaction gốc đã commit thành công, `@TransactionalEventListener(AFTER_COMMIT)` phù hợp cho các tác vụ như:

- Kích hoạt cập nhật projection tách biệt với write model.
- Yêu cầu gửi email thông báo khi đơn thật sự đã được lưu.
- Gọi adapter gửi integration event ra ngoài sau khi dữ liệu nguồn commit.
- Ghi metrics/audit về event đã được commit, với chính sách lỗi riêng.

Nhưng cần ba giới hạn:

**Thứ nhất: AFTER_COMMIT không tự rollback DB đã commit.** Nếu email, HTTP API hoặc message publish thất bại ở callback, transaction ghi đơn hàng đã kết thúc; không thể “uncommit” nó bằng cách ném exception trong listener. Phải chọn retry, persisted job, outbox hoặc xử lý bù trừ.

**Thứ hai: callback sau commit không bảo đảm task được lưu bền vững.** Process có thể chết ngay sau khi DB commit, trước khi listener thực thi hoặc hoàn thành. `@TransactionalEventListener` không phải transactional outbox.

**Thứ ba: transaction resources có thể còn gắn với thread trong giai đoạn callback.** Theo tài liệu Spring, thao tác data-access sau commit có thể trông như vẫn tham gia một transaction cũ, nhưng **thay đổi mới không còn một commit tiếp theo**. Khi cần ghi DB mới ở callback, hãy mở một transaction độc lập qua service khác có `Propagation.REQUIRES_NEW`.

Ví dụ cấu trúc minh họa:

```java
@Component
public class OrderAuditListener {
    private final AuditWriter auditWriter;

    public OrderAuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        auditWriter.saveAfterCommit(event.orderId());
    }
}

@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAfterCommit(String orderId) {
        repository.save(orderId);
    }
}
```

Đây là **hai class minh họa**, không thuộc project mục 5; chúng giả định đã có `AuditRepository`, `OrderPlaced` và imports `@Component`, `@Service`, `@TransactionalEventListener`, `TransactionPhase`, `@Transactional`, `Propagation`. Phần quan trọng là lời gọi từ **listener bean sang service bean riêng** để Spring proxy có thể tạo transaction mới. Gọi `this.saveAfterCommit(...)` trên cùng bean thường bypass proxy.

Khi test cấu trúc này, assert rằng bản ghi audit **tồn tại sau** transaction commit, không chỉ assert mock repository được gọi. Với rollback, assert bản ghi audit không xuất hiện. Đồng thời test failure khi transaction mới không thể tạo hoặc DB write thất bại.

## 11. AFTER_ROLLBACK: dùng để ghi nhận thất bại, không tự sửa được rollback

`@TransactionalEventListener(AFTER_ROLLBACK)` chạy sau khi giao dịch nguồn thất bại. Một số use case:

- Phát tín hiệu retry ở tầng job có trạng thái bền vững.
- Ghi nhận số lần rollback và lý do ở monitoring.
- Giải phóng tài nguyên tạm hoặc bổ sung hành động bù trừ đã thiết kế.
- Điều tra khi transaction không thể lưu một aggregate.

Nhưng handler AFTER_ROLLBACK **không tự biết toàn bộ nguyên nhân rollback** chỉ qua parameter event. Event là object đã được publish trước đó; để biết exception/status cụ thể, cần truyền/correlate dữ liệu phù hợp hoặc quan sát tại service boundary/log/tracing.

Một rollback có thể do nhiều nguyên nhân: exception trong service, exception ở BEFORE_COMMIT, validation lỗi, timeout, deadlock hoặc rollback-only. Test cần phân biệt các nhóm này nếu cách recovery khác nhau.

**Cẩn trọng về ghi audit trong rollback callback:** Bất kỳ thao tác ghi DB mới nào yêu cầu commit phải có transaction mới; nó không thể phụ thuộc một transaction đã rollback mà mong được lưu. Không nuốt mọi exception trong callback mà không lưu lại dấu vết vận hành.

## 12. AFTER_COMPLETION và thứ tự callbacks

`AFTER_COMPLETION` là điểm quan sát khi giao dịch hoàn tất cả hai trường hợp. Trong ví dụ, phase này luôn hiện cho hai nhánh commit và rollback thành công về mặt transaction management.

Nhưng:

- Đừng gộp `AFTER_COMPLETION` và `AFTER_COMMIT` thành một: rollback cũng kích hoạt completion.
- Nếu cần phân biệt commit/rollback, dùng listener phase riêng hoặc transaction synchronization có status.
- Đừng dùng thứ tự log giữa **hai listener cùng phase** làm hợp đồng nghiệp vụ. Thứ tự giữa các synchronization/listener có thể được cấu hình và bị ảnh hưởng bởi các thành phần khác.
- Nếu cần hai thao tác phải chạy tuần tự theo logic nghiệp vụ, hãy dùng một workflow/service orchestration rõ ràng thay vì chỉ dựa vào callback ordering.
- Nếu listener chạy bất đồng bộ hoặc submit thêm task, thời điểm event callback trả về không chứng minh tác vụ con đã hoàn tất.

Trong các test, **kiểm tra tập giá trị expected + số lượng**, như `assertCommitPhases(...)` trong ví dụ, thường bền hơn so với assert một danh sách log có thứ tự không được hợp đồng bảo đảm.

## 13. Phân biệt @EventListener và @TransactionalEventListener khi rollback

Hãy so sánh:

```java
@EventListener
public void immediate(OrderPlaced event) {
    // Thường chạy ngay lúc publish.
}

@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // Chỉ chạy khi transaction đã commit.
}
```

Đây là **hai method minh họa**, không nằm trong demo để tránh thay đổi số lượng record trong probe.

Nếu service insert order, publish event rồi ném exception:

- `immediate(...)` **có thể đã chạy** trước lúc rollback. Nếu nó gửi email, email đã đi.
- `afterCommit(...)` **không chạy** khi transaction rollback thông thường.
- `AFTER_ROLLBACK` chạy để ghi nhận rollback.
- Một `@EventListener` đồng bộ ném unchecked exception trước commit có thể khiến transaction rollback, nhưng nếu exception bị multicaster `ErrorHandler` nuốt hoặc callback chạy async, kết quả có thể khác.

Vì vậy, chọn phase theo **hậu quả nghiệp vụ**: không phải cứ “muốn lỏng coupling” là đổi mọi listener sang AFTER_COMMIT; mỗi loại side effect có yêu cầu riêng.

## 14. Test async và transaction: hai trục độc lập

Trong ví dụ runnable, phase listeners được gọi đồng bộ. Nếu ứng dụng dùng:

```java
@Async("eventExecutor")
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    remoteClient.send(event.orderId());
}
```

đây là **đoạn minh họa** với executor, `@EnableAsync`, bean `remoteClient` và listener Spring quản lý. Việc đăng ký callback phải diễn ra trong transaction-bound context phù hợp; sau commit, công việc remote có thể chạy trên worker khác.

Khi kiểm thử:

1. Không assert remote side effect ngay lập tức sau service call nếu method async.
2. Dùng `CountDownLatch`, `Awaitility` hoặc polling có timeout để chờ công việc.
3. Kiểm tra rằng event từ transaction rollback **không tạo task gửi**, nếu contract yêu cầu AFTER_COMMIT.
4. Kiểm tra executor rejection, shutdown, timeout và đường xử lý exception.
5. Không giả định transaction imperative của publisher tự được truyền sang worker; nó thường gắn với thread.
6. Nếu worker cần ghi DB, mở transaction mới và quyết định cách retry khi lỗi.

**Quan trọng:** `@Async` chỉ chuyển việc ra thread khác, **không biến nó thành durable delivery**. Process chết có thể làm task chưa được xử lý mất. Với event quan trọng, thử nghiệm crash/restart và cơ chế lưu trạng thái là cần thiết.

## 15. Khi cần không mất event: transactional outbox

`AFTER_COMMIT` đảm bảo điều kiện **không xử lý cho transaction rollback**, nhưng chưa giải quyết khoảng hở:

```text
T1: UPDATE orders
T2: publish application event (đăng ký AFTER_COMMIT)
T3: COMMIT DB thành công
T4: process crash
T5: listener chưa kịp gửi message ra broker
```

Sau restart, Spring Application Events không có record event bền vững để tự phát lại. Dữ liệu order đã commit, nhưng hệ thống khác có thể không biết.

**Transactional outbox** thường là lựa chọn cho những event bắt buộc được giao:

```text
BEGIN DB TRANSACTION
    UPDATE orders
    INSERT outbox(eventId, type, payload, status=NEW)
COMMIT
           |
           v
Outbox relay / CDC đọc record đã commit
           |
           +--> publish broker
           +--> broker confirm
           +--> mark SENT / retry
           |
           v
Consumer idempotent
```

Trong test:

- **Commit:** order và outbox record đều tồn tại.
- **Rollback:** cả order và outbox record đều không tồn tại.
- **Broker lỗi:** outbox vẫn ở trạng thái chưa hoàn thành để relay thử lại.
- **Relay crash sau publish trước khi mark SENT:** có thể phát lại; consumer phải chống trùng.
- **Consumer crash sau side effect trước ACK:** redelivery không được tạo side effect lần hai.

Outbox **không đồng nghĩa exactly-once end-to-end**. Retry và redelivery có thể gây duplicate; cần `eventId` cố định và idempotency/inbox ở consumer. Đặc biệt với payment/email/HTTP, DB local transaction không tự rollback side effect từ hệ thống ngoài.

**Kết luận của phần này:** test AFTER_COMMIT là một bài test về **thời điểm xử lý**, không phải bài test đầy đủ về **độ bền của pipeline sự kiện**.

## 16. Các sai lầm phổ biến trong kiểm thử commit/rollback

**Lỗi 1 — Dùng @Transactional trên test rồi chờ AFTER_COMMIT ngay sau method service.** Service `REQUIRED` đang tham gia test transaction; chưa commit. Dùng `TestTransaction.end()` hoặc một test không có transaction bao ngoài.

**Lỗi 2 — Chỉ assert repository.save(...) được gọi.** Mock verify không chứng minh DB đã commit. Dùng H2/test database và truy vấn sau khi transaction kết thúc.

**Lỗi 3 — Thấy row trong cùng transaction rồi kết luận đã commit.** Cần đọc lại ngoài transaction hoặc xác minh bằng transaction boundary thực.

**Lỗi 4 — Gọi listener method trực tiếp.** Bỏ qua Spring event dispatch và transaction synchronization. Direct unit test chỉ dành cho logic handler.

**Lỗi 5 — Dùng TestTransaction.flagForCommit() nhưng quên end().** Cờ commit không khiến callback chạy ngay; transaction vẫn active.

**Lỗi 6 — Dùng @Commit để assert AFTER_COMMIT bên trong test body.** `@Commit` thường tác động lúc kết thúc test, nên body chưa quan sát được callback. Dùng `@AfterTransaction` hoặc TestTransaction khi cần.

**Lỗi 7 — Quên publish ngoài transaction.** `@TransactionalEventListener` mặc định bỏ qua; cần test riêng và không bật fallback tùy tiện.

**Lỗi 8 — Đặt transaction annotation trên private/final/self-invoked method rồi mong proxy tạo transaction.** Kiểm tra cách Spring quản lý bean và gọi method qua proxy.

**Lỗi 9 — Chỉ assert exception và bỏ qua trạng thái DB.** Một exception từ AFTER_COMMIT có thể xảy ra sau khi dữ liệu đã commit; exception không chứng minh rollback.

**Lỗi 10 — Ghi DB mới trong AFTER_COMMIT mà không mở transaction mới.** Resource transaction cũ có thể còn gắn thread, nhưng không còn commit cho thay đổi mới. Dùng service `REQUIRES_NEW` qua proxy.

**Lỗi 11 — Dùng thứ tự log giữa listener làm bằng chứng.** Nhiều listener/async/transaction synchronizations có thể làm thứ tự khác mong đợi. Assert trạng thái/phase, không phụ thuộc log order nếu không có hợp đồng ordering.

**Lỗi 12 — Dùng sleep để đợi listener async.** Test flaky; dùng latch/polling có timeout và theo dõi lỗi executor.

**Lỗi 13 — Quên JPA flush.** Test với ORM có thể không gửi SQL/vi phạm constraint cho đến lúc flush; gọi `entityManager.flush()` đúng vị trí để tránh false positive.

**Lỗi 14 — Ngầm giả định afterRollback biết nguyên nhân.** Phase nói transaction rollback, không tự truyền exception gốc. Cần correlation/observability riêng.

**Lỗi 15 — Coi AFTER_COMMIT như outbox.** Process có thể chết sau commit trước khi gửi message. Dùng durable outbox khi event không được mất.

**Lỗi 16 — Để REQUIRES_NEW làm bẩn dữ liệu test.** Transaction độc lập có thể commit dù test transaction rollback. Dọn dữ liệu/fixture thích hợp và kiểm tra isolation.

**Lỗi 17 — Sử dụng preemptive timeout thay đổi thread test.** Có thể làm code chạy ngoài test-managed transaction, khiến rollback không bảo vệ DB. Tránh cách timeout không phù hợp.

## 17. Checklist trước khi kết thúc bài thực hành

1. Bài test đang gọi **Spring-managed service proxy** chứ không phải đối tượng tự tạo?
2. Event được publish ở **trong hay ngoài transaction**?
3. Listener là `@EventListener` thường hay `@TransactionalEventListener`?
4. Phase được khai báo rõ, biết default là `AFTER_COMMIT`?
5. Test có phân biệt commit, rollback do exception và rollback do callback BEFORE_COMMIT lỗi?
6. Có assert **dữ liệu DB sau transaction kết thúc** thay vì chỉ đọc row chưa commit?
7. Nếu test có `@Transactional`, đã chủ động dùng `TestTransaction.end()` khi cần quan sát callback?
8. Có hiểu rollback mặc định của TestContext và tác dụng của `@Commit`/`@Rollback`?
9. Có test publish ngoài transaction với `fallbackExecution=false`?
10. Có kiểm thử `AFTER_COMPLETION` cho cả commit và rollback?
11. Nếu callback after commit ghi DB, đã dùng transaction mới phù hợp?
12. Nếu có async, test có chờ có timeout và thu exception?
13. Đã phân biệt exception từ trước commit với exception từ hậu xử lý sau commit?
14. Có test rollback khi validation, deadlock/constraint hoặc rollback-only theo chính sách nghiệp vụ?
15. Với JPA, đã flush/clear khi kiểm tra kết quả cần commit/constraint?
16. Nếu event bắt buộc tới broker, đã thiết kế outbox, broker confirm, retry và idempotency?
17. Test có dữ liệu/ID cô lập, không phụ thuộc thứ tự chạy và không để transaction mới sót record?
18. Có metric/log theo event ID, transaction outcome, phase, latency và handler outcome, không lộ dữ liệu nhạy cảm?

**Ghi nhớ:** Một bài test Spring Application Events đúng phải biết **giao dịch nào là giao dịch thực, ai kết thúc nó và listener được gọi ở phase nào**. Dùng integration test với database thật và `TestTransaction` để xác minh cả callback lẫn trạng thái commit/rollback. Khi cần delivery xuyên service, bổ sung cơ chế lưu event bền vững: `AFTER_COMMIT` giải quyết vấn đề thời điểm, không thay thế transactional outbox.

## Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, phase, fallback và lưu ý tài nguyên transaction.
- [Spring Framework — Transaction Management trong TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): transaction của test, rollback mặc định, `TestTransaction`, `@Commit`, `@Rollback` và `@AfterTransaction`.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher` và cách dispatch listener.
- [Spring Framework — TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): `phase`, `fallbackExecution`.
- [Spring Framework — TestTransaction API](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): `flagForCommit()`, `flagForRollback()`, `end()` và `start()`.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC/H2 và khởi tạo schema.
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/): lifecycle, assertions và chạy test.
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): khoảng hở dual-write và cơ chế relay.
