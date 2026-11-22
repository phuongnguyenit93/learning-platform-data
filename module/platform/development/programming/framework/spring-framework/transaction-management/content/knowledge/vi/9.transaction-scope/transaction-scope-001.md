# Phân biệt phạm vi logic với giao dịch vật lý trong Spring Framework

## 1. Vì sao cần phân biệt hai khái niệm?

Khi hai service method cùng có `@Transactional`, ta có **hai phạm vi giao dịch logic (logical transaction scopes)**. Tuy nhiên, điều đó **không có nghĩa** hệ quản trị cơ sở dữ liệu đang chạy hai giao dịch vật lý (physical transactions). Với propagation mặc định `REQUIRED`, các phạm vi logic lồng nhau thường **cùng tham gia một giao dịch vật lý**. Đó là nguyên nhân một inner method đã bị bắt lỗi vẫn có thể khiến outer method không commit được.

Một hình dung:

```text
OuterService.outer()       @Transactional(REQUIRED)
│
├── cập nhật dữ liệu A
│
└── InnerService.inner()   @Transactional(REQUIRED)
    └── cập nhật dữ liệu B

Hai lời gọi qua Spring transaction proxy
→ hai logical scopes
→ thường chỉ MỘT physical database transaction.
```

Bài học tập trung vào **Spring Framework transaction management trong mô hình imperative**, ví dụ `@Transactional` + `DataSourceTransactionManager` + `JdbcTemplate`. Các trường hợp JPA, nhiều database, JTA, reactive transaction hoặc message broker có thể có chi tiết cơ chế khác.

**Kết quả cần đạt:**

1. Định nghĩa được transaction logic và transaction vật lý, không đánh đồng số method `@Transactional` với số `Connection.commit()`.
2. Vẽ được sự ánh xạ của `REQUIRED`, `REQUIRES_NEW` và `NESTED` từ logical scopes sang physical transactions.
3. Giải thích vì sao inner `REQUIRED` đánh dấu rollback-only có thể gây `UnexpectedRollbackException` ở outer.
4. Phân biệt **giao dịch vật lý mới** (`REQUIRES_NEW`) với **savepoint trên giao dịch vật lý hiện tại** (`NESTED`).
5. Chạy một dự án Java 17+ để kiểm tra kết quả commit/rollback, trạng thái scope, savepoint và JDBC connection.

## 2. Định nghĩa chính xác

### 2.1. Phạm vi giao dịch logic (logical transaction scope)

Một **logical transaction scope** là ranh giới mà tầng transaction abstraction của Spring gắn với một thao tác được intercept/quản lý, chẳng hạn một lần gọi method có `@Transactional` **qua Spring proxy**. Scope có thể mang cấu hình propagation, rollback rules, read-only, isolation, timeout và trạng thái rollback-only ở mức quản lý giao dịch.

Ví dụ:

```java
@Transactional
public void outer() {
    innerService.inner();
}

@Transactional
public void inner() {
    // Truy cập database.
}
```

Đây là **mã minh họa**, giả định hai method thuộc hai bean khác nhau và lời gọi `innerService.inner()` đi qua transaction proxy. Spring có thể tạo **một logical scope cho `outer()`** và **một logical scope cho `inner()`**.

Hai scope có thể quyết định rollback theo metadata của mình, nhưng chúng **không nhất thiết sở hữu hai giao dịch vật lý riêng**. `inner()` return bình thường cũng **không nhất thiết là database đã commit**: nếu `inner` chỉ tham gia physical transaction do `outer` sở hữu, commit vật lý thường phải chờ boundary ngoài cùng.

Lưu ý: chỉ đếm số annotation trên source code là chưa đủ. Nếu gọi trực tiếp object tạo bằng `new`, gọi `this.inner()` bỏ qua proxy, hoặc chưa kích hoạt transaction infrastructure đúng context, một `@Transactional` có thể **không được intercept**, nên không có logical scope như mô tả.

### 2.2. Giao dịch vật lý (physical transaction)

**Physical transaction** là giao dịch thực tế của tài nguyên, ví dụ một JDBC `Connection` trong chế độ `autoCommit=false` được transaction manager bắt đầu rồi commit/rollback, gắn với khóa, isolation và trạng thái chưa commit của database.

Với JDBC local transaction:

```text
DataSourceTransactionManager
   └── JDBC Connection (transaction-bound)
        ├── SQL UPDATE A
        ├── SQL UPDATE B
        └── COMMIT hoặc ROLLBACK
```

Nhiều repository/service calls có thể cùng dùng connection đó. Nếu tất cả cùng thuộc một physical transaction, database commit/rollback các thao tác của chúng như một đơn vị.

Ngược lại, một logical scope với `REQUIRES_NEW` khi đang có transaction bên ngoài sẽ tạo một physical transaction độc lập. `NESTED` trong cấu hình JDBC savepoint thông thường chỉ tạo **một điểm khôi phục bên trong cùng physical transaction**, không biến thành một independent commit.

### 2.3. Một bảng so sánh

