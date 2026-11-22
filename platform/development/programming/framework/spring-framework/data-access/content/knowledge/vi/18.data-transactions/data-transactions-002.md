# `DataSourceTransactionManager` và `JdbcTransactionManager` trong Spring JDBC

## 1. Mục tiêu của hai transaction manager

Một thao tác nghiệp vụ thường chạy **nhiều lệnh SQL phải thành công hoặc thất bại cùng nhau**. Chẳng hạn chuyển 100 đơn vị từ tài khoản A sang tài khoản B cần trừ A và cộng B trong một giao dịch. Nếu lệnh cộng B lỗi mà lệnh trừ A đã commit, dữ liệu bị sai.

Trong Spring Framework, `PlatformTransactionManager` là abstraction điều khiển vòng đời giao dịch: bắt đầu, commit, rollback và áp dụng các quy tắc propagation, isolation, read-only, timeout. Đối với **JDBC đồng bộ** truy cập một `DataSource`, hai implementation liên quan trực tiếp là:

- `org.springframework.jdbc.datasource.DataSourceTransactionManager`: quản lý **giao dịch JDBC cục bộ** trên kết nối lấy từ một `DataSource`.
- `org.springframework.jdbc.support.JdbcTransactionManager`: **kế thừa `DataSourceTransactionManager`**, giữ cơ chế quản lý kết nối/giao dịch và bổ sung **dịch lỗi `SQLException` xảy ra khi commit hoặc rollback** qua hạ tầng `SQLExceptionTranslator` mà `JdbcTemplate` cũng sử dụng.

`JdbcTransactionManager` có từ **Spring Framework 5.3**. Từ khóa “Jdbc” trong tên không có nghĩa nó sử dụng một mô hình giao dịch khác hay có khả năng điều phối nhiều cơ sở dữ liệu. Cả hai vẫn làm việc với một tài nguyên JDBC thông qua cùng một `DataSource`.

### Trường hợp cần transaction

```text
BEGIN TRANSACTION
    UPDATE account SET balance = balance - 100 WHERE id = 1;
    UPDATE account SET balance = balance + 100 WHERE id = 2;
COMMIT                        -- cả hai thay đổi có hiệu lực

BEGIN TRANSACTION
    UPDATE account SET balance = balance - 100 WHERE id = 1;
    UPDATE account SET balance = balance + 100 WHERE id = 2;
    -- ứng dụng phát hiện lỗi
ROLLBACK                      -- cả hai thay đổi bị hủy
```

Đây là **sơ đồ ý nghĩa**, không phải một script SQL đa hệ quản trị để sao chép nguyên văn. Cú pháp bắt đầu giao dịch và khả năng rollback phụ thuộc DBMS và loại đối tượng SQL. Trong Java/Spring, mã service nên mô tả **ranh giới giao dịch**; transaction manager và driver xử lý các thao tác JDBC thích hợp.

## 2. So sánh chính xác hai lớp

| Tiêu chí | `DataSourceTransactionManager` | `JdbcTransactionManager` |
| --- | --- | --- |
| Package | `org.springframework.jdbc.datasource` | `org.springframework.jdbc.support` |
| Quan hệ kế thừa | Kế thừa `AbstractPlatformTransactionManager` | Kế thừa trực tiếp `DataSourceTransactionManager` |
| Tài nguyên quản lý | Một JDBC `DataSource` | Một JDBC `DataSource` |
| Ràng buộc connection vào thread | Có, qua Spring transaction synchronization | Có, **thừa hưởng** |
| `@Transactional`, `TransactionTemplate` | Hỗ trợ | Hỗ trợ |
| `REQUIRED`, `REQUIRES_NEW`, `NESTED` | Hỗ trợ theo khả năng JDBC | Cùng cơ chế |
| Isolation, timeout, read-only | Theo JDBC/driver và cấu hình | Cùng cơ chế |
| SQLException ở **lệnh SQL** chạy qua `JdbcTemplate` | `JdbcTemplate` dịch sang `DataAccessException` | **Giống nhau** ở tầng `JdbcTemplate` |
| SQLException ngay khi **commit/rollback** | Mặc định bọc thành `TransactionSystemException` | Cố gắng dịch thành `DataAccessException` phù hợp; fallback `TransactionSystemException` |
| Khi thường chọn | Cần hành vi exception của manager truyền thống, tương thích luồng hiện có | Ứng dụng JDBC muốn xử lý lỗi commit/rollback nhất quán hơn với `JdbcTemplate` |

