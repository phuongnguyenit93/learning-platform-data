# Phân biệt NESTED với REQUIRES_NEW trong Spring transaction management

## 1. Bài toán: rollback một phần hay commit độc lập?

Khi một service đã ở trong transaction và gọi một service con, có lúc ta muốn **hủy riêng bước con nhưng vẫn tiếp tục công việc của service cha**. Cũng có lúc ta muốn **bước con được commit thực sự, ngay cả khi service cha sau đó thất bại**. Hai yêu cầu tưởng gần nhau nhưng dẫn tới hai propagation khác nhau của Spring:

- **PROPAGATION_NESTED:** tạo một **savepoint trong cùng physical transaction** của caller, để có thể rollback một đoạn đã thực hiện; commit cuối cùng vẫn phụ thuộc giao dịch ngoài.
- **PROPAGATION_REQUIRES_NEW:** tạm đình chỉ transaction ngoài và bắt đầu một **physical transaction độc lập**, có thể commit hoặc rollback riêng.

Điểm khác biệt quyết định không nằm ở số lượng method có @Transactional, mà ở **số giao dịch vật lý**, **số JDBC Connection được sử dụng**, **thời điểm dữ liệu thật sự commit** và **khả năng outer rollback ảnh hưởng đến inner**.

Bài học này nằm trong phần **NESTED và savepoint** của Spring Framework transaction management. Nội dung tập trung so sánh NESTED với REQUIRES_NEW và hướng dẫn chọn đúng trong ứng dụng JDBC/JPA. Phần thực hành Java 17+ dùng Spring JDBC và H2 minh họa bốn kịch bản rollback/commit có thể kiểm tra trực tiếp.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **logical transaction scope** và **physical transaction** khi gọi method lồng nhau.
2. Mô tả chính xác NESTED dùng **JDBC Savepoint** như thế nào.
3. Giải thích vì sao REQUIRES_NEW cần **transaction độc lập và thường cần Connection khác**.
4. Dự đoán dữ liệu còn lại khi **inner lỗi**, **outer lỗi**, **inner commit** hoặc **outer commit**.
5. Nhận diện giới hạn hỗ trợ của **transaction manager/driver/DBMS**, nhất là với JPA.
6. Tránh lỗi **self-invocation**, cạn pool, tranh chấp khóa và hiểu nhầm “commit inner”.
7. Viết integration test kiểm chứng các tình huống, không suy diễn từ annotation đơn lẻ.

## 2. Từ REQUIRED đến hai kiểu propagation lồng nhau

Mặc định, @Transactional sử dụng **Propagation.REQUIRED**. Khi outer transaction đã tồn tại, một method REQUIRED bên trong **tham gia cùng physical transaction**. Nếu inner logic đánh dấu transaction rollback-only, việc outer bắt lỗi rồi cố commit có thể gây **UnexpectedRollbackException**, vì toàn bộ physical transaction phải rollback.

NESTED và REQUIRES_NEW đều có thể làm kết quả khác đi, nhưng bằng **hai cơ chế hoàn toàn khác**:

~~~text
REQUIRED (tham gia):
    outer T1 begin ----------------------- outer T1 commit/rollback
        inner REQUIRED -> dùng cùng T1; không có savepoint tự động
        inner yêu cầu rollback-only -> T1 không thể commit

NESTED (savepoint):
    outer T1 begin ----------------------- outer T1 commit/rollback
        SAVEPOINT S1
        inner NESTED -> cùng T1, cùng Connection
        inner thất bại -> ROLLBACK TO S1
        outer có thể tiếp tục; nếu outer rollback, cả T1 mất

REQUIRES_NEW (giao dịch mới):
    outer T1 begin -- suspend ---------- resume -- outer commit/rollback
                     inner T2 begin
                     inner T2 commit/rollback
        T1 và T2 độc lập về quyết định commit cuối
~~~

**Physical transaction** là transaction mà JDBC Connection/DBMS đang thực thi commit/rollback. **Logical scope** là phạm vi cấu hình của một lời gọi method được Spring intercept. NESTED có thêm savepoint, còn REQUIRES_NEW có thêm physical transaction thực sự.

### Bảng khác biệt cốt lõi

| Tiêu chí | NESTED | REQUIRES_NEW |
| --- | --- | --- |
| Khi outer transaction đã tồn tại | Tham gia **cùng physical transaction** nhưng tạo savepoint | Suspend transaction ngoài; tạo **physical transaction mới** |
| JDBC Connection | Thông thường **cùng Connection** với outer | Thường dùng **Connection khác** khi outer giữ connection |
| Cách rollback inner | Rollback về **savepoint** | Rollback **transaction inner** độc lập |
| Inner thành công | Không có independent commit; thay đổi chờ outer commit | Có thể **commit độc lập ngay khi inner hoàn tất** |
| Outer rollback sau inner thành công | **Hủy cả thay đổi của inner** | Không hủy thay đổi inner **đã commit** |
| Outer commit sau inner rollback, lỗi đã xử lý | Có thể giữ phần outer còn hợp lệ | Có thể giữ phần outer, còn inner đã rollback riêng |
| Isolation/timeout/read-only cấp physical transaction | Thường đi theo transaction ngoài vì không mở physical transaction khác | Có thể cấu hình policy độc lập cho transaction mới |
| Resource/pool | Savepoint trên connection hiện có; thường không mượn thêm connection | Có thể cần thêm connection, dễ làm pool cạn nếu thiết kế kém |
| Điều kiện hỗ trợ | Manager + JDBC driver + DBMS hỗ trợ savepoint | Manager hỗ trợ suspend/resume và mở transaction mới phù hợp |
| Thường dùng | Thử một nhánh DB phụ; rollback một phần nhưng vẫn **cùng commit cuối** | Audit/ghi trạng thái phải commit **tách biệt** khi outer thất bại |
| Mức nhất quán | Phần nested vẫn thuộc all-or-nothing của outer | Inner commit có thể tồn tại dù outer không commit |