| Tiêu chí | Logical transaction scope | Physical transaction |
| --- | --- | --- |
| Do ai quản lý? | Spring transaction interceptor/transaction abstraction | Transaction manager phối hợp với DB/JDBC resource |
| Ranh giới quan sát | Lời gọi method/callback được quản lý | Begin/join, commit, rollback của giao dịch tài nguyên |
| Số lượng | Có thể nhiều scope lồng nhau | Có thể chỉ một physical transaction cho nhiều scope |
| `rollback-only` | Một scope có thể yêu cầu rollback | Physical transaction cuối cùng không được commit khi đã bị đánh dấu rollback-only |
| `REQUIRED` bên trong transaction có sẵn | Thêm scope tham gia | Dùng chung physical transaction |
| `REQUIRES_NEW` bên trong transaction có sẵn | Thêm scope độc lập | Tạo physical transaction mới, tạm treo scope/tài nguyên bên ngoài |
| `NESTED` bên trong JDBC transaction | Scope lồng nhau với savepoint | Vẫn chung một physical transaction |

**Điểm phải nhớ:** «logical» không có nghĩa giao dịch là giả. Nó là **ranh giới xử lý ở tầng Spring**, ánh xạ tới transaction tài nguyên theo propagation. Còn «physical» cũng không đơn giản bằng việc nhìn thấy một object `Connection`: với connection pool, wrapper/proxy và transaction manager khác nhau, cách quan sát connection có thể thay đổi. Dùng kết quả commit/rollback để xác nhận semantics.

## 3. `PROPAGATION_REQUIRED`: nhiều logic scope, một giao dịch vật lý

`REQUIRED` là propagation mặc định của `@Transactional`.

- Nếu **chưa có** transaction phù hợp, Spring tạo một physical transaction.
- Nếu **đã có** transaction, scope `REQUIRED` mới **tham gia physical transaction hiện tại**, chứ không tạo physical transaction độc lập.
- Mỗi method được intercept vẫn có logical scope riêng, có thể đưa ra quyết định rollback riêng.
- Commit vật lý thường do boundary sở hữu physical transaction thực hiện, không phải mỗi inner `REQUIRED` method tự commit.

```text
                 Một physical transaction T1
     ┌──────────────────────────────────────────┐
     │  Outer logical scope REQUIRED            │
     │  ┌────────────────────────────────────┐  │
     │  │ Inner logical scope REQUIRED       │  │
     │  │ UPDATE B                          │  │
     │  └────────────────────────────────────┘  │
     │  UPDATE A                                │
     └──────────────────────────────────────────┘
                         │
                    COMMIT T1
               hoặc ROLLBACK T1
```

### 3.1. Thành công: outer và inner cùng commit

Giả sử `outer()` cập nhật A, `inner()` cập nhật B. Không có lỗi; inner kết thúc bình thường; outer kết thúc bình thường. Spring có thể sử dụng cùng physical transaction T1 cho cả hai scope. Khi outer boundary thành công, **A và B cùng được commit**.

Việc inner return **chưa** tạo cam kết độc lập cho B. Nếu outer sau đó ném unchecked exception, **A và B đều rollback** bởi T1 chưa commit.

### 3.2. Inner gặp lỗi, outer đã catch nhưng vẫn không commit được

Ví dụ logic:

```java
@Transactional
public void outer() {
    repository.updateA();

    try {
        innerService.requiredAndFail();
    } catch (IllegalStateException ex) {
        // Outer đã xử lý exception ở tầng Java.
    }
    // Outer method hoàn thành bình thường.
}

@Transactional(propagation = Propagation.REQUIRED)
public void requiredAndFail() {
    repository.updateB();
    throw new IllegalStateException("inner failure");
}
```

Đây là **mã minh họa** (cần bean, repository và import phù hợp), với hai service gọi nhau **qua proxy**. Khi exception thoát qua transaction interceptor của inner:

1. Inner `REQUIRED` đang **tham gia physical transaction T1** của outer.
2. Spring áp dụng rollback rule mặc định cho `IllegalStateException` và **đánh dấu T1 rollback-only**. Inner không có một independent physical transaction để rollback riêng.
3. Outer catch exception, nên thân outer có thể tiếp tục/return bình thường.
4. Khi outer interceptor thử commit T1, manager phát hiện rollback-only và **rollback T1**.
5. Vì outer caller tưởng đang commit nhưng thực ra T1 bị rollback, Spring ném **`UnexpectedRollbackException`** trong tình huống chuẩn này.

Vì vậy, **catch exception ở outer không xóa rollback-only**. Ngoại lệ `UnexpectedRollbackException` **không đồng nghĩa Spring tự mở thêm transaction**; ngược lại, nó giúp caller không nhầm rằng dữ liệu đã commit thành công.

**Phân biệt hai trường hợp:**

- Nếu **inner exception được xử lý ngay bên trong inner method** và không thoát tới transaction interceptor (đồng thời không đánh dấu rollback-only), interceptor có thể coi inner kết thúc bình thường, nên không tự yêu cầu rollback từ lỗi đã bị nuốt.
- Nếu exception **đã đi qua inner transaction interceptor**, việc outer catch sau đó không xóa dấu rollback-only của physical transaction. Trong demo mặc định, outer commit sẽ thất bại bằng `UnexpectedRollbackException`.

## 4. `PROPAGATION_REQUIRES_NEW`: physical transaction độc lập

