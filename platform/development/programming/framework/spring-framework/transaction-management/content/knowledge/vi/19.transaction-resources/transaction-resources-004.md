# Dùng cùng tài nguyên giữa nhiều lớp truy cập dữ liệu trong Spring Transaction Management

## 1. Mục tiêu của bài học

Một transaction nghiệp vụ hiếm khi chỉ gọi một câu SQL. Nó thường đi qua **service → nhiều DAO/repository → JDBC/ORM**. Yêu cầu quan trọng là các thao tác thuộc **cùng ranh giới giao dịch** phải cùng tham gia transaction do Spring quản lý, thay vì mỗi DAO âm thầm mở kết nối riêng và tự commit.

Ví dụ, khi một yêu cầu chuyển tiền cần ghi:

1. Bản ghi thay đổi số dư qua `AccountDao`.
2. Bản ghi giao dịch qua `TransactionDao`.
3. Audit log trong cùng database qua `AuditDao`.

Nếu tất cả thuộc **một transaction vật lý**, chúng phải cùng commit hoặc cùng rollback. Việc code được chia thành ba lớp Java **không** buộc Spring tạo ba transaction. Điều quyết định là **transaction boundary, transaction manager, datasource/resource factory và cách mỗi lớp lấy tài nguyên**.

Sau bài học, bạn sẽ có thể:

- Giải thích tài nguyên **gắn với transaction** (transaction-bound resource), `ConnectionHolder` và `TransactionSynchronizationManager`.
- Hiểu vì sao nhiều `JdbcTemplate` hoặc nhiều DAO dùng **cùng `DataSource`** có thể sử dụng **cùng JDBC `Connection` trong một transaction**.
- Phân biệt việc dùng **cùng datasource/connection pool** với việc thực sự dùng **cùng physical transaction**.
- Dùng `DataSourceUtils.getConnection()` / `releaseConnection()` đúng cách khi phải viết JDBC thấp tầng; biết khi nào dùng `TransactionAwareDataSourceProxy`.
- Thiết kế tầng service với `@Transactional`, phân biệt `REQUIRED`, `REQUIRES_NEW` và `NESTED` đối với resource hiện hành.
- Kiểm chứng “cùng tài nguyên” bằng **một ví dụ Java 17 chạy được với Spring JDBC/H2**: nhiều DAO, một bean inner có `REQUIRED`, cùng connection, read-your-writes, rollback đồng bộ; có phản ví dụ kết nối thô thoát transaction.
- Nhận diện trường hợp dùng JPA/Hibernate, MyBatis, nhiều datasource, JTA, `@Async` hoặc reactive transactions, nơi chữ “cùng transaction” cần được hiểu chính xác hơn.

**Kết luận trước:** Trong JDBC transaction địa phương của Spring, `DataSourceTransactionManager`/`JdbcTransactionManager` có thể **bind một connection theo datasource vào thread đang thực thi transaction**. Các lớp truy cập dữ liệu dùng API *transaction-aware* và cùng datasource sẽ lấy lại resource đó. Nhưng `dataSource.getConnection()` thô hoặc một datasource/transaction manager khác có thể thoát khỏi sự quản lý ấy.

## 2. Phân biệt: cùng object, cùng datasource, cùng transaction

Ba khẳng định sau **không tương đương**:

- **Cùng DAO instance:** hai service có thể inject chung một bean `AccountDao`. Bean được chia sẻ **không có nghĩa** mọi request dùng cùng connection; một singleton DAO thường phục vụ nhiều threads và nhiều transactions khác nhau.
- **Cùng `DataSource`:** hai DAO có thể dùng cùng bean datasource hoặc cùng connection pool. Nếu chúng chạy tại thời điểm khác nhau hoặc không có transaction Spring, mỗi SQL có thể lấy **connection khác** và commit riêng.
- **Cùng physical transaction:** các SQL thật sự thuộc cùng một transaction database; với local JDBC manager và cùng datasource, chúng thường chạy trên **cùng connection đang được bind cho thread/transaction**.

Ví dụ với hai request đồng thời:

```text
Request A (thread A)              Request B (thread B)
---------------------------       ---------------------------
@Service @Transactional           @Service @Transactional
          |                                 |
  JdbcTransactionManager               cùng manager
          |                                 |
DataSource -> Connection A         DataSource -> Connection B
          |                                 |
 AccountDao / AuditDao               AccountDao / AuditDao
  dùng resource A                     dùng resource B
          |                                 |
commit/rollback A                   commit/rollback B
```

Hai request cùng dùng **singleton DAO và datasource**, nhưng **không** được dùng chung physical connection cùng lúc. Chỉ các thao tác đang chạy **trong transaction tương ứng** cần tái sử dụng tài nguyên đã bind của chính chúng.

Trong một request:

```text
TransferService.transfer()  @Transactional(REQUIRED)
            |
            v
JdbcTransactionManager mở transaction T
            |
            +-- bind DataSource X -> ConnectionHolder(Connection C)
            |
            +-- AccountDao:
            |     JdbcTemplate(X)  -> Connection C
            |
            +-- AuditDao:
            |     JdbcTemplate(X)  -> Connection C
            |
            +-- LegacyJdbcDao:
            |     DataSourceUtils.getConnection(X) -> Connection C
            |
            +-- TẤT CẢ SQL cùng trong physical transaction T
            |
            +-- commit hoặc rollback T một lần ở boundary service
```

Điểm quan trọng: “dùng cùng tài nguyên” ở đây mô tả **cùng physical JDBC transaction**, không phải nhiều JDBC `Statement` cùng instance, không phải chỉ cùng DB URL, và không phải giữ một JDBC connection toàn cục để các thread dùng chung.

## 3. Cơ chế gắn tài nguyên với transaction

### 3.1. Vai trò của transaction manager

Với một cơ sở dữ liệu JDBC địa phương, Spring cung cấp `DataSourceTransactionManager` và subclass `JdbcTransactionManager`:

1. Khi bắt đầu **physical transaction mới**, manager lấy một `Connection` từ datasource đã cấu hình.
2. Manager chuẩn bị connection: ví dụ isolation, read-only hint và trạng thái auto-commit phù hợp.
3. Nó đặt connection vào một `ConnectionHolder`.
4. Thông qua `TransactionSynchronizationManager`, holder được **gắn với thread theo key của datasource** (resource binding).
5. Những lớp truy cập dữ liệu có nhận biết Spring transaction tìm resource đã bind trước khi tự lấy connection mới.
6. Khi transaction hoàn tất, manager commit/rollback, dọn binding, khôi phục trạng thái connection khi cần rồi release connection về datasource/pool.

Có thể hình dung:

```text
ThreadLocal resource map (mô hình khái niệm)
+----------------------------------------------------------+
| key: DataSource X                                        |
| value: ConnectionHolder -> Connection C (transaction T) |
+----------------------------------------------------------+

TransactionSynchronizationManager:
  getResource(X) -> holder của T khi đang bind
  hasResource(X) -> true nếu resource X đã bind
```

Đây là **cơ chế hạ tầng**, không phải nơi business code nên tự gọi `bindResource()` hay `unbindResource()` để tạo transaction. Việc tự can thiệp có thể làm rối trạng thái binding, đóng/mất kết nối sai thời điểm, hoặc khiến transaction manager không thể cleanup.

### 3.2. Resource-bound không đồng nghĩa với database commit

