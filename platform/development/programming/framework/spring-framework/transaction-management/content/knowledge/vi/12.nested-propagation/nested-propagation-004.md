# Hành vi khi chưa tồn tại giao dịch bên ngoài — NESTED và savepoint

## 1. Điều cốt lõi cần trả lời

Khi Spring Framework gặp một lời gọi vào method được khai báo `@Transactional(propagation = Propagation.NESTED)`, Spring trước hết phải xét **tại điểm gọi đã có transaction vật lý bên ngoài chưa**.

- **Chưa có outer transaction:** `NESTED` mở **một physical transaction mới**, rồi commit khi method hoàn tất bình thường, hoặc rollback toàn transaction khi một exception phù hợp rollback rule thoát ra. **Không có savepoint lồng trong transaction cũ** vì không hề có transaction cũ.
- **Đã có outer transaction JDBC phù hợp:** `NESTED` chia sẻ **cùng physical transaction** và tạo **savepoint** cho logical scope bên trong. Khi inner thất bại, có thể rollback về savepoint và để outer tiếp tục. Inner hoàn tất bình thường không đồng nghĩa tự commit độc lập: outer vẫn quyết định commit cuối.
- **Có outer nhưng manager/driver không hỗ trợ savepoint:** không được giả định nested sẽ hoạt động. Spring có thể báo `NestedTransactionNotSupportedException` hoặc lỗi từ JDBC.
- **Không đi qua Spring proxy:** annotation ở method inner có thể không được transaction interceptor xử lý, dù source code có `@Transactional`.

Từ đó, câu trả lời chính xác cho “**Hành vi khi chưa tồn tại giao dịch bên ngoài**” là: **`NESTED` khởi tạo transaction như `REQUIRED` khi chưa có transaction; nó không yêu cầu phải có outer, cũng không tự tạo một savepoint độc lập.** Hành vi “bắt buộc có transaction ngoài” là của `MANDATORY`, không phải `NESTED`.

### Bảng quyết định ngắn

| Tình huống | Physical transaction | Savepoint | Ai commit / rollback? |
| --- | --- | --- | --- |
| NESTED qua proxy, **chưa có outer** | Bắt đầu T1 mới | Không | Inner proxy hoàn tất T1 |
| NESTED qua proxy, **có outer T1** và JDBC hỗ trợ | Dùng chung T1 | Có, tại đầu inner scope | Outer hoàn tất T1; inner có thể rollback cục bộ |
| NESTED khi có outer nhưng không hỗ trợ nested | Không thể thực thi savepoint như yêu cầu | Không có savepoint hợp lệ | Phải xử lý lỗi cấu hình / khả năng DB |
| `this.inner()` không đi qua proxy | Không tự áp annotation inner | Không tự tạo | Phụ thuộc transaction có sẵn, nếu có |

Đây là bài học về **propagation và transaction scope**, không phải giới thiệu một cú pháp Java riêng. Phần thực hành ở dưới dùng JDBC và H2 để kiểm tra trực tiếp trạng thái `isNewTransaction` và `hasSavepoint`.

## 2. Savepoint không phải transaction độc lập

### Transaction, logical scope và savepoint

**Physical transaction** là giao dịch database thực sự: các thao tác SQL thuộc một connection/resource transaction, và database đảm bảo commit/rollback cho nó.

**Logical transaction scope** là phạm vi do Spring transaction interceptor quản lý khi một method transactional được gọi qua proxy. Nhiều logical scope có thể dùng chung một physical transaction.

**Savepoint** là vị trí đánh dấu **trong** một transaction đang mở. Nó cho phép rollback một phần mà vẫn giữ các thao tác trước điểm đánh dấu trong cùng transaction. Savepoint không phải một transaction thứ hai với commit độc lập.

Ví dụ SQL minh họa khi **có outer**:

~~~sql
BEGIN;

UPDATE account_balance SET amount = amount + 10 WHERE id = 1;

SAVEPOINT inner_start;
UPDATE account_balance SET amount = amount + 10 WHERE id = 2;

ROLLBACK TO SAVEPOINT inner_start;
-- UPDATE cho id=2 bị hoàn tác, id=1 vẫn có thay đổi chưa commit.

UPDATE account_balance SET amount = amount + 10 WHERE id = 1;
COMMIT;
~~~

Ở Spring/JDBC, transaction manager thường làm việc qua API `Connection.setSavepoint()` và rollback tới savepoint thay vì yêu cầu developer tự gửi các câu SQL này. Đây chỉ là mô tả ý nghĩa, không phải lệnh phải nhúng thủ công vào code đang chạy `@Transactional`.

Khi **không có outer transaction**, lưu đồ đúng là:

~~~text
Lời gọi qua Spring proxy @Transactional(NESTED)
             |
             v
Có physical transaction phù hợp đang hoạt động không?
             |
             +-- KHÔNG
             |      |
             |      +-- Mở transaction T1 mới
             |      +-- Thực thi method trong T1
             |      +-- Thành công ------> COMMIT T1
             |      +-- Lỗi cần rollback -> ROLLBACK T1
             |
             +-- CÓ, manager hỗ trợ JDBC savepoint
                    |
                    +-- Tạo SAVEPOINT S1 trong T1
                    +-- Chạy body method trong T1
                    +-- Thành công -> hoàn tất scope S1
                    +-- Lỗi cần rollback -> ROLLBACK TO S1
                    +-- Outer vẫn quyết định COMMIT/ROLLBACK T1
~~~

Không được diễn giải `NESTED` như “luôn có transaction con T2”. Nó chỉ tạo **physical transaction mới khi thiếu transaction hiện hữu**; lúc tham gia outer thì chủ yếu là **savepoint trong cùng T1**, khác `REQUIRES_NEW`.

### Vì sao không có outer thì không thể rollback về savepoint của outer?

Một savepoint phải thuộc về transaction. Nếu chưa có T1, không tồn tại vị trí “trước khi vào inner” trong T1 để quay lại. Spring thay vì tạo một savepoint tưởng tượng sẽ **bắt đầu T1 mới**, rồi rollback cả T1 nếu method thất bại.

Cách hiểu này giải thích tại sao cùng một annotation có hai ngữ nghĩa quan sát được:

- `NESTED` standalone: `isNewTransaction() = true` và `hasSavepoint() = false`.
- `NESTED` tham gia outer JDBC: `isNewTransaction() = false` và `hasSavepoint() = true`.

Các giá trị trên dành cho **transaction manager JDBC kiểu DataSourceTransactionManager** trong bài lab, không phải cam kết về mọi transaction manager custom.

## 3. So sánh các propagation khi không có outer

| Propagation | Khi **không** có transaction ngoài | Khi **đã có** transaction ngoài |
| --- | --- | --- |
| `REQUIRED` | Bắt đầu transaction mới | Tham gia transaction hiện có; thường không tạo savepoint mới |
| **`NESTED`** | **Bắt đầu transaction mới**, không cần savepoint | Cùng physical transaction, có savepoint nếu được hỗ trợ |
| `REQUIRES_NEW` | Bắt đầu transaction mới | Tạm suspend outer và tạo transaction **độc lập** |
| `MANDATORY` | Báo lỗi vì không có transaction | Tham gia transaction hiện có |
| `SUPPORTS` | Không yêu cầu bắt đầu transaction mới | Tham gia transaction hiện có |
| `NOT_SUPPORTED` | Chạy không có transaction | Suspend outer rồi chạy không transaction khi được hỗ trợ |

Trong trường hợp **không có outer**, `REQUIRED`, `NESTED` và `REQUIRES_NEW` đều có thể **bắt đầu một transaction mới**. Vì vậy nhìn test chỉ kiểm tra “có transaction hay không” không phân biệt được cả ba. Muốn thấy sự khác nhau, phải thử **có outer** và kiểm tra savepoint/independent commit.

Sự khác nhau quan trọng khi **có outer**:

1. **`REQUIRED`** inner thất bại và yêu cầu rollback có thể đánh dấu **shared transaction rollback-only**. Outer catch exception nhưng vẫn có thể gặp `UnexpectedRollbackException` khi cố commit.
2. **`NESTED`** inner có savepoint; nếu lỗi phù hợp rollback rule xảy ra và rollback về savepoint thành công, outer có thể **tiếp tục rồi commit** phần còn hợp lệ.
3. **`REQUIRES_NEW`** inner là transaction khác T2. T2 commit rồi thì outer T1 rollback **không tự hoàn tác T2**; nhưng việc dùng connection khác, lock và pool capacity cần được cân nhắc.

Không nên tự động thay `NESTED` bằng `REQUIRES_NEW` khi gặp lỗi không hỗ trợ savepoint. Hai lựa chọn này khác nhau về **bất biến dữ liệu**.

## 4. Thử bằng hai tài khoản: không outer và có outer

Giả sử bảng `account_balance` có:

| Tài khoản | id | Giá trị gốc |
| --- | ---: | ---: |
| A | 1 | 100 |
| B | 2 | 200 |

Method được gọi qua proxy:

~~~java
@Transactional(propagation = Propagation.NESTED)
public void add(long id, long delta, boolean fail) {
    // UPDATE amount = amount + delta
    // Nếu fail thì throw IllegalStateException.
}
~~~

