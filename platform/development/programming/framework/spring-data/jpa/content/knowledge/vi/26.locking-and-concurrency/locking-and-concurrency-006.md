# Thời gian chờ khóa, deadlock và khác biệt theo cơ sở dữ liệu

## 1. Mục tiêu

Khi nhiều transaction cùng truy cập một dòng, database có thể buộc một transaction chờ khóa. Nếu các transaction chờ nhau theo vòng tròn, database phát hiện deadlock và hủy một transaction để giải phóng tài nguyên. Thời gian chờ, phạm vi rollback và cách báo lỗi khác nhau giữa PostgreSQL, MySQL/InnoDB, SQL Server, Oracle và H2.

Bài học hướng dẫn cách:
- Phân biệt lock wait timeout, transaction timeout, query timeout và connection pool timeout.
- Dùng `@Lock(PESSIMISTIC_WRITE)` để khóa dòng trong transaction.
- Cấu hình lock timeout bằng JPA hint hoặc thiết lập riêng của database.
- Tái hiện lock wait bằng hai transaction độc lập.
- Tạo deadlock có kiểm soát bằng hai transaction khóa hai dòng theo thứ tự ngược nhau.
- Nhận diện lỗi theo Spring exception, SQLState và mã lỗi vendor.
- Chọn cách retry an toàn sau deadlock hoặc lỗi serialization.
- Hiểu các khác biệt quan trọng giữa database và lý do cần kiểm thử trên engine production.

## 2. Phân biệt các loại timeout và deadlock

Những lỗi này có thể cùng xuất hiện dưới dạng request chạy lâu, nhưng nguyên nhân và cách xử lý khác nhau:

| Khái niệm | Đang chờ điều gì? | Ví dụ |
| --- | --- | --- |
| Lock wait timeout | Chờ transaction khác nhả khóa trên dòng hoặc tài nguyên. | Transaction A giữ `SELECT ... FOR UPDATE`, transaction B muốn khóa cùng dòng. |
| Transaction timeout | Giới hạn thời gian transaction được phép hoạt động theo cấu hình transaction manager/provider. | Service transaction vượt quá thời lượng được phép. |
| Query/statement timeout | Giới hạn thời gian thực thi một câu SQL/JPA query. | SELECT chạy quá lâu hoặc bị chặn bởi lock. |
| Connection pool timeout | Chờ một connection rảnh từ pool của ứng dụng. | HikariCP đã hết connection khả dụng. |
| Deadlock | Các transaction chờ tài nguyên do transaction khác giữ theo một chu trình. | A giữ dòng 1 chờ dòng 2; B giữ dòng 2 chờ dòng 1. |

Lock wait timeout xảy ra khi một lần chờ vượt quá giới hạn. Deadlock là chu trình chờ; database thường phát hiện và chọn một transaction làm nạn nhân mà không cần đợi hết lock timeout.

`@Transactional(timeout = 5)` không đồng nghĩa chắc chắn với database `lock_timeout = 5 seconds`. Transaction timeout, query timeout và lock timeout có thể được truyền qua các lớp khác nhau; provider hoặc database có thể không áp dụng chúng giống nhau.

Connection pool timeout xảy ra trước khi SQL được gửi tới database. Nếu ứng dụng không lấy được connection, không có lock request nào được tạo ra. Hãy đọc exception và metric của connection pool để phân biệt trường hợp này.

## 3. Pessimistic lock trong Spring Data JPA

JPA cung cấp lock mode để yêu cầu database bảo vệ dữ liệu trong transaction. Với thao tác đọc rồi cập nhật, `PESSIMISTIC_WRITE` thường được dùng để khóa dòng trước khi thay đổi.

Repository:

```java
package com.example.inventory;

import java.util.Optional;
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository extends JpaRepository<Inventory, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findForUpdate(@Param("id") Long id);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints(@QueryHint(
            name = "jakarta.persistence.lock.timeout",
            value = "2000"))
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findForUpdateWithHint(@Param("id") Long id);
}
```

`@Lock` nằm trong `org.springframework.data.jpa.repository.Lock`; `@QueryHints` của Spring Data JPA nhận các `jakarta.persistence.QueryHint`. Hint `jakarta.persistence.lock.timeout` dùng đơn vị millisecond theo JPA. Provider/database có thể bỏ qua hoặc ánh xạ hint theo cách riêng, vì vậy phải xác nhận bằng integration test trên database thực tế.

JPA lock cần transaction đang hoạt động. Gọi method lấy lock ngoài transaction có thể dẫn đến `TransactionRequiredException` hoặc hành vi không phù hợp. Giữ thao tác lấy lock, đọc dữ liệu và cập nhật trong cùng transaction.