`TransactionSynchronizationManager.isActualTransactionActive()` biểu thị actual transaction hiện hành theo ngữ cảnh Spring. `isSynchronizationActive()` cho biết resource synchronization đang active. Hai chỉ báo này không đồng nghĩa nhau trong mọi propagation/configuration; đặc biệt synchronization có thể hoạt động ngoài physical transaction.

Chỉ nhìn thấy:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

chưa đủ để kết luận một câu SQL của datasource **Y** được transaction manager của datasource **X** quản lý. Bạn phải xem đúng resource key, đúng manager và đường lấy connection. Trong JDBC địa phương, mỗi datasource chỉ có transaction context riêng; Spring không tự gom tất cả các kết nối từ mọi datasource vào một distributed transaction.

### 3.3. Resource được quản lý theo key nào?

`TransactionSynchronizationManager` sử dụng resource factory làm key, trong JDBC thông thường là bean `DataSource` mà transaction manager quản lý. Vì vậy:

- **Cùng bean datasource** trong transaction manager và các DAO là cấu hình dễ dự đoán nhất.
- **Hai bean datasource khác nhau** dù cùng URL, username và connection pool đích **không tự bảo đảm** chúng sử dụng cùng bound connection.
- **Proxy wrapper** như `TransactionAwareDataSourceProxy`, `LazyConnectionDataSourceProxy` hoặc routing datasource cần được cấu hình đúng thứ tự; các lớp có thể unwrap/delegate theo quy tắc riêng. Không thay đổi wrapper tùy tiện rồi mặc định resource keys vẫn trùng.
- Với nhiều datasource, mỗi datasource có thể được bind một connection riêng trong cùng thread; **có nhiều resource bindings** không có nghĩa chúng đang nằm trong **một giao dịch DB atomic chung**.

## 4. `JdbcTemplate`: đường tích hợp mặc định đúng nhất

Trong JDBC, cách phổ biến và được Spring khuyên dùng là inject `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` vào các DAO:

```java
@Repository
public class AccountDao {
    private final JdbcTemplate jdbc;

    public AccountDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void debit(long accountId, long amount) {
        jdbc.update(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            amount, accountId
        );
    }
}

@Repository
public class AuditDao {
    private final JdbcTemplate jdbc;

    public AuditDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String action) {
        jdbc.update(
            "INSERT INTO audit_events(action) VALUES (?)",
            action
        );
    }
}
```

Đây là **hai class ví dụ trong Spring application**, chưa là chương trình độc lập; cần imports, datasource/schema và transaction manager. Cả hai DAO có thể được gọi từ một service:

```java
@Service
public class TransferService {
    private final AccountDao accounts;
    private final AuditDao audits;

    public TransferService(AccountDao accounts, AuditDao audits) {
        this.accounts = accounts;
        this.audits = audits;
    }

    @Transactional
    public void debitAndAudit(long accountId, long amount) {
        accounts.debit(accountId, amount);
        audits.insert("DEBIT");
        // Nếu RuntimeException thoát method, transaction thường rollback
        // cả UPDATE và INSERT theo quy tắc mặc định.
    }
}
```

**Tại sao hai DAO không tự commit riêng?** `JdbcTemplate` lấy connection theo `DataSourceUtils`, vì vậy nếu transaction manager đã bind resource cho datasource, các lời gọi SQL tham gia đúng transaction hiện hành. Việc bean DAO được tạo bởi `@Repository` hay `@Bean` **không** biến nó thành transaction độc lập; boundary do `@Transactional`/`TransactionTemplate` và propagation quyết định.

### 4.1. Có cần chính xác một `JdbcTemplate` instance cho toàn ứng dụng?

Không. Hai DAO có thể có **hai object `JdbcTemplate` khác nhau** được khởi tạo với **cùng bean `DataSource`**:

```java
JdbcTemplate accountJdbc = new JdbcTemplate(dataSource);
JdbcTemplate auditJdbc   = new JdbcTemplate(dataSource);
```

Hai template khác instance, nhưng cả hai đều thực hiện connection lookup qua Spring-aware mechanism. **Sự dùng chung không nằm ở object template** mà nằm ở datasource và transaction context.

Ngược lại, một bean `JdbcTemplate` duy nhất vẫn có thể xử lý những transaction khác nhau trên các thread khác nhau. Không lưu một `Connection` làm field singleton chỉ để “ép mọi DAO dùng chung”.

### 4.2. Khi DAO gọi DAO khác

Nếu service gọi `AccountDao`, DAO lại gọi `AuditDao`, cả hai vẫn có thể dùng cùng bound resource khi call stack chạy đồng bộ trong cùng transaction/thread. Nhưng về thiết kế, thường tốt hơn khi **service orchestration** định nghĩa transaction boundary; DAO tập trung SQL/persistence.

Không đặt `@Transactional(REQUIRES_NEW)` tùy tiện trên DAO audit chỉ vì muốn “đảm bảo ghi audit”. Propagation đó tạo **physical transaction khác**, khiến logic atomicity thay đổi, và có thể gây rủi ro pool/lock.

## 5. Khi phải viết JDBC thấp tầng: `DataSourceUtils`

Nếu một lớp legacy cần thao tác trực tiếp với `java.sql.Connection` / `PreparedStatement`, hãy dùng:

```java
Connection con = DataSourceUtils.getConnection(dataSource);
try {
    try (PreparedStatement ps = con.prepareStatement(
            "INSERT INTO audit_events(action) VALUES (?)")) {
        ps.setString(1, "CHECKOUT");
        ps.executeUpdate();
    }
} catch (SQLException ex) {
    throw new IllegalStateException("JDBC operation failed", ex);
} finally {
    DataSourceUtils.releaseConnection(con, dataSource);
}
```

Đây là **snippet bên trong class có datasource**, cần imports, và là ví dụ cho một DAO dùng transaction manager JDBC. Những điều thiết yếu:

1. `DataSourceUtils.getConnection(dataSource)` ưu tiên connection đã được Spring bind vào thread, nếu có; khi không có resource phù hợp, nó có thể lấy connection mới từ datasource.
2. `DataSourceUtils.releaseConnection(con, dataSource)` là thao tác giải phóng **theo nhận thức transaction**. Nếu connection còn bound với transaction Spring, helper **không tự đóng physical transaction connection đang dùng**; cleanup sẽ do transaction manager xử lý.
3. **Đóng đúng `Statement`/`ResultSet` mà DAO tạo**, nhưng không tự gọi `con.commit()`, `con.rollback()`, `con.setAutoCommit(true)` hay `con.close()` trực tiếp trên connection Spring quản lý.
4. Kết hợp timeout/statement settings có thể cần thêm `DataSourceUtils.applyTransactionTimeout(...)`; `JdbcTemplate` lo nhiều việc này thay bạn.
5. Khi không có Spring transaction, helper vẫn có thể cung cấp connection bình thường và `releaseConnection` sẽ đóng/release phù hợp. **Không** coi việc gọi `getConnection()` là lệnh “mở transaction” tự động.

### 5.1. Vì sao `dataSource.getConnection()` trực tiếp nguy hiểm?

Một JDBC DAO viết thuần:

```java
try (Connection con = dataSource.getConnection()) {
    try (PreparedStatement ps =
            con.prepareStatement("INSERT INTO events(label) VALUES (?)")) {
        ps.setString(1, "external");
        ps.executeUpdate();
    }
}
```

