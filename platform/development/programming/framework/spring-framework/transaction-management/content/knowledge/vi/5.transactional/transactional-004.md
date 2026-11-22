# Giá trị mặc định của propagation, isolation và readOnly trong `@Transactional`

> **Spring Framework — Transaction Management → `@Transactional`.** Khi viết `@Transactional` mà không truyền tham số, Spring sẽ xử lý một giao dịch ra sao? Bài học giải thích ba giá trị mặc định, cách chúng tương tác khi phương thức có giao dịch lồng nhau, và cách kiểm tra bằng ví dụ Java 17+ có thể chạy độc lập.

## 1. Ba giá trị mặc định cần nhớ

Với annotation `org.springframework.transaction.annotation.Transactional`, ba thuộc tính đang xét mặc định là:

| Thuộc tính | Giá trị mặc định | Ý nghĩa ngắn gọn |
| --- | --- | --- |
| `propagation` | `Propagation.REQUIRED` | Tham gia transaction hiện có; nếu chưa có thì bắt đầu transaction mới. |
| `isolation` | `Isolation.DEFAULT` | Dùng mức isolation mặc định mà tài nguyên/transaction manager cung cấp; không ép một mức cụ thể như `SERIALIZABLE`. |
| `readOnly` | `false` | Không yêu cầu xử lý giao dịch theo chế độ chỉ đọc; về mặc định là read-write. |

Hai cách khai báo dưới đây có **cùng ba giá trị**:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void placeOrder() {
    // Nghiệp vụ sử dụng tài nguyên thuộc transaction manager.
}
```

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.DEFAULT,
    readOnly = false
)
public void placeOrder() {
    // Với ba thuộc tính trên, tương đương @Transactional không tham số.
}
```

Hai đoạn này là **fragment** của phương thức trong Spring bean, chưa phải một chương trình Java độc lập. Cần cấu hình transaction management, transaction manager phù hợp và gọi qua Spring proxy để hành vi declarative thực sự có hiệu lực.

**Quy tắc thực hành:** “Giá trị mặc định của annotation” khác “giá trị vật lý đang có hiệu lực trong database”. `REQUIRED` có thể *tham gia transaction đã mở*, `DEFAULT` kế thừa cấu hình isolation hiện hữu, còn `readOnly=false` ở một phương thức tham gia có thể không thay đổi tính chất read-only của transaction bên ngoài.

## 2. `Propagation.REQUIRED`: tham gia hoặc mở transaction

### Không có transaction bên ngoài

Một lời gọi `@Transactional` được Spring intercept sẽ khiến manager bắt đầu transaction mới khi chưa có transaction tương ứng.

```text
Controller / caller (chưa có transaction)
       |
       v
@Transactional mặc định: Service.placeOrder()
       |
       +-- transaction manager bắt đầu T1
       +-- SQL 1
       +-- SQL 2
       +-- kết thúc bình thường => COMMIT T1
       |
       +-- lỗi phải rollback => ROLLBACK T1
```

Với `JdbcTransactionManager`/`DataSourceTransactionManager`, manager điều phối JDBC `Connection` liên quan. Với `JpaTransactionManager`, manager điều phối JPA `EntityManager` và resource tương ứng. `@Transactional` không tự chọn lại manager chỉ dựa vào tên bảng/SQL trong thân hàm.

### Đã có transaction bên ngoài

Một method khác đang có transaction T1 và gọi method mặc định `REQUIRED` qua Spring proxy, dùng cùng manager/tài nguyên:

```text
outer() @Transactional             [logical scope outer]
  |
  +-- bắt đầu transaction vật lý T1
  +-- INSERT A
  |
  +-- inner() @Transactional      [logical scope inner]
  |     +-- tham gia T1 (không tạo transaction vật lý thứ hai)
  |     +-- INSERT B
  |
  +-- COMMIT/ROLLBACK T1 cho cả A và B
```

**Mỗi method có thể có logical transaction scope riêng, nhưng thường cùng một physical transaction** khi `REQUIRED` tham gia cùng transaction manager. Đây là lý do một lỗi ở inner có thể khiến cả thao tác outer rollback.

Không nên hiểu “method nào cũng có `@Transactional` thì method nào cũng tự commit”. Với `REQUIRED`, inner kết thúc thành công chỉ hoàn thành phạm vi logic của nó; commit vật lý vẫn thuộc ranh giới transaction ngoài cùng.

### Khi inner đặt transaction thành rollback-only

Giả sử inner có lỗi phải rollback; Spring đánh dấu transaction chung là `rollback-only`. Nếu outer bắt exception rồi cố kết thúc bình thường, transaction **vẫn không thể commit**. Khi outer cố commit, Spring có thể ném `UnexpectedRollbackException` để báo rằng kết quả thực tế là rollback.

