# NEVER và lỗi khi gặp giao dịch hiện hành trong Spring Framework

## 1. Bản chất của `Propagation.NEVER`

Trong Spring Framework, `Propagation.NEVER` là chính sách yêu cầu **phương thức phải chạy ngoài một transaction hiện hành**. Với phương thức được Spring transaction interceptor xử lý:

```java
@Transactional(propagation = Propagation.NEVER)
public void runOutsideTransaction() {
    // Logic chỉ được phép chạy khi KHÔNG có transaction hiện hành.
}
```

Spring áp dụng hai nhánh hành vi:

- **Không có transaction hiện hành mà transaction manager đang sử dụng nhận biết:** cho method body chạy **không có physical transaction được mở mới** cho lời gọi này.
- **Có transaction hiện hành:** Spring **ném `IllegalTransactionStateException`** từ transaction infrastructure **trước khi method body chạy**.

**NEVER không suspend transaction ngoài, không tạo transaction mới, không lập savepoint và không tự commit/rollback một transaction đã tồn tại.** Nếu muốn tạm treo transaction ngoài nhưng vẫn cho phép inner code chạy, đó là `Propagation.NOT_SUPPORTED`, chứ không phải `NEVER`.

Tên exception trong Spring:

```java
org.springframework.transaction.IllegalTransactionStateException
```

Đây là **tên class để tham khảo**, không phải một file Java hay statement độc lập. Nó là một unchecked transaction exception. Thông báo thường gặp trong `AbstractPlatformTransactionManager` là:

```text
Existing transaction found for transaction marked with propagation 'never'
```

Khi xử lý lỗi, kiểm tra **kiểu exception**, tránh phụ thuộc vào chính xác từng chữ của thông điệp vì phiên bản/implementation có thể thay đổi.

### Mục tiêu của bài học

1. Phân biệt «không tạo transaction» với «từ chối transaction hiện hành».
2. Hiểu ngoại lệ `NEVER` xảy ra ở **proxy/transaction manager**, trước thân method.
3. Phân tích kết quả khi outer `@Transactional` gọi inner `NEVER` rồi **catch** hoặc **không catch** ngoại lệ.
4. So sánh rõ `NEVER`, `NOT_SUPPORTED`, `MANDATORY`, `SUPPORTS` và `REQUIRED`.
5. Tự kiểm chứng bằng Spring JDBC, H2, Java 17 và Maven; quan sát cả log lẫn dữ liệu database sau commit/rollback.
6. Nhận diện giới hạn proxy, context, transaction manager, test transaction và resource participation.

## 2. Hai đường gọi khác nhau

### 2.1. Gọi `NEVER` khi không có transaction

```text
Application caller không có transaction
         |
         v
Spring proxy @Transactional(NEVER)
         |
         +--> Transaction manager không thấy transaction hiện hành
         |
         +--> Cho phép method body chạy
                   |
                   v
             Không mở physical transaction mới
```

Trong ví dụ Spring JDBC, cờ `TransactionSynchronizationManager.isActualTransactionActive()` ở bên trong method là `false`. Cần phân biệt điều này với việc «không có hoạt động database»: code vẫn có thể gọi JDBC, đọc dữ liệu hoặc thực thi SQL. Với JDBC connection thường ở `autoCommit=true` khi không tham gia transaction, **mỗi UPDATE có thể được commit riêng**. `NEVER` không đảm bảo tính nguyên tử của nhiều thao tác ghi.

Một `@Transactional(NEVER)` được gọi từ `main()` thông thường, khi không có transaction bao quanh, sẽ qua kiểm tra và chạy thành công **nếu không có lỗi ứng dụng khác**.

### 2.2. Gọi `NEVER` khi đã có transaction

