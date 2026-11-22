# TransactionDefinition và thuộc tính giao dịch trong Spring Framework

## Mục tiêu học tập

Sau bài học, bạn có thể: giải thích `TransactionDefinition` khác `TransactionStatus` ra sao; sử dụng năm thuộc tính propagation, isolation, timeout, read-only và name; dự đoán hành vi của transaction lồng nhau; phân biệt `TransactionDefinition` với `TransactionAttribute` và `@Transactional`; cấu hình transaction bằng Java; kiểm thử commit/rollback đúng trên database.

## 1. TransactionDefinition định nghĩa điều gì?

`org.springframework.transaction.TransactionDefinition` là interface biểu diễn **yêu cầu về một transaction**, không phải transaction đã bắt đầu. Nó trả lời: nếu đang có transaction thì tham gia hay tạo mới? Dùng mức cô lập nào? Timeout ra sao? Chỉ đọc hay có ghi? Tên transaction là gì?

Ở mô hình đồng bộ, `PlatformTransactionManager` nhận định nghĩa và trả về trạng thái thực:

```text
TransactionDefinition (chính sách/yêu cầu)
             |
             v
PlatformTransactionManager.getTransaction(definition)
             |
             v
TransactionStatus (trạng thái của lần chạy cụ thể)
             |
             +--> các thao tác JDBC/JPA tham gia transaction
             |
             +--> commit(status) hoặc rollback(status)
```

`TransactionDefinition` không giữ JDBC connection, không cung cấp phương thức commit và không tự quyết định exception nào phải rollback. `TransactionStatus` đại diện cho lần thực thi; có thể hỏi `isNewTransaction()`, `isRollbackOnly()`, `isCompleted()`. Cùng một định nghĩa có thể tái sử dụng, nhưng mỗi lần manager xử lý lại có transaction status riêng.

Hai cách sử dụng trong ứng dụng:

- **Declarative:** đặt `@Transactional` lên phương thức hoặc class; Spring transaction interceptor dịch annotation thành các transaction attributes và quản lý begin/commit/rollback.
- **Programmatic:** tạo `DefaultTransactionDefinition`, truyền vào `PlatformTransactionManager.getTransaction(...)`; hoặc cấu hình `TransactionTemplate` để không cần tự quản lý trạng thái.

Trong mô hình reactive, các thuộc tính cũng có ý nghĩa tương ứng; tuy nhiên, thao tác transaction dùng `ReactiveTransactionManager`/`TransactionalOperator` và Reactor Context. Ví dụ JDBC dưới đây là imperative, không trộn `PlatformTransactionManager` với reactive `Mono/Flux`.

## 2. Năm getter và giá trị mặc định

| Thuộc tính | Getter của `TransactionDefinition` | Mặc định | Ý nghĩa |
|---|---|---|---|
| Propagation | `getPropagationBehavior()` | `PROPAGATION_REQUIRED` | Cách tham gia/tạo transaction |
| Isolation | `getIsolationLevel()` | `ISOLATION_DEFAULT` | Cách cô lập các transaction đang cùng chạy |
| Timeout | `getTimeout()` | `TIMEOUT_DEFAULT` (`-1`) | Số giây dành cho transaction mới, nếu được hỗ trợ |
| Read-only | `isReadOnly()` | `false` | Gợi ý chỉ đọc cho manager/driver/ORM |
| Name | `getName()` | `null` | Tên phục vụ logging/monitoring |

`TransactionDefinition.withDefaults()` cung cấp một định nghĩa mặc định **không thể chỉnh sửa**. Khi muốn tùy chỉnh, dùng `new DefaultTransactionDefinition()` và các setter tương ứng: `setPropagationBehavior`, `setIsolationLevel`, `setTimeout`, `setReadOnly`, `setName`.

`ISOLATION_DEFAULT` không có nghĩa cố định là `READ_COMMITTED`: hệ thống dữ liệu/driver sẽ quyết định. `TIMEOUT_DEFAULT` dùng timeout mặc định của transaction manager/hệ thống giao dịch hoặc không có giới hạn nếu hệ thống không hỗ trợ. Điều quan trọng là **giá trị yêu cầu không đồng nhất với kết quả quan sát tại database**.

## 3. Propagation: quan hệ với transaction hiện có

Đây là thuộc tính kiểm soát ranh giới nghiệp vụ khi service A gọi service B. Spring hỗ trợ bảy hành vi chuẩn:

| Propagation | Khi đã có transaction | Khi chưa có transaction |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại | Bắt đầu transaction mới |
| `SUPPORTS` | Tham gia | Chạy không có physical transaction |
| `MANDATORY` | Tham gia | Ném `IllegalTransactionStateException` |
| `REQUIRES_NEW` | Tạm treo transaction hiện tại, bắt đầu transaction riêng | Bắt đầu transaction mới |
| `NOT_SUPPORTED` | Tạm treo transaction, chạy ngoài transaction | Chạy ngoài transaction |
| `NEVER` | Ném `IllegalTransactionStateException` | Chạy ngoài transaction |
| `NESTED` | Dùng savepoint trong cùng physical transaction nếu hỗ trợ | Hoạt động như `REQUIRED` |

Tên hằng đầy đủ trong interface là `TransactionDefinition.PROPAGATION_REQUIRED`, `TransactionDefinition.PROPAGATION_REQUIRES_NEW`, `TransactionDefinition.PROPAGATION_NESTED`, v.v. Trong `@Transactional` dùng enum `Propagation.REQUIRED`, `Propagation.REQUIRES_NEW`, `Propagation.NESTED`.

### REQUIRED — mặc định cho phần lớn nghiệp vụ

```text
OrderService.placeOrder()        REQUIRED
    |
    +-- StockService.reserve()   REQUIRED
    |
    +-- BillingService.charge()  REQUIRED

      Một physical transaction T1
   (nhiều logical transaction scope)
```

Nếu outer chưa có transaction, `placeOrder()` tạo T1. Các lời gọi inner `REQUIRED` tham gia T1 nên cùng commit/rollback. Mỗi lời gọi vẫn có logical transaction scope riêng. Nếu inner đánh dấu rollback-only rồi outer bắt lỗi và tiếp tục, lúc outer cố commit sẽ có thể nhận `UnexpectedRollbackException`: không thể commit T1 đã được đánh dấu rollback. Cố gắng “nuốt” exception không làm mất rollback-only marker.

### REQUIRES_NEW — transaction vật lý riêng

```text
Outer T1 đang chạy
  |
  +-- Inner REQUIRES_NEW
        suspend T1
        begin T2
        commit/rollback T2
        resume T1
  |
Outer T1 tiếp tục và commit/rollback
```

T2 có quyết định commit/rollback độc lập. Nếu T2 đã commit mà T1 sau đó rollback, các thay đổi đã commit của T2 **không bị hoàn tác theo T1**. Vì có thể phải giữ resource của T1 và lấy thêm connection cho T2, cần xem xét giới hạn connection pool, tải đồng thời và tính nhất quán nghiệp vụ. Chỉ dùng khi nghiệp vụ cần tính độc lập thật sự.

### NESTED — savepoint, không phải giao dịch độc lập

Với JDBC và transaction manager/driver hỗ trợ savepoint, `NESTED` tạo điểm đánh dấu bên trong **cùng physical transaction**. Khi phần con lỗi có thể rollback về savepoint và phần ngoài tiếp tục. Nhưng nếu outer cuối cùng rollback, **tất cả** thay đổi của cùng physical transaction đều rollback. Vì thế:

- `REQUIRES_NEW`: hai physical transaction, commit inner độc lập.
- `NESTED`: một physical transaction, rollback cục bộ bằng savepoint.

`NESTED` có giới hạn hỗ trợ tùy manager/driver, đặc biệt không mặc nhiên hoạt động với mọi JPA hoặc R2DBC setup. `SUPPORTS` khi không có physical transaction vẫn có thể duy trì transaction synchronization scope theo cấu hình manager, vì thế không nên coi nó luôn giống hoàn toàn một lời gọi thuần không qua manager.

### Thuộc tính inner có áp dụng khi REQUIRED tham gia outer?

Ví dụ outer có `@Transactional(readOnly = true, isolation = Isolation.READ_COMMITTED)`, inner có `@Transactional(propagation = REQUIRED, readOnly = false, isolation = SERIALIZABLE, timeout = 3)`. Inner chỉ **tham gia** transaction đã bắt đầu, nên không được tự mở lại connection để nâng isolation hay đặt lại timeout của physical transaction. Theo cấu hình mặc định của những manager hỗ trợ điều này, các yêu cầu isolation/timeout/read-only khác từ inner thường bị bỏ qua khi tham gia; đặc điểm transaction bên ngoài chi phối việc thực thi.