**Ghi nhớ một câu:** NESTED là **rollback một phần trong cùng transaction**; REQUIRES_NEW là **transaction riêng có quyền commit riêng**.

## 3. NESTED vận hành với JDBC Savepoint

### 3.1. Savepoint là gì?

JDBC có các API trong java.sql.Connection:

~~~java
// Chỉ minh họa JDBC API, không phải code dùng trong Spring-managed transaction.
Savepoint point = connection.setSavepoint("before_optional_step");
try {
    performOptionalSql(connection);
} catch (SQLException ex) {
    connection.rollback(point);
}
connection.releaseSavepoint(point);
~~~

Mã minh họa cần Connection, performOptionalSql và xử lý transaction hoàn chỉnh mới chạy được. Trong Spring, **không tự thao tác savepoint trên Connection đang được transaction manager quản lý** trừ khi bạn có lý do và biết cách phối hợp; để @Transactional(propagation=NESTED) hoặc TransactionStatus API xử lý theo hợp đồng của manager.

Savepoint giống một **điểm đánh dấu** trong transaction vật lý đang mở:

~~~text
BEGIN T1
    UPDATE account_A                       (thay đổi thuộc T1)
    SAVEPOINT S1
        UPDATE account_B                   (thay đổi sau S1)
        lỗi xảy ra
    ROLLBACK TO SAVEPOINT S1               (hủy thay đổi account_B)
    UPDATE account_C                       (tiếp tục trong T1)
COMMIT T1                                  (chỉ A và C được lưu)
~~~

Nếu thay COMMIT T1 bằng **ROLLBACK T1**, cả A và C cũng bị hủy. Savepoint **không phải một transaction đã commit riêng** và không làm inner thay đổi trở nên bền vững trước khi outer commit.

Về DBMS, rollback đến savepoint có thể khôi phục thay đổi dữ liệu và một số lock, nhưng thời điểm giải phóng lock/đối tượng khác phụ thuộc engine và isolation. Đừng giả định savepoint bảo đảm reset mọi trạng thái Java/ORM hoặc mọi side effect bên ngoài database.

### 3.2. Spring NESTED làm gì khi inner method được intercept?

Nếu outer đã mở transaction T1 và inner method khai báo:

~~~java
// Snippet: method phải được gọi qua Spring-managed proxy phù hợp.
@Transactional(propagation = Propagation.NESTED)
public void optionalUpdate() {
    jdbcTemplate.update("UPDATE optional_table SET score = score + 1");
}
~~~

Với JdbcTransactionManager/DataSourceTransactionManager và JDBC driver hỗ trợ savepoint, Spring tạo nested transaction status liên kết với savepoint; SQL inner chạy trên transaction-bound Connection của T1.

- **Inner return thành công:** Spring kết thúc nested scope, thường giải phóng savepoint. **Chưa gọi physical COMMIT** vì outer T1 vẫn đang chạy.
- **Inner ném RuntimeException đủ điều kiện rollback:** transaction interceptor yêu cầu rollback nested status; manager rollback về savepoint; lỗi được ném tiếp cho outer.
- **Outer catch lỗi inner rồi tiếp tục:** trong trường hợp savepoint rollback thành công và physical transaction vẫn hợp lệ, outer có thể tiếp tục và commit phần còn lại.
- **Outer kết thúc bằng rollback:** toàn bộ T1 bị hủy, kể cả thay đổi inner từng “thành công”.

Nếu dùng REQUIRED thay vì NESTED, inner runtime failure thường khiến logical scope đánh dấu **T1 rollback-only**, vì không có savepoint để rollback riêng; outer có thể nhận UnexpectedRollbackException khi cố commit. Đây là lý do NESTED hữu ích cho những nhánh có thể thất bại nhưng không cần hủy toàn bộ nghiệp vụ.

### 3.3. Một case quan trọng: nested success không phải commit

~~~text
T1 outer:
    UPDATE A = A + 10
    S1:
        UPDATE B = B + 10
        inner NESTED return success
    outer gặp lỗi và rollback T1

Kết quả cuối:
    A không tăng
    B cũng không tăng
~~~

Đây là một khác biệt quyết định với REQUIRES_NEW. Nếu yêu cầu sản phẩm là “ghi B dù phần A sau đó rollback”, NESTED không đáp ứng vì B chưa có commit độc lập.

## 4. REQUIRES_NEW vận hành với hai transaction vật lý

Khi inner method khai báo:

~~~java
// Snippet: method được gọi qua một Spring bean/proxy khác.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAudit() {
    jdbcTemplate.update("INSERT INTO audit_log(message) VALUES (?)", "attempted");
}
~~~

Nếu outer T1 đang hoạt động, Spring thường:

1. **Suspend** transaction context/resource của outer T1.
2. Lấy resource cho transaction T2 mới, thường là một JDBC Connection khác.
3. Mở transaction T2 với policy propagation/isolation/read-only/timeout riêng khi được hỗ trợ.
4. Chạy method inner và **COMMIT T2** hoặc **ROLLBACK T2** theo kết quả.
5. Cleanup T2, release Connection T2 và **resume** context của outer T1.
6. Cho outer tiếp tục; khi outer hoàn tất, nó commit/rollback T1 độc lập.

~~~mermaid
sequenceDiagram
    actor Caller
    participant Outer as Outer service
    participant TM as TransactionManager
    participant Inner as Inner service
    participant DB as DBMS
    Caller->>Outer: outer() REQUIRED
    Outer->>TM: begin T1
    TM->>DB: Connection 1 / T1
    Outer->>Inner: inner() REQUIRES_NEW
    Inner->>TM: suspend T1; begin T2
    TM->>DB: Connection 2 / T2
    Inner->>DB: SQL inner
    Inner->>TM: commit hoặc rollback T2
    TM->>DB: End T2
    TM->>Outer: resume T1
    Outer->>TM: commit hoặc rollback T1
    TM->>DB: End T1
    Outer-->>Caller: Kết quả