**Điểm quyết định là thời điểm phát sinh lỗi.** Một lệnh `INSERT` lỗi do trùng khóa có thể đã được `JdbcTemplate` chuyển thành `DuplicateKeyException` trong cả hai cấu hình. Điểm mở rộng của `JdbcTransactionManager` nằm ở lỗi phát sinh **muộn tại commit hoặc rollback**, ví dụ một số xung đột transaction isolation cao được DBMS báo ở bước commit.

Không khẳng định **mọi** lỗi commit đều sẽ trở thành một subclass cụ thể của `DataAccessException`: translator phụ thuộc loại `SQLException`, SQLState, JDBC driver và cấu hình. Nếu không dịch được, manager vẫn có thể ném `TransactionSystemException`. Code nghiệp vụ cần hiểu cả hai họ lỗi.

## 3. Cơ chế quản lý connection dưới một giao dịch

### 3.1. Một connection được dùng xuyên suốt các lệnh SQL

Với `DataSourceTransactionManager` hoặc `JdbcTransactionManager`, khi một giao dịch thực sự bắt đầu, Spring lấy một connection từ `DataSource` và gắn tài nguyên liên quan với luồng thực thi thông qua `TransactionSynchronizationManager`. Manager cấu hình trạng thái JDBC cần thiết, thường đặt `autoCommit = false` nếu cần, rồi commit/rollback và dọn dẹp sau khi giao dịch kết thúc.

`JdbcTemplate` tự động dùng `DataSourceUtils.getConnection(dataSource)`, nhờ đó hai câu SQL thực thi bên trong cùng một `@Transactional` có thể dùng **cùng connection đang tham gia transaction**. Khi transaction hoàn tất, Spring xử lý khôi phục trạng thái connection và trả connection về `DataSource`/pool phù hợp.

```text
External call: transferService.transfer(...)
             |
             v
Spring @Transactional proxy
             |
             v
PlatformTransactionManager.getTransaction(...)
             |
             v
DataSource -> JDBC Connection X, bound to current thread
             |
             +--> JdbcTemplate.update("debit")  -- Connection X
             |
             +--> JdbcTemplate.update("credit") -- Connection X
             |
             v
 commit() or rollback() on Connection X
             |
             v
 cleanup / unbind / release Connection X
```

Ví dụ mô tả luồng **imperative** chạy trong cùng thread. Không tự giả định cùng transaction sẽ theo sang thread được tạo bằng `new Thread(...)`, một tác vụ `@Async` hay pipeline reactive.

### 3.2. Tại sao cả manager lẫn DAO cần cùng DataSource?

Phần cốt lõi là **cùng một connection factory/tài nguyên mà Spring nhận diện**. Nếu cấu hình transaction manager với `dataSourceA` nhưng `JdbcTemplate` dùng `dataSourceB`, lệnh SQL có thể chạy ngoài transaction mà bạn nghĩ đang bảo vệ.

```java
// Fragment cấu hình trong một @Configuration class.
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}

@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
```

Cả hai phương thức dùng **cùng bean `DataSource`** được Spring inject. Có thể thay nội dung phương thức `transactionManager` bằng `new DataSourceTransactionManager(dataSource)` mà không cần sửa service và repository dùng `JdbcTemplate`.

Nếu tự gọi JDBC thấp cấp, hãy lấy connection bằng `DataSourceUtils.getConnection(dataSource)` và trả lại bằng `DataSourceUtils.releaseConnection(connection, dataSource)`. Gọi trực tiếp `dataSource.getConnection()` trên một pool thông thường rồi tự đóng có thể tạo **connection khác** và bỏ qua sự đồng bộ transaction của Spring. Khi tích hợp code legacy bắt buộc gọi `getConnection()` trực tiếp, Spring có `TransactionAwareDataSourceProxy`; cần dùng đúng vị trí proxy theo tài liệu.

