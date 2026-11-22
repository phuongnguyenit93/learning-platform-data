# Phân biệt `org.springframework.transaction.annotation.Transactional` với `jakarta.transaction.Transactional`

## 1. Hai annotation cùng tên, hai API khác nhau

Khi làm việc với Spring Framework, bạn có thể gặp hai cách import `@Transactional`:

```java
import org.springframework.transaction.annotation.Transactional;
```

```java
import jakarta.transaction.Transactional;
```

**Cả hai có thể khai báo ranh giới giao dịch của một Spring bean.** Spring Framework hỗ trợ annotation chuẩn `jakarta.transaction.Transactional` như một lựa chọn thay thế cho annotation của mình. Tuy vậy, **cùng tên không có nghĩa là cùng bộ thuộc tính**: Spring cung cấp các tùy chọn riêng về isolation, timeout, read-only, chọn transaction manager và `NESTED`; Jakarta dùng `TxType`, `rollbackOn` và `dontRollbackOn`.

- **Spring `@Transactional`** thuộc API Spring, thích hợp cho ứng dụng sử dụng sâu Spring Transaction Management.
- **Jakarta `@Transactional`** thuộc chuẩn Jakarta Transactions (JTA), được thiết kế để dùng với Jakarta EE/CDI managed components. Khi được xử lý trong ứng dụng Spring, nó vẫn đi qua Spring transaction infrastructure.
- **Annotation không quyết định loại transaction manager.** Sử dụng annotation Jakarta trong Spring với `JdbcTransactionManager` vẫn là một giao dịch JDBC cục bộ; không tự tạo XA/2-phase commit.

Trong bài này, ta so sánh ngữ nghĩa của hai annotation **trong Spring Framework 6.x** và chỉ rõ những điểm xuất phát từ tiêu chuẩn Jakarta EE.

## 2. Bảng so sánh nhanh

| Tiêu chí | `org.springframework.transaction.annotation.Transactional` | `jakarta.transaction.Transactional` |
| --- | --- | --- |
| Xuất xứ | Spring Framework | Jakarta Transactions |
| Default propagation | `Propagation.REQUIRED` | `TxType.REQUIRED` |
| Thuộc tính propagation | `propagation = Propagation.REQUIRES_NEW` | `value = TxType.REQUIRES_NEW` |
| Các kiểu propagation | `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED`, `NEVER`, `NESTED` | Sáu giá trị đầu; **không có `NESTED`** |
| Isolation level | Có `isolation`, ví dụ `Isolation.READ_COMMITTED` | Không có thuộc tính tương ứng |
| Timeout | Có `timeout` và `timeoutString` | Không có thuộc tính tương ứng |
| Read-only | Có `readOnly` | Không có thuộc tính tương ứng |
| Chọn manager theo phương thức | Có `transactionManager` hoặc `value` (String) | Không có thuộc tính chỉ định Spring transaction manager |
| Rollback với exception | `rollbackFor` | `rollbackOn` |
| Không rollback với exception | `noRollbackFor` | `dontRollbackOn` |
| Rule theo tên exception | Có `rollbackForClassName` và `noRollbackForClassName` | Không có |
| Transaction labels | Có `label` | Không có |
| Composed annotation theo Spring | Hỗ trợ meta-annotation tùy biến | Không cung cấp cùng API Spring-specific |
| Áp dụng trên Spring bean | Spring AOP proxy hoặc cơ chế AspectJ được cấu hình | Spring đọc metadata của Jakarta annotation rồi dùng transaction infrastructure tương ứng |
| Trong Jakarta EE/CDI | Không phải interceptor binding chuẩn của Jakarta Transactions | Là interceptor binding chuẩn cho CDI/managed bean |

**Điểm dễ sai nhất:** tên `value` có ý nghĩa khác hẳn nhau.

```java
// Spring: value (hoặc transactionManager) là String chọn manager.
@org.springframework.transaction.annotation.Transactional("ordersTx")
public void springWork() {
    System.out.println("Spring transaction manager: ordersTx");
}

// Jakarta: value là enum TxType, không phải tên manager.
@jakarta.transaction.Transactional(
        jakarta.transaction.Transactional.TxType.REQUIRES_NEW)
public void jakartaWork() {
    System.out.println("Jakarta TxType: REQUIRES_NEW");
}
```

