# Lập bộ kiểm tra hồi quy dữ liệu, giao dịch và hiệu năng trước phát hành với Spring Data JPA

## 1. Mục tiêu: xác nhận một bản nâng cấp thực sự an toàn

Nâng cấp Spring Boot, Spring Data JPA, Hibernate, JDBC driver hoặc database không chỉ là làm cho ứng dụng **biên dịch và khởi động được**. Phiên bản mới có thể tạo SQL khác, đổi cách ánh xạ `Instant`/`BigDecimal`, làm sai cascade, thay đổi thời điểm flush, tăng số truy vấn N+1, làm mất optimistic locking hoặc áp dụng migration gây mất dữ liệu.

Một bộ kiểm tra hồi quy (*regression suite*) trước phát hành phải đưa ra bằng chứng cho ba nhóm cam kết:

1. **Dữ liệu đúng:** dữ liệu cũ còn nguyên về ý nghĩa sau migration; constraint, khóa ngoại, tổng số tiền, trạng thái, enum, timestamp, sequence và kết quả query phù hợp nghiệp vụ.
2. **Giao dịch đúng:** các thay đổi liên quan cùng commit hoặc rollback; xung đột đồng thời được phát hiện hoặc điều phối; retry không nhân đôi side effect.
3. **Hiệu năng đạt chuẩn:** số SQL, độ trễ, throughput, lock wait, CPU và I/O không hồi quy vượt giới hạn được quyết định dựa trên baseline và SLO.

Các test không nên chỉ kiểm `repository.save()` trả về đối tượng khác `null`. Hãy kiểm **trạng thái database sau transaction đã kết thúc**, cả trên đường thành công lẫn khi lỗi xảy ra giữa chừng. Trường hợp lỗi ảnh hưởng tiền, dữ liệu, tính nguyên tử hoặc gây mất cập nhật phải chặn phát hành, kể cả khi tất cả HTTP endpoint vẫn trả 200.

## 2. Lập ma trận regression theo rủi ro

| Nhóm | Phép kiểm cần có | Kết quả được chấp nhận |
| --- | --- | --- |
| Schema và migration | Flyway/Liquibase từ schema cũ, DDL, FK, UNIQUE, CHECK, index, sequence | Chạy được trên bản sao database cũ; `hibernate.hbm2ddl.auto=validate` đạt |
| Dữ liệu | Count, sum, duplicate, orphan, null, decimal, enum, timezone, trạng thái | Không có sai lệch ngoài thay đổi đã được duyệt |
| JPA mapping | Entity, association, cascade, orphan removal, converter, lazy loading | Đọc/ghi qua repository vẫn bảo toàn ý nghĩa |
| Transaction | Commit, unchecked/checked exception, rollback, propagation, isolation | Không có trạng thái ghi dở; quy tắc rollback rõ ràng |
| Đồng thời | Optimistic/pessimistic lock, hai request sửa cùng record | Không lost update/double effect; lỗi xung đột xử lý được |
| SQL và latency | N+1, pagination, batching, DML dư thừa, query plan | SQL count và p50/p95/p99 đạt budget |
| Phát hành | Tương thích schema cũ/mới, backup, canary, phục hồi | Có tiêu chí dừng/tiếp tục và đầu mối nhận trách nhiệm |

Chia bộ test thành **unit**, **database integration** và **workload/performance**. Unit test xử lý logic nhanh nhưng không chứng minh SQL hay transaction. Integration test cần database thật. Benchmark lớn dùng dataset đại diện và báo cáo phân phối, không dựa vào một lần đo.

Ghi rõ trong kế hoạch: tên test, bất biến đang bảo vệ, dữ liệu đầu vào, expected result, mức chặn, thời gian chạy và artifact chứng minh. Nếu phiên bản cũ đã sai nghiệp vụ, baseline không phải chân lý; expected result phải được xác nhận theo hợp đồng domain.

## 3. Chốt baseline trước khi nâng phiên bản

