# So sánh bảy propagation trên hai trạng thái đầu vào trong Spring Framework

## 1. Hai đầu vào quyết định hành vi propagation

Trong Spring Framework, `Propagation` là cách quy định **phương thức đang được gọi** nên làm gì với một transaction đã tồn tại. Có bảy lựa chọn: `REQUIRED`, `SUPPORTS`, `MANDATORY`, `REQUIRES_NEW`, `NOT_SUPPORTED`, `NEVER` và `NESTED`.

Để so sánh chính xác, luôn xét **hai trạng thái trước khi đi qua transaction interceptor**:

- **A — CHƯA có actual transaction:** caller chưa tham gia một giao dịch vật lý do transaction manager tương ứng quản lý.
- **B — ĐÃ có actual transaction:** caller đã có transaction đang hoạt động; ví dụ một phương thức service bên ngoài được khai báo `@Transactional(REQUIRED)`.

“Đang có transaction” không đồng nghĩa chỉ có annotation trên source code hoặc `TransactionSynchronizationManager.isSynchronizationActive() == true`: synchronization có thể bật trong một empty transaction scope mà không mở giao dịch DB thực sự.

Bài này giúp dự đoán đủ **14 tổ hợp (7 propagation × 2 đầu vào)**, phân biệt logical/physical transaction, suspend/resume, savepoint, rollback-only, chi phí connection pool và các lỗi phổ biến. Ví dụ chạy với Java 17+, Spring Framework, JDBC và H2.

## 2. Ma trận 7 propagation × 2 trạng thái đầu vào

| Propagation | **A — CHƯA có transaction** | **B — ĐÃ có transaction ngoài** |
| --- | --- | --- |
| `REQUIRED` *(mặc định)* | Tạo một **physical transaction mới**. | **Tham gia transaction ngoài**; không mở physical transaction riêng. |
| `SUPPORTS` | Chạy **không có actual transaction**; có thể có synchronization scope. | **Tham gia transaction ngoài**. |
| `MANDATORY` | **Ném `IllegalTransactionStateException`** trước khi vào method body. | **Tham gia transaction ngoài**. |
| `REQUIRES_NEW` | Tạo **transaction mới**. | **Suspend outer**, tạo **physical transaction độc lập**, hoàn tất rồi resume outer. |
| `NOT_SUPPORTED` | Chạy **ngoài transaction**. | **Suspend outer**, chạy ngoài transaction, rồi resume outer. |
| `NEVER` | Chạy **ngoài transaction**. | **Ném `IllegalTransactionStateException`**, không tự suspend. |
| `NESTED` | Hoạt động như `REQUIRED`: **tạo transaction mới**. | **Savepoint trong cùng physical transaction**, nếu manager và driver hỗ trợ; không hỗ trợ có thể báo lỗi. |

Đây là bảng hành vi của **Spring transaction advice khi lời gọi thực sự đi qua proxy**. Nó không phải lời bảo đảm mọi transaction manager đều hỗ trợ savepoint, suspend hoặc mọi phương thức Java đều được intercept.

### Mẹo ghi nhớ

~~~text
A. CHƯA CÓ TRANSACTION:
REQUIRED      -> NEW
SUPPORTS      -> NO ACTUAL TRANSACTION
MANDATORY     -> ERROR
REQUIRES_NEW  -> NEW
NOT_SUPPORTED -> NO ACTUAL TRANSACTION
NEVER         -> NO ACTUAL TRANSACTION
NESTED        -> NEW (như REQUIRED)

B. ĐÃ CÓ TRANSACTION:
REQUIRED      -> JOIN
SUPPORTS      -> JOIN
MANDATORY     -> JOIN
REQUIRES_NEW  -> SUSPEND; NEW INDEPENDENT TX; RESUME
NOT_SUPPORTED -> SUSPEND; NO ACTUAL TX; RESUME
NEVER         -> ERROR
NESTED        -> SAVEPOINT (nếu được hỗ trợ)
~~~

