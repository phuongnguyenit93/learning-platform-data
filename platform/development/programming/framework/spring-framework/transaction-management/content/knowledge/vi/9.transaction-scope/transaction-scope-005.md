# Thuộc tính phương thức trong có thể không thay thế cấu hình bên ngoài

## 1. Vấn đề: tại sao annotation của phương thức trong không có tác dụng như mong đợi?

Khi các service trong Spring Framework gọi lẫn nhau, một phương thức đã mở transaction có thể gọi phương thức khác cũng có `@Transactional`. Không phải cứ gặp annotation mới là Spring đóng giao dịch cũ và tạo giao dịch mới với các thuộc tính mới. **Propagation** quyết định phương thức bên trong **tham gia giao dịch có sẵn hay mở giao dịch độc lập**.

Ví dụ:

~~~java
@Service
class OrderService {
    private final InventoryService inventory;

    OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE,
        readOnly = false,
        timeout = 30
    )
    public void placeOrder() {
        inventory.reserve();
    }
}

@Service
class InventoryService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        readOnly = true,
        timeout = 1
    )
    public void reserve() {
        // Thuộc cùng physical transaction do placeOrder() đã mở.
    }
}
~~~

Mã trên **chỉ minh họa ý tưởng**, không phải dự án độc lập (các imports và logic nghiệp vụ đã lược bớt). Bài lab chạy được nằm ở phần 5.

Nếu `placeOrder()` được caller gọi **qua Spring proxy** và mở transaction mới, còn `reserve()` cũng được gọi qua proxy của bean `InventoryService`:

- Outer mở một **physical transaction** với isolation `SERIALIZABLE`, read-only `false` và timeout 30 giây (theo hỗ trợ của manager/driver).
- Inner khai báo `REQUIRED`, nên **tham gia** physical transaction đã tồn tại. Nó tạo một *logical transaction scope* nhưng **không mở physical transaction mới**.
- Mặc định, transaction manager kiểu lenient của Spring **giữ isolation, timeout, read-only của outer transaction**, không để thuộc tính inner thay thế trên cùng physical transaction.
- Nếu inner trở về bình thường, transaction chưa chắc đã commit: outer mới là nơi hoàn thành transaction vật lý của toàn nghiệp vụ.

Điểm này không có nghĩa mọi metadata inner đều vô hiệu: **rollback rules** của inner vẫn có thể ảnh hưởng đến trạng thái rollback-only chung. Cần tách thuộc tính **đặc tính physical transaction** với quy tắc xử lý **logical scope**.

### Ma trận đầu tiên

| Cách gọi | Trạng thái bên ngoài | Propagation inner | Thuộc tính nào áp dụng vào giao dịch thực tế? |
| --- | --- | --- | --- |
| Gọi inner qua proxy khi chưa có transaction | Không có | `REQUIRED` | Inner mở giao dịch mới, dùng isolation/readOnly/timeout của chính nó khi được hỗ trợ. |
| Outer mở transaction, rồi gọi inner qua proxy | Đã có | `REQUIRED` | Inner tham gia giao dịch outer; thông số vật lý vẫn của outer theo mặc định. |
| Outer mở transaction, rồi gọi inner qua proxy | Đã có | `REQUIRES_NEW` | Inner mở physical transaction độc lập, có thể dùng thông số riêng. |
| Inner method được gọi qua `this.inner()` | Có hoặc chưa | Annotation có thể là `REQUIRED` hay `REQUIRES_NEW` | **Self-invocation** trong proxy mode thường bỏ qua transaction interceptor của inner. |

Ba câu hỏi quan trọng nhất khi debug là: **đã có transaction chưa?**, **propagation là gì?**, **lời gọi có đi qua proxy không?**

## 2. Phạm vi logic và giao dịch vật lý

Spring phân biệt:

- **Physical transaction:** giao dịch trên resource/database thực, có `BEGIN` hoặc cơ chế tương đương, quản lý JDBC connection, isolation, commit/rollback và vòng đời.
- **Logical transaction scope:** phạm vi advice của một method transactional đi qua interceptor. Một scope có rollback rule riêng, nhưng có thể dùng chung physical transaction với các scope khác.
- **Transaction owner:** scope bắt đầu physical transaction và chịu trách nhiệm hoàn tất commit/rollback ở biên ngoài cùng của giao dịch đó.

Sơ đồ `REQUIRED`:

~~~text
Caller
  |
  v