Đây là **hai phương thức minh họa cú pháp**, chưa phải chương trình độc lập. `ordersTx` cần tồn tại trong Spring context. Nếu dùng Jakarta annotation rồi cố viết `value = "ordersTx"`, code sẽ không biên dịch.

## 3. Đối chiếu `Propagation` với `TxType`

| Spring `Propagation` | Jakarta `TxType` | Hành vi mong muốn |
| --- | --- | --- |
| `REQUIRED` | `REQUIRED` | Có transaction thì tham gia; chưa có thì bắt đầu transaction mới. |
| `REQUIRES_NEW` | `REQUIRES_NEW` | Tạm treo transaction hiện tại và bắt đầu transaction độc lập nếu có hỗ trợ. |
| `SUPPORTS` | `SUPPORTS` | Có transaction thì tham gia; không có thì tiếp tục chạy ngoài transaction. |
| `MANDATORY` | `MANDATORY` | Phải có transaction sẵn; nếu không thì lỗi. |
| `NOT_SUPPORTED` | `NOT_SUPPORTED` | Chạy ngoài transaction, tạm treo transaction hiện tại khi có. |
| `NEVER` | `NEVER` | Chỉ được gọi khi không có transaction; đang có transaction thì lỗi. |
| `NESTED` | **Không có** | Spring có thể dùng savepoint trong cùng transaction vật lý, tùy manager/driver/DB. |

Ví dụ, khi cần **tạo transaction mới độc lập**, hai cách viết là:

```java
@org.springframework.transaction.annotation.Transactional(
        propagation = org.springframework.transaction.annotation.Propagation.REQUIRES_NEW)
public void auditWithSpring() {
    System.out.println("audit in separate transaction");
}

@jakarta.transaction.Transactional(
        value = jakarta.transaction.Transactional.TxType.REQUIRES_NEW)
public void auditWithJakarta() {
    System.out.println("audit in separate transaction");
}
```

Các phương thức này là **đoạn minh họa để đặt vào Spring-managed service**. Việc thật sự tạo transaction mới vẫn phụ thuộc bean proxy và khả năng của transaction manager.

**Không đổi `Propagation.NESTED` thành Jakarta `TxType.REQUIRES_NEW` một cách máy móc.** `NESTED` thường là savepoint bên trong transaction vật lý hiện tại, không cam kết độc lập; `REQUIRES_NEW` là ranh giới transaction riêng. Nếu transaction ngoài rollback, tác động cuối cùng của hai lựa chọn có thể khác nhau.

## 4. So sánh quy tắc rollback

### 4.1. Mặc định

Trong Spring Transaction Management imperative thông thường, interceptor mặc định rollback khi `RuntimeException` hoặc `Error` thoát khỏi ranh giới phương thức, nhưng **không tự động rollback checked exception**. Theo đặc tả Jakarta Transactions, `RuntimeException` mặc định đánh dấu rollback, còn checked exception thì không. Khi annotation Jakarta được Spring xử lý, phải xét quy tắc của Spring transaction interceptor thực tế.

Ví dụ checked exception `IOException`: nếu muốn rollback, phải chỉ rõ.

```java
@org.springframework.transaction.annotation.Transactional(
        rollbackFor = java.io.IOException.class)
public void importWithSpring() throws java.io.IOException {
    throw new java.io.IOException("import failed");
}

@jakarta.transaction.Transactional(
        rollbackOn = java.io.IOException.class)
public void importWithJakarta() throws java.io.IOException {
    throw new java.io.IOException("import failed");
}
```

Hai phương thức là **ví dụ thuộc tính**; khi được gọi qua transaction proxy, exception thoát ra sẽ dẫn đến xử lý rollback. Nếu chỉ `new` object rồi gọi trực tiếp thì annotation không làm Spring bắt đầu transaction.

### 4.2. Muốn loại trừ exception khỏi quy tắc rollback

