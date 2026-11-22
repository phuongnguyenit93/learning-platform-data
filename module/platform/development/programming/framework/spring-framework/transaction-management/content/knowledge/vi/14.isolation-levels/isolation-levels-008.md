# Isolation chỉ có hiệu lực trong điều kiện manager hỗ trợ

## 1. Ý chính: annotation đưa ra yêu cầu, manager mới áp dụng

Trong Spring Framework, cấu hình:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void placeOrder() {
    // Câu SQL chạy trong transaction của nghiệp vụ.
}
~~~

không có nghĩa Spring luôn có thể ép mọi database thực thi `SERIALIZABLE`. Đây chỉ là **một yêu cầu isolation** trong transaction definition. Việc thực hiện phụ thuộc vào **transaction manager**, loại tài nguyên, JDBC/ORM/reactive driver, database và thời điểm transaction bắt đầu.

Để mức cô lập mong muốn thật sự có hiệu lực, cần đồng thời:

1. **Lời gọi được transaction interceptor xử lý**: method được gọi qua Spring-managed proxy hoặc cơ chế transaction tương đương, không phải chỉ có annotation trong source.
2. **Một physical transaction mới được bắt đầu**: custom isolation được thiết kế chủ yếu cho `Propagation.REQUIRED`/`REQUIRES_NEW` khi mở transaction mới, không phải cứ vào method inner là thay mức của transaction đang chạy.
3. **Manager hỗ trợ custom isolation**: ví dụ `DataSourceTransactionManager`/`JdbcTransactionManager` có cơ chế dùng JDBC connection; các manager JPA/JTA có hạn chế khác.
4. **Driver và database hỗ trợ yêu cầu đó**: có thể từ chối, có thể chuẩn hóa theo khả năng engine, hoặc triển khai semantics khác nhau.
5. **Các SQL thực sự dùng đúng resource tham gia transaction**: nếu code lấy connection riêng hoặc một datasource khác, mức isolation của transaction do Spring quản lý không nhất thiết bao trùm chúng.

Đoạn Java đầu là **snippet**, không chạy độc lập vì chưa có imports, class và hạ tầng. Phần 6 có ví dụ Maven/Spring Boot/JDBC/H2/JUnit đầy đủ.

### Chuỗi từ khai báo đến thực thi

~~~text
@Transactional(isolation = SERIALIZABLE)
                  |
                  v
Transaction interceptor có được gọi qua proxy?
                  |
                  v
PlatformTransactionManager
                  |
             Có T1 đang tồn tại?
                  |
          +-------+---------+
          |                 |
       Có T1             Chưa có T1
          |                 |
       REQUIRED          Tạo T1 mới
       tham gia T1           |
          |                 v
       Giữ mức         Manager chuẩn bị resource
       của T1          và yêu cầu isolation
          |                 |
          +----------+------+
                     |
             JDBC / JPA / JTA / R2DBC
                     |
             Driver và DB engine
                     |
          Mức được hỗ trợ hay lỗi
                     |
         SQL chạy thực tế trên resource
~~~

Nếu manager không hỗ trợ custom isolation, yêu cầu có thể bị **từ chối bằng exception**. Không nên khẳng định Spring luôn im lặng hạ isolation. Mặt khác, driver có thể chấp nhận lời gọi cấu hình nhưng DB diễn giải từng mức theo semantics riêng: **mức được chấp nhận không bảo đảm mọi anomaly tuân theo cùng một bảng giản lược ở mọi engine**.

## 2. Isolation bảo vệ điều gì trong transaction đồng thời?

Isolation mô tả quan hệ quan sát dữ liệu giữa các transaction. Những hiện tượng thường được nêu:

- **Dirty read**: đọc dữ liệu chưa commit từ transaction khác.
- **Non-repeatable read**: đọc lại cùng một hàng trong một transaction nhưng giá trị thay đổi do transaction khác commit xen giữa.
- **Phantom read**: thực thi lại truy vấn theo điều kiện và tập kết quả thay đổi do ghi đồng thời.
- **Serialization anomaly**: kết quả các transaction chạy đồng thời không tương đương một thứ tự thực hiện tuần tự hợp lệ. Các mẫu như write skew cần xét cả ràng buộc nghiệp vụ và semantics của engine.

Spring cung cấp enum `org.springframework.transaction.annotation.Isolation` với các mức thông dụng:

| Mức | Ý nghĩa lý thuyết | Caveat quan trọng |
| --- | --- | --- |
| `DEFAULT` | Dùng mức mặc định từ transaction infrastructure/database | **Không đồng nghĩa READ_COMMITTED ở mọi hệ**. |
| `READ_UNCOMMITTED` | Mức yêu cầu yếu nhất trong phân loại SQL phổ biến | Một số engine không cho dirty reads và ánh xạ nó sang mức khác. |
| `READ_COMMITTED` | Không đọc dữ liệu chưa commit theo mô hình thông dụng | Không tự loại bỏ mọi race hoặc non-repeatable read. |
| `REPEATABLE_READ` | Hướng tới đọc lặp lại cùng một hàng nhất quán | Snapshot/locking và phantom phụ thuộc DB. |
| `SERIALIZABLE` | Kết quả các transaction thành công tương đương một lịch tuần tự | Có thể phải chờ, abort hoặc retry do xung đột. |

**Không áp bảng SQL isolation như một cam kết triển khai giống hệt trên mọi RDBMS.** Chẳng hạn PostgreSQL xử lý `READ_UNCOMMITTED` tương đương hành vi `READ_COMMITTED`. MySQL/InnoDB, PostgreSQL và H2 có chiến lược snapshot/lock khác nhau. Mức isolation cũng không thay thế constraint, thiết kế cập nhật có điều kiện, idempotency hoặc kiểm tra quyền truy cập.

### Ví dụ nghiệp vụ

Hai giao dịch cùng kiểm tra tồn kho rồi đặt hàng. Chỉ ghi:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void reserve() {
    // SELECT stock; if enough -> UPDATE stock.
}
~~~

không chứng minh ứng dụng tránh overselling. Bạn còn phải xác nhận manager thực sự áp isolation, code truy cập đúng DB, engine xử lý xung đột ra sao, rollback/retry có đúng không và cập nhật có điều kiện `WHERE stock >= ?` hoặc constraint phù hợp.

## 3. Khả năng của từng transaction manager

`PlatformTransactionManager` là một abstraction chung, **không phải lời hứa mọi implementation hỗ trợ tất cả isolation levels**.

### 3.1. JDBC: DataSourceTransactionManager và JdbcTransactionManager

Với một `DataSource` JDBC, `DataSourceTransactionManager` có thể yêu cầu custom isolation khi bắt đầu transaction mới bằng việc chuẩn bị JDBC `Connection`. `JdbcTransactionManager` là biến thể mở rộng, giữ khả năng JDBC này và bổ sung cơ chế dịch exception transaction phù hợp với `JdbcTemplate`.

Ở tầng JDBC, thao tác tương ứng về bản chất là:

~~~java
connection.setTransactionIsolation(
    java.sql.Connection.TRANSACTION_SERIALIZABLE
);
~~~

Đây là **snippet cấp thấp**, không nên tự gọi trong method đang được Spring quản lý. Spring transaction manager còn phải điều phối auto-commit, connection binding, rollback/commit và khôi phục trạng thái kết nối khi hoàn tất.

`JdbcTemplate` dùng `DataSourceUtils` để lấy connection tham gia transaction hiện tại. Nếu tự dùng `dataSource.getConnection()` lấy một kết nối khác rồi ghi, bạn có thể bỏ qua resource được Spring quản lý.

### 3.2. JPA: JpaTransactionManager và JpaDialect

Khi dùng JPA, transaction manager phải phối hợp với JPA `EntityManager`, provider và `JpaDialect`. Theo tài liệu Spring, một `JpaDialect` phù hợp có thể hỗ trợ khả năng nâng cao như **custom isolation**, timeout và truy cập JDBC connection. `DefaultJpaDialect` không cung cấp đầy đủ những khả năng nâng cao đó.

Do vậy:

- Không kết luận rằng **mọi JpaTransactionManager đều áp được mọi isolation**.
- Cũng không kết luận rằng **mọi JpaTransactionManager đều tuyệt đối không thể áp**; việc có `HibernateJpaDialect`/vendor adapter và hạ tầng JDBC liên quan có thể thay đổi khả năng.
- Khi chuyển từ JDBC thuần sang JPA, phải kiểm tra cấu hình thực tế và viết integration test trên provider đang dùng, không chỉ giữ nguyên annotation `@Transactional`.

### 3.3. JTA: coordinator có giới hạn riêng

