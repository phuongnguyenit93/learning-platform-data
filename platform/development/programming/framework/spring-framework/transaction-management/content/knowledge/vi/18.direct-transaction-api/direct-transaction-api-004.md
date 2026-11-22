# Kiểm tra `isNewTransaction`, `isRollbackOnly` và `isCompleted` với Spring TransactionStatus

## 1. Vì sao phải đọc đúng trạng thái giao dịch?

Trong Spring Framework, khi quản lý giao dịch **bằng mã** thông qua `PlatformTransactionManager` hoặc `TransactionTemplate`, ứng dụng có thể nhận một đối tượng `TransactionStatus`. Ba phương thức thường được dùng để kiểm tra vòng đời là:

- `isNewTransaction()` — scope hiện tại có **bắt đầu một transaction mới** hay đang tham gia transaction khác?
- `isRollbackOnly()` — scope/transaction đã được **đánh dấu chỉ được rollback** hay chưa?
- `isCompleted()` — **scope do đối tượng status này đại diện** đã được transaction manager kết thúc hay chưa?

Ba cờ trả lời ba câu hỏi **khác nhau**. Đặc biệt:

- `isNewTransaction() == false` **không** tự đồng nghĩa «không có transaction»: một scope `REQUIRED` có thể đang tham gia transaction của outer method.
- `isRollbackOnly() == true` **không** có nghĩa rollback vật lý **đã xảy ra ngay**. Nó thể hiện trạng thái yêu cầu/không cho phép commit bình thường.
- `isCompleted() == true` **không** chứng minh commit thành công. Status có thể completed **sau commit, rollback hoặc việc kết thúc có lỗi**. Với participating inner scope, status có thể completed khi **outer physical transaction vẫn đang chạy**.

Bài này thuộc mục **API giao dịch trực tiếp**. Trọng tâm là cách đọc ba cờ để debug và kiểm soát `getTransaction(...)`, `commit(...)`, `rollback(...)`; các propagation modes được đưa vào chỉ để làm rõ sự khác nhau của các status.

### Mục tiêu học tập

Sau khi học, bạn có thể:

1. Gọi `PlatformTransactionManager.getTransaction(TransactionDefinition)` để lấy `TransactionStatus`.
2. Hiểu vòng đời status trước/sau `commit` hoặc `rollback`.
3. Phân biệt `setRollbackOnly()` với `rollback(status)`.
4. Giải thích tại sao inner `REQUIRED` có `isNewTransaction=false`, nhưng khi đánh dấu rollback-only thì outer có thể thất bại bằng `UnexpectedRollbackException`.
5. Giải thích tại sao `isCompleted=true` của inner scope không có nghĩa transaction của outer đã kết thúc.
6. So sánh `REQUIRES_NEW` và `NESTED` với `hasSavepoint()` để không đọc sai `isNewTransaction`.
7. Viết và chạy một chương trình Java 17+ kiểm tra cả ba cờ bằng Spring JDBC/H2.

## 2. Từ `PlatformTransactionManager` đến `TransactionStatus`

Spring cung cấp API điều khiển transaction trực tiếp:

```java
PlatformTransactionManager txManager = /* bean được inject */;
TransactionDefinition definition = new DefaultTransactionDefinition();

TransactionStatus status = txManager.getTransaction(definition);
try {
    performBusinessWork();
} catch (RuntimeException | Error ex) {
    txManager.rollback(status);
    throw ex;
}
txManager.commit(status);
```

Đây là **mã minh họa**, chưa định nghĩa `txManager` hoặc `performBusinessWork()`. Cấu trúc cố ý đặt `commit(status)` **ngoài khối catch**, vì theo hợp đồng `PlatformTransactionManager`, khi `commit` đã trả về **hoặc ném lỗi**, status đã được kết thúc/dọn dẹp; **không gọi `rollback(status)` lần nữa chỉ vì `commit` bị lỗi**.

### 2.1. Ba đối tượng có vai trò khác nhau

| API | Vai trò |
| --- | --- |
| `TransactionDefinition` | Định nghĩa propagation, isolation, timeout, read-only và tên transaction nếu có. |
| `PlatformTransactionManager` | Bắt đầu/tham gia transaction, quyết định commit/rollback và dọn tài nguyên. |
| `TransactionStatus` | Đại diện **một lần yêu cầu transaction cụ thể**, chứa thông tin để kiểm tra và yêu cầu rollback. |

Một transaction manager có thể trả về nhiều status trong cùng một call stack. Ví dụ:

```text
TransactionStatus outer = txManager.getTransaction(REQUIRED);
    -> outer.isNewTransaction() == true

    TransactionStatus inner = txManager.getTransaction(REQUIRED);
        -> inner.isNewTransaction() == false
        -> inner tham gia physical transaction do outer tạo

    txManager.commit(inner);
        -> inner.isCompleted() == true
        -> physical transaction của outer CHƯA nhất thiết commit

txManager.commit(outer);
    -> outer.isCompleted() == true
    -> nếu mọi điều kiện hợp lệ, physical transaction mới commit
```

**Đừng coi hai status là hai kết nối hoặc hai physical transactions.** `TransactionStatus` là đối tượng cho một **scope quản lý**, còn physical transaction tùy thuộc propagation và transaction manager.

### 2.2. Status khác với `TransactionSynchronizationManager`

Đôi khi người học dùng:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