Đoạn này là snippet giải thích API, chưa phải class chạy riêng; project runnable sẽ hiện đầy đủ ở phần 6.

### Trường hợp A — Gọi NESTED hai lần mà caller không transactional

~~~text
NonTransactionalCoordinator.runTwoSteps()
    |
    +-- nested.add(A,+10,false)
    |     không có outer -> MỞ T1 -> COMMIT T1
    |     A đã lưu thành 110
    |
    +-- nested.add(B,+10,true)
          vẫn không có outer -> MỞ T2
          B tạm thành 210
          ném RuntimeException -> ROLLBACK toàn T2
          B trở lại 200

Giá trị sau khi caller nhận exception:
A = 110, B = 200
~~~

Đây là hệ quả cực kỳ quan trọng: **hai method NESTED gọi liên tiếp không tự tạo một “giao dịch cha vô hình”**. Method thứ nhất đã commit trước khi method thứ hai bắt đầu. Nếu workflow yêu cầu cả hai bước cùng thành công hoặc thất bại, cần một service facade có `@Transactional` bao cả hai bước.

### Trường hợp B — Gọi NESTED trong outer @Transactional

~~~text
OuterService.absorbNestedErrorAndCommit()
    |
    +-- MỞ T1
    +-- UPDATE A +10  (A đang 110 trong T1)
    |
    +-- nested.add(B,+10,true)
    |     NESTED có outer -> SAVEPOINT S1 trong T1
    |     UPDATE B +10  (B tạm 210)
    |     throw IllegalStateException
    |     ROLLBACK TO S1  (B trở về 200)
    |
    +-- Outer catch đúng exception thử nghiệm
    +-- UPDATE A +10  (A đang 120 trong T1)
    +-- COMMIT T1

Giá trị persisted: A = 120, B = 200
~~~

Ở đây savepoint chỉ hoàn tác cập nhật B của inner; các thao tác trước/sau của outer vẫn được commit nếu mọi ràng buộc khác cho phép.

### Trường hợp C — Inner hoàn tất bình thường, outer gặp lỗi

~~~text
OUTER T1:
  UPDATE A +10
  NESTED tạo S1
  INNER: UPDATE B +10 thành công
  Inner trả về bình thường (KHÔNG commit vật lý riêng)
  OUTER ném RuntimeException
  ROLLBACK toàn T1

Giá trị persisted: A = 100, B = 200
~~~

Khi có outer, một inner NESTED “thành công” chỉ có nghĩa nó chưa rollback ở scope inner. Nó **không giữ được kết quả khi outer rollback**.

## 5. Đo transaction status thay vì đoán từ annotation

Spring cung cấp `TransactionAspectSupport.currentTransactionStatus()` trong phạm vi transaction interceptor hiện tại. Trong một method được gọi qua proxy, có thể lấy:

~~~java
TransactionStatus tx =
    TransactionAspectSupport.currentTransactionStatus();

boolean newTransaction = tx.isNewTransaction();
boolean hasSavepoint = tx.hasSavepoint();
~~~

Snippet này cần imports và method context; code đầy đủ bên dưới.

| Lời gọi trong lab JDBC | `isNewTransaction()` | `hasSavepoint()` | Ý nghĩa |
| --- | --- | --- | --- |
| `nested.observe()` không có outer | `true` | `false` | Chính inner mở physical transaction |
| `outer.observeNestedWithinOuter()` gọi `nested.observe()` | `false` | `true` | Inner tham gia physical transaction outer và dùng savepoint |

Có thể kiểm tra thêm `TransactionSynchronizationManager.isActualTransactionActive()`; ở cả hai trường hợp nó phải báo `true`. Nhưng chỉ có `active=true` là chưa đủ để chứng minh savepoint có tồn tại hay không.

**Giới hạn:** `currentTransactionStatus()` phải được gọi từ một invocation mà interceptor đang quản lý; ngoài context nó có thể báo lỗi. Các giá trị quan sát chỉ có ý nghĩa khi app dùng đúng transaction manager, Spring proxy và resource. Bài lab không coi `TransactionStatus` là dữ liệu nghiệp vụ cần lưu.

## 6. Bài lab hoàn chỉnh: Java 17, Spring Boot, JDBC, H2, JUnit

Bài thực hành dùng **Spring Boot 3.5.0**, Java 17+, Spring JDBC, H2 in-memory và JUnit 5. Không cần cài database server riêng. Ta khai báo **một DataSourceTransactionManager** cho cùng DataSource của `JdbcTemplate`, bật rõ `nestedTransactionAllowed`, và kiểm tra tám tình huống.

Cấu trúc tệp:

~~~text
nested-no-outer-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/nestedlab/
    │   │   ├── NestedLabApplication.java
    │   │   ├── TxSnapshot.java
    │   │   ├── NestedService.java
    │   │   ├── OuterService.java
    │   │   └── NonTransactionalCoordinator.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/nestedlab/
            └── NestedTransactionTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>nested-no-outer-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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
</project>
~~~

### 6.2. application.properties và schema.sql

Tệp `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:nested_no_outer_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE account_balance (
    id BIGINT PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

Dữ liệu được reset và chèn trong `@BeforeEach` ở test, để không test nào phụ thuộc thứ tự của test khác. H2 chỉ là database demo trong bộ nhớ JVM.

### 6.3. NestedLabApplication.java

Tệp `src/main/java/com/example/nestedlab/NestedLabApplication.java`:

~~~java
package com.example.nestedlab;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class NestedLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedLabApplication.class, args);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
        manager.setNestedTransactionAllowed(true);
        return manager;
    }
}
~~~

Spring Boot có thể tự cấu hình manager cho JDBC khi điều kiện phù hợp, nhưng lab này khai báo rõ **một bean transaction manager** để không mơ hồ về cơ chế nested. `DataSourceTransactionManager` triển khai nested qua JDBC savepoints khi có outer và driver hỗ trợ. Cấu hình `setNestedTransactionAllowed(true)` không tự biến một database không hỗ trợ savepoint thành hỗ trợ; H2 dùng trong bài thực hành có tính năng này.

`PlatformTransactionManager` ở đây thực hiện transaction trên cùng `DataSource` mà `JdbcTemplate` sử dụng, nên các JDBC updates trong service tham gia đúng transaction.

### 6.4. TxSnapshot.java

Tệp `src/main/java/com/example/nestedlab/TxSnapshot.java`:

~~~java
package com.example.nestedlab;

public record TxSnapshot(
    boolean active,
    boolean newTransaction,
    boolean hasSavepoint
) {}
~~~

Record Java 17 này ghi lại thông tin Spring transaction context tại thời điểm gọi. **Đừng nhầm với MVCC snapshot** của database.

### 6.5. NestedService.java

Tệp `src/main/java/com/example/nestedlab/NestedService.java`:

~~~java
package com.example.nestedlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class NestedService {
    private final JdbcTemplate jdbc;

    public NestedService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public TxSnapshot observe() {
        TransactionStatus tx =
            TransactionAspectSupport.currentTransactionStatus();
        return new TxSnapshot(
            TransactionSynchronizationManager.isActualTransactionActive(),
            tx.isNewTransaction(),
            tx.hasSavepoint()
        );
    }

    @Transactional(propagation = Propagation.NESTED)
    public void add(long id, long delta, boolean failAfterUpdate) {
        int affected = jdbc.update(
            "UPDATE account_balance SET amount = amount + ? WHERE id = ?",
            delta, id
        );
        if (affected != 1) {
            throw new IllegalStateException("Missing account " + id);
        }
        if (failAfterUpdate) {
            throw new IllegalStateException("nested deliberate failure");
        }
    }
}
~~~

Lệnh cập nhật được thực hiện **trước** khi cố tình ném lỗi. Do đó rollback thật sự phải hoàn tác một giá trị đã bị thay đổi trung gian. Không chỉ test lỗi Java khi chưa có SQL nào chạy.

- Không có outer: `observe()` cho `active=true`, `newTransaction=true`, `hasSavepoint=false`. `add(...)` thành công commit một transaction mới; ném runtime exception thì rollback toàn transaction ấy.
- Có outer: `observe()` cho `active=true`, `newTransaction=false`, `hasSavepoint=true`. `add(...)` thất bại được rollback về savepoint khi driver còn khả năng tiếp tục, để outer có thể quyết định bước tiếp theo.

### 6.6. OuterService.java

Tệp `src/main/java/com/example/nestedlab/OuterService.java`:

~~~java
package com.example.nestedlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final NestedService nested;
    private final JdbcTemplate jdbc;

    public OuterService(NestedService nested, JdbcTemplate jdbc) {
        this.nested = nested;
        this.jdbc = jdbc;
    }

    @Transactional
    public TxSnapshot observeNestedWithinOuter() {
        return nested.observe();
    }

    @Transactional
    public void absorbNestedErrorAndCommit() {
        addToA(10L);

        try {
            nested.add(2L, 10L, true);
        } catch (IllegalStateException ex) {
            if (!"nested deliberate failure".equals(ex.getMessage())) {
                throw ex;
            }
            // Inner đã rollback đến savepoint; outer tiếp tục.
        }

        addToA(10L);
    }

    @Transactional
    public void bothSuccessful() {
        addToA(10L);
        nested.add(2L, 10L, false);
    }

    @Transactional
    public void failAfterNestedSuccess() {
        addToA(10L);
        nested.add(2L, 10L, false);
        throw new IllegalStateException("outer deliberate failure");
    }

    private void addToA(long delta) {
        int affected = jdbc.update(
            "UPDATE account_balance SET amount = amount + ? WHERE id = ?",
            delta, 1L
        );
        if (affected != 1) {
            throw new IllegalStateException("Account A missing");
        }
    }
}
~~~

`NestedService` và `OuterService` là hai beans khác nhau, nên lời gọi `nested.observe()`/`nested.add(...)` đi **qua proxy Spring**, không phải self-invocation `this.method()`.

- `absorbNestedErrorAndCommit()`: A tăng hai lần trong outer transaction, B được cập nhật trong nested scope rồi rollback về savepoint do exception, outer có thể commit A=120, B=200.
- `bothSuccessful()`: outer A+10, nested B+10, outer commit cả hai; A=110, B=210.
- `failAfterNestedSuccess()`: inner B+10 hoàn tất bình thường nhưng không commit riêng, outer ném lỗi và rollback toàn transaction; A=100, B=200.

**Không catch và nuốt mọi exception của database trên production.** Lab chỉ bắt chính xác lỗi Java cố tình chèn sau một UPDATE hợp lệ, để connection/transaction còn sử dụng an toàn.

### 6.7. NonTransactionalCoordinator.java

Tệp `src/main/java/com/example/nestedlab/NonTransactionalCoordinator.java`:

~~~java
package com.example.nestedlab;

import org.springframework.stereotype.Service;

@Service
public class NonTransactionalCoordinator {
    private final NestedService nested;

    public NonTransactionalCoordinator(NestedService nested) {
        this.nested = nested;
    }

    // Không có @Transactional ở coordinator.
    public void runTwoSteps() {
        nested.add(1L, 10L, false); // T1 tự mở, commit.
        nested.add(2L, 10L, true);  // T2 tự mở, rollback.
    }
}
~~~

Đây là phản chứng: mặc dù cả hai `add(...)` có annotation NESTED, **không có transaction bên ngoài** nào bao toàn bộ `runTwoSteps()`. Bước đầu đã commit trước khi bước thứ hai thất bại. Sau lỗi, A vẫn 110 và B trở về 200.

### 6.8. NestedTransactionTest.java — tám phép thử

Tệp `src/test/java/com/example/nestedlab/NestedTransactionTest.java`:

~~~java
package com.example.nestedlab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class NestedTransactionTest {
    @Autowired
    private NestedService nested;

    @Autowired
    private OuterService outer;

    @Autowired
    private NonTransactionalCoordinator nonTx;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM account_balance");
        jdbc.update(
            "INSERT INTO account_balance(id, amount) VALUES (?, ?)",
            1L, 100L
        );
        jdbc.update(
            "INSERT INTO account_balance(id, amount) VALUES (?, ?)",
            2L, 200L
        );
    }

    private long amount(long id) {
        Long value = jdbc.queryForObject(
            "SELECT amount FROM account_balance WHERE id = ?",
            Long.class, id
        );
        if (value == null) {
            throw new AssertionError("Missing account " + id);
        }
        return value;
    }

    @Test
    void withoutOuterNestedStartsNewTransactionNotSavepoint() {
        TxSnapshot s = nested.observe();

        assertTrue(s.active());
        assertTrue(s.newTransaction());
        assertFalse(s.hasSavepoint());
    }

    @Test
    void withOuterNestedCreatesSavepointNotPhysicalTransaction() {
        TxSnapshot s = outer.observeNestedWithinOuter();

        assertTrue(s.active());
        assertFalse(s.newTransaction());
        assertTrue(s.hasSavepoint());
    }

    @Test
    void standaloneNestedSuccessCommits() {
        nested.add(1L, 10L, false);

        assertEquals(110L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void standaloneNestedFailureRollsBackWholeTransaction() {
        assertThrows(
            IllegalStateException.class,
            () -> nested.add(1L, 10L, true)
        );

        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void consecutiveStandaloneNestedCallsAreNotOneTransaction() {
        assertThrows(
            IllegalStateException.class,
            nonTx::runTwoSteps
        );

        assertEquals(110L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void nestedFailureRollsBackToSavepointOuterStillCommits() {
        outer.absorbNestedErrorAndCommit();

        assertEquals(120L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void nestedSuccessDoesNotSurviveOuterRollback() {
        assertThrows(
            IllegalStateException.class,
            outer::failAfterNestedSuccess
        );

        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void nestedAndOuterSuccessCommitTogether() {
        outer.bothSuccessful();

        assertEquals(110L, amount(1L));
        assertEquals(210L, amount(2L));
    }
}
~~~

**Vì sao test không annotate `@Transactional`?** Spring Test có thể mở transaction bao ngoài test. Khi đó `nested.observe()` sẽ **đang có outer transaction của test**, nên kết quả savepoint khác hoàn toàn điều kiện “không có outer” cần nghiên cứu. Bài test này không được bọc transaction ngoài; dữ liệu reset trong `@BeforeEach` bằng JDBC trước mỗi test.

Những assertions kiểm tra **giá trị persisted sau khi service proxy kết thúc**, không chỉ kiểm tra exception. Hai test đầu trực tiếp đọc `TransactionStatus` tại thời điểm method NESTED đang được intercept.

## 7. Chạy test và bảng kết quả dự kiến

Từ thư mục `nested-no-outer-lab`, cần JDK 17+, Maven và dependencies:

~~~bash
java -version
mvn -version
mvn test
~~~

Nếu project có Maven Wrapper, có thể chạy `./mvnw test` (Linux/macOS) hoặc `.\mvnw.cmd test` (Windows PowerShell). Với source và H2 tương thích như trên, kết quả **dự kiến** là **8 test pass, 0 failure, 0 error**. Đây là dự đoán theo code, không phải log của một lần chạy đã thực hiện; thông báo Maven và thứ tự test không cố định.

| Test | Kết quả | Bài học |
| --- | --- | --- |
| `withoutOuterNestedStartsNewTransactionNotSavepoint` | active=true, newTransaction=true, hasSavepoint=false | NESTED không có outer mở physical transaction mới |
| `withOuterNestedCreatesSavepointNotPhysicalTransaction` | active=true, newTransaction=false, hasSavepoint=true | NESTED có outer dùng savepoint |
| `standaloneNestedSuccessCommits` | A=110, B=200 | Method standalone sở hữu commit |
| `standaloneNestedFailureRollsBackWholeTransaction` | A=100, B=200 | Method standalone rollback toàn transaction của nó |
| `consecutiveStandaloneNestedCallsAreNotOneTransaction` | A=110, B=200 | Hai lần standalone không nguyên tử với nhau |
| `nestedFailureRollsBackToSavepointOuterStillCommits` | A=120, B=200 | Inner rollback cục bộ, outer vẫn commit |
| `nestedSuccessDoesNotSurviveOuterRollback` | A=100, B=200 | Inner không commit độc lập |
| `nestedAndOuterSuccessCommitTogether` | A=110, B=210 | Outer commit toàn transaction gồm inner |

**Tập trung vào hai test đầu:** cùng annotation `NESTED` nhưng khi không có outer, `hasSavepoint()` false và `isNewTransaction()` true; khi có outer, chúng đảo lại. Đó là bằng chứng phân biệt bắt đầu một transaction mới với tạo savepoint trong transaction sẵn có.

## 8. Các giới hạn và lỗi phổ biến

### 8.1. Không phải manager nào cũng hỗ trợ nested transaction

`DataSourceTransactionManager` với JDBC savepoint phù hợp cho bài lab. H2 hỗ trợ JDBC savepoints; dự án thật phải kiểm tra manager và `Connection.getMetaData().supportsSavepoints()` khi cần.

- `JpaTransactionManager` quản lý JPA persistence context, và hỗ trợ JDBC savepoint không có nghĩa trạng thái của toàn bộ JPA object graph tự rollback đồng bộ. Không suy ra rằng `NESTED` hoạt động với mọi provider JPA.
- `JtaTransactionManager` có thể không hỗ trợ `NESTED` theo kiểu JDBC savepoint.
- Việc bật `nestedTransactionAllowed` trong Spring không tự tạo tính năng mà driver/database không hỗ trợ.
- Nếu **không có outer**, điểm quyết định là manager có thể bắt đầu physical transaction mới, chứ không phải savepoint của một outer chưa hề tồn tại.

Khi manager không hỗ trợ nested với outer, Spring có thể ném `NestedTransactionNotSupportedException`. Nên báo lỗi và sửa thiết kế/cấu hình; không tự thay `NESTED` thành `REQUIRES_NEW` nếu phải giữ atomicity với outer.

### 8.2. NESTED không tạo commit độc lập như REQUIRES_NEW

Savepoint vẫn thuộc một physical transaction. Nếu outer rollback, nó có thể hủy tất cả thay đổi chưa commit kể cả inner NESTED đã thành công. `REQUIRES_NEW` lại có independent commit/rollback và có thể cần connection riêng, với nguy cơ cạn connection pool hoặc lock contention.

Chọn `NESTED` khi muốn **một transaction tổng thể** nhưng có khả năng rollback cục bộ khi phù hợp; chọn `REQUIRES_NEW` khi thực sự muốn **transaction độc lập** và chấp nhận hậu quả không rollback theo outer.

### 8.3. Transaction manager chưa nhìn thấy outer vì khác thread/resource

JDBC imperative transaction thường gắn với thread. Nếu outer tạo transaction rồi gọi inner ở một thread khác qua `@Async`/executor, inner có thể không thấy transaction ngoài và mở transaction mới — dù ở luồng nghiệp vụ con người nghĩ nó “nằm trong outer”. Tương tự, hai `DataSource`/transaction managers khác nhau không tự chia sẻ physical transaction và savepoint.

Khi debug, kiểm tra manager, connection resource, thread và đường đi proxy. Không dùng phát biểu “NESTED đã nhìn thấy outer” chỉ dựa trên quan hệ gọi method trong sơ đồ kiến trúc.

### 8.4. Self-invocation bỏ qua annotation NESTED

Trong Spring AOP proxy mode thông thường, `this.someNestedMethod()` từ cùng target không qua proxy và transaction interceptor không tạo transaction/savepoint riêng. Khi không có outer, code có thể chạy ngoài transaction; khi có outer, SQL vẫn thuộc outer nhưng không có savepoint inner từ annotation.

Giải pháp là ranh giới service rõ ràng, gọi bean Spring qua proxy (bài lab tiêm một bean khác). Không tự động thêm AspectJ weaving chỉ để khắc phục thiết kế lời gọi nội bộ.

### 8.5. Kiểu exception quyết định rollback

Trong lab, `IllegalStateException` là `RuntimeException`; Spring mặc định rollback. Nếu inner NESTED ném checked `IOException` không có rollback rule, Spring có thể **không rollback** chỉ vì exception đó.

Ví dụ cấu hình khi checked exception phải rollback:

~~~java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = java.io.IOException.class
)
public void importRecords() throws java.io.IOException {
    // Đoạn minh họa, không phải class độc lập.
}
~~~

Khi không có outer, rollback toàn transaction mới. Khi có outer, rollback về savepoint nếu được hỗ trợ; exception tiếp tục đi qua outer proxy còn có thể kích hoạt rollback rule của outer.

### 8.6. Không phải lỗi database nào cũng cho outer tiếp tục an toàn

Lab chèn lỗi Java **sau một UPDATE thành công**; connection và transaction vẫn có thể tiếp tục sau rollback về savepoint. Một lỗi JDBC nghiêm trọng, connection bị mất hoặc persistence context ORM không còn nhất quán có thể khiến outer không nên tiếp tục commit. Trong production, cần phân loại lỗi và chủ động rollback/retry toàn transaction khi không thể tiếp tục an toàn.

### 8.7. Không nhầm test transactional với outer transaction thật

Nếu test class có `@Transactional`, Spring Test framework có thể tạo một transaction bao ngoài và rollback sau test. Khi đó test “standalone NESTED” không còn standalone, khiến kết quả sai mục tiêu. Để kiểm thử tự commit/rollback, đừng đặt transaction test-level vô ý và hãy **đọc database sau lời gọi proxy đã hoàn tất**.

### 8.8. Đừng dùng savepoint để né ràng buộc nghiệp vụ

Dù inner có thể rollback cục bộ, không phải mọi lỗi nghiệp vụ đều nên được nuốt để outer commit. Nếu outer và inner cùng tạo thành một bất biến cần nguyên tử, phải để lỗi dẫn tới rollback toàn transaction. `NESTED` chỉ hữu ích khi nghiệp vụ **thật sự cho phép** bỏ một bước phụ nhưng giữ bước chính.

## 9. Quy trình chẩn đoán

Khi một method NESTED không có hành vi như kỳ vọng:

1. Kiểm tra **transaction ngoài thật sự tồn tại tại thời điểm gọi** chưa; đừng quên transaction của test và thread-local.
2. Kiểm tra caller đi qua **Spring proxy** hay self-invocation, `new` object hoặc annotation ở method không được intercept.
3. Xác nhận transaction manager đang dùng là manager có khả năng tạo transaction và hỗ trợ nested JDBC nếu đã có outer.
4. Quan sát `TransactionAspectSupport.currentTransactionStatus()`: `isNewTransaction()`, `hasSavepoint()` và `TransactionSynchronizationManager.isActualTransactionActive()`.
5. Tạo lỗi **sau khi UPDATE** và đo dữ liệu sau completion. Lỗi trước mọi SQL không chứng minh rollback thực sự.
6. Phân biệt `NESTED` và `REQUIRES_NEW`: savepoint không có independent commit, independent transaction có.
7. Đọc rollback rules cho cả inner và outer; catch exception ở đâu, nó có thoát qua interceptor nào, resource còn commit được không?
8. Khi nhiều bước phải nguyên tử, kiểm tra **outer service có @Transactional** và dùng cùng manager/resource không.

## 10. Tự kiểm tra

1. **NESTED được gọi qua proxy nhưng không có outer có báo lỗi không?** — Không chỉ vì thiếu outer; manager phù hợp sẽ bắt đầu một physical transaction mới.
2. **Không có outer thì savepoint ở đâu?** — Không tạo savepoint lồng vào transaction cũ; trong lab `hasSavepoint=false`, `isNewTransaction=true`.
3. **NESTED standalone thành công có commit không?** — Có nếu nó sở hữu transaction mới và không có lý do rollback khác.
4. **NESTED standalone ném RuntimeException sau UPDATE thì sao?** — Rollback toàn physical transaction mà nó vừa mở.
5. **Hai lời gọi NESTED từ một coordinator không transactional có nguyên tử với nhau không?** — Không; một lời gọi đã commit không bị rollback bởi lỗi của lời gọi sau.
6. **NESTED có outer, inner thành công có commit bền vững ngay không?** — Không; outer giữ quyền commit cuối.
7. **NESTED có outer, inner lỗi có thể chỉ rollback riêng nó không?** — Có, nếu savepoint được hỗ trợ và trạng thái database cho phép outer tiếp tục.
8. **Outer rollback sau nested success thì sao?** — Các thay đổi chưa commit của inner vẫn bị rollback chung.
9. **NESTED khác MANDATORY khi không có outer thế nào?** — NESTED bắt đầu transaction; MANDATORY báo thiếu transaction.
10. **Vì sao không gắn @Transactional lên test?** — Để không vô tình tạo outer transaction thay đổi đúng điều kiện quan sát.
11. **Savepoint khác REQUIRES_NEW ở điều gì quan trọng?** — Savepoint chung physical transaction, không independent commit; REQUIRES_NEW là physical transaction độc lập.
12. **Gọi this.nestedMethod() có tự tạo savepoint không?** — Thông thường không trong proxy mode.

## 11. Bài tập mở rộng

**Bài A:** thêm `@Transactional` lên `NonTransactionalCoordinator.runTwoSteps()` rồi chạy lại phép thử A=110/B=200. Giờ các lần gọi nested nhìn thấy outer. Khi exception không được catch và thoát qua outer interceptor, dự đoán A=100/B=200 do rollback cả outer. Giải thích vì sao thêm transaction ở coordinator thay đổi tính nguyên tử.

**Bài B:** đổi một method NESTED sang REQUIRED để kiểm tra khác nhau **khi có outer**. Nếu inner REQUIRED ném RuntimeException, transaction chung có thể bị đánh dấu rollback-only; outer catch lỗi có thể vẫn không commit được. Nêu sự khác biệt với rollback về savepoint của NESTED.

**Bài C:** thử `Propagation.MANDATORY` trên method được gọi khi không có outer. Dự kiến Spring ném `IllegalTransactionStateException`. So sánh kết quả với standalone NESTED.

**Bài D:** đổi NESTED thành REQUIRES_NEW trong bản sao lab, cho inner/outer cập nhật hai hàng khác nhau để tránh lock wait. Sau khi inner commit rồi outer rollback, kiểm tra B có còn thay đổi không. Đó là phản chứng cho việc gọi savepoint là transaction độc lập.

**Bài E:** dùng checked `IOException` thay cho `IllegalStateException` sau UPDATE; kiểm tra mặc định và thêm `rollbackFor = IOException.class`. Không phán đoán kết quả rollback chỉ từ việc Java đã ném exception.

## 12. Kết luận

**NESTED không có outer** nghĩa là Spring **bắt đầu transaction mới**; nó không tạo savepoint trong một transaction vốn không tồn tại. **NESTED có outer** mới bộc lộ mục đích chính của savepoint: rollback cục bộ bên trong cùng physical transaction, giữ quyền commit cuối cho outer.

Muốn thiết kế transaction chính xác, luôn xét **(1) transaction hiện có, (2) propagation, (3) proxy boundary, (4) transaction manager/driver, (5) rollback rules**. Sự kết hợp đó — không phải riêng chữ `NESTED` — quyết định dữ liệu nào được commit hay hoàn tác.

### Tài liệu tham khảo chính thức

- [Spring Framework — Transaction Propagation, including PROPAGATION_NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — @Transactional Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — DataSourceTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — AbstractPlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework — Declarative Rollback Rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)