`JtaTransactionManager` phối hợp môi trường JTA, thường liên quan đến transaction coordinator/container. Tài liệu Spring nêu JTA **không hỗ trợ các JDBC custom isolation levels theo cùng cơ chế với DataSourceTransactionManager**. Transaction vẫn có thể commit/rollback, nhưng yêu cầu isolation tùy biến qua Spring không mặc nhiên được áp.

Nếu transaction manager không hỗ trợ một mức tùy biến, khi mở transaction có thể phát sinh exception thay vì tự chuyển xuống mức mặc định. Cần kiểm tra root cause; không nuốt lỗi cấu hình làm cho code chạy tiếp với một giả định an toàn sai.

### 3.4. R2DBC/reactive

`R2dbcTransactionManager` điều phối reactive transactions theo abstraction reactive, không dùng thread-bound JDBC `Connection` như lab. Việc áp isolation phụ thuộc vào reactive manager, R2DBC driver và database. Các snippet `JdbcTemplate` phía dưới **không** áp cho reactive code.

### Bảng so sánh

| Hạ tầng | Đường áp isolation | Điều cần xác minh |
| --- | --- | --- |
| JDBC + `DataSourceTransactionManager`/`JdbcTransactionManager` | JDBC Connection khi tạo physical transaction | Driver/DB hỗ trợ, cùng DataSource, đúng proxy |
| JPA + `JpaTransactionManager` | JPA provider / `JpaDialect` / JDBC khi được hỗ trợ | Dialect, vendor, cấu hình transaction |
| JTA + `JtaTransactionManager` | Transaction coordinator, khác JDBC cục bộ | Custom isolation có thực sự được hỗ trợ hay bị từ chối |
| R2DBC + reactive manager | R2DBC transaction definition/driver | Reactive resource và khả năng driver/DB |
| Manager tự viết hoặc wrapper | Theo code của implementation | Không được giả định chỉ vì implement `PlatformTransactionManager` |

## 4. Tại sao một inner @Transactional không thay được outer?

Giả sử có hai Spring beans:

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void outer() {
        inner.work();
    }
}

@Service
class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED
    )
    public void work() {
        // Đang tham gia physical transaction của outer.
    }
}
~~~

Đây là **mã minh họa chưa có imports**, không phải project độc lập. Nếu outer mở transaction T1 với isolation `SERIALIZABLE`, khi inner `REQUIRED` được gọi qua proxy, nó tham gia **T1**, không yêu cầu thay isolation thành `READ_COMMITTED` trên connection giữa chừng.

Phân biệt:

- **Metadata resolution:** annotation trực tiếp trên method có thể ưu tiên hơn annotation trên class cho chính lời gọi đó.
- **Physical transaction lifetime:** một T1 đã mở có isolation thực tế; inner `REQUIRED` mặc định dùng thông số T1.
- **Logical scope:** inner vẫn có transaction advice scope riêng và có thể có rollback rules, nhưng không tự tạo physical transaction mới.

### Chế độ mặc định và strict validation

Với manager kế thừa `AbstractPlatformTransactionManager`, cấu hình `setValidateExistingTransaction(false)` thường được dùng mặc định: **lenient participation** — inner có isolation khai báo khác nhưng vẫn tham gia outer, giữ mức của outer.

Nếu bật `setValidateExistingTransaction(true)`, manager có thể **từ chối** inner `READ_COMMITTED` đang cố tham gia outer `SERIALIZABLE` và ném `IllegalTransactionStateException`. Mục tiêu là phát hiện mismatch **chứ không bắt outer đổi sang inner**.

Nếu inner dùng `REQUIRES_NEW`, Spring tạm đình chỉ outer và mở transaction T2 riêng; manager có thể áp isolation của T2 khi hạ tầng hỗ trợ. Nhưng T2 commit độc lập, có chi phí connection riêng và có thể ảnh hưởng tính nguyên tử nghiệp vụ. Đừng dùng `REQUIRES_NEW` như cách sửa isolation mặc định khi thực chất cần các thao tác cùng commit.

| Cách gọi | Physical transaction | Kết quả isolation trong ví dụ |
| --- | --- | --- |
| Gọi inner `REQUIRED(READ_COMMITTED)` khi **không có outer** | T1 mới | JDBC manager có thể áp READ_COMMITTED |
| Outer `SERIALIZABLE` gọi inner `REQUIRED(READ_COMMITTED)` | Chung T1 | Inner thường dùng SERIALIZABLE của T1 |
| Outer `SERIALIZABLE` gọi inner `REQUIRES_NEW(READ_COMMITTED)` | T1 tạm đình chỉ; T2 mới | Inner T2 có thể dùng READ_COMMITTED; outer T1 vẫn SERIALIZABLE |
| Strict validation, inner `REQUIRED` khác isolation T1 | T1 hiện hữu; join bị từ chối | Exception, **không thay đổi isolation T1** |