### 3.3. Giới hạn của transaction JDBC cục bộ

Hai manager này phù hợp khi một thao tác dùng **một `DataSource` có connection độc lập**. Chúng không tạo một giao dịch phân tán nguyên tử trên hai database, JDBC cộng JMS, hoặc JDBC cộng HTTP request. Nếu thực sự cần phối hợp XA/nhiều resource, dùng công nghệ thích hợp như JTA khi môi trường hỗ trợ; với hệ thống phân tán còn phải xem xét outbox, saga, idempotency hoặc giao thức phù hợp.

Sự tồn tại của `@Transactional` không tự biến thao tác mạng, ghi file hoặc gửi email thành thành phần rollback được.

## 4. Ví dụ Java 17 + Spring JDBC chạy được

Mục tiêu: tạo hai tài khoản trong **H2 in-memory**; chạy một giao dịch chuyển tiền thành công và một giao dịch ném lỗi sau cả hai update. Kết quả chứng minh rollback thực sự, rồi đổi transaction manager từ `JdbcTransactionManager` sang `DataSourceTransactionManager` để thấy **quy tắc commit/rollback cơ bản không đổi**.

Ví dụ dùng **Spring Framework 6.2.x**, Java 17+, Maven và H2. Không cần chạy server database riêng. Chạy trong thư mục dự án mới hoặc môi trường thử nghiệm; các class nằm trong một tệp Java cho tiện đọc.

### 4.1. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jdbc-transaction-managers</artifactId>
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
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

`spring-context` cung cấp container và cấu hình annotation; `spring-jdbc` cung cấp `JdbcTemplate` và transaction manager; H2 là JDBC driver/DB dùng riêng cho demo. Trong dự án Spring Boot, nên để BOM của Boot quản lý version dependency tương thích; mã này dùng **Spring Framework thuần**, không cần Boot.

### 4.2. Tệp `src/main/java/TxManagerDemo.java`

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public class TxManagerDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_demo;DB_CLOSE_DELAY=-1");
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
            return new JdbcTransactionManager(ds);
            // Thử biến thể còn lại bằng cách đổi dòng trên thành:
            // return new DataSourceTransactionManager(ds);
        }

        @Bean
        public TransferService transferService(JdbcTemplate jdbc) {
            return new TransferService(jdbc);
        }
    }

    public static class TransferService {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transfer(long fromId, long toId,
                             int amount, boolean failAfterUpdates) {
            if (amount <= 0 || fromId == toId) {
                throw new IllegalArgumentException("Invalid transfer");
            }

            int debited = jdbc.update(
                    "UPDATE account SET balance = balance - ? "
                    + "WHERE id = ? AND balance >= ?",
                    amount, fromId, amount);
            if (debited != 1) {
                throw new IllegalArgumentException("Cannot debit");
            }

            int credited = jdbc.update(
                    "UPDATE account SET balance = balance + ? WHERE id = ?",
                    amount, toId);
            if (credited != 1) {
                throw new IllegalArgumentException("Cannot credit");
            }

            if (failAfterUpdates) {
                throw new IllegalStateException("Simulated failure");
            }
        }
    }

    private static int balance(JdbcTemplate jdbc, long id) {
        Integer result = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?",
                Integer.class, id);
        if (result == null) {
            throw new IllegalStateException("Missing balance for " + id);
        }
        return result;
    }

    private static void printBalances(String label, JdbcTemplate jdbc) {
        System.out.printf("%s: A=%d, B=%d%n",
                label, balance(jdbc, 1L), balance(jdbc, 2L));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransferService service = context.getBean(TransferService.class);

            jdbc.execute("CREATE TABLE account ("
                    + "id BIGINT PRIMARY KEY, balance INT NOT NULL)");
            jdbc.update("INSERT INTO account (id, balance) VALUES (?, ?)",
                    1L, 1000);
            jdbc.update("INSERT INTO account (id, balance) VALUES (?, ?)",
                    2L, 500);

            printBalances("Initial", jdbc);

            service.transfer(1L, 2L, 100, false);
            printBalances("After commit", jdbc);

            try {
                service.transfer(1L, 2L, 100, true);
                throw new AssertionError("Expected failure was not thrown");
            } catch (IllegalStateException expected) {
                if (!"Simulated failure".equals(expected.getMessage())) {
                    throw expected;
                }
            }
            printBalances("After rollback", jdbc);
        }
    }
}
```

**Giải thích các điểm có thể gây nhầm:**

- `Config` là cấu hình Spring thực; `@EnableTransactionManagement` kích hoạt cơ chế proxy cho `@Transactional`. Chỉ đặt annotation lên một method bình thường nhưng không có Spring transaction infrastructure thì chưa có tác dụng.
- `context.getBean(TransferService.class)` trả về bean do Spring quản lý (và có proxy khi cấu hình đúng). Gọi `service.transfer(...)` từ `main` là lời gọi **đi qua proxy**.
- Cả `JdbcTemplate` và `JdbcTransactionManager` nhận cùng `DataSource`. Trong giao dịch, hai `update` của service cùng tham gia cơ chế connection của Spring.
- `IllegalStateException` là unchecked exception. Theo quy tắc mặc định của `@Transactional`, ngoại lệ này làm rollback **cả hai UPDATE** đã chạy trước đó.
- Kiểm tra số dòng update và điều kiện `balance >= amount` là kiểm tra nghiệp vụ bổ sung, không phải đặc tính riêng của một transaction manager.
- `DriverManagerDataSource` không có connection pool; phù hợp demo/test ngắn, không nên dùng cho ứng dụng web production chịu tải.

### 4.3. Lệnh chạy và đầu ra

Từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=TxManagerDemo
```