Với `DriverManagerDataSource` hoặc connection pool thông thường, lệnh này có thể lấy một **connection vật lý khác** và để `autoCommit=true`. Mặc dù caller đang ở trong `@Transactional` của Spring, thao tác trên connection mới **có thể commit độc lập**, không rollback khi outer thất bại. Điều này thường tạo lỗi dữ liệu khó phát hiện.

Tuy nhiên, không tuyên bố tất cả `DataSource.getConnection()` đều thoát transaction: một **`TransactionAwareDataSourceProxy`** được thiết kế để giúp legacy code dùng API datasource chuẩn vẫn có thể tham gia Spring-managed transaction; datasource được ứng dụng server quản lý/JTA có thể có hành vi riêng. Cần phân biệt **datasource nào đã được truyền cho code** và **transaction coordinator nào đang hoạt động**.

### 5.2. `TransactionAwareDataSourceProxy` cho thư viện legacy

Khi một thư viện **bắt buộc** gọi `DataSource.getConnection()`, có thể truyền cho nó một `TransactionAwareDataSourceProxy`:

```java
DataSource targetDataSource = /* datasource thực */;
DataSource legacyView =
    new TransactionAwareDataSourceProxy(targetDataSource);

// Thư viện chỉ biết javax.sql.DataSource:
legacyLibrary.setDataSource(legacyView);
```

Đây là **snippet minh họa**; `legacyLibrary` do ứng dụng cung cấp. Proxy tạo ra connection handle transaction-aware để các lời gọi `getConnection()`/`close()` phù hợp với Spring resource management. **Không** bọc mọi DAO mới bằng proxy này chỉ theo thói quen: Spring ưu tiên `JdbcTemplate`/`DataSourceUtils`.

Khi cấu hình manager, truyền **target datasource** (hoặc loại proxy được transaction manager xử lý đúng) thay vì nhầm lẫn các wrapper. Thử tích hợp thật trước khi ghép nhiều `DataSourceProxy` hoặc routing/lazy proxies.

## 6. Ví dụ Java 17 chạy được: nhiều DAO dùng cùng connection, commit/rollback cùng nhau

Bài thực nghiệm dùng **Spring Framework 6.2**, **JDBC**, **H2 in-memory** và **`JdbcTransactionManager`**. Nó có:

- `LedgerDao` dùng một `JdbcTemplate`.
- `AuditDao` dùng **một `JdbcTemplate` khác**, cùng datasource.
- `AuditService` là bean khác, khai báo `@Transactional(propagation = REQUIRED)` và được gọi qua Spring proxy.
- `RawDao` dùng `DataSourceUtils.getConnection` + `PreparedStatement`.
- `OuterService` mở transaction và orchestrate ba DAO.
- `UnsafeDao` cố ý dùng `dataSource.getConnection()` trực tiếp trong một tình huống phản ví dụ.

Các phép quan sát:

1. **SUCCESS**: nhiều DAO hoạt động trên cùng transaction; inner `REQUIRED` tham gia transaction ngoài, các bản ghi cùng commit.
2. **ROLLBACK**: outer ném unchecked exception; cả bản ghi do `LedgerDao`, `AuditDao` và `RawDao` đều bị rollback.
3. **UNSAFE**: một DAO mở connection **không transaction-aware** đến datasource và ghi sang bảng khác (để tránh tranh chấp lock trong demo), auto-commit bản ghi đó; outer rollback nhưng bản ghi của UnsafeDao vẫn còn.

**Cách chứng minh:** dùng `DataSourceUtils.getConnection` trong DAO để so sánh **identity của connection đang bound** với connection ngoài. Đây chỉ là phép đo hạ tầng hợp lý với `JdbcTransactionManager` + `DriverManagerDataSource` trong demo; không viết logic nghiệp vụ production dựa vào so sánh `Connection == Connection` qua các proxy/driver khác nhau. Kiểm chứng quan trọng hơn vẫn là **read-your-writes và atomic commit/rollback**.

### 6.1. Cấu trúc thư mục