~~~

Nếu inner T2 **commit thành công** rồi outer T1 rollback, commit T2 thường vẫn tồn tại. Việc outer báo lỗi không làm TransactionManager rollback ngược transaction T2 đã commit. Điều đó chính là semantics của REQUIRES_NEW, đồng thời có thể là **rủi ro nhất quán nghiệp vụ** nếu sử dụng sai.

### Ví dụ đảo thứ tự kết quả

~~~text
BEGIN T1 (outer)
    UPDATE A = A + 10                  [chưa commit]
    SUSPEND T1
        BEGIN T2 (REQUIRES_NEW)
        UPDATE B = B + 10
        COMMIT T2                       [B đã commit]
    RESUME T1
    ERROR outer
ROLLBACK T1

Kết quả cuối:
    A giữ nguyên
    B tăng 10
~~~

**Tính độc lập không có nghĩa không tương tác:** hai physical transactions vẫn có thể tranh chấp khóa, deadlock hoặc gặp isolation anomaly. Nếu inner T2 muốn sửa hàng mà outer T1 đang khóa, T2 có thể phải chờ hoặc timeout; trong khi outer đang bị suspend, cuộc chờ có thể rất khó xử lý. Ví dụ thực hành ở dưới cố ý cập nhật **các hàng khác nhau** để tách bạch propagation khỏi vấn đề lock.

## 5. Ma trận dự đoán rollback và commit

Giả sử outer cập nhật hàng A, inner cập nhật hàng B. Cả hai dùng cùng DB và không có lỗi khác. Bảng sau là phần quan trọng nhất của bài:

| Tình huống | NESTED | REQUIRES_NEW |
| --- | --- | --- |
| Inner thành công; outer thành công | **A và B commit cùng T1** | B commit T2 trước; A commit T1 sau |
| Inner thành công; outer rollback | **A và B đều rollback** | A rollback; **B đã commit được giữ** |
| Inner rollback; outer bắt lỗi và commit | B rollback về savepoint; **A được commit** | B rollback T2; **A được commit** |
| Inner rollback; outer không bắt lỗi và rollback | Cả A và B rollback | B rollback T2, A rollback T1 |
| Inner và outer đều thành công nhưng outer commit sau đó thất bại | B cũng không thể coi đã commit nếu nằm trong T1 | B đã commit T2 có thể vẫn tồn tại dù T1 không commit |
| Chưa có outer transaction | Tạo transaction mới (không có transaction ngoài để đặt savepoint) | Tạo transaction mới |

Lưu ý: **không có outer transaction** thì NESTED không tạo savepoint treo lơ lửng. Giống các propagation cần transaction, Spring tạo một physical transaction mới để thực thi method. So sánh NESTED/REQUIRES_NEW có ý nghĩa lớn nhất khi **đã có transaction ở tầng gọi**.

### Trạng thái hiển thị ở database

NESTED dùng cùng physical transaction nên inner “thành công” thường **chưa nhìn thấy là dữ liệu đã commit** đối với các transaction độc lập, cho đến khi outer commit. REQUIRES_NEW commit riêng nên dữ liệu inner có thể hiển thị cho transaction khác sau commit theo mức isolation phù hợp. **Không đảm bảo outer nhìn thấy ngay dữ liệu T2** nếu outer có snapshot/transaction isolation đặc biệt; đừng phụ thuộc việc read lại của outer cho correctness mà không hiểu DBMS.

## 6. Ví dụ Java 17+ chạy được: bốn kịch bản cùng một database

Ví dụ dùng **Spring Framework 6.2.12**, **Spring JDBC**, **H2 2.3.232** và **JdbcTransactionManager**. Nó không cần Spring Boot hoặc server database riêng. Cùng hai bean service được Spring tạo AOP proxy; outer luôn dùng REQUIRED, inner thay đổi giữa NESTED và REQUIRES_NEW.

Ta tạo ba hàng A, B, C đều có amount=0. Các method outer cập nhật A và C; inner chỉ cập nhật B. Nhờ khác hàng, demo giảm nguy cơ tranh chấp lock giữa T1 và T2 để tập trung quan sát transaction semantics.

### 6.1. Cấu trúc dự án

~~~text
nested-versus-requires-new/
├── pom.xml
└── src/main/java/demo/NestedVsRequiresNewDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>nested-versus-requires-new</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <configuration>
                    <mainClass>demo.NestedVsRequiresNewDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring 6.x yêu cầu Java 17+. Ứng dụng thực dùng Spring Boot nên ưu tiên phiên bản Spring được BOM của Boot quản lý thay vì copy cứng version từ ví dụ.

