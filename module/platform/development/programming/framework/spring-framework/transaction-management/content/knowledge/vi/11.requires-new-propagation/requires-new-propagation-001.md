# Tạm ngưng giao dịch ngoài và tạo giao dịch vật lý độc lập với `REQUIRES_NEW`

## 1. Bài toán và kết quả cần hiểu

Trong Spring Framework, `@Transactional(propagation = Propagation.REQUIRES_NEW)` có nghĩa: **mỗi lần phương thức được transaction interceptor xử lý sẽ chạy trong một giao dịch vật lý mới, độc lập với giao dịch ngoài đang tồn tại**. Nếu có giao dịch ngoài, Spring **tạm treo** giao dịch đó trong thời gian giao dịch mới chạy; sau khi giao dịch trong kết thúc (commit hoặc rollback), Spring **khôi phục** giao dịch ngoài cho luồng xử lý tiếp tục.

Ta gọi giao dịch ngoài là **T1** và giao dịch trong là **T2**.

```text
Caller -> OuterService.outer() [@Transactional(REQUIRED)]
          |
          | BEGIN physical T1 (JDBC Connection C1)
          | UPDATE business_row ... (chưa commit)
          |
          +---> InnerService.inner() [@Transactional(REQUIRES_NEW)]
          |       |
          |       | Suspend T1, giữ tài nguyên C1 của T1
          |       | BEGIN physical T2 (JDBC Connection C2)
          |       | UPDATE audit_row ...
          |       | COMMIT / ROLLBACK T2
          |       | Resume T1 (C1)
          |       v
          |
          | Tiếp tục trong T1
          | COMMIT / ROLLBACK T1
          v
Caller
```

Ví dụ nghiệp vụ: service tạo đơn hàng cần ghi một nhật ký thao tác độc lập. Nếu đơn hàng cuối cùng thất bại, một bản ghi nhật ký về **lần thử thực hiện** vẫn có thể phải tồn tại. Nếu inner ghi nhật ký bằng T2 và commit thành công trước khi outer T1 rollback, **T2 không bị rollback theo**. Nhưng không phải mọi bản ghi audit hoặc outbox đều phù hợp `REQUIRES_NEW`: nếu sự kiện chỉ được xuất bản khi đơn hàng commit, tách transaction để event tồn tại dù đơn hàng rollback có thể tạo dữ liệu sai.

Sau bài này, bạn cần trả lời được:

1. «Suspend T1» diễn ra ở tầng Spring/JDBC như thế nào, và tại sao không phải `Thread.suspend()`?
2. Vì sao T2 có thể commit trước T1, và T1 rollback không làm mất dữ liệu T2 đã commit?
3. Khi T2 rollback, T1 có bắt buộc rollback không? Exception Java còn ảnh hưởng thế nào?
4. Vì sao `REQUIRES_NEW` cần thêm JDBC connection và có nguy cơ làm cạn connection pool?
5. Điều gì khiến annotation hiện diện nhưng không có T2: self-invocation, object tạo bằng `new`, sai `ApplicationContext` hay không qua Spring proxy?

## 2. Logical scope, physical transaction và suspend

Một **logical transaction scope** là ranh giới Spring quản lý khi một lời gọi được interceptor xử lý. Một **physical transaction** là giao dịch thực sự của tài nguyên, chẳng hạn JDBC connection đang ở chế độ transaction và được database commit/rollback.

Với `Propagation.REQUIRED` mặc định, nếu T1 đã tồn tại thì inner method `@Transactional(REQUIRED)` **tham gia T1**: hai method có thể có **hai logical scopes nhưng chỉ một physical transaction**. Inner kết thúc bình thường không commit vật lý độc lập.

Với `Propagation.REQUIRES_NEW`, inner không tham gia T1. Spring tạo **physical transaction T2 mới**, tạm chuyển tài nguyên và đồng bộ hóa của T1 ra khỏi transaction context đang hoạt động, rồi trả lại khi T2 kết thúc. Với `DataSourceTransactionManager` trong Spring JDBC thông thường, T1 giữ connection C1, còn T2 lấy connection C2 khác.