**Stdout dự kiến** của chương trình (không tính log Maven):

```text
Initial: A=1000, B=500
After commit: A=900, B=600
After rollback: A=900, B=600
```

Sau lần chuyển thành công, A còn 900 và B thành 600. Ở lần thứ hai, dù cả hai update được thực thi trước khi phát sinh `IllegalStateException`, Spring rollback nên số dư vẫn là 900 và 600. Nếu đổi bean `transactionManager` sang `new DataSourceTransactionManager(ds)`, đầu ra ba dòng vẫn như trên: khác biệt giữa hai manager **không xuất hiện** ở trường hợp rollback nghiệp vụ bình thường này.

Ví dụ tự kiểm tra **kết quả nghiệp vụ**, không tạo một lỗi `SQLException` đúng lúc commit/rollback; vì thế nó không chứng minh được loại exception dịch trong trường hợp sự cố concurrency ở commit. Trường hợp đó cần bài test riêng có driver và DBMS thật phù hợp.

## 5. Khác biệt cốt lõi: dịch lỗi commit và rollback

### 5.1. Hai thời điểm phát sinh lỗi SQL

Giả sử một transaction thực thi câu SQL rồi commit:

```text
    JdbcTemplate.update(...)
          |
          +-- SQL exception ngay khi statement thực thi:
          |      JdbcTemplate dùng SQLExceptionTranslator
          |      -> DataAccessException (với cả hai manager)
          |
          v
    PlatformTransactionManager.commit(...)
          |
          +-- SQLException xảy ra trong JDBC Connection.commit():
                 DataSourceTransactionManager
                    -> thường TransactionSystemException

                 JdbcTransactionManager
                    -> thử SQLExceptionTranslator:
                       DataAccessException tương ứng
                       hoặc fallback TransactionSystemException
```

Ví dụ đặc biệt: PostgreSQL ở isolation `SERIALIZABLE` có thể phát hiện một số xung đột giao dịch muộn khi commit. Khi SQLException phù hợp với quy tắc translator, `JdbcTransactionManager` có thể trả `ConcurrencyFailureException` hoặc subclass cụ thể thay vì chỉ một `TransactionSystemException` chung. **Không cố định mã lỗi, subclass hay thời điểm xảy ra lỗi cho tất cả driver.**

### 5.2. Các exception thường gặp