```text
spring-shared-resource-demo/
├── pom.xml
└── src/main/java/com/example/resource/Main.java
```

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-shared-resource-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` hỗ trợ context/beans/AOP, `spring-jdbc` cung cấp `JdbcTemplate` và transaction manager, H2 là JDBC database trong bộ nhớ. Không cần Spring Boot. Java 17 là runtime tối thiểu của Spring 6.x. `DriverManagerDataSource` thích hợp cho bài demo, không phải connection pool production.

### 6.3. `src/main/java/com/example/resource/Main.java`

```java
package com.example.resource;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class Main {

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:shared_resource;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public LedgerDao ledgerDao(DataSource ds) {
            return new LedgerDao(ds);
        }

        @Bean
        public AuditDao auditDao(DataSource ds) {
            return new AuditDao(ds);
        }

        @Bean
        public RawDao rawDao(DataSource ds) {
            return new RawDao(ds);
        }

        @Bean
        public UnsafeDao unsafeDao(DataSource ds) {
            return new UnsafeDao(ds);
        }

        @Bean
        public AuditService auditService(AuditDao auditDao) {
            return new AuditService(auditDao);
        }

        @Bean
        public OuterService outerService(
                DataSource ds, LedgerDao ledger, AuditDao audit,
                RawDao raw, AuditService auditService, UnsafeDao unsafe) {
            return new OuterService(ds, ledger, audit, raw,
                    auditService, unsafe);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }
    }

    // Dùng chung utility CHỈ cho mục tiêu quan sát trong demo.
    private static boolean sameBoundConnection(
            DataSource ds, Connection expected) {
        Connection current = DataSourceUtils.getConnection(ds);
        try {
            return current == expected;
        } finally {
            DataSourceUtils.releaseConnection(current, ds);
        }
    }

    public static class LedgerDao {
        private final DataSource ds;
        private final JdbcTemplate jdbc;

        public LedgerDao(DataSource ds) {
            this.ds = ds;
            this.jdbc = new JdbcTemplate(ds);
        }

        public void insert(String label) {
            jdbc.update(
                "INSERT INTO ledger_entries(label) VALUES (?)", label
            );
        }

        public boolean same(Connection expected) {
            return sameBoundConnection(ds, expected);
        }
    }

    public static class AuditDao {
        private final DataSource ds;
        private final JdbcTemplate jdbc;

        public AuditDao(DataSource ds) {
            this.ds = ds;
            this.jdbc = new JdbcTemplate(ds);
        }

        // Query qua một JdbcTemplate instance KHÁC với LedgerDao.
        public boolean seesLedger(String label) {
            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ledger_entries WHERE label = ?",
                Integer.class,
                label
            );
            return count != null && count > 0;
        }

        public void insert(String label) {
            jdbc.update(
                "INSERT INTO audit_entries(label) VALUES (?)", label
            );
        }

        public boolean same(Connection expected) {
            return sameBoundConnection(ds, expected);
        }
    }

    public static class RawDao {
        private final DataSource ds;

        public RawDao(DataSource ds) {
            this.ds = ds;
        }

        public boolean insertAndSame(String label, Connection expected) {
            Connection con = DataSourceUtils.getConnection(ds);
            try (PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO raw_entries(label) VALUES (?)")) {
                ps.setString(1, label);
                ps.executeUpdate();
                return con == expected;
            } catch (SQLException ex) {
                throw new IllegalStateException("raw JDBC failed", ex);
            } finally {
                DataSourceUtils.releaseConnection(con, ds);
            }
        }
    }

    // PHẢN VÍ DỤ: gọi datasource.getConnection() trực tiếp,
    // không đi qua DataSourceUtils; H2 connection này auto-commit.
    public static class UnsafeDao {
        private final DataSource ds;

        public UnsafeDao(DataSource ds) {
            this.ds = ds;
        }

        public boolean insertOutside(String label) {
            try (Connection con = ds.getConnection();
                 PreparedStatement ps = con.prepareStatement(
                     "INSERT INTO outside_entries(label) VALUES (?)")) {
                ps.setString(1, label);
                ps.executeUpdate();
                return con.getAutoCommit();
            } catch (SQLException ex) {
                throw new IllegalStateException("unsafe SQL failed", ex);
            }
        }
    }

    public static class AuditService {
        private final AuditDao audit;

        public AuditService(AuditDao audit) {
            this.audit = audit;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void record(String label, Connection expected) {
            boolean newTx = TransactionAspectSupport
                    .currentTransactionStatus()
                    .isNewTransaction();
            System.out.println("audit newTransaction=" + newTx);

            audit.insert(label);
            System.out.println(
                "audit sameConnection=" + audit.same(expected)
            );
        }
    }

    public static class OuterService {
        private final DataSource ds;
        private final LedgerDao ledger;
        private final AuditDao audit;
        private final RawDao raw;
        private final AuditService auditService;
        private final UnsafeDao unsafe;

        public OuterService(
                DataSource ds, LedgerDao ledger, AuditDao audit,
                RawDao raw, AuditService auditService, UnsafeDao unsafe) {
            this.ds = ds;
            this.ledger = ledger;
            this.audit = audit;
            this.raw = raw;
            this.auditService = auditService;
            this.unsafe = unsafe;
        }

        private void writeAll(String label) {
            Connection expected = DataSourceUtils.getConnection(ds);
            try {
                System.out.println(
                    "outer active=" +
                    TransactionSynchronizationManager
                        .isActualTransactionActive() +
                    " bound=" +
                    TransactionSynchronizationManager.hasResource(ds)
                );

                ledger.insert(label);
                System.out.println(
                    "ledger sameConnection=" + ledger.same(expected)
                );

                System.out.println(
                    "audit seesLedgerWrite=" + audit.seesLedger(label)
                );
                auditService.record(label, expected);
                System.out.println(
                    "raw sameConnection=" +
                    raw.insertAndSame(label, expected)
                );
            } finally {
                DataSourceUtils.releaseConnection(expected, ds);
            }
        }

        @Transactional
        public void successful() {
            writeAll("success");
        }

        @Transactional
        public void failed() {
            writeAll("rollback");
            throw new IllegalStateException("force rollback");
        }

        @Transactional
        public void unsafeMix() {
            ledger.insert("not-committed");
            boolean autoCommit = unsafe.insertOutside("outside-committed");
            System.out.println("outside autoCommit=" + autoCommit);
            throw new IllegalStateException("unsafe outer rollback");
        }
    }

    private static int count(JdbcTemplate jdbc, String tableName) {
        // tableName chỉ nhận HẰNG được hard-code trong Main, không
        // lấy từ input của người dùng.
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + tableName,
            Integer.class
        );
        return value;
    }

    private static String counts(JdbcTemplate jdbc) {
        return "ledger=" + count(jdbc, "ledger_entries") +
            ",audit=" + count(jdbc, "audit_entries") +
            ",raw=" + count(jdbc, "raw_entries") +
            ",outside=" + count(jdbc, "outside_entries");
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE ledger_entries (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," +
                "label VARCHAR(80) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE audit_entries (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," +
                "label VARCHAR(80) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE raw_entries (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," +
                "label VARCHAR(80) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE outside_entries (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," +
                "label VARCHAR(80) NOT NULL)"
            );

            OuterService outer = context.getBean(OuterService.class);

            System.out.println("=== SUCCESS ===");
            outer.successful();
            System.out.println("after success " + counts(jdbc));

            System.out.println("=== ROLLBACK ===");
            try {
                outer.failed();
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }
            System.out.println("after rollback " + counts(jdbc));

            System.out.println("=== UNSAFE GET_CONNECTION ===");
            try {
                outer.unsafeMix();
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }
            System.out.println("after unsafe " + counts(jdbc));
        }
    }
}
```

### 6.4. Lệnh chạy

Cài JDK 17+ và Maven. Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.resource.Main
```

Kết quả **dự kiến do chính chương trình in ra** trên H2 với configuration trong ví dụ (không tính thông điệp Maven/SLF4J nếu có):

```text
=== SUCCESS ===
outer active=true bound=true
ledger sameConnection=true
audit seesLedgerWrite=true
audit newTransaction=false
audit sameConnection=true
raw sameConnection=true
after success ledger=1,audit=1,raw=1,outside=0
=== ROLLBACK ===
outer active=true bound=true
ledger sameConnection=true
audit seesLedgerWrite=true
audit newTransaction=false
audit sameConnection=true
raw sameConnection=true
caught=force rollback
after rollback ledger=1,audit=1,raw=1,outside=0
=== UNSAFE GET_CONNECTION ===
outside autoCommit=true
caught=unsafe outer rollback
after unsafe ledger=1,audit=1,raw=1,outside=1
```

**Giải thích từng dòng quan trọng:**

- `outer active=true bound=true`: Spring đã mở physical transaction và bind một connection holder cho datasource vào thread.
- `ledger sameConnection=true` và `audit sameConnection=true`: hai DAO khác nhau có thể lấy lại đúng connection đang bound khi cần kiểm tra; mỗi DAO có một object `JdbcTemplate` riêng.
- `audit seesLedgerWrite=true`: `AuditDao` đọc được INSERT vừa thực hiện qua `LedgerDao` **trước khi transaction commit**. Đây là read-your-writes trong cùng transaction, không phải dirty read từ connection khác.
- `audit newTransaction=false`: method của `AuditService` được gọi qua Spring proxy và khai báo `REQUIRED`; nó **tham gia** physical transaction của outer thay vì tạo transaction mới.
- `raw sameConnection=true`: legacy-style JDBC code dùng `DataSourceUtils` vẫn nhận đúng bound connection.
- `after rollback ledger=1,audit=1,raw=1`: kịch bản đầu đã commit một bản ghi cho mỗi bảng; kịch bản hai có ghi ở cả ba DAO nhưng bị rollback toàn bộ, nên số đếm vẫn 1.
- `outside autoCommit=true`: `UnsafeDao` cố ý lấy connection mới trực tiếp từ `DriverManagerDataSource`, không đi qua `DataSourceUtils`, nên H2 tự commit statement vào bảng `outside_entries`.
- `after unsafe ... outside=1`: outer rollback thao tác `ledger.insert("not-committed")`, nhưng không rollback được thao tác ghi trên connection ngoài transaction Spring.

**Chú ý tính kiểm chứng:** cách so sánh `Connection == expected` hoạt động trong demo này vì hai lần lookup của `DataSourceUtils` đối với cùng datasource và active transaction đều trả cùng bound JDBC handle. Một connection proxy của `JdbcTemplate.execute(ConnectionCallback)` có thể có **identity khác** dù trỏ tới cùng underlying connection (`JdbcTemplate` tạo close-suppressing proxy). Không dùng so sánh object identity qua các wrapper hoặc pool làm định nghĩa chung của một transaction. Kiểm chứng chắc hơn là cùng nhìn được các SQL chưa commit và có atomic rollback/commit.

### 6.5. Vì sao transaction của demo không phụ thuộc self-invocation?