OuterService proxy
  |
  +-- OUTER logical transaction
  |      |
  |      +-- MỞ physical transaction T1
  |      |   isolation=SERIALIZABLE
  |      |   readOnly=false
  |      |   timeout=30
  |      |
  |      +-- outerBusinessMethod()
  |             |
  |             v
  |        InnerService proxy
  |             |
  |             +-- INNER logical transaction REQUIRED
  |             |   tham gia T1, không có T2
  |             |
  |             +-- innerBusinessMethod()
  |                   thực hiện SQL trên T1
  |
  +-- OUTER hoàn tất T1: commit hoặc rollback
~~~

**Mỗi method có thể tạo một logical scope** nhưng không nhất thiết tạo một database transaction riêng. Nếu cả hai cùng thuộc T1, không thể nói “inner đã commit” chỉ vì method trong trả về bình thường.

### Precedence của annotation không đồng nghĩa quyền đổi transaction đã mở

Khi Spring phân giải annotation, thông số `@Transactional` đặt **trực tiếp trên method** thường được ưu tiên so với thông số gắn trên class đó. Ví dụ:

~~~java
@Transactional(readOnly = true)
public class ExampleService {
    @Transactional(readOnly = false)
    public void update() {
        // Method-level metadata được ưu tiên hơn class-level metadata.
    }
}
~~~

Đây là đoạn minh họa, không phải file đầy đủ. **Metadata resolution** xảy ra khi Spring xác định thuộc tính transactional cho lời gọi. Còn việc **join một transaction đã tồn tại** là bước khác. `readOnly=false` ở method có thể được chọn đúng mà vẫn không thay được read-only của physical transaction do outer method ở bean khác tạo trước đó.

## 3. Những thuộc tính cần phân biệt

### 3.1. isolation

Nếu outer `SERIALIZABLE` và inner `REQUIRED(READ_COMMITTED)`, inner thường chạy trong isolation **SERIALIZABLE** của T1. Thuộc tính isolation inner không thể tự hạ hoặc nâng isolation của giao dịch vật lý đang hoạt động.

Ngược lại, nếu không có T1 và inner `REQUIRED` tự mở transaction, database/manager có thể áp `READ_COMMITTED`. Với `REQUIRES_NEW`, inner mở transaction mới T2 có isolation riêng.

Mức isolation thể hiện bảo đảm đồng thời của database. Chi tiết xử lý snapshot, lock, conflict có thể khác giữa PostgreSQL, MySQL/InnoDB, H2 và các engine khác.

### 3.2. readOnly

`readOnly=true` là thuộc tính/hint cho transaction manager, JDBC driver hoặc ORM; nó có thể tối ưu flush, đưa hint tới connection hay thực thi ràng buộc tùy cấu hình. **Không xem nó là cơ chế phân quyền bảo mật** hay bảo đảm mọi database đều cấm `UPDATE`.

Một inner `REQUIRED(readOnly=true)` tham gia outer read-write thường **không biến** T1 thành read-only. Ngược lại, một inner muốn ghi không thể tự “bật lại” read-write nếu outer đã mở read-only và manager/engine không cho phép.

### 3.3. timeout

`timeout` áp dụng khi **tạo physical transaction mới**. Inner `REQUIRED(timeout=1)` tham gia outer `timeout=30` không đồng nghĩa deadline của T1 bị reset còn một giây. Spring transaction timeout cũng không phải đồng hồ tự ngắt thread Java tùy ý ngay đúng giây: hiệu lực phụ thuộc cách transaction manager, JDBC/ORM và driver áp dụng giới hạn.

Cần network timeout hay business deadline riêng? Hãy thiết kế tại tầng liên quan thay vì trông chờ method inner thay đổi transaction timeout ngoài.

### 3.4. propagation

- `REQUIRED`: dùng transaction hiện có hoặc mở mới.
- `REQUIRES_NEW`: mở physical transaction mới, tạm đình chỉ transaction ngoài khi manager hỗ trợ; inner có thể commit/rollback độc lập.
- `NESTED`: thường tạo JDBC savepoint trong **cùng physical transaction** nếu manager hỗ trợ; không phải một commit độc lập như `REQUIRES_NEW`.
- `SUPPORTS`: tham gia transaction nếu có, không bắt buộc tạo transaction khi không có; không nên suy từ một annotation `SUPPORTS` rằng luôn có ranh giới commit.