| Thời điểm | Nguồn | Hành vi đáng chú ý |
| --- | --- | --- |
| Thực thi `JdbcTemplate.update/query` | `SQLException` từ JDBC statement | `JdbcTemplate` thường chuyển sang `DataAccessException` cho cả hai manager |
| Đến bước `Connection.commit()` | SQLException khi commit | `JdbcTransactionManager` thử dịch; `DataSourceTransactionManager` dùng `TransactionSystemException` theo hành vi mặc định |
| Đến bước `Connection.rollback()` | SQLException khi rollback | `JdbcTransactionManager` cũng thử dịch; fallback khi không nhận dạng |
| Exception nghiệp vụ từ service | `IllegalStateException`, v.v. | Theo rollback rules của `@Transactional`; cơ chế giống nhau |

**Cần tránh nhầm:** đổi manager sang `JdbcTransactionManager` **không phải** cách “bật dịch lỗi JDBC” cho `JdbcTemplate`: `JdbcTemplate` đã có exception translation riêng. Thay đổi có giá trị chủ yếu ở **commit/rollback**.

### 5.3. Cấu hình translator khi thật sự cần

`JdbcTransactionManager` có thể nhận `SQLExceptionTranslator` tùy chỉnh. Ví dụ dưới là fragment cấu hình chứ không phải lớp chạy độc lập:

```java
// Fragment tại một @Bean method, đã import các lớp liên quan.
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
    manager.setExceptionTranslator(
            new org.springframework.jdbc.support.SQLExceptionSubclassTranslator());
    return manager;
}
```

Spring Framework 6.x đã cung cấp translator mặc định phù hợp cho nhiều trường hợp thông qua các subclass SQL exception và SQLState; chỉ ghi đè khi có yêu cầu rõ ràng (ví dụ driver đặc thù, ánh xạ SQLState/vendor code). Khi custom translator không nhận dạng lỗi, code phải vẫn xử lý exception tổng quát hoặc để nó lan lên boundary thích hợp. Không dựa vào tên riêng của exception để kết luận transaction đã rollback thành công trong mọi tình huống lỗi commit: phải xét tình trạng transaction, retry an toàn và idempotency.

## 6. `@Transactional` và `TransactionTemplate` có liên hệ ra sao?

**Transaction manager** là thành phần thực hiện cơ chế giao dịch. `@Transactional` là metadata cho cách quản lý giao dịch **khai báo**; `TransactionTemplate` là API để quản lý transaction **bằng code**. Cả hai dùng `PlatformTransactionManager` đã được cấu hình.

### 6.1. Khai báo: `@Transactional`

```java
// Fragment trong Spring-managed service, được gọi qua Spring proxy.
@Transactional
public void placeOrder(long orderId) {
    jdbc.update("UPDATE orders SET state = 'CONFIRMED' WHERE id = ?",
            orderId);
    jdbc.update("INSERT INTO order_audit(order_id, action) VALUES (?, ?)",
            orderId, "CONFIRM");
}
```

Nếu lỗi trong một update dẫn đến unchecked exception và không bị nuốt trong phương thức, manager sẽ đánh dấu rollback theo quy tắc mặc định.

Điều kiện quan trọng: method phải được gọi **qua Spring proxy**, ví dụ từ bean khác. Method gọi method khác **trong cùng đối tượng** (self-invocation) không đi qua proxy trong chế độ proxy mặc định, nên annotation trên method bên trong có thể không có tác dụng. Mở transaction từ một public service method được gọi bên ngoài là một lựa chọn rõ ràng.

### 6.2. Lập trình: `TransactionTemplate`

Có thể cùng một manager chạy transaction tường minh bằng template; ví dụ fragment sau giả định đã inject `PlatformTransactionManager txManager` và `JdbcTemplate jdbc`:

```java
TransactionTemplate template = new TransactionTemplate(txManager);

template.executeWithoutResult(status -> {
    jdbc.update("UPDATE account SET balance = balance - ? WHERE id = ?",
            100, 1L);
    jdbc.update("UPDATE account SET balance = balance + ? WHERE id = ?",
            100, 2L);

    boolean validationFailed = true; // Giả sử kiểm tra nghiệp vụ thất bại.
    if (validationFailed) {
        status.setRollbackOnly();
    }
});
```