```text
OuterService.process()  @Transactional(REQUIRED)
         |
         +--> Bắt đầu transaction T1
         +--> UPDATE outer_row trong T1 (chưa commit)
         |
         +--> InnerService.runOutsideTransaction()
                   @Transactional(NEVER)
                       |
                       v
                Spring transaction interceptor:
                Phát hiện T1 hiện hành
                       |
                       +--> IllegalTransactionStateException
                             (trước method body)
         |
         +--> Outer nhận exception và quyết định xử lý
```

Spring **không chạy thân inner** sau khi phát hiện vi phạm propagation. Những dòng log, SQL hoặc side effect đặt ở **bên trong inner body** sẽ không được thực thi. Đây là tính chất «fail-fast» hữu ích khi một API có contract rõ ràng rằng nó không được chạy trong transaction của caller.

Tuy nhiên, ngoại lệ được ném từ interceptor của inner **không tự chứng minh** transaction T1 đã bị rollback. T1 có commit hay không còn tùy caller và transaction interceptor ngoài cùng.

## 3. Cùng lỗi nhưng outer có thể commit hoặc rollback

Xét hai bean Spring khác nhau:

```java
@Service
class OuterService {
    private final StrictService strict;

    OuterService(StrictService strict) {
        this.strict = strict;
    }

    @Transactional
    public void process() {
        repository.updateA();
        strict.mustRunWithoutTransaction();
    }
}

@Service
class StrictService {
    @Transactional(propagation = Propagation.NEVER)
    public void mustRunWithoutTransaction() {
        repository.updateB();
    }
}
```

Đây là **mã minh họa**, các biến `repository` và imports chưa được khai báo, không thể biên dịch độc lập. Lời gọi giữa **hai Spring beans** là quan trọng: nếu method `NEVER` được gọi bằng `this.inner()` trong cùng target, chế độ AOP proxy mặc định có thể bỏ qua transaction interceptor.

Giả sử outer `process()` đã mở transaction T1 và ghi `A`:

- Inner proxy nhận lời gọi `NEVER`, phát hiện T1, rồi ném `IllegalTransactionStateException`.
- Thân `mustRunWithoutTransaction()` **chưa chạy**, nên `updateB()` không được thực hiện.
- **Nếu outer không catch exception:** lỗi unchecked tiếp tục đi qua outer transaction interceptor; theo quy tắc rollback mặc định, outer T1 bị rollback, `updateA()` không được commit.
- **Nếu outer catch đúng exception rồi return bình thường:** inner `NEVER` chưa tham gia T1 để tự đặt rollback-only, nên T1 có thể commit `updateA()`, miễn các phần khác không khiến transaction rollback.

Minh họa cách catch có điều kiện:

```java
@Transactional
public void processAndOptionallySkip() {
    repository.updateA();
    try {
        strict.mustRunWithoutTransaction();
    } catch (IllegalTransactionStateException ex) {
        // Chỉ bỏ qua nếu hợp đồng nghiệp vụ CHO PHÉP thiếu bước strict.
        auditLogger.warn("Wrong transaction context", ex);
    }
}
```

Đoạn trên **không độc lập**, vì `repository`, `strict` và `auditLogger` là dependency giả định. Nếu thao tác strict là bước bắt buộc của use case, «nuốt lỗi để commit outer» là thiết kế sai. Cách đúng có thể là **điều chỉnh ranh giới transaction** để gọi strict trước/sau transaction, hoặc cố ý để ngoại lệ làm thất bại cả use case.

**Không nhầm với `UnexpectedRollbackException`:** exception này thường xuất hiện khi một participating `REQUIRED` scope đánh dấu cùng physical transaction rollback-only, nhưng outer vẫn cố commit. Với `NEVER`, Spring từ chối **trước khi inner tham gia transaction**; loại lỗi trực tiếp là `IllegalTransactionStateException`. Nếu không catch, outer có thể rollback vì exception lan ra, không phải vì inner tham gia T1.

## 4. Vì sao `NEVER` khác `NOT_SUPPORTED`?