```java
@Service
class InnerService {
    @Transactional
    public void inner() {
        throw new IllegalStateException("invalid");
    }
}

@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        try {
            inner.inner();
        } catch (IllegalStateException ignored) {
            // Bắt exception ở đây không tự xóa rollback-only của T1.
        }
        // Khi outer kết thúc, commit có thể báo UnexpectedRollbackException.
    }
}
```

Đây là fragment minh họa, cần import `@Service`/`@Transactional` và một ứng dụng có transaction manager. Việc phát sinh `UnexpectedRollbackException` phụ thuộc vào giao dịch đang được quản lý và lúc nào rollback-only được xác lập; không dùng fragment này làm chương trình độc lập.

### Đối chiếu nhanh các propagation khác

| Propagation | Nếu đã có transaction | Nếu chưa có transaction |
| --- | --- | --- |
| `REQUIRED` *(mặc định)* | Tham gia transaction có sẵn | Bắt đầu mới |
| `REQUIRES_NEW` | Tạm treo transaction ngoài và tạo transaction vật lý độc lập | Bắt đầu mới |
| `SUPPORTS` | Tham gia | Có thể chạy không có transaction thực |
| `MANDATORY` | Tham gia | Báo lỗi |
| `NOT_SUPPORTED` | Tạm treo transaction ngoài, chạy không có transaction | Chạy không có transaction |
| `NEVER` | Báo lỗi | Chạy không có transaction |
| `NESTED` | Dùng nested boundary/savepoint nếu manager hỗ trợ | Thường hành xử tương tự tạo transaction mới |

Bảng mô tả ý nghĩa tổng quát của propagation; hỗ trợ `NESTED`, hành vi tạm treo và chi tiết kỹ thuật phụ thuộc `PlatformTransactionManager` thực tế. Trong bài này, cần nắm vững **`REQUIRED` là mặc định** và không suy diễn rằng transaction mới luôn được tạo.

## 3. `Isolation.DEFAULT`: chọn mức cô lập hiệu lực như thế nào?

**Isolation là chính sách kiểm soát việc transaction nhìn thấy dữ liệu được đọc/ghi bởi transaction khác.** Isolation ảnh hưởng hiện tượng đọc bẩn, non-repeatable read, phantom read và xung đột đồng thời, nhưng không tự thay thế chiến lược khóa hay xử lý lỗi cạnh tranh.

`Isolation.DEFAULT` có nghĩa: **Spring không yêu cầu ép một isolation level cụ thể cho transaction mới**. Mức hiệu lực đến từ kết nối, cơ sở dữ liệu, cấu hình connection pool và transaction manager.

Ví dụ về các isolation level thường gặp:

| Giá trị trên Spring | Ý nghĩa khái quát |
| --- | --- |
| `DEFAULT` *(mặc định)* | Dùng mức có sẵn từ underlying resource/database. |
| `READ_UNCOMMITTED` | Cho phép mức cô lập yếu; khả năng quan sát dữ liệu chưa commit phụ thuộc DBMS. |
| `READ_COMMITTED` | Tránh dirty read theo mô hình mức cô lập SQL phổ biến. |
| `REPEATABLE_READ` | Bảo đảm đọc lặp lại theo chính sách DBMS; cách xử lý phantom phụ thuộc hệ quản trị/triển khai. |
| `SERIALIZABLE` | Mạnh nhất trong các mức JDBC chuẩn, nhưng có thể gây chờ, deadlock hoặc lỗi serialization cần retry. |

Đừng gán mặc định của Spring cho một con số JDBC cố định. Ví dụ, PostgreSQL thường có database default là `READ COMMITTED`, còn MySQL InnoDB thường là `REPEATABLE READ`; cấu hình máy chủ/connection có thể thay đổi. Do đó hai ứng dụng cùng dùng `@Transactional` có thể có mức cô lập hiệu lực khác nhau.

### Vì sao `DEFAULT` không tương đương `READ_COMMITTED`?

```java
@Transactional(isolation = Isolation.DEFAULT)
public void updateA() { /* ... */ }

@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateB() { /* ... */ }
```

- `updateA()` không đòi mức cô lập riêng. Nếu connection đang được cấu hình `SERIALIZABLE` thì “DEFAULT” không có nghĩa tự hạ về `READ_COMMITTED`.
- `updateB()` yêu cầu mức `READ_COMMITTED` **khi Spring bắt đầu transaction mới** và transaction manager/database hỗ trợ mức đó.
- Nếu hai phương thức **tham gia một transaction đã có** bằng `REQUIRED`, isolation hiệu lực của transaction ngoài thường được giữ nguyên. Annotation đặt trên inner không tự đổi isolation của transaction đang hoạt động.

### Lưu ý khi tham gia transaction ngoài

Theo chính sách lenient mặc định của Spring transaction manager, một inner `@Transactional(isolation = Isolation.SERIALIZABLE)` tham gia transaction `READ_COMMITTED` bằng `REQUIRED` thường vẫn chạy với isolation của transaction ngoài; yêu cầu inner không tự tạo một physical transaction khác để áp dụng mức mới.