## 5. Kiểm tra gì để chứng minh isolation đã được áp?

Không nên chỉ log dòng annotation. Có ba cấp thông tin khác nhau:

1. **Giá trị yêu cầu trong `@Transactional`:** ý định của application.
2. **Metadata transaction mà Spring lưu:** `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` có thể phản ánh mức Spring ghi nhận. Với `DEFAULT` metadata có thể `null`.
3. **Mức mà JDBC connection thật báo về:** `Connection.getTransactionIsolation()` lấy trên **connection tham gia transaction** thông qua `JdbcTemplate.execute(ConnectionCallback)` hoặc `DataSourceUtils`.

Cấp 3 phản ánh cấu hình JDBC gần database hơn, nhưng vẫn chưa đủ để chứng minh một anomaly cụ thể bị ngăn. Để chắc chắn semantics, cần **test hai transaction đồng thời trên database đích** và kiểm tra kết quả/exception.

Ví dụ code truy vấn connection trong `JdbcTemplate`:

~~~java
Integer level = jdbcTemplate.execute(
    (ConnectionCallback<Integer>) connection ->
        connection.getTransactionIsolation()
);
~~~

Đây là snippet (cần import `ConnectionCallback` và có bean `JdbcTemplate`). Không lấy một connection hoàn toàn mới từ datasource bên ngoài rồi cho rằng mức của nó đại diện transaction đang chạy.

JDBC driver còn cung cấp:

~~~java
boolean supports = connection.getMetaData()
    .supportsTransactionIsolationLevel(
        java.sql.Connection.TRANSACTION_SERIALIZABLE
    );
~~~

Đây là phép hỏi **driver công bố có hỗ trợ mức đó không**, không phải kiểm thử những anomaly xảy ra trong thực tế. Trong bài lab, dùng hai cơ chế này phối hợp với status của Spring.

## 6. Dự án runnable: Spring Boot 3.5 / Java 17 / H2

Bài lab tách rõ **có transaction mới**, **tham gia outer** và **manager strict**. Nó dùng Java 17+, Spring Boot 3.5.0, Spring JDBC, H2 in-memory và JUnit 5. Không cần cài database server riêng.

### 6.1. Cấu trúc thư mục

~~~text
isolation-manager-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/isolationlab/
    │   │   ├── IsolationLabApplication.java
    │   │   ├── IsolationView.java
    │   │   ├── InnerIsolationService.java
    │   │   └── OuterIsolationService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/isolationlab/
            ├── NormalIsolationTest.java
            └── StrictIsolationTest.java
~~~

Không có `schema.sql` vì bài này chỉ đọc isolation level từ connection; test cần đo cấu hình transaction, **không giả vờ đã thực hiện concurrency load test**.

### 6.2. Tệp pom.xml

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
    <artifactId>isolation-manager-lab</artifactId>
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

### 6.3. Tệp application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:isolation_manager_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
lab.strict=false
~~~

H2 chỉ là database trong bộ nhớ JVM, không phải nơi lưu trữ production.

### 6.4. Tệp IsolationLabApplication.java

~~~java
package com.example.isolationlab;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class IsolationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationLabApplication.class, args);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource,
            Environment environment) {
        boolean strict =
            environment.getProperty("lab.strict", Boolean.class, false);

        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
        manager.setValidateExistingTransaction(strict);
        return manager;
    }
}
~~~

Chúng ta chủ động khai báo **một `DataSourceTransactionManager`** cho đúng `DataSource` dùng bởi `JdbcTemplate`. Nó là manager JDBC có cơ chế custom isolation. Hai class test sẽ chạy với hai giá trị property `lab.strict` khác nhau, Spring tạo hai application contexts tương ứng.

`setValidateExistingTransaction(true)` không ép custom isolation lên inner; nó làm cho mismatch với transaction đã tồn tại bị **từ chối**. Không nên thay đổi flag này trên manager singleton đang phục vụ request thật chỉ để thực hành.

### 6.5. Tệp IsolationView.java