```java
@org.springframework.transaction.annotation.Transactional(
        noRollbackFor = IllegalArgumentException.class)
public void springIgnore() {
    throw new IllegalArgumentException("validation outcome");
}

@jakarta.transaction.Transactional(
        dontRollbackOn = IllegalArgumentException.class)
public void jakartaIgnore() {
    throw new IllegalArgumentException("validation outcome");
}
```

Giữa hai cách viết, **tên thuộc tính khác nhau**: `noRollbackFor` ở Spring, `dontRollbackOn` ở Jakarta. Không rollback theo **quy tắc của interceptor** không có nghĩa có thể ép commit nếu transaction đã `rollback-only` hoặc DB gặp lỗi bắt buộc rollback.

### 4.3. Khi quy tắc chồng chéo

- Spring chọn rollback rule khớp **cụ thể nhất** theo loại exception; có thêm các biến thể theo pattern class name. Nên ưu tiên `rollbackFor = MyException.class` thay cho pattern string để tránh khớp nhầm `MyExceptionV2` hay nested exception tương tự.
- Đặc tả Jakarta Transactions định nghĩa `dontRollbackOn` có ưu tiên so với `rollbackOn` khi cùng exception thỏa cả hai. Khi chạy dưới một runtime cụ thể, đặc biệt có nhiều quy tắc hoặc nhiều lớp advice, nên viết integration test thay vì dựa vào suy đoán.
- Một số phiên bản Spring mới cho phép thay đổi **quy tắc rollback mặc định toàn ứng dụng**, chẳng hạn `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`. Do đó, câu "checked exception luôn commit" chỉ đúng khi cấu hình mặc định tương ứng vẫn được giữ.

**Đặc biệt:** nếu bạn bắt exception **bên trong** phương thức `@Transactional` rồi không ném tiếp, transaction interceptor thường không thấy exception đó. Quy tắc rollback theo exception không tự kích hoạt chỉ vì có một `catch`, và transaction có thể được commit trừ khi có dấu hiệu rollback-only hay lỗi khác.

## 5. Ví dụ thực hành hoàn chỉnh trong Spring Framework (Java 17+)

Ta sẽ chạy **cả hai annotation trong cùng một Spring ApplicationContext** và cùng một `JdbcTransactionManager`, rồi kiểm tra dữ liệu sau mỗi ranh giới transaction.

Môi trường: **Java 17+, Spring Framework 6.2.5, Jakarta Transactions API 2.0.1, H2 2.2.224, Maven**. Đó là những phiên bản được khóa rõ ràng để bạn dễ lặp lại demo. Không cần Spring Boot, Jakarta EE server hoặc database cài riêng.

Cấu trúc:

```text
transactional-comparison/
  pom.xml
  src/main/java/demo/TransactionalComparison.java
```

### 5.1. Tạo `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transactional-comparison</artifactId>
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
            <groupId>jakarta.transaction</groupId>
            <artifactId>jakarta.transaction-api</artifactId>
            <version>2.0.1</version>
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
```

`spring-context` cung cấp container và JavaConfig; `spring-jdbc` cung cấp `JdbcTemplate`; `spring-tx` cung cấp transaction API/manager; `jakarta.transaction-api` cung cấp Jakarta annotation; H2 là database in-memory.

### 5.2. Tạo `src/main/java/demo/TransactionalComparison.java`

```java
package demo;