Cả hai propagation đều hướng tới việc **method body không chạy trong transaction hiện hành**, nhưng xử lý caller đang có transaction theo hai cách khác hẳn nhau.

```text
Khi T1 đã tồn tại:

NEVER:
T1 đang hoạt động
  └── Gọi inner proxy
         └── THROW IllegalTransactionStateException
                └── KHÔNG chạy method body

NOT_SUPPORTED:
T1 đang hoạt động
  └── Gọi inner proxy
         ├── SUSPEND T1
         ├── Chạy body KHÔNG có transaction T1
         ├── RESUME T1
         └── Quay lại outer
```

**`NEVER` là lời tuyên bố «caller không được mang transaction vào đây».** Nếu caller vi phạm, ứng dụng phải sửa cách gọi hoặc chấp nhận báo lỗi.

**`NOT_SUPPORTED` là lời tuyên bố «dù caller có transaction, hãy chạy đoạn này ngoài transaction».** Spring cố tạm treo T1 và sau đó khôi phục (theo khả năng của transaction manager). Những JDBC updates trong đoạn `NOT_SUPPORTED` có thể autocommit từng statement. Nếu T1 rollback, chúng **không mặc nhiên rollback theo**.

Chọn `NEVER` nếu cần **phát hiện sai contract sớm**. Chọn `NOT_SUPPORTED` nếu chủ đích là **thực thi code ngoài transaction kể cả khi caller đang có T1**. Cả hai không thay thế được một transaction thật khi muốn nhiều SQL cùng commit/rollback.

## 5. So sánh trong cả bảng propagation

| Propagation inner | Không có transaction sẵn | Đang có transaction T1 |
| --- | --- | --- |
| `REQUIRED` | Tạo transaction mới | Tham gia T1 |
| `SUPPORTS` | Chạy không có physical transaction mới | Tham gia T1 |
| `MANDATORY` | Ném lỗi vì thiếu transaction | Tham gia T1 |
| `REQUIRES_NEW` | Tạo transaction mới | Suspend T1 và tạo T2 độc lập |
| `NOT_SUPPORTED` | Chạy không transaction | Suspend T1 rồi chạy không transaction |
| **`NEVER`** | **Chạy không transaction** | **Ném `IllegalTransactionStateException`** |
| `NESTED` (manager hỗ trợ) | Hành xử gần giống `REQUIRED` | Có thể tạo savepoint trong T1 |

Một vài phản ví dụ:

- `NEVER` **không** phải «read-only transaction»: `readOnly=true` chỉ ảnh hưởng transaction attributes khi áp dụng được; `NEVER` không cho phép transaction hiện hành.
- `NEVER` **không** phải «transaction mới» như `REQUIRES_NEW`.
- `NEVER` **không** phải «savepoint» như `NESTED`.
- `NEVER` và `MANDATORY` là cặp điều kiện ngược nhau: `MANDATORY` **yêu cầu** một transaction, còn `NEVER` **cấm** một transaction.
- `NEVER` và `SUPPORTS` giống nhau ở trường hợp caller không có transaction, nhưng `SUPPORTS` chấp nhận tham gia T1 còn `NEVER` từ chối T1.

## 6. Lab chạy độc lập: Java 17+, Spring Framework và H2

Mục tiêu lab không chỉ nhìn exception, mà còn chứng minh **method body có/không chạy** và **giao dịch ngoài cuối cùng commit hay rollback**. Ví dụ dùng:

- Java 17+, Maven 3.9+.
- Spring Framework **6.2.8**, Spring JDBC/transaction infrastructure.
- H2 **2.3.232** chạy trong bộ nhớ; không cần Spring Boot hay web server.
- Một bảng `counters` có ba hàng: `outer`, `never`, `not_supported`. Mỗi case reset cả ba về 0.

Có bốn case:

1. **Không có T1 → NEVER chạy:** tăng `never` lên 1.
2. **Có T1, outer catch lỗi NEVER:** tăng `outer` lên 1; inner body không chạy; T1 commit.
3. **Có T1, lỗi NEVER lan ra:** inner body không chạy; outer T1 rollback.
4. **Có T1, inner NOT_SUPPORTED rồi outer lỗi:** inner chạy ngoài T1 và ghi dữ liệu; outer T1 rollback, ghi inner vẫn tồn tại.

### 6.1. Cấu trúc dự án

```text
never-tx-demo/
├── pom.xml
└── src/main/java/example/NeverDemo.java
```

### 6.2. `pom.xml`

Tệp bắt đầu **ngay** bằng XML declaration; copy nguyên code fence vào `pom.xml`, không thêm chú thích phía trước.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>never-tx-demo</artifactId>
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
                    <mainClass>example.NeverDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` hỗ trợ `ApplicationContext` và bean lifecycle; `spring-jdbc` có `JdbcTemplate` và `DataSourceTransactionManager`; `spring-tx` chứa propagation/transaction annotations. H2 phải có compile classpath vì code import `org.h2.jdbcx.JdbcDataSource`.

### 6.3. `src/main/java/example/NeverDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class NeverDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            StrictService strict = ctx.getBean(StrictService.class);
            OuterService outer = ctx.getBean(OuterService.class);

            runCase("NEVER without T1", jdbc, strict::mustRunOutside);
            runCase("Outer catches NEVER error", jdbc, outer::catchesNever);
            runCase("Outer propagates NEVER error", jdbc, outer::propagatesNever);
            runCase(
                "NOT_SUPPORTED then outer fails",
                jdbc,
                outer::notSupportedThenFails
            );
        }
    }

    private static void runCase(String title, JdbcTemplate jdbc, Runnable work) {
        reset(jdbc);
        System.out.println("CASE: " + title);
        try {
            work.run();
            System.out.println("Outcome: returned");
        } catch (IllegalTransactionStateException ex) {
            System.out.println("Outcome: IllegalTransactionStateException");
        } catch (IllegalStateException ex) {
            System.out.println("Outcome: " + ex.getMessage());
        }

        Integer outer = jdbc.queryForObject(
            "SELECT n FROM counters WHERE k = ?", Integer.class, "outer"
        );
        Integer never = jdbc.queryForObject(
            "SELECT n FROM counters WHERE k = ?", Integer.class, "never"
        );
        Integer other = jdbc.queryForObject(
            "SELECT n FROM counters WHERE k = ?", Integer.class, "not_supported"
        );
        System.out.println(
            "Values: outer=" + outer + ", never=" + never
                + ", not_supported=" + other
        );
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.execute("DROP TABLE IF EXISTS counters");
        jdbc.execute(
            "CREATE TABLE counters (k VARCHAR(30) PRIMARY KEY, n INT NOT NULL)"
        );
        jdbc.update("INSERT INTO counters(k, n) VALUES (?, ?)", "outer", 0);
        jdbc.update("INSERT INTO counters(k, n) VALUES (?, ?)", "never", 0);
        jdbc.update(
            "INSERT INTO counters(k, n) VALUES (?, ?)", "not_supported", 0
        );
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:never_tx;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public StrictService strictService(JdbcTemplate jdbc) {
            return new StrictService(jdbc);
        }

        @Bean
        public OuterService outerService(
            JdbcTemplate jdbc, StrictService strict
        ) {
            return new OuterService(jdbc, strict);
        }
    }

    public static class StrictService {
        private final JdbcTemplate jdbc;

        public StrictService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.NEVER)
        public void mustRunOutside() {
            System.out.println(
                "NEVER body active="
                    + TransactionSynchronizationManager.isActualTransactionActive()
            );
            jdbc.update("UPDATE counters SET n=n+1 WHERE k=?", "never");
        }

        @Transactional(propagation = Propagation.NOT_SUPPORTED)
        public void runWithoutT1() {
            System.out.println(
                "NOT_SUPPORTED body active="
                    + TransactionSynchronizationManager.isActualTransactionActive()
            );
            jdbc.update("UPDATE counters SET n=n+1 WHERE k=?", "not_supported");
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final StrictService strict;

        public OuterService(JdbcTemplate jdbc, StrictService strict) {
            this.jdbc = jdbc;
            this.strict = strict;
        }

        private void incrementOuter() {
            jdbc.update("UPDATE counters SET n=n+1 WHERE k=?", "outer");
        }

        private void showActive() {
            System.out.println(
                "Outer active="
                    + TransactionSynchronizationManager.isActualTransactionActive()
            );
        }

        @Transactional
        public void catchesNever() {
            showActive();
            incrementOuter();
            try {
                strict.mustRunOutside();
            } catch (IllegalTransactionStateException expected) {
                System.out.println("Caught in outer: IllegalTransactionStateException");
            }
        }

        @Transactional
        public void propagatesNever() {
            showActive();
            incrementOuter();
            strict.mustRunOutside();
        }

        @Transactional
        public void notSupportedThenFails() {
            showActive();
            incrementOuter();
            strict.runWithoutT1();
            throw new IllegalStateException("forced outer failure");
        }
    }
}
```

**Tại sao ví dụ làm rõ cơ chế?**

- `Config` tạo đúng một datasource và một transaction manager JDBC; `JdbcTemplate` dùng cùng datasource.
- `@EnableTransactionManagement` bật xử lý annotation. `OuterService` và `StrictService` là **hai Spring beans** được nhận qua `ctx.getBean`, không phải target tự tạo trong `main()`; lời gọi outer tới strict đi qua proxy.
- Các method `@Transactional` là public và class không final, thuận tiện cho class-based Spring AOP proxy. Nếu tự gọi bằng `this`, kết quả có thể khác.
- `reset()` thực hiện ngoài transaction trước mỗi case; vì thế mỗi case có dữ liệu ban đầu y hệt nhau và các câu query sau case nhìn vào trạng thái đã commit/rollback.
- `mustRunOutside()` in một dòng ngay **đầu thân method**. Nếu dòng này không xuất hiện khi có T1, ta thấy rõ interceptor đã ngăn body chạy.
- `runWithoutT1()` thể hiện `NOT_SUPPORTED`: nó đi vào body dù outer T1 đang tồn tại; việc SQL ghi vào hàng khác giúp tránh chờ row lock của T1.
- Chương trình cố ý catch exception **ở ngoài transactional boundary** trong `runCase()` để còn kiểm tra database; trong case outer catch, exception được bắt **ngay bên trong** boundary outer. Hai vị trí catch dẫn đến kết quả transaction khác nhau.

### 6.4. Biên dịch và chạy

Ở thư mục `never-tx-demo`, dùng JDK 17+ và Maven 3.9+:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Các dòng sau là output **do ứng dụng in ra** theo đúng thứ tự (bỏ qua log bổ sung của Maven/Spring):

```text
CASE: NEVER without T1
NEVER body active=false
Outcome: returned
Values: outer=0, never=1, not_supported=0
CASE: Outer catches NEVER error
Outer active=true
Caught in outer: IllegalTransactionStateException
Outcome: returned
Values: outer=1, never=0, not_supported=0
CASE: Outer propagates NEVER error
Outer active=true
Outcome: IllegalTransactionStateException
Values: outer=0, never=0, not_supported=0
CASE: NOT_SUPPORTED then outer fails
Outer active=true
NOT_SUPPORTED body active=false
Outcome: forced outer failure
Values: outer=0, never=0, not_supported=1
```

### 6.5. Phân tích kết quả từng case

**Case 1 — Không có T1.** `strict.mustRunOutside()` được gọi từ `main()` qua proxy, nhưng caller chưa mở transaction. `NEVER` cho phép body chạy. `TransactionSynchronizationManager.isActualTransactionActive()` trả `false`; JDBC update tăng `never=1` và được autocommit trong môi trường H2 demo. Không có transaction mới do `NEVER` mở.

**Case 2 — Outer bắt lỗi.** `OuterService.catchesNever()` mở T1 và tăng `outer`. Lời gọi `StrictService.mustRunOutside()` bị từ chối vì manager thấy T1; **không có log `NEVER body`**, `never` không tăng. Outer catch `IllegalTransactionStateException` và hoàn thành hợp lệ, nên T1 commit `outer=1`. Việc inner fail-fast không đồng nghĩa T1 tự bị đánh dấu rollback-only.

**Case 3 — Outer để lỗi lan ra.** Sau khi tăng `outer` trong T1, outer gọi strict và nhận exception. Không có catch trong outer, lỗi unchecked đi qua outer interceptor nên T1 rollback. Tại `runCase()`, caller bắt ngoại lệ sau boundary; dữ liệu quay về `outer=0, never=0`. Không có update nào được chạy trong inner body `NEVER`.

**Case 4 — Đối chứng NOT_SUPPORTED.** Outer mở T1, cập nhật `outer`, rồi gọi `StrictService.runWithoutT1()`. Spring suspend T1, cho code inner chạy ngoài transaction, nên có dòng `NOT_SUPPORTED body active=false`; update hàng `not_supported` được autocommit riêng. Sau khi resume T1, outer ném `IllegalStateException` và T1 rollback. `not_supported=1` vẫn giữ, cho thấy `NOT_SUPPORTED` là «suspend rồi thực thi», không phải «báo lỗi và bỏ qua body» như `NEVER`.

## 7. Khi nào dùng `NEVER` thay cho cơ chế khác?

`NEVER` là một **guard cho kiến trúc**, hữu ích khi một operation **không được phép chạy trong transaction của caller**. Ví dụ một thao tác rất chậm hoặc một API phải được gọi ở ngoài database transaction boundary để tránh giữ JDBC connection/row locks trong lúc chờ. Nếu đặt `NEVER` trên entry point của bean, caller vô tình bọc nó trong T1 sẽ bị từ chối sớm.

Mẫu điều phối minh họa:

```java
public void orchestrate() {
    preflightService.checkOutsideTransaction(); // NEVER
    orderService.writeOrder();                  // REQUIRED
    notificationService.scheduleAfterCommit(); // Theo thiết kế outbox/event
}
```

Đây là **mã minh họa**; các dependency và transaction semantics của bước notification chưa được triển khai. Đừng suy diễn rằng ba method chạy tuần tự thì transaction đảm bảo notification chỉ xảy ra sau commit. Nếu cần liên kết event với dữ liệu đã commit, hãy tìm hiểu transactional outbox hoặc after-commit hooks.

`NEVER` **không bảo đảm atomicity** của nhiều thao tác ghi ở thân method. Nếu body thực hiện hai `UPDATE` ngoài transaction trong JDBC auto-commit mode, update thứ nhất có thể đã commit dù update thứ hai thất bại. Nếu cần cùng rollback, chọn một transaction boundary thực sự.

### 7.1. NEVER như một contract, không phải một hàng rào bảo mật

`NEVER` kiểm tra transaction hiện hành **theo transaction manager được chọn** khi lời gọi đã được intercept. Nó không quét mọi tài nguyên/driver hoặc mọi database transaction mở thủ công trên JVM. Nếu ứng dụng dùng nhiều `PlatformTransactionManager` hoặc nhiều datasource, xác định manager đang xử lý method qua `@Transactional(transactionManager = "...")` và tài nguyên thực tế.

Cũng không coi `NEVER` là biện pháp phân quyền. Code vẫn có thể truy cập database ngoài transaction, và một lời gọi bypass proxy sẽ không thực hiện propagation check. Bảo mật dữ liệu nằm ở quyền ứng dụng/database; transaction propagation là chính sách điều phối thực thi.

## 8. Các bẫy kỹ thuật khiến kết quả khác mong đợi

### 8.1. Self-invocation bỏ qua proxy

```java
public void outer() {
    inner(); // this.inner(), không qua proxy cho @Transactional(NEVER).
}