Có thể bật `validateExistingTransaction` trên các manager kế thừa `AbstractPlatformTransactionManager` để yêu cầu từ chối mismatch isolation khi tham gia transaction có sẵn:

```java
// Fragment cấu hình, khi đang tạo JDBC transaction manager.
JdbcTransactionManager manager =
        new JdbcTransactionManager(dataSource);
manager.setValidateExistingTransaction(true);
```

Khi strict validation được bật, việc tham gia với isolation level không tương thích có thể bị từ chối, giúp phát hiện cấu hình sai sớm. Đây là validation ở manager, không phải một cách để inner thay đổi isolation vật lý của outer.

### Khi nào chủ động chỉ rõ isolation?

Cân nhắc khi nghiệp vụ có yêu cầu concurrency cụ thể và đã hiểu database:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void reserveUniqueResource() {
    // Chỉ một ví dụ khai báo; cần kiểm tra đặc tính DB và cơ chế retry.
}
```

`SERIALIZABLE` không tự biến nghiệp vụ thành “không bao giờ thất bại”; database có thể yêu cầu retry khi transaction bị hủy do tranh chấp/serialization failure. Chọn isolation nên dựa trên invariant, tải thực tế và transaction manager/DBMS, thay vì mặc định nâng mọi transaction lên mức mạnh nhất.

## 4. `readOnly=false`: read-write mặc định không đồng nghĩa “có lệnh ghi”

`@Transactional(readOnly = false)` là khai báo **không yêu cầu chế độ chỉ đọc** của transaction. Đây là giá trị mặc định.

Nó **không** có nghĩa:

- Phương thức bắt buộc phải ghi dữ liệu.
- Spring sẽ tự động kiểm tra rằng method có `INSERT`/`UPDATE`.
- Database bỏ qua mọi quyền truy cập, ràng buộc, lock hoặc cấu hình chỉ đọc của connection.
- Một inner method mặc định `readOnly=false` có thể chuyển transaction read-only đã được outer mở thành read-write.
- Một transaction read-write không thể chỉ thực hiện `SELECT`; thực tế rất nhiều truy vấn chỉ đọc vẫn hoạt động hoàn toàn bình thường.

Ví dụ:

```java
@Transactional // readOnly = false
public Account findAccount(long id) {
    return repository.findById(id).orElseThrow();
}
```

Đây là fragment, dùng `Account` và `repository` giả định. Dù chỉ truy vấn, method trên vẫn yêu cầu transaction read-write theo metadata mặc định. Điều này không làm truy vấn sai, nhưng với JPA, chỉ rõ `readOnly=true` khi phù hợp có thể cho provider cơ hội tối ưu, tùy cấu hình.

### Đổi sang `readOnly=true` thì sao?

```java
@Transactional(readOnly = true)
public Account findAccount(long id) {
    return repository.findById(id).orElseThrow();
}
```

- Với JDBC, transaction manager có thể gọi `Connection.setReadOnly(true)`, thường được driver coi là hint; cấu hình riêng có thể khiến một số database enforce read-only bằng SQL.
- Với JPA/Hibernate, Spring có thể tối ưu flush behavior và quản lý dirty checking tùy framework/provider/version.
- Một database/driver có thể cho phép ghi, từ chối ghi hoặc ứng xử khác trong read-only transaction. **Không coi `readOnly=true` là rào chắn quyền ghi hoặc quy tắc bảo mật tuyệt đối.**
- Khi method chỉ **tham gia** transaction outer đã tồn tại bằng `REQUIRED`, `readOnly=true` tại inner không tự biến transaction ngoài thành read-only.

Vì vậy, mặc định `readOnly=false` nghĩa là *không gửi read-only request từ metadata này*. Nó không phải lệnh “bật quyền ghi” cho tất cả resource.

### Isolation và readOnly cần quan tâm lúc transaction bắt đầu

Các thuộc tính `isolation`, `timeout`, `readOnly` trong annotation chủ yếu có hiệu lực khi transaction manager bắt đầu transaction vật lý mới với propagation như `REQUIRED` (nếu chưa có transaction) hoặc `REQUIRES_NEW`. Với `REQUIRED` tham gia transaction hiện hành, đặc tính vật lý do transaction đang có quyết định.

Nếu bật `validateExistingTransaction=true`, một số mismatch (đặc biệt inner read-write cố tham gia outer read-only) có thể bị từ chối thay vì chỉ dùng ngầm cấu hình outer. Đây là lý do không nên giả định các annotation ở mọi tầng đều độc lập quyết định readOnly/isolation.

## 5. Ba thuộc tính cùng hoạt động như thế nào?

Bảng dưới giả định các method được gọi **qua Spring proxy**, dùng cùng transaction manager, resource phù hợp và không có hành vi tùy chỉnh từ driver/provider.

| Bối cảnh | `REQUIRED` làm gì? | Isolation hiệu lực | Read-only hiệu lực |
| --- | --- | --- | --- |
| Method mặc định được gọi khi chưa có T1 | Tạo T1 | Mức hiện hành/mặc định của resource | Read-write request (`false`) |
| Method mặc định được gọi khi outer T1 đang hoạt động | Tham gia T1 | Theo T1; không tự tạo isolation mới | Theo T1 |
| Outer T1 là `readOnly=true`, inner mặc định `readOnly=false` | Inner tham gia T1 | Theo T1 | T1 vẫn read-only theo cấu hình outer |
| Outer T1 dùng `SERIALIZABLE`, inner mặc định `DEFAULT` | Inner tham gia T1 | Vẫn `SERIALIZABLE` của T1 | Theo T1 |
| Inner yêu cầu `READ_COMMITTED` nhưng T1 đang `SERIALIZABLE` | Inner tham gia T1 | Thường vẫn theo T1; có thể lỗi nếu strict validation | Theo T1 |
| Method dùng `REQUIRES_NEW` | Tạo transaction vật lý mới, ngoài transaction bị tạm treo | Theo thuộc tính của transaction mới / resource default | Theo thuộc tính của transaction mới |

Một cách ghi nhớ:

```text
Khởi tạo transaction mới:
    REQUIRED (khi chưa có tx) ──> chọn isolation và readOnly cho tx mới
    REQUIRES_NEW               ──> chọn isolation và readOnly cho tx mới