### 6.3. src/main/java/demo/NestedVsRequiresNewDemo.java

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public final class NestedVsRequiresNewDemo {
    private NestedVsRequiresNewDemo() {}

    private static void show(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT amount FROM demo_amount WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT amount FROM demo_amount WHERE id = 2", Integer.class);
        Integer c = jdbc.queryForObject(
                "SELECT amount FROM demo_amount WHERE id = 3", Integer.class);
        System.out.printf("%s: A=%d, B=%d, C=%d%n", label, a, b, c);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("UPDATE demo_amount SET amount = 0");
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OuterService outer = ctx.getBean(OuterService.class);

            jdbc.execute("CREATE TABLE demo_amount (" +
                    "id INT PRIMARY KEY, amount INT NOT NULL)");
            for (int id = 1; id <= 3; id++) {
                jdbc.update(
                        "INSERT INTO demo_amount(id, amount) VALUES (?, ?)",
                        id, 0);
            }
            show(jdbc, "initial");

            outer.catchNestedFailure();
            show(jdbc, "NESTED failure, outer commit");

            reset(jdbc);
            try {
                outer.nestedSuccessThenOuterFailure();
            } catch (IllegalStateException expected) {
                // Outer rollback is intentional for this experiment.
            }
            show(jdbc, "NESTED success, outer rollback");

            reset(jdbc);
            try {
                outer.newSuccessThenOuterFailure();
            } catch (IllegalStateException expected) {
                // Inner REQUIRES_NEW committed before outer failed.
            }
            show(jdbc, "REQUIRES_NEW success, outer rollback");

            reset(jdbc);
            outer.catchNewFailure();
            show(jdbc, "REQUIRES_NEW failure, outer commit");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:nested_vs_new;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            JdbcTransactionManager manager = new JdbcTransactionManager(ds);
            manager.setNestedTransactionAllowed(true);
            return manager;
        }

        @Bean
        public InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        public OuterService outerService(
                JdbcTemplate jdbc, InnerService inner) {
            return new OuterService(jdbc, inner);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nestedFail() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 2");
            throw new IllegalStateException("nested failed");
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nestedSuccess() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 2");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNewSuccess() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 2");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNewFail() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 2");
            throw new IllegalStateException("requires new failed");
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, InnerService inner) {
            this.jdbc = jdbc;
            this.inner = inner;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void catchNestedFailure() {
            addToA();
            try {
                inner.nestedFail();
            } catch (IllegalStateException expected) {
                // Nested scope already rolled back to its savepoint.
            }
            addToC();
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void nestedSuccessThenOuterFailure() {
            addToA();
            inner.nestedSuccess();
            throw new IllegalStateException("outer failed");
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void newSuccessThenOuterFailure() {
            addToA();
            inner.requiresNewSuccess();
            throw new IllegalStateException("outer failed");
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void catchNewFailure() {
            addToA();
            try {
                inner.requiresNewFail();
            } catch (IllegalStateException expected) {
                // Independent inner transaction already rolled back.
            }
            addToC();
        }

        private void addToA() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 1");
        }

        private void addToC() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 3");
        }
    }
}
~~~

Đây là **một Java file đầy đủ**, bao gồm Spring config và hai service dưới dạng public static nested classes. Không dùng self-invocation: outer gọi method của **InnerService bean khác** do Spring cung cấp, nên interceptor có cơ hội xử lý NESTED/REQUIRES_NEW đúng cách.

Trong bean transactionManager, setNestedTransactionAllowed(true) được khai báo tường minh nhằm nhấn mạnh khả năng dùng savepoint trong ví dụ. Với DataSourceTransactionManager/JdbcTransactionManager, flag này thường có default true, nhưng **JDBC driver và DBMS vẫn cần hỗ trợ savepoint**.

**Vì sao code reset dữ liệu giữa các lần thử?** Để mỗi kịch bản bắt đầu từ A=B=C=0, người học nhìn ra tác động của riêng propagation. Các lệnh reset chạy **sau khi transaction trước đã kết thúc**, không tham gia outer transaction. DriverManagerDataSource tạo connection trực tiếp và phù hợp demo; production thường dùng connection pool.

### 6.4. Chạy chương trình và kết quả

Tại thư mục nested-versus-requires-new có pom.xml, máy cần JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến** do Java main tạo ra (không tính các thông báo từ Maven hoặc logging):

~~~text
initial: A=0, B=0, C=0
NESTED failure, outer commit: A=10, B=0, C=10
NESTED success, outer rollback: A=0, B=0, C=0
REQUIRES_NEW success, outer rollback: A=0, B=10, C=0
REQUIRES_NEW failure, outer commit: A=10, B=0, C=10
~~~

### 6.5. Phân tích từng tình huống

**Tình huống 1 — Inner NESTED thất bại; outer vẫn commit**

- Outer mở T1, cập nhật A từ 0 lên 10.
- Inner NESTED tạo savepoint S1 trên chính T1, cập nhật B lên 10 rồi ném IllegalStateException.
- Interceptor của inner rollback về S1; B quay về 0 trong T1.
- Outer catch exception, cập nhật C lên 10 rồi commit T1.
- Kết quả cuối: **A=10, B=0, C=10**. Có partial rollback của inner nhưng không có independent commit.

**Tình huống 2 — Inner NESTED thành công; outer rollback**

- Outer mở T1, cập nhật A lên 10.
- Inner NESTED tạo savepoint, cập nhật B lên 10 rồi return bình thường.
- Nested scope hoàn tất **không commit vật lý**. Outer sau đó ném IllegalStateException.
- Interceptor của outer rollback T1; cả A và B bị hủy.
- Kết quả: **A=0, B=0, C=0**. Đây là bằng chứng NESTED **không commit độc lập**.

**Tình huống 3 — Inner REQUIRES_NEW commit; outer rollback**

- Outer mở T1, cập nhật A lên 10 nhưng chưa commit.
- Inner REQUIRES_NEW suspend T1 và tạo T2 dùng một Connection khác.
- T2 cập nhật B lên 10 rồi **commit T2**.
- Spring resume T1; outer ném IllegalStateException và rollback T1.
- Kết quả: **A=0, B=10, C=0**. Inner giữ thay đổi đã commit dù outer thất bại.

**Tình huống 4 — Inner REQUIRES_NEW rollback; outer vẫn commit**

- Outer mở T1 và tăng A.
- T2 độc lập của inner tăng B rồi ném IllegalStateException, khiến T2 rollback.
- Spring resume T1, outer catch exception, tăng C rồi commit T1.
- Kết quả: **A=10, B=0, C=10**. Cùng các giá trị như tình huống 1 nhưng **cơ chế hoàn toàn khác**: savepoint trong T1 vs rollback một T2 độc lập.

**Không thể dùng chỉ một dòng “B=0” để phân biệt cơ chế.** Phải nhìn trường hợp inner thành công nhưng outer rollback, và nếu cần thì xem transaction manager log/connection identity.

## 7. Tại sao số lượng Connection ảnh hưởng trực tiếp đến thiết kế?

### 7.1. NESTED không cần một physical Connection mới cho savepoint