### 2.1. Suspend không phải commit, rollback hay ngưng thread

- **Không commit T1:** các cập nhật của T1 vẫn chưa được commit. Đừng xem việc inner bắt đầu như một điểm lưu an toàn cho outer.
- **Không rollback T1:** T1 vẫn tồn tại; khi inner xong, outer tiếp tục công việc như trước.
- **Không giải phóng lock của T1:** connection C1 và những row locks của T1 có thể vẫn còn; inner T2 động vào cùng row đang bị T1 khóa có thể phải đợi.
- **Không tạm ngưng thread Java:** trong mô hình imperative thông thường, cùng một thread Java vào inner proxy, thực thi inner và quay về outer. Thread không bị `Thread.suspend()`; Spring tạm treo **transaction resource context**, không tạm dừng execution thread.
- **Không mặc nhiên trả C1 về pool:** outer có thể tiếp tục giữ connection C1, trong khi inner phải lấy thêm C2.
- **Không tách biệt mọi side effect:** T1/T2 chỉ kiểm soát tài nguyên tham gia đúng transaction manager. Email đã gửi hoặc HTTP request không tự rollback cùng JDBC.

### 2.2. Timeline cụ thể

```text
t0  Outer proxy tạo T1, bind Connection C1 vào thread
t1  Outer UPDATE orders; thay đổi chưa commit
t2  Inner REQUIRES_NEW proxy được gọi
t3  Suspend T1: unbind tài nguyên/synchronization của T1 khỏi context hiện hành
t4  Tạo T2 và bind Connection C2 (khác C1)
t5  Inner UPDATE audit
t6  Kết thúc T2: COMMIT hoặc ROLLBACK T2, dọn tài nguyên T2
t7  Resume T1: khôi phục connection/synchronization của T1
t8  Outer tiếp tục dùng C1
t9  Outer COMMIT hoặc ROLLBACK T1
```

Điều này diễn ra ở tầng transaction infrastructure; ứng dụng không nên tự gọi `TransactionSynchronizationManager.unbindResource(...)` để giả lập `REQUIRES_NEW`. Với manager/tài nguyên khác JDBC, chi tiết suspend có thể khác, nên đừng đồng nhất thứ tự trên với mọi transaction manager.

## 3. Khai báo đúng `REQUIRES_NEW` trong Spring

Mô hình service tách bean:

```java
@Service
public class OrderService {
    private final AuditService auditService;

    public OrderService(AuditService auditService) {
        this.auditService = auditService;
    }

    @Transactional // Mặc định REQUIRED -> tạo T1 nếu chưa có
    public void placeOrder() {
        // Ghi đơn hàng trong T1.
        auditService.recordAttempt(); // Đi qua proxy của AuditService.
        // Xử lý tiếp trong T1.
    }
}

@Service
public class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt() {
        // Ghi nhật ký trong T2 mới.
    }
}
```

Đây là **mã minh họa**, chưa có repository, imports và bean config hoàn chỉnh. `AuditService` phải là Spring bean được quản lý trong context có transaction annotation infrastructure. `OrderService` phải nhận đúng proxy của `AuditService`; Spring cần một transaction manager thích hợp với datasource/ORM đang dùng.

**Vì sao tách hai service?** Trong Spring AOP proxy mode mặc định, nếu hai method ở cùng class và `placeOrder()` gọi `this.recordAttempt()`, inner call không đi qua proxy nên `REQUIRES_NEW` **không được áp dụng** cho lời gọi ấy. Việc đặt annotation không tự chèn interceptor vào một lời gọi Java nội bộ.

### 3.1. Hai tình huống đầu vào

| Trạng thái trước khi gọi inner | Spring làm gì với `REQUIRES_NEW`? |
| --- | --- |
| Không có transaction hiện tại | Bắt đầu một physical transaction mới. Không có T1 để suspend. |
| Đã có T1 do outer mở | Suspend T1, tạo T2 mới, kết thúc T2, resume T1. |