@Transactional(propagation = Propagation.NEVER)
public void inner() {
    // Trong proxy mode mặc định, interceptor không thấy self-invocation.
}
```

Đây là **đoạn minh họa**, không phải class Java đầy đủ. Nếu method outer ở trong cùng target bean, `this.inner()` gọi trực tiếp nội bộ, không đi qua Spring proxy. Điều kiện `NEVER` **không được áp dụng riêng** cho lời gọi này; nếu outer đang có T1, code inner có thể thực thi trong T1 mà không ném propagation exception. Cách sửa rõ ràng là tách inner sang Spring bean khác và inject proxy, như lab.

### 8.2. Object được `new` ngoài container

Mã `new StrictService(jdbc)` tạo một target Java thường; annotation `@Transactional` trên class không tự chạy transaction interceptor. Nếu caller giữ raw instance, `NEVER` có thể hoàn toàn không kiểm tra T1. Dùng `ApplicationContext.getBean(...)` hoặc constructor injection từ Spring để caller giữ bean/proxy thích hợp. Một caller tự tạo bằng `new` vẫn có thể sử dụng đúng semantics nếu **callee reference là proxy**.

### 8.3. Transaction infrastructure ở sai ApplicationContext

Trong proxy mode, `@EnableTransactionManagement` đăng ký transaction advice tại `ApplicationContext` chứa cấu hình. Nếu bean service được root context quản lý nhưng hạ tầng chỉ bật ở child của `DispatcherServlet`, child không tự proxy lại bean root. Xác minh context nào thực sự **tạo bean**, không chỉ nơi một controller nhìn thấy nó.

### 8.4. Private/final method và JDK proxy

Class-based proxy không intercept private method theo cách thông thường và không override được final method; JDK dynamic proxy chỉ áp dụng cho interface methods phù hợp. Chọn public Spring service methods gọi **qua proxy** làm ranh giới transaction dễ hiểu. Khi dùng `AdviceMode.ASPECTJ` weaving, hạn chế khác, nhưng bài này nói về **Spring AOP proxy mode phổ biến**.

### 8.5. Test đã mở transaction sẵn

Spring Test có thể tự mở test-managed transaction nếu test method mang `@Transactional`. Khi gọi bean `NEVER` trong test đó, exception là **hành vi đúng** do transaction đang tồn tại, dù cùng lời gọi từ main không có T1 sẽ chạy bình thường. Viết hai test có/không có outer transaction; kiểm tra exception type và trạng thái DB sau boundary. Tránh xóa annotation `NEVER` chỉ để test không lỗi nếu contract thực sự yêu cầu không có transaction.

### 8.6. Bắt lỗi không có nghĩa tự động rollback-only

Một `IllegalTransactionStateException` xuất phát từ intercept của `NEVER` **trước khi tham gia T1**. Nếu outer bắt và return bình thường, transaction của outer có thể commit. Nếu outer không bắt, unchecked exception đi qua outer interceptor khiến T1 rollback theo default policy. Cả hai kết quả đã được chứng minh trong demo. Không nhầm với `UnexpectedRollbackException` phát sinh lúc outer commit một transaction đã bị một participating `REQUIRED` scope đánh dấu rollback-only.

### 8.7. Transaction flag và thread context

`TransactionSynchronizationManager.isActualTransactionActive()` là công cụ chẩn đoán hữu ích cho JDBC thread-bound transactions, nhưng không phải giải pháp thay thế việc chọn đúng manager và kiểm thử kết quả. Với reactive R2DBC, Spring transaction thường dựa vào Reactor Context; với `@Async`/`CompletableFuture`, transaction imperative gắn thread không tự lan sang thread mới. Không dùng một cờ thread đơn lẻ để quyết định propagation của mọi transaction system.

## 9. Áp dụng bằng `TransactionTemplate`

Ngoài declarative annotation, có thể yêu cầu chính sách tương đương bằng transaction API:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_NEVER
);

template.executeWithoutResult(status -> {
    performNonTransactionalWork();
});
```