## 4. Entity và Service ví dụ

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data JPA và Hibernate do Spring Boot quản lý phiên bản. Entity `Inventory` có số lượng còn lại và domain method kiểm tra số lượng trước khi trừ.

`src/main/java/com/example/inventory/Inventory.java`:

```java
package com.example.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory")
public class Inventory {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int available;

    protected Inventory() {
        // JPA cần constructor không tham số.
    }

    public Inventory(int available) {
        if (available < 0) {
            throw new IllegalArgumentException("Available cannot be negative");
        }
        this.available = available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("Insufficient inventory");
        }
        available -= quantity;
    }

    public Long getId() { return id; }
    public int getAvailable() { return available; }
}
```

Service đặt transaction boundary quanh việc khóa và cập nhật:

`src/main/java/com/example/inventory/InventoryService.java`:

```java
package com.example.inventory;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional(timeout = 10)
    public void reserve(Long id, int quantity) {
        Inventory item = repository.findForUpdate(id)
                .orElseThrow(() -> new IllegalArgumentException("Inventory not found"));
        item.reserve(quantity);
    }
}
```

`@Transactional(timeout = 10)` là transaction timeout tính bằng giây theo Spring transaction abstraction. Nó không thay thế cấu hình lock wait timeout riêng của database. Ví dụ Service này giữ khóa cho tới khi transaction commit/rollback; không gọi HTTP, gửi email hoặc chờ thao tác người dùng trong khoảng thời gian đó.

## 5. Cấu hình lock timeout bằng JPA hint

JPA định nghĩa hint:

```text
jakarta.persistence.lock.timeout
```

Ví dụ trên đặt giá trị `2000`, tương ứng yêu cầu timeout 2.000 millisecond. Có thể dùng hint trên query có `@Lock` qua Spring Data `@QueryHints`.

Cần phân biệt các tình huống:

- Provider hỗ trợ hint và database có thể áp dụng: câu lệnh khóa được phát ra với timeout tương ứng.
- Provider không hỗ trợ hoặc database không có cách ánh xạ tương đương: hint có thể bị bỏ qua.
- Database có giới hạn timeout ở cấp session/transaction: cấu hình vendor có thể quyết định kết quả cuối cùng.

Không kết luận timeout hoạt động chỉ vì annotation biên dịch. Hãy giữ một transaction khóa dòng, gọi query từ transaction thứ hai và xác nhận query thứ hai kết thúc bằng lỗi timeout trong khoảng dự kiến.

## 6. Cấu hình timeout theo database

Không có một cú pháp SQL timeout duy nhất dùng được cho mọi engine. Các ví dụ sau là thiết lập thường gặp; cú pháp, quyền thay đổi và phạm vi áp dụng còn phụ thuộc phiên bản/database configuration.

| Database | Lock wait timeout / cách yêu cầu | Deadlock thường nhận diện bằng |
| --- | --- | --- |
| PostgreSQL | `SET LOCAL lock_timeout = '2s'`; `NOWAIT` hoặc `SKIP LOCKED` trên locking SELECT. | SQLState `40P01`. |
| MySQL InnoDB | `innodb_lock_wait_timeout` tính bằng giây; locking read hỗ trợ `NOWAIT`/`SKIP LOCKED` trên các phiên bản phù hợp. | Error 1213, SQLState thường là `40001`. |
| SQL Server | `SET LOCK_TIMEOUT 2000` tính bằng millisecond; có các lock hints riêng. | Error 1205 là deadlock victim; error 1222 là lock request timeout. |
| Oracle | `SELECT ... FOR UPDATE WAIT n`, `NOWAIT` hoặc `SKIP LOCKED`. | `ORA-00060`; resource busy thường là `ORA-00054`. |
| H2 | Có `LOCK_TIMEOUT` theo millisecond và cú pháp khóa riêng của H2. | Hành vi và mã lỗi của H2; không đại diện đầy đủ cho engine production. |

### 6.1. PostgreSQL

Trong transaction PostgreSQL, có thể đặt giới hạn chờ khóa cho transaction hiện tại:

```sql
SET LOCAL lock_timeout = '2s';
```

`SET LOCAL` hết hiệu lực khi transaction kết thúc. PostgreSQL cũng có `statement_timeout`, giới hạn thời gian cho statement nói chung. `lock_timeout` chỉ áp dụng thời gian chờ khóa; nếu `statement_timeout` ngắn hơn, statement có thể bị hủy trước.