Với manager kế thừa `AbstractPlatformTransactionManager`, có thể gọi `setValidateExistingTransaction(true)` để từ chối một số yêu cầu không tương thích, chẳng hạn isolation khác hoặc inner read-write tham gia outer read-only. Khi bật, phải kiểm tra các service lồng nhau hiện có vì một số luồng trước đây vẫn chạy sẽ bắt đầu bị từ chối.

## 4. Isolation: transaction có thể nhìn thấy dữ liệu nào?

Các hiện tượng điển hình:

- **Dirty read:** T1 nhìn thấy thay đổi chưa commit của T2; T2 rollback làm giá trị từng đọc chưa bao giờ được lưu.
- **Non-repeatable read:** T1 đọc cùng một hàng hai lần, giữa hai lần có transaction khác commit sửa hàng.
- **Phantom read:** T1 chạy hai truy vấn cùng điều kiện và tập các hàng phù hợp thay đổi do transaction khác thêm/xóa/sửa hàng.

| Isolation | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| `DEFAULT` | Theo database | Theo database | Theo database |
| `READ_UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ_COMMITTED` | Ngăn | Có thể | Có thể |
| `REPEATABLE_READ` | Ngăn | Ngăn theo mô hình chuẩn | Có thể theo mô hình chuẩn |
| `SERIALIZABLE` | Ngăn | Ngăn | Ngăn |

Các hằng đầy đủ là `TransactionDefinition.ISOLATION_DEFAULT`, `ISOLATION_READ_UNCOMMITTED`, `ISOLATION_READ_COMMITTED`, `ISOLATION_REPEATABLE_READ` và `ISOLATION_SERIALIZABLE`. Chúng có liên hệ đến các mức `java.sql.Connection.TRANSACTION_*`. Spring đưa yêu cầu xuống driver/manager; database mới quyết định cách khóa, MVCC hay xử lý xung đột.

**Cần hiểu giới hạn của bảng:** các engine có thể ngăn thêm hiện tượng so với bảng, không hỗ trợ một level, hoặc diễn giải `REPEATABLE_READ` theo MVCC khác nhau. `SERIALIZABLE` có thể phát hiện xung đột rồi hủy một transaction, yêu cầu ứng dụng retry an toàn. Isolation không thay thế unique constraints, thao tác UPDATE có điều kiện, version column hay khóa tường minh trong nghiệp vụ cần kiểm soát tranh chấp.

Isolation tùy chỉnh chỉ áp dụng khi **physical transaction mới** được tạo. Inner `REQUIRED` tham gia T1 không tự thay mức isolation T1. Điều này đặc biệt quan trọng khi có method-level annotation và class-level annotation khác nhau.

## 5. Timeout: giới hạn thời gian thực thi

`getTimeout()` là số giây hoặc `TIMEOUT_DEFAULT = -1`. `setTimeout(10)` hoặc `@Transactional(timeout = 10)` yêu cầu giới hạn mười giây đối với transaction **mới**, nếu transaction manager hỗ trợ. Không thể giả định inner `REQUIRED` tham gia transaction đã tồn tại sẽ mở một timeout độc lập cho toàn bộ transaction.

Với Spring JDBC, transaction manager và `JdbcTemplate` có thể áp dụng thời gian còn lại cho các SQL statement; thời điểm kiểm tra và khả năng hủy SQL phụ thuộc driver/database. Timeout của transaction không đồng nghĩa timeout lấy connection từ pool, không tự ngắt mọi mã CPU, không bảo đảm tự dừng lời gọi HTTP đúng giây thứ 10. Cân nhắc statement/query timeout, lock timeout và deadline của request khi cần.

`@Transactional(timeoutString = "10")` là biến thể khai báo bằng chuỗi; trong ứng dụng Spring, có thể dùng giá trị cấu hình được resolve thay vì hardcode. Giá trị timeout có thể bị manager không hỗ trợ từ chối; hãy kiểm chứng trên công nghệ triển khai thực.

## 6. Read-only: gợi ý tối ưu, không phải cơ chế khóa dữ liệu

`setReadOnly(true)`/`@Transactional(readOnly = true)` đánh dấu kỳ vọng chỉ truy vấn dữ liệu. Với một số ORM/driver, Spring có thể giảm flush/check, tối ưu session hoặc đưa read-only flag xuống connection/database.

**Không giả định `readOnly=true` chặn được tất cả UPDATE/INSERT/DELETE.** Có manager bỏ qua hint, có database enforce một phần hoặc toàn bộ. Nếu doanh nghiệp cần chặn ghi, phải dùng quyền database, kiểm soát SQL/endpoint và test trên database đích.