Với Spring JDBC local transaction, outer T1 có một transaction-bound JDBC Connection. Inner NESTED dùng **Connection đã liên kết** và tạo savepoint trên nó. Manager không cần suspend T1 để lấy Connection thứ hai; điều này thường tiết kiệm pool resource.

Nhưng savepoint **không rút ngắn đời của T1**. Nếu outer transaction giữ khóa lâu, các thay đổi và tài nguyên của T1 vẫn có thể gây tranh chấp đến khi outer hoàn tất. Không dùng NESTED để “tự động giải phóng mọi lock” sau inner return.

### 7.2. REQUIRES_NEW có thể làm cạn pool và gây chờ lẫn nhau

Với transaction T1 đang giữ Connection A, inner REQUIRES_NEW thường phải mượn Connection B. Nếu có N worker threads và pool chỉ có N connections, mỗi worker có thể chiếm một Connection A rồi chờ connection B. Điều đó có thể khiến tất cả cùng kẹt hoặc timeout.

Spring khuyến nghị sizing connection pool **lớn hơn số concurrent threads ít nhất một connection** khi dùng REQUIRES_NEW; thực tế còn cần tính các lượt inner nested/concurrency khác, pool timeout và workload. Không tự chọn mức cố định cho mọi hệ thống.

~~~text
Ví dụ pool=4, 4 thread đồng thời:
    Thread 1: giữ A1 (outer), đợi B1 (REQUIRES_NEW)
    Thread 2: giữ A2 (outer), đợi B2
    Thread 3: giữ A3 (outer), đợi B3
    Thread 4: giữ A4 (outer), đợi B4
    Pool còn 0 connection rảnh => các inner cùng chờ

Nếu chỉ dùng NESTED/savepoint:
    Mỗi outer dùng connection đã mượn;
    nested scope không cần connection mới chỉ để mở savepoint.
~~~

Ngoài connection pool, **REQUIRES_NEW có thể bị chặn bởi lock của outer**. Nếu T1 giữ lock trên row X rồi T2 cố update cùng row X, T2 phải chờ T1; nhưng T1 đang suspend chờ T2. Transaction isolation và lock timeout cần được cân nhắc. Các câu SQL trong demo chọn các hàng khác nhau để tránh trường hợp này.

### 7.3. Kiểm tra bằng log

Trong Spring Boot, có thể bật tạm thời:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Dấu hiệu cần tìm (câu chữ tùy phiên bản/manager):

~~~text
NESTED:
    Creating nested transaction...
    Creating savepoint...
    Rolling back transaction to savepoint...
    Outer transaction commit/rollback...

REQUIRES_NEW:
    Suspending current transaction...
    Creating new transaction...
    Initiating transaction commit/rollback...
    Resuming suspended transaction...
    Outer transaction commit/rollback...
~~~

Đừng coi các dòng trên là output literal bắt buộc. Việc ghi log debug/trace của Spring/DBMS có thể khác. Hãy kết hợp **transaction status, connection/pool metrics và dữ liệu đọc lại sau transaction**. Bật TRACE có chọn lọc; tránh log SQL parameters nhạy cảm trong production.

## 8. Điều kiện hỗ trợ: Spring manager, JDBC driver và JPA

### 8.1. JdbcTransactionManager / DataSourceTransactionManager

Với một DataSource JDBC local:

- **DataSourceTransactionManager** hỗ trợ nested transaction dựa vào JDBC Savepoint; thuộc tính **nestedTransactionAllowed** mặc định true trong trường hợp này.
- **JdbcTransactionManager** kế thừa DataSourceTransactionManager, thêm cơ chế dịch ngoại lệ commit/rollback JDBC thích hợp với Spring JDBC.
- Driver và DBMS phải hỗ trợ savepoint; nếu không, NESTED có thể bị từ chối hoặc hoạt động khác kỳ vọng.
- Cần để JdbcTemplate/DAO dùng **đúng DataSource** mà manager quản lý; nếu code tự mở Connection qua DriverManager và không liên kết transaction, savepoint không bao lệnh SQL đó.

Trước khi phụ thuộc NESTED, có thể kiểm tra capability của JDBC driver/DBMS và chạy integration test thật:

~~~java
// Snippet đọc metadata của một Connection tự mở trong môi trường kiểm tra.
// Không thực hiện thao tác trên Connection đang được Spring quản lý.
try (java.sql.Connection c = dataSource.getConnection()) {
    boolean savepoints = c.getMetaData().supportsSavepoints();
    System.out.println("supportsSavepoints=" + savepoints);
}
~~~

Đây chỉ là snippet minh họa (cần biến dataSource); **supportsSavepoints=true là điều kiện cần, chưa đủ** bảo đảm mọi đoạn code nested đúng vì còn manager, transaction status, SQL/DDL và DBMS restrictions.

### 8.2. JpaTransactionManager: đừng coi JPA là savepoint-aware

**JPA EntityManager/persistence context không có nested transaction semantics giống JDBC Savepoint.** Trong Spring, JpaTransactionManager có liên quan đến JDBC savepoints nhưng **nestedTransactionAllowed mặc định false**; nếu bật đặc biệt để phục vụ JDBC access thì savepoint tác động tới JDBC Connection chứ không tự “quay ngược” toàn bộ state của EntityManager và các entity đã được cache/dirty.

Vì vậy, **không chuyển máy móc @Transactional(NESTED) từ JDBC sang JPA** rồi kỳ vọng tất cả entity state và flush rollback được như từng đoạn JDBC. Cần tìm hiểu provider, transaction manager và chiến lược rollback thực tế; nếu không hỗ trợ đúng, thiết kế một transaction thống nhất hoặc tách workflow rõ ràng.

Với **JtaTransactionManager**, không giả định hỗ trợ savepoint NESTED theo cách JDBC local. Với **R2DBC/reactive**, khả năng savepoint và context khác biệt theo manager/driver/version; kiểm tra tài liệu và test trên R2DBC driver đang dùng. Bài demo này chỉ chứng minh Spring JDBC local.