Locking read có thể dùng:

```sql
SELECT id, available
FROM inventory
WHERE id = 10
FOR UPDATE NOWAIT;
```

`NOWAIT` trả lỗi ngay nếu không lấy được lock. `SKIP LOCKED` bỏ qua các dòng đang bị khóa, thường hữu ích cho worker lấy việc từ queue. Nó không phù hợp nếu caller cần một kết quả đọc đầy đủ và nhất quán.

PostgreSQL dùng SQLState `55P03` cho lock not available, gồm một số trường hợp `NOWAIT`/lock timeout; deadlock có SQLState `40P01`. Một lỗi statement làm transaction PostgreSQL ở trạng thái aborted cho đến khi rollback hoặc rollback về savepoint.

### 6.2. MySQL với InnoDB

InnoDB dùng `innodb_lock_wait_timeout` để giới hạn chờ khóa record. Giá trị thường được tính bằng giây và có thể cấu hình ở server hoặc session tùy quyền/version:

```sql
SET SESSION innodb_lock_wait_timeout = 2;
```

Locking read:

```sql
SELECT id, available
FROM inventory
WHERE id = 10
FOR UPDATE NOWAIT;
```

MySQL 8.0 hỗ trợ `NOWAIT` và `SKIP LOCKED` cho locking reads trên InnoDB. Hãy kiểm tra đúng phiên bản và loại storage engine đang sử dụng.

Deadlock InnoDB thường trả error 1213 với SQLState `40001`; lock wait timeout thường trả error 1205. Mặc định, deadlock làm InnoDB rollback toàn bộ transaction nạn nhân. Lock wait timeout thường chỉ rollback statement bị timeout; `innodb_rollback_on_timeout` có thể thay đổi hành vi rollback transaction. Sau lỗi timeout, ứng dụng cần quyết định rollback transaction hiện tại và không tiếp tục dùng trạng thái transaction nếu không chắc nó còn hợp lệ.

InnoDB có thể sử dụng record lock, gap lock và next-key lock tùy isolation level, index và điều kiện truy vấn. Thiếu index phù hợp có thể khiến truy vấn quét/khóa nhiều record hoặc khoảng hơn dự kiến.

### 6.3. SQL Server

SQL Server cho phép đặt lock wait timeout ở session:

```sql
SET LOCK_TIMEOUT 2000;
```

Giá trị tính bằng millisecond. `-1` thường biểu thị chờ vô hạn và `0` là không chờ. Cài đặt session có thể tồn tại khi connection được trả về pool; nếu thay đổi qua SQL, cần reset đúng cách hoặc cấu hình qua cơ chế quản lý connection để không ảnh hưởng request tiếp theo.

SQL Server có các lock hint như `UPDLOCK`, `ROWLOCK`, `READPAST`, nhưng chúng có semantics riêng và không nên thêm tùy tiện. `ROWLOCK` là gợi ý, engine vẫn có thể chọn lock granularity khác hoặc lock escalation.

Error 1205 báo transaction bị chọn làm deadlock victim. Error 1222 báo lock request timeout. Phân biệt hai lỗi này để chọn retry hoặc phản hồi nghiệp vụ phù hợp.

### 6.4. Oracle

Oracle cho phép chỉ định thời gian chờ ngay trong locking SELECT:

```sql
SELECT id, available
FROM inventory
WHERE id = 10
FOR UPDATE WAIT 2;
```

`WAIT 2` yêu cầu chờ tối đa 2 giây; `NOWAIT` trả lỗi ngay; `SKIP LOCKED` bỏ qua dòng đang bị khóa, thường dùng trong xử lý queue. `ORA-00054` thường biểu thị resource busy/không lấy được lock theo yêu cầu; `ORA-00060` báo deadlock.

Khả năng ánh xạ các tùy chọn này từ JPA lock hint phụ thuộc Hibernate dialect và driver. Khi cần cú pháp Oracle đặc thù, có thể dùng native query hoặc JDBC trong repository riêng, nhưng phải kiểm thử trên Oracle.

### 6.5. H2

H2 có thể cấu hình `LOCK_TIMEOUT` trong URL test:

```properties
spring.datasource.url=jdbc:h2:mem:lockdb;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=2000
```

Đây là tiện ích cho test nhẹ. H2 không tái hiện đầy đủ lock granularity, deadlock detector, isolation, error code hoặc timeout của PostgreSQL/MySQL/SQL Server/Oracle. Test H2 qua không chứng minh production database sẽ có hành vi giống hệt.

## 7. Deadlock hình thành như thế nào?