`REQUIRES_NEW` có thể làm mất tính nguyên tử tổng thể: một inner transaction đã commit sẽ không bị rollback chỉ vì outer gặp lỗi sau đó. Nó còn cần tài nguyên/connection phù hợp và dễ gặp lock wait nếu inner ghi vào hàng outer vẫn đang giữ khóa.

### 3.5. rollback rules: phần inner *vẫn* có thể tác động

Khi inner `REQUIRED` có `@Transactional(rollbackFor = IOException.class)`, nếu `IOException` thoát qua **inner proxy**, advice có thể đánh dấu transaction T1 là **rollback-only**. Outer catch ngoại lệ rồi trả về bình thường **không xóa được dấu này**. Lúc outer cố commit, Spring thường rollback và báo `UnexpectedRollbackException`.

Ngược lại, inner `@Transactional(noRollbackFor = BusinessNotice.class)` không yêu cầu rollback chỉ vì exception này. Nếu outer bắt ngoại lệ rồi hoàn thành bình thường, T1 có thể commit. Nhưng nếu unchecked exception vẫn thoát qua outer proxy, rollback rule **của outer** có thể gây rollback.

Vì vậy nói “isolation, timeout, readOnly của inner không ghi đè outer” là đúng trong trường hợp tham gia T1; nói “mọi thuộc tính inner đều bị bỏ qua” lại **sai**.

## 4. Bảng tổng kết theo ranh giới transaction

| Tình huống | Physical transaction | Điều gì quyết định commit/rollback? |
| --- | --- | --- |
| Inner `REQUIRED` không có outer | T1 do inner mở | Inner proxy quyết định hoàn tất T1. |
| Outer T1 gọi inner `REQUIRED` | Cùng một T1 | Outer hoàn tất; inner có thể đặt rollback-only. |
| Outer T1 gọi inner `REQUIRES_NEW` | Outer T1 tạm dừng; inner T2 độc lập | T2 commit/rollback riêng; T1 tiếp tục sau đó. |
| Outer T1 gọi inner `NESTED` khi được hỗ trợ | Cùng T1, có savepoint | Có thể rollback scope inner về savepoint; commit vật lý do T1. |
| Inner bị gọi bằng `this.inner()` | Không phát sinh interceptor inner | Annotation inner có thể không được áp; chỉ phạm vi transaction sẵn có còn hiệu lực. |

Phần tiếp theo biến các phát biểu này thành phép thử **thực sự đọc database** và quan sát metadata transaction đang chạy.

## 5. Bài lab hoàn chỉnh: Java 17 + Spring Boot + JDBC + H2

Bài thực hành dùng **Spring Boot 3.5.0**, Spring JDBC, H2 in-memory và JUnit 5. Hai bean riêng `OuterService`/`InnerService` bảo đảm lời gọi bên trong đi qua Spring proxy; `SelfCallService` chứng minh trường hợp bypass proxy.

### 5.1. Cấu trúc dự án

~~~text
tx-scope-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/txscope/
    │   │   ├── TxScopeApplication.java
    │   │   ├── TxView.java
    │   │   ├── InnerService.java
    │   │   ├── OuterService.java
    │   │   └── SelfCallService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/txscope/
            └── TxScopeTest.java
~~~

### 5.2. pom.xml

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
    <artifactId>tx-scope-lab</artifactId>
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

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate` và transaction infrastructure; Spring Boot cấu hình JDBC transaction manager cho một `DataSource` thích hợp. `spring-boot-starter-test` cung cấp JUnit 5 và `@SpringBootTest`. Lab không kích hoạt chế độ strict validation.

### 5.3. application.properties và schema.sql

Tệp `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:tx_scope_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE tx_scope_balance (
    id BIGINT PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

H2 chạy trong bộ nhớ JVM và không đòi hỏi database server riêng. Mỗi test sẽ tự chèn dữ liệu A (id=1, amount=100) và B (id=2, amount=200). Bảng này chỉ là dữ liệu minh họa, không phải mô hình tài chính thật.

### 5.4. TxScopeApplication.java và TxView.java

Tệp `src/main/java/com/example/txscope/TxScopeApplication.java`:

~~~java
package com.example.txscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxScopeApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxScopeApplication.class, args);
    }
}
~~~

Tệp `src/main/java/com/example/txscope/TxView.java`:

~~~java
package com.example.txscope;

public record TxView(
    boolean active,
    Integer isolation,
    boolean readOnly
) {}
~~~