~~~java
package com.example.isolationlab;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public record IsolationView(
    boolean active,
    boolean newTransaction,
    int jdbcLevel
) {
    public static IsolationView capture(JdbcTemplate jdbc) {
        Integer level = jdbc.execute(
            (ConnectionCallback<Integer>) connection ->
                connection.getTransactionIsolation()
        );
        if (level == null) {
            throw new IllegalStateException("No JDBC level returned");
        }

        return new IsolationView(
            TransactionSynchronizationManager.isActualTransactionActive(),
            TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction(),
            level
        );
    }
}
~~~

`TransactionAspectSupport.currentTransactionStatus()` được gọi **trong method đã được transaction interceptor bao**, không phải ngoài proxy. Dùng `JdbcTemplate` cho phép đọc transaction-bound connection. Record `IsolationView` là Java 17 và không phải MVCC snapshot.

### 6.6. Tệp InnerIsolationService.java

~~~java
package com.example.isolationlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerIsolationService {
    private final JdbcTemplate jdbc;

    public InnerIsolationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED
    )
    public IsolationView requiredReadCommitted() {
        return IsolationView.capture(jdbc);
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.READ_COMMITTED
    )
    public IsolationView requiresNewReadCommitted() {
        return IsolationView.capture(jdbc);
    }

    @Transactional(isolation = Isolation.DEFAULT)
    public IsolationView usingDefault() {
        return IsolationView.capture(jdbc);
    }
}
~~~

Khi `requiredReadCommitted()` được gọi riêng từ test không có transaction, nó mở transaction mới, JDBC isolation được áp `READ_COMMITTED`. Khi nó tham gia outer `SERIALIZABLE`, connection vẫn báo `SERIALIZABLE`. `requiresNewReadCommitted()` có thể bắt đầu transaction độc lập khi cần.

### 6.7. Tệp OuterIsolationService.java

~~~java
package com.example.isolationlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterIsolationService {
    public record Comparison(
        IsolationView before,
        IsolationView inner,
        IsolationView after
    ) {}

    private final InnerIsolationService inner;
    private final JdbcTemplate jdbc;

    public OuterIsolationService(
            InnerIsolationService inner,
            JdbcTemplate jdbc) {
        this.inner = inner;
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public Comparison callRequired() {
        IsolationView before = IsolationView.capture(jdbc);
        IsolationView inside = inner.requiredReadCommitted();
        IsolationView after = IsolationView.capture(jdbc);
        return new Comparison(before, inside, after);
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public Comparison callRequiresNew() {
        IsolationView before = IsolationView.capture(jdbc);
        IsolationView inside = inner.requiresNewReadCommitted();
        IsolationView after = IsolationView.capture(jdbc);
        return new Comparison(before, inside, after);
    }
}
~~~

Outer và inner nằm ở **hai Spring beans khác nhau**, đảm bảo lời gọi qua proxy, tránh bẫy self-invocation `this.method()`. Bộ ba `before/inner/after` cho thấy isolation trước, trong và sau lời gọi inner **trong khi outer transaction vẫn còn hoạt động**.

### 6.8. Tệp NormalIsolationTest.java

~~~java
package com.example.isolationlab;

import java.sql.Connection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = "lab.strict=false")
class NormalIsolationTest {
    @Autowired
    private InnerIsolationService inner;

    @Autowired
    private OuterIsolationService outer;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void standaloneRequiredAppliesReadCommitted() {
        IsolationView v = inner.requiredReadCommitted();

        assertTrue(v.active());
        assertTrue(v.newTransaction());
        assertEquals(Connection.TRANSACTION_READ_COMMITTED,
                     v.jdbcLevel());
    }

    @Test
    void innerRequiredCannotOverrideSerializableOuter() {
        OuterIsolationService.Comparison r = outer.callRequired();

        assertTrue(r.before().active());
        assertTrue(r.inner().active());
        assertTrue(r.after().active());

        assertTrue(r.before().newTransaction());
        assertFalse(r.inner().newTransaction());

        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.before().jdbcLevel());
        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.inner().jdbcLevel());
        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.after().jdbcLevel());
    }

    @Test
    void requiresNewGetsItsOwnIsolationAndOuterResumes() {
        OuterIsolationService.Comparison r = outer.callRequiresNew();

        assertTrue(r.inner().active());
        assertTrue(r.inner().newTransaction());

        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.before().jdbcLevel());
        assertEquals(Connection.TRANSACTION_READ_COMMITTED,
                     r.inner().jdbcLevel());
        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.after().jdbcLevel());
    }

    @Test
    void defaultUsesDataSourceConnectionSetting() {
        Integer outside = jdbc.execute(
            (ConnectionCallback<Integer>) connection ->
                connection.getTransactionIsolation()
        );

        IsolationView inTransaction = inner.usingDefault();

        assertTrue(inTransaction.active());
        assertTrue(inTransaction.newTransaction());
        assertEquals(outside.intValue(), inTransaction.jdbcLevel());
    }

    @Test
    void h2DriverReportsSerializableSupport() {
        Boolean supported = jdbc.execute(
            (ConnectionCallback<Boolean>) connection ->
                connection.getMetaData().supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_SERIALIZABLE
                )
        );
        assertEquals(Boolean.TRUE, supported);
    }
}
~~~