Với `REQUIRES_NEW`:

1. Nếu outer T1 đang chạy, Spring **tạm treo tài nguyên gắn với T1** ở thread hiện tại.
2. Spring mở **physical transaction T2 mới** cho inner scope.
3. Inner commit hoặc rollback **T2** độc lập.
4. Sau khi inner kết thúc, Spring khôi phục T1 để outer tiếp tục.
5. Outer quyết định commit/rollback T1 riêng.

```text
Outer logical scope                 Inner logical scope
      │                                   │
  Physical T1 ── SUSPEND ────────→ Physical T2 (NEW)
      │                                   │
      │                            COMMIT/ROLLBACK T2
      │                                   │
  Physical T1 ←── RESUME ────────────────┘
      │
  COMMIT/ROLLBACK T1
```

**Hệ quả quan trọng:**

- Inner T2 bị rollback **không tự làm T1 rollback-only** theo cơ chế `REQUIRES_NEW`. Nếu outer bắt lỗi và tiếp tục, T1 có thể commit.
- Inner T2 **đã commit** thì outer T1 rollback sau đó **không thể hoàn tác commit của T2**.
- T2 có thể có isolation, timeout, read-only settings độc lập của nó.
- Với JDBC connection pool, outer thường giữ một connection trong khi inner cần **connection khác**. Dùng `REQUIRES_NEW` bừa bãi có thể gây thiếu connection hoặc deadlock ở tải cao; pool cần đủ sức chứa số transaction lồng nhau/đồng thời.

Ví dụ: thanh toán outer rollback nhưng inner ghi audit bằng `REQUIRES_NEW` đã commit. Điều này đôi khi được mong muốn với audit độc lập, nhưng không phù hợp nếu dữ liệu inner **phải** rollback cùng outer. Không chọn `REQUIRES_NEW` chỉ vì muốn «chắc chắn có transaction».

## 5. `PROPAGATION_NESTED`: một physical transaction, nhiều savepoint

Trong trường hợp **JDBC transaction manager hỗ trợ savepoints**, `NESTED` có thể đặt **savepoint** trên chính connection của physical transaction T1 hiện có. Nếu inner thất bại, Spring rollback về savepoint; outer có thể tiếp tục mà không cần rollback mọi thay đổi trước đó.

```text
Một physical transaction T1
  BEGIN T1
    UPDATE A (outer)
    SAVEPOINT S1
      UPDATE B (inner nested)
      nếu lỗi: ROLLBACK TO S1  ← chỉ hủy thay đổi sau S1
    outer tiếp tục
  COMMIT T1 (nếu toàn bộ T1 vẫn hợp lệ)
```

**Phân biệt rất kỹ với `REQUIRES_NEW`:**

- `NESTED` dùng **cùng physical transaction**, thêm savepoint, không phải T2 độc lập.
- Inner nested kết thúc thành công **không commit vật lý riêng**; nếu outer rollback, thay đổi B cũng bị rollback.
- Inner nested thất bại có thể rollback riêng phần sau savepoint để outer tiếp tục commit A.
- Nếu outer cuối cùng rollback, mọi thay đổi còn lại trong T1 — cả A và phần B chưa rollback — đều bị hủy.

Hỗ trợ `NESTED` **phụ thuộc transaction manager và tài nguyên**. Ví dụ `DataSourceTransactionManager` với JDBC driver hỗ trợ savepoints phù hợp bài lab. Không mặc định áp dụng giống hệt cho mọi `JpaTransactionManager`, R2DBC, JTA hay transaction phân tán. Nếu savepoint/manager không hỗ trợ, cấu hình có thể báo lỗi thay vì tự biến `NESTED` thành `REQUIRES_NEW`.

### 5.1. Bảng nhìn nhanh

| Quan sát | `REQUIRED` (inner tham gia outer) | `REQUIRES_NEW` | `NESTED` (JDBC savepoint) |
| --- | --- | --- | --- |
| Physical transaction khi inner chạy | Cùng T1 | T2 mới; T1 tạm treo | Cùng T1 |
| JDBC connection trong demo | Cùng connection | Connection khác | Cùng connection |
| Inner `TransactionStatus.isNewTransaction()` | `false` | `true` | `false` |
| Inner `TransactionStatus.hasSavepoint()` | `false` | `false` | `true` |
| Inner unchecked exception, outer catch | T1 có thể rollback-only → outer `UnexpectedRollbackException` | T2 rollback; T1 vẫn có thể commit | Rollback về savepoint; T1 có thể commit |
| Inner thành công, outer sau đó rollback | Cả A/B rollback | T2 đã commit vẫn giữ B | Cả A/B rollback |
| Chi phí/tài nguyên | Dùng chung T1 | Physical transaction/connection riêng | Savepoint trên T1 |

Các giá trị `TransactionStatus` trong bảng giả định inner thực sự được Spring intercept và outer **đã có transaction**. Nếu gọi `inner` trực tiếp không qua proxy hoặc chưa có transaction bên ngoài, kết quả khác. Đặc biệt `NESTED` khi không có transaction hiện có có thể phải bắt đầu transaction mới thay vì tạo savepoint.