Đối với mỗi release đang chạy ổn định, lưu ít nhất:

- Git commit ứng dụng, Java version, Spring Boot/Spring Data/Hibernate/JDBC driver, DB engine/version, migration version, isolation level, connection pool và các Hibernate settings ảnh hưởng SQL.
- Snapshot schema/data **nhất quán** hoặc dataset tạo lại được; số bản ghi từng bảng, số bản ghi theo trạng thái, phân bố quan hệ lớn, khóa có duplicate, tỷ lệ null, các trường edge case.
- Các truy vấn nghiệp vụ trọng tâm và kết quả: SQL shape, execution plan, SELECT/UPDATE mỗi thao tác, latency p50/p95, throughput, DB CPU/IO, lock wait, connection wait.
- Quy tắc bất biến: không âm số dư, tổng tiền không đổi qua chuyển khoản, không có orphan, order chỉ có trạng thái hợp lệ, phiên bản entity tăng khi thay đổi.
- Điều kiện đo: số người dùng đồng thời, dữ liệu, JVM warmup, query cache, index, batch size, tracing/logging, network và CPU/memory limits.

Sau khi nâng cấp, chạy cùng fixture và workload. So hai số p95 khi kích thước dữ liệu, cache, DB version hoặc thiết bị khác nhau có thể đánh lừa. Cần ghi chênh lệch và mức nhiễu; các thay đổi hợp lệ có chủ đích phải được cập nhật expected qua review.

## 4. Chuẩn bị database thử nghiệm và dữ liệu cũ

Với ứng dụng dùng PostgreSQL production, ưu tiên **Testcontainers PostgreSQL cùng họ phiên bản** cho integration test; H2 không mô phỏng đầy đủ SQL dialect, kiểu dữ liệu, MVCC, lock, index hay execution plan.

Một kế hoạch migration đúng có **hai đường kiểm**:

1. **Fresh install:** database rỗng chạy tất cả migrations đến bản mới, JPA validate schema và chạy smoke test.
2. **Upgrade thực:** khởi tạo schema/fixture ở phiên bản cũ, backup snapshot, chạy đúng các migration nâng cấp, kiểm dữ liệu, constraint và truy vấn nghiệp vụ ở phiên bản mới.

Đường thứ nhất không thể thay thế đường thứ hai: migration có thể chạy trên DB rỗng nhưng fail khi cột có null/duplicate trên dữ liệu cũ hoặc backfill không xử lý được một trạng thái hiếm.

Tạo fixture có khóa ổn định cho test, bao gồm Unicode, số tiền có phần thập phân, timestamp UTC/offset, quan hệ một-nhiều, thiếu/đủ số dư, giá trị enum cũ, null hợp lệ, cạnh tranh cùng khóa. Với bản sao production, ẩn danh dữ liệu nhạy cảm nhưng giữ cấu trúc phân bố đủ đại diện cho thống kê query plan. Các test cần reset dữ liệu giữa lần chạy, tránh phụ thuộc thứ tự test.

### Truy vấn đối soát dữ liệu

Các bảng `orders` và `customers` sau đây chỉ là **ví dụ checklist**, không liên quan đến bảng `bank_accounts` của mã chạy ở phần sau:

```sql
-- Kiểm số lượng theo trạng thái, so với snapshot trước nâng cấp.
SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status
ORDER BY status;

-- Tìm orphan trong quan hệ nghiệp vụ.
SELECT COUNT(*) AS orphan_count
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL AND c.id IS NULL;

-- Tìm duplicate theo khóa nghiệp vụ.
SELECT external_key, COUNT(*) AS occurrences
FROM orders
GROUP BY external_key
HAVING COUNT(*) > 1;

-- Đối soát số tiền bằng NUMERIC, không dùng số thực binary.
SELECT COALESCE(SUM(total_amount), 0) AS amount_total
FROM orders;

-- Bất biến business.
SELECT COUNT(*) AS invalid_count
FROM orders
WHERE total_amount < 0
   OR status NOT IN ('NEW', 'PAID', 'CANCELLED');
```