Một service query báo cáo là ví dụ phù hợp `readOnly=true`. Service ghi dữ liệu dùng read-write transaction. Khi đã tham gia outer read-only transaction, method inner `readOnly=false` không chắc có thể đổi resource đang bound.

## 7. Transaction name, rollback rules và TransactionAttribute

`getName()` có ích cho transaction monitor và logs. Trong programmatic transaction gọi `DefaultTransactionDefinition.setName("reconcile-invoices")`. Với Spring declarative transaction, tên thường là tên class đầy đủ + dấu chấm + tên method được intercept; `@Transactional` không có thuộc tính tùy chỉnh tên này.

`TransactionAttribute` mở rộng `TransactionDefinition`, bổ sung semantics cho interceptor, đặc biệt **quy tắc rollback theo exception**. Phân biệt:

| Thiết lập | Cấp API | Cách dùng |
|---|---|---|
| `propagation` / `isolation` / `timeout` / `readOnly` / `name` | `TransactionDefinition` | `DefaultTransactionDefinition` / `@Transactional` |
| `rollbackFor` / `noRollbackFor` | Transaction attributes và interceptor | `@Transactional(rollbackFor = IOException.class)` |
| `transactionManager` / `value` | Chọn manager cho annotation/interceptor | `@Transactional(transactionManager = "billingTx")` |
| `label` | Metadata mở rộng, manager tùy cách sử dụng | `@Transactional(label = {"batch"})` |

Mặc định với `@Transactional`, unchecked `RuntimeException` và `Error` gây rollback; checked exception thông thường không tự động rollback, trừ khi khai báo rules hoặc ứng dụng đã thay chính sách mặc định (Spring 6.2+ cho phép cấu hình default rollback policy). `TransactionDefinition` không có `getRollbackFor()`: nếu sử dụng `PlatformTransactionManager` thủ công, chính code gọi `commit(status)` hoặc `rollback(status)`.

`@Transactional(transactionManager = "billingTx")` chọn **tên bean/qualifier của manager**, không phải transaction name `getName()`. `label` thêm nhãn mô tả mà manager có thể xử lý theo cách riêng; không phải lệnh thực thi SQL.

## 8. Ví dụ Java 17 đầy đủ: quan sát thuộc tính và rollback thực tế

Ví dụ chạy độc lập sau dùng Spring JDBC và H2 in-memory. Nó cấu hình `DefaultTransactionDefinition`, mở transaction bằng `PlatformTransactionManager`, rồi kiểm chứng commit/rollback bằng truy vấn độc lập. Đây là ví dụ **imperative**, không cần Spring Boot.

### Cấu trúc thư mục

```text
transaction-definition-demo/
  pom.xml
  src/main/java/demo/TxDefinitionDemo.java
```

**`pom.xml`** (JDK 17+, Maven; cần tải dependency nếu máy chưa có):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-definition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
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
                <version>3.14.0</version>
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

**`src/main/java/demo/TxDefinitionDemo.java`:**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;