`outer.successful()`, `outer.failed()` và `outer.unsafeMix()` được gọi từ `Main` trên **bean lấy từ Spring context**, không phải từ đối tượng tự tạo bằng `new OuterService(...)`. Phương thức `AuditService.record()` cũng được outer gọi trên **bean do Spring quản lý**, nên advice cho `REQUIRED` được áp dụng.

Ngược lại, nếu một method cùng class gọi `this.newTransactionMethod()` thì trong Spring proxy mode, lời gọi có thể bypass proxy và không kích hoạt annotation của method được gọi. Việc đồng thời có bound resource ở outer không sửa được sai lầm về transactional boundary này.

### 6.6. Vì sao phản ví dụ dùng bảng ngoài riêng?

Trong nhiều database, T1 có thể đang giữ lock của bảng/hàng mà một connection khác cũng cần ghi. Nếu `UnsafeDao` dùng connection khác và chờ lock do outer đang giữ, cùng call stack sẽ **tự chặn** và làm ví dụ khó chạy. Bảng riêng `outside_entries` giúp cô lập bài học về **autocommit bên ngoài transaction** thay vì lẫn với lock contention. Trong ứng dụng thật, dùng raw connection sai còn có thể dẫn đến timeout/deadlock, không chỉ đến một bản ghi bị commit lệch.

## 7. Chỗ nào định nghĩa transaction boundary?

Một kiến trúc dễ đọc:

```text
Controller
  |
  v
Application service
  @Transactional
  |
  +-- Domain service / repository A
  +-- Domain service / repository B
  +-- Outbox / audit repository (nếu cần cùng DB atomicity)
  |
  +-- return
        |
        v
  Spring transaction interceptor hoàn tất transaction
```

Transaction boundary thường đặt ở **application service** vì service hiểu cần commit/rollback những thay đổi nào như một đơn vị. DAO/repository không cần đều khai báo `@Transactional`; khi chúng được gọi trong transaction đã mở, Spring-aware JDBC APIs sẽ tự tham gia.

### 7.1. Có nên ghi `@Transactional` trên mọi DAO?

Không bắt buộc. Nếu một DAO method được gọi độc lập ngoài transaction, bạn có thể cần một boundary ở tầng phù hợp, nhưng gắn `@Transactional` lên mọi thao tác tùy tiện làm luồng propagation khó theo dõi.

Với `REQUIRED`:
- Có outer transaction hợp lệ → tham gia outer.
- Không có transaction → tạo mới.
- Nếu participating scope đánh dấu rollback-only do lỗi, toàn outer transaction có thể rollback; caller có thể gặp `UnexpectedRollbackException` khi tưởng commit thành công.

Chính sách rollback của `@Transactional` mặc định dựa trên unchecked exception/`Error`; checked exception cần cân nhắc `rollbackFor` nếu muốn rollback. Đừng chỉ dùng `catch (Exception)` và nuốt lỗi rồi mong Spring biết để rollback.

### 7.2. `TransactionTemplate` thay cho AOP khi cần boundary lập trình

Cùng mô hình nhiều DAO vẫn dùng được với `TransactionTemplate`:

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);

tx.executeWithoutResult(status -> {
    accountDao.debit(accountId, amount);
    auditDao.insert("DEBIT");
    legacyDao.insertWithDataSourceUtils("DEBIT");

    if (businessRuleFailed()) {
        status.setRollbackOnly();
    }
});
```

Đây là **snippet**, các type/field/method nghiệp vụ phải do ứng dụng cung cấp. `TransactionTemplate` quản lý transaction trên thread hiện tại; các DAO dùng Spring-aware datasource lookup vẫn nhận đúng bound resource. Ưu điểm là boundary rõ trong code và không cần proxy để **vào** transaction template; nhược điểm là orchestration phải biết transaction API.

## 8. Propagation thay đổi resource như thế nào?

Không phải cứ gọi DAO trong cùng call stack thì **luôn** dùng physical transaction cũ. Propagation tại transactional method boundary có thể thay đổi điều đó.

| Propagation của inner | Khi outer đang có transaction A | Tài nguyên/commit |
|---|---|---|
| `REQUIRED` | Tham gia A | Thường cùng resource connection A; inner không commit A độc lập |
| `SUPPORTS` | Tham gia A nếu có | Khi có A, SQL Spring-aware thường dùng resource A; khi không có A có thể không có actual transaction |
| `MANDATORY` | Phải có A | Nếu có A thì tham gia; không có transaction sẽ lỗi |
| `REQUIRES_NEW` | Tạm ngưng A, mở B | B có resource/physical transaction độc lập; B hoàn tất rồi restore A |
| `NESTED` | Với JDBC manager hỗ trợ, dùng savepoint trong A | Vẫn một physical transaction/connection A; nested scope rollback về savepoint |
| `NOT_SUPPORTED` | Suspend A, chạy không trong transaction A | JDBC calls bên trong có thể dùng connection khác/nontransactional; sau đó resume A |
| `NEVER` | Không cho phép A hiện hữu | Nếu có A thì Spring ném lỗi |

### 8.1. `REQUIRES_NEW` không “dùng cùng resource A”

```text
Outer transaction A
     |
     +-- DAO 1 dùng Connection A
     |
     +-- inner @Transactional(REQUIRES_NEW)
     |        suspend resource A
     |        lấy Connection B, bắt đầu transaction B
     |        DAO 2 dùng B
     |        commit hoặc rollback B
     |        resume resource A
     |
     +-- DAO 3 dùng Connection A trở lại
     |
     +-- commit/rollback A
```

B có thể commit ngay cả nếu A sau đó rollback. B thường cần connection thứ hai, còn A có thể vẫn giữ connection/locks. Spring cảnh báo cấu hình pool đủ lớn khi nhiều thread dùng `REQUIRES_NEW`; không đưa nó vào mọi DAO chỉ để “an toàn”.

### 8.2. `NESTED` vẫn một physical transaction khi dùng savepoint

Nếu JDBC manager/driver hỗ trợ, `@Transactional(propagation = NESTED)` thường tạo savepoint trên connection A. Inner rollback về savepoint không đồng nghĩa A kết thúc; outer vẫn tiếp tục. Nếu sau đó A rollback toàn bộ thì **mọi** thay đổi chưa commit, kể cả phần nested “thành công”, vẫn mất.

Không suy rộng vào mọi JPA/JTA transaction manager; khả năng hỗ trợ savepoint/nested phụ thuộc manager và resource.

### 8.3. `NOT_SUPPORTED` và đường truy cập không transaction-aware

Trong đoạn `NOT_SUPPORTED`, Spring suspend context A; JDBC code có thể lấy một connection khác. Khi rời đoạn, A được resume. Đây là **thay đổi semantics có chủ đích**, khác với bug của `dataSource.getConnection()` trực tiếp khi bạn tưởng mình vẫn thuộc A.

## 9. Dùng cùng resource giữa JDBC và JPA/Hibernate

**Không đồng nhất “cùng DB” với “cùng transaction vật lý” nếu trộn persistence technologies.** Khi cần `JpaRepository` + `JdbcTemplate` trong một service transaction, cần xét:

- `JpaTransactionManager` quản lý `EntityManager` của một `EntityManagerFactory` và **có thể hỗ trợ JDBC access cùng một datasource** trong cùng transaction khi JPA provider/dialect cho phép truy cập JDBC connection phù hợp.
- `JdbcTemplate` phải dùng datasource gắn với persistence unit/transaction manager thích hợp. Việc tạo **một `JdbcTransactionManager` riêng** cho JDBC và một `JpaTransactionManager` riêng cho JPA trên cùng database **không mặc nhiên tạo một transaction duy nhất**.
- JPA `EntityManager` có **persistence context/first-level cache** và có thể trì hoãn SQL đến `flush()`. Vì vậy, dù JDBC thật sự thuộc cùng physical transaction, query JDBC có thể **chưa thấy** thay đổi của entity nếu JPA chưa flush các SQL cần thiết.
- JDBC `UPDATE` trực tiếp có thể làm DB thay đổi nhưng các entity đang managed trong persistence context vẫn chứa **state cũ**. Cần quy tắc rõ về `flush`, `clear`/`refresh`, optimistic locking và trình tự truy cập.
- Không thực hiện `Connection.commit()` trong JDBC layer chỉ vì JPA chưa flush; Spring/transaction manager quản lý lifecycle.

Ví dụ minh họa (không phải class chạy độc lập):

```java
@Service
class InventoryService {
    private final ItemRepository items; // Spring Data JPA
    private final JdbcTemplate jdbc;     // cùng DB/resource đúng cấu hình