### 8.3. Database/driver cũng là một phần của hợp đồng

Ngay cả với JDBC, khả năng rollback đến savepoint có thể bị giới hạn bởi DDL, engine transaction, stored procedures, trigger hoặc tình trạng transaction sau lỗi. Một số DBMS có behavior khóa và DDL riêng. H2 giúp học ý tưởng nhưng không thay thế test trên PostgreSQL/MySQL/Oracle hoặc DBMS production khi dùng savepoint để bảo vệ dữ liệu quan trọng.

## 9. Isolation, timeout và read-only khác nhau ra sao?

**NESTED:** vẫn cùng physical transaction với outer. Vì vậy isolation, timeout và read-only ở mức transaction/Connection thường do outer quyết định. Nếu inner NESTED khai báo Isolation.SERIALIZABLE nhưng outer đã mở READ_COMMITTED, không được mặc nhiên cho rằng có một physical transaction mới với isolation riêng.

**REQUIRES_NEW:** tạo physical transaction mới, nên có thể yêu cầu isolation/timeout/readOnly riêng và không kế thừa nguyên xi chính sách outer. Ví dụ:

~~~java
// Snippet trong bean được intercept; policy cần driver/DBMS hỗ trợ.
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 5,
    readOnly = true
)
public void readIndependentSnapshot() {
    // Chạy các truy vấn chỉ đọc thuộc transaction inner.
}
~~~

Đoạn này không phải chương trình độc lập. **readOnly=true là hint** có cách enforcement phụ thuộc manager/driver/DBMS, không phải một lớp bảo mật. Timeout cũng không tự ngắt mọi HTTP call đúng 5 giây. Một NESTED scope cùng Connection không thể thay đổi isolation của transaction vật lý đang chạy chỉ nhờ annotation inner.

Nếu method REQUIRED bên trong đã tham gia outer, nó cũng thường dùng đặc tính physical transaction của outer, dù metadata annotation khác. Khi cần validate mismatch, có thể nghiên cứu validateExistingTransaction=true trên AbstractPlatformTransactionManager theo môi trường cụ thể.

## 10. Rollback rules, bắt exception và UnexpectedRollbackException

### 10.1. Throw ra khỏi transactional proxy mới được advice quan sát

Hai snippet dưới đây có thể cho kết quả khác:

~~~java
// Minh họa: outer gọi inner bean khác để nested advice thực thi.
@Transactional
public void process() {
    try {
        innerService.optionalNestedStep(); // NESTED throws RuntimeException
    } catch (IllegalStateException ex) {
        // Inner interceptor đã rollback về savepoint trước khi lỗi tới đây.
    }
    repository.saveRequiredData();
}
~~~

Với NESTED/savepoint hợp lệ, outer có thể commit repository.saveRequiredData(). Nếu inner là REQUIRED thay vì NESTED, inner interceptor có thể đã đánh dấu physical transaction rollback-only; outer cố commit dẫn tới UnexpectedRollbackException. Với REQUIRES_NEW, inner rollback transaction của chính nó, outer có thể commit bình thường.

**Exception rules vẫn quan trọng**: mặc định @Transactional rollback với RuntimeException/Error; checked Exception không tự yêu cầu rollback trong cấu hình thông dụng trừ khi có rollbackFor hoặc default rollback rule phù hợp. Một checked exception từ inner NESTED có thể không tạo rollback về savepoint theo default; xác định rõ business exception và rollback policy.

### 10.2. Nếu outer không catch exception?

Với cả NESTED và REQUIRES_NEW, một RuntimeException từ inner **có thể đi tiếp qua outer transactional boundary**. Nếu outer không catch, outer cũng thường rollback theo rule của nó. Điểm khác biệt sẽ rõ khi:

- Inner **đã commit** trong REQUIRES_NEW rồi outer ném lỗi khác sau đó: inner commit vẫn tồn tại.
- Inner **thành công** trong NESTED rồi outer ném lỗi khác: inner changes vẫn thuộc T1 và bị outer rollback.

### 10.3. Nếu outer đã đánh dấu rollback-only?

Không có propagation nào làm outer đã rollback-only trở lại bình thường. NESTED inner success vẫn thuộc T1; cuối cùng outer T1 rollback. REQUIRES_NEW inner có thể commit độc lập nếu hoạt động đúng, nhưng outer vẫn phải rollback.

### 10.4. Catch bên trong inner khác catch bên ngoài inner

Nếu inner tự catch lỗi rồi return bình thường mà **không đánh dấu rollback-only**, interceptor của inner có thể coi method thành công. Với NESTED, savepoint có thể được release mà không rollback. Với REQUIRES_NEW, inner có thể commit. Vì vậy nếu lỗi là lý do phải hủy inner scope, hãy để exception phù hợp thoát tới interceptor hoặc gọi transaction status setRollbackOnly() theo API thích hợp.

Không viết catch (Exception ex) rồi chỉ log để “cứ chạy tiếp” khi nghiệp vụ thực sự cần rollback; việc nuốt exception có thể thay đổi kết quả commit.

## 11. Chọn NESTED hay REQUIRES_NEW theo ý nghĩa nghiệp vụ

### 11.1. NESTED phù hợp khi “cùng commit cuối, nhưng có nhánh có thể bỏ”

Ví dụ nhập một đơn hàng và có phần cập nhật ghi chú bổ sung:

- Outer transaction tạo order header và các order lines.
- Inner NESTED thử ghi một phần dữ liệu phụ cùng database.
- Nếu inner lỗi có thể bỏ qua theo business policy, rollback về savepoint; outer vẫn giữ order hợp lệ.
- Nếu outer thất bại và không thể commit order, **phần dữ liệu phụ từng thành công cũng phải mất**.

NESTED phù hợp khi outcome cuối cùng của inner **không được phép tồn tại độc lập** khỏi outer. Tuy nhiên, phải kiểm tra DB driver và khả năng dùng savepoint, không áp dụng máy móc cho JPA EntityManager.