Deadlock cần có chu trình chờ. Ví dụ hai transaction cập nhật hai dòng:

```text
Transaction A                 Transaction B
-------------                 -------------
LOCK inventory 1              LOCK inventory 2
WAIT inventory 2              WAIT inventory 1
       |                              |
       +---------- DEADLOCK -----------+
```

A giữ dòng 1 và chờ dòng 2. B giữ dòng 2 và chờ dòng 1. Không transaction nào có thể tiếp tục nếu không có một transaction bị hủy.

Database theo dõi lock graph và chọn một transaction làm nạn nhân. Việc chọn victim phụ thuộc engine, chi phí rollback, mức độ ưu tiên và trạng thái hệ thống; không dựa vào giả định transaction bắt đầu sau luôn bị hủy.

Deadlock khác lock timeout: deadlock detector phát hiện vòng chờ; lock timeout chỉ kết thúc một lần chờ đã vượt giới hạn. Một transaction có thể bị hủy do deadlock trước khi lock timeout hết hạn.

## 8. Vì sao thứ tự khóa quan trọng?

Giả sử mọi luồng chuyển tiền đều khóa tài khoản theo ID tăng dần. Khi hai request chuyển tiền giữa cùng hai tài khoản theo hướng ngược nhau, cả hai vẫn lấy lock theo cùng thứ tự.

```java
List<Long> ids = Stream.of(sourceId, targetId)
        .sorted()
        .toList();

List<Account> accounts = repository.findAllForUpdate(ids);
```

Quy tắc khóa theo thứ tự ổn định làm giảm khả năng tạo chu trình chờ. Repository có thể cần query với `IN` và `ORDER BY id`; cần xác nhận database thực sự khóa theo thứ tự mong muốn bằng SQL và execution plan. Không giả định thứ tự trong collection Java tự quyết định thứ tự lock ở database.

Các biện pháp giảm deadlock:

- Khóa nhiều dòng theo cùng một thứ tự ở mọi code path.
- Giữ transaction ngắn và tránh thao tác mạng trong khi giữ lock.
- Thêm index cho điều kiện lọc để giảm số record phải quét/khóa.
- Chỉ khóa những dòng cần thiết.
- Tránh nâng isolation level quá cao nếu nghiệp vụ không cần.
- Không giữ lock khi chờ người dùng hoặc chờ một job khác.
- Retry transaction bị deadlock khi thao tác an toàn để chạy lại.

## 9. Kiểm thử lock wait timeout trên PostgreSQL

Test dưới đây dùng hai transaction độc lập:

1. Transaction A khóa một Inventory row và giữ lock.
2. Transaction B đặt `lock_timeout` ngắn trong chính transaction của nó.
3. B yêu cầu khóa cùng dòng và nhận SQLState `55P03`.
4. A nhả lock và commit.
5. Test đọc lại dữ liệu bằng transaction mới.

Ví dụ cần `spring-boot-starter-data-jpa`, PostgreSQL JDBC driver, `spring-boot-starter-test`, `org.testcontainers:junit-jupiter` và `org.testcontainers:postgresql` ở scope test.

`src/test/java/com/example/inventory/PostgreSqlLockTimeoutTest.java`:

```java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.SQLException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.jpa.open-in-view=false"
})
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class PostgreSqlLockTimeoutTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name", postgres::getDriverClassName);
    }

    @Autowired
    private InventoryRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private PlatformTransactionManager transactionManager;

    private TransactionTemplate transactions;

    @BeforeEach
    void setUp() {
        transactions = new TransactionTemplate(transactionManager);
        transactions.executeWithoutResult(status -> repository.deleteAllInBatch());
    }

    private Long createInventory() {
        return transactions.execute(status ->
                repository.saveAndFlush(new Inventory(10)).getId());
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for test coordination");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Test interrupted", ex);
        }
    }

    private static boolean hasSqlState(Throwable error, String expected) {
        for (Throwable current = error; current != null; current = current.getCause()) {
            if (current instanceof SQLException sql
                    && expected.equals(sql.getSQLState())) {
                return true;
            }
        }
        return false;
    }

    @Test
    void secondTransactionTimesOutWhileFirstHoldsTheRowLock() throws Exception {
        Long id = createInventory();
        CountDownLatch firstHasLock = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> holder = pool.submit(() -> transactions.executeWithoutResult(status -> {
                repository.findForUpdate(id).orElseThrow();
                firstHasLock.countDown();
                await(releaseFirst);
            }));

            assertThat(firstHasLock.await(10, TimeUnit.SECONDS)).isTrue();

            Future<Throwable> contender = pool.submit(() -> {
                try {
                    transactions.executeWithoutResult(status -> {
                        jdbcTemplate.execute("SET LOCAL lock_timeout = '300ms'");
                        repository.findForUpdate(id).orElseThrow();
                    });
                    return null;
                } catch (RuntimeException ex) {
                    return ex;
                }
            });

            Throwable failure = contender.get(5, TimeUnit.SECONDS);
            assertThat(failure).isNotNull();
            assertThat(hasSqlState(failure, "55P03")).isTrue();

            releaseFirst.countDown();
            holder.get(10, TimeUnit.SECONDS);
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }

        int available = transactions.execute(status ->
                repository.findById(id).orElseThrow().getAvailable());
        assertThat(available).isEqualTo(10);
    }
}
```