Năm test này cho thấy:

- Một **transaction mới** với JDBC manager có thể áp `READ_COMMITTED`.
- Inner `REQUIRED` tham gia outer `SERIALIZABLE` không thay isolation outer.
- `REQUIRES_NEW` tạo physical transaction mới dùng isolation riêng, outer resume với isolation của mình.
- `DEFAULT` không ép một giá trị isolation cố định độc lập với datasource.
- JDBC driver H2 **công bố** hỗ trợ `SERIALIZABLE`.

Chưa có test nào chạy hai transaction cạnh tranh trên một bảng, nên **không** coi các test này là bằng chứng về toàn bộ anomaly/isolation behavior của hệ thống production.

### 6.9. Tệp StrictIsolationTest.java

~~~java
package com.example.isolationlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.IllegalTransactionStateException;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(properties = "lab.strict=true")
class StrictIsolationTest {
    @Autowired
    private OuterIsolationService outer;

    @Test
    void strictManagerRejectsJoiningWithDifferentIsolation() {
        assertThrows(
            IllegalTransactionStateException.class,
            outer::callRequired
        );
    }
}
~~~

Ở chế độ strict, outer mở `SERIALIZABLE` và inner `REQUIRED` yêu cầu `READ_COMMITTED`. Manager từ chối **tham gia** với isolation khác, thay vì sửa T1 thành READ_COMMITTED.

**Đừng nhầm phép thử strict với kiểm tra manager không hỗ trợ custom isolation:** strict validation kiểm tra **mismatch của một participant**; unsupported custom isolation là tình huống manager không thể áp yêu cầu cho **transaction mới**. Đây là hai nguyên nhân lỗi khác nhau.

Hai test classes chạy trong hai Spring application contexts có property riêng; chúng không ghi bảng nên không cần `schema.sql`. Nếu ứng dụng thực tế có nhiều transaction managers, cần bảo đảm test đi qua đúng manager.

### 6.10. Chạy và kết quả dự kiến

Trong thư mục `isolation-manager-lab`, dùng JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

Nếu dependencies tải được và môi trường đúng, Maven Surefire dự kiến có **6 tests pass, 0 failures, 0 errors**. Thứ tự test, log Spring và thời gian chạy có thể khác nhau. Đây là **kết quả dự kiến từ source**, không phải log thực tế đã chạy trong bài.

| Test | Giá trị/hiện tượng được khẳng định |
| --- | --- |
| `standaloneRequiredAppliesReadCommitted` | active=true, newTransaction=true, JDBC level=READ_COMMITTED |
| `innerRequiredCannotOverrideSerializableOuter` | SERIALIZABLE → SERIALIZABLE → SERIALIZABLE |
| `requiresNewGetsItsOwnIsolationAndOuterResumes` | SERIALIZABLE → READ_COMMITTED → SERIALIZABLE |
| `defaultUsesDataSourceConnectionSetting` | DEFAULT khớp setting của datasource connection trong lab |
| `h2DriverReportsSerializableSupport` | JDBC metadata trả về true |
| `strictManagerRejectsJoiningWithDifferentIsolation` | `IllegalTransactionStateException` |

## 7. Khi manager không hỗ trợ: phân biệt cách thất bại

### 7.1. Transaction manager từ chối isolation tùy biến

Một manager có thể hỗ trợ `commit/rollback` nhưng **không hỗ trợ custom isolation**. Trong trường hợp đó yêu cầu như `Isolation.SERIALIZABLE` có thể làm transaction startup thất bại, ví dụ qua `InvalidIsolationLevelException`; không nên tự giả định Spring sẽ im lặng áp mức thấp hơn.