## 3. Logical scope và physical transaction khác nhau thế nào?

**Logical transaction scope** là phạm vi transaction được khai báo trên một phương thức. **Physical transaction** là transaction thực trên connection/tài nguyên dữ liệu, có commit hoặc rollback cuối cùng.

Khi **inner REQUIRED** được gọi từ outer REQUIRED:

~~~text
Outer @Transactional(REQUIRED)      [logical OUTER]
  |
  '-- Inner @Transactional(REQUIRED) [logical INNER]
               |
               '-- CÙNG physical transaction TX-A

Sau cùng: TX-A COMMIT hoặc ROLLBACK một lần.
~~~

Inner kết thúc bình thường chưa có nghĩa TX-A đã commit. Nếu inner bị đánh dấu rollback-only, outer dù catch exception và muốn commit vẫn có thể nhận `UnexpectedRollbackException`.

Với **inner REQUIRES_NEW**, Spring phân biệt hai physical transactions:

~~~text
Outer TX-A đang hoạt động
  |
  +-- SUSPEND TX-A (giữ tài nguyên outer)
  +-- BEGIN TX-B cho @Transactional(REQUIRES_NEW)
  +-- COMMIT/ROLLBACK TX-B độc lập
  +-- RESUME TX-A
  |
  '-- TX-A tiếp tục rồi COMMIT/ROLLBACK sau
~~~

Nếu TX-B commit rồi TX-A rollback, dữ liệu TX-B vẫn có thể tồn tại. TX-B rollback không tự chuyển trạng thái rollback-only sang TX-A, dù exception từ TX-B **thoát khỏi outer method** có thể khiến outer interceptor chọn rollback.

Với **inner NESTED** trên JDBC savepoint:

~~~text
Outer physical TX-A
  UPDATE A
  SAVEPOINT S1
  inner UPDATE B
  nếu inner lỗi: ROLLBACK TO S1
  outer UPDATE C
TX-A COMMIT hoặc ROLLBACK cuối cùng
~~~

`NESTED` không có transaction vật lý mới. Outer rollback thì **A, B, C đều có thể bị hoàn tác**, kể cả inner đã hoàn tất thành công.

## 4. REQUIRED, SUPPORTS, MANDATORY — nhóm có thể tham gia transaction

### `REQUIRED` — tạo nếu thiếu, tham gia nếu có

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void saveOrder() {
    // Ghi những thay đổi cần nằm trong một transaction.
}
~~~

Ở đầu vào A, `REQUIRED` mở transaction và khi method qua proxy kết thúc bình thường, transaction interceptor sẽ cố commit. Ở đầu vào B, nó **không** tạo physical transaction mới, mà chia sẻ outer transaction. Đây là lựa chọn mặc định cho use case nghiệp vụ cần atomicity.

Điều dễ quên: `REQUIRED` inner tham gia outer có thể quyết định rollback-only khi gặp unchecked exception. Inner có annotation `isolation`, `timeout` hoặc `readOnly` riêng **không tự chỉnh lại** physical transaction đã được mở bởi outer; có cấu hình manager để từ chối mismatch.

### `SUPPORTS` — theo transaction nếu đang có

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public Report readReport() {
    // Có transaction thì tham gia; không có thì vẫn chạy.
}
~~~

Ở đầu vào A, `SUPPORTS` **không mở actual transaction**. Trên manager sử dụng `SYNCHRONIZATION_ALWAYS`, synchronization scope vẫn có thể active để phối hợp resource. SQL ở JDBC connection auto-commit có thể commit ngay, nên không dùng SUPPORTS khi yêu cầu nhiều SQL phải rollback cùng nhau.

Ở đầu vào B, SUPPORTS **tham gia transaction ngoài**. Cùng một phương thức có thể đọc trong transaction hoặc ngoài transaction tùy caller; cần đánh giá consistency và locking thực tế.