## 6. Demo kiểm chứng bằng JDBC: Java 17, Spring Framework, H2

Ta sẽ có 2 counters, mỗi counter ban đầu bằng 0:

- `outer` được outer service tăng trước khi gọi inner.
- `inner` được inner service tăng bên trong logical scope của từng propagation.
- Chủ động ném `IllegalStateException` để kiểm tra rollback.
- Mỗi case reset bảng, nên số liệu có thể so sánh trực tiếp.

Demo gồm **sáu case**:

| Case | Inner propagation | Điều cố ý xảy ra | Kết quả sau transaction |
| --- | --- | --- | --- |
| 1. `REQUIRED success` | `REQUIRED` | Không lỗi | outer=1, inner=1 |
| 2. `REQUIRED inner failure` | `REQUIRED` | Inner lỗi, outer catch | outer=0, inner=0; outer nhận `UnexpectedRollbackException` |
| 3. `REQUIRES_NEW inner failure` | `REQUIRES_NEW` | Inner T2 rollback, outer T1 tiếp tục | outer=1, inner=0 |
| 4. `NESTED inner failure` | `NESTED` | Inner rollback về savepoint, outer tiếp tục | outer=1, inner=0 |
| 5. `REQUIRES_NEW inner commits, outer fails` | `REQUIRES_NEW` | Inner T2 commit, outer T1 rollback | outer=0, inner=1 |
| 6. `NESTED inner succeeds, outer fails` | `NESTED` | Savepoint scope thành công nhưng T1 rollback | outer=0, inner=0 |

Bảng cho thấy chỉ nhìn kết quả của case 3 và 4 thì chưa đủ phân biệt `REQUIRES_NEW` với `NESTED`; phải xét **physical transaction** và trường hợp **inner commit rồi outer rollback** (case 5 so với 6).

### 6.1. Cấu trúc project

```text
logical-physical-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── LogicalPhysicalDemo.java
```

Không cần Spring Boot, web server hay database server. H2 chạy trong cùng JVM. Dùng dependency cố định để dễ tái lập ví dụ.

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>logical-physical-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
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
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.LogicalPhysicalDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích:** `spring-context` tạo và inject bean; `spring-jdbc` cung cấp JDBC transaction manager/JdbcTemplate; `spring-tx` có propagation, `@Transactional` và transaction status; H2 là JDBC database. `h2` ở compile classpath vì file Java dùng trực tiếp `JdbcDataSource`. Các phiên bản cố định cho ví dụ; trong hệ thống thật nên dùng BOM và quản lý dependency/security updates tập trung.

### 6.3. `src/main/java/example/LogicalPhysicalDemo.java`