public class TxDefinitionDemo {
    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:tx_defs;DB_CLOSE_DELAY=-1", "sa", "");
        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
                "CREATE TABLE accounts (id BIGINT PRIMARY KEY, balance INT NOT NULL)");
        jdbc.update("INSERT INTO accounts VALUES (1, 100), (2, 50)");

        PlatformTransactionManager manager =
                new JdbcTransactionManager(dataSource);

        var definition = new DefaultTransactionDefinition();
        definition.setName("wallet-transfer");
        definition.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        definition.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        definition.setTimeout(10);
        definition.setReadOnly(false);

        System.out.println(
                "definition: required=" +
                (definition.getPropagationBehavior()
                    == TransactionDefinition.PROPAGATION_REQUIRED) +
                ", readCommitted=" +
                (definition.getIsolationLevel()
                    == TransactionDefinition.ISOLATION_READ_COMMITTED) +
                ", timeout=" + definition.getTimeout() +
                ", readOnly=" + definition.isReadOnly());
        System.out.println("initial: " + balances(jdbc));

        transfer(jdbc, manager, definition, 1, 2, 20, false);
        System.out.println("after commit: " + balances(jdbc));

        try {
            transfer(jdbc, manager, definition, 1, 2, 5, true);
        } catch (IllegalStateException e) {
            System.out.println("caught: " + e.getMessage());
        }
        System.out.println("after rollback: " + balances(jdbc));
    }

    private static void transfer(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager,
            TransactionDefinition definition,
            long from, long to, int amount, boolean simulateFailure) {
        TransactionStatus status = manager.getTransaction(definition);
        try {
            int debited = jdbc.update(
                    "UPDATE accounts SET balance = balance - ? " +
                    "WHERE id = ? AND balance >= ?",
                    amount, from, amount);
            if (debited != 1) {
                throw new IllegalStateException("debit failed");
            }

            if (simulateFailure) {
                throw new IllegalStateException("simulated failure");
            }

            int credited = jdbc.update(
                    "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                    amount, to);
            if (credited != 1) {
                throw new IllegalStateException("credit failed");
            }
            manager.commit(status);
        } catch (RuntimeException e) {
            if (!status.isCompleted()) {
                manager.rollback(status);
            }
            throw e;
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 2", Integer.class);
        return a + "," + b;
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TxDefinitionDemo
```

**Stdout kỳ vọng** (ngoài các thông báo công cụ/logging tùy môi trường):

```text
definition: required=true, readCommitted=true, timeout=10, readOnly=false
initial: 100,50
after commit: 80,70
caught: simulated failure
after rollback: 80,70
```

Giải thích:

1. Tạo `definition` mới chỉ cấu hình chính sách; transaction **chưa bắt đầu**.
2. Lần `getTransaction(definition)` đầu tiên mở T1. Lệnh trừ 20 và cộng 20 cùng dùng connection được Spring gắn vào transaction; `commit(status)` cho kết quả 80,70.
3. Lần sau mở T2, đã trừ 5 nhưng chủ động ném `IllegalStateException` trước khi cộng; nhánh catch gọi `rollback(status)` nên sau đó vẫn là 80,70.
4. `status.isCompleted()` giúp tránh rollback lại khi trạng thái đã kết thúc. Trong code thực tế cũng phải thiết kế xử lý ngoại lệ commit/rollback cẩn thận; tốt nhất dùng abstraction cấp cao để giảm lỗi quản lý vòng đời.

Ở đây `DriverManagerDataSource` đơn giản để minh họa, không phải connection pool nên dùng cho production. Cần dùng cùng `DataSource` giữa `JdbcTransactionManager` và `JdbcTemplate`; nếu tạo connection độc lập bằng API thô, SQL có thể không tham gia transaction mà Spring đang quản lý.

## 9. Từ TransactionDefinition sang @Transactional và TransactionTemplate

Trong Spring application đã bật transaction management, có thể khai báo thuộc tính tương ứng bằng annotation. Ví dụ bên dưới là **Spring service**, không phải chương trình `main` độc lập (cần Spring context, bean `JdbcTemplate` và transaction manager):

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class AccountService {
    private final JdbcTemplate jdbc;

    public AccountService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Integer getBalance(long id) {
        return jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, id);
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = false)
    public void credit(long id, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        int rows = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, id);
        if (rows != 1) {
            throw new IllegalStateException("account not found");
        }
    }
}
```

Class-level `readOnly = true` áp dụng như cấu hình mặc định cho `getBalance()`; annotation cụ thể trên `credit()` được ưu tiên so với metadata ở class. Tuy vậy nếu `credit()` tham gia outer physical transaction đã read-only, thuộc tính mới không chắc có thể thay resource của outer.

Hãy gọi phương thức qua **Spring proxy**. Với proxy mode mặc định, `this.credit(...)` bên trong cùng class bỏ qua interceptor riêng của `credit()`. Trong ứng dụng dùng Spring Framework trực tiếp, kích hoạt `@EnableTransactionManagement` hoặc cấu hình tương đương; Spring Boot thường tự cấu hình khi dependency/manager hợp lệ.

Khi chỉ một đoạn mã cần transaction nhưng không muốn tự quản lý status, dùng `TransactionTemplate`, vốn mở rộng `DefaultTransactionDefinition`:

```java
// Đoạn code trong Spring component đã có manager và JdbcTemplate jdbc.
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
template.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
template.setTimeout(10);

template.executeWithoutResult(status -> {
    int rows = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            5, 1);
    if (rows != 1) {
        throw new IllegalStateException("account not found");
    }
});
```

`TransactionTemplate` xử lý begin/commit/rollback quanh callback. Với unchecked exception, lỗi đi ra khỏi callback khiến template rollback. Với checked exception hoặc logic nghiệp vụ muốn rollback nhưng không ném exception, cần thiết kế xử lý/`status.setRollbackOnly()` rõ ràng.

## 10. Chọn thiết lập phù hợp

| Nhu cầu | Gợi ý | Điều phải kiểm chứng |
|---|---|---|
| Service ghi nhiều bảng như một đơn vị nguyên tử | `REQUIRED` | Cùng manager/resource; propagation không bị cắt bởi lời gọi bất đồng bộ |
| Transaction con thật sự độc lập với outer | `REQUIRES_NEW` | Connection pool và hậu quả outer rollback |
| Chỉ được gọi khi caller đã mở transaction | `MANDATORY` | Lỗi rõ ràng nếu được gọi ngoài transaction |
| Rollback một phần trong JDBC transaction | `NESTED` | Savepoint và manager/driver hỗ trợ |
| Truy vấn báo cáo không ghi dữ liệu | `readOnly = true` | Hint được manager/ORM áp dụng thế nào |
| Muốn tránh dirty read | `READ_COMMITTED` trở lên | Isolation thực của database |
| Muốn giới hạn thời gian giữ resource | `timeout = n` | Driver/statement/query timeout |
| Đoạn code nhỏ cần transaction riêng | `TransactionTemplate` | Callback throw/rollback đúng |

Nếu ứng dụng có nhiều transaction manager, `@Transactional(transactionManager = "ordersTx")` phải chọn đúng bean. Việc có hai manager JDBC/R2DBC hay hai datasource không biến các resource thành **một distributed atomic transaction**. Mỗi transaction cục bộ có phạm vi riêng.

## 11. Các lỗi thường gặp và QA cần thực hiện

1. **Cho rằng isolation ở inner luôn thắng.** Inner `REQUIRED` có thể tham gia physical transaction cũ nên không tái cấu hình isolation.
2. **Nhầm `REQUIRES_NEW` với `NESTED`.** Một bên dùng transaction riêng; bên kia thường dùng savepoint trong transaction đang có.
3. **Hiểu read-only là database permission.** Hãy dùng quyền truy cập/constraint phù hợp khi cần chặn ghi thật.
4. **Hiểu timeout là tự động giết mọi thread.** Cần xác minh timeout của SQL/driver/request và cách phản ứng khi timeout.
5. **Bắt lỗi rồi tưởng rollback-only được xóa.** Outer có thể ném `UnexpectedRollbackException` khi cố commit.
6. **Nghĩ `rollbackFor` thuộc interface `TransactionDefinition`.** Nó thuộc transaction attribute/annotation interceptor, không phải năm getter cơ bản.
7. **Đánh dấu `@Transactional` nhưng gọi bằng `this.method()`.** Self-invocation không đi qua proxy ở chế độ mặc định.
8. **Quên đặt đúng manager và DataSource.** SQL lấy connection ngoài transaction-bound resource có thể không rollback cùng nghiệp vụ.
9. **Kiểm thử chỉ trường hợp thành công.** Cần kiểm thử cả lỗi sau lệnh ghi thứ nhất và đọc lại dữ liệu sau khi transaction kết thúc.

Checklist tích hợp tối thiểu: một case commit có dữ liệu đúng; một case exception khiến toàn bộ thay đổi rollback; một case `REQUIRED` lồng nhau có rollback-only; một case `REQUIRES_NEW` commit độc lập nếu sử dụng; một case `NESTED` với savepoint nếu hỗ trợ; kiểm thử đọc/ghi đồng thời ở isolation lựa chọn; và timeout trên database thật. Để xác minh commit, nên truy vấn bằng connection/transaction mới thay vì chỉ nhìn cache của persistence context cũ.

## 12. Câu hỏi tự kiểm tra

1. Vì sao `TransactionDefinition` có thể tái sử dụng, còn `TransactionStatus` gắn với từng lần thực thi?
2. Inner `REQUIRED` khai báo `SERIALIZABLE` nhưng outer đang `READ_COMMITTED` thì isolation thực tế do đâu quyết định?
3. Nếu inner `REQUIRES_NEW` commit rồi outer rollback, dữ liệu inner có bị rollback không?
4. `NESTED` khác `REQUIRES_NEW` về physical transaction và savepoint?
5. Vì sao `readOnly = true` không thể thay quyền database?
6. Phân biệt `getName()`, `@Transactional(transactionManager = "...")`, `@Transactional(label = "...")`.
7. Khi dùng manager trực tiếp, ai quyết định rollback thay vì `rollbackFor`?

## Tài liệu tham khảo

- Spring Framework, TransactionDefinition API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework, DefaultTransactionDefinition API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html
- Spring Framework, Transaction Abstraction: https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html
- Spring Framework, Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework, Using @Transactional: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework, Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