`TxView` trả về thông tin từ `TransactionSynchronizationManager`. Đây là metadata transaction được Spring giữ trên thread, **không phải snapshot MVCC** và cũng không xác minh database engine đã thực hiện mọi chi tiết isolation/read-only ra sao. Ta cố ý không đo timeout bằng cách cho Java thread ngủ một giây, vì đó không phải phép kiểm đúng cho JDBC transaction timeout.

### 5.5. InnerService.java

Tệp `src/main/java/com/example/txscope/InnerService.java`:

~~~java
package com.example.txscope;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        readOnly = true,
        timeout = 1
    )
    public TxView inspect() {
        return new TxView(
            TransactionSynchronizationManager.isActualTransactionActive(),
            TransactionSynchronizationManager.getCurrentTransactionIsolationLevel(),
            TransactionSynchronizationManager.isCurrentTransactionReadOnly()
        );
    }

    @Transactional(rollbackFor = IOException.class)
    public void updateThenFailChecked(long id) throws IOException {
        increase(id);
        throw new IOException("inner checked failure");
    }

    public static class BusinessNotice extends RuntimeException {
        public BusinessNotice(String message) {
            super(message);
        }
    }

    @Transactional(noRollbackFor = BusinessNotice.class)
    public void updateThenNotice(long id) {
        increase(id);
        throw new BusinessNotice("inner business notice");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateIndependently(long id) {
        increase(id);
    }

    private void increase(long id) {
        int affected = jdbc.update(
            "UPDATE tx_scope_balance SET amount = amount + 10 WHERE id = ?",
            id
        );
        if (affected != 1) {
            throw new IllegalStateException("Missing account " + id);
        }
    }
}
~~~

Những điểm cần xem:

- `inspect()` khai báo isolation `READ_COMMITTED`, `readOnly=true` và `timeout=1`. Nếu **không có** outer transaction, chính nó mở transaction và trả về metadata ấy. Nếu tham gia outer T1, nó quan sát metadata của T1.
- `updateThenFailChecked()` tăng số dư 10 rồi ném **checked `IOException`**. Nhờ `rollbackFor`, inner advice yêu cầu rollback dù IOException theo mặc định không tự khiến Spring rollback.
- `updateThenNotice()` tăng số dư rồi ném unchecked `BusinessNotice`. `noRollbackFor` yêu cầu inner không đánh dấu rollback chỉ vì exception ấy.
- `updateIndependently()` có `REQUIRES_NEW`: nó mở T2 độc lập; không thay thế isolation của T1, cũng không tự làm T1 commit.
- `increase()` là helper private được gọi trong transaction đang có. Không cần đặt `@Transactional` ở private helper; lời gọi transaction boundary nằm ở các public service methods.

### 5.6. OuterService.java

Tệp `src/main/java/com/example/txscope/OuterService.java`:

~~~java
package com.example.txscope;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final InnerService inner;
    private final JdbcTemplate jdbc;

    public OuterService(InnerService inner, JdbcTemplate jdbc) {
        this.inner = inner;
        this.jdbc = jdbc;
    }

    @Transactional(
        isolation = Isolation.SERIALIZABLE,
        readOnly = false,
        timeout = 30
    )
    public TxView inspectInnerJoined() {
        return inner.inspect();
    }

    @Transactional
    public void catchCheckedButRollbackOnly() {
        increase(1L);
        try {
            inner.updateThenFailChecked(1L);
        } catch (IOException e) {
            if (!"inner checked failure".equals(e.getMessage())) {
                throw new IllegalStateException(e);
            }
            // Catch không xóa rollback-only do inner advice đặt.
        }
    }

    @Transactional
    public void catchNoticeAndCommit() {
        increase(1L);
        try {
            inner.updateThenNotice(1L);
        } catch (InnerService.BusinessNotice expected) {
            // noRollbackFor ở inner và outer kết thúc bình thường.
        }
    }

    @Transactional
    public void propagateNoticeAndRollback() {
        increase(1L);
        inner.updateThenNotice(1L);
        // BusinessNotice còn thoát qua outer proxy.
    }

    @Transactional
    public void outerFailsAfterIndependentCommit() {
        increase(1L);
        inner.updateIndependently(2L);
        throw new IllegalStateException("outer failure");
    }

    private void increase(long id) {
        int affected = jdbc.update(
            "UPDATE tx_scope_balance SET amount = amount + 10 WHERE id = ?",
            id
        );
        if (affected != 1) {
            throw new IllegalStateException("Missing account " + id);
        }
    }
}
~~~