`status.setRollbackOnly()` yêu cầu rollback khi callback kết thúc; nó không nhất thiết ném exception. Fragment này chỉ minh họa API; không thay thế ví dụ đầy đủ ở phần 4. Nếu callback ném unchecked exception, `TransactionTemplate` cũng thực hiện rollback theo cơ chế của Spring rồi ném lại lỗi. Không cần đặt `@Transactional` và `TransactionTemplate` chồng nhau cho cùng ranh giới khi không có chủ đích propagation rõ ràng.

## 7. Propagation, savepoint, isolation, timeout và read-only

Vì `JdbcTransactionManager` **kế thừa** `DataSourceTransactionManager`, các tính năng quản lý transaction này về cơ bản giống nhau.

### Propagation

| Cấu hình | Ý nghĩa trong lời gọi Spring |
| --- | --- |
| `REQUIRED` (mặc định) | Tham gia transaction có sẵn; nếu chưa có thì tạo transaction mới |
| `REQUIRES_NEW` | Tạm giữ transaction bên ngoài và tạo transaction vật lý mới |
| `NESTED` | Khi đã có transaction, tạo nested scope bằng JDBC savepoint nếu driver hỗ trợ; nếu không có outer transaction thì bắt đầu transaction mới |
| `SUPPORTS` | Có transaction thì tham gia; không có thì chạy không có transaction thực |
| `MANDATORY` | Bắt buộc phải có transaction sẵn; nếu không thì lỗi |
| `NOT_SUPPORTED` | Chạy phần việc không có transaction thực, tạm giữ transaction hiện có |
| `NEVER` | Bị gọi khi có transaction thì lỗi |

**`NESTED` khác `REQUIRES_NEW`:** nested scope có thể rollback về **savepoint trong cùng physical transaction**, còn `REQUIRES_NEW` sử dụng physical transaction khác với connection riêng khi cần. Savepoint phải được JDBC driver và DBMS hỗ trợ; cờ `nestedTransactionAllowed` của `DataSourceTransactionManager` mặc định là `true`, nhưng điều đó không ép mọi driver hỗ trợ savepoint.

`REQUIRES_NEW` có thể phải lấy thêm connection từ pool trong khi transaction bên ngoài vẫn giữ connection cũ. Nếu pool quá nhỏ, các tác vụ đồng thời có thể chờ connection và gây bế tắc tài nguyên. Dùng `REQUIRES_NEW` chỉ khi cần khả năng commit/rollback độc lập thật sự.

### Isolation

`@Transactional(isolation = Isolation.READ_COMMITTED)` yêu cầu isolation tương ứng trên transaction mới, phụ thuộc driver/DBMS. Mức mặc định `Isolation.DEFAULT` nhường cho database. Isolation không phải “càng cao càng tốt”: mức mạnh có thể tăng conflict, locking và retry; hãy chọn theo tính nhất quán nghiệp vụ và đo trên database thực.

### Timeout

`@Transactional(timeout = 5)` yêu cầu transaction timeout 5 giây, nhưng mức độ áp dụng phụ thuộc manager/driver/các JDBC statement. `JdbcTemplate` và `DataSourceUtils.applyTransactionTimeout(...)` có cơ chế áp dụng timeout cho statement. Nếu tự tạo raw `Statement` mà bỏ qua Spring helper, không nên kết luận mọi query sẽ chịu đúng timeout đã khai báo.

### Read-only

`@Transactional(readOnly = true)` là tín hiệu cho transaction infrastructure/driver; mặc định nhiều môi trường chỉ xem đó là **hint**. `DataSourceTransactionManager.setEnforceReadOnly(true)` cho phép cố gắng áp dụng lệnh transaction read-only thật ở những DBMS được hỗ trợ, ví dụ bằng `SET TRANSACTION READ ONLY`. Cấu hình này **cả hai manager** đều có vì cùng cơ chế kế thừa; phải thử trên DBMS thật trước khi xem nó như rào cản ghi dữ liệu.

### Ví dụ annotation có thuộc tính

```java
// Fragment trên method trong Spring-managed service.
@Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 5,
        rollbackFor = java.io.IOException.class
)
public void updateAndAudit() throws java.io.IOException {
    // Các lệnh SQL dùng cùng DataSource/JdbcTemplate.
}
```