### 11.2. REQUIRES_NEW phù hợp khi “inner có quyền commit kể cả outer thất bại”

Ví dụ ghi bản ghi thử xử lý một tác vụ (attempt log) vào cùng database:

- Outer thực thi tác vụ chính.
- Inner REQUIRES_NEW ghi sự kiện **“đã thử tác vụ”**, yêu cầu audit được giữ cả khi outer không thành công.
- Inner commit trước; nếu outer rollback, bản ghi attempt có thể vẫn tồn tại.

Nhưng cần phân biệt **attempt log** với **business audit of committed outcome**. Nếu audit record nói “đơn hàng đã hoàn tất” mà outer cuối cùng rollback, REQUIRES_NEW có thể tạo thông tin sai. Trường hợp audit phải phản ánh giao dịch **đã commit**, nên cân nhắc after-commit notification hoặc transactional outbox trong cùng DB thay vì commit audit độc lập.

### 11.3. Khi không nên dùng cả hai

Nếu nghiệp vụ cần **tất cả cùng thành công hoặc cùng thất bại**, đơn giản nhất là một outer **REQUIRED** cho tất cả thao tác, không NESTED/REQUIRES_NEW không cần thiết.

Nếu nghiệp vụ cần ghi vào hai DB không được điều phối chung, REQUIRES_NEW trên một transaction manager local **không làm hai DB trở thành một distributed transaction nguyên tử**. Phải đánh giá JTA/XA khi tài nguyên hỗ trợ, hoặc dùng outbox/saga/eventual consistency. NESTED cũng chỉ áp dụng trong phạm vi một transaction resource phù hợp, không dùng savepoint để rollback HTTP/email/message đã gửi.

### Quy trình lựa chọn

1. **Inner thành công có được giữ nếu outer rollback không?**
   - Nếu **không**: ưu tiên REQUIRED hoặc NESTED nếu còn cần rollback nhánh riêng.
   - Nếu **có**: cân nhắc REQUIRES_NEW, xem lại ngữ nghĩa audit/side effect.
2. **Inner thất bại có được bỏ qua để outer vẫn commit không?**
   - Nếu **không**: REQUIRED có thể đủ và đơn giản hơn.
   - Nếu **có**: NESTED/savepoint hoặc REQUIRES_NEW đều có thể, nhưng điểm khác nhau ở **khả năng commit inner độc lập**.
3. **Transaction manager/driver/DBMS có hỗ trợ savepoint không?**
   - Nếu không: không dựa vào NESTED.
4. **Pool/lock có đủ cho connection và transaction riêng không?**
   - Nếu không: REQUIRES_NEW có thể làm hệ thống chờ/timeout; xem lại thiết kế.
5. **Đã kiểm chứng bằng integration test trên DBMS thật chưa?**
   - Nếu chưa: chưa coi propagation policy là bảo đảm kinh doanh.

## 12. Cảnh báo AOP proxy: annotation không tự hoạt động khi self-invocation

Trong proxy mode thông thường:

~~~java
// Snippet KHÔNG hoạt động như mong đợi khi gọi this.inner().
@Service
public class WrongService {
    @Transactional
    public void outer() {
        this.inner(); // Truy cập trực tiếp, không qua transaction proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Tưởng là transaction khác, nhưng advice của inner có thể không chạy.
    }
}
~~~

Đây là mã minh họa, cần imports và context để dùng. Tương tự, this.innerNested() không tạo savepoint chỉ vì method có @Transactional(NESTED).

Trong demo đầy đủ, **OuterService** gọi **InnerService** là Spring bean riêng. Lời gọi đi qua proxy của InnerService nên propagation metadata có tác dụng. Một class được tạo bằng new ngoài container, method private/final, @Async chuyển thread hoặc gọi sai bean cũng có thể khiến kết quả không như dự đoán.

**Debug trước khi kết luận “NESTED không hoạt động”:** xác minh method thực sự được Spring intercept, manager là gì, DataSource có đúng không và transaction ngoài đã tồn tại chưa.

## 13. Chẩn đoán và kiểm thử

| Triệu chứng | Nguyên nhân có thể | Việc cần kiểm tra |
| --- | --- | --- |
| @Transactional(NESTED) báo không hỗ trợ | Manager không hỗ trợ savepoint, driver/DBMS không hỗ trợ, nestedTransactionAllowed=false | Kiểm tra manager, driver supportsSavepoints(), test savepoint thật |
| Inner NESTED success nhưng outer rollback làm mất cả inner | **Đúng semantics:** cùng physical transaction | Đổi yêu cầu sang REQUIRES_NEW chỉ nếu commit độc lập thật sự cần |
| Inner REQUIRES_NEW commit rồi outer rollback vẫn còn inner | **Đúng semantics:** T2 độc lập | Xác nhận business có muốn dữ liệu này tồn tại độc lập không |
| Inner REQUIRES_NEW treo/timeout | Cạn pool; T2 đợi lock T1 đang giữ | Pool active/idle/pending, DB locks, transaction duration |
| NESTED inner exception bị catch nhưng outer vẫn rollback | DB transaction hỏng, rollback-only khác, inner chưa rollback savepoint hoặc lỗi đã đi qua outer | Bật transaction debug, xem exception/rollback-only và DB state |
| NESTED trên JPA lỗi hoặc entity state không trở lại | JpaTransactionManager không bảo đảm savepoint cho EntityManager state | Không dùng NESTED như JPA nested semantics; test với provider |
| Không có log tạo savepoint hoặc suspend | Self-invocation, chưa bật transaction management, wrong manager, method không đi qua proxy | Kiểm tra AOP proxy, @EnableTransactionManagement, bean naming |
| Inner REQUIRES_NEW thấy dữ liệu outer chưa commit không như mong muốn | T2 độc lập, không tự chia sẻ uncommitted state của T1 | DB isolation, thời điểm flush/commit, giao thức truyền dữ liệu |
| NESTED có method riêng nhưng vẫn thấy nhiều commits | Có top-level calls khác hoặc khác DataSource/manager | Đối chiếu JDBC Connection identity, transaction owner |
| Lỗi ở outer sau khi inner NESTED return “success” | Savepoint đã hoàn tất, outer vẫn quyết định kết quả cuối | Kiểm tra outer exception và rollback rule |
| UnexpectedRollbackException khi inner REQUIRED lỗi | Inner REQUIRED đánh dấu chung rollback-only, không phải NESTED savepoint | So sánh annotation thực tế, proxy và transaction status |