Nếu một T2 lại gọi phương thức `REQUIRES_NEW` khác, Spring có thể tiếp tục suspend T2 để mở T3. Mức lồng sâu sẽ tiêu thụ thêm tài nguyên và tăng rủi ro cạn connection pool.

## 4. Commit và rollback độc lập — nhưng exception không biến mất

Giả sử ban đầu hai hàng database `outer=0`, `inner=0`. Outer tăng hàng `outer` trong T1, inner tăng hàng `inner` trong T2. Những kết quả sau cho thấy độc lập vật lý:

| T2 (inner) | Outer xử lý thế nào? | T1 (outer) | Dữ liệu cuối |
| --- | --- | --- | --- |
| Thành công, commit T2 | Outer hoàn thành | Commit | `outer=1, inner=1` |
| Thành công, commit T2 | Outer sau đó ném unchecked exception | Rollback | `outer=0, inner=1` |
| Lỗi, rollback T2 | Outer catch lỗi và quyết định tiếp tục | Commit | `outer=1, inner=0` |
| Lỗi, rollback T2 | Exception lan ra ngoài outer method | Rollback do rollback rule của T1 | `outer=0, inner=0` |

**Phân biệt độc lập transaction với độc lập control flow.** Inner T2 rollback **không tự đánh dấu T1 rollback-only** chỉ vì hai transaction có quan hệ gọi nhau. Nhưng nếu inner ném `RuntimeException` và outer không bắt, exception tiếp tục đi qua transaction interceptor của outer: Spring có thể rollback T1 theo **rollback policy của chính T1**. Vì vậy câu «`REQUIRES_NEW` đảm bảo outer luôn commit dù inner lỗi» là sai.

Tương tự, inner T2 commit rồi outer T1 rollback **không làm T2 mất commit**. Nếu ứng dụng cần các cập nhật cùng sống/cùng chết, `REQUIRES_NEW` không đáp ứng atomicity chung; hãy dùng cùng transaction `REQUIRED` hoặc một thiết kế phù hợp hơn.

## 5. So sánh propagation để chọn đúng

| Inner propagation | Khi đang có T1 | Ý nghĩa |
| --- | --- | --- |
| `REQUIRED` | Join T1 | Inner không có physical commit riêng; participating scope có thể đánh dấu T1 rollback-only. |
| `REQUIRES_NEW` | Suspend T1; tạo T2 độc lập | Inner commit/rollback độc lập; inner T2 hoàn tất rồi T1 resume. |
| `NESTED` (khi hỗ trợ) | Savepoint trong cùng T1 | Inner rollback có thể quay về savepoint; inner không có independent physical commit. |
| `NOT_SUPPORTED` | Suspend T1 và chạy không có transaction | Không tạo T2; SQL có thể auto-commit theo từng statement. |
| `MANDATORY` | Bắt buộc phải có transaction | Không mở T2; thiếu transaction sẽ gây lỗi. |

Hai điểm đáng nhớ: (1) `NOT_SUPPORTED` cũng có thể suspend T1 nhưng **không** có transaction mới; (2) `NESTED` cho phép rollback cục bộ bằng savepoint trong một số JDBC manager, nhưng nếu outer rollback thì thay đổi inner nested cũng mất. Chỉ `REQUIRES_NEW` của nhóm trên tạo **independent physical transaction** trong khi outer đang có T1.

## 6. Demo đầy đủ: Java 17+, Spring JDBC và H2

Chúng ta xây một ứng dụng Java thuần sử dụng **Spring Framework 6.2.8**, **H2 2.3.232** và Maven. Không cần Spring Boot, HTTP server hay database server. Demo sử dụng hai row khác nhau để tránh T2 chờ lock của row T1 đang cập nhật.

### 6.1. Tệp dự án

```text
requires-new-demo/
├── pom.xml
└── src/main/java/example/RequiresNewDemo.java
```