Đây là **đoạn minh họa**, cần import `org.springframework.transaction.support.TransactionSynchronizationManager`. Nó cho biết Spring xem transaction actual đang active trên **thread hiện tại** trong mô hình imperative. Nhưng `active=true` không phân biệt outer T1 với inner T2, không thay thế việc đọc `TransactionStatus` của scope cụ thể; `active=false` cũng không thay thế kiểm tra mọi database resource riêng lẻ.

`TransactionStatus` giúp trả lời **ai có scope mới, ai đánh dấu rollback-only, scope nào đã hoàn thành**. `TransactionSynchronizationManager` hỗ trợ chẩn đoán **context tài nguyên của thread**. Cả hai cần được đặt trong ngữ cảnh transaction manager phù hợp.

## 3. `isNewTransaction()` — scope này có khởi tạo transaction mới?

Chữ ký:

```java
boolean isNewTransaction();
```

Giá trị `true` có ý nghĩa: trong môi trường Spring transaction manager thông thường, lần `getTransaction(...)` tương ứng đã **khởi tạo transaction mới** thay vì chỉ tham gia transaction có sẵn.

### 3.1. Ví dụ `REQUIRED` ở hai vị trí

```text
Không có transaction hiện hành:
  getTransaction(REQUIRED) -> outer status
    isNewTransaction = true

T1 đang chạy:
  getTransaction(REQUIRED) -> inner status
    isNewTransaction = false
    inner đang tham gia physical T1
```

Điều này rất quan trọng khi debug: nếu inner `REQUIRED` báo `false`, **không có lỗi**; đó là hành vi đúng vì inner sử dụng transaction do outer mở.

Nhưng `isNewTransaction() == false` **không chứng minh có physical transaction hiện hành**. Với `PROPAGATION_SUPPORTS` hoặc `PROPAGATION_NOT_SUPPORTED` khi không có transaction, Spring cũng có thể trả status `false` mà không có physical transaction để commit. Trong Spring 6.2, các API như `hasTransaction()` trên `TransactionExecution` và quan sát resource context có thể giúp chẩn đoán sâu hơn. Với database manager khác, đừng suy diễn chỉ từ một boolean.

### 3.2. `REQUIRES_NEW` và `NESTED`

Khi outer T1 đang chạy:

- Inner `REQUIRES_NEW` yêu cầu physical transaction T2 **độc lập**, tạm treo T1: inner `isNewTransaction()` thường là `true`.
- Inner `NESTED` với JDBC savepoint support **dùng chung T1**, nhưng có savepoint: inner `isNewTransaction()` thường `false` và `hasSavepoint()` là `true`.
- Inner `REQUIRED` cũng thường `isNewTransaction=false`, nhưng `hasSavepoint=false`.

Dùng thêm `hasSavepoint()` để tránh nhầm nested scope với participating `REQUIRED`. Khi không có outer transaction, `NESTED` có thể hành xử như bắt đầu một transaction mới; kết quả tùy ngữ cảnh và manager.

### 3.3. Sai lầm cần tránh

**Không** suy ra từ `isNewTransaction=true` rằng transaction đã commit; status đang active vẫn có thể rollback. **Không** suy ra từ `false` rằng mọi thao tác database đều autocommit. Và **không** dùng một status đã completed rồi gọi manager commit lần thứ hai chỉ vì `isNewTransaction` vẫn phản ánh nguồn gốc của status ấy.

## 4. `isRollbackOnly()` — yêu cầu rollback, chưa chắc đã rollback

Chữ ký:

```java
boolean isRollbackOnly();
void setRollbackOnly();
```

`isRollbackOnly()` kiểm tra **trạng thái bị đánh dấu rollback-only**. Trong những implementation thông dụng như `DefaultTransactionStatus`, nó phản ánh marker cục bộ của scope **hoặc** marker rollback-only của underlying transaction.

### 4.1. `setRollbackOnly` khác `rollback(status)`

```java
TransactionStatus status = txManager.getTransaction(definition);
status.setRollbackOnly();

// Ngay lúc này:
// status.isRollbackOnly() == true
// status.isCompleted() thường vẫn false

txManager.commit(status);
// Manager xử lý rollback vì status đã được đánh dấu.
```

Đây là **mã minh họa**, cần `txManager` và `definition`. Gọi `setRollbackOnly()` **chỉ đánh dấu**; chưa tự dọn scope và chưa tương đương `rollback(status)` thực thi hoàn tất. Với **transaction mới do chính scope sở hữu**, `commit(status)` khi có **local rollback-only** thường thực hiện rollback có chủ đích và **không ném `UnexpectedRollbackException` chỉ vì caller tự yêu cầu rollback**.

Ngược lại, `txManager.rollback(status)` là thao tác **kết thúc** scope bằng đường rollback. Sau khi manager thực hiện thành công, `status.isCompleted()` thường là `true`.

### 4.2. Participating scope đánh dấu rollback-only

Kịch bản khó nhất là hai `REQUIRED` cùng chia sẻ T1:

```text
outer = getTransaction(REQUIRED)  [new = true]     -> T1
  UPDATE A
  inner = getTransaction(REQUIRED) [new = false]   -> join T1
    UPDATE B
    inner.setRollbackOnly()                       -> inner local marker
    inner.isRollbackOnly() = true
  commit(inner)                                   -> đóng inner logical scope,
                                                     đánh dấu T1 rollback-only
  inner.isCompleted() = true
  outer.isRollbackOnly() = true (với JDBC demo)
commit(outer)                                     -> ROLLBACK T1
                                                   -> UnexpectedRollbackException
```