```java
package example;

import java.sql.Connection;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class LogicalPhysicalDemo {

    private enum Mode {
        REQUIRED, REQUIRES_NEW, NESTED
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OuterService service = context.getBean(OuterService.class);

            runCase("REQUIRED success", jdbc, service::requiredSuccess);
            runCase("REQUIRED inner failure", jdbc, service::requiredInnerFails);
            runCase(
                "REQUIRES_NEW inner failure",
                jdbc,
                service::requiresNewInnerFails
            );
            runCase("NESTED inner failure", jdbc, service::nestedInnerFails);
            runCase(
                "REQUIRES_NEW inner commits, outer fails",
                jdbc,
                service::requiresNewCommitsOuterFails
            );
            runCase(
                "NESTED inner succeeds, outer fails",
                jdbc,
                service::nestedSucceedsOuterFails
            );
        }
    }

    private static void runCase(String label, JdbcTemplate jdbc, Runnable work) {
        reset(jdbc);
        System.out.println("CASE: " + label);

        try {
            work.run(); // Gọi public @Transactional method qua Spring proxy.
            System.out.println("Outcome: COMMITTED");
        } catch (UnexpectedRollbackException ex) {
            System.out.println("Outcome: UnexpectedRollbackException");
        } catch (IllegalStateException ex) {
            System.out.println("Outcome: " + ex.getMessage());
        }

        Integer outer = jdbc.queryForObject(
            "SELECT n FROM counters WHERE counter_key = 'outer'",
            Integer.class
        );
        Integer inner = jdbc.queryForObject(
            "SELECT n FROM counters WHERE counter_key = 'inner'",
            Integer.class
        );
        System.out.println("Values: outer=" + outer + ", inner=" + inner);
    }

    private static void reset(JdbcTemplate jdbc) {
        // Mỗi case chạy trên dữ liệu ban đầu độc lập.
        jdbc.execute("DROP TABLE IF EXISTS counters");
        jdbc.execute(
            "CREATE TABLE counters (" +
            "counter_key VARCHAR(16) PRIMARY KEY, n INT NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO counters (counter_key, n) VALUES ('outer', 0)"
        );
        jdbc.update(
            "INSERT INTO counters (counter_key, n) VALUES ('inner', 0)"
        );
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:logical_physical;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
            DataSource dataSource
        ) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public InnerService innerService(JdbcTemplate jdbc, DataSource ds) {
            return new InnerService(jdbc, ds);
        }

        @Bean
        public OuterService outerService(
            JdbcTemplate jdbc,
            DataSource ds,
            InnerService inner
        ) {
            return new OuterService(jdbc, ds, inner);
        }
    }

    // Bean riêng để outer gọi inner QUA PROXY, tránh self-invocation.
    public static class InnerService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;

        public InnerService(JdbcTemplate jdbc, DataSource dataSource) {
            this.jdbc = jdbc;
            this.dataSource = dataSource;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void required(Connection outerConnection, boolean fail) {
            updateInner("REQUIRED", outerConnection, fail);
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNew(Connection outerConnection, boolean fail) {
            updateInner("REQUIRES_NEW", outerConnection, fail);
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nested(Connection outerConnection, boolean fail) {
            updateInner("NESTED", outerConnection, fail);
        }

        private void updateInner(
            String mode,
            Connection outerConnection,
            boolean fail
        ) {
            TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();

            Connection innerConnection =
                DataSourceUtils.getConnection(dataSource);
            boolean sameConnection;
            try {
                sameConnection = innerConnection == outerConnection;
            } finally {
                DataSourceUtils.releaseConnection(innerConnection, dataSource);
            }

            System.out.println(
                "Inner " + mode
                + ": active="
                + TransactionSynchronizationManager.isActualTransactionActive()
                + ", new=" + status.isNewTransaction()
                + ", savepoint=" + status.hasSavepoint()
                + ", sameConnection=" + sameConnection
            );

            int updated = jdbc.update(
                "UPDATE counters SET n = n + 1 WHERE counter_key = 'inner'"
            );
            if (updated != 1) {
                throw new IllegalStateException("missing inner row");
            }

            if (fail) {
                throw new IllegalStateException("inner failure");
            }
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;
        private final InnerService inner;

        public OuterService(
            JdbcTemplate jdbc,
            DataSource dataSource,
            InnerService inner
        ) {
            this.jdbc = jdbc;
            this.dataSource = dataSource;
            this.inner = inner;
        }

        @Transactional
        public void requiredSuccess() {
            execute(Mode.REQUIRED, false, false);
        }

        @Transactional
        public void requiredInnerFails() {
            execute(Mode.REQUIRED, true, false);
        }

        @Transactional
        public void requiresNewInnerFails() {
            execute(Mode.REQUIRES_NEW, true, false);
        }

        @Transactional
        public void nestedInnerFails() {
            execute(Mode.NESTED, true, false);
        }

        @Transactional
        public void requiresNewCommitsOuterFails() {
            execute(Mode.REQUIRES_NEW, false, true);
        }

        @Transactional
        public void nestedSucceedsOuterFails() {
            execute(Mode.NESTED, false, true);
        }

        private void execute(
            Mode mode,
            boolean failInner,
            boolean failOuter
        ) {
            // Ghi outer trong physical transaction do outer proxy mở.
            int updated = jdbc.update(
                "UPDATE counters SET n = n + 1 WHERE counter_key = 'outer'"
            );
            if (updated != 1) {
                throw new IllegalStateException("missing outer row");
            }

            // Chỉ phục vụ quan sát connection trong JDBC demo.
            Connection outerConnection =
                DataSourceUtils.getConnection(dataSource);
            try {
                try {
                    switch (mode) {
                        case REQUIRED ->
                            inner.required(outerConnection, failInner);
                        case REQUIRES_NEW ->
                            inner.requiresNew(outerConnection, failInner);
                        case NESTED ->
                            inner.nested(outerConnection, failInner);
                    }
                } catch (IllegalStateException ex) {
                    // Cố ý xử lý lỗi inner để xem outer có commit được không.
                    System.out.println("Outer caught: " + ex.getMessage());
                }
            } finally {
                DataSourceUtils.releaseConnection(outerConnection, dataSource);
            }

            if (failOuter) {
                throw new IllegalStateException("outer failure");
            }
        }
    }
}
```

**Vì sao dự án dùng hai service beans?** `OuterService` gọi `InnerService` được inject từ Spring; lời gọi inner đi **qua proxy**, nên Spring tạo logical scope tương ứng. Nếu đưa cả hai method vào cùng bean rồi gọi bằng `this.inner()`, proxy mode thông thường không intercept self-invocation; kết luận so sánh propagation sẽ sai.

**Vì sao dùng `DataSourceUtils.getConnection`?** Đây là cách lấy connection có ý thức về tài nguyên đang được Spring binding vào thread. Trong demo H2 không pool, ta giữ tham chiếu connection outer và so sánh với connection inner: `true` khi cùng connection vật lý của outer, `false` khi `REQUIRES_NEW` yêu cầu connection khác. Việc **truyền `Connection` làm tham số trong bài lab chỉ để quan sát**; đừng thiết kế nghiệp vụ production bằng cách chuyền JDBC connection giữa service methods. Với proxy/connection pool khác, so sánh `==` có thể không phải phép đo phổ quát; semantics commit/rollback mới là bằng chứng cuối.

`TransactionAspectSupport.currentTransactionStatus()` đọc trạng thái của **intercepted inner method hiện tại**. Vì method `updateInner` được gọi từ bên trong method inner đã được proxy intercept, việc đọc status trong helper này là hợp lệ. `status.isNewTransaction()` cho biết scope đó có khởi tạo transaction mới không; `status.hasSavepoint()` cho biết scope có savepoint; cả hai **không nên thay thế** việc quan sát dữ liệu sau transaction.