`SET LOCAL` và JPA Repository phải tham gia cùng transaction và cùng DataSource để dùng chung connection. `JdbcTemplate` được Spring quản lý sẽ tham gia transaction hiện tại khi nó dùng cùng DataSource với `JpaTransactionManager`.

Test không bắt exception bên trong transaction callback; exception đi ra ngoài `TransactionTemplate`, khiến transaction B rollback. Sau đó test kiểm tra SQLState của lỗi và đọc lại dữ liệu bằng transaction mới.

Chạy test:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS` và test xác nhận transaction B timeout trong khi A giữ khóa. Đây là kết quả kỳ vọng của ví dụ; chưa phải log build đã chạy trong môi trường thực tế.

## 10. Kiểm thử deadlock bằng hai transaction

Để tạo deadlock có kiểm soát, cần hai dòng và hai transaction độc lập:

- Transaction A khóa dòng 1, sau đó chờ dòng 2.
- Transaction B khóa dòng 2, sau đó chờ dòng 1.
- Latch bảo đảm cả hai đã giữ khóa đầu tiên trước khi cùng yêu cầu khóa thứ hai.

Ví dụ helper dùng cho integration test trên PostgreSQL:

```java
private String lockTwoRowsInOppositeOrder(
        Long firstId, Long secondId,
        CountDownLatch bothHoldFirst, CountDownLatch continueToSecond) {
    try {
        transactions.executeWithoutResult(status -> {
            repository.findForUpdate(firstId).orElseThrow().reserve(1);
            repository.flush();
            bothHoldFirst.countDown();
            await(continueToSecond);
            repository.findForUpdate(secondId).orElseThrow().reserve(1);
            repository.flush();
        });
        return "COMMITTED";
    } catch (RuntimeException ex) {
        if (hasSqlState(ex, "40P01")) {
            return "DEADLOCK";
        }
        throw ex;
    }
}
```

Trong test method, tạo hai Inventory với available bằng 10, sau đó chạy hai lời gọi theo thứ tự ngược nhau:

```java
CountDownLatch bothHoldFirst = new CountDownLatch(2);
CountDownLatch continueToSecond = new CountDownLatch(1);
ExecutorService pool = Executors.newFixedThreadPool(2);

try {
    Future<String> first = pool.submit(() -> lockTwoRowsInOppositeOrder(
            firstId, secondId, bothHoldFirst, continueToSecond));
    Future<String> second = pool.submit(() -> lockTwoRowsInOppositeOrder(
            secondId, firstId, bothHoldFirst, continueToSecond));

    assertThat(bothHoldFirst.await(10, TimeUnit.SECONDS)).isTrue();
    continueToSecond.countDown();

    assertThat(List.of(first.get(10, TimeUnit.SECONDS),
            second.get(10, TimeUnit.SECONDS)))
            .containsExactlyInAnyOrder("COMMITTED", "DEADLOCK");
} finally {
    continueToSecond.countDown();
    pool.shutdownNow();
}
```

Database phát hiện chu trình chờ và hủy một transaction. Transaction còn lại tiếp tục, lấy được khóa và commit. Vì mỗi transaction đã giảm một dòng trước khi yêu cầu khóa thứ hai, tổng số lượng sau test phải là 19 thay vì 20: chỉ thay đổi của transaction commit được giữ lại. Hãy đọc lại cả hai dòng trong transaction mới để xác nhận transaction nạn nhân đã rollback.

Ví dụ deadlock này phụ thuộc engine và deadlock detector. Trên PostgreSQL, kiểm tra SQLState `40P01`; với MySQL InnoDB, kiểm tra error 1213/SQLState `40001`. Đổi mã lỗi theo database đang test. Nếu chạy trên CI, dùng timeout đủ rộng và luôn nhả latch trong `finally` để không treo thread khi assertion thất bại.

## 11. Retry sau deadlock hoặc serialization failure

Deadlock thường là lỗi tạm thời có thể retry. Nhưng retry phải chạy lại toàn bộ transaction vì transaction bị database chọn làm victim đã bị rollback hoặc không còn trạng thái hợp lệ.

Quy tắc an toàn:

1. Chỉ retry những lỗi được xác định là transient, ví dụ deadlock hoặc serialization failure theo SQLState/vendor code.
2. Kết thúc transaction thất bại trước khi retry; mỗi lần thử phải có transaction mới.
3. Giới hạn số lần thử, ví dụ tối đa 2–3 lần, với exponential backoff và jitter.
4. Đảm bảo thao tác idempotent hoặc dùng idempotency key để không tạo side effect trùng.
5. Không retry lỗi validation, thiếu dữ liệu, vi phạm constraint nghiệp vụ hoặc quyền truy cập.
6. Ghi metric/log số lần retry và lỗi cuối cùng để phát hiện contention kéo dài.

Không gọi lại repository statement trong transaction đã bị đánh dấu rollback-only. Cách đơn giản là đặt retry ở một bean facade bên ngoài bean có `@Transactional`, để mỗi lần gọi worker tạo transaction mới. Cần kiểm tra thứ tự AOP giữa retry và transaction interceptor.

Ví dụ cấu trúc:

```java
@Service
public class InventoryRetryFacade {
    private final InventoryTransactionalWorker worker;