**Tại sao outer nhận `UnexpectedRollbackException`?** Outer code tưởng mình đang hoàn thành hợp lệ và gọi commit, nhưng physical transaction T1 đã bị một participating scope yêu cầu rollback. Spring cần báo rằng **commit đã không xảy ra**. Lỗi này khác với việc **chính outer status** gọi `setRollbackOnly()` rồi chủ động yêu cầu rollback lúc commit.

Lưu ý: marker cục bộ của inner và marker toàn cục của underlying transaction là các khái niệm khác. Ngay sau `inner.setRollbackOnly()`, trước khi kết thúc participating scope, không nên mặc định rằng mọi status khác lập tức thấy cùng giá trị; hãy kiểm tra sau khi manager đã xử lý `commit(inner)`/`rollback(inner)`. Cấu hình transaction manager như `globalRollbackOnParticipationFailure` có thể ảnh hưởng vài đường rollback do exception; bài lab dùng mặc định của `DataSourceTransactionManager`.

### 4.3. Vì sao `isRollbackOnly=false` không phải giấy chứng nhận commit?

Một status đang chạy có thể đang `false`, nhưng:

- SQL sau đó lỗi, transaction manager có thể đánh dấu rollback-only.
- Outer method có thể ném unchecked exception làm transaction rollback.
- Database có thể thất bại khi commit vì constraint, kết nối, deadlock hoặc timeout.
- Caller có thể quyết định `rollback(status)` dù chưa từng gọi `setRollbackOnly()`.

Vì vậy hãy xem `isRollbackOnly()` là **một tín hiệu trạng thái hiện tại**, không phải lời bảo đảm cuối cùng rằng commit chắc chắn thành công.

## 5. `isCompleted()` — scope đã kết thúc, không phải kết quả commit

Chữ ký:

```java
boolean isCompleted();
```

Theo vòng đời `PlatformTransactionManager` thông dụng:

- Ngay sau `getTransaction(...)`, status mới nhận được thường có `isCompleted() == false`.
- Sau `commit(status)` thành công, status có `isCompleted() == true`.
- Sau `rollback(status)` thành công, status cũng có `isCompleted() == true`.
- Ngay cả khi một `commit(status)` ném transaction exception, hợp đồng manager yêu cầu transaction/status đã được hoàn tất và dọn tài nguyên; **không gọi `rollback(status)` để «thử sửa» sau một commit failure**.

Điểm dễ nhầm: `isCompleted()` nói về **scope của status này**, **không nhất thiết** về toàn bộ physical transaction có thể vẫn do outer scope giữ.

```text
Outer T1 đang mở:
  outer.isCompleted() = false

Inner REQUIRED join T1:
  inner.isCompleted() = false

manager.commit(inner):
  inner.isCompleted() = true       <-- inner logical scope đã kết thúc
  outer.isCompleted() = false      <-- T1 vẫn mở
  physical T1 chưa commit

manager.commit(outer):
  outer.isCompleted() = true       <-- T1 kết thúc
```

**Không được dùng `isCompleted()==true` để suy ra «đã commit thành công».** Một scope vừa rollback cũng completed. Nếu cần kết quả nghiệp vụ, hãy quan sát **manager outcome, exception, transaction synchronization callback hoặc dữ liệu sau boundary**. `isCompleted()` là cờ **vòng đời**, không phải enum `COMMITTED/ROLLED_BACK`.

### 5.1. Không tái sử dụng completed status

Sai:

```java
txManager.commit(status);
txManager.rollback(status); // Sai: status đã completed.
```

Đây là **đoạn minh họa lỗi**. Với `AbstractPlatformTransactionManager`, gọi `commit` hoặc `rollback` trên status đã completed gây `IllegalTransactionStateException`. Không nên giữ `TransactionStatus` qua nhiều requests hoặc cache nó như một object có thể tái sử dụng. **Mỗi lần `getTransaction(...)` tạo một scope/status riêng, và mỗi scope cần được kết thúc đúng một lần.**

## 6. Bảng tổng hợp ba cờ qua các kịch bản

Trong bảng, giả định **Spring JDBC `DataSourceTransactionManager`**, propagation được áp dụng qua `PlatformTransactionManager.getTransaction(...)`, và outer đã có physical transaction nếu có mô tả «inner».

| Scope/Thời điểm | `isNewTransaction()` | `isRollbackOnly()` | `isCompleted()` | Diễn giải |
| --- | --- | --- | --- | --- |
| Outer `REQUIRED`, chưa có transaction, vừa bắt đầu | `true` | `false` | `false` | Outer mở T1, đang active. |
| Inner `REQUIRED` tham gia T1 | `false` | `false` lúc đầu | `false` | Thêm logical scope, không mở T2. |
| Inner sau `setRollbackOnly()`, trước khi kết thúc | `false` | `true` | `false` | Inner được đánh dấu, chưa dọn scope. |
| Inner sau `commit(inner)` đã xử lý rollback-only | Không dùng cờ new để quyết định tiếp | Không dùng để quyết định tiếp | `true` | Inner scope hoàn tất; T1 có thể vẫn mở và bị đánh dấu rollback-only. |
| Outer T1 sau inner đánh dấu global rollback-only | `true` | `true` | `false` | Outer còn active nhưng không thể commit bình thường. |
| Outer T1 sau commit bị rollback bất ngờ | Không tái sử dụng status | Không tái sử dụng status | `true` | Caller nhận `UnexpectedRollbackException`. |
| Inner `REQUIRES_NEW` bên trong T1 | `true` | `false` lúc đầu | `false` | Mở T2 độc lập, suspend T1. |
| Inner `NESTED` với JDBC savepoint | `false` | `false` lúc đầu | `false` | Cùng T1, thường `hasSavepoint=true`. |
| Outer explicit `rollback(status)` đã hoàn tất | Nguồn gốc status không quan trọng | Không cần kiểm tra cờ | `true` | Scope đã rollback; không gọi commit lại. |