Ở fragment này cần import `org.springframework.transaction.annotation.Propagation` và `org.springframework.transaction.annotation.Isolation`. Điều kiện rollback cho `IOException` là **được chỉ định tường minh**. Mặc định `@Transactional` rollback khi có `RuntimeException` hoặc `Error`; checked exception thông thường không tự kích hoạt rollback nếu không cấu hình quy tắc tương ứng. Nếu bắt exception bên trong method rồi không ném ra hoặc không đánh dấu rollback-only, transaction có thể tiếp tục đến commit.

## 8. Những trường hợp nên chọn manager nào?

### Chọn `JdbcTransactionManager` khi

- Ứng dụng dùng Spring JDBC (đặc biệt `JdbcTemplate`/`NamedParameterJdbcTemplate`) trên **một `DataSource`**.
- Muốn phân loại SQLException ở commit/rollback bằng cùng hệ thống `DataAccessException` đã dùng ở phần thao tác SQL.
- Có xử lý những lỗi concurrency đôi khi xuất hiện ở **commit** (đặc biệt các giao dịch isolation cao) và muốn tận dụng translator khi driver cung cấp đủ thông tin.
- Đã xác nhận hệ thống gọi phía trên chịu được việc `commit()/rollback()` có thể ném `DataAccessException` bên cạnh `TransactionException`.

### Giữ `DataSourceTransactionManager` khi

- Ứng dụng cũ đã viết lớp xử lý/giám sát với kỳ vọng cụ thể về `TransactionSystemException` ở commit/rollback.
- Bạn cần giữ nguyên hành vi exception lịch sử trong quá trình nâng cấp hoặc đã có cơ chế báo lỗi transaction-level riêng.
- Không có lợi ích thực tế từ việc dịch thêm lỗi commit/rollback, và thay đổi đó làm phát sinh điều chỉnh compatibility.

Không nên chọn dựa trên tiêu chí sai như “`JdbcTransactionManager` có transaction thực còn `DataSourceTransactionManager` không”, “manager cũ không hỗ trợ `@Transactional`”, hay “manager mới sửa được self-invocation”. Những nhận định này đều sai.

### Khi **không** dùng cả hai

- Sử dụng JPA với `EntityManager` làm tài nguyên chính: thường dùng `JpaTransactionManager` theo kiến trúc JPA, để quản lý lifecycle và flush của persistence context.
- Cần nhiều resource XA đồng nhất: xem giải pháp JTA phù hợp (chỉ khi môi trường thực sự hỗ trợ).
- Dùng Spring R2DBC/reactive: dùng `R2dbcTransactionManager` và reactive transaction context, không dùng thread-bound JDBC manager.

Có thể có hệ thống đa công nghệ cần nhiều transaction manager khác nhau; khi đó khai báo rõ manager đích bằng qualifier của `@Transactional(transactionManager = "...")` để tránh sử dụng nhầm.

## 9. Lỗi thực tế và hướng kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Lệnh đầu commit dù lệnh sau ném lỗi | Method không chạy qua proxy, manager/DAO khác DataSource, exception bị nuốt | Kiểm tra bean proxy, Spring config và cùng DataSource; test rollback bằng dữ liệu thực |
| Lỗi xảy ra ở commit nhưng không thấy `DataAccessException` cụ thể | Đang dùng `DataSourceTransactionManager` hoặc translator không nhận dạng SQLException | Đọc exception chain, loại manager và SQLState; không ép mọi lỗi thành một subclass |
| Có `@Transactional` nhưng không rollback khi ném checked exception | Rollback rules mặc định | Thêm `rollbackFor` hoặc cấu hình chính sách phù hợp |
| `NESTED` không hoạt động | Driver/DBMS không hỗ trợ savepoint hoặc không có transaction thực như kỳ vọng | Kiểm tra savepoint support và propagation thực tế |
| `REQUIRES_NEW` chờ connection | Outer transaction giữ connection, pool thiếu connection | Tăng capacity có căn cứ, giảm nesting hoặc thiết kế lại luồng |
| Query không chịu timeout | Raw JDBC Statement bỏ qua Spring timeout helper | Dùng `JdbcTemplate` hoặc `DataSourceUtils.applyTransactionTimeout` |
| `readOnly = true` vẫn ghi được | Read-only thường là hint, DBMS không cưỡng chế | Chọn mức enforcement được DBMS hỗ trợ và kiểm thử |
| Kết quả mất giữa các thread | Transaction context trong luồng imperative gắn với thread | Thiết kế boundary giao dịch trong từng luồng, tránh giả định tự truyền sang `@Async` |
| Khối JDBC được rollback nhưng email vẫn gửi | Gửi email không thuộc resource JDBC | Dùng outbox hoặc orchestration thích hợp |