    public InventoryRetryFacade(InventoryTransactionalWorker worker) {
        this.worker = worker;
    }

    public void reserveWithRetry(Long id, int quantity) {
        int maxAttempts = 3;
        for (int attempt = 1; ; attempt++) {
            try {
                worker.reserveInNewTransaction(id, quantity);
                return;
            } catch (PessimisticLockingFailureException ex) {
                if (attempt >= maxAttempts) {
                    throw ex;
                }
                backoff(attempt);
            }
        }
    }

    private void backoff(int attempt) {
        long baseMillis = 50L * (1L << (attempt - 1));
        long jitter = java.util.concurrent.ThreadLocalRandom.current()
                .nextLong(25L);
        try {
            Thread.sleep(baseMillis + jitter);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Retry interrupted", ex);
        }
    }
}

@Service
class InventoryTransactionalWorker {
    private final InventoryRepository repository;

    InventoryTransactionalWorker(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void reserveInNewTransaction(Long id, int quantity) {
        Inventory item = repository.findForUpdate(id).orElseThrow();
        item.reserve(quantity);
    }
}
```

Đây là skeleton minh họa. Trong ứng dụng thực tế, chỉ retry exception đã phân loại là deadlock/transient; `PessimisticLockingFailureException` có thể bao gồm nhiều loại lỗi khóa khác nhau. Nếu thao tác gửi email, gọi payment provider hoặc publish message, hãy dùng outbox/idempotency để side effect không lặp khi transaction được retry.

## 12. Các yếu tố làm lock wait kéo dài

Lock wait thường không chỉ do số lượng request cao. Kiểm tra các yếu tố sau:

- Transaction giữ lock quá lâu vì thực hiện nhiều công việc sau khi đọc.
- Query thiếu index và quét nhiều dòng trước khi lấy lock.
- Hai code path khóa nhiều dòng theo thứ tự khác nhau.
- Transaction mở rộng qua nhiều Repository call hoặc nhiều service không cần thiết.
- Một batch update/delete giữ lock trên nhiều dòng.
- Isolation level hoặc gap/next-key locking làm phạm vi khóa rộng hơn dự kiến.
- Connection pool cạn khiến request khác chờ connection trước khi có thể truy cập database.
- Một transaction bị treo hoặc client mất kết nối nhưng connection/transaction chưa được giải phóng ngay.

SQL log cho biết câu query nào đang chạy; database lock monitoring cho biết session nào đang block session nào. Khi điều tra production, thu thập cả query, transaction age, lock wait event, blocking session và connection pool metric.

## 13. Khác biệt trong phạm vi rollback

Không giả định mọi database rollback cùng phạm vi khi timeout:

| Engine | Lock timeout / deadlock | Phạm vi rollback cần chú ý |
| --- | --- | --- |
| PostgreSQL | Lock timeout thường làm statement lỗi; deadlock detector hủy một transaction. | Sau lỗi SQL, transaction thường ở trạng thái aborted và phải rollback toàn transaction hoặc về savepoint. |
| MySQL InnoDB | Lock wait timeout và deadlock có mã lỗi khác nhau. | Deadlock rollback transaction nạn nhân; lock wait timeout mặc định thường rollback statement, trừ khi cấu hình `innodb_rollback_on_timeout` thay đổi hành vi. |
| SQL Server | Lock timeout và deadlock victim có error code riêng. | Deadlock victim transaction bị rollback; lock timeout thường hủy statement, trạng thái transaction còn lại phụ thuộc cấu hình và ngữ cảnh. |
| Oracle | Có `WAIT`, `NOWAIT`, `SKIP LOCKED`; deadlock báo `ORA-00060`. | Deadlock thường rollback statement gây deadlock; ứng dụng cần xử lý transaction state theo lỗi thực tế. |
| H2 | Có lock timeout đơn giản cho test. | Dùng để kiểm thử cơ bản, không suy rộng rollback semantics sang engine khác. |

Với mọi engine, sau lỗi lock hãy để transaction boundary xử lý rollback rõ ràng. Không bắt exception rồi tiếp tục thao tác trong cùng transaction nếu không hiểu trạng thái transaction và provider.

## 14. NOWAIT và SKIP LOCKED

`NOWAIT` và `SKIP LOCKED` phục vụ hai mục đích khác nhau:

| Tùy chọn | Hành vi | Trường hợp dùng |
| --- | --- | --- |
| `NOWAIT` | Không chờ nếu dòng đang bị khóa; trả lỗi ngay. | API cần phản hồi nhanh khi tài nguyên đang bận. |
| `SKIP LOCKED` | Bỏ qua dòng đang bị khóa và tiếp tục lấy dòng khác. | Worker nhiều instance cùng lấy công việc từ queue. |

Ví dụ SQL kiểu PostgreSQL:

```sql
SELECT id, status
FROM job
WHERE status = 'READY'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 20;
```

Nhiều worker có thể lấy các nhóm job khác nhau mà không chờ nhau. Tuy nhiên, `SKIP LOCKED` tạo một view không đầy đủ tại thời điểm truy vấn vì dòng đang khóa bị bỏ qua. Không dùng nó cho màn hình tìm kiếm hoặc báo cáo cần tập kết quả đầy đủ.

Khả năng biểu diễn `NOWAIT`/`SKIP LOCKED` qua JPA lock timeout hoặc Hibernate hint phụ thuộc dialect. Nếu cần đảm bảo SQL chính xác, dùng native query có kiểm soát và integration test trên database mục tiêu.

## 15. Kiểm thử trên database thực tế

H2 phù hợp với Repository test nhanh nhưng không đủ để xác nhận:

- Deadlock detector và cách chọn victim.
- Error code/SQLState của lock timeout.
- Gap/next-key lock, lock escalation và row/page lock.
- `NOWAIT`, `SKIP LOCKED` và cú pháp vendor.
- Phạm vi rollback sau lock wait timeout.
- Tác động của index và isolation level tới lock graph.

Nếu ứng dụng chạy PostgreSQL, MySQL, SQL Server hoặc Oracle, hãy thêm integration test bằng Testcontainers hoặc môi trường database chuyên dụng tương ứng. Dùng cùng version gần production và cùng schema/index/migration để kết quả có ý nghĩa.

Không chỉ assert exception class chung. Khi cần phân biệt timeout và deadlock, kiểm tra SQLState hoặc vendor error code trong cause chain, đồng thời kiểm tra dữ liệu sau khi transaction kết thúc.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@Transactional(timeout=...)` không giới hạn thời gian chờ lock như dự kiến | Transaction timeout không đồng nghĩa lock timeout của database. | Dùng JPA lock hint hoặc cấu hình vendor và test trên engine mục tiêu. |
| Query hint lock timeout không có tác dụng | Provider/dialect/database bỏ qua hoặc ánh xạ hint khác. | Xem SQL, kiểm tra phiên bản Hibernate và dùng cấu hình database được hỗ trợ. |
| Request chờ lâu trước khi SQL chạy | Connection pool hết connection. | Kiểm tra pool acquisition timeout và metric, phân biệt với database lock wait. |
| Deadlock chỉ xuất hiện dưới tải | Các code path khóa nhiều dòng theo thứ tự khác nhau. | Chuẩn hóa thứ tự khóa, giảm transaction duration và kiểm thử hai transaction cạnh tranh. |
| Retry nhưng vẫn lỗi ngay | Retry chạy bên trong transaction cũ đã rollback-only. | Đặt retry ngoài transactional worker; mỗi attempt dùng transaction mới. |
| Retry tạo đơn hoặc side effect trùng | Operation không idempotent hoặc gọi external system trước commit. | Dùng idempotency key/outbox và retry có giới hạn. |
| MySQL timeout không rollback toàn transaction | InnoDB mặc định có thể chỉ rollback statement khi lock wait timeout. | Chủ động rollback transaction trong ứng dụng hoặc cấu hình `innodb_rollback_on_timeout` theo chính sách. |
| SQL Server session giữ lock timeout cũ | `SET LOCK_TIMEOUT` tồn tại trên pooled connection. | Reset session setting hoặc quản lý cấu hình connection cẩn thận. |
| `SKIP LOCKED` làm thiếu dòng | Query cố ý bỏ qua row đang khóa. | Chỉ dùng cho queue/worker; không dùng khi cần danh sách đầy đủ. |
| H2 test qua nhưng production deadlock | Lock manager và isolation khác engine. | Chạy test bằng database production qua Testcontainers. |

## 17. Quy trình điều tra lock wait và deadlock

1. Xác định request đang chờ connection pool hay đã có SQL chờ database.
2. Thu thập SQL đang chạy, transaction age và stack trace của request.
3. Trên database, xem blocking session, blocked session, lock type và row/table/index liên quan.
4. Với deadlock, đọc deadlock graph/log để biết mỗi transaction giữ và chờ tài nguyên nào.
5. Kiểm tra query plan và index để xác định phạm vi record bị khóa.
6. So sánh thứ tự khóa giữa các code path có thể cùng cập nhật những dòng đó.
7. Kiểm tra isolation level, batch size và thời gian giữ transaction.
8. Chọn lock timeout phù hợp với latency budget và cách phản hồi của API.
9. Chỉ retry deadlock/transient error với transaction mới, số lần giới hạn và thao tác idempotent.
10. Thêm integration test tái hiện đúng kịch bản trên database mục tiêu.

## 18. Nguyên tắc thiết kế

1. Dùng `PESSIMISTIC_WRITE` khi cần khóa dòng trong thao tác đọc rồi cập nhật; luôn thực hiện trong transaction.
2. Phân biệt lock timeout, transaction timeout, query timeout và connection pool timeout.
3. Xem `jakarta.persistence.lock.timeout` là yêu cầu của provider và xác nhận database thực sự áp dụng.
4. Chọn timeout theo SLA và thời gian chờ nghiệp vụ chấp nhận được; tránh chờ vô hạn.
5. Giữ transaction ngắn, không gọi dịch vụ ngoài trong lúc giữ database lock.
6. Khóa nhiều dòng theo một thứ tự ổn định ở mọi code path.
7. Tạo index cho điều kiện lọc và kiểm tra execution plan để giảm phạm vi khóa.
8. Xử lý deadlock bằng rollback và retry toàn bộ transaction mới nếu thao tác an toàn.
9. Không retry lỗi nghiệp vụ hoặc validation; giới hạn retry và thêm backoff/jitter.
10. Dùng `NOWAIT` khi muốn thất bại nhanh; dùng `SKIP LOCKED` cho queue khi chấp nhận bỏ qua dòng đang bận.
11. Kiểm thử timeout, deadlock và rollback trên đúng database/driver production.
12. Kiểm tra SQLState/vendor code cùng dữ liệu sau commit/rollback; không chỉ assert exception message.

## 19. Checklist hoàn thành

- [ ] Phân biệt lock wait timeout, transaction timeout, query timeout và connection pool timeout.
- [ ] Dùng `@Lock(PESSIMISTIC_WRITE)` trong transaction.
- [ ] Cấu hình và kiểm chứng `jakarta.persistence.lock.timeout`.
- [ ] Giải thích được chu trình deadlock giữa hai transaction.
- [ ] Tạo test hai transaction giữ khóa theo thứ tự ngược nhau.
- [ ] Kiểm tra lock timeout bằng hai transaction độc lập.
- [ ] Nhận diện deadlock và timeout qua SQLState/vendor code.
- [ ] Biết khác biệt rollback timeout giữa PostgreSQL, MySQL, SQL Server và Oracle.
- [ ] Hiểu ảnh hưởng của index, isolation level và thứ tự khóa.
- [ ] Dùng NOWAIT/SKIP LOCKED đúng mục đích.
- [ ] Retry toàn bộ transaction mới với giới hạn và idempotency.
- [ ] Chạy integration test trên database engine production.

Khi hoàn thành, bạn có thể thiết lập thời gian chờ khóa phù hợp, tái hiện deadlock bằng integration test và xử lý khác biệt của từng database để bảo vệ transaction trong Spring Data JPA.