Nếu `customer_id` bắt buộc, thêm kiểm `IS NULL`: anti-join trên chỉ phát hiện khóa khác null nhưng không khớp. Kết quả đối soát phải được so với expected snapshot đã được chuẩn hóa (ví dụ loại các cột kỹ thuật sinh theo thời gian nếu hợp đồng cho phép). Một checksum toàn dump không đủ chứng minh logic vì thứ tự hàng và timestamp thay đổi.

Đối với các thay đổi khó, thêm kiểm tra riêng:

| Migration | Trường hợp hồi quy dễ bị bỏ sót |
| --- | --- |
| String → enum | Giá trị cũ không map được; null/unknown bị thay bằng giá trị khác |
| Double → decimal | Sai precision/scale, rounding, tổng cộng sau chuyển kiểu |
| Timestamp → timestamptz | Lệch UTC/offset, daylight saving, dữ liệu không có timezone gốc |
| Thêm NOT NULL/UNIQUE | Dữ liệu tồn tại có null/duplicate, migration fail hoặc xóa tùy tiện |
| Đổi/tách bảng | Orphan FK, bản ghi bị nhân do join, thứ tự ID/sequence bị lệch |
| Thêm index | Câu truy vấn vẫn seq scan trên dữ liệu lớn; chi phí ghi tăng |
| Đổi id/sequence | ID mới trùng ID cũ sau restore, ID generation hết dải hoặc lệch sequence |

Không sửa migration đã chạy ở môi trường chung chỉ để test pass. Migrations phải có version, tác động, cách backfill và kế hoạch forward recovery rõ ràng.

## 5. Ví dụ hoàn chỉnh: bộ test giao dịch trên Spring Data JPA

Ta dùng ứng dụng mẫu quản lý hai tài khoản để thể hiện đầy đủ database migration, ghi entity, rollback, optimistic locking và đo SQL. Ví dụ dành cho **Java 17+, Spring Boot 3.x, Spring Data JPA/Hibernate 6, PostgreSQL, JUnit 5, Testcontainers, Flyway**. Các file bên dưới đặt cùng package `com.example.regression`; đây là một project Spring Boot/Gradle, không phải chương trình Java SE có thể chạy bằng `javac` đơn thuần.

Ứng dụng thực tế còn cần currency, audit, idempotency key và workflow chuyển tiền; bài này chỉ trình bày fixture nhỏ để kiểm năng lực persistence của bản nâng cấp.

### 5.1. Dependencies, cấu hình và migration

Bổ sung vào `build.gradle` của project đã có plugin Spring Boot và dependency management tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.flywaydb:flyway-core'
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không ghim Hibernate/Testcontainers/Flyway vào version ngẫu nhiên khác BOM đang dùng: kiểm ma trận compatibility của bản Spring Boot trước khi nâng cấp. Với Spring Boot 3, entity import từ `jakarta.persistence`, không dùng `javax.persistence`.

File `src/main/resources/application.properties`:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
spring.flyway.enabled=true
# Test profiling mới bật:
# spring.jpa.properties.hibernate.generate_statistics=true
```

Chú ý môi trường thực tế phải cấp datasource bằng cấu hình/secret riêng; test sử dụng Testcontainers bên dưới. Không dùng `ddl-auto=update` thay migration quản lý được.

File `src/main/resources/db/migration/V1__create_bank_accounts.sql`:

```sql
CREATE TABLE bank_accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_bank_accounts_nonnegative CHECK (balance >= 0)
);
```

Với project đã tồn tại migration V1, **không thay thế V1 đã phát hành**. Hãy tạo migration mang số version tiếp theo và thực thi tập test trên schema project thực tế. Bảng này chỉ phục vụ ví dụ độc lập.

### 5.2. Entity có optimistic locking

File `src/main/java/com/example/regression/BankAccount.java`:

```java
package com.example.regression;