```xml
<!-- pom.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>requires-new-demo</artifactId>
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
                    <mainClass>example.RequiresNewDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` chứa ApplicationContext/cấu hình; `spring-jdbc` chứa `JdbcTemplate` và JDBC transaction manager; `spring-tx` chứa `@Transactional` và `TransactionStatus`; H2 cung cấp in-memory JDBC datasource. Dùng trực tiếp `org.h2.jdbcx.JdbcDataSource` nên dependency H2 có mặt trên compile classpath.

### 6.2. File `RequiresNewDemo.java`

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

public class RequiresNewDemo {

    private enum Mode { NEW, REQUIRED }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OuterService outer = ctx.getBean(OuterService.class);
            InnerService inner = ctx.getBean(InnerService.class);

            test("both commit", jdbc, outer::bothCommit);
            test(
                "inner commits; outer fails",
                jdbc,
                outer::innerCommitsOuterFails
            );
            test(
                "inner fails; outer catches",
                jdbc,
                outer::innerFailsOuterCatches
            );
            test(
                "inner fails; exception reaches outer",
                jdbc,
                outer::innerFailsOuterPropagates
            );
            test(
                "REQUIRED comparison; outer catches",
                jdbc,
                outer::requiredFailsCaught
            );
            test(
                "REQUIRES_NEW without outer transaction",
                jdbc,
                () -> inner.requiresNew(null, false)
            );
        }
    }

    private static void test(String label, JdbcTemplate jdbc, Runnable action) {
        reset(jdbc);
        System.out.println("CASE: " + label);
        try {
            action.run(); // Caller gọi public @Transactional method qua proxy.
            System.out.println("Outcome: COMMITTED");
        } catch (UnexpectedRollbackException ex) {
            System.out.println("Outcome: UnexpectedRollbackException");
        } catch (IllegalStateException ex) {
            System.out.println("Outcome: " + ex.getMessage());
        }
        Integer a = jdbc.queryForObject(
            "SELECT n FROM counters WHERE counter_key='outer'",
            Integer.class
        );
        Integer b = jdbc.queryForObject(
            "SELECT n FROM counters WHERE counter_key='inner'",
            Integer.class
        );
        System.out.println("Values: outer=" + a + ", inner=" + b);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.execute("DROP TABLE IF EXISTS counters");
        jdbc.execute(
            "CREATE TABLE counters (" +
            "counter_key VARCHAR(20) PRIMARY KEY, n INT NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO counters(counter_key,n) VALUES (?,?)", "outer", 0
        );
        jdbc.update(
            "INSERT INTO counters(counter_key,n) VALUES (?,?)", "inner", 0
        );
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:requires_new;DB_CLOSE_DELAY=-1");
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

    public static class InnerService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;

        public InnerService(JdbcTemplate jdbc, DataSource dataSource) {
            this.jdbc = jdbc;
            this.dataSource = dataSource;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNew(Connection outerConnection, boolean fail) {
            updateInner("REQUIRES_NEW", outerConnection, fail);
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void required(Connection outerConnection, boolean fail) {
            updateInner("REQUIRED", outerConnection, fail);
        }

        private void updateInner(
            String label,
            Connection outerConnection,
            boolean fail
        ) {
            TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();

            Connection current = DataSourceUtils.getConnection(dataSource);
            String sameConnection;
            try {
                sameConnection = outerConnection == null
                    ? "n/a"
                    : String.valueOf(current == outerConnection);
            } finally {
                DataSourceUtils.releaseConnection(current, dataSource);
            }

            System.out.println(
                "Inner " + label
                + ": active="
                + TransactionSynchronizationManager.isActualTransactionActive()
                + ", new=" + status.isNewTransaction()
                + ", savepoint=" + status.hasSavepoint()
                + ", sameConnection=" + sameConnection
            );

            int updated = jdbc.update(
                "UPDATE counters SET n=n+1 WHERE counter_key=?", "inner"
            );
            if (updated != 1) {
                throw new IllegalStateException("inner row missing");
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
        public void bothCommit() {
            execute(Mode.NEW, false, true, false);
        }

        @Transactional
        public void innerCommitsOuterFails() {
            execute(Mode.NEW, false, true, true);
        }

        @Transactional
        public void innerFailsOuterCatches() {
            execute(Mode.NEW, true, true, false);
        }

        @Transactional
        public void innerFailsOuterPropagates() {
            execute(Mode.NEW, true, false, false);
        }

        @Transactional
        public void requiredFailsCaught() {
            execute(Mode.REQUIRED, true, true, false);
        }

        private void execute(
            Mode mode,
            boolean failInner,
            boolean catchInner,
            boolean failOuter
        ) {
            TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();
            System.out.println(
                "Outer before: active="
                + TransactionSynchronizationManager.isActualTransactionActive()
                + ", new=" + status.isNewTransaction()
            );

            int updated = jdbc.update(
                "UPDATE counters SET n=n+1 WHERE counter_key=?", "outer"
            );
            if (updated != 1) {
                throw new IllegalStateException("outer row missing");
            }

            Connection outerConnection =
                DataSourceUtils.getConnection(dataSource);
            try {
                try {
                    if (mode == Mode.NEW) {
                        inner.requiresNew(outerConnection, failInner);
                    } else {
                        inner.required(outerConnection, failInner);
                    }
                } catch (IllegalStateException ex) {
                    if (!catchInner) {
                        throw ex;
                    }
                    System.out.println("Outer caught: " + ex.getMessage());
                } finally {
                    Connection resumed =
                        DataSourceUtils.getConnection(dataSource);
                    try {
                        System.out.println(
                            "Outer after inner: active="
                            + TransactionSynchronizationManager
                                .isActualTransactionActive()
                            + ", sameConnection="
                            + (resumed == outerConnection)
                        );
                    } finally {
                        DataSourceUtils.releaseConnection(resumed, dataSource);
                    }
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

**Vì sao cấu trúc này có ý nghĩa?** `OuterService` và `InnerService` là hai Spring beans, nên inner call được proxy intercept; chúng dùng **cùng datasource/transaction manager**, không phải hai manager tình cờ có cùng tên. Outer đã lấy connection transaction-bound C1 trước khi gọi inner. Trong inner, `DataSourceUtils` lấy connection C2 cho T2; sau inner, outer lấy lại C1. Đây là phép quan sát thích hợp với H2 `JdbcDataSource` **không dùng pool/proxy connection**; ở sản phẩm thật, không dựa duy nhất vào phép so sánh tham chiếu `Connection == Connection`.

`TransactionAspectSupport.currentTransactionStatus()` phải gọi khi đang ở trong method do transaction advice quản lý; helper private `updateInner` được gọi từ bên trong annotated inner method, nên status tại đó vẫn thuộc inner interceptor. `@EnableTransactionManagement` kích hoạt transaction advice; `DataSourceTransactionManager` quản lý local JDBC transactions. Trong ví dụ hoàn chỉnh này, `@Bean` trả về `new` là hợp lệ vì Spring nhận và post-process object ấy thành bean/proxy trước khi caller lấy từ context.

### 6.3. Lệnh chạy và stdout

Trong thư mục `requires-new-demo`, cần JDK 17+ và Maven 3.9+:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Các dòng do chương trình in ra (không tính log Maven/Spring ngoài chương trình):

```text
CASE: both commit
Outer before: active=true, new=true
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer after inner: active=true, sameConnection=true
Outcome: COMMITTED
Values: outer=1, inner=1
CASE: inner commits; outer fails
Outer before: active=true, new=true
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer after inner: active=true, sameConnection=true
Outcome: outer failure
Values: outer=0, inner=1
CASE: inner fails; outer catches
Outer before: active=true, new=true
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer caught: inner failure
Outer after inner: active=true, sameConnection=true
Outcome: COMMITTED
Values: outer=1, inner=0
CASE: inner fails; exception reaches outer
Outer before: active=true, new=true
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer after inner: active=true, sameConnection=true
Outcome: inner failure
Values: outer=0, inner=0
CASE: REQUIRED comparison; outer catches
Outer before: active=true, new=true
Inner REQUIRED: active=true, new=false, savepoint=false, sameConnection=true
Outer caught: inner failure
Outer after inner: active=true, sameConnection=true
Outcome: UnexpectedRollbackException
Values: outer=0, inner=0
CASE: REQUIRES_NEW without outer transaction
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=n/a
Outcome: COMMITTED
Values: outer=0, inner=1
```

### 6.4. Đọc kết quả theo từng tình huống

**1. Both commit:** T1 ghi `outer`, suspend; T2 ghi `inner` và commit; resume T1 và commit. Hai hàng cùng có giá trị 1.

**2. Inner commits, outer fails:** Inner T2 đã commit `inner=1` trước khi outer ném `outer failure`. Outer T1 rollback, chỉ hoàn tác `outer`; kết quả `(0,1)` là bằng chứng rõ cho **hai physical transactions độc lập**.

**3. Inner fails, outer catches:** T2 tự rollback vì `IllegalStateException`. Outer bắt lỗi **sau khi inner proxy đã kết thúc T2**, tiếp tục T1 và commit. Kết quả `(1,0)` chứng tỏ T2 rollback không mặc nhiên đánh dấu T1 rollback-only.

**4. Inner fails, exception reaches outer:** T2 rollback, exception đi tiếp qua outer proxy nên T1 cũng rollback theo rollback rule của T1. `(0,0)` không có nghĩa T1/T2 dùng chung physical transaction; nguyên nhân là **cùng Java exception đã đi qua hai boundaries độc lập**.

**5. So sánh với REQUIRED:** Inner `REQUIRED` tham gia T1, `new=false` và connection giống outer. Inner ném unchecked exception, proxy inner yêu cầu T1 rollback-only. Outer catch và return bình thường nhưng khi outer proxy cố commit T1, Spring rollback và phát `UnexpectedRollbackException`. Đó là khác biệt quan trọng so với `REQUIRES_NEW`.

**6. Không có outer:** Gọi inner qua Spring proxy khi không có transaction ngoài. `REQUIRES_NEW` vẫn tạo transaction mới, nhưng không có T1 để suspend; kết quả `(0,1)`.

## 7. Giới hạn thực tế của việc suspend

### 7.1. Connection pool và khả năng bị kẹt

T1 có thể giữ C1 trong lúc T2 cần C2. Nếu có N request cùng mở T1, cùng chiếm N connection trong pool chỉ có N connection, **không thread nào lấy được connection mới cho T2**. Các request có thể chờ đến timeout; tổ hợp chờ tài nguyên này có thể dẫn đến pool starvation/deadlock-like failure. Hướng dẫn Spring khuyên pool khi dùng `REQUIRES_NEW` cần lớn hơn số concurrent outer threads **ít nhất một connection** trong tình huống đơn giản; nhiều mức lồng nhau và tải khác có thể cần nhiều hơn. Hãy đo active/idle/pending connections, thời gian giữ connection, mức concurrency thực tế.

Không khẳng định «mỗi request luôn cần đúng hai connections» ở mọi mô hình: điều này phụ thuộc lúc datasource lấy connection, connection pool, transaction manager và độ sâu của nested calls. Nhưng khi T1 **đã có connection**, T2 độc lập đòi hỏi transaction resource riêng trong kịch bản JDBC thông dụng.

### 7.2. T1 có thể giữ khóa trong khi T2 chạy

Suspend T1 tại Spring không giải phóng database row locks mà T1 đang giữ. Nếu T2 cố cập nhật **cùng row** với T1 (hoặc một row có ràng buộc phụ thuộc), T2 có thể bị block. Khi đó outer T1 đang đợi inner T2 kết thúc, còn inner lại đợi khóa do T1 giữ: rủi ro chờ khóa/timeout rất rõ.

Vì thế demo cập nhật hai hàng riêng, và không ép inner đọc một hàng vừa được outer insert chưa commit. T2 dùng transaction riêng nên dưới isolation thông dụng như `READ_COMMITTED`, nó **không tự nhìn thấy** các thay đổi chưa commit của T1. Với foreign key, unique constraint hoặc row locks, hậu quả phụ thuộc database và isolation.

### 7.3. Các thuộc tính isolation, timeout, read-only

Vì T2 là physical transaction riêng, inner có thể khai báo isolation/timeout/read-only riêng:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    readOnly = false
)
public void recordAudit() {
    // JDBC / repository work
}
```

Đây là **mã minh họa**, cần `Isolation` import và manager/database phù hợp. Các thuộc tính được áp dụng tùy transaction manager/driver. `readOnly` thường là một hint hoặc setting có mức enforcement tùy hạ tầng; không phải thay thế quyền ghi của database.

### 7.4. Chỉ quản lý tài nguyên tham gia đúng manager

`DataSourceTransactionManager` không thể rollback email, HTTP request, message đã phát đi hoặc transaction của database khác nếu những thao tác ấy không tham gia cùng cơ chế transaction. Nếu outer/inner dùng **manager khác nhau**, sự kiện «suspend» cần được hiểu với manager và resource thực tế. Với JTA, khả năng thực hiện suspension phụ thuộc runtime và sự tích hợp `JtaTransactionManager` tương ứng.

### 7.5. Không dùng REQUIRES_NEW tùy tiện cho outbox

Để gửi event **chỉ khi nghiệp vụ chính commit**, outbox record thường phải được insert trong **cùng transaction với dữ liệu nghiệp vụ chính**. Nếu outbox được insert bằng T2 `REQUIRES_NEW`, sau đó T1 rollback, event có thể tồn tại dù đơn hàng không có. Một audit về «cố thử thực hiện» có thể chủ ý dùng T2, nhưng phải định nghĩa rõ ý nghĩa dữ liệu, idempotency và retention.

## 8. Điều kiện để annotation thật sự có hiệu lực

### 8.1. Lời gọi phải đi qua proxy

Sai trong Spring AOP proxy mode phổ biến:

```java
@Service
class OrderService {
    @Transactional
    public void outer() {
        saveAudit(); // this.saveAudit(): self-invocation, không qua proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit() {
        // Không chắc đã có T2 vì call không đi qua interceptor của method này.
    }
}
```

Đây là **lớp minh họa**. Khi method inner được gọi bằng `this` trong cùng target, transaction interceptor của inner không chạy. Phần SQL của inner có thể vẫn dùng T1 do outer mở. Sửa bằng cách tách inner sang bean khác rồi inject/gọi proxy như demo, hoặc dùng `TransactionTemplate` cho một đoạn giao dịch mới trong cùng luồng xử lý.

Tương tự, `new AuditService(...)` trong application code không tự được tạo transaction proxy. Việc một class có `@Service` hoặc `@Transactional` không biến mọi instance thành Spring bean. Hãy lấy object qua `ApplicationContext`/constructor injection, và kiểm tra các điều kiện proxy của class/method (final/private/JDK interface proxy).

### 8.2. Đúng ApplicationContext và transaction manager

`@EnableTransactionManagement` trong chế độ proxy hoạt động theo `ApplicationContext` nơi nó được cấu hình. Bean service ở root context không tự được child `DispatcherServlet` context tạo proxy chỉ vì child có annotation infrastructure. Khi nhiều manager/datasource cùng tồn tại, cần xác định manager nào xử lý outer, inner và resource JDBC/JPA nào thực sự được enlist. Một lời gọi đã có proxy nhưng dùng connection lấy sai cách vẫn có thể cho hành vi khó hiểu.

### 8.3. Exception và rollback rules

Mặc định thông thường, `@Transactional` rollback khi `RuntimeException` hoặc `Error` thoát khỏi method được advice; checked exception có thể cần `rollbackFor` hoặc cấu hình default rollback policy phù hợp. Nếu inner **tự catch** exception và return bình thường, proxy có thể commit T2 nếu không có rollback-only. Nếu outer **catch sau khi T2 đã rollback** và quyết định tiếp tục, T1 có thể commit. Phân biệt vị trí catch rất quan trọng.

Không nuốt các lỗi critical để cố duy trì T1. Outer phải có lựa chọn nghiệp vụ rõ ràng: lỗi inner audit có thể bỏ qua hay phải làm thất bại cả request?

## 9. Cách mở T2 bằng mã với `TransactionTemplate`

Nếu cần transaction boundary rất cụ thể mà không muốn phụ thuộc vào self-invocation, có thể dùng transaction API lập trình:

```java
TransactionTemplate template =
    new TransactionTemplate(transactionManager);

template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);

template.executeWithoutResult(status -> {
    auditRepository.saveAttempt(...);
});
```

Đây là **mã minh họa**, giả định đã có `transactionManager` và `auditRepository`. Khi callback chạy trong T1 do **cùng manager** quản lý, template sẽ tạo T2 độc lập, suspend/resume T1 theo cơ chế transaction manager. Với checked/unchecked exception và callback cần kiểm tra rollback semantics tương ứng. Không dùng template như cách tự biến kết nối HTTP hoặc một datasource ngoài manager thành transactional.

Chọn `@Transactional(REQUIRES_NEW)` khi inner method là boundary service rõ ràng và được gọi qua proxy. Chọn template khi scope nằm trong một khối nhỏ, cần kiểm soát bằng mã, hoặc khi thiết kế class không phù hợp với proxy interception. Không cần kết hợp hai cơ chế trên cùng đoạn code nếu không có lý do rõ ràng.

## 10. Checklist chẩn đoán và bài tập

| Quan sát | Câu hỏi cần kiểm tra |
| --- | --- |
| `Inner REQUIRES_NEW` nhưng không thấy T2 | Caller có gọi bean proxy không, có self-invocation hoặc object `new` không? |
| Inner rollback và outer cũng rollback | Exception có lan ra ngoài outer không, outer có rollback-only riêng không? |
| Inner commit vẫn thấy dữ liệu mất | Có thực sự commit T2, hay inner đang dùng `REQUIRED`/cùng manager/config chưa đúng? |
| Inner không thấy row outer vừa ghi | Row ở T1 còn chưa commit; isolation/foreign key/lock ra sao? |
| Connection pool bị chờ | T1 giữ C1 trong khi T2 cần C2; pool có đủ connection và timeout phù hợp không? |
| Đã có Spring AOP proxy nhưng không rollback | Cần xem transaction advice, manager, datasource, exception rule và transaction boundary. |
| Test ra khác production | Test có transaction bao ngoài riêng do Spring Test không? |

**Bài tập:** (1) Đổi inner từ `REQUIRES_NEW` sang `REQUIRED` và so sánh case outer catch. (2) Thay inner bằng `NESTED` khi JDBC hỗ trợ savepoints rồi kiểm tra trường hợp inner commit nhưng outer rollback. (3) Cho outer và inner cố cập nhật cùng row trong database test với lock timeout nhỏ để thấy nguy cơ chờ; không làm trên dữ liệu thật. (4) Dùng connection pool kích thước nhỏ và chạy vài outer transactions đồng thời để quan sát pending connections. (5) Gọi inner trực tiếp khi không có outer để thấy `REQUIRES_NEW` vẫn bắt đầu transaction.

**Tổng kết:** `REQUIRES_NEW` **suspend transaction ngoài nếu có, tạo physical transaction mới cho inner, commit/rollback inner độc lập, rồi resume outer**. Tính độc lập ở tầng database không tự tách call stack, không giải phóng khóa của T1, không chặn mọi exception ảnh hưởng T1 và có chi phí connection thực sự. Hãy chọn nó theo **ý nghĩa nghiệp vụ của dữ liệu phải commit độc lập**, không theo cảm giác rằng «thêm transaction là an toàn hơn».

## 11. Tài liệu tham khảo

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html) — `REQUIRED`, `REQUIRES_NEW`, `NESTED`, independent physical transactions và lưu ý pool.
- [Spring Framework — `Propagation` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Propagation.html) — định nghĩa «create a new transaction, suspend current if exists».
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — attributes, rollback và proxy mode.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html) — `TransactionTemplate`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) — self-invocation và cách gọi qua proxy.