### 6.4. Chạy project

Cài **JDK 17+** và **Maven 3.9+**; Maven cần tải dependencies từ repository khi chưa có trong cache. Tại thư mục `logical-physical-demo`:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Các dòng do **chương trình** in ra theo thứ tự (không tính log từ Maven/Spring nếu môi trường bổ sung):

```text
CASE: REQUIRED success
Inner REQUIRED: active=true, new=false, savepoint=false, sameConnection=true
Outcome: COMMITTED
Values: outer=1, inner=1
CASE: REQUIRED inner failure
Inner REQUIRED: active=true, new=false, savepoint=false, sameConnection=true
Outer caught: inner failure
Outcome: UnexpectedRollbackException
Values: outer=0, inner=0
CASE: REQUIRES_NEW inner failure
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer caught: inner failure
Outcome: COMMITTED
Values: outer=1, inner=0
CASE: NESTED inner failure
Inner NESTED: active=true, new=false, savepoint=true, sameConnection=true
Outer caught: inner failure
Outcome: COMMITTED
Values: outer=1, inner=0
CASE: REQUIRES_NEW inner commits, outer fails
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outcome: outer failure
Values: outer=0, inner=1
CASE: NESTED inner succeeds, outer fails
Inner NESTED: active=true, new=false, savepoint=true, sameConnection=true
Outcome: outer failure
Values: outer=0, inner=0
```

### 6.5. Diễn giải từng case

**Case 1 — REQUIRED success:** Outer transaction T1 bắt đầu; inner `REQUIRED` join T1, nên `new=false` và `sameConnection=true`. Inner return bình thường. Outer return bình thường; T1 commit cả hai thay đổi, được `(outer=1, inner=1)`.

**Case 2 — REQUIRED inner failure:** Inner đã cập nhật `inner` rồi ném unchecked exception. Transaction interceptor của inner đánh dấu **physical T1** rollback-only. Outer catch exception nhưng không xóa rollback-only. Khi outer boundary muốn commit, Spring rollback toàn bộ T1 rồi ném `UnexpectedRollbackException`. Kết quả cả hai giá trị đều 0.

**Case 3 — REQUIRES_NEW inner failure:** Outer T1 được tạm treo; inner T2 mới dùng connection khác, `new=true`. Inner ném lỗi nên rollback T2. Outer catch lỗi, tiếp tục và commit T1. Kết quả `(outer=1, inner=0)`. T1 không bị inner T2 mặc định đánh dấu rollback-only.

**Case 4 — NESTED inner failure:** Inner dùng savepoint trong **cùng T1**, nên `savepoint=true` và `sameConnection=true`. Lỗi khiến Spring rollback những ghi sau savepoint; outer catch, rồi commit T1. Kết quả cũng `(outer=1, inner=0)`, nhưng **không có T2** như case 3.

**Case 5 — REQUIRES_NEW inner commits, outer fails:** T2 của inner hoàn tất bình thường và **commit trước** khi outer throw. Outer T1 sau đó rollback, chỉ hủy cập nhật outer. Giá trị inner=1 vẫn tồn tại. Đây là dấu hiệu quan trọng của **independent physical transaction**.

**Case 6 — NESTED inner succeeds, outer fails:** Inner hoàn tất nhưng chỉ giải quyết savepoint scope; không có commit vật lý riêng. Outer ném lỗi nên rollback cả T1, hủy cả thay đổi outer và inner. Đây là dấu hiệu rõ nhất rằng `NESTED` **không giống** `REQUIRES_NEW`.

## 7. Hiểu rollback-only và `UnexpectedRollbackException` cho đúng

### 7.1. Rollback-only không có nghĩa rollback đã xảy ra ngay

Khi một participating `REQUIRED` scope yêu cầu rollback, transaction manager có thể **đánh dấu physical transaction là rollback-only**, để không cho commit sai vào cuối. Trong thời gian outer scope còn chạy, một số SQL trước đó vẫn là thay đổi chưa commit trong transaction. Rollback thực sự xảy ra khi manager kết thúc physical transaction (hoặc khi hệ quản trị DB ép kết thúc sớm vì lỗi nghiêm trọng).

```text
T1 bắt đầu
  Outer ghi A
  Inner REQUIRED ghi B
  Inner ném RuntimeException
  Inner proxy đánh dấu T1 rollback-only
  Outer catch lỗi và return
  Outer proxy cố kết thúc T1
  -> ROLLBACK T1
  -> UnexpectedRollbackException báo cho caller
```

Đây là ví dụ theo mặc định của `DataSourceTransactionManager`/`@Transactional`. Không nên suy rộng rằng **mọi exception** hoặc **mọi catch** đều tạo `UnexpectedRollbackException`. Nếu inner không bị advice intercept, exception không thỏa rollback rule, rollback-only không được đặt, hoặc outer đã chủ động rollback theo luồng khác, kết quả có thể thay đổi.

### 7.2. Vì sao thông báo exception xuất hiện ở boundary ngoài?