import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "bank_accounts")
public class BankAccount {
    @Id
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    @Version
    @Column(nullable = false)
    private Long version;

    protected BankAccount() { }

    public BankAccount(Long id, BigDecimal openingBalance) {
        if (id == null || openingBalance == null
                || openingBalance.signum() < 0) {
            throw new IllegalArgumentException("Invalid account");
        }
        this.id = id;
        this.balance = openingBalance;
    }

    public Long getId() { return id; }
    public BigDecimal getBalance() { return balance; }
    public Long getVersion() { return version; }

    public void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("Insufficient balance");
        }
        balance = balance.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        balance = balance.add(amount);
    }
}
```

Trường `@Version Long` ban đầu `null` giúp Spring Data JPA nhận diện entity mới khi dùng assigned ID (`id` đã có giá trị) và Hibernate thiết lập phiên bản lúc persist. Khi entity dirty được flush, UPDATE kiểm `version` trong điều kiện WHERE; transaction dùng version cũ sẽ không cập nhật được và bị báo lỗi optimistic lock.

File `src/main/java/com/example/regression/BankAccountRepository.java`:

```java
package com.example.regression;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BankAccountRepository
        extends JpaRepository<BankAccount, Long> { }
```

### 5.3. Service định nghĩa ranh giới transaction

File `src/main/java/com/example/regression/BankTransferService.java`:

```java
package com.example.regression;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BankTransferService {
    private final BankAccountRepository accounts;

    public BankTransferService(BankAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(Long from, Long to, BigDecimal amount) {
        moveBalances(from, to, amount);
    }

    @Transactional
    public void transferThenFail(Long from, Long to, BigDecimal amount) {
        moveBalances(from, to, amount);
        throw new IllegalStateException("Simulated failure after changes");
    }

    private void moveBalances(Long from, Long to, BigDecimal amount) {
        if (from == null || to == null || from.equals(to)
                || amount == null || amount.signum() <= 0
                || amount.scale() > 2) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        BankAccount source = accounts.findById(from).orElseThrow();
        BankAccount target = accounts.findById(to).orElseThrow();

        source.debit(amount);
        target.credit(amount);
        // Entity đang managed: Hibernate flush khi transaction commit.
    }
}
```

Các method `@Transactional` phải được gọi **qua bean Spring proxy từ bên ngoài**, như JUnit test gọi service ở phần tiếp theo. Method `moveBalances` là helper private, không cần annotation riêng. Khi `transferThenFail` ném unchecked exception, transaction rollback cả hai thay đổi.

File `src/main/java/com/example/regression/RegressionApplication.java`:

```java
package com.example.regression;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegressionApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegressionApplication.class, args);
    }
}
```

### 5.4. Integration test dùng PostgreSQL thật

File `src/test/java/com/example/regression/BankTransferRegressionTest.java`:

```java
package com.example.regression;