**Một integration test tốt** phải bao các trường hợp:

1. Outer + inner NESTED: inner throw, outer catch và commit → outer còn, inner mất.
2. Outer + inner NESTED: inner success, outer rollback → **cả hai mất**.
3. Outer + inner REQUIRES_NEW: inner success, outer rollback → **inner còn**.
4. Outer + inner REQUIRES_NEW: inner throw, outer catch rồi commit → **outer còn, inner mất**.
5. Inner được gọi không có outer: xác nhận method vẫn tạo transaction phù hợp.
6. Kiểm tra lỗi savepoint capability và connection pool nếu ứng dụng phụ thuộc vào những tính năng đó.

Nếu dùng Spring TestContext với test được annotate @Transactional, framework test có thể rollback ở cuối khiến quan sát commit vật lý bị lệch. Hãy dùng test boundary và connection/transaction đọc lại độc lập; chương trình Java main ở trên tránh confound này bằng cách gọi qua bean và query sau mỗi transaction.

## 14. Các câu hỏi tự kiểm tra

**Câu 1.** NESTED có mở một physical transaction mới khi outer đã có transaction chưa?  
**Trả lời:** Thông thường không với JDBC local manager; nó dùng savepoint trong cùng physical transaction.

**Câu 2.** Inner NESTED đã return thành công. Outer rollback. Dữ liệu inner có còn không?  
**Trả lời:** Không; inner vẫn thuộc outer physical transaction và chưa có commit độc lập.

**Câu 3.** Inner REQUIRES_NEW đã commit. Outer rollback. Điều gì xảy ra với dữ liệu inner?  
**Trả lời:** Commit inner có thể vẫn tồn tại vì physical transaction riêng của inner đã hoàn tất.

**Câu 4.** Inner NESTED rollback về savepoint, outer bắt lỗi rồi tiếp tục. Outer có thể commit phần trước/sau savepoint không?  
**Trả lời:** Có trong điều kiện manager/DBMS hỗ trợ và physical transaction vẫn hợp lệ; các thay đổi sau savepoint bị rollback sẽ không được giữ.

**Câu 5.** REQUIRES_NEW có luôn an toàn hơn NESTED?  
**Trả lời:** Không. Nó có semantics commit độc lập và thường cần thêm connection; có thể gây cạn pool, lock wait và trạng thái nghiệp vụ không nhất quán nếu dùng sai.

**Câu 6.** Vì sao JPA EntityManager không thể mặc nhiên dùng NESTED như JDBC?  
**Trả lời:** JDBC savepoint không tự điều khiển đầy đủ state/persistence context của JPA. JpaTransactionManager có nestedTransactionAllowed mặc định false và cần hiểu rõ giới hạn của provider.

**Câu 7.** Nếu không có outer transaction, method NESTED làm gì?  
**Trả lời:** Manager phù hợp tạo một transaction mới; không thể tạo savepoint trong một transaction không tồn tại.

**Câu 8.** Tại sao gọi this.inner() có @Transactional(REQUIRES_NEW) có thể không mở T2?  
**Trả lời:** Trong proxy mode, self-invocation không đi qua Spring transaction proxy nên propagation advice có thể không thực thi.

**Câu 9.** Một hệ thống cần ghi audit “đơn đã commit” nhưng outer có thể rollback. Có nên dùng REQUIRES_NEW để ghi audit trước outer commit không?  
**Trả lời:** Cần rất cẩn trọng; có thể ghi audit sai vì outer rollback. Cân nhắc after-commit hoặc transactional outbox phản ánh đúng business outcome.

**Câu 10.** Tại sao cả NESTED và REQUIRES_NEW đều có thể để lại A=10,B=0,C=10 khi inner lỗi và outer catch?  
**Trả lời:** Hai cơ chế rollback inner khác nhau nhưng trạng thái cuối tình huống đó giống nhau. Phải thêm kịch bản inner success/outer rollback để phân biệt: NESTED mất inner, REQUIRES_NEW giữ inner đã commit.

## 15. Tổng kết ngắn gọn

- **NESTED = một physical transaction + JDBC savepoint + rollback một phần; outer quyết định commit cuối.**
- **REQUIRES_NEW = transaction mới độc lập + suspend outer + commit/rollback riêng; outer rollback không hủy inner đã commit.**
- NESTED phù hợp nhánh DB có thể bỏ nhưng vẫn phải cùng outcome với outer; REQUIRES_NEW chỉ phù hợp khi cần commit inner thật sự độc lập.
- REQUIRES_NEW thường thêm áp lực lên connection pool và có thể bị lock của outer chặn; NESTED phụ thuộc savepoint capability của driver/DBMS.
- Với JPA, không giả định persistence context có nested semantics của JDBC savepoint.
- Đảm bảo method được gọi qua Spring proxy, đúng TransactionManager/DataSource và rollback rules.
- Luôn test bốn kịch bản commit/rollback trên database thật khi nghiệp vụ quan trọng; **annotation mô tả ý định, dữ liệu sau transaction chứng minh kết quả**.

## Tài liệu tham khảo

- [Spring Framework — Transaction Propagation: REQUIRES_NEW và NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — DataSourceTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — JdbcTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html)
- [Spring Framework — JpaTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Java SE 17 — Connection, Savepoint API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html)