Trong `REQUIRED` tham gia transaction, inner không sở hữu independent physical commit. Outer có quyền kết thúc T1. Vì vậy inner method có thể kết thúc bằng exception ban đầu mà outer bắt được; **chỉ tới lần outer cố commit** mới thấy rollback-only khiến Spring ném `UnexpectedRollbackException`. Spring làm vậy để caller không hiểu lầm một method return bình thường là dữ liệu đã được commit.

### 7.3. Những cách xử lý đúng

- Nếu lỗi inner khiến cả use case không còn hợp lệ, thường nên **để exception truyền lên** để outer rollback thay vì catch rồi trả thành công.
- Nếu một phần thao tác có thể hủy cục bộ mà outer vẫn hợp lệ, cân nhắc **`NESTED` + savepoint** khi tài nguyên hỗ trợ, hoặc refactor nghiệp vụ rõ thành nhiều bước.
- Nếu inner cần commit/rollback hoàn toàn độc lập, cân nhắc **`REQUIRES_NEW`**, nhưng cần xác định rõ rằng inner commit **không bị outer rollback**.
- Nếu muốn transaction rollback dù đã bắt lỗi trong cùng scope, có thể chủ động đánh dấu rollback-only qua transaction API phù hợp; phải hiểu kết quả đối với caller và boundary ngoài.
- Không «chữa» bằng cách catch cả `UnexpectedRollbackException` rồi trả kết quả thành công: **database đã rollback**, và nghiệp vụ phải báo trạng thái trung thực.

## 8. Những điều propagation không tự giải quyết

### 8.1. Thay đổi isolation, timeout ở inner `REQUIRED`

Khi inner `REQUIRED` tham gia physical transaction do outer mở, nó **không có một connection transaction mới** để tự áp dụng độc lập mọi isolation/read-only/timeout khác. Đặc tính vật lý đang hoạt động thường từ outer transaction. Spring transaction manager có thể được cấu hình `validateExistingTransaction=true` để phát hiện khai báo isolation/read-only không tương thích thay vì im lặng tham gia.

`REQUIRES_NEW` vì có T2 riêng nên có thể khai báo isolation, timeout và read-only riêng cho T2. `NESTED` dùng chung T1 nên savepoint không tạo một DB isolation độc lập.

### 8.2. Lời gọi phải thực sự qua proxy

`@Transactional` trong proxy mode chỉ có tác dụng khi method call đi qua Spring proxy. Mã sai quen thuộc:

```java
public void outer() {
    inner(); // Self-invocation trong cùng object: bỏ qua transaction proxy cho inner.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void inner() {
    // Không nhất thiết có independent T2 nếu gọi trực tiếp bằng this.inner().
}
```

Đoạn trên là **minh họa**, không phải ứng dụng độc lập. Cách rõ ràng là đặt các inner transactional methods vào **bean khác** và gọi qua bean được inject, như `OuterService` và `InnerService` trong demo. Đặt `@Transactional` lên private method, object tự tạo bằng `new` hoặc sai `ApplicationContext` cũng có thể khiến advice không chạy.

### 8.3. Mỗi thread/reactive context có mô hình khác

Spring transaction **imperative** thường gắn tài nguyên JDBC với thread hiện tại. Đừng tự mở `new Thread`, `@Async` hay `CompletableFuture` rồi giả định T1 tự chuyển sang luồng mới. Với reactive R2DBC, transaction thường gắn với Reactor Context qua `ReactiveTransactionManager`, không áp dụng nguyên xi cách kiểm tra JDBC thread-bound trong demo.

### 8.4. Transaction manager và tài nguyên phải tương thích

`DataSourceTransactionManager` chỉ kiểm soát những JDBC connection tham gia cùng datasource. Không suy luận rằng rollback T1 sẽ hoàn tác email đã gửi, HTTP request, Kafka event không giao dịch chung, hoặc update database khác nếu không có phối hợp transaction phù hợp. `REQUIRES_NEW` không tự biến việc tích hợp nhiều hệ thống thành atomic distributed transaction.

### 8.5. Khi nhiều transaction manager cùng tồn tại

Một `@Transactional` có thể được gắn manager cụ thể qua `transactionManager`/`value`. Các method dùng **khác manager hoặc datasource** sẽ không mặc nhiên cùng một physical transaction, dù có cùng `REQUIRED`. Phải xác định tài nguyên/manager thật sự được dùng; tránh suy từ annotation một cách đơn độc.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Câu hỏi kiểm tra | Gợi ý xử lý |
| --- | --- | --- |
| Inner `@Transactional` return rồi outer lỗi khiến dữ liệu inner mất | Inner có đang `REQUIRED` chung T1 không? | Đây là hành vi atomic bình thường; cân nhắc `REQUIRES_NEW` chỉ khi cần commit độc lập. |
| Outer catch inner exception nhưng vẫn nhận `UnexpectedRollbackException` | Inner đã đánh dấu cùng T1 rollback-only chưa? | Đừng giả định catch xóa rollback-only; điều chỉnh transaction boundary/propagation theo nghiệp vụ. |
| `REQUIRES_NEW` nhưng inner rollback làm outer rollback theo | Outer có để exception tiếp tục thoát khỏi method? | Independent T2 không ngăn outer tự rollback nếu unchecked exception không được xử lý ở boundary outer. |
| `NESTED` không hoạt động hoặc báo không hỗ trợ | Transaction manager/JDBC driver có savepoint không? | Xác minh JDBC savepoint support và cấu hình; không thay `NESTED` bằng `REQUIRES_NEW` mà không cân nhắc semantics. |
| Gắn `REQUIRES_NEW` nhưng vẫn thấy chung transaction | Lời gọi inner có qua proxy không? | Tách bean, inject đúng reference, tránh self-invocation. |
| Ứng dụng treo khi nhiều `REQUIRES_NEW` | Pool còn connection dự phòng khi outer giữ connection không? | Giới hạn nested usage, size pool hợp lý, đo concurrency. |
| Inner `REQUIRED` khai báo isolation riêng nhưng không tác dụng | Inner có đang join outer physical T1? | Cấu hình ở outer hoặc dùng manager validation; không mong tạo connection mới. |
| Test pass nhưng production rollback khác | Test có một test-managed transaction bao ngoài không? | Kiểm tra boundary và readback sau commit/rollback thực tế. |