### `MANDATORY` — bắt buộc đã có transaction

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public void writeAsPartOfExistingUseCase() {
    // Caller phải mở transaction trước.
}
~~~

A → `IllegalTransactionStateException`, method body không được gọi. B → join outer. Khác `REQUIRED`, `MANDATORY` **không tự chữa thiếu transaction**. Nó có ích cho một contract mạnh: helper này chỉ được gọi từ use case đã có transaction.

Các đoạn Java trong mục này là **ví dụ thuộc tính** đặt trong Spring-managed service, chưa phải chương trình hoàn chỉnh; demo chạy đầy đủ ở mục 8.

## 5. REQUIRES_NEW, NOT_SUPPORTED — nhóm thay đổi ranh giới outer

### `REQUIRES_NEW` — transaction vật lý độc lập

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAuditAttempt() {
    // Audit có thể commit ngay cả khi business outer rollback.
}
~~~

A → tạo transaction mới. B → suspend outer, tạo **transaction vật lý khác**, kết thúc inner rồi resume outer. Inner có thể chọn isolation/timeout/read-only riêng; inner rollback không tự rollback outer.

**Giá phải trả:** với JDBC, outer thường giữ Connection A, còn inner cần Connection B. Nếu nhiều requests đều giữ outer connection và chờ inner, pool nhỏ có thể bị cạn hoặc deadlock khi cấp connection. Spring khuyến nghị pool đủ lớn so với số luồng đồng thời. Inner cũng không tự thấy row chưa commit của outer.

`REQUIRES_NEW` phù hợp cho **nhật ký attempt độc lập**, nhưng không nên phát event “đơn hàng đã commit” trong inner trước khi biết kết quả commit của outer.

### `NOT_SUPPORTED` — chạy ngoài transaction

~~~java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void executeOutsideTransaction() {
    // Không tham gia transaction đang có của caller.
}
~~~

A → chạy không có actual transaction. B → suspend outer, chạy không có actual transaction, rồi resume outer.

**Khác nhau:** `REQUIRES_NEW` có transaction mới với commit/rollback; `NOT_SUPPORTED` **không có physical transaction của inner**. Nếu inner dùng JDBC auto-commit, các câu SQL có thể tồn tại dù outer rollback sau đó.

## 6. NEVER và MANDATORY — hai hợp đồng trái ngược

| Propagation | Điều kiện bắt buộc ở caller | Trường hợp vi phạm |
| --- | --- | --- |
| `MANDATORY` | Phải **có** actual transaction | Không có → exception |
| `NEVER` | Phải **không có** actual transaction | Có → exception |

~~~java
@Transactional(propagation = Propagation.NEVER)
public void mustRunWithoutTransaction() {
    // Chạy ngoài transaction; nếu caller có transaction thì báo lỗi.
}
~~~

A → chạy không có transaction. B → ném `IllegalTransactionStateException` trước khi target thực thi. `NEVER` **không tự suspend** như `NOT_SUPPORTED`.

Một outer transactional method có thể catch exception do `NEVER` vi phạm. Nếu exception được bắt ở bên trong outer, không nên tự động kết luận transaction ngoài đã bị đánh dấu rollback-only chỉ vì method NEVER không được gọi. Xét rollback rule tại outer boundary và các lỗi khác.

## 7. NESTED — một tên nhưng hai cách thực thi theo đầu vào

~~~java
@Transactional(propagation = Propagation.NESTED)
public void saveOptionalStep() {
    // Có outer -> savepoint; không outer -> tạo transaction mới.
}
~~~

**Đầu vào A:** `NESTED` hoạt động giống `REQUIRED`: tạo một transaction mới; không có outer nên không có nested savepoint.

**Đầu vào B:** với manager hỗ trợ, Spring tạo **savepoint trong cùng physical transaction**. Inner rollback sẽ hoàn tác phần sau savepoint, outer có thể bắt lỗi rồi tiếp tục commit phần còn lại.