Bảng thể hiện **ý nghĩa thông thường** trong cấu hình minh họa; behavior chi tiết có thể khác giữa JTA, JPA, reactive transactions và các manager/cấu hình khác nhau. Đừng kết luận kết quả vật lý chỉ bằng một tuple booleans không có ngữ cảnh.

## 7. Dự án Java 17+ chạy được: đo cả ba cờ

Dự án sử dụng Spring Framework **6.2.8**, Spring JDBC và H2 **2.3.232**. Ta gọi **`PlatformTransactionManager` trực tiếp**, **không dùng `@Transactional` trên service**, để thấy chính xác thời điểm status xuất hiện và được kết thúc.

### 7.1. Cấu trúc thư mục

```text
transaction-status-flags/
├── pom.xml
└── src/main/java/example/StatusFlagsDemo.java
```

### 7.2. `pom.xml`

Lưu đoạn XML này **nguyên vẹn** vào `pom.xml`. Dòng đầu tiên là XML declaration; **không đặt comment trước `<?xml ... ?>`**.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>transaction-status-flags</artifactId>
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
                    <mainClass>example.StatusFlagsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` tạo `ApplicationContext`/beans; `spring-jdbc` có `JdbcTemplate` và `DataSourceTransactionManager`; `spring-tx` cung cấp contract transaction; H2 là database JDBC in-memory. Chúng ta **không cần `@EnableTransactionManagement`** vì toàn bộ transaction trong lab được bắt đầu **thủ công** bằng `PlatformTransactionManager` — đây là điểm khác với declarative proxy mode.

### 7.3. `src/main/java/example/StatusFlagsDemo.java`

```java
package example;

import java.util.List;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.DefaultTransactionDefinition;