Đây là **mã minh họa**, giả định `transactionManager` và `performNonTransactionalWork()` đã tồn tại, cần import `TransactionTemplate` và `TransactionDefinition`. Nếu manager không thấy transaction hiện hành, callback chạy mà không có physical transaction mới. Nếu có T1, `IllegalTransactionStateException` xảy ra **trước callback**, không có bước «suspend T1 rồi chạy callback».

Template hữu ích khi ranh giới cần nằm ngay trong một đoạn code thay vì một public Spring bean method. Nhưng nó vẫn không thể phát hiện mọi database transaction ngoài manager, và không khiến nhiều câu SQL không transaction có atomicity.

## 10. Thử nghiệm và câu hỏi tự kiểm tra

| Scenario | Body `NEVER` chạy? | Outer T1 có thể commit? | Kết quả cần quan sát |
| --- | --- | --- | --- |
| Gọi `NEVER` trực tiếp qua proxy, không có T1 | Có | Không có T1 | `never=1` |
| Outer T1 gọi `NEVER` rồi catch | Không | Có thể, nếu nghiệp vụ/rollback rule cho phép | `outer=1, never=0` |
| Outer T1 gọi `NEVER` và để lỗi lan ra | Không | Theo mặc định rollback | `outer=0, never=0` |
| Outer T1 gọi `NOT_SUPPORTED` rồi outer rollback | Body `NEVER` không liên quan; `NOT_SUPPORTED` body chạy | T1 rollback | Ghi `not_supported` ngoài T1 vẫn tồn tại |