Tham gia transaction hiện hành:
    REQUIRED (khi đã có tx) ────> dùng transaction hiện hành
                                      |
                                      +-- isolation hiện hành
                                      +-- readOnly hiện hành
                                      +-- commit/rollback vật lý chung
```

### Cẩn thận khi annotation ở class và method khác nhau

Annotation đặt trên method có độ ưu tiên cao hơn annotation trên class. Khi một method tự đặt `@Transactional` không tham số, nó dùng **các giá trị mặc định của annotation method**, thay vì tự cộng dồn từng thuộc tính chưa khai báo với annotation của class.

```java
@Transactional(readOnly = true)
@Service
public class ProductService {

    public Product view(long id) {
        // Kế thừa metadata @Transactional(readOnly = true) ở class.
        return repository.getReferenceById(id);
    }

    @Transactional // method override, readOnly=false theo mặc định
    public void edit(long id) {
        // Phương thức này có metadata read-write.
    }
}
```

Đây là fragment minh họa. Cách mô tả trên áp dụng khi Spring resolution chọn transaction attribute ở method; hoạt động thực tế vẫn phụ thuộc có transaction ngoài hay không. **Trong outer read-only T1, method `edit` mặc định `REQUIRED` vẫn tham gia T1**, nên không tự làm T1 read-write.

## 6. Ví dụ thực hành Java 17+: xác nhận defaults và rollback chung

Ví dụ hoàn chỉnh dùng Spring Framework 6.2.x, `JdbcTransactionManager` và H2 in-memory database. Hai Spring beans có `@Transactional` mặc định: method ngoài ghi dòng thứ nhất, method trong ghi dòng thứ hai, sau đó method ngoài ném `IllegalStateException`. Vì mặc định `REQUIRED`, cả hai INSERT tham gia cùng một transaction và được rollback.

Thêm một method riêng `@Transactional(readOnly=true)` để so sánh readOnly flag.

### 6.1. Tạo dự án

```text
transaction-defaults/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── TransactionDefaultsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>transaction-defaults</artifactId>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.TransactionDefaultsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Mã Java