public class StatusFlagsDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            PlatformTransactionManager manager =
                context.getBean(PlatformTransactionManager.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            commitNewTransaction(manager, jdbc);
            markNewTransactionRollbackOnly(manager, jdbc);
            participatingRequiredRollback(manager, jdbc);
            independentRequiresNew(manager, jdbc);
            nestedSavepointRollback(manager, jdbc);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:flags_demo;DB_CLOSE_DELAY=-1");
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
                DataSource dataSource) {
            DataSourceTransactionManager manager =
                new DataSourceTransactionManager(dataSource);
            manager.setNestedTransactionAllowed(true);
            return manager;
        }
    }

    private static DefaultTransactionDefinition definition(int propagation) {
        DefaultTransactionDefinition definition =
            new DefaultTransactionDefinition();
        definition.setPropagationBehavior(propagation);
        return definition;
    }

    private static void show(String label, TransactionStatus status) {
        System.out.println(
            label
                + ": new=" + status.isNewTransaction()
                + ", rollbackOnly=" + status.isRollbackOnly()
                + ", completed=" + status.isCompleted()
                + ", savepoint=" + status.hasSavepoint()
        );
    }

    private static void reset(JdbcTemplate jdbc) {
        // Chạy ngoài transaction trước từng case.
        jdbc.execute("DROP TABLE IF EXISTS events");
        jdbc.execute(
            "CREATE TABLE events (" +
            "id INT PRIMARY KEY, label VARCHAR(40) NOT NULL)"
        );
    }

    private static List<String> rows(JdbcTemplate jdbc) {
        return jdbc.queryForList(
            "SELECT label FROM events ORDER BY id",
            String.class
        );
    }

    private static void insert(JdbcTemplate jdbc, int id, String label) {
        jdbc.update(
            "INSERT INTO events(id, label) VALUES (?, ?)",
            id,
            label
        );
    }

    private static void commitNewTransaction(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 1: new transaction commits");

        TransactionStatus status = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        show("start", status);
        insert(jdbc, 1, "committed");
        manager.commit(status);

        System.out.println("after commit: completed=" + status.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }

    private static void markNewTransactionRollbackOnly(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 2: local rollback-only on new transaction");

        TransactionStatus status = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 1, "discard");
        status.setRollbackOnly();
        show("marked", status);

        // Dù gọi commit, manager chuyển sang rollback có chủ đích.
        manager.commit(status);
        System.out.println("after commit request: completed="
                           + status.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }

    private static void participatingRequiredRollback(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 3: inner REQUIRED marks shared transaction");

        TransactionStatus outer = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 1, "outer");
        show("outer start", outer);

        TransactionStatus inner = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 2, "inner");
        show("inner start", inner);
        inner.setRollbackOnly();
        show("inner marked", inner);

        // Kết thúc participating scope, không commit T1.
        manager.commit(inner);
        System.out.println("inner after end: completed=" + inner.isCompleted());
        show("outer after inner", outer);

        try {
            manager.commit(outer);
        } catch (UnexpectedRollbackException expected) {
            System.out.println(
                "outer commit outcome: UnexpectedRollbackException"
            );
        }
        System.out.println("outer after attempt: completed="
                           + outer.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }

    private static void independentRequiresNew(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 4: REQUIRES_NEW commits independently");

        TransactionStatus outer = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 1, "outer");

        TransactionStatus inner = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRES_NEW)
        );
        show("inner REQUIRES_NEW", inner);
        insert(jdbc, 2, "inner");
        manager.commit(inner);
        System.out.println("inner after commit: completed="
                           + inner.isCompleted());
        show("outer resumed", outer);

        manager.rollback(outer);
        System.out.println("outer after rollback: completed="
                           + outer.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }

    private static void nestedSavepointRollback(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 5: NESTED rolls back to savepoint");

        TransactionStatus outer = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 1, "outer");

        TransactionStatus nested = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_NESTED)
        );
        show("inner NESTED", nested);
        insert(jdbc, 2, "nested");

        // Rollback phần sau savepoint, không tự hủy T1.
        manager.rollback(nested);
        System.out.println("nested after rollback: completed="
                           + nested.isCompleted());
        show("outer after nested", outer);
        manager.commit(outer);

        System.out.println("outer after commit: completed="
                           + outer.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }
}
```

### 7.4. Cách chạy

Tạo hai tệp theo cấu trúc project. Trong thư mục `transaction-status-flags`, sử dụng JDK 17 trở lên và Maven 3.9+:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

### 7.5. Output dự kiến

Với Spring JDBC `DataSourceTransactionManager` và H2 như project, các dòng chương trình in ra theo thứ tự là:

```text
CASE 1: new transaction commits
start: new=true, rollbackOnly=false, completed=false, savepoint=false
after commit: completed=true
rows=[committed]
CASE 2: local rollback-only on new transaction
marked: new=true, rollbackOnly=true, completed=false, savepoint=false
after commit request: completed=true
rows=[]
CASE 3: inner REQUIRED marks shared transaction
outer start: new=true, rollbackOnly=false, completed=false, savepoint=false
inner start: new=false, rollbackOnly=false, completed=false, savepoint=false
inner marked: new=false, rollbackOnly=true, completed=false, savepoint=false
inner after end: completed=true
outer after inner: new=true, rollbackOnly=true, completed=false, savepoint=false
outer commit outcome: UnexpectedRollbackException
outer after attempt: completed=true
rows=[]
CASE 4: REQUIRES_NEW commits independently
inner REQUIRES_NEW: new=true, rollbackOnly=false, completed=false, savepoint=false
inner after commit: completed=true
outer resumed: new=true, rollbackOnly=false, completed=false, savepoint=false
outer after rollback: completed=true
rows=[inner]
CASE 5: NESTED rolls back to savepoint
inner NESTED: new=false, rollbackOnly=false, completed=false, savepoint=true
nested after rollback: completed=true
outer after nested: new=true, rollbackOnly=false, completed=false, savepoint=false
outer after commit: completed=true
rows=[outer]
```

Đây là output **theo semantics của cấu hình cụ thể**. Maven/Spring có thể in thêm log; khi dùng manager khác (JTA, Hibernate/JPA, reactive) phải kiểm tra các chi tiết triển khai thay vì giả định mọi flag/log luôn giống hệt nhau.

### 7.6. Phân tích từng case

**CASE 1 — Transaction mới commit thành công**

`getTransaction(REQUIRED)` chạy khi không có transaction nào khác, nên status có `new=true`, `rollbackOnly=false`, `completed=false`. `insert` chạy trong JDBC T1. Khi `manager.commit(status)` hoàn tất, scope được đánh dấu `completed=true` và hàng `committed` xuất hiện sau boundary. Đây là trường hợp dễ đọc nhất, nhưng không nên suy ra mọi status `completed=true` đều commit thành công — case 2 và 3 cho thấy ngược lại.

**CASE 2 — Đánh dấu rollback-only trong transaction mới**

Status mới cũng có `isNewTransaction=true`. Code chạy `insert` rồi `status.setRollbackOnly()`; lúc này `rollbackOnly=true` và `completed=false`. Khi ứng dụng gọi `manager.commit(status)`, Spring thấy marker cục bộ và **rollback có chủ đích**. Lời gọi hoàn thành, `completed=true` nhưng database **không còn** hàng `discard`. Đây là bằng chứng quan trọng rằng `completed` không phải `committed`, còn `setRollbackOnly` chỉ là marker chứ không lập tức hoàn tất giao dịch.

**CASE 3 — Inner REQUIRED đánh dấu chung physical transaction**

Outer T1 mở đầu, `outer.isNewTransaction=true`. Inner `REQUIRED` join T1, nên `inner.isNewTransaction=false`. Inner ghi một hàng rồi tự `setRollbackOnly()`; ban đầu marker là thuộc inner scope. Khi `manager.commit(inner)` được gọi, Spring không commit vật lý T1 mà xử lý participating scope và đánh dấu **T1 rollback-only**. Vì vậy `inner.isCompleted=true` trong khi `outer.isCompleted=false` và `outer.isRollbackOnly=true`. Khi outer sau đó yêu cầu commit, Spring rollback T1 và ném `UnexpectedRollbackException`. Hai hàng đều không tồn tại sau boundary. Không nhầm `inner.isCompleted=true` với «T1 đã commit».

**CASE 4 — Inner REQUIRES_NEW độc lập**

Outer T1 có một bản ghi chưa commit. Khi inner được yêu cầu với `REQUIRES_NEW`, manager suspend T1 và tạo T2: inner status `new=true`. Inner ghi và commit T2, status inner `completed=true`. Sau đó T1 được resume; `outer.isRollbackOnly=false` và vẫn chưa hoàn tất. Khi ứng dụng rollback T1, chỉ hàng `outer` bị hủy; hàng `inner` đã commit trong T2 vẫn còn. Đây là lý do `isNewTransaction=true` của inner mang ý nghĩa vật lý khác inner `REQUIRED` tham gia.

**CASE 5 — Inner NESTED dựa trên savepoint**

Trong Spring JDBC với savepoint hỗ trợ, inner `NESTED` có `new=false` và `hasSavepoint=true`. Inner ghi dữ liệu rồi `rollback(nested)` quay về savepoint, chỉ hủy thay đổi inner. Status nested đã `completed=true`; outer T1 vẫn mở, `rollbackOnly=false`, nên có thể commit hàng `outer`. Nếu database/transaction manager không hỗ trợ savepoints, cơ chế `NESTED` có thể bị từ chối; lab chủ động bật `setNestedTransactionAllowed(true)`.

## 8. Đọc status trong `TransactionTemplate`

Với những use cases thông thường, Spring khuyến nghị **`TransactionTemplate`** để tránh boilerplate `getTransaction`/`commit`/`rollback` thủ công.

```java
TransactionTemplate template = new TransactionTemplate(txManager);