Bài tập:

1. Đổi `Propagation.NEVER` ở `StrictService.mustRunOutside()` thành `NOT_SUPPORTED`. Dự đoán method body có chạy khi outer T1 tồn tại không; điều gì xảy ra với `never` nếu outer rollback?
2. Đổi sang `MANDATORY` rồi gọi từ main khi không có T1. Giải thích vì sao exception xảy ra ở tình huống đối lập với `NEVER`.
3. Bỏ `@EnableTransactionManagement` khỏi bản sao demo. Thử dự đoán vì sao các annotations có thể không được áp dụng dù vẫn xuất hiện trong source code.
4. Chuyển method `NEVER` sang cùng `OuterService` và gọi `this.mustRunOutside()`. So sánh behavior với lời gọi qua bean proxy khác.
5. Đánh dấu một test với `@Transactional` và gọi `NEVER`. Giải thích vì sao test báo lỗi trong khi lần gọi từ main không transaction lại chạy.
6. Xây test case có hai datasource/transaction managers; xác định manager nào xử lý `NEVER` và vì sao không nên suy rộng rằng nó bắt được mọi transaction hệ thống.

**Đáp án cốt lõi cần nhớ:** `Propagation.NEVER` **chỉ cho phép method chạy khi không có transaction hiện hành mà Spring transaction manager thấy được**. Nếu có transaction, nó **ném `IllegalTransactionStateException` trước khi chạy thân method**. Khi cần **suspend transaction để vẫn thực hiện inner**, dùng `NOT_SUPPORTED`; khi cần **tạo physical transaction mới độc lập**, dùng `REQUIRES_NEW`. Không nhầm ba cơ chế này.

## 11. Tài liệu tham khảo chính thức

- [Spring Framework — `Propagation` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Propagation.html): định nghĩa `NEVER`, `NOT_SUPPORTED`, `MANDATORY` và các propagation khác.
- [Spring Framework — `TransactionDefinition` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html): điều kiện transaction hiện hành và các hằng propagation.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): interceptor và transaction boundaries.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): cấu hình annotation, proxy interception.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): dùng `TransactionTemplate`.