### Checklist kiểm thử trước khi vận hành

1. Xác định `PlatformTransactionManager` nào thực sự được inject; xác định bean `DataSource` của manager và mọi `JdbcTemplate` có cùng nguồn connection.
2. Test **commit thành công** và **rollback vì unchecked exception**; kiểm tra dữ liệu sau transaction, không chỉ dựa vào log.
3. Test checked exception với/không có `rollbackFor` nếu nghiệp vụ phát sinh loại này.
4. Nếu cần, test `NESTED`/savepoint và `REQUIRES_NEW` với pool thật; chú ý số connection và transaction isolation.
5. Bật log chẩn đoán Spring transaction khi điều tra (ví dụ `org.springframework.transaction` và `org.springframework.jdbc.datasource` ở mức DEBUG trong môi trường phù hợp), nhưng tránh lộ thông tin nhạy cảm và đừng để log chi tiết quá lâu trên production.
6. Kiểm thử lỗi SQL ở **statement** riêng với lỗi ở **commit/rollback**. Lỗi ở commit có thể khó tái tạo; cần DBMS/driver thật và kịch bản concurrency được kiểm soát. Không suy loại exception từ ví dụ H2 nghiệp vụ trong phần 4.
7. Với ứng dụng có retry, bảo đảm retry diễn ra tại **ranh giới transaction mới**, có idempotency và chỉ retry các lỗi thật sự có thể hồi phục; không retry vô điều kiện mọi `DataAccessException`.
8. Nâng cấp Spring/JDBC driver cần test lại mapping `SQLExceptionTranslator` và logic bắt exception; đây là nơi hai manager có thể tạo khác biệt quan sát được.

## 10. Tổng kết kiến thức

- `DataSourceTransactionManager` quản lý connection và transaction JDBC cục bộ cho **một `DataSource`**, dùng với `JdbcTemplate`, `@Transactional` và `TransactionTemplate`.
- `JdbcTransactionManager` là **subclass** với cùng cơ chế transaction, thêm `SQLExceptionTranslator` ở bước **commit/rollback** để báo lỗi phù hợp hơn với hệ thống `DataAccessException` của Spring JDBC.
- Cả hai dùng cùng connection sharing, propagation, isolation, savepoint và cơ chế rollback cơ bản; việc chuyển manager **không tự sửa** lỗi cấu hình proxy, khác DataSource, thiếu pool hay transaction scope.
- Chọn manager theo tài nguyên, hành vi exception cần có và cách ứng dụng xử lý sự cố ở commit/rollback. Luôn kiểm chứng bằng test nghiệp vụ và DBMS thật khi đánh giá lỗi concurrency.

### Tài liệu chính thức

1. [Spring Framework – Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): cơ chế `DataSourceUtils`, `DataSourceTransactionManager` và `JdbcTransactionManager`, chia sẻ connection, tối ưu lazy connection.
2. [DataSourceTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): local JDBC, savepoints, timeout, read-only, lifecycle.
3. [JdbcTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): subclass từ 5.3, dịch SQLException tại commit/rollback, translator fallback.
4. [Spring Framework – Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy, propagation và rollback rules.
5. [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): sự khác nhau giữa `REQUIRED`, `REQUIRES_NEW` và `NESTED`.
6. [Spring Framework – Using `SQLExceptionTranslator`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): chuẩn hóa các ngoại lệ JDBC thành `DataAccessException`.