    InventoryService(ItemRepository items, JdbcTemplate jdbc) {
        this.items = items;
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(long id) {
        Item entity = items.findById(id).orElseThrow();
        entity.decreaseAvailable(1);

        // Tùy JPA provider, thay đổi entity có thể chưa flush ra SQL.
        items.flush();

        // JdbcTemplate đọc DB sau khi SQL JPA đã flush.
        Integer left = jdbc.queryForObject(
            "SELECT available FROM items WHERE id = ?",
            Integer.class, id
        );
        // Tiếp tục nghiệp vụ dựa trên giá trị đọc.
    }
}
```

Đây là **snippet ứng dụng cần repository/entity/configuration phù hợp**. Sự tồn tại của `items.flush()` không thay đổi nguyên tắc commit: flush gửi SQL, nhưng **không commit transaction vật lý**. Outer rollback vẫn có thể hoàn tác các thay đổi đã flush. Hãy test trên DB thật, xem đúng transaction manager được chọn nếu có nhiều manager beans.

## 10. Dùng cùng resource giữa MyBatis và Spring JDBC

MyBatis-Spring cung cấp `SqlSessionTemplate` để các mapper tham gia Spring transaction. Theo tài liệu MyBatis-Spring:

- `SqlSessionTemplate` sử dụng `SqlSession` gắn với transaction hiện hành và quản lý lifecycle thay application.
- Datasource của `SqlSessionFactoryBean` phải phù hợp với datasource của `DataSourceTransactionManager`/Spring transaction manager; **cùng URL không đủ** để mặc nhiên tham gia.
- `SpringManagedTransactionFactory` là lựa chọn thông thường với MyBatis-Spring.
- Không tự gọi `commit()`, `rollback()` hoặc `close()` trên `SqlSession` do Spring quản lý; MyBatis-Spring điều phối việc này.
- Dùng `SqlSessionFactory.openSession()` hoặc `DefaultSqlSession` bằng tay có thể bỏ qua Spring-managed session và dẫn tới lỗi consistency.

Sơ đồ cấu hình khái quát:

```text
Same DataSource bean
      |
      +-- JdbcTransactionManager/DataSourceTransactionManager
      |
      +-- JdbcTemplate (DAO A)
      |
      +-- SqlSessionFactoryBean -> SqlSessionTemplate (Mapper B)
                                      |
                                      v
                        SQL tham gia transaction Spring hiện hành
```

Đây là **mô hình tích hợp**, không phải chứng nhận rằng bất kỳ MyBatis configuration nào cũng đúng. Khi dùng mapper với executor types khác nhau, MyBatis-Spring còn có hạn chế không thay đổi `ExecutorType` bên trong cùng existing transaction một cách tùy tiện.

## 11. Nhiều datasource: cùng thread nhưng không cùng atomic transaction

Đây là một hiểu lầm lớn trong ứng dụng Spring:

```java
@Transactional("ordersTransactionManager")
public void placeOrder() {
    ordersJdbc.update("INSERT INTO orders ...");  // datasource orders
    billingJdbc.update("INSERT INTO charges ..."); // datasource billing
}
```

Đây là **snippet minh họa**, không chạy độc lập. `ordersTransactionManager` có thể chỉ quản lý datasource orders. Nếu `billingJdbc` dùng datasource billing khác, thao tác billing **không tự được đưa vào cùng physical transaction**. Nó có thể tự commit độc lập, hoặc cần một transaction manager riêng.

Sự kiện code nằm trong cùng Java method hoặc cùng thread không biến hai connection đến hai DB thành **một ACID unit**.

### 11.1. Các lựa chọn kiến trúc

1. **Một DB/connection cho các bảng cần atomicity:** đơn giản nhất khi domain boundaries cho phép.
2. **Distributed transaction/JTA/XA:** khi nhiều resource XA tham gia dưới một transaction coordinator phù hợp, chúng có thể được điều phối theo transaction phân tán, với hạn chế vận hành và hỗ trợ của từng driver/resource. Không đồng nhất “cùng resource” với “cùng JDBC connection”; mỗi resource vẫn có connection và transaction branch riêng.
3. **Outbox, saga, compensation:** khi không thể hoặc không muốn dùng XA, thiết kế eventual consistency, idempotency và xử lý thất bại từng bước.

Đừng “giải quyết” bằng cách đặt `@Transactional` lên cả hai datasource manager rồi tin Spring tự áp dụng two-phase commit. **Một annotation không tự biến hai local transaction managers thành global transaction manager**.

### 11.2. Chọn transaction manager đúng

Nếu ứng dụng có nhiều beans `PlatformTransactionManager`, có thể chọn theo qualifier:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void saveOrder() {
    // Chỉ những tài nguyên do manager phù hợp quản lý
    // mới chắc chắn tham gia transaction này.
}
```

Đây là snippet. Trong Spring, bạn cũng có thể cấu hình transaction manager mặc định qua cấu hình application. Phải thống nhất cách chọn manager cho service và repository; nếu method A dùng manager X còn method B dùng manager Y, việc tham gia/rollback có thể không giống một transaction.

## 12. Thread boundary và reactive transaction

### 12.1. `@Async` hoặc thread mới không tự mang JDBC resource binding theo

Imperative Spring transaction synchronization dựa vào **thread-bound context**. Một đoạn code:

```java
@Transactional
public void process() {
    accountDao.update();
    asyncAuditService.recordAsync(); // @Async -> thread khác
}
```

là **snippet minh họa**. `@Async` thường chạy ở thread khác; thread này **không tự kế thừa** connection đang được Spring bind cho thread gọi. Nó có thể mở transaction mới của mình hoặc chạy không transaction, tùy annotation/manager. Nếu cần atomicity với account update, **không** chuyển phần audit bắt buộc vào async method rồi mong rollback cùng transaction gốc.

Không copy `TransactionSynchronizationManager` resource map sang thread khác để “chia connection”: JDBC connections và persistence contexts nói chung **không an toàn để sử dụng đồng thời giữa threads**, và transaction manager không được thiết kế để quản lý lifecycle bằng cách copy thủ công.

### 12.2. Reactive transaction khác imperative transaction

R2DBC và reactive Spring transaction management gắn context vào **Reactor Context**, không phải mô hình `ThreadLocal ConnectionHolder` của JDBC imperative. Sử dụng `R2dbcTransactionManager`/`TransactionalOperator` và operator/reactive data APIs tương ứng.

Trộn `JdbcTemplate` blocking với R2DBC pipeline không bảo đảm cùng transaction; một datasource JDBC và một R2DBC `ConnectionFactory` là **hai resource models** khác nhau. Không suy diễn từ việc subscription cùng request ID để khẳng định atomic commit.

## 13. Read-only, isolation và timeout cũng được chia sẻ theo physical transaction

Khi nhiều DAO tham gia **cùng physical transaction**:

- **Isolation:** các SQL chạy trên physical transaction hiện tại sẽ chịu isolation do manager/connection cấu hình; một inner method `REQUIRED` khai báo isolation khác **thông thường không nâng isolation** của outer đang chạy.
- **Read-only:** nếu outer có `@Transactional(readOnly=true)`, inner DAO không mặc nhiên biến nó thành read-write; chính sách chặn ghi tùy DB/driver/manager. `readOnly` chủ yếu là hint ở Spring API, không phải một firewall SQL mặc định.
- **Timeout:** các statements có thể chịu transaction timeout còn lại; `JdbcTemplate` có cơ chế áp dụng timeout khi chuẩn bị statement. JDBC code thủ công phải biết tích hợp `DataSourceUtils.applyTransactionTimeout` nếu cần.
- **Rollback-only:** nếu một participating scope đánh dấu transaction rollback-only, mọi DAO đang trong physical transaction có thể bị rollback cùng nhau; không có “rollback riêng DAO B” chỉ vì DAO B có annotation riêng.

Khi `REQUIRES_NEW` mở physical transaction khác, inner có isolation/read-only/timeout riêng và resource mới. Điều này thay đổi cả concurrency behavior, transaction locks và khả năng commit độc lập.

## 14. Lỗi phổ biến, triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân phổ biến | Hướng kiểm tra |
|---|---|---|
| DAO A rollback nhưng DAO B đã commit | DAO B dùng `dataSource.getConnection()` thô với auto-commit hoặc manager khác | Kiểm tra datasource object, connection lookup, transaction boundary, SQL sau rollback |
| Hai DAO dùng cùng DB URL nhưng không chung transaction | Hai datasource bean/manager khác nhau, resource bindings khác | Kiểm tra bean wiring và transaction manager đang active |
| DAO legacy đóng connection giữa transaction | Gọi `con.close()` trực tiếp thay vì `DataSourceUtils.releaseConnection` | Dùng helper hoặc `TransactionAwareDataSourceProxy` cho legacy code |
| `JdbcTemplate` và raw JDBC có `Connection == false` | Một bên dùng proxy/wrapper; có thể vẫn cùng underlying resource | So sánh đúng target/holder trong test, quan trọng hơn là commit/rollback thực |
| ORM ghi dữ liệu nhưng JDBC SELECT chưa thấy | Hibernate/JPA chưa flush thay đổi xuống SQL | Dùng flush có chủ đích, kiểm tra SQL, cùng manager/provider |
| JDBC cập nhật DB nhưng JPA entity vẫn trả giá trị cũ | Persistence context cache giữ entity đã tải | Hiểu flush/clear/refresh, tránh stale managed state |
| Mapper MyBatis không tham gia Spring transaction | `SqlSessionFactory` dùng datasource khác, raw `openSession()` | Dùng `SqlSessionTemplate`, cấu hình SpringManagedTransactionFactory và DS đúng |
| Inner `@Transactional(REQUIRED)` được kỳ vọng có transaction mới | `REQUIRED` tham gia outer theo thiết kế | Kiểm tra `status.isNewTransaction()` trong test, hiểu propagation |
| Inner `REQUIRES_NEW` tự commit dù outer rollback | Đúng semantics independent physical transaction | Chỉ dùng khi yêu cầu business ghi độc lập |
| Pool cạn khi nhiều request gọi `REQUIRES_NEW` | Outer giữ một connection, inner đòi connection thứ hai | Đo pool usage, giới hạn concurrency, sizing phù hợp |
| Chạy `@Async` không rollback cùng caller | Resource bind theo thread, async chạy thread khác | Đưa vào cùng synchronous boundary hoặc dùng outbox |
| `TransactionSynchronizationManager.isActualTransactionActive() == true` nhưng DB B vẫn commit riêng | Flag của thread không chứng minh datasource B tham gia manager A | Kiểm tra resource key, transaction manager và SQL outcome |
| Chỉ nhìn log “Creating new transaction” mà cho rằng atomicity đã đúng | Chưa chắc tất cả DAO dùng connection đúng | Tạo integration test chèn nhiều bảng rồi cố ý rollback |
| Dùng `@Transactional` trên method private/self-invoked | Proxy advice không đi qua | Đặt public service method được gọi qua proxy hoặc dùng template |
| Cố dùng `@Transactional` trên hai datasource để có XA | Hai local managers vẫn độc lập | Cân nhắc JTA/XA hoặc saga/outbox |
| Gọi `commit()` trong DAO raw | Phá lifecycle do Spring quản lý; outer rollback không còn ý nghĩa dự kiến | Không tự commit/rollback connection đã bind |

### 14.1. Cách debug connection binding đúng mức

Trong integration test **chỉ để chẩn đoán**, bạn có thể kiểm tra:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean bound =
    TransactionSynchronizationManager.hasResource(dataSource);

Object resource =
    TransactionSynchronizationManager.getResource(dataSource);
```

Các dòng trên là snippet, cần import `TransactionSynchronizationManager` và biến datasource. Với JDBC manager, resource thường là `ConnectionHolder`. Không mang `resource`/`Connection` này sang thread khác hoặc lưu trong singleton. Đừng in raw JDBC credential, SQL parameters hay user-sensitive data vào logs.

Bật DEBUG của `org.springframework.transaction` và `org.springframework.jdbc.datasource` có thể giúp thấy create/join/suspend/resume/cleanup. Nhưng log chỉ là bằng chứng phụ; kiểm tra quyết định vẫn là **các bảng có cùng commit/rollback thật**.

### 14.2. Một integration test nên xác nhận những gì?

Thay vì chỉ unit test rằng DAO A và DAO B đã được gọi, hãy chạy một test với **database thực / Testcontainers**:

1. Cấu hình service thực, đúng Spring transaction proxy và transaction manager.
2. Gọi service tạo nhiều thay đổi qua **nhiều lớp truy cập dữ liệu khác nhau**.
3. Trong transaction, cho DAO B đọc thay đổi chưa commit của DAO A để kiểm tra read-your-writes.
4. Cố ý ném unchecked exception sau khi **mọi DAO** đã chạy.
5. Catch ở **ngoài boundary**; sau rollback, mở connection/transaction khác đọc lại các bảng. Tất cả các thay đổi trong unit of work phải mất.
6. Chạy case success và xác nhận tất cả cùng có dữ liệu.
7. Thử thêm đường raw JDBC, JDBC wrapper/proxy, MyBatis/JPA nếu hệ thống dùng.
8. Kiểm tra đường gọi async và multi-datasource riêng; không mặc định chúng thuộc cùng transaction.
9. Nếu có nested/requires-new, tách case kiểm thử từng propagation.
10. Thử lỗi commit/connection loss và chiến lược retry/idempotency nếu nghiệp vụ quan trọng.

**Phản chứng mạnh nhất:** Nếu một DAO tiếp tục để lại bản ghi sau khi outer Spring transaction đã rollback, trước hết hãy kiểm tra kết nối/datasource/manager/propagation của DAO đó — đừng vội kết luận Spring transaction tự động bị lỗi.

## 15. Những nguyên tắc thiết kế nên áp dụng

### 15.1. Đặt boundary quanh nghiệp vụ, không quanh từng truy vấn

Nếu một giao dịch nghiệp vụ đòi hỏi cả ghi ledger lẫn ghi audit cùng commit, đặt `@Transactional` tại service orchestrator và để các repository tham gia. Tránh chia thành hai transaction vật lý nếu không có yêu cầu độc lập.

### 15.2. Inject đúng cùng datasource/manager cho các DAO cùng DB

Một bean `DataSource` rõ ràng, một transaction manager thích hợp, các DAO dùng `JdbcTemplate`/`DataSourceUtils`. Nếu có nhiều datasource/manager, dùng qualifier rõ ràng thay vì dựa vào tên bean ngẫu nhiên. Đánh dấu dependency graph để review dễ hơn.

### 15.3. Không tự điều khiển connection đang do Spring quản lý

Trong DAO không gọi `setAutoCommit`, `commit`, `rollback` hoặc `close` tùy tiện. Nếu dùng raw JDBC, đóng statement/result set của mình, và release connection qua `DataSourceUtils`.

### 15.4. Phân biệt read-your-writes với isolation giữa transactions

DAO B nhìn thấy SQL chưa commit của DAO A **trong cùng transaction** là hành vi bình thường. Điều đó không có nghĩa một connection thứ hai ở transaction khác cũng được phép đọc dirty data. Isolation level và DB engine quyết định visibility **giữa** transactions.

### 15.5. Kiểm soát tài nguyên bên ngoài database

Việc sử dụng chung JDBC transaction không làm HTTP call, file write, Redis update hoặc broker message trở nên atomic với DB. Khi cần chắc chắn “ghi event chỉ sau commit”, cân nhắc outbox hoặc after-commit synchronization phù hợp. Nếu cần nhất quán xuyên resources, thiết kế JTA/XA hoặc eventual consistency có chủ đích.

### 15.6. Bảo đảm transaction không dài vô ích

Dùng một connection cho nhiều DAO trong cùng transaction giúp atomicity, nhưng cũng có thể kéo dài thời gian giữ connection/locks. Không đưa external HTTP call chậm, sleep hoặc việc tính toán không liên quan vào transaction nếu có thể tách an toàn. Kiểm soát timeout, connection pool và số transaction đồng thời.

## 16. Câu hỏi tự kiểm tra

1. **Hai `JdbcTemplate` khác instance nhưng cùng datasource có thể tham gia cùng transaction không?** — Có, khi cùng Spring-managed transaction/resource context và dùng connection lookup đúng cách.
2. **Hai DAO là singleton có đồng nghĩa mọi request dùng cùng connection không?** — Không. Mỗi transaction/thread có resource riêng.
3. **Trong JDBC local transaction, Spring lưu gì để các DAO dùng lại?** — Thường là `ConnectionHolder` bind theo key `DataSource` trong `TransactionSynchronizationManager`.
4. **Vì sao DAO B đọc được INSERT chưa commit của DAO A?** — Vì chúng đang dùng cùng physical transaction/connection, không phải vì DB cho dirty read giữa transactions.
5. **Khi viết raw JDBC trong Spring, nên lấy và release connection qua đâu?** — `DataSourceUtils.getConnection(ds)` và `DataSourceUtils.releaseConnection(con, ds)`.
6. **Vì sao `dataSource.getConnection()` thô có thể phá atomicity?** — Nó có thể lấy connection khác với auto-commit, không tham gia Spring transaction đang bind.
7. **Khi nào `TransactionAwareDataSourceProxy` hữu ích?** — Khi tích hợp thư viện legacy bắt buộc dùng datasource/getConnection JDBC chuẩn và không thể đổi sang Spring-aware lookup.
8. **Inner `REQUIRED` dùng connection nào nếu outer đang có transaction JDBC?** — Thường cùng connection outer; không mở physical transaction mới.
9. **Inner `REQUIRES_NEW` có dùng connection A của outer không?** — Không theo semantics independent physical transaction; outer tạm ngưng, inner dùng resource khác rồi resume outer.
10. **`NESTED` khác `REQUIRES_NEW` thế nào?** — NESTED thường dùng savepoint trên một physical transaction; REQUIRES_NEW có transaction vật lý riêng.
11. **`JpaRepository` và `JdbcTemplate` cùng datasource có chắc chắn thấy dữ liệu của nhau ngay không?** — Không tự động. Phải cấu hình transaction manager/provider đúng và chú ý JPA flush/persistence context.
12. **MyBatis mapper nào tham gia Spring transaction đúng cách?** — Mapper/`SqlSession` do MyBatis-Spring `SqlSessionTemplate` quản lý và được cấu hình datasource/manager đúng.
13. **Hai datasource cùng server DB có tự thành một ACID transaction không?** — Không. Local manager thường chỉ quản lý một resource; cần phối hợp transaction phân tán hoặc workflow khác.
14. **`@Async` có tự chia sẻ bound JDBC connection của caller không?** — Không; imperative transaction context theo thread.
15. **Cách chứng minh mạnh nhất rằng DAO A/B thật sự atomic?** — Integration test success và rollback sau khi cả hai thao tác, truy vấn dữ liệu bằng transaction mới.
16. **So sánh `Connection == expected` có phải chứng cứ phổ quát không?** — Không. Proxy/wrappers có thể cho handle khác; xem semantic transaction và outcome thật.

## 17. Tóm tắt

- **Cùng datasource không tự đủ; cùng transaction boundary + manager đúng + transaction-aware lookup mới là điều cốt lõi.**
- Trong một local Spring JDBC transaction, các DAO dùng `JdbcTemplate` hoặc `DataSourceUtils` với cùng datasource có thể lấy lại cùng bound connection và tham gia **một physical transaction**.
- `DataSourceTransactionManager`/`JdbcTransactionManager` chịu trách nhiệm begin/commit/rollback, bind/unbind/release resource. DAO không tự commit/đóng connection transaction.
- `TransactionAwareDataSourceProxy` là giải pháp tương thích cho một số thư viện legacy; không cần cho code mới dùng `JdbcTemplate`.
- `REQUIRED` thường tham gia resource outer, `REQUIRES_NEW` dùng transaction/resource độc lập, `NESTED` thường dùng savepoint trên resource hiện hành.
- JPA/ORM, MyBatis, nhiều datasources và async/reactive có những điều kiện liên kết riêng; đừng suy “cùng tài nguyên” chỉ vì cùng một method hoặc cùng URL DB.
- **Hãy kiểm chứng bằng trạng thái DB sau commit/rollback**, không chỉ bằng một boolean transaction active, tên bean hay Java object identity.

## Tài liệu tham khảo chính thức

- Spring Framework — Controlling Database Connections (`JdbcTemplate`, `DataSourceUtils`, `TransactionAwareDataSourceProxy`, transaction manager): https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Framework — Transaction Propagation (REQUIRED / REQUIRES_NEW / NESTED): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — `DataSourceUtils` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — `DataSourceTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `JdbcTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — `JpaTransactionManager` Javadoc (JPA/JDBC integration): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html
- MyBatis-Spring — Transactions: https://mybatis.org/spring/transactions.html
- MyBatis-Spring — `SqlSessionTemplate`: https://mybatis.org/spring/sqlsession.html