Tạo tệp `src/main/java/dev/learning/TransactionDefaultsDemo.java`:

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionDefaultsDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:defaults;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        OuterService outerService(JdbcTemplate jdbc, InnerService inner) {
            return new OuterService(jdbc, inner);
        }

        @Bean
        ReadService readService(JdbcTemplate jdbc) {
            return new ReadService(jdbc);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void insertSecond() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    2, "inner");
            System.out.println(
                    "inner.active=" +
                    TransactionSynchronizationManager
                            .isActualTransactionActive());
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, InnerService inner) {
            this.jdbc = jdbc;
            this.inner = inner;
        }

        @Transactional
        public void saveThenFail() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    1, "outer");

            System.out.println(
                    "outer.active=" +
                    TransactionSynchronizationManager
                            .isActualTransactionActive());

            System.out.println(
                    "outer.readOnly=" +
                    TransactionSynchronizationManager
                            .isCurrentTransactionReadOnly());

            // Gọi qua một Spring bean khác để đi qua proxy.
            inner.insertSecond();

            throw new IllegalStateException("forced failure");
        }
    }

    public static class ReadService {
        private final JdbcTemplate jdbc;

        public ReadService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(readOnly = true)
        public int count() {
            System.out.println(
                    "readService.readOnly=" +
                    TransactionSynchronizationManager
                            .isCurrentTransactionReadOnly());
            return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM events", Integer.class);
        }
    }

    public static void main(String[] args) throws Exception {
        Transactional declaration =
                OuterService.class.getMethod("saveThenFail")
                        .getAnnotation(Transactional.class);

        System.out.println(
                "annotation.propagation=" +
                declaration.propagation());
        System.out.println(
                "annotation.isolation=" +
                declaration.isolation());
        System.out.println(
                "annotation.readOnly=" +
                declaration.readOnly());

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AppConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE events (
                        id INT PRIMARY KEY,
                        label VARCHAR(80) NOT NULL
                    )
                    """);

            try {
                context.getBean(OuterService.class).saveThenFail();
            } catch (IllegalStateException expected) {
                System.out.println(
                        "caught=" + expected.getMessage());
            }

            Integer remaining = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM events", Integer.class);
            System.out.println("rowsAfterRollback=" + remaining);

            int visible = context.getBean(ReadService.class).count();
            System.out.println("rowsFromReadService=" + visible);
        }
    }
}
```

**Chi tiết cấu hình đáng chú ý:**

- `@EnableTransactionManagement` kích hoạt xử lý `@Transactional` thông qua Spring transaction infrastructure.
- `JdbcTransactionManager` nhận đúng `DataSource` mà `JdbcTemplate` sử dụng; manager có thể gắn JDBC connection vào transaction hiện hành.
- `OuterService` và `InnerService` là hai beans khác nhau; lời gọi `inner.insertSecond()` đi qua Spring proxy, nên annotation của inner được xử lý.
- Code kiểm tra trực tiếp giá trị của annotation bằng Java reflection **không phụ thuộc database**. Còn `TransactionSynchronizationManager` kiểm tra trạng thái transaction mà Spring thiết lập khi method được thực thi.
- `ReadService` yêu cầu `readOnly=true` trong transaction riêng sau khi method outer đã rollback, cho thấy cờ read-only Spring quan sát được khác với mặc định `false`.
- Phần thử nghiệm rollback cố ý ném unchecked exception, nên cả hai dòng bị rollback.

### 6.3. Biên dịch và chạy

Cần cài **JDK 17+**, Maven 3.x và Internet để tải dependencies trong lần chạy đầu. Tại thư mục `transaction-defaults`:

```bash
mvn -q clean compile exec:java
```

**Các dòng chương trình in ra theo thứ tự** trong ví dụ (không tính log phụ từ Maven hoặc logging):

```text
annotation.propagation=REQUIRED
annotation.isolation=DEFAULT
annotation.readOnly=false
outer.active=true
outer.readOnly=false
inner.active=true
caught=forced failure
rowsAfterRollback=0
readService.readOnly=true
rowsFromReadService=0
```

Giải thích:

1. Reflection đọc annotation thực tế trên `saveThenFail()` và trả về đúng ba default.
2. `OuterService.saveThenFail()` được gọi qua bean proxy. Nó mở transaction T1, vì lúc này chưa có transaction trước đó.
3. `InnerService.insertSecond()` có propagation `REQUIRED`, nên tham gia T1. Hai INSERT không tạo hai transaction vật lý riêng.
4. Outer ném `IllegalStateException`. Theo rollback rules mặc định của Spring, T1 bị rollback. Truy vấn từ ngoài transaction sau đó thấy **0 hàng**.
5. `ReadService.count()` chạy ở transaction thứ hai, với cờ `readOnly=true`; dòng in `readService.readOnly=true` cho biết metadata mà Spring áp dụng, không phải bằng chứng rằng mọi lệnh ghi chắc chắn bị database chặn.

Nếu xóa dòng `throw new IllegalStateException(...)`, phương thức outer hoàn tất bình thường; với bảng trống lúc đầu, hai INSERT được commit và số hàng sau đó là 2. Đó là thay đổi kịch bản để tự thử, không phải output của bản code ở trên.

### 6.4. Vì sao ví dụ không in ra một isolation thực tế cố định?

Giá trị `annotation.isolation=DEFAULT` là **cài đặt của Spring metadata**. Isolation thực tế của JDBC connection có thể đọc ở runtime qua `Connection.getTransactionIsolation()`, nhưng con số trả về phụ thuộc H2/driver và cấu hình datasource. Không nên in một kết quả database cụ thể rồi gọi đó là “mặc định Spring”.

Muốn tự quan sát isolation hiệu lực của JDBC connection **đang tham gia transaction** bên trong một service sử dụng `JdbcTemplate`:

```java
// Fragment trong method thuộc Spring JDBC transaction.
Integer effectiveIsolation =
        jdbc.execute((org.springframework.jdbc.core.ConnectionCallback<Integer>)
                connection -> connection.getTransactionIsolation());

System.out.println("jdbcIsolation=" + effectiveIsolation);
```

Giá trị trả về là hằng số JDBC, chẳng hạn `Connection.TRANSACTION_READ_COMMITTED` (2) hoặc `Connection.TRANSACTION_REPEATABLE_READ` (4), tùy database và kết nối. Với ứng dụng thực tế, nên giải mã số thành tên hằng, và kiểm tra tài liệu của DBMS về chi tiết isolation.

## 7. Chủ động ghi đè defaults khi có yêu cầu nghiệp vụ

`@Transactional` không tham số nên là lựa chọn có cân nhắc. Khi cần tùy chỉnh, khai báo đúng thuộc tính của transaction boundary:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    readOnly = true
)
public ReportSummary buildIndependentReport() {
    // Fragment: sử dụng tài nguyên phù hợp của một transaction mới.
}
```

Ý nghĩa:

- `REQUIRES_NEW` yêu cầu transaction vật lý độc lập và tạm treo transaction ngoài.
- `READ_COMMITTED` yêu cầu một mức cô lập cụ thể cho transaction mới, nếu backend hỗ trợ.
- `readOnly=true` gửi hint chỉ đọc đến transaction infrastructure/backend; không tự bảo đảm mọi cơ chế ghi đều bị chặn.

Tuy nhiên, một truy vấn báo cáo dài không nhất thiết cần `REQUIRES_NEW`; propagation độc lập tốn thêm resource và connection. Nếu muốn đảm bảo không chạy trong một transaction hiện hữu, chọn propagation dựa trên yêu cầu thực tế, không chọn chỉ vì “đọc là phải tạo transaction mới”.

### Cấu hình readOnly ở class, override ở method

```java
@Service
@Transactional(readOnly = true)
public class InventoryService {

    public StockView find(long productId) {
        // Dùng readOnly=true từ class-level annotation.
    }

    @Transactional // readOnly=false; propagation=REQUIRED; isolation=DEFAULT
    public void reserve(long productId, int amount) {
        // Method-level annotation được ưu tiên.
    }
}
```

Fragment giả định đã khai báo `StockView`, chưa thể biên dịch độc lập. Một phương thức có annotation riêng nhận **trọn bộ default** cho các thuộc tính không nêu; không nên nghĩ rằng method annotation chỉ thay đổi đúng những thuộc tính có ghi ra.

### Đặt khác isolation ở inner không thay đổi transaction đang có

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outer() {
    inventoryService.inner();
}

@Transactional(isolation = Isolation.SERIALIZABLE)
public void inner() {
    // Với REQUIRED mặc định và cùng manager, thường vẫn dùng
    // physical transaction của outer ở READ_COMMITTED.
}
```

Đây là minh họa logic, trong ứng dụng thực tế hai phương thức phải được intercept đúng qua Spring proxy; inner không tự đổi isolation. Nếu bắt buộc có isolation mới, đánh giá `REQUIRES_NEW` và chi phí concurrency, hoặc bật strict validation để từ chối mismatch.

## 8. Những lỗi hiểu sai thường gặp

### Lỗi 1: “`REQUIRED` có nghĩa là cứ vào method lại mở một connection và transaction mới”

Sai. `REQUIRED` tham gia transaction hiện có nếu thích hợp. Một lời gọi service A → B cùng manager có thể gồm hai logical scopes nhưng một physical transaction. Số lượng `@Transactional` không suy ra số transaction commit vật lý.

### Lỗi 2: “`Isolation.DEFAULT` luôn là `READ_COMMITTED`”

Sai. `DEFAULT` là **không yêu cầu isolation riêng**, nên mức hiệu lực phụ thuộc DBMS/connection configuration. Đọc giá trị của connection, xác nhận bằng cấu hình datasource và tài liệu DBMS.

### Lỗi 3: “`readOnly=false` khiến Spring chặn `SELECT` hoặc buộc phải ghi”

Sai. `false` chỉ là không bật read-only transaction hint. `SELECT` có thể thực thi bình thường trong transaction read-write.

### Lỗi 4: “`readOnly=true` luôn ngăn `UPDATE`”

Không được giả định. Phần lớn API coi đây là hint; vài backend/config có thể enforce. Phải kiểm tra trên datastore/driver cụ thể. Quyền ghi an toàn phải dựa trên DB permissions, nghiệp vụ và thiết kế API.

### Lỗi 5: “Inner có `readOnly=false` thì outer `readOnly=true` chuyển thành read-write”

Sai trong trường hợp inner `REQUIRED` tham gia cùng physical transaction của outer. Flag của outer vẫn chi phối transaction vật lý. `validateExistingTransaction` có thể giúp phát hiện những bất tương thích rõ ràng.

### Lỗi 6: “Việc bắt lỗi ở outer đủ để transaction đã bị inner đánh dấu rollback-only commit được”

Sai. Khi inner scope đã đánh dấu physical transaction rollback-only, outer không thể sửa việc đó chỉ bằng cách catch exception. `UnexpectedRollbackException` bảo vệ caller khỏi hiểu nhầm một rollback là commit.

### Lỗi 7: “Gọi method `@Transactional` nội bộ trong cùng object sẽ luôn chạy advice”

Sai với Spring proxy mode mặc định:

```java
public void call() {
    save(); // self-invocation: không đi qua proxy.
}

@Transactional
public void save() {
    // Không được tự động intercept nếu được gọi qua this.save().
}
```

Tách transaction boundary sang bean khác, gọi qua proxy do Spring quản lý hoặc cân nhắc `TransactionTemplate` khi thích hợp.

### Lỗi 8: “Mọi exception đều mặc định rollback”

Trong cấu hình declarative mặc định, Spring rollback khi `RuntimeException` hoặc `Error` thoát khỏi boundary; checked `Exception` không mặc nhiên kích hoạt rollback. Nếu yêu cầu nghiệp vụ khác, dùng `rollbackFor` hoặc cấu hình rollback rules:

```java
@Transactional(rollbackFor = Exception.class)
public void importData() throws Exception {
    // Kể cả checked Exception thoát ra cũng yêu cầu rollback.
}
```

Lỗi này liên quan trực tiếp đến `REQUIRED`: khi nhiều lệnh tham gia cùng một transaction nhưng lỗi không khiến rollback, transaction có thể commit ngoài dự kiến.

### Lỗi 9: “`@Transactional` ở method luôn kiểm soát isolation/readOnly, dù không có transaction manager”

Annotation là metadata. Cần Spring infrastructure đang hoạt động, method được intercept, manager phù hợp và resource tham gia. Nếu tự `new Service()` thay vì dùng Spring bean, hoặc gọi self-invocation, các defaults không tự trở thành hiệu ứng database.

### Lỗi 10: “Bên trong reactive pipeline có thể áp dụng nguyên xi kiểm tra ThreadLocal JDBC”

`PlatformTransactionManager` imperative thường gắn trạng thái vào thread; `ReactiveTransactionManager` dùng Reactor `Context`. Với R2DBC, cần reactive chain và manager tương ứng. Đừng dùng `TransactionSynchronizationManager` imperative để kết luận trạng thái transaction R2DBC theo cùng cách.

## 9. Cách kiểm tra defaults trong ứng dụng thực tế

### Kiểm tra annotation, không nhầm với trạng thái runtime

Dùng reflection như ví dụ runnable mục 6 cho biết ba giá trị **được khai báo trên method**. Nếu annotation nằm trên class hay được tạo qua meta-annotation, dùng Spring transaction attribute resolution thay vì chỉ gọi `getAnnotation` trên method.

```java
// Fragment: method và targetClass đã được xác định.
var source =
        new org.springframework.transaction.annotation
                .AnnotationTransactionAttributeSource();

var attributes = source.getTransactionAttribute(method, targetClass);

System.out.println(attributes.getPropagationBehavior());
System.out.println(attributes.getIsolationLevel());
System.out.println(attributes.isReadOnly());
```

Fragment yêu cầu `java.lang.reflect.Method method` và `Class<?> targetClass` phù hợp; khi không có transactional metadata, `getTransactionAttribute` có thể trả `null`. Các giá trị phản ánh Spring attribute resolution; vẫn phải phân biệt với **physical transaction** đang chạy.

### Kiểm tra trạng thái transaction hiện hành (imperative)

Bên trong method chạy thực sự qua Spring transaction advice:

```java
boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
Integer configuredIsolation =
        TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();
```

`configuredIsolation` có thể là `null` nếu không có isolation riêng được Spring gắn vào transaction. **`null` không có nghĩa database đang “không có isolation”**; muốn biết con số JDBC đang dùng thì phải hỏi connection trong transaction.

### Kiểm tra bằng integration test

- Gọi outer từ một bean khác qua proxy và quan sát transaction được kích hoạt.
- Trong một transaction, thực hiện hai INSERT rồi ném unchecked exception: xác minh cả hai rollback.
- Kiểm tra `readOnly` flag của Spring ở method mặc định và method `readOnly=true`; tránh dùng “INSERT không lỗi” làm bài test duy nhất cho readOnly.
- Thiết lập isolation rõ ràng cho transaction mới và đọc `Connection.getTransactionIsolation()`; chỉ dùng DBMS/driver hỗ trợ.
- Gọi inner `REQUIRED` bên trong outer read-only, xác nhận transaction thực tế không tự đổi thành read-write.
- Thử trường hợp inner đánh dấu rollback-only và outer bắt lỗi; kiểm tra xử lý `UnexpectedRollbackException`.
- Nếu có nhiều datasource/transaction managers, xác nhận đúng manager đang quản lý đúng resource; annotation defaults không tạo distributed transaction.

Lưu ý đặc biệt với **Spring TestContext**: transaction do test framework quản lý có quy định riêng về những annotation attributes được hỗ trợ; không dùng test method có `@Transactional(isolation=..., readOnly=...)` rồi suy ra tất cả các thuộc tính đều được TestContext áp dụng. Hãy kiểm tra thực tế trong service integration test và tài liệu testing.

## 10. Một checklist ngắn cho code review

| Câu hỏi | Kiểm tra gì? |
| --- | --- |
| Method có thực sự được intercept? | Spring bean/proxy, không phải self-invocation; `@EnableTransactionManagement` hoặc auto-configuration. |
| Ai là transaction manager? | Đúng `PlatformTransactionManager`/`ReactiveTransactionManager` và resource/factory. |
| `REQUIRED` đang tạo mới hay tham gia? | Có transaction outer tương ứng trước method không? |
| `DEFAULT` cho isolation hiệu lực bao nhiêu? | Connection và database configuration; không suy từ annotation. |
| `readOnly=false` có đúng mục đích? | Nếu chỉ đọc, có lợi ích từ `readOnly=true` không; provider có hỗ trợ hint không? |
| Một inner annotation có mâu thuẫn outer? | Mặc định inner thường theo thuộc tính vật lý outer; cân nhắc `validateExistingTransaction`. |
| Lỗi có rollback theo đúng yêu cầu? | Unchecked/checked exception, exception bị bắt/nuốt, rollback-only, propagation. |
| Giao dịch có phạm vi quá dài? | Chỉ giữ transaction mở trong khoảng công việc cần atomicity. |

## 11. Câu hỏi tự kiểm tra

**Câu 1:** `@Transactional` không tham số có bắt buộc mở transaction mới không?

*Đáp án:* Không. `REQUIRED` tham gia transaction hiện hành nếu có, và chỉ tạo mới khi chưa có transaction phù hợp.

**Câu 2:** Hai database dùng hai isolation defaults khác nhau. Có thể cả hai đều đúng với `@Transactional(isolation=DEFAULT)` không?

*Đáp án:* Có. `DEFAULT` không áp đặt một mức cô lập cụ thể; mức hiệu lực phụ thuộc underlying resource.

**Câu 3:** Outer `@Transactional(readOnly=true)` gọi inner `@Transactional` mặc định qua Spring proxy. Inner có bảo đảm được ghi không?

*Đáp án:* Không. Với `REQUIRED`, inner tham gia transaction outer, nên tính chất physical read-only từ outer vẫn có thể chi phối; hành vi chặn ghi tùy backend.

**Câu 4:** Method chỉ chạy `SELECT` mà annotation mặc định `readOnly=false` có sai cú pháp không?

*Đáp án:* Không. `readOnly=false` không cấm `SELECT`. Có thể chỉ rõ `readOnly=true` khi phù hợp để truyền hint tối ưu.

**Câu 5:** Tại sao outer vẫn gặp `UnexpectedRollbackException` dù đã catch lỗi của inner?

*Đáp án:* Inner đã khiến physical transaction chung bị đánh dấu rollback-only; catch exception không tự khôi phục khả năng commit của transaction.

**Câu 6:** Đặt `isolation=SERIALIZABLE` ở inner `REQUIRED` có tự nâng isolation của outer đang dùng `READ_COMMITTED` không?

*Đáp án:* Thường không. Inner tham gia physical transaction đã tồn tại; strict validation có thể từ chối mismatch. Muốn transaction mới với isolation riêng phải thiết kế ranh giới phù hợp, chẳng hạn `REQUIRES_NEW` và resource hỗ trợ.

## 12. Kết luận cần thuộc

- **`propagation=REQUIRED`:** dùng transaction đang có hoặc mở một transaction mới nếu chưa có.
- **`isolation=DEFAULT`:** không yêu cầu một isolation level cố định; giá trị thực tế do transaction/database/connection quyết định.
- **`readOnly=false`:** mặc định là read-write, không phải bắt buộc ghi dữ liệu và không tự xóa read-only của transaction ngoài.
- Với **inner `REQUIRED`**, isolation/readOnly vật lý thường theo transaction ngoài. Muốn thay đổi ranh giới phải xem propagation và manager, không chỉ thêm annotation.
- Kiểm chứng bằng transaction manager phù hợp, Spring proxy, integration tests và quan sát resource thực tế.

## Tài liệu tham khảo chính thức

1. [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): danh sách defaults, precedence giữa class/method và các thuộc tính annotation.
2. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, logical/physical transactions, rollback-only, `REQUIRES_NEW`.
3. [Spring Framework — `@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): default cụ thể của `propagation`, `isolation` và `readOnly`.
4. [Spring Framework — `TransactionDefinition`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html): các hằng propagation/isolation/timeout và ý nghĩa transaction settings.
5. [Spring Framework — `AbstractPlatformTransactionManager`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `validateExistingTransaction`, participating scopes và transaction synchronization.
6. [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): các giới hạn riêng của `@Transactional` trong Spring TestContext.