template.executeWithoutResult(status -> {
    System.out.println(status.isNewTransaction());
    System.out.println(status.isRollbackOnly());
    System.out.println(status.isCompleted());

    doSomeJDBCWork();
    if (businessRuleFailed()) {
        status.setRollbackOnly();
    }
});
```

Đây là **mã minh họa**, cần khai báo `txManager`, `doSomeJDBCWork` và `businessRuleFailed`. Callback nhận một `TransactionStatus`; bạn có thể đọc ba cờ và đánh dấu rollback-only trong callback. **Không tự gọi `txManager.commit(status)` hoặc `rollback(status)` ngay trong callback**; `TransactionTemplate` chịu trách nhiệm kết thúc scope khi callback return/throw. Ngay bên trong callback, `isCompleted()` thông thường vẫn `false` vì template chưa kết thúc transaction.

### 8.1. Nếu callback tự gọi `setRollbackOnly()`

```text
template.execute(callback)
    ├── Template mở/join transaction
    ├── Callback nhận status
    ├── Callback gọi status.setRollbackOnly()
    └── Template xử lý kết thúc scope
        └── New scope: rollback thay vì commit
```

Khi template đang **tham gia outer `REQUIRED` transaction**, marker của inner có thể làm outer rollback-only. Không hiểu `setRollbackOnly` như «chỉ hủy các câu SQL trong callback» nếu callback đang chia sẻ T1. Muốn savepoint cục bộ, xem `NESTED` khi hỗ trợ; muốn transaction vật lý độc lập, xem `REQUIRES_NEW`.

### 8.2. Status từ `@Transactional` proxy

Trong một method đang được Spring `@Transactional` interceptor quản lý, có thể truy cập current status bằng:

```java
TransactionStatus status =
    TransactionAspectSupport.currentTransactionStatus();