import java.io.IOException;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionalComparison {
    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE tx_record (
                        id INT PRIMARY KEY,
                        note VARCHAR(40) NOT NULL
                    )
                    """);

            SpringWriter spring = ctx.getBean(SpringWriter.class);
            JakartaWriter jakarta = ctx.getBean(JakartaWriter.class);

            spring.insert(1, false);
            jakarta.insert(2, false);
            System.out.println("after_success=" + count(jdbc));

            try {
                spring.insert(3, true);
            } catch (IllegalStateException ex) {
                System.out.println("spring_failure=" + ex.getMessage());
            }

            try {
                jakarta.insert(4, true);
            } catch (IllegalStateException ex) {
                System.out.println("jakarta_failure=" + ex.getMessage());
            }
            System.out.println("after_runtime_errors=" + count(jdbc));

            try {
                spring.insertThenThrowChecked(5);
            } catch (IOException ex) {
                System.out.println("spring_checked_failure=" + ex.getMessage());
            }

            try {
                jakarta.insertThenThrowChecked(6);
            } catch (IOException ex) {
                System.out.println("jakarta_checked_failure=" + ex.getMessage());
            }
            System.out.println("after_checked_errors=" + count(jdbc));
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM tx_record", Integer.class);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            var ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_compare;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public SpringWriter springWriter(JdbcTemplate jdbcTemplate) {
            return new SpringWriter(jdbcTemplate);
        }

        @Bean
        public JakartaWriter jakartaWriter(JdbcTemplate jdbcTemplate) {
            return new JakartaWriter(jdbcTemplate);
        }
    }

    public static class SpringWriter {
        private final JdbcTemplate jdbc;

        public SpringWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @org.springframework.transaction.annotation.Transactional
        public void insert(int id, boolean failAfterInsert) {
            jdbc.update("INSERT INTO tx_record (id, note) VALUES (?, ?)", id, "spring");
            System.out.println("spring_active="
                    + TransactionSynchronizationManager.isActualTransactionActive());
            if (failAfterInsert) {
                throw new IllegalStateException("boom");
            }
        }

        @org.springframework.transaction.annotation.Transactional(
                rollbackFor = IOException.class)
        public void insertThenThrowChecked(int id) throws IOException {
            jdbc.update("INSERT INTO tx_record (id, note) VALUES (?, ?)", id, "spring");
            throw new IOException("checked");
        }
    }

    public static class JakartaWriter {
        private final JdbcTemplate jdbc;

        public JakartaWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @jakarta.transaction.Transactional
        public void insert(int id, boolean failAfterInsert) {
            jdbc.update("INSERT INTO tx_record (id, note) VALUES (?, ?)", id, "jakarta");
            System.out.println("jakarta_active="
                    + TransactionSynchronizationManager.isActualTransactionActive());
            if (failAfterInsert) {
                throw new IllegalStateException("boom");
            }
        }

        @jakarta.transaction.Transactional(rollbackOn = IOException.class)
        public void insertThenThrowChecked(int id) throws IOException {
            jdbc.update("INSERT INTO tx_record (id, note) VALUES (?, ?)", id, "jakarta");
            throw new IOException("checked");
        }
    }
}
```

**Vì sao dùng tên annotation đầy đủ?** Hai annotation đều có simple name `Transactional`; cùng một file Java không thể import cả hai rồi sử dụng tên `@Transactional` mà không gây nhập nhằng. Viết tên package đầy đủ giúp người học nhận diện chính xác API được dùng.

**Vì sao demo không cần JTA server?** `Config` bật `@EnableTransactionManagement`, đăng ký một `JdbcTransactionManager` và hai Spring bean. Spring AOP proxy chặn lời gọi public method của từng bean; cả hai annotation đều được Spring đọc metadata. Transaction ở đây là JDBC cục bộ trên H2, do **cùng một manager** thực thi.

### 5.3. Biên dịch, chạy và đọc kết quả

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TransactionalComparison
```

Kết quả từ `System.out`, không tính thông báo khởi tạo của công cụ:

```text
spring_active=true
jakarta_active=true
after_success=2
spring_active=true
spring_failure=boom
jakarta_active=true
jakarta_failure=boom
after_runtime_errors=2
spring_checked_failure=checked
jakarta_checked_failure=checked
after_checked_errors=2
```

Phân tích kết quả:

1. `spring.insert(1, false)` và `jakarta.insert(2, false)` được gọi qua Spring bean proxy, transaction mới bắt đầu và commit bình thường; có hai hàng.
2. Cả hai phương thức `insert(..., true)` đã chạy câu `INSERT` bên trong transaction, sau đó ném unchecked `IllegalStateException`. Interceptor rollback, nên số hàng vẫn bằng `2`.
3. Hai phương thức `insertThenThrowChecked` ném `IOException`. Mặc định checked exception thường không gây rollback, nhưng ở đây ta khai báo **`rollbackFor`** trên Spring annotation và **`rollbackOn`** trên Jakarta annotation; hai `INSERT` được rollback, số hàng vẫn là `2`.
4. `TransactionSynchronizationManager.isActualTransactionActive()` in `true` cho cả hai service vì Spring đang quản lý transaction trong thread. Đó **không phải bằng chứng commit**; giá trị `COUNT(*)` sau khi lời gọi proxy kết thúc mới xác nhận trạng thái dữ liệu cuối cùng.

**Thí nghiệm bổ sung:** Trên bản sao của ví dụ, bỏ hai thuộc tính `rollbackFor` và `rollbackOn`, chạy lại từ database in-memory mới. Với quy tắc mặc định, hai `IOException` sẽ không tự đánh dấu rollback, do đó dù caller vẫn bắt checked exception, các `INSERT` có thể được commit. Khi thử xong, khôi phục hai quy tắc rollback.

## 6. Jakarta annotation trong Spring khác gì Jakarta EE/CDI?

### Khi chạy trong Spring

`@EnableTransactionManagement` hoặc cấu hình tương đương kích hoạt transaction advice. Spring có thể đọc metadata từ cả hai annotation, biến chúng thành transaction attributes và sử dụng transaction manager đã cấu hình (JDBC, JPA hoặc JTA). Việc annotation có package `jakarta.transaction` **không mặc nhiên yêu cầu Jakarta EE container hay JTA coordinator**.

Nếu một ứng dụng Spring có nhiều `PlatformTransactionManager`, annotation Spring hỗ trợ chọn theo từng method:

```java
@org.springframework.transaction.annotation.Transactional(
        transactionManager = "auditTransactionManager")
public void auditWithNamedManager() {
    System.out.println("audit");
}
```

Đây là phương thức minh họa trong Spring bean, cần một manager thật sự tên `auditTransactionManager`. Jakarta annotation **không có** `transactionManager` để khai báo ý này; có thể cần cấu hình manager mặc định/`TransactionManagementConfigurer` theo kiến trúc dự án, hoặc dùng Spring annotation ở nơi yêu cầu qualifier.

### Khi chạy trong Jakarta EE/CDI

`jakarta.transaction.Transactional` là CDI interceptor binding chuẩn, áp dụng cho các loại managed bean được hỗ trợ và dựa trên hạ tầng transaction của Jakarta EE runtime. `TxType` và rollback rules được xử lý bởi interceptor của container.

Chỉ thêm dependency `jakarta.transaction-api` vào một dự án Java SE rồi tạo `new Service()` sẽ **không tự cung cấp transaction interceptor**. Nếu cùng một ứng dụng có cả Spring và Jakarta EE runtime, cần biết ai đang thực sự sở hữu boundary; cấu hình trùng interceptor có thể dẫn đến hành vi không mong muốn.

## 7. Cách chuyển đổi cú pháp an toàn

Nếu đoạn code chỉ dùng propagation và rollback rules tương ứng, có thể chuyển ý định:

**Spring:**

```java
@org.springframework.transaction.annotation.Transactional(
        propagation = org.springframework.transaction.annotation.Propagation.REQUIRES_NEW,
        rollbackFor = java.io.IOException.class)
public void publishSpring() throws java.io.IOException {
    throw new java.io.IOException("send failed");
}
```

**Jakarta:**

```java
@jakarta.transaction.Transactional(
        value = jakarta.transaction.Transactional.TxType.REQUIRES_NEW,
        rollbackOn = java.io.IOException.class)
public void publishJakarta() throws java.io.IOException {
    throw new java.io.IOException("send failed");
}
```

Đây là **đoạn minh họa trong service**, chưa phải chương trình độc lập. Nếu method được gọi qua proxy và một transaction mới thực sự được tạo, cả hai diễn tả ý định tương đương về `REQUIRES_NEW` và rollback checked exception.

Ngược lại, đoạn Spring sau **không thể dịch nguyên thuộc tính** sang Jakarta annotation:

```java
@org.springframework.transaction.annotation.Transactional(
        isolation = org.springframework.transaction.annotation.Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = true,
        transactionManager = "reportingTransactionManager")
public void loadReport() {
    System.out.println("read report");
}
```

`isolation`, `timeout`, `readOnly` và `transactionManager` không tồn tại trên Jakarta annotation. Chuyển import làm mất thông tin cấu hình hoặc lỗi biên dịch. `readOnly` trong Spring chỉ là **hint**, không phải lời bảo đảm rằng DB tuyệt đối từ chối ghi; `timeout` và `isolation` chủ yếu có hiệu lực khi tạo transaction mới.

### Lưu ý từ `javax.transaction` đến `jakarta.transaction`

Trong hệ sinh thái Java EE/Spring cũ, bạn có thể thấy `javax.transaction.Transactional`. Khi nâng cấp sang Spring 6 và Jakarta EE 9+, API tương ứng là `jakarta.transaction.Transactional`. `javax.transaction.Transactional` và `jakarta.transaction.Transactional` là **hai Java type khác nhau**. Không coi việc thêm cả hai dependency là cách sửa import tự động; phải kiểm tra version framework, cấu hình và integration test transaction.

## 8. Những lỗi phổ biến

| Triệu chứng / hiểu nhầm | Cách giải thích và xử lý |
| --- | --- |
| Jakarta annotation không có `readOnly`, `isolation`, `rollbackFor` | Đây là thuộc tính riêng của Spring. Giữ Spring annotation nếu cần chúng, hoặc dùng đúng `rollbackOn`/`TxType` của Jakarta. |
| Viết Jakarta `value="txManager"` | Sai kiểu: Jakarta `value` yêu cầu `TxType`; Spring `value` mới là qualifier tên manager. |
| Tưởng `TxType.REQUIRES_NEW` thay được `Propagation.NESTED` | Khác transaction vật lý và savepoint; không thay máy móc. |
| Tưởng Jakarta annotation sẽ tạo XA transaction | Transaction manager/tài nguyên thật mới quyết định local hay distributed transaction. |
| Có annotation nhưng không thấy rollback | Kiểm tra bật annotation transaction management, bean do Spring quản lý và lời gọi có đi qua proxy không. |
| Tạo service bằng `new` hoặc gọi `this.innerMethod()` | Ở proxy mode, Spring advice không chặn lời gọi đó như một boundary mới. |
| Tưởng mọi checked exception đều rollback | Cần `rollbackFor` hoặc `rollbackOn`, trừ khi global rules được điều chỉnh. |
| Có nhiều datasources/transaction managers | Dùng manager phù hợp và rõ ràng; khi cần chọn manager theo method, Spring annotation có `transactionManager`. |
| Gắn cả Spring và Jakarta `@Transactional` lên cùng method | Có thể làm metadata khó hiểu, đặc biệt nếu rules mâu thuẫn; nên chọn một annotation trên một boundary và kiểm thử. |
| Đổi import `javax.transaction` sang `jakarta.transaction` nhưng chưa nâng cấp dependency tương thích | Có thể lỗi biên dịch hoặc runtime không nhận diện annotation; xác nhận framework và Jakarta API version. |
| Nghĩ `@Transactional` xử lý mọi self-invocation, thread mới hoặc `@Async` | Spring proxy không chặn self-invocation; transaction imperative thường gắn với thread, không tự truyền sang thread khác. |

**Lưu ý về Spring Boot:** trong ứng dụng Boot có auto-configuration giao dịch phù hợp, bạn thường không cần tự thêm `@EnableTransactionManagement`. Tuy vậy, cả hai annotation vẫn cần hạ tầng transaction đã được kích hoạt và manager phù hợp. Điều đó không thay đổi sự khác nhau về bộ thuộc tính.

## 9. Khi nào nên chọn loại nào?

**Nên ưu tiên Spring `@Transactional` nếu ứng dụng chủ yếu chạy trên Spring Framework/Spring Boot** và cần một trong các tính năng sau: `isolation`, `timeout`, `readOnly`, `Propagation.NESTED`, transaction manager theo method, label hay quy tắc rollback theo tên class. Annotation này diễn đạt đầy đủ hơn các lựa chọn của Spring transaction infrastructure.

**Có thể chọn Jakarta `@Transactional`** nếu dự án hướng tới contract Jakarta Transactions/CDI hoặc muốn thống nhất với mã sử dụng chuẩn Jakarta, đồng thời chỉ cần sáu `TxType` thông dụng và các rollback rules theo loại exception. Trước khi dùng, hãy xác nhận Spring/runtime thực sự nhận diện annotation và kiểm thử boundary quan trọng.

Khi đã chọn một API cho một phần code, giữ import nhất quán. Không thể suy ra "annotation Jakarta sẽ nhanh hơn" hoặc "annotation Spring sẽ bền dữ liệu hơn" chỉ dựa trên tên package: hiệu quả và độ tin cậy phụ thuộc DB, manager, cách sử dụng connection và transaction boundaries.

## 10. Câu hỏi kiểm tra hiểu biết

**1.** Dùng `@jakarta.transaction.Transactional` trên Spring bean truy cập JDBC bằng `JdbcTransactionManager` có nhất thiết cần JTA/XA coordinator?

**Đáp án:** Không. Spring có thể diễn giải Jakarta annotation và thực hiện giao dịch JDBC cục bộ bằng manager đã cấu hình.

**2.** Muốn checked `IOException` gây rollback thì khai báo thế nào?

**Đáp án:** Spring dùng `rollbackFor = IOException.class`; Jakarta dùng `rollbackOn = IOException.class`.

**3.** Nếu cần `isolation = READ_COMMITTED`, `timeout = 10` và `readOnly = true` trên cùng method, chọn annotation nào?

**Đáp án:** Spring `@Transactional`, vì Jakarta annotation không có các thuộc tính tương ứng.

**4.** Spring `Propagation.NESTED` có tương ứng với Jakarta `TxType.REQUIRES_NEW` không?

**Đáp án:** Không. `NESTED` thường dựa trên savepoint của transaction hiện có, còn `REQUIRES_NEW` là transaction vật lý riêng.

**5.** Tại sao hai file có cùng `@Transactional` nhưng IDE chỉ cho `value = "paymentsTx"` trong một file?

**Đáp án:** File đó import Spring annotation. Với Jakarta, `value` là enum `TxType` chứ không phải String qualifier.

**6.** Nếu service dùng `@jakarta.transaction.Transactional` nhưng được khởi tạo bằng `new` trong ứng dụng Spring, annotation có tự mở transaction không?

**Đáp án:** Không. Đối tượng tự tạo không được Spring proxy chặn; phải dùng Spring bean hoặc một container/interceptor phù hợp.

## Ghi nhớ

- **Cùng tên `@Transactional` nhưng khác API.** Spring có nhiều thuộc tính hơn; Jakarta là chuẩn gọn, tập trung vào `TxType` và rollback rules.
- **Spring:** `propagation`, `rollbackFor`, `noRollbackFor`, `isolation`, `timeout`, `readOnly`, `transactionManager`, `NESTED`.
- **Jakarta:** `value = TxType.*`, `rollbackOn`, `dontRollbackOn`; không có `NESTED` hoặc các option Spring-specific.
- **Trong Spring, cả hai đều có thể được transaction interceptor của Spring xử lý.** Annotation chỉ mô tả transaction; transaction manager và proxy thực sự quyết định hành vi.
- Khi đổi import, kiểm tra kỹ attribute names, transaction manager, default rollback và chạy integration test commit/rollback.

## Tài liệu tham khảo chính thức

1. Spring Framework 6.2 — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html).
2. Spring Framework — [Spring `@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html).
3. Jakarta EE Platform — [Jakarta `@Transactional` Javadoc](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/transaction/transactional).
4. Jakarta EE — [`Transactional.TxType`](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/transaction/transactional.txtype).
5. Jakarta Transactions — [Specification 2.0](https://jakarta.ee/specifications/transactions/2.0/jakarta-transactions-spec-2.0.html).
6. Maven Central — [`jakarta.transaction-api`](https://central.sonatype.com/artifact/jakarta.transaction/jakarta.transaction-api).