`OuterService` tiêm `InnerService` là bean **khác**, vì vậy `inner.inspect()` và các lời gọi inner khác đi qua proxy mà Spring quản lý. Với `catchCheckedButRollbackOnly()`, outer bắt `IOException` **sau khi inner interceptor đã đánh dấu shared transaction rollback-only**. Outer trả về bình thường nhưng transaction không thể commit bình thường. Với `catchNoticeAndCommit()`, inner `noRollbackFor` không đánh dấu rollback-only; outer catch exception rồi kết thúc bình thường nên hai lệnh tăng số dư cùng commit nếu không có lỗi khác.

`propagateNoticeAndRollback()` là trường hợp khác: outer **không catch** `BusinessNotice`, nên ngoại lệ unchecked thoát qua outer interceptor, làm rollback theo quy tắc **của outer** dù inner có `noRollbackFor`.

Trong `outerFailsAfterIndependentCommit()`, outer ghi A và inner `REQUIRES_NEW` ghi B: inner commit riêng, outer throw exception rồi rollback. Đây là lý do `REQUIRES_NEW` không phải “cách ép cấu hình inner thắng outer” trong mọi nghiệp vụ.

### 5.7. SelfCallService.java

Tệp `src/main/java/com/example/txscope/SelfCallService.java`:

~~~java
package com.example.txscope;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SelfCallService {
    public boolean viaThis() {
        return this.requiresNewTransaction();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public boolean requiresNewTransaction() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }
}
~~~

Ở ngữ cảnh **không có outer transaction**, gọi `viaThis()` thông qua bean trả về `false`: lời gọi `this.requiresNewTransaction()` không đi qua transaction proxy. Gọi `requiresNewTransaction()` trực tiếp **trên bean Spring** trả về `true` vì proxy mở physical transaction. Nếu đã có outer transaction, `isActualTransactionActive()` có thể trả về true ngay cả khi inner annotation bị bypass; bài lab tránh ngữ cảnh này để kiểm chứng chính xác self-invocation.

### 5.8. TxScopeTest.java: bảy phép thử tích hợp

Tệp `src/test/java/com/example/txscope/TxScopeTest.java`:

~~~java
package com.example.txscope;