Giới hạn hỗ trợ phải ghi nhớ:

- `DataSourceTransactionManager`/`JdbcTransactionManager` cùng driver JDBC hỗ trợ savepoints là trường hợp phù hợp. Demo bật `nestedTransactionAllowed=true`.
- `JpaTransactionManager` có hạn chế liên quan persistence context; không giả định mọi thao tác entity rollback đúng như JDBC savepoint.
- Một số JTA/transaction managers không hỗ trợ nested, có thể ném `NestedTransactionNotSupportedException` hoặc lỗi khác.
- Outer rollback cuối cùng sẽ làm mất cả thay đổi nested đã hoàn tất bình thường; `NESTED` **không phải** `REQUIRES_NEW`.

Đừng thay `NESTED` bằng `REQUIRES_NEW` chỉ để làm hết exception: chúng có semantics commit/rollback và tài nguyên khác nhau.

## 8. Ví dụ chạy được: đủ 14 trường hợp và savepoint rollback

Môi trường: **Java 17+, Spring Framework 6.2.5, Spring JDBC, H2 2.2.224, Maven**. Không dùng Spring Boot. Lời gọi của inner đi qua Spring bean proxy, không dùng self-invocation.

Ba trường in ra ở trong mỗi method:

- `actual`: `TransactionSynchronizationManager.isActualTransactionActive()`.
- `hasTx`: `TransactionAspectSupport.currentTransactionStatus().hasTransaction()`.
- `savepoint`: `TransactionAspectSupport.currentTransactionStatus().hasSavepoint()`.

Các boolean này mô tả **trạng thái hiện tại**, không xác nhận đã commit. `REQUIRED` join outer và `REQUIRES_NEW` mở transaction độc lập đều có thể in `actual=true`. Muốn phân biệt hai physical transactions, phải đọc đúng propagation và boundary.

### 8.1. Cấu trúc

~~~text
spring-propagation-matrix/
  pom.xml
  src/main/java/demo/PropagationMatrixDemo.java
~~~

### 8.2. Tạo `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-propagation-matrix</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
            <scope>runtime</scope>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. Tạo `src/main/java/demo/PropagationMatrixDemo.java`