### 9.1. Những dấu hiệu cần quan sát trong log/test

- **Service reference** có phải proxy được Spring tạo? Với code chẩn đoán, có thể dùng `AopUtils.isAopProxy(bean)`, nhưng proxy có thể là advice khác transaction.
- `TransactionSynchronizationManager.isActualTransactionActive()` có đúng lúc method đang chạy không?
- `TransactionAspectSupport.currentTransactionStatus().isNewTransaction()` và `hasSavepoint()` có đúng với propagation mong đợi không? Chỉ gọi khi thực sự có transaction invocation context.
- Kết quả **database sau khi outer boundary kết thúc** là gì? Đừng chỉ dựa trên việc inner đã chạy SQL hay log in ra trước commit.
- Có exception bị swallow, checked exception không nằm trong rollback rules, hoặc database resource không tham gia đúng manager không?
- Có transaction-level timeout, lock, isolation mismatch hoặc connection pool contention không?

## 10. Bài tập tư duy và thí nghiệm thêm

1. **Hai logical scopes, một physical transaction:** vẽ sơ đồ khi outer `@Transactional` gọi inner `@Transactional(REQUIRED)`. Giải thích vì sao cả hai method có annotation nhưng chỉ một lần commit vật lý.
2. **Catch không phải rollback:** sửa demo để inner `REQUIRED` tự catch exception **trước khi exception thoát ra khỏi inner method**. Dự đoán trạng thái rollback-only và so sánh với case 2.
3. **Khác nhau giữa NESTED và REQUIRES_NEW:** chỉ dùng case 3 và 4 sẽ thấy số cuối giống nhau. Dùng case 5/6 để chứng minh physical independence của `REQUIRES_NEW`.
4. **Outer không catch:** sửa case 3 để outer không catch inner T2 failure. Dù T2 độc lập, outer cũng có thể rollback do unchecked exception tiếp tục thoát khỏi outer transaction interceptor. Việc độc lập vật lý không ngăn rollback theo chính sách ở boundary outer.
5. **Thay nguồn exception:** đổi `IllegalStateException` thành checked exception phù hợp chữ ký method; tìm hiểu `@Transactional(rollbackFor = ...)` và dự đoán sự thay đổi theo rollback rules.
6. **Thay datasource:** tìm hiểu vì sao inner `REQUIRES_NEW` với connection pool nhỏ có nguy cơ chờ connection dù outer đang giữ một connection.
7. **Đọc trạng thái chính xác:** thử log `TransactionStatus` ở outer và inner; giải thích vì sao outer `isNewTransaction=true` còn inner `REQUIRED` `isNewTransaction=false`, dù cả hai nằm trong một giao dịch vật lý.

### Tự kiểm tra nhanh

- Một method `@Transactional(REQUIRED)` được gọi từ trong transaction đang chạy có chắc mở physical transaction mới không?
- Inner `REQUIRED` yêu cầu rollback-only, outer catch exception rồi return bình thường: vì sao caller còn có thể nhận `UnexpectedRollbackException`?
- Inner `REQUIRES_NEW` đã commit, outer sau đó rollback: kết quả inner có bị hủy không?
- Inner `NESTED` thành công, outer rollback: kết quả inner có còn không?
- Một JDBC savepoint có tương đương một physical transaction độc lập không?

**Câu trả lời cốt lõi:** `REQUIRED` tạo các **logical scopes tham gia chung physical transaction**; `REQUIRES_NEW` tạo **physical transaction riêng**; `NESTED` thường tạo **savepoint trong cùng physical transaction JDBC**. Không nên chọn propagation chỉ theo tên gọi: hãy quyết định dựa trên **dữ liệu nào phải commit/rollback cùng nhau** và kiểm tra bằng hành vi transaction thực tế.

## 11. Nguồn tham khảo

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): mô tả trực tiếp logical/physical scopes, `REQUIRED`, `REQUIRES_NEW`, `NESTED`, rollback-only và `UnexpectedRollbackException`.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation/rollback defaults và cấu hình annotation.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): proxy/interceptor và transaction boundaries.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): hành vi rollback và rollback rules.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`/`PlatformTransactionManager` và phạm vi quản lý bằng mã.