import java.sql.Connection;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class TxScopeTest {
    @Autowired
    private OuterService outer;

    @Autowired
    private InnerService inner;

    @Autowired
    private SelfCallService self;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_scope_balance");
        jdbc.update(
            "INSERT INTO tx_scope_balance(id, amount) VALUES (?, ?)",
            1L, 100L
        );
        jdbc.update(
            "INSERT INTO tx_scope_balance(id, amount) VALUES (?, ?)",
            2L, 200L
        );
    }

    private long amount(long id) {
        Long result = jdbc.queryForObject(
            "SELECT amount FROM tx_scope_balance WHERE id = ?",
            Long.class, id
        );
        if (result == null) {
            throw new AssertionError("Missing account " + id);
        }
        return result;
    }

    @Test
    void requiredInnerAloneUsesOwnAttributes() {
        TxView view = inner.inspect();

        assertTrue(view.active());
        assertEquals(
            Integer.valueOf(Connection.TRANSACTION_READ_COMMITTED),
            view.isolation()
        );
        assertTrue(view.readOnly());
    }

    @Test
    void requiredInnerJoinsAndKeepsOuterAttributes() {
        TxView view = outer.inspectInnerJoined();

        assertTrue(view.active());
        assertEquals(
            Integer.valueOf(Connection.TRANSACTION_SERIALIZABLE),
            view.isolation()
        );
        assertFalse(view.readOnly());
    }

    @Test
    void innerRollbackOnlyPreventsOuterCommit() {
        assertThrows(
            UnexpectedRollbackException.class,
            outer::catchCheckedButRollbackOnly
        );

        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void caughtNoticeWithNoRollbackForAllowsCommit() {
        outer.catchNoticeAndCommit();

        assertEquals(120L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void uncaughtNoticeStillRollsBackAtOuterBoundary() {
        assertThrows(
            InnerService.BusinessNotice.class,
            outer::propagateNoticeAndRollback
        );

        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void requiresNewCommitsIndependentlyOfOuter() {
        assertThrows(
            IllegalStateException.class,
            outer::outerFailsAfterIndependentCommit
        );

        assertEquals(100L, amount(1L));
        assertEquals(210L, amount(2L));
    }

    @Test
    void selfInvocationDoesNotTriggerAnnotation() {
        assertFalse(self.viaThis());
        assertTrue(self.requiresNewTransaction());
    }
}
~~~

**Bảy tests** kiểm chứng cả tính chất transaction và giá trị persisted, không chỉ thấy annotation có tồn tại. Test **không gắn `@Transactional` trên class hoặc method**; nếu Spring Test tự mở transaction bao ngoài, service `REQUIRED` có thể tham gia transaction của test và bị rollback khi test kết thúc, che giấu kết quả commit/rollback thật của service.

`@BeforeEach` xóa/chèn dữ liệu lại từ đầu ngoài transaction của test. Mỗi test được đọc lại sau khi service proxy đã hoàn tất transaction. `amount(1L)` là phép SELECT sau lời gọi, có khả năng quan sát giá trị committed/rolled-back như mong đợi.

## 6. Cách chạy và diễn giải kết quả

Yêu cầu JDK 17+ và Maven (hoặc Maven Wrapper của dự án). Tại thư mục `tx-scope-lab`:

~~~bash
java -version
mvn -version
mvn test
~~~

Nếu tạo project bằng Spring Initializr có Maven Wrapper, dùng `./mvnw test` trên Linux/macOS hoặc `.\mvnw.cmd test` trên Windows PowerShell.

Với code và cấu hình lab, Maven Surefire dự kiến báo **7 tests thành công, 0 failure và 0 error**. Thứ tự chạy và log hệ thống không cố định.

| Test | Kết quả cần có | Điều chứng minh |
| --- | --- | --- |
| `requiredInnerAloneUsesOwnAttributes` | active=true, READ_COMMITTED, readOnly=true | Khi tự mở transaction, inner áp thông số riêng. |
| `requiredInnerJoinsAndKeepsOuterAttributes` | active=true, SERIALIZABLE, readOnly=false | Inner `REQUIRED` không ghi đè các đặc tính physical transaction của outer. |
| `innerRollbackOnlyPreventsOuterCommit` | `UnexpectedRollbackException`, A=100, B=200 | Inner có rollback rule đánh dấu T1, outer không thể commit dù đã catch checked exception. |
| `caughtNoticeWithNoRollbackForAllowsCommit` | A=120, B=200 | Inner không mark rollback-only; outer bắt lỗi rồi commit bình thường. |
| `uncaughtNoticeStillRollsBackAtOuterBoundary` | `BusinessNotice`, A=100, B=200 | Outer rollback theo rule của mình khi unchecked exception thoát ra. |
| `requiresNewCommitsIndependentlyOfOuter` | Exception, A=100, B=210 | Inner `REQUIRES_NEW` commit riêng trước khi outer rollback. |
| `selfInvocationDoesNotTriggerAnnotation` | viaThis=false; direct call=true | Proxy interception khác với gọi `this.inner()`. |

### Phân tích cụ thể trường hợp rollback-only

~~~text
Ban đầu: A=100, B=200
    |
    v
OuterService.catchCheckedButRollbackOnly() mở T1
    |
    +-- Outer UPDATE A: 100 -> 110
    |
    +-- InnerService.updateThenFailChecked() REQUIRED, tham gia T1
    |      |
    |      +-- Inner UPDATE A: 110 -> 120
    |      +-- throw IOException
    |      +-- Inner advice có rollbackFor=IOException
    |      +-- đánh dấu T1 rollback-only
    |
    +-- Outer catch(IOException), kết thúc method bình thường
    |
    v
Outer transaction interceptor cố commit T1
    |
    +-- Phát hiện rollback-only
    +-- rollback toàn bộ T1
    +-- UnexpectedRollbackException
    |
    v
Sau đó: A=100, B=200
~~~

Nguyên nhân không phải inner đã “thay thế isolation” của outer. **Isolation/timeout/readOnly** là đặc tính của physical transaction; còn **rollback-only** là trạng thái hoàn tất có thể bị ảnh hưởng bởi các logical scopes đang tham gia.

### Kiểm thử REQUIRES_NEW không gây nhầm lẫn khóa

Inner `REQUIRES_NEW` trong demo cập nhật **hàng B**, trong khi outer cập nhật **hàng A**, bởi outer transaction vẫn có thể giữ khóa ghi trên A lúc inner transaction mới chạy. Nếu cả hai ghi cùng hàng A, inner có thể chờ outer nhả khóa trong khi outer đang chờ inner, dẫn đến timeout/deadlock. Điều đó không chứng minh `REQUIRES_NEW` sai; nó là hệ quả concurrency cần xử lý.

## 7. Tùy chọn kiểm tra nghiêm: validateExistingTransaction

Mặc định, nhiều transaction manager Spring xử lý *lenient*: inner `REQUIRED` với isolation khác vẫn tham gia outer và giữ isolation vật lý của outer. Khi cần phát hiện cấu hình trái nhau, có thể bật `validateExistingTransaction` trên transaction manager:

~~~java
// Minh họa cấu hình riêng; không bổ sung vào lab nếu muốn giữ 7 tests.
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
~~~

Đoạn cấu hình trên **không biên dịch độc lập** khi đứng một mình: cần class `@Configuration` và các imports `@Bean`, `DataSource`, `PlatformTransactionManager`, `JdbcTransactionManager`. Khi đặt trong một dự án thật, phải bảo đảm đây đúng là transaction manager được service sử dụng, không tạo nhiều manager mơ hồ.

Với strict validation:

- Inner `READ_COMMITTED` tham gia outer `SERIALIZABLE` có thể bị từ chối bằng `IllegalTransactionStateException` do **mismatch isolation**.
- Inner **read-write** cố tham gia outer **read-only** có thể bị từ chối.
- Inner **read-only** tham gia outer **read-write** không nhất thiết bị từ chối chỉ vì khác readOnly theo chiều này.

**Mục tiêu của strict mode không phải cho inner ghi đè transaction đã mở**; nó biến cấu hình không nhất quán thành lỗi dễ nhìn thấy, để người lập trình sửa transaction boundary/propagation.

## 8. Các lỗi phổ biến

### 8.1. Nhầm method annotation thắng class annotation với inner thắng outer

Method-level `@Transactional` có precedence so với annotation trên **cùng class** khi xác định metadata cho method. Nhưng nó không có nghĩa một method `REQUIRED` có thể thay physical transaction được outer method mở trước. Đây là hai giai đoạn khác nhau.

### 8.2. Self-invocation

Trong Spring AOP proxy mode, `this.innerMethod()` trong cùng target không đi qua interceptor. Nếu outer đã mở T1, code inner có thể thực thi trên T1 nhưng **không có logical scope transactional mới tương ứng với annotation inner**. Nếu không có outer, việc gọi nội bộ như vậy thường cũng không tự mở transaction mới. Bài test `SelfCallService` làm rõ điều này.

### 8.3. Bắt exception không xóa rollback-only

Inner `REQUIRED` ném lỗi khớp rollback rule có thể đánh dấu shared transaction rollback-only. Outer catch rồi tiếp tục không làm trạng thái này mất đi. Khi outer commit, `UnexpectedRollbackException` có thể xuất hiện. Không nên nuốt lỗi và thông báo thành công nếu đã có thành phần yêu cầu rollback.

### 8.4. noRollbackFor ở inner không bảo vệ khỏi rollback của outer

Một unchecked exception có `noRollbackFor` tại inner boundary nhưng vẫn **thoát qua outer boundary** có thể bị outer interceptor rollback theo mặc định. Muốn hiểu kết quả, phải theo dõi exception đi qua từng proxy và rollback rules của từng scope.

### 8.5. Giao dịch khác thread hoặc khác manager

Spring JDBC transaction thông thường dùng ngữ cảnh gắn với thread. Gọi `@Async`, executor hoặc `CompletableFuture` ở thread khác không mặc định truyền transaction T1 của outer sang. Dùng hai `DataSource` hoặc hai `PlatformTransactionManager` cũng không bảo đảm tất cả ghi DB trong cùng physical transaction. Không suy diễn logic trên khi resource/manager thực tế khác nhau.

### 8.6. Cạn connection khi dùng REQUIRES_NEW

Inner physical transaction thường cần connection riêng trong lúc outer vẫn đang giữ resource của nó. Khi tải cao, nhiều request đồng thời đều giữ outer connection và chờ inner, connection pool có thể cạn; Spring tài liệu cảnh báo cần bố trí pool phù hợp. Dùng `REQUIRES_NEW` có chủ đích, không như biện pháp “ép thuộc tính” mặc định.

### 8.7. readOnly và timeout bị coi là cam kết tuyệt đối

`readOnly` không thay thế DB permissions; `timeout` không phải công cụ ngắt thread Java sau đúng N giây. Để kiểm tra hiệu lực, hãy dựa trên transaction manager, driver, DB engine và phép thử có kiểm soát.

### 8.8. Test bị bao bởi transaction của Spring Test

Nếu test có `@Transactional`, các service `REQUIRED` có thể tham gia transaction của test, và test framework rollback toàn bộ sau test. Khi mục tiêu là thấy service có commit/rollback chính xác ở đâu, tránh kiểu test này hoặc quản lý test transaction chủ động. Bài lab không gắn annotation transaction trên test.

## 9. Checklist thiết kế phạm vi

Trước khi giao cho inner method một bộ `@Transactional` mới:

1. Xác định **các thao tác DB phải nguyên tử**: có cần cùng commit/rollback không?
2. Xác định ai **mở physical transaction**: outer hay inner?
3. Xác định propagation: `REQUIRED` sẽ join; `REQUIRES_NEW` tạo commit độc lập; `NESTED` dùng savepoint nếu hỗ trợ.
4. Chọn isolation/readOnly/timeout **tại boundary tạo transaction**, thay vì mong inner `REQUIRED` ghi đè.
5. Kiểm tra rollback rules ở từng interceptor: exception có thoát qua proxy không và có mark rollback-only không?
6. Kiểm tra self-invocation, thread hop, đúng transaction manager và cùng resource.
7. Chạy integration tests **đọc lại database sau completion**, không chỉ kiểm tra exception hoặc tên proxy.
8. Nếu cần từ chối cấu hình mâu thuẫn, xem xét `setValidateExistingTransaction(true)` và viết test cho mismatch.

Một use case đặt hàng thường đặt transaction tại `OrderService.placeOrder()` rồi các repository/service cùng tham gia `REQUIRED`. Nếu một service thực sự cần ghi lịch sử độc lập dù đặt hàng thất bại, `REQUIRES_NEW` có thể hợp lý nhưng phải chấp nhận dữ liệu phụ được commit khi nghiệp vụ chính rollback. Nếu gọi một hệ thống thanh toán HTTP ngoài database, local transaction không rollback được tác dụng từ HTTP; cần idempotency/compensation thích hợp.

## 10. Tự kiểm tra

1. Outer `SERIALIZABLE`, inner `REQUIRED READ_COMMITTED`: physical isolation nào? — Thường vẫn **SERIALIZABLE của outer**.
2. Outer read-write, inner `REQUIRED(readOnly=true)`: transaction vật lý có đổi thành read-only không? — **Không** theo hành vi mặc định.
3. Inner `REQUIRED(timeout=1)` tham gia outer timeout=30: có reset deadline xuống 1 giây không? — **Không**.
4. Inner `REQUIRED` gọi trực tiếp qua proxy khi chưa có outer: ai mở transaction? — **Inner**, dùng thông số của nó.
5. Inner `rollbackFor(IOException.class)` đã mark rollback-only, outer catch lỗi rồi return: có chắc commit không? — **Không**; có thể `UnexpectedRollbackException`.
6. Inner `noRollbackFor(BusinessNotice.class)` nhưng outer không catch lỗi: có thể rollback không? — **Có**, do outer proxy áp rule riêng.
7. Inner `REQUIRES_NEW` commit rồi outer rollback: inner commit có tự bị đảo ngược không? — **Không**, nó độc lập.
8. Bật strict `validateExistingTransaction` khi isolation mâu thuẫn có khiến inner thắng không? — **Không**; có thể báo `IllegalTransactionStateException`.
9. `this.inner()` có mở transaction riêng nhờ annotation inner không? — Thường **không**, vì bypass Spring proxy.
10. Vì sao không đặt `@Transactional` trên test trong lab? — Để transaction của test không che commit/rollback thật của service.

## 11. Kết luận

**Thuộc tính phương thức trong có thể không thay thế cấu hình bên ngoài** khi inner dùng `REQUIRED` và **tham gia transaction vật lý đã có**. Điều đó không phải lỗi ưu tiên annotation: transaction đã mở có isolation, timeout và read-only thuộc phạm vi physical resource; không thể tự đổi bằng cách bước vào một method con.

Phân biệt ba lớp để tránh nhầm:

- **Annotation metadata:** method-level có thể được ưu tiên hơn class-level khi Spring xác định policy của chính method đó.
- **Physical transaction characteristics:** inner `REQUIRED` thường **kế thừa outer**; inner `REQUIRES_NEW` có thể dùng đặc tính riêng.
- **Logical completion rules:** rollback-only và xử lý exception của từng interceptor vẫn có thể tác động lên kết quả chung.

### Tài liệu tham khảo chính thức

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction-bound resources](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework — TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)