~~~java
package demo;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class PropagationMatrixDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            InnerSteps inner = context.getBean(InnerSteps.class);
            OuterSteps outer = context.getBean(OuterSteps.class);

            jdbc.execute("CREATE TABLE marker (id INT PRIMARY KEY, note VARCHAR(40))");

            System.out.println("=== WITHOUT OUTER TRANSACTION ===");
            callAll("NONE", inner);

            System.out.println("=== WITH OUTER TRANSACTION ===");
            outer.callAllInsideTransaction();

            outer.testNestedSavepoint();
            List<Integer> ids = jdbc.queryForList(
                    "SELECT id FROM marker ORDER BY id", Integer.class);
            System.out.println("AFTER_NESTED_IDS=" + ids);
        }
    }

    static void callAll(String input, InnerSteps inner) {
        run(input, "REQUIRED", () -> inner.required(input));
        run(input, "SUPPORTS", () -> inner.supports(input));
        run(input, "MANDATORY", () -> inner.mandatory(input));
        run(input, "REQUIRES_NEW", () -> inner.requiresNew(input));
        run(input, "NOT_SUPPORTED", () -> inner.notSupported(input));
        run(input, "NEVER", () -> inner.never(input));
        run(input, "NESTED", () -> inner.nested(input));
    }

    private static void run(String input, String name, Runnable action) {
        try {
            action.run();
        } catch (IllegalTransactionStateException ex) {
            System.out.println(input + "/" + name
                    + " ERROR=IllegalTransactionStateException");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            var ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:propagation_matrix;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            var tm = new JdbcTransactionManager(ds);
            tm.setNestedTransactionAllowed(true);
            tm.setTransactionSynchronization(
                    AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS);
            return tm;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public InnerSteps innerSteps(JdbcTemplate jdbc) {
            return new InnerSteps(jdbc);
        }

        @Bean
        public OuterSteps outerSteps(InnerSteps inner, JdbcTemplate jdbc) {
            return new OuterSteps(inner, jdbc);
        }
    }

    public static class InnerSteps {
        private final JdbcTemplate jdbc;

        public InnerSteps(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private void show(String input, String propagation) {
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();
            System.out.printf("%s/%s actual=%s hasTx=%s savepoint=%s%n",
                    input, propagation,
                    TransactionSynchronizationManager.isActualTransactionActive(),
                    status.hasTransaction(),
                    status.hasSavepoint());
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void required(String input) {
            show(input, "REQUIRED");
        }

        @Transactional(propagation = Propagation.SUPPORTS)
        public void supports(String input) {
            show(input, "SUPPORTS");
        }

        @Transactional(propagation = Propagation.MANDATORY)
        public void mandatory(String input) {
            show(input, "MANDATORY");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNew(String input) {
            show(input, "REQUIRES_NEW");
        }

        @Transactional(propagation = Propagation.NOT_SUPPORTED)
        public void notSupported(String input) {
            show(input, "NOT_SUPPORTED");
        }

        @Transactional(propagation = Propagation.NEVER)
        public void never(String input) {
            show(input, "NEVER");
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nested(String input) {
            show(input, "NESTED");
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nestedWriteAndFail() {
            jdbc.update("INSERT INTO marker (id, note) VALUES (?, ?)",
                    11, "nested-to-rollback");
            throw new IllegalStateException("nested failed");
        }
    }

    public static class OuterSteps {
        private final InnerSteps inner;
        private final JdbcTemplate jdbc;

        public OuterSteps(InnerSteps inner, JdbcTemplate jdbc) {
            this.inner = inner;
            this.jdbc = jdbc;
        }

        @Transactional
        public void callAllInsideTransaction() {
            PropagationMatrixDemo.callAll("EXISTING", inner);
        }

        @Transactional
        public void testNestedSavepoint() {
            jdbc.update("INSERT INTO marker (id, note) VALUES (?, ?)",
                    10, "outer-before");
            try {
                inner.nestedWriteAndFail();
            } catch (IllegalStateException ex) {
                System.out.println("NESTED_FAILURE=" + ex.getMessage());
            }
            jdbc.update("INSERT INTO marker (id, note) VALUES (?, ?)",
                    12, "outer-after");
        }
    }
}
~~~

Spring tạo `InnerSteps` và `OuterSteps` qua `@Bean`. `main` lấy các service từ context; outer gọi **bean inner riêng** nên transaction proxy xử lý propagation. `@EnableTransactionManagement` bật hạ tầng annotation. JDBC manager được cấu hình cho phép nested savepoint.

### 8.4. Lệnh chạy và stdout

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.PropagationMatrixDemo
~~~

Các dòng `System.out` của chương trình (bỏ qua log Maven/Spring):

~~~text
=== WITHOUT OUTER TRANSACTION ===
NONE/REQUIRED actual=true hasTx=true savepoint=false
NONE/SUPPORTS actual=false hasTx=false savepoint=false
NONE/MANDATORY ERROR=IllegalTransactionStateException
NONE/REQUIRES_NEW actual=true hasTx=true savepoint=false
NONE/NOT_SUPPORTED actual=false hasTx=false savepoint=false
NONE/NEVER actual=false hasTx=false savepoint=false
NONE/NESTED actual=true hasTx=true savepoint=false
=== WITH OUTER TRANSACTION ===
EXISTING/REQUIRED actual=true hasTx=true savepoint=false
EXISTING/SUPPORTS actual=true hasTx=true savepoint=false
EXISTING/MANDATORY actual=true hasTx=true savepoint=false
EXISTING/REQUIRES_NEW actual=true hasTx=true savepoint=false
EXISTING/NOT_SUPPORTED actual=false hasTx=false savepoint=false
EXISTING/NEVER ERROR=IllegalTransactionStateException
EXISTING/NESTED actual=true hasTx=true savepoint=true
NESTED_FAILURE=nested failed
AFTER_NESTED_IDS=[10, 12]
~~~

**Diễn giải:**

1. `NONE`: REQUIRED/REQUIRES_NEW/NESTED mở transaction; MANDATORY báo lỗi; SUPPORTS/NOT_SUPPORTED/NEVER chạy không có actual transaction.
2. `EXISTING`: REQUIRED/SUPPORTS/MANDATORY tham gia; REQUIRES_NEW mở transaction độc lập nhưng vẫn in `actual=true`; NOT_SUPPORTED suspend outer nên `actual=false`; NEVER báo lỗi.
3. NESTED không có outer là transaction mới, `savepoint=false`; có outer là savepoint, `savepoint=true`.
4. Ca test cuối tạo row 10 trước savepoint, row 11 trong nested rồi ném lỗi, row 12 sau khi outer bắt lỗi. Nested rollback về savepoint xóa row 11, outer commit row 10 và row 12. Vì vậy `AFTER_NESTED_IDS=[10, 12]`.

Kết quả là **mong đợi trên cấu hình Java 17/Spring 6.2.5/H2**. Transaction manager khác hoặc driver không hỗ trợ savepoint có thể cho lỗi; không mặc định chép nguyên output cho mọi stack JPA/JTA.

## 9. Cách xử lý exception và rollback

Bảng ma trận cho biết **scope được thiết lập thế nào**. Nếu inner ném `RuntimeException` trong đầu vào B, kết quả phụ thuộc propagation:

| Inner propagation khi có outer | Khi outer bắt exception | Hệ quả cần nhớ |
| --- | --- | --- |
| `REQUIRED` | Inner interceptor có thể đánh dấu shared TX rollback-only | Outer có thể gặp `UnexpectedRollbackException` khi commit. |
| `SUPPORTS` | Vì tham gia outer, rollback rules có thể ảnh hưởng shared TX | Không còn là non-transactional. |
| `MANDATORY` | Tham gia outer; rollback rules áp dụng theo transaction hiện có | Không commit độc lập. |
| `REQUIRES_NEW` | Inner rollback độc lập, outer có thể tiếp tục nếu được phép | Inner rollback-only không tự chuyển sang outer. |
| `NOT_SUPPORTED` | Không có inner physical transaction để rollback | SQL auto-commit có thể không bị hoàn tác. |
| `NEVER` | Lỗi kiểm tra propagation có thể được outer bắt | Method body của NEVER không chạy. |
| `NESTED` | Inner rollback về savepoint, outer có thể tiếp tục | Cần manager hỗ trợ savepoint. |

Nếu exception bị bắt **ngay bên trong method annotated** và không ném tiếp, interceptor thường không biết exception để tự rollback. Mặc định `RuntimeException`/`Error` làm Spring rollback; checked exception thường không, trừ khi `rollbackFor` hoặc global rollback rules thay đổi.

Một inner `REQUIRED` kết thúc thành công không đồng nghĩa commit xong. `NESTED` release savepoint cũng không đồng nghĩa physical commit. Ngay cả sau khi method target return, transaction interceptor còn có thể gặp lỗi khi flush/commit.

## 10. Pool, locking, visibility và manager support

**REQUIRES_NEW:** outer vẫn có thể giữ JDBC connection/locks trong khi inner cần connection mới. Pool cạn khi nhiều threads đồng thời giữ connection outer và cùng chờ inner; hãy sizing pool theo concurrency/nested depth và cấu hình timeout. Inner không tự nhìn thấy row mà outer mới ghi nhưng chưa commit, và inner cố chạm row đang bị outer khóa có thể block/deadlock.

**NOT_SUPPORTED:** không có inner transaction; outer bị suspend không có nghĩa locks của outer bị giải phóng. Inner có thể dùng connection khác để chạy SQL auto-commit. Outer rollback sau đó không hoàn tác được các thay đổi inner đã commit.

**NESTED:** JDBC savepoint dùng cùng physical transaction, thường cùng connection. Không tạo transaction độc lập mới; outer rollback cuối vẫn hoàn tác nested.

**Manager thực tế:** `JdbcTransactionManager` và H2 trong demo hỗ trợ JDBC savepoint. `JpaTransactionManager` và `JtaTransactionManager` có hạn chế/tùy chọn khác về nested/suspend; một số tổ hợp có thể ném exception. Nếu nhiều transaction managers thì “có transaction” cần xét theo manager/tài nguyên được chọn, không suy luận từ một flag thread-local chung.

## 11. Những lỗi thường gặp

| Sai lầm | Giải thích / cách xử lý |
| --- | --- |
| Nghĩ `REQUIRED` luôn mở mới | Có outer thì tham gia, không commit riêng. |
| Dùng `SUPPORTS` cho nhiều SQL đòi rollback đồng bộ | Không có outer thì không mở actual transaction. |
| Tưởng `MANDATORY` tự tạo transaction khi thiếu | Nó ném `IllegalTransactionStateException`. |
| Tưởng `NEVER` tự suspend | Nó báo lỗi khi có transaction; `NOT_SUPPORTED` mới suspend. |
| Dùng `REQUIRES_NEW` thay `NESTED` mà không hiểu khác biệt | Một cái physical tx riêng, một cái savepoint chung physical tx. |
| Bắt unchecked exception rồi nghĩ chắc commit outer `REQUIRED` | Shared tx có thể đã bị đánh dấu rollback-only. |
| Quên connection pool khi dùng `REQUIRES_NEW` | Inner có thể cần thêm connection khi outer còn giữ một connection. |
| Gọi `this.inner()` mà mong `@Transactional` inner có hiệu lực | Self-invocation không qua proxy mode. Tách bean hoặc dùng `TransactionTemplate`. |
| Đánh đồng synchronization active với actual transaction active | Empty `SUPPORTS` có thể bật synchronization mà không tạo physical tx. |
| Đọc trạng thái trong method rồi nói commit đã thành công | Phải quan sát sau outer boundary hoặc qua transaction callback phù hợp. |

### Vấn đề proxy: ví dụ KHÔNG đúng

~~~java
@Service
class WrongService {
    @Transactional
    public void outer() {
        inner(); // this.inner(), không qua transaction proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Không tự động có boundary REQUIRES_NEW ở lời gọi nội bộ trên.
    }
}
~~~

Đây là **mã minh họa anti-pattern**, không phải source độc lập. Trong proxy mode mặc định, muốn propagation được áp thì gọi thông qua Spring proxy, chẳng hạn một service bean khác như demo.

## 12. Checklist chọn propagation

- Muốn **tạo transaction nếu chưa có** và **tham gia nếu đã có** → `REQUIRED`.
- Muốn có thể chạy **bên trong hoặc ngoài** transaction, không tự mở transaction mới → `SUPPORTS`.
- Muốn **bắt buộc caller đã mở transaction** → `MANDATORY`.
- Muốn **transaction độc lập** để commit/rollback riêng → `REQUIRES_NEW`; cân nhắc pool và atomicity.
- Muốn **tạm treo transaction ngoài để chạy non-transactional** → `NOT_SUPPORTED`.
- Muốn **báo lỗi khi caller đang có transaction** → `NEVER`.
- Muốn **savepoint rollback một phần trong cùng transaction ngoài** → `NESTED`, khi manager hỗ trợ.

Không có một lựa chọn tối ưu cho mọi hệ thống. Đặt propagation theo ý nghĩa commit/rollback mong muốn, kiểm tra khả năng của manager, sau đó viết integration test chứng minh trạng thái DB sau khi transaction **thực sự kết thúc**.

## 13. Bài tập tự kiểm tra

**Câu 1.** Không có outer, gọi `MANDATORY`. Kết quả?

**Đáp án:** Báo `IllegalTransactionStateException` trước khi body chạy.

**Câu 2.** Có outer, gọi `NEVER`. Spring suspend outer rồi chạy body?

**Đáp án:** Không. `NEVER` từ chối; `NOT_SUPPORTED` mới suspend rồi chạy ngoài transaction.

**Câu 3.** Không có outer, gọi `NESTED` trên JDBC manager hỗ trợ. Nó dùng savepoint lồng?

**Đáp án:** Không cần; nó tạo physical transaction mới như `REQUIRED`.

**Câu 4.** Có outer, inner `REQUIRES_NEW` commit audit, outer rollback sau đó. Audit có thể vẫn tồn tại?

**Đáp án:** Có. Inner là physical transaction riêng, không bị outer rollback hoàn tác tự động.

**Câu 5.** Inner `NESTED` ghi B rồi ném unchecked exception, outer catch và commit A. Có thể A còn và B mất?

**Đáp án:** Có khi savepoint được hỗ trợ. Ví dụ H2 giữ ID 10, 12 và hoàn tác 11.

**Câu 6.** Inner `REQUIRED` báo rollback-only, outer catch exception rồi return. Outer chắc chắn commit?

**Đáp án:** Không; có thể gặp `UnexpectedRollbackException` ở commit cuối.

**Câu 7.** `SUPPORTS` không có outer nhưng `isSynchronizationActive()` true. Có actual transaction?

**Đáp án:** Không nhất thiết. Synchronization scope không phải physical transaction.

**Câu 8.** `NOT_SUPPORTED` ghi dữ liệu auto-commit trong lúc outer đang suspend, rồi outer rollback. Dữ liệu inner có mất?

**Đáp án:** Không nhất thiết; SQL đã auto-commit có thể vẫn tồn tại.

**Câu 9.** Khi chưa có transaction, `REQUIRED` và `REQUIRES_NEW` đều mở mới. Khi có outer chúng giống nhau không?

**Đáp án:** Không. REQUIRED join, REQUIRES_NEW mở physical transaction mới độc lập.

## Ghi nhớ

**Đầu vào A:** `REQUIRED`, `REQUIRES_NEW` và `NESTED` mở transaction; `SUPPORTS`, `NOT_SUPPORTED` và `NEVER` chạy không có actual transaction; `MANDATORY` báo lỗi.

**Đầu vào B:** `REQUIRED`, `SUPPORTS` và `MANDATORY` tham gia; `REQUIRES_NEW` suspend + transaction độc lập; `NOT_SUPPORTED` suspend + chạy ngoài; `NEVER` báo lỗi; `NESTED` dùng savepoint khi hỗ trợ.

**Mấu chốt:** physical transaction khác logical scope. Cần Spring proxy, transaction manager đúng, driver hỗ trợ và kiểm thử commit/rollback cuối; annotation hay `isActualTransactionActive()==true` không tự bảo đảm transaction đã commit.

## Tài liệu tham khảo chính thức

1. Spring Framework — [`Propagation` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/transaction/annotation/Propagation.html): định nghĩa bảy giá trị.
2. Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): physical/logical transaction, REQUIRED/REQUIRES_NEW/NESTED.
3. Spring Framework — [`TransactionDefinition` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/transaction/TransactionDefinition.html): transaction semantics.
4. Spring Framework — [`AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): policies và savepoint.
5. Spring Framework — [`DataSourceTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): JDBC nested support.
6. Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy và self-invocation.