import java.math.BigDecimal;
import java.util.List;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceException;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
    "spring.jpa.hibernate.ddl-auto=validate",
    "spring.jpa.open-in-view=false",
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
@Testcontainers
class BankTransferRegressionTest {
    @Container
    static final PostgreSQLContainer<?> DB =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", DB::getJdbcUrl);
        registry.add("spring.datasource.username", DB::getUsername);
        registry.add("spring.datasource.password", DB::getPassword);
    }

    @Autowired BankAccountRepository accounts;
    @Autowired BankTransferService transfers;
    @Autowired EntityManagerFactory entityManagerFactory;

    @BeforeEach
    void seed() {
        accounts.deleteAllInBatch();
        accounts.saveAllAndFlush(List.of(
            new BankAccount(1L, new BigDecimal("100.00")),
            new BankAccount(2L, new BigDecimal("20.00"))
        ));
    }

    @Test
    void commitsBothSidesOfTransfer() {
        transfers.transfer(1L, 2L, new BigDecimal("30.00"));
        assertBalance(1L, "70.00");
        assertBalance(2L, "50.00");
    }

    @Test
    void rollsBackBothSidesAfterFailure() {
        assertThrows(IllegalStateException.class,
            () -> transfers.transferThenFail(
                1L, 2L, new BigDecimal("30.00")));
        assertBalance(1L, "100.00");
        assertBalance(2L, "20.00");
    }

    @Test
    void rejectsOverdraftWithoutPartialWrite() {
        assertThrows(IllegalArgumentException.class,
            () -> transfers.transfer(
                1L, 2L, new BigDecimal("200.00")));
        assertBalance(1L, "100.00");
        assertBalance(2L, "20.00");
    }

    @Test
    void rejectsStaleOptimisticWriter() {
        EntityManager first = entityManagerFactory.createEntityManager();
        EntityManager stale = entityManagerFactory.createEntityManager();

        try {
            first.getTransaction().begin();
            stale.getTransaction().begin();

            BankAccount current = first.find(BankAccount.class, 1L);
            BankAccount old = stale.find(BankAccount.class, 1L);

            current.debit(new BigDecimal("1.00"));
            first.getTransaction().commit();

            old.debit(new BigDecimal("1.00"));
            assertThrows(PersistenceException.class,
                () -> stale.getTransaction().commit());
        } finally {
            if (first.getTransaction().isActive()) {
                first.getTransaction().rollback();
            }
            if (stale.getTransaction().isActive()) {
                stale.getTransaction().rollback();
            }
            first.close();
            stale.close();
        }

        assertBalance(1L, "99.00");
    }

    @Test
    void keepsStatementCountWithinIsolatedTestBudget() {
        SessionFactory factory =
                entityManagerFactory.unwrap(SessionFactory.class);
        Statistics statistics = factory.getStatistics();

        long before = statistics.getPrepareStatementCount();
        transfers.transfer(1L, 2L, new BigDecimal("30.00"));
        long statements =
                statistics.getPrepareStatementCount() - before;

        // Budget ví dụ cho fixture hai lần SELECT và hai UPDATE
        // trong một JVM không có traffic song song.
        assertTrue(statements > 0 && statements <= 6,
                "Unexpected prepared statements: " + statements);

        assertBalance(1L, "70.00");
        assertBalance(2L, "50.00");
    }

    private void assertBalance(Long id, String expected) {
        BigDecimal actual = accounts.findById(id)
                .orElseThrow().getBalance();
        assertEquals(0, actual.compareTo(new BigDecimal(expected)));
    }
}
```

**Chạy thử** từ thư mục project có Gradle wrapper và Docker daemon:

```bash
./gradlew test --tests com.example.regression.BankTransferRegressionTest
```

Trên PowerShell dùng `.\gradlew.bat test --tests com.example.regression.BankTransferRegressionTest`. JUnit báo kết quả assertion; không có stdout cố định về latency hay số SQL cần chép trước khi chạy. Một lần chạy hoàn chỉnh sẽ khởi động PostgreSQL container, Flyway chạy SQL migration, Hibernate validate schema rồi thực thi các ca.

**Chi tiết quan trọng:** không gắn `@Transactional` vào class test này: nếu test tự bao một transaction thì có thể che việc service thực sự commit hay rollback. Hai `EntityManager` ở ca optimistic locking được tạo riêng và mỗi cái có transaction resource-local độc lập; nếu transaction thứ hai cố commit dữ liệu stale, JPA/Hibernate có thể ném `OptimisticLockException` hoặc bọc trong `RollbackException` (đều thuộc họ `PersistenceException`). Nếu thay provider/version và exception hierarchy khác, kiểm root cause và trạng thái DB để xác định lỗi optimistic lock; không chỉ kiểm chuỗi message.

## 6. Bổ sung test giao dịch cho trường hợp thực tế

Các test trên là hạt nhân, còn release thực tế cần xét thêm:

| Tình huống | Thiết lập | Hành vi bắt buộc |
| --- | --- | --- |
| Checked exception | Method có `@Transactional` ném checked exception sau khi sửa entity | Xác nhận `rollbackFor` đúng; Spring mặc định không rollback tất cả checked exceptions |
| `REQUIRES_NEW` | Giao dịch con commit, giao dịch ngoài fail | Cam kết độc lập là chủ đích; nếu muốn atomic phải thiết kế lại |
| Gọi nội bộ cùng bean | `this.methodAnnotatedTransactional()` | Biết self-invocation thường không đi qua proxy |
| Optimistic contention | Hai transaction đọc cùng `@Version` rồi ghi | Một ghi thành công, cập nhật stale bị phát hiện, retry có kiểm soát nếu cần |
| Pessimistic lock | Hai transaction khóa cùng hàng | Không có deadlock vĩnh viễn; timeout/ordering được kiểm |
| Isolation | Cạnh tranh đọc/ghi dưới READ COMMITTED hoặc REPEATABLE READ | Hành vi nhất quán với domain và DB thật |
| Bulk JPQL/native update | Bulk sửa hàng đã load thành entity managed | Xử lý stale persistence context/`@Version`/cache rõ ràng |
| Cascade và orphan removal | Thêm/xóa child với FK/UNIQUE | Cả hai đầu quan hệ đúng sau flush và commit |
| Retry sau deadlock | Tạo lỗi transient, thực hiện lại có giới hạn | Không nhân đôi giao dịch hay side effect |
| Outbox/event | Lỗi xảy ra trước commit hoặc sau commit nhưng trước publish | Không phát event về state chưa commit; có cơ chế phục hồi việc publish |

`@Transactional(readOnly = true)` có thể điều chỉnh flush/tracking theo provider, nhưng không nên coi là quyền cấm ghi DB tuyệt đối. Test khi method đọc vô tình làm dirty entity hoặc chạy bulk DML, đặc biệt sau nâng cấp. Chú ý mặc định `@Transactional` rollback khi unchecked exception; checked exception cần chính sách cụ thể, không phỏng đoán.

Với concurrency test, cho mỗi thread gọi service **qua bean** để có transaction riêng; đồng bộ thời điểm bằng `CountDownLatch`/barrier và timeout hữu hạn. Không dùng `Thread.sleep` may rủ để giả lập race. Sau hai lần commit/rollback, đọc DB bằng transaction mới để phát hiện lost update. Optimistic locking chỉ **báo lỗi**, không tự retry cho người dùng.

## 7. Hồi quy performance: không chỉ đo thời gian chạy test

Một regression suite cần phân biệt **SQL count gate** và **performance benchmark**.

### 7.1. SQL count/shape ở integration test

Trong test cô lập có Hibernate statistics, có thể đo hiệu số `Statistics.getPrepareStatementCount()` trước/sau một service call. Đây là số lần prepared statement theo Hibernate, gồm SELECT/INSERT/UPDATE, không phải số record hay số round-trip chính xác. Không gọi `statistics.clear()` trên SessionFactory production có traffic, vì counter dùng chung.

Bổ sung test cho các truy vấn sau:

- Tải danh sách 100 order có một association: kiểm không phát 101 SELECT do N+1 khi truy cập từng child.
- Phân trang và sort: số entity/result đúng, không fetch collection làm pagination trong bộ nhớ.
- Cập nhật một entity: tránh vòng lặp `saveAndFlush` gây nhiều flush; phân biệt `saveAll` với JDBC batching thực sự.
- Bulk JPQL/native DML: số SQL và số hàng bị ảnh hưởng; bulk thường bypass dirty checking và không tự xử lý `@Version` như update managed entity.
- Lazy/eager fetch: kiểm cả dữ liệu và số SQL. `@EntityGraph`, `JOIN FETCH` hoặc DTO projection là các lựa chọn, nhưng cần xét cardinality/duplication và memory thay vì bật EAGER mọi association.

### 7.2. Benchmark trước phát hành trên dữ liệu đại diện

Tải với dataset đủ lớn, warmup JVM/pool/cache, chạy nhiều vòng ở các mức concurrency; báo p50/p95/p99, throughput, error rate, CPU, allocations, GC, DB buffers, lock wait, connection wait và SQL count. Đánh giá chênh lệch trên **cùng** driver/DB/data/index/infra. Một lần test timeout 200 ms trong CI shared runner không đủ kết luận hiệu năng.

Ví dụ cách đặt gate (các ngưỡng **minh họa**, phải thay bằng SLO/baseline của project):

| Metric | Baseline ví dụ | Quy tắc minh họa |
| --- | ---: | --- |
| p95 endpoint tìm kiếm | 180 ms | ≤ 216 ms; tăng quá 20% cần điều tra/chặn tùy SLO |
| SQL SELECT cho một thao tác | 4 | ≤ 5; tăng lên 100 là dấu hiệu N+1 |
| Throughput import | 2.000 bản ghi/phút | ≥ 1.800 bản ghi/phút |
| Lỗi mất cập nhật/chênh lệch số tiền | 0 | 0, chặn release |
| Migration làm rơi bản ghi hợp lệ | 0 | 0, chặn release |

Với PostgreSQL, phân tích query plan bằng `EXPLAIN (ANALYZE, BUFFERS)` trên staging có dữ liệu đại diện. `EXPLAIN ANALYZE` **thực thi câu SQL**, bao gồm DML, nên không chạy UPDATE/DELETE với ANALYZE trên production tùy tiện. Nếu đã bật `pg_stat_statements`, kết hợp latency và buffer metrics để tìm hồi quy query shape/index. Cần phân biệt độ trễ query với thời gian auto-flush có thể xảy ra trước query.

## 8. Các điểm dễ sai khi nâng Spring Data JPA/Hibernate

- **`javax` → `jakarta`:** khi lên Spring Boot 3/Hibernate 6, cập nhật import entity/validation và phụ thuộc liên quan. Kiểm native query/dialect, tên bảng/cột, sequence.
- **Kiểu dữ liệu:** decimal scale, enum representation, UUID, JSON, `Instant`/`LocalDateTime`/`OffsetDateTime` và timezone. Đọc lại dữ liệu từ DB mới để kiểm ý nghĩa.
- **Flush/dirty checking:** một lần `flush()` có thể không có UPDATE; `saveAndFlush` trong vòng lặp có thể làm tăng SQL/round-trips; đo cả count và thời gian.
- **`@Version` và bulk DML:** JPQL/native bulk update không tự tăng version hoặc làm mới entity đang managed; thêm điều kiện version/clear/refresh khi cần.
- **ID generation:** sequence allocation, identity strategy, insert batching, sequence lệch sau restore.
- **Cascade/collection:** orphanRemoval và FK có thể bộc lộ lỗi do thay đổi thứ tự flush, nhất là khi chuyển child giữa parent.
- **Query shape:** DISTINCT, FETCH JOIN, pagination, sorting, null comparison, equality, projection. Thay đổi SQL có thể làm query plan khác dù kết quả đúng.
- **Transaction:** checked exception, self invocation, `REQUIRES_NEW`, isolation, read-only hint, retry. Cần test commit thực tế để xác nhận.
- **Cache:** second-level/query cache có thể giữ dữ liệu cũ sau bulk update; nếu bật cache phải kiểm invalidation.
- **Database version:** driver/dialect và schema index/constraint có thể thay đổi; test trên DB thật tương đương môi trường triển khai.

Không sửa expected của test chỉ vì Hibernate sinh SQL mới. Nếu SQL mới vẫn đúng nhưng chậm, phải điều tra planner/index và đo baseline; nếu thay đổi hành vi có chủ đích, ghi rõ migration, logic và quyết định chấp thuận.

## 9. Các cổng CI/CD trước phát hành

Quy trình đề xuất:

1. **Compile + unit:** kiểm code Java, validation và business rules.
2. **Migration from old schema:** khởi tạo schema/dữ liệu của bản trước, chạy migration mới, kiểm count/sum/duplicate/orphan, schema validation.
3. **JPA integration:** repository queries, entity mapping, FK, rollback, optimistic locking, SQL count trên Testcontainers.
4. **Staging performance:** workload đại diện, query plans, latency/throughput/DB resources so với baseline.
5. **Release readiness:** backup/restore drill, rolling schema compatibility, kế hoạch canary và alert.

Ví dụ GitHub Actions dành cho project Gradle có sẵn wrapper:

```yaml
name: JPA regression
on:
  pull_request:
  workflow_dispatch:

jobs:
  jpa-regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: PostgreSQL integration tests
        run: ./gradlew --no-daemon test --tests "com.example.regression.BankTransferRegressionTest"
```

Workflow trên minh họa job integration riêng với Testcontainers; **chưa thay thế** pipeline restore schema cũ hoặc benchmark. Điều chỉnh module path/Java version theo build thực tế, tách database giữa các job, tránh test song song gây nhiễu `Statistics`. Lưu artifact theo commit SHA gồm JUnit report, schema/migration version, dữ liệu fixture, SQL/plan diff, benchmark và quyết định gate.

## 10. Rolling release, canary và phục hồi

Trước phát hành cần kiểm sự tương thích của database với **phiên bản ứng dụng cũ và mới** trong lúc rolling deployment. Ưu tiên **expand → backfill/migrate → switch → contract**: thêm cột/bảng tương thích trước, cho hai phiên bản chạy, chuyển luồng ghi/đọc, cuối cùng mới bỏ cột cũ khi không còn consumer.

Trên PostgreSQL, một số DDL/index có thể khóa bảng; đánh giá thời gian lock/backfill, statement timeout và cách tạo index concurrent khi thích hợp. `CREATE INDEX CONCURRENTLY` có yêu cầu transaction riêng và phải phối hợp với công cụ migration.

Canary theo dõi ít nhất lỗi ứng dụng, deadlocks, optimistic-lock failures, SQL/query count, p95/p99, DB CPU/IO, connection pool, background jobs và các bất biến dữ liệu. Nếu phát hiện orphan/duplicate/tiền lệch, transaction partial write hoặc regression vượt mức blocking, dừng rollout.

**Rollback ứng dụng không đồng nghĩa rollback schema.** Migration phá hủy cột hoặc chuyển kiểu không đảo ngược dễ dàng có thể làm binary cũ không chạy được. Vì vậy cần backup có thử restore, cửa sổ rollback rõ ràng, script forward-fix/compensation được duyệt và khả năng chạy lại test trên state đã phục hồi.

## 11. Checklist hoàn tất regression suite

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Có baseline tái lập được? | Ghi commit, phiên bản DB/ORM, schema, dữ liệu, workload, SLO và artifacts |
| Đã nâng từ schema cũ có dữ liệu? | Migration/constraint/sequence/backfill đạt; SQL đối soát đúng |
| JPA mapping còn đúng? | Repo query, flush, cascade, lazy, converter, pagination qua DB thật |
| Transaction có nguyên tử? | Lỗi sau khi sửa nhiều entity rollback tất cả; kiểm DB sau kết thúc |
| Đồng thời được bảo vệ? | Không lost update, xung đột version/locking được xử lý có chủ đích |
| Không có performance regression? | SQL budget, plan, p95/p99/throughput đạt ngưỡng đã chọn |
| Gate phát hành đủ mạnh? | Test blocking chặn build/deploy, log/report lưu cùng release |
| Có thể dừng và phục hồi? | Canary, backup/restore, compatibility và forward-fix đã diễn tập |

**Kết luận:** Một bộ kiểm tra hồi quy Spring Data JPA trước phát hành kết nối **dữ liệu lịch sử**, **hành vi transaction** và **chi phí SQL/database** trong cùng quy trình có bằng chứng. Chỉ khi schema nâng cấp, bất biến dữ liệu, concurrency, query budget, benchmark và kế hoạch phục hồi đều được kiểm mới đủ cơ sở để quyết định phát hành.