```

Đây là **đoạn minh họa**, cần import `org.springframework.transaction.interceptor.TransactionAspectSupport` và phải chạy trong context có transaction aspect thực sự. Nếu gọi ngoài transaction AOP invocation, API có thể ném `NoTransactionException`. Đừng tự suy rằng mọi request có `@Transactional` annotation trong source đều tạo được status — self-invocation, object tự tạo `new` và cấu hình context/proxy sai có thể bỏ qua interception.

`TransactionAspectSupport.currentTransactionStatus()` khác `PlatformTransactionManager.getTransaction(...)` ở chỗ phương thức đầu lấy **status của AOP invocation đang chạy**, còn phương thức sau **yêu cầu transaction scope** bằng mã. Không trộn các status từ nhiều manager hoặc đóng một status không thuộc quyền điều khiển của đoạn code hiện tại.

## 9. Những sai lầm phổ biến

### 9.1. «`isNewTransaction=false` nghĩa là SQL chạy ngoài transaction»

Sai. Inner `REQUIRED` join T1 có `false` nhưng `JdbcTemplate` vẫn sử dụng transaction-bound connection của T1. Hãy xác định propagation và physical transaction trước khi kết luận.

### 9.2. «`isRollbackOnly=true` nghĩa là database đã rollback»

Sai. Marker có thể được đặt khi transaction vẫn active, còn các thay đổi chưa commit. Rollback hoàn tất ở một boundary do manager xử lý, không phải ngay khi boolean thành true.

### 9.3. «`isCompleted=true` nghĩa là commit thành công»

Sai. Sau explicit rollback hoặc sau một commit attempt bị chuyển thành rollback, status vẫn completed. Nếu cần biết outcome, ghi nhận exception, transaction synchronization status hoặc xác nhận dữ liệu sau khi boundary kết thúc.

### 9.4. «Inner scope completed thì outer transaction cũng completed»

Sai. Với `REQUIRED`, participating inner scope có thể kết thúc còn outer giữ physical T1. Case 3 thể hiện inner `completed=true` đồng thời outer `completed=false`.

### 9.5. «Dùng `commit(status)` rồi bắt lỗi và gọi `rollback(status)`»

Sai. Hợp đồng `PlatformTransactionManager.commit` quy định status đã được hoàn tất/dọn dẹp ngay cả khi commit ném exception. Gọi `rollback` lại dễ nhận `IllegalTransactionStateException` và che giấu lỗi gốc. Hãy tách giai đoạn business work và commit trong pattern quản lý trực tiếp hoặc dùng `TransactionTemplate`.

### 9.6. «Cứ gọi `setRollbackOnly` rồi return bình thường là caller biết rollback»

Không hẳn. Trong transaction mới, manager có thể hoàn tất rollback có chủ đích mà không ném ngoại lệ; nếu code return một kết quả «success» giả, tầng gọi có thể không biết tác vụ đã bị hủy. Hãy thiết kế return value/exception domain cho đúng. Với participating scope làm outer rollback-only, caller outer có thể nhận `UnexpectedRollbackException` khi cố commit.

### 9.7. «Có status new=true thì SQL nào cũng tự động được enlist»

Không. Status phải đi với đúng transaction manager và tài nguyên. JDBC connection lấy ngoài cơ chế Spring-aware có thể không tham gia transaction. Với `DataSourceTransactionManager`, dùng `JdbcTemplate`/`DataSourceUtils` đúng datasource; các hệ thống HTTP/email/message broker bên ngoài không tự rollback theo JDBC status.

### 9.8. «Đọc cờ trên status cũ trong request mới»

Sai. Status là trạng thái của **một scope giao dịch cụ thể**, không phải global singleton hay session state để cache. Không lưu `TransactionStatus` trong field dùng chung giữa các threads hoặc tái sử dụng sau completed.

### 9.9. «Có thể đọc `isCompleted` để quyết định commit lần nữa»

Sai. Khi completed, scope đã kết thúc. Không gọi tiếp `commit`/`rollback`. Kiểm tra `isCompleted()` có ích để diagnostic trong cleanup path, nhưng không biến status thành đối tượng được tái sử dụng.

### 9.10. «Manual API và declarative API luôn cho cùng status object»

Không nhất thiết. Với declarative method, AOP tạo/giữ status cho invocation; manual `getTransaction` tạo thêm một scope có propagation đã chọn. Chúng có thể cùng physical transaction nhưng không là cùng status object. Đừng tự `rollback` một status lấy từ AOP nếu bạn không quản lý boundary đó.

### 9.11. «`isRollbackOnly=false` nghĩa là commit sẽ thành công 100%»

Sai. Constraint validation, flush, network/DB disconnect, deadlock hoặc logic sau đó có thể gây rollback/commit exception. Flag là quan sát **tại một thời điểm**, không phải lời tiên tri về outcome cuối.

### 9.12. «`NESTED` luôn tạo transaction vật lý mới»

Sai trong JDBC savepoint model: `isNewTransaction=false`, `hasSavepoint=true`. Khác `REQUIRES_NEW`, nested scope không thể commit physical transaction độc lập và outer rollback vẫn hủy toàn bộ thay đổi của T1.

## 10. Viết unit/integration test cho ba cờ

Một test có giá trị cần kiểm tra **status và kết quả database**. Không chỉ assert boolean rồi tuyên bố hệ thống đảm bảo commit.

| Test | Assertion nên có |
| --- | --- |
| New `REQUIRED` | `new=true`, `completed=false` khi active; sau commit `completed=true`; dữ liệu tồn tại |
| New transaction tự `setRollbackOnly` | Trước kết thúc `rollbackOnly=true`; sau commit request `completed=true`; dữ liệu không tồn tại |
| Participating `REQUIRED` | Inner `new=false`, sau inner end `completed=true` nhưng outer `completed=false` |
| Inner rollback-only ảnh hưởng outer | Outer nhận `UnexpectedRollbackException` ở commit; cả outer/inner writes rollback |
| `REQUIRES_NEW` | Inner `new=true`; inner commit trước outer rollback; dữ liệu inner vẫn còn |
| JDBC `NESTED` | Inner `new=false` và `hasSavepoint=true`; rollback nested không buộc outer rollback |
| Gọi manager lần thứ hai với completed status | Kiểm tra `IllegalTransactionStateException` trong test riêng; không dùng như business flow |
| Exception khi commit | Không gọi `rollback` lại trên status đã completed; log nguyên nhân gốc |

### 10.1. Test có nhiều transaction managers

Nếu dùng `DataSourceTransactionManager` cho datasource A và manager JPA/JTA cho datasource B, phải xác định status đến từ **manager nào**. `isNewTransaction()` của một manager không xác nhận mọi resource trên JVM đang dùng một physical transaction chung. Đặt tên manager rõ ràng và test các resource thực sự tham gia.

### 10.2. Test dưới Spring Test `@Transactional`

Khi test method do Spring Test tự mở một transaction bao ngoài, một lời gọi `REQUIRED` trong code của bạn có thể có `isNewTransaction=false` dù cùng lời gọi trong `main()` khi không có outer lại là `true`. Đó là **khác biệt ngữ cảnh transaction**, không phải lỗi status. Các test của lab chủ động dùng `main()` và reset ngoài transaction để tránh transaction của test harness che kết quả.

### 10.3. Reactive transactions không dùng nguyên xi mô hình JDBC thread-bound

Với reactive data access, dùng `ReactiveTransactionManager`/`TransactionalOperator` và đối tượng `ReactiveTransaction` tương ứng. Reactive transaction context có thể gắn với Reactor Context thay vì Java thread hiện tại. Bài này cố ý dùng **imperative `PlatformTransactionManager` + Spring JDBC** để minh họa trạng thái một cách quan sát được, không giả định các primitive quản lý thread-bound giống hệt cho mọi reactive pipeline.

## 11. Bài tập

**Bài 1 — Dự đoán trạng thái:** Không có transaction nào; gọi `getTransaction(REQUIRED)`. Trước `commit`, hãy dự đoán ba cờ. Sau commit, có thể dựa vào `completed=true` để biết commit chắc chắn thành công không? Kiểm tra thêm database.

**Bài 2 — Rollback-only cục bộ:** Trong CASE 2, thay `status.setRollbackOnly(); manager.commit(status);` bằng `manager.rollback(status);`. Hai đường đi khác nhau về API thế nào? Kết quả database giống nhau hay khác? Khi nào `completed` chuyển thành true?

**Bài 3 — Inner participation:** Trong CASE 3, bỏ `inner.setRollbackOnly()` rồi chạy. Dự đoán outer có nhận `UnexpectedRollbackException` không. Giải thích vì sao `manager.commit(inner)` không thực sự commit physical T1.

**Bài 4 — Thời điểm thấy global rollback-only:** Trong CASE 3, thử in `outer.isRollbackOnly()` trước và sau `manager.commit(inner)`. Phân biệt marker cục bộ của inner với marker của physical transaction sau khi participating scope kết thúc.

**Bài 5 — Hai physical transactions:** Trong CASE 4, đổi `REQUIRES_NEW` thành `REQUIRED`. Nếu outer rollback, inner row còn tồn tại không? `isNewTransaction` của inner có thay đổi không?

**Bài 6 — Savepoint:** Trong CASE 5, bỏ `manager.rollback(nested)` và đổi thành `manager.commit(nested)`, rồi cho outer rollback. Dự đoán inner row còn không; giải thích vì sao nested commit không là physical commit.

**Bài 7 — Double finish:** Trong bản sao test, sau khi `manager.commit(status)` hãy thử gọi `manager.commit(status)` lần nữa, bắt đúng `IllegalTransactionStateException`. Không đặt logic này trong service production.

**Bài 8 — Refactor sang template:** Viết lại CASE 2 với `TransactionTemplate.executeWithoutResult(status -> ...)`. Đặt `status.setRollbackOnly()` trong callback; không gọi `manager.commit(status)` bằng tay. So sánh database output.

**Bài 9 — Domain policy:** Thiết kế một hàm trả kết quả `SUCCESS`/`REJECTED` thay vì chỉ in status. Nếu `rollbackOnly=true` do rule thất bại, hàm cần làm gì để không báo thành công giả? Thảo luận exception domain so với return value.

**Bài 10 — Cleanup khi commit lỗi:** Viết pseudocode quản lý exception theo pattern được Spring hướng dẫn: `rollback` khi business work ném lỗi **trước commit**, nhưng **không** rollback lần nữa khi `commit` ném exception. Giải thích vì sao.

### Câu hỏi tự kiểm tra

- Khi `inner.isNewTransaction()==false`, có chắc inner đang chạy ngoài transaction không?
- `setRollbackOnly()` đã thực hiện physical rollback ngay chưa?
- Tại sao `isCompleted()==true` của inner vẫn có thể đi cùng `outer.isCompleted()==false`?
- Tại sao một outer scope không tự gọi `setRollbackOnly` vẫn có thể thấy `isRollbackOnly()==true`?
- Khi `commit(status)` ném `UnexpectedRollbackException`, nên gọi tiếp `rollback(status)` không?
- Hai status đều `new=true` có nhất thiết dùng chung physical transaction không?
- `hasSavepoint()==true` cho biết điều gì mà `isNewTransaction()` không tự cho biết?

**Kết luận:** ba cờ cần được hiểu theo **một scope `TransactionStatus` cụ thể**: `isNewTransaction` nói về nguồn gốc transaction của scope, `isRollbackOnly` nói về **ý định/khả năng rollback**, còn `isCompleted` nói về **scope đã được kết thúc**. Không cờ nào riêng lẻ là bản báo cáo toàn diện về commit thực tế; hãy kết hợp propagation, transaction manager, exception và kết quả dữ liệu sau boundary.

## 12. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — `TransactionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html): status của transaction, `hasSavepoint()` và kế thừa `TransactionExecution`.
- [Spring Framework 6.2 — `TransactionExecution` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionExecution.html): `isNewTransaction`, `isRollbackOnly`, `isCompleted`, `setRollbackOnly`.
- [Spring Framework 6.2 — `PlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html): `getTransaction`, `commit`, `rollback` và hợp đồng không rollback sau commit failure.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): dùng `TransactionTemplate` hoặc transaction manager trực tiếp.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical/physical scopes, `REQUIRED`, `REQUIRES_NEW`, `NESTED`, rollback-only và `UnexpectedRollbackException`.
- [Spring Framework — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): điều phối participating transaction và rollback-only.