Với JPA, cần tìm hiểu `JpaDialect`/provider; với JTA, kiểm tra giới hạn của coordinator. Hãy đọc exception thực tế và log root cause của hệ thống đang chạy.

### 7.2. JDBC driver không hỗ trợ mức yêu cầu

Một `DataSourceTransactionManager` có thể có code để gọi `Connection.setTransactionIsolation(level)`, nhưng driver/database không chấp nhận `level` ấy. Khi đó `SQLException` có thể được bọc thành exception của hạ tầng transaction Spring. Không có một tên exception duy nhất đúng cho tất cả engine/driver/manager.

Kiểm tra driver qua `DatabaseMetaData.supportsTransactionIsolationLevel(level)`, kiểm tra kết quả trên connection, và test database thật. Metadata công bố là tín hiệu, không phải chứng cứ tuyệt đối cho mọi semantics concurrency.

### 7.3. Database ánh xạ hoặc triển khai isolation đặc thù

Ngay cả khi request không lỗi, hành vi database có thể không giống giả thuyết lý thuyết đơn giản. Ví dụ PostgreSQL `READ_UNCOMMITTED` hoạt động như `READ_COMMITTED`. Một engine có thể có snapshot isolation hoặc locking rules ảnh hưởng việc quan sát phantom/write skew.

Do vậy **không quy đổi một giá trị enum thành cam kết concurrency trên tất cả database**. Đối với invariant quan trọng, chạy tests nhiều phiên/transaction trên engine production và quan sát kết quả cuối, exception, retry path.

## 8. Các lỗi thường gặp

### 8.1. Gắn SERIALIZABLE ở method trong, nhưng outer đã mở transaction

Nếu inner `REQUIRED`, nó tham gia physical transaction có sẵn và không tự đổi mức. Giải pháp tốt thường là đặt isolation tại **service facade mở transaction**. Khi thực sự cần transaction mới, cân nhắc `REQUIRES_NEW` nhưng nhớ việc commit độc lập có thể làm mất nguyên tử tổng thể.

### 8.2. Đọc sai JDBC connection

Không lấy một connection tùy ý bằng `DataSource.getConnection()` rồi coi đó là connection trong transaction Spring. Dùng `JdbcTemplate` hoặc `DataSourceUtils` để truy cập đúng connection đang được bind.

### 8.3. Nhầm `Isolation.DEFAULT` với `READ_COMMITTED`

DEFAULT phụ thuộc database, driver, pool config và transaction infrastructure; không phải hằng số thực tế duy nhất. Khi dùng nhiều database, tránh hardcode mức mặc định.

### 8.4. Tự new service hoặc self-invocation

`@Transactional` cần Spring interceptor. Trong proxy mode, `new SomeService(...)` hoặc `this.someTransactionalMethod()` thường không kích hoạt advice. Không thể dùng isolation annotation để bảo vệ code nếu transaction chưa được mở.

### 8.5. Dùng sai transaction manager

Nhiều datasource/managers có thể dẫn đến isolation được áp cho resource A nhưng các SQL thực thi ở resource B. Cần xác định manager mặc định/qualifier và đường đi connection.

### 8.6. Nghĩ manager hỗ trợ JDBC thì mọi DB cũng hỗ trợ

Spring có thể gọi `setTransactionIsolation` nhưng driver/engine vẫn quyết định có chấp nhận mức đó. Đừng cam kết READ_UNCOMMITTED hoặc SERIALIZABLE hoạt động giống mọi DB.

### 8.7. Bật strict validation và tưởng nó nâng isolation

`setValidateExistingTransaction(true)` **từ chối** mismatch của inner `REQUIRED`, không đổi isolation của transaction đã mở. Thử strict riêng trong lab để tránh thay đổi policy production vô ý.

### 8.8. Cho rằng test JDBC level đã chứng minh chống được race

`Connection.getTransactionIsolation()` đo setting mà connection báo về. Nó không chứng minh trong thực tế transaction A/B có hay không dirty read, write skew hoặc serialization failure. Viết concurrency tests độc lập khi nghiệp vụ cần bảo đảm.

### 8.9. Tăng isolation thay cho transaction retry

SERIALIZABLE có thể dẫn tới chờ/abort/retry. Thiết kế production cần retry **toàn transaction** khi phù hợp, idempotency cho yêu cầu có thể lặp, và constraint/validation bảo vệ bất biến.

### 8.10. Nhầm isolation với rollback rules

`isolation` điều khiển môi trường đọc/ghi đồng thời; `rollbackFor`/`noRollbackFor` quyết định Spring yêu cầu rollback theo ngoại lệ. Isolation mạnh không tự biến mọi checked exception thành rollback; hai nhóm thuộc tính độc lập.

## 9. Quy trình quyết định và kiểm thử

1. Xác định **bất biến nghiệp vụ** cần bảo vệ và anomaly cần ngăn.
2. Xác định **DB engine/version**, default isolation, driver và connection pool.
3. Xác định **PlatformTransactionManager thực tế**; đừng dựa vào tên annotation.
4. Đặt isolation ở method **thực sự tạo physical transaction**.
5. Xác minh lời gọi đi qua **Spring proxy** và các SQL dùng đúng resource.
6. Kiểm tra khả năng manager/driver/DB chấp nhận custom isolation.
7. Đo isolation trên JDBC connection **đang trong transaction**, không trên một connection ngẫu nhiên.
8. Khi inner khai báo mức khác outer, cân nhắc strict validation để phát hiện cấu hình xung đột.
9. Viết test đồng thời trên engine đích, ghi nhận kết quả và serialization/deadlock errors.
10. Thiết kế cơ chế rollback/retry/idempotency phù hợp, thay vì kỳ vọng enum bảo đảm toàn bộ.

## 10. Câu hỏi tự kiểm tra

1. **`@Transactional(isolation=SERIALIZABLE)` có tự thay isolation của DB không?** — Không; phải có transaction mới, manager và driver/DB hỗ trợ.
2. **`DataSourceTransactionManager` áp custom isolation qua đâu?** — JDBC connection, ví dụ `setTransactionIsolation` lúc bắt đầu transaction.
3. **JPA có luôn áp được custom isolation không?** — Không bảo đảm; phụ thuộc `JpaDialect` và provider.
4. **JTA có hỗ trợ custom JDBC isolation giống manager JDBC không?** — Không được mặc định giả định như vậy; tài liệu Spring nêu giới hạn của JTA.
5. **Inner REQUIRED READ_COMMITTED tham gia outer SERIALIZABLE thì sao?** — Thường dùng SERIALIZABLE của outer, không hạ level.
6. **Inner REQUIRES_NEW READ_COMMITTED thì sao?** — Transaction mới có thể dùng READ_COMMITTED nếu hỗ trợ.
7. **Bật strict validation có khiến inner ghi đè outer không?** — Không; manager có thể ném `IllegalTransactionStateException`.
8. **Isolation.DEFAULT có mặc định là READ_COMMITTED không?** — Không, phụ thuộc infrastructure.
9. **`getCurrentTransactionIsolationLevel()` có giống `getTransactionIsolation()` không?** — Không nhất thiết; một là metadata của Spring, một là setting JDBC connection báo về.
10. **Driver hỗ trợ SERIALIZABLE có chứng minh mọi anomaly không xảy ra không?** — Chưa; cần kiểm tra concurrency trên đúng DB engine.
11. **Có thể dùng `@Transactional` mà không đi qua Spring proxy không?** — Trong proxy mode, lời gọi bypass interceptor không tự áp transaction annotation.
12. **Một manager không hỗ trợ custom isolation sẽ luôn âm thầm bỏ qua yêu cầu?** — Không; có thể ném lỗi và ngăn bắt đầu transaction.
13. **Isolation mạnh có thay được unique constraint và business validation không?** — Không; chúng bổ sung cho nhau.

## 11. Kết luận

**“Isolation chỉ có hiệu lực trong điều kiện manager hỗ trợ”** là ranh giới giữa **ý định cấu hình trong Java** và **khả năng thực thi thực tế**. Spring chỉ điều phối thông qua manager được chọn; manager chỉ có thể dùng những cơ chế resource/driver/database cung cấp; và isolation mới phải được áp vào **đúng physical transaction được mở**.

Muốn tránh cảm giác an toàn giả, hãy kiểm tra **manager, thời điểm bắt đầu transaction, proxy boundary, connection đang tham gia transaction, driver support và semantics concurrency của DB thực tế**.

### Tài liệu tham khảo chính thức

- [Spring Framework — @Transactional Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — AbstractPlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework — JPA and JpaDialect](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
